# Which code measured which row, and why there may be two answers

`sweep.code_fingerprint()` hashes the modification time and size of every
non-test module in `ccvc/bb` and is stamped on each row **as that row is
measured**, not once when a sweep starts. It is deliberately coarse: it answers
"did the code move under this run" cheaply and exactly, and it moves even when
the file that changed cannot affect a measured number.

## Why the sweep runs against a snapshot

The first attempt at the small stage ran from 00:18 to 00:26 on 2026-09-18
against the live repository while other agents were editing it. Three files
changed underneath it: `v4_mst.py` at 00:17:37, `paper_tables.py` at 00:22:50
and `exact_compare.py` at 00:25:53. The fingerprint moved from
`3fcfb592edf0` to `8d26f7c120f2` mid-run, so that CSV would have carried two
code versions with nothing but the column to say so. The run was stopped and
its partial output kept at `_aborted/small_mixed_fingerprint/`.

Every stage now runs against a snapshot of `ccvc/` taken at 00:27 on
2026-09-18 and held in the session scratchpad. Nothing in the live tree can
move it.

| | |
|---|---|
| base fingerprint | `798b4393cb4f` |
| content hash of the snapshot's non-test sources | `df5c797953b35d2d` |
| same hash over the live tree at snapshot time | `df5c797953b35d2d` (identical) |
| snapshot `v4_mst.py` sha256 | `cd01862d7c302c5117b3fb002f2e5173067dee818755e0e96c0c84de941eef1c` |

The content hash is the durable identifier: the fingerprint is built from
modification times and would differ after any copy, while the content hash
would not.

## Why GHS-MST-Backbone is measured separately

The `v4_mst.py` edit at 00:17:37 is ghs-debug's in-progress fix for the
`n15_m30_s2` asynchronous truncation and was not final. Every stage therefore
runs in two passes:

- **pass `main`** — the twelve arms that are not GHS-MST-Backbone, twenty-three
  arm and scheduler configurations, measured at the base fingerprint above.
- **pass `ghs`** — the two GHS-MST-Backbone configurations, measured only after
  ghs-debug declares `v4_mst.py` final. If the final file is byte-identical to
  the snapshot, nothing is copied, no modification time moves and the whole
  stage carries one fingerprint. If it differs, the file is copied into the
  snapshot, the new fingerprint is recorded in the table below and the GHS rows
  carry it while the other twelve arms keep the base value.

The merge step enforces exactly this shape. It accepts at most two
fingerprints, and two only when the second belongs to GHS-MST-Backbone alone;
any other split means a code change landed under a running stage and the merge
aborts rather than writing the file.

## Fingerprints in the published rows

| pass | arms | fingerprint | note |
|---|---|---|---|
| `main` | twelve arms, twenty-three configurations | `798b4393cb4f` | snapshot of 2026-09-18 00:27 |
| `ghs` | GHS-MST-Backbone, two configurations | pending | filled in when ghs-debug declares the file final |

## Relation to the published v2 sweeps

`sweep_small_full_k6_clean_v2`, `sweep_medium_n50_k6_join_v2` and
`sweep_medium_n100_fixed_v2` were measured at `26230cea50b4`, and
`v4_mst.py` was edited three minutes after the last of them finished. The
`full_v3` rows are therefore a replacement set, not rows to append to the v2
tables.

## GHS pass: the snapshot was reconciled with ghs-debug's final file

ghs-debug declared `v4_mst.py` final at 2026-09-18 00:34:13 +0300 with sha256
`0973adc5a90d3036f6bed19b38994dab29f0342f4b36f27d26683d592d942226`, 58907 bytes. The 00:27
snapshot held `cd01862d7c302c5117b3fb002f2e5173067dee818755e0e96c0c84de941eef1c`,
58395 bytes, so the two differ in bytes and the file was copied in before the
GHS pass ran.

**They are the same code.** Comparing the two abstract syntax trees with
docstrings stripped gives `True`: the difference is source text only.
ghs-debug's first edit tripped the global black hook and reformatted the whole
module, and the reformatting was undone at 00:34:13. This was checked here
independently rather than taken on report, because "behaviourally identical" is
exactly the claim that, if wrong, would be invisible in every table built on
these rows.

