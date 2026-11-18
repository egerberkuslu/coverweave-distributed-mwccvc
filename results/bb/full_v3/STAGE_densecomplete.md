# Stage `densecomplete` — the 36 files no other stage measured

Integrity verdict: **IN PROGRESS**


The other six stages of `full_v3` cover 324 of the benchmark's 360
files. This stage is the remaining 36, and a companion set of fills
under `_topup/densecomplete_fills/` re-measures the 187
(instance, arm, scheduler) pairs an earlier stage wrote as `skipped`
when its wall-clock budget ran out. Both were measured against one
frozen snapshot; `FINGERPRINTS.md` says which code that is and why it
carries a fourth fingerprint.

## What ran

| field | value |
|---|---|
| ns | 150,200,250,500,750,1000 |
| ratios | 8,10 |
| k | 6 |
| max_ms | 22000000 for n<=200, 102000000 above |
| mis_nbrs_max | 64 |
| schedulers | sync,async |
| jobs | 241 new + 19 fill |
| jobs finished | 49/241 new, 19/19 fill |
| seconds (summed over jobs, they ran in parallel) | 345377.3 |
| code fingerprint | 956bf8aa4130 |
| rows | 708 (expected 896) |
| fill rows | 187 (expected 187) |
| instances | 36 (expected 36) |
| arm x scheduler configs | 25 (expected 25) |
| missing / duplicate rows | 188 / 0 |
| false successes (verdict=solved, valid=False) | **0** |
| contradiction rows (verdict_agrees != yes) | 0 |
| blank rows (no status) | 0 |
| every instance has m > nk at k = 6 | yes |

## Why nothing here is scored for quality

Every one of the 36 files has more edges than n·k at k = 6, so no
capacitated cover exists on any of them and the only thing an arm can
do is announce impossibility. That is why they were cut from the first
pass and why filling them in changes no quality number: they enter the
denominator of nothing. What they do change is the coverage claim. The
sweep now reads every file the benchmark ships rather than the 324
that could be scored, so the sentence "324 of 360" becomes "360 of
360" and the reason a cell is empty is a property of the cell rather
than a decision about what to run.

## The fills are a different case and they DO move numbers

Three of the filled instances are `n500_m3000_s1`, `n750_m4500_s1` and
`n1000_m6000_s1`, where m equals n·k exactly rather than exceeding
it. Those are not in the provably-impossible class, so their rows reach
the reliability denominators. Before the fills, 37 of their 75
configurations carried no measurement at all; a table that read a
`skipped` row as a run an arm had failed would have understated those
arms, which is the reading error `SUMMARY_full_v3.md` records and
fixed. The fills replace the absence with a measurement, so the
denominators become real rather than repaired.

## Status inventory

| status | new rows | fill rows |
|---|---|---|
| `infeasible` | 708 | 187 |

## Fingerprints carried

| fingerprint | rows |
|---|---|
| `956bf8aa4130` | 895 |
## The witness cut on the eight largest dense files

The eight files at n >= 250 with m/n in {8, 10} carry one measured
configuration each rather than twenty-five, and the omission is a
decision rather than an accident. Measuring all twenty-five on
those eight costs about 218 core-hours against 86 for everything
else in this stage put together, and buys no comparison: every one
of the eight has m > nk at k = 6, so no cover exists, no arm can
score on them, and the only quantity the missing runs would have
produced is how long each arm takes to announce a fact that one
line of arithmetic already proves.

What IS measured on each of the eight is
`MIS-Connector-Backbone` under the synchronous scheduler, the
cheapest arm in the profile, run to the same budget as everywhere
else. It is a witness run: it establishes that the file was read,
that the protocol reaches a verdict on it, and that the verdict is
impossibility.

**So the coverage claim is 360 of 360 files read, not 25
configurations on each of 360 files.** Any sentence that says the
second thing is wrong. The measured shape is 352 files at 25
configurations plus 8 files at one, and the table below names which
arm ran where.

| file | configurations measured |
|---|---|
| `n1000_m10000_s1.txt` | MIS-Connector-Backbone/sync |
| `n1000_m8000_s1.txt` | MIS-Connector-Backbone/sync |
| `n250_m2000_s1.txt` | MIS-Connector-Backbone/sync |
| `n250_m2500_s1.txt` | MIS-Connector-Backbone/sync |
| `n500_m4000_s1.txt` | MIS-Connector-Backbone/sync |
| `n500_m5000_s1.txt` | MIS-Connector-Backbone/sync |
| `n750_m6000_s1.txt` | MIS-Connector-Backbone/sync |
| `n750_m7500_s1.txt` | MIS-Connector-Backbone/sync |

192 jobs covering 192 configurations on 8 files were left unmeasured by the cut; `CUT_LIST` names every job that ran and `jobs.jsonl` every job that was planned, so the difference is a list rather than a gap.


## Valid share per arm, on scored instances only

Empty by construction for the 36 new instances: no instance among them
admits a cover, so there is no scored denominator and printing a zero
would say twenty-five arms failed on thirty-six problems that have no
solution. The fills are folded back into `largedense` and `xlarge` and
are scored there, in those stages' own tables.


> This file was generated while the sweep was still running.
> Counts above are partial and the verdict is provisional.

