# Feature Specification: An untouched June test, run in the cloud with no laptop

**Feature Branch**: `004-june-test-and-baselines`

**Created**: 2026-11-04. Revised three times the same day, after three reviews of #85 and the owner's decisions. Revised again on 5 November, after the fourth review and the owner's decisions of that day.

**Status**: Draft for the owner. Nothing paid runs and no cloud resource is created before the owner approves.

**Input**: The owner's requests of 4 November 2026 (BUILD_LOG.md, 4 November). This spec delivers one full cloud run with no laptop. The owner uploads the test month's file to the Databricks volume. Its arrival starts a Databricks job. A webhook starts an approval workflow. After the owner approves the figures, a second Databricks job labels and scores, inside Databricks. It writes the results to a volume that holds nothing else. Claude copies them into the repo through a draft pull request. The test month is June 2026, never used before. It answers the question `docs/VALIDATION.md` left open: does the 0.9 hybrid rule beat the LLM alone on untouched data? XGBoost and the fine-tuned transformer are not in this spec (owner decisions). XGBoost moves to a later spec 005.

Requirement IDs are `J1`, `J2` and so on. Tests are named `test_J<number>_...`.

## What we know before planning (checked on 4 November 2026)

- **New data has no narratives.** The CFPB's announcement of 14 August 2026: "The CFPB to Cease Discretionary Publication of Complaint Narratives and Visualizations" (consumerfinance.gov newsroom). On 4 November, the current bulk export (its HTTP header gave a last-modified date of 3 November 2026) and the search API's CSV both had 15 of the 16 pinned columns, without "Consumer complaint narrative". Checked by Claude from column names only.
- **The archive.** "Archive of consumer complaints received December 1, 2011 through August 14, 2026 that were previously published in the Consumer Complaint Database", in the CFPB's FOIA reading room. Its page, last modified 14 September 2026, lists 21 zip files at `files.consumerfinance.gov/f/documents/`, one each for March to August 2026. The page states no terms. The search API's metadata says `license: CC0`. The July file name matches our pinned July export's name. Byte identity was not checked.
- **June 2026.** `CCDB_Export_19_June_2026.zip`, checked by the owner with a script that prints names and counts only: 19,624,767 bytes, one CSV of 219,864,163 bytes, the 16 pinned columns in order, 620,794 complaints, 16,820 with a narrative, all received in June 2026.
- **August 2026 is not usable.** The archive's August file is the owner's pinned August export: 667,140 complaints, all received in August, only 1 with a narrative (received 11 August).
- **Databricks Free Edition**, checked by the owner in the owner's workspace:
  - Trigger types offered: Scheduled, File arrival, Table update, Continuous, Model update and Upstream job completion.
  - A Webhook notification destination can be made, with an authentication mode and a URL.
  - A personal access token can be made.
  - From a notebook, `api.anthropic.com` and `api.github.com` were reachable, and so were `github.com` on ports 22 and 443 and `ssh.github.com` on 443. The public app on `azurewebsites.net` was not.
  - A service principal can be added in the workspace's settings, with its own entitlements (consumer, Databricks SQL, workspace and admin access). The owner added `voc-june-runner`, with workspace access only.
  - A job's permissions can be given to a user, a group or a service principal, at four levels: Can View ("to view job run results"), Can Manage Run ("to view, trigger" runs), Can Manage and Is Owner. The `admins` group has Can Manage on every job, inherited.
  - The sidebar has Experiments, Models and Serving.
  - Its documented limits (last updated 18 October 2026): serverless only, one 2X-Small SQL warehouse, at most 5 job tasks at a time, a daily compute quota with no published numbers, outbound internet only to "a limited set of trusted domains", and accounts that are inactive for long may be deleted.
