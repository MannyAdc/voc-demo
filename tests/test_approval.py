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
        self.started = {"run_id": 900002}

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
            reply = self.follow.pop(0) if len(self.follow) > 1 else self.follow[0]
            if isinstance(reply, BaseException):
                raise reply
            return reply
        if path == "/api/2.2/jobs/runs/get-output" and params["run_id"] == 900003:
            return copy.deepcopy(self.job_b_output)
        raise AssertionError((path, params))

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        assert path == "/api/2.2/jobs/run-now"
        if isinstance(self.started, BaseException):
            raise self.started
        return self.started


class FakeGitHub:
    def __init__(self, title="June approval for Job A run 900001", attempt=1):
        self.title, self.attempt = title, attempt

    def own_run(self):
        return {"display_title": self.title, "event": "workflow_dispatch", "head_branch": "main",
                "path": ".github/workflows/june_approval.yml", "run_attempt": self.attempt}


class FakeReceiver:
    def __init__(self, statuses=None):
        self.posts, self.statuses = [], list(statuses or [])

    def post(self, raw, headers):
        self.posts.append((raw, headers))
        return self.statuses.pop(0) if self.statuses else 202


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



# The review of #95 and the owner's decisions of 6 November


class RealReceiver:
    """Posts into the receiver's own code, receiver/receiver_core.py, with the same secret."""

    def __init__(self):
        import receiver_core

        self.core, self.replies, self.queued = receiver_core, [], []

    def post(self, raw, headers):
        import time

        core = self.core
        settings = core.Settings(basic_user="u", basic_password="syn-" + "p", hmac_secret=("syn-" + "result-secret").encode(),
                                 job_a_job_id=JOB_A)

        class Store:
            def add_key(self, key):
                return True

            def remove_key(self, key):
                pass

        receiver = self

        class Queue:
            def put(self, message):
                receiver.queued.append(message)

        reply = core.handle_http("result", headers, raw, settings, Store(), Queue(), int(time.time()), lambda *a, **k: None)
        self.replies.append(reply.status)
        return reply.status


ENDED_RUN = {"state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
             "tasks": [{"task_key": "job_b", "run_id": 900003}]}


def _ended(result_state=None, life="TERMINATED"):
    state = {"life_cycle_state": life}
    if result_state is not None:
        state["result_state"] = result_state
    return {"state": state, "tasks": [{"task_key": "job_b", "run_id": 900003}]}


def test_J16_the_run_job_s_message_is_accepted_by_the_receiver_s_own_code(monkeypatch):
    approval = _patched(monkeypatch)
    receiver = RealReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(), FakeGitHub(), receiver, sleep=lambda s: None)
    assert receiver.replies == [202]


@pytest.mark.parametrize("raw, mapped", [
    ("SUCCESS", "SUCCESS"), ("FAILED", "FAILED"), ("TIMEDOUT", "TIMEDOUT"), ("CANCELED", "CANCELED"),
    ("SUCCESS_WITH_FAILURES", "FAILED"), ("MAXIMUM_CONCURRENT_RUNS_REACHED", "FAILED"), ("EXCLUDED", "FAILED"),
    ("UPSTREAM_FAILED", "FAILED"), ("DISABLED", "FAILED"), (None, "FAILED"), ("SYNMARKER complaint text", "FAILED"),
])
def test_J16_databricks_end_states_map_onto_the_receiver_s_six(monkeypatch, capsys, raw, mapped):
    """Review of #95, serious 3 and minor 4: the receiver accepts six states. Any other end is a failure, and
    Databricks' own text is never printed."""
    approval = _patched(monkeypatch)
    receiver = RealReceiver()
    lines = approval.run_job(REPO, _env(), FakeDatabricks(follow=[_ended(raw)]), FakeGitHub(), receiver,
                             sleep=lambda s: None)
    assert receiver.replies == [202] and receiver.queued[0]["result_state"] == mapped
    assert f"result: {mapped}" in lines and "SYNMARKER" not in "\n".join(lines) + capsys.readouterr().out


@pytest.mark.parametrize("change", [lambda v: v.update(results_folder="june-1"),
                                    lambda v: v.update(stopped=True),
                                    lambda v: v.update(stop_reason="quota")])
