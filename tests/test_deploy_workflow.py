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


# Review of #56


CI = REPO / ".github" / "workflows" / "ci.yml"
GUIDE = REPO / "docs" / "DEPLOY.md"
GO = "steps.ready.outputs.go == 'true'"


def _job():
    return next(iter(_workflow()["jobs"].values()))


def test_A15_the_job_condition_is_exactly_ci_success_on_a_push_to_main_of_this_repo():
    # Checked whole, so an added `|| true` cannot slip through.
    assert _job()["if"] == ("github.event.workflow_run.conclusion == 'success'"
                            " && github.event.workflow_run.event == 'push'"
                            " && github.event.workflow_run.head_branch == 'main'"
                            " && github.event.workflow_run.head_repository.full_name == github.repository")


def test_A15_the_trigger_names_the_ci_workflow_by_its_own_name():
    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert _triggers(_workflow())["workflow_run"]["workflows"] == [ci["name"]]


def test_A15_the_first_step_decides_whether_to_deploy_and_every_other_step_follows_it():
    steps = _job()["steps"]
    assert steps[0]["id"] == "ready" and "uses" not in steps[0]
    for step in steps[1:]:
        assert step["if"] == GO, step.get("name")


def test_A15_it_skips_without_failing_until_the_azure_secrets_are_set():
    ready = _job()["steps"][0]
    assert ready["env"]["CLIENT_ID"] == "${{ secrets.AZURE_CLIENT_ID }}"
    assert ready["env"]["TENANT_ID"] == "${{ secrets.AZURE_TENANT_ID }}"
    assert ready["env"]["SUBSCRIPTION_ID"] == "${{ secrets.AZURE_SUBSCRIPTION_ID }}"
    run = ready["run"]
    for name in ("CLIENT_ID", "TENANT_ID", "SUBSCRIPTION_ID"):
        assert f'-z "${name}"' in run, name
    assert 'echo "go=false" >> "$GITHUB_OUTPUT"' in run and "exit 0" in run


def test_A15_it_skips_when_main_has_moved_on_since_the_tested_commit():
    # Deploys finish in the order their CI runs end, so an older commit could overwrite a newer one.
    ready = _job()["steps"][0]
    assert ready["env"]["TESTED"] == "${{ github.event.workflow_run.head_sha }}"
    assert ready["env"]["GH_TOKEN"] == "${{ github.token }}"
    run = ready["run"]
    assert 'gh api "repos/$GITHUB_REPOSITORY/commits/main" --jq .sha' in run
    assert '"$TESTED"' in run
    assert run.rstrip().endswith('echo "go=true" >> "$GITHUB_OUTPUT"')


def test_A15_the_zip_names_the_commit_it_was_built_from():
    runs = "\n".join(s.get("run", "") for s in _steps(_workflow()))
    archive = next(line for line in runs.splitlines() if line.strip().startswith("git archive"))
    assert '--add-virtual-file="BUILD_COMMIT:$(git rev-parse HEAD)"' in archive


def test_A15_the_health_check_waits_for_that_exact_commit_for_up_to_10_minutes():
    health = next(s["run"] for s in _steps(_workflow()) if "/api/health" in s.get("run", ""))
    assert "git rev-parse HEAD" in health and "jq -r .commit" in health
    # 20 tries of at most 15 seconds each, with 15 seconds between them: at most 600 seconds.
    assert "seq 1 20" in health and "--max-time 15" in health and "sleep 15" in health
    assert "10 minutes" in health


def test_A15_the_manual_redeploy_also_names_its_commit():
    script = (REPO / "scripts" / "deploy_azure.ps1").read_text(encoding="utf-8")
    archive = next(line for line in script.splitlines() if line.lstrip().startswith("git archive"))
    assert "--add-virtual-file=" in archive and "BUILD_COMMIT:" in archive


def _setup_block():
    guide = GUIDE.read_text(encoding="utf-8")
    section = guide[guide.index("## Automatic deploy"):]
    return section[section.index("```powershell"):section.index("```", section.index("```powershell") + 3)]


def test_A15_the_setup_stops_at_the_first_failed_command():
    lines = [line.strip() for line in _setup_block().splitlines()]
    commands = [i for i, line in enumerate(lines) if re.match(r"(\$\w+ = )?(az|gh) ", line)]
    assert len(commands) >= 9
    for i in commands:
        assert lines[i + 1].startswith("if ($LASTEXITCODE -ne 0)"), lines[i]


def test_A15_the_secrets_are_set_from_a_value_not_a_pipe():
    block = _setup_block()
    assert "| gh secret set" not in block
    for name, value in (("AZURE_CLIENT_ID", "$clientId"), ("AZURE_TENANT_ID", "$tenant"),
                        ("AZURE_SUBSCRIPTION_ID", "$sub")):
        assert f"gh secret set {name} --repo $repo --body {value}" in block


