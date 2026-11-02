"""Spec 003: the frozen lists of the validation review (B16, V1, V2, V5, V7).

Drawn once from the development set, in the spec's order, with a fixed seed, and committed in
`splits/validation/` with a manifest of hashes. Each row is a complaint ID and its content hash from the
development list, so the lists are checked like the other lists. Only counts are printed (B21).
"""
import csv
import hashlib
import io
import json
import shutil
import tempfile
import tomllib
from pathlib import Path

from voc.data import SampleMismatch, _id_number, _manifest, _read_list

ORDER = ("dry_run", "v5", "v2", "v1")
NAMES = {"dry_run": "dry run", "v5": "V5", "v2": "V2", "v1": "V1"}


def _ordered(ids, name, seed):
    """A seeded order of the IDs, the same whatever order they come in."""
    return sorted(ids, key=lambda c: hashlib.sha256(f"{name}:{seed}:{c}".encode()).hexdigest())


def _by_id(ids):
    return sorted(ids, key=lambda c: (_id_number(c), c))


def _take(ids, size, name, seed):
    if len(ids) < size:
        raise SampleMismatch(f"the {NAMES[name]} list needs {size} complaints and only {len(ids)} can be drawn")
    return _by_id(_ordered(ids, name, seed)[:size])


def draw(dev, accepted, recorded, sizes, seed):
    """The four lists, drawn in the spec's order, and the number of accepted disagreements.

    `dev` holds the development IDs, `accepted` each accepted development label by ID, and `recorded` each
    development ID's recorded product. V5 never shares a case with the dry run, and V2 never with either.
    """
    dev = set(dev)
    outside = (set(accepted) | set(recorded)) - dev
    if outside:
        raise SampleMismatch(f"{len(outside)} IDs are not in the development list")
    missing = set(accepted) - set(recorded)
    if missing:
        raise SampleMismatch(f"{len(missing)} accepted labels have no recorded product")
    disagree = {c for c, label in accepted.items() if label != recorded[c]}
    lists = {"dry_run": _take(set(accepted), sizes["dry_run"], "dry_run", seed)}
    lists["v5"] = _take(set(accepted) - set(lists["dry_run"]), sizes["v5"], "v5", seed)
    lists["v2"] = _take(disagree - set(lists["dry_run"]) - set(lists["v5"]), sizes["v2"], "v2", seed)
    lists["v1"] = _take(dev, sizes["v1"], "v1", seed)
    return lists, len(disagree)


def _list_bytes(ids, dev):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["complaint_id", "content_hash"])
    for complaint_id in ids:
        writer.writerow([complaint_id, dev.get(complaint_id, "")])
    return out.getvalue().encode("utf-8")