def test_J16_an_exit_value_the_receiver_would_refuse_is_sent_as_none(monkeypatch, change):
    """Review of #95, serious 3: the exit value is checked as the receiver checks it, so the message is never lost."""
    approval = _patched(monkeypatch)
    value = _fixture("job_b_exit.json")
    change(value)
    output = {"notebook_output": {"result": json.dumps(value), "truncated": False}}
    receiver = RealReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(job_b_output=output), FakeGitHub(), receiver, sleep=lambda s: None)
    assert receiver.replies == [202] and receiver.queued[0]["job_b_exit"] is None


def test_J16_the_result_post_is_retried_on_a_server_error_and_a_refusal_fails_the_job(monkeypatch):
    """Review of #95, serious 3: a lost result message is never silent."""
    approval = _patched(monkeypatch)
    receiver = FakeReceiver(statuses=[500, 503, 202])
    lines = approval.run_job(REPO, _env(), FakeDatabricks(), FakeGitHub(), receiver, sleep=lambda s: None)
    assert len(receiver.posts) == 3 and lines[-1] == "result message: HTTP 202"
    for statuses in ([400], [500, 500, 500]):
        with pytest.raises(approval.ApprovalError, match="result message"):
            approval.run_job(REPO, _env(), FakeDatabricks(), FakeGitHub(), FakeReceiver(statuses=statuses),
                             sleep=lambda s: None)


def test_J16_the_follow_keeps_going_through_failed_polls(monkeypatch):
    """Review of #95, serious 1: a failed poll is not the end of the follow."""
    approval = _patched(monkeypatch)
    follow = [approval.ApprovalError("answered HTTP 401"), OSError("network"), _ended("SUCCESS")]
    receiver = FakeReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(follow=follow), FakeGitHub(), receiver, sleep=lambda s: None)
    assert json.loads(receiver.posts[0][0])["result_state"] == "SUCCESS"


def test_J16_the_follow_ends_at_a_time_limit_and_posts_unknown(monkeypatch):
    """Review of #95, minor 3: the limit is 340 minutes of time, not a count of polls."""
    approval = _patched(monkeypatch)
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds + 30  # each poll also takes time

    running = {"state": {"life_cycle_state": "RUNNING"}, "tasks": []}
    receiver = FakeReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(follow=[running]), FakeGitHub(), receiver, sleep=sleep,
                     clock=lambda: now[0])
    assert json.loads(receiver.posts[0][0])["result_state"] == "UNKNOWN"
    assert now[0] <= 340 * 60 + 90


@pytest.mark.parametrize("started", [OSError("lost"), {"run_id": "900002"}, {}])
def test_J16_a_lost_or_odd_start_reply_posts_unknown_not_not_started(monkeypatch, started):
    """Review of #95, minor 1: once run-now is sent, Job B may have started."""
    approval = _patched(monkeypatch)
    databricks, receiver = FakeDatabricks(), FakeReceiver()
    databricks.started = started
    with pytest.raises((approval.ApprovalError, OSError)):
        approval.run_job(REPO, _env(), databricks, FakeGitHub(), receiver, sleep=lambda s: None)
    body = json.loads(receiver.posts[0][0])
    assert body["result_state"] == "UNKNOWN" and body["job_b_run_id"] is None


def test_J16_any_failure_before_the_start_posts_not_started(monkeypatch):
    """Review of #95, minor 2: a network error or a bad secret before the start posts NOT_STARTED too."""
    approval = _patched(monkeypatch)

    class Broken(FakeDatabricks):
        def get(self, path, params):
            raise OSError("network")

    receiver = FakeReceiver()
    with pytest.raises(OSError):
        approval.run_job(REPO, _env(), Broken(), FakeGitHub(), receiver, sleep=lambda s: None)
    assert json.loads(receiver.posts[0][0])["result_state"] == "NOT_STARTED"
    receiver = FakeReceiver()
    monkeypatch.setattr(approval, "Receiver", lambda url: receiver)
    env = {**_env(), "VOC_DATABRICKS_HOST": "https://not-bare", "VOC_DATABRICKS_CLIENT_ID": "x",
           "VOC_DATABRICKS_CLIENT_SECRET": "y", "GITHUB_REPOSITORY": "MannyAdc/voc-demo", "GITHUB_TOKEN": "t",
           "VOC_RECEIVER_URL": "https://receiver.example"}
    with pytest.raises(approval.ApprovalError):
        approval._run_from_env(env)
    assert json.loads(receiver.posts[0][0])["result_state"] == "NOT_STARTED"


