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
from voc import dbt_run
from voc.backends import ALLOWED, BackendError
from voc.data import SampleMismatch, build_samples, format_summary
from voc.datafile import DataFileError, find_export, load_pins, sha256_of, verify
from voc.dbt_run import DbtError
from voc.env import settings
from voc.labels import load_labels
from voc.load import DB_PATH, load_month
from voc.profile import format_profile, profile
from voc.replay import RecordingCorrupt, RecordingMissing

PIN = "july_2026"
# Each month's data folder comes from its own environment variable, never from a file (add-on 1).
MONTHS = {"july_2026": "VOC_DATA_DIR", "august_2026": "VOC_NEXT_DATA_DIR"}


def _export(config, month=PIN):
    variable = MONTHS[month]
    folder = config.get(variable)
    if not folder:
        raise DataFileError(f"{variable} is not set, in the environment or in .env")
    return find_export(folder)


def _pin(root, month):
    pins = load_pins(Path(root) / "config" / "data_files.toml")
    if month not in pins:
        raise DataFileError(f"{month} has no pin in config/data_files.toml yet")
    return pins[month]


def _data_hash(config, root, args):
    path = _export(config, args.month)
    print(f"{path.name}  {path.stat().st_size} bytes  sha256 {sha256_of(path)}")


def _load(config, root, args):
    path = _export(config, args.month)
    verify(path, _pin(root, args.month))
    labels = [label.name for label in load_labels(Path(root) / "config" / "labels.toml")]
    counts = load_month(Path(root) / DB_PATH, path, args.month, labels)
    print(f"loaded {args.month}: {counts['rows']} rows in the file, {counts['new']} new, "
          f"{counts['already_loaded']} already loaded, {counts['total']} rows in the staged table")


def _dbt(config, root, args):
    labels = [label.name for label in load_labels(Path(root) / "config" / "labels.toml")]
    if args.action == "docs":
        print("\n".join(dbt_run.docs(root, labels)))
        return
    lines, passed = dbt_run.build(root, labels)
    print("\n".join(lines))
    if not passed:
        raise DbtError("the dbt build failed, see the checks above")


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


def _sample(config, root, args):
    import tomllib

    with open(Path(root) / "config" / "samples.toml", "rb") as f:
        chosen = tomllib.load(f)
    month = chosen["month"]
    summary = build_samples(Path(root) / DB_PATH, month, seed=chosen["seed"],
                            splits_dir=Path(root) / "splits", source_sha256=_pin(root, month)["sha256"],
                            dev_margin=chosen["dev_margin"], test_margin=chosen["test_margin"])
    print(format_summary(summary))


def _label(config, root, args):
    from voc import pipeline
    from voc.backends import make_backend
    from voc.budget import Ledger
    from voc.costs import load_prices, run_cost
    from voc.replay import Answer, Caller, Reply

    backend_name = config.get("LLM_BACKEND", "")
    if backend_name not in ALLOWED:
        raise BackendError(f"unknown LLM_BACKEND {backend_name!r}, allowed values are {', '.join(ALLOWED)}")
    root = Path(root)
    version = pipeline.load_prompt_version(root, args.prompt)
    labels = load_labels(root / "config" / "labels.toml")
    complaints = pipeline.load_complaints(root / DB_PATH, root / "splits", args.set)
    complaints = sorted(complaints, key=lambda c: pipeline._id_number(c.complaint_id))
    if args.limit is not None:
        complaints = complaints[:args.limit]
    settings, model = version.settings, version.settings["model"]
    ledger, used_before = None, None
    if backend_name == "mock":
        if not config.get("VOC_MOCK_FIXTURES"):
            raise BackendError("the mock backend needs VOC_MOCK_FIXTURES, a JSON file of synthetic answers")
        items = json.loads(Path(config["VOC_MOCK_FIXTURES"]).read_text(encoding="utf-8"))
        backend = make_backend("mock", fixtures={item["prompt"]: Answer(item["text"], None, None, "end_turn")
                                                 for item in items})

        def call(prompt):
            return Reply(backend(prompt, dict(settings)).text, "mock", None, None, 0, 0, 1)
    else:
        mode = "replay" if args.replay else "live"
        backend = None if args.replay else make_backend("api", env=config, model=model)
        if not args.replay:
            ledger = Ledger()
            used_before = ledger.state()["used"]
        call = Caller("api", model, settings, backend=backend, mode=mode, root=root, ledger=ledger).call
    outcomes = pipeline.label_complaints(complaints, version, labels, call, backend_name)
    names = [label.name for label in labels]
    summary = pipeline.summarise(outcomes, args.set, version, backend_name,
                                 pipeline.list_sha256(root / "splits", args.set, complaints))
    if backend_name == "api":
        cost = run_cost(load_prices(root / "config" / "prices.toml"), model, [o for o in outcomes if o.source])
        summary["cost"] = {key: str(value) for key, value in cost.items()}
    if ledger is not None:
        summary["ledger_charged_tokens"] = ledger.state()["used"] - used_before
    results = pipeline.write_run(root / "results" / "labels", outcomes, summary, version, names)
    print(pipeline.format_run(summary, results.relative_to(root)))
    if "ledger_charged_tokens" in summary:
        print(f"ledger: {summary['ledger_charged_tokens']} tokens charged by this run, failed calls included")


