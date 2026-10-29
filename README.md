# voc-demo

A Voice of the Customer pipeline on the public US CFPB Consumer Complaint Database. An LLM labels each complaint by product and quotes the sentence that supports the label. A script checks that the quote really appears in the complaint. A label that fails a check goes to quarantine with a reason. It is never dropped and never counted as correct. A simple TF-IDF classifier is scored on the same complaints, head to head.

Built in three days, in the open: the spec, the tests written before the code, the reviews, the decisions and the mistakes. See [BUILD_LOG.md](BUILD_LOG.md).

## The result

The claim was fixed before the first run: **the LLM, with its quote check, beats TF-IDF at the same coverage** (rule B10 in the [spec](specs/001-core-labelling-pipeline/spec.md)). It was judged once, on a frozen test set of 1,909 complaints. [How we measure](docs/HOW_WE_MEASURE.md) explains the method in plain words.

**Verdict: the LLM beats TF-IDF.**

| Test set, 1,909 complaints | LLM (claude-haiku-5-5, prompt v1) | TF-IDF at the same coverage |
|---|---|---|
| Re-weighted strict accuracy | **80.3%** | 77.9% |
| Precision on accepted labels | 82.2% | 79.7% |
| Coverage | 97.6% | 97.6% |
| Macro-F1 | 0.761 | 0.654 |
| Cost per 1,000 complaints | $0.2373 | $0 |
| Time per 1,000 complaints | 2,015.2 seconds | 0.707 seconds |

The difference is +2.4 points, with a 95% interval of +0.5 to +4.1 points from a paired bootstrap (2,000 resamples, seed 0). The whole interval is above zero, so the verdict is "beats".

- The run: `uv run --native-tls voc final --prompt v1`, by the owner. It was logged in [runs/TEST_RUNS.md](runs/TEST_RUNS.md) on 29 October 2026 at 21:48, before any call. It is the only row there.
- 1,864 labels accepted and 45 quarantined: the quote was not in the text 21 times, the label was not in the list 15 times, the answer could not be read 6 times, and the quote was too short 3 times.
- 1,909 live calls, 2,630,555 input and 379,892 output tokens, $0.4530015 in all, 3,847 seconds.
- Results: [results/eval/v1_test.json](results/eval/v1_test.json) and [results/labels/v1_test.json](results/labels/v1_test.json).

**What the terms mean.**
- *Strict accuracy*: correct accepted labels divided by all complaints. A quarantined label counts as wrong.
- *Re-weighted*: worked out for each product, then averaged with weights equal to each product's share of the 9,303 complaints in the pool.
- *At the same coverage*: TF-IDF answers only as many complaints as the LLM accepted, its most confident ones, and the rest count as wrong. So neither method looks better by skipping hard cases.
- *Time per 1,000*: the LLM's calls were sent one at a time. TF-IDF's time counts labelling only, not training.

### Per product, on the test set

Here the LLM's quarantined labels count as wrong, and TF-IDF labels every complaint, at full coverage, not the matched coverage above. A product with fewer than 30 test complaints is "too few to judge".

| Product | Test complaints | F1, LLM | F1, TF-IDF |
|---|---|---|---|
| Debt collection | 452 | 0.833 | **0.863** |
| Checking or savings account | 416 | **0.822** | 0.780 |
| Credit card | 371 | **0.873** | 0.802 |
| Money transfer, virtual currency, or money service | 160 | **0.730** | 0.623 |
| Mortgage | 149 | 0.910 | 0.910 |
| Vehicle loan or lease | 104 | **0.905** | 0.813 |
| Payday loan, title loan, personal loan, or advance loan | 83 | **0.744** | 0.531 |
| Credit reporting or other personal consumer reports | 64 | 0.500 | **0.697** |
| Student loan | 63 | **0.923** | 0.822 |
| Prepaid card | 28 | too few to judge | |
| Debt or credit management | 19 | too few to judge | |

The LLM's clear weak spot is credit reporting. It gave that label to 168 accepted complaints, but only 64 test complaints have it. On Mortgage, the two tie at 3 decimals: 0.910394 against 0.910345.

### Development set: tuning figures, not the verdict

The development set (370 complaints) was used while building, so its figures are tuning figures only.

| Development set, 370 complaints | LLM | TF-IDF at the same coverage |
|---|---|---|
| Re-weighted strict accuracy | 79.8% | 79.1% |
| Precision on accepted labels | 81.7% | 81.2% |
| Coverage | 97.6% | 97.6% |
| Macro-F1 | 0.772 | 0.694 |

