"""T015c: the scheduled pipeline run on the committed synthetic fixture (B7, B12, B14, B16, B17, B21).

The run uses the real `voc` commands on a synthetic project folder: load (with its pin check), dbt build
(with its data tests), label on the mock backend, and evaluate. The fixture in `tests/fixtures/pipeline`
has its own export, pin, split lists, pool counts and mock answers, with `SYN-` IDs only. Nothing here
opens the network or calls a model.
"""
import contextlib
import csv
import importlib.util
import io
import json
import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "pipeline"
EXPORT = "synthetic_complaints.csv"
WORKFLOW = REPO / ".github" / "workflows" / "scheduled.yml"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """A fake home folder, so the real ledger and recordings are never used."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home


def _script(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _column(path, name):
    with open(path, encoding="utf-8", newline="") as f:
        return [row[name] for row in csv.DictReader(f)]


def _rewrite_first_id(path, new_id):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    rows[1][rows[0].index("Complaint ID")] = new_id
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def _split_ids(splits, name):
    return set(_column(splits / f"{name}.csv", "complaint_id"))


def _files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(Path(folder).rglob("*")) if p.is_file()}


# The committed fixture


def test_B16_the_pipeline_fixture_holds_synthetic_ids_only():
    ids = _column(FIXTURE / EXPORT, "Complaint ID")
    assert ids and all(i.startswith("SYN-") for i in ids)
    for name in ("dev", "test", "train"):
        listed = _split_ids(FIXTURE / "splits", name)
        assert listed and all(i.startswith("SYN-") for i in listed)
    answers = _column(FIXTURE / "answers.csv", "complaint_id")
    assert set(answers) == _split_ids(FIXTURE / "splits", "dev")
    manifest = json.loads((FIXTURE / "splits" / "manifest.json").read_text(encoding="utf-8"))
    assert all(i.startswith("SYN-") for i in manifest["quick_check"])


def test_B16_the_pipeline_fixture_export_matches_its_own_committed_pin():
    from voc.datafile import load_pins, verify

    pins = load_pins(FIXTURE / "data_files.toml")
    verify(FIXTURE / EXPORT, pins["july_2026"])
    # The fixture pin never stands in for the real pin: it names another file, and the real config is unchanged.
    real = load_pins(REPO / "config" / "data_files.toml")["july_2026"]
    assert real["file_name"] != pins["july_2026"]["file_name"]
    assert real["sha256"] != pins["july_2026"]["sha256"]


def test_B16_the_fixture_maker_rebuilds_the_committed_fixture_byte_for_byte(tmp_path):
    maker = _script("make_pipeline_fixture")
    assert maker.main([str(tmp_path / "fixture")]) == 0
    assert _files(tmp_path / "fixture") == _files(FIXTURE)


def test_B16_the_fixture_maker_never_overwrites_a_fixture(tmp_path, capsys):
    folder = tmp_path / "fixture"
    folder.mkdir()
    (folder / "SYN.txt").write_text("SYN", encoding="utf-8")
    assert _script("make_pipeline_fixture").main([str(folder)]) == 1
    assert "already exists" in capsys.readouterr().out
    assert _files(folder) == {"SYN.txt": b"SYN"}


# The synthetic project folder


def test_B16_prepare_uses_the_real_config_and_the_fixture_lists(tmp_path):
    work, data = tmp_path / "work", tmp_path / "data"
    _script("pipeline_project").prepare(work, data)
    for name in ("labels.toml", "tfidf.toml", "prompts/v1.toml"):
        assert (work / "config" / name).read_bytes() == (REPO / "config" / name).read_bytes()
    for name in ("data_files.toml", "pool.toml"):
        assert (work / "config" / name).read_bytes() == (FIXTURE / name).read_bytes()
    assert _files(work / "splits") == _files(FIXTURE / "splits")
    assert _files(work / "dbt" / "models") == _files(REPO / "dbt" / "models")
    assert _files(data) == {EXPORT: (FIXTURE / EXPORT).read_bytes()}
    assert not (work / ".env").exists()


def test_B12_prepare_gives_the_mock_backend_and_no_key(tmp_path):
    work, data = tmp_path / "work", tmp_path / "data"
    env = _script("pipeline_project").prepare(work, data)
    assert env == {"LLM_BACKEND": "mock", "VOC_DATA_DIR": str(data),
                   "VOC_MOCK_FIXTURES": str(work / "mock" / "answers.json")}
    answers = json.loads(Path(env["VOC_MOCK_FIXTURES"]).read_text(encoding="utf-8"))
    assert len(answers) == len(_split_ids(FIXTURE / "splits", "dev"))


def test_B16_prepare_refuses_a_fixture_with_an_id_that_is_not_synthetic(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(FIXTURE, fixture)
    _rewrite_first_id(fixture / EXPORT, "".join(["1", "2", "3"]))
    with pytest.raises(ValueError, match="SYN-"):
        _script("pipeline_project").prepare(tmp_path / "work", tmp_path / "data", fixture=fixture)
    assert not (tmp_path / "data").exists()


def test_B16_prepare_refuses_a_folder_that_already_exists(tmp_path):
    (tmp_path / "work").mkdir()
    with pytest.raises(FileExistsError):
        _script("pipeline_project").prepare(tmp_path / "work", tmp_path / "data")


def test_B16_the_load_step_refuses_an_export_that_does_not_match_the_fixture_pin(tmp_path, capsys):
    from voc import cli

    work, data = tmp_path / "work", tmp_path / "data"
    env = _script("pipeline_project").prepare(work, data)
    with open(data / EXPORT, "a", encoding="utf-8", newline="") as f:
        f.write("\n")
    capsys.readouterr()
    assert cli.main(["load", "july_2026"], env=env, root=work) == 1
    assert "does not match the pinned file" in capsys.readouterr().out
    assert not (work / "data" / "voc.duckdb").exists()


def test_B14_a_failing_step_stops_the_run_and_fails_it(tmp_path, capsys):
    fixture = tmp_path / "fixture"
    shutil.copytree(FIXTURE, fixture)
    pin = fixture / "data_files.toml"
    text = pin.read_text(encoding="utf-8")
    pin.write_text(text.replace("size_bytes = ", "size_bytes = 1", 1), encoding="utf-8")
    assert _script("pipeline_project").run(tmp_path / "work", tmp_path / "data", fixture=fixture) == 1
    out = capsys.readouterr().out
    assert "step 1 of 4: voc load july_2026" in out
    assert "does not match the pinned file" in out
    assert "step 2 of 4" not in out


# The whole run, once for the tests below


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    folder = tmp_path_factory.mktemp("scheduled")
    work, data = folder / "work", folder / "data"
    eval_versions = (REPO / "EVAL_VERSIONS.md").read_bytes()
    out, err = io.StringIO(), io.StringIO()
    with (pytest.MonkeyPatch.context() as mp, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
        mp.setattr(Path, "home", staticmethod(lambda: folder / "home"))
        code = _script("pipeline_project").run(work, data)
    return {"code": code, "out": out.getvalue(), "err": err.getvalue(), "work": work,
            "home_untouched": not (folder / "home").exists(),
            "repo_eval_unchanged": (REPO / "EVAL_VERSIONS.md").read_bytes() == eval_versions}


def test_B14_the_scheduled_run_loads_builds_labels_and_evaluates_in_order(ran):
    assert ran["code"] == 0
    out = ran["out"]
    steps = ["step 1 of 4: voc load july_2026", "step 2 of 4: voc dbt build", "step 3 of 4: voc label dev",
             "step 4 of 4: voc evaluate dev"]
    positions = [out.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "loaded july_2026:" in out
    assert "dbt build:" in out and "failed 0, errors 0" in out
    assert "labelled dev:" in out and "evaluated prompt v1 on dev" in out


def test_B14_the_scheduled_run_writes_its_results_in_the_work_folder_only(ran):
    work = ran["work"]
    figures = json.loads((work / "results" / "eval" / "v1_dev.json").read_text(encoding="utf-8"))
    assert figures["backend"] == "mock"
    assert figures["complaints"] == len(_split_ids(FIXTURE / "splits", "dev"))
    assert (work / "EVAL_VERSIONS.md").is_file()
    assert ran["repo_eval_unchanged"]


def test_B3_the_scheduled_run_accepts_some_answers_and_quarantines_others(ran):
    decisions = _column(ran["work"] / "results" / "labels" / "v1_dev.csv", "decision")
    assert decisions.count("accepted") > 0 and decisions.count("quarantined") > 0


def test_B17_the_scheduled_run_never_labels_or_scores_a_test_complaint(ran):
    work, splits = ran["work"], FIXTURE / "splits"
    dev, test = _split_ids(splits, "dev"), _split_ids(splits, "test")
    for path in (work / "results" / "labels" / "v1_dev.csv", work / "results" / "eval" / "v1_dev.csv"):
        ids = set(_column(path, "complaint_id"))
        assert ids == dev and not ids & test
    assert sorted(p.name for p in (work / "results" / "labels").iterdir()) == ["v1_dev.csv", "v1_dev.json"]


def test_B17_the_scheduled_dbt_step_leaves_the_test_rows_out_of_the_models(ran):
    from voc.db import connect
    from voc.load import DB_PATH, TABLE

    test = _split_ids(FIXTURE / "splits", "test")
    con = connect(ran["work"] / DB_PATH)
    try:
        staged = {cid for (cid,) in con.execute(f"SELECT complaint_id FROM {TABLE}").fetchall()}
        assert test & staged
        for model in ("stg_complaints", "curated_complaints"):
            ids = {cid for (cid,) in con.execute(f"SELECT complaint_id FROM {model}").fetchall()}
            assert ids and not ids & test, model
        built = con.execute("SELECT count(*) FROM stg_complaints").fetchone()[0]
        assert built == len(staged - test)
    finally:
        con.close()


def _texts():
    narratives = [n for n in _column(FIXTURE / EXPORT, "Consumer complaint narrative") if n]
    quotes = [q for q in _column(FIXTURE / "answers.csv", "quote") if q]
    assert narratives and quotes
    return narratives + quotes


def test_B21_the_scheduled_run_prints_no_complaint_text(ran):
    texts = _texts()
    assert not any(text in ran["out"] for text in texts)
    assert not any(text in ran["err"] for text in texts)


def test_B21_the_run_says_synthetic_fixture_not_a_real_result_before_the_evaluate_figures(ran):
    out = ran["out"]
    assert "synthetic fixture, not a real result" in out.splitlines()
    assert out.index("step 4 of 4") < out.index("synthetic fixture, not a real result")
    assert out.index("synthetic fixture, not a real result") < out.index("evaluated prompt v1 on dev")


def test_B8_a_local_run_writes_no_ledger_entry_and_no_recording(ran):
    # The ledger and the recordings live under the home folder. The mock path never makes either.
    assert ran["code"] == 0 and ran["home_untouched"]


# The step entry the workflow calls


def test_B14_each_step_entry_gives_the_command_environment_and_root_the_workflow_relies_on(tmp_path):
    pipeline = _script("pipeline_project")
    work, data = tmp_path / "work", tmp_path / "data"
    assert list(pipeline.STEPS) == ["load", "dbt", "label", "evaluate"]
    for name, command in pipeline.STEPS.items():
        argv, env, root = pipeline.step_call(name, work, data)
        assert argv == list(command) and root == work
        assert env == {"LLM_BACKEND": "mock", "VOC_DATA_DIR": str(data),
                       "VOC_MOCK_FIXTURES": str(work / "mock" / "answers.json")}
    assert pipeline.STEPS["load"] == ("load", "july_2026")
    assert pipeline.STEPS["dbt"] == ("dbt", "build")
    assert pipeline.STEPS["label"][:2] == ("label", "dev")
    assert pipeline.STEPS["evaluate"][:2] == ("evaluate", "dev")


def test_B14_the_step_entry_refuses_an_unknown_step(tmp_path, capsys):
    assert _script("pipeline_project").main(["step", "sample", str(tmp_path / "w"), str(tmp_path / "d")]) == 2
    assert "usage" in capsys.readouterr().out


def test_B14_the_four_step_entries_in_order_pass_on_the_fixture(tmp_path, capfd, home):
    pipeline = _script("pipeline_project")
    work, data = str(tmp_path / "work"), str(tmp_path / "data")
    assert pipeline.main(["prepare", work, data]) == 0
    for name in ("load", "dbt", "label", "evaluate"):
        assert pipeline.main(["step", name, work, data]) == 0, name
    out, err = capfd.readouterr()
    assert "loaded july_2026:" in out and "failed 0, errors 0" in out and "labelled dev:" in out
    assert out.index("synthetic fixture, not a real result") < out.index("evaluated prompt v1 on dev")
    texts = _texts()
    assert not any(text in out for text in texts)
    assert not any(text in err for text in texts)
    # Fixed in the code commit: the home fixture makes this folder, so the check is that it stays empty.
    assert list(home.iterdir()) == []


def test_B14_a_failing_dbt_data_test_fails_the_dbt_step(tmp_path, capfd):
    from voc.db import connect
    from voc.load import DB_PATH, TABLE

    pipeline = _script("pipeline_project")
    work, data = tmp_path / "work", tmp_path / "data"
    assert pipeline.main(["prepare", str(work), str(data)]) == 0
    assert pipeline.main(["step", "load", str(work), str(data)]) == 0
    # A repeated complaint ID that skips the load checks, so only the dbt data test can catch it.
    con = connect(work / DB_PATH)
    try:
        con.execute(f"INSERT INTO {TABLE} (date_received, product, narrative, complaint_id, source) "
                    "VALUES (DATE '2026-07-09', 'Mortgage', 'SYN repeated row.', 'SYN-1', 'july_2026')")
    finally:
        con.close()
    capfd.readouterr()
    assert pipeline.main(["step", "dbt", str(work), str(data)]) == 1
    assert "failed: test source_unique_voc_staged_complaints_complaint_id" in capfd.readouterr().out


def test_B14_the_dbt_copy_skips_database_files_and_writes_its_own_profile(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(REPO / "config", repo / "config")
    shutil.copytree(REPO / "dbt", repo / "dbt", ignore=shutil.ignore_patterns("target", "logs"))
    for name in ("SYN.duckdb", "SYN.duckdb.wal"):
        (repo / "dbt" / name).write_bytes(b"SYN")
    (repo / "dbt" / "profiles.yml").write_text("SYN: a local profile that must not be copied\n", encoding="utf-8")
    work = tmp_path / "work"
    _script("pipeline_project").prepare(work, tmp_path / "data", repo=repo)
    assert not list((work / "dbt").rglob("*.duckdb*"))
    profile = yaml.safe_load((work / "dbt" / "profiles.yml").read_text(encoding="utf-8"))
    assert profile == yaml.safe_load((REPO / "dbt" / "profiles.yml").read_text(encoding="utf-8"))


# The workflow


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps():
    return [step for job in _workflow()["jobs"].values() for step in job["steps"]]


def test_B14_the_workflow_runs_once_a_day_and_on_manual_trigger():
    workflow = _workflow()
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 reads the key `on` as true
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    (schedule,) = triggers["schedule"]
    minute, hour, *rest = schedule["cron"].split()
    assert minute.isdigit() and hour.isdigit() and rest == ["*", "*", "*"]


# Review of pull request #31: the workflow calls the tested `step` entry, not `python -m voc.cli`.
# Three tests of the old form were replaced by the tests below:
# the commands in order (now test_B14_the_workflow_prepares_then_calls_each_step_entry_in_order),
# the mock backend, no network and no secret (now test_B14_each_step_entry_gives_..., test_B7_... and
# test_B12_the_workflow_holds_no_secret_...), and the test set (now test_B17_the_step_entries_...).

WORK_AND_DATA = '"$3" "$4"'
PATHS = '"$RUNNER_TEMP/pipeline/work" "$RUNNER_TEMP/pipeline/data"'


def _entry_runs():
    return [s["run"] for s in _steps() if "scripts/pipeline_project.py" in s.get("run", "")]


def test_B21_every_workflow_step_name_says_synthetic_fixture():
    workflow = _workflow()
    assert "synthetic fixture" in workflow["name"].lower()
    names = [s["name"] for s in _steps()]
    assert names and all("synthetic fixture" in name.lower() for name in names)


def test_B14_the_workflow_prepares_then_calls_each_step_entry_in_order():
    pipeline = _script("pipeline_project")
    runs = _entry_runs()
    called = [run.split("scripts/pipeline_project.py ", 1)[1].split()[:2] for run in runs]
    assert called == [["prepare", WORK_AND_DATA.split()[0]]] + [["step", name] for name in pipeline.STEPS]
    for run in runs:
        assert run.split("scripts/pipeline_project.py ", 1)[1].splitlines()[0].rstrip().endswith(WORK_AND_DATA)
        assert run.rstrip().endswith(PATHS)
    names = [s["name"] for s in _steps() if "scripts/pipeline_project.py step " in s.get("run", "")]
    assert len(set(names)) == len(names) == len(pipeline.STEPS)


def test_B7_the_workflow_runs_prepare_and_every_step_with_no_network():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "-m voc.cli" not in text and "voc.cli" not in text
    runs = _entry_runs()
    assert len(runs) == 5 and all("unshare --net" in run for run in runs)


def test_B12_the_workflow_holds_no_secret_and_no_key_and_reads_only():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets" not in text and "${{" not in text
    assert "anthropic" not in text.lower() and "LLM_BACKEND=api" not in text
    assert _workflow()["permissions"] == {"contents": "read"}


def test_B17_the_step_entries_never_take_the_test_set_path_or_the_owner_word():
    word = "fin" + "al"
    assert word not in WORKFLOW.read_text(encoding="utf-8").lower()
    for name, command in _script("pipeline_project").STEPS.items():
        assert "test" not in command and not any(word in part.lower() for part in command)
        if name in ("label", "evaluate"):
            assert command[1] == "dev"
