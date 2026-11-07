# The receiver's deploy and its live check: the owner's steps

Spec 004, J9 and J13. Owner decisions, 6 and 7 November. Claude gives the full click-by-click checklist in the chat
when the pull requests are merged. This page keeps what each thing is, the exact values to type, and the live
check's clean-up.

## What you create, and for how long

| Name | Where | What it is for | Lifetime |
|---|---|---|---|
| `voc-receiver-rg` | Azure, Resource groups | the receiver's own group, apart from the dashboard's `voc-demo-rg` | as long as the receiver |
| `voc-receiver-deploy` | Azure, Managed Identities, in `voc-receiver-rg` | the identity the receiver's deploy signs in as | as long as the receiver |
| its federated credential | on that identity | trusts only the GitHub environment `receiver-deploy` (values below) | as long as the identity |
| Website Contributor on the Function app | the Function app's Access control | lets that identity deploy, and also change the app's settings and restart it | as long as the identity |
| `receiver-deploy` | GitHub, Settings, Environments | the environment the deploy runs in, limited to the `main` branch | as long as the receiver |
| `RECEIVER_AZURE_CLIENT_ID` | the `receiver-deploy` environment's secrets | the identity's client ID | as long as the identity |
| `RECEIVER_APP_NAME` | the `receiver-deploy` environment's secrets | the Function app's name | as long as the receiver |
| `RECEIVER_RESOURCE_GROUP` | the `receiver-deploy` environment's secrets | `voc-receiver-rg` | as long as the receiver |
| `RECEIVER_URL` | the `receiver-deploy` environment's secrets | the receiver's address, `https://` and the host, with no `/` at the end | as long as the receiver |

The repo secrets `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` already exist for the dashboard, and the deploy uses
them too.

## The federated credential's values

Choose "Other issuer", not the GitHub scenario, since this repo's tokens name the account and the repo by number.
The two numbers are the account's and the repo's public IDs, read from GitHub's API on 7 November.

- Issuer: `https://token.actions.githubusercontent.com`
- Subject: `repo:MannyAdc@84450984/voc-demo@1435727562:environment:receiver-deploy`
- Audience: `api://AzureADTokenExchange`

"Main only" comes from the environment's branch rule in GitHub, not from the subject.

## Before the first deploy

The deploy's check needs the receiver's own settings to load. These must hold a value: `VOC_BASIC_USER`,
`VOC_BASIC_PASSWORD` and `VOC_HMAC_SECRET`, as Key Vault references that resolve, and `VOC_JOB_A_JOB_ID`, a whole
number. Until Job A exists, `1`. The Databricks and GitHub settings may stay unset until the Databricks phase.

A deploy run that ends green with its later steps skipped found `main` moved on, and deployed nothing. Start a new
run.

## The live check, on the laptop

1. Copy the HMAC secret from the Key Vault page. Windows keeps a clipboard history (Windows key and V). After the
   check, clear it: Settings, System, Clipboard, Clear.
2. In PowerShell, in this repo's folder, on an up-to-date `main`:
   `uv run --locked --native-tls python scripts/receiver_live_check.py https://<the receiver's host>`
   Paste the secret only at its hidden prompt.
3. It passes when it prints `badly signed: HTTP 401`, `signed: HTTP 202` and `verdict: PASS`, with a key such as
   `1:1793000000`. Paste the printed lines only to Claude, not the command, which holds the receiver's host.

## Check that it was stored, then clean up, in the Azure portal

4. First wait a minute or two, since the queue function can start slowly. Then open the receiver's storage account,
   Storage browser, Tables, `juneevents`. If the portal says you have no access to the data, give yourself the
   Storage Table Data Contributor and Storage Queue Data Contributor roles on the storage account, and remove them
   after the clean-up.
5. Find the row with PartitionKey `result` and RowKey the printed key. It is the proof the receiver stored the
   message. Tell Claude whether it is there.
6. If it is not there after five minutes, open Queues, `june-events-poison`. A message there means the queue
   function failed. Tell Claude, then delete that message.
7. Delete the `result` row, and the row with PartitionKey `event` and the same RowKey. Nothing else uses them.
