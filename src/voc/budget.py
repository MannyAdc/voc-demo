"""B8: the token ledger. Spend has a hard stop.

One ledger file counts all live tokens (input plus output). It lives at one
fixed path in the home folder, so all worktrees share one cap.

The cap comes from `config/budget.toml` as committed on `refs/heads/main`,
which must match `origin/main`, in the repo the ledger was made in. Git runs
with replace objects off. Init copies the cap into the ledger. Only
`raise_cap` can raise it later, and only from that same repo (worktrees of it
count). So a throwaway repo, a branch, a tag or a file named `main` cannot
raise the shared cap. Init, raise, release and clear-overrun each write a
line to the build log before the ledger changes.

Known limit: deleting the ledger and running init again resets the use to 0.
The init line in the build log makes such a reset visible.

Until the input margin is confirmed against real token counts, the
effective cap is the smaller of the cap and the trial cap. The margin becomes
confirmed only through a committed config and `raise_cap`.

If a call's real use is above its reservation, the estimate was wrong. The
ledger then records an overrun and refuses every live call until the owner
clears it with a reason.

Every read and write of the ledger holds a file lock, so two processes can
never both spend the last tokens. A missing, unreadable or inconsistent
ledger stops every live call. Messages of BudgetError are ours, so they are
safe to print.
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
PROJECT_BRANCH = "main"
DEFAULT_TRIAL_CAP = 100_000
LOCK_TIMEOUT_SECONDS = 60


class BudgetError(ValueError):
    """A ledger or cap problem. The message is ours, so it is safe to print."""


class CapReached(BudgetError):
    """The reservation would pass the cap, so the call is not sent (quarantine reason `not_run_budget`)."""


class Overrun(BudgetError):
    """A call used more than its reservation. Live calls stop until the owner clears it."""


def voc_home():
    """The shared folder in the home folder for the ledger and the recordings."""
    return Path.home() / ".voc"


def ledger_path():
    return voc_home() / "ledger.json"


# Config and git


def _git(root, *args):
    """Run git with replace objects off, so `git replace` cannot swap the config content."""
    env = {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}
    try:
        return subprocess.run(["git", "--no-replace-objects", *args], cwd=root, env=env,
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise BudgetError("cannot run git to check the cap config") from None


def _ref(root, ref):
    result = _git(root, "rev-parse", "--verify", "-q", "--end-of-options", f"{ref}^{{commit}}")
    return result.stdout.decode("ascii", "replace").strip() if result.returncode == 0 else None


def _whole_number(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_config(raw):
    try:
        config = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise BudgetError(f"cannot read {CONFIG.as_posix()}") from None
    config.setdefault("trial_cap_tokens", DEFAULT_TRIAL_CAP)
    config.setdefault("margin_confirmed", False)
    for name in ("cap_tokens", "input_margin_tokens", "trial_cap_tokens"):
        if not _whole_number(config.get(name)):
            raise BudgetError(f"{CONFIG.as_posix()} needs a whole number {name} of 0 or more")
    if not isinstance(config["margin_confirmed"], bool):
        raise BudgetError(f"{CONFIG.as_posix()} needs margin_confirmed to be true or false")
    return config


def load_config(root):
    """The cap config as it is on disk in `root`."""
    try:
        raw = (Path(root) / CONFIG).read_bytes()
    except OSError:
        raise BudgetError(f"cannot read {CONFIG.as_posix()}") from None
    return _parse_config(raw)


def committed_config(root):
    """The cap config as committed on the real `main` branch in the repo that holds `root`.

    Only the full ref `refs/heads/main` counts, so a tag or a file named `main`
    is never read. It must match `refs/remotes/origin/main`, so a local `main`
    moved by hand is refused.
    """
    local = _ref(root, f"refs/heads/{PROJECT_BRANCH}")
    if local is None:
        raise BudgetError(f"there is no {PROJECT_BRANCH} branch")
    remote = _ref(root, f"refs/remotes/origin/{PROJECT_BRANCH}")
    if remote is None:
        raise BudgetError(f"there is no origin/{PROJECT_BRANCH}, so the committed cap cannot be checked")
    if local != remote:
        raise BudgetError(f"local {PROJECT_BRANCH} and origin/{PROJECT_BRANCH} differ, so this is refused")
    result = _git(root, "cat-file", "blob", f"{local}:{CONFIG.as_posix()}")
    if result.returncode != 0:
        raise BudgetError(f"{CONFIG.as_posix()} is not committed on {PROJECT_BRANCH}")
    return _parse_config(result.stdout)


def _same_text(a, b):
    """Byte for byte, except that a line ending may be CRLF on one side and LF on the other."""
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def require_clean_config(root):
    """Refuse unless the cap config on disk is exactly the committed one.

    The raw file bytes are compared with the committed blob. No git filter is
    run and no index flag is read, so skip-worktree, assume-unchanged and a
    local clean filter cannot hide a change.
    """
    path = CONFIG.as_posix()
    head = _git(root, "cat-file", "blob", f"HEAD:{path}")
    if head.returncode != 0:
        raise BudgetError(f"{path} is not committed, so this is refused")
    top = _git(root, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise BudgetError("this folder is not in a git repo")
    try:
        work = (Path(top.stdout.decode("utf-8").strip()) / CONFIG).read_bytes()
    except OSError:
        raise BudgetError(f"cannot read {path}, so this is refused") from None
    if not _same_text(work, head.stdout):
        raise BudgetError(f"{path} has uncommitted changes, so this is refused")


def _project_id(root):
    """The repo's shared git folder. Worktrees of one repo share it, other repos do not."""
    result = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if result.returncode != 0:
        raise BudgetError("this folder is not in a git repo")
    return os.path.normcase(str(Path(result.stdout.decode("utf-8").strip()).resolve()))


