"""A1 to A6 (specs/002-results-api-dashboard): a read-only API over the committed results files.

It reads only committed files. It copies only the fields it names, and checks each one: a number must be a
number, a name must be one of a fixed list, and a label must be in the label list. So a field added to a file
later, or a field holding something unexpected, is never served, and no complaint text can reach a response
(B21, A2). It calls no model and reads no ledger, recording, raw data or DuckDB file.
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
from starlette.middleware.trustedhost import TrustedHostMiddleware

from voc.audit import FAILURES
from voc.labels import load_labels

WEB = Path(__file__).parent / "web"
VERSION = re.compile(r"v[0-9]+")
MONEY = re.compile(r"[0-9]+(\.[0-9]+)?")
MODEL = re.compile(r"[a-z0-9][a-z0-9.\-]{0,63}")
COMPLAINT_ID = re.compile(r"(SYN-)?[0-9]{1,12}")
# docs/DATA.md, from `uv run --native-tls voc profile` on the pinned July 2026 export.
JULY_COMPLAINTS = 672_036
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
# A4: the names the app answers to, so a page on another site cannot reach it through DNS rebinding.
LOCAL_HOSTS = ["127.0.0.1", "localhost"]
TUNING = "tuning figures. The verdict comes only from the single test run"
VERDICTS = ("beats", "inconclusive", "does_not_beat")
BACKENDS = ("api", "mock")
SETS = ("dev", "quick")
SOURCES = ("live", "replay", "mock")
WHO = ("both", "only_llm", "only_tfidf", "neither")
# B3: every reason a complaint can be quarantined with.
REASONS = ("no_narrative", "boundary_in_text", "unparseable", "invalid_label", "quote_empty", "quote_redaction_only",
           "quote_too_short", "quote_not_in_text", "model_error", "not_run_budget")
NOT_IN_LIST = "(not in list)"
# B23: why a run has no time per 1,000 complaints (voc.pipeline).
NO_TIME_REASONS = ("no run time was measured", "the run stopped early", "no complaint was sent to the model",
                   "not every call was a live model call that returned an answer")
VERSION_COLUMNS = ("Date", "Prompt", "What changed", "Set", "List hash", "Backend", "Model", "Effort", "Complaints",
                   "LLM accuracy", "LLM coverage", "LLM quarantined", "TF-IDF accuracy", "TF-IDF coverage",
                   "TF-IDF quarantined", "Interval", "Quote length", "Live cost", "Replay cost")
METHOD_NUMBERS = {"llm": ("reweighted_accuracy", "precision", "coverage", "quarantine_rate", "macro_f1",
                          "seconds_per_1000_complaints"),
                  "tfidf": ("reweighted_accuracy", "precision", "coverage", "macro_f1", "seconds_per_1000_complaints")}
RUN_NUMBERS = ("complaints", "accepted", "quarantined", "cut", "input_tokens", "output_tokens", "run_seconds",
               "seconds_per_1000_complaints")
AUDIT_NUMBERS = ("accepted", "verified", "word_for_word", "quarantined", "rederived", "no_answer", "listed",
                 "rows_listed")


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _money(value):
    return value if isinstance(value, str) and MONEY.fullmatch(value) else None


def _one_of(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def _matches(value, pattern):
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _numbers(record, fields):
    record = _dict(record)
    return {k: _number(record.get(k)) for k in fields}


def _counts(mapping, allowed):
    """Counts under our own names only. Any other key, and any value that is not a number, is dropped."""
    return {k: v for k, v in _dict(mapping).items() if k in allowed and _number(v) is not None}


def create_app(root):
    root = Path(root)
    app = FastAPI(title="voc-demo results", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

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
        return _dict(json.loads(_file(folder, version, ".json").read_text(encoding="utf-8")))

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
        out = []
        for row in (line for line in lines if re.match(r"\| [0-9]{4}-", line)):
            cells = dict(zip(columns, (cell.strip() for cell in row.strip("|").split("|"))))
            out.append({k: v for k, v in cells.items() if k in VERSION_COLUMNS})
        return out

    @app.get("/api/eval/{version}")
    def figures(version: str):
        data = _json("eval", version)
        out = {"figures_are": TUNING, "set": _one_of(data.get("set"), SETS),
               "prompt_version": _matches(data.get("prompt_version"), VERSION),
               "backend": _one_of(data.get("backend"), BACKENDS), "model": _matches(data.get("model"), MODEL),
               "verdict": _one_of(data.get("verdict"), VERDICTS),
               "interval": [_number(v) for v in _list(data.get("interval"))][:2],
               **_numbers(data, ("complaints", "difference", "resamples", "seed"))}
        for method, fields in METHOD_NUMBERS.items():
            given = _dict(data.get(method))
            out[method] = {**_numbers(given, fields), "cost_per_1000_usd": _money(given.get("cost_per_1000_usd"))}
        out["llm"]["no_time_per_1000_because"] = _one_of(_dict(data.get("llm")).get("no_time_per_1000_because"),
                                                          NO_TIME_REASONS)
        out["who_was_right"] = _counts(data.get("who_was_right"), WHO)
        curve = _dict(data.get("precision_coverage"))
        out["precision_coverage"] = {
            "tfidf": [[_number(p[0]), _number(p[1])] for p in _list(curve.get("tfidf"))
                      if isinstance(p, list) and len(p) == 2],
            "llm": [_number(v) for v in _list(curve.get("llm"))][:2]}
        out["review_queue"] = {reason: _counts(entry, ("count", "tfidf_right"))
                               for reason, entry in _dict(data.get("review_queue")).items() if reason in REASONS}
        out["quote_length"] = _counts(data.get("quote_length"), ("median", "min", "max"))
        out["live_cost_usd"] = _money(data.get("live_cost_usd"))
        out["replay_cost_usd"] = _money(data.get("replay_cost_usd"))
        return out

    @app.get("/api/eval/{version}/quarantine")
    def quarantine(version: str):
        text = _file("eval", version, ".csv").read_text(encoding="utf-8")
        allowed = {label.name for label in load_labels(root / "config" / "labels.toml")} | {NOT_IN_LIST}
        queue = []
        for row in csv.DictReader(io.StringIO(text)):
            if row.get("decision") == "accepted" or not _matches(row.get("complaint_id"), COMPLAINT_ID):
                continue
            queue.append({"complaint_id": row["complaint_id"],
                          "reason": _one_of(row.get("reason"), REASONS) or "other",
                          "proposed_label": _one_of(row.get("proposed_label"), allowed) or "",
                          "tfidf_label": _one_of(row.get("tfidf_label"), allowed) or ""})
        return queue

    @app.get("/api/run/{version}")
    def run(version: str):
        data = _json("labels", version)
        out = _numbers(data, RUN_NUMBERS)
        out["no_time_per_1000_because"] = _one_of(data.get("no_time_per_1000_because"), NO_TIME_REASONS)
        out["quarantine_reasons"] = _counts(data.get("quarantine_reasons"), REASONS)
        out["calls_by_source"] = _counts(data.get("calls_by_source"), SOURCES)
        cost = _dict(data.get("cost"))
        out["cost"] = {"live_cost_usd": _money(cost.get("live_cost_usd")),
                       "own_cost_usd": _money(cost.get("own_cost_usd"))}
        return out

    @app.get("/api/audit/{version}")
    def audit(version: str):
        data = _json("audit", version)
        return {"set": _one_of(data.get("set"), SETS), "prompt_version": _matches(data.get("prompt_version"), VERSION),
                **_numbers(data, AUDIT_NUMBERS), "failures": _counts(data.get("failures"), FAILURES)}

    @app.get("/api/data")
    def data():
        manifest_path, pool_path = root / "splits" / "manifest.json", root / "config" / "pool.toml"
        if not manifest_path.is_file() or not pool_path.is_file():
            raise HTTPException(404, "the committed sample files are missing")
        manifest = _dict(json.loads(manifest_path.read_text(encoding="utf-8")))
        with open(pool_path, "rb") as f:
            products = _dict(tomllib.load(f).get("products"))
        return {"july_complaints": JULY_COMPLAINTS,
                "pool": sum(_number(_dict(p).get("pool")) or 0 for p in products.values()),
                "categories": len(products),
                "sets": {name: _number(_dict(_dict(manifest.get("lists")).get(name)).get("count"))
                         for name in ("dev", "test", "train")},
                "copies_removed": {"exact": _number(manifest.get("exact_copies")),
                                   "near": _number(manifest.get("near_copies"))}}

    @app.get("/")
    def page():
        return FileResponse(WEB / "index.html")

    app.mount("/web", StaticFiles(directory=WEB), name="web")
    return app
