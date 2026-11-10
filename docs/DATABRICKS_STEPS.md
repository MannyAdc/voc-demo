# The cloud setup for the dry run: the owner's steps, click by click

Spec 004, J8, J10, J11, J13 and J16, owner decisions of 8 and 9 November. First done on 9 November 2026. Every step
says where to start, which button to click, and where each value comes from, for a reader who is new to Databricks,
GitHub and Azure. Values in angle brackets, such as `<default domain>`, are private. Keep them in a note on your own
computer, never in this repo or a chat.

Three words used below:

- A catalog is the top folder of Databricks' data. This workspace has one, `workspace`.
- A schema (a folder that holds tables and volumes) sits inside a catalog. In Databricks a schema is a folder, not
  a table's list of columns.
- A volume (a folder for files, such as a zip) sits inside a schema.

What these steps make, and for how long:

| Name | Where | What it is for | Lifetime |
|---|---|---|---|
| `voc_results` | Databricks, Catalog, `workspace` → `voc_results` | Job B's results, in a schema of its own | until the real June results are copied |
| `voc-receiver` | Databricks, Settings, Notifications | how Databricks tells the Azure receiver that Job A succeeded | as long as the receiver |
| `voc-june-job-a` | Databricks, Jobs & Pipelines | Job A: unpacks and checks the upload, calls no model | until after the real June run |
| `voc-june-job-b` | Databricks, Jobs & Pipelines | Job B: labels the sample once the owner approves | until after the real June run |
| the robot's rights | each job's permissions | `voc-june-runner` may look at Job A's runs, and start, look at and cancel Job B's | as long as the jobs |
| `june-figures`, `june-run` | GitHub, Settings, Environments | the approval workflow's two jobs, the second waiting for the owner's approval | until after the real June run |
| the robot's secret | Databricks, Settings | the robot's sign-in, `jobs` scope only | 30 days |
| `voc-receiver-dispatch` | GitHub, your Settings | a token that lets the receiver start the approval workflow | 30 days |

## Copying a secret safely

Every secret below is copied with a **copy icon**, which works without showing the value on screen. Two boxes show a
new secret once, in steps 2.4 and 2.5: while they are open, never take a screenshot or share your screen. After the last paste of a step, clear the clipboard: press the Windows key and V together, then **Clear all**.
If that opens nothing because clipboard history is off, copy any harmless word instead, so the secret leaves the
clipboard.

## Step 1: Databricks

### Step 1.1: look first

1. In Databricks, in the left menu, click **Jobs & Pipelines**. Note the jobs listed. On 9 November only
   `voc-june-spike` was there. It is paused and watches `spike_incoming`, a folder of its own, so it can stay.
2. In the left menu, click **Catalog**, then `workspace`, then `default`. Note the volumes. On 9 November only
   `voc_raw` was there. It holds the raw uploads, with real complaint text.

### Step 1.2: the schema and volume `voc_results`

The results get a schema of their own, apart from `default`, which holds the raw uploads. The read-only account that
copies the results later gets the right to open only this schema, so one wrong grant inside `default` can never
let it reach the raw uploads (J13).

1. In **Catalog**, click `workspace` (its name only, not `default` under it). Click **Create schema** at the top
   right, or **Create**, then **Schema**. **Schema name:** `voc_results`. Leave the rest as it is. Click **Create**.
2. Click the new schema `voc_results`. Click **Create** at the top right, then **Volume**. **Volume name:**
   `voc_results`. **Volume type:** **Managed volume**. Click **Create**.
3. Check: `workspace` → `voc_results` holds the volume `voc_results`, and `workspace` → `default` holds only
   `voc_raw`.

On 9 November this volume was first made in `default` by mistake, then moved here: the owner made the schema and the
new volume, then opened `workspace` → `default` → `voc_results` (the empty one), clicked the ⋮ at its top right,
**Delete**, typed its name and confirmed. Never delete `voc_raw`.

### Step 1.3: the webhook destination `voc-receiver`

