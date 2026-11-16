# How much working time was wasted

This page answers a question the owner asked on 10 November: how much of the week's work was wasted? It covers spec 004, the June test in the cloud, from its start on 4 November to 16 November 2026. The owner decided then to measure it at the end, from the build log. This is that measure.

In plain words:

- Waste here means time that a better first attempt would have saved. For example, on 9 November the first dry run in the cloud failed, because a rule about how Databricks answers had been built without first checking Databricks live. The two hours spent finding and fixing that are waste. Building the piece the first time, the reviews the rules require, and the real June run are not.
- Each stretch of waste is an episode, with a start and an end time copied from the log, and one cause.
- The minutes of all episodes are added up by cause, and compared with all the working time the log shows.

The result, in one line: about 58 to 65 hours of 147 logged hours, or 40 to 44%, were waste. Most of it came from two causes in about equal parts: rules about outside platforms built without a live check first, and fix rounds for Claude's own mistakes.

The measure was made by a helper agent that read the log, then checked by Claude with the script under "Check the sums" below. It is an estimate: the minutes come straight from the log, but where an episode starts and ends, and which cause it gets, are judgement calls (see Limits).

Source: `BUILD_LOG.md`, read from line 1580 to the end on 16 November 2026, on the branch of pull request #142 at `cfed0c6`. Lines up to 3297 are the same as on `main` at `2d01af5`. The last entries, #141's merge and the start of #142 (16 November, 08:24 to 08:53), are in #142's section of the log. All times are local (UTC+11) and come from log lines. Line numbers refer to the log up to line 3297.

## 1. Summary

The period runs from the start of spec 004 (4 November, 18:31, line 1603) to the log's last entry when it was read (16 November, 08:53, the start of #142). The sub-period ends at the owner's question about waste (10 November, about 23:50, line 2624).

| | Whole period | Up to line 2624 |
|---|---|---|
| Logged working time | 146.7 h (8,799 min) | 86.2 h (5,172 min) |
| 1. Unchecked platform assumptions | 29.9 h (1,795 min), 20.4% | 13.5 h (809 min), 15.6% |
| 2. Fix rounds for Claude's mistakes | 29.3 h (1,760 min), 20.0% | 13.8 h (825 min), 16.0% |
| 3. Process overhead beyond the rules | 5.0 h (297 min), 3.4% | 5.0 h (297 min), 5.7% |
| 4. Stalls | 0.9 h (53 min), 0.6% | 0.9 h (53 min), 1.0% |
| **Total waste** | **65.1 h (3,905 min), 44.4%** | **33.1 h (1,984 min), 38.4%** |
| Total waste without episodes that ran beside first-build work | 58.5 h, 39.9% | 29.6 h, 34.3% |

After the owner's question, waste went on: 32.0 h of the 60.5 h logged from then to the end, or 53%.

Comparison with Claude's estimate of 10 November ("roughly 20 to 30 hours, a third or more"):

- The share was right. Up to the question, waste was 38% of logged time, or 34% without the parallel episodes.
- The hours were at or a little above the top of the range: 33.1 h measured, 29.6 h as a lower bound.
- The mix was different. Claude named a heavier process as one main cause. Measured, it was small, 5.0 h. Platform assumptions without a live probe (13.5 h) and fix rounds for Claude's own mistakes (13.8 h) made up most of the waste.
- Stalls were small in the log, 0.9 h. "Friction" in the estimate, such as unclear owner steps, is mostly inside the fix rounds or not timed in the log (see Limits).

## 2. Method

- An episode is a stretch with a start and an end time, both taken from log lines. Its minutes are end minus start. Where the log gives no end, the next logged time in the same thread is used and marked "end estimated". One start is marked "start estimated" for the same reason.
- Each episode has one cause. No stretch is counted twice. Where two waste episodes overlapped, the overlap was cut from one of them.
- Fix rounds (cause 2): counted from the time the review's findings were posted to the fix commit, when the log marks at least one finding of that round as an AI mistake. Where several rounds in a row had AI-marked findings, the stretch runs from the first findings to the last fix commit. Later rounds with no AI-marked finding are not counted. A whole pull request counts when it exists only to fix a logged AI mistake (for example #118 and #136).
- Platform assumptions (cause 1): a failed dry run round or gate run counts from the moment it failed. The final successful round or gate run is not waste, since a correct first attempt would have needed one. Every pull request and round in between counts: the fixes, the new round's files and its row.
- Process overhead (cause 3): before the owner's leaner process of 10 November (line 2446), each pull request got a log commit and its own CI run between the merge verdict and "ready". After it, the same step took about 1 minute (#105, line 2453). The stretch from verdict to ready is counted. So is #107, a log-only pull request that a later entry calls "one more pull request for no gain" (line 2737). Reviews and gates that CLAUDE.md requires are not counted.
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

