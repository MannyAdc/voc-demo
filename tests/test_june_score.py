"""Spec 004, J7 and J1: the June scoring and its frozen claims. All items here are synthetic."""
import json
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest

from voc import hybrid
from voc.june_score import JuneScoreError, load_claims, primary_verdict, score_june
from voc.metrics import NOT_RUN_BUDGET, Item

REPO = Path(__file__).resolve().parents[1]
COST = Decimal("0.2373")


def _item(i, product, llm=None, reason=None, tfidf=None, conf=0.5):
    return Item(f"SYN-{i}", product, llm, reason, tfidf or product, conf)


POOL = {"Mortgage": {"pool": 300, "sample": 4}, "Credit card": {"pool": 100, "sample": 2}}


def _score(items, pool=POOL):
    return score_june(items, pool, load_claims(REPO), COST)


def _mixed():
    """Mortgage: TF-IDF + LR right at 0.9, right at 0.89, a held-back LLM label, the LLM right. Credit card:
    TF-IDF + LR wrong at 0.95, the LLM right."""
    return [_item(1, "Mortgage", llm="Credit card", conf=0.9),
            _item(2, "Mortgage", llm="Credit card", conf=0.89),
            _item(3, "Mortgage", reason="quote_not_found", conf=0.5),
            _item(4, "Mortgage", llm="Mortgage", conf=0.2),
            _item(5, "Credit card", llm="Credit card", tfidf="Mortgage", conf=0.95),
            _item(6, "Credit card", llm="Credit card", conf=0.1)]


def test_J7_the_claims_are_frozen_before_any_june_label_is_scored():
    claims = load_claims(REPO)
    with open(REPO / "config" / "prompts" / "v1.toml", "rb") as f:
        prompt = tomllib.load(f)
    assert claims["model"] == "claude-haiku-5-5" == prompt["settings"]["model"] and claims["prompt"] == "v1"
    assert claims["primary"]["threshold"] == 0.9 == hybrid.THRESHOLD
    assert claims["bootstrap"] == {"resamples": 2000, "seed": 0, "within": "Product"}
    assert claims["primary"]["beats"] == "the 95% interval of the point difference is wholly above zero"
    assert claims["primary"]["does_not_beat"] == "the point difference is zero or below"
    assert claims["primary"]["inconclusive"] == "otherwise"


@pytest.mark.parametrize("difference, interval, verdict", [
    (0.02, [0.001, 0.04], "beats"),
    (0.0, [-0.01, 0.01], "does_not_beat"),
    (-0.01, [-0.03, 0.005], "does_not_beat"),
    (0.01, [-0.005, 0.03], "inconclusive"),
    (0.01, [0.0, 0.03], "inconclusive"),
])
def test_J7_the_primary_verdict_follows_the_rule_fixed_in_advance(difference, interval, verdict):
    assert primary_verdict(difference, interval) == verdict


def test_J7_scores_are_reweighted_by_junes_own_pool():
    items = [_item(1, "Mortgage", llm="Mortgage"), _item(2, "Mortgage", llm="Mortgage"),
             _item(3, "Mortgage", llm="Mortgage"), _item(4, "Mortgage", llm="Credit card"),
             _item(5, "Credit card", llm="Credit card"), _item(6, "Credit card", llm="Mortgage")]
    result = _score(items)
    assert result["shares"] == {"Credit card": 0.25, "Mortgage": 0.75}
    assert result["primary"]["llm_reweighted"] == pytest.approx(0.75 * 0.75 + 0.25 * 0.5)
    assert result["weights"] == load_claims(REPO)["weights"]


def test_J7_the_hybrid_takes_tfidf_lr_at_0_9_or_more_and_a_held_back_llm_label_counts_as_wrong():
    result = _score(_mixed())
    primary = result["primary"]
    assert primary["hybrid_reweighted"] == pytest.approx(0.75 * 2 / 4 + 0.25 * 1 / 2)
    assert primary["llm_reweighted"] == pytest.approx(0.75 * 1 / 4 + 0.25 * 2 / 2)
    assert primary["tfidf_share"] == pytest.approx(2 / 6) and primary["threshold"] == 0.9
    assert primary["claim"] == load_claims(REPO)["primary"]["claim"]


