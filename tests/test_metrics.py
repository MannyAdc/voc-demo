"""B3, B10, B18, B23: honest scoring of the LLM against TF-IDF. Hand-countable synthetic cases."""
import pytest

from voc.metrics import (Item, compare, confusion, injection_report, per_thousand, precision_coverage,
                         prf, review_queue, strict_accuracy, tfidf_answered, who_was_right)


def _item(i, product, llm=None, reason=None, tfidf=None, conf=0.5, **kw):
    return Item(complaint_id=f"SYN-{i:03d}", product=product, llm_label=llm, llm_reason=reason,
                tfidf_label=tfidf or product, tfidf_confidence=conf, **kw)


def _set():
    """10 items, two products. The LLM accepts 8 (7 right), quarantines 2."""
    items = [
        _item(1, "A", llm="A", conf=0.9), _item(2, "A", llm="A", conf=0.8), _item(3, "A", llm="A", conf=0.7),
        _item(4, "A", llm="B", tfidf="B", conf=0.95), _item(5, "A", reason="quote_not_in_text", conf=0.2),
        _item(6, "B", llm="B", conf=0.6), _item(7, "B", llm="B", tfidf="A", conf=0.99),
        _item(8, "B", llm="B", conf=0.4), _item(9, "B", llm="B", conf=0.3),
        _item(10, "B", reason="unparseable", tfidf="A", conf=0.1),
    ]
    return items


SHARES = {"A": 0.5, "B": 0.5}


def test_B3_quarantine_counts_as_wrong_in_the_strict_figure():
    assert strict_accuracy(_set()) == pytest.approx(7 / 10)


def test_B3_nothing_accepted_gives_zero_strict_accuracy():
    items = [_item(1, "A", reason="unparseable"), _item(2, "B", reason="quote_empty")]
    assert strict_accuracy(items) == 0.0


def test_B10_a_summary_of_nothing_is_an_error():
    with pytest.raises(ValueError):
        strict_accuracy([])


def test_B10_tfidf_answers_its_most_confident_share_with_ties_broken_by_complaint_id():
    items = [_item(3, "A", conf=0.5), _item(1, "A", conf=0.5), _item(2, "A", conf=0.9), _item(4, "A", conf=0.1)]
    assert tfidf_answered(items, 2) == {"SYN-002", "SYN-001"}


def test_B10_the_baseline_needs_a_coverage_that_keeps_at_least_one_item():
    with pytest.raises(ValueError):
        tfidf_answered(_set(), 0)


def test_B18_reweighted_strict_accuracy_matches_a_hand_count():
    # A: 3 of 5 right (item 4 wrong, item 5 quarantined). B: 4 of 5 right (item 10 quarantined).
    result = compare(_set(), {"A": 0.25, "B": 0.75}, resamples=50, seed=1)
    assert result["llm_reweighted"] == pytest.approx(0.25 * 3 / 5 + 0.75 * 4 / 5)


def test_B10_tfidf_is_scored_at_the_llms_coverage():
    # The LLM accepts 8. TF-IDF answers its 8 most confident: all but items 10 (0.1) and 5 (0.2).
    # Of those 8, TF-IDF is right on 1, 2, 3, 6, 8, 9 (6 items). Item 4 and 7 are wrong.
    result = compare(_set(), SHARES, resamples=50, seed=1)
    assert result["coverage"] == pytest.approx(0.8)
    assert result["tfidf_reweighted"] == pytest.approx(0.5 * 3 / 5 + 0.5 * 3 / 5)


def _clear_win():
    items = []
    for p in ("A", "B"):
        for i in range(40):
            n = len(items)
            items.append(_item(n, p, llm=p, tfidf="B" if p == "A" and i % 2 else ("A" if i % 2 else p), conf=0.5))
    return items


def test_B10_a_clear_win_is_beats():
    assert compare(_clear_win(), SHARES, resamples=300, seed=1)["verdict"] == "beats"


def test_B10_a_tie_is_not_a_win():
    items = [_item(i, "A" if i < 20 else "B", llm="A" if i < 20 else "B", conf=0.5) for i in range(40)]
    assert compare(items, SHARES, resamples=200, seed=1)["verdict"] == "does_not_beat"


def test_B10_a_loss_is_does_not_beat():
    items = [_item(i, "A", llm="B", conf=0.5) for i in range(20)] + [_item(20 + i, "B", llm="A", conf=0.5)
                                                                     for i in range(20)]
    assert compare(items, SHARES, resamples=200, seed=1)["verdict"] == "does_not_beat"


def test_B10_a_small_positive_difference_with_a_wide_interval_is_inconclusive():
    items = [_item(0, "A", llm="A", tfidf="B")] + [_item(i, "A" if i % 2 else "B", llm="A" if i % 2 else "B")
                                                   for i in range(1, 12)]
    result = compare(items, SHARES, resamples=500, seed=1)
    assert result["difference"] > 0 and result["verdict"] == "inconclusive"


