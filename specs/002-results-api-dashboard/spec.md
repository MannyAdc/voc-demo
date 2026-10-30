# Feature Specification: Results API and dashboard

**Feature Branch**: `002-results-api-dashboard`

**Created**: 2026-10-29

**Status**: Draft for the owner. Option A of 28 October: the dashboard shows results only.

**Input**: The brief asks for a front end, a middleware API, data engineering and public code, with Speed, Safety and Scale on screen.

Requirement IDs are `A1`, `A2` and so on. Tests are named `test_A<number>_...`.

## What it is

A small read-only web app. The API serves the committed results files, and one page shows them. It never labels anything, never calls a model, and never reads the ledger, the recordings, the raw data or the DuckDB file. So it can run anywhere the repo is checked out, with no key and no data.

## Rules

- **A1. Read only, committed files only.** The API reads only committed files: `EVAL_VERSIONS.md`, `results/eval/`, `results/labels/` (the run summaries), `results/audit/`, `config/pool.toml`, `config/labels.toml`, `splits/manifest.json` and `runs/TEST_RUNS.md`. It has GET routes only. It writes nothing.
- **A2. No complaint text.** Every response holds IDs, labels, reasons, positions, counts and figures only, as in B21. The API copies only named fields from each file, never a whole row or file, so a field added later is not served by accident. Each named field is checked too: a number must be a number, a name such as a verdict or a reason must be one of a fixed list, a label must be in the label list, and a complaint ID must look like one. A field that fails its check is served as empty. Tests check every route on synthetic files that hold hostile text or the wrong kind of value, both in fields the API must not serve and in fields it does serve. *Field checks added after the review of #32.*
- **A3. Names are checked.** A prompt version in a path must match `v` followed by digits, and its file must exist. Anything else is a 404 with a short message. No path is built from unchecked input.
- **A4. Local by default.** `voc serve` listens on 127.0.0.1 only. It answers only requests addressed to `127.0.0.1` or `localhost`, so a page on another site cannot reach it through DNS rebinding. It sends a Content-Security-Policy that allows scripts, styles and data only from the app itself. The one exception is an empty `data:` icon, so the browser asks for no icon file. The page loads nothing from outside. *Host check and icon note added after the review of #32.*
- **A5. The routes.**
  - `/api/health`
  - `/api/versions`: the rows of `EVAL_VERSIONS.md`.
  - `/api/eval/{version}`: the figures of `results/eval/{version}_dev.json`, labelled as tuning figures.
  - `/api/test/{version}`: the claim's verdict, from `results/eval/{version}_test.json` and `results/labels/{version}_test.json`. It answers only when `runs/TEST_RUNS.md` has a logged row for that version, and the scored file matches that row by list hash, model and count, with `set` equal to "test" (B17). Named and checked fields only: the prompt version, backend and model, the verdict, the difference, the interval, resamples and seed, both methods' figures (re-weighted strict accuracy, precision, coverage, macro-F1, quarantine rate, cost and time per 1,000), who was right, the precision against coverage points, the run counts, tokens, live cost and quarantine reasons, and the F1 of each product in the label list, or "too few to judge". *Changed in the review of #44: the match to the logged row, and the full field list.* *Added on 30 October (owner decision): the dashboard showed only development figures.*
  - `/api/tested`: the prompt versions with a logged test run, in log order. The page asks for the last one. *Added in the review of #44.*
  - `/api/eval/{version}/quarantine`: the quarantine queue. For each quarantined complaint: its ID, its reason, the LLM's proposed label and the TF-IDF label.
  - `/api/run/{version}`: named fields of the labelling run summary: counts, cut, calls by source, tokens, cost, run time and time per 1,000.
  - `/api/audit/{version}`: the counts of `results/audit/{version}_dev.json`.
  - `/api/data`: the pool and set sizes, and the copy counts, from `splits/manifest.json` and `config/pool.toml`.
- **A6. The audit writes its counts.** `voc audit` also writes its counts to `results/audit/{version}_{set}.json`, so the dashboard can show them without the recordings.
- **A7. The page.** One page, served by the app. First, the verdict on the frozen test set, with its interval and the F1 per product. It is not marked as a tuning figure. *Added on 30 October.* Then three panels of development figures.
  - **Speed:** cost and time per 1,000 complaints, for the LLM and for TF-IDF, with what each figure counts.
  - **Safety:** the quote check (accepted, and quarantined by reason), the quarantine queue, and the audit counts.
  - **Scale:** the July export (672,036 complaints), the pool after copies are removed, and the three set sizes.
  - Above them, the head-to-head: re-weighted strict accuracy, precision and coverage for both methods, the interval and the verdict. Every development figure says "tuning figure". Charts are drawn in the page as SVG, with no chart library.
- **A8. Tests.** The API is tested with FastAPI's in-process test client, so no socket is opened. The page is checked by a test that reads the HTML and finds no outside script or style.

## Not in scope

- Labelling or scoring from the page. Option B was not chosen.
- Any complaint text, quote text or model answer on screen. The owner reads examples in their own terminal.
- Users, logins or hosting. It runs on the owner's laptop for the demo.

## Known limits

- The dashboard shows what is committed. A figure that was not committed cannot be shown.
- No test drives the page in a browser. The owner checks it by eye before the demo.
- If a second test run is ever logged for the same version (B17 allows it only with a reason), the route serves the file that matches one of the rows, and the page still says "the single logged test run".
