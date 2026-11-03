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
import time
from pathlib import Path

from voc.budget import BudgetError, Ledger, clear_overrun, effective_cap, init_ledger, raise_cap, release
from voc import dbt_run
from voc.backends import ALLOWED, BackendError
from voc.data import SampleMismatch, build_samples, format_summary
from voc.datafile import DataFileError, find_export, load_pins, sha256_of, verify
from voc.dbt_run import DbtError
from voc.env import settings
from voc.audit import AuditError
from voc.consistency import ConsistencyError
from voc.review import ReviewError
from voc.judge import JudgeError
from voc.evaluate import EvaluationError
from voc.injection import InjectionError
from voc.testrun import TestRunError
from voc.labels import load_labels
from voc.load import DB_PATH, load_month
from voc.profile import format_profile, profile
from voc.pipeline import RunStopped
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
    if getattr(args, "month", None) and args.target != "databricks":
        raise DbtError("--month needs --target databricks, so nothing was run")
    labels = [label.name for label in load_labels(Path(root) / "config" / "labels.toml")]
    if args.action == "docs":
        print("\n".join(dbt_run.docs(root, labels)))
        return
    if args.action == "lineage":
        print("\n".join(dbt_run.lineage(root, labels)))
        return
    lines, passed = dbt_run.build(root, labels, args.target, args.month)
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


def _validation_lists(config, root, args):
    from voc.validation import format_summary, freeze

    print(format_summary(freeze(root)))


def _consistency(config, root, args):
    from voc.consistency import command

    print("\n".join(command(config, root, args.repeat, args.approved)))


def _review_sheet(config, root, args):
    from voc.review import format_sheet, write_sheet

    print("\n".join(format_sheet(write_sheet(root, args.piece))))


def _review_import(config, root, args):
    from voc.review import format_codes, import_codes

    print("\n".join(format_codes(import_codes(root, args.piece, replace=args.replace), root)))


def _judge(config, root, args):
    from voc.judge import command

    print("\n".join(command(config, root, args.action.replace("-", "_"), args.approved, args.judge)))


def _repeat(value):
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError("--repeat must be a whole number of 1 or more")
    return number


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
    if args.set == "injection":  # B5: the synthetic injection set, tied to its file by the file's hash
        from voc import injection

        if args.limit is not None:
            raise injection.InjectionError("the injection set is labelled whole, never with --limit")
        complaints, list_hash = injection.complaints(root)
    else:
        complaints, list_hash = pipeline.load_complaints(root / DB_PATH, root / "splits", args.set), None
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
    stopped = None
    started = time.monotonic()
    try:
        outcomes = pipeline.label_complaints(complaints, version, labels, call, backend_name)
    except RunStopped as err:  # the outcomes so far are still written, with the stop recorded (B7, B19)
        stopped, outcomes = err, err.outcomes
    run_seconds = time.monotonic() - started
    names = [label.name for label in labels]
    if list_hash is None:
        list_hash = pipeline.list_sha256(root / "splits", args.set, complaints)
    summary = pipeline.summarise(outcomes, args.set, version, backend_name, list_hash, limit=args.limit,
                                 stopped=stopped, run_seconds=run_seconds)
    if backend_name == "api":
        cost = run_cost(load_prices(root / "config" / "prices.toml"), model, [o for o in outcomes if o.source])
        summary["cost"] = {key: str(value) for key, value in cost.items()}
    if ledger is not None:
        summary["ledger_charged_tokens"] = ledger.state()["used"] - used_before
    results = pipeline.write_run(root / "results" / "labels", outcomes, summary, version, names)
    print(pipeline.format_run(summary, results.relative_to(root)))
    if "ledger_charged_tokens" in summary:
        print(f"ledger: {summary['ledger_charged_tokens']} tokens charged while this run went on, failed calls "
              "included. Any other run at the same time is counted too")
    if stopped is not None:
        raise stopped


def _audit(config, root, args):
    from voc.audit import audit, format_audit

    result = audit(root, args.set, args.prompt)
    print(format_audit(result))
    if result["failures"]:
        raise AuditError(f"{sum(result['failures'].values())} accepted labels failed the audit")


