"""Spec 004, pull request 5a: the spike on synthetic data, and the committed seed copy. The spike's job is made in
the owner's workspace from `cloud/spike/job_spike.json` and run once on a zip of the synthetic dbt fixture, to
answer the open points of J8 and J16 before the real Job A (5b). Nothing here reads June or July data."""
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import git_helper

REPO = Path(__file__).resolve().parents[1]
SPIKE = REPO / "cloud" / "spike"
FIXTURE = REPO / "tests" / "fixtures" / "dbt" / "complaints.csv"


def _spike():
    from voc import spike

    return spike


def _job():
    return json.loads((SPIKE / "job_spike.json").read_text(encoding="utf-8"))


# The committed seed copy (owner decision, 5 November)


def test_T021_J8_the_seed_copy_is_a_byte_copy_of_the_july_test_list_and_alone_in_its_folder():
    assert (REPO / "dbt" / "seeds" / "test_list.csv").read_bytes() == (REPO / "splits" / "test.csv").read_bytes()
    assert sorted(p.name for p in (REPO / "dbt" / "seeds").iterdir()) == ["test_list.csv"]


def test_T021_J8_the_seed_copy_is_not_ignored_by_git(tmp_path):
    # The commit gate tests a copy of the staged files that is not a git checkout, so the repo's .gitignore is
    # checked in a new temp repo, as test_databricks.py does.
    git_helper.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copy(REPO / ".gitignore", tmp_path / ".gitignore")
    ignored = git_helper.run(["git", "check-ignore", "-q", "dbt/seeds/test_list.csv"], cwd=tmp_path)
    assert ignored.returncode == 1


# The spike's job definition


def test_J8_the_spike_job_has_three_tasks_in_order_from_the_public_repo():
    job = _job()
    assert job["git_source"] == {"git_url": "https://github.com/MannyAdc/voc-demo", "git_provider": "gitHub",
                                 "git_branch": "main"}
    tasks = {task["task_key"]: task for task in job["tasks"]}
    assert list(tasks) == ["unpack", "dbt", "job_a"]
    assert "depends_on" not in tasks["unpack"]
    assert tasks["dbt"]["depends_on"] == [{"task_key": "unpack"}]
    assert tasks["job_a"]["depends_on"] == [{"task_key": "dbt"}]
    for key in ("unpack", "job_a"):
        assert tasks[key]["notebook_task"] == {"notebook_path": f"cloud/spike/{key}", "source": "GIT"}
    dbt = tasks["dbt"]["dbt_task"]
    assert dbt["project_directory"] == "dbt" and dbt["schema"] == "voc_spike" and dbt["source"] == "GIT"
    assert all(command.startswith("dbt ") for command in dbt["commands"])
    assert job["max_concurrent_runs"] == 1


def test_J8_the_dbt_command_takes_unpacks_task_values():
    command = next(t for t in _job()["tasks"] if t["task_key"] == "dbt")["dbt_task"]["commands"][-1]
    for name in ("month_file", "month_sha256", "month_rows", "labels"):
        assert "{{tasks.unpack.values." + name + "}}" in command


def test_J8_the_spike_names_no_june_or_july_data_and_holds_no_secret():
    texts = [(SPIKE / name).read_text(encoding="utf-8") for name in ("job_spike.json", "unpack.py", "job_a.py")]
    texts += [(REPO / path).read_text(encoding="utf-8") for path in ("src/voc/spike.py", "scripts/make_spike_zip.py")]
    for text in texts:
        for word in ("CCDB_Export", "june_2026", "july_2026", "/incoming/", "/june/", "token", "secret", "password"):
            assert word.lower() not in text.lower(), word


# The spike's logic


