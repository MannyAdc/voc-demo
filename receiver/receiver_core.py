"""Spec 004, J9 and J16: the receiver's logic, with no Azure, Databricks or GitHub library in it.

`handle_http` checks the caller, reads only the contract's fields, writes the event's key with an insert that fails
if it exists, puts the event on the queue, and replies. It gets no Databricks or GitHub client, so it does no work
before it replies. `handle_queue` does the work: for Job A's success it asks Databricks itself, checks GitHub for a
run with the same whole name, and dispatches the approval workflow. A result message is stored and starts nothing.

Errors are raised, never swallowed, so the queue retries a message, 5 tries in all (`host.json`), and then moves it
to the failure queue. Logs hold event names, IDs, statuses and counts only, never a secret or a body.
"""
import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass

CONTRACT = "voc-june-1"
RUN_NAME = "June approval for Job A run {}"
SUCCESS_EVENT = "jobs.on_success"
TIMESTAMP = re.compile(r"^[0-9]{1,12}$")
SIGNATURE = re.compile(r"^sha256=[0-9a-f]{64}$")
MAX_AGE, MAX_AHEAD = 300, 60
MAX_ID = 10 ** 19 - 1
RESULT_STATES = {"SUCCESS", "FAILED", "TIMEDOUT", "CANCELED", "NOT_STARTED", "UNKNOWN"}
RESULT_KEYS = {"contract", "github_run_id", "github_run_attempt", "job_a_run_id", "job_b_run_id", "result_state",
               "job_b_exit"}
JOB_B_EXIT_KEYS = {"contract", "kind", "entry_kind", "complaints", "labelled", "stopped", "stop_reason",
                   "results_folder"}
KINDS = {"real", "synthetic"}
ENTRY_KINDS = {"real", "synthetic", "resume", "reproduction", "second"}
STOP_REASONS = {None, "spend_limit", "quota", "ledger_cap", "error"}
FOLDER = re.compile(r"^june-[1-9][0-9]{0,18}$")


class ReceiverError(Exception):
    """A failure whose message holds only fixed text and counts. The queue retries it."""


