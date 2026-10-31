"""B14, B16, B17 and B21: the real monthly exports on Databricks (owner decision, 31 October 2026).

The owner uploads the pinned July and August exports to a Unity Catalog volume. `voc dbt build --target
databricks --month <month>` then runs the same models there on the real rows. Databricks checks the uploaded
file's SHA-256 against its pin before any model is built from it, so the rows are the same bytes the local
load checked. Only counts and check names are printed. These tests never open the network: dbt and the
Databricks query are stand-ins.
"""
import importlib.util
import json
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from voc import cli, dbt_run
from voc.labels import load_labels
from voc.load import COLUMNS

REPO = Path(__file__).resolve().parents[1]
SEEDS = Path("dbt") / "seeds"
VOLUME = "/Volumes/workspace/default/voc_raw/"


def _token():
    # A fake token, built while the test runs, never written as one string.
    return "dapi" + "0e" * 16


def _script():
    spec = importlib.util.spec_from_file_location("databricks_month_build",
                                                  REPO / "scripts" / "databricks_month_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pins():
    with open(REPO / "config" / "data_files.toml", "rb") as f:
        return tomllib.load(f)


def _labels():
    return [label.name for label in load_labels(REPO / "config" / "labels.toml")]


@pytest.fixture
def work(tmp_path):
    """A work folder made by the month script: config, the dbt project, the splits and the test list seed."""
    folder = tmp_path / "work"
    _script().prepare(folder)
    return folder


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "synthetic.example.invalid")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/synthetic")
    monkeypatch.setenv("DATABRICKS_TOKEN", _token())
    monkeypatch.delenv("DATABRICKS_CATALOG", raising=False)


class FakeDbt:
    """Stands in for the dbt child process. Records each call and writes a run_results.json."""

    def __init__(self, nodes=None, code=0):
        self.calls = []
        self.nodes = nodes if nodes is not None else [
            {"unique_id": "seed.voc.test_list", "status": "success"},
            {"unique_id": "model.voc.landed_complaints", "status": "success"},
            {"unique_id": "test.voc.landed_file_matches_pin", "status": "pass", "failures": 0},
            {"unique_id": "model.voc.stg_complaints", "status": "success"},
            {"unique_id": "model.voc.curated_complaints", "status": "success"},
        ]
        self.code = code

    def __call__(self, args, env=None, **kwargs):
        self.calls.append({"args": list(args), "env": dict(env or {})})
        target = Path(args[args.index("--target-path") + 1])
        target.mkdir(parents=True, exist_ok=True)
        (target / "run_results.json").write_text(json.dumps({"results": self.nodes}), encoding="utf-8")
        return subprocess.CompletedProcess(args, self.code)


class FakeQuery:
    """Stands in for the Databricks query after the build. Records the SQL, answers with counts."""

    def __init__(self):
        self.calls = []

    def __call__(self, env, sql):
        self.calls.append({"env": dict(env), "sql": sql})
        if "group by" in sql.lower():
            return [("august_2026", 4), ("july_2026", 5)]
        return [(3,)]


@pytest.fixture
def fake_dbt(monkeypatch):
    fake = FakeDbt()
    monkeypatch.setattr(dbt_run.subprocess, "run", fake)
    return fake


@pytest.fixture
def fake_query(monkeypatch):
    fake = FakeQuery()
    monkeypatch.setattr(dbt_run, "_databricks_query", fake)
    return fake


def _build(root, month="july_2026"):
    return cli.main(["dbt", "build", "--target", "databricks", "--month", month], env={}, root=root)


def _vars(fake):
    args = fake.calls[-1]["args"]
    return json.loads(args[args.index("--vars") + 1])


# The wrapper passes the pinned file, and nothing reaches Databricks unless the checks pass


@pytest.mark.parametrize("month", ["july_2026", "august_2026"])
def test_B16_the_month_build_passes_the_pinned_file_and_its_fingerprint_to_dbt(work, connected, fake_dbt,
                                                                               fake_query, month):
    assert _build(work, month) == 0
    pin = _pins()[month]
    found = _vars(fake_dbt)
    assert found["labels"] == _labels() and found["final"] is False
    assert found["month"] == month
    assert found["month_file"] == VOLUME + pin["file_name"]
    assert found["month_sha256"] == pin["sha256"]
    assert found["month_rows"] == pin.get("rows", 0)
    assert fake_dbt.calls[-1]["env"]["VOC_DBX_SCHEMA"] == "voc_cfpb"


def test_B16_july_has_its_row_count_pinned_from_the_profile():
    profile = json.loads((REPO / "results" / "profile_july_2026.json").read_text(encoding="utf-8"))
    assert _pins()["july_2026"]["rows"] == profile["rows"] == 672036


def test_B14_the_volume_path_follows_the_catalog(work, connected, fake_dbt, fake_query, monkeypatch):
    monkeypatch.setenv("DATABRICKS_CATALOG", "other_catalog")
    assert _build(work) == 0
    assert _vars(fake_dbt)["month_file"].startswith("/Volumes/other_catalog/default/voc_raw/")


