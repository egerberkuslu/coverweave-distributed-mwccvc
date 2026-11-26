#!/usr/bin/env python3
"""Hybrid genetic solver of kol2026 as a centralized quality reference (R1).

    python3 -m ccvc.bb.hga_ref --k 6 --time-limit 600 --ga-seeds 42 \
        --processes 4 --out results/bb/<block>/hga.csv FILE [FILE ...]

Runs `solve_hga` of the pinned upstream checkout (external_sources/MWCCVC,
loaded and hash-checked by `ccvc.greedy.central.upstream`) once per (instance,
GA seed) at a fixed capacity k, with the population and generation counts that
the Sensors paper prints (40/60 for n <= 200, 100/100 above). The instance is
the one the arms see (`sweep.prepare`, weights quantized with weight_scale).
The solver gets those weights divided by weight_scale: the same problem on the
published weight scale, because its decoder score and its penalties are not
scale-free. The solver returns a cover only. CoverAudit (`validate.validate`
without an owner map) checks vertex cover, connectivity and capacity by
max-flow, so `owner_source` is "flow": the owner map is reconstructed, not
produced by the solver.

One row per run, in the column layout of results/bb/exact/central.csv that
`revision_stats.load_central` reads (weight in the quantized units of the
sweep rows, empty when the cover is invalid), plus the instance identity of
the sweep rows and the solver settings. The time limit is on process CPU time,
so host load does not decide which runs time out; wall time is recorded too.
A run that hits the limit or returns an invalid cover is kept with its cost.
Rows are written as they finish; re-running with the same --out skips the runs
it already holds.

A file whose instance seed is pre-registered (`heldout.PREREGISTERED`) is
refused before any file is opened unless the annotated tag coverweave-r1-frozen
exists in the release repository, the check of ccvc/bb/mnwifi/run_m7.sh.

Exit codes: 0 done, 2 sealed seed refused.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from ccvc import bridge
from ccvc.bb import heldout, matrix, sweep, validate
from ccvc.greedy import central

RELEASE_REPO = os.path.expanduser("~/Desktop/bbcvc-release")
TAG = "coverweave-r1-frozen"
ARM = "HGA-Upstream"
NAME = re.compile(r"^n(\d+)_m(\d+)_s(\d+)\.txt$")
FIELDS = (
    # results/bb/exact/central.csv, read by revision_stats.load_central
    "instance", "n", "m", "k", "algorithm", "arm", "weight", "weight_unscaled",
    "weight_scale", "cover_size", "valid", "status", "seconds", "source",
    # sweep-row identity and the run's settings and cost
    "group", "seed", "ga_seed", "pop_size", "generations", "time_limit_s",
    "timed_out", "cpu_seconds", "violation_kinds", "owner_source",
    "instance_feasible", "solver_sha256", "code_fingerprint",
)  # fmt: skip


def settings(n: int) -> Tuple[int, int]:
    """(population, generations) of kol2026, Table 2: 40/60 up to n = 200, 100/100 for large."""
    return (40, 60) if n <= 200 else (100, 100)


def frozen_tag_exists(release: str = RELEASE_REPO) -> bool:
    r = subprocess.run(
        [
            "git",
            "-C",
            release,
            "rev-parse",
            "-q",
            "--verify",
            f"refs/tags/{TAG}^{{tag}}",
        ],
        capture_output=True,
    )
    return r.returncode == 0


def group_of(path: str, n: int) -> str:
    """Held-out family from the heldout.py layout DIR/<family>/<param>/file, else the dev group."""
    family = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    if family in heldout.FAMILIES:
        return family
    return "small" if n <= 25 else "medium" if n <= 200 else "large"


class _TimeLimit(BaseException):
    """Not an Exception, so an `except Exception` inside the solver cannot swallow it."""


def _expire(signum, frame):
    raise _TimeLimit


def run_one(path: str, k: int, ga_seed: int, time_limit_s: float) -> Dict:
    raw_w, raw_e = matrix.load_instance(path)
    w, e, adapt = sweep.prepare(raw_w, raw_e, weight_scale=sweep.DEFAULT_WEIGHT_SCALE)
    n, scale = len(w), adapt.weight_scale
    pop, gen = settings(n)
    row = dict.fromkeys(FIELDS, "")
    row.update(
        instance=os.path.basename(path), n=n, m=len(e), k=k, algorithm="hga", arm=ARM,
        weight_scale=scale, valid=False, source=f"external_sources/MWCCVC@{central.REVISION[:12]}",
        group=group_of(path, n), seed=int(NAME.match(os.path.basename(path)).group(3)),
        ga_seed=ga_seed, pop_size=pop, generations=gen, time_limit_s=time_limit_s,
        timed_out=False, solver_sha256=central.SOURCE_SHA256,
    )  # fmt: skip
    # loading and hashing the upstream module is not solver time
    solve = central.upstream().solve_hga
    graph, cover = None, None
    t0, c0 = time.perf_counter(), time.process_time()
    try:
        graph = central.check_input(e, w, k)
        vertices = [{"id": v, "weight": w[v] / scale} for v in sorted(w)]
        signal.signal(signal.SIGPROF, _expire)
        signal.setitimer(signal.ITIMER_PROF, time_limit_s)
        try:
            cover = sorted(
                solve(vertices, graph.edges, k, pop, gen, seed=ga_seed)["cover"]
            )
        finally:
            signal.setitimer(signal.ITIMER_PROF, 0)
    except _TimeLimit:
        row.update(status="timeout", timed_out=True)
    except Exception as exc:  # noqa: BLE001 - the reason goes into the row
        row["status"] = f"error:{type(exc).__name__}"
    row.update(
        seconds=round(time.perf_counter() - t0, 3),
        cpu_seconds=round(time.process_time() - c0, 3),
    )
    if graph is None:
        return row
    feasible = bridge.capacity_feasible(graph, set(w))[0]
    row["instance_feasible"] = "yes" if feasible else "no"
    if cover is None:
        return row
    rep = validate.validate(graph, cover)
    row.update(
        valid=rep.valid,
        violation_kinds=";".join(sorted({v.kind for v in rep.violations})),
        owner_source=rep.owner_source,
        status="ok"
        if rep.valid
        else "invalid_solution"
        if feasible
        else "infeasible_instance",
    )
    if rep.valid:
        weight = graph.total_weight(cover)
        row.update(
            weight=f"{weight:.6g}",
            weight_unscaled=f"{weight / scale:.6g}",
            cover_size=len(cover),
        )
    return row


def _write(path: str, rows: List[Dict]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=FIELDS)
        wr.writeheader()
        wr.writerows(rows)
    os.replace(tmp, path)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", help="instance files named n<N>_m<M>_s<S>.txt")
    ap.add_argument("--out", required=True, help="CSV of rows, resumed if it exists")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument(
        "--time-limit", type=float, required=True, help="CPU seconds per run"
    )
    ap.add_argument(
        "--ga-seeds", type=heldout.parse_seeds, default=[42], help="e.g. 42 or 1-3"
    )
    ap.add_argument("--processes", type=int, default=1)
    a = ap.parse_args(argv)

    bad = [p for p in a.files if not NAME.match(os.path.basename(p))]
    if bad:
        ap.error(f"not an instance file name: {bad[0]}")
    names = [os.path.basename(p) for p in a.files]
    if len(set(names)) != len(names):
        # rows, the resume check and revision_stats all key on the file name
        ap.error("two files share a name; run them into separate --out files")
    sealed = [
        p
        for p in a.files
        if int(NAME.match(os.path.basename(p)).group(3)) in heldout.PREREGISTERED
    ]
    if sealed and not frozen_tag_exists():
        print(
            f"ABORT: {len(sealed)} file(s) carry a pre-registered seed, e.g. {sealed[0]}; "
            f"held-out instances run only after the annotated tag {TAG} exists in "
            f"{RELEASE_REPO}",
            file=sys.stderr,
        )
        return 2

    rows: List[Dict] = []
    if os.path.exists(a.out):
        with open(a.out, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    done = {(r["instance"], r["k"], r["ga_seed"]) for r in rows}
    todo = [
        (p, s)
        for p in a.files
        for s in a.ga_seeds
        if (os.path.basename(p), str(a.k), str(s)) not in done
    ]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    fingerprint = sweep.code_fingerprint()
    print(
        f"hga_ref: {len(todo)} runs to do, {len(rows)} already in {a.out}, k={a.k} "
        f"limit={a.time_limit:g} CPU s, {a.processes} processes, fingerprint={fingerprint}",
        flush=True,
    )
    with ProcessPoolExecutor(max_workers=a.processes) as pool:
        futures = [pool.submit(run_one, p, a.k, s, a.time_limit) for p, s in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            r["code_fingerprint"] = fingerprint
            rows.append(r)
            _write(a.out, rows)
            print(
                f"[{i}/{len(todo)}] {r['instance']} ga_seed={r['ga_seed']} {r['status']} "
                f"W={r['weight'] or '-'} {r['seconds']}s wall {r['cpu_seconds']}s cpu",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
