#!/usr/bin/env python3
"""Derive counters and time series from the JSONL logs (brief section 7).

THE INVARIANT RULE: A NODE NEVER REPORTS ITS OWN COUNTERS. This file builds
every counter from log LINES; no node's claim that "I sent 12 messages" is
trusted. The rule is not arbitrary: a node's own counter becomes part of that
node's state, so a faulty node would corrupt the decision and the measurement
together. Measurement and decision must stay separate (api.Counters and simnet
follow the same rule).

RX ATTRIBUTION. `api.Counters.record_tx` credits rx to the SENDER ("how many
deliveries this node's transmissions caused"). On the emulator the sender cannot
know how many received it, so the attribution is done here in the collector:
every `rx` line carries the sender's MAC and the collector credits it to the
sender. The receiver side (`rx_delivered`) is kept separately; the global totals
are equal. The report states which attribution it used.

SLOT COUNTING. `sched.SyncScheduler` increments the slot each round and exits
when every node reports `done`, so the slot count is one more than the slot
index in which the LAST node became quiescent. The collector uses the same
definition, which is what makes the emulator and simulator numbers comparable.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

from ccvc.bb.api import Counters, Role  # noqa: E402
from ccvc.bb.bootstrap import hash16  # noqa: E402
from ccvc.bb.mnwifi.topology import (
    TopologyDiff,
    compare_topology,  # noqa: E402
    edge,
    parse_mac,
)

Edge = Tuple[int, int]

#: Role-changing events; the convergence timeline is built from these (brief 8/4).
ROLE_EVENTS = ("mis_decided", "connector", "cover", "joined")


# ==========================================================================
# 1. Okuma
# ==========================================================================
@dataclass
class NodeLog:
    """One station's log, parsed."""

    nid: int
    mac: int
    path: str
    records: List[Dict[str, Any]] = field(default_factory=list)
    #: Records dropped because they belonged to an EARLIER execution appended
    #: to the same file. Non-zero means the run directory was re-used.
    stale_records: int = 0

    @property
    def first_ms(self) -> Optional[int]:
        return self.records[0]["t_ms"] if self.records else None

    @property
    def last_ms(self) -> Optional[int]:
        return self.records[-1]["t_ms"] if self.records else None

    def of(self, event: str) -> List[Dict[str, Any]]:
        return [r for r in self.records if r.get("event") == event]

    def first_of(self, event: str) -> Optional[Dict[str, Any]]:
        for r in self.records:
            if r.get("event") == event:
                return r
        return None

    def last_of(self, event: str) -> Optional[Dict[str, Any]]:
        for r in reversed(self.records):
            if r.get("event") == event:
                return r
        return None


def split_last_execution(
    recs: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], int]:
    """Keep only the records of the LAST execution in FILE order.

    `JsonlLog` opens its file in append mode, so re-using a run directory
    concatenates a second execution onto the first. Both executions start
    their clock at t_ms 0, so the later `recs.sort(key=t_ms)` INTERLEAVES
    them: an rx from the old run lands between two ticks of the new one.
    Every counter downstream -- neighbours, ownership, slots, RSSI -- is then
    computed over a graph that never existed.

    MEASURED on dag_anneal_n10_m20_s1: two `run_start` records 203 s apart
    with different pids, and one directed pair whose RSSI reads -74 for 105
    samples and then -69 for 108 more, the jump landing exactly where t_ms
    falls from 8056 back to 4. That is not fading, it is the seam between two
    runs. The seam also produced two edges that were owned but absent from
    the discovered graph.

    A `run_start` is written once per execution, so the last one opens the
    last execution. Anything before it is stale and is dropped; how many
    records were dropped is returned rather than swallowed.
    """
    starts = [i for i, r in enumerate(recs) if r.get("event") == "run_start"]
    if len(starts) < 2:
        # ONE EXECUTION NEEDS NO SEAM. Cutting at the only `run_start` would
        # throw away whatever precedes it, and what precedes it carries the
        # station's MAC in the `open` record; without that the node cannot be
        # matched to its peers and every rx is attributed to nobody.
        return recs, 0
    cut = starts[-1]
    return recs[cut:], cut


