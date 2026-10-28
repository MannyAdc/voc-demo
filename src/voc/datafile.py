"""B16: find the export file in the data folder and check it against its pin."""
import hashlib
import tomllib
from pathlib import Path


class DataFileError(ValueError):
    """An error whose message is ours, so it is safe to print (it never holds data)."""


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pins(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def find_export(folder):
    """The one CSV file in the data folder."""
    files = sorted(Path(folder).glob("*.csv"))
    if len(files) != 1:
        raise DataFileError(f"the data folder must hold exactly one CSV file, it holds {len(files)}")
    return files[0]


def verify(path, pin):
    path = Path(path)
    if (path.name != pin["file_name"] or path.stat().st_size != pin["size_bytes"]
            or sha256_of(path) != pin["sha256"]):
        raise DataFileError("the data file does not match the pinned file in config/data_files.toml")
