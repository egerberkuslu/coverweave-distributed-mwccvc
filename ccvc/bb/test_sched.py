#!/usr/bin/env python3
"""sched.py + simnet.py tests: accounting calibration, loss, determinism,
termination, and "one node implementation, two schedulers" (brief 3.2, 3.3, 3.4;
api I1-I4).

Run (from the repo root):
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_sched.py -q
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Dict, List, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import sched, simnet, wire  # noqa: E402
from ccvc.bb.api import (MAX_PAYLOAD, MsgType, NodeCore,  # noqa: E402
                         PayloadTooLarge, Role)

# --------------------------------------------------------------------------
# The worked example of brief section 12.6 / DISCOVERY section 9
# --------------------------------------------------------------------------
EDGES = [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (4, 5), (4, 6), (5, 6),
         (5, 7), (6, 7), (7, 8), (7, 9), (8, 9), (8, 10), (9, 10)]
WEIGHTS = {1: 5, 2: 2, 3: 4, 4: 3, 5: 6, 6: 2, 7: 3, 8: 2, 9: 5, 10: 4}
NODES = sorted(WEIGHTS)
DEG_SUM = 2 * len(EDGES)          # 30


def make_net(**kw) -> simnet.SimNet:
    kw.setdefault("delay", simnet.fixed_delay(1))
    kw.setdefault("seed", 7)
    return simnet.SimNet(NODES, EDGES, **kw)


def trivial(net: simnet.SimNet) -> Dict[int, NodeCore]:
    return sched.build(net, WEIGHTS, sched.TrivialHelloNode)


# --------------------------------------------------------------------------
# 1. accounting calibration: 200 tx / 600 rx
# --------------------------------------------------------------------------
def test_calibration_200_tx_600_rx():
    """The brief's worked example: lossless, 20 slots, a node that decides nothing.

    10 broadcasts per slot -> 200 tx over 20 slots.
    Degree sum 30 -> 30 deliveries per slot -> 600 rx.
    These numbers are the proof that the accounting matches the brief's table,
    and they must hold BEFORE any algorithm is written.
    """
    net = make_net(loss=0.0)
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200, weights=WEIGHTS).run(4000)

    assert out.slots == 20
    assert out.converged is False        # the trivial node never goes quiet
    tot = out.totals()
    assert tot.tx == 200
    assert tot.rx == 600
    assert tot.retx == 0
    # the broadcasts are all one type: HELLO
    assert tot.by_type_tx == {int(MsgType.HELLO): 200}
    assert tot.by_type_rx == {int(MsgType.HELLO): 600}
    # bytes: a HELLO without mis_nbrs is 13 B
    assert tot.bytes_tx == 200 * 13
    assert tot.max_payload == 13


def test_calibration_per_node_matches_degree():
    """rx is attributed to the sender: a node's rx must be its degree times slots."""
    net = make_net(loss=0.0)
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000)
    for nid in NODES:
        assert out.counters_by_node[nid].tx == 20
        assert out.counters_by_node[nid].rx == 20 * net.degree(nid)
    # the receiver side is kept separately and its global total is the same
    assert sum(net.rx_delivered.values()) == 600


def test_tx_and_rx_are_independent_metrics():
    """The foundation of the whole argument: tx and rx are not the same thing.

    The existing engine counted only rx (DISCOVERY section 3); here they are
    kept apart.
    """
    net = make_net(loss=0.0)
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000)
    tot = out.totals()
    assert tot.rx == 3 * tot.tx          # average degree 3
    assert tot.rx != tot.tx


# --------------------------------------------------------------------------
# 2. loss: rx falls, tx does not
# --------------------------------------------------------------------------
@pytest.mark.parametrize("loss", [0.05, 0.15])
def test_loss_reduces_rx_not_tx(loss):
    net = make_net(loss=loss)
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000)
    tot = out.totals()
    assert tot.tx == 200                      # the transmission count is unaffected by loss
    assert tot.bytes_tx == 200 * 13           # so are the bytes that went on the air
    assert 0 < tot.rx < 600                   # deliveries fall
    assert tot.rx + net.dropped == 600        # lost + delivered = the degree sum


def test_per_link_loss_overrides_default():
    """One link fully broken: that link's deliveries must be zero."""
    net = make_net(loss=0.0, link_loss={(1, 2): 1.0})
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000)
    # edge 1-2 is dead in both directions: 2 fewer deliveries per slot
    assert out.totals().rx == 600 - 2 * 20
    assert out.totals().tx == 200


