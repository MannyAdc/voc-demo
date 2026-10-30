# Deploying the public copy to Azure App Service

The public copy (spec 002, rule A13) is the dashboard with the committed results files only. It answers only to its own Azure host name, never reads the local staged table, never serves complaint text or the consumer's own choice, and stores no review. So nothing in it is private: it is the same data as the public repo.

The owner runs every command here, in their own PowerShell, after `az login`. Claude creates no account and holds no Azure credential.

## Facts checked on Microsoft's pages (30 October 2026)

- App Service pricing for Linux: the Free (F1) tier is "Shared (60 CPU minutes / day)", with 1 GB RAM and 1 GB storage. The page does not say whether F1 runs Python on Linux, so the first command may need the Basic (B1) tier instead, which the free account's credit covers. ([App Service pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/))
- A ZIP deploy runs the build, including `pip install -r requirements.txt`, only when `SCM_DO_BUILD_DURING_DEPLOYMENT` is `true`. For Python 3.13 and earlier, a FastAPI app needs a startup command. ([Python quickstart](https://learn.microsoft.com/en-us/azure/app-service/quickstart-python), updated 27 July 2026)
- `WEBSITE_HOSTNAME` is set by App Service: "Primary host name for the app". ([App settings reference](https://learn.microsoft.com/en-us/azure/app-service/reference-app-settings), updated 10 September 2026)

## What is deployed

- A ZIP of the committed files on `main`, made with `git archive`, so nothing git ignores (data, `.env`, the deny list) can be in it.
- `requirements.txt`, the runtime packages pinned from `uv.lock`, made with `uv export --frozen --no-default-groups --no-hashes --no-emit-project --format requirements-txt`. A test checks it pins every runtime dependency and no test or Databricks package.
- The startup command `python -m uvicorn voc.public:app --host 0.0.0.0 --port 8000 --app-dir src`.

## The commands

Pick an app name that nobody else uses, with no personal name in it, for example `voc-demo-` and four digits. It becomes `https://<app name>.azurewebsites.net`.

```powershell
cd C:\Users\x13yr\Desktop\dev\voc-demo
git switch main
git pull
$app = "voc-demo-1234"   # change the digits
$rg = "voc-demo-rg"
az group create --name $rg --location australiaeast
az appservice plan create --name voc-demo-plan --resource-group $rg --sku F1 --is-linux
az webapp create --name $app --resource-group $rg --plan voc-demo-plan --runtime "PYTHON:3.13"
az webapp config appsettings set --name $app --resource-group $rg --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true
az webapp config set --name $app --resource-group $rg --startup-file "python -m uvicorn voc.public:app --host 0.0.0.0 --port 8000 --app-dir src"
az webapp log config --name $app --resource-group $rg --docker-container-logging filesystem
git archive --format=zip -o "$env:TEMP\voc-site.zip" main
az webapp deploy --name $app --resource-group $rg --src-path "$env:TEMP\voc-site.zip" --type zip
```

Then open `https://<app name>.azurewebsites.net`. The request log (rule A9) is in the log stream:

```powershell
az webapp log tail --name $app --resource-group $rg
```

and the counters are at `https://<app name>.azurewebsites.net/api/health`.

## If a step fails

- `az appservice plan create` refuses F1 for Linux: run it again with `--sku B1`. That costs money, which the free account's credit covers. Delete the group afterwards to stop it.
- `az webapp create` refuses the runtime: list the runtimes with `az webapp list-runtimes --os-type linux` and pick the closest Python 3.13 or later.

## Removing it

```powershell
az group delete --name voc-demo-rg
```

This deletes the app, the plan and everything in the group.