def test_J16_job_a_s_run_is_read_with_its_repair_history(monkeypatch):
    """Review of #95, serious 2: Databricks fills `repair_history` only when asked (unconfirmed)."""
    approval = _patched(monkeypatch)
    databricks = FakeDatabricks()
    approval.figures_job(REPO, _env(), databricks, FakeGitHub())
    assert ("GET", "/api/2.2/jobs/runs/get", {"run_id": 900001, "include_history": "true"}) in databricks.calls


def test_J13_the_token_is_renewed_before_it_expires_and_after_a_401(monkeypatch):
    """Review of #95, serious 1: the robot's token lasts about an hour, and Job B can run longer."""
    approval = _approval()
    now = [0.0]
    tokens, gets = [], []

    def fake(url, data=None, headers=None, method="GET"):
        if url.endswith("/oidc/v1/token"):
            tokens.append(now[0])
            return 200, json.dumps({"access_token": f"t{len(tokens)}", "expires_in": 3600}).encode()
        gets.append(headers["Authorization"])
        if len(gets) == 3:
            return 401, b""
        return 200, b"{}"

    monkeypatch.setattr(approval, "_request", fake)
    client = approval.Databricks("synthetic.example.invalid", "synthetic-id", "syn-" + "secret", clock=lambda: now[0])
    client.get("/api/2.2/jobs/runs/get", {"run_id": 1})
    now[0] = 3400.0
    client.get("/api/2.2/jobs/runs/get", {"run_id": 1})
    assert len(tokens) == 2
    client.get("/api/2.2/jobs/runs/get", {"run_id": 1})
    assert len(tokens) == 3 and gets[-1] == "Bearer t3"


def test_J13_no_request_follows_a_redirect():
    """Review of #95, minor 5: a redirect would carry the bearer token to another host."""
    import urllib.request

    approval = _approval()
    request = urllib.request.Request("https://synthetic.example.invalid/x", headers={"Authorization": "Bearer t"})
    assert approval.NoRedirect().redirect_request(request, None, 302, "Found", {}, "https://other.example/") is None
    assert any(isinstance(h, approval.NoRedirect) for h in approval._OPENER.handlers)


def _checkout(tmp_path, kind):
    """A checkout copy whose run log's last row has this kind, for the real target and pin code."""
    import shutil

    from voc.data import content_hash
    from voc.frozen import code_hash

    root = tmp_path / "root"
    (root / "splits" / "june").mkdir(parents=True)
    data = ("complaint_id,content_hash\n" + f"SYN-1,{content_hash('x', 'Mortgage')}\n").encode()
    (root / "splits" / "june" / "june.csv").write_bytes(data)
    (root / "splits" / "june" / "manifest.json").write_text(json.dumps(
        {"lists": {"june": {"count": 1, "sha256": hashlib.sha256(data).hexdigest()}}}), encoding="utf-8")
    shutil.copytree(REPO / "config", root / "config")
    (root / "config" / "june_cloud.toml").write_text("job_a_job_id = 800001\njob_b_job_id = 800002\n",
                                                     encoding="utf-8")
    listed = hashlib.sha256(data).hexdigest()
    (root / "runs").mkdir()
    (root / "runs" / "JUNE_RUNS.md").write_text(
        "| Date | Kind | June list hash | Code hash | Reason |\n|---|---|---|---|---|\n"
        f"| 2026-11-07 10:00 | {kind} | {listed} | {code_hash(root)} | a reason |\n", encoding="utf-8")
    return root, listed, code_hash(root)


def test_J16_the_real_target_code_refuses_a_synthetic_kind_until_pull_request_9(tmp_path, monkeypatch):
    """Review of #95, minor 6: the target and the pin through Job A's own code, not a patch."""
    approval = _approval()
    root, listed, code = _checkout(tmp_path, "real")
    value = {**_fixture("job_a_exit.json"), "kind": "real", "june_list_sha256": listed, "code_sha256": code}
    with pytest.raises(approval.ApprovalError, match="gates"):
        approval.figures_job(root, _env(), FakeDatabricks(output=_output(value)), FakeGitHub())
    # A synthetic row naming the checkout's list is refused by the run log's rule, before any pin. The pull
    # request 9 rule is reached only once pull request 9 gives the dry run its own list (second review of #95).
    root, listed, code = _checkout(tmp_path / "s", "synthetic")
    with pytest.raises(approval.ApprovalError, match="marked synthetic but names the real June list"):
        approval.figures_job(root, _env(), FakeDatabricks(output=_output({**value, "kind": "synthetic"})),
                             FakeGitHub())


