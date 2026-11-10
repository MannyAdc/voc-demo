# The dry run: the owner's steps

Spec 004, plan item 9, owner decisions of 6 and 8 November. The dry run runs the whole cloud chain once on synthetic
data: the upload, Job A in Databricks, Databricks' webhook to the Azure receiver, the approval workflow on GitHub,
the owner's approval, Job B, and the result message back to the receiver. Rounds 1 to 3 used the mock backend and
called no model. From round 4, Job B labels the 8 synthetic complaints through the API, with the key of the Claude
Console workspace `voc-june-cloud` and the June ledger, so they are proven in the cloud before June (owner decision,
10 November, option A). The setup before it is in `docs/DATABRICKS_STEPS.md`, click by click. This page keeps the
run's order, what each step checks, and the clean-up.

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

## Before round 4, in this order

Round 1 ran on 9 November and stopped at the approval workflow's check of Job A's run. Round 2 ran on 10 November
and stopped at Job B's check of its own run. Round 3's pull request fixed that check, and round 3 passed every step
on 10 November, with the mock backend. The pull requests of 6b then changed the frozen code: Job B's packages, the
refit, the June ledger, the API, the results files and the clean-up. So round 4 runs that code once, with new
`SYN-94` IDs, before the real run.

- **Round 4's row is merged.** After round 4's pull request is merged, Claude opens a pull request with round 4's
  row in `runs/JUNE_RUNS.md` (step 4). Upload nothing before it is merged: until then the last row is round 3's,
  and Job A refuses it, since its code is no longer the code on `main`.
