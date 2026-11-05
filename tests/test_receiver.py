"""Spec 004, J9 and J16: the receiver, an Azure Function. Its logic is tested here with fakes for the table, the
queue, Databricks and GitHub. No test opens a network connection. Every value is synthetic, and the shared secrets
are built while the tests run (CLAUDE.md)."""
import base64
import hashlib
import hmac
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "june_contract"
RECEIVER = REPO / "receiver"
NOW = 1793000000
JOB_A = 800001


def _core():
    import receiver_core

    return receiver_core


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _secret():
    return ("syn-" + "hmac-" + "test").encode("utf-8")


def _password():
    return "syn-" + "basic-" + "test"


def _settings():
    return _core().Settings(basic_user="voc-databricks", basic_password=_password(), hmac_secret=_secret(),
                            job_a_job_id=JOB_A)


class Store:
    def __init__(self):
        self.keys, self.results = set(), {}

    def add_key(self, key):
        if key in self.keys:
            return False
        self.keys.add(key)
        return True

    def remove_key(self, key):
        self.keys.discard(key)

    def save_result(self, key, record):
        self.results[key] = record


class Queue:
    def __init__(self, fail=False):
        self.messages, self.fail = [], fail

    def put(self, message):
        if self.fail:
            raise OSError("synthetic queue error")
        self.messages.append(message)


class Log:
    def __init__(self):
        self.entries = []

    def __call__(self, event, **fields):
        self.entries.append((event, fields))


class Untouchable:
    """A client that must not be used."""

    def __getattr__(self, name):
        raise AssertionError(f"{name} was called")


def _basic(user="voc-databricks", password=None):
    raw = f"{user}:{_password() if password is None else password}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}


def _webhook(body=None, headers=None, store=None, queue=None, log=None):
    data = body if isinstance(body, bytes) else json.dumps(body or _fixture("databricks_webhook.json")).encode()
    store, queue, log = store or Store(), queue or Queue(), log or Log()
    reply = _core().handle_http("databricks", _basic() if headers is None else headers, data, _settings(), store,
                                queue, NOW, log)
    return reply, store, queue, log


def _canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _signature(timestamp, raw, secret=None):
    digest = hmac.new(secret or _secret(), str(timestamp).encode("ascii") + b"." + raw, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _result(body=None, raw=None, timestamp=None, signature=None, store=None, queue=None, log=None, now=NOW):
    fixture = _fixture("result_message.json")
    timestamp = fixture["timestamp"] if timestamp is None else timestamp
    raw = _canonical(fixture["body"] if body is None else body) if raw is None else raw
    headers = {"X-Voc-Timestamp": str(timestamp),
               "X-Voc-Signature": _signature(timestamp, raw) if signature is None else signature}
    store, queue, log = store or Store(), queue or Queue(), log or Log()
    reply = _core().handle_http("result", headers, raw, _settings(), store, queue, now, log)
    return reply, store, queue, log


# The webhook (J16 item 1)


def test_J16_the_databricks_fixture_is_accepted_and_queued():
    reply, store, queue, _ = _webhook()
    assert reply.status == 202
    assert queue.messages == [{"kind": "databricks", "job_a_run_id": 900001}]
    assert store.keys == {"900001:jobs.on_success"}


@pytest.mark.parametrize("headers", [
    {}, _basic(password="wrong"), _basic(user="someone"), {"Authorization": "Bearer x"},
    {"Authorization": "Basic not-base64!"}, {"Authorization": "Basic " + base64.b64encode(b"no-colon").decode()},
])
def test_J9_a_bad_sign_in_gets_401_and_nothing_is_queued(headers):
    reply, store, queue, _ = _webhook(headers=headers)
    assert reply.status == 401 and queue.messages == [] and store.keys == set()


def test_J9_the_sign_in_and_the_signature_are_compared_in_constant_time(monkeypatch):
    core = _core()
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(core.hmac, "compare_digest", spy)
    _webhook()
    first = len(calls)
    _result()
    assert first >= 2 and len(calls) > first


@pytest.mark.parametrize("change", [
    lambda b: b.pop("run"), lambda b: b["run"].update(run_id="900001"), lambda b: b["run"].update(run_id=0),
    lambda b: b["run"].update(run_id=-5), lambda b: b["run"].update(run_id=True),
    lambda b: b["run"].update(run_id=10 ** 19), lambda b: b["job"].update(job_id=None),
    lambda b: b.update(event_type=7),
])
def test_J16_a_malformed_webhook_after_a_good_sign_in_gets_400(change):
    body = _fixture("databricks_webhook.json")
    change(body)
    reply, store, queue, _ = _webhook(body=body)
    assert reply.status == 400 and queue.messages == [] and store.keys == set()


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"{}", b"\xff\xfe"])
def test_J16_a_webhook_that_is_not_an_object_gets_400(raw):
    assert _webhook(body=raw)[0].status == 400


