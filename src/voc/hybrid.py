"""V6: cost against gain, and one hybrid (specs/003-validation-review/spec.md). No model call.

- Cost per extra correct label against the baseline: each run's cost per 1,000 complaints over its lead in
  re-weighted points per 1,000. The test figures come from the test run's published summary,
  `results/eval/v1_test.json`, only, never a per-complaint test file (V7).
- Time per 1,000 at scale: an estimate, labelled as one. The test run's time per 1,000, whose calls were all
  live and sent one at a time, over an assumed number of calls in parallel. No paid run measures it.
- The hybrid, fixed in advance: TF-IDF answers when its top class probability is at least 0.9, otherwise the
  LLM's answer is used, and a quarantined LLM answer counts as wrong. One rule for every product. It is scored
  on the development set only, as B10 scores, against the LLM alone, with the paired bootstrap drawn within each
  product. It is exploratory and optimistic: the prompt was tuned on the same set, and no untouched test set
  is left to check it.

Only figures are written or printed (B21).
"""
import csv
import json
from decimal import Decimal
from pathlib import Path

from voc import metrics

THRESHOLD = 0.9
PARALLEL = (10, 50)
RESAMPLES = 2000
SEED = 0


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
    if {r["complaint_id"] for r in rows} != set(products):
        raise ValueError("results/eval/v1_dev.csv does not cover exactly the development list")
    items = [metrics.Item(r["complaint_id"], products[r["complaint_id"]], r["accepted_label"] or None,
                          r["reason"] or None, r["tfidf_label"], float(r["tfidf_confidence"])) for r in rows]
    return items, shares


def run(root):
    """`voc cost-hybrid`. Writes `results/validation/v6_cost_hybrid.json` and returns the lines to print."""
    root = Path(root)
    test, dev = _summary(root, "test"), _summary(root, "dev")
    items, shares = _items(root)
    compared = compare_hybrid(items, shares)
    dev_cost = Decimal(str(dev["llm"]["cost_per_1000_usd"]))
    seconds = test["llm"]["seconds_per_1000_complaints"]
    figures = {
        "cost_per_extra_correct_usd": {
            "test": _money(cost_per_extra_correct(test["llm"]["cost_per_1000_usd"], test["difference"])),
            "dev": _money(cost_per_extra_correct(dev["llm"]["cost_per_1000_usd"], dev["difference"])),
            "from": "results/eval/v1_test.json and v1_dev.json: cost per 1,000 over the lead in re-weighted "
                    "points per 1,000"},
        "time_at_scale": {"is": "an estimate, not measured",
                          "measured_seconds_per_1000": seconds,
                          "seconds_per_1000": {str(n): round(time_at_scale(seconds, n), 1) for n in PARALLEL},
                          "assumes": "the test run's calls, sent one at a time, run this many at a time, with no "
                                     "rate limit"},
        "hybrid": {**compared, "set": "dev", "is": "exploratory and optimistic: the prompt was tuned on this set, "
                                                   "and no untouched test set is left to check it",
                   "llm_cost_per_1000_usd": str(dev_cost),
                   "hybrid_llm_cost_per_1000_usd": _money(dev_cost * Decimal(str(1 - compared["tfidf_share"])))},
    }
    path = root / "results" / "validation" / "v6_cost_hybrid.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(figures, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return format_figures(figures) + [f"written to {path.relative_to(root).as_posix()}"]


def _money(value):
    return None if value is None else f"{value:.6f}"


def format_figures(figures):
    cost, time_, hyb = figures["cost_per_extra_correct_usd"], figures["time_at_scale"], figures["hybrid"]
    low, high = hyb["interval"]
    return [f"cost per extra correct label: ${cost['test']} on the test set, "
            f"{'$' + cost['dev'] if cost['dev'] else 'no gain'} on the development set",
            "time per 1,000 at scale, an estimate: " + ", ".join(
                f"{s} seconds with {n} calls at a time" for n, s in time_["seconds_per_1000"].items()),
            f"hybrid (TF-IDF at {hyb['threshold']} or more, else the LLM), exploratory, development set only: "
            f"{hyb['hybrid_reweighted']:.1%} against the LLM alone {hyb['llm_reweighted']:.1%}, difference "
            f"{hyb['difference'] * 100:+.1f} points (95% interval {low * 100:+.1f} to {high * 100:+.1f})",
            f"TF-IDF answers {hyb['tfidf_share']:.1%}, so the LLM cost per 1,000 would be "
            f"${hyb['hybrid_llm_cost_per_1000_usd']} instead of ${hyb['llm_cost_per_1000_usd']}"]
