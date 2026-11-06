"""Spec 004, J8, J5 and J16: Job A's logic. Its three tasks run in Databricks: `unpack`, `dbt` and `job_a`
(`cloud/job_a.yml`). The notebooks in `cloud/job_a/` stay thin and call these functions.

- The run's target is the last row of `runs/JUNE_RUNS.md` at the frozen commit, with the kind of its list's first
  row, `real` or `synthetic` (J16). With no row, Job A refuses. Both notebooks first check that the row is a first
  row, that its list is `splits/june/june.csv` and that its code is the code they run (`checked_target`). A later
  row (a resume, a reproduction or a second run) is refused until Job A can read the June ledger's use, in pull
  request 6 (owner decision, 6 November).
- `unpack` takes the one zip from the incoming folder and checks it against the pin of its kind: the zip's name,
  size and SHA-256, its one member's name and size, and the CSV's SHA-256 after it is written. Then it checks the
  CSV's shape: the CFPB header, the same number of fields on every row, and the pinned row count. So a row that
  would make Spark's FAILFAST parser fail, whose error can quote the row, is refused before dbt reads a byte, with
  fixed text only (owner decision, 5 November: no complaint text in any task output). A CSV that fails a check is
  removed, whatever the failure.
- The dbt task runs dbt itself, with `--log-level none --log-level-file none --no-write-json`, so dbt prints and
  writes nothing that could hold a row.
- `job_a` counts the rows and the narratives Spark reads from the file, with dbt's own read options, and refuses
  unless they are the counts pinned from the laptop's check (owner decision, 6 November). Then it checks the frozen
  sample's rows against `splits/june/` and computes the figures for the approval: the call count, the worst case as
  the test run reserves it (each prompt plus its output limit, retries included), the tokens left under the June
  ledger's own cap, `june_cap_tokens`, and the expected cost at the July test run's cost per 1,000, rounded up.
- `june_check` is the owner's check of the June zip on the laptop, a gate before the June run log's real row
  (`voc june-check`): `unpack` in a temporary folder inside the June data folder, then the counts of rows,
  narratives and fields with line breaks, and the frozen sample's rows against their hashes.
- A refusal carries no earlier exception, not even a hidden one, since Spark's or a parser's own error could quote
  a row (review of #94).

B21 and J5: nothing here prints, and every refusal holds fixed text and counts only.
"""
import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal
from pathlib import Path

from voc.frozen import (FIRST_KINDS, GATES, RUNS, JuneRunsError, check_gates, check_runs, code_hash, list_hash,
                        read_gates, read_runs)
from voc.repo_checks import CFPB_COLUMNS

CONTRACT = "voc-june-1"
MONTH = "june_2026"
COST = re.compile(r"[0-9]+\.[0-9]{2}")
CHUNK = 1 << 20
# The volume's folders (J8). The trigger watches INCOMING. The CSV goes to JUNE_FOLDER, outside it.
VOLUME = "/Volumes/workspace/default/voc_raw"
INCOMING = VOLUME + "/incoming"
JUNE_FOLDER = VOLUME + "/june"
# Spark's CSV reader has no field size limit by default, and Python's is 131,072 characters, so unpack raises it
# while it reads (review of #94, minor 3). The largest value a C long holds on every platform.
FIELD_LIMIT = 2**31 - 1
NARRATIVE = CFPB_COLUMNS.index("Consumer complaint narrative")
PRODUCT = CFPB_COLUMNS.index("Product")
COMPLAINT_ID = CFPB_COLUMNS.index("Complaint ID")
# Java's white space, as Spark's `rlike '\\S'` reads it (dbt/macros/targets.sql, `has_text`). Python's own `\\s`
# also holds other Unicode spaces, such as the no-break space, which Spark counts as text.
JAVA_SPACE = " \t\n\x0b\f\r"


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


