# How we measure, in plain words

This page explains how the project decides whether the LLM is better than a simple classifier. No statistics background is needed. The exact rules are in the spec (B10 and B25).

## What we compare

Two methods label the same complaints with a product category, such as "credit card" or "mortgage":

- **The LLM** reads the complaint and picks a category. It must also quote the sentence that supports its choice. A script checks the quote is really in the complaint. If it is not, the label goes to quarantine and counts as wrong.
- **TF-IDF** is a simple, fast and cheap classifier. It learns which words go with which category from thousands of past complaints.

Neither method sees the other's answer. Each answer is checked against the category the consumer chose when filing the complaint. That recorded category is the answer key.

The consumer picked the category, so the answer key is not perfect. Some "mistakes" will really be the consumer's choice, not the method's. This affects both methods equally.

## How many complaints we check

We cannot check every complaint by hand, and we do not need to. A well-chosen sample tells us almost as much. We use **Cochran's formula**, a standard way to size a sample.

The idea: the more complaints we check, the more precise the score. But each extra complaint helps less than the one before.

| Complaints checked | The score is accurate to within |
|---|---|
| 385 | about 5 points either way |
| 1,068 | about 3 points either way |
| 2,401 | about 2 points either way |

"Within 2 points" means that if the LLM scores 84 percent, its true score is very likely between 82 and 86 percent. "Very likely" here means 95 times out of 100.

We use two samples:

- **Development set, about 385 complaints.** We use it to find mistakes and improve the LLM's instructions. About 5 points of precision is enough for that.
- **Test set, about 2,400 complaints.** It is put aside at the start, used once at the very end, and never used for tuning. This gives a fair final score, accurate to about 2 points.

Both samples keep the same mix of categories as the whole data. If 40 percent of all complaints are about credit reporting, about 40 percent of each sample is too. A category with fewer than 30 complaints in a sample is shown as "too few to judge", rather than given a shaky score.

## How we decide who wins

Suppose the LLM scores 84 percent and TF-IDF scores 81 percent. The LLM is 3 points ahead. Is that lead real, or luck in which complaints happened to be picked?

We answer this with a **paired bootstrap**. It works like re-running the exam many times with the questions we already have:

1. From the 2,400 test complaints, draw 2,400 at random, allowing repeats. Some complaints appear twice, some not at all. This is one pretend test set.
2. Score both methods on that same pretend set, with all the same rules, and write down the gap between them.
3. Do this 2,000 times. Now we have 2,000 gaps.
4. Look at the middle 95 percent of those gaps. That is the likely range for the real gap.

"Paired" means both methods are always scored on the same pretend set, so neither gets easier questions.

The verdict follows from that range:

| The range of the gap | Verdict |
|---|---|
| Entirely above zero, for example +1 to +5 points | The LLM **beats** TF-IDF |
| Includes zero, for example −1 to +6 points | **Inconclusive**: we cannot be sure |
| Otherwise | The LLM **does not beat** TF-IDF |

This needs no extra LLM calls. It reuses the labels we already have and runs in seconds on a laptop.

## One more fairness rule

The LLM sometimes sends a complaint to quarantine instead of answering. To keep the contest fair, TF-IDF answers the same number of complaints: the ones it is most sure about. So neither method can look better just by skipping the hard cases.

## What the result can and cannot tell you

- It tells you which method labels this data more accurately, and how sure we are.
- It also shows the cost and speed of each method, so you can judge whether the LLM's extra cost is worth it.
- It does not tell you about other data, other months or other industries.
- The CFPB says its database "is not a statistical sample of consumers' experiences in the marketplace". So the results describe this data, not all consumers.
- The rule for winning was written down before the first run, and the test set is used only once. So the result cannot be tuned after the fact.
