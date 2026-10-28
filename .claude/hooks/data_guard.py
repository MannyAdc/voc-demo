"""Data guard (CLAUDE.md, "Hooks"). PreToolUse on Write, Edit, MultiEdit and NotebookEdit.

Blocks a `.env` file, content that looks like an API key, and a file that
would hold raw CFPB rows (the CFPB header with a non-`SYN-` complaint ID).
An edit is checked on the file as it would be after the edit. Edits to the
Claude settings (project and user level), the hook scripts and
`src/voc/repo_checks.py` (which the guards import) ask the owner first.

Not built: the check for long runs of text copied from a sampled narrative
(cut list item 4, decided at the Wednesday 12:00 checkpoint).
"""
import json
import os
import re
import sys
from pathlib import Path

ANTHROPIC_KEY = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")
# In env-style files, any long value for a name like *_KEY, *_TOKEN or *_SECRET.
ENV_VALUE = re.compile(r"(?im)^\s*[A-Z0-9_]*(?:KEY|TOKEN|SECRET)[A-Z0-9_]*\s*=\s*['\"]?[A-Za-z0-9_\-./+]{16,}")
# The guards import src/voc/repo_checks.py, so a change there changes the guards.
ASK_FILES = {".claude/settings.json", ".claude/settings.local.json", "src/voc/repo_checks.py"}
ASK_FOLDERS = (".claude/hooks/", ".githooks/")
HOME_ASK_FILES = {".claude/settings.json", ".claude/settings.local.json"}


def _relative(path, root):
    path = Path(path) if Path(path).is_absolute() else Path(root) / path
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix().lower()
    except ValueError:
        return path.as_posix().lower()


def _is_env_file(name):
    name = name.lower()
    return name != ".env.example" and (name == ".env" or name.startswith(".env.") or name.endswith(".env"))


def _apply(text, old, new, replace_all=False):
    if old and old in text:
        return text.replace(old, new) if replace_all else text.replace(old, new, 1)
    return text + "\n" + new


def _result_text(tool_name, tool_input, path):
    """The new text this call adds, and the whole file as it would be after the call."""
    if tool_name == "Write":
        content = tool_input.get("content") or ""
        return content, content
    if tool_name == "NotebookEdit":
        source = tool_input.get("new_source") or ""
        return source, source
    current = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    edits = tool_input.get("edits") or [tool_input]
    added = []
    for edit in edits:
        new = edit.get("new_string") or ""
        added.append(new)
        current = _apply(current, edit.get("old_string") or "", new, bool(edit.get("replace_all")))
    return "\n".join(added), current


def decide(tool_name, tool_input, root, home=None):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from voc.repo_checks import has_raw_cfpb_rows

    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    path = Path(raw_path) if Path(raw_path).is_absolute() else Path(root) / raw_path
    name = path.name
    if _is_env_file(name):
        return ("deny", "data guard: `.env` files are never written by Claude. The owner edits them.")
    added, after = _result_text(tool_name, tool_input, path)
    if ANTHROPIC_KEY.search(added) or ANTHROPIC_KEY.search(after):
        return ("deny", "data guard: the content looks like an API key. Keys live only in the environment.")
    if name.lower() == ".env.example" and ENV_VALUE.search(after):
        return ("deny", "data guard: `.env.example` must not hold a key-like value.")
    if has_raw_cfpb_rows(after):
        return ("deny", "data guard: the file would hold raw CFPB rows. Fixtures use only `SYN-` IDs.")
    relative = _relative(path, root)
    in_home = _relative(path, Path.home() if home is None else home)
    if relative in ASK_FILES or relative.startswith(ASK_FOLDERS) or in_home in HOME_ASK_FILES:
        return ("ask", "data guard: this changes the Claude settings, a hook script or the checks they use, "
                       "so the owner decides.")
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
        decision = decide(event.get("tool_name"), event.get("tool_input") or {}, root=root)
    except Exception as err:  # fail closed
        print(f"data guard hook failed: {type(err).__name__}", file=sys.stderr)
        return 2
    _emit(decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
