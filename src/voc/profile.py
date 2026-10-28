"""B22: data facts from the export, as counts only.

B21: no complaint text ever leaves this module. Only counts, lengths, years
and category values are returned. A category value seen fewer than
MIN_COUNT times, or longer than MAX_LEN characters, is never shown. It is
counted under RARE_VALUE instead, because a badly split row could put
complaint text into a category column.
"""
from voc.datafile import DataFileError
from voc.db import connect
from voc.repo_checks import CFPB_COLUMNS

RARE_VALUE = "(rare or long values)"
NONE_VALUE = "(none)"
MIN_COUNT = 5
MAX_LEN = 120
LONG_TEXT = 4_000

RECEIVED = r"""
CASE
  WHEN regexp_matches(d, '^\d{4}-\d{2}-\d{2}$') THEN try_strptime(d, '%Y-%m-%d')
  WHEN regexp_matches(d, '^\d{1,2}/\d{1,2}/\d{4}$') THEN try_strptime(d, '%m/%d/%Y')
  WHEN regexp_matches(d, '^\d{1,2}/\d{1,2}/\d{2}$') THEN try_strptime(d, '%m/%d/%y')
END
"""


def _safe(column):
    """A category column with rare or long values replaced, and blanks named."""
    return f"""
    CASE
      WHEN {column} IS NULL OR trim({column}) = '' THEN '{NONE_VALUE}'
      WHEN length({column}) > {MAX_LEN} OR count(*) OVER (PARTITION BY {column}) < {MIN_COUNT}
        THEN '{RARE_VALUE}'
      ELSE {column}
    END"""


def _load(con, path):
    quoted = str(path).replace("'", "''")
    columns = [row[0] for row in con.execute(
        f"DESCRIBE SELECT * FROM read_csv('{quoted}', header = true, all_varchar = true)").fetchall()]
    missing = [c for c in CFPB_COLUMNS if c not in columns]
    if missing:
        raise DataFileError(f"missing CFPB columns: {len(missing)} of {len(CFPB_COLUMNS)}")
    con.execute(f"""
        CREATE TEMP TABLE raw AS SELECT
          "Product" AS product, "Sub-product" AS sub_product, "Company" AS company,
          "Complaint ID" AS complaint_id, "Consumer complaint narrative" AS narrative,
          "Date received" AS d
        FROM read_csv('{quoted}', header = true, all_varchar = true)""")
    con.execute(f"""
        CREATE TEMP TABLE c AS SELECT
          {_safe('product')} AS product,
          sub_product, company, complaint_id, narrative,
          coalesce(narrative, '') <> '' AND trim(narrative) <> '' AS has_text,
          ({RECEIVED})::DATE AS received
        FROM raw""")
    # Sub-product rarity is judged within each Product, on complaints with text.
    con.execute(f"""
        CREATE TEMP TABLE t AS SELECT
          product, received, length(narrative) AS chars,
          CASE
            WHEN sub_product IS NULL OR trim(sub_product) = '' THEN '{NONE_VALUE}'
            WHEN length(sub_product) > {MAX_LEN}
              OR count(*) OVER (PARTITION BY product, sub_product) < {MIN_COUNT} THEN '{RARE_VALUE}'
            ELSE sub_product
          END AS sub_product
        FROM c WHERE has_text""")


def _totals(con):
    row = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE has_text),
          count(DISTINCT company) FILTER (WHERE coalesce(trim(company), '') <> ''),
          count(*) - count(DISTINCT complaint_id),
          min(received)::VARCHAR, max(received)::VARCHAR,
          count(*) FILTER (WHERE received IS NULL),
          count(*) FILTER (WHERE has_text AND contains(narrative, 'XX')),
          count(*) FILTER (WHERE has_text)
            - count(DISTINCT lower(regexp_replace(trim(narrative), '\\s+', ' ', 'g'))) FILTER (WHERE has_text),
          count(*) FILTER (WHERE has_text AND length(narrative) > {LONG_TEXT})
        FROM c""").fetchone()
    keys = ["rows", "narratives", "distinct_companies", "complaint_id_duplicates", "date_min", "date_max",
            "unparsed_dates", "narratives_with_redaction", "narrative_exact_duplicates", "narratives_over_4000_chars"]
    facts = dict(zip(keys, row))
    facts["date_range"] = [facts.pop("date_min"), facts.pop("date_max")]
    return facts


def _products(con):
    products = {}
    for name, rows, texts in con.execute(
            "SELECT product, count(*), count(*) FILTER (WHERE has_text) FROM c GROUP BY 1 ORDER BY 1").fetchall():
        products[name] = {"rows": rows, "narratives": texts, "narrative_length": None,
                          "narratives_by_year": {}, "sub_products": {}}
    for name, p10, p50, p90, p99 in con.execute("""
            SELECT product, quantile_disc(chars, 0.10), quantile_disc(chars, 0.50),
                   quantile_disc(chars, 0.90), quantile_disc(chars, 0.99)
            FROM t GROUP BY 1""").fetchall():
        products[name]["narrative_length"] = {"p10": p10, "p50": p50, "p90": p90, "p99": p99}
    for name, year, n in con.execute("""
            SELECT product, coalesce(year(received)::VARCHAR, 'unknown'), count(*)
            FROM t GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
        products[name]["narratives_by_year"][year] = n
    for name, sub, n in con.execute(
            "SELECT product, sub_product, count(*) FROM t GROUP BY 1, 2 ORDER BY 1, 3 DESC, 2").fetchall():
        products[name]["sub_products"][sub] = n
    return products


def profile(path):
    con = connect()
    try:
        _load(con, path)
        facts = _totals(con)
        facts["products"] = _products(con)
        facts["rules"] = {"rare_value_below": MIN_COUNT, "longest_value_shown": MAX_LEN,
                          "long_text_over": LONG_TEXT}
        return facts
    finally:
        con.close()


def format_profile(facts):
    lines = [f"{key}: {facts[key]}" for key in (
        "rows", "narratives", "distinct_companies", "complaint_id_duplicates", "date_range", "unparsed_dates",
        "narratives_with_redaction", "narrative_exact_duplicates", "narratives_over_4000_chars")]
    lines.append("")
    lines.append(f"{'Product':<70} {'rows':>9} {'narratives':>11} {'median chars':>13}")
    for name, p in sorted(facts["products"].items(), key=lambda item: -item[1]["narratives"]):
        median = p["narrative_length"]["p50"] if p["narrative_length"] else "-"
        lines.append(f"{name[:70]:<70} {p['rows']:>9} {p['narratives']:>11} {median:>13}")
    return "\n".join(lines)
