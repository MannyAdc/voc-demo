"""V5: the judge (specs/003-validation-review/spec.md).

claude-sonnet-5-5, with no tools, through the same recorded and ledgered path as the labeller, rates whether
each accepted development label's quote supports its label: `supports`, `partly` or `does_not_support`. It
reads the label, what the label covers, the cut complaint text and the quote, never the consumer's product
(V8). An answer outside the three ratings is `unparseable`.

The dry run rates its own 10 cases first. They are never reported, so it writes only its call counts, the
recording keys and the check of the ledger's input margin for this model (`config/budget.toml` asks a new
model for its own check). The owner reads the judge's ratings and reasons from those recordings with
`voc review sheet v5_dry_run`, to decide whether the rubric needs its one change. The main run rates every
accepted development label except the dry run's, once the owner's blind V5 ratings are imported and the
margin held, with the dry run's judge or its one change.

Three failed cases in a row stop a run, as for the labeller (B7). A run with any failure writes no results.
The judge's reasons are model text. They never reach a results file or a printout (V8, B21). Nothing runs live
without `--approved` (V9), and a live run needs its rubric committed and unchanged.
"""
import csv
import io
import json
import math
import re
import subprocess
import time
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from voc import review
from voc.backends import API_VERSION
from voc.baselines import cut_text
from voc.budget import CapReached, input_estimate, worst_case
from voc.costs import call_cost
from voc.pipeline import FAILED_IN_A_ROW
from voc.prompt import CLOSE_TAG, OPEN_TAG, BoundaryInText, boundary_reason
from voc.replay import MAX_RETRIES, ModelError, recording_key

RATINGS = review.CODES["v5"]
UNPARSEABLE = "unparseable"
PIECES = ("dry_run", "main")
JUDGE = "judge_v1"
JUDGE_NAME = re.compile(r"^judge_v([1-9]\d*)$")
FENCE = re.compile(r"\A```(?i:json)?[ \t]*\r?\n(.*?)\r?\n?```\Z", re.DOTALL)
# The expected cost assumes 4 bytes of prompt per input token and 600 output tokens per call, thinking
# included. The worst case, which the ledger reserves, assumes nothing.
BYTES_PER_TOKEN = 4
EXPECTED_OUTPUT_TOKENS = 600
FIELDS = ("complaint_id", "rating", "recording_key", "source", "input_tokens", "output_tokens")


class JudgeError(ValueError):
    """An error whose message is ours, so it is safe to print (it never holds data)."""


@dataclass(frozen=True)
class JudgeVersion:
    name: str
    instructions: str
    settings: dict


@dataclass(frozen=True)
class Item:
    """One case for the judge. The label, quote and text go only into the prompt and the owner's sheet."""
    complaint_id: str
    prompt: str
    label: str
    quote: str
    text: str


def _check_name(name):
    if not isinstance(name, str) or not JUDGE_NAME.match(name):
        raise JudgeError("a judge is named judge_v and a number, as in config/prompts/judge_v1.toml")
    return name


def load_judge(root, name=JUDGE):
    _check_name(name)
    with open(Path(root) / "config" / "prompts" / f"{name}.toml", "rb") as f:
        raw = tomllib.load(f)
    if raw.get("name") != name:
        raise JudgeError(f"config/prompts/{name}.toml names itself {raw.get('name')!r}")
    settings = dict(raw["settings"])
    if settings.get("api_version") != API_VERSION:
        raise JudgeError(f"the judge {name} is set for another API version than the backend sends")
    return JudgeVersion(name=name, instructions=raw["instructions"], settings=settings)


def build_judge_prompt(instructions, label, definition, quote, text):
    """The judge's prompt: the rubric, the label and what it covers, then the complaint and the quote, each
    between the fixed tags. A text or quote that holds a tag gets no prompt (B5)."""
    if boundary_reason(text) or boundary_reason(quote):
        raise BoundaryInText("the complaint text holds a boundary tag")
    return (f"{instructions}\n\nThe label: {label}\nWhat the label covers: {definition}\n\n"
            f"The complaint:\n{OPEN_TAG}\n{text}\n{CLOSE_TAG}\n\n"
            f"The quote, copied from the complaint:\n{OPEN_TAG}\n{quote}\n{CLOSE_TAG}")


