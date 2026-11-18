#!/usr/bin/env python3
"""Build the job list for the densecomplete sweep.

Two kinds of work are missing from `full_v3` and both are enumerated here from
evidence rather than from a remembered list:

- **new** — the 36 dataset files no stage measured, found by diffing the
  dataset directory against every `full_v3/*/rows.csv`. All 36 have m > nk at
  k = 6, so no cover exists on any of them.
- **fill** — the 187 (instance, configuration) pairs that a stage wrote as
  `skipped` when its wall-clock budget ran out. Those rows carry no verdict,
  no slots and no tx, so they are measurements only in the sense that the file
  records they were not taken.

Configurations are packed into jobs under an estimated-seconds cap so that no
job holds more than a few hours of work and a crash cannot cost a whole
instance. The estimate comes from a measured per-arm profile at
`n200_m2000_s4` scaled per cell against the times the earlier stages recorded;
it is used only to size and order jobs, never reported as a result.

ORDER IS A DELIVERY DECISION, not a scheduling one. Running the longest jobs
first would finish the whole sweep soonest, but it leaves nothing foldable for
hours. The queue is ordered instead so that each milestone is a complete,
foldable cut on its own:

1. the 37 `xlarge` fills, because those three instances have m = nk and their
   rows reach the reliability denominators, so they are the only work here
   that can move a published number;
2. the 150 `largedense` fills, which close out the last `skipped` rows;
3. the 28 never-run files at n = 150 and 200, each instance whole, so the
   count of covered files rises one file at a time rather than in a lump;
4. the 8 never-run files at n = 250 and above, last and one configuration per
   job, synchronous before asynchronous and the cheap arms before DFS, so that
   stopping here costs a known list of configurations rather than a partial
   instance nobody can describe.

Rows already measured by an earlier round are read out of `parts/` and excluded,
so a rebuild never re-measures work that survived.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys

ROOT = "/home/ege/Desktop/MDS_SKYFABRIC"
FV3 = f"{ROOT}/results/bb/full_v3"
DATASET = f"{ROOT}/data/DagdevirenDataset"
STAGE = f"{FV3}/densecomplete"
TOPUP = f"{FV3}/_topup/densecomplete_fills"
TARGET_S = 9000.0          # per-job estimate cap; a single config may exceed it
K = 6
MIS_NBRS_MAX = 64

ARMS = ["MIS-Connector-Backbone", "MIS-Connector-TreeAgg",
        "DFS-Spanning-Backbone", "GHS-MST-Backbone", "WuLi-Dominating-Exact",
        "WuLi-Dominating-Bloom", "WuLi-Dominating-Chunked", "Anneal-Local",
        "Anneal-TreeAgg", "Anneal-Trickle", "Greedy-Degree-Backbone",
        "Greedy-Ratio-Backbone", "Greedy-Weight-Backbone"]
NO_SYNC = {"Anneal-Trickle"}

# measured seconds per configuration on n200_m2000_s4 (densecomplete log, 2026-09-18)
PROFILE = {
    "MIS-Connector-Backbone": (244.7, 369.8),
    "MIS-Connector-TreeAgg": (248.3, 403.7),
    "DFS-Spanning-Backbone": (943.7, 1001.1),
    "GHS-MST-Backbone": (307.5, 468.2),
    "WuLi-Dominating-Exact": (253.7, 331.9),
    "WuLi-Dominating-Bloom": (385.5, 444.9),
    "WuLi-Dominating-Chunked": (586.5, 853.9),
    "Anneal-Local": (679.9, 585.5),
    "Anneal-TreeAgg": (664.3, 599.4),
    "Anneal-Trickle": (0.0, 508.0),
    "Greedy-Degree-Backbone": (257.5, 380.7),
    "Greedy-Ratio-Backbone": (256.4, 387.5),
    "Greedy-Weight-Backbone": (266.3, 384.3),
}

# (sync, async) scale against that profile, per cell, fitted to measured rows
SCALE = {
    (150, 1200): (0.36, 0.36), (150, 1500): (0.48, 0.50),
    (200, 1600): (0.76, 0.78), (200, 2000): (1.00, 1.00),
    (250, 2000): (1.25, 1.35), (250, 2500): (1.65, 1.85),
    (500, 3000): (0.50, 1.00), (500, 4000): (3.60, 5.00),
    (500, 5000): (4.70, 7.00), (750, 4500): (0.90, 1.70),
    (750, 6000): (6.80, 11.50), (750, 7500): (8.80, 15.70),
    (1000, 6000): (1.60, 3.00), (1000, 8000): (9.00, 17.00),
    (1000, 10000): (10.90, 22.00),
}

NAME = re.compile(r"^n(\d+)_m(\d+)_s(\d+)\.txt$")


def arm_cost_rank(arm):
    """Cheap arms first, DFS last, by the measured profile's synchronous cost."""
    return PROFILE[arm][0] or PROFILE[arm][1]


