# voc-demo Constitution

## Core Principles

### I. Evidence Before Labels

- Every LLM label MUST come with a quote copied from the complaint text.
- A script MUST check that the quote appears in the text. The model's own claim is never enough.
- A label with no valid quote, or one the baseline disagrees with (in the agreement view), MUST go
  to quarantine with one reason.
- A quarantined item MUST never be dropped without a record and MUST never count as correct.

Rationale: the system is useful only if a reader can check every label against the source text.

### II. Test First, Offline and Repeatable

- In each pull request, the failing test MUST be committed before the code that makes it pass.
- Tests MUST check behaviour against the spec. They pass or fail in seconds.
- Tests MUST NOT open a network connection or call an AI model. Model answers come from recorded
  fixtures.
- Label quality is measured by evaluation, not by tests.

Rationale: tests prove the code does what the spec says. Evaluation measures how good the labels are.
Mixing the two makes both untrustworthy.

### III. Honest Measurement

- Every report MUST show coverage and quarantine rate next to accuracy.
- The recorded CFPB label MUST be used only for scoring, never in a labelling prompt. (The error analyser may see it, on development data only, because its job is to explain disagreements.)
- Prompt changes MUST be scored on the development set only. The frozen test set is run once, at
  the end. A second run MUST be logged with its reason.
- The success rule: two claims are fixed before the first run (spec B10). Each must beat the TF-IDF
  baseline at the same coverage, with a 95 percent bootstrap interval wholly above zero, on the
  single test run.
- Every prompt version MUST get a row in `EVAL_VERSIONS.md`, including versions that made things
  worse.
- Every number in the README MUST come from a run in this repo, with the command shown.

Rationale: a small lucky gain, or a gain measured on data the prompt was tuned on, is not evidence.

### IV. Untrusted Input, Safe by Default

- Complaint text is data, not instructions. It sits between fixed boundaries and cannot close them.
- Complaint text MUST never reach a model or agent that can run tools, read files or use the network.
- The redaction mark "XXXX" MUST stay exactly as written. The model must not guess what it hides.
- Secrets MUST live only in environment variables or a git-ignored `.env`. A key is never printed.
- Live model calls MUST stop at a token cap kept in a ledger file.
- Raw CFPB data MUST never be committed. Only scripts, complaint IDs and small fixtures are.
- The repo MUST contain no personal names, no employer names, and nothing from any employer.

Rationale: the repo is public and the input is written by strangers.

### V. Simplest Tool That Does the Job

- A tool is added only when it solves a problem this project has now. No tool is added for show.
- When a bigger tool is not used, the README states the trigger that would make us switch.

Rationale: three days of work should go into verification, not infrastructure.

## Constraints

- Data: the CFPB Consumer Complaint Database, July 2026 export. The Product and Issue fields are set
  by the consumer, so they are noisy labels. The data is not a statistical sample of consumers.
- Stack: Python 3.13 with uv, pytest, DuckDB, dbt-duckdb, scikit-learn, the Anthropic Python SDK,
  FastAPI with Pydantic, React with Vite and TypeScript, Playwright, GitHub Actions, gitleaks.
- The LLM never runs inside a web request. Labelling is a batch job. The API only reads results.
- LLM backend is chosen by `LLM_BACKEND` (`api` or `mock`). Tests and CI use `mock` only. There is no `cli` backend.

## Workflow and Quality Gates

- Work happens in small pull requests on branches. Each one takes minutes to about an hour.
- Before merge, a fresh reviewer agent that did not write the code reads only the diff, the spec and
  `CLAUDE.md`. It lists problems and does not edit. Its findings are posted on the pull request.
- The owner decides what to fix and merges.
- CI runs the tests and a secret scan on every pull request.
- `BUILD_LOG.md` records work times, AI mistakes and how they were caught, overruled suggestions, and
  parallel work, as they happen. Entries are never invented or tidied.
- Git history is never rewritten, squashed to hide time, or backdated. The one exception is removing a leaked key or name before the repo goes public. Only the owner decides it, and it is logged with its reason.

## Governance

This constitution holds the principles. `CLAUDE.md` holds the day-to-day conventions and MUST NOT
contradict it. If they disagree, this file wins until both are fixed in the same pull request.
Amendments are made in a pull request and logged in `BUILD_LOG.md`. Versions follow semantic
versioning: MAJOR for removing or redefining a principle, MINOR for adding one, PATCH for wording.

**Version**: 1.3.1 | **Ratified**: 2026-10-28 | **Last Amended**: 2026-10-28 (1.1.0: untrusted text never reaches an agent that can act. 1.2.0: two claims fixed in advance. 1.3.0: analyser exception and leak exception, after review round 4. 1.3.1: `cli` removed from the backend constraint, owner cut decision)
