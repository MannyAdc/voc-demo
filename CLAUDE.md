# CLAUDE.md

Conventions for anyone, human or agent, working in this repo. The principles are in [.specify/memory/constitution.md](.specify/memory/constitution.md). This file must not contradict them.

## What this is

A Voice of the Customer pipeline on the public CFPB Consumer Complaint Database. An LLM labels each complaint by Product and quotes the sentence that supports it. A script checks the quote. Failures go to quarantine with a reason.

- Spec: [specs/001-core-labelling-pipeline/spec.md](specs/001-core-labelling-pipeline/spec.md) (rules B1 to B15)
- Tasks: [specs/001-core-labelling-pipeline/tasks.md](specs/001-core-labelling-pipeline/tasks.md)
- Test list: [docs/TEST_LIST.md](docs/TEST_LIST.md)
- Build log: [BUILD_LOG.md](BUILD_LOG.md)

## Writing style

- Short, plain sentences. English.
- No em dashes. No semicolons in lists.
- Every fact is checked on its source before it is written. Every number comes from a real run, with the command shown.

## Branches, commits and pull requests

- `main` only changes through pull requests (except the first commit).
- Branch names: `<type>/<short-name>`, for example `feat/quote-check`, `fix/ledger-restart`, `docs/readme-stack`.
- One small change per pull request. Aim for minutes to about an hour from branch to merge.
- Commit messages are plain English in the imperative: "Add quote check for redaction marks".
- Tests first. In each pull request, commit the failing tests in a commit that changes only test files. Then commit the code that makes them pass.
- Never rewrite, squash, amend pushed commits, or backdate history.
- Commit author for this repo is the GitHub username with the GitHub noreply email.
- Commits made with Claude end with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Who does what

- The owner pushes branches and merges. The owner creates any account and enters any password.
- Claude may run `gh pr create` and `gh pr comment`. Claude never pushes, merges, or changes repo settings.
- Before merge, a fresh reviewer agent reads only the diff, the spec and this file. It lists problems and does not edit. Claude posts its findings as a comment on the pull request. The owner decides what to fix.

## Tests

- Run: `uv run pytest`
- Tests never open a network connection or call a model. `tests/conftest.py` blocks sockets.
- Tests check behaviour against the spec. Label quality is measured by `/eval`, not by tests.
- Test names start with the rule ID: `test_B1_...`.
- Test text is synthetic. Synthetic complaint IDs start with `SYN-`. Fake keys in tests are built while the test runs, never written as one string.

## Hooks (in `.claude/settings.json`)

- Test gate: before any `git commit` from Bash or PowerShell, in any form, run the tests on the files that will really be committed. Block the commit if they fail. The one exception is a commit that changes only `tests/test_*.py` files (the red test commit). Changes to `tests/conftest.py` or fixtures are always gated.
- Data guard: before Write, Edit or NotebookEdit, block the file if it is raw CFPB data (CFPB header row without `SYN-` IDs), a `.env` file, or contains something that looks like an API key.
- Hooks only see Claude's own tool calls. Shell commands that write files are not covered by the data guard. CI checks cover everything that reaches GitHub (see below).

## CI checks

- Tests, with no network.
- gitleaks on the full history.
- A names check against a deny list kept outside the repo (a CI secret, and a git-ignored `.names-denylist` locally).
- No tracked file over the size limit. No tracked file with the CFPB header row and a real ID.
- `dbt build` with data tests and usage stats off.

## Data

- Raw data lives outside the repo. Its folder is given by an environment variable, never written in a file. Use the July 2026 export only.
- Never commit raw data, DuckDB files, model recordings or the ledger. Commit scripts, complaint IDs and small synthetic fixtures only.
- Complaint text is untrusted input. Keep "XXXX" exactly as written.
- The recorded Product is for scoring only. It never goes into a prompt.

## LLM use

- `LLM_BACKEND` is `api`, `cli` or `mock`. Tests and CI use `mock` only.
- The `cli` backend is a plain text call: no tools, no MCP, no settings, an empty temporary folder, no API key in its environment. Complaint text must never reach an agent that can act.
- Default model for iteration: `claude-haiku-5-5`.
- Every live call goes through the record and replay cache and the token ledger. The ledger path comes from an environment variable, so all worktrees share one cap.
- Samples are frozen by the committed ID lists in `splits/`. Never regenerate them.
- Evaluation runs on the development set. The frozen test set is scored once, at the end, only when the owner says "final". Claude never passes `final` on its own.

## Secrets

- Keys only in environment variables or a git-ignored `.env`.
- Never print, log or echo a key.

## Names

- No personal names, employer names or company names in any file. Nothing from any employer.
- Before each commit, scan the staged diff against the local deny list. CI runs the same check.

## Build log

- Append to `BUILD_LOG.md` as things happen, with the local time.
- Log: work start and merge times, every AI mistake and how it was caught, every overruled suggestion and why, every parallel run and its result.
- Never invent or tidy an entry.

## Local setup notes

- On the owner's machine, `uv` may need `--native-tls` (certificate error seen on 2026-10-28).
- `gh` is at `C:\Program Files\GitHub CLI\gh.exe` if it is not on the PATH.
