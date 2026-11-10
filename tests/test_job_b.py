"""Spec 004, pull request 6a: the dry-run Job B (J11, J16), on synthetic data and the mock backend only. Its logic in
`src/voc/job_b.py` runs against the contract fixtures with fake Databricks, GitHub and volume clients. No test opens
a network connection or calls a model."""
import copy
import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "june_contract"
JOB = REPO / "cloud" / "job_b.yml"
NOTEBOOK = REPO / "cloud" / "job_b" / "job_b.py"
A, B, C, D, E = "a" * 64, "b" * 64, "c" * 40, "d" * 64, "e" * 64
JOB_A, JOB_B = 800001, 800002
JOB_A_RUN, JOB_B_RUN, GITHUB_RUN = 900001, 900002, 600001
ROWS = [("SYN-2", "Mortgage", "My mortgage servicer lost my payment."),
        ("SYN-1", "Credit card", "The card company charged a fee twice.")]
NOTE = "Nothing here is complaint text."


def _job_b():
    from voc import job_b

    return job_b


def _approval():
    from voc import approval

    return approval


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _values(**change):
    return {"job_a_run_id": str(JOB_A_RUN), "github_run_id": str(GITHUB_RUN), "job_b_run_id": str(JOB_B_RUN),
            **change}


def _listed(rows=ROWS):
    from voc.data import content_hash

    return {cid: content_hash(narrative, product) for cid, product, narrative in rows}


def _approved(rows=ROWS, **change):
    """Job A's exit value for these rows, with the figures Job A's own code gives them."""
    from voc.job_a import figures

    # Changed in the fix round of #98: the exit value names the dry run's list hash, bound to the row.
    return {**_fixture("job_a_exit.json"), "june_list_sha256": _list_hash(rows), **figures(REPO, rows, 0),
            **change}


def _output(value):
    return {"notebook_output": {"result": json.dumps(value, sort_keys=True, separators=(",", ":")),
                                "truncated": False}}


def _own_run(**change):
    run = {"run_id": JOB_B_RUN, "job_id": JOB_B, "state": {"life_cycle_state": "RUNNING"},
           "job_parameters": [{"name": "job_a_run_id", "default": "", "value": str(JOB_A_RUN)},
                              {"name": "github_run_id", "default": "", "value": str(GITHUB_RUN)}],
           # Changed in round 3's pull request: the commit is on the task, as round 2 saw it.
           "tasks": [{"task_key": "job_b", "attempt_number": 0, "git_source": {"git_snapshot": {"used_commit": C}}}]}
    run.update(change)
    return run


class FakeJobs:
    """Databricks' Jobs API as Job B reads it: its own run, and Job A's run, list and exit value."""

    def __init__(self, own=None, job_a_exit=None, run=None, runs=None, active=None):
        self.own = own or _own_run()
        self.job_a_exit = job_a_exit or _approved()
        self.run, self.runs = run or _fixture("job_a_run.json"), runs or _fixture("job_a_runs_list.json")
        self.active = {} if active is None else active
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, params))
        if path == "/api/2.2/jobs/runs/get" and params["run_id"] == JOB_B_RUN:
            return copy.deepcopy(self.own)
        if path == "/api/2.2/jobs/runs/get" and params["run_id"] == JOB_A_RUN:
            return copy.deepcopy(self.run)
        if path == "/api/2.2/jobs/runs/list" and params == {"job_id": JOB_A, "limit": 25}:
            return copy.deepcopy(self.runs)
        if path == "/api/2.2/jobs/runs/list" and params == {"job_id": JOB_A, "active_only": "true", "limit": 25}:
            return copy.deepcopy(self.active)
        if path == "/api/2.2/jobs/runs/get-output" and params["run_id"] == 900011:
            return _output(self.job_a_exit)
        raise AssertionError((path, params))


class FakeGitHub:
    """GitHub's public API: each path answers its replies in turn, then its last one again."""

    def __init__(self, run=None, approvals=None, run_replies=None):
        github_run = {**_fixture("github_run.json"), "head_sha": C, **(run or {})}
        approvals = _fixture("github_approvals.json") if approvals is None else approvals
        self.replies = {f"/{GITHUB_RUN}": run_replies or [(200, json.dumps(github_run).encode())],
                        f"/{GITHUB_RUN}/approvals": [(200, json.dumps(approvals).encode())]}
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        replies = self.replies[path]
        return replies.pop(0) if len(replies) > 1 else replies[0]


class FakeFiles:
    """A volume's files, as the Databricks SDK's `files` client gives them. A second upload of a path is refused."""

    def __init__(self, existing=()):
        self.files = {path: b"" for path in existing}
        self.folders = set()

    def get_metadata(self, path):
        if path not in self.files:
            raise type("NotFound", (Exception,), {})("missing")
        return {}

    def create_directory(self, path):
        self.folders.add(path)

    def upload(self, path, contents, overwrite=None):
        assert overwrite is False
        if path in self.files:
            raise type("AlreadyExists", (Exception,), {})("exists")
        self.files[path] = contents.read()


