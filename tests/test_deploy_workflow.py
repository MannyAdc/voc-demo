"""A15: the automatic deploy of the public copy (owner decision, 31 October 2026).

After CI passes on main, a workflow uploads the same ZIP as scripts/deploy_azure.ps1 and checks the live health
route. These read the workflow file. They never run it, and they never open the network.
"""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "deploy.yml"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(flow):
    # YAML 1.1 reads the key "on" as True.
    return flow.get("on", flow.get(True))


def _steps(flow):
    return [step for job in flow["jobs"].values() for step in job["steps"]]


def test_A15_the_deploy_runs_only_after_CI_passes_on_main():
    flow = _workflow()
    assert _triggers(flow) == {"workflow_run": {"workflows": ["CI"], "types": ["completed"], "branches": ["main"]}}
    for job in flow["jobs"].values():
        condition = job["if"]
        for part in ("github.event.workflow_run.conclusion == 'success'", "github.event.workflow_run.event == 'push'",
                     "github.event.workflow_run.head_branch == 'main'"):
            assert part in condition, part


def test_A15_the_deploy_may_only_read_the_repo_and_ask_for_a_sign_in_token():
    flow = _workflow()
    assert flow["permissions"] == {"contents": "read", "id-token": "write"}
    for job in flow["jobs"].values():
        assert "permissions" not in job


def test_A15_it_deploys_the_commit_CI_tested_and_keeps_no_git_credential():
    checkout = next(s for s in _steps(_workflow()) if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"
    assert checkout["with"]["persist-credentials"] is False


def test_A15_every_action_is_pinned_to_a_commit():
    for step in _steps(_workflow()):
        if "uses" in step:
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), step["uses"]


def test_A15_it_signs_in_with_openid_connect_and_holds_no_password():
    login = next(s for s in _steps(_workflow()) if s.get("uses", "").startswith("azure/login@"))
    assert login["with"] == {"client-id": "${{ secrets.AZURE_CLIENT_ID }}",
                             "tenant-id": "${{ secrets.AZURE_TENANT_ID }}",
                             "subscription-id": "${{ secrets.AZURE_SUBSCRIPTION_ID }}"}
    assert "creds" not in WORKFLOW.read_text(encoding="utf-8")


def test_A15_it_packs_like_the_script_and_prints_no_resource_id():
    runs = "\n".join(s.get("run", "") for s in _steps(_workflow()))
    archive = next(line for line in runs.splitlines() if line.strip().startswith("git archive"))
    assert ":!uv.lock" in archive and ":!pyproject.toml" in archive
    for line in runs.splitlines():
        if line.strip().startswith("az "):
            assert "-o none" in line, line


def test_A15_no_event_text_reaches_a_shell_command():
    # A branch name or commit message is chosen by whoever pushes. Only fixed values go into run scripts.
    for step in _steps(_workflow()):
        assert "github.event" not in step.get("run", ""), step.get("name")


def test_A15_it_checks_the_live_health_route_after_the_upload():
    runs = [s.get("run", "") for s in _steps(_workflow())]
    upload = next(i for i, run in enumerate(runs) if "az webapp deploy" in run)
    health = next(i for i, run in enumerate(runs) if "/api/health" in run)
    assert health > upload
    assert "--fail" in runs[health]
