"""B14 and B21: run the dbt project in `dbt/` and print only counts and check names.

dbt runs in a child process with its output thrown away, because dbt and
DuckDB can echo raw rows in their messages. What is printed comes from
`run_results.json` (node names, which are ours, statuses and counts) and from
row counts of our own models. Usage stats are off (B7), and credentials and
proxy settings never reach the child process.

T021: `--target databricks` runs the same project on a Databricks SQL warehouse,
on two synthetic seeds only. It refuses before dbt starts unless the seeds are
there, every seeded complaint ID is SYN-, and the test list seed is a byte copy
of the checked splits/test.csv. Only that target gets the connection variables.

With `--month` (owner decision, 31 October 2026) it runs the same models on a real pinned export that the
owner uploaded to the volume /Volumes/<catalog>/default/voc_raw. The only seed is then the test list. dbt
gets the file's path, its pinned SHA-256 and, where recorded, its row count, and Databricks checks them before
any staged model is built. After a passing build, one query per model reads the row counts back.

T017: `voc dbt lineage` runs `dbt parse` the same way and writes docs/LINEAGE.md,
a Mermaid graph of node names and edges only, so it holds no local path.
"""
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from voc.datafile import load_pins
from voc.db import connect
from voc.load import DB_PATH

PROJECT = Path("dbt")
# dbt's output can hold complaint text (run_results.json, dbt.log) and local paths (manifest.json),
# so it goes in the git-ignored data folder, next to the DuckDB file, which the read guard protects.
TARGET = DB_PATH.parent / "dbt" / "target"
LOGS = DB_PATH.parent / "dbt" / "logs"
MODELS = ("stg_complaints", "curated_complaints")
CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
QUIET = {
    "DBT_ENGINE_SEND_ANONYMOUS_USAGE_STATS": "False",  # dbt Core 1.11 and later
    "DBT_SEND_ANONYMOUS_USAGE_STATS": "False",  # dbt Core 1.10 and earlier
    "DO_NOT_TRACK": "1",
}
COMMANDS = {"build": ["build"], "docs": ["docs", "generate"], "parse": ["parse"]}
# B17: the models read the test IDs from this list, next to the dbt folder (dbt/macros/test_set.sql).
TEST_LIST = Path("splits") / "test.csv"
MANIFEST = Path("splits") / "manifest.json"
# T021: the Databricks target's profile folder, its connection variables and its seeds.
DATABRICKS_PROFILES = PROJECT / "databricks"
CONNECTION_VARS = ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
SEEDS = PROJECT / "seeds"
STAGED_SEED, TEST_SEED = "staged_complaints.csv", "test_list.csv"
TARGETS = ("local", "databricks")
# The real exports: their pins, the volume they are uploaded to, and the schema the models are built in.
PINS = Path("config") / "data_files.toml"
VOLUME = "/Volumes/{catalog}/default/voc_raw/"
REAL_SCHEMA = "voc_cfpb"
PLAIN = re.compile(r"[A-Za-z0-9_]+")
# T017: the lineage graph, written with node names only, so it can be committed.
LINEAGE = Path("docs") / "LINEAGE.md"
# The node kinds drawn in the lineage graph, in order, with their label and Mermaid shape.
KINDS = {"source": ("source", '[("', '")]'), "seed": ("seed", '[/"', '"/]'),
         "model": ("model", '["', '"]'), "test": ("test", '{{"', '"}}')}
SAFE_NAME = re.compile(r"[A-Za-z0-9_.]+")


class DbtError(Exception):
    """An error whose message is ours, so it is safe to print."""


def dbt_env(base):
    """The child's environment: no credentials, no Databricks settings, no proxy, usage stats off."""
    env = {name: value for name, value in base.items()
           if name not in CREDENTIAL_VARS and not name.upper().startswith("DATABRICKS_")
           and not (name.lower().endswith("_proxy") and name.lower() != "no_proxy")}
    env.update(QUIET)
    return env


