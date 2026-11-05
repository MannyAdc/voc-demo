"""Spec 004, J1: print the June list's hash and the frozen code's hash, for an entry in runs/JUNE_RUNS.md.

Usage: python scripts/june_hash.py

Run it from a clean checkout of the commit to be frozen. It prints two hashes and a file count, nothing else.
"""
import sys
from pathlib import Path

from voc.frozen import code_hash, frozen_files, list_hash


def main():
    root = Path(__file__).resolve().parents[1]
    print(f"june list sha256 {list_hash(root)}")
    print(f"frozen code sha256 {code_hash(root)} over {len(frozen_files(root))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
