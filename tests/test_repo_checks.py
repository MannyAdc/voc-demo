"""CI repo checks: names, raw CFPB data, file size, unreadable files.

The names here are invented tokens. The real deny list lives outside the repo.
"""
import gzip
import io
import subprocess
import zipfile

import pytest

from voc.repo_checks import (
    CFPB_HEADER,
    DenyListMissing,
    find_large_files,
    find_name_matches,
    has_raw_cfpb_rows,
    load_deny_list,
    place_for,
    scan_repository,
    texts_in_blob,
)

NAMES = ["Qwertyname", "Zorblax Corp"]


def _row(complaint_id):
    fields = ["2026-07-01", "Credit card"] + [""] * 13 + [complaint_id]
    return ",".join(fields)


# Names check


def test_a_name_is_found_with_its_source_and_line():
    sources = {"README.md": "hello\nwritten by qwertyname\n"}
    assert find_name_matches(sources, NAMES) == [("README.md", 2)]


def test_a_multi_word_name_is_found():
    assert find_name_matches({"a.txt": "a zorblax corp b"}, NAMES) == [("a.txt", 1)]


def test_a_name_inside_a_longer_word_is_not_a_match():
    assert find_name_matches({"a.txt": "Qwertynames xQwertyname"}, NAMES) == []


@pytest.mark.parametrize("text", ["first_qwertyname_x", "qwertyname2", "id=qwertyname@example"])
def test_a_name_joined_by_underscores_digits_or_symbols_is_found(text):
    assert find_name_matches({"a.txt": text}, NAMES) == [("a.txt", 1)]


def test_a_multi_word_name_wrapped_across_lines_is_found():
    assert find_name_matches({"a.md": "one\nby Zorblax\nCorp here"}, NAMES) == [("a.md", 2)]


def test_unicode_forms_of_a_name_are_found():
    fullwidth = "Ｑｗｅｒｔｙｎａｍｅ"
    assert find_name_matches({"a.txt": fullwidth}, NAMES) == [("a.txt", 1)]
    composed_name = ["Zoé"]
    decomposed_text = "by Zoé today"
    assert find_name_matches({"a.txt": decomposed_text}, composed_name) == [("a.txt", 1)]


def test_a_path_with_a_name_is_reported_by_number_only():
    assert place_for("notes/qwertyname.md", 3, NAMES) == "file #3"
    assert place_for("notes/plain.md", 3, NAMES) == "notes/plain.md"


def test_the_deny_list_is_read_from_the_environment_first():
    env = {"NAMES_DENYLIST": "Qwertyname\n# a comment\n\nZorblax Corp\n"}
    assert load_deny_list(env, path=None) == NAMES


def test_the_deny_list_is_read_from_the_local_file(tmp_path):
    f = tmp_path / ".names-denylist"
    f.write_text("Qwertyname\n", encoding="utf-8")
    assert load_deny_list({}, path=f) == ["Qwertyname"]


@pytest.mark.parametrize("env", [{}, {"NAMES_DENYLIST": ""}, {"NAMES_DENYLIST": "# only\n\n"}])
def test_a_missing_or_empty_deny_list_fails(env, tmp_path):
    with pytest.raises(DenyListMissing):
        load_deny_list(env, path=tmp_path / "does-not-exist")


def test_the_report_never_prints_the_name(capsys):
    from voc.repo_checks import report_name_matches

    report_name_matches([("README.md", 2)])
    out = capsys.readouterr()
    text = out.out + out.err
    assert "README.md:2" in text
    assert "qwertyname" not in text.lower()


# Raw data check


def test_the_header_is_built_from_the_sixteen_columns():
    assert len(CFPB_HEADER.split(",")) == 16
    assert CFPB_HEADER.endswith("Complaint ID")


def test_a_file_with_the_header_and_a_real_id_is_raw_data():
    text = CFPB_HEADER + "\n" + _row("SYN-1") + "\n" + _row("12345678") + "\n"
    assert has_raw_cfpb_rows(text)


