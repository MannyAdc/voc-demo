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
    return subprocess.run(["git", "-c", "user.name=synthetic", "-c", "user.email=synthetic@example.invalid",
                           "-c", "commit.gpgsign=false", *args],
                          cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _sync_origin(repo):
    """Stand in for a push: origin/main points at the local main."""
    _git(repo, "update-ref", "refs/remotes/origin/main", "refs/heads/main")


def _config(cap, margin=MARGIN):
    return f"cap_tokens = {cap}\ninput_margin_tokens = {margin}\n"


def _write_config(repo, cap, commit):
    (repo / "config" / "budget.toml").write_text(_config(cap), encoding="utf-8")
    if commit:
        _git(repo, "commit", "-q", "-am", f"Set cap to {cap}")
        _sync_origin(repo)


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "budget.toml").write_text(_config(CAP), encoding="utf-8")
    (repo / "BUILD_LOG.md").write_text("# Build log\n", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "Start")
    _sync_origin(repo)
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


# Review round 1 on PR #13


def _write_full_config(repo, cap, trial, confirmed, commit=True):
    text = (f"cap_tokens = {cap}\ninput_margin_tokens = {MARGIN}\n"
            f"trial_cap_tokens = {trial}\nmargin_confirmed = {'true' if confirmed else 'false'}\n")
    (repo / "config" / "budget.toml").write_text(text, encoding="utf-8")
    if commit:
        _git(repo, "commit", "-q", "-am", "Change the budget config")
        _sync_origin(repo)


def _throwaway_repo(tmp_path, cap):
    other = tmp_path / "throwaway"
    (other / "config").mkdir(parents=True)
    (other / "config" / "budget.toml").write_text(_config(cap), encoding="utf-8")
    (other / "BUILD_LOG.md").write_text("# Build log\n", encoding="utf-8")
    _git(other, "init", "-q", "-b", "main")
    _git(other, "add", ".")
    _git(other, "commit", "-q", "-m", "Start")
    return other


def _tamper(budget, change):
    path = budget.ledger_path()
    state = json.loads(path.read_text(encoding="utf-8"))
    change(state)
    path.write_text(json.dumps(state), encoding="utf-8")


def test_B8_raise_from_a_throwaway_repo_is_refused(budget, ledger, tmp_path):
    from voc import cli

    other = _throwaway_repo(tmp_path, 10 ** 12)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(other, reason="SYN throwaway try")
    assert cli.main(["ledger", "raise", "--reason", "SYN throwaway try"], env={}, root=other) == 1
    assert budget.Ledger().state()["cap"] == CAP
    assert "SYN throwaway try" not in (other / "BUILD_LOG.md").read_text(encoding="utf-8")


def test_B8_raise_reads_the_cap_from_main_not_from_the_current_branch(budget, ledger, repo):
    _git(repo, "checkout", "-q", "-b", "feature")
    _write_config(repo, 5_000, commit=True)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN branch try")
    assert budget.Ledger().state()["cap"] == CAP


def test_B8_raise_prints_the_old_and_new_cap(budget, repo, capsys):
    from voc import cli

    assert cli.main(["ledger", "init"], env={}, root=repo) == 0
    capsys.readouterr()
    _write_config(repo, 5_000, commit=True)
    assert cli.main(["ledger", "raise", "--reason", "SYN more runs"], env={}, root=repo) == 0
    out = capsys.readouterr().out
    assert "1,000" in out
    assert "5,000" in out


def test_B8_a_settle_above_the_reservation_is_an_overrun_that_stops_later_reservations(budget, ledger):
    ledger.settle(ledger.reserve(10), 11)
    state = ledger.state()
    assert state["used"] == 11
    assert state["overrun"] is not None
    assert any(e["type"] == "overrun" for e in state["events"])
    with pytest.raises(budget.Overrun):
        ledger.reserve(1)