def _patched(monkeypatch, kind="synthetic", entry_kind=None, rows=ROWS, answers=None):
    """The target row, its entry, its pin, the jobs' IDs, the dry run's list and its mock answers, as pull request
    9a will give them, without a real run log."""
    from voc.frozen import Entry
    from voc.job_a import Target

    approval, job_b = _approval(), _job_b()
    entry_kind = entry_kind or kind
    # Changed in the fix round of #98: the row names the dry run's list hash, and the list comes as its bytes.
    target = Target(kind=kind, entry_kind=entry_kind, list_hash=_list_hash(rows), code_hash=B, row=1)
    entry = Entry(date="2026-11-08 10:00", kind=entry_kind, list_hash=_list_hash(rows), code_hash=B,
                  reason="the dry run")
    monkeypatch.setattr(approval, "_target_and_entry", lambda root: (target, entry))
    monkeypatch.setattr(approval, "_pin", lambda root, k: {"sha256": D, "zip_sha256": E})
    monkeypatch.setattr(approval, "cloud_settings", lambda root: {"job_a_job_id": JOB_A, "job_b_job_id": JOB_B})
    monkeypatch.setattr(job_b, "listed_for", lambda root, t: _list_bytes(rows))
    monkeypatch.setattr(job_b, "mock_answers", lambda root, t: _answers(rows) if answers is None else answers)
    return job_b


def _answers(rows=ROWS):
    """A synthetic answer for every prompt the dry run sends."""
    from voc import pipeline
    from voc.baselines import cut_text
    from voc.labels import load_labels
    from voc.prompt import build_prompt

    version = pipeline.load_prompt_version(REPO, "v1")
    labels = load_labels(REPO / "config" / "labels.toml")
    names, defined = [label.name for label in labels], pipeline.definitions(labels)
    return [{"prompt": build_prompt(version.instructions, names, cut_text(narrative)[0], complaint_id=cid,
                                    definitions=defined).prompt, "text": "{}"} for cid, _, narrative in rows]


def _run(job_b, jobs=None, github=None, files=None, rows=ROWS, values=None, sleep=None):
    jobs, github, files = jobs or FakeJobs(), github or FakeGitHub(), files or FakeFiles()
    waits = []
    value = job_b.run(REPO, values or _values(), jobs, github, job_b.VolumeStore(files), lambda sql: list(rows),
                      sleep=sleep or waits.append)
    return json.loads(value), files, waits


# The job's file (J11)


def test_J11_job_b_is_one_task_one_run_at_a_time_on_main_with_no_trigger():
    job = yaml.safe_load(JOB.read_text(encoding="utf-8"))["resources"]["jobs"]["voc_june_job_b"]
    assert job["name"] == "voc-june-job-b" and job["max_concurrent_runs"] == 1
    assert job["git_source"] == {"git_url": "https://github.com/MannyAdc/voc-demo", "git_provider": "gitHub",
                                 "git_branch": "main"}
    assert "trigger" not in job and "schedule" not in job and "continuous" not in job
    assert [task["task_key"] for task in job["tasks"]] == ["job_b"]
    task = job["tasks"][0]["notebook_task"]
    assert task["notebook_path"] == "cloud/job_b/job_b" and task["source"] == "GIT"
    # Databricks fills the job's own run ID. Callers give only the two run IDs (owner decision, 8 November).
    assert task["base_parameters"] == {"job_b_run_id": "{{job.run_id}}"}


def test_J16_job_b_takes_exactly_run_now_s_two_job_parameters():
    job = yaml.safe_load(JOB.read_text(encoding="utf-8"))["resources"]["jobs"]["voc_june_job_b"]
    assert job["parameters"] == [{"name": "job_a_run_id", "default": ""}, {"name": "github_run_id", "default": ""}]
    assert set(_fixture("run_now.json")["job_parameters"]) == {"job_a_run_id", "github_run_id"}


def test_J1_job_b_s_file_and_notebook_are_frozen_with_the_code():
    from voc.frozen import FROZEN_PATHS

    for path in (JOB, NOTEBOOK, REPO / "src" / "voc" / "job_b.py"):
        name = path.relative_to(REPO).as_posix()
        # Review of #98, nit 10: a whole path, or a folder followed by its slash.
        assert any(name == f or name.startswith(f.rstrip("/") + "/") for f in FROZEN_PATHS), name


# Its parameters (J16 item 1)


@pytest.mark.parametrize("change", [{"job_a_run_id": "0"}, {"github_run_id": "12a"}, {"job_b_run_id": ""},
                                    {"job_a_run_id": str(2**63)}, {"github_run_id": " 1"}, {"job_b_run_id": "-1"}])
def test_J16_a_job_b_parameter_that_is_not_a_whole_number_in_range_is_refused(change):
    with pytest.raises(_job_b().JobBError, match="whole number"):
        _job_b().parameters(_values(**change))


def test_J16_job_b_reads_exactly_its_three_parameters():
    assert _job_b().parameters(_values()) == (JOB_A_RUN, GITHUB_RUN, JOB_B_RUN)
    for values in ({k: v for k, v in _values().items() if k != "github_run_id"}, _values(extra="1")):
        with pytest.raises(_job_b().JobBError, match="exactly"):
            _job_b().parameters(values)


# Synthetic only (J11, owner decision, 6 November)


@pytest.mark.parametrize("kind,entry_kind", [("real", "real"), ("synthetic", "resume"), ("synthetic", "second"),
                                              ("real", "reproduction")])