@pytest.mark.parametrize("change", [lambda b: b.update(event_type="jobs.on_failure"),
                                    lambda b: b["job"].update(job_id=800009)])
def test_J16_other_events_and_other_jobs_get_202_and_are_dropped(change):
    body = _fixture("databricks_webhook.json")
    change(body)
    reply, store, queue, log = _webhook(body=body)
    assert reply.status == 202 and queue.messages == [] and store.keys == set()
    assert log.entries


def test_J9_a_duplicate_webhook_is_acknowledged_and_dropped():
    _, store, queue, _ = _webhook()
    reply, _, _, _ = _webhook(store=store, queue=queue)
    assert reply.status == 202 and len(queue.messages) == 1


def test_J9_a_failed_queue_put_releases_the_key_so_a_retry_is_queued():
    store = Store()
    reply, _, _, _ = _webhook(store=store, queue=Queue(fail=True))
    assert reply.status == 500 and store.keys == set()
    reply, _, queue, _ = _webhook(store=store)
    assert reply.status == 202 and len(queue.messages) == 1


def test_J9_the_reply_comes_before_any_work():
    """The HTTP function gets no Databricks or GitHub client at all, so it cannot do the work before it replies."""
    import inspect

    assert list(inspect.signature(_core().handle_http).parameters) == [
        "route", "headers", "body", "settings", "store", "queue", "now", "log"]


def test_J9_an_unknown_route_gets_404():
    reply = _core().handle_http("other", {}, b"", _settings(), Store(), Queue(), NOW, Log())
    assert reply.status == 404


# The result message (J16 item 9)


def test_J16_the_result_fixture_with_a_good_signature_is_accepted_and_queued():
    reply, store, queue, _ = _result()
    body = _fixture("result_message.json")["body"]
    assert reply.status == 202
    assert queue.messages == [{"kind": "result", **body}]
    assert store.keys == {"600001:1"}


def test_J16_the_signed_bytes_must_be_the_compact_sorted_form():
    body = _fixture("result_message.json")["body"]
    spaced = json.dumps(body, sort_keys=True).encode("utf-8")
    assert _result(raw=spaced)[0].status == 400
    unsorted = json.dumps(dict(reversed(list(body.items()))), separators=(",", ":")).encode("utf-8")
    assert _result(raw=unsorted)[0].status == 400
    assert _result(raw=_canonical(body) + b"\n")[0].status == 400


def test_J16_the_signature_is_checked_over_the_raw_bytes_received():
    body = _fixture("result_message.json")["body"]
    raw = _canonical(body)
    signed_over_other = _signature(1793000000, _canonical({**body, "github_run_attempt": 2}))
    assert _result(raw=raw, signature=signed_over_other)[0].status == 401


@pytest.mark.parametrize("signature", [
    "", "sha256=", "sha1=abc", _signature(1793000000, b"{}"),
    _signature(1793000000, _canonical(json.loads((FIXTURES / "result_message.json").read_text())["body"]),
               secret=b"other-secret"),
])
def test_J9_a_bad_signature_gets_401_and_nothing_is_queued(signature):
    reply, store, queue, _ = _result(signature=signature)
    assert reply.status == 401 and queue.messages == [] and store.keys == set()


def test_J16_the_signature_is_lowercase_hex():
    fixture = _fixture("result_message.json")
    raw = _canonical(fixture["body"])
    upper = "sha256=" + _signature(fixture["timestamp"], raw)[7:].upper()
    assert _result(signature=upper)[0].status == 401


