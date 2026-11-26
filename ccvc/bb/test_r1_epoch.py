"""Regression tests for the epoch disagreement at silence (contract R1_PREREG.md,
Amendments 9 and 10, F16 and F16b).

Backend: the event simulator (SimNet, `rssi_range=None`, fixed delay of one
slot, synchronous scheduler). The fault is a deterministic `SimNet.drop`
predicate on one link; the rest of the channel is lossless. The three graphs
are the constructed development instances of the independent proof check; no
held-out instance and no pre-registered seed is used.

In each run a leaf u closes its barrier and its only neighbour v wakes later.
Every HELLO v -> u sent in the `burst` slots from `start` is lost. Without
F16b a burst of 59 to 98 slots left u in epoch 0, set by how long v happened
to transmit after it restarted. With F16b v keeps announcing its epoch to the
expired u for the hand-off wait, twice the stale cap, after its restart, so
every burst shorter than that wait ends in one epoch. A longer burst still
reads as u's departure, which now costs v one bounded wait. The thresholds
were measured on the code before F15 and again with F15 merged, unchanged at
every one of the 105 burst starts.
"""

from __future__ import annotations

import functools
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, sched, simnet, sweep, validate  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402

TAU = 200
HELLO = int(MsgType.HELLO)
LONG_BURST = 150  # the burst of the proof check, longer than every threshold

