"""The `voc` command line.

B21: every command prints only counts, IDs, labels, reasons and positions.
Our own errors (DataFileError) are printed as they are, because their text
is ours. Any other error is printed as its type only, because a library
error such as a CSV parse error can echo a raw row.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from voc.budget import BudgetError, init_ledger, raise_cap
from voc.datafile import DataFileError, find_export, load_pins, sha256_of, verify
from voc.env import settings
from voc.profile import format_profile, profile

PIN = "july_2026"


def _export(config):
    folder = config.get("VOC_DATA_DIR")
    if not folder:
        raise DataFileError("VOC_DATA_DIR is not set, in the environment or in .env")
    return find_export(folder)


def _data_hash(config, root, args):
    path = _export(config)
    print(f"{path.name}  {path.stat().st_size} bytes  sha256 {sha256_of(path)}")


def _profile(config, root, args):
    path = _export(config)
    verify(path, load_pins(Path(root) / "config" / "data_files.toml")[PIN])
    facts = profile(path)
    print(format_profile(facts))
    if args.write:
        Path(args.write).write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nwritten: {args.write}")


def _ledger_init(config, root, args):
    cap = init_ledger(root, cap=args.cap)
    print(f"ledger created in the home folder, cap {cap:,} tokens")


def _ledger_raise(config, root, args):
    cap = raise_cap(root, reason=args.reason)
    print(f"cap raised to {cap:,} tokens, event written to the ledger and BUILD_LOG.md")


COMMANDS = {"data-hash": _data_hash, "profile": _profile,
            ("ledger", "init"): _ledger_init, ("ledger", "raise"): _ledger_raise}


def main(argv=None, env=None, root=None):
    parser = argparse.ArgumentParser(prog="voc")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("data-hash", help="print the export file's name, size and SHA-256")
    p = sub.add_parser("profile", help="print data facts as counts (B22)")
    p.add_argument("--write", help="also write the facts as JSON to this file")
    ledger = sub.add_parser("ledger", help="the token ledger (B8)").add_subparsers(dest="action", required=True)
    init = ledger.add_parser("init", help="create the ledger with the committed cap")
    init.add_argument("--cap", type=int, help="a lower cap than the committed one")
    up = ledger.add_parser("raise", help="raise the cap to the committed value")
    up.add_argument("--reason", required=True, help="why the cap is raised, written to the ledger and the build log")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = Path.cwd() if root is None else Path(root)
    config = settings(dict(os.environ) if env is None else env, root)
    try:
        command = (args.command, args.action) if args.command == "ledger" else args.command
        COMMANDS[command](config, root, args)
    except (DataFileError, BudgetError) as err:
        print(f"error: {err}")
        return 1
    except Exception as err:  # B21: the type only, never the message
        print(f"error: {type(err).__name__}")
        return 1
    return 0


def run():
    sys.exit(main())


if __name__ == "__main__":
    run()
