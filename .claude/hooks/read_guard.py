"""Read guard (B21) and final guard (B17). PreToolUse on every tool.

Denies any tool call that names a protected place: the raw data folders
(`VOC_DATA_DIR` for July, `VOC_NEXT_DATA_DIR` for the next month and
`VOC_JUNE_DATA_DIR` for June, each from the environment or the local
`.env`), the repo's `data` folder (the
DuckDB file, its write-ahead log and dbt's output), the home folder
`.voc` (ledger, recordings and the home test log), any `.duckdb` file, a
`recordings` folder, a CFPB export file (the archive's and the pins' `CCDB_Export`
names, and the current bulk export's `complaints.csv` and `complaints.csv.zip`
with any copy number or suffix, except the synthetic fixture
`tests/fixtures/dbt/complaints.csv` in this repo), or the `.env` file that holds the
API key (`.env.example` is allowed). Every string in the tool input is
checked as a path, except text the tool writes (such as `content`), after
`..` is resolved. A search of a folder that holds the data folder or `.voc`
is denied too. A command that names a `.dpapi` file, or a call that decrypts
one, is denied, so a wildcard cannot find the owner's encrypted Databricks
token in `.voc` without naming the folder (review of #87).

Any tool input with a `command` field (Bash, PowerShell, Monitor) is checked
as a shell command. That is a text check, so it also covers `cat`,
`Get-Content` and the like. `show` and `dbt show` are denied outright: only
the owner runs `show`, in the owner's own terminal. `git show` is allowed.
A command containing the word `final` asks the owner. A command containing
`--with-text` is denied: only the owner starts the app with complaint text (A10).
A command that names `voc review sheet` or `voc review import`, in any form,
or the module's sheet and import functions, is denied, as `show` is: only the
owner writes and reads the review sheets, which hold complaint text (spec 003,
V8). Quotes, backticks and line breaks are taken out before the check, so a
mention inside a commit message or a quoted text is denied too.

Spec 004, J14: a command that runs the Databricks CLI, as any word of a line,
or names its SDK, its saved sign-in `.databrickscfg` or the volume `voc_raw`,
is denied, and so is a file tool on that sign-in file. Claude's `gh` signs in
as the owner, who approves the June run, so a command that reads an Actions
run log or artifact, starts, re-runs, cancels or deletes a run, approves a
deployment, uses the environments, secrets or variables APIs, writes through
the REST API or a GraphQL mutation, changes the repo's settings, prints the
token, sets an alias or an extension, or merges, by `gh` or by the API, is
denied too. Flags between `gh`, its group and its subcommand change nothing.
Reads through `gh api` stay allowed.
"""
import json
import os
import re
import sys
from pathlib import Path

# Text a tool writes or a search pattern, not a path. Glob's pattern is a path and is checked.
NOT_PATHS = {"content", "new_string", "old_string", "new_source", "description", "prompt", "message", "summary",
             "question", "label", "reason", "body", "text", "title"}
SEARCH_TOOLS = {"Grep", "Glob"}
SEGMENTS = re.compile(r"&&|\|\||[;|&\n]")
SHOW = re.compile(r"(?<![\w.-])show(?![\w-])", re.IGNORECASE)
FINAL = re.compile(r"(?<![a-z])final(?![a-z])", re.IGNORECASE)
# A10: the dashboard's text flag. Claude never passes it, so it never sees real complaint text there.
WITH_TEXT = re.compile(r"--with-text\b", re.IGNORECASE)
# V8: `voc review sheet` and `voc review import` in any form (voc, voc.exe, python -m voc.cli), and the
# functions that write or read a sheet. Checked after quotes, backticks and line continuations are taken out.
REVIEW_SHEETS = re.compile(r"(?<![\w-])voc(?:\.exe|\.cli)?\s+review\s+(?:sheet|import)\b"
                           r"|\b(?:write_sheet|sheet_rows|read_codes|import_codes)\b", re.IGNORECASE)