def read_node_log(path: str) -> NodeLog:
    """Read one JSONL file. A TRUNCATED LAST LINE IS TOLERATED.

    When a process is cut short by SIGTERM the final line can be half written.
    Dropping that line is right; rejecting the whole file would make every
    interrupted run unmeasurable. How many lines were dropped is reported as
    `truncated`.

    A re-used run directory is tolerated the same way: only the last
    execution is kept (see `split_last_execution`).
    """
    recs: List[Dict[str, Any]] = []
    bad = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(rec, dict) and "t_ms" in rec:
                recs.append(rec)
            else:
                bad += 1
    # BEFORE sorting: the seam is only visible in file order.
    recs, stale = split_last_execution(recs)
    recs.sort(key=lambda r: r["t_ms"])
    mac = 0
    for r in recs:
        if "mac" in r:
            mac = parse_mac(str(r["mac"]))
            break
    nid = hash16(mac) if mac else int(os.path.basename(path).split(".")[0])
    log = NodeLog(nid=nid, mac=mac, path=path, records=recs, stale_records=stale)
    if bad:
        log.records.append(
            {
                "t_ms": recs[-1]["t_ms"] if recs else 0,
                "event": "collector_note",
                "truncated": bad,
            }
        )
    return log


def read_run(run_dir: str) -> Dict[int, NodeLog]:
    out: Dict[int, NodeLog] = {}
    for name in sorted(os.listdir(run_dir)):
        # Faults belong to the orchestrator, not to any node. Only the
        # numeric filenames emitted by node_main are node telemetry.
        if not name.endswith(".jsonl") or not name[:-6].isdigit():
            continue
        log = read_node_log(os.path.join(run_dir, name))
        out[log.nid] = log
    return out


# ==========================================================================
# 2. Counters
# ==========================================================================
@dataclass
class RunCounters:
    """Everything derived from the log. None of it is a node's own claim."""

    t0_ms: int
    t_end_ms: int
    tau_ms: int
    by_node: Dict[int, Counters]
    rx_delivered: Dict[int, int]
    done_ms: Dict[int, int]
    slots: Optional[int]
    t_conv_ms: Optional[int]
    converged: bool
    roles: Dict[int, Role]
    owned: Dict[int, List[Edge]]
    deg: Dict[int, int]
    key_fp: Dict[int, int]
    epoch: Dict[int, int]
    bidir: Dict[int, List[int]]
    infeasible: bool
    unresolved: bool
    table_overflow: int
    id_rederivations: int
    slot_overruns: int
    truncated_lines: int
    #: Records dropped because the run directory already held an EARLIER
    #: execution. Non-zero is a warning about the harness, not the protocol.
    stale_records: int
    unicast_unreachable: int
    send_failures: int
    rssi_failures: int
    #: Peers whose RSSI was condemned as unreadable. Non-zero means the gate
    #: did not govern those links; see BootstrapParams.rssi_impossible_dbm.
    rssi_implausible: int
    #: Epoch restarts: the largest `epoch_advance` any station reported, the
    #: simulator's `restarts`. None when no station log carries it.
    restarts: Optional[int] = None

    # -- toplamlar --------------------------------------------------------
    def totals(self) -> Counters:
        agg = Counters()
        for c in self.by_node.values():
            agg.tx += c.tx
            agg.rx += c.rx
            agg.bytes_tx += c.bytes_tx
            agg.retx += c.retx
            agg.radio_on_ms += c.radio_on_ms
            agg.max_payload = max(agg.max_payload, c.max_payload)
            for dst, src in (
                (agg.by_type_tx, c.by_type_tx),
                (agg.by_type_rx, c.by_type_rx),
                (agg.by_phase_tx, c.by_phase_tx),
            ):
                for kk, vv in src.items():
                    dst[kk] = dst.get(kk, 0) + vv
        return agg

    @property
    def cover(self) -> List[int]:
        return sorted(n for n, r in self.roles.items() if r.in_cover)

    @property
    def owner(self) -> Dict[Edge, int]:
        out: Dict[Edge, int] = {}
        for nid in sorted(self.owned):
            for e in self.owned[nid]:
                out[edge(*e)] = nid
        return out

    def double_owned_edges(self) -> Dict[Edge, List[int]]:
        """Audit claims before the owner map overwrites duplicate owners."""
        claims: Dict[Edge, List[int]] = defaultdict(list)
        for nid, owned in sorted(self.owned.items()):
            for e in {edge(*e) for e in owned}:
                claims[e].append(nid)
        return {e: nodes for e, nodes in sorted(claims.items()) if len(nodes) > 1}

    def discovered_edges(self) -> List[Edge]:
        """The graph formed by the adjacencies nodes count as BIDIRECTIONAL.

        Only MUTUAL ones are edges: if u counts v as bidirectional but v does not
        count u, that is an asymmetry and NOT an edge (brief 3.4).
        """
        out = set()
        for u, lst in self.bidir.items():
            for v in lst:
                if u in self.bidir.get(v, ()):
                    out.add(edge(u, v))
        return sorted(out)

    def asymmetric_claims(self) -> List[Tuple[int, int]]:
        """u counts v as a neighbour but v does not. Witness of loss/asymmetry."""
        out = []
        for u, lst in sorted(self.bidir.items()):
            for v in lst:
                if u not in self.bidir.get(v, ()):
                    out.append((u, v))
        return out

    def energy_mah(self, t_frame_ms: float = 0.7) -> Dict[int, float]:
        return {n: c.energy_mah(t_frame_ms) for n, c in sorted(self.by_node.items())}


