# `full_v3`: the whole Dagdeviren benchmark, one night, one k

Every cell the dataset contains was swept at k = 6, the capacity all three published sweeps used, so these rows can be read against them and against each other. What follows is measured; where a number is missing the reason is named rather than the row dropped.

## 1. What ran

| stage | n | m/n | seeds | instances | rows | configs | main pass | GHS pass |
|---|---|---|---|---|---|---|---|---|
| `small` | 10, 15, 20, 25 | 2, 4, 6, 8, 10 | 10 | 140 | 3500 | 25 | 17 m 07 s | 1 m 08 s |
| `medium` | 50, 100 | 50: 2 to 10; 100: 2 to 8 | 10 | 90 | 2250 | 25 | 2 h 01 m | 9 m 10 s |
| `mediumdense` | 100 | 10 | 10 | 10 | 250 | 25 | 1 h 37 m | 9 m |
| `large` | 150, 200 | 2, 4, 6 | 10 | 60 | 1500 | 25 | 49 m 44 s | 3 m 22 s |
| `xlarge` | 250, 500, 750, 1000 | 2, 4, 6 | 1 | 12 | 300 | 25 | 2 h 07 m | 31 m 16 s |
| `largedense` | 150, 200 | 8, 10 | 3 | 12 | 300 | 25 | 55 m 32 s | 12 m 21 s |
| `densecomplete` | 150, 200; 250 to 1000 | 8, 10 | 150/200: 4 to 10; above: 1 | 36 | 708 | 25 at n <= 200, 1 at n >= 250 | 13 h 00 m on 13 workers | — |
| **total** | | | | **360** | **8808** | | **00:33 to 06:45** | **06:45 to 07:43** |

**All 360 files the benchmark ships were read.** The first six stages covered 324 of them and left 36 unmeasured; the `densecomplete` stage closed that gap, and the shape of the closure matters more than the count.

Twenty-eight of the 36 are the further seeds of the n = 150 and 200 cells at m/n = 8 and 10, and each carries all twenty-five configurations. The remaining eight are the m/n = 8 and 10 cells at n = 250 and above, and each carries **one**: `MIS-Connector-Backbone` under the synchronous scheduler. That is a witness run, deliberately taken instead of the full set, and the reason is arithmetic. Measuring all twenty-five on those eight costs about 218 core-hours against 86 for the whole rest of the stage, and buys no comparison: every one of the eight has m > nk at k = 6, so no cover exists, no arm can score, and the twenty-four unmeasured configurations per file would have produced exactly one quantity — how long each arm takes to announce an impossibility that one line of arithmetic already proves.

**So the claim these rows support is 360 of 360 files read, not 25 configurations on each of 360 files.** The measured shape is 352 files at twenty-five configurations plus 8 files at one, 8808 rows against the 9000 a complete sweep would hold. `densecomplete/CUT_LIST` names every job that ran and `densecomplete/jobs.jsonl` every job that was planned, so what was left out is a list somebody can run later rather than a gap nobody can describe.

Measured, not estimated, at the dense cells that were run whole: median seconds per run are 174 at n = 150 with m/n = 8, 259 at n = 150 with m/n = 10, 284 at n = 200 with m/n = 8 and 355 at n = 200 with m/n = 10, with a maximum of 1165 s. The eight witness runs took 257 s at n = 250 with m/n = 8 rising to 2298 s at n = 1000 with m/n = 10. The pilot figure this cut was originally justified with, 170 to 202 s per run at n = 150, matches the m/n = 8 cell and understates m/n = 10 by about a quarter.

Every cell the dataset has is represented. It holds 54 cells and 360 files, not five densities at every n: n = 10 has two, n = 15 three, n = 20 four. `matrix.py` stops at m/n = 8, so the m/n = 10 cells at n = 25, 50, 100, 150 and 200 were enumerated directly by the driver; through the stock command line they would have been missed.

## 2. Which code measured which rows

Four fingerprints appear. They do not separate arms from each other; they separate a first measurement from the two re-measurements that followed it, and both from the completeness sweep that ran last.

