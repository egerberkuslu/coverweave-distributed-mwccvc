#!/usr/bin/env python3
"""Proven optimum, or the LP lower bound where none is proven, per instance (R1).

    python3 -m ccvc.bb.r1_optima --k 6 --time-limit 600 --processes 4 \
        --out results/bb/<block>/optima.csv FILE [FILE ...]

Block M4 asks for the proven optimum up to n = 50 (prereg sections 4 and 5),
but run rows carry `exact_weight` only up to SweepOptions.exact_max_n = 18.
This runs the exact solver of the sweep (`ccvc.central.solve_exact`, the
branch-and-bound of exact_compare.py `optima`) without a size cap on the
instance the arms see (`sweep.prepare`, weight scale 10), and the LP bound of
`revision_stats.lp_bound` on the same instance.

One row per (instance, k) in the column layout of results/bb/exact/optima.csv,
which `revision_stats.load_optima` and `r1_tables --optima NAME CSV` read, plus
the file sha256, the LP bound and the run's cost. Status is ok, infeasible_at_k,
timed_out, invalid or error:<type>; only `ok` rows carry an optimum, so the
tables fall back to the LP bound of an instance that timed out. Such rows are
kept with their cost, never dropped. The time limit is on process CPU time
(SIGPROF), as in hga_ref.py, so the host's load does not decide which instances
time out; wall time is recorded too. Rows are written as they finish, and the
same --out resumes.

A file whose instance seed is pre-registered (`heldout.PREREGISTERED`) is
refused before any file is opened unless the annotated tag coverweave-r1-frozen
exists in the release repository (hga_ref.frozen_tag_exists).

Exit codes: 0 done, 2 sealed seed refused.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional

from ccvc import bridge, central
from ccvc.bb import exact_compare, hga_ref, heldout, matrix, sweep, validate
from ccvc.bb import revision_stats as rs

#: dataset and held-out names, with the `_<law>` suffix of the M8 weight families
NAME = re.compile(r"^n(\d+)_m(\d+)_s(\d+)(?:_[a-z]+)?\.txt$")
FIELDS = exact_compare.OPTIMA_FIELDS + (
    "sha256",
    "group",
    "seed",
    "time_limit_s",
    "cpu_seconds",
    "lp_status",
    "lp_bound",
    "solver_sha256",
)


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def run_one(path: str, k: int, time_limit_s: float) -> Dict:
    raw_w, raw_e = matrix.load_instance(path)
    w, e, adapt = sweep.prepare(raw_w, raw_e, weight_scale=sweep.DEFAULT_WEIGHT_SCALE)
    graph = validate.make_graph(list(e), k, dict(w))
    components = len(bridge.graph_components(graph))
    lp_status, lp = rs.lp_bound(w, e, k)
    row = dict.fromkeys(FIELDS, "")
    row.update(
        instance=os.path.basename(path), n=len(w), m=len(e), k=k,
        method="branch-and-bound (ccvc.central.solve_exact), per component",
        source="MDS_SKYFABRIC/ccvc/central.py", weight_scale=adapt.weight_scale,
        graph_connected=components == 1, components=components, sha256=_sha256(path),
        group=hga_ref.group_of(path, len(w)), seed=NAME.match(os.path.basename(path)).group(3),
        time_limit_s=time_limit_s, lp_status=lp_status,
        lp_bound="" if lp is None else f"{lp:.10g}", solver_sha256=_sha256(central.__file__),
    )  # fmt: skip
    t0, c0 = time.perf_counter(), time.process_time()
    result = None
    try:
        signal.signal(signal.SIGPROF, hga_ref._expire)
        signal.setitimer(signal.ITIMER_PROF, time_limit_s)
        try:
            result = central.solve_exact(
                graph, max_n=None, time_limit_s=None, strict=False
            )
        finally:
            signal.setitimer(signal.ITIMER_PROF, 0)
    except hga_ref._TimeLimit:
        row["status"] = "timed_out"
    except Exception as exc:  # noqa: BLE001 - the reason goes into the row
        row["status"] = f"error:{type(exc).__name__}"
    row.update(
        seconds=f"{time.perf_counter() - t0:.4f}",
        cpu_seconds=f"{time.process_time() - c0:.4f}",
    )
    if result is None:
        return row
    if not result.feasible:
        row["status"] = "infeasible_at_k"
    elif not result.valid:
        row["status"] = "invalid"
    else:
        # quantized weights are integers; .10g keeps every digit up to n = 1000
        opt = sum(w[v] for v in result.cover)
        row.update(
            status="ok",
            optimum=f"{opt:.10g}",
            optimum_unscaled=f"{opt / adapt.weight_scale:.10g}",
            cover_size=len(result.cover),
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
        "--time-limit", type=float, required=True, help="CPU seconds per instance"
    )
    ap.add_argument("--processes", type=int, default=1)
    a = ap.parse_args(argv)

    # every file must name its seed, so the sealed-seed check cannot be bypassed
    bad = [p for p in a.files if not NAME.match(os.path.basename(p))]
    if bad:
        ap.error(f"not an instance file name: {bad[0]}")
    names = [os.path.basename(p) for p in a.files]
    if len(set(names)) != len(names):
        ap.error("two files share a name; run them into separate --out files")
    sealed = [
        p
        for p in a.files
        if int(NAME.match(os.path.basename(p)).group(3)) in heldout.PREREGISTERED
    ]
    if sealed and not hga_ref.frozen_tag_exists():
        print(
            f"ABORT: {len(sealed)} file(s) carry a pre-registered seed, e.g. {sealed[0]}; "
            f"held-out instances run only after the annotated tag {hga_ref.TAG} exists "
            f"in {hga_ref.RELEASE_REPO}",
            file=sys.stderr,
        )
        return 2

    rows: List[Dict] = []
    if os.path.exists(a.out):
        with open(a.out, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    done = {(r["instance"], r["k"]) for r in rows}
    todo = [p for p in a.files if (os.path.basename(p), str(a.k)) not in done]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    print(
        f"r1_optima: {len(todo)} instances to do, {len(rows)} already in {a.out}, "
        f"k={a.k} limit={a.time_limit:g} CPU s, {a.processes} processes",
        flush=True,
    )
    with ProcessPoolExecutor(max_workers=a.processes) as pool:
        futures = [pool.submit(run_one, p, a.k, a.time_limit) for p in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            rows.append(r)
            _write(a.out, rows)
            print(
                f"[{i}/{len(todo)}] {r['instance']} {r['status']} "
                f"opt={r['optimum'] or '-'} lp={r['lp_bound'] or '-'} "
                f"{r['cpu_seconds']}s cpu {r['seconds']}s wall",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
