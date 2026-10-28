# Implementation Plan: Core labelling pipeline

**Branch**: `001-core-labelling-pipeline` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-core-labelling-pipeline/spec.md`

## Summary

A batch pipeline loads the CFPB July 2026 export into DuckDB, builds de-duplicated samples (Python, unit tested), joins everything in curated dbt models, labels each sampled complaint with an LLM that must quote its evidence, checks every quote with a script, and quarantines failures with a reason. Two baselines and a coverage-matched bootstrap comparison decide whether the LLM adds value.

## Technical Context

**Language/Version**: Python 3.13, managed with uv

**Primary Dependencies**: DuckDB, dbt-core with dbt-duckdb, scikit-learn, Anthropic Python SDK. Exact versions are checked and pinned in the first pull request that adds each one (see [research.md](research.md)).

**Storage**: one local DuckDB file, git-ignored. Raw CSV stays outside git.

**Testing**: pytest. Network blocked in every test. Model answers from recorded fixtures (`LLM_BACKEND=mock`).

**Target Platform**: Windows laptop for development, Linux in GitHub Actions.

**Project Type**: batch data pipeline plus Python library. The API and dashboard are later features that only read its results.

**Performance Goals**: full test suite under 60 seconds. Loading one month (672,036 rows) in a few minutes on a laptop.

**Constraints**: one hard token cap shared by all runs and worktrees. No raw data in git. No network in tests.

**Scale/Scope**: the July 2026 export. Row and narrative counts come from the `profile` command (B22). A development sample of about 385 and a frozen test set of about 2,400, from Cochran's formula (B25). *Changed on 28 October: the earlier estimate of about 10,000 narratives and a test set of about 1,000 is replaced.*

## Constitution Check

| Principle | How this plan meets it |
|---|---|
| I. Evidence before labels | Quote check (B1) and quarantine (B3) are in the first pull requests, before any live model call. |
| II. Test first, offline | Each pull request commits its failing tests first. A test fixture blocks sockets. `mock` backend only in tests and CI. |
| III. Honest measurement | Baselines (B11) and the comparison rule (B10) exist before the first real run. `/eval` writes `EVAL_VERSIONS.md` (B15). |
| IV. Untrusted input, safe by default | Boundaries and strict parsing (B5), "XXXX" kept (B6), key only from the environment (B12), token cap (B8), data guard hook. |
| V. Simplest tool | DuckDB and dbt on one laptop. No cluster, no scheduler. Switch triggers written in the README. |

Gate result: pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-core-labelling-pipeline/
├── spec.md
├── plan.md        # this file
├── research.md    # facts to check before pinning tools
└── tasks.md       # one task per small pull request
```

### Source Code (repository root)

```text
src/voc/
├── evidence.py    # B1, B6 quote check
├── prompt.py      # B4, B5 build prompt, parse answer
├── decision.py    # B3 accept or quarantine
├── pipeline.py    # one complaint in, one decision out
├── replay.py      # B7 record and replay
├── budget.py      # B8 token ledger
├── backends.py    # B12 api, mock
├── costs.py       # B13 tokens to dollars
├── data.py        # B9 dedupe, truncate, split
├── baselines.py   # B11 most-common-class, TF-IDF
├── metrics.py     # B3, B10 summary and comparison
└── cli.py         # commands: load, sample, label, evaluate

scripts/
└── load_month.py  # B14 raw CSV to staged DuckDB table

dbt/
├── models/curated/   # de-duplicated narratives, samples, joined results
├── models/serving/   # views the API will read
└── tests/            # data tests

tests/
├── fixtures/      # short synthetic texts and recorded mock answers
└── test_*.py      # named test_B<number>_...

splits/            # committed ID lists of the frozen samples, with hashes (B16)
results/           # committed per-complaint results, no narrative text (B19)
```

**Structure Decision**: a single Python package plus a dbt project. The four data layers map as: Raw (CSV outside git), Staged (DuckDB table from `load_month.py`), Curated (dbt models), Serving (dbt views). The labeller reads the sample table built by the `sample` command and writes results back to DuckDB, then dbt builds the curated and serving models. Until dbt lands, `load_month.py` runs the ID and Product checks itself. Recordings and the ledger live outside the repo, in the home folder.

## Complexity Tracking

No violations.
