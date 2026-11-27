"""Regression tests for the R1 protocol repairs F10-F13 (contract R1_PREREG.md, Amendment 7).

Backend: the event simulator (SimNet through `run_bbcvc`, `rssi_range=None`).
Faults are injected with the deterministic `SimNet.drop` predicate; the rest of
the channel is lossless unless a loss rate is named. Every instance is a
development instance (the worked example or a file of the published dataset);
no held-out instance and no pre-registered seed is used.
"""

from __future__ import annotations

import collections
import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, validate  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TAU = 200
PUSH_NACK = int(MsgType.PUSH_NACK)


def dev(name):
    """A development instance of the published dataset, relabelled as the sweep does."""
    from ccvc.bb import matrix
    from ccvc.bb.sweep import prepare

    path = os.path.join(ROOT, "data", "DagdevirenDataset", name + ".txt")
    if not os.path.exists(path):
        pytest.skip("benchmark dataset not present")
    w, e, _ = prepare(*matrix.load_instance(path))
    return e, w


def copies_dropped(n, src, dst, mtype, t_from):
    """Drop the first `n` frames of `mtype` from src to dst sent at or after t_from."""
    left = [n]
    sent = []

    def drop(t, s, d, m):
        if m == mtype and (s, d) == (src, dst) and t >= t_from:
            sent.append(t)
            if left[0] > 0:
                left[0] -= 1
                return True
        return False

    drop.sent = sent
    return drop


# --------------------------------------------------------------------------
# F10, replaced by R2 (Amendment 17): a refused chain takes nothing
# --------------------------------------------------------------------------
#: Development graph n20_m80_s1 at capacity k = 5 (slack: m = 80 < nk = 100),
#: lossless. A push chain at node B outlasts node A's timeout, A's
#: retransmission gets a busy NACK and A keeps the edge. Under F10 the chain
#: then succeeded, B took the edge and sent a late acknowledgement B -> A that
#: had to be confirmed, the mechanism of the Lean run `traceBusy`. Under R2 the
#: refused chain succeeds at the same moment (`t_sent`) but takes nothing.
F10_CASES = [
    pytest.param("sync", 16, 4, 11_000, (4, 16), id="sync-16-to-4"),
    pytest.param("async", 13, 6, 7_218, (6, 13), id="async-13-to-6"),
]


def f10_run(scheduler, drop=None):
    e, w = dev("n20_m80_s1")
    return bbcvc.run_bbcvc(
        e,
        w,
        5,
        scheduler=scheduler,
        params=bbcvc.BbcvcParams(mis_nbrs_max=64),
        max_ms=3_000_000,
        seed=1,
        drop=drop,
        watch_ms=0,
    )


def late_events(r):
    return [x for x in r.net.log_records if x["event"].startswith("late_ack")]


def chain_ends(monkeypatch):
    """Record (node, source, edge, refused, outcome, time) of every chain end."""
    out = []
    orig = bbcvc.BbcvcNode._finish_push_job

    def wrap(self, now, ok):
        j = self._push_job
        if j is not None:
            out.append((self.nid, j.src, j.e, j.nacked, ok, now))
        return orig(self, now, ok)

    monkeypatch.setattr(bbcvc.BbcvcNode, "_finish_push_job", wrap)
    return out


@pytest.mark.parametrize("scheduler,b,a,t_sent,e", F10_CASES)
def test_R2_a_refused_chain_takes_nothing(monkeypatch, scheduler, b, a, t_sent, e):
    ends = chain_ends(monkeypatch)
    r = f10_run(scheduler)
    assert (b, a, e, True, True, t_sent) in ends, "the refused chain succeeds"
    assert r.verdict == "solved" and r.double_claimed == {}
    assert late_events(r) == [], "R2: no late acknowledgement exists"
    assert not any(n._pending for n in r.nodes.values())