@pytest.mark.parametrize("now, status", [(NOW + 300, 202), (NOW + 301, 401), (NOW - 60, 202), (NOW - 61, 401)])
def test_J9_a_timestamp_more_than_5_minutes_old_or_1_minute_ahead_gets_401(now, status):
    assert _result(now=now)[0].status == status


@pytest.mark.parametrize("timestamp", ["", "12a", " 1793000000", "-1793000000", "1.5"])
def test_J9_a_timestamp_that_is_not_unix_seconds_gets_401(timestamp):
    raw = _canonical(_fixture("result_message.json")["body"])
    headers = {"X-Voc-Timestamp": timestamp, "X-Voc-Signature": _signature(timestamp, raw)}
    reply = _core().handle_http("result", headers, raw, _settings(), Store(), Queue(), NOW, Log())
    assert reply.status == 401


def test_J9_header_names_are_read_in_any_case():
    fixture = _fixture("result_message.json")
    raw = _canonical(fixture["body"])
    headers = {"x-voc-timestamp": str(fixture["timestamp"]), "x-voc-signature": _signature(fixture["timestamp"], raw)}
    assert _core().handle_http("result", headers, raw, _settings(), Store(), Queue(), NOW, Log()).status == 202


@pytest.mark.parametrize("change", [
    lambda b: b.pop("job_a_run_id"), lambda b: b.update(extra=1), lambda b: b.update(contract="voc-june-2"),
    lambda b: b.update(github_run_id="600001"), lambda b: b.update(result_state="DONE"),
    lambda b: b["job_b_exit"].update(extra=1), lambda b: b["job_b_exit"].update(stop_reason="tired"),
    lambda b: b.update(job_b_run_id=0), lambda b: b.update(github_run_attempt=True),
])
def test_J16_a_malformed_result_after_a_good_signature_gets_400(change):
    body = _fixture("result_message.json")["body"]
    change(body)
    reply, store, queue, _ = _result(body=body)
    assert reply.status == 400 and queue.messages == [] and store.keys == set()


def test_J16_a_result_with_no_job_b_run_is_accepted():
    body = {**_fixture("result_message.json")["body"], "job_b_run_id": None, "result_state": "NOT_STARTED",
            "job_b_exit": None}
    assert _result(body=body)[0].status == 202


def test_J9_a_duplicate_result_is_acknowledged_and_dropped():
    _, store, queue, _ = _result()
    reply, _, _, _ = _result(store=store, queue=queue)
    assert reply.status == 202 and len(queue.messages) == 1


# The queue function (J9)


class Databricks:
    def __init__(self, run=None, error=None):
        self.run, self.error, self.asked = run or _fixture("job_a_run.json"), error, []

    def get_run(self, run_id):
        self.asked.append(run_id)
        if self.error:
            raise self.error
        return self.run


class GitHub:
    def __init__(self, runs=(), status=200):
        self.runs, self.status, self.dispatched = list(runs), status, []

    def list_dispatch_runs(self):
        return self.runs

    def dispatch(self, body):
        self.dispatched.append(body)
        return self.status


def _work(message, databricks=None, github=None, store=None, log=None):
    databricks, github, store, log = databricks or Databricks(), github or GitHub(), store or Store(), log or Log()
    _core().handle_queue(message, _settings(), databricks, github, store, log)
    return databricks, github, store, log


def test_J9_the_queue_function_asks_databricks_then_dispatches_the_contract_body():
    databricks, github, _, _ = _work({"kind": "databricks", "job_a_run_id": 900001})
    assert databricks.asked == [900001]
    assert github.dispatched == [_fixture("dispatch.json")]


@pytest.mark.parametrize("run", [
    {**_fixture("job_a_run.json"), "job_id": 800009},
    {**_fixture("job_a_run.json"), "state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"}},
    {**_fixture("job_a_run.json"), "state": {"life_cycle_state": "RUNNING"}},
    {**_fixture("job_a_run.json"), "run_id": 900002},
])
def test_J9_a_run_of_another_job_or_one_that_did_not_succeed_is_not_dispatched(run):
    _, github, _, log = _work({"kind": "databricks", "job_a_run_id": 900001}, databricks=Databricks(run=run))
    assert github.dispatched == [] and log.entries


