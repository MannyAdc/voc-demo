"""Spec 004, J10 and J16: the approval workflow's logic (`.github/workflows/june_approval.yml`). It runs on GitHub's
runners with Python's standard library only, as `python3 -I src/voc/approval.py figures` or `... run`, so it is
frozen with the code (J1).

- `figures`, the first job, in the environment `june-figures`: it checks its own run's name, then Job A's run
  (J16 items 4 and 5), and prints the figures for the owner's approval, in the log and the step summary.
- `run`, the second job, in the protected environment `june-run`, after the owner approves: it refuses any run
  attempt but the first, checks Job A's run again, starts Job B with run-now (item 6), follows it, reads Job B's
  exit value (item 8), and posts the signed result message to the receiver (item 9). On any failure before run-now
  is sent it posts `NOT_STARTED`, and after it, where the start's reply is lost or odd, `UNKNOWN`. The follow
  renews the robot's token, outlasts failed looks, and ends at 340 minutes with `UNKNOWN`. The message is checked
  as the receiver checks it, tried again on a server error, and anything but 202 fails the job (review of #95).
  After the post, the job fails too unless Job B finished: it ended in `SUCCESS` and its exit value was read,
  checked as the receiver checks it, and says it did not stop. So the Actions tab shows a failed or stopped Job B
  as failed, and the receiver still gets the result first (owner decision, 12 November, after the dry run's
  rounds 4 and 5).

Both ask Databricks for a token with the `jobs` scope only (J10, J13). Nothing here prints `error`, `error_trace`,
`logs`, `state_message` or any other field it does not read (J5, J16). Refusals hold fixed text, IDs and counts.
"""
import base64
import hashlib
import hmac
import http.client
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__":  # run as a file on the runner, so the package is found next to this file
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CONTRACT = "voc-june-1"
ID = re.compile(r"[1-9][0-9]{0,18}")
MAX_ID = 2**63 - 1
HOST = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
TASKS = {"unpack", "dbt", "job_a"}
HASH = re.compile(r"[0-9a-f]{64}")
COST = re.compile(r"[0-9]+\.[0-9]{2}")
WORKFLOW_PATH = ".github/workflows/june_approval.yml"
EXIT_KEYS = {"contract": str, "kind": str, "source_sha256": str, "zip_sha256": str, "june_list_sha256": str,
             "code_sha256": str, "complaints": int, "calls": int, "worst_case_tokens": int,
             "tokens_left_under_cap": int, "expected_cost_usd": str}
FIGURES = ("complaints", "calls", "worst_case_tokens", "tokens_left_under_cap", "expected_cost_usd")
JOB_B_KEYS = {"contract": str, "kind": str, "entry_kind": str, "complaints": int, "labelled": int, "stopped": bool,
              "stop_reason": (str, type(None)), "results_folder": (str, type(None))}
ENTRY_KINDS = ("real", "synthetic", "resume", "reproduction", "second")
STOP_REASONS = (None, "spend_limit", "quota", "ledger_cap", "error")
# Job B's run ends in one of these life cycle states.
ENDED = ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")
# The follow looks at Job B once a minute.
POLL_SECONDS = 60
RUNS_LIST_LIMIT = 25
# The follow's limit in time, counted from the run job's start, which leaves 30 of the job's 360 minutes for the
# end: Job B's exit value and the result post. Then the result post's tries, 3 in all (reviews of #95).
FOLLOW_SECONDS = 330 * 60
POST_TRIES = 3
POST_WAIT_SECONDS = 10
# The robot's token is renewed this many seconds before it expires, or at half its life when that is short.
# Databricks gives `expires_in`, and an hour is taken when it does not.
TOKEN_MARGIN = 300
DEFAULT_TOKEN_LIFE = 3600
# The receiver accepts six result states (receiver/receiver_core.py). These four are Databricks' own, kept as
# they are. Any other end is a failure, and NOT_STARTED and UNKNOWN are the workflow's.
KEPT_STATES = ("SUCCESS", "FAILED", "TIMEDOUT", "CANCELED")
# The run job's last line. After the result is posted, the job fails unless Job B finished: it ended in SUCCESS and
# its exit value was read, checked as the receiver checks it, and says it did not stop (owner decision, 12 November,
# after the dry run's rounds 4 and 5).
FINISHED = "Job B finished"
NOT_FINISHED = "Job B did not finish, so this job fails after the result was sent"


