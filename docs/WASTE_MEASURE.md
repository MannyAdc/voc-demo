# How much working time was wasted

This page answers a question the owner asked on 10 November: how much of the week's work was wasted? It covers spec 004, the June test in the cloud, from its start on 4 November to 16 November 2026. The owner decided then to measure it at the end, from the build log. This is that measure.

In plain words:

- Waste here means time that a better first attempt would have saved. For example, on 10 November the second dry run in the cloud failed, because the code read the commit from a field of a Databricks run that had never been checked live. The 181 minutes spent finding that, fixing it and writing round 3's files (88 and 93 minutes in the table) are waste. So is round 3's row (75 minutes). Building the piece the first time, the reviews the rules require, and the real June run are not.
- Each stretch of waste is an episode, with a start and an end time copied from the log, and one cause.
- The minutes of all episodes are added up by cause, and compared with all the working time the log shows.

The result, in one line: 66 hours of 147 logged hours, or 45%, were waste, or 60 hours (41%) without the episodes that ran beside other work. These are not bounds: the choices under Limits push the figures both ways. Nearly all of the waste was Claude's own mistakes, of two kinds. Fix rounds for Claude's mistakes took about 36 hours. Rules about outside platforms built without a live check first took about 24 hours, and the log marks most of those as Claude's mistakes too.

The measure was made by a helper agent that read the log, then checked by Claude with the script under "Check the sums" below. It is an estimate: the minutes come straight from the log, but where an episode starts and ends, and which cause it gets, are judgement calls (see Limits).

Source: `BUILD_LOG.md`, read from line 1580 to the end on 16 November 2026, on the branch of pull request #142 at `cfed0c6`. Lines up to 3297 are the same as on `main` at `2d01af5`. Line 3298 at `cfed0c6`, under #141's heading, holds #141's fix commit (08:24) and its merge. The last two times, 08:52 and 08:53, are under #142's heading. All times are local (UTC+11) and come from log lines. Line numbers refer to the log up to line 3297, unless a row says otherwise.

## Words used on this page

