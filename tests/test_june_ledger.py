"""Spec 004, J11 and J12: Job B's own token ledger and recordings in the raw volume (pull request 6b, part 3a).

The June ledger's cap is `june_cap_tokens` in the frozen checkout's `config/budget.toml`, read from the job's Git
source, since serverless compute may have no git command (J11). The recordings live beside it, so a resumed run
replays every recorded answer and pays only for the rest (J1). Nothing here calls git or a model.

Every fixture is synthetic and built in a tmp folder.
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROMPT = "SYN-1 a synthetic prompt about a mortgage escrow account"


@pytest.fixture
def no_git(monkeypatch):
    """Serverless compute may have no git, so any git call fails the test."""
    from voc import budget

    def refused(*args, **kwargs):
        raise AssertionError("the June ledger must never call git")

    monkeypatch.setattr(budget, "_git", refused)


def _root(tmp_path, cap=None):
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    text = (REPO / "config" / "budget.toml").read_text(encoding="utf-8")
    if cap is not None:
        text = text.replace("june_cap_tokens = 40000000", f"june_cap_tokens = {cap}")
    (root / "config" / "budget.toml").write_text(text, encoding="utf-8")
    return root


def test_J12_the_june_ledger_is_made_with_the_frozen_june_cap_and_no_git(tmp_path, no_git):
    from voc import june_ledger

    path = tmp_path / "volume" / "ledger_june" / "ledger.json"
    ledger = june_ledger.open_ledger(_root(tmp_path, cap=1234567), path)
    state = ledger.state()
    assert state["cap"] == 1234567 and state["used"] == 0 and state["reserved"] == 0 and state["calls"] == 0
    assert state["project"] == june_ledger.PROJECT and state["margin_confirmed"] is True
    assert json.loads(path.read_text(encoding="utf-8"))["cap"] == 1234567


def test_J1_a_later_run_reuses_the_june_ledger_and_keeps_what_was_used(tmp_path, no_git):
    from voc import june_ledger

    root, path = _root(tmp_path), tmp_path / "volume" / "ledger_june" / "ledger.json"
    first = june_ledger.open_ledger(root, path)
    first.settle(first.reserve(500), 300)
    again = june_ledger.open_ledger(root, path)
    assert again.state()["used"] == 300 and again.state()["calls"] == 1


def test_J12_a_june_ledger_whose_cap_is_not_the_frozen_one_is_refused(tmp_path, no_git):
    from voc import june_ledger

    path = tmp_path / "volume" / "ledger_june" / "ledger.json"
    june_ledger.open_ledger(_root(tmp_path, cap=1000), path)
    with pytest.raises(june_ledger.JuneLedgerError, match="^the June ledger's cap is not the frozen June cap$"):
        june_ledger.open_ledger(_root(tmp_path / "other", cap=2000), path)


def test_J12_a_ledger_made_for_another_project_is_refused(tmp_path, no_git):
    from voc import june_ledger

    root, path = _root(tmp_path), tmp_path / "volume" / "ledger_june" / "ledger.json"
    june_ledger.open_ledger(root, path)
    state = json.loads(path.read_text(encoding="utf-8"))
    state["project"] = "the laptop"
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(june_ledger.JuneLedgerError, match="^the ledger in the volume is not the June ledger$"):
        june_ledger.open_ledger(root, path)


def test_J12_a_config_with_no_whole_june_cap_is_refused(tmp_path, no_git):
    from voc import june_ledger

    root = _root(tmp_path)
    text = (root / "config" / "budget.toml").read_text(encoding="utf-8")
    (root / "config" / "budget.toml").write_text(text.replace("june_cap_tokens = 40000000", "june_cap_tokens = -1"),
                                                 encoding="utf-8")
    with pytest.raises(june_ledger.JuneLedgerError, match="^config/budget.toml needs a whole number june_cap_tokens$"):
        june_ledger.open_ledger(root, tmp_path / "ledger.json")


def test_J11_the_ledger_and_recordings_live_in_the_raw_volume():
    from voc import june_ledger

    assert june_ledger.LEDGER == "/Volumes/workspace/default/voc_raw/ledger_june/ledger.json"
    assert june_ledger.RECORDINGS == "/Volumes/workspace/default/voc_raw/recordings_june"


def _answer(text='{"label": "Mortgage"}'):
    from voc.replay import Answer

    return Answer(text=text, input_tokens=120, output_tokens=30, stop_reason="end_turn")


def test_J1_a_live_call_is_recorded_in_the_volume_and_charged_to_the_june_ledger(tmp_path, no_git):
    from voc import june_ledger

    root = _root(tmp_path)
    calls = []

    def backend(prompt, settings):
        calls.append(prompt)
        return _answer()

    caller = june_ledger.june_caller(root, backend, {"max_tokens": 2048, "effort": "low", "thinking": "adaptive"},
                                     ledger_path=tmp_path / "ledger.json", recordings=tmp_path / "recordings")
    reply = caller.call(PROMPT)
    assert reply.source == "live" and calls == [PROMPT]
    assert len(list((tmp_path / "recordings").glob("*.json"))) == 1
    assert june_ledger.open_ledger(root, tmp_path / "ledger.json").state()["used"] == 150


def test_J1_a_resumed_run_replays_the_recorded_answer_and_pays_nothing(tmp_path, no_git):
    from voc import june_ledger

    root = _root(tmp_path)
    settings = {"max_tokens": 2048, "effort": "low", "thinking": "adaptive"}
    june_ledger.june_caller(root, lambda p, s: _answer(), settings, ledger_path=tmp_path / "ledger.json",
                            recordings=tmp_path / "recordings").call(PROMPT)

    def never(prompt, settings):
        raise AssertionError("a recorded answer must not be drawn again")

    reply = june_ledger.june_caller(root, never, settings, ledger_path=tmp_path / "ledger.json",
                                    recordings=tmp_path / "recordings").call(PROMPT)
    assert reply.source == "replay" and reply.charged_tokens == 0
    assert june_ledger.open_ledger(root, tmp_path / "ledger.json").state()["used"] == 150


def test_J12_a_call_past_the_june_cap_is_refused_before_anything_is_sent(tmp_path, no_git):
    from voc import june_ledger
    from voc.budget import CapReached

    root = _root(tmp_path, cap=100)

    def never(prompt, settings):
        raise AssertionError("nothing may be sent past the cap")

    caller = june_ledger.june_caller(root, never, {"max_tokens": 2048, "effort": "low", "thinking": "adaptive"},
                                     ledger_path=tmp_path / "ledger.json", recordings=tmp_path / "recordings")
    with pytest.raises(CapReached):
        caller.call(PROMPT)


def test_J11_the_laptop_caller_still_checks_the_committed_config(tmp_path, monkeypatch):
    """The laptop's path is unchanged: with no config given, the caller checks the committed budget file first."""
    from voc import replay

    checked = []
    monkeypatch.setattr(replay, "require_clean_config", lambda root: checked.append(root))
    monkeypatch.setattr(replay, "load_config", lambda root: {"input_margin_tokens": 100})
    monkeypatch.setattr(replay, "recordings_dir", lambda: tmp_path / "recordings")

    class FakeLedger:
        def reserve(self, tokens):
            return "r"

        def settle(self, rid, used):
            pass

    caller = replay.Caller("api", "claude-haiku-5-5", {"max_tokens": 2048}, backend=lambda p, s: _answer(),
                           root=tmp_path, ledger=FakeLedger())
    caller.call(PROMPT)
    assert checked == [tmp_path]