def test_loss_is_seed_dependent_and_reproducible():
    a = make_net(loss=0.15, seed=1)
    ra = sched.SyncScheduler(a, trivial(a), tau_ms=200).run(4000).totals()
    b = make_net(loss=0.15, seed=1)
    rb = sched.SyncScheduler(b, trivial(b), tau_ms=200).run(4000).totals()
    c = make_net(loss=0.15, seed=2)
    rc = sched.SyncScheduler(c, trivial(c), tau_ms=200).run(4000).totals()
    assert ra.rx == rb.rx
    assert ra.rx != rc.rx


# --------------------------------------------------------------------------
# 3. determinism
# --------------------------------------------------------------------------
def _fingerprint(out) -> tuple:
    per_node = tuple(
        (nid, c.tx, c.rx, c.bytes_tx, c.max_payload, c.retx, c.radio_on_ms,
         tuple(sorted(c.by_type_tx.items())), tuple(sorted(c.by_type_rx.items())),
         tuple(sorted(c.by_phase_tx.items())))
        for nid, c in sorted(out.counters_by_node.items()))
    return (out.scheduler, tuple(out.cover), tuple(sorted(out.owner.items())),
            out.total_weight, out.slots, out.t_conv_ms, out.converged, per_node)


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_same_seed_gives_identical_outcome(mode):
    def once():
        net = make_net(loss=0.15, seed=11, delay=simnet.uniform_delay(1, 40))
        nodes = trivial(net)
        if mode == "sync":
            return sched.SyncScheduler(net, nodes, tau_ms=200, weights=WEIGHTS).run(4000)
        return sched.AsyncScheduler(net, nodes, tick_ms=200, seed=11,
                                    weights=WEIGHTS).run(4000)
    assert _fingerprint(once()) == _fingerprint(once())


def test_determinism_survives_a_fresh_interpreter():
    """The same result in separate processes under different PYTHONHASHSEED.

    The classic trap: hash randomness leaking through set or dict ordering.
    """
    prog = (
        "import sys; sys.path.insert(0, %r)\n"
        "from ccvc.bb import sched, simnet\n"
        "from ccvc.bb.test_sched import EDGES, WEIGHTS\n"
        "net = simnet.SimNet(sorted(WEIGHTS), EDGES, loss=0.15, seed=11,\n"
        "                    delay=simnet.uniform_delay(1, 40))\n"
        "o = sched.AsyncScheduler(net, sched.build(net, WEIGHTS, sched.TrivialHelloNode),\n"
        "                         tick_ms=200, seed=11, weights=WEIGHTS).run(4000)\n"
        "t = o.totals()\n"
        "print(t.tx, t.rx, t.bytes_tx, net.dropped,\n"
        "      [o.counters_by_node[n].rx for n in sorted(WEIGHTS)])\n"
    ) % os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    outs = set()
    for hashseed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=hashseed)
        r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip())
    assert len(outs) == 1, outs
    # loss hits rx, not tx: delivered + dropped = degree sum times ticks
    tx, rx, _, dropped, _ = eval(outs.pop().replace(" ", ", ", 4))
    assert tx == 200 and rx + dropped == 20 * DEG_SUM


def test_different_seed_changes_async_schedule():
    def once(seed):
        net = make_net(loss=0.0, seed=seed, delay=simnet.uniform_delay(1, 40))
        return sched.AsyncScheduler(net, trivial(net), tick_ms=200, seed=seed).run(4000)
    assert _fingerprint(once(1)) != _fingerprint(once(2))


# --------------------------------------------------------------------------
# 4. termination: quiescence and the wall budget
# --------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_never_quiet_node_hits_budget(mode):
    net = make_net(loss=0.0)
    nodes = trivial(net)
    out = (sched.SyncScheduler(net, nodes, tau_ms=200).run(4000) if mode == "sync"
           else sched.AsyncScheduler(net, nodes, tick_ms=200, seed=3).run(4000))
    assert out.converged is False
    assert out.t_conv_ms is None
    assert "wall budget exhausted without quiescence" in out.notes
    # the budget was not exceeded
    for c in out.counters_by_node.values():
        assert c.radio_on_ms == 4000


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_quiet_node_converges_before_budget(mode):
    net = make_net(loss=0.0)
    nodes = sched.build(net, WEIGHTS,
                        lambda nid, w, p: sched.QuietAfterNode(nid, w, p, n_hello=3))
    out = (sched.SyncScheduler(net, nodes, tau_ms=200, weights=WEIGHTS).run(40_000)
           if mode == "sync"
           else sched.AsyncScheduler(net, nodes, tick_ms=200, seed=3,
                                     weights=WEIGHTS).run(40_000))
    assert out.converged is True
    assert net.in_flight == 0
    assert out.totals().tx == 3 * len(NODES)     # three HELLOs per node
    assert out.totals().rx == 3 * DEG_SUM
    if mode == "sync":
        assert out.slots is not None and out.slots < 40_000 // 200
        assert out.t_conv_ms is not None
    else:
        assert out.slots is None
        assert 0 < out.t_conv_ms < 40_000        # milliseconds, not slots


