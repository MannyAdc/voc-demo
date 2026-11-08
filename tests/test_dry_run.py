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
CSV = REPO / "tests" / "fixtures" / "june_dry_run" / "syn_june_dry_run_r1.csv"
LIST = REPO / "splits" / "june_dry" / "june_dry.csv"
PIN = REPO / "config" / "june_dry_run.toml"
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
    assert all(re.fullmatch(r"SYN-91[0-9]{2}", r[15]) for r in rows) and len({r[15] for r in rows}) == len(rows)
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
    assert pin["file_name"] == "syn_june_dry_run_r1.csv" and pin["zip_file_name"] == "syn_june_dry_run_r1.zip"
    assert pin["sha256"] == hashlib.sha256(CSV.read_bytes()).hexdigest() and pin["size_bytes"] == CSV.stat().st_size
    assert pin["sha256"] != june["sha256"] and pin["zip_sha256"] != june["zip_sha256"]
    with open(PIN, "rb") as f:
        assert tomllib.load(f)["round"] == 1


def test_J8_the_dry_run_zip_is_stored_with_fixed_fields_and_its_pinned_bytes():
    """The same bytes on every platform, so CI rebuilds the zip the owner uploads (owner decision, 8 November)."""
    files = _script("make_dry_run").build(REPO, 1)
    pin = _pin()
    assert hashlib.sha256(files["zip"]).hexdigest() == pin["zip_sha256"] and len(files["zip"]) == pin["zip_size_bytes"]
    with zipfile.ZipFile(io.BytesIO(files["zip"])) as archive:
        (info,) = archive.infolist()
        assert info.filename == pin["file_name"] and info.compress_type == zipfile.ZIP_STORED
        assert info.create_system == 3 and info.date_time == (2026, 6, 30, 0, 0, 0)
        assert archive.read(info) == CSV.read_bytes()


def test_J8_the_dry_run_script_makes_the_committed_files_byte_for_byte():
    module = _script("make_dry_run")
    for name, data in module.repo_files(module.build(REPO, 1)).items():
        assert (REPO / name).read_bytes() == data, name


def test_J8_unpack_takes_the_dry_run_zip_against_its_pin(tmp_path):
    from voc.job_a import file_counts, pin_for, unpack

    files = _script("make_dry_run").build(REPO, 1)
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
        assert re.fullmatch(r"SYN-91[0-9]{2}", cid) and by_id[cid][5] and digest == content_hash(by_id[cid][5],
                                                                                                    by_id[cid][1])
    manifest = json.loads((REPO / "splits" / "june_dry" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lists"]["june_dry"] == {"count": 8, "round": 1, "sha256": dry_run_list_hash(REPO)}
    assert dry_run_list_hash(REPO) == hashlib.sha256(LIST.read_bytes()).hexdigest()


def test_J1_the_dry_run_list_is_not_the_june_list():
    from voc.frozen import dry_run_list_hash, list_hash

    assert dry_run_list_hash(REPO) != list_hash(REPO)


# Job A's path for a synthetic row (J8, J16)


def _dry_root(tmp_path, kind="synthetic", dry_ids=None):
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
            {"lists": {"june_dry": {"count": len(dry_ids), "round": 1, "sha256": hashlib.sha256(data).hexdigest()}}}),
            encoding="utf-8")
    shutil.copytree(REPO / "config", root / "config")
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
    assert synthetic == [f"SYN-91{n:02d}" for n in range(1, 9)]
    assert not any(cid.startswith("SYN-") for cid in listed_ids(REPO)[:5])


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
    assert sorted(listed) == [f"SYN-91{n:02d}" for n in range(1, 9)]


def test_J11_job_b_s_list_and_answers_refuse_a_real_row():
    from voc.job_b import JobBError, listed_for, mock_answers

    for seam in (listed_for, mock_answers):
        with pytest.raises(JobBError, match="synthetic row only"):
            seam(REPO, _target(kind="real", list_hash="a" * 64))


def test_J11_the_mock_answers_cover_every_dry_run_prompt_with_one_quarantine():
    """Seven accepted labels with their quotes, and one quote the text does not hold, for the quarantine path."""
    from voc import pipeline
    from voc.backends import make_backend
    from voc.job_b import labelled, mock_answers
    from voc.labels import load_labels
    from voc.replay import Answer, Reply

    answers, rows = mock_answers(REPO, _target()), _listed_rows()
    assert len(answers) == 8 and labelled(REPO, rows, answers) == (8, False)
    version = pipeline.load_prompt_version(REPO, "v1")
    backend = make_backend("mock", fixtures={a["prompt"]: Answer(a["text"], None, None, "end_turn") for a in answers})
    outcomes = pipeline.label_complaints(
        [pipeline.Complaint(cid, narrative) for cid, _, narrative in rows], version,
        load_labels(REPO / "config" / "labels.toml"),
        lambda prompt: Reply(backend(prompt, dict(version.settings)).text, "mock", None, None, 0, 0, 1), "mock")
    accepted = {o.decision.complaint_id: o.decision.label for o in outcomes if o.decision.label}
    assert accepted == {cid: product for cid, product, _ in rows if cid != "SYN-9108"}
    assert [o.decision.complaint_id for o in outcomes if o.decision.reason] == ["SYN-9108"]


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
    assert module.main(["--round", "1", str(tmp_path / "zip")]) == 0
    out = capsys.readouterr().out
    assert re.fullmatch(r"syn_june_dry_run_r1\.zip  [0-9]+ bytes  sha256 [0-9a-f]{64}\n", out)
    assert (tmp_path / "zip" / "syn_june_dry_run_r1.zip").read_bytes() == module.build(REPO, 1)["zip"]
    assert module.main(["--round", "1", str(REPO / "inside")]) == 2 and not (REPO / "inside").exists()
