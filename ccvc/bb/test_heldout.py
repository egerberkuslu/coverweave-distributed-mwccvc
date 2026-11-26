#!/usr/bin/env python3
"""Tests of the held-out generator (ccvc/bb/heldout.py).

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_heldout.py -q

Every call uses seeds below 100. The pre-registered seeds stay sealed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc import bridge  # noqa: E402
from ccvc.bb import bbcvc, heldout, matrix  # noqa: E402
from ccvc.bb import validate as bb_validate  # noqa: E402
from ccvc.bb.mnwifi import run as mnrun  # noqa: E402
from ccvc.bb.mnwifi import topology as topo  # noqa: E402


@pytest.mark.parametrize(
    "set_name,seeds",
    [
        ("H1", [1]),
        ("H1-large", [1]),
        ("H2a", [1]),
        ("H2b", [1]),
        ("W", [1]),
        ("M9", [1, 2, 3]),
    ],
)
def test_set_round_trips_through_project_loader(tmp_path, set_name, seeds):
    m = heldout.generate(set_name, tmp_path, seeds=seeds)
    assert m["preregistered_seeds"] is False and m["files"]
    for e in m["files"]:
        path = tmp_path / e["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == e["sha256"]
        weights, edges = matrix.load_instance(
            str(path)
        )  # strict loader, rejects disconnected
        assert (len(weights), len(edges)) == (e["n"], e["m"])
        assert heldout._connected(len(weights), edges)
        assert heldout.instance_text(weights, edges) == path.read_text()
        assert all(heldout.WEIGHT_LO <= w < heldout.WEIGHT_HI for w in weights.values())
        if set_name.startswith("H1"):
            assert e["m"] == e["n"] * e["ratio"]
            assert all((v, v + 1) in set(edges) for v in range(e["n"] - 1))
        if set_name == "H2b":
            assert e["m"] == e["attach"] * (e["n"] - e["attach"])
        if set_name == "H2a":
            assert e["m"] == e["n"] * e["deg"] // 2 and e["deg"] in (6, 8)
        if set_name == "M9":  # infeasible by flow, both run-level witnesses silent
            k, n = e["k"], e["n"]
            g = bb_validate.make_graph(edges, k, nodes=list(range(n)))
            assert not bridge.capacity_feasible(g, set(range(n)))[0]
            assert not bbcvc.counting_bound_infeasible(n, e["m"], k)
            deg = [sum(v in uv for uv in edges) for v in range(n)]
            assert not bbcvc.degree_deficiency_infeasible(deg, e["m"], k)
    if set_name == "M9":
        assert sorted(e["n"] for e in m["files"]) == [20, 30, 50]


def test_m9_fails_loudly_when_the_flow_check_disagrees(monkeypatch):
    monkeypatch.setattr(heldout.bridge, "capacity_feasible", lambda g, c: (True, {}))
    with pytest.raises(RuntimeError, match="not a hidden infeasible instance"):
        heldout.generate_one("M9", 20, 6, 4)


def test_w_graph_json_matches_text_and_positions(tmp_path):
    m = heldout.generate("W", tmp_path, seeds=[2])
    for e in m["files"]:
        graph = tmp_path / e["graph_json"]
        assert hashlib.sha256(graph.read_bytes()).hexdigest() == e["graph_json_sha256"]
        edges, weights = mnrun.load_graph(str(graph))
        w_txt, e_txt = matrix.load_instance(str(tmp_path / e["file"]))
        assert edges == sorted((u + 1, v + 1) for u, v in e_txt)
        assert weights == {v + 1: w for v, w in w_txt.items()}
        assert len(edges) == e["n"] * e["deg"] // 2
        doc = json.loads(graph.read_text())
        pos = {int(i): tuple(p) for i, p in doc["positions"].items()}
        assert sorted(topo.realised_edges(pos, doc["radio_range_m"])) == edges


@pytest.mark.parametrize("n,deg", [(25, 6), (25, 8), (50, 8)])
def test_h2a_exact_degree_connected_and_loads(tmp_path, n, deg):
    weights, edges, pos = heldout.generate_one("H2a", n, deg, 3)
    assert pos is None and len(edges) == n * deg // 2 and heldout._connected(n, edges)
    path = tmp_path / f"n{n}_m{len(edges)}_s3.txt"
    path.write_text(heldout.instance_text(weights, edges))
    assert matrix.load_instance(str(path)) == (weights, edges)


def test_infeasible_udg_cell_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setattr(heldout, "UDG_TRIES", 5)
    with pytest.raises(RuntimeError, match="no connected unit disk graph"):
        heldout.generate_one("H2a", 200, 4, 1)
    monkeypatch.setattr(
        heldout,
        "FAMILIES",
        {**heldout.FAMILIES, "H2a": ("deg", [(25, 8), (200, 4)], ())},
    )
    with pytest.raises(RuntimeError):
        heldout.generate("H2a", tmp_path, seeds=[1])
    assert not any(tmp_path.iterdir())  # nothing written when one cell fails


@pytest.mark.parametrize(
    "family,n,param",
    [
        ("H1", 20, 4),
        ("H1-large", 500, 2),
        ("H2a", 25, 8),
        ("H2b", 50, 2),
        ("W", 30, 6),
        ("M9", 30, 6),
    ],
)
def test_deterministic_per_seed(family, n, param):
    a = heldout.generate_one(family, n, param, 7)
    assert a == heldout.generate_one(family, n, param, 7)
    assert a[:2] != heldout.generate_one(family, n, param, 8)[:2]


def test_seed_guards_and_no_overwrite(tmp_path):
    with pytest.raises(ValueError):
        heldout.generate("H1", tmp_path, seeds=[1, 101])
    with pytest.raises(ValueError):
        heldout.validate(seeds=[905])
    heldout.generate("W", tmp_path, seeds=[4])
    with pytest.raises(FileExistsError):
        heldout.generate("W", tmp_path, seeds=[4])


def test_plan_matches_preregistration_counts():
    # plan() only lists (family, n, param, seed); it draws nothing
    counts = {s: len(heldout.plan(s)) for s in (*heldout.FAMILIES, "reserve")}
    assert counts == {
        "H1": 160,
        "H1-large": 8,
        "H2a": 80,
        "H2b": 80,
        "W": 20,
        "M9": 20,
        **{f: 30 for f in heldout.WEIGHT_FAMILIES},
        "reserve": 348,
    }
    assert len(heldout.plan(heldout.M8_WEIGHTS)) == 120
    reserve = heldout.plan("reserve")
    assert {s for *_, s in reserve} == set(range(901, 911))
    assert "M9" not in {f for f, *_ in reserve}
    assert {p for f, _, p, _ in reserve if f == "H2a"} == {6, 8}  # Amendment 2
    assert (
        sorted(n for _, n, _, _ in heldout.plan("M9")) == [20] * 7 + [30] * 7 + [50] * 6
    )
    assert heldout.PREREGISTERED == set(range(101, 111)) | set(range(201, 211)) | set(
        range(301, 311)
    ) | set(range(401, 411)) | set(range(501, 521)) | set(range(901, 911))


def test_ks_statistic_and_parse_seeds():
    assert heldout.ks_statistic([1, 2, 3], [1, 2, 3]) == 0
    assert heldout.ks_statistic([1, 1], [2, 2]) == 1
    assert heldout.ks_statistic([1, 2, 3, 4], [3, 4, 5, 6]) == 0.5
    assert heldout.parse_seeds("1-3") == [1, 2, 3]
    assert heldout.parse_seeds("1,5") == [1, 5]


@pytest.mark.skipif(
    matrix.dataset_dir() is None, reason="published dataset not present"
)
def test_validate_compares_with_published_files():
    rows = heldout.validate(seeds=[1, 2], cells=[("H1", 10, 2)])
    assert len(rows) == 1 and rows[0]["files_pub"] == 10 and rows[0]["files_gen"] == 2
    assert 0 <= rows[0]["ks_gen_pub"] <= 1
    assert "| 10 | 20 | 10 |" in heldout.validation_table(rows)


def test_sealed_sets_refused_before_the_frozen_tag(tmp_path, monkeypatch):
    from ccvc.bb import hga_ref

    monkeypatch.setattr(hga_ref, "frozen_tag_exists", lambda *a: False)
    monkeypatch.setattr(
        heldout, "generate_one", lambda *a: pytest.fail("a sealed instance was drawn")
    )
    for set_name in ("H1", heldout.M8_WEIGHTS, "reserve"):
        with pytest.raises(PermissionError, match="coverweave-r1-frozen"):
            heldout.generate(set_name, tmp_path)
    assert heldout.main(["--set", "M9", "--out", str(tmp_path)]) == 2
    assert not any(tmp_path.iterdir())


def test_m8_weight_laws_on_the_h1_graphs(tmp_path):
    m = heldout.generate(heldout.M8_WEIGHTS, tmp_path, seeds=[1])
    names = [Path(e["file"]).name for e in m["files"]]
    assert len(names) == 24 and len(set(names)) == 24
    assert {e["family"] for e in m["files"]} == set(heldout.WEIGHT_FAMILIES)
    for e in m["files"]:
        law = heldout.WEIGHT_FAMILIES[e["family"]]
        assert e["file"].endswith(f"_s1_{law}.txt") and e["m"] == e["n"] * e["ratio"]
        w, edges = matrix.load_instance(str(tmp_path / e["file"]))
        assert edges == heldout.generate_one("H1", e["n"], e["ratio"], 1)[1]
        deg = [sum(v in uv for uv in edges) for v in range(e["n"])]
        if law == "unit":
            assert set(w.values()) == {1.0}
        elif law == "degree":
            assert [w[v] for v in range(e["n"])] == deg
        elif law == "energy":
            assert all(20.0 <= x <= 200.0 for x in w.values())
        else:
            assert min(w.values()) < 20.0 < max(w.values())
