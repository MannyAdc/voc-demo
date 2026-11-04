# Feature Specification: An untouched June test, two more baselines, and a run without the laptop

**Feature Branch**: `004-june-test-and-baselines`

**Created**: 2026-11-04

**Status**: Draft for the owner. Written from the owner's request of 4 November 2026 (BUILD_LOG.md, 4 November). Nothing paid runs and no cloud resource is created before the owner approves.

**Input**: The owner asked for (a) a test of the 0.9 hybrid rule on June 2026, a month never used before, as `docs/VALIDATION.md` asks, (b) a gradient-boosting baseline next to TF-IDF + LR, (c) a fine-tuned small transformer as a third method, with a compute and time estimate first, and (2b) the June run done without the owner's laptop, keeping the laptop path working. An event-driven pipeline is not planned here: the CFPB stopped publishing complaint narratives on 14 August 2026, so new months have no text to label. That work moves to a separate project with a live text source.

Requirement IDs are `J1`, `J2` and so on. Tests are named `test_J<number>_...`.

## What we know before planning (checked on 4 November 2026)

- **New data has no narratives.** The CFPB's announcement of 14 August 2026: "The CFPB to Cease Discretionary Publication of Complaint Narratives and Visualizations" (consumerfinance.gov newsroom). The current bulk export (`complaints.csv.zip`, last modified 3 November 2026) and the search API's CSV both have 15 of the 16 pinned columns. The missing one is "Consumer complaint narrative". Checked from column names only.
- **The archive.** "Archive of consumer complaints received December 1, 2011 through August 14, 2026 that were previously published in the Consumer Complaint Database", in the CFPB's FOIA reading room, last modified 14 September 2026. 21 zip files. March to August 2026 have one file each. Our pinned July export, `CCDB_Export_20_July_2026`, is one of them. The page states no terms. The search API's metadata says `license: CC0`.
- **June 2026.** `CCDB_Export_19_June_2026.zip`, checked by the owner with a script that prints names and counts only: 19,624,767 bytes, one CSV of 219,864,163 bytes, the 16 pinned columns in the same order, 620,794 complaints, 16,820 with a narrative, all received from 1 to 30 June 2026. June has never been used in this project.
- **Spend limits.** The Claude Console sets spend limits per organization and per workspace, not per API key. The default workspace cannot have one. A key belongs to one workspace. A limit the owner sets stops requests with HTTP 400 ("You have reached your specified workspace API usage limits"). The docs do not say whether spend can go slightly past it. Sources: platform.claude.com, "Rate limits" and "Workspaces", read 4 November 2026.
- **GitHub Environments.** On a public repo, required reviewers and "only main" branch rules are available, and an environment's secrets reach only jobs that name it. A pull request's run has the ref `refs/pull/N/merge`, so a main-only rule keeps it out. A job that names the environment waits until a required reviewer approves. Source: docs.github.com, "Deployments and environments", read 4 November 2026.
- **A pull request opened with the built-in `GITHUB_TOKEN`** creates its CI run "in an approval-required state", so a person approves it before it runs. Other events from that token create no run. Source: docs.github.com, "Triggering a workflow", read 4 November 2026.
- **Databricks Free Edition.** Serverless only, one small SQL warehouse, at most 5 job tasks at a time, a daily compute quota with no published numbers, and outbound internet "restricted to a limited set of trusted domains". Scheduled jobs, starting a job from outside and personal access tokens are documented for Databricks in general but not confirmed for Free Edition. Source: docs.databricks.com, "Free Edition limitations", last updated 18 October 2026.

## Rules for every piece

- **J1. June is scored once, after everything is frozen** (owner decision, 4 November: June last). Every method's settings, the hybrid rule, the June sample, the scoring and the claims are committed before any June label is scored. June is then scored once, for every method together. Nothing is tuned on June. As B17 for the test set.
- **J2. The July test set stays sealed.** No new method is scored on it. New methods are tuned and compared on the development set, then scored on June.
- **J3. The same rules as before.** No complaint text in git (B19, B21). Every live call goes through a spend cap, is recorded, and is approved first (V9). Results that do not favour the LLM are reported the same way. Agreement with the consumer's choice is called that.

## The pieces

