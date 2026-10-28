"""B7 and B8: record and replay of model answers.

Every test runs with a fake home folder in a tmp folder, so the real
recordings and ledger are never touched. Backends are fake functions.
Nothing here opens a network connection.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

CAP = 1_000
SETTINGS = {"max_tokens": 50, "temperature": 0}
PROMPT = "SYN classify this synthetic complaint"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """A fake home folder for every test, so the real one is never used."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def budget():
    from voc import budget
    return budget


@pytest.fixture
def replay():
    from voc import replay
    return replay


def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-c", "user.name=synthetic", "-c", "user.email=synthetic@example.invalid",
                    "-c", "commit.gpgsign=false", *args],
                   cwd=repo, env=env, check=True, capture_output=True)


def _make_repo(path):
    (path / "config").mkdir(parents=True)
    (path / "config" / "budget.toml").write_text(f"cap_tokens = {CAP}\ninput_margin_tokens = 100\n",
                                                 encoding="utf-8")
    _git(path, "init", "-q", "-b", "main")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "Start")
    _git(path, "update-ref", "refs/remotes/origin/main", "refs/heads/main")
    return path


@pytest.fixture
def repo(tmp_path):
    return _make_repo(tmp_path / "repo")


@pytest.fixture
def ledger(budget, repo):
    budget.init_ledger(repo)
    return budget.Ledger()


class FakeBackend:
    """Counts its calls and returns a fixed answer."""

    def __init__(self, replay, text='{"label": "x", "quote": "y"}', stop="end_turn", fail=None):
        self.answer = replay.Answer(text=text, input_tokens=30, output_tokens=7, stop_reason=stop)
        self.fail = fail
        self.calls = 0

    def __call__(self, prompt, settings):
        self.calls += 1
        if self.fail:
            raise self.fail
        return self.answer


def _caller(replay, repo, backend, mode="live", backend_name="fake", model="synthetic-model", settings=None):
    return replay.Caller(backend_name=backend_name, model=model, settings=settings or SETTINGS,
                         backend=backend, mode=mode, root=repo)


def _recording_files(home):
    folder = home / ".voc" / "recordings"
    return sorted(p for p in folder.rglob("*") if p.is_file()) if folder.exists() else []


def test_B7_the_key_is_a_stable_hash_of_backend_model_settings_and_prompt(replay):
    material = {"backend": "fake", "model": "synthetic-model", "prompt": PROMPT,
                "settings": {"max_tokens": 50, "temperature": 0}}
    expected = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()
    key = replay.recording_key("fake", "synthetic-model", {"temperature": 0, "max_tokens": 50}, PROMPT)
    assert key == expected
    assert key == replay.recording_key("fake", "synthetic-model", {"max_tokens": 50, "temperature": 0}, PROMPT)


def test_B7_first_call_is_live_second_comes_from_the_recording(replay, repo, ledger):
    backend = FakeBackend(replay)
    caller = _caller(replay, repo, backend)
    first = caller.call(PROMPT)
    second = caller.call(PROMPT)
    assert (first.source, second.source) == ("live", "replay")
    assert first.text == second.text
    assert backend.calls == 1


def test_B7_replay_mode_serves_a_recording_with_no_inner_client(replay, repo, ledger):
    _caller(replay, repo, FakeBackend(replay)).call(PROMPT)
    reply = _caller(replay, repo, None, mode="replay").call(PROMPT)
    assert reply.source == "replay"
    assert reply.text == '{"label": "x", "quote": "y"}'


def test_B7_replay_mode_with_no_recording_is_an_error_not_a_live_call(replay, repo, ledger):
    backend = FakeBackend(replay)
    with pytest.raises(replay.RecordingMissing):
        _caller(replay, repo, backend, mode="replay").call(PROMPT)
    assert backend.calls == 0


@pytest.mark.parametrize("change", [
    {"backend_name": "other"},
    {"model": "other-model"},
    {"settings": {"max_tokens": 50, "temperature": 1}},
    {"settings": {"max_tokens": 51, "temperature": 0}},
    {"prompt": PROMPT + " "},
])
def test_B7_a_different_backend_model_setting_or_prompt_is_not_served_the_old_recording(replay, repo, ledger, change):
    _caller(replay, repo, FakeBackend(replay)).call(PROMPT)
    prompt = change.pop("prompt", PROMPT)
    with pytest.raises(replay.RecordingMissing):
        _caller(replay, repo, None, mode="replay", **change).call(prompt)


