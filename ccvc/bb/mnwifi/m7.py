#!/usr/bin/env python3
"""Block M7 of the R1 pre-registration on Mininet-WiFi: jobs, plans, rows, host check.

M7 is the 27 development runs at the frozen tag (the archive in
results/bb/wifi_dagdeviren: n10_m20 k=6, n15_m90 k=8, n20_m160 k=12, seeds 1-3,
three arms) and set W (seeds 401-410, n in {30, 50}, average degree 6) with the
same three arms, 87 runs. `run_m7.sh` drives it one run at a time; every step
here is unprivileged and only `run.py run --resume` needs root.

    python3 -m ccvc.bb.mnwifi.m7 jobs  --dataset D --w-set W --out OUT
    python3 -m ccvc.bb.mnwifi.m7 todo  --jobs OUT/jobs.jsonl
    python3 -m ccvc.bb.mnwifi.m7 plan  --jobs OUT/jobs.jsonl --id ID
    python3 -m ccvc.bb.mnwifi.m7 row   --jobs OUT/jobs.jsonl --id ID --rc RC
    python3 -m ccvc.bb.mnwifi.m7 idle

Rows carry `sweep.CSV_FIELDS` plus `EXTRA_FIELDS`, so a wireless row reads like
a simulator row. `valid` is the planned-graph reading and `valid_discovered`
the discovered-graph reading (Amendment 4); `status` judges a false success
(`contradiction`) on the discovered graph, the reading H-a is evaluated on.
A run that fails, hits its limit or ends unresolved keeps its row and its
costs; no job is ever re-run once its run directory holds station logs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

from ccvc.bb import heldout, matrix, validate  # noqa: E402
from ccvc.bb import sweep as S  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402
from ccvc.bb.mnwifi import collect as collector  # noqa: E402
from ccvc.bb.mnwifi import run as R  # noqa: E402
from ccvc.greedy.audit import arm_config  # noqa: E402

#: The archived development runs: (cell stem, k). k keeps the DISCOVERED edge
#: count below n*k, since the radio adds edges the plan does not have.
DEV_CELLS = (("n10_m20", 6), ("n15_m90", 8), ("n20_m160", 12))
DEV_SEEDS = (1, 2, 3)
ARMS = ("MIS-Connector-Backbone", "GHS-MST-Backbone", "Anneal-Local")
#: Second note to Amendment 15: F9 passed its acceptance test on the repaired code and
#: the n = 100 probes, so it is the protocol under loss and M7 runs the defaults
M7_PROFILE: dict = {}
#: Set W is not given a k by the pre-registration; k = 6 is the development
#: set's capacity (section 2) and leaves twice the planned m = 3n.
W_K = 6
#: Planner settings of the archived runs: range 30 m matches the node's RSSI
#: gate (-75 dBm opens a link at about 31-34.5 m), margin 0.15, layout seed 0.
RANGE_M = 30.0
MARGIN = 0.15
LAYOUT_SEED = 0
#: Time limits. The 27 runs keep the 240 s of their archived execution; W uses
#: the 600 s the simulator sweep gives every size (Section 5, "Budgets").
DEV_MAX_MS = 240_000
W_MAX_MS = 600_000
#: Outer wall limit beyond max_ms: network build, settle, teardown and
#: evaluation took 27 s at n=10 and 45 s at n=20 in the archived batch.
WALL_MARGIN_S = 900
#: A host is idle when its 1-minute load is at most this share of its CPUs.
#: Contention shows up as slot overruns, which break synchronous fidelity.
LOAD_SHARE_MAX = 0.25

EXTRA_FIELDS = (
    "block",
    "run_id",
    "execution_backend",
    "wifi_fingerprint",
    "harness_rc",
    "stale_records",
    "slot_overruns",
    "rssi_implausible",
    "tau_ms",
    "instance_sha256",
)
COLUMNS = tuple(S.CSV_FIELDS) + EXTRA_FIELDS
ROWS_NAME = "m7_rows.csv"
_STEM = re.compile(r"n(\d+)_m(\d+)_s(\d+)\.txt$")


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ==========================================================================
# 1. Jobs
# ==========================================================================
def _arm_jobs(
    block: str, path: str, group: str, k: int, max_ms: int, out: str, sha256: str
) -> List[Dict[str, Any]]:
    n, m, seed = (int(x) for x in _STEM.search(os.path.basename(path)).groups())
    jobs = []
    for arm in ARMS:
        kind, params = arm_config(arm)
        params = {**params, **M7_PROFILE}
        rid = f"m7_{block}_{kind}_n{n}_m{m}_s{seed}"
        jobs.append(
            {
                "id": rid,
                "block": block,
                "path": os.path.abspath(path),
                "sha256": sha256,
                "group": group,
                "n": n,
                "m": m,
                "ratio": m // n,
                "seed": seed,
                "k": k,
                "arm": arm,
                "node_kind": kind,
                "params": params,
                "mode": "sync",
                "max_ms": max_ms,
                "wall_limit_s": max_ms // 1000 + WALL_MARGIN_S,
                "run_root": os.path.join(os.path.abspath(out), "runs"),
                "rows": os.path.join(os.path.abspath(out), ROWS_NAME),
            }
        )
    return jobs


def check_w_manifest(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The W entries of a held-out manifest, refused unless they are the registered set."""
    files = [f for f in manifest.get("files", []) if f.get("family") == "W"]
    registered = sorted((n, s) for _, n, _, s in heldout.plan("W"))
    found = sorted((int(f["n"]), int(f["seed"])) for f in files)
    if manifest.get("set") != "W" or manifest.get("preregistered_seeds") is not True:
        raise ValueError(
            "not the registered set W: the manifest must come from "
            "`heldout --set W` without --seeds"
        )
    if found != registered:
        raise ValueError(
            f"set W must hold {len(registered)} instances "
            f"(n, seed) = {registered}; found {found}"
        )
    return sorted(files, key=lambda f: (int(f["n"]), int(f["seed"])))


