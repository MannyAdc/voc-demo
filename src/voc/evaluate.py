"""B10, B15, B18, B19, B23: score a finished labelling run of the development set against TF-IDF.

It reads the run's results file and summary, and the recorded Products of the development and training
sets, checked against the committed lists. TF-IDF learns from the training set and labels every
development complaint. Both methods are then scored by `voc.metrics`. Everything printed or written is
figures, labels, reasons and IDs, never text (B21). The test set is never read here (B17).
"""
import csv
import hashlib
import io
import json
import statistics
import time
import tomllib
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from voc import metrics
from voc.baselines import fit_tfidf, load_tfidf_config, predict_tfidf
from voc.data import SampleMismatch, _id_number, _manifest, read_splits, verify_ids
from voc.labels import load_labels
from voc.load import DB_PATH
from voc.pipeline import _rows_by_id

SETS = ("dev",)
TUNING = "tuning figures. The verdict comes only from the single logged test run"
CLAIM = "the claim's verdict, from the single logged test run (B10, B17)"
TOO_FEW = 30  # B25: a Product with fewer complaints in a sample is "too few to judge"
RESAMPLES = 2000
SEED = 0
COVERAGE_POINTS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
EVAL_FIELDS = ("complaint_id", "split", "prompt_version", "proposed_label", "quote_start", "quote_end", "decision",
               "reason", "accepted_label", "tfidf_label", "tfidf_confidence", "recording_key")
VERSIONS_FILE = "EVAL_VERSIONS.md"
VERSIONS_COLUMNS = ("Date", "Prompt", "What changed", "Set", "List hash", "Backend", "Model", "Effort",
                    "Complaints", "LLM accuracy", "LLM coverage", "LLM quarantined", "TF-IDF accuracy",
                    "TF-IDF coverage", "TF-IDF quarantined", "Interval", "Quote length", "Live cost",
                    "Replay cost")
VERSIONS_INTRO = """# Evaluation versions

One row per evaluation of a prompt version on the development set, written by `voc evaluate` (B15).
Rows are only ever added. These are tuning figures. The verdict comes only from the final test run.

- Accuracy is re-weighted strict accuracy (B10): quarantined labels count as wrong, and each category is
  weighted by its share of the pool.
- TF-IDF answers only its most confident complaints, as many as the LLM accepted. So its coverage equals
  the LLM's, and "TF-IDF quarantined" is the share it did not answer.
- Interval: the 95 percent interval of the LLM minus TF-IDF, in points, from the paired bootstrap.
- Quote length: accepted quotes, in characters, median and range.
- Live cost: what every answer cost when it was first made. Replay cost: what the labelling run paid, with
  recorded answers free.
- No table row says one version beats another. That needs a paired test, which is cut (B15).

"""


class EvaluationError(ValueError):
    pass


def _run(root, set_name, version):
    folder = Path(root) / "results" / "labels"
    path = folder / f"{version}_{set_name}.json"
    if not path.exists():
        raise EvaluationError(f"no finished run of prompt {version} on the {set_name} set. "
                              f"Run `voc label {set_name} --prompt {version}` first")
    summary = json.loads(path.read_text(encoding="utf-8"))
    if summary.get("stopped"):
        raise EvaluationError(f"{path.name} records a run that stopped early. A stopped run is not scored (B7)")
    results = folder / f"{version}_{set_name}.csv"
    if not results.exists():
        raise EvaluationError(f"{results.name} is missing, so the run cannot be scored")
    rows = list(csv.DictReader(io.StringIO(results.read_text(encoding="utf-8"))))
    versions = {summary.get("prompt_version")} | {r["prompt_version"] for r in rows}
    if versions != {version}:
        raise EvaluationError(f"the run files hold prompt version {', '.join(sorted(map(str, versions)))}, "
                              f"not {version}")
    return summary, rows


def _check_run(splits_dir, summary, rows, set_name="dev"):
    manifest = _manifest(splits_dir)
    if summary.get("list_sha256") != manifest["lists"][set_name]["sha256"]:
        raise SampleMismatch(f"the run's list hash does not match splits/{set_name}.csv, so it labelled another list")
    wanted = set(read_splits(splits_dir)[set_name])
    ids = [r["complaint_id"] for r in rows]
    if set(ids) != wanted or len(ids) != len(wanted):
        name = "development" if set_name == "dev" else set_name
        raise SampleMismatch(f"the results file holds {len(set(ids))} complaints and the {name} list "
                             f"{len(wanted)}. Only a run of the whole list is scored")
    return manifest


