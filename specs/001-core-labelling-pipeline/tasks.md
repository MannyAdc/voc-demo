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
- [ ] T003 PR "CI": `.github/workflows/ci.yml` runs pytest and gitleaks on every pull request

## Phase 2: Foundational

- [ ] T004 [P] PR "hooks": tests in `tests/test_hooks.py`, then `.claude/hooks/test_gate.py` (tests-only commits allowed) and `.claude/hooks/data_guard.py` (raw CFPB data, `.env`, key-like content), wired in `.claude/settings.json`
- [ ] T005 [P] PR "quote check": tests in `tests/test_evidence.py` (B1, B6), then `src/voc/evidence.py`
- [ ] T006 [P] PR "prompt and parsing": tests in `tests/test_prompt.py` (B4, B5), then `src/voc/prompt.py`
- [ ] T007 PR "decision": tests in `tests/test_decision.py` (B2 both views, B3, B5), then `src/voc/decision.py`. Needs T005, T006.

**Checkpoint**: one model answer can be checked and accepted or quarantined, with no model call.

---

## Phase 3: User Story 4 - Re-runs are free and spend has a hard stop (P4, built early because every live run needs it)

- [ ] T008 [US4] PR "ledger and replay": tests in `tests/test_budget.py` and `tests/test_replay.py` (B7, B8), then `src/voc/budget.py` and `src/voc/replay.py`
- [ ] T009 [US4] PR "backends and cost": check terms and prices first (research.md), tests in `tests/test_backends.py` and `tests/test_costs.py` (B12, B13), then `src/voc/backends.py` and `src/voc/costs.py`

## Phase 4: User Story 3 - Load a new month safely (P3)

- [ ] T010 [P] [US3] PR "staged load": check DuckDB and dbt versions first, tests in `tests/test_load.py` (B14 re-runnable, schema check), then `scripts/load_month.py`
- [ ] T011 [US3] PR "dbt curated and data tests": dbt project in `dbt/`, data tests for missing or repeated IDs and unknown Product, a test that a bad fixture fails the build. Lineage graph generated.
- [ ] T012 [US3] PR "samples": tests in `tests/test_data.py` (B9), then `src/voc/data.py` and the `sample` command

## Phase 5: User Story 2 and User Story 1 - Label, quarantine, score (P1, P2)

- [ ] T013 [P] [US1] PR "baselines and metrics": tests in `tests/test_baselines.py` and `tests/test_metrics.py` (B3, B10, B11), then `src/voc/baselines.py` and `src/voc/metrics.py`
- [ ] T014 [US2] PR "pipeline": tests in `tests/test_pipeline.py` (B4, B5, B9 end to end with a fake model), then `src/voc/pipeline.py` and the `label` command
- [ ] T015 [US1] PR "eval skill": tests for the `evaluate` command and the `EVAL_VERSIONS.md` row (B15), then `.claude/skills/eval/SKILL.md`
- [ ] T016 [US1] First real run: prompt v1 on 50 development complaints, then the full development set if it looks right. Row in `EVAL_VERSIONS.md`.

## Phase 6: Polish

- [ ] T017 README "Why this stack" with checked facts, and the dbt lineage graph
- [ ] T018 Error analysis and prompt versions v2 onward (one cause per version)

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

T001 to T009 plus T012 to T014: one development run with quote check, quarantine, spend stop and an honest score.
