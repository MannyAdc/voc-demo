"""B14 and B21: `voc dbt lineage` writes a lineage graph that can be committed.

The graph holds node names and edges only: no local path, no SQL, no description.
The command prints one count line. The dbt project runs on a tmp copy with the
committed synthetic fixture (`SYN-` IDs), as in tests/test_dbt.py.
"""
import contextlib
import io
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from voc import cli
from voc.labels import load_labels
from voc.load import DB_PATH, load_month

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"
LINEAGE = Path("docs") / "LINEAGE.md"
COUNT_LINE = re.compile(r"dbt lineage: \d+ sources, \d+ seeds, \d+ models, \d+ data tests, \d+ edges\. "
                        r"Written to docs/LINEAGE\.md\.")


def _repo(root):
    """A project root with the label set, a copy of the dbt project, the fixture splits and staged rows."""
    (root / "config").mkdir()
    shutil.copy(REPO / "config" / "labels.toml", root / "config" / "labels.toml")
    shutil.copytree(REPO / "dbt", root / "dbt", ignore=shutil.ignore_patterns("target", "logs"))
    shutil.copytree(FIXTURE.parent / "splits", root / "splits")
    labels = [label.name for label in load_labels(root / "config" / "labels.toml")]
    load_month(root / DB_PATH, FIXTURE, "july_2026", labels)
    return root


@pytest.fixture
def repo(tmp_path):
    return _repo(tmp_path)


@pytest.fixture(scope="module")
def lineage(tmp_path_factory):
    """Run `voc dbt lineage` once for this file. Returns the written graph, what was printed and the root.

    dbt runs in a child process with its output thrown away, so what is printed comes from `print` only.
    """
    root = _repo(tmp_path_factory.mktemp("lineage"))
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["dbt", "lineage"], env={}, root=root)
    assert code == 0, out.getvalue()
    return (root / LINEAGE).read_text(encoding="utf-8"), out.getvalue() + err.getvalue(), root


def test_B14_dbt_lineage_writes_a_mermaid_graph(lineage):
    text, _, _ = lineage
    assert "```mermaid\ngraph LR\n" in text
    assert text.rstrip().endswith("```")


def test_B14_dbt_lineage_holds_every_model_source_and_data_test(lineage):
    text, _, _ = lineage
    for name in ("stg_complaints", "curated_complaints", "voc.staged_complaints", "no_test_set_rows",
                 "product_in_label_list", "unique_stg_complaints_complaint_id",
                 "source_not_null_voc_staged_complaints_complaint_id"):
        assert name in text, name


def _edges(text):
    """The edges as (parent label, child label) pairs, read from the node lines and the arrow lines."""
    labels = dict(re.findall(r"^\s*(n\d+)\S*?\"([^\"]+)\"", text, re.MULTILINE))
    return {(labels[a], labels[b]) for a, b in re.findall(r"^\s*(n\d+) --> (n\d+)$", text, re.MULTILINE)}


def test_B14_dbt_lineage_draws_the_edges_between_nodes(lineage):
    # Changed in the review of #48: the full edge set, exactly, not 5 of the 9 edges.
    source, stg, curated = "source: voc.staged_complaints", "model: stg_complaints", "model: curated_complaints"
    assert _edges(lineage[0]) == {
        (source, stg), (stg, curated),
        (stg, "test: no_test_set_rows"), (curated, "test: no_test_set_rows"),
        (stg, "test: not_null_stg_complaints_complaint_id"), (stg, "test: unique_stg_complaints_complaint_id"),
        (stg, "test: product_in_label_list"),
        (source, "test: source_not_null_voc_staged_complaints_complaint_id"),
        (source, "test: source_unique_voc_staged_complaints_complaint_id"),
    }


def test_B14_dbt_lineage_holds_no_local_path(lineage):
    text, _, repo = lineage
    assert not re.search(r"[A-Za-z]:[\\/]", text)
    assert "\\" not in text
    assert "Users" not in text and "home/" not in text
    assert str(repo) not in text and repo.as_posix() not in text and repo.name not in text
    assert ".sql" not in text and ".yml" not in text


