# Limits

Moved here from the README on 31 October 2026, word for word, except that references to sections now on other pages became links, and, in review, one claim about reviews became a statement of the rule. Back to the [README](../README.md).

## Limits

- The recorded product was chosen by the consumer, not by the CFPB, so some measured "errors" are label noise. TF-IDF learns from those same choices.
- The CFPB says its database "is not a statistical sample of consumers' experiences in the marketplace". The results describe this data only.
- The 10,002 narratives are a 1.5 percent subset with a very different mix. Credit reporting is 618,208 complaints (92 percent of all), but only 463 of them, about 1 in 1,300, have a narrative (`results/profile_july_2026.json`, [docs/DATA.md](DATA.md)).
- The model's training data cutoff is June 2026 ([models overview](https://platform.claude.com/docs/en/about-claude/models/overview), read 29 October 2026). The complaints were received in July 2026, so they cannot be in its training data.
- The CFPB file changes over time, and only the current export can be downloaded. So the July file cannot be fetched again, and a reader cannot re-run the labelling from this repo alone.
- Classifying is not the same as measuring. Prepaid card (28 test complaints) and debt or credit management (19) are too few to judge. Both methods still label them, and they count in the overall score. They were not over-sampled, because the pool has only 134 and 91 of them, and taking more for the test set would leave fewer for TF-IDF to train on. See "Small categories" in [docs/HOW_WE_MEASURE.md](HOW_WE_MEASURE.md) and in [docs/DATA.md](DATA.md).
- The tests prove the code's rules. They do not prove label quality, which the evaluation measures, or how a cloud deployment would be secured.
- One model, one prompt version and one test run. The result says nothing about other months, other data or other industries.
- `voc ledger raise` writes a line to BUILD_LOG.md, and `voc final` needs a clean working tree. So after a raise, that line must be committed or set aside before the scored run.
- Pending improvements:
  - The analyser for error analysis (T018a): a tool-less model call that names one cause from a fixed list for each wrong label.
  - A human spot check of whether quotes support their labels (T014c, the `show` command for the owner).
  - Catching a crash in the middle of the scored run.
- The public copy on Azure App Service (spec 002, A13, and [docs/DEPLOY.md](DEPLOY.md)) serves only what this repo already holds: the results files, with no complaint text, no consumer's choice and no review saving. It needs no login for that reason. A deployment that labels or reviews in the cloud would need more: authentication on the API, keys in a secrets manager, the ledger in a shared database, the recordings in protected storage, and branch protection with required checks.

### Known limits

These come from the threat model in the [spec](../specs/001-core-labelling-pipeline/spec.md). The guards stop honest mistakes, AI mistakes and hostile complaint text, and make any bypass visible in the public history. They are not built to stop a person who deliberately works around them.

