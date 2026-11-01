# How we measure, in plain words

This page explains how the project decides whether the LLM is better than a simple classifier. No statistics background is needed. The exact rules are in the spec (B10 and B25).

## What we compare

Two methods label the same complaints with a product category, such as "credit card" or "mortgage":

- **The LLM** reads the complaint and picks a category. It must also quote the sentence that supports its choice. A script then checks that the quote is really in the complaint. If it is not, the script puts the label in quarantine, and it counts as wrong.
- **TF-IDF** is a simple, fast and cheap classifier. It learns which words go with which category from thousands of other complaints in the same data. Those complaints are kept apart from the ones we score.

Neither method sees the other's answer. Each answer is checked against the category the consumer chose when filing the complaint. That recorded category is the answer key.

The consumer picked the category, so the answer key is not perfect. Some "mistakes" will really be the consumer's choice, not the method's. This affects both methods, but not always equally. TF-IDF learns from the same consumer choices, so it can pick up their habits.

## How many complaints we score

Scoring is automatic, but every LLM answer costs money and time. So we score a sample, not every complaint. A well-chosen sample tells us almost as much. We use **Cochran's formula**, a standard way to size a sample.

The idea: the more complaints we score, the more precise the result. But each extra complaint helps less than the one before.

| Complaints scored | The score is accurate to within, at most |
|---|---|
| 385 | about 5 points either way |
| 1,068 | about 3 points either way |
| 2,401 | about 2 points either way |

These are worst-case figures. For a method that scores about 84 percent, 2,401 complaints give about 1.5 points either way.

"Within 2 points" means this. If the LLM scores 84 percent on the sample, its score on the whole set of complaints is very likely between 82 and 86 percent. "Very likely" here means 95 times out of 100.

We use two samples:

- **Development set, about 385 complaints.** We use it to find mistakes and improve the LLM's instructions. About 5 points of precision is enough for that.
- **Test set, about 2,400 complaints.** It is put aside at the start, used once at the very end, and never used for tuning. This gives a fair final score, accurate to about 2 points at most.

These are the sizes before one correction. The pool holds only 9,303 complaints, and a sample that takes a large part of a small pool needs fewer complaints for the same precision. With that correction, the real sizes are 370 and 1,909 ([DATA.md](DATA.md), "Sample sizes").

Both samples keep the same mix of categories as the whole data. If a category makes up 40 percent of all complaints, it makes up about 40 percent of each sample too. A category with fewer than 30 complaints in a sample is shown as "too few to judge", rather than given a shaky score.

## Small categories: labelled, but not measured

Classifying and measuring are two different things.

- **Classifying** is what each method does to one complaint: it picks a category. TF-IDF does this for every complaint, in every category, however small. The LLM does it for almost every complaint. In the test run it gave no usable category for 21 of the 1,909: 15 times a category not in the list, and 6 times an answer that could not be read. It accepted the label "prepaid card" 24 times and "debt or credit management" 15 times (`results/labels/v1_test.json`).
- **Measuring** is how we find out how often those labels are right. That needs enough complaints of each category with a known answer. With 28 prepaid card complaints in the test set, each one is 3.6 percent of them, so one more right or wrong answer moves their accuracy by 3.6 points. The likely range is wide. By the same formula as above, a score of 80 percent on 28 complaints could really be anywhere from about 65 to 95 percent.

So the small categories are labelled like the others, and they count in the overall score. We just cannot say how good the labels are for each of them on its own.

Could we have taken more of them into the test set? Yes, a few. 2 more prepaid card and 11 more debt or credit management complaints would have reached the bar of 30. That was not done, for two reasons:

- 30 is only the floor below which we give no score at all. At 30, for a score of 80 percent, the likely range is still about 14 points either way.
- Every one taken for testing is one fewer for TF-IDF to learn from, and TF-IDF learns only from examples. The whole pool has only 134 prepaid card and 91 debt or credit management complaints. Taking many more would leave TF-IDF few or none, which would make the contest unfair to it in exactly these categories.

The overall score is **re-weighted**: each category counts in proportion to its share of the whole pool, not its share of the sample. So taking extra complaints of one category would not give it extra weight in the overall score. But re-weighting cannot give TF-IDF back the training examples it lost. So over-sampling would still tilt the result slightly against TF-IDF. The samples were drawn in proportion and frozen before the first run, as [DATA.md](DATA.md) records.

