#!/usr/bin/env python3
"""BB-CVC: backbone-based connected vertex cover, ONE event-driven node body.

Sources
  plan/BB-CVC_Algoritma_Ornekli_Anlatim.tex  (Phases 1a/1b/2/3/4/5, "full state machine")
  plan/MWCCVC_DAGITIK_TASARIM_BRIEF.md       (S2 structural facts, S4 normative summary)
  ccvc/bb/api.py                             (the contract; not modifiable)

CENTRAL PRINCIPLE. Five phases live in one body: `on_frame` and `on_timer` are
written once. `SyncScheduler` and `AsyncScheduler` are TWO CLOCKS over that body,
not two algorithms. The word "slot" does not appear in this file and no branch
inspects the scheduling mode; the only time a node sees is `Platform.now_ms()`.

BUILT ON BOOTSTRAP. Neighbour discovery, bidirectional verification, RSSI
hysteresis, the stability gate, key freezing and epoch handling all live in
`BootstrapNode` and are NOT REWRITTEN HERE. This class derives from it and
changes exactly three things:
  1. serialization moves to `wire.py` (bootstrap's private codec is not used;
     opening a second copy is forbidden),
  2. the HELLO gains populated `mis_nbrs` and `load` fields,
  3. the five-phase state machine (`_step`) is appended to `on_timer`.

PHASE NUMBERS (same as the .tex "full state machine"; DONE has two stages)
  0 BOOT    neighbour discovery; advances to 1 once bootstrap freezes the key
  1 MIS     Phase 1a rule runs; advances to 2 once the decision is FINAL
  2 CONN    Phase 1b connector rule (local barrier: all neighbours >= 2)
  3 COVER   Phase 2 cover extension (message-free)
  4 FORCED  Phase 3 forced load; advances to 5 once F(v) <= k
  5 OWN     Phase 4 flexible edge ownership
  6 QUIET   Phase 5a: no state change for T_q, load <= k, nothing pending
  7 DONE    Phase 5a: every neighbour is at >= QUIET

  The .tex describes a single DONE ("unchanged for T AND all neighbours DONE").
  Read literally that deadlocks: nobody can be the first to declare DONE. The
  .tex's own worked example describes two stages (a "quiescent" flag, then DONE),
  so QUIET and DONE are separate here. The divergence has been REPORTED.

ACCOUNTING ORDER (bb-core's second trap). `by_phase_tx` reads `node.phase` AT
SEND TIME. CHOICE: advance the phase first, then transmit. A frame is therefore
attributed to the phase it CARRIES; the HELLO announcing "I am now in phase 3"
counts against phase 3, and a unicast produced by a rule counts against that
rule's phase. This order is established in exactly one place inside `on_timer`
(`_step` then `_maybe_hello`) and is not broken anywhere.

RETX (bb-core's first trap). Every retransmission is reported via
`log("retx", n=1)`; the network layer keeps the counter. One place only:
`_retry_pending`.

DETERMINISM (third trap). THERE IS NO RNG. Every tie is broken on the key
(key_fp, id) and every traversal runs over sorted ids.

PHASE 4'S LOCALITY LIMIT (MEASURED NEGATIVE RESULT, will not be repaired).

There is a class of infeasibility that capacity repair CANNOT find, and it is
not a shortcoming of this implementation but A PROPERTY OF THE PROBLEM UNDER
LOCALITY. Concrete instance (figures.udg_instance(100, 0.15, 4), k=4):

  * no node is overloaded; the maximum forced load is 2 against k=4. So EVERY
    trigger keyed on F(v) > k is structurally BLIND to this class; F(v) > k is
    a NECESSARY condition for trouble and never a sufficient detector of it.
  * the cover is nonetheless capacity-infeasible: there is a Hakimi orientation
    contradiction over 242 flexible edges (brief G5), i.e. some subset S has
    |E(S)| > k|S| and no orientation can hold in-degree <= k.
  * the obstruction spans 13 HOPS inside G[C]. No ball at radius 1 through 4
    shows any counting violation; |E(S)| - budget(S) is -4 at radius 1 and grows
    MORE negative as the radius grows (measured by the team lead).
  * the deficiency is tiny: only 2 of 242 edges are left unplaceable, and
    EXACTLY ONE of the 11 outside nodes (node 78) resolves it when added.

Conclusion: no NEIGHBOURHOOD-SHAPED predicate can see this at any radius. Stage
3b's relayed escalation reaches two hops and is SILENT on this class; it has to
be, because there is no signal it could observe. Therefore the `relay_escalate`
counter is NOT a complete measure of "Phase 4 could not repair it": it reads
zero here. The two failure modes must be reported in separate columns and never
summed.

Returning `unresolved` in this situation IS THE CORRECT ANSWER: it is the most
accurate response available to the question a node is able to ask. Patching it
would require the global information this project has refused to use throughout.

R1 UPDATE (repair F11b, Amendment 8). The diagnosis above stands: no local
predicate sees this class. What changed is the reach of the repair, not its
information. A node whose deepest push failed relays an invitation through the
cover, one hop at a time, to a cover node that has an outside neighbour, which
invites it (`_far_step`). No node learns anything global. On this instance the
synchronous run now invites one outside node through four relays and ends
solved and valid with |C| = 90; on n200_m1200 s3 and s10 the spanning-tree arm,
whose cover lacked one node three hops away, now ends valid as well.

R1 REPAIRS (pre-registered, paper/CoverWeave_R1/contract/R1_PREREG.md, Amendment 1).
A proof audit showed by fault injection on the worked example that three lost
JOIN copies stall a run, three lost HANDOVER_ACK copies leave a doubly owned
edge, and a lost DONE HELLO plus its one answer leave beaconing that never
stops. The repairs, each with its regression test in test_r1_repairs.py:
  F1 `_retry_pending`: HANDOVER and PUSH are retransmitted with capped backoff
     until a reply arrives; a JOIN is re-armed after its give-up, so the rule
     that sent it sends it again while its trigger holds.
  F2 `_answer_a_neighbour_still_waiting`: HELLO carries an open-barrier flag and
     a DONE node answers every open-flag beacon at most once per stale window.
  F3 `_on_algo`: JOIN and edge messages carry the epoch; another epoch's frame
     is dropped.
  F4 `_nbrs_active` / `_view_stale`: decisions read the epoch's frozen view, and
     a frozen neighbour without a live verified record means wait.
  F5 `_seen_put`: the duplicate-reply cache keeps SEEN_PER_PEER replies per peer.
Amendment 4 adds two more:
  F7 `_refuse`: a request from a peer I hear but have not verified is answered
     with a refusal, so a request is always answered under one-way gates.
  F8 (v4_mst.py) is the spanning-tree arm's own repair.
Amendment 6: F9, one stale window per neighbour, lives in bootstrap.py.
Amendment 7 adds:
  F10 `_finish_push_job`: a push chain that outlived its sender's timeout (the
     sender got a busy NACK) ends with a LATE acknowledgement, and that one is
     a request: it is repeated until the sender confirms it (`LATE_ASK`,
     `LATE_CONFIRM`), so losing it can no longer leave both ends owning the edge.
  F13 `_quiescence` / `_expire`: a neighbour I hear but have not verified yet
     keeps me from DONE until it is verified or silent for its stale window
     (counted in its slowest beacon rate, `_quiet_window_ms`), so the LINK
     retry comes before the verdict; and a QUIET node, or a DONE node whose
     barrier is open, expires a silent neighbour, so a node removed while any
     neighbour still transmits is detected and the epoch restarts.
  F12b (v4_mst.py): the spanning-tree arm's final GHS REPORT wave sums
     min(deg, k), deg and the node count; the core applies the counting bound
     and the degree-gap witness, and HELLO's flag carries a positive verdict
     to every node (`_certify`), which then reports unresolved without
     repairing. Every other arm keeps the run-level check.
  F11b `_far_step`: when even the deepest push failed, an invitation is relayed
     through the cover (depth first, one search per node and epoch, every
     relay a persistent epoch-tagged request) to a cover node with an outside
     neighbour, which invites it; the origin then deepens once more.
  F17 `_cert_start` / `_on_cert`: the first node that uses up its repair
     rounds starts an echo wave over the discovered graph (the smallest
     initiator wins); the wave sums min(deg, k) and deg over every node, and its
     initiator applies the degree-gap witness, which fires on every instance
     the counting bound rejects. A positive verdict reaches every node through
     HELLO's flag and every node then reports unresolved instead of repairing
     (F12b's rule), so no futile deepening runs on an instance the witness
     proves infeasible. CERT is repeated until answered, like every request.
  F11 `_fix_overload`: when the repair rounds are used up, the push depth is
     raised step by step, each step a fresh round at twice the depth, up to an
     upper bound on the number of nodes (`n_bound`), before the node reports
     unresolved.
Amendment 9 adds:
  F15 `_confirm_state`: a role or forced load that a node announces after its
     DONE HELLO is final for ownership only once every frozen neighbour has
     echoed it in a HELLO. Until then the node is not done and its barrier
     stays open, and it asks again once per stale window; a DONE node, closed
     or not, echoes at once and announces at once a change of its own.
  F14 `_repeated`: a HANDOVER, PUSH or relay JOIN that missed the reply cache
     and is at or below its sender's highest executed seq is answered from the
     receiver's state and not executed, so an evicted duplicate changes nothing.
  F14b `_has_room`: a copy of the PUSH my chain still serves changes nothing
     but by taking the edge, a failed chain acknowledges an edge such a copy
     took instead of refusing it, and `_fix_overload` waits rather than offer
     an edge to a neighbour that still has its earlier offer open (a chain
     probe moves `_fix_key`, so the gate alone did not hold one per neighbour).
     A copy refused by F7 sets the busy flag of F10 like a busy refusal.
Amendment 10 adds:
  F16b `_handoff_open`: a node that expires a neighbour it held as DONE keeps
     its barrier open and announces its epoch until it hears that neighbour in
     it or twice the stale cap has passed since its latest restart.
"""
from __future__ import annotations

import copy
import itertools
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from ccvc.bb import wire
except ImportError:  # direct execution
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    from ccvc.bb import wire

from ccvc.bb.api import Counters, MsgType, NodeSnapshot, Platform, Role, to_fp
from ccvc.bb.bootstrap import (MAC_MASK, BootNeighbor, BootstrapNode,
                               BootstrapParams, RunInvalid, hash16,
                               validate_bootstrap)

Edge = Tuple[int, int]

#: Phase 5b sentinel for "no root / no parent". wire.Tree and wire.Finish carry
#: root and parent as plain 16-bit numbers and cannot carry Optional, so a
#: sentinel value is required.
#:
#: THIS DEPENDS ON AN INVARIANT HELD IN ANOTHER FILE, which is why it is named
#: here: `bootstrap.hash16` RESERVES 0 (`return folded if folded else 1`), so no
#: node id can be 0 and 0 can never be confused with a real root.
#:
#: THE PRESSURE IS REAL. All 310 benchmark instances are 0-indexed, so
#: `mac_for_id(0)` has no preimage and the first instinct is "let us free 0 in
#: hash16". IT MUST NOT BE FREED: the moment it is, a tree whose root is 0
#: becomes indistinguishable from "no root", silently, in THIS file.
#: bb-bootstrap did the right thing and relabelled in the benchmark harness.
#: `_tree_send` additionally checks this invariant AT RUNTIME: if 0 is ever
#: freed you get a noisy error rather than a wrong answer.
_TREE_NO_NODE = 0

#: Where an unfrozen key sorts: above every real key. Real keys are 16.16
#: fixed point and therefore stay below 2^31.
_KEY_INF = 1 << 62

#: Replies kept per peer for duplicate replay (repair F5), so the cache stays
#: O(deg) instead of growing per request. No constant covers every request a
#: peer can still be retransmitting: old JOINs of three reasons, a relayed
#: escalation and invitation, its own transfer, a chain probe and, while copy
#: after copy is lost, any number of later requests can arrive between two
#: copies. An evicted duplicate is caught by the per-peer mark of repair F14.
SEEN_PER_PEER = 4

#: Repair F10. The ttl byte of a PUSH_ACK, which is otherwise always 0, says
#: whether it is a late acknowledgement that wants a confirmation (LATE_ASK)
#: or that confirmation itself (LATE_CONFIRM). The frame keeps its 11 B.
LATE_ASK = 1
LATE_CONFIRM = 2
#: A late acknowledgement waits in `_pending` under (peer, _LATE_KEY | seq).
#: Its seq is the PEER's request seq, so the flag keeps it apart from my own
#: requests to that peer, whose seqs stay below 2^16.
_LATE_KEY = 1 << 16

# --------------------------------------------------------------------------
# phases
# --------------------------------------------------------------------------
PH_BOOT = 0
PH_MIS = 1
PH_CONN = 2
PH_COVER = 3
PH_FORCED = 4
PH_OWN = 5
PH_QUIET = 6
PH_DONE = 7

PHASE_NAMES = {PH_BOOT: "boot", PH_MIS: "mis", PH_CONN: "conn", PH_COVER: "cover",
               PH_FORCED: "forced", PH_OWN: "own", PH_QUIET: "quiet", PH_DONE: "done"}

# JOIN reasons (wire.Join.code)
JOIN_CONNECTOR = 1   # Phase 1b, 3-hop gap
JOIN_FORCED = 2      # Phase 3, forced-load overflow
JOIN_ESCALATE = 3    # Phase 4, stage 3 escalation
JOIN_RELAY = 4       # Phase 4, stage 3b: "escalate on my behalf" (see below)
JOIN_FAR = 5         # Phase 4, F11b: relayed through the cover to an outside node


def edge(u: int, v: int) -> Edge:
    return (u, v) if u <= v else (v, u)


def counting_bound_infeasible(n: int, m: int, k: int) -> bool:
    """The CHEAPEST but most certain witness: is total capacity below |E|?

    Every edge must have an owner and every node owns at most k edges, so the
    TOTAL capacity in the graph is n*k. If m > n*k then no cover, of any shape,
    in any order, can work. The brief's G6 lower bound (|C| >= ceil(m/k)) is the
    same fact in its most degenerate form: ceil(m/k) > n.

    SCOPE WARNING, written deliberately. This is a RUN-LEVEL check, not a
    node-level one: n and m are global quantities and a node can see neither
    (api I1). DO NOT try to generalise it into a LOCAL predicate -- the team
    lead's measurement shows the other infeasibility class is not locally
    detectable: the obstruction spans 13 hops inside G[C] and shows no counting
    violation at any radius from 1 to 4. Keeping the two classes apart is what
    preserves the distinction between `unresolved` ("local repair gave up") and
    `infeasible` ("proved that no solution exists").
    """
    return m > n * k


def degree_deficiency_infeasible(degrees, m: int, k: int) -> bool:
    """A SECOND run-level witness, strictly stronger than the counting bound.

    A node can own at most `min(deg(v), k)` edges: at most `k` by the capacity
    rule, and at most `deg(v)` because an owner must be an ENDPOINT of the edge
    it owns. Total ownable capacity is therefore `sum(min(deg(v), k))`, and if
    that is below `m` no assignment exists, hence no solution of any shape.

    This dominates `counting_bound_infeasible`: `sum(min(deg, k)) <= n*k` always,
    so every instance the counting bound rejects this one rejects too, and it
    also catches instances the counting bound CANNOT see -- the ones where
    `m == n*k` exactly and the bound holds with equality.

    MEASURED on the n50_m300 cell, where m = n*k = 300 and the counting bound is
    therefore silent. Ten seeds were decided exactly with a flow solver: eight
    are feasible and TWO are provably not. In seed 8 one node has degree 4 and
    in seed 6 two nodes have degree 5, so the available capacity comes to
    sum(min(deg, k)) = 298 < 300 in both. A node below degree k cannot fill its
    own quota, and at exact equality there is no slack anywhere else to make up
    the difference. Before this check those two instances were reported
    `unresolved`, which reads as an arm failing on a solvable instance; they are
    now `infeasible` with reason `degree_deficiency`.

    SCOPE, same warning as the counting bound: this is RUN-LEVEL. The degree
    sequence is a global quantity and no node can see it (api I1). Do not try to
    turn it into a local predicate.
    """
    if k <= 0:
        return m > 0
    return sum(min(int(d), k) for d in degrees) < m


def counting_witness(n_closed: int, m_induced: int, k: int) -> bool:
    """A SOUND infeasibility witness for a set S: |E(S)| > k|S|.

    Every edge INSIDE S must be owned by a node inside S (an owner is one of the
    edge's endpoints), and every node in S owns at most k edges. So if
    |E(S)| > k|S| there is no assignment. The proof is pure counting, which is
    why the witness is certain WHEREVER IT APPEARS; it carries no further proof
    obligation and does not care what the cover is.

    THE CONVERSE DOES NOT HOLD: the witness staying silent does NOT prove
    feasibility. There are infeasible instances whose only witness is global, so
    this is an EARLY-EXIT test and not a decision procedure (sound, incomplete).

    A node could run it for S = N[v]: `n_closed = deg(v) + 1` is already known,
    but `m_induced` requires knowing whether my neighbours are adjacent TO EACH
    OTHER, and today's HELLO does not carry that. See
    `BbcvcNode.local_infeasibility_witness`.
    """
    return m_induced > k * n_closed


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------
@dataclass
class BbcvcParams(BootstrapParams):
    """BootstrapParams plus BB-CVC settings. All parametric; there is no RNG."""

    push_ttl: int = 3            # .tex Phase 4, D = 3 (initial depth)
    push_ttl_max: int = 3
    """Ceiling D can reach by doubling. DEFAULT = push_ttl, i.e. DEEPENING IS OFF.

    I added deepening to repair false INFEASIBLE verdicts; measurement REFUTED
    that justification. What actually closed the false alarms is the "C = V
    witness" (my own F is 0 AND every neighbour's F is 0), not deepening: the
    property matrix yields zero false infeasibility at push_ttl_max=3 as well.

    The cost is severe. PUSH spreads as a TREE, not a path (each intermediate
    node tries its next neighbour on NACK), so depth multiplies the branching.
    Measured at n=100, m=275, k=4:
        seed 43: D<=3 -> 111 slots, 109 PUSH, VALID
                 D<=8 -> 1223 slots, 2158 PUSH, INVALID
        seed 67: D<=3 -> 444 slots, 984 PUSH  | D<=8 -> 1571 slots, 3892 PUSH
    PUSH success rate was 1.3% over 1719 attempts. Deepening is not merely
    expensive: on seed 43 it drives the assignment into a state it cannot
    recover from and LOSES the valid answer. The parameter remains for
    experiments; it is off on the default path. (That measurement predates
    F1-F10. Repair F11 deepens only after `max_repair_rounds` are used up,
    up to `n_bound`; it does not read this parameter.)
    """
    quiet_periods: int = 3       # .tex Phase 5a, T_q = 3 HELLO periods
    ack_periods: int = 3         # ACK timeout = 3 * T_hello (round trip is 2)
    ack_max_attempts: int = 3    # brief S3.4 R_max
    settle_steps: int = 1        # how many consecutive STEPS the barrier must hold
    gap_patience: int = 2        # patience before declaring a 3-hop gap
    escalate_patience: int = 2   # steps stuck before escalating
    max_repair_rounds: int = 4   # how many FULL ROUNDS the three stages retry
    push_depth_max: Optional[int] = 8
    """F17b: the constant D_max that caps repair F11's push depth below n_bound.

    Fixed on the development set (Amendment 11) as the smallest power of two
    that keeps every repair F11 resolved on the 75 runs with m = nk at its F11
    outcome. MEASURED: 14 of the 75 runs push deeper than 8 without the cap
    (to 12, 24 or 200); at 8 all 14 keep verdict and cover, at 4 three end
    unresolved (DFS sync, Wu-Li async on n200_m1200_s6), at 2 three others.
    Where the certificate is silent on an infeasible instance (block M9),
    every overloaded node otherwise climbs the doubling ladder to n.
    None leaves the cap at min(n_bound, 255).
    """
    n_bound: Optional[int] = None
    """An upper bound on the number of nodes that every node knows, like k (F11).

    It caps the deepening of repair F11: a path that reassigns ownership has
    fewer edges than there are nodes. `run_bbcvc` sets it to the run's node
    count; None means the deepest push a frame can carry (the 1-byte ttl).
    """

    def __post_init__(self) -> None:
        # Bootstrap's 100 ms LINK backoff produces spurious retransmissions even
        # on a LOSSLESS channel in this mode, where the round trip is a multiple
        # of a HELLO period (measured: 15 spurious retx). Wait a full round trip.
        if self.link_backoff_ms < 3 * self.t_hello_ms:
            self.link_backoff_ms = 3 * self.t_hello_ms
    #: G2(c) (Amendment 13): ask every frozen neighbour to confirm at DONE.
    #: Off only to measure its cost; the protocol runs with it on.
    mutual_confirm: bool = True
    enable_tree: bool = False    # Phase 5b (MIS-Connector-TreeAgg); measurement only, decides nothing
    tree_deadline_periods: int = 40   # the run still terminates if 5b stalls

    @property
    def ack_timeout_ms(self) -> int:
        return self.ack_periods * self.t_hello_ms

    @property
    def t_quiet_ms(self) -> int:
        return self.quiet_periods * self.t_hello_ms