# Estimates


def input_estimate(prompt, margin):
    """Worst-case input tokens: the UTF-8 byte count of the prompt plus a fixed margin."""
    return len(prompt.encode("utf-8")) + margin


def worst_case(prompt, output_limit, margin):
    """The reservation for one call: the input estimate plus the output limit."""
    return input_estimate(prompt, margin) + output_limit


def effective_cap(state):
    """The cap, or the trial cap if that is smaller and the margin is not confirmed yet."""
    return state["cap"] if state["margin_confirmed"] else min(state["cap"], state["trial_cap"])


# Files and lock


def _whole(tokens, what):
    if not _whole_number(tokens):
        raise BudgetError(f"{what} must be a whole number of 0 or more")
    return tokens


def _reason(reason, what):
    reason = " ".join((reason or "").split())
    if not reason:
        raise BudgetError(f"{what} needs a reason")
    return reason


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write(path, text):
    """Write a file through a flushed temporary file and an atomic replace."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Windows refuses a replace while another program has the file open.
            if attempt == 49:
                raise
            time.sleep(0.01)


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


def _valid(state):
    numbers = all(_whole_number(state[n]) for n in ("cap", "trial_cap", "used", "reserved", "calls"))
    kinds = (isinstance(state["margin_confirmed"], bool) and isinstance(state["project"], str)
             and isinstance(state["open"], dict) and isinstance(state["events"], list)
             and (state["overrun"] is None or isinstance(state["overrun"], dict)))
    if not (numbers and kinds and isinstance(state["released"], dict)):
        return False
    values = list(state["open"].values())
    return (all(_whole_number(v) for v in values) and sum(values) == state["reserved"]
            and all(_whole_number(v) for v in state["released"].values()))


def _read(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BudgetError("there is no ledger, so live calls are refused. Run: voc ledger init") from None
    except (OSError, ValueError):
        raise BudgetError("the ledger cannot be read, so live calls are refused") from None
    try:
        if isinstance(state, dict):
            state.setdefault("released", {})
        ok = isinstance(state, dict) and _valid(state)
    except KeyError:
        ok = False
    if not ok:
        raise BudgetError("the ledger is not valid, so live calls are refused")
    return state


def _write(path, state):
    atomic_write(path, json.dumps(state, indent=2, sort_keys=True) + "\n")


def _path(path):
    return Path(path) if path is not None else ledger_path()


def _build_log(project):
    """BUILD_LOG.md in the main checkout of the ledger's repo (the folder that holds its git folder)."""
    return Path(project).parent / "BUILD_LOG.md"


