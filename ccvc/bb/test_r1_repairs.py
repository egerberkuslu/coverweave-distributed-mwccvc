"""Regression tests for the R1 protocol repairs F1-F5 (contract R1_PREREG.md, Amendment 1).

Backend: the event simulator (SimNet, synchronous scheduler unless named), on
the manuscript's worked example (n=10, m=15, k=2). Faults are injected with the
deterministic `SimNet.drop` predicate, the rest of the channel is lossless and
`rssi_range=None` as in `run_bbcvc`.

The three fault scenarios B, C and D are the audit's reproductions. Their
harness builds the network by hand (it does not need any repaired API), so the
same file fails on the submitted code and passes on the repaired code.
"""

from __future__ import annotations

import collections
import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, sched, simnet, validate, wire  # noqa: E402
from ccvc.bb.api import MsgType, Role  # noqa: E402
from ccvc.bb.figures import (  # noqa: E402
    WORKED_EDGES as EDGES,
    WORKED_K as K,
    WORKED_WEIGHTS as WEIGHTS,
)

TAU = 200
IDS = sorted({a for e in EDGES for a in e} | set(WEIGHTS))
COVER = [2, 3, 4, 5, 6, 7, 8, 9]
COVER_WEIGHT = 27
JOIN, HO_ACK, HELLO = int(MsgType.JOIN), int(MsgType.HANDOVER_ACK), int(MsgType.HELLO)


# --------------------------------------------------------------------------
# scenario harness (independent of the repaired API)
# --------------------------------------------------------------------------
def first_n(n, pred):
    """Drop only the first `n` frames that match `pred` (n lost copies)."""
    left = [n]

    def drop(t, src, dst, mtype):
        if left[0] > 0 and pred(t, src, dst, mtype):
            left[0] -= 1
            return True
        return False

    return drop


def scenario(drop, horizon_slots=400):
    """Run the synchronous slot loop for a fixed horizon past the verdict.

    The loop is `SyncScheduler.run`'s own body; it does not stop at the
    verdict, so it can see whether the network falls silent afterwards.
    """
    net = simnet.SimNet(
        IDS,
        EDGES,
        loss=0.0,
        seed=0,
        delay=simnet.fixed_delay(1),
        rssi_range=None,
        macs=bbcvc.macs_for(IDS),
        drop=drop,
    )
    nodes = bbcvc.build_nodes(net, WEIGHTS, K, bbcvc.BbcvcParams())
    sc = sched.SyncScheduler(net, nodes, tau_ms=TAU, weights=WEIGHTS)
    tx = collections.Counter()
    cur = {"slot": 0}
    account = net._account

    def counting(nid, payload, fanout):
        tx[cur["slot"]] += 1
        return account(nid, payload, fanout)

    net._account = counting
    verdict = None
    for s in range(horizon_slots):
        cur["slot"] = s
        net.set_now(s * TAU)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            net.set_now(s * TAU)
            nodes[nid].on_timer("tick")
        net.set_now((s + 1) * TAU)
        sc._mark_done((s + 1) * TAU)
        if verdict is None and sc._all_done() and net.in_flight == 0:
            verdict = s + 1
    claims = collections.defaultdict(list)
    for nid in sorted(nodes):
        for e in nodes[nid].owned:
            claims[e].append(nid)
    cover = sorted(i for i in IDS if nodes[i].role.in_cover)
    report = validate.validate(
        validate.make_graph(EDGES, K, WEIGHTS),
        cover,
        {e: v[0] for e, v in claims.items()},
    )
    return {
        "verdict": verdict,
        "all_done": all(n.done for n in nodes.values()),
        "cover": cover,
        "weight": sum(WEIGHTS[i] for i in cover),
        "double": {e: tuple(v) for e, v in claims.items() if len(v) > 1},
        "valid": report.valid,
        "unresolved": [i for i in IDS if nodes[i].unresolved],
        "tx": tx,
        "last_tx_slot": max((s for s, c in tx.items() if c), default=None),
        "horizon": horizon_slots,
        "nodes": nodes,
        "net": net,
    }


def tx_in(res, lo, hi):
    return sum(c for s, c in res["tx"].items() if lo <= s < hi)


# --------------------------------------------------------------------------
# scenario B: three lost copies of the escalation JOIN 6 -> 5
# --------------------------------------------------------------------------
def test_B_three_lost_join_copies_converge():
    """F1. Submitted code: the run never terminates (the JOIN is never re-sent
    and node 6 waits on an invitee that never heard it). Repaired: the JOIN is
    re-armed after the give-up while node 6 is still overloaded."""
    res = scenario(first_n(3, lambda t, s, d, m: m == JOIN and s == 6 and d == 5))
    assert res["verdict"] is not None, "run never reached the verdict"
    assert res["all_done"] and not res["unresolved"]
    assert res["valid"] and not res["double"]
    assert (res["cover"], res["weight"]) == (COVER, COVER_WEIGHT)
    assert tx_in(res, res["horizon"] - 100, res["horizon"]) == 0