REVIEW_NOISE = re.compile(r"[\"'`]|\\\r?\n")
ASSIGNMENT = re.compile(r"^\w+=\S*$")
DRIVE = re.compile(r"^([a-z]):/")
# Checked on command text after lower-casing and turning backslashes into slashes.
SHELL_PATTERNS = (
    re.compile(r"(?:^|[^\w.])\.voc\b"),
    re.compile(r"\.duckdb\b"),
    re.compile(r"(?:^|[\s/\"'=])recordings/"),
    re.compile(r"voc_data_dir"),
    re.compile(r"voc_next_data_dir"),
    re.compile(r"voc_june_data_dir"),
    re.compile(r"ccdb_export"),
    # 4 November 2026: the CFPB's download paths, for the current bulk export (`/ccdb/`) and the narratives
    # archive (`/f/documents/CCDB_Export_...`, read from its FOIA page on 4 November). The export's own names are
    # checked by `_names_bulk_export`, and a run of `scripts/download.py` by `RUNS_DOWNLOAD`.
    re.compile(r"files\.consumerfinance\.gov/(?:ccdb|f/documents/ccdb)"),
    re.compile(r"(?:^|[\s/\"'=])\.env(?![\w.])"),  # the key file, not `.env.example`
    # The owner's encrypted Databricks token in `.voc`, found by a wildcard, and the calls that decrypt it.
    re.compile(r"\.dpapi\b|convertto-securestring|networkcredential|protecteddata|cryptunprotectdata"),
    # The repo's `data` folder (DuckDB file, write-ahead log, dbt output), named relative to the repo.
    re.compile(r"(?:^|[\s\"'=(])(?:\./)?data/"),
    re.compile(r"(?:^|[\s;&|(])(?:cd|ls|dir|gci|get-childitem|pushd|set-location|sl|tree|du|cat|type|gc|get-content"
               r"|head|tail|less|more|strings|find|grep|rg|select-string)\s+[\"']?(?:\./)?data[\"']?(?=\s|$|[;&|)])"),
)
DATA_FOLDER = "data"
DUCKDB_NAME = re.compile(r"\.duckdb(?:\.|$)")  # the DuckDB file and its `.wal` log
# The CFPB's current bulk export by its own names, `complaints.csv` and `complaints.csv.zip`, with a browser's copy
# number (`complaints (1).csv.zip`) and any further suffix (`.part`, `.gz`). The one name allowed is the synthetic
# fixture `tests/fixtures/dbt/complaints.csv` in this repo. A name with a word before it, such as
# `synthetic_complaints.csv`, is not matched, so a renamed copy slips past: the guard is best effort (review of #86).
BULK_EXPORT = re.compile(r"(?<![\w-])complaints(?: \(\d+\))?\.csv(?:\.[a-z0-9]+)*\b")
FIXTURE = "tests/fixtures/dbt/complaints.csv"
TOKEN_EDGE = re.compile(r"[\s\"'=(<>|;&]")
# A run of `scripts/download.py`, which fetches the bulk export. Naming it, as in `git diff`, stays allowed.
RUNS_DOWNLOAD = re.compile(r"(?:\bpython[\w.]*|\bpy|\buv\s+run(?:\s+--?[\w-]+(?:=\S+)?)*)\s+(?:-\S+\s+)*[\"']?"
                           r"(?:\./)?scripts/download\.py\b")
# July's folder, the next month's (add-on 1) and June's (spec 004, J6)
DATA_VARIABLES = ("VOC_DATA_DIR", "VOC_NEXT_DATA_DIR", "VOC_JUNE_DATA_DIR")
DENIED = "read guard: this names raw data, the DuckDB file, recordings, the ledger or the `.env` file."
# Spec 004, J14: the Databricks CLI as any word of a line (`env databricks`, `bash -c databricks`, `uv run
# databricks`), unless an earlier word is a command that only takes text, such as `git`, `gh` or `grep`. A path names
# the CLI only as the first word or as an `.exe`, so `ls dbt/databricks` stays allowed. The word after `--group` or
# `--with` names a package, not the CLI.
DATABRICKS_CLI = re.compile(r"^(?:databricks|dbsqlcli)(?:\.exe)?$")
TEXT_COMMANDS = re.compile(r"^(?:git|gh|grep|rg|echo|printf|select-string|sls|write-output|write-host)(?:\.exe)?$")
PACKAGE_FLAGS = {"--group", "--only-group", "--extra", "--with", "--package"}
# Its SDK and SQL connector, which sign in as the owner from the CLI's saved sign-in, and that file (review of #87).
DATABRICKS_SDK = re.compile(r"databricks\.sdk\b|\bworkspaceclient\b|\bfrom\s+databricks\s+import\s+sql\b"
                            r"|databricks\.sql\b|\.databrickscfg\b")
