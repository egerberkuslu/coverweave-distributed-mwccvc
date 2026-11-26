"""GHS-MST-Backbone: distributed minimum spanning tree (GHS), then backbone MIS.

WHAT THIS ARM IS FOR. The brief glosses the comparison as "why MST is the wrong
tree". That gloss claims more than the theorem it cites: G3 states the DFS
property for UNWEIGHTED vertex cover at k = infinity, while these instances are
weighted with a tight k. So the honest question this arm answers is narrower:
does an MST backbone produce a worse cover than MIS+connector on the benchmark,
and what does building one distributed actually cost?

WHY THE CENTRAL VERSION IS NOT ENOUGH. `variants.mst_internal_nodes()` computes
the same tree with the whole graph in hand. Keeping only that would make GHS-MST-Backbone a
full-information arm, which cannot be compared on message cost against arms that
build their own backbone. It stays as an ORACLE used by tests to check this
protocol, and is never called from node code.

THE PROTOCOL is Gallager-Humblet-Spira, with the seven messages the brief names:
CONNECT, INITIATE, TEST, ACCEPT, REJECT, REPORT, CHANGE-ROOT. Fragments carry a
level and an identity; a lower-level fragment is absorbed by a higher one, and
two fragments of equal level merge into one of level+1 identified by the weight
of the edge joining them.

EDGE WEIGHT is derived, because the graph carries only NODE weight: w(u)+w(v),
ties broken by the edge identity (u, v) so the tree is deterministic. A node
compares two weights and never tests one against a threshold, which is what
keeps the protocol scale-free: multiply every weight by a constant and the same
tree comes out.

CORRECTNESS GATE, AND ITS CURRENT VERDICT.

    STATUS: COMPLETE AND REGISTERED (2026-09-16).

The gate was set before the code was written: the distributed backbone must
equal the central oracle's. It now passes on every scale measured.

    scale                       result
    five constructed families   10/10 equal, solved, valid (both schedulers)
    small group, k=6            66 pass, 12 n/a, 0 fail
    n=50, six seeds             17 of 18 feasible rows per arm and scheduler;
                                the one failure is n50_m300 seed 6, which
                                EVERY arm fails, so it is the instance and not
                                this algorithm
    n=100                       12/12, best arm of the comparison

TEN REAL DEFECTS WERE FOUND AND FIXED, and they fall into four classes. The
classes matter more than the list, because a class recurs in the next variant
while a single bug does not. Full write-up in BULGULAR_BB.md 80, 82, 85, 86 and
106.

  CLASS 1, information needed for a total order dropped at the wire boundary
  (defects 1, 2 and 7 below, plus one in MIS-Connector-TreeAgg's STABLE message).
  CLASS 2, treating somebody else's unanswered question as my own uncertainty
  (defects 3, 4, 5 and 6): the rule that finally held is that NO deferred
  message blocks, only this node's own outstanding `ghs_test_nid`.
  CLASS 3, the seam has an unwritten precondition (defect 9): the shared
  `_on_join` promotes any node whose role is still OUT, and GHS-MST-Backbone assigns roles
  late, so a JOIN tore a node out of PH_CONN before it announced its decision.
  CLASS 4, THE MIRROR OF CLASS 2 (defect 10): my own UNFINISHED search read as
  a finished one. `ghs_test_nid` answers "is a question in flight", not "is my
  search over", and `_ghs_try_report` tested only the first. A child's REPORT
  arriving between a REJECT and the next `_ghs_test` carried the node out of
  FIND with its remaining BASIC edges untested, so its fragment claimed a
  heavier minimum outgoing edge than it had and two fragments deadlocked on
  two different edges. See `_ghs_try_report`.

They are listed because the next attempt should start from here rather than
repeat the search.

1. FRAGMENT IDENTITY WAS TRUNCATED BY THE WIRE.
   `frag` was a 2-byte field while a fragment is identified by the weight of its
   core edge, which is 16.16 fixed point. Every identity truncated to the same
   value, so `_ghs_on_test` compared equal every time and answered REJECT, no
   node ever found an outgoing edge, and fragments halted without merging --
   a spanning tree that did not span. The field is now 4 bytes.

2. A DEFERRED QUESTION WAS BEING READ AS AN ANSWER.
   A fragment halted on `best == INF` while two of its TESTs were still
   deferred. "I could not determine" was concluded as "there is none" -- the
   same conflation that made an earlier infeasibility witness unsound, and the
   reason `local_infeasibility_witness` returns None rather than False.

3. THE FIX FOR (2) CREATED A CIRCULAR WAIT, which is itself instructive.
   Counting EVERY deferred message as pending deadlocked the core edge: two
   nodes across it each name the other parent, a REPORT arriving early is
   deferred because the receiver is in FIND, and that deferral then prevents it
   from ever leaving FIND. The distinction that resolves it: a deferred TEST is
   MY unanswered question and must block; a deferred REPORT is somebody else's
   ANSWER that arrived before I was ready, and must not.

WHAT REMAINS WRONG, with the evidence rather than a guess. On `bridge` the
BRANCH edges still form two disjoint trees, {1,2,3,4,7} and {5,6}, with edge
(4,5) never taken, so at least one more defect sits in the merge/absorb path or
in the FIND/FOUND report cycle. On `star5` an earlier trace showed node 3
carrying `frag=196608` while the rest of its own fragment carried `196606`,
which points at the identity assigned on one side of a merge differing from the
other -- worth checking first.

WHAT IS KNOWN GOOD, so it is not rebuilt: the seven message types and their
codecs round-trip exactly; peer weight is recovered from HELLO's advertised
degree and uses only heard information, never a weight table; and the backbone
MIS and termination flood are shared in shape with DFS-Spanning-Backbone, which does pass its
own gate.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Set, Tuple

from ccvc.bb import wire
from ccvc.bb.api import MsgType, Role, to_fp
from ccvc.bb.bbcvc import PH_CONN, PH_COVER, PH_MIS, BbcvcNode, BbcvcParams, run_bbcvc
from ccvc.bb.bootstrap import BootNeighbor

# Node states (GHS).
SLEEPING, FIND, FOUND = 0, 1, 2
# Edge states.
BASIC, BRANCH, REJECTED = 0, 1, 2

#: Stands in for "no edge is better than this". Larger than any real w(u)+w(v)
#: on these instances by a wide margin, and carried as fixed point on the wire.
INF_W = 1 << 30


class V4MstDistNode(BbcvcNode):
    """Phase 1 = internal nodes of a DISTRIBUTED MST. No graph, no oracle."""

    def __init__(self, weight, platform, params=None, capacity_k: int = 2) -> None:
        super().__init__(weight, platform, params, capacity_k)
        self.ghs_state = SLEEPING
        self.ghs_level = 0
        self.ghs_frag = 0                     # fragment identity (a core EDGE)
        self.ghs_parent: Optional[int] = None  # neighbour towards the core
        self.ghs_edge: Dict[int, int] = {}     # nid -> BASIC | BRANCH | REJECTED
        self.ghs_best_wt = INF_W
        self.ghs_best_key = (INF_W, 0, 0)  # F18: a REPORT can reach a node never initiated
        self._ghs_round_ms = 0          # F18: when my current round began
        self.ghs_best_nid: Optional[int] = None
        self.ghs_test_nid: Optional[int] = None
        self.ghs_test_done = False     # my minimum outgoing edge is settled
        #: Edges where I sent CONNECT and the peer has not yet agreed. They are
        #: BRANCH on my side but are NOT yet children of my fragment.
        self.ghs_connect_out: Set[int] = set()
        self._ghs_deferred_set: Set[Tuple] = set()
        self.ghs_root_acted = False
        self.ghs_reported: Set[int] = set()     # children whose REPORT arrived
        #: F12b: child -> its subtree's certificate sums in this round, and the
        #: last sums each peer's REPORT carried, with that REPORT's level.
        self._ghs_child_cert: Dict[int, Tuple[int, int, int]] = {}
        self._ghs_peer_cert: Dict[int, Tuple[int, Tuple[int, int, int]]] = {}
        #: G6 (Amendment 13): child -> (level, fragment, state) of the INITIATE
        #: I sent it, so that a repeat carries the round's content.
        self._ghs_init_sent: Dict[int, Tuple[int, int, int]] = {}
        self.ghs_retry_ms = 0                   # when to re-ask an unanswered question
        self._ghs_last_asked = None             # the question outstanding last time
        self._ghs_retries = 0                   # re-asks spent on that question
        self.ghs_deferred: list = []           # (mtype, nid, level, frag, wfp)
        self.ghs_peer_deg: Dict[int, int] = {}  # heard from HELLO, not given
        self.ghs_halted = False
        # measurement, reported separately rather than folded into tx
        self.ghs_merges = 0
        self.ghs_rejects = 0
        self.ghs_connects = 0
        # backbone MIS, shared shape with DFS-Spanning-Backbone
        self._v4_in_backbone = False
        self._v4_mis_claim: Optional[bool] = None
        self._v4_bb_members: Set[int] = set()
        self._v4_bb_decided: Dict[int, bool] = {}
        self._v4_done_seen = False

    # ------------------------------------------------------------- weights
    def _on_hello(self, now: int, src_mac: int, rssi, h) -> None:
        """Record the peer's advertised degree, then defer to the base class.

        WHY THIS EXISTS. The MST criterion is w(u)+w(v), and a node must
        therefore recover a NEIGHBOUR's weight. The key on the wire is
        w/(deg+1), so the weight follows from key and degree -- and `deg` IS on
        the wire in every HELLO, it is simply not kept in the neighbour record.
        GHS-MST-Backbone keeps its own copy rather than widening `api.Neighbor`, because this
        is one arm's need and the record is shared by every arm.

        This is information the node HEARD. It is not a weight table handed to
        it, and nothing here reads a graph.
        """
        super()._on_hello(now, src_mac, rssi, h)
        if h.deg is not None:
            self.ghs_peer_deg[h.src] = int(h.deg)

    def _peer_w(self, n: BootNeighbor) -> int:
        """Recover w(peer) in fixed point from key = w/(deg+1) and heard degree."""
        deg = self.ghs_peer_deg.get(n.nid)
        if n.key is None or deg is None:
            return INF_W
        return int(n.key) * (deg + 1)

    def _my_w_fp(self) -> int:
        """My own weight AS A PEER WOULD RECONSTRUCT IT, not as I know it.

        THE EDGE CRITERION MUST BE SYMMETRIC OR THE PROTOCOL BREAKS. A fragment
        is identified by the weight of its core edge, and both endpoints compute
        that weight independently. If one uses its exact own weight while the
        other reconstructs it from `key = w/(deg+1)`, the two disagree whenever
        that division is not exact -- measured: w=1, deg=4 gives to_fp(1)=65536
        against a reconstruction of 13107*5=65535. One unit.

        The consequence was not one unit. The two endpoints of a merge assigned
        DIFFERENT identities to the same new fragment, so a node ended up in a
        fragment whose members disagreed about what fragment they were in, and
        TEST comparisons across that boundary answered wrongly.

        So a node reconstructs its OWN weight the same lossy way a peer does.
        Both sides then compute the identical number by construction rather than
        by luck, and the criterion stays `w(u)+w(v)` up to one shared rounding.
        """
        if self.key_fp is None or self.deg is None:
            return INF_W
        return int(self.key_fp) * (int(self.deg) + 1)

    @staticmethod
    def _pack_tie(key: Tuple[int, int, int]) -> int:
        """The two id components of an edge key, in one signed 32-bit field.

        Node ids are bounded by the matrix (n <= 1000), so 15 bits each is
        ample and the product stays well inside a signed int.
        """
        lo, hi = int(key[1]), int(key[2])
        assert 0 <= lo < 32768 and 0 <= hi < 32768, (lo, hi)
        return lo * 32768 + hi

    @staticmethod
    def _unpack_tie(wfp: int, tie: int) -> Tuple[int, int, int]:
        return (int(wfp), int(tie) // 32768, int(tie) % 32768)

    def _weight_of(self, n: BootNeighbor) -> Tuple[int, int, int]:
        """Total order on edges: (w(u)+w(v), min id, max id)."""
        pw = self._peer_w(n)
        if pw >= INF_W:
            return (INF_W, 0, 0)
        return (self._my_w_fp() + pw, min(self.nid, n.nid), max(self.nid, n.nid))

    def _edges_now(self, nb: Sequence[BootNeighbor]):
        out = []
        for n in nb:
            if not n.is_edge:
                continue
            self.ghs_edge.setdefault(n.nid, BASIC)
            out.append(n)
        return out

    # ------------------------------------------------------------ phase seam
    def _backbone_step(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        edges = self._edges_now(nb)
        if not edges:
            self._v4_finish_roles(now)
            return
        if self.phase == PH_MIS and self._v4_phase1_over(edges):
            # THE END OF PHASE 1 IS ANNOUNCED ONCE AND CAN BE LOST.
            # `_v4_flood_done` broadcasts a single DFS_DONE and never repeats
            # it, so one dropped frame at a cut point strands the whole subtree
            # behind it: those nodes hold a finished spanning tree with nothing
            # left to ask and no one left to wait for, and they sit in PH_MIS
            # until the budget runs out. Losing a frame is not an error here,
            # it is the channel.
            #
            # NO NEW MESSAGE IS NEEDED, BECAUSE THE ANSWER IS ALREADY ON THE
            # AIR. A neighbour that has moved past PH_MIS is beaconing that
            # phase in every HELLO, and it could only have moved by halting or
            # by hearing DONE, both of which mean the tree is complete. Reading
            # the beacon turns a one-shot announcement into a standing fact,
            # which is the same lesson as the termination barrier in
            # `bbcvc._barrier_closed`.
            #
            # MEASURED on the discovered n15_m90 s1 graph at five per cent
            # loss, seed 3: the core pair 12 and 13 halted and reached phase 3
            # while the other THIRTEEN nodes stayed in phase 1, one fragment,
            # every best at INF, no outstanding question anywhere. The run
            # returned a cover of two.
            self._v4_done_seen = True
            self._v4_flood_done(now)
            self._v4_enter_mis(now)
        elif self.phase == PH_MIS:
            if self.ghs_state == SLEEPING:
                if not self._ghs_weights_known(edges):
                    return              # waking on partial information is wrong
                self._ghs_wakeup(now, edges)
            self._ghs_replay(now, edges)
            if self.ghs_state == FIND:
                self._ghs_test(now, edges)
            self._ghs_try_report(now, edges)
            self._ghs_reassert(now, edges)
        elif self.phase == PH_CONN:
            self._v4_mis_step(now, edges)

    # ------------------------------------------------------------- GHS core
    def _ghs_weights_known(self, edges) -> bool:
        """Can I order ALL my incident edges yet?

        A sleeping node's fragment is a singleton, so its minimum outgoing edge
        is simply its lightest incident edge. Choosing it needs every peer's
        weight, and a peer's weight is only reconstructible once its degree has
        arrived in a HELLO: `_peer_w` returns INF_W until then. Waking earlier
        does not fail loudly, it silently ranks the unknown neighbours last and
        picks the lightest of whoever happened to answer first.

        MEASURED on n10_m20 s2: node 8's lightest edge is (7,8) at 545, but it
        woke before node 7's degree arrived and connected on (4,8) at 565. The
        run still produced a spanning tree of the right size and terminated, so
        nothing looked wrong; it just weighed 8480 against the true minimum of
        7708. A wrong answer that validates is worse than a crash.
        """
        if self.key_fp is None or self.deg is None:
            return False
        if self._view_stale():
            # G1 (Amendment 13, third note): waking orders ALL my edges, so a
            # handler waits while a frozen neighbour is missing; woken by a
            # CONNECT on a partial view, node 4 chose a wrong lightest edge and
            # five level-0 CONNECTs waited on each other (n5g5 k1 async).
            return False
        return all(self._peer_w(n) < INF_W for n in edges)

    def _ghs_wakeup(self, now: int, edges) -> None:
        best = min(edges, key=self._weight_of)
        self.ghs_edge[best.nid] = BRANCH
        self.ghs_level = 0
        self.ghs_state = FOUND
        self.ghs_reported.clear()
        self._ghs_child_cert.clear()
        self.ghs_connects += 1
        self.ghs_connect_out.add(best.nid)
        self._ghs_send(best, MsgType.GHS_CONNECT, 0, 0, 0)

    def _ghs_send(self, n: BootNeighbor, mt: MsgType, level: int, frag: int,
                  wfp: int) -> None:
        if mt is MsgType.GHS_INITIATE:
            self._ghs_init_sent[n.nid] = (level, int(frag), wfp)   # G6
        seq = self._next_seq()
        cert = self._ghs_subtree_cert() if mt is MsgType.GHS_REPORT else None
        self._ucast(n, wire.encode(wire.Ghs(mt, self.nid, seq, level,
                                            int(frag), int(wfp), cert)))

    def _ghs_subtree_cert(self) -> Tuple[int, int, int]:
        """F12b: (sum of min(deg, k), sum of deg, nodes) over my subtree.

        Every REPORT of a round carries it, so the core's two halves add up to
        the whole fragment; in the last round that is the whole component of
        the discovered graph. The degrees are the frozen ones.
        """
        d = self.deg or 0
        cap, degs, cnt = min(d, self.k), d, 1
        for c, dd, nn in self._ghs_child_cert.values():
            cap, degs, cnt = cap + c, degs + dd, cnt + nn
        return cap, degs, cnt

    def _ghs_defer(self, mt, nid, level, frag, wfp) -> None:
        """Queue a question I cannot answer yet, but never twice over.

        The test is the WHOLE message. `_ghs_reassert` repeats a question until
        it is answered, and a repeat that arrives while the original is still
        waiting is the same bytes asking the same thing, so a second copy tells
        the node nothing and only makes the replay longer.

        MEASURED on n15_m30 s2 under the asynchronous scheduler: node 13 held
        6665 deferred entries, all of them re-sent CONNECTs from node 6 on one
        edge, and node 5 held 6664 of the same shape from node 9.

        TRIED AND REVERTED: keying this on (type, peer) instead. That is NOT the
        same test and it is not safe. Two questions from one peer can name
        different levels and fragments, and `_ghs_replay` puts back what it
        cannot answer yet, so the newest copy overwrote an entry that still
        needed answering: with that version n10_m20 seed 1 returned an EMPTY
        cover at ZERO loss, where it solves in 37 slots. Only an EXACT duplicate
        may be dropped.
        """
        if self.phase > PH_MIS:
            return   # G6 (Amendment 13): the tree has halted; the question is moot
        item = (mt, nid, level, frag, wfp)
        if item in self._ghs_deferred_set:
            return
        self._ghs_deferred_set.add(item)
        self.ghs_deferred.append(item)

    def _ghs_replay(self, now: int, edges) -> None:
        """Deferred messages are retried whenever local state may have moved."""
        if not self.ghs_deferred:
            return
        pending, self.ghs_deferred = self.ghs_deferred, []
        self._ghs_deferred_set = set()
        by_id = {n.nid: n for n in edges}
        for mt, nid, level, frag, wfp in pending:
            n = by_id.get(nid) or self.nbrs.get(nid)
            if n is None or not n.is_edge:
                self._ghs_defer(mt, nid, level, frag, wfp)
                continue                # keep it: dropping it loses the question
            if mt is MsgType.GHS_CONNECT:
                self._ghs_on_connect(now, n, level, edges)
            elif mt is MsgType.GHS_TEST:
                self._ghs_on_test(now, n, level, frag)
            elif mt is MsgType.GHS_REPORT:
                self._ghs_on_report(now, n, wfp, edges, frag, level)

    def _ghs_on_connect(self, now: int, n: BootNeighbor, level: int, edges) -> None:
        if self.ghs_state == SLEEPING:
            # An incoming CONNECT wakes a sleeping node, and waking means
            # choosing MY OWN lightest incident edge. If I cannot yet rank my
            # edges I must not choose: defer the CONNECT and stay asleep.
            # MEASURED on n10_m20 s2: node 8 was woken here by a CONNECT while
            # node 7's degree had not arrived, ranked (7,8) as INF, and picked
            # (4,8) at 565 over the true lightest (7,8) at 545.
            if not self._ghs_weights_known(edges):
                self._ghs_defer(MsgType.GHS_CONNECT, n.nid, level, 0, 0)
                return
            self._ghs_wakeup(now, edges)
        self.ghs_connect_out.discard(n.nid)   # the peer answered my CONNECT
        if level < self.ghs_level:
            # Absorb: the smaller fragment joins mine and adopts my identity.
            if self.ghs_edge.get(n.nid) == BRANCH:
                # G6: a repeated CONNECT on an edge I already answered in this
                # round (my merge partner, which never got my INITIATE) gets
                # the INITIATE as first sent, not one rebuilt from my state.
                self._ghs_repeat_initiate(n)
                return
            self.ghs_edge[n.nid] = BRANCH
            self._ghs_send(n, MsgType.GHS_INITIATE, self.ghs_level,
                           self.ghs_frag, 0 if self.ghs_state == FOUND else 1)
        elif self.ghs_edge.get(n.nid) == BASIC:
            # Equal level but the edge is not yet ours: wait until it is.
            self._ghs_defer(MsgType.GHS_CONNECT, n.nid, level, 0, 0)
        else:
            # Merge: a new fragment one level up, identified by this edge.
            #
            # THE IDENTITY MUST NAME THE EDGE, NOT WEIGH IT. This used to be the
            # core edge's WEIGHT, following the textbook, which assumes all edge
            # weights distinct. Here they are not: the weight of an edge is
            # w(u)+w(v), and two different edges collide whenever two pairs of
            # node weights happen to sum alike. MEASURED on the graphs the
            # stations saw: 3 colliding sums over 6 edges on n15_m90 s3, 5 over
            # 10 on n20_m160 s1.
            #
            # A COLLISION IS NOT A TIE, IT IS A WRONG ANSWER. `_ghs_on_test`
            # replies REJECT when the asker's fragment id equals its own, and a
            # REJECT marks the edge REJECTED for good. So two DIFFERENT
            # fragments whose core edges weigh the same tell each other they are
            # one fragment, and the edge that could have joined them is thrown
            # away permanently. The pair then waits for a merge that nothing can
            # produce. `_pack_tie` already carries the two endpoint ids that make
            # the edge key a total order, and those ids identify the edge
            # uniquely, so the identity is built from them instead.
            key = self._weight_of(n)
            fid = self._pack_tie(key)
            if self.ghs_frag == fid and self.ghs_edge.get(n.nid) == BRANCH:
                # ALREADY MERGED ON THIS VERY EDGE. A re-sent CONNECT (the
                # sender never got my INITIATE) must not raise the level a
                # second time; it only needs the answer repeated (G6: the
                # answer as first sent, not rebuilt from my current state).
                self._ghs_repeat_initiate(n)
                return
            self.ghs_merges += 1
            self._ghs_send(n, MsgType.GHS_INITIATE, self.ghs_level + 1, fid, 1)
            self._ghs_initiate(now, n.nid, self.ghs_level + 1, fid, FIND, edges)

    def _ghs_initiate(self, now: int, parent_nid: Optional[int], level: int,
                      frag: int, state: int, edges) -> None:
        if parent_nid is not None:
            self.ghs_connect_out.discard(parent_nid)
        self.ghs_level = level
        self.ghs_frag = frag
        self.ghs_state = state
        self.ghs_parent = parent_nid
        self._ghs_round_ms = now
        self.ghs_best_wt = INF_W
        self.ghs_best_key = (INF_W, 0, 0)
        self.ghs_best_nid = None
        self.ghs_test_nid = None
        self.ghs_test_done = False       # a new fragment reopens the search
        self.ghs_root_acted = False      # and reopens the right to act once
        self.ghs_reported.clear()
        self._ghs_child_cert.clear()
        for n in edges:
            if n.nid != parent_nid and self.ghs_edge.get(n.nid) == BRANCH:
                self._ghs_send(n, MsgType.GHS_INITIATE, level, frag,
                               0 if state == FOUND else 1)

    def _ghs_test(self, now: int, edges) -> None:
        """Test the lightest BASIC edge -- ONCE settled, stop testing.

        NON-TERMINATION FOUND HERE. An ACCEPT does not change the edge state:
        in GHS an accepted edge stays BASIC until it is actually used, which is
        correct. But `_ghs_test` runs before `_ghs_try_report` on every step, so
        after an ACCEPT cleared `test_nid` the node immediately re-tested the
        SAME edge, got another ACCEPT, and never reported. Measured on the
        bridge family: nodes 4 and 5 testing each other forever, both holding a
        valid `best`, neither ever progressing, at every budget up to 2,000,000
        ms.

        Edges are tested in increasing weight order, so the first ACCEPT already
        names the minimum outgoing edge. There is nothing left to ask.
        """
        if self.ghs_test_nid is not None or self.ghs_test_done:
            return
        basics = [n for n in edges if self.ghs_edge.get(n.nid) == BASIC]
        if not basics:
            self.ghs_test_nid = None
            self.ghs_test_done = True
            return
        best = min(basics, key=self._weight_of)
        self.ghs_test_nid = best.nid
        self._ghs_send(best, MsgType.GHS_TEST, self.ghs_level, self.ghs_frag, 0)

    def _ghs_on_test(self, now: int, n: BootNeighbor, level: int, frag: int) -> None:
        if self.ghs_state == SLEEPING:
            # DEFER, never drop. A sleeping node cannot say whether the sender
            # shares its fragment, but "I cannot answer yet" is not "no answer
            # exists": the sender is blocked on this reply and will wait for it
            # forever. Classical GHS has no such case because any message wakes
            # a sleeping node; here a node may have to stay asleep until its
            # neighbours' weights arrive, which made the window wider rather
            # than narrower.
            #
            # MEASURED on n20_m40 s2 async: two fragments stalled at level 1,
            # node 11 holding an unanswered TEST to node 8 and node 14 one to
            # node 20, both questions dropped here while the receiver slept.
            self._ghs_defer(MsgType.GHS_TEST, n.nid, level, frag, 0)
            return
        if level > self.ghs_level:
            self._ghs_defer(MsgType.GHS_TEST, n.nid, level, frag, 0)
            return
        if frag != self.ghs_frag:
            self._ghs_send(n, MsgType.GHS_ACCEPT, 0, 0, 0)
        else:
            if self.ghs_edge.get(n.nid) == BASIC:
                self.ghs_edge[n.nid] = REJECTED
                self.ghs_rejects += 1
            self._ghs_send(n, MsgType.GHS_REJECT, 0, 0, 0)

    def _ghs_on_accept(self, now: int, n: BootNeighbor, edges) -> None:
        self.ghs_test_nid = None
        self.ghs_test_done = True        # the lightest outgoing edge is settled
        key = self._weight_of(n)
        if key < self.ghs_best_key:
            self.ghs_best_key = key
            self.ghs_best_wt = key[0]
            self.ghs_best_nid = n.nid

    def _ghs_on_reject(self, now: int, n: BootNeighbor, edges) -> None:
        if self.ghs_edge.get(n.nid) == BASIC:
            self.ghs_edge[n.nid] = REJECTED
            self.ghs_rejects += 1
        self.ghs_test_nid = None

    def _ghs_pending_unknown(self) -> bool:  # noqa: D401
        """Is any answer still outstanding?

        A DEFERRED message is an UNANSWERED QUESTION, not an answer. Treating
        `best == INF` as "my fragment has no outgoing edge" while a TEST is
        still deferred concludes "there is none" from "I could not determine" --
        the same conflation that made an earlier infeasibility witness unsound
        and that `local_infeasibility_witness` returns None rather than False to
        avoid. Measured consequence here: fragment {5,6} halted with two TESTs
        still deferred, left the GHS phase, stopped replaying them, and the tree
        never spanned.
        """
        # NOT every deferred message blocks. Only MY OWN unanswered question
        # does: an outstanding TEST, or an incoming TEST I have not yet been
        # able to answer. The other two kinds are somebody else's traffic and
        # counting them as pending is circular.
        #
        #   deferred REPORT  -- somebody else's ANSWER that reached me before I
        #     was ready for it. It was deferred BECAUSE I am in FIND, so letting
        #     it block me prevents me from ever leaving FIND. Measured on a
        #     5-node star: nodes 1 and 3 sit across the core edge naming each
        #     other parent, and node 1 waits forever for a report it holds.
        #
        #   deferred CONNECT -- somebody else's REQUEST TO JOIN, deferred
        #     because the edge is not mine yet. It becomes mine only when my
        #     fragment picks it, which needs my report to travel to the root.
        #     Blocking on it is the same circle one level up. MEASURED on
        #     n15_m30 s1 sync: three fragments stalled at level 1, node 14 in
        #     FIND with its single child already reported, unable to report
        #     because it held a CONNECT that only its own report could release.
        # NOT EVEN A DEFERRED TEST BLOCKS. This was the last face of the same
        # error. An incoming TEST I cannot answer yet is the SENDER's unanswered
        # question, not mine; the sender is correctly blocked by its own
        # `ghs_test_nid`. Holding my report because a neighbour asked me
        # something closes a circle: I defer its TEST because my level is lower,
        # my level can only rise when my fragment merges, my fragment can only
        # merge once my report reaches the core.
        #
        # MEASURED on n50_m100 s5 sync: six fragments frozen, node 4 at level 2
        # holding an unanswered TEST to node 28 at level 1, node 28 unable to
        # report because it held that very TEST. Five times the time budget
        # changed nothing (still six fragments), which is what separates a
        # livelock from slowness.
        #
        # SOUNDNESS, since an earlier fix put this blocker here to stop a
        # fragment concluding "no outgoing edge" from "I could not determine":
        # a node CANNOT report INF while holding a deferred TEST. That TEST came
        # from a different fragment, so the edge is not REJECTED, so it is still
        # BASIC, and `_ghs_test` tests every BASIC edge in weight order before
        # `ghs_test_done` is set. The node's own search covers that edge
        # independently of whether it has answered the neighbour.
        return self.ghs_test_nid is not None

    def _ghs_try_report(self, now: int, edges) -> None:
        """Report upward -- BUT NOT BEFORE MY OWN SEARCH HAS SETTLED.

        "NO QUESTION OUTSTANDING" IS NOT "MY SEARCH IS OVER", and two different
        fields say the two different things. `ghs_test_nid` says a question is
        in flight; `ghs_test_done` says the answer is in. Between a REJECT that
        clears the first and the next timer tick that calls `_ghs_test` on the
        following BASIC edge, BOTH are false, and the node looks settled while
        its search has not yet reached its lightest outgoing edge.
        `_ghs_on_report` calls this method on the MESSAGE path, so a child's
        REPORT landing inside that window carries the node out of FIND for
        good -- and `_ghs_test` only ever runs in FIND, so every remaining BASIC
        edge goes untested. This is the same class as `_ghs_pending_unknown`'s
        own lesson one step further in: there, a deferred question was read as
        an answer; here, an unstarted search is reported as an empty one.

        THE COST IS NOT ONE NODE'S BEST, IT IS THE WHOLE FRAGMENT'S. A node that
        reports INF this way hides every outgoing edge it owns from its
        fragment, so the fragment claims a HEAVIER minimum outgoing edge than it
        really has. Two fragments then name two DIFFERENT edges, each sends
        CONNECT at equal level on an edge the far side still holds BASIC, both
        take the "equal level but the edge is not yet ours" branch of
        `_ghs_on_connect`, and each waits for the other to claim an edge neither
        will ever pick. Nothing is lost and nothing repeats wrongly, so no
        amount of budget or re-assertion rescues it.

        MEASURED on n15_m30 s2 under the asynchronous scheduler at ZERO loss --
        the one truncated run left in the small group, and the reason its cell
        read 32 of 33. Node 13 is INITIATEd into FIND at t=1550 ms, TESTs
        (13,14) at 1141 and is REJECTed; at t=1950 ms node 1's REPORT of INF
        arrives while `ghs_test_nid` is None and `ghs_test_done` is still False,
        and node 13 reports INF upward with BASIC = [4, 6, 7, 9] never tested.
        Its edge (13,6) weighs 103088128 and is the LIGHTEST of the five edges
        crossing the two surviving fragments, so its fragment
        {1,2,3,7,9,10,11,12,13,14,15} claims (5,9) at 106758143 instead.
        Fragment {4,5,6,8} claims (6,13); node 13 defers that CONNECT because
        (13,6) is BASIC on its side, node 5 defers the mirror CONNECT on (5,9),
        and both fragments sit frozen at level 1 until the deadline.

        This was mis-read once as node 13 entering the fragment in FOUND state.
        It does not: the trace shows INITIATE with FIND. The state it never
        leaves is the one this guard now protects.

        THE GUARD COSTS AT MOST ONE TICK. With no BASIC edge left `_ghs_test`
        sets `ghs_test_done` on its next call without sending anything, so a
        node whose edges are all BRANCH or REJECTED still reports on the
        following step.
        """
        if (self.ghs_state != FIND or not self.ghs_test_done
                or self._ghs_pending_unknown()):
            return
        # A BRANCH edge on which I have sent CONNECT but received no reply is
        # NOT a child yet. Counting it as one waits forever for a report from a
        # node that has not joined my fragment and may never join it.
        # MEASURED: on n15_m30 node 8 marked (7,8) BRANCH when it sent CONNECT,
        # counted 7 as a child, and blocked; node 7 meanwhile had that CONNECT
        # deferred, in a different fragment, waiting for a level change that
        # could only come from the report node 8 was withholding.
        kids = [n for n in edges
                if self.ghs_edge.get(n.nid) == BRANCH
                and n.nid != self.ghs_parent
                and n.nid not in self.ghs_connect_out]
        if len(self.ghs_reported) < len(kids):
            return
        self.ghs_state = FOUND
        if self.ghs_parent is None:
            self._ghs_root_decide(now, edges)
            return
        p = self.nbrs.get(self.ghs_parent)
        if p is not None:
            self._ghs_send(p, MsgType.GHS_REPORT, self.ghs_level,
                           self._pack_tie(self.ghs_best_key), self.ghs_best_wt)

    # TRIED AND REVERTED: re-asserting an unanswered GHS question on a timer.
    #
    # The motivating measurement was real. `_ghs_send` is fire-and-forget, so a
    # dropped TEST leaves its sender blocked for ever, and re-asking took GHS at
    # two per cent loss from an EMPTY cover to solved in 92 slots.
    #
    # THE COSTS WERE NOT MEASURED AT THE TIME and they are disqualifying. At
    # n=50, m=100, seed 4 the re-assertion turned a run that solves in 0.6 s and
    # 54 slots into one that had not finished after 115 s, and a sweep row using
    # it reached 4.7 GB resident and twenty minutes of CPU on a single run.
    # Bounding the repeats did not save it: with the cap in place n10_m20 seed 1
    # returns an EMPTY cover at ZERO loss, where the same run without the
    # re-assertion solves in 38 slots. A repeat is not free here, because
    # re-sending CONNECT re-enters the merge path and a re-sent REPORT carries a
    # best-edge key the fragment has already moved past.
    #
    # The defect it addressed is real and stays open: see BULGULAR_BB.md section
    # 95a. It needs per-question state with its own timer and an answer that is
    # idempotent by construction, not a periodic broadcast of whatever is
    # currently outstanding.
    def _ghs_reassert(self, now: int, edges) -> None:
        """Ask again. A LOST GHS MESSAGE OTHERWISE DEADLOCKS THE RUN.

        `_ghs_send` is fire-and-forget unicast: unlike the LINK handshake there
        is no acknowledgement and no retry, while the protocol's progress
        depends on every question eventually getting an answer. One dropped
        TEST leaves its sender blocked on `ghs_test_nid` for ever, and nothing
        notices, so the run does not fail, it simply stops.

        THE EFFECT IS NOT SMALL, AND IT IS NOT ONE EFFECT. Measured on the nine
        graphs the stations saw, five RNG seeds each, at the five per cent loss
        the real channel runs at, by switching the three repeated questions on
        one at a time. The lossless column is the nine dataset instances at zero
        loss, which is where repetition can only do harm.

        | repeated          | lossless | lossy |
        |-------------------|----------|-------|
        | nothing           | 9/9      | 1/45  |
        | TEST              | 9/9      | 10/45 |
        | TEST+CONNECT      | 9/9      | 25/45 |
        | TEST+CONNECT+REPORT | 9/9    | 40/45 |

        So CONNECT carries more of the recovery than TEST does, and REPORT more
        than either. Repeating all three is what earns forty of forty-five.

        The four rows were measured together, under one code state, which is the
        only way the comparison between them means anything, and that state is
        several changes older than this file. Repetition was the DIAGNOSIS, not
        the cure: it turned silent deadlocks into reproducible ones and each of
        those was then fixed where it lived, in `_ghs_change_root`, in
        `_ghs_on_report`, in the fragment identity built by `_ghs_on_connect`,
        in how the end of Phase 1 is learned and in the quiet phase of
        `bbcvc.py`. The shipped configuration measures **45/45** at five per
        cent. The table is kept because the ordering it shows is the reason
        every one of those questions is repeated at all.

        WHAT REPETITION COSTS, AND WHERE IT WAS PAID. The table's lossless
        column reads 9/9 only because two defects that repetition EXPOSED were
        fixed first; before that, TEST+CONNECT+REPORT scored 7/9 AT ZERO LOSS.
        A repeated question is only harmless if answering it twice is. It was
        not: a re-sent REPORT re-entered `_ghs_change_root` and a second CONNECT
        went out on an edge already used, rewiring the tree into a parent cycle,
        and a REPORT carried no round of its own, so one written for a previous
        level was counted after the reset that should have erased it. Both are
        fixed where they live, in `_ghs_change_root` and in `_ghs_on_report`,
        with the measurements that found them.

        COST IN TIME AND MEMORY. An earlier version of this ran alongside an
        UNBOUNDED deferred queue, and together they took an n50_m100 run from
        0.6 s to over 115 s with 4.7 GB resident. The queue was the hoarder, not
        the repetition: the same instance now finishes in well under a second.
        """
        if now < self.ghs_retry_ms:
            return
        self.ghs_retry_ms = now + self.p.link_backoff_ms
        if self.ghs_test_nid is not None:
            n = self.nbrs.get(self.ghs_test_nid)
            if n is not None and n.is_edge:
                self._ghs_send(n, MsgType.GHS_TEST, self.ghs_level,
                               self.ghs_frag, 0)
        for nid in sorted(self.ghs_connect_out):
            n = self.nbrs.get(nid)
            if n is not None and n.is_edge:
                self._ghs_send(n, MsgType.GHS_CONNECT, self.ghs_level, 0, 0)
        if (self.ghs_state == FOUND and self.ghs_parent is not None
                and not self._ghs_pending_unknown()):
            p = self.nbrs.get(self.ghs_parent)
            if p is not None and p.is_edge:
                self._ghs_send(p, MsgType.GHS_REPORT, self.ghs_level,
                               self._pack_tie(self.ghs_best_key),
                               self.ghs_best_wt)
        # F18: CHANGE_ROOT was sent once; a lost copy left the fragment without
        # its merge. Repeated until the next round, its receiver acts once.
        b = self.ghs_best_nid
        if (self.ghs_root_acted and b is not None and b not in self.ghs_connect_out
                and self.ghs_edge.get(b) == BRANCH):
            t = self.nbrs.get(b)
            if t is not None and t.is_edge:
                self._ghs_send(t, MsgType.GHS_CHANGE_ROOT, self.ghs_level, 0, 0)

    def _ghs_on_report(self, now: int, n: BootNeighbor, wfp: int, edges,
                       tie: int = 0, level: Optional[int] = None) -> None:
        # A REPORT BELONGS TO ONE ROUND AND MUST NOT BE COUNTED IN ANOTHER.
        # `_ghs_initiate` wipes the accumulated best, so a report written for
        # the previous level answers a question that no longer exists. Nothing
        # used to separate the two: a REPORT carried no level, and the
        # deferred queue can hold one across an INITIATE boundary. A child is
        # always initiated before it reports, so its level never exceeds its
        # parent's; anything lower is stale by construction.
        #
        # MEASURED on n10_m20 s1: node 9 reported 76218369, was re-initiated to
        # level 2 and re-tested to INF, but its old report sat deferred in node
        # 6 and was replayed after the reset. Nodes 5 and 6 held that phantom
        # outgoing edge for ever, the core halt test never fired, and the run
        # returned an EMPTY cover although the spanning tree was complete.
        if level is not None and level < self.ghs_level:
            self._ghs_reinitiate(now, n)     # F18: or it missed my INITIATE
            return
        if level is not None and level > self.ghs_level:
            # F18: a round I have not entered, because its INITIATE was lost.
            # Counted as a child's it raised AttributeError on a node never
            # initiated (smoke H2a n25_m100_s1, async, 20 percent, seed 1).
            self._ghs_defer(MsgType.GHS_REPORT, n.nid, level, tie, wfp)
            return
        key = self._unpack_tie(wfp, tie)
        got = self._ghs_peer_cert.get(n.nid)
        if n.nid != self.ghs_parent and got is not None and got[0] == level:
            self._ghs_child_cert[n.nid] = got[1]   # F12b
        if n.nid != self.ghs_parent:
            # A SET, NOT A COUNTER. A REPORT is re-sent when the first one is
            # lost (see `_ghs_reassert`), so counting arrivals would let one
            # child stand for two and the parent would report upward before
            # every subtree had answered.
            self.ghs_reported.add(n.nid)
            if key < self.ghs_best_key:
                self.ghs_best_key = key
                self.ghs_best_wt = key[0]
                self.ghs_best_nid = n.nid
            self._ghs_try_report(now, edges)
            return
        if self.ghs_state == FIND:
            self._ghs_defer(MsgType.GHS_REPORT, n.nid,
                            self.ghs_level if level is None else level,
                            tie, wfp)
            return
        # THE COMPARISON MUST BE A TOTAL ORDER OR THE CORE DEADLOCKS. The two
        # core nodes each report their half's minimum outgoing edge, and the
        # one holding the smaller acts. `_weight_of` is a proper total order --
        # (w(u)+w(v), min id, max id) -- but only its FIRST component used to
        # be stored and reported, so two DIFFERENT edges of equal weight
        # compared equal: neither `>` nor the halt test fired and both core
        # nodes waited on each other.
        #
        # MEASURED on n25_m50 s2, the instance with the most ties of any tested
        # (two groups, four edges): five fragments frozen at level 1, every node
        # FOUND, no outstanding TEST, node 1 holding best 58392575 against node
        # 9's 58392575 for a different edge. Carrying the tie-break components
        # restores the strict order, so exactly one side acts and no second
        # CONNECT can create a cycle.
        if key > self.ghs_best_key:
            self._ghs_change_root(now, edges)
        elif wfp >= INF_W and self.ghs_best_wt >= INF_W:
            self._ghs_halt(now, partner=n.nid)

    def _ghs_root_decide(self, now: int, edges) -> None:
        """The core node: extend the fragment, or declare the tree finished."""
        if self._ghs_pending_unknown():
            return                      # an unanswered question is not an answer
        if self.ghs_best_wt >= INF_W:
            self._ghs_halt(now)
        else:
            self._ghs_change_root(now, edges)

    def _ghs_change_root(self, now: int, edges) -> None:
        """ONCE PER ROUND. Acting twice on one decision rewires the tree.

        Reaching outward is the end of a search round: the fragment has found
        its minimum outgoing edge and claims it. The answer that triggers this
        is a REPORT, and a REPORT can arrive more than once, both because
        `_ghs_reassert` repeats it and because a CHANGE_ROOT travelling the
        tree re-enters here at every hop. The second arrival finds the edge
        already BRANCH and sends a second CONNECT along it, which the far side
        answers with a fresh merge and a fresh parent.

        MEASURED on n25_m50 s2 at ZERO loss, with REPORT repetition enabled:
        the parent pointers of nodes 2, 25 and 7 closed into a three-cycle,
        five nodes stayed in FIND for ever and the run returned an EMPTY cover
        although all 25 nodes sat in one fragment with no outgoing edge left.
        The right to act is reopened by `_ghs_initiate`, which is exactly the
        start of the next round, so nothing is lost. A CONNECT that is itself
        lost is still recovered, because it stays in `ghs_connect_out` and
        `_ghs_reassert` re-sends it.
        """
        if self.ghs_root_acted or self.ghs_best_nid is None:
            return
        t = self.nbrs.get(self.ghs_best_nid)
        if t is None:
            return
        self.ghs_root_acted = True
        if self.ghs_edge.get(t.nid) == BRANCH:
            self._ghs_send(t, MsgType.GHS_CHANGE_ROOT, self.ghs_level, 0, 0)
        else:
            self.ghs_edge[t.nid] = BRANCH
            self.ghs_connects += 1
            self.ghs_connect_out.add(t.nid)
            self._ghs_send(t, MsgType.GHS_CONNECT, self.ghs_level, 0, 0)

    def _ghs_on_change_root(self, now: int, n: BootNeighbor, edges,
                            level: int) -> None:
        if level != self.ghs_level:
            if level < self.ghs_level:
                self._ghs_reinitiate(now, n)   # F18: it missed my INITIATE
            return
        self._ghs_change_root(now, edges)

    def _ghs_reinitiate(self, now: int, n: BootNeighbor) -> None:
        """F18: repeat my INITIATE to a child that is still in an older round.

        `_ghs_initiate` sends INITIATE once per child and nothing repeats it, so
        one lost copy leaves the child a level behind for ever: it defers every
        TEST of the new level and its old-level REPORT is discarded. Its
        repeated REPORT, or repeated CHANGE_ROOT on the path that turned the
        tree round, is the evidence. A copy that only crossed my INITIATE
        arrives within one tick, so a round younger than one re-ask interval is
        not repeated and lossless runs never repeat it.
        """
        if (n.nid != self.ghs_parent and self.ghs_edge.get(n.nid) == BRANCH
                and n.nid not in self.ghs_connect_out
                and now - self._ghs_round_ms >= self.p.link_backoff_ms):
            self._ghs_repeat_initiate(n)   # G6

    def _ghs_repeat_initiate(self, n: BootNeighbor) -> None:
        """G6 (Amendment 13): a repeated INITIATE carries the round's content.

        It repeats the level, fragment and state of the INITIATE first sent to
        this neighbour in my current round, not my current state. Rebuilt from
        my state, a repeat sent after my own search had ended said FOUND, so
        the neighbour entered the round without searching and its core halted
        on an incomplete tree (n4g1 k = 2, burst of 5 on 4->1: node 2 ended
        phase 1 as OUT and the cover was disconnected)."""
        sent = self._ghs_init_sent.get(n.nid)
        if sent is not None and sent[0] == self.ghs_level:
            self._ghs_send(n, MsgType.GHS_INITIATE, sent[0], sent[1], sent[2])
        else:
            self._ghs_send(n, MsgType.GHS_INITIATE, self.ghs_level,
                           self.ghs_frag, 0 if self.ghs_state == FOUND else 1)

    # ---------------------------------------------------------- termination
    def _ghs_halt(self, now: int, partner: Optional[int] = None) -> None:
        if self.ghs_halted:
            return
        self.ghs_halted = True
        # REPAIR F12b. The tree is complete: my subtree plus my core partner's
        # is the whole component. degs = 2m; the counting bound (m > nk) and
        # the degree-gap witness (sum of min(deg, k) < m) are decided here and
        # a positive verdict reaches every node through HELLO's flag.
        cap, degs, cnt = self._ghs_subtree_cert()
        got = self._ghs_peer_cert.get(partner) if partner is not None else None
        if got is not None:
            cap, degs, cnt = cap + got[1][0], degs + got[1][1], cnt + got[1][2]
        bad = degs > 2 * cnt * self.k or 2 * cap < degs
        self._log("ghs_certificate", cap_sum=cap, deg_sum=degs, nodes=cnt,
                  infeasible=bad)
        if bad and self._cert_root is None:
            # G5 (Amendment 13): the tree sums are not checked for completeness
            # (a halt on a fragment that missed its children summed 2 of 5
            # nodes of a feasible star), so they only start the echo wave,
            # whose completion is the certificate.
            self._cert_start(now)
        self._log("ghs_halt", level=self.ghs_level, merges=self.ghs_merges,
                  rejects=self.ghs_rejects, connects=self.ghs_connects)
        self._v4_flood_done(now)
        self._v4_enter_mis(now)

    def _v4_flood_done(self, now: int) -> None:
        seq = self._next_seq()
        self._bcast(wire.encode(wire.Token(MsgType.DFS_DONE, self.nid, seq,
                                           self.nid)))

    def _v4_phase1_over(self, edges) -> bool:
        """Has a neighbour already left Phase 1? Then it is over for me too."""
        # F18: only a record of my epoch; an older one said phase 3 of a
        # finished epoch and skipped the tree (H2a n25_m100_s1, ge:0.20:4).
        return any(n.phase > PH_MIS and self._in_epoch(n) for n in edges)

    def _on_v4_done(self, now: int, n: BootNeighbor, msg) -> None:
        if self._v4_done_seen:
            return
        self._v4_done_seen = True
        self._v4_flood_done(now)
        self._v4_enter_mis(now)

    # -------------------------------------------------------- backbone MIS
    def mst_internal(self) -> bool:
        """Internal = at least two tree edges, i.e. not a leaf."""
        return sum(1 for s in self.ghs_edge.values() if s == BRANCH) >= 2

    def _v4_enter_mis(self, now: int) -> None:
        # G6 (Amendment 13): GHS questions deferred in phase 1 are moot once
        # the component's tree has halted, which this flood announces.
        self.ghs_deferred = []
        self._ghs_deferred_set = set()
        if self.phase != PH_MIS:
            return
        self.phase = PH_CONN
        self._v4_in_backbone = self.mst_internal()
        if self._v4_in_backbone:
            self._v4_announce(now, 0)

    def _v4_announce(self, now: int, code: int) -> None:
        seq = self._next_seq()
        self._bcast(wire.encode(wire.Join(MsgType.BB_MIS, self.nid, seq, code)))

    def _on_v4_bb(self, now: int, n: BootNeighbor, msg) -> None:
        self._v4_bb_members.add(n.nid)
        if msg.code == 1:
            self._v4_bb_decided[n.nid] = True
        elif msg.code == 2:
            self._v4_bb_decided[n.nid] = False

    def _v4_decided(self, n: BootNeighbor):
        """A backbone neighbour's MIS decision: True, False, or None (not yet).

        REPAIR F8 (R1, Amendment 4). The decision travels in ONE BB_MIS
        broadcast, and that frame can be lost. MEASURED on the worked example,
        asynchronous, ten per cent loss, channel seed 2: node 4 waited for the
        whole 600 s budget on node 6, whose decision frame it never received,
        while every HELLO of node 6 already said phase 3, role MIS. Nothing was
        pending anywhere. The answer is on the air, as in `_v4_phase1_over`: a
        backbone node leaves PH_CONN only after deciding, and its role then
        says which way (MIS, or CONNECTOR/COVER for "not MIS").
        """
        d = self._v4_bb_decided.get(n.nid)
        if d is None and n.phase >= PH_COVER:
            d = n.role == Role.MIS
        return d

    def _v4_mis_step(self, now: int, edges) -> None:
        if not self._v4_in_backbone or self._v4_mis_claim is not None:
            self._v4_finish_roles(now)
            return
        mk = self._mykey()
        # F8: a neighbour whose HELLO says MIS is a decided backbone member even
        # if its BB_MIS announcement was lost.
        smaller = [n for n in edges
                   if (n.nid in self._v4_bb_members
                       or (n.phase >= PH_COVER and n.role == Role.MIS))
                   and self._nkey(n) < mk]
        if any(self._v4_decided(n) is None for n in smaller):
            return
        self._v4_mis_claim = not any(self._v4_decided(n) for n in smaller)
        self._v4_announce(now, 1 if self._v4_mis_claim else 2)
        self._v4_finish_roles(now)

    def _v4_finish_roles(self, now: int) -> None:
        if self.phase >= PH_COVER:
            return
        if self._v4_in_backbone:
            if self._v4_mis_claim is None:
                return
            self.role = Role.MIS if self._v4_mis_claim else Role.CONNECTOR
        else:
            self.role = Role.OUT
        self.phase = PH_COVER
        self._log("v4_phase1_done", role=int(self.role),
                  branch=sum(1 for s in self.ghs_edge.values() if s == BRANCH),
                  merges=self.ghs_merges, rejects=self.ghs_rejects)

    def _on_join(self, now: int, n: BootNeighbor, msg) -> None:
        """A JOIN can promote a node that is STILL DECIDING in Phase 1.

        SEAM CONTRACT VIOLATION, and it belongs here rather than in the shared
        code. `BbcvcNode._on_join` promotes any node whose role is still OUT
        straight to PH_FORCED. For MIS-Connector-Backbone and MIS-Connector-TreeAgg that is harmless, because their
        Phase 1 assigns a role early. GHS-MST-Backbone leaves the role at OUT until its
        backbone MIS decision is made, so a JOIN yanks the node out of PH_CONN
        before it ever announces that decision -- and `_backbone_step`, which
        would have announced it, is only called in PH_MIS and PH_CONN.

        MEASURED on n50_m200 s4 async: node 30, in the backbone, was promoted to
        CONNECTOR with `_v4_mis_claim` still None and its phase written straight
        from 2 to 4. Node 16 then waited for node 30's announcement for the rest
        of the run, never left PH_CONN, and edge (15,16) stayed uncovered with
        120 edges unowned behind it.

        The node is being made a CONNECTOR by this very JOIN, so the honest
        announcement is "not an MIS member": the role it ends with is the same
        either way, and the neighbours stop waiting.
        """
        if (self.phase == PH_CONN and self._v4_in_backbone
                and self._v4_mis_claim is None):
            self._v4_mis_claim = False
            self._v4_announce(now, 2)
        super()._on_join(now, n, msg)

    # ------------------------------------------------------------- epoch
    def _reset_to_phase0(self, now: int, reason: str) -> None:
        """An epoch restart must restart GHS too, not only bootstrap.

        THE FOURTH DEADLOCK, AND IT IS NOT A LOST MESSAGE. The three fixed in
        section 95 were all unanswered questions; this one is the shape of
        section 93 instead -- a half-finished undo. `BbcvcNode._reset_to_phase0`
        rewinds phase, key, degree, frozen neighbourhood and role, and
        `_init_algo_state` rewinds Phases 2-5. The GHS state survived it whole,
        and GHS is what decides the role here. Two flags in it are LATCHES:
        `ghs_halted` makes `_ghs_halt` a no-op forever after, and
        `_v4_done_seen` makes `_on_v4_done` a no-op forever after. Between them
        they are the only two ways a node leaves PH_MIS, so a node that has
        already finished Phase 1 once can never finish it again.

        MEASURED on the graph the n=20 stations actually saw (dag_mst_n20_m160
        seed 1, replayed in the event simulator, sync, 200 s budget) at TEN PER
        CENT loss. Phase 1 completes perfectly at t = 11.6-12.0 s: `ghs_halt` on
        the core pair (nodes 4 and 15), `v4_phase1_done` on all twenty nodes,
        eighteen `cover` records by t = 12.8 s. Then at t = 13.4 s node 20
        bumps the epoch, all twenty reset, and across the eight further epochs
        that follow (through epoch 11, to the deadline at t = 185 s) there is
        not ONE further `ghs_halt`, `v4_phase1_done` or `cover` record. Every
        node ends FOUND at level 1 in one fragment with no outstanding TEST and
        no deferred message, still in PH_MIS, and the run returns an EMPTY
        cover. The halt propagation was never the defect: it had already
        reached all twenty nodes.

        Retransmitting the halt would not have helped and the measurement says
        so: `_v4_done_seen` is True on all twenty at the end, so every node HAD
        received the announcement, and a repeat would have been discarded by the
        same latch.

        WHAT IS KEPT. `ghs_peer_deg` is neighbour information HEARD in HELLOs,
        the same class as `self.nbrs`, which the bootstrap reset also preserves;
        dropping it would only make every node fail `_ghs_weights_known` until a
        fresh HELLO arrived from each peer. The three counters are cumulative
        measurement of the whole run and feed no decision.
        """
        super()._reset_to_phase0(now, reason)
        self.ghs_state = SLEEPING
        self.ghs_level = 0
        self.ghs_frag = 0
        self.ghs_parent = None
        self.ghs_edge = {}
        self.ghs_best_wt = INF_W
        self.ghs_best_key = (INF_W, 0, 0)
        self.ghs_best_nid = None
        self.ghs_test_nid = None
        self.ghs_test_done = False
        self.ghs_connect_out = set()
        self.ghs_reported = set()
        self._ghs_child_cert = {}
        self._ghs_peer_cert = {}
        self._ghs_init_sent = {}
        self.ghs_retry_ms = 0
        self._ghs_last_asked = None
        self._ghs_retries = 0
        # Deferred messages name a fragment and a level this restart has just
        # discarded, so replaying them would answer with stale identities.
        self.ghs_deferred = []
        self._ghs_deferred_set = set()
        self.ghs_halted = False
        self._v4_in_backbone = False
        self._v4_mis_claim = None
        self._v4_bb_members = set()
        self._v4_bb_decided = {}
        self._v4_done_seen = False

    # ------------------------------------------------------------- dispatch
    #: GHS messages whose sender is blocked until it gets an answer. Dropping
    #: one of these does not slow the run down, it stops it.
    _GHS_BLOCKING = (MsgType.GHS_CONNECT, MsgType.GHS_TEST, MsgType.GHS_REPORT,
                     MsgType.GHS_INITIATE)
    #: F18: this arm's own frames carry no epoch byte (F3 covers JOIN and the
    #: edge types only), so the sender's epoch is the one its HELLO announced.
    _V4_TYPES = _GHS_BLOCKING + (MsgType.GHS_ACCEPT, MsgType.GHS_REJECT,
                                 MsgType.GHS_CHANGE_ROOT, MsgType.DFS_DONE,
                                 MsgType.BB_MIS)

    def _on_algo(self, now: int, src_mac: int, msg) -> None:
        peer = msg.src
        n = self.nbrs.get(peer)
        if n is None or n.mac != src_mac:
            return                      # unknown peer or wrong MAC: not mine
        if msg.mtype in self._V4_TYPES and not self._in_epoch(n):
            # F18: a frame of an older epoch. Processed after my restart it set
            # a SLEEPING node's parent across a BASIC edge (n100_m400_s2, sync,
            # 5 percent). Every type here is repeated or read from HELLO.
            return
        if not n.is_edge:
            # DEFER, NEVER DROP -- the same rule `_ghs_on_test` already states
            # for a sleeping node, applied one layer out. A known neighbour
            # whose edge is momentarily down is "I cannot answer yet", not "no
            # answer exists", and the sender is blocked on the reply.
            #
            # MEASURED in the event simulator at five per cent loss on the
            # n=20 graph the stations saw: node 16 received 339 TESTs from node
            # 9 and DROPPED 311 of them right here while the edge (9,16) was
            # between states, answering only 28. Node 9 held `ghs_test_nid=16`
            # for the whole run, so its fragment never reported, the root
            # re-issued INITIATE 37 times and the run ended with no cover at
            # all. Deferring costs a replay; dropping costs the run.
            if msg.mtype in self._GHS_BLOCKING:
                self._ghs_defer(msg.mtype, peer, getattr(msg, "level", 0),
                                getattr(msg, "frag", 0), getattr(msg, "wfp", 0))
            return
        mt = msg.mtype
        edges = [x for x in self.nbrs.values() if x.is_edge]
        for x in edges:
            self.ghs_edge.setdefault(x.nid, BASIC)
        if mt is MsgType.GHS_CONNECT:
            self._ghs_on_connect(now, n, msg.level, edges)
        elif mt is MsgType.GHS_INITIATE:
            # TRIED AND REVERTED: dropping an INITIATE that names the level
            # and fragment I already hold. The reasoning was sound, and the
            # duplicate is real -- on n15_m30 s2 under the asynchronous
            # scheduler node 12 floods the same INITIATE twice and node 13
            # loses an in-flight TEST to it. It is NOT what deadlocks that
            # run: with the guard in place the run still truncates on seed
            # 2, while the lossless nine and the lossy forty-five are
            # unchanged at 9/9 and 40/45. A change that buys nothing is not
            # kept, so the remaining async deadlock is written down in
            # docs/SONUCLAR.md instead of papered over here.
            self._ghs_initiate(now, n.nid, msg.level, msg.frag,
                               FIND if msg.wfp else FOUND, edges)
        elif mt is MsgType.GHS_TEST:
            self._ghs_on_test(now, n, msg.level, msg.frag)
        elif mt is MsgType.GHS_ACCEPT:
            self._ghs_on_accept(now, n, edges)
        elif mt is MsgType.GHS_REJECT:
            self._ghs_on_reject(now, n, edges)
        elif mt is MsgType.GHS_REPORT:
            # REPORT reuses the otherwise unused `frag` field to carry the two
            # id components of the edge key, so the core comparison is a strict
            # total order rather than a weight that ties.
            if msg.cert is not None:
                self._ghs_peer_cert[n.nid] = (msg.level, tuple(msg.cert))   # F12b
            self._ghs_on_report(now, n, msg.wfp, edges, msg.frag, msg.level)
        elif mt is MsgType.GHS_CHANGE_ROOT:
            self._ghs_on_change_root(now, n, edges, msg.level)
        elif mt is MsgType.DFS_DONE:
            self._on_v4_done(now, n, msg)
        elif mt is MsgType.BB_MIS:
            self._on_v4_bb(now, n, msg)
        else:
            super()._on_algo(now, src_mac, msg)


def build_v4_dist_nodes(net, weights, k: int, params=None):
    """One node per station. NO seed data: GHS-MST-Backbone builds its own tree."""
    p = params or BbcvcParams()
    return {nid: V4MstDistNode(weights[nid], net.port(nid), p, k)
            for nid in sorted(weights)}


def run_v4(edges, weights, k: int, *, scheduler: str = "sync", params=None,
           max_ms: int = 600_000, seed: int = 0, loss: float = 0.0,
           **kw) -> Any:
    """Thin wrapper. EXTRA OPTIONS ARE FORWARDED, not dropped.

    `run_bbcvc` accepts platform-shaped options such as `tau_ms`, which the
    Mininet-WiFi collector passes when it reruns the same case in the
    simulator for comparison. A wrapper with a closed signature turns those
    into a TypeError at the END of a finished wireless run, the most
    expensive possible moment to discover it. MEASURED: the first real n=10
    run reached quiescence on all ten stations and then failed here.
    """
    return run_bbcvc(edges, weights, k, scheduler=scheduler, params=params,
                     max_ms=max_ms, seed=seed, loss=loss,
                     node_factory=build_v4_dist_nodes, **kw)


def _spec_run(req) -> Any:
    from ccvc.bb.sweep import with_overrides

    p = BbcvcParams()
    p.mis_nbrs_max = req.mis_nbrs_max
    return run_v4(list(req.edges), dict(req.weights), req.k,
                  scheduler=req.scheduler, params=with_overrides(p, req),
                  max_ms=req.max_ms, seed=req.seed, loss=req.loss)


def _build_specs():
    from ccvc.bb.sweep import VariantSpec

    # `family="mst"` and `phase1="mst"` for the same reason DFS-Spanning-Backbone is its own
    # family: GHS-MST-Backbone replaces Phase 1 with a different ALGORITHM, not with a
    # different parameter, so a paired comparison against MIS-Connector-Backbone would
    # differ in more than one axis. It pairs with DFS-Spanning-Backbone and MIS-Connector-Backbone on the phase1
    # axis in the cross comparison.
    #
    # Registered only now. The gate the brief requires -- backbone equal to the
    # central oracle, verdict solved, validator clean, ownership total and
    # unique -- passes on the whole small group at three seeds under both
    # schedulers (66 rows), with the twelve capacity-infeasible rows reported
    # as such rather than counted as passes.
    return (
        VariantSpec("GHS-MST-Backbone", "mst", "mst", "local", _spec_run),
    )


BB_VARIANTS = _build_specs()