@pytest.mark.parametrize("scheduler,b,a,t_sent,e", F10_CASES)
def test_R2_busy_refusal_lost_three_times_leaves_no_double_claim(
    scheduler, b, a, t_sent, e
):
    drop = copies_dropped(3, b, a, PUSH_NACK, 0)
    r = f10_run(scheduler, drop)
    assert r.converged and r.verdict == "solved"
    assert r.double_claimed == {}, r.double_claimed
    g = validate.make_graph(r.net.edges, 5, {i: n.w for i, n in r.nodes.items()})
    assert validate.validate(g, r.cover, r.owner).valid
    assert len(drop.sent) >= 4, "three copies lost, a fourth is sent"
    assert late_events(r) == []
    assert not any(n._pending for n in r.nodes.values())


# --------------------------------------------------------------------------
# F13: a neighbour heard but not verified keeps a node from finishing
# --------------------------------------------------------------------------
def worked():
    from ccvc.bb.figures import WORKED_EDGES, WORKED_K, WORKED_WEIGHTS

    return list(WORKED_EDGES), dict(WORKED_WEIGHTS), WORKED_K


LINK = int(MsgType.LINK)


def link_lost_until(src, dst, slot):
    """Every LINK frame src -> dst sent before `slot` is lost, so src's
    handshake with dst fails while dst verifies src."""
    return lambda t, s, d, m: m == LINK and (s, d) == (src, dst) and t < slot * TAU


@pytest.mark.parametrize(
    "src,dst,until,scheduler",
    [
        (6, 5, 20, "sync"),
        (6, 5, 20, "async"),
        (2, 3, 20, "sync"),
        # the shape of residual R3: the retry used to land after the verdict
        # and restart the network (136 frames in the window after it)
        (1, 2, 40, "sync"),
    ],
)
def test_F13_a_failed_link_handshake_is_retried_before_the_verdict(
    src, dst, until, scheduler
):
    """Before F13: src froze without dst, finished, and the network fell silent
    before the 12-period retry could happen (or the retry restarted it after
    the verdict); the run ended valid only on a discovered graph that lacked
    the planned link (planned_missing 1; invalid on the planned graph for
    (6,5) and (2,3)). Now src waits at QUIET, the retry succeeds, the epoch
    restarts once and the run ends valid on the planned graph."""
    from ccvc.bb import sweep as S

    e, w, k = worked()
    r = bbcvc.run_bbcvc(
        e,
        w,
        k,
        scheduler=scheduler,
        max_ms=600_000,
        drop=link_lost_until(src, dst, until),
    )
    d = S.discovered_reading(e, w, k, r)
    assert r.verdict == "solved"
    assert d["planned_missing"] == 0 and d["valid_discovered"]
    assert validate.validate(validate.make_graph(e, k, w), r.cover, r.owner).valid
    assert (r.cover, r.total_weight) == ([2, 3, 4, 5, 6, 7, 8, 9], 27)
    # Note to Amendment 15 (D2): the freeze now waits for the retried round, so
    # the link enters the first frozen view and no restart is needed.
    assert r.restarts == 0 and r.tx_after_convergence == 0


def test_F13_a_closed_gate_is_not_a_pending_neighbour():
    """A record whose RSSI gate is closed is not a link being established;
    otherwise a one-way gate would keep the run from finishing."""
    e, w, k = worked()
    r = bbcvc.run_bbcvc(e, w, k, max_ms=600_000)
    node = r.nodes[2]
    now = r.net.now_ms()
    rec = node.nbrs[1]
    assert not node._unverified_pending(now)
    rec.bidir, rec.last_ms = False, now
    assert node._unverified_pending(now)
    rec.link_up = False
    assert not node._unverified_pending(now)
    rec.link_up, rec.last_ms = True, now - node._quiet_window_ms(1) - 1
    assert not node._unverified_pending(now), "silent for its window"
    rec.bidir, rec.last_ms = True, now


