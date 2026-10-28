"""B4, B5, B9: label complaints, one at a time, in complaint ID order.

A complaint here holds only its ID and its text, so its recorded Product
cannot reach the prompt (B4). The text is cut at 4,000 characters, and the
model sees and quotes only the cut text (B9). A text with no words or with a
boundary tag is decided with no call (B5, B9). Once the cap is reached, that
complaint and every later one is `not_run_budget`, with no more calls (B8).
A missing recording in replay mode stops the run (B7).

B21: the results hold IDs, labels, reasons, positions and counts only. A
proposed label outside the list is model text, so it is written as a marker.
"""
import csv
import hashlib
import io
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from voc.backends import API_VERSION
from voc.baselines import cut_text
from voc.budget import BudgetError
from voc.data import SampleMismatch, _manifest, _month_rows, quick_check_ids, read_splits, verify_ids
from voc.decision import NOT_RUN_BUDGET, CallOutcome, Decision, before_call, decide
from voc.prompt import build_prompt
from voc.replay import ModelError, recording_key

SETS = ("dev", "quick")
NOT_IN_LIST = "(not in list)"
RESULT_FIELDS = ("complaint_id", "split", "prompt_version", "proposed_label", "quote_start", "quote_end",
                 "decision", "reason", "label", "cut", "recording_key", "source", "input_tokens", "output_tokens")


@dataclass(frozen=True)
class Complaint:
    complaint_id: str
    narrative: str


@dataclass(frozen=True)
class PromptVersion:
    name: str
    instructions: str
    settings: dict


@dataclass(frozen=True)
class Outcome:
    """One complaint's decision, with what the run needs to record. No text."""
    decision: Decision
    cut: bool
    source: str | None = None
    recording_key: str | None = None
    prompt_bytes: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    charged_tokens: int = 0
    live_cost_tokens: int = 0


def load_prompt_version(root, name):
    with open(Path(root) / "config" / "prompts" / f"{name}.toml", "rb") as f:
        raw = tomllib.load(f)
    if raw.get("name") != name:
        raise ValueError(f"config/prompts/{name}.toml names itself {raw.get('name')!r}")
    settings = dict(raw["settings"])
    if settings.get("api_version") != API_VERSION:
        raise ValueError(f"prompt {name} is set for API version {settings.get('api_version')!r}, "
                         f"but the backend sends {API_VERSION}")
    return PromptVersion(name=name, instructions=raw["instructions"], settings=settings)


def definitions(labels):
    """Each label's definition: the sub-products the CFPB form lists under it (B24)."""
    return {label.name: "includes " + ", ".join(label.covers) for label in labels}


def _id_number(complaint_id):
    digits = "".join(ch for ch in complaint_id.split("-")[-1] if ch.isdigit())
    return (int(digits) if digits else float("inf"), complaint_id)


def label_complaints(complaints, version, labels, call, backend_name):
    """Decide every complaint, in complaint ID order. `call(prompt)` returns a Reply or raises."""
    names = [label.name for label in labels]
    defined = definitions(labels)
    model = version.settings["model"]
    outcomes, budget_stopped = [], False
    for complaint in sorted(complaints, key=lambda c: _id_number(c.complaint_id)):
        text, cut = cut_text(complaint.narrative)
        cid = complaint.complaint_id
        if before_call(text):
            outcomes.append(Outcome(decide(cid, text, CallOutcome("ok"), names), cut))
            continue
        if budget_stopped:
            outcomes.append(Outcome(Decision(cid, reason=NOT_RUN_BUDGET), cut))
            continue
        prompt = build_prompt(version.instructions, names, text, complaint_id=cid, definitions=defined).prompt
        key = recording_key(backend_name, model, version.settings, prompt)
        size = len(prompt.encode("utf-8"))
        try:
            reply = call(prompt)
        except BudgetError:
            budget_stopped = True
            outcomes.append(Outcome(Decision(cid, reason=NOT_RUN_BUDGET), cut, recording_key=key, prompt_bytes=size))
            continue
        except ModelError:
            outcomes.append(Outcome(decide(cid, text, CallOutcome("failed"), names), cut, recording_key=key,
                                    prompt_bytes=size))
            continue
        outcomes.append(Outcome(decide(cid, text, CallOutcome("ok", reply.text), names), cut, reply.source, key,
                                size, reply.input_tokens, reply.output_tokens, reply.charged_tokens,
                                reply.live_cost_tokens))
    return outcomes


def token_pairs(outcomes):
    """(prompt bytes, real input tokens) for each live call, sorted, so no pair points to a complaint (T014b)."""
    return sorted([o.prompt_bytes, o.input_tokens] for o in outcomes
                  if o.source == "live" and o.input_tokens is not None)


def load_complaints(db_path, splits_dir, set_name):
    """The complaints of a development set, checked against the frozen list. Never the test set (B16, B17)."""
    if set_name not in SETS:
        raise SampleMismatch(f"only {' and '.join(SETS)} can be labelled here. The test set waits for the final run")
    manifest = _manifest(splits_dir)
    wanted = set(quick_check_ids(splits_dir)) if set_name == "quick" else set(read_splits(splits_dir)["dev"])
    rows = [row for row in _month_rows(db_path, manifest["month"]) if row.complaint_id in wanted]
    found = {row.complaint_id for row in rows}
    if found != wanted:
        raise SampleMismatch(f"{len(wanted - found)} development complaints are missing from the staged table")
    verify_ids(splits_dir, "dev", rows)
    return [Complaint(row.complaint_id, row.narrative) for row in rows]