def test_B7_a_recording_file_holds_no_headers_and_no_key(replay, repo, ledger, home, monkeypatch):
    fake_key = "sk-" + "ant-" + "SYN" + "q" * 24
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_key)
    _caller(replay, repo, FakeBackend(replay)).call(PROMPT)
    files = _recording_files(home)
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert fake_key not in text
    assert "header" not in text.lower()
    assert set(json.loads(text)) == {"key", "key_material", "text", "usage", "live_cost_tokens"}


def test_B7_recordings_are_stored_in_the_home_folder_cache_so_a_second_worktree_replays_them_free(
        budget, replay, repo, ledger, home, tmp_path, monkeypatch):
    _caller(replay, repo, FakeBackend(replay)).call(PROMPT)
    assert len(_recording_files(home)) == 1
    assert replay.recordings_dir() == home / ".voc" / "recordings"
    second = _make_repo(tmp_path / "second_worktree")
    monkeypatch.chdir(second)
    used = budget.Ledger().state()["used"]
    backend = FakeBackend(replay)
    reply = _caller(replay, second, backend).call(PROMPT)
    assert reply.source == "replay"
    assert backend.calls == 0
    assert budget.Ledger().state()["used"] == used


@pytest.mark.parametrize("backend_args", [
    {"fail": ConnectionError("synthetic failure")},
    {"stop": "refusal"},
    {"stop": "max_tokens"},
])
def test_B7_a_failed_refused_or_cut_off_call_is_not_stored_in_the_cache(replay, repo, ledger, home, backend_args):
    with pytest.raises(replay.ModelError):
        _caller(replay, repo, FakeBackend(replay, **backend_args)).call(PROMPT)
    assert _recording_files(home) == []
    with pytest.raises(replay.RecordingMissing):
        _caller(replay, repo, None, mode="replay").call(PROMPT)


def test_B8_a_live_call_is_charged_a_replayed_call_is_free(budget, replay, repo, ledger):
    caller = _caller(replay, repo, FakeBackend(replay))
    live = caller.call(PROMPT)
    assert live.charged_tokens == 37
    assert budget.Ledger().state()["used"] == 37
    again = caller.call(PROMPT)
    assert again.charged_tokens == 0
    assert again.live_cost_tokens == 37
    assert budget.Ledger().state()["used"] == 37


def test_B8_a_live_call_past_the_cap_is_refused_before_it_is_sent(budget, replay, repo):
    budget.init_ledger(repo, cap=10)
    backend = FakeBackend(replay)
    with pytest.raises(budget.CapReached):
        _caller(replay, repo, backend).call(PROMPT)
    assert backend.calls == 0
    assert budget.Ledger().state()["used"] == 0


def test_B8_a_recording_is_still_served_when_the_budget_is_spent(budget, replay, repo, ledger):
    _caller(replay, repo, FakeBackend(replay)).call(PROMPT)
    spent = budget.Ledger()
    spent.reserve(CAP - spent.state()["used"])
    with pytest.raises(budget.CapReached):
        spent.reserve(1)
    backend = FakeBackend(replay)
    reply = _caller(replay, repo, backend).call(PROMPT)
    assert reply.source == "replay"
    assert backend.calls == 0


# Review round 1 on PR #13


def test_B7_settings_with_a_tuple_are_served_from_the_recording(replay, repo, ledger):
    settings = {"max_tokens": 50, "stop_sequences": ("SYN-END",), "temperature": 0}
    backend = FakeBackend(replay)
    caller = _caller(replay, repo, backend, settings=settings)
    caller.call(PROMPT)
    second = caller.call(PROMPT)
    assert second.source == "replay"
    assert backend.calls == 1
    assert _caller(replay, repo, None, mode="replay", settings=settings).call(PROMPT).source == "replay"