1. In Databricks, click your initial or name at the **top right**, then **Settings**.
2. Under **Workspace admin**, click **Notifications**. Next to **Notification destinations**, click **Manage**, then
   **Add destination**.
3. **Type:** **Webhook**. **Name:** `voc-receiver`.
4. **Authentication mode** shows **No Auth**. Change it to **Basic Auth**. Only then do the **Username** and
   **Password** fields appear. Never leave it on **No Auth**.
5. **URL:** `https://<default domain>/api/databricks`. The default domain is in the Azure portal: open the Function
   app, and on its **Overview** page read **Default domain**. It ends in `.azurewebsites.net`.
6. **Username:** in the Azure portal, open **Key vaults** and click the vault's **name**, `voc-june-kv` (not its
   checkbox, and never **Delete**). In the vault's left menu, open **Objects**, then **Secrets**. Click
   `voc-basic-user`, then the line under **Current version**, then the copy icon at the right end of the value's box.
   Paste it into **Username**.
7. **Password:** the same, with `voc-basic-password`.
8. Click **Create**. Clear the clipboard, as above.

On 9 November the form had no test button. The dry run's Job A run is the destination's test.

### Step 1.4: the SQL warehouse's ID

1. In the left menu, click **SQL Warehouses**. If it is not there, click **Compute**, then the **SQL warehouses**
   tab.
2. Click the warehouse's **name**, **Serverless Starter Warehouse**.
3. Its ID is on its page, labelled **ID**, or in the browser's address bar, the text after `warehouses/`. It is
   about 16 letters and digits.
4. In Notepad, write one line: `warehouse ID: <the ID>`.

### Step 1.5: Job A, `voc-june-job-a`

1. In your browser, open `https://github.com/MannyAdc/voc-demo/blob/main/cloud/job_a.yml`. Just above the file's
   text, on the right, click the button with two overlapping squares, **Copy raw file**. Paste it into Notepad.
2. In Notepad, on the line `warehouse_id: the SQL warehouse's ID, set by the owner`, replace the words after
   `warehouse_id: ` with the warehouse ID. Keep the spaces at the start of the line.
3. In Notepad, delete these three lines: `webhook_notifications:`, `on_success:` and
   `- id: the receiver's notification destination ID, set by the owner`. Step 1.6 connects the webhook by clicking,
   since the destination's ID is not shown on its page.
4. In Databricks, in the left menu, click **Jobs & Pipelines**, then the blue **Create** button at the top right,
   then **Job**.
5. On the new job page, click the **⋮** (three vertical dots) just left of the grey **Run now** button, then the
   item with **YAML** in its name.
6. Click inside the editor, press Ctrl+A, and paste the edited text from Notepad. Click **Save**.
7. Check the page: the name `voc-june-job-a`, three tasks in a row, `unpack`, then `dbt`, then `job_a`. On the right
   side, **Run as** shows your own account, never `voc-june-runner`.
8. On the right side, find **Job ID** and write it in Notepad: `Job A ID: <number>`.

### Step 1.6: connect Job A to the receiver, and check it against its file

1. On Job A's page, on the right side, scroll down to **Job notifications** and click **Edit notifications**.
2. Click **Add notification**. In the new row's dropdown, choose `voc-receiver`. Tick **Success** only.
3. Click **Save**. The right side now shows `voc-receiver` with **On success**.
4. On the right side, scroll up to **Schedules & Triggers**. It shows **File arrival**, **Paused**, and the folder
   `/Volumes/workspace/default/voc_raw/incoming/`. Never click the ▶ next to it until the dry run's step says so,
   since that unpauses it.
5. Last, compare the live job with its file. Click the ⋮ just left of **Run now**, then the **YAML** item, and
   compare it with `cloud/job_a.yml`. Two places differ by design: `warehouse_id` holds the warehouse's ID, and
   `webhook_notifications` names the destination's ID. The editor also adds or leaves out three defaults, listed in
   step 2.7. It must still say `pause_status: PAUSED`, and hold no
   `email_notifications` block, since the job sends no failure email. Close the editor without saving.