| fingerprint | what it marks |
|---|---|
| `798b4393cb4f` | first measurement, the nine arms that are neither GHS-MST-Backbone nor annealing |
| `bebb0f917410` | GHS-MST-Backbone everywhere, plus any row the budget skipped on the first pass and had to be re-run |
| `be8a9f9c1e43` | Anneal-Local, Anneal-TreeAgg and Anneal-Trickle, re-measured after the §107 fix |
| `956bf8aa4130` | the `densecomplete` stage: the 36 files no other stage measured, every one of which has m > nk, plus the 187 (instance, arm, scheduler) pairs an earlier stage had written `skipped` |

Each value is admitted for a stated reason and the fold refuses anything else. A row may carry `bebb0f917410` only if it is GHS-MST-Backbone or was written `skipped` on the first pass, `be8a9f9c1e43` only if its arm is one of the three annealing arms, and `956bf8aa4130` only if no cover exists on its instance or that exact (instance, arm, scheduler) had been written `skipped` — the pairs are listed, as they stood before any fill, in `_topup/densecomplete_fills/skipped_pairs.json`, and `paper/tools/check_paper.py` tests the condition row by row rather than counting distinct values. So a run cannot be re-rolled because somebody disliked its result, and every row that ran the first time and was not touched by a fix keeps its original measurement.

**The §107 fix is why the third value exists.** `anneal.py`'s freeze path skipped Phase 3, so the §105 key-election repair never ran. All three annealing arms share that path, so all three were re-measured: replacing only Anneal-Trickle, the arm whose false successes exposed the defect, would have left the other two measured against code known to be wrong with nothing marking them. The rows each re-measurement replaced are archived beside the stage, because the difference between old and new is the evidence a fix did what it claims.

**The fourth value marks a new copy of the code, not new code.** A reboot at 22:20 on 2026-09-18 cleared `/tmp` and took the `be8a9f9c1e43` snapshot with it, so the remaining work ran against a replacement snapshot held under `results/` where no reboot can reach it. `anneal.py` and `v4_mst.py` in that snapshot have exactly the sha256 values this file already recorded for the §107 and GHS fixes, and the fingerprint moved only because a copy has new modification times and because five reporting modules were edited after the earlier snapshot. None of the five is on the path that produces a row; that was checked by running a full twenty-five configuration job and reading the loaded modules back out of `sys.modules` rather than assumed.

The first two values are the same code for every arm but GHS. The GHS pass ran after ghs-debug declared `v4_mst.py` final, and that file differs from the earlier snapshot in source text only, confirmed here by comparing both syntax trees with docstrings stripped; the nine other arms never import it. The third value is a real behavioural change and only the annealing arms carry it. `FINGERPRINTS.md` has the hashes, the snapshot times and the quiet-tree check each copy waited for.

### One thing `largedense` still does not carry

Every instance in that stage has m > nk at k = 6, so no cover exists and each arm's only job is to announce impossibility. Two decisions followed from that and only one of them still stands.

Its 150 budget-skipped rows **were** filled, by the `densecomplete` pass, and they carry `956bf8aa4130`. The stage now holds 300 measured rows and no `skipped` ones. What has not changed is its annealing rows, which keep their pre-§107 measurement at `798b4393cb4f`. The §107 defect shows itself as a false success, a run claiming a cover the validator rejects, and on an instance with no cover there is nothing to claim: the stage is `infeasible` throughout with zero false successes. No table reads these rows for quality, so re-measuring them would cost hours to move no number.

### The wall-clock column was removed from the tables

`seconds` is how long a run took on the machine that measured it, and the sweep ran on a shared box whose load varied by a factor of three between passes. `tab:scaling` and `tab:distmetrics` printed it as an `s` column averaged over rows from different passes, which is not one quantity. Both columns are gone. Nothing was lost: both tables already print `t_conv_ms`, which is simulated and therefore identical no matter what else the machine was doing, and every argument those tables carry is made by slots, tx, rx and payload.

