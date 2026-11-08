"""Spec 004, pull request 5b: Job A (J8, J5, J16), on synthetic data only. Its three tasks, `unpack`, `dbt` and
`job_a`, run in Databricks. Their logic is tested here, with synthetic pins and zips, and the dbt task's quiet
flags are proved on a local dbt run with a deliberately failing row. No test opens a network connection."""
import csv
import hashlib
import io
import json
import re
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
    from voc.frozen import JuneRunsError

    with pytest.raises(JuneRunsError, match="synthetic"):
        _job_a().target(_log(tmp_path, [("2026-11-06 10:00", "synthetic", C, B, "dry run")]), real_list_hash=C)


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
    previous = csv.field_size_limit(2**31 - 1)  # so a long synthetic field can be counted here
    try:
        rows = len(list(csv.reader(io.StringIO(data.decode("utf-8"))))) - 1
    finally:
        csv.field_size_limit(previous)
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


def _ran_the_model(project):
    """dbt compiled and ran the failing model, so a refusal is the model's failure, not an early stop (review of
    #94, minor 2: with an unknown flag dbt exits 2 having compiled nothing)."""
    return list((project / "target" / "run").rglob("failing.sql")) != []


def test_J5_without_the_flags_a_failing_row_does_leak_so_the_test_can_see_a_leak(tmp_path):
    project = _dbt_project(tmp_path)
    result = _run_dbt(project, [])
    assert result.returncode == 1 and _ran_the_model(project)
    assert "SYNMARKER" in result.stdout + result.stderr or _files_with_marker(project)


def test_J5_with_the_committed_flags_a_failing_row_leaves_no_text_in_any_output_or_file(tmp_path):
    project = _dbt_project(tmp_path)
    flags = _dbt_command()[0].split("--vars")[0].split()[2:]  # the flags the committed command passes before --vars
    assert flags == ["--log-level", "none", "--log-level-file", "none", "--no-write-json"]
    result = _run_dbt(project, flags)
    assert result.returncode == 1 and _ran_the_model(project)
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
    assert figures["expected_cost_usd"] == "0.01"  # 2 calls at $0.2373 per 1,000, rounded up


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


# The review of #94 and the owner's decisions of 6 November


def test_J8_job_a_has_a_timeout_and_no_failure_email():
    """Changed in the second fix round (owner decision on minor 5): Job A sends no failure email, an output nobody
    checks. The owner watches the job page after the upload. Renamed in the third fix round."""
    job = _job()
    assert job["timeout_seconds"] == 3600
    assert "email_notifications" not in job
    assert "@" not in (REPO / "cloud" / "job_a.yml").read_text(encoding="utf-8")


def test_J8_the_trigger_and_the_notebooks_use_the_same_folders():
    job_a = _job_a()
    assert job_a.INCOMING == job_a.VOLUME + "/incoming" and job_a.JUNE_FOLDER == job_a.VOLUME + "/june"
    assert _job()["trigger"]["file_arrival"]["url"] == job_a.INCOMING + "/"


def _root(tmp_path, kinds, list_hash=None, code=None, gates=("june-check", "failcheck")):
    """A checkout with the synthetic June list and a run log whose rows have these kinds."""
    from voc.frozen import code_hash

    root = _sample(tmp_path, ROWS)
    shutil.copytree(REPO / "config", root / "config")  # the pin, which the gates name, as a checkout has it
    listed = list_hash or hashlib.sha256((root / "splits" / "june" / "june.csv").read_bytes()).hexdigest()
    code = code or code_hash(root)
    (root / "runs").mkdir()
    _log(root / "runs", [(f"2026-11-0{n + 6} 10:00", kind, listed, code, "a reason") for n, kind in enumerate(kinds)])
    if gates:
        _gates(root, [("2026-11-05 09:00", gate, _real_pin_sha(), code, "a pass") for gate in gates])
    return root


def _real_pin_sha():
    import tomllib

    with open(REPO / "config" / "data_files.toml", "rb") as f:
        return tomllib.load(f)["june_2026"]["sha256"]


def _gates(root, rows):
    """Rows of five cells are passes, written with the Result column the log gained in the third fix round."""
    return _gate_rows(root, [row if len(row) == 6 else (row[0], row[1], "pass", *row[2:]) for row in rows])


def test_J16_the_checked_target_is_the_last_row_when_its_list_and_code_are_this_checkout_s(tmp_path):
    root = _root(tmp_path, ["real"])
    target = _job_a().checked_target(root)
    assert (target.kind, target.entry_kind, target.row) == ("real", "real", 1)


@pytest.mark.parametrize("later", ["resume", "reproduction", "second"])
def test_J1_job_a_refuses_a_later_row_until_it_can_read_the_june_ledger(tmp_path, later):
    """Owner decision, 6 November (review of #94, minor 4): a later row's figures need the June ledger's use, which
    Job A cannot read until pull request 6. So it refuses rather than print full-run figures."""
    root = _root(tmp_path, ["real", later])
    with pytest.raises(_job_a().JobAError, match="pull request 6"):
        _job_a().checked_target(root)


def test_J16_job_a_refuses_a_row_whose_list_is_not_the_june_list(tmp_path):
    """Review of #94, minor 6: the list Job A checks must be the list the target row names."""
    root = _root(tmp_path, ["synthetic"], list_hash=A)
    with pytest.raises(_job_a().JobAError, match="June list"):
        _job_a().checked_target(root)


def test_J16_job_a_refuses_code_that_is_not_the_row_s_frozen_code(tmp_path):
    root = _root(tmp_path, ["real"], code=B)
    with pytest.raises(_job_a().JobAError, match="frozen code"):
        _job_a().checked_target(root)


@pytest.mark.parametrize("notebook, first_use", [("unpack.py", "unpack("), ("job_a.py", "spark_counts(")])
def test_J16_both_notebooks_check_the_target_before_they_touch_the_june_file(notebook, first_use):
    """Review of #94, minor 5: `unpack` and `dbt` handle the June file, so the code check runs in `unpack` too."""
    text = (REPO / "cloud" / "job_a" / notebook).read_text(encoding="utf-8")
    assert "checked_target(root)" in text and "target_for(" not in text
    assert text.index("checked_target(root)") < text.index(first_use)


def test_J8_the_june_pin_holds_the_narrative_count():
    pin = _job_a().pin_for(REPO, "real")
    assert pin["rows"] == 620794 and pin["narratives"] == 16820


def test_J8_a_pin_without_a_narrative_count_is_refused(tmp_path, monkeypatch):
    import voc.datafile

    real = voc.datafile.load_pins(REPO / "config" / "data_files.toml")
    pins = {**real, "june_2026": {k: v for k, v in real["june_2026"].items() if k != "narratives"}}
    monkeypatch.setattr(voc.datafile, "load_pins", lambda path: pins)
    with pytest.raises(_job_a().JobAError, match="narratives"):
        _job_a().pin_for(REPO, "real")


def test_J8_job_a_counts_the_file_as_dbt_reads_it():
    """Owner decision, 6 November: Job A counts the rows and narratives Spark reads from the file, with dbt's own
    options, so a multi-line parsing difference cannot pass quietly."""
    import re

    macro = (REPO / "dbt" / "macros" / "targets.sql").read_text(encoding="utf-8")
    options = re.search(r"read_files\('\{\{ var\(\"month_file\"\) \| replace\(\"'\", \"''\"\) \}\}', (.*?)\)\n",
                        macro, re.S).group(1)
    sql = _job_a().count_sql("/Volumes/x/june/june.csv")
    assert " ".join(f"read_files('/Volumes/x/june/june.csv', {options})".split()) in " ".join(sql.split())
    assert "count(*) as rows" in sql and r"`Consumer complaint narrative` rlike '\\S'" in sql
    with pytest.raises(_job_a().JobAError):
        _job_a().count_sql("/Volumes/x/june/it's.csv")


def test_J8_job_a_refuses_a_row_or_narrative_count_that_is_not_the_pin_s():
    pin = {"rows": 10, "narratives": 4}
    _job_a().checked_counts(pin, 10, 4)
    with pytest.raises(_job_a().JobAError, match="rows") as refused:
        _job_a().checked_counts(pin, 11, 4)
    assert "11" in str(refused.value) and "10" in str(refused.value)
    with pytest.raises(_job_a().JobAError, match="narratives"):
        _job_a().checked_counts(pin, 10, 3)