- **Databricks webhooks and tokens.** A job's webhook payload has `event_type` (such as `jobs.on_success`), `run.run_id` and the job's ID, sent with HTTP Basic sign-in or OAuth, with no signature ("Add notifications on a job"). The `jobs` scope covers starting a job and reading a run. Unused tokens are revoked after 90 days ("personal access tokens", last updated 7 October 2026).
- **Spend limits.** The Claude Console sets spend limits per organization and per workspace, not per key, and the default workspace cannot have one. A key can be made inside one workspace. A limit the owner sets stops requests with HTTP 400 ("You have reached your specified workspace API usage limits"). Responses carry an `anthropic-workspace-id` header (platform.claude.com).
- **GitHub.** On a public repo, Environments with required reviewers and main-only branch rules are available, and an environment's secrets reach only jobs that name it. `workflow_dispatch` needs a fine-grained token with "Actions" write. `repository_dispatch` and writing files or commits need "Contents" write ("Permissions required for fine-grained personal access tokens"). The repo is public, so Actions logs are public.
- **`main` is protected.** An active ruleset on the default branch, with no bypass actors, blocks deletion and force pushes, and requires a pull request and the checks `tests`, `repo-checks` and `secret-scan` (`gh api`, 4 November 2026). So nothing can push to `main` directly. But the pull request rule needs 0 approvals, and merging a pull request (`PUT /pulls/{n}/merge`, `POST /merges`) is listed under "Contents" write. So a "Contents" token could merge a ready pull request that passed CI. A deploy key has no API access. But a push with it runs `ci.yml` on the pushed commit (`push` on every branch), with the repo secret `NAMES_DENYLIST`, and the docs do not say whether a deploy key can push a changed workflow (fourth review). So this spec uses no GitHub key (J13). The repo's default workflow token is read-only, and Actions cannot approve pull requests (`gh api .../actions/permissions/workflow`, 5 November 2026). That default is only the starting point: a workflow file can add write rights in its own `permissions` block ("Workflow syntax for GitHub Actions"). With 0 required approvals, a workflow that asks for "Contents" write could merge a ready pull request. Only someone who can push a workflow change can do that, and with no outside key (J13), that is the owner's own account.
- **Databricks Unity Catalog and service principals** (Databricks docs, read on 5 November 2026). Reading or listing files in one volume needs USE CATALOG on its catalog, USE SCHEMA on its schema and READ VOLUME on the volume. Workspace users get USE CATALOG on the workspace catalog by default, and USE SCHEMA and create rights on its `default` schema, but no READ VOLUME or SELECT. Workspace admins can make an OAuth secret for a service principal in the workspace's settings, so the account console, which Free Edition lacks, is not needed. Whether the Files API needs the workspace-access entitlement is not documented. Pull request 5 tests it.
- **Azure Functions Flex Consumption.** "The lowest maximum scale is currently `1`". The limit applies "to each independently-scaling function group rather than to the app's combined instances" (learn.microsoft.com, 15 September 2026).
- **The model's training data.** The README and `docs/LIMITS.md` say the July complaints cannot be in the model's training data, because it ends in June 2026. That does not hold for June. June narratives could be published from early June, after the company's response or 15 days, so some may have been public within the month the training data ends.

## Rules for every piece

- **J1. June is scored once, after everything is frozen.**
  - Every setting, the hybrid rule, the June sample, the scoring code and the claims are committed before any June label is scored.
  - Then one entry is added to `runs/JUNE_RUNS.md`, which only grows, in its own pull request after the last code change. It names the June list's hash and a hash of the frozen code and configuration, computed by a committed script over `src/`, `config/`, `dbt/`, `splits/`, `pyproject.toml`, `uv.lock`, the job definitions, the approval workflow and the script itself. Job B runs the code of the commit that merged that entry.
  - Job B refuses to score unless the entry's two hashes match what it is about to run.
  - Before its first model call, Job B writes a start marker for that entry in the volume, with a create that fails if the marker exists. It refuses if a marker exists, unless a later entry in `runs/JUNE_RUNS.md` names it as a reproduction, a resume or a second run, with the reason.
  - The dry run (pull request 9) uses a synthetic sample, with its own list hash and its own entry marked synthetic. The real June list matches no synthetic entry.
  - The laptop path refuses to label or score June at all. `voc label` and `voc evaluate` keep working for July.
  - A later run is logged with its reason, and is a reproduction (the same recorded answers replayed) or a second run, never a quiet rescoring. A run stopped by the spend limit or the quota is not scored. It resumes by replay, under a later entry of the kind "resume", and any new spend needs a new approval of the printed figures.
