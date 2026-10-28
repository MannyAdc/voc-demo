"""B7 and B8: record and replay of model answers, with every live call through the ledger.

A backend is any callable `backend(prompt, settings)` that returns an Answer
(or an object with the same four fields) or raises. The real clients come
later (T009). Tests use fake backends.

Everything a backend sends to the model must come from the prompt or the
settings. A system prompt, tools or examples sent any other way would be in
neither the worst-case estimate nor the recording key. Settings must be JSON
values (tuples become lists).

A recording is keyed by a SHA-256 hash of the backend, the model, the
settings (sorted) and the exact prompt. It holds only that key material, the
answer text, the token use and the live cost in tokens. It never holds
headers or keys. Failed, refused and cut-off calls are never stored, and
neither are calls with no full usage report.

Recordings live in the home folder next to the ledger, so all worktrees share
one cache. A recorded answer is served with no backend and no ledger, so it
costs nothing and works when the budget is spent. In replay mode a missing
recording is an error, never a live call. A corrupt recording is an error in
both modes, never a silent paid call.

B21: errors never hold backend text. A stop reason is named only if it is a
known one, anything else is `other`.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from voc.budget import Ledger, atomic_write, load_config, require_clean_config, voc_home, worst_case

# The SDK must never retry on its own. Every retry is a new call through the ledger (T009 uses this).
SDK_MAX_RETRIES = 0
MAX_RETRIES = 2
OK_STOP_REASONS = frozenset({"end_turn", "stop_sequence"})
KNOWN_STOP_REASONS = frozenset({"max_tokens", "refusal", "tool_use", "pause_turn",
                                "model_context_window_exceeded"})
MODES = ("live", "replay")


class ModelError(Exception):
    """The call failed, was refused or was cut off (quarantine reason `model_error`). The message is ours."""


class RecordingMissing(Exception):
    """Replay mode found no recording for this call. The message is ours."""


class RecordingCorrupt(Exception):
    """A recording exists for this key but cannot be used. The message is ours."""


@dataclass(frozen=True)
class Answer:
    """What a backend returns. Token counts are None when the backend reports no usage."""
    text: str
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str


@dataclass(frozen=True)
class Reply:
    """What a call returns. `charged_tokens` is this call's cost, `live_cost_tokens` the original live cost."""
    text: str
    source: str
    input_tokens: int | None
    output_tokens: int | None
    charged_tokens: int
    live_cost_tokens: int
    attempts: int


def recordings_dir():
    return voc_home() / "recordings"


def _key_material(backend, model, settings, prompt):
    return {"backend": backend, "model": model, "settings": dict(sorted(settings.items())), "prompt": prompt}


def _canonical(material):
    return json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def recording_key(backend, model, settings, prompt):
    """A stable SHA-256 hash of the backend, the model, the sorted settings and the exact prompt."""
    return hashlib.sha256(_canonical(_key_material(backend, model, settings, prompt)).encode("utf-8")).hexdigest()


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usage(answer):
    """Input plus output tokens, or None unless both counts are reported."""
    counts = (_count(answer.input_tokens), _count(answer.output_tokens))
    return None if None in counts else sum(counts)


def _stop_name(stop):
    return stop if isinstance(stop, str) and stop in KNOWN_STOP_REASONS else "other"


def _valid_record(record, key, canonical):
    try:
        usage = record["usage"]
        return (record["key"] == key and _canonical(record["key_material"]) == canonical
                and isinstance(record["text"], str) and isinstance(usage, dict)
                and _count(usage["input_tokens"]) is not None and _count(usage["output_tokens"]) is not None
                and _count(record["live_cost_tokens"]) is not None)
    except (KeyError, TypeError):
        return False


class Caller:
    """Calls one backend and model with fixed settings, through the recordings and the ledger."""

    def __init__(self, backend_name, model, settings, backend=None, mode="live", root=None, ledger=None):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        self.backend_name = backend_name
        self.model = model
        self.settings = dict(settings)
        self.backend = backend
        self.mode = mode
        self.root = Path.cwd() if root is None else Path(root)
        self.ledger = ledger

    def _path(self, key):
        return recordings_dir() / f"{key}.json"

    def _load(self, key, material):
        path = self._path(key)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RecordingCorrupt(f"the recording {key} cannot be read") from None
        if not isinstance(record, dict) or not _valid_record(record, key, _canonical(material)):
            raise RecordingCorrupt(f"the recording {key} is not valid")
        return record

    def _store(self, key, material, answer, cost):
        record = {"key": key, "key_material": material, "text": answer.text,
                  "usage": {"input_tokens": answer.input_tokens, "output_tokens": answer.output_tokens},
                  "live_cost_tokens": cost}
        recordings_dir().mkdir(parents=True, exist_ok=True)
        atomic_write(self._path(key), json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    def call(self, prompt):
        material = _key_material(self.backend_name, self.model, self.settings, prompt)
        key = recording_key(self.backend_name, self.model, self.settings, prompt)
        record = self._load(key, material)
        if record is not None:
            usage = record["usage"]
            return Reply(record["text"], "replay", usage["input_tokens"], usage["output_tokens"],
                         0, record["live_cost_tokens"], 0)
        if self.mode == "replay":
            raise RecordingMissing("no recording for this call, and replay mode never calls the model")
        return self._live(prompt, key, material)

    def _live(self, prompt, key, material):
        if self.backend is None:
            raise ModelError("live mode needs a backend")
        require_clean_config(self.root)
        margin = load_config(self.root)["input_margin_tokens"]
        output_limit = self.settings.get("max_tokens")
        if not isinstance(output_limit, int) or isinstance(output_limit, bool) or output_limit <= 0:
            raise ModelError("the settings need a whole number max_tokens, so the worst case can be reserved")
        ledger = self.ledger or Ledger()
        reservation = worst_case(prompt, output_limit, margin)
        failure = None
        for attempt in range(1, MAX_RETRIES + 2):
            rid = ledger.reserve(reservation)  # CapReached or Overrun stops here, before anything is sent
            try:
                answer = self.backend(prompt, dict(self.settings))
            except Exception as err:  # the type only, never the message
                ledger.settle(rid, None)
                failure = type(err).__name__
                continue
            used = _usage(answer)
            ledger.settle(rid, used)
            charged = reservation if used is None else used
            if not (isinstance(answer.stop_reason, str) and answer.stop_reason in OK_STOP_REASONS):
                raise ModelError(f"the model call ended with stop reason {_stop_name(answer.stop_reason)}")
            if not isinstance(answer.text, str):
                raise ModelError("the backend answer has no text")
            if used is not None:
                self._store(key, material, answer, charged)
            return Reply(answer.text, "live", answer.input_tokens, answer.output_tokens, charged, charged, attempt)
        raise ModelError(f"the model call failed {MAX_RETRIES + 1} times, last error {failure}")