def test_async_reports_milliseconds_not_slots():
    net = make_net(loss=0.0, delay=simnet.exponential_delay(15.0))
    nodes = sched.build(net, WEIGHTS,
                        lambda nid, w, p: sched.QuietAfterNode(nid, w, p, n_hello=2))
    out = sched.AsyncScheduler(net, nodes, tick_ms=200, seed=5).run(20_000)
    assert out.converged and out.slots is None and out.t_conv_ms is not None
    # radio-on time differs per node: asynchronously there is no shared slot boundary
    assert len({c.radio_on_ms for c in out.counters_by_node.values()}) > 1


# --------------------------------------------------------------------------
# 5. one node implementation, two schedulers (api I4)
# --------------------------------------------------------------------------
class ModeSniffer(sched.TrivialHelloNode):
    """A node that TRIES to work out the scheduler mode. It must not manage to."""

    def __init__(self, nid, weight, plat):
        super().__init__(nid, weight, plat)
        self.timer_names: set = set()
        self.api_surface = sorted(m for m in dir(plat) if not m.startswith("_"))

    def on_timer(self, name: str) -> None:
        self.timer_names.add(name)
        super().on_timer(name)


def test_identical_node_class_runs_under_both_schedulers():
    """The same CLASS and the same constructor; the only difference is the scheduler."""
    outs = {}
    sniffers = {}
    for mode in ("sync", "async"):
        net = make_net(loss=0.0)
        nodes = sched.build(net, WEIGHTS, ModeSniffer)
        sniffers[mode] = nodes
        outs[mode] = (sched.SyncScheduler(net, nodes, tau_ms=200, weights=WEIGHTS).run(4000)
                      if mode == "sync"
                      else sched.AsyncScheduler(net, nodes, tick_ms=200, seed=4,
                                                weights=WEIGHTS).run(4000))
    # the timer name the node sees is the same in both modes
    for mode in ("sync", "async"):
        for n in sniffers[mode].values():
            assert n.timer_names == {sched.TIMER_TICK}
    # the platform surface the node sees is the same in both modes, four calls only
    a = sniffers["sync"][1].api_surface
    b = sniffers["async"][1].api_surface
    assert a == b
    assert set(a) == {"log", "mac", "now_ms", "send_broadcast", "send_unicast"}
    # the same broadcast count: 20 ticks / 20 slots
    assert outs["sync"].totals().tx == outs["async"].totals().tx == 200
    assert outs["sync"].scheduler == "sync" and outs["async"].scheduler == "async"


def test_async_timers_are_not_slot_aligned():
    """Synchronously the firing times land on slot boundaries; asynchronously they do not."""
    stamps = {"sync": [], "async": []}

    def factory(mode):
        class Stamper(sched.TrivialHelloNode):
            def on_timer(self, name):
                stamps[mode].append(self.plat.now_ms())
                super().on_timer(name)
        return Stamper

    for mode, run in (("sync", True), ("async", False)):
        net = make_net(loss=0.0)
        nodes = sched.build(net, WEIGHTS, factory(mode))
        if run:
            sched.SyncScheduler(net, nodes, tau_ms=200).run(2000)
        else:
            sched.AsyncScheduler(net, nodes, tick_ms=200, seed=9).run(2000)

    assert all(t % 200 == 0 for t in stamps["sync"])
    assert any(t % 200 != 0 for t in stamps["async"])


def test_sync_message_is_delivered_in_the_next_slot():
    """A frame sent in slot t is NOT PROCESSED in slot t."""
    seen_at = []

    class Watcher(sched.TrivialHelloNode):
        def on_frame(self, src, rssi, payload):
            seen_at.append((self.plat.now_ms(), src))
            super().on_frame(src, rssi, payload)

    net = make_net(loss=0.0)
    nodes = sched.build(net, WEIGHTS, Watcher)
    sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)
    # the first broadcast is at t=0; the first delivery no earlier than t=200
    assert seen_at and min(t for t, _ in seen_at) == 200
    assert all(t % 200 == 0 for t, _ in seen_at)


