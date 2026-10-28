---
description: "Task list for the core labelling pipeline"
---

# Tasks: Core labelling pipeline

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md)

**Tests**: required. The constitution says tests first. In every pull request, the test task is committed (red) before the code task (green).

**Organization**: one group of tasks is one small pull request. Groups marked [P] can run in parallel in separate git worktrees.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: which user story the task serves (US1 to US4)

---

## Phase 1: Setup

- [x] T001 First commit on `main`: `CLAUDE.md`, `BUILD_LOG.md`, `.gitignore`, README stub, Spec Kit files
- [x] T002 PR "project skeleton": `pyproject.toml` with uv, pytest config, `tests/conftest.py` that blocks sockets, one test that proves the block (B7)
- [x] T004 [P] PR "hooks" moves here: it must exist before any task touches real data
- [ ] T002b PR "download and profile": tests in `tests/test_download.py` and `tests/test_analysis.py` (B16 SHA-256 check, B22), then `scripts/download.py` (pinned export URL, date and SHA-256) and the `profile` command. Then, from its output (counts only), `docs/DATA.md`: the exploratory data analysis, the label set assessment (B24) and the sample sizes from Cochran's formula (B25). From `docs/DATA.md`, the frozen label set in `config/labels.toml`. The owner reviews both before T012 draws any sample.
- [x] T003 PR "CI": `.github/workflows/ci.yml` runs pytest with no network, gitleaks on the full history, the names check, the file size and raw data checks on every pull request. `dbt build` is added to CI in T011.

## Phase 2: Foundational

- [x] T004 (built before T002b, see above) PR "hooks": tests in `tests/test_hooks.py`, then `.claude/hooks/test_gate.py` (tests-only commits allowed) and `.claude/hooks/data_guard.py` (raw CFPB data, `.env`, key-like content), wired in `.claude/settings.json`
- [ ] T005 [P] PR "quote check": tests in `tests/test_evidence.py` (B1, B6), then `src/voc/evidence.py`
- [ ] T006 [P] PR "prompt and parsing": tests in `tests/test_prompt.py` (B4, B5), then `src/voc/prompt.py`. The prompt takes the label list as an input, and tests use synthetic labels. The real list comes later from `config/labels.toml`, which T002b creates (B24).
- [ ] T006b PR "merge verdict", right after T005 and T006: a `/merge-verdict` command. A script runs the mechanical checks:
  - CI is green.
  - The red commit came before the code.
  - Every review finding is fixed or deferred with a reason.
  - For parallel branches: they touch no shared file, and the tests pass on both merged together.

  Claude then gives a one-line verdict: MERGE or FIX FIRST, with the reason, and the merge order for parallel branches. The owner still merges. T005 and T006 get the same checks by hand. The command is used on every pull request from T007 on.
- [ ] T007 PR "decision": tests in `tests/test_decision.py` (B3, B5), then `src/voc/decision.py`. Needs T005, T006.

**Checkpoint**: one model answer can be checked and accepted or quarantined, with no model call.

---

## Phase 3: User Story 4 - Re-runs are free and spend has a hard stop (P4, built early because every live run needs it)

- [ ] T008 [US4] PR "ledger and replay": tests in `tests/test_budget.py` and `tests/test_replay.py` (B7, B8), then `src/voc/budget.py` and `src/voc/replay.py`
- [ ] T008b Owner task: set the monthly dollar limit in the Anthropic console to $20 (owner decision, 28 October). Claude writes down the steps. The owner does it and logs the time.
- [ ] T009 [US4] PR "backends and cost" (also owns: `.env` loading, with tests pointing it at an empty temp file): check prices and API settings first (research.md), including whether the API still accepts a temperature setting (B12), then tests in `tests/test_backends.py` and `tests/test_costs.py` (B12, B13), then `src/voc/backends.py` and `src/voc/costs.py`. Only `api` and `mock`: `cli` was cut on 28 October.

## Phase 4: User Story 3 - Load a new month safely (P3)