def test_B21_an_unknown_stop_reason_is_never_echoed_in_the_error(replay, repo, ledger):
    with pytest.raises(replay.ModelError) as caught:
        _caller(replay, repo, FakeBackend(replay, stop="SYN leaked model words")).call(PROMPT)
    assert "SYN leaked" not in str(caught.value)
    assert "other" in str(caught.value)


def test_B21_a_known_stop_reason_is_named_in_the_error(replay, repo, ledger):
    with pytest.raises(replay.ModelError) as caught:
        _caller(replay, repo, FakeBackend(replay, stop="refusal")).call(PROMPT)
    assert "refusal" in str(caught.value)


def _corrupt(home, kind):
    [path] = _recording_files(home)
    if kind == "not json":
        path.write_text("not json {", encoding="utf-8")
        return
    record = json.loads(path.read_text(encoding="utf-8"))
    if kind == "no usage":
        del record["usage"]
    elif kind == "usage is null":
        record["usage"] = {"input_tokens": None, "output_tokens": 7}
    elif kind == "other prompt":
        record["key_material"]["prompt"] = "SYN some other prompt"
    path.write_text(json.dumps(record), encoding="utf-8")


@pytest.mark.parametrize("mode", ["live", "replay"])
@pytest.mark.parametrize("kind", ["not json", "no usage", "usage is null", "other prompt"])
def test_B7_a_corrupt_recording_is_an_error_not_a_silent_paid_call(budget, replay, repo, ledger, home, mode, kind):
    _caller(replay, repo, FakeBackend(replay)).call(PROMPT)
    _corrupt(home, kind)
    used = budget.Ledger().state()["used"]
    backend = FakeBackend(replay)
    with pytest.raises(replay.RecordingCorrupt):
        _caller(replay, repo, backend, mode=mode).call(PROMPT)
    assert backend.calls == 0
    assert budget.Ledger().state()["used"] == used


class LeakyAnswer:
    """A backend answer that also carries headers and a key-like value."""

    def __init__(self, key):
        self.text = '{"label": "x", "quote": "y"}'
        self.input_tokens = 30
        self.output_tokens = 7
        self.stop_reason = "end_turn"
        self.headers = {"x-api-key": key, "authorization": "Bearer " + key}
        self.api_key = key
        self.request = {"headers": {"x-api-key": key}}


def test_B7_headers_and_keys_on_a_backend_answer_never_reach_the_recording(replay, repo, ledger, home):
    fake_key = "sk-" + "ant-" + "api03-" + "SYN" + "z" * 30
    _caller(replay, repo, lambda p, s: LeakyAnswer(fake_key)).call(PROMPT)
    [path] = _recording_files(home)
    text = path.read_text(encoding="utf-8")
    assert fake_key not in text
    assert "header" not in text.lower()
    assert "bearer" not in text.lower()
    assert "api_key" not in text


# Smoke test of 28 October: the cause was hidden, and failures that cannot pass were retried


def test_B7_a_failure_a_retry_cannot_fix_is_tried_once_and_named(replay, repo, ledger):
    backend = FakeBackend(replay, fail=replay.PermanentModelError(
        "the API refused the call: AuthenticationError (HTTP 401)"))
    with pytest.raises(replay.ModelError) as err:
        _caller(replay, repo, backend).call(PROMPT)
    assert backend.calls == 1 and "AuthenticationError (HTTP 401)" in str(err.value)


def test_B7_the_last_error_keeps_our_own_message(replay, repo, ledger):
    backend = FakeBackend(replay, fail=replay.ModelError("the API call failed: RateLimitError (HTTP 429)"))
    with pytest.raises(replay.ModelError) as err:
        _caller(replay, repo, backend).call(PROMPT)
    assert backend.calls == 3 and "RateLimitError (HTTP 429)" in str(err.value)


def test_B21_any_other_error_is_still_named_by_its_type_only(replay, repo, ledger):
    backend = FakeBackend(replay, fail=RuntimeError("SYNHOSTILE raw backend text"))
    with pytest.raises(replay.ModelError) as err:
        _caller(replay, repo, backend).call(PROMPT)
    assert "SYNHOSTILE" not in str(err.value) and "RuntimeError" in str(err.value)