def _test_run(config, root, args):
    """B17: the owner's one scored run of the test set, live on the api backend."""
    from voc import testrun
    from voc.backends import make_backend
    from voc.budget import Ledger, effective_cap
    from voc.costs import load_prices, run_cost
    from voc.pipeline import load_prompt_version
    from voc.replay import Caller

    if config.get("LLM_BACKEND") != "api":
        raise BackendError("the test run needs LLM_BACKEND=api")
    root = Path(root)
    version = load_prompt_version(root, args.prompt)
    model, settings = version.settings["model"], version.settings
    ledger = Ledger()
    state = ledger.state()
    remaining = effective_cap(state) - state["used"] - state["reserved"]
    call = Caller("api", model, settings, backend=make_backend("api", env=config, model=model), mode="live",
                  root=root, ledger=ledger).call

    def cost(outcomes):
        found = run_cost(load_prices(root / "config" / "prices.toml"), model, [o for o in outcomes if o.source])
        return {"cost": {key: str(value) for key, value in found.items()}}

    report = testrun.run(root, args.prompt, args.reason, call, remaining, add_to_summary=cost,
                         overrun=state["overrun"] is not None)
    print(testrun.format_report(report))


def _serve(config, root, args):
    """A4: the results API and dashboard, on this computer only."""
    import uvicorn

    from voc.api import create_app

    # A10: complaint text only when the owner asks for it. The coding agent never passes --with-text (CLAUDE.md).
    what = "with complaint text from the local data" if args.with_text else "no complaint text"
    print(f"dashboard on http://127.0.0.1:{args.port}/ ({what}). Ctrl+C stops it")
    uvicorn.run(create_app(root, with_text=args.with_text), host="127.0.0.1", port=args.port, log_level="warning")


def _evaluate(config, root, args):
    if args.set == "injection":  # B10: scored apart, never in an accuracy figure or EVAL_VERSIONS.md
        from voc.injection import format_score, score

        print(format_score(score(root, args.prompt, args.note)))
        return
    from voc.evaluate import evaluate, format_evaluation

    print(format_evaluation(evaluate(root, args.set, args.prompt, args.note), root))