def test_J11_job_b_refuses_a_real_or_later_row_until_6b(monkeypatch, kind, entry_kind):
    job_b = _patched(monkeypatch, kind=kind, entry_kind=entry_kind)
    jobs = FakeJobs()
    with pytest.raises(job_b.JobBError, match="synthetic first row until pull request 6b"):
        _run(job_b, jobs=jobs)
    assert jobs.calls == []


def test_J11_job_b_refuses_an_id_that_is_not_synthetic(monkeypatch):
    rows = ROWS + [("3141592", "Mortgage", "Not synthetic.")]
    job_b = _patched(monkeypatch, rows=rows)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="not synthetic"):
        # Changed in the fix round of #98: Job A's exit value names these rows' list hash.
        _run(job_b, jobs=FakeJobs(job_a_exit=_approved(rows)), files=files, rows=rows)
    assert files.files == {}


def test_J11_job_b_never_makes_the_api_backend_or_reads_a_key(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-" + "ant-" + "syn" * 10)
    from voc import backends

    made = []
    real = backends.make_backend
    monkeypatch.setattr(backends, "make_backend", lambda name, **kw: made.append(name) or real(name, **kw))
    job_b = _patched(monkeypatch)
    value, _, _ = _run(job_b)
    assert made == ["mock"] and value["stopped"] is False
    for path in (REPO / "src" / "voc" / "job_b.py", NOTEBOOK):
        text = path.read_text(encoding="utf-8")
        for word in ("secrets", "ANTHROPIC_API_KEY", "import anthropic", "LLM_BACKEND"):
            assert word not in text, (path.name, word)


# Its own run (J11, owner decision, 8 November)


@pytest.mark.parametrize("change", [
    {"run_id": 900099}, {"job_id": 800009}, {"state": {"life_cycle_state": "TERMINATED"}},
    {"job_parameters": [{"name": "job_a_run_id", "value": str(JOB_A_RUN)}]},
    {"job_parameters": [{"name": "job_a_run_id", "value": "900005"}, {"name": "github_run_id", "value": "600001"}]},
    {"job_parameters": [{"name": "job_a_run_id", "value": "900001"}, {"name": "github_run_id", "value": "600001"},
                        {"name": "job_b_run_id", "value": "900002"}]},
    # Changed in round 3's pull request: the commit cases name the task, where the commit is.
    {"tasks": [{"task_key": "job_b", "git_source": {"git_snapshot": {"used_commit": "main"}}}]},
    {"tasks": [{"task_key": "job_b", "git_source": {}}]}])
def test_J11_job_b_refuses_its_own_run_unless_running_job_b_with_these_parameters(monkeypatch, change):
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="Job B's own run"):
        _run(job_b, jobs=FakeJobs(own=_own_run(**change)), files=files)
    assert files.files == {}


# The dry run's round 2 (10 November): Databricks keeps the commit on each task of the run, at
# tasks[].git_source.git_snapshot.used_commit, and not on the run itself. The task was also retried once on its own.


def _task(commit=C, attempt=0, key="job_b"):
    return {"task_key": key, "attempt_number": attempt, "run_id": 970000 + attempt,
            "git_source": {"git_branch": "main", "git_provider": "gitHub", "git_snapshot": {"used_commit": commit},
                           "git_url": "https://github.com/MannyAdc/voc-demo"}}


def _live_own_run(tasks):
    # Changed in the green commit: the helper above has no run-level `git_source` any more.
    run = _own_run(tasks=tasks)
    run.pop("git_source", None)
    return run


@pytest.mark.parametrize("tasks", [[_task()], [_task(attempt=0), _task(attempt=1)]])
def test_J11_job_b_takes_its_commit_from_its_task_as_round_2_saw_it(monkeypatch, tasks):
    job_b = _patched(monkeypatch)
    value, _, _ = _run(job_b, jobs=FakeJobs(own=_live_own_run(tasks)))
    assert value["stopped"] is False


@pytest.mark.parametrize("own", [
    _live_own_run([]),
    _live_own_run([_task(key="other")]),
    _live_own_run([_task(commit="main")]),
    _live_own_run([_task(attempt=0), _task(commit="d" * 40, attempt=1)]),
    _live_own_run([{"task_key": "job_b", "attempt_number": 0, "git_source": {}}]),
    # The shape the code first expected, with the commit on the run only, is refused now.
    {**_live_own_run([{"task_key": "job_b", "attempt_number": 0}]), "git_source": {"git_snapshot": {"used_commit": C}}},
])
def test_J11_job_b_refuses_its_own_run_unless_every_attempt_of_its_task_names_one_commit(monkeypatch, own):
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="Job B's own run"):
        _run(job_b, jobs=FakeJobs(own=own), files=files)
    assert files.files == {}


# The approval on GitHub (J11, J16 item 7)


def test_J16_job_b_accepts_the_github_run_and_approvals_fixtures(monkeypatch):
    job_b = _patched(monkeypatch)
    github = FakeGitHub()
    value, _, _ = _run(job_b, github=github)
    assert value["stopped"] is False
    assert github.calls == [f"/{GITHUB_RUN}", f"/{GITHUB_RUN}/approvals"]


