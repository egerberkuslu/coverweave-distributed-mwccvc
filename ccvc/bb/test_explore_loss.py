#!/usr/bin/env python3
"""Tests of the drop-pattern explorer itself (task X1), not of the protocol."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import explore_loss as X  # noqa: E402

PATH3 = dict(
    graph="p3",
    n=3,
    edges=[[1, 2], [2, 3]],
    weights={"1": 1.0, "2": 2.0, "3": 1.0},
    wname="t",
    k=2,
    arm="mis",
    sched="sync",
)

#: V4 report, first instance: HELLO 5->3 dropped in slots 24..173 gave a silent
#: run, verdict solved, with (3,5) owned by both ends, on the code before F15.
V4_CFG = dict(
    graph="v4",
    n=13,
    wname="v4",
    k=3,
    arm="mis",
    sched="sync",
    edges=[
        [1, 3],
        [1, 5],
        [1, 7],
        [1, 8],
        [2, 4],
        [2, 7],
        [2, 8],
        [2, 11],
        [3, 5],
        [3, 9],
        [4, 6],
        [4, 7],
        [4, 12],
        [4, 13],
        [5, 8],
        [5, 11],
        [6, 8],
        [6, 11],
        [6, 13],
        [7, 8],
        [7, 9],
        [7, 10],
        [7, 11],
        [7, 13],
        [8, 11],
        [10, 12],
    ],
    weights={
        "1": 9,
        "2": 1,
        "3": 8,
        "4": 6,
        "5": 4,
        "6": 2,
        "7": 6,
        "8": 3,
        "9": 8,
        "10": 7,
        "11": 5,
        "12": 5,
        "13": 5,
    },
)
V4_PATTERN = X.pattern_dict(windows=[(5, 3, X.HELLO, 24 * 200, 174 * 200)])
#: A copy of the pre-F15 tree (b7/f13b) the V4 report ran on.
OLD_ROOT = os.environ.get(
    "X1_OLD_ROOT",
    "/tmp/claude-1000/-home-ege-Desktop-MDS-SKYFABRIC/"
    "90753496-ccce-4735-a465-70e4075af194/scratchpad/x1/old",
)


def test_frame_beyond_the_run_touches_nothing():
    base, bdr, _ = X.run_one(PATH3, record=True)
    res, dr, exc = X.run_one(PATH3, X.pattern_dict(frames=[(1, 2, X.HELLO, 10**6)]))
    assert exc is None and dr.dropped == []
    assert (res.tx, res.slots, res.cover) == (base.tx, base.slots, base.cover)


def test_dropped_keys_replay_the_same_run():
    """Dedup and minimisation rest on this: the explicit keys of a run's drops
    reproduce the run exactly, and a burst longer than the link's remaining
    frames drops fewer than its length (so longer ones are pruned)."""
    res, dr, _ = X.run_one(PATH3, X.pattern_dict(bursts=[(2, 1, 3, 10**6)]))
    assert 0 < len(dr.dropped) < 10**6
    res2, dr2, _ = X.run_one(PATH3, X.pattern_dict(frames=dr.keys()))
    assert dr2.dropped == dr.dropped
    assert (res2.tx, res2.slots, res2.verdict) == (res.tx, res.slots, res.verdict)


def test_explore_accounting_and_dedup(monkeypatch):
    monkeypatch.setitem(
        X.TIERS, "t", dict(bursts=(2, 10**6), burst_starts=2, pair_cap=5, single_cap=10 ** 6, n6=0)
    )
    s = X.explore_config(PATH3, "t")
    c = s["counts"]
    distinct = sum(v for k, v in c.items() if k.startswith("distinct_"))
    assert s["runs"] == s["generated"] + 1
    assert s["generated"] == distinct + s["deduped_zero"] + s["deduped_same"]
    assert c["distinct_single"] == s["baseline"]["frames"]
    assert s["baseline"]["viol"] == []


def test_old_code_double_owner_reproduced(tmp_path):
    """Known violation of the old code, from the recorded V4 pattern."""
    if not os.path.isdir(os.path.join(OLD_ROOT, "ccvc", "bb")):
        pytest.skip(f"no copy of the old tree at {OLD_ROOT}")
    f = tmp_path / "v4.json"
    f.write_text(json.dumps(dict(cfg=V4_CFG, pattern=V4_PATTERN)))
    env = dict(os.environ, PYTHONPATH=OLD_ROOT)
    out = subprocess.run(
        [sys.executable, X.__file__, "replay", str(f)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    rep = json.loads(out.stdout.strip().splitlines()[-1])
    assert rep["verdict"] == "solved" and rep["drops"] == 15
    assert any(p == "double_owned" and "(3, 5)" in d for p, d in rep["violations"])
