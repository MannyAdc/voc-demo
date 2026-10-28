"""Load one pinned monthly export into the staged DuckDB table (B14).

The same as `voc load <month>`: the file is checked against its pin first,
the load is safe to repeat, and only counts are printed (B21).

Run: uv run python scripts/load_month.py july_2026
"""
import sys

from voc import cli


def main(argv, env=None, root=None):
    return cli.main(["load", *argv], env=env, root=root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
