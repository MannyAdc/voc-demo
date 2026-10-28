"""B12: the backend switch. `LLM_BACKEND` is `api` or `mock`. Any other value is an error.

`api` calls Claude through the Anthropic Python SDK. The key comes only from
the environment (the command line may load a git-ignored `.env` first), and
never appears in an error. SDK retries are off: a retry is a new call through
the ledger (B8). No temperature or other sampling setting is sent, because API
version 2026-10-21 refuses them and Claude 4.7 and later models accept only
the defaults. Everything sent is in the prompt or the settings, so the ledger
estimate and the recording key both see it.

`mock` serves recorded fixtures only and never uses the network.
"""
import os

from voc.replay import Answer, ModelError, PermanentModelError, SDK_MAX_RETRIES, _stop_name

ALLOWED = ("api", "mock")
DEFAULT_MODEL = "claude-haiku-5-5"
# The API version the pinned SDK (anthropic 1.13.0) sends.
API_VERSION = "2023-06-01"
BASE_URL = "https://api.anthropic.com"
# The SDK reads these itself. They could send the key elsewhere, change the API version or log prompts.
REFUSED_VARIABLES = ("ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_LOG")
# Failures a retry can fix: no connection, a timeout, a rate limit, an overloaded or failing server.
# Any other failure (a refused key, no credit, a bad request, an unknown model) is never retried.
RETRY_ERRORS = frozenset({"APIConnectionError", "APITimeoutError"})
RETRY_STATUSES = frozenset({408, 409, 429})


class BackendError(ValueError):
    pass


def run_settings(effort="low", thinking="adaptive", max_tokens=2048, model=DEFAULT_MODEL):
    """The settings of a prompt version. They are recorded with each run (B12, B15)."""
    return {"model": model, "effort": effort, "thinking": thinking, "max_tokens": max_tokens,
            "api_version": API_VERSION}


def _failure(err):
    """Our own message for an SDK error: its type and HTTP status only, never its text (B21)."""
    name = type(err).__name__
    status = getattr(err, "status_code", None)
    status = status if isinstance(status, int) and not isinstance(status, bool) else None
    names = {cls.__name__ for cls in type(err).__mro__}
    retry = bool(names & RETRY_ERRORS) or status in RETRY_STATUSES or (status is not None and status >= 500)
    if retry:
        return ModelError(f"the API call failed: {name}" + (f" (HTTP {status})" if status else ""))
    return PermanentModelError(f"the API refused the call: {name}" + (f" (HTTP {status})" if status else ""))


def _anthropic_client(**kwargs):
    import anthropic  # imported only when the api backend is made, so mock runs never load the SDK

    return anthropic.Anthropic(**kwargs)


def _mock(fixtures):
    def backend(prompt, settings):
        if prompt not in fixtures:
            raise ModelError("the mock backend has no fixture for this prompt")
        return fixtures[prompt]
    return backend


def _api(env, model, client_factory):
    for name in REFUSED_VARIABLES:
        if os.environ.get(name):
            raise BackendError(f"{name} is set, so the api backend refuses to run. Unset it first.")
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        raise BackendError("ANTHROPIC_API_KEY is not set in the environment")
    client = client_factory(api_key=key, max_retries=SDK_MAX_RETRIES, base_url=BASE_URL,
                            default_headers={"anthropic-version": API_VERSION})

    def backend(prompt, settings):
        failure = None
        try:
            response = client.messages.create(
                model=model,
                max_tokens=settings["max_tokens"],
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": settings["effort"]},
                thinking={"type": settings["thinking"]},
            )
        except Exception as err:  # the SDK error holds the request, and so the key: keep only its type
            failure = _failure(err)
        if failure:
            raise failure
        usage = response.usage
        cached = (getattr(usage, "cache_read_input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        if not text.strip():
            raise PermanentModelError(f"the answer held no text, stop reason {_stop_name(response.stop_reason)}")
        return Answer(text=text, input_tokens=usage.input_tokens + cached, output_tokens=usage.output_tokens,
                      stop_reason=response.stop_reason)
    return backend


def make_backend(name, env=None, model=DEFAULT_MODEL, fixtures=None, client_factory=_anthropic_client):
    if name not in ALLOWED:
        raise BackendError(f"unknown LLM_BACKEND {name!r}, allowed values are {', '.join(ALLOWED)}")
    if name == "mock":
        return _mock(fixtures or {})
    return _api(env or {}, model, client_factory)
