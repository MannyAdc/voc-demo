"""B14: load one pinned monthly export into the staged DuckDB table.

The load is safe to repeat. It is keyed on complaint ID: a complaint ID that
is already in the table is not added again, and its first row is kept.
Columns are typed, and the file is checked before anything is written: the
column names, the types, missing or repeated complaint IDs, and Product
values outside `config/labels.toml`. A failed check writes nothing.

B21: only counts leave this module. Error messages are ours, name only
columns and counts, and never hold a value from the file.
"""
from pathlib import Path

from voc.datafile import DataFileError
from voc.db import connect
from voc.repo_checks import CFPB_COLUMNS

DB_PATH = Path("data") / "voc.duckdb"
TABLE = "staged_complaints"

# CFPB column: (staged column, type). Dates and the timely flag are typed, the rest is text.
COLUMNS = {
    "Date received": ("date_received", "DATE"),
    "Product": ("product", "VARCHAR"),
    "Sub-product": ("sub_product", "VARCHAR"),
    "Issue": ("issue", "VARCHAR"),
    "Sub-issue": ("sub_issue", "VARCHAR"),
    "Consumer complaint narrative": ("narrative", "VARCHAR"),
    "Company public response": ("company_public_response", "VARCHAR"),
    "Company": ("company", "VARCHAR"),
    "State": ("state", "VARCHAR"),
    "ZIP code": ("zip_code", "VARCHAR"),
    "Tags": ("tags", "VARCHAR"),
    "Submitted via": ("submitted_via", "VARCHAR"),
    "Date sent to company": ("date_sent_to_company", "DATE"),
    "Company response to consumer": ("company_response", "VARCHAR"),
    "Timely response?": ("timely_response", "BOOLEAN"),
    "Complaint ID": ("complaint_id", "VARCHAR"),
}
assert set(COLUMNS) == set(CFPB_COLUMNS)
REQUIRED = ("Date received",)


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _blank(column):
    return rf"({column} IS NULL OR NOT regexp_matches({column}, '\S'))"


def _date(column):
    """The CFPB writes dates as 2026-07-01 or 07/01/2026 (07/01/26 is read too). Anything else is NULL."""
    return rf"""
    CASE
      WHEN regexp_matches({column}, '^\d{{4}}-\d{{2}}-\d{{2}}$') THEN try_strptime({column}, '%Y-%m-%d')::DATE
      WHEN regexp_matches({column}, '^\d{{1,2}}/\d{{1,2}}/\d{{4}}$') THEN try_strptime({column}, '%m/%d/%Y')::DATE
      WHEN regexp_matches({column}, '^\d{{1,2}}/\d{{1,2}}/\d{{2}}$') THEN try_strptime({column}, '%m/%d/%y')::DATE
    END"""


def _typed(raw, kind):
    if kind == "DATE":
        return _date(raw)
    if kind == "BOOLEAN":
        return f"CASE {raw} WHEN 'Yes' THEN true WHEN 'No' THEN false END"
    return raw


def _read(con, path):
    """The file as text, in a temp table, after the column check."""
    quoted = str(path).replace("'", "''")
    source = f"read_csv('{quoted}', header = true, all_varchar = true)"
    names = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    missing = len(set(CFPB_COLUMNS) - set(names))
    extra = len(set(names) - set(CFPB_COLUMNS))
    if missing or extra or len(names) != len(CFPB_COLUMNS):
        raise DataFileError(f"schema check failed: {missing} CFPB columns missing, {extra} other columns")
    con.execute(f"CREATE TEMP TABLE raw AS SELECT * FROM {source}")


def _check_types(con):
    for name, (_, kind) in COLUMNS.items():
        raw = _quote(name)
        if name in REQUIRED:
            empty = con.execute(f"SELECT count(*) FROM raw WHERE {_blank(raw)}").fetchone()[0]
            if empty:
                raise DataFileError(f"schema check failed: {empty} rows have no {name}")
        if kind == "VARCHAR":
            continue
        bad = con.execute(
            f"SELECT count(*) FROM raw WHERE NOT {_blank(raw)} AND ({_typed(raw, kind)}) IS NULL").fetchone()[0]
        if bad:
            raise DataFileError(f"schema check failed: {bad} values in {name} are not of type {kind}")


def _check_keys(con, labels):
    cid = _quote("Complaint ID")
    missing = con.execute(f"SELECT count(*) FROM raw WHERE {_blank(cid)}").fetchone()[0]
    if missing:
        raise DataFileError(f"{missing} rows have a missing complaint ID")
    repeated = con.execute(f"SELECT count(*) - count(DISTINCT {cid}) FROM raw").fetchone()[0]
    if repeated:
        raise DataFileError(f"{repeated} rows have a repeated complaint ID")
    con.execute("CREATE TEMP TABLE labels (name VARCHAR)")
    con.executemany("INSERT INTO labels VALUES (?)", [(name,) for name in labels])
    unknown = con.execute(
        'SELECT count(*) FROM raw WHERE "Product" IS NULL OR "Product" NOT IN (SELECT name FROM labels)').fetchone()[0]
    if unknown:
        raise DataFileError(f"{unknown} rows have a Product outside config/labels.toml")


def _create_table(con):
    columns = ", ".join(f"{column} {kind}" for column, kind in COLUMNS.values())
    con.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} ({columns}, source VARCHAR NOT NULL)")


def load_month(db_path, path, month, labels):
    """Load the checked export `path` as `month`. Returns counts only."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db_path)
    try:
        _read(con, path)
        _check_types(con)
        _check_keys(con, labels)
        typed = ", ".join(f"{_typed(_quote(name), kind)} AS {column}" for name, (column, kind) in COLUMNS.items())
        con.execute("BEGIN TRANSACTION")
        _create_table(con)
        before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        con.execute(f"""
            INSERT INTO {TABLE}
            SELECT {typed}, ? AS source FROM raw
            WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.complaint_id = raw."Complaint ID")""", [month])
        after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        con.execute("COMMIT")
        rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
        return {"rows": rows, "new": after - before, "already_loaded": rows - (after - before), "total": after}
    finally:
        con.close()