**A rule I proposed for this and had to withdraw**, because it is the kind of mistake worth recording rather than quietly fixing. I first told the section writer to quote wall-clock timings only from rows at `798b4393cb4f`, on the theory that the later fingerprints marked the contended re-runs. writer-eval3 checked it and it fails in both directions. Among scored rows that fingerprint excludes every GHS-MST-Backbone row in the sweep, because GHS carries the second value for a code reason and not a timing one, so no sentence written under the rule could mention the MST backbone at all. And it keeps exactly what it was meant to drop: the slowest scored row anywhere is DFS-Spanning-Backbone async on `n1000_m4000_s1` at 5028.3 s, and it is a first-pass row. Within the first pass alone the scored rows run from a median of 0.49 s to a 99th percentile of 51.4 s to that 5028.3 s maximum. A fingerprint records which code ran, not how loaded the machine was, and using it as a proxy for the second thing was wrong.

### A reading error these tables carried until it was found

An earlier build of `paper/tables_full/` was circulated, and two of its columns were wrong in the same way. `sweep._skipped_row` fills the `infeasible` column with False because the dataclass needs a value, not because anything was measured, and both `common_subset` and `arm_stats` read that default as evidence. Budget-skipped rows therefore counted as feasible runs an arm had failed. In the reliability table the n = 250 to 1000 column read 64 per cent for Anneal-TreeAgg, 70 for Anneal-Local and 89 for MIS-Connector, all of which are 100; and the dense column read nought per cent for most arms, which said twenty-five arms failed on twelve problems when no instance there admits a cover and every arm said so. Both call sites now share one helper that judges feasibility per instance from rows that actually ran, and an empty denominator prints a dash rather than a zero. Any number quoted from the first build of these tables should be re-read from this one.

## 3. False successes

None.

## 4. Per stage

### `small`

- instances 140, feasible 110, infeasible 30 (witness $m > nk$)
- common valid subset **110** of 110
- statuses `ok` 2750, `infeasible` 750

| arm | valid / common | vs best | vs optimum | algo tx | total tx |
|---|---|---|---|---|---|
| `GHS-MST-Backbone/async` | 110/110 | 1.031 | 1.142 | 1170 | 2624 |
| `GHS-MST-Backbone/sync` | 110/110 | 1.053 | 1.176 | 1322 | 3277 |
| `Anneal-Local/async` | 110/110 | 1.000 | 1.166 | 419 | 2636 |
| `Anneal-Local/sync` | 110/110 | 1.003 | 1.179 | 491 | 3018 |
| `Anneal-TreeAgg/async` | 110/110 | 1.000 | 1.166 | 419 | 2636 |
| `Anneal-TreeAgg/sync` | 110/110 | 1.003 | 1.179 | 491 | 3018 |
| `Anneal-Trickle/async` | 110/110 | 1.004 | 1.161 | 419 | 1685 |
| `DFS-Spanning-Backbone/async` | 110/110 | 1.128 | 1.318 | 927 | 4431 |
| `DFS-Spanning-Backbone/sync` | 110/110 | 1.126 | 1.306 | 952 | 7322 |
| `MIS-Connector-Backbone/async` | 110/110 | 1.107 | 1.266 | 825 | 2064 |
| `MIS-Connector-Backbone/sync` | 110/110 | 1.121 | 1.278 | 763 | 2387 |
| `MIS-Connector-TreeAgg/async` | 110/110 | 1.107 | 1.266 | 1110 | 2352 |
| `MIS-Connector-TreeAgg/sync` | 110/110 | 1.121 | 1.278 | 1118 | 2742 |
| `WuLi-Dominating-Exact/async` | 110/110 | 1.162 | 1.351 | 705 | 1816 |
| `WuLi-Dominating-Exact/sync` | 110/110 | 1.163 | 1.355 | 688 | 2111 |
| `WuLi-Dominating-Bloom/async` | 110/110 | 1.195 | 1.467 | 425 | 1094 |
| `WuLi-Dominating-Bloom/sync` | 110/110 | 1.195 | 1.467 | 494 | 1475 |
| `WuLi-Dominating-Chunked/async` | 110/110 | 1.162 | 1.351 | 705 | 2712 |
| `WuLi-Dominating-Chunked/sync` | 110/110 | 1.163 | 1.355 | 688 | 3298 |
| `Greedy-Degree-Backbone/async` | 110/110 | 1.135 | 1.324 | 991 | 2133 |
| `Greedy-Degree-Backbone/sync` | 110/110 | 1.156 | 1.361 | 1021 | 2469 |
| `Greedy-Ratio-Backbone/async` | 110/110 | 1.136 | 1.321 | 939 | 1998 |
| `Greedy-Ratio-Backbone/sync` | 110/110 | 1.160 | 1.374 | 972 | 2324 |
| `Greedy-Weight-Backbone/async` | 110/110 | 1.139 | 1.327 | 856 | 1817 |
| `Greedy-Weight-Backbone/sync` | 110/110 | 1.159 | 1.382 | 908 | 2150 |

