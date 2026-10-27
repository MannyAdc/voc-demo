"""Read guard (B21) and final guard (B17). PreToolUse on every tool.

Denies any tool call that names a protected place: the raw data folder
(`VOC_DATA_DIR`, from the environment or the local `.env`), the home folder
`.voc` (ledger, recordings and the home test log), any `.duckdb` file, a
`recordings` folder, a CFPB export file, or the `.env` file that holds the
API key (`.env.example` is allowed). Every string in the tool input is
checked as a path, except text the tool writes (such as `content`), after
`..` is resolved. A search of a folder that holds the data folder or `.voc`
is denied too.

Any tool input with a `command` field (Bash, PowerShell, Monitor) is checked
as a shell command. That is a text check, so it also covers `cat`,
`Get-Content` and the like. `show` and `dbt show` are denied outright: only
the owner runs `show`, in the owner's own terminal. `git show` is allowed.
A command containing the word `final` asks the owner.
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
ASSIGNMENT = re.compile(r"^\w+=\S*$")
DRIVE = re.compile(r"^([a-z]):/")
# Checked on command text after lower-casing and turning backslashes into slashes.
SHELL_PATTERNS = (
    re.compile(r"(?:^|[^\w.])\.voc\b"),
    re.compile(r"\.duckdb\b"),
    re.compile(r"(?:^|[\s/\"'=])recordings/"),
    re.compile(r"voc_data_dir"),
    re.compile(r"ccdb_export"),
    re.compile(r"(?:^|[\s/\"'=])\.env(?![\w.])"),  # the key file, not `.env.example`
)
DENIED = "read guard: this names raw data, the DuckDB file, recordings, the ledger or the `.env` file."


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


def _data_dir(env, root):
    value = env.get("VOC_DATA_DIR")
    env_file = Path(root) / ".env"
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, rest = line.strip().partition("=")
            if sep and key.strip() == "VOC_DATA_DIR":
                value = rest.strip().strip("'\"")
    return value or None


def _places(home, data_dir):
    places = set(_clean(Path(home) / ".voc"))
    if data_dir:
        places |= _clean(data_dir)
    return places


def _under(path, place):
    return path == place or path.startswith(place + "/")


def _protected_path(value, home, root, places, search):
    text = str(value)
    if text.startswith("~"):
        text = str(home) + text[1:]
    path = Path(text) if Path(text).is_absolute() else Path(root) / text
    for normal in _clean(path):
        if any(_under(normal, p) for p in places):
            return True
        if search and any(_under(p, normal) for p in places):
            return True  # the search would cover a protected place
        parts = normal.split("/")
        if normal.endswith(".duckdb") or "recordings" in parts or "ccdb_export" in normal or parts[-1] == ".env":
            return True
    return False


def _shell_forms(place):
    """A protected folder as it can appear in a command: `c:/x/y` and the Git Bash form `/c/x/y`."""
    forms = {place}
    drive = DRIVE.match(place)
    if drive:
        forms.add(f"/{drive.group(1)}/{place[3:]}")
    return forms


def _protected_command(command, places, data_dir):
    normal = _normal(command)
    if any(form in normal for p in places for form in _shell_forms(p)):
        return True
    if data_dir:
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
    data_dir = _data_dir(env, root)
    places = _places(home, data_dir)
    command = tool_input.get("command")
    if isinstance(command, str):
        if _protected_command(command, places, data_dir):
            return ("deny", DENIED)
        if _runs_show(command):
            return ("deny", "read guard: only the owner runs `show`, in the owner's own terminal.")
        if FINAL.search(command):
            return ("ask", "final guard: this command contains `final`. Only the owner decides a final run.")
    search = tool_name in SEARCH_TOOLS
    for key, value in _strings(tool_input):
        if key in NOT_PATHS or key == "command" or (key == "pattern" and tool_name != "Glob"):
            continue
        if value and _protected_path(value, home, root, places, search):
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
        event = json.loads(sys.stdin.read())
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