@pytest.mark.parametrize("change,words", [
    ({"id": 600002}, "not a dispatch of the approval workflow"),
    ({"path": ".github/workflows/other.yml"}, "not a dispatch of the approval workflow"),
    ({"event": "push"}, "not a dispatch of the approval workflow"),
    ({"head_branch": "feature"}, "not a dispatch of the approval workflow"),
    ({"head_sha": "f" * 40}, "commit Job B runs"),
    ({"display_title": "June approval for Job A run 9000011"}, "exact name"),
    ({"display_title": "June approval for Job A run 90000"}, "exact name"),
    ({"run_attempt": 2}, "first attempt")])
def test_J16_job_b_refuses_each_broken_github_run_field(monkeypatch, change, words):
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match=words):
        _run(job_b, github=FakeGitHub(run=change), files=files)
    assert files.files == {}


@pytest.mark.parametrize("approvals", [
    [],
    [{"state": "approved", "environments": [{"name": "june-figures"}], "user": {"login": "MannyAdc"}}],
    [{"state": "approved", "environments": [{"name": "june-run"}], "user": {"login": "someone-else"}}],
    [{"state": "rejected", "environments": [{"name": "june-run"}], "user": {"login": "MannyAdc"}}],
    {"not": "a list"}])
def test_J16_job_b_refuses_without_an_owner_approval_for_june_run(monkeypatch, approvals):
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="approval"):
        _run(job_b, github=FakeGitHub(approvals=approvals), files=files)
    assert files.files == {}  # review of #98, minor 3


def test_J16_job_b_refuses_any_rejection_of_june_run_even_beside_an_approval(monkeypatch):
    """Owner decision, 8 November."""
    approved = _fixture("github_approvals.json")[0]
    rejected = {**approved, "state": "rejected", "user": {"login": "someone-else"}}
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="rejected"):
        _run(job_b, github=FakeGitHub(approvals=[approved, rejected]), files=files)
    assert files.files == {}  # review of #98, minor 3


def test_J11_github_is_read_with_no_token_and_no_redirect(monkeypatch):
    approval, job_b = _approval(), _job_b()
    sent = []

    def fake(url, data=None, headers=None, method="GET"):
        sent.append((url, dict(headers or {}), method))
        return 200, b"{}"

    monkeypatch.setattr(approval, "_request", fake)
    assert job_b.PublicGitHub().get("/600001") == (200, b"{}")
    url, headers, method = sent[0]
    assert url == "https://api.github.com/repos/MannyAdc/voc-demo/actions/runs/600001" and method == "GET"
    assert not any(name.lower() == "authorization" for name in headers)
    assert any(isinstance(h, approval.NoRedirect) for h in approval._OPENER.handlers)


@pytest.mark.parametrize("status", [0, 403, 429, 500, 503])
def test_J11_github_is_retried_three_times_then_refused(monkeypatch, status):
    job_b = _patched(monkeypatch)
    github = FakeGitHub(run_replies=[(status, b"")])
    waits, files = [], FakeFiles()
    with pytest.raises(job_b.JobBError, match=f"did not answer after 3 tries: HTTP {status}"):
        _run(job_b, github=github, sleep=waits.append, files=files)
    assert github.calls == [f"/{GITHUB_RUN}"] * 3 and waits == [20, 60]
    assert files.files == {}  # fix-round review of #98, minor 1


def test_J11_a_github_retry_that_succeeds_goes_on(monkeypatch):
    job_b = _patched(monkeypatch)
    good = (200, json.dumps({**_fixture("github_run.json"), "head_sha": C}).encode())
    value, _, waits = _run(job_b, github=FakeGitHub(run_replies=[(503, b""), good]))
    assert value["stopped"] is False and waits == [20]


def test_J11_a_github_refusal_that_is_not_retried_is_refused_at_once(monkeypatch):
    job_b = _patched(monkeypatch)
    github, files = FakeGitHub(run_replies=[(404, b"")]), FakeFiles()
    with pytest.raises(job_b.JobBError, match="HTTP 404"):
        _run(job_b, github=github, files=files)
    assert github.calls == [f"/{GITHUB_RUN}"] and files.files == {}  # fix-round review of #98, minor 1


# Job A's run, checked again (J11, J16 item 5)


@pytest.mark.parametrize("jobs,words", [
    (lambda: FakeJobs(run={**_fixture("job_a_run.json"), "job_id": 800009}), "not this run of Job A"),
    (lambda: FakeJobs(run={**_fixture("job_a_run.json"), "state": {"result_state": "FAILED"}}),
     "did not finish successfully"),
    # Changed after the dry run's round 1: one ORIGINAL item is a never-repaired run, so a repair is a REPAIR item.
    (lambda: FakeJobs(run={**_fixture("job_a_run.json"),
                           "repair_history": [{"type": "ORIGINAL"}, {"type": "REPAIR"}]}),
     "repaired"),
    (lambda: FakeJobs(runs={"runs": [{"job_id": JOB_A, "run_id": 900005, "start_time": 1793000000000}] +
                            _fixture("job_a_runs_list.json")["runs"]}), "newer run"),
    (lambda: FakeJobs(active={"runs": [{"job_id": JOB_A, "run_id": 900005}]}), "active runs"),
    (lambda: FakeJobs(job_a_exit=_approved(june_list_sha256=B)), "last row"),
    (lambda: FakeJobs(job_a_exit=_approved(source_sha256=A)), "pin")])