def _rows(db_path, splits_dir, month, name, ids):
    rows = _rows_by_id(db_path, month, ids)
    if {r.complaint_id for r in rows} != set(ids):
        raise SampleMismatch(f"{len(set(ids) - {r.complaint_id for r in rows})} {name} complaints are missing "
                             "from the staged table")
    verify_ids(splits_dir, name, rows)
    return sorted(rows, key=lambda r: _id_number(r.complaint_id))


def pool_shares(path, dev_rows, train_rows, test_size):
    """Each Product's share of the pool (B18), from the committed counts, checked against the lists.

    The test counts cannot be checked per category before the final run (B17). Only their total is checked
    against the test list, so counts moved between categories would go unnoticed.
    """
    if not Path(path).exists():
        raise EvaluationError("config/pool.toml is missing, so the pool shares are unknown (B18)")
    with open(path, "rb") as f:
        products = tomllib.load(f)["products"]
    seen = {}
    for name, rows in (("dev", dev_rows), ("train", train_rows)):
        for row in rows:
            seen.setdefault(row.product, {"dev": 0, "train": 0})[name] += 1
    for product, counts in seen.items():
        entry = products.get(product)
        if entry is None or entry["dev"] != counts["dev"] or entry["train"] != counts["train"]:
            raise EvaluationError(f"config/pool.toml does not match the committed lists for {product}")
    for product, entry in products.items():
        if entry["pool"] != entry["dev"] + entry["test"] + entry["train"]:
            raise EvaluationError(f"config/pool.toml: the pool of {product} is not the sum of its three sets")
    if sum(entry["test"] for entry in products.values()) != test_size:
        raise EvaluationError("config/pool.toml: the test counts do not add up to the test list")
    total = sum(entry["pool"] for entry in products.values())
    return {product: entry["pool"] / total for product, entry in products.items()}


def _quote_lengths(rows):
    lengths = [int(r["quote_end"]) - int(r["quote_start"]) for r in rows if r["decision"] == "accepted"]
    if not lengths:
        return None
    return {"median": statistics.median(lengths), "min": min(lengths), "max": max(lengths)}


def _cost_per_1000(cost, complaints):
    """Dollars per 1,000 complaints, to a hundredth of a cent."""
    if not cost:
        return None
    return str((Decimal(cost) * 1000 / complaints).quantize(Decimal("0.0001")))


def evaluate(root, set_name, version, note):
    """Score the run, write the results file, the figures and one EVAL_VERSIONS.md row. Returns the figures."""
    if set_name not in SETS:
        raise EvaluationError("only the development set is scored here. The test set waits for the final run")
    return _score(root, set_name, version, note)


def score_test_set(root, version, note):
    """B17: score the test set. Only `voc.testrun` calls this, after the run is logged and committed."""
    return _score(root, "test", version, note)