Causes: 1 platform assumption, 2 fix round for Claude's mistake, 3 process overhead, 4 stall. "Parallel" marks an episode that ran beside first-build work. These make up the difference between the total and the lower bound.

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
| 9 Nov | 14:14 | 16:18 | 124 | 1 | 2336-2345 | Dry run round 1 fails: `jobs:read` scope 403, repair history never seen live, receiver queue failures. |
| 9 Nov | 16:18 | 16:43 | 25 | 2 | 2345 | Wrong copy step for a poison message, five failed re-sends. |
| 9 Nov | 16:43 | 16:57 | 14 | 1 | 2345-2347 | End of round 1's receiver diagnosis. |
| 9 Nov | 16:57 | 18:21 | 84 | 1 | 2351-2369 | #102: round 1's fix and round 2's files. |
| 9 Nov | 18:21 | 18:34 | 13 | 3 | 2369-2370 | #102 log commit. CI failed at a download. End estimated. |
| 9 Nov | 21:24 | 22:22 | 58 | 1 | 2379-2390 | #103: round 2's row. Parallel with #104. |
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
| 11 Nov | 12:53 | 13:08 | 15 | 1 | 2727-2732 | Round 4 fails at the refit check on ARM, clean-up, first checks. |
| 12 Nov | 15:19 | 17:30 | 131 | 1 | 2736-2760 | #121: strict stopping point, built on a cause not proven. |
| 12 Nov | 17:31 | 18:51 | 80 | 1 | 2764-2776 | #122: round 5's files. |
| 12 Nov | 18:52 | 20:08 | 76 | 1 | 2780-2789 | #123: round 5's row. |
| 12 Nov | 20:08 | 21:28 | 80 | 1 | 2793-2802 | Round 5 fails the same way. The real cause is a tie in the vocabulary. |
| 12 Nov | 21:28 | 23:18 | 110 | 1 | 2806-2829 | #124: the pinned vocabulary. |
| 13 Nov | 08:50 | 10:01 | 71 | 1 | 2851-2863 | #126: round 6's files. |
| 13 Nov | 10:02 | 10:56 | 54 | 1 | 2867-2875 | #127: round 6's row. |
| 13 Nov | 12:59 | 13:16 | 17 | 2 | 2902-2910 | #128 fix: a quote taken from a summary (minor). |
| 13 Nov | 13:25 | 13:42 | 17 | 1 | 2916-2919 | Gate 2 fails: serverless retries list each dbt task twice. Parallel with #128. |
| 13 Nov | 13:42 | 16:06 | 144 | 1 | 2923-2944 | #129: the failcheck reads every attempt. |
| 13 Nov | 16:06 | 17:06 | 60 | 2 | 2915, 2918, 2949-2963 | #130: every click and value the gates' steps lacked. |
| 13 Nov | 17:07 | 17:40 | 33 | 1 | 2963-2973 | Gates again: gate 2 fails on a control rule built on an unchecked Databricks assumption. |
| 13 Nov | 17:42 | 18:22 | 40 | 1 | 2977-3010 | #131 probe rule, and the probe run. |
| 13 Nov | 18:22 | 20:28 | 126 | 1 | 3014-3026 | #132: the control rule A+. |
| 13 Nov | 21:19 | 21:35 | 16 | 2 | 3042-3044 | #133 refused by the gate: one test file run before the commit. |
| 14 Nov | 09:58 | 11:16 | 78 | 2 | 3079-3097 | #135 two fix rounds: cost 0.49 not 0.50, no key check (serious), then a retry sentence. |
| 14 Nov | 14:21 | 16:53 | 152 | 2 | 3115-3144 | Results commit failed: no `.gitignore` exception. #136 to fix it, two review rounds. |
| 14 Nov | 21:13 | 23:25 | 132 | 2 | 3188-3201 | #138 write-up fix rounds: overstated claims (minor). Includes 64 min waiting for the owner. |
| 15 Nov | 10:19 | 10:32 | 13 | 2 | 3217-3221 | #139 fix: the $0.49 claimed as Job B's alone. |
| 15 Nov | 14:45 | 17:50 | 185 | 2 | 3240-3261 | #140 reviews 1 to 4: each found a wrong claim of Claude's on credential risk (serious). |
| 15 Nov | 20:13 | 22:03 | 94 | 2 | 3263-3283 | #140 reviews 5 and 6, minus 21:01 to 21:17 (the owner's question and deletions). |
| 16 Nov | 08:12 | 08:24 | 12 | 2 | 3293-3297, #142's first line | #141 fix: a section written without checking past steps. |

