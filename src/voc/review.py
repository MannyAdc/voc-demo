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
import re
from pathlib import Path

from voc import budget

REPO_ROOT = Path(__file__).resolve().parents[2]
# `v5_dry_run` holds the judge's dry run ratings and reasons, read from the recordings, for the owner only.
SHEETS = {"v2": "v2_sheet.csv", "v3": "v3_sheet.csv", "v5": "v5_sheet.csv", "v5_dry_run": "v5_dry_run_reasons.csv"}
CODES = {"v2": ("llm_right", "consumer_right", "both_plausible", "unclear"),
         "v3": ("check_right", "check_wrong", "unclear"),
         "v5": ("supports", "partly", "does_not_support")}
# V5's sheet is blind: no judge rating and no consumer's product (V5, V8).
SHEET_FIELDS = {"v2": ("complaint_id", "consumer_choice", "llm_label", "llm_quote", "complaint_text", "code"),
                "v3": ("complaint_id", "reason", "proposed_label", "proposed_quote", "complaint_text", "code"),
                "v5": ("complaint_id", "llm_label", "label_covers", "llm_quote", "complaint_text", "code"),
                "v5_dry_run": ("complaint_id", "rating", "reason", "llm_label", "llm_quote", "complaint_text")}
NO_ANSWER = "(no label or quote could be read)"
# V5: the judge's question and ratings, as `config/prompts/judge_v1.toml` words them, printed with the owner's
# sheet. The first sheet gave neither, so its ratings answered another question and were withdrawn (BUILD_LOG.md).
V5_QUESTION = (
    "the question, as the judge was asked it: does the quote, on its own, support the label?",
    "supports: the quote on its own makes clear that the complaint is about this product",
    "partly: the quote is about the product's area but does not on its own make this product clear, or it fits "
    "other products just as well",
    "does_not_support: the quote does not point to this product",
    "use the complaint only to understand the quote, and do not judge whether another label would be better",
    "label_covers says what the label covers, as the judge was told")
NO_CALL = "(no call was made, so there is no answer)"
# The quarantine reasons decided with no model call, so with no recording.
NO_CALL_REASONS = ("no_narrative", "not_run_budget")
KEY = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^(?:\d{1,12}|SYN-\d{1,12})$")
# A spreadsheet runs a cell that starts with one of these as a formula.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n")


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


def _check_piece(piece, sheet=False):
    if piece not in (SHEET_FIELDS if sheet else CODES):
        raise ReviewError("the sheet command covers v2, v3, v5 and v5_dry_run, and the import v2, v3 and v5")


def _recorded(root):
    from voc.consistency import _old

    return _old(root)


def _ids(root, piece, recorded):
    """V2's or V5's frozen list, or every quarantined development complaint for V3 (V7)."""
    from voc.validation import read_lists

    if piece in ("v2", "v5"):
        return read_lists(Path(root) / "splits")[piece]
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
    """The proposed label and quote of a quarantined answer, from its recording, for the owner's sheet only.

    A quarantine decided with no call has no answer. An unparseable answer, or a model error with no usable
    answer, has none that can be read. Each says so on the sheet instead of stopping it.
    """
    from voc.labels import load_labels
    from voc.prompt import parse_answer
    from voc.replay import recordings_dir

    key = row["recording_key"]
    if row["reason"] in NO_CALL_REASONS or row["reason"].startswith("boundary") or not key:
        return NO_CALL, NO_CALL
    if not KEY.match(key):
        raise ReviewError(f"{row['complaint_id']} has a recording key that is not a SHA-256 hash")
    if row["reason"] == "unparseable":
        return NO_ANSWER, NO_ANSWER
    try:
        record = json.loads((recordings_dir() / f"{key}.json").read_text(encoding="utf-8"))
        text = record["text"] if record["key"] == key else None
    except (OSError, ValueError, KeyError, TypeError):
        text = None
    if not isinstance(text, str):
        if row["reason"] == "model_error":
            return NO_ANSWER, NO_ANSWER
        raise ReviewError(f"the recorded answer of {row['complaint_id']} is missing or cannot be read")
    parsed = parse_answer(text, [label.name for label in load_labels(Path(root) / "config" / "labels.toml")])
    if not parsed.label and not parsed.quote:
        return NO_ANSWER, NO_ANSWER
    return parsed.label or "", parsed.quote or ""


