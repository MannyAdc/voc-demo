"""Spec 004, J7: the June scores and the one primary claim, from labelled items. No model call.

The claims and their numbers come from `config/june_claims.toml`, fixed before any June label is scored (J1).
Scores are re-weighted by June's own pool after copies are removed (`splits/june/manifest.json`), so they are
not directly comparable with July's. The primary claim is the hybrid against the LLM alone, as V6 scores it
(`voc.hybrid`). The secondary comparison is the LLM against TF-IDF + LR at the same coverage, as B10 scores it
(`voc.metrics`), with its interval and no verdict. Both intervals come from the paired bootstrap within each
Product. A run stopped by the spend limit or the quota is not scored (J1).

B21: the result holds figures, labels and fixed text only, never a complaint ID or text.
"""
import tomllib
from collections import Counter
from pathlib import Path

from voc import hybrid, metrics

CLAIMS = Path("config") / "june_claims.toml"


class JuneScoreError(ValueError):
    """A refusal whose message holds only counts and fixed text (B21)."""


def load_claims(root):
    with open(Path(root) / CLAIMS, "rb") as f:
        return tomllib.load(f)


def primary_verdict(difference, interval):
    """The rule fixed in advance: beats if the interval is wholly above zero, does not beat if the point difference
    is zero or below, otherwise inconclusive."""
    if interval[0] > 0:
        return "beats"
    if difference <= 0:
        return "does_not_beat"
    return "inconclusive"


def _hybrid_prediction(item, threshold):
    return item.tfidf_label if item.tfidf_confidence >= threshold else metrics._prediction(item, "llm")


def _table(counts):
    return sorted([recorded, predicted, count] for (recorded, predicted), count in counts.items())


def score_june(items, pool, claims, cost_per_1000):
    """The June figures. `pool` is the manifest's Products, each with its pool count after copies are removed."""
    if any(item.llm_reason == metrics.NOT_RUN_BUDGET for item in items):
        raise JuneScoreError("the run stopped before every complaint was labelled, so it is not scored (J1)")
    total = sum(counts["pool"] for counts in pool.values())
    shares = {product: counts["pool"] / total for product, counts in sorted(pool.items())}
    bootstrap, primary = claims["bootstrap"], claims["primary"]
    threshold = primary["threshold"]
    try:
        first = hybrid.compare_hybrid(items, shares, threshold=threshold, resamples=bootstrap["resamples"],
                                      seed=bootstrap["seed"])
        second = metrics.compare(items, shares, resamples=bootstrap["resamples"], seed=bootstrap["seed"])
    except ValueError as err:  # our own messages, counts and fixed text only
        raise JuneScoreError(str(err)) from None
    second.pop("verdict")
    llm_full = metrics._reweighted(items, [i.llm_right for i in items], shares)
    tfidf_full = metrics._reweighted(items, [i.tfidf_right for i in items], shares)
    return {
        "complaints": len(items),
        "accepted": sum(i.accepted for i in items),
        "quarantined": dict(sorted(Counter(i.llm_reason for i in items if not i.accepted).items())),
        "weights": claims["weights"],
        "shares": shares,
        "primary": {**first, "claim": primary["claim"],
                    "verdict": primary_verdict(first["difference"], first["interval"])},
        "secondary": {**second, "interval": list(second["interval"]),
                      "comparison": claims["secondary"]["comparison"]},
        "full_coverage": {"llm_reweighted": llm_full, "tfidf_reweighted": tfidf_full,
                          "difference": llm_full - tfidf_full},
        "cost_per_extra_correct_usd": {
            "same_coverage": hybrid._money(hybrid.cost_per_extra_correct(cost_per_1000, second["difference"])),
            "full_coverage": hybrid._money(hybrid.cost_per_extra_correct(cost_per_1000, llm_full - tfidf_full)),
            "note": claims["cost"]["per_extra_correct"]},
        "confusion": {"llm": _table(metrics.confusion(items, "llm")),
                      "tfidf": _table(metrics.confusion(items, "tfidf")),
                      "hybrid": _table(Counter((i.product, _hybrid_prediction(i, threshold)) for i in items))},
    }
