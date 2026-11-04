# Feature Specification: An untouched June test, run in the cloud with no laptop

**Feature Branch**: `004-june-test-and-baselines`

**Created**: 2026-11-04. Revised the same day after the first review of #85 and the owner's decisions.

**Status**: Draft for the owner. Nothing paid runs and no cloud resource is created before the owner approves.

**Input**: The owner's requests of 4 November 2026 (BUILD_LOG.md, 4 November). The main goal is one full cloud run with no laptop: the owner uploads the test month's file to the Databricks volume, the file's arrival starts a Databricks job, a webhook starts the labelling workflow when the build finishes, and the results come back as a pull request. The test month is June 2026, never used before. It answers the question `docs/VALIDATION.md` left open: does the 0.9 hybrid rule beat the LLM alone on untouched data? A small XGBoost baseline is added. The fine-tuned transformer is dropped from this spec (owner decision). An event-driven pipeline on new months is not possible here, because the CFPB stopped publishing complaint narratives on 14 August 2026.

Requirement IDs are `J1`, `J2` and so on. Tests are named `test_J<number>_...`.

## What we know before planning (checked on 4 November 2026)

- **New data has no narratives.** The CFPB's announcement of 14 August 2026: "The CFPB to Cease Discretionary Publication of Complaint Narratives and Visualizations" (consumerfinance.gov newsroom). On 4 November, the current bulk export (`complaints.csv.zip`, last modified 3 November 2026 by its HTTP header) and the search API's CSV both had 15 of the 16 pinned columns, without "Consumer complaint narrative". Checked by Claude from column names only.
- **The archive.** "Archive of consumer complaints received December 1, 2011 through August 14, 2026 that were previously published in the Consumer Complaint Database", in the CFPB's FOIA reading room, last modified 14 September 2026, 21 zip files at `files.consumerfinance.gov/f/documents/`. March to August 2026 have one file each. The page states no terms. The search API's metadata says `license: CC0`. The July file name matches our pinned July export's name. Byte identity was not checked.
- **June 2026.** `CCDB_Export_19_June_2026.zip`, checked by the owner with a script that prints names and counts only: 19,624,767 bytes, one CSV of 219,864,163 bytes, the 16 pinned columns in order, 620,794 complaints, 16,820 with a narrative, all received in June 2026.
- **August 2026 is not usable.** The archive's August file is the owner's pinned August export. It holds 667,140 complaints, all received in August, but only 1 with a narrative (received 11 August).
- **Databricks Free Edition**, checked by the owner in the owner's workspace: the trigger types offered are Scheduled, File arrival, Table update, Continuous, Model update and Upstream job completion. A Webhook notification destination can be made, with an authentication mode and a URL. A personal access token can be made. Its documented limits (last updated 18 October 2026): serverless only, one 2X-Small SQL warehouse, at most 5 job tasks at a time, a daily compute quota with no published numbers, outbound internet only to "a limited set of trusted domains", and accounts that are inactive for long may be deleted.
- **Databricks webhooks** use HTTP Basic sign-in or OAuth, with no signature. A job's payload has `event_type` (such as `jobs.on_success`), `run.run_id` and the job's ID (docs.databricks.com, "Add notifications on a job").
- **Databricks tokens.** The `jobs` scope covers starting a job and reading a run. A token with no scope has full access. Unused tokens are revoked after 90 days (docs.databricks.com, "personal access tokens", last updated 7 October 2026).
- **Spend limits.** The Claude Console sets spend limits per organization and per workspace, not per API key, and the default workspace cannot have one. Some keys are made inside one workspace. Others pick a workspace with a header on each request. A limit the owner sets stops requests with HTTP 400 ("You have reached your specified workspace API usage limits"). The docs do not say whether spend can go slightly past it (platform.claude.com, "Rate limits" and "Workspaces").
- **GitHub Environments.** On a public repo, required reviewers and main-only branch rules are available, and an environment's secrets reach only jobs that name it. A pull request's run has the ref `refs/pull/N/merge`, so a main-only rule keeps it out. A job that names the environment waits for a required reviewer. A `repository_dispatch` needs a token with contents write. The repo is public, so Actions logs are public (docs.github.com).
- **XGBoost.** `xgboost==3.4.1`, released on 15 August 2026, with a Windows wheel, for Python 3.12 and later. Its docs show a scipy.sparse CSR matrix loaded with `xgb.DMatrix(csr)`, and say its scikit-learn interface builds "a DMatrix or a QuantileDMatrix" from the input ("Python Package Introduction"). scikit-learn's `GradientBoostingClassifier` also takes sparse input. XGBoost is used by owner decision.
- **The model's training data.** The README and `docs/LIMITS.md` say the July complaints cannot be in the model's training data, because it ends in June 2026. That does not hold for June. June narratives could be published from early June, after the company's response or 15 days, so some may have been public within the month the training data ends.

