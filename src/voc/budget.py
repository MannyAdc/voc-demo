"""B8: the token ledger. Spend has a hard stop.

One ledger file counts all live tokens (input plus output). It lives at one
fixed path in the home folder, so all worktrees share one cap. The cap comes
from the committed `config/budget.toml` and is copied into the ledger at
init. Only `raise_cap` can raise it later.

Every read and write of the ledger holds a file lock, so two processes can
never both spend the last tokens. A missing or unreadable ledger stops every
live call. Messages of BudgetError are ours, so they are safe to print.
"""
import json
import os
import subprocess
import sys
import time
import tomllib
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

CONFIG = Path("config") / "budget.toml"
LOCK_TIMEOUT_SECONDS = 60


class BudgetError(ValueError):
    """A ledger or cap problem. The message is ours, so it is safe to print."""


class CapReached(BudgetError):
    """The reservation would pass the cap, so the call is not sent."""


def voc_home():
    """The shared folder in the home folder for the ledger and the recordings."""
    return Path.home() / ".voc"


def ledger_path():
    return voc_home() / "ledger.json"


def load_config(root):
    try:
        with open(Path(root) / CONFIG, "rb") as f:
            config = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        raise BudgetError(f"cannot read {CONFIG.as_posix()}") from None
    for name in ("cap_tokens", "input_margin_tokens"):
        value = config.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise BudgetError(f"{CONFIG.as_posix()} needs a whole number {name} of 0 or more")
    return config


def require_clean_config(root):
    """Refuse unless the cap config is committed exactly as it is on disk."""
    try:
        result = subprocess.run(["git", "status", "--porcelain", "--", CONFIG.as_posix()],
                                cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise BudgetError("cannot run git to check the cap config") from None
    if result.returncode != 0:
        raise BudgetError(f"cannot check {CONFIG.as_posix()} with git, so live calls are refused")
    if result.stdout.strip():
        raise BudgetError(f"{CONFIG.as_posix()} has uncommitted changes, so this is refused")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", CONFIG.as_posix()],
                             cwd=root, capture_output=True, text=True, timeout=30)
    if tracked.returncode != 0:
        raise BudgetError(f"{CONFIG.as_posix()} is not committed, so this is refused")


def input_estimate(prompt, margin):
    """Worst-case input tokens: the UTF-8 byte count of the prompt plus a fixed margin."""
    return len(prompt.encode("utf-8")) + margin


def worst_case(prompt, output_limit, margin):
    """The reservation for one call: the input estimate plus the output limit."""
    return input_estimate(prompt, margin) + output_limit


def _whole(tokens, what):
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        raise BudgetError(f"{what} must be a whole number of 0 or more")
    return tokens


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def _locked(path):
    """Hold an exclusive lock on a side file next to the ledger."""
    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+b") as f:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                _lock(f)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise BudgetError("the ledger is locked by another process") from None
                time.sleep(0.005)
        try:
            yield
        finally:
            _unlock(f)


if sys.platform == "win32":
    import msvcrt

    def _lock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _read(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BudgetError("there is no ledger, so live calls are refused. Run: voc ledger init") from None
    except (OSError, ValueError):
        raise BudgetError("the ledger cannot be read, so live calls are refused") from None
    try:
        for name in ("cap", "used", "reserved", "calls"):
            _whole(state[name], name)
        if not isinstance(state["open"], dict) or not isinstance(state["events"], list):
            raise TypeError
    except (KeyError, TypeError, BudgetError):
        raise BudgetError("the ledger is not valid, so live calls are refused") from None
    return state


def _write(path, state):
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Windows refuses a replace while a reader without the lock has the file open.
            if attempt == 49:
                raise
            time.sleep(0.01)


class Ledger:
    """The token ledger at the fixed path, or at `path` if one is given."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else ledger_path()

    def state(self):
        with _locked(self.path):
            return _read(self.path)

    def reserve(self, tokens):
        """Reserve the worst case for one call. Returns the reservation ID."""
        _whole(tokens, "a reservation")
        with _locked(self.path):
            state = _read(self.path)
            if state["used"] + state["reserved"] + tokens > state["cap"]:
                raise CapReached(f"the reservation of {tokens} tokens would pass the cap of {state['cap']} tokens")
            rid = uuid.uuid4().hex
            state["open"][rid] = tokens
            state["reserved"] += tokens
            state["calls"] += 1
            _write(self.path, state)
            return rid

    def settle(self, rid, real_tokens=None):
        """Replace a reservation by the real use. No real use means the full reservation is charged."""
        if real_tokens is not None:
            _whole(real_tokens, "a charge")
        with _locked(self.path):
            state = _read(self.path)
            if rid not in state["open"]:
                raise BudgetError("unknown reservation")
            reserved = state["open"].pop(rid)
            state["reserved"] -= reserved
            state["used"] += reserved if real_tokens is None else real_tokens
            _write(self.path, state)


def init_ledger(root, cap=None, path=None):
    """Create a new ledger with the committed cap. An override can only lower it."""
    require_clean_config(root)
    config_cap = load_config(root)["cap_tokens"]
    if cap is not None:
        _whole(cap, "the cap override")
        if cap > config_cap:
            raise BudgetError(f"an override can only lower the cap of {config_cap} tokens, never raise it")
    cap = config_cap if cap is None else cap
    path = Path(path) if path is not None else ledger_path()
    with _locked(path):
        if path.exists():
            raise BudgetError("a ledger already exists at the fixed path, so init is refused")
        _write(path, {"cap": cap, "used": 0, "reserved": 0, "calls": 0, "open": {},
                      "events": [{"type": "init", "time": _now(), "cap": cap, "config_cap": config_cap}]})
    return cap


def raise_cap(root, reason, path=None):
    """Raise the cap to the committed config value, with a reason in the ledger and the build log."""
    reason = " ".join((reason or "").split())
    if not reason:
        raise BudgetError("a raise needs a reason")
    require_clean_config(root)
    new_cap = load_config(root)["cap_tokens"]
    path = Path(path) if path is not None else ledger_path()
    with _locked(path):
        state = _read(path)
        old_cap = state["cap"]
        if new_cap <= old_cap:
            raise BudgetError(f"the committed cap of {new_cap} tokens is not above the ledger cap of {old_cap} tokens")
        now = datetime.now().astimezone()
        state["cap"] = new_cap
        state["events"].append({"type": "raise", "time": now.isoformat(timespec="seconds"),
                                "from": old_cap, "to": new_cap, "reason": reason})
        _write(path, state)
    _log_raise(Path(root) / "BUILD_LOG.md", now, old_cap, new_cap, reason)
    return new_cap


def _log_raise(log, now, old_cap, new_cap, reason):
    heading = f"## {now:%A} {now.day} {now:%B %Y}"
    text = log.read_text(encoding="utf-8") if log.exists() else "# Build log\n"
    lines = [] if heading in text else ["", heading, ""]
    lines.append(f"- {now:%H:%M} Decision: token cap raised from {old_cap:,} to {new_cap:,} "
                 f"with `voc ledger raise`. Reason: {reason}")
    with open(log, "a", encoding="utf-8", newline="\n") as f:
        if not text.endswith("\n"):
            f.write("\n")
        f.write("\n".join(lines) + "\n")
