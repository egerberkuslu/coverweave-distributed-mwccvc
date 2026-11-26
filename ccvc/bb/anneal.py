#!/usr/bin/env python3
"""Anneal-Local: ANNEAL-CVC, the comparison algorithm against BB-CVC.

Source: brief section 6.5 and `plan/BB-CVC_Algoritma_Ornekli_Anlatim.tex` §13.

DIFFERENCE IN CHARACTER. BB-CVC is constructive: it builds the solution once,
a role only ever moves OUT -> COVER (api I5), and it stops. ANNEAL-CVC is
iterative: a node CAN LEAVE the cover, the process can be stopped at any moment
(anytime), and when stopped it reports the last valid solution it holds.

SO api I5 (role monotonicity) IS SUSPENDED FOR THE DURATION OF ANNEALING.
This is not a violation but the definition of the algorithm: "a method in which
nodes can leave the cover" is exactly this. From the freeze onwards roles are
fixed and Phase 4-5 sees an unchanging assignment. The tests verify both that
the suspension is real (roles are measured going back) and that everything is
stable after the freeze.

WHAT IS SHARED AND WHAT IS NOT.
  Shared: bootstrap (identity, neighbour discovery, key freezing), the HELLO
          carrier, Phase 4 (flexible edge ownership) and Phase 5 (termination)
          -- `BbcvcNode`'s OWN code, called without a line changed.
  Separate: only the "who is in the cover" decision. BB-CVC uses MIS + connector
          + expansion; here it is three local loops.

ENERGY (.tex §13.1)
    E = sum w(v)x_v + lam_c*(uncovered edges) + lam_k*sum max(0, ell_v - k)
        + lam_b*(components(G[C]) - 1)
    ell_v = F(v) + sum_{u: x_u=x_v=1} y_vu
Every lambda exceeds w_max, so no violation can be bought with a saving in
weight.

THREE LOOPS, ONE `on_timer` (.tex §13.2), NO EXTRA MESSAGE TYPES:
  A  flip    : Metropolis + token-based local exclusion (only on winning the token)
  B  balance : y <- clip(y + eta*(ell_u-ell_v)/2), IDENTICAL at both ends, message-free
  C  label   : label = min(id, neighbour labels), with root-counter staleness protection

ONE NODE IMPLEMENTATION, TWO SCHEDULERS. The temperature is derived from the
node's OWN period counter (`T = T0*alpha^floor(p/s)`). Synchronously each node
processes exactly one period per slot, so that counter COINCIDES with the global
slot counter and everyone shares a temperature; asynchronously the periods are
unaligned, so the temperature becomes node-local. One formula, two behaviours:
the node never ASKS which mode it is in.

Trickle (.tex §13.5) is a PARAMETER, not an inference. A node cannot work out
"I am synchronous" and switch itself off (if it could, I4 would already be
broken); the synchronous slot is fixed, so Trickle is disabled in that setup by
whoever configures the experiment.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import wire  # noqa: E402
from ccvc.bb.api import Counters, NodeSnapshot, Platform, Role  # noqa: E402
from ccvc.bb.bbcvc import (JOIN_ESCALATE, PH_DONE, PH_MIS, PH_OWN,  # noqa: E402
                           BbcvcNode, BbcvcParams, edge, macs_for)
from ccvc.bb.bootstrap import BootNeighbor, epoch_newer, xorshift32  # noqa: E402

#: The annealing phase. It reuses BB-CVC's PH_COVER slot: the meaning ("the
#: cover decision is being made") is the same, only the rule that makes it
#: differs. Neighbour phase comparisons (barriers) therefore keep working.
PH_ANNEAL = 3

Y_ONE = 1 << 8          # 1.0 in 8.8 fixed point
ELL_MAX_FP = 0xFFFF     # ceiling of the ell field on the wire


def f2fp(x: float) -> int:
    """To 8.8 fixed point, rounding to nearest."""
    return int(math.floor(x * Y_ONE + 0.5))


def fp2f(x: int) -> float:
    return x / float(Y_ONE)


@dataclass
class AnnealParams(BbcvcParams):
    """Defaults are the worked-example parameters of .tex §13.3."""

    lam_c: Optional[float] = None    # uncovered-edge penalty
    lam_k: Optional[float] = None    # overload penalty
    lam_b: Optional[float] = None    # disconnection penalty / bridge incentive
    repay_bridge_credit: bool = True
    """Whether leaving the cover repays the discount joining was granted.

    TRUE IS THE ONLY CORRECT SETTING; the flag exists so the defect can be
    REPRODUCED on demand rather than described from memory. With it False the
    energy function is not self-consistent: delta(join) + delta(leave) comes to
    -lam_b*(labels-1) instead of zero, so a node can flip back and forth and
    harvest energy forever. That is the whole of the bug documented in
    BULGULAR_BB.md §90, and `bridgefix_measure.py` turns it on and off to
    measure the difference instead of quoting it.
    """
    lam_scale: float = 2.0
    """lambda = lam_scale * w_max. The lambdas are NOT CONSTANTS; they are
    DERIVED from the instance.

    .tex §13.1 says "lam_c, lam_k, lam_b are chosen > w_max" and §13.3 uses 12.
    In that example w_max = 6, so 12 is not a constant but an instantiation of
    `2*w_max`. Applying the rule reproduces exactly 12 on the worked example and
    carries over to other instances.

    A FIXED 12 COLLAPSED THE ALGORITHM ON REAL DATA. In the Dagdeviren benchmark
    weights run from 26 to 94; with lambda = 12, leaving the cover gains up to
    94 while each uncovered edge costs only 12, so the penalty becomes BUYABLE
    with weight. The result: every node leaves and the cover comes back EMPTY
    (bb-figures: 195/195 rows, every node role=OUT).

    Deriving lambda from w_max is deployment-time configuration, exactly like k:
    a node cannot compute w_max on its own and receives it as a parameter. That
    is an assumption and the report must state it as one.
    """
    t0: Optional[float] = None   # initial temperature; if None, t0_scale*w_max
    alpha: float = 0.9           # geometric cooling
    t_min_temp: Optional[float] = None   # stopping temperature (named apart so
                                         # it cannot clash with BootstrapParams.t_min)
    t0_scale: float = 1.0
    t_min_frac: float = 0.05 / 6.0
    """Temperature is also IN UNITS OF ENERGY, so it scales with w_max too.

    .tex §13.3 gives T0 = 6 and T_min = 0.05; in that example w_max = 6, so
    T0 = w_max and T_min = (0.05/6)*T0. As with lambda, these are not constants
    but ratios expressed in terms of w_max.

    Left unscaled, the Metropolis rule `exp(-delta/T)` breaks: multiply the
    weights by twenty and delta grows twentyfold while T stays put, so the chain
    runs at effectively ZERO temperature and annealing silently degenerates into
    greedy descent. A VALID solution is still produced, so no gate catches the
    fault; the only thing lost is the entire reason for using annealing.

    With all three scaling together the algorithm becomes SCALE-INVARIANT:
    multiplying every weight by c multiplies the energy by c, the acceptance
    probabilities are unchanged, and the trajectory is bit-identical. This is
    asserted in the tests. `freeze_periods` depends only on the ratio T_min/T0,
    so it is already scale-free and stays 92.
    """
    cool_every: int = 2          # s: cool once every s periods
    eta: float = 1.0             # Loop B step size
    flip_quiet_periods: int = 3  # T_q: periods the neighbourhood must go without a flip
    trickle: bool = False        # .tex §13.5; OFF in the synchronous setup
    t_hello_max_ms: int = 0
    """Trickle ceiling. 0 = the largest value soft state permits.

    .tex §13.5 wants the period doubled up to `T_max`, but the soft-state rule
    of §3.4 DROPS a neighbour that is not refreshed within
    `stale_periods*T_hello`, and that threshold is computed AT THE RECEIVER from
    ITS OWN `T_hello`. The sender's extended period is never ANNOUNCED on the
    wire, so the receiver cannot know about it: the moment the period crosses
    the threshold, neighbours drop each other, the bidirectional set changes,
    the epoch resets and the run never converges. Measured: with a 1600 ms
    ceiling, 20 of 20 asynchronous runs ended invalid and transmissions went UP
    from 1122 to 3268 instead of DOWN.

    So the ceiling is kept below the soft-state window. The real fix is to put
    the period in the HELLO; that wire change was not requested for this work.
    """

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.t_hello_max_ms:
            # stay under the threshold: speak before a neighbour drops me
            self.t_hello_max_ms = max(self.t_hello_ms,
                                      (self.stale_periods - 1) * self.t_hello_ms)
    rng_seed: int = 0            # node-local xorshift32 seed


    def resolved(self, weights) -> "AnnealParams":
        """Return a COPY with the lambdas derived from the instance's w_max.

        Explicitly supplied lambdas are left alone; only the None ones are filled.
        """
        import dataclasses
        wmax = max(float(w) for w in weights) if weights else 1.0
        lam = self.lam_scale * wmax
        t0 = self.t0 if self.t0 is not None else self.t0_scale * wmax
        return dataclasses.replace(
            self,
            lam_c=self.lam_c if self.lam_c is not None else lam,
            lam_k=self.lam_k if self.lam_k is not None else lam,
            lam_b=self.lam_b if self.lam_b is not None else lam,
            t0=t0,
            t_min_temp=(self.t_min_temp if self.t_min_temp is not None
                        else self.t_min_frac * t0),
        )

    @property
    def freeze_periods(self) -> int:
        """I = s*ceil(log(T_min/T0)/log alpha) (.tex §13.6). 92 with the example values."""
        # Depends only on the RATIO T_min/T0, so it is scale-free.
        frac = (self.t_min_frac if self.t0 is None or self.t_min_temp is None
                else self.t_min_temp / self.t0)
        n = math.ceil(math.log(frac) / math.log(self.alpha))
        return self.cool_every * int(n)


@dataclass
class PeerState:
    """A neighbour's ANNEAL tail from its HELLO, plus when it was heard."""

    x: bool
    ell_fp: int
    label: int
    label_ctr: int
    token: int
    cool: int
    heard_ms: int
    hops: int = 0          # T1: hop count of `label`
    bridge: bool = False   # T2: OUT and two or more labels among its cover neighbours


