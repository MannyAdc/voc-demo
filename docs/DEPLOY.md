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

## Redeploying after a change

One line, after `az login`, from the repo folder:

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