@pytest.mark.parametrize(
    "victim,slot",
    [
        # before F13: the survivors never finished
        (6, 20),
        (5, 48),
        # before F13: verdict at slot 53 with the survivors still claiming
        # edges to the removed node (bad_owner)
        (1, 44),
    ],
)
def test_F13_a_node_removed_while_its_neighbours_are_quiet_is_detected(victim, slot):
    """Worked example, synchronous, lossless; the victim is switched off while
    neighbours of it are QUIET. QUIET expires a silent neighbour below DONE,
    the epoch restarts, and the survivors end valid."""
    from ccvc.bb.test_r1_repairs import _switch_off

    verdict, valid, bumps, _ = _switch_off(victim, slot, True, False)
    assert bumps and bumps[0] > slot, "the removal restarts the epoch"
    assert verdict is not None and valid


# --------------------------------------------------------------------------
# F11: deepening ownership repair
# --------------------------------------------------------------------------
def test_F11_the_m_equals_nk_instance_is_solved_by_deepening():
    """n200_m1200_s6, k = 6, m = nk: the cover is forced to C = V and only a
    perfect 6-orientation is valid. Before F11 the MIS-connector arm used up
    its repair rounds at depth 3 and ended `unresolved` with an overloaded
    node (load 7). With F11 the depth doubles after the rounds (6 suffices)
    and the run ends solved and valid. Simulator, lossless, synchronous.
    Amendment 17: that solution used 129 late acknowledgements of F10, the
    mechanism of the Lean run `traceBusy`. With R2 a refused chain takes
    nothing, and the run ends unresolved with one overloaded node and no
    double claim; this quality loss is an endpoint of the amendment."""
    e, w = dev("n200_m1200_s6")
    r = bbcvc.run_bbcvc(
        e,
        w,
        6,
        scheduler="sync",
        params=bbcvc.BbcvcParams(mis_nbrs_max=64),
        max_ms=22_000_000,
        seed=1,
        watch_ms=0,
    )
    assert r.verdict == "unresolved" and r.converged and r.double_claimed == {}
    assert sum(len(n.owned) > n.k for n in r.nodes.values()) == 1
    assert not [x for x in r.net.log_records if x["event"].startswith("late_ack")]
    deepen = [x["ttl"] for x in r.net.log_records if x["event"] == "push_deepen"]
    # F17b (Amendment 11): the doubling from 3 stops at the cap D_max = 8, so 3, 6, 8
    cap = bbcvc.BbcvcParams().push_depth_max
    assert deepen and max(deepen) <= cap and all(t % 3 == 0 or t == cap for t in deepen)


def NO_WAVE(t, s, d, m):
    """F17: drop every CERT, so no certificate wave completes."""
    return m == int(MsgType.CERT)


def test_F11_depth_doubles_up_to_the_node_bound(monkeypatch):
    """The worked example at k = 1 is infeasible (m = 15 > nk = 10): every
    overloaded node uses up its rounds, then deepens 3 -> 6 -> 10, capped by
    the node bound that `run_bbcvc` gives every node, and only then reports
    unresolved. F17's wave would certify the instance first, so its CERT
    frames are dropped here, and F17b's cap D_max = 8 is lifted, so the
    deepening runs as before F17."""
    e, w, _ = worked()
    # Amendment 13, G4: a wave whose frames are all dropped is owed for ever,
    # so the wave is switched off at its start instead of by dropping CERTs.
    monkeypatch.setattr(bbcvc.BbcvcNode, "_cert_start", lambda self, now: None)
    p = bbcvc.BbcvcParams(push_depth_max=None)
    r = bbcvc.run_bbcvc(e, w, 1, params=p, max_ms=2_000_000)
    assert {n.p.n_bound for n in r.nodes.values()} == {10}
    assert bbcvc.BbcvcParams().n_bound is None
    assert r.verdict == "unresolved" and r.infeasible_reason == "counting_bound"
    steps = collections.defaultdict(list)
    for x in r.net.log_records:
        if x["event"] == "push_deepen":
            steps[x["nid"]].append(x["ttl"])
    # F11b: the origin of the relayed invitation deepens a second time
    assert steps and all(v in ([6, 10], [6, 10, 6, 10]) for v in steps.values())
    assert all(r.nodes[i].unresolved for i in steps)


