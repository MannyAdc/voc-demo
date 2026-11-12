"""Spec 004, J7 and J11: Job B's refit of TF-IDF + LR, checked against the committed July development labels before it
labels June (pull request 6b, part 2).

It runs the laptop's own path inside Databricks, so the refit is the laptop's: the pinned July export in the volume
is checked against its pin, loaded whole by B16's loader into a DuckDB file in a temporary folder, as on the laptop,
and only the training and development rows are selected, by their IDs, each checked against its list's content hash.
The test rows are loaded into that file with the rest, but no test row is ever selected, labelled or scored, and
the file is deleted with its folder (J2, review of #109, minor 1). TF-IDF + LR is fitted on the training rows
with the frozen settings, and must give every committed development label in `results/eval/v1_dev.csv` before
Job B goes on.

The vocabulary is the laptop's own (rounds 4 and 5 of the dry run, owner decision of 12 November). TF-IDF keeps the
`max_features` most used terms. On July's training rows, 11,379 terms tie at the cut, with 4 uses each, and 1,917
of them fit. scikit-learn picks them with numpy's `argsort`, which leaves equal values in an order that differs
between the laptop's x86 chip and Databricks' ARM chips. Other picks change 0 to 2 development labels, and in rounds
4 and 5 Databricks gave 1 of the 370 labels other than the committed one. So the laptop's pick is pinned in
`config/june_refit_vocabulary.json`: how many terms are above the cut and at it, the positions of the tied terms it
kept, in alphabetical order, and a hash of the whole vocabulary. The file names no term. The refit counts the terms
again, takes every term above the cut and the tied terms at those positions, and refuses unless the counts and the
hash are the pin's. `scripts/june_refit_vocabulary.py` writes the pin on the laptop.

One setting is June's own: the solver's stopping point. Logistic regression is fitted step by step. Each step
makes the model a little less wrong on the training rows, and the solver (L-BFGS) stops once the error is almost
flat, when its steepest slope left is below `tol` (scikit-learn passes `tol` to scipy as `gtol`). It also stops,
with no warning, once a step barely lowers the error (scipy's `ftol`, which scikit-learn fixes). At
scikit-learn's default, 1e-4, the laptop's solver stops after 87 steps, short of the settled answer. June's refit
runs to 1e-8, 291 steps on the laptop, and gives the same 370 labels (owner decision, 12 November). Round 5 showed
that the stopping point was not the cause of round 4's different label: the vocabulary was. The strict stopping
point stays, so both chips settle (owner decision, 12 November). A refit that has not settled is refused: one whose
solver used all of `max_iter`, or warned that it stopped early (review of #121).

B21 and J5: nothing here prints. Every refusal holds fixed text, IDs and counts only, and carries no earlier
exception. An error from DuckDB or scikit-learn is given by its type only, since its text could quote a row.
"""
import csv
import hashlib
import json
import warnings
from pathlib import Path

from voc.baselines import cut_text, fit_tfidf, load_tfidf_config, predict_tfidf
from voc.data import SampleMismatch, read_splits
from voc.datafile import DataFileError, load_pins, verify
from voc.evaluate import _rows
from voc.labels import load_labels
from voc.load import load_month

MONTH = "july_2026"
DEV_RESULTS = Path("results") / "eval" / "v1_dev.csv"
REFIT_TOL = 1e-8  # the strict stopping point, June's refit only (J7, owner decision of 12 November)
VOCABULARY_PIN = Path("config") / "june_refit_vocabulary.json"
PIN_NOTE = ("TF-IDF's vocabulary for June's refit, from the laptop's fit on July's training rows (spec 004, J7). It "
            "holds counts, the positions of the tied terms kept, in alphabetical order, and a hash. It names no term.")
PIN_KEYS = ("note", "month", "max_features", "count_at_cut", "terms_above", "terms_tied", "kept_tied_positions",
            "vocabulary_sha256")


class RefitError(ValueError):
    """A refusal with fixed text, IDs and counts only (B21, J5)."""


