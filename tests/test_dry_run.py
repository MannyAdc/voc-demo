"""Spec 004, pull request 9a: the dry run's setup, on synthetic data only (owner decisions of 6 and 8 November). Its
CSV, list, pin and mock answers, Job A's and Job B's path for a synthetic row, and the dry run's own hash path. No
test opens a network connection or calls a model."""
import copy
import csv
import hashlib
import importlib.util
import io
import json
import re
import shutil
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIST = REPO / "splits" / "june_dry" / "june_dry.csv"
PIN = REPO / "config" / "june_dry_run.toml"
# Review of #99, minor 4: the round comes from the pin, so a new round rewrites no test.
with open(PIN, "rb") as _f:
    ROUND = tomllib.load(_f)["round"]
STEM = f"syn_june_dry_run_r{ROUND}"
CSV = REPO / "tests" / "fixtures" / "june_dry_run" / f"{STEM}.csv"
IDS = re.compile(rf"SYN-9{ROUND}[0-9]{{2}}")
ANSWERS = REPO / "cloud" / "job_b" / "dry_run_answers.json"
MARKER = "SYNMARKER-DRYRUN"


def _script(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pin():
    with open(PIN, "rb") as f:
        return tomllib.load(f)["june_dry_run"]


def _records():
    return list(csv.reader(io.StringIO(CSV.read_text(encoding="utf-8"), newline="")))


def _target(kind="synthetic", list_hash=None):
    from voc.frozen import dry_run_list_hash
    from voc.job_a import Target

    return Target(kind=kind, entry_kind=kind, list_hash=list_hash or dry_run_list_hash(REPO), code_hash="b" * 64,
                  row=1)


def _listed_ids():
    return [cid for cid, _ in csv.reader(io.StringIO(LIST.read_text(encoding="utf-8")))][1:]


def _listed_rows():
    """The listed rows as Job A reads them from the June tables: (complaint_id, product, narrative)."""
    listed = {row[0] for row in csv.reader(io.StringIO(LIST.read_text(encoding="utf-8")))} - {"complaint_id"}
    return [(r[15], r[1], r[5]) for r in _records()[1:] if r[15] in listed]


# The CSV, its zip and its pin (J8)


def test_J8_the_dry_run_csv_is_synthetic_with_the_cfpb_header_and_the_pinned_counts():
    from voc.job_a import has_text
    from voc.labels import load_labels
    from voc.repo_checks import CFPB_COLUMNS

    records = _records()
    assert records[0] == list(CFPB_COLUMNS) and b"\r" not in CSV.read_bytes()
    rows, pin = records[1:], _pin()
    assert all(IDS.fullmatch(r[15]) for r in rows) and len({r[15] for r in rows}) == len(rows)
    assert pin["rows"] == len(rows) == 12 and pin["narratives"] == sum(has_text(r[5]) for r in rows) == 11
    labels = {label.name for label in load_labels(REPO / "config" / "labels.toml")}
    assert {r[1] for r in rows} <= labels
    # dbt's typed checks: yyyy-mm-dd dates and a Yes or No flag (dbt/tests/landed_rows_are_valid.sql).
    assert all(re.fullmatch(r"2026-06-[0-9]{2}", r[0]) and r[0] == r[12] and r[14] in ("Yes", "No") for r in rows)
    # A live J5 check, a line break inside a quoted narrative, and a complaint with no narrative.
    assert sum(MARKER in r[5] for r in rows) == 1 and sum("\n" in r[5] for r in rows) == 1
    assert sum(not r[5] for r in rows) == 1


def test_J8_the_dry_run_pin_names_syn_files_apart_from_the_june_pin():
    from voc.datafile import load_pins

    pin, june = _pin(), load_pins(REPO / "config" / "data_files.toml")["june_2026"]
    assert set(pin) == {"file_name", "size_bytes", "sha256", "rows", "narratives", "zip_file_name", "zip_size_bytes",
                        "zip_sha256"}
    assert pin["file_name"] == f"{STEM}.csv" and pin["zip_file_name"] == f"{STEM}.zip"
    assert pin["sha256"] == hashlib.sha256(CSV.read_bytes()).hexdigest() and pin["size_bytes"] == CSV.stat().st_size
    assert pin["sha256"] != june["sha256"] and pin["zip_sha256"] != june["zip_sha256"]
    manifest = json.loads((REPO / "splits" / "june_dry" / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(ROUND, int) and manifest["lists"]["june_dry"]["round"] == ROUND


def test_J8_the_dry_run_zip_is_stored_with_fixed_fields_and_its_pinned_bytes():
    """The same bytes on every platform, so CI rebuilds the zip the owner uploads (owner decision, 8 November)."""
    files = _script("make_dry_run").build(REPO, ROUND)
    pin = _pin()
    assert hashlib.sha256(files["zip"]).hexdigest() == pin["zip_sha256"] and len(files["zip"]) == pin["zip_size_bytes"]
    with zipfile.ZipFile(io.BytesIO(files["zip"])) as archive:
        (info,) = archive.infolist()
        assert info.filename == pin["file_name"] and info.compress_type == zipfile.ZIP_STORED
        assert info.create_system == 3 and info.date_time == (2026, 6, 30, 0, 0, 0)
        assert archive.read(info) == CSV.read_bytes()


def test_J8_the_dry_run_script_makes_the_committed_files_byte_for_byte():
    module = _script("make_dry_run")
    for name, data in module.repo_files(module.build(REPO, ROUND)).items():
        assert (REPO / name).read_bytes() == data, name


def test_J8_unpack_takes_the_dry_run_zip_against_its_pin(tmp_path):
    from voc.job_a import file_counts, pin_for, unpack

    files = _script("make_dry_run").build(REPO, ROUND)
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / _pin()["zip_file_name"]).write_bytes(files["zip"])
    values = unpack(incoming, tmp_path / "june", pin_for(REPO, "synthetic"), REPO / "config" / "labels.toml")
    assert values["month_sha256"] == _pin()["sha256"] and values["month_rows"] == "12"
    counts = file_counts(values["month_file"])
    assert counts["rows"] == 12 and counts["narratives"] == 11 and counts["fields_with_lone_returns"] == 0


# The dry run's list (J1)


def test_J1_the_dry_run_list_is_the_csv_s_rows_with_their_content_hashes():
    from voc.data import content_hash
    from voc.frozen import dry_run_list_hash

    listed = list(csv.reader(io.StringIO(LIST.read_text(encoding="utf-8"))))
    assert listed[0] == ["complaint_id", "content_hash"] and len(listed) == 9
    by_id = {r[15]: r for r in _records()[1:]}
    for cid, digest in listed[1:]:
        assert IDS.fullmatch(cid) and by_id[cid][5] and digest == content_hash(by_id[cid][5],
                                                                                                    by_id[cid][1])
    manifest = json.loads((REPO / "splits" / "june_dry" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lists"]["june_dry"] == {"count": 8, "round": ROUND, "sha256": dry_run_list_hash(REPO)}
    assert dry_run_list_hash(REPO) == hashlib.sha256(LIST.read_bytes()).hexdigest()


def test_J1_the_dry_run_list_is_not_the_june_list():
    from voc.frozen import dry_run_list_hash, list_hash

    assert dry_run_list_hash(REPO) != list_hash(REPO)


# Job A's path for a synthetic row (J8, J16)


def _dry_root(tmp_path, kind="synthetic", dry_ids=None, with_files=False):
    """A checkout with the dry run's list, a June list and a run log whose one row names the dry run's list."""
    from voc.data import content_hash
    from voc.frozen import code_hash

    root = tmp_path / "root"
    (root / "splits" / "june").mkdir(parents=True)
    june = ("complaint_id,content_hash\n" + f"3141592,{content_hash('x', 'Mortgage')}\n").encode()
    (root / "splits" / "june" / "june.csv").write_bytes(june)
    (root / "splits" / "june" / "manifest.json").write_text(json.dumps(
        {"lists": {"june": {"count": 1, "sha256": hashlib.sha256(june).hexdigest()}}}), encoding="utf-8")
    shutil.copytree(REPO / "splits" / "june_dry", root / "splits" / "june_dry")
    if dry_ids is not None:
        data = ("complaint_id,content_hash\n" + "".join(f"{cid},{'a' * 64}\n" for cid in dry_ids)).encode()
        (root / "splits" / "june_dry" / "june_dry.csv").write_bytes(data)
        (root / "splits" / "june_dry" / "manifest.json").write_text(json.dumps(
            {"lists": {"june_dry": {"count": len(dry_ids), "round": ROUND,
                                    "sha256": hashlib.sha256(data).hexdigest()}}}),
            encoding="utf-8")
    shutil.copytree(REPO / "config", root / "config")
    if with_files:  # review of #99, nit 11: what Job B reads, and the jobs' IDs, before the code hash
        (root / "results" / "eval").mkdir(parents=True)
        shutil.copyfile(REPO / "results" / "eval" / "v1_test.json", root / "results" / "eval" / "v1_test.json")
        (root / "cloud" / "job_b").mkdir(parents=True)
        shutil.copyfile(ANSWERS, root / "cloud" / "job_b" / "dry_run_answers.json")
        (root / "config" / "june_cloud.toml").write_text("job_a_job_id = 800001\njob_b_job_id = 800002\n",
                                                         encoding="utf-8")
    listed = hashlib.sha256((root / "splits" / "june_dry" / "june_dry.csv").read_bytes()).hexdigest()
    (root / "runs").mkdir()
    (root / "runs" / "JUNE_RUNS.md").write_text(
        "| Date | Kind | June list hash | Code hash | Reason |\n|---|---|---|---|---|\n"
        f"| 2026-11-13 10:00 | {kind} | {listed} | {code_hash(root)} | the dry run |\n", encoding="utf-8")
    return root


def test_J16_job_a_takes_a_synthetic_row_naming_the_dry_run_list(tmp_path):
    from voc.job_a import checked_target

    root = _dry_root(tmp_path)
    run_target = checked_target(root)
    assert run_target.kind == run_target.entry_kind == "synthetic" and run_target.row == 1


def test_J16_job_a_s_synthetic_pin_is_the_dry_run_pin_and_the_real_one_the_june_pin():
    from voc.datafile import load_pins
    from voc.job_a import pin_for

    assert pin_for(REPO, "synthetic") == _pin()
    assert pin_for(REPO, "real") == load_pins(REPO / "config" / "data_files.toml")["june_2026"]


def test_J16_job_a_reads_the_dry_run_list_for_a_synthetic_row_and_the_june_list_for_a_real_one():
    from voc.job_a import listed_ids

    synthetic = listed_ids(REPO, _target())
    assert synthetic == [cid for cid, _ in csv.reader(io.StringIO(LIST.read_text(encoding="utf-8")))][1:]
    assert len(synthetic) == 8 and all(IDS.fullmatch(cid) for cid in synthetic)
    # Review of #99, nit 11: every June ID, not the first five.
    assert not any(cid.startswith("SYN-") for cid in listed_ids(REPO))


def test_J16_job_a_refuses_a_dry_run_list_id_that_is_not_synthetic(tmp_path):
    from voc.job_a import JobAError, checked_target, listed_ids

    root = _dry_root(tmp_path, dry_ids=["SYN-9101", "3141592"])
    with pytest.raises(JobAError, match="not synthetic"):
        listed_ids(root, checked_target(root))


def test_J16_the_job_a_notebook_passes_the_target_to_both_list_reads():
    text = (REPO / "cloud" / "job_a" / "job_a.py").read_text(encoding="utf-8")
    assert "listed_ids(root, run_target)" in text and "checked_sample(root, rows, run_target)" in text


def test_J8_job_a_on_the_dry_run_s_rows_gives_an_exit_value_the_workflow_takes():
    from voc import approval
    from voc.job_a import checked_sample, exit_value, figures, pin_for

    rows, run_target = _listed_rows(), _target()
    assert checked_sample(REPO, rows, run_target) == 8
    value = json.loads(exit_value(run_target, pin_for(REPO, "synthetic"), figures(REPO, rows, 0)))
    output = {"notebook_output": {"result": json.dumps(value), "truncated": False}}
    assert approval.exit_value(output) == value
    approval.checked_exit(value, run_target, approval._pin(REPO, "synthetic"))
    assert value["kind"] == "synthetic" and value["complaints"] == 8


# Job B's path for a synthetic row (J11)


def test_J11_job_b_reads_the_committed_dry_run_list_bound_to_the_row():
    from voc.job_b import checked_list, listed_for

    listed = checked_list(listed_for(REPO, _target()), _target())
    assert sorted(listed) == sorted(_listed_ids()) and len(listed) == 8


def test_J11_job_b_s_list_and_answers_refuse_a_real_row():
    from voc.job_b import JobBError, listed_for, mock_answers

    for seam in (listed_for, mock_answers):
        with pytest.raises(JobBError, match="synthetic row only"):
            seam(REPO, _target(kind="real", list_hash="a" * 64))


def test_J11_the_mock_answers_cover_every_dry_run_prompt_with_one_quarantine():
    """Seven accepted labels with their quotes, and one quote the text does not hold, for the quarantine path."""
    from voc import pipeline
    from voc.backends import make_backend
    from voc.job_b import _outcomes, mock_answers
    from voc.labels import load_labels
    from voc.replay import Answer, Reply

    answers, rows = mock_answers(REPO, _target()), _listed_rows()
    # Fix-round review of #99, nit 6: the function `run` itself uses.
    decided, stopped = _outcomes(REPO, rows, answers)
    assert len(answers) == 8 and len(decided) == 8 and stopped is False
    version = pipeline.load_prompt_version(REPO, "v1")
    backend = make_backend("mock", fixtures={a["prompt"]: Answer(a["text"], None, None, "end_turn") for a in answers})
    outcomes = pipeline.label_complaints(
        [pipeline.Complaint(cid, narrative) for cid, _, narrative in rows], version,
        load_labels(REPO / "config" / "labels.toml"),
        lambda prompt: Reply(backend(prompt, dict(version.settings)).text, "mock", None, None, 0, 0, 1), "mock")
    accepted = {o.decision.complaint_id: o.decision.label for o in outcomes if o.decision.label}
    last = _listed_ids()[-1]
    assert accepted == {cid: product for cid, product, _ in rows if cid != last}
    assert [o.decision.complaint_id for o in outcomes if o.decision.reason] == [last]


class Jobs:
    def __init__(self, job_a_exit):
        self.job_a_exit = job_a_exit

    def get(self, path, params):
        fixtures = REPO / "tests" / "fixtures" / "june_contract"
        if path == "/api/2.2/jobs/runs/get" and params["run_id"] == 900002:
            return {"run_id": 900002, "job_id": 800002, "state": {"life_cycle_state": "RUNNING"},
                    "job_parameters": [{"name": "job_a_run_id", "value": "900001"},
                                       {"name": "github_run_id", "value": "600001"}],
                    "git_source": {"git_snapshot": {"used_commit": "c" * 40}}}
        if path == "/api/2.2/jobs/runs/get":
            return json.loads((fixtures / "job_a_run.json").read_text(encoding="utf-8"))
        if path == "/api/2.2/jobs/runs/list" and "active_only" in params:
            return {}
        if path == "/api/2.2/jobs/runs/list":
            return json.loads((fixtures / "job_a_runs_list.json").read_text(encoding="utf-8"))
        return {"notebook_output": {"result": json.dumps(self.job_a_exit), "truncated": False}}


class GitHub:
    def get(self, path):
        fixtures = REPO / "tests" / "fixtures" / "june_contract"
        if path.endswith("/approvals"):
            return 200, (fixtures / "github_approvals.json").read_bytes()
        run = json.loads((fixtures / "github_run.json").read_text(encoding="utf-8"))
        return 200, json.dumps({**run, "head_sha": "c" * 40}).encode()


class Files:
    def __init__(self):
        self.files = {}

    def get_metadata(self, path):
        if path not in self.files:
            raise type("NotFound", (Exception,), {})("missing")

    def create_directory(self, path):
        pass

    def upload(self, path, contents, overwrite=None):
        assert overwrite is False and path not in self.files
        self.files[path] = contents.read()


def test_J11_job_b_runs_the_dry_run_end_to_end_on_the_committed_files(monkeypatch, capsys):
    from voc import approval, job_b
    from voc.frozen import Entry
    from voc.job_a import exit_value, figures, pin_for

    run_target, rows = _target(), _listed_rows()
    entry = Entry(date="2026-11-13 10:00", kind="synthetic", list_hash=run_target.list_hash, code_hash="b" * 64,
                  reason="the dry run")
    monkeypatch.setattr(approval, "_target_and_entry", lambda root: (run_target, entry))
    monkeypatch.setattr(approval, "cloud_settings", lambda root: {"job_a_job_id": 800001, "job_b_job_id": 800002})
    job_a_exit = json.loads(exit_value(run_target, pin_for(REPO, "synthetic"), figures(REPO, rows, 0)))
    files = Files()
    raw = job_b.run(REPO, {"job_a_run_id": "900001", "github_run_id": "600001", "job_b_run_id": "900002"},
                    Jobs(job_a_exit), GitHub(), job_b.VolumeStore(files), lambda sql: copy.deepcopy(rows),
                    sleep=lambda s: None)
    value = json.loads(raw)
    assert value == {"complaints": 8, "contract": "voc-june-1", "entry_kind": "synthetic", "kind": "synthetic",
                     "labelled": 8, "results_folder": "june-900002", "stop_reason": None, "stopped": False}
    assert not any(MARKER.encode() in data for data in files.files.values())
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# The dry run's own hash path (J1, owner decision of 8 November)


def _hash_root(tmp_path, with_ids):
    root = tmp_path / "root"
    shutil.copytree(REPO / "config", root / "config")
    shutil.copytree(REPO / "splits" / "june_dry", root / "splits" / "june_dry")
    shutil.copytree(REPO / "splits" / "june", root / "splits" / "june")
    if with_ids:
        (root / "config" / "june_cloud.toml").write_text("job_a_job_id = 800001\njob_b_job_id = 800002\n",
                                                         encoding="utf-8")
    else:
        # The job IDs pull request commits the file, so a checkout without it is made by removing the copy.
        (root / "config" / "june_cloud.toml").unlink(missing_ok=True)
    return root


def test_J1_the_dry_run_hash_path_refuses_until_the_jobs_ids_are_committed(tmp_path, capsys):
    root = _hash_root(tmp_path, with_ids=False)
    assert _script("june_hash").main(["--dry-run", str(root)]) == 1
    out = capsys.readouterr().out
    assert "june_cloud.toml" in out and "sha256" not in out


def test_J1_the_dry_run_hash_path_prints_its_list_hash_and_code_hash_with_no_gate(tmp_path, capsys):
    from voc.frozen import code_hash, dry_run_list_hash, frozen_files, list_hash

    root = _hash_root(tmp_path, with_ids=True)
    assert _script("june_hash").main(["--dry-run", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == [f"dry-run list sha256 {dry_run_list_hash(root)}",
                                f"frozen code sha256 {code_hash(root)} over {len(frozen_files(root))} files"]
    assert list_hash(root) not in out


def test_J1_the_hash_script_still_has_no_synthetic_flag_and_takes_one_folder(tmp_path, capsys):
    root = _hash_root(tmp_path, with_ids=True)
    for argv in (["--synthetic", str(root)], ["--dry-run", str(root), str(root)], ["--dry-run", "--other"]):
        assert _script("june_hash").main(argv) == 1
    assert "sha256" not in capsys.readouterr().out


# J5: the script prints names, sizes and hashes only


def test_J5_the_dry_run_script_prints_names_sizes_and_hashes_only(tmp_path, capsys):
    module = _script("make_dry_run")
    assert module.main(["--round", str(ROUND), str(tmp_path / "zip")]) == 0
    out = capsys.readouterr().out
    assert re.fullmatch(rf"{STEM}\.zip  [0-9]+ bytes  sha256 [0-9a-f]{{64}}\n", out)
    assert (tmp_path / "zip" / f"{STEM}.zip").read_bytes() == module.build(REPO, ROUND)["zip"]
    assert module.main(["--round", str(ROUND), str(REPO / "inside")]) == 2 and not (REPO / "inside").exists()


# The review of #99 (owner decision: fix every finding, with one fresh review of the fix round)


def test_J8_the_pin_s_round_must_match_the_list_s_round(tmp_path):
    """Minor 4: a pin and a list of different rounds are refused."""
    from voc.job_a import JobAError, pin_for

    root = tmp_path / "root"
    shutil.copytree(REPO / "config", root / "config")
    shutil.copytree(REPO / "splits" / "june_dry", root / "splits" / "june_dry")
    manifest = json.loads((root / "splits" / "june_dry" / "manifest.json").read_text(encoding="utf-8"))
    manifest["lists"]["june_dry"]["round"] = ROUND + 1
    (root / "splits" / "june_dry" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(JobAError, match="round"):
        pin_for(root, "synthetic")


def test_J16_job_a_refuses_a_synthetic_row_naming_another_list_hash(tmp_path):
    """Minor 5: the checkout's dry run list is there, and the row names a stale one."""
    from voc.job_a import JobAError, checked_target

    root = _dry_root(tmp_path)
    text = (root / "runs" / "JUNE_RUNS.md").read_text(encoding="utf-8")
    stale = text.replace(hashlib.sha256(LIST.read_bytes()).hexdigest(), "f" * 64)
    (root / "runs" / "JUNE_RUNS.md").write_text(stale, encoding="utf-8")
    with pytest.raises(JobAError) as refused:
        checked_target(root)
    assert str(refused.value) == ("the run log's last row names a June list other than "
                                  "splits/june_dry/june_dry.csv")


def test_J8_unpack_refuses_a_synthetic_csv_with_an_id_that_is_not_synthetic(tmp_path):
    """Minor 6: a second guard behind the pin's SHA-256, before dbt reads a byte."""
    from voc.job_a import JobAError, unpack

    data = CSV.read_bytes().replace(b",SYN-9", b",9", 1)
    pin = {**_pin(), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    archive = _script("make_dry_run").zip_bytes(pin["file_name"], data)
    pin.update(zip_size_bytes=len(archive), zip_sha256=hashlib.sha256(archive).hexdigest())
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / pin["zip_file_name"]).write_bytes(archive)
    with pytest.raises(JobAError, match="not synthetic"):
        unpack(incoming, tmp_path / "june", pin, REPO / "config" / "labels.toml")
    assert not (tmp_path / "june" / pin["file_name"]).exists()


def test_J11_the_dry_run_note_gives_the_accepted_and_quarantined_counts(monkeypatch):
    """Minor 1: the split of 7 and 1 is seen in the cloud, as counts only."""
    from voc import approval, job_b
    from voc.frozen import Entry
    from voc.job_a import exit_value, figures, pin_for

    run_target, rows = _target(), _listed_rows()
    entry = Entry(date="2026-11-13 10:00", kind="synthetic", list_hash=run_target.list_hash, code_hash="b" * 64,
                  reason="the dry run")
    monkeypatch.setattr(approval, "_target_and_entry", lambda root: (run_target, entry))
    monkeypatch.setattr(approval, "cloud_settings", lambda root: {"job_a_job_id": 800001, "job_b_job_id": 800002})
    job_a_exit = json.loads(exit_value(run_target, pin_for(REPO, "synthetic"), figures(REPO, rows, 0)))
    files = Files()
    job_b.run(REPO, {"job_a_run_id": "900001", "github_run_id": "600001", "job_b_run_id": "900002"},
              Jobs(job_a_exit), GitHub(), job_b.VolumeStore(files), lambda sql: copy.deepcopy(rows),
              sleep=lambda s: None)
    note = files.files["/Volumes/workspace/voc_results/voc_results/june-900002/DRY_RUN.txt"].decode("utf-8")
    assert note.endswith("Labelled: 8. Accepted: 7. Quarantined: 1.\n")  # fix-round review of #99, nit 4
    assert not any(cid in note for cid, _, _ in rows) and MARKER not in note


def test_J11_job_b_runs_the_dry_run_on_a_checkout_with_its_real_run_log_row(tmp_path):
    """Nit 11: no patched target or settings. A checkout with the dry run's row, the jobs' IDs and its code hash."""
    from voc import job_b
    from voc.job_a import checked_target, exit_value, figures, pin_for

    root = _dry_root(tmp_path, with_files=True)
    run_target, rows = checked_target(root), _listed_rows()
    job_a_exit = json.loads(exit_value(run_target, pin_for(root, "synthetic"), figures(root, rows, 0)))
    files = Files()
    value = json.loads(job_b.run(root, {"job_a_run_id": "900001", "github_run_id": "600001",
                                        "job_b_run_id": "900002"},
                                 Jobs(job_a_exit), GitHub(), job_b.VolumeStore(files),
                                 lambda sql: copy.deepcopy(rows), sleep=lambda s: None))
    assert value["stopped"] is False and value["labelled"] == 8 and value["entry_kind"] == "synthetic"


def test_J1_the_dry_run_steps_keep_main_still_from_the_upload_and_use_the_repo_s_python():
    """Minors 2, 3 and 7, and nit 10."""
    text = (REPO / "docs" / "DRY_RUN_STEPS.md").read_text(encoding="utf-8")
    assert "from the upload until Job B ends" in text
    assert "a fresh upload" in text
    assert "uv run --native-tls --locked python scripts/make_dry_run.py" in text
    assert "uv run --native-tls --locked python scripts/june_hash.py --dry-run" in text
    assert "`python scripts/" not in text
    assert "every table and view" in text


# The fix-round review of #99 (owner's stopping rule: nothing serious, so Claude fixes the minors and nits)


def test_J16_an_unreadable_dry_run_list_is_refused_as_unreadable(tmp_path):
    """Minor 2: the refusal says the checkout's file cannot be read, not that the row names another list."""
    from voc.job_a import JobAError, checked_target

    root = _dry_root(tmp_path)
    (root / "splits" / "june_dry" / "manifest.json").unlink()
    with pytest.raises(JobAError) as refused:
        checked_target(root)
    assert str(refused.value) == ("the checkout's June list file, splits/june_dry/june_dry.csv, or its manifest "
                                  "cannot be read, so the run log's last row cannot be checked")


def test_J1_the_re_run_steps_say_how_to_start_a_fresh_workflow_run_and_the_note_holds_counts():
    """Minor 1 and nit 3."""
    text = (REPO / "docs" / "DRY_RUN_STEPS.md").read_text(encoding="utf-8")
    assert "start `June approval` by hand on `main`" in text and "GitHub's re-run button" in text
    assert "IDs, states, counts and fixed text only" in text


# The jobs' IDs and the Databricks setup steps (owner decisions of 8 and 9 November)

DATABRICKS_STEPS = REPO / "docs" / "DATABRICKS_STEPS.md"


def test_J16_the_jobs_ids_are_the_jobs_the_owner_made():
    """J16 item 10: Job A's and Job B's IDs, made by the owner in the workspace on 9 November."""
    from voc.approval import cloud_settings

    assert cloud_settings(REPO) == {"job_a_job_id": 980148595231243, "job_b_job_id": 111509808656471}


def test_J1_the_databricks_steps_1_go_click_by_click_with_no_azure_host_or_guid():
    """Owner decision, 9 November: every step names its clicks in order, for a reader new to Databricks."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    steps = re.findall(r"^### Step (1\.[0-9]+): ", text, flags=re.M)
    assert steps == [f"1.{n}" for n in range(1, 9)]
    for words in ("Copy raw file", "just left of the grey **Run now** button", "**Can View**", "**Can Manage Run**",
                  "**Paused**", "`voc_results`", "`voc-receiver`", "**On success**", "Clear all"):
        assert words in text, words
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.I)
    assert set(re.findall(r"(\S*)azurewebsites\.net", text)) <= {"`."}
    assert "<default domain>" in text and "<the ID>" in text


# The review of #100 (owner decisions of 9 November: option A, the results volume in its own schema, and every
# other finding fixed)


def test_J13_job_b_writes_its_results_to_their_own_schema():
    """Serious 1: `voc_results` sits in its own schema, apart from `default`, which holds the raw uploads."""
    from voc.job_b import RESULTS_VOLUME

    assert RESULTS_VOLUME == "/Volumes/workspace/voc_results/voc_results" and "/default/" not in RESULTS_VOLUME


def test_J1_the_databricks_steps_make_the_results_schema_and_explain_the_word():
    """Serious 1: the step makes the schema, then the volume, and says what a schema is the first time."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    step = text.split("### Step 1.2: ")[1].split("\n### ")[0]
    assert "schema (a folder that holds tables and volumes)" in text
    assert step.index("Create schema") < step.index("Volume") and "`workspace` → `voc_results`" in step


def test_J1_the_databricks_steps_check_the_live_jobs_against_their_files():
    """Minors 2 and 3, nits 9 and 10."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    assert "**Run as**" in text and "never `voc-june-runner`" in text
    assert "compare it with `cloud/job_a.yml`" in text and "`pause_status: PAUSED`" in text
    assert "`email_notifications`" in text and "cancel" in text
    job_a = (REPO / "cloud" / "job_a.yml").read_text(encoding="utf-8")
    for line in ("warehouse_id: the SQL warehouse's ID, set by the owner", "webhook_notifications:", "on_success:",
                 "- id: the receiver's notification destination ID, set by the owner"):
        assert line in job_a and f"`{line}`" in text, line
    assert "attach the destination by clicking" in job_a


def test_J1_the_databricks_steps_copy_secrets_without_showing_them_and_clear_the_clipboard_either_way():
    """Minor 6."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    assert "Show Secret Value" not in text
    assert "clipboard history is off" in text


def test_J1_the_databricks_steps_hold_no_workspace_host_vault_address_or_warehouse_id():
    """Minor 7."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    for host in ("cloud.databricks.com", "azuredatabricks.net", "vault.azure.net"):
        assert host not in text, host
    assert not re.search(r"\b[0-9a-f]{16}\b", text)


def test_J8_the_spec_and_the_steps_name_the_dry_run_as_the_webhook_s_test():
    """Minor 4, nit 11."""
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    assert "the dry run's Job A run is that test" in spec and "attach the destination by clicking" in spec
    dry = (REPO / "docs" / "DRY_RUN_STEPS.md").read_text(encoding="utf-8")
    assert "DATABRICKS_STEPS.md" in dry and "Claude gives the click-by-click steps in the chat" not in dry


# The fix-round review of #100 (owner's stopping rule: nothing serious, so Claude fixes the minors and nits)


def test_J8_the_dry_run_steps_say_what_to_do_if_no_approval_run_appears():
    """Minor 1: the dry run's Job A run is the webhook's test, and the spec no longer names a destination test."""
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    assert "Use the destination's test" not in spec
    dry = (REPO / "docs" / "DRY_RUN_STEPS.md").read_text(encoding="utf-8")
    assert "no `June approval` run appears" in dry and "J8's fallback" in dry


def test_J1_the_steps_record_the_live_job_check_and_the_officer_role_s_removal():
    """Minors 2 and 6: the owner compared the live Job A with its file, and removed the Secrets Officer role."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    assert "### Step 2.7: " in text and "### Step 2.8: " in text
    check = text.split("### Step 2.7: ")[1].split("\n### ")[0]
    for words in ("`max_concurrent_runs`", "`queue`", "`performance_target`"):
        assert words in check, words
    role = text.split("### Step 2.8: ")[1].split("\n### ")[0]
    assert "Key Vault Secrets Officer" in role and "Key Vault Secrets User" in role


def test_J10_the_steps_name_every_secret_the_workflow_and_the_receiver_read():
    """Minor 5: the steps' secret names are the workflow's and the receiver's own."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    workflow = (REPO / ".github" / "workflows" / "june_approval.yml").read_text(encoding="utf-8")
    for name in set(re.findall(r"secrets\.([A-Z_]+)", workflow)):
        assert f"`{name}`" in text, name
    settings = json.loads((REPO / "receiver" / "app_settings.json").read_text(encoding="utf-8"))
    for value in settings.values():
        found = re.search(r"SecretName=([a-z-]+)\)", value)
        if found and found.group(1) not in ("voc-basic-user", "voc-basic-password", "voc-hmac-secret"):
            assert f"SecretName={found.group(1)})" in text, found.group(1)


def test_J1_the_steps_count_six_green_ticks_and_warn_about_the_one_time_boxes():
    """Minors 3 and 4: the receiver has six Key Vault references, and two boxes show a new secret once."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    assert "all six did" in text and "all five did" not in text
    assert "never take a screenshot or share your screen" in text


# The dry run's row (plan item 9, owner decisions of 8 November: the row comes last, after the jobs' IDs)


def test_J1_the_run_log_s_last_row_is_the_dry_run_s_on_the_frozen_code():
    """The last row is synthetic, names the dry run's list and this checkout's frozen code, and Job A takes it.

    It pins round 1's one row and today's code hash on purpose, as a tripwire: any later change to a frozen file
    fails it in CI before the dry run. The next row, a round 2 or the real June row, or the next frozen change
    after the dry run retires it, in that pull request, marked and logged (review of #101)."""
    from voc.frozen import code_hash, dry_run_list_hash, read_runs
    from voc.job_a import checked_target, pin_for

    entries = read_runs(REPO / "runs" / "JUNE_RUNS.md")
    assert len(entries) == 1
    row = entries[-1]
    assert row.kind == "synthetic" and row.list_hash == dry_run_list_hash(REPO) and row.code_hash == code_hash(REPO)
    assert re.fullmatch(r"2026-11-09 [0-9]{2}:[0-9]{2}", row.date) and "round 1" in row.reason
    run_target = checked_target(REPO)
    assert (run_target.kind, run_target.entry_kind, run_target.row) == ("synthetic", "synthetic", 1)
    assert pin_for(REPO, run_target.kind) == _pin()


# The dry run's round 2 (owner decisions of 9 November, after round 1 stopped at the repair history check)


def test_J8_round_2_has_its_own_synthetic_ids_apart_from_round_1():
    """A list has one first row, and the June staging table never changes a row it has built, so a round after a code
    fix gets new IDs. Round 1's CSV stays, as its record."""
    assert ROUND == 2
    old = REPO / "tests" / "fixtures" / "june_dry_run" / "syn_june_dry_run_r1.csv"
    old_ids = {r[15] for r in list(csv.reader(io.StringIO(old.read_text(encoding="utf-8"), newline="")))[1:]}
    new_ids = {r[15] for r in _records()[1:]}
    assert all(re.fullmatch(r"SYN-92[0-9]{2}", cid) for cid in new_ids) and not old_ids & new_ids
    assert len(new_ids) == len(old_ids) == 12


def test_J13_the_steps_give_the_robot_s_secret_the_jobs_scope_with_read_and_write():
    """Round 1: the secret made with `jobs:read` was refused (HTTP 403). The run-now of Job B needs write."""
    text = DATABRICKS_STEPS.read_text(encoding="utf-8")
    step = text.split("### Step 2.4: ")[1].split("\n### ")[0]
    assert "**Read + Write**" in step and "`jobs:read`" in step and "**Other APIs**" in step


def test_J1_the_dry_run_steps_make_the_zip_of_round_2_and_clean_up_round_1_first():
    text = (REPO / "docs" / "DRY_RUN_STEPS.md").read_text(encoding="utf-8")
    assert "--round 2" in text and "--round 1" not in text
    assert "round 1's zip" in text and "every table and view in the `voc_june` schema" in text