def test_J7_the_primary_verdict_is_given_both_ways():
    better = [_item(n, "Mortgage", llm="Credit card", conf=0.95) for n in range(40)]
    better += [_item(100 + n, "Credit card", llm="Mortgage", conf=0.95) for n in range(20)]
    assert _score(better)["primary"]["verdict"] == "beats"
    worse = [_item(n, "Mortgage", llm="Mortgage", tfidf="Credit card", conf=0.95) for n in range(40)]
    worse += [_item(100 + n, "Credit card", llm="Credit card", tfidf="Mortgage", conf=0.95) for n in range(20)]
    assert _score(worse)["primary"]["verdict"] == "does_not_beat"


def test_J7_the_secondary_comparison_has_its_interval_and_no_verdict():
    secondary = _score(_mixed())["secondary"]
    assert "verdict" not in secondary and len(secondary["interval"]) == 2
    assert secondary["comparison"] == load_claims(REPO)["secondary"]["comparison"]
    assert secondary["coverage"] == pytest.approx(5 / 6)


def test_J7_the_bootstrap_is_2000_draws_within_each_product_with_seed_0():
    first, second = _score(_mixed()), _score(_mixed())
    for part in ("primary", "secondary"):
        assert first[part]["resamples"] == 2000 and first[part]["seed"] == 0
        assert first[part]["interval"] == second[part]["interval"]


def test_J7_cost_per_extra_correct_label_against_tfidf_lr_in_both_views():
    result = _score(_mixed())
    full = result["full_coverage"]
    assert full["llm_reweighted"] == pytest.approx(0.75 * 1 / 4 + 0.25 * 2 / 2)
    assert full["tfidf_reweighted"] == pytest.approx(0.75 * 4 / 4 + 0.25 * 1 / 2)
    cost = result["cost_per_extra_correct_usd"]
    expected = hybrid.cost_per_extra_correct(COST, result["secondary"]["difference"])
    assert cost["same_coverage"] == (None if expected is None else f"{expected:.6f}")
    assert cost["full_coverage"] is None  # TF-IDF + LR leads when it labels every complaint, so no gain
    gain = [_item(n, "Mortgage", llm="Mortgage", tfidf="Credit card", conf=0.5) for n in range(4)]
    gain += [_item(10 + n, "Credit card", llm="Credit card", conf=0.5) for n in range(2)]
    cost = _score(gain)["cost_per_extra_correct_usd"]
    lead = 0.75
    assert cost["full_coverage"] == f"{hybrid.cost_per_extra_correct(COST, lead):.6f}"


def test_J7_the_counts_and_confusion_tables():
    result = _score(_mixed())
    assert result["complaints"] == 6 and result["accepted"] == 5 and result["quarantined"] == {"quote_not_found": 1}
    for name in ("llm", "tfidf", "hybrid"):
        table = result["confusion"][name]
        assert sum(count for _, _, count in table) == 6 and table == sorted(table)
    assert ["Mortgage", "quarantined", 1] in result["confusion"]["llm"]
    assert ["Credit card", "Mortgage", 1] in result["confusion"]["hybrid"]


def test_J1_a_run_stopped_by_the_spend_limit_is_not_scored():
    items = _mixed() + [_item(7, "Credit card", reason=NOT_RUN_BUDGET)]
    with pytest.raises(JuneScoreError, match="not scored"):
        _score(items)


def test_J7_a_pool_product_missing_from_the_items_is_refused():
    with pytest.raises(JuneScoreError, match="missing"):
        _score(_mixed(), pool={**POOL, "Student loan": {"pool": 50, "sample": 1}})


def test_J7_repeated_complaints_are_refused():
    with pytest.raises(JuneScoreError):
        _score(_mixed() + [_item(1, "Mortgage", llm="Mortgage")])


def test_B21_the_june_scores_hold_figures_and_labels_only():
    text = json.dumps(_score(_mixed()))
    assert "SYN-" not in text