def _dry_run_rows(root):
    """The judge's dry run ratings and reasons, from its recordings, with each case's label, quote and text."""
    from voc import judge
    from voc.replay import recordings_dir

    summary_path = judge.result_paths(root)["dry_run"]
    if not summary_path.exists():
        raise ReviewError("the judge's dry run has not been run")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    keys = summary.get("keys", {})
    rows = []
    for case in judge.items(root, "dry_run", judge.load_judge(root, summary["judge"])):
        key = keys.get(case.complaint_id, "")
        if not KEY.match(key):
            raise ReviewError(f"{case.complaint_id} has no recording key in the dry run's summary")
        try:
            record = json.loads((recordings_dir() / f"{key}.json").read_text(encoding="utf-8"))
            text = record["text"] if record["key"] == key else None
        except (OSError, ValueError, KeyError, TypeError):
            text = None
        rating, reason = judge.parse_rating(text) if isinstance(text, str) else ("(no recording)", "")
        rows.append({"complaint_id": case.complaint_id, "rating": rating, "reason": reason, "llm_label": case.label,
                     "llm_quote": case.quote, "complaint_text": case.text})
    return rows


def sheet_rows(root, piece):
    """The sheet's rows. They hold complaint text, so only the owner's sheet ever gets them."""
    from voc.baselines import cut_text

    _check_piece(piece, sheet=True)
    if piece == "v5_dry_run":
        return _dry_run_rows(root)
    if piece == "v5":
        from voc.labels import load_labels
        from voc.pipeline import definitions

        defined = definitions(load_labels(Path(root) / "config" / "labels.toml"))
    recorded = _recorded(root)
    ids = _ids(root, piece, recorded)
    staged = _staged(root, ids)
    rows = []
    for complaint_id in ids:
        old, text = recorded[complaint_id], cut_text(staged[complaint_id].narrative)[0]
        if piece in ("v2", "v5"):
            start, end = int(old["quote_start"]), int(old["quote_end"])
            row = {"complaint_id": complaint_id, "llm_label": old["accepted_label"], "llm_quote": text[start:end],
                   "complaint_text": text, "code": ""}
            if piece == "v2":
                row["consumer_choice"] = staged[complaint_id].product
            else:
                row["label_covers"] = defined[old["accepted_label"]]
            rows.append(row)
        else:
            label, quote = _proposed_answer(root, old)
            rows.append({"complaint_id": complaint_id, "reason": old["reason"], "proposed_label": label,
                         "proposed_quote": quote, "complaint_text": text, "code": ""})
    return rows