- [ ] T010 [P] [US3] PR "staged load" (also owns: DuckDB extension auto-install and auto-load turned off on every connection, with a test): check DuckDB and dbt versions first, tests in `tests/test_load.py` (B14 re-runnable, schema check), then `scripts/load_month.py`. Add-on 1 (owner, 28 October): the August file's folder comes from a second environment variable, `VOC_NEXT_DATA_DIR`, never written in a file. Its SHA-256 is pinned like July's. The read guard is extended to that folder, tests first, and the owner approves the hook edit.
- [ ] T011 [US3] PR "dbt curated and data tests": dbt project in `dbt/`, data tests for missing or repeated IDs and unknown Product, a test that a bad fixture fails the build. Lineage graph generated. Add-on 1 (owner, 28 October): the staged complaints model is incremental, keyed on complaint ID, so a run adds only new rows. Shown with two real files, July then August. `BUILD_LOG.md` records the row count after July, after adding August, and after a re-run (must be unchanged), each with its command. A dbt test fails on any duplicated complaint ID. The README says what this does not cover yet: late or corrected records, and changes to the file's columns.
- [ ] T012 [US3] PR "samples": tests in `tests/test_data.py` (B9, B16, B25), then `src/voc/data.py`, the `sample` command, and the committed ID lists in `splits/`. Uses the label set from `docs/DATA.md` (B24), after the owner has reviewed it. Draws the development set and the test set with the Cochran sizes (B25), and freezes both.

## Phase 5: User Story 2 and User Story 1 - Label, quarantine, score (P1, P2)

- [ ] T013 [P] [US1] PR "baselines and metrics": tests in `tests/test_baselines.py` and `tests/test_metrics.py` (B3, B10, B11, B18), then `src/voc/baselines.py` and `src/voc/metrics.py`
- [ ] T014 [US2] PR "pipeline": tests in `tests/test_pipeline.py` (B4, B5, B9 end to end with a fake model), then `src/voc/pipeline.py` and the `label` command
- [ ] T014b Live smoke test: 20 development complaints through the tested `label` command and the real `api` backend, right after T014. It prints only counts. It checks real Product strings, the quote match rate and real token counts. The token count fixture keeps only (byte count, token count) pairs, with no text or IDs. Logged.
- [ ] T014c PR "show command": tests (refuses test rows without `final`, blocked for Claude by the read guard), then the `show` command for the owner
- [ ] T015 [US1] PR "eval skill": tests in `tests/test_evaluate.py` (B15, B17, B19), then the `evaluate` command, the test run log, the results file and `.claude/skills/eval/SKILL.md`
- [ ] T015c PR "scheduled pipeline run" (add-on 1, owner, 28 October, Thursday): a GitHub Actions workflow that runs load, dbt build with tests, and evaluation in order, once a day and on manual trigger. It uses the `mock` backend and the committed synthetic fixtures, because the replay cache holds model answers on real complaints and stays outside the repo. No live LLM, no secret. Clear logs per step, and the run fails if any step or data test fails. README note: what it does today, and when to move to a full scheduler such as Airflow (many dependent pipelines, retries per step, backfills). Airflow is not installed.
- [ ] T015b [US1] Synthetic injection set: about 10 synthetic complaints with injection attempts, labelled synthetic, added to the evaluation (B5 real-model check)
- [ ] T016 [US1] First real run: prompt v1 on 50 development complaints, then the full development set if it looks right. Row in `EVAL_VERSIONS.md`.

## Phase 6: Polish

- [ ] T017 README "Why this stack" with checked facts, and the dbt lineage graph
- [ ] T021 Optional Thursday stretch (add-on 1, owner, 28 October), only after every must-have is done, time box 1 hour: run the same dbt models on a Databricks Free Edition SQL warehouse with the dbt Databricks adapter. First read Databricks' Free Edition pages and limitations and the adapter's current docs, and report what they say about connecting dbt and about non-commercial use. The owner creates the account. The token lives only in an environment variable, never in the repo or printed. If it does not work within 1 hour, stop, log it and keep DuckDB as the only path. DuckDB stays the main path either way.
- [ ] T018a PR "analyser": tests in `tests/test_analysis.py` (B21), then the `analyse` command with its fixed cause list
- [ ] T018 Error analysis (B21) and prompt versions v2 onward (one cause per version)
- [ ] T019 Final test run, once, with the chosen prompt version, only when the owner says "final" (B17)
- [ ] T020 README results: every figure with the command that produced it, the LLM and TF-IDF side by side with cost and run time, per-Product table, re-weighted figure, synthetic injection results reported apart. README checklist, checked by the reviewer agent: the CFPB "not a statistical sample" sentence, narratives are a 1.5 percent subset with a different class mix, labels are set by the consumer, "quote found in the text" not "quote supports the label", the injection caveat (an obeyed injection with a real quote passes the quote check), the model's training cutoff, the CFPB file changes over time, Known limits (from the threat model), why there is no `cli` backend (untrusted text must never reach an agent with tools, and one code path keeps every number reproducible), the cost to label every narrative projected from measured tokens, every number with its command