- **J4. The June sample.** `voc sample`, as for July: June's 16,820 narratives, copies removed as before, and also any complaint whose narrative copies one in the July pool, so June shares nothing with the data used to build. Sample size by Cochran's formula (B25) at e = 2 points, with the finite pool correction: about 2,080 complaints, split across Products in proportion. Frozen with its hashes in `splits/june/`. The file gets its own pin in `config/data_files.toml`, and its folder its own variable, `VOC_JUNE_DATA_DIR`.
- **J5. Gradient boosting (b).** A gradient-boosted tree model on the same TF-IDF features, trained on the same 7,024 training complaints, with a confidence for every label. Its settings are chosen on the development set only, with a small, fixed grid written down before the first run. It is scored at the same coverage, as TF-IDF + LR is. Library: XGBoost (owner decision, 4 November), pinned as `xgboost==3.4.1` in `pyproject.toml`, released on 15 August 2026, with a Windows wheel, for Python 3.12 and later. Its docs show a scipy.sparse CSR matrix loaded directly with `xgb.DMatrix(csr)`, and say its scikit-learn interface builds a DMatrix from the input ("Python Package Introduction", xgboost.readthedocs.io, read 4 November 2026). The first test of this piece checks that `XGBClassifier` fits and predicts on the CSR features, and how it treats the unstored zeros. scikit-learn's own gradient boosting needs dense features, which at 50,000 features would not fit.
- **J6. A fine-tuned small transformer (c), estimate first.** A small pretrained text model, fine-tuned on the 7,024 training complaints to pick one of the 11 Products, with a confidence. First, a free estimate on the laptop: one pass over 500 training complaints, timed, with the model's size and the text length fixed. From it, the time for a full run. Then the owner decides where it runs (owner decision, 4 November: the estimate first, then the decision). On the laptop it costs nothing but time. A GPU service would be a new place for complaint text, so it needs the owner's decision and its own check. The model and its settings are chosen before training. Development-set figures pick between at most 3 fixed settings. Proposed starting point: a distilled English model of about 66 million parameters, with text cut at 256 tokens. It is scored at the same coverage too.
- **J7. The June test (a).** On the June sample, each method labels each complaint once: the LLM (claude-haiku-5-5, prompt v1, unchanged), TF-IDF + LR (the trained July model, unchanged), gradient boosting and the transformer. The hybrid is the rule fixed on 2 November, unchanged: TF-IDF + LR answers at a top confidence of 0.9 or more, else the LLM. A held-back LLM label counts as wrong. Scored as B10: re-weighted strict accuracy at the same coverage, with a paired bootstrap of 2,000 draws within each Product, seed 0. The claims, fixed before the run:
  - the hybrid against the LLM alone, the question `docs/VALIDATION.md` left open
  - the LLM against TF-IDF + LR, as a repeat of the July claim on a new month
  - gradient boosting and the transformer each against the LLM
  - each reported whatever it shows, with its interval, and the LLM's cost per extra correct label as in V6.
- **J8. The June run without the laptop (2b).**
  1. The owner uploads the June file to the Unity Catalog volume once.
  2. A Databricks job builds June with the same dbt models as the July and August build, started by hand from the Databricks page.
  3. A GitHub Actions workflow, started by hand, in a protected environment (`june-run`, main only, the owner as required reviewer), reads the June sample's rows from the Databricks SQL warehouse, labels them with the LLM, and writes the recordings and the ledger to the volume.
  4. The same workflow opens a pull request with the results files only (IDs, labels, positions, decisions, reasons, counts). The owner merges it as any other.
  - The laptop path, `voc label` and `voc evaluate`, keeps working, and both paths give the same files.
- **J9. The spend cap for the cloud run.** A separate workspace in the Claude Console, made by the owner, for cloud runs only, with its own API key and a monthly spend limit the owner sets. Limit: $5 a month (owner decision, 4 November), about 10 times the expected cost. The key is a secret of the `june-run` environment only, never a repository secret. The run also keeps a ledger, as the laptop does, with the same estimate and cap before any call. A 400 "usage limits" answer stops the run and is not retried. A 429 is retried only when it has a `retry-after` header.
- **J10. Recordings in the volume.** The model's answers hold quotes, which are complaint text, so they go to the volume `voc_raw`, in their own folder, never to git or to a GitHub artifact. A rerun replays them from there.
- **J11. The results pull request.** The workflow opens it with the built-in `GITHUB_TOKEN`, with contents and pull requests write only. Its CI run then waits for the owner's approval, and no extra token is needed. The pull request still gets a fresh reviewer and `/merge-verdict`, and the owner merges it.

## Costs

| Item | One-off | Monthly |
|---|---|---|
| LLM labels for the June sample, about 2,080 complaints at the test run's $0.2373 per 1,000 | about $0.49 | none |
| Gradient boosting and the transformer on the laptop | $0 | none |
| A GPU service for the transformer, only if the estimate says so | to be priced from the estimate | none |
| Databricks Free Edition, GitHub Actions on a public repo | $0 | $0 |
| Azure | none used | none |

The ledger reserves a worst case before the run, as it does now. That is much more than the expected cost.

## Pull requests, in order

1. This spec, the README's "monthly feed" line, and the test list.
2. J4: the June pin, its variable, and the frozen June sample (the owner runs `voc sample` on the June file, as for July).
3. J5: gradient boosting, tuned and compared on the development set.
4. J6, part 1: the timed estimate, reported to the owner. Part 2, after the owner's decision: the fine-tuning, compared on the development set.
5. J7: the frozen claims and the June scoring code, on synthetic data. Stop point: the owner decides whether to run June on the laptop now, or after J8.
6. J8 to J11: the Databricks job, the `june-run` workflow and environment, the recordings and the ledger in the volume, and the results pull request, on synthetic data first.
7. The June run itself, after the owner approves the printed figures, by either path. Then the June results in `docs/VALIDATION.md` and the README, as the owner decides.

## Owner's setup steps

- Upload the June file to the volume.
- Make the cloud workspace, its key and its spend limit in the Claude Console.
- Make the `june-run` environment with its secrets and the main-only rule.
- Approve the CI run on the results pull request.
- Check in the Databricks workspace that a personal access token can be made and a job can run by hand. Free Edition's docs do not confirm either.

## Not in scope

- An event-driven or scheduled pipeline, and webhooks. Moved to a separate project.
- Any new score on the July test set.
- Changing prompt v1 or the 0.9 rule.
- A transformer larger than the estimate supports.

## Known limits

- June is one more month. It does not show how the methods behave after August 2026, because there is no text after 14 August.
- Gradient boosting and the transformer are tuned on the same development set the LLM's prompt was tuned on. June is their only untouched test.
- The answer key is still the consumer's choice, which V2 shows is noisy.
- The Free Edition features in J8 are not confirmed by its docs. If one is missing, the June run falls back to the laptop path, and the plan says which step moved.