def _score(root, set_name, version, note):
    root = Path(root)
    splits_dir = root / "splits"
    run, rows = _run(root, set_name, version)
    manifest = _check_run(splits_dir, run, rows, set_name)
    lists = read_splits(splits_dir)
    dev_rows = _rows(root / DB_PATH, splits_dir, manifest["month"], set_name, set(lists[set_name]))
    train_rows = _rows(root / DB_PATH, splits_dir, manifest["month"], "train", set(lists["train"]))
    dev_for_pool = dev_rows if set_name == "dev" else _rows(root / DB_PATH, splits_dir, manifest["month"], "dev",
                                                              set(lists["dev"]))
    shares = pool_shares(root / "config" / "pool.toml", dev_for_pool, train_rows, len(lists["test"]))

    tfidf_path = root / "config" / "tfidf.toml"
    model = fit_tfidf([(r.complaint_id, "train", r.narrative, r.product) for r in train_rows],
                      load_tfidf_config(tfidf_path))
    started = time.monotonic()
    predictions = predict_tfidf(model, [r.narrative for r in dev_rows])
    tfidf_seconds = time.monotonic() - started

    by_id = {r["complaint_id"]: r for r in rows}
    items = []
    for row, (tfidf_label, confidence) in zip(dev_rows, predictions):
        result = by_id[row.complaint_id]
        items.append(metrics.Item(row.complaint_id, row.product, result["accepted_label"] or None,
                                  result["reason"] or None, tfidf_label, confidence,
                                  llm_proposed=result["proposed_label"] or None))
    labels = [label.name for label in load_labels(root / "config" / "labels.toml")]
    if not any(item.accepted for item in items):
        raise EvaluationError("the LLM accepted nothing in this run, so there is nothing to compare (B10)")
    compared = metrics.compare(items, shares, resamples=RESAMPLES, seed=SEED)
    curve, llm_point = metrics.precision_coverage(items, COVERAGE_POINTS)
    n = len(items)
    cost = run.get("cost") or {}
    figures = {
        "set": set_name, "prompt_version": version, "note": note, "backend": run["backend"], "model": run["model"],
        "settings": run["settings"], "list_sha256": run["list_sha256"], "complaints": n,
        "figures_are": TUNING if set_name == "dev" else CLAIM,
        "verdict": compared["verdict"], "difference": compared["difference"], "interval": list(compared["interval"]),
        "resamples": RESAMPLES, "seed": SEED,
        "llm": {"reweighted_accuracy": compared["llm_reweighted"], "precision": compared["llm_precision"],
                "coverage": compared["coverage"], "quarantine_rate": compared["quarantine_rate"],
                "macro_f1": metrics.prf(items, "llm", labels)["macro_f1"],
                "cost_per_1000_usd": _cost_per_1000(cost.get("live_cost_usd"), n),
                "seconds_per_1000_complaints": run.get("seconds_per_1000_complaints"),
                "no_time_per_1000_because": run.get("no_time_per_1000_because")},
        "tfidf": {"reweighted_accuracy": compared["tfidf_reweighted"], "precision": compared["tfidf_precision"],
                  "coverage": compared["coverage"], "macro_f1": metrics.prf(items, "tfidf", labels)["macro_f1"],
                  "cost_per_1000_usd": "0",
                  "settings_sha256": hashlib.sha256(tfidf_path.read_bytes()).hexdigest(),
                  "seconds_per_1000_complaints": round(metrics.per_thousand(tfidf_seconds, n), 3)},
        "per_category": ("not reported for the development set (docs/DATA.md, decision 2)" if set_name == "dev"
                         else _per_category(items, labels)),
        "confusion": {**{method: sorted([p, q, c] for (p, q), c in metrics.confusion(items, method).items())
                         for method in ("llm", "tfidf")},
                      "note": "[recorded, predicted, count]. The LLM matrix has a 'quarantined' column. The TF-IDF "
                              "matrix covers every complaint, at full coverage, not the matched coverage of the "
                              "headline figures"},
        "who_was_right": metrics.who_was_right(items),
        "precision_coverage": {"tfidf": [list(point) for point in curve], "llm": list(llm_point)},
        "review_queue": metrics.review_queue(items),
        "quote_length": _quote_lengths(rows),
        "live_cost_usd": cost.get("live_cost_usd"), "replay_cost_usd": cost.get("own_cost_usd"),
    }
    folder = root / "results" / "eval"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{version}_{set_name}.csv").write_text(_results_csv(rows, predictions, dev_rows), encoding="utf-8",
                                                       newline="")
    (folder / f"{version}_{set_name}.json").write_text(json.dumps(figures, indent=2, sort_keys=True) + "\n",
                                                        encoding="utf-8", newline="")
    if set_name == "dev":  # B15: the table holds development rows only
        _append_row(root / VERSIONS_FILE, figures)
    return figures


def _per_category(items, labels):
    """B18: per-Product figures for the test set. A Product with fewer than 30 complaints is "too few to judge"."""
    counts = {label: sum(i.product == label for i in items) for label in labels}
    llm, tfidf = metrics.prf(items, "llm", labels), metrics.prf(items, "tfidf", labels)
    return {label: ({"complaints": n, "too_few_to_judge": True} if n < TOO_FEW else
                    {"complaints": n, "llm": llm[label], "tfidf": tfidf[label]})
            for label, n in counts.items()}


