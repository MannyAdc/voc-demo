# The dry run: the owner's steps

Spec 004, plan item 9, owner decisions of 6 and 8 November. The dry run runs the whole cloud chain once on synthetic
data with the mock backend: the upload, Job A in Databricks, Databricks' webhook to the Azure receiver, the approval
workflow on GitHub, the owner's approval, Job B, and the result message back to the receiver. It holds no API key
and calls no model. The setup before it is in `docs/DATABRICKS_STEPS.md`, click by click. This page keeps the run's
order, what each step checks, and the clean-up.

## Before the dry run, in this order

1. Pull request 9a is merged: the dry run's CSV, list, pin and mock answers.
2. At the Databricks setup, the owner creates Job A and Job B from `cloud/job_a.yml` and `cloud/job_b.yml`, with
   Job A's trigger paused, the robot's permissions and the receiver's webhook destination.
3. A pull request adds both jobs' IDs in `config/june_cloud.toml`.
4. A last pull request adds the synthetic row to `runs/JUNE_RUNS.md`, with the hashes that
   `uv run --native-tls --locked python scripts/june_hash.py --dry-run` prints from a clean checkout of `main`
   after step 3. The row comes last, since its code hash covers `config/`.

From step 4 until Job B ends, nothing that changes the frozen code is merged to `main`. And nothing at all is merged
to `main` from the upload until Job B ends: Job A runs `main` from the upload, the approval workflow's run is made
from `main` when the receiver starts it, and Job B refuses a GitHub run made from another commit than the one it
runs (review of #99).

## Before round 3, in this order

Round 1 ran on 9 November and stopped at the approval workflow's check of Job A's run. Round 2 ran on 10 November
and stopped at Job B's check of its own run, which looked for its commit on the run, where Databricks does not keep
it. Round 3's pull request fixed that check, and round 3 passed every step on 10 November. Before it:

- **Round 3's row is merged.** After round 3's pull request is merged, Claude opens a pull request with round 3's
  row in `runs/JUNE_RUNS.md` (step 4). Upload nothing before it is merged: until then the last row is round 2's,
  and Job A refuses it, since its code is no longer the code on `main`.
- **Any other open pull request is merged first, or waits.** Every pull request the owner means to merge before
  round 3 is merged before the upload. Anything else waits until Job B ends (review of #103).
- **Job A's trigger stays paused.** It was paused again after 01:17 on 10 November. To check: in Databricks, in the left
  menu, click **Jobs & Pipelines**, then Job A, `voc-june-job-a`. On the right side, **Schedules & Triggers** says
  **Paused**. Leave it so until step 6.
- **The robot can start Job B.** In **Jobs & Pipelines**, click `voc-june-job-b`. On the right side, scroll to
  **Permissions** (as on Job A's page, seen on 10 November): `voc-june-runner` shows **Can Manage Run**. If it shows anything
  else, click **Edit permissions** just below the list, choose **Can Manage Run** next to it, and click **Save**. Never **Can Manage** or **Is Owner**. In round 2 it showed **Can View**, and
  Databricks refused to start Job B (HTTP 403).
- **Delete round 2's zip.** In the left menu, click **Catalog**, then `workspace`, then `default`, then `voc_raw`,
  then the folder `incoming`. On the row of `syn_june_dry_run_r2.zip`, click the ⋮ at the right end of the row,
  then **Delete**, and confirm. The folder `incoming` itself stays. If the menu has no **Delete**, stop and tell
  Claude.
- **Delete round 2's CSV.** The same way, in the folder `june` of `voc_raw`, delete `syn_june_dry_run_r2.csv`, and
  nothing else. Open no other file in `voc_raw`, since it holds real complaint text.
- **Drop every table and view in the `voc_june` schema** (a schema is a folder that holds tables and volumes). In
  **Catalog**, click `workspace`, then `voc_june`. For each item it lists: click the item, click the ⋮ at the top
  right of its page, then **Delete**, and confirm. If the menu has no **Delete**, stop and tell Claude. Check:
  `voc_june` lists nothing. The schema itself stays. Job A's next run builds the tables again.
- **Application Insights stays on** until round 3 ends (owner decision, 9 November, until the dry run ends). Step
  16 removes it.

## The run

5. On the laptop, in the repo's folder:
   `uv run --native-tls --locked python scripts/make_dry_run.py --round 3 <a folder outside the repo>`. It prints
   the zip's name, size and SHA-256, which must be the pin's in `config/june_dry_run.toml`.
6. In Databricks, check that the volume's `incoming` folder is empty, then unpause Job A's trigger.
7. Upload the zip to the volume's `incoming` folder. Job A starts on its own.
8. Job A ends green. Its webhook reaches the receiver, which checks the run with Databricks and starts the approval
   workflow on GitHub, named for Job A's run. If no `June approval` run appears on GitHub's **Actions** tab within 10
   minutes of Job A ending green, the webhook did not get through. Tell Claude. The way on is J8's fallback: the owner
   starts `June approval` by hand on `main` with Job A's run ID.
9. The workflow's first job prints the figures: 8 complaints. Approve `june-run` on GitHub.
10. The workflow starts Job B. Job B checks the approval and Job A's run again, marks both used, and labels the 8
    complaints with the mock answers. Its results folder holds only `DRY_RUN.txt`, which ends with the counts:
    `Labelled: 8. Accepted: 7. Quarantined: 1.`
11. The workflow posts the result message. In the receiver's storage account, the `juneevents` table holds a
    `result` row for the workflow's run with `result_state` `SUCCESS`, and `june-events-poison` is empty.
12. Pause Job A's trigger again.

If a step fails, tell Claude the step and its fixed text or status. Refusals hold fixed text and IDs only.

## The clean-up, required (owner decision, 8 November)

13. Delete the dry run's zip from the volume's `incoming` folder and its CSV from the volume's `june` folder.
14. Drop every table and view in the `voc_june` schema, so the June staging table holds no synthetic row tagged
    as June beside the real ones. The real run builds them again.
15. Keep the receiver's `result` row, the used markers and the results folder's `DRY_RUN.txt`, as the dry run's
    record. They hold IDs, states, counts and fixed text only.
16. If Application Insights was turned on for a diagnosis, remove it, as in steps 3 and 4 of "Application
    Insights, for a diagnosis only" in `docs/RECEIVER_STEPS.md`.

The real run's last step checks that this clean-up was done.

## A re-run

A re-run with no code change uses the same round. If Job B refused before it marked anything used, a fresh
workflow run and a fresh approval are enough. The receiver starts the workflow only on Job A's webhook, and
GitHub's re-run button gives a second attempt, which Job B refuses. So the owner will
start `June approval` by hand on `main`, with the Job A run's ID (J8's fallback), and approve it again. Once Job B has marked the Job A run used, it needs a fresh Job A
run too: empty the `incoming` folder and make a fresh upload of the same zip (review of #99). A re-run after a
code fix is a new round: Claude adds the round's synthetic CSV with new `SYN-` IDs, and `scripts/make_dry_run.py
--round <n> --repo` writes its list, pin and mock answers. A list has one first row, and the June staging table
never changes a row it has built, so a new round also needs its own row and, before it, the clean-up of step 14.
