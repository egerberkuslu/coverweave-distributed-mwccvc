#!/usr/bin/env python3
"""Simulated network: a lossy/lossless implementation of `Platform` (brief 3.3, 3.4).

INVARIANTS
  I1  The true adjacency lives ONLY here. It is never leaked to node code by
      any route: a unicast to a non-neighbour is NOT an error, it is a frame
      that goes out on the air and reaches nobody. Raising would have told the
      node "that one was not my neighbour".
  I2  A node's contact with the outside world is four calls: send_broadcast,
      send_unicast, now_ms, log.

ADDRESSING: `src` AND `dst` ARE MACs, NOT node ids
  The port does NOT give the node its own id; it gives only its own MAC.
  The `src` in `on_frame(src, ...)` is the sender's 48-bit MAC. Under ESP-NOW
  and 802.11 the sender MAC is in the frame HEADER and comes off the radio;
  over UDP it comes off the socket. It is never placed in the payload. So
  `send_unicast(dst, ...)` addresses by MAC too: the only address a node holds
  for a peer is the MAC it read off a frame. The 16-bit node id is DERIVED as
  `id = hash16(MAC)` and can collide; addressing by it would misdeliver exactly
  when a collision occurs. A unicast to an unknown MAC behaves identically to a
  unicast to a non-neighbour: it goes out, reaches nobody, and raises nothing (I1).

ACCOUNTING (brief 3.3, api.Counters.record_tx)
  broadcast : tx += 1, rx += the number of neighbours that ACTUALLY received it.
              Loss reduces rx; it does not reduce tx.
  unicast   : tx += 1, rx += 1 if delivered, 0 if lost.
  The loss decision is made AT SEND TIME, so rx does not depend on whether the
  frame was ever dequeued.
  Because `Counters.record_tx` increments tx and rx on the same object, rx is
  attributed to the SENDER (the number of deliveries a node's transmissions
  caused). For the receiver side, `rx_delivered` is kept separately; the global
  totals are equal. `retx` is derived from the node's `log("retx")` call (api:
  "counters are derived from the log; a node does not report its own counters").

RECEIVER SIDE: THE ATTRIBUTION IS IN THE NAME
  `Counters.by_phase_tx` is the SENDER's phase and that is correct. Using the
  same pattern for the receiver side would write the sender's phase under the
  receiver's name: a node in Phase 5 may be processing a frame from a neighbour
  still in Phase 0. So receiver counters are kept SEPARATE and the attribution
  appears in their names:

      rx_at_receiver[nid]                        frames processed
      rx_by_receiver_phase[nid][phase]           receiver's phase at processing
      bytes_rx_by_receiver_phase[nid][phase]     same breakdown, in bytes
      rx_by_receiver_phase_type[nid][(phase,type)] phase x type cross-tab

  These are counted inside `deliver()`, at the moment the frame is PROCESSED.
  `rx_delivered` cannot stand in for them: it increments at `_enqueue`, so a
  frame queued in one phase and processed in another would land in the wrong
  phase. `rx_delivered` is left untouched because `mnwifi/collect.py` depends
  on its current meaning.

  Their totals are NOT equal and should not be: a frame still in flight when
  the run ends has been written to `Counters.rx` (decided at send time) but was
  never processed. The difference is between "deliveries produced" and
  "deliveries consumed".

radio_on_ms : the interval from the start of the run until that node reports
              DONE. For a node that never reports DONE, the whole run.

CHANNEL FAULTS (brief 3.4)
  `loss`/`link_loss` are probabilistic and UNDIRECTED. None of the four faults
  brief 3.4 exercises can be written with them, so there is a predicate hook:

      drop(t_ms, src, dst, msg_type) -> bool

  It is directed (1->2 can be broken while 2->1 works), it sees time (cut for
  three HELLO periods, then restore), and it sees the type (drop HELLO, deliver
  LINK). `src`/`dst` are NODE IDS, not MACs: this is a measurement hook, not
  something node code can see, and whoever writes a scenario already has the
  topology in node ids.

  The predicate DOES NOT GENERATE ITS OWN RANDOMNESS; it is a pure function of
  its four arguments. Anyone wanting probabilistic drops uses `loss`. The loss
  draw is taken INDEPENDENTLY of the predicate: the die is rolled even when the
  predicate drops the frame, so adding a predicate does not shift the loss
  pattern on other links.

  A frame dropped by the predicate behaves exactly like one dropped by loss: it
  is written to tx, not to rx, and `dropped` increases. The invariant
  `rx + dropped == degree sum` holds under the predicate too, and is tested.

  RSSI is either a dict as before or a `(t_ms, src, dst) -> float` callable;
  the callable exists so a link can be swung between -76 and -84 dBm over time
  and the hysteresis actually exercised.
"""
from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import wire  # noqa: E402
from ccvc.bb.api import Counters, NodeCore, Platform  # noqa: E402