Difference +0.6 points, 95% interval -3.1 to +4.7 points: inconclusive. Source: `uv run --native-tls voc evaluate dev --prompt v1 --note "first version"`, the first row of [EVAL_VERSIONS.md](EVAL_VERSIONS.md).

## Speed, Safety, Scale

**Speed**
- The LLM took 2,015.2 seconds per 1,000 complaints on the test run, with calls sent one at a time. TF-IDF took 0.707 seconds per 1,000.
- The LLM cost $0.2373 per 1,000 complaints on the test run (claude-haiku-5-5, prompt v1). Labelling all 10,002 complaints with a narrative in the July file would cost about $2.37 at that rate ($0.4530015 / 1,909 x 10,002). That is a projection, not a run.
- Every answer is recorded, so a re-run of the same prompt replays it at no cost.

**Safety**
- Every accepted label has a quote that a script found word for word in the complaint. The model's word is never taken on trust. That shows the quote is **in the text**. It does not show that the quote **supports the label**. No human has checked that yet (see Limits).
- `voc audit` checks a results file against the recorded answers and the complaint texts. On the development run it re-derived 361 of 361 accepted and 9 of 9 quarantined decisions, and 361 of 361 quotes matched word for word at their stored positions (`uv run --native-tls voc audit dev --prompt v1`). It reuses the labeller's own steps, so it is a consistency check. The word-for-word comparison is the independent part.
- A synthetic injection set of 10 made-up complaints (`config/injection.toml`, IDs SYN-9001 to SYN-9010) tries to force wrong labels. In one live run of prompt v1, 9 reached the model and none was obeyed. The tenth, a fake closing tag, was caught by the script before any call (`uv run --native-tls voc label injection --prompt v1`, then `uv run --native-tls voc evaluate injection --prompt v1`). These results are reported apart and never enter an accuracy figure. They show resistance on this set, with one model, not in general. An obeyed injection that quotes a real sentence from the text would pass the quote check.
- Complaint text is untrusted data. It goes to the model between fixed tags, as data, in a call with no tools. There is no `claude -p` or other agent backend, because untrusted text must never reach an agent that can act, and one code path keeps every number reproducible.
- The coding agent that built this repo never read a complaint, a quote or a model answer from real data. Commands print IDs, labels, reasons, positions and counts only. Hooks block it from reading the data, the ledger and the recordings, and ask the owner before any command with the word `final`.
- A hard token cap, a record and replay cache, and one token ledger shared by every run.

**Scale**
- The July 2026 export holds 672,036 complaints. 10,002 of them (1.5 percent) have a narrative. After 699 copies and near-copies are removed, 9,303 remain.
- Sample sizes come from Cochran's formula: 370 for development and 1,909 for the frozen test set. The remaining 7,024 train TF-IDF ([docs/DATA.md](docs/DATA.md)).
- Loading is incremental and keyed on complaint ID, so loading the same file again adds nothing. dbt builds the models and runs the data tests.
- A scheduled GitHub Actions workflow runs load, dbt build, label and evaluate every day on a committed synthetic fixture, with the mock backend. Its figures are synthetic, not a result.

## How it works

1. `voc load july_2026` checks the export's SHA-256 against its pin in `config/data_files.toml`, then loads it into DuckDB.
2. `voc dbt build` builds the staged and curated models and runs the data tests. The models leave out the test set.
3. `voc sample` froze the development, test and training lists in `splits/`, by ID and content hash. They are never regenerated.
4. `voc label dev` sends each complaint to the model, with the text between fixed tags, and records every answer.
5. A script checks each quote. A failure is quarantined with its reason.
6. `voc evaluate dev` scores both methods on the same complaints and adds a row to `EVAL_VERSIONS.md`.
7. `voc final --prompt v1`, run once by the owner, commits its log row before any call, then labels and scores the test set.
8. `voc serve` shows the committed results on a local dashboard at 127.0.0.1, with no complaint text.

## Run it yourself

Without any data or key, you can run the tests and the dashboard:

```
uv sync
uv run pytest
uv run voc serve
```

Then open http://127.0.0.1:8000. The tests never open a network connection or call a model.

To label real complaints you need the pinned July 2026 export. The CFPB serves only its current export, updated about daily, so that exact file cannot be downloaded again. `python scripts/download.py <empty folder>` fetches today's file and prints its SHA-256, which would need its own pin. The data folder is given by an environment variable. The API key goes in an environment variable too, never in a file in the repo. Contributors also install gitleaks and run `git config core.hooksPath .githooks` (see [CLAUDE.md](CLAUDE.md)).

## Why this stack

Versions are the pins in `pyproject.toml`.