def test_J8_the_job_a_notebook_checks_the_counts_before_the_sample():
    text = (REPO / "cloud" / "job_a" / "job_a.py").read_text(encoding="utf-8")
    assert "checked_counts(" in text and "spark_counts(" in text
    assert text.index("checked_counts(") < text.index("checked_sample(")


def _june_csv(narratives):
    """The CFPB header and one synthetic row per narrative, written by csv as the CFPB writes it."""
    from voc.repo_checks import CFPB_COLUMNS

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CFPB_COLUMNS)
    for n, narrative in enumerate(narratives):
        row = ["2026-06-01", "Mortgage", "", "Issue", "", narrative, "", "Company", "NY", "10001", "", "Web",
               "2026-06-02", "Closed with explanation", "Yes", f"SYN-{n + 1}"]
        writer.writerow(row)
    return buffer.getvalue()


def test_J8_the_laptop_check_counts_rows_narratives_and_line_breaks(tmp_path):
    """Owner decision, 6 November: the owner checks the June zip on the laptop as `unpack` will, before the upload.
    A narrative counts as text where it holds a character other than Java's white space, as Spark's `rlike '\\S'`
    reads it, so a no-break space counts."""
    text = _june_csv(["one line", "two\nlines", "a\r\nWindows break", "a lone\rreturn", "", " \t ", " "])
    folder, pin = _zip_and_pin(tmp_path, text=text)
    counts = _job_a().june_check(next(folder.iterdir()), pin, REPO / "config" / "labels.toml")
    assert counts == {"rows": 7, "narratives": 5, "fields_with_line_breaks": 3, "fields_with_lone_returns": 1}


def test_J8_the_laptop_check_refuses_as_unpack_does_and_leaves_no_copy(tmp_path, monkeypatch):
    import tempfile

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    folder, pin = _zip_and_pin(tmp_path, text=_june_csv(["one"]))
    pin["rows"] += 1
    with pytest.raises(_job_a().JobAError, match="rows"):
        _job_a().june_check(next(folder.iterdir()), pin, REPO / "config" / "labels.toml")
    assert list(scratch.iterdir()) == []
    _job_a().june_check(next(folder.iterdir()), {**pin, "rows": 1}, REPO / "config" / "labels.toml")
    assert list(scratch.iterdir()) == []


def test_J8_the_laptop_check_prints_counts_and_says_whether_they_match_the_pin():
    counts = {"rows": 10, "narratives": 4, "fields_with_line_breaks": 2, "fields_with_lone_returns": 0}
    lines = _job_a().format_june_check(counts, {"rows": 10, "narratives": 4})
    assert lines == ["rows: 10 (pin: 10, matches)", "narratives: 4 (pin: 4, matches)",
                     "fields with line breaks: 2", "fields with a lone carriage return: 0"]
    lines = _job_a().format_june_check({**counts, "narratives": 5}, {"rows": 10, "narratives": 4})
    assert lines[1] == "narratives: 5 (pin: 4, DIFFERS)"


def test_J8_the_cli_has_the_laptop_check(capsys):
    from voc.cli import main

    with pytest.raises(SystemExit):
        main(["june-check", "--help"])
    assert "counts and hashes only" in capsys.readouterr().out  # changed in the third fix round


def test_J8_the_cli_refuses_a_zip_that_is_not_the_june_pin_s_with_fixed_text(tmp_path, capsys):
    from voc.cli import main

    folder, _ = _zip_and_pin(tmp_path, text=_june_csv([MARKER]))
    env = {"VOC_JUNE_DATA_DIR": str(tmp_path)}
    assert main(["june-check", "--zip", str(next(folder.iterdir()))], env=env, root=REPO) == 1
    out = capsys.readouterr().out
    assert out.startswith("error: refused, as Job A's unpack would refuse it: the zip is not the pinned zip")
    assert "SYNMARKER" not in out and str(tmp_path) not in out


def test_J12_the_figures_use_the_june_cap_not_the_laptop_s(monkeypatch):
    """Review of #94, minor 7: the June ledger's cap has its own name in config/budget.toml."""
    import voc.budget

    from voc.budget import load_config

    assert load_config(REPO)["june_cap_tokens"] == 40_000_000
    real = voc.budget.load_config
    monkeypatch.setattr(voc.budget, "load_config", lambda root: {**real(root), "cap_tokens": 7, "june_cap_tokens": 500})
    assert _job_a().figures(REPO, ROWS, 100)["tokens_left_under_cap"] == 400


def test_J12_the_expected_cost_is_rounded_up_to_the_cent():
    """Review of #94, nit: rounding up never shows less than the expected cost."""
    from decimal import Decimal

    assert _job_a().expected_cost(Decimal("0.2373"), 2) == "0.01"
    assert _job_a().expected_cost(Decimal("0.2373"), 2073) == "0.50"
    assert _job_a().expected_cost(Decimal("0.2373"), 0) == "0.00"
    assert _job_a().expected_cost(Decimal("1.00"), 1000) == "1.00"


HOSTILE = [("SYN-1", f"Mortgage {MARKER}", f"{MARKER} narrative"), ("SYN-2", "Credit card", f"{MARKER} again")]


@pytest.mark.parametrize("rows", [HOSTILE, HOSTILE[:1], [HOSTILE[0], ("SYN-3", MARKER, MARKER)],
                                  [HOSTILE[0], ("SYN-2", "Credit card", MARKER + " changed")]])
def test_J5_the_sample_check_holds_no_complaint_text(tmp_path, capsys, rows):
    """Review of #94, minor 8: J5's hostile-text test of `checked_sample`."""
    root = _sample(tmp_path, HOSTILE)
    try:
        result = _job_a().checked_sample(root, rows)
        text = str(result)
    except _job_a().JobAError as refused:
        text = str(refused)
    out = capsys.readouterr()
    for each in (text, out.out, out.err):
        assert "SYNMARKER" not in each


def test_J5_the_figures_hold_no_complaint_text(capsys):
    """Review of #94, minor 8: J5's hostile-text test of `figures`."""
    figures = _job_a().figures(REPO, HOSTILE, 0)
    out = capsys.readouterr()
    assert "SYNMARKER" not in json.dumps(figures) + out.out + out.err


@pytest.mark.parametrize("error", ["zlib", "eof", "not_implemented", "runtime"])
def test_J8_unpack_removes_the_csv_on_any_failure_with_fixed_text(tmp_path, monkeypatch, error):
    """Review of #94, nit: every failure after the CSV is written removes it, with fixed text."""
    import zlib

    raised = {"zlib": zlib.error(MARKER), "eof": EOFError(MARKER), "not_implemented": NotImplementedError(MARKER),
              "runtime": RuntimeError(MARKER)}[error]

    def fail(path, pin):
        raise raised

    monkeypatch.setattr(_job_a(), "_check_shape", fail)
    folder, pin = _zip_and_pin(tmp_path)
    with pytest.raises(_job_a().JobAError) as refused:
        _unpack(folder, tmp_path / "june", pin)
    assert "SYNMARKER" not in str(refused.value) and refused.value.__cause__ is None
    assert refused.value.__context__ is None  # changed in the third fix round: no earlier exception at all
    assert not (tmp_path / "june" / "june.csv").exists()


def test_J8_an_empty_csv_is_refused_with_fixed_text_and_removed(tmp_path):
    folder, pin = _zip_and_pin(tmp_path, text="")
    with pytest.raises(_job_a().JobAError, match="empty"):
        _unpack(folder, tmp_path / "june", pin)
    assert not (tmp_path / "june" / "june.csv").exists()


def test_J8_a_narrative_longer_than_python_s_default_field_limit_is_read(tmp_path):
    """Review of #94, minor 3: Python's csv refuses a field over 131,072 characters by default. Spark has no such
    limit, so unpack must not refuse a long narrative that Spark reads."""
    import csv as csv_module

    before = csv_module.field_size_limit()
    folder, pin = _zip_and_pin(tmp_path, text=_june_csv(["x" * 200_000]))
    _unpack(folder, tmp_path / "june", pin)
    assert csv_module.field_size_limit() == before