### `medium`

- instances 90, feasible 50, infeasible 40 (witness $m > nk$ or $\sum_v \min(\deg v, k) < m$)
- common valid subset **50** of 50
- statuses `ok` 1250, `infeasible` 1000

| arm | valid / common | vs best | vs optimum | algo tx | total tx |
|---|---|---|---|---|---|
| `GHS-MST-Backbone/async` | 50/50 | 1.146 | -- | 4052 | 9573 |
| `GHS-MST-Backbone/sync` | 50/50 | 1.158 | -- | 4958 | 13099 |
| `Anneal-Local/async` | 50/50 | 1.000 | -- | 1366 | 9949 |
| `Anneal-Local/sync` | 50/50 | 1.009 | -- | 1590 | 11342 |
| `Anneal-TreeAgg/async` | 50/50 | 1.000 | -- | 1366 | 9949 |
| `Anneal-TreeAgg/sync` | 50/50 | 1.009 | -- | 1590 | 11342 |
| `Anneal-Trickle/async` | 50/50 | 1.026 | -- | 1368 | 6315 |
| `DFS-Spanning-Backbone/async` | 50/50 | 1.226 | -- | 2703 | 39965 |
| `DFS-Spanning-Backbone/sync` | 50/50 | 1.222 | -- | 2939 | 75343 |
| `MIS-Connector-Backbone/async` | 50/50 | 1.236 | -- | 1664 | 4763 |
| `MIS-Connector-Backbone/sync` | 50/50 | 1.236 | -- | 1803 | 6279 |
| `MIS-Connector-TreeAgg/async` | 50/50 | 1.236 | -- | 5816 | 8959 |
| `MIS-Connector-TreeAgg/sync` | 50/50 | 1.236 | -- | 7332 | 11808 |
| `WuLi-Dominating-Exact/async` | 50/50 | 1.237 | -- | 1462 | 4136 |
| `WuLi-Dominating-Exact/sync` | 50/50 | 1.237 | -- | 1643 | 5432 |
| `WuLi-Dominating-Bloom/async` | 50/50 | 1.238 | -- | 1412 | 3996 |
| `WuLi-Dominating-Bloom/sync` | 50/50 | 1.238 | -- | 1612 | 5340 |
| `WuLi-Dominating-Chunked/async` | 50/50 | 1.237 | -- | 1462 | 5804 |
| `WuLi-Dominating-Chunked/sync` | 50/50 | 1.237 | -- | 1643 | 7978 |
| `Greedy-Degree-Backbone/async` | 50/50 | 1.237 | -- | 2625 | 5665 |
| `Greedy-Degree-Backbone/sync` | 50/50 | 1.237 | -- | 3071 | 7491 |
| `Greedy-Ratio-Backbone/async` | 50/50 | 1.237 | -- | 2610 | 5636 |
| `Greedy-Ratio-Backbone/sync` | 50/50 | 1.237 | -- | 3071 | 7491 |
| `Greedy-Weight-Backbone/async` | 50/50 | 1.237 | -- | 2610 | 5636 |
| `Greedy-Weight-Backbone/sync` | 50/50 | 1.237 | -- | 3071 | 7491 |

### `mediumdense`

- instances 10, feasible 0, infeasible 10 (witness $m > nk$)
- common valid subset **0** of 0
- statuses `infeasible` 250

| arm | valid / common | vs best | vs optimum | algo tx | total tx |
|---|---|---|---|---|---|

### `large`