def test_J5_the_run_job_prints_no_field_it_does_not_read(monkeypatch, capsys):
    """Review of #95, minor 7: J5's hostile-text test of the run job too."""
    approval = _patched(monkeypatch)
    marker = "SYNMARKER complaint text"
    ended = {"state": {"life_cycle_state": "TERMINATED", "result_state": marker, "state_message": marker},
             "status": {"termination_details": {"message": marker}}, "run_name": marker,
             "tasks": [{"task_key": "job_b", "run_id": 900003}]}
    output = {"error": marker, "error_trace": marker, "logs": marker, "notebook_output": {"result": marker,
                                                                                          "truncated": False}}
    lines = approval.run_job(REPO, _env(), FakeDatabricks(follow=[ended], job_b_output=output), FakeGitHub(),
                             FakeReceiver(), sleep=lambda s: None)
    out = capsys.readouterr()
    assert marker not in "\n".join(lines) + out.out + out.err


def test_J5_the_figures_job_prints_no_termination_message(monkeypatch, capsys):
    approval = _patched(monkeypatch)
    marker = "SYNMARKER complaint text"
    run = _run()
    run["status"]["termination_details"]["message"] = marker
    lines = approval.figures_job(REPO, _env(), FakeDatabricks(run=run), FakeGitHub())
    assert marker not in "\n".join(lines) + capsys.readouterr().out


def test_J16_a_job_b_run_with_no_task_list_still_posts(monkeypatch):
    """Review of #95, nit 2."""
    approval = _patched(monkeypatch)
    receiver = FakeReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(follow=[{"state": {"life_cycle_state": "TERMINATED",
                                                                      "result_state": "SUCCESS"}, "tasks": None}]),
                     FakeGitHub(), receiver, sleep=lambda s: None)
    assert json.loads(receiver.posts[0][0])["job_b_exit"] is None


def test_J16_an_exit_value_that_is_not_json_is_refused():
    """Review of #95, nit 3: the non-JSON branch, reached with `truncated` false."""
    with pytest.raises(_approval().ApprovalError, match="not JSON"):
        _approval().exit_value({"notebook_output": {"result": "not json", "truncated": False}})


@pytest.mark.parametrize("env_attempt, api_attempt", [("1", 2), ("2", 1)])
def test_J16_either_attempt_source_alone_stops_a_re_run(monkeypatch, env_attempt, api_attempt):
    """Review of #95, nit 4."""
    approval = _patched(monkeypatch)
    databricks, receiver = FakeDatabricks(), FakeReceiver()
    with pytest.raises(approval.ApprovalError, match="attempt"):
        approval.run_job(REPO, _env(GITHUB_RUN_ATTEMPT=env_attempt), databricks, FakeGitHub(attempt=api_attempt),
                         receiver, sleep=lambda s: None)
    assert not [c for c in databricks.calls if c[0] == "POST"]
    assert json.loads(receiver.posts[0][0])["result_state"] == "NOT_STARTED"


def test_J5_a_cancelled_run_prints_no_traceback(monkeypatch, capsys):
    """Review of #95, nit 5."""
    approval = _approval()

    def cancelled(env):
        raise KeyboardInterrupt

    monkeypatch.setattr(approval, "_run_from_env", cancelled)
    try:
        code = approval.main(["run"], env={})
    except KeyboardInterrupt:  # caught here, so a main that lets it out fails this test, not the whole session
        code = "escaped"
    assert code == 130
    assert capsys.readouterr().out == "error: KeyboardInterrupt\n"



# The second review of #95, on its fix round (owner decision: the last round, fixed with no further review)


@pytest.mark.parametrize("error", ["IncompleteRead", "BadStatusLine", "LineTooLong", "RemoteDisconnected"])
def test_J16_a_broken_http_reply_is_no_answer_not_a_crash(monkeypatch, error):
    """Minor 1: http.client's own errors are not OSError, so the request treats them as no answer."""
    import http.client

    approval = _approval()
    raised = {"IncompleteRead": http.client.IncompleteRead(b""), "BadStatusLine": http.client.BadStatusLine("x"),
              "LineTooLong": http.client.LineTooLong("header line"),
              "RemoteDisconnected": http.client.RemoteDisconnected("x")}[error]

    def broken(request, timeout=None):
        raise raised

    monkeypatch.setattr(approval._OPENER, "open", broken)
    assert approval._request("https://synthetic.example.invalid/x") == (0, b"")


