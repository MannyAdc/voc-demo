# Validation review: how far can the labeller be trusted?

The main result in the [README](../README.md) answers one question: does the LLM label more complaints correctly than a simple baseline? This page checks the labeller from other sides. Does it give the same answer twice? How many of its "mistakes" are really the consumer's? Did the quote check stop the right cases? Does each quote really back up its label? And what does the LLM's gain cost?

The checks ran from 3 to 4 November 2026, under rules written on 2 November in [spec 003](../specs/003-validation-review/spec.md). They used the development set, the 370 complaints used to build and tune the labeller, or results already recorded. The sealed test set was not scored again. Complaint text is never committed to this repo. The results files hold IDs, labels, codes, positions and counts.

The baseline is TF-IDF with logistic regression (TF-IDF + LR): word scores fed into a standard statistical model. [What we compare](HOW_WE_MEASURE.md#what-we-compare) explains it in plain words.

## In plain words

**What we checked.**

- Whether the LLM gives the same label when asked again.
- Whether the consumer's own choice of product, our answer key, is sometimes the one that is wrong.
- Whether the quote check was right to hold back the labels it held back.
- Whether the quote the LLM gives as its evidence really backs up its label.
- What each extra correct label costs, and whether mixing the two methods helps.

**What we found.**

- The LLM is steady. Asked again, it gave the same label for 97 of 100 complaints. It often chose a different passage as its quote, though.
- The answer key is noisy. Where the LLM and the consumer disagreed, the owner judged the LLM right in 25 of 40 cases and the consumer right in only 7. The owner knew which label was the LLM's, so this may lean towards the LLM.
- Each time the quote check held a label back, it was right: 9 of 9.
- By the judge's ratings, the quote fully backs up the label in about 6 of 10 cases, and only partly in about 1 of 3. The judge is a second model. The owner, rating 50 of the same quotes, was less strict.
- The judge and the owner often rated the same quote differently. They agreed only a little more than luck would give.
- Each extra correct label costs about 1 to 2 cents on the test set, depending on how it is counted, and the range is wide. On the development set, against TF-IDF + LR labelling every complaint, the LLM gained nothing.

**What it means.**

- The LLM is probably right more often than its measured accuracy shows. This rests on 40 development cases, coded by one person who was not blind.
- The quote shown with each label is a pointer to the reason, not proof. A person should still read it.
- A model judge cannot replace that person yet.

**What we would do next.** Ask for several quotes from different parts of the complaint, retry an unreadable answer once, and check whether weak evidence goes with wrong labels. See [What we would do next](#what-we-would-do-next).

## What each check measures

Each check answers a different question. None of them alone says how good the labeller is. V4 is this page.

| Check | The question | What it measures | What it does not measure | Result |
|---|---|---|---|---|
| The main result ([README](../README.md#-the-result)) | Is the label right? | Accuracy against the consumer's choice | Whether the evidence is good | 80.3% against 77.9% for TF-IDF + LR, on 1,909 test complaints ([results/eval/v1_test.json](../results/eval/v1_test.json)) |
| V1 | Same answer twice? | Reliability | Whether the answer is right | Same label for 97 of 100 |
| V2 | Is the "error" the consumer's? | Noise in the answer key | TF-IDF + LR's errors | LLM right in 25 of 40, by the owner's coding |
| V3 | Was the quote check right to hold a label back? | The safety check | Labels that were accepted but should not have been | Right in 9 of 9 |
| V5 | Does the quote, on its own, back up the label? | The evidence | Whether the label is right | Fully in 213 of 351 (60.7%), by the judge's ratings |
| V6 | What does the gain cost? | Cost against gain | Quality | About 1 to 2 cents per extra correct label, on the test set |

**V5 checks the evidence, not whether the label is right.** The LLM reads the whole complaint, chooses the label, then copies one short passage as its evidence. V5 rates only that passage. A label can be right with weak evidence: the complaint is clearly about a mortgage, but the passage only says "my loan payment". A label can also be wrong with evidence that looks fine: a passage that mentions a credit card can seem to back "Credit card" when the complaint is mainly about a bank account. So V5 says how far an analyst can rely on the quote. How often the label is right is the main result's question.

## The method and the figures

Every share from a sample has a 95% interval. It is the range the true figure very likely lies in: 95 times out of 100, as [How many complaints we score](HOW_WE_MEASURE.md#how-many-complaints-we-score) explains. For a share, we use the Wilson score interval, a standard range for a share from a small sample. The samples here are small, so the ranges are wide.

The lists for V1, V2, V5's 50 and the judge's dry run were drawn once, at random, from the development set, and committed before any rating (`splits/validation/`, by `voc validation-lists`). V3 takes every quarantined development complaint. The judge's main run takes every accepted development label except the dry run's.

### V1: does it give the same answer twice?

**Sample.** 100 development complaints, at random. Each was labelled again with the same model (claude-haiku-5-5), the same prompt (v1) and the same settings, as a fresh live call.

**Command and file.** `voc consistency --repeat 1 --approved`, run once by the owner on 3 November 2026, written to [results/validation/v1_consistency_r1.json](../results/validation/v1_consistency_r1.json). 100 live calls, $0.0229437.

| Compared with the first answer | Count | Share (95% interval) |
|---|---|---|
| The same label | 97 of 100 | 97.0% (91.5% to 99.0%) |
| The same decision, accepted or held back | 98 of 100 | 95 accepted both times, 3 held back both times |
| The quote, where both answers were accepted: the same passage | 63 of 95 | 66.3% (56.3% to 75.0%) |
| An overlapping passage | 19 of 95 | 20.0% (13.2% to 29.1%) |
| A passage elsewhere in the text | 13 of 95 | 13.7% (8.2% to 22.0%) |

Of the 3 different labels, 1 is the marker "(not in list)": the second answer named no listed product, so it was held back. So 2 of 100 moved to another product. The decision changed for 2 of 100. Both were accepted the first time and held back the second.

**What it means.** The label is steady. The evidence is less so: for about 1 complaint in 3, a second try picks a different passage. Several passages often fit, so this is not an error. But it shows that the quote is one possible reason, not the only one.

**Limit.** A difference may come from chance or from a quiet update of the model behind the same name. The two cannot be told apart.

### V2: how many "errors" are really the consumer's?

**Sample.** 40 accepted labels where the LLM's label differs from the product the consumer chose: 40 of the 66 accepted disagreements in the development set, at random.

**How.** The owner read each complaint, with the LLM's label and quote and the consumer's choice, and coded who was right.

**Command and file.** `voc review summary v2`, from the owner's codes in [results/validation/v2_codes.csv](../results/validation/v2_codes.csv), written to [results/validation/v2_summary.json](../results/validation/v2_summary.json).

| Code | Count | Share (95% interval) |
|---|---|---|
| The LLM is right | 25 of 40 | 62.5% (47.0% to 75.8%) |
| The consumer is right | 7 of 40 | 17.5% (8.7% to 32.0%) |
| Both are plausible | 0 of 40 | 0.0% (0.0% to 8.8%) |
| Unclear | 8 of 40 | 20.0% (10.5% to 34.8%) |

**What it means.** By the owner's coding, about 6 in 10 of these disagreements are noise in the answer key, not the LLM's mistakes (47.0% to 75.8%). So the measured accuracy likely understates how often the LLM is right.

**Limits.**

- The coding was not blind. The owner saw the LLM's label and quote while coding, and built the system, so the codes may lean towards the LLM.
- Only the LLM's disagreements were reviewed, not TF-IDF + LR's. TF-IDF + LR learns from the consumers' choices, so its errors may differ in kind.
- The published comparison is not corrected for this. A corrected answer key might move both methods.

### V3: was the quote check right to hold a label back?

**Sample.** All 9 quarantined development complaints: 7 whose quote was not in the text, and 2 whose answer could not be read.

**Command and file.** `voc review summary v3`, from the owner's codes in [results/validation/v3_codes.csv](../results/validation/v3_codes.csv), written to [results/validation/v3_summary.json](../results/validation/v3_summary.json).

**Result.** The check was right in 9 of 9 (95% interval 70.1% to 100.0%). Nine cases are too few for a reliable share, as the wide interval shows. V3 cannot see labels that should have been held back but were accepted.

### V5: does each quote back up its label?

**The judge.** A second model, claude-sonnet-5-5, with no tools. It read the complaint text as the labeller saw it (cut at the same length limit), the accepted label, what the label covers and the quote. It never saw the consumer's product. It answered one of three ratings: the quote on its own makes the product clear (**supports**), it points to the product's area but not clearly to this product (**partly**), or it does not point to this product (**does not support**). Its rubric, [config/prompts/judge_v1.toml](../config/prompts/judge_v1.toml), was written before any judge call, tried on a dry run of 10 other labels that is not reported, and not changed after.

**Sample.** 351 accepted labels: every accepted development label except the 10 of the dry run.

**Command and file.** `voc judge main --approved`, run once by the owner on 3 November 2026, written to [results/validation/v5_judge.json](../results/validation/v5_judge.json). 351 live calls, $0.829388.

| Judge's rating | Count | Share (95% interval) |
|---|---|---|
| Supports | 213 of 351 (60.7%) | 55.5% to 65.7% |
| Partly | 125 of 351 (35.6%) | 30.8% to 40.8% |
| Does not support | 13 of 351 (3.7%) | 2.2% to 6.2% |

**Checking the judge against a person.** The owner rated 50 of them, at random, with the same three ratings and the same question, on a sheet with no judge rating and no consumer's product. The owner's first ratings were withdrawn and redone, because their sheet did not state the judge's question or say what each label covers, and only the second ratings are used.

**Command and file.** `voc judge agreement`, from [results/validation/v5_codes.csv](../results/validation/v5_codes.csv) and [results/validation/v5_judge.csv](../results/validation/v5_judge.csv), written to [results/validation/v5_agreement.json](../results/validation/v5_agreement.json). No model call.

| Owner's rating, then the judge's | Supports | Partly | Does not support |
|---|---|---|---|
| Supports (37) | 24 | 11 | 2 |
| Partly (9) | 3 | 5 | 1 |
| Does not support (4) | 2 | 1 | 1 |

- They gave the same rating to 30 of 50 quotes: 60% agreement (95% interval 46.2% to 72.4%).
- Both mostly said "supports", so about 50% would match by luck alone.
- Beyond luck, they agreed only a little: Cohen's kappa 0.21, with a 95% interval of −0.01 to 0.43. Kappa is 0 for no better than luck and 1 for full agreement. [How we check agreement](HOW_WE_MEASURE.md#how-we-check-agreement-between-two-raters) explains it step by step.
- Where they differed, the judge was the stricter in 14 cases and the owner in 6.

The kappa interval comes from 2,000 draws of the 50 pairs, with replacement, seed 0. Its ends are the 51st and the 1,950th of the 2,000 kappas, in order.

**What it means.** By the judge's ratings, about 6 in 10 quotes fully back up their label on their own, and about 1 in 3 only partly. The owner rated more of the same 50 as "supports": 37 of 50 (74%), against the judge's 29 (58%). One possible reason for the many "partly" ratings is that the prompt asks for one short passage that shows the product, not the passage that explains the whole choice. That was not measured. The judge and a person often read the same quote differently, and the judge was usually the stricter. So the judge's ratings describe the evidence roughly, but they cannot stand in for a person.

**Limits.**

- One person rated, and that person had seen these 50 before, read the judge's 10 dry-run answers, and knew from the totals that the judge was stricter.
- The judge's reasons are model text, so they stay on the owner's machine. A reader of this repo sees the ratings, not the reasons.
- A judge from the same model family as the labeller may favour its answers. A different model reduces this, but does not remove it.

### V6: what does the gain cost?

**Command and file.** `voc cost-hybrid`, from the recorded results only, with no model call, written to [results/validation/v6_cost_hybrid.json](../results/validation/v6_cost_hybrid.json). The test figures come from the test run's published summary, [results/eval/v1_test.json](../results/eval/v1_test.json), never from a per-complaint test file.

**Two terms.** Coverage is the share of complaints with an accepted label. "At the same coverage" means that TF-IDF + LR answers only as many complaints as the LLM accepted, its most confident ones, so neither method looks better by skipping hard cases ([One more fairness rule](HOW_WE_MEASURE.md#one-more-fairness-rule)). Scores are re-weighted: each product counts by its share of the 9,303 complaints in the pool, not by its share of the sample.

**Cost per extra correct label.** On the test set, the LLM costs $0.2373 per 1,000 complaints. At the same coverage, its score is +2.40 points higher than TF-IDF + LR's, so it labels about 24 more of every 1,000 correctly. Each extra correct label then costs about 1 cent. The lead's 95% interval runs from +0.5 to +4.1 points, so the cost could be anywhere from 0.6 to 4.6 cents. A lead in re-weighted points only approximates extra correct labels.

| Set | Against TF-IDF + LR at the same coverage (the headline rule) | Against TF-IDF + LR labelling every complaint |
|---|---|---|
| Test set, 1,909 complaints, $0.2373 per 1,000 | $0.009891 (lead +2.40 points) | $0.016312 (lead +1.45 points) |
| Development set, 370 complaints, $0.2332 per 1,000, tuning figures | $0.037929 (lead +0.61 points) | no gain (lead −0.48 points) |

When TF-IDF + LR labels every complaint, it no longer skips its least confident ones, while the LLM's held-back labels still count as wrong. On the development set it then scores slightly higher than the LLM, so the LLM's gain there is none. The development figures are tuning figures (rule B10): the prompt was tuned on that set, so they may look better than the same method would on new data.

**Time per 1,000 at scale, an estimate.** The test run sent its calls one at a time and took 2,015.2 seconds per 1,000 complaints. With 10 calls at a time, that would be about 201.5 seconds. With 50, about 40.3 seconds. This assumes no rate limit, and no run measured it.

**One mix of the two methods.** Fixed before it ran: TF-IDF + LR answers when its top confidence is at least 0.9, and the LLM answers the rest. On the development set it scored 81.9% against 79.8% for the LLM alone. From the unrounded figures, that is +2.2 points (95% interval +0.8 to +3.8, from a paired bootstrap of 2,000 draws within each product, as in [How we decide who wins](HOW_WE_MEASURE.md#how-we-decide-who-wins)). TF-IDF + LR answered 20.5% of the complaints, so the LLM's cost per 1,000 on the development set would fall from $0.2332 to $0.185299, if every complaint costs the same.

This result is exploratory and optimistic. The prompt was tuned on the same set. The 0.9 was set on 2 November, after the development results were published on 29 October. No untouched test set is left to check it.

### What this review cost

$0.88 in all: $0.0229437 for V1, $0.024326 for the judge's dry run ([results/validation/v5_dry_run.json](../results/validation/v5_dry_run.json)) and $0.829388 for the judge's main run. V2, V3 and V6 made no model call.

## Limits

- Every sample is small, so every range is wide.
- The answer key is the consumer's own choice, and V2 shows it is noisy. V2 measured this on 40 cases only.
- One person did every human review, and that person also owns the project. In V2 the owner saw the LLM's label while coding.
- Only one month of data, one labelling model and one prompt version were checked.

All the project's limits are in [LIMITS.md](LIMITS.md).

## What we would do next

Not done yet:

- **Several quotes from different parts of the complaint** (prompt v2), so that the evidence covers the whole choice, not one short passage. V1 and V5 both point here.
- **One automatic retry for an unreadable answer** (prompt v2). 2 of the 9 labels held back were unreadable.
- **Check whether weak evidence goes with wrong labels.** Compare the judge's "partly" and "does not support" ratings with whether those labels match the consumer's choice.
- **A second person** to rate the same 50 quotes, so that the human ratings can be checked against each other. Ideally someone who did not build the system.
- **The mix of the two methods on a new month,** as an untouched test of the 0.9 rule.