class ApprovalError(ValueError):
    """A refusal with fixed text, IDs and counts only."""


def parse_id(text, name):
    if not isinstance(text, str) or not ID.fullmatch(text) or int(text) > MAX_ID:
        raise ApprovalError(f"{name} must be a whole number from 1 to 2^63 - 1, written in decimal")
    return int(text)


def _whole(value, name, low=1, high=MAX_ID):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ApprovalError(f"{name} must be a whole number from {low} to {high}")
    return value


def run_name(job_a_run_id):
    """J16 item 3: the whole name, compared whole, so run 123 never matches run 1234."""
    return f"June approval for Job A run {job_a_run_id}"


def cloud_settings(root):
    """J16 item 10: the jobs' IDs, frozen with the code."""
    path = Path(root) / "config" / "june_cloud.toml"
    if not path.is_file():
        raise ApprovalError("config/june_cloud.toml is missing: the jobs' IDs are added in pull request 9")
    try:
        with open(path, "rb") as f:
            settings = tomllib.load(f)
    except tomllib.TOMLDecodeError:
        raise ApprovalError("config/june_cloud.toml cannot be read") from None
    return {name: _whole(settings.get(name), name) for name in ("job_a_job_id", "job_b_job_id")}


def _succeeded(item):
    state, status = item.get("state"), item.get("status")
    return (isinstance(state, dict) and state.get("result_state") == "SUCCESS" and isinstance(status, dict)
            and isinstance(status.get("termination_details"), dict)
            and status["termination_details"].get("code") == "SUCCESS")


def _never_repaired(history):
    """A never-repaired run read with `include_history` holds exactly one repair history item, of type ORIGINAL,
    the run itself (the dry run's round 1, 9 November). A repair adds an item. An empty or missing history means
    the history was not given, so it is refused too."""
    return (isinstance(history, list) and len(history) == 1 and isinstance(history[0], dict)
            and history[0].get("type") == "ORIGINAL")


def checked_run(run, run_id, job_a_job_id):
    """J16 item 5: Job A's run, finished successfully, with exactly its three tasks by key, all succeeded, never
    repaired. Returns the `job_a` task's run ID."""
    if run.get("run_id") != run_id or run.get("job_id") != job_a_job_id:
        raise ApprovalError("the run is not this run of Job A")
    if not _succeeded(run):
        raise ApprovalError("Job A's run did not finish successfully")
    if not _never_repaired(run.get("repair_history")):
        raise ApprovalError("Job A's run was repaired, or its repair history is missing")
    tasks = run.get("tasks")
    if (not isinstance(tasks, list) or len(tasks) != len(TASKS)
            or {t.get("task_key") for t in tasks if isinstance(t, dict)} != TASKS):
        raise ApprovalError("Job A's run does not have exactly the tasks unpack, dbt and job_a")
    if not all(_succeeded(t) for t in tasks):
        raise ApprovalError("a task of Job A's run did not succeed")
    return _whole(next(t for t in tasks if t["task_key"] == "job_a").get("run_id"), "job_a's run ID")


def checked_latest(runs_list, run_id, job_a_job_id):
    """J16 item 5: the run is Job A's newest run. The list is checked to be newest first, so a list in another
    order is refused rather than read wrongly."""
    runs = runs_list.get("runs")
    if not isinstance(runs, list) or not runs or not all(isinstance(r, dict) for r in runs):
        raise ApprovalError("Job A's runs list is empty")
    if any(r.get("job_id") != job_a_job_id for r in runs):
        raise ApprovalError("Job A's runs list holds another job's run")
    starts = [r.get("start_time") for r in runs]
    if not all(isinstance(s, int) and not isinstance(s, bool) for s in starts) or starts != sorted(starts,
                                                                                                    reverse=True):
        raise ApprovalError("Job A's runs list is not newest first")
    if runs[0].get("run_id") != run_id:
        raise ApprovalError("a newer run of Job A exists, so this run is not the one to approve")


