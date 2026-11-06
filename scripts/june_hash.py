"""Spec 004, J1: print the June list's hash and the frozen code's hash, for an entry in runs/JUNE_RUNS.md.

Usage: python scripts/june_hash.py [root]

Run it from a clean checkout of the commit to be frozen. It refuses when the frozen files on disk differ from the
files git tracks, in name or in content, naming only their number. It prints two hashes and a file count,
nothing else. Where git is missing, it says so on stderr and hashes the files as they are.

It also refuses unless `runs/JUNE_GATES.md` holds an open pass of both gates, `june-check` and `failcheck`, for
this code and the June pin (owner decisions, 6 November). It has no way round that. The dry run's own path comes
with its own list, in pull request 9.
"""
import sys
from pathlib import Path

from voc.datafile import load_pins
from voc.frozen import GATES, changed_frozen, code_hash, frozen_files, list_hash, missing_gates, read_gates


def main(argv):
    if len(argv) > 1 or (argv and argv[0].startswith("-")):
        print("refused: the only argument is the checkout's folder")
        return 1
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    differ = changed_frozen(root)
    if differ is None:
        print("no git checkout here, so the frozen files were not compared with the tracked ones", file=sys.stderr)
    elif differ:
        print(f"refused: {len(differ)} frozen files differ from the files git tracks. Commit or remove them first")
        return 1
    pin = load_pins(root / "config" / "data_files.toml")["june_2026"]["sha256"]
    missing = missing_gates(read_gates(root / GATES), code_hash(root), pin)
    if missing:
        print(f"refused: runs/JUNE_GATES.md holds no open pass of the {' and '.join(missing)} gate for this code "
              "and the June pin. Run both gates first (cloud/failcheck/STEPS.md)")
        return 1
    print(f"june list sha256 {list_hash(root)}")
    print(f"frozen code sha256 {code_hash(root)} over {len(frozen_files(root))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
