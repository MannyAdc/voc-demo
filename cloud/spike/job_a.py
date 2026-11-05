# Databricks notebook source
# Spec 004, pull request 5a: the spike's last task, on synthetic data only. Its exit value holds counts only (J5).
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.spike import exit_value  # noqa: E402

landed = spark.sql("select count(*) from workspace.voc_spike.landed_complaints").first()[0]  # noqa: F821
staged = spark.sql("select count(*) from workspace.voc_spike.stg_complaints").first()[0]  # noqa: F821
dbutils.notebook.exit(exit_value(landed, staged))  # noqa: F821
