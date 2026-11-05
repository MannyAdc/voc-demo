"""Spec 004, J7: the June scores and the one primary claim, from labelled items. No model call.

The claims and their numbers come from `config/june_claims.toml`, fixed before any June label is scored (J1).
Scores are re-weighted by June's own pool after copies are removed (`splits/june/manifest.json`), so they are
not directly comparable with July's. The primary claim is the hybrid against the LLM alone, as V6 scores it
(`voc.hybrid`). The secondary comparison is the LLM against TF-IDF + LR at the same coverage, as B10 scores it
(`voc.metrics`), with its interval and no verdict. Both intervals come from the paired bootstrap within each
Product, in complaint ID order, so the order the items come in changes nothing. A win needs both a point
difference above zero and an interval wholly above zero (owner decision, 5 November).

Job B calls `score_june_sample`, which reads the pool and the list from `splits/june/`, and scores only when every
complaint of the June list has a result, Product by Product. So a run stopped by the spend limit, the quota or a
crash is not scored (J1). `score_june` does the figures.

B21: the result holds figures, labels and fixed text only, never a complaint ID or text.
"""
import csv
import hashlib
import io
import json
import tomllib
from collections import Counter
from pathlib import Path

from voc import hybrid, metrics

CLAIMS = Path("config") / "june_claims.toml"
JUNE = Path("splits") / "june"
# Reasons that mean the run stopped. Pull request 6 adds Job B's reason for a stop by the spend limit or the quota.
STOP_REASONS = (metrics.NOT_RUN_BUDGET,)


class JuneScoreError(ValueError):
    """A refusal whose message holds only counts, complaint IDs and fixed text, never complaint text (B21, J5)."""


def load_claims(root):
    with open(Path(root) / CLAIMS, "rb") as f:
        return tomllib.load(f)


def primary_verdict(difference, interval):
    """The rule fixed in advance: does not beat if the point difference is zero or below, whatever the interval.
    Otherwise beats if the 95% interval is wholly above zero, and inconclusive if not."""
    if difference <= 0:
        return "does_not_beat"
    if interval[0] > 0:
        return "beats"
    return "inconclusive"


def _hybrid_prediction(item, threshold):
    return item.tfidf_label if item.tfidf_confidence >= threshold else metrics._prediction(item, "llm")


def _table(counts):
    return sorted([recorded, predicted, count] for (recorded, predicted), count in counts.items())


def score_june_sample(root, items, cost_per_1000):
    """The June figures for the frozen June list, from the pool in its manifest. Refused unless every complaint of
    the list has exactly one result and the complaints per Product match the manifest (J1)."""
    folder = Path(root) / JUNE
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    data = (folder / "june.csv").read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["lists"]["june"]["sha256"]:
        raise JuneScoreError("splits/june/june.csv does not match its hash in splits/june/manifest.json")
    listed = [row[0] for row in list(csv.reader(io.StringIO(data.decode("utf-8"))))[1:]]
    products = manifest["products"]
    if sum(counts["pool"] for counts in products.values()) != manifest["pool"]:
        raise JuneScoreError("the Products' pool counts in the June manifest do not add up to its pool")
    if not sum(counts["sample"] for counts in products.values()) == len(listed) == manifest["lists"]["june"]["count"]:
        raise JuneScoreError("the Products' sample counts in the June manifest do not add up to the June list")
    given = [item.complaint_id for item in items]
    if len(given) != len(set(given)):
        raise JuneScoreError("the items must describe distinct complaints")
    extra, missing = set(given) - set(listed), set(listed) - set(given)
    if extra:
        raise JuneScoreError(f"{len(extra)} complaints are not in the June list")
    if missing:
        raise JuneScoreError(f"{len(missing)} of {len(listed)} June complaints have no result, so the run is not "
                             "scored (J1)")
    if dict(Counter(item.product for item in items)) != {p: c["sample"] for p, c in products.items() if c["sample"]}:
        raise JuneScoreError("the complaints per Product differ from the June manifest")
    return score_june(items, products, load_claims(root), cost_per_1000)


def score_june(items, pool, claims, cost_per_1000):
    """The June figures. `pool` is the manifest's Products, each with its pool count after copies are removed.
    Job B calls `score_june_sample`, which takes the pool from the manifest."""
    if any(item.llm_reason in STOP_REASONS for item in items):
        raise JuneScoreError("the run stopped before every complaint was labelled, so it is not scored (J1)")
    if any(item.synthetic for item in items):
        raise JuneScoreError("synthetic items are never part of the June sample")
    outside = {item.product for item in items} - set(pool)
    if outside:
        raise JuneScoreError(f"{len(outside)} Products of the items are not in the June pool")
    if claims["bootstrap"]["within"] != "Product":
        raise JuneScoreError("the claims must resample within each Product, as B10 does")
    items = sorted(items, key=lambda item: (metrics._id_number(item.complaint_id), item.complaint_id))
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
