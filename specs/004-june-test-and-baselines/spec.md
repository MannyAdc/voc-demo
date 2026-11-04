# Feature Specification: An untouched June test, run in the cloud with no laptop

**Feature Branch**: `004-june-test-and-baselines`

**Created**: 2026-11-04. Revised twice the same day, after two reviews of #85 and the owner's decisions.

**Status**: Draft for the owner. Nothing paid runs and no cloud resource is created before the owner approves.

**Input**: The owner's requests of 4 November 2026 (BUILD_LOG.md, 4 November). This spec delivers one full cloud run with no laptop. The owner uploads the test month's file to the Databricks volume. Its arrival starts a Databricks job. A webhook starts an approval workflow. After the owner approves the figures, a second Databricks job labels and scores, inside Databricks. The results come back as a branch and a pull request. The test month is June 2026, never used before. It answers the question `docs/VALIDATION.md` left open: does the 0.9 hybrid rule beat the LLM alone on untouched data? XGBoost and the fine-tuned transformer are not in this spec (owner decisions). XGBoost moves to a later spec 005.

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
  - From a notebook, `api.anthropic.com` and `api.github.com` were reachable. The public app on `azurewebsites.net` was not.
  - The sidebar has Experiments, Models and Serving.
  - Its documented limits (last updated 18 October 2026): serverless only, one 2X-Small SQL warehouse, at most 5 job tasks at a time, a daily compute quota with no published numbers, outbound internet only to "a limited set of trusted domains", and accounts that are inactive for long may be deleted.
- **Databricks webhooks and tokens.** A job's webhook payload has `event_type` (such as `jobs.on_success`), `run.run_id` and the job's ID, sent with HTTP Basic sign-in or OAuth, with no signature ("Add notifications on a job"). The `jobs` scope covers starting a job and reading a run. Unused tokens are revoked after 90 days ("personal access tokens", last updated 7 October 2026).
- **Spend limits.** The Claude Console sets spend limits per organization and per workspace, not per key, and the default workspace cannot have one. A key can be made inside one workspace. A limit the owner sets stops requests with HTTP 400 ("You have reached your specified workspace API usage limits"). Responses carry an `anthropic-workspace-id` header (platform.claude.com).
- **GitHub.** On a public repo, Environments with required reviewers and main-only branch rules are available, and an environment's secrets reach only jobs that name it. `workflow_dispatch` needs a fine-grained token with "Actions" write. `repository_dispatch` and writing files or commits need "Contents" write ("Permissions required for fine-grained personal access tokens"). The repo is public, so Actions logs are public.
- **`main` is protected.** An active ruleset on the default branch, with no bypass actors, blocks deletion and force pushes, and requires a pull request and the checks `tests`, `repo-checks` and `secret-scan` (`gh api`, 4 November 2026). So no token can push to `main`.
- **Azure Functions Flex Consumption.** "The lowest maximum scale is currently `1`". The limit applies "to each independently-scaling function group rather than to the app's combined instances" (learn.microsoft.com, 15 September 2026).
- **The model's training data.** The README and `docs/LIMITS.md` say the July complaints cannot be in the model's training data, because it ends in June 2026. That does not hold for June. June narratives could be published from early June, after the company's response or 15 days, so some may have been public within the month the training data ends.

## Rules for every piece

- **J1. June is scored once, after everything is frozen.**
  - Every setting, the hybrid rule, the June sample, the scoring code and the claims are committed before any June label is scored.
  - Then one entry is added to `runs/JUNE_RUNS.md`, which only grows. It names the June list's hash and a hash of the frozen code and configuration, computed by a committed script over `src/`, `config/` and the job definitions.
  - Job B refuses to score unless the entry's two hashes match what it is about to run.
  - The laptop path refuses to score June at all. `voc label` and `voc evaluate` keep working for July.
  - A later run is logged with its reason, and is a reproduction (the same recorded answers replayed) or a second run, never a quiet rescoring. A run stopped by the spend limit or the quota is not scored, and resumes by replay.
- **J2. The July test set stays sealed.** No June step reads it.
- **J3. The same rules as before.** No complaint text in git (B19, B21). Every live call is capped, recorded and approved first (V9). Results that do not favour the LLM are reported the same way. Agreement with the consumer's choice is called that, never accuracy.
- **J4. Complaint text stays in Databricks.** June and July training text, the recordings, the ledger and the fitted TF-IDF + LR model stay in the volume. The text leaves Databricks only to the Anthropic API, in tool-less calls. GitHub receives only numbers (the estimate) and the results files (IDs, labels, positions, decisions, reasons and counts). No runner, artifact, cache, log or model hub ever holds complaint text.
- **J5. What a job may print.** The repo is public, so its Actions logs are public. Every job and workflow prints only IDs, labels, reasons, positions, decisions and counts, through B21's shared error handler, with no traceback, no debug or verbose logging and the SDK's debug logging off. A test runs each entry point on hostile synthetic text and checks the output.

## The constitution and the data rules

