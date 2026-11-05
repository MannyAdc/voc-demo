"""B17 and spec 004's J1: check that a run log only grows. CI runs it on every push and pull request, on
`runs/TEST_RUNS.md` and on `runs/JUNE_RUNS.md`.

Usage: python scripts/check_test_runs.py <log on main> <log here>

It passes when the log on main is missing, or when the log here starts with every line of the log on main.
It fails when a line was changed or removed, or when the log was deleted.
"""
import sys
from pathlib import Path


def main(argv):
    base, head = Path(argv[0]), Path(argv[1])
    if not base.exists():
        print(f"{head.name}: nothing on main yet, so nothing can have been removed")
        return 0
    if not head.exists():
        print(f"{head.name}: the log on main was deleted here")
        return 1
    old = base.read_text(encoding="utf-8").splitlines()
    new = head.read_text(encoding="utf-8").splitlines()
    if new[:len(old)] != old:
        print(f"{head.name}: a line on main was changed or removed here. Rows are only ever added")
        return 1
    print(f"{head.name}: {len(new) - len(old)} lines added, none changed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
