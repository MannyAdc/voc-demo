"""V8: the review folder, where the owner's review sheets live (specs/003-validation-review/spec.md).

A sheet holds complaint text, so it is written only inside the review folder in the home folder's `.voc`,
which the read guard blocks for Claude. Each sheet has one fixed path. Errors name no path.
"""
from pathlib import Path

from voc import budget

SHEETS = {"v2": "v2_sheet.csv", "v3": "v3_sheet.csv", "v5": "v5_sheet.csv"}


class ReviewError(ValueError):
    """An error whose message is ours, so it is safe to print (it never holds a path or data)."""


def review_dir():
    return budget.voc_home() / "review"


def inside_review_dir(path):
    """The resolved path, if it is inside the review folder. Anything else is refused."""
    folder = review_dir().resolve()
    resolved = Path(path).resolve()
    if resolved == folder or not resolved.is_relative_to(folder):
        raise ReviewError("a review sheet must be inside the review folder")
    return resolved


def sheet_path(piece):
    """The one path of a piece's sheet. Only V2, V3 and V5 have a sheet."""
    if piece not in SHEETS:
        raise ReviewError("there is a review sheet only for v2, v3 and v5")
    return review_dir() / SHEETS[piece]
