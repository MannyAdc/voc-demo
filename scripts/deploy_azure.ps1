<#
Redeploy the public copy of the dashboard to Azure App Service (spec 002, A13, docs/DEPLOY.md).

Run by the owner, in their own PowerShell, after `az login` and the one-time setup in docs/DEPLOY.md:

    .\scripts\deploy_azure.ps1 -App voc-demo-20261030

It packs the committed files of a branch on GitHub (main by default) into a ZIP with `git archive`, so nothing
git ignores can be in it, and leaves out uv.lock and pyproject.toml, so Azure builds from requirements.txt only.
Then it uploads the ZIP, with `-o none`, so no resource ID (which holds the subscription ID) is printed.
It holds no secret and logs in to nothing: it uses the owner's `az login`.

It works from any folder: it packs the repo it sits in, then goes back to the folder it started in. Every step
checks its own exit code and stops the script, and the ZIP is deleted even when a step fails.
#>
param(
    [Parameter(Mandatory = $true)][string]$App,
    [string]$ResourceGroup = "voc-demo-rg",
    [string]$Ref = "main"
)
$here = Get-Location
Set-Location (Join-Path $PSScriptRoot "..") -ErrorAction Stop
$zip = Join-Path $env:TEMP "voc-site.zip"
try {
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed, so nothing was deployed" }
    # Review of #56: the ZIP names its commit in BUILD_COMMIT, which /api/health reports.
    $commit = git rev-parse "origin/$Ref"
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse failed, so nothing was deployed" }
    git archive --format=zip -o $zip --add-virtual-file="BUILD_COMMIT:$commit" "origin/$Ref" -- . ":!uv.lock" ":!pyproject.toml"
    if ($LASTEXITCODE -ne 0) { throw "git archive failed, so nothing was deployed" }
    az webapp deploy --name $App --resource-group $ResourceGroup --src-path $zip --type zip -o none
    if ($LASTEXITCODE -ne 0) { throw "az webapp deploy failed" }
    Write-Output "Deployed origin/$Ref to https://$App.azurewebsites.net"
} finally {
    Remove-Item $zip -ErrorAction SilentlyContinue
    Set-Location $here
}
