"""B22: data facts from the export, as counts only.

B21: no complaint text ever leaves this module. Only counts, lengths, years
and category values are returned. A category value seen fewer than
MIN_COUNT times, or longer than MAX_LEN characters, is never shown. It is
counted under RARE_VALUE instead, because a badly split row could put
complaint text into a category column.

The profile also compares, for each Product, the rows that have text with
all rows, on the fields every complaint has (`text_vs_all`). Its
`difference` is the total variation distance: half the sum of the gaps
between the two shares. 0 means the same mix, 1 means no overlap.
"""
from voc.datafile import DataFileError
from voc.db import connect
from voc.repo_checks import CFPB_COLUMNS

RARE_VALUE = "(rare or long values)"
NONE_VALUE = "(none)"
MIN_COUNT = 5
MAX_LEN = 120
LONG_TEXT = 4_000
COMPARED = {
    "Submitted via": "submitted_via", "Issue": "issue", "Company response to consumer": "company_response",
    "Timely response?": "timely", "Tags": "tags", "State": "state",
}
REDACTION = r"(^|[^A-Za-z])X{2,}([^A-Za-z]|$)"

RECEIVED = r"""
CASE
  WHEN regexp_matches(d, '^\d{4}-\d{2}-\d{2}$') THEN try_strptime(d, '%Y-%m-%d')
  WHEN regexp_matches(d, '^\d{1,2}/\d{1,2}/\d{4}$') THEN try_strptime(d, '%m/%d/%Y')
  WHEN regexp_matches(d, '^\d{1,2}/\d{1,2}/\d{2}$') THEN try_strptime(d, '%m/%d/%y')
END
"""


def _blank(column):
    return rf"({column} IS NULL OR NOT regexp_matches({column}, '\S'))"


def _safe(column, partition):
    """A category value, or RARE_VALUE if it is rare or long within its partition, or NONE_VALUE if blank."""
    return f"""
    CASE
      WHEN {_blank(column)} THEN '{NONE_VALUE}'
      WHEN length({column}) > {MAX_LEN} OR count(*) OVER (PARTITION BY {partition}) < {MIN_COUNT}
        THEN '{RARE_VALUE}'
      ELSE {column}
    END"""


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _load(con, path):
    quoted = str(path).replace("'", "''")
    source = f"read_csv('{quoted}', header = true, all_varchar = true)"
    columns = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    missing = [c for c in CFPB_COLUMNS if c not in columns]
    if missing:
        raise DataFileError(f"missing CFPB columns: {len(missing)} of {len(CFPB_COLUMNS)}")
    con.execute(f"CREATE TEMP TABLE raw AS SELECT * FROM {source}")
    extra = ", ".join(f"{_quote(name)} AS {alias}" for name, alias in COMPARED.items())
    con.execute(f"""
        CREATE TEMP TABLE base AS SELECT
          "Product" AS product_raw, "Sub-product" AS sub_product, "Company" AS company,
          "Complaint ID" AS complaint_id, "Consumer complaint narrative" AS narrative,
          "Date received" AS d, {extra}
        FROM raw""")
    con.execute(rf"""
        CREATE TEMP TABLE c AS SELECT *,
          {_safe('product_raw', 'product_raw')} AS product,
          NOT {_blank('narrative')} AS has_text,
          CASE WHEN NOT {_blank('narrative')}
            THEN trim(regexp_replace(lower(narrative), '\s+', ' ', 'g')) END AS norm,
          ({RECEIVED})::DATE AS received
        FROM base""")
    # The first copy of each text, by complaint ID as a number, is the one kept (B9).
    # Real IDs are numbers. Synthetic IDs are SYN- and a number, so the number is read from the end.
    con.execute(rf"""
        CREATE TEMP TABLE t AS SELECT
          product, received, length(narrative) AS chars,
          row_number() OVER (PARTITION BY norm
            ORDER BY try_cast(regexp_extract(complaint_id, '(\d+)$', 1) AS BIGINT) NULLS LAST,
                     complaint_id) = 1 AS first_copy,
          {_safe('sub_product', 'product, sub_product')} AS sub_product
        FROM c WHERE has_text""")


