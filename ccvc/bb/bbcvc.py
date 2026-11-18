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
"""
from __future__ import annotations

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
    experiments; it is off on the default path.
    """
    quiet_periods: int = 3       # .tex Phase 5a, T_q = 3 HELLO periods
    ack_periods: int = 3         # ACK timeout = 3 * T_hello (round trip is 2)
    ack_max_attempts: int = 3    # brief S3.4 R_max
    settle_steps: int = 1        # how many consecutive STEPS the barrier must hold
    gap_patience: int = 2        # patience before declaring a 3-hop gap
    escalate_patience: int = 2   # steps stuck before escalating
    max_repair_rounds: int = 4   # how many FULL ROUNDS the three stages retry

    def __post_init__(self) -> None:
        # Bootstrap's 100 ms LINK backoff produces spurious retransmissions even
        # on a LOSSLESS channel in this mode, where the round trip is a multiple
        # of a HELLO period (measured: 15 spurious retx). Wait a full round trip.
        if self.link_backoff_ms < 3 * self.t_hello_ms:
            self.link_backoff_ms = 3 * self.t_hello_ms
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
class PushJob:
    """Chain state kept while servicing an inbound PUSH (.tex on_push)."""

    src: int          # who sent me the PUSH
    seq: int          # their seq; my reply carries it back
    e: Edge           # the edge they want to hand me
    ttl: int          # the ttl I received
    tried: Set[int] = field(default_factory=set)
    probing: Optional[int] = None   # the neighbour I am probing right now
    probe_edge: Optional[Edge] = None


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

    # ---------------------------------------------------------------- state
    def _init_algo_state(self) -> None:
        # The answered-once record belongs to ONE DONE epoch. An epoch restart
        # rewinds the phase, so the neighbours that were answered in the old
        # epoch must be answerable again in the new one; see the half-finished
        # undo class in BULGULAR sections 90, 92, 93 and 97.
        self._answered_done: Set[int] = set()
        self._told_them_i_am_done: Optional[int] = None
        self._done_beacons: Dict[int, int] = {}
        self._repair_beacon = False
        self.owned: Set[Edge] = set()
        self._explicit: Dict[Edge, bool] = {}   # ownership settled by a transfer
        self.infeasible = False
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
        self._fix_key: Optional[Tuple[int, int]] = None   # the one active HANDOVER/PUSH
        #: Edges this node has offered in THIS epoch. Cleared with everything
        #: else by `_init_algo_state`, which is what makes a late ACK from a
        #: cancelled epoch distinguishable from a late ACK of a live transfer.
        self._offered: Set[Edge] = set()
        #: Edge -> how many times I have taken it. See `Pending.e_take`.
        self._takes: Dict[Edge, int] = {}
        self._seen: Dict[Tuple[int, int, int], bytes] = {}   # (peer,type,seq) -> reply
        self._push_job: Optional[PushJob] = None
        self._join_sent: Set[Tuple[int, int]] = set()        # (peer, reason)
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
        self._answered_done: Set[int] = set()
        self._told_them_i_am_done: Optional[int] = None
        self._done_beacons: Dict[int, int] = {}
        self._repair_beacon = False
        self._hello_dirty = True
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
        if self.phase < PH_DONE:
            return False
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
        """Only bidirectionally verified neighbours, in id order (determinism)."""
        return [self.nbrs[i] for i in sorted(self.nbrs) if self.nbrs[i].is_edge]

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
        """Her komşunun anahtarı donmuş mu? Donmadıysa karar verilmez, beklenir."""
        return self.key_fp is not None and all(n.key is not None for n in nb)

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
            self._log("mis_decided", role="OUT", reason="no_incident_edges")
            return
        mk = self._mykey()
        smaller = [n for n in nb if self._nkey(n) < mk]
        if any(n.role == Role.MIS for n in smaller):
            self.role = Role.OUT
            self.phase = PH_CONN
            self._log("mis_decided", role="OUT")
            self._touch()
        elif all(n.phase >= PH_CONN for n in smaller):
            self.role = Role.MIS
            self.phase = PH_CONN
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
        for n in outs[:need]:
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
        # stage 1: handover
        for n in peers:
            e = edge(self.nid, n.nid)
            if self._explicit.get(e) is False:
                continue
            if (n.nid, MsgType.HANDOVER, e) in self._tried:
                continue
            self._tried.add((n.nid, MsgType.HANDOVER, e))
            self._send_edge_msg(now, n, MsgType.HANDOVER, e, 0, tag="handover")
            return
        # stage 2: path reversal
        for n in peers:
            e = edge(self.nid, n.nid)
            if (n.nid, MsgType.PUSH, e, self._push_ttl) in self._tried:
                continue
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
            return   # my invitees have not joined yet; too early to cry INFEASIBLE

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
                   and (len(self.owned) <= self.k or self.infeasible
                        or self.unresolved))
        if self.phase == PH_OWN and settled:
            self.phase = PH_QUIET
            self._log("quiet")
            self._touch()
        if self.phase == PH_QUIET and all(n.phase >= PH_QUIET for n in nb):
            self.phase = PH_DONE
            self._log("done", weight=self.w, load=len(self.owned))
            self._touch()
        elif self.phase == PH_DONE and any(n.phase < PH_QUIET for n in nb):
            # A neighbour produced new work. Since a DONE node is SILENT,
            # staying silent would feed it to that neighbour's soft-state timer
            # and start an epoch reset (measured). I drop back to QUIET and
            # resume the liveness broadcast; once the neighbour settles I become
            # DONE again.
            self.phase = PH_QUIET
            self._touch()

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
        return all(n.phase >= PH_DONE for n in self.nbrs.values() if n.is_edge)

    def _maybe_hello(self, now: int) -> None:
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
        f = self.forced_load()
        mis = self.mis_nbrs()
        self.load = f          # bootstrap._hello_payload reads this field
        self._bcast(self._hello_payload(mis))
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
        """A quiescent node NEVER drops its neighbours.

        The reasoning is a matching pair: a DONE node stops broadcasting, so a
        neighbour that times it out changes its `bidir` set and starts an epoch
        reset. Since a node can only become DONE when ALL its neighbours are at
        >= QUIET, every neighbour of a silent node is inside this same gate; so
        silence and expiry can never catch each other.
        """
        if self.phase >= PH_QUIET:
            return
        super()._expire(now)

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
        if h.src != self.nid and h.src in self.nbrs:
            self._nbr_deg[h.src] = h.deg
        self._answer_a_neighbour_still_waiting(now, h)

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
        45 lossy ones converged. So each neighbour is answered at most once per
        DONE epoch, which keeps the exchange finite while still repairing the
        stale half; if that one answer is lost as well, the beacon is left to
        the neighbour and this node says nothing more.

        MEASURED on the discovered n15_m90 s3 graph at five per cent loss, seed
        1: all fifteen nodes reached PH_DONE with a valid cover, yet nodes 10,
        12 and 13 still recorded neighbours 14, 1, 15 and 6 at PH_QUIET and beaconed
        for ever. The run reported `truncated` at four times the budget.
        """
        if self.phase < PH_DONE or self._hello_dirty:
            return
        if getattr(h, "phase", 0) < PH_DONE or h.src == self.nid:
            return
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
        if h.src in self._answered_done:
            return
        seen = self._done_beacons.get(h.src, 0) + 1
        self._done_beacons[h.src] = seen
        if seen < 2:
            return
        # A LIVENESS BEACON, NOT AN EVENT. `_hello_dirty` marks a HELLO that
        # carries a STATE CHANGE, and the counter split exists to keep those two
        # apart. This repair changes nothing about my state; it repeats a fact I
        # already announced. Routing it through `_hello_dirty` would have moved
        # it into the event column (109 to 113 on the worked example) and made
        # the split say something untrue, so it is sent as what it is.
        self._answered_done.add(h.src)
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
        payload = wire.encode(wire.Join(MsgType.JOIN, self.nid, seq, code))
        self._join_sent.add((n.nid, code))
        self._arm(now, Pending(seq=seq, peer=n.nid, mtype=MsgType.JOIN,
                               payload=payload, tag=f"join{code}"))
        self._ucast(n, payload)

    def _send_edge_msg(self, now: int, n: BootNeighbor, mt: MsgType,
                       e: Edge, ttl: int, tag: str) -> None:
        seq = self._next_seq()
        payload = wire.encode(wire.EdgeMsg(mt, self.nid, seq, e[0], e[1], ttl))
        p = Pending(seq=seq, peer=n.nid, mtype=mt, payload=payload, e=e,
                    e_take=self._takes.get(e, 0) if e is not None else 0,
                    ttl=ttl, tag=tag)
        if mt in (MsgType.HANDOVER, MsgType.PUSH):
            self._offered.add(e)
        self._arm(now, p)
        self._fix_key = (n.nid, seq)
        self._ucast(n, payload)

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

    def _retry_pending(self, now: int) -> None:
        """THE single retransmission point. `log("retx")` lives here and only here."""
        for key in sorted(self._pending):
            p = self._pending.get(key)
            if p is None or now < p.next_ms:
                continue
            n = self._nbr(p.peer)
            if p.attempts >= self.p.ack_max_attempts or n is None:
                self._pending.pop(key, None)
                self._log("ack_gave_up", peer=p.peer, tag=p.tag, attempts=p.attempts)
                # An exhausted request is treated LIKE A NACK. Otherwise a PUSH
                # chain hangs forever in its `probing` field and the node never
                # repairs its own overload again (a measured deadlock).
                self._resolve(now, p, ok=False)
                continue
            p.attempts += 1
            p.next_ms = now + self._timeout_of(p) * (2 ** (p.attempts - 1))
            self._log("retx", n=1, peer=p.peer, tag=p.tag, attempt=p.attempts)
            self._ucast(n, p.payload)   # SAME seq: the receiver is idempotent

    def _reply(self, peer: int, payload: bytes, key: Tuple[int, int, int]) -> None:
        n = self._nbr(peer)
        self._seen[key] = payload
        if n is not None:
            self._ucast(n, payload)

    # ======================================================================
    # ALGORITHM MESSAGE HANDLERS (.tex "message handlers")
    # ======================================================================
    def _on_algo(self, now: int, src_mac: int, msg) -> None:
        peer = msg.src
        n = self.nbrs.get(peer)
        if n is None or n.mac != src_mac or not n.is_edge:
            return                       # unknown or unverified neighbour
        mt = msg.mtype
        if mt is MsgType.JOIN:
            self._on_join(now, n, msg)
        elif mt is MsgType.JOIN_ACK:
            self._on_ack(now, peer, msg.seq, ok=True)
        elif mt is MsgType.HANDOVER:
            self._on_handover(now, n, msg)
        elif mt is MsgType.PUSH:
            self._on_push(now, n, msg)
        elif mt in (MsgType.HANDOVER_ACK, MsgType.PUSH_ACK):
            if (peer, msg.seq) in self._pending:
                self._on_ack(now, peer, msg.seq, ok=True)
            else:
                self._on_late_ack(now, n, msg)
        elif mt in (MsgType.HANDOVER_NACK, MsgType.PUSH_NACK):
            self._on_ack(now, peer, msg.seq, ok=False)
        elif mt is MsgType.TREE:
            self._on_tree(now, n, msg)
        elif mt is MsgType.STABLE:
            self._on_stable(now, n, msg)
        elif mt is MsgType.FINISH:
            self._on_finish(now, n, msg)

    def _on_join(self, now: int, n: BootNeighbor, msg) -> None:
        """Someone invites me into the cover. Idempotent: I ACK even if already in."""
        key = (n.nid, int(MsgType.JOIN), msg.seq)
        if key in self._seen:
            self._reply(n.nid, self._seen[key], key)
            return
        if msg.code == JOIN_RELAY:
            # "Escalate on my behalf." I am already in the cover; what I must do
            # is invite MY OWN outside neighbour, so one of my forced edges
            # becomes flexible and I have budget to give the asker.
            self._relay_escalate(now)
        elif self.role == Role.OUT:
            self.role = Role.CONNECTOR if msg.code == JOIN_CONNECTOR else Role.COVER
            self.phase = max(self.phase, PH_FORCED)
            self._log("joined", by=n.nid, reason=msg.code, role=self.role.name)
            self._touch()
        ack = wire.encode(wire.Join(MsgType.JOIN_ACK, self.nid, msg.seq, 1))
        self._reply(n.nid, ack, key)

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
        if key in self._seen:
            self._reply(n.nid, self._seen[key], key)
            return
        e = edge(msg.u, msg.v)
        ok = not self._yields_to_inbound(e, n) and self._accept_edge(e)
        mt = MsgType.HANDOVER_ACK if ok else MsgType.HANDOVER_NACK
        self._reply(n.nid, wire.encode(wire.EdgeMsg(mt, self.nid, msg.seq, e[0], e[1])), key)

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
        mine_pending = any(p.e == e for p in self._pending.values())
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
        if self._explicit.get(e) is True:
            return True
        if e in self.owned:
            # The edge is currently mine by the DEFAULT rule. I still make the
            # acceptance explicit: otherwise the sender releases it
            # (`_explicit=False`) while I hold only a rule-derived trace, and
            # once F changes and the rule flips the edge is left UNOWNED.
            # Measured: on a 20-node UDG, (5,6) and (5,10) fell through this way.
            self._explicit[e] = True
            return True
        if len(self.owned) >= self.k:
            return False
        self._explicit[e] = True
        self.owned.add(e)
        self._touch()
        return True

    def _release_edge(self, e: Edge) -> None:
        self._explicit[e] = False
        self.owned.discard(e)
        self._touch()

    def _on_push(self, now: int, n: BootNeighbor, msg) -> None:
        """A chained transfer. With free budget it behaves like a handover;
        without it I push one of my own edges to another neighbour (ttl-1) and
        the chain grows that way."""
        key = (n.nid, int(MsgType.PUSH), msg.seq)
        if key in self._seen:
            self._reply(n.nid, self._seen[key], key)
            return
        e = edge(msg.u, msg.v)
        if self._yields_to_inbound(e, n):
            self._reply(n.nid, wire.encode(wire.EdgeMsg(
                MsgType.PUSH_NACK, self.nid, msg.seq, e[0], e[1])), key)
            return
        if self._accept_edge(e):
            self._reply(n.nid, wire.encode(wire.EdgeMsg(
                MsgType.PUSH_ACK, self.nid, msg.seq, e[0], e[1])), key)
            return
        if msg.ttl <= 0 or self._push_job is not None:
            self._reply(n.nid, wire.encode(wire.EdgeMsg(
                MsgType.PUSH_NACK, self.nid, msg.seq, e[0], e[1])), key)
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
        self._finish_push_job(ok=False)

    def _finish_push_job(self, ok: bool) -> None:
        job = self._push_job
        if job is None:
            return
        self._push_job = None
        # Even when the chain succeeds the acceptance can FAIL: the default rule
        # may have filled the slot I freed with another edge meanwhile. If
        # `_accept_edge`'s return value is IGNORED I send an ACK, the sender
        # releases the edge and I do not hold it: the edge is left UNOWNED.
        # Measured: (5,15) fell through exactly this way on a 15-node UDG.
        took = self._accept_edge(job.e) if ok else False
        mt = MsgType.PUSH_ACK if took else MsgType.PUSH_NACK
        key = (job.src, int(MsgType.PUSH), job.seq)
        self._reply(job.src, wire.encode(wire.EdgeMsg(
            mt, self.nid, job.seq, job.e[0], job.e[1])), key)

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
        job = self._push_job
        if (job is not None and job.probing == p.peer
                and job.probe_edge == p.e and p.mtype is MsgType.PUSH):
            job.probing = None
            job.probe_edge = None
            if ok:
                self._finish_push_job(ok=True)
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


def run_bbcvc(edges: Sequence[Edge], weights: Dict[int, float], k: int, *,
              scheduler: str = "sync", params: Optional[BbcvcParams] = None,
              max_ms: int = 200_000, loss: float = 0.0, seed: int = 0,
              delay=None, tau_ms: int = 200, tick_ms: int = 200,
              rssi_range=None, node_factory=None, result_cls=None) -> "BbcvcRun":
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
    """
    from ccvc.bb import sched as _sched
    from ccvc.bb import simnet as _simnet

    p = params or BbcvcParams()
    nodes_ids = sorted({a for e in edges for a in e} | set(weights))
    net = _simnet.SimNet(nodes_ids, edges, loss=loss, seed=seed,
                         delay=delay or _simnet.fixed_delay(1),
                         rssi_range=rssi_range, macs=macs_for(nodes_ids))
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
    )
