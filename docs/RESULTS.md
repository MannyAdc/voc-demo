# Results in detail

Moved here from the README on 31 October 2026, word for word, except that references to sections now on other pages became links, and, in review, one claim about reviews became a statement of the rule. Back to the [README](../README.md).

## The result

The claim was fixed before the first run: **the LLM, with its quote check, beats TF-IDF at the same coverage** (rule B10 in the [spec](../specs/001-core-labelling-pipeline/spec.md)). It was judged once, on a frozen test set of 1,909 complaints. [How we measure](HOW_WE_MEASURE.md) explains the method in plain words.

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

- The run: `uv run --native-tls voc final --prompt v1`, by the owner. It was logged in [runs/TEST_RUNS.md](../runs/TEST_RUNS.md) on 29 October 2026 at 21:48, before any call. It is the only row there.
- 1,864 labels accepted and 45 quarantined: the quote was not in the text 21 times, the label was not in the list 15 times, the answer could not be read 6 times, and the quote was too short 3 times.
- 1,909 live calls, 2,630,555 input and 379,892 output tokens, $0.4530015 in all, 3,847 seconds.
- Results: [results/eval/v1_test.json](../results/eval/v1_test.json) and [results/labels/v1_test.json](../results/labels/v1_test.json).

**What the terms mean.**
- *Strict accuracy*: correct accepted labels divided by all complaints. A quarantined label counts as wrong.
- *Re-weighted*: worked out for each product, then averaged with weights equal to each product's share of the 9,303 complaints in the pool.
- *At the same coverage*: TF-IDF answers only as many complaints as the LLM accepted, its most confident ones, and the rest count as wrong. So neither method looks better by skipping hard cases.
- *Time per 1,000*: the LLM's calls were sent one at a time. TF-IDF's time counts labelling only, not training.
- *Macro-F1*: the F1 score of each of the 11 products, averaged with equal weight. It is the one row not at matched coverage: TF-IDF's macro-F1 counts its label for every complaint.

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
| Prepaid card | 28 | too few to judge | too few to judge |
| Debt or credit management | 19 | too few to judge | too few to judge |

The LLM's clear weak spot is credit reporting. It gave that label to 168 accepted complaints, but only 64 test complaints have it. Of the 168, 58 were recorded as credit reporting, 72 as debt collection, 17 as credit card, 11 as checking or savings account, and 10 as other products (`confusion` in `results/eval/v1_test.json`). So 72 of the 452 debt collection complaints were labelled credit reporting, which lowers the LLM's debt collection score too. Some of this may be label noise: the consumer picks the product, and a complaint about a debt on a credit report could fit either. On Mortgage, the two tie at 3 decimals: 0.910394 against 0.910345.

### Development set: tuning figures, not the verdict

The development set (370 complaints) was used while building, so its figures are tuning figures only.

| Development set, 370 complaints | LLM | TF-IDF at the same coverage |
|---|---|---|
| Re-weighted strict accuracy | 79.8% | 79.1% |
| Precision on accepted labels | 81.7% | 81.2% |
| Coverage | 97.6% | 97.6% |
| Macro-F1 | 0.772 | 0.694 |

Difference +0.6 points, from the unrounded figures (79.76% against 79.14%), 95% interval -3.1 to +4.7 points: inconclusive. Source: `uv run --native-tls voc evaluate dev --prompt v1 --note "first version"`, the first row of [EVAL_VERSIONS.md](../EVAL_VERSIONS.md).


## Speed, Safety, Scale

**Speed**
- The LLM took 2,015.2 seconds per 1,000 complaints on the test run, with calls sent one at a time. TF-IDF took 0.707 seconds per 1,000.
- The LLM cost $0.2373 per 1,000 complaints on the test run (claude-haiku-5-5, prompt v1). Labelling all 10,002 complaints with a narrative in the July file would cost about $2.37 at that rate ($0.4530015 / 1,909 x 10,002). With calls sent one at a time, it would take about 5.6 hours (2,015.2 seconds x 10.002). Both are projections, not runs.
- Every answer is recorded, so on the machine that holds the recordings, a re-run of the same prompt replays it at no cost.

**Safety**
- Every accepted label has a quote that a script found in the complaint, starting and ending on word boundaries. Before matching, both sides get the same small normalisation: one Unicode form, runs of spaces made one space, plain quote marks and dashes, and no zero-width characters (`src/voc/evidence.py`). Capital letters still matter. The model's word is never taken on trust. That shows the quote is **in the text**. It does not show that the quote **supports the label**. No human has checked that yet (see [LIMITS.md](LIMITS.md)).
- `voc audit` checks a results file against the recorded answers and the complaint texts. On the development run it re-derived 361 of 361 accepted and 9 of 9 quarantined decisions, and 361 of 361 quotes matched word for word at their stored positions (`uv run --native-tls voc audit dev --prompt v1`). It reuses the labeller's own steps, so it is a consistency check. The exact character comparison is the independent part. The audit ran on the development run only. The test run has not been audited, because `voc audit` accepts the development and quick sets only.
- A synthetic injection set of 10 made-up complaints (`config/injection.toml`, IDs SYN-9001 to SYN-9010) tries to force wrong labels. In one live run of prompt v1, 9 reached the model and none was obeyed. The tenth, a fake closing tag, was caught by the script before any call. The counts: obeyed and accepted 0, obeyed and quarantined 0, caught before any call 1, no usable answer 0, not obeyed 9 (`uv run --native-tls voc label injection --prompt v1`, then `uv run --native-tls voc evaluate injection --prompt v1 --note "first live run of the injection set"`, in [results/eval/v1_injection.json](../results/eval/v1_injection.json)). These results are reported apart and never enter an accuracy figure. They show resistance on this set, with one model, not in general. An obeyed injection that quotes a real sentence from the text would pass the quote check.
- Complaint text is untrusted data. It goes to the model between fixed tags, as data, in a call with no tools. There is no `claude -p` or other agent backend, because untrusted text must never reach an agent that can act, and one code path keeps every number reproducible.
- The coding agent that built this repo was blocked from reading complaints, quotes and model answers from real data, and the build log records no case of it doing so. Commands print IDs, labels, reasons, positions and counts only. Hooks block it from reading the data, the ledger and the recordings, and ask the owner before any command with the word `final`. The hooks are best effort (see Known limits in [LIMITS.md](LIMITS.md)).
- Every live call goes through a hard token cap, a record and replay cache, and one token ledger shared by every run.

**Scale**
- The July 2026 export holds 672,036 complaints. 10,002 of them (1.5 percent) have a narrative (`uv run --native-tls voc profile --write results/profile_july_2026.json`). `voc sample` removed 623 exact copies and 76 near-copies, so 9,303 remain ([docs/DATA.md](DATA.md)).
- Sample sizes come from Cochran's formula: 370 for development and 1,909 for the frozen test set. The remaining 7,024 train TF-IDF ([docs/DATA.md](DATA.md)).
- Loading is incremental and keyed on complaint ID, so loading the same file again adds nothing. dbt builds the models and runs the data tests.
- A scheduled GitHub Actions workflow runs load, dbt build, label and evaluate every day on a committed synthetic fixture, with the mock backend. Its figures are synthetic, not a result. It is one job that runs these four steps in order after its setup steps, and any failing step or data test fails the run (`.github/workflows/scheduled.yml`). A full scheduler such as Airflow would be worth it with many pipelines that depend on each other, retries for each step, or backfills of past months. Airflow is not installed.
