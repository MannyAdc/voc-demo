# June gates

Spec 004, J1 (owner decisions, 6 November). Each row records one result of a gate that must pass before the real
row of `runs/JUNE_RUNS.md`: `june-check`, the owner's check of the June zip on the laptop, and `failcheck`, the
failing-row check read as the robot in Databricks (`cloud/failcheck/STEPS.md`). A fail is recorded too.

- Date: the time the gate ran, in UTC, from its own output. The run log's real row is dated in UTC too.
- Result: `pass` or `fail`, from its verdict line.
- Pin SHA-256 and Code hash: from its gate record line (june-check) or `code sha256` line (failcheck).
- Evidence: its verdict line, and for the failcheck, its run ID.

A gate is open for a code hash and the June pin when its latest result for them is `pass`. Only results dated
strictly before the real row count, and CI refuses a new real row whose passes are not on `main` already.
`scripts/june_hash.py`, Job A and a test refuse a real row without both gates open. This log only grows, and rows
are never changed.

| Date | Gate | Result | Pin SHA-256 | Code hash | Evidence |
|---|---|---|---|---|---|
| 2026-11-13 02:01 | june-check | pass | 4adca715ede2ac1780bf72d3735b34fb7d88616f2aa9468ea41357f414180850 | e6a61fe3a42497198ff7e020aa351dfef17aba2b8302d26499e5b5bea8ad55f6 | verdict: PASS |
| 2026-11-13 02:25 | failcheck | fail | 4adca715ede2ac1780bf72d3735b34fb7d88616f2aa9468ea41357f414180850 | e6a61fe3a42497198ff7e020aa351dfef17aba2b8302d26499e5b5bea8ad55f6 | verdict: FAIL: the run lists the task dbt twice and the run lists the task dbt_control twice (the verdict line joins them with a bar, which marks a column here), run 340824676096743 |
| 2026-11-13 06:08 | june-check | pass | 4adca715ede2ac1780bf72d3735b34fb7d88616f2aa9468ea41357f414180850 | 41f7163892d0aae76a6d1c461032eacb39320788c1a661954f9eb6eba95020f8 | verdict: PASS |
| 2026-11-13 06:26 | failcheck | fail | 4adca715ede2ac1780bf72d3735b34fb7d88616f2aa9468ea41357f414180850 | 41f7163892d0aae76a6d1c461032eacb39320788c1a661954f9eb6eba95020f8 | verdict: FAIL: the control shows no leak in its output, so the check cannot see one, run 64209205776851 |
| 2026-11-13 09:29 | june-check | pass | 4adca715ede2ac1780bf72d3735b34fb7d88616f2aa9468ea41357f414180850 | db063ac8f671e5fa4b3944adca2b25c3c9b605f6b444157f91102ff30c0d677a | verdict: PASS |
| 2026-11-13 09:47 | failcheck | pass | 4adca715ede2ac1780bf72d3735b34fb7d88616f2aa9468ea41357f414180850 | db063ac8f671e5fa4b3944adca2b25c3c9b605f6b444157f91102ff30c0d677a | verdict: PASS, run 269286114094038 |
