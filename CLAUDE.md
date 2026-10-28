# CLAUDE.md

Conventions for anyone, human or agent, working in this repo. The principles are in [.specify/memory/constitution.md](.specify/memory/constitution.md). This file must not contradict them.

## What this is

A Voice of the Customer pipeline on the public CFPB Consumer Complaint Database. An LLM labels each complaint by Product and quotes the sentence that supports it. A script checks the quote. Failures go to quarantine with a reason.

- Spec: [specs/001-core-labelling-pipeline/spec.md](specs/001-core-labelling-pipeline/spec.md) (rules B1 to B23, and a threat model)
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

- Claude may push feature branches, run `gh pr create` and `gh pr comment`. Claude never pushes to `main`, never pushes with force, never deletes a branch, never merges, and never changes repo settings. Pushing is proposing. Merging is deciding.
- Deny rules in `.claude/settings.json` block force pushes, pushes to `main`, branch deletion and `gh pr merge`, from Bash and PowerShell. They match command text only, so they are best effort.
- Every pull request is opened as a draft, so GitHub cannot merge it yet. Claude marks it ready only after the reviewer agent's findings are posted and the owner has decided what to fix. Claude then writes "PR #N is ready to merge." in the chat. Without those words, the owner waits.
- From T007 on, Claude runs `/merge-verdict` before marking a pull request ready. "PR #N is ready to merge." is written only after a MERGE verdict. A FIX FIRST verdict goes to the owner with its reason. The verdict is a recommendation. The owner still decides and merges.
- The owner merges, using a normal merge commit (not squash or rebase). The owner creates any account and enters any password.
- Until the repo is public, GitHub cannot block a merge when CI fails (protected branches need a paid plan on private repos). So the owner checks that CI is green before merging.
- Before merge, a fresh reviewer agent reads only the diff, the spec and this file. It lists problems and does not edit. Claude posts its findings as a comment on the pull request. The owner decides what to fix.

## Tests

- Run: `uv run pytest`
- Tests never open a network connection or call a model. `tests/conftest.py` blocks sockets.
- Tests check behaviour against the spec. Label quality is measured by `/eval`, not by tests.
- Test names start with the rule ID: `test_B1_...`.
- Test text is synthetic. Synthetic complaint IDs start with `SYN-`. Fake keys in tests are built while the test runs, never written as one string.

## Hooks (in `.claude/settings.json`)

