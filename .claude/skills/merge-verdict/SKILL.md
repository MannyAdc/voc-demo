---
name: "merge-verdict"
description: "Check one pull request, or several parallel ones that share no file, before marking it ready, and give a one-line MERGE or FIX FIRST verdict. The owner still merges."
argument-hint: "One or more pull request numbers, for example: 29, or 29 30 for parallel branches"
user-invocable: true
disable-model-invocation: false
---

# /merge-verdict

Runs before Claude marks a pull request ready, on every pull request from T007 on (T006b). A script runs
the mechanical checks. Claude judges the rest and gives the verdict. The verdict is a recommendation. The
owner still decides and merges.

## Steps

1. Run, from the repo root:

   ```
   uv run --native-tls python scripts/merge_verdict.py <N> [<M> ...]
   ```

   For parallel branches, add `--test-merge`. It fetches the latest base and each head, merges them in a
   temporary tree with no commit and no hook, and runs the full test suite there. It takes several
   minutes. It uses this checkout's packages, so a change to the dependencies is not covered. Its tests
   run with the mock backend, and with no variable whose name holds KEY, TOKEN or SECRET and no data
   folder variable. It refuses a pull request from a fork without fetching anything.

   Several numbers together are only for pull requests that share no file. The script fails any file two
   of them change, with or without `--test-merge`. Pull requests that change the same file, such as
   `BUILD_LOG.md`, are checked one at a time, as in step 6.

2. Read each line. PASS and FAIL are mechanical. FOR CLAUDE is a judgement the script cannot make. The
   last line and the exit code give the script's result:
   - `MERGE` (exit 0): every check passed.
   - `FIX FIRST: <reasons>` (exit 1): at least one check failed.
   - `PENDING: Claude must judge: <items>` (exit 3): nothing failed, but the FOR CLAUDE items are open.
     This is not a MERGE. It is the usual result, because the review and the build log are always
     FOR CLAUDE.
   - Exit 2: the data could not be read, or the script crashed (printed as the error type only). Report
     that and stop.

3. Judge each FOR CLAUDE item:
   - Review findings: read the `## Reviewer findings` comment and the owner's choices in `BUILD_LOG.md`.
     Check in the diff that each finding the owner chose is fixed. Check that each other finding is
     deferred with a reason, in Known limits, the test list or the build log. This holds even when the
     comment says it found nothing.
   - Build log: check `BUILD_LOG.md` has the work start, the findings, the owner's choices and every AI
     mistake for this pull request.
   - No conflicts, when GitHub has not worked it out yet: run the script again.
   - Tests on the merge, when not run: run again with `--test-merge`.

4. Write one line in the chat:
   - `MERGE: <reason>` when the script said MERGE, or said PENDING and Claude has checked that every
     FOR CLAUDE item holds. For parallel branches, add the merge order the script printed.
   - `FIX FIRST: <reason>` otherwise, and always after a script FIX FIRST. Give it to the owner with its
     reason. Do not mark the pull request ready.

5. Only after a MERGE verdict, and just before marking it ready, run `gh pr view <N> --json mergeable`.
   Go on only when it says MERGEABLE. On UNKNOWN, GitHub has not worked it out yet: read it again a
   few minutes later, and after three reads tell the owner. On CONFLICTING, the verdict no longer
   holds: merge `main` in as step 6 says, and start again at step 1. Then run `gh pr ready <N>` and
   write "PR #N is ready to merge." in the chat.

6. When other open pull requests change the same file as this one:
   - Mark ready and name only one of them at a time, the lowest number first, as the script orders
     them.
   - If one already marked ready turns CONFLICTING, first mark it a draft again
     (`gh pr ready <N> --undo`).
   - After each merge to `main`, merge `main` into each other open pull request that changes that
     file. Each is a normal merge commit. Keep every `BUILD_LOG.md` section word for word, in merge
     order.
   - Log each merge commit, its conflicts and the suite result in `BUILD_LOG.md`. A conflict resolved
     in any file other than `BUILD_LOG.md` gets a fresh review of the merge.
   - Then run this skill on each of them alone, from step 1. A FIX FIRST goes to the owner, and the
     next one may go ahead.

## Never

- Never merge, push to `main` or change repo settings. The owner merges, with a normal merge commit.
- Never call a FOR CLAUDE item a pass without checking it.
- Never print commit messages or comment text from the script's data. The script prints only check
  names, statuses, short commit IDs, file paths and counts.
