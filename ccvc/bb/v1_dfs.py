"""DFS-Spanning-Backbone: the provable 2-approximation baseline, fully distributed.

WHAT THIS ARM IS FOR. Savage's 1982 result says the internal nodes of any DFS
tree form a vertex cover within a factor of two of optimal. DFS-Spanning-Backbone exists to measure
what that guarantee COSTS when nobody may look at the graph: the tree has to be
built by passing a token over the medium, and the price of doing so is the
measurement.

WHY THERE IS NO SEEDED ROOT. Handing the arm a root would make it partly
full-information and would delete exactly the cost we are trying to measure.
Instead every local minimum starts its own walk, the token carries its
initiator, and a walk with a smaller initiator absorbs a larger one on contact.
Preempted partial walks are not waste; they ARE the measured quantity, which is
why `dfs_preempted` is reported separately rather than folded into the total.

THREE DISTRIBUTED PIECES, all in `variants.V1DfsNode`:

  1a  token walk            TOKEN offers, TOKEN bounced back on refusal,
                            TOKEN_DONE returned when a subtree finishes. The two
                            different reply types are what lets a parent count
                            children; with one reply type every tree degree
                            stays zero and the backbone comes out empty.
  1b  termination detection DFS_DONE flooded from the initiator. Only the
                            initiator can know the walk finished, because only
                            its own stack empties. `_barrier` cannot help: it
                            synchronises on phase, and whether the phase may
                            advance is precisely what must be decided.
  1c  backbone MIS          BB_MIS over the frozen tree. Without it every
                            internal node would be CONNECTOR, `mis_nbrs` would
                            be empty everywhere, and the 3-hop gap rule would
                            silently never fire.

Phase 2 onwards is the base class unchanged, reached through the
`_backbone_step` seam, so DFS-Spanning-Backbone shares Phases 2-5 with every other BB arm rather
than carrying a copy.

MEASURED, NOT ASSUMED. On the Dagdeviren benchmark the backbone this protocol
produces equals the reference DFS internal-node set exactly, and the runs
validate. Preemption fires on graphs that have more than one local minimum; on
the benchmark cells checked so far node 1 is the only local minimum, so a zero
preemption count there is the correct answer rather than a silent failure.
"""
from __future__ import annotations

from typing import Any

from ccvc.bb.bbcvc import BbcvcParams, run_bbcvc
from ccvc.bb.variants import V1DfsNode


def build_v1_nodes(net, weights, k: int, params=None):
    """Node factory: one `V1DfsNode` per station, no seed data of any kind.

    Unlike GHS-MST-Backbone's central MST seeding, DFS-Spanning-Backbone receives NOTHING but its own weight and
    its platform handle. Everything else it learns from frames.
    """
    p = params or BbcvcParams()
    return {nid: V1DfsNode(weights[nid], net.port(nid), p, k)
            for nid in sorted(weights)}


def run_v1(edges, weights, k: int, *, scheduler: str = "sync",
           params=None, max_ms: int = 600_000, seed: int = 0,
           loss: float = 0.0, **kw) -> Any:
    """Run DFS-Spanning-Backbone. The SAME node class serves both schedulers.

    Extra keyword options are forwarded to `run_bbcvc` for the same reason as
    in `v4_mst.run_v4`: the wireless collector reruns the case in the simulator
    with platform-shaped options, and dropping them fails after the run.
    """
    return run_bbcvc(edges, weights, k, scheduler=scheduler, params=params,
                     max_ms=max_ms, seed=seed, loss=loss,
                     node_factory=build_v1_nodes, **kw)


def _spec_run(req) -> Any:
    from ccvc.bb.sweep import with_overrides

    p = BbcvcParams()
    p.mis_nbrs_max = req.mis_nbrs_max
    return run_v1(list(req.edges), dict(req.weights), req.k,
                  scheduler=req.scheduler, params=with_overrides(p, req),
                  max_ms=req.max_ms, seed=req.seed, loss=req.loss)


def _build_specs():
    from ccvc.bb.sweep import VariantSpec

    # `family="dfs"` and `phase1="dfs"`: DFS-Spanning-Backbone replaces Phase 1 and nothing else,
    # so it pairs with MIS-Connector-Backbone on the phase1 axis, which is the comparison
    # the arm exists for. It is NOT in the "bb" family, because a paired
    # comparison must differ in exactly one axis and DFS-Spanning-Backbone's backbone construction
    # is a different algorithm rather than a different parameter.
    return (
        VariantSpec("DFS-Spanning-Backbone", "dfs", "dfs", "local", _spec_run),
    )


BB_VARIANTS = _build_specs()
