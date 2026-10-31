# How the pipeline works

Moved here from the README on 31 October 2026, word for word, except that references to sections now on other pages became links, and, in review, one claim about reviews became a statement of the rule. Back to the [README](../README.md).

## How it works

1. `voc load july_2026` checks the export's SHA-256 against its pin in `config/data_files.toml`, then loads it into DuckDB.
2. `voc dbt build` builds the staged and curated models and runs the data tests. The models leave out the test set.
3. `voc sample` froze the development, test and training lists in `splits/`, by ID and content hash. They are never regenerated.
4. `voc label dev` sends each complaint to the model, with the text between fixed tags, and records every answer.
5. A script checks each quote. A failure is quarantined with its reason.
6. `voc evaluate dev` scores both methods on the same complaints and adds a row to `EVAL_VERSIONS.md`.
7. `voc final --prompt v1`, run once by the owner, commits its log row before any call, then labels and scores the test set.
8. `voc serve` shows the committed results on a local dashboard at 127.0.0.1, with no complaint text. It logs each request in the terminal as one line (time, method, route pattern, status and milliseconds, never the query string or the client address), and `/api/health` counts the requests and the 4xx and 5xx answers since start (A9 in [specs/002-results-api-dashboard/spec.md](../specs/002-results-api-dashboard/spec.md)).

**The same models on Databricks (T021).** `voc dbt build --target databricks` runs the dbt models on a Databricks SQL warehouse, on synthetic data only. `scripts/databricks_fixture_build.py` loads the committed synthetic fixture with the same load code, writes it as a dbt seed in a work folder, and runs the build. The command refuses unless every complaint ID in both seeds starts with `SYN-`. Four DuckDB-only parts have a Databricks branch: the staged rows come from the seed, the test list is a seed, not a local file, the text check uses `rlike`, and the incremental model uses `merge`. The connection comes from environment variables. The adapter is pinned in its own dependency group (`dbt-databricks==1.13.0`), so a normal install does not get it. The lock file is shared, though, so adding it moved four packages of the normal install down: dbt-common, packaging, pydantic and pydantic-core. First live run, by the owner on 30 October 2026, on a Databricks Free Edition SQL warehouse: `uv run --native-tls --group databricks python scripts/databricks_fixture_build.py tests/fixtures/dbt/complaints.csv <new work folder>`, with the connection in environment variables. It printed "dbt build: 2 seeds, 2 models, 4 data tests. passed 8, failed 0, errors 0, skipped 0". A search of the work folder afterwards found the token in none of its files.


## The real exports on Databricks

Owner decision, 31 October 2026: the same dbt models run on Databricks on the real July and August exports, not only on synthetic data.

- The owner uploads the two pinned exports, under their own names, to the Unity Catalog volume `voc_raw` in the `default` schema of the `workspace` catalog.
- `voc dbt build --target databricks --month <month>` reads the month's file from the volume with every column as text, and types it as `voc load` does (`dbt/models/landed_complaints.sql`).
- Before any staged model is built from it, data tests on the warehouse check:
  - that the file's SHA-256 matches its pin in `config/data_files.toml`, so the rows are the same bytes the local load checked (`dbt/tests/landed_file_matches_pin.sql`)
  - the row count, for July, where a count is pinned (`dbt/tests/landed_row_count_matches_pin.sql`)
  - the dates, the Yes/No flag and the complaint IDs (`dbt/tests/landed_rows_are_valid.sql` and `dbt/models/schema.yml`)
  - the Products, against the label set (`dbt/tests/landed_product_in_label_list.sql`)
  - that the test rows are left out (`dbt/tests/landed_has_no_test_set_rows.sql`)
- dbt skips every model below a failing test. The models are built in the schema `voc_cfpb`, the synthetic seeds in `voc_synthetic`.
- The staged model is incremental on Databricks too: the August run adds only complaint IDs that the July run did not.
- After a passing build, two queries read the row counts back: the staged rows by month, and the curated rows. Only counts and check names are printed. The narrative text stays in the warehouse.

**Step by step, in the owner's own PowerShell.**

1. Upload the two files: in the workspace's sidebar, click **New**, then **Add or upload data**, then **Upload files to a volume**. Pick catalog `workspace`, schema `default`, and create the volume `voc_raw`. Drop in `CCDB_Export_20_July_2026.csv` and `CCDB_Export_21_August_2026.csv` from the folders named by `VOC_DATA_DIR` and `VOC_NEXT_DATA_DIR`. (Databricks, "Upload files to a volume", updated 27 October 2026. The limit is 5 GB per file.)
2. Find the connection details: in the sidebar, click **SQL Warehouses**, open the warehouse, and open **Connection details**. Keep the page open for the server hostname and the HTTP path.
3. Open PowerShell in your clone of this repo and run these lines. Each `Read-Host` asks for one value. Paste it and press Enter. The token is read from the encrypted file made on 30 October and never shown:

   ```powershell
   $env:DATABRICKS_HOST = Read-Host "Server hostname, without https://"
   $env:DATABRICKS_HTTP_PATH = Read-Host "HTTP path"
   $sec = Get-Content "$HOME\.voc\databricks-token.dpapi" | ConvertTo-SecureString
   $env:DATABRICKS_TOKEN = [System.Net.NetworkCredential]::new('', $sec).Password
   ```

