"""V1: run-to-run consistency (specs/003-validation-review/spec.md).

V1's frozen list of development complaints is labelled again with prompt v1, the same model and the same
settings, as fresh calls under a repeat number. The number joins the recording key only (`voc.replay`), so
the recordings of 29 October are never replayed for it. Each new answer is compared with the recorded one by
its decision, its proposed label and its quote positions.

Nothing runs live without `--approved`. Before that, the command prints the calls, the expected cost, the
worst case the ledger will reserve and the tokens left (V9). Only IDs, labels, positions, codes and counts are
written or printed (B21, V8).
"""
import csv
import hashlib
import io
import json
import math
import os
import time
from decimal import Decimal
from pathlib import Path

from voc.baselines import cut_text
from voc.budget import worst_case
from voc.costs import call_cost
from voc.decision import MODEL_ERROR, NOT_RUN_BUDGET, before_call
from voc.pipeline import _proposed, definitions, label_complaints
from voc.prompt import build_prompt
from voc.replay import MAX_RETRIES, recording_key, recordings_dir

PROMPT = "v1"
DECISION = ("both_accepted", "both_quarantined", "changed")
LABEL = ("same", "different", "missing")
QUOTE = ("same", "overlapping", "apart")
FIELDS = ("complaint_id", "repeat", "old_decision", "new_decision", "old_label", "new_label", "decision", "label",
          "quote", "new_quote_start", "new_quote_end", "new_reason", "recording_key", "source", "input_tokens",
          "output_tokens")


class ConsistencyError(ValueError):
    """An error whose message is ours, so it is safe to print (it never holds data)."""


def wilson(k, n, z=1.96):
    """The Wilson score interval for k out of n, at 95 percent (V10)."""
    if n <= 0:
        raise ValueError("a share needs at least one case")
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def compare(old, new):
    """The codes for one complaint. `old` and `new` hold the decision, the proposed label and the quote positions,
    as the results files write them."""
    if old["decision"] == new["decision"] == "accepted":
        decision = "both_accepted"
    elif old["decision"] == new["decision"] == "quarantined":
        decision = "both_quarantined"
    else:
        decision = "changed"
    if not old["proposed_label"] or not new["proposed_label"]:
        label = "missing"
    else:
        label = "same" if old["proposed_label"] == new["proposed_label"] else "different"
    if decision != "both_accepted":
        quote = "not_compared"
    else:
        a = (int(old["quote_start"]), int(old["quote_end"]))
        b = (int(new["quote_start"]), int(new["quote_end"]))
        quote = "same" if a == b else "overlapping" if a[0] < b[1] and b[0] < a[1] else "apart"
    return {"decision": decision, "label": label, "quote": quote}


def _position(value):
    return "" if value is None else str(value)


def relabel(complaints, version, labels, call, backend_name, repeat, old):
    """Label the complaints again under `repeat` and compare each answer with `old`, its recorded row by ID."""
    names = [label.name for label in labels]
    rows = []
    for outcome in label_complaints(complaints, version, labels, call, backend_name, repeat=repeat):
        d = outcome.decision
        new = {"decision": "accepted" if d.accepted else "quarantined", "proposed_label": _proposed(d, names),
               "quote_start": _position(d.quote_start), "quote_end": _position(d.quote_end)}
        before = old[d.complaint_id]
        rows.append({"complaint_id": d.complaint_id, "repeat": repeat, "old_decision": before["decision"],
                     "new_decision": new["decision"], "old_label": before["proposed_label"],
                     "new_label": new["proposed_label"], **compare(before, new),
                     "new_quote_start": new["quote_start"], "new_quote_end": new["quote_end"],
                     "new_reason": d.reason or "", "recording_key": outcome.recording_key or "",
                     "source": outcome.source or "", "input_tokens": outcome.input_tokens,
                     "output_tokens": outcome.output_tokens})
    return rows


def _share(k, n):
    low, high = wilson(k, n)
    return {"count": k, "share": k / n, "interval": [low, high]}


def summarise(rows, repeat):
    """Counts, shares and Wilson intervals. Quote codes are shared over the complaints accepted both times."""
    n = len(rows)
    if not n:
        raise ConsistencyError("there are no complaints to summarise")
    summary = {"repeat": repeat, "complaints": n}
    for field, codes in (("decision", DECISION), ("label", LABEL)):
        summary[field] = {code: _share(sum(r[field] == code for r in rows), n) for code in codes}
    compared = [r for r in rows if r["quote"] != "not_compared"]
    summary["quote_compared"] = len(compared)
    summary["quote_not_compared"] = n - len(compared)
    summary["quote"] = ({code: _share(sum(r["quote"] == code for r in compared), len(compared)) for code in QUOTE}
                        if compared else {})
    return summary


