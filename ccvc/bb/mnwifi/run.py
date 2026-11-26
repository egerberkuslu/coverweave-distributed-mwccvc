#!/usr/bin/env python3
"""The BB-CVC mininet-wifi run orchestrator (brief section 7).

THREE MODES
  plan     unprivileged. Generates positions, addresses, T_hello and tau,
           prepares the run directory, and prints THE ONE command the user runs.
  run      PRIVILEGED. Builds the ad-hoc network, starts one process per
           station, waits for quiescence, stops, collects, compares.
  collect  unprivileged. Re-evaluates a finished run directory.

WHY IT IS SPLIT IN TWO. sudo asks for a password on this machine, so an agent
cannot launch the run. The only thing that needs privilege is creating network
namespaces; everything computable -- layout, channel time, addresses,
collection, comparison -- sits on the unprivileged side of the split and is
covered by tests. What remains inside `run` is only "start the processes, wait,
stop them".

THE ORCHESTRATOR TAKES THE SCHEDULER'S ROLE. A node cannot know about global
quiescence (api I1); in the simulator `Scheduler` makes that call. Here the
orchestrator makes it: it watches the logs and drops a `STOP` file once every
node has gone quiet. The node is told nothing.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import math
import os
import random
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

from ccvc.bb.mnwifi import node_main, collect as collector  # noqa: E402
from ccvc.bb.mnwifi import topology as topo  # noqa: E402

Edge = Tuple[int, int]

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
DEFAULT_RUN_ROOT = "/tmp/run"

# The worked example from section 1 of the .tex; the calibration graph.
EXAMPLE_EDGES: List[Edge] = [
    (1, 2),
    (1, 3),
    (2, 3),
    (2, 4),
    (3, 4),
    (4, 5),
    (4, 6),
    (5, 6),
    (5, 7),
    (6, 7),
    (7, 8),
    (7, 9),
    (8, 9),
    (8, 10),
    (9, 10),
]
EXAMPLE_WEIGHTS: Dict[int, int] = {
    1: 5,
    2: 2,
    3: 4,
    4: 3,
    5: 6,
    6: 2,
    7: 3,
    8: 2,
    9: 5,
    10: 4,
}
EXAMPLE_K = 2


# ==========================================================================
# 1. Graph sources
# ==========================================================================
#: Target average degree for a random geometric graph. The measured density of
#: the Dagdeviren benchmark (8.0 at n=25, 12.0 at n=100, 16.0 at n=200; see
#: `ccvc/bb/BULGULAR_BB.md`) falls inside this band.
DEFAULT_AVG_DEG = 8.0


def side_for_density(
    n: int, radio_range_m: float, avg_deg: float = DEFAULT_AVG_DEG
) -> float:
    """Square side that yields the target average degree.

    Expected degree is (n-1)*pi*r^2/L^2, hence L = r*sqrt(pi*(n-1)/deg).
    Fixing the side by hand silently disconnects the graph as n grows: the
    connectivity threshold scales like ln(n) and a constant side does not keep
    up (measured: at n=50, r=200, L=1286 none of 200 draws was connected).
    """
    return radio_range_m * math.sqrt(math.pi * max(n - 1, 1) / max(avg_deg, 1e-6))


def unit_disk_graph(
    n: int,
    *,
    seed: int = 0,
    side: Optional[float] = None,
    radio_range_m: float = 200.0,
    tries: int = 60,
    avg_deg: float = DEFAULT_AVG_DEG,
) -> Tuple[List[Edge], Dict[int, Tuple[float, float]]]:
    """Generate a connected unit disk graph.

    Connectivity is required: the problem statement (brief section 1) assumes a
    connected graph, and on a disconnected instance the condition "G[C] is
    connected" becomes meaningless. If no side is given it is derived from the
    target density; if no connected draw appears the side is SHRUNK IN STEPS, so
    the search does not roll dice forever at the same density.
    """
    rng = random.Random(seed * 2654435761 + 0xC0FFEE)
    L = float(side if side else side_for_density(n, radio_range_m, avg_deg))
    for attempt in range(tries):
        pos = {i + 1: (rng.uniform(0, L), rng.uniform(0, L)) for i in range(n)}
        edges = sorted(topo.realised_edges(pos, radio_range_m))
        if _connected(range(1, n + 1), edges):
            return edges, pos
        if attempt % 5 == 4:
            L *= 0.94
    raise RuntimeError(f"n={n}, r={radio_range_m}: no connected instance found")


def _connected(nodes: Iterable[int], edges: Sequence[Edge]) -> bool:
    ids = sorted(set(int(n) for n in nodes))
    if not ids:
        return True
    adj: Dict[int, List[int]] = {i: [] for i in ids}
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    seen = {ids[0]}
    stack = [ids[0]]
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return len(seen) == len(ids)


#: Dagdeviren dosya adi: n<dugum>_m<kenar>_s<tohum>.txt
_DATASET_NAME = re.compile(r"n\d+_m\d+_s\d+\.txt$")

#: Veri kumesi agirliklari ondalik; supurme onlari `max(1, round(w*10))` ile
#: tamsayilastirir. KABLOSUZ TARAF AYNI OLCEGI KULLANMALI, yoksa ayni ornek
#: iki arka ucta iki farkli agirlik tasir ve toplayicinin simulator
#: karsilastirmasi ayni seyi karsilastirmadigi hâlde karsilastiriyor gorunur.
_DATASET_WEIGHT_SCALE = 10


def load_graph(path: str) -> Tuple[List[Edge], Dict[int, int]]:
    """`{"edges": ...}` JSON, Dagdeviren veri kumesi dosyasi, ya da kenar listesi.

    VERI KUMESI BICIMI AYRI ELE ALINIR. Dagdeviren dosyasinda once `id agirlik`
    satirlari (ondalik), sonra `u v` satirlari gelir. Asagidaki duz metin yolu
    her satiri kenar sanip agirlik satirinda patliyordu, dolayisiyla `--graph`
    veri kumesiyle hic kullanilamiyordu -- oysa `dataset_provenance` tam da bu
    kullanim icin yazilmis.
    """
    if _DATASET_NAME.search(os.path.basename(path)):
        from ccvc.bb import matrix as _matrix

        w_raw, edges_raw = _matrix.load_instance(path)
        ids = sorted(w_raw)
        relabel = {old: i + 1 for i, old in enumerate(ids)}
        edges = sorted({topo.edge(relabel[u], relabel[v]) for u, v in edges_raw})
        weights = {
            relabel[o]: max(1, round(x * _DATASET_WEIGHT_SCALE))
            for o, x in w_raw.items()
        }
        return edges, weights
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        edges = []
        for line in text.splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            u, v = line.replace(",", " ").split()[:2]
            edges.append(topo.edge(int(u), int(v)))
        nodes = sorted({a for e in edges for a in e})
        return edges, {n: 1 for n in nodes}
    edges = [topo.edge(int(u), int(v)) for u, v in doc["edges"]]
    nodes = sorted({a for e in edges for a in e})
    w = {int(k): float(v) for k, v in (doc.get("weights") or {}).items()}
    return edges, {n: w.get(n, 1) for n in nodes}


def weights_for(
    nodes: Sequence[int], *, seed: int = 0, lo: int = 1, hi: int = 9
) -> Dict[int, int]:
    rng = random.Random(seed * 2654435761 + 0x1234)
    return {int(n): rng.randint(lo, hi) for n in sorted(nodes)}


# ==========================================================================
# 2. Run plan
# ==========================================================================
@dataclass
class Fault:
    """A scheduled fault (brief section 7: node death and relocation).

    `kill`  kill the process. The only experiment that shows soft state (brief
            3.4) actually works: neighbours must drop the entry within
            `3*T_hello` and the run must still terminate.
    `move`  relocate via `setPosition`. The bidirectional neighbour set changes,
            the node raises its epoch and everyone returns to phase 0 (brief
            3.5/6). This is where RE-RUNNING, not patching, is put to the test.

    Time is RELATIVE TO THE RUN (ms), not wall clock, so the same scenario fires
    in the same slot on every run.
    """

    at_ms: int
    kind: str  # "kill" | "move"
    nid: int
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in ("kill", "move"):
            raise ValueError(f"unknown fault kind: {self.kind!r}")

    @staticmethod
    def parse(spec: str) -> "Fault":
        """`kill:4@2000` ya da `move:4@2000:310,120`."""
        kind, _, rest = spec.partition(":")
        head, _, tail = rest.partition("@")
        nid = int(head)
        if kind == "kill":
            return Fault(at_ms=int(tail), kind="kill", nid=nid)
        when, _, xy = tail.partition(":")
        x, y = (float(v) for v in xy.split(",")[:2])
        return Fault(at_ms=int(when), kind="move", nid=nid, x=x, y=y)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "at_ms": self.at_ms,
            "kind": self.kind,
            "nid": self.nid,
            "x": self.x,
            "y": self.y,
        }


@dataclass
class RunPlan:
    run_id: str
    run_dir: str
    spec: topo.TopoSpec
    mode: str
    max_ms: int
    loss_pct: float
    drops: Dict[int, List[str]]
    seed: int
    faults: List[Fault] = field(default_factory=list)
    node_kind: str = "bbcvc"
    node_params: Dict[str, Any] = field(default_factory=dict)
    dataset_case: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        d = self.spec.as_dict()
        d.update(
            {
                "run_id": self.run_id,
                "run_dir": self.run_dir,
                "mode": self.mode,
                "max_ms": self.max_ms,
                "loss_pct": self.loss_pct,
                "seed": self.seed,
                "drops": {str(k): v for k, v in sorted(self.drops.items())},
                "faults": [f.as_dict() for f in self.faults],
            }
        )
        d["node_kind"] = self.node_kind
        d["node_params"] = self.node_params
        d["dataset_case"] = self.dataset_case
        return d


def make_plan(
    edges: Sequence[Edge],
    weights: Dict[int, int],
    k: int,
    *,
    run_id: Optional[str] = None,
    run_root: str = DEFAULT_RUN_ROOT,
    mode: str = "sync",
    radio_range_m: float = 100.0,
    margin: float = 0.15,
    seed: int = 0,
    max_ms: int = 600_000,
    loss_pct: float = 0.0,
    rho_max: float = 0.1,
    udp_port: int = 47001,
    prop_exp: float = 3.0,
    drops: Optional[Dict[int, List[str]]] = None,
    faults: Optional[Sequence[Fault]] = None,
    positions: Optional[Dict[int, Tuple[float, float]]] = None,
    node_kind: str = "bbcvc",
    node_params: Optional[Dict[str, Any]] = None,
    dataset_case: Optional[Dict[str, Any]] = None,
) -> RunPlan:
    # THIRD copy of the same list, and the reason this one matters: the launcher
    # spawns `node_main.py --node <kind>`, so `node_main.NODE_KINDS` is the only
    # registry that can actually start a station. Every other list is a mirror,
    # and a mirror that drifts rejects a kind the station would have run fine.
    if node_kind not in node_main.NODE_KINDS:
        raise ValueError(
            f"Unsupported station node kind: {node_kind!r}; "
            f"known: {sorted(node_main.NODE_KINDS)}"
        )
    rid = run_id or time.strftime("%Y%m%d-%H%M%S")
    spec = topo.plan(
        edges,
        weights,
        k,
        radio_range_m=radio_range_m,
        margin=margin,
        seed=seed,
        udp_port=udp_port,
        rho_max=rho_max,
        prop_exp=prop_exp,
    )
    if positions:
        # If the graph was generated FROM positions (a UDG), do NOT re-solve
        # the layout: the real positions realise the target exactly by
        # construction.
        spec.positions = {
            int(n): (round(p[0], 2), round(p[1], 2)) for n, p in positions.items()
        }
        spec.geometric_diff = topo.compare_topology(
            edges, topo.realised_edges(spec.positions, radio_range_m)
        )
    from ccvc.bb.mnwifi.config import station_params

    resolved = station_params(
        node_kind,
        weights,
        spec.channel,
        spec.mis_nbrs_max,
        overrides=node_params,
        mode=mode,
        seed=seed,
    )
    return RunPlan(
        run_id=rid,
        run_dir=os.path.join(run_root, rid),
        spec=spec,
        mode=mode,
        max_ms=max_ms,
        loss_pct=loss_pct,
        drops=dict(drops or {}),
        seed=seed,
        faults=sorted(faults or (), key=lambda f: (f.at_ms, f.nid)),
        node_kind=node_kind,
        node_params=resolved,
        dataset_case=dataset_case,
    )


def _clear_stale_node_logs(run_dir: str) -> List[str]:
    """Remove node logs left by an EARLIER execution in the same directory.

    `JsonlLog` appends, so re-using a run directory writes the new execution
    onto the end of the old one. The collector now keeps only the last
    execution, but it should never have to: a run directory that still holds
    another run's telemetry when the plan is written is stale by definition,
    and the honest thing is to clear it before the stations start rather than
    to reconstruct the seam afterwards.

    Only the numeric `<nid>.jsonl` files node_main writes are removed. Plans,
    summaries and fault logs are left alone; the caller may want to compare
    against them.
    """
    removed: List[str] = []
    if not os.path.isdir(run_dir):
        return removed
    for name in sorted(os.listdir(run_dir)):
        if name.endswith(".jsonl") and name[:-6].isdigit():
            os.remove(os.path.join(run_dir, name))
            removed.append(name)
    return removed


def closest_pair_m(plan: "RunPlan") -> float:
    """Distance between the two nearest stations, or inf when there are none.

    THE PLANNER CAN COLLAPSE TWO NODES ONTO EACH OTHER. The embedding only has
    to reproduce a graph, not to keep stations apart, and a target that wants
    two nodes with identical neighbourhoods is solved by putting them in the
    same place. At that distance the received power leaves the range a signed
    byte can hold and the driver reports RSSI as a wrapped value, which makes
    the hysteretic gate toggle the link forever (see
    `BootstrapParams.rssi_impossible_dbm`). Printing the number with the plan
    puts that condition in front of the reader BEFORE the run is spent.
    """
    pos = [tuple(p[:2]) for p in getattr(plan.spec, "positions", {}).values()]
    best = float("inf")
    for i, (x1, y1) in enumerate(pos):
        for x2, y2 in pos[i + 1 :]:
            best = min(best, math.hypot(x1 - x2, y1 - y2))
    return best


def write_plan(plan: RunPlan) -> str:
    os.makedirs(plan.run_dir, exist_ok=True)
    _clear_stale_node_logs(plan.run_dir)
    doc = plan.as_dict()
    from ccvc.greedy.compare import fingerprint

    doc["code_fingerprint"] = fingerprint()
    doc["t0_ms"] = None
    raw = (json.dumps(plan.node_params, indent=2, sort_keys=True) + "\n").encode()
    with open(os.path.join(plan.run_dir, "params.json"), "wb") as fh:
        fh.write(raw)
    doc["params_sha256"] = hashlib.sha256(raw).hexdigest()
    with open(os.path.join(plan.run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    with open(os.path.join(plan.run_dir, "peers.json"), "w", encoding="utf-8") as fh:
        json.dump(topo.peers_to_json(plan.spec.peers), fh, indent=2, sort_keys=True)
    return plan.run_dir


def load_plan(run_dir: str) -> RunPlan:
    """Restore saved timing, propagation and addressing without new defaults."""
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    peers = topo.peers_from_json(meta["peers"])
    plan = make_plan(
        [topo.edge(int(u), int(v)) for u, v in meta["edges"]],
        {int(n): float(w) for n, w in meta["weights"].items()},
        int(meta["k"]),
        run_id=meta["run_id"],
        run_root=os.path.dirname(run_dir),
        mode=meta["mode"],
        radio_range_m=meta["radio_range_m"],
        seed=int(meta["seed"]),
        max_ms=int(meta["max_ms"]),
        loss_pct=float(meta["loss_pct"]),
        rho_max=float(meta["channel"]["rho_max"]),
        udp_port=int(meta["peers"]["udp_port"]),
        prop_exp=float(meta.get("prop_exp", 3.0)),
        drops={int(n): v for n, v in meta["drops"].items()},
        faults=[Fault(**f) for f in meta.get("faults", [])],
        positions={int(n): tuple(p) for n, p in meta["positions"].items()},
        node_kind=meta.get("node_kind", "bbcvc"),
        node_params=meta.get("node_params") or None,
        dataset_case=meta.get("dataset_case"),
    )
    plan.run_dir = run_dir
    plan.spec.peers = peers
    plan.spec.channel = replace(
        plan.spec.channel,
        **{
            key: meta["channel"][key]
            for key in (
                "n2_max",
                "t_frame_ms",
                "rho_max",
                "t_hello_ms",
                "tau_ms",
                "hello_bytes",
            )
        },
    )
    for key in ("rate_mbps", "mis_nbrs_max", "max_degree"):
        if key in meta:
            setattr(plan.spec, key, meta[key])
    return plan


def node_argv(
    plan: RunPlan,
    nid: int,
    *,
    python: str = "python3",
    start_at_ms: int = 0,
    broadcast: str = "subnet",
    nbr_table_max: int = 64,
) -> List[str]:
    p = plan.spec.peers[nid]
    nbr_table_max = plan.node_params.get("nbr_table_max", nbr_table_max)
    argv = [
        python,
        os.path.join(REPO_ROOT, "ccvc", "bb", "mnwifi", "node_main.py"),
        "--peers",
        os.path.join(plan.run_dir, "peers.json"),
        "--log-dir",
        plan.run_dir,
        "--iface",
        p.iface,
        "--weight",
        str(plan.spec.weights[nid]),
        "--k",
        str(int(plan.spec.k)),
        "--mode",
        plan.mode,
        "--node",
        plan.node_kind,
        "--tau-ms",
        str(int(plan.spec.channel.tau_ms)),
        "--t-hello-ms",
        str(int(plan.spec.channel.t_hello_ms)),
        "--max-ms",
        str(int(plan.max_ms)),
        "--broadcast",
        broadcast,
        "--mis-nbrs-max",
        str(int(plan.spec.mis_nbrs_max)),
        "--nbr-table-max",
        str(int(nbr_table_max)),
    ]
    if plan.node_params:
        argv += ["--params-json", os.path.join(plan.run_dir, "params.json")]
    if start_at_ms:
        argv += ["--start-at-ms", str(int(start_at_ms))]
    for spec in plan.drops.get(nid, ()):
        argv += ["--drop", spec]
    return argv


def sudo_command(plan: RunPlan) -> str:
    """THE ONE command the user has to run."""
    return (
        f"sudo -E env PYTHONPATH={shlex.quote(REPO_ROOT)} "
        f"PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 "
        f"{shlex.quote(os.path.join(REPO_ROOT, 'ccvc/bb/mnwifi/run.py'))} run "
        f"--resume {shlex.quote(plan.run_dir)}"
    )


# ==========================================================================
# 3. The privileged run
# ==========================================================================
def _live_wmediumd_pids() -> List[int]:
    """wmediumd processes that can actually OWN a radio, zombies excluded.

    A defunct process has already exited: it holds no netlink socket, no hwsim
    radio and no configuration. It lingers only as a process-table entry until
    its parent reaps it, and `pgrep -x` still matches it by name.

    MEASURED 2026-09-16: an orphaned wmediumd was terminated, its parent (an
    unrelated long-running gRPC agent) never reaped it, and the resulting
    zombie kept this guard refusing every new network for as long as that
    parent stayed alive. Refusing to run because of a process that has already
    exited is a false positive, and the only cure available to the user would
    have been killing somebody else's service.
    """
    out = subprocess.run(["pgrep", "-x", "wmediumd"], capture_output=True, text=True)
    if out.returncode != 0:
        return []
    live = []
    for raw in out.stdout.split():
        try:
            pid = int(raw)
        except ValueError:
            continue
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
                # The state letter follows the LAST ')': comm may contain ')'.
                state = fh.read().rsplit(")", 1)[1].split()[0]
        except OSError:
            # UNREADABLE MEANS LIVE, not exited. Only a POSITIVE reading of "Z"
            # may excuse a process; anything else and we refuse. Guessing the
            # permissive way here would let a real network through on a host
            # where /proc is restricted, and the cost of that is two networks
            # sharing one radio module against the cost of one refusal.
            live.append(pid)
            continue
        if state != "Z":
            live.append(pid)
    return live


def _ppid(pid: int) -> Optional[int]:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return int(fh.read().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


#: Where the kernel lists every mac80211 radio, in every network namespace.
HWSIM_DEBUGFS = "/sys/kernel/debug/ieee80211"


def scoped_stop(net: Any, *, owner_pid: Optional[int] = None) -> List[str]:
    """Stop THIS network and nothing else on the host; return what failed.

    `Mininet_wifi.stop()` ends in `CleanupWifi.kill_mod_proc()`, which is
    host-wide (mn_wifi/clean.py, mininet-wifi 91ca5be3): it pkills every
    wmediumd, hostapd, wpa_supplicant and simple_switch_grpc on the machine
    and rmmods mac80211_hwsim and ifb, so it tears down other running
    networks. This keeps the per-network half of `stop()` (links, stations)
    and replaces the host-wide half with this process's own wmediumd child and
    the hwsim radios mn_wifi named after this PID ("mn%05dp%02ds%02d").
    """
    pid = os.getpid() if owner_pid is None else owner_pid
    errors: List[str] = []
    calls = [(link, "stop") for link in net.links]
    calls += [(sta, "terminate") for sta in net.stations]
    for obj, name in calls:
        try:
            getattr(obj, name)()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name} {obj}: {exc}")
    try:
        from mn_wifi.wmediumdConnector import w_server

        w_server.disconnect()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"wmediumd disconnect: {exc}")
    for wpid in _live_wmediumd_pids():
        if _ppid(wpid) == pid:
            try:
                os.kill(wpid, signal.SIGTERM)
            except OSError as exc:
                errors.append(f"kill wmediumd {wpid}: {exc}")
    prefix = f"mn{pid:05d}p"
    for entry in (
        sorted(os.listdir(HWSIM_DEBUGFS)) if os.path.isdir(HWSIM_DEBUGFS) else ()
    ):
        if entry.startswith(prefix) and os.path.exists(
            os.path.join(HWSIM_DEBUGFS, entry, "hwsim")
        ):
            res = subprocess.run(
                ["hwsim_mgmt", "-x", entry], capture_output=True, text=True
            )
            if res.returncode:
                errors.append(f"hwsim_mgmt -x {entry}: {res.stderr.strip()}")
    return errors


def execute(
    plan: RunPlan,
    *,
    settle_s: float = 2.0,
    poll_s: float = 0.25,
    quiet_slots: int = 3,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Build the net, start processes, await quiescence, stop. NEEDS SUDO."""
    if os.geteuid() != 0:
        raise SystemExit(
            "this mode needs root; use plan mode and run the "
            "command yourself:\n  " + sudo_command(plan)
        )
    # Every wmediumd serves one fixed socket (/var/run/wmediumd.sock) and
    # registers with the shared hwsim module, so two emulated wireless networks
    # cannot share a host.
    # Refuse coexistence before creating nodes.
    existing = _live_wmediumd_pids()
    if existing:
        raise RuntimeError(
            "Another wmediumd network is running (PIDs: "
            + ", ".join(str(p) for p in existing)
            + "). Finish that network before this run; "
            "one emulated wireless network at a time."
        )
    net, stations = topo.build_net(plan.spec)
    host_namespace_inode = os.stat("/proc/self/ns/net").st_ino
    started: Dict[int, Any] = {}
    stop_path = os.path.join(plan.run_dir, "STOP")
    if os.path.exists(stop_path):
        os.remove(stop_path)
    try:
        # 1) Static ARP, so ARP broadcasts never pollute the experiment.
        for nid, cmds in topo.static_arp_commands(plan.spec).items():
            for c in cmds:
                stations[nid].cmd(c)
        # 2) Extra loss (brief section 7: 0/5/15 percent).
        if plan.loss_pct:
            for nid in sorted(stations):
                stations[nid].cmd(topo.netem_command(plan.spec, nid, plan.loss_pct))
        time.sleep(settle_s)  # IBSS merge plus wmediumd's first SNR

        # 3) SHARED START: every process opens its first slot on the same stamp.
        tau = plan.spec.channel.tau_ms
        t0 = ((int(time.time() * 1000) + int(settle_s * 1000)) // tau + 2) * tau
        for nid in sorted(stations):
            argv = node_argv(plan, nid, start_at_ms=t0)
            started[nid] = stations[nid].popen(argv)

        # 4) AWAIT quiescence and apply faults on schedule. The decision
        #    belongs to the orchestrator, never to a node.
        deadline = t0 + plan.max_ms + 5_000
        pending_faults = list(plan.faults)
        while int(time.time() * 1000) < deadline:
            time.sleep(poll_s)
            rel = int(time.time() * 1000) - t0
            while pending_faults and pending_faults[0].at_ms <= rel:
                apply_fault(
                    plan, stations, pending_faults.pop(0), rel, processes=started
                )
            logs = collector.read_run(plan.run_dir)
            quiet, done, alive = quiescence(plan, logs, rel, quiet_slots=quiet_slots)
            if verbose:
                print(f"\r  quiescent: {done}/{alive}", end="", flush=True)
            if quiet and not pending_faults:
                break
        if verbose:
            print()
        stop_rel_ms = int(time.time() * 1000) - t0
        with open(stop_path, "w", encoding="utf-8") as fh:
            fh.write(str(int(time.time() * 1000)))
        time.sleep(max(1.0, 2 * tau / 1000.0))
    finally:
        # Namespaces share the host PID space. Reap only processes launched
        # by this run; a name-based pkill can terminate another experiment.
        stop_processes(started)
        teardown_errors = scoped_stop(net)
        for problem in teardown_errors:
            print(f"teardown: {problem}", file=sys.stderr)
    meta_path = os.path.join(plan.run_dir, "run.json")
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    # Log timestamps are RELATIVE TO THE RUN (UdpPort.epoch_ms), so the zero
    # point for the collector is 0; the wall-clock equivalent is stored too.
    meta["t0_ms"] = 0
    meta["epoch_wall_ms"] = t0
    meta["execution_backend"] = "mininet-wifi"
    meta["host_network_namespace_inode"] = host_namespace_inode
    meta["station_process_pids"] = {str(n): proc.pid for n, proc in started.items()}
    meta["orchestrator_stop_ms"] = stop_rel_ms
    meta["teardown_errors"] = teardown_errors
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    return meta


def quiescence(
    plan: RunPlan, logs: Dict[int, Any], rel_ms: int, *, quiet_slots: int = 3
) -> Tuple[bool, int, int]:
    """Wait in the logs' run-relative clock, counting only surviving nodes."""
    killed = {f.nid for f in plan.faults if f.kind == "kill" and f.at_ms <= rel_ms}
    alive = set(plan.spec.peers) - killed
    stamps = []
    for nid in alive:
        log = logs.get(nid)
        record = log.first_of("node_done") if log else None
        if record is not None:
            stamps.append(int(record.get("t_end_ms", record["t_ms"])))
    done = len(stamps)
    quiet = (
        done == len(alive)
        and rel_ms >= max(stamps, default=0) + quiet_slots * plan.spec.channel.tau_ms
    )
    return quiet, done, len(alive)


def stop_processes(processes: Dict[int, Any]) -> None:
    """Terminate and reap this run's children, with a bounded kill fallback."""
    for proc in processes.values():
        if proc.poll() is None:
            proc.terminate()
    for proc in processes.values():
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)


