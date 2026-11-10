"""Spec 004, J11 and J12: Job B's own token ledger and recordings, in the raw volume (pull request 6b, part 3a).

The June ledger is apart from the laptop's. Its cap is `june_cap_tokens` in the frozen checkout's
`config/budget.toml`, read from the job's Git source, since serverless compute may have no git command to check
`origin/main` (J11). It is made on Job B's first live call and reused by a later run, so a resumed run keeps what
was used. The recordings live beside it, so a resumed run replays every recorded answer and calls the model only
for the complaints with none (J1). The volume's file system takes the ledger's lock, atomic replace and exclusive
create (probe 3 of 10 November).

B21 and J5: nothing here prints. Every refusal holds fixed text and numbers only.
"""
from datetime import datetime
from pathlib import Path

from voc.budget import Ledger, _locked, _read, _whole_number, _write, load_config
from voc.job_a import VOLUME
from voc.replay import Caller

LEDGER = VOLUME + "/ledger_june/ledger.json"
RECORDINGS = VOLUME + "/recordings_june"
PROJECT = "spec 004, Job B's June ledger"
MODEL = "claude-haiku-5-5"


class JuneLedgerError(ValueError):
    """A refusal with fixed text and numbers only (B21, J5)."""


def june_config(root):
    """The frozen checkout's budget config, with a whole number June cap, and no git."""
    config = load_config(root)
    if not _whole_number(config.get("june_cap_tokens")):
        raise JuneLedgerError("config/budget.toml needs a whole number june_cap_tokens")
    return config


def open_ledger(root, path=LEDGER):
    """The June ledger at `path`, made with the frozen June cap if it is not there yet."""
    config = june_config(root)
    cap, path = config["june_cap_tokens"], Path(path)
    with _locked(path):
        if not path.exists():
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            _write(path, {"cap": cap, "trial_cap": config["trial_cap_tokens"],
                          "margin_confirmed": config["margin_confirmed"], "used": 0, "reserved": 0, "calls": 0,
                          "open": {}, "released": {}, "overrun": None, "project": PROJECT,
                          "events": [{"type": "init", "time": now, "cap": cap, "config": "june_cap_tokens"}]})
            state = None
        else:
            state = _read(path)
    if state is not None and state["project"] != PROJECT:
        raise JuneLedgerError("the ledger in the volume is not the June ledger")
    if state is not None and state["cap"] != cap:
        raise JuneLedgerError("the June ledger's cap is not the frozen June cap")
    return Ledger(path)


def june_caller(root, backend, settings, ledger_path=LEDGER, recordings=RECORDINGS, mode="live"):
    """The laptop's caller, with the June ledger, the volume's recordings and the frozen config, so it never runs
    git and never touches the home folder."""
    return Caller("api", MODEL, settings, backend=backend, mode=mode, root=root,
                  ledger=open_ledger(root, ledger_path), recordings=Path(recordings), config=june_config(root))
