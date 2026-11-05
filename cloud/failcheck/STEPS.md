# The failing-row check: the owner's steps

Spec 004, J5 and J13. Owner decision, 6 November: a gate before the June upload. Run it once, after the pull
request that adds this file is merged. It uses synthetic rows only, and no model call.

It answers one question: when Job A's dbt task fails on a row, can the robot `voc-june-runner` read any of the
row's text? The job runs Job A's own dbt command on synthetic rows, one of them made to fail. Then it runs the
same command without the quiet flags, as a control. You read both as the robot.

## What you create, and for how long

| Name | Where | What it is for | Lifetime |
|---|---|---|---|
| `voc-june-failcheck` | Databricks, Jobs & Pipelines | the job that runs the check once | deleted at the end |
| a new OAuth secret of `voc-june-runner` | Databricks, Settings, Service principals | the robot's sign-in for this check | 1 day, deleted at the end |
| `voc-failcheck-robot` | Databricks, Workspace, your Home folder | the notebook that reads the run as the robot | deleted at the end |

The job also makes these, which you delete at the end:
- the folder `failcheck` in the `voc_raw` volume, with one synthetic CSV
- the schema `voc_failcheck` in the `workspace` catalog, which dbt makes

## Databricks

1. **Make the job.** Jobs & Pipelines, then Create, then Job. Open the YAML editor, as for the spike. Replace
   everything in it with the text of `cloud/failcheck.yml` from this repo's `main` on GitHub. In two places, put
   the SQL warehouse's ID where the text says `the SQL warehouse's ID, set by the owner`. Save. The job's name is
   `voc-june-failcheck`. It has three tasks: `make_rows`, `dbt` and `dbt_control`.
2. **Let the robot read it.** On the job's page, Permissions, add `voc-june-runner` with Can View. Save.
3. **Run it.** Press Run now. It takes about 5 minutes. Expected:
   - `make_rows` succeeded
   - `dbt` failed
   - `dbt_control` failed

   Both dbt tasks are meant to fail. Note the run's ID: the number after `/runs/` in the run page's address.
4. **Make the robot's secret.** Settings, Identity and access, Service principals, `voc-june-runner`, Secrets,
   Generate secret. Lifetime 1 day, scope `jobs` only. Copy the client ID and the secret. They are shown once.
5. **Make the notebook.** Workspace, Home, Create, Notebook. Rename it `voc-failcheck-robot`. Paste into its first
   cell the text of `cloud/failcheck/robot_check.py` from GitHub. At its top, fill in `CLIENT_ID`,
   `CLIENT_SECRET` and `RUN_ID`. Leave `HOST` empty. Connect to serverless and run the cell.
6. **Read the lines it prints.** They hold task keys, states, places and status codes only, never the secret or a
   value it read. Paste them to Claude. The check passes when:
   - `dbt: FAILED, marker in the output: nowhere`, and any `dbt: artifacts:` line ends `marker in: nowhere`
   - a `dbt_control` line names a place, which shows the check can see a leak
   - `query history: HTTP 401` or `HTTP 403`, so the robot cannot read the warehouse's query history

   If the marker is anywhere in `dbt`'s lines, stop. The June upload waits. If `dbt_control` shows it nowhere,
   the check could not see a leak, so tell Claude before going on.

## Clean up, the same day

7. Delete the notebook `voc-failcheck-robot`, then empty it from the Trash. It holds the secret.
8. Delete the robot's secret: Settings, Identity and access, Service principals, `voc-june-runner`, Secrets.
9. Delete the job `voc-june-failcheck`.
10. Catalog, `workspace`, `default`, `voc_raw`: delete the folder `failcheck`.
11. Catalog, `workspace`: delete the schema `voc_failcheck`.

The warehouse's query history keeps the failing statement's error, with the synthetic marker. Of this project's
accounts, only you, as the workspace admin, can read it. Nothing there is complaint text.
