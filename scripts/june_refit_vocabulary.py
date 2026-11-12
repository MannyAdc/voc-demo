"""Spec 004, J7: write `config/june_refit_vocabulary.json`, the laptop's TF-IDF vocabulary for June's refit.

Usage: uv run --native-tls --locked python scripts/june_refit_vocabulary.py

The laptop only. It reads the pinned July export from the folder that the July data variable names, in the
environment or in `.env`, loads it as the refit does, and pins the vocabulary that scikit-learn's own TF-IDF keeps
on July's training rows on this machine. Then it runs the refit with that pin, which must give every committed July
development label. If it does not, the old pin is put back. It prints counts, the hash and the check's result only,
never a term (B21).
"""
import os
import sys
import tempfile
from pathlib import Path

from voc import june_refit
from voc.cli import _export
from voc.datafile import DataFileError
from voc.env import settings


def main():
    root = Path(__file__).resolve().parents[1]
    try:
        export = _export(settings(dict(os.environ), root))
        with tempfile.TemporaryDirectory() as work:
            pin = june_refit.write_and_check_vocabulary_pin(root, export, work)
    except (june_refit.RefitError, DataFileError) as err:
        print(f"refused: {err}")
        return 1
    print(f"terms above the cut: {pin['terms_above']}, tied at {pin['count_at_cut']} uses: {pin['terms_tied']}, "
          f"tied terms kept: {len(pin['kept_tied_positions'])}")
    print(f"vocabulary sha256 {pin['vocabulary_sha256']}")
    print("the refit with this pin gives every committed July development label")
    return 0


if __name__ == "__main__":
    sys.exit(main())
