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
REVIEW_COLUMNS = ("complaint_id", "label", "reason", "decided_at")
# A12: a review must come from this app's own page. Another site's form cannot set a custom header.
PAGE_HEADER = "voc"


def _order(complaint_id):
    """Complaint IDs in number order, so SYN-3 comes before SYN-10."""
    digits = "".join(ch for ch in complaint_id if ch.isdigit())
    return (int(digits) if digits else 0, complaint_id)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Optional[str]
    reason: str


def add_routes(app, root, checked_version, complaint_id_pattern, with_text=False):
    """Add the analyst routes. `checked_version` raises a 404 for a bad version name."""

    def _labels():
        return [label.name for label in load_labels(root / "config" / "labels.toml")]

    def _results(version):
        checked_version(version)
        path = root / "results" / "eval" / f"{version}_dev.csv"
        if not path.is_file():
            raise HTTPException(404, "no committed development results for this version")
        names = set(_labels())
        rows = {}
        for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
            cid = row.get("complaint_id") or ""
            if not complaint_id_pattern.fullmatch(cid):
                continue
            accepted = row.get("decision") == "accepted"
            rows[cid] = {"complaint_id": cid, "decision": "accepted" if accepted else "quarantined",
                         "reason": None if accepted else (row.get("reason") or "other"),
                         "ai_label": row.get("accepted_label") if accepted and row.get("accepted_label") in names
                         else None,
                         "proposed_label": row.get("proposed_label") if row.get("proposed_label") in names else None,
                         "tfidf_label": row.get("tfidf_label") if row.get("tfidf_label") in names else None,
                         "quote": _quote(row) if accepted else None}
        return rows

    def _reviews_path(version):
        return root / "results" / "reviews" / f"{version}_dev.csv"

    def _reviews(version):
        path = _reviews_path(version)
        if not path.is_file():
            return {}
        names = set(_labels())
        out = {}
        for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
            if row.get("reason") in REVIEW_REASONS and (row.get("label") in names or row.get("label") == ""):
                out[row["complaint_id"]] = {"label": row["label"] or None, "reason": row["reason"],
                                            "decided_at": row.get("decided_at") or None}
        return out

    def _local(ids):
        """The consumer's own choice and the text, from the local staged table, for these development IDs only."""
        path = root / DB_PATH
        if not path.is_file():
            return None
        try:
            con = duckdb.connect(str(path), read_only=True, config=SAFE_CONFIG)
        except duckdb.Error:
            return None
        try:
            found = con.execute(f"SELECT complaint_id, product, narrative FROM {TABLE} "
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
        if x_requested_with != PAGE_HEADER:
            raise HTTPException(403, "a review can only be sent from this app's own page")
        rows = _results(version)
        if complaint_id not in rows:
            raise HTTPException(404, "no such complaint in the development results")
        row = rows[complaint_id]
        if row["decision"] != "quarantined":
            raise HTTPException(409, "only a quarantined complaint is reviewed")
        if body.reason not in REVIEW_REASONS:
            raise HTTPException(422, "the reason must be one of the fixed list")
        if body.reason == "no_product":
            if body.label is not None:
                raise HTTPException(422, "no product fits, so the label is left empty")
        elif body.label not in _labels():
            raise HTTPException(422, "the label must be one of the 11 products")
        if body.reason == "ai_right" and body.label != row["proposed_label"]:
            raise HTTPException(422, "the label is not the AI's proposed label")
        if body.reason == "word_model_right" and body.label != row["tfidf_label"]:
            raise HTTPException(422, "the label is not the word-based model's suggestion")
        decided = {"label": body.label, "reason": body.reason,
                   "decided_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        stored = _reviews(version) | {complaint_id: decided}
        path = _reviews_path(version)
        path.parent.mkdir(parents=True, exist_ok=True)
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for cid in sorted(stored, key=_order):
            writer.writerow({"complaint_id": cid, "label": stored[cid]["label"] or "",
                             "reason": stored[cid]["reason"], "decided_at": stored[cid]["decided_at"] or ""})
        path.write_text(out.getvalue(), encoding="utf-8")
        return {"saved": True, "complaint_id": complaint_id, "review": decided}


def _quote(row):
    try:
        start, end = int(row.get("quote_start") or ""), int(row.get("quote_end") or "")
    except ValueError:
        return None
    return {"start": start, "end": end} if 0 <= start < end else None