The fingerprint still moves, because it is built from modification times and
sizes rather than from content, so the GHS rows carry a different value from the
other twelve arms even though the code that produced them is unchanged.

| pass | arms | fingerprint |
|---|---|---|
| `main` | twelve arms, twenty-three configurations | `798b4393cb4f` |
| `ghs` | GHS-MST-Backbone, two configurations | `bebb0f917410` |

The copy was made after every main pass finished and before the first GHS pass
started, so no stage has a non-GHS arm split across the two values.

## After the re-runs: what each fingerprint means now

The wall-clock budget cut 284 rows on the first pass. They were written as
`skipped` rather than dropped, which is the right record but not a measurement:
a skipped row carries no verdict, no slots and no tx. Three cells were therefore
re-run, and the re-runs happened after `v4_mst.py` was reconciled, so they are
measured against the snapshot as it stands, `bebb0f917410`.

That changes what the two values mean. They no longer separate twelve arms from
one; they separate a first measurement from a later one.

| fingerprint | what it marks |
|---|---|
| `798b4393cb4f` | measured on the first pass, the twelve arms that are not GHS-MST-Backbone |
| `bebb0f917410` | GHS-MST-Backbone everywhere, plus any row that was `skipped` on the first pass and had to be re-run |

**A row may carry `bebb0f917410` for one of exactly two reasons**: it is a
GHS-MST-Backbone row, or the same instance and configuration was written
`skipped` on the first pass. The fold step enforces that and refuses to write
the file otherwise, so a run cannot be quietly re-rolled because somebody
disliked its result. Every row that ran the first time keeps its original
measurement even where a newer one exists.

There is no third fingerprint. The re-runs use the same snapshot as the GHS
pass, so their rows carry the value the GHS rows already carry.

### The three cells that were re-run

- **`xlarge`** and **`largedense`** were re-run in full. Their skipped rows were
  spread across arms and instances, and one shard per instance is what they
  needed; the earlier six and ten shard splits starved the expensive cells.
- **The n = 100, m/n = 10 cell** held all 67 of the medium stage's skipped rows.
  It is now its own stage, `mediumdense`, measured end to end. Its first-pass
  rows were moved out of `medium/rows.csv` to
  `_archive/medium_n100_m1000_first_pass_rows.csv`, so the same ten instances
  do not appear twice with nothing but a row count to say which is which.
  `medium` is now exactly the ninety instances measured end to end on the first
  pass.

## The third value: annealing re-measured after §107

fs-debug found that `anneal.py`'s freeze path skipped Phase 3, so the §105
key-election repair never ran. The defect is in a path all three annealing arms
share, so **all three are re-measured, not only the one whose false successes
exposed it**. Replacing Anneal-Trickle alone would leave Anneal-Local and
Anneal-TreeAgg in the tables measured against code known to be wrong, with
nothing in the file to mark them.

A third snapshot was taken for it, in its own directory. The first snapshot
could not be edited: three sweeps were running against it, and the fingerprint
is stamped per row as each row is measured, so changing that tree would have
split arms across versions inside jobs already in flight.

| | |
|---|---|
| fingerprint | `be8a9f9c1e43` |
| `anneal.py` sha256 | `69ea06ee9d7a4e8c69fccba04a8d21bb23e31a0d716ed0c763d768c3f4860425` |
| content hash of the snapshot's non-test sources | `8b1870eb69fe0155` |
| taken | 2026-09-18, after the live tree went 120 s with no change under `ccvc/bb` |

The quiet check is not ceremony. The whole reason these snapshots exist is that
the live tree moved under a running sweep at 00:22; copying a tree somebody was
still editing would have reproduced that fault one level down. The snapshot
script watched all 36 non-test modules and reset its clock on any change.

### The three values and what each marks

