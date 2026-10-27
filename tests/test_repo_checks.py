"""CI repo checks: names, raw CFPB data, file size.

The names here are invented tokens. The real deny list lives outside the repo.
"""
import pytest

from voc.repo_checks import (
    CFPB_HEADER,
    DenyListMissing,
    find_large_files,
    find_name_matches,
    has_raw_cfpb_rows,
    load_deny_list,
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
    assert find_name_matches({"a.txt": "Qwertynames Qwertyname2"}, NAMES) == []


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


def test_a_file_without_the_header_is_not_checked_as_csv():
    assert not has_raw_cfpb_rows("print('hello')\n" + _row("12345678"))


# File size check


def test_files_over_the_limit_are_listed():
    sizes = {"small.txt": 10, "big.bin": 3_000_000}
    assert find_large_files(sizes, limit=2_000_000) == ["big.bin"]