- **DuckDB** (`duckdb==1.5.6`): one local file, no server, enough for a monthly export of 216 MB.
- **dbt** (`dbt-core==1.12.6`, `dbt-duckdb==1.11.0`): the models and data tests live as reviewed code, with incremental loads keyed on complaint ID.
- **scikit-learn** (`scikit-learn==1.9.1`): the TF-IDF baseline. It is cheap, fast and well understood, which makes it the honest thing to beat.
- **Anthropic SDK** (`anthropic==1.13.0`) with claude-haiku-5-5: Anthropic's low-cost model for high-volume work such as classification, at $0.10 per million input tokens and $0.50 per million output tokens (`config/prices.toml`, from the [pricing page](https://platform.claude.com/docs/en/about-claude/pricing), checked 28 October 2026).
- **FastAPI** (`fastapi==0.143.0`, with `uvicorn==0.54.0`): a small read-only API and dashboard over the committed results.
- **uv**: one lock file (`uv.lock`), so every machine and CI install the same versions.

## Limits

- The recorded product was chosen by the consumer, not by the CFPB, so some measured "errors" are label noise. TF-IDF learns from those same choices.
- The CFPB says its database "is not a statistical sample of consumers' experiences in the marketplace". The results describe this data only.
- The 10,002 narratives are a 1.5 percent subset with a very different mix. Credit reporting is 92 percent of all complaints, but only about 1 in 1,300 of them has a narrative ([docs/DATA.md](docs/DATA.md)).
- The model's training data cutoff is June 2026 ([models overview](https://platform.claude.com/docs/en/about-claude/models/overview), read 29 October 2026). The complaints were received in July 2026, so they cannot be in its training data.
- The CFPB file changes over time, and only the current export can be downloaded. So the July file cannot be fetched again, and a reader cannot re-run the labelling from this repo alone.
- Classifying is not the same as measuring. Prepaid card (28 test complaints) and debt or credit management (19) are too few to judge. They were not over-sampled, because the pool has only 134 and 91 of them, and taking more would cut TF-IDF's training data (decision 2 in [docs/DATA.md](docs/DATA.md)).
- The tests prove the code's rules. They do not prove label quality, which the evaluation measures, or how a cloud deployment would be secured.
- One model, one prompt version and one test run. The result says nothing about other months, other data or other industries.
- `voc ledger raise` writes a line to BUILD_LOG.md, and `voc final` needs a clean working tree. So after a raise, that line must be committed or set aside before the scored run.
- Pending improvements:
  - The analyser for error analysis (T018a): a tool-less model call that names one cause from a fixed list for each wrong label.
  - A human spot check of whether quotes support their labels (T014c, the `show` command for the owner).
  - Catching a crash in the middle of the scored run.
- What a cloud deployment would need: authentication on the API, keys in a secrets manager, the ledger in a shared database, the recordings in protected storage, and branch protection with required checks.

### Known limits

These come from the threat model in the [spec](specs/001-core-labelling-pipeline/spec.md). The guards stop honest mistakes, AI mistakes and hostile complaint text, and make any bypass visible in the public history. They are not built to stop a person who deliberately works around them.