### Step 1.7: Job B, `voc-june-job-b`

1. In your browser, open `https://github.com/MannyAdc/voc-demo/blob/main/cloud/job_b.yml` and click **Copy raw
   file**. Job B needs no edit.
2. In Databricks, click **Jobs & Pipelines**, then **Create**, then **Job**.
3. Click the **⋮** just left of the grey **Run now** button, then the **YAML** item. Click inside the editor, press
   Ctrl+A, then Ctrl+V. Click **Save**.
4. Check the page: the name `voc-june-job-b`, one task, `job_b`, under **Job parameters** `job_a_run_id` and
   `github_run_id`, and under **Schedules & Triggers** no trigger. **Run as** shows your own account, never
   `voc-june-runner`.
5. On the right side, find **Job ID** and write it in Notepad: `Job B ID: <number>`.

### Step 1.8: the robot's two rights

1. In **Jobs & Pipelines**, click `voc-june-job-a`. Open its permissions: on the right side near the top, under
   **Permissions**, or in the **⋮** menu just left of **Run now**. Click **Edit permissions**.
2. In the search field, type `voc-june-runner` and click it. In the permission dropdown next to it, choose
   **Can View**. Click **Add**, then **Save**.
3. In **Jobs & Pipelines**, click `voc-june-job-b`, and do the same with **Can Manage Run**. It lets the robot start
   Job B and look at its runs and their output, which the approval workflow needs. It also lets the robot cancel a
   run, which nothing uses.
4. Never give the robot **Can Manage** or **Is Owner**. They give far more than it needs.

The two job IDs then go into `config/june_cloud.toml`, in a pull request of their own.

### Step 1.9: the reader `voc-results-reader` (spec 004, J13, pull request 6b part 6)

The reader is a second service principal. It can read the results volume `voc_results` and nothing else, and it
is in no job and never in `admins`. Claude's copy script signs in as it, from the laptop, to bring the two results
files into the repo. It lives until the owner removes it after the June run.

1. In Databricks, your initial or name at the top right, **Settings**, **Identity and access**, next to **Service
   principals** **Manage**, then **Add service principal**, **Add new**. Name it `voc-results-reader`. Click
   **Add**. Never add it to a group. Databricks puts every new principal in the workspace's own users group
   (`_workspace_users_workspace_` followed by a number) by itself, so check what that group holds:
   - In **Catalog**, `workspace`, the **Permissions** tab: the group may hold **USE CATALOG**, Databricks' default.
     It only shows that the catalog exists, so leave it.
   - `default`, the **Permissions** tab: on 10 November the group held **USE SCHEMA** and five **CREATE** rights
     there. Tick each of the group's rows, click **Revoke** and confirm, so the list says **No permissions granted
     yet**. The owner's own jobs are not affected, since the owner owns the catalog and the jobs run as the owner.
   - The volume `voc_raw`, the **Permissions** tab, with **Inherited** set to all three levels: it should say no
     permission matches. On 10 November it did, so nobody but the owner can read it.
   - `voc_cfpb` and `voc_june`, the **Permissions** tab: no right for the group. If one is there, stop and tell
     Claude.
2. In the left menu, **Catalog**, click `workspace`, the **Permissions** tab, **Grant**. Principal
   `voc-results-reader`, privilege **USE CATALOG** only. Click **Grant**.
3. In **Catalog**, click `workspace`, then `voc_results`, the **Permissions** tab, **Grant**. Principal
   `voc-results-reader`, privilege **USE SCHEMA** only. Click **Grant**.
4. In `voc_results`, click the volume `voc_results`, the **Permissions** tab, **Grant**. Principal
   `voc-results-reader`, privilege **READ VOLUME** only. Click **Grant**. Grant nothing on `default` or `voc_raw`.
5. Back in **Settings**, **Identity and access**, **Service principals**, `voc-results-reader`, the **Secrets** tab,
   **Generate secret**. **Lifetime:** 30 days. **Scope:** all APIs, which the copy script asks for. This scope is not
   yet tried live: if the check of item 7 says the sign-in was refused, tell Claude. The reader's real rights stay its
   three grants of items 2 to 4. Click **Generate**. A box shows the **Client ID** and the **Secret**.
