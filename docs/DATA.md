# The data, in plain words

This page describes the July 2026 complaint file and the decisions based on it. Every number comes from one command:

```
uv run voc profile --write results/profile_july_2026.json
```

It ran on 28 October 2026 on the pinned file (`config/data_files.toml`), in about 2 seconds. It prints counts only, never complaint text. The full output is in [results/profile_july_2026.json](../results/profile_july_2026.json).

Status: **draft for the owner's review.** No sample is drawn until the owner has reviewed this page (B24, B25).

## What the file is

- **672,036 complaints**, all received between **1 and 31 July 2026**. Every date was read. No complaint ID appears twice.
- They are about **1,789 different companies**. This repo names no company.
- One industry: US consumer finance. Each complaint has a **Product**, a broad category the consumer chose when filing, such as "Credit card" or "Mortgage".
- The file name says 20 July 2026, but it holds complaints received up to 31 July. So the file was downloaded on or after 31 July. Its name is not its download date.

## Only a small part has text

Only **10,002 complaints (1.5 percent) have a narrative**, the consumer's own description. The LLM needs that text, so this project works only on those 10,002.

The mix of categories in that 1.5 percent is very different from the whole file:

| Category | All complaints | With text | Share of the text set |
|---|---|---|---|
| Debt collection | 24,649 | 2,727 | 27.3% |
| Checking or savings account | 7,963 | 2,025 | 20.2% |
| Credit card | 8,027 | 1,822 | 18.2% |
| Money transfer, virtual currency, or money service | 3,474 | 781 | 7.8% |
| Mortgage | 3,066 | 728 | 7.3% |
| Vehicle loan or lease | 2,158 | 509 | 5.1% |
| Credit reporting or other personal consumer reports | 618,208 | 463 | 4.6% |
| Payday loan, title loan, personal loan, or advance loan | 1,793 | 410 | 4.1% |
| Student loan | 1,787 | 310 | 3.1% |
| Prepaid card | 530 | 134 | 1.3% |
| Debt or credit management | 381 | 93 | 0.9% |

Credit reporting is **92 percent of all complaints but only 4.6 percent of those with text**. So every result in this project describes complaints that have text, not all complaints. The README says this. Why so few credit reporting complaints have text is not checked here.

## The text itself

- **Length.** The middle (median) narrative is between 711 and 1,640 characters, depending on the category. Mortgage complaints are the longest. 497 narratives are over 4,000 characters and are cut at that point, with each cut recorded (B9).
- **Redaction.** 8,301 narratives (83 percent) contain redaction marks such as "XXXX", where the CFPB removed names, dates or amounts. They stay exactly as written (B6).
- **Exact copies.** 623 narratives are exact copies of another one, after ignoring case and spacing. Copies are removed before sampling, so the same text cannot be in both the training and the test set (B9).

## The label set (B24)

- There are **11 categories**, and all of them come from the CFPB's current list (since 2023). The file covers one month, so no category was renamed, merged or retired inside it.
- Each category has between 2 and 11 sub-categories. They are counted as background only and are not labelled.
- Some categories overlap in ways a consumer could confuse. These are guesses from the category names, to check later in error analysis:
  - Debt collection and the loan categories (credit card, student loan, payday loan), when a collector chases a loan.
  - Credit reporting and debt collection, when a debt shows on a credit report.
  - Credit reporting and debt or credit management, when a credit repair service is involved.
  - Checking or savings account, money transfer and prepaid card, which all move money.

**Proposal:** use all 11 categories as they are, with no merging or mapping. They are frozen in `config/labels.toml` after the owner agrees.

## Sample sizes (B25)

The pool is the 10,002 narratives minus the 623 exact copies: **9,379 complaints**. Near-copies are removed later (T012), so the final pool may be slightly smaller, and the sizes are recomputed then.

Cochran's formula, with the correction for a pool of this size (see [How we measure](HOW_WE_MEASURE.md)):

| Set | Margin of error | Complaints |
|---|---|---|
| Development | 5 points | 370 |
| Test | 2 points (about 1.5 at 84 percent accuracy) | 1,912 |
| Training, for TF-IDF only | not sampled | the remaining 7,097 |

Split across categories in proportion to the text set:

| Category | Development | Test | Training |
|---|---|---|---|
| Debt collection | 101 | 521 | 2,105 |
| Checking or savings account | 75 | 387 | 1,563 |
| Credit card | 67 | 348 | 1,407 |
| Money transfer, virtual currency, or money service | 29 | 149 | 603 |
| Mortgage | 27 | 139 | 562 |
| Vehicle loan or lease | 19 | 97 | 393 |
| Credit reporting or other personal consumer reports | 17 | 89 | 357 |
| Payday loan, title loan, personal loan, or advance loan | 15 | 79 | 316 |
| Student loan | 12 | 59 | 239 |
| Prepaid card | 5 | 26 | 103 |
| Debt or credit management | 3 | 18 | 72 |

The training column is approximate, because exact copies are removed per category in T012.

**Two categories fall below 30 in the test set:** prepaid card (26) and debt or credit management (18). Their per-category scores are shown as "too few to judge". They still count in the overall score.

## For the owner to decide

1. Use all 11 categories as they are, with no merging?
2. Accept that prepaid card and debt or credit management are "too few to judge" in the per-category tables?