SAVED_SIGN_IN = ".databrickscfg"
RAW_VOLUME = "voc_raw"
DATABRICKS_DENIED = ("databricks guard: Claude never runs the Databricks CLI or SDK, reads its saved sign-in, or names "
                     "the volume `voc_raw` (spec 004, J14). Text that names them goes in a file.")
# Spec 004, J14: Claude's `gh` signs in as the owner, who approves the June run. Checked on command text after quotes
# are taken out, lower-casing and turning backslashes into slashes, so `gh.exe` by its full path is covered too.
GH = r"(?:^|[\s/&;|(])gh(?:\.exe)?\s+"
# Flags, each with or without a value, between `gh`, its group and its subcommand: `gh pr -R o/r merge 85`.
FLAGS = r"(?:-\S+(?:\s+(?!-)\S+)?\s+)*"
# An API path on a repo, so `docs/environments.md` or `scripts/rerun.py` is not taken for one (review of #87).
REPO = r"repos/[^/\s]+/[^/\s]+"


def _gh(*words):
    """`gh` and its words, with any flags before and between them."""
    return GH + FLAGS + (r"\s+" + FLAGS).join(words)


OWNER_ACTIONS = tuple(re.compile(pattern) for pattern in (
    _gh("run", r"view\b[^;&|\n]*\s--log"),  # a run's log, `--log` and `--log-failed`
    _gh("run", r"(?:download|rerun|cancel|delete)\b"),
    _gh("workflow", r"(?:run|enable|disable)\b"),
    _gh(r"secret\b"),
    _gh("variable", r"(?:set|delete)\b"),
    _gh("pr", r"merge\b"),
    _gh("alias", r"(?:set|import|delete)\b"),  # an alias could stand for any denied command
    _gh(r"(?:extension|extensions|ext)", r"(?:install|upgrade|create|exec)\b"),
    _gh("auth", r"(?:token|refresh|login|logout|switch)\b"),
    _gh("auth", r"status\b[^;&|\n]*\s-t\b"),
    r"--show-token\b",
    _gh("repo", r"(?:edit|delete|rename|archive|unarchive|sync|deploy-key|autolink)\b"),
    REPO + r"/actions/(?:runs|jobs)/\S*/logs\b",
    REPO + r"/actions/artifacts/\d+/\w+",  # an artifact's download
    REPO + r"/\S*dispatches\b",  # a workflow's and the repo's
    REPO + r"/actions/(?:runs|jobs)/\S*/(?:rerun(?:-failed-jobs)?|(?:force-)?cancel)\b",
    REPO + r"/actions/workflows/\S*/(?:enable|disable)\b",
    r"pending_deployments",
    REPO + r"/environments\b",
    REPO + r"/(?:\S*/)?secrets\b",
    REPO + r"/pulls/[^/\s]+/merge\b",
    REPO + r"/merges\b",
    REPO + r"/git/refs?\b",  # moving a branch, `main` included
    r"\b(?:mergepullrequest|enablepullrequestautomerge|approvedeployments|mergebranch|createcommitonbranch"
    r"|updaterefs?|createref|deleteref)\b",  # GraphQL
))
# `gh api` writes with a method other than GET, or with fields and no method, which gh sends as a POST. In GraphQL,
# a mutation, or a query read from a file, which the text check cannot see, is denied. Other reads stay allowed.
GH_API = re.compile(GH + FLAGS + r"api\b")
GRAPHQL = re.compile(r"\bgraphql\b")
GRAPHQL_WRITE = re.compile(r"\bmutation\b|=@|--input\b")
API_WRITE = re.compile(r"(?:-x|--method)[\s=]*(?:post|put|patch|delete)\b")
API_FIELDS = re.compile(r"(?:^|\s)(?:-f|--field|--raw-field|--input)(?=[\s=]|$)")
API_GET = re.compile(r"(?:-x|--method)[\s=]*get\b")
GITHUB_DENIED = ("github guard: only the owner reads Actions run logs and artifacts, starts, re-runs, cancels or "
                 "deletes a run, approves a deployment, uses the environments, secrets and variables APIs, writes "
                 "through the API, changes the repo's settings, reads the token, sets an alias or an extension, or "
                 "merges (spec 004, J14). Text that names them goes in a file.")


