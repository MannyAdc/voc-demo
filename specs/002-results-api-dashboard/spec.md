# Feature Specification: Results API and dashboard

**Feature Branch**: `002-results-api-dashboard`

**Created**: 2026-10-29

**Status**: Draft for the owner. Option A of 28 October: the dashboard shows results only.

**Input**: The brief asks for a front end, a middleware API, data engineering and public code, with Speed, Safety and Scale on screen.

Requirement IDs are `A1`, `A2` and so on. Tests are named `test_A<number>_...`.

## What it is

A small read-only web app. The API serves the committed results files, and one page shows them. It never labels anything, never calls a model, and never reads the ledger, the recordings, the raw data or the DuckDB file. So it can run anywhere the repo is checked out, with no key and no data.

## Rules

- **A1. Read only, committed files only.** The API reads only committed files: `EVAL_VERSIONS.md`, `results/eval/`, `results/labels/` (the run summaries), `results/audit/`, `config/pool.toml`, `config/labels.toml` and `splits/manifest.json`. It has GET routes only. It writes nothing.
- **A2. No complaint text.** Every response holds IDs, labels, reasons, positions, counts and figures only, as in B21. The API copies only named fields from each file, never a whole row or file, so a field added later is not served by accident. Each named field is checked too: a number must be a number, a name such as a verdict or a reason must be one of a fixed list, a label must be in the label list, and a complaint ID must look like one. A field that fails its check is served as empty. Tests check every route on synthetic files that hold hostile text or the wrong kind of value, both in fields the API must not serve and in fields it does serve. *Field checks added after the review of #32.*
- **A3. Names are checked.** A prompt version in a path must match `v` followed by digits, and its file must exist. Anything else is a 404 with a short message. No path is built from unchecked input.
- **A4. Local by default.** `voc serve` listens on 127.0.0.1 only. It answers only requests addressed to `127.0.0.1` or `localhost`, so a page on another site cannot reach it through DNS rebinding. It sends a Content-Security-Policy that allows scripts, styles and data only from the app itself. The one exception is an empty `data:` icon, so the browser asks for no icon file. The page loads nothing from outside. *Host check and icon note added after the review of #32.*
- **A5. The routes.**
  - `/api/health`
  - `/api/versions`: the rows of `EVAL_VERSIONS.md`.
  - `/api/eval/{version}`: the figures of `results/eval/{version}_dev.json`, labelled as tuning figures.
  - `/api/eval/{version}/quarantine`: the quarantine queue. For each quarantined complaint: its ID, its reason, the LLM's proposed label and the TF-IDF label.
  - `/api/run/{version}`: named fields of the labelling run summary: counts, cut, calls by source, tokens, cost, run time and time per 1,000.
  - `/api/audit/{version}`: the counts of `results/audit/{version}_dev.json`.
  - `/api/data`: the pool and set sizes, and the copy counts, from `splits/manifest.json` and `config/pool.toml`.
- **A6. The audit writes its counts.** `voc audit` also writes its counts to `results/audit/{version}_{set}.json`, so the dashboard can show them without the recordings.
- **A7. The page.** One page, served by the app, in three panels.
  - **Speed:** cost and time per 1,000 complaints, for the LLM and for TF-IDF, with what each figure counts.
  - **Safety:** the quote check (accepted, and quarantined by reason), the quarantine queue, and the audit counts.
  - **Scale:** the July export (672,036 complaints), the pool after copies are removed, and the three set sizes.
  - Above them, the head-to-head: re-weighted strict accuracy, precision and coverage for both methods, the interval and the verdict. Every development figure says "tuning figure". Charts are drawn in the page as SVG, with no chart library.
- **A8. Tests.** The API is tested with FastAPI's in-process test client, so no socket is opened. The page is checked by a test that reads the HTML and finds no outside script or style.
- **A9. Request log and counters.** Every request is logged as one line on stderr, so `voc serve` shows it in the terminal: the time (UTC), the method, the path, the status code and the duration in milliseconds. A line never holds the query string, a header, the body or the client address. The path is logged as the pattern of the route it matched, such as `/api/eval/{version}` or `/web/{path}`, and any other path as `(unknown path)`. A method outside the standard ones is logged as `(other method)`. So nothing a caller typed reaches the log. `/api/health` serves `{"status": "ok", "requests": n, "client_errors": n, "server_errors": n, "started": "<ISO time>"}`: the requests answered since the app started, and how many of them got a 4xx or a 5xx status. A request is counted after its answer, so a health request does not count itself. The code is in `src/voc/api_log.py`. *Added on 30 October.*

## Not in scope

- Labelling or scoring from the page. Option B was not chosen.
- Any complaint text, quote text or model answer on screen. The owner reads examples in their own terminal.
- Users, logins or hosting. It runs on the owner's laptop for the demo.

## Known limits

- The dashboard shows what is committed. A figure that was not committed cannot be shown.
- No test drives the page in a browser. The owner checks it by eye before the demo.
- The request counters live in memory. They start again at zero when `voc serve` restarts, and they are not stored anywhere.
- The request log goes to the terminal only. It is not written to a file, so it is gone when the terminal closes.
- `/api/health` is open to anyone who can reach the app. With the A4 host check and the 127.0.0.1 listener, that is this computer only.
