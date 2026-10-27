#!/bin/sh
# Runs one hook script with the project's Python.
# Any failure exits 2, so Claude Code blocks the action instead of letting it through.
dir=$(dirname "$0")
root="$dir/../.."
for py in "$root/.venv/Scripts/python.exe" "$root/.venv/bin/python"; do
  if [ -x "$py" ]; then
    "$py" "$dir/$1"
    [ $? -eq 0 ] && exit 0
    exit 2
  fi
done
echo "hook failed: no project Python in .venv, run uv sync" >&2
exit 2