def make_jobs(dataset: str, w_set: str, out: str) -> List[Dict[str, Any]]:
    """The 87 M7 jobs. W instance files are not read here, only the manifest."""
    jobs: List[Dict[str, Any]] = []
    for stem, k in DEV_CELLS:
        for s in DEV_SEEDS:
            path = os.path.join(dataset, f"{stem}_s{s}.txt")
            jobs += _arm_jobs("dev", path, "small", k, DEV_MAX_MS, out, _sha256(path))
    with open(os.path.join(w_set, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    for f in check_w_manifest(manifest):
        jobs += _arm_jobs(
            "W", os.path.join(w_set, f["file"]), "W", W_K, W_MAX_MS, out, f["sha256"]
        )
    return jobs


def load_jobs(path: str) -> Dict[str, Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return {j["id"]: j for j in (json.loads(line) for line in fh if line.strip())}


def run_dir_of(job: Dict[str, Any]) -> str:
    return os.path.join(job["run_root"], job["id"])


# ==========================================================================
# 2. Plan (unprivileged)
# ==========================================================================
def plan_job(job: Dict[str, Any]) -> str:
    """Write the run directory of one job; the instance must match its sha256."""
    if _sha256(job["path"]) != job["sha256"]:
        raise ValueError(f"{job['path']}: sha256 differs from the job")
    raw_w, raw_e = matrix.load_instance(job["path"])
    weights, edges, _ = S.prepare(raw_w, raw_e)
    if (len(weights), len(edges)) != (job["n"], job["m"]):
        raise ValueError(
            f"{job['path']}: n={len(weights)} m={len(edges)}, "
            f"job says n={job['n']} m={job['m']}"
        )
    plan = R.make_plan(
        edges,
        weights,
        job["k"],
        run_id=job["id"],
        run_root=job["run_root"],
        mode=job["mode"],
        radio_range_m=RANGE_M,
        margin=MARGIN,
        seed=LAYOUT_SEED,
        max_ms=job["max_ms"],
        node_kind=job["node_kind"],
        node_params=job["params"],
    )
    return R.write_plan(plan)


# ==========================================================================
# 3. Rows (unprivileged, from station logs)
# ==========================================================================
def _base_row(job: Dict[str, Any], fingerprint: str) -> Dict[str, Any]:
    spec = next(s for s in S.discover() if s.name == job["arm"])
    row: Dict[str, Any] = {c: "" for c in COLUMNS}
    row.update(
        source="dataset" if job["block"] == "dev" else "heldout",
        group=job["group"],
        n=job["n"],
        ratio=job["ratio"],
        m=job["m"],
        seed=job["seed"],
        instance=os.path.basename(job["path"]),
        variant=job["arm"],
        family=spec.family,
        phase1=spec.phase1,
        phase5=spec.phase5,
        scheduler=job["mode"],
        k=job["k"],
        loss=0.0,
        code_fingerprint=fingerprint,
        counting_bound_infeasible=job["m"] > job["n"] * job["k"],
        relabelled=True,
        weight_scale=S.DEFAULT_WEIGHT_SCALE,
        lower_bound_g6=math.ceil(job["m"] / job["k"]),
        exact_status="not_requested",
        rng_seed=LAYOUT_SEED,
        params=json.dumps(job["params"], sort_keys=True) if job["params"] else "",
        block=job["block"],
        run_id=job["id"],
        instance_sha256=job["sha256"],
    )
    return row


def build_row(
    job: Dict[str, Any], *, rc: Optional[int], fingerprint: str, note: str = ""
) -> Dict[str, Any]:
    """One row from whatever the run directory holds; costs survive a failure."""
    row = _base_row(job, fingerprint)
    row["harness_rc"] = "" if rc is None else rc
    run_dir = run_dir_of(job)
    meta: Dict[str, Any] = {}
    if os.path.exists(os.path.join(run_dir, "run.json")):
        with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    logs = collector.read_run(run_dir) if os.path.isdir(run_dir) else {}
    notes = [x for x in (note, "" if not rc else f"harness exit {rc}") if x]
    if not meta or not logs:
        row.update(status="error", detail="; ".join(notes + ["no station logs"]))
        return row
    edges = [tuple(e) for e in meta["edges"]]
    weights = {int(v): float(w) for v, w in meta["weights"].items()}
    k = int(meta["k"])
    tau = int(meta["channel"]["tau_ms"])
    # Station clocks count from the shared start (UdpPort.epoch_ms), so t0 is 0.
    run = collector.counters_from_logs(logs, tau_ms=tau, t0_ms=0)
    tot = run.totals()
    double = run.double_owned_edges()
    res = SimpleNamespace(
        cover=run.cover,
        owner=run.owner,
        double_claimed=double,
        discovered_edges=run.discovered_edges(),
    )
    g = validate.make_graph(edges, k, weights, nodes=sorted(weights))
    rep = S.validate_run(g, res)
    disc = S.discovered_reading(edges, weights, k, res)
    verdict = (
        "truncated"
        if not run.converged
        else "unresolved"
        if run.unresolved
        else "solved"
    )
    if verdict == "truncated":
        status = "truncated"
    elif run.infeasible:
        status = "infeasible"
    elif verdict == "unresolved":
        status = "unresolved"
    elif not disc["valid_discovered"]:
        status = "contradiction"
    else:
        status = "ok"
    stop_ms = meta.get("orchestrator_stop_ms")
    row.update(
        graph_connected=S.is_connected(sorted(weights), edges),
        instance_feasible=S.instance_feasibility(
            SimpleNamespace(edges=edges, weights=weights), SimpleNamespace(k=k)
        ),
        mis_nbrs_max=meta.get("mis_nbrs_max", ""),
        status=status,
        verdict=verdict,
        truncated=verdict == "truncated",
        converged=run.converged,
        infeasible=run.infeasible,
        unresolved=run.unresolved,
        valid=bool(rep.valid),
        vertex_cover=bool(rep.vertex_cover),
        connected=bool(rep.connected),
        capacity=bool(rep.capacity),
        violations=len(rep.violations),
        violation_kinds="|".join(sorted({v.kind for v in rep.violations})),
        cover_size=len(run.cover),
        total_weight=round(sum(weights[v] for v in run.cover), 6),
        slots=run.slots,
        t_conv_ms=run.t_conv_ms,
        tx=tot.tx,
        rx=tot.rx,
        retx=tot.retx,
        bytes_tx=tot.bytes_tx,
        max_payload=tot.max_payload,
        hello_tx=tot.by_type_tx.get(int(MsgType.HELLO), 0),
        seconds="" if stop_ms is None else round(stop_ms / 1000.0, 3),
        detail="; ".join(notes),
        restarts="" if run.restarts is None else run.restarts,
        double_claims=len(double),
        **disc,
        execution_backend=meta.get("execution_backend", "unverified"),
        wifi_fingerprint=meta.get("code_fingerprint", ""),
        stale_records=run.stale_records,
        slot_overruns=run.slot_overruns,
        rssi_implausible=run.rssi_implausible,
        tau_ms=tau,
    )
    return row


def done_ids(rows_path: str) -> set:
    if not os.path.exists(rows_path):
        return set()
    with open(rows_path, newline="", encoding="utf-8") as fh:
        return {r["run_id"] for r in csv.DictReader(fh)}


def append_row(rows_path: str, row: Dict[str, Any]) -> None:
    new = not os.path.exists(rows_path)
    with open(rows_path, "a", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        if new:
            wr.writeheader()
        wr.writerow(row)


def todo(jobs: Dict[str, Dict[str, Any]], fingerprint: str) -> List[str]:
    """Jobs still to run. A run directory with logs but no row was interrupted:
    it gets its row now, with its costs, and is not run again."""
    out = []
    for jid, job in jobs.items():
        if jid in done_ids(job["rows"]):
            continue
        run_dir = run_dir_of(job)
        if os.path.isdir(run_dir) and collector.read_run(run_dir):
            append_row(
                job["rows"],
                build_row(
                    job,
                    rc=None,
                    fingerprint=fingerprint,
                    note="interrupted before its row was written; not re-run",
                ),
            )
            continue
        out.append(jid)
    return out


# ==========================================================================
# 4. Idle host
# ==========================================================================
def _mininet_shells() -> List[int]:
    """Node shells of any running Mininet network (`bash --norc --noediting -is mininet:<node>`)."""
    # The full argv tail, so a shell that merely mentions "mininet:" is not counted.
    out = subprocess.run(
        ["pgrep", "-f", "--", "bash --norc --noediting -is mininet:"],
        capture_output=True,
        text=True,
    )
    return [int(p) for p in out.stdout.split() if p.isdigit()]


def host_problems(
    *,
    wmediumd: Callable[[], List[int]] = R._live_wmediumd_pids,
    shells: Callable[[], List[int]] = _mininet_shells,
    load: Callable[[], Sequence[float]] = os.getloadavg,
    cpus: Optional[int] = None,
) -> List[str]:
    """Why this host may not start an M7 run now; empty when it may."""
    problems = []
    wmd, sh, load1 = wmediumd(), shells(), load()[0]
    if wmd:
        problems.append(
            f"wmediumd is running (PIDs {wmd}); one emulated wireless network at a time"
        )
    if sh:
        problems.append(
            f"Mininet node shells are running (PIDs {sh}); M7 runs alone on the host"
        )
    limit = LOAD_SHARE_MAX * (cpus or os.cpu_count() or 1)
    if load1 > limit:
        problems.append(f"1-minute load {load1:.2f} exceeds {limit:.2f}")
    return problems


# ==========================================================================
# 5. CLI
# ==========================================================================
def _require_snapshot() -> None:
    """Rows must record the frozen snapshot, not the live tree (as in r1_run)."""
    snap = os.environ.get("BB_SNAPSHOT") or ""
    if not snap or not os.path.realpath(S.__file__).startswith(
        os.path.realpath(snap) + os.sep
    ):
        raise SystemExit(
            f"ABORT: sweep.py resolved to {S.__file__}, not under "
            f"the snapshot {snap!r}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("jobs")
    p.add_argument("--dataset", required=True)
    p.add_argument("--w-set", required=True)
    p.add_argument("--out", required=True)
    for name in ("todo", "plan", "row"):
        p = sub.add_parser(name)
        p.add_argument("--jobs", required=True)
        if name != "todo":
            p.add_argument("--id", required=True)
        if name == "row":
            p.add_argument("--rc", type=int, required=True)
    sub.add_parser("idle")
    a = ap.parse_args(argv)

    if a.cmd == "idle":
        problems = host_problems()
        for msg in problems:
            print(f"NOT IDLE: {msg}", file=sys.stderr)
        return 1 if problems else 0
    _require_snapshot()
    if a.cmd == "jobs":
        jobs = make_jobs(a.dataset, a.w_set, a.out)
        os.makedirs(a.out, exist_ok=True)
        path = os.path.join(a.out, "jobs.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(j, sort_keys=True) + "\n" for j in jobs)
        print(path)
        return 0
    jobs = load_jobs(a.jobs)
    if a.cmd == "todo":
        print("\n".join(todo(jobs, S.code_fingerprint())))
        return 0
    job = jobs[a.id]
    if a.cmd == "plan":
        print(plan_job(job), job["wall_limit_s"])
        return 0
    append_row(job["rows"], build_row(job, rc=a.rc, fingerprint=S.code_fingerprint()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
