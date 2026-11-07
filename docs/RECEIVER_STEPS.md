# The receiver's deploy and its live check: the owner's steps

Spec 004, J9 and J13. Owner decisions, 6 and 7 November. This page keeps what each thing is, the exact values to
type, the click-by-click steps as first done on 7 November, the live check and its clean-up, and what to do if the
signed message gets no answer.

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

## Click by click, the first setup

Done once, by the owner, in the Azure portal, on GitHub and on the laptop, first on 7 November 2026. Five values
are marked **Record**: `<storage account>`, `<key vault>`, `<function app>`, `<default domain>` and
`<deploy client ID>`. Keep them in a private note, never in this repo or a chat, and hide them in any screenshot
shared for help. Use one region for every resource.

### Step 1 of 17: the resource group

1. In the portal's search bar, **Resource groups**, then **+ Create**.
2. Name `voc-receiver-rg`, and a region.
3. **Review + create**, then **Create**.

### Step 2 of 17: the storage account

1. **Storage accounts**, **+ Create**, resource group `voc-receiver-rg`.
2. Name `<storage account>`: lowercase letters and digits, 3 to 24 characters, unique across Azure. **Record** it.
3. Performance Standard, redundancy LRS, the other tabs as they are. **Review + create**, **Create**, **Go to
   resource**.
4. **Data storage**, **Queues**: add `june-events` and `june-events-poison`.
5. **Data storage**, **Tables**: add `juneevents`.

### Step 3 of 17: the Key Vault

1. **Key vaults**, **+ Create**, resource group `voc-receiver-rg`, pricing tier Standard, purge protection disabled,
   so the vault can be deleted for good later. The trade-off: a deleted secret can then be purged at once, before
   its 90 days in the recycle bin.
2. Name `<key vault>`, for example `voc-june-kv`, unique across Azure. **Record** it.
3. **Access configuration**: permission model **Azure role-based access control**.
4. **Review + create**, **Create**, **Go to resource**.
5. **Access control (IAM)**, **+ Add**, **Add role assignment**: **Key Vault Secrets Officer** for your own account,
   so you can add secrets. It can take a few minutes to work.
   Remove it once the Databricks phase has added its secrets.

### Step 4 of 17: the three secrets

1. Open **Cloud Shell** (`>_` at the top right), **Bash**, and **No storage account required** if asked.
2. In the vault, **Objects**, **Secrets**, **+ Generate/Import**, upload option **Manual**, no dates:
   - `voc-basic-user`, with one line printed by `openssl rand -hex 8` in Cloud Shell, never the tests' user name
   - `voc-basic-password`, with one line printed by `openssl rand -hex 32`
   - `voc-hmac-secret`, with a second, new line from `openssl rand -hex 32`
3. Close Cloud Shell. Clear the clipboard and its history (Windows key and V, **Clear all**). The values stay only
   in the vault.

### Step 5 of 17: the Function app

1. **Function App**, **+ Create**, **Flex Consumption**, **Select**.
2. **Basics**: resource group `voc-receiver-rg`, name `<function app>` (**Record** it), runtime stack Python 3.12,
   instance size 512 MB, zone redundancy off.
3. **Storage**: the storage account of step 2, with diagnostic settings **Configure later**.
4. **Azure OpenAI**: unticked. **Networking** and **Durable Functions**: as they are.
5. **Monitoring**: **Enable Application Insights:** No.
6. **Deployment**: **Continuous deployment:** Disable. The repo's own workflow deploys, and this would add another.
7. **Authentication**: for both host storage and deployment storage, **Managed identity**, and below them
   **System-assigned managed identity**, not **Secrets**. With Secrets the storage account's key sits in the app's
   settings, which the deploy identity of step 8 can read through Website Contributor. The portal then gives the app
   Storage Blob Data Owner on the account and Storage Blob Data Contributor on its package container.
8. **Review + create**, **Create**, **Go to resource**. On **Overview**, **Record** the **Default domain** as
   `<default domain>`. It ends in `.azurewebsites.net` and can be longer than the app's name.
