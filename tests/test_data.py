"""B9, B16, B25: samples are prepared, sized, split and frozen. All text here is synthetic."""
import json

import pytest

from voc.data import (DUPLICATE_THRESHOLD, Row, SampleMismatch, allocate, cochran_size, content_hash, dedupe,
                      load_test_hashes, opening_key, quick_check_ids, read_splits, split, verify_ids,
                      write_splits)


def _rows(product, count, start=0, text="complaint number {i} about the account fee and the bank"):
    return [Row(f"SYN-{start + i}", product, text.format(i=i)) for i in range(count)]


# Duplicates (B9)


def test_B9_the_opening_key_ignores_case_digits_and_redaction_runs():
    assert opening_key("On XX/XX/XXXX I paid 500 to the BANK") == opening_key("on xx/xx/xxxx i paid 12 to the bank")
    assert opening_key("Sent XXXX a letter") == opening_key("sent a letter")


def test_B9_different_openings_have_different_keys():
    assert opening_key("My card was charged twice") != opening_key("My mortgage escrow was wrong")


def test_B9_the_same_opening_with_a_different_body_keeps_both():
    a = Row("SYN-1", "A", "I am writing about my account. The fee was charged twice last month.")
    b = Row("SYN-2", "A", "I am writing about my account. A collector keeps calling me at work.")
    kept, removed = dedupe([a, b])
    assert [r.complaint_id for r in kept] == ["SYN-1", "SYN-2"] and removed == 0


def test_B9_the_same_opening_and_very_similar_full_text_is_one_duplicate():
    a = Row("SYN-1", "A", "I am writing about my account. The fee was charged twice last month, please refund.")
    b = Row("SYN-2", "A", "I am writing about my account. The fee was charged twice last month, please refund!")
    kept, removed = dedupe([b, a])
    assert [r.complaint_id for r in kept] == ["SYN-1"] and removed == 1


def test_B9_exact_copies_after_normalising_case_and_spacing_are_duplicates():
    rows = [Row("SYN-3", "A", "The Fee  was wrong"), Row("SYN-1", "B", "the fee was\nwrong")]
    kept, removed = dedupe(rows)
    assert [r.complaint_id for r in kept] == ["SYN-1"] and removed == 1


def test_B9_dedupe_gives_the_same_result_whatever_order_the_rows_arrive_in():
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
    rows = [Row(f"SYN-{i}", "A", f"{w} is what this complaint is about and nothing else") for i, w in enumerate(words)]
    rows.append(Row("SYN-100", "A", "charlie is what this complaint is about and nothing else"))
    kept, removed = dedupe(rows)
    assert (kept, removed) == dedupe(list(reversed(rows)))
    assert len(kept) == 6 and removed == 1


def test_B9_the_kept_copy_is_the_lowest_complaint_id_as_a_number():
    rows = [Row("SYN-10", "A", "same words here exactly"), Row("SYN-9", "A", "same words here exactly")]
    assert [r.complaint_id for r in dedupe(rows)[0]] == ["SYN-9"]


def test_B9_the_similarity_threshold_is_fixed_and_recorded(tmp_path):
    assert 0.8 <= DUPLICATE_THRESHOLD < 1.0
    sets = split(_rows("A", 40), dev_size=4, test_size=8, seed=1)
    write_splits(tmp_path, sets, removed=0, source_sha256="0" * 64, seed=1)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["duplicate_threshold"] == DUPLICATE_THRESHOLD and manifest["duplicates_removed"] == 0


# Sizes (B25)


def test_B25_cochran_gives_the_textbook_sizes_for_a_huge_pool():
    assert [cochran_size(e, 10**12) for e in (0.05, 0.03, 0.02)] == [385, 1068, 2401]


def test_B25_the_finite_pool_correction_matches_the_data_page():
    assert cochran_size(0.05, 9_379) == 370 and cochran_size(0.02, 9_379) == 1_912


def test_B25_the_split_follows_the_pool_shares_and_adds_up_exactly():
    parts = allocate(100, {"A": 667, "B": 222, "C": 111})
    assert parts == {"A": 67, "B": 22, "C": 11} and sum(parts.values()) == 100


# Splits (B9, B16)


def _pool():
    return _rows("A", 300) + _rows("B", 60, start=1000) + _rows("C", 6, start=2000)