def check_seeds(root):
    """T021: the Databricks target gets synthetic rows only. Raises before dbt starts if not.

    The seed folder must hold exactly the two seeds. The test list seed is a byte copy of
    splits/test.csv, already checked (B17). Every complaint ID in both seeds starts with SYN-.
    The messages name files, never IDs or values.
    """
    folder = Path(root) / SEEDS
    stop = "so nothing was sent to Databricks"
    if not folder.is_dir():
        raise DbtError(f"{SEEDS.as_posix()} is missing: the Databricks target needs the synthetic seeds, "
                       f"written by scripts/databricks_fixture_build.py, {stop}")
    found = sorted(path.name for path in folder.iterdir())
    if found != sorted((STAGED_SEED, TEST_SEED)):
        raise DbtError(f"{SEEDS.as_posix()} must hold exactly {STAGED_SEED} and {TEST_SEED}, {stop}")
    try:
        rows = list(csv.reader(io.StringIO((folder / STAGED_SEED).read_text(encoding="utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        raise DbtError(f"{STAGED_SEED} is not a valid seed, {stop}") from None
    if not rows or rows[0][:1] != ["complaint_id"] or len(rows) < 2:
        raise DbtError(f"{STAGED_SEED} must start with a complaint_id column and hold rows, {stop}")
    if any(not row or not row[0].startswith("SYN-") for row in rows[1:]):
        raise DbtError(f"{STAGED_SEED} holds a complaint ID that is not synthetic (SYN-), {stop}")
    if (folder / TEST_SEED).read_bytes() != (Path(root) / TEST_LIST).read_bytes():
        raise DbtError(f"{TEST_SEED} is not a byte copy of {TEST_LIST.as_posix()}, {stop}")
    # Added in the review of #43: the test list seed holds IDs too, so they must be synthetic as well.
    # check_test_list has already read it as UTF-8 with a complaint_id column first.
    test_rows = list(csv.reader(io.StringIO((folder / TEST_SEED).read_text(encoding="utf-8"))))[1:]
    if any(not row[0].startswith("SYN-") for row in test_rows):
        raise DbtError(f"{TEST_SEED} holds a complaint ID that is not synthetic (SYN-), {stop}")


def check_month_seeds(root):
    """A month build reads its rows from the volume, so the only seed is the test list, a byte copy of the
    checked splits/test.csv. Raises before dbt starts if not."""
    folder = Path(root) / SEEDS
    stop = "so nothing was sent to Databricks"
    if not folder.is_dir() or sorted(path.name for path in folder.iterdir()) != [TEST_SEED]:
        raise DbtError(f"{SEEDS.as_posix()} must hold only {TEST_SEED} for a month build, {stop}")
    if (folder / TEST_SEED).read_bytes() != (Path(root) / TEST_LIST).read_bytes():
        raise DbtError(f"{TEST_SEED} is not a byte copy of {TEST_LIST.as_posix()}, {stop}")


def catalog_name(base):
    """The Unity Catalog name, `workspace` unless DATABRICKS_CATALOG is set. It goes into SQL, so it must be plain."""
    name = base.get("DATABRICKS_CATALOG") or "workspace"
    if not PLAIN.fullmatch(name):
        raise DbtError("DATABRICKS_CATALOG must be plain letters, digits and _, so nothing was sent to Databricks")
    return name


def month_vars(root, month, catalog):
    """The dbt variables for a month build, from the month's pin in config/data_files.toml."""
    pin = load_pins(Path(root) / PINS)[month]
    return {"month": month, "month_file": VOLUME.format(catalog=catalog) + pin["file_name"],
            "month_sha256": pin["sha256"], "month_rows": pin.get("rows", 0)}


def _databricks_query(env, sql):
    """One query on the SQL warehouse, with the connection from `env`. Returns the rows as tuples."""
    from databricks import sql as databricks_sql  # in the databricks dependency group only

    with databricks_sql.connect(server_hostname=env["DATABRICKS_HOST"], http_path=env["DATABRICKS_HTTP_PATH"],
                                access_token=env["DATABRICKS_TOKEN"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return [tuple(row) for row in cursor.fetchall()]


def databricks_counts(env, catalog):
    """B21: the row counts of the real models, by month. Counts and our own month names only."""
    schema = f"{catalog}.{REAL_SCHEMA}"
    months = _databricks_query(env, f"select source, count(*) from {schema}.stg_complaints "
                                    "group by source order by source")
    if any(not PLAIN.fullmatch(str(source)) for source, _ in months):
        raise DbtError("stg_complaints holds a month name that is not ours")
    curated = _databricks_query(env, f"select count(*) from {schema}.curated_complaints")
    return ["stg_complaints by month: " + ", ".join(f"{source} {int(n)} rows" for source, n in months),
            f"curated_complaints: {int(curated[0][0])} rows"]


def databricks_env(base):
    """T021: the child's environment for the Databricks target: the safe one, plus the connection."""
    missing = [name for name in CONNECTION_VARS if not base.get(name)]
    if missing:
        raise DbtError(f"{', '.join(missing)} not set, so nothing was sent to Databricks")
    env = dbt_env(base)
    env.update({name: base[name] for name in (*CONNECTION_VARS, "DATABRICKS_CATALOG") if base.get(name)})
    return env


def check_test_list(root):
    """B17: check splits/test.csv against its SHA-256 and count in splits/manifest.json. Returns the count.

    The hash is of the file's bytes, as in voc.data. A missing, empty, header-only, malformed or swapped
    list would make the models leave out the wrong rows or none, so each one stops dbt before it starts.
    """
    path = Path(root) / TEST_LIST
    name, manifest_name = TEST_LIST.as_posix(), MANIFEST.as_posix()
    stop = "(B17). dbt did not run"
    if not path.is_file():
        raise DbtError(f"{name} is missing, so the dbt models cannot leave out the test rows {stop}")
    try:
        expected = json.loads((Path(root) / MANIFEST).read_text(encoding="utf-8"))["lists"]["test"]
        digest, count = expected["sha256"], expected["count"]
    except (OSError, ValueError, KeyError, TypeError):
        raise DbtError(f"{manifest_name} is missing or has no hash for the test list, so {name} cannot be "
                       f"checked {stop}") from None
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise DbtError(f"{name} does not match its hash in {manifest_name} {stop}")
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        raise DbtError(f"{name} is not a valid test list {stop}") from None
    if rows and (rows[0] != ["complaint_id", "content_hash"]
                 or any(len(row) != 2 or not row[0].strip() for row in rows[1:])):
        raise DbtError(f"{name} is not a valid test list {stop}")
    if len(rows) <= 1:
        raise DbtError(f"{name} holds no test IDs, so the dbt models would leave out nothing {stop}")
    if len(rows) - 1 != count:
        raise DbtError(f"{name} does not match its count in {manifest_name} {stop}")
    return count


def _run(root, action, labels, target_name="local", month=None):
    # B17: without a checked test list the models cannot leave out the test rows, so dbt does not start.
    check_test_list(root)
    project = (Path(root) / PROJECT).resolve()
    profiles = project
    extra = {}
    if target_name == "databricks":
        if month:
            check_month_seeds(root)
            extra = month_vars(root, month, catalog_name(os.environ))
        else:
            check_seeds(root)
        env = databricks_env(os.environ)
        # The real exports are built in their own schema. The synthetic seeds keep the profile's default.
        env.pop("VOC_DBX_SCHEMA", None)
        if month:
            env["VOC_DBX_SCHEMA"] = REAL_SCHEMA
        profiles = (Path(root) / DATABRICKS_PROFILES).resolve()
    else:
        env = dbt_env(os.environ)
    target = (Path(root) / TARGET).resolve()
    results = target / "run_results.json"
    results.unlink(missing_ok=True)
    args = [sys.executable, "-c", "from dbt.cli.main import cli; cli()", *COMMANDS[action],
            "--project-dir", str(project), "--profiles-dir", str(profiles),
            "--target-path", str(target), "--log-path", str((Path(root) / LOGS).resolve()),
            # B17: the test-set flag is always passed off. It overrides dbt_project.yml, and no command turns it on.
            "--vars", json.dumps({"labels": labels, "final": False, **extra})]
    if target_name == "databricks":
        args += ["--target", "databricks"]
    env["VOC_DBT_DB"] = str((Path(root) / DB_PATH).resolve())
    code = subprocess.run(args, env=env, cwd=project, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    return code, results


def _row_counts(root):
    con = connect(Path(root) / DB_PATH)
    try:
        found = {name for (name,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
        return {name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in MODELS if name in found}
    finally:
        con.close()


def build(root, labels, target_name="local", month=None):
    """Run `dbt build`. Returns the lines to print and whether the build passed."""
    if month and target_name != "databricks":
        raise DbtError("--month needs --target databricks, so nothing was run")
    code, results = _run(root, "build", labels, target_name, month)
    if not results.is_file():
        raise DbtError(f"dbt exited with code {code} before it wrote any result")
    nodes = json.loads(results.read_text(encoding="utf-8"))["results"]
    tally = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    kinds = {"seed": 0, "model": 0, "test": 0}
    problems = []
    for node in nodes:
        kind, _, name = node["unique_id"].split(".")[:3]
        kinds[kind] = kinds.get(kind, 0) + 1
        status = node["status"]
        if status in ("success", "pass"):
            tally["passed"] += 1
        elif status == "skipped":
            tally["skipped"] += 1
        elif status == "fail":
            tally["failed"] += 1
            problems.append(f"failed: {kind} {name} ({node.get('failures') or 0} rows)")
        else:
            tally["errors"] += 1
            problems.append(f"error: {kind} {name} ({status})")
    seeds = f"{kinds['seed']} seeds, " if kinds["seed"] else ""
    lines = [f"dbt build: {seeds}{kinds['model']} models, {kinds['test']} data tests. "
             + ", ".join(f"{key} {value}" for key, value in tally.items())]
    lines += problems
    # The row counts read the local DuckDB file, so they are for the local target only.
    counts = _row_counts(root) if target_name == "local" else {}
    if counts:
        lines.append(", ".join(f"{name}: {n} rows" for name, n in counts.items()))
    passed = code == 0 and not problems
    # A month build reads its counts back from Databricks, only after it passed.
    if month and passed:
        lines += databricks_counts(databricks_env(os.environ), catalog_name(os.environ))
    return lines, passed


def docs(root, labels):
    """Run `dbt docs generate`, which writes the lineage graph files."""
    code, _ = _run(root, "docs", labels)
    target = Path(root) / TARGET
    written = [name for name in ("manifest.json", "catalog.json", "index.html") if (target / name).is_file()]
    if code != 0:
        raise DbtError(f"dbt docs exited with code {code}")
    return [f"dbt docs: {', '.join(written)} written to {TARGET.as_posix()}. "
            "They hold local paths, so do not commit them. For a lineage graph with no paths, "
            "run `voc dbt lineage`."]


def _lineage_nodes(manifest):
    """The graph's nodes as {unique_id: (kind, name)} and its edges as sorted (parent, child) pairs.

    Only names are read, never paths, SQL or descriptions. A source is named `source_name.name`.
    A name that is not plain letters, digits, `_` and `.` stops the command, so nothing else reaches the file.
    """
    nodes = {}
    # A node that is off for this target is left out. dbt lists a data test of a model that is off,
    # with its own config off (found while building the real exports on Databricks).
    for uid, node in manifest.get("sources", {}).items():
        if node.get("config", {}).get("enabled", True) is not False:
            nodes[uid] = ("source", f"{node['source_name']}.{node['name']}")
    for uid, node in manifest.get("nodes", {}).items():
        if node["resource_type"] in KINDS and node.get("config", {}).get("enabled", True) is not False:
            nodes[uid] = (node["resource_type"], node["name"])
    for kind, name in nodes.values():
        if not SAFE_NAME.fullmatch(name):
            raise DbtError(f"a dbt {kind} name holds characters the lineage graph does not allow")
    edges = sorted({(parent, uid) for uid, node in manifest.get("nodes", {}).items() if uid in nodes
                    for parent in node.get("depends_on", {}).get("nodes", []) if parent in nodes})
    return nodes, edges


def lineage(root, labels):
    """T017: run `dbt parse` and write docs/LINEAGE.md, a Mermaid graph of node names and edges only.

    `dbt docs` files hold local paths, so they cannot be committed. This file can. It is built from
    `manifest.json` with names only, and it has no date, so a re-run on the same project changes nothing.
    """
    code, _ = _run(root, "parse", labels)
    path = Path(root) / TARGET / "manifest.json"
    if code != 0 or not path.is_file():
        raise DbtError(f"dbt parse exited with code {code}")
    nodes, edges = _lineage_nodes(json.loads(path.read_text(encoding="utf-8")))
    order = list(KINDS)
    ordered = sorted(nodes, key=lambda uid: (order.index(nodes[uid][0]), nodes[uid][1]))
    ids = {uid: f"n{number}" for number, uid in enumerate(ordered, start=1)}
    counts = {kind: sum(1 for k, _ in nodes.values() if k == kind) for kind in KINDS}
    lines = ["# dbt lineage", "",
             "Written by `voc dbt lineage` from dbt's `manifest.json` (`dbt parse`). Do not edit it by hand.",
             "It holds node names and edges only: no paths, no SQL and no descriptions."]
    if counts["seed"] == 0:
        lines += ["It shows the local DuckDB target. The two seeds of the Databricks target (T021) are off there,",
                  "so they are not drawn."]
    # Added in the review of #48: the inputs dbt reads without tracking them as nodes.
    lines += ["dbt does not track two inputs, so the graph does not draw them: `splits/test.csv`, read by the",
              "test set macro, and the label list, passed in the `labels` variable and read by the",
              "`product_in_label_list` data test.", "",
              f"{counts['source']} sources, {counts['seed']} seeds, {counts['model']} models, "
             f"{counts['test']} data tests, {len(edges)} edges.", "",
             "```mermaid", "graph LR"]
    for uid in ordered:
        kind, name = nodes[uid]
        label, start, end = KINDS[kind]
        lines.append(f"  {ids[uid]}{start}{label}: {name}{end}")
    lines += [f"  {ids[parent]} --> {ids[child]}" for parent, child in edges]
    lines.append("```")
    out = Path(root) / LINEAGE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return [f"dbt lineage: {counts['source']} sources, {counts['seed']} seeds, {counts['model']} models, "
            f"{counts['test']} data tests, {len(edges)} edges. Written to {LINEAGE.as_posix()}."]