def test_J16_the_follow_and_the_post_outlast_http_client_errors(monkeypatch):
    import http.client

    approval = _patched(monkeypatch)
    follow = [http.client.IncompleteRead(b""), _ended("SUCCESS")]

    class Flaky(FakeReceiver):
        def post(self, raw, headers):
            self.posts.append((raw, headers))
            if len(self.posts) == 1:
                raise http.client.BadStatusLine("x")
            return 202

    receiver = Flaky()
    approval.run_job(REPO, _env(), FakeDatabricks(follow=follow), FakeGitHub(), receiver, sleep=lambda s: None)
    assert len(receiver.posts) == 2 and json.loads(receiver.posts[1][0])["result_state"] == "SUCCESS"


def test_J16_a_failed_post_names_the_first_error_too(monkeypatch):
    """Minor 2: the reason Job B was not started is not lost when the result post fails as well."""
    approval = _patched(monkeypatch)
    with pytest.raises(approval.ApprovalError) as refused:
        approval.run_job(REPO, _env(GITHUB_RUN_ATTEMPT="2"), FakeDatabricks(), FakeGitHub(attempt=2),
                         FakeReceiver(statuses=[500, 500, 500]), sleep=lambda s: None)
    assert "first attempt" in str(refused.value) and "result message" in str(refused.value)


def test_J16_a_cancel_after_the_start_posts_unknown_once(monkeypatch):
    """Minor 3: a cancel, or GitHub's own time limit, during the follow still tells the receiver."""
    approval = _patched(monkeypatch)
    receiver = FakeReceiver(statuses=[500])
    with pytest.raises(KeyboardInterrupt):
        approval.run_job(REPO, _env(), FakeDatabricks(follow=[KeyboardInterrupt()]), FakeGitHub(), receiver,
                         sleep=lambda s: pytest.fail("no wait while cancelled"))
    assert len(receiver.posts) == 1
    body = json.loads(receiver.posts[0][0])
    assert body["result_state"] == "UNKNOWN" and body["job_b_run_id"] == 900002


def test_J16_a_cancel_before_the_start_posts_not_started(monkeypatch):
    approval = _patched(monkeypatch)

    class Cancelled(FakeGitHub):
        def own_run(self):
            raise KeyboardInterrupt

    receiver = FakeReceiver()
    with pytest.raises(KeyboardInterrupt):
        approval.run_job(REPO, _env(), FakeDatabricks(), Cancelled(), receiver, sleep=lambda s: None)
    assert json.loads(receiver.posts[0][0])["result_state"] == "NOT_STARTED"


def test_J16_the_follow_s_limit_counts_from_the_job_s_start_and_leaves_a_reserve(monkeypatch):
    """Minor 4: the checks before the start take time too, and the end needs time for the post."""
    approval = _patched(monkeypatch)
    now = [0.0]

    class Slow(FakeGitHub):
        def own_run(self):
            now[0] += 20 * 60  # twenty minutes of slow replies before the start
            return super().own_run()

    def sleep(seconds):
        now[0] += seconds + 30

    running = {"state": {"life_cycle_state": "RUNNING"}, "tasks": []}
    receiver = FakeReceiver()
    approval.run_job(REPO, _env(), FakeDatabricks(follow=[running]), Slow(), receiver, sleep=sleep,
                     clock=lambda: now[0])
    assert json.loads(receiver.posts[0][0])["result_state"] == "UNKNOWN"
    assert now[0] <= approval.FOLLOW_SECONDS + 90 and approval.FOLLOW_SECONDS <= 330 * 60


def test_J13_a_short_token_is_renewed_at_half_its_life_and_a_403_renews_once(monkeypatch):
    """Nit 1: a short life is not stretched, and an expired token answered with 403 is renewed too."""
    approval = _approval()
    now = [0.0]
    tokens, gets = [], []

    def fake(url, data=None, headers=None, method="GET"):
        if url.endswith("/oidc/v1/token"):
            tokens.append(now[0])
            return 200, json.dumps({"access_token": f"t{len(tokens)}", "expires_in": 120}).encode()
        gets.append(headers["Authorization"])
        return (403, b"") if len(gets) == 2 else (200, b"{}")

    monkeypatch.setattr(approval, "_request", fake)
    client = approval.Databricks("synthetic.example.invalid", "synthetic-id", "syn-" + "secret", clock=lambda: now[0])
    client.get("/api/2.2/jobs/runs/get", {"run_id": 1})
    now[0] = 61.0
    client.get("/api/2.2/jobs/runs/get", {"run_id": 1})
    assert len(tokens) == 3 and gets[-1] == "Bearer t3"


