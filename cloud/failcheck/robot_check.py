# Databricks notebook source
# Spec 004, J5 and J13: the failing-row check, read as the robot `voc-june-runner` (owner decision, 6 November).
# The owner pastes this file into a notebook named `voc-failcheck-robot`, fills in the three values below, runs it
# once, and then deletes the notebook and the robot's secret (cloud/failcheck/STEPS.md).
#
# It asks for a token with the `jobs` scope, and once more with `all-apis`, which must be refused. As the robot, it
# reads the failcheck run (`runs/get`), each task's output (`runs/get-output`) and any dbt files the output links
# to, and looks for the failcheck's synthetic marker in all of them. It tries the SQL warehouse's query history. Its
# last line is the verdict, PASS only when every rule of STEPS.md holds. It prints only task keys, states, places,
# counts, status codes and the failcheck code's hash, never a value it read, the token or the secret.
import base64
import io
import json
import re
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

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
    """The number of files in a downloaded tar (of any compression) or zip archive, and the names of those that
    hold the marker. None when the download is not an archive it can read, which is never "nowhere"."""
    marker = MARKER.encode()
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            members = [m for m in archive.getmembers() if m.isfile()]
            return len(members), [m.name for m in members if marker in archive.extractfile(m).read()]
    except (tarfile.TarError, EOFError, OSError, ValueError):
        pass
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [i.filename for i in archive.infolist() if not i.is_dir()]
            return len(names), [n for n in names if marker in archive.read(n)]
    except (zipfile.BadZipFile, EOFError, OSError, ValueError, NotImplementedError):
        return None


def _json(body):
    try:
        value = json.loads(body)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _token(base, client_id, client_secret, scope):
    form = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": scope}).encode("ascii")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    status, body = _call(f"{base}/oidc/v1/token", data=form,
                         headers={"Authorization": f"Basic {basic}",
                                  "Content-Type": "application/x-www-form-urlencoded"})
    token = (_json(body) or {}).get("access_token")
    return status, (token if status == 200 and isinstance(token, str) and token else None), body


def _found(body, parsed):
    """Where the marker is in a reply: its JSON places, or the whole reply when it is not JSON."""
    if parsed is not None:
        found = places(parsed)
        return found or (["(the reply)"] if MARKER.encode() in body else [])
    return ["(the reply)"] if MARKER.encode() in body else []


