"""Regression tests for the link gate (note to Amendment 15, D2).

Backend: the event simulator (SimNet, fixed delay of one slot). Instances: the
worked example and the development file n100_m400_s1; no held-out instance,
no pre-registered seed (channel seed 1).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, bootstrap, matrix, sweep  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402
from ccvc.bb.figures import WORKED_EDGES, WORKED_K, WORKED_WEIGHTS  # noqa: E402

PROFILE = {"adaptive_stale": False, "stale_periods": 24, "stab_periods": 24}


def test_one_bound_for_the_freeze_gate_and_done():
    assert bootstrap.BootstrapParams().link_rounds_max == 4
    assert bbcvc.BbcvcParams().link_rounds_max == 4


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_a_failed_round_before_the_freeze_is_waited_for(scheduler):
    """The first three LINKs 2 -> 1 are lost, so node 2's first round fails.
    Before the link gate node 2 froze without node 1, verified it 12 periods
    later and restarted the epoch; now the freeze waits for the next round."""
    lost = []

    def drop(t, s, d, m):
        if int(m) == int(MsgType.LINK) and (s, d) == (2, 1) and len(lost) < 3:
            lost.append(t)
            return True
        return False

    r = bbcvc.run_bbcvc(WORKED_EDGES, dict(WORKED_WEIGHTS), WORKED_K,
                        scheduler=scheduler, max_ms=600_000, drop=drop)
    assert len(lost) == 3
    assert r.verdict == "solved" and r.restarts == 0
    assert r.cover == [2, 3, 4, 5, 6, 7, 8, 9] and len(r.discovered_edges) == 15


def test_lossless_runs_never_fail_a_handshake():
    for scheduler in ("sync", "async"):
        r = bbcvc.run_bbcvc(WORKED_EDGES, dict(WORKED_WEIGHTS), WORKED_K,
                            scheduler=scheduler, max_ms=600_000)
        assert not any(x["event"] == "link_gave_up" for x in r.net.log_records)
        assert r.restarts == 0


PATH = "/home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset/n100_m400_s1.txt"


@pytest.mark.skipif(not os.path.exists(PATH), reason="development dataset not present")
def test_the_restart_loop_at_thirty_percent_ends():
    """n100_m400_s1, NexusWarp, sync, 30 % independent loss, the Amendment 15
    profile: before the link gate about 1000 restarts and truncated at 12 M ms
    (226 bumps in the first 300 s); now solved without a restart."""
    w, e, _ = sweep.prepare(*matrix.load_instance(PATH))
    p = bbcvc.BbcvcParams(mis_nbrs_max=64, **PROFILE)
    r = bbcvc.run_bbcvc(e, w, 6, scheduler="sync", loss=0.3, seed=1,
                        max_ms=12_000_000, params=p, watch_ms=0)
    assert r.verdict == "solved" and r.restarts == 0