def checked_no_active(active_list):
    """J16 item 5: Job A has no run still active. Asked for with `active_only`, since whether the plain list holds
    active runs is not confirmed from the docs."""
    runs = active_list.get("runs", [])
    if not isinstance(runs, list):
        raise ApprovalError("Job A's list of active runs cannot be read")
    if runs:
        raise ApprovalError(f"Job A has {len(runs)} active runs, so no run of it can be approved now")


def _notebook_value(output, task):
    notebook = output.get("notebook_output") if isinstance(output, dict) else None
    if (not isinstance(notebook, dict) or notebook.get("truncated") is not False
            or not isinstance(notebook.get("result"), str)):
        raise ApprovalError(f"{task}'s output has no whole exit value")
    try:
        value = json.loads(notebook["result"])
    except ValueError:
        raise ApprovalError(f"{task}'s exit value is not JSON") from None
    if not isinstance(value, dict):
        raise ApprovalError(f"{task}'s exit value is not an object")
    return value


def _typed(value, keys, task):
    if set(value) != set(keys):
        raise ApprovalError(f"{task}'s exit value does not have exactly the contract's keys")
    for key, kind in keys.items():
        if not isinstance(value[key], kind) or (isinstance(value[key], bool) and kind is not bool):
            raise ApprovalError(f"{task}'s exit value has a {key} of the wrong type")
    if value["contract"] != CONTRACT:
        raise ApprovalError(f"{task}'s exit value names another contract")
    if value["kind"] not in ("real", "synthetic"):
        raise ApprovalError(f"{task}'s exit value names another kind")


def exit_value(output):
    """J16 item 4: `notebook_output.result`, not truncated, with exactly the contract's keys and types."""
    value = _notebook_value(output, "job_a")
    _typed(value, EXIT_KEYS, "job_a")
    for key in ("source_sha256", "zip_sha256", "june_list_sha256", "code_sha256"):
        if not HASH.fullmatch(value[key]):
            raise ApprovalError(f"job_a's exit value has a {key} that is not a SHA-256")
    if not COST.fullmatch(value["expected_cost_usd"]) or any(value[k] < 0 for k in FIGURES[:4]):
        raise ApprovalError("job_a's exit value has a figure out of range")
    return value


def job_b_exit(output):
    """J16 item 8: Job B's exit value, with exactly its keys and types."""
    value = _notebook_value(output, "job_b")
    _typed(value, JOB_B_KEYS, "job_b")
    if value["entry_kind"] not in ENTRY_KINDS or value["stop_reason"] not in STOP_REASONS:
        raise ApprovalError("job_b's exit value names another kind of row or stop")
    if value["complaints"] < 0 or value["labelled"] < 0:
        raise ApprovalError("job_b's exit value has a count out of range")
    return value


def result_state(raw):
    """Databricks' result state as the receiver takes it. Any end other than the four kept, such as
    SUCCESS_WITH_FAILURES or a run skipped at its start, is FAILED, and Databricks' own text is never passed on."""
    return raw if raw in KEPT_STATES else "FAILED"


def exit_for_receiver(value, job_b_run_id):
    """Job B's exit value, or None where the receiver would refuse it: a finished run names `june-<Job B run ID>`
    and no stop reason, and a stopped one names no folder and gives its reason (review of #95)."""
    if value["stopped"]:
        kept = value["results_folder"] is None and value["stop_reason"] is not None
    else:
        kept = value["results_folder"] == f"june-{job_b_run_id}" and value["stop_reason"] is None
    return value if kept else None


def checked_exit(value, run_target, pin):
    """J16 item 5: the exit value matches the run's target row and names the pin of its kind."""
    if value["june_list_sha256"] != run_target.list_hash or value["code_sha256"] != run_target.code_hash:
        raise ApprovalError("Job A's exit value does not match the run log's last row")
    if value["kind"] != run_target.kind:
        raise ApprovalError("Job A's exit value names another kind than the run log's last row")
    if value["source_sha256"] != pin["sha256"] or value["zip_sha256"] != pin["zip_sha256"]:
        raise ApprovalError("Job A's exit value does not name the pin of its kind")