- **Any other open pull request is merged first, or waits.** Every pull request the owner means to merge before
  round 4 is merged before the upload. Anything else waits until Job B ends (review of #103).
- **Job B's settings match its file.** Since round 3, `cloud/job_b.yml` stops Job B after three hours, not one
  (owner decision, 10 November). In your browser, open
  `https://github.com/MannyAdc/voc-demo/blob/main/cloud/job_b.yml` and click **Copy raw file**. In Databricks, in
  the left menu, click **Jobs & Pipelines**, then `voc-june-job-b`. Click the **⋮** just left of the grey
  **Run now** button, then the **YAML** item. Click inside the editor, press Ctrl+A, then Ctrl+V. Click **Save**.
  Check: open the **⋮** and the **YAML** item again, find the line `timeout_seconds: 10800`, and close the editor
  without saving. The name is still `voc-june-job-b`, **Schedules & Triggers** shows no trigger, **Run as** shows
  your own account, and on the right side the **Job ID** is still `111509808656471`, as `job_b_job_id` in
  `config/june_cloud.toml`.
- **The money side.** Round 4's 8 calls go through the June ledger in the volume, the same ledger as the real run,
  with its cap of 40,000,000 tokens (`june_cap_tokens` in `config/budget.toml`). They should use about 13,000
  tokens, from the laptop's expected use of about 3,000,000 tokens for 1,909 complaints. The hard stop is the $5
  monthly spend limit of the Claude Console workspace `voc-june-cloud`. A call that uses more than its reservation
  would block the June ledger until the owner decides how to clear it (spec 004, Known limits). `DRY_RUN.txt` holds
  no token count, so step 10 checks the cost in the Console.
- **The robot can start Job B.** On the same page, on the right side, scroll to **Permissions**:
  `voc-june-runner` shows **Can Manage Run**. If it shows anything else, click **Edit permissions** just below the
  list, choose **Can Manage Run** next to it, and click **Save**. Never **Can Manage** or **Is Owner**. In round 2
  it showed **Can View**, and Databricks refused to start Job B (HTTP 403).
- **Job A's trigger stays paused.** The owner paused it again after round 3, before 10:58 on 10 November. To check:
  in **Jobs & Pipelines**, click Job A, `voc-june-job-a`. On the right side, **Schedules & Triggers** says
  **Paused**. Leave it so until step 6.
- **Round 3's files and tables are gone.** The owner deleted round 3's zip and CSV and dropped `voc_june`'s four
  objects after round 3, on 10 November. To check: in the left menu, click **Catalog**, then `workspace`, then
  `default`, then `voc_raw`, then the folder `incoming`, which lists nothing. In the folder `june` of `voc_raw`,
  `syn_june_dry_run_r3.csv` is not listed. Open no file in `voc_raw`, since it holds real complaint text. Then click
  `workspace`, then `voc_june`, which lists nothing. If round 3's zip or CSV is still there, delete it: on its row,
  click the ⋮ at the right end, then **Delete**, and confirm. If `voc_june` lists anything, drop every table and
  view in the `voc_june` schema: click the item, click the ⋮ at the top right of its page, then **Delete**, and
  confirm. If a menu has no **Delete**, stop and tell Claude.
- **Application Insights is off.** The owner removed it after round 3, on 10 November. Round 4 needs it only for a
  diagnosis (step 16).

## The run

5. On the laptop, in the repo's folder:
   `uv run --native-tls --locked python scripts/make_dry_run.py --round 4 <a folder outside the repo>`. It prints
   the zip's name, size and SHA-256, which must be the pin's in `config/june_dry_run.toml`.
6. In Databricks, check that the volume's `incoming` folder is empty, then unpause Job A's trigger.
7. Upload the zip to the volume's `incoming` folder. Job A starts on its own.
8. Job A ends green. Its webhook reaches the receiver, which checks the run with Databricks and starts the approval
   workflow on GitHub, named for Job A's run. If no `June approval` run appears on GitHub's **Actions** tab within 10
   minutes of Job A ending green, the webhook did not get through. Tell Claude. The way on is J8's fallback: the owner
   starts `June approval` by hand on `main` with Job A's run ID.
9. The workflow's first job prints the figures: 8 complaints. Approve `june-run` on GitHub.
10. The workflow starts Job B. Job B checks the approval and Job A's run again, marks both used, refits the July
    model and checks it, and labels the 8 complaints through the API and the June ledger. Its results folder holds
    only `DRY_RUN.txt`. The note says Job B labelled with the API, then gives `Labelled: 8.` with the accepted and
    quarantined counts. The model decides those, so any split of the 8 is fine. Rounds 1 to 3, with the mock
    answers, showed `Accepted: 7. Quarantined: 1.` The note's last line is the clean-up's, below. Then, in the
    Claude Console, open the workspace `voc-june-cloud` and its usage or cost page, and tell Claude the cost it
    shows. If the page has another name, tell Claude what you see.
    A stop that only the API can cause ends the labelling early: 3 complaints in a row failing, as with a bad key
    or a network fault (`error`, the likeliest in a first API round), an answer from another workspace, the spend
    limit, or the ledger's cap. Then the results folder has no `DRY_RUN.txt`, Job B's run page in Databricks shows
    the notebook's exit value with `"stopped": true` and its `stop_reason`, and Job B cleans up nothing, so steps
    13 and 14 are done by hand. Tell Claude the `stop_reason`.
11. The workflow posts the result message. In the receiver's storage account, the `juneevents` table holds a
    `result` row for the workflow's run with `result_state` `SUCCESS`, and `june-events-poison` is empty.
12. Pause Job A's trigger again.

If a step fails, tell Claude the step and its fixed text or status. Refusals hold fixed text and IDs only.

## The clean-up, required (owner decision, 8 November)

From round 4, Job B does step 13 and drops the four objects Job A builds in `voc_june` (the view
`curated_complaints` and the tables `landed_complaints`, `stg_complaints` and `test_list`), which is step 14 while
the schema holds only those. It does this after a finished synthetic run, and its note `DRY_RUN.txt` ends
with `Cleaned up: 2 files deleted, 4 June tables and views dropped.` (6b part 7, owner decision of 10 November).
Do them by hand only when the note says `Clean-up incomplete`, or when the run stopped, which cleans up nothing.
Step 12, the trigger, stays the owner's.

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