COMMANDS = {"data-hash": _data_hash, "profile": _profile, "load": _load, "sample": _sample,
            "validation-lists": _validation_lists, "consistency": _consistency,
            ("review", "sheet"): _review_sheet, ("review", "import"): _review_import,
            ("judge", "dry-run"): _judge, ("judge", "main"): _judge, "label": _label,
            "evaluate": _evaluate, "final": _test_run, "audit": _audit, "serve": _serve,
            ("dbt", "build"): _dbt, ("dbt", "docs"): _dbt, ("dbt", "lineage"): _dbt,
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
    sub.add_parser("validation-lists", help="draw and freeze the validation review's lists from the development "
                                           "set, printing counts only (spec 003, B16)")
    co = sub.add_parser("consistency", help="V1: label V1's list again under a repeat number and compare, printing "
                                            "counts only. No call without --approved (spec 003)")
    co.add_argument("--repeat", type=_repeat, required=True, help="the repeat number, 1 or more, joined to the "
                                                                  "recording key only")
    co.add_argument("--approved", action="store_true", help="make the calls. Only after the owner approved the "
                                                            "figures printed without it")
    rv = sub.add_parser("review", help="V2 and V3: the owner's review sheets (spec 003). The owner runs these, "
                                       "because a sheet holds complaint text")
    rv_actions = rv.add_subparsers(dest="action", required=True)
    sh = rv_actions.add_parser("sheet", help="write the sheet in the review folder, once")
    sh.add_argument("piece", choices=("v2", "v3", "v5", "v5_dry_run"), help="which review, or the judge's dry run")
    im = rv_actions.add_parser("import", help="read only the ID and code columns back, printing counts only")
    im.add_argument("piece", choices=("v2", "v3", "v5"), help="which review")
    im.add_argument("--replace", action="store_true", help="write over codes imported before")
    jd = sub.add_parser("judge", help="V5: the judge rates whether each quote supports its label, printing counts "
                                      "only. No call without --approved (spec 003)")
    jd_actions = jd.add_subparsers(dest="action", required=True)
    for action, text in (("dry-run", "rate the dry run's own cases, which are never reported, and check the margin"),
                         ("main", "rate every accepted development label but the dry run's, after the owner's "
                                  "V5 ratings")):
        step = jd_actions.add_parser(action, help=text)
        step.add_argument("--approved", action="store_true", help="make the calls. Only after the owner approved "
                                                                  "the figures printed without it")
        step.add_argument("--judge", default="judge_v1", help="the judge's rubric, from config/prompts")
    lb = sub.add_parser("label", help="label development complaints with the LLM, printing counts only (B3, B21)")
    lb.add_argument("set", choices=("dev", "quick", "injection"),
                    help="the development set, its fixed 50-complaint part, or the synthetic injection set")
    lb.add_argument("--limit", type=int, help="label only the first N complaints, in complaint ID order")
    lb.add_argument("--prompt", default="v1", help="the prompt version, from config/prompts")
    lb.add_argument("--replay", action="store_true", help="serve recorded answers only, never a live call")
    fr = sub.add_parser("final", help="the owner's one scored run of the frozen test set (B17)")
    fr.add_argument("--prompt", default="v1", help="the prompt version that goes to the test set")
    fr.add_argument("--reason", help="why, if a test run is already logged. It goes in the logs and BUILD_LOG.md")
    ev = sub.add_parser("evaluate", help="score a finished development run against TF-IDF, printing figures only "
                                         "(B10, B15, B21)")
    ev.add_argument("set", choices=("dev", "injection"),
                    help="the development set, or the synthetic injection set. The test set waits for the final run")
    ev.add_argument("--prompt", default="v1", help="the prompt version whose run is scored")
    ev.add_argument("--note", required=True, help="what changed in this version, for EVAL_VERSIONS.md")
    au = sub.add_parser("audit", help="re-check every accepted label against its recorded answer and the text, "
                                      "printing counts only (B1, B21)")
    au.add_argument("set", choices=("dev", "quick"), help="the set whose labelling run is audited")
    au.add_argument("--prompt", default="v1", help="the prompt version whose run is audited")
    sv = sub.add_parser("serve", help="the results API and dashboard on 127.0.0.1, committed results only (A1 to A8)")
    sv.add_argument("--port", type=int, default=8000, help="the local port")
    sv.add_argument("--with-text", action="store_true",
                    help="include complaint text from the local data, for the owner only (A10). Claude never passes it")
    ld = sub.add_parser("load", help="load one pinned monthly export into the staged DuckDB table (B14)")
    ld.add_argument("month", choices=sorted(MONTHS), help="the month to load, as named in config/data_files.toml")
    dbt = sub.add_parser("dbt", help="run the dbt project, printing counts and check names only (B14, B21)")
    dbt_actions = dbt.add_subparsers(dest="action", required=True)
    db = dbt_actions.add_parser("build", help="build the models and run the data tests")
    db.add_argument("--target", choices=dbt_run.TARGETS, default="local",
                    help="local DuckDB, or Databricks on the synthetic seeds (T021) or a real month (--month)")
    db.add_argument("--month", choices=sorted(MONTHS), default=None,
                    help="with --target databricks: build from this month's pinned export in the volume")
    dbt_actions.add_parser("docs", help="write the dbt docs and lineage graph files to dbt/target")
    dbt_actions.add_parser("lineage", help="write docs/LINEAGE.md, a lineage graph of node names only (T017)")
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
        command = (args.command, args.action) if args.command in ("ledger", "dbt", "review", "judge") \
            else args.command
        COMMANDS[command](config, root, args)
    except (DataFileError, BudgetError, DbtError, SampleMismatch, BackendError, RecordingMissing,
            RecordingCorrupt, RunStopped, EvaluationError, AuditError, InjectionError, TestRunError,
            ConsistencyError, ReviewError, JudgeError) as err:
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