def test_B8_real_use_above_the_reservation_stops_every_later_live_call(budget, replay, repo, ledger):
    big = lambda p, s: _answer(replay, input_tokens=500, output_tokens=7)
    _caller(replay, repo, big).call("SYN small prompt")
    assert budget.Ledger().state()["used"] == 507
    sent = []
    caller = _caller(replay, repo, lambda p, s: sent.append(p) or _answer(replay))
    with pytest.raises(budget.Overrun):
        caller.call("SYN another prompt")
    assert sent == []


def test_B8_clear_overrun_needs_a_reason_and_allows_live_calls_again(budget, replay, repo, ledger):
    from voc import cli

    ledger.settle(ledger.reserve(10), 11)
    with pytest.raises(budget.BudgetError):
        budget.clear_overrun(reason="  ")
    assert cli.main(["ledger", "clear-overrun", "--reason", "SYN estimate checked"], env={}, root=repo) == 0
    state = budget.Ledger().state()
    assert state["overrun"] is None
    assert state["events"][-1]["type"] == "overrun_cleared"
    assert state["events"][-1]["reason"] == "SYN estimate checked"
    assert _caller(replay, repo, lambda p, s: _answer(replay)).call("SYN prompt").source == "live"


def test_B8_while_the_margin_is_unconfirmed_the_trial_cap_limits_live_use(budget, repo):
    _write_full_config(repo, 1_000, 300, False)
    budget.init_ledger(repo)
    ledger = budget.Ledger()
    ledger.reserve(300)
    with pytest.raises(budget.CapReached):
        ledger.reserve(1)


def test_B8_the_margin_is_confirmed_only_through_a_committed_config_and_the_event_is_logged(budget, repo):
    _write_full_config(repo, 1_000, 300, False)
    budget.init_ledger(repo)
    _write_full_config(repo, 1_000, 300, True, commit=False)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN margin checked")
    assert budget.Ledger().state()["margin_confirmed"] is False
    _git(repo, "commit", "-q", "-am", "Confirm the margin")
    _sync_origin(repo)
    budget.raise_cap(repo, reason="SYN margin checked")
    state = budget.Ledger().state()
    assert state["margin_confirmed"] is True
    assert any(e["type"] == "margin_confirmed" and e["reason"] == "SYN margin checked" for e in state["events"])
    budget.Ledger().reserve(1_000)


def test_B8_the_committed_config_confirms_the_margin_after_the_smoke_test(budget):
    # Was "...has_the_trial_limit_until_the_margin_is_confirmed", asserting False. Changed in the green commit
    # because the margin was confirmed on 29 October (owner decision), and a red commit cannot break a passing test.
    config = budget.load_config(Path(__file__).resolve().parents[1])
    assert config["trial_cap_tokens"] == 200_000  # raised from 100,000 on 29 October (owner decision)
    assert config["margin_confirmed"] is True


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_B8_a_hidden_change_to_the_cap_config_is_still_caught(budget, repo, flag):
    _git(repo, "update-index", flag, "config/budget.toml")
    _write_config(repo, 5_000, commit=False)
    with pytest.raises(budget.BudgetError):
        budget.require_clean_config(repo)


def test_B8_a_git_error_in_the_clean_check_is_a_budget_error(budget, repo, monkeypatch):
    real = subprocess.run

    def flaky(args, *rest, **kwargs):
        if "status" in args:
            return real(args, *rest, **kwargs)
        raise OSError("synthetic git failure")

    monkeypatch.setattr(budget.subprocess, "run", flaky)
    with pytest.raises(budget.BudgetError):
        budget.require_clean_config(repo)


@pytest.mark.parametrize("change", [
    lambda s: s.update(reserved=s["reserved"] - 50),
    lambda s: s["open"].update(bad=-5) or s.update(reserved=s["reserved"] - 5),
    lambda s: s["open"].update(bad="many"),
])
def test_B8_open_reservations_must_be_valid_and_add_up_to_the_reserved_total(budget, ledger, change):
    ledger.reserve(100)
    _tamper(budget, change)
    with pytest.raises(budget.BudgetError):
        budget.Ledger().state()


