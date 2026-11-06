"""Spec 004, pull request 8: the approval workflow (J10, J16), on synthetic data only. The workflow's YAML is read
as data, and its logic in `src/voc/approval.py` runs against the contract fixtures with fake Databricks, GitHub and
receiver clients. No test opens a network connection or calls a model."""
import copy
import hashlib
import hmac
import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "june_approval.yml"
FIXTURES = REPO / "tests" / "fixtures" / "june_contract"
A, B, D, E = "a" * 64, "b" * 64, "d" * 64, "e" * 64
JOB_A, JOB_B = 800001, 800002


def _approval():
    from voc import approval

    return approval


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _on(workflow):
    # YAML 1.1 reads the key `on` as true.
    return workflow.get("on", workflow.get(True))


# The workflow's YAML (J10, J16 item 3)


def test_J16_the_workflow_has_one_required_string_input_and_names_its_run_by_it():
    workflow = _workflow()
    assert set(_on(workflow)) == {"workflow_dispatch"}
    inputs = _on(workflow)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"job_a_run_id"}
    assert inputs["job_a_run_id"]["required"] is True and inputs["job_a_run_id"]["type"] == "string"
    assert workflow["run-name"] == "June approval for Job A run ${{ inputs.job_a_run_id }}"
    assert _approval().run_name(900001) == "June approval for Job A run 900001"


def test_J10_the_workflow_has_two_jobs_in_their_environments_on_main_only():
    jobs = _workflow()["jobs"]
    assert set(jobs) == {"figures", "run"}
    assert jobs["figures"]["environment"] == "june-figures" and jobs["run"]["environment"] == "june-run"
    assert jobs["run"]["needs"] == "figures"
    for job in jobs.values():
        assert job["if"] == "github.ref == 'refs/heads/main'"
        assert job["runs-on"] == "ubuntu-24.04"


def test_J10_permissions_are_read_only_and_set_per_job_with_one_run_at_a_time():
    workflow = _workflow()
    assert workflow["permissions"] == {}
    assert workflow["concurrency"] == {"group": "june-approval", "cancel-in-progress": False}
    jobs = workflow["jobs"]
    assert jobs["figures"]["permissions"] == {"contents": "read", "actions": "read"}
    assert jobs["run"]["permissions"] == {"contents": "read", "actions": "read"}
    assert jobs["figures"]["timeout-minutes"] <= 15 and jobs["run"]["timeout-minutes"] == 360


def test_J10_every_action_is_pinned_by_its_commit_sha_and_keeps_no_credential():
    for job in _workflow()["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
                if step["uses"].startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] is False


def test_J10_inputs_and_secrets_reach_commands_through_env_only():
    for job in _workflow()["jobs"].values():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), step.get("name")
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("${{ inputs.job_a_run_id }}") == 3  # the run name and the two jobs' env


def test_J10_each_job_runs_the_frozen_logic_with_its_own_secrets():
    jobs = _workflow()["jobs"]
    figures = [s for s in jobs["figures"]["steps"] if "run" in s]
    run = [s for s in jobs["run"]["steps"] if "run" in s]
    assert [s["run"] for s in figures] == ["python3 -I src/voc/approval.py figures"]
    assert [s["run"] for s in run] == ["python3 -I src/voc/approval.py run"]
    databricks = {"VOC_DATABRICKS_HOST", "VOC_DATABRICKS_CLIENT_ID", "VOC_DATABRICKS_CLIENT_SECRET"}
    assert set(figures[0]["env"]) == databricks | {"JOB_A_RUN_ID", "GITHUB_TOKEN"}
    assert set(run[0]["env"]) == databricks | {"JOB_A_RUN_ID", "GITHUB_TOKEN", "VOC_RESULT_SECRET", "VOC_RECEIVER_URL"}
    for env in (figures[0]["env"], run[0]["env"]):
        assert env["JOB_A_RUN_ID"] == "${{ inputs.job_a_run_id }}" and env["GITHUB_TOKEN"] == "${{ github.token }}"
        for name in env:
            if name.startswith("VOC_"):
                assert env[name] == "${{ secrets." + name + " }}"


def test_J1_the_workflow_and_its_logic_are_frozen_with_the_code():
    from voc.frozen import FROZEN_PATHS

    assert ".github/workflows/june_approval.yml" in FROZEN_PATHS and "src" in FROZEN_PATHS


# The run ID (J16, the rules for every message)


