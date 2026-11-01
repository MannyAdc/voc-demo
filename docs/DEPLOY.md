# Deploying the public copy to Azure App Service

The public copy (spec 002, rule A13) is the dashboard with the committed results files only. It answers only to its own Azure host name, never reads the local staged table, never serves complaint text or the consumer's own choice, and stores no review. So nothing in it is private: it is the same data as the public repo.

The owner runs every command here, in their own PowerShell, after `az login -o none`. Every `az` command here ends with `-o none`, because `az` otherwise prints resource IDs, and they hold the subscription ID. Claude creates no account and holds no Azure credential.

## Facts checked on Microsoft's pages (30 October 2026)

- App Service pricing for Linux: the Free (F1) tier is "Shared (60 CPU minutes / day)", with 1 GB RAM and 1 GB storage. The page does not say whether F1 runs Python on Linux (it does: see the first deploy below), so the first command may need the Basic (B1) tier instead, which the free account's credit covers. The Python quickstart recommends B1 "for better performance over the Free F1 plan". ([App Service pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/))
- A ZIP deploy runs the build, including `pip install -r requirements.txt`, only when `SCM_DO_BUILD_DURING_DEPLOYMENT` is `true`. For Python 3.13 and earlier, a FastAPI app needs a startup command. ([Python quickstart](https://learn.microsoft.com/en-us/azure/app-service/quickstart-python), updated 27 July 2026)
- Always On is off by default. Without it, "the app is unloaded after 20 minutes without any incoming requests", and the next request waits for the app to start. This app does not set it. ([Configure an App Service app](https://learn.microsoft.com/en-us/azure/app-service/configure-common), dated 13 April 2026)
- `WEBSITE_HOSTNAME` is set by App Service: "Primary host name for the app". ([App settings reference](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings), updated 10 September 2026)

## What is deployed

- A ZIP of the committed files on `main`, made with `git archive`, so nothing git ignores (data, `.env`, the deny list) can be in it.
- `requirements.txt`, the public copy's packages only, pinned from `uv.lock`: the `public` dependency group (fastapi, starlette, uvicorn and duckdb) and what they need. It is made with `uv export --native-tls --frozen --only-group public --no-hashes --no-emit-project --format requirements-txt > requirements.txt`. Tests check each pin matches `uv.lock`, and that every package the public app loads is pinned.
- The ZIP leaves out `pyproject.toml` and `uv.lock`. Microsoft lists both a `requirements.txt` build and a `uv` build, and does not say which wins when both are there. Without them, the build can only use `requirements.txt`.
- The startup command `python -m uvicorn voc.public:app --host 0.0.0.0 --port 8000 --app-dir src`.

## The commands

Pick an app name that nobody else uses, with no personal name in it, for example `voc-demo-` and four digits. It becomes `https://<app name>.azurewebsites.net`.

```powershell
cd <your clone of this repo>
git switch main
git pull
$app = "voc-demo-1234"   # change the digits
$rg = "voc-demo-rg"
az group create --name $rg --location australiaeast -o none
az appservice plan create --name voc-demo-plan --resource-group $rg --sku F1 --is-linux -o none
az webapp create --name $app --resource-group $rg --plan voc-demo-plan --runtime "PYTHON:3.13" -o none
az webapp config appsettings set --name $app --resource-group $rg --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true -o none
az webapp config set --name $app --resource-group $rg --startup-file "python -m uvicorn voc.public:app --host 0.0.0.0 --port 8000 --app-dir src" -o none
az webapp log config --name $app --resource-group $rg --docker-container-logging filesystem -o none
git archive --format=zip -o "$env:TEMP\voc-site.zip" main -- . ":!uv.lock" ":!pyproject.toml"
az webapp deploy --name $app --resource-group $rg --src-path "$env:TEMP\voc-site.zip" --type zip -o none
```

Then open `https://<app name>.azurewebsites.net`. The request log (rule A9) is in the log stream:

```powershell
az webapp log tail --name $app --resource-group $rg
```

and the counters are at `https://<app name>.azurewebsites.net/api/health`.

## If a step fails

- `az appservice plan create` refuses F1 for Linux: run it again with `--sku B1`. That costs money, which the free account's credit covers. Delete the group afterwards to stop it.
- `az webapp create` refuses the runtime: list the runtimes with `az webapp list-runtimes --os-type linux` and pick the closest Python 3.13 or later.
- `az` is not found in a PowerShell window opened before the install: open a new window, or reload the path in that window with `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")`.

## What happened on the first deploy (30 October 2026)

The owner ran the setup commands above, each with `-o none`, with the app name `voc-demo-20261030`. Creating the plan printed "Creating App Service Plan 'voc-demo-plan' (Linux, SKU: F1)", then, because the account was new, "Resource provider 'Microsoft.Web' used by this operation is not registered. We are registering for you." and "Registration succeeded." Before the code was uploaded, the address answered 503, because the start command had nothing to start. The owner then uploaded the `feat/public-mode` branch (pull request #50) with `git archive` and `az webapp deploy`, and the dashboard loaded at https://voc-demo-20261030.azurewebsites.net. So F1 does run this Python app on Linux.

## Automatic deploy (A15)

After CI passes on a push to `main`, the workflow `.github/workflows/deploy.yml` uploads the same ZIP as the script below, plus a file `BUILD_COMMIT` that names the commit. It then waits, for up to 10 minutes, until `https://<app name>.azurewebsites.net/api/health` reports that exact commit. Nobody runs anything after a merge.

The workflow's first step decides whether to deploy. It ends the run without failing in two cases: the three secrets below are not set yet, or `main` has moved on since the tested commit, so the run for the newer commit deploys instead.

It signs in to Azure with OpenID Connect: GitHub gives the workflow a short-lived token, and Azure trusts it only for this repo's `main` branch and only for this one web app. No password or key is stored. Facts checked on Microsoft's page [Deploy by using GitHub Actions](https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions) (dated 28 November 2025, read 31 October 2026): the role "Website Contributor" on the web app, the issuer `https://token.actions.githubusercontent.com`, the audience `api://AzureADTokenExchange`, and the three secrets below. The subject comes from GitHub, not from Microsoft's page. For repos created after mid-July 2026, GitHub's token names the owner and the repo with their fixed numeric IDs: `repo:<owner>@<owner id>/<repo>@<repo id>:ref:refs/heads/main` (GitHub's [OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc), read 1 November 2026). Microsoft's page shows the older form `repo:<owner>/<repo>:ref:refs/heads/main`, which Azure refused for this repo on 1 November (AADSTS700213). GitHub's page [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) says a `workflow_run` workflow runs with the default branch as its ref, so the subject is `main`'s. The workflow checks out the exact commit CI tested.

One-time setup, by the owner. **Run it once.** A second run would make a second app registration named `voc-demo-deploy`. If that happens, delete the extra one in the Azure portal, under Microsoft Entra ID, App registrations.

Open PowerShell in your clone of this repo, the folder that holds `README.md`, and paste the whole block. It runs as one piece, so it stops at the first command that fails. Before it changes anything, it checks that it runs in this repo's folder, that the folder's GitHub repo is `voc-demo`, and that the web app is in the Azure subscription you signed in to. Every ID stays in a variable and goes straight into a GitHub secret, so none is printed:

```powershell
& {
$env:Path = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;C:\Program Files\GitHub CLI;" + $env:Path
if (-not (Test-Path ".github/workflows/deploy.yml")) { throw "Open PowerShell in your clone of this repo first." }
az login -o none
if ($LASTEXITCODE -ne 0) { throw "az login failed" }
gh auth status
if ($LASTEXITCODE -ne 0) { throw "gh is not signed in. Run gh auth login first." }
$app = "voc-demo-20261030"
$rg = "voc-demo-rg"
$repo = gh repo view --json nameWithOwner --jq .nameWithOwner
if ($LASTEXITCODE -ne 0) { throw "gh repo view failed" }
if ($repo -notlike "*/voc-demo") { throw "This folder's GitHub repo is not voc-demo, so nothing was changed." }
$pair = @(gh api "repos/$repo" --jq ".owner.id, .id")
if ($LASTEXITCODE -ne 0) { throw "Reading the repo's IDs from GitHub failed" }
if ($pair.Count -ne 2) { throw "GitHub did not return the owner and repo IDs" }
$owner, $name = $repo.Split("/")
$subject = "repo:" + $owner + "@" + $pair[0] + "/" + $name + "@" + $pair[1] + ":ref:refs/heads/main"
az webapp show --name $app --resource-group $rg -o none
if ($LASTEXITCODE -ne 0) { throw "The web app is not in the subscription you signed in to, so nothing was changed." }
$sub = az account show --query id -o tsv
if ($LASTEXITCODE -ne 0) { throw "az account show failed" }
$tenant = az account show --query tenantId -o tsv
if ($LASTEXITCODE -ne 0) { throw "az account show failed" }
$clientId = az ad app create --display-name "voc-demo-deploy" --query appId -o tsv
if ($LASTEXITCODE -ne 0) { throw "az ad app create failed" }
$appObjectId = az ad app show --id $clientId --query id -o tsv
if ($LASTEXITCODE -ne 0) { throw "az ad app show failed" }
$spObjectId = az ad sp create --id $clientId --query id -o tsv
if ($LASTEXITCODE -ne 0) { throw "az ad sp create failed" }
az role assignment create --role "Website Contributor" --assignee-object-id $spObjectId --assignee-principal-type ServicePrincipal --scope "/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.Web/sites/$app" -o none
if ($LASTEXITCODE -ne 0) { throw "az role assignment create failed" }
$credential = '{"name": "voc-demo-main", "issuer": "https://token.actions.githubusercontent.com", "subject": "' + $subject + '", "audiences": ["api://AzureADTokenExchange"]}'
[System.IO.File]::WriteAllText("$env:TEMP\voc-credential.json", $credential)
az ad app federated-credential create --id $appObjectId --parameters "$env:TEMP\voc-credential.json" -o none
if ($LASTEXITCODE -ne 0) { throw "az ad app federated-credential create failed" }
Remove-Item "$env:TEMP\voc-credential.json"
gh secret set AZURE_CLIENT_ID --repo $repo --body $clientId
if ($LASTEXITCODE -ne 0) { throw "gh secret set failed" }
gh secret set AZURE_TENANT_ID --repo $repo --body $tenant
if ($LASTEXITCODE -ne 0) { throw "gh secret set failed" }
gh secret set AZURE_SUBSCRIPTION_ID --repo $repo --body $sub
if ($LASTEXITCODE -ne 0) { throw "gh secret set failed" }
"Done: the identity, its role on the web app, the federated credential and the three secrets."
}
```

`WriteAllText` writes the file without a byte order mark, which Windows PowerShell 5.1's `Set-Content` would add. `--body` gives each secret its value directly, so no newline from a pipe can slip in.

**If the first automatic deploy fails at the upload with a 403**, the role on the web app alone was not enough for `az webapp deploy`. Give the same role on the resource group instead. Paste this in the same kind of PowerShell window. It stops if it does not find exactly one `voc-demo-deploy` identity:

```powershell
& {
$env:Path = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;C:\Program Files\GitHub CLI;" + $env:Path
$sub = az account show --query id -o tsv
if ($LASTEXITCODE -ne 0) { throw "az account show failed. Run az login first." }
$ids = @(az ad sp list --display-name "voc-demo-deploy" --query "[].id" -o tsv)
if ($LASTEXITCODE -ne 0) { throw "az ad sp list failed" }
if ($ids.Count -ne 1) { throw "Expected one voc-demo-deploy identity, found $($ids.Count). Delete the extra one first." }
az role assignment create --role "Website Contributor" --assignee-object-id $ids[0] --assignee-principal-type ServicePrincipal --scope "/subscriptions/$sub/resourceGroups/voc-demo-rg" -o none
if ($LASTEXITCODE -ne 0) { throw "az role assignment create failed" }
"Done: the role on the resource group."
}
```

Then rerun the failed run from the Actions tab.

**If an automatic deploy fails at the sign-in with AADSTS700213** ("No matching federated identity record found"), the credential trusts a different subject from the one GitHub sends. A setup run before 1 November 2026 used the older form. This block updates the credential to the form above. Paste it in PowerShell, in your clone of this repo. It stops if it does not find exactly one `voc-demo-deploy` app:

```powershell
& {
$env:Path = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;C:\Program Files\GitHub CLI;" + $env:Path
if (-not (Test-Path ".github/workflows/deploy.yml")) { throw "Open PowerShell in your clone of this repo first." }
az login -o none
if ($LASTEXITCODE -ne 0) { throw "az login failed" }
$repo = gh repo view --json nameWithOwner --jq .nameWithOwner
if ($LASTEXITCODE -ne 0) { throw "gh repo view failed" }
if ($repo -notlike "*/voc-demo") { throw "This folder's GitHub repo is not voc-demo, so nothing was changed." }
$pair = @(gh api "repos/$repo" --jq ".owner.id, .id")
if ($LASTEXITCODE -ne 0) { throw "Reading the repo's IDs from GitHub failed" }
if ($pair.Count -ne 2) { throw "GitHub did not return the owner and repo IDs" }
$owner, $name = $repo.Split("/")
$subject = "repo:" + $owner + "@" + $pair[0] + "/" + $name + "@" + $pair[1] + ":ref:refs/heads/main"
$ids = @(az ad app list --display-name "voc-demo-deploy" --query "[].id" -o tsv)
if ($LASTEXITCODE -ne 0) { throw "az ad app list failed" }
if ($ids.Count -ne 1) { throw "Expected one voc-demo-deploy app, found $($ids.Count), so nothing was changed." }
$credential = '{"name": "voc-demo-main", "issuer": "https://token.actions.githubusercontent.com", "subject": "' + $subject + '", "audiences": ["api://AzureADTokenExchange"]}'
[System.IO.File]::WriteAllText("$env:TEMP\voc-credential.json", $credential)
az ad app federated-credential update --id $ids[0] --federated-credential-id voc-demo-main --parameters "$env:TEMP\voc-credential.json" -o none
if ($LASTEXITCODE -ne 0) { throw "az ad app federated-credential update failed" }
Remove-Item "$env:TEMP\voc-credential.json"
"Done: the credential now trusts the subject with the owner and repo IDs."
}
```

Then rerun the failed run from the Actions tab, or merge the next change.

To stop automatic deploys, delete the federated credential or the three secrets. The script below still works by hand.

## Redeploying after a change

By hand, for example before the automatic deploy is set up: one line, after `az login`, from the repo folder:

```powershell
.\scripts\deploy_azure.ps1 -App voc-demo-20261030
```

It packs the committed files of `origin/main` the same way, leaving out `uv.lock` and `pyproject.toml`, and uploads them. `-Ref <branch>` deploys another branch. It works from any folder of the clone, and deletes its ZIP afterwards.

If Windows answers that running scripts is disabled on this system, run it this way instead. It allows this one run only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_azure.ps1 -App voc-demo-20261030
```

## Removing it

```powershell
az group delete --name voc-demo-rg -o none
```

This deletes the app, the plan and everything in the group.