def test_B14_a_catalog_name_that_is_not_plain_is_refused(work, connected, fake_dbt, fake_query, monkeypatch,
                                                         capfd):
    monkeypatch.setenv("DATABRICKS_CATALOG", "workspace'; drop")
    assert _build(work) != 0
    assert fake_dbt.calls == [] and fake_query.calls == []
    assert "DATABRICKS_CATALOG" in capfd.readouterr().out


def test_B14_the_month_option_needs_the_databricks_target(tmp_path, fake_dbt, fake_query, capfd):
    assert cli.main(["dbt", "build", "--month", "july_2026"], env={}, root=tmp_path) != 0
    assert fake_dbt.calls == [] and fake_query.calls == []
    assert "--month" in capfd.readouterr().out


def test_B14_the_month_build_refuses_a_staged_seed(work, connected, fake_dbt, fake_query, capfd):
    # The rows come from the volume. A staged seed would be a second source of rows.
    (work / SEEDS / "staged_complaints.csv").write_text("complaint_id\nSYN-1\n", encoding="utf-8")
    assert _build(work) != 0
    assert fake_dbt.calls == []
    assert "nothing was sent to Databricks" in capfd.readouterr().out


def test_B17_the_month_build_refuses_a_test_list_seed_that_differs_from_the_checked_list(work, connected,
                                                                                         fake_dbt, fake_query,
                                                                                         capfd):
    seed = work / SEEDS / "test_list.csv"
    seed.write_bytes(seed.read_bytes()[:-40])
    assert _build(work) != 0
    assert fake_dbt.calls == []
    assert "byte copy" in capfd.readouterr().out


@pytest.mark.parametrize("missing", ["DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"])
def test_B14_the_month_build_refuses_without_its_connection_variables(work, connected, fake_dbt, fake_query,
                                                                      monkeypatch, missing):
    monkeypatch.delenv(missing)
    assert _build(work) != 0
    assert fake_dbt.calls == [] and fake_query.calls == []


def test_B14_the_synthetic_build_keeps_its_own_schema_and_variables():
    # T021 is unchanged: without --month the seeds are used, in the voc_synthetic schema.
    profile = yaml.safe_load((REPO / "dbt" / "databricks" / "profiles.yml").read_text(encoding="utf-8"))
    schema = profile["voc"]["outputs"]["databricks"]["schema"]
    assert schema == "{{ env_var('VOC_DBX_SCHEMA', 'voc_synthetic') }}"


# The counts after the build


def test_B21_the_month_build_prints_counts_from_databricks_and_no_secret(work, connected, fake_dbt, fake_query,
                                                                        capfd):
    assert _build(work) == 0
    printed = capfd.readouterr()
    assert "stg_complaints by month: august_2026 4 rows, july_2026 5 rows" in printed.out
    assert "curated_complaints: 3 rows" in printed.out
    assert _token() not in printed.out + printed.err
    assert "synthetic.example.invalid" not in printed.out + printed.err
    for call in fake_query.calls:
        assert "workspace.voc_cfpb." in call["sql"]
        assert "narrative" not in call["sql"]


def test_B21_a_failed_month_build_asks_databricks_for_nothing(work, connected, monkeypatch, fake_query, capfd):
    fake = FakeDbt(nodes=[{"unique_id": "test.voc.landed_file_matches_pin", "status": "fail", "failures": 1}])
    monkeypatch.setattr(dbt_run.subprocess, "run", fake)
    assert _build(work) != 0
    assert fake_query.calls == []
    assert "failed: test landed_file_matches_pin (1 rows)" in capfd.readouterr().out


