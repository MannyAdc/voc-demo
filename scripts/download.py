"""Download the CFPB's current complaint export (B16).

The CFPB serves only its current export, updated about daily. So this script
fetches today's file, not the July 2026 file this project is pinned to. It
never overwrites a file, and a failed download leaves nothing behind. It
prints the file's name, size and SHA-256, so the file can be pinned.

Run by the owner: python scripts/download.py <empty folder>
"""
import hashlib
import sys
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

URL = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
CHUNK = 1 << 20


def _fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        while block := response.read(CHUNK):
            yield block


def download(url, dest_dir, fetch=_fetch):
    target = Path(dest_dir) / PurePosixPath(urlparse(url).path).name
    if target.exists():
        raise FileExistsError(f"{target.name} already exists, so nothing was downloaded")
    partial = target.with_name(target.name + ".part")
    if partial.exists():
        raise FileExistsError(f"{partial.name} already exists, so nothing was downloaded")
    digest = hashlib.sha256()
    try:
        with open(partial, "wb") as f:
            blocks = fetch(url)
            for block in [blocks] if isinstance(blocks, bytes) else blocks:
                digest.update(block)
                f.write(block)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target, digest.hexdigest()


def main(argv, fetch=_fetch):
    if len(argv) != 1:
        print("usage: python scripts/download.py <empty folder>")
        return 2
    try:
        path, sha = download(URL, argv[0], fetch=fetch)
    except FileExistsError as err:
        print(f"error: {err}")
        return 1
    except Exception as err:  # B21: the type only, never the message
        print(f"error: {type(err).__name__}")
        return 1
    print(f"{path.name}  {path.stat().st_size} bytes  sha256 {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