- instances 60, feasible 45, infeasible 15 (witness $\sum_v \min(\deg v, k) < m$)
- common valid subset **42** of 45
- statuses `ok` 1100, `infeasible` 375, `unresolved` 25

| arm | valid / common | vs best | vs optimum | algo tx | total tx |
|---|---|---|---|---|---|
| `GHS-MST-Backbone/async` | 43/45 | 1.172 | -- | 8917 | 20856 |
| `GHS-MST-Backbone/sync` | 44/45 | 1.194 | -- | 12216 | 32362 |
| `Anneal-Local/async` | 44/45 | 1.000 | -- | 2480 | 21538 |
| `Anneal-Local/sync` | 44/45 | 1.005 | -- | 2644 | 23578 |
| `Anneal-TreeAgg/async` | 44/45 | 1.000 | -- | 2480 | 21538 |
| `Anneal-TreeAgg/sync` | 44/45 | 1.005 | -- | 2644 | 23578 |
| `Anneal-Trickle/async` | 44/45 | 1.035 | -- | 2479 | 13380 |
| `DFS-Spanning-Backbone/async` | 45/45 | 1.267 | -- | 4917 | 172571 |
| `DFS-Spanning-Backbone/sync` | 44/45 | 1.267 | -- | 5224 | 334088 |
| `MIS-Connector-Backbone/async` | 44/45 | 1.274 | -- | 2632 | 7459 |
| `MIS-Connector-Backbone/sync` | 44/45 | 1.274 | -- | 2840 | 9961 |
| `MIS-Connector-TreeAgg/async` | 44/45 | 1.274 | -- | 11437 | 16404 |
| `MIS-Connector-TreeAgg/sync` | 44/45 | 1.274 | -- | 15974 | 23094 |
| `WuLi-Dominating-Exact/async` | 44/45 | 1.273 | -- | 2583 | 7095 |
| `WuLi-Dominating-Exact/sync` | 44/45 | 1.273 | -- | 2698 | 8889 |
| `WuLi-Dominating-Bloom/async` | 44/45 | 1.274 | -- | 2583 | 7095 |
| `WuLi-Dominating-Bloom/sync` | 44/45 | 1.274 | -- | 2698 | 8888 |
| `WuLi-Dominating-Chunked/async` | 44/45 | 1.273 | -- | 2583 | 8942 |
| `WuLi-Dominating-Chunked/sync` | 44/45 | 1.273 | -- | 2698 | 11665 |
| `Greedy-Degree-Backbone/async` | 44/45 | 1.274 | -- | 5096 | 9920 |
| `Greedy-Degree-Backbone/sync` | 44/45 | 1.274 | -- | 5962 | 13081 |
| `Greedy-Ratio-Backbone/async` | 44/45 | 1.274 | -- | 5097 | 9920 |
| `Greedy-Ratio-Backbone/sync` | 44/45 | 1.274 | -- | 5962 | 13081 |
| `Greedy-Weight-Backbone/async` | 44/45 | 1.274 | -- | 5097 | 9920 |
| `Greedy-Weight-Backbone/sync` | 44/45 | 1.274 | -- | 5962 | 13081 |

### `xlarge`

- instances 12, feasible 8, infeasible 4 (witness $\sum_v \min(\deg v, k) < m$)
- common valid subset **8** of 8
- statuses `ok` 200, `infeasible` 100

- **The 37 rows the wall-clock budget had skipped are now measured.** They were at n = 500, m/n = 6 (6 rows), n = 750, m/n = 6 (13 rows) and n = 1000, m/n = 6 (18 rows), and they carry `956bf8aa4130`. Those three instances have m equal to nk rather than greater, so the counting bound never fires on them and their infeasibility rests on the degree-deficiency witness of §96, which every measured row on them reports. They were therefore the only fills in this whole pass that could have moved a published number, and the reliability denominators they feed did not move: the instances are infeasible, so the per-instance helper excludes them exactly as it did when the rows were absent.