- Setup, once per clone, by the owner: install gitleaks (`winget install --id Gitleaks.Gitleaks --exact --version 8.30.1` on Windows), run `uv sync`, then `git config core.hooksPath .githooks`.
- Test gate: the git pre-commit hook (`.githooks/pre-commit`, which runs `.claude/hooks/test_gate.py`) runs gitleaks on the staged changes, the names check on the staged files, and the tests on the staged tree. Git builds that tree for every `git commit` form, so the tests run on exactly the files that will be committed, from Claude or from the owner's terminal. `.githooks/pre-merge-commit` runs the same gate for merge commits. `cherry-pick`, `revert` and `commit-tree` run no pre-commit hook (see Known limits in the spec). It fails if gitleaks or the deny list is missing. The one exception to "all tests pass" is a commit that changes only `tests/test_*.py` files and where every failing test is new or was already failing before it (the red test commits). Such a commit may not delete a test or stop an existing test passing. Each already failing test it carries over is printed as a notice, logged in `BUILD_LOG.md`, and checked by the reviewer for weakening. This allowance is reviewed at the Thursday 12:00 checkpoint. Changes to `tests/conftest.py` or fixtures are always gated.
- The Claude side of the test gate blocks ways around the git hook: `--no-verify`, `commit -n`, and any command that names `core.hooksPath`. It refuses every commit while the git hook is not installed. "Installed" means the hook setting is `.githooks`, or the full path to `.githooks` in this checkout or the main checkout, where `.githooks/pre-commit` exists. Any other value counts as not installed. (Claude Code's worktree feature was seen to write the full path.)
- Data guard: before Write, Edit, MultiEdit or NotebookEdit, block the file if it is raw CFPB data (CFPB header row without `SYN-` IDs, checked on the file as it would be after the edit), a `.env` file, or contains something that looks like an Anthropic key. `.env.example` is allowed if it holds no key-like value. Edits to `.claude/settings.json`, `.claude/settings.local.json`, `.claude/hooks/`, `.githooks/`, `src/voc/repo_checks.py` (which the guards import) and the user-level Claude settings ask the owner first. The check for a long run of text copied from a sampled narrative was cut on 28 October (cut list item 4) and is in Known limits.
- Read guard: block Claude from reading the raw data folder (`VOC_DATA_DIR`), the home folder `.voc` (ledger and recordings), any `.duckdb` file, a `recordings` folder, a CFPB export file and the `.env` file, with any tool. Every path-like string in a tool's input is checked after `..` is resolved, and a search of a folder that holds the data folder or `.voc` is blocked too. Any tool input with a `command` (Bash, PowerShell, Monitor) is checked as a shell command, including commands that name the places in Windows or Git Bash form. Block Claude from running `show` or `dbt show` at all (`git show` is allowed). Ask the owner before Claude runs any command containing the word `final`.
- Every Claude hook runs through `.claude/hooks/run.sh` and fails closed: a crash, bad input or a missing Python blocks the action (`onFailure: "block"`, plus exit code 2 for older Claude Code versions).
- Hooks only see Claude's own tool calls, and they parse command text, so they are best effort. Shell commands that write files are not covered by the data guard. The real gate is CI, plus branch protection with required checks on `main` once the repo is public.

## CI checks

- Tests, with no network.
- gitleaks on the full history.
- A names check against a deny list kept outside the repo (a CI secret, and a git-ignored `.names-denylist` locally). It fails if the list is missing or empty.
- `runs/TEST_RUNS.md` only grows compared with `main`.
- No tracked file over the size limit. No tracked file with the CFPB header row and a real ID.
- `dbt build` with data tests and usage stats off.

## Data

- Raw data lives outside the repo. Its folders are given by environment variables (`VOC_DATA_DIR` for July, `VOC_NEXT_DATA_DIR` for August), never written in a file. July is used for labelling and evaluation. August is used only to show the incremental load.
- Sample sizes come from Cochran's formula (B25). The winner is judged by the paired bootstrap (B10). `docs/HOW_WE_MEASURE.md` explains both in plain words.
- Never commit raw data, DuckDB files, model recordings or the ledger. Commit scripts, complaint IDs, small synthetic fixtures and results files (B19) only. A results file holds IDs, labels, positions, reasons and counts, never complaint text.
- Complaint text is untrusted input. Keep "XXXX" exactly as written.
- The recorded Product is for scoring only. It never goes into a prompt.

## LLM use

- `LLM_BACKEND` is `api` or `mock`. Tests and CI use `mock` only.
- There is no `cli` backend (cut on 28 October). Complaint text must never reach an agent that can act, and `claude -p` is one.
- The LLM is not trained. Prompt versions are judged on the development set. Sample sizes and the label set come from `docs/DATA.md` (B24, B25).
- Default model for iteration: `claude-haiku-5-5`.
- Every live call goes through the record and replay cache and the token ledger. The ledger lives at one fixed path in the home folder, so all worktrees share one cap. The cap can only be lowered by an override.
- Samples are frozen by the committed ID and content-hash lists in `splits/`. Never regenerate them.
- Claude never prints or reads narrative text, quotes or raw model answers from real data. Commands print only IDs, labels, reasons, positions and counts.
- Error analysis runs through the analyser (a tool-less model call that answers with one cause from a fixed list). Claude sees only the causes and counts. The owner spot-checks 10 per round with `show` in the owner's own terminal. Claude never runs `show`. Notes hold IDs and short descriptions, never copied text.
- Evaluation runs on the development set. The frozen test set is scored once, at the end, only when the owner says "final". Claude never passes `final` on its own.

## Secrets

- Keys only in environment variables or a git-ignored `.env`, which the command line loads at start-up.
- Never print, log or echo a key.
- If a key leaks: rotate it at once. If a name leaks: tell the owner. Removing a leak from history is the only allowed rewrite, only before the repo is public, only by the owner's decision, and logged with its reason.

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