def _zip(tmp_path, members):
    path = tmp_path / "spike.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_J8_unpack_writes_the_one_synthetic_csv_and_gives_dbt_its_values(tmp_path):
    folder = tmp_path / "incoming"
    folder.mkdir()
    _zip(folder, {"spike_complaints.csv": FIXTURE.read_bytes()})
    out = tmp_path / "spike"
    values = _spike().unpack(folder, out, REPO / "config" / "labels.toml")
    csv_path = out / "spike_complaints.csv"
    assert csv_path.read_bytes() == FIXTURE.read_bytes()
    rows = len(list(csv.reader(io.StringIO(FIXTURE.read_text(encoding="utf-8"))))) - 1
    assert values == {"month_file": str(csv_path), "month_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                      "month_rows": str(rows), "labels": values["labels"]}
    labels = json.loads(values["labels"])
    assert labels and all(isinstance(label, str) for label in labels)


@pytest.mark.parametrize("members, files", [
    ({}, ["spike.zip"]),
    ({"a.csv": b"x", "b.csv": b"y"}, ["spike.zip"]),
    ({"../evil.csv": b"x"}, ["spike.zip"]),
    ({"dir/a.csv": b"x"}, ["spike.zip"]),
    ({"spike_complaints.csv": None}, ["spike.zip", "other.txt"]),
    ({"spike_complaints.csv": None}, []),
])
def test_J8_unpack_refuses_anything_but_one_zip_with_one_flat_csv(tmp_path, members, files):
    folder = tmp_path / "incoming"
    folder.mkdir()
    members = {name: (FIXTURE.read_bytes() if data is None else data) for name, data in members.items()}
    if "spike.zip" in files:
        _zip(folder, members)
    if "other.txt" in files:
        (folder / "other.txt").write_text("x", encoding="utf-8")
    with pytest.raises(_spike().SpikeError):
        _spike().unpack(folder, tmp_path / "spike", REPO / "config" / "labels.toml")


def test_J8_unpack_refuses_a_row_that_is_not_synthetic(tmp_path):
    folder = tmp_path / "incoming"
    folder.mkdir()
    text = FIXTURE.read_text(encoding="utf-8").replace("SYN-", "12345", 1)
    _zip(folder, {"spike_complaints.csv": text.encode("utf-8")})
    with pytest.raises(_spike().SpikeError, match="synthetic"):
        _spike().unpack(folder, tmp_path / "spike", REPO / "config" / "labels.toml")
    assert not (tmp_path / "spike" / "spike_complaints.csv").exists()


def test_J5_the_spike_exit_value_holds_counts_only():
    value = json.loads(_spike().exit_value(landed_rows=12, staged_rows=12))
    assert value == {"contract": "voc-june-spike", "landed_rows": 12, "staged_rows": 12}


def test_J8_the_spike_zip_is_made_from_the_synthetic_fixture_only(tmp_path):
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "make_spike_zip.py"), str(tmp_path)],
                            capture_output=True, text=True, check=True)
    with zipfile.ZipFile(tmp_path / "spike.zip") as archive:
        assert archive.namelist() == ["spike_complaints.csv"]
        assert archive.read("spike_complaints.csv") == FIXTURE.read_bytes()
    zip_sha = hashlib.sha256((tmp_path / "spike.zip").read_bytes()).hexdigest()
    assert result.stdout.splitlines() == [f"spike.zip  {(tmp_path / 'spike.zip').stat().st_size} bytes  sha256 {zip_sha}"]


# The review of #92


def test_J8_the_spike_trigger_is_paused_until_the_owner_unpauses_it_and_watches_exactly_its_folder():
    trigger = _job()["trigger"]
    assert trigger["pause_status"] == "PAUSED"
    assert trigger["file_arrival"]["url"] == "/Volumes/workspace/default/voc_raw/spike_incoming/"


def test_B17_the_spike_dbt_command_passes_final_off():
    command = next(t for t in _job()["tasks"] if t["task_key"] == "dbt")["dbt_task"]["commands"][-1]
    assert '\"final\": false' in json.dumps(command) or '"final": false' in command


def test_J8_the_dbt_task_runs_in_an_environment_with_the_repos_dbt_databricks_pin():
    job = _job()
    dbt = next(t for t in job["tasks"] if t["task_key"] == "dbt")
    environments = {env["environment_key"]: env for env in job["environments"]}
    dependencies = environments[dbt["environment_key"]]["spec"]["dependencies"]
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert dependencies == ["dbt-databricks==1.13.0"] and '"dbt-databricks==1.13.0"' in pyproject


def test_J8_no_label_holds_a_quote_so_the_dbt_command_stays_whole():
    from voc.labels import load_labels

    assert all("'" not in label.name and '"' not in label.name for label in load_labels(REPO / "config" / "labels.toml"))


def test_J8_unpack_refuses_a_short_row_with_its_own_error(tmp_path):
    folder = tmp_path / "incoming"
    folder.mkdir()
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    _zip(folder, {"spike_complaints.csv": ("\n".join(lines[:2] + ["2026-07-01,Mortgage"]) + "\n").encode("utf-8")})
    with pytest.raises(_spike().SpikeError):
        _spike().unpack(folder, tmp_path / "spike", REPO / "config" / "labels.toml")


def test_J8_unpack_refuses_a_member_over_its_size_cap(tmp_path, monkeypatch):
    folder = tmp_path / "incoming"
    folder.mkdir()
    _zip(folder, {"spike_complaints.csv": FIXTURE.read_bytes()})
    monkeypatch.setattr(_spike(), "MAX_BYTES", 10)
    with pytest.raises(_spike().SpikeError, match="size"):
        _spike().unpack(folder, tmp_path / "spike", REPO / "config" / "labels.toml")
