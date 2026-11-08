"""Spec 004, pull request 9a: the dry run's files, built from its synthetic CSV for one round (owner decision,
8 November: a re-run after a code fix is a new round, with new synthetic IDs, a new list and a new row).

Usage:
    python scripts/make_dry_run.py --round 1 <folder>   writes the zip to <folder>, outside the repo, for the upload
    python scripts/make_dry_run.py --round 1 --repo     writes the committed list, its manifest, the pin and the
                                                         mock answers

The zip is the same bytes on every platform: stored with no compression, a fixed date, and fixed fields for the system
that made it and the file's mode, so CI can rebuild it and compare it with the pin. The CSV, the list and the answers
are synthetic, with `SYN-` IDs only. It prints names, sizes and SHA-256s only (J5).
"""
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

LISTED = 8
DATE = (2026, 6, 30, 0, 0, 0)
UNIX = 3
MODE = 0o100644 << 16
PREFIX = "Synthetic text: "


def csv_path(root, round_number):
    return Path(root) / "tests" / "fixtures" / "june_dry_run" / f"syn_june_dry_run_r{round_number}.csv"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def zip_bytes(member, data):
    """The zip, the same bytes on every platform."""
    info = zipfile.ZipInfo(member, date_time=DATE)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = UNIX
    info.external_attr = MODE
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(info, data)
    return out.getvalue()


def _records(data):
    from voc.repo_checks import CFPB_COLUMNS

    records = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
    if records[0] != list(CFPB_COLUMNS):
        raise ValueError("the dry run's CSV does not have the CFPB header")
    return records[1:]


def _quote(narrative):
    """The first sentence after the synthetic prefix, as the mock model quotes it."""
    text = narrative[len(PREFIX):] if narrative.startswith(PREFIX) else narrative
    return re.split(r"(?<=\.)\s", text, maxsplit=1)[0]


def build(root, round_number):
    """Every file of the round, as bytes or values. Nothing is written."""
    from voc import pipeline
    from voc.baselines import cut_text
    from voc.data import content_hash
    from voc.job_a import COMPLAINT_ID, NARRATIVE, PRODUCT, has_text
    from voc.labels import load_labels
    from voc.prompt import build_prompt

    root = Path(root)
    data = csv_path(root, round_number).read_bytes()
    records = _records(data)
    stem = f"syn_june_dry_run_r{round_number}"
    archive = zip_bytes(f"{stem}.csv", data)
    pin = {"file_name": f"{stem}.csv", "size_bytes": len(data), "sha256": _sha256(data), "rows": len(records),
           "narratives": sum(has_text(r[NARRATIVE]) for r in records), "zip_file_name": f"{stem}.zip",
           "zip_size_bytes": len(archive), "zip_sha256": _sha256(archive)}
    with_text = sorted((r for r in records if has_text(r[NARRATIVE])), key=lambda r: int(r[COMPLAINT_ID][4:]))
    listed = with_text[:LISTED]
    listing = ("complaint_id,content_hash\n" + "".join(
        f"{r[COMPLAINT_ID]},{content_hash(r[NARRATIVE], r[PRODUCT])}\n" for r in listed)).encode("utf-8")
    manifest = {"lists": {"june_dry": {"count": len(listed), "round": round_number, "sha256": _sha256(listing)}}}
    version = pipeline.load_prompt_version(root, "v1")
    labels = load_labels(root / "config" / "labels.toml")
    names, defined = [label.name for label in labels], pipeline.definitions(labels)
    answers = []
    for n, r in enumerate(listed):
        prompt = build_prompt(version.instructions, names, cut_text(r[NARRATIVE])[0], complaint_id=r[COMPLAINT_ID],
                              definitions=defined).prompt
        # The last listed complaint's answer quotes a sentence its text does not hold, so the dry run also shows
        # the quarantine path.
        quote = "this sentence is not in the complaint at all" if n == len(listed) - 1 else _quote(r[NARRATIVE])
        answers.append({"prompt": prompt, "text": json.dumps({"label": r[PRODUCT], "quote": quote})})
    return {"csv": data, "zip": archive, "pin": pin, "list": listing, "manifest": manifest, "answers": answers,
            "round": round_number}


def pin_text(files):
    pin = files["pin"]
    lines = ["# Spec 004, pull request 9a: the pin of the dry run's synthetic zip and CSV, made by",
             "# scripts/make_dry_run.py. Job A takes it for a synthetic row (J8, J16). Never the June pin.",
             f"round = {files['round']}", "", "[june_dry_run]"]
    for key in ("file_name", "size_bytes", "sha256", "rows", "narratives", "zip_file_name", "zip_size_bytes",
                "zip_sha256"):
        value = pin[key]
        lines.append(f"{key} = {json.dumps(value) if isinstance(value, str) else value}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def repo_files(files):
    """The committed files of the round, by path from the repo's root."""
    return {"config/june_dry_run.toml": pin_text(files),
            "splits/june_dry/june_dry.csv": files["list"],
            "splits/june_dry/manifest.json": (json.dumps(files["manifest"], indent=2, sort_keys=True) + "\n").encode(),
            "cloud/job_b/dry_run_answers.json": (json.dumps(files["answers"], indent=1, sort_keys=True) + "\n").encode()}


def main(argv):
    if len(argv) != 3 or argv[0] != "--round" or not re.fullmatch(r"[1-9]", argv[1]):
        print("usage: python scripts/make_dry_run.py --round <1 to 9> <folder> | --repo")
        return 2
    files = build(REPO, int(argv[1]))
    if argv[2] == "--repo":
        for name, data in repo_files(files).items():
            path = REPO / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"{name}  {len(data)} bytes  sha256 {_sha256(data)}")
        return 0
    folder = Path(argv[2]).resolve()
    if folder == REPO or REPO in folder.parents:
        print("refused: write the zip to a folder outside the repo")
        return 2
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / files["pin"]["zip_file_name"]
    path.write_bytes(files["zip"])
    print(f"{path.name}  {len(files['zip'])} bytes  sha256 {_sha256(files['zip'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
