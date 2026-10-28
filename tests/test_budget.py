"""B8: the token ledger.

Every test runs with a fake home folder in a tmp folder, so the real ledger
is never touched. The cap config lives in a small tmp git repo. Backends are
fake functions. Nothing here opens a network connection.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CAP = 1_000
MARGIN = 100
OUTPUT_LIMIT = 50
SETTINGS = {"max_tokens": OUTPUT_LIMIT, "temperature": 0}
SRC = Path(__file__).resolve().parents[1] / "src"


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


def _config(cap, margin=MARGIN):
    return f"cap_tokens = {cap}\ninput_margin_tokens = {margin}\n"


def _write_config(repo, cap, commit):
    (repo / "config" / "budget.toml").write_text(_config(cap), encoding="utf-8")
    if commit:
        _git(repo, "commit", "-q", "-am", f"Set cap to {cap}")


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "budget.toml").write_text(_config(CAP), encoding="utf-8")
    (repo / "BUILD_LOG.md").write_text("# Build log\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "Start")
    return repo


@pytest.fixture
def ledger(budget, repo):
    budget.init_ledger(repo)
    return budget.Ledger()


def _answer(replay, text='{"label": "x", "quote": "y"}', input_tokens=30, output_tokens=7, stop="end_turn"):
    return replay.Answer(text=text, input_tokens=input_tokens, output_tokens=output_tokens, stop_reason=stop)


def _caller(replay, repo, backend, **kwargs):
    return replay.Caller(backend_name="fake", model="synthetic-model", settings=SETTINGS,
                         backend=backend, root=repo, **kwargs)


def _worst_case(prompt):
    return len(prompt.encode("utf-8")) + MARGIN + OUTPUT_LIMIT


def test_B8_init_creates_a_ledger_that_has_used_nothing(budget, ledger):
    state = ledger.state()
    assert state["used"] == 0
    assert state["reserved"] == 0
    assert state["cap"] == CAP


def test_B8_missing_ledger_refuses_every_live_call(budget, repo):
    with pytest.raises(budget.BudgetError):
        budget.Ledger().reserve(10)


def test_B8_unreadable_ledger_refuses_every_live_call(budget, ledger):
    budget.ledger_path().write_text("not json {", encoding="utf-8")
    with pytest.raises(budget.BudgetError):
        ledger.reserve(10)


def test_B8_missing_ledger_stops_a_live_call_before_it_is_sent(budget, replay, repo):
    sent = []
    caller = _caller(replay, repo, lambda prompt, settings: sent.append(prompt) or _answer(replay))
    with pytest.raises(budget.BudgetError):
        caller.call("SYN prompt")
    assert sent == []


def test_B8_charges_add_up(ledger):
    for real in (10, 20, 30):
        ledger.settle(ledger.reserve(100), real)
    assert ledger.state()["used"] == 60
    assert ledger.state()["reserved"] == 0


def test_B8_use_survives_a_restart(budget, ledger):
    ledger.settle(ledger.reserve(100), 40)
    ledger.reserve(25)
    again = budget.Ledger()
    assert again.state()["used"] == 40
    assert again.state()["reserved"] == 25


def test_B8_a_reservation_that_just_fits_is_allowed_one_more_token_is_refused(budget, ledger):
    ledger.settle(ledger.reserve(400), 400)
    ledger.reserve(CAP - 400)
    with pytest.raises(budget.CapReached):
        ledger.reserve(1)
    assert ledger.state()["used"] + ledger.state()["reserved"] == CAP


def test_B8_reservation_is_input_estimate_plus_output_limit(budget):
    prompt = "SYN café ’quote’"
    size = len(prompt.encode("utf-8"))
    assert size > len(prompt)
    assert budget.input_estimate(prompt, MARGIN) == size + MARGIN
    assert budget.worst_case(prompt, OUTPUT_LIMIT, MARGIN) == size + MARGIN + OUTPUT_LIMIT


def test_B8_a_live_call_reserves_the_worst_case(budget, replay, repo, ledger):
    prompt = "SYN a prompt with café"
    seen = []

    def backend(p, settings):
        seen.append(budget.Ledger().state()["reserved"])
        return _answer(replay)

    _caller(replay, repo, backend).call(prompt)
    assert seen == [_worst_case(prompt)]


def test_B8_the_cap_is_copied_into_the_ledger_at_init(budget, repo, ledger):
    _write_config(repo, 5_000, commit=True)
    assert budget.Ledger().state()["cap"] == CAP


def test_B8_an_override_at_init_can_lower_the_cap(budget, repo):
    budget.init_ledger(repo, cap=400)
    assert budget.Ledger().state()["cap"] == 400


def test_B8_an_override_at_init_cannot_raise_the_cap(budget, repo):
    with pytest.raises(budget.BudgetError):
        budget.init_ledger(repo, cap=CAP + 1)
    assert not budget.ledger_path().exists()


def test_B8_live_calls_are_refused_while_the_cap_config_has_uncommitted_changes(budget, replay, repo, ledger):
    _write_config(repo, 5_000, commit=False)
    sent = []
    caller = _caller(replay, repo, lambda prompt, settings: sent.append(prompt) or _answer(replay))
    with pytest.raises(budget.BudgetError):
        caller.call("SYN prompt")
    assert sent == []
    _git(repo, "commit", "-q", "-am", "Commit the cap")
    assert caller.call("SYN prompt").text


def test_B8_a_cap_config_that_is_not_in_git_counts_as_uncommitted(budget, tmp_path):
    folder = tmp_path / "not_a_repo"
    (folder / "config").mkdir(parents=True)
    (folder / "config" / "budget.toml").write_text(_config(CAP), encoding="utf-8")
    with pytest.raises(budget.BudgetError):
        budget.require_clean_config(folder)


def test_B8_the_ledger_path_is_the_fixed_path_in_the_home_folder(budget, repo, home, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert budget.ledger_path() == home / ".voc" / "ledger.json"
    budget.init_ledger(repo)
    assert (home / ".voc" / "ledger.json").is_file()
    assert not (elsewhere / ".voc").exists()
    assert not (repo / ".voc").exists()


def test_B8_init_refuses_when_a_ledger_already_exists(budget, ledger, repo):
    ledger.settle(ledger.reserve(100), 70)
    with pytest.raises(budget.BudgetError):
        budget.init_ledger(repo)
    assert budget.Ledger().state()["used"] == 70


def test_B8_raise_refuses_while_the_cap_config_has_uncommitted_changes(budget, ledger, repo):
    _write_config(repo, 5_000, commit=False)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN more runs needed")
    assert budget.Ledger().state()["cap"] == CAP
    assert "SYN more runs needed" not in (repo / "BUILD_LOG.md").read_text(encoding="utf-8")


def test_B8_raise_writes_a_raise_event_with_a_reason(budget, ledger, repo):
    _write_config(repo, 5_000, commit=True)
    budget.raise_cap(repo, reason="SYN more runs needed")
    state = budget.Ledger().state()
    assert state["cap"] == 5_000
    event = state["events"][-1]
    assert event["type"] == "raise"
    assert (event["from"], event["to"], event["reason"]) == (CAP, 5_000, "SYN more runs needed")
    log = (repo / "BUILD_LOG.md").read_text(encoding="utf-8")
    assert "SYN more runs needed" in log
    assert "5,000" in log or "5000" in log


def test_B8_raise_needs_a_reason_and_a_higher_cap(budget, ledger, repo):
    _write_config(repo, 5_000, commit=True)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="  ")
    _write_config(repo, CAP, commit=True)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN not higher")
    assert budget.Ledger().state()["cap"] == CAP


def test_B8_sdk_retries_are_off_and_a_retry_is_charged_as_a_new_call(budget, replay, repo, ledger):
    assert replay.SDK_MAX_RETRIES == 0
    prompt = "SYN retry prompt"
    attempts = []

    def flaky(p, settings):
        attempts.append(p)
        if len(attempts) == 1:
            raise TimeoutError("synthetic timeout")
        return _answer(replay, input_tokens=30, output_tokens=7)

    reply = _caller(replay, repo, flaky).call(prompt)
    assert reply.attempts == 2
    state = budget.Ledger().state()
    assert state["calls"] == 2
    assert state["used"] == _worst_case(prompt) + 37


def test_B8_a_failed_call_is_retried_at_most_2_times(budget, replay, repo, ledger):
    attempts = []

    def broken(p, settings):
        attempts.append(p)
        raise ConnectionError("synthetic failure")

    with pytest.raises(replay.ModelError):
        _caller(replay, repo, broken).call("SYN broken prompt")
    assert len(attempts) == 3
    assert budget.Ledger().state()["calls"] == 3


def test_B8_after_a_call_the_reservation_is_replaced_by_the_real_use(budget, replay, repo, ledger):
    _caller(replay, repo, lambda p, s: _answer(replay, input_tokens=30, output_tokens=7)).call("SYN prompt")
    state = budget.Ledger().state()
    assert state["used"] == 37
    assert state["reserved"] == 0


def test_B8_a_failed_call_is_charged_the_full_reservation(budget, replay, repo, ledger):
    prompt = "SYN failing prompt"

    def broken(p, settings):
        raise ConnectionError("synthetic failure")

    with pytest.raises(replay.ModelError):
        _caller(replay, repo, broken).call(prompt)
    state = budget.Ledger().state()
    assert state["used"] == 3 * _worst_case(prompt)
    assert state["reserved"] == 0


def test_B8_a_call_with_no_reported_usage_is_charged_the_full_reservation(budget, replay, repo, ledger):
    prompt = "SYN prompt with no usage"
    backend = lambda p, s: _answer(replay, input_tokens=None, output_tokens=None)
    _caller(replay, repo, backend).call(prompt)
    state = budget.Ledger().state()
    assert state["used"] == _worst_case(prompt)
    assert state["reserved"] == 0


WORKER = """
import sys
from pathlib import Path
from voc.budget import CapReached, Ledger