def parse_rating(answer):
    """(rating, reason). The answer must be one JSON object with exactly a `rating` from the list and a text
    `reason`, optionally inside one code fence. Anything else is (`unparseable`, "")."""
    failed = (UNPARSEABLE, "")
    if not isinstance(answer, str):
        return failed
    body = answer.strip()
    fenced = FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        value = json.loads(body)
    except (ValueError, RecursionError):
        return failed
    if not isinstance(value, dict) or set(value) != {"rating", "reason"}:
        return failed
    if value["rating"] not in RATINGS or not isinstance(value["reason"], str):
        return failed
    return value["rating"], value["reason"]


def _ids(root, piece):
    """The dry run's frozen list, or every accepted development label except the dry run's (V5, V7)."""
    from voc.consistency import _old
    from voc.pipeline import _id_number
    from voc.validation import read_lists

    dry = read_lists(Path(root) / "splits")["dry_run"]
    if piece == "dry_run":
        return dry
    accepted = [c for c, r in _old(root).items() if r["decision"] == "accepted" and c not in set(dry)]
    return sorted(accepted, key=_id_number)


def items(root, piece, version=None):
    """The judge's cases, with their prompts, from the checked labels file and the staged table."""
    from voc.consistency import _old
    from voc.labels import load_labels
    from voc.pipeline import definitions

    version = version or load_judge(root)
    recorded, ids = _old(root), _ids(root, piece)
    staged = review._staged(root, ids)
    defined = definitions(load_labels(Path(root) / "config" / "labels.toml"))
    found = []
    for complaint_id in ids:
        old, text = recorded[complaint_id], cut_text(staged[complaint_id].narrative)[0]
        label, quote = old["accepted_label"], text[int(old["quote_start"]):int(old["quote_end"])]
        prompt = build_judge_prompt(version.instructions, label, defined[label], quote, text)
        found.append(Item(complaint_id, prompt, label, quote, text))
    return found


def judge(cases, call, backend_name, version):
    """Rate each case. Returns the rows (IDs, ratings, keys, tokens, no text) and the reasons by ID. Three
    failed cases in a row stop the run, so the cap is not spent on a setup that does not work (B7)."""
    model, settings = version.settings["model"], version.settings
    rows, reasons, in_a_row = [], {}, 0
    for case in cases:
        row = {"complaint_id": case.complaint_id, "recording_key": recording_key(backend_name, model, settings,
                                                                                 case.prompt)}
        try:
            reply = call(case.prompt)
        except (CapReached, ModelError) as err:
            rows.append({**row, "rating": "", "failed": "not_run_budget" if isinstance(err, CapReached)
                         else "model_error"})
            in_a_row += 1
            if in_a_row >= FAILED_IN_A_ROW:
                raise JudgeError(f"{in_a_row} cases in a row failed, so the run stopped and wrote nothing, so the "
                                 "cap is not spent on a setup that does not work") from None
            continue
        in_a_row = 0
        rating, reasons[case.complaint_id] = parse_rating(reply.text)
        rows.append({**row, "rating": rating, "source": reply.source, "input_tokens": reply.input_tokens,
                     "output_tokens": reply.output_tokens})
    return rows, reasons


def margin_pairs(rows, prompts, margin):
    """(reserved input estimate, real input tokens) for every answer with token counts, replayed ones too."""
    return [(input_estimate(prompts[r["complaint_id"]], margin), r["input_tokens"]) for r in rows
            if r.get("input_tokens") is not None]


def margin_check(pairs):
    """The margin held when no call used more input tokens than were reserved for it."""
    if not pairs:
        return {"margin_ok": None, "closest": None, "calls_checked": 0}
    closest = min(estimate - real for estimate, real in pairs)
    return {"margin_ok": closest >= 0, "closest": closest, "calls_checked": len(pairs)}


def estimate(cases, version, prices, margin, tokens_left):
    """The calls, the expected cost under the stated assumption, and the worst case the ledger will reserve,
    retries included. Refused when the worst case is over the tokens left."""
    model, limit = version.settings["model"], version.settings["max_tokens"]
    expected, worst = Decimal(0), 0
    for case in cases:
        size = len(case.prompt.encode("utf-8"))
        expected += call_cost(prices, model, math.ceil(size / BYTES_PER_TOKEN), EXPECTED_OUTPUT_TOKENS)
        worst += worst_case(case.prompt, limit, margin)
    worst *= MAX_RETRIES + 1
    if tokens_left is not None and worst > tokens_left:
        raise JudgeError(f"the cap has {tokens_left:,} tokens left, and this run needs up to {worst:,} in the "
                         "worst case, retries included")
    return {"calls": len(cases), "expected_cost_usd": str(expected), "worst_case_tokens": worst,
            "tokens_left": tokens_left}