def apply_fault(
    plan: RunPlan,
    stations: Dict[int, Any],
    f: Fault,
    rel_ms: int,
    *,
    processes: Optional[Dict[int, Any]] = None,
) -> None:
    """Apply the fault and record it in A SEPARATE FILE from the node logs.

    It is never written to a node's log: a fault is an event the node DOES NOT
    KNOW ABOUT, and putting it in that file would stop the collector being able
    to separate what the node knew from what it did not.
    """
    sta = stations[f.nid]
    if f.kind == "kill":
        if processes is None:
            raise ValueError("kill faults require this run's process handles")
        proc = processes[f.nid]
        if proc.poll() is None:
            proc.kill()
    else:
        sta.setPosition(f"{f.x},{f.y},0")
    with open(os.path.join(plan.run_dir, "faults.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"t_ms": rel_ms, "event": f.kind, "nid": f.nid, "x": f.x, "y": f.y}
            )
            + "\n"
        )


# ==========================================================================
# 4. Evaluation
# ==========================================================================
def evaluate(run_dir: str, *, compare_sim: bool = True) -> Dict[str, Any]:
    """Collect the logs, validate, and compare against the simulator."""
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    tau = int(meta["channel"]["tau_ms"])
    edges = [topo.edge(int(u), int(v)) for u, v in meta["edges"]]
    weights = {int(k): float(v) for k, v in meta["weights"].items()}
    k = int(meta["k"])
    run, doc, tl = collector.collect(
        run_dir,
        tau_ms=tau,
        t0_ms=meta.get("t0_ms"),
        target_edges=edges,
        weights=weights,
    )
    doc["timeline"] = tl.as_dict()
    doc["channel"] = meta["channel"]
    doc["geometric"] = meta.get("geometric")

    # Validator: the three gates plus the violation list (brief section 9).
    from ccvc.bb import validate as _val

    g = _val.make_graph(edges, k, weights)
    rep = _val.validate(g, run.cover, run.owner)
    duplicates = run.double_owned_edges()
    violations = [{"kind": v.kind, "detail": v.detail} for v in rep.violations]
    violations += [
        {
            "kind": "duplicate_ownership",
            "detail": f"Edge {e} is claimed by nodes {nodes}",
        }
        for e, nodes in duplicates.items()
    ]
    doc["validation"] = {
        "valid": rep.valid and not duplicates,
        "vertex_cover": rep.vertex_cover,
        "connected": rep.connected,
        "capacity": rep.capacity,
        "summary": rep.summary()
        if not duplicates
        else f"INVALID: {len(duplicates)} edges have duplicate owners",
        "violations": violations,
    }

    # TWO QUESTIONS, TWO ANSWERS. The block above judges the cover against the
    # PLANNED topology, so it answers "did the radio realise the plan AND did
    # the algorithm solve it" with a single bit. Those are different questions
    # and they have different owners.
    #
    # MEASURED on the first real n=10 runs: the node's own RSSI gate does not
    # reproduce the planner's unit disc. Links opened at 34.2 m and 31.1 m and
    # did not at 34.5 m and 31.6 m, and six edges below 29.9 m stayed shut in a
    # third run, so the realised graph differs between runs at fixed positions.
    # Against the planned graph both runs read INVALID; against the graph the
    # stations actually discovered, both were VALID. Reporting only the first
    # would have blamed the algorithm for the channel.
    dv = doc.get("discovered_vs_target") or {}
    if dv and not dv.get("exact", True):
        discovered = {tuple(e) for e in edges} - {
            tuple(e) for e in dv.get("missing", [])
        } | {tuple(e) for e in dv.get("extra", [])}
        g_d = _val.make_graph(sorted(discovered), k, weights)
        rep_d = _val.validate(g_d, run.cover, run.owner)
        doc["validation_vs_discovered"] = {
            "valid": rep_d.valid and not duplicates,
            "vertex_cover": rep_d.vertex_cover,
            "connected": rep_d.connected,
            "capacity": rep_d.capacity,
            "m_discovered": len(discovered),
            "summary": rep_d.summary()
            if not duplicates
            else f"INVALID: {len(duplicates)} edges have duplicate owners",
            "scope": (
                "The graph the stations actually saw. This isolates the "
                "ALGORITHM from the channel; `validation` above still "
                "answers whether the planned topology was realised."
            ),
        }

    doc["node_kind"] = meta.get("node_kind", "bbcvc")
    if meta.get("execution_backend") == "mininet-wifi":
        from ccvc.greedy.audit import verify_run

        proof = verify_run(run_dir)
        doc["execution_provenance"] = proof
        doc["comparison_eligible"] = proof["dataset_comparison_eligible"]
        doc["execution_backend"] = proof["backend"]
    else:
        doc["execution_backend"] = "unverified"
        doc["comparison_eligible"] = False
        doc["execution_provenance"] = {
            "status": "PENDING: no namespace execution record"
        }
    if compare_sim:
        from ccvc.bb import bbcvc as _bb

        kind = doc["node_kind"]
        options = dict(
            scheduler=meta.get("mode", "sync"),
            max_ms=int(meta.get("max_ms", 600_000)),
            seed=int(meta.get("seed", 0)),
            tau_ms=tau,
            tick_ms=tau,
        )
        settings = dict(
            t_hello_ms=int(meta["channel"]["t_hello_ms"]),
            mis_nbrs_max=int(meta.get("mis_nbrs_max", 5)),
        )
        settings.update(meta.get("node_params") or {})
        if kind in ("gccvc", "grccvc", "gwccvc"):
            from ccvc.greedy.distributed import GreedyParams, run_greedy

            sim = run_greedy(
                edges,
                weights,
                k,
                algorithm=kind,
                params=GreedyParams(algorithm=kind, **settings),
                **options,
            )
        elif kind == "wuli":
            from ccvc.bb.v5_wuli import WuLiParams, run_wuli

            sim = run_wuli(edges, weights, k, params=WuLiParams(**settings), **options)
        elif kind == "bbcvc":
            sim = _bb.run_bbcvc(
                edges, weights, k, params=_bb.BbcvcParams(**settings), **options
            )
        elif kind == "anneal":
            from ccvc.bb.anneal import AnnealParams, AnnealNode
            from ccvc.bb.v6_anneal import run_anneal

            sim = run_anneal(
                edges,
                weights,
                k,
                params=AnnealParams(**settings),
                trace=False,
                node_cls=AnnealNode,
                **options,
            )
        elif kind == "dfs":
            from ccvc.bb.v1_dfs import run_v1

            sim = run_v1(
                edges, weights, k, params=_bb.BbcvcParams(**settings), **options
            )
        elif kind == "mst":
            from ccvc.bb.v4_mst import run_v4

            sim = run_v4(
                edges, weights, k, params=_bb.BbcvcParams(**settings), **options
            )
        else:
            raise ValueError(
                f"No matched simulator implementation for node kind {kind!r}"
            )
        cmp_ = collector.compare_with_sim(run, sim, weights=weights)
        doc["vs_simulator"] = {
            "exact": cmp_.exact,
            "matches": cmp_.matches,
            "discrepancies": [
                {
                    "metric": d.metric,
                    "emulator": d.emulator,
                    "simulator": d.simulator,
                    "rel": d.rel,
                }
                for d in cmp_.discrepancies
            ],
            "cover_same": cmp_.cover_same,
            "owner_same": cmp_.owner_same,
            "simulator": {
                "slots": sim.slots,
                "tx": sim.tx,
                "rx": sim.rx,
                "bytes_tx": sim.bytes_tx,
                "total_weight": sim.total_weight,
                "cover": sim.cover,
            },
            "summary": cmp_.summary(),
        }
    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    return doc


