#!/usr/bin/env python3
"""One process per station: run a `NodeCore` UNMODIFIED (brief section 7).

THIS IS THE CLAIM THE ARCHITECTURE RESTS ON. This file imports a node class,
constructs it, and feeds it two events: `on_frame` and `on_timer`. No subclass,
no monkeypatching, no extra call. Not one line of node code changes in order to
run on mininet-wifi, and `test_mnwifi.py` asserts that on the object rather than
on the source text.

IT IS NOT TIED TO ONE IMPLEMENTATION. `NODE_KINDS` maps a name to a
(node class, params class) pair, and `--node` selects one. That matters beyond
convenience: a claim of platform independence made with a single implementation
is barely a claim at all. Running a SECOND, independently written `NodeCore`
over the same four platform calls turns "the node code does not depend on the
platform" from an assertion into a comparison. Both entries below have the
identical constructor signature `(weight, platform, params, capacity_k)`, and
that is not a coincidence -- it is `api.NodeCore`'s contract.

THE PROCESS LOOP IS THE SCHEDULER'S COUNTERPART, not part of the algorithm.
`sched.SyncScheduler` drains the queue at the slot boundary and then fires
`on_timer` once per node. The loop here reproduces that order in one process:

    start of slot t:  frames that arrived in slot t-1 -> on_frame
                      on_timer("tick")
                      sleep until the start of slot t+1

Which slot a frame belongs to is read from the KERNEL ARRIVAL TIMESTAMP
(`SO_TIMESTAMPNS`), never from the sender's claim; the payload is never opened.

TERMINATION. A node CANNOT KNOW about global quiescence (I1). So the process
never closes itself: every time `done` becomes true it writes a `node_done`
record (radio-on time is derived from the latest one), every time it becomes
false again it writes `node_undone`, and it KEEPS LISTENING, because its
neighbours may still need its ACKs. An epoch restart takes a done node out of
done; with one stamp per process the orchestrator and the collector could not
see that (Amendment 18). The run is ended by
the orchestrator, which watches the logs and drops a `STOP` file. That is the
exact counterpart of `Scheduler`'s role in the simulator.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import hashlib
import os
import signal
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

from ccvc.bb.api import NodeCore  # noqa: E402
from ccvc.bb.bootstrap import hash16  # noqa: E402
from ccvc.bb.mnwifi.topology import format_mac, parse_mac, peers_from_json  # noqa: E402
from ccvc.bb.mnwifi.udp_port import (
    AddressMap,
    DropRule,
    JsonlLog,  # noqa: E402
    RssiReader,
    RxFrame,
    UdpPort,
)

STOP_FILE = "STOP"

#: Selectable node implementations: name -> (module, node class, params class).
#: Resolved lazily so that importing this module does not drag in every
#: algorithm variant, and so a broken variant cannot stop the others running.
#:
#: THESE KEYS ARE NOT ARM NAMES AND WERE DELIBERATELY LEFT ALONE WHEN THE ARMS
#: WERE RENAMED. A key here names an IMPLEMENTATION, and it is written into
#: every archived `run.json` as `node_kind` and into the `--node` command line
#: recorded with each prepared station plan; renaming one would make the
#: archived runs unverifiable against the code that produced them. `gccvc`,
#: `grccvc` and `gwccvc` are additionally the function names inside the pinned
#: `external_sources/MWCCVC` checkout, so they are the upstream's spelling and
#: not ours to change. The reader-facing names live in `ccvc/bb/armnames.py`;
#: `ccvc.greedy.audit.ARM_CONFIGS` is the map from an arm to the kind it runs.
NODE_KINDS: Dict[str, Tuple[str, str, str]] = {
    "bbcvc": ("ccvc.bb.bbcvc", "BbcvcNode", "BbcvcParams"),
    "wuli": ("ccvc.bb.v5_wuli", "WuLiNode", "WuLiParams"),
    "gccvc": ("ccvc.greedy.distributed", "GccvcNode", "GreedyParams"),
    "grccvc": ("ccvc.greedy.distributed", "GrccvcNode", "GreedyParams"),
    "gwccvc": ("ccvc.greedy.distributed", "GwccvcNode", "GreedyParams"),
    "anneal": ("ccvc.bb.anneal", "AnnealNode", "AnnealParams"),
    # DFS-Spanning-Backbone and GHS-MST-Backbone replace Phase 1 only, so they
    # reuse BbcvcParams unchanged. Both satisfy the same
    # `(weight, platform, params, capacity_k)` constructor, and
    # registering them here is what makes their arms launchable on the emulator
    # rather than simulator-only.
    "dfs": ("ccvc.bb.variants", "V1DfsNode", "BbcvcParams"),
    "mst": ("ccvc.bb.v4_mst", "V4MstDistNode", "BbcvcParams"),
}


def resolve_node_kind(name: str) -> Tuple[type, type]:
    """Look up (node class, params class) for a registered implementation."""
    if name not in NODE_KINDS:
        raise SystemExit(f"unknown node kind {name!r}; " f"known: {sorted(NODE_KINDS)}")
    mod_name, cls_name, par_name = NODE_KINDS[name]
    mod = __import__(mod_name, fromlist=[cls_name, par_name])
    node_cls = getattr(mod, cls_name)
    if not issubclass(node_cls, NodeCore):
        raise SystemExit(f"{cls_name} is not a NodeCore")
    return node_cls, getattr(mod, par_name)


def build_params(params_cls: type, **wanted: Any) -> Any:
    """Construct a params object, passing only fields it actually declares.

    Different implementations carry different knobs. Filtering here keeps the
    launcher from having to know which ones each variant supports, and makes an
    unknown option a silent no-op rather than a crash at station start-up.
    """
    fields = {f.name for f in dataclasses.fields(params_cls)}
    return params_cls(
        **{k: v for k, v in wanted.items() if k in fields and v is not None}
    )


# ==========================================================================
# 1. Set-up
# ==========================================================================
def build_port(
    peers_doc: Dict[str, object],
    my_mac: int,
    log_dir: str,
    *,
    broadcast: str = "subnet",
    iface: Optional[str] = None,
    rssi_period_ms: int = 500,
    bind_device: bool = True,
    rssi_runner=None,
    drops=None,
    reach=None,
    epoch_ms: int = 0,
) -> UdpPort:
    """Build a port from the address table. FIND your own identity from the MAC."""
    peers = peers_from_json(peers_doc)
    me = next((nid for nid, p in peers.items() if p.mac == my_mac), None)
    if me is None:
        raise SystemExit(f"MAC not in the table: {format_mac(my_mac)}")
    amap = AddressMap(peers, me, broadcast=broadcast, reach=reach)
    nid = hash16(my_mac)  # the same identity the node will derive itself
    jlog = JsonlLog(os.path.join(log_dir, f"{nid}.jsonl"))
    reader = None
    if iface:
        reader = RssiReader(iface, period_ms=rssi_period_ms, runner=rssi_runner)
    return UdpPort(
        amap,
        jlog,
        rssi=reader,
        drops=drops,
        epoch_ms=epoch_ms,
        bind_device=iface if (bind_device and iface) else None,
    )


def resolve_mac(mac_arg: Optional[str], iface: Optional[str]) -> int:
    """OBTAIN the MAC: the explicit argument first, otherwise the interface.

    Reading it from the interface is the real path; `--mac` exists only for
    interface-less (loopback) testing. With neither, the process REFUSES TO
    START: inventing an identity would turn bootstrap's identity-derivation path
    (brief 3.5/1) into dead code.
    """
    if mac_arg:
        return parse_mac(mac_arg)
    if iface:
        return read_iface_mac(iface)
    raise SystemExit("either --mac or --iface must be given")


def read_iface_mac(iface: str) -> int:
    """The interface's REAL MAC. This is the emulator's counterpart of
    `esp_wifi_get_mac`; identity is DERIVED from it and handed over from
    nowhere (brief 3.5/1)."""
    with open(f"/sys/class/net/{iface}/address", encoding="utf-8") as fh:
        return parse_mac(fh.read().strip())


# ==========================================================================
# 2. Loop
# ==========================================================================
class NodeRunner:
    """The in-process scheduler. It CANNOT SEE node internals; it feeds two events."""

    #: How it is decided WHICH SLOT a frame is processed in.
    #:
    #:   "stamp"    kernel arrival time. PRODUCTION MODE. A frame arriving in
    #:              slot t is processed in slot t+1, which is what
    #:              `sched.SyncScheduler` means. With one node per process it is
    #:              safe to drain inside `step`: the timestamp states the frame's
    #:              true slot regardless of WHEN it was drained.
    #:
    #:   "boundary" every drained frame is processed in the CURRENT slot. This
    #:              is correct only when `poll` is called AT THE SLOT BOUNDARY,
    #:              BEFORE ANY SEND in that slot: whatever is then in the socket
    #:              was sent in the previous slot, so it is due exactly now. It
    #:              exists for deterministic single-process replay on a virtual
    #:              clock, where a kernel timestamp cannot be aligned.
    DEFER_POLICIES = ("stamp", "boundary")

    def __init__(
        self,
        node: NodeCore,
        port: UdpPort,
        *,
        mode: str,
        tau_ms: int,
        deadline_ms: int,
        log_dir: str,
        sleeper=time.sleep,
        clock=time.time,
        defer: str = "stamp",
    ) -> None:
        if mode not in ("sync", "async"):
            raise ValueError(f"unknown mode: {mode!r}")
        if defer not in self.DEFER_POLICIES:
            raise ValueError(f"unknown defer policy: {defer!r}")
        self.defer = defer
        self.late_frames = 0
        self.node = node
        self.port = port
        self.mode = mode
        self.tau_ms = int(tau_ms)
        self.deadline_ms = int(deadline_ms)
        self.log_dir = log_dir
        self._sleep = sleeper
        self._clock = clock
        self.stop = False
        self.slots = 0
        self.done_ms: Optional[int] = None  # latest entry into done, end of slot
        self._was_done = False
        #: slot -> frames TO BE PROCESSED in that slot (arrival slot + 1)
        self._deferred: Dict[int, List[RxFrame]] = {}

    # -- one slot ---------------------------------------------------------
    def poll(self, slot: int) -> None:
        """Drain the socket, deferring each frame to the slot it is due in.

        Kept SEPARATE from `fire` because deterministic replay of several nodes
        in one process must, like `sched.SyncScheduler`, drain EVERY node's queue
        FIRST and only then fire every timer. In a real deployment there is one
        node per process and `step` calls the two back to back; the ordering
        there is already resolved correctly by the kernel arrival timestamp.
        """
        for f in self.port.receive():
            due = self._due_slot(f, slot)
            if due > slot + 1:
                # The frame arrived across a slot boundary, so it will be
                # processed ONE SLOT LATE. This is the only place the emulator
                # deviates from the simulator and it is forbidden to stay
                # silent about it; the count is reported.
                self.late_frames += 1
                self.port.log("late_frame", due=due, slot=slot)
            self._deferred.setdefault(max(due, slot), []).append(f)

    def fire(self, slot: int) -> None:
        """Deliver the frames that are due, then fire the timer."""
        for s in sorted(k for k in self._deferred if k <= slot):
            for f in self._deferred.pop(s):
                self.node.on_frame(f.src_mac, f.rssi, f.payload)
        self.node.on_timer("tick")
        self.slots += 1
        done_now = bool(self.node.done)
        if done_now and not self._was_done:
            # A distinct name so it cannot be confused with the node's own
            # `done` event: this stamp is THE SCHEDULER'S observation, and
            # radio-on time is derived from it.
            #
            # It is stamped at the END of the slot, not the start. The reason is
            # fidelity: `sched._BaseScheduler._mark_done` marks quiescence at
            # `t_end = (i+1)*tau`. Stamping at the slot start would understate
            # both radio-on time and the slot count by one slot.
            self.done_ms = (slot + 1) * self.tau_ms
            self.port.log(
                "node_done",
                role=int(self.node.role),
                phase=int(self.node.phase),
                slot=slot,
                t_end_ms=self.done_ms,
            )
        elif self._was_done and not done_now:
            # Amendment 18: leaving done is recorded, so the last record of each
            # node says whether its LATEST state is done.
            self.port.log(
                "node_undone",
                role=int(self.node.role),
                phase=int(self.node.phase),
                slot=slot,
                t_end_ms=(slot + 1) * self.tau_ms,
            )
        self._was_done = done_now

    def step(self, slot: int) -> None:
        self.poll(slot)
        self.fire(slot)

    @property
    def pending(self) -> int:
        """Frames deferred but not yet delivered.

        The counterpart of `SimNet.in_flight`: the orchestrator only concludes
        the run is genuinely over when this is zero (quiescence AND no frame in
        flight).
        """
        return sum(len(v) for v in self._deferred.values())

    def _due_slot(self, f: RxFrame, slot: int) -> int:
        if self.mode != "sync":
            return slot  # async: processed on arrival
        if self.defer == "boundary":
            return slot
        return (f.t_recv_ms // self.tau_ms) + 1

    # -- run --------------------------------------------------------------
    def run(self, t0_ms: int) -> None:
        slot0 = t0_ms // self.tau_ms
        while not self.stop:
            now = self.port.now_ms()
            if now >= self.deadline_ms:
                self.port.log("deadline", slot=self.slots)
                break
            if self._stop_requested():
                self.port.log("stop_file", slot=self.slots)
                break
            slot = now // self.tau_ms
            self.port.log("tick", slot=slot - slot0)
            self.step(slot)
            target = (slot + 1) * self.tau_ms
            gap = target - self.port.now_ms()
            if gap > 0:
                self._sleep(gap / 1000.0)
            elif self.mode == "sync":
                # Slot missed: the node could not finish inside tau. This is the
                # one event that BREAKS synchronous fidelity, and it is
                # forbidden to stay silent about it.
                self.port.log("slot_overrun", slot=slot - slot0, over_ms=-gap)

    def _stop_requested(self) -> bool:
        return os.path.exists(os.path.join(self.log_dir, STOP_FILE))


# ==========================================================================
# 3. Entry point
# ==========================================================================
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="BB-CVC station process")
    ap.add_argument("--peers", required=True, help="path to peers.json")
    ap.add_argument("--log-dir", required=True)
    ap.add_argument(
        "--iface", default=None, help="staX-wlan0; used for RSSI and for binding"
    )
    ap.add_argument(
        "--mac",
        default=None,
        help="give the MAC explicitly (when there is no interface); "
        "otherwise it is read from the interface",
    )
    ap.add_argument(
        "--node",
        choices=sorted(NODE_KINDS),
        default="bbcvc",
        help="which NodeCore implementation to run",
    )
    ap.add_argument("--weight", type=float, required=True)
    ap.add_argument("--k", type=int, required=True)
    ap.add_argument("--mode", choices=("sync", "async"), default="sync")
    ap.add_argument("--tau-ms", type=int, required=True)
    ap.add_argument("--t-hello-ms", type=int, required=True)
    ap.add_argument("--max-ms", type=int, default=600_000)
    ap.add_argument(
        "--start-at-ms",
        type=int,
        default=0,
        help="shared start timestamp; 0 means start immediately",
    )
    ap.add_argument("--broadcast", choices=("subnet", "fanout"), default="subnet")
    ap.add_argument("--rssi-period-ms", type=int, default=500)
    ap.add_argument("--mis-nbrs-max", type=int, default=5)
    ap.add_argument("--nbr-table-max", type=int, default=64)
    ap.add_argument(
        "--params-json",
        default=None,
        help="Saved deployment parameters; unknown fields are rejected",
    )
    ap.add_argument(
        "--drop",
        action="append",
        default=[],
        help="measurement hook, e.g. 'mtype=0,count=1,after_ms=2000'",
    )
    ap.add_argument(
        "--reach",
        default=None,
        help="LOOPBACK TESTING ONLY. In-range MACs, comma separated. "
        "NEVER supplied on a mininet-wifi run: the radio "
        "(wmediumd) decides range, not the wrapper.",
    )
    a = ap.parse_args(argv)

    with open(a.peers, encoding="utf-8") as fh:
        peers_doc = json.load(fh)
    my_mac = resolve_mac(a.mac, a.iface)
    node_cls, params_cls = resolve_node_kind(a.node)

    # The clock's zero point is THE START OF THE RUN; without `--start-at-ms`
    # it is this process's own start. It is rounded to a multiple of tau so slot
    # alignment is not disturbed (see UdpPort.epoch_ms).
    epoch = (
        int(a.start_at_ms)
        if a.start_at_ms
        else ((int(time.time() * 1000) // a.tau_ms) * a.tau_ms)
    )
    port = build_port(
        peers_doc,
        my_mac,
        a.log_dir,
        broadcast=a.broadcast,
        iface=a.iface,
        rssi_period_ms=a.rssi_period_ms,
        drops=[DropRule.parse(d) for d in a.drop],
        epoch_ms=epoch,
        reach=None
        if not a.reach
        else [parse_mac(m) for m in a.reach.split(",") if m.strip()],
    )

    saved = {}
    params_sha256 = None
    if a.params_json:
        raw = open(a.params_json, "rb").read()
        saved = json.loads(raw)
        if not isinstance(saved, dict):
            raise ValueError("Deployment parameters must be a JSON object")
        unknown = set(saved) - {f.name for f in dataclasses.fields(params_cls)}
        if unknown:
            raise ValueError(f"Unknown deployment parameter fields: {sorted(unknown)}")
        for key, value in (
            ("t_hello_ms", a.t_hello_ms),
            ("mis_nbrs_max", a.mis_nbrs_max),
            ("nbr_table_max", a.nbr_table_max),
        ):
            if key in saved and saved[key] != value:
                raise ValueError(f"Saved {key} disagrees with the station command")
        params_sha256 = hashlib.sha256(raw).hexdigest()
    settings = dict(
        t_hello_ms=a.t_hello_ms,
        mis_nbrs_max=a.mis_nbrs_max,
        nbr_table_max=a.nbr_table_max,
    )
    settings.update(saved)
    params = build_params(
        params_cls,
        **settings,
    )
    # === THE ARCHITECTURAL CLAIM: the node is constructed UNWRAPPED and
    # === UNMODIFIED, through the contract every NodeCore shares.
    node = node_cls(a.weight, port, params, a.k)
    port.set_phase_source(lambda: node.phase)

    from ccvc.greedy.compare import fingerprint as code_fingerprint

    port.log(
        "run_start",
        code_fingerprint=code_fingerprint(),
        node_kind=a.node,
        mode=a.mode,
        tau_ms=a.tau_ms,
        t_hello_ms=a.t_hello_ms,
        k=a.k,
        weight=a.weight,
        params_sha256=params_sha256,
        network_namespace_inode=os.stat("/proc/self/ns/net").st_ino,
        nid=node.nid,
        iface=a.iface or "",
        pid=os.getpid(),
        max_ms=a.max_ms,
        epoch_wall_ms=epoch,
    )

    # Shared clock: every station shares the host kernel's clock, so slot
    # alignment via floor(t/tau) is EXACT here. On an ESP32 it would only be
    # approximate, and the report says so (brief section 7).
    while port.now_ms() < 0:
        time.sleep(min(0.02, max(0.0, -port.now_ms() / 1000.0)))
    t0 = 0  # the clock now counts relative to the run

    runner = NodeRunner(
        node,
        port,
        mode=a.mode,
        tau_ms=a.tau_ms,
        deadline_ms=a.max_ms,
        log_dir=a.log_dir,
    )

    def _bye(_sig, _frm):
        runner.stop = True

    signal.signal(signal.SIGTERM, _bye)
    signal.signal(signal.SIGINT, _bye)

    try:
        runner.run(t0)
    finally:
        # `getattr` throughout: the fields below are what BB-CVC exposes, and a
        # different NodeCore need not carry all of them. A missing field must
        # degrade the record, never abort the run.
        snap = node.snapshot()
        owned = sorted(getattr(node, "owned", ()) or ())
        port.log(
            "run_end",
            node_kind=a.node,
            slots=runner.slots,
            role=int(node.role),
            phase=int(node.phase),
            done=bool(node.done),
            deg=getattr(node, "deg", None)
            if getattr(node, "deg", None) is not None
            else -1,
            key_fp=-1 if getattr(node, "key_fp", None) is None else int(node.key_fp),
            epoch=int(getattr(node, "epoch", 0)),
            epoch_advance=getattr(node, "epoch_advance", None),
            owned=[list(e) for e in owned],
            bidir=sorted(
                int(u) for u in (node.edges() if hasattr(node, "edges") else ())
            ),
            forced_load=int(snap.forced_load),
            infeasible=bool(getattr(node, "infeasible", False)),
            unresolved=bool(getattr(node, "unresolved", False)),
            table_overflow=int(getattr(node, "table_overflow", 0)),
            id_rederivations=int(getattr(node, "id_rederivations", 0)),
            rssi_implausible=int(getattr(node, "rssi_implausible", 0)),
            late_frames=int(runner.late_frames),
            dropped_by_rule=int(port.dropped_by_rule),
            rssi_reads=(port.rssi.reads if port.rssi else 0),
            rssi_failures=(port.rssi.failures if port.rssi else 0),
        )
        port.jlog.close()
        port.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