def _results_csv(rows, predictions, dev_rows):
    tfidf = {row.complaint_id: p for row, p in zip(dev_rows, predictions)}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=EVAL_FIELDS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for r in sorted(rows, key=lambda r: _id_number(r["complaint_id"])):
        label, confidence = tfidf[r["complaint_id"]]
        # The exact value, so a recompute from this file breaks ties the same way (B19).
        writer.writerow({**r, "tfidf_label": label, "tfidf_confidence": repr(confidence)})
    return out.getvalue()


def _percent(value):
    return f"{value * 100:.1f}%"


def _money(value):
    return "n/a" if value is None else f"${value}"


def _append_row(path, f):
    """Add one row, never rewriting the rows before it (B15)."""
    if not path.exists():
        path.write_text(VERSIONS_INTRO + "| " + " | ".join(VERSIONS_COLUMNS) + " |\n"
                        + "|" + "---|" * len(VERSIONS_COLUMNS) + "\n", encoding="utf-8", newline="")
    low, high = f["interval"]
    q = f["quote_length"]
    cells = [datetime.now().strftime("%Y-%m-%d %H:%M"), f["prompt_version"], f["note"], f["set"],
             f["list_sha256"], f["backend"], f["model"], str(f["settings"].get("effort") or "n/a"),
             str(f["complaints"]),
             _percent(f["llm"]["reweighted_accuracy"]), _percent(f["llm"]["coverage"]),
             _percent(f["llm"]["quarantine_rate"]), _percent(f["tfidf"]["reweighted_accuracy"]),
             _percent(f["tfidf"]["coverage"]), _percent(1 - f["tfidf"]["coverage"]),
             f"{low * 100:+.1f} to {high * 100:+.1f} points",
             "n/a" if q is None else f"median {q['median']} ({q['min']} to {q['max']})",
             _money(f["live_cost_usd"]), _money(f["replay_cost_usd"])]
    cells = [cell.replace("|", "/").replace("\n", " ") for cell in cells]
    with open(path, "a", encoding="utf-8", newline="") as out:
        out.write("| " + " | ".join(cells) + " |\n")


def format_evaluation(f, root):
    llm, tfidf = f["llm"], f["tfidf"]
    low, high = f["interval"]
    verdict = f["verdict"] or "none, because some complaints were not run (budget)"
    lines = [f"evaluated prompt {f['prompt_version']} on {f['set']}: {f['complaints']} complaints, "
             f"backend {f['backend']}, model {f['model']}",
             f"these are {f['figures_are']}",
             f"LLM: re-weighted strict accuracy {_percent(llm['reweighted_accuracy'])}, precision "
             f"{_percent(llm['precision'])}, coverage {_percent(llm['coverage'])}, quarantined "
             f"{_percent(llm['quarantine_rate'])}, macro-F1 {llm['macro_f1']:.3f}",
             f"TF-IDF at the same coverage: re-weighted strict accuracy {_percent(tfidf['reweighted_accuracy'])}, "
             f"precision {_percent(tfidf['precision'])}, macro-F1 {tfidf['macro_f1']:.3f}",
             f"difference: {f['difference'] * 100:+.1f} points, 95% interval {low * 100:+.1f} to {high * 100:+.1f} "
             f"points ({f['resamples']} resamples, seed {f['seed']}), verdict: {verdict}",
             "who was right: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in f["who_was_right"].items())]
    lines += [f"  quarantined as {reason}: {q['count']}, TF-IDF right on {q['tfidf_right']}"
              for reason, q in f["review_queue"].items()]
    lines.append(f"cost per 1,000 complaints in the run: LLM {_money(llm['cost_per_1000_usd'])}, "
                 "TF-IDF $0 (no API call)")
    llm_time = (f"{llm['seconds_per_1000_complaints']} seconds" if llm["seconds_per_1000_complaints"] is not None
                else f"not measured, because {llm['no_time_per_1000_because']}")
    lines.append(f"time per 1,000 complaints: LLM {llm_time}, TF-IDF {tfidf['seconds_per_1000_complaints']} "
                 "seconds (labelling only, training left out)")
    lines.append(f"results: results/eval/{f['prompt_version']}_{f['set']}.csv, row added to {VERSIONS_FILE}")
    return "\n".join(lines)
