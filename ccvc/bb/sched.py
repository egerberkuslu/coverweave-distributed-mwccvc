#!/usr/bin/env python3
"""Two schedulers, ONE node implementation (brief 3.2, api I4).

Node code CANNOT LEARN which scheduler it is running under. Three rules make
that true:

  1. Both schedulers hand the node the same two events: `on_frame` and
     `on_timer`. There is no other entry point.
  2. The timer name is `TIMER_TICK` in both. Synchronously it fires once per
     slot; asynchronously it fires per node at a `tick_ms` period with a
     per-node phase offset. The node cannot tell the modes apart by name.
  3. Time is read only through `Platform.now_ms()`. Synchronously that value
     lands on slot boundaries and asynchronously it does not; to the node both
     are simply "the clock". The notion of a slot never enters node code
     (brief 3.5/7: the timer and the seq/ACK queue live inside the node, the
     engine does not supply them).

Termination is identical in both: every node reports `done` AND nothing is in
flight. If the wall budget runs out we exit with `converged=False`.
"""
from __future__ import annotations

import heapq
import os
import random
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import wire  # noqa: E402
from ccvc.bb.api import (Counters, NodeCore, NodeSnapshot, Platform, Role,  # noqa: E402
                         RunOutcome, Scheduler)
from ccvc.bb.simnet import Delivery, SimNet  # noqa: E402

#: The same name in both modes. Node code cannot infer the mode from it.
TIMER_TICK = "tick"


# --------------------------------------------------------------------------
# ortak taban
# --------------------------------------------------------------------------
class _BaseScheduler(Scheduler):
    def __init__(self, net: SimNet, nodes: Dict[int, NodeCore], *,
                 weights: Optional[Dict[int, float]] = None) -> None:
        self.net = net
        self.nodes = dict(nodes)
        self.order: List[int] = sorted(self.nodes)
        self.weights = dict(weights or {})
        for nid, node in self.nodes.items():
            net.attach(nid, node)

    # -- helpers ----------------------------------------------------------
    def _mark_done(self, t_ms: int) -> List[int]:
        """Mark newly quiescent nodes and return the list of them."""
        fresh = []
        for nid in self.order:
            if self.nodes[nid].done and self.net.done_ms(nid) is None:
                self.net.mark_done(nid, t_ms)
                fresh.append(nid)
        return fresh

    def _all_done(self) -> bool:
        return all(self.nodes[nid].done for nid in self.order)

    def _snapshots(self) -> Dict[int, NodeSnapshot]:
        snaps: Dict[int, NodeSnapshot] = {}
        for nid in self.order:
            s = self.nodes[nid].snapshot()
            # Counters come from the network, not from the node (api: a node
            # does not report its own counters).
            s.counters = self.net.counters[nid]
            snaps[nid] = s
        return snaps

    def _outcome(self, *, converged: bool, slots: Optional[int],
                 t_conv_ms: Optional[int], notes: List[str]) -> RunOutcome:
        snaps = self._snapshots()
        cover = sorted(nid for nid, s in snaps.items() if s.role.in_cover)
        owner: Dict[Tuple[int, int], int] = {}
        for nid, s in snaps.items():
            for (u, v) in s.owned:
                owner[(u, v) if u <= v else (v, u)] = nid
        total = sum(float(self.weights.get(nid, 0.0)) for nid in cover)
        return RunOutcome(
            scheduler=self.name,
            cover=cover,
            owner=owner,
            total_weight=round(total, 6),
            counters_by_node={nid: self.net.counters[nid] for nid in self.order},
            slots=slots,
            t_conv_ms=t_conv_ms,
            converged=converged,
            notes=notes,
        )


# --------------------------------------------------------------------------
# synchronous: slotted
# --------------------------------------------------------------------------
class SyncScheduler(_BaseScheduler):
    """Time is divided into slots of length tau (brief 3.2).

    A frame sent during slot t is processed at the START of slot t+1. The flow
    of one slot is: deliver the previous slot's frames, then fire the timer
    once on each node. That order enforces "not processed in the slot it was
    sent" by draining the queue at the slot boundary.

    `SimNet.delay` is IGNORED in this mode: in a slot model the delay is one
    full slot by definition. The delay distribution matters only asynchronously.

    Budget: `run(max_ms)` runs at most `max_ms // tau_ms` slots.
    """

    name = "sync"

    def __init__(self, net: SimNet, nodes: Dict[int, NodeCore], *,
                 tau_ms: int = 200, weights: Optional[Dict[int, float]] = None) -> None:
        super().__init__(net, nodes, weights=weights)
        if tau_ms <= 0:
            raise ValueError("tau_ms must be > 0")
        self.tau_ms = int(tau_ms)

    def run(self, max_ms: int) -> RunOutcome:
        budget = int(max_ms) // self.tau_ms
        notes: List[str] = [f"tau_ms={self.tau_ms}", f"budget_slots={budget}"]
        slots = 0
        converged = False
        t_end = 0

        while slots < budget:
            t0 = slots * self.tau_ms
            self.net.set_now(t0)

            # 1) whatever was sent in the previous slot is delivered now
            for d in self.net.drain_all():
                self.net.deliver(d)

            # 2) timer: once per node, in a deterministic order
            for nid in self.order:
                self.net.set_now(t0)
                self.nodes[nid].on_timer(TIMER_TICK)

            slots += 1
            t_end = slots * self.tau_ms
            self.net.set_now(t_end)
            self._mark_done(t_end)

            if self._all_done() and self.net.in_flight == 0:
                converged = True
                break

        if not converged:
            notes.append("wall budget exhausted without quiescence")
        self.net.set_now(t_end)
        self.net.finalize(t_end)
        return self._outcome(converged=converged, slots=slots,
                             t_conv_ms=t_end if converged else None, notes=notes)


