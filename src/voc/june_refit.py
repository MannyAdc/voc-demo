"""Spec 004, J7 and J11: Job B's refit of TF-IDF + LR, checked against the committed July development labels before it
labels June (pull request 6b, part 2).

It runs the laptop's own path inside Databricks, so the refit is the laptop's: the pinned July export in the volume
is checked against its pin, loaded whole by B16's loader into a DuckDB file in a temporary folder, and only the
training and development rows are selected, by their IDs, each checked against its list's content hash (J2: no test
row is read). TF-IDF + LR is fitted on the training rows with the frozen settings, and must give every committed
development label in `results/eval/v1_dev.csv` before Job B goes on.

B21 and J5: nothing here prints. Every refusal holds fixed text, IDs and counts only, and carries no earlier
exception. An error from DuckDB or scikit-learn is given by its type only, since its text could quote a row.
"""
import csv
from pathlib import Path

from voc.baselines import fit_tfidf, load_tfidf_config, predict_tfidf
from voc.data import SampleMismatch, read_splits
from voc.datafile import DataFileError, load_pins, verify
from voc.evaluate import _rows
from voc.labels import load_labels
from voc.load import load_month

MONTH = "july_2026"
DEV_RESULTS = Path("results") / "eval" / "v1_dev.csv"


class RefitError(ValueError):
    """A refusal with fixed text, IDs and counts only (B21, J5)."""


def _step(what, function, *args):
    """Runs one step. The repo's own refusals keep their fixed text, and any other error gives its type only."""
    try:
        return function(*args)
    except (DataFileError, SampleMismatch) as err:
        message = str(err)
    except Exception as err:  # noqa: BLE001, read by its type only, outside the except block
        message = f"{what}: {type(err).__name__}"
    raise RefitError(message)


def _committed(root):
    with open(Path(root) / DEV_RESULTS, encoding="utf-8", newline="") as f:
        return {row["complaint_id"]: row["tfidf_label"] for row in csv.DictReader(f)}


def refit(root, export_path, work_dir):
    """The refit model, once it gives every committed July development label. `work_dir` holds the DuckDB file."""
    root = Path(root)
    pin = load_pins(root / "config" / "data_files.toml")[MONTH]
    _step("the July export could not be checked", verify, export_path, pin)
    labels = [label.name for label in load_labels(root / "config" / "labels.toml")]
    db_path = Path(work_dir) / "july.duckdb"
    _step("the July export could not be loaded", load_month, db_path, export_path, MONTH, labels)
    splits = root / "splits"
    lists = read_splits(splits)
    train = _step("the July training rows could not be read", _rows, db_path, splits, MONTH, "train",
                  set(lists["train"]))
    dev = _step("the July development rows could not be read", _rows, db_path, splits, MONTH, "dev",
                set(lists["dev"]))
    settings = load_tfidf_config(root / "config" / "tfidf.toml")
    model = _step("TF-IDF + LR could not be fitted", fit_tfidf,
                  [(r.complaint_id, "train", r.narrative, r.product) for r in train], settings)
    predicted = _step("TF-IDF + LR could not label the development rows", predict_tfidf, model,
                      [r.narrative for r in dev])
    committed = _committed(root)
    if set(committed) != {r.complaint_id for r in dev}:
        raise RefitError("the committed July development labels are not the development list's")
    wrong = sum(committed[r.complaint_id] != label for r, (label, _) in zip(dev, predicted))
    if wrong:
        raise RefitError(f"the refit TF-IDF + LR gives {wrong} of {len(dev)} July development labels other than "
                         "the committed ones")
    return model
