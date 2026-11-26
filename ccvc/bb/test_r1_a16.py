"""Amendment 16 (R1-repair): regression tests, one per cause, on development data.

Each test fails on the frozen version 09af268d95e0 and passes on R1-repair.
A: a TemperFlux hub whose join is uphill leaves the cover disconnected (T2).
B: connectors freeze while a stale label is still held (T1, T2).
C: FabricTree's core halts on a tree with asymmetric BRANCH marks (F1).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, heldout, sweep, v4_mst, validate  # noqa: E402
from ccvc.bb.anneal import AnnealParams  # noqa: E402
from ccvc.bb.v6_anneal import run_anneal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def dev(name):
    """A development instance of the published dataset, relabelled as the sweep does."""
    from ccvc.bb import matrix

    path = os.path.join(ROOT, "data", "DagdevirenDataset", name + ".txt")
    if not os.path.exists(path):
        pytest.skip("benchmark dataset not present")
    w, e, _ = sweep.prepare(*matrix.load_instance(path))
    return e, w


def _two_label_out_nodes(nodes):
    """OUT nodes that see two or more labels among their cover neighbours."""
    out = []
    for v, nd in nodes.items():
        if nd.x:
            continue
        labels = {ps.label for _, ps in nd._peers(nd._nbrs_active()) if ps.x}
        if len(labels) > 1:
            out.append(v)
    return out


def _connected_or_not_solved(res, e, w, k):
    g = validate.make_graph(list(e), k, w, sorted(w))
    comps = validate.cover_components(g, set(res.cover))
    return (not res.converged) or len(comps) == 1, len(comps)


# --------------------------------------------------------------------------
# A, T2: Barabasi-Albert graph grown from a star (development seed), hubs of
# degree well above 2k next to pendant nodes in the cover.
#: Synthetic H2b development seed (< 100): n = 25, attach 3, hub degree 18.
#: Scanning seeds 1 to 39 on the frozen code, Anneal-Local async, channel seed
#: 1, this was the one false success (2 cover components).
HUB_SEED = 20


def test_t2_hub_overload_cover_is_connected():
    w0, e0, _ = heldout.generate_one("H2b", 25, 3, HUB_SEED)
    w, e, _ = sweep.prepare(w0, e0, weight_scale=sweep.DEFAULT_WEIGHT_SCALE)
    k = 6
    p = AnnealParams(rng_seed=1, mis_nbrs_max=64)
    res = run_anneal(e, w, k, scheduler="async", params=p, seed=1, max_ms=4_500_000)
    deg = {v: 0 for v in w}
    for a, b in e:
        deg[a] += 1
        deg[b] += 1
    assert max(deg.values()) >= 2 * k + 4, "the fixture must have an overloaded hub"
    assert res.converged
    g = validate.make_graph(list(e), k, w, sorted(w))
    vr = validate.validate(g, sorted(res.cover), res.owner)
    assert vr.valid, [str(x)[:80] for x in vr.violations][:3]
    assert not _two_label_out_nodes(res.nodes)


# --------------------------------------------------------------------------
# B, T1: a label whose hop count exceeds n_bar is dead whatever its heartbeat,
# and a change of (label, hops) is reported as a move for the freeze rule.
def test_t1_a_label_beyond_the_node_bound_is_dead():
    from ccvc.bb import anneal, simnet
    from ccvc.bb.anneal import PeerState

    ids = [1, 2, 3]
    w = {v: 10.0 for v in ids}
    net = simnet.SimNet(ids, [(1, 2), (2, 3)], macs=bbcvc.macs_for(ids))
    nd = anneal.build_nodes(net, w, 2, AnnealParams(n_bound=3))[3]
    nd.x = 1

    class Peer:
        nid = 2

    def heard(hops):
        return PeerState(
            x=True,
            ell_fp=0,
            label=1,
            label_ctr=5,
            token=0,
            cool=0,
            heard_ms=0,
            hops=hops,
        )

    assert nd._loop_c(0, [(Peer, heard(1))])
    assert (nd.label, nd.label_hops) == (1, 2)
    assert nd._loop_c(0, [(Peer, heard(2))]), "a hop change is not quiet"
    assert (nd.label, nd.label_hops) == (1, 3)
    assert nd._loop_c(0, [(Peer, heard(3))]), "the dead label must be dropped"
    assert (nd.label, nd.label_hops) == (nd.nid, 0)


# --------------------------------------------------------------------------
# B, T1 + T2: the repay-off ablation row of block M10 (development n50_m100_s3,
# sync, channel seed 3). Before the repair its connectors froze on one stale
# label and the run reported solved with two cover components.
def test_t1_no_out_node_freezes_on_two_labels():
    e, w = dev("n50_m100_s3")
    k = 6
    p = AnnealParams(rng_seed=3, mis_nbrs_max=64, repay_bridge_credit=False)
    res = run_anneal(e, w, k, scheduler="sync", params=p, seed=3, max_ms=200_000)
    ok, comps = _connected_or_not_solved(res, e, w, k)
    assert ok, f"reported solved with {comps} cover components"
    if res.converged:
        assert not _two_label_out_nodes(res.nodes)


# --------------------------------------------------------------------------
# C, F1: one BRANCH mark of a tree node is made asymmetric at the moment the
# core's halt test fires. The halt must be refused while the asymmetry lasts;
# once the mark is restored the next halt test certifies and the run solves.
def test_f1_halt_with_asymmetric_branch_marks_is_refused():
    e, w = dev("n10_m20_s1")
    k = 6
    nodes = {}
    ctl = {"asym": None, "done": False, "halts_while_asym": 0}

    class Node(v4_mst.V4MstDistNode):
        def _ghs_halt(self, now, partner=None):
            if ctl["asym"] is None and not ctl["done"]:
                for c in sorted(nodes):
                    nd = nodes[c]
                    par = nd.ghs_parent
                    if (
                        par is not None
                        and nodes[par].ghs_parent != c
                        and nd.ghs_edge.get(par) == v4_mst.BRANCH
                    ):
                        nd.ghs_edge[par] = v4_mst.REJECTED
                        ctl["asym"] = (c, par)
                        break
            super()._ghs_halt(now, partner)

        def _log(self, event, **fields):
            if event == "ghs_halt" and ctl["asym"] is not None:
                ctl["halts_while_asym"] += 1
            if event == "halt_check_cancel" and ctl["asym"] is not None:
                c, par = ctl["asym"]
                nodes[c].ghs_edge[par] = v4_mst.BRANCH
                ctl["asym"], ctl["done"] = None, True
            super()._log(event, **fields)

    def factory(net, weights, kk, pp):
        nodes.update(
            {nid: Node(weights[nid], net.port(nid), pp, kk) for nid in sorted(weights)}
        )
        return nodes

    p = bbcvc.BbcvcParams()
    p.mis_nbrs_max = 64
    res = bbcvc.run_bbcvc(
        e, w, k, scheduler="sync", params=p, max_ms=600_000, node_factory=factory
    )
    assert ctl["asym"] is not None or ctl["done"], "no tree node was corrupted"
    assert ctl["halts_while_asym"] == 0, "the core halted on asymmetric marks"
    assert ctl["done"], "the halt was never refused and retried"
    assert res.converged
    g = validate.make_graph(list(e), k, w, sorted(w))
    assert validate.validate(g, sorted(res.cover), res.owner).valid