def test_B9_the_three_sets_never_overlap_and_cover_every_row():
    sets = split(_pool(), dev_size=20, test_size=60, seed=3)
    ids = [{r.complaint_id for r in sets[name]} for name in ("dev", "test", "train")]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])
    assert len(ids[0] | ids[1] | ids[2]) == len(_pool())


def test_B9_big_classes_fill_their_quota():
    sets = split(_pool(), dev_size=20, test_size=60, seed=3)
    assert sum(r.product == "A" for r in sets["test"]) == allocate(60, {"A": 300, "B": 60, "C": 6})["A"]


def test_B9_a_small_class_gives_at_most_half_to_test_and_keeps_training_rows():
    rows = _rows("A", 10) + _rows("B", 4, start=100)
    sets = split(rows, dev_size=1, test_size=12, seed=3)
    assert sum(r.product == "B" for r in sets["test"]) <= 2
    assert any(r.product == "B" for r in sets["train"])


def test_B9_the_same_seed_gives_the_same_split_and_another_seed_another_test_set():
    first, again = split(_pool(), 20, 60, seed=3), split(_pool(), 20, 60, seed=3)
    other = split(_pool(), 20, 60, seed=4)
    assert first == again
    assert {r.complaint_id for r in first["test"]} != {r.complaint_id for r in other["test"]}


def test_B9_the_test_set_does_not_change_when_the_development_size_changes():
    small, large = split(_pool(), 10, 60, seed=3), split(_pool(), 40, 60, seed=3)
    assert small["test"] == large["test"]


# Frozen lists (B16)


def test_B16_the_content_hash_covers_narrative_and_product_together():
    assert content_hash("text", "A") != content_hash("text", "B") != content_hash("other", "A")
    assert content_hash("text", "A") not in {content_hash("text", ""), content_hash("", "A")}


def test_B16_each_list_hash_matches_its_content_and_the_quick_check_list_is_part_of_dev(tmp_path):
    sets = split(_pool(), 60, 60, seed=3)
    write_splits(tmp_path, sets, removed=2, source_sha256="a" * 64, seed=3)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    loaded = read_splits(tmp_path)
    for name in ("dev", "test", "train"):
        assert manifest["lists"][name]["count"] == len(sets[name])
        assert loaded[name] == {r.complaint_id: content_hash(r.narrative, r.product) for r in sets[name]}
    quick = quick_check_ids(tmp_path)
    assert len(quick) == 50 and set(quick) <= set(loaded["dev"])


def test_B16_a_changed_list_file_is_refused(tmp_path):
    write_splits(tmp_path, split(_pool(), 60, 60, seed=3), removed=0, source_sha256="a" * 64, seed=3)
    path = tmp_path / "dev.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("SYN-", "SYN-9", 1), encoding="utf-8")
    with pytest.raises(SampleMismatch):
        read_splits(tmp_path)


def test_B16_ids_that_are_not_in_the_committed_list_are_refused(tmp_path):
    sets = split(_pool(), 60, 60, seed=3)
    write_splits(tmp_path, sets, removed=0, source_sha256="a" * 64, seed=3)
    good = sets["dev"][:3]
    verify_ids(tmp_path, "dev", good)
    with pytest.raises(SampleMismatch):
        verify_ids(tmp_path, "dev", good + [Row("SYN-99999", "A", "not in the list")])


def test_B16_a_complaint_whose_narrative_or_product_changed_is_refused(tmp_path):
    sets = split(_pool(), 60, 60, seed=3)
    write_splits(tmp_path, sets, removed=0, source_sha256="a" * 64, seed=3)
    first = sets["dev"][0]
    with pytest.raises(SampleMismatch):
        verify_ids(tmp_path, "dev", [Row(first.complaint_id, first.product, first.narrative + " changed")])
    with pytest.raises(SampleMismatch):
        verify_ids(tmp_path, "dev", [Row(first.complaint_id, "Other", first.narrative)])


def test_B16_the_test_hash_loader_returns_only_ids_and_hashes(tmp_path):
    sets = split(_pool(), 60, 60, seed=3)
    write_splits(tmp_path, sets, removed=0, source_sha256="a" * 64, seed=3)
    hashes = load_test_hashes(tmp_path)
    assert set(hashes) == {r.complaint_id for r in sets["test"]}
    assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in hashes.values())
    texts = {r.narrative for r in sets["test"]} | {"A", "B", "C"}
    assert not texts & set(hashes.values())
