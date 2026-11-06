# June gates

Spec 004, J1 (owner decision, 6 November). Each row records one pass of a gate that must come before the real row
of `runs/JUNE_RUNS.md`: `june-check`, the owner's check of the June zip on the laptop, and `failcheck`, the
failing-row check read as the robot in Databricks (`cloud/failcheck/STEPS.md`). A pass counts only for the code
hash and the June pin it names, and only if it is dated before the real row. `scripts/june_hash.py`, Job A and a
test all refuse a real row without both. This log only grows, and rows are never changed.

| Date | Gate | Pin SHA-256 | Code hash | Evidence |
|---|---|---|---|---|