## Dependencies

- T002 before everything else. T003 right after.
- T004, T005, T006, T010, T013 do not depend on each other. They are the parallel candidates.
- T007 needs T005 and T006. T014 needs T007, T008, T009, T012. T015 needs T013 and T014.

## Parallel plan

- Workstream A (labeller): T005, T006, T007, T008, T009, T014
- Workstream B (data): T010, T011, T012
- Workstream C (tooling): T004, then T015
- Each workstream runs in its own git worktree. Every run in parallel is logged in `BUILD_LOG.md`.
- Agreed on 28 October: T005 and T006 run in parallel, one by Claude in the main worktree and one by a second agent in its own worktree. Each gets its own red commit, reviewer and owner merge. Both get the `/merge-verdict` checks by hand, because T006b builds the command after them. The second agent does not edit `BUILD_LOG.md`, so the two branches share no file. Claude logs the parallel run.

## MVP

T001 to T016 except T011. Until dbt lands, `load_month.py` runs the missing ID, repeated ID and unknown Product checks itself, and the labeller reads the sample table built by the `sample` command. dbt then adds the same checks as data tests and builds the serving views: one development run with quote check, quarantine, spend stop and an honest score. Then T019 and T020 must happen before the deadline, whatever else is cut.

## Checkpoints

Changed on 28 October by owner decision, because the Wednesday 12:00 target (T001 to T009) would be missed. The original targets were: Wednesday 12:00 T001 to T009, Wednesday 18:00 T010 to T014 and T014b, Wednesday 23:00 T016.

- Wednesday 18:00: T002b and T005 to T009 merged.
- Thursday 01:00: T010 to T014 merged and the T014b smoke test done.
- Thursday 10:00: first full development run (T016).
- Thursday 12:00: prompt versions done or stopped. Then API and dashboard (Thursday 12:00 to 18:00). Also look again at the "carried-over failing test" allowance in the test gate (owner decision, 28 October): count its uses in `BUILD_LOG.md` and any weakened test the reviewer found. If any was weakened, go back to the strict rule.
- Thursday 22:00: final test run (T019) and README results (T020).

At Wednesday 12:00, make a cut decision whatever the state. After that, if a checkpoint is missed by more than 2 hours, cut further from the list below. The API and dashboard are not on the cut list, because the brief needs them to answer the feedback.

## Cut list if time runs short (confirmed by the owner 2026-10-28)

Cut in this order, never cutting the quote check, quarantine, tests, CI, the spend stop or the build log:

1. The `cli` backend (use `api` and `mock` only). This removes the canary check too.
2. PowerShell commit parsing in the test gate (the git pre-commit hook still covers it).
3. Full-text similarity dedupe across all pairs (keep exact normalised-text duplicates, and compare full text only where openings match).
4. Narrative-copy detection in the data guard, and every rare commit form in the test gate (move both to Known limits).
5. The CI check that the test run log only grows (the log stays committed).
6. The version-to-version interval (keep the interval against TF-IDF).
7. Method comparison extras beyond the confusion matrices and the who-was-right table (owner to confirm).
8. The analyser (owner to confirm). The fallback is that the owner reads examples with `show` and Claude sees only counts.
9. The brief's own cut order after that: the Databricks stretch (T021, added on 28 October, cut first), synthetic sales calls, Azure, the dbt lineage graph. (The agreement step was removed on 28 October by owner decision, with claim B.)

### Cut decision, 28 October (owner)

- Cut: items 1, 2, 3, 4 and 6. Item 2 and the rare commit forms in item 4 needed no work: the git pre-commit hook covers every commit form. The narrative-copy check from item 4 moves to Known limits.
- Kept for now, looked at again at the Thursday 12:00 checkpoint: items 5, 7 and 8.
- Added: the label set assessment and the sample size calculation (B24, B25), and the test set raised to about 3,000 (replaced later the same day by Cochran's formula, see B25).
