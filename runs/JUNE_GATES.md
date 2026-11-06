# June gates

Spec 004, J1 (owner decisions, 6 November). Each row records one result of a gate that must pass before the real
row of `runs/JUNE_RUNS.md`: `june-check`, the owner's check of the June zip on the laptop, and `failcheck`, the
failing-row check read as the robot in Databricks (`cloud/failcheck/STEPS.md`). A fail is recorded too.

- Date: the local time the gate ran, from its own output.
- Result: `pass` or `fail`, from its verdict line.
- Pin SHA-256 and Code hash: from its gate record line (june-check) or `code sha256` line (failcheck).
- Evidence: its verdict line, and for the failcheck, its run ID.

A gate is open for a code hash and the June pin when its latest result for them is `pass`. Only results dated
strictly before the real row count, and CI refuses a new real row whose passes are not on `main` already.
`scripts/june_hash.py`, Job A and a test refuse a real row without both gates open. This log only grows, and rows
are never changed.

| Date | Gate | Result | Pin SHA-256 | Code hash | Evidence |
|---|---|---|---|---|---|
