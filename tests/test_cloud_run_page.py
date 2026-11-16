"""Spec 004, J8: `docs/CLOUD_RUN.md`, the plain page on how the June run passed data between Databricks, Azure,
GitHub and the Anthropic API.

The run IDs and counts the page states are read from the run's own summary, `results/june/v1_june.json`, and the
names of the cloud pieces from the job definitions in `cloud/`, so the page cannot drift from what ran. Every link on
the page must point to a file in the repo, and the README must link the page, or nobody finds it.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "CLOUD_RUN.md"


def _page():
    return PAGE.read_text(encoding="utf-8")


def test_J8_cloud_page_names_the_real_runs_from_the_summary():
    s = json.loads((REPO / "results" / "june" / "v1_june.json").read_text(encoding="utf-8"))
    page = _page()
    for key in ("job_a_run_id", "github_run_id", "job_b_run_id"):
        assert str(s[key]) in page, key
    assert f"{s['complaints']:,}" in page


def test_J8_cloud_page_names_the_pieces_as_the_job_definitions_do():
    page = _page()
    job_a = (REPO / "cloud" / "job_a.yml").read_text(encoding="utf-8")
    job_b = (REPO / "cloud" / "job_b.yml").read_text(encoding="utf-8")
    trigger = re.search(r"file_arrival:\s*\n\s*url: /Volumes/workspace/default/(\S+)", job_a).group(1)
    assert f"`{trigger}`" in page
    for name in re.findall(r"^\s+name: (\S+)", job_a + job_b, flags=re.M):
        assert f"`{name}`" in page, name
    for task in re.findall(r"- task_key: (\w+)", job_a + job_b):
        assert f"`{task}`" in page, task
    for workflow in ("june_approval.yml", "deploy.yml", "deploy_receiver.yml"):
        assert (REPO / ".github" / "workflows" / workflow).is_file()
        assert f"`{workflow}`" in page, workflow


def test_J8_every_link_on_the_cloud_page_points_to_a_repo_file():
    targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", _page())
    local = [t for t in targets if not t.startswith(("http://", "https://"))]
    assert local
    for target in local:
        assert (PAGE.parent / target).resolve().exists(), target


def test_J8_readme_links_the_cloud_page():
    assert "(docs/CLOUD_RUN.md)" in (REPO / "README.md").read_text(encoding="utf-8")
