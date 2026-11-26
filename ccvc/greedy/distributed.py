"""Coordinator-free greedy cover expansion on the existing connected backbone.

GCCVC, GRCCVC and GWCCVC use their source score rules on residual OUT--OUT
edges. Only one-hop authenticated advertisements are available to a node.
RED priority is local; winners can proceed concurrently. This is deliberately
named a backbone adaptation, not an exact distributed execution of the
upstream's global serial greedy. Connectivity and capacity repair reuse the
existing BB-CVC implementation, with its actual ACK/retry traffic.

No node is passed the graph, a precomputed cover, or a neighbor list. The same
NodeCore is used by the synchronous scheduler, asynchronous scheduler and UDP
station process. There are no scheduler-specific decision branches.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ccvc.bb import wire
from ccvc.bb.api import MsgType, Role
from ccvc.bb.bbcvc import BbcvcNode, BbcvcParams, PH_COVER, PH_DONE, PH_FORCED, run_bbcvc

RULES = {"gccvc": 0, "grccvc": 1, "gwccvc": 2}


def candidate_key(rule: str, state: wire.GreedyState):
    """Source score order with a deterministic final ID tie break."""
    if rule == "gccvc":
        score = (-state.degree, state.weight, state.src)
    elif rule == "grccvc":
        score = (state.weight / state.denominator if state.denominator > 0 else math.inf,
                 state.weight, state.src)
    elif rule == "gwccvc":
        score = (state.weight, -state.degree, state.src)
    else:
        raise ValueError(f"Unknown greedy rule {rule!r}")
    return (state.color, *score)


@dataclass
class GreedyParams(BbcvcParams):
    algorithm: str = "gccvc"
    score_stale_periods: int = 3

    def __post_init__(self):
        super().__post_init__()
        if self.algorithm not in RULES or self.score_stale_periods < 1:
            raise ValueError("Require a known greedy rule and positive score freshness window")


class GreedyNode(BbcvcNode):
    def __init__(self, weight, platform, params=None, capacity_k=2):
        if not math.isfinite(float(weight)) or float(weight) <= 0:
            raise ValueError("Greedy weights must be finite and positive")
        if isinstance(capacity_k, bool) or not isinstance(capacity_k, int) or capacity_k < 1:
            raise ValueError("Greedy capacity must be a positive integer")
        super().__init__(weight, platform, params or GreedyParams(), capacity_k)

    def _init_algo_state(self):
        super()._init_algo_state()
        self._greedy_info = {}  # peer -> (authenticated local advertisement, arrival time)
        self._greedy_red = False
        self._greedy_seq = 0
        self._greedy_last = None
        self._greedy_sent_ms = None
        self.greedy_selections = 0

    def _local_state(self):
        residual = [n for n in self._nbrs_active() if n.role == Role.OUT]
        degree = len(residual) if self.role == Role.OUT else 0
        if self.phase >= PH_COVER and self.role == Role.OUT and degree <= 1:
            self._greedy_red = True  # Source RED marking is sticky within an epoch.
        if self.role.in_cover:
            color = 3
        elif self._greedy_red:
            color = 0
        else:
            # All OUT nodes are dominated by the selected backbone at this stage.
            color = 2 if any(n.role.in_cover for n in self._nbrs_active()) else 1
        denominator = sum(self._greedy_info[n.nid][0].weight for n in residual
                          if n.nid in self._greedy_info) if degree else 0.0
        return wire.GreedyState(self.nid, self._greedy_seq, float(self.w), denominator,
                                degree, color, self.epoch, RULES[self.p.algorithm], self.phase)

    def _maybe_hello(self, now):
        super()._maybe_hello(now)
        # Status is actual protocol traffic, separate from bootstrap HELLO.
        # It stops after the greedy/forced stages, avoiding an endless outbox.
        if self.phase > PH_FORCED:
            return
        state = self._local_state()
        signature = (state.weight, state.denominator, state.degree, state.color,
                     state.epoch, state.rule, state.phase)
        due = self._greedy_sent_ms is None or now >= self._greedy_sent_ms + self.p.t_hello_ms
        if signature != self._greedy_last or due:
            if signature != self._greedy_last:
                self._greedy_seq = (self._greedy_seq + 1) & 0xFFFFFFFF
            state.seq = self._greedy_seq
            self._bcast(wire.encode(state))
            self._greedy_last = signature
            self._greedy_sent_ms = now

    def _on_algo(self, now, src_mac, msg):
        if msg.mtype is not MsgType.GREEDY_STATE:
            return super()._on_algo(now, src_mac, msg)
        neighbor = self.nbrs.get(msg.src)
        if (neighbor is None or neighbor.mac != src_mac or not neighbor.is_edge
                or msg.epoch != self.epoch or msg.rule != RULES[self.p.algorithm]):
            return
        previous = self._greedy_info.get(msg.src)
        if previous:
            delta = (msg.seq - previous[0].seq) & 0xFFFFFFFF
            if delta >= 0x80000000:
                return  # An older reordered frame cannot replace a newer score.
            if delta == 0 and msg != previous[0]:
                return  # A sequence number identifies one immutable score.
        self._greedy_info[msg.src] = (msg, now)

    def _rule_cover(self, neighbors):
        """Iterate residual cover expansion instead of BB's one-shot edge rule."""
        if self.role.in_cover:
            self.phase = PH_FORCED
            self._touch()
            return
        residual = [neighbor for neighbor in neighbors if neighbor.role == Role.OUT]
        if not residual:
            self.phase = PH_FORCED
            self._touch()
            return
        now = self.plat.now_ms()
        rivals = []
        for neighbor in residual:
            known = self._greedy_info.get(neighbor.nid)
            if known is None:
                return  # Never invent a remote weight or residual degree.
            state, arrived = known
            if (state.epoch != self.epoch or state.phase < PH_COVER
                    or now - arrived > self.p.score_stale_periods * self.p.t_hello_ms
                    or state.color == 3 or state.degree == 0):
                return  # Wait for coherent, current local observations.
            rivals.append(state)
        mine = self._local_state()
        if all(candidate_key(self.p.algorithm, mine) < candidate_key(self.p.algorithm, rival)
               for rival in rivals):
            self.role = Role.COVER
            self.phase = PH_FORCED
            self.greedy_selections += 1
            self._log("greedy_selected", algorithm=self.p.algorithm,
                      residual_degree=mine.degree, weight=mine.weight,
                      denominator=mine.denominator, color=mine.color)
            self._touch()