def rows_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row.get(key) is None else row[key] for key in FIELDS})
    return out.getvalue()


def tokens_left(state):
    """The cap left for this run: the effective cap less the tokens used and reserved (as the final run's check).
    An open overrun refuses."""
    from voc.budget import effective_cap

    if state.get("overrun") is not None:
        raise ConsistencyError("a ledger overrun is open. Clear it with `voc ledger clear-overrun` first")
    return effective_cap(state) - state["used"] - state["reserved"]


def estimate(complaints, version, labels, old, prices, margin, tokens_left, is_recorded=None):
    """The calls, the expected cost from the recorded tokens of the same complaints, and the worst case the
    ledger will reserve, retries included. Refused when the worst case is over the tokens left.

    `is_recorded(prompt)` says whether an answer is already recorded under this repeat number. Those are
    replayed at no cost, so the printout says how many there are.
    """
    names, defined = [label.name for label in labels], definitions(labels)
    model, limit = version.settings["model"], version.settings["max_tokens"]
    calls, expected, worst, recorded = 0, Decimal(0), 0, 0
    for complaint in complaints:
        text, _ = cut_text(complaint.narrative)
        if before_call(text):
            continue
        prompt = build_prompt(version.instructions, names, text, complaint_id=complaint.complaint_id,
                              definitions=defined).prompt
        calls += 1
        recorded += bool(is_recorded and is_recorded(prompt))
        worst += worst_case(prompt, limit, margin)
        before = old[complaint.complaint_id]
        try:
            expected += call_cost(prices, model, int(before["input_tokens"]), int(before["output_tokens"]))
        except (KeyError, TypeError, ValueError):
            raise ConsistencyError("a recorded answer has no token counts, so the cost cannot be estimated") from None
    worst *= MAX_RETRIES + 1
    if tokens_left is not None and worst > tokens_left:
        raise ConsistencyError(f"the cap has {tokens_left:,} tokens left, and this run needs up to {worst:,} in the "
                               "worst case, retries included")
    return {"calls": calls, "expected_cost_usd": str(expected), "worst_case_tokens": worst,
            "tokens_left": tokens_left, "already_recorded": recorded}


def result_paths(root, repeat):
    folder = Path(root) / "results" / "validation"
    return folder / f"v1_consistency_r{repeat}.csv", folder / f"v1_consistency_r{repeat}.json"


def _complaints(root):
    """V1's complaints, from its checked list, read by ID and checked against the development list (B16, V7)."""
    from voc.data import _manifest, verify_ids
    from voc.load import DB_PATH
    from voc.pipeline import Complaint, _rows_by_id
    from voc.validation import read_lists

    splits = Path(root) / "splits"
    wanted = set(read_lists(splits)["v1"])
    rows = _rows_by_id(Path(root) / DB_PATH, _manifest(splits)["month"], wanted)
    if {r.complaint_id for r in rows} != wanted:
        raise ConsistencyError(f"{len(wanted - {r.complaint_id for r in rows})} V1 complaints are missing from the "
                               "staged table")
    verify_ids(splits, "dev", rows)
    return [Complaint(r.complaint_id, r.narrative) for r in rows]


