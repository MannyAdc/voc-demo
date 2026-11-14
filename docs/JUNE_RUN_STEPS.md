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
  the **Job ID** is `111509808656471`, and under **Permissions** `voc-june-runner` has **Can Manage Run**. If
  **Permissions** shows anything else for `voc-june-runner`, click **Edit permissions** just below the list, choose
  **Can Manage Run** next to it, and click **Save**. Never **Can Manage** or **Is Owner**. In round 2 it showed
  **Can View**, and Databricks refused to start Job B (HTTP 403). If any other of these settings differs, stop and
  tell Claude.
- **Job A's trigger is paused.** Click **Jobs & Pipelines**, then `voc-june-job-a`. On the right side,
  **Schedules & Triggers** says **Paused**. Leave it so until the run.
- **The dry run's clean-up was done.** Round 6's Job B did it on 13 November, and you checked it at 12:05. To check
  again: click **Catalog**, then `workspace`, then `default`, then `voc_raw`, then the folder `incoming`, which lists
  nothing. In the folder `june` of `voc_raw`, no `syn_june_dry_run_` CSV is listed. Then click `workspace`, then
  `voc_june`, which lists nothing. Open no file in `voc_raw`. If anything is there, stop and tell Claude.
- **The money side.** The run's calls go through the June ledger, with its cap of 40,000,000 tokens, of which round
  6 used 8,013. The spec expects about $0.49 for the whole sample, at the July test run's $0.2373 per 1,000
  complaints: 0.2373 × 2,073 / 1,000 = 0.4919. Job A's figures round it up to the cent, so they show 0.50. The
  worst case the ledger reserves is about 38.4 million tokens (spec 004), which would cost more than the $5 monthly
  spend limit of the Claude Console workspace `voc-june-cloud`, so that limit is the hard stop. In the Console, open
  `voc-june-cloud` and note the cost the key `voc-june-job-b` shows now.
- **The Claude Console key and its limit.** In the Console, open the workspace `voc-june-cloud`. Its API keys page
  lists `voc-june-job-b` as **Active**, with an end date after the run. On 13 November your screenshot showed it
  ends on 10 December 2026. The workspace's limits show the monthly spend limit of $5. If the key is not
  **Active**, or the limit is not $5, stop and tell Claude. Job B marks the run used and writes the start marker
  before its first call, so a dead key would stop the run with `error` after the real row is used up. If a page has
  another name, tell Claude what you see.
- **The 30-day credentials.** Each was made with a life of 30 days. Check that each one ends after tomorrow. Open
  no secret's value.
  - The robot's secret: in Databricks, your initial or name at the top right, **Settings**, **Identity and
    access**, next to **Service principals** **Manage**, then `voc-june-runner`, the **Secrets** tab. Its row shows
    its dates. If it shows no end date, the end is its made date plus 30 days. It was made on 9 November, between
    15:33 and 15:48, so it ends about 9 December. The GitHub environments `june-figures` and `june-run` and the
    Key Vault hold copies of this same secret, so its end is theirs too. Their other secrets, the robot's client
    ID `VOC_DATABRICKS_CLIENT_ID`, the host, the receiver's address and the result secret, have no end date.
  - The dispatch token `voc-receiver-dispatch`: on github.com, your profile picture at the top right, **Settings**,
    at the bottom of the left menu **Developer settings**, then **Personal access tokens**, **Fine-grained
    tokens**. Its row shows when it expires. It was made on 9 November at 08:45, so it ends about 9 December.
  - The reader's secret: the same Databricks page as the robot's, but `voc-results-reader`, the **Secrets** tab.
    It was made on 10 or 11 November, before the reader's checks of 11 November, so it ends about 10 to 11
    December. Then, in your own
    terminal, in the repo's folder, run
    `uv run --native-tls --locked python scripts/copy_june_results.py --check-reader` and paste its output to
    Claude. Its last line must be `verdict | PASS`. The copy after the run signs in as the reader.
  - The Console key, above.

  If one ends before the run, stop and tell Claude. A renewed secret changes no code.
- **The June zip on the laptop.** `CCDB_Export_19_June_2026.zip` in your June folder, the one `june-check` read on 13
  November. Its pin in `config/data_files.toml` is 19,624,767 bytes, SHA-256 `3021c8af…49df`. Job A checks it
  against the pin, and refuses any other file.
- **Application Insights is off,** as it has been since round 3.

## The run

1. In Databricks, check that `incoming` is still empty. Then unpause Job A's trigger: **Jobs & Pipelines**, then
   `voc-june-job-a`, then, under **Schedules & Triggers**, resume **File arrival**.
2. Wait for the trigger's fresh look: refresh Job A's page until **Last evaluated**, under **Schedules &
   Triggers**, shows a time after the unpause and says 0 files in total. Only then go on. In round 4 the zip went
   up before that look, the trigger said "Found no new files and 1 file in total", and no run started.
