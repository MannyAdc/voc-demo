"""T006b: the mechanical checks behind `/merge-verdict`.

The checks are pure functions on the JSON that `gh pr view` returns, with each
commit's files and parent count added. A thin layer at the end fetches that JSON
with read-only `gh` calls and can try the branches merged together.

Each check ends as PASS, FAIL or FOR CLAUDE. FOR CLAUDE is a judgement the script
cannot make, so it is never counted as a pass. The last line printed is the
script's verdict, with its exit code:

- MERGE (0): every check passed.
- FIX FIRST (1): at least one check failed, with the reasons.
- PENDING (3): nothing failed, but Claude must judge the FOR CLAUDE items.
- An error (2): the data could not be read, or the script crashed.

The owner still merges.

Only check names, statuses, short commit IDs, file paths and counts are printed.
Commit messages and comment text are never printed. An unexpected error is
printed as its type only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PASS, FAIL, CLAUDE = "PASS", "FAIL", "FOR CLAUDE"
# The job names in .github/workflows/ci.yml. A test keeps the two the same.
EXPECTED_CHECKS = ("tests", "repo-checks", "secret-scan")
GREEN = {"SUCCESS", "NEUTRAL"}
REVIEW_HEADING = "## Reviewer findings"
BASE = "main"
GH_WINDOWS = Path(r"C:\Program Files\GitHub CLI\gh.exe")
PR_FIELDS = ("number,state,isDraft,mergeable,isCrossRepository,baseRefName,headRefName,headRefOid,"
             "statusCheckRollup,commits,files,comments")
EXIT_MERGE, EXIT_FIX_FIRST, EXIT_ERROR, EXIT_PENDING = 0, 1, 2, 3
# The trial merge runs a pull request's tests on this machine. These never reach them.
SECRET_WORDS = ("KEY", "TOKEN", "SECRET")
DROPPED_VARS = ("VOC_DATA_DIR", "VOC_NEXT_DATA_DIR", "VOC_MOCK_FIXTURES")
RED_FILE = re.compile(r"tests/test_[^/]*\.py")
CODE_SUFFIXES = (".py", ".sql", ".sh", ".ps1")
# The dashboard page is its folder, whatever the file type (found on #51). requirements.txt is what Azure builds from.
# config/ (labels and prompts) is left out on purpose: a prompt or label change is judged by /eval and the spec.
CODE_FOLDERS = (".githooks/", ".github/workflows/", "dbt/", "src/voc/web/")
CODE_FILES = ("pyproject.toml", "uv.lock", "requirements.txt", ".claude/settings.json")


@dataclass(frozen=True)
class Check:
    pr: int | None
    name: str
    status: str
    detail: str


class GhError(Exception):
    """A `gh` or `git` call failed. The text is ours, plus the tool's exit code."""


def _short(oid):
    return oid[:7]