def summarise(rows):
    """Each rating's count and share with its Wilson interval. Unparseable answers are counted apart."""
    from voc.consistency import wilson

    n = len(rows)
    if not n:
        raise JudgeError("there are no ratings to summarise")

    def share(k):
        low, high = wilson(k, n)
        return {"count": k, "share": k / n, "interval": [low, high]}

    return {"cases": n, "ratings": {code: share(sum(r["rating"] == code for r in rows)) for code in RATINGS},
            "unparseable": sum(r["rating"] == UNPARSEABLE for r in rows)}


def result_paths(root):
    folder = Path(root) / "results" / "validation"
    return {"dry_run": folder / "v5_dry_run.json", "csv": folder / "v5_judge.csv", "json": folder / "v5_judge.json"}


def _ratings_imported(root):
    """True when the owner's V5 ratings cover exactly V5's list."""
    from voc.validation import read_lists

    path = review.codes_path(root, "v5")
    if not path.exists():
        return False
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    wanted = read_lists(Path(root) / "splits")["v5"]
    return (sorted(r["complaint_id"] for r in rows) == sorted(wanted)
            and all(r["code"] in RATINGS for r in rows))


def _ready_for_main(root, paths, judge_name):
    """The main run waits for the dry run, the owner's ratings and a margin that held, and uses the dry run's
    judge or its one change (V5)."""
    if not paths["dry_run"].exists():
        raise JudgeError("the dry run has not been run. Run `voc judge dry-run` first")
    if not _ratings_imported(root):
        raise JudgeError("the owner's V5 ratings are not all imported. The main run waits for them (V5)")
    dry = json.loads(paths["dry_run"].read_text(encoding="utf-8"))
    if dry.get("margin_ok") is None:
        raise JudgeError("the dry run checked no call with token counts, so the input margin is not known. "
                         "It needs a dry run on the api backend")
    if dry.get("margin_ok") is not True:
        raise JudgeError("the dry run showed that the ledger's input margin does not hold for this model. The "
                         "owner decides a new margin first")
    dry_judge = _check_name(dry.get("judge", ""))
    allowed = {dry_judge, f"judge_v{int(JUDGE_NAME.match(dry_judge).group(1)) + 1}"}
    if judge_name not in allowed:
        raise JudgeError(f"the main run uses the dry run's judge or its one change: {' or '.join(sorted(allowed))}")


def _rubric_committed(root, name):
    """A live run needs its rubric committed and unchanged, so the rubric a result came from can be read."""
    path = f"config/prompts/{name}.toml"
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=root, capture_output=True)
    changed = subprocess.run(["git", "status", "--porcelain", "--", path], cwd=root, capture_output=True,
                             text=True)
    if tracked.returncode != 0 or changed.returncode != 0 or changed.stdout.strip():
        raise JudgeError(f"the judge's rubric {path} must be committed and unchanged before a live run")


def _rows_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row.get(key) is None else row[key] for key in FIELDS})
    return out.getvalue()


def format_estimate(figures, piece, version):
    left = figures["tokens_left"]
    return [f"V5 judge, {piece.replace('_', ' ')}: {version.name}, model {version.settings['model']}",
            f"calls: {figures['calls']}",
            f"expected cost: ${Decimal(figures['expected_cost_usd']):.4f}, assuming {BYTES_PER_TOKEN} bytes of "
            f"prompt per input token and {EXPECTED_OUTPUT_TOKENS} output tokens per call",
            f"worst case: {figures['worst_case_tokens']:,} tokens reserved at most, retries included",
            "tokens left: no ledger for the mock backend" if left is None else f"tokens left: {left:,}"]


