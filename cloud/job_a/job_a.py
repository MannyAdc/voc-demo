# Databricks notebook source
# Spec 004, J8 and J16: Job A's last task. It checks the run log's last row and that this is its frozen code, counts
# the rows and narratives Spark reads from the file against the pin, reads the frozen sample's rows from the June
# tables, checks them against splits/june/, computes the figures for the approval, and returns the contract's exit
# value. It prints nothing else (J5).
import os
import re
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.job_a import (JUNE_FOLDER, JobAError, checked_counts, checked_sample, checked_target,  # noqa: E402
                       count_sql, exit_value, figures, pin_for)

run_target = checked_target(root)
pin = pin_for(root, run_target.kind)
# Owner decision, 6 November: the counts Spark reads, with dbt's options, must be the laptop's for the pinned file.
counts = spark.sql(count_sql(f"{JUNE_FOLDER}/{pin['file_name']}")).collect()[0]  # noqa: F821
checked_counts(pin, counts["rows"], counts["narratives"])
listed = [line.split(",")[0] for line in (root / "splits" / "june" / "june.csv").read_text(encoding="utf-8").splitlines()[1:]]
# Real IDs are numbers, and the dry run's synthetic ones start with SYN- (pull request 9). They go into the SQL below.
if not all(re.fullmatch(r"(SYN-)?[0-9]{1,19}", cid) for cid in listed):
    raise JobAError("the frozen June list holds an ID that is not a complaint ID")
rows = [tuple(r) for r in spark.sql(  # noqa: F821
    "select complaint_id, product, narrative from workspace.voc_june.stg_complaints where complaint_id in ("
    + ",".join(f"'{cid}'" for cid in listed) + ")").collect()]
checked_sample(root, rows)
# Until pull request 6, Job A runs only a first row (checked_target), so the June ledger is new and nothing has been
# used yet. Job B checks its own ledger (J12).
dbutils.notebook.exit(exit_value(run_target, pin, figures(root, rows, 0)))  # noqa: F821