def _proposed(decision, names):
    label = decision.proposed_label
    if label is None:
        return ""
    return label if label in names else NOT_IN_LIST


def results_csv(outcomes, set_name, version, names):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=RESULT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for o in outcomes:
        d = o.decision
        writer.writerow({
            "complaint_id": d.complaint_id, "split": "dev", "prompt_version": version.name,
            "proposed_label": _proposed(d, names), "quote_start": "" if d.quote_start is None else d.quote_start,
            "quote_end": "" if d.quote_end is None else d.quote_end,
            "decision": "accepted" if d.accepted else "quarantined", "reason": d.reason or "",
            "label": d.label or "", "cut": "yes" if o.cut else "no", "recording_key": o.recording_key or "",
            "source": o.source or "", "input_tokens": "" if o.input_tokens is None else o.input_tokens,
            "output_tokens": "" if o.output_tokens is None else o.output_tokens})
    return out.getvalue()


def summarise(outcomes, set_name, version, backend_name, list_sha256):
    """Counts only (B21)."""
    reasons, accepted = {}, {}
    for o in outcomes:
        d = o.decision
        if d.accepted:
            accepted[d.label] = accepted.get(d.label, 0) + 1
        else:
            reasons[d.reason] = reasons.get(d.reason, 0) + 1
    sources = {}
    for o in outcomes:
        if o.source:
            sources[o.source] = sources.get(o.source, 0) + 1
    pairs = token_pairs(outcomes)
    return {"set": set_name, "prompt_version": version.name, "backend": backend_name,
            "model": version.settings["model"], "settings": version.settings, "list_sha256": list_sha256,
            "complaints": len(outcomes), "accepted": sum(accepted.values()),
            "quarantined": sum(reasons.values()), "accepted_by_label": dict(sorted(accepted.items())),
            "quarantine_reasons": dict(sorted(reasons.items())), "cut": sum(o.cut for o in outcomes),
            "calls_by_source": dict(sorted(sources.items())),
            "input_tokens": sum(o.input_tokens or 0 for o in outcomes),
            "output_tokens": sum(o.output_tokens or 0 for o in outcomes),
            "charged_tokens": sum(o.charged_tokens for o in outcomes),
            "live_cost_tokens": sum(o.live_cost_tokens for o in outcomes),
            "token_pairs": pairs,
            "largest_tokens_over_bytes": max((t - b for b, t in pairs), default=None)}


def write_run(folder, outcomes, summary, version, names):
    """Write the results file and the run summary. A run on another backend never overwrites one (B12)."""
    folder = Path(folder)
    stem = f"{version.name}_{summary['set']}"
    summary_path = folder / f"{stem}.json"
    if summary_path.exists():
        before = json.loads(summary_path.read_text(encoding="utf-8"))
        if before.get("backend") != summary["backend"]:
            raise SampleMismatch(f"{summary_path.name} holds a run on the {before.get('backend')} backend, "
                                 f"so a {summary['backend']} run would mix backends. Move it first")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.csv").write_text(results_csv(outcomes, summary["set"], version, names), encoding="utf-8",
                                        newline="")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="")
    return folder / f"{stem}.csv"


def list_sha256(splits_dir, set_name, complaints):
    """The dev list's hash for the whole set, or a hash of the IDs used when the set is a part of it."""
    manifest = _manifest(splits_dir)
    if set_name == "dev" and len(complaints) == manifest["lists"]["dev"]["count"]:
        return manifest["lists"]["dev"]["sha256"]
    ids = "\n".join(sorted((c.complaint_id for c in complaints), key=_id_number))
    return hashlib.sha256(ids.encode("utf-8")).hexdigest()


def format_run(summary, results_path):
    lines = [f"labelled {summary['set']}: {summary['complaints']} complaints, prompt {summary['prompt_version']}, "
             f"backend {summary['backend']}, model {summary['model']}",
             f"accepted {summary['accepted']}, quarantined {summary['quarantined']}"]
    lines += [f"  accepted as {label}: {n}" for label, n in summary["accepted_by_label"].items()]
    lines += [f"  quarantined as {reason}: {n}" for reason, n in summary["quarantine_reasons"].items()]
    lines.append(f"cut at 4,000 characters: {summary['cut']}")
    lines.append("calls: " + (", ".join(f"{n} {s}" for s, n in summary["calls_by_source"].items()) or "none"))
    lines.append(f"tokens: input {summary['input_tokens']}, output {summary['output_tokens']}, "
                 f"charged in the ledger by this run {summary['charged_tokens']}")
    if summary.get("cost"):
        lines.append(f"cost: this run ${summary['cost']['own_cost_usd']}, "
                     f"original live ${summary['cost']['live_cost_usd']}")
    if summary["largest_tokens_over_bytes"] is not None:
        lines.append(f"largest (real input tokens minus prompt bytes): {summary['largest_tokens_over_bytes']}")
    lines.append(f"results: {Path(results_path).as_posix()}")
    return "\n".join(lines)