# ==========================================================================
# 5. Scale sweep
# ==========================================================================
#: Additional memory per station process, in MB. MEASURED on this machine from
#: `/proc/*/smaps_rollup` over ten live `node_main` processes: RSS 17.1 MB but
#: PSS 10.5 MB. PSS is the honest figure for scaling because every node process
#: shares the same interpreter and libc pages, so RSS double-counts them by
#: 63 percent and the error grows with n. Using RSS put the n=200 estimate at
#: 4.4 GB when the real cost is about 2.1 GB.
PROC_PSS_MB = 10.5


def scale_estimate(
    n: int,
    *,
    radio_range_m: float = 200.0,
    side: Optional[float] = None,
    seed: int = 0,
    k: int = 4,
    with_sim: bool = False,
) -> Dict[str, Any]:
    """What n stations cost on this machine.

    MEASURABLE WITHOUT PRIVILEGE: N2, T_hello, tau, the number of pairs wmediumd
    has to carry (an SNR per pair in interference mode), and with `--with-sim`
    the REAL slot count. The last one dominates: a run's wall-clock duration is
    `slots x tau` and both factors grow with n.

    NOT MEASURABLE HERE: wmediumd's CPU and the kernel cost of 200 namespaces.
    Those need a privileged run to confirm, so the report states separately what
    was measured and what is an estimate rather than blending the two.
    """
    s = side or side_for_density(n, radio_range_m)
    t_gen = time.perf_counter()
    edges, pos = unit_disk_graph(n, seed=seed, side=s, radio_range_m=radio_range_m)
    t_gen = time.perf_counter() - t_gen
    ch = topo.channel_time(edges, nodes=sorted(pos))
    row: Dict[str, Any] = {
        "n": n,
        "m": len(edges),
        "side_m": round(s, 1),
        "avg_deg": round(2 * len(edges) / n, 2),
        "n2_max": ch.n2_max,
        "t_hello_ms": ch.t_hello_ms,
        "tau_ms": ch.tau_ms,
        "wmediumd_pairs": n * (n - 1) // 2,
        "processes": n,
        "est_mem_mb": round(n * PROC_PSS_MB, 1),
        "graph_gen_s": round(t_gen, 3),
        "measured": (
            "N2, T_hello, tau, edge count, pair count; "
            "per-process memory (PSS, 10 live processes)"
        ),
        "estimated": "wmediumd CPU, per-namespace kernel cost",
    }
    if with_sim:
        from ccvc.bb import bbcvc as _bb

        w = weights_for(sorted(pos), seed=seed)
        t = time.perf_counter()
        sim = _bb.run_bbcvc(
            edges,
            w,
            k,
            scheduler="sync",
            params=_bb.BbcvcParams(t_hello_ms=ch.t_hello_ms),
            max_ms=20_000_000,
            tau_ms=ch.tau_ms,
        )
        row["sim_s"] = round(time.perf_counter() - t, 1)
        row["slots"] = sim.slots
        row["converged"] = sim.converged
        row["tx"] = sim.tx
        if sim.slots:
            row["wall_per_run_s"] = round(sim.slots * ch.tau_ms / 1000.0, 1)
    return row


