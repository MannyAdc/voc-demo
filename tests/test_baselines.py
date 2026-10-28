"""B11: two baselines, set up fairly. All text here is synthetic."""
from pathlib import Path

import pytest

from voc.baselines import (MostCommonBaseline, SplitError, cut_text, fit_tfidf, load_tfidf_config,
                           predict_tfidf)

CONFIG = Path(__file__).resolve().parent.parent / "config" / "tfidf.toml"
CARD = ["my credit card was charged twice", "the card company raised my interest", "card fee was wrong"]
HOME = ["my mortgage payment was misapplied", "the mortgage servicer lost my escrow", "mortgage late fee"]


def _rows(split="train"):
    rows = [(f"SYN-{i}", split, t, "Credit card") for i, t in enumerate(CARD * 3)]
    rows += [(f"SYN-{100 + i}", split, t, "Mortgage") for i, t in enumerate(HOME * 3)]
    return rows


def test_B11_the_most_common_class_baseline_predicts_the_top_training_label_for_every_row():
    baseline = MostCommonBaseline().fit(["Mortgage", "Credit card", "Mortgage"])
    assert baseline.predict(4) == ["Mortgage"] * 4


def test_B11_a_tie_for_most_common_is_broken_by_label_name():
    assert MostCommonBaseline().fit(["Mortgage", "Credit card"]).predict(1) == ["Credit card"]


def test_B11_tfidf_is_fitted_on_the_training_split_only():
    with pytest.raises(SplitError):
        fit_tfidf(_rows() + [("SYN-900", "dev", "card", "Credit card")], load_tfidf_config(CONFIG))


def test_B11_tfidf_gives_a_label_and_a_confidence_for_every_row():
    model = fit_tfidf(_rows(), load_tfidf_config(CONFIG))
    out = predict_tfidf(model, ["my card was charged", "escrow on my mortgage", ""])
    assert len(out) == 3
    assert out[0][0] == "Credit card" and out[1][0] == "Mortgage"
    assert all(0.0 <= conf <= 1.0 for _, conf in out)


def test_B11_tfidf_sees_the_same_cut_text_as_the_llm():
    long_card = "x " * 2_100 + "mortgage escrow mortgage"  # the only home words come after the cut
    assert len(long_card) > 4_000
    assert cut_text(long_card) == (long_card[:4_000], True)
    model = fit_tfidf(_rows(), load_tfidf_config(CONFIG))
    cut_view = predict_tfidf(model, [long_card])[0]
    assert cut_view == predict_tfidf(model, [long_card[:4_000]])[0]


def test_B11_short_text_is_not_cut():
    assert cut_text("short text") == ("short text", False)


def test_B11_the_tfidf_settings_come_from_the_recorded_config():
    config = load_tfidf_config(CONFIG)
    assert set(config) >= {"ngram_max", "min_df", "max_features", "sublinear_tf", "C", "max_iter", "seed"}
    model = fit_tfidf(_rows(), config)
    assert model.settings == config


def test_B11_a_config_missing_a_setting_is_refused(tmp_path):
    f = tmp_path / "tfidf.toml"
    f.write_text("ngram_max = 2\n", encoding="utf-8")
    with pytest.raises(KeyError):
        load_tfidf_config(f)


# Review of pull request #15


def test_B11_the_fitted_model_really_uses_every_recorded_setting():
    config = load_tfidf_config(CONFIG)
    model = fit_tfidf(_rows(), config)
    vec, clf = model.vectorizer.get_params(), model.classifier.get_params()
    assert vec["ngram_range"] == (1, config["ngram_max"]) and vec["min_df"] == config["min_df"]
    assert vec["max_features"] == config["max_features"] and vec["sublinear_tf"] == config["sublinear_tf"]
    assert vec["lowercase"] == config["lowercase"] and vec["token_pattern"] == config["token_pattern"]
    assert clf["C"] == config["C"] and clf["max_iter"] == config["max_iter"]
    assert clf["random_state"] == config["seed"] and clf["solver"] == config["solver"]
    expected_weight = None if config["class_weight"] == "none" else config["class_weight"]
    assert clf["class_weight"] == expected_weight


def test_B11_the_most_common_class_baseline_learns_from_the_training_split_only():
    with pytest.raises(SplitError):
        MostCommonBaseline().fit_rows(_rows() + [("SYN-900", "test", "card", "Credit card")])
    assert MostCommonBaseline().fit_rows(_rows()).predict(1) == ["Credit card"]
