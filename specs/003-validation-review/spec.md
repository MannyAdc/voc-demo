# Feature Specification: Validation review

**Feature Branch**: `003-validation-review`

**Created**: 2026-11-02

**Status**: Draft for the owner. Written from the owner's request and choices of 2 November 2026 (BUILD_LOG.md).

**Input**: The owner asked for a careful, independent look at how far the LLM labeller can be trusted, written up as `docs/VALIDATION.md`.

Requirement IDs are `V1`, `V2` and so on. Tests are named `test_V<number>_...`. V1 to V6 are the six pieces of work. V7 to V10 hold for all of them.

## What it is

Six pieces that check the labeller from different sides: does it give the same answer twice (V1), how much of its measured error is really the consumer's choice (V2), was the quote check right to stop what it stopped (V3), does each quote support its label (V5), and what the LLM's gain costs, with one hybrid tried (V6). V4 writes it all up. Every measurement uses the development set (370 complaints) or results already recorded. The sealed test set is not scored again.

## Rules for every piece

- **V7. The test set stays closed.** No new command reads a test row, a test label or a test recording. Every new command checks its IDs against the development list and refuses any other ID. V6 may use the test set's published figures in the README, as plain arithmetic, never by reading test rows again.
- **V8. No complaint text in git.** Committed results hold complaint IDs, labels, positions, decisions, codes and counts only (as B19 and B21). Review sheets, which hold complaint text, are written only to a review folder inside the home folder's `.voc`, which the read guard blocks for Claude. The owner runs every command that writes or reads a review sheet. Claude never opens a sheet. The judge's reasons (V5) stay in the recordings and the review folder, never in a results file or a printout.
- **V9. Spend only after approval.** Every paid command first prints the number of calls, the expected cost, the worst-case tokens the ledger will reserve and the tokens left under the cap. Claude runs it live only after the owner approves those figures in the chat. Every live answer goes through the ledger and is recorded, as B7 and B8.
- **V10. Small samples carry intervals.** Every share from a sample has a 95% interval. Shares use the Wilson score interval. Kappa and the hybrid's difference use a bootstrap with 2,000 draws and seed 0. Each figure in `docs/VALIDATION.md` names its sample size and the command and file it comes from.

## The six pieces

- **V1. Run-to-run consistency.** A frozen list of 100 development IDs, drawn at random with a fixed seed. `voc consistency` labels them again with prompt v1, the same model and the same settings, as fresh live calls. A repeat number is added to the recording key only, never to what is sent, so the recordings of 29 October are never replayed and the new answers are recorded apart. For each complaint it compares the new answer with the recorded one: the proposed label (same or different), the decision (accepted or quarantined, same or changed), and the quote, by its start and end positions in the same cut text (same, overlapping or apart). It prints counts and shares with intervals, and writes `results/validation/v1_consistency.json`. It can be run again with a new repeat number. Limit: a difference may come from randomness or from a quiet model update under the same model ID. The two cannot be told apart.
- **V2. Disagreement review.** A frozen list of 40 development IDs, drawn at random with a fixed seed from the accepted labels that differ from the consumer's recorded product. The owner runs `voc review sheet v2`, which writes a sheet with the complaint text, the LLM's label and quote, and the consumer's choice. The owner marks each one with a code: `llm_right`, `consumer_right`, `both_plausible` or `unclear`. The owner then runs `voc review import v2`, which reads only the ID and code columns, refuses any ID not on the list or any code not in the list, and writes `results/validation/v2_codes.csv`. The summary gives each code's share with its interval, and the share of the measured disagreements that is label noise: `llm_right` alone as the lower figure, `llm_right` plus `both_plausible` as the upper one.
- **V3. Quarantine review.** Every quarantined development complaint (9 in `results/labels/v1_dev.csv`). The same sheet and import commands, as `v3`, show each one's reason. The codes are `check_right`, `check_wrong` and `unclear`. The result is a plain list of IDs, reasons and codes, with counts. Nine cases are too few for a reliable share. The interval is given and the text says so.
- **V5. LLM as a judge, checked against a human.** Today the script proves each quote is in the complaint, not that it supports the label (README).
  - *The judge* is claude-sonnet-5-5, a different model from the labeller, with no tools, through the same recorded and ledgered path. It reads the cut complaint text, the accepted label and its quote, and answers with one rating, `supports`, `partly` or `does_not_support`, and a short reason. An answer outside the three ratings is `unparseable`. Its price is added to `config/prices.toml` from Anthropic's pricing page. Limit: a judge from the same model family reduces self-preference but does not remove it.
  - *The rubric* is written in `config/prompts/judge_v1.toml` before any judge call. A dry run on a frozen list of 10 accepted development labels comes first. The 10 are never reported. After the dry run the rubric may change once, and is then committed and frozen before any reported case runs. The dry run also checks the ledger's input margin for this model (`config/budget.toml` asks a new model for its own check).
  - *The owner's ratings.* A frozen list of 50 accepted development labels, drawn at random with a fixed seed, leaving out the 10 dry-run IDs. It may overlap V2's list. The owner rates them blind, with the same three ratings, through `voc review sheet v5` and `voc review import v5`, before the judge's main run. The sheet holds no judge rating.
  - *The judge's main run* covers every accepted development label except the 10 dry-run IDs: 351 calls. It writes the ratings to `results/validation/v5_judge.csv`.
  - *The report:* the judge's rating shares over the 351, with intervals. On the 50: the percent agreement, Cohen's kappa with its bootstrap interval, the 3 by 3 confusion table, and the IDs where the judge and the owner differ, with both ratings. No judge reason is reported. The owner may add a short note in their own words.
- **V6. Cost against gain, and a hybrid.** From recorded results only, with no model call.
  - *Cost per extra correct label* against the baseline, from the published test figures (the cost per 1,000 complaints and the lead in points), and the same on the development set.
  - *Time per 1,000 at scale* is an estimate, labelled as one: the recorded time per call, divided by an assumed number of calls in parallel. No paid run measures it.
  - *The hybrid,* fixed in advance: the baseline answers when its top class probability is at least 0.9, otherwise the LLM's answer is used, and a quarantined LLM answer counts as wrong. It is scored on the development set only, against the LLM alone, with the share each method answered and the paired bootstrap difference. It is reported as exploratory and optimistic, because the prompt was tuned on the same set and no untouched test set is left to check it.
- **V4. `docs/VALIDATION.md`.** A plain-language summary first: what we checked, what we found, what it means and what we would do next. Then the method and the figures, for technical readers. Results that do not favour the LLM are reported the same way as the rest. The README links it. Every figure has its command and file, as in the README.

## Pull requests, in order

1. This spec, the change to B16, and the test list.
2. The read guard blocks the review folder.
3. The frozen lists: V1 (100), V2 (40), V5 (50) and the dry run (10).
4. V1, then its paid run after approval.
5. The review sheet and import commands, for V2 and V3.
6. V5: the judge, the dry run, the owner's ratings, then the main run after approval.
7. V6.
8. `docs/VALIDATION.md` and the README link.

## Not in scope

- Any new score on the test set.
- A judge or a labeller from another company.
- A paid run with calls in parallel.
- Changing the labelling prompt.

## Known limits

- Every sample is small. The intervals are wide, and the text says so.
- The consumer's recorded product is the answer key and is itself noisy. V2 measures how noisy, on 40 cases only.
- The judge's reasons are model text and stay local, so a reader of the repo sees ratings, not reasons.
