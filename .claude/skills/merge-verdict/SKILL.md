---
name: "merge-verdict"
description: "Check one pull request, or several parallel ones, before marking it ready, and give a one-line MERGE or FIX FIRST verdict. The owner still merges."
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
   minutes. It uses this checkout's packages, so a change to the dependencies is not covered.

2. Read each line. PASS and FAIL are mechanical. FOR CLAUDE is a judgement the script cannot make. Exit
   code 2 means the data could not be read. Report that and stop.

3. Judge each FOR CLAUDE item:
   - Review findings: read the `## Reviewer findings` comment and the owner's choices in `BUILD_LOG.md`.
     Check in the diff that each finding the owner chose is fixed. Check that each other finding is
     deferred with a reason, in Known limits, the test list or the build log.
   - Build log: check `BUILD_LOG.md` has the work start, the findings, the owner's choices and every AI
     mistake for this pull request.
   - No conflicts, when GitHub has not worked it out yet: run the script again.
   - Tests on the merge, when not run: run again with `--test-merge`.

4. Write one line in the chat:
   - `MERGE: <reason>` when there is no FAIL and every FOR CLAUDE item holds. For parallel branches, add
     the merge order the script printed.
   - `FIX FIRST: <reason>` otherwise. Give it to the owner with its reason. Do not mark the pull request
     ready.

5. Only after a MERGE verdict, run `gh pr ready <N>` and write "PR #N is ready to merge." in the chat.

## Never

- Never merge, push to `main` or change repo settings. The owner merges, with a normal merge commit.
- Never call a FOR CLAUDE item a pass without checking it.
- Never print commit messages or comment text from the script's data. The script prints only check
  names, statuses, short commit IDs, file paths and counts.
