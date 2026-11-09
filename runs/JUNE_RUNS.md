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
| 2026-11-09 00:30 | synthetic | 0cc696205a81ce55bfe505f3ff83e2bf1e1e770ecad0167d63cf9fa027f89cbf | 6335e9b1d795628dcbb6da45ba76b577c1654f0b6bc83da206968e5146b3af67 | the dry run, round 1, on the jobs' IDs of #100 |
| 2026-11-09 10:45 | synthetic | 6d619f00843fa99fb098a08d7c142c7fdb415b77d3553c7858d71acde8fce412 | 0095cfc74d9b3ded993101653f8a4486d30385b604c420d9e973ba770a5c9f07 | the dry run, round 2, after the fixes of #102 |
