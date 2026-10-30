"""A10 to A12 (specs/002-results-api-dashboard, docs/USER.md tasks 2 and 3): the analyst screens' routes.

The screens use the development set, never the test set: the test set's text and its consumer's choices are
read only by the one scored run (B17), and review never touches the test set results (B20). Owner decision of
30 October 2026.

The lists and the complaint view read the development results file: IDs, labels, quote positions and reasons.
The consumer's own choice comes from the local staged table, on the analyst's own machine. The complaint's text
comes from the same table, and only when the owner starts the app with `--with-text`. A public copy has no such
table, so it serves IDs, labels and reasons only. Only complaints in the development results file are ever
looked up (A10).

The consumer's own choice is hidden on a quarantined complaint until a person has reviewed it, so the
decision is the person's own (A11). One POST route stores a review decision: an ID, one of the 11 products or
none, and a reason from a fixed list, never free text (A12).
"""
import csv
import datetime
import io
import math
import os
import re
import threading
from typing import Literal, Optional

import duckdb
from fastapi import Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from voc.baselines import cut_text
from voc.db import SAFE_CONFIG
from voc.labels import load_labels
from voc.load import DB_PATH, TABLE

PER_PAGE = 25
REVIEW_REASONS = ("ai_right", "word_model_right", "other_product", "no_product")
# Review of #46: a saved decision is locked. A change is stored as a new entry with this reason, and the first
# decision is the one that is scored.
CORRECTION = "correction"
REVIEW_COLUMNS = ("complaint_id", "label", "reason", "decided_at")
# B3: every reason a complaint can be quarantined with, as in voc.api. Any other value is served as "other" (A2).
QUARANTINE_REASONS = ("no_narrative", "boundary_in_text", "unparseable", "invalid_label", "quote_empty",
                      "quote_redaction_only", "quote_too_short", "quote_not_in_text", "model_error", "not_run_budget")
DECIDED_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}")
WRITE_LOCK = threading.Lock()
# A12: a review must come from this app's own page. Another site's form cannot set a custom header.
PAGE_HEADER = "voc"


def _order(complaint_id):
    """Complaint IDs in number order, so SYN-3 comes before SYN-10."""
    digits = "".join(ch for ch in complaint_id if ch.isdigit())
    return (int(digits) if digits else 0, complaint_id)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Optional[str]
    reason: Literal["ai_right", "word_model_right", "other_product", "no_product", "correction"]


def _ids(path):
    if not path.is_file():
        return set()
    return {row.get("complaint_id") for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))}


