"""B17: the one scored run of the frozen test set, behind the owner's `voc final` command.

Before any model call it checks that:
- the working tree is clean
- the run is on a branch, not on main, so its log entry reaches main through a pull request
- the remaining cap covers the worst case for the whole test set, retries included
- if a test run is already logged, in the repo or in the home folder, a written reason is given

Then it writes the entry to `runs/TEST_RUNS.md` and commits it, and adds it to a second log beside the ledger,
so a crashed run on a deleted branch still counts. A second run's reason also goes in `BUILD_LOG.md`. Only then
does it label the test set and score it. The test rows are loaded here, through the content-hash check, and
nowhere else.
"""
import subprocess
import time
from datetime import datetime
from pathlib import Path

from voc import pipeline
from voc.baselines import cut_text
from voc.budget import load_config, voc_home, worst_case
from voc.data import _manifest, read_splits, verify_ids
from voc.evaluate import score_test_set
from voc.labels import load_labels
from voc.load import DB_PATH
from voc.prompt import build_prompt
from voc.replay import MAX_RETRIES

LOG = Path("runs") / "TEST_RUNS.md"
LOG_INTRO = """# Test runs

One row per scoring of the frozen test set (B17). Rows are only ever added. CI checks that this file only grows
compared with main. Each row is committed before the scoring starts.

| Date | Prompt | Test list hash | Model | Complaints | Reason |
|---|---|---|---|---|---|
"""


class TestRunError(ValueError):
    __test__ = False  # not a pytest test class


