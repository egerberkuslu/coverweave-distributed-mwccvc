"""Regression tests for repair F18 (FabricTree, GHS-MST-Backbone, under loss).

Backend: the event simulator (SimNet). Faults are injected with the
deterministic `SimNet.drop` predicate on small constructed graphs; the rest of
the channel is lossless. Each test fails on the code before F18.

- a REPORT of a round the receiver has not entered (its INITIATE was lost)
  raised AttributeError 'ghs_best_key' on a node never initiated;
- an INITIATE forwarded to a child is sent once, so one lost copy left the
  child a level behind for ever and the run truncated;
- a CHANGE_ROOT is sent once, so one lost copy left the fragment without its
  merge;
- GHS frames carry no epoch byte, so a frame of an older epoch set a freshly
  restarted node's parent across a BASIC edge, and an older HELLO record
  ended phase 1 without a tree.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import v4_mst, validate, wire  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402
from ccvc.bb.bbcvc import PH_MIS, BbcvcParams  # noqa: E402
from ccvc.bb.test_v4_mst import N15_M30_S2_E, N15_M30_S2_W  # noqa: E402
from ccvc.bb.v4_mst import SLEEPING, run_v4  # noqa: E402

CONNECT, INITIATE = int(MsgType.GHS_CONNECT), int(MsgType.GHS_INITIATE)
CHANGE_ROOT = int(MsgType.GHS_CHANGE_ROOT)
BRIDGE = [(1, 2), (2, 3), (1, 3), (3, 4), (4, 5), (5, 6), (4, 6)]
BRIDGE_W = {1: 1, 2: 2, 3: 1, 4: 1, 5: 2, 6: 2}


def _params():
    p = BbcvcParams()
    p.mis_nbrs_max = 64
    return p


def first_n(n, pred):
    """Drop only the first `n` frames that match `pred`."""
    left = [n]

    def drop(t, src, dst, mtype):
        if left[0] > 0 and pred(t, src, dst, mtype):
            left[0] -= 1
            return True
        return False

    return drop


def _solved_valid(edges, w, scheduler, drop, max_ms=200_000):
    res = run_v4(
        edges,
        w,
        6,
        scheduler=scheduler,
        params=_params(),
        max_ms=max_ms,
        seed=1,
        drop=drop,
    )
    g = validate.make_graph(edges, 6, w, sorted(w))
    return (
        res,
        res.verdict == "solved" and validate.validate(g, res.cover, res.owner).valid,
    )


@pytest.mark.parametrize("scheduler", ("sync", "async"))
def test_a_report_of_a_round_not_entered_waits_for_its_initiate(scheduler):
    """Node 1's CONNECT and INITIATE to node 2 are lost for 2 s; node 1 merged on
    node 2's CONNECT and reports to it at level 1 while node 2 was never
    initiated. Before F18: AttributeError 'ghs_best_key'."""
    edges, w = [(1, 2)], {1: 1, 2: 2}
    _, ok = _solved_valid(
        edges,
        w,
        scheduler,
        drop=lambda t, s, d, m: s == 1
        and d == 2
        and m in (CONNECT, INITIATE)
        and t < 2000,
        max_ms=100_000,
    )
    assert ok


def test_a_lost_initiate_to_an_unchanged_child_is_repeated():
    """Both level-2 INITIATE copies from 11 to its child 3 are lost (n15_m30_s2,
    sync). Before F18 node 3 stayed at level 1, deferred every level-2 TEST and
    the run truncated; its repeated level-1 REPORT now brings the INITIATE back."""
    res, ok = _solved_valid(
        N15_M30_S2_E,
        N15_M30_S2_W,
        "sync",
        drop=lambda t, s, d, m: m == INITIATE
        and s == 11
        and d == 3
        and 3000 <= t < 5000,
    )
    assert ok and res.slots <= 60


def test_a_lost_initiate_on_the_turned_path_is_repeated():
    """The first two INITIATE copies from 13 to 12 are lost; 12 sits on the
    change-root path, so its parent pointer still names its old parent and its
    REPORT never reaches 13. Its repeated CHANGE_ROOT, carrying level 1, does."""
    res, ok = _solved_valid(
        N15_M30_S2_E,
        N15_M30_S2_W,
        "sync",
        drop=first_n(2, lambda t, s, d, m: m == INITIATE and s == 13 and d == 12),
    )
    assert ok and res.slots <= 60


def test_a_lost_change_root_is_repeated():
    """One CHANGE_ROOT from 12 to 13 is lost (n15_m30_s2, sync): before F18 the
    fragment never claimed its minimum outgoing edge and the run truncated."""
    res, ok = _solved_valid(
        N15_M30_S2_E,
        N15_M30_S2_W,
        "sync",
        drop=first_n(1, lambda t, s, d, m: m == CHANGE_ROOT and s == 12 and d == 13),
    )
    assert ok and res.slots <= 60


def test_frames_and_records_of_an_older_epoch_are_ignored():
    res = run_v4(
        BRIDGE, BRIDGE_W, 6, scheduler="sync", params=_params(), max_ms=200_000, seed=1
    )
    node = res.nodes[3]
    peer = next(n for n in node.nbrs.values() if n.is_edge)
    node._reset_to_phase0(0, reason="test")
    peer.bidir, peer.awaiting_ack = True, False  # Amendment 13, G2(a): re-verified
    node.epoch = (node.epoch + 1) & 0xFF
    node.phase = PH_MIS
    peer.epoch, peer.phase = (node.epoch - 1) & 0xFF, 7  # its last HELLO: old epoch
    init = wire.decode(
        wire.encode(wire.Ghs(MsgType.GHS_INITIATE, peer.nid, 1, 1, 99, 1))
    )

    assert not node._v4_phase1_over([peer]), "an older record ended phase 1"
    node._on_algo(0, peer.mac, init)
    assert node.ghs_state == SLEEPING and node.ghs_parent is None

    peer.epoch = node.epoch  # control: same epoch
    assert node._v4_phase1_over([peer])
    node._on_algo(0, peer.mac, init)
    assert node.ghs_parent == peer.nid


def test_lossless_runs_never_repeat_an_initiate(monkeypatch):
    """The age gate keeps a REPORT that only crossed my INITIATE from repeating it."""
    sent = []
    orig = v4_mst.V4MstDistNode._ghs_reinitiate
    send = v4_mst.V4MstDistNode._ghs_send

    def spy(self, now, n):
        self._ghs_send = lambda *a: (sent.append(a[1]), send(self, *a))
        try:
            orig(self, now, n)
        finally:
            del self._ghs_send

    monkeypatch.setattr(v4_mst.V4MstDistNode, "_ghs_reinitiate", spy)
    for sch in ("sync", "async"):
        _, ok = _solved_valid(BRIDGE, BRIDGE_W, sch, drop=None)
        assert ok
    assert sent == [], "a lossless run asked a child to re-enter its round"