def test_J13_the_opener_has_no_redirect_handler_but_the_refusing_one():
    """Nit 6: urllib's own redirect handler is replaced, so a 3xx comes back as a status."""
    import urllib.request

    handlers = _approval()._OPENER.handlers
    redirects = [h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert len(redirects) == 1 and isinstance(redirects[0], _approval().NoRedirect)


def test_J13_a_redirect_comes_back_as_its_status(monkeypatch):
    import urllib.error

    approval = _approval()

    def redirected(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 302, "Found", {}, None)

    monkeypatch.setattr(approval._OPENER, "open", redirected)
    assert approval._request("https://synthetic.example.invalid/x") == (302, b"")


def test_J16_the_post_is_tried_again_after_a_429_or_no_answer(monkeypatch):
    approval = _patched(monkeypatch)
    receiver = FakeReceiver(statuses=[429, 202])
    approval.run_job(REPO, _env(), FakeDatabricks(), FakeGitHub(), receiver, sleep=lambda s: None)
    assert len(receiver.posts) == 2

    class NoAnswer(FakeReceiver):
        def post(self, raw, headers):
            self.posts.append((raw, headers))
            if len(self.posts) == 1:
                raise OSError("network")
            return 202

    receiver = NoAnswer()
    approval.run_job(REPO, _env(), FakeDatabricks(), FakeGitHub(), receiver, sleep=lambda s: None)
    assert len(receiver.posts) == 2


def test_J5_main_s_refusal_of_the_run_job_holds_no_field_it_does_not_read(monkeypatch, capsys):
    """Nit 7: J5's hostile-text test through `main`, the path the workflow runs."""
    approval = _patched(monkeypatch)
    marker = "SYNMARKER complaint text"
    run = _broken(BROKEN["failed"])
    run["state"]["state_message"] = marker
    run["status"]["termination_details"]["message"] = marker
    monkeypatch.setattr(approval, "_clients", lambda env: (FakeDatabricks(run=run), FakeGitHub()))
    monkeypatch.setattr(approval, "Receiver", lambda url: FakeReceiver())
    env = {**_env(), "VOC_RECEIVER_URL": "https://receiver.example.invalid"}
    assert approval.main(["run"], env=env) == 1
    out = capsys.readouterr()
    assert out.out.startswith("refused:") and marker not in out.out + out.err


# The dry run's round 1, 9 November: a never-repaired run read with `include_history` holds exactly one repair
# history item, of type ORIGINAL (the owner's notebook, Job A runs 183323422885765 and 799709723207063)

ORIGINAL = {"type": "ORIGINAL", "start_time": 1792999000000, "end_time": 1792999180000,
            "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
            "status": {"termination_details": {"code": "SUCCESS"}}, "task_run_ids": [900009, 900010, 900011],
            "effective_performance_target": "PERFORMANCE_OPTIMIZED"}


def test_J16_a_never_repaired_run_s_one_original_history_item_is_taken():
    run = {**_run(), "repair_history": [copy.deepcopy(ORIGINAL)]}
    assert _approval().checked_run(run, 900001, JOB_A) == 900011


@pytest.mark.parametrize("history", [
    [], [copy.deepcopy(ORIGINAL), copy.deepcopy(ORIGINAL)], [copy.deepcopy(ORIGINAL), {"type": "REPAIR", "id": 2}],
    [{"type": "REPAIR", "id": 1}], [{**ORIGINAL, "type": "ORIGINAL_RUN"}], ["ORIGINAL"], {"type": "ORIGINAL"}])
def test_J16_any_repair_history_but_one_original_item_is_refused(history):
    """An empty list, as `runs/get` gives without `include_history`, no longer counts: the workflow always asks for
    the history, so an empty one means the history was not given."""
    run = {**_run(), "repair_history": history}
    with pytest.raises(_approval().ApprovalError, match="repaired, or its repair history"):
        _approval().checked_run(run, 900001, JOB_A)
