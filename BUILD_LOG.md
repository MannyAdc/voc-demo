# Build log

Entries are added as things happen. Times are local (AEDT, UTC+11). Nothing here is tidied or written after the fact.

Sections used in entries: Work (start, merged, duration), AI error (what, how caught), Overruled (what, why), Parallel (what ran, result), Decision.

## Tuesday 27 October 2026

- 23:57 Work: planning session started. Read the earlier abandoned start (reference only, not copied). It has 10 behaviour rules (B1 to B10), 75 test cases in 8 files, and stub modules with no implementation. It was never committed.
- 23:58 Decision (fact check): the CFPB field reference says Product is "The type of product the consumer identified in the complaint". Issue is "The issue the consumer identified in the complaint". So the consumer sets these labels, not the CFPB. The labels are noisy and the README must say so. Source: https://cfpb.github.io/api/ccdb/fields.html (read 27 Oct 2026).

## Wednesday 28 October 2026

- 00:06 Decision: the test gate lets through a commit that changes only test files. Any commit that touches other files must pass the tests. Reason: the tests-first rule needs a red commit, and the gate would otherwise block it. (Owner chose the recommended option.)
- 00:06 Decision: evaluation reports two views, "quote check only" and "quote check plus baseline agreement". Reason: with the agreement rule alone, the LLM can never be right where TF-IDF is wrong, so it can never show a win there. (Owner chose the recommended option.)
- 00:06 Decision: Claude may run `gh pr create` and `gh pr comment`. The owner pushes branches and merges.
- 00:06 Decision: commits use the GitHub username and the GitHub noreply email, set for this repo only.
- 00:06 Decision: internal deadline is Friday 30 October 2026, 12:00 AEDT.
- 00:06 Decision: repo name `voc-demo`.
- 00:06 Decision: stack confirmed. Python 3.13, uv, pytest, DuckDB, dbt-duckdb, scikit-learn, Anthropic Python SDK, FastAPI, Pydantic, React, Vite, TypeScript, Playwright, GitHub Actions, gitleaks. Versions to be checked before pinning.
- 00:07 Work: Spec Kit trial started. Time box 30 minutes, ends 00:37.
- 00:08 Spec Kit v1.2.3 installed from the official repo tag. The first install failed with a certificate error (`invalid peer certificate: UnknownIssuer`). It worked with `uv tool install --native-tls`. Project uv commands may need the same flag on this machine.
- 00:09 `specify init --here --force --non-interactive --integration claude --script ps` worked. It added 10 skills in `.claude/skills/speckit-*` and a `.specify/` folder. No git extension, so it creates no branches.
- 00:12 Decision: keep Spec Kit. Constitution, spec, plan, research and tasks were written in about 5 minutes and nothing fought our conventions. Notes: the new skills do not load into a session that is already running, so Claude followed each `SKILL.md` by hand. The spec uses rule IDs B1 to B15 instead of the template's FR numbers, so tests can keep the `test_B<number>` names. The plan's optional files (data model, contracts, quickstart) were skipped for now.
- 00:12 Reused from the earlier start: rules B1 to B10 (rewritten, without its notes on names and origins) and its test ideas. B2 changed: the quote-only view is now always reported beside the agreement view. New rules: B11 to B15.
- 00:13 Fact check: the README quotes on the CFPB data were checked on the CFPB page. The real sentence is longer than the one in the brief ("This database is not a statistical sample of consumers' experiences in the marketplace"). The README uses the full sentence.
- 00:14 Work: first commit `4126874` on `main` (plan, conventions, build log, Spec Kit files). Planning took 23:57 to 00:14, 17 minutes. The test list and spec went in marked "draft". The owner's approval or changes will come in the first pull request.
- 00:15 AI error: Claude made the first commit without the `Co-Authored-By` line that marks AI help. Caught by Claude when checking the commit right after. Not fixed by amending, so history stays as it happened. From now on every commit gets the line, and `CLAUDE.md` will say so.