def summary(run_id, run, value, entry):
    """What the owner approves: the run, its target row, its start and the figures. Never the row's reason."""
    start = _whole(run.get("start_time"), "the run's start time", low=0)
    started = datetime.fromtimestamp(start / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return [f"Job A run: {run_id}", f"kind: {value['kind']}", f"run log row: {entry.date}, {entry.kind}",
            f"started: {started}", *[f"{key}: {value[key]}" for key in FIGURES]]


def message_bytes(body):
    """J16 item 9: the signed body's exact bytes."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def signed_headers(secret, timestamp, raw):
    stamp = str(_whole(timestamp, "the timestamp", low=0))
    signature = hmac.new(secret.encode("utf-8"), stamp.encode("ascii") + b"." + raw, hashlib.sha256).hexdigest()
    return {"X-Voc-Timestamp": stamp, "X-Voc-Signature": f"sha256={signature}", "Content-Type": "application/json"}


def result_body(github_run_id, github_run_attempt, job_a_run_id, job_b_run_id, result_state, job_b_value):
    return {"contract": CONTRACT, "github_run_id": github_run_id, "github_run_attempt": github_run_attempt,
            "job_a_run_id": job_a_run_id, "job_b_run_id": job_b_run_id, "result_state": result_state,
            "job_b_exit": job_b_value}


# The services. Each call's reply is read only for the fields above, and an error reply is reported by its status.


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is refused, so a bearer token or a signature is never sent on to another host (review of #95)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(NoRedirect)


def _request(url, data=None, headers=None, method="GET"):
    request = urllib.request.Request(url, data=data, headers=dict(headers or {}), method=method)
    try:
        with _OPENER.open(request, timeout=60) as reply:
            return reply.status, reply.read()
    except urllib.error.HTTPError as err:
        return err.code, b""
    except (OSError, http.client.HTTPException):
        # No answer, or a broken one. http.client's own errors, such as IncompleteRead, are not OSError (second
        # review of #95). Status 0 is never a success.
        return 0, b""


def _json_reply(status, body, what):
    if status != 200:
        raise ApprovalError(f"{what} answered HTTP {status}")
    try:
        value = json.loads(body)
    except ValueError:
        raise ApprovalError(f"{what} did not answer JSON") from None
    if not isinstance(value, dict):
        raise ApprovalError(f"{what} did not answer an object")
    return value


class Databricks:
    """The robot's sign-in, with the `jobs` scope only (J13), and the Jobs API. The token is renewed five minutes
    before it expires, or at half its life when that is short, and once more after a 401 or 403, since Job B can
    run longer than a token lasts (reviews of #95)."""

    def __init__(self, host, client_id, client_secret, clock=time.monotonic):
        if not isinstance(host, str) or not HOST.fullmatch(host):
            raise ApprovalError("VOC_DATABRICKS_HOST must be the workspace's bare host name")
        if not client_id or not client_secret:
            raise ApprovalError("the robot's client ID and secret are not set")
        self.host, self.client_id, self.client_secret = host, client_id, client_secret
        self.clock, self._token, self._renew_at = clock, None, 0.0

    def token(self, renew=False):
        if renew or self._token is None or self.clock() >= self._renew_at:
            basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
            data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "jobs"}).encode("ascii")
            asked = self.clock()
            status, body = _request(f"https://{self.host}/oidc/v1/token", data=data, method="POST",
                                    headers={"Authorization": f"Basic {basic}",
                                             "Content-Type": "application/x-www-form-urlencoded"})
            reply = _json_reply(status, body, "Databricks' token request")
            token, life = reply.get("access_token"), reply.get("expires_in")
            if not isinstance(token, str) or not token:
                raise ApprovalError("Databricks gave no token")
            if isinstance(life, bool) or not isinstance(life, int) or life <= 0:
                life = DEFAULT_TOKEN_LIFE
            self._token, self._renew_at = token, asked + max(life - TOKEN_MARGIN, life / 2)
        return self._token

    def _send(self, url, data=None, method="GET", extra=None):
        for renew in (False, True):
            headers = {"Authorization": f"Bearer {self.token(renew)}", **(extra or {})}
            status, body = _request(url, data=data, headers=headers, method=method)
            # An expired token may be answered with 401 or 403, so either is tried once with a new token.
            if status not in (401, 403):
                break
        return status, body

    def get(self, path, params):
        status, body = self._send(f"https://{self.host}{path}?{urllib.parse.urlencode(params)}")
        return _json_reply(status, body, path)

    def post(self, path, body):
        status, reply = self._send(f"https://{self.host}{path}", data=json.dumps(body).encode("utf-8"),
                                   method="POST", extra={"Content-Type": "application/json"})
        return _json_reply(status, reply, path)


