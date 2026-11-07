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
    # Changed in the fix round of #96: the deploy runs in its own environment, whose token its own identity trusts.
    assert job["environment"] == "receiver-deploy"


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
    # Changed in the fix round of #96: the receiver's own identity, RECEIVER_AZURE_CLIENT_ID.
    for name in ("RECEIVER_APP_NAME", "RECEIVER_RESOURCE_GROUP", "RECEIVER_URL", "RECEIVER_AZURE_CLIENT_ID",
                 "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"):
        assert "${{ secrets." + name + " }}" in text, name
    assert "azurewebsites.net" not in text


def test_J9_only_the_receiver_folder_is_packed_and_built_remotely():
    runs = "\n".join(step.get("run", "") for step in _steps())
    # Changed in the fix round of #96: the receiver's own files are named, with the commit.
    assert 'git archive --format=zip -o "$RUNNER_TEMP/receiver.zip" --add-virtual-file="BUILD_COMMIT:$GITHUB_SHA" HEAD:receiver' in runs
    assert "functionapp deployment source config-zip" in runs and "--build-remote true" in runs
    assert "-o none" in runs


def test_J9_the_deploy_checks_the_live_receiver_refuses_an_unsigned_call():
    """The check proves the new code answers, and sends nothing a receiver would take."""
    runs = "\n".join(step.get("run", "") for step in _steps())
    assert '"$RECEIVER_URL/api/result"' in runs and "401" in runs
    assert "X-Voc-Signature" not in runs


def test_J9_the_deploy_fails_until_the_owner_has_set_its_secrets():  # renamed in the last round of #96
    # Changed in the fix round of #96: a run with a secret unset fails, and only a moved main stops it quietly.
    first = _steps()[0]
    assert "go=false" in first["run"] and "exit 0" in first["run"] and "exit 1" in first["run"]


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
    # Changed in the fix round of #96: only 401 for the bad message, "queued", and the key to check and delete.
    lines = out.splitlines()
    assert lines[:2] == ["badly signed: HTTP 401 (must be 401)", "signed: HTTP 202 (must be 202: queued)"]
    assert lines[2].startswith("verdict: PASS, queued under the key 1:")
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
    body = json.loads(check.message_bytes(1793000000))  # changed in the fix round of #96: a fresh attempt each run
    assert body["result_state"] == "NOT_STARTED" and body["job_b_run_id"] is None and body["job_b_exit"] is None
    assert body["github_run_id"] == 1 and body["github_run_attempt"] == 1793000000 and body["job_a_run_id"] == 1


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
    raw = check.message_bytes(1793000000)  # changed in the fix round of #96
    headers = check.signed_headers(SECRET, 1793000000, raw)
    expected = hmac.new(SECRET.encode(), b"1793000000." + raw, hashlib.sha256).hexdigest()
    assert headers["X-Voc-Signature"] == f"sha256={expected}" and headers["X-Voc-Timestamp"] == "1793000000"
    assert raw == _core().canonical(json.loads(raw))



# The review of #96 and the owner's decisions of 7 November


def _function_app(monkeypatch):
    """receiver/function_app.py, imported with a small stand-in for `azure.functions`, which is not installed here."""
    import importlib
    import sys
    import types

    functions = types.ModuleType("azure.functions")

    class FunctionApp:
        def __init__(self, http_auth_level=None):
            pass

        def route(self, **kwargs):
            return lambda f: f

        def queue_trigger(self, **kwargs):
            return lambda f: f

    class HttpResponse:
        def __init__(self, status_code=200, headers=None):
            self.status_code, self.headers = status_code, dict(headers or {})

    functions.FunctionApp, functions.HttpResponse = FunctionApp, HttpResponse
    functions.AuthLevel = types.SimpleNamespace(ANONYMOUS="anonymous")
    functions.HttpRequest = functions.QueueMessage = object
    azure = types.ModuleType("azure")
    azure.functions = functions
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.functions", functions)
    monkeypatch.delitem(sys.modules, "function_app", raising=False)
    return importlib.import_module("function_app")


class Message:
    def __init__(self, body):
        self.body = body

    def get_body(self):
        return self.body


