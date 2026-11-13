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
| 2026-11-09 22:24 | synthetic | 92c133d48483da34a499692d47e0aa8eedf31cbe687435a72c6870a9dd24fc94 | 634c46d3d006c201b98b7a5772fc3d38d8b2eb15621e55703a6e5439c8c866b6 | the dry run, round 3, after the fixes of #105 |
| 2026-11-10 23:25 | synthetic | 9d83ce9483a0bbc9f124724af11764296433ba41d1f41627628b2b003f3a3d06 | 1d89976747d3d57fb070d6cdb9d2a530c2c2a7e45aef2712f526c30ec700b291 | the dry run, round 4, on the code of 6b, after #119 |
| 2026-11-12 07:51 | synthetic | 973898f58fd9d38c566f0cd2ee20161646f0c227c6e76436ce8af9e7f0cbff3a | d8dd57560fc172b80f5c372ee653986d0892b7dd83f047fad27d44d50d9f1d15 | the dry run, round 5, on the refit's strict stopping point, after #122 |
| 2026-11-12 23:01 | synthetic | 74d8d5618301a677728154ee8136ef5868b8dcc90b3a986b22134147e67484b7 | e6a61fe3a42497198ff7e020aa351dfef17aba2b8302d26499e5b5bea8ad55f6 | the dry run, round 6, on the pinned vocabulary and the red run job, after #126 |
| 2026-11-13 11:40 | real | 4ae0c333e53479527a53d67711d53c81272a07c2bbcea28fc36d020b346477d0 | db063ac8f671e5fa4b3944adca2b25c3c9b605f6b444157f91102ff30c0d677a | the June run, on the code of #132, after both gates passed (#133) |
