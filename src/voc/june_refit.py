"""Spec 004, J7 and J11: Job B's refit of TF-IDF + LR, checked against the committed July development labels before it
labels June (pull request 6b, part 2).

It runs the laptop's own path inside Databricks, so the refit is the laptop's: the pinned July export in the volume
is checked against its pin, loaded whole by B16's loader into a DuckDB file in a temporary folder, as on the laptop,
and only the training and development rows are selected, by their IDs, each checked against its list's content hash.
The test rows are loaded into that file with the rest, but no test row is ever selected, labelled or scored, and
the file is deleted with its folder (J2, review of #109, minor 1). TF-IDF + LR is fitted on the training rows
with the frozen settings, and must give every committed development label in `results/eval/v1_dev.csv` before
Job B goes on.

One setting is June's own: the solver's stopping point. Logistic regression is fitted step by step, and the solver
stops when a step changes the model by less than `tol`. At scikit-learn's default, 1e-4, the laptop's solver stops
after 87 steps, short of the settled answer. Databricks runs on ARM chips and the laptop on x86, and their last
digits differ, so the two can stop at slightly different points. In round 4 of the dry run (11 November), one
of the 370 development labels came out different in Databricks. Run to the strict stopping point of 1e-8, the
laptop's solver takes 278 steps and gives the same 370 labels, so the check stays exact (owner decision,
12 November). A refit that has not settled within its step limit, `max_iter`, is refused.

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
REFIT_TOL = 1e-8  # the strict stopping point, June's refit only (J7, owner decision of 12 November)


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


def _inputs(root):
    """The committed files the refit reads first: the pin, the labels, the lists, the settings and the development
    labels. Review of #109, nit 4: any failure to read them is refused with its type only. The lists' content
    hashes are read later, inside `_rows`, behind `_step`'s fixed text (second review of #109, nit 3)."""
    try:
        pin = load_pins(root / "config" / "data_files.toml")[MONTH]
        labels = [label.name for label in load_labels(root / "config" / "labels.toml")]
        lists = read_splits(root / "splits")
        settings = load_tfidf_config(root / "config" / "tfidf.toml")
        return (pin, labels, lists, settings, _committed(root)), None
    except Exception as err:  # noqa: BLE001, read by its type only, outside the except block
        failure = type(err).__name__
    raise RefitError(f"the refit's committed files could not be read: {failure}")


def _committed(root):
    with open(Path(root) / DEV_RESULTS, encoding="utf-8", newline="") as f:
        return {row["complaint_id"]: row["tfidf_label"] for row in csv.DictReader(f)}


def refit(root, export_path, work_dir):
    """The refit model, once it gives every committed July development label. `work_dir` holds the DuckDB file."""
    root = Path(root)
    (pin, labels, lists, settings, committed), _ = _inputs(root)
    _step("the July export could not be checked", verify, export_path, pin)
    db_path = Path(work_dir) / "july.duckdb"
    _step("the July export could not be loaded", load_month, db_path, export_path, MONTH, labels)
    splits = root / "splits"
    train = _step("the July training rows could not be read", _rows, db_path, splits, MONTH, "train",
                  set(lists["train"]))
    dev = _step("the July development rows could not be read", _rows, db_path, splits, MONTH, "dev",
                set(lists["dev"]))
    model = _step("TF-IDF + LR could not be fitted", fit_tfidf,
                  [(r.complaint_id, "train", r.narrative, r.product) for r in train], settings, REFIT_TOL)
    if max(model.classifier.n_iter_) >= settings["max_iter"]:
        raise RefitError(f"the refit TF-IDF + LR did not settle within its {settings['max_iter']} solver steps")
    predicted = _step("TF-IDF + LR could not label the development rows", predict_tfidf, model,
                      [r.narrative for r in dev])
    if set(committed) != {r.complaint_id for r in dev}:
        raise RefitError("the committed July development labels are not the development list's")
    wrong = sum(committed[r.complaint_id] != label for r, (label, _) in zip(dev, predicted))
    if wrong:
        raise RefitError(f"the refit TF-IDF + LR gives {wrong} of {len(dev)} July development labels other than "
                         "the committed ones")
    return model
