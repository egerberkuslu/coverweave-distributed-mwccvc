#!/usr/bin/env python3
"""R2R3-repair (Amendment 17): the three counterexamples to Theorem 3(b).

The Lean model of the transfer layer of one flexible edge
(formal ExecFullTransfer.lean, `thm3b_fails_without_yield`, `thm3b_fails_with_yield`,
`thm3b_fails_repeat`) found three runs that end quiet, with every frame
delivered in order and every positive answer delivered to its sender, in
which the edge has two owners or none. Each test below replays the Lean
event list on the handlers of bbcvc.py: two nodes of the worked example, one
FIFO channel per direction, frames delivered, lost or retransmitted exactly
as the list says. What the rest of the protocol decides (the message-free
start, room for the edge, a chain's outcome) is set by hand, as in the Lean
events `flip`, `room` and `finish`. An event the code does not enable (a
delivery on an empty channel) is skipped. The run then settles: every frame
is delivered and every open request repeated until nothing is open, and the
edge must have exactly one owner.

`traceBusy` and `traceRepeat` fail before R2 and R3 and pass after; the
sequence of R4 (Lean bounded search) fails before R4 and passes after.
`traceNoYield` refutes the text, not the code: the code's yield rule closes
it, so that test checks the yield rule and that disabling it reopens the race.

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_r2r3.py -q
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, wire  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402
from ccvc.bb.figures import WORKED_EDGES, WORKED_K, WORKED_WEIGHTS  # noqa: E402

H, P = MsgType.HANDOVER, MsgType.PUSH
E = (6, 7)


class Pair:
    """Nodes a = 6 (the smaller key) and b = 7 of the converged worked example,
    reset to the start of Phase 4 for e = (6, 7): no transfer of e yet, both
    holding e by the message-free start (their advertised budgets disagree)."""

    def __init__(self):
        r = bbcvc.run_bbcvc(
            WORKED_EDGES, WORKED_WEIGHTS, WORKED_K, scheduler="sync", max_ms=600_000
        )
        self.r = r
        self.n = [r.nodes[6], r.nodes[7]]
        a, b = self.n
        assert a._mykey() < b._mykey()
        self.chan = [[], []]
        self.dflt = [True, True]
        self.offers = [[], []]
        for i, nd in enumerate(self.n):
            peer_mac = nd.nbrs[self.n[1 - i].nid].mac
            nd.plat.send_unicast = self._capture(i, peer_mac)
            nd._explicit.pop(E, None)
            nd.owned.add(E)
            nd._pending.clear()
            nd._push_job = None
            nd._offered.discard(E)

    def _capture(self, i, peer_mac):
        def send(mac, payload):
            if mac == peer_mac:  # a chain's probes to other neighbours stay out
                self.chan[i].append(payload)

        return send

    def now(self):
        return self.r.net.now_ms()

    def nbr(self, i):
        return self.n[i].nbrs[self.n[1 - i].nid]

    def room(self, i, room):
        """`len(owned) < k` at node i, for e's acceptance, by moving other edges."""
        nd = self.n[i]
        others = sorted(x for x in nd.owned if x != E)
        while room and len(nd.owned) >= nd.k:
            nd.owned.discard(others.pop(0))
        j = 0
        while not room and len(nd.owned - {E}) < nd.k:
            nd.owned.add((nd.nid, 1000 + j))  # a stand-in for another edge
            j += 1

    # ---- the Lean events -------------------------------------------------
    def offer(self, i, push):
        nd = self.n[i]
        mt, ttl = (P, 3) if push else (H, 0)
        nd._send_edge_msg(
            self.now(), self.nbr(i), mt, E, ttl, tag="push" if push else "handover"
        )
        self.offers[i].append(nd._fix_key[1])

    def retx(self, i, k):
        p = self.n[i]._pending.get((self.n[1 - i].nid, self.offers[i][k - 1]))
        if p is not None:
            self.chan[i].append(p.payload)

    def evict(self, i, k):
        seq = self.offers[1 - i][k - 1]
        for mt in (H, P):
            self.n[i]._seen.get(self.n[1 - i].nid, {}).pop((int(mt), seq), None)

    def flip(self, i):
        self.dflt[i] = not self.dflt[i]
        nd = self.n[i]
        if nd._explicit.get(E) is None:
            (nd.owned.add if self.dflt[i] else nd.owned.discard)(E)

    def lose(self, i):
        if self.chan[i]:
            self.chan[i].pop(0)

    def deliver(self, i, room=False, chain=False):
        if not self.chan[i]:
            return
        j = 1 - i
        self.room(j, room)
        msg = wire.decode(self.chan[i].pop(0))
        self.n[j]._on_algo(self.now(), self.nbr(j).mac, msg)

    def finish(self, i, ok, room):
        nd = self.n[i]
        if nd._push_job is None:
            return
        for key in [k for k, p in nd._pending.items() if p.tag == "push_chain"]:
            del nd._pending[key]  # the chain's probe was answered
        self.room(i, room)
        nd._finish_push_job(self.now(), ok)

    # ---- the end ---------------------------------------------------------
    def settle(self, rounds=20):
        """Deliver everything, repeat every open request of e, until quiet."""
        for _ in range(rounds):
            if self.chan[0] or self.chan[1]:
                for i in (0, 1):
                    while self.chan[i]:
                        self.deliver(i, room=False)
                continue
            open_ = [
                (i, p)
                for i, nd in enumerate(self.n)
                for p in nd._pending.values()
                if p.e == E and p.peer == self.n[1 - i].nid
            ]
            if not open_:
                break
            for i, p in open_:
                self.chan[i].append(p.payload)
        a, b = self.n
        assert not self.chan[0] and not self.chan[1]
        assert a._push_job is None and b._push_job is None
        assert not [p for nd in self.n for p in nd._pending.values() if p.e == E]

    def owners(self):
        out = []
        for i, nd in enumerate(self.n):
            x = nd._explicit.get(E)
            if x is True or (x is None and self.dflt[i]):
                out.append(nd.nid)
        return out


