"""B14, B17 and B21 on the Databricks target (T021): the same dbt models, on synthetic seeds only.

No test opens a connection. dbt is replaced by a fake child process that records its arguments
and environment and writes a run_results.json. The live run is the owner's, with their own token.
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from voc import cli, dbt_run
from voc.dbt_run import DbtError
from voc.labels import load_labels
from voc.load import DB_PATH, load_month

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"
SEEDS = Path("dbt") / "seeds"
CONNECTION = ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")


def _token():
    # A fake token, built while the test runs, never written as one string.
    return "dapi" + "0f" * 16


def _script():
    spec = importlib.util.spec_from_file_location("databricks_fixture_build",
                                                  REPO / "scripts" / "databricks_fixture_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def work(tmp_path):
    """A work folder made by the fixture script: the dbt project, the splits and the synthetic seeds."""
    folder = tmp_path / "work"
    _script().prepare(FIXTURE, folder)
    return folder


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "synthetic.example.invalid")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/synthetic")
    monkeypatch.setenv("DATABRICKS_TOKEN", _token())


class FakeDbt:
    """Stands in for the dbt child process. Records each call and writes a run_results.json."""

    def __init__(self, nodes=None, code=0):
        self.calls = []
        self.nodes = nodes if nodes is not None else [
            {"unique_id": "seed.voc.staged_complaints", "status": "success"},
            {"unique_id": "seed.voc.test_list", "status": "success"},
            {"unique_id": "model.voc.stg_complaints", "status": "success"},
            {"unique_id": "model.voc.curated_complaints", "status": "success"},
            {"unique_id": "test.voc.product_in_label_list", "status": "pass", "failures": 0},
        ]
        self.code = code

    def __call__(self, args, env=None, **kwargs):
        self.calls.append({"args": list(args), "env": dict(env or {})})
        target = Path(args[args.index("--target-path") + 1])
        target.mkdir(parents=True, exist_ok=True)
        (target / "run_results.json").write_text(json.dumps({"results": self.nodes}), encoding="utf-8")
        return subprocess.CompletedProcess(args, self.code)


@pytest.fixture
def fake_dbt(monkeypatch):
    fake = FakeDbt()
    monkeypatch.setattr(dbt_run.subprocess, "run", fake)
    return fake


def _labels():
    return [label.name for label in load_labels(REPO / "config" / "labels.toml")]


def _build(root):
    return cli.main(["dbt", "build", "--target", "databricks"], env={}, root=root)


# The seeds hold synthetic rows only (no complaint text from real data reaches the cloud)


def test_B14_the_fixture_script_writes_seeds_with_synthetic_ids_only(work):
    seed = (work / SEEDS / "staged_complaints.csv").read_text(encoding="utf-8").splitlines()
    assert seed[0].split(",")[0] == "complaint_id"
    assert len(seed) > 1 and all(row.startswith("SYN-") for row in seed[1:])
    assert (work / SEEDS / "test_list.csv").read_bytes() == (work / "splits" / "test.csv").read_bytes()


def test_B14_the_databricks_target_refuses_without_the_synthetic_seeds(tmp_path, connected, fake_dbt, capfd):
    folder = tmp_path / "work"
    _script().prepare(FIXTURE, folder)
    shutil.rmtree(folder / SEEDS)
    assert _build(folder) != 0
    assert "synthetic seed" in capfd.readouterr().out
    assert fake_dbt.calls == []


def test_B14_the_databricks_target_refuses_a_seed_with_an_id_that_is_not_synthetic(work, connected, fake_dbt,
                                                                                    capfd):
    seed = work / SEEDS / "staged_complaints.csv"
    rows = seed.read_text(encoding="utf-8").splitlines()
    rows.append("1234567" + rows[1][rows[1].index(","):])
    seed.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert _build(work) != 0
    printed = capfd.readouterr().out
    assert "SYN-" in printed and "1234567" not in printed
    assert fake_dbt.calls == []


def test_B14_the_databricks_target_refuses_an_extra_seed_file(work, connected, fake_dbt, capfd):
    (work / SEEDS / "other.csv").write_text("complaint_id\nSYN-1\n", encoding="utf-8")
    assert _build(work) != 0
    assert fake_dbt.calls == []


def test_B17_the_databricks_target_refuses_a_test_list_seed_that_differs_from_the_checked_list(work, connected,
                                                                                               fake_dbt, capfd):
    seed = work / SEEDS / "test_list.csv"
    seed.write_text(seed.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    assert _build(work) != 0
    assert "test_list.csv" in capfd.readouterr().out
    assert fake_dbt.calls == []


# The connection comes from environment variables, and the token only reaches the Databricks build


@pytest.mark.parametrize("missing", CONNECTION)
def test_B14_the_databricks_target_refuses_without_its_connection_variables(work, connected, fake_dbt, capfd,
                                                                            monkeypatch, missing):
    monkeypatch.delenv(missing)
    assert _build(work) != 0
    printed = capfd.readouterr().out
    assert missing in printed and _token() not in printed
    assert fake_dbt.calls == []


def test_B7_the_databricks_token_reaches_dbt_only_on_the_databricks_target(work, connected, fake_dbt, monkeypatch):
    key_name = "ANTHROPIC" + "_API_KEY"
    monkeypatch.setenv(key_name, "x" * 8)
    assert _build(work) == 0
    env = fake_dbt.calls[-1]["env"]
    assert env["DATABRICKS_TOKEN"] == _token() and key_name not in env
    assert dbt_run.dbt_env({"DATABRICKS_TOKEN": _token(), "PATH": "p"}) == {"PATH": "p", **dbt_run.QUIET}


def test_B14_the_databricks_profile_reads_the_connection_from_environment_variables_only():
    text = (REPO / "dbt" / "databricks" / "profiles.yml").read_text(encoding="utf-8")
    output = yaml.safe_load(text)["voc"]["outputs"]["databricks"]
    assert output["type"] == "databricks"
    assert output["host"] == "{{ env_var('DATABRICKS_HOST') }}"
    assert output["http_path"] == "{{ env_var('DATABRICKS_HTTP_PATH') }}"
    assert output["token"] == "{{ env_var('DATABRICKS_TOKEN') }}"


def test_B14_the_local_profile_has_no_databricks_target():
    outputs = yaml.safe_load((REPO / "dbt" / "profiles.yml").read_text(encoding="utf-8"))["voc"]["outputs"]
    assert all(output["type"] == "duckdb" for output in outputs.values())


# The build runs the same project, with the flag off, and prints counts and names only


def test_B17_the_databricks_build_passes_the_flag_off_and_its_own_target(work, connected, fake_dbt):
    assert _build(work) == 0
    args = fake_dbt.calls[-1]["args"]
    assert args[args.index("--target") + 1] == "databricks"
    assert Path(args[args.index("--profiles-dir") + 1]) == (work / "dbt" / "databricks").resolve()
    assert Path(args[args.index("--project-dir") + 1]) == (work / "dbt").resolve()
    assert json.loads(args[args.index("--vars") + 1]) == {"labels": _labels(), "final": False}


def test_B21_the_databricks_build_prints_counts_and_names_only(work, connected, fake_dbt, capfd):
    assert _build(work) == 0
    printed = capfd.readouterr()
    assert "2 seeds, 2 models, 1 data tests" in printed.out
    assert "passed 5" in printed.out
    assert _token() not in printed.out + printed.err
    assert "synthetic.example.invalid" not in printed.out + printed.err


def test_B21_a_failed_databricks_check_is_named_and_fails_the_command(work, connected, monkeypatch, capfd):
    fake = FakeDbt(nodes=[{"unique_id": "test.voc.product_in_label_list", "status": "fail", "failures": 2}])
    monkeypatch.setattr(dbt_run.subprocess, "run", fake)
    assert _build(work) != 0
    assert "failed: test product_in_label_list (2 rows)" in capfd.readouterr().out


def test_B14_the_local_build_is_unchanged_by_the_target_option(tmp_path, fake_dbt, monkeypatch):
    (tmp_path / "config").mkdir()
    shutil.copy(REPO / "config" / "labels.toml", tmp_path / "config" / "labels.toml")
    shutil.copytree(REPO / "dbt", tmp_path / "dbt", ignore=shutil.ignore_patterns("target", "logs"))
    shutil.copytree(FIXTURE.parent / "splits", tmp_path / "splits")
    load_month(tmp_path / DB_PATH, FIXTURE, "july_2026", _labels())
    monkeypatch.setenv("DATABRICKS_TOKEN", _token())
    assert cli.main(["dbt", "build"], env={}, root=tmp_path) == 0
    args, env = fake_dbt.calls[-1]["args"], fake_dbt.calls[-1]["env"]
    assert "--target" not in args and "DATABRICKS_TOKEN" not in env
    assert Path(args[args.index("--profiles-dir") + 1]) == (tmp_path / "dbt").resolve()


# The models keep their DuckDB form, with a Databricks branch for each DuckDB-only part


def test_B14_the_models_branch_on_the_target_for_each_duckdb_only_part():
    macros = (REPO / "dbt" / "macros" / "test_set.sql").read_text(encoding="utf-8")
    assert "read_csv(" in macros and "ref('test_list')" in macros
    curated = (REPO / "dbt" / "models" / "curated_complaints.sql").read_text(encoding="utf-8")
    assert "has_text(" in curated
    staged = (REPO / "dbt" / "models" / "stg_complaints.sql").read_text(encoding="utf-8")
    assert "'delete+insert'" in staged and "'merge'" in staged and "staged_source()" in staged


def test_B14_the_seeds_are_switched_off_for_the_local_target():
    project = yaml.safe_load((REPO / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))
    assert project["seeds"]["voc"]["+enabled"] == "{{ target.type == 'databricks' }}"


def test_B14_the_databricks_adapter_is_pinned_in_its_own_group():
    with open(REPO / "pyproject.toml", "rb") as f:
        project = tomllib.load(f)
    assert "dbt-databricks==1.13.0" in project["dependency-groups"]["databricks"]
    assert not any(d.startswith("dbt-databricks") for d in project["project"]["dependencies"])


def test_B14_the_repo_has_no_seed_folder_so_the_databricks_target_always_refuses_here():
    assert not (REPO / SEEDS).exists()


# Added in the review of #43


def _swap_test_list(work, text):
    """Replace the work folder's test list, its manifest entry and its seed copy, so only the ID check is left."""
    data = text.encode("utf-8")
    (work / "splits" / "test.csv").write_bytes(data)
    manifest = json.loads((work / "splits" / "manifest.json").read_text(encoding="utf-8"))
    manifest["lists"]["test"] = {"count": len(text.splitlines()) - 1, "sha256": hashlib.sha256(data).hexdigest()}
    (work / "splits" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (work / SEEDS / "test_list.csv").write_bytes(data)


def test_B14_the_databricks_target_refuses_a_test_list_seed_with_an_id_that_is_not_synthetic(work, connected,
                                                                                            fake_dbt, capfd):
    _swap_test_list(work, "complaint_id,content_hash\n7654321," + "0" * 64 + "\n")
    assert _build(work) != 0
    printed = capfd.readouterr().out
    assert "test_list.csv" in printed and "SYN-" in printed and "7654321" not in printed
    assert fake_dbt.calls == []


@pytest.mark.parametrize("content", [b"complaint_id,product\n", b"product,complaint_id\nMortgage,SYN-1\n",
                                     b"complaint_id\n\xff\xfeSYN-1\n"])
def test_B14_the_databricks_target_refuses_a_staged_seed_with_no_rows_a_wrong_header_or_bad_bytes(
        work, connected, fake_dbt, capfd, content):
    (work / SEEDS / "staged_complaints.csv").write_bytes(content)
    assert _build(work) != 0
    assert "staged_complaints.csv" in capfd.readouterr().out
    assert fake_dbt.calls == []


def test_B7_the_databricks_target_passes_the_catalog_and_drops_other_databricks_variables(work, connected,
                                                                                          fake_dbt, monkeypatch):
    monkeypatch.setenv("DATABRICKS_CATALOG", "synthetic_catalog")
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "synthetic")
    assert _build(work) == 0
    env = fake_dbt.calls[-1]["env"]
    assert env["DATABRICKS_CATALOG"] == "synthetic_catalog"
    assert "DATABRICKS_CONFIG_PROFILE" not in env


def test_B14_the_fixture_script_main_prepares_and_runs_the_databricks_build(tmp_path, connected, fake_dbt, capfd):
    assert _script().main([str(FIXTURE), str(tmp_path / "work")]) == 0
    printed = capfd.readouterr().out
    assert "loaded the fixture: 12 rows" in printed and "2 seeds, 2 models" in printed
    args = fake_dbt.calls[-1]["args"]
    assert args[args.index("--target") + 1] == "databricks"


def test_B14_git_ignores_any_seed_file_so_a_seed_cannot_be_committed_by_accident(tmp_path):
    # Changed in the green commit of the review of #43: the gate runs the tests on a copy of the staged
    # files, which is not a git checkout. So the repo's .gitignore is checked in a new temp repo.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copy(REPO / ".gitignore", tmp_path / ".gitignore")
    for name in ("staged_complaints.csv", "test_list.csv"):
        result = subprocess.run(["git", "check-ignore", "-q", f"dbt/seeds/{name}"], cwd=tmp_path)
        assert result.returncode == 0, name