# --------------------------------------------------------------------------
# asynchronous: event driven
# --------------------------------------------------------------------------
class AsyncScheduler(_BaseScheduler):
    """No slots; every frame is processed on arrival (brief 3.2).

    The delay is arbitrary but finite and is configured through `SimNet.delay`.
    The timer fires on each node at a `tick_ms` period; the first firing time is
    drawn per node from [0, tick_ms) with a seeded generator, so nodes never
    align on a shared slot boundary. Time is reported in MILLISECONDS, not slots.
    """

    name = "async"

    def __init__(self, net: SimNet, nodes: Dict[int, NodeCore], *,
                 tick_ms: int = 200, seed: int = 0,
                 weights: Optional[Dict[int, float]] = None) -> None:
        super().__init__(net, nodes, weights=weights)
        if tick_ms <= 0:
            raise ValueError("tick_ms must be > 0")
        self.tick_ms = int(tick_ms)
        self.seed = int(seed)

    def run(self, max_ms: int) -> RunOutcome:
        max_ms = int(max_ms)
        notes: List[str] = [f"tick_ms={self.tick_ms}"]
        rng = random.Random(self.seed * 2654435761 + 0x27D4)

        heap: List[Tuple[int, int, int, int, Optional[Delivery]]] = []
        seq = 0
        for nid in self.order:
            seq += 1
            heapq.heappush(heap, (rng.randrange(self.tick_ms), seq, 0, nid, None))

        pending_deliveries = 0
        converged = False
        t = 0
        last_change_ms = 0

        while heap:
            t_evt, _, kind, nid, deliv = heapq.heappop(heap)
            if t_evt > max_ms:
                t = max_ms
                break
            t = t_evt
            self.net.set_now(t)

            if kind == 0:
                self.nodes[nid].on_timer(TIMER_TICK)
                seq += 1
                heapq.heappush(heap, (t + self.tick_ms, seq, 0, nid, None))
            else:
                pending_deliveries -= 1
                self.net.deliver(deliv)

            # frames born during a send enter the same heap carrying their own
            # absolute delivery times
            for d in self.net.drain_all():
                seq += 1
                pending_deliveries += 1
                heapq.heappush(heap, (d.t_ms, seq, 1, d.dst, d))

            if self._mark_done(t):
                last_change_ms = t

            if self._all_done() and pending_deliveries == 0:
                converged = True
                break

        if not converged:
            notes.append("wall budget exhausted without quiescence")
        t_final = t if converged else max_ms
        self.net.set_now(t_final)
        self.net.finalize(t_final)
        return self._outcome(converged=converged, slots=None,
                             t_conv_ms=max(last_change_ms, t_final) if converged else None,
                             notes=notes)


# --------------------------------------------------------------------------
# calibration node
# --------------------------------------------------------------------------
class TrivialHelloNode(NodeCore):
    """A node that DECIDES NOTHING: it broadcasts one HELLO per timer firing.

    It exists to calibrate the accounting. On the brief's worked example of 10
    nodes and 15 edges, a lossless 20-slot run must produce exactly 200 tx and
    600 rx (10 broadcasts per slot, a degree sum of 30 deliveries per slot).

    It does not know which scheduler it runs under: it sees only the `on_timer`
    name and the value of `now_ms()`.
    """

    def __init__(self, nid: int, weight: float, plat: Platform) -> None:
        self.nid = nid
        self.weight = weight
        self.plat = plat
        self.phase = 0
        self.role = Role.OUT
        self.mac = getattr(plat, "mac", None)
        self.seen: Dict[int, int] = {}      # neighbour MAC -> time last heard
        self.rssi: Dict[int, float] = {}
        self.hellos_sent = 0
        self.frames_rx = 0

    def on_frame(self, src: int, rssi: Optional[float], payload: bytes) -> None:
        # `src` is the sender's MAC (frame header). The `src` inside the
        # payload is the 16-bit application id; the two are different things.
        msg = wire.decode(payload)
        self.frames_rx += 1
        self.seen[src] = self.plat.now_ms()
        if rssi is not None:
            self.rssi[src] = rssi

    def on_timer(self, name: str) -> None:
        if name != TIMER_TICK:
            return
        self.plat.send_broadcast(wire.encode(wire.Hello(
            src=self.nid, key=None, deg=len(self.seen), role=self.role,
            phase=self.phase, load=0, epoch=0, mis_nbrs=())))
        self.hellos_sent += 1

    def snapshot(self) -> NodeSnapshot:
        return NodeSnapshot(nid=self.nid, role=self.role, phase=self.phase,
                            key=None, deg=len(self.seen), owned=(), forced_load=0,
                            counters=Counters(), epoch=0)

    @property
    def done(self) -> bool:
        return False


class QuietAfterNode(TrivialHelloNode):
    """A node that goes quiet after `n_hello` broadcasts, to exercise termination."""

    def __init__(self, nid: int, weight: float, plat: Platform, n_hello: int = 3) -> None:
        super().__init__(nid, weight, plat)
        self.n_hello = n_hello

    def on_timer(self, name: str) -> None:
        if self.hellos_sent >= self.n_hello:
            return
        super().on_timer(name)

    @property
    def done(self) -> bool:
        return self.hellos_sent >= self.n_hello


def build(net: SimNet, weights: Dict[int, float], factory) -> Dict[int, NodeCore]:
    """Build one core per node. A core is given only its own id, its weight and
    its port; the graph is never given to it (I1)."""
    return {nid: factory(nid, weights.get(nid, 1.0), net.port(nid)) for nid in net.nodes}