# --------------------------------------------------------------------------
# 6. locality (api I1) and the platform surface (I2)
# --------------------------------------------------------------------------
def test_node_cannot_reach_the_graph_through_its_port():
    net = make_net()
    port = net.port(1)
    assert not hasattr(port, "neighbors")
    assert not hasattr(port, "degree")
    assert not hasattr(port, "edges")
    # the port does NOT hand over a node id either: id = hash16(MAC) is the
    # node's own computation. Given one ready-made, a node could never see its
    # derived id diverge from its assigned one, so the identity-collision path
    # would never fire.
    assert not hasattr(port, "nid")
    assert port.mac == net.mac_of(1)


def test_node_learns_neighbours_only_from_frames():
    """A node starts knowing no neighbours; what it ends up knowing must equal
    exactly its real neighbours."""
    net = make_net(loss=0.0)
    nodes = trivial(net)
    for n in nodes.values():
        assert n.seen == {}
    sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)
    for nid, n in nodes.items():
        # the neighbour table is keyed by MAC, not by node id
        assert sorted(n.seen) == sorted(net.mac_of(x) for x in net.neighbors(nid))


def test_unicast_to_a_non_neighbour_does_not_leak_adjacency():
    """I1: a unicast to a non-neighbour does NOT raise; if it did, the node
    would learn the graph."""
    net = make_net(loss=0.0)
    nodes = trivial(net)
    port = net.port(1)
    payload = wire.encode(wire.Ctrl(MsgType.LINK, 1, 1))
    port.send_unicast(net.mac_of(10), payload)   # 1 and 10 are not neighbours
    c = net.counters[1]
    assert c.tx == 1 and c.rx == 0         # it went on the air and reached nobody
    assert net.rx_delivered[10] == 0
    assert any(r["event"] == "unicast_unreachable" for r in net.log_records)


# --------------------------------------------------------------------------
# 6b. addressing: src and dst are MACs (team decision, brief 3.5/1)
# --------------------------------------------------------------------------
def test_on_frame_src_is_the_mac_not_the_node_id():
    """The MAC comes from the frame HEADER; it never enters the payload."""
    got = []

    class Sniffer(sched.TrivialHelloNode):
        def on_frame(self, src, rssi, payload):
            got.append((src, wire.decode(payload).src))
            super().on_frame(src, rssi, payload)

    net = make_net(loss=0.0)
    nodes = sched.build(net, WEIGHTS, Sniffer)
    sched.SyncScheduler(net, nodes, tau_ms=200).run(600)
    assert got
    for mac, payload_id in got:
        assert mac == net.mac_of(net.id_of_mac(mac))   # a real MAC
        assert mac != payload_id                       # NOT the same as the id
        assert mac.bit_length() > 32                   # 48 bitlik adres
    # no MAC in the payload: the HELLO size is unchanged
    assert wire.hello_size(0) == 13


def test_macs_are_locally_administered_unicast_and_unique():
    net = make_net()
    for nid in NODES:
        mac = net.mac_of(nid)
        assert 0 < mac <= 0xFFFFFFFFFFFF
        first = mac >> 40
        assert first & 0b10, "the locally-administered bit must be set"
        assert not first & 0b01, "must be a unicast address, not multicast"
    assert len({net.mac_of(n) for n in NODES}) == len(NODES)


def test_mac_mapping_is_deterministic_and_seed_independent():
    """MACs stay the same across seeds: same topology, same addresses."""
    a = simnet.SimNet(NODES, EDGES, seed=1).macs
    b = simnet.SimNet(NODES, EDGES, seed=999).macs
    assert a == b == {n: simnet.default_mac(n) for n in NODES}
    assert simnet.SimNet(NODES, EDGES).id_of_mac(simnet.default_mac(7)) == 7


def test_macs_can_be_overridden_for_identity_collision_tests():
    """bootstrap's identity-collision path needs TWO DIFFERENT MACs landing on
    the same hash16, which is why the mapping can be supplied from outside."""
    net = simnet.SimNet([1, 2], [(1, 2)], macs={1: 0x020000001234, 2: 0x02FFFF001234})
    assert net.mac_of(1) == 0x020000001234
    assert net.mac_of(1) & 0xFFFF == net.mac_of(2) & 0xFFFF    # same low 16 bits
    assert net.id_of_mac(0x02FFFF001234) == 2
    with pytest.raises(ValueError):
        simnet.SimNet([1, 2], [(1, 2)], macs={1: 0x020000000001, 2: 0x020000000001})


