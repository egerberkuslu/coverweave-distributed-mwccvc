"""Regression tests for repairs F14 and F14b (contract R1_PREREG.md, Amendment 9).

F14: a repeated request whose reply was evicted from the bounded reply cache
was executed again. The node-level tests rebuild, on the lossless worked
example, the pattern of the development run n10_m40_s2 (k = 3, loss 0.1,
seed 4), where node 9 kept retransmitting PUSH 52 to node 2 while it sent node 2
four later requests (PUSH 55, HANDOVER 60, PUSH 64, PUSH 67): node 2 evicted the
reply, counted a second acquisition on every copy and finally ran a second push
chain for the same request.

F14b: a copy of the PUSH whose push chain is still running counted an
acquisition it did not make, a failed chain answered PUSH_NACK for an edge such
a copy had taken, and a chain probe that moved `_fix_key` let a node offer an
edge to a neighbour that still had its earlier offer open. The run-level test
drives all of it on development runs with loss. No held-out instance and no
pre-registered seed is used.
"""

from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, matrix, wire  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402
from ccvc.bb.figures import (  # noqa: E402
    WORKED_EDGES as EDGES,
    WORKED_K as K,
    WORKED_WEIGHTS as WEIGHTS,
)
from ccvc.bb.sweep import prepare  # noqa: E402

HANDOVER, PUSH = MsgType.HANDOVER, MsgType.PUSH
#: Everything a request handler can change (the reply cache aside).
STATE = (
    "owned",
    "_explicit",
    "_takes",
    "_offered",
    "_pending",
    "_push_job",
    "_far_job",
    "_join_sent",
    "escalations",
    "role",
)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def state(node):
    return copy.deepcopy({f: getattr(node, f) for f in STATE})


def worked():
    return bbcvc.run_bbcvc(EDGES, WEIGHTS, K, scheduler="sync", max_ms=600_000)


def deliver(r, dst, mt, src, seq, e, ttl=0):
    node = r.nodes[dst]
    # Amendment 13, G7: a request carries the sender's version of the edge
    gen = r.nodes[src]._gen.get(e, 0) if src in r.nodes else 0
    msg = wire.EdgeMsg(mt, src, seq, e[0], e[1], ttl, node.epoch, gen)
    node._on_algo(r.net.now_ms(), node.nbrs[src].mac, msg)


def reply(node, peer, mt, seq):
    payload = node._seen_get((peer, int(mt), seq))
    return None if payload is None else wire.decode(payload).mtype


def test_F14_an_evicted_handover_is_answered_and_not_executed():
    r = worked()
    q, e = r.nodes[5], (5, 7)
    deliver(r, 5, HANDOVER, 7, 1000, e)
    assert e in q.owned and q._explicit[e] is True
    for i, mt in enumerate((PUSH, HANDOVER, PUSH, PUSH), start=1):
        deliver(r, 5, mt, 7, 1000 + i, e, ttl=3 if mt is PUSH else 0)
    assert reply(q, 7, HANDOVER, 1000) is None, "the first reply is evicted"
    before = state(q)
    deliver(r, 5, HANDOVER, 7, 1000, e)  # a copy of the first request
    assert state(q) == before, "a repeated request changes no state"
    assert reply(q, 7, HANDOVER, 1000) is MsgType.HANDOVER_ACK, "I hold the edge"


def test_F14_an_evicted_push_does_not_run_a_second_chain():
    r = worked()
    q, e = r.nodes[6], (4, 6)
    assert len(q.owned) == q.k and q._explicit[e] is False
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)
    while q._push_job is not None:  # every probe of the chain is refused
        (peer, seq), p = next(
            (key, p) for key, p in q._pending.items() if p.tag == "push_chain"
        )
        deliver(r, 6, MsgType.PUSH_NACK, peer, seq, p.e)
    assert reply(q, 4, PUSH, 2000) is MsgType.PUSH_NACK
    for i in range(1, 5):
        deliver(r, 6, HANDOVER, 4, 2000 + i, e)
    assert reply(q, 4, PUSH, 2000) is None, "the first reply is evicted"
    before = state(q)
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)  # a copy of the first request
    assert state(q) == before, "no second chain, no second acquisition"
    assert reply(q, 4, PUSH, 2000) is MsgType.PUSH_NACK


def test_F14_the_mark_is_a_16_bit_serial_number():
    node = worked().nodes[5]
    assert not node._repeated(7, 0xFFFE)
    assert node._repeated(7, 0xFFFE) and node._repeated(7, 0xFF00)
    assert not node._repeated(7, 1), "a seq after the wrap is new"
    assert node._repeated(7, 0xFFFE)