class GitHub:
    """This workflow run, read with the job's own token (`actions: read`)."""

    def __init__(self, repository, run_id, token):
        if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repository or ""):
            raise ApprovalError("GITHUB_REPOSITORY is not an owner and repo name")
        self.repository, self.run_id, self.token = repository, parse_id(run_id, "GITHUB_RUN_ID"), token

    def own_run(self):
        status, body = _request(f"https://api.github.com/repos/{self.repository}/actions/runs/{self.run_id}",
                                headers={"Authorization": f"Bearer {self.token}",
                                         "Accept": "application/vnd.github+json"})
        return _json_reply(status, body, "GitHub's run")


class Receiver:
    def __init__(self, url):
        if not isinstance(url, str) or not re.fullmatch(r"https://[a-z0-9.-]+", url):
            raise ApprovalError("VOC_RECEIVER_URL must be the receiver's https address, with no path")
        self.url = url

    def post(self, raw, headers):
        status, _ = _request(f"{self.url}/api/result", data=raw, headers=headers, method="POST")
        return status


# The two jobs


def _target_and_entry(root):
    """The run's target, checked as Job A checks it (a first row, its list, its code and its gates), and its row."""
    from voc.frozen import RUNS, read_runs
    from voc.job_a import JobAError, checked_target

    try:
        return checked_target(root), read_runs(Path(root) / RUNS)[-1]
    except (JobAError, ValueError) as err:
        raise ApprovalError(f"the run log's last row cannot be run: {err}") from None


def _pin(root, kind):
    from voc.job_a import JobAError, pin_for

    try:
        return pin_for(root, kind)
    except JobAError as err:
        raise ApprovalError(str(err)) from None


def _own_run_checked(github, job_a_run_id):
    own = github.own_run()
    if own.get("display_title") != run_name(job_a_run_id):
        raise ApprovalError("this workflow run's name is not the exact name for its Job A run")
    if (own.get("event") != "workflow_dispatch" or own.get("head_branch") != "main"
            or own.get("path") != WORKFLOW_PATH):
        raise ApprovalError("this workflow run is not a dispatch of the approval workflow on main")
    return own


def _checked_job_a(root, job_a_run_id, databricks):
    """J16 item 5, on every path: the run, its being the newest, its exit value against the target and the pin.
    The run is read with its repair history, which Databricks may fill only when asked (review of #95)."""
    settings = cloud_settings(root)
    run = databricks.get("/api/2.2/jobs/runs/get", {"run_id": job_a_run_id, "include_history": "true"})
    task_run_id = checked_run(run, job_a_run_id, settings["job_a_job_id"])
    checked_latest(databricks.get("/api/2.2/jobs/runs/list", {"job_id": settings["job_a_job_id"],
                                                                "limit": RUNS_LIST_LIMIT}),
                   job_a_run_id, settings["job_a_job_id"])
    checked_no_active(databricks.get("/api/2.2/jobs/runs/list", {"job_id": settings["job_a_job_id"],
                                                                   "active_only": "true", "limit": RUNS_LIST_LIMIT}))
    value = exit_value(databricks.get("/api/2.2/jobs/runs/get-output", {"run_id": task_run_id}))
    run_target, entry = _target_and_entry(root)
    checked_exit(value, run_target, _pin(root, run_target.kind))
    return settings, run, value, entry


def figures_job(root, env, databricks, github):
    job_a_run_id = parse_id(env.get("JOB_A_RUN_ID"), "job_a_run_id")
    _own_run_checked(github, job_a_run_id)
    _, run, value, entry = _checked_job_a(root, job_a_run_id, databricks)
    lines = summary(job_a_run_id, run, value, entry)
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("## The figures to approve\n\n" + "".join(f"- {line}\n" for line in lines))
    return lines