@pytest.mark.parametrize("text", ["", "0", "01", "-1", " 1", "1 ", "1.0", "9223372036854775808", "1e3", "１"])
def test_J16_a_run_id_that_is_not_a_whole_number_in_range_is_refused(text):
    with pytest.raises(_approval().ApprovalError):
        _approval().parse_id(text, "job_a_run_id")


def test_J16_a_run_id_in_range_is_read():
    assert _approval().parse_id("9223372036854775807", "x") == 2**63 - 1
    assert _approval().parse_id("900001", "x") == 900001


# Job A's run, before the approval (J16 items 4 and 5)


def _run():
    return _fixture("job_a_run.json")


def test_J16_the_run_fixture_names_success_as_the_spike_saw_it():
    run = _run()
    for item in [run, *run["tasks"]]:
        assert item["state"]["result_state"] == "SUCCESS"
        assert item["status"]["termination_details"]["code"] == "SUCCESS"


def test_J16_job_a_s_good_run_gives_job_a_s_task_run_id():
    assert _approval().checked_run(_run(), 900001, JOB_A) == 900011


def _broken(change):
    run = copy.deepcopy(_run())
    change(run)
    return run


BROKEN = {
    "another job": lambda r: r.update(job_id=800009),
    "another run": lambda r: r.update(run_id=900002),
    "failed": lambda r: r["state"].update(result_state="FAILED"),
    "not terminated well": lambda r: r["status"]["termination_details"].update(code="CANCELED"),
    "no status": lambda r: r.pop("status"),
    "repaired": lambda r: r.update(repair_history=[{"type": "REPAIR", "id": 1}]),
    "no repair history": lambda r: r.pop("repair_history"),
    "a task failed": lambda r: r["tasks"][1]["state"].update(result_state="FAILED"),
    "a task without status": lambda r: r["tasks"][2].pop("status"),
    "a task missing": lambda r: r["tasks"].pop(0),
    "an extra task": lambda r: r["tasks"].append({**r["tasks"][0], "task_key": "extra"}),
    "a repeated task": lambda r: r["tasks"].__setitem__(0, {**r["tasks"][1]}),
}


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_J16_a_run_that_is_not_job_a_s_whole_successful_unrepaired_run_is_refused(name):
    with pytest.raises(_approval().ApprovalError):
        _approval().checked_run(_broken(BROKEN[name]), 900001, JOB_A)


def test_J16_the_tasks_are_checked_by_key_not_by_order():
    run = _run()
    run["tasks"].reverse()
    assert _approval().checked_run(run, 900001, JOB_A) == 900011


def test_J16_the_run_must_be_job_a_s_newest_run():
    runs = _fixture("job_a_runs_list.json")
    _approval().checked_latest(runs, 900001, JOB_A)
    with pytest.raises(_approval().ApprovalError, match="newer"):
        _approval().checked_latest(runs, 899001, JOB_A)
    newer = {"runs": [{"job_id": JOB_A, "run_id": 900005, "start_time": 1793100000000}, *runs["runs"]]}
    with pytest.raises(_approval().ApprovalError, match="newer"):
        _approval().checked_latest(newer, 900001, JOB_A)
    with pytest.raises(_approval().ApprovalError):
        _approval().checked_latest({"runs": []}, 900001, JOB_A)
    with pytest.raises(_approval().ApprovalError):
        _approval().checked_latest({"runs": list(reversed(runs["runs"]))}, 899001, JOB_A)
    with pytest.raises(_approval().ApprovalError):
        _approval().checked_latest({"runs": [{**runs["runs"][0], "job_id": 800009}]}, 900001, JOB_A)


def _output(value=None, truncated=False):
    value = _fixture("job_a_exit.json") if value is None else value
    return {"notebook_output": {"result": json.dumps(value, sort_keys=True, separators=(",", ":")),
                                "truncated": truncated}}


def test_J16_the_exit_value_is_read_with_exactly_the_contract_s_keys():
    assert _approval().exit_value(_output()) == _fixture("job_a_exit.json")


@pytest.mark.parametrize("change", [
    lambda v: v.pop("calls"), lambda v: v.update(extra=1), lambda v: v.update(contract="voc-june-2"),
    lambda v: v.update(kind="resume"), lambda v: v.update(calls="2073"), lambda v: v.update(calls=True),
    lambda v: v.update(expected_cost_usd="0.5"), lambda v: v.update(expected_cost_usd=" 0.49"),
    lambda v: v.update(code_sha256="B" * 64), lambda v: v.update(zip_sha256="e" * 63),
    lambda v: v.update(complaints=-1), lambda v: v.update(contract=" voc-june-1"),
])
def test_J16_an_exit_value_that_breaks_the_contract_is_refused(change):
    value = _fixture("job_a_exit.json")
    change(value)
    with pytest.raises(_approval().ApprovalError):
        _approval().exit_value(_output(value))


