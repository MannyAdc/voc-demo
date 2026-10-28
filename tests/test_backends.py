"""B12: the backend switch. `api` calls Claude, `mock` serves fixtures. Nothing else exists.

No test calls the network: the `api` backend is built with a fake client.
Fake keys are built while the test runs, never written as one string.
"""
from types import SimpleNamespace

import pytest

from voc.backends import API_VERSION, BackendError, make_backend, run_settings
from voc.env import settings
from voc.replay import Answer, ModelError


def _fake_key():
    return "sk-" + "ant-" + "api03-" + "Z" * 40


class FakeClient:
    """Stands in for `anthropic.Anthropic`. It records what it was given."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.made_with, self.sent = response, error, None, None
        self.messages = SimpleNamespace(create=self._create)

    def __call__(self, **kwargs):
        self.made_with = kwargs
        return self

    def _create(self, **kwargs):
        self.sent = kwargs
        if self.error:
            raise self.error
        return self.response


def _response(blocks, stop_reason="end_turn", input_tokens=120, output_tokens=30, cache_read=0, cache_write=0):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                            cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write)
    return SimpleNamespace(content=blocks, stop_reason=stop_reason, usage=usage)


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _api(client, env=None):
    env = {"ANTHROPIC_API_KEY": _fake_key()} if env is None else env
    return make_backend("api", env=env, model="claude-haiku-5-5", client_factory=client)


def test_B12_mock_serves_its_fixtures_and_nothing_else():
    answer = Answer(text='{"label": "Mortgage", "quote": "a b c"}', input_tokens=10, output_tokens=5,
                    stop_reason="end_turn")
    backend = make_backend("mock", fixtures={"the prompt": answer})
    assert backend("the prompt", {}) == answer
    with pytest.raises(ModelError):
        backend("another prompt", {})


@pytest.mark.parametrize("name", ["cli", "claude", "", "API"])
def test_B12_an_unknown_backend_is_an_error_that_names_the_allowed_values(name):
    with pytest.raises(BackendError) as err:
        make_backend(name, env={})
    assert "api" in str(err.value) and "mock" in str(err.value)


def test_B12_api_with_no_key_in_the_environment_fails_with_a_clear_message():
    with pytest.raises(BackendError, match="ANTHROPIC_API_KEY is not set"):
        _api(FakeClient(), env={})


def test_B12_api_reads_the_key_only_from_the_environment_and_an_empty_env_file_gives_none(tmp_path):
    (tmp_path / ".env").write_text("# nothing here\n", encoding="utf-8")
    with pytest.raises(BackendError, match="ANTHROPIC_API_KEY is not set"):
        _api(FakeClient(), env=settings({}, tmp_path))


def test_B12_the_client_is_made_with_the_key_and_sdk_retries_off():
    client = FakeClient(_response([_text("ok")]))
    _api(client)("prompt", run_settings())
    assert client.made_with["api_key"] == _fake_key()
    assert client.made_with["max_retries"] == 0


def test_B12_the_key_never_appears_in_an_error_message():
    key = _fake_key()
    client = FakeClient(error=RuntimeError(f"auth failed for {key} at https://example.invalid"))
    with pytest.raises(ModelError) as err:
        _api(client, env={"ANTHROPIC_API_KEY": key})("prompt", run_settings())
    assert key not in str(err.value) and "RuntimeError" in str(err.value)


def test_B12_the_request_holds_model_effort_thinking_and_no_sampling_settings():
    client = FakeClient(_response([_text("ok")]))
    _api(client)("the complaint prompt", run_settings())
    sent = client.sent
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["messages"] == [{"role": "user", "content": "the complaint prompt"}]
    assert sent["output_config"] == {"effort": "low"}
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["max_tokens"] == run_settings()["max_tokens"]
    assert not {"temperature", "top_p", "top_k", "system", "tools"} & set(sent)


def test_B12_the_answer_text_is_the_text_blocks_and_thinking_is_left_out():
    blocks = [SimpleNamespace(type="thinking", thinking=""), _text('{"label": '), _text('"Mortgage", "quote": "x"}')]
    answer = _api(FakeClient(_response(blocks)))("prompt", run_settings())
    assert answer.text == '{"label": "Mortgage", "quote": "x"}'


def test_B12_input_tokens_include_cached_input():
    response = _response([_text("ok")], input_tokens=100, output_tokens=20, cache_read=30, cache_write=7)
    answer = _api(FakeClient(response))("prompt", run_settings())
    assert answer.input_tokens == 137 and answer.output_tokens == 20


@pytest.mark.parametrize("stop", ["end_turn", "max_tokens", "refusal"])
def test_B12_the_stop_reason_is_passed_on(stop):
    assert _api(FakeClient(_response([_text("ok")], stop_reason=stop)))("prompt", run_settings()).stop_reason == stop


def test_B12_each_run_records_the_model_effort_thinking_and_api_version():
    recorded = run_settings()
    assert recorded["effort"] == "low" and recorded["thinking"] == "adaptive"
    assert recorded["api_version"] == API_VERSION == "2023-06-01"
    assert "temperature" not in recorded


# Review of pull request #14


@pytest.mark.parametrize("variable", ["ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_LOG"])
def test_B12_sdk_environment_overrides_are_refused(variable, monkeypatch):
    # The SDK reads these itself: they could send the key elsewhere, change the API version, or log prompts.
    monkeypatch.setenv(variable, "set")
    with pytest.raises(BackendError, match=variable):
        _api(FakeClient(_response([_text("ok")])))


def test_B12_the_client_is_pinned_to_the_anthropic_address_and_the_recorded_api_version():
    client = FakeClient(_response([_text("ok")]))
    _api(client)("prompt", run_settings())
    assert client.made_with["base_url"] == "https://api.anthropic.com"
    assert client.made_with["default_headers"] == {"anthropic-version": API_VERSION}


def test_B12_the_recorded_api_version_is_the_installed_sdks_own():
    import anthropic._constants

    assert API_VERSION == anthropic._constants.ANTHROPIC_API_VERSION


def test_B12_the_real_client_is_built_offline_with_retries_off_and_the_fixed_address():
    from voc.backends import _anthropic_client

    client = _anthropic_client(api_key=_fake_key(), max_retries=0, base_url="https://api.anthropic.com",
                               default_headers={"anthropic-version": API_VERSION})
    assert client.max_retries == 0
    assert str(client.base_url).rstrip("/") == "https://api.anthropic.com"


def test_B12_an_sdk_error_keeps_no_trace_of_the_original_exception():
    key = _fake_key()
    with pytest.raises(ModelError) as err:
        _api(FakeClient(error=RuntimeError(f"bad {key}")), env={"ANTHROPIC_API_KEY": key})("prompt", run_settings())
    assert err.value.__context__ is None and err.value.__cause__ is None


def test_B12_an_answer_with_no_text_is_a_model_error():
    blocks = [SimpleNamespace(type="thinking", thinking="")]
    with pytest.raises(ModelError):
        _api(FakeClient(_response(blocks)))("prompt", run_settings())


def test_B12_an_answer_holds_only_text_tokens_and_the_stop_reason():
    answer = _api(FakeClient(_response([_text("ok")])))("prompt", run_settings())
    assert set(vars(answer)) == {"text", "input_tokens", "output_tokens", "stop_reason"}


def test_B12_each_run_records_the_model_too():
    assert run_settings(model="claude-haiku-5-5")["model"] == "claude-haiku-5-5"


# Smoke test of 28 October: every call failed, the cause was hidden, and every failure was retried


def _sdk_error(name, status=None):
    """An exception shaped like an SDK error: its class name, and the HTTP status if it has one."""
    err = type(name, (Exception,), {})("SYN detail that must never be echoed")
    if status is not None:
        err.status_code = status
    return err


@pytest.mark.parametrize("name, status", [("AuthenticationError", 401), ("BadRequestError", 400),
                                          ("PermissionDeniedError", 403), ("NotFoundError", 404)])
def test_B8_a_refused_call_is_marked_not_worth_retrying_and_names_its_type_and_status(name, status):
    from voc.replay import PermanentModelError

    with pytest.raises(PermanentModelError) as err:
        _api(FakeClient(error=_sdk_error(name, status)))("prompt", run_settings())
    assert name in str(err.value) and f"HTTP {status}" in str(err.value) and "SYN detail" not in str(err.value)


@pytest.mark.parametrize("name, status", [("APIConnectionError", None), ("APITimeoutError", None),
                                          ("RateLimitError", 429), ("InternalServerError", 500),
                                          ("OverloadedError", 529)])
def test_B8_a_failure_a_retry_can_fix_stays_a_plain_model_error(name, status):
    from voc.replay import PermanentModelError

    with pytest.raises(ModelError) as err:
        _api(FakeClient(error=_sdk_error(name, status)))("prompt", run_settings())
    assert not isinstance(err.value, PermanentModelError)
    assert name in str(err.value) and "SYN detail" not in str(err.value)


def test_B8_an_answer_with_no_text_is_not_worth_retrying_and_names_its_stop_reason():
    from voc.replay import PermanentModelError

    blocks = [SimpleNamespace(type="thinking", thinking="")]
    with pytest.raises(PermanentModelError, match="max_tokens"):
        _api(FakeClient(_response(blocks, stop_reason="max_tokens")))("prompt", run_settings())
