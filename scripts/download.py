"""Download the CFPB's current complaint export (B16).

The CFPB serves only its current export, updated about daily. So this script
fetches today's file, not the July 2026 file this project is pinned to. It
never overwrites a file. It prints the file's name, size and SHA-256.

Run by the owner: python scripts/download.py <empty folder>
"""
import hashlib
import sys
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

URL = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"


def _fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def download(url, dest_dir, fetch=_fetch):
    target = Path(dest_dir) / PurePosixPath(urlparse(url).path).name
    if target.exists():
        raise FileExistsError(f"{target.name} already exists, so nothing was downloaded")
    data = fetch(url)
    target.write_bytes(data)
    return target, hashlib.sha256(data).hexdigest()


def main(argv):
    if len(argv) != 1:
        print("usage: python scripts/download.py <empty folder>")
        return 2
    path, sha = download(URL, argv[0])
    print(f"{path.name}  {path.stat().st_size} bytes  sha256 {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
