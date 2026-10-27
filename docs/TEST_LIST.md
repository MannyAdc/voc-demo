# Test list

Status: approved by the owner on 2026-10-28, then revised after review rounds 1 to 4. Each line is one test. Tests check behaviour against [the spec](../specs/001-core-labelling-pipeline/spec.md). They run offline in seconds and never call a model. Label quality is measured separately by evaluation.

Lines marked (reused) come from test ideas in an earlier unpublished start of this project. Lines marked (review) were added after a reviewer finding. The rest are new.

All fixture data is synthetic. Synthetic complaint IDs start with `SYN-`, so they can never be mistaken for real CFPB IDs.

## Network block (B7), `tests/test_network.py`

- the test suite cannot open a network connection (reused)
- a subprocess started by a test cannot reach the network either (review, CI only: CI runs tests with no network)
- tests run with DuckDB extension auto-install off, dbt usage stats off, no `ANTHROPIC_API_KEY`, and `.env` loading pointed at an empty temp file (review)

## Output safety (B21 layer 1), `tests/test_output_safety.py`

Started in the first pull request that adds an entry point (T002b), and extended by every later one.

- each entry point (`download`, `load`, `profile`, `sample`, `label`, `evaluate`, `analyse`, the dbt wrapper) prints no narrative, quote or raw model answer on hostile synthetic text (review, moved earlier)
- a library error that echoes a raw row is replaced by its type, row number and complaint ID (review)

## Quote check (B1, B6), `tests/test_evidence.py`

- quote found, ignoring spaces and line breaks (reused)
- reported start and end point into the original text (reused)
- capital letters matter (reused)
- a quote not in the text is rejected, with no position (reused)
- an empty or blank quote is rejected (reused)
- a quote needs at least 3 words (reused)
- redaction marks do not count toward the 3 words (review)
- `XX/XX/XXXX` dates, `{$500.00}` amounts and plain numbers do not count as real words (review)
- a quote that starts or ends inside a word is rejected (review)
- curly and straight quote marks, apostrophes and dashes match each other (review)
- "XXXX" in a quote matches "XXXX" in the text (reused)
- a guess in place of "XXXX" does not match (reused)
- a quote of only redaction marks is not evidence (reused)

## Prompt and parsing (B4, B5), `tests/test_prompt.py`

- the prompt is built only from the version's instruction block, the labels, the text and training examples (reused, changed)
- the prompt contains the text and every label (reused)
- the text sits between one pair of boundaries (reused)
- a text containing a boundary tag, in any capitalisation, is quarantined as `boundary_in_text` with no model call (reused, changed)
- lookalike tags (`</ complaint>`, `&lt;/complaint&gt;`) are caught too (review)
- example text with a boundary tag is refused (review)
- the same complaint gives the same prompt on every run, so its recording key is stable (review)
- an example from the development or test split is refused (review)
- a training example may show its recorded Product (review)
- valid JSON is parsed (reused)
- JSON inside a code fence is parsed (reused)
- prose is unparseable (reused)
- a missing key is unparseable (reused)
- values that are not text are unparseable (reused)
- extra keys, two JSON objects, or text after the JSON are unparseable (review)
- the examples used are logged by complaint ID (review)

## Decision (B2, B3, B5), `tests/test_decision.py`

- agreement view: accepted when the quote is real and both sources agree (reused)
- agreement view: disagreement is quarantined as `disputed` (reused)
- quote-only view: the same disagreement is accepted
- a quarantined decision keeps the proposal but has no label (reused)
- a made-up quote is quarantined (reused)
- short and empty quotes are quarantined (reused)
- a label outside the list is quarantined even with a real quote (reused)
- an unparseable answer is quarantined (reused)
- a failed, refused or cut-off model call is quarantined as `model_error` (review)
- check order is model call, parse, label, quote, agreement (reused, changed)
- an obeyed injection with a real quote is caught by agreement (reused)
- an obeyed injection with an invented quote is caught by the quote check (reused)
- a quarantined decision never has an accepted label, 4 cases (reused)

