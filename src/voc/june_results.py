"""Spec 004, J11 and B19: Job B's two results files for a real June run, and their checks (pull request 6b, part 4).

`v1_june.csv` holds one row per sampled complaint with B19's columns only, the development results' columns, split
`june`, in complaint ID order, with TF-IDF + LR's label from the refit and its exact confidence, so anyone can
recompute every June figure from it and the public archive file. `v1_june.json` holds the run summary: the run's
settings, its tokens and cost, and the June figures of `voc.june_score`. Job B checks both before it writes them to
the results volume, and the copy script checks them again on the laptop (J11).

Neither file holds narrative text, a quote, the consumer's recorded Product or any field of a complaint but its
ID. The labels are from the fixed label list and the reasons from the fixed list of reasons.

B21 and J5: nothing here prints. Every refusal holds fixed text and counts only, never a value from a file.
"""
import csv
import hashlib
import io
import json
import re
import time
from decimal import Decimal
from pathlib import Path

from voc import june_score, metrics, pipeline
from voc.baselines import predict_tfidf
from voc.costs import call_cost, load_prices, run_cost
from voc.evaluate import COVERAGE_POINTS, _per_category, _quote_lengths
from voc.labels import load_labels
from voc.repo_checks import CFPB_HEADER, SIZE_LIMIT

COLUMNS = ("complaint_id", "split", "prompt_version", "proposed_label", "quote_start", "quote_end", "decision",
           "reason", "accepted_label", "tfidf_label", "tfidf_confidence", "recording_key")
FILES = ("v1_june.csv", "v1_june.json")
REASONS = ("no_narrative", "boundary_in_text", "unparseable", "invalid_label", "quote_empty", "quote_redaction_only",
           "quote_too_short", "quote_not_in_text", "model_error", "not_run_budget")
JUNE_LIST = Path("splits") / "june" / "june.csv"
PROMPT_VERSION = "v1"
# Review of #112, serious 1: the keys of July's test summary, the hybrid's and the run's.
REQUIRED_KEYS = frozenset({
    "backend", "complaints", "confusion", "difference", "figures_are", "interval", "list_sha256", "live_cost_usd",
    "llm", "model", "note", "per_category", "precision_coverage", "prompt_version", "quote_length",
    "replay_cost_usd", "resamples", "review_queue", "seed", "set", "settings", "tfidf", "verdict", "who_was_right",
    "primary", "secondary", "full_coverage", "cost_per_extra_correct_usd", "shares", "weights", "accepted",
    "quarantined", "entry_list_sha256", "entry_code_sha256", "job_a_run_id", "job_b_run_id", "github_run_id",
    "run_seconds", "input_tokens", "output_tokens", "calls_without_usage", "charged_without_answer_tokens",
    "cost_per_1000_usd"})
TEXT_LIMIT = 500  # review of #112, minor 4: no text value in the summary is longer, so no complaint fits
NOTE = ("the June run: the LLM, TF-IDF + LR refit from July's training rows, and the hybrid, on the frozen June "
        "sample. The top-level verdict, difference and interval are the primary claim's (J7)")
FIGURES_ARE = "the June claim's verdict, from the single June run (J1, J7)"
CONFUSION_NOTE = ("[recorded, predicted, count]. The LLM matrix has a 'quarantined' column. The TF-IDF and "
                  "hybrid matrices cover every complaint")
_KEY = re.compile(r"[0-9a-f]{64}")
FORMS = {"prompt_version": lambda v: v == PROMPT_VERSION,
         "decision": lambda v: v in ("accepted", "quarantined"),
         "quote_start": lambda v: v == "" or v.isdigit(), "quote_end": lambda v: v == "" or v.isdigit(),
         "tfidf_confidence": lambda v: _probability(v),
         "recording_key": lambda v: v == "" or bool(_KEY.fullmatch(v))}


def _probability(value):
    try:
        number = float(value)
    except ValueError:
        return False
    return 0.0 <= number <= 1.0


class JuneResultsError(ValueError):
    """A refusal with fixed text and counts only (B21, J5)."""


def _listed(root):
    data = (Path(root) / JUNE_LIST).read_bytes()
    return {row[0] for row in list(csv.reader(io.StringIO(data.decode("utf-8"))))[1:]}, hashlib.sha256(data).hexdigest()


def _ordered(rows, outcomes):
    """The sample's complaint IDs in ID number order, then ID, as `june_score` sorts. The outcomes must be the
    sample's complaints, once each (review of #112, nits 6 and 7)."""
    ids = [cid for cid, _, _ in rows]
    given = [o.decision.complaint_id for o in outcomes]
    if len(set(ids)) != len(ids) or sorted(given) != sorted(ids):
        raise JuneResultsError("the outcomes must be the sample's complaints, once each")
    return sorted(ids, key=lambda cid: (metrics._id_number(cid), cid))


