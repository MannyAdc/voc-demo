<#
Redeploy the public copy of the dashboard to Azure App Service (spec 002, A13, docs/DEPLOY.md).

Run by the owner, in their own PowerShell, after `az login` and the one-time setup in docs/DEPLOY.md:

    .\scripts\deploy_azure.ps1 -App voc-demo-20261030

It packs the committed files of a branch on GitHub (main by default) into a ZIP with `git archive`, so nothing
git ignores can be in it, and leaves out uv.lock and pyproject.toml, so Azure builds from requirements.txt only.
Then it uploads the ZIP. It holds no secret and logs in to nothing: it uses the owner's `az login`.
#>
param(
    [Parameter(Mandatory = $true)][string]$App,
    [string]$ResourceGroup = "voc-demo-rg",
    [string]$Ref = "main"
)
$ErrorActionPreference = "Stop"

git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed, so nothing was deployed" }
$zip = Join-Path $env:TEMP "voc-site.zip"
git archive --format=zip -o $zip "origin/$Ref" -- . ":!uv.lock" ":!pyproject.toml"
if ($LASTEXITCODE -ne 0) { throw "git archive failed, so nothing was deployed" }
az webapp deploy --name $App --resource-group $ResourceGroup --src-path $zip --type zip
if ($LASTEXITCODE -ne 0) { throw "az webapp deploy failed" }
Write-Output "Deployed origin/$Ref to https://$App.azurewebsites.net"