def test_J11_the_june_caller_leaves_the_laptop_s_shared_folder_alone(tmp_path, no_git, monkeypatch):
    """The June caller never writes to the home folder's recordings."""
    from voc import june_ledger, replay

    monkeypatch.setattr(replay, "recordings_dir", lambda: (_ for _ in ()).throw(AssertionError("home folder used")))
    june_ledger.june_caller(_root(tmp_path), lambda p, s: _answer(), {"max_tokens": 2048, "effort": "low",
                                                                       "thinking": "adaptive"},
                            ledger_path=tmp_path / "ledger.json", recordings=tmp_path / "recordings").call(PROMPT)
    shutil.rmtree(tmp_path / "recordings")


# The review of #110 (owner decision: fixed in 6b, part 3b): a reused ledger must keep the frozen config's trial
# cap settings, and a June ledger refusal is a budget refusal.


@pytest.mark.parametrize("field, value", [("margin_confirmed", False), ("trial_cap", 1)])
def test_J12_a_reused_june_ledger_with_other_trial_settings_is_refused(tmp_path, no_git, field, value):
    from voc import june_ledger

    root, path = _root(tmp_path), tmp_path / "volume" / "ledger_june" / "ledger.json"
    june_ledger.open_ledger(root, path)
    state = json.loads(path.read_text(encoding="utf-8"))
    state[field] = value
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(june_ledger.JuneLedgerError, match="^the June ledger's settings are not the frozen config's$"):
        june_ledger.open_ledger(root, path)


def test_J12_a_june_ledger_refusal_is_a_budget_refusal():
    from voc import june_ledger
    from voc.budget import BudgetError

    assert issubclass(june_ledger.JuneLedgerError, BudgetError)
