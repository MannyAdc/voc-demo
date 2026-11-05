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


# The review of #89: the sample is scored only when complete, from the manifest's pool, and a win needs both tests.


def _project(tmp_path, items, pool=None):
    """A root with the frozen claims and a June list and manifest made from these items."""
    import hashlib

    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    (root / "config" / "june_claims.toml").write_bytes((REPO / "config" / "june_claims.toml").read_bytes())
    folder = root / "splits" / "june"
    folder.mkdir(parents=True)
    data = ("complaint_id,content_hash\n" + "".join(f"{i.complaint_id},{'0' * 64}\n" for i in items)).encode("utf-8")
    (folder / "june.csv").write_bytes(data)
    counts = {}
    for i in items:
        counts[i.product] = counts.get(i.product, 0) + 1
    products = {p: {"pool": (pool or {}).get(p, 100 * n), "sample": n} for p, n in counts.items()}
    manifest = {"month": "june_2026", "pool": sum(c["pool"] for c in products.values()), "products": products,
                "lists": {"june": {"count": len(items), "sha256": hashlib.sha256(data).hexdigest()}}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_J1_the_sample_is_scored_only_when_every_complaint_has_a_result(tmp_path):
    from voc.june_score import score_june_sample

    root = _project(tmp_path, _mixed())
    assert score_june_sample(root, _mixed(), COST)["complaints"] == 6
    with pytest.raises(JuneScoreError, match="not scored"):
        score_june_sample(root, _mixed()[:-1], COST)


def test_J1_items_outside_the_june_list_are_refused(tmp_path):
    from voc.june_score import score_june_sample

    root = _project(tmp_path, _mixed())
    items = _mixed()[:-1] + [_item(99, "Credit card", llm="Credit card")]
    with pytest.raises(JuneScoreError, match="June list"):
        score_june_sample(root, items, COST)


def test_J1_a_product_count_that_differs_from_the_manifest_is_refused(tmp_path):
    from voc.june_score import score_june_sample

    root = _project(tmp_path, _mixed())
    items = _mixed()[:-1] + [_item(6, "Mortgage", llm="Mortgage")]
    with pytest.raises(JuneScoreError, match="manifest"):
        score_june_sample(root, items, COST)


def test_J1_a_june_list_that_does_not_match_its_manifest_is_refused(tmp_path):
    from voc.june_score import score_june_sample

    root = _project(tmp_path, _mixed())
    path = root / "splits" / "june" / "june.csv"
    path.write_bytes(path.read_bytes() + b"SYN-77," + b"0" * 64 + b"\n")
    with pytest.raises(JuneScoreError, match="does not match"):
        score_june_sample(root, _mixed(), COST)


def test_J7_the_sample_is_weighted_by_the_manifests_pool(tmp_path):
    from voc.june_score import score_june_sample

    root = _project(tmp_path, _mixed(), pool={"Mortgage": 300, "Credit card": 100})
    result = score_june_sample(root, _mixed(), COST)
    assert result["shares"] == {"Credit card": 0.25, "Mortgage": 0.75}
    assert result == _score(_mixed())


def test_J7_a_pool_that_does_not_add_up_is_refused(tmp_path):
    from voc.june_score import score_june_sample

    root = _project(tmp_path, _mixed())
    path = root / "splits" / "june" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["pool"] += 1
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(JuneScoreError, match="pool"):
        score_june_sample(root, _mixed(), COST)


def test_J7_synthetic_items_are_refused():
    items = _mixed()[:-1] + [Item("SYN-6", "Credit card", "Credit card", None, "Credit card", 0.1, synthetic=True)]
    with pytest.raises(JuneScoreError, match="synthetic"):
        _score(items)


def test_J7_a_product_outside_the_pool_is_refused_not_a_crash():
    with pytest.raises(JuneScoreError, match="pool"):
        _score(_mixed() + [_item(7, "Student loan", llm="Student loan")])


def test_J7_the_scores_do_not_depend_on_the_order_of_the_items():
    def item(n):
        product = "Mortgage" if n % 3 else "Credit card"
        other = "Credit card" if product == "Mortgage" else "Mortgage"
        return _item(n, product, llm=product if n % 5 else other, tfidf=product if n % 2 == 0 else other,
                     conf=0.95 if n % 4 == 0 else 0.5)

    items = [item(n) for n in range(60)]
    assert _score(list(reversed(items))) == _score(items)


@pytest.mark.parametrize("difference, interval", [(0.0, [0.001, 0.02]), (-0.001, [0.0005, 0.01])])
def test_J7_a_win_needs_a_point_difference_above_zero_whatever_the_interval(difference, interval):
    assert primary_verdict(difference, interval) == "does_not_beat"


def test_J7_the_claims_say_does_not_beat_wins_when_both_tests_apply():
    rule = load_claims(REPO)["primary"]["rule"]
    assert rule == ("a win needs both a point difference above zero and a 95% interval wholly above zero. When the "
                    "point difference is zero or below, the verdict is does not beat, whatever the interval")


def test_J7_the_bootstrap_draws_2000_times_within_each_product(monkeypatch):
    import numpy

    real = numpy.random.default_rng
    calls = []

    class Spy:
        def __init__(self, seed):
            self.seed, self.rng = seed, real(seed)

        def choice(self, members, size, replace):
            calls.append((self.seed, len(members), size, replace))
            return self.rng.choice(members, size=size, replace=replace)

    monkeypatch.setattr(numpy.random, "default_rng", Spy)
    _score(_mixed())
    # Two bootstraps, the primary and the secondary, of 2,000 draws each, one draw per Product of its own size.
    assert len(calls) == 2 * 2000 * 2
    assert set(calls) == {(0, 4, 4, True), (0, 2, 2, True)}


def test_J7_claims_that_resample_other_than_within_products_are_refused():
    claims = load_claims(REPO)
    claims["bootstrap"] = {**claims["bootstrap"], "within": "Issue"}
    with pytest.raises(JuneScoreError, match="within"):
        score_june(_mixed(), POOL, claims, COST)
