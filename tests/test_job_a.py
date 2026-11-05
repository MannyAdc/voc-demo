"""Spec 004, pull request 5b: Job A (J8, J5, J16), on synthetic data only. Its three tasks, `unpack`, `dbt` and
`job_a`, run in Databricks. Their logic is tested here, with synthetic pins and zips, and the dbt task's quiet
flags are proved on a local dbt run with a deliberately failing row. No test opens a network connection."""
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"
CONTRACT = REPO / "tests" / "fixtures" / "june_contract"
MARKER = "SYNMARKER complaint text that must never be printed"
A, B, C = "a" * 64, "b" * 64, "c" * 64


def _job_a():
    from voc import job_a

    return job_a


def _definition():
    return yaml.safe_load((REPO / "cloud" / "job_a.yml").read_text(encoding="utf-8"))


def _job(definition=None):
    jobs = (definition or _definition())["resources"]["jobs"]
    assert list(jobs) == ["voc_june_job_a"]
    return jobs["voc_june_job_a"]


def _tasks(job):
    return {task["task_key"]: task for task in job["tasks"]}


def _dbt_command():
    return _tasks(_job())["dbt"]["dbt_task"]["commands"]


# The job definition (J8, J16)


def test_J16_job_a_has_the_three_tasks_by_key_and_dependency_not_by_order():
    tasks = _tasks(_job())
    assert set(tasks) == {"unpack", "dbt", "job_a"} and len(_job()["tasks"]) == 3
    assert "depends_on" not in tasks["unpack"]
    assert tasks["dbt"]["depends_on"] == [{"task_key": "unpack"}]
    assert tasks["job_a"]["depends_on"] == [{"task_key": "dbt"}]
    for key in ("unpack", "job_a"):
        assert tasks[key]["notebook_task"] == {"notebook_path": f"cloud/job_a/{key}", "source": "GIT"}


def test_J8_job_a_runs_the_public_repo_s_main_one_run_at_a_time():
    job = _job()
    assert job["git_source"] == {"git_url": "https://github.com/MannyAdc/voc-demo", "git_provider": "gitHub",
                                 "git_branch": "main"}
    assert job["max_concurrent_runs"] == 1 and job["name"] == "voc-june-job-a"


def test_J8_the_trigger_is_paused_and_watches_exactly_the_incoming_folder():
    trigger = _job()["trigger"]
    assert trigger == {"pause_status": "PAUSED",
                       "file_arrival": {"url": "/Volumes/workspace/default/voc_raw/incoming/"}}


def test_J5_the_dbt_task_prints_nothing_and_writes_no_json_files():
    commands = _dbt_command()
    assert len(commands) == 1
    for flag in ("--log-level none", "--log-level-file none", "--no-write-json"):
        assert flag in commands[0], flag


def test_J8_the_dbt_task_builds_june_with_unpacks_values_and_final_off():
    command = _dbt_command()[0]
    assert command.startswith("dbt build ")
    assert '"month": "june_2026"' in command and '"final": false' in command
    for name in ("month_file", "month_sha256", "month_rows", "labels"):
        assert "{{tasks.unpack.values." + name + "}}" in command
    dbt = _tasks(_job())["dbt"]["dbt_task"]
    assert dbt["project_directory"] == "dbt" and dbt["catalog"] == "workspace" and dbt["schema"] == "voc_june"
    assert dbt["source"] == "GIT"


def test_J8_the_dbt_task_runs_with_the_repos_dbt_databricks_pin():
    job = _job()
    environments = {env["environment_key"]: env for env in job["environments"]}
    spec = environments[_tasks(job)["dbt"]["environment_key"]]["spec"]
    assert spec == {"environment_version": "2", "dependencies": ["dbt-databricks==1.13.0"]}
    assert '"dbt-databricks==1.13.0"' in (REPO / "pyproject.toml").read_text(encoding="utf-8")


def test_J9_job_a_sends_its_success_webhook_to_the_receiver_s_destination():
    notifications = _job()["webhook_notifications"]
    assert set(notifications) == {"on_success"} and len(notifications["on_success"]) == 1


def test_J8_job_a_names_no_data_file_and_holds_no_secret():
    texts = [(REPO / "cloud" / "job_a.yml").read_text(encoding="utf-8")]
    texts += [(REPO / "cloud" / "job_a" / name).read_text(encoding="utf-8") for name in ("unpack.py", "job_a.py")]
    for text in texts:
        for word in ("CCDB_Export", "token", "secret", "password"):
            assert word.lower() not in text.lower(), word


# The run's target, from the June run log (J1, J16)


def _log(tmp_path, rows):
    path = tmp_path / "JUNE_RUNS.md"
    path.write_text("# June runs\n\n| Date | Kind | June list hash | Code hash | Reason |\n|---|---|---|---|---|\n"
                    + "".join(f"| {' | '.join(row)} |\n" for row in rows), encoding="utf-8")
    return path


