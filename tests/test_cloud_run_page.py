"""Spec 004, J8: `docs/CLOUD_RUN.md`, the plain page on how the June run passed data between Databricks, Azure,
GitHub and the Anthropic API.

Some of the page's facts are read from their sources here: the run IDs and the count from the run's own summary,
`results/june/v1_june.json`, the token cap and the expected cost as the code computes them, the jobs' names, task keys
and trigger folder from the job definitions in `cloud/`, and the app and environment names from the workflows. The
times, the worst case and the sign-ins' states are checked by review, not here. Every link on the page must point to
a file and heading in the repo, and the README must link the page, or nobody finds it.
"""
import json
import re
import tomllib
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "CLOUD_RUN.md"
WORKFLOWS = REPO / ".github" / "workflows"


def _page():
    return PAGE.read_text(encoding="utf-8")


def _slug(heading):
    """GitHub's anchor for a heading: lower case, punctuation but hyphens dropped, spaces as hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_J8_cloud_page_names_the_real_runs_from_the_summary():
    s = json.loads((REPO / "results" / "june" / "v1_june.json").read_text(encoding="utf-8"))
    page = _page()
    for key in ("job_a_run_id", "github_run_id", "job_b_run_id"):
        assert str(s[key]) in page, key
    assert f"{s['complaints']:,}" in page


def test_J8_cloud_page_states_the_cap_and_the_expected_cost_as_the_code_computes_them():
    from voc.job_a import expected_cost

    count = json.loads((REPO / "splits" / "june" / "manifest.json").read_text(encoding="utf-8"))["lists"]["june"]
    per_1000 = json.loads((REPO / "results" / "eval" / "v1_test.json").read_text(encoding="utf-8"))["llm"]
    cap = tomllib.loads((REPO / "config" / "budget.toml").read_text(encoding="utf-8"))["june_cap_tokens"]
    page = _page()
    assert f"${expected_cost(Decimal(per_1000['cost_per_1000_usd']), count['count'])}" in page
    assert cap % 1_000_000 == 0
    assert f"cap of {cap // 1_000_000} million" in page


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
        assert (WORKFLOWS / workflow).is_file()
        assert f"`{workflow}`" in page, workflow


def test_J8_cloud_page_names_the_app_and_the_environments_as_the_workflows_do():
    page = _page()
    app = re.search(r"^\s+APP: (voc-\S+)", (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8"), flags=re.M)
    assert f"`{app.group(1)}`" in page
    environments = re.findall(r"^\s+environment: (\S+)", "".join(
        (WORKFLOWS / name).read_text(encoding="utf-8") for name in ("june_approval.yml", "deploy_receiver.yml")),
        flags=re.M)
    assert sorted(environments) == ["june-figures", "june-run", "receiver-deploy"]
    for environment in environments:
        assert f"`{environment}`" in page, environment


def test_J8_every_link_on_the_cloud_page_points_to_a_repo_file():
    links = re.findall(r"\]\(([^)#\s]+)(?:#([^)\s]*))?\)", _page())
    local = [(target, anchor) for target, anchor in links if not target.startswith(("http://", "https://"))]
    assert local
    for target, anchor in local:
        path = (PAGE.parent / target).resolve()
        assert path.exists(), target
        if anchor:
            headings = re.findall(r"^#+ (.+)$", path.read_text(encoding="utf-8"), flags=re.M)
            assert anchor in {_slug(h) for h in headings}, f"{target}#{anchor}"


def test_J8_readme_links_the_cloud_page():
    assert (REPO / "README.md").read_text(encoding="utf-8").count("(docs/CLOUD_RUN.md)") == 2