def checked_target(root):
    """The run's target, refused unless Job A can run it from this checkout. Both notebooks call it first."""
    run_target = target_for(root)
    if run_target.entry_kind not in FIRST_KINDS:
        raise JobAError(f"the run log's last row is a {run_target.entry_kind} row, and Job A runs only a first row "
                        "until it can read the June ledger's use (pull request 6)")
    if run_target.list_hash != list_hash(root):
        raise JobAError("the run log's last row names a June list other than splits/june/june.csv")
    if code_hash(root) != run_target.code_hash:
        raise JobAError("the code this job runs is not the frozen code of the run log's last row")
    if run_target.entry_kind == "real":
        # Owner decision, 6 November: both gates passed for this code and the June pin before the row was written.
        try:
            check_gates(read_runs(Path(root) / RUNS), read_gates(Path(root) / GATES), pin_for(root, "real")["sha256"])
            error = None
        except JuneRunsError as err:
            error = str(err)
        if error:
            raise JobAError(f"the June gates were not passed first: {error}")
    return run_target


def pin_for(root, kind):
    from voc.datafile import load_pins

    if kind != "real":
        raise JobAError("the dry run's pin is named in pull request 9, so a synthetic run cannot start yet")
    pin = load_pins(Path(root) / "config" / "data_files.toml")[MONTH]
    for key in ("file_name", "size_bytes", "sha256", "rows", "narratives", "zip_file_name", "zip_size_bytes",
                "zip_sha256"):
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


def _records(path):
    """The CSV's rows after its header, refused with fixed text and counts unless the header is the CFPB header and
    every row has its number of fields."""
    previous = csv.field_size_limit(FIELD_LIMIT)
    rows = 0
    try:
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.reader(f, strict=True)
            try:
                header = next(reader, None)
                if header is None:
                    raise JobAError("the CSV is empty")
                if header != list(CFPB_COLUMNS):
                    raise JobAError("the CSV's header is not the CFPB header of the pin")
                for record in reader:
                    rows += 1
                    if len(record) != len(CFPB_COLUMNS):
                        raise JobAError(f"row {rows} of the CSV has {len(record)} fields, not {len(CFPB_COLUMNS)}")
                    yield record
                error = None
            except csv.Error:
                error = f"the CSV cannot be read as CSV after row {rows}"
            except UnicodeDecodeError:
                error = "the CSV is not UTF-8"
            if error:
                raise JobAError(error)
    finally:
        csv.field_size_limit(previous)


def _check_shape(path, pin):
    """The CFPB header, the same number of fields on every row, and the pinned row count. Counts only."""
    rows = sum(1 for _ in _records(path))
    if rows != pin["rows"]:
        raise JobAError(f"the CSV has {rows} rows, and the pin has {pin['rows']}")


def labels_value(labels_file):
    """The labels as JSON for dbt's variables. Job A's dbt command quotes its variables with apostrophes, so a label holding
    one is refused (review of #94)."""
    from voc.labels import load_labels

    names = [label.name for label in load_labels(labels_file)]
    if any("'" in name for name in names):
        raise JobAError("a label holds an apostrophe, which the dbt command's quoting cannot carry")
    return json.dumps(names)


def unpack(incoming, out, pin, labels_file):
    """Writes the pinned CSV to `out` and returns dbt's variables as strings, for the task values."""
    labels = labels_value(labels_file)
    path = _the_zip(incoming, pin)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    target_path = out / pin["file_name"]
    try:
        with zipfile.ZipFile(path) as archive:
            _write_member(archive, pin, target_path)
        _check_shape(target_path, pin)
        failure = None
    except JobAError:
        target_path.unlink(missing_ok=True)
        raise
    except Exception as err:  # noqa: BLE001, any failure removes the CSV and is refused with its type only
        target_path.unlink(missing_ok=True)
        failure = type(err).__name__
    if failure:
        raise JobAError(f"the zip cannot be read: {failure}")
    return {"month_file": str(target_path), "month_sha256": pin["sha256"], "month_rows": str(pin["rows"]),
            "labels": labels}