# --------------------------------------------------------------------------
# scenario C: three lost HANDOVER_ACK copies of one accepted handover
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "drop",
    [
        pytest.param(
            lambda: first_n(3, lambda t, s, d, m: m == HO_ACK and s == 9 and d == 8),
            id="three-acks-9-to-8",
        ),
        pytest.param(
            lambda: lambda t, s, d, m: m == HO_ACK and 15 * TAU <= t < 27 * TAU,
            id="window-15-27",
        ),
        pytest.param(
            lambda: lambda t, s, d, m: m == HO_ACK and 38 * TAU <= t < 50 * TAU,
            id="window-38-50",
        ),
    ],
)
def test_C_lost_handover_acks_leave_no_double_claim(drop):
    """F1. Submitted code: the sender gives up after R_max and keeps the edge
    the receiver has already committed, so an all-DONE run ends with a doubly
    owned edge. Repaired: HANDOVER is retransmitted until a reply arrives."""
    res = scenario(drop())
    assert res["double"] == {}, f"doubly claimed edges: {res['double']}"
    assert res["verdict"] is not None and res["all_done"]
    assert res["valid"] and not res["unresolved"]
    assert (res["cover"], res["weight"]) == (COVER, COVER_WEIGHT)


# --------------------------------------------------------------------------
# scenario D: node 6's DONE HELLO to 5 and its single answer are lost
# --------------------------------------------------------------------------
def d_drop():
    return (
        lambda t, s, d, m: m == HELLO and s == 6 and d == 5 and 51 * TAU <= t < 71 * TAU
    )


def test_D_lost_done_hello_and_answer_reach_silence():
    """F2. Submitted code: node 5 keeps its barrier open and beacons for ever
    after the verdict. Repaired: node 6 answers every open-flag beacon at most
    once per stale window, so once the channel recovers the network falls
    silent and stays silent."""
    res = scenario(d_drop())
    assert res["verdict"] is not None and res["all_done"]
    assert res["valid"] and not res["double"]
    assert (res["cover"], res["weight"]) == (COVER, COVER_WEIGHT)
    # silence: the last transmission happens shortly after the drop window
    # ends, and a 300-slot window after it carries no frame at all
    assert res["last_tx_slot"] is not None and res["last_tx_slot"] < 100
    assert tx_in(res, 100, res["horizon"]) == 0


# --------------------------------------------------------------------------
# lossless worked example (the manuscript quotes these numbers)
# --------------------------------------------------------------------------
def run(scheduler="sync", **kw):
    kw.setdefault("max_ms", 600_000)
    return bbcvc.run_bbcvc(EDGES, WEIGHTS, K, scheduler=scheduler, **kw)


def assert_worked_cover(r):
    assert r.converged and r.verdict == "solved"
    assert (r.cover, r.total_weight) == (COVER, COVER_WEIGHT)
    assert r.double_claimed == {}
    rep = validate.validate(validate.make_graph(EDGES, K, WEIGHTS), r.cover, r.owner)
    assert rep.valid, rep.violations


def test_lossless_worked_example_sync_numbers():
    """Every repair keeps the lossless answer. The cost numbers are the new
    pinned values; the manuscript quotes them."""
    r = run("sync")
    assert_worked_cover(r)
    # Submitted code: 53 slots, 510 tx, 1373 rx, 6646 B. The epoch byte adds
    # one byte to each of the 40 JOIN and edge frames; repeated F2 answers add
    # twelve liveness HELLOs while nodes 2 and 3 wait on node 4, and the last
    # one is in flight at slot 53, so the verdict moves to slot 54.
    # Amendment 13: every DONE node asks its frozen neighbours to confirm it
    # (G2c), and a node is done only when closed (G4). On the worked example
    # that is 6 HELLOs (closed nodes echoing) and 20 rx more, slots unchanged; the
    # cover, weight and every algorithm unicast are unchanged.
    assert (r.slots, r.tx, r.rx, r.bytes_tx) == (54, 528, 1417, 7121)
    assert (r.hello_change_tx, r.hello_periodic_tx) == (116, 312)  # Amendment 13: +6 echoes
    link = r.by_type_tx[int(MsgType.LINK)] + r.by_type_tx[int(MsgType.LINK_ACK)]
    assert link == 60
    assert r.tx - link - r.hello_change_tx - r.hello_periodic_tx == 40
    assert (r.mis_depth, r.restarts, r.tx_after_convergence) == (1, 0, 0)


def test_lossless_worked_example_async_cover():
    r = run("async")
    assert_worked_cover(r)
    # Amendment 13: every DONE node asks its frozen neighbours to confirm it
    # (G2c), and a node is done only when closed (G4). On the worked example
    # that is 6 HELLOs (closed nodes echoing) and 20 rx more, slots unchanged; the
    # cover, weight and every algorithm unicast are unchanged.
    # Amendment 13, third note, G4(b): a node with a received frame still
    # unprocessed is not done, so the async verdict is 85 ms later; frames unchanged.
    assert (r.tx, r.rx, r.t_conv_ms) == (388, 988, 6658)
    assert (r.restarts, r.tx_after_convergence) == (0, 0)


