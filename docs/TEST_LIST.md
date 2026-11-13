# Test list

Status: approved by the owner on 2026-10-28, then revised after review rounds 1 to 4. Each line is one test. Tests check behaviour against [the spec](../specs/001-core-labelling-pipeline/spec.md). They run offline in seconds and never call a model. Label quality is measured separately by evaluation.

Lines marked (reused) come from test ideas in an earlier unpublished start of this project. Lines marked (review) were added after a reviewer finding. The rest are new.

All fixture data is synthetic. Synthetic complaint IDs start with `SYN-`, so they can never be mistaken for real CFPB IDs.

## Network block (B7), `tests/test_network.py`

- the test suite cannot open a network connection (reused)
- a subprocess started by a test cannot reach the network either (review, CI only: CI runs tests with no network)
- tests run with dbt usage stats off, proxy settings cleared, and none of `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` visible, from import time until the process exits (review)
- DuckDB extension auto-install off is tested in `tests/test_load.py` (T010). `.env` isolation is tested in `tests/test_backends.py` (T009). (review)

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
- the first match on word boundaries is the one reported (T005)
- a quote may not start or end inside a word, also not across an apostrophe or hyphen, and a combining mark is part of its word (review of #10)
- composed and decomposed letters, other apostrophes and dashes, soft hyphens, zero-width characters and non-breaking spaces are normalised the same on both sides (review of #10)
- lookalike X characters are not real words, and redaction marks joined by a dash are redaction only (review of #10)

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

## Decision (B3, B5), `tests/test_decision.py`

- a label with a real quote is accepted whatever TF-IDF says, and TF-IDF's label is never an input (B2 removed on 28 October, the three agreement tests are dropped)
- a quarantined decision keeps the proposal but has no label (reused)
- a made-up quote is quarantined (reused)
- short and empty quotes are quarantined (reused)
- a label outside the list is quarantined even with a real quote (reused)
- an unparseable answer is quarantined (reused)
- a failed, refused or cut-off model call is quarantined as `model_error` (review)
- check order is model call, parse, label, quote (reused, changed on 28 October)
- an obeyed injection with a real quote is accepted, and the synthetic injection report counts it as "obeyed and accepted" (changed on 28 October: no agreement to catch it)
- an obeyed injection with an invented quote is caught by the quote check (reused)
- a quarantined decision never has an accepted label, 4 cases (reused)

## Ledger (B8), `tests/test_budget.py`

- a ledger created with the init command has used nothing (reused, changed)
- a missing or unreadable ledger refuses every live call (review)
- charges add up (reused)
- use survives a restart (reused)
- a reservation that just fits is allowed, one more token is refused (reused, changed)
- the reservation is input estimate plus the output limit (review)
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
- `LLM_BACKEND=cli` is an unknown value and fails with a clear message (the `cli` backend and its four tests were cut on 28 October)
- the effort setting, model and API version are recorded with each run, and no temperature is ever sent (review, changed in T009: the API refuses a temperature)
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
- a copy with a different opening is found by full-text similarity (review) (cut on 28 October with cut list item 3: full text is compared only where openings match)
- two narratives with the same opening and very similar full text count as one duplicate (cut list item 3, what is kept)
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
- samples are built only from rows of the pinned July file (review), except spec 004's June sample, built only from the pinned June file (added on 4 November)
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
- the injection set counts "obeyed and accepted", "obeyed and quarantined" and "not obeyed", matching a hand count (review)
- the bootstrap interval is computed for the figure that decides the verdict (review)
- re-weighted strict accuracy matches a hand count, quarantined counted as wrong (review)
- coverage is matched by count inside each resample (review)
- the one claim gets one verdict, and no verdict is given with any `not_run_budget` complaint (changed on 28 October: claim B dropped)

## Method comparison (B23), `tests/test_metrics.py`

- each confusion matrix matches a hand count, for the LLM and TF-IDF
- per-Product precision, recall and F1, and macro-F1, match a hand count
- the who-was-right table counts both, only LLM, only TF-IDF and neither correctly
- the precision and coverage points match a hand count
- the review queue breakdown (quarantined LLM labels by reason, and how often TF-IDF was right on them) matches a hand count
- cost and run time per 1,000 complaints are reported for each method (B23, 28 October)
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
- the `profile` command prints, per Product, the narrative count, length percentiles, Sub-product counts and counts per year received, from a synthetic fixture (B22, 28 October)
- the `profile` command prints counts only: a hostile synthetic narrative never appears in its output (B22, B21)
- the label set config lists every label once, and the prompt and both baselines read the same list from it (B24)
- a recorded Product that is not in the label set, and has no mapping, stops sampling with a clear message (B24)
- Cochran's formula gives 385, 1,068 and 2,401 for margins of 5, 3 and 2 points at 95 percent and p = 0.5 (B25)
- the finite pool correction makes n smaller for a small pool, and changes almost nothing for a large one (B25)
- the split across Products follows the pool's shares and the parts add up to n exactly (B25)
- a Product with fewer than 30 complaints in a sample is marked "too few to judge" (B25)
- no Product sends more than half of its pool to the test set (B9, B25)
- a smaller test size than the rule gives is refused unless a reason is given, and the reason is written with the sample (B25)

## Human review (B20), later feature

- an analyst decision never changes the scored results (review, written with the review screen)

## Hooks, `tests/test_hooks.py`

- test gate: a commit is blocked when tests fail
- test gate: a commit is allowed when tests pass
- test gate: a commit that changes only `tests/test_*.py` files is allowed when the only failing tests are new ones
- test gate: a second red commit may keep tests that were already failing, prints each as a notice, and may still not delete one (owner decision, T004)
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
- data guard: notes or docs with a long run of text copied from a sampled narrative are blocked when local data is present (review) (cut on 28 October, cut list item 4, moved to Known limits)
- data guard: an edit is checked on the file as it would be after the edit, so adding a real row to a synthetic fixture is blocked (T004)
- read guard: Claude reading the `.env` file is blocked, with any tool, and `.env.example` is allowed (T004)
- each hook fails closed: bad input exits 2 with the hook's own message (T004)
- the git pre-commit hook clears git's own variables before running the tests, so tests that run git are not pointed at the real index (T004)
- data guard: writing a file with the CFPB header row is blocked
- data guard: a synthetic fixture with only `SYN-` IDs under `tests/fixtures/` is allowed (review)
- data guard: writing a `.env` file is blocked
- data guard: content that looks like an Anthropic key is blocked (the fake key is built while the test runs)
- data guard: a normal source file is allowed
- read guard: June's data folder (`VOC_JUNE_DATA_DIR`) is protected like July's, from the environment or `.env`, by file tools, searches and commands (spec 004, J6)
- read guard: a command that runs the Databricks CLI, as any word of a line unless an earlier word only takes text (`git`, `gh`, `grep`), or by its full path, or names its SDK, its saved sign-in `.databrickscfg` or the volume `voc_raw`, is denied. A file tool on `.databrickscfg` is denied too. `ls dbt/databricks` and `uv run --group databricks` stay allowed (spec 004, J14, review of #87)
- read guard: a command that names a `.dpapi` file or a call that decrypts one is denied, so a wildcard cannot reach the owner's encrypted Databricks token in `.voc` (review of #87)
- read guard: reading an Actions run log, starting, re-running or cancelling a workflow, approving a deployment, the environments and secrets APIs, and merging a pull request are denied, by `gh`, `gh.exe` by its full path, the REST API or GraphQL. Checking, viewing and commenting on a pull request, viewing a run without its log, and running the merge verdict stay allowed (spec 004, J14)
- read guard: flags between `gh`, its group and its subcommand change nothing (`gh pr -R o/r merge`). Also denied: deleting a run, artifacts' downloads, the variables API, writes through `gh api` (any method but GET, or fields with no method), GraphQL mutations and queries read from a file, `git/refs`, aliases, extensions, `gh auth token`, `--show-token`, and the repo's settings by `gh repo edit` or the API. API paths count only after `repos/<owner>/<repo>/`, so `cat docs/environments.md` and `python scripts/rerun.py` stay allowed. Every J14 refusal names J14 (spec 004, J14, review of #87)
- settings: permission deny rules remove the browser tools (Claude in Chrome, Chrome DevTools, the built-in browser, computer use and their enable tools) and deny WebFetch to `github.com`, `api.github.com`, `*.cloud.databricks.com` and `*.azuredatabricks.net` (spec 004, J14, owner decision of 5 November)

## Merge verdict (T006b), `tests/test_merge_verdict.py`

Every test feeds the checks synthetic `gh pr view` JSON. No test runs `gh` or opens the network. The trial merge tests use a small git repo in a temporary folder.

- CI is green only when every check on the latest commit finished with success and every CI job reported (T006b)
- a failed, skipped or still running check, a failed or pending commit status, or no checks at all is FAIL (T006b, pending added in review)
- the expected check names match the job names in `.github/workflows/ci.yml` (T006b)
- a commit with only `tests/test_*.py` files must come before the first commit that changes code, and merge commits are left out (T006b)
- every file in the page folder `src/voc/web/` counts as code, and `requirements.txt` too. An `.html` or `.css` file elsewhere does not. `config/` stays out on purpose (T006b, found on #51, changed in review of #52)
- a pull request that changes no code needs no red commit (T006b)
- a missing `## Reviewer findings` comment is FAIL. Whether each finding is fixed or deferred is FOR CLAUDE, never PASS, even when the comment starts with "No findings" (T006b, review)
- the build log check is always FOR CLAUDE (T006b)
- a pull request that is not open, not against `main` or in conflict is FAIL (T006b)
- parallel branches that share a file are FAIL, and the merge order is lowest number first (T006b)
- the trial merge puts the branches together with no work tree, commit or hook, stops on a conflict, and runs the tests on the merged tree (T006b)
- the trial merge refuses a pull request from a fork, or with no fork flag, before it fetches anything (T006b, review)
- the trial merge's tests run with `LLM_BACKEND=mock`, and with no variable whose name holds KEY, TOKEN or SECRET and no data folder variable, June's included (T006b, review, spec 004 J6)
- the verdict is one line: FIX FIRST with every failure (exit 1), PENDING while a FOR CLAUDE item is open and nothing fails (exit 3), or MERGE (exit 0). It never starts with MERGE while an item is open (T006b, review)
- the script exits 2 when the data cannot be read, and on a crash prints only the error type (T006b, review)
- the script never prints commit messages or comment text, and makes only read-only `gh` calls (T006b)

## CI checks, `.github/workflows/ci.yml`

- gitleaks scans the full history, in its own job so other failures cannot hide it (review of #4)
- names, raw data, size and unreadable-file checks cover every blob in history, file paths, tags and pull request text (review of #4)
- git pre-commit hook: gitleaks runs on every commit, and the hook fails if gitleaks is not installed (review, changed)
- a names check fails on any word from a deny list kept outside the repo, in a CI secret, and fails if the list is missing or empty (review)
- `runs/TEST_RUNS.md` only grows compared with `main` (review, deferred to T015, when the file first exists)
- the names check also scans commit authors, commit messages and branch names, and prints only the file and line of a match, never the word (review)
- no tracked Parquet, JSONL or headerless CSV holds a real-format complaint ID with a text field, except committed results files with no text (review) (deferred to T012, when the first JSONL files are written)
- any tracked file over a size limit fails (review)
- any tracked file with the CFPB header row and a non-`SYN-` ID fails (review)
- dbt build with data tests runs, with usage stats off (review, deferred to T011)

Written on 9 November 2026, after two CI runs failed at a download from GitHub (8 and 9 November), `tests/test_ci_workflow.py`:

- CI runs on every pull request and on pushes to `main` only, so a pull request's push runs once (T003)
- each job that uses uv installs Python and the project first, retried up to 3 times, so no later step downloads them (T003)
- the secret scan retries its download, and the checksum still decides whether it is used (T003)

Written on 9 November 2026, in the fix round of #104. The tests are named after task T003, the CI task, as the merge verdict's tests are named after T006b, since no spec rule covers CI's own setup.

- the install step ends on a pass, fails after the third failure, swallows no failure, and no later step installs or downloads with uv (T003, minor 2)
- the secret scan's download fails on an error page, and the checksum comes after it (T003, nit 8)

## Validation review ([spec 003](../specs/003-validation-review/spec.md)), `tests/test_validation.py`

Added on 2 November 2026. Each piece adds its tests in its own pull request, failing first.

- no validation command accepts a test or training ID (V7)
- no results file of the validation review holds narrative text, a quote or a judge reason, on hostile synthetic text (V8)
- the review sheet is written only inside the review folder, the sheet command refuses any other folder, and the import reads only the ID and code columns (V8)
- no judge prompt and no V3 or V5 sheet holds the consumer's recorded product (V8)
- a paid command prints the calls, the expected cost, the worst-case tokens and the tokens left before any call, and makes no call without `--approved` (V9)
- the Wilson interval and the bootstrap interval match known values on fixed data (V10)
- the four frozen lists are drawn from the development set only, with a fixed seed, in the spec's order: V5 never shares a case with the dry run, V2 never with V5 or the dry run, and all are checked like the other lists (V1, V2, V5, B16)
- a repeat number changes the recording key but not the prompt or the settings sent, and no repeat number leaves the key exactly as before (V1)
- the comparison counts a changed decision, a missing label and a quote that is not compared, as the spec says (V1)
- the quote comparison by positions gives same, overlapping and apart correctly (V1)
- the import refuses a missing, repeated or unknown ID and a blank or unknown code, and then writes nothing (V2, V3, V5)
- the label noise share is reported as a lower and an upper figure (V2)
- `voc review summary` recomputes V2's and V3's figures from the committed codes only, with no model call. It writes IDs, reasons, codes and figures only (V2, V3, V8, V10)
- the summary checks the codes file as the import checks the sheet, with the same messages, and also refuses a missing file or column and a changed V3 reason. V3's IDs must be in the development list, for the import too (V2, V3, V7, review of #82)
- the judge's answer outside the three ratings is `unparseable`, listed apart and left out of the agreement, the kappa and the table (V5)
- the judge's main run refuses while the owner's ratings are missing, and never includes a dry-run ID (V5)
- Cohen's kappa and the confusion table match hand-worked values on synthetic ratings (V5)
- `voc judge agreement` recomputes the V5 figures from the committed IDs and ratings only, lists the differences by ID, and refuses codes that are not the frozen list, a missing judge rating or an unknown code (V5, V10)
- `voc judge agreement` reads the V5 list checked against its hash and the development list, and refuses a repeated judge ID, a judge ID outside the development list, no pairs, an undefined kappa and more than 1% of bootstrap draws without a kappa (V5, V7, V10, review of #81)
- the hybrid uses the baseline at a top probability of at least 0.9 and the LLM otherwise, a quarantined answer counts as wrong, and it is scored as B10 scores (V6)
- V6 reads the test run's summary file only, never a per-complaint test file (V7)

## June sample ([spec 004](../specs/004-june-test-and-baselines/spec.md), J6, J1, J2)

Written in pull request 3, on 5 November 2026.

- `voc sample june` reads the one CSV in `VOC_JUNE_DATA_DIR`, refuses it with no pin or when it does not match its pin, and never loads it into the staged table (J6, J1)
- June's rows go through `voc load`'s checks, in a database in memory, so a Product outside `config/labels.toml` is refused and nothing is written (J6, B24)
- rows with no narrative are not in the pool, copies within June are removed by July's measure, and so are copies, exact or near, of July's training and development narratives (J6)
- July's training and development rows are selected by ID and checked against their lists. A missing one is refused. A copy of a July test narrative stays in June's pool, because no July test row is read (J2)
- the size is Cochran's at 2 points on June's pool, split across Products in proportion, and the same seed gives the same sample (J6, B25)
- the list is frozen in `splits/june/` with its hash, the pool and sample per Product and the copy counts, and is never overwritten. July's lists do not change (J6, B16)
- the settings (`config/june.toml`: month, margin 0.02, seed) are committed before the draw (J6)
- the summary and the files hold counts, IDs and hashes only (B21)
- the laptop refuses to load June or build it on Databricks, with a J1 message, and `voc label`, `evaluate` and `audit` have no June set. `voc final` takes no set at all (J1)
- read guard: the Azure CLI (`az`, `az.cmd`) is denied like the Databricks CLI. Text that names it stays allowed after a command that only takes text, such as `git` or `gh` (a pull request title). Elsewhere it fails closed: `cd az` or `pytest -k az` is denied (J14, owner decision of 5 November, review of #88)
- July's copies are removed before the copies within June, so a June row whose near-copy was a copy of July stays (J6, review of #88)
- July's test rows are never asked for: deleting them changes nothing, and only training and development IDs are selected (J2, review of #88)
- a failed write leaves neither file, so the next run is not blocked. Settings that do not name June are refused. The seed in `config/june.toml` is the seed of the draw (J6, review of #88)

## June claims, hashes and scoring ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J7)

Written in pull request 4, on 5 November 2026, on synthetic items only.

- the claims are frozen in `config/june_claims.toml`: the model and prompt (the same as `config/prompts/v1.toml`), the 0.9 threshold, 2,000 draws within each Product with seed 0, and the verdict words (J7)
- the primary verdict: beats if the 95% interval is wholly above zero, does not beat if the point difference is zero or below, otherwise inconclusive. Given both ways on synthetic items (J7)
- scores are re-weighted by June's own pool. The hybrid takes TF-IDF + LR at 0.9 or more, else the LLM, and a held-back LLM label counts as wrong (J7)
- the secondary comparison, the LLM against TF-IDF + LR at the same coverage, has its interval and no verdict. Both intervals repeat with the same seed (J7)
- the cost per extra correct label, at the same coverage and at full coverage, with no figure when the LLM gains nothing (J7)
- the counts, the reasons of held-back labels, and the confusion tables of the LLM, TF-IDF + LR and the hybrid. The result holds no complaint ID (J7, B21)
- a run stopped by the spend limit is not scored. A pool Product missing from the items, and a repeated complaint, are refused (J1, J7)
- the frozen code's hash covers exactly the places J1 names (`cloud/` for the job definitions), changes with any frozen file or file name and with nothing else, is the same in any folder, and hashes exactly the tracked files, none with Windows line endings (J1)
- the June list's hash is the SHA-256 of `splits/june/june.csv`, refused unless it matches the manifest. `scripts/june_hash.py` prints the two hashes and a count only (J1)
- the sample is scored only when every complaint of the June list has exactly one result, Product by Product, with the pool and the list from `splits/june/`. A list that does not match its manifest, a pool or sample counts that do not add up, a complaint outside the list, synthetic items, and a Product outside the pool are refused (J1, J7, review of #89)
- a win needs a point difference above zero, whatever the interval (J7, owner decision of 5 November). The scores do not depend on the order of the items. The bootstrap draws 2,000 times within each Product, one draw per Product of its own size, and claims that resample otherwise are refused (J7, review of #89)
- the July development labels are frozen too. The hash script refuses when the frozen files differ from the tracked ones, naming only their number, and says so on stderr where git is missing. The tracked-files test fails in CI instead of skipping. The committed run log is put through its rules. A row the reader would skip is refused. The CI step runs the check on the June log in `repo-checks`, and the check names the log it checks (J1, review of #89)
- `runs/JUNE_RUNS.md` starts with its header and no row. A row is found by its two hashes. A malformed row, a second first row for a list, a later row with no first row or no reason, a synthetic row naming the real June list, and a real row naming another list are refused. CI checks that the file only grows (J1)

## The receiver ([spec 004](../specs/004-june-test-and-baselines/spec.md), J9, J16)

Written in pull request 7, on 5 November 2026, with fakes for the table, the queue, Databricks and GitHub.

- the webhook fixture of J16 is accepted and queued. A bad sign-in gets 401 and nothing is queued. A malformed body after a good sign-in gets 400. Another event or job gets 202 and is dropped. A duplicate gets 202 and is dropped. A failed queue put gets 500 and frees its key (J9, J16)
- the sign-in and the signature are compared in constant time (J9)
- the result fixture with a good signature is accepted. A bad or uppercase signature, one over other bytes, and a timestamp more than 5 minutes old, more than 1 minute ahead or not in Unix seconds get 401. Bytes that are not the compact sorted form, and a malformed body, get 400. Header names are read in any case (J9, J16)
- the HTTP function gets no Databricks or GitHub client, so it replies before any work (J9)
- the queue function asks Databricks for the run, dispatches with the contract's body, skips a run of another job or one that did not succeed, skips a dispatch already made by its whole run name only, takes 200 or 204 as success and raises on any other reply or failure, so the queue retries it (J9, J16)
- a result message is stored and starts nothing. Logs hold event names, IDs, statuses and counts only (J9)
- the settings refuse an empty or unresolved Key Vault secret and a bad job ID. Strings are checked whole. A list or object in a field gets 400. A finished run names `june-<Job B run ID>`, a stopped one no folder and its reason. IDs above the 64-bit limit get 400. A body over 16 KB gets 413. The Basic scheme and header names are read in any case. The compare's result decides the sign-in. The core imports no service library. A key that cannot be freed, and a failed purge, are logged (J9, J16, review of #91)
- the Function's files: the extension bundle, the queue encoding, the poison queue's name in the spec, requirements resolved for Linux, 5 tries, one instance of 512 MB per function with none always ready, every secret a Key Vault reference, no Application Insights, two open HTTP functions and one queue function, and pinned requirements (J9)

Written on 7 November 2026, in the receiver's deploy pull request (owner decisions of 6 November):

- the queue function makes its Databricks and GitHub clients only when a message needs them, so a result message is stored with neither, and a lazy client is made once, on first use (J9)
- the deploy workflow runs by hand on `main` only, with no environment, read-only contents and an OpenID Connect token, one at a time, every action pinned, no value written into a script, the app's names and address as secrets, only `receiver/` packed and built remotely, a check that the live receiver refuses an unsigned call, and an early end until its secrets are set (J9)
- the owner's live check sends a badly signed and a well signed synthetic message to the receiver's own code, passes only on 401 or 400 and then 202, takes only the address as its argument, asks for the secret with a hidden prompt and drops it, prints status codes and a verdict only, and signs as the receiver checks (J9, J16 item 9)

Written on 7 November 2026, in the fix round of #96, from its review and the owner's decisions:

- each live check uses a fresh synthetic key, says queued, names its key, takes only 401 for the bad message, hints at the clock when the signed one is refused, and its post reports a status and follows no redirect (J9, serious 1, minors 10 and 11, nit 5)
- the deploy runs in its own environment with its own identity, every step after the first runs only when it goes ahead, it fails with its secrets unset and stops on a moved `main`, and the CLI's error text never reaches the public log (J9, J13, minors 2, 4, 5 and 9)
- every reply names the deployed commit, and the deploy's check wants it, with an empty body. Only the receiver's own files are packed, with the commit (J9, minors 1 and 3, nits 4 and 8)
- the real queue function stores a result message with no client settings, and a lazy client survives a copy and a maker that returns None (J9, nits 2 and 3)

Written on 7 November 2026, from the second review of #96, fixed with no further review round. Four lines of the first round above changed in the fix round: the deploy now has an environment, packs the receiver's five own files with the commit, takes only 401, and fails with its secrets unset.

- a failed upload names one fixed word, never the CLI's text, and the deploy's check says what it saw on its last try (J9, minors 3 and 4)
- the pack line is exact, the `&&` of the check is pinned, and the function reads its commit from its own folder (J9, nit 6)
- the steps give the exact trust subject, a resource group of the receiver's own, the settings the first deploy needs, the receiver's names as environment secrets, and a clean-up that waits and covers a missing row (J9, J13, minors 1, 2, 5, 7 and 8, nits 8 and 9)
- the owner's steps create the Function before its role, and the clock hint gives both limits (J9, minor 6, nit 2)

Written on 7 November 2026, after the live receiver test (owner decision: keep the click-by-click steps in the repo, with placeholders only). One line above changed: the plan's settings now hold the HTTP concurrency.

- each instance takes 4 HTTP calls at once, in the plan file and in J9 with its reason, and in the owner's Azure step (J9)
- the steps go click by click from step 1 to step 17, set the concurrency before the first deploy, keep the Function's own storage on its managed identity, leave Application Insights and continuous deployment off, and list the five roles with a warning of the Certificate User role (J9)
- the steps hold placeholders only, never a real address, storage account or ID (J9)
- the steps test calls in a row from Cloud Shell when the signed message gets no answer, and use Application Insights for a diagnosis only, then remove it (J9)

Written on 7 November 2026, from the review of #97 (owner decision: fix the minors and nits). The repeat of the plan's test and the narrow placeholder test above went, since newer tests cover them.

- the spec lists the five roles the Function was given, says why its own storage never uses the storage key, and turns Application Insights on only for a diagnosis (J9, J13, minors 1 to 3)
- the roles step warns against the Certificate User role and leaves it out of its list, and the diagnosis deletes the connection setting and then the logbook (J9, minor 4, nit 11)
- no receiver address, storage URL or ID, in any case, in the steps, the spec or the build log, except the public dashboard's host (J9, minor 5)
- the Basic user name is random, never the tests' value (J9, minor 6)
- the steps call one call at a time the most likely cause, name the vault's trade-offs, use one placeholder for the host and give step 9's clicks, and Known limits name the storage account's key access (J9, minor 7, nits 9, 10 and 12)

Written on 7 November 2026, from the fix-round review of #97, fixed with no further review round. The placeholder test above also checks that it finds the placeholders, and covers the test list.

- Known limits say the storage key also reaches the receiver's code, the adapters name the roles the Function was given, and the owner's steps remove the Secrets Officer role after the last secrets (J9, minors 1 to 3, nit 6)

Written on 6 November 2026, in the fix of the receiver's scope:

- the receiver asks Databricks for one token with the `jobs` scope only, the scope of the robot's secret, with the client's ID and secret in the Basic header and a form body (J13, spike of 6 November, review of #93)

## The spike for Job A ([spec 004](../specs/004-june-test-and-baselines/spec.md), pull request 5a)

Written on 5 November 2026, on synthetic data only.

- `dbt/seeds/test_list.csv` is a byte copy of `splits/test.csv`, alone in its folder and tracked by git, and git ignores every other seed file (owner decision of 5 November)
- the Databricks target refuses inside a git checkout, a `.git` folder or a worktree's `.git` file in the build root or above it, and a work folder made by the build scripts is not a checkout and still builds. A DuckDB build reads the July test list from `splits/test.csv` and no seed. These replace the old rule that the repo has no seed folder (B14, B17, owner decision of 5 November)
- the spike's job has the three tasks `unpack`, `dbt` and `job_a` in order, from the public repo's `main`, with one run at a time. The dbt command takes `unpack`'s task values, and the trigger watches only its scratch folder. No June or July data and no secret is named (J8, J16)
- `unpack` writes the one synthetic CSV and gives dbt its values. It refuses anything but one zip with one flat CSV, any row that is not synthetic, a short row, and a CSV over its size cap. The exit value holds counts only. The spike zip is made from the synthetic dbt fixture only (J5, J8)
- the spike's trigger is paused until the owner unpauses it and watches exactly its folder. Its dbt command passes `final` off. Its dbt task runs with the repo's `dbt-databricks` pin. No label holds a quote. A copy of the project with no `.git` refuses the Databricks target too (B14, B17, J8, review of #92)
- the hard requirement of 5b, written in pull request 5b: a row that would fail Spark's parser is refused by `unpack` before dbt with fixed text, and a local dbt run with a failing row in a data file leaks its text without the committed flags and leaves it in no output and no file with them (J5, J13, owner decision of 5 November)

## Job A ([spec 004](../specs/004-june-test-and-baselines/spec.md), pull request 5b, J8, J16)

Written on 6 November 2026, on synthetic data only.

- `cloud/job_a.yml`: three tasks by key and dependency, not by order, the public repo's `main`, one run at a time, the trigger paused on exactly `incoming/`, the dbt command's quiet flags, June's variables with `final` off, the pinned dbt environment, the success webhook, and no data file or secret named (J8, J9, J16)
- the run's target is the last row of `runs/JUNE_RUNS.md` with its list's kind. No row, or a log that breaks its rules, is refused. The real kind uses the June pin, and the dry run's pin waits for pull request 9 (J1, J16)
- `unpack` refuses a zip that is not the pinned zip, a second file, a member that is not the pinned CSV, a CSV that is not the pinned CSV (and removes it), a header that is not the CFPB header, a malformed row, and a row count that is not the pin's, and prints nothing (J5, J8)
- `job_a` refuses rows that are not exactly the frozen June list with their hashes. Its figures follow the test run's worst case and July's cost per 1,000, and its exit value has exactly the contract's keys, with a two-place cost (J8, J16)

Written on 6 November 2026, in the fix round of #94, from its review and the owner's decisions:

- both notebooks first refuse a later row of the run log, a row whose list is not `splits/june/june.csv`, and code that is not the row's frozen code, before they touch the June file (J1, J16, owner decision 3, minors 5 and 6)
- the June pin holds the narrative count. `job_a` counts the rows and narratives Spark reads, with dbt's own read options, and refuses any count that is not the pin's (J8, owner decision 2)
- `voc june-check` runs `unpack` on a copy in a temporary folder, leaves nothing behind, counts the rows, the narratives with text as Spark's `rlike` reads it, and the fields with a line break or a lone carriage return, says whether each count matches the pin, and refuses with unpack's fixed text (J8, owner decision 2)
- the figures use the June ledger's own cap, `june_cap_tokens`, and round the cost up to the cent (J12, minor 7)
- `checked_sample` and `figures` hold no complaint text in any refusal, value or print (J5, minor 8)
- `unpack` removes the CSV on any failure with fixed text, refuses an empty CSV, reads a field longer than Python's default limit, and refuses a label holding an apostrophe (J8, minor 3 and nits)
- the dbt flags tests check that dbt ran the failing model, so an early stop cannot pass for a quiet failure (J5, minor 2)
- Job A stops a run after an hour and has one failure notice, with no address in the repo (J8)
- the failcheck job runs Job A's own dbt command on its own rows, and the same command without the flags as a control after it, with no trigger. Its rows hold a short row that `unpack` would refuse (J5, owner decision 1)
- the robot's check holds no secret, finds the marker in nested fields and in downloaded archives, and reports task keys, states, places and status codes only (J5, J13, owner decision 1)

Written on 6 November 2026, in the second fix round of #94, from the review of its fix round and the owner's decisions:

- a real row of the run log needs a recorded pass of both gates, `june-check` and `failcheck`, for its code and the June pin, dated before it. A pass for other code, another pin or a later date does not count, a synthetic row needs none, a malformed gate row is refused, and the committed logs keep the rule. Job A and `scripts/june_hash.py` refuse without both, and CI checks that the gates log only grows (J1, owner decision on minor 2)
- `job_a` reads Spark only through wrappers that refuse with fixed text and no cause, and its sample's SQL takes only complaint IDs (J5, serious 3)
- the robot's check reads tar and zip archives and reports any other download as unread, searches `runs/get` too, gets no `all-apis` token, and gives a verdict that fails on any leak, any unread place, a control that shows no leak in each kind of place judged, or a query history that is not refused (J5, J13, serious 1 and 2, minor 1)
- the failcheck's short row holds the marker at the start of each free-text field, its control differs from the quiet run by the flags only, and its first task returns its code hash for the gate's record (J5, minor 4, nit 8)
- `voc june-check` checks the frozen sample's rows against their hashes and counts sampled narratives with a carriage return, unpacks inside the June data folder, fails with a non-zero exit on any mismatch, and prints the gate's record only on a pass from unchanged frozen files (J1, J8, minors 3 and 6, nit 1)
- Job A sends no failure email (J8, owner decision on minor 5)

Written on 6 November 2026, in the third fix round of #94, from the review of its second fix round and the owner's decisions:

- the robot's verdict passes only when both dbt runs' dbt files show they reached the failing model. A reply with HTTP 200 that is not JSON is unread. Only HTTP 400, 401 or 403, or a token narrowed to `jobs`, is a refusal of `all-apis`. The marker in any other task fails, a task listed twice stops the check, the control must show the marker in its output, and an encrypted zip is unread (J5, J13, serious 1, minors 1 and 2, nits 4 to 6)
- the robot's check calls every place and never prints the query history's message (J5, minor 7)
- the gates log has a Result column. A later fail closes a gate and a later pass opens it again, only results strictly before the row count, a row with a bad result or an impossible date is refused, and CI refuses a new real row whose passes are not on `main` already (J1, minors 3 and 8, nit 7)
- the hash script has no way round the gates, prints the two hashes when both are open, and compares the frozen files with git by content, as `voc june-check` does before its gate record, which also needs the top of a checkout (J1, minors 4 and 5, nit 9)
- Job A's refusals, Spark's and unpack's, carry no earlier exception at all (J5, minor 6)
- no text still says the gates come before the upload, the steps run `voc june-check` with the lock file kept, and the owner's steps make the sample before it (J8, minor 10, nits 1 and 8)

Written on 6 November 2026, from the minors of the last review of #94, fixed with no further review round:

- `voc june-check` records a fail too, and both gates print their time in UTC. The robot's check prints its time and the code hash even when it stops early (J1, minors 2 and 3)
- the robot's run file rule needs a folder boundary (J13, nit 1)
- a frozen file rewritten with other line endings, or hidden from git's status, counts as changed, and a file with a space in its name does not (J1, minors 4 and 5)
- a run log row with an impossible date is refused (J1, minor 6)
- the hash script prints the two hashes on a real git checkout with both gates open, and refuses once a frozen file is added (J1, minor 7)
- `unpack`'s refusal keeps no exception even when the CSV cannot be removed (J5, nit 6)
- the steps give every rule of the verdict and the dates in UTC, and the spec says how the dry run gets its hashes (J1, J8, minors 1 and 8, nit 3)

## The approval workflow ([spec 004](../specs/004-june-test-and-baselines/spec.md), pull request 8, J10, J16)

Written on 6 November 2026, with fakes for Databricks, GitHub and the receiver.

- the workflow has one required string input and names its run by it, two jobs in their environments on `main` only, read-only permissions per job, one run at a time, every action pinned by its commit SHA with no kept credential, inputs and secrets reaching commands through `env:` only, and its logic in frozen `src/` (J10, J16 item 3)
- a run ID that is not a whole number from 1 to 2^63 - 1, written in decimal, is refused (J16)
- Job A's run is refused unless it is this run of Job A, finished successfully with the spike's two success fields, never repaired, with exactly its three tasks by key, all succeeded. It must be the newest in a list that is newest first, and Job A must have no active run (J16 item 5)
- the exit value is read whole, untruncated, with exactly the contract's keys and types, and must match the run log's last row and its pin (J16 items 4 and 5)
- the figures job refuses a run name that is not the exact name, and prints only the run, its row, its start and the figures, in the log and the step summary (J16 items 3 and 5)
- the run job starts Job B with the contract's body, follows it to its end or reports `UNKNOWN`, reads Job B's exit value with exactly its keys, and posts the signed result message with the contract's bytes. A re-run never starts Job B, and a refusal before the start posts `NOT_STARTED` (J16 items 6 to 9)
- both jobs ask Databricks for the `jobs` scope only, and refuse a host that is not a bare name (J10, J13)
- no field the jobs do not read reaches their output, and other errors print their type only (J5)
- the jobs' IDs come from `config/june_cloud.toml`, refused while it is missing or holds a value that is not a whole number above zero (J16 item 10)

Written on 6 November 2026, in the fix round of #95, from its review and the owner's decisions:

- the robot's token is renewed before it expires and after a 401, and the follow outlasts failed looks and ends at 340 minutes of time with `UNKNOWN` (J10, serious 1, minor 3)
- Job A's run is read with `include_history` (J16 item 5, serious 2)
- Databricks' end states map onto the receiver's six, Databricks' own text is never printed, an exit value the receiver would refuse is sent as null, the message is tried again on a server error, anything but 202 fails the job, and the message passes the receiver's own code (J16 item 9, serious 3, minor 4)
- a lost or odd reply to run-now posts `UNKNOWN`, any failure before it posts `NOT_STARTED`, a setting that cannot be read included, and no request follows a redirect (J16, minors 1, 2 and 5)
- the real target and pin code refuse a real row without its gates and a synthetic row until pull request 9, and the run job and the termination message pass J5's hostile-text test (J5, J16, minors 6 and 7)
- a Job B run with no task list still posts, an exit value that is not JSON is refused, either attempt source alone stops a re-run and posts `NOT_STARTED`, and a cancelled run prints no traceback (J5, J16, nits 2 to 5)

Written on 7 November 2026, from the second review of #95, fixed with no further review round:

- `http.client`'s own errors are no answer, in the request, the follow and the post, and a failed post names the first error too (J16, minors 1 and 2)
- a cancel after the start posts `UNKNOWN` once with no wait, and before it `NOT_STARTED` (J16, minor 3)
- the follow's limit counts from the job's start and leaves 30 minutes for the end (J10, minor 4)
- a short token is renewed at half its life, and a 403 renews it once (J13, nit 1)
- the opener's only redirect handler refuses, a redirect comes back as its status, the post is tried again after a 429 or no answer, and `main`'s refusal of the run job holds no field it does not read (J5, J13, nits 6 and 7)
- the synthetic case of the real target test is refused by the run log's rule, as it says now (minor 6)

## The dry-run Job B ([spec 004](../specs/004-june-test-and-baselines/spec.md), pull request 6a, J11, J16), `tests/test_job_b.py`

Written on 8 November 2026, with fakes for the Jobs API, GitHub and the volume (owner decisions of 6 and 8 November):

- Job B is one task, one run at a time, on `main`, with no trigger, exactly run-now's two job parameters, and its own run ID filled by Databricks. Its file, its notebook and its logic are frozen with the code (J1, J11, J16 item 6)
- its three parameters are read exactly, each a whole number in range (J16 item 1)
- it takes only a synthetic first row and `SYN-` IDs, waits for pull request 9a for its list and mock answers, and never makes the API backend or reads a key (J11)
- it refuses its own run unless it is a running run of Job B with exactly the two run IDs and a known commit (J11)
- it reads the GitHub run and its approvals with no token and no redirect, tries 3 times after no answer, 403, 429 or a server error, and refuses each broken field, a missing owner approval of `june-run` and any rejection of it (J11, J16 item 7)
- it checks Job A's run again: its job, its success, no repair, the newest run, no active run, and the exit value against the row and the pin (J16 item 5)
- it refuses rows that are not exactly the listed sample with their content hashes, and figures other than the approved ones (J11)
- it marks the GitHub run and the Job A run for its row as used, only after every check, looks for both first, and never overwrites, so a used one or one made in between is refused (J11, J16 item 7)
- its exit value has the contract's keys as compact sorted JSON and passes the workflow's and the receiver's checks. A finished run's results folder holds only the dry run's note, and a stopped run names no folder and gives its reason (J16 item 8)
- it prints nothing, its refusals hold no row text and no earlier exception, a failure of the Jobs API or the volume is refused with its type only, and the notebook names no secret (J5)

Written on 8 November 2026, in the fix round of #98, from its review and the owner's decisions. What two lines above describe changed: the list now comes as its bytes, and the exit values pass the receiver's own check too.

- the dry run's list is read from its bytes, which must hash to the run log row's list hash, and its IDs and hashes are checked before any SQL runs (J11, minors 1 and 2)
- every marker comes after every outside call, and no refusal writes a file (J11, minor 3)
- the exit values pass the receiver's own check, any kind of not-found error means a marker is missing, and a job parameter with no name is refused (J11, J16 item 8, minors 4 and 5, nit 6)
- the contract defines `labelled`, the job file names no `run_as`, frozen paths match whole, and each re-check of Job A is refused for its own reason (J1, J11, J16, nits 7, 9, 10 and 11)

Written on 8 November 2026, from the fix-round review of #98, fixed with no further review round:

- the GitHub, list-hash and list-shape refusals write no file, a list with only its header or with an ID twice is refused, a June table row that is not synthetic is refused, and the rows check keeps its own check of the list (J11, minor 1, nits 2 and 3)
- `labelled` counts every complaint with a decision, the ones not run for the budget included (J16 item 8, nit 6)

## The dry run's setup ([spec 004](../specs/004-june-test-and-baselines/spec.md), pull request 9a, J1, J8, J11, J16), `tests/test_dry_run.py`

Written on 8 November 2026, on synthetic data only (owner decisions of 6 and 8 November). Two earlier tests went in its green commit, since these replace them: Job A's pin waiting for pull request 9, and Job B's list and answers waiting for 9a.

- the round's CSV has the CFPB header, `SYN-` IDs only, the pinned counts, Products from the label list, dbt's date and flag forms, one marker, one line break inside a narrative and one empty narrative (J8)
- its pin names `syn_` files apart from the June pin, and its zip is stored with fixed fields, so it is the same bytes on every platform and the pin's (J8)
- the script makes every committed file byte for byte, and `unpack` takes the zip against its pin (J8)
- the dry run's list is the CSV's narrative rows with their content hashes, bound to its manifest and never the June list (J1)
- Job A takes a synthetic row naming the dry run's list, with its pin, reads that list with `SYN-` IDs only, the notebook passes the target to both list reads, and its exit value on the dry run's rows passes the workflow's checks (J8, J16)
- Job B reads the committed list bound to the row and the mock answers, seven accepted and one quarantined, refuses both for a real row, and runs end to end on fakes with no marker in any file and nothing printed (J5, J11)
- the dry run's hash path refuses until the jobs' IDs are committed, then prints its list hash and the code hash with no gate and never the June list's hash, and the script still has no synthetic flag (J1)
- the script prints names, sizes and hashes only, and writes the zip only outside the repo (J5)

Written on 8 November 2026, in the fix round of #99, from its review and the owner's decisions. The tests above now read the round from the pin, and the June list check reads every ID.

- the pin's round must match the list's, and a synthetic row naming another round's list is refused (J8, J16, minors 4 and 5)
- `unpack` refuses a dry run CSV with an ID that is not synthetic, and removes the CSV (J8, minor 6)
- the dry run's note ends with the labelled, accepted and quarantined counts, with no ID and no text (J11, minor 1)
- Job B runs on a checkout with its real run log row, the jobs' IDs and its code hash, with nothing patched (J11, nit 11)
- the steps keep `main` still from the upload, ask for a fresh upload on a re-run once Job B marked its run used, use the repo's Python, and drop every table and view (J1, minors 2, 3 and 7, nit 10)

Written on 8 November 2026, from the fix-round review of #99, fixed with no further review round. The stale list test above is renamed for what it checks, a list hash other than the checkout's.

- an unreadable dry run list is refused as unreadable, the re-run steps say how to start a fresh workflow run by hand, and the kept note holds counts (J1, J16, minors 1 and 2, nit 3)
- the note ends with its counts, and the mock answers test uses the function Job B's run uses (J11, nits 4 and 6)

## The jobs' IDs and the Databricks steps ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J16 item 10), `tests/test_dry_run.py`

Written on 9 November 2026, after the owner made Job A and Job B in the workspace:

- `config/june_cloud.toml` holds Job A's and Job B's IDs, and a checkout without it is made by removing the copy (J16 item 10)
- `docs/DATABRICKS_STEPS.md` gives steps 1.1 to 1.8 click by click, with placeholders only and no real address or ID (J1, owner decision of 9 November)

Written on 9 November 2026, in the fix round of #100, from its review and the owner's decisions:

- Job B writes its results in a schema of its own, `workspace.voc_results`, never in `default` (J13, serious 1)
- the steps make that schema and say what a schema is, check each job's Run as and the live job against its file, give the robot's rights in full, copy secrets without showing them and clear the clipboard either way, and hold no workspace host, vault address or warehouse ID (J1, J13, minors 2, 3, 5 to 7, nits 9 and 10)
- the spec and the dry run's steps name the dry run as the webhook's test, and link the steps page (J8, minor 4, nit 11)

Written on 9 November 2026, from the fix-round review of #100, fixed with no further review round. The steps test above is renamed for what it checks.

- the dry run's steps say what to do if no approval run appears, and the spec names no destination test (J8, minor 1)
- the steps record the owner's check of the live Job A and the removal of the Secrets Officer role, name every secret the workflow and the receiver read, count six green ticks, and warn about the two boxes that show a new secret once (J1, J10, J13, minors 2 to 6)

## The dry run's row ([spec 004](../specs/004-june-test-and-baselines/spec.md), plan item 9, J1), `tests/test_dry_run.py`

Written on 9 November 2026, after the jobs' IDs (owner decision of 8 November: the row comes last). The test that expected an empty run log now checks its header only.

- the run log's one row is the dry run's, synthetic, round 1, naming the dry run's list and the checkout's frozen code, and Job A takes it with the dry run's pin (J1, J16). Retired in round 2's pull request, below.

## The dry run's round 2 ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J8, J13, J16 item 5), `tests/test_approval.py`, `tests/test_dry_run.py`

Written on 9 November 2026, after round 1 stopped at the approval workflow's check of Job A's run. In the green commit, round 1's row test above now checks that row as a record, and Job B's re-check case for a repaired run uses an `ORIGINAL` and a `REPAIR` item.

- a never-repaired run's one `ORIGINAL` repair history item is taken, and any other history is refused, an empty or missing one included (J16 item 5)
- round 1's row stays in the run log as a record, with its list and code no longer the checkout's (J1)
- round 2 has its own `SYN-` IDs, apart from round 1's (J8)
- the steps give the robot's secret the `jobs` scope with **Read + Write**, never **Read** alone (J13)
- the dry run's steps make round 2's zip, after round 1's clean-up (J1)

Written on 9 November 2026, in the fix round of #102, from its review and the owner's decisions. The two round 2 tests above are renamed and read the round from the pin.

- each round has its own `SYN-` IDs, apart from the round before's, and the steps make this round's zip after the round before's clean-up (J1, J8, minor 6)
- the steps put the round's row first, keep Job A's trigger paused, and remove Application Insights after the round (J1, minor 4)
- Job A refuses the checkout until its last row is this round's (J1, nit 7)

Written on 9 November 2026, for round 2's row (owner decision of 8 November: the row comes last).

- the run log's last row is this round's, synthetic, naming the dry run's list and the checkout's frozen code, and Job A takes it with the dry run's pin (J1, J16)
- in the fix round of #103: Job B takes it too, the round is matched as a whole word, and the row is dated after the one before it (J1, minor 1, nit 4)

## The dry run's round 3 ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J11), `tests/test_job_b.py`, `tests/test_dry_run.py`

Written on 10 November 2026, after round 2 stopped at Job B's check of its own run. In the green commit, Job B's own-run helper, its commit cases and the dry run's fake own run hold the commit on the task, as round 2 saw it.

- Job B takes its commit from its task's `git_source.git_snapshot.used_commit`, one attempt or two (J11)
- Job B refuses its own run with no task, another task, a commit that is not 40 hex characters, attempts that name different commits, a task with no snapshot, or the commit on the run only (J11)
- between a round's code pull request and its row pull request, Job A refuses the checkout (J1)
- in the fix round of #105: after a retry, the approval workflow reads Job B's exit value from its latest attempt, in either order, and sends none when the attempts cannot be ordered (J16, serious 1)
- in round 3's row pull request: the run log holds one row for round 3, synthetic, naming the list and code hashes printed on `main` after #105 merged (J1)

## Pull request 6b, part 1: Job B's packages and time limit ([spec 004](../specs/004-june-test-and-baselines/spec.md), J11), `tests/test_job_b.py`, `tests/test_dry_run.py`

Written on 10 November 2026, after the probes in the workspace.

- Job B stops after three hours (J11)
- Job B's requirements pin every package at uv.lock's version, with hashes, compiled for Python 3.12 on ARM (J11)
- the `cloud` group pins what the project pins (J11)
- the notebook installs the locked packages with `--require-hashes` and restarts Python before it imports the repo's code (J11)
- Job B refuses packages other than the locked ones, naming each, before any other check (J11)
- in the green commit: between a change to the frozen code and its round's row, Job A refuses the checkout, and the dry run's checkout copies the requirements file (J1)

## Pull request 6b, part 2: Job B's refit of TF-IDF + LR ([spec 004](../specs/004-june-test-and-baselines/spec.md), J7, J11), `tests/test_june_refit.py`, `tests/test_job_b.py`

Written on 10 November 2026.

- the refit reproduces the committed development labels, and refuses with the count when one differs (J7)
- committed labels that are not the development list's are refused (J7)
- an export that is not the pinned one is refused, and a training row whose text is not its list's is refused (J11)
- the refit reads only training and development rows, never a test row (J2, J11)
- a loader failure is refused with its type only (J5)
- the refit uses the frozen settings and the committed development labels, the July pin's file in the raw volume, and the laptop's duckdb (J7, J11)
- Job B refits before it marks anything, and a refused refit stops it before any marker (J11)
- from the second review of #108: a requirements file that is not UTF-8, or text after a pin that is not a marker or a continuation, is refused, and a pin with a marker or a continuation is taken (J11)

## Pull request 6b, part 3a: Job B's ledger and recordings in the volume ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J11, J12), `tests/test_june_ledger.py`, `tests/test_job_b.py`

Written on 10 November 2026.

- the June ledger is made with the frozen June cap and no git, and a later run reuses it and keeps what was used (J1, J12)
- a June ledger with another cap, or made for another project, is refused, and so is a config with no whole June cap (J12)
- the ledger and recordings live in the raw volume (J11)
- a live call is recorded in the volume and charged to the June ledger, and a resumed run replays it and pays nothing (J1)
- a call past the June cap is refused before anything is sent (J12)
- the laptop's caller still checks the committed config, and the June caller never uses the home folder (J11)
- from the second review of #109: a marker holding a token that starts with "-" is refused (J11)

## Pull request 6b, part 3b: Job B's real labelling through the API ([spec 004](../specs/004-june-test-and-baselines/spec.md), J11, J12, J16), `tests/test_june_api.py`, `tests/test_job_b.py`, `tests/test_june_ledger.py`

Written on 10 November 2026.

- an answer from the cloud workspace is taken, and one for another workspace, or with no workspace header, stops the run (J11)
- a 400 usage limits answer stops the run with no retry, the reason `spend_limit` and none of the API's text, and another 400 is refused without counting as the spend limit (J12)
- the caller passes a stop up at once and records nothing, and the labeller stops the whole run on the first stop (J12)
- without a workspace, the laptop's backend is unchanged (J11)
- with a backend from the notebook, Job B labels the synthetic sample through the June caller, its recordings apart from June's, and the note says so (J11, owner decision of 10 November)
- a spend limit stop and a June ledger cap stop give the contract's reasons and write no note (J12, J16)
- the notebook reads the key and the workspace ID from the secret scope `voc-june`, and prints nothing (J11)
- from the review of #110: Job B refuses a run whose worst case passes what is left under the June cap, counting what is reserved, a reused ledger with other trial settings is refused, and a June ledger refusal is a budget refusal (J12)

## Pull request 6b, part 4: Job B's results files ([spec 004](../specs/004-june-test-and-baselines/spec.md), J11, B19), `tests/test_june_results.py`, `tests/test_job_b.py`, `tests/test_june_api.py`

Written on 10 November 2026.

- the CSV's columns are the development results' columns, and the reasons are the fixed list (B19)
- a valid pair of files passes, and a file is refused for other columns, a label or reason outside the lists, a complaint outside the June list or given twice, another split, the CFPB header row or the size limit, with no value from the file in the refusal (J5, J11)
- `build` writes June rows in complaint ID order with the refit's labels and exact confidences, and the summary with the run's settings, tokens and the figures, and no text (J11)
- from the review of #111: an overrun is refused before any marker, a stop after some calls leaves no open reservation and keeps the earlier answers recorded, and an empty workspace ID is refused (J11, J12)

## Pull request 6b, part 5: a real first row ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J11), `tests/test_job_b.py`, `tests/test_june_results.py`

Written on 10 November 2026.

- a real first row is labelled through the API, scored and its two files written, with its recordings in June's folder (J11)
- a real run writes its start marker before its first model call, a row already started is refused before anything is written, and a synthetic run writes none (J1)
- a real row is never labelled with the mock answers, and a later row is refused in this build (J11)
- a real list or sample holding a synthetic ID is refused (J11)
- results that fail their check stop the run with no results file (J1, J11)
- from the second review of #112: `build` needs the June ledger's charge, the summary holds only its keys and short texts in values and keys, rows given in any order are sorted by ID number then ID and scored with their recorded Products, and number columns take plain numbers only (J3, J11)

## Pull request 6b, part 6: the copy of the results and the reader check ([spec 004](../specs/004-june-test-and-baselines/spec.md), J11, J13), `tests/test_june_copy.py`, `tests/test_job_b.py`, `tests/test_june_results.py`

Written on 10 November 2026.

- the reader signs in with its own client and basic auth, and comes from its own variables, never a default token (J13)
- the copy brings exactly the two files, checks them and writes them, refuses a folder holding anything else, never writes files that fail their check, and never overwrites results already in the repo (J11)
- an HTTP refusal gives its status only and never the secret (J5)
- the reader check passes when the results are readable and the raw data is not, and fails otherwise (J13)
- the script takes one run ID or `--check-reader` and names no default token or SDK (J11, J14)
- from the review of #113: a real `build` passes the real `check`, `build` refuses a ledger charge that is not a whole number, any failure after labelling stops the run with `error`, a failed second upload leaves no results file, and a real sample row with a synthetic ID is refused (J1, J3, J11)

## Pull request 6b, part 7: the dry run's clean-up ([spec 004](../specs/004-june-test-and-baselines/spec.md), J11), `tests/test_job_b.py`

Written on 11 November 2026.

- a finished synthetic run deletes its two files and nothing else, drops exactly the four June objects, and says so in its note (J11)
- a clean-up failure never fails the run, and the note says what is left, with no text from the error (J5, J11)
- a stopped synthetic run and a real run clean up nothing (J11)
- names that are not a dry run round's are never deleted, and the names come from the dry run's pin (J11)

## The dry run's round 4 ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J8), `tests/test_dry_run.py`

Written on 11 November 2026, after the pull requests of 6b changed the frozen code. The other dry run tests read the round from the pin, so they cover round 4's CSV, list, pin and steps with no change.

- round 3's row names the frozen code before the pull requests of 6b, so the pin names round 4 or a later round, with new IDs (J1, J8). Changed in the review of #119: the first version asked for the next round after any frozen change, against 6b's one shared round
- in round 4's row pull request: the run log holds one row for round 4, synthetic, naming the list and code hashes printed on `main` after #119 merged (J1)

## The refit's strict stopping point ([spec 004](../specs/004-june-test-and-baselines/spec.md), J7, B11), `tests/test_june_refit.py`

Written on 12 November 2026, after round 4 of the dry run.

- June's refit runs the solver to a `tol` of 1e-8, not scikit-learn's default (J7)
- a refit that has not settled within its `max_iter` solver steps is refused (J7)
- from the review of #121: a refit whose solver warned that it stopped early, in fewer steps, is refused too (J7)
- the July evaluation's fit keeps scikit-learn's default stopping point, 1e-4 (B11)

## The dry run's round 5 ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J8), `tests/test_dry_run.py`

Written on 12 November 2026, after #121 made June's refit run to a strict stopping point. The other dry run tests read the round from the pin, so they cover round 5's CSV, list, pin and steps with no change.

- round 4's row names the frozen code before #121, so the pin names round 5 or a later round, with new IDs (J1, J8)
- the run's steps wait for the trigger's fresh look, with 0 files in total, before the upload, since round 4's zip went up before it and started no run (J8)
- in round 5's row pull request: the run log holds one row for round 5, synthetic, naming the list and code hashes printed on `main` after #122 merged (J1)

## The refit's pinned vocabulary ([spec 004](../specs/004-june-test-and-baselines/spec.md), J5, J7), `tests/test_june_refit.py`

Written on 12 November 2026, after rounds 4 and 5 of the dry run. The fixture works out its own vocabulary pin, so the tests do not check the code against itself.

- the refit takes the pinned vocabulary, not the sort's pick of tied terms (J7)
- a vocabulary whose hash is not the pin's, term counts that are not the pin's, and a pin for other settings are refused (J7)
- the pin names the tied terms scikit-learn keeps on the machine that writes it, and the laptop's writer writes it from the July training rows (J7)
- the committed pin holds counts, positions and a hash only, never a term (J7, B19)
- an unreadable pin is refused with its type only (J5)
- from the review of #124: a pin that is not well formed is refused with its own message, for its positions, keys, month, hash or counts, and the laptop's writer puts the old pin back, or removes a new one, when the refit check with the new pin fails (J7)
- from the second review of #124: each rule on the pin's positions is checked on its own, on a fixture whose tie is cut (J7)

## The approval workflow fails when Job B did not finish ([spec 004](../specs/004-june-test-and-baselines/spec.md), J10), `tests/test_approval.py`

Written on 13 November 2026, after the dry run's rounds 4 and 5, where the `run` job ended green after a failed Job B.

- the run job passes, with `Job B finished` as its last line, when Job B ended in `SUCCESS` and its exit value, read and checked, says it did not stop (J10)
- from the review of #125: a passing `figures` job still exits 0 through `main`, and a follow that stops with `UNKNOWN` fails the run job through `main` (J10)
- it fails after the result is posted, with its own last line, when Job B ended in `FAILED`, `TIMEDOUT`, `CANCELED` or another end, when Job B stopped, when its exit value cannot be read, and when the follow stops with `UNKNOWN` (J10)

## The dry run's round 6 ([spec 004](../specs/004-june-test-and-baselines/spec.md), J1, J8, J10), `tests/test_dry_run.py`

Written on 13 November 2026, after #124 pinned the refit's vocabulary and #125 made the run job fail when Job B did not finish. The other dry run tests read the round from the pin, so they cover round 6's CSV, list, pin and steps with no change.

- round 5's row names the frozen code before #124 and #125, so the pin names round 6 or a later round, with new IDs (J1, J8)
- the steps say the run job shows a red cross when Job B did not finish, and that the workflow refuses a re-run's second attempt before it starts Job B (J10)
- in round 6's row pull request: the run log holds one row for round 6, synthetic, naming the list and code hashes printed on `main` after #126 merged (J1)

## The failcheck reads every attempt ([spec 004](../specs/004-june-test-and-baselines/spec.md), J5, J13), `tests/test_job_a.py`

Written on 13 November 2026, after gate 2's first run failed because serverless auto-optimization retried both dbt tasks.

- the robot check reads every attempt of a retried task, by its attempt number, and passes when every rule holds (J13)
- a leak in any attempt of the quiet run fails it, and every quiet attempt must reach the failing model (J5, J13)
- the control's latest attempt is the one that must show the marker (J13)
- two items of a task with the same attempt number are still refused (J13)

## June test in the cloud ([spec 004](../specs/004-june-test-and-baselines/spec.md)), planned

Added on 4 November 2026, revised twice the same day. Each piece adds its tests in its own pull request, failing first.

- the June sample is drawn from June only, drops copies within June and copies of July's training and development sets, refuses a Product not in `config/labels.toml`, follows Cochran's formula at e = 2 points on June's pool, and is frozen with its hashes (J6): written in pull request 3, listed above
- the laptop refuses to score June (written in pull request 3, listed above), Job B refuses unless `runs/JUNE_RUNS.md` names the June list's hash and the frozen code's hash, and that file only grows (J1)
- no June step reads a July test row (J2): the June sample's part written in pull request 3
- the refit TF-IDF + LR reproduces the committed July development labels before it labels June (J7)
- the primary claim is the hybrid against the LLM alone at full coverage, with the verdict words fixed, and the secondary comparison carries no verdict (J7): written in pull request 4, listed above
- every job and workflow entry point, on hostile synthetic text, prints only IDs, labels, reasons, positions, decisions and counts, with no traceback (J5)
- Job A checks the pin and the sample's hashes, computes the approval figures and makes no model call (J8)
- the receiver refuses a bad sign-in or signature and an old or future timestamp with 401, replies 202 before the work, drops a duplicate, confirms a Databricks run by asking Databricks, skips a dispatch already made, and moves a message to the failure queue after 5 tries (J9): written in pull request 7, listed above
- the receiver's settings: maximum instance count 1 for each function, 4 HTTP calls at once per instance (added on 7 November), and only Key Vault references in its app settings (J9)
- written in pull request 8, listed above: the approval workflow's YAML: started only by `workflow_dispatch` on `main`, its run ID input checked and passed through `env:`, permissions per job, the Databricks credential in both jobs and the HMAC secret only in the `june-run` job, one run at a time, actions pinned by SHA. A test can check only the YAML (J10)
- Job B checks the run entry's hashes and the June and July hashes, refuses unless the workspace header names the cloud workspace and the cap covers the whole worst case, stops on a 400 "usage limits" answer with no retry, is one task that refuses an approval for another Job A run or one already used, and writes only the two results files to the results volume (J11, J12)
- The copy script reads only the two results file names, refuses any other file, and checks the columns, the label and reason lists, the IDs, the size limit and the CFPB header (J11)
- The copy script signs in only with the reader's credential, named in its call, and never with a default profile or the environment's `DATABRICKS_TOKEN` (J13, review of #87)
- recordings, the ledger and the fitted model never leave the volume, and complaint text never reaches GitHub (J4)
- the read guard protects `VOC_JUNE_DATA_DIR`, the raw volume, all Actions run logs, and the approval workflow's start (J6, J14): written in pull request 2, listed under Hooks. The June tables are named in pull request 5, and Claude never runs the Databricks CLI at all
- the laptop path and the cloud path give the same July results on mock or replay (J8)
- the contract (J16): each side reads and writes exactly the fields of its fixed sample messages in `tests/fixtures/june_contract/`, refuses another `contract` value, a missing field or a field of the wrong type, and checks IDs against `^[1-9][0-9]{0,18}$`. The workflow's `display_title` is compared whole, never in part. Before the approval, on every path, the workflow refuses a Job A run of another job, one that did not succeed, one that is not Job A's latest, and one whose exit value does not name the pin and list of its kind, and it prints the run's ID, kind, start time and figures in the step summary. It also refuses a repaired run and one that does not match the target row, the last row of `runs/JUNE_RUNS.md`. Job B makes the same checks, refuses a run attempt other than 1, a used GitHub run and a used Job A run for its row. The result message's bytes and signature follow J16's exact rules. The result message's signature is built over the timestamp, a dot and the raw body. Each test is written in the pull request of its side (5 to 8)
- a Databricks Git folder or a job's Git source gives the same bytes for every frozen file, `.py` files it may treat as notebooks included, so Job B's code hash matches the laptop's (J1, pull request 6, review of #89)
- a stopped run writes no per-complaint file and no figure, and a resumed run calls the model only for complaints with no recorded answer (J1, pull request 6, owner decision of 5 November)

## Later features (listed now, specified later)

- API: typed schemas, input checks, paging, error messages, request logging
- API: test servers run with `loop="asyncio"`, because uvloop would bypass the Python socket block (review of #3)
- Browser: one end-to-end test per analyst task in `docs/USER.md`