def test_unicast_to_an_unknown_mac_is_indistinguishable_from_a_non_neighbour():
    """I1: a MAC that never existed and a non-neighbour MAC must give the same
    outcome. If they differed, a node could map the graph by probing."""
    payload = wire.encode(wire.Ctrl(MsgType.LINK, 1, 1))

    def cost(dst_mac):
        net = make_net(loss=0.0)
        trivial(net)
        net.port(1).send_unicast(dst_mac, payload)
        c = net.counters[1]
        return (c.tx, c.rx, c.bytes_tx,
                [r["event"] for r in net.log_records])

    non_neighbour = cost(make_net().mac_of(10))
    never_existed = cost(0x02DEADBEEF01)
    assert non_neighbour == never_existed
    assert non_neighbour[:2] == (1, 0)


def test_unicast_to_a_neighbour_is_one_tx_one_rx():
    net = make_net(loss=0.0)
    trivial(net)
    net.port(1).send_unicast(net.mac_of(2), wire.encode(wire.Ctrl(MsgType.LINK, 1, 1)))
    assert net.counters[1].tx == 1 and net.counters[1].rx == 1
    assert net.rx_delivered[2] == 1


def test_isolated_node_broadcast_is_one_tx_zero_rx():
    net = simnet.SimNet([1, 2, 3], [(1, 2)], seed=0)
    sched.build(net, {1: 1, 2: 1, 3: 1}, sched.TrivialHelloNode)
    net.port(3).send_broadcast(wire.encode(
        wire.Hello(src=3, key=None, deg=0, role=Role.OUT, phase=0, load=0)))
    assert net.counters[3].tx == 1 and net.counters[3].rx == 0


# --------------------------------------------------------------------------
# 7. RSSI, retx, the phase breakdown, and the 250 B gate
# --------------------------------------------------------------------------
def test_synthetic_rssi_is_delivered_symmetric_and_deterministic():
    seen = {}

    class RssiNode(sched.TrivialHelloNode):
        def on_frame(self, src, rssi, payload):
            seen[(src, self.mac)] = rssi
            super().on_frame(src, rssi, payload)

    net = make_net(loss=0.0, rssi_range=(-85.0, -45.0), seed=3)
    nodes = sched.build(net, WEIGHTS, RssiNode)
    sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)
    seen = {(net.id_of_mac(a), net.id_of_mac(b)): v for (a, b), v in seen.items()}
    assert len(seen) == DEG_SUM
    for v in seen.values():
        assert v is not None and -85.0 <= v <= -45.0
    for (u, v), val in seen.items():
        assert seen[(v, u)] == val               # link simetrik
    # the same seed gives the same RSSI
    assert simnet.SimNet(NODES, EDGES, seed=3).rssi == net.rssi
    assert simnet.SimNet(NODES, EDGES, seed=4).rssi != net.rssi


def test_rssi_can_be_switched_off_and_overridden():
    net = simnet.SimNet([1, 2], [(1, 2)], rssi_range=None)
    assert net.rssi == {}
    net2 = simnet.SimNet([1, 2], [(1, 2)], rssi={(2, 1): -70.0}, rssi_range=None)
    assert net2.rssi == {(1, 2): -70.0}


def test_retx_is_derived_from_the_node_log():
    """api: counters are derived from the log; a node does not report its own."""
    net = make_net()
    port = net.port(1)
    assert net.counters[1].retx == 0
    port.log("retx", reason="ack_timeout", seq=4)
    port.log("retx", n=2, reason="ack_timeout", seq=5)
    assert net.counters[1].retx == 3
    assert len(net.log_records) == 2


def test_phase_breakdown_follows_the_node_phase():
    class PhaseNode(sched.TrivialHelloNode):
        def on_timer(self, name):
            super().on_timer(name)
            self.phase += 1

    net = make_net(loss=0.0)
    nodes = sched.build(net, WEIGHTS, PhaseNode)
    out = sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)
    # 5 slots, one broadcast per slot in phases 0..4, 10 nodes
    assert out.totals().by_phase_tx == {0: 10, 1: 10, 2: 10, 3: 10, 4: 10}


def test_oversize_payload_raises_at_the_network_boundary():
    """I3 is a gate at the network layer too: a payload over 250 B cannot be sent."""
    net = make_net()
    trivial(net)
    ok = bytes([int(MsgType.HELLO)]) + b"x" * (MAX_PAYLOAD - 1)
    net.port(1).send_broadcast(ok)                      # exactly at the limit, passes
    assert net.counters[1].max_payload == MAX_PAYLOAD
    with pytest.raises(PayloadTooLarge):
        net.port(1).send_broadcast(ok + b"x")           # one byte over is an error


