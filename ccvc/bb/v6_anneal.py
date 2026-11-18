#!/usr/bin/env python3
"""Anneal-Local's sweep registration: `BB_VARIANTS`, the runner adapter, the anytime trace.

The algorithm lives in `ccvc/bb/anneal.py`; this file contains ONLY the binding
to the `ccvc/bb/sweep.py` contract. It is a separate file because
`sweep.VARIANT_MODULES` probes for the name `ccvc.bb.v6_anneal`; that list
belongs to bb-figures, and rather than asking them to change it we meet the name.

FAMILY AND AXES. `family="anneal"`, `phase1="anneal"`. This means Anneal cannot form
a MATCHED PAIR with the BB arms, and that is correct: Anneal does not merely replace
Phase 1, it changes the CHARACTER of the cover decision (iterative and
reversible instead of constructive and monotone). Because it differs on two axes
at once it appears in cross-variant comparison, not in matched comparison.

`phase5="local"`: after freezing, Anneal runs BB-CVC's 5a unchanged. The tree version
(5b) is also possible and is enabled with `enable_tree`; that arm forms a MATCHED
pair inside Anneal on the phase5 axis, because it is the only difference between them.

INFEASIBILITY: Anneal HAS NO WITNESS OF ITS OWN
  In BB-CVC the infeasibility witness is built on Phase 3's forced-load path.
  Anneal HAS NO PHASE 3, so no node ever produces a local witness and `infeasible`
  can only come from the run-level COUNTING BOUND (m > n*k). That bound is
  deliberately narrow: it is arithmetic, it does not care which arm produced the
  cover, and it names itself as `infeasible_reason == "counting_bound"`.
  Instances that are infeasible for subtler reasons come back as `unresolved` in
  Anneal, because we hold no evidence that would separate "I failed" from "there is
  no solution". This is honesty rather than a gap; the other infeasibility class
  is provably NOT locally detectable at any ball radius (bb-algo).

VERDICT MEANS THE RUN FINISHED, NOT THAT THE ANSWER IS GOOD
  `verdict` is produced on the shared path and reports only how the run
  terminated. A frozen but garbage cover reads "solved"; the empty-cover bug
  looked exactly like that. The correct condition for counting a row as an arm
  result is `verdict == "solved"` AND a clean validator, both together.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import anneal, bbcvc  # noqa: E402
from ccvc.bb import validate as V  # noqa: E402
from ccvc.bb.anneal import AnnealNode, AnnealParams  # noqa: E402
from ccvc.bb.bbcvc import BbcvcRun, run_bbcvc  # noqa: E402
from ccvc.bb.sweep import AnytimeSample, AnytimeTrace, RunRequest, VariantSpec  # noqa: E402

Edge = Tuple[int, int]

#: Default sampling interval for the anytime trace (ms). Every sample runs a
#: global validity check (including flow-based capacity), so it is not free; the
#: value is chosen as a multiple of a HELLO period.
SAMPLE_EVERY_MS = 1000

# --------------------------------------------------------------------------
# ESP32 POWER MODEL -- A DERIVED ESTIMATE, NOT A MEASUREMENT
#
# These are ESP32 radio currents at 1 Mbps, mirroring api.Counters.energy_mah.
# The target platform is mininet-wifi, where a station is a Linux process with
# no radio and therefore no current draw. Nothing here measures energy on the
# platform we actually run on: it applies an ESP32 power model to emulated
# frame timings.
#
# It is kept because every arm uses the SAME model, so the comparison BETWEEN
# arms remains meaningful. It is a relative measure under a stated model, never
# an absolute one, and every place it surfaces -- field name, figure axis,
# caption, CSV column -- has to say so. The warning lives in the identifier
# rather than in this comment because a caveat in a docstring does not travel
# into a figure.
# --------------------------------------------------------------------------
ESP32_LISTEN_MA = 100.0      # radio receiving
ESP32_TRANSMIT_MA = 240.0    # radio transmitting
ESP32_FRAME_MS = 0.7         # 24 B at 1 Mbps
_MS_PER_HOUR = 3_600_000.0


@dataclass
class AnnealRun(BbcvcRun):
    """`BbcvcRun` plus the fields specific to Anneal.

    SUBCLASSING MATTERS. Because `run_bbcvc(result_cls=AnnealRun)` builds the
    result, the fifteen contract fields and the run-level fields such as
    `verdict`, `truncated` and `infeasible_reason` are produced by the SAME code
    as BB-CVC's. Keeping my own copy would let the result derivation drift over
    time, and the claim "they go through the same pipeline" would quietly become
    false.

    The Anneal-specific fields are filled in AFTER the run, because `run_bbcvc` does
    bilmez ve bilmemelidir.
    """

    trace: Optional[AnytimeTrace] = None
    # measurement extras (outside the contract, in case a figure wants them)
    flips: int = 0
    periods_with_violation: int = 0
    total_periods: int = 0
    #: OBSERVER BOUND. The best valid solution seen during the run.
    #:
    #: The name carries `observer_` and that is not a stylistic preference: this
    #: value IS NOT A RESULT THE DISTRIBUTED SYSTEM COULD PRODUCE. Validity means
    #: coverage, connectivity and capacity; none of the three is knowable from
    #: 1-hop state, so no node can say "the configuration I am in right now is
    #: the best one I have been in". The value here is computed by a sampler
    #: using global knowledge.
    #:
    #: For the system to REALLY report it, a periodic convergecast is required --
    #: that is Phase 5b's TREE/STABLE machinery and it increases `tx`. That cost
    #: is NOT COUNTED. So the value must never appear BARE in any table or
    #: figure; everywhere it appears it must be labelled "observer bound,
    #: requires an uncounted convergecast" (team lead's decision).
    #:
    #: The entire justification for this project was that the old
    #: MWCCVC-MININET code did NOT COUNT as distributed, because it
    #: reconstructed its answer from the global graph. Publishing a
    #: globally-computed "best seen" as Anneal's result would repeat that same error
    #: with our own name on it. The number that goes in the report is
    #: `total_weight`.
    observer_best_weight: Optional[float] = None
    observer_best_cover: Tuple[int, ...] = ()

    #: Embeds the label in code, so that whoever takes the number is forced to
    #: take the label with it.
    OBSERVER_LABEL: str = (
        "observer bound; the distributed system cannot report this without an "
        "uncounted convergecast"
    )

    @property
    def transient_violation_rate(self) -> float:
        return self.periods_with_violation / max(self.total_periods, 1)


class _Sampler:
    """Collects the anytime trace. This is the MEASUREMENT SIDE, not node code.

    HONESTY NOTE, and it belongs in the figure caption: "the best VALID solution
    so far" is a GLOBAL quantity. Validity means coverage, connectivity and
    capacity, and none of them is knowable from 1-hop state. So this curve is not
    something the distributed system could report ABOUT ITSELF; it is what an
    outside observer sees. Anneal genuinely does "report the last valid solution it
    holds when stopped", but only an observer can know that the solution is valid.

    Capacity is checked here by FLOW, not by ownership: ownership is produced in
    Phase 4 and `owned` is empty while annealing is still running. The TU claim
    is exactly "if a fractional/flow assignment is feasible then an integral one
    exists", so the flow question is the right one to ask.
    """

    def __init__(self, net, nodes, graph, weights, every_ms: int = SAMPLE_EVERY_MS):
        self.net = net
        self.nodes = nodes
        self.graph = graph
        self.weights = weights
        self.every_ms = every_ms
        self.samples: List[AnytimeSample] = []
        self._next_ms = 0
        self._best_w: Optional[float] = None
        self._best_n: Optional[int] = None
        self.best_cover: Tuple[int, ...] = ()

    def energy_mah_esp32_model(self, now: int) -> float:
        """DERIVED ESP32 ESTIMATE, not measured energy. See the module header.

        Same formula as api.Counters.energy_mah, but with a LIVE listening
        time. `Counters.radio_on_ms` is only written when a node reports done
        or when `finalize` runs, so mid-run it is zero: calling `c.energy_mah()`
        directly would give a curve that sits near flat and then jumps at the
        wall. A node that has not gone quiet has been listening since the start,
        so the live value is `now`.

        Monotone non-decreasing by construction: a done time is fixed once set
        and `tx` only grows, which is what the anytime contract requires.
        """
        tot = 0.0
        for nid, c in self.net.counters.items():
            done = self.net.done_ms(nid)
            on = now if done is None else done
            tot += (on / _MS_PER_HOUR * ESP32_LISTEN_MA
                    + c.tx * ESP32_FRAME_MS / _MS_PER_HOUR * ESP32_TRANSMIT_MA)
        return round(tot, 9)

    def maybe_sample(self, now: int) -> None:
        if now < self._next_ms:
            return
        self._next_ms = now + self.every_ms
        self.sample(now)

    def sample(self, now: int) -> None:
        cover = sorted(nid for nid, n in self.nodes.items() if n.role.in_cover)
        current: Optional[float] = None
        if cover:
            # Validity is asked of the REAL validator, not of some weaker test.
            # Capacity is checked by FLOW: while annealing is still running the
            # ownership has not been produced yet (`owned` is empty), so an
            # ownership-based check would call every intermediate state invalid.
            if V.validate(self.graph, cover).valid:
                current = round(sum(float(self.weights[v]) for v in cover), 6)
                if self._best_w is None or current < self._best_w:
                    self._best_w, self._best_n = current, len(cover)
                    self.best_cover = tuple(cover)
        tx = sum(c.tx for c in self.net.counters.values())
        self.samples.append(AnytimeSample(
            t_ms=int(now), energy_mah=self.energy_mah_esp32_model(now), tx=int(tx),
            observer_best_weight=self._best_w, cover_size=self._best_n,
            current_weight=current))

    def trace(self, variant: str) -> AnytimeTrace:
        t = AnytimeTrace(variant=variant, samples=self.samples)
        t.check()                                   # a broken trace RAISES rather than being drawn
        return t


class _TracedAnnealNode(AnnealNode):
    """Exists only to trigger the sampler. The decision logic is UNCHANGED."""

    def on_timer(self, name: str = "tick") -> None:
        super().on_timer(name)
        # Only a one-way measurement event crosses the platform boundary.
        # No node stores a sampler containing the global graph or node table.
        self.plat.log("observer_tick")


def run_anneal(edges: Sequence[Edge], weights: Dict[int, float], k: int, *,
               scheduler: str = "sync", params: Optional[AnnealParams] = None,
               max_ms: int = 200_000, loss: float = 0.0, seed: int = 0,
               delay=None, tau_ms: int = 200, tick_ms: int = 200,
               rssi_range=None, trace: bool = True,
               sample_every_ms: int = SAMPLE_EVERY_MS,
               node_cls: type = None) -> AnnealRun:
    """Run Anneal-Local under a scheduler. Node code CANNOT SEE the mode.

    Network construction, scheduler selection, the bootstrap gate, the
    cover/ownership extraction and the counting bound are all BB-CVC's OWN code;
    only the node factory and the result type are supplied here. This function
    used to hold a copy of `run_bbcvc`, and that copy was the kind that breaks a
    comparison silently.
    """
    p = (params or AnnealParams(rng_seed=seed)).resolved(weights.values())
    cls = node_cls or _TracedAnnealNode      # lets tests inject a faulty node
    box: Dict[str, object] = {}

    def factory(net, w, kk, pp):
        """A NET-LEVEL factory: the sampler is attached before the scheduler starts."""
        nodes = {nid: cls(w[nid], net.port(nid), pp, kk) for nid in net.nodes}
        if trace:
            graph = V.make_graph(list(edges), kk, w, sorted(w))
            sampler = _Sampler(net, nodes, graph, w, sample_every_ms)
            net.add_log_observer(lambda record: sampler.maybe_sample(record["t_ms"])
                                 if record["event"] == "observer_tick" else None)
            box["sampler"] = sampler
            box["net"] = net
        return nodes

    res: AnnealRun = run_bbcvc(
        list(edges), dict(weights), k, scheduler=scheduler, params=p,
        max_ms=max_ms, loss=loss, seed=seed, delay=delay, tau_ms=tau_ms,
        tick_ms=tick_ms, rssi_range=rssi_range,
        node_factory=factory, result_cls=AnnealRun)

    nodes = res.nodes
    res.flips = sum(n.flips for n in nodes.values())
    res.periods_with_violation = sum(n.periods_with_violation
                                     for n in nodes.values())
    res.total_periods = sum(n.periods for n in nodes.values())
    if trace:
        sampler = box["sampler"]
        sampler.sample(box["net"].now_ms())      # son durumu mutlaka yakala
        res.trace = sampler.trace("Anneal-Local")
        res.observer_best_weight = sampler._best_w
        res.observer_best_cover = sampler.best_cover
    return res


def _spec_run(tree: bool, trickle: bool):
    def run(req: RunRequest) -> AnnealRun:
        p = AnnealParams(rng_seed=req.seed, enable_tree=tree, trickle=trickle,
                         mis_nbrs_max=req.mis_nbrs_max)
        return run_anneal(list(req.edges), dict(req.weights), req.k,
                          scheduler=req.scheduler, max_ms=req.max_ms,
                          loss=req.loss, seed=req.seed, params=p)
    return run


BB_VARIANTS: Tuple[VariantSpec, ...] = (
    VariantSpec("Anneal-Local", "anneal", "anneal", "local",
                _spec_run(tree=False, trickle=False), anytime=True),
    VariantSpec("Anneal-TreeAgg", "anneal", "anneal", "tree",
                _spec_run(tree=True, trickle=False), anytime=True),
    # Trickle is meaningful ONLY asynchronously: the synchronous slot is fixed
    # for everyone (.tex §13.5). `schedulers` enforces that structurally rather
    # than in a comment.
    VariantSpec("Anneal-Trickle", "anneal", "anneal", "local",
                _spec_run(tree=False, trickle=True), schedulers=("async",),
                anytime=True),
)
