"""V8: the review folder, where the owner's review sheets live (specs/003-validation-review/spec.md).

A sheet holds complaint text, so it is written only inside the review folder in the home folder's `.voc`,
which the read guard blocks for Claude. Each sheet has one fixed path. Errors name no path.

V2 and V3: the owner runs `voc review sheet` to write a sheet and `voc review import` to read the codes back.
The import reads only the ID and code columns. What is committed holds IDs, reasons and codes only (V8).
"""
import csv
import io
import json
import os
from pathlib import Path

from voc import budget

REPO_ROOT = Path(__file__).resolve().parents[2]
SHEETS = {"v2": "v2_sheet.csv", "v3": "v3_sheet.csv", "v5": "v5_sheet.csv"}
CODES = {"v2": ("llm_right", "consumer_right", "both_plausible", "unclear"),
         "v3": ("check_right", "check_wrong", "unclear")}
SHEET_FIELDS = {"v2": ("complaint_id", "consumer_choice", "llm_label", "llm_quote", "complaint_text", "code"),
                "v3": ("complaint_id", "reason", "proposed_label", "proposed_quote", "complaint_text", "code")}
NO_ANSWER = "(no label or quote could be read)"


class ReviewError(ValueError):
    """An error whose message is ours, so it is safe to print (it never holds a path or data)."""


def review_dir():
    """The review folder, next to the ledger and the recordings in the home folder."""
    return budget.voc_home() / "review"


def inside_review_dir(path):
    """The resolved path, if it is inside the review folder. Anything else is refused.

    Links are followed first, so a link inside the folder that points outside is refused. A review folder
    that itself leads into the repo is refused too, because a sheet there could be committed.
    """
    folder = review_dir().resolve()
    if folder.is_relative_to(REPO_ROOT.resolve()):
        raise ReviewError("the review folder must not be inside the repo")
    resolved = Path(path).resolve()
    if resolved == folder or not resolved.is_relative_to(folder):
        raise ReviewError("a review sheet must be inside the review folder")
    return resolved


def sheet_path(piece):
    """The one path of a piece's sheet, after the folder check. Only V2, V3 and V5 have a sheet."""
    if piece not in SHEETS:
        raise ReviewError("there is a review sheet only for v2, v3 and v5")
    path = review_dir() / SHEETS[piece]
    inside_review_dir(path)
    return path


def codes_path(root, piece):
    return Path(root) / "results" / "validation" / f"{piece}_codes.csv"


def _check_piece(piece):
    if piece not in CODES:
        raise ReviewError("the sheet and import commands cover v2 and v3")


def _recorded(root):
    from voc.consistency import _old

    return _old(root)


def _ids(root, piece, recorded):
    """V2's frozen list, or every quarantined development complaint for V3 (V7)."""
    from voc.validation import read_lists

    if piece == "v2":
        return read_lists(Path(root) / "splits")["v2"]
    read_lists(Path(root) / "splits")  # checks the labels file the quarantines come from
    from voc.pipeline import _id_number

    return sorted((c for c, r in recorded.items() if r["decision"] == "quarantined"), key=_id_number)


def _staged(root, ids):
    """The rows of these development IDs from the staged table, checked against the development list."""
    from voc.data import _manifest, verify_ids
    from voc.load import DB_PATH
    from voc.pipeline import _rows_by_id

    splits = Path(root) / "splits"
    rows = _rows_by_id(Path(root) / DB_PATH, _manifest(splits)["month"], set(ids))
    if {r.complaint_id for r in rows} != set(ids):
        raise ReviewError(f"{len(set(ids) - {r.complaint_id for r in rows})} complaints are missing from the "
                          "staged table")
    verify_ids(splits, "dev", rows)
    return {r.complaint_id: r for r in rows}


def _proposed_answer(root, row):
    """The proposed label and quote of a quarantined answer, from its recording, for the owner's sheet only."""
    from voc.labels import load_labels
    from voc.prompt import parse_answer
    from voc.replay import recordings_dir

    if row["reason"] == "unparseable":
        return NO_ANSWER, NO_ANSWER
    key = row["recording_key"]
    path = recordings_dir() / f"{key}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        text = record["text"] if record["key"] == key else None
    except (OSError, ValueError, KeyError, TypeError):
        text = None
    if not isinstance(text, str):
        raise ReviewError("a recorded answer of a quarantined complaint is missing or cannot be read")
    parsed = parse_answer(text, [label.name for label in load_labels(Path(root) / "config" / "labels.toml")])
    return parsed.label or "", parsed.quote or ""


def sheet_rows(root, piece):
    """The sheet's rows. They hold complaint text, so only the owner's sheet ever gets them."""
    from voc.baselines import cut_text

    _check_piece(piece)
    recorded = _recorded(root)
    ids = _ids(root, piece, recorded)
    staged = _staged(root, ids)
    rows = []
    for complaint_id in ids:
        old, text = recorded[complaint_id], cut_text(staged[complaint_id].narrative)[0]
        if piece == "v2":
            start, end = int(old["quote_start"]), int(old["quote_end"])
            rows.append({"complaint_id": complaint_id, "consumer_choice": staged[complaint_id].product,
                         "llm_label": old["accepted_label"], "llm_quote": text[start:end], "complaint_text": text,
                         "code": ""})
        else:
            label, quote = _proposed_answer(root, old)
            rows.append({"complaint_id": complaint_id, "reason": old["reason"], "proposed_label": label,
                         "proposed_quote": quote, "complaint_text": text, "code": ""})
    return rows