def test_J9_a_dispatch_already_made_is_skipped():
    runs = [{"display_title": "June approval for Job A run 900001"}]
    _, github, _, _ = _work({"kind": "databricks", "job_a_run_id": 900001}, github=GitHub(runs=runs))
    assert github.dispatched == []


@pytest.mark.parametrize("title", ["June approval for Job A run 9000011", "June approval for Job A run 90000",
                                   "june approval for job a run 900001", "June approval for Job A run 900001 "])
def test_J16_only_the_whole_run_name_counts_as_a_dispatch_already_made(title):
    _, github, _, _ = _work({"kind": "databricks", "job_a_run_id": 900001}, github=GitHub(runs=[{"display_title": title}]))
    assert len(github.dispatched) == 1


@pytest.mark.parametrize("status, ok", [(200, True), (204, True), (403, False), (422, False), (500, False)])
def test_J16_a_dispatch_reply_of_200_or_204_is_success_and_any_other_is_retried(status, ok):
    message = {"kind": "databricks", "job_a_run_id": 900001}
    if ok:
        _work(message, github=GitHub(status=status))
    else:
        with pytest.raises(_core().ReceiverError):
            _work(message, github=GitHub(status=status))


def test_J9_a_failure_is_raised_so_the_queue_retries_it():
    with pytest.raises(OSError):
        _work({"kind": "databricks", "job_a_run_id": 900001}, databricks=Databricks(error=OSError("synthetic")))


def test_J9_a_result_message_is_stored_and_starts_nothing():
    body = _fixture("result_message.json")["body"]
    _, _, store, log = _work({"kind": "result", **body}, databricks=Untouchable(), github=Untouchable())
    assert store.results["600001:1"] == {"result_state": "SUCCESS", "job_a_run_id": 900001, "job_b_run_id": 900002,
                                         "complaints": 2073, "labelled": 2073, "stopped": False, "stop_reason": None}
    assert log.entries


def test_J9_an_unknown_queue_message_is_refused():
    with pytest.raises(_core().ReceiverError):
        _work({"kind": "other"})


def test_J9_logs_hold_ids_event_types_statuses_and_counts_only():
    logs = [_webhook()[3], _webhook(headers=_basic(password="wrong"))[3], _result()[3],
            _result(signature="sha256=00")[3], _work({"kind": "databricks", "job_a_run_id": 900001})[3],
            _work({"kind": "result", **_fixture("result_message.json")["body"]})[3]]
    for log in logs:
        for event, fields in log.entries:
            assert re.fullmatch(r"[a-z_]+", event)
            for value in fields.values():
                assert value is None or isinstance(value, (bool, int)) or re.fullmatch(r"[A-Za-z0-9_.:]{0,40}", value)
            text = json.dumps(fields)
            assert _password() not in text and _secret().decode() not in text and "voc-databricks" not in text


# The Function's files (J9)


def test_J9_failures_retry_5_times_in_all_then_go_to_the_failure_queue():
    host = json.loads((RECEIVER / "host.json").read_text(encoding="utf-8"))
    assert host["extensions"]["queues"]["maxDequeueCount"] == 5


def test_J9_the_plan_is_one_instance_per_function_of_512_mb_with_none_always_ready():
    plan = json.loads((RECEIVER / "plan.json").read_text(encoding="utf-8"))
    assert plan == {"maximumInstanceCount": 1, "instanceMemoryMB": 512, "alwaysReady": []}


def test_J9_the_app_settings_hold_only_key_vault_references_for_secrets_and_no_application_insights():
    settings = json.loads((RECEIVER / "app_settings.json").read_text(encoding="utf-8"))
    secrets = {"VOC_BASIC_USER", "VOC_BASIC_PASSWORD", "VOC_HMAC_SECRET", "VOC_DATABRICKS_CLIENT_ID",
               "VOC_DATABRICKS_CLIENT_SECRET", "VOC_GITHUB_TOKEN"}
    assert secrets <= set(settings)
    for name in secrets:
        assert re.fullmatch(r"@Microsoft\.KeyVault\(VaultName=[a-z0-9-]+;SecretName=[a-z0-9-]+\)", settings[name])
    for name, value in settings.items():
        if name not in secrets:
            assert not value.startswith("@Microsoft.KeyVault") and len(value) < 80
    assert not {n for n in settings if "APPINSIGHTS" in n or "APPLICATIONINSIGHTS" in n}


