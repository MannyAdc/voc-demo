"""B16: the export file is pinned by SHA-256, and the download script never overwrites.

The CFPB serves only its current export, so the July 2026 file cannot be
downloaded again. It is pinned by name, size and SHA-256 in
`config/data_files.toml`, and every command checks the local file against it.
"""
import hashlib
import importlib.util
from pathlib import Path

import pytest

from voc.datafile import DataFileError, find_export, load_pins, sha256_of, verify

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _download_module():
    spec = importlib.util.spec_from_file_location("download", SCRIPTS / "download.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pins(tmp_path, file_name, sha, size):
    pins = tmp_path / "data_files.toml"
    pins.write_text(f'[july_2026]\nfile_name = "{file_name}"\nsha256 = "{sha}"\nsize_bytes = {size}\n',
                    encoding="utf-8")
    return pins


def test_B16_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "a.csv"
    f.write_bytes(b"x" * 100_000)
    assert sha256_of(f) == hashlib.sha256(b"x" * 100_000).hexdigest()


def test_B16_a_file_that_matches_its_pin_is_accepted(tmp_path):
    f = tmp_path / "export.csv"
    f.write_bytes(b"abc")
    pins = load_pins(_pins(tmp_path, "export.csv", sha256_of(f), 3))
    verify(f, pins["july_2026"])


@pytest.mark.parametrize("change", ["content", "size", "name"])
def test_B16_a_file_that_differs_from_its_pin_is_refused(tmp_path, change):
    f = tmp_path / "export.csv"
    f.write_bytes(b"abc")
    sha, size, name = sha256_of(f), 3, "export.csv"
    if change == "content":
        sha = "0" * 64
    elif change == "size":
        size = 4
    else:
        name = "other.csv"
    pin = load_pins(_pins(tmp_path, name, sha, size))["july_2026"]
    with pytest.raises(DataFileError, match="does not match the pinned file"):
        verify(f, pin)


def test_B16_the_export_is_the_one_csv_in_the_data_folder(tmp_path):
    (tmp_path / "export.csv").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert find_export(tmp_path).name == "export.csv"


@pytest.mark.parametrize("count", [0, 2])
def test_B16_a_data_folder_with_no_csv_or_several_is_an_error(tmp_path, count):
    for i in range(count):
        (tmp_path / f"e{i}.csv").write_text("x", encoding="utf-8")
    with pytest.raises(DataFileError):
        find_export(tmp_path)


def test_B16_an_excel_lock_file_and_a_folder_named_csv_are_ignored(tmp_path):
    (tmp_path / "export.CSV").write_text("x", encoding="utf-8")
    (tmp_path / "~$export.csv").write_text("x", encoding="utf-8")
    (tmp_path / "old.csv").mkdir()
    assert find_export(tmp_path).name == "export.CSV"


def test_B16_a_failed_download_leaves_no_file_behind(tmp_path):
    download = _download_module()

    def broken(url):
        yield b"part of the file"
        raise OSError("connection reset")

    with pytest.raises(OSError):
        download.download("https://example.invalid/complaints.csv.zip", tmp_path, fetch=broken)
    assert list(tmp_path.iterdir()) == []


def test_B16_download_never_overwrites_a_partial_file_either(tmp_path):
    download = _download_module()
    (tmp_path / "complaints.csv.zip.part").write_bytes(b"left from before")
    with pytest.raises(FileExistsError):
        download.download("https://example.invalid/complaints.csv.zip", tmp_path, fetch=lambda url: b"new")
    assert (tmp_path / "complaints.csv.zip.part").read_bytes() == b"left from before"


def test_B21_the_download_script_prints_only_the_error_type(tmp_path, capsys):
    download = _download_module()

    def hostile(url):
        raise OSError("SYNHOSTILE text from a server")

    assert download.main([str(tmp_path)], fetch=hostile) != 0
    out = capsys.readouterr().out
    assert "SYNHOSTILE" not in out and "error: OSError" in out


def test_B16_the_committed_pin_file_has_the_july_export():
    pins = load_pins(Path(__file__).resolve().parent.parent / "config" / "data_files.toml")
    pin = pins["july_2026"]
    assert len(pin["sha256"]) == 64 and pin["size_bytes"] > 0 and pin["file_name"].endswith(".csv")


def test_B16_download_writes_a_new_file_and_reports_its_hash(tmp_path):
    download = _download_module()
    path, sha = download.download("https://example.invalid/complaints.csv.zip", tmp_path,
                                  fetch=lambda url: b"zip bytes")
    assert path.read_bytes() == b"zip bytes"
    assert sha == hashlib.sha256(b"zip bytes").hexdigest()


def test_B16_download_never_overwrites_an_existing_file(tmp_path):
    download = _download_module()
    (tmp_path / "complaints.csv.zip").write_bytes(b"old")
    with pytest.raises(FileExistsError):
        download.download("https://example.invalid/complaints.csv.zip", tmp_path, fetch=lambda url: b"new")
    assert (tmp_path / "complaints.csv.zip").read_bytes() == b"old"