@pytest.mark.parametrize("output", [{}, {"notebook_output": {}}, {"notebook_output": {"result": "not json"}},
                                    {"notebook_output": {"result": "[]", "truncated": False}}])
def test_J16_a_missing_or_truncated_exit_value_is_refused(output):
    with pytest.raises(_approval().ApprovalError):
        _approval().exit_value(output)
    with pytest.raises(_approval().ApprovalError):
        _approval().exit_value(_output(truncated=True))


def _target(kind="synthetic", list_hash=A, code_hash=B):
    from voc.job_a import Target

    return Target(kind=kind, entry_kind=kind, list_hash=list_hash, code_hash=code_hash, row=1)


PIN = {"sha256": D, "zip_sha256": E}


def test_J16_the_exit_value_must_match_the_target_row_and_its_pin():
    value = _fixture("job_a_exit.json")
    _approval().checked_exit(value, _target(), PIN)
    for target in (_target(list_hash=B), _target(code_hash=A), _target(kind="real")):
        with pytest.raises(_approval().ApprovalError, match="last row"):
            _approval().checked_exit(value, target, PIN)
    for pin in ({**PIN, "sha256": A}, {**PIN, "zip_sha256": A}):
        with pytest.raises(_approval().ApprovalError, match="pin"):
            _approval().checked_exit(value, _target(), pin)


def test_J16_the_summary_shows_the_run_its_row_its_start_and_the_figures_only():
    from voc.frozen import Entry

    entry = Entry(date="2026-11-07 10:00", kind="synthetic", list_hash=A, code_hash=B, reason="the dry run")
    lines = _approval().summary(900001, _run(), _fixture("job_a_exit.json"), entry)
    assert lines == ["Job A run: 900001", "kind: synthetic", "run log row: 2026-11-07 10:00, synthetic",
                     "started: 2026-10-26 07:16:40 UTC", "complaints: 2073", "calls: 2073",
                     "worst_case_tokens: 38400000", "tokens_left_under_cap: 40000000", "expected_cost_usd: 0.49"]
    assert "the dry run" not in "\n".join(lines)


# The settings (J16 item 10)


def test_J16_the_jobs_ids_come_from_the_frozen_settings_file(tmp_path):
    (tmp_path / "config").mkdir()
    with pytest.raises(_approval().ApprovalError, match="pull request 9"):
        _approval().cloud_settings(tmp_path)
    (tmp_path / "config" / "june_cloud.toml").write_text("job_a_job_id = 800001\njob_b_job_id = 800002\n",
                                                          encoding="utf-8")
    assert _approval().cloud_settings(tmp_path) == {"job_a_job_id": JOB_A, "job_b_job_id": JOB_B}
    for text in ("job_a_job_id = 800001\n", "job_a_job_id = 0\njob_b_job_id = 1\n",
                 'job_a_job_id = "800001"\njob_b_job_id = 800002\n'):
        (tmp_path / "config" / "june_cloud.toml").write_text(text, encoding="utf-8")
        with pytest.raises(_approval().ApprovalError):
            _approval().cloud_settings(tmp_path)


# The result message (J16 item 9)