@dataclass
class Pending:
    """A pending reliable unicast. Retransmitted with the same seq (idempotent)."""

    seq: int
    peer: int
    mtype: MsgType
    payload: bytes
    e: Optional[Edge] = None
    #: How many times I had ACQUIRED `e` when this was sent. An ACK only
    #: authorises a release if that number has not moved; see `_resolve`.
    e_take: int = 0
    ttl: int = 0
    attempts: int = 1
    next_ms: int = 0
    tag: str = ""


@dataclass
class FarJob:
    """F11b: a relayed invitation I am searching for (src None at the origin)."""

    src: Optional[int]
    seq: int
    tried: Set[int] = field(default_factory=set)
    probing: Optional[int] = None


@dataclass
class PushJob:
    """Chain state kept while servicing an inbound PUSH (.tex on_push)."""

    src: int          # who sent me the PUSH
    seq: int          # their seq; my reply carries it back
    e: Edge           # the edge they want to hand me
    ttl: int          # the ttl I received
    tried: Set[int] = field(default_factory=set)
    probing: Optional[int] = None   # the neighbour I am probing right now
    probe_edge: Optional[Edge] = None
    #: I answered a retransmission of THIS request with a busy NACK, so the
    #: sender has given up on it and my final ACK will be late (F10).
    nacked: bool = False