| arm | valid / common | vs best | vs optimum | algo tx | total tx |
|---|---|---|---|---|---|
| `GHS-MST-Backbone/async` | 8/8 | 1.191 | -- | 36846 | 92920 |
| `GHS-MST-Backbone/sync` | 8/8 | 1.215 | -- | 54566 | 155736 |
| `Anneal-Local/async` | 8/8 | 1.000 | -- | 7713 | 73945 |
| `Anneal-Local/sync` | 8/8 | 1.006 | -- | 7749 | 77144 |
| `Anneal-TreeAgg/async` | 8/8 | 1.000 | -- | 7713 | 73945 |
| `Anneal-TreeAgg/sync` | 8/8 | 1.006 | -- | 7749 | 77144 |
| `Anneal-Trickle/async` | 8/8 | 1.058 | -- | 7720 | 45572 |
| `DFS-Spanning-Backbone/async` | 8/8 | 1.291 | -- | 16105 | 2408054 |
| `DFS-Spanning-Backbone/sync` | 8/8 | 1.291 | -- | 16101 | 4725039 |
| `MIS-Connector-Backbone/async` | 8/8 | 1.293 | -- | 8350 | 23340 |
| `MIS-Connector-Backbone/sync` | 8/8 | 1.293 | -- | 8520 | 29676 |
| `MIS-Connector-TreeAgg/async` | 8/8 | 1.293 | -- | 46564 | 62241 |
| `MIS-Connector-TreeAgg/sync` | 8/8 | 1.293 | -- | 65477 | 86633 |
| `WuLi-Dominating-Exact/async` | 8/8 | 1.292 | -- | 7977 | 21599 |
| `WuLi-Dominating-Exact/sync` | 8/8 | 1.292 | -- | 7977 | 25422 |
| `WuLi-Dominating-Bloom/async` | 8/8 | 1.293 | -- | 7977 | 21599 |
| `WuLi-Dominating-Bloom/sync` | 8/8 | 1.293 | -- | 7977 | 25422 |
| `WuLi-Dominating-Chunked/async` | 8/8 | 1.292 | -- | 7977 | 25078 |
| `WuLi-Dominating-Chunked/sync` | 8/8 | 1.292 | -- | 7977 | 30026 |
| `Greedy-Degree-Backbone/async` | 8/8 | 1.293 | -- | 17303 | 32279 |
| `Greedy-Degree-Backbone/sync` | 8/8 | 1.293 | -- | 20003 | 41135 |
| `Greedy-Ratio-Backbone/async` | 8/8 | 1.293 | -- | 17303 | 32279 |
| `Greedy-Ratio-Backbone/sync` | 8/8 | 1.293 | -- | 20003 | 41135 |
| `Greedy-Weight-Backbone/async` | 8/8 | 1.293 | -- | 17303 | 32279 |
| `Greedy-Weight-Backbone/sync` | 8/8 | 1.293 | -- | 20003 | 41135 |

### `largedense`

- instances 12, feasible 0, infeasible 12 (witness $m > nk$)
- common valid subset **0** of 0
- statuses `infeasible` 300

- **The 150 rows the wall-clock budget had skipped are now measured** and carry `956bf8aa4130`. They were at n = 150, m/n = 8 (17 rows), n = 150, m/n = 10 (34 rows), n = 200, m/n = 8 (36 rows) and n = 200, m/n = 10 (63 rows). Every instance here has m > nk, so the fills changed no quality number; what they changed is that the stage no longer reports rows it did not take.

| arm | valid / common | vs best | vs optimum | algo tx | total tx |
|---|---|---|---|---|---|

### `densecomplete`

- instances 36, feasible 0, infeasible 36 (witness $m > nk$)
- common valid subset **0** of 0
- statuses `infeasible` 708

The arm table is empty here and that is the correct output, not a missing one. No instance in this stage admits a cover, so there is no scored denominator, and printing a zero would say twenty-five arms failed on thirty-six problems that have no solution.

The stage is two different things measured under one fingerprint:

- **28 files at n = 150 and 200, m/n = 8 and 10, each with all 25 configurations**, 700 rows. These are the seeds the first pass stopped short of, three run out of ten per cell.
- **8 files at n = 250 and above, m/n = 8 and 10, each with one configuration**, 8 rows. `MIS-Connector-Backbone` under the synchronous scheduler, measured at 257 s on `n250_m2000_s1` rising to 2298 s on `n1000_m10000_s1`, every one returning `infeasible` on the counting bound.

