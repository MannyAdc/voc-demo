"""Build the dbt project on a committed synthetic fixture, in a work folder (CI, T011).

The fixture is loaded with the same load code as `voc load`, without the pin
check, because it is a committed synthetic file (`SYN-` IDs), not an export.
Then `voc dbt build` runs on it. Only counts and check names are printed (B21).

The models read the test list from `splits/test.csv` (B17), so the fixture's own `splits`
folder next to the fixture file (the list and its manifest) is copied into the work folder.
Without them, or when the list does not match the manifest, `voc dbt build` refuses. The dbt fixture's list holds no ID from `complaints.csv`, so its
counts stay the same. The scheduled run's fixture checks the filter on real fixture rows.

Run: uv run python scripts/dbt_fixture_build.py tests/fixtures/dbt/complaints.csv <empty work folder>
"""
import shutil
import sys
from pathlib import Path

from voc import cli
from voc.labels import load_labels
from voc.load import DB_PATH, load_month

REPO = Path(__file__).resolve().parents[1]


def main(argv):
    if len(argv) != 2:
        print("usage: python scripts/dbt_fixture_build.py <fixture.csv> <empty work folder>")
        return 2
    fixture, work = Path(argv[0]), Path(argv[1])
    (work / "config").mkdir(parents=True)
    shutil.copy(REPO / "config" / "labels.toml", work / "config" / "labels.toml")
    shutil.copytree(REPO / "dbt", work / "dbt", ignore=shutil.ignore_patterns("target", "logs"))
    splits = fixture.parent / "splits"
    if splits.is_dir():
        shutil.copytree(splits, work / "splits")
    labels = [label.name for label in load_labels(work / "config" / "labels.toml")]
    counts = load_month(work / DB_PATH, fixture, "synthetic", labels)
    print(f"loaded the fixture: {counts['rows']} rows, {counts['new']} new")
    return cli.main(["dbt", "build"], env={}, root=work)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
