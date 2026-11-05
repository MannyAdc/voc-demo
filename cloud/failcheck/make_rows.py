# Databricks notebook source
# Spec 004, J5: the failcheck job's first task (owner decision, 6 November). It writes the synthetic rows, one of
# them made to fail Spark's parser, and hands dbt the same variables Job A's unpack hands it. It prints nothing.
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.failcheck import FOLDER, write_rows  # noqa: E402

values = write_rows(FOLDER, root / "config" / "labels.toml")
for key, value in values.items():
    dbutils.jobs.taskValues.set(key=key, value=value)  # noqa: F821, the notebook's own global