def test_J16_the_result_message_s_bytes_and_signature_follow_the_contract():
    fixture = _fixture("result_message.json")
    raw = _approval().message_bytes(fixture["body"])
    assert raw == json.dumps(fixture["body"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    secret = "syn-" + "result-secret"
    expected = hmac.new(secret.encode("utf-8"), str(fixture["timestamp"]).encode() + b"." + raw,
                        hashlib.sha256).hexdigest()
    headers = _approval().signed_headers(secret, fixture["timestamp"], raw)
    assert headers == {"X-Voc-Timestamp": str(fixture["timestamp"]), "X-Voc-Signature": f"sha256={expected}",
                       "Content-Type": "application/json"}


def test_J16_the_result_body_has_exactly_the_contract_s_keys():
    body = _approval().result_body(600001, 1, 900001, 900002, "SUCCESS", _fixture("job_b_exit.json"))
    assert body == _fixture("result_message.json")["body"]
    stopped = _approval().result_body(600001, 1, 900001, None, "NOT_STARTED", None)
    assert stopped["job_b_run_id"] is None and stopped["job_b_exit"] is None and set(stopped) == set(body)


@pytest.mark.parametrize("name", ["job_b_exit.json", "job_b_exit_stopped.json"])
def test_J16_job_b_s_exit_value_is_read_with_exactly_its_keys(name):
    value = _fixture(name)
    output = {"notebook_output": {"result": json.dumps(value), "truncated": False}}
    assert _approval().job_b_exit(output) == value
    for change in (lambda v: v.pop("labelled"), lambda v: v.update(extra=1), lambda v: v.update(stopped="no"),
                   lambda v: v.update(stop_reason="other"), lambda v: v.update(entry_kind="later")):
        broken = copy.deepcopy(value)
        change(broken)
        with pytest.raises(_approval().ApprovalError):
            _approval().job_b_exit({"notebook_output": {"result": json.dumps(broken), "truncated": False}})


# The two jobs, end to end, with fakes


class FakeDatabricks:
    def __init__(self, run=None, runs=None, output=None, follow=None, job_b_output=None, active=None):
        self.run, self.runs = run or _run(), runs or _fixture("job_a_runs_list.json")
        self.active = {} if active is None else active
        self.output = output or _output()
        self.follow = list(follow or [{"state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
                                       "tasks": [{"task_key": "job_b", "run_id": 900003}]}])
        self.job_b_output = job_b_output or {"notebook_output": {"result": json.dumps(_fixture("job_b_exit.json")),
                                                                 "truncated": False}}
        self.calls = []

    def get(self, path, params):
        self.calls.append(("GET", path, params))
        if path == "/api/2.2/jobs/runs/get" and params["run_id"] == 900001:
            return copy.deepcopy(self.run)
        if path == "/api/2.2/jobs/runs/list" and params == {"job_id": JOB_A, "limit": 25}:
            return copy.deepcopy(self.runs)
        if path == "/api/2.2/jobs/runs/list" and params == {"job_id": JOB_A, "active_only": "true", "limit": 25}:
            return copy.deepcopy(self.active)
        if path == "/api/2.2/jobs/runs/get-output" and params["run_id"] == 900011:
            return copy.deepcopy(self.output)
        if path == "/api/2.2/jobs/runs/get" and params["run_id"] == 900002:
            return self.follow.pop(0) if len(self.follow) > 1 else self.follow[0]
        if path == "/api/2.2/jobs/runs/get-output" and params["run_id"] == 900003:
            return copy.deepcopy(self.job_b_output)
        raise AssertionError((path, params))

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        assert path == "/api/2.2/jobs/run-now"
        return {"run_id": 900002}


class FakeGitHub:
    def __init__(self, title="June approval for Job A run 900001", attempt=1):
        self.title, self.attempt = title, attempt

    def own_run(self):
        return {"display_title": self.title, "event": "workflow_dispatch", "head_branch": "main",
                "path": ".github/workflows/june_approval.yml", "run_attempt": self.attempt}


class FakeReceiver:
    def __init__(self):
        self.posts = []

    def post(self, raw, headers):
        self.posts.append((raw, headers))
        return 202


def _env(**extra):
    return {"JOB_A_RUN_ID": "900001", "GITHUB_RUN_ID": "600001", "GITHUB_RUN_ATTEMPT": "1",
            "VOC_RESULT_SECRET": "syn-" + "result-secret", **extra}


def _patched(monkeypatch, kind="synthetic"):
    """The target row, its entry and its pin, as a checkout would give them, without a real run log."""
    from voc.frozen import Entry

    approval = _approval()
    entry = Entry(date="2026-11-07 10:00", kind=kind, list_hash=A, code_hash=B, reason="the dry run")
    monkeypatch.setattr(approval, "_target_and_entry", lambda root: (_target(kind), entry))
    monkeypatch.setattr(approval, "_pin", lambda root, k: PIN)
    monkeypatch.setattr(approval, "cloud_settings", lambda root: {"job_a_job_id": JOB_A, "job_b_job_id": JOB_B})
    return approval


def test_J10_the_figures_job_checks_the_run_and_prints_the_summary(monkeypatch, tmp_path):
    approval = _patched(monkeypatch)
    summary = tmp_path / "summary.md"
    lines = approval.figures_job(REPO, _env(GITHUB_STEP_SUMMARY=str(summary)), FakeDatabricks(), FakeGitHub())
    assert lines[0] == "Job A run: 900001" and "expected_cost_usd: 0.49" in lines
    assert all(line in summary.read_text(encoding="utf-8") for line in lines)


def test_J16_the_figures_job_refuses_a_run_name_that_is_not_the_exact_name(monkeypatch):
    approval = _patched(monkeypatch)
    for title in ("June approval for Job A run 9000011", "June approval for Job A run 90000", ""):
        with pytest.raises(approval.ApprovalError, match="name"):
            approval.figures_job(REPO, _env(), FakeDatabricks(), FakeGitHub(title=title))


@pytest.mark.parametrize("name", ["another job", "failed", "repaired", "a task missing"])
def test_J16_the_figures_job_refuses_a_run_that_fails_a_check(monkeypatch, name):
    approval = _patched(monkeypatch)
    with pytest.raises(approval.ApprovalError):
        approval.figures_job(REPO, _env(), FakeDatabricks(run=_broken(BROKEN[name])), FakeGitHub())


def test_J16_the_figures_job_refuses_a_run_that_does_not_match_the_target_row(monkeypatch):
    approval = _patched(monkeypatch, kind="real")
    with pytest.raises(approval.ApprovalError, match="last row"):
        approval.figures_job(REPO, _env(), FakeDatabricks(), FakeGitHub())


def test_J16_the_figures_job_refuses_a_run_that_is_not_the_newest(monkeypatch):
    approval = _patched(monkeypatch)
    runs = {"runs": [{"job_id": JOB_A, "run_id": 900005, "start_time": 1793100000000},
                     *_fixture("job_a_runs_list.json")["runs"]]}
    with pytest.raises(approval.ApprovalError, match="newer"):
        approval.figures_job(REPO, _env(), FakeDatabricks(runs=runs), FakeGitHub())


def test_J16_the_run_job_starts_job_b_with_the_contract_s_body_and_posts_the_signed_result(monkeypatch):
    approval = _patched(monkeypatch)
    databricks, receiver = FakeDatabricks(), FakeReceiver()
    lines = approval.run_job(REPO, _env(), databricks, FakeGitHub(), receiver, sleep=lambda s: None)
    posts = [c for c in databricks.calls if c[0] == "POST"]
    assert posts == [("POST", "/api/2.2/jobs/run-now", _fixture("run_now.json"))]
    [(raw, headers)] = receiver.posts
    assert json.loads(raw) == _fixture("result_message.json")["body"]
    secret = "syn-" + "result-secret"
    expected = hmac.new(secret.encode(), headers["X-Voc-Timestamp"].encode() + b"." + raw, hashlib.sha256).hexdigest()
    assert headers["X-Voc-Signature"] == f"sha256={expected}"
    assert "Job B run: 900002" in lines and "result: SUCCESS" in lines


def test_J16_the_run_job_follows_job_b_until_it_ends(monkeypatch):
    approval = _patched(monkeypatch)
    running = {"state": {"life_cycle_state": "RUNNING"}, "tasks": [{"task_key": "job_b", "run_id": 900003}]}
    ended = {"state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"},
             "tasks": [{"task_key": "job_b", "run_id": 900003}]}
    waits, receiver = [], FakeReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(follow=[running, running, ended]), FakeGitHub(), receiver,
                     sleep=waits.append)
    assert len(waits) == 2 and json.loads(receiver.posts[0][0])["result_state"] == "FAILED"


