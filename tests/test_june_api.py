"""Spec 004, J11 and J12: Job B's API backend checks every answer's workspace header, and a spend limit refusal or a
wrong workspace stops the whole run at once, with no retry (pull request 6b, part 3b).

No test calls the network: the backend is built with a fake client. Fake keys are built while the test runs.
"""
from types import SimpleNamespace

import pytest

from voc.backends import make_backend
from voc.replay import Answer, ModelError, PermanentModelError

WORKSPACE = "wrkspc_" + "SYN" + "1" * 20


def _fake_key():
    return "sk-" + "ant-" + "api03-" + "Q" * 40


def _response(text='{"label": "Mortgage"}'):
    usage = SimpleNamespace(input_tokens=120, output_tokens=30, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn", usage=usage)


class RawClient:
    """Stands in for `anthropic.Anthropic`, with the raw response that carries the headers."""

    def __init__(self, headers=None, error=None):
        self.headers = {"anthropic-workspace-id": WORKSPACE} if headers is None else headers
        self.error, self.calls = error, 0
        self.messages = SimpleNamespace(create=self._plain,
                                        with_raw_response=SimpleNamespace(create=self._raw))

    def __call__(self, **kwargs):
        return self

    def _plain(self, **kwargs):
        raise AssertionError("with a workspace to check, every call must read the raw response's headers")

    def _raw(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return SimpleNamespace(headers=self.headers, parse=_response)


def _backend(client):
    return make_backend("api", env={"ANTHROPIC_API_KEY": _fake_key()}, model="claude-haiku-5-5",
                        client_factory=client, workspace=WORKSPACE)


SETTINGS = {"max_tokens": 2048, "effort": "low", "thinking": "adaptive"}


def test_J11_an_answer_from_the_cloud_workspace_is_taken():
    answer = _backend(RawClient())("a synthetic prompt", SETTINGS)
    assert answer.text == '{"label": "Mortgage"}' and answer.input_tokens == 120


@pytest.mark.parametrize("headers", [{"anthropic-workspace-id": "wrkspc_other"}, {}])
def test_J11_an_answer_for_another_workspace_or_none_stops_the_run(headers):
    from voc.replay import StopRun

    with pytest.raises(StopRun, match="^the API answered for another workspace, so the run stops$") as caught:
        _backend(RawClient(headers=headers))("a synthetic prompt", SETTINGS)
    assert caught.value.reason == "error"


class _Refused(Exception):
    def __init__(self, status, message):
        super().__init__("SYNHOSTILE " + message)
        self.status_code = status
        self.body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}


def test_J12_a_400_usage_limits_answer_stops_the_run_with_no_retry_and_no_text():
    from voc.replay import StopRun

    client = RawClient(error=_Refused(400, "You have reached your specified workspace API usage limits. SYNHOSTILE"))
    with pytest.raises(StopRun) as caught:
        _backend(client)("a synthetic prompt", SETTINGS)
    assert str(caught.value) == "the workspace's spend limit was reached (HTTP 400), so the run stops"
    assert caught.value.reason == "spend_limit"
    assert client.calls == 1 and "SYNHOSTILE" not in str(caught.value)


def test_J12_another_400_is_refused_but_does_not_count_as_the_spend_limit():
    from voc.replay import StopRun

    with pytest.raises(PermanentModelError) as caught:
        _backend(RawClient(error=_Refused(400, "prompt is too long SYNHOSTILE")))("a synthetic prompt", SETTINGS)
    assert not isinstance(caught.value, StopRun) and "SYNHOSTILE" not in str(caught.value)


def test_J12_the_caller_passes_a_stop_up_at_once_and_records_nothing(tmp_path):
    from voc.replay import Caller, StopRun

    class FakeLedger:
        def __init__(self):
            self.settled = []

        def reserve(self, tokens):
            return "r"

        def settle(self, rid, used):
            self.settled.append(used)

    calls = []

    def backend(prompt, settings):
        calls.append(prompt)
        raise StopRun("the workspace's spend limit was reached (HTTP 400), so the run stops")

    ledger = FakeLedger()
    caller = Caller("api", "claude-haiku-5-5", SETTINGS, backend=backend, root=tmp_path, ledger=ledger,
                    recordings=tmp_path / "recordings", config={"input_margin_tokens": 100})
    with pytest.raises(StopRun):
        caller.call("a synthetic prompt")
    assert len(calls) == 1 and ledger.settled == [None] and not (tmp_path / "recordings").exists()


def test_J12_the_labeller_stops_the_whole_run_on_the_first_stop():
    from voc import pipeline
    from voc.labels import load_labels
    from voc.pipeline import Complaint, RunStopped
    from voc.replay import StopRun
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    version = pipeline.load_prompt_version(root, "v1")
    labels = load_labels(root / "config" / "labels.toml")
    complaints = [Complaint(f"SYN-{i}", f"a synthetic complaint about a mortgage escrow account {i}") for i in (1, 2, 3)]

    def call(prompt):
        raise StopRun("the workspace's spend limit was reached (HTTP 400), so the run stops")

    with pytest.raises(RunStopped) as caught:
        pipeline.label_complaints(complaints, version, labels, call, "api")
    assert len(caught.value.outcomes) == 1 and caught.value.not_tried == 2
    assert "spend limit" in str(caught.value)


def test_J11_without_a_workspace_the_laptop_backend_is_unchanged():
    client = RawClient()
    client.messages = SimpleNamespace(create=lambda **kwargs: _response())
    answer = make_backend("api", env={"ANTHROPIC_API_KEY": _fake_key()}, model="claude-haiku-5-5",
                          client_factory=client)("a synthetic prompt", SETTINGS)
    assert answer.text == '{"label": "Mortgage"}'


def test_B21_a_stop_is_a_model_error_so_every_handler_of_one_still_catches_it():
    from voc.replay import StopRun

    assert issubclass(StopRun, PermanentModelError) and issubclass(StopRun, ModelError)


# The review of #111, nit 6 (owner decision: fixed in 6b, part 4).


@pytest.mark.parametrize("workspace", ["", "   "])
def test_J11_an_empty_workspace_id_is_refused_when_the_backend_is_made(workspace):
    from voc.backends import BackendError

    with pytest.raises(BackendError, match="^the cloud workspace's ID is empty$"):
        make_backend("api", env={"ANTHROPIC_API_KEY": _fake_key()}, model="claude-haiku-5-5",
                     client_factory=RawClient(), workspace=workspace)
