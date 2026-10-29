"""B14 and B21: run the dbt project in `dbt/` and print only counts and check names.

dbt runs in a child process with its output thrown away, because dbt and
DuckDB can echo raw rows in their messages. What is printed comes from
`run_results.json` (node names, which are ours, statuses and counts) and from
row counts of our own models. Usage stats are off (B7), and credentials and
proxy settings never reach the child process.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from voc.db import connect
from voc.load import DB_PATH

PROJECT = Path("dbt")
# dbt's output can hold complaint text (run_results.json, dbt.log) and local paths (manifest.json),
# so it goes in the git-ignored data folder, next to the DuckDB file, which the read guard protects.
TARGET = DB_PATH.parent / "dbt" / "target"
LOGS = DB_PATH.parent / "dbt" / "logs"
MODELS = ("stg_complaints", "curated_complaints")
CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
QUIET = {
    "DBT_ENGINE_SEND_ANONYMOUS_USAGE_STATS": "False",  # dbt Core 1.11 and later
    "DBT_SEND_ANONYMOUS_USAGE_STATS": "False",  # dbt Core 1.10 and earlier
    "DO_NOT_TRACK": "1",
}
COMMANDS = {"build": ["build"], "docs": ["docs", "generate"]}
# B17: the models read the test IDs from this list, next to the dbt folder (dbt/macros/test_set.sql).
TEST_LIST = Path("splits") / "test.csv"


class DbtError(Exception):
    """An error whose message is ours, so it is safe to print."""


def dbt_env(base):
    """The child's environment: no credentials, no proxy, usage stats off."""
    env = {name: value for name, value in base.items()
           if name not in CREDENTIAL_VARS and not (name.lower().endswith("_proxy") and name.lower() != "no_proxy")}
    env.update(QUIET)
    return env


def _run(root, action, labels):
    # B17: without the test list the models cannot leave out the test rows, so dbt does not start.
    if not (Path(root) / TEST_LIST).is_file():
        raise DbtError(f"{TEST_LIST.as_posix()} is missing, so the dbt models cannot leave out the test rows "
                       "(B17). dbt did not run")
    project = (Path(root) / PROJECT).resolve()
    target = (Path(root) / TARGET).resolve()
    results = target / "run_results.json"
    results.unlink(missing_ok=True)
    args = [sys.executable, "-c", "from dbt.cli.main import cli; cli()", *COMMANDS[action],
            "--project-dir", str(project), "--profiles-dir", str(project),
            "--target-path", str(target), "--log-path", str((Path(root) / LOGS).resolve()),
            # B17: the test-set flag is always passed off. It overrides dbt_project.yml, and no command turns it on.
            "--vars", json.dumps({"labels": labels, "final": False})]
    env = dbt_env(os.environ)
    env["VOC_DBT_DB"] = str((Path(root) / DB_PATH).resolve())
    code = subprocess.run(args, env=env, cwd=project, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    return code, results


def _row_counts(root):
    con = connect(Path(root) / DB_PATH)
    try:
        found = {name for (name,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
        return {name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in MODELS if name in found}
    finally:
        con.close()


def build(root, labels):
    """Run `dbt build`. Returns the lines to print and whether the build passed."""
    code, results = _run(root, "build", labels)
    if not results.is_file():
        raise DbtError(f"dbt exited with code {code} before it wrote any result")
    nodes = json.loads(results.read_text(encoding="utf-8"))["results"]
    tally = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    kinds = {"model": 0, "test": 0}
    problems = []
    for node in nodes:
        kind, _, name = node["unique_id"].split(".")[:3]
        kinds[kind] = kinds.get(kind, 0) + 1
        status = node["status"]
        if status in ("success", "pass"):
            tally["passed"] += 1
        elif status == "skipped":
            tally["skipped"] += 1
        elif status == "fail":
            tally["failed"] += 1
            problems.append(f"failed: {kind} {name} ({node.get('failures') or 0} rows)")
        else:
            tally["errors"] += 1
            problems.append(f"error: {kind} {name} ({status})")
    lines = [f"dbt build: {kinds['model']} models, {kinds['test']} data tests. "
             + ", ".join(f"{key} {value}" for key, value in tally.items())]
    lines += problems
    counts = _row_counts(root)
    if counts:
        lines.append(", ".join(f"{name}: {n} rows" for name, n in counts.items()))
    return lines, code == 0 and not problems


def docs(root, labels):
    """Run `dbt docs generate`, which writes the lineage graph files."""
    code, _ = _run(root, "docs", labels)
    target = Path(root) / TARGET
    written = [name for name in ("manifest.json", "catalog.json", "index.html") if (target / name).is_file()]
    if code != 0:
        raise DbtError(f"dbt docs exited with code {code}")
    return [f"dbt docs: {', '.join(written)} written to {TARGET.as_posix()}. "
            "They hold local paths: strip them before the lineage graph is published."]