## Rules for every piece

- **J1. June is scored once, after everything is frozen.** Every method's settings, the hybrid rule, the June sample, the scoring code and the claims are committed before any June label is scored. Then one entry is added to `runs/JUNE_RUNS.md`, which only grows, as `runs/TEST_RUNS.md` does: date, commit, sample and methods. June is then scored once, by the cloud path, for every method together. A June load refuses unless that entry exists for the current commit. A later run is logged with its reason, and is a reproduction (the same recorded answers replayed) or a second run, never a quiet rescoring. A run stopped by the spend limit is not scored, and resumes by replay.
- **J2. The July test set stays sealed.** No new method is scored on it, and no June step reads it. New methods are tuned and compared on the development set only.
- **J3. The same rules as before.** No complaint text in git (B19, B21). Every live call goes through a spend cap, is recorded and is approved first (V9). Results that do not favour the LLM are reported the same way. Agreement with the consumer's choice is called that, never accuracy.
- **J4. Nothing with complaint text leaves its place.** Complaint text, recordings and fitted models (a TF-IDF vocabulary holds complaint words) stay in the Databricks volume or on the laptop. Never in git, a GitHub artifact, an Actions cache, a log or a model hub.
- **J5. What a cloud job may print.** The repo is public, so its Actions logs are public. A workflow prints only IDs, labels, reasons, positions, decisions and counts, through the same output rule as the command line (B21), with no debug or verbose logging. A test runs it on hostile synthetic text and checks the log.

## The constitution and the data rules

The constitution allows "the CFPB Consumer Complaint Database, July 2026 export, for all labelling and evaluation" (2.0.1), B16 builds samples only from the pinned July file, and B25 sizes them from the July pool. Owner decision of 4 November: a MINOR amendment to 2.1.0 allows one archive month, June 2026, for this spec's one untouched test only, with its one primary claim. B16, B25 and CLAUDE.md change to match, in the first pull request, logged. The July results, the July claim and `docs/VALIDATION.md` stay as they are. June gets its own new section.

## The pieces

- **J6. The June sample.** `voc sample june`, as for July: June's narratives, copies within June removed as before, and also any June complaint whose narrative copies one in July's training or development sets (owner decision, the July test set stays sealed). Every June Product must be in `config/labels.toml` (B24), or the sample refuses. Its size by Cochran's formula (B25) at e = 2 points, with N the June pool after copies are removed: about 2,080 if about 1,270 copies go, and 2,102 if none do. The exact n comes from the June count. Split across Products in proportion. Frozen with its hashes in `splits/june/`. The file gets its own pin in `config/data_files.toml`, and its folder its own variable, `VOC_JUNE_DATA_DIR`, which the read guard protects and the merge check drops, as for July and August.
- **J7. XGBoost, kept small.** `XGBClassifier` on the same TF-IDF features, trained on the same 7,024 training complaints, with a confidence for every label. One fixed grid of at most 4 settings, written down before the first run, chosen on the development set. Its first test checks that it fits and predicts on the CSR features and how it treats unstored zeros. Scored at the same coverage, as B10 defines it: its own most confident k complaints, with k the LLM's accepted count, chosen again in each resample, ties broken by ID.
- **J8. The June scoring and its claims.** On the June sample, the LLM (claude-haiku-5-5, prompt v1, unchanged), TF-IDF + LR (the July model, refit from July training only, unchanged settings) and XGBoost each label every complaint once. The hybrid is the rule fixed on 2 November, unchanged: TF-IDF + LR answers at a top confidence of 0.9 or more, else the LLM. A held-back LLM label counts as wrong. Scores are re-weighted by June's own pool after copies are removed, so they are not directly comparable with July's, whose product mix differs. Intervals come from a paired bootstrap of 2,000 draws within each Product, seed 0.
  - **The one primary claim, fixed now** (owner decision): the hybrid against the LLM alone, both at full coverage, as V6 scores it. The hybrid beats the LLM if the 95% interval of the difference is wholly above zero, does not beat it if the difference is zero or below, and is inconclusive otherwise.
  - **Secondary, each with its interval, not as verdicts:** the LLM against TF-IDF + LR at the same coverage, and XGBoost minus the LLM, with no direction fixed in advance.
  - **Cost per extra correct label:** against TF-IDF + LR at the same coverage, as V6's headline, with the full-coverage view next to it.