def _step(what, function, *args):
    """Runs one step. The repo's own refusals keep their fixed text, and any other error gives its type only."""
    try:
        return function(*args)
    except (DataFileError, SampleMismatch, RefitError) as err:
        message = str(err)
    except Exception as err:  # noqa: BLE001, read by its type only, outside the except block
        message = f"{what}: {type(err).__name__}"
    raise RefitError(message)


def _inputs(root, with_vocabulary=True):
    """The committed files the refit reads first: the pin, the labels, the lists, the settings, the development
    labels and the vocabulary pin. Review of #109, nit 4: any failure to read them is refused with its type only.
    The lists' content hashes are read later, inside `_rows`, behind `_step`'s fixed text (second review of #109,
    nit 3). Only the laptop's script that writes the vocabulary pin reads them without it."""
    try:
        pin = load_pins(root / "config" / "data_files.toml")[MONTH]
        labels = [label.name for label in load_labels(root / "config" / "labels.toml")]
        lists = read_splits(root / "splits")
        settings = load_tfidf_config(root / "config" / "tfidf.toml")
        vocabulary = _read_pin(root) if with_vocabulary else None
        return (pin, labels, lists, settings, _committed(root), vocabulary), None
    except Exception as err:  # noqa: BLE001, read by its type only, outside the except block
        failure = type(err).__name__
    raise RefitError(f"the refit's committed files could not be read: {failure}")


def _committed(root):
    with open(Path(root) / DEV_RESULTS, encoding="utf-8", newline="") as f:
        return {row["complaint_id"]: row["tfidf_label"] for row in csv.DictReader(f)}


def _read_pin(root):
    """The vocabulary pin, with its keys and its positions checked: whole numbers, in order, each once."""
    pin = json.loads((Path(root) / VOCABULARY_PIN).read_text(encoding="utf-8"))
    positions = pin["kept_tied_positions"]
    if (set(pin) != set(PIN_KEYS) or not all(type(p) is int for p in positions)
            or positions != sorted(set(positions)) or (positions and not 0 <= positions[0] <= positions[-1]
                                                       < pin["terms_tied"])):
        raise ValueError("the vocabulary pin's keys or positions")
    return pin


def _term_counts(texts, settings):
    """Every term after `min_df`, in alphabetical order, with its total uses, as scikit-learn counts them before it
    cuts to `max_features`."""
    from sklearn.feature_extraction.text import CountVectorizer

    counter = CountVectorizer(ngram_range=(1, settings["ngram_max"]), min_df=settings["min_df"],
                              lowercase=settings["lowercase"], token_pattern=settings["token_pattern"])
    totals = counter.fit_transform([cut_text(t)[0] for t in texts]).sum(axis=0).A1
    return list(counter.get_feature_names_out()), [int(n) for n in totals]


def _split(terms, totals, cut):
    return [t for t, n in zip(terms, totals) if n > cut], [t for t, n in zip(terms, totals) if n == cut]


def _sha256(vocabulary):
    return hashlib.sha256("\n".join(sorted(vocabulary)).encode("utf-8")).hexdigest()