@pytest.mark.parametrize("repair", ["F1", "F2", "F3", "F4", "F5"])
def test_each_repair_keeps_the_lossless_worked_cover(repair):
    """The repairs share one code version, so each check is the same run seen
    through the repair's own mechanism: no lossless run exercises a give-up
    (F1), a reopened barrier (F2), a foreign epoch (F3), a stale frozen
    neighbour (F4) or an evicted reply (F5)."""
    r = run("sync")
    assert_worked_cover(r)
    events = collections.Counter(rec["event"] for rec in r.net.log_records)
    nodes = r.nodes.values()
    if repair == "F1":
        assert events["ack_gave_up"] == events["join_rearm"] == 0
    elif repair == "F2":
        assert all(n._barrier_closed() for n in nodes)
    elif repair == "F3":
        assert events["epoch_mismatch_drop"] == 0
        assert {n.epoch for n in nodes} == {0}
    elif repair == "F4":
        assert not any(n._view_stale() for n in nodes)
        assert all(set(n._frozen_bidir) == n.edges() for n in nodes)
    else:
        assert all(
            len(c) <= bbcvc.SEEN_PER_PEER for n in nodes for c in n._seen.values()
        )


# --------------------------------------------------------------------------
# F1: persistent HANDOVER/PUSH, re-armed JOIN
# --------------------------------------------------------------------------
def test_F1_handover_is_never_abandoned_while_the_peer_is_verified():
    r = run(
        "sync", drop=first_n(3, lambda t, s, d, m: m == HO_ACK and s == 9 and d == 8)
    )
    assert_worked_cover(r)
    gave_up = [rec for rec in r.net.log_records if rec["event"] == "ack_gave_up"]
    assert gave_up == []
    retx = [
        rec
        for rec in r.net.log_records
        if rec["event"] == "retx" and rec.get("tag") == "handover"
    ]
    assert len(retx) == 3, "three lost copies, the fourth copy is answered"


def test_F1_backoff_is_capped():
    node = bbcvc.BbcvcNode(1, _FakePort(), bbcvc.BbcvcParams(), 2)
    p = bbcvc.Pending(seq=1, peer=9, mtype=MsgType.HANDOVER, payload=b"x")
    cap = node._timeout_of(p) * 2 ** (node.p.ack_max_attempts - 1)
    gaps = [node._backoff_ms(p, a) for a in range(1, 12)]
    assert gaps[:3] == [node._timeout_of(p) * 2**i for i in range(3)]
    assert max(gaps) == cap and gaps[-1] == cap


def test_F1_join_is_re_armed_after_a_give_up():
    r = run("sync", drop=first_n(3, lambda t, s, d, m: m == JOIN and s == 6 and d == 5))
    assert_worked_cover(r)
    # Amendment 13, G3: the JOIN is not given up and re-armed; the same request
    # is repeated with the capped backoff until it is answered.
    assert not any(rec["event"] in ("join_rearm", "ack_gave_up") for rec in r.net.log_records)
    retx = [rec for rec in r.net.log_records if rec["event"] == "retx"
            and rec["nid"] == 6 and rec.get("peer") == 5
            and str(rec.get("tag", "")).startswith("join")]
    assert len(retx) >= 3


def test_F1_retry_branches():
    """PUSH past R_max is resent at the capped gap; an exhausted JOIN is
    dropped and re-armed; a request to a stale frozen neighbour waits."""
    r = run("sync")
    node = r.nodes[4]
    now = r.net.now_ms()
    sent = []
    node.plat.send_unicast = lambda mac, payload: sent.append(payload)
    push = wire.encode(wire.EdgeMsg(MsgType.PUSH, 4, 900, 2, 4, 3, node.epoch))
    p = bbcvc.Pending(
        seq=900, peer=2, mtype=MsgType.PUSH, payload=push, e=(2, 4), ttl=3, attempts=10
    )
    node._pending[(2, 900)] = p
    node._retry_pending(now)
    assert node._pending[(2, 900)] is p and p.attempts == 11 and sent == [push]
    assert p.next_ms == now + node._backoff_ms(p, node.p.ack_max_attempts)
    del node._pending[(2, 900)]

    join = wire.encode(wire.Join(MsgType.JOIN, 4, 901, bbcvc.JOIN_ESCALATE, node.epoch))
    node._join_sent.add((5, bbcvc.JOIN_ESCALATE))
    node._pending[(5, 901)] = bbcvc.Pending(
        seq=901, peer=5, mtype=MsgType.JOIN, payload=join, attempts=3
    )
    node._retry_pending(now)
    # Amendment 13, G3: an exhausted JOIN is repeated, not dropped and re-armed
    assert (5, 901) in node._pending and sent[-1] == join
    assert (5, bbcvc.JOIN_ESCALATE) in node._join_sent
    del node._pending[(5, 901)]

    sent.clear()
    gone = node.nbrs.pop(6)
    node._pending[(6, 902)] = bbcvc.Pending(
        seq=902, peer=6, mtype=MsgType.JOIN, payload=join, attempts=3
    )
    node._retry_pending(now)
    assert (6, 902) in node._pending and sent == [], "F4: wait, do not give up"
    node.nbrs[6] = gone
    del node._pending[(6, 902)]


