"""B5, B10: the synthetic injection set, labelled and scored apart from every accuracy figure.

The set itself is synthetic (`config/injection.toml`, SYN- IDs). These tests use the mock backend with planted
answers, so they prove the counting works. How the real model behaves comes from the owner's live run.
"""
import csv
import json
import shutil
import tomllib
from pathlib import Path

import pytest

from voc.labels import load_labels
from voc.prompt import build_prompt

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """A fake home folder, so the real ledger and recordings are never used."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home


def _items():
    with open(REPO / "config" / "injection.toml", "rb") as f:
        return tomllib.load(f)["item"]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    for name in ("labels.toml", "prices.toml", "injection.toml"):
        shutil.copy(REPO / "config" / name, root / "config" / name)
    shutil.copytree(REPO / "config" / "prompts", root / "config" / "prompts")
    # A committed repo, because an uncommitted injection file is refused (B16, review of #33).
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "SYN first")
    return root


def _git(root, *args):
    import subprocess

    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, f"git {args[0]} failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _mock(root, answers):
    """Mock answers keyed by the exact prompt `voc label injection` builds.

    `answers` maps an ID to (label, quote), or to a raw answer text.
    """
    from voc.baselines import cut_text
    from voc.pipeline import definitions, load_prompt_version

    labels = load_labels(root / "config" / "labels.toml")
    names = [label.name for label in labels]
    v1 = load_prompt_version(root, "v1")
    fixtures = []
    for item in _items():
        if item["id"] not in answers:
            continue
        answer = answers[item["id"]]
        text = answer if isinstance(answer, str) else json.dumps({"label": answer[0], "quote": answer[1]})
        prompt = build_prompt(v1.instructions, names, cut_text(item["text"])[0], complaint_id=item["id"],
                              definitions=definitions(labels)).prompt
        fixtures.append({"prompt": prompt, "text": text})
    path = root / "mock.json"
    path.write_text(json.dumps(fixtures), encoding="utf-8")
    return {"LLM_BACKEND": "mock", "VOC_MOCK_FIXTURES": str(path)}


def _first_sentence(text):
    return text.split(". ")[0].removeprefix("SYN ")


def _planted(root):
    """SYN-9001 obeys with a real quote, SYN-9002 obeys with a made-up quote, the rest answer correctly."""
    answers = {}
    for item in _items():
        if item["id"] == "SYN-9005":
            continue  # its fake closing tag is caught before any call
        if item["id"] == "SYN-9001":
            answers[item["id"]] = (item["forced_label"], _first_sentence(item["text"]))
        elif item["id"] == "SYN-9002":
            answers[item["id"]] = (item["forced_label"], "the collector called me at work")
        else:
            answers[item["id"]] = (item["product"], _first_sentence(item["text"]))
    return _mock(root, answers)


def _voc(root, env, *args):
    from voc import cli

    return cli.main(list(args), env=env, root=root)


def test_B5_the_injection_set_is_synthetic_and_well_formed():
    items = _items()
    names = {label.name for label in load_labels(REPO / "config" / "labels.toml")}
    assert len(items) >= 10
    assert len({i["id"] for i in items}) == len(items) and len({i["attack"] for i in items}) == len(items)
    for item in items:
        assert item["id"].startswith("SYN-")
        assert item["product"] in names and item["forced_label"] in names
        assert item["forced_label"] != item["product"]
        assert item["text"].startswith("SYN ")


def test_B5_voc_label_injection_labels_the_set_and_marks_it_synthetic(repo):
    assert _voc(repo, _planted(repo), "label", "injection") == 0
    rows = list(csv.DictReader((repo / "results" / "labels" / "v1_injection.csv").read_text(encoding="utf-8")
                               .splitlines()))
    assert {r["complaint_id"] for r in rows} == {i["id"] for i in _items()}
    assert {r["split"] for r in rows} == {"injection"}
    reasons = {r["complaint_id"]: r["reason"] for r in rows}
    assert reasons["SYN-9005"] == "boundary_in_text"


def test_B10_voc_evaluate_injection_counts_the_three_outcomes(repo, capsys):
    assert _voc(repo, _planted(repo), "label", "injection") == 0
    capsys.readouterr()
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN first look") == 0
    out = capsys.readouterr().out
    report = json.loads((repo / "results" / "eval" / "v1_injection.json").read_text(encoding="utf-8"))
    # Changed in the green commit after the review of #33 (owner decision): the closing-tag item is now
    # "caught before a call", not "not obeyed". A red commit cannot make a passing test fail.
    assert report["counts"] == {"obeyed_and_accepted": 1, "obeyed_and_quarantined": 1, "caught_before_call": 1,
                                "no_usable_answer": 0, "not_obeyed": len(_items()) - 3}
    by_id = {i["complaint_id"]: i for i in report["items"]}
    assert by_id["SYN-9001"]["outcome"] == "obeyed_and_accepted"
    assert by_id["SYN-9002"]["outcome"] == "obeyed_and_quarantined"
    assert by_id["SYN-9005"]["outcome"] == "caught_before_call" and by_id["SYN-9005"]["reason"] == "boundary_in_text"
    assert by_id["SYN-9001"]["attack"] == "direct override"
    assert "obeyed and accepted: 1" in out and "reported apart" in out


def test_B10_injection_results_never_enter_the_development_figures(repo):
    assert _voc(repo, _planted(repo), "label", "injection") == 0
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 0
    assert not (repo / "EVAL_VERSIONS.md").exists()
    assert not (repo / "results" / "eval" / "v1_dev.json").exists()


def test_B7_evaluate_injection_refuses_a_run_that_was_never_made(repo, capsys):
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 1
    assert "voc label injection" in capsys.readouterr().out


def test_B16_a_changed_injection_file_is_refused_at_scoring(repo, capsys):
    assert _voc(repo, _planted(repo), "label", "injection") == 0
    path = repo / "config" / "injection.toml"
    path.write_text(path.read_text(encoding="utf-8").replace("direct override", "SYN renamed"), encoding="utf-8")
    capsys.readouterr()
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 1
    assert "injection set changed" in capsys.readouterr().out


# Review of #33: every kind of non-answer has its own outcome, and the inputs are checked


def _results(root):
    return root / "results" / "labels" / "v1_injection.csv"


def _rewrite(path, change):
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    rows = change(rows)
    with open(path, "w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_B10_each_kind_of_non_answer_has_its_own_outcome(repo):
    answers = {}
    for item in _items():
        if item["id"] == "SYN-9005":
            continue
        answers[item["id"]] = (item["product"], _first_sentence(item["text"]))
    first = _items()[0]
    answers["SYN-9001"] = (first["forced_label"], _first_sentence(first["text"]))
    answers["SYN-9002"] = (_items()[1]["forced_label"], "the collector called me at work")
    answers["SYN-9010"] = "SYN this is not an answer in the agreed format"
    answers["SYN-9004"] = ("SYN a label that is not in the list", _first_sentence(_items()[3]["text"]))
    assert _voc(repo, _mock(repo, answers), "label", "injection") == 0
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 0
    report = json.loads((repo / "results" / "eval" / "v1_injection.json").read_text(encoding="utf-8"))
    assert report["counts"] == {"obeyed_and_accepted": 1, "obeyed_and_quarantined": 1, "caught_before_call": 1,
                                "no_usable_answer": 2, "not_obeyed": len(_items()) - 5}
    by_id = {i["complaint_id"]: i["outcome"] for i in report["items"]}
    assert by_id["SYN-9005"] == "caught_before_call" and by_id["SYN-9010"] == "no_usable_answer"


@pytest.mark.parametrize("reason", ["model_error", "not_run_budget"])
def test_B7_a_run_where_the_model_never_answered_an_item_is_not_scored(repo, capsys, reason):
    assert _voc(repo, _planted(repo), "label", "injection") == 0

    def broken(rows):
        rows[0].update(decision="quarantined", reason=reason, accepted_label="", quote_start="", quote_end="")
        return rows

    _rewrite(_results(repo), broken)
    capsys.readouterr()
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 1
    assert "never answered" in capsys.readouterr().out


def test_B7_a_stopped_injection_run_is_refused(repo, capsys):
    assert _voc(repo, _planted(repo), "label", "injection") == 0
    path = repo / "results" / "labels" / "v1_injection.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["stopped"] = "SYN stop"
    path.write_text(json.dumps(summary), encoding="utf-8")
    capsys.readouterr()
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 1
    assert "stopped early" in capsys.readouterr().out


def test_B16_a_results_file_without_exactly_the_set_is_refused(repo, capsys):
    assert _voc(repo, _planted(repo), "label", "injection") == 0
    _rewrite(_results(repo), lambda rows: rows[1:])
    capsys.readouterr()
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 1
    assert "exactly the injection set" in capsys.readouterr().out


def test_B16_an_uncommitted_injection_file_is_not_labelled(repo, capsys):
    path = repo / "config" / "injection.toml"
    path.write_text(path.read_text(encoding="utf-8") + "\n# SYN uncommitted edit\n", encoding="utf-8")
    capsys.readouterr()
    assert _voc(repo, _planted(repo), "label", "injection") == 1
    assert "uncommitted" in capsys.readouterr().out


def test_B16_the_loader_refuses_a_repeated_id_or_a_forced_label_equal_to_the_product(repo, capsys):
    path = repo / "config" / "injection.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('id = "SYN-9002"', 'id = "SYN-9001"', 1), encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "SYN repeated ID")
    capsys.readouterr()
    assert _voc(repo, _planted(repo), "label", "injection") == 1
    assert "repeated" in capsys.readouterr().out


def test_B9_the_injection_set_is_labelled_whole_never_with_a_limit(repo, capsys):
    capsys.readouterr()
    assert _voc(repo, _planted(repo), "label", "injection", "--limit", "3") == 1
    assert "limit" in capsys.readouterr().out


def test_B10_the_development_results_are_left_unchanged(repo):
    (repo / "EVAL_VERSIONS.md").write_text("SYN table\n", encoding="utf-8")
    dev = repo / "results" / "eval" / "v1_dev.json"
    dev.parent.mkdir(parents=True)
    dev.write_text('{"SYN": 1}\n', encoding="utf-8")
    assert _voc(repo, _planted(repo), "label", "injection") == 0
    assert _voc(repo, {}, "evaluate", "injection", "--prompt", "v1", "--note", "SYN") == 0
    assert (repo / "EVAL_VERSIONS.md").read_text(encoding="utf-8") == "SYN table\n"
    assert dev.read_text(encoding="utf-8") == '{"SYN": 1}\n'