def test_J9_the_real_queue_function_stores_a_result_message_with_no_client_settings(monkeypatch):
    """Nit 3 of the review: the wiring of function_app.py itself, not only Lazy."""
    app = _function_app(monkeypatch)
    store = Store()
    monkeypatch.setattr(app, "_store", lambda: store)
    monkeypatch.setattr(app, "_settings", lambda: _core().Settings(basic_user="u", basic_password="syn-" + "p",
                                                                    hmac_secret=SECRET.encode(), job_a_job_id=1))
    monkeypatch.setattr(app, "purge_safely", lambda *a, **k: None)
    monkeypatch.setattr(app.DatabricksClient, "from_env", classmethod(lambda cls: _never()))
    monkeypatch.setattr(app.GitHubClient, "from_env", classmethod(lambda cls: _never()))
    body = json.loads((REPO / "tests" / "fixtures" / "june_contract" / "result_message.json").read_text(
        encoding="utf-8"))["body"]
    app.work(Message(json.dumps({"kind": "result", **body}).encode()))
    assert list(store.results) == ["600001:1"]


def test_J9_every_reply_names_the_deployed_commit(monkeypatch, tmp_path):
    """Minor 1 of the review: the deploy's check tells the new code from the old by the commit it reports."""
    core = _core()
    commit = "a" * 40
    (tmp_path / "BUILD_COMMIT").write_text(commit, encoding="utf-8")
    assert core.build_commit(tmp_path) == commit
    (tmp_path / "BUILD_COMMIT").write_text("not a commit", encoding="utf-8")
    assert core.build_commit(tmp_path) == "unknown"
    assert core.build_commit(tmp_path / "missing") == "unknown"
    app = _function_app(monkeypatch)
    monkeypatch.setattr(app, "BUILD", commit)
    monkeypatch.setattr(app, "handle_http", lambda *a, **k: core.Reply(401))
    monkeypatch.setattr(app, "_settings", lambda: None)
    monkeypatch.setattr(app, "_store", lambda: None)
    monkeypatch.setattr(app, "_queue", lambda: None)

    class Request:
        headers = {}

        def get_body(self):
            return b""

    reply = app.result(Request())
    assert reply.status_code == 401 and reply.headers == {"X-Voc-Build": commit}


def test_J9_lazy_survives_copy_and_a_maker_that_returns_none():
    """Nit 2 of the review."""
    import copy

    core = _core()
    calls = []

    def make():
        calls.append(1)
        return None

    lazy = core.Lazy(make)
    copy.copy(lazy)
    with pytest.raises(AttributeError):
        lazy.anything
    with pytest.raises(AttributeError):
        lazy.anything
    assert calls == [1]


def test_J9_the_deploy_runs_in_its_own_environment_with_its_own_identity():
    """Minor 5 of the review: a second identity, trusted only for this environment's token."""
    job = _workflow()["jobs"]["deploy"]
    assert job["environment"] == "receiver-deploy"
    login = next(s for s in _steps() if s.get("uses", "").startswith("azure/login@"))
    assert login["with"]["client-id"] == "${{ secrets.RECEIVER_AZURE_CLIENT_ID }}"
    assert "secrets.AZURE_CLIENT_ID" not in WORKFLOW.read_text(encoding="utf-8")


def test_J9_every_step_after_the_first_runs_only_when_the_deploy_goes_ahead():
    for step in _steps()[1:]:
        assert step["if"] == "steps.ready.outputs.go == 'true'", step.get("name")


