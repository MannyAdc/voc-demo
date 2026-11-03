"""Run git in a test's own scratch repo, with a retry for a passing Windows file lock.

Now and then Windows refuses git access to a file it is writing inside a scratch repo, with "Permission
denied", even when no other gate runs (BUILD_LOG.md, from 2 November). Git then writes nothing, and the test
gate refuses a good commit. Only that error is retried, twice, after a short wait. Any
other failure, such as a hook's expected refusal, is returned or raised at once, as `subprocess.run` does.
"""
import subprocess
import time

TRIES = 3
WAIT_SECONDS = 0.5
LOCKED = "Permission denied"


def _text(output):
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def run(args, check=False, **kwargs):
    """`subprocess.run(args, ...)` for git, tried again only when git reports a file lock."""
    if "stderr" not in kwargs and not kwargs.get("capture_output"):
        # The error text is needed to tell a lock from a real failure. A caller's own stdout is kept.
        if "stdout" in kwargs:
            kwargs["stderr"] = subprocess.PIPE
        else:
            kwargs["capture_output"] = True
    for attempt in range(1, TRIES + 1):
        result = subprocess.run(args, **kwargs)
        if result.returncode == 0 or LOCKED not in _text(result.stderr) or attempt == TRIES:
            break
        time.sleep(WAIT_SECONDS)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    return result