# --------------------------------------------------------------------------
# F14b: a copy of the PUSH whose chain is still running
# --------------------------------------------------------------------------
def refuse_chain(r, dst):
    """Answer every probe of the running push chain at `dst` with a NACK."""
    q = r.nodes[dst]
    while q._push_job is not None:
        (peer, seq), p = next(
            (key, p) for key, p in q._pending.items() if p.tag == "push_chain"
        )
        deliver(r, dst, MsgType.PUSH_NACK, peer, seq, p.e)


def test_F14b_a_busy_copy_without_room_counts_no_acquisition():
    r = worked()
    q, e = r.nodes[6], (4, 6)
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)
    assert q._push_job is not None and len(q.owned) == q.k
    before = state(q)
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)  # a copy while the chain runs
    after = state(q)
    assert after["_push_job"].nacked, "F10: the busy refusal is still flagged"
    after["_push_job"].nacked = before["_push_job"].nacked
    assert after == before, "nothing else changes, no acquisition is counted"
    assert reply(q, 4, PUSH, 2000) is MsgType.PUSH_NACK


def test_F14b_a_failed_chain_acknowledges_the_edge_a_copy_took():
    """Pattern of the lossless development run n15_m90_s1 (k = 6, sync), slot
    19400: node 5 took (4,5) on a copy of node 4's PUSH 24, its chain then
    failed and it answered PUSH_NACK for the edge it held."""
    r = worked()
    q, e = r.nodes[6], (4, 6)
    q._send_edge_msg(r.net.now_ms(), q.nbrs[7], HANDOVER, (6, 7), 0, tag="handover")
    ((_, own),) = [key for key, p in q._pending.items() if p.tag == "handover"]
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)
    assert q._push_job is not None
    deliver(r, 6, MsgType.HANDOVER_ACK, 7, own, (6, 7))  # room opens
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)  # a copy takes the edge
    assert e in q.owned and reply(q, 4, PUSH, 2000) is MsgType.PUSH_ACK
    refuse_chain(r, 6)
    assert e in q.owned
    assert reply(q, 4, PUSH, 2000) is MsgType.PUSH_ACK, "the answer matches the state"


def test_F14b_a_copy_refused_as_unverified_makes_the_answer_late():
    """Pattern of the development run n15_m60_s1 (k = 3, loss 0.2, seed 1),
    slot 132400: node 2 had expired node 6's record and heard it again, so a copy
    of node 6's PUSH 79 met an unverified record and got F7's refusal while the
    chain for it ran. Without the busy flag the chain's acknowledgement was a
    plain one, sent once at 137800."""
    r = worked()
    q, e = r.nodes[6], (4, 6)
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)
    job = q._push_job
    assert job is not None and not job.nacked
    q.nbrs[4].bidir = False  # heard again after an expiry, not verified yet
    deliver(r, 6, PUSH, 4, 2000, e, ttl=1)  # a copy from a frozen neighbour
    # Amendment 13, G3: node 4 is in node 6's frozen view, so the copy is not
    # refused but waits (the F4 wait); the chain's answer stays the normal one.
    assert not job.nacked, "a frozen neighbour re-verifying is waited for"
    q.nbrs[4].bidir = True
    (peer, seq), p = next(
        (key, p) for key, p in q._pending.items() if p.tag == "push_chain"
    )
    deliver(r, 6, MsgType.PUSH_ACK, peer, seq, p.e)  # the chain succeeds
    assert q._push_job is None and e in q.owned
    assert (4, bbcvc._LATE_KEY | 2000) not in q._pending, "a plain answer (G3)"
    assert reply(q, 4, PUSH, 2000) == MsgType.PUSH_ACK


def test_F14b_one_own_transfer_per_neighbour():
    """Node 6 hands (6,7) to node 7 as stage 1 of `_fix_overload` does. A chain
    probe for node 4's PUSH moves `_fix_key` and its refusal clears it, so the
    gate of `_rule_ownership` opens although the handover is still open. The
    calls an overloaded node then makes must not offer (6,7) to node 7 again."""
    r = worked()
    q = r.nodes[6]
    q._tried.add((7, HANDOVER, (6, 7)))
    q._send_edge_msg(r.net.now_ms(), q.nbrs[7], HANDOVER, (6, 7), 0, tag="handover")
    first = q._fix_key
    deliver(r, 6, PUSH, 4, 2000, (4, 6), ttl=1)
    refuse_chain(r, 6)
    assert q._fix_key is None and first in q._pending, "the gate is open"
    for _ in range(4):
        q._fix_overload(r.net.now_ms(), q._nbrs_active())
    to_7 = [
        key
        for key, p in q._pending.items()
        if p.peer == 7 and p.tag in ("handover", "push")
    ]
    assert to_7 == [first], "a second transfer of (6,7) to node 7"


