"""B9, B16, B25: prepare, size, split and freeze the samples.

Rows are handled in complaint ID order (as a number), so every step is
repeatable. Duplicates are removed before sampling: two narratives are
duplicates when their normalised text is identical, or when they share an
opening and their full text is very similar. The test set is drawn first, in a
seeded order within each Product, so it does not change when the development
size changes. A Product gives at most half of its pool to the test set.

The lists are frozen in `splits/`: each complaint ID with one hash of its
narrative and Product together, and a manifest with each list's hash. Every
command checks the IDs and hashes it is given against these lists.
"""
import csv
import difflib
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

DUPLICATE_THRESHOLD = 0.9
OPENING_WORDS = 6
QUICK_CHECK_SIZE = 50
LISTS = ("dev", "test", "train")
# Redaction runs, in any case: the opening key only decides which narratives are compared.
REDACTION = re.compile(r"(?<![a-z])x{2,}(?![a-z])", re.IGNORECASE)


class SampleMismatch(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    complaint_id: str
    product: str
    narrative: str


def _id_number(complaint_id):
    digits = re.search(r"(\d+)$", complaint_id)
    return int(digits.group(1)) if digits else math.inf


def _by_id(rows):
    return sorted(rows, key=lambda r: (_id_number(r.complaint_id), r.complaint_id))


def _normal(text):
    return " ".join(text.lower().split())


def opening_key(text):
    """The first words of a narrative, ignoring case, digits and redaction marks."""
    cleaned = REDACTION.sub(" ", text)
    cleaned = re.sub(r"[\d/{}$.,]+", " ", cleaned.lower())
    return " ".join(cleaned.split()[:OPENING_WORDS])


def _similar(a, b):
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return (matcher.real_quick_ratio() >= DUPLICATE_THRESHOLD and matcher.quick_ratio() >= DUPLICATE_THRESHOLD
            and matcher.ratio() >= DUPLICATE_THRESHOLD)


def dedupe(rows):
    """Keep the lowest complaint ID of each duplicate group. Returns the kept rows and the number removed."""
    kept, seen, by_opening = [], set(), {}
    for row in _by_id(rows):
        normal = _normal(row.narrative)
        if normal in seen:
            continue
        group = by_opening.setdefault(opening_key(row.narrative), [])
        if any(_similar(normal, other) for other in group):
            continue
        seen.add(normal)
        group.append(normal)
        kept.append(row)
    return kept, len(rows) - len(kept)


def cochran_size(margin, pool):
    """Cochran's formula at 95 percent and p = 0.5, with the finite pool correction, both rounded up (B25)."""
    n0 = math.ceil(1.96 ** 2 * 0.25 / margin ** 2)
    return math.ceil(n0 / (1 + (n0 - 1) / pool))


def allocate(total, pool_counts):
    """Split `total` across Products in proportion to the pool, by largest remainder, adding up exactly."""
    pool = sum(pool_counts.values())
    raw = {p: total * n / pool for p, n in pool_counts.items()}
    parts = {p: math.floor(v) for p, v in raw.items()}
    for p in sorted(raw, key=lambda p: (-(raw[p] - parts[p]), p))[:total - sum(parts.values())]:
        parts[p] += 1
    return parts


def _seeded(rows, seed):
    return sorted(rows, key=lambda r: hashlib.sha256(f"{seed}:{r.complaint_id}".encode()).hexdigest())


def split(rows, dev_size, test_size, seed):
    """Development, test and training sets. They never overlap and together hold every row."""
    by_product = {}
    for row in _by_id(rows):
        by_product.setdefault(row.product, []).append(row)
    counts = {p: len(rs) for p, rs in by_product.items()}
    test_quota, dev_quota = allocate(test_size, counts), allocate(dev_size, counts)
    sets = {name: [] for name in LISTS}
    for product, members in sorted(by_product.items()):
        ordered = _seeded(members, seed)
        n_test = min(test_quota[product], len(members) // 2)
        n_dev = min(dev_quota[product], len(members) - n_test - 1) if len(members) - n_test > 1 else 0
        sets["test"] += ordered[:n_test]
        sets["dev"] += ordered[n_test:n_test + n_dev]
        sets["train"] += ordered[n_test + n_dev:]
    return {name: _by_id(members) for name, members in sets.items()}


def content_hash(narrative, product):
    """One hash of narrative and Product together, so it reveals neither on its own (B16)."""
    return hashlib.sha256(f"{product}\x1f{narrative}".encode("utf-8")).hexdigest()


def _list_bytes(rows):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["complaint_id", "content_hash"])
    for row in rows:
        writer.writerow([row.complaint_id, content_hash(row.narrative, row.product)])
    return out.getvalue().encode("utf-8")


def write_splits(folder, sets, removed, source_sha256, seed):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": seed, "duplicate_threshold": DUPLICATE_THRESHOLD, "opening_words": OPENING_WORDS,
                "duplicates_removed": removed, "source_sha256": source_sha256, "lists": {}}
    for name in LISTS:
        data = _list_bytes(sets[name])
        (folder / f"{name}.csv").write_bytes(data)
        manifest["lists"][name] = {"count": len(sets[name]), "sha256": hashlib.sha256(data).hexdigest()}
    quick = [r.complaint_id for r in _seeded(sets["dev"], f"quick:{seed}")[:QUICK_CHECK_SIZE]]
    manifest["quick_check"] = sorted(quick, key=lambda c: (_id_number(c), c))
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(folder):
    return json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))