## Ledger (B8), `tests/test_budget.py`

- a ledger created with the init command has used nothing (reused, changed)
- a missing or unreadable ledger refuses every live call (review)
- charges add up (reused)
- use survives a restart (reused)
- a reservation that just fits is allowed, one more token is refused (reused, changed)
- the reservation is input estimate plus the output limit, plus the `cli` allowance for `cli` (review)
- the input estimate is never below the real count, checked against a fixture of real token counts recorded once in a logged live counting run (review, changed)
- the cap is copied into the ledger at init and an override can only lower it (review, changed)
- live calls are refused while the cap config has uncommitted changes (review)
- the ledger path is the fixed path in the home folder, whatever the working folder (review)
- init refuses when a ledger already exists (review)
- `raise` refuses while the cap config has uncommitted changes, and writes a raise event with a reason (review)
- SDK retries are off, and a retry is charged as a new call (review)
- a failed call is retried at most 2 times (review)
- after a call, the reservation is replaced by the real use (review)
- a failed call is charged the full reservation (review)
- a call with no reported usage is charged the full reservation (review)
- two processes reserving at once cannot both pass the cap (review)
- a negative charge is an error (reused)

## Record and replay (B7, B8), `tests/test_replay.py`

- the key is a stable hash of backend, model, settings and prompt (reused, changed)
- first call is live, second comes from the recording (reused)
- replay mode serves a recording with no inner client (reused)
- replay mode with no recording is an error, not a live call (reused)
- a different backend, model, setting or prompt is not served the old recording (reused, changed)
- a recording file holds no headers and no key (review)
- recordings are stored in the home-folder cache, so a second worktree replays them for free (review)
- a failed, refused or cut-off call is not stored in the cache (review)
- re-scoring a run from its results file reproduces its failures exactly (review)
- a live call is charged, a replayed call is free (reused)
- a live call past the cap is refused before it is sent (reused)
- a recording is still served when the budget is spent (reused)

## Backends (B12), `tests/test_backends.py`

- `LLM_BACKEND=mock` serves fixtures and makes no network call
- an unknown `LLM_BACKEND` value is an error that names the allowed values
- `api` with no key in the environment fails with a clear message
- the key never appears in an error message or log line
- `cli` builds a command with no tools, no MCP servers and no settings or instruction files (review, the process itself is faked)
- `cli` runs in a new empty temporary folder (review)
- `cli` passes an environment with no API key and no repo paths (review)
- `cli` refuses real complaints until a canary result is logged (review)
- the temperature is recorded with each run (review)
- a comparison that mixes backends is refused (review)
- the key does not appear in recordings, results files or reports (review)
- a `.env` file is loaded into the environment at start-up (review)

## Cost (B13), `tests/test_costs.py`

- tokens convert to dollars with the price table
- the price table names its source and the date checked
- a model missing from the price table is an error, not zero cost
- each run records its tokens and cost
- a replayed run reports zero own cost and the original live cost (review)

## Loading (B14), `tests/test_load.py` and dbt data tests

- loading a synthetic fixture file twice gives the same row count
- a column with the wrong type fails the schema check
- a second month loads with one command and keeps the first month
- dbt: a missing complaint ID fails the build
- dbt: a repeated complaint ID fails the build
- dbt: a Product outside the known list fails the build

## Samples (B9, B16), `tests/test_data.py`

