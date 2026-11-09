"""CI's own setup (T003): it runs once per change and retries its downloads.

On 8 and 9 November a CI run failed at a download from GitHub (a 504 for uv's Python, and the first download step of
each job), and the owner had to re-run it, since Claude never re-runs a workflow. Every push to a pull request also ran
CI twice, once for the push and once for the pull request, which doubled the chance of such a fault.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CI = REPO / ".github" / "workflows" / "ci.yml"


def _workflow():
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _triggers(flow):
    # YAML 1.1 reads the key "on" as True.
    return flow.get("on", flow.get(True))


def _runs(job):
    return [step.get("run", "") for step in _workflow()["jobs"][job]["steps"]]


def test_T003_ci_runs_on_every_pull_request_and_on_pushes_to_main_only():
    triggers = _triggers(_workflow())
    assert set(triggers) == {"pull_request", "push"}
    assert triggers["pull_request"] is None
    # The dashboard's deploy follows CI's push run on main (A15), so main keeps it.
    assert triggers["push"] == {"branches": ["main"]}


def test_T003_each_job_installs_python_and_the_project_with_retries_before_using_uv():
    for job in ("tests", "repo-checks"):
        runs = _runs(job)
        install = [i for i, run in enumerate(runs) if "uv sync --locked" in run]
        assert len(install) == 1, job
        step = runs[install[0]]
        assert "for attempt in 1 2 3" in step and "sleep" in step and "exit 1" in step, job
        # No later step may download Python or a package on its own first.
        first_use = min(i for i, run in enumerate(runs) if "uv run" in run or ".venv/bin/python" in run)
        assert install[0] < first_use, job


def test_T003_the_secret_scan_retries_its_download():
    curl = next(run for run in _runs("secret-scan") if "curl" in run)
    assert "--retry 3" in curl and "--retry-all-errors" in curl
    # The checksum still decides whether the download is used.
    assert "sha256sum -c -" in curl
