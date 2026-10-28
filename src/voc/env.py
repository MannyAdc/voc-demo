"""Read the git-ignored `.env` file. Values are never printed."""
from pathlib import Path


def load_dotenv(path):
    """KEY=VALUE pairs from a `.env` file, or an empty dict if there is none."""
    path = Path(path)
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip().strip("'\"")
    return values


def settings(env, root):
    """The environment, with the local `.env` filling any gap. The real environment wins."""
    return {**load_dotenv(Path(root) / ".env"), **env}
