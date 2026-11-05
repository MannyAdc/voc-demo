"""Spec 004, J8, J5 and J16: Job A's logic. Its three tasks run in Databricks: `unpack`, `dbt` and `job_a`
(`cloud/job_a.yml`). The notebooks in `cloud/job_a/` stay thin and call these functions.

- The run's target is the last row of `runs/JUNE_RUNS.md` at the frozen commit, with the kind of its list's first
  row, `real` or `synthetic` (J16). With no row, Job A refuses.
- `unpack` takes the one zip from the incoming folder and checks it against the pin of its kind: the zip's name,
  size and SHA-256, its one member's name and size, and the CSV's SHA-256 after it is written. Then it checks the
  CSV's shape: the CFPB header, the same number of fields on every row, and the pinned row count. So a row that
  would make Spark's FAILFAST parser fail, whose error can quote the row, is refused before dbt reads a byte, with
  fixed text only (owner decision, 5 November: no complaint text in any task output). A CSV that fails a check is
  removed.
- The dbt task runs dbt itself, with `--log-level none --log-level-file none --no-write-json`, so dbt prints and
  writes nothing that could hold a row.
- `job_a` checks the frozen sample's rows against `splits/june/` and computes the figures for the approval: the
  call count, the worst case as the test run reserves it (each prompt plus its output limit, retries included),
  the tokens left under the June ledger's cap, and the expected cost at the July test run's cost per 1,000.

B21 and J5: nothing here prints, and every refusal holds fixed text and counts only.
"""
import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from voc.frozen import RUNS, check_runs, list_hash, read_runs
from voc.repo_checks import CFPB_COLUMNS

CONTRACT = "voc-june-1"
MONTH = "june_2026"
COST = re.compile(r"[0-9]+\.[0-9]{2}")
CHUNK = 1 << 20


class JobAError(ValueError):
    """A refusal whose message holds only fixed text and counts (B21, J5)."""


@dataclass(frozen=True)
class Target:
    kind: str
    entry_kind: str
    list_hash: str
    code_hash: str
    row: int


def target(runs_file, real_list_hash):
    """The run's target: the June run log's last row, with the kind of its list's first row."""
    entries = read_runs(runs_file)
    if not entries:
        raise JobAError("runs/JUNE_RUNS.md has no row yet, so Job A has nothing to run")
    check_runs(entries, real_list_hash=real_list_hash)
    last = entries[-1]
    first = next(e for e in entries if e.list_hash == last.list_hash)
    return Target(kind=first.kind, entry_kind=last.kind, list_hash=last.list_hash, code_hash=last.code_hash,
                  row=len(entries))


def target_for(root):
    return target(Path(root) / RUNS, real_list_hash=list_hash(root))


def pin_for(root, kind):
    from voc.datafile import load_pins

    if kind != "real":
        raise JobAError("the dry run's pin is named in pull request 9, so a synthetic run cannot start yet")
    pin = load_pins(Path(root) / "config" / "data_files.toml")[MONTH]
    for key in ("file_name", "size_bytes", "sha256", "rows", "zip_file_name", "zip_size_bytes", "zip_sha256"):
        if key not in pin:
            raise JobAError(f"the June pin has no {key}")
    return pin


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _the_zip(incoming, pin):
    files = sorted(p for p in Path(incoming).iterdir() if p.is_file())
    if len(files) != 1:
        raise JobAError(f"the incoming folder must hold exactly one file, it holds {len(files)}")
    path = files[0]
    if (path.name != pin["zip_file_name"] or path.stat().st_size != pin["zip_size_bytes"]
            or _sha256(path) != pin["zip_sha256"]):
        raise JobAError("the zip is not the pinned zip: its name, size or SHA-256 differs from the pin")
    return path


def _write_member(archive, pin, target_path):
    names = archive.namelist()
    if names != [pin["file_name"]]:
        raise JobAError(f"the zip must hold exactly the pinned CSV, it holds {len(names)} entries")
    if archive.getinfo(pin["file_name"]).file_size != pin["size_bytes"]:
        raise JobAError("the CSV in the zip is not the pinned CSV: its size differs from the pin")
    digest = hashlib.sha256()
    with archive.open(pin["file_name"]) as source, open(target_path, "wb") as out:
        for block in iter(lambda: source.read(CHUNK), b""):
            digest.update(block)
            out.write(block)
    if digest.hexdigest() != pin["sha256"]:
        raise JobAError("the CSV is not the pinned CSV: its SHA-256 differs from the pin")