- **J2. The July test set stays sealed.** No June step reads it.
- **J3. The same rules as before.** No complaint text in git (B19, B21). Every live call is capped, recorded and approved first (V9). Results that do not favour the LLM are reported the same way. Agreement with the consumer's choice is called that, never accuracy.
- **J4. Complaint text stays in Databricks.** June and July training text, the recordings, the ledger and the fitted TF-IDF + LR model stay in the volume. The text leaves Databricks only to the Anthropic API, in tool-less calls. GitHub receives only numbers (the estimate). The results files (J11) reach the repo only through Claude's copy and a draft pull request. No runner, artifact, cache, log or model hub ever holds complaint text.
- **J5. What a job may print.** The repo is public, so its Actions logs are public. Every job and workflow prints only IDs, labels, reasons, positions, decisions and counts, through B21's shared error handler, with no traceback, no debug or verbose logging and the SDK's debug logging off. A test runs each entry point on hostile synthetic text and checks the output. Job A is a notebook task that ends with `dbutils.notebook.exit` and a JSON of fixed keys (counts and the worst case). A workflow reads only those keys from the run's output, and never prints `error`, `error_trace`, `logs`, `state_message` or a termination message.

## The constitution and the data rules

The constitution allowed "the CFPB Consumer Complaint Database, July 2026 export, for all labelling and evaluation" (2.0.1), B16 built samples only from the pinned July file, and B25 sized them from the July pool. Owner decision of 4 November: a MINOR amendment to 2.1.0 allows one archive month, June 2026, for this spec's one untouched test only, with its one primary claim. It also adds what this run uses to the Stack constraint: Databricks jobs, the volume and the file-arrival trigger as a used part of the run, not an optional stretch, and an Azure Function with its storage queue, table and Key Vault. It also names where this run's secrets live, which principle IV otherwise limits to environment variables and `.env`: a Databricks secret scope, GitHub environment secrets and an Azure Key Vault. And it says the Databricks Assistant, an agent that can read tables, is never used on June or July data. B16, B25, CLAUDE.md and `docs/TEST_LIST.md` change to match. The July results, the July claim and `docs/VALIDATION.md` stay as they are. June gets its own new section.

## The pieces

- **J6. The June sample.**
  - `voc sample june`, on the laptop, as for July. It reads the pinned June CSV, the one inside the zip, and pins it in `config/data_files.toml`, with its folder in the variable `VOC_JUNE_DATA_DIR`.
  - Copies within June are removed, and so is any June complaint whose narrative copies one in July's training or development sets (owner decision, the July test set stays sealed).
  - Every June Product must be in `config/labels.toml` (B24), or the sample refuses.
  - Its size by Cochran's formula (B25) at e = 2 points, with N the June pool after copies are removed: about 2,080 if about 1,270 copies go, and 2,102 if none do. The exact n comes from the June count. Split across Products in proportion.
  - Frozen with its hashes in `splits/june/`. The read guard protects `VOC_JUNE_DATA_DIR`, and the merge check drops it, as for July and August.
