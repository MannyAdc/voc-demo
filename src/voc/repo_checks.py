"""Repo checks that CI runs on every push and pull request.

The whole history is checked, not only the current files, because the full
history becomes public.

- Names: no word from a deny list in any file, file path, commit metadata,
  branch, tag, or pull request title and body. The deny list lives outside
  the repo. A match is reported by place only, never by the word, because
  CI logs may become public. A path that holds a name is shown as a number.
- Raw data: no file holds CFPB rows with real complaint IDs. Synthetic
  fixtures use IDs that start with SYN-.
- Size: no file is over the size limit.
- Unchecked: a file that cannot be read as text, an archive or an image
  fails, so nothing passes just because it could not be read.

Run: python -m voc.repo_checks
"""
import csv
import gzip
import io
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

CFPB_COLUMNS = (
    "Date received", "Product", "Sub-product", "Issue", "Sub-issue",
    "Consumer complaint narrative", "Company public response", "Company",
    "State", "ZIP code", "Tags", "Submitted via", "Date sent to company",
    "Company response to consumer", "Timely response?", "Complaint ID",
)
# Built from the column list, so this source file never holds the header row.
CFPB_HEADER = ",".join(CFPB_COLUMNS)
ID_COLUMN = "Complaint ID"
TEXT_COLUMN = "Consumer complaint narrative"
SYNTHETIC_PREFIX = "SYN-"
SIZE_LIMIT = 2_000_000
DENY_LIST_FILE = ".names-denylist"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp"}
LETTER = r"[^\W\d_]"


class DenyListMissing(Exception):
    pass


@dataclass
class Report:
    name_hits: list = field(default_factory=list)
    raw_hits: list = field(default_factory=list)
    large_hits: list = field(default_factory=list)
    unchecked: list = field(default_factory=list)


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


# Names


def _normal(text):
    return unicodedata.normalize("NFKC", text).casefold()


def _name_pattern(name):
    # Boundaries are letters only, so "first_last", "name2" and "name@" still match.
    words = [re.escape(_normal(w)) for w in name.split()]
    return re.compile(rf"(?<!{LETTER})" + r"\s+".join(words) + rf"(?!{LETTER})")


def find_name_matches(sources, names):
    """sources maps a place to its text, or is a list of (place, text) pairs."""
    pairs = sources.items() if hasattr(sources, "items") else sources
    patterns = [_name_pattern(n) for n in names]
    matches = []
    for place, text in pairs:
        normal = _normal(text)
        lines = sorted({normal.count("\n", 0, m.start()) + 1
                        for p in patterns for m in p.finditer(normal)})
        matches.extend((place, line) for line in lines)
    return matches


def place_for(path, index, names):
    """The path itself, or a number if the path holds a name."""
    return f"file #{index}" if find_name_matches({"path": path}, names) else path


def report_name_matches(matches):
    for place, line_no in matches:
        print(f"name match in {place}:{line_no}")


# Raw data


def has_raw_cfpb_rows(text):
    """True if the text has a CFPB-style header and a row with a real complaint ID."""
    if ID_COLUMN not in text or TEXT_COLUMN not in text:
        return False
    try:
        id_index = None
        for row in csv.reader(io.StringIO(text.lstrip("﻿"))):
            cells = [c.strip().lstrip("﻿") for c in row]
            if id_index is None:
                if ID_COLUMN in cells and TEXT_COLUMN in cells:
                    id_index = cells.index(ID_COLUMN)
            elif len(cells) > id_index and cells[id_index] and not cells[id_index].startswith(SYNTHETIC_PREFIX):
                return True
    except csv.Error:
        return False
    return False


def find_large_files(sizes, limit=SIZE_LIMIT):
    return [path for path, size in sizes.items() if size > limit]


# Reading blobs


