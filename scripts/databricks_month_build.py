"""Build the dbt project on Databricks from a real pinned export (owner decision, 31 October 2026).

The owner first uploads the pinned export, under its own file name, to the Unity Catalog volume
/Volumes/<catalog>/default/voc_raw. This script makes a work folder with the labels, the pins, the dbt
project, the splits and one seed, the test list. Then `voc dbt build --target databricks --month <month>`
reads the file from the volume, checks its SHA-256 and row count against the pins, and runs the same models.
Only counts and check names are printed (B21). The narrative text stays in the warehouse.

The connection comes from DATABRICKS_HOST, DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN, set by the owner
for one run (docs/PIPELINE.md, "The real exports on Databricks").

Run: uv run --native-tls --group databricks python scripts/databricks_month_build.py <month> <empty work folder>
"""
import shutil
import sys
from pathlib import Path

from voc import cli
from voc.cli import MONTHS
from voc.dbt_run import SEEDS, TEST_LIST, TEST_SEED

REPO = Path(__file__).resolve().parents[1]


def prepare(work):
    """Make the work folder. It must be new or empty, so no seed from an earlier run is carried over."""
    work = Path(work)
    if work.exists() and any(work.iterdir()):
        raise FileExistsError("the work folder is not empty")
    (work / "config").mkdir(parents=True, exist_ok=True)
    for name in ("labels.toml", "data_files.toml"):
        shutil.copy(REPO / "config" / name, work / "config" / name)
    shutil.copytree(REPO / "dbt", work / "dbt", ignore=shutil.ignore_patterns("target", "logs", "seeds"))
    shutil.copytree(REPO / "splits", work / "splits")
    (work / SEEDS).mkdir()
    shutil.copyfile(work / TEST_LIST, work / SEEDS / TEST_SEED)


def main(argv):
    if len(argv) != 2 or argv[0] not in MONTHS:
        print(f"usage: python scripts/databricks_month_build.py <{' or '.join(sorted(MONTHS))}> <empty work folder>")
        return 2
    prepare(argv[1])
    print(f"work folder ready for {argv[0]}: the dbt project and the test list seed")
    return cli.main(["dbt", "build", "--target", "databricks", "--month", argv[0]], env={}, root=Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
