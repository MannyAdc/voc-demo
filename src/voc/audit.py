"""B1, B19: check a finished labelling run against its recorded answers and the complaint texts.

This is a consistency check, made after the run. It reuses the labeller's own steps (the text cut, the
prompt, the answer parser and the quote check), so it cannot find a bug in those steps. What it proves is
that the committed results file, the recorded answers and the staged texts all agree. For every row it:

1. checks that the row's complaint is in the committed list, once, and that no listed complaint is missing,
2. rebuilds the exact prompt from the staged text (B16) and checks that its recording key is the row's key,
3. loads the recorded answer, whose key material must match (B7),
4. decides the complaint again from that answer, and checks that the decision, the reason, the label and
   the quote's start and end are the ones in the row.

One part is independent of the quote check: for each accepted label, the characters at the stored start
and end are compared with the model's quote as plain text.

It calls no model and prints counts only, never text (B21).
"""
import csv
import io
import json
from collections import Counter
from pathlib import Path

from voc.baselines import cut_text
from voc.decision import MODEL_ERROR, NOT_RUN_BUDGET, CallOutcome, before_call, decide
from voc.labels import load_labels
from voc.load import DB_PATH
from voc.pipeline import definitions, load_complaints, load_prompt_version
from voc.prompt import UNPARSEABLE, build_prompt
from voc.replay import Caller, RecordingCorrupt, _key_material, recording_key

FAILURES = ("not_in_list", "duplicate_row", "missing_row", "count_differs", "key_differs", "recording_missing",
            "recording_invalid", "answer_unparseable", "quote_not_found", "decision_differs", "label_differs",
            "position_differs")
NO_ANSWER = (MODEL_ERROR, NOT_RUN_BUDGET)  # no answer was recorded for these, so there is nothing to decide again


class AuditError(ValueError):
    pass


def _cell(value):
    return "" if value is None else str(value)


def _compare(derived, row):
    """The kind of failure, or None when the decision made again is the one in the row."""
    accepted = row["decision"] == "accepted"
    if derived.accepted != accepted or _cell(derived.reason) != row["reason"]:
        if derived.reason == UNPARSEABLE:
            return "answer_unparseable"
        if accepted and derived.reason == "quote_not_in_text":
            return "quote_not_found"
        return "decision_differs"
    if derived.accepted and derived.label != row["accepted_label"]:
        return "label_differs"
    if (_cell(derived.quote_start), _cell(derived.quote_end)) != (row["quote_start"], row["quote_end"]):
        return "position_differs"
    return None


def audit(root, set_name, version_name):
    """Counts of rows checked, and of each kind of failure."""
    root = Path(root)
    folder = root / "results" / "labels"
    summary_path, results_path = folder / f"{version_name}_{set_name}.json", folder / f"{version_name}_{set_name}.csv"
    if not summary_path.exists() or not results_path.exists():
        raise AuditError(f"no run of prompt {version_name} on the {set_name} set to audit")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("stopped"):
        raise AuditError(f"{summary_path.name} records a run that stopped early, so it is not audited (B7)")
    if summary.get("backend") != "api":
        raise AuditError("only an api run has recorded answers to audit")
    version = load_prompt_version(root, version_name)
    labels = load_labels(root / "config" / "labels.toml")
    names = [label.name for label in labels]
    defined = definitions(labels)
    model, settings = version.settings["model"], version.settings
    complaints = {c.complaint_id: c for c in load_complaints(root / DB_PATH, root / "splits", set_name)}
    caller = Caller("api", model, settings, mode="replay", root=root)

    rows = list(csv.DictReader(io.StringIO(results_path.read_text(encoding="utf-8"))))
    failures = Counter()
    ids = Counter(r["complaint_id"] for r in rows)
    failures["duplicate_row"] = sum(n - 1 for n in ids.values())
    failures["missing_row"] = len(set(complaints) - set(ids))
    accepted_rows = sum(r["decision"] == "accepted" for r in rows)
    failures["count_differs"] = int(summary.get("complaints") != len(rows) or summary.get("accepted") != accepted_rows)

    verified, word_for_word, rederived, quarantined, no_answer, listed = 0, 0, 0, 0, 0, 0
    seen = set()
    for row in rows:
        complaint = complaints.get(row["complaint_id"])
        if complaint is None:
            failures["not_in_list"] += 1
            continue
        if row["complaint_id"] in seen:
            continue  # counted as a duplicate above
        seen.add(row["complaint_id"])
        listed += 1
        if row["decision"] != "accepted":
            quarantined += 1
        text, _ = cut_text(complaint.narrative)
        if before_call(text):
            derived = decide(complaint.complaint_id, text, CallOutcome("ok"), names)
        elif row["reason"] in NO_ANSWER:
            no_answer += 1
            continue
        else:
            prompt = build_prompt(version.instructions, names, text, complaint_id=complaint.complaint_id,
                                  definitions=defined).prompt
            key = recording_key("api", model, settings, prompt)
            if key != row["recording_key"]:
                failures["key_differs"] += 1
                continue
            try:
                record = caller._load(key, _key_material("api", model, settings, prompt))
            except RecordingCorrupt:
                failures["recording_invalid"] += 1
                continue
            if record is None:
                failures["recording_missing"] += 1
                continue
            derived = decide(complaint.complaint_id, text, CallOutcome("ok", record["text"]), names)
        kind = _compare(derived, row)
        if kind:
            failures[kind] += 1
        elif derived.accepted:
            verified += 1
            word_for_word += text[derived.quote_start:derived.quote_end] == derived.proposed_quote
        else:
            rederived += 1
    result = {"set": set_name, "prompt_version": version_name, "listed": len(complaints), "rows_listed": listed,
              "accepted": accepted_rows, "verified": verified, "word_for_word": word_for_word,
              "quarantined": quarantined, "rederived": rederived, "no_answer": no_answer,
              "failures": {k: failures[k] for k in FAILURES if failures[k]}}
    # A6: the counts are committed, so the dashboard can show them without the recordings.
    out = root / "results" / "audit" / f"{version_name}_{set_name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="")
    return result


def format_audit(result):
    lines = [f"audited prompt {result['prompt_version']} on {result['set']}: re-verified {result['verified']} of "
             f"{result['accepted']} accepted labels",
             f"  word for word at the stored position: {result['word_for_word']} "
             "(a plain character comparison, independent of the quote check)",
             f"  re-derived {result['rederived']} of {result['quarantined']} quarantined decisions",
             f"  not decided again, because no answer was recorded (model error or budget): {result['no_answer']}",
             f"  rows checked against the committed list: {result['rows_listed']} of {result['listed']}"]
    lines += [f"  failed as {kind}: {n}" for kind, n in result["failures"].items()]
    return "\n".join(lines)