9. **Settings**, **Scale and concurrency**: **On demand maximum instance count** `1`.
   Under **Concurrency per instance**, for **HTTP**, **Assign manually** and `4`. **Save**. Python's default is one
   call at a time, and with one instance the second of two calls in a row got no answer (live test, 7 November).
10. **Settings**, **Identity**: **System assigned** is **On**.

### Step 6 of 17: the Function's five roles

The app signs in to its storage and its vault as its own identity. Add each role with **Access control (IAM)**,
**+ Add**, **Add role assignment**, the role, **Next**, **Managed identity**, **+ Select members**, **Function
App**, your app, **Select**, then **Review + assign** twice.

1. On the storage account: **Storage Queue Data Contributor**, then **Storage Table Data Contributor**.
2. On the Key Vault: **Key Vault Secrets User**. Not **Key Vault Certificate User**, which sits next to it in the
   list and cannot read the secrets.
3. Check on the app, **Settings**, **Identity**, **Azure role assignments**. It lists five roles:
   - Storage Blob Data Owner and Storage Blob Data Contributor, from step 5
   - Storage Queue Data Contributor
   - Storage Table Data Contributor
   - Key Vault Secrets User

   The storage account's own list can be slow to show them.

### Step 7 of 17: the six app settings

On the app, **Environment variables**, **App settings**, **+ Add** for each row, then **Apply** and **Confirm**.
Leave the portal's own settings as they are. `VOC_STORAGE__` has two underscores.

| Name | Value |
|---|---|
| `VOC_BASIC_USER` | `@Microsoft.KeyVault(VaultName=<key vault>;SecretName=voc-basic-user)` |
| `VOC_BASIC_PASSWORD` | `@Microsoft.KeyVault(VaultName=<key vault>;SecretName=voc-basic-password)` |
| `VOC_HMAC_SECRET` | `@Microsoft.KeyVault(VaultName=<key vault>;SecretName=voc-hmac-secret)` |
| `VOC_JOB_A_JOB_ID` | `1` |
| `VOC_STORAGE__queueServiceUri` | `https://<storage account>.queue.core.windows.net` |
| `VOC_STORAGE__tableServiceUri` | `https://<storage account>.table.core.windows.net` |

After a minute, **Refresh**. Each Key Vault row shows a green tick under **Source**. A red cross means a typo, or
the role of step 6 is not active yet.

### Step 8 of 17: the deploy identity and its trust

1. **Managed Identities**, **+ Create**, resource group `voc-receiver-rg`, name `voc-receiver-deploy`. **Review +
   create**, **Create**, **Go to resource**.
2. **Record** its **Client ID** as `<deploy client ID>`. It is in the right column of **Overview**'s
   **Essentials**, or `clientId` in **JSON View**. Not the Object (principal) ID.
3. **Settings**, **Federated credentials**, **+ Add Credential**, scenario **Other issuer**, with the values in "The
   federated credential's values" above, and the name `receiver-deploy-env`.

### Step 9 of 17: the deploy identity's one role

On the Function app, **Access control (IAM)**, **+ Add**, **Add role assignment**, **Website Contributor**,
**Next**, **Managed identity**, **+ Select members**, then in the panel **User-assigned managed identity**,
`voc-receiver-deploy`, **Select**, and **Review + assign** twice. Nothing on the resource group.

### Step 10 of 17: the GitHub environment

1. The repo's **Settings**, **Environments**, **New environment**, `receiver-deploy`, **Configure environment**.
2. **Deployment branches and tags**: **Selected branches and tags**, with a rule for the branch `main`. No
   required reviewer.
3. Under **Environment secrets**, not the repo's secrets, add:
   - `RECEIVER_AZURE_CLIENT_ID` with `<deploy client ID>`
   - `RECEIVER_APP_NAME` with `<function app>`
   - `RECEIVER_RESOURCE_GROUP` with `voc-receiver-rg`
   - `RECEIVER_URL` with `https://<default domain>`, with no `/` at the end
4. Check that the repo secrets `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` are listed.