def _post_result(receiver, env, body, sleep, tries=POST_TRIES):
    """Posts the signed message, a fresh timestamp each try. After a server error, a 429 or no answer it tries
    again, 3 tries in all. Anything but 202 at the end fails the job, so a lost message is never silent (review of
    #95)."""
    raw = message_bytes(body)
    status = 0
    for n in range(tries):
        try:
            status = receiver.post(raw, signed_headers(env["VOC_RESULT_SECRET"], int(time.time()), raw))
        except (OSError, http.client.HTTPException):
            status = 0
        if status == 202 or (0 < status < 500 and status != 429):
            break
        if n + 1 < tries:
            sleep(POST_WAIT_SECONDS * (n + 1))
    if status != 202:
        raise ApprovalError(f"the receiver did not take the result message: HTTP {status}")
    return f"result message: HTTP {status}"


def _post_quietly(receiver, env, body):
    """One try, with no wait, for a run being cancelled: GitHub allows a few seconds. A failure is let go, since
    the cancel itself is what the job reports."""
    try:
        _post_result(receiver, env, body, lambda seconds: None, tries=1)
    except Exception:  # noqa: BLE001
        pass


def _follow(databricks, job_b_run_id, sleep, polls, deadline, clock):
    """Job B's end, followed until the deadline. A failed or broken look is tried again at the next one."""
    looks = 0
    while clock() < deadline and (polls is None or looks < polls):
        looks += 1
        try:
            run = databricks.get("/api/2.2/jobs/runs/get", {"run_id": job_b_run_id})
        except (ApprovalError, OSError, http.client.HTTPException):
            run = None
        state = run.get("state") if isinstance(run, dict) and isinstance(run.get("state"), dict) else {}
        if state.get("life_cycle_state") in ENDED:
            return run, result_state(state.get("result_state"))
        if polls is None or looks < polls:
            sleep(POLL_SECONDS)
    return None, "UNKNOWN"


def _ids(env):
    return (parse_id(env.get("JOB_A_RUN_ID"), "job_a_run_id"), parse_id(env.get("GITHUB_RUN_ID"), "GITHUB_RUN_ID"),
            parse_id(env.get("GITHUB_RUN_ATTEMPT"), "GITHUB_RUN_ATTEMPT"))


def _latest_attempt(tasks):
    """Job B's latest task attempt: its one item, or the item with the highest of distinct whole attempt numbers,
    since the platform retried Job B's task once on its own in the dry run's round 2 (review of #105). None if the
    attempts cannot be ordered."""
    if len(tasks) == 1:
        return tasks[0]
    numbers = [task.get("attempt_number") for task in tasks]
    if not tasks or not all(type(n) is int for n in numbers) or len(set(numbers)) != len(numbers):
        return None
    return max(tasks, key=lambda task: task["attempt_number"])


