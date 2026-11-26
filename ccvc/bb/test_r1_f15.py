"""Regression tests for the stale forced load at a closed node (contract R1_PREREG.md, Amendment 9, F15).

Backend: the event simulator (SimNet, `rssi_range=None`, fixed delay of one
slot, synchronous scheduler). The fault is a deterministic `SimNet.drop`
predicate on one link; the rest of the channel is lossless. The two graphs are
the constructed development instances of the independent proof check, written
out literally; no held-out instance and no pre-registered seed is used.

In each run node u has closed its barrier when its neighbour v changes its
forced load, and every HELLO v -> u of the next 150 slots is lost. Before F15
the network fell silent with the edge (u, v) owned by both ends and the
verdict solved.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, sched, simnet, sweep, validate, wire  # noqa: E402
from ccvc.bb.api import MsgType, Role  # noqa: E402

TAU = 200
HELLO = int(MsgType.HELLO)
BURST = 150  # slots in which every HELLO v -> u is lost
HORIZON = 400

#: name -> (edges, weights, k, u, v, burst start, slot of u's last frame before F15)
CASES = {
    "n13_m26": (
        [(1, 3), (1, 5), (1, 7), (1, 8), (2, 4), (2, 7), (2, 8), (2, 11), (3, 5)]
        + [(3, 9), (4, 6), (4, 7), (4, 12), (4, 13), (5, 8), (5, 11), (6, 8)]
        + [(6, 11), (6, 13), (7, 8), (7, 9), (7, 10), (7, 11), (7, 13), (8, 11)]
        + [(10, 12)],
        {1: 9, 2: 1, 3: 8, 4: 6, 5: 4, 6: 2, 7: 6, 8: 3, 9: 8, 10: 7, 11: 5}
        | {12: 5, 13: 5},
        3,
        3,
        5,
        24,
        52,
    ),
    "n10_m23": (
        [(1, 6), (1, 7), (1, 9), (1, 10), (2, 8), (2, 9), (3, 4), (3, 5), (3, 6)]
        + [(3, 7), (3, 9), (3, 10), (4, 7), (4, 8), (4, 9), (4, 10), (5, 6)]
        + [(5, 7), (5, 9), (5, 10), (6, 7), (6, 10), (7, 10)],
        {1: 7, 2: 6, 3: 5, 4: 5, 5: 4, 6: 2, 7: 3, 8: 4, 9: 9, 10: 7},
        3,
        8,
        4,
        25,
        78,
    ),
}


def burst(case):
    e, w, k, u, v, t, _ = CASES[case]

    def drop(tt, s, d, m):
        return (s, d) == (v, u) and m == HELLO and t * TAU <= tt < (t + BURST) * TAU

    return drop


@pytest.mark.parametrize("case", sorted(CASES))
def test_F15_constructed_run_ends_with_no_double_owner(case):
    """The proof check's counterexample: before F15 the run ended solved with
    (u, v) owned by both ends. v's change now waits for u's echo, the silent u
    is expired, the epoch restarts, and the run ends silent and valid on the
    graph it discovered. With F16b the ends that expired each other keep
    announcing until the burst is over, so that graph keeps (u, v)."""
    e, w, k, u, v, _, _ = CASES[case]
    r = bbcvc.run_bbcvc(e, w, k, scheduler="sync", max_ms=10**7, drop=burst(case))
    assert r.verdict == "solved"
    assert r.double_claimed == {}
    assert sweep.discovered_reading(e, w, k, r)["valid_discovered"]
    assert r.tx_after_convergence == 0
    assert r.restarts >= 1


def run_twin(case):
    """The run with u switched off right after its last frame before F15: it
    stops ticking and every frame to or from it is lost from the next slot."""
    e, w, k, u, v, t, last = CASES[case]
    ids = sorted(w)
    lossy = burst(case)

    def drop(tt, s, d, m):
        return u in (s, d) and tt > last * TAU or lossy(tt, s, d, m)

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
    tx = []
    for s in range(HORIZON):
        net.set_now(s * TAU)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            if nid != u or s <= last:
                net.set_now(s * TAU)
                nodes[nid].on_timer("tick")
        tx.append(sum(c.tx for i, c in net.counters.items() if i != u))
    return {i: n for i, n in nodes.items() if i != u}, tx


@pytest.mark.parametrize("case", sorted(CASES))
def test_F15_departure_twin_still_falls_silent(case):
    """A confirmation owed to a neighbour that has really gone ends when the
    neighbour expires (F13). Before F15 the survivors fell silent at once on
    the DONE they had heard and kept u's edges; now v waits for u's echo,
    expires u and restarts, and the survivors fall silent, valid without u."""
    e, w, k, u, _, _, _ = CASES[case]
    alive, tx = run_twin(case)
    assert tx[-1] == tx[-101], "silent for the last 100 slots"
    assert all(n.done and n._barrier_closed() for n in alive.values())
    assert len({n.epoch for n in alive.values()}) == 1
    owned = [x for n in alive.values() for x in n.owned]
    assert len(owned) == len(set(owned))
    left = [x for x in e if u not in x]
    cover = [i for i, n in alive.items() if n.role.in_cover]
    owner = {x: i for i, n in alive.items() for x in n.owned}
    g = validate.make_graph(left, k, w, nodes=sorted(alive))
    assert validate.validate(g, cover, owner, connectivity=validate.PER_COMPONENT).valid


def test_F15_hello_carries_the_request_and_at_most_two_echoes():
    """The request is a flag bit and the echo a block after mis_nbrs, so a
    HELLO without either keeps its size and the largest grows by a constant."""
    plain = wire.Hello(src=4, key=100, deg=3, role=Role.MIS, phase=7, load=1)
    asked = wire.Hello(
        src=4,
        key=100,
        deg=3,
        role=Role.MIS,
        phase=7,
        load=1,
        mis_nbrs=(2, 9),
        confirm=True,
        echo=((2, 1, 0), (9, 3, 2)),
        anneal=wire.Anneal(x=True, ell_fp=300, label=4, label_ctr=1, token=0, cool=5),
    )
    assert len(wire.encode(plain)) == wire.hello_size(0) == 13
    for h in (plain, asked):
        assert wire.decode(wire.encode(h)) == h
    assert len(wire.encode(asked)) == wire.hello_size(2, anneal=True, echo=2)
    assert wire.hello_size(wire.MIS_NBRS_SOFT_MAX, echo=wire.ECHO_MAX) == 32