def _read_list(folder, name, manifest):
    data = (Path(folder) / f"{name}.csv").read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["lists"][name]["sha256"]:
        raise SampleMismatch(f"splits/{name}.csv does not match its hash in the manifest")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))[1:]
    return {complaint_id: digest for complaint_id, digest in rows}


def read_splits(folder):
    manifest = _manifest(folder)
    return {name: _read_list(folder, name, manifest) for name in LISTS}


def quick_check_ids(folder):
    manifest = _manifest(folder)
    dev = _read_list(folder, "dev", manifest)
    quick = manifest["quick_check"]
    if not set(quick) <= set(dev):
        raise SampleMismatch("the quick-check list is not part of the development list")
    return quick


def load_test_hashes(folder):
    """The only allowed way to touch test rows without `final`: IDs and hashes, never text or labels (B17)."""
    return dict(_read_list(folder, "test", _manifest(folder)))


def _month_rows(db_path, month):
    from voc.db import connect
    from voc.load import TABLE

    con = connect(db_path)
    try:
        found = con.execute(rf"""
            SELECT complaint_id, product, narrative FROM {TABLE}
            WHERE source = ? AND narrative IS NOT NULL AND regexp_matches(narrative, '\S')""", [month]).fetchall()
    finally:
        con.close()
    return [Row(*values) for values in found]


def build_samples(db_path, month, seed, splits_dir, source_sha256, dev_margin=0.05, test_margin=0.02):
    """Build and freeze the samples from one month of the staged table. Returns counts only (B21)."""
    splits_dir = Path(splits_dir)
    if (splits_dir / "manifest.json").exists():
        raise SampleMismatch("the sample lists already exist, and they are never regenerated")
    kept, removed = dedupe(_month_rows(db_path, month))
    dev_size, test_size = cochran_size(dev_margin, len(kept)), cochran_size(test_margin, len(kept))
    sets = split(kept, dev_size, test_size, seed)
    write_splits(splits_dir, sets, removed=removed, source_sha256=source_sha256, seed=seed)
    by_product = {}
    for name in LISTS:
        for row in sets[name]:
            by_product.setdefault(row.product, dict.fromkeys(LISTS, 0))[name] += 1
    return {"pool": len(kept), "duplicates_removed": removed, "dev": len(sets["dev"]),
            "test": len(sets["test"]), "train": len(sets["train"]), "dev_target": dev_size,
            "test_target": test_size, "test_by_product": {p: c["test"] for p, c in sorted(by_product.items())},
            "by_product": dict(sorted(by_product.items()))}


def format_summary(summary):
    lines = [f"pool: {summary['pool']} (after {summary['duplicates_removed']} duplicates removed)",
             f"development: {summary['dev']} (Cochran target {summary['dev_target']})",
             f"test: {summary['test']} (Cochran target {summary['test_target']})",
             f"training: {summary['train']}", "",
             f"{'Product':<56} {'dev':>5} {'test':>6} {'train':>6}"]
    for product, counts in summary["by_product"].items():
        flag = "  too few to judge" if counts["test"] < 30 else ""
        lines.append(f"{product[:56]:<56} {counts['dev']:>5} {counts['test']:>6} {counts['train']:>6}{flag}")
    return "\n".join(lines)


def verify_ids(folder, name, rows):
    """Refuse unless every row is in the committed list with the same narrative and Product."""
    committed = _read_list(folder, name, _manifest(folder))
    for row in rows:
        if committed.get(row.complaint_id) != content_hash(row.narrative, row.product):
            raise SampleMismatch(f"{row.complaint_id} is not in splits/{name}.csv with this content")
