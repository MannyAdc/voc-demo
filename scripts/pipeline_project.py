"""The scheduled pipeline run (T015c): a synthetic project folder, and the real `voc` commands run on it.

The run cannot use real complaints. The export and the replay cache stay outside the repo, and CI has no
key. So `prepare` builds a work folder from the committed synthetic fixture in `tests/fixtures/pipeline`
(`SYN-` IDs only) and the real config, and a data folder that holds only the synthetic export. Then the
real commands run on them, in order, with every check they have:

1. `voc load july_2026` checks the export against the fixture's own pin, then the columns and IDs.
2. `voc dbt build` builds the models and runs the data tests.
3. `voc label dev` labels the development list on the mock backend, after the list checks.
4. `voc evaluate dev` scores the run against TF-IDF, after the list, run and pool count checks.

Nothing here changes a check. The test set is never labelled or scored, and no key is used.
The workflow `.github/workflows/scheduled.yml` runs `prepare`, then each command in its own step.

Run: uv run python scripts/pipeline_project.py prepare <new work folder> <new data folder>
     uv run python scripts/pipeline_project.py run <new work folder> <new data folder>
"""
import csv
import json
import shutil
import sys
from pathlib import Path

from voc import cli
from voc.baselines import cut_text
from voc.data import read_splits
from voc.labels import load_labels
from voc.pipeline import definitions, load_prompt_version
from voc.prompt import build_prompt

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "pipeline"
EXPORT = "synthetic_complaints.csv"
PROMPT = "v1"
NOTE = "scheduled run on the synthetic fixture, mock backend"
STEPS = (("load", "july_2026"), ("dbt", "build"), ("label", "dev", "--prompt", PROMPT),
         ("evaluate", "dev", "--prompt", PROMPT, "--note", NOTE))


class FixtureError(ValueError):
    """An error whose message is ours."""


def _column(path, name):
    with open(path, encoding="utf-8", newline="") as f:
        return [row[name] for row in csv.DictReader(f)]


def check_fixture(fixture):
    """Refuse a fixture with any complaint ID that is not synthetic."""
    fixture = Path(fixture)
    lists = {f"splits/{name}.csv": list(ids) for name, ids in read_splits(fixture / "splits").items()}
    found = {EXPORT: _column(fixture / EXPORT, "Complaint ID"),
             "answers.csv": _column(fixture / "answers.csv", "complaint_id"), **lists}
    for name, ids in found.items():
        bad = sum(not i.startswith("SYN-") for i in ids)
        if bad or not ids:
            raise FixtureError(f"{name} in the fixture holds {bad} complaint IDs that do not start with SYN-, "
                               f"out of {len(ids)}")


def _mock_answers(work, fixture, path):
    """The mock backend's answers, keyed by the exact prompt `voc label` builds for each complaint."""
    labels = load_labels(work / "config" / "labels.toml")
    names = [label.name for label in labels]
    version = load_prompt_version(work, PROMPT)
    with open(fixture / EXPORT, encoding="utf-8", newline="") as f:
        texts = {row["Complaint ID"]: row["Consumer complaint narrative"] for row in csv.DictReader(f)}
    items = []
    with open(fixture / "answers.csv", encoding="utf-8", newline="") as f:
        for answer in csv.DictReader(f):
            cid = answer["complaint_id"]
            text, _ = cut_text(texts[cid])
            prompt = build_prompt(version.instructions, names, text, complaint_id=cid,
                                  definitions=definitions(labels)).prompt
            items.append({"prompt": prompt, "text": json.dumps({"label": answer["label"], "quote": answer["quote"]})})
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(items), encoding="utf-8")
    return len(items)


def prepare(work, data, fixture=FIXTURE):
    """Build the work folder and the data folder. Returns the environment for the commands."""
    work, data, fixture = Path(work), Path(data), Path(fixture)
    check_fixture(fixture)
    for folder in (work, data):
        if folder.exists():
            raise FileExistsError(f"{folder.name} already exists. Give two new folders")
    (work / "config").mkdir(parents=True)
    data.mkdir(parents=True)
    for name in ("labels.toml", "tfidf.toml"):
        shutil.copy(REPO / "config" / name, work / "config" / name)
    shutil.copytree(REPO / "config" / "prompts", work / "config" / "prompts")
    for name in ("data_files.toml", "pool.toml"):
        shutil.copy(fixture / name, work / "config" / name)
    shutil.copytree(fixture / "splits", work / "splits")
    shutil.copytree(REPO / "dbt", work / "dbt", ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"))
    shutil.copy(fixture / EXPORT, data / EXPORT)
    answers = work / "mock" / "answers.json"
    count = _mock_answers(work, fixture, answers)
    lists = read_splits(work / "splits")
    print(f"synthetic project ready: {len(_column(fixture / EXPORT, 'Complaint ID'))} complaints in the export, "
          f"all with SYN- IDs. Lists: dev {len(lists['dev'])}, test {len(lists['test'])}, "
          f"train {len(lists['train'])}. {count} mock answers for the development list")
    return {"LLM_BACKEND": "mock", "VOC_DATA_DIR": str(data), "VOC_MOCK_FIXTURES": str(answers)}


def run(work, data, fixture=FIXTURE):
    """Prepare, then run every step in order. Stops at the first step that fails, and returns its code."""
    try:
        env = prepare(work, data, fixture)
    except (FixtureError, FileExistsError) as err:
        print(f"error: {err}")
        return 1
    for n, step in enumerate(STEPS, start=1):
        print(f"step {n} of {len(STEPS)}: voc {' '.join(step)}", flush=True)
        code = cli.main(list(step), env=env, root=work)
        if code != 0:
            print(f"step {n} failed, so the run stops here")
            return code
    print(f"all {len(STEPS)} steps passed")
    return 0


def main(argv):
    if len(argv) != 3 or argv[0] not in ("prepare", "run"):
        print("usage: python scripts/pipeline_project.py prepare|run <new work folder> <new data folder>")
        return 2
    action, work, data = argv
    if action == "run":
        return run(work, data)
    try:
        prepare(work, data)
    except (FixtureError, FileExistsError) as err:
        print(f"error: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
