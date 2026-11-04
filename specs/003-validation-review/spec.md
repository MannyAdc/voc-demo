# Feature Specification: Validation review

**Feature Branch**: `003-validation-review`

**Created**: 2026-11-02

**Status**: Draft for the owner. Written from the owner's request and choices of 2 November 2026 (BUILD_LOG.md, 2 November).

**Input**: The owner asked for a careful, independent look at how far the LLM labeller can be trusted, written up as `docs/VALIDATION.md`.

Requirement IDs are `V1`, `V2` and so on. Tests are named `test_V<number>_...`. V1 to V6 are the six pieces of work. V7 to V10 hold for all of them.

## What it is

Six pieces that check the labeller from different sides: does it give the same answer twice (V1), how much of its measured error is really the consumer's choice (V2), was the quote check right to stop what it stopped (V3), does each quote support its label (V5), and what the LLM's gain costs, with one hybrid tried (V6). V4 writes it all up. Every measurement uses the development set (370 complaints) or results already recorded. The sealed test set is not scored again.

## Rules for every piece

- **V7. The test set stays closed.** No new command reads a test row, a test label or a test recording. Every new command checks its IDs against the development list and refuses any other ID. V6 may use the test run's published summary, `results/eval/v1_test.json`, the file the README's figures come from. It never reads `results/eval/v1_test.csv` or any other per-complaint test file.
- **V8. No complaint text in git.** Committed results hold complaint IDs, labels, positions, decisions, codes and counts only (as B19 and B21). Review sheets, which hold complaint text, are written only to a review folder inside the home folder's `.voc`, which the read guard blocks for Claude. The sheet command refuses any other folder. The owner runs every command that writes or reads a review sheet. Claude never opens a sheet. The judge's reasons (V5) stay in the recordings and the review folder, never in a results file or a printout. No judge prompt and no sheet shows the consumer's recorded product, except V2's sheet, whose purpose is to compare it.
- **V9. Spend only after approval.** Every paid command first prints the number of calls, the expected cost, the worst-case tokens the ledger will reserve and the tokens left under the cap. Without `--approved` it stops there, with no call. Claude passes `--approved` only after the owner approves those figures in the chat. Every live answer goes through the ledger and is recorded, as B7 and B8.
- **V10. Small samples carry intervals.** Every share from a sample has a 95% interval. Shares use the Wilson score interval. Kappa and the hybrid's difference use a bootstrap with 2,000 draws and seed 0. Each figure in `docs/VALIDATION.md` names its sample size and the command and file it comes from.

## The frozen lists

Drawn once, from the development set only, with a fixed seed, in this order, and committed in `splits/` with their hashes (B16):

1. The dry run: 10 accepted development labels.
2. V5: 50 accepted development labels, at random, leaving out the dry run.
3. V2: 40 accepted development labels that differ from the consumer's recorded product, at random, leaving out the dry run and V5. So V2 and V5 never share a case, and V5 stays a plain random sample.
4. V1: 100 development IDs, at random from all 370. V1 may share cases with the other lists, because nobody rates them by hand.

## The six pieces

- **V1. Run-to-run consistency.** `voc consistency` labels V1's 100 again with prompt v1, the same model and the same settings, as fresh live calls.
  - *The recording key.* `recording_key` (`src/voc/replay.py`) takes an optional repeat number. With none, the key is exactly as before, so the recordings of 29 October still replay. With one, the number joins the key material only, never what is sent to the model. The new answers are recorded apart, and the command can be run again with a new number.
  - *The comparison,* for each complaint, new answer against recorded answer:
    - the decision: both accepted, both quarantined, or changed
    - the proposed label: same, different, or missing in one or both (an `unparseable` answer has no label)
    - the quote, only when both answers are accepted: same start and end, overlapping, or apart. Otherwise the quote is "not compared", counted apart.
  - It prints counts and shares with intervals, and writes `results/validation/v1_consistency_r<repeat>.json` and `.csv`, one pair for each repeat number. It refuses to write over a pair that exists. *Changed on 3 November in pull request 4: the file names carry the repeat number, so a second run does not replace the first.*
  - Limit: a difference may come from randomness or from a quiet model update under the same model ID. The two cannot be told apart.