def _check_shape(path, pin):
    """The CFPB header, the same number of fields on every row, and the pinned row count. Counts only."""
    rows = 0
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, strict=True)
        try:
            header = next(reader)
            if header != list(CFPB_COLUMNS):
                raise JobAError("the CSV's header is not the CFPB header of the pin")
            for record in reader:
                rows += 1
                if len(record) != len(CFPB_COLUMNS):
                    raise JobAError(f"row {rows} of the CSV has {len(record)} fields, not {len(CFPB_COLUMNS)}")
        except csv.Error:
            raise JobAError(f"the CSV cannot be read as CSV after row {rows}") from None
        except UnicodeDecodeError:
            raise JobAError("the CSV is not UTF-8") from None
    if rows != pin["rows"]:
        raise JobAError(f"the CSV has {rows} rows, and the pin has {pin['rows']}")


def unpack(incoming, out, pin, labels_file):
    """Writes the pinned CSV to `out` and returns dbt's variables as strings, for the task values."""
    from voc.labels import load_labels

    path = _the_zip(incoming, pin)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    target_path = out / pin["file_name"]
    try:
        with zipfile.ZipFile(path) as archive:
            _write_member(archive, pin, target_path)
        _check_shape(target_path, pin)
    except (JobAError, zipfile.BadZipFile, OSError) as err:
        target_path.unlink(missing_ok=True)
        if isinstance(err, JobAError):
            raise
        raise JobAError(f"the zip cannot be read: {type(err).__name__}") from None
    labels = [label.name for label in load_labels(labels_file)]
    return {"month_file": str(target_path), "month_sha256": pin["sha256"], "month_rows": str(pin["rows"]),
            "labels": json.dumps(labels)}


def checked_sample(root, rows):
    """`rows` are (complaint_id, product, narrative) from the June tables. Refused unless they are exactly the frozen
    June list, each with its content hash. Returns the count."""
    from voc.data import content_hash

    folder = Path(root) / "splits" / "june"
    listed_hash = list_hash(root)
    data = (folder / "june.csv").read_bytes()
    if hashlib.sha256(data).hexdigest() != listed_hash:
        raise JobAError("splits/june/june.csv does not match its hash")
    listed = dict(list(csv.reader(io.StringIO(data.decode("utf-8"))))[1:])
    given = {cid: (product, narrative) for cid, product, narrative in rows}
    if len(given) != len(rows):
        raise JobAError("the June rows repeat a complaint ID")
    extra, missing = set(given) - set(listed), set(listed) - set(given)
    if extra:
        raise JobAError(f"{len(extra)} June rows are not in the frozen June list")
    if missing:
        raise JobAError(f"{len(missing)} complaints of the frozen June list are missing from the June tables")
    changed = sum(content_hash(narrative, product) != listed[cid] for cid, (product, narrative) in given.items())
    if changed:
        raise JobAError(f"{changed} June rows do not match their content hash in the frozen June list")
    return len(rows)


def figures(root, rows, used_tokens):
    """The figures for the approval, from the June rows. The worst case is the test run's (voc.testrun)."""
    from voc import pipeline
    from voc.baselines import cut_text
    from voc.budget import load_config, worst_case
    from voc.labels import load_labels
    from voc.prompt import build_prompt
    from voc.replay import MAX_RETRIES

    root = Path(root)
    version = pipeline.load_prompt_version(root, "v1")
    labels = load_labels(root / "config" / "labels.toml")
    names, defined = [label.name for label in labels], pipeline.definitions(labels)
    config = load_config(root)
    per_try = sum(worst_case(build_prompt(version.instructions, names, cut_text(narrative)[0], complaint_id=cid,
                                          definitions=defined).prompt, version.settings["max_tokens"],
                             config["input_margin_tokens"]) for cid, _, narrative in rows)
    summary = json.loads((root / "results" / "eval" / "v1_test.json").read_text(encoding="utf-8"))
    per_1000 = Decimal(summary["llm"]["cost_per_1000_usd"])
    expected = (per_1000 * len(rows) / 1000).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"complaints": len(rows), "calls": len(rows), "worst_case_tokens": per_try * (MAX_RETRIES + 1),
            "tokens_left_under_cap": config["cap_tokens"] - used_tokens, "expected_cost_usd": f"{expected}"}


def exit_value(run_target, pin, run_figures):
    """J16 item 4: exactly the contract's keys, as compact JSON with sorted keys."""
    if not COST.fullmatch(str(run_figures["expected_cost_usd"])):
        raise JobAError("the expected cost must be a decimal with two places")
    value = {"contract": CONTRACT, "kind": run_target.kind, "source_sha256": pin["sha256"],
             "zip_sha256": pin["zip_sha256"], "june_list_sha256": run_target.list_hash,
             "code_sha256": run_target.code_hash, **{k: run_figures[k] for k in (
                 "complaints", "calls", "worst_case_tokens", "tokens_left_under_cap", "expected_cost_usd")}}
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
