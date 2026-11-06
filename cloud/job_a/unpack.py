# Databricks notebook source
# Spec 004, J8: Job A's first task. It checks the run log's last row and that this is its frozen code, then the one
# zip in the incoming folder against the pin of the run's kind. It writes the pinned CSV, checks its shape, and
# hands dbt its variables. It prints nothing (J5).
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.job_a import INCOMING, JUNE_FOLDER, checked_target, pin_for, unpack  # noqa: E402

# Review of #94, minor 5: this task and dbt's handle the June file, so the code is checked here first.
run_target = checked_target(root)
values = unpack(INCOMING, JUNE_FOLDER, pin_for(root, run_target.kind), root / "config" / "labels.toml")
for key, value in values.items():
    dbutils.jobs.taskValues.set(key=key, value=value)  # noqa: F821, the notebook's own global
