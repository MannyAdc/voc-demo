"""Spec 004, J11 and J16: Job B's logic, as the dry run of pull request 6a. Its one task, `job_b`, runs in Databricks
as the owner (`cloud/job_b.yml`). The notebook in `cloud/job_b/` stays thin and calls `run`.

The dry run takes only a synthetic first row of the run log, labels the synthetic sample with the mock backend, and
writes no results file. Its results folder holds a note, `DRY_RUN.txt`, so the folder exists on the object store and
explains itself (owner decision, 8 November). The real labelling, its ledger, its start marker, the TF-IDF refit, the
scoring and the results files come in pull request 6b.

Every check runs before the first marker is written, in this order:
1. its parameters, exactly the two run IDs and its own run ID, each a whole number (J16 item 1)
2. the run log's last row, through Job A's checks, and only a synthetic first row until pull request 6b
3. its own run: Job B's job, running, with exactly the two run IDs, and the commit it runs
4. the GitHub run, read from GitHub's public API with no credential: the approval workflow's dispatch on `main`, from
   the commit Job B runs, with the exact name for the Job A run, first attempt, approved for `june-run` by the owner
   and never rejected (J11, J16 item 7)
5. Job A's run again, as the approval workflow checks it (J16 item 5)
6. the sample: only `SYN-` IDs, exactly the dry run's list, each row with its content hash
7. Job A's figures, computed again from the rows: the same counts, and no more tokens or cost than approved
Then it marks the GitHub run, and the Job A run for its row, as used. A marker already there is refused, and an
upload never overwrites. Then it labels, writes the note and returns the contract's exit value (J16 item 8).

B21 and J5: nothing here prints. Every refusal holds fixed text, IDs and counts only, and carries no earlier exception.
"""
import io
import json
import re
import time
from decimal import Decimal

from voc import approval
from voc.job_a import VOLUME

CONTRACT = "voc-june-1"
USED_FOLDER = VOLUME + "/job_b_used"
RESULTS_VOLUME = "/Volumes/workspace/default/voc_results"
DRY_RUN_FILE = "DRY_RUN.txt"
DRY_RUN_NOTE = ("This folder is a synthetic dry run of spec 004's Job B (pull request 6a). Job B labelled the "
                "synthetic sample with the mock backend and wrote no results file. The results files arrive in pull "
                "request 6b.\n")
PARAMETERS = ("job_a_run_id", "github_run_id", "job_b_run_id")
JOB_PARAMETERS = ("job_a_run_id", "github_run_id")
GITHUB_RUNS = "https://api.github.com/repos/MannyAdc/voc-demo/actions/runs"
OWNER = "MannyAdc"
ENVIRONMENT = "june-run"
# GitHub allows 60 calls an hour without a token, per address, and serverless addresses are shared (J11).
GITHUB_TRIES = 3
GITHUB_WAITS = (20, 60)
COMMIT = re.compile(r"[0-9a-f]{40}")
SYNTHETIC_ID = re.compile(r"SYN-[0-9]{1,19}")


class JobBError(ValueError):
    """A refusal with fixed text, IDs and counts only (B21, J5)."""


def _checked(function, *args):
    """Calls the approval workflow's own check, and gives its refusal as Job B's, with no earlier exception."""
    try:
        return function(*args), None
    except approval.ApprovalError as err:
        message = str(err)
    raise JobBError(message)


# 1. The parameters


def parameters(values):
    """J16 item 1: exactly the two run IDs and Job B's own run ID, each a whole number in range."""
    if set(values) != set(PARAMETERS):
        raise JobBError("Job B takes exactly job_a_run_id, github_run_id and job_b_run_id")
    return tuple(_checked(approval.parse_id, values[name], name)[0] for name in PARAMETERS)


# 2. The run log's last row


def checked_target(root):
    (run_target, entry), _ = _checked(approval._target_and_entry, root)
    if run_target.kind != "synthetic" or run_target.entry_kind != "synthetic":
        raise JobBError("Job B runs only a synthetic first row until pull request 6b")
    return run_target, entry


# 3. Its own run


def _job_parameters(run):
    items = run.get("job_parameters")
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        return None
    names = [i.get("name") for i in items]
    if sorted(names) != sorted(JOB_PARAMETERS):
        return None
    return {i["name"]: i.get("value") for i in items}


