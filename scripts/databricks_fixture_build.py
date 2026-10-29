"""Build the dbt project on Databricks from a committed synthetic fixture (T021).

The fixture is loaded into a local DuckDB file with the same load code as `voc load`,
as in scripts/dbt_fixture_build.py. The staged table is then written as the seed
`staged_complaints.csv`, and the fixture's test list is copied as the seed `test_list.csv`.
Both go into the work folder's dbt/seeds, never into this repo. Then
`voc dbt build --target databricks` checks that every seeded complaint ID is SYN- and runs
the same models on the Databricks SQL warehouse. Only counts and check names are printed (B21).

The connection comes from DATABRICKS_HOST, DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN,
set by the owner for one run.

Run: uv run --group databricks python scripts/databricks_fixture_build.py tests/fixtures/dbt/complaints.csv <empty work folder>
"""
import shutil
import sys
from pathlib import Path

from voc import cli
from voc.db import connect
from voc.dbt_run import SEEDS, STAGED_SEED, TEST_LIST, TEST_SEED
from voc.labels import load_labels
from voc.load import DB_PATH, TABLE, load_month

REPO = Path(__file__).resolve().parents[1]


def prepare(fixture, work):
    """Make the work folder: labels, the dbt project, the fixture's splits and the two seeds."""
    fixture, work = Path(fixture), Path(work)
    (work / "config").mkdir(parents=True)
    shutil.copy(REPO / "config" / "labels.toml", work / "config" / "labels.toml")
    shutil.copytree(REPO / "dbt", work / "dbt", ignore=shutil.ignore_patterns("target", "logs", "seeds"))
    shutil.copytree(fixture.parent / "splits", work / "splits")
    labels = [label.name for label in load_labels(work / "config" / "labels.toml")]
    counts = load_month(work / DB_PATH, fixture, "synthetic", labels)
    seeds = work / SEEDS
    seeds.mkdir()
    con = connect(work / DB_PATH)
    try:
        path = (seeds / STAGED_SEED).as_posix().replace("'", "''")
        con.execute(f"COPY (SELECT complaint_id, * EXCLUDE (complaint_id) FROM {TABLE} ORDER BY complaint_id) "
                    f"TO '{path}' (HEADER, DELIMITER ',')")
    finally:
        con.close()
    shutil.copyfile(work / TEST_LIST, seeds / TEST_SEED)
    return counts


def main(argv):
    if len(argv) != 2:
        print("usage: python scripts/databricks_fixture_build.py <fixture.csv> <empty work folder>")
        return 2
    counts = prepare(argv[0], argv[1])
    print(f"loaded the fixture: {counts['rows']} rows, written as the synthetic seed")
    return cli.main(["dbt", "build", "--target", "databricks"], env={}, root=Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