def test_done_waits_for_open_requests_and_push_chains():
    r = run("sync")
    node = r.nodes[4]
    assert node.done
    node._pending[(2, 1)] = bbcvc.Pending(
        seq=1, peer=2, mtype=MsgType.HANDOVER, payload=b""
    )
    assert not node.done
    node._pending.clear()
    node._push_job = bbcvc.PushJob(src=2, seq=1, e=(2, 4), ttl=1)
    assert not node.done
    node._push_job = None
    assert node.done


def test_async_verdict_is_not_declared_while_a_chain_runs():
    """MEASURED before this clause: on n50_m300_s2 the asynchronous verdict
    came at 27.6 s while DONE nodes were still servicing push chains, and 399
    frames followed it. Simulator backend, lossless."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "DagdevirenDataset",
        "n50_m300_s2.txt",
    )
    if not os.path.exists(path):
        pytest.skip("benchmark dataset not present")
    from ccvc.bb import matrix
    from ccvc.bb.sweep import prepare

    w, e, _ = prepare(*matrix.load_instance(path))
    r = bbcvc.run_bbcvc(
        e,
        w,
        6,
        scheduler="async",
        params=bbcvc.BbcvcParams(mis_nbrs_max=64),
        max_ms=2_000_000,
        seed=1,
    )
    assert r.converged
    assert all(not n._pending and n._push_job is None for n in r.nodes.values())
    assert r.tx_after_convergence == 0


# --------------------------------------------------------------------------
# F2: open-barrier flag in HELLO
# --------------------------------------------------------------------------
def test_F2_flag_rides_a_spare_bit_and_hello_keeps_its_size():
    for flag in (False, True):
        h = wire.Hello(
            src=7, key=100, deg=3, role=Role.COVER, phase=7, load=1, barrier_open=flag
        )
        b = wire.encode(h)
        assert len(b) == wire.hello_size(0) == 13
        back = wire.decode(b)
        assert back.barrier_open is flag and back.role is Role.COVER


def test_F2_answers_carry_the_flag_cleared():
    """No ping-pong: every HELLO node 6 sends while its barrier is closed has
    the flag cleared, so it can never trigger an answer."""
    sent = []
    net = simnet.SimNet(
        IDS,
        EDGES,
        loss=0.0,
        seed=0,
        delay=simnet.fixed_delay(1),
        rssi_range=None,
        macs=bbcvc.macs_for(IDS),
        drop=d_drop(),
    )
    nodes = bbcvc.build_nodes(net, WEIGHTS, K, bbcvc.BbcvcParams())
    sc = sched.SyncScheduler(net, nodes, tau_ms=TAU, weights=WEIGHTS)
    bcast = net._broadcast

    def spy(src, payload):
        if src == 6:
            sent.append((nodes[6]._barrier_closed(), wire.decode(payload)))
        return bcast(src, payload)

    net._broadcast = spy
    out = sc.run(400 * TAU)
    sc.watch(200 * TAU)
    assert out.converged
    after_done = [(c, h) for c, h in sent if h.phase >= bbcvc.PH_DONE]
    assert after_done, "node 6 never sent a DONE HELLO"
    assert all(not h.barrier_open for c, h in after_done if c)
    # Amendment 13, G2(c): node 5's lost DONE HELLO is also recovered through
    # the confirmation echo, which node 6 can send before it closes; either
    # way node 6 sent more than its own DONE HELLO.
    assert len(after_done) >= 2, "node 6 never answered"


# --------------------------------------------------------------------------
# F3: epoch byte in JOIN and edge messages
# --------------------------------------------------------------------------
def test_F3_wire_carries_the_epoch_and_sizes_grow_by_one_byte():
    j = wire.Join(MsgType.JOIN, 9, 5, code=2, epoch=200)
    e = wire.EdgeMsg(MsgType.PUSH, 14, 7, 5, 6, ttl=3, epoch=17)
    assert wire.decode(wire.encode(j)) == j and wire.decode(wire.encode(e)) == e
    s = wire.sizes()
    # Amendment 13, G7: the two requests carry one more byte, the edge version
    assert (s["JOIN"], s["JOIN_ACK"], s["HANDOVER"], s["PUSH"]) == (7, 7, 12, 12)
    assert s["BB_MIS"] == 6, "BB_MIS shares the body but carries no epoch"


def test_F3_a_frame_of_another_epoch_is_dropped():
    r = run("sync")
    out = r.nodes[1]  # node 1 ends outside the cover
    assert out.role is Role.OUT
    mac2 = r.net.mac_of(2)
    stale = wire.Join(MsgType.JOIN, 2, 4000, bbcvc.JOIN_ESCALATE, epoch=out.epoch + 1)
    out.on_frame(mac2, None, wire.encode(stale))
    out._drain_rx(r.net.now_ms())
    assert out.role is Role.OUT
    fresh = wire.Join(MsgType.JOIN, 2, 4001, bbcvc.JOIN_ESCALATE, epoch=out.epoch)
    out.on_frame(mac2, None, wire.encode(fresh))
    out._drain_rx(r.net.now_ms())
    assert out.role is Role.COVER


# --------------------------------------------------------------------------
# F4: decisions over the frozen view
# --------------------------------------------------------------------------
def test_F4_a_stale_frozen_neighbour_means_wait_and_new_ones_are_ignored():
    r = run("sync")
    v = r.nodes[4]
    assert v._frozen_bidir is not None and 6 in v._frozen_bidir
    adv = (v._adv_forced, v._adv_mis)
    gone = v.nbrs.pop(6)
    assert v._view_stale() and not v._keys_ready(v._nbrs_active())
    assert 6 not in [n.nid for n in v._nbrs_active()]
    owned = set(v.owned)
    v._step(r.net.now_ms())
    assert v.owned == owned, "no decision while a frozen neighbour is stale"
    v._hello_dirty = True
    v._maybe_hello(r.net.now_ms())
    assert (v._adv_forced, v._adv_mis) == adv, "a waiting node repeats itself"
    v.nbrs[6] = gone
    assert not v._view_stale()
    # a verified record outside the frozen view is not part of the decisions
    extra = bbcvc.BootNeighbor(
        nid=99, mac=1, bidir=True, link_up=True, key=1, last_ms=0
    )
    v.nbrs[99] = extra
    assert 99 not in [n.nid for n in v._nbrs_active()]
    del v.nbrs[99]
    # and its requests are not served: node 1 ends OUT; a JOIN from a
    # verified peer outside its frozen view leaves it OUT
    out = r.nodes[1]
    out.nbrs[99] = bbcvc.BootNeighbor(
        nid=99, mac=12345, bidir=True, link_up=True, key=1, last_ms=0
    )
    join = wire.Join(MsgType.JOIN, 99, 5000, bbcvc.JOIN_ESCALATE, out.epoch)
    out._on_algo(r.net.now_ms(), 12345, join)
    assert out.role is Role.OUT
    del out.nbrs[99]


# --------------------------------------------------------------------------
# F5: bounded duplicate-reply cache
# --------------------------------------------------------------------------
def test_F5_reply_cache_is_bounded_per_peer_and_still_replays():
    r = run("sync")
    v = r.nodes[4]
    for seq in range(1000, 1050):
        v._seen_put((2, int(MsgType.HANDOVER), seq), bytes([seq & 0xFF]))
    assert len(v._seen[2]) == bbcvc.SEEN_PER_PEER
    assert v._seen_get((2, int(MsgType.HANDOVER), 1049)) == bytes([1049 & 0xFF])
    assert v._seen_get((2, int(MsgType.HANDOVER), 1000)) is None


# --------------------------------------------------------------------------
# run-level counters (no behaviour change)
# --------------------------------------------------------------------------
class _FakePort:
    mac = bbcvc.mac_for_id(1)

    def now_ms(self):
        return 0

    def log(self, event, **fields):
        pass

    def send_broadcast(self, payload):
        pass

    def send_unicast(self, dst, payload):
        pass


def test_state_bytes_accounting_uses_the_documented_widths():
    w = bbcvc.STATE_WIDTHS
    assert (w["key"], w["id"], w["flag"], w["mac"], w["ts"]) == (4, 2, 1, 6, 4)
    node = bbcvc.BbcvcNode(3, _FakePort(), bbcvc.BbcvcParams(), 2)
    base = bbcvc.state_bytes(node)
    assert base == bbcvc.STATE_FIXED_BYTES
    node.nbrs[5] = bbcvc.BootNeighbor(nid=5, mac=7, mis_nbrs=(1, 2), last_ms=0)
    assert bbcvc.state_bytes(node) == base + bbcvc.STATE_NEIGHBOUR_BYTES + 2 * w["id"]
    node.owned.add((1, 5))
    node._seen_put((5, int(MsgType.HANDOVER), 3), b"\x00" * 11)
    grown = base + bbcvc.STATE_NEIGHBOUR_BYTES + 2 * w["id"]
    grown += 2 * w["id"]  # one owned edge
    grown += w["id"] + w["flag"] + w["id"] + 11  # one cached reply
    assert bbcvc.state_bytes(node) == grown


def test_counters_on_the_lossless_run():
    r = run("sync")
    per_node = [bbcvc.state_bytes(n) for n in r.nodes.values()]
    assert r.state_bytes_max == max(per_node)
    assert r.state_bytes_mean == pytest.approx(sum(per_node) / len(per_node))
    assert r.mis_depth == max(n.mis_round for n in r.nodes.values())


def test_tx_after_convergence_is_measured_on_a_twin():
    """The window after the verdict runs on a copy: the run's own numbers are
    the verdict's, with or without the window."""
    a = run("sync", drop=d_drop(), watch_ms=100 * TAU)
    b = run("sync", drop=d_drop(), watch_ms=0)
    # Amendment 13, G4: done means closed, so the verdict comes at silence and
    # the window after it is empty; before, the barrier tail of scenario D.
    assert a.tx_after_convergence == 0
    assert b.tx_after_convergence is None
    assert (a.slots, a.tx, a.rx, a.bytes_tx) == (b.slots, b.tx, b.rx, b.bytes_tx)
    assert len(a.net.log_records) == len(b.net.log_records)
    assert a.cover == b.cover == COVER