def _write_atomic(path, data, encoding):
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_bytes(data.encode(encoding))
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def write_sheet(root, piece):
    """Write the owner's sheet once. A sheet that exists is never written over, so no marks are lost."""
    path = sheet_path(piece)
    if path.exists():
        raise ReviewError(f"the {piece} sheet already exists. Its marks are kept. Move it away to write a new one")
    rows = sheet_rows(root, piece)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=SHEET_FIELDS[piece], lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, out.getvalue(), "utf-8-sig")  # with the mark spreadsheets need to read it as UTF-8
    return {"piece": piece, "complaints": len(rows), "path": path, "codes": CODES[piece]}


def _sheet_text(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")  # a spreadsheet that saved it in the Windows code page


def read_codes(root, piece):
    """The owner's codes by ID, from the ID and code columns only. Refused unless every listed ID appears exactly
    once with a code from the list. The refusal names IDs and counts only."""
    _check_piece(piece)
    path = sheet_path(piece)
    if not path.exists():
        raise ReviewError(f"there is no {piece} sheet. Write it with `voc review sheet {piece}` first")
    reader = csv.DictReader(io.StringIO(_sheet_text(path)))
    if not {"complaint_id", "code"} <= set(reader.fieldnames or []):
        raise ReviewError(f"the {piece} sheet has no complaint_id or code column")
    wanted = _ids(root, piece, _recorded(root))
    codes, problems = {}, []
    for row in reader:
        complaint_id, code = (row["complaint_id"] or "").strip(), (row["code"] or "").strip()
        if complaint_id not in wanted:
            problems.append(f"{complaint_id or '(blank)'} is not on the {piece} list")
        elif complaint_id in codes:
            problems.append(f"{complaint_id} appears more than once")
        elif not code:
            problems.append(f"{complaint_id} has no code")
        elif code not in CODES[piece]:
            problems.append(f"{complaint_id} has a code that is not one of {', '.join(CODES[piece])}")
        codes.setdefault(complaint_id, code)
    missing = [c for c in wanted if c not in codes]
    if missing:
        problems.append(f"{len(missing)} listed complaints are missing: {', '.join(missing)}")
    if problems:
        raise ReviewError("the sheet is refused and nothing is written: " + ". ".join(problems))
    return {c: codes[c] for c in wanted}


def summarise_codes(piece, codes):
    """Each code's count and share with its Wilson interval. For V2, the label noise as a lower figure
    (`llm_right`) and an upper one (`llm_right` and `both_plausible`)."""
    from voc.consistency import wilson

    n = len(codes)
    if not n:
        raise ReviewError("there are no codes to summarise")

    def share(k):
        low, high = wilson(k, n)
        return {"count": k, "share": k / n, "interval": [low, high]}

    counts = {code: sum(c == code for c in codes.values()) for code in CODES[piece]}
    summary = {"piece": piece, "cases": n, "codes": {code: share(k) for code, k in counts.items()}}
    if piece == "v2":
        summary["label_noise"] = {"lower": share(counts["llm_right"]),
                                  "upper": share(counts["llm_right"] + counts["both_plausible"])}
    return summary


def import_codes(root, piece, replace=False):
    """Read the owner's codes and write them, with V3's reasons, to the results. Returns the summary."""
    codes = read_codes(root, piece)
    path = codes_path(root, piece)
    if path.exists() and not replace:
        raise ReviewError(f"{piece}_codes.csv already exists. Use --replace to import the sheet again")
    fields = ["complaint_id", "code"] if piece == "v2" else ["complaint_id", "reason", "code"]
    recorded = _recorded(root) if piece == "v3" else {}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for complaint_id, code in codes.items():
        row = {"complaint_id": complaint_id, "code": code}
        if piece == "v3":
            row["reason"] = recorded[complaint_id]["reason"]
        writer.writerow(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, out.getvalue(), "utf-8")
    return summarise_codes(piece, codes)


def format_sheet(result):
    return [f"{result['piece']} sheet: {result['complaints']} complaints",
            f"written to {result['path']}",
            f"fill the code column with one of: {', '.join(result['codes'])}",
            f"then run `voc review import {result['piece']}`"]


def format_codes(summary, root):
    lines = [f"{summary['piece']}: {summary['cases']} cases"]
    for code, figure in summary["codes"].items():
        low, high = figure["interval"]
        lines.append(f"{code}: {figure['count']} ({figure['share']:.1%}, 95% interval {low:.1%} to {high:.1%})")
    for bound, figure in summary.get("label_noise", {}).items():
        low, high = figure["interval"]
        lines.append(f"label noise, {bound} figure: {figure['count']} ({figure['share']:.1%}, 95% interval "
                     f"{low:.1%} to {high:.1%})")
    if summary["cases"] < 30:
        lines.append(f"only {summary['cases']} cases, so every share is uncertain")
    lines.append(f"written to {codes_path(root, summary['piece']).relative_to(Path(root)).as_posix()}")
    return lines