def test_J16_job_b_refuses_each_re_check_of_job_a_for_its_own_reason(monkeypatch, jobs, words):
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    # Review of #98, nit 11: each case is refused for its own reason.
    with pytest.raises(job_b.JobBError, match=words):
        _run(job_b, jobs=jobs(), files=files)
    assert files.files == {}


# The sample and the figures (J11)


def test_J11_job_b_refuses_rows_that_are_not_exactly_the_listed_sample(monkeypatch):
    job_b = _patched(monkeypatch)
    for rows, words in ((ROWS[:1], "missing"), (ROWS + [("SYN-3", "Mortgage", "x")], "not in the dry run's list"),
                        ([(ROWS[0][0], ROWS[0][1], "changed text"), ROWS[1]], "content hash"),
                        (ROWS + ROWS[:1], "repeat")):
        files = FakeFiles()
        with pytest.raises(job_b.JobBError, match=words):
            _run(job_b, rows=rows, files=files)
        assert files.files == {}  # review of #98, minor 3


@pytest.mark.parametrize("change", [{"complaints": 3}, {"calls": 1}, {"worst_case_tokens": 10},
                                    {"expected_cost_usd": "0.00"}])
def test_J11_job_b_refuses_figures_other_than_the_approved_ones(monkeypatch, change):
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="figures"):
        _run(job_b, jobs=FakeJobs(job_a_exit=_approved(**change)), files=files)
    assert files.files == {}  # review of #98, minor 3


def test_J11_figures_at_or_under_the_approved_ones_pass(monkeypatch):
    job_b = _patched(monkeypatch)
    value, _, _ = _run(job_b, jobs=FakeJobs(job_a_exit=_approved(worst_case_tokens=10**9, expected_cost_usd="9.99")))
    assert value["stopped"] is False


# The used markers (J11, J16 item 7)


def _marker_paths(job_b):
    used = job_b.USED_FOLDER
    return f"{used}/github/{GITHUB_RUN}.json", f"{used}/job_a/{JOB_A_RUN}-row1.json"


def test_J16_job_b_marks_the_github_run_and_the_job_a_run_for_its_row_as_used(monkeypatch):
    job_b = _patched(monkeypatch)
    _, files, _ = _run(job_b)
    github, pair = _marker_paths(job_b)
    assert job_b.USED_FOLDER == "/Volumes/workspace/default/voc_raw/job_b_used"
    assert json.loads(files.files[github]) == {"github_run_id": GITHUB_RUN, "job_a_run_id": JOB_A_RUN,
                                               "job_b_run_id": JOB_B_RUN, "row": 1}
    assert json.loads(files.files[pair]) == {"code_sha256": B, "github_run_id": GITHUB_RUN,
                                             "job_a_run_id": JOB_A_RUN, "job_b_run_id": JOB_B_RUN,
                                             "june_list_sha256": _list_hash(), "row": 1}  # fix round of #98


@pytest.mark.parametrize("used", [0, 1])
def test_J16_a_used_github_run_or_job_a_run_is_refused_before_anything_is_written(monkeypatch, used):
    job_b = _patched(monkeypatch)
    existing = _marker_paths(job_b)[used]
    files = FakeFiles(existing=[existing])
    with pytest.raises(job_b.JobBError, match="already"):
        _run(job_b, files=files)
    assert set(files.files) == {existing}


def test_J11_a_marker_made_by_another_run_in_between_is_refused(monkeypatch):
    """The upload never overwrites, so a marker that appears after the look is refused too."""
    job_b = _patched(monkeypatch)
    _, pair = _marker_paths(job_b)
    files = FakeFiles()
    upload = files.upload

    def racing(path, contents, overwrite=None):
        if path.endswith(".json") and "/github/" in path:
            files.files[pair] = b"{}"
        return upload(path, contents, overwrite=overwrite)

    files.upload = racing
    with pytest.raises(job_b.JobBError, match="already"):
        _run(job_b, files=files)


def test_J11_markers_are_written_only_after_every_check(monkeypatch):
    job_b = _patched(monkeypatch)
    order = []
    files = FakeFiles()
    upload = files.upload
    files.upload = lambda path, contents, overwrite=None: order.append(path) or upload(path, contents, overwrite)
    jobs = FakeJobs()
    get = jobs.get
    jobs.get = lambda path, params: order.append(path) or get(path, params)
    _run(job_b, jobs=jobs, files=files)
    first_marker = next(i for i, item in enumerate(order) if item.startswith(job_b.USED_FOLDER))
    assert all(not item.startswith("/Volumes") for item in order[:first_marker])
    assert all(item.startswith("/Volumes") for item in order[first_marker:])


# The labelling, the results folder and the exit value (J11, J16 item 8)


def test_J16_job_b_s_exit_value_has_the_contract_s_keys_and_names_its_results_folder(monkeypatch):
    job_b = _patched(monkeypatch)
    value, files, _ = _run(job_b)
    expected = {**_fixture("job_b_exit.json"), "complaints": 2, "labelled": 2,
                "results_folder": f"june-{JOB_B_RUN}"}
    assert value == expected


