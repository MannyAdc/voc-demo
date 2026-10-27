# Test list

Status: draft, waiting for the owner's approval before any code. Each line is one test. Tests check behaviour against [the spec](../specs/001-core-labelling-pipeline/spec.md). They run offline in seconds and never call a model. Label quality is measured separately by evaluation.

Lines marked (reused) come from test ideas in an earlier unpublished start of this project. The rest are new.

## Network block (B7), `tests/test_network.py`

- the test suite cannot open a network connection (reused)

## Quote check (B1, B6), `tests/test_evidence.py`

- quote found, ignoring spaces and line breaks (reused)
- reported start and end point into the original text (reused)
- capital letters matter (reused)
- a quote not in the text is rejected, with no position (reused)
- an empty or blank quote is rejected (reused)
- a quote needs at least 3 words (reused)
- "XXXX" in a quote matches "XXXX" in the text (reused)
- a guess in place of "XXXX" does not match (reused)
- a quote of only redaction marks is not evidence (reused)

## Prompt and parsing (B4, B5), `tests/test_prompt.py`

- the prompt function takes only the text and the labels (reused)
- the prompt contains the text and every label (reused)
- the text sits between one pair of boundaries (reused)
- text cannot close the data section early (reused)
- valid JSON is parsed (reused)
- JSON inside a code fence is parsed (reused)
- prose is unparseable (reused)
- a missing key is unparseable (reused)
- values that are not text are unparseable (reused)

## Decision (B2, B3, B5), `tests/test_decision.py`

- agreement view: accepted when the quote is real and both sources agree (reused)
- agreement view: disagreement is quarantined as `disputed` (reused)
- quote-only view: the same disagreement is accepted
- a quarantined decision keeps the proposal but has no label (reused)
- a made-up quote is quarantined (reused)
- short and empty quotes are quarantined (reused)
- a label outside the list is quarantined even with a real quote (reused)
- an unparseable answer is quarantined (reused)
- check order is parse, label, quote, agreement (reused)
- an obeyed injection with a real quote is caught by agreement (reused)
- an obeyed injection with an invented quote is caught by the quote check (reused)
- a quarantined decision never has an accepted label, 4 cases (reused)

## Ledger (B8), `tests/test_budget.py`

- a new ledger has used nothing (reused)
- charges add up (reused)
- use survives a restart (reused)
- a call that just fits is allowed, one more token is refused (reused)
- actual use above the estimate blocks the next call (reused)
- a negative charge is an error (reused)

## Record and replay (B7, B8), `tests/test_replay.py`

- the key is a stable hash of model, settings and prompt (reused, settings added)
- first call is live, second comes from the recording (reused)
- replay mode serves a recording with no inner client (reused)
- replay mode with no recording is an error, not a live call (reused)
- a different model or prompt is not served the old recording (reused)
- a live call is charged, a replayed call is free (reused)
- a live call past the cap is refused before it is sent (reused)
- a recording is still served when the budget is spent (reused)

## Backends (B12), `tests/test_backends.py`

- `LLM_BACKEND=mock` serves fixtures and makes no network call
- an unknown `LLM_BACKEND` value is an error that names the allowed values
- `api` with no key in the environment fails with a clear message
- the key never appears in an error message or log line
- `cli` builds the expected `claude -p` command (the process itself is faked)

## Cost (B13), `tests/test_costs.py`

- tokens convert to dollars with the price table
- the price table names its source and the date checked
- a model missing from the price table is an error, not zero cost
- each run records its tokens and cost

## Loading (B14), `tests/test_load.py` and dbt data tests

- loading a fixture file twice gives the same row count
- a column with the wrong type fails the schema check
- a second month loads with one command and keeps the first month
- dbt: a missing complaint ID fails the build
- dbt: a repeated complaint ID fails the build
- dbt: a Product outside the known list fails the build

## Samples (B9), `tests/test_data.py`

- the opening key ignores case, digits and redaction runs (reused)
- different openings have different keys (reused)
- dedupe keeps the first of each group, in order (reused)
- short text is not cut (reused)
- long text is cut at the limit and flagged (reused)
- the three sets never overlap and cover all rows (reused)
- big classes fill their quota (reused)
- a small class gives at most half to test and keeps training rows (reused)
- same seed gives the same split, a different seed a different test set (reused)
- the test set does not change when the development size changes (reused)

## Baselines (B11), `tests/test_baselines.py`

- the most-common-class baseline predicts the most common training label for every row
- TF-IDF is fitted on the training split only
- TF-IDF gives a label and a confidence for every row

## Metrics (B3, B10), `tests/test_metrics.py`

- quarantine counts as wrong in the strict figure (reused)
- nothing accepted gives no accuracy and zero strict accuracy (reused)
- a summary of nothing is an error (reused)
- the baseline is scored on its most confident share (reused)
- the baseline needs a coverage that keeps at least one item (reused)
- a clear win is "beats" (reused)
- a tie is not a win (reused)
- a loss is "does_not_beat" (reused)
- a small positive difference with a wide interval is "inconclusive" (reused)
- the same seed gives the same result (reused)
- inputs must describe the same complaints (reused)
- a pipeline that accepts nothing cannot be compared (reused)

## Pipeline (B4, B5, B9), `tests/test_pipeline.py`

- a good complaint is accepted and keeps its ID (reused)
- recorded Product, Issue and company never reach the model (reused)
- a complaint with no text is quarantined with no model call (reused)
- long text is cut and flagged, and the model sees only the cut text (reused)
- a quote from the cut part is not evidence (reused)
- text that tries to close the data section does not change the outcome (reused)

## Evaluation record (B15), `tests/test_evaluate.py`

- an evaluation appends exactly one row to `EVAL_VERSIONS.md`
- the row has prompt version, date, accuracy, coverage, quarantine rate, interval and cost
- evaluation refuses the frozen test set unless `final` is given
- a `final` run is written to the run log

## Hooks, `tests/test_hooks.py`

- test gate: a commit is blocked when tests fail
- test gate: a commit that changes only test files is allowed even when tests fail
- test gate: a commit is allowed when tests pass
- data guard: writing a file with the CFPB header row is blocked
- data guard: writing a `.env` file is blocked
- data guard: content that looks like an Anthropic key is blocked (the fake key is built while the test runs)
- data guard: a normal source file is allowed

## Later features (listed now, specified later)

- API: typed schemas, input checks, paging, error messages, request logging
- Browser: one end-to-end test per analyst task in `docs/USER.md`
