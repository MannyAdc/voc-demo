# Databricks notebook source
# Spec 004, J5 and J13: the failing-row check, read as the robot `voc-june-runner` (owner decision, 6 November).
# The owner pastes this file into a notebook named `voc-failcheck-robot`, fills in the three values below, runs it
# once, and then deletes the notebook and the robot's secret (cloud/failcheck/STEPS.md).
#
# It asks for a token with the `jobs` scope only, reads the failcheck run and each task's output as the robot, and
# downloads any dbt files the output links to. It looks for the failcheck's synthetic marker in all of them, and
# tries the SQL warehouse's query history as the robot. It prints only task keys, states, places, counts and
# status codes, never a value it read, the token or the secret.
import base64
import io
import json
import tarfile
import urllib.error
import urllib.parse
import urllib.request

CLIENT_ID = ""      # the robot's client ID, from its page in the workspace's settings
CLIENT_SECRET = ""  # the robot's new OAuth secret, made for this check and deleted after it
RUN_ID = 0          # the failcheck run's ID, the number after /runs/ in its page's address
HOST = ""           # left empty, the notebook's own workspace is used
MARKER = "SYNFAILCHECKMARKER"  # the same as src/voc/failcheck.py
ORDER = ("make_rows", "dbt", "dbt_control")


def _call(url, token=None, data=None, headers=None):
    """One HTTP call. Returns the status and the body, also for an error status."""
    request = urllib.request.Request(url, data=data, headers=dict(headers or {}))
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=120) as reply:
            return reply.status, reply.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def places(value, path="$"):
    """The paths in a JSON value whose text holds the marker."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if MARKER in str(key):
                found.append(f"{path} (a key)")
            found += places(item, f"{path}.{key}")
    elif isinstance(value, list):
        for n, item in enumerate(value):
            found += places(item, f"{path}[{n}]")
    elif isinstance(value, str) and MARKER in value:
        found.append(path)
    return found


def archive_places(data):
    """The number of files in a downloaded tar or tar.gz archive, and the names of those that hold the marker.
    A download that is not such an archive counts as one file."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            members = [m for m in archive.getmembers() if m.isfile()]
            found = [m.name for m in members if MARKER.encode() in archive.extractfile(m).read()]
            return len(members), found
    except (tarfile.TarError, EOFError, OSError):
        return 1, (["(the whole download)"] if MARKER.encode() in data else [])


def _json(body):
    try:
        return json.loads(body)
    except ValueError:
        return None


def report(host, client_id, client_secret, run_id):
    base = f"https://{host}"
    form = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "jobs"}).encode("ascii")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    status, body = _call(f"{base}/oidc/v1/token", data=form,
                         headers={"Authorization": f"Basic {basic}",
                                  "Content-Type": "application/x-www-form-urlencoded"})
    token = (_json(body) or {}).get("access_token")
    if status != 200 or not token:
        return [f"token: HTTP {status}, {(_json(body) or {}).get('error', 'no token')}"]
    lines = []
    status, body = _call(f"{base}/api/2.2/jobs/runs/get?run_id={int(run_id)}", token=token)
    run = _json(body) or {}
    if status != 200:
        return [f"runs/get: HTTP {status}, {run.get('error_code', '')}"]
    tasks = sorted(run.get("tasks", []), key=lambda t: (ORDER.index(t["task_key"]) if t["task_key"] in ORDER
                                                       else len(ORDER), t["task_key"]))
    for task in tasks:
        key = task["task_key"]
        state = task.get("state", {}).get("result_state", "no state")
        status, body = _call(f"{base}/api/2.2/jobs/runs/get-output?run_id={int(task['run_id'])}", token=token)
        output = _json(body)
        if status != 200:
            lines.append(f"{key}: {state}, get-output HTTP {status}")
            continue
        found = places(output) if output is not None else []
        if not found and MARKER.encode() in body:
            found = ["(the reply)"]
        lines.append(f"{key}: {state}, marker in the output: {', '.join(found) or 'nowhere'}")
        link = ((output or {}).get("dbt_output") or {}).get("artifacts_link")
        if link:
            headers = (output["dbt_output"].get("artifacts_headers") or {})
            status, data = _call(link, headers=headers)
            if status != 200:
                lines.append(f"{key}: artifacts: HTTP {status}")
            else:
                count, names = archive_places(data)
                lines.append(f"{key}: artifacts: {count} files, marker in: {', '.join(names) or 'nowhere'}")
    status, body = _call(f"{base}/api/2.0/sql/history/queries", token=token)
    lines.append(f"query history: HTTP {status}, {(_json(body) or {}).get('error_code', 'no error code')}")
    return lines


if __name__ == "__main__":
    if not (CLIENT_ID and CLIENT_SECRET and RUN_ID):
        print("Fill in CLIENT_ID, CLIENT_SECRET and RUN_ID at the top, then run this cell again.")
    else:
        host = HOST or spark.conf.get("spark.databricks.workspaceUrl")  # noqa: F821, the notebook's own global
        for line in report(host, CLIENT_ID, CLIENT_SECRET, RUN_ID):
            print(line)
