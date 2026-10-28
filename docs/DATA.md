# The data, in plain words

This page describes the July 2026 complaint file and the decisions based on it. Every number comes from one command:

```
uv run voc profile --write results/profile_july_2026.json
```

It ran on 28 October 2026 on the pinned file (`config/data_files.toml`), in about 3 seconds. It prints counts only, never complaint text. The full output is in [results/profile_july_2026.json](../results/profile_july_2026.json).

This is a best-effort look at real data. Where data is missing or a question cannot be answered from the file, this page says so.

Status: **draft for the owner's review.** No sample is drawn until the owner has reviewed this page (B24, B25).

## What the file is

- **672,036 complaints**, all received between **1 and 31 July 2026**. Every date was read. No complaint ID is missing or appears twice.
- They are about **1,789 different companies**. This repo names no company.
- **Complaints only.** The CFPB calls it "a database of financial product and service complaints" ([its consumer complaint database page](https://www.consumerfinance.gov/data-research/consumer-complaints/), read 28 October 2026). There is no positive feedback.
- One industry: US consumer finance. Each complaint has a **Product**, a broad category the consumer chose when filing, such as "Credit card" or "Mortgage". We call it the category.
- The file name says 20 July 2026, but it holds complaints received up to 31 July. So the file was downloaded on or after 31 July. Its name is not its download date.

## What is missing

Fields that are empty for some complaints:

| Field | Empty | Share empty |
|---|---|---|
| Consumer complaint narrative (the text) | 662,034 | 98.5% |
| Tags (such as "Older American") | 657,955 | 97.9% |
| Company public response | 346,761 | 51.6% |
| Sub-issue | 7,198 | 1.1% |
| ZIP code | 705 | 0.1% |
| State | 619 | 0.1% |

Every other field is filled in for every complaint.

## Only a small part has text

Only **10,002 complaints (1.5 percent) have a narrative**, the consumer's own description. The LLM needs that text, so this project works only on those 10,002.

| Category | All complaints | With text | Share of all | Share of text set | Share of the category with text |
|---|---|---|---|---|---|
| Credit reporting or other personal consumer reports | 618,208 | 463 | 92.0% | 4.6% | 0.1% |
| Debt collection | 24,649 | 2,727 | 3.7% | 27.3% | 11.1% |
| Credit card | 8,027 | 1,822 | 1.2% | 18.2% | 22.7% |
| Checking or savings account | 7,963 | 2,025 | 1.2% | 20.2% | 25.4% |
| Money transfer, virtual currency, or money service | 3,474 | 781 | 0.5% | 7.8% | 22.5% |
| Mortgage | 3,066 | 728 | 0.5% | 7.3% | 23.7% |
| Vehicle loan or lease | 2,158 | 509 | 0.3% | 5.1% | 23.6% |
| Payday loan, title loan, personal loan, or advance loan | 1,793 | 410 | 0.3% | 4.1% | 22.9% |
| Student loan | 1,787 | 310 | 0.3% | 3.1% | 17.3% |
| Prepaid card | 530 | 134 | 0.1% | 1.3% | 25.3% |
| Debt or credit management | 381 | 93 | 0.1% | 0.9% | 24.4% |

**Does the text set represent all complaints? Overall, no.** We measure the gap between two mixes with one number, the difference: 0 percent means the same mix, 100 percent means no overlap at all. (Statisticians call it the total variation distance.)

- Between all complaints and the text set, the difference is **87 percent**. Credit reporting is 92 percent of all complaints, but only about 1 in 1,300 of them has text.
- Leaving credit reporting out, the difference falls to **17 percent**. Most categories have text for about 1 in 4 complaints. Debt collection is lower, at about 1 in 9.
- Why credit reporting complaints so rarely have text cannot be answered from this file.

## Within each category, do complaints with text look like the rest?

For each category, we compared the complaints with text against all complaints in that category, on six fields recorded for each complaint. An empty value is compared as its own group, which matters for Tags (97.9 percent empty). The numbers are the difference, from 0 (the same mix) to 1 (no overlap). Values seen fewer than 5 times are grouped together, which can only make a difference smaller, so these are lower bounds.

| Category | How submitted | Issue | Company response | On time | Tags | State |
|---|---|---|---|---|---|---|
| Checking or savings account | 0.10 | 0.04 | 0.11 | 0.00 | 0.03 | 0.06 |
| Credit card | 0.09 | 0.06 | 0.10 | 0.00 | 0.05 | 0.05 |
| Credit reporting or other personal consumer reports | 0.00 | 0.07 | 0.16 | 0.00 | 0.02 | 0.19 |
| Debt collection | 0.01 | 0.15 | 0.07 | 0.01 | 0.05 | 0.11 |
| Debt or credit management | 0.03 | 0.11 | 0.13 | 0.03 | 0.03 | 0.15 |
| Money transfer, virtual currency, or money service | 0.04 | 0.05 | 0.07 | 0.00 | 0.03 | 0.08 |
| Mortgage | 0.10 | 0.04 | 0.13 | 0.01 | 0.06 | 0.08 |
| Payday loan, title loan, personal loan, or advance loan | 0.06 | 0.09 | 0.06 | 0.01 | 0.04 | 0.11 |
| Prepaid card | 0.14 | 0.09 | 0.12 | 0.04 | 0.04 | 0.16 |
| Student loan | 0.02 | 0.08 | 0.18 | 0.18 | 0.05 | 0.13 |
| Vehicle loan or lease | 0.06 | 0.08 | 0.08 | 0.00 | 0.02 | 0.10 |

As a rough reading guide (our own, not a standard): under 0.05 is very similar, 0.05 to 0.15 shows some difference, and over 0.15 is a noticeable difference.

**What stands out:**

- **How submitted.** In every category, every complaint with text came through the web form. Of all complaints, between 85.8 percent (prepaid card) and 99.9 percent (credit reporting) did.
- **Company response.** Almost no complaint with text is still "in progress": 5 of 10,002. In credit reporting, 16.4 percent of all complaints are in progress, and none of those with text.
- **Issue, in debt collection.** "Took or threatened to take negative or legal action" is 22.4 percent of all debt collection complaints, but 7.1 percent of those with text. "Written notification about debt" is 17.0 percent of all, and 25.0 percent of those with text.
- **On time, in student loans.** The company answered late for 21.8 percent of all student loan complaints, but 40.0 percent of those with text.
- **State.** Some states are over- or under-represented. In credit reporting, Texas is 16.9 percent of all complaints and 27.0 percent of those with text.

**What this means for the project.** Within most categories, complaints with text are similar to the rest on most fields, but not the same. So our results describe **complaints that have text**: all sent through the web form, and almost all already answered by the company. They do not describe all complaints, and they say least about credit reporting. The README will say this (task T020).

## The text itself

- **Length.** The middle (median) narrative is between 711 and 1,640 characters, depending on the category. Mortgage complaints are the longest. 497 narratives are over 4,000 characters and are cut at that point, with each cut recorded (B9).
- **Redaction.** 8,297 narratives (83 percent) contain redaction marks such as "XXXX", where the CFPB removed names, dates or amounts. They stay exactly as written (B6).
- **Exact copies.** 623 narratives are exact copies of another one, after ignoring case and spacing. Most are in debt collection (469) and credit reporting (138). Copies are removed before sampling, keeping the one with the lowest complaint ID, so the same text cannot be in both the training and the test set (B9).

## The label set (B24)

- There are **11 categories**. They are exactly the 11 products in the CFPB's own list, "Consumer complaint form product and issue options", effective 24 August 2023 ([PDF](https://files.consumerfinance.gov/f/documents/cfpb_consumer_complaint_form_product_issue_options_August_2023_FINAL.pdf), read 28 October 2026). The file covers one month, so no category was renamed, merged or retired inside it. The CFPB says its lists changed in April 2017 and in 2023, so older files would need this check again.
- **The CFPB publishes no written definition of each category.** That document's "definitions" only explain its change markers. What it does give is the official list of sub-categories under each category. These lists are the label definitions this project uses, in `config/labels.toml`, copied word for word except one curly apostrophe written straight. The July file words three sub-products differently from the form (for example "CD (Certificate of Deposit)" for "CD"). The file notes them.
- Each category has between 2 and 11 sub-categories among complaints with text, not counting values too rare to show. They are counted as background only and are not labelled.
- Some categories overlap in ways a consumer could confuse. These are guesses from the category names, to check later in error analysis:
  - Debt collection and the loan categories (credit card, student loan, payday loan), when a collector chases a loan.
  - Credit reporting and debt collection, when a debt shows on a credit report.
  - Credit reporting and debt or credit management, when a credit repair service is involved.
  - Checking or savings account, money transfer and prepaid card, which all move money.

**Decided by the owner on 28 October:** all 11 categories are used as they are, with no merging or mapping. They are frozen in `config/labels.toml`.

## Sample sizes (B25)

The samples were drawn on 28 October with `uv run --native-tls voc sample` (about 5 seconds), from the July rows loaded with `uv run --native-tls voc load july_2026`. The settings are in `config/samples.toml` and the frozen lists in `splits/`.

- **Copies removed: 699.** `voc sample` prints 623 exact copies and 76 near-copies. The 623 match the profile's count of exact copies.
  - An exact copy has the same text as an earlier narrative, after ignoring case and spacing.
  - A near-copy opens with the same six words as a kept narrative, and the two texts overlap closely. We split each text into its runs of five words in a row. We count the runs both texts share, and divide by the runs found in either text. A near-copy scores at least 0.9 (statisticians call this the Jaccard similarity of word 5-grams).
  - The lowest complaint ID of each group is kept.
- **This copy test is strict.** Two changed words far apart in a 100-word text give about 0.81, so both texts are kept. A few close copies may therefore sit in both the training and the test set. That can only help TF-IDF, which learns from the training set. It cannot help the LLM, which learns nothing. So it does not flatter the LLM.
- **The pool: 9,303 complaints.**

Cochran's formula, with the correction for a pool of this size (see [How we measure](HOW_WE_MEASURE.md)):

| Set | Margin of error | Complaints |
|---|---|---|
| Development | 5 points at most | 370 |
| Test | 2 points at most (about 1.5 at 84 percent accuracy) | 1,909 |
| Training, for TF-IDF only | not sampled | the remaining 7,024 |

Split across categories in proportion to the pool:

| Category | Pool | Development | Test | Training |
|---|---|---|---|---|
| Debt collection | 2,204 | 88 | 452 | 1,664 |
| Checking or savings account | 2,025 | 81 | 416 | 1,528 |
| Credit card | 1,807 | 72 | 371 | 1,364 |
| Money transfer, virtual currency, or money service | 780 | 31 | 160 | 589 |
| Mortgage | 728 | 29 | 149 | 550 |
| Vehicle loan or lease | 508 | 20 | 104 | 384 |
| Payday loan, title loan, personal loan, or advance loan | 406 | 16 | 83 | 307 |
| Credit reporting or other personal consumer reports | 311 | 12 | 64 | 235 |
| Student loan | 309 | 12 | 63 | 234 |
| Prepaid card | 134 | 5 | 28 | 101 |
| Debt or credit management | 91 | 4 | 19 | 68 |
| **Total** | **9,303** | **370** | **1,909** | **7,024** |

**Small categories.**

- In the **test set**, two categories fall below 30: prepaid card (28) and debt or credit management (19). Their per-category scores are shown as "too few to judge". They still count in the overall score.
- In the **development set**, 7 of 11 categories are below 30. The development set is used to find error patterns, not to score categories, so no per-category score is reported from it.

## Decisions (owner, 28 October)

1. All 11 categories are used as they are, with no merging.
2. Prepaid card and debt or credit management are "too few to judge" in the per-category test tables, and the development set gives no per-category scores. Small categories are where the two methods differ most. TF-IDF learns only from examples, and prepaid card has about 100 in training. The LLM reads the category's official sub-category list and needs no examples (zero-shot). So small categories are a fair test of that difference, and the README will report it with its limits: few test complaints, and definitions that are lists, not prose.
