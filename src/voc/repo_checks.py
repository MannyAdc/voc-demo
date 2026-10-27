"""Repo checks that CI runs on every pull request.

- Names: no word from a deny list in any tracked file, commit metadata or
  branch name. The deny list lives outside the repo. A match is reported by
  place only, never by the word, because CI logs may become public.
- Raw data: no tracked file holds CFPB rows with real complaint IDs.
  Synthetic fixtures use IDs that start with SYN-.
- Size: no tracked file is over the size limit.

Run: python -m voc.repo_checks
"""
import csv
import io
import os
import re
import subprocess
import sys
from pathlib import Path

CFPB_COLUMNS = (
    "Date received", "Product", "Sub-product", "Issue", "Sub-issue",
    "Consumer complaint narrative", "Company public response", "Company",
    "State", "ZIP code", "Tags", "Submitted via", "Date sent to company",
    "Company response to consumer", "Timely response?", "Complaint ID",
)
# Built from the column list, so this source file never holds the header row.
CFPB_HEADER = ",".join(CFPB_COLUMNS)
SYNTHETIC_PREFIX = "SYN-"
SIZE_LIMIT = 2_000_000
DENY_LIST_FILE = ".names-denylist"


class DenyListMissing(Exception):
    pass


def load_deny_list(env, path):
    """Names from NAMES_DENYLIST, else from the local file. Fails if there are none."""
    text = env.get("NAMES_DENYLIST")
    if not text and path is not None and Path(path).is_file():
        text = Path(path).read_text(encoding="utf-8")
    names = [line.strip() for line in (text or "").splitlines()]
    names = [n for n in names if n and not n.startswith("#")]
    if not names:
        raise DenyListMissing("the names deny list is missing or empty")
    return names


def _name_pattern(name):
    words = [re.escape(w) for w in name.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", re.IGNORECASE)


def find_name_matches(sources, names):
    """sources maps a place (file path, commit, branch) to its text."""
    patterns = [_name_pattern(n) for n in names]
    matches = []
    for place, text in sources.items():
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(p.search(line) for p in patterns):
                matches.append((place, line_no))
    return matches


def report_name_matches(matches):
    for place, line_no in matches:
        print(f"name match in {place}:{line_no}")


def has_raw_cfpb_rows(text):
    """True if the text has the CFPB header followed by a row with a real ID."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == CFPB_HEADER:
            rest = "".join(lines[i + 1:])
            for row in csv.reader(io.StringIO(rest)):
                if len(row) == len(CFPB_COLUMNS) and not row[-1].startswith(SYNTHETIC_PREFIX):
                    return True
            return False
    return False


def find_large_files(sizes, limit=SIZE_LIMIT):
    return [path for path, size in sizes.items() if size > limit]


def _git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def _tracked_files():
    return [p for p in _git("ls-files", "-z").split("\0") if p]


def _read_text(path):
    data = Path(path).read_bytes()
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _metadata_sources():
    sources = {}
    log = _git("log", "--all", "--format=%h%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e")
    for record in log.split("\x1e"):
        record = record.strip()
        if record:
            sha, *fields = record.split("\x1f")
            sources[f"commit {sha}"] = "\n".join(fields)
    refs = _git("for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes")
    for i, ref in enumerate(refs.splitlines(), start=1):
        sources[f"branch #{i}"] = ref
    return sources


def main():
    failed = False
    files = _tracked_files()
    texts = {path: _read_text(path) for path in files if os.path.isfile(path)}

    try:
        names = load_deny_list(os.environ, DENY_LIST_FILE)
    except DenyListMissing as err:
        print(f"names check: {err}")
        failed = True
    else:
        sources = {p: t for p, t in texts.items() if t is not None}
        sources.update(_metadata_sources())
        matches = find_name_matches(sources, names)
        report_name_matches(matches)
        failed |= bool(matches)
        print(f"names check: {len(matches)} matches")

    raw = [p for p, t in texts.items() if t is not None and has_raw_cfpb_rows(t)]
    for path in raw:
        print(f"raw CFPB data in {path}")
    failed |= bool(raw)
    print(f"raw data check: {len(raw)} files")

    large = find_large_files({p: os.path.getsize(p) for p in texts})
    for path in large:
        print(f"file over {SIZE_LIMIT} bytes: {path}")
    failed |= bool(large)
    print(f"size check: {len(large)} files")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