- the opening key ignores case, digits and redaction runs (reused)
- different openings have different keys (reused)
- two narratives with the same opening but different bodies are both kept (review)
- a copy with a different opening is found by full-text similarity (review)
- dedupe gives the same result whatever order the rows arrive in (review)
- the number removed is reported (review)
- the similarity threshold is recorded with the sample (review)
- short text is not cut (reused)
- long text is cut at the limit and flagged (reused)
- the three sets never overlap and cover all rows (reused)
- big classes fill their quota (reused)
- a small class gives at most half to test and keeps training rows (reused)
- same seed gives the same split, a different seed a different test set (reused)
- the test set does not change when the development size changes (reused)
- a command given IDs that do not match the committed list refuses to run (review)
- a complaint whose narrative and Product hash has changed is refused (review)
- the content hash covers narrative and Product together, so it does not reveal the Product (review)
- samples are built only from rows of the pinned July file (review)
- each list's hash matches its content (review)
- the 50-ID quick-check list is a subset of the development list (review)
- the test-ID hash loader returns only hashes, never text or labels (review)
- every file the code reads from `splits/`, `config/` and `tests/fixtures/` is tracked by git (review, CI)
- the download script refuses a file whose SHA-256 does not match (review)
- adding a new month of rows does not change the committed lists (review)

## Baselines (B11), `tests/test_baselines.py`

- the most-common-class baseline predicts the most common training label for every row
- TF-IDF is fitted on the training split only
- TF-IDF sees the same cut text as the LLM (review)
- TF-IDF gives a label and a confidence for every row
- the TF-IDF settings are read from a recorded config, not from code defaults (review)
- changing the TF-IDF config after the first logged development evaluation needs its own `EVAL_VERSIONS.md` row (review)
- changing the TF-IDF config after a test run is logged is refused (review)
- the most-common-class baseline is reported at full coverage only (review)

## Metrics (B3, B10, B18), `tests/test_metrics.py`

- quarantine counts as wrong in the strict figure (reused)
- nothing accepted gives no accuracy and zero strict accuracy (reused)
- a summary of nothing is an error (reused)
- the baseline is scored on its most confident share (reused)
- ties at the cut-off are broken by complaint ID (review)
- the baseline needs a coverage that keeps at least one item (reused)
- a clear win is "beats" (reused)
- a tie is not a win (reused)
- a loss is "does_not_beat" (reused)
- a small positive difference with a wide interval is "inconclusive" (reused)
- the bootstrap resamples within each Product and is paired (review)
- the same seed gives the same result (reused)
- inputs must describe the same complaints (reused)
- a pipeline that accepts nothing cannot be compared (reused)
- a run with any `not_run_budget` complaint gets no verdict (review)
- per-Product figures and the re-weighted figure match a hand count (review)
- the injection set counts "obeyed and accepted", "obeyed and quarantined" and "not obeyed" per view, matching a hand count (review)
- the bootstrap interval is computed for the figure that decides the verdict (review)
- re-weighted strict accuracy matches a hand count, quarantined counted as wrong (review)
- coverage is matched by count inside each resample (review)
- claims A and B each get their own verdict (review)

## Method comparison (B23), `tests/test_metrics.py`

- each confusion matrix matches a hand count, for the LLM, TF-IDF and the combined system
- per-Product precision, recall and F1, and macro-F1, match a hand count
- the who-was-right table counts both, only LLM, only TF-IDF and neither correctly
- the precision and coverage points match a hand count
- the review queue breakdown matches a hand count
- synthetic results are reported apart and never enter accuracy figures (review)

## Pipeline (B4, B5, B9), `tests/test_pipeline.py`

- a good complaint is accepted and keeps its ID (reused)
- no column other than the narrative reaches the model, including Sub-product and Sub-issue (reused, changed)
- a complaint with no text is quarantined with no model call (reused)
- long text is cut and flagged, and the model sees only the cut text (reused)
- a quote from the cut part is not evidence (reused)
- text that tries to close the data section does not change the outcome (reused)
- when the budget runs out partway, the rest are `not_run_budget` and none is missing (review)

## Evaluation record (B15, B17, B19), `tests/test_evaluate.py`