- **J9. The full cloud run.**
  1. The owner uploads the June file to a folder `voc_raw/incoming/` in the volume.
  2. Its arrival starts a Databricks job (file-arrival trigger): it checks the file against its pin, then runs the same dbt models as the July build, then writes the June sample's rows to a table. It prints counts only.
  3. When the job succeeds, its webhook notification goes to the receiver (J10).
  4. The receiver starts the labelling workflow with a `repository_dispatch`.
  5. The labelling workflow (J11) waits for the owner's approval, then labels and scores.
  6. It pushes a results branch. Claude opens the draft pull request from it, as usual (owner decision). The repo setting that lets Actions open pull requests stays off.
  - The laptop path, `voc label` and `voc evaluate`, keeps working. On mock or replay, both paths give the same files.
- **J10. The receiver.** A small Azure Function, apart from the public app, which stays read-only.
  - It replies at once (202) and does the work afterwards, through a queue in its own storage account.
  - It checks each caller. The Databricks webhook carries HTTP Basic sign-in with a secret, and the receiver then asks Databricks itself whether that `run.run_id` really succeeded for the June job, with a token of `jobs` scope. The workflow's result message back to the receiver (step 7 below) carries an HMAC-SHA256 signature of the raw body with a shared secret and a timestamp, checked with a constant-time compare, refused if older than 5 minutes.
  - It ignores a duplicate. Each event's ID (Databricks: the run ID and event type, GitHub: a delivery ID) is stored, and a repeat is acknowledged and dropped.
  - It retries failures. A failed call to GitHub or Databricks is retried with backoff up to 5 times by the queue, then moved to a failure queue and logged, with IDs and counts only.
  - It holds no complaint text. Its secrets are in its own app settings.
  - The outbound webhook: when the labelling workflow ends, it posts a signed result message (status, counts and the commit) to the receiver, which logs it.
  - Tests for each: a bad signature, an old timestamp, a duplicate, a slow reply, and a retry that ends in the failure queue.
- **J11. The labelling workflow.**
  - Started only by `repository_dispatch` from the receiver or by the owner with `workflow_dispatch`. Claude never starts it.
  - Permissions per job. A labelling job in the protected environment `june-run` (main only, the owner as required reviewer, "prevent self-review" off so the owner can approve a run the owner's dispatch started) holds the secrets and has read-only repo access. A second job, with no secrets, pushes the results branch.
  - One run at a time (a `concurrency` group), and every action pinned by its commit SHA.
  - Before labelling, it checks the sample's IDs and content hashes against `splits/june/` (B16).
  - It reads the June rows from the SQL warehouse, labels them, and writes the recordings and the ledger to `voc_raw/recordings_june/` and `voc_raw/ledger_june/`. TF-IDF + LR and XGBoost are fitted in the same job, from July training rows read the same way, and never saved outside the volume.
  - Its results files hold IDs, labels, positions, decisions, reasons and counts only.
- **J12. The spend cap.** A separate workspace in the Claude Console, made by the owner, for cloud runs only, with a key made inside it, and a monthly spend limit of $5 (owner decision). The workflow refuses unless the API's `anthropic-workspace-id` response header names that workspace. It keeps its own ledger, with a cap of 15 million tokens for this run. Because the worst-case reservation for about 2,080 calls is about 38 million tokens (the July test run's reservation, 35,233,329 for 1,909 calls, scaled), the workflow labels in batches that each fit the cap and the $5 limit. A 400 "usage limits" answer stops the run with no retry. A 429 is retried only when it has a `retry-after` header.
- **J13. Tokens and secrets.**
  - `june-run` environment secrets: the API key, a Databricks token with the `sql` scope and the scope for the Files API (to be named from `GET /api/2.0/token-scopes` before it is made), and the HMAC secret.
  - The receiver's app settings: a Databricks token with the `jobs` scope only, a GitHub fine-grained token for this repo with contents write only (needed for `repository_dispatch`), the Basic sign-in secret and the HMAC secret.
  - Each token lasts 30 days, enough for the run and a rerun, and is revoked after. The owner's existing token, scope `sql`, expires on 6 November, so new ones are made when the run is near.