- **J7. The June scoring and its claims.**
  - On the June sample, the LLM (claude-haiku-5-5, prompt v1, unchanged) labels every complaint once. TF-IDF + LR is refit from July's training rows only, with its settings unchanged. The refit model must reproduce the committed July development labels in `results/eval/v1_dev.csv` before it labels June.
  - The hybrid is the rule fixed on 2 November, unchanged: TF-IDF + LR answers at a top confidence of 0.9 or more, else the LLM. A held-back LLM label counts as wrong.
  - Scores are re-weighted by June's own pool after copies are removed, so they are not directly comparable with July's, whose product mix differs. Intervals come from a paired bootstrap of 2,000 draws within each Product, seed 0.
  - **The one primary claim, fixed now:** the hybrid against the LLM alone, both at full coverage, as V6 scores it. The hybrid beats the LLM if the 95% interval of the point difference is wholly above zero. It does not beat it if the point difference is zero or below. Otherwise it is inconclusive.
  - **One secondary comparison, with its interval and no verdict:** the LLM against TF-IDF + LR at the same coverage, as B10 defines it.
  - **Cost per extra correct label:** against TF-IDF + LR at the same coverage, as V6's headline, with the full-coverage view next to it.
- **J8. The full cloud run.**
  1. Last of all the owner's steps, the owner uploads the June zip to `voc_raw/incoming/`.
  2. **Job A** starts on its arrival (file-arrival trigger, limited to `.zip` files in that folder). It unzips the file into `voc_raw/june/`, outside the trigger folder, checks the CSV against its pin, runs the same dbt models as the July build (with June's own row count in the data tests), selects the frozen sample's IDs and checks their hashes against `splits/june/`. It computes the numbers for the approval: the call count, the expected cost, the worst-case tokens and the tokens left under the cap. It makes no model call and prints counts only.
  3. Job A's success webhook goes to the receiver (J9). The receiver starts the approval workflow (J10) with Job A's run ID.
  4. The approval workflow reads Job A's numbers from its run output and prints them. Its second job waits for the owner's approval in the `june-run` environment, then starts **Job B** with `run-now`, passing Job A's run ID and its own GitHub run ID.
  5. **Job B** (J11) labels and scores inside Databricks and writes the results files to the results volume `voc_results`.
  6. The approval workflow follows Job B through the jobs API until it ends, then posts a signed result message to the receiver.
  7. Claude copies the results files from `voc_results` with the reader's credential (J13), on a branch `results/june-<run ID>`, and opens a draft pull request, as usual (owner decisions). CI's checks (the secret scan, the names check, the size limit and the CFPB header check) run on the copied files before anything reaches `main`.
  - **The webhook fallback:** if the notification destination's test shows that Databricks' webhooks cannot reach the receiver, the owner starts the approval workflow by hand after the upload, with no run ID. It then finds Job A's first run that started after the upload through the jobs API, waits for it to end, and goes on the same way. Job B is followed the same way in both cases.
- **J9. The receiver.** A small Azure Function, apart from the public app, which stays read-only.
  - Two functions: an HTTP function that takes the calls, and a queue function that does the work. The maximum instance count is 1, the lowest allowed, which applies to each of the two, so at most 2 instances run. Instance size 512 MB, with no always-ready instance.
  - The HTTP function checks the caller before it replies. Databricks' webhook carries HTTP Basic sign-in, compared in constant time. The approval workflow's result message carries an HMAC-SHA256 over the timestamp, a dot and the raw body, with a shared secret, compared in constant time, and refused if the timestamp is more than 5 minutes old or more than 1 minute ahead. A refused call gets 401 and is not queued.
  - An accepted call gets 202 at once and goes on the queue.
  - Duplicates: each event's key (Databricks: the job run ID and event type, the result message: the GitHub run ID and run attempt) is written to a table with an insert that fails if the key exists. A repeat is acknowledged and dropped. Keys are kept for 30 days.
  - The queue function asks Databricks itself whether that run really succeeded, for the June job, with the robot account's credential (J13), which can view Job A's and Job B's runs, and start or cancel Job B. Then it starts the approval workflow. Before it does, it checks GitHub for a run of that workflow whose name (`run-name`, shown as `display_title`) holds the same Databricks run ID, so a retried dispatch cannot start a second one.
  - The signed result message is stored in the table with its status and counts, and logged with IDs and counts only. It starts nothing.
  - Failures: the queue retries by its visibility timeout, at most 5 tries in all, then moves the message to the failure queue, logged with IDs and counts only.
  - Its secrets are in an Azure Key Vault, read by the Function's managed identity. Its app settings hold only Key Vault references. No secret is in code, a log or the repo. It logs IDs, event types, statuses and counts only. Application Insights is not turned on.
  - Tests for each: a bad sign-in, a bad signature, an old or future timestamp, a duplicate, the 202 reply before the work, a dispatch already made, and a retry that ends in the failure queue.
- **J10. The approval workflow.**
  - Started only by `workflow_dispatch` on `main`, from the receiver or by the owner. Claude never starts it.
  - Its one input is the Databricks run ID, optional for the fallback, checked as a whole number or empty and passed to commands through `env:`, never written into a `run:` script. Its `run-name` holds that ID.
  - First job, in the environment `june-figures` (main only, no reviewer): it holds the robot account's credential, reads Job A's numbers and prints them.
  - Second job, in the protected environment `june-run` (main only, the owner as required reviewer, "prevent self-review" off so the owner can approve a run the owner's dispatch started): it holds the robot account's credential and the HMAC secret, starts Job B, follows it, and posts the signed result message.
  - Permissions per job, read-only repo access, one run at a time (a `concurrency` group), and every action pinned by its commit SHA.
- **J11. Job B.**
  - It runs the repo's code at the frozen commit (J1). It first checks the `runs/JUNE_RUNS.md` entry's hashes and the start marker, the June sample's IDs and hashes, and July's training IDs and hashes against `splits/`. It reads only July's training rows from the pinned July export already in the volume (T021b), through B16's loader, never a test row.
  - Job B is one task, so `run-now`'s `only` cannot skip a check. Every check runs in that task before the first model call. It runs as the owner, never as the robot. Its maximum concurrent runs is 1.
  - It refuses unless the GitHub run it was given is the approval for this Job A run, checked through GitHub's API (the repo is public, so this needs no token): the run's workflow path is the approval workflow, its event is `workflow_dispatch`, its branch is `main`, its commit is the frozen commit (J1), its `display_title` holds the given Job A run ID, and its approvals list `approved` for `june-run` by the owner's account. It writes the GitHub run ID and attempt to the volume as used, and refuses one already used. So the robot account's right to start Job B is not enough to start a scoring, and an old approval cannot start a new one. GitHub allows 60 calls an hour without a token, per address, and serverless addresses are shared, so the check retries a few times and then refuses.
  - It recomputes Job A's figures from Job A's run ID and refuses if they exceed what was approved. Its only parameters are the two run IDs, checked as whole numbers.
  - Its API key is in a Databricks secret scope, made inside the cloud workspace (J12). It refuses unless the API's `anthropic-workspace-id` header names that workspace.
  - It refits TF-IDF + LR, checks it against the July development labels, labels the sample with the LLM, scores as J7, and writes the recordings to `voc_raw/recordings_june/` and the ledger to `voc_raw/ledger_june/`. The ledger's path and its cap come from the frozen commit's `config/budget.toml`, read from the job's Git source, because serverless compute may have no git command to check `origin/main`.
  - It writes the results files to `voc_results/june-<Job B run ID>/`, after checking them against B19's columns, the size limit and the CFPB header check. It pushes nothing and holds no GitHub credential. The results files, and nothing else:
    - `v1_june.csv`: one row per sampled complaint, with B19's columns only: `complaint_id`, `split` (`june`), `prompt_version`, `proposed_label`, `quote_start`, `quote_end`, `decision`, `reason`, `accepted_label`, `tfidf_label`, `tfidf_confidence` and `recording_key`.
    - `v1_june.json`: the run summary, with the keys of `results/eval/v1_test.json` and the hybrid's: counts, confusion tables (counts per pair of Products), scores, intervals, the primary verdict and the secondary comparison (J7), costs, tokens, the June list's hash, the run entry's two hashes, the two Databricks run IDs, the GitHub run ID and the run time.
    - Neither file holds narrative text, a quote, the consumer's recorded Product or any other field of a complaint but its ID. The labels and confidences are the models' outputs, from the fixed label list. Each reason is from the fixed list of reasons. Each recording key is a SHA-256 of the backend, model, settings and prompt (B7). It cannot be turned back into text, but someone who already holds a complaint's text could confirm that it matches, as with July's committed files.
    - The per-complaint rows are needed outside Databricks for B19: with them and the public archive file, anyone can recompute every June figure, including the bootstrap and the hybrid's answer (TF-IDF + LR's label when its confidence is 0.9 or more, else the accepted label).
  - The copy script, `scripts/copy_june_results.py`, run by Claude on the laptop, reads only those two names under `voc_results`, refuses any other file, checks the columns, the label and reason lists, the IDs against `splits/june/`, the size limit and the CFPB header check again, and writes them to `results/june/`. The results pull request holds data only, so it has no failing-test commit, the one exception to tests first.
- **J12. The spend cap.**
  - A separate workspace in the Claude Console, made by the owner, for cloud runs only, with a key made inside it and a monthly spend limit of $5 (owner decision).
  - Job B keeps its own ledger with a cap of 40 million tokens (owner decision), above the run's worst case of about 38.4 million (the July test run's 35,233,329 for 1,909 calls, scaled to about 2,080). As for July, it refuses unless the cap covers the whole run's worst case, retries included. The rule of 29 October stays whole.
  - The $5 limit is the hard stop on real spend. The expected spend is about $0.49.
  - A 400 "usage limits" answer stops the run with no retry. A 429 is retried only when it has a `retry-after` header.