def has_text(value):
    """True where the value holds a character other than Java's white space, as Spark's `rlike '\\S'`."""
    return any(ch not in JAVA_SPACE for ch in value)


def file_counts(path):
    """The rows, the narratives with text, and the fields holding a line break or a carriage return on its own."""
    counts = {"rows": 0, "narratives": 0, "fields_with_line_breaks": 0, "fields_with_lone_returns": 0}
    for record in _records(path):
        counts["rows"] += 1
        counts["narratives"] += has_text(record[NARRATIVE])
        for field in record:
            counts["fields_with_line_breaks"] += "\n" in field or "\r" in field
            counts["fields_with_lone_returns"] += "\r" in field.replace("\r\n", "")
    return counts


def sample_counts(path, root):
    """The frozen June list's rows as Python reads them from the file: how many match their frozen content hash,
    and how many narratives hold a carriage return, which Spark may read otherwise (owner decision on minor 6)."""
    from voc.data import content_hash

    list_hash(root)
    data = (Path(root) / "splits" / "june" / "june.csv").read_text(encoding="utf-8")
    listed = dict(list(csv.reader(io.StringIO(data)))[1:])
    matching, returns = set(), set()
    for record in _records(path):
        cid = record[COMPLAINT_ID]
        if cid in listed:
            if content_hash(record[NARRATIVE], record[PRODUCT]) == listed[cid]:
                matching.add(cid)
            if "\r" in record[NARRATIVE]:
                returns.add(cid)
    return {"sampled_rows": len(listed), "sampled_matching": len(matching), "sampled_with_returns": len(returns)}


def june_check(zip_path, pin, labels_file, root=None, scratch=None):
    """The owner's check of the June zip before the June run log's row (owner decision, 6 November): `unpack` on a
    copy in a temporary folder inside `scratch`, the June data folder, then the file's counts, and with `root` the
    frozen sample's. Nothing is left behind, and nothing is printed."""
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        incoming = Path(folder) / "incoming"
        incoming.mkdir()
        shutil.copyfile(zip_path, incoming / Path(zip_path).name)
        values = unpack(incoming, Path(folder) / "june", pin, labels_file)
        counts = file_counts(values["month_file"])
        if root is not None:
            counts.update(sample_counts(values["month_file"], root))
        return counts


def format_june_check(counts, pin):
    lines = []
    for key in ("rows", "narratives"):
        verdict = "matches" if counts[key] == pin[key] else "DIFFERS"
        lines.append(f"{key}: {counts[key]} (pin: {pin[key]}, {verdict})")
    lines.append(f"fields with line breaks: {counts['fields_with_line_breaks']}")
    lines.append(f"fields with a lone carriage return: {counts['fields_with_lone_returns']}")
    return lines


def june_check_verdict(counts, pin):
    """The lines `voc june-check` prints, and whether the check passed. It passes only when the rows and the
    narratives match the pin, every sampled row matches its frozen hash, and no sampled narrative holds a carriage
    return. The two counts of line breaks in the whole file are shown for the record."""
    lines = format_june_check(counts, pin)
    matched = counts["sampled_matching"] == counts["sampled_rows"]
    lines.append(f"sampled rows matching their frozen hash: {counts['sampled_matching']} of {counts['sampled_rows']} "
                 f"({'matches' if matched else 'DIFFERS'})")
    lines.append(f"sampled narratives with a carriage return: {counts['sampled_with_returns']}")
    fails = [key for key in ("rows", "narratives") if counts[key] != pin[key]]
    if not matched:
        fails.append("sampled rows")
    if counts["sampled_with_returns"]:
        fails.append("a sampled narrative holds a carriage return, which Spark may read otherwise")
    lines.append("verdict: PASS" if not fails else "verdict: FAIL: " + ", ".join(fails))
    return lines, not fails