def _totals(con):
    row = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE has_text),
          count(DISTINCT company) FILTER (WHERE NOT {_blank('company')}),
          count(*) FILTER (WHERE NOT {_blank('complaint_id')})
            - count(DISTINCT complaint_id) FILTER (WHERE NOT {_blank('complaint_id')}),
          count(*) FILTER (WHERE {_blank('complaint_id')}),
          min(received)::VARCHAR, max(received)::VARCHAR,
          count(*) FILTER (WHERE received IS NULL),
          count(*) FILTER (WHERE has_text AND regexp_matches(narrative, '{REDACTION}')),
          count(*) FILTER (WHERE has_text) - count(DISTINCT norm) FILTER (WHERE has_text),
          count(*) FILTER (WHERE has_text AND length(narrative) > {LONG_TEXT})
        FROM c""").fetchone()
    keys = ["rows", "narratives", "distinct_companies", "complaint_id_duplicates", "missing_complaint_ids",
            "date_min", "date_max", "unparsed_dates", "narratives_with_redaction", "narrative_exact_duplicates",
            "narratives_over_4000_chars"]
    facts = dict(zip(keys, row))
    facts["date_range"] = [facts.pop("date_min"), facts.pop("date_max")]
    return facts


def _missing(con):
    counts = ", ".join(f"count(*) FILTER (WHERE {_blank(_quote(name))})" for name in CFPB_COLUMNS)
    return dict(zip(CFPB_COLUMNS, con.execute(f"SELECT {counts} FROM raw").fetchone()))


def _products(con):
    products = {}
    for name, rows, texts in con.execute(
            "SELECT product, count(*), count(*) FILTER (WHERE has_text) FROM c GROUP BY 1 ORDER BY 1").fetchall():
        products[name] = {"rows": rows, "narratives": texts, "unique_narratives": 0, "narrative_length": None,
                          "narratives_by_year": {}, "sub_products": {}}
    for name, unique, p10, p50, p90, p99 in con.execute("""
            SELECT product, count(*) FILTER (WHERE first_copy), quantile_disc(chars, 0.10),
                   quantile_disc(chars, 0.50), quantile_disc(chars, 0.90), quantile_disc(chars, 0.99)
            FROM t GROUP BY 1""").fetchall():
        products[name]["unique_narratives"] = unique
        products[name]["narrative_length"] = {"p10": p10, "p50": p50, "p90": p90, "p99": p99}
    for name, year, n in con.execute("""
            SELECT product, coalesce(year(received)::VARCHAR, 'unknown'), count(*)
            FROM t GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
        products[name]["narratives_by_year"][year] = n
    for name, sub, n in con.execute(
            "SELECT product, sub_product, count(*) FROM t GROUP BY 1, 2 ORDER BY 1, 3 DESC, 2").fetchall():
        products[name]["sub_products"][sub] = n
    return products


def _text_vs_all(con):
    compared = {}
    for field, alias in COMPARED.items():
        for product, value, rows, texts in con.execute(f"""
                SELECT product, v, count(*), count(*) FILTER (WHERE has_text) FROM (
                  SELECT product, has_text, {_safe(alias, f'product, {alias}')} AS v FROM c)
                GROUP BY 1, 2 ORDER BY 1, 3 DESC, 2""").fetchall():
            entry = compared.setdefault(product, {}).setdefault(field, {"difference": None, "values": {}})
            entry["values"][value] = {"all": rows, "text": texts}
    for fields in compared.values():
        for entry in fields.values():
            all_total = sum(v["all"] for v in entry["values"].values())
            text_total = sum(v["text"] for v in entry["values"].values())
            if all_total and text_total:
                gap = sum(abs(v["all"] / all_total - v["text"] / text_total) for v in entry["values"].values())
                entry["difference"] = round(gap / 2, 3)
    return compared


def profile(path):
    con = connect()
    try:
        _load(con, path)
        facts = _totals(con)
        facts["missing_values"] = _missing(con)
        facts["products"] = _products(con)
        facts["text_vs_all"] = _text_vs_all(con)
        facts["rules"] = {"rare_value_below": MIN_COUNT, "longest_value_shown": MAX_LEN,
                          "long_text_over": LONG_TEXT}
        return facts
    finally:
        con.close()


def format_profile(facts):
    lines = [f"{key}: {facts[key]}" for key in (
        "rows", "narratives", "distinct_companies", "complaint_id_duplicates", "missing_complaint_ids",
        "date_range", "unparsed_dates", "narratives_with_redaction", "narrative_exact_duplicates",
        "narratives_over_4000_chars")]
    lines.append("")
    lines.append(f"{'Product':<56} {'rows':>9} {'text':>6} {'unique':>7} {'median chars':>13}")
    for name, p in sorted(facts["products"].items(), key=lambda item: -item[1]["narratives"]):
        median = p["narrative_length"]["p50"] if p["narrative_length"] else "-"
        lines.append(f"{name[:56]:<56} {p['rows']:>9} {p['narratives']:>6} {p['unique_narratives']:>7} {median:>13}")
    lines.append("")
    lines.append("Difference between rows with text and all rows (0 = same mix, 1 = no overlap):")
    fields = list(COMPARED)
    lines.append(f"{'Product':<56} " + " ".join(f"{f[:10]:>10}" for f in fields))
    for name, by_field in sorted(facts["text_vs_all"].items()):
        cells = [by_field.get(f, {}).get("difference") for f in fields]
        lines.append(f"{name[:56]:<56} " + " ".join(f"{'-' if c is None else c:>10}" for c in cells))
    return "\n".join(lines)
