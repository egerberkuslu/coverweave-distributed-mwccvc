#!/usr/bin/env python3
"""Loss models of the simulator: Gilbert-Elliott ('ge:<r>:<b>') and empirical ('emp').

Backend: event simulator (simnet). The float path is pinned to a trace recorded
before these models were added.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import bbcvc, figures, sched, simnet  # noqa: E402
from ccvc.bb.api import MsgType  # noqa: E402
from ccvc.bb.test_sched import DEG_SUM, make_net, trivial  # noqa: E402


def drop_trace(spec: str, n: int, seed: int = 0) -> list:
    net = simnet.SimNet([1, 2], [(1, 2)], loss=spec, seed=seed)
    return [net._drops(1, 2, 0) for _ in range(n)]


def bursts(trace: list) -> list:
    runs, cur = [], 0
    for lost in trace:
        if lost:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    return runs


# --------------------------------------------------------------------------
# Gilbert-Elliott
# --------------------------------------------------------------------------
def test_ge_transitions_match_the_formulas():
    p, q = simnet.ge_transitions(0.10, 4)
    assert q == pytest.approx(1 / 4)
    assert p == pytest.approx(0.10 / (4 * 0.90))
    assert p / (p + q) == pytest.approx(0.10)


@pytest.mark.parametrize("r", [0.05, 0.10, 0.20])
def test_ge_stationary_rate_and_mean_burst_over_a_long_trace(r):
    trace = drop_trace(f"ge:{r:.2f}:4", 200_000, seed=3)
    runs = bursts(trace)
    assert sum(trace) / len(trace) == pytest.approx(r, abs=0.01)
    assert sum(runs) / len(runs) == pytest.approx(4, abs=0.4)


def test_ge_chains_are_per_directed_link():
    net = simnet.SimNet([1, 2], [(1, 2)], loss="ge:0.10:4", seed=0)
    net._drops(1, 2, 0)
    net._drops(2, 1, 0)
    assert set(net._ge_bad) == {(1, 2), (2, 1)}


def test_ge_is_deterministic_per_seed():
    assert drop_trace("ge:0.10:4", 5000, seed=1) == drop_trace(
        "ge:0.10:4", 5000, seed=1
    )
    assert drop_trace("ge:0.10:4", 5000, seed=1) != drop_trace(
        "ge:0.10:4", 5000, seed=2
    )


@pytest.mark.parametrize(
    "spec", ["ge:1.0:4", "ge:0.1:0.5", "ge:0.9:1", "ge:0.1", "bursty"]
)
def test_bad_loss_labels_are_rejected(spec):
    with pytest.raises(ValueError):
        simnet.SimNet([1, 2], [(1, 2)], loss=spec)


def test_ge_and_link_loss_are_exclusive():
    with pytest.raises(ValueError):
        simnet.SimNet([1, 2], [(1, 2)], loss="ge:0.1:4", link_loss={(1, 2): 0.5})


# --------------------------------------------------------------------------
# empirical per-link loss
# --------------------------------------------------------------------------
@pytest.fixture
def emp_pool(tmp_path, monkeypatch):
    path = tmp_path / "delivery.json"
    path.write_text(json.dumps({"delivery": [0.9, 0.5, 1.0]}))
    monkeypatch.setattr(simnet, "EMP_DELIVERY_PATH", str(path))
    return path


def test_emp_draws_one_measured_loss_per_link(emp_pool):
    net = make_net(loss="emp", seed=4)
    assert set(net.link_loss) == set(net.edges)
    assert {round(v, 9) for v in net.link_loss.values()} <= {0.1, 0.5, 0.0}
    assert net.link_loss == make_net(loss="emp", seed=4).link_loss
    assert net.link_loss != make_net(loss="emp", seed=5).link_loss


def test_emp_keeps_explicit_link_loss(emp_pool):
    assert make_net(loss="emp", link_loss={(2, 1): 0.25}).link_loss[(1, 2)] == 0.25


def test_emp_without_data_file_says_how_to_derive_it(tmp_path, monkeypatch):
    monkeypatch.setattr(simnet, "EMP_DELIVERY_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError, match="derive_hello_delivery"):
        make_net(loss="emp")


def test_run_bbcvc_passes_label_and_link_loss_through(emp_pool):
    edges, weights, k = (
        list(figures.WORKED_EDGES),
        dict(figures.WORKED_WEIGHTS),
        figures.WORKED_K,
    )
    r = bbcvc.run_bbcvc(edges, weights, k, loss="emp", seed=2, max_ms=20_000)
    assert set(r.net.link_loss) == set(r.net.edges)
    r = bbcvc.run_bbcvc(edges, weights, k, link_loss={(1, 2): 1.0}, max_ms=20_000)
    assert r.net.link_loss == {(1, 2): 1.0}
    r = bbcvc.run_bbcvc(edges, weights, k, loss="ge:0.10:4", max_ms=20_000)
    assert r.net._ge is not None and r.net.dropped > 0


# --------------------------------------------------------------------------
# accounting and the unchanged float path
# --------------------------------------------------------------------------
@pytest.mark.parametrize("spec", ["ge:0.20:4", "emp"])
def test_delivered_plus_dropped_is_the_degree_sum(spec, emp_pool):
    net = make_net(loss=spec)
    tot = sched.SyncScheduler(net, trivial(net), tau_ms=200).run(4000).totals()
    assert tot.tx == 200
    assert 0 < tot.rx < 20 * DEG_SUM
    assert tot.rx + net.dropped == 20 * DEG_SUM


def test_float_path_is_bit_identical_to_the_pre_change_trace():
    """sha256 recorded on the simulator before the loss models were added."""
    net = simnet.SimNet(
        range(1, 7),
        [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (1, 6), (2, 5)],
        loss=0.3,
        seed=7,
    )
    trace = [
        net._drops(s, d, 0) for _ in range(500) for s, d in [(1, 2), (2, 1), (5, 6)]
    ]
    assert hashlib.sha256(bytes(trace)).hexdigest() == (
        "99e72ce4950e54054dae4ac23f4f7b8b3e5755c61dda9f7d9fccabdd9b2f76cc"
    )


# --------------------------------------------------------------------------
# derivation of the 'emp' data file from station logs
# --------------------------------------------------------------------------
def test_derive_hello_delivery_from_station_logs(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "derive_hello_delivery",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data",
            "derive_hello_delivery.py",
        ),
    )
    derive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(derive)

    a, b = "02:00:00:00:00:01", "02:00:00:00:00:02"
    hello, link = int(MsgType.HELLO), int(MsgType.LINK)

    def write(name, mac, recs):
        with open(tmp_path / name, "w") as fh:
            for t, rec in enumerate(recs):
                fh.write(json.dumps({"t_ms": t, "mac": mac, **rec}) + "\n")

    tx = {"event": "tx", "kind": "bcast", "delivered": True}
    write(
        "1.jsonl",
        a,
        [{**tx, "mtype": hello}] * 4
        + [{**tx, "mtype": link}] * 2
        + [{"event": "rx", "src": b, "mtype": hello}] * 2,
    )
    write(
        "2.jsonl",
        b,
        [{**tx, "mtype": hello}] * 2
        + [{"event": "rx", "src": a, "mtype": hello}] * 3
        + [{"event": "rx", "src": a, "mtype": link}],
    )
    assert sorted(derive.pair_delivery(str(tmp_path))) == [0.75, 1.0]

    out = tmp_path / "pool.json"
    assert derive.main([str(tmp_path), "--out", str(out)]) == 0
    assert simnet.empirical_delivery(str(out)) == (0.75, 1.0)