def run(trace, pair=None):
    pair = pair or Pair()
    for ev, *args in trace:
        getattr(pair, ev)(*args)
    pair.settle()
    return pair


A, B = 0, 1
#: `traceNoYield`: two HANDOVERs that cross, then the start agrees.
TRACE_NO_YIELD = [
    ("offer", A, False),
    ("offer", B, False),
    ("deliver", A),
    ("deliver", B),
    ("deliver", B),
    ("deliver", A),
    ("flip", B),
]
#: `traceBusy`: a's PUSH meets b's chain, a copy of it meets the busy chain.
TRACE_BUSY = [
    ("offer", A, True),
    ("retx", A, 1),
    ("offer", B, False),
    ("flip", B),
    ("deliver", A, False, True),
    ("deliver", A),
    ("lose", B),
    ("retx", B, 1),
    ("deliver", B),
    ("finish", B, True, True),
    ("deliver", B),
    ("deliver", A),
    ("deliver", B),
    ("deliver", A),
]
#: `traceRepeat`: HANDOVERs only; b's cache evicts its refusal of a's request.
TRACE_REPEAT = [
    ("offer", A, False),
    ("flip", A),
    ("deliver", A),
    ("offer", B, False),
    ("deliver", B),
    ("retx", B, 1),
    ("deliver", B, True),
    ("offer", A, False),
    ("lose", A),
    ("retx", A, 2),
    ("deliver", A),
    ("evict", B, 2),
    ("deliver", B),
    ("deliver", A),
    ("deliver", A),
    ("lose", B),
    ("deliver", B),
]


#: R4, found by the Lean model's bounded search: HANDOVERs only, no busy PUSH,
#: no eviction. Both ends offer e; the start stops giving e to b, which is full;
#: a's request reaches b, which does not yield and refuses for lack of room;
#: b's own request is lost and retransmitted, a (its offer answered) accepts it;
#: b reads the ACK; the start gives e to b again.
TRACE_FULL = [
    ("offer", A, False),
    ("offer", B, False),
    ("flip", B),
    ("deliver", A),
    ("lose", B),
    ("deliver", B),
    ("retx", B, 1),
    ("deliver", B),
    ("deliver", A),
    ("flip", B),
]


def test_crossing_handovers_are_refused_by_the_yield_rule(monkeypatch):
    assert len(run(TRACE_NO_YIELD).owners()) == 1
    # The Lean run is a run of the text, which does not state the yield rule.
    monkeypatch.setattr(bbcvc.BbcvcNode, "_yields_to_inbound", lambda *_: False)
    assert len(run(TRACE_NO_YIELD).owners()) == 2


def test_R2_a_busy_copy_of_a_push_leaves_one_owner():
    p = run(TRACE_BUSY)
    assert len(p.owners()) == 1, (p.owners(), [n._explicit.get(E) for n in p.n])
    late = [x for x in p.r.net.log_records if x["event"].startswith("late_ack")]
    assert late == [], "R2: no late acknowledgement exists"


def test_R3_a_repeat_after_an_evicted_refusal_leaves_one_owner():
    p = run(TRACE_REPEAT)
    assert len(p.owners()) == 1, (p.owners(), [n._explicit.get(E) for n in p.n])


def test_R4_a_refusal_for_lack_of_room_counts_no_take():
    p = Pair()
    b = p.n[B]
    for ev, *args in TRACE_FULL[:3]:
        getattr(p, ev)(*args)
    takes = b._takes.get(E, 0)
    p.deliver(A)  # b is full: refused
    counted = (b._takes.get(E, 0), E in b._offered) != (takes, True)
    for ev, *args in TRACE_FULL[4:]:
        getattr(p, ev)(*args)
    p.settle()
    assert len(p.owners()) == 1, (p.owners(), [n._explicit.get(E) for n in p.n])
    assert not counted, "R4: a refusal counts no take and keeps my offer"


