"""Spec 004, J5 and J13: the failing-row check in Databricks, a gate before the June upload (owner decision,
6 November). Its job, `cloud/failcheck.yml`, runs Job A's own dbt command on synthetic rows with one row that
makes Spark's FAILFAST parser fail, whose error can quote the row. Then it runs the same command without the quiet
flags, as a control. The owner reads every task's output as the robot (`cloud/failcheck/robot_check.py`). The marker
must be nowhere in the quiet run's output and somewhere in the control's, which shows the check can see a leak.

Job A's `unpack` would refuse the short row before dbt, so this job writes its rows itself, to reach dbt.
"""
import csv
import hashlib
import io
from pathlib import Path

from voc.job_a import VOLUME, labels_value
from voc.repo_checks import CFPB_COLUMNS

MARKER = "SYNFAILCHECKMARKER"
FOLDER = VOLUME + "/failcheck"
FILE_NAME = "failcheck.csv"


def _row(complaint_id, narrative, text=None):
    """One row. With `text`, it fills every free-text field, so a shortened error still shows it first."""
    return ["2026-06-01", "Mortgage", text or "Conventional home mortgage", text or "Trouble during payment process",
            text or "", narrative, text or "", text or "Synthetic Company", "NY", "10001", "", "Web", "2026-06-02",
            "Closed with explanation", "Yes", complaint_id]


def rows_text():
    """The CFPB header, two well-formed synthetic rows, and a last row one field short, with the marker at the
    start of its narrative and of its other free-text fields (review of the fix round, minor 4)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CFPB_COLUMNS)
    writer.writerow(_row("SYN-F1", "Synthetic text: my payment was applied late."))
    writer.writerow(_row("SYN-F2", "Synthetic text: a fee I did not expect."))
    writer.writerow(_row("SYN-F3", f"{MARKER} synthetic text that must never reach the robot",
                         text=f"{MARKER} synthetic text")[:-1])
    return buffer.getvalue()


def write_rows(folder, labels_file):
    """Writes the rows to `folder` and returns dbt's variables as strings, as Job A's `unpack` does."""
    data = rows_text().encode("utf-8")
    path = Path(folder) / FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"month_file": str(path), "month_sha256": hashlib.sha256(data).hexdigest(), "month_rows": "3",
            "labels": labels_value(labels_file)}