class Malformed(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    basic_user: str
    basic_password: str
    hmac_secret: bytes
    job_a_job_id: int


@dataclass(frozen=True)
class Reply:
    status: int


def _id(value, nullable=False):
    """A whole number above zero, never a bool or a string (J16)."""
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_ID:
        raise Malformed("not an ID")
    return value


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Malformed("not a count")
    return value


def _headers(headers):
    return {str(name).lower(): value for name, value in headers.items()}


def _signed_in(headers, settings):
    value = _headers(headers).get("authorization", "")
    if not value.startswith("Basic "):
        return False
    try:
        user, sep, password = base64.b64decode(value[6:], validate=True).decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user_ok = hmac.compare_digest(user.encode("utf-8"), settings.basic_user.encode("utf-8"))
    password_ok = hmac.compare_digest(password.encode("utf-8"), settings.basic_password.encode("utf-8"))
    return bool(sep) and user_ok and password_ok


def _object(body):
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Malformed("not JSON") from None
    if not isinstance(value, dict):
        raise Malformed("not an object")
    return value


def _queue(key, message, store, queue, log, event):
    if not store.add_key(key):
        log(f"{event}_duplicate")
        return Reply(202)
    try:
        queue.put(message)
    except Exception:
        store.remove_key(key)  # so the caller's retry is not dropped as a duplicate
        log(f"{event}_queue_failed")
        return Reply(500)
    log(f"{event}_queued")
    return Reply(202)


def _databricks(headers, body, settings, store, queue, log):
    if not _signed_in(headers, settings):
        log("webhook_refused")
        return Reply(401)
    try:
        event = _object(body)
        event_type = event.get("event_type")
        run, job = event.get("run"), event.get("job")
        if not isinstance(event_type, str) or not isinstance(run, dict) or not isinstance(job, dict):
            raise Malformed("missing fields")
        run_id, job_id = _id(run.get("run_id")), _id(job.get("job_id"))
    except Malformed:
        log("webhook_malformed")
        return Reply(400)
    if event_type != SUCCESS_EVENT or job_id != settings.job_a_job_id:
        log("webhook_dropped", job_id=job_id, run_id=run_id, is_success=event_type == SUCCESS_EVENT)
        return Reply(202)
    return _queue(f"{run_id}:{event_type}", {"kind": "databricks", "job_a_run_id": run_id}, store, queue, log,
                  "webhook")


def canonical(value):
    """The contract's bytes: sorted keys at every level, no spaces, ASCII escapes, no newline (J16 item 9)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sign(secret, timestamp, raw):
    return "sha256=" + hmac.new(secret, timestamp.encode("ascii") + b"." + raw, hashlib.sha256).hexdigest()


def _job_b_exit(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != JOB_B_EXIT_KEYS or value["contract"] != CONTRACT:
        raise Malformed("bad Job B exit value")
    if value["kind"] not in KINDS or value["entry_kind"] not in ENTRY_KINDS or value["stop_reason"] not in STOP_REASONS:
        raise Malformed("bad Job B exit value")
    if not isinstance(value["stopped"], bool):
        raise Malformed("bad Job B exit value")
    _count(value["complaints"]), _count(value["labelled"])
    folder = value["results_folder"]
    if not (folder is None or (isinstance(folder, str) and FOLDER.match(folder))):
        raise Malformed("bad Job B exit value")
    return value


def _result(headers, body, settings, store, queue, now, log):
    found = _headers(headers)
    timestamp, signature = found.get("x-voc-timestamp", ""), found.get("x-voc-signature", "")
    if not (isinstance(timestamp, str) and TIMESTAMP.match(timestamp) and isinstance(signature, str)):
        log("result_refused")
        return Reply(401)
    age = now - int(timestamp)
    if age > MAX_AGE or -age > MAX_AHEAD:
        log("result_refused")
        return Reply(401)
    expected = sign(settings.hmac_secret, timestamp, body)
    if not (SIGNATURE.match(signature) and hmac.compare_digest(expected.encode("ascii"), signature.encode("ascii"))):
        log("result_refused")
        return Reply(401)
    try:
        message = _object(body)
        if canonical(message) != body:
            raise Malformed("not the contract's bytes")
        if set(message) != RESULT_KEYS or message["contract"] != CONTRACT or message["result_state"] not in RESULT_STATES:
            raise Malformed("bad result message")
        _id(message["github_run_id"]), _id(message["github_run_attempt"]), _id(message["job_a_run_id"])
        _id(message["job_b_run_id"], nullable=True)
        _job_b_exit(message["job_b_exit"])
    except Malformed:
        log("result_malformed")
        return Reply(400)
    key = f"{message['github_run_id']}:{message['github_run_attempt']}"
    return _queue(key, {"kind": "result", **message}, store, queue, log, "result")


def handle_http(route, headers, body, settings, store, queue, now, log):
    """The HTTP function's logic. Replies 401, 400, 202, 404 or 500, after no work but the queue put (J9)."""
    if route == "databricks":
        return _databricks(headers, body, settings, store, queue, log)
    if route == "result":
        return _result(headers, body, settings, store, queue, now, log)
    return Reply(404)


def _succeeded(run, run_id, settings):
    state = run.get("state") or {}
    return (run.get("run_id") == run_id and run.get("job_id") == settings.job_a_job_id
            and state.get("result_state") == "SUCCESS")


def handle_queue(message, settings, databricks, github, store, log):
    """The queue function's logic. Raises on any failure, so the queue retries the message."""
    kind = message.get("kind")
    if kind == "databricks":
        run_id = _id(message.get("job_a_run_id"))
        run = databricks.get_run(run_id)
        if not _succeeded(run, run_id, settings):
            log("dispatch_skipped_not_job_a_success", run_id=run_id)
            return
        name = RUN_NAME.format(run_id)
        if any(r.get("display_title") == name for r in github.list_dispatch_runs()):
            log("dispatch_skipped_already_made", run_id=run_id)
            return
        status = github.dispatch({"ref": "main", "inputs": {"job_a_run_id": str(run_id)}})
        if status not in (200, 204):
            raise ReceiverError(f"the dispatch got HTTP {status}")
        log("dispatched", run_id=run_id, status=status)
        return
    if kind == "result":
        exit_value = message.get("job_b_exit") or {}
        key = f"{message['github_run_id']}:{message['github_run_attempt']}"
        record = {"result_state": message["result_state"], "job_a_run_id": message["job_a_run_id"],
                  "job_b_run_id": message["job_b_run_id"], "complaints": exit_value.get("complaints"),
                  "labelled": exit_value.get("labelled"), "stopped": exit_value.get("stopped"),
                  "stop_reason": exit_value.get("stop_reason")}
        store.save_result(key, record)
        log("result_stored", github_run_id=message["github_run_id"], job_b_run_id=message["job_b_run_id"],
            result_state=message["result_state"], labelled=exit_value.get("labelled"))
        return
    raise ReceiverError("an unknown queue message")
