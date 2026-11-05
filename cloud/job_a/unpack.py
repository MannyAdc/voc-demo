# Databricks notebook source
# Spec 004, J8: Job A's first task. It checks the one zip in the incoming folder against the pin of the run's kind,
# writes the pinned CSV, checks its shape, and hands dbt its variables. It prints nothing (J5).
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.job_a import pin_for, target_for, unpack  # noqa: E402

VOLUME = "/Volumes/workspace/default/voc_raw"
run_target = target_for(root)
values = unpack(f"{VOLUME}/incoming", f"{VOLUME}/june", pin_for(root, run_target.kind),
                root / "config" / "labels.toml")
for key, value in values.items():
    dbutils.jobs.taskValues.set(key=key, value=value)  # noqa: F821, the notebook's own global