def _append_log(log, now, line):
    heading = f"## {now:%A} {now.day} {now:%B %Y}"
    text = log.read_text(encoding="utf-8") if log.exists() else "# Build log\n"
    lines = [] if heading in text else ["", heading, ""]
    lines.append(f"- {now:%H:%M} {line}")
    with open(log, "a", encoding="utf-8", newline="\n") as f:
        if not text.endswith("\n"):
            f.write("\n")
        f.write("\n".join(lines) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _logged_write(path, state, log, now, line, what):
    """Write the build log line first, then the ledger. A change that cannot be logged does not happen.

    If the ledger write fails after the log line, a second line says so.
    """
    try:
        _append_log(log, now, line)
    except OSError:
        raise BudgetError(f"cannot write BUILD_LOG.md, so the {what} is refused") from None
    try:
        _write(path, state)
    except OSError:
        try:
            _append_log(log, datetime.now().astimezone(), f"Correction: the {what} above failed. "
                        "The ledger was not changed.")
        except OSError:
            pass
        raise BudgetError(f"cannot write the ledger, so the {what} failed") from None


# The ledger


class Ledger:
    """The token ledger at the fixed path, or at `path` if one is given."""

    def __init__(self, path=None):
        self.path = _path(path)

    def state(self):
        with _locked(self.path):
            return _read(self.path)

    def reserve(self, tokens):
        """Reserve the worst case for one call. Returns the reservation ID."""
        _whole(tokens, "a reservation")
        with _locked(self.path):
            state = _read(self.path)
            if state["overrun"] is not None:
                raise Overrun("a call used more than its reservation, so live calls are refused. "
                              "The owner checks the estimate, then runs: voc ledger clear-overrun")
            cap = effective_cap(state)
            if state["used"] + state["reserved"] + tokens > cap:
                raise CapReached(f"the reservation of {tokens} tokens would pass the cap of {cap} tokens")
            rid = uuid.uuid4().hex
            state["open"][rid] = tokens
            state["reserved"] += tokens
            state["calls"] += 1
            _write(self.path, state)
            return rid

    def settle(self, rid, real_tokens=None):
        """Replace a reservation by the real use. No real use means the full reservation is charged.

        Real use above the reservation is charged, and recorded as an overrun.
        """
        if real_tokens is not None:
            _whole(real_tokens, "a charge")
        with _locked(self.path):
            state = _read(self.path)
            if rid in state["open"]:
                reserved = state["open"].pop(rid)
                state["reserved"] -= reserved
                charge = reserved if real_tokens is None else real_tokens
                state["used"] += charge
            elif rid in state["released"]:
                # Released while still in flight: the release charged the full reservation,
                # so the real use replaces that charge.
                reserved = state["released"].pop(rid)
                charge = reserved if real_tokens is None else real_tokens
                state["used"] += charge - reserved
            else:
                raise BudgetError("unknown reservation")
            if charge > reserved:
                event = {"type": "overrun", "time": _now(), "reservation": rid,
                         "reserved": reserved, "real": charge}
                state["events"].append(event)
                state["overrun"] = event
            _write(self.path, state)


def init_ledger(root, cap=None, path=None):
    """Create a new ledger from the config committed on main. An override can only lower the cap.

    Init writes a build log line first, so a ledger reset shows in the history.
    """
    require_clean_config(root)
    config = committed_config(root)
    config_cap = config["cap_tokens"]
    if cap is not None:
        _whole(cap, "the cap override")
        if cap > config_cap:
            raise BudgetError(f"an override can only lower the cap of {config_cap} tokens, never raise it")
    cap = config_cap if cap is None else cap
    project = _project_id(root)
    path = _path(path)
    with _locked(path):
        if path.exists():
            raise BudgetError("a ledger already exists at the fixed path, so init is refused")
        now = datetime.now().astimezone()
        state = {"cap": cap, "trial_cap": config["trial_cap_tokens"],
                 "margin_confirmed": config["margin_confirmed"], "used": 0, "reserved": 0,
                 "calls": 0, "open": {}, "released": {}, "overrun": None, "project": project,
                 "events": [{"type": "init", "time": now.isoformat(timespec="seconds"), "cap": cap,
                             "config_cap": config_cap, "trial_cap": config["trial_cap_tokens"],
                             "margin_confirmed": config["margin_confirmed"]}]}
        line = (f"Decision: new token ledger made with `voc ledger init`: cap {cap:,} tokens, "
                f"trial cap {config['trial_cap_tokens']:,} tokens, margin confirmed "
                f"{'yes' if config['margin_confirmed'] else 'no'}, effective cap {effective_cap(state):,} tokens. "
                "Any earlier use is not carried over.")
        _logged_write(path, state, _build_log(project), now, line, "init")
    return cap


def raise_cap(root, reason, path=None):
    """Apply the config committed on main: a higher cap, a new trial cap, or a confirmed margin.

    It must run in the repo the ledger was made in. The build log line is
    written first, so a raise that cannot be logged does not happen.
    Returns the old and new cap and effective cap.
    """
    reason = _reason(reason, "a raise")
    require_clean_config(root)
    config = committed_config(root)
    project = _project_id(root)
    path = _path(path)
    with _locked(path):
        state = _read(path)
        if project != state["project"]:
            raise BudgetError("raise must run in the repo the ledger was made in")
        new = {"cap": config["cap_tokens"], "trial_cap": config["trial_cap_tokens"],
               "margin_confirmed": config["margin_confirmed"]}
        if new["cap"] < state["cap"]:
            raise BudgetError(f"the committed cap of {new['cap']} tokens is below the ledger cap of {state['cap']}")
        if state["margin_confirmed"] and not new["margin_confirmed"]:
            raise BudgetError("the ledger has a confirmed margin, but the committed config does not")
        changed = [k for k in ("cap", "trial_cap", "margin_confirmed") if new[k] != state[k]]
        if not changed:
            raise BudgetError("the committed config matches the ledger, so there is nothing to raise")
        now = datetime.now().astimezone()
        result = {"from": state["cap"], "to": new["cap"], "effective_from": effective_cap(state),
                  "effective_to": effective_cap({**state, **new})}
        changes = []
        stamp = now.isoformat(timespec="seconds")
        if "cap" in changed:
            changes.append(f"cap {state['cap']:,} to {new['cap']:,}")
            state["events"].append({"type": "raise", "time": stamp, "from": state["cap"],
                                    "to": new["cap"], "reason": reason})
        if "trial_cap" in changed:
            changes.append(f"trial cap {state['trial_cap']:,} to {new['trial_cap']:,}")
            state["events"].append({"type": "trial_cap", "time": stamp, "from": state["trial_cap"],
                                    "to": new["trial_cap"], "reason": reason})
        if "margin_confirmed" in changed:
            changes.append("input margin confirmed, so the trial cap no longer applies")
            state["events"].append({"type": "margin_confirmed", "time": stamp, "reason": reason})
        state.update(new)
        line = (f"Decision: token ledger changed with `voc ledger raise`: {', '.join(changes)}. "
                f"Effective cap {result['effective_from']:,} to {result['effective_to']:,} tokens. "
                f"Reason: {reason}")
        _logged_write(path, state, _build_log(state["project"]), now, line, "raise")
    return result


def release(rid, reason, path=None):
    """Close a reservation left open by a crash. It is charged in full, since the call may have been sent.

    The ID is kept, so if the call was still in flight, its late settle
    replaces the charge with the real use and records any overrun.
    """
    reason = _reason(reason, "a release")
    path = _path(path)
    with _locked(path):
        state = _read(path)
        if rid not in state["open"]:
            raise BudgetError("unknown reservation")
        now = datetime.now().astimezone()
        tokens = state["open"].pop(rid)
        state["reserved"] -= tokens
        state["used"] += tokens
        state["released"][rid] = tokens
        state["events"].append({"type": "release", "time": now.isoformat(timespec="seconds"),
                                "reservation": rid, "tokens": tokens, "reason": reason})
        line = (f"Decision: reservation {rid} of {tokens:,} tokens released with `voc ledger release` "
                f"and charged in full. Reason: {reason}")
        _logged_write(path, state, _build_log(state["project"]), now, line, "release")
    return tokens


def clear_overrun(reason, path=None):
    """The owner has checked the estimate. Live calls may go on."""
    reason = _reason(reason, "clearing an overrun")
    path = _path(path)
    with _locked(path):
        state = _read(path)
        overrun = state["overrun"]
        if overrun is None:
            raise BudgetError("there is no overrun to clear")
        now = datetime.now().astimezone()
        state["events"].append({"type": "overrun_cleared", "time": now.isoformat(timespec="seconds"),
                                "overrun": overrun, "reason": reason})
        state["overrun"] = None
        line = (f"Decision: token overrun cleared with `voc ledger clear-overrun` "
                f"(reserved {overrun.get('reserved', 0):,}, real {overrun.get('real', 0):,} tokens). "
                f"Reason: {reason}")
        _logged_write(path, state, _build_log(state["project"]), now, line, "overrun clear")
