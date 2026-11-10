# Databricks notebook source
# Spec 004, J11: Job B's packages first. Databricks' serverless Python has older scikit-learn, numpy and scipy, and
# no anthropic, so this cell installs the locked versions, checked by their hashes, and restarts Python before any
# code of the repo is imported (pull request 6b). It prints nothing, and refuses with fixed text.
import os
import subprocess
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
installed = subprocess.run([sys.executable, "-m", "pip", "install", "--require-hashes", "--no-deps",
                            "--only-binary=:all:", "-q", "-r", str(root / "cloud" / "job_b" / "requirements.txt")],
                           capture_output=True)
if installed.returncode != 0:
    raise RuntimeError("Job B could not install its locked packages")
dbutils.library.restartPython()  # noqa: F821, the notebook's own global

# COMMAND ----------

# Spec 004, J11 and J16: Job B's one task. It reads its two run IDs and its own run ID, makes every check of
# src/voc/job_b.py before it marks anything used, labels the sample with the API through the June ledger
# (6b, part 3b), writes the dry run's note, and returns the contract's exit value. It prints nothing (J5).
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from databricks.sdk import WorkspaceClient  # noqa: E402

from voc.backends import make_backend  # noqa: E402
from voc.job_b import SECRET_SCOPE, PublicGitHub, VolumeStore, WorkspaceJobs, run  # noqa: E402
from voc.job_a import runner  # noqa: E402

# The notebook's own sign-in, as the owner, who runs Job B (J11).
client = WorkspaceClient()
values = {"job_a_run_id": dbutils.widgets.get("job_a_run_id"),  # noqa: F821, the notebook's own global
          "github_run_id": dbutils.widgets.get("github_run_id"),  # noqa: F821
          "job_b_run_id": dbutils.widgets.get("job_b_run_id")}  # noqa: F821
# Spark's errors could quote a row, so the sample is read through Job A's wrapper, which refuses with fixed text.
# Spec 004, J12 and 6b part 3b: the cloud workspace's API key and its ID, from the secret scope, never printed.
# Every answer's workspace header must name that workspace.
backend = make_backend("api", env={"ANTHROPIC_API_KEY": dbutils.secrets.get(SECRET_SCOPE, "anthropic-api-key")},  # noqa: F821
                       workspace=dbutils.secrets.get(SECRET_SCOPE, "anthropic-workspace-id"))  # noqa: F821
exit_value = run(root, values, WorkspaceJobs(client.api_client), PublicGitHub(), VolumeStore(client.files),
                 runner(spark), backend=backend)  # noqa: F821, the notebook's own global
dbutils.notebook.exit(exit_value)  # noqa: F821