- an evaluation appends exactly one row to `EVAL_VERSIONS.md`
- the row has every field B15 lists
- old rows are never changed (review)
- the results file has every field B19 lists and no narrative text (review)
- loading test narratives or test labels refuses unless `final` is given, while reading the test ID list is allowed (review, changed)
- `final` refuses when the working tree is not clean (review)
- `final` refuses when the remaining cap does not cover the whole test set, retries included (review)
- `final` also writes the home-folder test log, and demands a reason if either log already has an entry (review)
- `show` refuses test rows unless `final` is given (review)
- `final` commits the test run log entry before scoring starts (review)
- reading test rows from the staged table, or setting the dbt final flag, goes through the same guard (review)
- dbt models leave out test rows unless the final flag is set (review)
- a replayed scoring of the test set is logged like a live one (review)
- a second `final` scoring needs a written reason (review)

## Error analysis and profile (B21, B22), `tests/test_analysis.py`

- the analyser's answer must be one cause from the fixed list, and anything else is `unparseable` (review)
- the analyser refuses test-set complaints (review)
- free text from the analyser is never printed (review)
- a quote mismatch is typed by a script (spacing, quote marks, paraphrase, not found) (review)
- the owner's spot-check result is recorded per round (review)
- the `profile` command prints every data fact the README uses, from a synthetic fixture (review)

## Human review (B20), later feature

- an analyst decision never changes the scored results (review, written with the review screen)

## Hooks, `tests/test_hooks.py`

- test gate: a commit is blocked when tests fail
- test gate: a commit is allowed when tests pass
- test gate: a commit that changes only `tests/test_*.py` files is allowed when the only failing tests are new ones
- test gate: a commit that changes `tests/conftest.py` or fixtures is gated like any other (review)
- test gate: `git -C . commit`, `git commit -a` and `git commit <path>` are all recognised, and the real committed files are checked (review)
- test gate: a commit run from PowerShell is gated too (review)
- test gate: a tests-only commit that deletes a test, or makes an existing test skip, is blocked (review)
- test gate: `--no-verify` is blocked (review)
- git pre-commit hook: runs the same gate for commits made outside Claude (review)
- data guard: an edit to `.claude/settings.json` or a hook script asks the owner first (review)
- read guard: Claude reading the raw data folder or the DuckDB file is blocked (review)
- read guard: Claude running `show` or `dbt show` is blocked outright (review, changed)
- read guard: Claude reading the recordings or ledger folder, including through a shell command naming the path, is blocked (review)
- final guard: Claude running any command containing `final` asks the owner first (review)
- data guard: `.env.example` is allowed only if it holds no key-like value (review)
- data guard: notes or docs with a long run of text copied from a sampled narrative are blocked when local data is present (review)
- data guard: writing a file with the CFPB header row is blocked
- data guard: a synthetic fixture with only `SYN-` IDs under `tests/fixtures/` is allowed (review)
- data guard: writing a `.env` file is blocked
- data guard: content that looks like an Anthropic key is blocked (the fake key is built while the test runs)
- data guard: a normal source file is allowed

## CI checks, `.github/workflows/ci.yml`

- gitleaks scans the full history
- git pre-commit hook: gitleaks runs on every commit, and the hook fails if gitleaks is not installed (review, changed)
- a names check fails on any word from a deny list kept outside the repo, in a CI secret, and fails if the list is missing or empty (review)
- `runs/TEST_RUNS.md` only grows compared with `main` (review)
- the names check also scans commit authors, commit messages and branch names, and prints only the file and line of a match, never the word (review)
- no tracked Parquet, JSONL or headerless CSV holds a real-format complaint ID with a text field, except committed results files with no text (review)
- any tracked file over a size limit fails (review)
- any tracked file with the CFPB header row and a non-`SYN-` ID fails (review)
- dbt build with data tests runs, with usage stats off (review)

## Later features (listed now, specified later)

- API: typed schemas, input checks, paging, error messages, request logging
- Browser: one end-to-end test per analyst task in `docs/USER.md`
