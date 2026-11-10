"""Spec 004, J11 and J16: Job B's logic. Its one task, `job_b`, runs in Databricks as the owner (`cloud/job_b.yml`).
The notebook in `cloud/job_b/` stays thin and calls `run`.

Job B takes a first row of the run log, synthetic or real (6b part 5). With a backend from the notebook it labels
through the API, the June ledger and the volume's recordings (6b part 3b). A synthetic run writes a note,
`DRY_RUN.txt`, and no results file (owner decision, 8 November). A real run writes its start marker before its
first model call, and after a finished run its two results files, checked (6b parts 4 and 5). With no backend, as
in the laptop's tests, a synthetic run serves the mock backend's committed answers (pull request 9a).

Every check runs before the first marker is written, in this order:
0. its packages: every version the notebook installed is the one in `cloud/job_b/requirements.txt` (pull
   request 6b)
1. its parameters, exactly the two run IDs and its own run ID, each a whole number (J16 item 1)
2. the run log's last row, through Job A's checks, and only a first row, synthetic or real
3. its own run: Job B's job, running, with exactly the two run IDs, and the commit it runs
4. the GitHub run, read from GitHub's public API with no credential: the approval workflow's dispatch on `main`, from
   the commit Job B runs, with the exact name for the Job A run, first attempt, approved for `june-run` by the owner
   and never rejected (J11, J16 item 7)
5. Job A's run again, as the approval workflow checks it (J16 item 5)
6. the sample: the row's list, the dry run's or the June list, whose bytes hash to the row's list hash, with only
   IDs of its kind, checked before any SQL runs, then exactly its rows from the June tables, each with its content
   hash
7. Job A's figures, computed again from the rows: the same counts, and no more tokens or cost than approved
8. the refit of TF-IDF + LR from July's training rows, which must give every committed July development label
   (`voc.june_refit`, pull request 6b)
9. when it calls the API, room in the June ledger for the whole run's worst case (J12)
Then it marks the GitHub run, and the Job A run for its row, as used, and for a real row writes the row's start
marker. A marker already there is refused, and an upload never overwrites. Then it labels, writes the note or the
results files and returns the contract's exit value (J16 item 8).

B21 and J5: nothing here prints. Every refusal holds fixed text, IDs and counts only, and carries no earlier exception.
"""
import csv
import hashlib
import io
import json
import re
import time
from decimal import Decimal
from pathlib import Path

from voc import approval
from voc.job_a import VOLUME

CONTRACT = "voc-june-1"
USED_FOLDER = VOLUME + "/job_b_used"
# The results volume sits in a schema of its own, apart from `default`, which holds the raw uploads, so the
# reader's grants never reach a schema with complaint data (J13, review of #100).
RESULTS_VOLUME = "/Volumes/workspace/voc_results/voc_results"
DRY_RUN_FILE = "DRY_RUN.txt"
DRY_RUN_NOTE = ("This folder is a synthetic dry run of spec 004's Job B (pull request 6a). Job B labelled the "
                "synthetic sample with the mock backend and wrote no results file. The results files arrive in pull "
                "request 6b.\n")
DRY_RUN_NOTE_API = ("This folder is a synthetic dry run of spec 004's Job B (pull request 6b, part 3b). Job B "
                    "labelled the synthetic sample with the API, through the June ledger, and wrote no results "
                    "file.\n")
# The Databricks secret scope that holds the cloud workspace's API key and its ID (J12). The notebook reads them.
SECRET_SCOPE = "voc-june"
PARAMETERS = ("job_a_run_id", "github_run_id", "job_b_run_id")
JOB_PARAMETERS = ("job_a_run_id", "github_run_id")
GITHUB_RUNS = "https://api.github.com/repos/MannyAdc/voc-demo/actions/runs"
OWNER = "MannyAdc"
ENVIRONMENT = "june-run"
# GitHub allows 60 calls an hour without a token, per address, and serverless addresses are shared (J11).
GITHUB_TRIES = 3
GITHUB_WAITS = (20, 60)
COMMIT = re.compile(r"[0-9a-f]{40}")
HASH = re.compile(r"[0-9a-f]{64}")
SYNTHETIC_ID = re.compile(r"SYN-[0-9]{1,19}")
# A CFPB complaint ID, as J16 checks IDs (6b part 5).
REAL_ID = re.compile(r"[1-9][0-9]{0,18}")
# The start markers of real runs: one for each run log row, written before the first model call (J1, 6b part 5).
START_FOLDER = VOLUME + "/job_b_started"


