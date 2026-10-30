"""B14 and B21: `voc dbt lineage` writes a lineage graph that can be committed.

The graph holds node names and edges only: no local path, no SQL, no description.
The command prints one count line. The dbt project runs on a tmp copy with the
committed synthetic fixture (`SYN-` IDs), as in tests/test_dbt.py.
"""
import contextlib
import io
import re
import shutil
from pathlib import Path

import pytest

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
    edges = _edges(lineage[0])
    assert ("source: voc.staged_complaints", "model: stg_complaints") in edges
    assert ("model: stg_complaints", "model: curated_complaints") in edges
    assert ("model: curated_complaints", "test: no_test_set_rows") in edges
    assert ("model: stg_complaints", "test: no_test_set_rows") in edges
    assert ("source: voc.staged_complaints", "test: source_unique_voc_staged_complaints_complaint_id") in edges


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
