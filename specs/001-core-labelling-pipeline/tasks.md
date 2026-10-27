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

- [ ] T001 First commit on `main`: `CLAUDE.md`, `BUILD_LOG.md`, `.gitignore`, README stub, Spec Kit files
- [ ] T002 PR "project skeleton": `pyproject.toml` with uv, pytest config, `tests/conftest.py` that blocks sockets, one test that proves the block (B7)
- [ ] T004 [P] PR "hooks" moves here: it must exist before any task touches real data
- [ ] T002b PR "download and profile": tests in `tests/test_download.py` and `tests/test_analysis.py` (B16 SHA-256 check, B22), then `scripts/download.py` (pinned export URL, date and SHA-256) and the `profile` command
- [ ] T003 PR "CI": `.github/workflows/ci.yml` runs pytest with no network, gitleaks on the full history, the names check, the file size and raw data checks on every pull request. `dbt build` is added to CI in T011.

## Phase 2: Foundational

- [ ] T004 (built before T002b, see above) PR "hooks": tests in `tests/test_hooks.py`, then `.claude/hooks/test_gate.py` (tests-only commits allowed) and `.claude/hooks/data_guard.py` (raw CFPB data, `.env`, key-like content), wired in `.claude/settings.json`
- [ ] T005 [P] PR "quote check": tests in `tests/test_evidence.py` (B1, B6), then `src/voc/evidence.py`
- [ ] T006 [P] PR "prompt and parsing": tests in `tests/test_prompt.py` (B4, B5), then `src/voc/prompt.py`
- [ ] T007 PR "decision": tests in `tests/test_decision.py` (B2 both views, B3, B5), then `src/voc/decision.py`. Needs T005, T006.

**Checkpoint**: one model answer can be checked and accepted or quarantined, with no model call.

---

## Phase 3: User Story 4 - Re-runs are free and spend has a hard stop (P4, built early because every live run needs it)

- [ ] T008 [US4] PR "ledger and replay": tests in `tests/test_budget.py` and `tests/test_replay.py` (B7, B8), then `src/voc/budget.py` and `src/voc/replay.py`
- [ ] T008b Owner task: set the monthly dollar limit in the Anthropic console. Claude writes down the steps. The owner does it and logs the time.
- [ ] T009 [US4] PR "backends and cost" (also owns: `.env` loading, with tests pointing it at an empty temp file): check terms and prices first (research.md), tests in `tests/test_backends.py` and `tests/test_costs.py` (B12, B13), then `src/voc/backends.py` and `src/voc/costs.py`

## Phase 4: User Story 3 - Load a new month safely (P3)

- [ ] T010 [P] [US3] PR "staged load" (also owns: DuckDB extension auto-install and auto-load turned off on every connection, with a test): check DuckDB and dbt versions first, tests in `tests/test_load.py` (B14 re-runnable, schema check), then `scripts/load_month.py`
- [ ] T011 [US3] PR "dbt curated and data tests": dbt project in `dbt/`, data tests for missing or repeated IDs and unknown Product, a test that a bad fixture fails the build. Lineage graph generated.
- [ ] T012 [US3] PR "samples": tests in `tests/test_data.py` (B9, B16), then `src/voc/data.py`, the `sample` command, and the committed ID lists in `splits/`

## Phase 5: User Story 2 and User Story 1 - Label, quarantine, score (P1, P2)

- [ ] T013 [P] [US1] PR "baselines and metrics": tests in `tests/test_baselines.py` and `tests/test_metrics.py` (B3, B10, B11, B18), then `src/voc/baselines.py` and `src/voc/metrics.py`
- [ ] T014 [US2] PR "pipeline": tests in `tests/test_pipeline.py` (B4, B5, B9 end to end with a fake model), then `src/voc/pipeline.py` and the `label` command
- [ ] T014b Live smoke test: 20 development complaints through the tested `label` command and the real `api` backend, right after T014. It prints only counts. It checks real Product strings, the quote match rate and real token counts. The token count fixture keeps only (byte count, token count) pairs, with no text or IDs. Logged.
- [ ] T014c PR "show command": tests (refuses test rows without `final`, blocked for Claude by the read guard), then the `show` command for the owner
- [ ] T015 [US1] PR "eval skill": tests in `tests/test_evaluate.py` (B15, B17, B19), then the `evaluate` command, the test run log, the results file and `.claude/skills/eval/SKILL.md`
- [ ] T015b [US1] Synthetic injection set: about 10 synthetic complaints with injection attempts, labelled synthetic, added to the evaluation (B5 real-model check)
- [ ] T016 [US1] First real run: prompt v1 on 50 development complaints, then the full development set if it looks right. Row in `EVAL_VERSIONS.md`.

## Phase 6: Polish

- [ ] T017 README "Why this stack" with checked facts, and the dbt lineage graph
- [ ] T018a PR "analyser": tests in `tests/test_analysis.py` (B21), then the `analyse` command with its fixed cause list
- [ ] T018 Error analysis (B21) and prompt versions v2 onward (one cause per version)
- [ ] T019 Final test run, once, with the chosen prompt version, only when the owner says "final" (B17)
- [ ] T020 README results: every figure with the command that produced it, both views, per-Product table, re-weighted figure, synthetic injection results reported apart. README checklist, checked by the reviewer agent: the CFPB "not a statistical sample" sentence, narratives are a 1.5 percent subset with a different class mix, labels are set by the consumer, "quote found in the text" not "quote supports the label", the injection caveat for the quote-only view, the model's training cutoff, the CFPB file changes over time, Known limits (from the threat model), every number with its command

## Dependencies

- T002 before everything else. T003 right after.
- T004, T005, T006, T010, T013 do not depend on each other. They are the parallel candidates.
- T007 needs T005 and T006. T014 needs T007, T008, T009, T012. T015 needs T013 and T014.

## Parallel plan

- Workstream A (labeller): T005, T006, T007, T008, T009, T014
- Workstream B (data): T010, T011, T012
- Workstream C (tooling): T004, then T015
- Each workstream runs in its own git worktree. Every run in parallel is logged in `BUILD_LOG.md`.

## MVP

T001 to T016 except T011. Until dbt lands, `load_month.py` runs the missing ID, repeated ID and unknown Product checks itself, and the labeller reads the sample table built by the `sample` command. dbt then adds the same checks as data tests and builds the serving views: one development run with quote check, quarantine, spend stop and an honest score. Then T019 and T020 must happen before the deadline, whatever else is cut.

## Checkpoints

- Wednesday 12:00: T001 to T009 merged.
- Wednesday 18:00: T010 to T014 merged and the T014b smoke test done.
- Wednesday 23:00: first full development run (T016).
- Thursday 12:00: prompt versions done or stopped. Then API and dashboard.
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
9. The brief's own cut order after that: synthetic sales calls, Azure, the dbt lineage graph. The agreement step is never cut, because claim B depends on it.
