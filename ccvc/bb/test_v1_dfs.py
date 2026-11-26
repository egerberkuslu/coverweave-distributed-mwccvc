"""DFS-Spanning-Backbone: distribution, scheduler and termination tests.

These exercise the three pieces that were missing until now -- walk driving,
termination detection and the backbone MIS -- on graphs whose DFS structure is
known by construction, so a failure names the piece rather than the instance.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from ccvc.bb import validate  # noqa: E402
from ccvc.bb.bbcvc import BbcvcParams  # noqa: E402
from ccvc.bb.v1_dfs import build_v1_nodes, run_v1  # noqa: E402
from ccvc.bb.variants import (  # noqa: E402
    adjacency, dfs_internal_nodes, double_owned_edges, unowned_edges,
)
from ccvc.bridge import CcvcGraph  # noqa: E402

PATH5 = [(1, 2), (2, 3), (3, 4), (4, 5)]
CYCLE5 = [(1, 2), (2, 3), (3, 4), (4, 5), (1, 5)]
STAR5 = [(1, 2), (1, 3), (1, 4), (1, 5)]
BRIDGE = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (3, 7)]
#: Two triangles joined by one edge: a walk must cross the bridge to span both.
TWO_FRAG = [(1, 2), (1, 3), (2, 3), (3, 4), (4, 5), (4, 6), (5, 6)]
#: Two local minima (1 and 2), so a walk is genuinely preempted.
TWO_STARTS = [(1, 3), (2, 4), (3, 5), (4, 6), (5, 7), (2, 7)]

GRAPHS = {"path5": PATH5, "cycle5": CYCLE5, "star5": STAR5,
          "bridge": BRIDGE, "two_frag": TWO_FRAG, "two_starts": TWO_STARTS}


def _w(edges):
    n = max(max(e) for e in edges)
    return {i: 1 + (i % 3) for i in range(1, n + 1)}


def _params():
    p = BbcvcParams()
    p.mis_nbrs_max = 64      # the benchmark is not a unit-disk graph (finding 3)
    return p


def _run(edges, scheduler="sync", seed=1, loss=0.0, k=4):
    return run_v1(edges, _w(edges), k, scheduler=scheduler, params=_params(),
                  max_ms=400_000, seed=seed, loss=loss)


def _validate(run, edges, k=4):
    w = _w(edges)
    g = CcvcGraph(nodes=sorted(w), edges=list(edges), weight=w, capacity_k=k)
    return validate.validate(g, run.cover, run.owner)


# ------------------------------------------------------------ graph families
@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_every_graph_family_terminates_and_validates(name):
    edges = GRAPHS[name]
    r = _run(edges)
    assert r.verdict == "solved", f"{name}: {r.verdict}"
    rep = _validate(r, edges)
    assert rep.valid, [v.kind for v in rep.violations]


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_the_backbone_equals_the_reference_dfs_internal_set(name):
    """The distributed walk must build the same tree the reference builds.

    This is the whole correctness claim of the arm: internal nodes of a DFS tree
    are a 2-approximate vertex cover, and a token walk that produces a DIFFERENT
    set is not that algorithm.
    """
    edges = GRAPHS[name]
    r = _run(edges)
    got = {nid for nid, nd in r.nodes.items() if nd.dfs_internal}
    ref = set(dfs_internal_nodes(sorted(_w(edges)), list(edges)))
    assert got == ref, f"{name}: got {sorted(got)} ref {sorted(ref)}"


# -------------------------------------------------------------- preemption
def test_preemption_fires_when_there_are_two_local_minima():
    """The measured preemption cost must be READABLE, not inferred.

    A zero count on a graph with one local minimum is the correct answer; this
    graph has two, so the counter has to move.
    """
    adj = adjacency(sorted(_w(TWO_STARTS)), TWO_STARTS)
    minima = [v for v in adj if adj[v] and v < min(adj[v])]
    assert len(minima) >= 2, f"premise failed: minima={minima}"
    r = _run(TWO_STARTS)
    assert sum(n.dfs_preempted for n in r.nodes.values()) > 0
    assert sum(n.dfs_offers for n in r.nodes.values()) > 0


def test_a_single_local_minimum_yields_no_preemption():
    """The counter must not fire spuriously; STAR5 can only start one walk."""
    r = _run(STAR5)
    assert sum(n.dfs_preempted for n in r.nodes.values()) == 0


#: F19. Walks 1 and 2 start together. Node 4 offers walk 2's token to node 2
#: in the slot in which walk 1 reaches node 4, so the refusal comes back to a
#: node that has joined walk 1; once node 2 joins too, both refuse it to each
#: other for ever and the channel never goes quiet.
PING_PONG = [(1, 5), (2, 3), (2, 4), (3, 4), (4, 6), (5, 6)]
#: F19. Node 5 joins walk 1 and bounces walk 2's token; walk 2 then reads node
#: 5 as visited, finishes first and floods its DFS_DONE, so node 2 leaves the
#: walk phase and never returns walk 1's token to node 5.
EARLY_DONE = [(1, 4), (1, 5), (2, 3), (2, 5), (4, 5), (5, 6)]


@pytest.mark.parametrize("edges", [PING_PONG, EARLY_DONE],
                         ids=["ping_pong", "early_done"])
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_a_larger_walk_dies_on_contact(edges, scheduler):
    """Extinction: a TOKEN of a larger walk is ignored, never sent back.

    Both graphs have two local minima. On the code before F19 the
    synchronous runs end truncated on a lossless channel.
    """
    r = _run(edges, scheduler=scheduler)
    assert r.verdict == "solved", r.verdict
    assert _validate(r, edges).valid
    got = {nid for nid, nd in r.nodes.items() if nd.dfs_internal}
    assert got == set(dfs_internal_nodes(sorted(_w(edges)), list(edges)))


# ------------------------------------------------------------- schedulers
@pytest.mark.parametrize("name", ["path5", "bridge", "two_frag"])
def test_the_same_node_class_serves_both_schedulers(name):
    edges = GRAPHS[name]
    outs = {s: _run(edges, scheduler=s) for s in ("sync", "async")}
    for s, r in outs.items():
        assert r.verdict == "solved", f"{name}/{s}"
        assert _validate(r, edges).valid, f"{name}/{s}"
    ref = set(dfs_internal_nodes(sorted(_w(edges)), list(edges)))
    for s, r in outs.items():
        got = {nid for nid, nd in r.nodes.items() if nd.dfs_internal}
        assert got == ref, f"{name}/{s}"


def test_the_same_seed_reproduces_the_same_run():
    a = _run(BRIDGE, seed=7)
    b = _run(BRIDGE, seed=7)
    assert (a.tx, a.slots, sorted(a.cover)) == (b.tx, b.slots, sorted(b.cover))


# ------------------------------------------------------------------- loss
@pytest.mark.parametrize("loss", [0.05, 0.15])
def test_the_walk_survives_a_lossy_channel(loss):
    """Loss must not produce a wrong answer; it may cost more or give up."""
    r = _run(BRIDGE, loss=loss, seed=3)
    assert r.verdict in ("solved", "unresolved", "truncated")
    if r.verdict == "solved":
        assert _validate(r, BRIDGE).valid


# -------------------------------------------------------------- ownership
@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_ownership_is_total_and_unique(name):
    """Both directions of the conservation law, because three lost-edge bugs and
    one duplicated-edge bug were all invisible to a check that tested one."""
    edges = GRAPHS[name]
    r = _run(edges)
    assert unowned_edges(r, edges) == []
    assert double_owned_edges(r) == []


# ---------------------------------------------------------------- locality
def test_the_node_never_receives_a_graph():
    """DFS-Spanning-Backbone gets weight and a platform handle. Nothing else."""
    import inspect
    src = inspect.getsource(build_v1_nodes)
    assert "edges" not in src, "the DFS-Spanning-Backbone factory must not take edges"
    assert "adjacency" not in src


def test_v1_state_only_ever_names_neighbours():
    """Pin the PROPERTY, not the attribute name -- but only over fields whose
    meaning is known.

    Two earlier versions of this test were unsound and both are worth recording.
    The first asserted `not hasattr(node, "edges")`, which failed because
    `BootstrapNode.edges` is a METHOD returning the node's own bidirectional
    neighbours -- local information a node is entitled to. The second swept
    every container attribute for small integers that happen to be valid node
    ids, and flagged `_barrier_hits` (keyed by PHASE) and `_last_fp` (holding
    fixed-point key values). An untyped small integer cannot be told apart from
    a node id by inspection, so a structural sweep produces false positives and
    then gets switched off, which is worse than a narrow sound check.

    So this checks the fields that actually hold node ids, named explicitly.
    """
    edges = BRIDGE
    r = _run(edges)
    adj = adjacency(sorted(_w(edges)), edges)
    for nid, nd in r.nodes.items():
        allowed = set(adj[nid]) | {nid}
        held = set(nd.dfs_tried) | set(nd._v1_bb_members) | set(nd._v1_bb_decided)
        if nd.dfs_parent is not None:
            held.add(nd.dfs_parent)
        if nd._v1_offer_out is not None:
            held.add(nd._v1_offer_out)
        held |= set(nd.nbrs)
        assert held <= allowed, (
            f"node {nid} names non-neighbours {sorted(held - allowed)}; "
            f"neighbours are {sorted(adj[nid])}")


def test_the_local_edge_view_is_exactly_the_neighbour_set():
    """`node.edges()` must return neighbours, never the graph."""
    r = _run(BRIDGE)
    adj = adjacency(sorted(_w(BRIDGE)), BRIDGE)
    for nid, nd in r.nodes.items():
        assert set(nd.edges()) == set(adj[nid]), nid
