"""Spec 004, J1: the frozen code's hash, the June list's hash, and the June run log, which only grows."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from voc.frozen import (FROZEN_PATHS, JuneRunsError, check_runs, code_hash, frozen_files, list_hash, matching,
                        read_runs)

REPO = Path(__file__).resolve().parents[1]
# The script runs in its own process. It must import this tree's `voc`, not the installed one, which can point at
# another checkout (the commit gate tests a copy of the staged files).
SCRIPT_ENV = {**os.environ, "PYTHONPATH": str(REPO / "src")}
A, B, C = "a" * 64, "b" * 64, "c" * 64
HEADER = ("# June runs\n\nIntro.\n\n| Date | Kind | June list hash | Code hash | Reason |\n"
          "|---|---|---|---|---|\n")


def _tree(root):
    """A small project with a file in every kind of frozen place, and some files outside them."""
    for rel, text in {"src/voc/a.py": "x = 1\n", "config/b.toml": "k = 1\n", "dbt/models/c.sql": "select 1\n",
                      "splits/june/june.csv": "complaint_id,content_hash\n", "pyproject.toml": "[project]\n",
                      "uv.lock": "lock\n", "cloud/job_a.yml": "job\n", "scripts/june_hash.py": "script\n",
                      ".github/workflows/june_approval.yml": "on: workflow_dispatch\n",
                      "docs/x.md": "doc\n", "scripts/other.py": "other\n", "runs/JUNE_RUNS.md": "log\n",
                      ".github/workflows/ci.yml": "ci\n"}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


def test_J1_the_frozen_places_are_the_ones_the_spec_names():
    assert FROZEN_PATHS[:9] == ("src", "config", "dbt", "splits", "pyproject.toml", "uv.lock", "cloud",
                                ".github/workflows/june_approval.yml", "scripts/june_hash.py")


def test_J1_the_code_hash_changes_with_any_frozen_file_and_nothing_else(tmp_path):
    root = _tree(tmp_path / "p")
    first = code_hash(root)
    for rel in ("docs/x.md", "scripts/other.py", "runs/JUNE_RUNS.md", ".github/workflows/ci.yml"):
        (root / rel).write_text("changed\n", encoding="utf-8")
    (root / "src" / "voc" / "__pycache__").mkdir()
    (root / "src" / "voc" / "__pycache__" / "a.cpython-313.pyc").write_bytes(b"\x00")
    (root / "dbt" / "target").mkdir()
    (root / "dbt" / "target" / "manifest.json").write_text("{}", encoding="utf-8")
    assert code_hash(root) == first
    for rel in ("src/voc/a.py", "config/b.toml", "dbt/models/c.sql", "splits/june/june.csv", "pyproject.toml",
                "uv.lock", "cloud/job_a.yml", "scripts/june_hash.py", ".github/workflows/june_approval.yml"):
        before = code_hash(root)
        (root / rel).write_text("changed again\n", encoding="utf-8")
        assert code_hash(root) != before, rel


def test_J1_the_code_hash_covers_file_names_too(tmp_path):
    root = _tree(tmp_path / "p")
    first = code_hash(root)
    (root / "src" / "voc" / "a.py").rename(root / "src" / "voc" / "renamed.py")
    assert code_hash(root) != first


def test_J1_the_code_hash_is_the_same_in_any_folder(tmp_path):
    one = _tree(tmp_path / "one")
    two = tmp_path / "elsewhere" / "two"
    shutil.copytree(one, two)
    assert code_hash(one) == code_hash(two)


def test_J1_the_frozen_files_are_exactly_the_tracked_ones():
    """On a clean checkout, so the laptop and Databricks' Git folder hash the same files. The commit gate tests a
    copy of the staged files that is not a git checkout, so there it is skipped, and CI runs it."""
    inside = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if inside.returncode != 0 or Path(inside.stdout.strip()).resolve() != REPO:
        assert not os.environ.get("GITHUB_ACTIONS"), "CI must run this test on its checkout"
        pytest.skip("not a git checkout of this repo, so there are no tracked files to compare (CI runs this)")
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--", *FROZEN_PATHS], capture_output=True,
                             text=True, check=True).stdout.split()
    assert frozen_files(REPO) == sorted(tracked)


def test_J1_no_frozen_file_has_windows_line_endings():
    """`.gitattributes` keeps LF, so the bytes are the same on Windows and on Linux."""
    assert [rel for rel in frozen_files(REPO) if b"\r\n" in (REPO / rel).read_bytes()] == []


def test_J1_the_list_hash_is_the_june_list_and_matches_its_manifest(tmp_path):
    manifest = json.loads((REPO / "splits" / "june" / "manifest.json").read_text(encoding="utf-8"))
    data = (REPO / "splits" / "june" / "june.csv").read_bytes()
    assert list_hash(REPO) == hashlib.sha256(data).hexdigest() == manifest["lists"]["june"]["sha256"]
    copy = tmp_path / "copy"
    shutil.copytree(REPO / "splits" / "june", copy / "splits" / "june")
    (copy / "splits" / "june" / "june.csv").write_bytes(data + b"SYN-1,x\n")
    with pytest.raises(JuneRunsError, match="does not match"):
        list_hash(copy)


def test_J1_the_hash_script_prints_the_two_hashes_only():
    # Since the second fix round of #94 the real row's hashes need both gates' passes, so this asks as for a
    # synthetic row. tests/test_job_a.py tests the refusal.
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "june_hash.py"), "--synthetic"], capture_output=True,
                            text=True, check=True, cwd=REPO, env=SCRIPT_ENV)
    lines = result.stdout.splitlines()
    assert lines[0] == f"june list sha256 {list_hash(REPO)}"
    assert lines[1] == f"frozen code sha256 {code_hash(REPO)} over {len(frozen_files(REPO))} files"
    assert len(lines) == 2


def _log(tmp_path, rows):
    path = tmp_path / "JUNE_RUNS.md"
    path.write_text(HEADER + "".join(f"| {' | '.join(row)} |\n" for row in rows), encoding="utf-8")
    return path


def test_J1_the_committed_june_run_log_has_its_header_and_no_entry_yet():
    entries = read_runs(REPO / "runs" / "JUNE_RUNS.md")
    assert entries == []
    text = (REPO / "runs" / "JUNE_RUNS.md").read_text(encoding="utf-8")
    assert "| Date | Kind | June list hash | Code hash | Reason |" in text and "only grows" in text


def test_J1_an_entry_is_found_by_its_two_hashes(tmp_path):
    entries = read_runs(_log(tmp_path, [("2026-11-06 10:00", "synthetic", A, B, "dry run"),
                                        ("2026-11-07 10:00", "real", C, B, "the June run")]))
    found = matching(entries, C, B)
    assert [e.kind for e in found] == ["real"]
    assert matching(entries, C, A) == [] and matching(entries, A, C) == []


@pytest.mark.parametrize("row, message", [
    (("2026-11-07 10:00", "rescore", C, B, "x"), "kind"),
    (("2026-11-07 10:00", "real", "x" * 64, B, "x"), "hash"),
    (("2026-11-07 10:00", "real", C, B[:63], "x"), "hash"),
    (("2026-11-07 10:00", "real", C, B), "columns"),
])
def test_J1_a_malformed_entry_is_refused(tmp_path, row, message):
    with pytest.raises(JuneRunsError, match=message):
        read_runs(_log(tmp_path, [row]))


def test_J1_later_entries_need_a_first_entry_and_a_reason(tmp_path):
    first = ("2026-11-07 10:00", "real", C, B, "the June run")
    for kind in ("reproduction", "resume", "second"):
        check_runs(read_runs(_log(tmp_path, [first, ("2026-11-08 10:00", kind, C, B, "why")])), real_list_hash=C)
        with pytest.raises(JuneRunsError, match="reason"):
            check_runs(read_runs(_log(tmp_path, [first, ("2026-11-08 10:00", kind, C, B, "")])), real_list_hash=C)
        with pytest.raises(JuneRunsError, match="first"):
            check_runs(read_runs(_log(tmp_path, [("2026-11-08 10:00", kind, C, B, "why")])), real_list_hash=C)


def test_J1_a_list_has_one_first_entry(tmp_path):
    rows = [("2026-11-07 10:00", "real", C, B, "the June run"), ("2026-11-08 10:00", "real", C, A, "again")]
    with pytest.raises(JuneRunsError, match="first"):
        check_runs(read_runs(_log(tmp_path, rows)), real_list_hash=C)


def test_J1_the_real_june_list_matches_no_synthetic_entry_and_a_real_entry_names_it(tmp_path):
    with pytest.raises(JuneRunsError, match="synthetic"):
        check_runs(read_runs(_log(tmp_path, [("2026-11-06 10:00", "synthetic", C, B, "dry run")])),
                   real_list_hash=C)
    with pytest.raises(JuneRunsError, match="real"):
        check_runs(read_runs(_log(tmp_path, [("2026-11-07 10:00", "real", A, B, "the June run")])),
                   real_list_hash=C)


def test_J1_ci_checks_that_the_june_run_log_only_grows():
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "scripts/check_test_runs.py" in workflow and "runs/JUNE_RUNS.md" in workflow
    assert workflow.count("origin/main:runs/JUNE_RUNS.md") == 2


# The review of #89: the July development labels, the script's check against git, the run log's rules on main,
# strict rows, and the CI step.


def test_J7_the_july_development_labels_are_frozen_too():
    """Job B checks the refit TF-IDF + LR against them (J7), so a change to them must change the hash."""
    assert "results/eval/v1_dev.csv" in FROZEN_PATHS and "results/eval/v1_dev.csv" in frozen_files(REPO)


def _git_tree(tmp_path):
    root = _tree(tmp_path / "g")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def test_J1_the_hash_script_refuses_files_that_git_does_not_track(tmp_path):
    from voc.frozen import differs_from_git

    root = _git_tree(tmp_path)
    assert differs_from_git(root) == []
    (root / "src" / "voc" / "stray.py").write_text("x = 2\n", encoding="utf-8")
    (root / "config" / "b.toml").unlink()
    assert differs_from_git(root) == ["config/b.toml", "src/voc/stray.py"]
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "june_hash.py"), str(root)],
                            capture_output=True, text=True, env=SCRIPT_ENV)
    assert result.returncode == 1
    assert "2 frozen files differ from the files git tracks" in result.stdout and "stray" not in result.stdout


def test_J1_without_git_the_check_is_skipped_and_said_so(tmp_path):
    from voc.frozen import differs_from_git

    assert differs_from_git(_tree(tmp_path / "nogit")) is None


def test_J1_the_committed_june_run_log_follows_its_rules():
    check_runs(read_runs(REPO / "runs" / "JUNE_RUNS.md"), real_list_hash=list_hash(REPO))


@pytest.mark.parametrize("line", [
    f"  | 2026-11-07 10:00 | real | {C} | {B} | the June run |",
    f"| Date 2026-11-07 | real | {C} | {B} | the June run |",
    f"|--- | real | {C} | {B} | the June run |",
])
def test_J1_a_row_the_reader_would_skip_is_refused(tmp_path, line):
    path = tmp_path / "JUNE_RUNS.md"
    path.write_text(HEADER + line + "\n", encoding="utf-8")
    with pytest.raises(JuneRunsError):
        read_runs(path)


def test_J1_the_ci_step_runs_the_log_check_on_the_june_log_in_repo_checks():
    import yaml

    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    runs = [step.get("run", "") for step in workflow["jobs"]["repo-checks"]["steps"]]
    assert any("scripts/check_test_runs.py" in run and '"$base" runs/JUNE_RUNS.md' in run for run in runs)


def test_J1_the_log_check_names_the_log_it_checks(tmp_path):
    base, head = tmp_path / "base" / "JUNE_RUNS.md", tmp_path / "head" / "JUNE_RUNS.md"
    for path, text in ((base, "| a |\n"), (head, "| a |\n| b |\n")):
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8")
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "check_test_runs.py"), str(base), str(head)],
                            capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.startswith("JUNE_RUNS.md: ")