def _old(root):
    """The recorded answers, from the labels file the lists were drawn from, read once and checked by its hash."""
    manifest = json.loads((Path(root) / "splits" / "validation" / "manifest.json").read_text(encoding="utf-8"))
    data = (Path(root) / manifest["labels_file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["labels_sha256"]:
        raise ConsistencyError(f"{manifest['labels_file']} does not match its hash in the validation manifest")
    return {r["complaint_id"]: r for r in csv.DictReader(io.StringIO(data.decode("utf-8")))}


def format_estimate(figures, repeat, model):
    left = figures["tokens_left"]
    return [f"V1 consistency, repeat {repeat}: prompt {PROMPT}, model {model}",
            f"calls: {figures['calls']}",
            f"expected cost: ${Decimal(figures['expected_cost_usd']):.4f}, from the recorded tokens of the same "
            "complaints",
            f"worst case: {figures['worst_case_tokens']:,} tokens reserved at most, retries included",
            f"already recorded under repeat {repeat}: {figures['already_recorded']}, replayed at no cost",
            "tokens left: no ledger for the mock backend" if left is None else f"tokens left: {left:,}"]


def format_summary(summary, paths):
    lines = [f"complaints: {summary['complaints']}"]
    for field in ("decision", "label", "quote"):
        for code, figure in summary[field].items():
            low, high = figure["interval"]
            lines.append(f"{field} {code}: {figure['count']} ({figure['share']:.1%}, 95% interval "
                         f"{low:.1%} to {high:.1%})")
    lines.append(f"quote not compared: {summary['quote_not_compared']}")
    lines.append(f"cost: ${Decimal(summary['cost_usd']):.4f} for {summary['live_calls']} live calls")
    lines.append(f"replayed calls: {summary['replayed_calls']}")
    lines += [f"written to {p.as_posix()}" for p in paths]
    return lines


def _summary_json(summary):
    return json.dumps(summary, indent=2, sort_keys=True) + "\n"


def _write_results(paths, rows, summary):
    """Both files are written to temporary files first and then renamed, so a write that fails partway leaves
    neither, and the repeat stays open."""
    folder = paths[0].parent
    folder.mkdir(parents=True, exist_ok=True)
    temporary = [folder / f".{p.name}.tmp" for p in paths]
    try:
        temporary[0].write_text(rows_csv(rows), encoding="utf-8", newline="\n")
        temporary[1].write_text(_summary_json(summary), encoding="utf-8", newline="\n")
        for temp, path in zip(temporary, paths):
            os.replace(temp, path)
    except BaseException:
        for temp in temporary:
            temp.unlink(missing_ok=True)
        raise


def command(config, root, repeat, approved):
    """`voc consistency`. Returns the lines to print."""
    from voc import backends
    from voc.budget import Ledger, load_config
    from voc.costs import load_prices
    from voc.labels import load_labels
    from voc.pipeline import load_prompt_version
    from voc.replay import Answer, Caller, Reply

    root = Path(root)
    backend_name = config.get("LLM_BACKEND", "")
    if backend_name not in ("api", "mock"):
        raise ConsistencyError("LLM_BACKEND must be api or mock")
    paths = result_paths(root, repeat)
    if any(p.exists() for p in paths):
        raise ConsistencyError(f"the results of repeat {repeat} already exist. Use a new repeat number")
    version = load_prompt_version(root, PROMPT)
    labels = load_labels(root / "config" / "labels.toml")
    complaints, old = _complaints(root), _old(root)
    prices = load_prices(root / "config" / "prices.toml")
    model, settings = version.settings["model"], version.settings
    ledger, left, is_recorded = None, None, None
    if backend_name == "api":
        ledger = Ledger()
        left = tokens_left(ledger.state())

        def is_recorded(prompt):
            return (recordings_dir() / f"{recording_key('api', model, settings, prompt, repeat)}.json").exists()
    figures = estimate(complaints, version, labels, old, prices, load_config(root)["input_margin_tokens"], left,
                       is_recorded)
    lines = format_estimate(figures, repeat, model)
    if not approved:
        return lines + ["no call made. Run it again with --approved once the owner has approved these figures"]
    if backend_name == "mock":
        if not config.get("VOC_MOCK_FIXTURES"):
            raise ConsistencyError("the mock backend needs VOC_MOCK_FIXTURES, a JSON file of synthetic answers")
        items = json.loads(Path(config["VOC_MOCK_FIXTURES"]).read_text(encoding="utf-8"))
        backend = backends.make_backend("mock", fixtures={i["prompt"]: Answer(i["text"], None, None, "end_turn")
                                                          for i in items})

        def call(prompt):
            return Reply(backend(prompt, dict(settings)).text, "mock", None, None, 0, 0, 1)
    else:
        backend = backends.make_backend("api", env=config, model=model)
        call = Caller("api", model, settings, backend=backend, mode="live", root=root, ledger=ledger,
                      repeat=repeat).call
    used_before = ledger.state()["used"] if ledger else None
    started = time.monotonic()
    rows = relabel(complaints, version, labels, call, backend_name, repeat, old)
    failed = sum(r["new_reason"] in (MODEL_ERROR, NOT_RUN_BUDGET) for r in rows)
    if failed:
        raise ConsistencyError(f"{failed} complaints failed with a model error or at the cap, so no results are "
                               f"written. The answers so far are recorded. Run repeat {repeat} again to finish")
    summary = summarise(rows, repeat)
    live = [r for r in rows if r["source"] == "live" and r["input_tokens"] is not None]
    cost = sum((call_cost(prices, model, r["input_tokens"], r["output_tokens"]) for r in live), Decimal(0))
    summary.update({"prompt_version": PROMPT, "model": model, "backend": backend_name,
                    "list": "splits/validation/v1.csv", "run_seconds": round(time.monotonic() - started, 1),
                    "live_calls": len(live), "replayed_calls": sum(r["source"] == "replay" for r in rows),
                    "input_tokens": sum(r["input_tokens"] for r in live),
                    "output_tokens": sum(r["output_tokens"] for r in live), "cost_usd": str(cost)})
    if ledger is not None:
        summary["ledger_charged_tokens"] = ledger.state()["used"] - used_before
    _write_results(paths, rows, summary)
    return lines + format_summary(summary, [p.relative_to(root) for p in paths])