A fair measurement of the small categories needs more data, for example several months of complaints, not a bigger slice of one month.

## How we decide who wins

Suppose the LLM scores 84 percent and TF-IDF scores 81 percent. The LLM is 3 points ahead. Is that lead real, or luck in which complaints happened to be picked?

We answer this with a **paired bootstrap**. It works like re-running the exam many times with the questions we already have. By then, both methods have already labelled every test complaint once. So for each complaint and each method there is one fact: right or wrong.

1. **One pick.** Take 1 complaint at random from one category of the test complaints, and put it back. So the same complaint can be picked again.
2. **One draw.** Make as many picks in each category as it has complaints, for example 452 picks from the 452 debt collection complaints. That is 1,909 picks in all: one pretend test set, the same size and the same mix of categories as the real one. Because each pick is put back, a draw is not the real set again. On average about 63 percent of the complaints appear in it, some of them twice or more, and about 37 percent do not appear at all.
3. **Score the draw.** Score both methods with the same rules as the real test. A complaint picked twice counts twice.
   - The LLM: a quarantined label counts as wrong.
   - TF-IDF: it answers only as many picks as the LLM accepted in this draw, its most confident ones. The picks it skips count as wrong. This is chosen again in every draw (see "One more fairness rule" below).
   - For each category, take the share of its picks that are right. Then combine the categories, each weighted by its share of the 9,303 complaints in the pool. Because the test set was drawn in proportion to the pool, this is very close to "right picks ÷ 1,909".
   - Write down the gap: the LLM's score minus TF-IDF's score, in percentage points.
4. **Repeat.** Make 2,000 draws. Now there are 2,000 gaps.
5. **The 95 percent range.** Sort the 2,000 gaps from smallest to largest. Drop about the smallest 50 and the largest 50, which is 2.5 percent at each end. The smallest and largest gaps left are the ends of the range. On the test set, they were +0.5 and +4.1 points.

A small, simplified example: 5 complaints, A to E, all in one category, with nothing quarantined and nothing skipped. The LLM got A, B, C and D right. TF-IDF got A, B, C and E right.

| Set | Complaints in it | LLM right | TF-IDF right | Gap |
|---|---|---|---|---|
| The real set | A, B, C, D, E | 4 of 5 (80%) | 4 of 5 (80%) | 0 points |
| Draw 1 | A, A, D, D, B | 5 of 5 (100%) | 3 of 5 (60%) | +40 points |
| Draw 2 | E, E, C, A, E | 2 of 5 (40%) | 5 of 5 (100%) | −60 points |
| Draw 3 | B, D, C, C, A | 5 of 5 (100%) | 4 of 5 (80%) | +20 points |

With only 5 complaints the gap swings wildly. With 1,909 it moves much less.

Each draw counts some complaints twice and leaves others out, so the gap moves. How far it moves over 2,000 draws shows how much the result depends on which complaints happened to be in the test.

"Paired" means both methods are always scored on the same draw, so neither gets easier questions.

The draws only re-count answers that already exist. No model runs again, nothing is trained, and no test complaint is sent anywhere. The code is `compare` in `src/voc/metrics.py`: 2,000 draws, seed 0, and the range is the 2.5th and 97.5th percentile of the gaps.

The verdict follows from that range:

| The LLM's lead, and its range | Verdict |
|---|---|
| The whole range is above zero, for example +1 to +5 points | The LLM **beats** TF-IDF |
| The LLM is ahead, but the range includes zero, for example +2 points with a range of −1 to +5 | **Inconclusive**: the lead could be luck |
| The LLM is level or behind | The LLM **does not beat** TF-IDF |

This needs no extra LLM calls. It reuses the labels we already have.

## One more fairness rule

The quote check sometimes sends an LLM label to quarantine. Quarantined labels count as wrong. To keep the contest fair, TF-IDF answers the same number of complaints: the ones it is most sure about. The complaints it skips count as wrong too. So neither method can look better just by skipping the hard cases.

## What the result can and cannot tell you

- It tells you which method labels this data more accurately, and how sure we are.
- It also shows the cost and speed of each method, so you can judge whether the LLM's extra cost is worth it.
- It does not tell you about other data, other months or other industries.
- The CFPB says its database "is not a statistical sample of consumers' experiences in the marketplace". So the results describe this data, not all consumers.
- The rule for winning was written down before the first run, and the test set is used only once. So the result cannot be tuned after the fact.
