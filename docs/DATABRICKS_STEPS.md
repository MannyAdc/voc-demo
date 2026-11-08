# The Databricks setup for the dry run: the owner's steps, click by click

Spec 004, J8, J11, J13 and J16, owner decisions of 8 and 9 November. First done on 9 November 2026. Every step says
where to start, which button to click, and where each value comes from, for a reader who is new to Databricks.
Values in angle brackets, such as `<default domain>`, are private. Keep them in a note on your own computer, never in
this repo or a chat.

What these steps make, and for how long:

| Name | Where | What it is for | Lifetime |
|---|---|---|---|
| `voc_results` | Catalog, `workspace`, `default` | Job B's results folder | until the real June results are copied |
| `voc-receiver` | Settings, Notifications | how Databricks tells the Azure receiver that Job A succeeded | as long as the receiver |
| `voc-june-job-a` | Jobs & Pipelines | Job A: unpacks and checks the upload, calls no model | until after the real June run |
| `voc-june-job-b` | Jobs & Pipelines | Job B: labels the sample once the owner approves | until after the real June run |
| the robot's rights | each job's permissions | `voc-june-runner` may view Job A's runs and start Job B, nothing else | as long as the jobs |

### Step 1.1: look first

1. In Databricks, in the left menu, click **Jobs & Pipelines**. Note the jobs listed. On 9 November only
   `voc-june-spike` was there. It is paused and watches `spike_incoming`, a folder of its own, so it can stay.
2. In the left menu, click **Catalog**, then `workspace`, then `default`. Note the volumes. On 9 November only
   `voc_raw` was there.

### Step 1.2: the volume `voc_results`

1. In **Catalog**, open `workspace`, then `default`.
2. Click **Create** at the top right, then **Volume**.
3. **Volume name:** `voc_results`. **Volume type:** **Managed volume**. Leave the rest as it is.
4. Click **Create**. `default` now lists `voc_raw` and `voc_results`.

### Step 1.3: the webhook destination `voc-receiver`

1. In Databricks, click your initial or name at the **top right**, then **Settings**.
2. Under **Workspace admin**, click **Notifications**. Next to **Notification destinations**, click **Manage**, then
   **Add destination**.
3. **Type:** **Webhook**. **Name:** `voc-receiver`.
4. **Authentication mode** shows **No Auth**. Change it to the username and password option. Only then do the
   **Username** and **Password** fields appear. Never leave it on **No Auth**.
5. **URL:** `https://<default domain>/api/databricks`. The default domain is in the Azure portal: open the Function
   app, and on its **Overview** page read **Default domain**. It ends in `.azurewebsites.net`.
6. **Username:** in the Azure portal, open **Key vaults**, click the vault's **name**, `voc-june-kv` (not its
   checkbox, and never **Delete**). In the vault's left menu, open **Objects**, then **Secrets**. Click
   `voc-basic-user`, then the line under **Current version**. Click **Show Secret Value**, then the copy icon at the
   right end of the value's box, then **Hide Secret Value**. Paste it into **Username**.
7. **Password:** the same, with `voc-basic-password`.
8. Click **Create**. Then clear the clipboard: press the Windows key and V together, then **Clear all**.

On 9 November the form had no test button. Job A's first run tests the destination for real.

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
3. In Notepad, delete the three lines `webhook_notifications:`, `on_success:` and
   `- id: the receiver's notification destination ID, set by the owner`. Step 1.6 connects the webhook by clicking.
4. In Databricks, in the left menu, click **Jobs & Pipelines**, then the blue **Create** button at the top right,
   then **Job**.
5. On the new job page, click the **⋮** (three vertical dots) just left of the grey **Run now** button, then the
   item with **YAML** in its name.
6. Click inside the editor, press Ctrl+A, and paste the edited text from Notepad. Click **Save**.
7. Check the page: the name `voc-june-job-a`, three tasks in a row, `unpack`, then `dbt`, then `job_a`.
8. On the right side, find **Job ID** and write it in Notepad: `Job A ID: <number>`.

### Step 1.6: connect Job A to the receiver

1. On Job A's page, on the right side, scroll down to **Job notifications** and click **Edit notifications**.
2. Click **Add notification**. In the new row's dropdown, choose `voc-receiver`. Tick **Success** only.
3. Click **Save**. The right side now shows `voc-receiver` with **On success**.
4. On the right side, scroll up to **Schedules & Triggers**. It shows **File arrival**, **Paused**, and the folder
   `/Volumes/workspace/default/voc_raw/incoming/`. Never click the ▶ next to it until the dry run's step says so,
   since that unpauses it.

### Step 1.7: Job B, `voc-june-job-b`

1. In your browser, open `https://github.com/MannyAdc/voc-demo/blob/main/cloud/job_b.yml` and click **Copy raw
   file**. Job B needs no edit.
2. In Databricks, click **Jobs & Pipelines**, then **Create**, then **Job**.
3. Click the **⋮** just left of the grey **Run now** button, then the **YAML** item. Click inside the editor, press
   Ctrl+A, then Ctrl+V. Click **Save**.
4. Check the page: the name `voc-june-job-b`, one task, `job_b`, under **Job parameters** `job_a_run_id` and
   `github_run_id`, and under **Schedules & Triggers** no trigger.
5. On the right side, find **Job ID** and write it in Notepad: `Job B ID: <number>`.

### Step 1.8: the robot's two rights

1. In **Jobs & Pipelines**, click `voc-june-job-a`. Open its permissions: on the right side near the top, under
   **Permissions**, or in the **⋮** menu just left of **Run now**. Click **Edit permissions**.
2. In the search field, type `voc-june-runner` and click it. In the permission dropdown next to it, choose
   **Can View**. Click **Add**, then **Save**.
3. In **Jobs & Pipelines**, click `voc-june-job-b`, and do the same with **Can Manage Run**.
4. Never give the robot **Can Manage** or **Is Owner**. They give far more than it needs.

The two job IDs then go into `config/june_cloud.toml`, in a pull request of their own, and the receiver's
`VOC_JOB_A_JOB_ID` setting takes Job A's ID. The steps for the robot's secret, the GitHub token, the GitHub
environments and the receiver's settings are added here as they are done.
