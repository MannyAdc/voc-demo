"""Spec 004, pull request 5a: the spike's logic, on synthetic rows. The dbt task also builds the committed test list
seed, the July test list's complaint IDs and content hashes, as Job A will, and no complaint text.

The spike's job (`cloud/spike/job_spike.json`) runs three tasks, `unpack`, `dbt` and `job_a`, as Job A will, to
answer the open points before the real Job A is built (5b). `unpack` takes the one zip from the scratch folder,
writes its one CSV to the spike folder and hands dbt its variables as task values. It refuses anything but one zip
holding one flat CSV, and any row whose complaint ID is not synthetic (`SYN-`). `job_a` returns counts only.
"""
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from voc.labels import load_labels

CONTRACT = "voc-june-spike"
MAX_BYTES = 5 * 1024 * 1024  # the synthetic fixture is far smaller
SYNTHETIC = "SYN-"


class SpikeError(ValueError):
    """A refusal whose message holds only fixed text and counts."""


def _one_zip(folder):
    files = sorted(p for p in Path(folder).iterdir() if p.is_file())
    if len(files) != 1 or files[0].suffix.lower() != ".zip":
        raise SpikeError(f"the scratch folder must hold exactly one zip and nothing else, it holds {len(files)} files")
    return files[0]


def _one_csv(archive):
    names = archive.namelist()
    if len(names) != 1 or "/" in names[0] or "\\" in names[0] or not names[0].lower().endswith(".csv"):
        raise SpikeError(f"the zip must hold exactly one CSV at its top, it holds {len(names)} entries")
    return names[0]


def unpack(incoming, out, labels_file):
    """Writes the zip's one CSV to `out` and returns dbt's variables, all as strings, for the task values."""
    path = _one_zip(incoming)
    with zipfile.ZipFile(path) as archive:
        name = _one_csv(archive)
        if archive.getinfo(name).file_size > MAX_BYTES:
            raise SpikeError(f"the CSV is over the spike's size cap of {MAX_BYTES} bytes")
        data = archive.read(name)
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
    if not rows or any(not (row.get("Complaint ID") or "").startswith(SYNTHETIC) for row in rows):
        raise SpikeError("the spike takes synthetic rows only, and every complaint ID must start with SYN-")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / name
    target.write_bytes(data)
    labels = [label.name for label in load_labels(labels_file)]
    return {"month_file": str(target), "month_sha256": hashlib.sha256(data).hexdigest(), "month_rows": str(len(rows)),
            "labels": json.dumps(labels)}


def exit_value(landed_rows, staged_rows):
    return json.dumps({"contract": CONTRACT, "landed_rows": int(landed_rows), "staged_rows": int(staged_rows)},
                      sort_keys=True, separators=(",", ":"))
