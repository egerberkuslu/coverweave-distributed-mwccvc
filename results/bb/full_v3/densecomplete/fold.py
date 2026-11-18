#!/usr/bin/env python3
"""Fold the densecomplete parts into `full_v3`, refusing anything irregular.

Two destinations, two different rules.

- The 36 newly measured files become a stage of their own,
  `densecomplete/rows.csv`. Nothing is replaced: no other stage holds a row for
  any of those instances.
- The 187 fills replace rows that a stage wrote as `skipped`. A fill may land
  ONLY on a pair that `skipped_pairs.json` records, and only on a row whose
  status in the target stage is still `skipped`. Any other overlap means a row
  that actually ran is about to be overwritten, and the fold aborts instead.

Nothing is written until every check passes, so a refusal leaves the previous
state intact.

`--partial` folds a cut taken before the sweep ends. It drops the "every job
finished" requirement and the "every planned run has a row" requirement, and
instead reports exactly which instances are whole and which are not. A
partially measured instance is still written, because a row that exists is a
measurement whatever else is missing; what must not happen is a table quietly
averaging over an instance whose arm set is incomplete, so the fold prints the
incomplete instances by name and the stage report carries the list.
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import shutil
import sys

ROOT = "/home/ege/Desktop/MDS_SKYFABRIC"
FV3 = f"{ROOT}/results/bb/full_v3"
STAGE = f"{FV3}/densecomplete"
FILLS = f"{FV3}/_topup/densecomplete_fills"
DENSECOMPLETE_FP = "956bf8aa4130"
SANCTIONED = {"798b4393cb4f", "bebb0f917410", "be8a9f9c1e43", DENSECOMPLETE_FP}

errs: list[str] = []


def bad(msg):
    errs.append(msg)
    print("REFUSE:", msg)


def T(x):
    return str(x).strip().lower() in ("true", "1", "yes", "evet")


def read(pattern):
    rows, fields = [], None
    for p in sorted(glob.glob(pattern)):
        with open(p, newline="", encoding="utf-8") as fh:
            rd = csv.DictReader(fh)
            fields = fields or rd.fieldnames
            rows += list(rd)
    return rows, fields


def key(r):
    return (r["instance"], r["variant"], r["scheduler"])


def main(apply_it, partial=False):
    jobs = [json.loads(l) for l in open(f"{STAGE}/jobs.jsonl")]
    unfinished = [j for j in jobs if not os.path.exists(j["out"] + ".done")]
    if unfinished and not partial:
        for j in unfinished[:5]:
            bad(f"job {j['id']} is not finished")
        if len(unfinished) > 5:
            bad(f"...and {len(unfinished) - 5} more unfinished jobs; use "
                f"--partial to fold a cut on purpose")
    new, fields = read(f"{STAGE}/parts/*.csv")
    fills, _ = read(f"{FILLS}/parts/*.csv")

    want_new = {(j["instance"], tuple(c)) for j in jobs if j["kind"] == "new"
                for c in j["configs"]}
    want_fill = {(j["instance"], tuple(c)) for j in jobs if j["kind"] == "fill"
                 for c in j["configs"]}
    got_new = {(r["instance"], (r["variant"], r["scheduler"])) for r in new}
    got_fill = {(r["instance"], (r["variant"], r["scheduler"])) for r in fills}
    if want_new - got_new and not partial:
        bad(f"{len(want_new - got_new)} planned new runs have no row")
    if want_fill - got_fill and not partial:
        bad(f"{len(want_fill - got_fill)} planned fills have no row")
    if partial:
        per = collections.Counter(r["instance"] for r in new)
        whole = sorted(i for i, c in per.items() if c == 25)
        part = sorted((i, c) for i, c in per.items() if c != 25)
        print(f"partial fold: {len(whole)} instances complete at 25 "
              f"configurations, {len(part)} partial, "
              f"{len(want_new - got_new)} new runs and "
              f"{len(want_fill - got_fill)} fills still missing")
        for i, c in part:
            print(f"    partial: {i} has {c}/25")
    for name, rows in (("new", new), ("fill", fills)):
        c = collections.Counter(key(r) for r in rows)
        d = [k for k, v in c.items() if v > 1]
        if d:
            bad(f"{name}: {len(d)} duplicated (instance, arm, scheduler), "
                f"e.g. {d[:3]}")
        blank = [r for r in rows if not r["status"]]
        if blank:
            bad(f"{name}: {len(blank)} blank rows")
        fs = [r for r in rows if r["verdict"] == "solved" and not T(r["valid"])]
        if fs:
            bad(f"{name}: {len(fs)} false successes")
        sk = [r for r in rows if r["status"] == "skipped"]
        if sk:
            bad(f"{name}: {len(sk)} rows are themselves skipped")
        fp = {r["code_fingerprint"] for r in rows}
        if rows and fp != {DENSECOMPLETE_FP}:
            bad(f"{name}: fingerprints {sorted(fp)}, expected only "
                f"{DENSECOMPLETE_FP}")
    for r in new:
        if int(r["m"]) <= int(r["n"]) * int(r["k"]):  # noqa: SIM102
            bad(f"new row {key(r)} has m <= nk; the new-instance set is supposed "
                f"to be provably infeasible throughout")
            break

    sp = json.load(open(f"{FILLS}/skipped_pairs.json", encoding="utf-8"))
    allowed = {stage: {tuple(x) for x in pairs}
               for stage, pairs in sp["pairs"].items()}
    by_stage = collections.defaultdict(list)
    for r in fills:
        stages = [s for s, ks in allowed.items() if key(r) in ks]
        if len(stages) != 1:
            bad(f"fill {key(r)} matches {len(stages)} stages in "
                f"skipped_pairs.json; it may not be written")
            continue
        by_stage[stages[0]].append(r)

    # touching only rows that are still `skipped` in the target stage
    updated = {}
    for stage, rows in sorted(by_stage.items()):
        path = f"{FV3}/{stage}/rows.csv"
        with open(path, newline="", encoding="utf-8") as fh:
            rd = csv.DictReader(fh)
            target = list(rd)
            tfields = rd.fieldnames
        index = {key(r): i for i, r in enumerate(target)}
        for r in rows:
            i = index.get(key(r))
            if i is None:
                bad(f"{stage}: fill {key(r)} has no row to replace")
                continue
            if target[i]["status"] != "skipped":
                bad(f"{stage}: fill {key(r)} would overwrite a row with status "
                    f"{target[i]['status']!r}, not a skipped one")
                continue
            target[i] = {k: r.get(k, "") for k in tfields}
        left = sum(1 for r in target if r["status"] == "skipped")
        print(f"  {stage}: {len(rows)} fills applied, {left} skipped rows left")
        updated[stage] = (path, target, tfields)

    if errs:
        print(f"\n{len(errs)} refusals; nothing written")
        return 1
    if not apply_it:
        print("\nall checks pass; re-run with --apply to write")
        return 0

    out = f"{STAGE}/rows.csv"
    tmp = out + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in sorted(new, key=lambda r: (int(r["n"]), int(r["m"]),
                                            int(r["seed"]), r["variant"],
                                            r["scheduler"])):
            w.writerow(r)
    os.replace(tmp, out)
    print(f"wrote {out}: {len(new)} rows")
    for stage, (path, target, tfields) in updated.items():
        tmp = path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=tfields)
            w.writeheader()
            for r in target:
                w.writerow(r)
        os.replace(tmp, path)
        print(f"wrote {path}: {len(target)} rows")

    fp = collections.Counter()
    insts, tot, fs, sk = set(), 0, 0, 0
    for p in sorted(glob.glob(f"{FV3}/*/rows.csv")):
        for r in csv.DictReader(open(p)):
            tot += 1
            insts.add(r["instance"])
            fp[r["code_fingerprint"]] += 1
            fs += r["verdict"] == "solved" and not T(r["valid"])
            sk += r["status"] == "skipped"
    print(f"\nfull_v3 now: {tot} rows, {len(insts)} instances, "
          f"{fs} false successes, {sk} skipped rows")
    print("fingerprints:", dict(fp))
    if set(fp) - SANCTIONED:
        print("WARNING unsanctioned fingerprint:", set(fp) - SANCTIONED)
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv, "--partial" in sys.argv))