def add_routes(app, root, checked_version, complaint_id_pattern, with_text=False, public=False):
    """Add the analyst routes. `checked_version` raises a 404 for a bad version name. On the public copy (A13)
    the local staged table is never read and no review is stored."""

    def _labels():
        return [label.name for label in load_labels(root / "config" / "labels.toml")]

    def _results(version):
        checked_version(version)
        path = root / "results" / "eval" / f"{version}_dev.csv"
        if not path.is_file():
            raise HTTPException(404, "no committed development results for this version")
        names = set(_labels())
        # B17, review of #46: only IDs on the frozen development list, and never one on the test list, so an
        # edited results file cannot let a test row through to the staged table lookup.
        dev, test = _ids(root / "splits" / "dev.csv"), _ids(root / "splits" / "test.csv")
        rows = {}
        for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
            cid = row.get("complaint_id") or ""
            if not complaint_id_pattern.fullmatch(cid) or cid not in dev or cid in test:
                continue
            accepted = row.get("decision") == "accepted"
            reason = row.get("reason") if row.get("reason") in QUARANTINE_REASONS else "other"
            rows[cid] = {"complaint_id": cid, "decision": "accepted" if accepted else "quarantined",
                         "reason": None if accepted else reason,
                         "ai_label": row.get("accepted_label") if accepted and row.get("accepted_label") in names
                         else None,
                         "proposed_label": row.get("proposed_label") if row.get("proposed_label") in names else None,
                         "tfidf_label": row.get("tfidf_label") if row.get("tfidf_label") in names else None,
                         "quote": _quote(row) if accepted else None}
        return rows

    def _reviews_path(version):
        return root / "results" / "reviews" / f"{version}_dev.csv"

    def _review_rows(version):
        """The stored rows, each field checked (A2). A broken row is skipped, never an error."""
        path = _reviews_path(version)
        if not path.is_file():
            return []
        names = set(_labels())
        out = []
        for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
            cid, label, reason = row.get("complaint_id") or "", row.get("label"), row.get("reason")
            if (complaint_id_pattern.fullmatch(cid) and reason in (*REVIEW_REASONS, CORRECTION)
                    and (label in names or label == "")):
                decided = row.get("decided_at") or ""
                out.append({"complaint_id": cid, "label": label or None, "reason": reason,
                            "decided_at": decided if DECIDED_AT.fullmatch(decided) else None})
        return out

    def _reviews(version):
        """For each ID: the latest entry, with the first decision under "first". The first one is scored."""
        out = {}
        for row in _review_rows(version):
            entry = {k: row[k] for k in ("label", "reason", "decided_at")}
            if row["complaint_id"] not in out:
                if row["reason"] == CORRECTION:
                    continue
                out[row["complaint_id"]] = entry | {"first": entry}
            else:
                out[row["complaint_id"]] = entry | {"first": out[row["complaint_id"]]["first"]}
        return out

    def _local(ids):
        """The consumer's own choice and the text, from the local staged table, for these development IDs only."""
        path = root / DB_PATH
        if public or not path.is_file():
            return None
        try:
            con = duckdb.connect(str(path), read_only=True, config=SAFE_CONFIG)
        except duckdb.Error:
            return None
        # Review of #46: the narrative column is read only when the owner started the app with --with-text.
        text = "narrative" if with_text else "NULL"
        try:
            found = con.execute(f"SELECT complaint_id, product, {text} FROM {TABLE} "
                                "WHERE list_contains(?::VARCHAR[], complaint_id)", [sorted(ids)]).fetchall()
        except duckdb.Error:
            return None
        finally:
            con.close()
        names = set(_labels())
        return {cid: (product if product in names else None, narrative) for cid, product, narrative in found}

    def _view(row, local, reviews):
        """One row as served: the consumer's own choice is hidden on a quarantined complaint not yet reviewed."""
        review = reviews.get(row["complaint_id"])
        hidden = row["decision"] == "quarantined" and review is None
        choice = None if local is None or hidden else (local.get(row["complaint_id"]) or (None, None))[0]
        return {key: row[key] for key in ("complaint_id", "decision", "reason", "ai_label", "proposed_label",
                                          "tfidf_label")} | {"consumer_choice": choice, "hidden": hidden,
                                                             "review": review}

    @app.get("/api/review/{version}/complaints")
    def complaints(version: str, product: Optional[str] = None,
                   show: Literal["all", "right", "wrong", "quarantined"] = "all", page: int = Query(1, ge=1)):
        rows = _results(version)
        if product is not None and product not in _labels():
            raise HTTPException(404, "unknown product")
        local = _local(rows)
        reviews = _reviews(version)
        views = [_view(row, local, reviews) for row in rows.values()]
        held_back = 0
        if product is not None:
            # A11: with a product chosen, a hidden complaint is left out, so where it is listed cannot give
            # away the consumer's choice. The page says how many are in the review queue instead.
            held_back = sum(v["hidden"] for v in views)
            key = "consumer_choice" if local is not None else "ai_label"
            views = [v for v in views if not v["hidden"] and v[key] == product]
        if show == "right":
            views = [v for v in views if v["decision"] == "accepted" and v["consumer_choice"] is not None
                     and v["ai_label"] == v["consumer_choice"]]
        elif show == "wrong":
            views = [v for v in views if v["decision"] == "accepted" and v["consumer_choice"] is not None
                     and v["ai_label"] != v["consumer_choice"]]
        elif show == "quarantined":
            views = [v for v in views if v["decision"] == "quarantined"]
        views.sort(key=lambda v: _order(v["complaint_id"]))
        pages = max(1, math.ceil(len(views) / PER_PAGE))
        return {"local": local is not None, "product": product, "show": show, "page": page, "per_page": PER_PAGE,
                "pages": pages, "total": len(views), "held_back_for_review": held_back,
                "rows": views[(page - 1) * PER_PAGE:page * PER_PAGE]}

    @app.get("/api/review/{version}/complaint/{complaint_id}")
    def complaint(version: str, complaint_id: str):
        rows = _results(version)
        if complaint_id not in rows:
            raise HTTPException(404, "no such complaint in the development results")
        row = rows[complaint_id]
        local = _local({complaint_id})
        out = _view(row, local, _reviews(version))
        text, cut = None, False
        # A10: the text only when the owner started the app with --with-text.
        if with_text and local is not None and complaint_id in local:
            text, cut = cut_text(local[complaint_id][1])
        quote = row["quote"]
        if quote is not None and text is not None and quote["end"] > len(text):
            quote = None
        return out | {"local": local is not None, "with_text": with_text, "text": text, "cut": cut, "quote": quote,
                      "labels": _labels()}

    @app.get("/api/review/{version}/queue")
    def review_queue(version: str):
        rows = _results(version)
        reviews = _reviews(version)
        queue = [_view(row, None, reviews) for row in rows.values() if row["decision"] == "quarantined"]
        queue.sort(key=lambda v: _order(v["complaint_id"]))
        return {"total": len(queue), "reviewed": sum(v["review"] is not None for v in queue), "rows": queue}

    @app.post("/api/review/{version}/decision/{complaint_id}")
    def review(version: str, complaint_id: str, body: Review, x_requested_with: Optional[str] = Header(None)):
        if public:
            raise HTTPException(403, "the public copy stores no review. Reviews are made on the analyst's own machine")
        if x_requested_with != PAGE_HEADER:
            raise HTTPException(403, "a review can only be sent from this app's own page")
        rows = _results(version)
        if complaint_id not in rows:
            raise HTTPException(404, "no such complaint in the development results")
        row = rows[complaint_id]
        if row["decision"] != "quarantined":
            raise HTTPException(409, "only a quarantined complaint is reviewed")
        existing = _reviews(version).get(complaint_id)
        if body.reason == CORRECTION:
            if existing is None:
                raise HTTPException(409, "there is no decision to correct yet")
            if body.label is not None and body.label not in _labels():
                raise HTTPException(422, "the label must be one of the 11 products, or none")
        elif existing is not None:
            raise HTTPException(409, "a saved decision is locked. Send a correction instead")
        elif body.reason == "no_product":
            if body.label is not None:
                raise HTTPException(422, "no product fits, so the label is left empty")
        elif body.label not in _labels():
            raise HTTPException(422, "the label must be one of the 11 products")
        if body.reason == "ai_right" and body.label != row["proposed_label"]:
            raise HTTPException(422, "the label is not the AI's proposed label")
        if body.reason == "word_model_right" and body.label != row["tfidf_label"]:
            raise HTTPException(422, "the label is not the word-based model's suggestion")
        if body.reason == "other_product" and body.label in (row["proposed_label"], row["tfidf_label"]):
            raise HTTPException(422, "that product belongs to another reason")
        decided = {"label": body.label, "reason": body.reason,
                   "decided_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        path = _reviews_path(version)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Review of #46: one save at a time, and the file is swapped in whole, so a crash cannot truncate it.
        with WRITE_LOCK:
            stored = _review_rows(version) + [{"complaint_id": complaint_id, **decided}]
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
            writer.writeheader()
            for entry in stored:
                writer.writerow({"complaint_id": entry["complaint_id"], "label": entry["label"] or "",
                                 "reason": entry["reason"], "decided_at": entry["decided_at"] or ""})
            temp = path.with_name(path.name + ".tmp")
            temp.write_text(out.getvalue(), encoding="utf-8")
            os.replace(temp, path)
        return {"saved": True, "complaint_id": complaint_id, "review": _reviews(version)[complaint_id]}


def _quote(row):
    try:
        start, end = int(row.get("quote_start") or ""), int(row.get("quote_end") or "")
    except ValueError:
        return None
    return {"start": start, "end": end} if 0 <= start < end else None