ledger = Ledger(Path(sys.argv[1]))
start = Path(sys.argv[2])
while not start.exists():
    pass
won = 0
for _ in range(int(sys.argv[3])):
    try:
        ledger.reserve(1)
        won += 1
    except CapReached:
        pass
print(won)
"""


def test_B8_two_processes_reserving_at_once_cannot_both_pass_the_cap(budget, repo, home, tmp_path):
    budget.init_ledger(repo, cap=150)
    script = tmp_path / "worker.py"
    script.write_text(WORKER, encoding="utf-8")
    start = tmp_path / "start"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(PYTHONPATH=str(SRC), HOME=str(home), USERPROFILE=str(home))
    workers = [subprocess.Popen([sys.executable, str(script), str(budget.ledger_path()), str(start), "100"],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
               for _ in range(2)]
    start.write_text("go", encoding="utf-8")
    results = [w.communicate(timeout=120) for w in workers]
    assert [w.returncode for w in workers] == [0, 0], [err[-300:] for _, err in results]
    won = [int(out.strip()) for out, _ in results]
    assert sum(won) == 150
    assert budget.Ledger().state()["reserved"] == 150


def test_B8_a_negative_charge_is_an_error(budget, ledger):
    rid = ledger.reserve(100)
    with pytest.raises(budget.BudgetError):
        ledger.settle(rid, -1)
    with pytest.raises(budget.BudgetError):
        ledger.reserve(-1)
    state = ledger.state()
    assert (state["used"], state["reserved"]) == (0, 100)


def test_B8_cli_ledger_init_and_raise(budget, repo):
    from voc import cli

    assert cli.main(["ledger", "init"], env={}, root=repo) == 0
    assert budget.Ledger().state()["cap"] == CAP
    assert cli.main(["ledger", "init"], env={}, root=repo) == 1
    _write_config(repo, 5_000, commit=True)
    assert cli.main(["ledger", "raise", "--reason", "SYN more runs"], env={}, root=repo) == 0
    assert budget.Ledger().state()["cap"] == 5_000


def test_B8_the_committed_cap_config_is_valid(budget):
    root = Path(__file__).resolve().parents[1]
    config = budget.load_config(root)
    assert config["cap_tokens"] == 20_000_000
    assert config["input_margin_tokens"] > 0
