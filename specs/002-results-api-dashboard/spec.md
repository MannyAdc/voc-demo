# Feature Specification: Results API and dashboard

**Feature Branch**: `002-results-api-dashboard`

**Created**: 2026-10-29

**Status**: Draft for the owner. Option A of 28 October: the dashboard shows results only.

**Input**: The brief asks for a front end, a middleware API, data engineering and public code, with Speed, Safety and Scale on screen.

Requirement IDs are `A1`, `A2` and so on. Tests are named `test_A<number>_...`.

## What it is

A small web app. The API serves the committed results files, and one page shows them. It never labels anything, never calls a model, and never reads the ledger, the recordings or the raw data. So it can run anywhere the repo is checked out, with no key and no data. *Changed on 30 October (owner decision, docs/USER.md): the analyst screens (A10 to A12) also read the development set's rows from the local staged table when it is there, and store review decisions.*

## Rules

- **A1. Read only, committed files only.** The API reads only committed files: `EVAL_VERSIONS.md`, `results/eval/`, `results/labels/` (the run summaries), `results/audit/`, `config/pool.toml`, `config/labels.toml`, `splits/manifest.json` and `runs/TEST_RUNS.md`. It has GET routes only. It writes nothing. *Changed on 30 October: two exceptions, the local staged table for the development set's rows (A10), and one POST route that stores a review decision (A12).*
- **A2. No complaint text.** Every response holds IDs, labels, reasons, positions, counts and figures only, as in B21. *Changed on 30 October: one exception, the complaint view of A10, and only when the owner starts the app with `--with-text`.* The API copies only named fields from each file, never a whole row or file, so a field added later is not served by accident. Each named field is checked too: a number must be a number, a name such as a verdict or a reason must be one of a fixed list, a label must be in the label list, and a complaint ID must look like one. A field that fails its check is served as empty. Tests check every route on synthetic files that hold hostile text or the wrong kind of value, both in fields the API must not serve and in fields it does serve. *Field checks added after the review of #32.*
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
- **A9. Request log and counters.** Every request is logged as one line on stderr, so `voc serve` shows it in the terminal: the time (UTC), the method, the path, the status code and the duration in milliseconds. A line never holds the query string, a header, the body or the client address. The path is logged as the pattern of the route it matched, such as `/api/eval/{version}` or `/web/{path}`, and any other path as `(unknown path)`. A route that matches both the path and the method wins over one that matches the path only. A method outside a fixed list (GET, HEAD, POST, PUT, PATCH, DELETE and OPTIONS) is logged as `(other method)`. So nothing a caller typed reaches this log line. A request cancelled before any answer, for example at shutdown, is logged as `(no response)` and counted, but not as an error. Uvicorn can still print its own error tracebacks to the same terminal. *Review of #49: full match, method list, no response and the traceback note.* `/api/health` serves `{"status": "ok", "requests": n, "client_errors": n, "server_errors": n, "started": "<ISO time>"}`: the requests answered since the app started, and how many of them got a 4xx or a 5xx status. A request is counted after its answer, so a health request does not count itself. The code is in `src/voc/api_log.py`. *Added on 30 October.*
- **A10. The analyst screens read the development set only.** They serve the complaints of `results/eval/{version}_dev.csv`, never the test set: its text and its consumer's choices are read only by the one scored run (B17), and review never touches the test set results (B20). Each ID must also be on the frozen development list, `splits/dev.csv`, and not on the test list, so an edited results file cannot let a test row through. *Added in the review of #46.* For those IDs only, the consumer's own choice and the text come from the local staged table, read only, when it is there. The text column is read only with the flag. The text is served only when the owner starts the app with `voc serve --with-text`. Without it, and on any copy without the local table, the screens serve IDs, labels and reasons only. Claude never passes `--with-text` and never opens a page served with it (CLAUDE.md). *Added on 30 October (owner decision A, docs/USER.md).*
- **A11. The consumer's own choice is hidden while a person decides.** On a quarantined complaint that has not been reviewed, it is not served. Such a complaint is also left out of every product list, because the product it is listed under would give the choice away. The list says how many are held back. The list pages by 25, and filters by product and by whether the AI was right or wrong.
- **A12. One route stores a review decision.** `POST /api/review/{version}/decision/{id}` stores, for a quarantined development complaint only: its ID, one of the 11 products or none, and one of four fixed reasons, with the time. Never free text. The label must fit the reason: "the AI's label is right" needs the AI's proposed label, "the word-based model is right" needs its suggestion, and "it fits no product" needs none. "Another product fits better" may not use either of those two labels. The request must be JSON and carry the header `X-Requested-With: voc`, which another site's form cannot set. A saved decision is locked: the first decision is the one that is scored, because after saving, the consumer's own choice is no longer hidden. A change is stored as a new entry with the reason "correction", and both stay in the file. Every field read back from the file is checked, and a broken row is skipped. The file is written whole to a temp file and swapped in, one save at a time. The file is `results/reviews/{version}_dev.csv`, which can be committed. Decisions never change a scored result (B20). *Lock, correction and safe write added in the review of #46 (owner decision).* The read guard refuses any command of Claude's that contains `--with-text`.
  - The routes: `/api/review/{version}/complaints`, `/api/review/{version}/complaint/{id}`, `/api/review/{version}/queue` and the POST above.
- **A13. The public copy.** `voc.public:app` is the app for a host such as Azure App Service. It answers only to the host name the platform sets in `WEBSITE_HOSTNAME`, and refuses to start without it. It never reads the local staged table, so it never serves complaint text or the consumer's own choice, even if a table were there. It stores no review: the POST of A12 answers 403. Everything it serves is in the public repo already. The security policy of A4 and the request log of A9 stay. `requirements.txt` pins only its own runtime packages, the `public` dependency group, from `uv.lock`, and the ZIP leaves out `uv.lock` and `pyproject.toml`, so the build installs only those. `docs/DEPLOY.md` has the owner's commands. *Added on 30 October (owner decision: deploy to Azure).*

## Not in scope

- Scoring from the page. Option B was not chosen. *Changed on 30 October: labelling by a person, in the review of A12, is now in scope.*
- Complaint text, quote text or a model answer on screen, except the development complaint text of A10 on the owner's own machine.
- Users and logins. The public copy (A13) has none, because it serves only what the public repo holds. *Changed on 30 October: hosting is in scope, as A13.*

## Known limits

- On App Service, the platform's warm-up ping uses another host name, so the public copy answers it with a 400. Each one is logged and counted as a client error at `/api/health`. The warm-up counts any answer as ready, so this does not stop the app. *Review of #50.*
- The dashboard shows what is committed. A figure that was not committed cannot be shown.
- No test drives the page in a browser. The owner checks it by eye before the demo.
- The request counters live in memory. They start again at zero when `voc serve` restarts, and they are not stored anywhere.
- The request log goes to the terminal only. It is not written to a file, so it is gone when the terminal closes.
- `/api/health` is open to anyone who can reach the app. With the A4 host check and the 127.0.0.1 listener, that is this computer only.
- If a second test run is ever logged for the same version (B17 allows it only with a reason), the route serves the file that matches one of the rows, and the page still says "the single logged test run".