def safe_cell(value):
    """A cell as the owner's spreadsheet should show it: text that starts like a formula gets a leading
    apostrophe, so it is shown, never run. Only the text columns, which the import never reads, go through it."""
    return "'" + value if isinstance(value, str) and value.startswith(FORMULA_START) else value


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
    for row in rows:
        writer.writerow({key: value if key in ("complaint_id", "code", "rating") else safe_cell(value)
                         for key, value in row.items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, out.getvalue(), "utf-8-sig")  # with the mark spreadsheets need to read it as UTF-8
    return {"piece": piece, "complaints": len(rows), "path": path, "codes": CODES.get(piece, ())}


def _sheet_text(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # A spreadsheet that saved it in the Windows code page. Only the ID and code columns are read, and they
        # are plain ASCII, so a byte the code page does not define is replaced, never a reason to stop.
        return data.decode("cp1252", errors="replace")


def _shown(value, number):
    """A value from the sheet for a refusal: the value if it looks like a complaint ID, else its row number (B21)."""
    return value if ID.match(value) else f"the value on row {number}"


def read_codes(root, piece):
    """The owner's codes by ID, from the ID and code columns only. Refused unless every listed ID appears exactly
    once with a code from the list. The refusal names IDs and counts only."""
    _check_piece(piece)
    path = sheet_path(piece)
    if not path.exists():
        raise ReviewError(f"there is no {piece} sheet. Write it with `voc review sheet {piece}` first")
    reader = csv.reader(io.StringIO(_sheet_text(path)))
    header = [name.strip().lower() for name in next(reader, [])]
    if not {"complaint_id", "code"} <= set(header):
        hint = " It looks saved with semicolons: save it as comma-separated CSV" if ";" in "".join(header) else ""
        raise ReviewError(f"the {piece} sheet has no complaint_id or code column.{hint}")
    if piece == "v5" and "label_covers" not in header:
        # Only the redo's sheet has it, so the withdrawn first sheet can never be imported as the redo.
        raise ReviewError("the v5 sheet has no label_covers column, so it is not the redo's sheet. Move the old "
                          "sheet away and write a new one with `voc review sheet v5`")
    at_id, at_code = header.index("complaint_id"), header.index("code")
    wanted = _ids(root, piece, _recorded(root))
    codes, problems = {}, []
    for number, cells in enumerate(reader, start=2):  # the header is row 1, as the spreadsheet shows it
        if not any(cell.strip() for cell in cells):
            continue  # a row a spreadsheet left empty
        complaint_id = cells[at_id].strip() if at_id < len(cells) else ""
        code = cells[at_code].strip() if at_code < len(cells) else ""
        if complaint_id not in wanted:
            problems.append(f"{_shown(complaint_id, number) if complaint_id else f'row {number}'} is not on the "
                            f"{piece} list")
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
    judged = [Path(root) / "results" / "validation" / name for name in ("v5_judge.csv", "v5_judge.json")]
    if piece == "v5" and any(path.exists() for path in judged) and codes_path(root, "v5").exists():
        # The one redo (spec 003): the first ratings were withdrawn, so the redo may come after the judge's run.
        raise ReviewError("the judge's main run has already rated these, and the owner's V5 ratings are imported, "
                          "so they stay as they are (V5 is blind)")
    codes = read_codes(root, piece)
    path = codes_path(root, piece)
    if path.exists() and not replace:
        raise ReviewError(f"{piece}_codes.csv already exists. Use --replace to import the sheet again")
    fields = ["complaint_id", "reason", "code"] if piece == "v3" else ["complaint_id", "code"]
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
    summary = summarise_codes(piece, codes)
    if piece == "v3":
        summary["list"] = [{"complaint_id": c, "reason": recorded[c]["reason"], "code": code}
                           for c, code in codes.items()]
    return summary


def _home_relative(path):
    """The path with the home folder written as `~`, so a printout does not show the login name."""
    try:
        return "~/" + Path(path).relative_to(Path.home()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def format_sheet(result):
    if not result["codes"]:  # the dry run's ratings and reasons, to read only
        return [f"{result['piece']} sheet: {result['complaints']} complaints",
                f"written to {_home_relative(result['path'])}", "it is for reading only and has no import"]
    question = list(V5_QUESTION) if result["piece"] == "v5" else []
    return [f"{result['piece']} sheet: {result['complaints']} complaints",
            f"written to {_home_relative(result['path'])}", *question,
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
    for entry in summary.get("list", []):
        lines.append(f"{entry['complaint_id']}: {entry['reason']}, {entry['code']}")
    if summary["cases"] < 30:
        lines.append(f"only {summary['cases']} cases, so every share is uncertain")
    lines.append(f"written to {codes_path(root, summary['piece']).relative_to(Path(root)).as_posix()}")
    return lines