def test_J16_with_no_row_in_the_run_log_job_a_refuses(tmp_path):
    with pytest.raises(_job_a().JobAError, match="no row"):
        _job_a().target(_log(tmp_path, []), real_list_hash=C)


def test_J16_the_target_is_the_last_row_with_its_list_s_kind(tmp_path):
    rows = [("2026-11-06 10:00", "synthetic", A, B, "dry run"), ("2026-11-07 10:00", "real", C, B, "the June run"),
            ("2026-11-08 10:00", "resume", C, A, "a stop by the spend limit")]
    target = _job_a().target(_log(tmp_path, rows), real_list_hash=C)
    assert (target.kind, target.entry_kind, target.list_hash, target.code_hash, target.row) == ("real", "resume", C, A, 3)


def test_J16_a_run_log_that_breaks_its_rules_is_refused(tmp_path):
    with pytest.raises(Exception, match="synthetic"):
        _job_a().target(_log(tmp_path, [("2026-11-06 10:00", "synthetic", C, B, "dry run")]), real_list_hash=C)


def test_J16_the_real_kind_uses_the_june_pin_and_the_dry_run_s_pin_waits_for_pull_request_9():
    pin = _job_a().pin_for(REPO, "real")
    assert pin["file_name"].endswith(".csv") and pin["zip_file_name"].endswith(".zip") and pin["rows"] > 0
    with pytest.raises(_job_a().JobAError, match="pull request 9"):
        _job_a().pin_for(REPO, "synthetic")


# unpack: the zip and the CSV against the pin, before dbt reads a byte (J8, J5)


def _rows():
    return FIXTURE.read_text(encoding="utf-8")


