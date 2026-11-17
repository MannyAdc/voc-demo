"""CLAUDE.md, "Build log": append to BUILD_LOG.md, and never invent or tidy an entry.

CI checks that BUILD_LOG.md only grows compared with `main`, with the same script as the run logs
(`scripts/check_test_runs.py`). A correction to a merged line is a new line, never an edit of the old one.
On 17 November a find-and-replace that was not limited to one line changed the ending of old log lines on a
branch, 48 of them restored in all, one of them a line on `main` (BUILD_LOG.md, "Pull request: stale rules files"),
and only a manual check caught it. These tests have no rule ID: the rule is CLAUDE.md's, which has none.
"""
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def _check(tmp_path, old, new):
    base, head = tmp_path / "base.md", tmp_path / "BUILD_LOG.md"
    base.write_text(old, encoding="utf-8")
    head.write_text(new, encoding="utf-8")
    return subprocess.run([sys.executable, str(REPO / "scripts" / "check_test_runs.py"), str(base), str(head)],
                          capture_output=True, text=True).returncode


def test_build_log_check_passes_when_lines_are_only_added_at_the_end(tmp_path):
    old = "# Build log\n\n- 10:00 Work start.\n"
    assert _check(tmp_path, old, old + "- 10:05 A correction to the line above, as a new line.\n") == 0


def test_build_log_check_fails_when_an_old_line_s_ending_is_changed(tmp_path):
    old = "- 10:00 Change written. Claude ran the whole suite first.\n- 10:10 Commit.\n"
    new = "- 10:00 Change written. Claude ran the whole suite first: exit code 0.\n- 10:10 Commit.\n"
    assert _check(tmp_path, old, new) == 1


def test_build_log_check_fails_when_an_old_line_is_removed(tmp_path):
    assert _check(tmp_path, "- a\n- b\n", "- a\n") == 1


def test_build_log_ci_checks_that_the_build_log_only_grows_compared_with_main():
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    # In the job the ruleset requires, so a failure blocks the merge (BUILD_LOG.md, 1 November).
    runs = [step.get("run", "") for step in workflow["jobs"]["repo-checks"]["steps"]]
    assert any("scripts/check_test_runs.py" in run and '"$base" BUILD_LOG.md' in run
               and 'git show origin/main:BUILD_LOG.md > "$base"' in run
               and "git rev-parse --verify origin/main" in run
               for run in runs)


def test_build_log_ci_step_cannot_swallow_a_failure():
    # Second review of #153, nit 2: a skipped step or a swallowed exit code would turn the check off unseen.
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["repo-checks"]
    steps = [step for step in job["steps"] if '"$base" BUILD_LOG.md' in step.get("run", "")]
    assert len(steps) == 1
    step = steps[0]
    assert "if" not in step and "continue-on-error" not in step and "continue-on-error" not in job
    assert "|| true" not in step["run"] and "|| :" not in step["run"] and "set +e" not in step["run"]