Edge = Tuple[int, int]


def _norm(u: int, v: int) -> Edge:
    return (u, v) if u <= v else (v, u)


# MAC space: locally administered unicast (first octet bit 1 set, bit 0 clear).
_MAC_LOCAL = 0x020000000000
_MAC_MASK = 0xFFFFFFFFFF


def default_mac(nid: int) -> int:
    """A DETERMINISTIC 48-bit MAC derived from the node id.

    Seed-independent: the same topology always gets the same MACs. The
    splitmix64 mixing is deliberate; a scheme where the MAC equals the id would
    hide any bug that confuses the two.
    """
    x = (int(nid) + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 30
    x = (x * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 27
    x = (x * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 31
    return _MAC_LOCAL | (x & _MAC_MASK)


@dataclass(frozen=True)
class Delivery:
    """A single frame in flight."""

    t_ms: int
    order: int
    src: int
    dst: int
    rssi: Optional[float]
    payload: bytes


# --------------------------------------------------------------------------
# delay models
# --------------------------------------------------------------------------
def fixed_delay(ms: int) -> Callable[[int, int, random.Random], int]:
    def _f(src: int, dst: int, rng: random.Random) -> int:
        return ms
    return _f


def uniform_delay(lo_ms: int, hi_ms: int) -> Callable[[int, int, random.Random], int]:
    def _f(src: int, dst: int, rng: random.Random) -> int:
        return rng.randint(lo_ms, hi_ms)
    return _f


def exponential_delay(mean_ms: float, cap_ms: int = 10_000) -> Callable[[int, int, random.Random], int]:
    """Arbitrary but FINITE delay (the asynchronous model of brief 3.2)."""
    def _f(src: int, dst: int, rng: random.Random) -> int:
        return min(cap_ms, max(1, int(rng.expovariate(1.0 / mean_ms))))
    return _f


# --------------------------------------------------------------------------
# the network
# --------------------------------------------------------------------------
class SimNet:
    """The only object that knows the graph. Nodes speak only through `port(nid)`."""

    def __init__(
        self,
        nodes: Iterable[int],
        edges: Iterable[Edge],
        *,
        loss: float = 0.0,
        link_loss: Optional[Dict[Edge, float]] = None,
        delay: Callable[[int, int, random.Random], int] = None,
        rssi=None,
        drop: Optional[Callable[[int, int, int, int], bool]] = None,
        rssi_range: Optional[Tuple[float, float]] = (-85.0, -45.0),
        macs: Optional[Dict[int, int]] = None,
        seed: int = 0,
    ) -> None:
        self.nodes: List[int] = sorted(set(nodes))
        self._adj: Dict[int, List[int]] = {n: [] for n in self.nodes}
        self.edges: List[Edge] = []
        for u, v in edges:
            if u == v:
                raise ValueError(f"self-loop edge: {u}")
            e = _norm(u, v)
            if e in self.edges:
                continue
            for a in e:
                if a not in self._adj:
                    raise ValueError(f"edge touches an unknown node: {a}")
            self.edges.append(e)
            self._adj[e[0]].append(e[1])
            self._adj[e[1]].append(e[0])
        for n in self.nodes:
            self._adj[n].sort()

        self.loss = float(loss)
        self.link_loss: Dict[Edge, float] = {_norm(*k): float(v)
                                             for k, v in (link_loss or {}).items()}
        self.delay = delay or fixed_delay(1)
        self.seed = int(seed)

        # independent streams: loss and delay never shift each other's draws
        self._rng_loss = random.Random(self.seed * 2654435761 + 0x9E37)
        self._rng_delay = random.Random(self.seed * 2654435761 + 0x85EB)

        self.drop = drop
        self.rssi_fn: Optional[Callable[[int, int, int], float]] = None
        self.rssi: Dict[Edge, float] = {}
        if callable(rssi):
            self.rssi_fn = rssi
            rssi_range = None          # synthesis is meaningless with a callable
        else:
            self.rssi = {_norm(*k): float(v) for k, v in (rssi or {}).items()}
        if rssi_range is not None:
            rng = random.Random(self.seed * 2654435761 + 0xC2B2)
            lo, hi = rssi_range
            for e in self.edges:
                self.rssi.setdefault(e, round(rng.uniform(lo, hi), 2))

        # id -> MAC. Overridable from outside: exercising bootstrap's identity
        # collision path needs two different MACs landing on the same hash16.
        self.macs: Dict[int, int] = {n: default_mac(n) for n in self.nodes}
        self.macs.update({int(k): int(v) for k, v in (macs or {}).items()})
        if len(set(self.macs.values())) != len(self.macs):
            raise ValueError("MAC collision: two nodes were given the same MAC")
        self._by_mac: Dict[int, int] = {m: n for n, m in self.macs.items()}

        self.counters: Dict[int, Counters] = {n: Counters() for n in self.nodes}
        self.rx_delivered: Dict[int, int] = {n: 0 for n in self.nodes}
        # --- receiver side, at PROCESSING time (see the header note) ---
        self.rx_at_receiver: Dict[int, int] = {n: 0 for n in self.nodes}
        self.rx_by_receiver_phase: Dict[int, Dict[int, int]] = {n: {} for n in self.nodes}
        self.bytes_rx_by_receiver_phase: Dict[int, Dict[int, int]] = {n: {} for n in self.nodes}
        self.rx_by_receiver_phase_type: Dict[int, Dict[Tuple[int, int], int]] = {
            n: {} for n in self.nodes}
        self.dropped: int = 0           # total (probabilistic + predicate)
        self.dropped_by_rule: int = 0   # dropped by the `drop` predicate only
        self.log_records: List[Dict[str, Any]] = []
        self._log_observers: List[Callable[[Dict[str, Any]], None]] = []

        self._nodes_obj: Dict[int, NodeCore] = {}
        self._outbox: List[Delivery] = []
        self._order = 0
        self._now = 0
        self._done_ms: Dict[int, int] = {}

    # -- registration -----------------------------------------------------
    def attach(self, nid: int, node: NodeCore) -> None:
        if nid not in self._adj:
            raise ValueError(f"node not in the network: {nid}")
        self._nodes_obj[nid] = node

    def port(self, nid: int) -> Platform:
        if nid not in self._adj:
            raise ValueError(f"node not in the network: {nid}")
        return _Port(self, nid)

    def mac_of(self, nid: int) -> int:
        """The node's radio address. This is what goes in the frame header."""
        return self.macs[nid]

    def id_of_mac(self, mac: int) -> Optional[int]:
        """For MEASUREMENT; node code has no such table."""
        return self._by_mac.get(int(mac))

    def degree(self, nid: int) -> int:
        """For MEASUREMENT. Node code never calls this (I1)."""
        return len(self._adj[nid])

    def neighbors(self, nid: int) -> Tuple[int, ...]:
        """For MEASUREMENT and validation. Node code never calls this (I1)."""
        return tuple(self._adj[nid])

    # -- saat -------------------------------------------------------------
    def set_now(self, ms: int) -> None:
        self._now = int(ms)

    def now_ms(self) -> int:
        return self._now

    # -- kuyruk -----------------------------------------------------------
    @property
    def in_flight(self) -> int:
        return len(self._outbox)

    def drain_all(self) -> List[Delivery]:
        """Drain everything from the queue.

        The synchronous scheduler calls this at a slot boundary and ignores
        `t_ms` (in a slot model the delay is one full slot by definition). The
        asynchronous scheduler drains and re-files each item into its own event
        heap using `t_ms`.
        """
        out = sorted(self._outbox, key=lambda d: (d.t_ms, d.order))
        self._outbox = []
        return out

    # -- quiescence and radio-on time -------------------------------------
    def mark_done(self, nid: int, t_ms: int) -> None:
        if nid not in self._done_ms:
            self._done_ms[nid] = int(t_ms)
            self.counters[nid].radio_on_ms = int(t_ms)

    def done_ms(self, nid: int) -> Optional[int]:
        return self._done_ms.get(nid)

    def receiver_totals(self) -> Dict[str, Dict]:
        """Aggregated receiver-side breakdowns for the measurement side (figure 5)."""
        phase: Dict[int, int] = {}
        pbytes: Dict[int, int] = {}
        cross: Dict[Tuple[int, int], int] = {}
        for n in self.nodes:
            for ph, c in self.rx_by_receiver_phase[n].items():
                phase[ph] = phase.get(ph, 0) + c
            for ph, b in self.bytes_rx_by_receiver_phase[n].items():
                pbytes[ph] = pbytes.get(ph, 0) + b
            for key, c in self.rx_by_receiver_phase_type[n].items():
                cross[key] = cross.get(key, 0) + c
        return {"rx_by_receiver_phase": phase,
                "bytes_rx_by_receiver_phase": pbytes,
                "rx_by_receiver_phase_type": cross,
                "rx_at_receiver": sum(self.rx_at_receiver.values())}

    def finalize(self, t_ms: int) -> None:
        """Nodes that never reported DONE were listening for the whole run."""
        for n in self.nodes:
            if n not in self._done_ms:
                self.counters[n].radio_on_ms = int(t_ms)

    # -- iletim -----------------------------------------------------------
    def _loss_of(self, src: int, dst: int) -> float:
        return self.link_loss.get(_norm(src, dst), self.loss)

    def _rssi_of(self, src: int, dst: int) -> Optional[float]:
        if self.rssi_fn is not None:
            return float(self.rssi_fn(self._now, src, dst))
        return self.rssi.get(_norm(src, dst))

    def _drops(self, src: int, dst: int, mtype: int) -> bool:
        """Is this frame dropped from src to dst? The single decision point.

        The die is ALWAYS rolled, even when the predicate drops the frame, so
        that the alignment of the loss stream stays independent of the predicate.
        """
        roll = self._rng_loss.random()
        by_rule = self.drop is not None and bool(self.drop(self._now, src, dst, mtype))
        if by_rule:
            self.dropped_by_rule += 1
            return True
        return roll < self._loss_of(src, dst)

    def _enqueue(self, src: int, dst: int, payload: bytes) -> None:
        d_ms = self.delay(src, dst, self._rng_delay)
        self._order += 1
        self._outbox.append(Delivery(t_ms=self._now + int(d_ms), order=self._order,
                                     src=src, dst=dst,
                                     rssi=self._rssi_of(src, dst),
                                     payload=payload))

    def _phase_of(self, nid: int) -> int:
        node = self._nodes_obj.get(nid)
        return int(getattr(node, "phase", 0) or 0)

    def _account(self, nid: int, payload: bytes, fanout: int) -> None:
        mtype = int(wire.peek_type(payload))
        c = self.counters[nid]
        c.record_tx(mtype, self._phase_of(nid), len(payload), fanout)
        c.by_type_rx[mtype] = c.by_type_rx.get(mtype, 0) + fanout

    def _broadcast(self, src: int, payload: bytes) -> None:
        mtype = int(wire.peek_type(payload))
        arrivals = []
        for dst in self._adj[src]:
            if self._drops(src, dst, mtype):
                self.dropped += 1
            else:
                arrivals.append(dst)
        # rx falls with loss; tx does not
        self._account(src, payload, len(arrivals))
        for dst in arrivals:
            self.rx_delivered[dst] += 1
            self._enqueue(src, dst, payload)

    def _unicast(self, src: int, dst_mac: int, payload: bytes) -> None:
        # An unknown MAC and a non-neighbour MAC give the same outcome: the
        # frame goes out and nobody receives it. A node CANNOT tell them apart (I1).
        dst = self._by_mac.get(int(dst_mac))
        reachable = dst is not None and dst in self._adj[src]
        delivered = False
        if reachable:
            if self._drops(src, dst, int(wire.peek_type(payload))):
                self.dropped += 1
            else:
                delivered = True
        self._account(src, payload, 1 if delivered else 0)
        if delivered:
            self.rx_delivered[dst] += 1
            self._enqueue(src, dst, payload)
        elif not reachable:
            # I1: the node is not told; this only goes to the log.
            self._record_log(src, "unicast_unreachable", dst_mac=int(dst_mac))

    def _record_log(self, nid: int, event: str, **fields: Any) -> None:
        rec = {"t_ms": self._now, "nid": nid, "event": event}
        rec.update(fields)
        self.log_records.append(rec)
        if event == "retx":
            self.counters[nid].retx += int(fields.get("n", 1))
        for observer in self._log_observers:
            observer(rec)

    def add_log_observer(self, observer: Callable[[Dict[str, Any]], None]) -> None:
        """Attach measurement on the network side, without exposing it to nodes."""
        self._log_observers.append(observer)

    # -- teslim -----------------------------------------------------------
    def deliver(self, d: Delivery) -> None:
        node = self._nodes_obj.get(d.dst)
        if node is None:
            return
        # The phase is read IMMEDIATELY BEFORE processing: `on_frame` can
        # advance the node's phase, and attributing the frame to the new phase
        # would shift the breakdown.
        phase = self._phase_of(d.dst)
        mtype = int(wire.peek_type(d.payload))
        nbytes = len(d.payload)
        self.rx_at_receiver[d.dst] += 1
        bp = self.rx_by_receiver_phase[d.dst]
        bp[phase] = bp.get(phase, 0) + 1
        bb = self.bytes_rx_by_receiver_phase[d.dst]
        bb[phase] = bb.get(phase, 0) + nbytes
        pt = self.rx_by_receiver_phase_type[d.dst]
        pt[(phase, mtype)] = pt.get((phase, mtype), 0) + 1
        # The sender's MAC: it comes from the frame HEADER, not the payload.
        node.on_frame(self.macs[d.src], d.rssi, d.payload)


class _Port(Platform):
    """The world as one node sees it. There is nothing more than this."""

    __slots__ = ("_net", "_nid")

    def __init__(self, net: SimNet, nid: int) -> None:
        self._net = net
        self._nid = nid

    @property
    def mac(self) -> int:
        """The node's OWN radio address; on real hardware, esp_wifi_get_mac.

        `nid` is absent DELIBERATELY. A node's identity is COMPUTED as
        `id = hash16(MAC)` (brief 3.5/1); handed one ready-made, a node would
        never notice that its derived id differs from the one assigned to it,
        and the collision path would be dead code. SimNet keeps using node ids
        internally for routing and accounting; that is measurement, not node
        knowledge.
        """
        return self._net.macs[self._nid]

    def send_broadcast(self, payload: bytes) -> None:
        self._net._broadcast(self._nid, bytes(payload))

    def send_unicast(self, dst: int, payload: bytes) -> None:
        """`dst` is a MAC (48 bits), not a node id."""
        self._net._unicast(self._nid, dst, bytes(payload))

    def now_ms(self) -> int:
        return self._net.now_ms()

    def log(self, event: str, **fields: Any) -> None:
        self._net._record_log(self._nid, event, **fields)
