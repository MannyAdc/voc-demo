"""B3 and B5: decide whether one model answer is accepted or quarantined.

Before any call, a complaint with no text is `no_narrative` and a text with a
boundary tag is `boundary_in_text`, so neither is sent to the model. After the
call, checks run in a fixed order: model call, parse, label, quote. The first
failure names the one reason. A quarantined decision keeps the proposal for
review but never has an accepted label. TF-IDF's label is never an input.
"""
from dataclasses import dataclass

from voc.evidence import check_quote
from voc.prompt import boundary_reason, parse_answer

NO_NARRATIVE = "no_narrative"
MODEL_ERROR = "model_error"
NOT_RUN_BUDGET = "not_run_budget"
CALL_STATUSES = {"ok", "failed", "refused", "cut_off", NOT_RUN_BUDGET}


@dataclass(frozen=True)
class CallOutcome:
    """What came back from one model call. `status` is one of CALL_STATUSES."""
    status: str
    answer: str | None = None


@dataclass(frozen=True)
class Decision:
    complaint_id: str
    label: str | None = None
    reason: str | None = None
    proposed_label: str | None = None
    proposed_quote: str | None = None
    quote_start: int | None = None
    quote_end: int | None = None

    @property
    def accepted(self):
        return self.reason is None and self.label is not None


def before_call(text):
    """The reason a complaint is not sent to the model at all, or None."""
    if not text or not text.strip():
        return NO_NARRATIVE
    return boundary_reason(text)


def decide(complaint_id, text, outcome, labels):
    if outcome.status not in CALL_STATUSES:
        raise ValueError(f"unknown call status {outcome.status!r}, expected one of {sorted(CALL_STATUSES)}")
    early = before_call(text)
    if early:
        return Decision(complaint_id, reason=early)
    if outcome.status == NOT_RUN_BUDGET:
        return Decision(complaint_id, reason=NOT_RUN_BUDGET)
    if outcome.status != "ok":
        return Decision(complaint_id, reason=MODEL_ERROR)
    parsed = parse_answer(outcome.answer, labels)
    proposal = {"proposed_label": parsed.label, "proposed_quote": parsed.quote}
    if parsed.reason:
        return Decision(complaint_id, reason=parsed.reason, **proposal)
    evidence = check_quote(text, parsed.quote)
    if not evidence.ok:
        return Decision(complaint_id, reason=evidence.reason, **proposal)
    return Decision(complaint_id, label=parsed.label, quote_start=evidence.start, quote_end=evidence.end, **proposal)