- **V2. Disagreement review.** V2's 40. The owner runs `voc review sheet v2`, which writes a sheet with the complaint text, the LLM's label and quote, and the consumer's choice. The owner marks each one with a code: `llm_right`, `consumer_right`, `both_plausible` or `unclear`. The owner then runs `voc review import v2`, which reads only the ID and code columns and writes `results/validation/v2_codes.csv`. The summary gives each code's share with its interval, and the share of the measured disagreements that is label noise: `llm_right` alone as the lower figure, `llm_right` plus `both_plausible` as the upper one.
- **V3. Quarantine review.** Every quarantined development complaint: 9 in `results/labels/v1_dev.csv` (7 `quote_not_in_text`, 2 `unparseable`). The same sheet and import commands, as `v3`, show each one's reason, the text, and the proposed label and quote where the answer gave them. For the 2 `unparseable` ones, the sheet says that no label or quote could be read. The codes are `check_right`, `check_wrong` and `unclear`. The import writes `results/validation/v3_codes.csv`. The result is a plain list of IDs, reasons and codes, with counts. Nine cases are too few for a reliable share. The interval is given and the text says so.
- **The summary, for V2 and V3.** *Added on 4 November, for V10:* `voc review summary v2` or `v3` recomputes the figures from the committed codes only, with no sheet and no model call, checked as the import checks them, and writes `results/validation/v2_summary.json` or `v3_summary.json`. Claude may run it, because it reads no complaint text.
- **The import, for V2, V3 and V5.** Every ID on the list must appear exactly once, with a code from the list. A missing ID, a repeated ID, an ID not on the list, a blank code or an unknown code refuses the whole import, and nothing is written. The refusal names IDs and counts only. *Added on 3 November in pull request 5:* a sheet that exists is never written over, so no marks are lost, and an import that would write over codes imported before needs `--replace`. The sheet is saved as UTF-8 with the mark spreadsheets need, and the import also reads a sheet a spreadsheet saved in the Windows code page.
- **V5. LLM as a judge, checked against a human.** Today the script proves each quote is in the complaint, not that it supports the label (README). *Added on 4 November:* V5 checks the evidence, not whether the label is right. The LLM labels from the whole complaint, and V5 rates only the quote it gives.
  - *The judge* is claude-sonnet-5-5, a different model from the labeller, with no tools, through the same recorded and ledgered path. It reads the cut complaint text, the accepted label and its quote, never the consumer's product. It answers with one rating, `supports`, `partly` or `does_not_support`, and a short reason. An answer outside the three ratings is `unparseable`. Its price is added to `config/prices.toml` from Anthropic's pricing page. Limit: a judge from the same model family reduces self-preference but does not remove it.
  - *The rubric* is written in `config/prompts/judge_v1.toml` before any judge call. The dry run on its 10 comes first. They are never reported. After the dry run the rubric may change once, as `judge_v2.toml`, committed before any reported case runs. The version used is then frozen.
  - *The token margin.* The ledger's input margin in `config/budget.toml` was checked on Haiku only. The dry run checks every answer's real input tokens, replayed ones too, against its reserved estimate. If any call goes over, or none had token counts, the main run waits, and the owner decides a new margin, merged in its own pull request.
  - *The dry run is never reported.* It writes only its call counts, the margin check and the recording keys. The owner reads its ratings and reasons with `voc review sheet v5_dry_run`, which only the owner runs. *Added on 3 November after the review of #75, with the next three rules.*
  - *The rubric in use.* A judge is named `judge_v` and a number. The one change, the next number, may change only the instructions, not the settings. Once it exists, the main run uses it, and otherwise the dry run's judge. A live run needs the rubric and `config/labels.toml`, which both go into the prompt, committed and unchanged. A dry run's summary with no margin result, such as a mock run's, does not count as the one dry run.
  - *Failures.* Three failed cases in a row stop a run, as for the labeller (B7), and a run with any failure writes no results. The judge's output limit is the labeller's, 2,048 tokens.
  - *Blinding.* Once the judge's main run exists and the owner's V5 ratings are imported, they cannot be imported again.
  - *The one redo.* The owner's first V5 ratings were withdrawn on 3 November, before #76 merged: their sheet did not state the judge's question or give the label definitions, so they answered a different question (whether the label fits the whole complaint). They are not a V5 result. The owner rates the 50 again once, on a sheet that gives what each label covers, still with no judge rating and no consumer's product. Writing the sheet prints the judge's question and three ratings in the rubric's words, in the owner's terminal. The import needs the sheet's `label_covers` column, so the first sheet cannot be imported as the redo. That one import may come after the judge's main run, and is refused once V5 ratings are imported. Deleting `v5_codes.csv` would open it again, which only git history would show. The agreement, the kappa and the table use the redo only. Limits: the owner has seen these 50 before, read the judge's 10 dry-run answers, knows from the totals that the judge was stricter, and could look up the judge's committed rating of any case.
  - *The owner's ratings.* V5's 50, rated blind with the same three ratings, through `voc review sheet v5` and `voc review import v5`. The sheet holds no judge rating and no consumer's product. The judge's main run refuses until these ratings are imported. The ratings used are the one redo below, imported after the main run.
  - *The judge's main run* covers every accepted development label except the dry run: 351 calls. It never includes a dry-run ID. It writes the ratings to `results/validation/v5_judge.csv`.
  - *The report:* the judge's rating shares over the 351, with intervals. On the 50: the percent agreement, Cohen's kappa with its bootstrap interval, the 3 by 3 confusion table, and the IDs where the judge and the owner differ, with both ratings. An `unparseable` judge answer is listed by ID, counted apart, and left out of the agreement, the kappa and the table. No judge reason is reported. The owner may add a short note in their own words. Added on 4 November: `voc judge agreement` recomputes these figures from the committed IDs and ratings only, with no model call, and writes them to `results/validation/v5_agreement.json`.