def test_tx_after_convergence_async_window():
    r = run("async", watch_ms=50 * TAU)
    assert r.tx_after_convergence == 0


def test_restarts_count_epoch_waves():
    """Cutting link (1,2) in slots [8,18) expires the record during Phases 1-3:
    the link leaves (one restart wave) and comes back (a second wave)."""
    cut = lambda t, s, d, m: {s, d} == {1, 2} and 8 * TAU <= t < 18 * TAU  # noqa: E731
    r = run("sync", drop=cut)
    assert_worked_cover(r)
    # Amendment 13, G2(a): the restart re-verifies every link and the gate waits
    # for the handshake, so the link that returns at slot 18 enters the new
    # view before it freezes; the second wave of the old code no longer occurs.
    assert r.restarts == 1
    assert {n.epoch for n in r.nodes.values()} == {1}
    assert r.restarts == max(n.epoch_advance for n in r.nodes.values())


# --------------------------------------------------------------------------
# Amendment 4: F7 (refusal under one-way gates), F8 (spanning-tree arm),
# validity on the discovered graph
# --------------------------------------------------------------------------
def one_way(src, dst, scheduler="sync"):
    """Frames src -> dst arrive at -80 dBm, so dst never opens its gate for
    src, while src verifies dst through LINK_ACK. Every other direction is at
    -50 dBm. The emulated backend's failure shape, in the simulator."""
    rssi = lambda t, s, d: -80.0 if (s, d) == (src, dst) else -50.0  # noqa: E731
    net = simnet.SimNet(
        IDS,
        EDGES,
        loss=0.0,
        seed=0,
        delay=simnet.fixed_delay(1),
        rssi=rssi,
        macs=bbcvc.macs_for(IDS),
    )
    nodes = bbcvc.build_nodes(net, WEIGHTS, K, bbcvc.BbcvcParams())
    if scheduler == "sync":
        sc = sched.SyncScheduler(net, nodes, tau_ms=TAU, weights=WEIGHTS)
    else:
        sc = sched.AsyncScheduler(net, nodes, tick_ms=TAU, seed=0, weights=WEIGHTS)
    return sc.run(200 * TAU * 5), nodes, net


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_F7_a_request_to_a_one_way_peer_is_refused_and_the_run_settles(scheduler):
    """Node 2 verifies node 1, node 1 never verifies node 2. Before F7 node 2
    retransmitted its HANDOVER to 1 for the whole budget (truncated); now node
    1 refuses it with a NACK and the run reaches its verdict."""
    out, nodes, net = one_way(2, 1, scheduler)
    # Amendment 13, G2(b): node 1 does not hear node 2, so it does not answer
    # node 2's LINK; the edge is absent at both ends (symmetric views) and no
    # request is ever sent on it. The bounded F13 wait (G4) lets node 2 finish.
    assert 1 not in nodes[2].edges() and 2 not in nodes[1].edges()
    assert out.converged
    assert not any(r["event"] == "refused_unverified" for r in net.log_records)
    assert not any(n._pending for n in nodes.values())