def checked_own_run(run, job_b_run_id, job_b_job_id, job_a_run_id, github_run_id):
    """Its own run is Job B's, still running, with exactly the two run IDs it was given. Returns the commit it runs.
    So a run ID filled by hand that names another run is refused (owner decision, 8 November)."""
    snapshot = (run.get("git_source") or {}).get("git_snapshot") if isinstance(run.get("git_source"), dict) else None
    commit = snapshot.get("used_commit") if isinstance(snapshot, dict) else None
    if (run.get("run_id") != job_b_run_id or run.get("job_id") != job_b_job_id
            or (run.get("state") or {}).get("life_cycle_state") != "RUNNING"
            or _job_parameters(run) != {"job_a_run_id": str(job_a_run_id), "github_run_id": str(github_run_id)}
            or not isinstance(commit, str) or not COMMIT.fullmatch(commit)):
        raise JobBError("Job B's own run cannot be confirmed: it must be a running run of Job B with exactly these "
                        "two run IDs and a known commit")
    return commit


# 4. The approval on GitHub


class PublicGitHub:
    """GitHub's public API for this repo's workflow runs, read with no credential and no redirect (J11)."""

    def get(self, path):
        return approval._request(GITHUB_RUNS + path, headers={"Accept": "application/vnd.github+json",
                                                              "X-GitHub-Api-Version": "2022-11-28"})


def _retried(status):
    return status in (0, 403, 429) or 500 <= status <= 599


def github_json(github, path, sleep):
    """Tried 3 times, waiting 20 and then 60 seconds, after no answer, 403, 429 or a server error. Then refused."""
    for attempt in range(GITHUB_TRIES):
        status, body = github.get(path)
        if not _retried(status) or attempt == GITHUB_TRIES - 1:
            break
        sleep(GITHUB_WAITS[attempt])
    if _retried(status):
        raise JobBError(f"GitHub's API did not answer after {GITHUB_TRIES} tries: HTTP {status}")
    if status != 200:
        raise JobBError(f"GitHub's API answered HTTP {status}")
    try:
        value = json.loads(body)
    except ValueError:
        value = None
    if value is None:
        raise JobBError("GitHub's API did not answer JSON")
    return value