#: name -> (edges, weights, k, leaf u, its neighbour v, slot u closes, slot of u's last frame)
CASES = {
    "n9_m15": (
        [(1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (2, 3), (2, 4)]
        + [(2, 7), (2, 8), (3, 4), (3, 8), (4, 7), (5, 7), (8, 9)],
        {1: 7, 2: 3, 3: 6, 4: 4, 5: 8, 6: 1, 7: 6, 8: 3, 9: 4},
        2,
        9,
        8,
        32,
        55,
    ),
    "n13_m19": (
        [(1, 5), (1, 8), (1, 10), (2, 8), (2, 12), (3, 4), (3, 5), (3, 7)]
        + [(3, 11), (3, 12), (4, 5), (4, 10), (5, 8), (6, 11), (6, 12), (6, 13)]
        + [(8, 10), (8, 12), (9, 10)],
        {1: 7, 2: 2, 3: 2, 4: 6, 5: 5, 6: 5, 7: 6, 8: 2, 9: 5, 10: 6, 11: 8}
        | {12: 6, 13: 4},
        2,
        9,
        10,
        22,
        22,
    ),
    "n13_m22": (
        [(1, 4), (1, 6), (1, 7), (1, 10), (1, 11), (1, 12), (2, 5), (2, 13)]
        + [(3, 6), (4, 6), (4, 12), (4, 13), (5, 7), (6, 9), (7, 8), (7, 10)]
        + [(7, 11), (8, 9), (9, 10), (10, 12), (10, 13), (12, 13)],
        {1: 1, 2: 8, 3: 4, 4: 9, 5: 4, 6: 5, 7: 6, 8: 4, 9: 7, 10: 4, 11: 6}
        | {12: 7, 13: 4},
        2,
        3,
        6,
        22,
        22,
    ),
}

#: The hand-off wait of F16b in slots: twice the stale cap of 48 periods.
HANDOFF = 96

#: (name, burst start) -> shortest burst that leaves u in epoch 0, with F16b.
#: The first start is u's close, the second the start that needs the shortest
#: burst (scan of every start from u's close to 13 slots after v's wake and
#: every length up to 160). Without F16b: 92, 73, 79, 59, 98, 78.
#: Amendment 13 (G1-G6) moved them, measured over every length 1..220 at both
#: starts: 121, 102, 127, 102, none (one epoch for every length), 104. Every
#: split set is contiguous from its threshold, and every run ends silent.
THRESHOLD = {
    ("n9_m15", 32): 121,
    ("n9_m15", 51): 102,
    ("n13_m19", 22): 127,
    ("n13_m19", 47): 102,
    ("n13_m22", 22): None,
    ("n13_m22", 46): 104,
}
WORST = {case: max(s for c, s in THRESHOLD if c == case) for case in CASES}
SCAN_MAX = 220  # Amendment 13: the longest burst of the scan


@functools.lru_cache(maxsize=None)
def run(case, burst, start=None, switched_off=False):
    """The run with every HELLO v -> u lost in the `burst` slots from `start`
    (default: u's close), or its twin in which u is also switched off (it
    stops ticking and every frame to or from it is lost) after its last frame.
    Returns the nodes, every survivor's (tx, rx) per slot, the slots of the
    lost HELLOs, and the restart and hand-off events as (slot, node, event)."""
    e, w, k, u, v, t_close, t_last = CASES[case]
    t0 = t_close if start is None else start
    ids = sorted(w)
    lost = []

    def drop(t, s, d, m):
        if switched_off and u in (s, d) and t >= t_last * TAU:
            return True
        hit = (s, d) == (v, u) and m == HELLO and t0 <= t // TAU < t0 + burst
        if hit:
            lost.append(t // TAU)
        return hit

    net = simnet.SimNet(
        ids,
        e,
        loss=0.0,
        seed=0,
        delay=simnet.fixed_delay(1),
        rssi_range=None,
        macs=bbcvc.macs_for(ids),
        drop=drop,
    )
    nodes = bbcvc.build_nodes(net, w, k, bbcvc.BbcvcParams(n_bound=len(ids)))
    sc = sched.SyncScheduler(net, nodes, tau_ms=TAU, weights=w)
    trace = []
    for s in range(t0 + burst + 250):
        net.set_now(s * TAU)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            if not switched_off or nid != u or s < t_last:
                net.set_now(s * TAU)
                nodes[nid].on_timer("tick")
        trace.append(
            tuple((i, c.tx, c.rx) for i, c in sorted(net.counters.items()) if i != u)
        )
    events = tuple(
        (x["t_ms"] // TAU, x["nid"], x["event"])
        for x in net.log_records
        if x["event"] in ("epoch_bump", "handoff", "handoff_heard", "handoff_timeout")
    )
    return nodes, tuple(trace), tuple(lost), events


def epochs(nodes):
    return {n.epoch for n in nodes.values()}


def test_F16b_the_handoff_wait_is_twice_the_stale_cap():
    p = bbcvc.BbcvcParams()
    wait_ms = bbcvc.BbcvcNode._handoff_wait_ms(SimpleNamespace(p=p))
    assert wait_ms == 2 * p.stale_periods_cap * p.t_hello_ms == HANDOFF * TAU


@pytest.mark.parametrize("case", sorted(CASES))
def test_F16b_every_burst_shorter_than_the_handoff_wait_ends_in_one_epoch(case):
    """At the burst start that needs the shortest burst, every burst from 1
    slot up to one below the threshold ends silent in one epoch, and the
    threshold exceeds the hand-off wait. At u's close the threshold is larger.
    Both thresholds split the epochs."""
    worst = WORST[case]
    th = THRESHOLD[(case, worst)]
    assert th > HANDOFF
    for burst in range(1, th):
        nodes, trace, _, _ = run(case, burst, worst)
        assert len(epochs(nodes)) == 1, burst
        assert trace[-1] == trace[-101], burst
    assert epochs(run(case, th, worst)[0]) == {0, 1}
    t_close = CASES[case][5]
    th_close = THRESHOLD[(case, t_close)]
    if th_close is None:  # Amendment 13: no burst up to SCAN_MAX splits here
        assert len(epochs(run(case, SCAN_MAX, t_close)[0])) == 1
        return
    assert th_close > th
    assert len(epochs(run(case, th_close - 1)[0])) == 1
    assert epochs(run(case, th_close)[0]) == {0, 1}


@pytest.mark.parametrize("case", sorted(CASES))
def test_F16b_a_departure_costs_one_bounded_wait(case):
    """u is switched off after its last frame. v expires it while it was
    finished, restarts, announces its epoch for exactly the hand-off wait
    after the restart, gives up, and the survivors fall silent before the
    wait ends."""
    v = CASES[case][4]
    _, trace, _, events = run(case, LONG_BURST, switched_off=True)
    assert trace[-1] == trace[-101], "silent for the last 100 slots"
    mine = [(s, ev) for s, n, ev in events if n == v]
    kinds = [ev for _, ev in mine]
    assert kinds == ["handoff", "epoch_bump", "handoff_timeout"], mine
    bump, timeout = mine[1][0], mine[2][0]
    assert timeout - bump == HANDOFF
    tx = [sum(c[1] for c in slot) for slot in trace]
    last = max(i for i in range(1, len(tx)) if tx[i] != tx[i - 1])
    # Amendment 13, G4: the hand-off is owed until it ends, so v's last slow
    # beacon can fall in the slot the wait ends (n13_m22), never after it.
    assert last <= timeout


@pytest.mark.parametrize("case", sorted(CASES))
def test_F16_a_longer_burst_reads_as_a_departure(case):
    """Beyond the threshold the protocol treats u as departed. Every survivor's
    tx and rx agree slot by slot with the twin in which u is really gone, the
    run ends silent with no edge owned twice, u is DONE and closed in epoch 0
    with v in its view while v's view lacks u, u keeps its old role and its
    claim on (u, v), and the reading on the discovered graph is valid with
    (u, v) as the one planned link missing."""
    e, w, k, u, v, _, _ = CASES[case]
    nodes, trace, _, _ = run(case, LONG_BURST)
    assert trace[-1] == trace[-101], "silent for the last 100 slots"
    # Amendment 13: u, alive, now answers the confirmation asks (G2c), so the
    # survivors' trace is no longer bit-identical to the departure twin
    # (n13_m19, n13_m22), and on n13_m22 the burst no longer splits the epochs.
    if len(epochs(nodes)) == 1:
        assert case == "n13_m22"
        return
    leaf, nbr = nodes[u], nodes[v]
    assert (leaf.epoch, leaf.phase, leaf._barrier_closed()) == (0, bbcvc.PH_DONE, True)
    assert {n.epoch for i, n in nodes.items() if i != u} == {1}
    assert v in leaf._frozen_bidir and u not in nbr._frozen_bidir
    uv = bbcvc.edge(u, v)
    assert leaf.role.in_cover and leaf.owned == {uv} and uv not in nbr.owned
    claims = [x for n in nodes.values() for x in n.owned]
    assert len(claims) == len(set(claims))
    frozen = {i: set(n._frozen_bidir) for i, n in nodes.items()}
    res = SimpleNamespace(
        cover=sorted(i for i, n in nodes.items() if n.role.in_cover),
        owner={x: i for i, n in nodes.items() for x in n.owned},
        double_claimed={},
        discovered_edges=sorted(
            {bbcvc.edge(a, b) for a in frozen for b in frozen[a] if a in frozen[b]}
        ),
    )
    assert not [x for x in res.discovered_edges if u in x]
    reading = sweep.discovered_reading(e, w, k, res)
    assert reading == dict(valid_discovered=True, planned_missing=1, discovered_extra=0)
    assert validate.validate(validate.make_graph(e, k, w), res.cover, res.owner).valid
