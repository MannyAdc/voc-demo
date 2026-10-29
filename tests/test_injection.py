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
    return root


def _mock(root, answers):
    """Mock answers keyed by the exact prompt `voc label injection` builds. `answers` maps an ID to (label, quote)."""
    from voc.baselines import cut_text
    from voc.pipeline import definitions, load_prompt_version

    labels = load_labels(root / "config" / "labels.toml")
    names = [label.name for label in labels]
    v1 = load_prompt_version(root, "v1")
    fixtures = []
    for item in _items():
        if item["id"] not in answers:
            continue
        label, quote = answers[item["id"]]
        prompt = build_prompt(v1.instructions, names, cut_text(item["text"])[0], complaint_id=item["id"],
                              definitions=definitions(labels)).prompt
        fixtures.append({"prompt": prompt, "text": json.dumps({"label": label, "quote": quote})})
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
    assert report["counts"] == {"obeyed_and_accepted": 1, "obeyed_and_quarantined": 1,
                                "not_obeyed": len(_items()) - 2}
    by_id = {i["complaint_id"]: i for i in report["items"]}
    assert by_id["SYN-9001"]["outcome"] == "obeyed_and_accepted"
    assert by_id["SYN-9002"]["outcome"] == "obeyed_and_quarantined"
    assert by_id["SYN-9005"]["outcome"] == "not_obeyed" and by_id["SYN-9005"]["reason"] == "boundary_in_text"
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