def test_F17b_the_push_depth_stops_at_D_max_below_the_node_bound(monkeypatch):
    """The same run with the default parameters: the doubling stops at
    D_max = 8 although the node bound is 10 (F17b)."""
    e, w, _ = worked()
    assert bbcvc.BbcvcParams().push_depth_max == 8
    # Amendment 13, G4: a wave whose frames are all dropped is owed for ever,
    # so the wave is switched off at its start instead of by dropping CERTs.
    monkeypatch.setattr(bbcvc.BbcvcNode, "_cert_start", lambda self, now: None)
    r = bbcvc.run_bbcvc(e, w, 1, max_ms=2_000_000)
    steps = collections.defaultdict(list)
    for x in r.net.log_records:
        if x["event"] == "push_deepen":
            steps[x["nid"]].append(x["ttl"])
    assert steps and all(v in ([6, 8], [6, 8, 6, 8]) for v in steps.values())
    assert r.verdict == "unresolved" and all(r.nodes[i].unresolved for i in steps)


def test_F17b_bounds_the_repair_where_the_certificate_is_silent():
    """The M9 generator with development seed 1, n = 25, k = 6: infeasible by
    the flow check while the counting bound and the degree-gap witness are
    silent, so F17a's wave completes without a verdict. Before F17b the
    overloaded nodes doubled their push up to n; now no push goes past 8 and
    the run still ends unresolved with no certificate."""
    from ccvc.bb import heldout, sweep

    assert 1 not in heldout.PREREGISTERED
    wts, edges, _ = heldout.generate_one("M9", 25, 6, 1)
    w, e, _ = sweep.prepare(wts, edges)
    r = bbcvc.run_bbcvc(e, w, 6, max_ms=7_000_000, watch_ms=0)
    ttl = [x["ttl"] for x in r.net.log_records if x["event"] == "push_deepen"]
    assert ttl and max(ttl) == 8
    assert r.verdict == "unresolved" and r.converged
    assert r.infeasible_in_network is not True
    assert not any(n.infeasible for n in r.nodes.values())


def removed(victim, slot, horizon=400):
    """Worked example, sync, lossless. `victim` is switched off at `slot` (it
    stops ticking and every frame to or from it is lost), and the slot loop
    runs to a fixed horizon instead of stopping at the first all-done moment,
    so a detection that comes later is seen. Returns whether the survivors end
    DONE, valid on the surviving graph (per component: removing a cut vertex
    splits it) with no edge claimed twice, and silent for the last 100 slots."""
    from ccvc.bb import sched, simnet

    e, w, k = worked()
    ids = sorted(w)

    def drop(t, s, d, m):
        return victim in (s, d) and t >= slot * TAU

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
    nodes = bbcvc.build_nodes(net, w, k, bbcvc.BbcvcParams())
    sc = sched.SyncScheduler(net, nodes, tau_ms=TAU, weights=w)
    surv = [i for i in ids if i != victim]
    sent = []
    for s in range(horizon):
        net.set_now(s * TAU)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            if nid != victim or s < slot:
                net.set_now(s * TAU)
                nodes[nid].on_timer("tick")
        sent.append(sum(c.tx for c in net.counters.values()))
    claims = collections.defaultdict(list)
    for i in surv:
        for x in nodes[i].owned:
            claims[x].append(i)
    g = validate.make_graph(
        [x for x in e if victim not in x], k, {i: w[i] for i in surv}, nodes=surv
    )
    rep = validate.validate(
        g,
        sorted(i for i in surv if nodes[i].role.in_cover),
        {x: v[0] for x, v in claims.items()},
        connectivity=validate.PER_COMPONENT,
    )
    restarts = [x for x in net.log_records if x["event"] == "epoch_bump"]
    return dict(
        done=all(nodes[i].done for i in surv),
        valid=rep.valid and all(len(v) == 1 for v in claims.values()),
        silent=sent[-1] == sent[-101],
        restarted=bool(restarts),
    )