# --------------------------------------------------------------------------
# 8. RunOutcome contents
# --------------------------------------------------------------------------
def test_outcome_reports_cover_owner_and_weight():
    class Decider(sched.QuietAfterNode):
        """Rule: even-id nodes are in the cover, and the lower end owns the edge."""

        def __init__(self, nid, w, p):
            super().__init__(nid, w, p, n_hello=2)
            self.role = Role.COVER if nid % 2 == 0 else Role.OUT

        def snapshot(self):
            s = super().snapshot()
            s.role = self.role
            s.owned = tuple(e for e in EDGES if e[0] == self.nid)
            return s

    net = make_net(loss=0.0)
    nodes = sched.build(net, WEIGHTS, Decider)
    out = sched.SyncScheduler(net, nodes, tau_ms=200, weights=WEIGHTS).run(10_000)
    assert out.cover == [2, 4, 6, 8, 10]
    assert out.total_weight == pytest.approx(2 + 3 + 2 + 2 + 4)
    assert len(out.owner) == len(EDGES)
    assert out.owner[(1, 2)] == 1 and out.owner[(8, 10)] == 8
    assert out.scheduler == "sync"


def test_energy_estimate_uses_radio_on_and_tx():
    net = make_net(loss=0.0)
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000)
    c = out.totals()
    expected = c.radio_on_ms / 3_600_000.0 * 100.0 + c.tx * 0.7 / 3_600_000.0 * 240.0
    assert c.energy_mah() == pytest.approx(round(expected, 6))
    assert c.radio_on_ms == 10 * 4000       # none of them went quiet


# --------------------------------------------------------------------------
# 9. channel faults: directed, timed and type-aware dropping (brief 3.4)
# --------------------------------------------------------------------------
def test_drop_predicate_is_directed():
    """1->2 broken while 2->1 works. Only this makes the bidirectional handshake
    meaningful, since without it a one-way link would silently become an edge."""
    net = make_net(loss=0.0, drop=lambda t, src, dst, mt: (src, dst) == (1, 2))
    nodes = trivial(net)
    sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)
    assert net.mac_of(1) not in nodes[2].seen      # 2, 1'i duymuyor
    assert net.mac_of(2) in nodes[1].seen          # 1, 2'yi duyuyor
    # undirected link_loss CANNOT express this: it cuts both directions
    undirected = make_net(loss=0.0, link_loss={(1, 2): 1.0})
    un = trivial(undirected)
    sched.SyncScheduler(undirected, un, tau_ms=200).run(1000)
    assert undirected.mac_of(1) not in un[2].seen
    assert undirected.mac_of(2) not in un[1].seen


def test_drop_predicate_sees_time_for_a_bounded_outage():
    """Node 4 is deaf for three HELLO periods, then restored."""
    T_HELLO = 200
    outage = 3 * T_HELLO
    net = make_net(loss=0.0,
                   drop=lambda t, src, dst, mt: dst == 4 and t < outage)
    nodes = trivial(net)
    sched.SyncScheduler(net, nodes, tau_ms=T_HELLO).run(2000)
    # during the outage it must hear no neighbour, and all of them afterwards
    assert sorted(nodes[4].seen) == sorted(net.mac_of(x) for x in net.neighbors(4))
    heard_times = sorted(nodes[4].seen.values())
    assert min(heard_times) >= outage, "a frame leaked through the outage window"
    # its neighbours never stopped hearing 4: the drop is DIRECTED
    assert net.mac_of(4) in nodes[2].seen


def test_drop_predicate_sees_message_type():
    """HELLO is dropped, LINK is delivered. The distinction is essential so the
    victim cannot learn a neighbour through a handshake it should never receive."""
    seen_types = {2: []}

    class Chatty(sched.TrivialHelloNode):
        """Broadcasts one HELLO per tick and unicasts one LINK to node 2."""

        def on_timer(self, name):
            super().on_timer(name)
            if self.nid == 1:
                self.plat.send_unicast(
                    self.plat_mac2, wire.encode(wire.Ctrl(MsgType.LINK, 1, 1)))

        def on_frame(self, src, rssi, payload):
            seen_types.setdefault(self.nid, []).append(wire.peek_type(payload))
            super().on_frame(src, rssi, payload)

    net = make_net(loss=0.0,
                   drop=lambda t, src, dst, mt: mt == int(MsgType.HELLO) and dst == 2)
    nodes = sched.build(net, WEIGHTS, Chatty)
    for n in nodes.values():
        n.plat_mac2 = net.mac_of(2)
    sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)

    got = seen_types[2]
    assert got, "node 2 received nothing at all"
    assert MsgType.HELLO not in got          # the HELLOs were dropped
    assert MsgType.LINK in got               # LINK geldi
    assert net.dropped_by_rule > 0


