"""V6: cost against gain, and one hybrid (specs/003-validation-review/spec.md). No model call.

- Cost per extra correct label against TF-IDF with logistic regression (TF-IDF + LR, `voc.baselines`): each
  run's cost per 1,000 complaints over its lead in re-weighted points per 1,000, in two views. At the same
  coverage, the headline rule fixed before the first run (B10): TF-IDF + LR answers only as many complaints as
  the LLM accepted. And with TF-IDF + LR labelling every complaint. A lead in re-weighted points only approximates extra correct labels per 1,000. The test figures
  come from the test run's published summary, `results/eval/v1_test.json`, only, never a per-complaint test
  file (V7). The development figures are tuning figures (B10).
- Time per 1,000 at scale: an estimate, labelled as one. The test run's time per 1,000, whose calls were all
  live and sent one at a time, over an assumed number of calls in parallel. No paid run measures it.
- The hybrid, fixed in advance of its run: TF-IDF + LR answers when its top class probability is at least 0.9,
  otherwise the LLM's answer is used, and a quarantined LLM answer counts as wrong. One rule for every product.
  It is scored on the development set only, as B10 scores, against the LLM alone, with the paired bootstrap
  drawn within each product. It is exploratory and optimistic: the prompt was tuned on the same set, the 0.9
  was fixed after the development results were published, and no untouched test set is left to check it.

Only figures are written or printed (B21). Reader-facing text says "TF-IDF + LR" (owner decision, 4 November).
Data keys such as `tfidf_share` keep their names.
"""
import csv
import json
import tomllib
from decimal import Decimal
from pathlib import Path

from voc import metrics

THRESHOLD = 0.9
PARALLEL = (10, 50)
RESAMPLES = 2000
SEED = 0
QUARANTINED = "quarantined"
HYBRID_IS = ("exploratory and optimistic: the prompt was tuned on this set, the 0.9 threshold was fixed on "
             "2 November, after the development results were published on 29 October, and no untouched test "
             "set is left to check it")
COST_NOTE = ("each run's cost per 1,000 complaints over its lead in re-weighted points per 1,000, against TF-IDF "
             "with logistic regression (TF-IDF + LR) at the same coverage (the headline rule, B10) and against "
             "TF-IDF + LR labelling every complaint. A lead in re-weighted points only approximates extra correct "
             "labels per 1,000")


def hybrid_answers(items, threshold=THRESHOLD):
    """For each item, whether the hybrid's answer is right, and which method gave it."""
    right, by = [], []
    for item in items:
        if item.tfidf_confidence >= threshold:
            right.append(item.tfidf_right)
            by.append("tfidf")
        else:
            right.append(item.llm_right)
            by.append("llm")
    return right, by


def compare_hybrid(items, shares, threshold=THRESHOLD, resamples=RESAMPLES, seed=SEED):
    """The hybrid against the LLM alone, as B10 scores: re-weighted strict accuracy, and a 95% interval of the
    difference from a paired bootstrap drawn within each product."""
    import numpy as np

    items = metrics._real(items)  # refuses repeated complaints and unusable confidences, as `compare` does
    missing = sorted(set(shares) - {i.product for i in items})
    if missing:
        raise ValueError(f"pool Products missing from the items: {len(missing)} of {len(shares)}")

    def score(sample):
        right, by = hybrid_answers(sample, threshold)
        llm = metrics._reweighted(sample, [i.llm_right for i in sample], shares)
        return llm, metrics._reweighted(sample, right, shares), by

    llm, hyb, by = score(items)
    groups = {}
    for n, item in enumerate(items):
        groups.setdefault(item.product, []).append(n)
    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(resamples):
        picked = [n for members in groups.values() for n in rng.choice(members, size=len(members), replace=True)]
        s_llm, s_hyb, _ = score([items[n] for n in picked])
        differences.append(s_hyb - s_llm)
    low, high = (float(v) for v in np.percentile(differences, [2.5, 97.5]))
    return {"llm_reweighted": llm, "hybrid_reweighted": hyb, "difference": hyb - llm, "interval": [low, high],
            "tfidf_share": by.count("tfidf") / len(items), "threshold": threshold, "resamples": resamples,
            "seed": seed}


def full_coverage_from_confusion(confusion, shares):
    """The LLM's and TF-IDF's re-weighted strict accuracy from a run's confusion tables of
    [recorded, predicted, count], where TF-IDF labels every complaint and a quarantined LLM answer is wrong."""

    def reweighted(rows):
        by_product = {}
        for recorded, predicted, count in rows:
            total, right = by_product.get(recorded, (0, 0))
            by_product[recorded] = (total + count, right + (count if predicted == recorded else 0))
        weight = sum(shares[p] for p in by_product)
        return sum(shares[p] / weight * right / total for p, (total, right) in by_product.items())

    return reweighted(confusion["llm"]), reweighted(confusion["tfidf"])


def cost_per_extra_correct(cost_per_1000, difference):
    """Dollars per extra correct label: the cost per 1,000 over the extra correct labels per 1,000. None when the
    LLM gains nothing."""
    if difference is None or difference <= 0:
        return None
    return Decimal(str(cost_per_1000)) / (Decimal(str(difference)) * 1000)


def time_at_scale(seconds_per_1000, parallel):
    """An estimate: the time per 1,000 if the calls ran this many at a time, ignoring any rate limit."""
    return seconds_per_1000 / parallel


def _summary(root, name):
    return json.loads((Path(root) / "results" / "eval" / f"v1_{name}.json").read_text(encoding="utf-8"))


