"""Test gate (CLAUDE.md, "Hooks").

Two modes:

- Claude hook (PreToolUse on Bash and PowerShell, event JSON on stdin).
  It blocks ways around the git hook (`--no-verify`, `-n`, changing
  `core.hooksPath`) and refuses a commit while the git hook is not installed.
- Git pre-commit hook (`--git-pre-commit`, run by `.githooks/pre-commit`).
  It runs gitleaks on the staged changes, the names check on the staged
  files, and the tests on the staged tree. Git builds that tree for every
  commit form (`-a`, `git commit <path>`, PowerShell or not), so the tests
  run on exactly what will be committed.

A commit that changes only `tests/test_*.py` files may have failing tests,
as long as every failing test is new or was already failing before it. It
may not delete a test, or make an existing passing test skip or fail. Each
already failing test it carries over is printed as a notice.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HOOKS_PATH = ".githooks"
TESTS_ONLY = re.compile(r"^tests/test_[^/]+\.py$")
SEGMENTS = re.compile(r"&&|\|\||[;|&\n]")
COMMIT = re.compile(r"\bgit\b(?:\s+(?:-C\s+\S+|-c\s+\S+|--?[\w-]+(?:=\S+)?))*\s+commit\b")
# Short options of `git commit` that take a value, so letters after them are the value.
VALUE_OPTIONS = set("mFCctSu")


# Claude hook


def _tokens(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _is_git_commit(segment):
    """Token check, for forms the regex misses, such as `git -C "my dir" commit`."""
    tokens = _tokens(segment)
    return "git" in tokens and "commit" in tokens[tokens.index("git") + 1:]


def _skips_hooks(segment):
    tokens = _tokens(segment)
    if "commit" not in tokens:
        return False
    after = tokens[tokens.index("commit") + 1:]
    skip_value = False
    for token in after:
        if skip_value:
            skip_value = False
            continue
        if token == "--":
            break
        if token.startswith("-") and not token.startswith("--"):
            for i, letter in enumerate(token[1:]):
                if letter == "n":
                    return True
                if letter in VALUE_OPTIONS:
                    skip_value = i == len(token) - 2  # the value is the next token
                    break
    return False


def _installed(hooks_path, roots):
    """The hook setting is `.githooks`, or the full path to `.githooks` in this checkout or the main one.

    Claude Code's worktree feature was seen to replace `.githooks` with its full path.
    """
    value = (hooks_path or "").strip().rstrip("/\\")
    if value == HOOKS_PATH:
        return True
    if not value or not Path(value).is_absolute():
        return False
    target = os.path.normcase(os.path.normpath(value))
    return any(target == os.path.normcase(os.path.normpath(Path(root) / HOOKS_PATH)) for root in roots)


def decide(tool_name, tool_input, hooks_path, roots=()):
    command = tool_input.get("command") or ""
    lower = command.lower()
    # `--no-v` also catches the short forms git accepts, such as `--no-veri`.
    if "--no-v" in lower or "hookspath" in lower:
        return ("deny", "test gate: skipping or changing the git hooks is not allowed for Claude.")
    commits = [s for s in SEGMENTS.split(command) if COMMIT.search(s) or _is_git_commit(s)]
    if not commits:
        return None
    if any(_skips_hooks(s) for s in commits):
        return ("deny", "test gate: `git commit -n` skips the git hook and is not allowed.")
    if not _installed(hooks_path, roots):
        return ("deny", "test gate: the git hook is not installed. The owner runs, once per clone: "
                        f"git config core.hooksPath {HOOKS_PATH}")
    return None


# Git pre-commit hook


def _git(repo, *args, data=None):
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, input=data)
    return result.stdout


def _head_tree(repo):
    result = subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD^{tree}"], cwd=repo, capture_output=True)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def _staged_changes(repo, head):
    if head is None:
        names = _git(repo, "ls-files", "-z").decode("utf-8").split("\0")
        return [("A", n) for n in names if n]
    out = _git(repo, "diff", "--cached", "--name-status", "--no-renames", "-z", "HEAD").decode("utf-8")
    parts = [p for p in out.split("\0") if p]
    return list(zip(parts[0::2], parts[1::2]))


def _outcomes(report):
    """Test id to "passed", "failed" or "skipped", from a JUnit XML report."""
    outcomes = {}
    if not report.is_file():
        return outcomes
    for case in ET.parse(report).getroot().iter("testcase"):
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("failure") is not None or case.find("error") is not None:
            outcomes[test_id] = "failed"
        elif case.find("skipped") is not None:
            outcomes[test_id] = "skipped"
        else:
            outcomes[test_id] = "passed"
    return outcomes


def _run_tests(repo, tree):
    """Run the tests on one git tree in a clean folder. Returns (exit code, outcomes)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work, report = Path(tmp) / "tree", Path(tmp) / "report.xml"
        # A temporary index and checkout-index, not `git archive`, which would
        # leave out files marked `export-ignore` in `.gitattributes`.
        index_env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        subprocess.run(["git", "read-tree", tree], cwd=repo, env=index_env, check=True, capture_output=True)
        subprocess.run(["git", "checkout-index", "-a", f"--prefix={work.as_posix()}/"],
                       cwd=repo, env=index_env, check=True, capture_output=True)
        # Git sets GIT_DIR, GIT_INDEX_FILE and others for hooks. Tests that run
        # git in their own folders must not see them.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
             "--continue-on-collection-errors", f"--junitxml={report}"],
            cwd=work, env=env, capture_output=True)
        return result.returncode, _outcomes(report)