def _cost(root, model_name, outcomes, ledger_tokens):
    """Tokens and cost, never too low (review of #112, serious 2). Each answered call as `costs.run_cost` costs it:
    one with no usage as output tokens from what it was charged, and a replayed one in the live cost but not this
    run's own. A call the June ledger charged that gave no answer, failed, refused or cut off, is costed as output
    tokens too: the ledger's charge in this run less what the answered calls were charged."""
    prices = load_prices(Path(root) / "config" / "prices.toml")
    answered = [o for o in outcomes if o.source in ("live", "replay")]
    summary = run_cost(prices, model_name, answered)
    charged = sum(o.live_cost_tokens for o in answered if o.source == "live")
    extra = max(0, ledger_tokens - charged) if ledger_tokens is not None else 0
    extra_cost = call_cost(prices, model_name, 0, extra)
    return {"input_tokens": summary["input_tokens"], "output_tokens": summary["output_tokens"] + extra,
            "calls_without_usage": summary["calls_without_usage"], "charged_without_answer_tokens": extra,
            "live_cost_usd": summary["live_cost_usd"] + extra_cost,
            "replay_cost_usd": summary["own_cost_usd"] + extra_cost}


def build(root, rows, outcomes, model, version, run_info, ledger_tokens=None, run_seconds=None):
    """The two files' contents for a finished real run: the CSV text and the summary. `rows` are the sample's
    (complaint ID, recorded Product, text), `outcomes` the labeller's, `model` the refit TF-IDF + LR, `run_info` the
    run entry's two hashes and the three run IDs, `ledger_tokens` what the June ledger charged in this run, and
    `run_seconds` the labelling's time. The summary has the keys of July's test summary, built by the same functions,
    and the hybrid's figures (review of #112, serious 1)."""
    root = Path(root)
    by_id = {cid: (product, text) for cid, product, text in rows}
    ordered = _ordered(rows, outcomes)
    started = time.monotonic()
    predicted = dict(zip(ordered, predict_tfidf(model, [by_id[cid][1] for cid in ordered])))
    tfidf_seconds = time.monotonic() - started
    labels = [label.name for label in load_labels(root / "config" / "labels.toml")]
    decided = {row["complaint_id"]: row for row in
               csv.DictReader(io.StringIO(pipeline.results_csv(outcomes, "june", version, labels)))}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    items, written = [], []
    for cid in ordered:
        label, confidence = predicted[cid]
        # The exact value, so a recompute from this file breaks ties the same way (B19).
        row = {**decided[cid], "split": "june", "tfidf_label": label, "tfidf_confidence": repr(confidence)}
        writer.writerow(row)
        written.append(row)
        items.append(metrics.Item(cid, by_id[cid][0], row["accepted_label"] or None, row["reason"] or None, label,
                                  confidence, llm_proposed=row["proposed_label"] or None))
    model_name = version.settings["model"]
    cost = _cost(root, model_name, outcomes, ledger_tokens)
    n = len(items)
    cost_per_1000 = str((cost["live_cost_usd"] * 1000 / n).quantize(Decimal("0.0001"))) if cost["live_cost_usd"] else None
    figures = june_score.score_june_sample(root, items, cost_per_1000)
    claims = june_score.load_claims(root)
    second = figures["secondary"]
    _, list_sha256 = _listed(root)
    llm_prf, tfidf_prf = metrics.prf(items, "llm", labels), metrics.prf(items, "tfidf", labels)
    confusion = {**figures["confusion"], "note": CONFUSION_NOTE}
    summary = {
        **figures,
        "set": "june", "prompt_version": version.name, "note": NOTE, "backend": "api", "model": model_name,
        "settings": version.settings, "list_sha256": list_sha256, "complaints": n, "figures_are": FIGURES_ARE,
        "verdict": figures["primary"]["verdict"], "difference": figures["primary"]["difference"],
        "interval": list(figures["primary"]["interval"]), "resamples": claims["bootstrap"]["resamples"],
        "seed": claims["bootstrap"]["seed"],
        "llm": {"reweighted_accuracy": second.get("llm_reweighted"), "precision": second.get("llm_precision"),
                "coverage": second.get("coverage"), "quarantine_rate": second.get("quarantine_rate"),
                "macro_f1": llm_prf["macro_f1"], "cost_per_1000_usd": cost_per_1000,
                "seconds_per_1000_complaints": (round(metrics.per_thousand(run_seconds, n), 3)
                                                if run_seconds is not None else None),
                "no_time_per_1000_because": None if run_seconds is not None else "no run time was measured"},
        "tfidf": {"reweighted_accuracy": second.get("tfidf_reweighted"), "precision": second.get("tfidf_precision"),
                  "coverage": second.get("coverage"), "macro_f1": tfidf_prf["macro_f1"], "cost_per_1000_usd": "0",
                  "settings_sha256": hashlib.sha256((root / "config" / "tfidf.toml").read_bytes()).hexdigest(),
                  "seconds_per_1000_complaints": round(metrics.per_thousand(tfidf_seconds, n), 3)},
        "per_category": _per_category(items, labels),
        "confusion": confusion,
        "who_was_right": metrics.who_was_right(items),
        "precision_coverage": {"tfidf": [list(point) for point in metrics.precision_coverage(items, COVERAGE_POINTS)[0]],
                               "llm": list(metrics.precision_coverage(items, COVERAGE_POINTS)[1])},
        "review_queue": metrics.review_queue(items),
        "quote_length": _quote_lengths(written),
        "live_cost_usd": str(cost["live_cost_usd"]), "replay_cost_usd": str(cost["replay_cost_usd"]),
        "input_tokens": cost["input_tokens"], "output_tokens": cost["output_tokens"],
        "calls_without_usage": cost["calls_without_usage"],
        "charged_without_answer_tokens": cost["charged_without_answer_tokens"], "cost_per_1000_usd": cost_per_1000,
        "entry_list_sha256": run_info["entry_list_sha256"], "entry_code_sha256": run_info["entry_code_sha256"],
        "job_a_run_id": run_info["job_a_run_id"], "job_b_run_id": run_info["job_b_run_id"],
        "github_run_id": run_info["github_run_id"], "run_seconds": run_seconds,
    }
    return out.getvalue(), summary