def report(host, client_id, client_secret, run_id):
    base = f"https://{host}"
    lines, fails = [], []
    status, token, body = _token(base, client_id, client_secret, "jobs")
    if not token:
        return [f"token: HTTP {status}, {(_json(body) or {}).get('error', 'no token')}",
                "verdict: FAIL: no token for the jobs scope"]
    status, wide, _ = _token(base, client_id, client_secret, "all-apis")
    if wide:
        lines.append("all-apis token: GIVEN")
        fails.append("an all-apis token was given")
    else:
        lines.append(f"all-apis token: refused, HTTP {status}")
    status, body = _call(f"{base}/api/2.2/jobs/runs/get?run_id={int(run_id)}", token=token)
    run = _json(body)
    if status != 200 or run is None:
        return lines + [f"runs/get: HTTP {status}", "verdict: FAIL: runs/get could not be read"]
    tasks = {t.get("task_key"): t for t in run.get("tasks", []) if isinstance(t, dict)}
    outside = {k: v for k, v in run.items() if k != "tasks"}
    run_places = places(outside)
    lines.append(f"run: runs/get: marker {', '.join(run_places) or 'nowhere'}")
    if run_places:
        fails.append("the marker is in the run's runs/get")
    seen = {}
    for key in sorted(tasks, key=lambda k: (ORDER.index(k) if k in ORDER else len(ORDER), str(k))):
        task = tasks[key]
        state = (task.get("state") or {}).get("result_state", "no state")
        lines.append(f"{key}: {state}")
        in_get = places(task)
        lines.append(f"{key}: runs/get: marker {', '.join(in_get) or 'nowhere'}")
        status, body = _call(f"{base}/api/2.2/jobs/runs/get-output?run_id={int(task.get('run_id', 0))}", token=token)
        output = _json(body)
        if status != 200:
            lines.append(f"{key}: output: could not read, HTTP {status}")
            fails.append(f"could not read {key}'s output")
            seen[key] = {"state": state, "get": in_get, "output": None, "artifacts": "none"}
            continue
        in_output = _found(body, output)
        lines.append(f"{key}: output: marker {', '.join(in_output) or 'nowhere'}")
        artifacts = "none"
        link = ((output or {}).get("dbt_output") or {}).get("artifacts_link")
        if link:
            headers = (output["dbt_output"].get("artifacts_headers") or {})
            status, data = _call(link, headers=headers)
            read = archive_places(data) if status == 200 else None
            if read is None:
                lines.append(f"{key}: artifacts: could not read, HTTP {status}")
                fails.append(f"could not read {key}'s artifacts")
                artifacts = "unread"
            else:
                lines.append(f"{key}: artifacts: files: {read[0]}, marker in: {', '.join(read[1]) or 'nowhere'}")
                artifacts = read[1]
        seen[key] = {"state": state, "get": in_get, "output": in_output, "artifacts": artifacts, "value": output}
    make_rows, quiet, control = seen.get("make_rows"), seen.get("dbt"), seen.get("dbt_control")
    if not (make_rows and quiet and control):
        fails.append("the run does not have the tasks make_rows, dbt and dbt_control")
    else:
        code = None
        try:
            code = json.loads(((make_rows.get("value") or {}).get("notebook_output") or {}).get("result", ""))
            code = code.get("code_sha256") if isinstance(code, dict) else None
        except ValueError:
            code = None
        if isinstance(code, str) and re.fullmatch(r"[0-9a-f]{64}", code):
            lines.append(f"code sha256: {code}")
        else:
            fails.append("no code hash from make_rows")
        if make_rows["state"] != "SUCCESS":
            fails.append("make_rows did not succeed")
        if make_rows["get"] or make_rows["output"]:
            fails.append("the marker is in make_rows' output")
        if quiet["state"] != "FAILED":
            fails.append("dbt did not fail")
        if quiet["get"]:
            fails.append("the marker is in dbt's runs/get")
        if quiet["output"]:
            fails.append("the marker is in dbt's output")
        if isinstance(quiet["artifacts"], list) and quiet["artifacts"]:
            fails.append("the marker is in dbt's artifacts")
        if control["state"] != "FAILED":
            fails.append("the control did not fail")
        if not (control["get"] or control["output"]):
            fails.append("the control shows no leak in its output, so the check cannot see one")
        if quiet["artifacts"] != "none":
            if control["artifacts"] == "none":
                fails.append("the control has no artifacts to show a leak in")
            elif isinstance(control["artifacts"], list) and not control["artifacts"]:
                fails.append("the control shows no leak in its artifacts, so the check cannot see one")
    status, body = _call(f"{base}/api/2.0/sql/history/queries", token=token)
    lines.append(f"query history: HTTP {status}, {(_json(body) or {}).get('error_code', 'no error code')}")
    if status not in (401, 403):
        fails.append("the query history was not refused")
    lines.append("verdict: PASS" if not fails else "verdict: FAIL: " + " | ".join(dict.fromkeys(fails)))
    return lines


def _host():
    if HOST:
        return HOST
    try:
        return spark.conf.get("spark.databricks.workspaceUrl")  # noqa: F821, the notebook's own global
    except Exception:  # noqa: BLE001, any failure means the host must be typed in
        return None


if __name__ == "__main__":
    if not (CLIENT_ID and CLIENT_SECRET and RUN_ID):
        print("Fill in CLIENT_ID, CLIENT_SECRET and RUN_ID at the top, then run this cell again.")
    elif not _host():
        print("Fill in HOST with the workspace's host name, from the browser's address bar, then run this cell again.")
    else:
        for line in report(_host(), CLIENT_ID, CLIENT_SECRET, RUN_ID):
            print(line)
