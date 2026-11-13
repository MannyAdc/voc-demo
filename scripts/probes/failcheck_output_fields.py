# Databricks notebook source
# Spec 004, the standing rule of 13 November: a read-only probe before a gate rule about the platform is frozen.
# It reads one failcheck run as the owner, with the notebook's own sign-in, and prints, for every attempt of every
# task, only the names of the fields of its run output, their types and lengths, and three yes or no answers: is the
# failcheck's marker anywhere in the output, does its `error` field start with "Workload failed", and is its
# `error_trace` field empty. It never prints a value it read. Delete the notebook after its one run.
import json
import urllib.error
import urllib.request

RUN_ID = 0  # the failcheck run's ID, the number after /runs/ in its page's address
MARKER = "SYNFAILCHECKMARKER"  # the same as src/voc/failcheck.py

ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()  # noqa: F821, the notebook's own global
HOST, TOKEN = ctx.apiUrl().get(), ctx.apiToken().get()


def get(path):
    request = urllib.request.Request(f"{HOST}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(request, timeout=120) as reply:
            return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as err:
        return err.code, None


def shape(value):
    if isinstance(value, dict):
        return "object{" + ", ".join(f"{k}: {shape(v)}" for k, v in sorted(value.items())) + "}"
    if isinstance(value, list):
        return f"list of {len(value)}"
    if isinstance(value, str):
        return f"text of {len(value)}"
    return type(value).__name__


if not RUN_ID:
    print("Fill in RUN_ID at the top, then run this cell again.")
else:
    status, run = get(f"/api/2.2/jobs/runs/get?run_id={int(RUN_ID)}")
    print(f"runs/get: HTTP {status}")
    for task in sorted((run or {}).get("tasks", []), key=lambda t: (str(t.get("task_key")), t.get("attempt_number", 0))):
        label = f"{task.get('task_key')} (attempt {task.get('attempt_number', 'none')})"
        status, output = get(f"/api/2.2/jobs/runs/get-output?run_id={int(task.get('run_id', 0))}")
        if output is None:
            print(f"{label}: get-output: HTTP {status}")
            continue
        text = json.dumps(output)
        error = output.get("error")
        print(f"{label}: get-output: HTTP {status}, fields: {shape(output)}")
        print(f"{label}: marker in output: {'yes' if MARKER in text else 'no'}, error starts with \"Workload failed\": "
              f"{'yes' if isinstance(error, str) and error.startswith('Workload failed') else 'no'}, error_trace "
              f"empty: {'yes' if not output.get('error_trace') else 'no'}")
