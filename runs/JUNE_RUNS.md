# June runs

One row per scoring of spec 004's June sample (J1). Rows are only ever added. CI checks that this file only grows
compared with main. A row is added in its own pull request, after the last code change, and Job B runs the code
of the commit that merged it. Job B refuses to score unless a row names both hashes it is about to run.

- June list hash: the SHA-256 of `splits/june/june.csv`. Code hash: the frozen code's hash. `scripts/june_hash.py`
  prints both.
- Kind: `real` or `synthetic` for a list's first row (the dry run of pull request 9 is `synthetic`), then
  `reproduction` (the same recorded answers replayed), `resume` (after a stop by the spend limit or the quota)
  or `second` (a new run), each with its reason. Never a quiet rescoring.

| Date | Kind | June list hash | Code hash | Reason |
|---|---|---|---|---|