def test_J8_a_label_with_an_apostrophe_is_refused_since_the_dbt_command_quotes_with_one(tmp_path):
    """Review of #94, nit: the labels go inside the dbt command's single-quoted `--vars`."""
    from voc.labels import load_labels

    assert not any("'" in label.name for label in load_labels(REPO / "config" / "labels.toml"))
    text = (REPO / "config" / "labels.toml").read_text(encoding="utf-8")
    labels = tmp_path / "labels.toml"
    labels.write_text(text.replace('name = "Mortgage"', 'name = "Mortgage\'s"'), encoding="utf-8")
    assert labels.read_text(encoding="utf-8") != text
    folder, pin = _zip_and_pin(tmp_path)
    with pytest.raises(_job_a().JobAError, match="apostrophe"):
        _job_a().unpack(folder, tmp_path / "june", pin, labels)


# The failing-row check in Databricks (owner decision, 6 November: a gate before the June upload)


def _failcheck():
    jobs = yaml.safe_load((REPO / "cloud" / "failcheck.yml").read_text(encoding="utf-8"))["resources"]["jobs"]
    assert list(jobs) == ["voc_june_failcheck"]
    return jobs["voc_june_failcheck"]


def test_J5_the_failcheck_job_runs_job_a_s_dbt_command_on_its_own_rows_then_a_control_without_the_flags():
    job = _failcheck()
    tasks = _tasks(job)
    assert set(tasks) == {"make_rows", "dbt", "dbt_control"} and len(job["tasks"]) == 3
    assert job["name"] == "voc-june-failcheck" and job["max_concurrent_runs"] == 1 and "trigger" not in job
    assert job["git_source"] == _job()["git_source"] and job["environments"] == _job()["environments"]
    assert tasks["make_rows"]["notebook_task"] == {"notebook_path": "cloud/failcheck/make_rows", "source": "GIT"}
    job_a_dbt = _tasks(_job())["dbt"]["dbt_task"]
    command = job_a_dbt["commands"][0].replace("tasks.unpack.values.", "tasks.make_rows.values.").replace(
        '"month": "june_2026"', '"month": "failcheck"')
    assert tasks["dbt"]["depends_on"] == [{"task_key": "make_rows"}]
    assert tasks["dbt"]["dbt_task"] == {**job_a_dbt, "commands": [command], "schema": "voc_failcheck"}
    assert tasks["dbt"]["environment_key"] == _tasks(_job())["dbt"]["environment_key"]
    control = tasks["dbt_control"]
    assert control["depends_on"] == [{"task_key": "dbt"}] and control["run_if"] == "ALL_DONE"
    assert control["dbt_task"]["commands"] == [command.replace(" --log-level none --log-level-file none --no-write-json", "")]
    assert "--log-level" not in control["dbt_task"]["commands"][0]


