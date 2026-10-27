"""Read guard (B21) and final guard (B17). PreToolUse on every tool.

Denies any tool call that names a protected place: the raw data folder
(`VOC_DATA_DIR`, from the environment or the local `.env`), the home folder
`.voc` (ledger, recordings and the home test log), any `.duckdb` file, a
`recordings` folder, a CFPB export file, or the `.env` file that holds the
API key (`.env.example` is allowed). For shell commands this is a
text check, so it also covers `cat`, `Get-Content` and the like.

Denies `show` and `dbt show` outright: only the owner runs `show`, in the
owner's own terminal. `git show` is allowed.

Asks the owner before any shell command containing the word `final`.
"""
import json
import os
import re
import sys
from pathlib import Path

SHELL_TOOLS = {"Bash", "PowerShell"}
PATH_FIELDS = ("file_path", "notebook_path", "path", "glob")
SEGMENTS = re.compile(r"&&|\|\||[;|\n]")
SHOW = re.compile(r"(?<![\w.-])show(?![\w-])", re.IGNORECASE)
FINAL = re.compile(r"(?<![a-z])final(?![a-z])", re.IGNORECASE)
ASSIGNMENT = re.compile(r"^\w+=\S*$")
# Checked on command text after lower-casing and turning backslashes into slashes.
SHELL_PATTERNS = (
    re.compile(r"/\.voc(?:[/\"'\s]|$)"),
    re.compile(r"\.duckdb\b"),
    re.compile(r"(?:^|[\s/\"'=])recordings/"),
    re.compile(r"voc_data_dir"),
    re.compile(r"ccdb_export"),
    re.compile(r"(?:^|[\s/\"'=])\.env(?![\w.])"),  # the key file, not `.env.example`
)


def _normal(text):
    return str(text).replace("\\", "/").lower().rstrip("/")


def _data_dir(env, root):
    value = env.get("VOC_DATA_DIR")
    env_file = Path(root) / ".env"
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, rest = line.strip().partition("=")
            if sep and key.strip() == "VOC_DATA_DIR":
                value = rest.strip().strip("'\"")
    return _normal(value) if value else None


def _protected_path(value, home, root, data_dir):
    text = str(value)
    if text.startswith("~"):
        text = str(home) + text[1:]
    path = Path(text) if Path(text).is_absolute() else Path(root) / text
    normal = _normal(path)
    under = [_normal(Path(home) / ".voc")] + ([data_dir] if data_dir else [])
    if any(normal == p or normal.startswith(p + "/") for p in under):
        return True
    parts = normal.split("/")
    return (normal.endswith(".duckdb") or "recordings" in parts or "ccdb_export" in normal
            or parts[-1] == ".env")


def _protected_command(command, home, data_dir):
    normal = _normal(command)
    if data_dir and data_dir in normal:
        return True
    if _normal(Path(home) / ".voc") in normal:
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


def decide(tool_name, tool_input, env, home, root):
    data_dir = _data_dir(env, root)
    if tool_name in SHELL_TOOLS:
        command = tool_input.get("command") or ""
        if _protected_command(command, home, data_dir):
            return ("deny", "read guard: this names raw data, the DuckDB file, recordings or the ledger.")
        if _runs_show(command):
            return ("deny", "read guard: only the owner runs `show`, in the owner's own terminal.")
        if FINAL.search(command):
            return ("ask", "final guard: this command contains `final`. Only the owner decides a final run.")
        return None
    for field in PATH_FIELDS:
        value = tool_input.get(field)
        if value and _protected_path(value, home, root, data_dir):
            return ("deny", "read guard: this names raw data, the DuckDB file, recordings or the ledger.")
    if tool_name == "Glob" and tool_input.get("pattern"):
        if _protected_path(tool_input["pattern"], home, root, data_dir):
            return ("deny", "read guard: this names raw data, the DuckDB file, recordings or the ledger.")
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
