# Databricks notebook source
# Spec 004, J8 and J16: Job A's last task. It checks the run log's last row and that this is its frozen code, counts
# the rows and narratives Spark reads from the file against the pin, reads the frozen sample's rows from the June
# tables, checks them against splits/june/, computes the figures for the approval, and returns the contract's exit
# value. It prints nothing else (J5).
import os
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.job_a import (JUNE_FOLDER, checked_counts, checked_sample, checked_target, exit_value,  # noqa: E402
                       figures, listed_ids, pin_for, runner, spark_counts, spark_rows)

run_target = checked_target(root)
pin = pin_for(root, run_target.kind)
# Spark's errors could quote a row, so both reads go through wrappers that refuse with fixed text only.
run_sql = runner(spark)  # noqa: F821, the notebook's own global
# Owner decision, 6 November: the counts Spark reads, with dbt's options, must be the laptop's for the pinned file.
rows_read, narratives_read = spark_counts(run_sql, f"{JUNE_FOLDER}/{pin['file_name']}")
checked_counts(pin, rows_read, narratives_read)
# Pull request 9a: a synthetic target reads the dry run's own list, with SYN- IDs only.
rows = spark_rows(run_sql, listed_ids(root, run_target))
checked_sample(root, rows, run_target)
# Until pull request 6, Job A runs only a first row (checked_target), so the June ledger is new and nothing has been
# used yet. Job B checks its own ledger (J12).
dbutils.notebook.exit(exit_value(run_target, pin, figures(root, rows, 0)))  # noqa: F821