def _when(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


# CI is green


def _check_name(item):
    return item.get("name") or item.get("context") or "unnamed check"


def _check_state(item):
    """One rollup item as "green", "running" or the failing conclusion."""
    if item.get("__typename") == "StatusContext":
        state = item.get("state") or "UNKNOWN"
        if state in ("PENDING", "EXPECTED"):
            return "running"
        return "green" if state in GREEN else state.lower()
    if item.get("status") != "COMPLETED":
        return "running"
    conclusion = item.get("conclusion") or "UNKNOWN"
    return "green" if conclusion in GREEN else conclusion.lower()


def check_ci(pr):
    """CI is green on the latest commit: every check finished green and every CI job reported."""
    number, head = pr["number"], _short(pr["headRefOid"])
    rollup = pr.get("statusCheckRollup") or []
    if not rollup:
        return Check(number, "CI", FAIL, f"no checks reported on {head}")
    problems = []
    for item in rollup:
        state = _check_state(item)
        if state == "running":
            problems.append(f"{_check_name(item)} still running")
        elif state != "green":
            problems.append(f"{_check_name(item)} {state}")
    seen = {_check_name(item) for item in rollup}
    problems += [f"{name} missing" for name in EXPECTED_CHECKS if name not in seen]
    if problems:
        return Check(number, "CI", FAIL, f"not green on {head}: {', '.join(sorted(set(problems)))}")
    return Check(number, "CI", PASS, f"green on {head}: {', '.join(EXPECTED_CHECKS)}")


# The red commit came before the code


def is_red_file(path):
    """A file a red test commit may hold: a test file directly in tests/."""
    return bool(RED_FILE.fullmatch(path))


def is_code_file(path):
    """A file whose change needs a red test commit first. Docs, results, config and tests do not."""
    if path.startswith("tests/"):
        return False
    return path.endswith(CODE_SUFFIXES) or path.startswith(CODE_FOLDERS) or path in CODE_FILES


def check_red_first(pr):
    """A commit with only tests/test_*.py files comes before the first commit that changes code.

    Merge commits are left out, because they bring in files from the base branch.
    """
    number = pr["number"]
    commits = [c for c in pr["commits"] if c.get("parents", 1) < 2]
    code = [i for i, c in enumerate(commits) if any(is_code_file(p) for p in c["files"])]
    if not code:
        return Check(number, "red commit first", PASS, "no code files changed, so no red commit is needed")
    red = [i for i, c in enumerate(commits) if c["files"] and all(is_red_file(p) for p in c["files"])]
    first_code = _short(commits[code[0]]["oid"])
    if not red:
        return Check(number, "red commit first", FAIL,
                     f"no commit holds only tests/test_*.py files, first code commit {first_code}")
    if red[0] > code[0]:
        return Check(number, "red commit first", FAIL,
                     f"code commit {first_code} came before the first red commit {_short(commits[red[0]]['oid'])}")
    return Check(number, "red commit first", PASS,
                 f"red commit {_short(commits[red[0]]['oid'])} came before the first code commit {first_code}")


# Every review finding is fixed or deferred


def check_review(pr):
    """A reviewer findings comment exists. Whether each finding is handled is for Claude to judge."""
    number = pr["number"]
    findings = [c for c in pr.get("comments") or [] if (c.get("body") or "").lstrip().startswith(REVIEW_HEADING)]
    if not findings:
        return Check(number, "review findings", FAIL, f"no comment starts with '{REVIEW_HEADING}'")
    # Never a pass, even when the comment says it found nothing: only Claude can judge that.
    latest = max(findings, key=lambda c: _when(c["createdAt"]))
    posted = _when(latest["createdAt"])
    after = sum(1 for c in pr["commits"] if _when(c["committedDate"]) > posted)
    stamp = latest["createdAt"].replace("T", " ").replace("Z", " UTC")
    if after:
        word = "commit" if after == 1 else "commits"
        return Check(number, "review findings", CLAUDE,
                     f"{after} {word} after the findings of {stamp}. Check that each finding the owner chose "
                     "is fixed and each other one is deferred with a reason")
    return Check(number, "review findings", CLAUDE,
                 f"no commit after the findings of {stamp}. Check that the owner chose to fix none "
                 "and each finding is deferred with a reason")


def check_build_log(pr):
    """Whether BUILD_LOG.md is up to date is for Claude to judge."""
    touched = any(f["path"] == "BUILD_LOG.md" for f in pr.get("files") or [])
    where = "this branch changes BUILD_LOG.md" if touched else "this branch does not change BUILD_LOG.md"
    return Check(pr["number"], "build log", CLAUDE,
                 f"{where}. Check it has the work start, the findings, the owner's choices and any AI mistake")


# The pull request itself


def check_open(pr):
    number, state, base = pr["number"], pr.get("state"), pr.get("baseRefName")
    if state != "OPEN":
        return Check(number, "open against main", FAIL, f"the pull request is {str(state).lower()}")
    if base != BASE:
        return Check(number, "open against main", FAIL, f"the base branch is {base}, not {BASE}")
    return Check(number, "open against main", PASS, f"open, base {BASE}")


def check_conflicts(pr):
    number, mergeable = pr["number"], pr.get("mergeable")
    if mergeable == "MERGEABLE":
        return Check(number, "no conflicts", PASS, f"GitHub can merge it into {pr.get('baseRefName')}")
    if mergeable == "CONFLICTING":
        return Check(number, "no conflicts", FAIL, f"it conflicts with {pr.get('baseRefName')}")
    return Check(number, "no conflicts", CLAUDE, "GitHub has not worked it out yet. Run the script again")


# Parallel branches


def check_shared_files(prs):
    """Parallel branches touch no shared file."""
    owners = {}
    for pr in prs:
        for f in pr.get("files") or []:
            owners.setdefault(f["path"], set()).add(pr["number"])
    shared = sorted(path for path, numbers in owners.items() if len(numbers) > 1)
    if shared:
        listed = ", ".join(shared[:5]) + (f" and {len(shared) - 5} more" if len(shared) > 5 else "")
        return Check(None, "no shared file", FAIL, f"{len(shared)} shared: {listed}")
    return Check(None, "no shared file", PASS, f"{len(owners)} files, none in two pull requests")


def merge_order(prs):
    """The pull request opened first is merged first."""
    return sorted(pr["number"] for pr in prs)


def check_pr(pr):
    return [check_open(pr), check_ci(pr), check_conflicts(pr), check_red_first(pr), check_review(pr),
            check_build_log(pr)]


def check_all(prs, merged=None):
    """Every check on every pull request, plus the parallel checks when there is more than one.

    `merged` is the trial merge check, if one was run.
    """
    checks = [c for pr in sorted(prs, key=lambda p: p["number"]) for c in check_pr(pr)]
    if len(prs) > 1:
        checks.append(check_shared_files(prs))
    if merged is not None:
        checks.append(merged)
    elif len(prs) > 1:
        checks.append(Check(None, "tests on the merge", CLAUDE,
                            "not run. Run again with --test-merge, or merge the branches by hand and run the tests"))
    return checks


# The verdict


def _label(check):
    return f"#{check.pr} {check.name}" if check.pr is not None else check.name


def verdict(checks):
    """One line: FIX FIRST with every failure, PENDING with every judgement item, or MERGE."""
    failed = [c for c in checks if c.status == FAIL]
    if failed:
        return "FIX FIRST: " + ". ".join(f"{_label(c)}: {c.detail}" for c in failed)
    judged = [c for c in checks if c.status == CLAUDE]
    if judged:
        return "PENDING: Claude must judge: " + ", ".join(_label(c) for c in judged)
    return "MERGE"


def exit_code(checks):
    if any(c.status == FAIL for c in checks):
        return EXIT_FIX_FIRST
    if any(c.status == CLAUDE for c in checks):
        return EXIT_PENDING
    return EXIT_MERGE


def format_report(checks, order):
    lines = [f"{c.status:<10} {_label(c)}: {c.detail}" for c in checks]
    if len(order) > 1:
        lines.append("Merge order: " + ", then ".join(f"#{n}" for n in order))
    lines.append(verdict(checks))
    return "\n".join(lines)


# The trial merge


def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True)