COMMANDS = {"data-hash": _data_hash, "profile": _profile, "load": _load, "sample": _sample, "label": _label,
            ("dbt", "build"): _dbt, ("dbt", "docs"): _dbt,
            ("ledger", "init"): _ledger_init, ("ledger", "raise"): _ledger_raise,
            ("ledger", "status"): _ledger_status, ("ledger", "release"): _ledger_release,
            ("ledger", "clear-overrun"): _ledger_clear_overrun}


def main(argv=None, env=None, root=None):
    parser = argparse.ArgumentParser(prog="voc")
    sub = parser.add_subparsers(dest="command", required=True)
    dh = sub.add_parser("data-hash", help="print the export file's name, size and SHA-256")
    dh.add_argument("month", nargs="?", default=PIN, choices=sorted(MONTHS), help="which month's folder to read")
    p = sub.add_parser("profile", help="print data facts as counts (B22)")
    p.add_argument("--write", help="also write the facts as JSON to this file")
    sub.add_parser("sample", help="build and freeze the samples from the staged July rows (B9, B16, B25)")
    lb = sub.add_parser("label", help="label development complaints with the LLM, printing counts only (B3, B21)")
    lb.add_argument("set", choices=("dev", "quick"), help="the development set, or its fixed 50-complaint part")
    lb.add_argument("--limit", type=int, help="label only the first N complaints, in complaint ID order")
    lb.add_argument("--prompt", default="v1", help="the prompt version, from config/prompts")
    lb.add_argument("--replay", action="store_true", help="serve recorded answers only, never a live call")
    ld = sub.add_parser("load", help="load one pinned monthly export into the staged DuckDB table (B14)")
    ld.add_argument("month", choices=sorted(MONTHS), help="the month to load, as named in config/data_files.toml")
    dbt = sub.add_parser("dbt", help="run the dbt project, printing counts and check names only (B14, B21)")
    dbt_actions = dbt.add_subparsers(dest="action", required=True)
    dbt_actions.add_parser("build", help="build the models and run the data tests")
    dbt_actions.add_parser("docs", help="write the dbt docs and lineage graph files to dbt/target")
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
        command = (args.command, args.action) if args.command in ("ledger", "dbt") else args.command
        COMMANDS[command](config, root, args)
    except (DataFileError, BudgetError, DbtError, SampleMismatch, BackendError, RecordingMissing,
            RecordingCorrupt) as err:
        print(f"error: {err}")
        return 1
    # B21: the type only, never the message. The spec also asks for the row number and the
    # complaint ID. Bulk loads have neither for a library error, so they come with the
    # row-by-row pipeline (T014).
    except Exception as err:
        print(f"error: {type(err).__name__}")
        return 1
    return 0


def run():
    sys.exit(main())


if __name__ == "__main__":
    run()
