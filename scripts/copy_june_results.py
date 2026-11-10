"""Spec 004, J11 and J13: copy Job B's two June results files into `results/june/`, as the read-only reader.

Run from the repo's folder, by Claude, after the owner has put the reader's client ID and secret in `.env`:

    uv run --native-tls --locked python scripts/copy_june_results.py <Job B run ID>
    uv run --native-tls --locked python scripts/copy_june_results.py --check-reader

It prints only the files' names, the rows' count and yes or no, never a secret or a file's content (J5).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from voc import june_copy  # noqa: E402
from voc.approval import ApprovalError, parse_id  # noqa: E402
from voc.env import settings  # noqa: E402


def main(argv):
    try:
        reader = june_copy.reader_from(settings(os.environ, ROOT))
        if argv == ["--check-reader"]:
            lines = june_copy.check_reader(reader)
        elif len(argv) == 1:
            names = june_copy.copy(ROOT, parse_id(argv[0], "the Job B run ID"), reader)
            rows = len((ROOT / june_copy.OUT / names[0]).read_text(encoding="utf-8").splitlines()) - 1
            lines = [f"copied | {', '.join(names)}", f"rows | {rows}"]
        else:
            print("usage | copy_june_results.py <Job B run ID>, or --check-reader")
            return 2
    except (june_copy.CopyError, ApprovalError) as err:
        print(f"refused | {err}")
        return 1
    print("\n".join(lines))
    return 1 if lines[-1] == "verdict | FAIL" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