| fingerprint | what it marks |
|---|---|
| `798b4393cb4f` | first measurement, the nine arms that are neither GHS-MST-Backbone nor annealing |
| `bebb0f917410` | GHS-MST-Backbone everywhere, plus any row the budget skipped on the first pass and had to be re-run |
| `be8a9f9c1e43` | Anneal-Local, Anneal-TreeAgg and Anneal-Trickle, re-measured after the §107 fix |

The fold refuses to write a stage whose rows do not fit this shape: no
non-annealing arm may carry `be8a9f9c1e43`, and no row may carry
`bebb0f917410` unless it is GHS or was skipped first time. The rows each
re-measurement replaced are archived beside the stage rather than discarded,
because the difference between the old rows and the new ones is the evidence
that a fix did what it claims.

## `largedense` was not re-run, and its annealing rows are pre-§107

Two re-measurements skip that stage on purpose, and the reason is the same both
times: **every instance in it has m > nk at k = 6**, so no cover exists, each
arm's only job there is to announce impossibility, and no table reads those
rows for quality.

- Its 150 budget-skipped rows stay `skipped`. They are recorded as not measured
  rather than filled in.
- Its annealing rows keep their pre-§107 measurement and carry
  `798b4393cb4f`, not `be8a9f9c1e43`. The §107 defect is a freeze path that
  skipped Phase 3 and so lost the key-election repair; its visible symptom is a
  false success, a run claiming a valid cover that the validator rejects. On an
  instance with no cover at all there is nothing to claim, and the stage's rows
  are `infeasible` throughout with zero false successes.

The cost of re-running it was two to four hours for numbers nothing quotes, and
that time would have come out of the annealing re-measurement that several
tables do read. If a later reader wants those rows on current code, the cut is
recorded here rather than hidden, and the cell is one command to re-run.

## The fourth value: `densecomplete`, and why a reboot forced a new snapshot

The machine rebooted at about 22:20 on 2026-09-18 with the completeness sweep
in flight. The reboot cleared `/tmp`, and the `be8a9f9c1e43` snapshot lived
there, together with the launcher that drove it. Neither survived. The rows
that snapshot had already written did survive, because they were written under
`results/`, and they are kept.

So the remaining work — the 36 files no stage had measured, and the 187
`skipped` pairs — is measured against a new snapshot, and it carries a fourth
fingerprint. The honest question is whether that fourth value marks different
code or only a different copy.

| | |
|---|---|
| fingerprint | `956bf8aa4130` |
| snapshot | `results/bb/full_v3/_snapshot_densecomplete/` (under `results/`, not `/tmp`, so the next reboot cannot take it) |
| taken | 2026-09-18 22:35 +0300, after the live tree went 120 s with no change under `ccvc/` |
| `anneal.py` sha256 | `69ea06ee9d7a4e8c69fccba04a8d21bb23e31a0d716ed0c763d768c3f4860425` |
| `v4_mst.py` sha256 | `0973adc5a90d3036f6bed19b38994dab29f0342f4b36f27d26683d592d942226` |
| content hash of the 23 modules the sweep imports | `e88f70c8faa710ee` |

**The two hashes above are the ones this file already recorded for
`be8a9f9c1e43` and for ghs-debug's final `v4_mst.py`, unchanged.** The §107
annealing fix and the GHS fix are therefore byte-identical in the new snapshot
to the code that measured the rows already in the file.

### What did change, and why it cannot reach a measured number

`code_fingerprint()` hashes modification time and size over every non-test
module in `ccvc/bb`, so a copy moves it even when nothing was edited, and an
edit to any module in that directory moves it even when the sweep never imports
that module. Both happened here.

Five modules were edited after the `be8a9f9c1e43` snapshot was taken:
`exact_compare.py` at 09:44, `compare_figures.py` at 10:02, `paper_tables.py`
at 10:18, `report_pipeline.py` at 15:53 and `reliability_figure.py` at 15:56.
Every one of them builds tables, figures or comparisons *from* rows. None of
them is on the path that produces a row. That was checked rather than assumed:
a full 25-configuration run on `n25_m50_s1` was executed against the new
snapshot and the modules Python actually loaded were read back out of
`sys.modules`. There are 23 of them, listed by hash in the stage report, and
none of the five is among them. The newest modification time on any of the 23
is `anneal.py` at 08:54:34, which is the §107 fix itself.