def command(config, root, piece, approved, judge_name=JUDGE):
    """`voc judge dry-run` and `voc judge main`. Returns the lines to print."""
    from voc import backends
    from voc.budget import Ledger, load_config
    from voc.consistency import tokens_left
    from voc.costs import load_prices
    from voc.replay import Answer, Caller, Reply

    root = Path(root)
    _check_name(judge_name)
    backend_name = config.get("LLM_BACKEND", "")
    if backend_name not in ("api", "mock"):
        raise JudgeError("LLM_BACKEND must be api or mock")
    paths = result_paths(root)
    if piece == "dry_run" and paths["dry_run"].exists():
        raise JudgeError("the dry run has already been run, and it runs once")
    if piece == "main":
        if paths["csv"].exists() or paths["json"].exists():
            raise JudgeError("the judge's main run has already been written")
        _ready_for_main(root, paths, judge_name)
    version = load_judge(root, judge_name)
    cases = items(root, piece, version)
    prices = load_prices(root / "config" / "prices.toml")
    margin = load_config(root)["input_margin_tokens"]
    ledger, left = None, None
    if backend_name == "api":
        ledger = Ledger()
        left = tokens_left(ledger.state())
    lines = format_estimate(estimate(cases, version, prices, margin, left), piece, version)
    if not approved:
        return lines + ["no call made. Run it again with --approved once the owner has approved these figures"]
    model, settings = version.settings["model"], version.settings
    if backend_name == "mock":
        if not config.get("VOC_MOCK_FIXTURES"):
            raise JudgeError("the mock backend needs VOC_MOCK_FIXTURES, a JSON file of synthetic answers")
        fixtures = json.loads(Path(config["VOC_MOCK_FIXTURES"]).read_text(encoding="utf-8"))
        backend = backends.make_backend("mock", fixtures={i["prompt"]: Answer(i["text"], None, None, "end_turn")
                                                          for i in fixtures})

        def call(prompt):
            return Reply(backend(prompt, dict(settings)).text, "mock", None, None, 0, 0, 1)
    else:
        _rubric_committed(root, judge_name)
        backend = backends.make_backend("api", env=config, model=model)
        call = Caller("api", model, settings, backend=backend, mode="live", root=root, ledger=ledger).call
    used_before = ledger.state()["used"] if ledger else None
    started = time.monotonic()
    rows, _ = judge(cases, call, backend_name, version)  # the reasons stay in the recordings (V8)
    failed = sum(bool(r.get("failed")) for r in rows)
    if failed:
        kept = "The answers so far are recorded. " if backend_name == "api" else ""
        raise JudgeError(f"{failed} cases failed with a model error or at the cap, so no results are written. "
                         f"{kept}Run it again to finish")
    live = [r for r in rows if r.get("source") == "live" and r.get("input_tokens") is not None]
    cost = sum((call_cost(prices, model, r["input_tokens"], r["output_tokens"]) for r in live), Decimal(0))
    summary = {"piece": piece, "judge": version.name, "model": model, "backend": backend_name, "calls": len(rows),
               "live_calls": len(live), "replayed_calls": sum(r.get("source") == "replay" for r in rows),
               "unparseable": sum(r["rating"] == UNPARSEABLE for r in rows), "cost_usd": str(cost),
               "run_seconds": round(time.monotonic() - started, 1)}
    if ledger is not None:
        summary["ledger_charged_tokens"] = ledger.state()["used"] - used_before
    paths["dry_run"].parent.mkdir(parents=True, exist_ok=True)
    if piece == "dry_run":  # never reported: no ratings, only the margin, the counts and the keys
        prompts = {case.complaint_id: case.prompt for case in cases}
        summary.update(margin_check(margin_pairs(rows, prompts, margin)))
        summary["keys"] = {r["complaint_id"]: r["recording_key"] for r in rows}
        review._write_atomic(paths["dry_run"], json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8")
        return lines + format_dry_run(summary) + [f"written to {paths['dry_run'].relative_to(root).as_posix()}",
                                                  "the owner reads the ratings and reasons with "
                                                  "`voc review sheet v5_dry_run`"]
    summary.update(summarise(rows))
    review._write_atomic(paths["csv"], _rows_csv(rows), "utf-8")
    review._write_atomic(paths["json"], json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8")
    return lines + format_summary(summary) + [f"written to {p.relative_to(root).as_posix()}"
                                              for p in (paths["csv"], paths["json"])]


def format_dry_run(summary):
    return [f"calls: {summary['calls']}, unparseable: {summary['unparseable']}",
            f"input margin held: {summary['margin_ok']} ({summary['calls_checked']} calls checked)",
            f"cost: ${Decimal(summary['cost_usd']):.4f} for {summary['live_calls']} live calls, "
            f"{summary['replayed_calls']} replayed"]


def format_summary(summary):
    lines = [f"cases: {summary['cases']}"]
    for code, figure in summary["ratings"].items():
        low, high = figure["interval"]
        lines.append(f"{code}: {figure['count']} ({figure['share']:.1%}, 95% interval {low:.1%} to {high:.1%})")
    lines.append(f"unparseable: {summary['unparseable']}")
    lines.append(f"cost: ${Decimal(summary['cost_usd']):.4f} for {summary['live_calls']} live calls, "
                 f"{summary['replayed_calls']} replayed")
    return lines
