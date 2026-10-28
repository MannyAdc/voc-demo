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
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

OPEN_TAG = "<complaint>"
CLOSE_TAG = "</complaint>"

BOUNDARY_IN_TEXT = "boundary_in_text"
UNPARSEABLE = "unparseable"
INVALID_LABEL = "invalid_label"

TRAIN_SPLIT = "train"

# The start of either tag, with any capitals and any spaces or slashes after
# the "<". No closing ">" is needed, so a fragment such as "</complaint" at
# the end of a text, "<complaint/>" and "<complaint x>" are all caught.
_TAG = re.compile(r"<[\s/]*complaint\b", re.IGNORECASE)

# One answer, optionally inside one code fence. The fence may name the
# language "json", in any capitals, or nothing. Any other word, such as
# "json5", is unparseable, because its content need not be strict JSON.
_FENCE = re.compile(r"\A```(?i:json)?[ \t]*\r?\n(.*?)\r?\n?```\Z", re.DOTALL)

# Folding stops after this many rounds. Real text settles in one or two.
# A text still changing after this is treated as holding a tag.
_MAX_FOLD_ROUNDS = 50

# Extra guard beyond the wording of B5: characters that look like the
# letters of "complaint", like "<" or ">", or like "/". They are folded to
# the plain character for the tag check only. The prompt keeps the text as
# written.
_LOOKALIKES = str.maketrans(
    {
        # Cyrillic letters
        0x0430: "a", 0x0410: "A", 0x0441: "c", 0x0421: "C", 0x0435: "e",
        0x0415: "E", 0x0456: "i", 0x0406: "I", 0x043C: "m", 0x041C: "M",
        0x043E: "o", 0x041E: "O", 0x0440: "p", 0x0420: "P", 0x0442: "t",
        0x0422: "T", 0x043F: "n", 0x041D: "H",
        # Greek letters
        0x03B1: "a", 0x0391: "A", 0x03B9: "i", 0x0399: "I", 0x039C: "M",
        0x039D: "N", 0x03BF: "o", 0x039F: "O", 0x03C1: "p", 0x03A1: "P",
        0x03A4: "T",
        # Angle quotes and brackets
        0x2039: "<", 0x00AB: "<", 0x3008: "<", 0x27E8: "<", 0x02C2: "<",
        0x276C: "<", 0x276E: "<",
        0x203A: ">", 0x00BB: ">", 0x3009: ">", 0x27E9: ">", 0x02C3: ">",
        0x276D: ">", 0x276F: ">",
        # Slashes
        0x2044: "/", 0x2215: "/", 0x29F8: "/",
    }
)


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


def _fold_once(text):
    """One round of decoding and folding, for the tag check only."""
    text = html.unescape(text)
    # Extra guard beyond the wording of B5: URL encoding, such as "%3C".
    text = urllib.parse.unquote(text)
    text = unicodedata.normalize("NFKC", text)
    # Drop invisible format characters, such as zero-width spaces.
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return text.translate(_LOOKALIKES)


def _fold(text):
    """Fold until the text stops changing. None if it never settles."""
    for _ in range(_MAX_FOLD_ROUNDS):
        folded = _fold_once(text)
        if folded == text:
            return text
        text = folded
    return None


def boundary_reason(text):
    """Return `boundary_in_text` if the text holds a boundary tag, else None.

    The caller runs this before any model call. B5 asks for capitals, spaces
    and HTML entities to be ignored. As an extra guard, the check also
    ignores URL encoding, NFKC lookalikes, invisible format characters, and
    Cyrillic, Greek, angle-quote and slash lookalikes. Decoding repeats until
    the text stops changing. A text that never settles is refused.
    """
    folded = _fold(text)
    if folded is None or _TAG.search(folded):
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


def _check_examples(examples, labels, complaint_id):
    if isinstance(examples, (str, Mapping)) or not isinstance(examples, Sequence):
        raise TypeError("examples must be a list of Example")
    checked = []
    for example in examples:
        if not isinstance(example, Example):
            raise TypeError("each example must be an Example")
        if example.complaint_id == complaint_id:
            raise ExampleRefused(f"example {example.complaint_id} is the complaint being labelled")
        # The split is the caller's word for now. Checking example IDs
        # against the committed training list comes later, once `splits/`
        # exists.
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


def build_prompt(instructions, labels, text, *, complaint_id, definitions=None, examples=()):
    """Build the prompt. The same inputs always give the same string.

    The complaint ID is used only to refuse an example that is the complaint
    itself. It is not put in the prompt.

    Raises BoundaryInText if the complaint text holds a boundary tag, and
    ExampleRefused for an example that is not allowed.
    """
    if not isinstance(instructions, str):
        raise TypeError("instructions must be a string")
    if not isinstance(text, str):
        raise TypeError("text must be the complaint text as a string")
    if not isinstance(complaint_id, str) or not complaint_id.strip():
        raise ValueError("complaint_id must be a non-empty string")
    labels = _check_labels(labels)
    definitions = _check_definitions(definitions, labels)
    examples = _check_examples(examples, labels, complaint_id)
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
    `unparseable`. Text that cannot be written as UTF-8, such as a lone
    surrogate, is `unparseable` too. A label not in the list is
    `invalid_label`.
    """
    labels = _check_labels(labels)
    failed = ParsedAnswer(label=None, quote=None, reason=UNPARSEABLE)
    if not isinstance(answer, str):
        return failed
    body = answer.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        value = json.loads(body, object_pairs_hook=_no_repeated_keys, parse_constant=_refuse_constant)
    except (ValueError, RecursionError):
        # Deep nesting raises RecursionError, which is not a ValueError.
        return failed
    if not isinstance(value, dict) or set(value) != {"label", "quote"}:
        return failed
    label, quote = value["label"], value["quote"]
    if not isinstance(label, str) or not isinstance(quote, str):
        return failed
    try:
        label.encode("utf-8")
        quote.encode("utf-8")
    except UnicodeEncodeError:
        return failed
    if label not in labels:
        return ParsedAnswer(label=label, quote=quote, reason=INVALID_LABEL)
    return ParsedAnswer(label=label, quote=quote, reason=None)