def _git_out(repo, *args):
    result = _git(repo, *args)
    if result.returncode != 0:
        raise GhError(f"git {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def merged_tree(repo, base, heads):
    """Merge each (number, commit) onto `base` in order, with no work tree, commit or hook.

    Returns (None, tree) on success, or (number, None) for the first pull request that conflicts.
    """
    tree = base
    for number, oid in heads:
        merge_base = _git_out(repo, "merge-base", base, oid)
        result = _git(repo, "merge-tree", "--write-tree", f"--merge-base={merge_base}", tree, oid)
        if result.returncode == 1:
            return number, None
        if result.returncode != 0:
            raise GhError(f"git merge-tree failed (exit {result.returncode})")
        tree = result.stdout.split()[0]
    return None, tree


def _summary(output):
    lines = [line.strip("= ").strip() for line in output.splitlines() if line.strip("= ").strip()]
    return lines[-1] if lines else "no pytest output"


def trial_env(environ):
    """The environment for a trial merge's tests: no git variables, secrets or data folders, and the mock backend.

    A variable is dropped when its name holds KEY, TOKEN or SECRET in any case.
    """
    env = {}
    for name, value in environ.items():
        upper = name.upper()
        if upper.startswith("GIT_") or upper in DROPPED_VARS or any(word in upper for word in SECRET_WORDS):
            continue
        env[name] = value
    env["LLM_BACKEND"] = "mock"
    return env


def run_tests_on_tree(repo, tree):
    """Run the tests on one git tree in a clean folder, as the git hook does. Returns (exit code, summary).

    The tests use this checkout's Python and packages, so a change to the dependencies is not covered.
    They run with `trial_env`. Only pytest's last line is returned, which holds counts only.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "tree"
        env = trial_env(os.environ)
        index_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        index_env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
        for args in (["read-tree", tree], ["checkout-index", "-a", f"--prefix={work.as_posix()}/"]):
            result = subprocess.run(["git", *args], cwd=repo, env=index_env, capture_output=True)
            if result.returncode != 0:
                raise GhError(f"git {args[0]} failed (exit {result.returncode})")
        result = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"],
                                cwd=work, env=env, capture_output=True, text=True, errors="replace")
        return result.returncode, _summary(result.stdout)


def trial_merge(repo, base, heads, run_tests=None):
    """The branches merged together onto `base` merge cleanly and pass the tests."""
    run_tests = run_tests or (lambda tree: run_tests_on_tree(repo, tree))
    order = ", ".join(f"#{n}" for n, _ in heads)
    conflict, tree = merged_tree(repo, base, heads)
    if conflict is not None:
        return Check(None, "tests on the merge", FAIL,
                     f"#{conflict} does not merge cleanly onto {_short(base)} after the ones before it")
    code, summary = run_tests(tree)
    if code != 0:
        return Check(None, "tests on the merge", FAIL, f"{order} onto {_short(base)}: {summary}")
    return Check(None, "tests on the merge", PASS, f"{order} onto {_short(base)}: {summary}")


def _fetch_commit(repo, ref):
    result = _git(repo, "fetch", "--quiet", "--no-tags", "origin", ref)
    if result.returncode != 0:
        raise GhError(f"git fetch of {ref} failed (exit {result.returncode})")
    return _git_out(repo, "rev-parse", "FETCH_HEAD")


def refuse_forks(prs):
    """A FAIL for any pull request from a fork, or with no fork flag, or None when there is none.

    The trial merge runs a branch's tests on this machine, so it is for this repo's own branches only.
    """
    forks = [pr["number"] for pr in prs if pr.get("isCrossRepository") is not False]
    if not forks:
        return None
    listed = ", ".join(f"#{n}" for n in forks)
    return Check(None, "tests on the merge", FAIL,
                 f"refused, not run: {listed} may come from a fork (head repository is not this repository, "
                 "or unknown). The trial merge runs only this repo's own branches")


def fetch_and_trial_merge(prs, repo=None):
    """Fetch the base and each pull request head, then run the trial merge. `prs` is in merge order.

    A fork is refused before anything is fetched.
    """
    refused = refuse_forks(prs)
    if refused is not None:
        return refused
    repo = Path.cwd() if repo is None else Path(repo)
    base =_fetch_commit(repo, f"refs/heads/{prs[0]['baseRefName']}")
    heads = []
    for pr in prs:
        oid = _fetch_commit(repo, f"refs/pull/{pr['number']}/head")
        if oid != pr["headRefOid"]:
            raise GhError(f"#{pr['number']} moved while the script ran. Run it again")
        heads.append((pr["number"], oid))
    return trial_merge(repo, base, heads)


# The gh layer. Read-only calls only: `gh pr view` and GET requests through `gh api`.


def find_gh():
    found = shutil.which("gh")
    if found:
        return found
    if GH_WINDOWS.exists():
        return str(GH_WINDOWS)
    raise GhError("gh is not on the PATH")


def run_gh(args):
    result = subprocess.run([find_gh(), *args], capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    if result.returncode != 0:
        raise GhError(f"gh {' '.join(args[:2])} failed (exit {result.returncode})")
    return result.stdout


def fetch_pr(number, gh=run_gh):
    """The `gh pr view` JSON, with each commit's files and parent count added."""
    pr = json.loads(gh(["pr", "view", str(number), "--json", PR_FIELDS]))
    for commit in pr["commits"]:
        detail = json.loads(gh(["api", f"repos/{{owner}}/{{repo}}/commits/{commit['oid']}",
                                "--jq", "{parents: (.parents | length), files: [.files[].filename]}"]))
        commit["files"], commit["parents"] = detail["files"], detail["parents"]
    return pr


def main(argv=None, fetch=fetch_pr, trial=fetch_and_trial_merge):
    parser = argparse.ArgumentParser(prog="merge_verdict",
                                     description="Run the mechanical merge checks on one or more pull requests")
    parser.add_argument("numbers", nargs="+", type=int, help="the pull request numbers")
    parser.add_argument("--test-merge", action="store_true",
                        help="also merge the heads onto the latest base and run the tests there (slow)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    numbers = sorted(set(args.numbers))
    try:
        prs = [fetch(n) for n in numbers]
        order = merge_order(prs)
        merged = None
        if args.test_merge:
            by_number = {pr["number"]: pr for pr in prs}
            ordered = [by_number[n] for n in order]
            merged = refuse_forks(ordered) or trial(ordered)
        checks = check_all(prs, merged)
        report = format_report(checks, order)
    except GhError as err:
        print(f"error: {err}")
        return EXIT_ERROR
    # The type only, never the message, which could hold data from GitHub.
    except Exception as err:
        print(f"error: {type(err).__name__}")
        return EXIT_ERROR
    print(report)
    return exit_code(checks)


if __name__ == "__main__":
    sys.exit(main())
