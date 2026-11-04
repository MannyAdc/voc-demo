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
- read guard: a command that runs the Databricks CLI, in any part of a line or by its full path, or names the volume `voc_raw`, is denied (spec 004, J14)
- read guard: reading an Actions run log, starting, re-running or cancelling a workflow, approving a deployment, the environments and secrets APIs, and merging a pull request are denied, by `gh`, `gh.exe` by its full path, the REST API or GraphQL. Checking, viewing and commenting on a pull request, viewing a run without its log, and running the merge verdict stay allowed (spec 004, J14)

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

## June test in the cloud ([spec 004](../specs/004-june-test-and-baselines/spec.md)), planned

Added on 4 November 2026, revised twice the same day. Each piece adds its tests in its own pull request, failing first.

- the June sample is drawn from June only, drops copies within June and copies of July's training and development sets, refuses a Product not in `config/labels.toml`, follows Cochran's formula at e = 2 points on June's pool, and is frozen with its hashes (J6)
- the laptop refuses to score June, Job B refuses unless `runs/JUNE_RUNS.md` names the June list's hash and the frozen code's hash, and that file only grows (J1)
- no June step reads a July test row (J2)
- the refit TF-IDF + LR reproduces the committed July development labels before it labels June (J7)
- the primary claim is the hybrid against the LLM alone at full coverage, with the verdict words fixed, and the secondary comparison carries no verdict (J7)
- every job and workflow entry point, on hostile synthetic text, prints only IDs, labels, reasons, positions, decisions and counts, with no traceback (J5)
- Job A checks the pin and the sample's hashes, computes the approval figures and makes no model call (J8)
- the receiver refuses a bad sign-in or signature and an old or future timestamp with 401, replies 202 before the work, drops a duplicate, confirms a Databricks run by asking Databricks, skips a dispatch already made, and moves a message to the failure queue after 5 tries (J9)
- the receiver's settings: maximum instance count 1 for each function, and only Key Vault references in its app settings (J9)
- the approval workflow's YAML: started only by `workflow_dispatch` on `main`, its run ID input checked and passed through `env:`, permissions per job, the secrets only in the `june-run` job, one run at a time, actions pinned by SHA. A test can check only the YAML (J10)
- Job B checks the run entry's hashes and the June and July hashes, refuses unless the workspace header names the cloud workspace and the cap covers the whole worst case, stops on a 400 "usage limits" answer with no retry, is one task that refuses an approval for another Job A run or one already used, and writes only the two results files to the results volume (J11, J12)
- The copy script reads only the two results file names, refuses any other file, and checks the columns, the label and reason lists, the IDs, the size limit and the CFPB header (J11)
- recordings, the ledger and the fitted model never leave the volume, and complaint text never reaches GitHub (J4)
- the read guard protects `VOC_JUNE_DATA_DIR`, the raw volume, all Actions run logs, and the approval workflow's start (J6, J14): written in pull request 2, listed under Hooks. The June tables are named in pull request 5, and Claude never runs the Databricks CLI at all
- the laptop path and the cloud path give the same July results on mock or replay (J8)

## Later features (listed now, specified later)

- API: typed schemas, input checks, paging, error messages, request logging
- API: test servers run with `loop="asyncio"`, because uvloop would bypass the Python socket block (review of #3)
- Browser: one end-to-end test per analyst task in `docs/USER.md`