- **Pull request (#N):** a proposed change. A fresh reviewer agent lists its problems, Claude fixes the ones the owner chooses, and the owner merges it.
- **Review round, fix round:** one review, and the fixes that follow it.
- **AI mistake:** an error of Claude's, marked as such in the build log.
- **Merge verdict, ready:** Claude's last check of a pull request, then marking it ready for the owner to merge.
- **Log commit:** a commit that only adds lines to the build log.
- **CI:** GitHub's automatic checks, run on every pull request and on every push to `main`.
- **Gate:** the check before each commit: all the tests, a scan for secrets and the names check. The two gates before the June run were other checks: the owner's check of the June file, and the failcheck.
- **Dry run, round:** a full rehearsal of the June run in the cloud, on made-up complaints. Each try is a round.
- **Row:** the line in the run log that allows one run.
- **Job A, Job B:** the two Databricks jobs. Job A unpacks and checks the upload. Job B labels the sample after the owner approves.
- **Receiver:** a small Azure app that hears from Databricks when Job A succeeds and starts the approval workflow.
- **Refit:** Job B trains the simple TF-IDF baseline again in the cloud, and checks it gives the same labels as on the laptop.
- **Scope:** the set of rights a sign-in token has, for example `jobs`.
- **Failcheck:** a Databricks run in which Job A's data step fails on a made-up row, to check that the robot account cannot read any of that row's text. A second run of the same step, without its quiet settings, is the control, which must show the row.
- **Poison message:** a queue message that failed too often and was set aside.
- **Probe:** a small read-only check of how a platform really behaves, run before a rule about it is written.

## 1. Summary

The period runs from the start of spec 004 (4 November, 18:31, line 1603) to the log's last entry when it was read (16 November, 08:53, the start of #142). The sub-period ends at 23:50 on 10 November, just after the owner's question about waste (line 2624). That line has no time. The log puts it between 23:46 (line 2623) and 23:49 (line 2627).

| | Whole period | Up to line 2624 |
|---|---|---|
| Logged working time | 146.7 h (8,799 min) | 86.2 h (5,172 min) |
| 1. Unchecked platform assumptions | 23.8 h (1,428 min), 16.2% | 13.5 h (809 min), 15.6% |
| 2. Fix rounds for Claude's mistakes | 36.5 h (2,189 min), 24.9% | 14.8 h (887 min), 17.2% |
| 3. Process overhead beyond the rules | 5.0 h (297 min), 3.4% | 5.0 h (297 min), 5.7% |
| 4. Stalls | 0.9 h (53 min), 0.6% | 0.9 h (53 min), 1.0% |
| **Total waste** | **66.1 h (3,967 min), 45.1%** | **34.1 h (2,046 min), 39.6%** |
| Total waste without the parallel episodes | 60.5 h (3,628 min), 41.2% | 31.6 h (1,893 min), 36.6% |

Parallel episodes ran at the same time as other work, mostly first-build work, so a better first attempt might not have saved their wall-clock time. The figures without them are not a floor: the choices under Limits push the figures both ways.

After the owner's question, waste went on: 32.0 h of the 60.5 h logged from then to the end, or 53%.

Comparison with Claude's estimate of 10 November ("roughly 20 to 30 hours, a third or more"):

- The share was right. Up to the question, waste was 40% of logged time, or 37% without the parallel episodes.
- The hours were above the range: 34.1 h measured, 31.6 h without the parallel episodes.
- The mix was different. Claude listed a heavier process among five causes. Measured, it was small, 5.0 h. Fix rounds for Claude's own mistakes (14.8 h) and platform assumptions without a live check (13.5 h) made up most of the waste.
- Stalls were small in the log, 0.9 h. "Friction" in the estimate, such as unclear owner steps, is mostly inside the fix rounds or not timed in the log (see Limits).

## 2. Method

- An episode is a stretch with a start and an end time, both taken from log lines. Its minutes are end minus start. Where the log gives no end, the next logged time in the same thread is used and marked "end estimated". Two ends and one start are marked as estimated in the table.
- Each episode has one cause. No stretch is counted twice. Where two waste episodes overlapped, the overlap was cut from one of them.
- Causes 1 and 2 overlap: the log marks most cause 1 episodes as Claude's mistakes too (for example lines 1820, 2093, 2339, 2430 and 2970). The rule used: a mistake about how an outside platform behaves, or code not yet run in the cloud, goes to cause 1. Every other mistake of Claude's goes to cause 2.
- Fix rounds (cause 2): counted from the time the review's findings were posted, when the log marks at least one finding of that round as an AI mistake. Some early rows end at the time the log gives for the fix being written (for example lines 1666, 1691 and 1732). Others end at the fix commit, as #135, #139 and #141 do, about 10 minutes after their fix was written. Where several rounds in a row had AI-marked findings, the stretch runs from the first findings to the last fix commit. Later rounds with no AI-marked finding are not counted. A whole pull request counts when a logged AI mistake caused it (for example #104, #118 and #136). So does work built on a cause Claude had not proven, which the log marks as an AI mistake: #121 to round 5 (line 2798).
- Platform assumptions (cause 1): a failed dry run round or gate run counts from the moment it failed. The final successful round or gate run is not waste, since a correct first attempt would have needed one. Every pull request and round in between counts: the fixes, the new round's files and its row. Code assumed to give the same result in the cloud as on the laptop, without being run there first, counts here too: in round 4 the refit kept other tied words in the cloud (line 2799).
- Process overhead (cause 3): before the owner's leaner process of 10 November (line 2446), each pull request got a log commit and its own CI run between the merge verdict and "ready". After it, the same step took about 1 minute (#105, line 2453). The stretch from verdict to ready is counted. So is #107, a pull request for round 3's log alone. From 12 November, late log lines went into the next pull request instead (line 2737). Reviews and gates that CLAUDE.md requires are not counted.
- Stalls (cause 4): waiting with no work caused by an avoidable error. Faults on GitHub's side, a network drop and a permission check are not counted.
- Not waste: the first build of each piece, required reviews, the owner's decisions and checks, the planned live tests, the successful runs and the real June run.
- Working time: the log was split into sessions at every gap of more than 2 hours between logged times. A session runs from its first to its last logged time, so waiting inside a session counts as working time. A range the log states ("12:46 to 17:46 Steps 1 to 10", line 2088, and the June run, 12:20 to 13:41, line 3111) counts as continuous. Sessions that cross midnight are listed by their start date.

Sessions and their minutes:

| Start date | Session | Minutes |
|---|---|---|
| 4 Nov | 18:31 to 22:15 | 224 |
| 5 Nov | 00:46 to 02:04 | 78 |
| 5 Nov | 06:49 to 17:40 | 651 |
| 5 Nov | 21:43 to 03:49 | 366 |
| 6 Nov | 08:20 to 11:29 | 189 |
| 6 Nov | 14:33 to 15:58 | 85 |
| 6 Nov | 21:47 to 01:15 | 208 |
| 7 Nov | 09:27 to 00:29 | 902 |
| 8 Nov | 10:42 to 15:57 | 315 |
| 8 Nov | 20:19 to 01:03 | 284 |
| 9 Nov | 08:02 to 18:34 | 632 |
| 9 Nov | 21:21 to 03:06 | 345 |
| 10 Nov | 08:57 to 02:00 (to 23:50 for the sub-period: 893) | 1,023 |
| 11 Nov | 06:43 to 13:08 | 385 |
| 12 Nov | 15:19 to 00:57 | 578 |
| 13 Nov | 08:16 to 00:05 | 949 |
| 14 Nov | 09:07 to 23:55 | 888 |
| 15 Nov | 09:28 to 17:50 | 502 |
| 15 Nov | 20:13 to 22:43 | 150 |
| 16 Nov | 08:08 to 08:53 | 45 |
| **Total** | | **8,799** |

Gaps removed, each over 2 hours: 4 Nov 22:15 to 5 Nov 00:46 (151 min), 5 Nov 02:04 to 06:49, 5 Nov 17:40 to 21:43, 6 Nov 03:49 to 08:20, 6 Nov 11:29 to 14:33 (the owner offline, line 1933), 6 Nov 15:58 to 21:47, 7 Nov 01:15 to 09:27, 8 Nov 00:29 to 10:42, 8 Nov 15:57 to 20:19, 9 Nov 01:03 to 08:02, 9 Nov 18:34 to 21:21 (167 min), 10 Nov 03:06 to 08:57, 11 Nov 02:00 to 06:43, 11 Nov 13:08 to 12 Nov 15:19, 13 Nov 00:57 to 08:16, 14 Nov 00:05 to 09:07, 14 Nov 23:55 to 15 Nov 09:28, 15 Nov 17:50 to 20:13 (143 min), 15 Nov 22:43 to 16 Nov 08:08.

## 3. Episodes

Causes: 1 platform assumption, 2 fix round for Claude's mistake, 3 process overhead, 4 stall. "Parallel" marks an episode that ran beside other work: first-build work, or in two rows (11 November, 06:43, and 13 November, 13:25) another fix. The figures without the parallel episodes leave these out.

| Date | Start | End | Min | Cause | Log lines | What happened |
|---|---|---|---|---|---|---|
| 5 Nov | 06:49 | 07:12 | 23 | 2 | 1657-1666 | #87 fix round: holes in Claude's guard (serious). Mixed with the owner's new browser rules. |
| 5 Nov | 07:29 | 07:45 | 16 | 3 | 1669-1670 | #87 log commit and CI wait, verdict to ready. |
| 5 Nov | 09:23 | 10:09 | 46 | 2 | 1685-1691 | #88 fix round: copy order and a weak J2 test (minor). |
| 5 Nov | 11:10 | 11:27 | 17 | 3 | 1701-1702 | #88 log commit wait. |
| 5 Nov | 12:44 | 13:37 | 53 | 2 | 1716-1732 | #89 fix round: a stopped run could be scored (serious). |
| 5 Nov | 13:55 | 14:13 | 18 | 3 | 1738-1739 | #89 log commit wait. |
| 5 Nov | 14:55 | 15:02 | 7 | 2 | 1752-1757 | #90 fix: a re-run could reuse an old approval (serious). |
| 5 Nov | 16:12 | 16:39 | 27 | 2 | 1773-1780 | #91 fix: literal Key Vault reference trusted, no extension bundle (serious). Parallel. |
| 5 Nov | 17:24 | 17:40 | 16 | 2 | 1793-1797 | 5a refused by the gate: a git test outside a checkout, the same mistake as in #89's pull request. End estimated. |
| 5 Nov | 21:43 | 22:53 | 70 | 2 | 1798-1805 | 5a seed copy proposed without reading the seed tests, rework. |
| 6 Nov | 00:18 | 00:34 | 16 | 3 | 1816-1817 | #92 log commit wait. |
| 6 Nov | 02:35 | 03:08 | 33 | 1 | 1819-1824 | #93: the receiver asked for an `all-apis` token, refused in the live spike. Parallel. |
| 6 Nov | 08:20 | 09:31 | 71 | 1 | 1825-1836, 1897 | #93 fix round to its verdict. Parallel. |
| 6 Nov | 09:31 | 09:53 | 22 | 3 | 1836, 1883 | #93 log commit wait. Parallel. |
| 6 Nov | 09:56 | 11:29 | 93 | 2 | 1884-1918 | #94 second fix round: serious errors in the first fix round. |
| 6 Nov | 14:33 | 15:06 | 33 | 2 | 1919-1955 | #94 third fix round: a serious error in the second. |
| 6 Nov | 21:47 | 22:03 | 16 | 3 | 1971-1972 | #94 log commit wait. |
| 6 Nov | 22:55 | 23:52 | 57 | 2 | 1987-2016 | #95 fix round: three serious errors. Includes the owner's decisions on the live test. |
| 7 Nov | 00:54 | 01:05 | 11 | 3 | 2025, 2037 | #95 log commit wait, cut where #96's findings start. |
| 7 Nov | 01:05 | 01:15 | 10 | 2 | 2037-2057 | #96 fix round, first part (serious). |
| 7 Nov | 09:27 | 10:20 | 53 | 2 | 2058-2067 | #96 fix round, second part, and a merge the gate refused. |
| 7 Nov | 11:24 | 11:39 | 15 | 3 | 2079-2080 | #96 log commit wait. |
| 7 Nov | 18:23 | 21:00 | 157 | 1 | 2092-2100 | Live receiver test: signed calls got no answer. The plan missed Python's HTTP concurrency of one. Several wrong leads. |
| 7 Nov | 21:10 | 21:22 | 12 | 1 | 2102-2103 | Application Insights removed, added only for that diagnosis. |
| 7 Nov | 22:04 | 23:00 | 56 | 2 | 2119-2140 | #97 fix round: the live Basic user was the tests' fixture value (minor). The owner changed it. |
| 7 Nov | 23:57 | 00:15 | 18 | 3 | 2150-2151 | #97 log commit wait. |
| 8 Nov | 11:54 | 12:38 | 44 | 2 | 2174-2185 | #98 fix round (minor). |
| 8 Nov | 13:37 | 13:54 | 17 | 3 | 2193-2194 | #98 log commit wait. |
| 8 Nov | 20:19 | 21:19 | 60 | 2 | 2217-2234 | #99 two fix rounds on wrong steps (minor). |
| 8 Nov | 22:04 | 22:39 | 35 | 3 | 2236-2238 | #99 log commit. Its CI failed at a download and was re-run. |
| 9 Nov | 08:51 | 09:47 | 56 | 2 | 2283-2295 | #100: results volume in the wrong schema (serious). The owner remade it. |
| 9 Nov | 10:02 | 10:44 | 30 | 2 | 2297-2306 | #100 second round, minus setup steps 2.7 and 2.8 (12 min). |
| 9 Nov | 10:59 | 11:17 | 18 | 3 | 2307-2308 | #100 log commit wait. |
| 9 Nov | 12:32 | 12:48 | 16 | 3 | 2326-2327 | #101 log commit wait. |
| 9 Nov | 14:14 | 16:18 | 124 | 1 | 2336-2345 | Dry run round 1 fails: the `jobs:read` scope refused (403), which came partly from Claude's step text (lines 2338-2339), the repair history never seen live, and the receiver's queue failures. |
| 9 Nov | 16:18 | 16:43 | 25 | 2 | 2345 | A wrong step for copying a failed queue message (a poison message), and five failed re-sends. |
| 9 Nov | 16:43 | 16:57 | 14 | 1 | 2345-2347 | End of round 1's receiver diagnosis. |
| 9 Nov | 16:57 | 18:21 | 84 | 1 | 2351-2369 | #102: round 1's fix and round 2's files. |
| 9 Nov | 18:21 | 18:34 | 13 | 3 | 2369-2370 | #102 log commit. CI failed at a download. End estimated. |
| 9 Nov | 21:24 | 22:22 | 58 | 1 | 2379-2390 | #103: round 2's row. #104 ran beside it from 21:57. |
| 9 Nov | 22:22 | 23:24 | 62 | 2 | 2371, 2394-2409 | #104: CI's downloads made to retry, after an AI mistake (line 2371). It started at 21:57, but is counted from 22:22, so its overlap with #103 is not counted twice. |
| 9 Nov | 23:24 | 23:37 | 13 | 3 | 2408-2409 | #104 log commit wait. |
| 10 Nov | 00:04 | 01:32 | 88 | 1 | 2409-2436 | Dry run round 2 fails: the commit read from a run field never seen live. |
| 10 Nov | 01:32 | 03:05 | 93 | 1 | 2436-2453 | #105: round 2's fix and round 3's files. |
| 10 Nov | 08:57 | 10:12 | 75 | 1 | 2458-2469 | #106: round 3's row. |
| 10 Nov | 11:31 | 12:07 | 36 | 3 | 2487-2493 | #107: round 3's log as its own pull request, its review and verdict. |
| 10 Nov | 16:33 | 17:26 | 53 | 4 | 2532-2538 | Claude said it was starting #110, then ended its turn. Start estimated. |
| 10 Nov | 20:04 | 20:29 | 25 | 2 | 2574-2580 | #112 fix: summary keys missing, cost too low (serious). |
| 10 Nov | 22:42 | 23:23 | 41 | 2 | 2612-2619 | #114 fix: any non-200 counted as a refusal (serious), then the `all-apis` scope. |
| 11 Nov | 00:36 | 01:30 | 54 | 2 | 2625, 2633-2637 | #115: the rule against quality shortcuts, after Claude proposed one. Parallel. |
| 11 Nov | 06:43 | 08:38 | 115 | 2 | 2645-2687 | A past decision stated from memory: #117's split and #118, three wordings. Parallel with #116's fix. |
| 11 Nov | 09:27 | 09:34 | 7 | 2 | 2697-2702 | #119 fix: a red test stricter than the agreed process. |
| 11 Nov | 12:36 | 12:45 | 9 | 1 | 2724 | Round 4: the file-arrival trigger counted the zip as already there. |
| 11 Nov | 12:53 | 13:08 | 15 | 1 | 2727-2732 | Round 4 fails at the refit check: the cloud kept other tied words than the laptop (found later, line 2799). Clean-up, first checks. |
| 12 Nov | 15:19 | 17:30 | 131 | 2 | 2736-2760, 2798 | #121: strict stopping point, built on a cause not proven. Logged as an AI mistake. |
| 12 Nov | 17:31 | 18:51 | 80 | 2 | 2764-2776, 2798 | #122: round 5's files, built on #121's cause. |
| 12 Nov | 18:52 | 20:08 | 76 | 2 | 2780-2789, 2798 | #123: round 5's row, built on #121's cause. |
| 12 Nov | 20:08 | 21:28 | 80 | 2 | 2793-2802 | Round 5 fails the same way, so #121's cause was wrong. The real cause is words tied at the vocabulary's cut-off. |
| 12 Nov | 21:28 | 23:18 | 110 | 1 | 2806-2829 | #124: the pinned vocabulary. |
| 13 Nov | 08:50 | 10:01 | 71 | 1 | 2851-2863 | #126: round 6's files. |
| 13 Nov | 10:02 | 10:56 | 54 | 1 | 2867-2875 | #127: round 6's row. |
| 13 Nov | 12:59 | 13:16 | 17 | 2 | 2902-2910 | #128 fix: a quote taken from a summary (minor). |
| 13 Nov | 13:25 | 13:42 | 17 | 1 | 2916-2919 | Gate 2 fails: serverless retries list each dbt task twice. Parallel with #128. |
| 13 Nov | 13:42 | 16:06 | 144 | 1 | 2923-2944 | #129: the failcheck reads every attempt. |
| 13 Nov | 16:06 | 17:06 | 60 | 2 | 2915, 2918, 2949-2963 | #130: every click and value the gates' steps lacked. |
| 13 Nov | 17:07 | 17:40 | 33 | 1 | 2963-2973 | Gates again: gate 2 fails on a control rule built on an unchecked Databricks assumption. |
| 13 Nov | 17:42 | 18:22 | 40 | 1 | 2977-3010 | #131 probe rule, and the probe run. |
| 13 Nov | 18:22 | 20:28 | 126 | 1 | 3014-3026 | #132: the failcheck's new control rule, the owner's option "A+" (line 2973). |
| 13 Nov | 21:19 | 21:35 | 16 | 2 | 3042-3044 | #133 refused by the gate: one test file run before the commit. |
| 14 Nov | 09:58 | 11:16 | 78 | 2 | 3079-3097 | #135 two fix rounds: cost 0.49 not 0.50, no key check (serious), then a retry sentence. |
| 14 Nov | 14:21 | 16:53 | 152 | 2 | 3115-3144 | Results commit failed: no `.gitignore` exception. #136 to fix it, two review rounds. |
| 14 Nov | 21:13 | 23:25 | 132 | 2 | 3188-3201 | #138 write-up fix rounds: overstated claims (minor). Includes 64 min waiting for the owner. |
| 15 Nov | 10:19 | 10:32 | 13 | 2 | 3217-3221 | #139 fix: the $0.49 claimed as Job B's alone. |
| 15 Nov | 14:45 | 17:50 | 185 | 2 | 3240-3261 | #140 reviews 1 to 4: each found a wrong claim of Claude's on credential risk, three of them serious. |
| 15 Nov | 20:13 | 22:03 | 94 | 2 | 3263-3283 | #140: the fix of review 4's findings, then reviews 5 and 6, minus 21:01 to 21:17 (the owner's question and deletions). |
| 16 Nov | 08:12 | 08:24 | 12 | 2 | 3293-3297, and line 3298 at `cfed0c6` | #141 fix: a section written without checking past steps. |

The first 49 rows are the sub-period up to line 2624.

## 4. Limits

What the log cannot show:

- Time in the removed gaps. The 2-hour rule removes at least one stretch of real work: 4 November 22:15 to 5 November 00:46, when the spec's fourth review ran and the owner decided. Removing working time makes the shares a little higher.
- Waiting inside a session counts as working time, for waste and for the total alike. Some episodes hold long waits for the owner, for example 64 min in the #138 row and about 100 min in the #140 rows.
- The owner's time outside the chat, for example portal work, is timed only where the log gives a range or a message time.
- Claude's time and the owner's time are not told apart. Wall-clock time is measured, not effort.
- 34 log entries from line 1603 to 3297 say the exact time was not recorded: `sed -n '1603,3297p' BUILD_LOG.md | grep -c "exact times\? not recorded"` printed 34. Their stretches are covered only through the logged times around them. Two ends and one start are estimated, marked in the table.

Choices that move the figures:

- Upward: a fix round counts whole when at least one of its findings is marked an AI mistake, though many rounds also fixed findings that were improvements, not mistakes. Some rows also hold the owner's own decisions (#87, #95, #100). A fix pull request counts whole, though a correct first build would also have taken some time.
- Downward: not counted are the four review rounds of the spec itself (#85, about 5 h on 4 and 5 November), the first build of #97 (partly a fix for the concurrency), #125 (the workflow's red cross after a failed Job B), small AI mistakes with no time, the Windows file-lock rebuilds, the gate refusals for a missing names list, unclear owner steps not tied to a fix round, the CI re-run of 9 November after 18:34 (in a removed gap), and the push refused by a permission check on 14 November (17:16 to 18:38, 82 min).
- Choices that could go either way: round 1 (9 November) counts as cause 1, though its refused `jobs:read` scope came from Claude's step text (lines 2338-2339) as much as from the platform. The log commits of #99 and #102 count as cause 3, though both hold a CI re-run after a download fault on GitHub's side, and line 2371 logs #102's re-run as an AI mistake, which would make that part cause 2. #104 counts as cause 2 in full, though it also changed when CI runs, and its retries were work a better first attempt would also have needed, only earlier. #115 (cause 2) and #131 (cause 1) count as waste, though they are rules the owner asked for after a mistake. The refit's tied words (round 4, #124 and round 6) count as cause 1, as code never run in the cloud before round 4, while #121 to round 5, built on a cause Claude had not proven, count as cause 2.
- Parallel work: 339 min of waste ran beside first-build work. The figures without the parallel episodes leave them out.

How sure the figures are: every start and end comes from a logged time, so the minutes of each chosen stretch are exact to the minute. The doubt is in the choices: where an episode starts and ends, and which cause it gets. The figure without the parallel episodes and the total differ by that one choice only: 60 and 66 hours, or 41 and 45% of logged time, for the whole period, and 32 and 34 hours, or 37 and 40%, up to the owner's question. They are not bounds, since the other choices above push the figures both ways. The split between causes 1 and 2 moves more than the total, since it rests on choices like the refit's above.

## 5. Check the sums

This script reads the two tables on this page and prints every figure in section 1: the working time, each cause, the total, the parallel minutes, the figures without them, and the part after the owner's question. It also lists any episode or session whose minutes are not its end minus its start. Save it as `check_waste.py` in the repo's folder and run `python -I check_waste.py`:

```python
import re

t = open('docs/WASTE_MEASURE.md', encoding='utf-8').read()


def span(a, b):
    return ((int(b[:2]) * 60 + int(b[3:])) - (int(a[:2]) * 60 + int(a[3:]))) % 1440


ep = re.findall(r'^\| (\d+) Nov \| (\d\d:\d\d) \| (\d\d:\d\d) \| (\d+) \| (\d) \| [^|]+ \| ([^|]+) \|$', t, re.M)
ss = re.findall(r'^\| (\d+) Nov \| (\d\d:\d\d) to (\d\d:\d\d)([^|]*)\| ([\d,]+) \|$', t, re.M)
work = sum(int(s[4].replace(',', '')) for s in ss)
work_sub = sum(int(re.search(r'sub-period: (\d+)', s[3]).group(1)) if 'sub-period' in s[3]
               else int(s[4].replace(',', '')) for s in ss if int(s[0]) <= 10)
sub = [e for e in ep if int(e[0]) <= 10]


def line(name, whole, part):
    print(f'{name}: {whole} min, {whole / 60:.1f} h, {100 * whole / work:.1f}% | '
          f'{part} min, {part / 60:.1f} h, {100 * part / work_sub:.1f}%')


print(f'episodes {len(ep)}, of them up to line 2624: {len(sub)}')
print(f'working time: {work} min, {work / 60:.1f} h | {work_sub} min, {work_sub / 60:.1f} h')
for c in '1234':
    line(f'cause {c}', sum(int(e[3]) for e in ep if e[4] == c), sum(int(e[3]) for e in sub if e[4] == c))
waste, waste_sub = sum(int(e[3]) for e in ep), sum(int(e[3]) for e in sub)
line('waste', waste, waste_sub)
par, par_sub = (sum(int(e[3]) for e in x if 'Parallel' in e[5]) for x in (ep, sub))
print(f'parallel: {par} min | {par_sub} min')
line('waste without parallel', waste - par, waste_sub - par_sub)
after, work_after = waste - waste_sub, work - work_sub
print(f'after line 2624: {after} min, {after / 60:.1f} h of {work_after} min, {work_after / 60:.1f} h, '
      f'{100 * after / work_after:.0f}%')
print('episodes whose minutes are not end minus start:',
      [f'{e[0]} Nov {e[1]}' for e in ep if span(e[1], e[2]) != int(e[3])])
print('sessions whose minutes are not end minus start:',
      [f'{s[0]} Nov {s[1]}' for s in ss if span(s[1], s[2]) != int(s[4].replace(',', ''))])
```

It printed, on 16 November 2026:

```
episodes 76, of them up to line 2624: 49
working time: 8799 min, 146.7 h | 5172 min, 86.2 h
cause 1: 1428 min, 23.8 h, 16.2% | 809 min, 13.5 h, 15.6%
cause 2: 2189 min, 36.5 h, 24.9% | 887 min, 14.8 h, 17.2%
cause 3: 297 min, 5.0 h, 3.4% | 297 min, 5.0 h, 5.7%
cause 4: 53 min, 0.9 h, 0.6% | 53 min, 0.9 h, 1.0%
waste: 3967 min, 66.1 h, 45.1% | 2046 min, 34.1 h, 39.6%
parallel: 339 min | 153 min
waste without parallel: 3628 min, 60.5 h, 41.2% | 1893 min, 31.6 h, 36.6%
after line 2624: 1921 min, 32.0 h of 3627 min, 60.5 h, 53%
episodes whose minutes are not end minus start: ['9 Nov 10:02', '15 Nov 20:13']
sessions whose minutes are not end minus start: []
```

The first figures on each line are for the whole period, those after the bar for the part up to line 2624. Two episodes' minutes are less than end minus start, because a stretch inside them was not waste and was taken out. Their rows say which: 9 November, 10:02 to 10:44, minus 12 minutes of setup steps, and 15 November, 20:13 to 22:03, minus 21:01 to 21:17.
