# voc-demo

Status: planning done, no code yet (28 October 2026).

A Voice of the Customer pipeline on the public US CFPB Consumer Complaint Database. An LLM labels each complaint by Product and quotes the sentence that supports the label. A script checks that the quote really appears in the text. A label that fails a check goes to quarantine with a reason. It is never dropped and never counted as correct.

## About the data

- Source: the CFPB Consumer Complaint Database. Raw data is not stored in this repo.
- The CFPB says: "This database is not a statistical sample of consumers' experiences in the marketplace". Results here describe this data only.
- The CFPB also says: "All complaint data we publish is freely available for anyone to use, analyze, and build on." Both quotes are from the [CFPB complaint database page](https://www.consumerfinance.gov/data-research/consumer-complaints/), read 28 October 2026.
- The Product and Issue fields are set by the consumer, not by the CFPB ("The type of product the consumer identified in the complaint", [CFPB field reference](https://cfpb.github.io/api/ccdb/fields.html)). So the recorded labels are noisy, and some measured "errors" will be label noise.

## Loading a new month

- `voc load july_2026` and then `voc load august_2026` put each pinned monthly file into one staged DuckDB table. `voc dbt build` then builds the models and runs the data tests.
- The load and the staged dbt model are incremental and keyed on complaint ID. A run adds only complaint IDs it has not seen, so loading the same file again adds nothing.
- What this does not cover yet:
  - Late or corrected records. If a later file holds a complaint ID that is already loaded with changed values, the first row is kept and the change is ignored.
  - Column changes. A file with a missing or extra column fails the load. A new or removed column in the staged table fails the incremental dbt build (`on_schema_change='fail'`). Neither is migrated automatically.
- `voc dbt docs` writes the dbt docs and the lineage graph to the git-ignored `data/dbt/target` folder. Those files hold local paths, including the user folder. Strip the local paths before the lineage graph is published.

## Where to start

- What it must do: [specs/001-core-labelling-pipeline/spec.md](specs/001-core-labelling-pipeline/spec.md)
- How we work: [CLAUDE.md](CLAUDE.md)
- What happened and when: [BUILD_LOG.md](BUILD_LOG.md)
