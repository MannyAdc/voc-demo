"""Spec 004, J9: the receiver's links to the storage table and queue, Databricks and GitHub.

The table and the queue use the Function's managed identity. Databricks is reached with the robot account's OAuth
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

EVENTS, RESULTS = "event", "result"
TABLE = "juneevents"
REPO = "MannyAdc/voc-demo"
WORKFLOW = "june_approval.yml"
TIMEOUT = 30


def _credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


class TableStore:
    """The keys of events already taken, and the result messages, in one table."""

    def __init__(self, client):
        self.client = client

    @classmethod
    def from_env(cls):
        from azure.data.tables import TableServiceClient

        service = TableServiceClient(endpoint=os.environ["VOC_STORAGE__tableServiceUri"], credential=_credential())
        return cls(service.create_table_if_not_exists(TABLE))

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
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_env(cls, name):
        from azure.storage.queue import QueueClient

        return cls(QueueClient(account_url=os.environ["VOC_STORAGE__queueServiceUri"], queue_name=name,
                               credential=_credential()))

    def put(self, message):
        self.client.send_message(json.dumps(message, sort_keys=True))


def _request(url, data=None, headers=None, method="GET"):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read()


class DatabricksClient:
    def __init__(self, host, client_id, client_secret):
        self.host, self.client_id, self.client_secret = host, client_id, client_secret

    @classmethod
    def from_env(cls):
        return cls(os.environ["VOC_DATABRICKS_HOST"], os.environ["VOC_DATABRICKS_CLIENT_ID"],
                   os.environ["VOC_DATABRICKS_CLIENT_SECRET"])

    def _token(self):
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "all-apis"}).encode("ascii")
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
        return cls(os.environ["VOC_GITHUB_TOKEN"])

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "voc-demo-receiver"}

    def list_dispatch_runs(self):
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
