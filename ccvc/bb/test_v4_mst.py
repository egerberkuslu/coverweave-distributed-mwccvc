"""GHS-MST-Backbone: distributed GHS correctness, symmetry and termination tests.

Every test here pins a defect that was actually measured rather than a property
that merely sounded desirable, so a failure names the bug that came back. The
five defects, in the order they were found, are recorded in BULGULAR_BB.md 80.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from ccvc.bb import validate, wire  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402
from ccvc.bb.bbcvc import BbcvcParams  # noqa: E402
from ccvc.bb.v4_mst import INF_W, run_v4  # noqa: E402
from ccvc.bb.variants import (  # noqa: E402
    double_owned_edges, mst_internal_nodes, unowned_edges,
)
from ccvc.bridge import CcvcGraph  # noqa: E402

PATH5 = [(1, 2), (2, 3), (3, 4), (4, 5)]
CYCLE5 = [(1, 2), (2, 3), (3, 4), (4, 5), (1, 5)]
STAR5 = [(1, 2), (1, 3), (1, 4), (1, 5)]
#: Two triangles joined at 3-4. Nodes 4 and 5 tested each other forever here.
BRIDGE = [(1, 2), (2, 3), (1, 3), (3, 4), (4, 5), (5, 6), (4, 6)]
#: Two triangles joined by one edge: fragments must merge across it.
#: Edges are kept (min, max) like everywhere else in the project. The owner map
#: is keyed on the normalised pair, so an un-normalised fixture reports every
#: reversed edge as both unowned and foreign -- a fixture defect that reads
#: exactly like an ownership bug.
TWO_FRAG = [(1, 2), (2, 3), (1, 3), (4, 5), (5, 6), (4, 6), (3, 4)]

GRAPHS = {"path5": PATH5, "cycle5": CYCLE5, "star5": STAR5,
          "bridge": BRIDGE, "two_frag": TWO_FRAG}
WEIGHTS = {
    "path5": {1: 3, 2: 1, 3: 2, 4: 1, 5: 3},
    "cycle5": {1: 1, 2: 2, 3: 3, 4: 2, 5: 1},
    "star5": {1: 1, 2: 2, 3: 2, 4: 2, 5: 2},
    "bridge": {1: 1, 2: 2, 3: 1, 4: 1, 5: 2, 6: 2},
    "two_frag": {i: i for i in range(1, 7)},
}
SCHEDULERS = ("sync", "async")


def _params():
    p = BbcvcParams()
    p.mis_nbrs_max = 64
    return p


def _run(name, scheduler, k=6, seed=1):
    edges, w = GRAPHS[name], WEIGHTS[name]
    return edges, w, run_v4(edges, w, k, scheduler=scheduler,
                            params=_params(), max_ms=600_000, seed=seed)


def _tree_edges(res):
    """The BRANCH edges, as an undirected set. BRANCH is 1 in v4_mst."""
    out = set()
    for nid, node in res.nodes.items():
        for other, state in node.ghs_edge.items():
            if state == 1:
                out.add((min(nid, other), max(nid, other)))
    return out


def _kruskal(edges, w):
    parent = {v: v for v in w}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    tree = set()
    for u, v in sorted(edges, key=lambda e: (w[e[0]] + w[e[1]], e[0], e[1])):
        a, b = find(u), find(v)
        if a != b:
            parent[a] = b
            tree.add((u, v))
    return tree


# --------------------------------------------------------------- the backbone
@pytest.mark.parametrize("name", sorted(GRAPHS))
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_backbone_equals_the_central_oracle(name, scheduler):
    edges, w, res = _run(name, scheduler)
    got = {n for n, node in res.nodes.items() if node.mst_internal()}
    assert got == mst_internal_nodes(sorted(w), edges, w)


@pytest.mark.parametrize("name", sorted(GRAPHS))
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_run_terminates(name, scheduler):
    """Non-termination is the failure this variant kept producing."""
    _, _, res = _run(name, scheduler)
    assert getattr(res, "verdict", None) == "solved"


@pytest.mark.parametrize("name", sorted(GRAPHS))
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_termination_is_detected_and_reaches_everyone(name, scheduler):
    """Only the node that DETECTS termination sets `ghs_halted`.

    The rest learn by the DONE flood, so asserting that every node halted asks
    the wrong question: it would fail on a perfectly correct run. What must
    hold is that somebody detected it and that every node then left the GHS
    phase, which is what `_v4_done_seen` and the phase advance record.
    """
    _, w, res = _run(name, scheduler)
    assert any(res.nodes[n].ghs_halted for n in w), "nobody detected termination"
    stuck = sorted(n for n in w if res.nodes[n].phase == 1)
    assert not stuck, f"still in the GHS phase: {stuck}"


# ------------------------------------------------------- the tree is minimum
@pytest.mark.parametrize("name", sorted(GRAPHS))
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_tree_spans_and_is_minimum(name, scheduler):
    """A SPANNING tree of the right size can still be the wrong tree.

    This is the test that would have caught the fifth defect. That run
    terminated, produced exactly n-1 edges, and passed the validator; it was
    simply not minimum (8480 against 7708 on n10_m20 s2). Size and validity
    are not enough, the WEIGHT has to be checked.
    """
    edges, w, res = _run(name, scheduler)
    tree = _tree_edges(res)
    assert len(tree) == len(w) - 1
    cost = sum(w[u] + w[v] for u, v in tree)
    assert cost == sum(w[u] + w[v] for u, v in _kruskal(edges, w))


def test_a_spanning_tree_of_the_right_size_can_be_suboptimal():
    """The premise of the test above, stated as its own claim.

    Guards against someone weakening `test_tree_spans_and_is_minimum` back to
    an edge count on the grounds that the count is equivalent. It is not.
    """
    edges = [(1, 2), (2, 3), (1, 3)]
    w = {1: 1, 2: 2, 3: 10}
    mst = _kruskal(edges, w)
    other = {(1, 2), (2, 3)}
    assert len(other) == len(mst) == len(w) - 1
    assert sum(w[u] + w[v] for u, v in other) > sum(w[u] + w[v] for u, v in mst)


# --------------------------------------------------- the criterion is symmetric
@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_both_endpoints_agree_on_every_edge_weight(name):
    """Defect (b): the two ends of a merge named the same fragment differently.

    Each endpoint reconstructs the other's weight from key = w/(deg+1), which
    is lossy. If a node used its own exact weight while its peer used the
    reconstruction, the two totals differed by one unit and the merge produced
    two fragment identities for one fragment.
    """
    edges, w, res = _run(name, "sync")
    for u, v in edges:
        a, b = res.nodes[u], res.nodes[v]
        na = a.nbrs.get(v)
        nb = b.nbrs.get(u)
        if na is None or nb is None:
            continue
        assert a._weight_of(na)[0] == b._weight_of(nb)[0], \
            f"edge ({u},{v}) weighed differently by its two endpoints"


def test_fragment_identity_survives_the_wire():
    """Defect (a): a 2-byte frag field collapsed every 16.16 identity.

    The identity is a fixed-point edge weight, so it needs the full 32 bits.
    """
    big = (1 << 30) - 7
    msg = wire.Ghs(MsgType.GHS_INITIATE, 3, 11, 2, big, 0)
    back = wire.decode(wire.encode(msg))
    assert back.frag == big


# ------------------------------------------------------------- ownership
@pytest.mark.parametrize("name", sorted(GRAPHS))
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_ownership_is_total_and_unique(name, scheduler):
    edges, w, res = _run(name, scheduler)
    graph = CcvcGraph(nodes=sorted(w), edges=edges, weight=w, capacity_k=6)
    assert validate.validate(graph, res.cover, res.owner).valid
    # Both helpers take the RUN, not the owner map, and for `double_owned_edges`
    # that is the whole point: `owner[e] = nid` lets a second writer overwrite
    # the first silently, so double ownership is NOT REPRESENTABLE in the map
    # and an audit reading the map can never see it (BULGULAR_BB.md 79).
    assert unowned_edges(res, edges) == []
    assert double_owned_edges(res) == []


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_both_schedulers_reach_the_same_backbone(name):
    """The backbone is a property of the graph, not of the message order."""
    _, _, a = _run(name, "sync")
    _, _, b = _run(name, "async")
    ia = {n for n, nd in a.nodes.items() if nd.mst_internal()}
    ib = {n for n, nd in b.nodes.items() if nd.mst_internal()}
    assert ia == ib


# ------------------------------------------------- what "unknown" must mean
def test_a_node_does_not_wake_before_it_can_rank_its_edges():
    """Defect (e): waking on partial information picks the wrong edge silently.

    `_peer_w` returns INF_W for a neighbour whose degree has not arrived. A
    node that wakes then does not fail, it ranks the unknown neighbours last
    and connects to the lightest of whoever answered first.
    """
    _, w, res = _run("bridge", "sync")
    node = res.nodes[min(w)]
    assert node.key_fp is not None and node.deg is not None
    for nbr in node.nbrs.values():
        if nbr.is_edge:
            assert node._peer_w(nbr) < INF_W


def test_no_deferred_message_of_any_kind_blocks_reporting():
    """Defects (c) and (h): deferred traffic is somebody ELSE's question.

    A deferred REPORT is another node's early answer, a deferred CONNECT is a
    request to join, and a deferred TEST is a neighbour's probe. None of the
    three tells me anything about MY OWN minimum outgoing edge, and counting
    any of them as pending closes a circle: the message was deferred because of
    my state, and it then preserves that state.

    The TEST case took the longest to see because it looks like uncertainty. It
    is not: the sender is already blocked by its own `ghs_test_nid`, and my own
    search covers that same edge independently, since a TEST from a different
    fragment leaves the edge BASIC and `_ghs_test` tries every BASIC edge in
    weight order before declaring the search done.
    """
    _, w, res = _run("two_frag", "sync")
    node = res.nodes[min(w)]
    node.ghs_test_nid = None
    node.ghs_deferred = [(MsgType.GHS_REPORT, 2, 0, 0, 0),
                         (MsgType.GHS_CONNECT, 3, 0, 0, 0),
                         (MsgType.GHS_TEST, 4, 0, 0, 0)]
    assert not node._ghs_pending_unknown()


def test_an_outstanding_test_blocks_reporting():
    _, w, res = _run("two_frag", "sync")
    node = res.nodes[min(w)]
    node.ghs_deferred = []
    node.ghs_test_nid = 2
    assert node._ghs_pending_unknown()


def test_a_sleeping_node_defers_a_test_instead_of_dropping_it():
    """Defect (f): a sleeping receiver discarded the question entirely.

    The sender is blocked on this reply and has no timeout, so a dropped TEST
    is permanent: `_ghs_test` will not ask again while `ghs_test_nid` is set.
    Classical GHS never hits this because any message wakes a sleeping node,
    but a node here may have to stay asleep until its neighbours' weights
    arrive, which widens the window rather than closing it.
    """
    _, w, res = _run("two_frag", "sync")
    node = res.nodes[min(w)]
    peer = next(n for n in node.nbrs.values() if n.is_edge)
    node.ghs_state = 0                      # SLEEPING
    node.ghs_deferred = []
    sent_before = len(getattr(node, "_sent_log", []) or [])
    node._ghs_on_test(0, peer, 1, 12345)
    assert node.ghs_deferred, "the question was dropped, not deferred"
    assert node.ghs_deferred[0][0] is MsgType.GHS_TEST
    assert node.ghs_deferred[0][1] == peer.nid
    del sent_before


def test_the_core_comparison_is_a_strict_total_order():
    """Defect (g): two DIFFERENT edges of equal weight compared equal.

    The two core nodes each report their half's minimum outgoing edge and the
    one holding the smaller acts. Comparing only w(u)+w(v) makes that decision
    undefined under ties: neither side is greater, so neither acts and neither
    halts. `_weight_of` is already a total order; the bug was that only its
    first component survived into the report.
    """
    _, w, res = _run("two_frag", "sync")
    node = res.nodes[min(w)]
    same_weight_different_edge = ((100, 1, 5), (100, 2, 3))
    a, b = same_weight_different_edge
    assert a[0] == b[0], "the fixture must actually tie on weight"
    assert (a < b) != (b < a), "one must still be strictly smaller"
    for key in same_weight_different_edge:
        assert node._unpack_tie(key[0], node._pack_tie(key)) == key


def test_report_ties_do_not_freeze_the_core():
    """The whole-run form of the test above, on the instance that froze.

    Node weights are chosen so that (1,2) and (3,4) weigh the same, which is
    exactly the shape that stalled five fragments at level 1 on n25_m50 s2.
    """
    edges = [(1, 2), (2, 3), (3, 4), (1, 4)]
    w = {1: 1, 2: 3, 3: 1, 4: 3}
    assert w[1] + w[2] == w[3] + w[4], "the fixture must tie"
    res = run_v4(edges, w, 6, scheduler="sync", params=_params(),
                 max_ms=600_000, seed=1)
    assert getattr(res, "verdict", None) == "solved"
    tree = _tree_edges(res)
    assert len(tree) == len(w) - 1
    assert sum(w[u] + w[v] for u, v in tree) == \
        sum(w[u] + w[v] for u, v in _kruskal(edges, w))


def test_an_epoch_restart_rewinds_the_ghs_latches():
    """The fourth deadlock: an epoch restart left the termination latches set.

    `ghs_halted` and `_v4_done_seen` are LATCHES -- each makes its own handler a
    no-op forever after -- and between them they are the only two ways a node
    leaves PH_MIS. `BbcvcNode._reset_to_phase0` rewinds phase, key, degree and
    role but knew nothing about them, so a node that had finished Phase 1 once
    could never finish it again and sat in PH_MIS until the deadline.

    The direct consequence is asserted, not just the flags: after a restart a
    halt must still be able to move the node out of PH_MIS.
    """
    _, w, res = _run("bridge", "sync")
    node = res.nodes[min(w)]
    node.ghs_halted = True
    node._v4_done_seen = True
    node.ghs_state = 2                       # FOUND
    node.ghs_deferred = [(MsgType.GHS_TEST, 2, 0, 0, 0)]

    node._reset_to_phase0(0, reason="test")

    assert node.ghs_halted is False
    assert node._v4_done_seen is False
    assert node.ghs_state == 0               # SLEEPING: the search starts over
    assert node.ghs_parent is None
    assert node.ghs_edge == {}
    assert node.ghs_deferred == []           # names a discarded fragment
    assert node.ghs_best_wt == INF_W and node.ghs_best_nid is None
    assert node._v4_mis_claim is None and node._v4_in_backbone is False

    node.phase = 1                           # PH_MIS, where the restart lands
    node._ghs_halt(0)
    assert node.phase == 2, "a halt after a restart must still leave PH_MIS"


def test_ghs_survives_five_per_cent_loss():
    """WAS A PINNED LIMIT, NOW A GUARANTEE. Kept so it cannot regress.

    This test used to assert the OPPOSITE: that GHS returned an empty cover at
    five per cent loss, pinned so that fixing it would be noticed. Its own note
    said that when message recovery was designed properly the test should start
    failing. It did, so it now pins the other side.

    What changed is in `v4_mst._ghs_reassert`, together with the two defects
    that enabling it EXPOSED rather than caused. `_ghs_change_root` now acts
    once per round, so a repeated REPORT cannot send a second CONNECT down an
    edge already used and rewire the tree into a parent cycle. A REPORT now
    carries the level it was written for, so one belonging to a previous round
    is not counted after the reset that should have erased it.

    MEASURED on the nine graphs the stations saw, five seeds each: 45 of 45
    valid at five per cent, against 1 of 45 with no repetition at all. Getting
    there took more than the repetition: it made five latent deadlocks
    reproducible, and each was fixed where it lived rather than papered over
    here.
    """
    edges, w = GRAPHS["bridge"], WEIGHTS["bridge"]
    g = validate.make_graph(edges, 6, w, sorted(w))

    for loss in (0.0, 0.02):
        for seed in range(8):
            res = run_v4(edges, w, 6, scheduler="sync", params=_params(),
                         max_ms=200_000, seed=seed, loss=loss)
            assert res.verdict == "solved", f"kayip {loss} tohum {seed}"
            assert validate.validate(g, res.cover, res.owner).valid

    # AT FIVE PER CENT THE CLAIM IS WEAKER AND IS STATED AS SUCH: most seeds
    # finish, and a seed that does not finish SAYS SO. Six of eight solve here;
    # the two that do not report `truncated` with a partial cover, never a
    # `solved` that the validator then contradicts.
    solved = 0
    for seed in range(8):
        res = run_v4(edges, w, 6, scheduler="sync", params=_params(),
                     max_ms=200_000, seed=seed, loss=0.05)
        rep = validate.validate(g, res.cover, res.owner)
        if res.verdict == "solved":
            assert rep.valid, f"yanlis basari: tohum {seed}"
            solved += 1
    assert solved >= 5, f"bes yuzde kayipta yalnizca {solved}/8 cozuldu"


# ------------------------------------------- an unfinished search is not empty
#: `n15_m30_s2` of the Dagdeviren benchmark, after `sweep.prepare` (weight scale
#: 10, ids relabelled 1..15). Embedded rather than loaded, because the dataset
#: is not in the repository and this is the instance the defect lived on.
N15_M30_S2_W = {1: 760.0, 2: 1095.0, 3: 751.0, 4: 1176.0, 5: 540.0, 6: 750.0,
                7: 960.0, 8: 1030.0, 9: 1089.0, 10: 932.0, 11: 272.0, 12: 220.0,
                13: 823.0, 14: 318.0, 15: 562.0}
N15_M30_S2_E = [(1, 2), (1, 13), (2, 3), (2, 12), (3, 4), (3, 10), (3, 11),
                (4, 5), (4, 7), (4, 10), (4, 13), (5, 6), (5, 9), (6, 7),
                (6, 8), (6, 13), (7, 8), (7, 9), (7, 12), (7, 13), (8, 9),
                (9, 10), (9, 11), (9, 13), (10, 11), (11, 12), (12, 13),
                (12, 15), (13, 14), (14, 15)]


def test_a_node_in_find_does_not_report_before_its_own_search_settles():
    """"No question outstanding" is NOT "my search is over".

    `ghs_test_nid` says a question is in flight; `ghs_test_done` says the answer
    is in. Between a REJECT that clears the first and the next timer tick that
    calls `_ghs_test` on the following BASIC edge, BOTH are false. A child's
    REPORT arriving in that window used to carry the node out of FIND, and
    `_ghs_test` only ever runs in FIND, so every remaining BASIC edge went
    untested and the node reported INF for edges it owned.
    """
    _, w, res = _run("two_frag", "sync")
    node = res.nodes[min(w)]
    node.ghs_state = 1                       # FIND
    node.ghs_test_nid = None                 # no question in flight
    node.ghs_test_done = False               # but the search has not settled
    node.ghs_deferred = []
    node._ghs_try_report(0, [n for n in node.nbrs.values() if n.is_edge])
    assert node.ghs_state == 1, "reported with its own search unfinished"

    node.ghs_test_done = True
    node._ghs_try_report(0, [n for n in node.nbrs.values() if n.is_edge])
    assert node.ghs_state == 2, "a settled search must still be able to report"


def test_n15_m30_s2_async_does_not_deadlock_at_zero_loss():
    """The one truncated run left in the small group, pinned as solved.

    WHAT IT COST BEFORE THE GUARD. Node 13 is INITIATEd into FIND, TESTs (13,14)
    and is REJECTed; node 1's REPORT of INF then lands while `ghs_test_nid` is
    None and `ghs_test_done` is still False, and node 13 reports INF upward with
    BASIC = [4, 6, 7, 9] never tested. Edge (13,6) weighs 103088128 and is the
    LIGHTEST of the five crossing the two surviving fragments, so its fragment
    claimed (5,9) at 106758143 instead. The other fragment claimed (6,13), each
    sent CONNECT at equal level on an edge the far side still held BASIC, both
    took the "equal level but the edge is not yet ours" branch, and the run sat
    frozen at level 1 until the four thousand second budget ran out.

    The assertion is on the TREE, not only on the verdict: a deadlock that
    resolves into the wrong tree would still pass a verdict check.
    """
    res = run_v4(N15_M30_S2_E, N15_M30_S2_W, 6, scheduler="async",
                 params=_params(), max_ms=200_000, seed=2, loss=0.0)
    assert res.verdict == "solved"
    tree = _tree_edges(res)
    assert len(tree) == len(N15_M30_S2_W) - 1
    assert sum(N15_M30_S2_W[u] + N15_M30_S2_W[v] for u, v in tree) == \
        sum(N15_M30_S2_W[u] + N15_M30_S2_W[v]
            for u, v in _kruskal(N15_M30_S2_E, N15_M30_S2_W))
    got = {n for n, nd in res.nodes.items() if nd.mst_internal()}
    assert got == mst_internal_nodes(sorted(N15_M30_S2_W), N15_M30_S2_E,
                                     N15_M30_S2_W)
    g = validate.make_graph(N15_M30_S2_E, 6, N15_M30_S2_W,
                            sorted(N15_M30_S2_W))
    assert validate.validate(g, res.cover, res.owner).valid