def _decode(data):
    """Text if the bytes are UTF-16 with a BOM or valid UTF-8 (NUL bytes allowed), else None."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def texts_in_blob(path, data):
    """(place, text) pairs to check, [] for an allowed image, None if unreadable."""
    if PurePosixPath(path).suffix.lower() in IMAGE_SUFFIXES:
        return []
    if data[:2] == b"\x1f\x8b":
        text = _decode(gzip.decompress(data))
        return None if text is None else [(path, text)]
    if data[:4] == b"PK\x03\x04":
        found = []
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.namelist():
                place = f"{path}!{member}"
                found.append((place, member))
                inner = texts_in_blob(member, archive.read(member))
                if inner is None:
                    return None
                found.extend((place, text) for _, text in inner)
        return found
    text = _decode(data)
    return None if text is None else [(path, text)]


# Whole repository


def _git(root, *args, data=None):
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, input=data)
    return result.stdout


def _blobs(root):
    """Every blob in the history: (sha, first path seen, size, content)."""
    paths = {}
    for line in _git(root, "rev-list", "--objects", "--all").decode("utf-8", "replace").splitlines():
        sha, _, path = line.partition(" ")
        if path:
            paths.setdefault(sha, path)
    request = "".join(f"{sha}\n" for sha in paths).encode()
    out = _git(root, "cat-file", "--batch", data=request)
    blobs, pos = [], 0
    while pos < len(out):
        end = out.index(b"\n", pos)
        sha, kind, size = out[pos:end].decode().split()
        size = int(size)
        content = out[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
        if kind == "blob":
            blobs.append((sha, paths[sha], size, content))
    return blobs


def _metadata(root, env):
    pairs = []
    log = _git(root, "log", "--all", "--format=%h%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e")
    for record in log.decode("utf-8", "replace").split("\x1e"):
        record = record.strip()
        if record:
            sha, *fields = record.split("\x1f")
            pairs.append((f"commit {sha}", "\n".join(fields)))
    refs = _git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes", "refs/tags")
    for i, ref in enumerate(refs.decode("utf-8", "replace").splitlines(), start=1):
        pairs.append((f"ref #{i}", ref))
    tags = _git(root, "for-each-ref", "--format=%(taggername) %(taggeremail)%0a%(contents)%1e", "refs/tags")
    for i, tag in enumerate(tags.decode("utf-8", "replace").split("\x1e"), start=1):
        if tag.strip():
            pairs.append((f"tag #{i}", tag))
    for name in ("PR_TITLE", "PR_BODY"):
        if env.get(name):
            pairs.append((f"pull request {name.split('_')[1].lower()}", env[name]))
    return pairs


def scan_repository(root, names, env):
    report = Report()
    blobs = _blobs(root)
    all_paths = sorted({path for _, path, _, _ in blobs})
    index = {path: i for i, path in enumerate(all_paths, start=1)}

    sources = []
    for sha, path, size, content in blobs:
        place = f"{place_for(path, index[path], names)} (blob {sha[:8]})"
        sources.append((place, path))
        if size > SIZE_LIMIT:
            report.large_hits.append(place)
        texts = texts_in_blob(path, content)
        if texts is None:
            report.unchecked.append(place)
            continue
        for part, (_, text) in enumerate(texts):
            label = place if part == 0 else f"{place} part {part}"
            sources.append((label, text))
            if has_raw_cfpb_rows(text) and place not in report.raw_hits:
                report.raw_hits.append(place)
    sources.extend(_metadata(root, env))
    report.name_hits = [f"{place}:{line}" for place, line in find_name_matches(sources, names)]
    return report


def main():
    try:
        names = load_deny_list(os.environ, DENY_LIST_FILE)
    except DenyListMissing as err:
        print(f"names check: {err}")
        names = None
    report = scan_repository(".", names or [], os.environ)
    for hit in report.name_hits:
        print(f"name match in {hit}")
    for hit in report.raw_hits:
        print(f"raw CFPB data in {hit}")
    for hit in report.large_hits:
        print(f"file over {SIZE_LIMIT} bytes: {hit}")
    for hit in report.unchecked:
        print(f"could not be checked: {hit}")
    print(f"names: {len(report.name_hits)}, raw data: {len(report.raw_hits)}, "
          f"over size: {len(report.large_hits)}, unchecked: {len(report.unchecked)}")
    failed = names is None or any([report.name_hits, report.raw_hits, report.large_hits, report.unchecked])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
