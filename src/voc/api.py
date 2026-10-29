"""A1 to A5 (specs/002-results-api-dashboard): a read-only API over the committed results files.

It reads only committed files and copies only the fields it names, so a field added to a file later is never
served by accident and no complaint text can reach a response (B21, A2). It calls no model and reads no
ledger, recording, raw data or DuckDB file.
"""
import csv
import io
import json
import re
import tomllib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB = Path(__file__).parent / "web"
VERSION = re.compile(r"v[0-9]+")
MONEY = re.compile(r"[0-9]+(\.[0-9]+)?")
# docs/DATA.md, from `uv run --native-tls voc profile` on the pinned July 2026 export.
JULY_COMPLAINTS = 672_036
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

FIGURES = ("set", "prompt_version", "complaints", "backend", "model", "figures_are", "verdict", "difference",
           "interval", "resamples", "seed")
METHOD = {"llm": ("reweighted_accuracy", "precision", "coverage", "quarantine_rate", "macro_f1",
                  "cost_per_1000_usd", "seconds_per_1000_complaints", "no_time_per_1000_because"),
          "tfidf": ("reweighted_accuracy", "precision", "coverage", "macro_f1", "cost_per_1000_usd",
                    "seconds_per_1000_complaints")}
RUN = ("complaints", "accepted", "quarantined", "quarantine_reasons", "cut", "calls_by_source", "input_tokens",
       "output_tokens", "run_seconds", "seconds_per_1000_complaints", "no_time_per_1000_because")
AUDIT = ("set", "prompt_version", "accepted", "verified", "word_for_word", "quarantined", "rederived", "no_answer",
         "listed", "rows_listed", "failures")
QUEUE = ("complaint_id", "reason", "proposed_label", "tfidf_label")


def _pick(record, fields):
    return {k: record[k] for k in fields if k in record}


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _money(value):
    return value if isinstance(value, str) and MONEY.fullmatch(value) else None


def _counts(mapping):
    """A mapping of our own names to counts, with anything else dropped."""
    if not isinstance(mapping, dict):
        return {}
    return {str(k): v for k, v in mapping.items() if _number(v) is not None}


def create_app(root):
    root = Path(root)
    app = FastAPI(title="voc-demo results", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def _file(folder, version, suffix):
        if not VERSION.fullmatch(version):
            raise HTTPException(404, "unknown prompt version")
        path = root / "results" / folder / f"{version}_dev{suffix}"
        if not path.is_file():
            raise HTTPException(404, "no committed results for this version")
        return path

    def _json(folder, version):
        return json.loads(_file(folder, version, ".json").read_text(encoding="utf-8"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/versions")
    def versions():
        path = root / "EVAL_VERSIONS.md"
        if not path.is_file():
            return []
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("|")]
        header = next((line for line in lines if line.startswith("| Date")), None)
        if header is None:
            return []
        columns = [cell.strip() for cell in header.strip("|").split("|")]
        rows = [line for line in lines if re.match(r"\| [0-9]{4}-", line)]
        return [dict(zip(columns, (cell.strip() for cell in row.strip("|").split("|")))) for row in rows]

    @app.get("/api/eval/{version}")
    def figures(version: str):
        data = _json("eval", version)
        out = _pick(data, FIGURES)
        out["interval"] = [_number(v) for v in data.get("interval", [])][:2]
        for method, fields in METHOD.items():
            picked = _pick(data.get(method, {}), fields)
            picked["cost_per_1000_usd"] = _money(picked.get("cost_per_1000_usd"))
            out[method] = picked
        out["who_was_right"] = _counts(data.get("who_was_right"))
        curve = data.get("precision_coverage", {})
        out["precision_coverage"] = {
            "tfidf": [[_number(a), _number(b)] for a, b in curve.get("tfidf", [])],
            "llm": [_number(v) for v in curve.get("llm", [])][:2]}
        out["review_queue"] = {str(reason): _counts(entry) for reason, entry in data.get("review_queue", {}).items()}
        out["quote_length"] = _counts(data.get("quote_length"))
        out["live_cost_usd"] = _money(data.get("live_cost_usd"))
        out["replay_cost_usd"] = _money(data.get("replay_cost_usd"))
        return out

    @app.get("/api/eval/{version}/quarantine")
    def quarantine(version: str):
        text = _file("eval", version, ".csv").read_text(encoding="utf-8")
        return [_pick(row, QUEUE) for row in csv.DictReader(io.StringIO(text)) if row.get("decision") != "accepted"]

    @app.get("/api/run/{version}")
    def run(version: str):
        data = _json("labels", version)
        out = _pick(data, RUN)
        out["quarantine_reasons"] = _counts(out.get("quarantine_reasons"))
        out["calls_by_source"] = _counts(out.get("calls_by_source"))
        cost = data.get("cost") or {}
        out["cost"] = {"live_cost_usd": _money(cost.get("live_cost_usd")),
                       "own_cost_usd": _money(cost.get("own_cost_usd"))}
        return out

    @app.get("/api/audit/{version}")
    def audit(version: str):
        data = _json("audit", version)
        out = _pick(data, AUDIT)
        out["failures"] = _counts(out.get("failures"))
        return out

    @app.get("/api/data")
    def data():
        manifest = json.loads((root / "splits" / "manifest.json").read_text(encoding="utf-8"))
        with open(root / "config" / "pool.toml", "rb") as f:
            products = tomllib.load(f)["products"]
        return {"july_complaints": JULY_COMPLAINTS,
                "pool": sum(_number(p.get("pool")) or 0 for p in products.values()),
                "categories": len(products),
                "sets": {name: _number(entry.get("count")) for name, entry in manifest.get("lists", {}).items()},
                "copies_removed": {"exact": _number(manifest.get("exact_copies")),
                                   "near": _number(manifest.get("near_copies"))}}

    @app.get("/")
    def page():
        return FileResponse(WEB / "index.html")

    app.mount("/web", StaticFiles(directory=WEB), name="web")
    return app
