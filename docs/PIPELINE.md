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
