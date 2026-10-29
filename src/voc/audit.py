"""B1, B19: re-check every accepted label from the committed results file and the recorded answers.

This is a second check of the quote check, made after the run. For each accepted complaint it:

1. rebuilds the exact prompt from the staged text, checked against the committed list (B16),
2. checks that the prompt's recording key is the key in the results file, so the answer is for this text,
3. loads the recorded answer, whose key material must match (B7),
4. checks that the answer's label is the accepted label,
5. checks that the answer's quote is found in the text (B1) at the stored start and end.

It calls no model and prints counts only, never text (B21).
"""
import csv
import io
import json
from collections import Counter
from pathlib import Path

from voc.baselines import cut_text
from voc.evidence import check_quote
from voc.labels import load_labels
from voc.load import DB_PATH
from voc.pipeline import definitions, load_complaints, load_prompt_version
from voc.prompt import build_prompt, parse_answer
from voc.replay import Caller, RecordingCorrupt, _key_material, recording_key

FAILURES = ("not_in_list", "key_differs", "recording_missing", "recording_invalid", "label_differs",
            "quote_not_found", "position_differs")


class AuditError(ValueError):
    pass


def audit(root, set_name, version_name):
    """Counts of accepted labels re-verified, and of each kind of failure."""
    root = Path(root)
    folder = root / "results" / "labels"
    summary_path, results_path = folder / f"{version_name}_{set_name}.json", folder / f"{version_name}_{set_name}.csv"
    if not summary_path.exists() or not results_path.exists():
        raise AuditError(f"no finished run of prompt {version_name} on the {set_name} set to audit")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
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
    accepted = [r for r in rows if r["decision"] == "accepted"]
    failures, verified, word_for_word = Counter(), 0, 0
    for row in accepted:
        complaint = complaints.get(row["complaint_id"])
        if complaint is None:
            failures["not_in_list"] += 1
            continue
        text, _ = cut_text(complaint.narrative)
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
        parsed = parse_answer(record["text"], names)
        if parsed.reason is not None or parsed.label != row["accepted_label"]:
            failures["label_differs"] += 1
            continue
        evidence = check_quote(text, parsed.quote)
        if not evidence.ok:
            failures["quote_not_found"] += 1
            continue
        if (evidence.start, evidence.end) != (int(row["quote_start"]), int(row["quote_end"])):
            failures["position_differs"] += 1
            continue
        verified += 1
        word_for_word += text[evidence.start:evidence.end] == parsed.quote
    return {"set": set_name, "prompt_version": version_name, "accepted": len(accepted), "verified": verified,
            "word_for_word": word_for_word, "failures": {k: failures[k] for k in FAILURES if failures[k]}}


def format_audit(result):
    lines = [f"audited prompt {result['prompt_version']} on {result['set']}: re-verified {result['verified']} of "
             f"{result['accepted']} accepted labels",
             f"  word for word at the stored position: {result['word_for_word']}",
             f"  after the quote check's small normalisation (spaces, quote marks, dashes): "
             f"{result['verified'] - result['word_for_word']}"]
    lines += [f"  failed as {kind}: {n}" for kind, n in result["failures"].items()]
    return "\n".join(lines)
