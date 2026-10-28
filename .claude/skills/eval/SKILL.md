---
name: "eval"
description: "Score a finished labelling run of the development set against TF-IDF, and add its row to EVAL_VERSIONS.md."
argument-hint: "The prompt version, then a short note of what changed, for example: v2 \"definitions for small categories\""
user-invocable: true
disable-model-invocation: false
---

# /eval

Scores one finished run of `voc label dev` against TF-IDF (B10, B15, B23). It calls no model and opens no
network connection. It prints figures, labels, reasons and IDs only (B21).

## Steps

1. Check that `results/labels/<version>_dev.json` exists. If it does not, stop and tell the owner to run
   `voc label dev --prompt <version>` in their own terminal. Claude never runs a live labelling run.
2. Run, from the repo root:

   ```
   uv run --native-tls voc evaluate dev --prompt <version> --note "<what changed>"
   ```

3. If it refuses (a stopped run, a limited run, a list mismatch, or pool counts that do not match), report
   the refusal as printed. Do not work around it.
4. Report the printed figures to the owner as they are. Say they are tuning figures. Never call a version
   better than another from this table, because that needs a paired test, which is cut (B15).
5. Never read the narratives, quotes or model answers behind the figures. For error analysis, use the
   analyser (T018a). The owner spot-checks with `show` in their own terminal.

## Never

- Never score the test set. That waits for the owner's `final` (B17).
- Never edit or delete a row of `EVAL_VERSIONS.md`. Rows are only added.
