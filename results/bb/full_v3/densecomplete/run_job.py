#!/usr/bin/env python3
"""Run ONE job of the densecomplete sweep against the frozen code snapshot.

A job is one dataset instance plus a named list of (arm, scheduler)
configurations. The row for every configuration is appended to the job's own
CSV the moment it is measured, so a crash or a reboot costs at most one run
instead of the whole job. Re-running a job skips the configurations its CSV
already holds, so the pool is restartable.

The snapshot is the only code this ever imports: the launcher sets the working
directory to the snapshot root, so `ccvc.bb.sweep` resolves there and the
`code_fingerprint` column records the snapshot, not the live tree.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

DATASET = os.environ.get("MWCCVC_DATASET") or ""


def load_done(path):
    if not os.path.exists(path):
        return set(), []
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {(r["variant"], r["scheduler"]) for r in rows}, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--id", required=True)
    a = ap.parse_args()

    with open(a.jobs, encoding="utf-8") as fh:
        job = next(json.loads(l) for l in fh if json.loads(l)["id"] == a.id)

    # A cut is a decision about what to measure, so it is a file rather than a
    # kill signal: a job outside the cut exits here, having measured nothing and
    # written no `.done` marker, and `fold.py --partial` then reports it as
    # missing instead of mistaking an early exit for a finished job.
    cut = os.path.join(os.path.dirname(os.path.abspath(a.jobs)), "CUT_LIST")
    if os.path.exists(cut):
        allowed = {l.strip() for l in open(cut, encoding="utf-8")
                   if l.strip() and not l.startswith("#")}
        if a.id not in allowed:
            print(f"job {a.id}: outside the cut in CUT_LIST, not measured",
                  flush=True)
            return 0

    from ccvc.bb import matrix
    from ccvc.bb import sweep as S

    snap = os.environ.get("BB_SNAPSHOT") or ""
    if not snap or not os.path.realpath(S.__file__).startswith(
            os.path.realpath(snap) + os.sep):
        print(f"ABORT: sweep.py resolved to {S.__file__}, not under the "
              f"snapshot {snap!r}; the run would measure the live tree",
              file=sys.stderr)
        return 2
    if not DATASET or not os.path.isdir(DATASET):
        print(f"ABORT: MWCCVC_DATASET={DATASET!r} is not a directory",
              file=sys.stderr)
        return 2

    out = job["out"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    done, kept = load_done(out)
    todo = [tuple(c) for c in job["configs"] if tuple(c) not in done]
    print(f"job {a.id}: {job['instance']} {len(job['configs'])} configs, "
          f"{len(done)} already measured, {len(todo)} to run, "
          f"max_ms={job['max_ms']} fingerprint={S.code_fingerprint()}", flush=True)
    if not todo:
        open(out + ".done", "w").close()
        print("job already complete", flush=True)
        return 0

    cell = matrix.Cell(job["group"], job["n"], job["ratio"])
    path = os.path.join(DATASET, job["instance"])
    raw_w, raw_e = matrix.load_instance(path)
    w, e, adapt = S.prepare(raw_w, raw_e, weight_scale=S.DEFAULT_WEIGHT_SCALE)
    seeds_in_cell = len(matrix.seeds_available(cell, DATASET))
    inst = S.Instance("dataset", cell, job["seed"], path, tuple(e), w,
                      seeds_in_cell, adapt)
    if len(e) != job["m"] or len(w) != job["n"]:
        print(f"ABORT: loaded n={len(w)} m={len(e)}, expected "
              f"n={job['n']} m={job['m']}", file=sys.stderr)
        return 3

    specs = {s.name: s for s in S.discover()}
    opts = S.SweepOptions(k=job["k"], loss=0.0, max_ms=job["max_ms"],
                          mis_nbrs_max=job["mis_nbrs_max"], time_budget_s=None)

    fields = list(S.CSV_FIELDS)
    t_job = time.time()
    for i, (arm, sch) in enumerate(todo, 1):
        spec = specs.get(arm)
        if spec is None or sch not in spec.schedulers:
            print(f"ABORT: unknown config {arm}/{sch}", file=sys.stderr)
            return 4
        t0 = time.time()
        rows = S.sweep([inst], [spec], schedulers=[sch], opts=opts)
        if len(rows) != 1:
            print(f"ABORT: {arm}/{sch} produced {len(rows)} rows",
                  file=sys.stderr)
            return 5
        r = rows[0]
        kept.append(r.as_dict())
        tmp = out + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=fields)
            wr.writeheader()
            for d in kept:
                wr.writerow(d)
        os.replace(tmp, out)
        print(f"[{i}/{len(todo)}] {job['instance']} {arm}/{sch} -> "
              f"{r.status}/{r.verdict or '-'} valid={r.valid} "
              f"({time.time() - t0:.1f}s)", flush=True)
    open(out + ".done", "w").close()
    print(f"JOB DONE {a.id}: {len(kept)} rows in {time.time() - t_job:.1f}s "
          f"-> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