def test_B8_release_closes_a_reservation_left_open_by_a_crash_and_charges_it_in_full(budget, ledger):
    rid = ledger.reserve(100)
    with pytest.raises(budget.BudgetError):
        budget.release(rid, reason=" ")
    budget.release(rid, reason="SYN crashed run")
    state = budget.Ledger().state()
    assert (state["used"], state["reserved"], state["open"]) == (100, 0, {})
    assert state["events"][-1]["type"] == "release"
    assert state["events"][-1]["reason"] == "SYN crashed run"
    with pytest.raises(budget.BudgetError):
        budget.release(rid, reason="SYN again")


def test_B8_cli_ledger_status_and_release(budget, repo, capsys):
    from voc import cli

    assert cli.main(["ledger", "init"], env={}, root=repo) == 0
    rid = budget.Ledger().reserve(40)
    capsys.readouterr()
    assert cli.main(["ledger", "status"], env={}, root=repo) == 0
    assert rid in capsys.readouterr().out
    assert cli.main(["ledger", "release", rid, "--reason", "SYN crashed run"], env={}, root=repo) == 0
    assert budget.Ledger().state()["used"] == 40


def test_B8_settling_an_unknown_reservation_is_an_error(budget, ledger):
    ledger.reserve(100)
    with pytest.raises(budget.BudgetError):
        ledger.settle("SYN-unknown", 5)
    state = ledger.state()
    assert (state["used"], state["reserved"]) == (0, 100)


def test_B8_a_lock_held_too_long_is_an_error_not_an_endless_wait(budget, ledger, monkeypatch):
    monkeypatch.setattr(budget, "LOCK_TIMEOUT_SECONDS", 0.2)
    with budget._locked(budget.ledger_path()):
        with pytest.raises(budget.BudgetError):
            budget.Ledger().reserve(1)
    budget.Ledger().reserve(1)


def test_B8_the_ledger_is_flushed_to_disk_before_it_is_replaced(budget, ledger, monkeypatch):
    order = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(budget.os, "fsync", lambda fd: order.append("fsync") or real_fsync(fd))
    monkeypatch.setattr(budget.os, "replace", lambda a, b: order.append("replace") or real_replace(a, b))
    ledger.reserve(1)
    assert "fsync" in order
    assert order.index("fsync") < order.index("replace")


def test_B8_a_raise_that_cannot_be_logged_is_refused(budget, ledger, repo):
    _write_config(repo, 5_000, commit=True)
    log = repo / "BUILD_LOG.md"
    log.unlink()
    log.mkdir()
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN more runs")
    assert budget.Ledger().state()["cap"] == CAP


def test_B8_a_call_with_partial_usage_is_charged_the_full_reservation(budget, replay, repo, ledger):
    prompt = "SYN prompt with half the usage"
    _caller(replay, repo, lambda p, s: _answer(replay, input_tokens=30, output_tokens=None)).call(prompt)
    state = budget.Ledger().state()
    assert state["used"] == _worst_case(prompt)
    assert state["reserved"] == 0


# Review round 2 on PR #13

HUGE = 10 ** 12


def _side_commit(repo):
    """A commit on a side branch with a huge cap and a confirmed margin. HEAD goes back to main."""
    _git(repo, "checkout", "-q", "-b", "side")
    _write_full_config(repo, HUGE, 300, True, commit=False)
    _git(repo, "commit", "-q", "-am", "Side")
    sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    return sha


def _assert_unchanged(budget):
    state = budget.Ledger().state()
    assert state["cap"] == CAP
    assert state["margin_confirmed"] is False


def _log(repo):
    return (repo / "BUILD_LOG.md").read_text(encoding="utf-8")


def test_B8_a_tag_named_main_cannot_raise_the_cap_or_confirm_the_margin(budget, ledger, repo):
    _git(repo, "tag", "main", _side_commit(repo))
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN tag try")
    _assert_unchanged(budget)


def test_B8_a_main_file_in_the_git_folder_cannot_raise_the_cap(budget, ledger, repo):
    (repo / ".git" / "main").write_text(_side_commit(repo) + "\n", encoding="utf-8")
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN file try")
    _assert_unchanged(budget)