class GccvcNode(GreedyNode):
    def __init__(self, weight, platform, params=None, capacity_k=2):
        super().__init__(weight, platform, replace(params or GreedyParams(), algorithm="gccvc"), capacity_k)


class GrccvcNode(GreedyNode):
    def __init__(self, weight, platform, params=None, capacity_k=2):
        super().__init__(weight, platform, replace(params or GreedyParams(), algorithm="grccvc"), capacity_k)


class GwccvcNode(GreedyNode):
    def __init__(self, weight, platform, params=None, capacity_k=2):
        super().__init__(weight, platform, replace(params or GreedyParams(), algorithm="gwccvc"), capacity_k)


def build_nodes(net, weights, k, params):
    node_class = {"gccvc": GccvcNode, "grccvc": GrccvcNode, "gwccvc": GwccvcNode}[params.algorithm]
    return {node: node_class(weights[node], net.port(node), params, k) for node in net.nodes}


def run_greedy(edges, weights, k, *, algorithm="gccvc", scheduler="sync", params=None, **kwargs):
    from ccvc.greedy.central import check_input
    check_input(edges, weights, k)  # Run-level guard; never handed to node code.
    if any(node == 0 or node > 65535 for node in weights):
        raise ValueError("Relabel vertices to 1..65535 before using the distributed protocol")
    p = replace(params or GreedyParams(), algorithm=algorithm)
    return run_bbcvc(edges, weights, k, scheduler=scheduler, params=p,
                     node_factory=build_nodes, **kwargs)


def _specs():
    from ccvc.bb import armnames
    from ccvc.bb.sweep import VariantSpec, with_overrides
    specs = []
    for algorithm in RULES:
        def run(request, rule=algorithm):
            return run_greedy(request.edges, request.weights, request.k,
                              algorithm=rule, scheduler=request.scheduler,
                              seed=request.seed, loss=request.loss, max_ms=request.max_ms,
                              params=with_overrides(
                                  GreedyParams(algorithm=rule,
                                               mis_nbrs_max=request.mis_nbrs_max),
                                  request))
        # The arm name says which score the rule maximises, because that is the
        # ONLY thing separating the three; `armnames` owns the spelling so the
        # sweep, the audit table and the legacy translation cannot drift apart.
        specs.append(VariantSpec(armnames.greedy_arm(algorithm, "Backbone"),
                                 "greedy-backbone",
                                 f"mis+{algorithm}-cover", "local", run))
    return specs


BB_VARIANTS = _specs()
