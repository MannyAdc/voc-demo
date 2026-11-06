"""Spec 004, J9 and J16: the receiver's logic, with no Azure, Databricks or GitHub library in it.

`handle_http` checks the caller, reads only the contract's fields, writes the event's key with an insert that fails
if it exists, puts the event on the queue, and replies. It gets no Databricks or GitHub client, so it does no work
before it replies. `handle_queue` does the work: for Job A's success it asks Databricks itself, checks GitHub for a
run with the same whole name, and dispatches the approval workflow. A result message is stored and starts nothing.

In the queue function, errors are raised, so the queue retries a message, 5 tries in all (`host.json`), and then
the runtime moves it to the failure queue. The HTTP function answers a failed queue put with 500, so the caller
retries. A failed purge of old keys is logged and never blocks the work. Logs hold event names, IDs, statuses and
counts only, never a secret or a body. Every string is checked whole, with `fullmatch`.
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
TIMESTAMP = re.compile(r"[0-9]{1,12}")
SIGNATURE = re.compile(r"sha256=[0-9a-f]{64}")
ID_TEXT = re.compile(r"[1-9][0-9]{0,18}")
MAX_AGE, MAX_AHEAD = 300, 60
# The 64-bit limit, which Databricks' IDs and Azure Tables' numbers keep to (review of #91).
MAX_ID = 2 ** 63 - 1
MAX_BODY = 16 * 1024
UNRESOLVED = "@Microsoft.KeyVault("
RESULT_STATES = {"SUCCESS", "FAILED", "TIMEDOUT", "CANCELED", "NOT_STARTED", "UNKNOWN"}
RESULT_KEYS = {"contract", "github_run_id", "github_run_attempt", "job_a_run_id", "job_b_run_id", "result_state",
               "job_b_exit"}
JOB_B_EXIT_KEYS = {"contract", "kind", "entry_kind", "complaints", "labelled", "stopped", "stop_reason",
                   "results_folder"}
KINDS = {"real", "synthetic"}
ENTRY_KINDS = {"real", "synthetic", "resume", "reproduction", "second"}
STOP_REASONS = {None, "spend_limit", "quota", "ledger_cap", "error"}


class ReceiverError(Exception):
    """A failure whose message holds only fixed text and counts. The queue retries it."""


class Malformed(ValueError):
    pass


class Lazy:
    """A service client made on first use, and only once. The queue function passes its Databricks and GitHub
    clients this way, so a result message, which needs neither, is stored with no Databricks or GitHub setting at
    all (owner decision, 6 November)."""

    def __init__(self, make):
        self._make, self._made = make, None

    def __getattr__(self, name):
        if self._made is None:
            self._made = self._make()
        return getattr(self._made, name)


@dataclass(frozen=True)
class Settings:
    basic_user: str
    basic_password: str
    hmac_secret: bytes
    job_a_job_id: int


@dataclass(frozen=True)
class Reply:
    status: int


def secret(env, name):
    """A secret from an app setting. An empty one, or a Key Vault reference Azure left unresolved, which is public
    text in this repo, stops the receiver (review of #91)."""
    value = env.get(name, "")
    if not value or value.startswith(UNRESOLVED):
        raise ReceiverError(f"{name} is empty or its Key Vault reference did not resolve")
    return value


def load_settings(env):
    job_id = env.get("VOC_JOB_A_JOB_ID", "")
    if not ID_TEXT.fullmatch(job_id) or int(job_id) > MAX_ID:
        raise ReceiverError("VOC_JOB_A_JOB_ID is not a job ID")
    return Settings(basic_user=secret(env, "VOC_BASIC_USER"), basic_password=secret(env, "VOC_BASIC_PASSWORD"),
                    hmac_secret=secret(env, "VOC_HMAC_SECRET").encode("utf-8"), job_a_job_id=int(job_id))


def purge_safely(store, days, log):
    """Deletes event keys older than `days`. A failure is logged and never blocks the work (review of #91)."""
    try:
        store.purge_older_than_days(days)
    except Exception:
        log("purge_failed")


def _one_of(value, allowed):
    """`value` is in `allowed`, and is a string or None, so a list or an object is refused, not a crash."""
    if not (value is None or isinstance(value, str)) or value not in allowed:
        raise Malformed("not one of the allowed values")
    return value


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
    scheme, _, credentials = value.partition(" ")
    if scheme.lower() != "basic":  # the scheme is case-insensitive (RFC 7617)
        return False
    try:
        user, sep, password = base64.b64decode(credentials, validate=True).decode("utf-8").partition(":")
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
        try:
            store.remove_key(key)  # so the caller's retry is not dropped as a duplicate
        except Exception:
            log(f"{event}_key_not_freed")  # rare, a known limit: the retry is then dropped for 30 days
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


def _job_b_exit(value, job_b_run_id):
    """Job B's exit value (J16 item 8). A finished run names `june-<Job B run ID>`, a stopped one no folder."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != JOB_B_EXIT_KEYS or value["contract"] != CONTRACT:
        raise Malformed("bad Job B exit value")
    _one_of(value["kind"], KINDS), _one_of(value["entry_kind"], ENTRY_KINDS)
    _one_of(value["stop_reason"], STOP_REASONS)
    if not isinstance(value["stopped"], bool) or job_b_run_id is None:
        raise Malformed("bad Job B exit value")
    _count(value["complaints"]), _count(value["labelled"])
    if value["stopped"]:
        if value["results_folder"] is not None or value["stop_reason"] is None:
            raise Malformed("a stopped run names no folder and gives its reason")
    elif value["results_folder"] != f"june-{job_b_run_id}" or value["stop_reason"] is not None:
        raise Malformed("a finished run names its own folder and no stop reason")
    return value


def _result(headers, body, settings, store, queue, now, log):
    found = _headers(headers)
    timestamp, signature = found.get("x-voc-timestamp", ""), found.get("x-voc-signature", "")
    if not (isinstance(timestamp, str) and TIMESTAMP.fullmatch(timestamp) and isinstance(signature, str)):
        log("result_refused")
        return Reply(401)
    age = now - int(timestamp)
    if age > MAX_AGE or -age > MAX_AHEAD:
        log("result_refused")
        return Reply(401)
    expected = sign(settings.hmac_secret, timestamp, body)
    if not (SIGNATURE.fullmatch(signature) and hmac.compare_digest(expected.encode("ascii"), signature.encode("ascii"))):
        log("result_refused")
        return Reply(401)
    try:
        message = _object(body)
        if canonical(message) != body:
            raise Malformed("not the contract's bytes")
        if set(message) != RESULT_KEYS or message["contract"] != CONTRACT:
            raise Malformed("bad result message")
        _one_of(message["result_state"], RESULT_STATES)
        _id(message["github_run_id"]), _id(message["github_run_attempt"]), _id(message["job_a_run_id"])
        _job_b_exit(message["job_b_exit"], _id(message["job_b_run_id"], nullable=True))
    except Malformed:
        log("result_malformed")
        return Reply(400)
    key = f"{message['github_run_id']}:{message['github_run_attempt']}"
    return _queue(key, {"kind": "result", **message}, store, queue, log, "result")


def handle_http(route, headers, body, settings, store, queue, now, log):
    """The HTTP function's logic. Replies 413, 401, 400, 202, 404 or 500, after no work but the queue put (J9)."""
    if len(body) > MAX_BODY:  # before any check, so a large body costs no hash (review of #91)
        log("body_too_large")
        return Reply(413)
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
