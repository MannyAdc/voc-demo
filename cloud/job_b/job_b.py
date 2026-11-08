# Databricks notebook source
# Spec 004, J11 and J16: Job B's one task, as the dry run of pull request 6a. It reads its two run IDs and its own
# run ID, makes every check of src/voc/job_b.py before it marks anything used, labels the synthetic sample with the
# mock backend, writes the dry run's note, and returns the contract's exit value. It prints nothing else (J5).
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from databricks.sdk import WorkspaceClient  # noqa: E402

from voc.job_b import PublicGitHub, VolumeStore, WorkspaceJobs, run  # noqa: E402
from voc.job_a import runner  # noqa: E402

# The notebook's own sign-in, as the owner, who runs Job B (J11).
client = WorkspaceClient()
values = {"job_a_run_id": dbutils.widgets.get("job_a_run_id"),  # noqa: F821, the notebook's own global
          "github_run_id": dbutils.widgets.get("github_run_id"),  # noqa: F821
          "job_b_run_id": dbutils.widgets.get("job_b_run_id")}  # noqa: F821
# Spark's errors could quote a row, so the sample is read through Job A's wrapper, which refuses with fixed text.
exit_value = run(root, values, WorkspaceJobs(client.api_client), PublicGitHub(), VolumeStore(client.files),
                 runner(spark))  # noqa: F821, the notebook's own global
dbutils.notebook.exit(exit_value)  # noqa: F821