def _test_problems(repo):
    head = _head_tree(repo)
    changes = _staged_changes(repo, head)
    tests_only = bool(changes) and all(TESTS_ONLY.match(path) for _, path in changes)
    code, new = _run_tests(repo, _git(repo, "write-tree").decode().strip())
    failed = sorted(t for t, outcome in new.items() if outcome == "failed")

    if not tests_only:
        if failed:
            return [f"failing test: {t}" for t in failed]
        if code != 0:
            return [f"the tests did not run cleanly (pytest exit code {code})"]
        return []

    problems = [f"tests-only commit deletes a test file: {path}" for status, path in changes if status == "D"]
    old = _run_tests(repo, head)[1] if head else {}
    for test_id, outcome in sorted(old.items()):
        if test_id not in new:
            problems.append(f"tests-only commit removes a test: {test_id}")
        elif new[test_id] == "skipped" and outcome != "skipped":
            problems.append(f"tests-only commit makes an existing test skip: {test_id}")
        elif outcome == "passed" and new[test_id] != "passed":
            problems.append(f"tests-only commit stops an existing test passing: {test_id}")
        elif outcome != "failed" and new[test_id] == "failed":
            problems.append(f"failing test is not new: {test_id}")
        elif outcome == "failed" and new[test_id] == "failed":
            # Allowed by owner decision (two red commits in a row), but never silent.
            print(f"pre-commit: notice: carried-over failing test: {test_id}")
    if code not in (0, 1):
        problems.append(f"the tests did not run cleanly (pytest exit code {code})")
    return problems


def _staged_name_hits(repo, names):
    sys.path.insert(0, str(Path(repo) / "src"))
    from voc.repo_checks import find_name_matches, place_for, texts_in_blob

    paths = [p for p in _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
             .decode("utf-8").split("\0") if p]
    sources = []
    for i, path in enumerate(paths, start=1):
        place = place_for(path, i, names)
        sources.append((place, path))
        texts = texts_in_blob(path, _git(repo, "show", f":{path}"))
        if texts is None:
            sources.append((place, ""))
            continue
        sources.extend((place, text) for _, text in texts)
    return [f"name from the deny list in {place}:{line}" for place, line in find_name_matches(sources, names)]


def check_staged(repo, names=None):
    """Problems with the staged commit. Names are never printed, only places."""
    problems = _staged_name_hits(repo, names) if names else []
    return problems + _test_problems(repo)


def git_pre_commit(repo, env):
    gitleaks = shutil.which("gitleaks", path=env.get("PATH"))
    if not gitleaks:
        print("pre-commit: gitleaks is not installed, so the commit is blocked.")
        return 1
    scan = subprocess.run([gitleaks, "git", "--pre-commit", "--redact", "--staged", "--no-banner", "."],
                          cwd=repo, env=env)
    if scan.returncode != 0:
        print("pre-commit: gitleaks reported a possible secret, so the commit is blocked.")
        return 1
    sys.path.insert(0, str(Path(repo) / "src"))
    from voc.repo_checks import DENY_LIST_FILE, DenyListMissing, load_deny_list
    try:
        names = load_deny_list(env, Path(repo) / DENY_LIST_FILE)
    except DenyListMissing as err:
        print(f"pre-commit: {err}, so the commit is blocked.")
        return 1
    problems = check_staged(repo, names)
    for problem in problems:
        print(f"pre-commit: {problem}")
    return 1 if problems else 0


# Entry point


def _git_out(cwd, *args):
    """A git command's output, decoded as UTF-8 (never the Windows code page), or None."""
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    return result.stdout.strip() or None if result.returncode == 0 else None


def _hooks_path(cwd):
    return _git_out(cwd, "config", "--get", "core.hooksPath")


def _repo_roots(cwd):
    """This checkout's top folder, and the main checkout's, kept only if their `.githooks/pre-commit` exists.

    The main checkout is the folder holding the shared `.git`. A bare repository has none, so it adds nothing.
    """
    roots = []
    top = _git_out(cwd, "rev-parse", "--show-toplevel")
    if top:
        roots.append(Path(top))
    common = _git_out(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and Path(common).name == ".git":
        roots.append(Path(common).parent)
    return tuple(r for r in roots if (r / HOOKS_PATH / "pre-commit").is_file())


def _emit(decision):
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision[0],
            "permissionDecisionReason": decision[1],
        }}))


def main(argv):
    if argv == ["--git-pre-commit"]:
        return git_pre_commit(Path.cwd(), os.environ)
    try:
        # Claude Code sends UTF-8. Read bytes, so the system code page (cp932 here) never decodes it.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        cwd = event.get("cwd") or "."
        decision = decide(event.get("tool_name"), event.get("tool_input") or {},
                          hooks_path=_hooks_path(cwd), roots=_repo_roots(cwd))
    except Exception as err:  # fail closed
        print(f"test gate hook failed: {type(err).__name__}", file=sys.stderr)
        return 2
    _emit(decision)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