def test_A15_the_guide_says_to_run_the_setup_once_and_what_a_403_means():
    section = GUIDE.read_text(encoding="utf-8")
    section = section[section.index("## Automatic deploy"):section.index("## Redeploying after a change")]
    assert "once" in section and "403" in section


# Second review of #56


def _blocks():
    """The PowerShell blocks of the "Automatic deploy" section, as lists of stripped, non-empty lines."""
    guide = GUIDE.read_text(encoding="utf-8")
    section = guide[guide.index("## Automatic deploy"):guide.index("## Redeploying after a change")]
    found = re.findall(r"```powershell\n(.*?)```", section, flags=re.S)
    return [[line.strip() for line in block.splitlines() if line.strip()] for block in found]


def test_A15_every_setup_line_runs_inside_one_block_so_a_failure_stops_the_rest():
    # A throw outside & { } does not stop the lines pasted after it.
    for lines in _blocks():
        assert lines[0] == "& {" and lines[-1] == "}", lines[:2]
        assert "& {" not in lines[1:]


def test_A15_the_setup_checks_its_folder_and_its_repo_before_any_change():
    setup = _blocks()[0]
    folder = next(i for i, line in enumerate(setup) if 'Test-Path ".github/workflows/deploy.yml"' in line)
    repo = next(i for i, line in enumerate(setup) if '$repo -notlike "*/voc-demo"' in line)
    first_change = next(i for i, line in enumerate(setup) if line.startswith("$clientId = az ad app create"))
    assert folder < repo < first_change
    assert not any("Read-Host" in line for line in setup)


def test_A15_the_403_fix_checks_each_command_and_needs_exactly_one_identity():
    fix = _blocks()[1]
    commands = [i for i, line in enumerate(fix) if re.match(r"(\$\w+ = @?\(?)?(az|gh) ", line)]
    assert len(commands) >= 3
    for i in commands:
        assert fix[i + 1].startswith("if ($LASTEXITCODE -ne 0)"), fix[i]
    assert any("$ids.Count -ne 1" in line for line in fix)


def test_A15_the_manual_redeploy_names_a_full_commit_id():
    # Renamed in the third review of #56: -Ref names a branch. Tags are not under origin/, so "for a tag" was wrong.
    script = (REPO / "scripts" / "deploy_azure.ps1").read_text(encoding="utf-8")
    assert 'git rev-parse "origin/$Ref^{commit}"' in script


# Third review of #56


def test_A15_the_setup_checks_the_web_app_is_in_the_signed_in_subscription_before_any_change():
    # Without this, a sign-in to another subscription would create an app registration, then fail and leave it.
    setup = _blocks()[0]
    webapp = next(i for i, line in enumerate(setup) if line == "az webapp " + "show --name $app --resource-group $rg -o none")
    first_change = next(i for i, line in enumerate(setup) if line.startswith("$clientId = az ad app create"))
    assert webapp < first_change
    assert setup[webapp + 1].startswith("if ($LASTEXITCODE -ne 0)")


# The first automatic deploy, 1 November: Azure refused GitHub's token (AADSTS700213).


def test_A15_the_setup_trusts_the_subject_with_the_owner_and_repo_ids():
    # GitHub's tokens for repos made after mid-July 2026 name the owner and repo with fixed numeric IDs:
    # repo:OWNER@OWNER-ID/REPO@REPO-ID:ref:refs/heads/main. The old form repo:OWNER/REPO:... is refused.
    setup = _blocks()[0]
    owner_id = next(i for i, line in enumerate(setup) if line.startswith("$ownerId = gh api"))
    repo_id = next(i for i, line in enumerate(setup) if line.startswith("$repoId = gh api"))
    for i in (owner_id, repo_id):
        assert setup[i + 1].startswith("if ($LASTEXITCODE -ne 0)")
    subject = next(line for line in setup if line.startswith("$subject = "))
    assert '"@" + $ownerId' in subject and '"@" + $repoId' in subject and ":ref:refs/heads/main" in subject
    credential = next(line for line in setup if line.startswith("$credential = "))
    assert "$subject" in credential and "$repo + ':ref" not in credential
    first_change = next(i for i, line in enumerate(setup) if line.startswith("$clientId = az ad app create"))
    assert owner_id < first_change and repo_id < first_change


def test_A15_the_guide_says_how_to_fix_a_credential_made_with_the_old_subject():
    guide = GUIDE.read_text(encoding="utf-8")
    section = guide[guide.index("## Automatic deploy"):guide.index("## Redeploying after a change")]
    assert "AADSTS700213" in section and "az ad app federated-credential update" in section