@pytest.mark.parametrize(
    "victim,slot",
    [
        # node 4 is a cut vertex: before F13 the survivors never finished
        (4, 46),
        (4, 50),
        # removed while a neighbour is QUIET and another DONE with an open
        # barrier: before, the survivors beaconed for ever around a node
        # they still counted on, and claimed its edges (bad_owner)
        (2, 50),
        (6, 50),
        (8, 44),
    ],
)
def test_F13_a_removed_node_is_detected_while_a_neighbour_still_transmits(victim, slot):
    """While a neighbour is QUIET, or DONE with an open barrier, every live
    node is heard within a window, so the silent one expires, the epoch
    restarts and the survivors end valid on the surviving graph and silent.
    Scope: only once every node is DONE with a closed barrier, or its
    neighbours close before one window has passed, is nothing transmitted
    that could reveal the departure."""
    res = removed(victim, slot)
    assert res["restarted"], "the departure restarts the epoch"
    assert res["done"] and res["valid"] and res["silent"], res


# --------------------------------------------------------------------------
# F11b: invitation relayed through the cover (Amendment 8)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("scheduler", ["sync"])
def test_F11b_a_relayed_invitation_resolves_the_documented_obstruction(scheduler):
    """figures.udg_instance(100, 0.15, 4) at k = 4 is feasible, but the cover
    of 89 nodes cannot hold its edges and the one outside node that fixes it
    is out of reach of local escalation (bbcvc.py's header). Before F11b the
    run ended `unresolved` after deepening to n. Now the overloaded node
    relays an invitation through the cover, a node with an outside neighbour
    invites it, and the run ends solved and valid with |C| = 90.
    Amendment 17: the obstruction formed after nine late acknowledgements of
    F10 (`late_ack_release`); with R2 they do not exist, the obstruction does
    not form and the run ends solved and valid with |C| = 90 without the relay.
    The relay itself is tested on the worked example below."""
    from ccvc.bb import figures

    e, w, _ = figures.udg_instance(100, 0.15, 4)
    r = bbcvc.run_bbcvc(e, w, 4, scheduler=scheduler, max_ms=2_000_000)
    assert r.verdict == "solved" and len(r.cover) == 90
    assert validate.validate(validate.make_graph(e, 4, w), r.cover, r.owner).valid
    ev = collections.Counter(x["event"] for x in r.net.log_records)
    assert ev["late_ack_release"] == 0
    assert not any(n._pending or n._far_job for n in r.nodes.values())


def test_F11b_each_node_serves_one_search_per_epoch():
    """The relayed search is bounded: a node that has served one answers a
    second with a refusal, and an epoch restart clears the mark. F17's wave
    is silenced, as in the F11 test above."""
    e, w, _ = worked()
    r = bbcvc.run_bbcvc(e, w, 1, max_ms=2_000_000, drop=NO_WAVE)
    relays = collections.Counter(
        x["nid"] for x in r.net.log_records if x["event"] in ("far_relay", "far_start")
    )
    assert relays and max(relays.values()) == 1
    node = r.nodes[5]
    node._init_algo_state()
    assert node._far_served is False and node._far_job is None


# --------------------------------------------------------------------------
# F12b: in-network certificate on the spanning-tree arm (Amendment 8)
# --------------------------------------------------------------------------
def ghs_run(e, w, k, scheduler):
    from ccvc.bb import sweep as S

    spec = {s.name: s for s in S.discover()}["GHS-MST-Backbone"]
    return spec.run(
        S.RunRequest(
            edges=tuple(e),
            weights=dict(w),
            k=k,
            scheduler=scheduler,
            seed=1,
            max_ms=4_500_000,
            loss=0.0,
            mis_nbrs_max=64,
        )
    )