def home_log():
    return voc_home() / "test_runs.log"


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def _logged_runs(root):
    """How many test runs are already logged, in the repo log and in the home log together."""
    path = Path(root) / LOG
    repo = sum(line.startswith("| 20") for line in path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
    home = home_log()
    other = len([line for line in home.read_text(encoding="utf-8").splitlines() if line.strip()]) if home.exists() else 0
    return repo + other


def test_complaints(root):
    """The test complaints, checked against the committed list by ID and content hash (B16, B17)."""
    root = Path(root)
    splits_dir = root / "splits"
    wanted = set(read_splits(splits_dir)["test"])
    rows = pipeline._rows_by_id(root / DB_PATH, _manifest(splits_dir)["month"], wanted)
    if {row.complaint_id for row in rows} != wanted:
        raise TestRunError(f"{len(wanted - {r.complaint_id for r in rows})} test complaints are missing from the "
                           "staged table")
    verify_ids(splits_dir, "test", rows)
    return sorted((pipeline.Complaint(row.complaint_id, row.narrative) for row in rows),
                  key=lambda c: pipeline._id_number(c.complaint_id))


def preflight(root, version_name, reason, remaining):
    """Every check that must pass before anything is written or any model is called. Returns what the run needs."""
    root = Path(root)
    status = _git(root, "status", "--porcelain")
    if status.returncode != 0 or status.stdout.strip():
        raise TestRunError("the working tree is not clean. Commit or remove every change first")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch in ("main", "HEAD", ""):
        raise TestRunError("run it on a branch, not on main, so its log entry reaches main through a pull request")
    version = pipeline.load_prompt_version(root, version_name)
    labels = load_labels(root / "config" / "labels.toml")
    names = [label.name for label in labels]
    defined = pipeline.definitions(labels)
    complaints = test_complaints(root)
    margin = load_config(root)["input_margin_tokens"]
    per_try = sum(worst_case(build_prompt(version.instructions, names, cut_text(c.narrative)[0],
                                          complaint_id=c.complaint_id, definitions=defined).prompt,
                             version.settings["max_tokens"], margin) for c in complaints)
    worst = per_try * (MAX_RETRIES + 1)
    if remaining < worst:
        raise TestRunError(f"the cap has {remaining:,} tokens left, and the test set needs up to {worst:,} in the "
                           "worst case, retries included")
    earlier = _logged_runs(root)
    if earlier and not (reason and reason.strip()):
        raise TestRunError(f"{earlier} test run(s) are already logged. A second run needs --reason, which goes in "
                           "the logs and in BUILD_LOG.md")
    return version, labels, complaints, earlier, worst


def _log_the_run(root, version, complaints, reason, earlier, now):
    """Write the entry to both logs and commit the repo log, before any model call."""
    root = Path(root)
    manifest = _manifest(root / "splits")
    when = now.strftime("%Y-%m-%d %H:%M")
    cells = [when, version.name, manifest["lists"]["test"]["sha256"], version.settings["model"],
             str(len(complaints)), (reason or "first test run").replace("|", "/").replace("\n", " ")]
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(LOG_INTRO, encoding="utf-8", newline="")
    with open(path, "a", encoding="utf-8", newline="") as out:
        out.write("| " + " | ".join(cells) + " |\n")
    home = home_log()
    home.parent.mkdir(parents=True, exist_ok=True)
    with open(home, "a", encoding="utf-8", newline="") as out:
        out.write(" | ".join(cells) + f" | {root}\n")
    paths = [str(LOG)]
    if earlier:
        with open(root / "BUILD_LOG.md", "a", encoding="utf-8", newline="") as out:
            out.write(f"- {now.strftime('%H:%M')} Test run number {earlier + 1} of prompt {version.name}. "
                      f"Reason: {cells[-1]}\n")
        paths.append("BUILD_LOG.md")
    _git(root, "add", *paths)
    commit = _git(root, "commit", "-q", "-m", f"Log a test run of prompt {version.name} before scoring")
    if commit.returncode != 0:
        raise TestRunError("the log entry could not be committed, so nothing was scored. The home log keeps the entry")


def run(root, version_name, reason, call, remaining, backend_name="api", now=None, add_to_summary=None):
    """Check, log and commit, then label and score the test set. Returns the run summary and the figures.

    `add_to_summary(outcomes)` gives extra summary fields, such as the cost, before the results are written.
    """
    root = Path(root)
    version, labels, complaints, earlier, worst = preflight(root, version_name, reason, remaining)
    _log_the_run(root, version, complaints, reason, earlier, now or datetime.now())
    stopped = None
    started = time.monotonic()
    try:
        outcomes = pipeline.label_complaints(complaints, version, labels, call, backend_name)
    except pipeline.RunStopped as err:  # the outcomes so far are still written, with the stop (B7, B19)
        stopped, outcomes = err, err.outcomes
    names = [label.name for label in labels]
    summary = pipeline.summarise(outcomes, "test", version, backend_name,
                                 _manifest(root / "splits")["lists"]["test"]["sha256"], stopped=stopped,
                                 run_seconds=time.monotonic() - started)
    if add_to_summary is not None:
        summary.update(add_to_summary(outcomes))
    pipeline.write_run(root / "results" / "labels", outcomes, summary, version, names)
    if stopped is not None:
        raise TestRunError(f"the run stopped early, so it is not scored: {stopped}. It is logged, so a new run "
                           "needs --reason")
    figures = score_test_set(root, version_name, reason or "first test run")
    return {"summary": summary, "figures": figures, "worst_case_tokens": worst}


def format_report(report):
    s, f = report["summary"], report["figures"]
    low, high = f["interval"]
    return "\n".join([
        f"test run, prompt {f['prompt_version']}: {s['complaints']} complaints, accepted {s['accepted']}, "
        f"quarantined {s['quarantined']}",
        f"these are {f['figures_are']}",
        f"LLM re-weighted strict accuracy {f['llm']['reweighted_accuracy'] * 100:.1f}%, TF-IDF at the same "
        f"coverage {f['tfidf']['reweighted_accuracy'] * 100:.1f}%",
        f"difference {f['difference'] * 100:+.1f} points, 95% interval {low * 100:+.1f} to {high * 100:+.1f} points",
        f"verdict: {f['verdict'] or 'none, because some complaints were not run (budget)'}",
        f"results: results/labels/{f['prompt_version']}_test.csv and results/eval/{f['prompt_version']}_test.json"])
