"""T006b: the merge verdict script checks a pull request before it is marked ready.

Every test feeds the checks synthetic pull request data, shaped like the JSON that
`gh pr view` returns. No test runs `gh` or opens the network. The trial merge tests
build a small git repo in a temporary folder.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
SYN_HEADLINE = "SYN headline that must never be printed"
SYN_FINDING = "SYN finding sentence that must never be printed"


@pytest.fixture
def mv():
    import voc.merge_verdict as module
    return module


def _run(name, conclusion="SUCCESS", status="COMPLETED"):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion,
            "workflowName": "CI"}


def _commit(oid, files, date, parents=1):
    return {"oid": oid, "messageHeadline": SYN_HEADLINE, "messageBody": "", "committedDate": date,
            "authoredDate": date, "authors": [], "files": files, "parents": parents}


def _comment(body, date):
    return {"body": body, "createdAt": date, "author": {"login": "syn-owner"}}


def _pr(number=101, **over):
    pr = {
        "number": number, "state": "OPEN", "isDraft": True, "mergeable": "MERGEABLE", "isCrossRepository": False,
        "baseRefName": "main", "headRefName": f"feat/syn-{number}", "headRefOid": f"{number:a<40}",
        "statusCheckRollup": [_run(n) for n in ("tests", "repo-checks", "secret-scan")] * 2,
        "commits": [
            _commit("1" * 40, ["tests/test_syn.py"], "2026-10-29T01:00:00Z"),
            _commit("2" * 40, ["src/voc/syn.py"], "2026-10-29T01:10:00Z"),
            _commit("3" * 40, ["src/voc/syn.py", "tests/test_syn.py"], "2026-10-29T02:00:00Z"),
        ],
        "files": [{"path": "tests/test_syn.py"}, {"path": f"src/voc/syn_{number}.py"}],
        "comments": [_comment(f"## Reviewer findings (fresh agent)\n\n1. {SYN_FINDING}.", "2026-10-29T01:30:00Z")],
    }
    pr.update(over)
    return pr


# CI is green


def test_T006b_ci_green_when_every_expected_check_succeeded(mv):
    check = mv.check_ci(_pr())
    assert check.status == mv.PASS
    assert "101aaaa" in check.detail  # the short head commit


def test_T006b_ci_fails_when_a_check_failed(mv):
    rollup = [_run("tests", "FAILURE"), _run("repo-checks"), _run("secret-scan")]
    check = mv.check_ci(_pr(statusCheckRollup=rollup))
    assert check.status == mv.FAIL
    assert "tests" in check.detail


def test_T006b_ci_fails_while_a_check_is_still_running(mv):
    rollup = [_run("tests", None, "IN_PROGRESS"), _run("repo-checks"), _run("secret-scan")]
    check = mv.check_ci(_pr(statusCheckRollup=rollup))
    assert check.status == mv.FAIL
    assert "running" in check.detail


def test_T006b_ci_fails_on_a_pending_commit_status(mv):
    rollup = [_run(n) for n in mv.EXPECTED_CHECKS]
    rollup.append({"__typename": "StatusContext", "context": "syn-status", "state": "PENDING"})
    check = mv.check_ci(_pr(statusCheckRollup=rollup))
    assert check.status == mv.FAIL
    assert "syn-status" in check.detail


@pytest.mark.parametrize("status", ["QUEUED", "IN_PROGRESS", "WAITING", "PENDING", None])
def test_T006b_ci_fails_on_a_check_run_not_completed(mv, status):
    rollup = [_run("tests", None, status), _run("repo-checks"), _run("secret-scan")]
    check = mv.check_ci(_pr(statusCheckRollup=rollup))
    assert check.status == mv.FAIL
    assert "tests" in check.detail


def test_T006b_ci_fails_with_no_checks(mv):
    assert mv.check_ci(_pr(statusCheckRollup=[])).status == mv.FAIL


def test_T006b_ci_fails_when_an_expected_check_is_missing(mv):
    check = mv.check_ci(_pr(statusCheckRollup=[_run("tests"), _run("repo-checks")]))
    assert check.status == mv.FAIL
    assert "secret-scan" in check.detail


def test_T006b_ci_fails_on_a_skipped_check(mv):
    rollup = [_run("tests", "SKIPPED"), _run("repo-checks"), _run("secret-scan")]
    assert mv.check_ci(_pr(statusCheckRollup=rollup)).status == mv.FAIL


def test_T006b_ci_fails_on_a_failed_commit_status(mv):
    rollup = [_run(n) for n in mv.EXPECTED_CHECKS]
    rollup.append({"__typename": "StatusContext", "context": "syn-status", "state": "FAILURE"})
    check = mv.check_ci(_pr(statusCheckRollup=rollup))
    assert check.status == mv.FAIL
    assert "syn-status" in check.detail


def test_T006b_expected_checks_match_the_ci_jobs(mv):
    text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    jobs = text.split("\njobs:\n", 1)[1]
    names = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", jobs, flags=re.M)
    assert sorted(names) == sorted(mv.EXPECTED_CHECKS)


# The red commit came before the code


def test_T006b_red_commit_before_code_passes(mv):
    check = mv.check_red_first(_pr())
    assert check.status == mv.PASS
    assert "1111111" in check.detail and "2222222" in check.detail


def test_T006b_code_before_the_red_commit_fails(mv):
    commits = [_commit("2" * 40, ["src/voc/syn.py"], "2026-10-29T01:00:00Z"),
               _commit("1" * 40, ["tests/test_syn.py"], "2026-10-29T01:10:00Z")]
    check = mv.check_red_first(_pr(commits=commits))
    assert check.status == mv.FAIL
    assert "2222222" in check.detail


def test_T006b_no_tests_only_commit_fails(mv):
    commits = [_commit("2" * 40, ["src/voc/syn.py", "tests/test_syn.py"], "2026-10-29T01:00:00Z")]
    assert mv.check_red_first(_pr(commits=commits)).status == mv.FAIL


@pytest.mark.parametrize("extra", ["tests/conftest.py", "tests/fixtures/syn.csv", "README.md"])
def test_T006b_red_commit_holds_only_test_files(mv, extra):
    commits = [_commit("1" * 40, ["tests/test_syn.py", extra], "2026-10-29T01:00:00Z"),
               _commit("2" * 40, ["src/voc/syn.py"], "2026-10-29T01:10:00Z")]
    assert mv.check_red_first(_pr(commits=commits)).status == mv.FAIL


def test_T006b_no_code_change_needs_no_red_commit(mv):
    commits = [_commit("4" * 40, ["BUILD_LOG.md", "results/eval/v1_dev.csv", "docs/DATA.md"],
                       "2026-10-29T01:00:00Z")]
    check = mv.check_red_first(_pr(commits=commits))
    assert check.status == mv.PASS
    assert "no code" in check.detail


def test_T006b_merge_commits_are_left_out_of_the_order(mv):
    commits = [_commit("5" * 40, ["src/voc/other.py"], "2026-10-29T00:50:00Z", parents=2),
               _commit("1" * 40, ["tests/test_syn.py"], "2026-10-29T01:00:00Z"),
               _commit("2" * 40, ["src/voc/syn.py"], "2026-10-29T01:10:00Z")]
    assert mv.check_red_first(_pr(commits=commits)).status == mv.PASS


@pytest.mark.parametrize("path, code", [
    ("src/voc/syn.py", True),
    ("scripts/syn.py", True),
    (".githooks/pre-commit", True),
    (".claude/hooks/run.sh", True),
    (".claude/settings.json", True),
    (".github/workflows/ci.yml", True),
    ("dbt/models/syn.sql", True),
    ("dbt/models/schema.yml", True),
    ("pyproject.toml", True),
    ("uv.lock", True),
    ("tests/test_syn.py", False),
    ("tests/conftest.py", False),
    ("BUILD_LOG.md", False),
    ("docs/DATA.md", False),
    ("results/eval/v1_dev.csv", False),
    ("config/labels.toml", False),
])
def test_T006b_code_files_are_told_apart(mv, path, code):
    assert mv.is_code_file(path) is code


@pytest.mark.parametrize("path, red", [
    ("tests/test_syn.py", True),
    ("tests/conftest.py", False),
    ("tests/fixtures/test_syn.py", False),
    ("src/voc/test_syn.py", False),
])
def test_T006b_red_files_are_top_level_test_files(mv, path, red):
    assert mv.is_red_file(path) is red


# Every review finding is fixed or deferred


def test_T006b_missing_reviewer_findings_fails(mv):
    check = mv.check_review(_pr(comments=[_comment("Synthetic note.", "2026-10-29T01:30:00Z")]))
    assert check.status == mv.FAIL


def test_T006b_findings_heading_must_start_the_comment(mv):
    body = "Synthetic note.\n\n## Reviewer findings\n\n1. Something."
    assert mv.check_review(_pr(comments=[_comment(body, "2026-10-29T01:30:00Z")])).status == mv.FAIL


def test_T006b_findings_with_later_commits_are_for_claude(mv):
    check = mv.check_review(_pr())
    assert check.status == mv.CLAUDE
    assert "1 commit after" in check.detail


def test_T006b_findings_with_no_later_commit_are_for_claude(mv):
    check = mv.check_review(_pr(comments=[_comment("## Reviewer findings\n\n1. X.", "2026-10-29T03:00:00Z")]))
    assert check.status == mv.CLAUDE
    assert "no commit after" in check.detail


@pytest.mark.parametrize("body", [
    "## Reviewer findings\n\nNo findings.\n\n1. A real synthetic finding.",
    "## Reviewer findings\n\nNo findings. Nothing to fix.",
    "## Reviewer findings\n\nNothing to fix.",
    "## Reviewer findings\n\nNo fix needed.",
])
def test_T006b_review_is_never_a_pass(mv, body):
    check = mv.check_review(_pr(comments=[_comment(body, "2026-10-29T03:00:00Z")]))
    assert check.status == mv.CLAUDE


def test_T006b_latest_findings_comment_counts(mv):
    comments = [_comment("## Reviewer findings\n\n1. X.", "2026-10-29T01:05:00Z"),
                _comment("## Reviewer findings (second round)\n\n1. Y.", "2026-10-29T01:30:00Z")]
    check = mv.check_review(_pr(comments=comments))
    assert "1 commit after" in check.detail


def test_T006b_build_log_is_always_for_claude(mv):
    assert mv.check_build_log(_pr()).status == mv.CLAUDE


# The pull request itself


@pytest.mark.parametrize("over, status", [
    ({}, "PASS"),
    ({"state": "MERGED"}, "FAIL"),
    ({"state": "CLOSED"}, "FAIL"),
    ({"baseRefName": "syn-base"}, "FAIL"),
])
def test_T006b_pull_request_is_open_against_main(mv, over, status):
    assert mv.check_open(_pr(**over)).status == status


@pytest.mark.parametrize("mergeable, status", [
    ("MERGEABLE", "PASS"),
    ("CONFLICTING", "FAIL"),
    ("UNKNOWN", "FOR CLAUDE"),
])
def test_T006b_merge_conflicts_with_the_base(mv, mergeable, status):
    assert mv.check_conflicts(_pr(mergeable=mergeable)).status == status


# Parallel branches


def test_T006b_parallel_branches_with_no_shared_file_pass(mv):
    assert mv.check_shared_files([_pr(101), _pr(102, files=[{"path": "src/voc/other.py"}])]).status == mv.PASS


def test_T006b_parallel_branches_with_a_shared_file_fail(mv):
    check = mv.check_shared_files([_pr(101), _pr(102)])
    assert check.status == mv.FAIL
    assert "tests/test_syn.py" in check.detail


def test_T006b_merge_order_is_lowest_number_first(mv):
    assert mv.merge_order([_pr(103), _pr(101), _pr(102)]) == [101, 102, 103]


def test_T006b_parallel_branches_without_a_trial_merge_are_for_claude(mv):
    prs = [_pr(101), _pr(102, files=[{"path": "src/voc/other.py"}])]
    checks = mv.check_all(prs)
    merged = [c for c in checks if c.name == "tests on the merge"]
    assert len(merged) == 1 and merged[0].status == mv.CLAUDE


# The verdict


def test_T006b_verdict_merge_when_all_pass(mv):
    checks = [mv.Check(101, "CI", mv.PASS, "green")]
    assert mv.verdict(checks) == "MERGE"


def test_T006b_verdict_fix_first_names_the_reason(mv):
    checks = [mv.Check(101, "CI", mv.FAIL, "tests failed"), mv.Check(101, "review", mv.CLAUDE, "judge")]
    line = mv.verdict(checks)
    assert line.startswith("FIX FIRST: ")
    assert "#101" in line and "tests failed" in line
    assert "\n" not in line


def test_T006b_verdict_is_pending_while_claude_must_judge(mv):
    checks = [mv.Check(101, "CI", mv.PASS, "green"), mv.Check(101, "review findings", mv.CLAUDE, "judge"),
              mv.Check(101, "build log", mv.CLAUDE, "judge")]
    line = mv.verdict(checks)
    assert line.startswith("PENDING: Claude must judge: ")
    assert "#101 review findings" in line and "#101 build log" in line
    assert "MERGE" not in line
    assert "\n" not in line


def test_T006b_verdict_fix_first_wins_over_pending(mv):
    checks = [mv.Check(101, "CI", mv.FAIL, "tests failed"), mv.Check(101, "review findings", mv.CLAUDE, "judge")]
    assert mv.verdict(checks).startswith("FIX FIRST: ")


# The command


def _fake_fetch(prs):
    by_number = {pr["number"]: pr for pr in prs}

    def fetch(number):
        return by_number[number]
    return fetch


def test_T006b_main_prints_each_check_and_the_verdict_last(mv, capsys):
    code = mv.main(["101"], fetch=_fake_fetch([_pr(101)]))
    lines = capsys.readouterr().out.strip().splitlines()
    assert code == 3
    assert any(line.startswith("PASS") and "CI" in line for line in lines)
    assert any(line.startswith("FOR CLAUDE") for line in lines)
    assert lines[-1].startswith("PENDING: Claude must judge: ")


def test_T006b_main_exits_1_on_fix_first(mv, capsys):
    pr = _pr(101, statusCheckRollup=[_run("tests", "FAILURE"), _run("repo-checks"), _run("secret-scan")])
    assert mv.main(["101"], fetch=_fake_fetch([pr])) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("FIX FIRST: ")


def test_T006b_main_never_prints_commit_messages_or_comment_text(mv, capsys):
    mv.main(["101", "102"], fetch=_fake_fetch([_pr(101), _pr(102)]))
    out = capsys.readouterr().out
    assert SYN_HEADLINE not in out
    assert SYN_FINDING not in out


def test_T006b_main_prints_the_merge_order_for_parallel_branches(mv, capsys):
    prs = [_pr(102, files=[{"path": "src/voc/other.py"}]), _pr(101)]
    mv.main(["102", "101"], fetch=_fake_fetch(prs))
    assert "Merge order: #101, then #102" in capsys.readouterr().out


def test_T006b_main_runs_the_trial_merge_only_when_asked(mv, capsys):
    prs = [_pr(101), _pr(102, files=[{"path": "src/voc/other.py"}])]
    calls = []

    def trial(ordered):
        calls.append([pr["number"] for pr in ordered])
        return mv.Check(None, "tests on the merge", mv.PASS, "3 passed")

    mv.main(["102", "101"], fetch=_fake_fetch(prs), trial=trial)
    assert calls == []
    mv.main(["102", "101", "--test-merge"], fetch=_fake_fetch(prs), trial=trial)
    assert calls == [[101, 102]]
    assert "3 passed" in capsys.readouterr().out


def test_T006b_main_exits_2_when_the_data_cannot_be_read(mv, capsys):
    def fetch(number):
        raise mv.GhError("gh pr view failed (exit 1)")

    assert mv.main(["101"], fetch=fetch) == 2
    assert capsys.readouterr().out.startswith("error: ")


def test_T006b_main_exits_3_while_pending(mv, capsys):
    assert mv.main(["101"], fetch=_fake_fetch([_pr(101)])) == 3
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("PENDING: Claude must judge: ")


def test_T006b_main_exits_0_only_on_merge(mv, capsys, monkeypatch):
    monkeypatch.setattr(mv, "check_all", lambda prs, merged=None: [mv.Check(101, "CI", mv.PASS, "green")])
    assert mv.main(["101"], fetch=_fake_fetch([_pr(101)])) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "MERGE"


def test_T006b_main_crash_exits_2_with_the_error_type_only(mv, capsys):
    message = "SYN crash text " + "that must never be printed"

    def fetch(number):
        raise ValueError(message)

    assert mv.main(["101"], fetch=fetch) == 2
    out = capsys.readouterr().out
    assert out.strip() == "error: ValueError"
    assert message not in out


def test_T006b_main_refuses_the_trial_merge_for_a_fork(mv, capsys):
    prs = [_pr(101), _pr(102, files=[{"path": "src/voc/other.py"}], isCrossRepository=True)]
    calls = []

    def trial(ordered):
        calls.append(ordered)
        return mv.Check(None, "tests on the merge", mv.PASS, "3 passed")

    assert mv.main(["101", "102", "--test-merge"], fetch=_fake_fetch(prs), trial=trial) == 1
    out = capsys.readouterr().out
    assert calls == []
    assert any(line.startswith("FAIL") and "tests on the merge" in line and "#102" in line and "fork" in line
               for line in out.splitlines())


@pytest.mark.parametrize("over", [{"isCrossRepository": True}, {"isCrossRepository": None}])
def test_T006b_trial_merge_refuses_a_fork_before_any_fetch(mv, tmp_path, over):
    pr = _pr(101, **over)
    if over["isCrossRepository"] is None:
        del pr["isCrossRepository"]
    # tmp_path is not a git repo, so any fetch or git call would raise.
    check = mv.fetch_and_trial_merge([pr], repo=tmp_path)
    assert check.status == mv.FAIL
    assert "#101" in check.detail and "fork" in check.detail


def test_T006b_pr_fields_include_the_fork_flag(mv):
    assert "isCrossRepository" in mv.PR_FIELDS.split(",")


# The gh layer


def test_T006b_fetch_adds_each_commits_files_with_read_only_calls(mv):
    view = _pr(101)
    for commit in view["commits"]:
        del commit["files"], commit["parents"]
    calls = []

    def gh(args):
        calls.append(args)
        if args[:2] == ["pr", "view"]:
            return json.dumps(view)
        oid = args[1].rsplit("/", 1)[1]
        return json.dumps({"parents": 1, "files": [f"src/voc/{oid[:3]}.py"]})

    pr = mv.fetch_pr(101, gh=gh)
    assert [c["files"] for c in pr["commits"]] == [["src/voc/111.py"], ["src/voc/222.py"], ["src/voc/333.py"]]
    assert all(c["parents"] == 1 for c in pr["commits"])
    for args in calls:
        assert args[0] in ("pr", "api")
        if args[0] == "pr":
            assert args[1] == "view"
        else:
            assert not {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"} & set(args)


# The trial merge, on a small local repo


def _git(repo, *args):
    result = subprocess.run([*GIT, *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _branch(repo, base, name, files):
    _git(repo, "checkout", "-q", "-b", name, base)
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")
        _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def test_T006b_trial_merge_tests_the_branches_merged_together(mv, repo):
    base = _git(repo, "rev-parse", "HEAD")
    one = _branch(repo, base, "one", {"b.txt": "one\n"})
    two = _branch(repo, base, "two", {"c.txt": "two\n"})
    seen = []

    def run_tests(tree):
        seen.append(sorted(_git(repo, "ls-tree", "--name-only", tree).splitlines()))
        return 0, "3 passed in 0.1s"

    check = mv.trial_merge(repo, base, [(101, one), (102, two)], run_tests=run_tests)
    assert seen == [["a.txt", "b.txt", "c.txt"]]
    assert check.status == mv.PASS
    assert "3 passed" in check.detail


def test_T006b_trial_merge_conflict_fails_without_running_tests(mv, repo):
    base = _git(repo, "rev-parse", "HEAD")
    one = _branch(repo, base, "one", {"a.txt": "one\n"})
    two = _branch(repo, base, "two", {"a.txt": "two\n"})

    def run_tests(tree):
        raise AssertionError("tests must not run on a conflict")

    check = mv.trial_merge(repo, base, [(101, one), (102, two)], run_tests=run_tests)
    assert check.status == mv.FAIL
    assert "#102" in check.detail


def test_T006b_trial_merge_failing_tests_fail(mv, repo):
    base = _git(repo, "rev-parse", "HEAD")
    one = _branch(repo, base, "one", {"b.txt": "one\n"})
    check = mv.trial_merge(repo, base, [(101, one)], run_tests=lambda tree: (1, "1 failed, 2 passed in 0.1s"))
    assert check.status == mv.FAIL
    assert "1 failed" in check.detail


def test_T006b_trial_merge_runs_pytest_on_the_merged_tree(mv, repo):
    base = _git(repo, "rev-parse", "HEAD")
    one = _branch(repo, base, "one", {"tests/test_syn_ok.py": "def test_ok():\n    assert True\n"})
    two = _branch(repo, base, "two", {"tests/test_syn_two.py": "def test_two():\n    assert 1 + 1 == 2\n"})
    code, summary = mv.run_tests_on_tree(repo, mv.merged_tree(repo, base, [(101, one), (102, two)])[1])
    assert code == 0
    assert "2 passed" in summary


def _syn_env():
    # Names are built while the test runs. The values are plain synthetic words, not key-like.
    return {
        "PATH": "syn-path",
        "SYSTEMROOT": "syn-root",
        "ANTHROPIC_" + "API_KEY": "syn-value",
        "SYN_" + "KEY_FILE": "syn-value",
        "syn_lower_" + "key": "syn-value",
        "SYN_" + "TOKEN": "syn-value",
        "GH_" + "TOKEN": "syn-value",
        "SYN_" + "SECRET_VALUE": "syn-value",
        "VOC_DATA_DIR": "syn-folder",
        "VOC_NEXT_DATA_DIR": "syn-folder",
        "VOC_MOCK_FIXTURES": "syn-folder",
        "GIT_DIR": "syn-git",
        "LLM_BACKEND": "api",
    }


def test_T006b_trial_merge_env_drops_secrets_and_data_folders(mv):
    env = mv.trial_env(_syn_env())
    assert env == {"PATH": "syn-path", "SYSTEMROOT": "syn-root", "LLM_BACKEND": "mock"}


def test_T006b_trial_merge_tests_run_with_mock_and_no_secrets(mv, repo, monkeypatch):
    for name, value in _syn_env().items():
        if name not in ("PATH", "SYSTEMROOT", "GIT_DIR"):  # the test's own git calls need GIT_DIR unset
            monkeypatch.setenv(name, value)
    probe = (
        "import os\n\n"
        "def test_env():\n"
        "    assert os.environ.get('LLM_BACKEND') == 'mock'\n"
        "    names = [n.upper() for n in os.environ]\n"
        "    assert not [n for n in names if 'KEY' in n or 'TOKEN' in n or 'SECRET' in n]\n"
        "    assert not {'VOC_DATA_DIR', 'VOC_NEXT_DATA_DIR', 'VOC_MOCK_FIXTURES'} & set(names)\n"
    )
    base = _git(repo, "rev-parse", "HEAD")
    one = _branch(repo, base, "one", {"tests/test_syn_env.py": probe})
    code, summary = mv.run_tests_on_tree(repo, mv.merged_tree(repo, base, [(101, one)])[1])
    assert code == 0, summary
    assert "1 passed" in summary