6. On the laptop, open `.env` in the repo's folder in Notepad and add two lines, `VOC_READER_CLIENT_ID=` followed by
   the Client ID, and `VOC_READER_CLIENT_SECRET=` followed by the Secret. Check that `VOC_DATABRICKS_HOST=` with the
   workspace's bare host is there too. Save, close Notepad, close the Databricks box and clear the clipboard.
7. Tell Claude. Claude runs `uv run --native-tls --locked python scripts/copy_june_results.py --check-reader`,
   which prints only yes or no: the results volume readable, the raw volume refused, the secret scope `voc-june`
   refused, and a verdict. Only a real refusal counts, so a failure never passes.
8. When it passes, back in **Settings**, **Identity and access**, **Service principals**, `voc-results-reader`, the
   **Configurations** tab: untick **Workspace access** and save. Tell Claude, who runs the check again. If it still
   passes, the reader keeps no workspace access, so it cannot make or run notebooks or jobs. If it fails, tick the
   box again and tell Claude (the robot's rule of J13, applied to the reader).

## Step 2: GitHub, Databricks and Azure

### Step 2.1: the GitHub environment `june-figures`

1. Open `https://github.com/MannyAdc/voc-demo/settings/environments`. Click the green **New environment** button.
2. **Name:** `june-figures`. Click **Configure environment**.
3. Under **Deployment branches and tags**, change **No restriction** to **Selected branches and tags**. Click
   **Add deployment branch or tag rule**, leave **Ref type** on **Branch**, type `main`, and click **Add rule**.
4. Leave **Required reviewers** unticked.

### Step 2.2: the GitHub environment `june-run`

1. On the same Environments page, click **New environment**. **Name:** `june-run`. Click **Configure environment**.
2. Tick **Required reviewers**, type `MannyAdc` in the box under it and click the account. Make sure **Prevent
   self-review** is unticked, so the owner can approve a run the receiver started. If the page offers a setting that
   lets administrators bypass the rules, leave it as it is: Job B refuses any run with no approval on record. Click
   **Save protection rules**.
3. Under **Deployment branches and tags**, allow the branch `main` only, as in step 2.1.

### Step 2.3: the addresses and the result secret

1. Copy the Databricks workspace's host from the browser's address bar: the part between `https://` and the next
   `/`. Write it in Notepad as `databricks host: <host>`.
2. In **june-figures**, under **Environment secrets**, click **Add environment secret**: **Name**
   `VOC_DATABRICKS_HOST`, **Value** the host. Click **Add secret**.
3. In **june-run**, add three: `VOC_DATABRICKS_HOST` with the host, `VOC_RECEIVER_URL` with
   `https://<default domain>` (no `/` at the end), and `VOC_RESULT_SECRET` with the copy of `voc-hmac-secret` from
   the Key Vault, taken as in step 1.3, item 6. Clear the clipboard.

### Step 2.4: the robot's secret, pasted six times

Databricks shows the secret once, so keep its box open until all six pastes are done.

1. In Databricks, your initial or name at the top right, **Settings**, **Identity and access**, next to **Service
   principals** **Manage**, then `voc-june-runner`, the **Secrets** tab, **Generate secret**. **Lifetime:** 30 days.
   **Scope:** click **Other APIs**, then **Add scope**, and choose `jobs`. Set its access to **Read + Write**, never
   **Read** alone, which makes the scope `jobs:read`: Databricks refuses a token for `jobs` from it (HTTP 403, round
   1 of the dry run, 9 November), and starting Job B needs write. The robot's real rights stay its two job
   permissions of step 1.8. Click **Generate**. A box shows the **Client ID** and the **Secret**, each with a copy
   button.
2. In GitHub's **june-figures**, add `VOC_DATABRICKS_CLIENT_ID` (the Client ID) and `VOC_DATABRICKS_CLIENT_SECRET`
   (the Secret). Do the same in **june-run**.
3. In the Key Vault, **Objects**, **Secrets**, **+ Generate/Import**, upload option **Manual**, no dates:
   `voc-databricks-client-id` with the Client ID,
   then `voc-databricks-client-secret` with the Secret.
4. Close the Databricks box. Clear the clipboard. **june-figures** lists 3 secrets, **june-run** lists 5.

### Step 2.5: the GitHub Actions token

1. On github.com, your profile picture at the top right, **Settings**, at the bottom of the left menu **Developer
   settings**, then **Personal access tokens**, **Fine-grained tokens**, **Generate new token**.
2. **Token name:** `voc-receiver-dispatch`. **Resource owner:** `MannyAdc`. **Expiration:** 30 days. **Repository
   access:** **Only select repositories**, `MannyAdc/voc-demo`. Under **Repository permissions**, **Actions**:
   **Read and write**. Nothing else. GitHub adds **Metadata: Read-only** by itself, which is fine. Click
   **Generate token**.
3. In the Key Vault, **+ Generate/Import**: `voc-github-token` with the token, using GitHub's copy button. Clear the
   clipboard.

### Step 2.6: the receiver's settings

1. In the Azure portal, the Function app, **Environment variables**, **App settings**.
2. Click `VOC_JOB_A_JOB_ID` and set its value to Job A's ID: `job_a_job_id` in `config/june_cloud.toml`, the same
   number as your Notepad's `Job A ID`. Click **Apply** in its box.
3. Click **+ Add** for each of these four, and **Apply**:
   - `VOC_DATABRICKS_HOST` with the host from Notepad
   - `VOC_DATABRICKS_CLIENT_ID` with `@Microsoft.KeyVault(VaultName=voc-june-kv;SecretName=voc-databricks-client-id)`
   - `VOC_DATABRICKS_CLIENT_SECRET` with `@Microsoft.KeyVault(VaultName=voc-june-kv;SecretName=voc-databricks-client-secret)`
   - `VOC_GITHUB_TOKEN` with `@Microsoft.KeyVault(VaultName=voc-june-kv;SecretName=voc-github-token)`
4. Click **Apply** at the bottom, then **Confirm**. After a minute, **Refresh**. Every Key Vault row shows a green
   tick under **Source**. On 9 November all six did.

### Step 2.7: check the live Job A against its file

Done by the owner on 9 November, as step 1.6, item 5, says. Copy the live job's YAML (the ⋮ just left of **Run now**,
the **YAML** item, Ctrl+A, Ctrl+C, then close without saving) into Notepad and compare it with `cloud/job_a.yml`. On 9
November Claude compared them from a copy the owner saved on the Desktop for the check, deleted after it. Beside the warehouse's ID
and the destination's ID, the editor differed in three defaults, none a problem:

- `max_concurrent_runs` is left out, since 1 is Databricks' default.
- `queue` is on, Databricks' default: a second start waits instead of being dropped, and `unpack` refuses a second
  file anyway.
- `performance_target` is `PERFORMANCE_OPTIMIZED`: the serverless compute starts faster and uses more of Free
  Edition's daily allowance. Job A is small.

The trigger was still paused, and there was no failure email.

### Step 2.8: remove the owner's Key Vault Secrets Officer role

The owner gave themselves Key Vault Secrets Officer on 7 November to add secrets. Once the last ones are in, it goes,
so a stolen sign-in or a wrong click cannot read or change the secrets without adding the role back first, which Azure
logs. The owner stays the owner of everything, and can add it back in two minutes, for example to renew the robot's
secret and the token after 30 days.

1. In the Azure portal, open **Key vaults**, then click the name `voc-june-kv`.
2. In its left menu, click **Access control (IAM)**, then the **Role assignments** tab.
3. Under **Key Vault Secrets Officer**, tick the row with your own account only. Never tick the Function app's row
   under **Key Vault Secrets User**, which the receiver needs.
4. Click **Remove**, then **Yes**. Done on 9 November.
