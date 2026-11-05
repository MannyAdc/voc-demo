# Databricks notebook source
# Spec 004, J8 and J16: Job A's last task. It checks that the code it runs is the target row's frozen code, reads
# the frozen sample's rows from the June tables, checks them against splits/june/, computes the figures for the
# approval, and returns the contract's exit value. It prints nothing else (J5).
import os
import re
import sys
from pathlib import Path

root = Path(os.getcwd()).resolve()
while not (root / "pyproject.toml").exists() and root != root.parent:
    root = root.parent
sys.path.insert(0, str(root / "src"))

from voc.frozen import code_hash  # noqa: E402
from voc.job_a import JobAError, checked_sample, exit_value, figures, pin_for, target_for  # noqa: E402

run_target = target_for(root)
if code_hash(root) != run_target.code_hash:
    raise JobAError("the code this job runs is not the frozen code of the run log's last row")
listed = [line.split(",")[0] for line in (root / "splits" / "june" / "june.csv").read_text(encoding="utf-8").splitlines()[1:]]
# Real IDs are numbers, and the dry run's synthetic ones start with SYN- (pull request 9). They go into the SQL below.
if not all(re.fullmatch(r"(SYN-)?[0-9]{1,19}", cid) for cid in listed):
    raise JobAError("the frozen June list holds an ID that is not a complaint ID")
rows = [tuple(r) for r in spark.sql(  # noqa: F821
    "select complaint_id, product, narrative from workspace.voc_june.stg_complaints where complaint_id in ("
    + ",".join(f"'{cid}'" for cid in listed) + ")").collect()]
checked_sample(root, rows)
# The June ledger is new until Job B's first run, so nothing has been used yet. Job B checks its own ledger (J12).
dbutils.notebook.exit(exit_value(run_target, pin_for(root, run_target.kind), figures(root, rows, 0)))  # noqa: F821