def test_B14_dbt_lineage_holds_no_sql_or_description(lineage):
    text, _, _ = lineage
    sql = (REPO / "dbt" / "models" / "stg_complaints.sql").read_text(encoding="utf-8")
    assert "select" not in text.lower()
    assert not any(line.strip() and line.strip() in text for line in sql.splitlines() if len(line.strip()) > 12)
    # Added in the review of #48: no description text from the dbt YAML files either.
    descriptions = []

    def collect(item):
        if isinstance(item, dict):
            for key, value in item.items():
                if key == "description" and isinstance(value, str):
                    descriptions.append(value)
                collect(value)
        elif isinstance(item, list):
            for value in item:
                collect(value)

    for path in (REPO / "dbt" / "models").glob("*.yml"):
        collect(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert descriptions
    for description in descriptions:
        words = description.split()
        # Any run of 4 words from a description, so a shortened copy is caught too.
        for start in range(max(1, len(words) - 3)):
            assert " ".join(words[start:start + 4]) not in text, description


def test_B21_dbt_lineage_prints_only_one_count_line(lineage):
    _, out, _ = lineage
    assert COUNT_LINE.fullmatch(out.strip()), out


def test_B14_dbt_lineage_counts_match_the_project(lineage):
    _, out, _ = lineage
    assert "1 sources, 0 seeds, 2 models, 6 data tests, " in out


def test_B14_the_committed_lineage_graph_matches_the_dbt_project(lineage):
    text, _, _ = lineage
    committed = REPO / LINEAGE
    assert committed.is_file(), "docs/LINEAGE.md is missing: run `voc dbt lineage` and commit it"
    assert committed.read_text(encoding="utf-8") == text, "docs/LINEAGE.md is out of date: run `voc dbt lineage`"


def test_B14_dbt_lineage_refuses_without_the_checked_test_list(repo, capfd):
    (repo / "splits" / "test.csv").unlink()
    assert cli.main(["dbt", "lineage"], env={}, root=repo) != 0
    out = capfd.readouterr().out
    assert out.startswith("error: ") and "splits/test.csv is missing" in out
    assert not (repo / LINEAGE).exists()


# Added in the review of #48: the safe-name refusal, the seed sentence and the inputs dbt does not track.


def _fake_manifest(names, seeds=0):
    """A manifest with one source, one model per name, and `seeds` seeds, all depending on the source."""
    source = "source.voc.voc.staged_complaints"
    nodes = {f"model.voc.m{i}": {"resource_type": "model", "name": name, "depends_on": {"nodes": [source]}}
             for i, name in enumerate(names)}
    nodes.update({f"seed.voc.s{i}": {"resource_type": "seed", "name": f"seed_{i}", "depends_on": {"nodes": []}}
                  for i in range(seeds)})
    return {"sources": {source: {"source_name": "voc", "name": "staged_complaints"}}, "nodes": nodes}


@pytest.fixture
def fake_parse(tmp_path, monkeypatch):
    """A project root where `dbt parse` is replaced by writing a given manifest, so no dbt runs."""
    from voc import dbt_run

    # Fixed after the first tests commit of the #48 review: without the label file, `voc dbt` stopped
    # on a missing file before the name check, so the refusal tests passed for the wrong reason.
    (tmp_path / "config").mkdir()
    shutil.copy(REPO / "config" / "labels.toml", tmp_path / "config" / "labels.toml")

    def use(manifest):
        def parse(root, action, labels, target_name="local"):
            assert action == "parse"
            target = Path(root) / dbt_run.TARGET
            target.mkdir(parents=True, exist_ok=True)
            (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            return 0, target / "run_results.json"

        monkeypatch.setattr(dbt_run, "_run", parse)
        return tmp_path

    return use


@pytest.mark.parametrize("name", ["C:/Users/x", 'stg"complaints', "a b", "..\\x"])
def test_B14_dbt_lineage_refuses_an_unsafe_name_and_writes_nothing(fake_parse, capsys, name):
    root = fake_parse(_fake_manifest(["stg_complaints", name]))
    assert cli.main(["dbt", "lineage"], env={}, root=root) == 1
    out = capsys.readouterr().out
    assert out.startswith("error: ") and name not in out
    assert "a dbt model name holds characters the lineage graph does not allow" in out
    assert not (root / LINEAGE).exists()


def test_B14_dbt_lineage_refusing_leaves_the_committed_file_unchanged(fake_parse, capsys):
    root = fake_parse(_fake_manifest(["C:/Users/x"]))
    (root / LINEAGE).parent.mkdir(parents=True)
    (root / LINEAGE).write_text("SYN earlier graph\n", encoding="utf-8")
    assert cli.main(["dbt", "lineage"], env={}, root=root) == 1
    assert "the lineage graph does not allow" in capsys.readouterr().out
    assert (root / LINEAGE).read_text(encoding="utf-8") == "SYN earlier graph\n"


def test_B14_dbt_lineage_names_the_seed_note_only_when_no_seed_is_drawn(fake_parse, capsys):
    root = fake_parse(_fake_manifest(["stg_complaints"]))
    assert cli.main(["dbt", "lineage"], env={}, root=root) == 0
    assert "Databricks" in (root / LINEAGE).read_text(encoding="utf-8")
    root = fake_parse(_fake_manifest(["stg_complaints"], seeds=2))
    assert cli.main(["dbt", "lineage"], env={}, root=root) == 0
    text = (root / LINEAGE).read_text(encoding="utf-8")
    assert "Databricks" not in text and "seed: seed_0" in text
    assert "2 seeds" in capsys.readouterr().out


def test_B14_dbt_lineage_says_which_inputs_dbt_does_not_track(lineage):
    text, _, _ = lineage
    assert "`splits/test.csv`" in text and "`labels`" in text