# --------------------------------------------------------------------------
# node
# --------------------------------------------------------------------------
class BbcvcNode(BootstrapNode):
    """All of BB-CVC: Phase 0 (inherited) plus Phases 1a/1b/2/3/4/5.

    A node CANNOT SEE the graph. It has its own MAC, its weight, its k, and
    whatever it learns from HELLOs (api I1). Not even the neighbour list is a
    parameter.
    """

    def __init__(self, weight, platform: Platform,
                 params: Optional[BbcvcParams] = None, capacity_k: int = 2) -> None:
        super().__init__(weight, platform, params or BbcvcParams(), capacity_k)
        self.p: BbcvcParams = self.p  # type narrowing
        self._init_algo_state()
        #: F16b: expired finished neighbour -> end of its hand-off wait (ms).
        self._handoff: Dict[int, int] = {}

    # ---------------------------------------------------------------- state
    def _init_algo_state(self) -> None:
        # The answered-once record belongs to ONE DONE epoch. An epoch restart
        # rewinds the phase, so the neighbours that were answered in the old
        # epoch must be answerable again in the new one; see the half-finished
        # undo class in BULGULAR sections 90, 92, 93 and 97.
        self._answered_ms: Optional[int] = None   # when I last answered (F2)
        self._told_them_i_am_done: Optional[int] = None
        self._done_beacons: Dict[int, int] = {}
        self._repair_beacon = False
        self.owned: Set[Edge] = set()
        self._explicit: Dict[Edge, bool] = {}   # ownership settled by a transfer
        self.infeasible = False
        #: F12b: the verdict of an in-network certificate this node computed
        #: (the spanning-tree arm's core), None when it computed none.
        self.cert_decided: Optional[bool] = None
        #: All three stages exhausted but there is no infeasibility WITNESS: the
        #: local rules could not repair this instance. Kept SEPARATE from
        #: INFEASIBLE, because the exact solver may call the instance feasible,
        #: in which case this is a quality loss and not an infeasibility claim.
        #: The node still reaches quiescence so the run TERMINATES and the
        #: validator can report the overload.
        self.unresolved = False
        self._repair_rounds = 0
        self._adv_forced = 0                    # the F(v) I LAST ADVERTISED
        self._adv_role = Role.OUT
        self._adv_mis: Tuple[int, ...] = ()
        # THE KEY MUST BE (peer, seq). A seq number is PER-SENDER: two different
        # neighbours will happily use the same one. Matching on seq alone lets an
        # ACK from one neighbour close a request addressed to ANOTHER; measured:
        # on a 15-node UDG edge (5,15) was left UNOWNED this way, with both
        # endpoints believing the other had taken it.
        self._pending: Dict[Tuple[int, int], Pending] = {}
        #: The last HANDOVER/PUSH sent, a chain probe included, so it gates
        #: `_fix_overload` but does not bound my open transfers (F14b does that).
        self._fix_key: Optional[Tuple[int, int]] = None
        #: Edges this node has offered in THIS epoch. Cleared with everything
        #: else by `_init_algo_state`, which is what makes a late ACK from a
        #: cancelled epoch distinguishable from a late ACK of a live transfer.
        self._offered: Set[Edge] = set()
        #: Edge -> how many times I have taken it. See `Pending.e_take`.
        self._takes: Dict[Edge, int] = {}
        #: Edge -> the last seq I had issued when I last took it. A late ACK of a
        #: request at or below it answers an offer made before the edge came back,
        #: the theta check of OnAck for `_on_late_ack` (see `_accept_edge`).
        self._retake_seq: Dict[Edge, int] = {}
        #: G7 (Amendment 13): edge -> completed transfers of it that I took part
        #: in, as receiver (accept) or as sender (release on the answer). Both
        #: ends agree once a transfer completes, so a request that carries an
        #: older version was overtaken by a later transfer and is refused.
        self._gen: Dict[Edge, int] = {}
        #: peer -> {(type, seq): reply}, at most SEEN_PER_PEER per peer (F5)
        self._seen: Dict[int, Dict[Tuple[int, int], bytes]] = {}
        #: peer -> highest seq of a HANDOVER, PUSH or relay JOIN executed (F14)
        self._mark: Dict[int, int] = {}
        self._push_job: Optional[PushJob] = None
        #: F11b. The relayed invitation I am searching for; whether I have
        #: served one in this epoch (each node serves at most one, which bounds
        #: the search); whether I asked once for this neighbour signature.
        self._far_job: Optional[FarJob] = None
        self._far_served = False
        self._far_sent = False
        #: F17. The certificate wave I take part in: its initiator, my parent
        #: in it (None at the initiator), the neighbours I still wait for, my
        #: subtree's (sum of min(deg, k), sum of deg), and whether I finished.
        self._cert_root: Optional[int] = None
        self._cert_parent: Optional[int] = None
        self._cert_waiting: Set[int] = set()
        self._cert_sum: Tuple[int, int] = (0, 0)
        self._cert_done = False
        #: F17: sends of my CERT so far and the time of the next one (ProAsk).
        self._cert_tries = 0
        self._cert_next_ms = 0
        #: F15. Neighbours that echoed the role and F I announced after my
        #: DONE HELLO (None while nothing needs confirming), neighbours waiting
        #: for my echo, and when I last asked.
        self._confirmed: Optional[Set[int]] = None
        self._echo_due: Set[int] = set()
        self._confirm_ms: Optional[int] = None
        self._join_sent: Set[Tuple[int, int]] = set()        # (peer, reason)
        #: JOINs a peer refused because it has not verified me (F7). Such a
        #: peer will never join, so no rule waits for it.
        self._join_refused: Set[Tuple[int, int]] = set()
        self._barrier_hits: Dict[int, int] = {}
        self._tried_set: Set[Tuple] = set()
        self._nbr_deg: Dict[int, int] = {}
        self._nb_sig: Optional[Tuple] = None
        self._stuck_steps = 0
        self._push_ttl = (self.p.push_ttl if isinstance(self.p, BbcvcParams) else 3)
        self._gap_hits = 0
        self._last_fp: Optional[Tuple] = None
        #: None, NOT ZERO. Zero is only correct in a simulator whose clock starts
        #: at zero; under a wall clock `now - 0` fills the quiescence window on
        #: the very first tick. The baseline is set by
        #: `_establish_clock_baseline`.
        self._last_change_ms: Optional[int] = None
        self._answered_ms: Optional[int] = None
        self._told_them_i_am_done: Optional[int] = None
        self._done_beacons: Dict[int, int] = {}
        self._repair_beacon = False
        self._hello_dirty = True
        #: Phase-1a rule evaluations so far, and the 0-based evaluation at which
        #: the MIS decision was made (measurement: the run's `mis_depth`).
        self._mis_evals = 0
        self.mis_round: Optional[int] = None
        self.hellos_periodic = 0
        self.hellos_change = 0
        self.escalations = 0
        # Phase 5b (measurement). NOT ON THE DECISION PATH: no field here feeds
        # role, cover or ownership; this is asserted by a test.
        self.tree_root: Optional[int] = None
        self.tree_parent: Optional[int] = None
        self.tree_depth = 0
        self.tree_finished = False
        self.tree_subtree = 0
        self.tree_weight_fp = 0
        self._tree_nbr: Dict[int, Tuple[int, int, int]] = {}   # u -> (root, depth, parent)
        self._tree_reports: Dict[int, Tuple[int, int]] = {}    # child -> (size, weight)
        self._tree_stable_since: Optional[int] = None
        self._tree_sent_ms: Optional[int] = None
        self._tree_started_ms: Optional[int] = None

    # ------------------------------------------------------------ NodeCore
    def _establish_clock_baseline(self, now: int) -> None:
        """Bootstrap's extension point: I establish my own time fields too.

        The base class reserves this method for exactly that purpose
        ("subclasses may override it and establish their own time fields"), and
        `super()` establishes `_t0_ms` and `_stable_since_ms`. The two fields
        here belong to BB-CVC and the base class knows nothing about them, so
        its lazy-property protection does NOT cover them; establishing them is
        this override's job.

        WHY `on_timer` ALSO CALLS THIS. `on_timer` is overridden deliberately
        (order: decide THEN transmit, see the accounting note in the header) and
        does not call `super().on_timer()`. Since `stable_since_ms` is now a
        property that establishes itself on read, the base class's fields are
        correct on every path; but `_last_change_ms` and `_tree_sent_ms` are
        plain attributes and this is the only place that sets them. The baseline
        is established as the FIRST STATEMENT, by saying so rather than as a
        side effect of a later line: previously the thing that established it was
        the "the bidirectional set changed" line, which never ran on a node that
        never acquired a neighbour, leaving correctness one edit away.

        No time field is initialised to 0: under a wall clock `now - 0` is about
        1.7e12 ms and opens every duration gate on the first tick. Measured
        (bb-mnwifi, T_stab=147 ms): with zero initialisation every node freezes
        its key with deg=0 on tick one.
        """
        super()._establish_clock_baseline(now)
        if self._last_change_ms is None:
            self._last_change_ms = now
        if self._tree_sent_ms is None:
            self._tree_sent_ms = now

    def on_timer(self, name: str = "tick") -> None:
        """The single entry point. There is NO mode distinction; the timer name is
        the same under both clocks."""
        now = self.plat.now_ms()
        self._establish_clock_baseline(now)
        before = self._bidir_ids()
        self._drain_rx(now)
        self._expire(now)
        self._retry_links(now)
        after = self._bidir_ids()
        if after != before:
            self.stable_since_ms = now
        self._gate(now, after)          # key freezing / epoch (bootstrap)
        self._retry_pending(now)        # my own acknowledged unicasts
        self._step(now)                 # the five phases
        self._maybe_hello(now)          # phase advanced FIRST, then transmit

    def snapshot(self) -> NodeSnapshot:
        return NodeSnapshot(
            nid=self.nid, role=self.role, phase=self.phase,
            key=self.key_fp, deg=0 if self.deg is None else self.deg,
            owned=tuple(sorted(self.owned)), forced_load=self.forced_load(),
            counters=Counters(), epoch=self.epoch,
        )

    @property
    def done(self) -> bool:
        # An open request or a push chain still running is unfinished work:
        # with F1 a request stays open until it is answered. MEASURED without
        # this clause on lossless asynchronous runs: the verdict came while
        # DONE nodes were still servicing push chains, which then went on
        # transmitting (n50_m300_s2: verdict 27.6 s instead of 40.3 s, 399
        # frames after it). Synchronous runs were unaffected.
        if self.phase < PH_DONE or not self._barrier_closed():
            return False   # G4: done exactly when closed
        if self.p.enable_tree and self.role.in_backbone:
            return self.tree_finished
        return True

    # ------------------------------------------------------------ observation
    def forced_load(self) -> int:
        """F(v) = |{u in N(v): u outside the cover}|. Zero for an outside node."""
        if not self.role.in_cover:
            return 0
        return sum(1 for n in self._nbrs_active() if n.role == Role.OUT)

    def mis_nbrs(self) -> Tuple[int, ...]:
        """The MIS-neighbour list carried in HELLO. THIS IS THE PRODUCER.

        NO TRUNCATION. `wire.MIS_NBRS_SOFT_MAX` is NOT enforced on the wire (six
        entries encode to 25 B and round-trip perfectly); enforcing the bound is
        the producer's job, and the producer of this field is Phase 1, i.e. here.
        If the bound is exceeded `_hello_payload` RAISES (bootstrap, the single
        enforcement point): brief S5's claim that "HELLO is independent of
        density" rests precisely on this field not growing, so truncating
        silently would refute the claim invisibly.

        The bound is NOT a literal 5, it is `params.mis_nbrs_max`. G8 is a unit
        disk graph theorem and does not hold on the benchmark (measured: on the
        Dagdeviren set at n=200 every node exceeds 5, the largest is 17). The
        run script raises the bound for non-UDG runs; hard-coding 5 here would
        make BB-CVC unable to run on the benchmark at all.
        """
        return tuple(sorted(n.nid for n in self._nbrs_active()
                            if n.role == Role.MIS))

    def local_infeasibility_witness(self) -> Optional[bool]:
        """The counting witness over N[v]. None when the information is absent.

        `None` and `False` are DELIBERATELY distinct: `False` means "the witness
        did not fire", `None` means "I have no way to compute the witness".
        Conflating them is exactly the shape of the bug just removed -- mistaking
        not knowing for knowing.

        `_induced_edges` is NOT POPULATED anywhere today, and that is not an
        omission but a MEASURED DECISION (team lead, closing call).

        The witness needs |E(N[v])|, which needs a HELLO field carrying whether
        my neighbours are adjacent to each other. The carrier's cost was measured
        (bb-validate): HELLO goes from 13 B bare to 13 + 2(1+d), i.e. 31 B at
        degree 8 and 87 B at degree 36. And HELLO is roughly HALF of all
        transmissions. So this is a PERMANENT payload increase on the dominant
        frame, paid on every run, for a check that can only ever help on
        INFEASIBLE instances.

        The benefit is small once the run-level counting bound exists. Measured
        over 580 instances:
          local witness alone            88.6%
          global count (m > n*k) alone   catches 25 instances the local one
                                         structurally cannot see
          the two together               98.4%
        The global count is FREE (arithmetic on three integers the harness
        already holds). Wiring the local witness buys the 40 local-only
        instances by doubling HELLO. The trade does not clear.

        THEREFORE: do NOT add the carrier FOR THIS. But if someone adds one for
        ANOTHER reason (WuLi-Dominating's neighbour summary already carries it), then
        wiring this up is nearly free, and
        `test_counting_witness_needs_information_the_wire_does_not_carry` fails
        the moment such a field appears in order to say so. The hook and the test
        stand deliberately; nothing is wired, deliberately.
        """
        m_induced = getattr(self, "_induced_edges", None)
        if m_induced is None or self.deg is None:
            return None
        return counting_witness(self.deg + 1, m_induced, self.k)

    def load(self) -> int:
        return len(self.owned)

    def free_budget(self) -> int:
        return self.k - len(self.owned)

    # ----------------------------------------------------------- internals
    def _nbrs_active(self) -> List[BootNeighbor]:
        """Verified neighbours of the epoch's FROZEN view, in id order (determinism).

        Repair F4. Within an epoch the rules read the set frozen with the key, not
        the live table: a record that blinks out for less than T_stab (no
        restart) must not leave the barriers, F(v) or the ownership rule. Such a
        neighbour is simply absent here, and `_view_stale` makes the rules wait
        for it. Before the key freezes there is no frozen set and the live
        verified records are the view.
        """
        ids = self.nbrs if self._frozen_bidir is None else self._frozen_bidir
        return [self.nbrs[i] for i in sorted(ids)
                if i in self.nbrs and self.nbrs[i].is_edge
                and (self._frozen_bidir is None or self._in_epoch(self.nbrs[i]))]

    def _in_epoch(self, x) -> bool:
        """G1 (Amendment 13): was this record or HELLO announced in my epoch?

        The one epoch test of the protocol. A record of an older epoch is kept
        (liveness and the gate are properties of the link) but no rule reads
        it: it counts as not yet heard, so the rules wait (the F4 wait)."""
        return x.epoch == self.epoch

    def _view_stale(self) -> bool:
        """A frozen neighbour without a live verified record (repair F4): WAIT.

        The wait is bounded: either the record comes back, or the difference
        persists for T_stab and the epoch gate restarts the run.
        """
        return self._frozen_bidir is not None and any(
            self._nbr(i) is None or not self._in_epoch(self.nbrs[i])
            for i in self._frozen_bidir)

    def _mykey(self) -> Tuple[int, int]:
        return (self.key_fp, self.nid)

    def _nbr_mis(self, n: BootNeighbor) -> Tuple[int, ...]:
        """A neighbour's MIS list. THE SINGLE READ PATH FOR THIS FIELD.

        Why the indirection: `mis_nbrs` is the ONLY variable-length word array in
        the Hello body, so a variant that must carry 2-hop information
        (WuLi-Dominating) is forced to put its neighbour SUMMARY there. In that
        variant the field holds the full neighbour list, NOT MIS ids.

        A fourth reader added to the base class silently reads the wrong thing in
        WuLi-Dominating. bb-validate MEASURED it: adding one innocent line to `_rule_cover`
        grew the cover from 12 to 20 nodes at n=20 and the weight by 23% -- and
        nothing failed: the run converged and the validator said VALID. The
        answer was not malformed, it was WRONG; that is exactly the failure shape
        where the test suite stays green and the number in the paper changes.

        A single read path makes it noisy instead: WuLi-Dominating overrides only HERE and
        raises, so a new reader dies with a stack trace the first time it runs.

        THE LIMIT, PLAINLY: this only protects readers that go through here.
        Anyone writing `n.mis_nbrs` directly still breaks WuLi-Dominating silently. It reduces
        the hazard to one line of discipline in one file; it does not eliminate
        it. What would eliminate it is a dedicated neighbour field on Hello
        (36 entries = 85 B, below the 250 B limit).
        """
        return n.mis_nbrs

    @staticmethod
    def _nkey(n: BootNeighbor) -> Tuple[int, int]:
        """A neighbour's sort key. AN UNFROZEN key counts as the LARGEST.

        `n.key` can be None: the neighbour may not have passed the stability gate
        yet, or may have returned to Phase 0 through an epoch reset. The decision
        RULES never see this, because `_step` requires `_keys_ready` first; but
        the MESSAGE HANDLERS (`_on_join` -> `_relay_escalate`, `_on_push` ->
        `_flex_peers`) run INDEPENDENTLY of `_step` and are not behind that gate.
        A raw tuple comparison CRASHES there with `None < int`; measured: a
        TypeError on the relayed-escalation path at 5% loss.

        Treating None as the largest does more than avoid the crash, it is also
        semantically right: a node that has not decided anything must never be
        PREFERRED in any choice.
        """
        return (n.key if n.key is not None else _KEY_INF, n.nid)

    def _keys_ready(self, nb: Sequence[BootNeighbor]) -> bool:
        """Her komşunun anahtarı donmuş mu? Donmadıysa karar verilmez, beklenir.

        A stale frozen neighbour (repair F4) also means wait."""
        return (self.key_fp is not None and not self._view_stale()
                and all(n.key is not None for n in nb))

    def _barrier(self, nb: Sequence[BootNeighbor], p: int) -> bool:
        """Yerel bariyer (brief §3.2): bütün komşular >= p. `settle_steps` adım üst
        üste tutması istenir; mis_nbrs/rol bilgisinin bir tur yayılmasına izin verir."""
        ok = all(n.phase >= p for n in nb)
        hits = self._barrier_hits.get(p, 0)
        self._barrier_hits[p] = hits + 1 if ok else 0
        return ok and self._barrier_hits[p] > self.p.settle_steps

    def _touch(self) -> None:
        """Durum değişti: bir sonraki HELLO gecikmeden çıkar."""
        self._hello_dirty = True

    # ======================================================================
    # DURUM MAKİNESİ (.tex "Tam durum makinesi")
    # ======================================================================
    def _step(self, now: int) -> None:
        if self.phase < PH_MIS:
            return                       # bootstrap kapısı henüz açılmadı
        nb = self._nbrs_active()
        if not self._keys_ready(nb):
            return

        if self.phase in (PH_MIS, PH_CONN):
            self._backbone_step(now, nb)
        if self.phase >= PH_COVER:
            self._rule_gap(now, nb)      # 3-atlama boşluğu; geç terfiler için her adım
        if self.phase == PH_COVER and self._barrier(nb, PH_COVER):
            self._rule_cover(nb)
        if self.phase == PH_FORCED and self._barrier(nb, PH_FORCED):
            self._rule_forced(now, nb)
        if self.phase >= PH_OWN:
            self._rule_ownership(now, nb)
        self._quiescence(now, nb)
        if self.p.enable_tree:
            self._tree_step(now, nb)

    # ------------------------------------------------------------ Phase 1 seam
    def _backbone_step(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        """Phase 1: establish roles and advance `phase` to PH_COVER. VARIANTS
        OVERRIDE THIS.

        THE CONTRACT an overriding class must satisfy. On return, at the moment
        `phase` reaches PH_COVER:
          * every node's role is MIS, CONNECTOR or OUT (never COVER; that is
            assigned in Phase 2),
          * B = MIS u CONNECTOR is connected and dominating (brief G1/G2;
            asserted in tests via `check_g2`) -- BUT ONLY IF THE GRAPH IS NOT
            COMPLETE (TAM DEĞİLSE). The EXCEPTION is the theorem's scope, not a defect:
            WuLi-Dominating's marking rule is "mark a node two of whose neighbours are
            NOT adjacent to each other", and in K_n every neighbourhood is a
            clique, so nobody is marked and B stays EMPTY (connected but not
            dominating). Wu-Li's CDS theorem is stated for connected NON-COMPLETE
            graphs in the first place. WuLi-Dominating's output is still valid, because
            Phase 2 pulls the smaller-key endpoint of every both-ends-outside-B
            edge into C, which on K_n yields n-1 nodes.
            Practical consequence: a backbone-based gate (such as `check_g2`)
            WILL trip on WuLi-Dominating over an instance set containing a complete graph, for
            a documented reason. The Dagdeviren benchmark contains NO complete
            graphs (bb-bootstrap checked all 310 instances), so this is a latent
            trap rather than a live one.
          * the `mis_nbrs` field carries the MIS-role neighbours, because Phase
            1b and the 3-hop rule read it. THIS CLAUSE IS NOT RELAXED: a variant
            that uses the field with another meaning (WuLi-Dominating carries a
            neighbour summary) MUST override `_nbr_mis` and raise, because the
            base class cannot distinguish the two meanings by type checking. The
            right solution is not to share the field but to add a dedicated
            neighbour field to Hello.
        Everything from Phase 2 onward rests on this contract and does not know
        HOW the roles were established; DFS-Spanning-Backbone, GHS-MST-Backbone and WuLi-Dominating change
        only this method and run Phases 2-5 as literally the same code (brief S6:
        making a copy quietly stops the comparison being a comparison).

        `now` is unused in this body; it stays in the signature because variants
        that need a clock (a DFS token, MST merge rounds) could not override it
        otherwise.
        """
        if self.phase == PH_MIS:
            self._rule_mis(nb)
        if self.phase == PH_CONN and self._barrier(nb, PH_CONN):
            self._rule_connector(nb)

    # ---------------------------------------------------------- Phase 1a MIS
    def _rule_mis(self, nb: Sequence[BootNeighbor]) -> None:
        """.tex Alg. 1. If any neighbour with a smaller key is MIS then I am OUT;
        if they have all decided and none is MIS then I am MIS; otherwise wait."""
        # A NODE WITH NO INCIDENT EDGES MUST NOT ENTER THE COVER. It covers
        # nothing, so admitting it can only add weight and split G[C]; the
        # cover then fails the connectivity gate through no fault of the rest
        # of the run. On a CONNECTED graph no such node exists, so this guard
        # cannot change any in-contract result -- it only stops an
        # out-of-contract input from producing a self-inflicted violation.
        #
        # MEASURED on real Mininet-WiFi, n=10 seed 5: link loss isolated node 9,
        # MIS-Connector-Backbone put it in the cover and its G[C] came out in two pieces,
        # while GHS-MST-Backbone left it out and stayed valid. Reproduced in the
        # simulator on a six-node graph plus one edgeless node.
        if not self.edges():
            if self.role != Role.OUT:
                self.role = Role.OUT
                self._touch()
            self.phase = PH_CONN
            self.mis_round = self._mis_evals
            self._log("mis_decided", role="OUT", reason="no_incident_edges")
            return
        self._mis_evals += 1
        mk = self._mykey()
        smaller = [n for n in nb if self._nkey(n) < mk]
        if any(n.role == Role.MIS for n in smaller):
            self.role = Role.OUT
            self.phase = PH_CONN
            self.mis_round = self._mis_evals - 1
            self._log("mis_decided", role="OUT")
            self._touch()
        elif all(n.phase >= PH_CONN for n in smaller):
            self.role = Role.MIS
            self.phase = PH_CONN
            self.mis_round = self._mis_evals - 1
            self._log("mis_decided", role="MIS")
            self._touch()
        # otherwise: wait. The decision is MONOTONE and never retracted.

    # --------------------------------------------------- Phase 1b connector
    def _rule_connector(self, nb: Sequence[BootNeighbor]) -> None:
        """.tex Alg. 2: with two MIS neighbours I am a candidate connector; among
        the neighbours that can bridge the same pair, the smallest key wins."""
        if self.role == Role.OUT:
            mk = self._mykey()
            mis = sorted(n.nid for n in nb if n.role == Role.MIS)
            for a, b in itertools.combinations(mis, 2):
                rivals = [n for n in nb
                          if a in self._nbr_mis(n) and b in self._nbr_mis(n)]
                if all(mk < self._nkey(n) for n in rivals):
                    self.role = Role.CONNECTOR
                    self._log("connector", pair=(a, b))
                    self._touch()
                    break
        self.phase = PH_COVER
        self._touch()

    def _rule_gap(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        """The 3-hop gap (.tex figure "distance-3 gap", the a-x-y-b path).

        DEVIATION AND ITS JUSTIFICATION (reported). The .tex gives this rule to
        the MIS node: "if a sees no MIS other than itself in any neighbour's
        mis_nbrs, it promotes its richest neighbour to connector with a JOIN."
        When measured, that rule FIRES WRONGLY in two places, and every firing
        puts an unnecessary node into the cover:
          * in a star (the centre is the only MIS and every leaf's mis_nbrs holds
            only the centre),
          * in K_n (one MIS, everyone adjacent to it) -- measured: |C| was 5
            instead of 4 on K5.
        In both cases the backbone is already a SINGLE node and therefore
        connected; a's observation that it is "alone" is NOT a real gap, and a
        CANNOT tell the difference with 1-hop information.

        The rule has therefore moved from a to x, where the observation is
        1-hop: on the path a-x-y-b it is x that sees b (b appears in y's
        mis_nbrs). x becomes a connector and JOINs y when all three hold:
          (1) x has a MIS neighbour a, and some neighbour y lists a MIS b that x
              cannot see,
          (2) there is NO distance-2 bridge for the pair {a,b} (if there were,
              the Phase 1b pair rule already handles it -- in the worked example
              this is exactly what silences nodes 3 and 5),
          (3) the neighbour carrying b is not already in the backbone (if it is,
              the path already exists; this is the promotion chain's stopping
              condition).
        The result matches the .tex's figure: x and y become connectors and
        a-x-y-b enters the backbone. The difference is that the .tex has a break
        the tie between x and z by key; here x and z CANNOT SEE each other, so
        both may be promoted. That means one extra connector, not a loss of
        connectivity; it is written up in the report.
        """
        if self.role == Role.MIS or self.phase < PH_COVER:
            self._gap_hits = 0
            return
        near = {n.nid for n in nb if n.role == Role.MIS}
        if not near:
            self._gap_hits = 0
            return
        carriers: Dict[int, List[BootNeighbor]] = {}
        for n in nb:
            for b in self._nbr_mis(n):
                if b not in near:
                    carriers.setdefault(b, []).append(n)
        gaps: List[BootNeighbor] = []
        for b in sorted(carriers):
            if any(a in self._nbr_mis(n) and b in self._nbr_mis(n)
                   for n in nb for a in near):
                continue                       # (2) mesafe-2 köprüsü var
            for n in carriers[b]:
                if self.role.in_backbone and n.role.in_backbone:
                    continue                   # (3) the path is already in B
                if n.role == Role.OUT and (n.nid, JOIN_CONNECTOR) not in self._join_sent:
                    gaps.append(n)
        if not gaps:
            self._gap_hits = 0
            return
        self._gap_hits += 1
        if self._gap_hits <= self.p.gap_patience:
            return
        best = min(gaps, key=lambda n: (-len(self._nbr_mis(n)), self._nkey(n)))
        if self.role == Role.OUT:
            self.role = Role.CONNECTOR
            self._log("connector", reason="gap3")
            self._touch()
        self._send_join(now, best, JOIN_CONNECTOR)
        self._gap_hits = 0

    # -------------------------------------------------------- Phase 2 cover
    def _rule_cover(self, nb: Sequence[BootNeighbor]) -> None:
        """A message-free decision: for an edge with both ends outside the
        backbone, the smaller-key end becomes COVER. Each end already knows the
        other's key and role (by G2 connectivity survives automatically; a test
        asserts this)."""
        if self.role == Role.OUT:
            mk = self._mykey()
            if any(n.role == Role.OUT and mk < self._nkey(n) for n in nb):
                self.role = Role.COVER
                self._log("cover")
                self._touch()
        self.phase = PH_FORCED
        self._touch()

    # ------------------------------------------------- Phase 3 forced load
    def _rule_forced(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        """If F(v) > k, JOIN the F(v)-k smallest-key outside neighbours (with
        ACK). Joining is MONOTONE, so this terminates."""
        self._cover_what_the_key_election_missed(nb)
        if not self.role.in_cover:
            self.phase = PH_OWN
            self._touch()
            return
        outs = sorted((n for n in nb if n.role == Role.OUT), key=self._nkey)
        need = len(outs) - self.k
        if need <= 0:
            self.phase = PH_OWN
            self._touch()
            return
        # F7: a refusing neighbour will never join; invite the next one, and
        # if too few remain the overload goes on to Phase 4 to be reported.
        open_ = [n for n in outs if (n.nid, JOIN_FORCED) not in self._join_refused]
        if len(open_) < need:
            self.phase = PH_OWN
            self._touch()
            return
        for n in open_[:need]:
            if (n.nid, JOIN_FORCED) not in self._join_sent:
                self._send_join(now, n, JOIN_FORCED)

    def _cover_what_the_key_election_missed(self, nb: Sequence[BootNeighbor]) -> None:
        """THE KEY ELECTION ASSUMES BOTH ENDS SEE THE EDGE. ONE MAY NOT.

        `_rule_cover` gives an edge with both ends outside to the SMALLER-key
        end, and that is message-free precisely because both ends compute it
        from the same two keys. It silently assumes the edge is in both
        neighbour tables. Under loss it need not be: soft state can decay on one
        side only, so the elected end does not know the edge exists and will
        never act, while the other end defers to it for ever.

        MEASURED on the discovered n10_m20 s3 graph at five per cent loss, seed
        0, edge (1,7): node 1 held `bidir=False` for 7 and therefore no edge at
        all, node 7 held `is_edge=True` for 1 and a smaller key on the far side.
        Both stayed OUT, the edge was left uncovered AND unowned, and the run
        reported `solved`, which is the dangerous class because it looks right.

        THE REPAIR IS A ROLE, NOT A VERDICT. Refusing to settle while an
        uncovered edge is visible was tried before and reverted: `verdict` is
        the mode of termination only, and coupling it to validity turns a
        DETECTABLE false success into an undetectable truncation
        (`test_verdict_is_not_derived_from_validity`). Covering the edge instead
        makes the ANSWER correct, and it is monotone, so it cannot oscillate.

        The election is only overruled once it has demonstrably failed: the
        neighbour must still be OUT and must already have passed its own cover
        decision, which its advertised phase says. Before that it is simply
        early, and acting early would put a node into the cover for nothing.
        """
        if self.role != Role.OUT or self.phase < PH_FORCED:
            return
        if any(n.role == Role.OUT and n.phase >= PH_FORCED for n in nb):
            self.role = Role.COVER
            self._log("cover_asymmetric")
            self._touch()

    # ------------------------------------------------- Phase 4 ownership
    def _default_owner(self, n: BootNeighbor) -> bool:
        """Do I take the flexible edge (me, n)? Message-free, and it yields the
        SAME answer at both ends.

        The criterion is `cap = k - F`, and both ends use only ADVERTISED values
        (`self._adv_forced` is the F in my last HELLO, `n.load` the F in theirs).
        Using my freshly computed F would compare against a value the neighbour
        has not heard yet and leave the edge UNOWNED or DOUBLE-OWNED. Since F
        decreases monotonically this criterion does not oscillate; using total
        load would.
        """
        mine = self.k - self._adv_forced
        theirs = self.k - n.load
        if mine != theirs:
            return mine > theirs
        return self._mykey() < self._nkey(n)

    def _recompute_owned(self, nb: Sequence[BootNeighbor]) -> None:
        """Ownership is re-derived every step: forced edges, plus the flexible
        rule, plus decisions SETTLED by a transfer (`_explicit`). A transfer
        decision overrides the rule."""
        if not self.role.in_cover:
            new: Set[Edge] = set()
        else:
            new = set()
            for n in nb:
                e = edge(self.nid, n.nid)
                if n.role == Role.OUT:
                    new.add(e)                     # forced: no other owner possible
                elif e in self._explicit:
                    if self._explicit[e]:
                        new.add(e)
                elif self._default_owner(n):
                    new.add(e)
        if new != self.owned:
            self.owned = new
            self._touch()

    def _rule_ownership(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        sig = tuple((n.nid, int(n.role), n.load) for n in nb)
        if sig != self._nb_sig:
            # A neighbour's role or forced load changed, so attempts that were
            # NACKed earlier are now STALE. Role and F are monotone, so this
            # signature changes finitely often and the attempt count is bounded.
            self._nb_sig = sig
            self._tried_set.clear()
            self._stuck_steps = 0
            self._repair_rounds = 0
            self._push_ttl = self.p.push_ttl
            self._far_sent = False
        self._recompute_owned(nb)
        if self.unresolved and len(self.owned) <= self.k:
            # THE FLAG DESCRIBES THE PRESENT STATE, NOT A MOMENT IN THE PAST.
            #
            # `unresolved` means "local repair gave up". After giving up, my
            # overload can be relieved by SOMEONE ELSE's work: a neighbour
            # escalates, its F drops, the default rule shifts the edge onto it
            # and I fall back under k. If the flag is not cleared I assert a
            # failure that IS NO LONGER HAPPENING, and the run reports "could not
            # solve" over a VALID solution.
            #
            # Measured by bb-figures: three arms (WuLi-Dominating-Bloom/sync, Anneal-Local/sync,
            # Anneal-TreeAgg/sync) reported `unresolved` on one instance while
            # the validator found ZERO violations. This is the MIRROR of the
            # unsound infeasibility claim just removed: an arm asserting a
            # failure it cannot support.
            #
            # Termination is unaffected: `_quiescence` already passes on the
            # `load <= k` disjunct; the flag was only needed WHILE the overload
            # persisted.
            self.unresolved = False
            self._log("repair_recovered", load=len(self.owned), k=self.k)
            self._touch()
        if not self.role.in_cover:
            return
        if self._push_job is not None:
            self._service_push_job(now, nb)
            return
        if len(self.owned) <= self.k or self._fix_key is not None:
            return
        if self.infeasible:
            # F12b: the network proved that no valid pair exists, so repairing
            # is futile; say so instead of spending the rounds.
            if not self.unresolved:
                self.unresolved = True
                self._log("repair_skipped", reason="certified", load=len(self.owned))
                self._touch()
            return
        self._fix_overload(now, nb)

    def _flex_peers(self, nb: Sequence[BootNeighbor]) -> List[BootNeighbor]:
        """The far ends of the FLEXIBLE edges I own, in attempt order.

        Order (ascending): estimated flexible degree `deg - F`, then key. A
        neighbour's CURRENT load is not on the wire (HELLO carries only F);
        `deg - F` is how many flexible edges it has, and the intuition that "a
        node with fewer flexible edges is likelier to have room" reproduces the
        .tex example's choice (node 2 tries 3 rather than 4).
        """
        out = [n for n in nb
               if n.role != Role.OUT and edge(self.nid, n.nid) in self.owned]
        return sorted(out, key=lambda n: (self._deg_of(n) - n.load, self._nkey(n)))

    def _fix_overload(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        """Three stages: HANDOVER -> PUSH(ttl=D) -> escalation (JOIN). All monotone."""
        peers = self._flex_peers(nb)
        # F14b: one own transfer per neighbour. A chain probe moves `_fix_key`,
        # so an earlier transfer can still be open here; the next offer to that
        # neighbour waits for its answer instead of offering the edge twice.
        open_to = {p.peer for p in self._pending.values() if p.tag in ("handover", "push")}
        # stage 1: handover
        for n in peers:
            e = edge(self.nid, n.nid)
            if self._explicit.get(e) is False:
                continue
            if (n.nid, MsgType.HANDOVER, e) in self._tried:
                continue
            if n.nid in open_to:
                return
            self._tried.add((n.nid, MsgType.HANDOVER, e))
            self._send_edge_msg(now, n, MsgType.HANDOVER, e, 0, tag="handover")
            return
        # stage 2: path reversal
        for n in peers:
            e = edge(self.nid, n.nid)
            if (n.nid, MsgType.PUSH, e, self._push_ttl) in self._tried:
                continue
            if n.nid in open_to:
                return
            self._tried.add((n.nid, MsgType.PUSH, e, self._push_ttl))
            self._send_edge_msg(now, n, MsgType.PUSH, e, self._push_ttl, tag="push")
            return
        # stage 3: escalation. It is the only IRREVERSIBLE, weight-increasing
        # step, so after 1 and 2 are exhausted we wait a few more steps: in that
        # time another node's escalation may open room nearby, and once the
        # signature changes stages 1-2 are retried.
        self._stuck_steps += 1
        if self._stuck_steps <= self.p.escalate_patience:
            return
        outs = sorted((n for n in nb if n.role == Role.OUT), key=self._nkey)
        if outs:
            for n in outs:
                if (n.nid, JOIN_ESCALATE) in self._join_sent:
                    continue
                self.escalations += 1
                self._send_join(now, n, JOIN_ESCALATE)
                return
            if any((n.nid, JOIN_ESCALATE) not in self._join_refused for n in outs):
                return   # my invitees have not joined yet; too early to cry INFEASIBLE
            # F7: every outside neighbour refused; fall through to stage 3b.

        # stage 3b: RELAYED ESCALATION.
        #
        # MEASURED JUSTIFICATION (n=100, m=275, k=4). In every failing run, EVERY
        # overloaded node had NO outside neighbour (3 nodes out of 3, no
        # exceptions). The .tex's escalation says "JOIN my smallest-key outside
        # neighbour", which assumes the overloaded node sits on the BOUNDARY of
        # the cover; when the overload is in the INTERIOR the rule has nobody to
        # invite and the only mechanism that grows the cover is silently
        # disabled. In those runs the flow solver says "no valid assignment" for
        # BB-CVC's own cover, i.e. the cover really is insufficient; the place
        # that needs to grow is OUTSIDE my one-hop reach and I cannot get there
        # on my own.
        #
        # The remedy is available with one-hop information: HELLO's `load` field
        # is F, so a neighbour u with F(u) > 0 demonstrably HAS an outside
        # neighbour. I ask u to "escalate on my behalf"; u invites its own
        # smallest-key outside neighbour, one of u's forced edges becomes
        # flexible, F(u) drops by one, its budget opens by one unit and it CAN
        # NOW ACCEPT the transfer. This is how two-hop reach is obtained without
        # two-hop information.
        relays = sorted((n for n in nb
                         if n.role != Role.OUT and n.load > 0
                         and (n.nid, JOIN_RELAY) not in self._join_sent),
                        key=self._nkey)
        if relays:
            self._send_join(now, relays[0], JOIN_RELAY)
            return
        if self._push_ttl < self.p.push_ttl_max:
            # No free budget found within D steps. The .tex fixes D; with a fixed
            # D a REACHABLE but distant slack cannot be found and the node raises
            # an infeasibility flag. Measured: in 6 of 120 property runs the flag
            # went up while the exact solver called the instance feasible. The
            # depth doubles; the flag is only considered once the deepest push
            # has also failed.
            self._push_ttl = min(self.p.push_ttl_max, self._push_ttl * 2)
            self._log("push_deepen", ttl=self._push_ttl)
            return
        if self._repair_rounds < self.p.max_repair_rounds:
            # A FULL ROUND of all three stages is done. A neighbour's CURRENT
            # load is not on the wire (HELLO carries only F), so I CANNOT SEE
            # that a neighbour has freed room meanwhile; `_tried` does not go
            # stale by itself. Reset the round and retry. The round count is
            # bounded: unlimited retrying means a run that never terminates.
            self._repair_rounds += 1
            self._tried_set.clear()
            self._push_ttl = self.p.push_ttl
            self._log("repair_retry", round=self._repair_rounds)
            return
        if self._cert_root is None:
            # REPAIR F17. Before the futile part can start, ask the network once
            # whether the witness proves the instance infeasible. MEASURED
            # without it: on infeasible n100_m800 every overloaded node deepened
            # to n and the run took 5.2 times the slots of the run without F11.
            self._cert_start(now)
        cap = min(0xFF, self.p.n_bound or 0xFF, self.p.push_depth_max or 0xFF)  # F17b
        if self._push_ttl < cap:
            # REPAIR F11. The rounds above all push to depth D, so an existing
            # reassignment path longer than D is never found and the node gave
            # up on feasible instances (m = nk: 25 development runs ended
            # unresolved). One more round at twice the depth, up to n - 1 hops.
            # DOUBLING, NOT +1: both solve n200_m1200_s6 (depth 6 suffices),
            # but on infeasible instances, where no depth helps, +1 steps cost
            # 6.6x (n20_m160_s1) to 27x (n50_m300_s6) the frames of the run
            # without F11 and doubling 2.4x to 4x: log(n) rounds instead of n.
            self._push_ttl = min(cap, 2 * self._push_ttl)
            self._tried_set.clear()
            self._log("push_deepen", ttl=self._push_ttl)
            return
        if self._far_job is not None:
            return
        if not self._far_sent and not self._far_served:
            # REPAIR F11b. Even the deepest push failed, so the cover itself
            # may lack capacity where no invitation of mine reaches (the
            # spanning-tree arm on n200_m1200 s3 and s10: 199 of 200 nodes,
            # the outside node three hops away). Relay an invitation through
            # the cover to a node that has an outside neighbour; it invites
            # that neighbour, and I deepen once more (`_far_finish`).
            self._far_sent = True
            self._far_served = True
            self._far_job = FarJob(src=None, seq=0)
            self._log("far_start")
            self._far_step(now)
            return
        # NO INFEASIBILITY IS DECLARED HERE. The reason is a MEASURED BUG.
        #
        # The gate here used to be "my own F is 0 AND every neighbour's F is 0",
        # which I treated as a two-hop witness for the .tex's "C = V" condition.
        # IT IS NOT SOUND: the condition only says my two-hop view lies entirely
        # inside the cover, not that it covers ALL of it. In the instance
        # bb-bootstrap found (n=100, r=0.15, seed 4, k=4) the condition held for
        # nodes 62 and 94, yet |C| = 89 < 100 and the instance WAS FEASIBLE:
        # central gwccvc finds a valid solution with |C| = 91. So the flag was a
        # FALSE ALARM, and that was the algorithm lying rather than the validator.
        #
        # The only sound witness is a COUNTING contradiction (see
        # `counting_witness`): if |E(S)| > k|S| for some set S there is not
        # enough capacity to own S's edges, so the instance really is infeasible.
        # Today's HELLO cannot compute it, and not adding the carrier is a
        # MEASURED DECISION; the cost/benefit is in the
        # `local_infeasibility_witness` docstring. The run-level proof of
        # infeasibility is `counting_bound_infeasible`.
        #
        # Until then the node's honest answer is "I could not solve it", not
        # "it has no solution". The authority on feasibility is the validator.
        if not self.unresolved:
            self.unresolved = True
            self._log("repair_failed", load=len(self.owned), k=self.k)
            self._touch()

    # ------------------------------------------------- Phase 5a local quiescence
    def _fingerprint(self) -> Tuple:
        """The state fingerprint used to measure quiescence.

        The QUIET/DONE phases are OUTSIDE the fingerprint: they are the RESULT of
        quiescence, and including them would make the timer reset itself."""
        return (int(self.role), min(self.phase, PH_OWN), self.infeasible,
                tuple(sorted(self.owned)))

    # TRIED AND REVERTED: refusing to settle while this node can see an
    # uncovered edge (an OUT node with an OUT neighbour). The intent was to stop
    # a run claiming success with the contract visibly broken, and it did work
    # on the case that motivated it: at five per cent loss the n=10 graph went
    # from `solved` + invalid to `solved` + valid, because the node kept working
    # until edge (1,7) was covered.
    #
    # IT IS STILL WRONG, and this file's own contract says why
    # (`test_verdict_is_not_derived_from_validity`): `verdict` is the MODE OF
    # TERMINATION and nothing else, so a frozen but invalid run must still read
    # `solved` and let the validator contradict it. A row counts as an arm
    # result only when verdict is `solved` AND the validator is clean. Coupling
    # the two turns a DETECTABLE false success into an undetectable truncation,
    # which hides exactly what the separation exists to expose. The asymmetric
    # edge behind that case is real and is written up in BULGULAR_BB.md section
    # 98; it needs repairing where it breaks, not concealing at the exit.

    def _quiescence(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        fp = self._fingerprint()
        if fp != self._last_fp:
            self._last_fp = fp
            self._last_change_ms = now
            if self.phase in (PH_QUIET, PH_DONE):
                self.phase = PH_OWN       # new work appeared; leave quiescence
                self._wake(now)
        if self.phase < PH_OWN:
            return
        settled = (now - self._last_change_ms >= self.p.t_quiet_ms
                   and not self._pending and self._push_job is None
                   and self._far_job is None
                   and (len(self.owned) <= self.k or self.infeasible
                        or self.unresolved))
        if self.phase == PH_OWN and settled:
            self.phase = PH_QUIET
            self._log("quiet")
            self._touch()
        pending = self._unverified_pending(now)
        if (self.phase == PH_QUIET and not pending
                and all(n.phase >= PH_QUIET for n in nb)
                and not self._silent_below_done(now, nb)):
            self.phase = PH_DONE
            self._log("done", weight=self.w, load=len(self.owned))
            self._touch()
        elif self.phase == PH_DONE and (pending or any(n.phase < PH_QUIET for n in nb)):
            # A neighbour produced new work. Since a DONE node is SILENT,
            # staying silent would feed it to that neighbour's soft-state timer
            # and start an epoch reset (measured). I drop back to QUIET and
            # resume the liveness broadcast; once the neighbour settles I become
            # DONE again.
            self.phase = PH_QUIET
            self._touch()

    def _unverified_pending(self, now: int) -> bool:
        """REPAIR F13: is a link still being established, so that DONE is early?

        A neighbour I hear through an open gate but have not verified, while it
        has not been silent for `_quiet_window_ms`, or a verified view that
        differs from the frozen one (the epoch gate will restart). Before F13 a failed LINK
        handshake was retried 12 periods later, often after the verdict: the
        network then restarted after it (941 frames in 100 slots on the worked
        example at 20 % loss), or the run ended valid only on a discovered graph
        that lacked the planned link. A closed RSSI gate is not a link and does
        not count, nor does a neighbour that has gone silent.
        """
        if self._diff_since_ms is not None:
            return True
        # G4 (Amendment 13): the wait has a bound. F13 waits for the retry of
        # a failed handshake; a link whose handshake failed twice in this epoch
        # is one-way (G2: only an end that hears the other answers) and is not
        # waited for again.
        # Note to Amendment 15: the same bound R as the freeze gate.
        return any(n.link_up and not n.bidir
                   and n.link_rounds < self.p.link_rounds_max
                   and now - n.last_ms <= self._quiet_window_ms(n.nid)
                   for n in self.nbrs.values())

    def _silent_below_done(self, now: int, nb: Sequence[BootNeighbor]) -> bool:
        """F13: a neighbour below DONE beacons every period, so one I have not
        heard for its stale window is gone, or moved on with its HELLO lost.
        Either way DONE waits: I hear it again, or `_expire` drops it after
        `_quiet_window_ms` and the epoch restarts. Without this a QUIET node
        went DONE on the last phase it had heard from a node switched off
        while QUIET, and DONE never expires anybody."""
        return any(n.phase < PH_DONE and now - n.last_ms > self.stale_ms(n.nid)
                   for n in nb)

    def _quiet_window_ms(self, nid: int) -> int:
        """The silence a quiescent node tolerates before it calls a neighbour gone.

        A live neighbour beacons at least once per stale window: every period
        below DONE, once per window as a DONE node with an open barrier. My
        record of its phase can be stale (its DONE HELLO lost), so the window
        is counted in that slowest rate: `stale_periods` missed beacons.
        MEASURED with the plain stale window instead, 20 % loss: QUIET nodes
        expired DONE neighbours whose DONE HELLO they had missed, so restarts
        rose and a pending neighbour looked gone after one lost slow beacon.
        """
        return self.stale_ms(nid) * self.p.stale_periods

    # ======================================================================
    # HELLO: the wire.py codec (NO SECOND COPY IS EVER OPENED)
    # ======================================================================
    def _barrier_closed(self) -> bool:
        """Has every edge neighbour reached PH_DONE, as far as I have heard?

        This is the condition under which falling silent is SAFE. Waiting for
        PH_QUIET instead is not enough and the difference is the whole fix: a
        neighbour that missed my DONE is itself stuck at PH_QUIET, so a
        QUIET-based test lets me go silent while the node waiting on me can
        never learn, which is the same deadlock one level up. Waiting for
        PH_DONE terminates instead, because a node that has not reached PH_DONE
        is still beaconing, so I keep hearing it below the bar and keep
        answering until it catches up; once every neighbour is DONE, everyone
        has what they need and the whole neighbourhood goes quiet together.
        """
        return (not self._owes()
                and all(n.phase >= PH_DONE for n in self._nbrs_active()))

    def _owes(self) -> bool:
        """G4 (Amendment 13): does this node still owe the network something?

        An open request, a push chain, a relayed search or a certificate wave
        in progress, an unconfirmed announcement (F15), a hand-off (F16b) or a
        stale frozen record (F4, G1). A node that owes something is not closed:
        it keeps beaconing and keeps expiring silent peers, so a departure of
        the peer it waits for still ends in a restart and then in silence."""
        # A LINK handshake in progress is a request as well (G3, G4).
        return bool(self._pending or self._push_job is not None
                    or bool(self._rxq)   # frames received, not yet processed
                    or any(n.awaiting_ack for n in self.nbrs.values())
                    or self._far_job is not None
                    or (self._cert_root is not None and not self._cert_done)
                    or bool(self._echo_due)   # an echo I owe (F15, G2c)
                    or self._unconfirmed() or self._view_stale()
                    or self._handoff_open())

    def _handoff_wait_ms(self) -> int:
        return 2 * self.p.stale_periods_cap * self.p.t_hello_ms

    def _handoff_open(self) -> bool:
        """REPAIR F16b: is a finished neighbour still owed my epoch?

        A neighbour I held as DONE expired from my table. If it is alive it is
        closed and silent, and only a HELLO of my epoch makes it adopt the
        epoch, so I keep my barrier open and announce until I hear it in my
        epoch or the hand-off wait has passed since my latest restart. A node
        that really left costs one bounded wait, not a beacon for ever.
        """
        now = self.plat.now_ms()
        for i in [i for i, t in self._handoff.items() if now >= t]:
            del self._handoff[i]
            self._log("handoff_timeout", peer=i)
        return bool(self._handoff)

    def _maybe_hello(self, now: int) -> None:
        self._echo_due.intersection_update(self.nbrs)
        if self.phase >= PH_DONE:
            # F15: a DONE node, closed or not, announces a new role or F at
            # once and echoes for a neighbour that asked now, not a window later.
            if not self._view_stale() and (self.role, self.forced_load()) != (
                    self._adv_role, self._adv_forced):
                self._touch()
            if self._echo_due:
                self._repair_beacon = True
                self._hello_due_ms = 0
        due = self._last_hello_ms is None or now >= self._hello_due_ms
        if not (due or self._hello_dirty):
            return
        if (self.phase >= PH_DONE and not self._hello_dirty
                and not self._repair_beacon
                and not self._barrier_closed()
                and self._last_hello_ms is not None
                and now - self._last_hello_ms < self.p.t_stale_ms):
            # BARRIER STILL OPEN, BUT BEACON SLOWLY. Keeping the full periodic
            # rate after DONE costs more than the guarantee needs: on the worked
            # example it took tx from 482 to 570, past the 2.5x-of-document bound
            # the counter test guards. One beacon per stale window is enough to
            # recover a lost DONE, because that is exactly the window in which a
            # neighbour entry could otherwise go unrefreshed.
            return
        if (self.phase >= PH_DONE and not self._hello_dirty
                and not self._repair_beacon
                and self._barrier_closed()):
            # A DONE node stops its periodic liveness broadcast: otherwise the
            # network never empties and convergence time cannot be measured.
            # Sleep/duty-cycle (brief S3.6) is NOT IMPLEMENTED; only TRANSMISSION
            # stops, the node keeps listening, and it speaks immediately if its
            # state changes (`_hello_dirty`).
            #
            # BUT ONLY ONCE THE BARRIER HAS ACTUALLY CLOSED. Going silent the
            # instant THIS node is done announced the DONE bit exactly once, on
            # a best-effort broadcast, and then removed every chance of saying
            # it again; neighbours at PH_QUIET also suspend soft-state expiry,
            # so the stale entry could be neither refreshed nor dropped. One
            # lost frame therefore deadlocked termination for the whole network,
            # and it is not specific to any arm: all three share `_quiescence`.
            #
            # MEASURED on dag_anneal_n20_m160 seed 2. Every station froze and
            # reached PH_QUIET by t = 23.5 s, slot ~148, which is exactly the
            # 145-149 slots its two sibling seeds took, and the cover was
            # validator clean. Nodes 10, 13 and 20 then entered PH_DONE in the
            # SAME slot, all three sent their single phase-7 HELLO into the same
            # burst, and all three frames were lost at all nineteen receivers.
            # The other seventeen kept those neighbours at phase 5 for ever, the
            # barrier never closed, and the run spent its remaining 216 s
            # beaconing: 23,611 of its 27,375 transmissions were post-
            # convergence liveness chatter, against 568 and 483 in the siblings.
            # The collision was not bad luck either: `_touch()` forces an
            # IMMEDIATE hello on the transition, so nodes that finish in the
            # same slot transmit in lockstep, while ordinary periodic hellos are
            # spread out.
            return
        if self._view_stale():
            # F4: waiting on a stale frozen neighbour. Repeat what I last said
            # rather than re-derive F and the MIS list from a shrunken view.
            f, mis = self._adv_forced, self._adv_mis
        else:
            f, mis = self.forced_load(), self.mis_nbrs()
        self.load = f          # bootstrap._hello_payload reads this field
        if (self._told_them_i_am_done is not None
                and (self.role, f) != (self._adv_role, self._adv_forced)):
            self._confirmed, self._confirm_ms = set(), None   # F15
        if (self.phase >= PH_DONE and self._confirmed is None
                and getattr(self.p, "mutual_confirm", True)):
            # G2 (Amendment 13): the first DONE HELLO asks every frozen
            # neighbour to confirm that it holds me (and what I announce).
            self._confirmed, self._confirm_ms = set(), None
        # F15: ask with the announcement, then once per stale window, and echo
        # at most ECHO_MAX askers per HELLO so that its size stays bounded.
        self.hello_confirm = bool(self._unconfirmed()) and (
            self._confirm_ms is None or now - self._confirm_ms >= self.p.t_stale_ms)
        if self.hello_confirm:
            self._confirm_ms = now
        echo = sorted(self._echo_due)[:wire.ECHO_MAX]
        self._echo_due.difference_update(echo)
        self.hello_echo = tuple((i, int(self.nbrs[i].role), self.nbrs[i].load) for i in echo)
        # F2: a DONE node still waiting for a neighbour says so on the air.
        self.barrier_open = self.phase >= PH_DONE and not self._barrier_closed()
        self._bcast(self._hello_payload(mis))
        self.hello_confirm, self.hello_echo = False, ()
        self._adv_forced = f            # the edge rule uses ONLY advertised values
        self._adv_role = self.role
        self._adv_mis = mis
        # The document's asynchronous table SEPARATES "event HELLOs" from
        # liveness HELLOs. The distinction must be about CONTENT, not the REASON
        # for sending: in these runs the period coincides with the timer, so
        # every HELLO counts as "due" and a counter keyed on the reason would
        # stay at zero. The criterion is therefore "does this HELLO carry a state
        # change" (`_hello_dirty`).
        if self._hello_dirty:
            self.hellos_change += 1
        else:
            self.hellos_periodic += 1
        self._hello_dirty = False
        self._repair_beacon = False
        if self.phase >= PH_DONE and self._told_them_i_am_done is None:
            self._told_them_i_am_done = now
        self._last_hello_ms = now
        self._hello_due_ms = now + self.p.t_hello_ms

    def _expire(self, now: int) -> None:
        """Only a DONE node with a CLOSED barrier never drops its neighbours.

        Such a node is silent and so are its neighbours, legitimately: a node
        falls silent only once every neighbour is DONE. A neighbour that timed
        it out would restart the network for nothing, so the time I spend
        closed does not count (`_wake` on every closed tick).

        REPAIR F13. Expiry used to stop at QUIET, so a node switched off while
        its neighbours were QUIET or DONE stayed in their tables for ever
        (worked example: removed at slot 50 the survivors kept claiming its
        edges, bad_owner; node 4 removed at slot 46 and they never finished).
        While I am QUIET, or DONE with an open barrier, every live neighbour is
        heard at least once per stale window: below DONE it beacons every
        period, and DONE with an open barrier it beacons once per window. A
        QUIET node therefore expires a record silent for `_quiet_window_ms`.
        A DONE node with an open barrier may also be waiting on a neighbour
        that is DONE and closed (its DONE HELLO was lost), which only answers
        my open-flag beacons (F2), so it uses `_done_window_ms`. Either window
        is per neighbour and grows with F9. An expired record is a node that
        left: the view change restarts the epoch, and the survivors rebuild
        without it. Only after every node is DONE with a closed barrier
        is nothing transmitted that could reveal an absence; that is the scope
        of a one-shot construction.
        """
        if self.phase >= PH_DONE and self._barrier_closed():
            self._wake(now)
            return
        held = [i for i, n in self.nbrs.items() if n.phase >= PH_DONE]
        super()._expire(now)
        for i in held:
            if i not in self.nbrs:
                self._handoff[i] = now + self._handoff_wait_ms()   # F16b
                self._log("handoff", peer=i)

    def _expiry_ms(self, nbr: BootNeighbor) -> Optional[int]:
        if self.phase < PH_QUIET:
            return super()._expiry_ms(nbr)
        if self.phase == PH_QUIET:
            return self._quiet_window_ms(nbr.nid)
        return self._done_window_ms(nbr.nid)

    def _done_window_ms(self, nid: int) -> int:
        """The silence an open DONE node tolerates (F13).

        A closed neighbour is heard only through F2: it answers after two of
        my open-flag beacons, then at most once per stale window, and each
        answer needs two frames to get through, mine and its own. So the
        window is twice `stale_periods` attempts plus the two beacons F2
        waits for: (2 * stale_periods + 2) stale windows, 24 periods at the
        defaults. With the QUIET window (9 periods) instead, the 20-slot
        outage of scenario D restarted the network.
        """
        return self.stale_ms(nid) * (2 * self.p.stale_periods + 2)

    def _wake(self, now: int) -> None:
        """Leaving quiescence RESETS the soft-state TIMERS.

        Expiry is suspended throughout QUIET, and some of my neighbours are
        silent because they are DONE. Running `_expire` the instant I wake would
        mistake that LEGITIMATE silence for death and empty the whole table;
        `bidir` changes, the epoch increments and the network restarts (measured:
        a wholesale reset at slot 40 of the worked example, then an endless
        loop). Time spent in silence does not count.
        """
        for n in self.nbrs.values():
            n.last_ms = now

    def _drain_rx(self, now: int) -> None:
        """Drain the queue. Decoding goes ONLY through wire.py (no second copy).

        Bootstrap's own `_drain_rx` discards everything but HELLO/LINK/LINK_ACK;
        this version DELEGATES those same three types to it and handles only the
        algorithm types itself.
        """
        q, self._rxq = self._rxq, []
        boot: List[Tuple[int, Optional[float], bytes]] = []
        for src, rssi, payload in q:
            try:
                mt = wire.peek_type(payload)
            except Exception:
                continue
            if mt in (MsgType.HELLO, MsgType.LINK, MsgType.LINK_ACK):
                boot.append((src, rssi, payload))
                continue
            try:
                msg = wire.decode(payload)
            except Exception:
                continue
            self._on_algo(now, int(src) & MAC_MASK, msg)
        self._rxq = boot
        super()._drain_rx(now)

    def _on_hello(self, now: int, src_mac: int, rssi, h) -> None:
        """Bootstrap's HELLO path runs unchanged; ONLY `deg` is stored on top.

        `api.Neighbor` carries no degree field (it has role, phase, load,
        mis_nbrs), yet `deg` already arrives on the wire and two rules use it:
        whether a 3-hop candidate leads anywhere (`deg >= 2`) and the flexible
        degree estimate (`deg - F`). Since api.py cannot be modified, it is kept
        here.
        """
        super()._on_hello(now, src_mac, rssi, h)
        if self._in_epoch(h) and self._handoff.pop(h.src, None) is not None:
            self._log("handoff_heard", peer=h.src)   # F16b: it has my epoch
        if h.src != self.nid and h.src in self.nbrs:
            self._nbr_deg[h.src] = h.deg
        if (getattr(h, "infeasible", False) and self._in_epoch(h)
                and h.src in (self._frozen_bidir or ()) and self._nbr(h.src)):
            self._certify("hello")   # F12b: the verdict reaches every node
        self._confirm_state(h)
        self._answer_a_neighbour_still_waiting(now, h)

    def _unconfirmed(self) -> Set[int]:
        """F15: frozen neighbours that have not echoed what I announced after DONE.

        Counted over the frozen view, not the live records: a neighbour that
        expires stays owed until the epoch restarts, so a run is never done on
        the gap between the expiry and the restart."""
        if self._confirmed is None:
            return set()
        return set(self._frozen_bidir or ()) - self._confirmed

    def _confirm_state(self, h) -> None:
        """REPAIR F15: confirmed state.

        The flexible-edge rule reads the forced load each end last heard from
        the other. A closed node neither beacons nor expires records, so when
        every HELLO that carries a neighbour's new role or F is lost it keeps
        the old value, the network still falls silent, and both ends of their
        flexible edge take it (two constructed runs, Amendment 9).

        Only a change made after my DONE HELLO can be missed that way: a
        barrier closes on DONE records, and a DONE HELLO carries everything I
        changed before it. Such a change is therefore asked for in my HELLO,
        and every frozen neighbour, whatever its role, echoes what it holds in
        its own next HELLO; a role change can turn an edge to a neighbour I
        record as OUT into a flexible one, so none is left out. An echo counts
        only when it equals what I advertise. After DONE a role only rises and
        F only falls, so an equal echo is never an older value. A neighbour
        that never echoes is expired like any silent one, since my barrier is
        open while I wait, and the view change restarts the epoch: a departure
        still ends in silence (F13).
        """
        if not self._in_epoch(h) or h.src == self.nid:
            return
        if (self._confirmed is not None
                and (self.nid, int(self._adv_role), self._adv_forced) in h.echo):
            self._confirmed.add(h.src)
        if h.confirm and h.src in self.nbrs and h.src in (self._frozen_bidir or ()):
            # G2 (Amendment 13): an echo says "you are in my frozen view", so a
            # node echoes only a neighbour it holds; a one-sided edge stays
            # unconfirmed at the end that holds it, which keeps beaconing until
            # the other end verifies it and the view difference restarts.
            self._echo_due.add(h.src)

    def _certify(self, via: str) -> None:
        """F12b: the instance is proved infeasible; say so, once per epoch."""
        if not self.infeasible:
            self.infeasible = True
            self._log("infeasible_certified", via=via)
            self._touch()

    def _answer_a_neighbour_still_waiting(self, now: int, h) -> None:
        """A BEACON FROM A FINISHED NODE MEANS IT HAS NOT HEARD MINE.

        `_barrier_closed` lets a DONE node fall silent once every neighbour is
        also DONE, and that is what ends the run. It has one hole: the last
        HELLO can be lost. Then my neighbour's record of me is frozen below
        PH_DONE, its barrier never closes and it beacons for ever, while I see
        it as DONE, close my own barrier and say nothing back. Nothing refreshes
        the stale half, so the network never goes quiet even though every node
        has finished, and the run is truncated while holding a perfectly valid
        cover.

        THE MISSING FACT IS ALREADY ON THE AIR. A node at PH_DONE beacons while
        its barrier is OPEN, so a HELLO from a DONE neighbour is evidence that
        it is still missing someone, and the only thing it can be missing from
        me is my own last HELLO.

        THE ANSWER MUST BE COUNTED, NOT JUST CONDITIONED. Answering freely is
        self-defeating: once a closed node replies, "a DONE node only beacons
        when open" stops being true, two closed nodes answer each other for ever
        and NOTHING terminates. MEASURED that way: 0 of 9 lossless runs and 0 of
        45 lossy ones converged.

        REPAIR F2 (R1 audit). The submitted rule answered each neighbour once
        per DONE epoch, so losing my DONE HELLO AND that one answer left the
        neighbour beaconing for ever (scenario D). Now the beacon says what it
        is: HELLO carries an open-barrier flag, set only by a DONE node whose
        barrier is open. I answer an open-flag beacon at most once per stale
        window, as often as the neighbour keeps asking; the answer is a
        broadcast, so one per window serves every neighbour that is waiting.
        It is sent with my barrier closed, so its flag is clear and it can
        never trigger an answer itself. Once every barrier is closed nobody
        beacons, and the network is silent for good.

        MEASURED on the discovered n15_m90 s3 graph at five per cent loss, seed
        1: all fifteen nodes reached PH_DONE with a valid cover, yet nodes 10,
        12 and 13 still recorded neighbours 14, 1, 15 and 6 at PH_QUIET and beaconed
        for ever. The run reported `truncated` at four times the budget.
        """
        if self.phase < PH_DONE or self._hello_dirty:
            return
        if getattr(h, "phase", 0) < PH_DONE or h.src == self.nid:
            return
        if not getattr(h, "barrier_open", False):
            return                       # F2: a closed barrier is not waiting
        # ONLY AFTER MY OWN DONE HELLO HAS GONE OUT. Until then a neighbour's
        # beacon is not evidence of anything: it simply has not heard me YET,
        # which is ordinary propagation and not a loss. Answering that early
        # adds a HELLO to every clean run, and it cost the emulator/simulator
        # equivalence: the same run finished in 53 slots on real sockets and 57
        # in the simulator, identical cover and identical tx, differing only in
        # how the extra beacon landed in time. The guarantee that both backends
        # produce the SAME numbers is worth more than an early answer.
        # AND ONLY ONCE A REPLY WAS OVERDUE, COUNTED IN BEACONS AND NOT IN
        # MILLISECONDS. Right after my own DONE HELLO a neighbour is still
        # beaconing for the ordinary reason: it has not received it yet.
        # Answering that fires on every clean run and costs beacons.
        #
        # THE THRESHOLD MUST BE AN EVENT, NOT A CLOCK. A wall-clock separation
        # was tried first and it broke the emulator/simulator equivalence: the
        # same run finished in 53 slots on real sockets and 57 in the simulator,
        # identical cover and identical tx, because two HELLO periods do not
        # line up the same way on the two backends. The message SEQUENCE does
        # line up exactly, which is what that equivalence test asserts, so the
        # second beacon heard from this neighbour after my own DONE HELLO is a
        # separation both backends compute alike.
        if self._told_them_i_am_done is None or not self._barrier_closed():
            return
        seen = self._done_beacons.get(h.src, 0) + 1
        self._done_beacons[h.src] = seen
        if seen < 2:
            return
        if self._answered_ms is not None and now - self._answered_ms < self.p.t_stale_ms:
            return                       # F2: at most once per stale window
        # A LIVENESS BEACON, NOT AN EVENT. `_hello_dirty` marks a HELLO that
        # carries a STATE CHANGE, and the counter split exists to keep those two
        # apart. This repair changes nothing about my state; it repeats a fact I
        # already announced. Routing it through `_hello_dirty` would have moved
        # it into the event column (109 to 113 on the worked example) and made
        # the split say something untrue, so it is sent as what it is.
        self._answered_ms = now          # one broadcast answers every waiting neighbour
        self._repair_beacon = True
        self._hello_due_ms = 0

    def _deg_of(self, n: BootNeighbor) -> int:
        return self._nbr_deg.get(n.nid, 0)

    # ======================================================================
    # RELIABLE UNICAST: seq + ACK + exponential backoff + retx logging
    # ======================================================================
    @property
    def _tried(self) -> Set[Tuple]:
        return self._tried_set

    def _nbr(self, nid: int) -> Optional[BootNeighbor]:
        n = self.nbrs.get(nid)
        return n if (n is not None and n.is_edge) else None

    def _send_join(self, now: int, n: BootNeighbor, code: int) -> None:
        seq = self._next_seq()
        payload = wire.encode(wire.Join(MsgType.JOIN, self.nid, seq, code, self.epoch))
        self._join_sent.add((n.nid, code))
        self._arm(now, Pending(seq=seq, peer=n.nid, mtype=MsgType.JOIN,
                               payload=payload, tag=f"join{code}"))
        self._ucast(n, payload)

    def _send_edge_msg(self, now: int, n: BootNeighbor, mt: MsgType,
                       e: Edge, ttl: int, tag: str) -> None:
        seq = self._next_seq()
        payload = self._edge_payload(mt, seq, e, ttl)
        p = Pending(seq=seq, peer=n.nid, mtype=mt, payload=payload, e=e,
                    e_take=self._takes.get(e, 0) if e is not None else 0,
                    ttl=ttl, tag=tag)
        if mt in (MsgType.HANDOVER, MsgType.PUSH):
            # G4 (Amendment 13, third note): an answer I owe (F10's late
            # acknowledgement) is cancelled only when the edge is released,
            # never by a new offer of it. Cancelled here, the peer kept its
            # claim while my version had advanced (G7), and every later
            # transfer between us was refused as stale (n6a106 k2).
            self._offered.add(e)
        self._arm(now, p)
        self._fix_key = (n.nid, seq)
        self._ucast(n, payload)

    def _edge_payload(self, mt: MsgType, seq: int, e: Edge, ttl: int = 0) -> bytes:
        """An edge message stamped with my epoch (repair F3) and, on a request,
        with my transfer version of the edge (G7)."""
        return wire.encode(wire.EdgeMsg(mt, self.nid, seq, e[0], e[1], ttl, self.epoch,
                                        self._gen.get(e, 0) & 0xFF))

    def _stale_version(self, msg, e: Edge) -> bool:
        """G7: was this request sent before a transfer of `e` that completed?"""
        return (getattr(msg, "gen", 0) & 0xFF) != (self._gen.get(e, 0) & 0xFF)

    def _bump(self, e: Edge) -> None:
        self._gen[e] = self._gen.get(e, 0) + 1

    def _timeout_of(self, p: Pending) -> int:
        """PUSH is a CHAIN: an intermediate node asks its own question and waits,
        so its reply is delayed in proportion to ttl. A fixed timeout produces
        spurious retx here even on a lossless channel; allow for the chain
        depth."""
        if p.mtype is MsgType.PUSH:
            return (2 * (p.ttl + 1) + 2) * self.p.t_hello_ms
        return self.p.ack_timeout_ms

    def _arm(self, now: int, p: Pending) -> None:
        p.next_ms = now + self._timeout_of(p)
        self._pending[(p.peer, p.seq)] = p

    def _backoff_ms(self, p: Pending, attempts: int) -> int:
        """The wait after the `attempts`-th send: doubling, capped at R_max sends."""
        return self._timeout_of(p) * 2 ** min(attempts - 1, self.p.ack_max_attempts - 1)

    def _retry_pending(self, now: int) -> None:
        """THE single retransmission point. `log("retx")` lives here and only here.

        REPAIR F1 (R1 audit). HANDOVER and PUSH are retransmitted with capped
        backoff UNTIL A REPLY ARRIVES. Giving up after R_max and keeping the
        edge was the double-ownership path: the receiver commits before it
        acknowledges, so three lost acknowledgements left both ends owning the
        edge (scenario C). They end only on a reply, an epoch restart (which
        clears `_pending`) or a peer that left the epoch's verified view.

        A JOIN still gives up after R_max, and is then RE-ARMED: its
        `_join_sent` mark is removed, so the rule that sent it sends a fresh
        one while its trigger still holds. Keeping the mark was the stall of
        scenario B: three lost copies left the sender waiting for ever on an
        invitee that never heard it.
        """
        for key in sorted(self._pending):
            p = self._pending.get(key)
            if p is None or now < p.next_ms:
                continue
            n = self._nbr(p.peer)
            if n is None and p.peer in (self._frozen_bidir or ()):
                continue                 # F4: stale frozen neighbour, wait
            if n is None:
                # G3 (Amendment 13): a request ends on its reply or the epoch;
                # only a peer outside my frozen view ends it here.
                self._pending.pop(key, None)
                self._log("ack_gave_up", peer=p.peer, tag=p.tag, attempts=p.attempts)
                if p.mtype is MsgType.JOIN:
                    self._join_sent.discard((p.peer, wire.decode(p.payload).code))
                # An exhausted request is treated LIKE A NACK. Otherwise a PUSH
                # chain hangs forever in its `probing` field and the node never
                # repairs its own overload again (a measured deadlock).
                self._resolve(now, p, ok=False)
                continue
            p.attempts += 1
            p.next_ms = now + self._backoff_ms(p, p.attempts)
            self._log("retx", n=1, peer=p.peer, tag=p.tag, attempt=p.attempts)
            self._ucast(n, p.payload)   # SAME seq: the receiver is idempotent
        if self._cert_waiting and now >= self._cert_next_ms:
            self._cert_send(now)        # F17: the wave's requests too

    def _reply(self, peer: int, payload: bytes, key: Tuple[int, int, int]) -> None:
        n = self._nbr(peer)
        self._seen_put(key, payload)
        if n is not None:
            self._ucast(n, payload)

    def _seen_get(self, key: Tuple[int, int, int]) -> Optional[bytes]:
        return self._seen.get(key[0], {}).get(key[1:])

    def _seen_put(self, key: Tuple[int, int, int], payload: bytes) -> None:
        """Cache a reply for replay; the oldest of a peer's entries goes first (F5)."""
        cache = self._seen.setdefault(key[0], {})
        cache.pop(key[1:], None)
        cache[key[1:]] = payload
        while len(cache) > SEEN_PER_PEER:
            del cache[next(iter(cache))]

    def _repeated(self, peer: int, seq: int) -> bool:
        """F14: is a request that missed the cache at or below the peer's mark?

        The mark is the highest seq of a state-changing request (HANDOVER, PUSH,
        relay JOIN) I executed from that peer in this epoch; a request above it
        becomes the new mark. One at or below it was executed already and its
        reply evicted, or it was overtaken by a later one whose copy got through
        first; either way it is answered from my state and not executed. Seqs
        are 16-bit serial numbers (RFC 1982), as `_next_seq` wraps.
        """
        mark = self._mark.get(peer)
        if mark is not None and not 0 < ((seq - mark) & 0xFFFF) < 0x8000:
            return True
        self._mark[peer] = seq
        return False

    # ======================================================================
    # ALGORITHM MESSAGE HANDLERS (.tex "message handlers")
    # ======================================================================
    def _on_algo(self, now: int, src_mac: int, msg) -> None:
        peer = msg.src
        n = self.nbrs.get(peer)
        if n is None or n.mac != src_mac:
            return                       # unknown neighbour
        if not n.is_edge:
            if peer in (self._frozen_bidir or ()):
                return                   # G3: a frozen neighbour re-verifying: wait
            self._refuse(n, msg)         # F7: heard but not verified
            return
        if self._frozen_bidir is not None and peer not in self._frozen_bidir:
            return                       # F4: outside this epoch's frozen view
        mt = msg.mtype
        if (mt in (MsgType.JOIN, MsgType.HANDOVER, MsgType.PUSH, MsgType.CERT)
                and self._view_stale()):
            # G1 (Amendment 13, third note): a request is decided over my frozen
            # view, so it waits while that view is stale, like every rule; the
            # sender repeats it (G3).
            return
        if mt in wire.EPOCH_TYPES and msg.epoch != self.epoch:
            # F3: a request or reply that outlived an epoch restart. Without
            # the byte, a JOIN of the old epoch delivered after my reset was
            # processed as new, because `_seen` is cleared at the restart.
            self._log("epoch_mismatch_drop", peer=peer, mtype=int(mt), epoch=msg.epoch)
            return
        if mt is MsgType.JOIN:
            self._on_join(now, n, msg)
        elif mt is MsgType.JOIN_ACK:
            p = self._pending.get((peer, msg.seq))
            if not msg.code and p is not None and p.tag != "far":
                self._join_refused.add((peer, wire.decode(p.payload).code))   # F7
            self._on_ack(now, peer, msg.seq, ok=bool(msg.code))
        elif mt is MsgType.HANDOVER:
            self._on_handover(now, n, msg)
        elif mt is MsgType.PUSH:
            self._on_push(now, n, msg)
        elif mt is MsgType.PUSH_ACK and msg.ttl == LATE_CONFIRM:
            if self._pending.pop((peer, _LATE_KEY | msg.seq), None) is not None:
                self._log("late_ack_confirmed", peer=peer, edge=edge(msg.u, msg.v))
        elif mt in (MsgType.HANDOVER_ACK, MsgType.PUSH_ACK):
            if (peer, msg.seq) in self._pending:
                self._on_ack(now, peer, msg.seq, ok=True)
            else:
                self._on_late_ack(now, n, msg)
            if mt is MsgType.PUSH_ACK and msg.ttl == LATE_ASK:
                # F10: confirm every copy; a confirmation carries no state.
                self._ucast(n, self._edge_payload(MsgType.PUSH_ACK, msg.seq,
                                                  edge(msg.u, msg.v), LATE_CONFIRM))
        elif mt in (MsgType.HANDOVER_NACK, MsgType.PUSH_NACK):
            self._on_ack(now, peer, msg.seq, ok=False)
        elif mt is MsgType.CERT:
            self._on_cert(now, n, msg.seq, msg.ttl)
        elif mt is MsgType.CERT_ACK:
            self._on_cert_ack(now, n, msg.seq, msg.u, msg.v)
        elif mt is MsgType.TREE:
            self._on_tree(now, n, msg)
        elif mt is MsgType.STABLE:
            self._on_stable(now, n, msg)
        elif mt is MsgType.FINISH:
            self._on_finish(now, n, msg)

    def _refuse(self, n: BootNeighbor, msg) -> None:
        """REPAIR F7: refuse a request from a peer I hear but have not verified.

        With one-way gates (emulated backend) the sender verified me while I
        never verified it, so it keeps the edge in its view and, with F1,
        retransmits its request until it is answered. Dropping the request
        therefore stalled the sender for good: on the worked example a weak
        direction on any of 13 of the 30 directed links left a request
        unanswered for the whole budget (sync). A refusal is safe because I take
        nothing: HANDOVER and PUSH get their NACK, a JOIN gets a JOIN_ACK with
        the accept flag cleared. Replies are not cached; they carry no state.
        """
        mt = msg.mtype
        if mt not in (MsgType.JOIN, MsgType.HANDOVER, MsgType.PUSH):
            return
        if msg.epoch != self.epoch:
            return                       # F3: a stale request is not answered
        if mt is MsgType.JOIN:
            payload = wire.encode(wire.Join(MsgType.JOIN_ACK, self.nid, msg.seq, 0, self.epoch))
        else:
            nack = MsgType.HANDOVER_NACK if mt is MsgType.HANDOVER else MsgType.PUSH_NACK
            payload = self._edge_payload(nack, msg.seq, edge(msg.u, msg.v))
        job = self._push_job
        if mt is MsgType.PUSH and job is not None and (job.src, job.seq) == (n.nid, msg.seq):
            # F14b: a copy of the PUSH my chain serves; as with F10's busy refusal
            # the sender gives up on it, so my chain's answer must be the late one.
            job.nacked = True
        self._log("refused_unverified", peer=n.nid, mtype=int(mt))
        self._ucast(n, payload)

    def _on_join(self, now: int, n: BootNeighbor, msg) -> None:
        """Someone invites me into the cover. Idempotent: I ACK even if already in."""
        key = (n.nid, int(MsgType.JOIN), msg.seq)
        cached = self._seen_get(key)
        if cached is not None:
            self._reply(n.nid, cached, key)
            return
        if msg.code == JOIN_FAR:
            job = self._far_job
            if job is not None and (job.src, job.seq) == (n.nid, msg.seq):
                return                   # F11b: still searching; it is answered later
            if self._far_served or job is not None:
                self._reply(n.nid, wire.encode(wire.Join(
                    MsgType.JOIN_ACK, self.nid, msg.seq, 0, self.epoch)), key)
                return                   # F11b: visited in this epoch
            self._far_served = True
            self._far_job = FarJob(src=n.nid, seq=msg.seq)
            self._log("far_relay", by=n.nid)
            self._far_step(now)
            return
        if msg.code == JOIN_RELAY:
            # "Escalate on my behalf." I am already in the cover; what I must do
            # is invite MY OWN outside neighbour, so one of my forced edges
            # becomes flexible and I have budget to give the asker.
            if not self._repeated(n.nid, msg.seq):   # F14
                self._relay_escalate(now)
        elif self.role == Role.OUT:
            self.role = Role.CONNECTOR if msg.code == JOIN_CONNECTOR else Role.COVER
            self.phase = max(self.phase, PH_FORCED)
            self._log("joined", by=n.nid, reason=msg.code, role=self.role.name)
            self._touch()
        ack = wire.encode(wire.Join(MsgType.JOIN_ACK, self.nid, msg.seq, 1, self.epoch))
        self._reply(n.nid, ack, key)

    def _far_step(self, now: int) -> None:
        """F11b: invite my outside neighbour, else relay to the next cover neighbour.

        A depth-first search over the cover. Each node serves one search per
        epoch, so a search costs at most two frames per cover edge, and every
        relay is a persistent request (F1) tagged with the epoch (F3).
        """
        job = self._far_job
        if job is None or job.probing is not None:
            return
        nb = self._nbrs_active()
        outs = sorted((x for x in nb if x.role == Role.OUT and x.key is not None
                       and (x.nid, JOIN_ESCALATE) not in self._join_refused),
                      key=self._nkey)
        if outs and job.src is not None:
            x = outs[0]
            if (x.nid, JOIN_ESCALATE) not in self._join_sent:
                self.escalations += 1
                self._log("far_escalate", to=x.nid)
                self._send_join(now, x, JOIN_ESCALATE)
            self._far_finish(now, True)
            return
        for x in sorted((x for x in nb if x.role.in_cover), key=self._nkey):
            if x.nid == job.src or x.nid in job.tried:
                continue
            job.tried.add(x.nid)
            job.probing = x.nid
            seq = self._next_seq()
            payload = wire.encode(wire.Join(MsgType.JOIN, self.nid, seq, JOIN_FAR, self.epoch))
            self._arm(now, Pending(seq=seq, peer=x.nid, mtype=MsgType.JOIN,
                                   payload=payload, tag="far"))
            self._ucast(x, payload)
            return
        self._far_finish(now, False)

    def _far_finish(self, now: int, found: bool) -> None:
        job, self._far_job = self._far_job, None
        if job is None:
            return
        if job.src is not None:
            key = (job.src, int(MsgType.JOIN), job.seq)
            self._reply(job.src, wire.encode(wire.Join(
                MsgType.JOIN_ACK, self.nid, job.seq, int(found), self.epoch)), key)
            return
        # The origin deepens once more from the start: the cover may have grown
        # anywhere, also through another node's search.
        self._log("far_done", found=found)
        self._tried_set.clear()
        self._push_ttl = self.p.push_ttl

    # ------------------------------------------------ F17 certificate wave
    def _cert_own(self) -> Tuple[int, int]:
        d = self.deg or 0
        return min(d, self.k), d

    def _cert_join(self, now: int, root: int, parent: Optional[int]) -> None:
        """Join the wave of `root`: forward it to every other frozen neighbour.

        An echo algorithm with extinction: a smaller initiator replaces a larger
        one. A neighbour already in my wave answers my CERT with its own CERT,
        which counts as its reply. The wave reads the FROZEN view: a neighbour
        that is stale for a moment is still waited for, so no node's term is
        left out of the sums. A wave that cannot complete certifies nothing.
        """
        self._cert_root, self._cert_parent = root, parent
        self._cert_sum = self._cert_own()
        self._cert_done = False
        self._cert_waiting = set(self._frozen_bidir) - {parent}
        self._cert_tries = 0
        self._cert_send(now)
        self._cert_check(now)

    def _cert_send(self, now: int) -> None:
        """(Re)send my CERT request (ttl 1) to every neighbour I still wait for,
        with the capped doubling backoff of the other requests (ProAsk)."""
        self._cert_tries += 1
        self._cert_next_ms = now + self.p.ack_timeout_ms * 2 ** min(
            self._cert_tries - 1, self.p.ack_max_attempts - 1)
        payload = self._edge_payload(MsgType.CERT, self._cert_root, (0, 0), ttl=1)
        for i in sorted(self._cert_waiting):
            x = self._nbr(i)
            if x is not None:
                self._ucast(x, payload)

    def _cert_start(self, now: int) -> None:
        self._log("cert_wave_start")
        self._cert_join(now, self.nid, None)

    def _on_cert(self, now: int, n: BootNeighbor, root: int, ttl: int) -> None:
        if self.deg is None:
            return                     # no frozen view yet: the sender repeats
        if self._cert_root is None or root < self._cert_root:
            self._cert_join(now, root, n.nid)
        elif root != self._cert_root:
            return                     # a wave that has lost to mine
        elif n.nid in self._cert_waiting:
            self._cert_waiting.discard(n.nid)   # a neighbour inside my wave
            self._cert_check(now)
        elif ttl and n.nid == self._cert_parent:
            if self._cert_done:
                self._cert_ack()       # my CERT_ACK was lost: send it again
        elif ttl:
            # My CERT to n was lost and n repeats its own. Answer with a reply
            # (ttl 0), which is never answered, so two nodes cannot ping-pong.
            self._ucast(n, self._edge_payload(MsgType.CERT, root, (0, 0)))

    def _on_cert_ack(self, now: int, n: BootNeighbor, root: int, cap: int,
                     degs: int) -> None:
        if root != self._cert_root or n.nid not in self._cert_waiting:
            return
        self._cert_waiting.discard(n.nid)
        c, d = self._cert_sum
        self._cert_sum = (c + cap, d + degs)
        self._cert_check(now)

    def _cert_check(self, now: int) -> None:
        if self._cert_done or self._cert_waiting:
            return
        self._cert_done = True
        cap, degs = self._cert_sum
        if self._cert_parent is None:
            # degs = 2m of my component of the discovered graph. Owned edges
            # number at most sum of min(deg, k), so a sum below m proves the
            # instance infeasible; m > nk implies it. A sum that overflowed a
            # 16-bit field arrives as (0xFFFF, 0) and can never fire.
            bad = 2 * cap < degs
            self.cert_decided = bad
            self._log("cert_wave_done", cap_sum=cap, deg_sum=degs, infeasible=bad)
            if bad:
                self._certify("wave")
            return
        self._cert_ack()

    def _cert_ack(self) -> None:
        cap, degs = self._cert_sum
        if cap > 0xFFFF or degs > 0xFFFF:
            cap, degs = 0xFFFF, 0
        p = self._nbr(self._cert_parent)
        if p is not None:
            self._ucast(p, self._edge_payload(MsgType.CERT_ACK, self._cert_root,
                                              (cap, degs)))

    def _relay_escalate(self, now: int) -> None:
        """At a neighbour's request, invite MY OWN outside neighbour (stage 3b)."""
        # A neighbour whose key has not frozen is NOT invited: pulling it into
        # the cover would fix the role of a node whose degree and key are still
        # undetermined.
        outs = sorted((x for x in self._nbrs_active()
                       if x.role == Role.OUT and x.key is not None),
                      key=self._nkey)
        for x in outs:
            if (x.nid, JOIN_ESCALATE) in self._join_sent:
                continue
            self.escalations += 1
            self._log("relay_escalate", to=x.nid)
            self._send_join(now, x, JOIN_ESCALATE)
            return

    def _on_handover(self, now: int, n: BootNeighbor, msg) -> None:
        """Someone wants to hand me an edge. If I accept I reserve FIRST and ACK
        AFTERWARDS; the sender counts the edge as its own until it sees the ACK."""
        key = (n.nid, int(MsgType.HANDOVER), msg.seq)
        cached = self._seen_get(key)
        if cached is not None:
            self._reply(n.nid, cached, key)
            return
        e = edge(msg.u, msg.v)
        if self._repeated(n.nid, msg.seq):
            ok = self._explicit.get(e) is True   # F14: held by a transfer?
        elif self._stale_version(msg, e):
            ok = False                           # G7: overtaken by a later transfer
            self._log("stale_version", peer=n.nid, edge=e)
        else:
            ok = not self._yields_to_inbound(e, n) and self._accept_edge(e)
        mt = MsgType.HANDOVER_ACK if ok else MsgType.HANDOVER_NACK
        self._reply(n.nid, self._edge_payload(mt, msg.seq, e), key)

    def _yields_to_inbound(self, e: Edge, peer: BootNeighbor) -> bool:
        """Break the MUTUAL transfer race for the same edge, deterministically.

        MEASURED BUG (n=30, k=3, edge (6,17), slots 147-148). Node 6 was handing
        the edge to 17 with a PUSH while 17 was handing the SAME edge to 6 with a
        HANDOVER. Each request was processed correctly on its own, both were
        accepted, both were ACKed, and BOTH ENDS released the edge: it was left
        UNOWNED.

        The .tex's reservation discipline ("the sender counts the edge as its own
        until the ACK arrives, the receiver reserves") is correct for a ONE-WAY
        transfer and does not cover this case; two opposing transfers are each
        correct and together lose the edge.

        The rule: when my own request for the same edge is in flight, I reject an
        incoming one if my key is SMALLER (my request wins) and accept it if my
        key is LARGER (theirs wins, and mine will be NACKed anyway). Like every
        tie this breaks on the key, so the two ends can NEVER decide the same
        way and there is no deadlock: exactly one transfer proceeds.
        """
        mine_pending = any(p.e == e and p.mtype in (MsgType.HANDOVER, MsgType.PUSH)
                           for p in self._pending.values())
        return mine_pending and self._mykey() < self._nkey(peer)

    def _accept_edge(self, e: Edge) -> bool:
        """TAKING AN EDGE CANCELS MY OWN OFFER OF IT.

        `_offered` records the edges I have handed out, and section 99 uses it
        to refuse an ACK that outlived its epoch. It was only ever ADDED to, so
        an edge stayed "offered" for the rest of the run even after it came back
        to me, and a late ACK then released an edge I had since re-accepted.

        WHAT THAT LOOKS LIKE IS BOTH ENDS LETTING GO. Traced on the discovered
        n15_m90 s2 graph at five per cent loss, seed 0, for edge (12,15): node
        15 accepted it, node 12 released it, node 12 accepted it back, node 15
        accepted it, then node 12 released and node 15 released. Two transfers
        of the same edge crossed in opposite directions; `_loses_race` guards
        that while both requests are pending, but one side's pending record was
        already gone. The edge ended owned by NOBODY and the run reported
        `solved` with a `bad_owner` violation, which is the dangerous class: it
        looks correct.

        Accepting is the moment my offer stops being true, so it is retracted
        here and the section 99 guard then refuses the stale ACK by itself.
        """
        self._offered.discard(e)
        self._takes[e] = self._takes.get(e, 0) + 1
        self._retake_seq[e] = self._seq
        if self._explicit.get(e) is True:
            return True
        if e in self.owned:
            # The edge is currently mine by the DEFAULT rule. I still make the
            # acceptance explicit: otherwise the sender releases it
            # (`_explicit=False`) while I hold only a rule-derived trace, and
            # once F changes and the rule flips the edge is left UNOWNED.
            # Measured: on a 20-node UDG, (5,6) and (5,10) fell through this way.
            self._explicit[e] = True
            self._bump(e)   # G7: the receiver's side of a completed transfer
            return True
        if len(self.owned) >= self.k:
            return False
        self._explicit[e] = True
        self._bump(e)       # G7
        self.owned.add(e)
        self._touch()
        return True

    def _has_room(self, e: Edge) -> bool:
        """F14b: would `_accept_edge(e)` succeed? The same tests, no side effect."""
        return self._explicit.get(e) is True or e in self.owned or len(self.owned) < self.k

    def _release_edge(self, e: Edge) -> None:
        self._bump(e)   # G7: the sender's side of a completed transfer
        self._explicit[e] = False
        self.owned.discard(e)
        self._drop_late_ack(e)
        self._touch()

    def _drop_late_ack(self, e: Edge) -> None:
        """F10: once I give the edge away, my late "I took it" is moot; a copy
        sent after that could release an edge the peer has taken back."""
        for key in [k for k, p in self._pending.items()
                    if p.mtype is MsgType.PUSH_ACK and p.e == e]:
            del self._pending[key]

    def _on_push(self, now: int, n: BootNeighbor, msg) -> None:
        """A chained transfer. With free budget it behaves like a handover;
        without it I push one of my own edges to another neighbour (ttl-1) and
        the chain grows that way."""
        key = (n.nid, int(MsgType.PUSH), msg.seq)
        cached = self._seen_get(key)
        if cached is not None:
            self._reply(n.nid, cached, key)
            return
        e = edge(msg.u, msg.v)
        job = self._push_job
        busy = job is not None and (job.src, job.seq) == (n.nid, msg.seq)
        if not busy and self._repeated(n.nid, msg.seq):
            # F14: answered like a HANDOVER
            mt = MsgType.PUSH_ACK if self._explicit.get(e) is True else MsgType.PUSH_NACK
            self._reply(n.nid, self._edge_payload(mt, msg.seq, e), key)
            return
        if self._yields_to_inbound(e, n) or (not busy and self._stale_version(msg, e)):
            # G7: a PUSH sent before a completed transfer of e is refused too
            self._reply(n.nid, self._edge_payload(MsgType.PUSH_NACK, msg.seq, e), key)
            return
        # F14b: a copy of the request my chain serves changes nothing but by
        # taking the edge: held already, it is acknowledged without counting an
        # acquisition, and without room only the busy flag below is set.
        if busy and self._explicit.get(e) is True:
            took = True
        else:
            took = (not busy or self._has_room(e)) and self._accept_edge(e)
        if took:
            self._reply(n.nid, self._edge_payload(MsgType.PUSH_ACK, msg.seq, e), key)
            return
        if msg.ttl <= 0 or self._push_job is not None:
            job = self._push_job
            if job is not None and (job.src, job.seq) == (n.nid, msg.seq):
                job.nacked = True        # F10: the sender gives up on this one
            self._reply(n.nid, self._edge_payload(MsgType.PUSH_NACK, msg.seq, e), key)
            return
        self._push_job = PushJob(src=n.nid, seq=msg.seq, e=e, ttl=msg.ttl)
        self._service_push_job(now, self._nbrs_active())

    def _service_push_job(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        job = self._push_job
        if job is None or job.probing is not None:
            return
        for n in self._flex_peers(nb):
            if n.nid == job.src or n.nid in job.tried:
                continue
            e2 = edge(self.nid, n.nid)
            if self._explicit.get(e2) is False:
                continue
            job.tried.add(n.nid)
            job.probing = n.nid
            job.probe_edge = e2
            self._send_edge_msg(now, n, MsgType.PUSH, e2, job.ttl - 1, tag="push_chain")
            return
        self._finish_push_job(now, ok=False)

    def _finish_push_job(self, now: int, ok: bool) -> None:
        job = self._push_job
        if job is None:
            return
        self._push_job = None
        # Even when the chain succeeds the acceptance can FAIL: the default rule
        # may have filled the slot I freed with another edge meanwhile. If
        # `_accept_edge`'s return value is IGNORED I send an ACK, the sender
        # releases the edge and I do not hold it: the edge is left UNOWNED.
        # Measured: (5,15) fell through exactly this way on a 15-node UDG.
        # F14b: a copy of this request may have taken the edge while the chain
        # ran and been acknowledged; a failed chain must not answer NACK then.
        took = (self._accept_edge(job.e) if ok else False) or self._explicit.get(job.e) is True
        mt = MsgType.PUSH_ACK if took else MsgType.PUSH_NACK
        key = (job.src, int(MsgType.PUSH), job.seq)
        if took and job.nacked:
            # REPAIR F10. The sender resolved this request on my busy NACK and
            # kept the edge, so this ACK is LATE and nobody would ask for it
            # again: sent once and lost, it left both ends owning the edge. It
            # is therefore a request of its own, repeated by `_retry_pending`
            # until the sender confirms it, and while it is open I am not done.
            payload = self._edge_payload(mt, job.seq, job.e, LATE_ASK)
            self._reply(job.src, payload, key)
            self._arm(now, Pending(seq=_LATE_KEY | job.seq, peer=job.src,
                                   mtype=MsgType.PUSH_ACK, payload=payload,
                                   e=job.e, tag="late_ack"))
            return
        self._reply(job.src, self._edge_payload(mt, job.seq, job.e), key)

    def _on_ack(self, now: int, peer: int, seq: int, ok: bool) -> None:
        p = self._pending.pop((peer, seq), None)
        if p is None:
            return                        # a duplicate: state DOES NOT CHANGE (api I5)
        self._resolve(now, p, ok)

    def _on_late_ack(self, now: int, n: BootNeighbor, msg) -> None:
        """A positive reply that arrives AFTER I GAVE UP. The edge IS RELEASED.

        MEASURED BUG (found by the team lead; edge (15,19), n25_m150_s1,
        WuLi-Dominating-Bloom). On a long PUSH chain the receiver's reply can come back after
        the sender's `R_max` attempts are exhausted. The sender has already
        treated that request as a NACK and KEPT the edge, while the receiver has
        ACCEPTED it inside `_finish_push_job`: the edge ends up with TWO OWNERS.

        This is the MIRROR of the three "edge lost" bugs fixed earlier, and it is
        a definitional violation (brief S1: every edge is assigned to EXACTLY ONE
        endpoint). It was also invisible: the `owner` dictionary collapsed the
        double claim into a single entry.

        The resolution: a positive reply is AUTHORITATIVE even when late. The
        neighbour says EXPLICITLY that it took the edge and holds it via
        `_explicit`; my releasing it is the only consistent way to end the double
        ownership, and it cannot leave the edge UNOWNED, because the neighbour
        only releases if it receives an ACK itself.
        """
        e = edge(msg.u, msg.v)
        if self.nid not in e or n.nid not in e:
            return                        # an edge that is not mine
        if self._explicit.get(e) is False and e not in self.owned:
            return                        # already released; a duplicate
        if e not in self._offered:
            # AN ACK THAT OUTLIVED ITS EPOCH IS NOT AN ACK. The reasoning above
            # holds inside ONE epoch: the neighbour said explicitly that it took
            # the edge, so releasing cannot leave the edge unowned. An epoch
            # restart cancels the transfer on BOTH sides -- `_init_algo_state`
            # clears `_explicit`, `owned` and `_pending` everywhere -- so an ACK
            # that arrives after it confirms a transfer that no longer exists.
            # Honouring it releases an edge nobody has taken.
            #
            # MEASURED at five per cent loss, the level this channel actually
            # runs at, on the graphs the twenty stations saw. Six of forty-five
            # MIS-Connector runs ended `solved` AND invalid, every one of them
            # `bad_owner`. In each the giver held `_explicit[e] = False` while
            # the taker had NO entry at all: edge (2,19) in seed 2, (3,11) in
            # seed 3, (1,16) and (1,17) in seed 1. Both ends agreed on epoch,
            # key and load, so the tie-break was not at fault; the release was.
            self._log("stale_ack_ignored", peer=n.nid, edge=e)
            return
        floor = self._retake_seq.get(e)
        if floor is not None and not 0 < ((msg.seq - floor) & 0xFFFF) < 0x8000:
            # AN ACK OF AN OFFER MADE BEFORE I TOOK THE EDGE BACK. Found by the Lean
            # model of the handlers (formal/.../ExecRequests.lean, `code_late_ack_twice`):
            # offer, the ACK releases the edge, the edge comes back, it is offered
            # again, and a delayed copy of the first ACK released it a second time.
            # `_resolve` refuses that case through `e_take`, the theta check of
            # OnAck; this is the same check on the late path.
            self._log("stale_late_ack_ignored", peer=n.nid, edge=e)
            return
        self._log("late_ack_release", peer=n.nid, edge=e)
        self._release_edge(e)

    def _resolve(self, now: int, p: Pending, ok: bool) -> None:
        """The END of a pending request: ACK, NACK, or attempts exhausted."""
        if self._fix_key == (p.peer, p.seq):
            self._fix_key = None
        if p.mtype in (MsgType.HANDOVER, MsgType.PUSH) and ok and p.e is not None:
            # AN ACK AUTHORISES A RELEASE ONLY IF I STILL HOLD WHAT I OFFERED.
            # Between sending a handover and its acknowledgement the same edge
            # can come BACK to me, and then the ACK confirms a transfer of an
            # edge I have since re-acquired. Honouring it hands away something
            # nobody else is holding.
            #
            # TRACED on the discovered n15_m90 s2 graph at five per cent loss,
            # seed 0, edge (12,15): node 15 accepted it, node 12 released, node
            # 12 accepted it back, node 15 accepted it, and then BOTH released,
            # each acting on an acknowledgement of a handover it had sent
            # before its own re-acquisition. `_loses_race` guards two requests
            # that are pending AT THE SAME TIME; these were not. The edge ended
            # owned by nobody and the run reported `solved` with `bad_owner`,
            # which is the dangerous class because it looks correct.
            if self._takes.get(p.e, 0) != p.e_take:
                self._log("stale_handover_ack", peer=p.peer, edge=p.e)
            else:
                self._release_edge(p.e)
        far = self._far_job
        if p.tag == "far" and far is not None and far.probing == p.peer:
            far.probing = None
            if ok:
                self._far_finish(now, True)
            else:
                self._far_step(now)
        job = self._push_job
        if (job is not None and job.probing == p.peer
                and job.probe_edge == p.e and p.mtype is MsgType.PUSH):
            job.probing = None
            job.probe_edge = None
            if ok:
                self._finish_push_job(now, ok=True)
            else:
                self._service_push_job(now, self._nbrs_active())
        self._touch()


    # ======================================================================
    # PHASE 5b: backbone convergecast (.tex Phase 5, "backbone tree")
    # ======================================================================
    # FOR MEASUREMENT ONLY; IT DECIDES NOTHING. No value here touches role,
    # cover or ownership; it runs only when `enable_tree` is set and only once
    # the node has already reached quiescence (phase >= QUIET). Its purpose is to
    # MEASURE "how cheap is the backbone for communication": collecting the same
    # information by broadcast costs 2m deliveries, while the backbone tree costs
    # |B| unicasts.
    #
    # Root: the SMALLEST-ID MIS node. A node cannot see this and learns it by
    # min-id gossip: the triple (root, depth, parent) is carried to backbone
    # neighbours in TREE messages and everyone adopts the smallest root and
    # shortest depth it has seen. Since that quantity decreases monotonically,
    # this terminates.
    #
    # The collected values are SUBTREE SIZE and SUBTREE WEIGHT. The tx/rx/bytes
    # fields exist on the wire but ZERO is sent: per api.py a node does not
    # report its own counters, which are derived from the log.
    def _tree_step(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        if self.phase < PH_QUIET:
            return
        if not self.role.in_backbone:
            self.tree_finished = True
            return
        if self._tree_started_ms is None:
            self._tree_started_ms = now
        if self.tree_finished:
            return
        if now - self._tree_started_ms > self.p.tree_deadline_periods * self.p.t_hello_ms:
            # The tree stalled (loss, or a disconnected backbone). The run must
            # still TERMINATE; the event is logged and the measurement is
            # reported as incomplete.
            self.tree_finished = True
            self._log("tree_timeout", root=self.tree_root, depth=self.tree_depth)
            return

        bb = [n for n in nb if n.role.in_backbone]
        best = (self.nid, 0, None) if self.role == Role.MIS else None
        for n in bb:
            info = self._tree_nbr.get(n.nid)
            if info is None:
                continue
            cand = (info[0], info[1] + 1, n.nid)
            if best is None or cand < best:
                best = cand
        if best is None:
            return                              # henüz kök duymadım
        cur = (self.tree_root, self.tree_depth, self.tree_parent)
        if cur != best:
            self.tree_root, self.tree_depth, self.tree_parent = best
            self._tree_stable_since = now
            self._tree_reports.clear()
            self._tree_send(now, bb, force=True)
            return
        if self._tree_stable_since is None:
            self._tree_stable_since = now
        if now - self._tree_sent_ms >= self.p.t_quiet_ms:
            # Yavaş yineleme: TREE zaten DEĞİŞİMDE gönderiliyor; buradaki
            # periyot yalnız kayıp telafisi içindir. HELLO periyoduyla
            # göndermek ölçülen 5b maliyetini üç katına çıkarıyordu.
            self._tree_send(now, bb, force=False)
        if now - self._tree_stable_since < self.p.t_quiet_ms:
            return
        # Kök ANLAŞMASI beklenir: bütün omurga komşularım aynı kökü söylemeli.
        # Bu kapı olmadan yerel olarak erken oturan bir alt ağaç kendini kök
        # ilan edip toplamayı bitiriyor, sonra gerçek (daha küçük kimlikli) kök
        # duyulduğunda iş bitmiş oluyordu. Ölçüldü: çalışan örnekte 2 ve 8
        # ayrı ayrı kök oldu, alt ağaç boyutu 5 yerine 2 çıktı.
        if any(self._tree_nbr.get(n.nid, (None,))[0] != self.tree_root for n in bb):
            return

        children = sorted(n.nid for n in bb
                          if self._tree_nbr.get(n.nid, (0, 0, None))[2] == self.nid)
        if any(c not in self._tree_reports for c in children):
            return
        self.tree_subtree = 1 + sum(v[0] for v in self._tree_reports.values())
        self.tree_weight_fp = to_fp(self.w) + sum(v[1] for v in self._tree_reports.values())
        if self.tree_parent is None:
            self.tree_finished = True
            self._log("tree_root_done", root=self.tree_root,
                      subtree=self.tree_subtree, weight_fp=self.tree_weight_fp)
            self._tree_finish(children)
        else:
            n = self._nbr(self.tree_parent)
            if n is not None:
                self._ucast(n, wire.encode(wire.Stable(
                    src=self.nid, seq=self._next_seq(), root=self.tree_root or _TREE_NO_NODE,
                    subtree=self.tree_subtree, tx=0, rx=0, bytes_tx=0,
                    weight_fp=self.tree_weight_fp)))

    def _tree_send(self, now: int, bb: Sequence[BootNeighbor], force: bool) -> None:
        if self.tree_root is None:
            return
        # Nöbetçi denetimi (bkz. _TREE_NO_NODE). Kimlik 0'a düşerse kök/ebeveyn
        # alanları "yok" ile karışır; bu, sessiz bir yanlış ağaç demektir.
        # Değişmez BAŞKA BİR DOSYADA (bootstrap.hash16) tutuluyor ve onu gevşetmek
        # için gerçek bir baskı var, o yüzden burada koşum anında denetlenir.
        if _TREE_NO_NODE in (self.nid, self.tree_root):
            raise ValueError(
                f"düğüm kimliği {_TREE_NO_NODE} Faz 5b nöbetçisiyle çakışıyor: "
                f"nid={self.nid} root={self.tree_root}. `bootstrap.hash16` 0'ı "
                f"ayırmayı bıraktıysa 5b'nin kodlaması onarılmalıdır; 0-indeksli "
                f"girdiler harness'ta yeniden etiketlenmelidir.")
        self._tree_sent_ms = now
        payload = wire.encode(wire.Tree(
            src=self.nid, seq=self._next_seq(), root=self.tree_root,
            parent=_TREE_NO_NODE if self.tree_parent is None else self.tree_parent,
            depth=min(self.tree_depth, 255)))
        for n in bb:
            self._ucast(n, payload)

    def _tree_finish(self, children: Sequence[int]) -> None:
        for cid in children:
            n = self._nbr(cid)
            if n is not None:
                self._ucast(n, wire.encode(wire.Finish(
                    src=self.nid, seq=self._next_seq(),
                    root=self.tree_root or _TREE_NO_NODE, epoch=self.epoch)))

    def _on_tree(self, now: int, n: BootNeighbor, msg) -> None:
        # parent == _TREE_NO_NODE "ebeveynim yok (kökümü)" demektir; gerçek bir
        # kimlikle karışmaması `bootstrap.hash16`ın 0'ı ayırmasına dayanır.
        self._tree_nbr[n.nid] = (msg.root, msg.depth,
                                 None if msg.parent == _TREE_NO_NODE else msg.parent)

    def _on_stable(self, now: int, n: BootNeighbor, msg) -> None:
        self._tree_reports[n.nid] = (msg.subtree, msg.weight_fp)

    def _on_finish(self, now: int, n: BootNeighbor, msg) -> None:
        if self.tree_finished or n.nid != self.tree_parent:
            return
        self.tree_finished = True
        bb = [x for x in self._nbrs_active() if x.role.in_backbone]
        children = sorted(x.nid for x in bb
                          if self._tree_nbr.get(x.nid, (0, 0, None))[2] == self.nid)
        self._tree_finish(children)

    # ------------------------------------------------------------ epoch
    def _reset_to_phase0(self, now: int, reason: str) -> None:
        """Epoch yeniden koşumu: ALGORİTMA durumu da sıfırlanır. Yama yok."""
        super()._reset_to_phase0(now, reason)
        self.role = Role.OUT
        self._init_algo_state()
        # F16b: the hand-off wait of a still owed neighbour counts from the restart
        self._handoff = {i: now + self._handoff_wait_ms()
                         for i, t in self._handoff.items() if now < t}
        # `_init_algo_state` zaman alanlarını None'a çeker; taban HEMEN yeniden
        # kurulur, yoksa epoch sıfırlamasından sonraki ilk tık tabansız koşar.
        self._establish_clock_baseline(now)




# ==========================================================================
# KOŞUM YARDIMCILARI (ölçüm/test tarafı; düğüm kodunun parçası DEĞİLDİR)
# ==========================================================================
# Düğüm kendi kimliğini `id = hash16(MAC)` ile TÜRETİR (brief §3.5/1); motorun
# verdiği çizge etiketiyle aynı olmak zorunda değildir. Ölçümü okunur kılmak
# için MAC'ler, hash16'ları istenen etikete DÜŞECEK biçimde seçilir. Bu bir
# kolaylıktır, düğüme bilgi sızdırmaz: düğüm yine yalnız kendi MAC'ini görür
# ve id'yi kendisi hesaplar. Yan faydası, rastgele MAC'lerde ortaya çıkabilen
# hash16 çakışmalarının deneyi kirletmemesidir.
_MAC_BASE = 0x020000000000
_MAC_INDEX: Dict[int, int] = {}
_MAC_SCAN = 0


def mac_for_id(nid: int) -> int:
    """hash16(mac) == nid olacak bir MAC bul. Sonuç önbelleklenir."""
    global _MAC_SCAN
    if nid in _MAC_INDEX:
        return _MAC_INDEX[nid]
    x = _MAC_SCAN
    while nid not in _MAC_INDEX:
        mac = _MAC_BASE | x
        _MAC_INDEX.setdefault(hash16(mac), mac)
        x += 1
        if x > (1 << 24):
            raise RuntimeError(f"hash16 ön görüntüsü bulunamadı: {nid}")
    _MAC_SCAN = x
    return _MAC_INDEX[nid]


def macs_for(ids: Iterable[int]) -> Dict[int, int]:
    return {int(i): mac_for_id(int(i)) for i in sorted(set(int(i) for i in ids))}


def build_nodes(net, weights: Dict[int, float], k: int,
                params: Optional[BbcvcParams] = None) -> Dict[int, BbcvcNode]:
    """Her düğüm için bir çekirdek. Çizge VERİLMEZ: yalnız ağırlık, k ve port."""
    return {nid: BbcvcNode(weights[nid], net.port(nid), params, k) for nid in net.nodes}


# --------------------------------------------------------------------------
# protocol state per node, at embedded field widths (measurement)
# --------------------------------------------------------------------------
#: Field widths, in bytes, of the embedded layout `state_bytes` assumes: a 16.16
#: key or weight (and the 32-bit RNG state) 4; a node id or sequence number 2; a
#: flag, role, phase, epoch, degree, load, code or small counter 1; a MAC 6; a
#: millisecond timestamp 4. An edge is two ids; a stored frame counts its length.
STATE_WIDTHS = {"key": 4, "id": 2, "flag": 1, "mac": 6, "ts": 4}
_WK, _WI, _WF, _WM, _WT = (STATE_WIDTHS[x] for x in ("key", "id", "flag", "mac", "ts"))
_WE = 2 * _WI
#: Scalars every node holds: identity (id, MAC, salt, weight, k), bootstrap
#: (epoch, phase, role, load, barrier flag, deg, key, seq, RNG, five timers)
#: and Phases 1-5 (fourteen flags and counters, the active fix key, four timers).
STATE_FIXED_BYTES = ((_WI + _WM + _WF + _WK + _WF)
                     + (6 * _WF + _WK + _WI + _WK + 5 * _WT)
                     + (14 * _WF + 2 * _WI + 4 * _WT))
#: One neighbour record without its MIS list: id, MAC, key, role, phase, load,
#: epoch, last heard, packed link flags, RSSI average, LINK seq, last acked seq,
#: LINK attempts, two LINK timers.
STATE_NEIGHBOUR_BYTES = (_WI + _WM + _WK + 4 * _WF + _WT + _WF + _WF
                         + 2 * _WI + _WF + 2 * _WT)
_STATE_TREE_BYTES = 2 * _WI + 2 * _WF + _WI + 2 * _WK + 3 * _WT


def state_bytes(node: BbcvcNode) -> int:
    """Protocol state one node holds, in bytes at `STATE_WIDTHS`.

    Counts the shared core (bootstrap and Phases 1-5) as the code stores it:
    the neighbour table, the frozen view, ownership, pending requests with
    their frames, the reply cache, the attempt and invitation sets and the
    barrier bookkeeping; the Phase 5b tree only when it is enabled. Measurement
    counters and log state are not protocol state and are not counted, nor is
    the extra state an arm keeps for its own Phase 1.
    """
    b = STATE_FIXED_BYTES
    b += sum(STATE_NEIGHBOUR_BYTES + _WI * len(n.mis_nbrs) for n in node.nbrs.values())
    b += _WI * len(node._frozen_bidir or ())
    b += _WI * len(node._adv_mis)
    b += _WE * len(node.owned) + (_WE + _WF) * (len(node._explicit) + len(node._takes))
    b += _WE * len(node._offered)
    b += (_WE + _WI) * len(node._retake_seq)
    b += sum(2 * _WI + _WF + _WE + 3 * _WF + _WT + len(p.payload)
             for p in node._pending.values())
    b += sum(_WI + _WF + _WI + len(r) for c in node._seen.values() for r in c.values())
    b += 2 * _WI * len(node._mark)   # F14: peer id and seq
    job = node._push_job
    if job is not None:
        b += 2 * _WI + _WE + _WF + _WI * len(job.tried) + _WI + _WE + _WF
    if node._cert_root is not None:   # F17
        b += 2 * _WI + 2 * _WK + 2 * _WF + _WT + _WI * len(node._cert_waiting)
    far = node._far_job
    if far is not None:
        b += 3 * _WI + _WI * len(far.tried)   # F11b
    b += (_WI + _WF) * (len(node._join_sent) + len(node._join_refused)
                        + len(node._done_beacons) + len(node._nbr_deg))
    b += (_WI + _WF + _WE + _WF) * len(node._tried_set)
    b += _WI * (len(node._confirmed or ()) + len(node._echo_due))   # F15
    b += 2 * _WF * len(node._barrier_hits)
    b += (_WI + _WF) * len(node._stale_p) + _WI * len(node._expired)   # F9
    b += (_WI + _WT) * len(node._handoff)   # F16b
    if node._nb_sig is not None:
        b += (_WI + 2 * _WF) * len(node._nb_sig)
    if node._last_fp is not None:
        b += 3 * _WF + _WE * len(node._last_fp[3])
    if node.p.enable_tree:
        b += _STATE_TREE_BYTES + (2 * _WI + _WF + _WI) * len(node._tree_nbr)
        b += (2 * _WI + 2 * _WK) * len(node._tree_reports)
    return b


def _tx_after_convergence(sc, window_ms: int) -> int:
    """Transmissions in the `window_ms` after the verdict, counted on a TWIN.

    The scheduler, network and nodes are deep-copied and the copy keeps
    running; the run's own objects never advance past the verdict, so every
    number the run reports (counters, log, anytime traces of the observers)
    stays the verdict's. The log and its observers are detached for the copy.
    """
    net = sc.net
    kept = net.log_records, net._log_observers
    net.log_records, net._log_observers = [], []
    try:
        twin = copy.deepcopy(sc)
    finally:
        net.log_records, net._log_observers = kept
    before = sum(c.tx for c in twin.net.counters.values())
    twin.watch(window_ms)
    return sum(c.tx for c in twin.net.counters.values()) - before


@dataclass
class BbcvcRun:
    """Bir koşumun okunur özeti. `cover`/`owner` çizge etiketi uzayındadır."""

    outcome: object
    nodes: Dict[int, BbcvcNode]
    net: object
    cover: List[int]
    owner: Dict[Edge, int]
    total_weight: float
    tx: int
    rx: int
    retx: int
    bytes_tx: int
    max_payload: int
    slots: Optional[int]
    t_conv_ms: Optional[int]
    converged: bool
    #: KOŞUMUN hükmü, tek kelimeyle: "solved" | "unresolved" | "truncated".
    #: (Alan adı `outcome` DEĞİL: o ad zaten zamanlayıcının `RunOutcome`
    #: nesnesini taşıyor ve ikisini karıştırmak sessiz bir hata olurdu.)
    #: BUNU OKUYUN. Bayrakların YOKLUĞUNDAN başarı çıkarmak yanlıştır ve tam da
    #: bu yüzden bu alan var: bütçesi dolmuş bir koşum `infeasible=False,
    #: unresolved=False` döndürür, çünkü hiçbir düğüm henüz pes etmemiştir.
    #: Ölçüldü (çalışan örnek, max_ms=4000): 20 slotta kesilen koşum |C|=3,
    #: sıfır sahiplik ve KOPUK bir örtüyle "bayraksız" dönüyordu; yalnız
    #: `converged=False` bunu söylüyordu ve onu okumayan bir tüketici satırı
    #: geçerli bir kol sonucu olarak kaydederdi.
    #:
    #: "solved"     yakınsadı ve hiçbir düğüm pes etmedi
    #: "unresolved" yakınsadı ama yerel onarım yetmedi
    #: "truncated"  duvar bütçesi doldu; bu koşumun cevabı HİÇBİR ŞEY ANLATMAZ
    verdict: str
    #: `verdict == "truncated"` ile aynı bilgi, açık bayrak olarak.
    truncated: bool
    infeasible: bool
    #: `infeasible` NEREDEN geldi. "" (gelmedi) | "counting_bound" (koşum
    #: düzeyinde aritmetik) | "node" (düğümün kendi tanığı). Kaynağı ayrı
    #: tutmak zorunludur: bugün düğümün SAĞLAM bir yerel tanığı YOKTUR, ve
    #: koşum düzeyindeki bir kanıtı düğüm yeteneği gibi göstermek, az önce
    #: kaldırılan yanlış alarmın aynısını başka kılıkta geri getirirdi.
    #:
    #: `infeasible` ÖRNEK hakkındadır, `verdict` KOŞUM hakkında. İkisi ayrı
    #: sorulardır: bütçesi dolmuş bir koşum, uygunsuzluğu aritmetikle
    #: kanıtlanmış bir örnek üzerinde de olabilir; o zaman örnek uygunsuzdur
    #: VE koşum kesiktir, ikisi birden doğrudur.
    infeasible_reason: str
    unresolved: bool
    hello_change_tx: int
    hello_periodic_tx: int
    by_phase_tx: Dict[int, int]
    by_type_tx: Dict[int, int]
    #: İKİ UCU DA sahiplendiğini söyleyen kenarlar: {kenar: (düğüm, düğüm)}.
    #: `owner` haritası sözlük olduğundan çifte iddiayı tek girdiye ÇÖKERTİR ve
    #: aşağı akıştaki hiçbir tüketici -- doğrulayıcı dahil -- onu göremez. Boş
    #: olmayan bir sözlük, problem tanımının ("her kenar TAM BİR uca atanır")
    #: ihlal edildiği anlamına gelir ve koşum raporlanamaz.
    double_claimed: Dict[Edge, Tuple[int, ...]] = field(default_factory=dict)
    tree_root: Optional[int] = None
    #: R1 run-level counters (measurement only, no effect on the run).
    #: Largest 0-based Phase-1a decision round over the nodes; None for arms
    #: without the Phase-1a MIS rule. The run took mis_depth + 1 rounds.
    mis_depth: Optional[int] = None
    #: Epoch restarts: the largest unwrapped epoch advance over the nodes.
    restarts: int = 0
    #: Frames sent in a window after the verdict (`run_bbcvc(watch_ms=...)`),
    #: measured on a twin; None when the run did not converge or no window ran.
    tx_after_convergence: Optional[int] = None
    #: `state_bytes` over the nodes at run end.
    state_bytes_max: int = 0
    state_bytes_mean: float = 0.0
    #: The final frozen discovered graph: {u,v} with each endpoint holding the
    #: other in its frozen view (Amendment 4). A node that has not frozen in
    #: the final epoch contributes no edge.
    discovered_edges: Tuple[Edge, ...] = ()
    #: F12b: the verdict of the in-network certificate (spanning-tree arm), or
    #: None when no node computed one; whether every node then held the flag
    #: is read from the nodes.
    infeasible_in_network: Optional[bool] = None


def run_bbcvc(edges: Sequence[Edge], weights: Dict[int, float], k: int, *,
              scheduler: str = "sync", params: Optional[BbcvcParams] = None,
              max_ms: int = 200_000, loss: float | str = 0.0, seed: int = 0,
              delay=None, tau_ms: int = 200, tick_ms: int = 200,
              rssi_range=None, node_factory=None, result_cls=None,
              link_loss=None, drop=None,
              watch_ms: Optional[int] = None) -> "BbcvcRun":
    """BB-CVC'yi bir zamanlayıcıyla koştur. Düğüm kodu kipi GÖREMEZ.

    VARYANT KANCALARI (DFS-Spanning-Backbone, GHS-MST-Backbone, WuLi-Dominating, Anneal-Local için).

    `node_factory(net, weights, k, params) -> Dict[int, NodeCore]` düğüm kurma
    adımını devralır; varsayılan `build_nodes`tır. AĞ DÜZEYİNDEDİR, düğüm
    düzeyinde değil, ve bu bilinçli: fabrika `net`i gördüğü için
      * DÜĞÜM BAŞINA tohum verisi dağıtabilir (GHS-MST-Backbone'un MST'den türettiği roller),
      * kurduğu düğümlere zamanlayıcı BAŞLAMADAN önce gözlemci takabilir
        (Anneal'ın anytime izi, şekil 8),
      * kendi params alt tipini kullanabilir (`AnnealParams`); `params` buradan
        DEĞİŞTİRİLMEDEN geçer, `BbcvcParams`a zorlanmaz.
    Tek kanca bu üç ihtiyacın üçünü birden karşılar.

    `result_cls` sonucu açar: `BbcvcRun`ın varsayılan alanlarına ek alanlar
    taşıyan bir alt sınıf verilebilir (Anneal'ın `AnnealRun`ı). Sonuç tipi
    sabitlenseydi Anneal yine bir uyarlayıcı yazardı ve kopya yok olmaz, yalnız
    yer değiştirirdi.

    Bu satırdan sonrası — `validate_bootstrap` kapısı, örtü/sahiplik çıkarımı,
    sayma sınırı, sonuç derlemesi — BÜTÜN varyantlarda AYNI koddur. Kopyalanan
    bir sonuç çıkarımı, kopyalanan bir Faz 3-4 gibi kayar; karşılaştırma sessizce
    karşılaştırma olmaktan çıkar (brief §6).

    `drop` is SimNet's deterministic fault predicate (tests). `watch_ms` is the
    window after the verdict in which `tx_after_convergence` is counted, on a
    twin of the run; None means five stale windows, 0 means no window.
    """
    from ccvc.bb import sched as _sched
    from ccvc.bb import simnet as _simnet

    p = params or BbcvcParams()
    nodes_ids = sorted({a for e in edges for a in e} | set(weights))
    if getattr(p, "n_bound", 0) is None:
        p = copy.copy(p)
        p.n_bound = len(nodes_ids)   # F11: the bound every node is given
    # `loss` is a probability or a simnet loss label ('ge:<r>:<b>', 'emp')
    net = _simnet.SimNet(nodes_ids, edges, loss=loss, link_loss=link_loss, seed=seed,
                         delay=delay or _simnet.fixed_delay(1),
                         rssi_range=rssi_range, macs=macs_for(nodes_ids), drop=drop)
    nodes = (node_factory or build_nodes)(net, weights, k, p)
    if scheduler == "sync":
        sc = _sched.SyncScheduler(net, nodes, tau_ms=tau_ms, weights=weights)
    elif scheduler == "async":
        sc = _sched.AsyncScheduler(net, nodes, tick_ms=tick_ms, seed=seed,
                                   weights=weights)
    else:
        raise ValueError(f"bilinmeyen zamanlayıcı: {scheduler!r}")
    out = sc.run(max_ms)
    # Koşum RAPORLANMADAN ÖNCE bootstrap kapısı: komşu tablosu taşan bir düğüm
    # yanlış bir dereceyle, dolayısıyla yanlış bir anahtarla donmuştur ve o
    # anahtar bütün MIS sıralamasını belirler. `RunInvalid` bilerek yükselir.
    validate_bootstrap(nodes.values())

    # KOŞUM DÜZEYİ SAYMA SINIRI. Düğümler bunu göremez (n ve m küresel), ama
    # sistem görebilir ve "çözemedim" ile "çözümü yok"u ayırt etmek bu ayrımın
    # taşıdığı anlamın tamamıdır.
    n_nodes, m_edges = len(net.nodes), len(net.edges)
    bound = counting_bound_infeasible(n_nodes, m_edges, k)
    _deg: Dict[int, int] = {}
    for _u, _v in net.edges:
        _deg[_u] = _deg.get(_u, 0) + 1
        _deg[_v] = _deg.get(_v, 0) + 1
    deficit = degree_deficiency_infeasible(
        (_deg.get(nid, 0) for nid in net.nodes), m_edges, k)
    node_flag = any(n.infeasible for n in nodes.values())
    if bound:
        reason = "counting_bound"
    elif deficit:
        reason = "degree_deficiency"
    elif node_flag:
        reason = "node"
    else:
        reason = ""
    bound = bound or deficit

    cover = sorted(nid for nid, n in nodes.items() if n.role.in_cover)
    # SAHİPLİK ÇAKIŞMASI ÇÖKERTİLMEZ.
    #
    # Eski hâli `owner[e] = nid` idi ve aynı kenarı İKİ UÇ birden iddia
    # ettiğinde ikinci yazan birinciyi sessizce eziyordu. Sonuç: harita 150
    # kenarın 150'sini kapsıyor, her kenarın tam bir sahibi görünüyor, hiçbir
    # düğüm taşkın görünmüyor ve doğrulayıcı GEÇİYOR -- oysa bir düğümün kendi
    # `owned` kümesinde k'den fazla kenar var ve o düğüm haklı olarak
    # `unresolved` diyor. Çifte iddianın TEK izi, düğümün özel görüşünün
    # toplamla çelişmesiydi ve hiçbir tüketici ona bakmıyordu.
    #
    # Problem tanımı her kenarın TAM BİR uca atanmasını ister (brief §1), yani
    # bu muhasebe hatası değil TANIM İHLALİDİR: kapasite argümanının tamamı
    # "her kenar bir kez sayılır" üzerine kuruludur.
    owner: Dict[Edge, int] = {}
    claims: Dict[Edge, List[int]] = {}
    for nid in sorted(nodes):
        for e in sorted(nodes[nid].owned):
            claims.setdefault(e, []).append(nid)
            owner[e] = nid
    double_claimed = {e: tuple(v) for e, v in claims.items() if len(v) > 1}
    unresolved = any(n.unresolved for n in nodes.values())
    verdict = ("truncated" if not out.converged
               else "unresolved" if unresolved else "solved")
    tot = out.totals()
    window = 5 * p.t_stale_ms if watch_ms is None else int(watch_ms)
    tx_after = (_tx_after_convergence(sc, window)
                if out.converged and window > 0 else None)
    state = [state_bytes(n) for n in nodes.values()]
    label = {n.nid: lab for lab, n in nodes.items()}
    frozen = {lab: {label.get(i, i) for i in (n._frozen_bidir or ())}
              for lab, n in nodes.items()}
    discovered = tuple(sorted({edge(u, v) for u, fs in frozen.items() for v in fs
                               if u in frozen.get(v, ())}))
    rounds = [r for r in (getattr(n, "mis_round", None) for n in nodes.values())
              if r is not None]
    return (result_cls or BbcvcRun)(
        outcome=out, nodes=nodes, net=net, cover=cover, owner=owner,
        total_weight=round(sum(weights[v] for v in cover), 6),
        tx=tot.tx, rx=tot.rx, retx=tot.retx, bytes_tx=tot.bytes_tx,
        max_payload=tot.max_payload, slots=out.slots, t_conv_ms=out.t_conv_ms,
        converged=out.converged,
        verdict=verdict,
        truncated=not out.converged,
        infeasible=bound or node_flag,
        infeasible_reason=reason,
        unresolved=unresolved,
        hello_change_tx=sum(n.hellos_change for n in nodes.values()),
        hello_periodic_tx=sum(n.hellos_periodic for n in nodes.values()),
        double_claimed=double_claimed,
        by_phase_tx=dict(tot.by_phase_tx), by_type_tx=dict(tot.by_type_tx),
        tree_root=next((n.tree_root for n in nodes.values()
                        if n.tree_parent is None and n.role.in_backbone), None),
        mis_depth=max(rounds) if rounds else None,
        restarts=max((n.epoch_advance for n in nodes.values()), default=0),
        tx_after_convergence=tx_after,
        state_bytes_max=max(state, default=0),
        state_bytes_mean=sum(state) / len(state) if state else 0.0,
        discovered_edges=discovered,
        infeasible_in_network=(lambda c: any(c) if c else None)(
            [n.cert_decided for n in nodes.values()
             if getattr(n, "cert_decided", None) is not None]),
    )
