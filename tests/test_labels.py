"""B24: the label set is frozen in one config file, and every reader uses it.

The labels and the sub-products they cover come from the CFPB's own list,
"Consumer complaint form product and issue options", effective 24 August 2023.
"""
import json
from pathlib import Path

from voc.labels import load_labels

ROOT = Path(__file__).resolve().parent.parent


def test_B24_the_label_set_lists_each_label_once():
    labels = load_labels(ROOT / "config" / "labels.toml")
    names = [label.name for label in labels]
    assert len(names) == 11 and len(set(names)) == 11


def test_B24_every_label_lists_the_cfpb_sub_products_it_covers():
    for label in load_labels(ROOT / "config" / "labels.toml"):
        assert label.covers, label.name
        assert all(item.strip() == item and item for item in label.covers)


def test_B24_the_labels_are_exactly_the_profiled_categories():
    profile = json.loads((ROOT / "results" / "profile_july_2026.json").read_text(encoding="utf-8"))
    assert {label.name for label in load_labels(ROOT / "config" / "labels.toml")} == set(profile["products"])


def test_B24_a_repeated_label_is_refused(tmp_path):
    f = tmp_path / "labels.toml"
    f.write_text('[[label]]\nname = "A"\ncovers = ["x"]\n[[label]]\nname = "A"\ncovers = ["y"]\n', encoding="utf-8")
    try:
        load_labels(f)
    except ValueError as err:
        assert "more than once" in str(err)
    else:
        raise AssertionError("a repeated label was accepted")
