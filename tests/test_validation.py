"""The validation review (specs/003-validation-review/spec.md).

Each piece adds its tests here, failing first. These tests never call a model, never read real data and
never open a review sheet. The review folder is built under a temporary home folder.
"""
import importlib.util
from pathlib import Path

import pytest

from voc import budget

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / ".claude" / "hooks"


def _read_guard():
    spec = importlib.util.spec_from_file_location("read_guard", HOOKS / "read_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".voc").mkdir(parents=True)
    monkeypatch.setattr(budget, "voc_home", lambda: home / ".voc")
    return home


# V8: review sheets live only in the review folder, which the read guard blocks for Claude.

def test_V8_the_review_folder_is_inside_the_home_voc_folder_and_not_in_the_repo(home):
    from voc import review
    folder = review.review_dir()
    assert folder == home / ".voc" / "review"
    assert not folder.resolve().is_relative_to(REPO)


@pytest.mark.parametrize("piece", ["v2", "v3", "v5"])
def test_V8_each_sheet_has_one_fixed_path_in_the_review_folder(home, piece):
    from voc import review
    path = review.sheet_path(piece)
    assert path.parent == review.review_dir()
    assert path.name == f"{piece}_sheet.csv"


@pytest.mark.parametrize("piece", ["v1", "v4", "v6", "", "../v2", "v2/../../x", "V2"])
def test_V8_a_sheet_for_any_other_name_is_refused(home, piece):
    from voc import review
    with pytest.raises(review.ReviewError):
        review.sheet_path(piece)


def test_V8_a_path_inside_the_review_folder_is_allowed(home):
    from voc import review
    inside = review.review_dir() / "v2_sheet.csv"
    assert review.inside_review_dir(inside) == inside.resolve()


@pytest.mark.parametrize("where", ["repo", "voc", "dot_dot", "next_to"])
def test_V8_a_path_outside_the_review_folder_is_refused(home, tmp_path, where):
    from voc import review
    folder = review.review_dir()
    path = {"repo": REPO / "v2_sheet.csv",
            "voc": home / ".voc" / "v2_sheet.csv",
            "dot_dot": folder / ".." / "v2_sheet.csv",
            "next_to": home / ".voc" / "review2" / "v2_sheet.csv"}[where]
    with pytest.raises(review.ReviewError):
        review.inside_review_dir(path)


def test_V8_the_refusal_names_no_path(home):
    from voc import review
    with pytest.raises(review.ReviewError) as refused:
        review.inside_review_dir(home / "elsewhere" / "v2_sheet.csv")
    assert str(home) not in str(refused.value)


# These pin the read guard over the review folder. The guard already blocks the whole home `.voc` folder,
# so they pass at once. They fail if that is ever narrowed.

@pytest.mark.parametrize("tool, tool_input", [
    ("Read", {"file_path": "{review}/v2_sheet.csv"}),
    ("Grep", {"pattern": "x", "path": "{review}"}),
    ("Glob", {"pattern": "*.csv", "path": "{review}"}),
    ("Bash", {"command": "cat ~/.voc/review/v2_sheet.csv"}),
    ("Bash", {"command": "cd ~/.voc/review && head -3 v5_sheet.csv"}),
    ("PowerShell", {"command": r"Get-Content $env:USERPROFILE\.voc\review\v3_sheet.csv"}),
    ("Monitor", {"command": "tail -f $HOME/.voc/review/v2_sheet.csv"}),
])
def test_V8_the_read_guard_blocks_the_review_folder(tmp_path, tool, tool_input):
    home = tmp_path / "home"
    review_folder = home / ".voc" / "review"
    review_folder.mkdir(parents=True)
    filled = {key: value.replace("{review}", str(review_folder)) for key, value in tool_input.items()}
    decision = _read_guard().decide(tool, filled, env={}, home=home, root=tmp_path / "repo")
    assert decision and decision[0] == "deny"


# Review of #70.

def test_V8_a_review_folder_that_resolves_inside_the_repo_is_refused(tmp_path, monkeypatch):
    from voc import review
    repo = tmp_path / "repo"
    monkeypatch.setattr(review, "REPO_ROOT", repo)
    monkeypatch.setattr(budget, "voc_home", lambda: repo / "linked")
    with pytest.raises(review.ReviewError):
        review.inside_review_dir(repo / "linked" / "review" / "v2_sheet.csv")
    with pytest.raises(review.ReviewError):
        review.sheet_path("v2")


def test_V8_the_sheet_path_goes_through_the_folder_check(home, monkeypatch):
    from voc import review
    seen = []
    monkeypatch.setattr(review, "inside_review_dir", lambda path: seen.append(path) or path)
    review.sheet_path("v3")
    assert seen == [review.review_dir() / "v3_sheet.csv"]


def test_V8_the_review_folder_itself_is_refused(home):
    from voc import review
    with pytest.raises(review.ReviewError):
        review.inside_review_dir(review.review_dir())


def test_V8_a_link_inside_the_folder_that_points_outside_is_refused(home, tmp_path):
    from voc import review
    folder = review.review_dir()
    folder.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (folder / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("this machine cannot make links (Windows without the permission). CI on Linux runs it.")
    with pytest.raises(review.ReviewError):
        review.inside_review_dir(folder / "link" / "v2_sheet.csv")


# The frozen lists (spec 003, "The frozen lists", B16). Drawn from synthetic IDs here.

SIZES = {"dry_run": 10, "v5": 50, "v2": 40, "v1": 100}


def _synthetic(n=300):
    """Development IDs, accepted labels (every 10th quarantined) and recorded products (every 3rd differs)."""
    dev = [f"SYN-{i}" for i in range(1, n + 1)]
    accepted = {c: ("B" if i % 3 == 0 else "A") for i, c in enumerate(dev, 1) if i % 10}
    recorded = dict.fromkeys(dev, "A")
    return dev, accepted, recorded


def test_B16_V2_V5_the_lists_are_drawn_in_the_spec_order_with_the_spec_sizes():
    from voc import validation
    dev, accepted, recorded = _synthetic()
    lists, disagreements = validation.draw(dev, accepted, recorded, SIZES, seed=7)
    assert {name: len(ids) for name, ids in lists.items()} == SIZES
    assert disagreements == sum(1 for c, label in accepted.items() if label != recorded[c])
    assert set(lists["dry_run"]) <= set(accepted)
    assert set(lists["v5"]) <= set(accepted) and not set(lists["v5"]) & set(lists["dry_run"])
    assert all(accepted[c] != recorded[c] for c in lists["v2"])
    assert not set(lists["v2"]) & (set(lists["dry_run"]) | set(lists["v5"]))
    assert set(lists["v1"]) <= set(dev)


def test_B16_the_lists_are_in_complaint_id_order_and_the_same_for_the_same_seed():
    from voc import validation
    dev, accepted, recorded = _synthetic()
    first, _ = validation.draw(dev, accepted, recorded, SIZES, seed=7)
    again, _ = validation.draw(list(reversed(dev)), dict(reversed(accepted.items())), recorded, SIZES, seed=7)
    other, _ = validation.draw(dev, accepted, recorded, SIZES, seed=8)
    assert first == again
    assert first != other
    for ids in first.values():
        assert ids == sorted(ids, key=lambda c: int(c.split("-")[1]))


def test_B16_too_few_complaints_for_a_list_is_refused():
    from voc import validation
    from voc.data import SampleMismatch
    dev, accepted, recorded = _synthetic(60)
    with pytest.raises(SampleMismatch):
        validation.draw(dev, accepted, recorded, SIZES, seed=7)


def test_V7_an_id_outside_the_development_list_is_refused():
    from voc import validation
    from voc.data import SampleMismatch
    dev, accepted, recorded = _synthetic()
    with pytest.raises(SampleMismatch):
        validation.draw(dev, {**accepted, "SYN-9999": "A"}, {**recorded, "SYN-9999": "A"}, SIZES, seed=7)


def test_B16_an_accepted_label_with_no_recorded_product_is_refused():
    from voc import validation
    from voc.data import SampleMismatch
    dev, accepted, recorded = _synthetic()
    del recorded[next(iter(accepted))]
    with pytest.raises(SampleMismatch):
        validation.draw(dev, accepted, recorded, SIZES, seed=7)


def _splits(tmp_path, dev):
    """A synthetic frozen development list with its manifest, as `voc sample` writes it."""
    from voc.data import Row, write_splits
    rows = [Row(c, "A", f"synthetic text {c}") for c in dev]
    sets = {"dev": rows, "test": [Row("SYN-90001", "A", "t")], "train": [Row("SYN-90002", "A", "u")]}
    folder = tmp_path / "splits"
    write_splits(folder, sets, removed=0, source_sha256="0" * 64, seed=1, settings={"month": "july_2026"})
    return folder


def test_B16_the_lists_are_written_once_and_read_back_with_their_hashes(tmp_path):
    from voc import validation
    from voc.data import SampleMismatch
    dev, accepted, recorded = _synthetic()
    splits = _splits(tmp_path, dev)
    lists, disagreements = validation.draw(dev, accepted, recorded, SIZES, seed=7)
    validation.write_lists(splits, lists, seed=7, disagreements=disagreements)
    assert validation.read_lists(splits) == lists
    with pytest.raises(SampleMismatch):
        validation.write_lists(splits, lists, seed=7, disagreements=disagreements)


def test_B16_a_changed_list_file_is_refused(tmp_path):
    from voc import validation
    from voc.data import SampleMismatch
    dev, accepted, recorded = _synthetic()
    splits = _splits(tmp_path, dev)
    lists, disagreements = validation.draw(dev, accepted, recorded, SIZES, seed=7)
    validation.write_lists(splits, lists, seed=7, disagreements=disagreements)
    path = splits / "validation" / "v2.csv"
    path.write_text(path.read_text(encoding="utf-8").replace(lists["v2"][0] + ",", "SYN-299,"), encoding="utf-8")
    with pytest.raises(SampleMismatch):
        validation.read_lists(splits)


@pytest.mark.parametrize("change", ["not_dev", "overlap"])
def test_B16_V7_lists_that_leave_the_development_set_or_overlap_are_refused_on_read(tmp_path, change):
    from voc import validation
    from voc.data import SampleMismatch
    dev, accepted, recorded = _synthetic()
    splits = _splits(tmp_path, dev)
    lists, disagreements = validation.draw(dev, accepted, recorded, SIZES, seed=7)
    if change == "not_dev":
        lists["v1"] = lists["v1"][:-1] + ["SYN-90001"]
    else:
        lists["v2"] = lists["v2"][:-1] + [lists["v5"][0]]
    validation.write_lists(splits, lists, seed=7, disagreements=disagreements)
    with pytest.raises(SampleMismatch):
        validation.read_lists(splits)


def test_B16_the_committed_config_has_the_spec_sizes_and_a_fixed_seed():
    import tomllib
    with open(REPO / "config" / "validation.toml", "rb") as f:
        config = tomllib.load(f)
    assert {name: config[name] for name in SIZES} == SIZES
    assert isinstance(config["seed"], int)


def test_B16_B21_the_command_draws_from_the_staged_table_and_prints_counts_only(tmp_path, capsys):
    import csv
    from voc import cli, validation
    from voc.data import Row, write_splits
    from voc.labels import load_labels
    from voc.load import DB_PATH, load_month

    fixture = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"
    with open(fixture, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["Consumer complaint narrative"].strip()]
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    labels_toml = (REPO / "config" / "labels.toml").read_text(encoding="utf-8")
    (root / "config" / "labels.toml").write_text(labels_toml, encoding="utf-8")
    (root / "config" / "validation.toml").write_text(
        'dry_run = 1\nv5 = 1\nv2 = 1\nv1 = 3\nseed = 7\nlabels_file = "results/labels/v1_dev.csv"\n', encoding="utf-8")
    load_month(root / DB_PATH, fixture, "july_2026",
               [label.name for label in load_labels(root / "config" / "labels.toml")])
    dev = [Row(r["Complaint ID"], r["Product"], r["Consumer complaint narrative"]) for r in rows]
    write_splits(root / "splits", {"dev": dev, "test": [], "train": []}, removed=0, source_sha256="0" * 64,
                 seed=1, settings={"month": "july_2026"})
    # 6 accepted, the first 4 with a label that differs from the recorded product, and 1 quarantined.
    differing = {r.complaint_id for r in dev[:4]}
    labels = root / "results" / "labels" / "v1_dev.csv"
    labels.parent.mkdir(parents=True)
    with open(labels, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["complaint_id", "decision", "accepted_label"])
        for r in dev[:-1]:
            other = "Mortgage" if r.product != "Mortgage" else "Credit card"
            writer.writerow([r.complaint_id, "accepted", other if r.complaint_id in differing else r.product])
        writer.writerow([dev[-1].complaint_id, "quarantined", ""])
    assert cli.main(["validation-lists"], env={}, root=root) == 0
    printed = capsys.readouterr().out
    assert "accepted disagreements: 4" in printed
    for r in rows:
        assert r["Consumer complaint narrative"][:20] not in printed
    lists = validation.read_lists(root / "splits")
    assert {name: len(ids) for name, ids in lists.items()} == {"dry_run": 1, "v5": 1, "v2": 1, "v1": 3}
    assert set(lists["v2"]) <= differing
    assert dev[-1].complaint_id not in lists["dry_run"] + lists["v5"] + lists["v2"]