def test_B7_the_query_after_the_build_gets_the_connection_and_no_other_secret(work, connected, fake_dbt,
                                                                             fake_query, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-" + "ant-" + "0" * 20)
    assert _build(work) == 0
    env = fake_query.calls[-1]["env"]
    assert env["DATABRICKS_TOKEN"] == _token()
    assert "ANTHROPIC_API_KEY" not in env


# The models read the volume file and check it like the local load


def test_B14_the_landed_model_reads_the_month_file_with_every_cfpb_column():
    landed = (REPO / "dbt" / "models" / "landed_complaints.sql").read_text(encoding="utf-8")
    # Changed in the green commit: the read is the macro month_file_rows(), shared with the row checks.
    assert "month_file_rows()" in landed
    landed += (REPO / "dbt" / "macros" / "targets.sql").read_text(encoding="utf-8")
    assert "read_files(" in landed and "var('month_file')" in landed.replace('"', "'")
    for option in ("format => 'csv'", "header => true", "multiLine => true", "escape => '\"'"):
        assert option in landed, option
    for name, (column, _) in COLUMNS.items():
        assert f"`{name}`" in landed, name
        assert f"as {column}" in landed, column
    assert "as source" in landed


def test_B14_the_landed_model_is_on_only_for_a_month_build_on_databricks():
    landed = (REPO / "dbt" / "models" / "landed_complaints.sql").read_text(encoding="utf-8")
    assert "target.type == 'databricks'" in landed and "var('month'" in landed
    project = yaml.safe_load((REPO / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))
    staged_seed = project["seeds"]["voc"]["staged_complaints"]["+enabled"]
    assert "target.type == 'databricks'" in staged_seed and "var('month'" in staged_seed
    for name in ("month", "month_file", "month_sha256"):
        assert project["vars"][name] == ""
    assert project["vars"]["month_rows"] == 0
    macros = (REPO / "dbt" / "macros" / "targets.sql").read_text(encoding="utf-8")
    assert "ref('landed_complaints')" in macros


def test_B16_databricks_checks_the_file_fingerprint_before_the_staged_model_is_built():
    check = (REPO / "dbt" / "tests" / "landed_file_matches_pin.sql").read_text(encoding="utf-8")
    assert "sha2(content, 256)" in check and "binaryFile" in check
    assert "var('month_sha256')" in check.replace('"', "'")
    # dbt build skips every model below a failing test of its parent.
    assert "depends_on: {{ ref('landed_complaints') }}" in check


def test_B14_databricks_checks_the_landed_rows_like_the_local_load():
    checks = (REPO / "dbt" / "tests" / "landed_rows_are_valid.sql").read_text(encoding="utf-8")
    assert "ref('landed_complaints')" in checks
    for part in ("Date received", "Date sent to company", "Timely response?", "Complaint ID"):
        assert part in checks, part
    count = (REPO / "dbt" / "tests" / "landed_row_count_matches_pin.sql").read_text(encoding="utf-8")
    assert "var('month_rows'" in count.replace('"', "'") and "ref('landed_complaints')" in count
    schema = yaml.safe_load((REPO / "dbt" / "models" / "schema.yml").read_text(encoding="utf-8"))
    landed = next(m for m in schema["models"] if m["name"] == "landed_complaints")
    tests = {c["name"]: c["data_tests"] for c in landed["columns"]}
    assert {"not_null", "unique"} <= set(tests["complaint_id"])
    assert "not_null" in tests["date_received"]


# The owner's script


def test_B14_the_month_script_writes_only_the_test_list_seed(work):
    assert sorted(p.name for p in (work / SEEDS).iterdir()) == ["test_list.csv"]
    assert (work / SEEDS / "test_list.csv").read_bytes() == (REPO / "splits" / "test.csv").read_bytes()
    for name in ("config/labels.toml", "config/data_files.toml", "dbt/dbt_project.yml", "splits/manifest.json"):
        assert (work / name).is_file(), name


def test_B14_the_month_script_refuses_a_folder_that_is_not_empty(tmp_path):
    (tmp_path / "old.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _script().prepare(tmp_path)


def test_B14_the_month_script_main_prepares_and_runs_the_month_build(tmp_path, connected, fake_dbt, fake_query,
                                                                    capfd):
    assert _script().main(["august_2026", str(tmp_path / "work")]) == 0
    assert _vars(fake_dbt)["month"] == "august_2026"
    assert _script().main([]) == 2
    assert "usage" in capfd.readouterr().out


# Added in the review of #58


def test_B14_every_rlike_pattern_in_the_dbt_project_doubles_its_backslashes():
    # Databricks drops a backslash before an unknown escape in a string literal, so '\s' would match "s".
    # DuckDB uses regexp_matches, not rlike, so every rlike pattern is a Databricks one.
    found = 0
    for path in (REPO / "dbt").rglob("*.sql"):
        for pattern in re.findall(r"rlike '([^']*)'", path.read_text(encoding="utf-8")):
            found += 1
            assert "\\" not in pattern.replace("\\\\", ""), f"{path.name}: {pattern}"
    assert found >= 5


def test_B17_the_landed_model_leaves_out_the_test_rows_and_a_data_test_checks_it():
    landed = (REPO / "dbt" / "models" / "landed_complaints.sql").read_text(encoding="utf-8")
    assert "leave_out_test_rows(" in landed
    check = (REPO / "dbt" / "tests" / "landed_has_no_test_set_rows.sql").read_text(encoding="utf-8")
    assert "ref('landed_complaints')" in check and "test_set_ids()" in check
    assert "var('month'" in check


def test_B16_the_row_count_check_counts_the_file_itself():
    # The landed model leaves out the test rows, so the pinned count is checked on the file as read.
    count = (REPO / "dbt" / "tests" / "landed_row_count_matches_pin.sql").read_text(encoding="utf-8")
    assert "from {{ month_file_rows() }}" in count
    assert "depends_on: {{ ref('landed_complaints') }}" in count


def test_B14_the_product_check_runs_on_the_landed_rows_before_the_staged_merge():
    check = (REPO / "dbt" / "tests" / "landed_product_in_label_list.sql").read_text(encoding="utf-8")
    assert "from {{ ref('landed_complaints') }}" in check and "var('labels')" in check
    assert "product is null" in check and "var('month'" in check


def test_B21_the_owner_steps_delete_the_work_folders():
    pipeline = (REPO / "docs" / "PIPELINE.md").read_text(encoding="utf-8")
    section = pipeline[pipeline.index("## The real exports on Databricks"):]
    section = section[:section.index("\n## ", 1)]
    assert "Remove-Item -Recurse -Force $julyWork, $augustWork" in section
