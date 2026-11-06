"""Spec 004, J1: print the June list's hash and the frozen code's hash, for an entry in runs/JUNE_RUNS.md.

Usage: python scripts/june_hash.py [root] [--synthetic]

Run it from a clean checkout of the commit to be frozen. It refuses when the frozen files on disk differ from the
files git tracks, naming only their number. It prints two hashes and a file count, nothing else. Where git is
missing, it says so on stderr and hashes the files as they are.

For the real row it also refuses unless `runs/JUNE_GATES.md` records a pass of both gates, `june-check` and
`failcheck`, for this code and the June pin (owner decision, 6 November). `--synthetic` is for a synthetic row,
which needs no gate.
"""
import sys
from pathlib import Path

from voc.datafile import load_pins
from voc.frozen import GATES, code_hash, differs_from_git, frozen_files, list_hash, missing_gates, read_gates


def main(argv):
    synthetic = "--synthetic" in argv
    argv = [a for a in argv if a != "--synthetic"]
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    differ = differs_from_git(root)
    if differ is None:
        print("no git checkout here, so the frozen files were not compared with the tracked ones", file=sys.stderr)
    elif differ:
        print(f"refused: {len(differ)} frozen files differ from the files git tracks. Commit or remove them first")
        return 1
    if not synthetic:
        pin = load_pins(root / "config" / "data_files.toml")["june_2026"]["sha256"]
        missing = missing_gates(read_gates(root / GATES), code_hash(root), pin)
        if missing:
            print(f"refused: runs/JUNE_GATES.md records no pass of the {' and '.join(missing)} gate for this code and "
                  "the June pin. Run both gates first (cloud/failcheck/STEPS.md)")
            return 1
    print(f"june list sha256 {list_hash(root)}")
    print(f"frozen code sha256 {code_hash(root)} over {len(frozen_files(root))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