#: Development runs (published dataset, sync, i.i.d. loss 0.3). At k = 3 the
#: graph has m = 40 > nk = 30 edges, so the repair stages and their push chains
#: run until the verdict. Before F14 and F14b every check below fails on them;
#: after, seeds 6 and 14 still carry an evicted repeat and all carry busy copies.
# note to Amendment 15: with the link gate the evicted-copy case no longer occurs on
# seeds 0, 6, 14; seed 1 is added for it (24 seeds checked, no inconsistency on any)
# Amendment 17: with R2 the evicted-copy case no longer occurs on seeds 0, 6,
# 14 and 1; of seeds 2 to 29, seeds 5 and 21 show it, so seed 5 was added.
INSTANCE, LOSS, SEEDS = "n10_m40_s2", 0.3, (0, 6, 14, 1, 5)


def test_F14_on_lossy_development_runs_requests_and_answers_agree(monkeypatch):
    """The worst case, driven on development runs. A copy of an answered request
    that missed the cache changes no state (F14); a copy of the PUSH whose chain
    runs counts no acquisition it does not make, and a chain never answers
    PUSH_NACK for an edge its node holds by a transfer (F14b); no node sends an
    own HANDOVER or PUSH to a neighbour while one to it is open (F14b)."""
    path = os.path.join(ROOT, "data", "DagdevirenDataset", INSTANCE + ".txt")
    if not os.path.exists(path):
        pytest.skip("benchmark dataset not present")
    w, e, _ = prepare(*matrix.load_instance(path))
    seen = {"evicted": [], "busy": [], "chain_end": [], "own": []}
    bad = {key: [] for key in seen}
    N = bbcvc.BbcvcNode

    def audited(mt, orig):
        def handler(self, now, n, msg):
            done = self.__dict__.setdefault("_test_done", set())
            key = (self.epoch, n.nid, int(mt), msg.seq)
            job = self._push_job if mt is PUSH else self._far_job
            busy = job is not None and (job.src, job.seq) == (n.nid, msg.seq)
            missed = self._seen_get(key[1:]) is None
            if mt is PUSH and busy and missed:
                ed = bbcvc.edge(msg.u, msg.v)
                takes, held = self._takes.get(ed, 0), ed in self.owned
                explicit = self._explicit.get(ed)
                orig(self, now, n, msg)
                seen["busy"].append(key)
                took = held != (ed in self.owned) or explicit != self._explicit.get(ed)
                if self._takes.get(ed, 0) != takes and not took:
                    bad["busy"].append((self.nid, key))
                return
            if key not in done or busy or not missed:
                done.add(key)
                return orig(self, now, n, msg)
            before = state(self)
            orig(self, now, n, msg)
            seen["evicted"].append(key)
            if state(self) != before:
                bad["evicted"].append((self.nid, key))

        return handler

    def finish(orig):
        def handler(self, now, ok):
            job = self._push_job
            orig(self, now, ok)
            if job is not None:
                seen["chain_end"].append((self.nid, job.src, job.seq))
                answer = reply(self, job.src, PUSH, job.seq)
                if self._explicit.get(job.e) is True and answer is MsgType.PUSH_NACK:
                    bad["chain_end"].append((self.nid, job.src, job.seq))

        return handler

    def send(orig):
        def handler(self, now, n, mt, ed, ttl, tag):
            if tag in ("handover", "push"):
                seen["own"].append((self.nid, n.nid))
                if any(
                    p.peer == n.nid and p.tag in ("handover", "push")
                    for p in self._pending.values()
                ):
                    bad["own"].append((self.nid, n.nid, tag))
            return orig(self, now, n, mt, ed, ttl, tag)

        return handler

    for name, mt in (
        ("_on_join", MsgType.JOIN),
        ("_on_handover", HANDOVER),
        ("_on_push", PUSH),
    ):
        monkeypatch.setattr(N, name, audited(mt, getattr(N, name)))
    monkeypatch.setattr(N, "_finish_push_job", finish(N._finish_push_job))
    monkeypatch.setattr(N, "_send_edge_msg", send(N._send_edge_msg))
    # F17 would certify this infeasible instance early and end the repairs
    # this audit needs; without its wave they run as long as before F17.
    monkeypatch.setattr(N, "_cert_start", lambda self, now: None)
    for seed in SEEDS:
        res = bbcvc.run_bbcvc(
            e,
            w,
            3,
            scheduler="sync",
            loss=LOSS,
            seed=seed,
            params=bbcvc.BbcvcParams(mis_nbrs_max=64),
            # note to Amendment 15: the link gate waits up to R = 4 failed rounds at
            # 30 % loss; without F17 seed 6 ends unresolved at 3 092 800 ms
            max_ms=6_000_000,
            watch_ms=0,
        )
        assert res.verdict == "unresolved" and res.double_claimed == {}
    assert all(seen.values()), {key: len(v) for key, v in seen.items()}
    assert bad == {key: [] for key in seen}, {key: v[:3] for key, v in bad.items()}
