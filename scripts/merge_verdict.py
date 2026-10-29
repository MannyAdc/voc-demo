"""Run the mechanical merge checks on one or more pull requests (T006b).

The checks are in `src/voc/merge_verdict.py`. This script only starts them.
It makes read-only `gh` calls and changes nothing on GitHub. The owner still merges.

Run: uv run --native-tls python scripts/merge_verdict.py 29
Parallel branches: uv run --native-tls python scripts/merge_verdict.py 29 30 --test-merge
"""
import sys

from voc.merge_verdict import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
