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
from decimal import Decimal
from pathlib import Path

from voc import june_score, metrics, pipeline
from voc.baselines import predict_tfidf
from voc.costs import call_cost, load_prices
from voc.labels import load_labels
from voc.repo_checks import CFPB_HEADER, SIZE_LIMIT

COLUMNS = ("complaint_id", "split", "prompt_version", "proposed_label", "quote_start", "quote_end", "decision",
           "reason", "accepted_label", "tfidf_label", "tfidf_confidence", "recording_key")
FILES = ("v1_june.csv", "v1_june.json")
REASONS = ("no_narrative", "boundary_in_text", "unparseable", "invalid_label", "quote_empty", "quote_redaction_only",
           "quote_too_short", "quote_not_in_text", "model_error", "not_run_budget")
JUNE_LIST = Path("splits") / "june" / "june.csv"


class JuneResultsError(ValueError):
    """A refusal with fixed text and counts only (B21, J5)."""


def _listed(root):
    data = (Path(root) / JUNE_LIST).read_bytes()
    return {row[0] for row in list(csv.reader(io.StringIO(data.decode("utf-8"))))[1:]}, hashlib.sha256(data).hexdigest()


def build(root, rows, outcomes, model, version):
    """The two files' contents for a finished real run: the CSV text and the summary. `rows` are the sample's
    (complaint ID, recorded Product, text), `outcomes` the labeller's, `model` the refit TF-IDF + LR."""
    root = Path(root)
    by_id = {cid: (product, text) for cid, product, text in rows}
    ordered = sorted(by_id, key=metrics._id_number)
    predicted = dict(zip(ordered, predict_tfidf(model, [by_id[cid][1] for cid in ordered])))
    names = [label.name for label in load_labels(root / "config" / "labels.toml")]
    decided = {row["complaint_id"]: row for row in
               csv.DictReader(io.StringIO(pipeline.results_csv(outcomes, "june", version, names)))}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    items = []
    for cid in ordered:
        label, confidence = predicted[cid]
        row = decided[cid]
        # The exact value, so a recompute from this file breaks ties the same way (B19).
        writer.writerow({**row, "split": "june", "tfidf_label": label, "tfidf_confidence": repr(confidence)})
        items.append(metrics.Item(cid, by_id[cid][0], row["accepted_label"] or None, row["reason"] or None, label,
                                  confidence, llm_proposed=row["proposed_label"] or None))
    prices = load_prices(root / "config" / "prices.toml")
    model_name = version.settings["model"]
    tokens_in = sum(o.input_tokens or 0 for o in outcomes)
    tokens_out = sum(o.output_tokens or 0 for o in outcomes)
    cost = sum((call_cost(prices, model_name, o.input_tokens, o.output_tokens) for o in outcomes
                if o.input_tokens is not None and o.output_tokens is not None), Decimal(0))
    cost_per_1000 = str((cost * 1000 / len(items)).quantize(Decimal("0.0001"))) if items and cost else None
    figures = june_score.score_june_sample(root, items, cost_per_1000)
    _, list_sha256 = _listed(root)
    summary = {"set": "june", "prompt_version": version.name, "model": model_name, "settings": version.settings,
               "backend": "api", "list_sha256": list_sha256, "input_tokens": tokens_in, "output_tokens": tokens_out,
               "live_cost_usd": str(cost), "cost_per_1000_usd": cost_per_1000, **figures,
               "complaints": len(items)}
    return out.getvalue(), summary


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
    try:
        summary = json.loads(json_text)
    except ValueError:
        summary = None
    if not isinstance(summary, dict) or summary.get("set") != "june":
        raise JuneResultsError("v1_june.json is not the June run's summary")