class JobBError(ValueError):
    """A refusal with fixed text, IDs and counts only (B21, J5)."""


def _checked(function, *args):
    """Calls the approval workflow's own check, and gives its refusal as Job B's, with no earlier exception."""
    try:
        return function(*args), None
    except approval.ApprovalError as err:
        message = str(err)
    raise JobBError(message)


# 0. Its packages

REQUIREMENTS = Path("cloud") / "job_b" / "requirements.txt"


def _installed_version(name):
    from importlib import metadata

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


# A pin, then at most a marker and a line continuation (second review of #108, nit 5).
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)(\s*;[^\\]*)?(?:\s*\\)?")
# A marker may not hold a token that starts with "-", which pip would read as an option. A legal marker never
# does (review of #109, nit 5, and its second review, nit 4).
OPTION = re.compile(r"(?:^|[\s;])-")


def checked_packages(root):
    """Every package of Job B's requirements file is installed at its pinned version (pull request 6b). Review of
    #108, minor 4: a missing file, or a line at column 0 that is not a pinned package, is refused too."""
    try:
        lines = (Path(root) / REQUIREMENTS).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):  # second review of #108, nit 4
        lines = None
    if lines is None:
        raise JobBError("Job B's requirements file cannot be read")
    wrong = []
    for line in lines:
        if line and not line[0].isspace() and not line.startswith("#"):
            pin = PIN.fullmatch(line)
            if pin is None or (pin.group(3) is not None and OPTION.search(pin.group(3))):
                raise JobBError("Job B's requirements file has a line that is not a pinned package")
            if _installed_version(pin.group(1)) != pin.group(2):
                wrong.append(pin.group(1))
    if wrong:
        raise JobBError("Job B's packages are not the locked versions: " + ", ".join(sorted(wrong)))


# 1. The parameters


def parameters(values):
    """J16 item 1: exactly the two run IDs and Job B's own run ID, each a whole number in range."""
    if set(values) != set(PARAMETERS):
        raise JobBError("Job B takes exactly job_a_run_id, github_run_id and job_b_run_id")
    return tuple(_checked(approval.parse_id, values[name], name)[0] for name in PARAMETERS)


# 2. The run log's last row


def checked_target(root):
    (run_target, entry), _ = _checked(approval._target_and_entry, root)
    # 6b part 5: a real first row too. A later row, a resume, a reproduction or a second run, is refused, since
    # Job A runs only a first row (Known limits).
    if (run_target.kind, run_target.entry_kind) not in (("synthetic", "synthetic"), ("real", "real")):
        raise JobBError("Job B runs only a first row of the run log in this build")
    return run_target, entry


# 3. Its own run


def _job_parameters(run):
    items = run.get("job_parameters")
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        return None
    names = [i.get("name") for i in items]
    if not all(isinstance(n, str) for n in names) or sorted(names) != sorted(JOB_PARAMETERS):
        return None
    return {i["name"]: i.get("value") for i in items}


def _task_commit(task):
    source = task.get("git_source") if isinstance(task, dict) else None
    snapshot = source.get("git_snapshot") if isinstance(source, dict) else None
    return snapshot.get("used_commit") if isinstance(snapshot, dict) else None


def _run_commit(run):
    """The commit Job B runs. Databricks keeps it on each task of the run, at `git_source.git_snapshot.used_commit`,
    and not on the run itself (the dry run's round 2, 10 November). Every task must be Job B's one task, and every
    attempt of it, since Databricks retried it once on its own in round 2, must name the same commit."""
    tasks = run.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None
    if not all(isinstance(task, dict) and task.get("task_key") == "job_b" for task in tasks):
        return None
    commits = {_task_commit(task) for task in tasks}
    if len(commits) != 1:
        return None
    return commits.pop()


def checked_own_run(run, job_b_run_id, job_b_job_id, job_a_run_id, github_run_id):
    """Its own run is Job B's, still running, with exactly the two run IDs it was given. Returns the commit it runs.
    So a run ID filled by hand that names another run is refused (owner decision, 8 November)."""
    commit = _run_commit(run)
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
    """The dry run's frozen list file's bytes, `complaint_id,content_hash` rows (pull request 9a). Its SHA-256 must
    be the run log row's list hash (review of #98), which `checked_list` checks."""
    from voc.job_a import list_file

    return list_file(root, run_target.kind).read_bytes()  # the June list for a real row (6b part 5)