def _role_from(value: Any) -> Role:
    try:
        return Role(int(value))
    except Exception:
        return Role.OUT


def counters_from_logs(
    logs: Dict[int, NodeLog], *, tau_ms: int, t0_ms: Optional[int] = None
) -> RunCounters:
    """Derive every counter from the log. The single entry point."""
    by_mac: Dict[int, int] = {lg.mac: nid for nid, lg in logs.items() if lg.mac}
    by_node: Dict[int, Counters] = {nid: Counters() for nid in logs}
    rx_delivered: Dict[int, int] = {nid: 0 for nid in logs}
    done_obs: Dict[int, int] = {}  # the scheduler's observation (node_done)
    done_self: Dict[int, int] = {}  # the node's own claim (done)
    roles: Dict[int, Role] = {}
    owned: Dict[int, List[Edge]] = {}
    deg: Dict[int, int] = {}
    key_fp: Dict[int, int] = {}
    epoch: Dict[int, int] = {}
    bidir: Dict[int, List[int]] = {}
    infeasible = unresolved = False
    table_overflow = id_reder = overruns = truncated = 0
    stale = sum(lg.stale_records for lg in logs.values())
    unreachable = send_fail = rssi_fail = rssi_implausible = 0
    advances: List[int] = []

    starts = [lg.first_ms for lg in logs.values() if lg.first_ms is not None]
    ends = [lg.last_ms for lg in logs.values() if lg.last_ms is not None]
    t0 = int(t0_ms) if t0_ms is not None else (min(starts) if starts else 0)
    t_end = max(ends) if ends else t0

    for nid, lg in logs.items():
        c = by_node[nid]
        for r in lg.records:
            ev = r.get("event")
            if ev == "tx":
                nb = int(r.get("bytes", 0))
                c.tx += 1
                c.bytes_tx += nb
                c.max_payload = max(c.max_payload, nb)
                mt = int(r.get("mtype", -1))
                ph = int(r.get("phase", 0))
                c.by_type_tx[mt] = c.by_type_tx.get(mt, 0) + 1
                c.by_phase_tx[ph] = c.by_phase_tx.get(ph, 0) + 1
            elif ev == "rx":
                rx_delivered[nid] += 1
                src = by_mac.get(parse_mac(str(r.get("src", "00:00:00:00:00:00"))))
                mt = int(r.get("mtype", -1))
                if src is not None and src in by_node:
                    by_node[src].rx += 1  # credited to the SENDER (api)
                    by_node[src].by_type_rx[mt] = by_node[src].by_type_rx.get(mt, 0) + 1
            elif ev == "retx":
                c.retx += int(r.get("n", 1))
            elif ev == "node_done" and nid not in done_obs:
                # `t_end_ms` is the END of the slot, the same instant as the
                # scheduler's `_mark_done(t_end)`. Without it, fall back to the
                # line's own timestamp.
                done_obs[nid] = int(r.get("t_end_ms", r["t_ms"]))
            elif ev == "done" and nid not in done_self:
                done_self[nid] = int(r["t_ms"])
            elif ev == "slot_overrun":
                overruns += 1
            elif ev == "unicast_unreachable":
                unreachable += 1
            elif ev == "send_failed":
                send_fail += 1
            elif ev == "collector_note":
                truncated += int(r.get("truncated", 0))
        end = lg.last_of("run_end")
        if end is not None:
            roles[nid] = _role_from(end.get("role", 0))
            owned[nid] = [edge(int(a), int(b)) for a, b in end.get("owned", [])]
            deg[nid] = int(end.get("deg", -1))
            key_fp[nid] = int(end.get("key_fp", -1))
            epoch[nid] = int(end.get("epoch", 0))
            bidir[nid] = [int(u) for u in end.get("bidir", [])]
            infeasible = infeasible or bool(end.get("infeasible"))
            unresolved = unresolved or bool(end.get("unresolved"))
            table_overflow += int(end.get("table_overflow", 0))
            id_reder += int(end.get("id_rederivations", 0))
            rssi_fail += int(end.get("rssi_failures", 0))
            rssi_implausible += int(end.get("rssi_implausible", 0))
            if end.get("epoch_advance") is not None:
                advances.append(int(end["epoch_advance"]))
        else:
            roles.setdefault(nid, Role.OUT)
            owned.setdefault(nid, [])
            bidir.setdefault(nid, [])

    # Quiescence stamp: THE SCHEDULER'S observation is preferred and the node's
    # own `done` claim is only a fallback. Both are written on the same tick and
    # carry the same `t_ms`, so relying on ordering would be wrong; the rule is
    # explicitly "a node's own claim is not trusted", and the choice follows it.
    done_ms: Dict[int, int] = dict(done_self)
    done_ms.update(done_obs)
    converged = bool(logs) and len(done_ms) == len(logs)
    slots: Optional[int] = None
    t_conv: Optional[int] = None
    if converged:
        last = max(done_ms.values())
        t_conv = last - t0
        slots = ((last - t0) // int(tau_ms)) + 1

    # Radio-on: from the start of the run to that node's quiescence; a node
    # that never became quiescent listened for the whole run (as in simnet).
    for nid, c in by_node.items():
        c.radio_on_ms = int(done_ms.get(nid, t_end) - t0)

    return RunCounters(
        t0_ms=t0,
        t_end_ms=t_end,
        tau_ms=int(tau_ms),
        by_node=by_node,
        rx_delivered=rx_delivered,
        done_ms=done_ms,
        slots=slots,
        t_conv_ms=t_conv,
        converged=converged,
        roles=roles,
        owned=owned,
        deg=deg,
        key_fp=key_fp,
        epoch=epoch,
        bidir=bidir,
        infeasible=infeasible,
        unresolved=unresolved,
        table_overflow=table_overflow,
        id_rederivations=id_reder,
        slot_overruns=overruns,
        truncated_lines=truncated,
        stale_records=stale,
        unicast_unreachable=unreachable,
        send_failures=send_fail,
        rssi_failures=rssi_fail,
        rssi_implausible=rssi_implausible,
        restarts=max(advances) if advances else None,
    )


# ==========================================================================
# 3. Zaman serileri (brief §8/4)
# ==========================================================================
@dataclass
class Timeline:
    """x = slot; y = nodes changing role in that slot, |C|, and sum of w."""

    slots: List[int]
    role_changes: List[int]
    cover_size: List[int]
    cover_weight: List[float]
    phase_bounds: Dict[int, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slots": self.slots,
            "role_changes": self.role_changes,
            "cover_size": self.cover_size,
            "cover_weight": self.cover_weight,
            "phase_bounds": {str(k): v for k, v in sorted(self.phase_bounds.items())},
        }


def timeline(
    logs: Dict[int, NodeLog],
    *,
    tau_ms: int,
    t0_ms: int,
    weights: Optional[Dict[int, float]] = None,
) -> Timeline:
    w = {int(k): float(v) for k, v in (weights or {}).items()}
    changes: Dict[int, int] = defaultdict(int)
    joined: Dict[int, int] = {}  # nid -> slot it first entered the cover
    phase_first: Dict[int, int] = {}
    last_slot = 0
    for nid, lg in logs.items():
        for r in lg.records:
            slot = (int(r["t_ms"]) - t0_ms) // int(tau_ms)
            last_slot = max(last_slot, slot)
            ev = r.get("event")
            if ev in ROLE_EVENTS:
                if ev == "mis_decided" and r.get("role") == "OUT":
                    continue
                changes[slot] += 1
                joined.setdefault(nid, slot)
            elif ev == "tx":
                ph = int(r.get("phase", 0))
                if ph not in phase_first or slot < phase_first[ph]:
                    phase_first[ph] = slot
    slots = list(range(last_slot + 1))
    size: List[int] = []
    weight: List[float] = []
    for s in slots:
        inc = [n for n, js in joined.items() if js <= s]
        size.append(len(inc))
        weight.append(round(sum(w.get(n, 0.0) for n in inc), 6))
    return Timeline(
        slots=slots,
        role_changes=[changes.get(s, 0) for s in slots],
        cover_size=size,
        cover_weight=weight,
        phase_bounds=dict(sorted(phase_first.items())),
    )


# ==========================================================================
# 4. Comparison against the simulator (brief section 7, ordering item 2)
# ==========================================================================
@dataclass
class Discrepancy:
    metric: str
    emulator: Any
    simulator: Any

    @property
    def delta(self) -> Any:
        try:
            return self.emulator - self.simulator
        except TypeError:
            return None

    @property
    def rel(self) -> Optional[float]:
        try:
            if not self.simulator:
                return None
            return round((self.emulator - self.simulator) / self.simulator, 6)
        except TypeError:
            return None

    def __str__(self) -> str:
        r = "" if self.rel is None else f" ({self.rel:+.1%})"
        return (
            f"{self.metric}: emulator {self.emulator} / simulator {self.simulator}{r}"
        )


@dataclass
class SimComparison:
    """A lossless synchronous emulator run MUST reproduce the simulator (brief 7).

    A mismatch is A FINDING: it gets explained and quantified, never tuned away.
    The comparison is made against the SIMULATOR'S MEASURED values, not against
    the 214/20 figures in the document; that difference is understood and
    recorded in `ccvc/bb/BULGULAR_BB.md`.
    """

    matches: List[str]
    discrepancies: List[Discrepancy]
    cover_same: bool
    owner_same: bool
    emulator_cover: List[int]
    simulator_cover: List[int]

    @property
    def exact(self) -> bool:
        return not self.discrepancies and self.cover_same and self.owner_same

    def summary(self) -> str:
        if self.exact:
            return "the emulator reproduced the simulator EXACTLY"
        lines = [f"MISMATCH on {len(self.discrepancies)} metric(s)"]
        lines += [f"  - {d}" for d in self.discrepancies]
        if not self.cover_same:
            lines.append(
                f"  - cover differs: emulator {self.emulator_cover} / "
                f"simulator {self.simulator_cover}"
            )
        if not self.owner_same:
            lines.append("  - ownership assignment differs")
        return "\n".join(lines)


#: Metrics that must match EXACTLY on a lossless synchronous run.
STRICT_METRICS = ("slots", "tx", "rx", "bytes_tx", "max_payload", "total_weight")


def compare_with_sim(
    run: RunCounters,
    sim_run: Any,
    *,
    weights: Optional[Dict[int, float]] = None,
    metrics: Sequence[str] = STRICT_METRICS,
) -> SimComparison:
    """Compare emulator counters against a simulator run object."""
    w = {int(k): float(v) for k, v in (weights or {}).items()}
    tot = run.totals()
    emu: Dict[str, Any] = {
        "slots": run.slots,
        "tx": tot.tx,
        "rx": tot.rx,
        "bytes_tx": tot.bytes_tx,
        "max_payload": tot.max_payload,
        "retx": tot.retx,
        "total_weight": round(sum(w.get(v, 0.0) for v in run.cover), 6),
    }
    sim: Dict[str, Any] = {
        "slots": getattr(sim_run, "slots", None),
        "tx": getattr(sim_run, "tx", None),
        "rx": getattr(sim_run, "rx", None),
        "bytes_tx": getattr(sim_run, "bytes_tx", None),
        "max_payload": getattr(sim_run, "max_payload", None),
        "retx": getattr(sim_run, "retx", None),
        "total_weight": getattr(sim_run, "total_weight", None),
    }
    matches, diffs = [], []
    for m in metrics:
        if emu.get(m) == sim.get(m):
            matches.append(m)
        else:
            diffs.append(Discrepancy(m, emu.get(m), sim.get(m)))
    sim_cover = sorted(getattr(sim_run, "cover", []) or [])
    sim_owner = {edge(*e): v for e, v in (getattr(sim_run, "owner", {}) or {}).items()}
    return SimComparison(
        matches=matches,
        discrepancies=diffs,
        cover_same=(run.cover == sim_cover),
        owner_same=(run.owner == sim_owner),
        emulator_cover=run.cover,
        simulator_cover=sim_cover,
    )


# ==========================================================================
# 5. Rapor
# ==========================================================================
def report(
    run: RunCounters,
    *,
    target_edges: Optional[Iterable[Edge]] = None,
    weights: Optional[Dict[int, float]] = None,
    t_frame_ms: float = 0.7,
) -> Dict[str, Any]:
    tot = run.totals()
    w = {int(k): float(v) for k, v in (weights or {}).items()}
    doc: Dict[str, Any] = {
        "converged": run.converged,
        "slots": run.slots,
        "t_conv_ms": run.t_conv_ms,
        "t_conv_label": "maximum local quiescence timestamp; excludes harness guard and shutdown",
        "slots_label": "legacy local-quiescence-derived proxy; not a count of all station loop iterations",
        "tau_ms": run.tau_ms,
        "n_nodes": len(run.by_node),
        "totals": {
            "tx": tot.tx,
            "rx": tot.rx,
            "bytes_tx": tot.bytes_tx,
            "max_payload": tot.max_payload,
            "retx": tot.retx,
            "radio_on_ms": tot.radio_on_ms,
            "radio_on_label": "elapsed active phase until quiescence; not a physical radio measurement",
            "energy_mah_esp32_model": round(
                sum(c.energy_mah_esp32_model(t_frame_ms) for c in run.by_node.values()),
                6,
            ),
            "energy_label": Counters.ENERGY_LABEL,
            "by_type_tx": {str(k): v for k, v in sorted(tot.by_type_tx.items())},
            "by_phase_tx": {str(k): v for k, v in sorted(tot.by_phase_tx.items())},
        },
        "rx_attribution": "sender (api.Counters); receiver side in rx_delivered",
        "rx_delivered_total": sum(run.rx_delivered.values()),
        "cover": run.cover,
        "cover_weight": round(sum(w.get(v, 0.0) for v in run.cover), 6),
        "owner": {f"{u}-{v}": o for (u, v), o in sorted(run.owner.items())},
        "health": {
            "double_owned_edges": {
                f"{u}-{v}": nodes for (u, v), nodes in run.double_owned_edges().items()
            },
            "infeasible": run.infeasible,
            "unresolved": run.unresolved,
            "table_overflow": run.table_overflow,
            "id_rederivations": run.id_rederivations,
            "slot_overruns": run.slot_overruns,
            "truncated_lines": run.truncated_lines,
            "stale_records": run.stale_records,
            "unicast_unreachable": run.unicast_unreachable,
            "send_failures": run.send_failures,
            "rssi_failures": run.rssi_failures,
            "rssi_implausible": run.rssi_implausible,
            "restarts": run.restarts,
        },
        "asymmetric_claims": [list(p) for p in run.asymmetric_claims()],
    }
    if target_edges is not None:
        diff: TopologyDiff = compare_topology(target_edges, run.discovered_edges())
        doc["discovered_vs_target"] = diff.as_dict()
        doc["discovered_vs_target"]["summary"] = diff.summary()
    return doc


def collect(
    run_dir: str,
    *,
    tau_ms: int,
    t0_ms: Optional[int] = None,
    target_edges: Optional[Iterable[Edge]] = None,
    weights: Optional[Dict[int, float]] = None,
) -> Tuple[RunCounters, Dict[str, Any], Timeline]:
    logs = read_run(run_dir)
    run = counters_from_logs(logs, tau_ms=tau_ms, t0_ms=t0_ms)
    tl = timeline(logs, tau_ms=tau_ms, t0_ms=run.t0_ms, weights=weights)
    return run, report(run, target_edges=target_edges, weights=weights), tl


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="BB-CVC log collector")
    ap.add_argument("run_dir")
    ap.add_argument("--tau-ms", type=int, default=None)
    a = ap.parse_args(argv)
    meta_path = os.path.join(a.run_dir, "run.json")
    meta: Dict[str, Any] = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
    tau = a.tau_ms or int(meta.get("channel", {}).get("tau_ms", 0)) or 200
    weights = {int(k): float(v) for k, v in (meta.get("weights") or {}).items()}
    edges = [edge(int(u), int(v)) for u, v in (meta.get("edges") or [])] or None
    run, doc, tl = collect(
        a.run_dir,
        tau_ms=tau,
        t0_ms=meta.get("t0_ms"),
        target_edges=edges,
        weights=weights,
    )
    doc["timeline"] = tl.as_dict()
    print(json.dumps(doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
