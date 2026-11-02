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
