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

Both samples keep the same mix of categories as the whole data. If a category makes up 40 percent of all complaints, it makes up about 40 percent of each sample too. A category with fewer than 30 complaints in a sample is shown as "too few to judge", rather than given a shaky score.

## How we decide who wins

Suppose the LLM scores 84 percent and TF-IDF scores 81 percent. The LLM is 3 points ahead. Is that lead real, or luck in which complaints happened to be picked?

We answer this with a **paired bootstrap**. It works like re-running the exam many times with the questions we already have:

1. From the test complaints, draw a new set of the same size at random, allowing repeats. Some complaints appear twice, some not at all. The draw is made within each category, so every pretend set keeps the same mix of categories. This is one pretend test set.
2. Score both methods on that same pretend set, with all the same rules, and write down the gap between them.
3. Do this 2,000 times. Now we have 2,000 gaps.
4. Look at the middle 95 percent of those gaps. That is the likely range for the real gap.

"Paired" means both methods are always scored on the same pretend set, so neither gets easier questions.

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
