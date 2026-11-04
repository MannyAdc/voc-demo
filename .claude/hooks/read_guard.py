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
is denied too.

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

Spec 004, J14: a command that runs the Databricks CLI or names the volume
`voc_raw` is denied. Claude's `gh` signs in as the owner, who approves the
June run, so a command that reads an Actions run log, starts, re-runs or
cancels a workflow, approves a deployment, uses the environments or secrets
APIs, or merges a pull request, by `gh` or by the API, is denied too.
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
# Spec 004, J14: the Databricks CLI as the command of any part of a line, and the raw volume `voc_raw` by name.
DATABRICKS_CLI = re.compile(r"^(?:databricks|dbsqlcli)(?:\.exe)?$")
RAW_VOLUME = "voc_raw"
# Spec 004, J14: Claude's `gh` signs in as the owner, who approves the June run. Checked on command text after quotes
# are taken out, lower-casing and turning backslashes into slashes, so `gh.exe` by its full path is covered too.
GH = r"(?:^|[\s/&;|(])gh(?:\.exe)?\s+"
OWNER_ACTIONS = tuple(re.compile(pattern) for pattern in (
    GH + r"run\s+view\b[^;&|\n]*\s--log",  # a run's log, `--log` and `--log-failed`
    GH + r"run\s+(?:download|rerun|cancel)\b",
    GH + r"workflow\s+(?:run|enable|disable)\b",
    GH + r"secret\b",
    GH + r"pr\s+merge\b",
    r"/actions/(?:runs|jobs)/\S*/logs\b",
    r"/dispatches\b",  # a workflow's and the repo's
    r"/rerun(?:-failed-jobs)?\b",
    r"/(?:force-)?cancel\b",
    r"pending_deployments",
    r"/environments\b",
    r"/secrets\b",
    r"/pulls/[^/\s]+/merge\b",
    r"/merges\b",
    r"\b(?:mergepullrequest|enablepullrequestautomerge|approvedeployments)\b",  # GraphQL
))


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
    """Every raw data folder named for July or the next month, in the environment or in `.env`.

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
    if RAW_VOLUME in normal:
        return True
    for segment in SEGMENTS.split(normal):
        words = [w for w in segment.split() if not ASSIGNMENT.match(w)]
        if words and DATABRICKS_CLI.match(words[0].split("/")[-1]):
            return True
    return False


def _uses_owner_actions(command):
    normal = _normal(REVIEW_NOISE.sub(" ", command))
    return any(p.search(normal) for p in OWNER_ACTIONS)


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
            return ("deny", "databricks guard: Claude never runs the Databricks CLI or names the volume `voc_raw` "
                            "(spec 004, J14).")
        if _uses_owner_actions(command):
            return ("deny", "github guard: only the owner reads Actions run logs, starts, re-runs or cancels a "
                            "workflow, approves a deployment, uses the environments and secrets APIs, or merges "
                            "(spec 004, J14).")
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
