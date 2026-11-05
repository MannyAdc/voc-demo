"""Spec 004, pull request 5a: make the spike's zip from the synthetic dbt fixture, and print its name, size and
SHA-256. The zip holds that fixture only, as `spike_complaints.csv`, with a fixed date, so it is the same every time.

Usage: python scripts/make_spike_zip.py <folder>
"""
import hashlib
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"
NAME, MEMBER = "spike.zip", "spike_complaints.csv"


def main(argv):
    if len(argv) != 1:
        print("usage: python scripts/make_spike_zip.py <folder>")
        return 2
    folder = Path(argv[0])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / NAME
    info = zipfile.ZipInfo(MEMBER, date_time=(2026, 11, 5, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, FIXTURE.read_bytes())
    print(f"{NAME}  {path.stat().st_size} bytes  sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