# ==========================================================================
# 6. CLI
# ==========================================================================
def _graph_from_args(
    a,
) -> Tuple[List[Edge], Dict[int, int], int, Optional[Dict[int, Tuple[float, float]]]]:
    if a.graph:
        edges, weights = load_graph(a.graph)
        return edges, weights, a.k, None
    if a.n:
        edges, pos = unit_disk_graph(
            a.n, seed=a.seed, side=a.side, radio_range_m=a.range
        )
        return edges, weights_for(sorted(pos), seed=a.seed), a.k, pos
    return list(EXAMPLE_EDGES), dict(EXAMPLE_WEIGHTS), a.k or EXAMPLE_K, None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="BB-CVC mininet-wifi orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--graph", default=None, help="kenar listesi ya da JSON")
        p.add_argument("--n", type=int, default=None, help="UDG node count")
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--k", type=int, default=EXAMPLE_K)
        p.add_argument("--range", type=float, default=100.0, dest="range")
        p.add_argument("--side", type=float, default=None)
        p.add_argument("--mode", choices=("sync", "async"), default="sync")
        # Choices come from the REGISTRY, not from a second hand-written list.
        # The duplicate list had already drifted: `dfs` and `mst` were
        # registered in node_main.NODE_KINDS and still rejected here, so a node
        # kind could exist and be unreachable from the launcher.
        p.add_argument(
            "--node",
            choices=tuple(sorted(node_main.NODE_KINDS)),
            default="bbcvc",
            help="Station algorithm; comparison uses the same core",
        )
        p.add_argument(
            "--params-json",
            default=None,
            help="Optional deployment parameter overrides; saved with the run",
        )
        p.add_argument("--loss-pct", type=float, default=0.0)
        p.add_argument("--max-ms", type=int, default=600_000)
        p.add_argument("--run-id", default=None)
        p.add_argument("--run-root", default=DEFAULT_RUN_ROOT)
        p.add_argument(
            "--margin",
            type=float,
            default=0.15,
            help="Separation between an edge and a non-edge, as a "
            "fraction of --range. MEASURED: the neighbour gate "
            "is a BAND, not a disc (links opened at 31.1 m and "
            "34.2 m, and did not at 31.6 m and 34.5 m), so a "
            "topology is realised exactly only when edges sit "
            "below the band and non-edges above it.",
        )
        p.add_argument("--rho-max", type=float, default=0.1)
        p.add_argument(
            "--drop",
            action="append",
            default=[],
            help="nid:mtype=0,count=1,after_ms=2000",
        )
        p.add_argument(
            "--fault",
            action="append",
            default=[],
            help="kill:4@2000 ya da move:4@2000:310,120",
        )

    p_plan = sub.add_parser("plan", help="unprivileged preparation")
    common(p_plan)

    p_run = sub.add_parser("run", help="PRIVILEGED run")
    common(p_run)
    p_run.add_argument("--resume", default=None, help="prepared run directory")
    p_run.add_argument("--no-compare", action="store_true")

    p_col = sub.add_parser("collect", help="evaluate a finished run")
    p_col.add_argument("run_dir")
    p_col.add_argument("--no-compare", action="store_true")

    p_sc = sub.add_parser("scale", help="n sweep (unprivileged)")
    p_sc.add_argument("--ns", default="50,100,200")
    p_sc.add_argument("--range", type=float, default=200.0, dest="range")
    p_sc.add_argument("--seed", type=int, default=0)
    p_sc.add_argument("--k", type=int, default=4)
    p_sc.add_argument(
        "--with-sim",
        action="store_true",
        help="measure the real slot count via the simulator (slow)",
    )

    a = ap.parse_args(argv)

    if a.cmd == "scale":
        rows = [
            scale_estimate(
                int(x), radio_range_m=a.range, seed=a.seed, k=a.k, with_sim=a.with_sim
            )
            for x in a.ns.split(",")
            if x.strip()
        ]
        print(json.dumps(rows, indent=2))
        return 0

    if a.cmd == "collect":
        print(
            json.dumps(
                evaluate(a.run_dir, compare_sim=not a.no_compare),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if a.cmd == "run" and a.resume:
        plan = load_plan(a.resume)
        execute(plan)
        print(
            json.dumps(
                evaluate(plan.run_dir, compare_sim=not a.no_compare),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    edges, weights, k, pos = _graph_from_args(a)
    drops: Dict[int, List[str]] = {}
    for spec in a.drop:
        nid, _, rest = spec.partition(":")
        drops.setdefault(int(nid), []).append(rest)
    requested_params = None
    if a.params_json:
        with open(a.params_json, encoding="utf-8") as fh:
            requested_params = json.load(fh)
    plan = make_plan(
        edges,
        weights,
        k,
        run_id=a.run_id,
        run_root=a.run_root,
        mode=a.mode,
        radio_range_m=a.range,
        seed=a.seed,
        max_ms=a.max_ms,
        loss_pct=a.loss_pct,
        rho_max=a.rho_max,
        drops=drops,
        faults=[Fault.parse(f) for f in a.fault],
        positions=pos,
        node_kind=a.node,
        node_params=requested_params,
        margin=a.margin,
    )
    if a.graph:
        from ccvc.greedy.audit import dataset_provenance

        plan.dataset_case = dataset_provenance(a.graph, plan)
    write_plan(plan)

    if a.cmd == "plan":
        print(
            json.dumps(
                {
                    "run_dir": plan.run_dir,
                    "n": len(plan.spec.peers),
                    "m": len(plan.spec.edges),
                    "channel": plan.spec.channel.as_dict(),
                    "geometric": plan.spec.geometric_diff.as_dict(),
                    "geometric_summary": plan.spec.geometric_diff.summary(),
                    "closest_pair_m": round(closest_pair_m(plan), 3),
                    "mininet_available": topo.mininet_available(),
                    "sudo_command": sudo_command(plan),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    execute(plan)
    print(
        json.dumps(
            evaluate(plan.run_dir, compare_sim=not a.no_compare),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