def already_measured():
    """(instance, arm, scheduler) triples an earlier round already wrote."""
    done = set()
    for p in (glob.glob(f"{STAGE}/parts/*.csv") + glob.glob(f"{TOPUP}/parts/*.csv")):
        for r in csv.DictReader(open(p)):
            done.add((r["instance"], r["variant"], r["scheduler"]))
    return done


def est(n, m, arm, sch):
    s = SCALE[(n, m)][0 if sch == "sync" else 1]
    return PROFILE[arm][0 if sch == "sync" else 1] * s


def pack(configs, n, m):
    """Greedy bin packing, longest first, under TARGET_S."""
    items = sorted(configs, key=lambda c: -est(n, m, *c))
    bins = []
    for c in items:
        e = est(n, m, *c)
        for b in bins:
            if b[0] + e <= TARGET_S:
                b[0] += e
                b[1].append(c)
                break
        else:
            bins.append([e, [c]])
    return bins


def main():
    files = {f for f in os.listdir(DATASET) if NAME.match(f)}
    covered, skipped = set(), {}
    for p in sorted(glob.glob(f"{FV3}/*/rows.csv")):
        stage = p.split("/")[-2]
        for r in csv.DictReader(open(p)):
            covered.add(r["instance"])
            if r["status"] == "skipped":
                skipped.setdefault((stage, r["instance"]), []).append(
                    (r["variant"], r["scheduler"]))
    missing = sorted(files - covered,
                     key=lambda f: tuple(int(x) for x in NAME.match(f).groups()))
    print(f"dataset {len(files)} files, {len(covered)} covered, "
          f"{len(missing)} never run, "
          f"{sum(len(v) for v in skipped.values())} skipped pairs")

    done = already_measured()
    if done:
        print(f"{len(done)} runs already measured by an earlier round; excluded")

    jobs = []
    # --- milestones 1 and 2: the fills, xlarge before largedense ---
    for (stage, f), cfgs in sorted(skipped.items(),
                                   key=lambda kv: (kv[0][0] != "xlarge", kv[0])):
        n, m, seed = (int(x) for x in NAME.match(f).groups())
        group = "medium" if n <= 200 else "large"
        cs = [c for c in sorted(cfgs) if (f, c[0], c[1]) not in done]
        if not cs:
            continue
        rank = 0 if stage == "xlarge" else 1
        for bi, (e, bucket) in enumerate(pack(cs, n, m)):
            jid = f"fill_{stage}_n{n}_m{m}_s{seed}_{bi:02d}"
            jobs.append(dict(id=jid, kind="fill", stage=stage, instance=f,
                             n=n, m=m, ratio=m // n, seed=seed, group=group,
                             configs=[list(c) for c in bucket],
                             k=K, mis_nbrs_max=MIS_NBRS_MAX,
                             max_ms=22_000_000 if n <= 200 else 102_000_000,
                             est=round(e, 1), milestone=rank,
                             out=f"{TOPUP}/parts/{jid}.csv"))

    # --- milestones 3 and 4: the never-run files, n <= 200 before the rest ---
    for f in missing:
        n, m, seed = (int(x) for x in NAME.match(f).groups())
        group = "medium" if n <= 200 else "large"
        cfgs = [(a, s_) for a in ARMS for s_ in ("sync", "async")
                if not (a in NO_SYNC and s_ == "sync")
                and (f, a, s_) not in done]
        if not cfgs:
            continue
        if n <= 200:
            # whole instance in as few jobs as the cap allows: an instance is
            # foldable only once all 25 of its configurations exist
            buckets = pack(cfgs, n, m)
            rank = 2
        else:
            # one configuration per job, synchronous first, DFS last, so the
            # cut line is a list of configurations rather than half an instance
            cfgs.sort(key=lambda c: (c[0] != "MIS-Connector-Backbone" or
                                     c[1] != "sync",
                                     c[1] != "sync", arm_cost_rank(c[0])))
            buckets = [(est(n, m, *c), [c]) for c in cfgs]
            rank = 3
        for bi, (e, bucket) in enumerate(buckets):
            jid = f"new_n{n}_m{m}_s{seed}_{bi:02d}"
            jobs.append(dict(id=jid, kind="new", instance=f, n=n, m=m,
                             ratio=m // n, seed=seed, group=group,
                             configs=[list(c) for c in bucket],
                             k=K, mis_nbrs_max=MIS_NBRS_MAX,
                             max_ms=22_000_000 if n <= 200 else 102_000_000,
                             est=round(e, 1), milestone=rank, cfg_rank=bi,
                             out=f"{STAGE}/parts/{jid}.csv"))

    # Milestone 4 goes configuration-major rather than instance-major: every
    # one of the eight files gets its cheapest synchronous arm before any file
    # gets its second, so a cut there is "these arms on all eight" instead of
    # "some arms on some files". The witness configuration is first of all.
    jobs.sort(key=lambda j: (j["milestone"],
                             j.get("cfg_rank", 0) if j["milestone"] == 3 else 0,
                             j["n"], j["m"], j["seed"], -j["est"]))
    with open(f"{STAGE}/jobs.jsonl", "w", encoding="utf-8") as fh:
        for j in jobs:
            fh.write(json.dumps(j) + "\n")

    names = {0: "1  xlarge fills (m = nk, these move numbers)",
             1: "2  largedense fills", 3: "4  n >= 250 never-run, one config per job",
             2: "3  n = 150 and 200 never-run, whole instances"}
    cum = 0.0
    print()
    for r in (0, 1, 2, 3):
        sel = [j for j in jobs if j["milestone"] == r]
        e = sum(j["est"] for j in sel)
        cum += e
        print(f"milestone {names[r]}: {len(sel)} jobs, "
              f"{sum(len(j['configs']) for j in sel)} runs, "
              f"{e/3600:.0f} core-h, cumulative {cum/3600:.0f} core-h "
              f"-> {cum/3600/13:.1f} h on 13 workers")
    print(f"\ntotal {len(jobs)} jobs, {sum(len(j['configs']) for j in jobs)} runs, "
          f"{cum/3600:.0f} core-hours, longest job "
          f"{max(j['est'] for j in jobs)/3600:.1f} h")

    witness = [(f, est(int(NAME.match(f).group(1)), int(NAME.match(f).group(2)),
                       "MIS-Connector-Backbone", "sync")) for f in missing
               if int(NAME.match(f).group(1)) >= 250]
    print(f"\nwitness-only cut for the {len(witness)} big files "
          f"(MIS-Connector-Backbone/sync alone): "
          f"{sum(e for _, e in witness)/3600:.1f} core-hours, "
          f"longest {max(e for _, e in witness)/3600:.1f} h")
    for f, e in witness:
        print(f"    {f:22s} {e/3600:5.2f} h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