def test_a_synthetic_fixture_is_not_raw_data():
    text = CFPB_HEADER + "\n" + _row("SYN-1") + "\n" + _row("SYN-2") + "\n"
    assert not has_raw_cfpb_rows(text)


def test_a_header_with_a_bom_and_quotes_is_still_found():
    quoted = ",".join(f'"{c}"' for c in CFPB_HEADER.split(","))
    text = "﻿" + quoted + "\n" + _row("12345678") + "\n"
    assert has_raw_cfpb_rows(text)


def test_a_header_with_extra_or_reordered_columns_is_still_found():
    text = "Complaint ID,Consumer complaint narrative,Extra\n12345678,some text,x\n"
    assert has_raw_cfpb_rows(text)
    assert not has_raw_cfpb_rows("Complaint ID,Consumer complaint narrative\nSYN-1,text\n")


def test_a_file_without_the_header_is_not_checked_as_csv():
    assert not has_raw_cfpb_rows("print('hello')\n" + _row("12345678"))


# File size check


def test_files_over_the_limit_are_listed():
    sizes = {"small.txt": 10, "big.bin": 3_000_000}
    assert find_large_files(sizes, limit=2_000_000) == ["big.bin"]


# Reading blobs


def test_valid_utf8_with_a_nul_byte_is_still_checked_as_text():
    assert texts_in_blob("a.py", b"x = 1\x00 qwertyname") == [("a.py", "x = 1\x00 qwertyname")]


def test_utf16_text_is_decoded_and_checked():
    data = "hello qwertyname".encode("utf-16")
    assert texts_in_blob("a.txt", data) == [("a.txt", "hello qwertyname")]


def test_zip_and_gzip_members_are_checked():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("inner/qwertyname.txt", "body")
    found = texts_in_blob("a.zip", buf.getvalue())
    assert ("a.zip!inner/qwertyname.txt", "inner/qwertyname.txt") in found
    assert ("a.zip!inner/qwertyname.txt", "body") in found
    assert texts_in_blob("a.gz", gzip.compress(b"plain text")) == [("a.gz", "plain text")]


def test_an_unreadable_file_returns_none_but_images_are_allowed():
    assert texts_in_blob("a.bin", b"\x00\xc3\x28\xff binary") is None  # not valid UTF-8
    assert texts_in_blob("a.png", b"\x89PNG\x00\x01") == []


# Whole repository, including history


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "keep.txt").write_text("nothing here\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_a_name_deleted_from_the_tree_is_still_found_in_history(repo):
    (repo / "gone.txt").write_text("by qwertyname\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add")
    (repo / "gone.txt").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "remove")
    report = scan_repository(repo, NAMES, env={})
    assert report.name_hits and all("qwertyname" not in h.lower() for h in report.name_hits)


def test_raw_data_deleted_from_the_tree_is_still_found_in_history(repo):
    (repo / "slice.csv").write_text(CFPB_HEADER + "\n" + _row("12345678") + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add")
    _git(repo, "rm", "-q", "slice.csv")
    _git(repo, "commit", "-q", "-m", "remove")
    assert scan_repository(repo, NAMES, env={}).raw_hits


def test_tag_names_tag_messages_and_commit_metadata_are_checked(repo):
    _git(repo, "tag", "-a", "v1", "-m", "release by Zorblax Corp")
    assert scan_repository(repo, NAMES, env={}).name_hits


def test_pull_request_title_and_body_are_checked(repo):
    report = scan_repository(repo, NAMES, env={"PR_TITLE": "fix", "PR_BODY": "thanks qwertyname"})
    assert report.name_hits


def test_a_clean_repository_passes(repo):
    report = scan_repository(repo, NAMES, env={})
    assert not (report.name_hits or report.raw_hits or report.large_hits or report.unchecked)
