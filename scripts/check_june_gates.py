"""Spec 004, J1 (owner decisions, 6 November): a new real row of `runs/JUNE_RUNS.md` needs open passes of both
gates already on `main`, so a pass cannot be added with the row and given an earlier date. CI runs it on every push
and pull request.

Usage: python scripts/check_june_gates.py <gates log on main> <run log on main> <run log here> <data_files.toml>

A missing log on main counts as empty. It prints the result in one line, with no hash but the rule's. It finds the
new rows by count, so it relies on the step before it in the same CI job, which checks the run log only grows.
"""
import sys
import tomllib
from pathlib import Path

from voc.frozen import JuneRunsError, check_gates, read_gates, read_runs


def main(argv):
    main_gates, main_runs, head_runs, data_files = (Path(a) for a in argv)
    base = read_runs(main_runs) if main_runs.is_file() else []
    new = [e for e in read_runs(head_runs)[len(base):] if e.kind == "real"]
    if not new:
        print("no new real row in the June run log")
        return 0
    with open(data_files, "rb") as f:
        pin = tomllib.load(f)["june_2026"]["sha256"]
    try:
        check_gates(new, read_gates(main_gates), pin)
        error = None
    except JuneRunsError as err:
        error = str(err)
    if error:
        print(f"refused: {error}. The gate passes must be on main before the real row is added")
        return 1
    print(f"{len(new)} new real row, with both gates' passes on main")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