The content hash above is over exactly those 23 modules, as
`sha256("name:sha256(bytes);" for each, sorted by path)`, truncated to sixteen
hex characters. **It is not comparable to the `8b1870eb69fe0155` recorded
earlier in this file**, because that value's recipe was not written down and
could not be reproduced: twenty-five plausible definitions over five candidate
file sets were tried against the live tree and none returned it. Rather than
publish a number that looks like a match and is not one, the comparison that
carries the claim here is the per-file sha256 of the two modules the earlier
snapshots did record, and those agree exactly.

### Which rows may carry it

A row may carry `956bf8aa4130` for one of exactly two reasons.

- **Its instance has m > nk at k = 6.** All 36 newly measured files are in this
  class. No cover exists on any of them, every arm's only job is to announce
  impossibility, and no table reads them for quality. Nothing can be re-rolled
  in anybody's favour on an instance with no solution.
- **That exact (instance, arm, scheduler) was written `skipped`.** These are
  the 187 pairs a stage recorded as not measured when its budget ran out. They
  are listed, as they stood before any fill was written, in
  `_topup/densecomplete_fills/skipped_pairs.json`, and the rows they replace are
  archived at `_archive/largedense_before_densecomplete_fills_rows.csv` and
  `_archive/xlarge_before_densecomplete_fills_rows.csv`.

`paper/tools/check_paper.py` enforces both conditions row by row rather than
counting distinct values, and fails if the manifest is missing, so the licence
cannot be widened by deleting the record of what it covers.

### One thing the fills change that the 36 files do not

Three filled instances — `n500_m3000_s1`, `n750_m4500_s1` and
`n1000_m6000_s1` — have m equal to n·k rather than greater than it. They are
scored instances, their fills reach the reliability denominators, and 37 of
their 75 configurations previously held no measurement at all. Unlike the 36
new files, these rows can move a published number, and the direction is toward
a denominator that was measured rather than inferred.

### `largedense` is now re-run after all, in one narrow sense

An earlier section here records that `largedense` was left alone on purpose:
its 150 budget-skipped rows stayed `skipped` and its annealing rows kept their
pre-§107 measurement. The first half of that is now undone — the 150 skipped
rows are filled — and the second half still stands. The annealing rows in that
stage are not re-measured, for the reason given there: the §107 defect shows
itself as a false success, and on an instance with no cover there is nothing to
claim falsely. So `largedense` will hold rows at three values, and the two
reasons are different and both recorded.

### The witness cut: eight files carry one arm, not twenty-five

The completeness sweep was cut on purpose before it finished, and the cut is
recorded here because a reader counting rows will otherwise find eight files
that look half-measured.

Measuring all twenty-five configurations on the eight files at n >= 250 with
m/n in {8, 10} costs about 218 core-hours. Everything else in the stage — the
187 fills and the 28 files at n = 150 and 200, whole — costs 86. The 218 buys
no comparison. Every one of the eight has m > nk at k = 6, so no cover exists,
no arm can score on them, and the twenty-four unmeasured configurations per
file would have produced exactly one quantity: how long each arm takes to
announce an impossibility that one line of arithmetic already proves.

Each of the eight therefore carries one measured configuration,
`MIS-Connector-Backbone` under the synchronous scheduler, run to the same
budget and against the same snapshot as everything else. It is a witness run.
It establishes that the file was read, that the protocol reaches a verdict on
it, and that the verdict is impossibility.

**The coverage claim this supports is "360 of 360 files read", not "25
configurations on each of 360 files".** The measured shape is 352 files at 25
configurations plus 8 files at one, 8808 rows against the 9000 a complete
sweep would hold. `densecomplete/CUT_LIST` names every job that ran and
`densecomplete/jobs.jsonl` every job that was planned, so what was left out is
a list somebody can run later rather than a gap nobody can describe.

The cut changes nothing about which rows may carry `956bf8aa4130`. The eight
files are in the m > nk class, which is the first of the two conditions above,
and `check_paper.py` checks that condition per row regardless of how many rows
a file has.