def test_J11_the_results_folder_holds_a_dry_run_note_until_6b(monkeypatch):
    """Owner decision, 8 November: an empty folder may not persist on the object store, so a note makes it exist."""
    job_b = _patched(monkeypatch)
    _, files, _ = _run(job_b)
    folder = f"/Volumes/workspace/voc_results/voc_results/june-{JOB_B_RUN}"
    note = files.files[f"{folder}/DRY_RUN.txt"].decode("utf-8")
    assert [p for p in files.files if p.startswith("/Volumes/workspace/voc_results/voc_results")] == [
        f"{folder}/DRY_RUN.txt"]
    assert "synthetic dry run" in note and "pull request 6b" in note
    assert all(cid not in note for cid, _, _ in ROWS)


THREE = ROWS + [("SYN-3", "Mortgage", "The escrow account was wrong.")]


def test_J16_a_stopped_run_names_no_folder_and_gives_its_reason(monkeypatch):
    """With no mock answer, three complaints in a row fail, and the labelling stops (B4's rule)."""
    job_b = _patched(monkeypatch, rows=THREE, answers=[])
    value, files, _ = _run(job_b, jobs=FakeJobs(job_a_exit=_approved(THREE)), rows=THREE)
    assert value == {**_fixture("job_b_exit_stopped.json"), "complaints": 3, "labelled": 3, "stop_reason": "error"}
    assert not any(p.startswith("/Volumes/workspace/voc_results/voc_results") for p in files.files)
    assert len([p for p in files.files if p.startswith(job_b.USED_FOLDER)]) == 2


def test_J16_job_b_s_exit_values_pass_the_workflow_s_and_receiver_s_checks(monkeypatch):
    approval = _approval()
    for answers in (None, []):
        job_b = _patched(monkeypatch, rows=THREE, answers=answers)
        value, _, _ = _run(job_b, jobs=FakeJobs(job_a_exit=_approved(THREE)), rows=THREE)
        output = {"notebook_output": {"result": json.dumps(value), "truncated": False}}
        assert approval.job_b_exit(output) == value
        assert approval.exit_for_receiver(value, JOB_B_RUN) == value
        # Review of #98, minor 4: the receiver's own code takes it too.
        import receiver_core

        assert receiver_core._job_b_exit(value, JOB_B_RUN) == value


def test_J16_the_exit_value_is_compact_json_with_sorted_keys(monkeypatch):
    job_b = _patched(monkeypatch)
    raw = job_b.run(REPO, _values(), FakeJobs(), FakeGitHub(), job_b.VolumeStore(FakeFiles()), lambda sql: list(ROWS),
                    sleep=lambda s: None)
    assert raw == json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"))


# J5: nothing printed, and refusals hold fixed text


def test_J5_job_b_prints_nothing_and_its_refusals_hold_no_row_text(monkeypatch, capsys):
    marker = "SYNMARKER complaint text"
    rows = [("SYN-1", "Mortgage", marker), ("SYN-2", "Mortgage", marker + " again")]
    job_b = _patched(monkeypatch, rows=rows)
    jobs = FakeJobs(job_a_exit=_approved(rows))  # changed in the fix round of #98: the list hash of these rows
    _run(job_b, jobs=jobs, rows=rows)
    bad = [(rows[0][0], rows[0][1], marker + " changed"), rows[1]]
    with pytest.raises(job_b.JobBError) as refused:
        _run(job_b, jobs=FakeJobs(job_a_exit=_approved(rows)), rows=bad)
    assert marker not in str(refused.value) and refused.value.__context__ is None
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_J5_a_databricks_or_volume_failure_is_refused_with_its_type_only():
    job_b = _job_b()

    class Broken:
        def do(self, method, path, query=None):
            raise RuntimeError("SYNMARKER a message that could hold anything")

    with pytest.raises(job_b.JobBError) as refused:
        job_b.WorkspaceJobs(Broken()).get("/api/2.2/jobs/runs/get", {"run_id": 1})
    assert "SYNMARKER" not in str(refused.value) and "RuntimeError" in str(refused.value)
    assert refused.value.__context__ is None

    class BrokenFiles(FakeFiles):
        def get_metadata(self, path):
            raise RuntimeError("SYNMARKER")

    with pytest.raises(job_b.JobBError) as refused:
        job_b.VolumeStore(BrokenFiles()).exists("/Volumes/workspace/default/voc_raw/job_b_used/x.json")
    assert "SYNMARKER" not in str(refused.value)


def test_J11_the_notebook_runs_job_b_s_logic_and_names_no_secret():
    text = NOTEBOOK.read_text(encoding="utf-8")
    assert text.startswith("# Databricks notebook source\n")
    assert "from voc.job_b import" in text and "run(" in text and "dbutils.notebook.exit(" in text
    for name in ("job_a_run_id", "github_run_id", "job_b_run_id"):
        assert f'dbutils.widgets.get("{name}")' in text
    assert "WorkspaceClient()" in text and "print(" not in text
    assert not re.search(r"dbutils\.secrets|\bsecrets\b", text)


# The review of #98 (owner decision: fix every finding, with one fresh review of the fix round)


def _list_hash(rows=ROWS):
    import hashlib

    return hashlib.sha256(_list_bytes(rows)).hexdigest()


def _list_bytes(rows=ROWS):
    return ("complaint_id,content_hash\n" + "".join(f"{cid},{h}\n" for cid, h in _listed(rows).items())).encode()