@pytest.mark.parametrize(
    "held,gen_mine,gen_sent,ok",
    [
        (True, 3, 2, True),  # what accepting the request left
        (True, 1, 2, False),  # refused as stale (traceRepeat)
        (True, 2, 2, False),  # refused; or I hold e from a transfer already completed
        (False, 3, 2, False),  # released since
        (True, 0, 255, True),  # the 8-bit count wraps
    ],
)
def test_R3_repeat_answer(held, gen_mine, gen_sent, ok):
    nd = Pair().n[1]
    nd._explicit[E] = held
    nd._gen[E] = gen_mine
    msg = wire.EdgeMsg(H, 6, 1, E[0], E[1], 0, nd.epoch, gen_sent)
    assert nd._repeat_ok(msg, E) is ok


# --------------------------------------------------------------------------
# The same rules on F7's refusal path (a copy from a peer heard, not verified)
# --------------------------------------------------------------------------
def unverified(q, peer):
    """`peer` heard again after an expiry and outside q's frozen view: F7 refuses."""
    q.nbrs[peer].bidir = False
    q._frozen_bidir = q._frozen_bidir - {peer}
    sent = []
    q._ucast = lambda n, payload: sent.append(wire.decode(payload).mtype)
    return sent


def test_R2_a_copy_refused_by_F7_stops_the_chain():
    from ccvc.bb.test_r1_f14 import deliver, reply, worked

    r = worked()
    q, e = r.nodes[6], (4, 6)
    deliver(r, 6, P, 4, 2000, e, ttl=1)
    job, frozen = q._push_job, q._frozen_bidir
    assert job is not None and q._explicit.get(e) is False
    sent = unverified(q, 4)
    deliver(r, 6, P, 4, 2000, e, ttl=1)  # a copy refused by F7 while the chain runs
    assert sent == [MsgType.PUSH_NACK] and job.nacked
    del q._ucast
    q._frozen_bidir, q.nbrs[4].bidir = frozen, True
    (peer, seq), p = next((k, p) for k, p in q._pending.items() if p.tag == "push_chain")
    deliver(r, 6, MsgType.PUSH_ACK, peer, seq, p.e)  # the chain succeeds
    assert q._push_job is None and e not in q.owned, "R2: the refused chain takes nothing"
    assert reply(q, 4, P, 2000) is MsgType.PUSH_NACK
    assert not [k for k in q._pending if k[1] & bbcvc._LATE_KEY], "no late acknowledgement"


def test_R3_F7_answers_a_copy_as_its_request_was_answered():
    from ccvc.bb.test_r1_f14 import deliver, worked

    r = worked()
    q, e = r.nodes[5], (5, 7)
    deliver(r, 5, H, 7, 1000, e)
    assert q._explicit[e] is True
    sent = unverified(q, 7)
    deliver(r, 5, H, 7, 1000, e)  # a copy: the cached answer
    q._seen[7].pop((int(H), 1000))
    deliver(r, 5, H, 7, 1000, e)  # evicted: answered from my state (R3)
    assert sent == [MsgType.HANDOVER_ACK, MsgType.HANDOVER_ACK]


def test_R2_a_refused_request_is_never_answered_ACK_later():
    """Found by the Lean search of 5d9936a: after the busy refusal, a later
    HANDOVER of the same edge from the same sender is accepted, and the refused
    PUSH (an evicted copy while the chain runs, and the chain's end) was then
    answered ACK from `_explicit`: the cache held ACK for a request already
    NACKed."""
    from ccvc.bb.test_r1_f14 import deliver, refuse_chain, reply, worked

    r = worked()
    q, e = r.nodes[6], (4, 6)
    q._send_edge_msg(r.net.now_ms(), q.nbrs[7], H, (6, 7), 0, tag="handover")
    ((_, own),) = [key for key, p in q._pending.items() if p.tag == "handover"]
    deliver(r, 6, P, 4, 2000, e, ttl=1)
    job = q._push_job
    deliver(r, 6, P, 4, 2000, e, ttl=1)  # a busy copy without room
    assert job.nacked and reply(q, 4, P, 2000) is MsgType.PUSH_NACK
    deliver(r, 6, MsgType.HANDOVER_ACK, 7, own, (6, 7))  # room opens
    deliver(r, 6, H, 4, 2001, e)  # the sender's next transfer of e
    assert q._explicit[e] is True
    q._seen[4].pop((int(P), 2000))  # the refusal is evicted
    deliver(r, 6, P, 4, 2000, e, ttl=1)  # a late copy while the chain runs
    assert reply(q, 4, P, 2000) is MsgType.PUSH_NACK, "the busy path"
    refuse_chain(r, 6)
    assert q._push_job is None
    assert reply(q, 4, P, 2000) is MsgType.PUSH_NACK, "the chain's end"