def count_sql(month_file):
    """Spark's counts of the file, read with dbt's options (dbt/macros/targets.sql, `month_file_rows`)."""
    if "'" in month_file or "\\" in month_file:
        raise JobAError("the CSV's path holds a character the SQL cannot carry")
    return ("select count(*) as rows, count_if(`Consumer complaint narrative` rlike '\\\\S') as narratives "
            f"from read_files('{month_file}', format => 'csv', header => true, multiLine => true, escape => '\"', "
            "mode => 'FAILFAST', inferColumnTypes => false, schemaEvolutionMode => 'none')")


def runner(session):
    """The notebook's Spark session as a function from SQL to rows, for the two reads below."""
    return lambda sql: session.sql(sql).collect()


def spark_counts(run_sql, month_file):
    """Spark's counts of the file. Spark's own error could quote a row, so any failure is refused with fixed text
    only (review of the fix round, serious 3)."""
    sql = count_sql(month_file)
    try:
        row = run_sql(sql)[0]
        counts = int(row["rows"]), int(row["narratives"])
    except Exception:  # noqa: BLE001, refused below, outside the except block, so no exception is kept
        counts = None
    if counts is None:
        raise JobAError("Spark could not count the June file")
    return counts


def listed_ids(root):
    data = (Path(root) / "splits" / "june" / "june.csv").read_text(encoding="utf-8")
    return [row[0] for row in list(csv.reader(io.StringIO(data)))[1:]]


def sample_sql(listed):
    # Real IDs are numbers, and the dry run's synthetic ones start with SYN- (pull request 9). They go into the SQL.
    if not listed or not all(re.fullmatch(r"(SYN-)?[0-9]{1,19}", cid) for cid in listed):
        raise JobAError("the frozen June list holds an ID that is not a complaint ID")
    return ("select complaint_id, product, narrative from workspace.voc_june.stg_complaints where complaint_id in ("
            + ",".join(f"'{cid}'" for cid in listed) + ")")


def spark_rows(run_sql, listed):
    """The frozen sample's rows from the June tables, refused with fixed text only on any failure."""
    sql = sample_sql(listed)
    try:
        rows = [tuple(r) for r in run_sql(sql)]
    except Exception:  # noqa: BLE001, refused below, outside the except block, so no exception is kept
        rows = None
    if rows is None:
        raise JobAError("Spark could not read the June sample's rows")
    return rows


def checked_counts(pin, rows, narratives):
    """Refused unless Spark read the pinned counts from the laptop's check (owner decision, 6 November)."""
    if rows != pin["rows"]:
        raise JobAError(f"Spark read {rows} rows, and the pin has {pin['rows']}")
    if narratives != pin["narratives"]:
        raise JobAError(f"Spark read {narratives} narratives, and the pin has {pin['narratives']}")


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


def expected_cost(per_1000, complaints):
    """Rounded up to the cent, so it never shows less than the expected cost (review of #94)."""
    return f"{(per_1000 * complaints / 1000).quantize(Decimal('0.01'), rounding=ROUND_UP)}"


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
    cap = config.get("june_cap_tokens")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        raise JobAError("config/budget.toml needs a whole number june_cap_tokens")
    return {"complaints": len(rows), "calls": len(rows), "worst_case_tokens": per_try * (MAX_RETRIES + 1),
            "tokens_left_under_cap": cap - used_tokens, "expected_cost_usd": expected_cost(per_1000, len(rows))}


def exit_value(run_target, pin, run_figures):
    """J16 item 4: exactly the contract's keys, as compact JSON with sorted keys."""
    if not COST.fullmatch(str(run_figures["expected_cost_usd"])):
        raise JobAError("the expected cost must be a decimal with two places")
    value = {"contract": CONTRACT, "kind": run_target.kind, "source_sha256": pin["sha256"],
             "zip_sha256": pin["zip_sha256"], "june_list_sha256": run_target.list_hash,
             "code_sha256": run_target.code_hash, **{k: run_figures[k] for k in (
                 "complaints", "calls", "worst_case_tokens", "tokens_left_under_cap", "expected_cost_usd")}}
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
