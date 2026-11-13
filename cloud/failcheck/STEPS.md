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

1. In PowerShell, in this repo's folder, on an up-to-date `main` with no changes (`git checkout main`, `git pull`,
   then `git status` shows nothing to commit). First tell the window where the June files are.
   Put the folder, not the zip, in the quotes:
   `$env:VOC_JUNE_DATA_DIR = "C:\your\june\folder"`
   The folder holds `CCDB_Export_19_June_2026.zip`. This lasts until the window closes. Then run:
   `uv run --locked --native-tls voc june-check`
   If it says the zip is not in that folder, add `--zip` and the zip's path. It unpacks a copy inside the June
   data folder and removes it after. On 13 November the first try stopped because the variable was not set in
   the window, and the next because it named the zip.
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

Before step 1, find the SQL warehouse's ID, as in step 1.4 of `docs/DATABRICKS_STEPS.md`: in Databricks' left
menu click **SQL Warehouses** (or **Compute**, then the **SQL warehouses** tab), then **Serverless Starter
Warehouse**. Its ID is on its page, labelled **ID**, or the text after `warehouses/` in the address bar. Keep it
to hand and do not paste it to Claude.

1. **Make the job.** On GitHub, open `cloud/failcheck.yml` on `main` and click **Copy raw file**. In Databricks,
   click **Jobs & Pipelines**, then **Create**, then **Job**. Click the **⋮** just left of **Run now**, then
   **YAML**. Click inside the editor, press Ctrl+A, then Ctrl+V. In the two places that say `the SQL warehouse's
   ID, set by the owner`, put the warehouse's ID. Click **Save**. The job's name is `voc-june-failcheck`, with three
   tasks: `make_rows`, `dbt` and `dbt_control`. On the right side, **Run as** shows your own account, never the
   robot.
2. **Let the robot read it.** On the job's page, on the right side, under **Permissions**, click **Edit
   permissions**. In the search field, type `voc-june-runner` and click it. In the permission dropdown next to it,
   choose **Can View**. Click **Add**, then **Save**.
3. **Run it.** Click **Run now**, and wait until all three tasks have ended. Expected:
   - `make_rows` succeeded
   - `dbt` failed
   - `dbt_control` failed

   Both dbt tasks are meant to fail, and Databricks may retry them on their own first. Note the run's ID: the
   number after `/runs/` in the run page's address. Claude may be told this ID.
4. **Make the robot's secret.** At the top right click your initial or name, then **Settings**, then **Identity
   and access**, then **Manage** next to **Service principals**, then `voc-june-runner`, the **Secrets** tab, and
   **Generate secret**. In the box:
   - **Lifetime:** 1 (days)
   - **Scope:** click **Other APIs**, then **Add scope**, and choose `jobs`
   - its access: **Read + Write**, never **Read** alone. **Read** makes the scope `jobs:read`, and Databricks
     refuses a `jobs` token from it (HTTP 403, round 1 of the dry run, and nearly again on 13 November). The
     robot still sees only this job, through **Can View** in step 2.

   Click **Generate**. The box shows the **Client ID** and the **Secret** once, each with a copy icon. Keep it
   open, and do step 5 in a new browser tab. Paste them only into the notebook, never into a file or a message.
   While the box is open, and while the notebook holds the secret, take no screenshot and share no screen, not
   even for Claude ("Copying a secret safely" in `docs/DATABRICKS_STEPS.md`).
5. **Make the notebook.** In a new tab, in Databricks, click **Workspace**, then **Home**, then **Create**, then
   **Notebook**. Click its name at the top, type `voc-failcheck-robot`, and press Enter. Its language is
   **Python**. On GitHub, open `cloud/failcheck/robot_check.py` on `main`, click **Copy raw file**, and paste it
   into the notebook's first cell. At its top:
   - `CLIENT_ID = ""`: the **Client ID** from step 4, between the quotes
   - `CLIENT_SECRET = ""`: the **Secret** from step 4, between the quotes
   - `RUN_ID = 0`: the run's ID from step 3, in place of 0, with no quotes
   - `HOST = ""`: left empty, unless the cell asks for it. Then type the workspace's host name from the
     address bar, without `https://`

   Close the secret's box. Clear the clipboard: press the Windows key and V together, then **Clear all**, or copy
   any harmless word if that opens nothing. At the top right of the notebook click **Connect**, then
   **Serverless**. Run the cell with its **▶** or Shift+Enter. Copy its printed lines as text, not as a
   screenshot, since the cell above them holds the secret.
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
   - the control's output holds dbt's error and logs text, so it was read, and its dbt files hold the marker, so
     the check can see a leak where dbt writes the row's text. Databricks puts no row text in a failed dbt task's
     output, even without the quiet flags (the probe of 13 November), so the control cannot show a leak there
   - a request for an `all-apis` token is refused with HTTP 400, 401 or 403, or the token given is
     narrowed to `jobs`, so the secret holds the `jobs` scope only
   - the warehouse's query history is refused (HTTP 401 or 403)

   If Databricks offers no dbt files for the quiet run, the verdict is FAIL, and the design is rethought (owner
   decision, 6 November).

   If the verdict is `FAIL`, stop. The run log's row waits. Tell Claude the verdict line.

### Clean up, the same day

7. **The notebook.** Click **Workspace**, then **Home**. On the row `voc-failcheck-robot`, click the **⋮** at its
   right end, then **Move to Trash**, and confirm. Then click **Trash** in the same list, and on the notebook's
   row click **⋮**, then **Delete permanently**, and confirm. It holds the secret.
8. **The secret.** Settings, **Identity and access**, **Manage** next to **Service principals**,
   `voc-june-runner`, the **Secrets** tab. Delete only the secret made today, which expires tomorrow, with the
   bin icon at its row's end. The robot's other secret is the one GitHub uses to start Job B, and it stays.
9. **The job.** **Jobs & Pipelines**, then `voc-june-failcheck`, then the **⋮** just left of **Run now**, then
   **Delete job**. The box names `voc-june-failcheck`. Confirm.
10. **The folder.** **Catalog**, `workspace`, `default`, `voc_raw`. On the row `failcheck`, click the **⋮** at its
    right end, then **Delete directory**. The box names `failcheck`. Confirm. Open no file in `voc_raw`.
11. **The schema.** **Catalog**, `workspace`, then the arrow next to `voc_failcheck`, then **Tables**. First
    delete each table in it: click it, then the **⋮** at the top right of its page, then **Delete**, and confirm.
    On 13 November there was one. Then delete the schema: click `voc_failcheck`, then the **⋮** at the top
    right, then **Delete**, and confirm. With a table still there, Databricks refuses ("Schema ... is not
    empty").

The jobs list then shows `voc-june-job-a`, `voc-june-job-b` and `voc-june-spike` only.

The warehouse's query history keeps the failing statement's error, with the synthetic marker. Of this project's
accounts, only you, as the workspace admin, can read it. Nothing there is complaint text.
