"""Spec 004, J1: print the June list's hash and the frozen code's hash, for an entry in runs/JUNE_RUNS.md.

Usage: python scripts/june_hash.py [root]

Run it from a clean checkout of the commit to be frozen. It refuses when the frozen files on disk differ from the
files git tracks, naming only their number. It prints two hashes and a file count, nothing else. Where git is
missing, it says so on stderr and hashes the files as they are.
"""
import sys
from pathlib import Path

from voc.frozen import code_hash, differs_from_git, frozen_files, list_hash


def main(argv):
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    differ = differs_from_git(root)
    if differ is None:
        print("no git checkout here, so the frozen files were not compared with the tracked ones", file=sys.stderr)
    elif differ:
        print(f"refused: {len(differ)} frozen files differ from the files git tracks. Commit or remove them first")
        return 1
    print(f"june list sha256 {list_hash(root)}")
    print(f"frozen code sha256 {code_hash(root)} over {len(frozen_files(root))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