class AnnealNode(BbcvcNode):
    """One node's ANNEAL-CVC implementation. It CANNOT SEE the graph (api I1)."""

    def __init__(self, weight, platform: Platform,
                 params: Optional[AnnealParams] = None, capacity_k: int = 2) -> None:
        super().__init__(weight, platform, params or AnnealParams(), capacity_k)
        self.p: AnnealParams = self.p
        self._check_lambdas()
        self._init_anneal_state()

    def _check_lambdas(self) -> None:
        """lambda > w_v is LOCALLY checkable, and it must be checked.

        A node cannot know w_max but it does know ITS OWN weight, and if
        lambda <= w_v then that node alone can buy a violation with a saving in
        weight. This is a locally checkable NECESSARY condition for the global
        invariant.

        Staying silent meant producing an EMPTY COVER on real data while
        reporting "converged=True"; failing loudly beats producing a wrong number.
        """
        lam = (self.p.lam_c, self.p.lam_k, self.p.lam_b)
        if self.p.t0 is None or self.p.t_min_temp is None:
            raise ValueError(
                "temperature unresolved: T0 and T_min scale with w_max too; "
                "AnnealParams.resolved(weights) must be called")
        if any(v is None for v in lam):
            raise ValueError(
                "lambda unresolved: a node cannot be built without calling "
                "AnnealParams.resolved(weights) (lambda is derived from the "
                "instance, it is not a constant)")
        if min(lam) <= self.w:
            raise ValueError(
                f"lambda={min(lam)} <= w={self.w} (node {getattr(self, 'nid', '?')}). "
                f".tex §13.1 requires lambda > w_max; once that is broken a "
                f"violation can be bought with weight and the cover empties.")

    # ------------------------------------------------------------- durum
    def _init_anneal_state(self) -> None:
        # .tex: initial x_v = 1, everyone in the cover -- valid but heavy
        self.x = 1
        self.role = Role.COVER
        self.y: Dict[int, int] = {}          # neighbour id -> my share (8.8)
        self.peer: Dict[int, PeerState] = {}
        self.label = 0                       # nid bilinince kurulur
        self.label_ctr = 0
        self.label_hops = 0                  # T1 (Amendment 16)
        self._bridge = False                 # T2: advertised obligation flag
        self._label_src_ctr: Optional[int] = None
        self._label_fresh_ms = 0
        #: A dropped label and the highest counter seen for it at the moment it
        #: was dropped. Without this a stale label NEVER DIES: the node that
        #: dropped it immediately re-adopts it from a neighbour that has not
        #: dropped it yet, resetting its own clock (count-to-infinity).
        #: The bridge discount this node was GIVEN when it joined, and still
        #: owes. See `_delta_e`: the discount is granted on 0->1 and must be
        #: charged back on 1->0, otherwise joining and leaving are both downhill
        #: and the node oscillates forever.
        self._bridge_credit: float = 0.0
        self._stale_label: Optional[int] = None
        self._stale_ctr = 0
        self.token = 0
        self.periods = 0
        self.flips = 0
        self.frozen = False
        self.frozen_ms: Optional[int] = None
        self._adv_ell_fp = 0
        self._quiet_periods = 0
        self._last_seen_flip: Dict[int, bool] = {}
        self._t_hello_cur = self.p.t_hello_ms
        self._escalations = 0
        # measurement: transient violations LOCALLY VISIBLE (an edge with both
        # endpoints outside the cover)
        self.periods_with_violation = 0
        self._rng = 0

    # --------------------------------------------------------- helpers
    @property
    def temperature(self) -> float:
        return self.p.t0 * (self.p.alpha ** self.cool_index)

    @property
    def cool_index(self) -> int:
        return min(self.periods // self.p.cool_every, wire.COOL_MAX)

    def _rand16(self) -> int:
        if self._rng == 0:
            seed = (self.p.rng_seed * 2654435761) ^ (self.mac & 0xFFFFFFFF)
            self._rng = (seed & 0xFFFFFFFF) or 0x1234567
        self._rng = xorshift32(self._rng)
        return self._rng & 0xFFFF

    def _rand_unit(self) -> float:
        return self._rand16() / 65536.0

    def _peers(self, nb: Sequence[BootNeighbor]) -> List[Tuple[BootNeighbor, PeerState]]:
        out = []
        for n in nb:
            ps = self.peer.get(n.nid)
            if ps is not None:
                out.append((n, ps))
        return out

    def _fresh(self, ps: PeerState, now: int) -> bool:
        """Token freshness (.tex §13.5): a token older than one HELLO period
        does not count as having "won"."""
        return now - ps.heard_ms <= self._t_hello_cur

    def _over(self, ell: float) -> float:
        return max(0.0, ell - self.k)

    def _forced(self, peers) -> int:
        """F(v): the number of neighbours outside the cover. Undefined when
        x_v = 0, where it returns 0."""
        return sum(1 for _, ps in peers if not ps.x) if self.x else 0

    def _ell(self, peers) -> float:
        if not self.x:
            return 0.0
        tot = self._forced(peers) * Y_ONE
        for n, ps in peers:
            if ps.x:
                tot += self.y.get(n.nid, Y_ONE // 2)
        return fp2f(tot)

    # ================================================================ HELLO
    def _anneal_block(self) -> wire.Anneal:
        return wire.Anneal(x=bool(self.x), ell_fp=min(self._adv_ell_fp, ELL_MAX_FP),
                           label=self.label or self.nid, label_ctr=self.label_ctr,
                           token=self.token, cool=self.cool_index,
                           hops=min(self.label_hops, wire.HOPS_MAX),
                           bridge=self._bridge)

    def _hello_payload(self, mis_nbrs: Tuple[int, ...] = ()) -> bytes:
        """Keep bootstrap's PRODUCER-side checks (G8, deg, key type) exactly as
        they are and append the ANNEAL tail. The checks are not copied: two
        copies would need separate maintenance and would drift apart."""
        h = wire.decode(super()._hello_payload(mis_nbrs))
        h.anneal = self._anneal_block()
        return wire.encode(h)

    def _maybe_hello(self, now: int) -> None:
        before = self._last_hello_ms
        super()._maybe_hello(now)
        if self._last_hello_ms != before and self.p.trickle:
            self._hello_due_ms = now + self._t_hello_cur

    def _on_hello(self, now: int, src_mac: int, rssi, h) -> None:
        super()._on_hello(now, src_mac, rssi, h)
        if h.anneal is None:
            return
        a = h.anneal
        prev = self.peer.get(h.src)
        if prev is not None and prev.x != a.x:
            self._last_seen_flip[h.src] = True
        self.peer[h.src] = PeerState(x=a.x, ell_fp=a.ell_fp, label=a.label,
                                     label_ctr=a.label_ctr, token=a.token,
                                     cool=a.cool, heard_ms=now, hops=a.hops,
                                     bridge=a.bridge)

    def _send_join(self, now: int, n: BootNeighbor, code: int) -> None:
        if code == JOIN_ESCALATE:
            self._escalations += 1
        super()._send_join(now, n, code)

    # ========================================================= durum makinesi
    def _step(self, now: int) -> None:
        if self.phase < PH_MIS:
            return                       # the bootstrap gate has not opened yet
        nb = self._nbrs_active()
        if not self._keys_ready(nb):
            return
        if not self.label:
            self.label = self.nid

        if not self.frozen:
            if self.phase < PH_ANNEAL:
                self.phase = PH_ANNEAL
                self._touch()
            self._anneal_period(now, nb)
            return

        # LOOP C KEEPS RUNNING AFTER THE FREEZE. This is an OBSERVATION, not a
        # decision: a label does not change x. But `on_frame` keeps advancing the
        # neighbour table after the freeze, so if Loop C stops, the label layer
        # freezes behind reality and a disconnection becomes INVISIBLE (see the
        # note below).
        self._loop_c(now, self._peers(nb))
        # T2 (Amendment 16): a frozen OUT node that sees two labels still joins;
        # a join of an OUT node with a cover neighbour keeps the cover connected.
        self._bridge = self._bridge_obliged(self._peers(nb))
        if self._bridge:
            self._join_frozen(self._peers(nb))

        # PHASE 3'S REPAIR, WHICH THE ANNEALER USED TO JUMP STRAIGHT OVER.
        # The freeze sets `phase = PH_OWN`, so PH_FORCED is never occupied and
        # `_rule_forced` -- the only caller of the repair below -- never runs.
        # Reaching it needs no new rule: the repair's own guard already asks
        # exactly the question the freeze answers. See the override.
        self._cover_what_the_key_election_missed(nb)   # Phase 3

        # FROZEN: everything past here is BB-CVC's OWN code, unchanged.
        self._rule_ownership(now, nb)     # Phase 4
        self._quiescence(now, nb)         # Phase 5a
        if self.p.enable_tree:
            self._tree_step(now, nb)      # Phase 5b

    def _anneal_period(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        peers = self._peers(nb)
        self.periods += 1

        self._loop_b(peers)               # denge
        label_moved = self._loop_c(now, peers)   # etiket; T1: (label, hops)
        self._observe_violation(peers)

        token_prev = self.token
        self.token = self._rand16()       # this token is for the NEXT period

        flipped = False
        if self._holds_token(now, peers, token_prev):
            flipped = self._loop_a(peers)
        # A descent step I COULD NOT TAKE because I lost the token is also a
        # "change pending" state; it resets the quiescence counter below.
        # T2: a bridge obligation is pending whatever the energy change.
        pending = (not flipped) and (self._delta_e(self._peers(nb)) < 0
                                     or self._bridge_obliged(self._peers(nb)))
        self._bridge = self._bridge_obliged(self._peers(nb))

        # The advertised ell that Phase 4 reads is refreshed IMMEDIATELY before
        # the HELLO goes out
        self._adv_ell_fp = f2fp(self._ell(self._peers(nb)))
        # The neighbour-flip observation is consumed ONCE per period. Clearing
        # it inside `_trickle` left the flag permanently set whenever Trickle was
        # off, so the quiescence counter never advanced at all.
        nbr_flip = any(self._last_seen_flip.values())
        self._last_seen_flip.clear()
        self._trickle(flipped or nbr_flip)
        # T1 (Amendment 16) now adds `label_moved`, a change of (label, hops),
        # to the quiescence counter. The earlier attempt below failed on the
        # since-fixed repay bug; the hop bound makes a dead label die in
        # bounded time, so the label stops moving once the cover does.
        #
        # TRIED AND REVERTED: adding `label_moved` to the quiescence counter.
        # The idea was that a node whose component label is still moving has not
        # gone quiet. It MEASURABLY MADE THINGS WORSE: on n50_m100 seed 3 async
        # the run went from `solved` in 143 periods to `truncated` at 39,994,
        # because the label churn is DRIVEN by a node that oscillates forever
        # (see `_loop_a`), so gating the freeze on the label let that one node
        # hold the whole run open. The label not converging is a SYMPTOM of the
        # oscillation, not its cause, and freezing on it treats the symptom.
        self._maybe_freeze(now, flipped or nbr_flip or pending or label_moved,
                           self._peers(nb))

    # ------------------------------------------------------- Loop A: the flip
    def _holds_token(self, now: int, peers, mine: int) -> bool:
        """Local exclusion: is my token smaller than every FRESH neighbour token?

        Ties break by id. With 16-bit tokens ties genuinely occur, and if they
        are not broken two neighbours can flip in the same period; preventing
        exactly that is the only job exclusion has.
        engellemektir.
        """
        for n, ps in peers:
            if not self._fresh(ps, now):
                continue
            if (ps.token, n.nid) < (mine, self.nid):
                return False
        return True

    def _delta_e(self, peers) -> float:
        """The LOCAL energy difference of flipping x_v (.tex §13.2, Loop A).

        Computed only from neighbours' x, ell and label values; no global
        quantity is ever read.
        """
        lam_c, lam_k, lam_b = self.p.lam_c, self.p.lam_k, self.p.lam_b
        outs = [(n, ps) for n, ps in peers if not ps.x]
        covs = [(n, ps) for n, ps in peers if ps.x]

        if self.x:
            # 1 -> 0 : I am leaving the cover
            d = -float(self.w)
            d += lam_c * len(outs)                  # these edges become uncovered
            d -= lam_k * self._over(self._ell(peers))
            for n, ps in covs:
                # (v,u) goes from flexible to FORCED. u's share moves from
                # (1 - y_vu) to 1.0, so its load rises by EXACTLY MY SHARE.
                # Writing (1 - y_vu) gives the same answer at y = 1/2, and every
                # opening move in the worked example is at y = 1/2, so that bug
                # is INVISIBLE to hand-checking: it only diverges once the load
                # has been balanced, precisely at the overloaded node.
                ell_u = fp2f(ps.ell_fp)
                mine = fp2f(self.y.get(n.nid, Y_ONE // 2))
                d += lam_k * (self._over(ell_u + mine) - self._over(ell_u))
            # THE BRIDGE DISCOUNT IS A DEBT, AND LEAVING REPAYS IT.
            #
            # .tex says "a cut vertex cannot know that it is a cut vertex", and
            # that is true: from INSIDE the cover my neighbours' labels have
            # already merged, so the evidence for the bridge is gone and there
            # is nothing left to measure. The previous reading of that sentence
            # was "therefore charge nothing", which made the energy function
            # INCONSISTENT: joining paid -lam_b*(labels-1) and leaving paid
            # nothing back, so a node could join for the discount, leave for
            # free, and join again for the discount a second time. A discount
            # that is never repaid is a perpetual energy source.
            #
            # MEASURED on n50_m100 seed 1: delta(join) + delta(leave) came to
            # exactly -lam_b*(labels-1) every time -- -2400 with two labels,
            # -4800 with three, -7200 with four -- never zero, while every
            # capacity term was zero. One node flipped 12,493 times and never
            # reached quiescence, which held the whole run open until the budget
            # ran out. The cover churning under it is also why the component
            # labels never converged: that was a SYMPTOM of this, not a cause.
            #
            # So the node REMEMBERS what it was given and repays it. The pair
            # now sums to zero, which is the only thing that makes "downhill"
            # mean anything.
            d += self._bridge_credit
        else:
            # 0 -> 1 : I am joining the cover
            d = +float(self.w)
            d -= lam_c * len(outs)                  # these edges become covered
            new_ell = len(outs) + 0.5 * len(covs)   # new flexible shares start at 1/2
            d += lam_k * self._over(new_ell)
            for n, ps in covs:
                # (v,u) was FORCED for u and becomes flexible: its load drops by 1 - 1/2
                ell_u = fp2f(ps.ell_fp)
                d += lam_k * (self._over(ell_u - 0.5) - self._over(ell_u))
            labels = {ps.label for _, ps in covs}
            if len(labels) > 1:                     # I am a bridge: I merge components
                d -= lam_b * (len(labels) - 1)
        return d

    def _reset_to_phase0(self, now: int, reason: str) -> None:
        """An epoch restart must restart the ANNEALER too, not only bootstrap.

        The base class rewinds the bootstrap: phase, key, degree and the frozen
        neighbourhood all go back. The annealing state used to survive, and it
        is the annealing state that decides anything. `periods` drives the
        temperature, so a node that had already cooled stayed cold through the
        restart; `frozen` short-circuits `on_period` entirely, so a node that
        had already frozen never annealed again at all.

        MEASURED on dag_anneal_n20_m160 seed 2 and dag_anneal_n15_m90 seed 3:
        after the LAST reset only 36 and 29 periods passed before every node
        went quiet, while cooling to `t_min_temp` takes 92 and `_maybe_freeze`
        returns early above that temperature. Freezing that early is only
        possible if the clock never rewound. Both runs ended `converged` with
        an EMPTY cover and every node's role OUT, because a cold frozen node
        keeps whatever x it had and a restart leaves that at zero.

        The bridge credit goes with them: it is a debt recorded against a
        neighbourhood that the restart has just discarded.

        AND SO DOES x. THE COVER BIT LIVES IN TWO FIELDS AND THE RESTART ONLY
        REWOUND ONE. `BbcvcNode._reset_to_phase0` forces `role = OUT`, which is
        right for a constructive algorithm that rebuilds its cover from nothing;
        the annealer's `x` is the SAME BIT and it was left untouched, so after a
        restart a node advertised x = 1 in its ANNEAL tail while REPORTING
        role = OUT. Nothing detects the split: every neighbour sees a covered
        node, every edge looks covered, no delta is downhill, everyone freezes
        on the first schedule -- and the reported cover is EMPTY, because the
        cover is read off `role`.

        MEASURED on the nine discovered wireless graphs (n=10/15/20), three
        seeds x four loss levels, 108 sync runs: 33 runs suffered an epoch
        restart and ALL 33 came out with x != role (up to 18 of 20 nodes), 30 of
        those 33 were INVALID, and 5 reported `solved` with a cover of size
        ZERO. Those 33 runs were also the ONLY invalid runs in the sweep. After
        this line the same 108 runs give 0 mismatches and 0 empty covers.

        .tex S13 opens the chain at x_v = 1 for everyone ("valid but heavy"), so
        that -- not OUT -- is what a restart must restore. The shares y go with
        it: they are per-edge state defined against the neighbourhood the
        restart has just discarded, exactly like the bridge credit.
        """
        super()._reset_to_phase0(now, reason)
        self.periods = 0
        self.frozen = False
        self.frozen_ms = None
        self._quiet_periods = 0
        self._bridge_credit = 0.0
        self.x = 1
        self.role = Role.COVER
        self.y = {}
        self._bridge = False

    def _bridge_discount(self, peers) -> float:
        """What joining right now would discount me, as a debt to record.

        Kept beside `_delta_e` and computed the same way, so the amount charged
        back on leaving is exactly the amount granted on joining and the two
        cannot drift apart.
        """
        labels = {ps.label for _, ps in peers if ps.x}
        return self.p.lam_b * (len(labels) - 1) if len(labels) > 1 else 0.0

    def _bridge_obliged(self, peers) -> bool:
        """T2 (Amendment 16): am I OUT with two or more labels among my cover
        neighbours? V \\ C is independent when C covers, so C is connected
        exactly when no OUT node touches two cover components."""
        return not self.x and len({ps.label for _, ps in peers if ps.x}) > 1

    def _join_frozen(self, peers) -> None:
        """Join after the freeze, rebuilding the anneal state as `_loop_a` does."""
        self.x = 1
        self.role = Role.COVER
        self._bridge = False
        self.y = {n.nid: Y_ONE // 2 for n, ps in peers if ps.x}
        self._adv_ell_fp = f2fp(self._ell(peers))
        self._touch()

    def _loop_a(self, peers) -> bool:
        """Metropolis. At T <= T_min no UPHILL step remains, but DESCENT CONTINUES.

        The .tex algorithm gates Loop A on `T > T_min`. That reading CONTRADICTS
        the same document's own claim: "energy minima are exactly the valid
        solutions", with a stopping rule of "T <= T_min AND no flip for T_q".
        If Loop A shuts off entirely once cold then no flip can occur anyway, so
        the T_q condition is vacuous in the synchronous case and the chain stops
        NOT at a local minimum but wherever the temperature schedule ran out.
        Disconnection repair (the bridge incentive, delta = -lam_b + w < 0) is
        precisely a descent step, so the closing gate closes the repair too:
        measured, 24 of 60 frozen states came out disconnected.

        So the gate is applied to the ACCEPTANCE RULE rather than to the
        temperature: when cold only delta < 0 is accepted, the chain descends to
        a genuine local minimum, and the stopping condition regains its meaning.
        The deviation has been reported.
        """
        d = self._delta_e(peers)
        t = self.temperature
        if d < 0 or self._bridge_obliged(peers):
            accept = True                # T2: the bridge join is never refused
        elif t <= self.p.t_min_temp:
            accept = False               # zero temperature: descent only
        else:
            accept = self._rand_unit() < math.exp(-d / t)
        if not accept:
            return False
        # RECORD THE DEBT AT THE MOMENT IT IS TAKEN. The discount is computed
        # from the labels I can see RIGHT NOW; a moment later they merge and the
        # evidence is gone, so it cannot be recovered afterwards and has to be
        # written down here.
        if self.x:
            self._bridge_credit = 0.0            # leaving: the debt is settled
        elif self.p.repay_bridge_credit:
            self._bridge_credit = self._bridge_discount(peers)
        self.x = 1 - self.x
        self.role = Role.COVER if self.x else Role.OUT
        self.flips += 1
        # .tex: "reset/initialise the relevant y values"
        self.y = {n.nid: Y_ONE // 2 for n, ps in peers if ps.x} if self.x else {}
        self._touch()
        return True

    # ------------------------------------------------- Loop B: load balancing
    def _loop_b(self, peers) -> None:
        """y ← clip(y + η(ℓ_u−ℓ_v)/2), MESAJSIZ.

        The CONDITION for being message-free is that both ends produce the same
        number. Two choices guarantee it and both are mandatory:

        1. Both ends use the ADVERTISED ell values. An end that used its own
           instantaneous ell would compute with a number its neighbour has not
           heard yet, and the shares would diverge. (The same lesson was already
           paid for on F in `bbcvc._default_owner`.)
        2. The step is computed in the CANONICAL DIRECTION: a single integer d,
           applied as +d at the lower-id end and -d at the higher-id end. If each
           end rounded in its own direction the rounding might not be
           antisymmetric and y_uv + y_vu = 1 would break.
        """
        if not self.x:
            self.y = {}
            return
        alive = set()
        for n, ps in peers:
            if not ps.x:
                continue                       # not flexible: a forced edge
            alive.add(n.nid)
            mine = self.y.setdefault(n.nid, Y_ONE // 2)
            lo_is_me = self.nid < n.nid
            ell_lo = self._adv_ell_fp if lo_is_me else ps.ell_fp
            ell_hi = ps.ell_fp if lo_is_me else self._adv_ell_fp
            scale = max(self._deg_of(n), self.deg or 1, 1)
            d = self._balance_step(ell_lo, ell_hi, scale)
            mine += d if lo_is_me else -d
            self.y[n.nid] = max(0, min(Y_ONE, mine))
        for gone in [i for i in self.y if i not in alive]:
            del self.y[gone]

    def _balance_step(self, ell_lo_fp: int, ell_hi_fp: int, scale: int) -> int:
        """The INTEGER step to add to the lower-id end's share.

        Computed once in the canonical direction; the other end subtracts the
        same number, so antisymmetry is established INDEPENDENTLY of rounding.

        DIVIDING BY THE DEGREE IS MANDATORY, .tex DOES NOT SAY SO, and it never
        gives eta at all. Because the formula is applied separately to every
        flexible edge, a node's total load moves by deg*eta*delta_ell/2 in one
        period; at eta = 1 and deg = 4 that is 2*delta_ell, so the step
        overshoots its target twofold and the iteration DOES NOT CONVERGE, it
        oscillates. Measured: node 4's load swung between 4.0 and 0.0 period by
        period, and sampled every second period it looked like a "stable but
        unbalanced" fixed point -- the oscillation only became visible when
        looking at every period.

        The scale is max(deg_u, deg_v): a quantity BOTH ends know (deg is a
        HELLO field) and a SYMMETRIC one. Dividing by one's own degree is
        tempting and wrong; the two ends would produce different numbers and the
        invariant y_uv + y_vu = 1 would break.
        """
        raw = self.p.eta * (ell_hi_fp - ell_lo_fp) / (2.0 * scale)
        return int(math.floor(raw + 0.5)) if raw >= 0 else -int(math.floor(-raw + 0.5))

    # --------------------------------------------- Loop C: component label
    def _loop_c(self, now: int, peers) -> bool:
        """label = min(id, labels of cover neighbours), with the root counter.

        RETURNS whether my label moved this period. THE LABEL IS PART OF MY
        STATE, so a node whose label is still changing has NOT gone quiet, and
        the freeze must not fire on it. Measured consequence of leaving it out
        below, in `_maybe_freeze`.

        THE STALE-LABEL RULE IS SUBTLE AND THE FIRST VERSION WAS WRONG. Freshness
        cannot be measured as "does the counter of the neighbour I picked differ
        from last time": of two neighbours carrying the same label, one may be
        lagging in the wave, and if I keep picking that one the counter appears
        to have stopped, I drop the label, and I re-adopt it next period. The
        result is LABEL DIVERSITY THAT IS NOT REAL, and the bridge incentive in
        Loop A fires on that noise: measured, it was pulling nodes back into the
        cover even on a connected graph.

        The correct rule: keep the NEWEST counter SEEN per label, and reset the
        freshness clock only on a counter that genuinely advanced. The counter is
        one byte and therefore wraps, so the comparison goes through
        `epoch_newer`.
        """
        # ONLY THE LABEL AND ITS HOPS, NOT THE COUNTER. The root advances its
        # counter every single period as a heartbeat, so comparing the counter
        # too would make every root permanently non-quiescent and no run would
        # ever freeze. T1 (Amendment 16): the hop count is the distance to the
        # label's root along cover nodes; a dead label's hops rise every period
        # (count to infinity), so it keeps its holders non-quiet until it
        # exceeds the node bound n_bar and dies.
        before = (self.label, self.label_hops)
        nbar = min(self.p.n_bound or wire.HOPS_MAX, wire.HOPS_MAX)
        if not self.x:
            self.label, self.label_ctr, self.label_hops = self.nid, 0, 0
            self._label_src_ctr = None
            return before != (self.label, self.label_hops)

        best = self.nid
        best_ctr: Optional[int] = None
        best_hops = 0
        for _, ps in peers:
            if not ps.x:
                continue                       # a node outside the cover has no label
            if self._is_stale(ps.label, ps.label_ctr):
                continue                       # dead label: I do not re-adopt it
            if ps.hops + 1 > nbar:
                continue                       # T1: dead whatever the heartbeat says
            if ps.label < best:
                best, best_ctr, best_hops = ps.label, ps.label_ctr, ps.hops + 1
            elif ps.label == best and best_ctr is not None:
                # same label, take the counter that is further along the wave
                if epoch_newer(ps.label_ctr, best_ctr):
                    best_ctr = ps.label_ctr
                best_hops = min(best_hops, ps.hops + 1)

        if best == self.nid:
            # I am the root of my own component: I advance the counter
            self.label = self.nid
            self.label_ctr = (self.label_ctr + 1) & 0xFF
            self.label_hops = 0
            self._label_src_ctr = None
            self._label_fresh_ms = now
            return before != (self.label, self.label_hops)

        if best != self.label:
            self.label, self.label_ctr = best, best_ctr or 0
            self.label_hops = best_hops
            self._label_src_ctr = best_ctr
            self._label_fresh_ms = now          # new label: the clock resets
            return True

        self.label_hops = best_hops
        if best_ctr is not None and (self._label_src_ctr is None
                                     or epoch_newer(best_ctr, self._label_src_ctr)):
            self._label_src_ctr = best_ctr      # the counter GENUINELY advanced
            self.label_ctr = best_ctr
            self._label_fresh_ms = now
        elif now - self._label_fresh_ms > 3 * self._t_hello_cur:
            # the root has been unheard for 3 periods: KILL the label and
            # remember it as dead
            self._stale_label = self.label
            self._stale_ctr = self._label_src_ctr or 0
            self.label, self.label_ctr, self.label_hops = self.nid, 0, 0
            self._label_src_ctr = None
            self._label_fresh_ms = now
        return before != (self.label, self.label_hops)

    def _is_stale(self, label: int, ctr: int) -> bool:
        """Is this the label I killed, and is its root still silent?

        If the root is heard again (the counter HAS ADVANCED) the label revives
        and leaves the dead list; that is exactly what happens when components
        merge back together.
        """
        if self._stale_label is None or label != self._stale_label:
            return False
        if epoch_newer(ctr, self._stale_ctr):
            self._stale_label = None           # the root came back
            return False
        return True

    # --------------------------------------------- measurement / stopping
    def _observe_violation(self, peers) -> None:
        """A transient violation that is LOCALLY visible: an edge with both
        endpoints outside the cover."""
        if not self.x and any(not ps.x for _, ps in peers):
            self.periods_with_violation += 1

    def _trickle(self, changed: bool) -> None:
        if not self.p.trickle:
            return
        if changed:
            self._t_hello_cur = self.p.t_hello_ms
        else:
            self._t_hello_cur = min(2 * self._t_hello_cur, self.p.t_hello_max_ms)

    def _maybe_freeze(self, now: int, changed: bool, peers=()) -> None:
        """.tex: T <= T_min AND no flip in the neighbourhood for T_q -> freeze.

        "NO FLIP" IS NOT ENOUGH; "NOBODY WANTS TO FLIP" IS WHAT IS NEEDED. Token
        exclusion can silence a node for consecutive periods: it has a step with
        delta < 0 but never manages to win the token. A counter based on
        observation mistakes that for quiescence. In a neighbourhood with five
        contenders the probability of losing the token three periods running is
        about 0.5, so this is NOT a rare corner case but typical behaviour:
        measured, 20 of 60 frozen states were disconnected, and the bridge step
        that would have repaired them (delta around -33) had been starved out in
        exactly this way.

        HONESTY NOTE. After Loop C's count-to-infinity bug was fixed, this gate
        does no MEASURABLE work: across 60 seeds the gated and ungated versions
        give the same result (both 0 invalid, 0 freezes outside a local minimum).
        It stays anyway, because what it provides is not a measured result but a
        GUARANTEE: the frozen state being a local minimum follows from here, not
        from an observation-based counter. The real cause of the disconnections
        was not this gate but the stale label failing to die; that bug is
        described in `_loop_c`.
        """
        if changed:
            self._quiet_periods = 0
        else:
            self._quiet_periods += 1
        if self.temperature > self.p.t_min_temp:
            return
        if self._quiet_periods < self.p.flip_quiet_periods:
            return
        if any(not ps.x and ps.bridge for _, ps in peers):
            return                       # T2: an OUT neighbour still sees two labels
        self.frozen = True
        self.frozen_ms = now
        self.phase = PH_OWN
        self._touch()

    def _cover_what_the_key_election_missed(self, nb: Sequence[BootNeighbor]) -> None:
        """A FROZEN NODE MAY NOT REST ON AN EDGE IT CAN SEE IS UNCOVERED.

        BB-CVC already owns this repair and its reasoning (`bbcvc`, Phase 3):
        an edge whose two ends are both OUT is uncovered and unowned, and once
        the far end has DEMONSTRABLY finished deciding, deferring to it for ever
        is how a run reports `solved` on an invalid answer. Only the trigger is
        restated here, because the annealer jumps from PH_ANNEAL to PH_OWN and
        so never occupies PH_FORCED, where the base class calls it.

        NOTHING IS RE-JUDGED: the base guard asks for a neighbour that is still
        OUT and whose ADVERTISED PHASE says it is past its own cover decision.
        For an annealing node that phase is exactly the freeze -- PH_ANNEAL is
        PH_COVER, which is BELOW PH_FORCED, so a neighbour that is still
        annealing cannot trigger the repair and is left to fix the edge itself.
        A frozen neighbour advertises PH_OWN and never flips again, so at that
        point the edge is provably nobody else's to cover.

        WHY THE FREEZE IS NOT SIMPLY REFUSED. `verdict` is the mode of
        termination and coupling it to validity turns a DETECTABLE false
        success into an undetectable truncation, which §105 tried and reverted.
        It would also not work here: the reason the two ends are stuck is that
        every move they have is UPHILL, so refusing to freeze buys no repair,
        only a run that never ends.

        MEASURED, full_v3, Anneal-Trickle/async at zero loss. `n100_m400_s10`
        seed 10: nodes 7 and 70 both froze OUT at period 92 with edge (7,70)
        between them, each SEEING the other out. Joining priced at +5001 and
        +3218, because the join resets every flexible share to y = 1/2 and
        charges the resulting transient overload (node 7: F = 1 forced plus
        16 x 1/2 = 9 against k = 6, so 3 x lam_k = 7110) against a single
        uncovered edge worth lam_c = 2370. At T <= T_min only descent is
        accepted, so neither repair was reachable. `n200_m800_s1` seed 1 is
        the same shape on edge (30,51). Both are the ONLY two false successes
        in the sweep, and both close here.

        THE COVER BIT LIVES IN TWO FIELDS. `role` is what the base class moves
        and `x` is what every anneal rule reads; `_reset_to_phase0` documents
        what happens when only one of them travels. So the shares are rebuilt
        and the advertised load refreshed exactly as `_loop_a` does on a join,
        and the repair stays MONOTONE: `role` leaves OUT once and Loop A is
        already frozen, so it cannot oscillate.
        """
        was = self.role
        super()._cover_what_the_key_election_missed(nb)
        if self.role is was or not self.role.in_cover:
            return
        self.x = 1
        peers = self._peers(nb)
        self.y = {n.nid: Y_ONE // 2 for n, ps in peers if ps.x}
        self._adv_ell_fp = f2fp(self._ell(peers))
        self._touch()

    # TRIED AND REVERTED: waking a frozen node.
    #
    # The cause of the disconnection was found (below), and the first attempted
    # repair was "a node whose basis for freezing has gone stale returns to
    # annealing". It SOLVED the label problem but produced a different bug:
    # nodes waking while cold kept descending greedily and, on some runs,
    # stripped the cover down to |C| = 2 and left edges uncovered. Trading one
    # defect for another is not a repair, so it was reverted. Only VISIBILITY
    # was kept in its place: Loop C keeps running after the freeze.

    # ------------------------------------------------------- observation
    def snapshot(self) -> NodeSnapshot:
        s = super().snapshot()
        s.phase = self.phase
        return s

    def local_energy_terms(self) -> Dict[str, float]:
        """For measurement and figures; never used for a DECISION."""
        peers = self._peers(self._nbrs_active())
        return {"x": float(self.x), "ell": self._ell(peers),
                "forced": float(self._forced(peers)), "T": self.temperature,
                "label": float(self.label), "flips": float(self.flips)}


# ==========================================================================
# run helpers (MEASUREMENT side; node code never sees these)
# ==========================================================================
def build_nodes(net, weights: Dict[int, float], k: int,
                params: Optional[AnnealParams] = None) -> Dict[int, AnnealNode]:
    """One core per node. The graph is NOT GIVEN: only weight, k and the port."""
    p = (params or AnnealParams()).resolved(weights.values())
    return {nid: AnnealNode(weights[nid], net.port(nid), p, k) for nid in net.nodes}


def total_energy(edges, weights: Dict[int, float], k: int, cover: Iterable[int],
                 lam_c: float = 12.0, lam_k: float = 12.0,
                 lam_b: float = 12.0) -> float:
    """GLOBAL energy, .tex §13.1. An independent reference: the node code's
    local delta-E is cross-checked against it (this assumes integral ownership
    rather than fractional y, and uses the best distribution for the load)."""
    from ccvc.bb import validate as V
    C = set(cover)
    e = sum(float(weights[v]) for v in C)
    uncovered = [(u, v) for u, v in edges if u not in C and v not in C]
    e += lam_c * len(uncovered)
    g = V.make_graph(list(edges), k, weights, sorted(weights))
    over = 0.0
    for v in C:
        forced = V.forced_load(g, C, v)
        over += max(0.0, forced - k)
    e += lam_k * over
    comps = V.cover_components(g, C)
    e += lam_b * max(0, len(comps) - 1)
    return e
