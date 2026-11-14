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

    statuses = {}

    def __call__(self, url, data=None, headers=None, method="GET"):
        self.calls.append((method, url, dict(headers or {}), data))
        for part, status in self.statuses.items():
            if part in url:
                return status, b""
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
    # Changed with the scope files:read: the form encodes its colon, so the test compares the encoded form.
    assert __import__("urllib.parse").parse.urlencode({"scope": june_copy.SCOPE}).encode() in data
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
    # Changed in the fix rounds of #114: the check also needs the secret scope refused, with a 403, since a 404 is no
    # longer proof of a refusal.
    http.statuses = {"/api/2.0/secrets/list": 403}
    assert june_copy.check_reader(_reader(http)) == ["results volume readable | yes", "raw volume refused | yes",
                                                     "secret scope refused | yes", "verdict | PASS"]


def test_J13_the_reader_check_fails_when_raw_data_is_readable():
    from voc import june_copy

    http = FakeHTTP(folders={june_copy.RESULTS: ["june-900002"], june_copy.RAW: ["incoming"]})
    assert june_copy.check_reader(_reader(http))[-1] == "verdict | FAIL"


def test_J11_the_script_takes_one_run_id_and_prints_only_names_and_counts():
    text = (REPO / "scripts" / "copy_june_results.py").read_text(encoding="utf-8")
    assert "june_copy" in text and "--check-reader" in text and "print(" in text
    assert "DATABRICKS_TOKEN" not in text and "databricks.sdk" not in text


# The review of #114 (serious 1, minors 2 and 6, nits 8 and 9)


def _check(raw=None, scope=403, results=("june-900002",), extra=None):
    from voc import june_copy

    http = FakeHTTP(folders={june_copy.RESULTS: list(results) if results is not None else None})
    http.statuses = {"/api/2.0/fs/directories" + june_copy.RAW: raw if raw is not None else 403,
                     "/api/2.0/secrets/list": scope, **(extra or {})}
    return june_copy.check_reader(_reader(http))


# Changed in the second fix round of #114: only 403 counts (test_J13_a_404_is_not_proof_of_a_refusal).
@pytest.mark.parametrize("raw", [403])
def test_J13_only_a_real_refusal_counts_as_refused(raw):
    lines = _check(raw=raw)
    assert "raw volume refused | yes" in lines and "secret scope refused | yes" in lines
    assert lines[-1] == "verdict | PASS"


@pytest.mark.parametrize("raw", [0, 401, 429, 500, 302, 200])
def test_J13_a_raw_volume_answer_that_is_not_a_refusal_fails_the_check(raw):
    """Serious 1: a network failure, a sign-in refusal, rate limiting, a server error or a redirect is not a
    refusal, so the check can never pass on one."""
    lines = _check(raw=raw)
    assert lines[-1] == "verdict | FAIL"
    assert "raw volume refused | yes" not in lines


@pytest.mark.parametrize("scope", [200, 0, 500])
def test_J13_the_reader_must_be_refused_on_the_secret_scope(scope):
    """Minor 2: the reader has no right on the secret scope that holds the API key."""
    lines = _check(scope=scope)
    assert lines[-1] == "verdict | FAIL"


def test_J13_the_secret_scope_check_lists_only_the_scope_s_names():
    from voc import june_copy

    http = FakeHTTP(folders={june_copy.RESULTS: ["june-900002"]})
    http.statuses = {"/api/2.0/fs/directories" + june_copy.RAW: 403, "/api/2.0/secrets/list": 403}
    june_copy.check_reader(_reader(http))
    urls = [url for _, url, _, _ in http.calls]
    assert f"https://{HOST}/api/2.0/secrets/list?scope=voc-june" in urls
    assert not any("/secrets/get" in url for url in urls)


def test_J13_a_results_volume_that_cannot_be_listed_fails_the_check():
    assert _check(results=None)[-1] == "verdict | FAIL"


def test_J11_a_listing_with_more_pages_is_refused(tmp_path):
    """Nit 8: the results folder holds two files, so a second page means something else is there."""
    from voc import june_copy

    http = _http()
    folder = _folder()
    body = json.dumps({"contents": [{"name": "v1_june.csv"}, {"name": "v1_june.json"}], "next_page_token": "x"})
    http.statuses = {}
    original = http.__call__

    def paged(url, data=None, headers=None, method="GET"):
        if url.endswith("/api/2.0/fs/directories" + folder):
            http.calls.append((method, url, dict(headers or {}), data))
            return 200, body.encode()
        return original(url, data, headers, method)

    with pytest.raises(june_copy.CopyError, match="^the results folder's listing has more than one page$"):
        june_copy.copy(tmp_path, 900002, _reader(paged))


def test_J11_a_listing_item_that_is_not_an_object_is_refused(tmp_path):
    """Nit 9."""
    from voc import june_copy

    folder = _folder()

    def odd(url, data=None, headers=None, method="GET"):
        if url.endswith("/oidc/v1/token"):
            return 200, json.dumps({"access_token": "tok" + "en"}).encode()
        if url.endswith("/api/2.0/fs/directories" + folder):
            return 200, json.dumps({"contents": ["v1_june.csv"]}).encode()
        return 404, b""

    with pytest.raises(june_copy.CopyError, match="^the Files API's folder listing could not be read$"):
        june_copy.copy(tmp_path, 900002, _reader(odd))


def test_J13_the_reader_asks_for_the_files_scope_read_only():
    """Owner's check of the secret's form, 10 November: Databricks calls all-apis not recommended. The reader's token
    reads files only."""
    from voc import june_copy

    assert june_copy.SCOPE == "files:read"


# The second review of #114, minor 1: a 404 also means "not there", so a typo in a path would look like a refusal.


@pytest.mark.parametrize("raw, scope", [(404, 403), (403, 404)])
def test_J13_a_404_is_not_proof_of_a_refusal(raw, scope):
    lines = _check(raw=raw, scope=scope)
    assert lines[-1] == "verdict | FAIL"


@pytest.mark.parametrize("name", ["v1_june.csv", "v1_june.json"])
def test_J11_both_june_results_files_can_be_committed(tmp_path, name):
    # The results PR commits both files, which hold IDs, labels, positions, reasons and counts only (J11). The gate
    # runs the tests on a copy that is not a git repo, so the test makes its own repo with a copy of `.gitignore`.
    import shutil
    import subprocess

    import git_helper

    shutil.copy(REPO / ".gitignore", tmp_path / ".gitignore")
    git_helper.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    found = subprocess.run(["git", "check-ignore", "--no-index", "-q", f"results/june/{name}"], cwd=tmp_path,
                           capture_output=True)
    assert found.returncode == 1