def test_accounting_invariant_holds_under_the_drop_predicate():
    """A frame dropped by the predicate is written to tx, not to rx."""
    net = make_net(loss=0.0, drop=lambda t, src, dst, mt: dst in (4, 7))
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000)
    tot = out.totals()
    assert tot.tx == 200                      # the transmission count is unaffected by the fault
    assert tot.bytes_tx == 200 * 13
    assert tot.rx + net.dropped == 20 * DEG_SUM
    assert net.dropped == net.dropped_by_rule == 20 * (net.degree(4) + net.degree(7))


def test_predicate_and_loss_compose_without_breaking_the_invariant():
    net = make_net(loss=0.15, drop=lambda t, src, dst, mt: (src, dst) == (1, 2))
    out = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000)
    tot = out.totals()
    assert tot.tx == 200
    assert tot.rx + net.dropped == 20 * DEG_SUM
    assert 0 < net.dropped_by_rule <= net.dropped


def test_predicate_does_not_perturb_the_loss_stream():
    """The predicate generates no randomness of its own AND does not shift the
    loss die.

    Because the die is rolled for every frame regardless, adding a predicate
    leaves the loss pattern on UNAFFECTED links exactly as it was. Without that,
    adding one fault scenario would invalidate every previously recorded result.
    """
    def drops_at(drop):
        net = make_net(loss=0.15, seed=21, drop=drop)
        nodes = trivial(net)
        sched.SyncScheduler(net, nodes, tau_ms=200).run(4000)
        # frames heard by every node other than the 1->2 direction
        return {nid: n.frames_rx for nid, n in nodes.items() if nid not in (2,)}

    plain = drops_at(None)
    with_rule = drops_at(lambda t, src, dst, mt: (src, dst) == (1, 2))
    assert plain == with_rule


def test_callable_rssi_can_oscillate_a_link_over_time():
    """Oscillation between the hysteresis thresholds (-75 opens, -85 closes).
    A hysteresis that is never made to flap has not been tested."""
    trace = []

    class RssiTap(sched.TrivialHelloNode):
        def on_frame(self, src, rssi, payload):
            trace.append((self.plat.now_ms(), src, self.mac, rssi))
            super().on_frame(src, rssi, payload)

    def rssi_fn(t_ms, src, dst):
        if (src, dst) in ((1, 2), (2, 1)):
            return -76.0 if (t_ms // 400) % 2 == 0 else -84.0
        return -60.0

    net = make_net(loss=0.0, rssi=rssi_fn)
    assert net.rssi == {} and net.rssi_fn is rssi_fn
    nodes = sched.build(net, WEIGHTS, RssiTap)
    sched.SyncScheduler(net, nodes, tau_ms=200).run(2000)

    def vals(a, b):
        return {v for _, s_, d_, v in trace
                if (s_, d_) == (net.mac_of(a), net.mac_of(b))}

    assert vals(1, 2) == {-76.0, -84.0}, "the link did not oscillate"
    assert vals(2, 1) == {-76.0, -84.0}, "the reverse direction must oscillate too"
    assert vals(1, 3) == {-60.0}, "other links must be unaffected"


def test_static_rssi_forms_still_work_unchanged():
    net = simnet.SimNet([1, 2], [(1, 2)], rssi={(2, 1): -70.0}, rssi_range=None)
    assert net.rssi == {(1, 2): -70.0} and net.rssi_fn is None
    assert simnet.SimNet(NODES, EDGES, seed=3).rssi == make_net(seed=3).rssi


# --------------------------------------------------------------------------
# 10. does the surface test itself work (mutation check)
# --------------------------------------------------------------------------
def _public_surface(obj) -> set:
    return {m for m in dir(obj) if not m.startswith("_")}


def test_port_surface_assertion_actually_catches_a_violation():
    """A test that looks in the wrong place is worse than no test.

    Is the surface assertion LIVE: it must reject a port with an added member,
    and reject one with a member removed.
    """
    expected = {"log", "mac", "now_ms", "send_broadcast", "send_unicast"}
    net = make_net()
    assert _public_surface(net.port(1)) == expected     # the real port passes

    class LeakyPort(type(net.port(1))):
        def neighbors(self):                            # a leaking extra member
            return ()

    leaky = LeakyPort(net, 1)
    assert _public_surface(leaky) != expected
    assert "neighbors" in _public_surface(leaky)

    # a removal must be caught too
    class StarvedPort:
        log = now_ms = send_broadcast = send_unicast = None

    assert _public_surface(StarvedPort()) != expected


def test_private_attribute_reach_through_is_a_known_hole():
    """AN HONESTY NOTE, NOT a hole that has been closed.

    The surface test filters out names starting with `_`, yet `plat._net` hands
    over the entire graph. Python cannot close that at the language level; the
    thing guarding this door is the AST checker that scans node code (on the
    bootstrap side). What is recorded here is only the EXISTENCE of the hole, so
    that nobody trusts the surface test further than it goes.
    """
    port = make_net().port(1)
    assert hasattr(port, "_net")
    assert "_net" not in _public_surface(port)
    assert port._net.neighbors(1) == (2, 3)


# --------------------------------------------------------------------------
# 11. Receiver-side breakdown: the attribution is IN THE NAME (figure 5)
# --------------------------------------------------------------------------
def test_receiver_side_rx_is_counted_at_processing_not_at_enqueue():
    """A frame queued in one phase and processed in ANOTHER must be attributed
    to the phase it was PROCESSED in. `rx_delivered` cannot do that: it
    increments at `_enqueue`."""
    class PhaseBumper(sched.TrivialHelloNode):
        """Advances its phase every tick; synchronously a frame is processed in
        the next slot, so the sending phase and the processing phase are
        NECESSARILY different."""

        def on_timer(self, name):
            super().on_timer(name)
            self.phase += 1

    net = make_net(loss=0.0)
    nodes = sched.build(net, WEIGHTS, PhaseBumper)
    out = sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)   # 5 slots

    tot = net.receiver_totals()
    # sender side: broadcast in slot t while in phase t
    assert out.totals().by_phase_tx == {0: 10, 1: 10, 2: 10, 3: 10, 4: 10}
    # receiver side: what was sent in slot t is processed in slot t+1, i.e. phase t+1
    assert tot["rx_by_receiver_phase"] == {1: 30, 2: 30, 3: 30, 4: 30}
    # the two attributions are NOT THE SAME, which is exactly why they are separate
    assert tot["rx_by_receiver_phase"] != dict(out.totals().by_phase_tx)