The 187 fills this same pass measured are not counted here. They belong to the stages whose `skipped` rows they replaced, `largedense` and `xlarge`, and are reported there.

## 4b. Per band, as the tables group them

The tables group by node-count range rather than by stage directory, so the dense stages fold in: `mediumdense` lands in n = 50 to 100 and `largedense` in n = 150 to 200. Infeasible instances are excluded from every denominator.

| band | stages | instances | feasible | common valid | rows |
|---|---|---|---|---|---|
| n = 10 to 25 | `small` | 140 | 110 | **110** | 3500 |
| n = 50 to 100 | `medium`, `mediumdense` | 100 | 50 | **50** | 2500 |
| n = 150 to 200 | `large`, `largedense`, `densecomplete` | 100 | 45 | **42** | 2500 |
| n = 250 to 1000 | `xlarge`, `densecomplete` | 20 | 8 | **8** | 308 |

The last two bands grew by the 36 files `densecomplete` added, and neither feasible count nor common valid subset moved, because all 36 are infeasible and infeasible instances are excluded from every denominator. The n = 250 to 1000 band holds 308 rows rather than 500 because its eight new files carry one witness configuration each. Its column heading in `tab:reliability` lost the qualifier `m/n <= 6` for the same reason: the band now contains the dense cells too, and they are excluded on the merits rather than by the band's definition.

## 5. Headline ratios, for quoting

`vs best` is the arm's mean weight over the common valid subset divided by the best arm's on the same instances, so it is a relative ratio and not an approximation ratio. `vs optimum` is against a proven optimum and exists only where the solver ran.

**Small group, n = 10 to 25, against the proven optimum** (50 of the 110 common instances carry a proven optimum, the rest are past `exact_max_n = 18`)

  GHS-MST-Backbone/async 1.142 / Anneal-Trickle/async 1.161 / Anneal-Local/async 1.166 / Anneal-TreeAgg/async 1.166 / GHS-MST-Backbone/sync 1.176 / Anneal-Local/sync 1.179

**n = 50 and n = 100, against the best arm** (50 instances)

  Anneal-Local/async 1.000 / Anneal-TreeAgg/async 1.000 / Anneal-Local/sync 1.009 / Anneal-TreeAgg/sync 1.009 / Anneal-Trickle/async 1.026 / GHS-MST-Backbone/async 1.146

**n = 150 and n = 200, against the best arm** (42 instances)

  Anneal-Local/async 1.000 / Anneal-TreeAgg/async 1.000 / Anneal-Local/sync 1.005 / Anneal-TreeAgg/sync 1.005 / Anneal-Trickle/async 1.035 / GHS-MST-Backbone/async 1.172

**n = 250 to 1000, against the best arm** (8 instances)

  Anneal-Local/async 1.000 / Anneal-TreeAgg/async 1.000 / Anneal-Local/sync 1.006 / Anneal-TreeAgg/sync 1.006 / Anneal-Trickle/async 1.058 / GHS-MST-Backbone/async 1.191

Wider optima come from the exact-compare join, not from these rows: `sweep.py` stops at `exact_max_n = 18`, while `ccvc.central.solve_exact` proves optima for every feasible instance up to n = 50. `paper/tables_full/exact_compare.tex` carries that join over 107 instances on a common basis.

## 6. Where the artefacts are

- rows and per-stage summaries: `results/bb/full_v3/<stage>/rows.csv`, `STAGE_<stage>.md`
- report pipeline: `results/bb/report_full_v3/` (8 tables, 18 figure files)
- manuscript tables: `paper/tables_full/` (nine generators plus `exact_compare.tex`), and `paper/tables/`, refreshed from these rows with each table's hand-set float placement preserved. Only one line of one table changed: the fourth column heading of `tab:reliability`.
- the witness cut: `results/bb/full_v3/densecomplete/CUT_LIST` (what ran) against `jobs.jsonl` (what was planned)
- code provenance: `results/bb/full_v3/FINGERPRINTS.md`
- the aborted first attempt, kept with its cost: `results/bb/full_v3/_aborted/small_mixed_fingerprint/`
