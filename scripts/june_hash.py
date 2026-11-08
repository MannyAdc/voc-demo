"""Spec 004, J1: print the June list's hash and the frozen code's hash, for an entry in runs/JUNE_RUNS.md.

Usage: python scripts/june_hash.py [root]
       python scripts/june_hash.py --dry-run [root]

Run it from a clean checkout of the commit to be frozen. It refuses when the frozen files on disk differ from the
files git tracks, in name or in content, naming only their number. It prints two hashes and a file count,
nothing else. Where git is missing, it says so on stderr and hashes the files as they are.

It also refuses unless `runs/JUNE_GATES.md` holds an open pass of both gates, `june-check` and `failcheck`, for
this code and the June pin (owner decisions, 6 November). It has no way round that.

`--dry-run` prints the dry run's own list hash, `splits/june_dry/june_dry.csv`, and the frozen code's hash, for the
synthetic row (pull request 9a). J1's gates guard only a real row, so it checks none, and it never prints the June
list's hash. It refuses until `config/june_cloud.toml` holds the jobs' IDs, since that file is frozen and the row's
code hash must include it (owner decision, 8 November: the row comes after the jobs' IDs).
"""
import sys
from pathlib import Path

from voc.datafile import load_pins
from voc.frozen import (GATES, JuneRunsError, changed_frozen, code_hash, dry_run_list_hash, frozen_files, list_hash,
                        missing_gates, read_gates)


def main(argv):
    dry_run = bool(argv) and argv[0] == "--dry-run"
    rest = argv[1:] if dry_run else argv
    if len(rest) > 1 or (rest and rest[0].startswith("-")):
        print("refused: the only arguments are --dry-run and the checkout's folder")
        return 1
    root = Path(rest[0]) if rest else Path(__file__).resolve().parents[1]
    differ = changed_frozen(root)
    if differ is None:
        print("no git checkout here, so the frozen files were not compared with the tracked ones", file=sys.stderr)
    elif differ:
        print(f"refused: {len(differ)} frozen files differ from the files git tracks. Commit or remove them first")
        return 1
    if dry_run:
        return _dry_run(root)
    pin = load_pins(root / "config" / "data_files.toml")["june_2026"]["sha256"]
    missing = missing_gates(read_gates(root / GATES), code_hash(root), pin)
    if missing:
        print(f"refused: runs/JUNE_GATES.md holds no open pass of the {' and '.join(missing)} gate for this code "
              "and the June pin. Run both gates first (cloud/failcheck/STEPS.md)")
        return 1
    print(f"june list sha256 {list_hash(root)}")
    print(f"frozen code sha256 {code_hash(root)} over {len(frozen_files(root))} files")
    return 0


def _dry_run(root):
    from voc.approval import ApprovalError, cloud_settings

    try:
        cloud_settings(root)
        refused = None
    except ApprovalError:
        refused = "refused: config/june_cloud.toml must hold both jobs' IDs before the synthetic row's hashes"
    if refused:
        print(refused)
        return 1
    try:
        listed = dry_run_list_hash(root)
    except (OSError, ValueError, KeyError, JuneRunsError):
        listed = None
    if listed is None:
        print("refused: splits/june_dry/june_dry.csv does not match its manifest")
        return 1
    print(f"dry-run list sha256 {listed}")
    print(f"frozen code sha256 {code_hash(root)} over {len(frozen_files(root))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