- **J14. Claude's access.** The read guard also denies Databricks CLI and SQL commands that name the volume `voc_raw` or the June tables, and `gh run view --log` and `gh run download` for the June workflow. Claude reads only the results branch.
- **J15. A backup.** Free Edition may delete an inactive account and may shut compute down for a day. The owner keeps the June file and, after the run, a copy of the June recordings, on the laptop's backup, as for the exports.

## Costs

| Item | One-off | Monthly |
|---|---|---|
| LLM labels for the June sample, about 2,080 complaints at the July test run's $0.2373 per 1,000 | about $0.49 | none |
| XGBoost and TF-IDF + LR, in the workflow | $0 | none |
| Databricks Free Edition, GitHub Actions on a public repo | $0 | $0 |
| The receiver: Azure Functions Flex Consumption, Australia East | $0 (free grant: 250,000 runs and 100,000 GB-seconds a month) | $0 at this use |
| Its storage account (queue, event IDs, function code), Hot LRS | none | under $0.10 (data $0.02 per GB, operations $0.0044 to $0.055 per 10,000, Azure Retail Prices API, 4 November 2026) |

The owner approves the Azure Function and its storage account before they are made.

## Pull requests, in order

1. This spec, the constitution amendment to 2.1.0, B16, B25 and CLAUDE.md, the README's "monthly feed" lines, and the test list.
2. The read guard: `VOC_JUNE_DATA_DIR`, the Databricks and run-log commands (J14), after #86.
3. J6: the June pin, its variable, and the frozen June sample (the owner runs `voc sample june` on the laptop).
4. J7: XGBoost, on the development set.
5. J8 and J1: the frozen claims, `runs/JUNE_RUNS.md`, and the June scoring code, on synthetic data.
6. J9: the Databricks job, as code and steps, on synthetic data.
7. J10: the receiver, with its tests. Then the owner approves and creates it.
8. J11 to J13: the labelling workflow and its environment, on mock data. Stop point: the owner decides whether to run.
9. The June run itself, after the owner approves the printed figures. Then a new June section in `docs/VALIDATION.md` and the README, as the owner decides.

## Owner's setup steps

- Upload the June file to the volume, and keep a backup.
- Make the cloud workspace, a key inside it and its $5 limit in the Claude Console.
- Make the `june-run` environment, its secrets and its main-only rule.
- Make the Databricks tokens and the GitHub fine-grained token when the run is near.
- Approve and create the Azure Function and its storage account.
- Approve the labelling run, then the results pull request's CI.
- Delete the Databricks test jobs made on 4 November.

## Not in scope

- An event-driven pipeline on new months, and monitoring. Moved to a separate project.
- The fine-tuned transformer. Dropped by owner decision.
- Any new score on the July test set.
- Changing prompt v1 or the 0.9 rule.

## Known limits

- June comes before July, so it is untouched but not a test of the future.
- The training-data claim in the README and `docs/LIMITS.md` does not hold for June. Some June narratives may be in the LLM's training data. That would favour the LLM in every June comparison. It would bias the primary claim towards the LLM alone and against the hybrid, the secondary LLM against TF-IDF + LR comparison towards the LLM, and XGBoost minus the LLM towards the LLM. The June section says so.
- June's narrative share is 2.7% (16,820 of 620,794) against July's 1.5% (10,002 of 672,036), which suggests a different publication lag and mix.
- XGBoost is tuned on the development set and TF-IDF + LR was not. June is their only untouched test.
- The answer key is still the consumer's choice, which V2 shows is noisy.
- The receiver confirms a Databricks call by asking Databricks, because Databricks does not sign its webhooks.
- Free Edition's daily quota has no published numbers. If a run is cut, it resumes by replay.
