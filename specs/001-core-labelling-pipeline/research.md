# Research: Core labelling pipeline

Each item is checked on its official source before the pull request that needs it. The answer, the URL and the date read are written here. Nothing is filled in from memory.

| Question | Needed by | Status |
|---|---|---|
| Current versions of DuckDB, dbt-core and dbt-duckdb, and which work together | data load pull request | open |
| How dbt moves a project to a cloud warehouse (adapters), in dbt's own words | README "Why this stack" | open |
| How to turn off dbt usage stats, so builds in tests make no network call | dbt pull request | open |
| Current price per token for `claude-haiku-5-5` | costs pull request (B13) | checked 28 October on the live pricing page: $0.10 input, $0.50 output per million tokens (prompts up to 100,000 tokens), Batch API 50% off. Re-check in T009 |
| Anthropic terms on using `claude -p` with a personal subscription | backend pull request (B12) | closed: `cli` cut on 28 October |
| Exact Product strings in the July 2026 file | data tests (B14) | open |
| `claude -p` flags for no tools, no MCP servers, no settings or instruction files, one turn | backend pull request (B12) | closed: `cli` cut on 28 October |
| Does an `ANTHROPIC_API_KEY` in the environment make `claude -p` bill the API instead of the subscription | backend pull request (B12) | closed: `cli` cut on 28 October |
| Does `claude -p` report token use in its JSON output | backend pull request (B8, B12) | closed: `cli` cut on 28 October |
| Is the UTF-8 byte count of a prompt always at least its token count | ledger pull request (B8) | open |
| Training cutoff of `claude-haiku-5-5`, compared with the July 2026 complaint dates | README | open |
| How many input tokens `claude -p` adds for its own system prompt (the `cli` allowance) | backend pull request (B8, B12) | closed: `cli` cut on 28 October |
| Export download URL for the July 2026 file, and its SHA-256 | download pull request (B16) | open |
| Does `claude -p` let us set an output-token limit and a temperature | backend pull request (B8, B12) | closed: `cli` cut on 28 October |
| How to run CI tests with no network on GitHub-hosted Linux runners | CI pull request | open |

## Answered

- **Who sets Product?** The consumer. CFPB field reference: "The type of product the consumer identified in the complaint". https://cfpb.github.io/api/ccdb/fields.html, read 2026-10-27.
- **Spec Kit install.** v1.2.3, installed from the official repo tag. `uv` needed `--native-tls` on this machine because of a certificate error. https://github.github.io/spec-kit/installation.html, read 2026-10-28.
- **Branch protection on a private personal repo.** GitHub's plans page lists "Protected branches" for private repositories under GitHub Pro only. Free gives public repositories "a full feature set". So required checks are possible once the repo is public. https://docs.github.com/en/get-started/learning-about-github/githubs-plans, read 2026-10-28.
- **GitHub push protection.** For personal accounts it is on by default and "Blocks you from pushing secrets to public repositories". For private repositories it "Requires GitHub Secret Protection to be enabled." So while the repo is private, our own gitleaks checks are the guard. https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection, read 2026-10-28.