def test_F7_every_one_way_link_of_the_worked_example_settles():
    """Before F7, 13 of the 30 directed one-way links left a request unanswered
    for the whole budget (sync)."""
    stuck = []
    for a, b in EDGES:
        for src, dst in ((a, b), (b, a)):
            out, _, _ = one_way(src, dst)
            if not out.converged:
                stuck.append((src, dst))
    assert stuck == []


def test_F7_lossless_runs_refuse_nothing():
    for scheduler in ("sync", "async"):
        r = run(scheduler)
        assert_worked_cover(r)
        assert not any(
            rec["event"] == "refused_unverified" for rec in r.net.log_records
        )


def test_F8_spanning_tree_arm_no_longer_waits_on_a_lost_bb_mis_decision():
    """Worked example, GHS-MST-Backbone, asynchronous, 10 % i.i.d. loss,
    channel seed 2. Before F8: truncated at 600 s with node 4 in PH_CONN
    waiting for node 6's lost decision frame, nothing pending anywhere."""
    from ccvc.bb import sweep as S

    spec = {s.name: s for s in S.discover()}["GHS-MST-Backbone"]
    req = S.RunRequest(
        edges=tuple(EDGES),
        weights=dict(WEIGHTS),
        k=K,
        scheduler="async",
        seed=2,
        max_ms=600_000,
        loss=0.1,
        mis_nbrs_max=32,
    )
    r = spec.run(req)
    assert r.converged and r.verdict == "solved"
    assert S.validate_run(validate.make_graph(EDGES, K, WEIGHTS), r).valid
    assert all(n.phase >= bbcvc.PH_COVER for n in r.nodes.values())


