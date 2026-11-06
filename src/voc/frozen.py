"""Spec 004, J1: what is frozen before June is scored, and the June run log.

The frozen code's hash is one SHA-256 over every file in the places the spec names, each as its path and its
own SHA-256, in path order. It is computed from the files themselves, not from git, because Databricks'
serverless compute may have no git command. `.gitattributes` keeps every frozen file in LF, so a Windows and a
Linux checkout give the same bytes, and a test checks that the files hashed are exactly the tracked ones. The
July development labels are frozen too, because Job B checks the refit TF-IDF + LR against them (J7). Where git
is present, `scripts/june_hash.py` refuses when the files on disk differ from the tracked ones.

`runs/JUNE_RUNS.md` only grows. Each row names the June list's hash and the frozen code's hash, and its kind:
`real` or `synthetic` for a list's first entry, then `reproduction`, `resume` or `second`, each with its reason.
A row the reader cannot read is refused, never skipped.
"""
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

FROZEN_PATHS = ("src", "config", "dbt", "splits", "pyproject.toml", "uv.lock", "cloud",
                ".github/workflows/june_approval.yml", "scripts/june_hash.py", "results/eval/v1_dev.csv")
# Made by Python, pytest and dbt while they run, and never tracked.
SKIP_DIRS = {"__pycache__", ".pytest_cache", "target", "logs", "dbt_packages"}
SKIP_SUFFIXES = (".pyc", ".duckdb", ".wal")
RUNS = Path("runs") / "JUNE_RUNS.md"
# The two gates that must pass, for the real row's code and the June pin, before that row is written (owner
# decision, 6 November). The log only grows, and is not frozen, so recording a pass changes no code hash.
GATES = Path("runs") / "JUNE_GATES.md"
GATE_NAMES = ("june-check", "failcheck")
GATES_HEADER = "| Date | Gate | Result | Pin SHA-256 | Code hash | Evidence |"
GATES_SEPARATOR = "|---|---|---|---|---|---|"
GATE_RESULTS = ("pass", "fail")
JUNE_LIST = Path("splits") / "june"
FIRST_KINDS = ("real", "synthetic")
LATER_KINDS = ("reproduction", "resume", "second")
HASH = re.compile(r"^[0-9a-f]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
HEADER_ROW = "| Date | Kind | June list hash | Code hash | Reason |"
SEPARATOR = "|---|---|---|---|---|"


class JuneRunsError(ValueError):
    """A refusal whose message holds only file names, kinds and counts (B21)."""


@dataclass(frozen=True)
class Entry:
    date: str
    kind: str
    list_hash: str
    code_hash: str
    reason: str


def _skipped(path, root):
    parts = path.relative_to(root).parts
    return bool(set(parts[:-1]) & SKIP_DIRS) or path.name.endswith(SKIP_SUFFIXES)


def frozen_files(root):
    """The frozen files, as paths relative to `root` with forward slashes, in order."""
    root = Path(root)
    found = set()
    for name in FROZEN_PATHS:
        path = root / name
        if path.is_file():
            found.add(name)
        elif path.is_dir():
            found |= {p.relative_to(root).as_posix() for p in path.rglob("*") if p.is_file() and not _skipped(p, root)}
    return sorted(found)


def code_hash(root):
    root = Path(root)
    digest = hashlib.sha256()
    for rel in frozen_files(root):
        digest.update(f"{rel}\0{hashlib.sha256((root / rel).read_bytes()).hexdigest()}\n".encode("utf-8"))
    return digest.hexdigest()


def changed_frozen(root):
    """The frozen files that are new, missing or changed in content against the last commit, or against the
    staged files where nothing is committed yet, so a file edited in place counts (review of #94). None where
    `root` is not the top of a git checkout, or git is missing."""
    root = Path(root).resolve()
    git = ["git", "-c", "core.quotepath=off", "-C", str(root)]
    try:
        top = subprocess.run(git + ["rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            return None
        head = subprocess.run(git + ["rev-parse", "--verify", "-q", "HEAD"], capture_output=True, text=True)
        changed = subprocess.run(git + ["diff", "--name-only", *(["HEAD"] if head.returncode == 0 else []), "--",
                                        *FROZEN_PATHS], capture_output=True, text=True)
        new = subprocess.run(git + ["ls-files", "--others", "--exclude-standard", "--", *FROZEN_PATHS],
                             capture_output=True, text=True)
        listing = subprocess.run(git + (["ls-tree", "-r", "-z", "HEAD", "--"] if head.returncode == 0
                                        else ["ls-files", "-s", "-z", "--"]) + list(FROZEN_PATHS), capture_output=True)
    except OSError:
        return None
    if changed.returncode != 0 or new.returncode != 0 or listing.returncode != 0:
        return None
    paths = {p for p in changed.stdout.splitlines() + new.stdout.splitlines() if p and not _skipped(root / p, root)}
    # git can hide a change, for example line endings it normalises or a file marked skip-worktree, which the code
    # hash still sees. So each file's raw bytes are hashed as git hashes a blob, and compared with the listing's.
    for entry in listing.stdout.decode("utf-8").split("\0"):
        if not entry or "\t" not in entry:
            continue
        meta, rel = entry.split("\t", 1)
        expected = meta.split()[2 if head.returncode == 0 else 1]
        path = root / rel
        if _skipped(path, root):
            continue
        if not path.is_file():
            paths.add(rel)
            continue
        data = path.read_bytes()
        algorithm = hashlib.sha1 if len(expected) == 40 else hashlib.sha256
        if algorithm(b"blob %d\0" % len(data) + data).hexdigest() != expected:
            paths.add(rel)
    return sorted(paths | set(differs_from_git(root) or []))


def differs_from_git(root):
    """The frozen files on disk that git does not track, and the tracked ones missing from disk. None where `root`
    is not the top of a git checkout, or git is missing, so there is nothing to compare."""
    root = Path(root).resolve()
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            return None
        tracked = [p for p in subprocess.run(["git", "-c", "core.quotepath=off", "-C", str(root), "ls-files", "-z",
                                              "--", *FROZEN_PATHS], capture_output=True, check=True)
                   .stdout.decode("utf-8").split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return None
    return sorted(set(frozen_files(root)) ^ set(tracked))


def list_hash(root):
    """The SHA-256 of `splits/june/june.csv`, refused unless it matches the June manifest."""
    folder = Path(root) / JUNE_LIST
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    found = hashlib.sha256((folder / "june.csv").read_bytes()).hexdigest()
    if found != manifest["lists"]["june"]["sha256"]:
        raise JuneRunsError("splits/june/june.csv does not match its hash in splits/june/manifest.json")
    return found


def read_runs(path):
    """The entries of the June run log, refused if a row is malformed."""
    entries = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if line in (HEADER_ROW, SEPARATOR) or not line.lstrip().startswith("|"):
            continue
        if line != line.lstrip():
            raise JuneRunsError(f"line {number} of the June run log starts with a space")
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            raise JuneRunsError(f"line {number} of the June run log has {len(cells)} columns, not 5")
        entry = Entry(*cells)
        if not _real_date(entry.date):
            raise JuneRunsError(f"line {number} of the June run log has no real date of the form 2026-11-07 10:00")
        if entry.kind not in FIRST_KINDS + LATER_KINDS:
            raise JuneRunsError(f"line {number} of the June run log has an unknown kind")
        if not (HASH.match(entry.list_hash) and HASH.match(entry.code_hash)):
            raise JuneRunsError(f"line {number} of the June run log has a hash that is not 64 hex characters")
        entries.append(entry)
    return entries


@dataclass(frozen=True)
class Gate:
    date: str
    gate: str
    result: str
    pin_sha256: str
    code_hash: str
    evidence: str


def _real_date(text):
    from datetime import datetime

    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return bool(DATE.match(text))


def read_gates(path):
    """The recorded results of the June gates. A missing log has none. A malformed row is refused."""
    path = Path(path)
    if not path.is_file():
        return []
    gates = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line in (GATES_HEADER, GATES_SEPARATOR) or not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line != line.lstrip() or len(cells) != 6:
            raise JuneRunsError(f"line {number} of the June gates log does not have 6 columns at its start")
        gate = Gate(*cells)
        if (not _real_date(gate.date) or gate.gate not in GATE_NAMES or gate.result not in GATE_RESULTS
                or not HASH.match(gate.pin_sha256) or not HASH.match(gate.code_hash) or not gate.evidence):
            raise JuneRunsError(f"line {number} of the June gates log breaks its format")
        gates.append(gate)
    return gates


def missing_gates(gates, code, pin_sha256, before=None):
    """The gates not open for this code and pin: with no recorded result, or whose latest result is a fail. Only
    results dated strictly before `before` count, when it is given (owner decisions, 6 November)."""
    missing = []
    for name in GATE_NAMES:
        results = [(g.date, n, g.result) for n, g in enumerate(gates)
                   if g.gate == name and g.code_hash == code and g.pin_sha256 == pin_sha256
                   and (before is None or g.date < before)]
        if not results or max(results)[2] != "pass":
            missing.append(name)
    return missing


def check_gates(entries, gates, pin_sha256):
    """Every real row has a recorded pass of both gates for its code and the June pin, dated before it."""
    for n, entry in enumerate(entries, start=1):
        if entry.kind == "real":
            missing = missing_gates(gates, entry.code_hash, pin_sha256, before=entry.date)
            if missing:
                raise JuneRunsError(f"entry {n}, a real row, has no recorded pass of the {' and '.join(missing)} "
                                    "gate for its code and the June pin, dated before it")


def check_runs(entries, real_list_hash):
    """Each list has one first entry, `real` only for the real June list and `synthetic` never for it. A later
    entry follows its list's first entry and gives its reason."""
    first = set()
    for n, entry in enumerate(entries, start=1):
        if entry.kind in FIRST_KINDS:
            if entry.list_hash in first:
                raise JuneRunsError(f"entry {n} is a second first entry for its list")
            if entry.kind == "synthetic" and entry.list_hash == real_list_hash:
                raise JuneRunsError(f"entry {n} is marked synthetic but names the real June list")
            if entry.kind == "real" and entry.list_hash != real_list_hash:
                raise JuneRunsError(f"entry {n} is marked real but does not name the real June list")
            first.add(entry.list_hash)
        else:
            if entry.list_hash not in first:
                raise JuneRunsError(f"entry {n} comes before its list's first entry")
            if not entry.reason:
                raise JuneRunsError(f"entry {n} gives no reason")


def matching(entries, list_hash, code_hash):
    """The entries that name both hashes."""
    return [e for e in entries if e.list_hash == list_hash and e.code_hash == code_hash]