The first 48 rows are the sub-period up to line 2624.

## 4. Limits

What the log cannot show:

- Time in the removed gaps. The 2-hour rule removes at least one stretch of real work: 4 November 22:15 to 5 November 00:46, when the spec's fourth review ran and the owner decided. Removing working time makes the shares a little higher.
- Waiting inside a session counts as working time, for waste and for the total alike. Some episodes hold long waits for the owner, for example 64 min in the #138 row and about 100 min in the #140 rows.
- The owner's time outside the chat, for example portal work, is timed only where the log gives a range or a message time.
- Claude's time and the owner's time are not told apart. Wall-clock time is measured, not effort.
- About a dozen log entries have no time ("exact time not recorded"). Their stretches are covered only through the logged times around them. One end and one start are estimated, marked in the table.

Choices that move the figures:

- Upward: a fix round counts whole when at least one of its findings is marked an AI mistake, though many rounds also fixed findings that were improvements, not mistakes. Some rows also hold the owner's own decisions (#87, #95, #100).
- Downward: not counted are the four review rounds of the spec itself (#85, about 5 h on 4 and 5 November), the first build of #97 (partly a fix for the concurrency), #125 (the workflow's red cross after a failed Job B), small AI mistakes with no time, the Windows file-lock rebuilds, the gate refusals for a missing names list, unclear owner steps not tied to a fix round, the CI re-run of 9 November after 18:34 (in a removed gap), and the push refused by a permission check on 14 November (17:16 to 18:38, 82 min).
- Parallel work: 397 min of waste ran beside first-build work. The lower bound leaves them out.

How sure the figures are: every start and end comes from a logged time, so the minutes of each chosen stretch are exact to the minute. The doubt is in the choices: where an episode starts and ends, and which cause it gets. A fair range for the whole period is the lower bound to the total, 58 to 65 hours, or 40 to 44% of logged time. Up to the owner's question it is 30 to 33 hours, or 34 to 38%.

## 5. Check the sums

This script reads the two tables on this page, checks each episode's minutes against its start and end, and adds them up. Run it from the repo's folder:

```
python -I -c "
import re
t = open('docs/WASTE_MEASURE.md', encoding='utf-8').read()
m = lambda a, b: ((int(b[:2]) * 60 + int(b[3:])) - (int(a[:2]) * 60 + int(a[3:]))) % 1440
ep = re.findall(r'^[|] (\d+ Nov) [|] (\d\d:\d\d) [|] (\d\d:\d\d) [|] (\d+) [|] (\d) [|]', t, re.M)
ss = re.findall(r'^[|] \d+ Nov [|] (\d\d:\d\d) to (\d\d:\d\d)[^|]*[|] ([\d,]+) [|]$', t, re.M)
for c in '1234': print('cause', c, sum(int(e[3]) for e in ep if e[4] == c), sum(int(e[3]) for e in ep[:48] if e[4] == c))
print('waste', sum(int(e[3]) for e in ep), sum(int(e[3]) for e in ep[:48]))
print('episodes', len(ep), 'sessions', sum(int(s[2].replace(',', '')) for s in ss))
print('minutes not end minus start', [e[:4] for e in ep if m(e[1], e[2]) != int(e[3])])
"
```

It printed, on 16 November 2026:

```
cause 1 1795 809
cause 2 1760 825
cause 3 297 297
cause 4 53 53
waste 3905 1984
episodes 75 sessions 8799
minutes not end minus start [('9 Nov', '10:02', '10:44', '30'), ('15 Nov', '20:13', '22:03', '94')]
```

Each cause's minutes are given for the whole period, then up to line 2624. Two rows' minutes are less than end minus start, because a stretch inside them was not waste and was taken out. Their rows say which: 9 November, 10:02 to 10:44, minus 12 minutes of setup steps, and 15 November, 20:13 to 22:03, minus 21:01 to 21:17.