def test_J5_the_failcheck_rows_hold_a_row_that_unpack_would_refuse(tmp_path):
    """Its short row makes Spark's FAILFAST parser fail, whose error can quote the row. Job A's unpack refuses it
    first, so the failcheck writes its rows itself, to reach dbt."""
    from voc import failcheck
    from voc.repo_checks import CFPB_COLUMNS

    values = failcheck.write_rows(tmp_path, REPO / "config" / "labels.toml")
    path = Path(values["month_file"])
    assert path == tmp_path / "failcheck.csv"
    records = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
    assert records[0] == list(CFPB_COLUMNS)
    assert [len(r) for r in records[1:]] == [16, 16, 15] and failcheck.MARKER in records[-1][5]
    assert all(r[-1].startswith("SYN-") for r in records[1:3])
    assert values["month_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest() and values["month_rows"] == "3"
    with pytest.raises(_job_a().JobAError, match="fields"):
        _job_a()._check_shape(path, {"rows": 3})


def test_J5_the_failcheck_notebook_writes_its_rows_and_sets_the_values():
    text = (REPO / "cloud" / "failcheck" / "make_rows.py").read_text(encoding="utf-8")
    assert "write_rows(FOLDER" in text and "taskValues.set" in text and "print(" not in text


def _robot_check():
    import importlib.util

    spec = importlib.util.spec_from_file_location("robot_check", REPO / "cloud" / "failcheck" / "robot_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_J13_the_robot_check_holds_no_secret_and_the_failcheck_s_marker():
    from voc import failcheck

    check = _robot_check()
    assert check.CLIENT_ID == "" and check.CLIENT_SECRET == "" and check.RUN_ID == 0
    assert check.MARKER == failcheck.MARKER


def test_J13_the_robot_check_finds_the_marker_in_fields_and_archives():
    import tarfile

    check = _robot_check()
    marker = check.MARKER
    assert check.places({"a": [{"b": "x"}, {"c": f"x {marker} y"}], "d": marker}) == ["$.a[1].c", "$.d"]
    assert check.places({"a": "nothing"}) == []
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in (("target/run.sql", b"select 1"), ("logs/dbt.log", f"error {marker}".encode())):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    assert check.archive_places(buffer.getvalue()) == (2, ["logs/dbt.log"])
    # Changed in the second fix round (serious 1): a download it cannot read is reported as unread, never searched.
    assert check.archive_places(f"not an archive {marker}".encode()) is None


def test_J13_the_robot_check_reports_states_and_places_only(monkeypatch):
    """Changed in the second fix round: the lines are the new report's, with both scopes asked for."""
    check = _robot_check()
    lines = _report(check, monkeypatch, _replies(check))
    assert lines[0] == "all-apis token: refused, HTTP 400"
    assert "make_rows: SUCCESS" in lines and "dbt: FAILED" in lines and "dbt_control: FAILED" in lines
    assert "dbt: output: marker nowhere" in lines and "dbt: artifacts: files: 1, marker in: nowhere" in lines
    assert "dbt_control: output: marker $.error" in lines
    assert "query history: HTTP 403, PERMISSION_DENIED" in lines
    assert check.MARKER not in "\n".join(lines)


# The second review of #94, on its fix round, and the owner's decisions on it (6 November)


def test_J1_a_real_row_needs_both_gates_passed_for_its_code_and_the_june_pin(tmp_path):
    """Owner decision on minor 2: the robot's leak check and june-check must pass, for the code and pin of the real
    row, before the row is written. Job A refuses a real row without both passes."""
    root = _root(tmp_path, ["real"], gates=("june-check",))
    with pytest.raises(_job_a().JobAError, match="failcheck"):
        _job_a().checked_target(root)
    root = _root(tmp_path / "b", ["real"], gates=())
    with pytest.raises(_job_a().JobAError, match="gate"):
        _job_a().checked_target(root)


def test_J1_a_gate_pass_for_other_code_or_another_pin_or_after_the_row_does_not_count(tmp_path):
    from voc.frozen import JuneRunsError, check_gates, read_gates, read_runs

    root = _root(tmp_path, ["real"], gates=())
    entry = read_runs(root / "runs" / "JUNE_RUNS.md")[0]
    pin = _real_pin_sha()
    good = [("2026-11-05 09:00", gate, pin, entry.code_hash, "a pass") for gate in ("june-check", "failcheck")]
    check_gates(read_runs(root / "runs" / "JUNE_RUNS.md"), read_gates(_gates(root, good)), pin)
    for bad in (("2026-11-05 09:00", "failcheck", pin, A, "other code"),
                ("2026-11-05 09:00", "failcheck", A, entry.code_hash, "another pin"),
                ("2026-11-07 09:00", "failcheck", pin, entry.code_hash, "after the row")):
        rows = [good[0], bad]
        with pytest.raises(JuneRunsError, match="failcheck"):
            check_gates(read_runs(root / "runs" / "JUNE_RUNS.md"), read_gates(_gates(root, rows)), pin)


def test_J1_a_synthetic_row_needs_no_gate(tmp_path):
    root = _root(tmp_path, ["synthetic"], list_hash=None, gates=())
    from voc.frozen import check_gates, read_gates, read_runs

    check_gates(read_runs(root / "runs" / "JUNE_RUNS.md"), read_gates(root / "runs" / "JUNE_GATES.md"), A)


@pytest.mark.parametrize("line", ["| 2026-11-05 09:00 | other | pass | {p} | {c} | x |",
                                  "| 2026-11-05 | june-check | pass | {p} | {c} | x |",
                                  "| 2026-11-05 09:00 | june-check | pass | {p} | short | x |",
                                  "| 2026-11-05 09:00 | june-check | pass | {p} | {c} |  |"])
def test_J1_a_gate_row_that_breaks_the_format_is_refused(tmp_path, line):
    from voc.frozen import JuneRunsError, read_gates

    path = _gates(tmp_path, [])
    path.write_text(path.read_text(encoding="utf-8") + line.format(p=A, c=B) + "\n", encoding="utf-8")
    with pytest.raises(JuneRunsError):
        read_gates(path)


def test_J1_the_committed_logs_keep_the_rule():
    """CI runs this on the committed files: every real row of runs/JUNE_RUNS.md has both gates' passes."""
    from voc.frozen import GATES, RUNS, check_gates, read_gates, read_runs

    check_gates(read_runs(REPO / RUNS), read_gates(REPO / GATES), _real_pin_sha())
    assert (REPO / GATES).is_file()


def test_J1_the_hash_script_refuses_without_both_gates(tmp_path, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("june_hash", REPO / "scripts" / "june_hash.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = _root(tmp_path, ["synthetic"], gates=())
    assert module.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("refused:") and "gate" in out and "june list sha256" not in out
    # Changed in the third fix round: the synthetic flag is gone until pull request 9.


def test_J1_ci_checks_that_the_gates_log_only_grows():
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    runs = [step.get("run", "") for job in workflow["jobs"].values() for step in job["steps"]]
    assert any("scripts/check_test_runs.py" in run and "runs/JUNE_GATES.md" in run
               and "origin/main:runs/JUNE_GATES.md" in run for run in runs)


def test_J5_job_a_s_spark_reads_are_refused_with_fixed_text_only():
    """Review of the fix round, serious 3: Spark's error on the June file could quote a row."""
    def failing(sql):
        raise RuntimeError(f"Malformed CSV record: {MARKER}")

    for call in (lambda: _job_a().spark_counts(failing, "/Volumes/x/june/june.csv"),
                 lambda: _job_a().spark_rows(failing, ["1", "2"])):
        with pytest.raises(_job_a().JobAError) as refused:
            call()
        assert "SYNMARKER" not in str(refused.value) and refused.value.__cause__ is None
        assert refused.value.__context__ is None  # changed in the third fix round: no earlier exception at all


def test_J8_job_a_s_spark_reads_return_counts_and_rows():
    class Row(dict):
        def __getitem__(self, key):
            return dict.__getitem__(self, key)

    seen = []

    def run(sql):
        seen.append(sql)
        return [Row(rows=3, narratives=2)] if "count(*)" in sql else [("1", "Mortgage", "x"), ("2", "Credit card", "y")]

    assert _job_a().spark_counts(run, "/Volumes/x/june/june.csv") == (3, 2)
    assert _job_a().spark_rows(run, ["1", "2"]) == [("1", "Mortgage", "x"), ("2", "Credit card", "y")]
    assert "complaint_id in ('1','2')" in seen[1] and "workspace.voc_june.stg_complaints" in seen[1]
    for bad in (["1; drop"], ["SYN-1'"], [""]):
        with pytest.raises(_job_a().JobAError):
            _job_a().spark_rows(run, bad)


def test_J5_the_job_a_notebook_reads_spark_only_through_the_fixed_text_wrappers():
    text = (REPO / "cloud" / "job_a" / "job_a.py").read_text(encoding="utf-8")
    assert "spark.sql(" not in text
    assert "spark_counts(" in text and "spark_rows(" in text
    assert text.index("spark_counts(") < text.index("checked_counts(") < text.index("spark_rows(")


def test_J5_the_failcheck_marker_starts_each_text_field_of_the_short_row():
    """Review of the fix round, minor 4: if Databricks shortens an error, the marker is what is left."""
    from voc import failcheck

    records = list(csv.reader(io.StringIO(failcheck.rows_text())))
    short = records[-1]
    for n in (2, 3, 4, 5, 6, 7):
        assert short[n].startswith(failcheck.MARKER), n


def test_J5_the_failcheck_control_differs_from_the_quiet_run_by_the_flags_only():
    tasks = _tasks(_failcheck())
    quiet, control = tasks["dbt"], tasks["dbt_control"]
    assert {k: v for k, v in control.items() if k not in ("task_key", "depends_on", "run_if", "dbt_task")} == \
        {k: v for k, v in quiet.items() if k not in ("task_key", "depends_on", "dbt_task")}
    assert {**control["dbt_task"], "commands": quiet["dbt_task"]["commands"]} == quiet["dbt_task"]


def test_J5_the_failcheck_s_first_task_returns_its_code_hash_only():
    """The robot's check prints it, so the gate's pass is recorded for the code that ran."""
    text = (REPO / "cloud" / "failcheck" / "make_rows.py").read_text(encoding="utf-8")
    assert "dbutils.notebook.exit(json.dumps({\"code_sha256\": code_hash(root)}))" in text


def _archive(kind, files):
    import tarfile
    import zipfile as zf

    buffer = io.BytesIO()
    if kind == "tar.gz":
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, payload in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
    else:
        with zf.ZipFile(buffer, "w", zf.ZIP_DEFLATED) as archive:
            for name, payload in files.items():
                archive.writestr(name, payload)
    return buffer.getvalue()


def test_J13_the_robot_check_reads_tar_and_zip_and_says_when_it_cannot_read():
    """Review of the fix round, serious 1: a download that is not a readable archive is never "nowhere"."""
    check = _robot_check()
    marker = check.MARKER.encode()
    for kind in ("tar.gz", "zip"):
        assert check.archive_places(_archive(kind, {"a.sql": b"select 1", "logs/dbt.log": marker})) == \
            (2, ["logs/dbt.log"])
        assert check.archive_places(_archive(kind, {"a.sql": b"select 1"})) == (1, [])
    for unreadable in (b"\x1f\x8b not really", b"<html>sign in</html>", b"", b"PK\x03\x04 cut off"):
        assert check.archive_places(unreadable) is None


def _replies(check, quiet_error="dbt failed", quiet_state="", control_error=None, control_artifacts=None,
             quiet_artifacts=None, history=403, wide=400, quiet_link=True, quiet_output_raw=None, control_state="",
             history_message="", extra_tasks=()):
    host = "https://synthetic.example.invalid"
    marker = check.MARKER
    control_artifacts = _archive("zip", {"logs/dbt.log": marker.encode()}) if control_artifacts is None \
        else control_artifacts
    quiet_artifacts = _archive("tar.gz", {"target/run.sql": b"select 1"}) if quiet_artifacts is None else quiet_artifacts
    tasks = [{"task_key": "make_rows", "run_id": 11, "state": {"result_state": "SUCCESS"}},
             {"task_key": "dbt", "run_id": 12, "state": {"result_state": "FAILED", "state_message": quiet_state}},
             {"task_key": "dbt_control", "run_id": 13, "state": {"result_state": "FAILED",
                                                                  "state_message": control_state}},
             *extra_tasks]
    return {
        ("jobs", f"{host}/oidc/v1/token"): (200, json.dumps({"access_token": "synthetic-token"}).encode()),
        ("all-apis", f"{host}/oidc/v1/token"): (wide, json.dumps({"error": "invalid_scope"}).encode()),
        f"{host}/api/2.2/jobs/runs/get?run_id=99": (200, json.dumps({"tasks": tasks}).encode()),
        f"{host}/api/2.2/jobs/runs/get-output?run_id=11": (200, json.dumps({"notebook_output": {
            "result": json.dumps({"code_sha256": B}), "truncated": False}}).encode()),
        f"{host}/api/2.2/jobs/runs/get-output?run_id=12": (200, quiet_output_raw if quiet_output_raw is not None
                                                          else json.dumps({"error": quiet_error, **({"dbt_output": {
            "artifacts_link": f"{host}/a12", "artifacts_headers": {}}} if quiet_link else {})}).encode()),
        f"{host}/api/2.2/jobs/runs/get-output?run_id=13": (200, json.dumps({
            "error": control_error if control_error is not None else f"dbt failed {marker}",
            "dbt_output": {"artifacts_link": f"{host}/a13", "artifacts_headers": {}}}).encode()),
        f"{host}/a12": (200, quiet_artifacts),
        f"{host}/a13": (200, control_artifacts),
        f"{host}/api/2.0/sql/history/queries": (history, json.dumps({"error_code": "PERMISSION_DENIED",
                                                                     "message": history_message}).encode()),
    }


def _report(check, monkeypatch, replies):
    import urllib.parse

    def fake(url, token=None, data=None, headers=None):
        if url.endswith("/oidc/v1/token"):
            scope = urllib.parse.parse_qs(data.decode("ascii"))["scope"][0]
            return replies[(scope, url)]
        return replies[url]

    monkeypatch.setattr(check, "_call", fake)
    return check.report("synthetic.example.invalid", "synthetic-id", "syn-" + "secret", 99)


def test_J13_the_robot_check_passes_only_when_every_rule_holds(monkeypatch):
    check = _robot_check()
    lines = _report(check, monkeypatch, _reached(check))  # changed in the third fix round: both reached the model
    assert lines[-1] == "verdict: PASS"
    assert f"code sha256: {B}" in lines
    assert "all-apis token: refused, HTTP 400" in lines
    assert "dbt: runs/get: marker nowhere" in lines
    assert "dbt_control: artifacts: files: 2, marker in: logs/dbt.log" in lines
    text = "\n".join(lines)
    assert check.MARKER not in text and "synthetic-token" not in text and "syn-secret" not in text


@pytest.mark.parametrize("change, reason", [
    ({"quiet_error": "dbt failed SYNFAILCHECKMARKER"}, "dbt's output"),
    ({"quiet_state": "SYNFAILCHECKMARKER"}, "dbt's runs/get"),
    ({"quiet_artifacts": b"PK\x03\x04 cut off"}, "could not read"),
    ({"quiet_artifacts": b"<html>sign in</html>"}, "could not read"),
    ({"control_error": "dbt failed"}, "control"),
    ({"control_artifacts": b"x"}, "could not read"),
    ({"history": 200}, "query history"),
    ({"wide": 200}, "all-apis"),
])
def test_J13_the_robot_check_fails_on_any_leak_unread_place_or_blind_control(monkeypatch, change, reason):
    check = _robot_check()
    replies = _replies(check, **change)
    if change.get("wide") == 200:
        replies[("all-apis", "https://synthetic.example.invalid/oidc/v1/token")] = (
            200, json.dumps({"access_token": "wide-token"}).encode())
    lines = _report(check, monkeypatch, replies)
    assert lines[-1].startswith("verdict: FAIL") and reason in lines[-1]
    assert check.MARKER not in "\n".join(lines) and "wide-token" not in "\n".join(lines)


def test_J13_the_control_s_artifacts_must_show_the_marker_when_the_quiet_run_s_are_judged(monkeypatch):
    """Review of the fix round, serious 1: the control must show the check can see a leak in each kind of place."""
    check = _robot_check()
    replies = _replies(check, control_artifacts=_archive("zip", {"target/run.sql": b"select 1"}))
    lines = _report(check, monkeypatch, replies)
    assert lines[-1].startswith("verdict: FAIL") and "control" in lines[-1]


def test_J13_the_robot_check_says_how_to_set_the_host_when_it_cannot_find_it():
    text = (REPO / "cloud" / "failcheck" / "robot_check.py").read_text(encoding="utf-8")
    assert "Fill in HOST" in text


def _june_root(tmp_path, rows):
    """A checkout copy with a June list made of these (complaint_id, product, narrative) rows."""
    root = _sample(tmp_path / "root", rows)
    return root


def test_J8_the_laptop_check_checks_the_sample_s_hashes_and_its_line_breaks(tmp_path):
    """Owner decision on minor 6 of the fix round's review: the sampled rows, as Python reads them, must match the
    frozen hashes, and a sampled narrative holding a carriage return is counted, since Spark may read it otherwise."""
    narratives = ["one line", "a\r\nWindows break", "two\nlines"]
    text = _june_csv(narratives)
    folder, pin = _zip_and_pin(tmp_path, text=text)
    sampled = [("SYN-1", "Mortgage", "one line"), ("SYN-2", "Mortgage", "a\r\nWindows break")]
    root = _june_root(tmp_path, sampled)
    counts = _job_a().june_check(next(folder.iterdir()), pin, REPO / "config" / "labels.toml", root=root,
                                 scratch=tmp_path)
    assert counts["sampled_rows"] == 2 and counts["sampled_matching"] == 2
    assert counts["sampled_with_returns"] == 1
    changed = _june_root(tmp_path / "c", [("SYN-1", "Mortgage", "one line, changed"), sampled[1]])
    counts = _job_a().june_check(next(folder.iterdir()), pin, REPO / "config" / "labels.toml", root=changed,
                                 scratch=tmp_path)
    assert counts["sampled_matching"] == 1


def test_J8_the_laptop_check_unpacks_inside_the_folder_it_is_given_and_leaves_nothing(tmp_path):
    """Review of the fix round, nit 1: the copy stays inside the June data folder, which the read guard covers."""
    scratch = tmp_path / "june_folder"
    scratch.mkdir()
    folder, pin = _zip_and_pin(tmp_path, text=_june_csv(["one"]))
    root = _june_root(tmp_path, [("SYN-1", "Mortgage", "one")])
    seen = []
    real = _job_a().file_counts

    def spy(path, *args, **kwargs):
        seen.append(Path(path))
        return real(path, *args, **kwargs)

    import voc.job_a

    original, voc.job_a.file_counts = voc.job_a.file_counts, spy
    try:
        _job_a().june_check(next(folder.iterdir()), pin, REPO / "config" / "labels.toml", root=root, scratch=scratch)
    finally:
        voc.job_a.file_counts = original
    assert seen and scratch in seen[0].parents
    assert list(scratch.iterdir()) == []


def test_J8_the_laptop_check_s_lines_say_what_must_hold_and_fail_on_any_mismatch():
    """Owner decision on minor 3: a mismatch exits non-zero, and the step can be met as written."""
    counts = {"rows": 10, "narratives": 4, "fields_with_line_breaks": 2, "fields_with_lone_returns": 0,
              "sampled_rows": 3, "sampled_matching": 3, "sampled_with_returns": 0}
    pin = {"rows": 10, "narratives": 4}
    lines, ok = _job_a().june_check_verdict(counts, pin)
    assert ok and lines[-1] == "verdict: PASS"
    for change in ({"rows": 11}, {"narratives": 5}, {"sampled_matching": 2}, {"sampled_with_returns": 1}):
        lines, ok = _job_a().june_check_verdict({**counts, **change}, pin)
        assert not ok and lines[-1].startswith("verdict: FAIL")


def test_J8_the_cli_exits_non_zero_when_the_laptop_check_fails(tmp_path, capsys, monkeypatch):
    import voc.job_a
    from voc.cli import main

    folder, _ = _zip_and_pin(tmp_path, text=_june_csv(["one"]))
    monkeypatch.setattr(voc.job_a, "june_check", lambda *a, **k: {
        "rows": 1, "narratives": 1, "fields_with_line_breaks": 0, "fields_with_lone_returns": 0,
        "sampled_rows": 1, "sampled_matching": 0, "sampled_with_returns": 0})
    env = {"VOC_JUNE_DATA_DIR": str(tmp_path)}
    assert main(["june-check", "--zip", str(next(folder.iterdir()))], env=env, root=REPO) == 1
    assert "verdict: FAIL" in capsys.readouterr().out


def test_J8_the_cli_s_laptop_check_needs_the_june_data_folder(tmp_path, capsys):
    from voc.cli import main

    folder, _ = _zip_and_pin(tmp_path, text=_june_csv(["one"]))
    assert main(["june-check", "--zip", str(next(folder.iterdir()))], env={}, root=REPO) == 1
    assert "VOC_JUNE_DATA_DIR" in capsys.readouterr().out



def test_J1_the_cli_prints_the_gate_record_only_on_a_pass_from_unchanged_code(tmp_path, capsys, monkeypatch):
    import voc.frozen
    import voc.job_a
    from voc.cli import main
    from voc.frozen import code_hash

    good = {"rows": 620794, "narratives": 16820, "fields_with_line_breaks": 0, "fields_with_lone_returns": 0,
            "sampled_rows": 3, "sampled_matching": 3, "sampled_with_returns": 0}
    folder, _ = _zip_and_pin(tmp_path, text=_june_csv(["one"]))
    monkeypatch.setattr(voc.job_a, "june_check", lambda *a, **k: good)
    # Changed in the third fix round: the check is by content, in changed_frozen.
    monkeypatch.setattr(voc.frozen, "changed_frozen", lambda root: [])
    env = {"VOC_JUNE_DATA_DIR": str(tmp_path)}
    assert main(["june-check", "--zip", str(next(folder.iterdir()))], env=env, root=REPO) == 0
    out = capsys.readouterr().out
    assert "verdict: PASS" in out
    assert f"gate record: june-check passed for pin {_real_pin_sha()} and code {code_hash(REPO)}" in out
    monkeypatch.setattr(voc.frozen, "changed_frozen", lambda root: ["src/voc/x.py"])
    assert main(["june-check", "--zip", str(next(folder.iterdir()))], env=env, root=REPO) == 1
    out = capsys.readouterr().out
    assert "gate record" not in out and "1 frozen files differ" in out
    assert "ran at: " not in out



# The third review of #94, on its second fix round, and the owner's decisions on it (6 November)

RUN_FILE = "target/run/voc/models/landed_complaints.sql"


def _reached(check, **change):
    """Replies in which both dbt runs reached the failing model: their dbt files hold its run file."""
    marker = check.MARKER.encode()
    return _replies(check, **{"quiet_artifacts": _archive("tar.gz", {RUN_FILE: b"create table x as select 1"}),
                              "control_artifacts": _archive("zip", {RUN_FILE: b"create table x as select 1",
                                                                    "logs/dbt.log": marker}), **change})


def test_J13_the_robot_check_passes_when_both_runs_reached_the_failing_model(monkeypatch):
    check = _robot_check()
    lines = _report(check, monkeypatch, _reached(check))
    assert lines[-1] == "verdict: PASS"


@pytest.mark.parametrize("change", [
    {"quiet_artifacts": _archive("tar.gz", {"target/run.sql": b"select 1"})},
    {"quiet_link": False},
])
def test_J13_the_quiet_run_must_show_it_reached_the_failing_model(monkeypatch, change):
    """Serious 1 of the third review: a quiet run that failed early proves nothing about the flags."""
    check = _robot_check()
    lines = _report(check, monkeypatch, _reached(check, **change))
    assert lines[-1].startswith("verdict: FAIL") and "reached the failing model" in lines[-1]


def test_J13_the_control_must_show_it_reached_the_failing_model(monkeypatch):
    check = _robot_check()
    control = _archive("zip", {"logs/dbt.log": check.MARKER.encode()})
    lines = _report(check, monkeypatch, _reached(check, control_artifacts=control))
    assert lines[-1].startswith("verdict: FAIL") and "control" in lines[-1]


def test_J13_an_output_that_is_not_json_is_unread(monkeypatch):
    check = _robot_check()
    lines = _report(check, monkeypatch, _reached(check, quiet_output_raw=b"<html>a proxy page</html>"))
    assert "dbt: output: could not read, HTTP 200" in lines
    assert lines[-1].startswith("verdict: FAIL") and "could not read" in lines[-1]


@pytest.mark.parametrize("status", [500, 429, 200])
def test_J13_an_all_apis_request_must_be_refused_or_narrowed(monkeypatch, status):
    """Minor 2 of the third review: only 400, 401 or 403 is a refusal, and a token given must be narrowed to jobs."""
    check = _robot_check()
    replies = _reached(check, wide=status)
    if status == 200:
        replies[("all-apis", "https://synthetic.example.invalid/oidc/v1/token")] = (
            200, json.dumps({"access_token": "wide-token", "scope": "all-apis"}).encode())
    lines = _report(check, monkeypatch, replies)
    assert lines[-1].startswith("verdict: FAIL") and "all-apis" in lines[-1]
    assert "wide-token" not in "\n".join(lines)


def test_J13_an_all_apis_token_narrowed_to_jobs_is_not_a_failure(monkeypatch):
    check = _robot_check()
    replies = _reached(check)
    replies[("all-apis", "https://synthetic.example.invalid/oidc/v1/token")] = (
        200, json.dumps({"access_token": "narrow-token", "scope": "jobs"}).encode())
    lines = _report(check, monkeypatch, replies)
    assert "all-apis token: narrowed to jobs" in lines and lines[-1] == "verdict: PASS"
    assert "narrow-token" not in "\n".join(lines)


def test_J13_the_marker_in_any_other_task_fails_and_a_repeated_task_is_refused(monkeypatch):
    check = _robot_check()
    other = {"task_key": "other", "run_id": 14, "state": {"result_state": "SUCCESS", "state_message": check.MARKER}}
    replies = _reached(check, extra_tasks=(other,))
    replies["https://synthetic.example.invalid/api/2.2/jobs/runs/get-output?run_id=14"] = (200, b"{}")
    lines = _report(check, monkeypatch, replies)
    assert lines[-1].startswith("verdict: FAIL") and "other" in lines[-1]
    again = {"task_key": "dbt", "run_id": 15, "state": {"result_state": "FAILED"}}
    lines = _report(check, monkeypatch, _reached(check, extra_tasks=(again,)))
    assert lines[-1].startswith("verdict: FAIL") and "twice" in lines[-1]


def test_J13_the_control_must_show_the_marker_in_its_output_not_only_its_run_details(monkeypatch):
    """Nit 5 of the third review: the spec says the control shows the marker in its output."""
    check = _robot_check()
    lines = _report(check, monkeypatch, _reached(check, control_error="dbt failed", control_state=check.MARKER))
    assert lines[-1].startswith("verdict: FAIL") and "control" in lines[-1]


def test_J13_an_encrypted_zip_is_unread_not_a_crash(monkeypatch):
    import zipfile as zf

    check = _robot_check()
    data = _archive("zip", {"logs/dbt.log": b"x"})

    def encrypted(self, name, pwd=None):
        raise RuntimeError("File is encrypted, password required for extraction")

    monkeypatch.setattr(zf.ZipFile, "read", encrypted)
    assert check.archive_places(data) is None


def test_J13_the_robot_check_calls_every_place_and_never_prints_the_history_message(monkeypatch):
    """Minor 7 of the third review: the assertions the second round's green commit dropped."""
    import urllib.parse

    check = _robot_check()
    replies = _reached(check, history_message=f"denied for {check.MARKER}")
    called = []

    def fake(url, token=None, data=None, headers=None):
        if url.endswith("/oidc/v1/token"):
            key = (urllib.parse.parse_qs(data.decode("ascii"))["scope"][0], url)
        else:
            key = url
        called.append(key)
        return replies[key]

    monkeypatch.setattr(check, "_call", fake)
    lines = check.report("synthetic.example.invalid", "synthetic-id", "syn-" + "secret", 99)
    assert set(called) == set(replies)
    assert check.MARKER not in "\n".join(lines)


def _gate_rows(root, rows):
    """The gates log in its form with a Result column (minor 8 of the third review)."""
    path = Path(root) / "runs" / "JUNE_GATES.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# June gates\n\n| Date | Gate | Result | Pin SHA-256 | Code hash | Evidence |\n"
                    "|---|---|---|---|---|---|\n" + "".join(f"| {' | '.join(row)} |\n" for row in rows),
                    encoding="utf-8")
    return path


def _real_entries(tmp_path):
    from voc.frozen import read_runs

    root = _root(tmp_path, ["real"], gates=())
    return root, read_runs(root / "runs" / "JUNE_RUNS.md")


def test_J1_a_gate_pass_in_the_same_minute_as_the_row_does_not_count(tmp_path):
    """Minor 3 of the third review: "dated before" means strictly before."""
    from voc.frozen import JuneRunsError, check_gates, read_gates

    root, entries = _real_entries(tmp_path)
    pin, code, row_date = _real_pin_sha(), entries[0].code_hash, entries[0].date
    rows = [(row_date, gate, "pass", pin, code, "a pass") for gate in ("june-check", "failcheck")]
    with pytest.raises(JuneRunsError):
        check_gates(entries, read_gates(_gate_rows(root, rows)), pin)
    rows = [("2026-11-05 09:00", gate, "pass", pin, code, "a pass") for gate in ("june-check", "failcheck")]
    check_gates(entries, read_gates(_gate_rows(root, rows)), pin)


def test_J1_a_later_fail_of_a_gate_closes_it_and_a_later_pass_opens_it_again(tmp_path):
    """Minor 8 of the third review: a recorded FAIL after a PASS blocks the row."""
    from voc.frozen import JuneRunsError, check_gates, read_gates

    root, entries = _real_entries(tmp_path)
    pin, code = _real_pin_sha(), entries[0].code_hash
    june = ("2026-11-05 08:00", "june-check", "pass", pin, code, "a pass")
    rows = [june, ("2026-11-05 09:00", "failcheck", "pass", pin, code, "a pass"),
            ("2026-11-05 10:00", "failcheck", "fail", pin, code, "verdict: FAIL")]
    with pytest.raises(JuneRunsError, match="failcheck"):
        check_gates(entries, read_gates(_gate_rows(root, rows)), pin)
    rows.append(("2026-11-05 11:00", "failcheck", "pass", pin, code, "a pass after a fix"))
    check_gates(entries, read_gates(_gate_rows(root, rows)), pin)


@pytest.mark.parametrize("row", [("2026-11-05 09:00", "failcheck", "maybe", A, B, "x"),
                                 ("2026-13-45 99:99", "failcheck", "pass", A, B, "x"),
                                 ("2026-11-05 09:00", "failcheck", "pass", A, B, "")])
def test_J1_a_gate_row_with_a_bad_result_or_date_is_refused(tmp_path, row):
    from voc.frozen import JuneRunsError, read_gates

    with pytest.raises(JuneRunsError):
        read_gates(_gate_rows(tmp_path, [row]))


def test_J1_the_committed_gates_log_has_the_result_column():
    from voc.frozen import GATES

    assert "| Date | Gate | Result | Pin SHA-256 | Code hash | Evidence |" in (REPO / GATES).read_text(encoding="utf-8")


def _gates_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_june_gates", REPO / "scripts" / "check_june_gates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_J1_ci_refuses_a_new_real_row_whose_gate_passes_are_not_on_main_already(tmp_path, capsys):
    """Minor 3 of the third review: gate rows cannot be added with the real row and an earlier date."""
    root, entries = _real_entries(tmp_path)
    pin, code = _real_pin_sha(), entries[0].code_hash
    passes = [("2026-11-05 09:00", gate, "pass", pin, code, "a pass") for gate in ("june-check", "failcheck")]
    main = tmp_path / "main"
    main.mkdir()
    main_runs = main / "JUNE_RUNS.md"
    main_runs.write_text("# June runs\n", encoding="utf-8")
    main_gates = _gate_rows(main / "g", passes)
    data_files = REPO / "config" / "data_files.toml"
    script = _gates_script()
    head_runs = root / "runs" / "JUNE_RUNS.md"
    assert script.main([str(main_gates), str(main_runs), str(head_runs), str(data_files)]) == 0
    empty = _gate_rows(main / "e", [])
    assert script.main([str(empty), str(main_runs), str(head_runs), str(data_files)]) == 1
    assert "on main" in capsys.readouterr().out
    assert script.main([str(main / "missing.md"), str(main / "missing_runs.md"), str(head_runs), str(data_files)]) == 1


def test_J1_ci_runs_the_gates_check_against_main():
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    runs = [step.get("run", "") for job in workflow["jobs"].values() for step in job["steps"]]
    assert any("scripts/check_june_gates.py" in run and "origin/main:runs/JUNE_GATES.md" in run
               and "origin/main:runs/JUNE_RUNS.md" in run for run in runs)


def _hash_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("june_hash", REPO / "scripts" / "june_hash.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_J1_the_hash_script_has_no_synthetic_way_round_the_gates(tmp_path, capsys):
    """Minor 4 of the third review: the flag is removed until pull request 9 names the dry run's own list."""
    root = _root(tmp_path, ["synthetic"], gates=())
    assert _hash_script().main([str(root), "--synthetic"]) == 1
    assert "june list sha256" not in capsys.readouterr().out


def test_J1_the_hash_script_prints_the_hashes_when_both_gates_passed(tmp_path, capsys):
    from voc.frozen import code_hash, frozen_files, list_hash

    root = _root(tmp_path, ["synthetic"], gates=())
    pin, code = _real_pin_sha(), code_hash(root)
    _gate_rows(root, [("2026-11-05 09:00", gate, "pass", pin, code, "a pass") for gate in ("june-check", "failcheck")])
    assert _hash_script().main([str(root)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"june list sha256 {list_hash(root)}", f"frozen code sha256 {code} over {len(frozen_files(root))} files"]


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True)


def test_J1_a_frozen_file_changed_in_content_counts_as_changed(tmp_path):
    """Minor 5 of the third review: a tracked file edited in place, such as uv.lock, is not unchanged."""
    from voc.frozen import changed_frozen

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    # LF bytes, as this repo's checkout has them (`.gitattributes`). Python's write_text writes CRLF on Windows,
    # which the content check counts as a change (changed in the last fix round).
    (root / "src" / "a.py").write_bytes(b"x = 1\n")
    (root / "uv.lock").write_bytes(b"lock\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    assert changed_frozen(root) == []
    (root / "uv.lock").write_bytes(b"rewritten\n")
    (root / "src" / "b.py").write_bytes(b"y = 2\n")
    assert sorted(changed_frozen(root)) == ["src/b.py", "uv.lock"]
    assert changed_frozen(tmp_path / "not_a_repo") is None


def test_J1_the_cli_s_gate_record_needs_content_unchanged_and_the_top_of_a_checkout(tmp_path, capsys, monkeypatch):
    import voc.frozen
    import voc.job_a
    from voc.cli import main

    good = {"rows": 620794, "narratives": 16820, "fields_with_line_breaks": 0, "fields_with_lone_returns": 0,
            "sampled_rows": 3, "sampled_matching": 3, "sampled_with_returns": 0}
    folder, _ = _zip_and_pin(tmp_path, text=_june_csv(["one"]))
    monkeypatch.setattr(voc.job_a, "june_check", lambda *a, **k: good)
    env = {"VOC_JUNE_DATA_DIR": str(tmp_path)}
    zip_arg = ["june-check", "--zip", str(next(folder.iterdir()))]
    monkeypatch.setattr(voc.frozen, "changed_frozen", lambda root: [])
    assert main(zip_arg, env=env, root=REPO) == 0
    assert "gate record: june-check passed" in capsys.readouterr().out
    monkeypatch.setattr(voc.frozen, "changed_frozen", lambda root: ["uv.lock"])
    assert main(zip_arg, env=env, root=REPO) == 1
    assert "gate record" not in capsys.readouterr().out
    monkeypatch.setattr(voc.frozen, "changed_frozen", lambda root: None)
    assert main(zip_arg, env=env, root=REPO) == 1
    assert "top of" in capsys.readouterr().out


def test_J5_job_a_s_refusals_carry_no_exception_at_all():
    """Minor 6 of the third review: `from None` only hides the cause. The refusal must hold no earlier exception."""
    def failing(sql):
        raise RuntimeError(f"Malformed CSV record: {MARKER}")

    for call in (lambda: _job_a().spark_counts(failing, "/Volumes/x/june/june.csv"),
                 lambda: _job_a().spark_rows(failing, ["1", "2"])):
        with pytest.raises(_job_a().JobAError) as refused:
            call()
        assert refused.value.__context__ is None and refused.value.__cause__ is None


@pytest.mark.parametrize("text", [f'2026-06-01,Mortgage,"{MARKER}"', ""])
def test_J5_unpack_s_refusals_carry_no_exception_at_all(tmp_path, monkeypatch, text):
    import zlib

    if text:
        folder, pin = _zip_and_pin(tmp_path, text=_with_row(_rows(), text))
    else:
        def fail(path, pin):
            raise zlib.error(MARKER)

        monkeypatch.setattr(_job_a(), "_check_shape", fail)
        folder, pin = _zip_and_pin(tmp_path)
    with pytest.raises(_job_a().JobAError) as refused:
        _unpack(folder, tmp_path / "june", pin)
    assert refused.value.__context__ is None


def test_J8_no_text_still_says_the_gates_come_before_the_upload():
    """Nit 1 of the third review: the gates come before the run log's real row."""
    for name in ("cloud/failcheck.yml", "src/voc/failcheck.py", "src/voc/job_a.py", "config/data_files.toml",
                 "cloud/failcheck/STEPS.md", "src/voc/cli.py"):
        assert "before the June upload" not in (REPO / name).read_text(encoding="utf-8"), name
    assert "counts and hashes only" in (REPO / "src" / "voc" / "cli.py").read_text(encoding="utf-8")


def test_J8_the_steps_run_june_check_with_the_lock_file_kept():
    steps = (REPO / "cloud" / "failcheck" / "STEPS.md").read_text(encoding="utf-8")
    assert "uv run --locked --native-tls voc june-check" in steps
    assert "frozen" in steps.split("## Gate 1")[0]


def test_J8_the_owner_s_steps_make_the_sample_before_june_check():
    """Minor 10 of the third review: june-check needs the pin and the sample."""
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    steps = spec.split("## Owner's setup steps")[1]
    assert steps.index("`voc sample june`") < steps.index("run `voc june-check`")



# The minors of the last review of #94 (owner decision: fixed with no further review round)


def test_J1_the_cli_records_a_fail_too_with_its_time_in_utc(tmp_path, capsys, monkeypatch):
    """Minors 2 and 3 of the last review: a fail can be recorded, and both gates print their time in UTC."""
    import voc.frozen
    import voc.job_a
    from voc.cli import main
    from voc.frozen import code_hash

    bad = {"rows": 620794, "narratives": 16821, "fields_with_line_breaks": 0, "fields_with_lone_returns": 0,
           "sampled_rows": 3, "sampled_matching": 3, "sampled_with_returns": 0}
    folder, _ = _zip_and_pin(tmp_path, text=_june_csv(["one"]))
    monkeypatch.setattr(voc.job_a, "june_check", lambda *a, **k: bad)
    monkeypatch.setattr(voc.frozen, "changed_frozen", lambda root: [])
    env = {"VOC_JUNE_DATA_DIR": str(tmp_path)}
    assert main(["june-check", "--zip", str(next(folder.iterdir()))], env=env, root=REPO) == 1
    out = capsys.readouterr().out
    assert "verdict: FAIL" in out and re.search(r"ran at: \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", out)
    assert f"gate record: june-check failed for pin {_real_pin_sha()} and code {code_hash(REPO)}" in out


def test_J13_the_robot_check_prints_its_time_and_code_hash_even_when_it_stops_early(monkeypatch):
    """Minor 3 of the last review: a task listed twice still gives what a fail's row needs."""
    check = _robot_check()
    again = {"task_key": "dbt", "run_id": 15, "state": {"result_state": "FAILED"}}
    lines = _report(check, monkeypatch, _reached(check, extra_tasks=(again,)))
    assert f"code sha256: {B}" in lines
    assert re.fullmatch(r"checked at: \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", lines[-2])
    assert lines[-1].startswith("verdict: FAIL")


def test_J13_the_run_file_rule_needs_a_folder_boundary(monkeypatch):
    """Nit 1 of the last review."""
    check = _robot_check()
    lines = _report(check, monkeypatch, _reached(check, quiet_artifacts=_archive(
        "tar.gz", {"x" + RUN_FILE.split("/", 1)[1]: b"create table x as select 1"})))
    assert lines[-1].startswith("verdict: FAIL") and "reached the failing model" in lines[-1]


def _repo(tmp_path, files, attributes="* text=auto eol=lf\n"):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitattributes").write_bytes(attributes.encode())
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    _git(root, "init", "-q")
    _git(root, "config", "core.autocrlf", "true")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    return root


def test_J1_a_frozen_file_rewritten_with_other_line_endings_counts_as_changed(tmp_path):
    """Minor 4 of the last review: git may hide a change that the code hash sees."""
    from voc.frozen import changed_frozen

    root = _repo(tmp_path, {"src/a.py": b"x = 1\n", "src/b.py": b"y = 1\n"})
    assert changed_frozen(root) == []
    (root / "src" / "a.py").write_bytes(b"x = 1\r\n")
    assert changed_frozen(root) == ["src/a.py"]


def test_J1_a_frozen_file_hidden_from_git_s_status_still_counts(tmp_path):
    from voc.frozen import changed_frozen

    root = _repo(tmp_path, {"src/a.py": b"x = 1\n"})
    _git(root, "update-index", "--skip-worktree", "src/a.py")
    (root / "src" / "a.py").write_bytes(b"x = 2\n")
    assert changed_frozen(root) == ["src/a.py"]


def test_J1_a_frozen_file_with_a_space_in_its_name_is_not_a_change(tmp_path):
    """Minor 5 of the last review."""
    from voc.frozen import changed_frozen, differs_from_git

    root = _repo(tmp_path, {"src/a b.py": b"x = 1\n"})
    assert differs_from_git(root) == [] and changed_frozen(root) == []


def test_J1_a_run_log_row_with_an_impossible_date_is_refused(tmp_path):
    """Minor 6 of the last review."""
    from voc.frozen import JuneRunsError, read_runs

    with pytest.raises(JuneRunsError):
        read_runs(_log(tmp_path, [("2026-11-07 99:99", "real", A, B, "the June run")]))


def test_J1_the_hash_script_prints_the_hashes_on_a_git_checkout_with_both_gates_open(tmp_path, capsys):
    """Minor 7 of the last review: the path the owner uses, on a real checkout."""
    from voc.frozen import code_hash, frozen_files, list_hash

    root = _root(tmp_path, ["synthetic"], gates=())
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    code = code_hash(root)
    _gate_rows(root, [("2026-11-05 09:00", gate, "pass", _real_pin_sha(), code, "a pass")
                      for gate in ("june-check", "failcheck")])
    assert _hash_script().main([str(root)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"june list sha256 {list_hash(root)}", f"frozen code sha256 {code} over {len(frozen_files(root))} files"]
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "new.py").write_text("x = 1\n", encoding="utf-8")
    assert _hash_script().main([str(root)]) == 1


def test_J5_unpack_s_refusal_carries_no_exception_even_when_the_removal_fails(tmp_path, monkeypatch):
    """Nit 6 of the last review."""
    import zlib

    def fail(path, pin):
        raise zlib.error(MARKER)

    def cannot_remove(self, missing_ok=False):
        raise OSError("cannot remove")

    monkeypatch.setattr(_job_a(), "_check_shape", fail)
    folder, pin = _zip_and_pin(tmp_path)
    monkeypatch.setattr(Path, "unlink", cannot_remove)
    with pytest.raises(_job_a().JobAError) as refused:
        _unpack(folder, tmp_path / "june", pin)
    assert refused.value.__context__ is None and "SYNMARKER" not in str(refused.value)


def test_J8_the_steps_give_the_verdict_s_rules_and_the_dates_in_utc():
    """Minors 1 and 2 of the last review, and nit 3."""
    steps = (REPO / "cloud" / "failcheck" / "STEPS.md").read_text(encoding="utf-8")
    for words in ("reached the failing model", "narrowed to `jobs`", "no other task", "UTC",
                  "config/data_files.toml"):
        assert words in steps, words
    gates = (REPO / "runs" / "JUNE_GATES.md").read_text(encoding="utf-8")
    assert "UTC" in gates


def test_J1_the_spec_says_how_the_dry_run_gets_its_hashes():
    """Minor 8 of the last review: pull request 9 must give the dry run's entry its own way to its hashes."""
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    assert "the dry run's own way to its entry's hashes" in spec