- **V6. Cost against gain, and a hybrid.** From recorded results only, with no model call.
  - *Cost per extra correct label* against the baseline: from the test run's published summary (`results/eval/v1_test.json`: the cost per 1,000 complaints and the lead in points), and the same from the development set's files. Changed in the review of #80: in two views. At the same coverage, the headline rule fixed before the first run (B10), and with the baseline labelling every complaint, from the summary's confusion tables. A lead in re-weighted points only approximates extra correct labels per 1,000.
  - *Time per 1,000 at scale* is an estimate, labelled as one: the test run's published time per 1,000 (all its calls were live, in `results/eval/v1_test.json`), divided by an assumed number of calls in parallel. The development run cannot give it, because 63 of its 370 answers were replayed. No paid run measures it.
  - *The hybrid,* fixed in advance, one rule for every product with no per-product split: the baseline answers when its top class probability is at least 0.9, otherwise the LLM's answer is used, and a quarantined LLM answer counts as wrong. It is scored on the development set only, as B10 scores: re-weighted strict accuracy, against the LLM alone, with the share each method answered and the paired bootstrap difference, drawn within each product. It is reported as exploratory and optimistic, because the prompt was tuned on the same set and no untouched test set is left to check it. Added in the review of #80: the 0.9 was fixed on 2 November, after the development results were published on 29 October, so it is reported that way too.
- **V4. `docs/VALIDATION.md`.** A plain-language summary first: what we checked, what we found, what it means and what we would do next. Then the method and the figures, for technical readers. Results that do not favour the LLM are reported the same way as the rest. The README links it. Every figure has its command and file, as in the README. *Added on 4 November (owner decision):* it opens with a table of what each check measures and does not, and `docs/HOW_WE_MEASURE.md` gains a worked example of agreement and kappa. The README gains one link line only.

## Pull requests, in order

1. This spec, the change to B16, and the test list.
2. The review folder: the read guard already blocks the whole home `.voc`, so this adds a test that pins it for the review folder, and the sheet command's refusal of any other folder.
3. The frozen lists, in the order above.
4. V1, then its paid run after approval.
5. The review sheet and import commands, for V2 and V3.
6. V5: the judge, the dry run, the owner's ratings, then the main run after approval.
7. V6.
8. `docs/VALIDATION.md` and the README link.

## Not in scope

- Any new score on the test set.
- A judge or a labeller from another company.
- A paid run with calls in parallel.
- A hybrid with a different rule for each product.
- Changing the labelling prompt.

## Follow-ups, planned

- The baseline's name. The baseline is TF-IDF features fed into a logistic regression (`voc.baselines`). Owner decision of 4 November: new reader-facing text says "TF-IDF + LR", spelled out on first use, from V6 on. The README, the docs and the dashboard, published on 1 November, still say "TF-IDF" as the short name, after naming it in full once. They are changed to "TF-IDF + LR" in their own wording-only pull request after `docs/VALIDATION.md`, with no number or conclusion changed. Code names and data keys keep "tfidf".

## Known limits

- Every sample is small. The intervals are wide, and the text says so.
- The consumer's recorded product is the answer key and is itself noisy. V2 measures how noisy, on 40 cases only.
- The judge's reasons are model text and stay local, so a reader of the repo sees ratings, not reasons.
- V5: as for V1 below, a case whose call fails the same way every time, such as a refusal, blocks the judge's main run, and every rerun pays for that one call again. The run stops after 3 failures in a row, so a rerun costs little. The owner decides what to do if it happens. *Added on 3 November after the second review of #75.*
- V1: a complaint whose call fails the same way every time is never recorded, so every rerun of that repeat
  pays for it again and the repeat cannot finish. The run stops after 3 failures in a row, so each rerun costs
  little. The owner decides what to do if it happens. *Added on 3 November after the second review of #72.*
