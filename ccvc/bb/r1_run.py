#!/usr/bin/env python3
"""Run ONE job of the R1 revision blocks against a frozen code snapshot.

Modelled on results/bb/full_v3/densecomplete/run_job.py. A job is one
instance file under one capacity k, one channel condition and one channel seed,
plus a list of (variant, scheduler) configurations. Each row is appended to
the job's own CSV the moment it is measured, so a crash costs at most one run;
re-running a job skips the configurations its CSV already holds, and a
finished job leaves `<out>.done`.

Usage, from the snapshot root so that `ccvc` resolves there and the
`code_fingerprint` column records the snapshot, not the live tree:

    cd <snapshot> && BB_SNAPSHOT=$PWD PYTHONPATH=$PWD \
        python3 -m ccvc.bb.r1_run --jobs jobs.jsonl --id <job id>

`jobs.jsonl` holds one JSON object per line with the keys
    id            unique job id
    dataset       directory holding the instance file
    instance      file name inside `dataset` (read by matrix.load_instance)
    group, n, m, ratio, seed
                  cell and instance identity; `seed` is the instance seed
    k             capacity
    loss          independent loss probability (float), or a channel label
                  such as "ge:0.10:4" or "emp", passed unchanged to the run
    rng_seed      seed of the run's RNG and channel, independent of `seed`
    configs       [[variant, scheduler], ...]
    max_ms, mis_nbrs_max
                  per-run budget and HELLO neighbour cap
    out           path of the job's CSV
    params        optional {field: value} parameter overrides (block M8),
                  recorded in the `params` column; a field the arm's
                  parameter dataclass lacks stops the job
    all_configs_on_infeasible
                  optional, default false; true runs every configuration on
                  an infeasible instance (block M9)

An instance proved infeasible (flow check of sweep.instance_feasibility, or
m > n k) runs only its first configuration, as the witness run of the
pre-registration, unless `all_configs_on_infeasible` is true; the rows say
`instance_feasible=no`.

If R1_FROZEN_FINGERPRINT is set, a snapshot whose code_fingerprint differs
from it is refused.

Exit codes: 0 done, 2 snapshot, fingerprint or dataset guard, 3 instance does
not match the job, 4 unknown configuration.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import List, Optional


def load_done(path):
    if not os.path.exists(path):
        return set(), []
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {(r["variant"], r["scheduler"]) for r in rows}, rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--id", required=True)
    a = ap.parse_args(argv)

    with open(a.jobs, encoding="utf-8") as fh:
        job = next(
            j
            for j in (json.loads(line) for line in fh if line.strip())
            if j["id"] == a.id
        )

    from ccvc.bb import matrix
    from ccvc.bb import sweep as S

    snap = os.environ.get("BB_SNAPSHOT") or ""
    if not snap or not os.path.realpath(S.__file__).startswith(
        os.path.realpath(snap) + os.sep
    ):
        print(
            f"ABORT: sweep.py resolved to {S.__file__}, not under the "
            f"snapshot {snap!r}; the run would measure the live tree",
            file=sys.stderr,
        )
        return 2
    frozen = os.environ.get("R1_FROZEN_FINGERPRINT")
    if frozen is not None and frozen != S.code_fingerprint():
        print(
            f"ABORT: code fingerprint {S.code_fingerprint()} differs from "
            f"R1_FROZEN_FINGERPRINT={frozen!r}",
            file=sys.stderr,
        )
        return 2
    dataset = job["dataset"]
    if not os.path.isdir(dataset):
        print(f"ABORT: dataset {dataset!r} is not a directory", file=sys.stderr)
        return 2

    cell = matrix.Cell(job["group"], job["n"], job["ratio"])
    path = os.path.join(dataset, job["instance"])
    raw_w, raw_e = matrix.load_instance(path)
    w, e, adapt = S.prepare(raw_w, raw_e, weight_scale=S.DEFAULT_WEIGHT_SCALE)
    if len(e) != job["m"] or len(w) != job["n"]:
        print(
            f"ABORT: loaded n={len(w)} m={len(e)}, expected "
            f"n={job['n']} m={job['m']}",
            file=sys.stderr,
        )
        return 3
    seeds_in_cell = len(matrix.seeds_available(cell, dataset))
    inst = S.Instance(
        "dataset", cell, job["seed"], path, tuple(e), w, seeds_in_cell, adapt
    )
    opts = S.SweepOptions(
        k=job["k"],
        loss=job["loss"],
        rng_seed=job["rng_seed"],
        max_ms=job["max_ms"],
        mis_nbrs_max=job["mis_nbrs_max"],
        time_budget_s=None,
        params_overrides=job.get("params") or None,
    )

    feasible = S.instance_feasibility(inst, opts)
    configs = [tuple(c) for c in job["configs"]]
    infeasible = feasible == "no" or len(e) > len(w) * opts.k
    if infeasible and not job.get("all_configs_on_infeasible", False):
        configs = configs[:1]
    out = job["out"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    done, kept = load_done(out)
    todo = [c for c in configs if c not in done]
    print(
        f"job {a.id}: {job['instance']} k={opts.k} loss={opts.loss} "
        f"rng_seed={opts.rng_seed} feasible={feasible} {len(configs)} configs, "
        f"{len(done)} already measured, {len(todo)} to run, "
        f"max_ms={opts.max_ms} fingerprint={S.code_fingerprint()}",
        flush=True,
    )
    specs = {s.name: s for s in S.discover()}
    for arm, sch in todo:
        spec = specs.get(arm)
        if spec is None or sch not in spec.schedulers:
            print(f"ABORT: unknown config {arm}/{sch}", file=sys.stderr)
            return 4

    exact = S._exact_reference(inst.edges, inst.weights, opts.k, opts) if todo else None
    t_job = time.time()
    for i, (arm, sch) in enumerate(todo, 1):
        t0 = time.time()
        r = S.run_one(inst, specs[arm], sch, opts, exact=exact, feasible=feasible)
        kept.append(r.as_dict())
        tmp = out + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(S.CSV_FIELDS))
            wr.writeheader()
            wr.writerows(kept)
        os.replace(tmp, out)
        print(
            f"[{i}/{len(todo)}] {job['instance']} {arm}/{sch} -> "
            f"{r.status}/{r.verdict or '-'} valid={r.valid} "
            f"({time.time() - t0:.1f}s)",
            flush=True,
        )
    open(out + ".done", "w").close()
    print(
        f"JOB DONE {a.id}: {len(kept)} rows in {time.time() - t_job:.1f}s -> {out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