4. Build July:

   ```powershell
   $julyWork = Join-Path $env:TEMP ("voc-dbx-july-" + (Get-Date -Format "yyyyMMdd-HHmm"))
   uv run --native-tls --group databricks python scripts/databricks_month_build.py july_2026 $julyWork
   ```

5. Then August, the incremental load:

   ```powershell
   $augustWork = Join-Path $env:TEMP ("voc-dbx-august-" + (Get-Date -Format "yyyyMMdd-HHmm"))
   uv run --native-tls --group databricks python scripts/databricks_month_build.py august_2026 $augustWork
   ```

6. Remove the token from the session, and delete the two work folders. If Databricks fails to read a row, dbt's log in a work folder can hold part of it. Nothing there is printed, but the folders are outside the repo's guards:

   ```powershell
   Remove-Item Env:DATABRICKS_TOKEN
   Remove-Variable sec
   Remove-Item -Recurse -Force $julyWork, $augustWork
   ```

Each build prints a line of counts, `dbt build: ... passed ..., failed 0, errors 0, skipped 0`, then the rows by month and the curated rows. Keep `--group databricks`: without it, `uv run` removes the Databricks packages.

## Run it yourself

Without any data or key, you can run the tests, the dbt build on the synthetic fixture and the dashboard:

```
uv sync
uv run pytest
uv run python scripts/dbt_fixture_build.py tests/fixtures/dbt/complaints.csv <empty work folder>
uv run voc serve
```

Then open http://127.0.0.1:8000. The tests never open a network connection or call a model.

To label real complaints you need the pinned July 2026 export. The CFPB serves only its current export, updated about daily, so that exact file cannot be downloaded again. `python scripts/download.py <empty folder>` fetches today's file, a zip archive, and prints the archive's SHA-256. The pins in `config/data_files.toml` are on the CSV inside, so a new file must be unzipped and given its own pin. The data folder is given by an environment variable. The API key goes in an environment variable too, never in a file in the repo. Contributors also install gitleaks and run `git config core.hooksPath .githooks` (see [CLAUDE.md](../CLAUDE.md)).


## Loading a new month

- `voc load july_2026` and then `voc load august_2026` put each pinned monthly file into one staged DuckDB table. `voc dbt build` then builds the models and runs the data tests.
- The dbt models leave out the test set (B17). They read the test IDs from `splits/test.csv`. Setting the dbt variable `final` to true turns this off, and `voc dbt` always passes it as false. The staged table under the models still holds the test rows.
- The load and the staged dbt model are incremental and keyed on complaint ID. A run adds only complaint IDs it has not seen, so loading the same file again adds nothing.
- What this does not cover yet:
  - Late or corrected records. If a later file holds a complaint ID that is already loaded with changed values, the first row is kept and the change is ignored.
  - Column changes. A file with a missing or extra column fails the load. A new or removed column in the staged table fails the incremental dbt build (`on_schema_change='fail'`). Neither is migrated automatically.
- `voc dbt docs` writes the dbt docs and the lineage graph to the git-ignored `data/dbt/target` folder. Those files hold local paths, including the user folder, so they are not committed.
- `voc dbt lineage` writes [docs/LINEAGE.md](LINEAGE.md): the lineage graph of the source, the models and the data tests, with node names and edges only, and no paths. It printed "dbt lineage: 1 sources, 0 seeds, 2 models, 6 data tests, 9 edges. Written to docs/LINEAGE.md." (`uv run --native-tls voc dbt lineage`, 30 October 2026). A test fails if the committed file no longer matches the dbt project.


## How it was built

- Every rule is in the [spec](../specs/001-core-labelling-pipeline/spec.md), and the API's rules are in [specs/002-results-api-dashboard/spec.md](../specs/002-results-api-dashboard/spec.md). Every test is named after its rule.
- Tests come first. Each pull request that changes code has a commit with failing tests only, then the code.
- A git hook runs gitleaks, a names check and the full test suite on exactly the staged files, for every commit in a clone where the hook is switched on. Known limits in [LIMITS.md](LIMITS.md) lists the ways around it.
- The rule: a fresh reviewer agent reads each pull request. Its findings and Claude's check of each are posted on the pull request. The owner decides what to fix, and the owner merges.
- `scripts/merge_verdict.py` runs the mechanical merge checks and leaves the judgement items to Claude.