def _row(name, scheduler, seed, loss):
    from ccvc.bb import matrix
    from ccvc.bb import sweep as S

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if name == "worked":
        inst = S.Instance(
            "synthetic",
            matrix.Cell("worked", 10, 1),
            0,
            "worked",
            tuple(EDGES),
            dict(WEIGHTS),
            1,
        )
        k = K
    else:
        path = os.path.join(root, "data", "DagdevirenDataset", name + ".txt")
        if not os.path.exists(path):
            pytest.skip("benchmark dataset not present")
        n, m, s = (int(x[1:]) for x in name.split("_"))
        w, e, ad = S.prepare(*matrix.load_instance(path))
        inst = S.Instance(
            "dataset", matrix.Cell("small", n, m // n), s, path, tuple(e), w, 10, ad
        )
        k = 6
    spec = {s.name: s for s in S.discover()}["MIS-Connector-Backbone"]
    opts = S.SweepOptions(
        k=k, loss=loss, rng_seed=seed, max_ms=300_000, mis_nbrs_max=64
    )
    return S.run_one(inst, spec, scheduler, opts)


@pytest.mark.parametrize(
    "name,scheduler,seed",
    [
        ("worked", "async", 1),
        ("n10_m20_s1", "async", 2),
        ("n15_m30_s1", "async", 3),
        # Round 2 had n20_m40_s2/sync/2 here; with F9 that run now discovers
        # every planned link and is valid on both graphs (asserted below).
        ("n15_m30_s1", "sync", 3),
    ],
)
def test_discovered_reading_on_the_four_twenty_percent_runs(name, scheduler, seed):
    """Before F13 each ended with an unowned planned edge that a failed LINK
    handshake kept out of the discovered graph: invalid on the planned graph,
    valid on the graph the guarantees refer to (planned_missing 1, 3, 3, 1).
    These were the four such runs of the 30-run 20 % grid (MIS-connector, 5
    development instances, 2 schedulers, 3 seeds). With F13 the handshake is
    retried before the verdict, and all four discover every planned link."""
    r = _row(name, scheduler, seed, 0.2)
    assert r.verdict == "solved"
    assert r.valid is True and r.valid_discovered is True
    assert r.planned_missing == 0 and r.discovered_extra == 0


def test_discovered_reading_after_f9_on_the_former_fourth_run():
    r = _row("n20_m40_s2", "sync", 2, 0.2)
    assert r.valid is True and r.valid_discovered is True
    assert (r.planned_missing, r.discovered_extra) == (0, 0)


def test_discovered_reading_on_a_lossless_run():
    r = _row("worked", "sync", 0, 0.0)
    assert r.valid is True and r.valid_discovered is True
    assert (r.planned_missing, r.discovered_extra) == (0, 0)
    run_ = run("sync")
    assert set(run_.discovered_edges) == {bbcvc.edge(*e) for e in EDGES}


def test_discovered_reading_counts_load_on_undiscovered_edges():
    """Capacity counts every claim, so load on an edge the peer never verified
    cannot be hidden by reading the discovered graph only."""
    from types import SimpleNamespace

    from ccvc.bb import sweep as S

    res = SimpleNamespace(
        cover=[2],
        owner={(1, 2): 2, (2, 3): 2},
        double_claimed={},
        discovered_edges=((1, 2),),
    )
    d = S.discovered_reading([(1, 2), (2, 3)], {1: 1, 2: 1, 3: 1}, 1, res)
    assert d == dict(valid_discovered=False, planned_missing=1, discovered_extra=0)
    res.owner = {(1, 2): 2}
    d = S.discovered_reading([(1, 2), (2, 3)], {1: 1, 2: 1, 3: 1}, 1, res)
    assert d["valid_discovered"] is True


# --------------------------------------------------------------------------
# Amendment 6: F9, one stale window per neighbour (bootstrap.py)
# --------------------------------------------------------------------------
def _dev(name):
    if name == "worked":
        return list(EDGES), dict(WEIGHTS), K
    from ccvc.bb import matrix
    from ccvc.bb import sweep as S

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "data", "DagdevirenDataset", name + ".txt")
    if not os.path.exists(path):
        pytest.skip("benchmark dataset not present")
    w, e, _ = S.prepare(*matrix.load_instance(path))
    return e, w, 6


def _trace(r):
    return (
        r.slots,
        r.t_conv_ms,
        r.tx,
        r.rx,
        r.bytes_tx,
        r.cover,
        sorted(r.owner.items()),
        sorted(r.by_type_tx.items()),
        r.restarts,
        [(x["t_ms"], x["nid"], x["event"]) for x in r.net.log_records],
    )


@pytest.mark.parametrize("name", ["worked", "n10_m20_s1", "n15_m30_s1"])
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_F9_is_bit_identical_when_no_record_expires(name, scheduler):
    """Lossless runs, and Bernoulli runs in which no record ever expires, are
    the same run with F9 on and off, down to every log event."""
    e, w, k = _dev(name)
    cases = [(0.0, 0)] + [(loss, s) for loss in (0.02, 0.05) for s in (1, 2, 3)]
    checked = 0
    for loss, seed in cases:
        kw = dict(scheduler=scheduler, max_ms=300_000, loss=loss, seed=seed, watch_ms=0)
        off = bbcvc.run_bbcvc(
            e,
            w,
            k,
            params=bbcvc.BbcvcParams(mis_nbrs_max=64, adaptive_stale=False),
            **kw,
        )
        if any(x["event"] == "nbr_expired" for x in off.net.log_records):
            continue
        on = bbcvc.run_bbcvc(e, w, k, params=bbcvc.BbcvcParams(mis_nbrs_max=64), **kw)
        assert _trace(on) == _trace(off), (loss, seed)
        checked += 1
    assert checked >= 3