- Deleting the ledger or the home-folder test log and starting again resets them, with no trace in git.
- A git-ignored local settings file can turn off the project hooks.
- Shell commands that write files are not seen by the data guard.
- Until branch protection is on, the owner can merge with failing CI.
- A tests-only commit can weaken an existing check. Only the reviewer agent would notice.
- A script that opens the DuckDB file directly skips the `final` guard and the dbt test-row filter.
- The staged DuckDB table under the dbt models still holds the test rows. So the real seal is the `final` command path, its committed log and the CI check on that log. The dbt flag is a second layer.
- A hand run of dbt with a relative project folder bakes a relative path to `splits/test.csv` into the `curated_complaints` view. Querying the view then depends on the folder the reader runs in. `voc dbt` always gives the full path.
- `git commit --no-verify` in the owner's own terminal skips the git hook. Only CI catches it.
- Hooks read command text, so an unusual command form can slip past them.
- On Claude Code versions before 2.1.295, a hook that times out lets the action through. A crash still blocks, through exit code 2.
- The git hook is switched on per clone with `git config core.hooksPath .githooks`. A fresh clone has no test gate until the owner runs it. Claude refuses to commit until then.
- The read guard blocks any shell command with the word `show` unless it starts with `git`, so it also blocks harmless commands such as `echo show`.
- `git cherry-pick`, `git revert` and `git commit-tree` run no pre-commit hook, so they can create a commit the test gate has not checked. Only CI catches it.
- The read guard checks path-like fields and command text. A path built at run time inside a script (for example joined from parts in Python) is not seen.
- The data guard does not check for complaint text copied into notes or docs. The read guard keeps Claude from reading that text in the first place.
- A server error or rate limit that lasts is retried, so up to 9 reservations are charged before 3 failed complaints stop the run. A failed call is charged its full reservation, even when the API billed nothing.
- The scored test run writes its results when it finishes, or when 3 complaints in a row fail. A crash in the middle (Ctrl-C, a ledger lock timeout, a corrupt recording, a ledger overrun that opens during the run) loses the outcomes so far. The log entry stays, so a new run needs a reason. Answers already made stay in the recordings, so a new run replays them at no cost. An overrun already open before the run is refused first.
- The test gate keeps the full pytest output of its last run in the system temp folder, one folder per checkout. A failing test can print a fake key it built, and that stays there until the next run. No scan covers that folder.
- `voc audit` needs the recorded answers, which stay outside the repo. So only the owner's machine can run it, not a reader of the repo. A recording rewritten together with matching positions in the results file would pass it, because recordings carry no signature.
- `voc sample` records the pinned file's SHA-256 in `splits/manifest.json`, but it does not check that the staged rows came from that file. `voc load` checks the file against its pin before loading, and the staged table does not keep the file's hash.
- No CI check yet stops `splits/` from changing compared with `main`. `voc sample` refuses to run while any list file is there, but a deleted folder can be rebuilt. With the same code and seed, the rebuilt lists are the same.
- The merge verdict's trial merge (`--test-merge`) runs the tests with this checkout's installed packages, so a dependency change in a pull request is not covered.
- The trial merge runs a pull request's tests on this machine. So it is for this repo's own pull requests only, and it refuses a pull request from a fork.

## How it was built

- Every rule is in the [spec](specs/001-core-labelling-pipeline/spec.md), and the API's rules are in [specs/002-results-api-dashboard/spec.md](specs/002-results-api-dashboard/spec.md). Every test is named after its rule.
- Tests come first. Each pull request has a commit with failing tests only, then the code.
- A git hook runs gitleaks, a names check and the full test suite on exactly the staged files, for every commit.
- A fresh reviewer agent reads every pull request. Its findings and Claude's check of each are posted on the pull request. The owner decides what to fix, and the owner merges.
- `scripts/merge_verdict.py` runs the mechanical merge checks and leaves the judgement items to Claude.

## About the data

- Source: the CFPB Consumer Complaint Database. Raw data is not stored in this repo.
- The CFPB says: "This database is not a statistical sample of consumers' experiences in the marketplace". Results here describe this data only.
- The CFPB also says: "All complaint data we publish is freely available for anyone to use, analyze, and build on." Both quotes are from the [CFPB complaint database page](https://www.consumerfinance.gov/data-research/consumer-complaints/), read 28 October 2026.
- The Product and Issue fields are set by the consumer, not by the CFPB ("The type of product the consumer identified in the complaint", [CFPB field reference](https://cfpb.github.io/api/ccdb/fields.html)). So the recorded labels are noisy, and some measured "errors" will be label noise.

## Loading a new month

- `voc load july_2026` and then `voc load august_2026` put each pinned monthly file into one staged DuckDB table. `voc dbt build` then builds the models and runs the data tests.
- The dbt models leave out the test set (B17). They read the test IDs from `splits/test.csv`. Setting the dbt variable `final` to true turns this off, and `voc dbt` always passes it as false. The staged table under the models still holds the test rows.
- The load and the staged dbt model are incremental and keyed on complaint ID. A run adds only complaint IDs it has not seen, so loading the same file again adds nothing.
- What this does not cover yet:
  - Late or corrected records. If a later file holds a complaint ID that is already loaded with changed values, the first row is kept and the change is ignored.
  - Column changes. A file with a missing or extra column fails the load. A new or removed column in the staged table fails the incremental dbt build (`on_schema_change='fail'`). Neither is migrated automatically.
- `voc dbt docs` writes the dbt docs and the lineage graph to the git-ignored `data/dbt/target` folder. Those files hold local paths, including the user folder. Strip the local paths before the lineage graph is published.

## Where to start

- What it must do: [specs/001-core-labelling-pipeline/spec.md](specs/001-core-labelling-pipeline/spec.md)
- How we work: [CLAUDE.md](CLAUDE.md)
- What happened and when: [BUILD_LOG.md](BUILD_LOG.md)
- How we measure: [docs/HOW_WE_MEASURE.md](docs/HOW_WE_MEASURE.md)
- What the data holds: [docs/DATA.md](docs/DATA.md)
