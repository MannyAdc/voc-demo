# The two gates before the June run log's row: the owner's steps

Spec 004, J1, J5 and J13. Owner decisions, 6 November. Two gates must pass before the real row of
`runs/JUNE_RUNS.md` is written (pull request 10):
- `june-check`, the owner's check of the June zip on the laptop
- `failcheck`, the failing-row check in Databricks, read as the robot

## When

Run both after the last code change is merged, that is after pull request 9, and before pull request 10. A pass
counts only for the code it ran on. So if any code changes after a gate, run both gates again. This file is in the
frozen `cloud/` folder too, so even a typo fix here means both gates run again.

Each result, a pass or a fail, is recorded as a row of `runs/JUNE_GATES.md`, in a pull request Claude opens, from
the lines the gate prints:
- Date: the time the gate ran, in UTC, from its `ran at` or `checked at` line. Both gates print UTC, so no time
  is converted.
- Result: `pass` or `fail`, from its verdict line
- Pin SHA-256: from june-check's gate record line. For the failcheck, the June pin's `sha256` in
  `config/data_files.toml` at the code the failcheck ran.
- Code hash: from june-check's gate record line, or the failcheck's `code sha256` line. If a failcheck stopped
  before it could read one, Claude computes the code hash of the `main` commit the job ran.
- Evidence: its verdict line, and for the failcheck its run ID

That pull request merges before pull request 10 opens, since CI refuses a real row whose passes are not on `main`
already. A gate's latest result for the code and pin is the one that counts, so a fail after a pass closes it.
`scripts/june_hash.py`, Job A and a test all refuse the real row unless both gates are open for its code and the
June pin.

## Gate 1: june-check, on the laptop

1. In PowerShell, in this repo's folder, on an up-to-date `main` with no changes:
   `uv run --locked --native-tls voc june-check`
   If the June zip is not in the June data folder, add `--zip` and its path. It unpacks a copy inside the June
   data folder and removes it after.
2. Paste the lines it prints to Claude. They hold counts and hashes only. The gate passes when:
   - the rows line and the narratives line say `matches`
   - the sampled rows line says `matches`
   - the line on sampled narratives with a carriage return says 0
   - the last lines are `verdict: PASS`, a `ran at:` line in UTC and a `gate record: june-check passed` line

   On a fail it still prints `ran at:` and a `gate record: june-check failed` line, so the fail can be recorded.

   The two counts of line breaks in the whole file are for the record only.

   If it says `DIFFERS` or `verdict: FAIL`, or stops with an error, stop and tell Claude. The run log's row waits.

## Gate 2: failcheck, in Databricks

It answers one question: when Job A's dbt task fails on a row, can the robot `voc-june-runner` read any of the
row's text? The job runs Job A's own dbt command on synthetic rows, one of them made to fail. Then it runs the
same command without the quiet flags, as a control, which must show the marker. You read both as the robot.

### What you create, and for how long

| Name | Where | What it is for | Lifetime |
|---|---|---|---|
| `voc-june-failcheck` | Databricks, Jobs & Pipelines | the job that runs the check once | deleted at the end |
| a new OAuth secret of `voc-june-runner` | Databricks, Settings, Service principals | the robot's sign-in for this check | 1 day, deleted at the end |
| `voc-failcheck-robot` | Databricks, Workspace, your Home folder | the notebook that reads the run as the robot | deleted at the end |

The job also makes these, which you delete at the end:
- the folder `failcheck` in the `voc_raw` volume, with one synthetic CSV
- the schema `voc_failcheck` in the `workspace` catalog, which dbt makes

### Steps

1. **Make the job.** Jobs & Pipelines, then Create, then Job. Open the YAML editor, as for the spike. Replace
   everything in it with the text of `cloud/failcheck.yml` from this repo's `main` on GitHub. In two places, put
   the SQL warehouse's ID where the text says `the SQL warehouse's ID, set by the owner`. Save. The job's name is
   `voc-june-failcheck`. It has three tasks: `make_rows`, `dbt` and `dbt_control`.
2. **Let the robot read it.** On the job's page, Permissions, add `voc-june-runner` with Can View. Save.
3. **Run it.** Press Run now, and wait until all three tasks have ended. Expected:
   - `make_rows` succeeded
   - `dbt` failed
   - `dbt_control` failed

   Both dbt tasks are meant to fail. Note the run's ID: the number after `/runs/` in the run page's address.
4. **Make the robot's secret.** Settings, Identity and access, Service principals, `voc-june-runner`, Secrets,
   Generate secret. Lifetime 1 day, scope `jobs` only. It shows the client ID and the secret once. Paste them only
   into the notebook of step 5, not into a file or a message.
5. **Make the notebook.** Workspace, Home, Create, Notebook. Rename it `voc-failcheck-robot`. Paste into its first
   cell the text of `cloud/failcheck/robot_check.py` from GitHub. At its top, fill in `CLIENT_ID`,
   `CLIENT_SECRET` and `RUN_ID`. Leave `HOST` empty unless the cell asks for it, then type the workspace's host
   name from the browser's address bar, without `https://`. Connect to serverless and run the cell.
6. **Read the lines it prints.** They hold task keys, states, places, file counts, status codes, the time in UTC
   and the failcheck code's hash, never the secret, the token or a value it read. Paste them to Claude. The gate
   passes only when the last line is `verdict: PASS`. Databricks retries a failed task on its own, so `dbt` and
   `dbt_control` may each have run more than once. The check reads every attempt, and its lines name each one,
   such as `dbt (attempt 1)`. Every attempt of every task must be readable, and no attempt of `make_rows` or of any
   other task may hold the marker. The rules below on `dbt` apply to every attempt of `dbt`, and those on the
   control to the latest attempt of `dbt_control`. The latest attempt of `make_rows` must have succeeded. An
   attempt number that is not a whole number is refused, and so is a missing one beside others. The rules:
   - both dbt runs' dbt files show they reached the failing model, so the quiet flags were really tested
   - the marker is nowhere in `dbt`'s run details, output or dbt files, and every one of them could be read
   - the marker is in no other task, `make_rows` included
   - the control shows the marker in its output and in its dbt files, so the check can see a leak
   - a request for an `all-apis` token is refused with HTTP 400, 401 or 403, or the token given is
     narrowed to `jobs`, so the secret holds the `jobs` scope only
   - the warehouse's query history is refused (HTTP 401 or 403)

   If Databricks offers no dbt files for the quiet run, the verdict is FAIL, and the design is rethought (owner
   decision, 6 November).

   If the verdict is `FAIL`, stop. The run log's row waits. Tell Claude the verdict line.

### Clean up, the same day

7. Delete the notebook `voc-failcheck-robot`, then empty it from the Trash. It holds the secret.
8. Delete the robot's secret: Settings, Identity and access, Service principals, `voc-june-runner`, Secrets.
9. Delete the job `voc-june-failcheck`.
10. Catalog, `workspace`, `default`, `voc_raw`: delete the folder `failcheck`.
11. Catalog, `workspace`: delete the schema `voc_failcheck`.

The warehouse's query history keeps the failing statement's error, with the synthetic marker. Of this project's
accounts, only you, as the workspace admin, can read it. Nothing there is complaint text.