def test_B10_the_same_seed_gives_the_same_result():
    assert compare(_set(), SHARES, resamples=200, seed=7) == compare(_set(), SHARES, resamples=200, seed=7)


def test_B10_the_interval_is_for_the_reweighted_difference_and_holds_it():
    result = compare(_clear_win(), SHARES, resamples=300, seed=1)
    low, high = result["interval"]
    assert low <= result["difference"] <= high


def test_B10_the_bootstrap_resamples_within_each_product():
    # With only one product present in A's stratum, every resample keeps 40 A and 40 B items.
    result = compare(_clear_win(), SHARES, resamples=100, seed=3, keep_samples=True)
    assert all(counts == {"A": 40, "B": 40} for counts in result["sample_counts"])


def test_B10_inputs_must_describe_distinct_complaints():
    items = _set() + [_item(1, "A", llm="A")]
    with pytest.raises(ValueError):
        compare(items, SHARES, resamples=10, seed=1)


def test_B10_a_pipeline_that_accepts_nothing_cannot_be_compared():
    items = [_item(i, "A", reason="unparseable") for i in range(5)]
    with pytest.raises(ValueError):
        compare(items, {"A": 1.0}, resamples=10, seed=1)


def test_B10_a_run_with_a_not_run_budget_complaint_gets_no_verdict():
    items = _set() + [_item(11, "A", reason="not_run_budget")]
    assert compare(items, SHARES, resamples=50, seed=1)["verdict"] is None


def test_B23_the_confusion_matrices_match_a_hand_count():
    assert confusion(_set(), "llm") == {("A", "A"): 3, ("A", "B"): 1, ("A", "quarantined"): 1,
                                        ("B", "B"): 4, ("B", "quarantined"): 1}
    assert confusion(_set(), "tfidf") == {("A", "A"): 4, ("A", "B"): 1, ("B", "B"): 3, ("B", "A"): 2}


def test_B23_per_product_precision_recall_f1_and_macro_f1_match_a_hand_count():
    scores = prf(_set(), "llm", ["A", "B"])
    # A: predicted A 3 times, all right. 5 true A. B: predicted B 5 times, 4 right. 5 true B.
    assert scores["A"]["precision"] == pytest.approx(1.0) and scores["A"]["recall"] == pytest.approx(0.6)
    assert scores["B"]["precision"] == pytest.approx(0.8) and scores["B"]["recall"] == pytest.approx(0.8)
    f1_a, f1_b = 2 * 1.0 * 0.6 / 1.6, 0.8
    assert scores["macro_f1"] == pytest.approx((f1_a + f1_b) / 2)


def test_B23_the_who_was_right_table_counts_correctly_at_matched_coverage():
    # LLM right: 1, 2, 3, 6, 7, 8, 9. TF-IDF right among its 8 answered: 1, 2, 3, 6, 8, 9.
    assert who_was_right(_set()) == {"both": 6, "only_llm": 1, "only_tfidf": 0, "neither": 3}


def test_B23_the_precision_and_coverage_points_match_a_hand_count():
    curve, llm_point = precision_coverage(_set(), [0.5, 1.0])
    # Top 5 by confidence: 7 (wrong), 4 (wrong), 1, 2, 3 (right): precision 3/5.
    assert curve == [(0.5, pytest.approx(0.6)), (1.0, pytest.approx(0.7))]
    assert llm_point == (pytest.approx(0.8), pytest.approx(7 / 8))


def test_B23_the_review_queue_breakdown_matches_a_hand_count():
    assert review_queue(_set()) == {"quote_not_in_text": {"count": 1, "tfidf_right": 1},
                                    "unparseable": {"count": 1, "tfidf_right": 0}}


def test_B23_cost_and_run_time_are_reported_per_1000_complaints():
    assert per_thousand(0.25, 500) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        per_thousand(1.0, 0)


def test_B10_synthetic_items_are_reported_apart_and_never_enter_accuracy():
    items = _set() + [_item(50, "A", llm="B", synthetic=True, forced_label="B")]
    assert compare(items, SHARES, resamples=50, seed=1) == compare(_set(), SHARES, resamples=50, seed=1)


def test_B10_the_injection_report_matches_a_hand_count():
    items = [
        _item(60, "A", llm="B", synthetic=True, forced_label="B"),
        _item(61, "A", reason="quote_not_in_text", llm_proposed="B", synthetic=True, forced_label="B"),
        _item(62, "A", llm="A", synthetic=True, forced_label="B"),
    ]
    assert injection_report(items) == {"obeyed_and_accepted": 1, "obeyed_and_quarantined": 1, "not_obeyed": 1}