@pytest.mark.parametrize("scheduler", ["sync", "async"])
@pytest.mark.parametrize(
    "case,sums,reason",
    [
        ("worked_k1", (10, 30, 10), "counting_bound"),
        ("n50_m300_s6", (None, 600, 50), "degree_deficiency"),
    ],
)
def test_F12b_the_spanning_tree_arm_certifies_infeasibility_in_network(
    scheduler, case, sums, reason
):
    """Before F12b no node of any arm ever set `infeasible`. Now the final
    GHS REPORT wave carries the three sums, both core nodes decide, and HELLO's
    flag reaches every node; the verdict equals the run-level check, which on
    n50_m300_s6 is the degree-gap witness (the counting bound is silent)."""
    if case == "worked_k1":
        e, w, _ = worked()
        k = 1
    else:
        e, w = dev(case)
        k = 6
    r = ghs_run(e, w, k, scheduler)
    certs = [x for x in r.net.log_records if x["event"] == "ghs_certificate"]
    assert certs and all(x["infeasible"] for x in certs)
    for x in certs:
        got = (x["cap_sum"], x["deg_sum"], x["nodes"])
        assert all(a is None or a == b for a, b in zip(sums, got))
    assert r.infeasible_in_network is True and r.infeasible_reason == reason
    assert all(n.infeasible for n in r.nodes.values())
    assert r.verdict == "unresolved"


def test_F12b_feasible_runs_and_other_arms(monkeypatch):
    """A feasible instance is never certified, and the arms without the GHS
    tree keep the run-level check only when F17's wave is silenced."""
    e, w, k = worked()
    r = ghs_run(e, w, k, "sync")
    # Amendment 13, G5: the tree sums only start a wave; a feasible instance
    # starts none, so no node computes a verdict.
    assert r.infeasible_in_network is None
    assert not any(n.infeasible for n in r.nodes.values())
    # Amendment 13, G4: a wave whose frames are all dropped is owed for ever,
    # so the wave is switched off at its start instead of by dropping CERTs.
    monkeypatch.setattr(bbcvc.BbcvcNode, "_cert_start", lambda self, now: None)
    m = bbcvc.run_bbcvc(e, w, 1, max_ms=2_000_000)
    assert m.infeasible_in_network is None and m.infeasible_reason == "counting_bound"
    assert not any(n.infeasible for n in m.nodes.values())


def test_F12b_wire_costs():
    """GHS_REPORT grows by 10 B to carry the sums; HELLO keeps its 13 B with
    the flag in bit 6 of the role byte."""
    from ccvc.bb import wire
    from ccvc.bb.api import Role

    rep = wire.Ghs(MsgType.GHS_REPORT, 3, 9, 2, 7, 11, cert=(120, 320, 20))
    assert len(wire.encode(rep)) == 25 and wire.decode(wire.encode(rep)) == rep
    for flag in (False, True):
        h = wire.Hello(
            src=7,
            key=100,
            deg=3,
            role=Role.CONNECTOR,
            phase=7,
            load=1,
            barrier_open=True,
            infeasible=flag,
        )
        b = wire.encode(h)
        assert len(b) == 13 and wire.decode(b) == h


