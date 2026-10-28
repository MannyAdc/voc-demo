"""Build the labelling prompt and parse the model's answer (B4, B5).

The prompt is built only from the prompt version's instruction block, the
label list, optional label definitions, the complaint text and optional
training examples. No other field of a complaint can be passed in.

Complaint text is data. It sits between two fixed tags. A text that holds
either tag, or a lookalike, is refused before any model call.
"""
import html
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

OPEN_TAG = "<complaint>"
CLOSE_TAG = "</complaint>"

BOUNDARY_IN_TEXT = "boundary_in_text"
UNPARSEABLE = "unparseable"
INVALID_LABEL = "invalid_label"

TRAIN_SPLIT = "train"

# Either tag, with any capitals and any spaces inside the angle brackets.
# Attributes after the name are caught too, so "<complaint x>" is refused.
_TAG = re.compile(r"<\s*/?\s*complaint(?:\s[^<>]*)?>", re.IGNORECASE)

# One answer, optionally inside one code fence with an optional language word.
_FENCE = re.compile(r"\A```[A-Za-z]*[ \t]*\r?\n(.*?)\r?\n?```\Z", re.DOTALL)

# Entity decoding stops after this many rounds. Each round makes the text
# shorter, so real text settles long before this.
_MAX_DECODE_ROUNDS = 10


class BoundaryInText(ValueError):
    """The complaint text holds a boundary tag. No prompt is built."""

    reason = BOUNDARY_IN_TEXT


class ExampleRefused(ValueError):
    """An example is not allowed in the prompt."""


@dataclass(frozen=True)
class Example:
    """A training example: its ID, its split, its text and its recorded label."""

    complaint_id: str
    split: str
    text: str
    label: str


@dataclass(frozen=True)
class BuiltPrompt:
    """The prompt string and the IDs of the examples it shows, for the log."""

    prompt: str
    example_ids: tuple[str, ...]


@dataclass(frozen=True)
class ParsedAnswer:
    """A parsed answer. The reason is None when the answer is usable.

    For `invalid_label`, the proposed label and quote are kept for review.
    """

    label: str | None
    quote: str | None
    reason: str | None


def _normalise(text):
    """Decode HTML entities until stable, then fold lookalike characters."""
    for _ in range(_MAX_DECODE_ROUNDS):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = unicodedata.normalize("NFKC", text)
    # Drop invisible format characters, such as zero-width spaces.
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def boundary_reason(text):
    """Return `boundary_in_text` if the text holds a boundary tag, else None.

    The caller runs this before any model call.
    """
    if _TAG.search(_normalise(text)):
        return BOUNDARY_IN_TEXT
    return None


def _check_labels(labels):
    if isinstance(labels, str) or not isinstance(labels, Sequence):
        raise TypeError("labels must be a list of strings")
    labels = list(labels)
    if not labels:
        raise ValueError("labels must not be empty")
    for label in labels:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("each label must be a non-empty string")
    if len(set(labels)) != len(labels):
        raise ValueError("labels must not repeat")
    return labels


def _check_definitions(definitions, labels):
    if definitions is None:
        return {}
    if not isinstance(definitions, Mapping):
        raise TypeError("definitions must be a mapping from label to text")
    unknown = sorted(set(definitions) - set(labels))
    if unknown:
        raise ValueError(f"definitions name labels not in the list: {unknown}")
    for value in definitions.values():
        if not isinstance(value, str):
            raise TypeError("each definition must be a string")
    return dict(definitions)


def _check_examples(examples, labels):
    if isinstance(examples, (str, Mapping)) or not isinstance(examples, Sequence):
        raise TypeError("examples must be a list of Example")
    checked = []
    for example in examples:
        if not isinstance(example, Example):
            raise TypeError("each example must be an Example")
        if example.split != TRAIN_SPLIT:
            raise ExampleRefused(f"example {example.complaint_id} is not from the training split")
        if not isinstance(example.text, str) or boundary_reason(example.text):
            raise ExampleRefused(f"example {example.complaint_id} text holds a boundary tag")
        if example.label not in labels:
            raise ExampleRefused(f"example {example.complaint_id} label is not in the list")
        checked.append(example)
    return checked


def _wrap(text):
    return f"{OPEN_TAG}\n{text}\n{CLOSE_TAG}"


def build_prompt(instructions, labels, text, definitions=None, examples=()):
    """Build the prompt. The same inputs always give the same string.

    Raises BoundaryInText if the complaint text holds a boundary tag, and
    ExampleRefused for an example that is not allowed.
    """
    if not isinstance(instructions, str):
        raise TypeError("instructions must be a string")
    if not isinstance(text, str):
        raise TypeError("text must be the complaint text as a string")
    labels = _check_labels(labels)
    definitions = _check_definitions(definitions, labels)
    examples = _check_examples(examples, labels)
    if boundary_reason(text):
        raise BoundaryInText(BOUNDARY_IN_TEXT)

    # Definitions follow the label order, never the mapping's order.
    label_lines = ["Allowed labels:"]
    for label in labels:
        if label in definitions:
            label_lines.append(f"- {label}: {definitions[label]}")
        else:
            label_lines.append(f"- {label}")

    sections = [instructions.strip(), "\n".join(label_lines)]
    for number, example in enumerate(examples, start=1):
        sections.append(f"Example {number}:\n{_wrap(example.text)}\nLabel: {example.label}")
    sections.append(f"Complaint to label:\n{_wrap(text)}")
    return BuiltPrompt(
        prompt="\n\n".join(sections),
        example_ids=tuple(example.complaint_id for example in examples),
    )


def _no_repeated_keys(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("repeated key")
    return dict(pairs)


def _refuse_constant(name):
    raise ValueError(f"not allowed: {name}")


def parse_answer(answer, labels):
    """Parse one model answer against the label list.

    The answer must be exactly one JSON object with exactly the text keys
    `label` and `quote`, optionally inside one code fence. Anything else is
    `unparseable`. A label not in the list is `invalid_label`.
    """
    failed = ParsedAnswer(label=None, quote=None, reason=UNPARSEABLE)
    if not isinstance(answer, str):
        return failed
    body = answer.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        value = json.loads(body, object_pairs_hook=_no_repeated_keys, parse_constant=_refuse_constant)
    except ValueError:
        return failed
    if not isinstance(value, dict) or set(value) != {"label", "quote"}:
        return failed
    label, quote = value["label"], value["quote"]
    if not isinstance(label, str) or not isinstance(quote, str):
        return failed
    if label not in labels:
        return ParsedAnswer(label=label, quote=quote, reason=INVALID_LABEL)
    return ParsedAnswer(label=label, quote=quote, reason=None)
