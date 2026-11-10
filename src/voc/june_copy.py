"""Spec 004, J11 and J13: the copy of Job B's two results files from the results volume into the repo, signed in as
the read-only reader account, and the check of that account (pull request 6b, part 6).

The reader `voc-results-reader` is a service principal with three grants only: USE CATALOG on the catalog, USE
SCHEMA on the results schema and READ VOLUME on `voc_results`, which holds no complaint data (J13). Its client ID and
secret live only in the owner's git-ignored `.env`, as `VOC_READER_CLIENT_ID` and `VOC_READER_CLIENT_SECRET`, and
only this module reads them. It never signs in with a default profile or the environment's `DATABRICKS_TOKEN`. It
calls Databricks' token endpoint and Files API over plain HTTPS, with no SDK.

The copy reads exactly `v1_june.csv` and `v1_june.json` from `june-<Job B run ID>`, refuses a folder holding anything
else, checks them again with `june_results.check`, and writes them to `results/june/`, never over files already
there. The reader check proves the account can list the results volume and is refused on the raw volume.

B21 and J5: nothing here prints a secret or a file's content. Every refusal holds fixed text and HTTP statuses only.
"""
import base64
import json
import urllib.parse
from pathlib import Path

from voc import june_results
from voc.approval import HOST, _request

RESULTS = "/Volumes/workspace/voc_results/voc_results"
RAW = "/Volumes/workspace/default/voc_raw"
# The token's scope. The reader's rights come from its grants, which allow reading one volume and nothing else.
SCOPE = "all-apis"
OUT = Path("results") / "june"


class CopyError(ValueError):
    """A refusal with fixed text and HTTP statuses only (B21, J5)."""


class Reader:
    """The reader's sign-in and the Files API, over plain HTTPS."""

    def __init__(self, host, client_id, client_secret, request=_request):
        if not isinstance(host, str) or not HOST.fullmatch(host):
            raise CopyError("VOC_DATABRICKS_HOST must be the workspace's bare host name")
        if not client_id or not client_secret:
            raise CopyError("the reader's client ID and secret are not set")
        self.host, self.client_id, self._secret, self._request = host, client_id, client_secret, request
        self._token = None

    def _bearer(self):
        if self._token is None:
            basic = base64.b64encode(f"{self.client_id}:{self._secret}".encode("utf-8")).decode("ascii")
            data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode("ascii")
            status, body = self._request(f"https://{self.host}/oidc/v1/token", data=data, method="POST",
                                         headers={"Authorization": f"Basic {basic}",
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            token = None
            if status == 200:
                try:
                    token = json.loads(body).get("access_token")
                except (ValueError, AttributeError):
                    token = None
            if not isinstance(token, str) or not token:
                raise CopyError(f"Databricks refused the reader's sign-in: HTTP {status}")
            self._token = token
        return {"Authorization": f"Bearer {self._token}"}

    def get(self, api, path):
        """The status and body of one Files API read."""
        url = f"https://{self.host}/api/2.0/fs/{api}{urllib.parse.quote(path)}"
        return self._request(url, headers=self._bearer())

    def names(self, folder):
        """The names in a folder, or None when the reader is refused or it is not there."""
        status, body = self.get("directories", folder)
        if status != 200:
            return None
        try:
            contents = json.loads(body).get("contents") or []
        except (ValueError, AttributeError):
            raise CopyError("the Files API's folder listing could not be read") from None
        return sorted(item.get("name") or item.get("path", "").rsplit("/", 1)[-1] for item in contents)


def reader_from(env):
    """The reader from its own variables only, never a default profile or `DATABRICKS_TOKEN` (J13)."""
    return Reader(env.get("VOC_DATABRICKS_HOST"), env.get("VOC_READER_CLIENT_ID"),
                  env.get("VOC_READER_CLIENT_SECRET"))


def copy(root, run_id, reader):
    """Copies the two results files of Job B's run `run_id` into `results/june/`. Returns their names."""
    root = Path(root)
    folder = f"{RESULTS}/june-{run_id}"
    out = root / OUT
    if any((out / name).exists() for name in june_results.FILES):
        raise CopyError("results/june already holds the June results")
    names = reader.names(folder)
    if names != sorted(june_results.FILES):
        raise CopyError("the results folder must hold exactly v1_june.csv and v1_june.json")
    texts = []
    for name in june_results.FILES:
        status, body = reader.get("files", f"{folder}/{name}")
        if status != 200:
            raise CopyError(f"{name} could not be read: HTTP {status}")
        try:
            texts.append(body.decode("utf-8"))
        except UnicodeDecodeError:
            raise CopyError(f"{name} is not UTF-8") from None
    try:
        june_results.check(root, texts[0], texts[1])
        failure = None
    except june_results.JuneResultsError as err:
        failure = str(err)
    if failure is not None:
        raise CopyError(failure)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in zip(june_results.FILES, texts):
        (out / name).write_bytes(text.encode("utf-8"))
    return list(june_results.FILES)


def check_reader(reader):
    """J13: the reader can list the results volume and is refused on the raw volume. Lines of yes, no and a verdict."""
    readable = reader.names(RESULTS) is not None
    refused = reader.names(RAW) is None
    return [f"results volume readable | {'yes' if readable else 'no'}",
            f"raw volume refused | {'yes' if refused else 'no'}",
            f"verdict | {'PASS' if readable and refused else 'FAIL'}"]
