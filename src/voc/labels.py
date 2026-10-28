"""B24: the frozen label set, read from `config/labels.toml` by every part that needs it."""
import tomllib
from dataclasses import dataclass


@dataclass(frozen=True)
class Label:
    name: str
    covers: tuple


def load_labels(path):
    with open(path, "rb") as f:
        entries = tomllib.load(f)["label"]
    labels, seen = [], set()
    for entry in entries:
        if entry["name"] in seen:
            raise ValueError(f"the label {entry['name']!r} is listed more than once")
        seen.add(entry["name"])
        labels.append(Label(entry["name"], tuple(entry["covers"])))
    return labels
