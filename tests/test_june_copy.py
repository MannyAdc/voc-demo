"""Spec 004, J11 and J13: the copy script brings Job B's two results files from the results volume into the repo,
signed in as the read-only reader account, and checks them again (pull request 6b, part 6).

No test opens a network connection: the reader's HTTP calls go to a fake. Fake secrets are built while the test
runs. Every results file is synthetic.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOST = "dbc-synthetic.cloud.databricks.com"


def _secret():
    return "dose" + "SYN" + "9" * 30


class FakeHTTP:
    """Databricks' token endpoint and Files API, as the reader sees them."""

    def __init__(self, folders=None, files=None, token_status=200):
        self.folders = folders or {}
        self.files = files or {}
        self.token_status = token_status
        self.calls = []

    def __call__(self, url, data=None, headers=None, method="GET"):
        self.calls.append((method, url, dict(headers or {}), data))
        if url == f"https://{HOST}/oidc/v1/token":
            return self.token_status, json.dumps({"access_token": "tok" + "en", "expires_in": 3600}).encode()
        for path, names in self.folders.items():
            if url == f"https://{HOST}/api/2.0/fs/directories{path}":
                if names is None:
                    return 403, b""
                return 200, json.dumps({"contents": [{"path": f"{path}/{n}", "name": n, "is_directory": False}
                                                     for n in names]}).encode()
        for path, body in self.files.items():
            if url == f"https://{HOST}/api/2.0/fs/files{path}":
                return 200, body
        return 404, b""


def _reader(http):
    from voc import june_copy

    return june_copy.Reader(HOST, "reader-id", _secret(), request=http)


def _folder(run_id=900002):
    from voc import june_copy

    return f"{june_copy.RESULTS}/june-{run_id}"


def _http(names=("v1_june.csv", "v1_june.json")):
    folder = _folder()
    return FakeHTTP(folders={folder: list(names)},
                    files={f"{folder}/v1_june.csv": b"complaint_id\n", f"{folder}/v1_june.json": b'{"set": "june"}'})


def test_J13_the_reader_signs_in_with_its_own_client_and_basic_auth(monkeypatch):
    from voc import june_copy

    http = _http()
    _reader(http).names(_folder())
    method, url, headers, data = http.calls[0]
    assert (method, url) == ("POST", f"https://{HOST}/oidc/v1/token")
    assert headers["Authorization"].startswith("Basic ") and b"grant_type=client_credentials" in data
    assert f"scope={june_copy.SCOPE}".encode() in data
    assert http.calls[1][2]["Authorization"] == "Bearer " + "tok" + "en"


def test_J13_the_reader_comes_from_its_own_variables_never_a_default_token(tmp_path):
    from voc import june_copy

    env = {"VOC_DATABRICKS_HOST": HOST, "VOC_READER_CLIENT_ID": "reader-id", "VOC_READER_CLIENT_SECRET": _secret(),
           "DATABRICKS_TOKEN": "dapi" + "SYN" * 10, "DATABRICKS_CONFIG_PROFILE": "DEFAULT"}
    reader = june_copy.reader_from(env)
    assert (reader.host, reader.client_id) == (HOST, "reader-id")
    with pytest.raises(june_copy.CopyError, match="^the reader's client ID and secret are not set$"):
        june_copy.reader_from({"VOC_DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": "dapi" + "SYN" * 10})


def test_J11_the_copy_brings_exactly_the_two_files_checks_them_and_writes_them(tmp_path, monkeypatch):
    from voc import june_copy, june_results

    checked = []
    monkeypatch.setattr(june_results, "check", lambda root, c, j, listed=None: checked.append((c, j)))
    written = june_copy.copy(tmp_path, 900002, _reader(_http()))
    assert checked == [("complaint_id\n", '{"set": "june"}')]
    assert (tmp_path / "results" / "june" / "v1_june.csv").read_bytes() == b"complaint_id\n"
    assert (tmp_path / "results" / "june" / "v1_june.json").read_bytes() == b'{"set": "june"}'
    assert written == ["v1_june.csv", "v1_june.json"]


@pytest.mark.parametrize("names", [("v1_june.csv",), ("v1_june.csv", "v1_june.json", "DRY_RUN.txt"),
                                   ("v1_june.csv", "other.json")])
def test_J11_a_folder_that_does_not_hold_exactly_the_two_files_is_refused(tmp_path, monkeypatch, names):
    from voc import june_copy, june_results

    monkeypatch.setattr(june_results, "check", lambda *a, **k: None)
    with pytest.raises(june_copy.CopyError, match="^the results folder must hold exactly v1_june.csv and "
                                                  "v1_june.json$"):
        june_copy.copy(tmp_path, 900002, _reader(_http(names)))
    assert not (tmp_path / "results").exists()


def test_J11_files_that_fail_their_check_are_never_written(tmp_path, monkeypatch):
    from voc import june_copy, june_results

    def refused(root, c, j, listed=None):
        raise june_results.JuneResultsError("v1_june.json lacks a required key")

    monkeypatch.setattr(june_results, "check", refused)
    with pytest.raises(june_copy.CopyError, match="^v1_june.json lacks a required key$"):
        june_copy.copy(tmp_path, 900002, _reader(_http()))
    assert not (tmp_path / "results").exists()


def test_J11_results_already_in_the_repo_are_never_overwritten(tmp_path, monkeypatch):
    from voc import june_copy, june_results

    monkeypatch.setattr(june_results, "check", lambda *a, **k: None)
    (tmp_path / "results" / "june").mkdir(parents=True)
    (tmp_path / "results" / "june" / "v1_june.csv").write_text("old", encoding="utf-8")
    with pytest.raises(june_copy.CopyError, match="^results/june already holds the June results$"):
        june_copy.copy(tmp_path, 900002, _reader(_http()))
    assert (tmp_path / "results" / "june" / "v1_june.csv").read_text(encoding="utf-8") == "old"


def test_J5_an_http_refusal_gives_its_status_only_and_never_the_secret(tmp_path, capsys):
    from voc import june_copy

    with pytest.raises(june_copy.CopyError) as caught:
        june_copy.copy(tmp_path, 900002, _reader(FakeHTTP(token_status=401)))
    assert str(caught.value) == "Databricks refused the reader's sign-in: HTTP 401"
    assert _secret() not in str(caught.value) + capsys.readouterr().out


def test_J13_the_reader_check_passes_when_results_are_readable_and_raw_data_is_not():
    from voc import june_copy

    http = FakeHTTP(folders={june_copy.RESULTS: ["june-900002"], june_copy.RAW: None})
    assert june_copy.check_reader(_reader(http)) == ["results volume readable | yes", "raw volume refused | yes",
                                                     "verdict | PASS"]


def test_J13_the_reader_check_fails_when_raw_data_is_readable():
    from voc import june_copy

    http = FakeHTTP(folders={june_copy.RESULTS: ["june-900002"], june_copy.RAW: ["incoming"]})
    assert june_copy.check_reader(_reader(http))[-1] == "verdict | FAIL"


def test_J11_the_script_takes_one_run_id_and_prints_only_names_and_counts():
    text = (REPO / "scripts" / "copy_june_results.py").read_text(encoding="utf-8")
    assert "june_copy" in text and "--check-reader" in text and "print(" in text
    assert "DATABRICKS_TOKEN" not in text and "databricks.sdk" not in text