The constitution allowed "the CFPB Consumer Complaint Database, July 2026 export, for all labelling and evaluation" (2.0.1), B16 built samples only from the pinned July file, and B25 sized them from the July pool. Owner decision of 4 November: a MINOR amendment to 2.1.0 allows one archive month, June 2026, for this spec's one untouched test only, with its one primary claim. It also adds what this run uses to the Stack constraint: Databricks jobs, the volume and the file-arrival trigger as a used part of the run, not an optional stretch, and an Azure Function with its storage queue, table and Key Vault. B16, B25, CLAUDE.md and `docs/TEST_LIST.md` change to match. The July results, the July claim and `docs/VALIDATION.md` stay as they are. June gets its own new section.

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
  2. **Job A** starts on its arrival (file-arrival trigger). It unzips the file in the volume, checks the CSV against its pin, runs the same dbt models as the July build (with June's own row count in the data tests), selects the frozen sample's IDs and checks their hashes against `splits/june/`. It computes the numbers for the approval: the call count, the expected cost and the worst-case tokens. It makes no model call and prints counts only.
  3. Job A's success webhook goes to the receiver (J9). The receiver starts the approval workflow (J10) with Job A's run ID.
  4. The approval workflow reads Job A's numbers from its run output and prints them. Its second job waits for the owner's approval in the `june-run` environment, then starts **Job B** with `run-now`.
  5. **Job B** (J11) labels and scores inside Databricks, writes the results files, and pushes them to a results branch.
  6. The approval workflow follows Job B through the jobs API until it ends, then posts a signed result message to the receiver. Claude opens the draft pull request from the results branch, as usual (owner decision).
  - **The webhook fallback:** if the notification destination's test shows that Databricks' webhooks cannot reach the receiver, the owner starts the approval workflow by hand after the upload. It then finds Job A's latest run through the jobs API, waits for it to end, and goes on the same way. Job B is followed the same way in both cases.
- **J9. The receiver.** A small Azure Function, apart from the public app, which stays read-only.
  - Two functions: an HTTP function that takes the calls, and a queue function that does the work. The maximum instance count is 1, the lowest allowed, which applies to each of the two, so at most 2 instances run. Instance size 512 MB, with no always-ready instance.
  - The HTTP function checks the caller before it replies. Databricks' webhook carries HTTP Basic sign-in, compared in constant time. The approval workflow's result message carries an HMAC-SHA256 over the timestamp, a dot and the raw body, with a shared secret, compared in constant time, and refused if the timestamp is more than 5 minutes old or more than 1 minute ahead. A refused call gets 401 and is not queued.
  - An accepted call gets 202 at once and goes on the queue.
  - Duplicates: each event's key (Databricks: the job run ID and event type, the result message: the GitHub run ID and run attempt) is written to a table with an insert that fails if the key exists. A repeat is acknowledged and dropped. Keys are kept for 30 days.
  - The queue function asks Databricks itself whether that run really succeeded, for the June job, with a token of `jobs` scope. Then it starts the approval workflow. Before it does, it checks GitHub for a run of that workflow with the same Databricks run ID, so a retried dispatch cannot start a second one.
  - Failures: the queue retries by its visibility timeout, at most 5 tries in all, then moves the message to the failure queue, logged with IDs and counts only.
  - Its secrets are in an Azure Key Vault, read by the Function's managed identity. Its app settings hold only Key Vault references. No secret is in code, a log or the repo. It logs IDs, event types, statuses and counts only. Application Insights is not turned on.
  - Tests for each: a bad sign-in, a bad signature, an old or future timestamp, a duplicate, the 202 reply before the work, a dispatch already made, and a retry that ends in the failure queue.
- **J10. The approval workflow.**
  - Started only by `workflow_dispatch` on `main`, from the receiver or by the owner. Claude never starts it.
  - Its inputs are the Databricks run ID, checked as a whole number and passed to commands through `env:`, never written into a `run:` script.
  - First job, with no secrets: it reads and prints Job A's numbers.
  - Second job, in the protected environment `june-run` (main only, the owner as required reviewer, "prevent self-review" off so the owner can approve a run the owner's dispatch started): it holds a Databricks token of `jobs` scope and the HMAC secret, starts Job B, follows it, and posts the signed result message.
  - Permissions per job, read-only repo access, one run at a time (a `concurrency` group), and every action pinned by its commit SHA.
- **J11. Job B.**
  - It runs the repo's code at the frozen commit. It first checks the `runs/JUNE_RUNS.md` entry's hashes (J1), the June sample's IDs and hashes, and July's training IDs and hashes against `splits/`.
  - Its API key is in a Databricks secret scope, made inside the cloud workspace (J12). It refuses unless the API's `anthropic-workspace-id` header names that workspace.
  - It refits TF-IDF + LR, checks it against the July development labels, labels the sample with the LLM, scores as J7, and writes the recordings to `voc_raw/recordings_june/` and the ledger to `voc_raw/ledger_june/`.
  - It writes the results files (IDs, labels, positions, decisions, reasons and counts only) and pushes them to a branch `results/june-<run ID>` through GitHub's API, with a fine-grained token (J13). The commit's author is the owner's GitHub name with the noreply email, as CLAUDE.md asks.
- **J12. The spend cap.**
  - A separate workspace in the Claude Console, made by the owner, for cloud runs only, with a key made inside it and a monthly spend limit of $5 (owner decision).
  - Job B keeps its own ledger with a cap of 40 million tokens (owner decision), above the run's worst case of about 38.4 million (the July test run's 35,233,329 for 1,909 calls, scaled to about 2,080). As for July, it refuses unless the cap covers the whole run's worst case, retries included. The rule of 29 October stays whole.
  - The $5 limit is the hard stop on real spend. The expected spend is about $0.49.
  - A 400 "usage limits" answer stops the run with no retry. A 429 is retried only when it has a `retry-after` header.
- **J13. Tokens, secrets and the trade-off.**
  - **Databricks secret scope:** the API key of the cloud workspace, and a GitHub fine-grained token for this repo only, with "Contents" read and write and nothing else (GitHub adds "Metadata" read to every fine-grained token). It can write files, commits and branches anywhere but `main`, which the ruleset protects. It cannot open a pull request, merge, read secrets or start a workflow.
  - **The `june-run` environment:** a Databricks token of `jobs` scope, and the HMAC secret.
  - **The receiver's Key Vault:** the Basic sign-in details, a Databricks token of `jobs` scope, a GitHub fine-grained token for this repo only with "Actions" read and write and nothing else, and the HMAC secret.
  - **What the tokens can do, plainly.** The `jobs` scope can read, start, edit and delete any job in the workspace, including Job B, so a stolen one can spend, within the $5 limit and the ledger cap. "Actions" write can start, re-run and cancel this repo's workflows, including `scheduled.yml`, delete their runs and logs, and turn workflows off. "Contents" write can push to any branch but `main`.
  - **The trade-off, decided:** the other design had a GitHub workflow copy the results from the volume, with a Databricks token that could also read the complaint text, because Databricks tokens are limited by scope, not by folder. With Job B pushing the branch itself, GitHub holds no token that can read the volume, and the GitHub token in Databricks cannot touch `main`. Complaint text is what this project protects most, so this design has the narrower risk.
  - Each token lasts 30 days, enough for the run and a rerun, and is revoked after. The owner's existing token, scope `sql`, expires on 6 November, so new ones are made when the run is near.
- **J14. Claude's access.** The read guard also denies Databricks CLI and SQL commands that name the volume `voc_raw` or the June tables, all Actions run logs (`gh run view --log`, `gh run download`, `gh api .../logs`), because a run ID does not show its workflow, and Claude starting the approval workflow (`gh workflow run` and the dispatch API). Claude reads only the results branch.
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
2. The read guard: `VOC_JUNE_DATA_DIR` and J14.
3. J6 and J1's laptop refusal: the June pin, its variable, and the frozen June sample (the owner runs `voc sample june`).
4. J7 and J1: the frozen claims, the hash script, `runs/JUNE_RUNS.md` and the June scoring code, on synthetic data.
5. J8's Job A: its definition and code, on synthetic data, with J5's output test.
6. J11 and J12: Job B, on the mock backend, with the push to a test branch.
7. J9: the receiver, with its tests. Then the owner approves and creates it.
8. J10: the approval workflow, with its tests on the YAML.
9. A dry run of the whole chain on synthetic data with the mock backend. Stop point: the owner decides whether to run June.
10. The June run itself, after the owner approves the printed figures. Then a new June section in `docs/VALIDATION.md` and the README, as the owner decides.

## Owner's setup steps, in order, each when its pull request is ready

- Delete the Databricks test jobs made on 4 November.
- **Claude Console:** make the cloud workspace, a key inside it and its $5 limit.
- **Databricks:** confirm that a job can run the repo's code (a Git folder or Git source) and that a secret scope can be made, make the secret scope with the API key and the GitHub "Contents" token, make the Databricks tokens, and set up Job A, Job B and the webhook destination with its Basic sign-in details.
- **GitHub:** make the `june-run` environment (main only, the owner as required reviewer, "prevent self-review" off) and its secrets, and make the two fine-grained tokens.
- **Azure:** approve and create the Function (maximum instance count 1, 512 MB), its storage account and its Key Vault, and put the secrets in the Key Vault. Use the destination's test to check that Databricks can reach the receiver.
- **Laptop:** set `VOC_JUNE_DATA_DIR`, run `voc sample june`, and keep the backup.
- **Last:** upload the June zip, then approve the run when its figures print.
- **Afterwards:** revoke the tokens, and remove the Function, its storage and Key Vault, and the workspace limit, if the owner wishes.

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
- Job B needs PyPI and GitHub from Databricks. GitHub's API was reachable on 4 November. PyPI is checked in pull request 5.
- Free Edition's daily quota has no published numbers. If a run is cut, it resumes by replay.
