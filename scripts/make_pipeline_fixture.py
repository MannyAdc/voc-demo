"""Make the synthetic fixture for the scheduled pipeline run (T015c), once, in a new folder.

The committed copy is in `tests/fixtures/pipeline`. Every complaint is synthetic, with a `SYN-` ID. The
fixture holds:

- `synthetic_complaints.csv`: a small export with the CFPB columns, three Products and two rows with no text.
- `data_files.toml`: its own pin (file name, size, SHA-256), so `voc load` checks it like a real export.
- `splits/`: the frozen lists, drawn by the same `build_samples` code as `voc sample`, with wider margins
  so the small pool still has a training set.
- `pool.toml`: each Product's counts, from the `build_samples` summary.
- `answers.csv`: one mock answer per development complaint. Most give the right Product and a quote from
  the text. Some give the wrong Product, and some a quote that is not in the text.

The maker never overwrites a folder. A test checks that it rebuilds the committed copy byte for byte.

Run: uv run python scripts/make_pipeline_fixture.py <new folder>
"""
import csv
import hashlib
import sys
import tempfile
from pathlib import Path

from voc.data import _id_number, build_samples, read_splits
from voc.labels import load_labels
from voc.load import DB_PATH, load_month
from voc.repo_checks import CFPB_COLUMNS

REPO = Path(__file__).resolve().parents[1]
EXPORT = "synthetic_complaints.csv"
MONTH = "july_2026"  # `voc load` takes only the months in the command line, so the fixture stands in for July
SEED = 20261029
DEV_MARGIN = 0.15
TEST_MARGIN = 0.15
PER_PRODUCT = 30
WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
# Product: (word in the opening, sub-product, issue, three sentences that can be quoted)
PRODUCTS = {
    "Mortgage": ("mortgage", "Conventional home mortgage", "Trouble during payment process",
                 ["My escrow payment was applied to the wrong month",
                  "The servicer lost my loan modification papers",
                  "They charged a late fee on my home loan"]),
    "Credit card": ("card", "General-purpose credit card or charge card", "Fees or interest",
                    ["The card company charged the same fee twice",
                     "My credit limit was cut without notice",
                     "The dispute on my statement was closed with no answer"]),
    "Student loan": ("student", "Federal student loan", "Dealing with your lender or servicer",
                     ["My student loan servicer misapplied my payment",
                      "They put my loans in forbearance without asking",
                      "The repayment plan paperwork was lost again"]),
}
NOT_IN_TEXT = "SYN words that appear in no complaint"


def _rows():
    """The export rows, in complaint ID order: every Product in turn, then two rows with no text."""
    rows, names = [], list(PRODUCTS)
    for i in range(PER_PRODUCT * len(names)):
        product = names[i % len(names)]
        k = i // len(names)
        word, sub_product, issue, sentences = PRODUCTS[product]
        text = (f"SYN {word} story {WORDS[k % 10]} {WORDS[k // 10]}. {sentences[k % 3]}. "
                "It happened on XX/XX/XXXX and I called XXXX twice.")
        rows.append({"Complaint ID": f"SYN-{i + 1}", "Product": product, "Sub-product": sub_product,
                     "Issue": issue, "Consumer complaint narrative": text,
                     "Date received": f"2026-07-{k % 28 + 1:02d}"})
    for n in (1, 2):
        product = names[n - 1]
        rows.append({"Complaint ID": f"SYN-{len(rows) + 1}", "Product": product,
                     "Sub-product": PRODUCTS[product][1], "Issue": PRODUCTS[product][2],
                     "Consumer complaint narrative": "", "Date received": "2026-07-30"})
    for row in rows:
        row.update({"Company": "Synthetic Bank", "State": "CA", "Submitted via": "Web",
                    "Date sent to company": row["Date received"],
                    "Company response to consumer": "Closed with explanation", "Timely response?": "Yes"})
    return rows


def _write_export(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CFPB_COLUMNS, restval="", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write(path, text):
    Path(path).write_text(text, encoding="utf-8", newline="")


def _pin(path):
    data = Path(path).read_bytes()
    return (
        "# The pin of the synthetic export for the scheduled pipeline run (T015c), made by\n"
        "# scripts/make_pipeline_fixture.py. It stands in for the July pin only in a work folder.\n"
        "# The real pin in config/data_files.toml is never changed or read by the scheduled run.\n\n"
        f"[{MONTH}]\n"
        f'file_name = "{EXPORT}"\n'
        f"size_bytes = {len(data)}\n"
        f'sha256 = "{hashlib.sha256(data).hexdigest()}"\n')


def _pool(by_product):
    lines = ["# Synthetic pool counts for the scheduled pipeline run (T015c), from the `build_samples`",
             "# summary in scripts/make_pipeline_fixture.py."]
    for product, counts in sorted(by_product.items()):
        lines += ["", f'[products."{product}"]', f"pool = {sum(counts.values())}", f"dev = {counts['dev']}",
                  f"test = {counts['test']}", f"train = {counts['train']}"]
    return "\n".join(lines) + "\n"


def _answers(path, rows, dev_ids):
    """One answer per development complaint, in complaint ID order. Every 7th from the 4th has the wrong
    Product with a real quote, and every 7th from the 6th a quote that is not in the text."""
    by_id = {row["Complaint ID"]: row for row in rows}
    names = list(PRODUCTS)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["complaint_id", "label", "quote"])
        for j, cid in enumerate(sorted(dev_ids, key=lambda c: (_id_number(c), c))):
            row = by_id[cid]
            label, quote = row["Product"], row["Consumer complaint narrative"].split(". ")[1]
            if j % 7 == 3:
                label = names[(names.index(label) + 1) % len(names)]
            elif j % 7 == 5:
                quote = NOT_IN_TEXT
            writer.writerow([cid, label, quote])


def make(folder):
    folder = Path(folder)
    folder.mkdir(parents=True)
    rows = _rows()
    export = folder / EXPORT
    _write_export(export, rows)
    _write(folder / "data_files.toml", _pin(export))
    labels = [label.name for label in load_labels(REPO / "config" / "labels.toml")]
    sha = hashlib.sha256(export.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        load_month(Path(tmp) / DB_PATH, export, MONTH, labels)
        summary = build_samples(Path(tmp) / DB_PATH, MONTH, seed=SEED, splits_dir=folder / "splits",
                                source_sha256=sha, dev_margin=DEV_MARGIN, test_margin=TEST_MARGIN)
    # The manifest is written with the platform's line ends. Git keeps LF, so LF is written here too.
    manifest = folder / "splits" / "manifest.json"
    manifest.write_bytes(manifest.read_bytes().replace(b"\r\n", b"\n"))
    _write(folder / "pool.toml", _pool(summary["by_product"]))
    _answers(folder / "answers.csv", rows, set(read_splits(folder / "splits")["dev"]))
    return summary


def main(argv):
    if len(argv) != 1:
        print("usage: python scripts/make_pipeline_fixture.py <new folder>")
        return 2
    folder = Path(argv[0])
    if folder.exists():
        print(f"error: {folder.name} already exists, and a fixture is never overwritten")
        return 1
    summary = make(folder)
    print(f"fixture made: {summary['pool']} complaints with text, dev {summary['dev']}, test {summary['test']}, "
          f"train {summary['train']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