def test_B8_a_replaced_config_blob_cannot_raise_the_cap(budget, ledger, repo, tmp_path):
    fake = tmp_path / "fake.toml"
    fake.write_text(f"cap_tokens = {HUGE}\ninput_margin_tokens = {MARGIN}\nmargin_confirmed = true\n",
                    encoding="utf-8")
    fake_blob = _git(repo, "hash-object", "-w", str(fake))
    real_blob = _git(repo, "rev-parse", "main:config/budget.toml")
    _git(repo, "replace", real_blob, fake_blob)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN replace try")
    _assert_unchanged(budget)


def test_B8_a_moved_local_main_cannot_raise_the_cap(budget, ledger, repo):
    _git(repo, "checkout", "-q", "-b", "feature")
    _write_full_config(repo, HUGE, 300, True, commit=False)
    _git(repo, "commit", "-q", "-am", "Feature")
    _git(repo, "update-ref", "refs/heads/main", "refs/heads/feature")
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN moved main")
    _assert_unchanged(budget)


def test_B8_raise_is_refused_when_origin_main_is_missing(budget, ledger, repo):
    _write_config(repo, 5_000, commit=True)
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN no origin")
    _assert_unchanged(budget)


def test_B8_init_writes_a_build_log_line_so_a_reset_shows_in_the_history(budget, ledger, repo):
    log = _log(repo)
    assert "voc ledger init" in log
    assert "1,000" in log


def test_B8_a_late_settle_of_a_released_reservation_charges_the_real_use_and_records_the_overrun(
        budget, replay, repo, ledger):
    prompt = "SYN-a"
    assert _worst_case(prompt) == 155

    def backend(p, settings):
        [rid] = budget.Ledger().state()["open"]
        budget.release(rid, reason="SYN looked stuck")
        return _answer(replay, input_tokens=300, output_tokens=7)

    _caller(replay, repo, backend).call(prompt)
    state = budget.Ledger().state()
    assert state["used"] == 307
    assert state["reserved"] == 0
    assert state["overrun"] is not None
    assert state["overrun"]["real"] == 307


def test_B8_release_writes_a_build_log_line_with_the_reason(budget, ledger, repo):
    budget.release(ledger.reserve(100), reason="SYN crash note")
    assert "SYN crash note" in _log(repo)


def test_B8_clear_overrun_writes_a_build_log_line_with_the_reason(budget, ledger, repo):
    ledger.settle(ledger.reserve(10), 11)
    budget.clear_overrun(reason="SYN estimate checked by the owner")
    assert "SYN estimate checked by the owner" in _log(repo)


def test_B8_a_local_clean_filter_cannot_hide_a_change(budget, repo):
    _git(repo, "config", "filter.synthetic.clean", "git show HEAD:config/budget.toml")
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("config/budget.toml filter=synthetic\n", encoding="utf-8")
    _write_config(repo, 5_000, commit=False)
    with pytest.raises(budget.BudgetError):
        budget.require_clean_config(repo)


def test_B8_a_failed_ledger_write_after_the_log_line_is_logged_as_failed(budget, ledger, repo, monkeypatch):
    _write_config(repo, 5_000, commit=True)

    def broken(path, text):
        raise OSError("synthetic disk full")

    monkeypatch.setattr(budget, "atomic_write", broken)
    with pytest.raises(budget.BudgetError):
        budget.raise_cap(repo, reason="SYN more runs")
    assert budget.Ledger().state()["cap"] == CAP
    lines = _log(repo).rstrip().splitlines()
    assert "SYN more runs" in lines[-2]
    assert "failed" in lines[-1]


def test_B8_a_git_call_that_runs_and_exits_non_zero_is_refused(budget, ledger, repo, monkeypatch):
    real = subprocess.run

    def failing(args, *rest, **kwargs):
        return real(["git", "synthetic-no-such-command"], *rest, **kwargs)

    monkeypatch.setattr(budget.subprocess, "run", failing)
    checks = (lambda: budget.require_clean_config(repo), lambda: budget.committed_config(repo),
              lambda: budget.raise_cap(repo, reason="SYN git fails"))
    for check in checks:
        with pytest.raises(budget.BudgetError):
            check()
