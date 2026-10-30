# Why this stack

Moved here from the README on 31 October 2026, word for word, except that references to sections now on other pages became links. Back to the [README](../README.md).

## Why this stack

The judgement here is to use the simplest tool that does the job. No tool was added for show. The one optional demonstration is Databricks (T021), added to show that the dbt models carry over to another platform.

**Size.** The July 2026 export holds 672,036 complaints ([docs/DATA.md](DATA.md), `results/profile_july_2026.json`). The file is 216,250,982 bytes (`config/data_files.toml`). That fits on one laptop. A Spark cluster or a cloud warehouse would add setup time, cost and accounts, with no gain at this size.

**dbt is the part that carries over.** The SQL models and the data tests are dbt code, and dbt draws the lineage and writes the docs from them. dbt's documentation says: "dbt connects with data platforms by using a dedicated adapter plugin for each". Its table lists Databricks as "Generally available", and DuckDB as "Generally available" with the note "(CLI only)" ([Supported data platforms](https://docs.getdbt.com/docs/connect-adapters), read 30 October 2026). In this repo the same models ran on a Databricks SQL warehouse, on synthetic data. The run printed "dbt build: 2 seeds, 2 models, 4 data tests. passed 8, failed 0, errors 0, skipped 0" (see "The same models on Databricks (T021)" in [PIPELINE.md](PIPELINE.md), and [BUILD_LOG.md](../BUILD_LOG.md), 30 October). Four DuckDB-only parts needed a Databricks branch to get there.

**Anyone can run it.** The tests, the dbt build on the synthetic fixture and the dashboard need no account, no key and no money. After `uv sync`, each is one command (see "Run it yourself" in [PIPELINE.md](PIPELINE.md)). CI runs the same dbt build, with its data tests, on the committed synthetic fixture with no network (`.github/workflows/ci.yml`).

**Time goes to verification, not infrastructure.** With no cluster or warehouse to set up, the time went to the quote check (`src/voc/evidence.py`), the evaluation against TF-IDF with a paired bootstrap ([docs/HOW_WE_MEASURE.md](HOW_WE_MEASURE.md)), and the tests written before the code.

**When to switch.**
- The data no longer fits on one machine. Then the dbt models can move to a warehouse through its adapter. The Databricks run showed this on synthetic data, through another adapter. It did not show how a large load would move.
- Many people write at once. DuckDB's documentation says that in its in-process mode "one process can both read and write to the database". It also says: "Writing to DuckDB's native database format from multiple processes is supported through the Quack remote protocol, which turns DuckDB into a client-server database." And: "Alternatively, consider using the DuckLake format with PostgreSQL as the catalog database." ([Concurrency](https://duckdb.org/docs/2.0/connect/concurrency.html), the DuckDB 2.0 docs, read 30 October 2026. This repo pins DuckDB 1.5.6 and uses neither option.)
- There are many pipelines that depend on each other, retries for each step, or backfills of past months. Then a scheduler such as Airflow earns its cost (see the scheduler note under Scale in [RESULTS.md](RESULTS.md)). For the synthetic run, one scheduled GitHub Actions job is enough.

Versions are the pins in `pyproject.toml`.

- **DuckDB** (`duckdb==1.5.6`): one local file, no server, enough for a monthly export of 216 MB (216,250,982 bytes, `config/data_files.toml`).
- **dbt** (`dbt-core==1.12.6`, `dbt-duckdb==1.11.0`): the models and data tests live as reviewed code, with incremental loads keyed on complaint ID.
- **scikit-learn** (`scikit-learn==1.9.1`): the TF-IDF baseline. It is cheap, fast and well understood, which makes it the honest thing to beat.
- **Anthropic SDK** (`anthropic==1.13.0`) with claude-haiku-5-5: Anthropic's low-cost model for high-volume work such as classification, at $0.10 per million input tokens and $0.50 per million output tokens (`config/prices.toml`, from the [pricing page](https://platform.claude.com/docs/en/about-claude/pricing), checked 28 October 2026).
- **FastAPI** (`fastapi==0.143.0`, with `uvicorn==0.54.0`): a small read-only API and dashboard over the committed results.
- **uv**: one lock file (`uv.lock`), so every machine and CI install the same versions.