ANSWERS = Path("cloud") / "job_b" / "dry_run_answers.json"


def mock_answers(root, run_target):
    """The mock backend's synthetic answers for the dry run's prompts (pull request 9a), each a prompt and a text."""
    if run_target.kind != "synthetic":
        raise JobBError("Job B reads the dry run's mock answers for a synthetic row only")
    try:
        answers = json.loads((Path(root) / ANSWERS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        answers = None
    if (not isinstance(answers, list) or not all(isinstance(a, dict) and set(a) == {"prompt", "text"}
                                                 and all(isinstance(v, str) for v in a.values()) for a in answers)):
        raise JobBError("the dry run's mock answers cannot be read")
    return answers


def checked_list(data, run_target):
    """The dry run's list, bound to its row: its bytes hash to the row's list hash. Every ID synthetic and every
    hash a SHA-256, checked before any SQL runs (review of #98). Returns complaint ID to content hash."""
    name, pattern, kind_word = _list_words(run_target.kind)
    if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != run_target.list_hash:
        raise JobBError(f"{name} does not match the run log row's list hash")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is None:
        raise JobBError(f"{name} is not UTF-8")
    records = list(csv.reader(io.StringIO(text)))
    if (len(records) < 2 or records[0] != ["complaint_id", "content_hash"]
            or not all(len(r) == 2 for r in records[1:])):
        raise JobBError(f"{name} is not a list of complaint IDs and content hashes")
    listed = {}
    for cid, digest in records[1:]:
        if not pattern.fullmatch(cid):
            raise JobBError(f"{name} holds an ID that is not {kind_word}")
        if not HASH.fullmatch(digest):
            raise JobBError(f"{name} holds a content hash that is not a SHA-256")
        listed[cid] = digest
    if len(listed) != len(records) - 1:
        raise JobBError(f"{name} repeats a complaint ID")
    return listed


def _list_words(kind):
    """The list's name in refusals, its ID pattern and the word for a wrong ID, by the row's kind."""
    if kind == "real":
        return "the June list", REAL_ID, "a CFPB complaint ID"
    return "the dry run's list", SYNTHETIC_ID, "synthetic"


def checked_rows(listed, rows, kind="synthetic"):
    """`rows` are (complaint_id, product, narrative). Refused unless they are exactly the listed sample, every ID
    of the row's kind, synthetic or a CFPB complaint ID, each row with its content hash. Returns the count."""
    from voc.data import content_hash

    name, pattern, kind_word = _list_words(kind)
    if not all(isinstance(cid, str) and pattern.fullmatch(cid) for cid in listed):
        raise JobBError(f"{name} holds an ID that is not {kind_word}")
    given = {}
    for cid, product, narrative in rows:
        if not isinstance(cid, str) or not pattern.fullmatch(cid):
            raise JobBError(f"the sample holds an ID that is not {kind_word}")
        given[cid] = (product, narrative)
    if len(given) != len(rows):
        raise JobBError("the sample's rows repeat a complaint ID")
    extra, missing = set(given) - set(listed), set(listed) - set(given)
    if extra:
        raise JobBError(f"{len(extra)} sample rows are not in {name}")
    if missing:
        raise JobBError(f"{len(missing)} complaints of {name} are missing from the June tables")
    changed = sum(content_hash(narrative, product) != listed[cid] for cid, (product, narrative) in given.items())
    if changed:
        raise JobBError(f"{changed} sample rows do not match their content hash in {name}")
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
            # The SDK's NotFound, or any of its subclasses, means the file is missing (review of #98).
            missing = any(kind.__name__ == "NotFound" for kind in type(err).__mro__)
            found, failure = False, None if missing else type(err).__name__
        if failure is not None:
            raise JobBError(f"the volume could not be read: {failure}")
        return found

    def delete(self, path):
        """Best effort: deletes one file, so a half pair of results files is not left (review of #113, item 2)."""
        try:
            self.files.delete(path)
        except Exception:  # noqa: BLE001, the run already reports its stop, and the owner deletes by hand if need be
            pass

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


# 9. Room in the June ledger (J12, review of #110, minor 1)


def checked_june_ledger(root, worst_case):
    """The June ledger has room for the whole run's worst case, counting what is used and what is still reserved,
    for instance by a run that crashed. Checked before any marker, only when Job B calls the API."""
    from voc import june_ledger
    from voc.budget import BudgetError, effective_cap

    try:
        state, failure = june_ledger.open_ledger(root, june_ledger.LEDGER).state(), None
    except BudgetError as err:
        state, failure = None, str(err)
    if failure is not None:
        raise JobBError(failure)
    if state["overrun"] is not None:  # review of #111, minor 3: before the markers, so no approval is spent
        raise JobBError("the June ledger holds an overrun, so Job B refuses before it marks anything")
    left = effective_cap(state) - state["used"] - state["reserved"]
    if worst_case > left:
        raise JobBError(f"the June ledger has {left} tokens left under its cap, less than the run's worst case of "
                        f"{worst_case}")


# 8. The refit (J7, pull request 6b)


def july_export(root):
    """The pinned July export, in the raw volume where the owner uploaded it (T021b)."""
    from voc.datafile import load_pins

    return f"{VOLUME}/{load_pins(Path(root) / 'config' / 'data_files.toml')['july_2026']['file_name']}"


def refit_check(root):
    """The refit model, once it gives every committed July development label. Its DuckDB file lives in a
    temporary folder inside Databricks, and goes with it (J4)."""
    import tempfile

    from voc import june_refit

    with tempfile.TemporaryDirectory() as work:
        try:
            return june_refit.refit(root, july_export(root), work)
        except june_refit.RefitError as err:
            message = str(err)
    raise JobBError(message)


# The labelling and the exit value


def _outcomes(root, rows, answers):
    """The mock backend's decisions for the rows, and whether the labelling stopped."""
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
    return outcomes, stopped


def _api_outcomes(root, rows, backend, run_target):
    """The decisions from the API, through the June ledger and the volume's recordings, whether the run stopped,
    and its stop reason (6b, part 3b). The synthetic sample's recordings are kept apart from June's."""
    from voc import june_ledger, pipeline
    from voc.labels import load_labels
    from voc.pipeline import NOT_RUN_BUDGET, Complaint, RunStopped

    version = pipeline.load_prompt_version(root, "v1")
    labels = load_labels(root / "config" / "labels.toml")
    recordings = june_ledger.RECORDINGS_DRY if run_target.kind == "synthetic" else june_ledger.RECORDINGS
    caller = june_ledger.june_caller(root, backend, dict(version.settings), ledger_path=june_ledger.LEDGER,
                                     recordings=recordings)
    complaints = [Complaint(cid, narrative) for cid, _, narrative in rows]
    before, started = caller.ledger.state()["used"], time.monotonic()
    try:
        outcomes, stopped, reason = pipeline.label_complaints(complaints, version, labels, caller.call, "api"), False, None
    except RunStopped as stop:
        outcomes, stopped, reason = stop.outcomes, True, stop.reason
    if not stopped and any(o.decision.reason == NOT_RUN_BUDGET for o in outcomes):
        stopped, reason = True, "ledger_cap"
    spent = {"ledger_tokens": caller.ledger.state()["used"] - before,
             "run_seconds": round(time.monotonic() - started, 3)}
    return outcomes, stopped, reason, spent


def _results_written(root, store, rows, outcomes, model, run_info, spent, job_b_run_id):
    """A finished real run's two results files, built, checked and written (J11, 6b part 5). False when anything
    fails, so the run reports a stop and leaves no results file (J1, review of #113, items 1 and 2)."""
    from voc import june_results, pipeline

    version = pipeline.load_prompt_version(root, "v1")
    try:
        csv_text, summary = june_results.build(root, rows, outcomes, model, version, run_info,
                                               ledger_tokens=spent["ledger_tokens"],
                                               run_seconds=spent["run_seconds"])
        json_text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        june_results.check(root, csv_text, json_text)
        failed = False
    except Exception:  # noqa: BLE001, any failure after the spend gives the exit value `error`, never a crash
        failed = True
    if failed:
        return False
    folder = f"{RESULTS_VOLUME}/june-{job_b_run_id}"
    first, second = (f"{folder}/{name}" for name in june_results.FILES)
    try:
        store.create(first, csv_text.encode("utf-8"))
    except JobBError:
        return False
    try:
        store.create(second, json_text.encode("utf-8"))
    except JobBError:
        store.delete(first)  # the Files API has no rename, so the first file goes again
        return False
    return True


def exit_value(run_target, complaints, count, stopped, job_b_run_id, stop_reason=None):
    """J16 item 8: a finished run names `june-<Job B run ID>`, and a stopped one no folder and its reason."""
    value = {"contract": CONTRACT, "kind": run_target.kind, "entry_kind": run_target.entry_kind,
             "complaints": complaints, "labelled": count, "stopped": stopped,
             "stop_reason": (stop_reason or "error") if stopped else None,
             "results_folder": None if stopped else f"june-{job_b_run_id}"}
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def run(root, values, databricks, github, store, run_sql, sleep=time.sleep, backend=None):
    """Job B's dry run, end to end. Returns the exit value as compact JSON. With a `backend` from the notebook it
    labels through the API and the June ledger (6b, part 3b). With none, it serves the mock answers."""
    from pathlib import Path

    from voc.job_a import JobAError, figures

    root = Path(root)
    checked_packages(root)
    job_a_run_id, github_run_id, job_b_run_id = parameters(values)
    run_target, _ = checked_target(root)
    if run_target.kind == "real" and backend is None:
        raise JobBError("a real run labels through the API only")
    settings, _ = _checked(approval.cloud_settings, root)
    commit = checked_own_run(databricks.get("/api/2.2/jobs/runs/get", {"run_id": job_b_run_id}), job_b_run_id,
                             settings["job_b_job_id"], job_a_run_id, github_run_id)
    checked_github_run(github_json(github, f"/{github_run_id}", sleep), github_run_id, job_a_run_id, commit)
    checked_approvals(github_json(github, f"/{github_run_id}/approvals", sleep))
    (_, _, approved, _), _ = _checked(approval._checked_job_a, root, job_a_run_id, databricks)
    listed = checked_list(listed_for(root, run_target), run_target)
    rows = _spark_rows(run_sql, listed)[0]
    complaints = checked_rows(listed, rows, run_target.kind)
    try:
        computed, failure = figures(root, rows, 0), None
    except JobAError as err:
        computed, failure = None, str(err)
    if failure is not None:
        raise JobBError(failure)
    checked_figures(computed, approved)
    model = refit_check(root)
    if backend is not None:
        checked_june_ledger(root, computed["worst_case_tokens"])
    answers = mock_answers(root, run_target) if backend is None else None
    start = f"{START_FOLDER}/row{run_target.row}-{run_target.list_hash}.json"
    if run_target.kind == "real" and store.exists(start):
        raise JobBError(f"run log row {run_target.row} has already been started")
    marked_used(store, run_target, job_a_run_id, github_run_id, job_b_run_id)
    if run_target.kind == "real":  # J1: before the first model call, and only once for the row
        store.create(start, _compact({"row": run_target.row, "job_a_run_id": job_a_run_id,
                                      "github_run_id": github_run_id, "job_b_run_id": job_b_run_id}))
    if backend is None:
        (outcomes, stopped), reason, note = _outcomes(root, rows, answers), None, DRY_RUN_NOTE
    else:
        outcomes, stopped, reason, spent = _api_outcomes(root, rows, backend, run_target)
        note = DRY_RUN_NOTE_API
    if run_target.kind == "real":
        run_info = {"entry_list_sha256": run_target.list_hash, "entry_code_sha256": run_target.code_hash,
                    "job_a_run_id": job_a_run_id, "job_b_run_id": job_b_run_id, "github_run_id": github_run_id}
        if not stopped and not _results_written(root, store, rows, outcomes, model, run_info, spent,
                                                job_b_run_id):
            stopped, reason = True, "error"
        return exit_value(run_target, complaints, len(outcomes), stopped, job_b_run_id, reason)
    if not stopped:
        # Review of #99: the split is seen in the cloud, as counts only.
        accepted = sum(o.decision.label is not None for o in outcomes)
        counts = f"Labelled: {len(outcomes)}. Accepted: {accepted}. Quarantined: {len(outcomes) - accepted}.\n"
        store.create(f"{RESULTS_VOLUME}/june-{job_b_run_id}/{DRY_RUN_FILE}",
                     (note + counts).encode("utf-8"))
    return exit_value(run_target, complaints, len(outcomes), stopped, job_b_run_id, reason)