def _normal(text):
    return str(text).replace("\\", "/").lower().rstrip("/")


def _clean(path):
    """Absolute, with `..` resolved, in normal form. Also the resolved form, which expands links."""
    forms = {_normal(os.path.normpath(os.path.abspath(path)))}
    try:
        forms.add(_normal(Path(path).resolve()))
    except OSError:
        pass
    return forms


def _data_dirs(env, root):
    """Every raw data folder named for July, the next month or June, in the environment or in `.env`.

    `voc.env.settings` lets the environment win and, inside `.env`, the last line win. The guard
    protects every value it finds, so it covers the folder the command line reads whatever the order.
    The file is read as `utf-8-sig`, as the command line reads it, so a byte order mark changes nothing.
    """
    values = [env.get(name) for name in DATA_VARIABLES]
    env_file = Path(root) / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            key, sep, rest = line.strip().partition("=")
            if sep and key.strip() in DATA_VARIABLES:
                values.append(rest.strip().strip("'\""))
    return [value for value in values if value]


def _places(home, data_dirs):
    places = set(_clean(Path(home) / ".voc"))
    for data_dir in data_dirs:
        places |= _clean(data_dir)
    return places


def _inner_places(root):
    """The repo's `data` folder, which holds the DuckDB file, its write-ahead log and dbt's output.

    Reading in it is denied. Searching the repo is still allowed, because Grep and Glob skip
    git-ignored folders such as this one.
    """
    return set(_clean(Path(root) / DATA_FOLDER))


def _under(path, place):
    return path == place or path.startswith(place + "/")


def _protected_path(value, home, root, places, search, inner=frozenset()):
    text = str(value)
    if text.startswith("~"):
        text = str(home) + text[1:]
    path = Path(text) if Path(text).is_absolute() else Path(root) / text
    for normal in _clean(path):
        if any(_under(normal, p) for p in places | inner):
            return True
        if search and any(_under(p, normal) for p in places):
            return True  # the search would cover a protected place
        parts = normal.split("/")
        if (DUCKDB_NAME.search(parts[-1]) or "recordings" in parts or "ccdb_export" in normal
                or (BULK_EXPORT.fullmatch(parts[-1]) and normal not in _clean(Path(root) / FIXTURE))
                or parts[-1] == ".env"):
            return True
    return False


def _names_bulk_export(normal, root):
    """True if the command names the bulk export, other than the one synthetic fixture in this repo."""
    allowed = {FIXTURE, "./" + FIXTURE}
    for place in _clean(Path(root)):
        allowed |= {f"{form}/{FIXTURE}" for form in _shell_forms(place)}
    for match in BULK_EXPORT.finditer(normal):
        edge = max((m.end() for m in TOKEN_EDGE.finditer(normal, 0, match.start())), default=0)
        if match.group(0) != "complaints.csv" or normal[edge:match.end()] not in allowed:
            return True
    return False


def _shell_forms(place):
    """A protected folder as it can appear in a command: `c:/x/y` and the Git Bash form `/c/x/y`."""
    forms = {place}
    drive = DRIVE.match(place)
    if drive:
        forms.add(f"/{drive.group(1)}/{place[3:]}")
    return forms