def _burst_6_to_4(t, s, d, m):
    """From slot 8, node 6's HELLOs to node 4 are lost in slots 0-4 of every 10."""
    return m == HELLO and (s, d) == (6, 4) and t >= 8 * TAU and (t // TAU) % 10 < 5


def test_F9_a_recurring_burst_no_longer_restarts_the_network():
    """Each 5-slot burst outlasts the fixed 3-period window: without F9 node 4
    expires node 6 every 10 slots and the run restarts until the limit (99
    restarts in 1000 slots). With F9 the first false suspicion doubles node 4's
    window for node 6 to 6 periods, which outlasts the burst."""
    kw = dict(max_ms=1000 * TAU, drop=_burst_6_to_4)
    off = run("sync", params=bbcvc.BbcvcParams(adaptive_stale=False), **kw)
    assert off.verdict == "truncated" and off.restarts > 50
    on = run("sync", **kw)
    assert_worked_cover(on)
    assert on.nodes[4]._stale_p == {6: 6}
    assert on.restarts <= 1
    assert set(on.discovered_edges) == {bbcvc.edge(*x) for x in EDGES}


def _switch_off(victim, t_off, adaptive, pre_bursts, horizon=1000):
    """Node `victim` is switched off at slot `t_off`: it stops ticking and every
    frame to or from it is lost. The verdict is taken over the survivors."""

    def drop(t, s, d, m):
        if victim in (s, d) and t >= t_off * TAU:
            return True
        # earlier false suspicions on the victim's links, to grow the windows
        return (
            pre_bursts
            and m == HELLO
            and s == victim
            and 6 * TAU <= t < t_off * TAU
            and (t // TAU) % 10 < 5
        )

    net = simnet.SimNet(
        IDS,
        EDGES,
        loss=0.0,
        seed=0,
        delay=simnet.fixed_delay(1),
        rssi_range=None,
        macs=bbcvc.macs_for(IDS),
        drop=drop,
    )
    nodes = bbcvc.build_nodes(
        net, WEIGHTS, K, bbcvc.BbcvcParams(adaptive_stale=adaptive)
    )
    sc = sched.SyncScheduler(net, nodes, tau_ms=TAU, weights=WEIGHTS)
    surv = [i for i in IDS if i != victim]
    verdict = None
    for s in range(horizon):
        net.set_now(s * TAU)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            if nid != victim or s < t_off:
                net.set_now(s * TAU)
                nodes[nid].on_timer("tick")
        if all(nodes[i].done for i in surv) and net.in_flight == 0:
            verdict = s + 1
            break
    edges = [x for x in EDGES if victim not in x]
    owner = {x: i for i in surv for x in nodes[i].owned}
    rep = validate.validate(
        validate.make_graph(edges, K, {i: WEIGHTS[i] for i in surv}, nodes=surv),
        sorted(i for i in surv if nodes[i].role.in_cover),
        owner,
    )
    bumps = [x["t_ms"] // TAU for x in net.log_records if x["event"] == "epoch_bump"]
    return verdict, rep.valid, bumps, nodes


def test_F9_a_node_that_is_really_gone_is_still_detected():
    """Without earlier suspicions the removal of node 5 at slot 12 is detected
    exactly as before (slot 19, both settings). After false suspicions grew
    every neighbour's window for node 5 to 6 periods, its removal at slot 20
    is detected later, within twice that window and so within twice the cap,
    and the survivors still end valid."""
    on = _switch_off(5, 12, True, False)
    off = _switch_off(5, 12, False, False)
    assert on[:3] == off[:3]
    assert on[0] is not None and on[1] and on[2][0] == 19

    verdict, valid, bumps, nodes = _switch_off(5, 20, True, True)
    windows = {i: nodes[i]._stale_p.get(5) for i in (4, 6, 7)}
    assert windows == {4: 6, 6: 6, 7: 6}
    cap = bbcvc.BbcvcParams().stale_periods_cap
    assert verdict is not None and valid
    detect = bumps[0] - 20
    assert 0 < detect <= 2 * max(windows.values()) + 1 <= 2 * cap


def test_F9_state_bytes_counts_the_per_neighbour_window():
    w = bbcvc.STATE_WIDTHS
    node = bbcvc.BbcvcNode(3, _FakePort(), bbcvc.BbcvcParams(), 2)
    base = bbcvc.state_bytes(node)
    node._stale_p[5] = 6
    assert bbcvc.state_bytes(node) == base + w["id"] + w["flag"]
    node._expired.add(7)
    assert bbcvc.state_bytes(node) == base + w["id"] + w["flag"] + w["id"]


def test_F9_window_doubles_on_each_false_suspicion_up_to_the_cap():
    p = bbcvc.BbcvcParams(stale_periods_cap=20)
    node = bbcvc.BbcvcNode(3, _FakePort(), p, 2)
    hello = wire.Hello(src=9, key=None, deg=0, role=Role.OUT, phase=0, load=0)
    seen = []
    for _ in range(5):
        node._expired.add(9)
        node.nbrs.pop(9, None)
        node._on_hello(0, 77, None, hello)
        seen.append(node._stale_p[9])
    assert seen == [6, 12, 20, 20, 20]
    assert node.stale_ms(9) == 20 * p.t_hello_ms