def run_job(root, env, databricks, github, receiver, sleep=time.sleep, polls=None, clock=time.monotonic):
    deadline = clock() + FOLLOW_SECONDS
    job_a_run_id, github_run_id, attempt = _ids(env)
    if not env.get("VOC_RESULT_SECRET"):
        raise ApprovalError("VOC_RESULT_SECRET is not set")
    lines, sent = [], False
    try:
        if attempt != 1:
            raise ApprovalError("only a workflow run's first attempt can start Job B (J16 item 7)")
        own = _own_run_checked(github, job_a_run_id)
        if own.get("run_attempt") != 1:
            raise ApprovalError("only a workflow run's first attempt can start Job B (J16 item 7)")
        settings, _, _, _ = _checked_job_a(root, job_a_run_id, databricks)
        sent = True
        started = databricks.post("/api/2.2/jobs/run-now", {
            "job_id": settings["job_b_job_id"],
            "job_parameters": {"job_a_run_id": str(job_a_run_id), "github_run_id": str(github_run_id)}})
        job_b_run_id = _whole(started.get("run_id"), "Job B's run ID")
    except BaseException as err:
        # Before run-now is sent, Job B cannot have started. After it, a lost or odd reply may hide a start.
        body = result_body(github_run_id, attempt, job_a_run_id, None, "UNKNOWN" if sent else "NOT_STARTED", None)
        if not isinstance(err, Exception):  # a cancel: one quick try, and the cancel goes on
            _post_quietly(receiver, env, body)
            raise
        try:
            _post_result(receiver, env, body, sleep)
        except ApprovalError as failed:
            # Both reasons are named, so the first is not lost (second review of #95).
            first = str(err) if isinstance(err, ApprovalError) else type(err).__name__
            raise ApprovalError(f"{first}, and then {failed}") from None
        raise
    lines.append(f"Job B run: {job_b_run_id}")
    try:
        run, state = _follow(databricks, job_b_run_id, sleep, polls, deadline, clock)
        value = None
        if run is not None:
            tasks = run.get("tasks") if isinstance(run.get("tasks"), list) else []
            tasks = [t for t in tasks if isinstance(t, dict) and t.get("task_key") == "job_b"]
            latest = _latest_attempt(tasks)
            if latest is not None and state in ("SUCCESS", "FAILED"):
                try:
                    value = exit_for_receiver(job_b_exit(databricks.get(
                        "/api/2.2/jobs/runs/get-output",
                        {"run_id": _whole(latest.get("run_id"), "job_b's run ID")})), job_b_run_id)
                except (ApprovalError, OSError, http.client.HTTPException):
                    value = None
    except BaseException as err:
        if isinstance(err, Exception):
            raise
        # A cancel, or GitHub's own time limit, while following: the receiver is told Job B's end is unknown.
        _post_quietly(receiver, env, result_body(github_run_id, attempt, job_a_run_id, job_b_run_id, "UNKNOWN",
                                                 None))
        raise
    lines.append(f"result: {state}")
    lines.append(_post_result(receiver, env, result_body(github_run_id, attempt, job_a_run_id, job_b_run_id, state,
                                                         value), sleep))
    finished = state == "SUCCESS" and isinstance(value, dict) and value.get("stopped") is False
    lines.append(FINISHED if finished else NOT_FINISHED)
    return lines


def _clients(env):
    databricks = Databricks(env.get("VOC_DATABRICKS_HOST"), env.get("VOC_DATABRICKS_CLIENT_ID"),
                            env.get("VOC_DATABRICKS_CLIENT_SECRET"))
    github = GitHub(env.get("GITHUB_REPOSITORY"), env.get("GITHUB_RUN_ID"), env.get("GITHUB_TOKEN"))
    return databricks, github


def _root():
    return Path(__file__).resolve().parents[2]


def _figures_from_env(env):
    return figures_job(_root(), env, *_clients(env))


def _run_from_env(env):
    receiver = Receiver(env.get("VOC_RECEIVER_URL"))
    try:
        databricks, github = _clients(env)
    except Exception:
        # A bad setting, such as the host, still posts NOT_STARTED where the message can be signed and sent
        # (review of #95).
        try:
            ids = _ids(env) if env.get("VOC_RESULT_SECRET") else None
        except ApprovalError:
            ids = None
        if ids:
            job_a_run_id, github_run_id, attempt = ids
            _post_result(receiver, env, result_body(github_run_id, attempt, job_a_run_id, None, "NOT_STARTED",
                                                    None), time.sleep)
        raise
    return run_job(_root(), env, databricks, github, receiver)


def main(argv=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    env = dict(os.environ) if env is None else env
    if argv not in (["figures"], ["run"]):
        print("usage: approval.py figures|run")
        return 2
    try:
        lines = (_figures_from_env if argv == ["figures"] else _run_from_env)(env)
    except ApprovalError as err:
        print(f"refused: {err}")
        return 1
    except KeyboardInterrupt:  # a cancelled run, which GitHub stops with SIGINT: no traceback (J5)
        print("error: KeyboardInterrupt")
        return 130
    except Exception as err:  # noqa: BLE001, J5: the type only, never the message
        print(f"error: {type(err).__name__}")
        return 1
    for line in lines:
        print(line)
    return 1 if argv == ["run"] and lines[-1] == NOT_FINISHED else 0


if __name__ == "__main__":
    sys.exit(main())
