# Databricks notebook source
# Spec 004, pull request 5a: the spike's first task, on synthetic data only. It prints counts only (J5).
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.spike import unpack  # noqa: E402

VOLUME = "/Volumes/workspace/default/voc_raw"
values = unpack(f"{VOLUME}/spike_incoming", f"{VOLUME}/spike", root / "config" / "labels.toml")
for key, value in values.items():
    dbutils.jobs.taskValues.set(key=key, value=value)  # noqa: F821, the notebook's own global
print(f"unpacked: {values['month_rows']} synthetic rows")