def vocabulary_pin(texts, settings):
    """The laptop's side: the pin of the vocabulary that scikit-learn's own TF-IDF keeps on this machine."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    chosen = set(TfidfVectorizer(ngram_range=(1, settings["ngram_max"]), min_df=settings["min_df"],
                                 max_features=settings["max_features"], sublinear_tf=settings["sublinear_tf"],
                                 lowercase=settings["lowercase"], token_pattern=settings["token_pattern"]
                                 ).fit([cut_text(t)[0] for t in texts]).vocabulary_)
    terms, totals = _term_counts(texts, settings)
    uses = dict(zip(terms, totals))
    cut = min(uses[t] for t in chosen)
    above, tied = _split(terms, totals, cut)
    positions = [i for i, t in enumerate(tied) if t in chosen]
    if not set(above) <= chosen or len(above) + len(positions) != len(chosen):
        raise RefitError("the laptop's vocabulary is not every term above its cut and some at it")
    return {"note": PIN_NOTE, "month": MONTH, "max_features": settings["max_features"], "count_at_cut": cut,
            "terms_above": len(above), "terms_tied": len(tied), "kept_tied_positions": positions,
            "vocabulary_sha256": _sha256(chosen)}


def pinned_vocabulary(texts, settings, pin):
    """The cloud's side: every term above the pin's cut and the tied terms at its positions, once the counts and the
    hash are the pin's."""
    if pin["max_features"] != settings["max_features"]:
        raise RefitError(f"the vocabulary pin is for max_features {pin['max_features']}, not the settings' "
                         f"{settings['max_features']}")
    terms, totals = _term_counts(texts, settings)
    above, tied = _split(terms, totals, pin["count_at_cut"])
    if (len(above), len(tied)) != (pin["terms_above"], pin["terms_tied"]):
        raise RefitError(f"the July training rows give {len(above)} terms above the vocabulary's cut and {len(tied)} "
                         f"at it, not the pin's {pin['terms_above']} and {pin['terms_tied']}")
    vocabulary = sorted(above + [tied[i] for i in pin["kept_tied_positions"]])
    if _sha256(vocabulary) != pin["vocabulary_sha256"]:
        raise RefitError("the refit's vocabulary is not the pinned one: its SHA-256 differs")
    return vocabulary


def _july_rows(root, export_path, work_dir, inputs):
    """The July training and development rows, from the export checked against its pin."""
    pin, labels, lists = inputs[0], inputs[1], inputs[2]
    _step("the July export could not be checked", verify, export_path, pin)
    db_path = Path(work_dir) / "july.duckdb"
    _step("the July export could not be loaded", load_month, db_path, export_path, MONTH, labels)
    splits = root / "splits"
    train = _step("the July training rows could not be read", _rows, db_path, splits, MONTH, "train",
                  set(lists["train"]))
    dev = _step("the July development rows could not be read", _rows, db_path, splits, MONTH, "dev",
                set(lists["dev"]))
    return train, dev


def write_vocabulary_pin(root, export_path, work_dir):
    """The laptop only: writes the vocabulary pin from July's training rows, and returns it."""
    root = Path(root)
    inputs, _ = _inputs(root, with_vocabulary=False)
    train, _ = _july_rows(root, export_path, work_dir, inputs)
    pin = _step("the vocabulary pin could not be made", vocabulary_pin, [r.narrative for r in train], inputs[3])
    (root / VOCABULARY_PIN).write_bytes((json.dumps(pin, indent=1) + "\n").encode("utf-8"))
    return pin


def refit(root, export_path, work_dir):
    """The refit model, once it gives every committed July development label. `work_dir` holds the DuckDB file."""
    root = Path(root)
    inputs, _ = _inputs(root)
    _, _, _, settings, committed, pin = inputs
    train, dev = _july_rows(root, export_path, work_dir, inputs)
    texts = [r.narrative for r in train]
    vocabulary = _step("the refit's vocabulary could not be made", pinned_vocabulary, texts, settings, pin)
    with warnings.catch_warnings(record=True) as warned:  # recorded, so nothing prints (B21)
        warnings.simplefilter("always")
        model = _step("TF-IDF + LR could not be fitted", fit_tfidf,
                      [(r.complaint_id, "train", r.narrative, r.product) for r in train], settings, REFIT_TOL,
                      vocabulary)
    if max(model.classifier.n_iter_) >= settings["max_iter"]:
        raise RefitError(f"the refit TF-IDF + LR did not settle within its {settings['max_iter']} solver steps")
    from sklearn.exceptions import ConvergenceWarning

    if any(issubclass(w.category, ConvergenceWarning) for w in warned):
        raise RefitError("the refit TF-IDF + LR did not settle: its solver stopped early")
    predicted = _step("TF-IDF + LR could not label the development rows", predict_tfidf, model,
                      [r.narrative for r in dev])
    if set(committed) != {r.complaint_id for r in dev}:
        raise RefitError("the committed July development labels are not the development list's")
    wrong = sum(committed[r.complaint_id] != label for r, (label, _) in zip(dev, predicted))
    if wrong:
        raise RefitError(f"the refit TF-IDF + LR gives {wrong} of {len(dev)} July development labels other than "
                         "the committed ones")
    return model