- **J13. Identities, secrets and the trade-offs** (owner decisions: option A of the third review, and on 5 November the results volume in place of option D's deploy key).
  - **The robot account** `voc-june-runner`, a Databricks service principal, never in the `admins` group, with workspace access only. On Job A it has Can View. On Job B it has Can Manage Run. It runs no job: Job A and Job B run as the owner. How it gets its own credential on Free Edition (an OAuth secret, which the docs say a workspace admin can make) is checked in pull request 5. If it cannot get one, the owner starts Job B by hand in Databricks, with the approved GitHub run ID as its parameter, and follows it there, and no Databricks credential leaves Databricks.
  - **The reader account** `voc-results-reader`, a second service principal, never in the `admins` group and in no job. Its only grants are USE CATALOG on the catalog, USE SCHEMA on the results schema and READ VOLUME on `voc_results`, which is in its own schema and holds no complaint data. Its OAuth secret is in the owner's `.env`, read only by the copy script (J11).
  - **Databricks secret scope:** the API key of the cloud workspace, and nothing else. Only the owner has rights on it.
  - **GitHub:** the `june-figures` and `june-run` environments hold the robot's credential, and `june-run` also the HMAC secret. No deploy key, "Contents" token or other GitHub write credential exists for this run, on any repo.
  - **The receiver's Key Vault:** the Basic sign-in details, the robot's credential, a GitHub fine-grained token for this repo only with "Actions" read and write and nothing else, and the HMAC secret.
  - **What each can do, plainly.**
    - The robot's credential can read Job A's and Job B's runs, and start or cancel Job B. A Job B it starts without this run's approval refuses before any call (J11). With workspace access, it could also make and run its own notebooks and jobs on serverless compute, with outbound internet, but only with its own data rights. So pull request 5 checks, as the owner, that it has no READ VOLUME on `voc_raw`, no SELECT on the June or July tables and no rights on the secret scope, and tests whether it still works without the workspace-access entitlement. If it does, that entitlement is removed.
    - The reader's credential can read the results files, which will be public anyway, and nothing else. Pull request 5 checks its grants the same way and tests the same entitlement. Its check script, run with its credential, expects a refusal when it lists `voc_raw`, reads the June or July tables' metadata or lists the secret scope. Each of those calls returns names or metadata at most, never complaint text, so the test itself cannot leak.
    - "Actions" write can start, re-run and cancel this repo's workflows, including `scheduled.yml`, delete their runs and logs, and turn workflows off.
  - **The trade-offs, decided.** Before, the plan used the owner's own `jobs` token in GitHub and the receiver. The owner is a workspace admin, so that token could run any code as the owner and read the complaint text and the secrets. The robot account removes that. Next, Job B pushed with a deploy key, but a push with it could run code in Actions and reach `NAMES_DENYLIST` (fourth review). The results volume removes every GitHub write credential, and a leaked reader secret exposes only the results. The cost is a second service principal, one more volume and Claude's copy step.
  - **The fallback, if pull request 5's checks fail** (owner decision of 5 November): a private repo `voc-demo-results`, with Actions off and no secrets, and a deploy key on that repo only. Job B pushes the two files there, and Claude copies them into this repo the same way. The key never exists on this repo.
  - Every credential lasts 30 days where it can expire, enough for the run and a rerun, and is revoked after.
- **J14. Claude's access.** Claude's `gh` signs in as the owner, who is `june-run`'s required reviewer. So the read guard also denies:
  - Databricks CLI and SQL commands that name the volume `voc_raw` or the June tables
  - all Actions run logs (`gh run view --log`, `gh run download`, `gh api .../logs`), because a run ID does not show its workflow
  - starting the approval workflow (`gh workflow run` and the dispatch API), re-running or cancelling a run (`gh run rerun`, `gh run cancel` and their API forms), approving a deployment (`gh api .../pending_deployments`), and the environments and secrets APIs
  - merging through the API (`.../pulls/<n>/merge` and `.../merges`), which the deny rules on `gh pr merge` do not cover today
  - CLAUDE.md says Claude never approves a deployment. Claude reads from Databricks only the two results files, through the copy script.
- **J15. A backup.** Free Edition may delete an inactive account and may shut compute down for a day. The owner keeps the June file and, after the run, a copy of the June recordings, on the laptop's backup, as for the exports.

## Costs

| Item | One-off | Monthly |
|---|---|---|
| LLM labels for the June sample, about 2,080 complaints at the July test run's $0.2373 per 1,000 | about $0.49 expected. The worst case the ledger reserves, about 38.4 million tokens, would be about $9, so the $5 limit is the real bound. | none |
| TF-IDF + LR, in Job B | $0 | none |
| Databricks Free Edition, GitHub Actions on a public repo | $0 | $0 |
| The receiver: Azure Functions Flex Consumption, Australia East | $0 (free grant: 250,000 runs and 100,000 GB-seconds a month) | $0 at this use |
| Its storage account (queue, failure queue, key table, function code), Hot LRS | none | under $0.10 (data $0.02 per GB, operations $0.0044 to $0.055 per 10,000, Azure Retail Prices API, 4 November 2026) |
| Its Key Vault, Standard | none | under $0.01 ($0.03 per 10,000 operations, Australia East, same source) |
| Logs | none | $0: Application Insights is not turned on |

The owner approves the Azure Function, its storage account and its Key Vault before they are made.

## Pull requests, in order

1. This spec, the constitution amendment to 2.1.0, B16, B25, CLAUDE.md, the README's "monthly feed" lines, and the test list.
2. The read guard and the deny rules: `VOC_JUNE_DATA_DIR` and J14.
3. J6 and J1's laptop refusal: the June pin, its variable, and the frozen June sample (the owner runs `voc sample june`).
4. J7 and J1: the frozen claims, the hash script, `runs/JUNE_RUNS.md` and the June scoring code, on synthetic data.
5. J8's Job A: its definition and code, on synthetic data, with J5's output test. The owner's checks of the robot and the reader (J13), and whether the robot can read Job A's exit value with Can View alone. If the reader's checks fail, the owner decides on the fallback (J13).
6. J11 and J12: Job B, on the mock backend, and the copy script, on synthetic files.
7. J9: the receiver, with its tests. Then the owner approves and creates it.
8. J10: the approval workflow, with its tests on the YAML.
9. A dry run of the whole chain on synthetic data with the mock backend, with its synthetic entry (J1). Stop point: the owner decides whether to run June.
10. The `runs/JUNE_RUNS.md` entry for June, in its own pull request, after the last code change.
11. The June run itself, after the owner approves the printed figures. Then a new June section in `docs/VALIDATION.md` and the README, as the owner decides.

## Owner's setup steps, in order, each when its pull request is ready

- Delete the Databricks test jobs made on 4 November.
- **Claude Console:** make the cloud workspace, a key inside it and its $5 limit.
- **Databricks:** confirm that a job can run the repo's code (a Git folder or Git source) and that a secret scope can be made. Make the secret scope with the API key. Make the results schema and the `voc_results` volume. Give `voc-june-runner` Can View on Job A and Can Manage Run on Job B, and its credential. Add `voc-results-reader` with its three grants, and put its credential in `.env`. Run the checks of J13. Set up Job A, Job B and the webhook destination with its Basic sign-in details. Never use the Databricks Assistant on June or July data.
- **GitHub:** make the `june-figures` environment (main only, no reviewer) and the `june-run` environment (main only, the owner as required reviewer, "prevent self-review" off), with their secrets. Make the "Actions" fine-grained token. The owner's existing Databricks token, scope `sql`, expires on 6 November, so new credentials are made when the run is near.
- **Azure:** approve and create the Function (maximum instance count 1, 512 MB), its storage account and its Key Vault, and put the secrets in the Key Vault. Use the destination's test to check that Databricks can reach the receiver.
- **Laptop:** set `VOC_JUNE_DATA_DIR`, run `voc sample june`, and keep the backup.
- **Last:** upload the June zip, then approve the run when its figures print.
- **Afterwards:** revoke the tokens and secrets, and remove the robot and reader accounts, the Function, its storage and Key Vault, and the workspace limit, if the owner wishes.

## Not in scope

- An event-driven pipeline on new months, and monitoring. Moved to a separate project.
- XGBoost, moved to spec 005 (an MLOps loop on Databricks), and the fine-tuned transformer, dropped.
- Any new score on the July test set.
- Changing prompt v1 or the 0.9 rule.

## Known limits

- June comes before July, so it is untouched but not a test of the future.
- The training-data claim in the README and `docs/LIMITS.md` does not hold for June. Some June narratives may be in the LLM's training data. That would favour the LLM, so it would bias the primary claim towards the LLM alone and against the hybrid, and the secondary comparison towards the LLM. The June section says so.
- June's narrative share is 2.7% (16,820 of 620,794) against July's 1.5% (10,002 of 672,036), which suggests a different publication lag and mix.
- The answer key is still the consumer's choice, which V2 shows is noisy.
- Databricks does not sign its webhooks, so the receiver confirms each call by asking Databricks.
- Job B needs PyPI and GitHub's API from Databricks. GitHub's API was reachable on 4 November. PyPI is checked in pull request 5.
- How the robot and the reader get a credential on Free Edition is documented but not yet tried. If the robot cannot, the owner starts Job B by hand. If the reader cannot, the fallback repo is used (J13).
- Free Edition's daily quota has no published numbers. If a run is cut, it resumes by replay.