def test_receiver_totals_carry_bytes_and_a_phase_type_cross_tab():
    net = make_net(loss=0.0)
    nodes = trivial(net)
    sched.SyncScheduler(net, nodes, tau_ms=200).run(1000)
    tot = net.receiver_totals()
    hello = int(MsgType.HELLO)
    assert tot["rx_at_receiver"] == sum(tot["rx_by_receiver_phase"].values())
    # HELLO is 13 B: the byte breakdown must be 13 times the frame breakdown
    for ph, n in tot["rx_by_receiver_phase"].items():
        assert tot["bytes_rx_by_receiver_phase"][ph] == 13 * n
    assert set(tot["rx_by_receiver_phase_type"]) == {(0, hello)}


def test_processed_rx_is_not_the_same_as_caused_rx_when_frames_are_in_flight():
    """`Counters.rx` is decided at send time; a frame still in flight when the
    run ends has been COUNTED but never PROCESSED. The difference is real and
    must not be hidden."""
    net = make_net(loss=0.0)
    nodes = trivial(net)
    out = sched.SyncScheduler(net, nodes, tau_ms=200).run(4000)
    caused = out.totals().rx
    processed = net.receiver_totals()["rx_at_receiver"]
    assert caused == 600
    # the last slot's broadcasts were never delivered: short by the degree sum
    assert processed == caused - DEG_SUM
    assert processed < caused


def test_loss_reduces_processed_rx_exactly_like_caused_rx():
    net = make_net(loss=0.15)
    nodes = trivial(net)
    out = sched.SyncScheduler(net, nodes, tau_ms=200).run(4000)
    processed = net.receiver_totals()["rx_at_receiver"]
    assert processed <= out.totals().rx
    assert out.totals().tx == 200          # tx yine etkilenmez


def test_rx_delivered_keeps_its_old_meaning_for_mnwifi():
    """`rx_delivered` is used by `mnwifi/collect.py` and its meaning is
    UNCHANGED: the number of frames that survived loss and were DESTINED for
    this node."""
    net = make_net(loss=0.0)
    nodes = trivial(net)
    out = sched.SyncScheduler(net, nodes, tau_ms=200).run(4000)
    assert sum(net.rx_delivered.values()) == out.totals().rx == 600