def test_J16_the_run_job_reports_unknown_when_it_stops_following(monkeypatch):
    approval = _patched(monkeypatch)
    running = {"state": {"life_cycle_state": "RUNNING"}, "tasks": [{"task_key": "job_b", "run_id": 900003}]}
    receiver = FakeReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(follow=[running]), FakeGitHub(), receiver, sleep=lambda s: None,
                     polls=3)
    body = json.loads(receiver.posts[0][0])
    assert body["result_state"] == "UNKNOWN" and body["job_b_run_id"] == 900002 and body["job_b_exit"] is None


def test_J16_a_re_run_never_starts_job_b(monkeypatch):
    """Owner decision, 5 November: only the run's first attempt can start a scoring."""
    approval = _patched(monkeypatch)
    databricks, receiver = FakeDatabricks(), FakeReceiver()
    with pytest.raises(approval.ApprovalError, match="attempt"):
        approval.run_job(REPO, _env(GITHUB_RUN_ATTEMPT="2"), databricks, FakeGitHub(attempt=2), receiver,
                         sleep=lambda s: None)
    assert not [c for c in databricks.calls if c[0] == "POST"]


def test_J16_the_run_job_checks_job_a_s_run_again_and_posts_not_started_on_a_refusal(monkeypatch):
    approval = _patched(monkeypatch)
    databricks, receiver = FakeDatabricks(run=_broken(BROKEN["repaired"])), FakeReceiver()
    with pytest.raises(approval.ApprovalError):
        approval.run_job(REPO, _env(), databricks, FakeGitHub(), receiver, sleep=lambda s: None)
    assert not [c for c in databricks.calls if c[0] == "POST"]
    body = json.loads(receiver.posts[0][0])
    assert body["result_state"] == "NOT_STARTED" and body["job_b_run_id"] is None and body["job_b_exit"] is None


