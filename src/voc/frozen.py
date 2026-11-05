"""Spec 004, J1: what is frozen before June is scored, and the June run log.

The frozen code's hash is one SHA-256 over every file in the places the spec names, each as its path and its
own SHA-256, in path order. It is computed from the files themselves, not from git, because Databricks'
serverless compute may have no git command. `.gitattributes` keeps every frozen file in LF, so a Windows and a
Linux checkout give the same bytes, and a test checks that the files hashed are exactly the tracked ones.

`runs/JUNE_RUNS.md` only grows. Each row names the June list's hash and the frozen code's hash, and its kind:
`real` or `synthetic` for a list's first entry, then `reproduction`, `resume` or `second`, each with its reason.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

FROZEN_PATHS = ("src", "config", "dbt", "splits", "pyproject.toml", "uv.lock", "cloud",
                ".github/workflows/june_approval.yml", "scripts/june_hash.py")
# Made by Python, pytest and dbt while they run, and never tracked.
SKIP_DIRS = {"__pycache__", ".pytest_cache", "target", "logs", "dbt_packages"}
SKIP_SUFFIXES = (".pyc", ".duckdb", ".wal")
RUNS = Path("runs") / "JUNE_RUNS.md"
JUNE_LIST = Path("splits") / "june"
FIRST_KINDS = ("real", "synthetic")
LATER_KINDS = ("reproduction", "resume", "second")
HASH = re.compile(r"^[0-9a-f]{64}$")


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
        if not line.startswith("|") or line.startswith("| Date ") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            raise JuneRunsError(f"line {number} of the June run log has {len(cells)} columns, not 5")
        entry = Entry(*cells)
        if entry.kind not in FIRST_KINDS + LATER_KINDS:
            raise JuneRunsError(f"line {number} of the June run log has an unknown kind")
        if not (HASH.match(entry.list_hash) and HASH.match(entry.code_hash)):
            raise JuneRunsError(f"line {number} of the June run log has a hash that is not 64 hex characters")
        entries.append(entry)
    return entries


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