def _pool_shares(root):
    with open(Path(root) / "config" / "pool.toml", "rb") as f:
        products = tomllib.load(f)["products"]
    total = sum(entry["pool"] for entry in products.values())
    return {product: entry["pool"] / total for product, entry in products.items()}


def _items(root):
    """The development items: the committed LLM and TF-IDF answers, and the recorded product from the staged
    table, checked against the development list."""
    from voc.data import _manifest, read_splits
    from voc.evaluate import _rows, pool_shares
    from voc.load import DB_PATH

    root = Path(root)
    splits = root / "splits"
    lists = read_splits(splits)
    month = _manifest(splits)["month"]
    dev_rows = _rows(root / DB_PATH, splits, month, "dev", set(lists["dev"]))
    train_rows = _rows(root / DB_PATH, splits, month, "train", set(lists["train"]))
    shares = pool_shares(root / "config" / "pool.toml", dev_rows, train_rows, len(lists["test"]))
    products = {r.complaint_id: r.product for r in dev_rows}
    with open(root / "results" / "eval" / "v1_dev.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = [r["complaint_id"] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(products):
        raise ValueError("results/eval/v1_dev.csv does not hold each development complaint exactly once")
    items = [metrics.Item(r["complaint_id"], products[r["complaint_id"]], r["accepted_label"] or None,
                          r["reason"] or None, r["tfidf_label"], float(r["tfidf_confidence"])) for r in rows]
    return items, shares


def _views(cost_per_1000, same, full):
    return {"same_coverage": _money(cost_per_extra_correct(cost_per_1000, same)),
            "full_coverage": _money(cost_per_extra_correct(cost_per_1000, full)),
            "lead_points": {"same_coverage": round(same * 100, 2), "full_coverage": round(full * 100, 2)}}


def run(root):
    """`voc cost-hybrid`. Writes `results/validation/v6_cost_hybrid.json` and returns the lines to print."""
    root = Path(root)
    test, dev = _summary(root, "test"), _summary(root, "dev")
    items, shares = _items(root)
    compared = compare_hybrid(items, shares)
    test_llm, test_tfidf = full_coverage_from_confusion(test["confusion"], _pool_shares(root))
    dev_llm = metrics._reweighted(items, [i.llm_right for i in items], shares)
    dev_tfidf = metrics._reweighted(items, [i.tfidf_right for i in items], shares)
    dev_cost = Decimal(str(dev["llm"]["cost_per_1000_usd"]))
    seconds = test["llm"]["seconds_per_1000_complaints"]
    figures = {
        "cost_per_extra_correct_usd": {
            "test": _views(test["llm"]["cost_per_1000_usd"], test["difference"], test_llm - test_tfidf),
            "dev": {**_views(dev_cost, dev["difference"], dev_llm - dev_tfidf),
                    "figures_are": "tuning figures, development set (B10)"},
            "note": COST_NOTE,
            "from": "results/eval/v1_test.json (its difference and confusion tables), v1_dev.json and v1_dev.csv"},
        "time_at_scale": {"is": "an estimate, not measured",
                          "measured_seconds_per_1000": seconds,
                          "seconds_per_1000": {str(n): round(time_at_scale(seconds, n), 1) for n in PARALLEL},
                          "assumes": "the test run's calls, sent one at a time, run this many at a time, with no "
                                     "rate limit"},
        "hybrid": {**compared, "set": "dev", "is": HYBRID_IS,
                   "llm_cost_per_1000_usd": str(dev_cost),
                   "hybrid_llm_cost_per_1000_usd": _money(dev_cost * Decimal(str(1 - compared["tfidf_share"]))),
                   "hybrid_llm_cost_assumes": "every complaint costs the same to label, so the LLM's cost falls by "
                                              "the share TF-IDF + LR answers"},
    }
    path = root / "results" / "validation" / "v6_cost_hybrid.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(figures, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return format_figures(figures) + [f"written to {path.relative_to(root).as_posix()}"]


def _money(value):
    return None if value is None else f"{value:.6f}"


def _dollars(value):
    return f"${value}" if value else "no gain"


def format_figures(figures):
    cost, time_, hyb = figures["cost_per_extra_correct_usd"], figures["time_at_scale"], figures["hybrid"]
    low, high = hyb["interval"]
    lines = []
    for name, label in (("test", "test set"), ("dev", "development set, tuning figures")):
        view = cost[name]
        lead = view["lead_points"]
        lines.append(f"cost per extra correct label, {label}: {_dollars(view['same_coverage'])} against TF-IDF + LR "
                     f"at the same coverage (lead {lead['same_coverage']:+.2f} points), "
                     f"{_dollars(view['full_coverage'])} against TF-IDF + LR labelling every complaint "
                     f"(lead {lead['full_coverage']:+.2f} points)")
    lines += ["time per 1,000 at scale, an estimate: " + ", ".join(
                  f"{s} seconds with {n} calls at a time" for n, s in time_["seconds_per_1000"].items()),
              f"hybrid (TF-IDF + LR at {hyb['threshold']} or more, else the LLM), exploratory and optimistic, "
              f"development set only: {hyb['hybrid_reweighted']:.1%} against the LLM alone "
              f"{hyb['llm_reweighted']:.1%}, difference {hyb['difference'] * 100:+.1f} points (95% interval "
              f"{low * 100:+.1f} to {high * 100:+.1f})",
              f"TF-IDF + LR answers {hyb['tfidf_share']:.1%}, so the LLM cost per 1,000 would be "
              f"${hyb['hybrid_llm_cost_per_1000_usd']} instead of ${hyb['llm_cost_per_1000_usd']}, if every "
              "complaint costs the same"]
    return lines