- Deleting the ledger or the home-folder test log and starting again resets them, with no trace in git.
- A git-ignored local settings file can turn off the project hooks.
- Shell commands that write files are not seen by the data guard.
- Until branch protection is on, the owner can merge with failing CI.
- A tests-only commit can weaken an existing check. Only the reviewer agent would notice.
- A script that opens the DuckDB file directly skips the `final` guard and the dbt test-row filter.
- The staged DuckDB table under the dbt models still holds the test rows. So the real seal is the `final` command path, its committed log and the CI check on that log. The dbt flag is a second layer.
- A hand run of dbt with a relative project folder bakes a relative path to `splits/test.csv` into the `curated_complaints` view. Querying the view then depends on the folder the reader runs in. `voc dbt` always gives the full path.
- `git commit --no-verify` in the owner's own terminal skips the git hook. Only CI catches it.
- Hooks read command text, so an unusual command form can slip past them.
- On Claude Code versions before 2.1.295, a hook that times out lets the action through. A crash still blocks, through exit code 2.
- The git hook is switched on per clone with `git config core.hooksPath .githooks`. A fresh clone has no test gate until the owner runs it. Claude refuses to commit until then.
- The read guard blocks any shell command with the word `show` unless it starts with `git`, so it also blocks harmless commands such as `echo show`.
- `git cherry-pick`, `git revert` and `git commit-tree` run no pre-commit hook, so they can create a commit the test gate has not checked. Only CI catches it.
- The read guard checks path-like fields and command text. A path built at run time inside a script (for example joined from parts in Python) is not seen.
- The data guard does not check for complaint text copied into notes or docs. The read guard keeps Claude from reading that text in the first place.
- A server error or rate limit that lasts is retried, so up to 9 reservations are charged before 3 failed complaints stop the run. A failed call is charged its full reservation, even when the API billed nothing.
- The scored test run writes its results when it finishes, or when 3 complaints in a row fail. A crash in the middle (Ctrl-C, a ledger lock timeout, a corrupt recording, a ledger overrun that opens during the run) loses the outcomes so far. The log entry stays, so a new run needs a reason. Answers already made stay in the recordings, so a new run replays them at no cost. An overrun already open before the run is refused first.
- The test gate keeps the full pytest output of its last run in the system temp folder, one folder per checkout. A failing test can print a fake key it built, and that stays there until the next run. No scan covers that folder.
- `voc audit` needs the recorded answers, which stay outside the repo. So only the owner's machine can run it, not a reader of the repo. A recording rewritten together with matching positions in the results file would pass it, because recordings carry no signature.
- `voc sample` records the pinned file's SHA-256 in `splits/manifest.json`, but it does not check that the staged rows came from that file. `voc load` checks the file against its pin before loading, and the staged table does not keep the file's hash.
- No CI check yet stops `splits/` from changing compared with `main`. `voc sample` refuses to run while any list file is there, but a deleted folder can be rebuilt. With the same code and seed, the rebuilt lists are the same.
- The merge verdict's trial merge (`--test-merge`) runs the tests with this checkout's installed packages, so a dependency change in a pull request is not covered.
- The trial merge runs a pull request's tests on this machine. So it is for this repo's own pull requests only, and it refuses a pull request from a fork.
- The Databricks target checks the seed's complaint IDs, not its text. A synthetic ID with real complaint text copied into the seed would pass. The seed is written by the fixture script from the committed synthetic fixture, and the repo has no seed folder.
- A hand run of dbt with the Databricks profile skips the wrapper's seed check.
- The seed check trusts the work folder's `dbt_project.yml`. A hand edit of its seed path would point dbt at seeds the check never read.
- The month build on Databricks (31 October) builds `landed_complaints` from the file before its data tests run, so that one table can hold rows from a file that then fails a check. No model below it is built if a check on `landed_complaints` fails. The checks on `stg_complaints` run after its merge, as on the local target.
- The month build checks the columns it reads by name. A missing one fails the build, but an extra column is not refused, though `voc load` refuses one. The SHA-256 pin means the file is the one `voc load` checked.
- A month build's work folder is outside the repo's guards. If Databricks fails to read a row, dbt's log there can hold part of it. Nothing is printed, and the owner's steps delete the folder after the run.
- August's row count is not pinned, so on Databricks August is checked by its SHA-256 and values, not by its count.
- The real exports, with their narrative text, are in the owner's Databricks workspace (owner decision, 31 October 2026). The CFPB publishes them for anyone to use. Only the owner can open the workspace. Claude never reads the text: the commands print counts and check names only.
- The Databricks run uses the owner's Free Edition workspace, which is for non-commercial use only. Its token is the owner's, kept encrypted on the owner's machine, and never in the repo.


## About the data

- Source: the CFPB Consumer Complaint Database. Raw data is not stored in this repo.
- The CFPB says: "This database is not a statistical sample of consumers' experiences in the marketplace". Results here describe this data only.
- The CFPB also says: "All complaint data we publish is freely available for anyone to use, analyze, and build on." Both quotes are from the [CFPB complaint database page](https://www.consumerfinance.gov/data-research/consumer-complaints/), read 28 October 2026.
- The Product and Issue fields are set by the consumer, not by the CFPB ("The type of product the consumer identified in the complaint", [CFPB field reference](https://cfpb.github.io/api/ccdb/fields.html)). So the recorded labels are noisy, and some measured "errors" will be label noise.
