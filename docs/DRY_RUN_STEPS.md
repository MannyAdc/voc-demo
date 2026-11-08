# The dry run: the owner's steps

Spec 004, plan item 9, owner decisions of 6 and 8 November. The dry run runs the whole cloud chain once on synthetic
data with the mock backend: the upload, Job A in Databricks, Databricks' webhook to the Azure receiver, the approval
workflow on GitHub, the owner's approval, Job B, and the result message back to the receiver. It holds no API key
and calls no model. Claude gives the click-by-click steps in the chat at the time, one step at a time, and this page
keeps their order, what each checks, and the clean-up.

## Before the dry run, in this order

1. Pull request 9a is merged: the dry run's CSV, list, pin and mock answers.
2. At the Databricks setup, the owner creates Job A and Job B from `cloud/job_a.yml` and `cloud/job_b.yml`, with
   Job A's trigger paused, the robot's permissions and the receiver's webhook destination.
3. A pull request adds both jobs' IDs in `config/june_cloud.toml`.
4. A last pull request adds the synthetic row to `runs/JUNE_RUNS.md`, with the hashes that
   `python scripts/june_hash.py --dry-run` prints from a clean checkout of `main` after step 3. The row comes last,
   since its code hash covers `config/`.

From step 4 until Job B ends, nothing that changes the frozen code is merged to `main`. Between the approval and Job
B's end, nothing is merged to `main` at all, since Job B refuses a GitHub run made from another commit than the one
it runs.

## The run

5. On the laptop, in the repo's folder: `python scripts/make_dry_run.py --round 1 <a folder outside the repo>`. It
   prints the zip's name, size and SHA-256, which must be the pin's in `config/june_dry_run.toml`.
6. In Databricks, check that the volume's `incoming` folder is empty, then unpause Job A's trigger.
7. Upload the zip to the volume's `incoming` folder. Job A starts on its own.
8. Job A ends green. Its webhook reaches the receiver, which checks the run with Databricks and starts the approval
   workflow on GitHub, named for Job A's run.
9. The workflow's first job prints the figures: 8 complaints. Approve `june-run` on GitHub.
10. The workflow starts Job B. Job B checks the approval and Job A's run again, marks both used, and labels the 8
    complaints with the mock answers: 7 accepted and 1 quarantined. Its results folder holds only `DRY_RUN.txt`.
11. The workflow posts the result message. In the receiver's storage account, the `juneevents` table holds a
    `result` row for the workflow's run with `result_state` `SUCCESS`, and `june-events-poison` is empty.
12. Pause Job A's trigger again.

If a step fails, tell Claude the step and its fixed text or status. Refusals hold fixed text and IDs only.

## The clean-up, required (owner decision, 8 November)

13. Delete the dry run's zip from the volume's `incoming` folder and its CSV from the volume's `june` folder.
14. Drop every table in the `voc_june` schema, so the June staging table holds no synthetic row tagged as June
    beside the real ones. The real run builds them again.
15. Keep the receiver's `result` row, the used markers and the results folder's `DRY_RUN.txt`, as the dry run's
    record. They hold IDs, states and fixed text only.

The real run's last step checks that this clean-up was done.

## A re-run

A re-run with no code change uses the same round, after a fresh workflow run and a fresh approval. A re-run after a
code fix is a new round: Claude adds the round's synthetic CSV with new `SYN-` IDs, and `scripts/make_dry_run.py
--round <n> --repo` writes its list, pin and mock answers. A list has one first row, and the June staging table
never changes a row it has built, so a new round also needs its own row and, before it, the clean-up of step 14.
