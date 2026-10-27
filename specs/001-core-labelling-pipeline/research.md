# Research: Core labelling pipeline

Each item is checked on its official source before the pull request that needs it. The answer, the URL and the date read are written here. Nothing is filled in from memory.

| Question | Needed by | Status |
|---|---|---|
| Current versions of DuckDB, dbt-core and dbt-duckdb, and which work together | data load pull request | open |
| How dbt moves a project to a cloud warehouse (adapters), in dbt's own words | README "Why this stack" | open |
| How to turn off dbt usage stats, so builds in tests make no network call | dbt pull request | open |
| Current price per token for `claude-haiku-5-5` | costs pull request (B13) | open |
| Anthropic terms on using `claude -p` with a personal subscription | backend pull request (B12) | open |
| Exact Product strings in the July 2026 file | data tests (B14) | open |

## Answered

- **Who sets Product?** The consumer. CFPB field reference: "The type of product the consumer identified in the complaint". https://cfpb.github.io/api/ccdb/fields.html, read 2026-10-27.
- **Spec Kit install.** v1.2.3, installed from the official repo tag. `uv` needed `--native-tls` on this machine because of a certificate error. https://github.github.io/spec-kit/installation.html, read 2026-10-28.