def _protected_command(command, places, data_dirs, root):
    normal = _normal(command)
    if _names_bulk_export(normal, root) or RUNS_DOWNLOAD.search(normal):
        return True
    if any(form in normal for p in places for form in _shell_forms(p)):
        return True
    for data_dir in data_dirs:
        name = _normal(data_dir).split("/")[-1]
        if len(name) >= 6 and re.search(rf"(?:^|[\s/\"'=]){re.escape(name)}(?:[/\s\"']|$)", normal):
            return True
    return any(p.search(normal) for p in SHELL_PATTERNS)


def _runs_show(command):
    for segment in SEGMENTS.split(command):
        if not SHOW.search(segment):
            continue
        words = [w for w in segment.split() if not ASSIGNMENT.match(w)]
        if not words or words[0].lower() != "git":
            return True
    return False


def _runs_databricks(command):
    normal = _normal(REVIEW_NOISE.sub(" ", command))
    if RAW_VOLUME in normal or DATABRICKS_SDK.search(normal):
        return True
    for segment in SEGMENTS.split(normal):
        words = [w for w in segment.split() if not ASSIGNMENT.match(w)]
        for i, word in enumerate(words):
            name = word.split("/")[-1]
            if TEXT_COMMANDS.match(name):
                break
            if i and words[i - 1] in PACKAGE_FLAGS:
                continue
            if DATABRICKS_CLI.match(name) and (i == 0 or "/" not in word or name.endswith(".exe")):
                return True
    return False


def _uses_owner_actions(command):
    normal = _normal(REVIEW_NOISE.sub(" ", command))
    if any(p.search(normal) for p in OWNER_ACTIONS):
        return True
    for segment in SEGMENTS.split(normal):
        if not GH_API.search(segment):
            continue
        if GRAPHQL.search(segment):
            if GRAPHQL_WRITE.search(segment):
                return True
        elif API_WRITE.search(segment) or (API_FIELDS.search(segment) and not API_GET.search(segment)):
            return True
    return False


def _strings(value, key=None):
    """Every string in the tool input, with the name of the field it came from."""
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, key)


def decide(tool_name, tool_input, env, home, root):
    data_dirs = _data_dirs(env, root)
    places = _places(home, data_dirs)
    inner = _inner_places(root)
    command = tool_input.get("command")
    if isinstance(command, str):
        if _protected_command(command, places | inner, data_dirs, root):
            return ("deny", DENIED)
        if _runs_show(command):
            return ("deny", "read guard: only the owner runs `show`, in the owner's own terminal.")
        if _runs_databricks(command):
            return ("deny", DATABRICKS_DENIED)
        if _uses_owner_actions(command):
            return ("deny", GITHUB_DENIED)
        if WITH_TEXT.search(command):
            return ("deny", "text guard: only the owner passes --with-text, in the owner's own terminal (A10).")
        if REVIEW_SHEETS.search(REVIEW_NOISE.sub(" ", command)):
            return ("deny", "review guard: only the owner runs `voc review sheet` and `voc review import`, in the "
                            "owner's own terminal (V8).")
        if FINAL.search(command):
            return ("ask", "final guard: this command contains `final`. Only the owner decides a final run.")
    search = tool_name in SEARCH_TOOLS
    for key, value in _strings(tool_input):
        if key in NOT_PATHS or key == "command" or (key == "pattern" and tool_name != "Glob"):
            continue
        if value and _normal(value).split("/")[-1] == SAVED_SIGN_IN:
            return ("deny", DATABRICKS_DENIED)
        if value and _protected_path(value, home, root, places, search, inner):
            return ("deny", DENIED)
    return None


def _emit(decision):
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision[0],
            "permissionDecisionReason": decision[1],
        }}))


def main():
    try:
        # Claude Code sends UTF-8. Read bytes, so the system code page (cp932 here) never decodes it.
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        root = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or "."
        decision = decide(event.get("tool_name"), event.get("tool_input") or {},
                          env=os.environ, home=Path.home(), root=root)
    except Exception as err:  # fail closed
        print(f"read guard hook failed: {type(err).__name__}", file=sys.stderr)
        return 2
    _emit(decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
