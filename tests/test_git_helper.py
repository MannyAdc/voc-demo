"""The test helper that runs git in a test's own scratch repo (BUILD_LOG.md, 2 and 3 November).

Now and then Windows refuses git access to a file it is writing in a scratch repo, with "Permission denied",
though nothing else runs, and the gate refuses a good commit. The helper retries only that error. These tests
use a fake `subprocess.run`, so no git runs here.
"""
import subprocess

import pytest


class FakeRun:
    """Returns the given results in turn and counts the calls."""

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return self.results.pop(0)


def _done(code, stderr=b""):
    return subprocess.CompletedProcess(["git"], code, stdout=b"", stderr=stderr)


LOCK = b"error: unable to write file .git/objects/02/ab: Permission denied\nfatal: failed to write commit object\n"


def test_a_git_step_refused_by_a_passing_file_lock_is_tried_again(monkeypatch):
    import git_helper
    fake = FakeRun(_done(128, LOCK), _done(0))
    monkeypatch.setattr(git_helper.subprocess, "run", fake)
    monkeypatch.setattr(git_helper.time, "sleep", lambda seconds: None)
    assert git_helper.run(["git", "commit", "-m", "x"]).returncode == 0
    assert len(fake.calls) == 2


def test_any_other_failure_is_returned_at_once_so_an_expected_refusal_stays_a_refusal(monkeypatch):
    import git_helper
    fake = FakeRun(_done(1, b"pre-commit: failing test: tests.test_x::test_y\n"))
    monkeypatch.setattr(git_helper.subprocess, "run", fake)
    assert git_helper.run(["git", "commit", "-m", "x"]).returncode == 1
    assert len(fake.calls) == 1


def test_a_lock_that_does_not_pass_gives_up_after_three_tries(monkeypatch):
    import git_helper
    fake = FakeRun(_done(128, LOCK), _done(128, LOCK), _done(128, LOCK), _done(0))
    monkeypatch.setattr(git_helper.subprocess, "run", fake)
    monkeypatch.setattr(git_helper.time, "sleep", lambda seconds: None)
    assert git_helper.run(["git", "add", "."]).returncode == 128
    assert len(fake.calls) == 3


def test_check_raises_after_the_last_try_as_subprocess_does(monkeypatch):
    import git_helper
    fake = FakeRun(_done(128, LOCK), _done(128, LOCK), _done(128, LOCK))
    monkeypatch.setattr(git_helper.subprocess, "run", fake)
    monkeypatch.setattr(git_helper.time, "sleep", lambda seconds: None)
    with pytest.raises(subprocess.CalledProcessError):
        git_helper.run(["git", "add", "."], check=True)


def test_text_output_is_read_too_and_the_caller_options_are_passed_on(monkeypatch):
    import git_helper
    fake = FakeRun(subprocess.CompletedProcess(["git"], 128, stdout="", stderr=LOCK.decode()),
                   subprocess.CompletedProcess(["git"], 0, stdout="ok", stderr=""))
    monkeypatch.setattr(git_helper.subprocess, "run", fake)
    monkeypatch.setattr(git_helper.time, "sleep", lambda seconds: None)
    result = git_helper.run(["git", "status"], cwd="repo", text=True, env={"A": "1"})
    assert result.stdout == "ok"
    assert all(kwargs["cwd"] == "repo" and kwargs["env"] == {"A": "1"} for _, kwargs in fake.calls)
