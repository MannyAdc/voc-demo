# The receiver's deploy and its live check: the owner's steps

Spec 004, J9 and J13. Owner decisions, 6 and 7 November. Claude gives the full click-by-click checklist in the chat
when the pull requests are merged. This page keeps what each thing is, and the live check's clean-up.

## What you create, and for how long

| Name | Where | What it is for | Lifetime |
|---|---|---|---|
| `voc-receiver-deploy` | Azure, Managed Identities | the identity the receiver's deploy signs in as | as long as the receiver |
| its federated credential | on that identity | trusts only the GitHub environment `receiver-deploy` on `main` | as long as the identity |
| Website Contributor on the Function app | the Function app's Access control | lets that identity deploy the receiver, nothing else | as long as the identity |
| `receiver-deploy` | GitHub, Settings, Environments | the environment the deploy runs in, limited to `main` | as long as the receiver |
| `RECEIVER_AZURE_CLIENT_ID` | that environment's secrets | the identity's client ID | as long as the identity |
| `RECEIVER_APP_NAME`, `RECEIVER_RESOURCE_GROUP` | the repo's Actions secrets | the Function app's name and its resource group | as long as the receiver |
| `RECEIVER_URL` | the repo's Actions secrets | the receiver's address, `https://` and the host, with no `/` at the end | as long as the receiver |

The repo secrets `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` already exist for the dashboard, and the deploy uses
them too.

## The live check, on the laptop

1. Copy the HMAC secret from the Key Vault page. Windows keeps a clipboard history (Windows key and V). After the
   check, clear it: Settings, System, Clipboard, Clear.
2. In PowerShell, in this repo's folder, on an up-to-date `main`:
   `uv run --locked --native-tls python scripts/receiver_live_check.py https://<the receiver's host>`
   Paste the secret only at its hidden prompt.
3. It passes when it prints `badly signed: HTTP 401`, `signed: HTTP 202` and `verdict: PASS`, with a key such as
   `1:1793000000`. Paste the lines to Claude. They hold no secret.

## Check that it was stored, then clean up, in the Azure portal

4. The receiver's storage account, Storage browser, Tables, `juneevents`.
5. Find the row with PartitionKey `result` and RowKey the printed key. It is the proof the receiver stored the
   message. Tell Claude whether it is there.
6. Delete that row, and the row with PartitionKey `event` and the same RowKey. Nothing else uses them.