def write_lists(splits_dir, lists, seed, disagreements, labels_file):
    """Write the lists once, each ID with its development hash, and their manifest. Never regenerated.

    `labels_file` is the labels file the lists were drawn from, relative to the folder that holds `splits/`.
    Its hash goes in the manifest. Everything is written to a temporary folder first and then renamed, so a
    write that stops partway leaves nothing behind.
    """
    splits_dir = Path(splits_dir)
    folder = splits_dir / "validation"
    if folder.exists():
        raise SampleMismatch("the validation lists already exist, and they are never regenerated")
    manifest = _manifest(splits_dir)
    dev = _read_list(splits_dir, "dev", manifest)
    outside = {c for ids in lists.values() for c in ids} - set(dev)
    if outside:
        raise SampleMismatch(f"{len(outside)} IDs are not in the development list")
    labels = (splits_dir.parent / labels_file).read_bytes()
    out = {"seed": seed, "accepted_disagreements": disagreements,
           "dev_sha256": manifest["lists"]["dev"]["sha256"], "labels_file": Path(labels_file).as_posix(),
           "labels_sha256": hashlib.sha256(labels).hexdigest(), "lists": {}}
    work = Path(tempfile.mkdtemp(prefix=".validation-", dir=splits_dir))
    try:
        for name in ORDER:
            data = _list_bytes(lists[name], dev)
            (work / f"{name}.csv").write_bytes(data)
            out["lists"][name] = {"count": len(lists[name]), "sha256": hashlib.sha256(data).hexdigest()}
        (work / "manifest.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                            newline="\n")
        work.rename(folder)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def read_lists(splits_dir):
    """The four lists, checked: each file against its hash, each ID and hash against the development list,
    the dry run, V5 and V2 against the accepted labels they were drawn from, and the lists that must not
    share a case."""
    splits_dir = Path(splits_dir)
    folder = splits_dir / "validation"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    dev_manifest = _manifest(splits_dir)
    if manifest["dev_sha256"] != dev_manifest["lists"]["dev"]["sha256"]:
        raise SampleMismatch("the validation lists were drawn from another development list")
    dev = _read_list(splits_dir, "dev", dev_manifest)
    labels = splits_dir.parent / manifest["labels_file"]
    if hashlib.sha256(labels.read_bytes()).hexdigest() != manifest["labels_sha256"]:
        raise SampleMismatch(f"{manifest['labels_file']} does not match its hash in the validation manifest")
    with open(labels, encoding="utf-8", newline="") as f:
        accepted = {r["complaint_id"] for r in csv.DictReader(f) if r["decision"] == "accepted"}
    lists = {}
    for name in ORDER:
        data = (folder / f"{name}.csv").read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest["lists"][name]["sha256"]:
            raise SampleMismatch(f"splits/validation/{name}.csv does not match its hash in the manifest")
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))[1:]
        if any(len(row) != 2 for row in rows):
            raise SampleMismatch(f"splits/validation/{name}.csv has a row that is not an ID and a hash")
        ids = [complaint_id for complaint_id, _ in rows]
        if len(set(ids)) != len(ids) or any(dev.get(c) != digest for c, digest in rows):
            raise SampleMismatch(f"splits/validation/{name}.csv holds an ID that is repeated, or not in the "
                                 "development list with this content")
        lists[name] = ids
    kept_apart = set(lists["dry_run"]) & set(lists["v5"]) or set(lists["v2"]) & set(lists["dry_run"] + lists["v5"])
    if kept_apart:
        raise SampleMismatch("the dry run, V5 and V2 lists share a case")
    if not set(lists["dry_run"] + lists["v5"] + lists["v2"]) <= accepted:
        raise SampleMismatch("the dry run, V5 or V2 list holds a complaint that is not an accepted label")
    return lists


def freeze(root):
    """Draw the lists from the development set and write them. Returns counts only (B21)."""
    from voc.evaluate import _rows
    from voc.load import DB_PATH

    root = Path(root)
    with open(root / "config" / "validation.toml", "rb") as f:
        config = tomllib.load(f)
    splits_dir = root / "splits"
    if (splits_dir / "validation").exists():
        raise SampleMismatch("the validation lists already exist, and they are never regenerated")
    manifest = _manifest(splits_dir)
    dev = set(_read_list(splits_dir, "dev", manifest))
    with open(root / config["labels_file"], encoding="utf-8", newline="") as f:
        accepted = {r["complaint_id"]: r["accepted_label"] for r in csv.DictReader(f) if r["decision"] == "accepted"}
    recorded = {r.complaint_id: r.product for r in _rows(root / DB_PATH, splits_dir, manifest["month"], "dev", dev)}
    lists, disagreements = draw(dev, accepted, recorded, {name: config[name] for name in ORDER}, config["seed"])
    write_lists(splits_dir, lists, config["seed"], disagreements, labels_file=config["labels_file"])
    return {"accepted": len(accepted), "disagreements": disagreements,
            "counts": {name: len(ids) for name, ids in lists.items()}}


def format_summary(summary):
    lines = [f"accepted development labels: {summary['accepted']}",
             f"accepted disagreements: {summary['disagreements']}"]
    lines += [f"{NAMES[name]} list: {summary['counts'][name]}" for name in ORDER]
    lines.append("written to splits/validation/")
    return "\n".join(lines)