def _patched_list(monkeypatch, data, rows=ROWS):
    """The dry run's list as pull request 9a will give it: the file's bytes, whose hash is the row's list hash."""
    import hashlib

    from voc.frozen import Entry
    from voc.job_a import Target

    approval, job_b = _approval(), _patched(monkeypatch, rows=rows)
    digest = hashlib.sha256(data).hexdigest()
    target = Target(kind="synthetic", entry_kind="synthetic", list_hash=digest, code_hash=B, row=1)
    entry = Entry(date="2026-11-08 10:00", kind="synthetic", list_hash=digest, code_hash=B, reason="the dry run")
    monkeypatch.setattr(approval, "_target_and_entry", lambda root: (target, entry))
    monkeypatch.setattr(job_b, "listed_for", lambda root, t: data)
    return job_b, FakeJobs(job_a_exit=_approved(rows, june_list_sha256=digest))


def test_J11_the_dry_run_s_list_is_read_from_its_bytes_and_job_b_runs_on_it(monkeypatch):
    job_b, jobs = _patched_list(monkeypatch, _list_bytes())
    value, _, _ = _run(job_b, jobs=jobs)
    assert value["stopped"] is False and value["complaints"] == 2


def test_J11_job_b_checks_the_list_s_ids_before_it_reads_the_june_table(monkeypatch):
    """Minor 1: a real ID in the list is refused before any SQL runs."""
    rows = ROWS + [("3141592", "Mortgage", "Not synthetic.")]
    job_b, jobs = _patched_list(monkeypatch, _list_bytes(rows), rows=rows)
    asked, files = [], FakeFiles()
    with pytest.raises(job_b.JobBError, match="not synthetic"):
        job_b.run(REPO, _values(), jobs, FakeGitHub(), job_b.VolumeStore(files), lambda sql: asked.append(sql) or [],
                  sleep=lambda s: None)
    assert asked == [] and files.files == {}


def test_J11_the_dry_run_s_list_must_be_the_run_log_row_s_list(monkeypatch):
    """Minor 2: the list's bytes must hash to the row's list hash, so 9a's list is bound to its row."""
    job_b, jobs = _patched_list(monkeypatch, _list_bytes())
    monkeypatch.setattr(job_b, "listed_for", lambda root, t: _list_bytes(ROWS[:1]))
    asked, files = [], FakeFiles()
    with pytest.raises(job_b.JobBError, match="list hash"):
        job_b.run(REPO, _values(), jobs, FakeGitHub(), job_b.VolumeStore(files),
                  lambda sql: asked.append(sql) or [], sleep=lambda s: None)
    assert asked == [] and files.files == {}  # fix-round review of #98, minor 1


@pytest.mark.parametrize("data", [b"complaint_id\nSYN-1\n", b"", "complaint_id,content_hash\n".encode() + b"\xff\n",
                                  b"complaint_id,content_hash\nSYN-1,abc\n",
                                  # Fix-round review of #98, nit 2: a header only, and an ID twice.
                                  b"complaint_id,content_hash\n",
                                  ("complaint_id,content_hash\n" + f"SYN-1,{'a' * 64}\n" * 2).encode()])
def test_J11_a_dry_run_list_that_is_not_ids_and_hashes_is_refused(monkeypatch, data):
    job_b, jobs = _patched_list(monkeypatch, data)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="dry run's list"):
        _run(job_b, jobs=jobs, files=files)
    assert files.files == {}  # fix-round review of #98, minor 1


def test_J11_every_marker_comes_after_every_outside_call(monkeypatch):
    """Minor 3: the Jobs API, GitHub and the June table are all read before the first marker is written."""
    job_b = _patched(monkeypatch)
    order = []
    jobs, github, files = FakeJobs(), FakeGitHub(), FakeFiles()
    get_job, get_github, upload = jobs.get, github.get, files.upload
    jobs.get = lambda path, params: order.append("jobs") or get_job(path, params)
    github.get = lambda path: order.append("github") or get_github(path)
    files.upload = lambda path, contents, overwrite=None: order.append("upload") or upload(path, contents, overwrite)
    job_b.run(REPO, _values(), jobs, github, job_b.VolumeStore(files), lambda sql: order.append("sql") or list(ROWS),
              sleep=lambda s: None)
    first = order.index("upload")
    assert {"jobs", "github", "sql"} <= set(order[:first]) and set(order[first:]) == {"upload"}


def test_J11_any_kind_of_not_found_error_means_the_marker_is_missing():
    """Minor 5: the SDK may raise a subclass of NotFound for a missing file."""
    job_b = _job_b()
    not_found = type("NotFound", (Exception,), {})
    missing = type("ResourceDoesNotExist", (not_found,), {})

    class Files(FakeFiles):
        def get_metadata(self, path):
            raise missing("gone")

    assert job_b.VolumeStore(Files()).exists("/Volumes/workspace/default/x/y.json") is False


def test_J11_a_job_parameter_item_with_no_name_is_refused(monkeypatch):
    """Nit 6."""
    job_b = _patched(monkeypatch)
    own = _own_run(job_parameters=[{"value": str(JOB_A_RUN)}, {"name": "github_run_id", "value": str(GITHUB_RUN)}])
    with pytest.raises(job_b.JobBError, match="Job B's own run"):
        _run(job_b, jobs=FakeJobs(own=own))


