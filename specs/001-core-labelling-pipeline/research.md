# Research: Core labelling pipeline

Each item is checked on its official source before the pull request that needs it. The answer, the URL and the date read are written here. Nothing is filled in from memory.

| Question | Needed by | Status |
|---|---|---|
| Current versions of DuckDB, dbt-core and dbt-duckdb, and which work together | data load pull request | checked 28 October, see "Answered" |
| How dbt moves a project to a cloud warehouse (adapters), in dbt's own words | README "Why this stack" | open |
| How to turn off dbt usage stats, so builds in tests make no network call | dbt pull request | checked 28 October, see "Answered" |
| Current price per token for `claude-haiku-5-5` | costs pull request (B13) | checked 28 October on the live pricing page: $0.10 input, $0.50 output per million tokens (prompts up to 100,000 tokens), Batch API 50% off. Re-check in T009 |
| Anthropic terms on using `claude -p` with a personal subscription | backend pull request (B12) | closed: `cli` cut on 28 October |
| Exact Product strings in the July 2026 file | data tests (B14) | answered 28 October by `voc profile`: 11 values, frozen in `config/labels.toml` (T002b) |
| Does the API still accept a temperature setting | backend pull request (B12) | answered 28 October, Anthropic's migration guide (https://platform.claude.com/docs/en/api/migration-2026-10-21): "In `2026-10-21`, a request that sends `temperature`, `top_p`, or `top_k` returns a 400 error, even at the parameter's default value." Claude 4.7 and later models accept only the defaults. B12 records the effort setting instead |
| Which Anthropic Python SDK release to pin | backend pull request (B12) | checked 28 October on PyPI: 2.0.0 (21 October) is the first on API version `2026-10-21`, latest 2.3.0 (23 October). The newest release at least two weeks old is 1.13.0 (9 October, API version `2023-06-01`). Owner to choose in T009 |
| `claude -p` flags for no tools, no MCP servers, no settings or instruction files, one turn | backend pull request (B12) | closed: `cli` cut on 28 October |
| Does an `ANTHROPIC_API_KEY` in the environment make `claude -p` bill the API instead of the subscription | backend pull request (B12) | closed: `cli` cut on 28 October |
| Does `claude -p` report token use in its JSON output | backend pull request (B8, B12) | closed: `cli` cut on 28 October |
| Is the UTF-8 byte count of a prompt always at least its token count | ledger pull request (B8) | open |
| Training cutoff of `claude-haiku-5-5`, compared with the July 2026 complaint dates | README | open |
| How many input tokens `claude -p` adds for its own system prompt (the `cli` allowance) | backend pull request (B8, B12) | closed: `cli` cut on 28 October |
| Export download URL for the July 2026 file, and its SHA-256 | download pull request (B16) | answered 28 October: the CFPB serves only its current export, so the July file is pinned by SHA-256 in `config/data_files.toml`, with no URL (T002b, B16 amended) |
| Does `claude -p` let us set an output-token limit and a temperature | backend pull request (B8, B12) | closed: `cli` cut on 28 October |
| How to run CI tests with no network on GitHub-hosted Linux runners | CI pull request | open |

## Answered

- **Who sets Product?** The consumer. CFPB field reference: "The type of product the consumer identified in the complaint". https://cfpb.github.io/api/ccdb/fields.html, read 2026-10-27.
- **Spec Kit install.** v1.2.3, installed from the official repo tag. `uv` needed `--native-tls` on this machine because of a certificate error. https://github.github.io/spec-kit/installation.html, read 2026-10-28.
- **Branch protection on a private personal repo.** GitHub's plans page lists "Protected branches" for private repositories under GitHub Pro only. Free gives public repositories "a full feature set". So required checks are possible once the repo is public. https://docs.github.com/en/get-started/learning-about-github/githubs-plans, read 2026-10-28.
- **DuckDB, dbt-core and dbt-duckdb versions.** Read on PyPI on 2026-10-28, from each package's JSON page (upload times in UTC):
  - duckdb: newest release 2.0.0 (2026-10-21). The repo pins 1.5.6 (2026-09-28), the newest 1.5 release. https://pypi.org/pypi/duckdb/json
  - dbt-core: newest release 1.12.6 (2026-10-14), 14 days old. Release candidates of 2.0.0 exist and are not used. https://pypi.org/pypi/dbt-core/json
  - dbt-duckdb: newest release 1.11.1 (2026-10-26), only 2 days old. The one before is 1.11.0 (2026-08-07). Both require `duckdb>=1.0.0`, `dbt-core>=1.8.0`, `dbt-adapters<2,>=1` and `dbt-common<2,>=1`. https://pypi.org/pypi/dbt-duckdb/json
  - The dbt-duckdb README says: "The latest supported version targets `dbt-core` versions >= 1.8.x and `duckdb` version >= 1.0.0". So duckdb 1.5.6 is supported. https://github.com/duckdb/dbt-duckdb, read 2026-10-28.
  - Chosen, following the two-week rule: dbt-core 1.12.6 and dbt-duckdb 1.11.0, with duckdb 1.5.6.
- **dbt-duckdb incremental models.** The README lists the `delete+insert`, `append`, `merge` and `microbatch` strategies. `unique_key` names the key column. `merge` needs DuckDB 1.4.0 or later. https://github.com/duckdb/dbt-duckdb, read 2026-10-28.
- **Turning off dbt usage stats.** dbt's page says: for dbt Core, set `send_anonymous_usage_stats: false` under `flags:` in `dbt_project.yml`, or the environment variable `DBT_SEND_ANONYMOUS_USAGE_STATS=False` up to Core 1.10 and `DBT_ENGINE_SEND_ANONYMOUS_USAGE_STATS=False` from Core 1.11. `DO_NOT_TRACK=1` does the same. It lists no command-line flag. https://docs.getdbt.com/reference/global-configs/usage-stats (page source in the dbt docs repo), read 2026-10-28. `tests/conftest.py` still sets the old variable name, but it also sets `DO_NOT_TRACK=1`.
- **GitHub push protection.** For personal accounts it is on by default and "Blocks you from pushing secrets to public repositories". For private repositories it "Requires GitHub Secret Protection to be enabled." So while the repo is private, our own gitleaks checks are the guard. https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection, read 2026-10-28.
