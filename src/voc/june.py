"""Spec 004, J6: the June sample, drawn on the laptop from the pinned June file.

June is read straight from its file into a database in memory, with the same checks as `voc load`, and never
goes into the staged table (J1). First any June complaint whose narrative copies one in July's training or
development sets is removed, then the copies within June, both with July's measure (B9). July's rows come first
because they are the earlier ones: the other order could drop a June row whose only near-copy was itself a copy
of July (review of #88). Those July rows are selected by their IDs, so no July test row is ever read (J2). The size comes from Cochran's formula on the June pool (B25),
split across Products in proportion, and the list is frozen in `splits/june/` with its hashes (B16).

B21: only counts leave this module.
"""
import hashlib
import json
from pathlib import Path

from voc.data import (DUPLICATE_MEASURE, DUPLICATE_THRESHOLD, OPENING_WORDS, Row, SampleMismatch, _by_id, _dedupe,
                      _grams, _list_bytes, _manifest, _normal, _read_list, _seeded, _similar, allocate, cochran_size,
                      opening_key, verify_ids)
from voc.db import connect
from voc.load import _check_keys, _check_types, _read

LIST = "june"
JULY_LISTS = ("train", "dev")  # never the test set (J2)


def _june_rows(path, labels):
    """June's rows with a narrative, after `voc load`'s checks, in a database in memory."""
    con = connect()
    try:
        _read(con, path)
        _check_types(con)
        _check_keys(con, labels)
        found = con.execute(r"""
            SELECT "Complaint ID", "Product", "Consumer complaint narrative" FROM raw
            WHERE regexp_matches("Consumer complaint narrative", '\S')""").fetchall()
    finally:
        con.close()
    return [Row(*values) for values in found]


def _july_rows(db_path, splits_dir):
    """July's training and development rows, selected by ID and checked against their frozen lists."""
    from voc.pipeline import _rows_by_id

    if not Path(db_path).is_file():
        raise SampleMismatch("the staged table is missing. Run `voc load july_2026` first")
    manifest = _manifest(splits_dir)
    rows = []
    for name in JULY_LISTS:
        wanted = set(_read_list(splits_dir, name, manifest))
        found = _rows_by_id(db_path, manifest["month"], wanted)
        missing = wanted - {row.complaint_id for row in found}
        if missing:
            raise SampleMismatch(f"{len(missing)} July {name} complaints are missing from the staged table")
        verify_ids(splits_dir, name, found)
        rows += found
    return rows, {name: manifest["lists"][name]["sha256"] for name in JULY_LISTS}


def _drop_july_copies(rows, july):
    """The rows that copy no July narrative, exactly or nearly, by July's measure, and the number dropped."""
    normals = {_normal(row.narrative) for row in july}
    by_opening = {}
    for row in july:
        by_opening.setdefault(opening_key(row.narrative), []).append(_grams(_normal(row.narrative)))
    kept, copies = [], 0
    for row in rows:
        normal = _normal(row.narrative)
        if normal in normals or any(_similar(_grams(normal), other)
                                    for other in by_opening.get(opening_key(row.narrative), ())):
            copies += 1
        else:
            kept.append(row)
    return kept, copies


def _draw(rows, size, seed):
    """`size` rows split across Products in proportion to the pool, each Product in a seeded order."""
    by_product = {}
    for row in _by_id(rows):
        by_product.setdefault(row.product, []).append(row)
    quota = allocate(size, {product: len(members) for product, members in by_product.items()})
    sample, products = [], {}
    for product, members in sorted(by_product.items()):
        chosen = _seeded(members, seed)[:quota[product]]
        sample += chosen
        products[product] = {"pool": len(members), "sample": len(chosen)}
    return _by_id(sample), products


def build_june_sample(csv_path, labels, db_path, splits_dir, source_sha256, seed, margin, month="june_2026"):
    """Draw and freeze the June sample in `splits/june/`. Returns counts only (B21)."""
    splits_dir = Path(splits_dir)
    folder = splits_dir / LIST
    if any((folder / name).exists() for name in ("manifest.json", f"{LIST}.csv")):
        raise SampleMismatch("the June sample lists already exist, and they are never regenerated")
    june = _june_rows(csv_path, labels)
    july, july_lists = _july_rows(db_path, splits_dir)
    not_july, july_copies = _drop_july_copies(june, july)
    pool, copies = _dedupe(not_july)
    if not pool:
        raise SampleMismatch("no June rows with text are left to sample")
    target = cochran_size(margin, len(pool))
    sample, products = _draw(pool, target, seed)
    data = _list_bytes(sample)
    summary = {"month": month, "seed": seed, "margin": margin, "duplicate_threshold": DUPLICATE_THRESHOLD,
               "duplicate_measure": DUPLICATE_MEASURE, "opening_words": OPENING_WORDS, "source_sha256": source_sha256,
               "june_rows": len(june), "exact_copies": copies["exact"], "near_copies": copies["near"],
               "july_copies": july_copies, "july_lists": july_lists, "pool": len(pool), "target": target,
               "lists": {LIST: {"count": len(sample), "sha256": hashlib.sha256(data).hexdigest()}},
               "products": products}
    _write(folder, data, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def _write(folder, data, manifest):
    """Both files or neither, so a failed write never leaves a list that blocks the next run."""
    folder.mkdir(parents=True, exist_ok=True)
    written = [folder / f"{LIST}.csv", folder / "manifest.json"]
    try:
        written[0].write_bytes(data)
        written[1].write_text(manifest, encoding="utf-8")
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        if not any(folder.iterdir()):
            folder.rmdir()
        raise


def format_june_summary(summary):
    lines = [f"June rows with text: {summary['june_rows']}",
             f"removed: {summary['exact_copies']} exact copies and {summary['near_copies']} near-copies within June, "
             f"{summary['july_copies']} copies of July training or development narratives",
             f"pool: {summary['pool']}",
             f"sample: {summary['lists'][LIST]['count']} (Cochran target {summary['target']} at "
             f"{summary['margin'] * 100:g} points)", "",
             f"{'Product':<56} {'pool':>6} {'sample':>6}"]
    for product, counts in summary["products"].items():
        lines.append(f"{product[:56]:<56} {counts['pool']:>6} {counts['sample']:>6}")
    return "\n".join(lines)