def test_J16_the_contract_defines_labelled():
    """Nit 7."""
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    item = next(line for line in spec.splitlines() if "**8. Job B's exit value**" in line)
    assert "`labelled` is the count of complaints decided" in item


def test_J11_job_b_s_file_names_no_run_as_so_it_runs_as_its_owner():
    """Nit 9."""
    text = JOB.read_text(encoding="utf-8")
    assert "run_as" not in text and "service_principal" not in text


# The fix-round review of #98 (owner's stopping rule: nothing serious, so Claude fixes the minors and nits)


def test_J11_a_june_table_row_that_is_not_synthetic_is_refused_for_a_synthetic_list(monkeypatch):
    """Nit 3: the June table's answer is checked too, not only the list."""
    job_b = _patched(monkeypatch)
    files = FakeFiles()
    with pytest.raises(job_b.JobBError, match="the sample holds an ID that is not synthetic"):
        _run(job_b, rows=ROWS + [("3141592", "Mortgage", "Not synthetic.")], files=files)
    assert files.files == {}


def test_J11_the_rows_check_refuses_a_list_that_is_not_synthetic():
    """Nit 3: `checked_rows` keeps its own check of the list's IDs, as a second line behind `checked_list`."""
    listed = {"3141592": "a" * 64}
    with pytest.raises(_job_b().JobBError, match="list holds an ID that is not synthetic"):
        _job_b().checked_rows(listed, [("3141592", "Mortgage", "x")])


def test_J16_labelled_counts_every_complaint_with_a_decision():
    """Nit 6: a complaint not run for the budget has a decision too."""
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    item = next(line for line in spec.splitlines() if "**8. Job B's exit value**" in line)
    assert "not run for the budget" in item


# Pull request 6b, part 1: Job B's packages and its time limit (owner decisions, 10 November). Databricks' serverless
# Python is 3.12 with older scikit-learn, numpy and scipy, and no anthropic (the probe of 10 November), so Job B
# installs the laptop's locked versions, checked by their hashes, before it imports any code of the repo.

REQUIREMENTS = REPO / "cloud" / "job_b" / "requirements.txt"


def _locked():
    import tomllib

    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    return {p["name"]: p for p in lock["package"]}


def _required():
    pins = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if line and not line[0].isspace() and not line.startswith("#"):
            name, _, rest = line.partition("==")
            pins[name.strip()] = rest.split()[0].rstrip("\\").strip()
    return pins


def test_J11_job_b_stops_after_three_hours():
    """The laptop labelled 1,909 complaints in 3,847 seconds, so June's 2,073 take about 70 minutes, over the old
    hour. The time limit changes no token use (owner decision, 10 November)."""
    job = yaml.safe_load(JOB.read_text(encoding="utf-8"))["resources"]["jobs"]["voc_june_job_b"]
    assert job["timeout_seconds"] == 10800


def test_J11_job_b_s_requirements_pin_every_package_at_its_locked_version_with_hashes():
    locked, pins = _locked(), _required()
    # Changed in the green commit: anthropic 1.13.0 uses httpx2, not httpx (red test's wrong fact).
    assert {"anthropic", "scikit-learn", "numpy", "scipy", "joblib", "threadpoolctl", "httpx2"} <= set(pins)
    for name, version in pins.items():
        assert locked[name]["version"] == version, name
    text = REQUIREMENTS.read_text(encoding="utf-8")
    # Changed in the green commit: uv.lock has no Python 3.12 builds, so the file is compiled for Databricks'
    # platform, with the versions above still held to uv.lock's (the probes of 10 November).
    assert "--python-version 3.12 --python-platform aarch64-manylinux_2_17 --generate-hashes" in text
    for name in pins:
        start = text.index("\n" + name + "==")
        block = text[start:text.find("\n", text.find("--hash", start)) + 1]
        assert "--hash=sha256:" in block, name


def test_J11_the_cloud_group_pins_what_the_project_pins():
    import tomllib

    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    cloud = project["dependency-groups"]["cloud"]
    assert set(cloud) == {"anthropic==1.13.0", "scikit-learn==1.9.1"}
    assert set(cloud) <= set(project["project"]["dependencies"])


def test_J11_the_notebook_installs_the_locked_packages_before_it_imports_the_repo_s_code():
    text = NOTEBOOK.read_text(encoding="utf-8")
    install = text.index("--require-hashes")
    assert "cloud/job_b/requirements.txt" in text or '"requirements.txt"' in text
    assert install < text.index("dbutils.library.restartPython()") < text.index("from voc.job_b import")
    assert "--no-deps" in text and "# COMMAND ----------" in text


def test_J11_job_b_refuses_packages_other_than_the_locked_ones(monkeypatch):
    from voc import job_b

    pins = _required()
    installed = dict(pins)
    monkeypatch.setattr(job_b, "_installed_version", lambda name: installed.get(name))
    job_b.checked_packages(REPO)
    installed["scikit-learn"] = "1.7.2"
    with pytest.raises(job_b.JobBError, match="^Job B's packages are not the locked versions: scikit-learn$"):
        job_b.checked_packages(REPO)
    installed["scikit-learn"] = pins["scikit-learn"]
    installed.pop("anthropic")
    with pytest.raises(job_b.JobBError, match="^Job B's packages are not the locked versions: anthropic$"):
        job_b.checked_packages(REPO)
