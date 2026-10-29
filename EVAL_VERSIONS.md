# Evaluation versions

One row per evaluation of a prompt version on the development set, written by `voc evaluate` (B15).
Rows are only ever added. These are tuning figures. The verdict comes only from the final test run.

- Accuracy is re-weighted strict accuracy (B10): quarantined labels count as wrong, and each category is
  weighted by its share of the pool.
- TF-IDF answers only its most confident complaints, as many as the LLM accepted. So its coverage equals
  the LLM's, and "TF-IDF quarantined" is the share it did not answer.
- Interval: the 95 percent interval of the LLM minus TF-IDF, in points, from the paired bootstrap.
- Quote length: accepted quotes, in characters, median and range.
- Live cost: what every answer cost when it was first made. Replay cost: what the labelling run paid, with
  recorded answers free.
- No table row says one version beats another. That needs a paired test, which is cut (B15).

| Date | Prompt | What changed | Set | List hash | Backend | Model | Effort | Complaints | LLM accuracy | LLM coverage | LLM quarantined | TF-IDF accuracy | TF-IDF coverage | TF-IDF quarantined | Interval | Quote length | Live cost | Replay cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-29 11:44 | v1 | first version | dev | 628e76005de8e73006b84ae84bb316483ed0225895af0457c6896bd3899301b9 | api | claude-haiku-5-5 | low | 370 | 79.8% | 97.6% | 2.4% | 79.1% | 97.6% | 2.4% | -3.1 to +4.7 points | median 68 (25 to 174) | $0.0862902 | $0.0718306 |
