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

from voc.budget import BudgetError, Ledger, clear_overrun, effective_cap, init_ledger, raise_cap, release
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
    result = raise_cap(root, reason=args.reason)
    print(f"cap {result['from']:,} to {result['to']:,} tokens, "
          f"effective cap {result['effective_from']:,} to {result['effective_to']:,} tokens. "
          "Event written to the ledger and BUILD_LOG.md")


def _ledger_status(config, root, args):
    state = Ledger().state()
    print(f"cap {state['cap']:,}  trial cap {state['trial_cap']:,}  margin confirmed {state['margin_confirmed']}")
    print(f"effective cap {effective_cap(state):,}  used {state['used']:,}  reserved {state['reserved']:,}  "
          f"calls {state['calls']:,}  overrun {'yes' if state['overrun'] else 'no'}")
    for rid, tokens in sorted(state["open"].items()):
        print(f"open reservation {rid}  {tokens:,} tokens")


def _ledger_release(config, root, args):
    tokens = release(args.reservation, reason=args.reason)
    print(f"reservation {args.reservation} released and charged {tokens:,} tokens")


def _ledger_clear_overrun(config, root, args):
    clear_overrun(reason=args.reason)
    print("overrun cleared, live calls may go on")


COMMANDS = {"data-hash": _data_hash, "profile": _profile,
            ("ledger", "init"): _ledger_init, ("ledger", "raise"): _ledger_raise,
            ("ledger", "status"): _ledger_status, ("ledger", "release"): _ledger_release,
            ("ledger", "clear-overrun"): _ledger_clear_overrun}


def main(argv=None, env=None, root=None):
    parser = argparse.ArgumentParser(prog="voc")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("data-hash", help="print the export file's name, size and SHA-256")
    p = sub.add_parser("profile", help="print data facts as counts (B22)")
    p.add_argument("--write", help="also write the facts as JSON to this file")
    ledger = sub.add_parser("ledger", help="the token ledger (B8)").add_subparsers(dest="action", required=True)
    init = ledger.add_parser("init", help="create the ledger with the committed cap")
    init.add_argument("--cap", type=int, help="a lower cap than the committed one")
    up = ledger.add_parser("raise", help="apply the cap config committed on main")
    up.add_argument("--reason", required=True, help="why the cap is raised, written to the ledger and the build log")
    ledger.add_parser("status", help="print the cap, the use and the open reservation IDs")
    rel = ledger.add_parser("release", help="close a reservation left open by a crash, charged in full")
    rel.add_argument("reservation", help="the reservation ID, from `voc ledger status`")
    rel.add_argument("--reason", required=True, help="why it is released, written to the ledger")
    clear = ledger.add_parser("clear-overrun", help="allow live calls again after an overrun")
    clear.add_argument("--reason", required=True, help="what was checked, written to the ledger")
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