def checked_github_run(run, github_run_id, job_a_run_id, commit):
    """J16 item 7: the approval workflow's dispatch on main, from the commit Job B runs, with the exact name."""
    if not isinstance(run, dict):
        raise JobBError("GitHub's run is not an object")
    if (run.get("id") != github_run_id or run.get("path") != approval.WORKFLOW_PATH
            or run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main"):
        raise JobBError("the GitHub run is not a dispatch of the approval workflow on main")
    if run.get("head_sha") != commit:
        raise JobBError("the GitHub run was not made from the commit Job B runs: no merge to main may come between "
                        "the approval and Job B's end")
    if run.get("display_title") != approval.run_name(job_a_run_id):
        raise JobBError("the GitHub run's name is not the exact name for this Job A run")
    if run.get("run_attempt") != 1:
        raise JobBError("only a workflow run's first attempt can start Job B (J16 item 7)")


def _for_june_run(item):
    environments = item.get("environments")
    return isinstance(environments, list) and any(
        isinstance(e, dict) and e.get("name") == ENVIRONMENT for e in environments)


def checked_approvals(approvals):
    """An approval of `june-run` by the owner, and no rejection of it by anyone (owner decision, 8 November)."""
    if not isinstance(approvals, list) or not all(isinstance(i, dict) for i in approvals):
        raise JobBError("the GitHub run's approval list cannot be read")
    june_run = [i for i in approvals if _for_june_run(i)]
    if any(i.get("state") != "approved" for i in june_run):
        raise JobBError("the GitHub run's june-run review was rejected, so it gives no approval")
    if not any((i.get("user") or {}).get("login") == OWNER for i in june_run if isinstance(i.get("user"), dict)):
        raise JobBError("the GitHub run has no approval of june-run by the owner")


# 6. The sample


def listed_for(root, run_target):
    """The dry run's frozen list, complaint ID to content hash. Pull request 9a adds it."""
    raise JobBError("the dry run's list is added in pull request 9a, so Job B cannot run yet")


def mock_answers(root, run_target):
    """The mock backend's synthetic answers for the dry run's prompts. Pull request 9a adds them."""
    raise JobBError("the dry run's mock answers are added in pull request 9a, so Job B cannot run yet")


def checked_rows(listed, rows):
    """`rows` are (complaint_id, product, narrative). Refused unless they are exactly the listed sample, every ID
    synthetic, each row with its content hash. Returns the count."""
    from voc.data import content_hash

    if not all(isinstance(cid, str) and SYNTHETIC_ID.fullmatch(cid) for cid in listed):
        raise JobBError("the dry run's list holds an ID that is not synthetic")
    given = {}
    for cid, product, narrative in rows:
        if not isinstance(cid, str) or not SYNTHETIC_ID.fullmatch(cid):
            raise JobBError("the sample holds an ID that is not synthetic")
        given[cid] = (product, narrative)
    if len(given) != len(rows):
        raise JobBError("the sample's rows repeat a complaint ID")
    extra, missing = set(given) - set(listed), set(listed) - set(given)
    if extra:
        raise JobBError(f"{len(extra)} sample rows are not in the dry run's list")
    if missing:
        raise JobBError(f"{len(missing)} complaints of the dry run's list are missing from the June tables")
    changed = sum(content_hash(narrative, product) != listed[cid] for cid, (product, narrative) in given.items())
    if changed:
        raise JobBError(f"{changed} sample rows do not match their content hash in the dry run's list")
    return len(rows)


def _spark_rows(run_sql, listed):
    from voc.job_a import JobAError, spark_rows

    try:
        return spark_rows(run_sql, sorted(listed)), None
    except JobAError as err:
        message = str(err)
    raise JobBError(message)


# 7. The figures


def checked_figures(computed, approved):
    """J11: Job A's figures, computed again from the rows, are the approved counts, with no more tokens or cost."""
    if (computed["complaints"] != approved["complaints"] or computed["calls"] != approved["calls"]
            or computed["worst_case_tokens"] > approved["worst_case_tokens"]
            or Decimal(computed["expected_cost_usd"]) > Decimal(approved["expected_cost_usd"])):
        raise JobBError("Job A's figures, computed again, are not the approved ones")


# The volume


class VolumeStore:
    """The volumes' files through the Databricks SDK's `files` client. An upload never overwrites, so a file that
    exists already is refused (whether the Files API's check is atomic is not documented, J11 Known limits)."""

    def __init__(self, files):
        self.files = files

    def exists(self, path):
        try:
            self.files.get_metadata(path)
            found, failure = True, None
        except Exception as err:  # noqa: BLE001, read by its type only, outside the except block
            found, failure = False, type(err).__name__
        if failure is not None and failure != "NotFound":
            raise JobBError(f"the volume could not be read: {failure}")
        return found

    def create(self, path, data):
        failure = None
        try:
            self.files.create_directory(path.rsplit("/", 1)[0])
            self.files.upload(path, io.BytesIO(data), overwrite=False)
        except Exception as err:  # noqa: BLE001, read by its type only, outside the except block
            failure = type(err).__name__
        if failure is not None:
            raise JobBError(f"{path.rsplit('/', 1)[1]} could not be written, or was already there: {failure}")


class WorkspaceJobs:
    """The Jobs API through the notebook's own sign-in, as the owner, read by `get` as the approval workflow reads
    it. A failure is refused with its type only, since the SDK's message is not ours."""

    def __init__(self, api_client):
        self.api_client = api_client

    def get(self, path, params):
        failure = None
        try:
            value = self.api_client.do("GET", path, query=params)
        except Exception as err:  # noqa: BLE001, read by its type only, outside the except block
            failure = type(err).__name__
        if failure is not None:
            raise JobBError(f"Databricks' {path} could not be read: {failure}")
        if not isinstance(value, dict):
            raise JobBError(f"Databricks' {path} did not answer an object")
        return value


def _compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def marked_used(store, run_target, job_a_run_id, github_run_id, job_b_run_id):
    """J16 item 7: the GitHub run, and the Job A run for its row, marked used. Both are looked at first, so a used
    pair does not use up the GitHub run. A marker made by another run in between is refused by the upload."""
    github_marker = f"{USED_FOLDER}/github/{github_run_id}.json"
    pair_marker = f"{USED_FOLDER}/job_a/{job_a_run_id}-row{run_target.row}.json"
    if store.exists(github_marker):
        raise JobBError(f"GitHub run {github_run_id} has already started Job B")
    if store.exists(pair_marker):
        raise JobBError(f"Job A run {job_a_run_id} has already been used for run log row {run_target.row}")
    ids = {"github_run_id": github_run_id, "job_a_run_id": job_a_run_id, "job_b_run_id": job_b_run_id,
           "row": run_target.row}
    store.create(github_marker, _compact(ids))
    store.create(pair_marker, _compact({**ids, "june_list_sha256": run_target.list_hash,
                                        "code_sha256": run_target.code_hash}))


# The labelling and the exit value


def labelled(root, rows, answers):
    """The mock backend's labels for the rows. Returns how many were decided, and whether the run stopped."""
    from voc import pipeline
    from voc.backends import make_backend
    from voc.labels import load_labels
    from voc.pipeline import Complaint, RunStopped
    from voc.replay import Answer, Reply

    version = pipeline.load_prompt_version(root, "v1")
    labels = load_labels(root / "config" / "labels.toml")
    backend = make_backend("mock", fixtures={item["prompt"]: Answer(item["text"], None, None, "end_turn")
                                             for item in answers})
    settings = dict(version.settings)

    def call(prompt):
        return Reply(backend(prompt, dict(settings)).text, "mock", None, None, 0, 0, 1)

    complaints = [Complaint(cid, narrative) for cid, _, narrative in rows]
    try:
        outcomes, stopped = pipeline.label_complaints(complaints, version, labels, call, "mock"), False
    except RunStopped as stop:
        outcomes, stopped = stop.outcomes, True
    return len(outcomes), stopped


def exit_value(run_target, complaints, count, stopped, job_b_run_id):
    """J16 item 8: a finished run names `june-<Job B run ID>`, and a stopped one no folder and its reason."""
    value = {"contract": CONTRACT, "kind": run_target.kind, "entry_kind": run_target.entry_kind,
             "complaints": complaints, "labelled": count, "stopped": stopped,
             "stop_reason": "error" if stopped else None,
             "results_folder": None if stopped else f"june-{job_b_run_id}"}
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def run(root, values, databricks, github, store, run_sql, sleep=time.sleep):
    """Job B's dry run, end to end. Returns the exit value as compact JSON."""
    from pathlib import Path

    from voc.job_a import JobAError, figures

    root = Path(root)
    job_a_run_id, github_run_id, job_b_run_id = parameters(values)
    run_target, _ = checked_target(root)
    settings, _ = _checked(approval.cloud_settings, root)
    commit = checked_own_run(databricks.get("/api/2.2/jobs/runs/get", {"run_id": job_b_run_id}), job_b_run_id,
                             settings["job_b_job_id"], job_a_run_id, github_run_id)
    checked_github_run(github_json(github, f"/{github_run_id}", sleep), github_run_id, job_a_run_id, commit)
    checked_approvals(github_json(github, f"/{github_run_id}/approvals", sleep))
    (_, _, approved, _), _ = _checked(approval._checked_job_a, root, job_a_run_id, databricks)
    listed = listed_for(root, run_target)
    rows = _spark_rows(run_sql, listed)[0]
    complaints = checked_rows(listed, rows)
    try:
        computed, failure = figures(root, rows, 0), None
    except JobAError as err:
        computed, failure = None, str(err)
    if failure is not None:
        raise JobBError(failure)
    checked_figures(computed, approved)
    answers = mock_answers(root, run_target)
    marked_used(store, run_target, job_a_run_id, github_run_id, job_b_run_id)
    count, stopped = labelled(root, rows, answers)
    if not stopped:
        store.create(f"{RESULTS_VOLUME}/june-{job_b_run_id}/{DRY_RUN_FILE}", DRY_RUN_NOTE.encode("utf-8"))
    return exit_value(run_target, complaints, count, stopped, job_b_run_id)