def test_J9_two_functions_open_at_the_http_level_and_one_queue_function():
    text = (RECEIVER / "function_app.py").read_text(encoding="utf-8")
    assert text.count("@app.route(") == 2 and 'route="databricks"' in text and 'route="result"' in text
    assert text.count("@app.queue_trigger(") == 1
    assert "AuthLevel.ANONYMOUS" in text and "AuthLevel.FUNCTION" not in text


def test_J9_the_functions_requirements_are_pinned():
    lines = [line for line in (RECEIVER / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if line and not line.startswith("#")]
    assert lines and all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", line) for line in lines)


# The review of #91


def _env(**changes):
    env = {"VOC_BASIC_USER": "voc-databricks", "VOC_BASIC_PASSWORD": _password(),
           "VOC_HMAC_SECRET": _secret().decode("utf-8"), "VOC_JOB_A_JOB_ID": str(JOB_A)}
    env.update(changes)
    return env


def test_J9_settings_load_from_the_environment():
    settings = _core().load_settings(_env())
    assert settings.job_a_job_id == JOB_A and settings.hmac_secret == _secret()


@pytest.mark.parametrize("name", ["VOC_BASIC_USER", "VOC_BASIC_PASSWORD", "VOC_HMAC_SECRET"])
@pytest.mark.parametrize("value", ["", "@Microsoft.KeyVault(VaultName=voc-june-kv;SecretName=voc-basic-user)"])
def test_J9_an_empty_or_unresolved_key_vault_secret_stops_the_receiver(name, value):
    with pytest.raises(_core().ReceiverError):
        _core().load_settings(_env(**{name: value}))


@pytest.mark.parametrize("value", ["", "x", "0", "9223372036854775808"])
def test_J9_a_job_a_job_id_that_is_not_an_id_stops_the_receiver(value):
    with pytest.raises(_core().ReceiverError):
        _core().load_settings(_env(VOC_JOB_A_JOB_ID=value))


def test_J9_the_extension_bundle_and_the_queue_encoding_are_set():
    host = json.loads((RECEIVER / "host.json").read_text(encoding="utf-8"))
    assert host["extensionBundle"]["id"] == "Microsoft.Azure.Functions.ExtensionBundle"
    assert host["extensionBundle"]["version"].startswith("[4.")
    assert host["extensions"]["queues"]["messageEncoding"] == "none"


def test_J9_the_failure_queue_is_the_work_queue_s_poison_queue_named_in_the_spec():
    text = (RECEIVER / "function_app.py").read_text(encoding="utf-8")
    assert 'QUEUE = "june-events"' in text
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    assert "`june-events-poison`" in spec


def test_J16_a_timestamp_with_a_trailing_newline_gets_401():
    raw = _canonical(_fixture("result_message.json")["body"])
    timestamp = "1793000000\n"
    headers = {"X-Voc-Timestamp": timestamp, "X-Voc-Signature": _signature(timestamp, raw)}
    assert _core().handle_http("result", headers, raw, _settings(), Store(), Queue(), NOW, Log()).status == 401


@pytest.mark.parametrize("change", [
    lambda b: b.update(result_state=["SUCCESS"]), lambda b: b["job_b_exit"].update(kind={"a": 1}),
    lambda b: b["job_b_exit"].update(entry_kind=["real"]), lambda b: b["job_b_exit"].update(stop_reason=[None]),
    lambda b: b["job_b_exit"].update(results_folder="june-900002\n"),
    lambda b: b["job_b_exit"].update(results_folder="june-900003"),
    lambda b: b["job_b_exit"].update(stopped=True, stop_reason="spend_limit"),
    lambda b: b["job_b_exit"].update(results_folder=None),
    lambda b: b["job_b_exit"].pop("labelled"), lambda b: b.update(job_b_run_id=2 ** 63),
])
def test_J16_a_signed_result_with_a_bad_field_gets_400_not_500(change):
    body = _fixture("result_message.json")["body"]
    change(body)
    assert _result(body=body)[0].status == 400


def test_J16_a_stopped_run_has_no_results_folder():
    body = _fixture("result_message.json")["body"]
    body["job_b_exit"] = {**body["job_b_exit"], "stopped": True, "stop_reason": "quota", "labelled": 1500,
                          "results_folder": None}
    assert _result(body=body)[0].status == 202


def test_J16_ids_above_the_64_bit_limit_get_400():
    body = _fixture("databricks_webhook.json")
    body["run"]["run_id"] = 2 ** 63
    assert _webhook(body=body)[0].status == 400


@pytest.mark.parametrize("route", ["databricks", "result"])
def test_J9_a_body_over_16_kb_gets_413_before_any_check(route):
    reply = _core().handle_http(route, {}, b"x" * (16 * 1024 + 1), _settings(), Untouchable(), Untouchable(), NOW,
                                Log())
    assert reply.status == 413


def test_J9_the_basic_scheme_and_the_header_name_are_read_in_any_case():
    raw = f"voc-databricks:{_password()}".encode("utf-8")
    headers = {"authorization": "basic " + base64.b64encode(raw).decode("ascii")}
    assert _webhook(headers=headers)[0].status == 202


def test_J9_the_compare_result_decides_the_sign_in(monkeypatch):
    """If the compare's result were ignored, a wrong password would pass when the compare says no."""
    core = _core()
    assert _webhook(headers=_basic(password="wrong"))[0].status == 401
    monkeypatch.setattr(core.hmac, "compare_digest", lambda a, b: True)
    assert _webhook(headers=_basic(password="wrong"))[0].status == 202
    assert _result(signature="sha256=" + "0" * 64)[0].status == 202


def test_J9_the_core_imports_no_service_library_so_the_reply_needs_no_service():
    import importlib
    import sys

    for name in ("receiver_core", "receiver_adapters", "azure", "azure.functions"):
        sys.modules.pop(name, None)
    importlib.import_module("receiver_core")
    assert "receiver_adapters" not in sys.modules and "azure" not in sys.modules
    reply, store, queue, _ = _webhook()
    assert reply.status == 202 and queue.messages == [{"kind": "databricks", "job_a_run_id": 900001}]


class StuckStore(Store):
    def remove_key(self, key):
        raise OSError("synthetic table error")


def test_J9_a_key_that_cannot_be_freed_is_logged():
    reply, _, _, log = _webhook(store=StuckStore(), queue=Queue(fail=True))
    assert reply.status == 500 and ("webhook_key_not_freed", {}) in log.entries


class FailingPurge(Store):
    def purge_older_than_days(self, days):
        raise OSError("synthetic table error")


def test_J9_a_failed_purge_is_logged_and_never_blocks_the_work():
    log = Log()
    _core().purge_safely(FailingPurge(), 30, log)
    assert ("purge_failed", {}) in log.entries


def test_J9_the_functions_requirements_are_resolved_for_linux():
    text = (RECEIVER / "requirements.txt").read_text(encoding="utf-8")
    assert "for Linux" in text.splitlines()[0]


# The spike of pull request 5a (6 November): the robot's OAuth secret is made with the `jobs` scope only, and a
# token request for `all-apis` is refused ("Scopes 'all-apis' are not assigned to the client").


def test_J13_the_receiver_asks_databricks_for_the_jobs_scope_only(monkeypatch):
    import base64
    import urllib.parse

    import receiver_adapters

    sent = []

    def fake(url, data=None, headers=None, method="GET"):
        sent.append((url, data, headers, method))
        return 200, b'{"access_token": "synthetic"}'

    monkeypatch.setattr(receiver_adapters, "_request", fake)
    secret = "syn-" + "secret"
    client = receiver_adapters.DatabricksClient("synthetic.example.invalid", "synthetic-id", secret)
    assert client._token() == "synthetic"
    assert len(sent) == 1
    url, data, headers, method = sent[0]
    assert url == "https://synthetic.example.invalid/oidc/v1/token" and method == "POST"
    assert urllib.parse.parse_qs(data.decode("ascii")) == {"grant_type": ["client_credentials"], "scope": ["jobs"]}
    # Review of #93, nit 3: the client's ID and secret go in the Basic header, and the body is a form.
    assert headers == {"Authorization": "Basic " + base64.b64encode(f"synthetic-id:{secret}".encode()).decode(),
                       "Content-Type": "application/x-www-form-urlencoded"}