### Step 11 of 17: the deploy

**Actions**, **Deploy the receiver**, **Run workflow**, branch `main`. It shows **Queued** at first, and on 7
November it took 3 minutes. It passes when the job has a green tick and every step a ticked circle. A step with a
slashed circle was skipped (see "Before the first deploy"). On a red cross, tell Claude the failed step's name and
its last line, which holds fixed words only.

### Step 12 of 17: the laptop's copy

In this repo's folder, `git switch main`, then `git pull`.

### Step 13 of 17: the live check

Steps 1 to 3 of "The live check, on the laptop" below. To copy the secret: the vault, **Objects**, **Secrets**,
`voc-hmac-secret`, its current version, **Show Secret Value**, the copy icon at the end of the box, then **Hide
Secret Value**.

### Step 14 of 17: read the live check

It passes on `badly signed: HTTP 401`, `signed: HTTP 202` and `verdict: PASS` with its key. On `signed: HTTP 0`,
see "If the signed message gets no answer" below.

### Step 15 of 17: the stored rows

Steps 4 and 5 of "Check that it was stored" below. Both rows, `event` and `result`, have the printed key as their
RowKey. The `result` row holds `job_a_run_id` 1 and `result_state` `NOT_STARTED`.

### Step 16 of 17: the failure queue

`june-events-poison` is empty (step 6 below).

### Step 17 of 17: the clean-up

Delete both rows (step 7 below). The table is then empty.

## The live check, on the laptop

1. Copy the HMAC secret from the Key Vault page. Windows keeps a clipboard history (Windows key and V). After the
   check, clear it: Settings, System, Clipboard, Clear.
2. In PowerShell, in this repo's folder, on an up-to-date `main`:
   `uv run --locked --native-tls python scripts/receiver_live_check.py https://<default domain>`
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

## If the signed message gets no answer

`signed: HTTP 0` means no answer within 30 seconds. Test calls in a row from Cloud Shell, which is outside the
laptop and needs no secret:

```
for i in 1 2 3; do curl -s -o /dev/null -m 40 --data '' -w "call $i: HTTP %{http_code} in %{time_total}s\n" https://<default domain>/api/result; done
```

Each call should print `HTTP 401` within a few seconds. `HTTP 000` for a call straight after an answered one is
most likely the app taking one call at a time: set the HTTP concurrency of step 5, item 9.

On 7 November three calls in a row gave 401, then 000 after 40 seconds, then 401. With 5 seconds between them,
the same. After the change, three times 401, the slowest in 2.0 seconds. Why the call was lost is not known (spec,
Known limits).

## Application Insights, for a diagnosis only

The receiver runs without it (J9). To find a fault:

1. On the app, **Application Insights**, **Turn on Application Insights**, **Create new resource**,
   `voc-receiver-insights`, in `voc-receiver-rg` if offered. **Apply**. The app restarts.
2. Run the failing check again. After 5 minutes, open `voc-receiver-insights`, **Logs**. Turn the **Agent** switch
   off and use **KQL mode**. This count shows each instance's life and the calls it took:

   ```
   union traces, performanceCounters, exceptions
   | where timestamp > ago(1h)
   | summarize first_seen = min(timestamp), last_seen = max(timestamp), calls = countif(message startswith "Executing") by inst = substring(cloud_RoleInstance, 0, 8)
   | order by first_seen asc
   ```

   The receiver logs event names, IDs and statuses only. Azure's own lines can name the app, so hide it in what
   you share.
3. Afterwards, on the app, **Environment variables**: delete `APPLICATIONINSIGHTS_CONNECTION_STRING`, and
   `APPLICATIONINSIGHTS_AUTHENTICATION_STRING` if it is there, then **Apply** and **Confirm**. Then open
   `voc-receiver-insights` and **Delete** it.
4. The portal may put the logbook's Log Analytics workspace in a shared default group, as on 7 November. Leave that
   workspace unless nothing else uses it. With the logbook gone it takes no new entries, and the old ones expire
   with the workspace's retention.
