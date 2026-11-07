"""Spec 004, J9: the receiver's links to the storage table and queue, Databricks and GitHub.

The table and the queue use the Function's system-assigned managed identity, which needs the roles Storage Queue
Data Contributor and Storage Table Data Contributor on its storage account. Its own storage uses that identity too,
with Storage Blob Data Owner on the account and Storage Blob Data Contributor on the code package's container
(spec 004, J9, "Its identity"). Databricks is reached with the robot account's OAuth
credential (J13), GitHub with the fine-grained token that has "Actions" write on this repo only. Every secret comes
from an app setting that is a Key Vault reference (`app_settings.json`). The tests use fakes in their place, and the
dry run of pull request 9 is the first to run these against the real services.
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from receiver_core import secret

EVENTS, RESULTS = "event", "result"
TABLE = "juneevents"
REPO = "MannyAdc/voc-demo"
WORKFLOW = "june_approval.yml"
TIMEOUT = 30


def _credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


class TableStore:
    """The keys of events already taken, and the result messages, in one table. The table client is made on first
    use, so a request refused by the checks costs no storage call."""

    def __init__(self, make_client):
        self.make_client, self._client = make_client, None

    @property
    def client(self):
        if self._client is None:
            self._client = self.make_client()
        return self._client

    @classmethod
    def from_env(cls):
        def make():
            from azure.data.tables import TableServiceClient

            service = TableServiceClient(endpoint=os.environ["VOC_STORAGE__tableServiceUri"], credential=_credential())
            return service.create_table_if_not_exists(TABLE)

        return cls(make)

    def add_key(self, key):
        from azure.core.exceptions import ResourceExistsError

        try:
            self.client.create_entity({"PartitionKey": EVENTS, "RowKey": key})
        except ResourceExistsError:
            return False
        return True

    def remove_key(self, key):
        self.client.delete_entity(partition_key=EVENTS, row_key=key)

    def save_result(self, key, record):
        self.client.upsert_entity({"PartitionKey": RESULTS, "RowKey": key, **{k: v for k, v in record.items()
                                                                              if v is not None}})

    def purge_older_than_days(self, days):
        """Keys are kept for 30 days (J9)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = f"PartitionKey eq '{EVENTS}' and Timestamp lt datetime'{cutoff}'"
        for entity in self.client.query_entities(query):
            self.client.delete_entity(partition_key=EVENTS, row_key=entity["RowKey"])


class StorageQueue:
    """The work queue. Its client is made on first use, as the table's is."""

    def __init__(self, make_client):
        self.make_client, self._client = make_client, None

    @classmethod
    def from_env(cls, name):
        def make():
            from azure.storage.queue import QueueClient

            return QueueClient(account_url=os.environ["VOC_STORAGE__queueServiceUri"], queue_name=name,
                               credential=_credential())

        return cls(make)

    def put(self, message):
        if self._client is None:
            self._client = self.make_client()
        self._client.send_message(json.dumps(message, sort_keys=True))


def _request(url, data=None, headers=None, method="GET"):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read()


class DatabricksClient:
    def __init__(self, host, client_id, client_secret):
        self.host, self.client_id, self.client_secret = host, client_id, client_secret

    @classmethod
    def from_env(cls):
        return cls(os.environ["VOC_DATABRICKS_HOST"], secret(os.environ, "VOC_DATABRICKS_CLIENT_ID"),
                   secret(os.environ, "VOC_DATABRICKS_CLIENT_SECRET"))

    def _token(self):
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        # The robot's secret carries the `jobs` scope only.
        # A request for `all-apis` is refused (spike, 6 November).
        data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "jobs"}).encode("ascii")
        _, body = _request(f"https://{self.host}/oidc/v1/token", data=data, method="POST",
                           headers={"Authorization": f"Basic {basic}",
                                    "Content-Type": "application/x-www-form-urlencoded"})
        return json.loads(body)["access_token"]

    def get_run(self, run_id):
        query = urllib.parse.urlencode({"run_id": run_id})
        _, body = _request(f"https://{self.host}/api/2.2/jobs/runs/get?{query}",
                           headers={"Authorization": f"Bearer {self._token()}"})
        return json.loads(body)


class GitHubClient:
    def __init__(self, token):
        self.token = token

    @classmethod
    def from_env(cls):
        return cls(secret(os.environ, "VOC_GITHUB_TOKEN"))

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "voc-demo-receiver"}

    def list_dispatch_runs(self):
        """The newest 100 runs only. A known limit (review of #91, owner decision (a)): Job B's checks of used runs
        mean a second dispatch can never score twice."""
        query = urllib.parse.urlencode({"event": "workflow_dispatch", "branch": "main", "per_page": 100})
        _, body = _request(f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?{query}",
                           headers=self._headers())
        return json.loads(body)["workflow_runs"]

    def dispatch(self, body):
        try:
            status, _ = _request(f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
                                 data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={**self._headers(), "Content-Type": "application/json"})
        except urllib.error.HTTPError as err:
            return err.code
        return status
