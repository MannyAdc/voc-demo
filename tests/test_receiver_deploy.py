"""Spec 004, J9: the receiver's deploy workflow, the queue function's lazy clients, and the owner's live check of a
deployed receiver. On synthetic data only. No test opens a network connection."""
import hashlib
import hmac
import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "deploy_receiver.yml"
SCRIPT = REPO / "scripts" / "receiver_live_check.py"
SECRET = "syn-" + "hmac-" + "live"


def _core():
    import receiver_core

    return receiver_core


# The queue function builds the Databricks and GitHub clients only for a Databricks message (owner decision,
# 6 November), so a result message is stored with no Databricks or GitHub setting at all.


class Store:
    def __init__(self):
        self.results = {}

    def save_result(self, key, record):
        self.results[key] = record


def _never():
    raise AssertionError("a client was built for a result message")


def test_J9_a_result_message_is_stored_without_building_any_client():
    core = _core()
    message = {"kind": "result", **json.loads((REPO / "tests" / "fixtures" / "june_contract" /
                                               "result_message.json").read_text(encoding="utf-8"))["body"]}
    store = Store()
    settings = core.Settings(basic_user="u", basic_password="syn-" + "p", hmac_secret=SECRET.encode(), job_a_job_id=1)
    core.handle_queue(message, settings, core.Lazy(_never), core.Lazy(_never), store, lambda *a, **k: None)
    assert list(store.results) == ["600001:1"]


def test_J9_a_lazy_client_is_built_once_on_first_use():
    core = _core()
    built = []

    class Client:
        def get_run(self, run_id):
            return {"run_id": run_id}

    def make():
        built.append(1)
        return Client()

    lazy = core.Lazy(make)
    assert built == []
    assert lazy.get_run(5) == {"run_id": 5} and lazy.get_run(6) == {"run_id": 6}
    assert built == [1]


def test_J9_the_queue_function_passes_lazy_clients():
    text = (REPO / "receiver" / "function_app.py").read_text(encoding="utf-8")
    assert "Lazy(DatabricksClient.from_env)" in text and "Lazy(GitHubClient.from_env)" in text
    assert "DatabricksClient.from_env()" not in text and "GitHubClient.from_env()" not in text


# The deploy workflow (J9, owner decision of 6 November)


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _on(workflow):
    return workflow.get("on", workflow.get(True))


def _steps():
    return _workflow()["jobs"]["deploy"]["steps"]


def test_J9_the_receiver_is_deployed_only_by_hand_from_main():
    workflow = _workflow()
    assert _on(workflow) == {"workflow_dispatch": None}
    job = workflow["jobs"]["deploy"]
    assert set(workflow["jobs"]) == {"deploy"}
    assert job["if"] == "github.ref == 'refs/heads/main'" and job["runs-on"] == "ubuntu-24.04"
    assert workflow["permissions"] == {"contents": "read", "id-token": "write"}
    assert workflow["concurrency"] == {"group": "deploy-receiver", "cancel-in-progress": False}
    assert job["timeout-minutes"] <= 30
    # No environment: Azure trusts this repo's main branch, and an environment would change the token's subject.
    assert "environment" not in job


def test_J9_every_action_is_pinned_and_no_value_is_written_into_a_script():
    for step in _steps():
        if "uses" in step:
            assert re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
            if step["uses"].startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False
        assert "${{" not in step.get("run", ""), step.get("name")


def test_J9_the_app_s_names_and_address_are_secrets_not_files():
    """The receiver's address is not written in this public repo."""
    text = WORKFLOW.read_text(encoding="utf-8")
    for name in ("RECEIVER_APP_NAME", "RECEIVER_RESOURCE_GROUP", "RECEIVER_URL", "AZURE_CLIENT_ID", "AZURE_TENANT_ID",
                 "AZURE_SUBSCRIPTION_ID"):
        assert "${{ secrets." + name + " }}" in text, name
    assert "azurewebsites.net" not in text


def test_J9_only_the_receiver_folder_is_packed_and_built_remotely():
    runs = "\n".join(step.get("run", "") for step in _steps())
    assert 'git archive --format=zip -o "$RUNNER_TEMP/receiver.zip" HEAD:receiver' in runs
    assert "functionapp deployment source config-zip" in runs and "--build-remote true" in runs
    assert "-o none" in runs