def test_J10_both_jobs_ask_databricks_for_the_jobs_scope_only(monkeypatch):
    import urllib.parse

    approval = _approval()
    sent = []

    def fake(url, data=None, headers=None, method="GET"):
        sent.append((url, data, headers, method))
        return 200, b'{"access_token": "synthetic-token"}'

    monkeypatch.setattr(approval, "_request", fake)
    client = approval.Databricks("synthetic.example.invalid", "synthetic-id", "syn-" + "secret")
    assert client.token() == "synthetic-token"
    url, data, headers, method = sent[0]
    assert url == "https://synthetic.example.invalid/oidc/v1/token" and method == "POST"
    assert urllib.parse.parse_qs(data.decode("ascii")) == {"grant_type": ["client_credentials"], "scope": ["jobs"]}


@pytest.mark.parametrize("host", ["", "https://x.example", "x.example/path", "x.example:443", "x example"])
def test_J16_a_databricks_host_that_is_not_a_bare_name_is_refused(host):
    with pytest.raises(_approval().ApprovalError):
        _approval().Databricks(host, "synthetic-id", "syn-" + "secret")


def test_J5_the_jobs_print_no_field_they_do_not_read(monkeypatch, capsys, tmp_path):
    """A hostile field in Databricks' replies never reaches the log or the step summary."""
    approval = _patched(monkeypatch)
    marker = "SYNMARKER complaint text"
    run = {**_run(), "state": {**_run()["state"], "state_message": marker}, "run_name": marker}
    output = {**_output(), "error": marker, "error_trace": marker, "logs": marker}
    summary = tmp_path / "summary.md"
    lines = approval.figures_job(REPO, _env(GITHUB_STEP_SUMMARY=str(summary)), FakeDatabricks(run=run, output=output),
                                 FakeGitHub())
    out = capsys.readouterr()
    assert marker not in "\n".join(lines) + out.out + out.err + summary.read_text(encoding="utf-8")


def test_J5_a_refusal_s_text_is_fixed_and_the_main_prints_the_type_only_for_other_errors(monkeypatch, capsys):
    approval = _approval()

    def broken(*args):
        raise RuntimeError("SYNMARKER complaint text")

    monkeypatch.setattr(approval, "_figures_from_env", broken)
    assert approval.main(["figures"], env={}) == 1
    assert capsys.readouterr().out == "error: RuntimeError\n"


def test_J16_an_active_run_of_job_a_refuses_the_approval(monkeypatch):
    """Whether the runs list holds active runs by default is not confirmed from Databricks' docs, so the workflow
    also asks for active runs only, and refuses if Job A has any (J16 item 5)."""
    approval = _patched(monkeypatch)
    active = {"runs": [{"job_id": JOB_A, "run_id": 900007, "start_time": 1793100000000}]}
    with pytest.raises(approval.ApprovalError, match="active"):
        approval.figures_job(REPO, _env(), FakeDatabricks(active=active), FakeGitHub())
    databricks = FakeDatabricks()
    approval.figures_job(REPO, _env(), databricks, FakeGitHub())
    assert ("GET", "/api/2.2/jobs/runs/list", {"job_id": JOB_A, "active_only": "true", "limit": 25}) in databricks.calls


@pytest.mark.parametrize("active", [{}, {"runs": []}, {"has_more": False}])
def test_J16_no_active_run_is_read_as_none(active):
    _approval().checked_no_active(active)


@pytest.mark.parametrize("active", [{"runs": [{"run_id": 1}]}, {"runs": "x"}])
def test_J16_any_active_run_or_a_malformed_list_is_refused(active):
    with pytest.raises(_approval().ApprovalError):
        _approval().checked_no_active(active)
