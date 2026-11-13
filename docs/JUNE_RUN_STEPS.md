# The June run: the owner's steps

Spec 004, plan item 11. The June run scores the frozen June sample once, in the cloud, on the code both gates
passed, `db063ac8…677a` (#133), with the run log's real row (#134). It is the dry run's chain with the real June file:
the upload, Job A, the webhook, the receiver, the approval workflow, your approval, Job B, and the result message.
Job B labels the June sample through the API with the key of the Claude Console workspace `voc-june-cloud`, scores
it, and writes two results files. Then Claude copies them into the repo. The owner decided to run June at 23:37 on
13 November (plan item 9's stop point).

Once Job B has started labelling, the real row is used up. A run that stops cannot be resumed without a further pull
request (spec 004, Known limits). So each check below comes first.

Nothing at all is merged to `main` from the upload until Job B ends: Job A and the workflow run `main`, and Job B
refuses a workflow run made from another commit than the one it runs. Nothing that changes the frozen code is merged
until the run ends either, or both gates and the real row must be done again.

## Before the run, in this order

- **The real row is on `main`.** #134 is merged. The run log's last row is the real one, `real`, June list
  `4ae0c333…77d0` and code `db063ac8…677a`.
- **No other pull request is open,** or it waits until Job B ends.
- **Job B's settings still match its file.** In Databricks, click **Jobs & Pipelines**, then `voc-june-job-b`, then
  the **⋮** just left of **Run now**, then **YAML**. Find the line `timeout_seconds: 10800`, and close the editor
  without saving. On the right side: **Schedules & Triggers** shows no trigger, **Run as** shows your own account,
  the **Job ID** is `111509808656471`, and under **Permissions** `voc-june-runner` has **Can Manage Run**.
- **Job A's trigger is paused.** Click **Jobs & Pipelines**, then `voc-june-job-a`. On the right side,
  **Schedules & Triggers** says **Paused**. Leave it so until the run.
- **The dry run's clean-up was done.** Round 6's Job B did it on 13 November, and you checked it at 12:05. To check
  again: click **Catalog**, then `workspace`, then `default`, then `voc_raw`, then the folder `incoming`, which lists
  nothing. In the folder `june` of `voc_raw`, no `syn_june_dry_run_` CSV is listed. Then click `workspace`, then
  `voc_june`, which lists nothing. Open no file in `voc_raw`. If anything is there, stop and tell Claude.
- **The money side.** The run's calls go through the June ledger, with its cap of 40,000,000 tokens, of which round
  6 used 8,013. The spec expects about $0.49 for the whole sample, at the July test run's cost per complaint. The
  worst case the ledger reserves is about 38 million tokens, which would cost more than the $5 monthly spend limit of
  the Claude Console workspace `voc-june-cloud`, so that limit is the hard stop. In the Console, open
  `voc-june-cloud` and note the cost the key `voc-june-job-b` shows now.
- **The June zip on the laptop.** `CCDB_Export_19_June_2026.zip` in your June folder, the one `june-check` read on 13
  November. Its pin in `config/data_files.toml` is 19,624,767 bytes, SHA-256 `3021c8af…49df`. Job A checks it
  against the pin, and refuses any other file.
- **Application Insights is off,** as it has been since round 3.

## The run

1. In Databricks, check that `incoming` is still empty. Then unpause Job A's trigger: **Jobs & Pipelines**, then
   `voc-june-job-a`, then, under **Schedules & Triggers**, resume **File arrival**.
2. Wait for the trigger's fresh look: refresh Job A's page until **Last evaluated** shows a time after the unpause
   and says 0 files in total. Only then go on. In round 4 the zip went up before that look, and no run started.
3. Upload `CCDB_Export_19_June_2026.zip` to `incoming`: **Catalog**, `workspace`, `default`, `voc_raw`,
   `incoming`, then **Upload to this volume**. Job A starts on its own within a minute or two.
4. Job A ends green. It unpacks the zip, checks the CSV against the pin, and builds the June tables. It takes a few
   minutes.
5. Within about 10 minutes, a `June approval` run named for Job A's run appears on GitHub's **Actions** tab. If none
   appears, tell Claude, who looks it up. The way on is to start `June approval` by hand on `main`, with Job A's run
   ID.
6. **Check the figures before you approve.** Open the run, then the **figures** job's summary. It must show:
   - `kind`: real
   - `run log row`: 2026-11-13 11:40, real
   - `complaints`: 2,073, the frozen June sample
   - `worst_case_tokens` no larger than `tokens_left_under_cap`, which shows 40,000,000: Job A counts the cap only
     (`figures(root, rows, 0)` in `cloud/job_a/job_a.py`). Job B checks the ledger's real room, after round 6's
     8,013 tokens, before its first call, and refuses if the worst case does not fit
   - `expected_cost_usd`: about 0.49, and well under 5

   Paste the summary's lines to Claude, who checks them too. If anything differs, do not approve.
7. Approve: click **Review deployments**, tick `june-run`, and click **Approve and deploy**.
8. Job B checks the approval and Job A's run, refits the July model with the pinned vocabulary and checks it, marks
   the run used, writes the real row's start marker, and labels the 2,073 complaints through the API and the June
   ledger. Then it scores them and writes two files to its results folder: `v1_june.csv`, one row per complaint with
   IDs, labels, positions and reasons only, and `v1_june.json`, the summary. Its time limit is 3 hours. Round 6's
   whole Job B, its refit and 8 calls, took 2 minutes 43 seconds. The time for 2,073 calls was not measured, so
   the labelling should fit, but that is not proven.
9. When Job B ends, the workflow posts the result. Its `run` job shows a green tick, with the last log line `Job B
   finished`, or a red cross, with "Job B did not finish, so this job fails after the result was sent". Tell Claude
   which, and Job B's run ID from its run page. If it stopped, its run page shows the exit value's `stop_reason`:
   tell Claude that too.
10. Pause Job A's trigger again.
11. In the Console, note the key's cost again. It may take a while to show.

If a step fails, tell Claude the step and its fixed text or status. Refusals hold fixed text and IDs only.

## After the run

12. Claude copies the two results files into `results/june/`, as the read-only reader, with
    `uv run --native-tls --locked python scripts/copy_june_results.py <Job B run ID>`, and opens the results pull
    request. It prints only the files' names and the rows' count. You do not open the files in the volume.
13. Keep the results folder, the used markers, the start marker and the receiver's `result` row, as the run's record.
    The spec names no clean-up of the June tables or the June CSV after the real run. Claude asks you before anything
    is deleted.