def _zip_and_pin(tmp_path, text=None, name="june.csv", zip_name="june.zip", extra=None):
    data = (_rows() if text is None else text).encode("utf-8")
    folder = tmp_path / "incoming"
    folder.mkdir(exist_ok=True)
    path = folder / zip_name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, data)
        for member, payload in (extra or {}).items():
            archive.writestr(member, payload)
    rows = len(list(csv.reader(io.StringIO(data.decode("utf-8"))))) - 1
    pin = {"file_name": "june.csv", "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
           "rows": rows, "zip_file_name": "june.zip", "zip_size_bytes": path.stat().st_size,
           "zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return folder, pin


def _unpack(folder, out, pin):
    return _job_a().unpack(folder, out, pin, REPO / "config" / "labels.toml")


def test_J8_unpack_writes_the_pinned_csv_and_gives_dbt_its_values(tmp_path):
    folder, pin = _zip_and_pin(tmp_path)
    values = _unpack(folder, tmp_path / "june", pin)
    path = tmp_path / "june" / "june.csv"
    assert path.read_bytes() == FIXTURE.read_bytes()
    assert values["month_file"] == str(path) and values["month_sha256"] == pin["sha256"]
    assert values["month_rows"] == str(pin["rows"]) and json.loads(values["labels"])


@pytest.mark.parametrize("change", ["zip_file_name", "zip_size_bytes", "zip_sha256"])
def test_J8_a_zip_that_is_not_the_pinned_zip_is_refused(tmp_path, change):
    folder, pin = _zip_and_pin(tmp_path)
    pin[change] = {"zip_file_name": "other.zip", "zip_size_bytes": 1, "zip_sha256": A}[change]
    with pytest.raises(_job_a().JobAError, match="pin"):
        _unpack(folder, tmp_path / "june", pin)


def test_J8_a_second_file_in_the_incoming_folder_is_refused(tmp_path):
    folder, pin = _zip_and_pin(tmp_path)
    (folder / "other.txt").write_text("x", encoding="utf-8")
    with pytest.raises(_job_a().JobAError, match="exactly one"):
        _unpack(folder, tmp_path / "june", pin)


@pytest.mark.parametrize("name, extra", [("other.csv", None), ("dir/june.csv", None), ("../june.csv", None),
                                         ("june.csv", {"second.csv": b"x"})])
def test_J8_a_zip_whose_one_member_is_not_the_pinned_csv_is_refused(tmp_path, name, extra):
    folder, pin = _zip_and_pin(tmp_path, name=name, extra=extra)
    with pytest.raises(_job_a().JobAError):
        _unpack(folder, tmp_path / "june", pin)
    assert not (tmp_path / "june" / "june.csv").exists()


@pytest.mark.parametrize("change", ["size_bytes", "sha256"])
def test_J8_a_csv_that_is_not_the_pinned_csv_is_refused_and_removed(tmp_path, change):
    folder, pin = _zip_and_pin(tmp_path)
    pin[change] = {"size_bytes": 1, "sha256": A}[change]
    with pytest.raises(_job_a().JobAError, match="pin"):
        _unpack(folder, tmp_path / "june", pin)
    assert not (tmp_path / "june" / "june.csv").exists()


def _with_row(text, row):
    return text.rstrip("\n") + "\n" + row + "\n"


@pytest.mark.parametrize("bad", [
    f'2026-06-01,Mortgage,"{MARKER}"',                                  # too few fields
    "2026-06-01," + ",".join([f'"{MARKER}"'] * 16),                      # too many fields
    f'2026-06-01,Mortgage,,,,"{MARKER} with an unclosed quote,,,,,,,,,,',  # a quote that never closes
])
def test_J5_a_malformed_row_is_refused_before_dbt_with_fixed_text_only(tmp_path, capsys, bad):
    """The hard requirement of pull request 5b (owner decision, 5 November): a row that would make Spark's FAILFAST
    parser fail, whose error can quote the row, is refused first, and the refusal holds no complaint text."""
    folder, pin = _zip_and_pin(tmp_path, text=_with_row(_rows(), bad))
    with pytest.raises(_job_a().JobAError) as refused:
        _unpack(folder, tmp_path / "june", pin)
    out = capsys.readouterr()
    for text in (str(refused.value), out.out, out.err):
        assert "SYNMARKER" not in text
    assert not (tmp_path / "june" / "june.csv").exists()


def test_J8_a_header_that_is_not_the_cfpb_header_is_refused(tmp_path):
    lines = _rows().splitlines()
    folder, pin = _zip_and_pin(tmp_path, text="\n".join([lines[0].replace("Product", "Produkt")] + lines[1:]) + "\n")
    with pytest.raises(_job_a().JobAError, match="header"):
        _unpack(folder, tmp_path / "june", pin)


def test_J8_a_row_count_that_is_not_the_pinned_count_is_refused(tmp_path):
    folder, pin = _zip_and_pin(tmp_path)
    pin["rows"] += 1
    with pytest.raises(_job_a().JobAError, match="rows"):
        _unpack(folder, tmp_path / "june", pin)


def test_J5_unpack_prints_nothing(tmp_path, capsys):
    folder, pin = _zip_and_pin(tmp_path)
    _unpack(folder, tmp_path / "june", pin)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# The hard requirement: the dbt task's flags leave no complaint text in any output (J5, J13)


def _dbt_project(tmp_path):
    project = tmp_path / "project"
    (project / "models").mkdir(parents=True)
    (project / "dbt_project.yml").write_text("name: synthetic\nversion: '1.0.0'\nconfig-version: 2\nprofile: synthetic\n"
                                             "model-paths: ['models']\nseed-paths: ['seeds']\n", encoding="utf-8")
    (project / "profiles.yml").write_text(
        "synthetic:\n  target: local\n  outputs:\n    local:\n      type: duckdb\n"
        f"      path: '{(tmp_path / 'synthetic.duckdb').as_posix()}'\n      threads: 1\n", encoding="utf-8")
    # A row that fails on its cast, as a malformed real row would, with the marker in the failing value.
    # As in Job A, the complaint text comes from a data file, not from the SQL: a seed holds a row whose value fails
    # its cast in a table model (a table, not dbt's default view, so the cast runs at build time).
    (project / "seeds").mkdir()
    (project / "seeds" / "rows.csv").write_text(f'x\n"{MARKER}"\n', encoding="utf-8")
    (project / "models" / "failing.sql").write_text("{{ config(materialized='table') }}\n"
                                                    "select cast(x as integer) as x from {{ ref('rows') }}\n",
                                                    encoding="utf-8")
    return project


def _run_dbt(project, flags):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("DATABRICKS_")}
    env.update({"DBT_SEND_ANONYMOUS_USAGE_STATS": "False", "DBT_ENGINE_SEND_ANONYMOUS_USAGE_STATS": "False",
                "DO_NOT_TRACK": "1"})
    args = [sys.executable, "-c", "from dbt.cli.main import cli; cli()", "build", "--project-dir", str(project),
            "--profiles-dir", str(project), "--no-version-check", *flags]
    return subprocess.run(args, cwd=project, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def _files_with_marker(folder):
    """Every file dbt wrote or kept that holds the marker, other than the input data itself (the seed)."""
    seeds = Path(folder) / "seeds"
    return [p for p in Path(folder).rglob("*") if p.is_file() and p.suffix != ".duckdb" and seeds not in p.parents
            and "SYNMARKER" in p.read_text(encoding="utf-8", errors="replace")]


def test_J5_without_the_flags_a_failing_row_does_leak_so_the_test_can_see_a_leak(tmp_path):
    project = _dbt_project(tmp_path)
    result = _run_dbt(project, [])
    assert result.returncode != 0
    assert "SYNMARKER" in result.stdout + result.stderr or _files_with_marker(project)


def test_J5_with_the_committed_flags_a_failing_row_leaves_no_text_in_any_output_or_file(tmp_path):
    project = _dbt_project(tmp_path)
    flags = _dbt_command()[0].split("--vars")[0].split()[2:]  # the flags the committed command passes before --vars
    assert flags == ["--log-level", "none", "--log-level-file", "none", "--no-write-json"]
    result = _run_dbt(project, flags)
    assert result.returncode != 0
    assert "SYNMARKER" not in result.stdout + result.stderr
    assert _files_with_marker(project) == []


# job_a: the frozen sample's rows, the figures and the exit value (J8, J16)


def _sample(tmp_path, rows):
    """A June list and manifest made from these (complaint_id, product, narrative) rows."""
    from voc.data import content_hash

    folder = tmp_path / "splits" / "june"
    folder.mkdir(parents=True)
    data = ("complaint_id,content_hash\n"
            + "".join(f"{cid},{content_hash(narrative, product)}\n" for cid, product, narrative in rows)).encode()
    (folder / "june.csv").write_bytes(data)
    (folder / "manifest.json").write_text(json.dumps({"lists": {"june": {"count": len(rows),
                                                                         "sha256": hashlib.sha256(data).hexdigest()}}}),
                                          encoding="utf-8")
    return tmp_path


ROWS = [("SYN-1", "Mortgage", "Synthetic text: my payment was applied late."),
        ("SYN-2", "Credit card", "Synthetic text: a fee I did not expect.")]


def test_J8_the_sample_rows_must_be_the_frozen_list_with_its_hashes(tmp_path):
    root = _sample(tmp_path, ROWS)
    assert _job_a().checked_sample(root, ROWS) == 2
    with pytest.raises(_job_a().JobAError, match="not in"):
        _job_a().checked_sample(root, ROWS[:1] + [("SYN-3", "Mortgage", "x")])
    with pytest.raises(_job_a().JobAError, match="missing"):
        _job_a().checked_sample(root, ROWS[:1])
    with pytest.raises(_job_a().JobAError, match="hash"):
        _job_a().checked_sample(root, [ROWS[0], ("SYN-2", "Credit card", "changed")])


def test_J8_the_figures_follow_the_test_run_s_worst_case_and_july_s_cost(tmp_path):
    from voc import pipeline
    from voc.budget import load_config, worst_case
    from voc.labels import load_labels
    from voc.baselines import cut_text
    from voc.prompt import build_prompt
    from voc.replay import MAX_RETRIES

    figures = _job_a().figures(REPO, ROWS, used_tokens=1000)
    version = pipeline.load_prompt_version(REPO, "v1")
    labels = load_labels(REPO / "config" / "labels.toml")
    names, defined = [label.name for label in labels], pipeline.definitions(labels)
    margin = load_config(REPO)["input_margin_tokens"]
    per_try = sum(worst_case(build_prompt(version.instructions, names, cut_text(narrative)[0], complaint_id=cid,
                                          definitions=defined).prompt, version.settings["max_tokens"], margin)
                  for cid, _, narrative in ROWS)
    assert figures["complaints"] == figures["calls"] == 2
    assert figures["worst_case_tokens"] == per_try * (MAX_RETRIES + 1)
    assert figures["tokens_left_under_cap"] == load_config(REPO)["cap_tokens"] - 1000
    assert figures["expected_cost_usd"] == "0.00"  # 2 calls at $0.2373 per 1,000


def test_J16_the_exit_value_has_exactly_the_contract_s_keys_and_types():
    target = _job_a().Target(kind="synthetic", entry_kind="synthetic", list_hash=A, code_hash=B, row=1)
    sample = json.loads((CONTRACT / "job_a_exit.json").read_text(encoding="utf-8"))
    figures = {k: sample[k] for k in ("complaints", "calls", "worst_case_tokens", "tokens_left_under_cap",
                                      "expected_cost_usd")}
    value = json.loads(_job_a().exit_value(target, {"sha256": "d" * 64, "zip_sha256": "e" * 64}, figures))
    assert set(value) == set(sample)
    assert value == {**sample, "june_list_sha256": A, "code_sha256": B}


@pytest.mark.parametrize("cost", ["0.5", "1", "abc", "0.499"])
def test_J16_an_expected_cost_that_is_not_two_decimals_is_refused(cost):
    target = _job_a().Target(kind="real", entry_kind="real", list_hash=A, code_hash=B, row=1)
    figures = {"complaints": 1, "calls": 1, "worst_case_tokens": 1, "tokens_left_under_cap": 1, "expected_cost_usd": cost}
    with pytest.raises(_job_a().JobAError):
        _job_a().exit_value(target, {"sha256": C, "zip_sha256": C}, figures)