3. Upload `CCDB_Export_19_June_2026.zip` to `incoming`: **Catalog**, `workspace`, `default`, `voc_raw`,
   `incoming`, then **Upload to this volume**. Job A starts on its own within a minute or two. If no run of Job A
   starts and **Last evaluated** says "Found no new files and 1 file in total", as in round 4, delete the zip from
   `incoming` (on its row, the ⋮ at the right end, then **Delete**, and confirm), wait for a look that says 0 files
   in total, and upload it again. Job A has not run, so nothing is used.
4. Job A ends green. It unpacks the zip, checks the CSV against the pin, and builds the June tables. It takes a few
   minutes.
5. Within about 10 minutes of Job A ending green, a `June approval` run named for Job A's run appears on GitHub's
   **Actions** tab. If none appears, tell Claude, who looks it up first. The way on, only after Claude says so (J8's
   fallback): on GitHub, the **Actions** tab, `June approval` in the left list, then the **Run workflow** button on
   the right. **Use workflow from:** Branch: `main`. **Job A's run ID** (the field `job_a_run_id`): the run ID on
   Job A's run page. Click the green **Run workflow**.
6. **Check the figures before you approve.** Open the run, then the **figures** job's summary, under "The figures to
   approve". It shows nine lines, in this order. The numbers have no commas.
   - `Job A run: <ID>`, the same run ID as on Job A's run page
   - `kind: real`
   - `run log row: 2026-11-13 11:40, real`
   - `started: <date and time> UTC`, Job A's start
   - `complaints: 2073`, the frozen June sample
   - `calls: 2073`, one call per complaint
   - `worst_case_tokens: <a whole number>`, about 38.4 million, and no larger than 39991987
   - `tokens_left_under_cap: 40000000`. Job A counts the cap only (`figures(root, rows, 0)` in
     `cloud/job_a/job_a.py`). Job B checks the ledger's real room, 39,991,987 after round 6's 8,013 tokens, before
     it marks anything used, and refuses if the worst case does not fit
   - `expected_cost_usd: 0.50`, the spec's $0.4919 rounded up to the cent, and well under 5

   Paste the summary's lines to Claude, who checks them too. If anything differs, do not approve.
7. Approve: click **Review deployments**, tick `june-run`, and click **Approve and deploy**.
8. Job B checks the approval and Job A's run, refits the July model with the pinned vocabulary and checks it, marks
   the run used, writes the real row's start marker, and labels the 2,073 complaints through the API and the June
   ledger. Then it scores them and writes two files to its results folder: `v1_june.csv`, one row per complaint with
   IDs, labels, positions and reasons only, and `v1_june.json`, the summary. Its time limit is 3 hours. The spec
   estimates about 70 minutes for the labelling, since the laptop labelled 1,909 complaints in 3,847 seconds, one at
   a time (spec 004, Known limits). Round 6's whole Job B, its refit and 8 calls, took 2 minutes 43 seconds on its
   run page, from your screenshot of 13 November. The time for 2,073 calls in the cloud was not measured, so the
   labelling should fit, but that is not proven.
9. When Job B ends, the workflow posts the result. Its `run` job shows a green tick, with the last log line `Job B
   finished`, or a red cross, with "Job B did not finish, so this job fails after the result was sent". Tell Claude
   which, and Job B's run ID from its run page. If it stopped, its run page shows the exit value's `stop_reason`:
   tell Claude that too.
10. Pause Job A's trigger again.
11. In the Console, note the key's cost again. It may take a while to show.

If a step fails, tell Claude the step and its fixed text or status. Refusals hold fixed text and IDs only.

## If something refuses or stops

The real row has one use, so a wrong click can spend it. After any refusal, stop, or red cross:

- Never click GitHub's **Re-run jobs** or **Re-run all jobs**, Job A's or Job B's **Run now**, or **Repair run**,
  and never upload the zip a second time, until Claude has looked and says which way on. GitHub's re-run gives a
  second attempt, which the workflow refuses before it starts Job B. What a Repair or a Run now would do in this
  run is not tested, so Claude checks it in the code first.
- If the workflow refused before Job B started, a fresh `June approval` run by hand, as in step 5, and a fresh
  approval are the way on, once Claude says so. Once Job B has marked Job A's run used, the way on needs a fresh Job
  A run too, and once it has written the start marker, a further pull request (spec 004, Known limits).
- Databricks retries a failed task on its own, at most 3 times (spec 004, Known limits). Job B's run page shows each
  attempt of its task. If it shows more than one attempt, tell Claude how many and each one's status. A later attempt,
  after the run was marked used, refuses at the markers, so a red cross can come from that refusal after an
  earlier attempt already labelled. A later attempt before that makes Job B's checks again and can go on to label.
  Delete nothing in `voc_results` or `voc_raw`. A retried task of Job A makes the approval refuse its run.
- Tell Claude the step, the fixed text or `stop_reason`, and the run IDs.

## After the run

12. Claude copies the two results files into `results/june/`, as the read-only reader, with
    `uv run --native-tls --locked python scripts/copy_june_results.py <Job B run ID>`, and opens the results pull
    request. It prints only the files' names and the rows' count. You do not open the files in the volume.
13. Keep the results folder, the used markers, the start marker and the receiver's `result` row, as the run's record.
    The spec names no clean-up of the June tables or the June CSV after the real run. Claude asks you before anything
    is deleted.