def test_J9_the_deploy_checks_the_live_receiver_refuses_an_unsigned_call():
    """The check proves the new code answers, and sends nothing a receiver would take."""
    runs = "\n".join(step.get("run", "") for step in _steps())
    assert '"$RECEIVER_URL/api/result"' in runs and "401" in runs
    assert "X-Voc-Signature" not in runs


def test_J9_the_deploy_waits_until_the_owner_has_set_its_secrets():
    first = _steps()[0]
    assert "go=false" in first["run"] and "exit 0" in first["run"]


# The owner's live check (owner decisions, 6 November)


def _check():
    import importlib.util

    spec = importlib.util.spec_from_file_location("receiver_live_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Receiver:
    """Posts into the receiver's own code, with the secret the owner types."""

    def __init__(self, secret=SECRET, accept_bad=False):
        self.secret, self.accept_bad, self.calls = secret, accept_bad, []

    def __call__(self, url, raw, headers):
        import time

        core = _core()
        self.calls.append((url, raw, headers))
        settings = core.Settings(basic_user="u", basic_password="syn-" + "p", hmac_secret=self.secret.encode(),
                                 job_a_job_id=1)

        class Keys:
            def add_key(self, key):
                return True

            def remove_key(self, key):
                pass

        class Queue:
            def put(self, message):
                pass

        status = core.handle_http("result", headers, raw, settings, Keys(), Queue(), int(time.time()),
                                  lambda *a, **k: None).status
        return 202 if self.accept_bad and len(self.calls) == 1 else status


def test_J9_the_live_check_sends_a_refused_and_an_accepted_message(monkeypatch, capsys):
    check = _check()
    monkeypatch.setattr(check.getpass, "getpass", lambda prompt="": SECRET)
    receiver = Receiver()
    monkeypatch.setattr(check, "_post", receiver)
    assert check.main(["https://receiver.example.invalid"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == ["badly signed: HTTP 401 (must be 401 or 400)", "signed: HTTP 202 (must be 202)",
                                "verdict: PASS"]
    assert SECRET not in out
    assert [url for url, _, _ in receiver.calls] == ["https://receiver.example.invalid/api/result"] * 2


def test_J9_the_live_check_fails_when_a_bad_signature_is_taken_or_a_good_one_refused(monkeypatch, capsys):
    check = _check()
    monkeypatch.setattr(check.getpass, "getpass", lambda prompt="": SECRET)
    monkeypatch.setattr(check, "_post", Receiver(accept_bad=True))
    assert check.main(["https://receiver.example.invalid"]) == 1
    assert capsys.readouterr().out.splitlines()[-1].startswith("verdict: FAIL")
    monkeypatch.setattr(check, "_post", Receiver(secret="syn-" + "other"))
    assert check.main(["https://receiver.example.invalid"]) == 1


def test_J9_the_live_check_s_message_is_synthetic_and_starts_nothing():
    check = _check()
    body = json.loads(check.message_bytes())
    assert body["result_state"] == "NOT_STARTED" and body["job_b_run_id"] is None and body["job_b_exit"] is None
    assert body["github_run_id"] == 1 and body["github_run_attempt"] == 1 and body["job_a_run_id"] == 1


@pytest.mark.parametrize("argv", [[], ["https://receiver.example.invalid", SECRET], ["http://receiver.example"],
                                  ["https://receiver.example/api"]])
def test_J9_the_live_check_takes_only_the_address_never_the_secret_as_an_argument(monkeypatch, capsys, argv):
    """Owner decision: the secret never goes on the command line, which PowerShell keeps in its history file."""
    check = _check()
    monkeypatch.setattr(check.getpass, "getpass", lambda prompt="": pytest.fail("asked for the secret"))
    assert check.main(argv) == 2
    assert SECRET not in capsys.readouterr().out


def test_J9_the_live_check_asks_for_the_secret_with_a_hidden_prompt_and_drops_it():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "getpass.getpass(" in text and "input(" not in text
    assert "del secret" in text
    for word in ("print(secret", "logging"):
        assert word not in text


def test_J9_the_live_check_signs_as_the_receiver_checks():
    check = _check()
    raw = check.message_bytes()
    headers = check.signed_headers(SECRET, 1793000000, raw)
    expected = hmac.new(SECRET.encode(), b"1793000000." + raw, hashlib.sha256).hexdigest()
    assert headers["X-Voc-Signature"] == f"sha256={expected}" and headers["X-Voc-Timestamp"] == "1793000000"
    assert raw == _core().canonical(json.loads(raw))