def _texts(value):
    """Every text value in a summary, at any depth."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _texts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)


def check(root, csv_text, json_text, listed=None):
    """Refuses a pair of results files that breaks a rule of B19 or J11. `listed` is the June list's IDs, read from
    the checkout when not given."""
    root = Path(root)
    for name, text in zip(FILES, (csv_text, json_text)):
        if len(text.encode("utf-8")) > SIZE_LIMIT:
            raise JuneResultsError(f"{name} is over the size limit of {SIZE_LIMIT} bytes")
        if CFPB_HEADER in text:
            raise JuneResultsError(f"{name} holds the CFPB header row")
    reader = csv.DictReader(io.StringIO(csv_text))
    if tuple(reader.fieldnames or ()) != COLUMNS:
        raise JuneResultsError("v1_june.csv does not have exactly B19's columns")
    names = {label.name for label in load_labels(root / "config" / "labels.toml")}
    listed = _listed(root)[0] if listed is None else set(listed)
    seen = set()
    for row in reader:
        if row["split"] != "june":
            raise JuneResultsError("v1_june.csv has a row whose split is not june")
        if row["complaint_id"] not in listed:
            raise JuneResultsError("v1_june.csv has a complaint that is not in the June list")
        if row["complaint_id"] in seen:
            raise JuneResultsError("v1_june.csv must hold each complaint once")
        seen.add(row["complaint_id"])
        for column in ("accepted_label", "tfidf_label"):
            if row[column] and row[column] not in names:
                raise JuneResultsError(f"v1_june.csv has a {column} outside the label list")
        if row["proposed_label"] and row["proposed_label"] not in names | {pipeline.NOT_IN_LIST}:
            raise JuneResultsError("v1_june.csv has a proposed_label outside the label list")
        if row["reason"] and row["reason"] not in REASONS:
            raise JuneResultsError("v1_june.csv has a reason outside the fixed list")
        # Review of #112, minor 4: every other column in its form, so no text can hide in one.
        for column in FORMS:
            if not FORMS[column](row[column]):
                raise JuneResultsError(f"v1_june.csv has a {column} value outside its form")
    missing = len(listed - seen)
    if missing:
        raise JuneResultsError(f"v1_june.csv lacks {missing} complaint{'' if missing == 1 else 's'} of the June list")
    try:
        summary = json.loads(json_text)
    except ValueError:
        summary = None
    if not isinstance(summary, dict) or summary.get("set") != "june":
        raise JuneResultsError("v1_june.json is not the June run's summary")
    if not REQUIRED_KEYS <= set(summary):
        raise JuneResultsError("v1_june.json lacks a required key")
    if any(len(text) > TEXT_LIMIT for text in _texts(summary)):
        raise JuneResultsError(f"v1_june.json holds a text value longer than {TEXT_LIMIT} characters")