def test_J9_a_deploy_with_its_secrets_unset_or_main_moved_on_fails_or_stops_plainly():
    """Minors 2 and 9 of the review: a run with no secrets fails, and an old run never rolls the receiver back."""
    first = _steps()[0]["run"]
    assert re.search(r"not all set[^\n]*\n\s*exit 1", first)
    assert "commits/main" in first and '"$GITHUB_SHA"' in first
    assert _steps()[0]["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_J9_the_cli_s_error_text_never_reaches_the_public_log():
    """Minor 4 of the review: the exit code only. The details are in the Azure portal."""
    deploy = next(s for s in _steps() if "config-zip" in s.get("run", ""))
    # Changed in the last round of #96: the error text is kept in a variable and only matched, never printed.
    assert "2>&1 >/dev/null" in deploy["run"] and "exit code" in deploy["run"]
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "set -x" not in text


def test_J9_only_the_receiver_s_own_files_are_packed_with_the_commit():
    """Nit 8 of the review: the two settings files are notes for the owner, not part of the app."""
    runs = "\n".join(step.get("run", "") for step in _steps())
    pack = next(line for line in runs.splitlines() if "git archive" in line)
    for name in ("function_app.py", "host.json", "requirements.txt", "receiver_core.py", "receiver_adapters.py"):
        assert name in pack, name
    assert "app_settings.json" not in pack and "plan.json" not in pack
    assert '--add-virtual-file="BUILD_COMMIT:$GITHUB_SHA"' in pack


def test_J9_the_live_receiver_check_sends_an_empty_body_and_wants_the_new_commit():
    """Minors 1 and 3 of the review, and nit 4."""
    check = next(s for s in _steps() if "/api/result" in s.get("run", ""))["run"]
    assert "--data ''" in check and "--silent" in check and "--output /dev/null" in check
    assert '[ "$status" = "401" ]' in check and "x-voc-build" in check.lower() and '"$GITHUB_SHA"' in check
    assert "10 minutes" in check


def test_J9_each_live_check_uses_a_fresh_synthetic_key():
    """Serious 1 of the review: a re-run is never a duplicate that passes with nothing queued."""
    check = _check()
    first, second = json.loads(check.message_bytes(1793000000)), json.loads(check.message_bytes(1793000060))
    assert first["github_run_attempt"] == 1793000000 and second["github_run_attempt"] == 1793000060
    assert first["github_run_id"] == 1 and first["job_a_run_id"] == 1


def test_J9_the_live_check_says_queued_names_its_key_and_takes_only_401_for_the_bad_one(monkeypatch, capsys):
    """Serious 1 and minor 11 of the review."""
    check = _check()
    monkeypatch.setattr(check.getpass, "getpass", lambda prompt="": SECRET)
    monkeypatch.setattr(check.time, "time", lambda: 1793000000)
    monkeypatch.setattr(check, "_post", Receiver())
    assert check.main(["https://receiver.example.invalid"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "badly signed: HTTP 401 (must be 401)"
    assert lines[1] == "signed: HTTP 202 (must be 202: queued)"
    assert lines[2] == "verdict: PASS, queued under the key 1:1793000000"
    assert "result" in lines[3] and "1:1793000000" in lines[3]

    class Gives400(Receiver):
        def __call__(self, url, raw, headers):
            status = super().__call__(url, raw, headers)
            return 400 if len(self.calls) == 1 else status

    monkeypatch.setattr(check, "_post", Gives400())
    assert check.main(["https://receiver.example.invalid"]) == 1


def test_J9_the_live_check_hints_at_the_clock_when_the_signed_message_is_refused(monkeypatch, capsys):
    """Nit 5 of the review."""
    check = _check()
    monkeypatch.setattr(check.getpass, "getpass", lambda prompt="": SECRET)
    monkeypatch.setattr(check, "_post", Receiver(secret="syn-" + "other"))
    assert check.main(["https://receiver.example.invalid"]) == 1
    out = capsys.readouterr().out
    assert "clock" in out and SECRET not in out


@pytest.mark.parametrize("failure, status", [("redirect", 302), ("network", 0), ("broken", 0), ("refused", 401)])
def test_J9_the_live_check_s_post_reports_a_status_and_follows_no_redirect(monkeypatch, failure, status):
    """Minor 10 and nit 5 of the review."""
    import http.client
    import urllib.error

    check = _check()

    def opened(request, timeout=None):
        if failure in ("redirect", "refused"):
            raise urllib.error.HTTPError(request.full_url, status, "x", {}, None)
        raise {"network": OSError("x"), "broken": http.client.BadStatusLine("x")}[failure]

    monkeypatch.setattr(check._OPENER, "open", opened)
    assert check._post("https://receiver.example.invalid/api/result", b"{}", {}) == status
    redirects = [h for h in check._OPENER.handlers if isinstance(h, check.urllib.request.HTTPRedirectHandler)]
    assert len(redirects) == 1 and isinstance(redirects[0], check._NoRedirect)



# The second review of #96, on its fix round (owner decision: the last round, fixed with no further review)

STEPS = REPO / "docs" / "RECEIVER_STEPS.md"


def _step(word):
    return next(s for s in _steps() if word in s.get("run", ""))["run"]


def test_J9_a_failed_upload_names_one_fixed_word_never_the_cli_s_text():
    """Minor 3: authorization, not found or other, so the owner knows where to look."""
    run = _step("config-zip")
    assert 'err=$(' in run and "2>&1 >/dev/null" in run
    for word in ("authorization", "not found", "other"):
        assert f'kind="{word}"' in run, word
    # The CLI's text is only ever matched, never printed.
    for line in run.splitlines():
        if "$err" in line:
            assert "grep" in line, line


def test_J9_the_live_receiver_check_says_what_it_saw_on_its_last_try():
    """Minor 4: the status and one fixed word on the last try."""
    run = _step("/api/result")
    assert 'if [ "$status" = "401" ] && [ "$build" = "$GITHUB_SHA" ]; then' in run
    for word in ("this commit", "another commit", "no header"):
        assert word in run, word


def test_J9_only_the_receiver_s_five_files_and_the_commit_are_packed_exactly():
    """Nit 6: the whole pack line, so no extra path can slip in."""
    assert _step("git archive").strip() == (
        'git archive --format=zip -o "$RUNNER_TEMP/receiver.zip" --add-virtual-file="BUILD_COMMIT:$GITHUB_SHA" '
        "HEAD:receiver function_app.py host.json requirements.txt receiver_core.py receiver_adapters.py")


def test_J9_the_function_reads_its_commit_from_its_own_folder(monkeypatch):
    """Nit 6: not only a patched value."""
    app = _function_app(monkeypatch)
    assert app.BUILD == _core().build_commit(REPO / "receiver") == "unknown"
    assert "build_commit(Path(__file__).resolve().parent)" in (REPO / "receiver" / "function_app.py").read_text(
        encoding="utf-8")


def test_J13_the_steps_give_the_exact_trust_subject_and_a_resource_group_of_its_own():
    """Minors 1 and 2: the subject with the repo's numeric IDs, and the receiver apart from the dashboard."""
    text = STEPS.read_text(encoding="utf-8")
    assert "repo:MannyAdc@84450984/voc-demo@1435727562:environment:receiver-deploy" in text
    assert "https://token.actions.githubusercontent.com" in text and "api://AzureADTokenExchange" in text
    assert "`voc-receiver-rg`" in text
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    assert "widens the role to the resource group" not in spec and "Reader on the Function's plan" in spec


def test_J9_the_steps_name_the_settings_the_first_deploy_needs():
    """Minor 5: the deploy's check gets 401 only once the receiver's settings load."""
    text = STEPS.read_text(encoding="utf-8")
    for name in ("VOC_BASIC_USER", "VOC_BASIC_PASSWORD", "VOC_HMAC_SECRET", "VOC_JOB_A_JOB_ID"):
        assert name in text, name


def test_J9_the_receiver_s_names_and_address_are_environment_secrets():
    """Minor 8: only jobs in `receiver-deploy` on main can read them."""
    text = STEPS.read_text(encoding="utf-8")
    for name in ("RECEIVER_APP_NAME", "RECEIVER_RESOURCE_GROUP", "RECEIVER_URL", "RECEIVER_AZURE_CLIENT_ID"):
        row = next(line for line in text.splitlines() if line.startswith(f"| `{name}`"))
        assert "`receiver-deploy` environment" in row, name


def test_J9_the_live_check_s_clean_up_waits_and_says_what_to_do_if_the_row_is_missing():
    """Minor 7, and nits 8 and 9."""
    text = STEPS.read_text(encoding="utf-8")
    for words in ("wait", "june-events-poison", "Storage Table Data Contributor", "printed lines only",
                  "deployed nothing"):
        assert words in text, words


def test_J9_the_owner_s_steps_create_the_function_before_its_role():
    """Minor 6."""
    spec = (REPO / "specs" / "004-june-test-and-baselines" / "spec.md").read_text(encoding="utf-8")
    steps = spec.split("## Owner's setup steps")[1]
    assert steps.index("- **Azure:** approve and create the Function") < steps.index("- **Azure, for the receiver's deploy")


def test_J9_the_clock_hint_gives_both_limits(monkeypatch, capsys):
    """Nit 2: the receiver allows 5 minutes behind and 1 minute ahead."""
    check = _check()
    monkeypatch.setattr(check.getpass, "getpass", lambda prompt="": SECRET)
    monkeypatch.setattr(check, "_post", Receiver(secret="syn-" + "other"))
    check.main(["https://receiver.example.invalid"])
    out = capsys.readouterr().out
    assert "5 minutes behind" in out and "1 minute ahead" in out