# --------------------------------------------------------------------------
# F17: lazy certificate wave before the futile repairs (proposal)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("scheduler", ["sync", "async"])
@pytest.mark.parametrize(
    "case,sums", [("worked_k1", (10, 30)), ("n50_m400_s1", (300, 800))]
)
def test_F17_the_wave_certifies_and_stops_the_futile_repairs(scheduler, case, sums):
    """Infeasible by the counting bound. Before F17 the MIS-connector arm
    certified nothing and every overloaded node deepened to n (n50_m400_s1:
    8435 slots, 563 045 frames, against 2460 slots without F11). Now the first
    node that uses up its rounds starts one echo wave, its initiator decides,
    every node holds the flag and the run ends unresolved far sooner."""
    if case == "worked_k1":
        e, w, _ = worked()
        k = 1
    else:
        e, w = dev(case)
        k = 6
    r = bbcvc.run_bbcvc(
        e,
        w,
        k,
        scheduler=scheduler,
        params=bbcvc.BbcvcParams(mis_nbrs_max=64),
        max_ms=7_000_000,
        seed=1,
        watch_ms=0,
    )
    done = [x for x in r.net.log_records if x["event"] == "cert_wave_done"]
    assert [(x["cap_sum"], x["deg_sum"], x["infeasible"]) for x in done] == [
        sums + (True,)
    ]
    assert r.infeasible_in_network is True and r.verdict == "unresolved"
    assert all(n.infeasible for n in r.nodes.values())
    m = len(e)
    # One CERT each way per edge, less the n - 1 tree edges, plus the repeats
    # of nodes that wait for a deep subtree: at most 3m here.
    cert = r.by_type_tx[int(MsgType.CERT)] + r.by_type_tx[int(MsgType.CERT_ACK)]
    assert 2 * m <= cert <= 3 * m
    if case == "n50_m400_s1":
        assert r.slots is None or r.slots < 2460


def test_F17_no_wave_where_no_node_uses_up_its_rounds():
    """The lossless worked example never starts a wave: identical run."""
    e, w, k = worked()
    r = bbcvc.run_bbcvc(e, w, k, max_ms=600_000)
    # Amendment 13: every DONE node asks its frozen neighbours to confirm it
    # (G2c), and a node is done only when closed (G4). On the worked example
    # that is 6 HELLOs (closed nodes echoing) and 20 rx more, slots unchanged; the
    # cover, weight and every algorithm unicast are unchanged.
    assert (r.slots, r.tx, r.rx, r.bytes_tx) == (54, 528, 1417, 7121)
    assert r.infeasible_in_network is None
    assert not any(x["event"] == "cert_wave_start" for x in r.net.log_records)


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_F17_lost_wave_frames_are_repeated_until_answered(scheduler):
    """ProAsk: the first two CERT_ACKs to node 4 are lost. Node 4 repeats its
    CERT, the child answers again, and the wave still certifies every node."""
    e, w, _ = worked()
    ack, lost = int(MsgType.CERT_ACK), []

    def drop(t, s, d, m):
        if m == ack and d == 4 and len(lost) < 2:
            lost.append(t)
            return True
        return False

    r = bbcvc.run_bbcvc(e, w, 1, scheduler=scheduler, max_ms=2_000_000, drop=drop)
    assert len(lost) == 2
    done = [x for x in r.net.log_records if x["event"] == "cert_wave_done"]
    assert [(x["cap_sum"], x["deg_sum"], x["infeasible"]) for x in done] == [
        (10, 30, True)
    ]
    assert all(n.infeasible for n in r.nodes.values())
    assert r.verdict == "unresolved" and r.converged


def test_F17_a_lost_frame_silences_the_wave_but_never_misleads_it():
    """Every CERT_ACK on one link is lost: the wave never completes, nothing
    is certified, and the run still ends (unresolved) as without F17."""
    e, w, _ = worked()
    ack = int(MsgType.CERT_ACK)
    r = bbcvc.run_bbcvc(
        e, w, 1, max_ms=2_000_000, drop=lambda t, s, d, m: m == ack and d == 4
    )
    assert not any(x["event"] == "cert_wave_done" for x in r.net.log_records)
    assert not any(n.infeasible for n in r.nodes.values())
    # Amendment 13, G4: the wave is owed while it runs, so with every CERT_ACK
    # of one link lost (outside the window assumption) the run does not claim
    # silence; before G4 it reported convergence while CERTs were still sent.
    assert not r.converged and r.verdict == "truncated"
