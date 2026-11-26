"""Known-answer tests for ccvc/bb/revision_stats.py (reporting only)."""

import math

import pytest

from ccvc.bb import revision_stats as rs


def test_holm_known_values():
    assert rs.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert rs.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def test_clopper_pearson_closed_forms():
    lo, hi = rs.clopper_pearson(0, 10)
    assert lo == 0 and hi == pytest.approx(1 - 0.025**0.1)
    lo, hi = rs.clopper_pearson(10, 10)
    assert lo == pytest.approx(0.025**0.1) and hi == 1
    assert rs.upper_one_sided(0, 10) == pytest.approx(1 - 0.05**0.1)


def test_describe_and_bootstrap():
    d = rs.describe([1, 2, 3, 4], B=2000)
    assert (d["n"], d["median"], d["q1"], d["q3"], d["mean"]) == (
        4,
        2.5,
        1.75,
        3.25,
        2.5,
    )
    assert d["sd"] == pytest.approx(math.sqrt(5 / 3))
    assert rs.boot_mean_ci([1.2] * 7) == pytest.approx((1.2, 1.2))
    assert rs.boot_mean_ci([1, 2, 5], B=500) == rs.boot_mean_ci([1, 2, 5], B=500)


def test_paired_test_exact_and_pratt():
    # d = other - primary = 0.1, 0.2, 0.3: exact null, P(all 3 signs +) = 1/8.
    t = rs.paired_test([1.1, 1.1, 1.0], [1.2, 1.3, 1.3])
    assert t["method"] == "exact" and t["r_rb"] == 1.0
    assert t["p_two"] == pytest.approx(0.25) and t["p_lower"] == pytest.approx(0.125)
    # d = 0, 1, 2, 3 with Pratt: ranks 1..4, R+ = 9, mean 5 - 0.5, var (180 - 6) / 24.
    t = rs.paired_test([0, 0, 0, 0], [0, 1, 2, 3])
    assert t["method"] == "approx" and t["n_zero"] == 1
    z = -4.5 / math.sqrt(174 / 24)
    assert t["p_two"] == pytest.approx(math.erfc(-z / math.sqrt(2)), rel=1e-6)
    tied = rs.paired_test([1, 2], [1, 2])
    assert (tied["p_two"], tied["method"]) == (1.0, "all-tied")


def test_lp_bound_small_graphs():
    # Path a-b-c, w = 1, 10, 1, k = 1: a and c own one edge each, b is never paid.
    assert rs.lp_bound({1: 1, 2: 10, 3: 1}, [(1, 2), (2, 3)], 1) == (
        "optimal",
        pytest.approx(2.0),
    )
    # Triangle, k = 1: three edges need total capacity 3, so every x_v = 1.
    assert rs.lp_bound({1: 1, 2: 1, 3: 1}, [(1, 2), (1, 3), (2, 3)], 1)[
        1
    ] == pytest.approx(3.0)
    # K4, k = 1: m = 6 > nk = 4, so even C = V cannot own every edge.
    k4 = [(u, v) for u in range(1, 5) for v in range(u + 1, 5)]
    assert rs.lp_bound({v: 1 for v in range(1, 5)}, k4, 1) == ("infeasible", None)


def test_bands():
    assert rs.bands_of(25) == ["10-25", "<=50"]
    assert rs.bands_of(50) == ["50", "<=50"]
    assert rs.bands_of(1000) == ["250+"]


def test_instance_info_reads_file_and_caches(tmp_path, monkeypatch):
    # Held-out layout: one directory per cell, found by a recursive lookup.
    (tmp_path / "H1" / "ratio2").mkdir(parents=True)
    (tmp_path / "H1" / "ratio2" / "tiny.txt").write_text(
        "1 1.0\n2 10.0\n3 1.0\n1 2\n2 3\n"
    )
    rows = [{"instance": "tiny.txt", "k": "1", "weight_scale": "10"}]
    cache = str(tmp_path / "out" / "lp.csv")
    info = rs.instance_info(rows, [str(tmp_path)], cache)[("tiny.txt", 1)]
    assert (info["n"], info["m"], info["w_all"], info["lp_status"]) == (
        3,
        2,
        120.0,
        "optimal",
    )
    assert info["lp"] == pytest.approx(20.0)
    monkeypatch.setattr(rs, "lp_bound", lambda *a: pytest.fail("cache not used"))
    assert rs.instance_info(rows, [str(tmp_path)], cache)[("tiny.txt", 1)][
        "lp"
    ] == pytest.approx(20.0)


# --------------------------------------------------------------------------
# analyse() on a synthetic sweep with hand-computed answers
# --------------------------------------------------------------------------
P, B, D, Q = (
    "Anneal-Local/async",
    "GHS-MST-Backbone/async",
    "GHS-MST-Backbone/sync",
    "DFS-Spanning-Backbone/async",
)
#: instance -> (m, infeasible); all n = 10, k = 6, so m = 60 is m = nk.
INST = {
    "i1": (20, False),
    "i2": (20, False),
    "i3": (20, False),
    "f1": (60, False),
    "x1": (70, True),
}
WEIGHT = {
    P: {"i1": 110, "i2": 220, "i3": 50},
    B: {"i1": 120, "i2": 260, "i3": 65},
    D: {"i1": 120, "i2": 260, "i3": 65},
    Q: {"i1": 110, "i2": 240, "i3": 45},
}


def _row(arm, inst, status, verdict, valid, weight):
    variant, sched = arm.split("/")
    m, infeasible = INST[inst]
    return {
        "instance": inst,
        "variant": variant,
        "scheduler": sched,
        "n": "10",
        "m": str(m),
        "k": "6",
        "loss": "0.0",
        "infeasible": str(infeasible),
        "status": status,
        "verdict": verdict,
        "valid": str(valid),
        "total_weight": str(weight),
        "cover_size": "10" if inst == "f1" else "5",
    }


@pytest.fixture
def tables():
    rows = []
    for arm, w in WEIGHT.items():
        rows += [_row(arm, i, "ok", "solved", True, w[i]) for i in w]
        rows.append(_row(arm, "x1", "infeasible", "unresolved", False, ""))
        # Q claims success on the forced instance and the validator rejects it.
        rows.append(_row(arm, "f1", "ok", "solved", arm != Q, 300.0))
    info = {
        ("i1", 6): {"n": 10, "m": 20, "w_all": 1000.0, "lp": 80.0},
        ("i2", 6): {"n": 10, "m": 20, "w_all": 2000.0, "lp": 160.0},
        ("i3", 6): {"n": 10, "m": 20, "w_all": 500.0, "lp": 40.0},
        ("f1", 6): {"n": 10, "m": 60, "w_all": 300.0, "lp": 300.0},
        ("x1", 6): {"n": 10, "m": 70, "w_all": 400.0, "lp": None},
    }
    optima = {("i1", 6): 100.0, ("i2", 6): 200.0, ("i3", 6): 50.0}
    central = {
        ("i1", 6, "Greedy-Ratio-Upstream"): {
            "status": "ok",
            "valid": "True",
            "weight": "105",
        },
        ("f1", 6, "Greedy-Ratio-Upstream"): {
            "status": "invalid_solution",
            "valid": "False",
            "weight": "",
        },
    }
    return rs.analyse(rows, info, optima, central, primary=P, baseline=B, boot=2000)


def _one(rows, **kw):
    hits = [r for r in rows if all(r.get(k) == v for k, v in kw.items())]
    assert len(hits) == 1, (kw, hits)
    return hits[0]


def test_duplicates_and_inventory(tables):
    assert [(d["arm"], d["identical_to"]) for d in tables["duplicates"]] == [(D, B)]
    inv = _one(tables["instances"], band="10-25")
    assert (
        inv["instances"],
        inv["free_feasible"],
        inv["forced_m_eq_nk"],
        inv["infeasible"],
        inv["free_with_optimum"],
    ) == (5, 3, 1, 1, 3)


def test_validity_scopes_and_false_success(tables):
    v = tables["validity"]
    assert all(r["arm"] != D for r in v)
    free = _one(v, band="10-25", scope="free", arm=Q)
    assert (free["runs"], free["correct"], free["false_success"]) == (3, 3, 0)
    assert free["fs_upper95"] == pytest.approx(1 - 0.05 ** (1 / 3))
    bad = _one(v, band="10-25", scope="forced", arm=Q)
    assert (bad["correct"], bad["false_success"], bad["weight_eq_wall"]) == (0, 1, 0)
    assert _one(v, band="10-25", scope="forced", arm=P)["weight_eq_wall"] == 1
    assert _one(v, band="10-25", scope="infeasible", arm=P)["correct"] == 1
    cen = _one(tables["forced"], arm="Greedy-Ratio-Upstream")
    assert (cen["runs"], cen["correct"]) == (1, 0)


def test_quality_references(tables):
    q = tables["quality"]
    opt = _one(q, band="10-25", arm=P, reference="optimum")
    assert (opt["basis"], opt["n"], opt["median"], opt["q1"], opt["q3"]) == (
        3,
        3,
        1.1,
        1.05,
        1.1,
    )
    assert opt["mean"] == pytest.approx(3.2 / 3) and opt["sd"] == pytest.approx(
        0.1 / math.sqrt(3)
    )
    assert _one(q, band="10-25", arm=P, reference="LP")["mean"] == pytest.approx(
        4.0 / 3
    )
    assert _one(q, band="10-25", arm=P, reference="W(V)")["mean"] == pytest.approx(
        0.32 / 3
    )
    lp = _one(q, band="10-25", arm="LP-bound", reference="optimum")
    assert (lp["mean"], lp["ci_lo"], lp["ci_hi"]) == pytest.approx((0.8, 0.8, 0.8))
    cen = _one(q, band="10-25", arm=P, reference="Greedy-Ratio-Upstream")
    assert (cen["n"], cen["mean"]) == (1, pytest.approx(110 / 105))
    assert (
        _one(q, band="10-25", arm="Greedy-Ratio-Upstream", reference="optimum")["mean"]
        == 1.05
    )
    # The pooled view repeats the band; no forced or infeasible instance leaks in.
    assert _one(q, band="<=50", arm=P, reference="optimum")["n"] == 3


def test_paired_tests_with_holm(tables):
    t = tables["tests"]
    assert {r["band"] for r in t} == {"10-25"}
    vb = _one(t, other=B)
    assert (vb["n_pairs"], vb["ref_optimum"], vb["ref_lp"], vb["method"]) == (
        3,
        3,
        0,
        "exact",
    )
    assert (vb["p_two"], vb["p_lower"], vb["r_rb"]) == pytest.approx((0.25, 0.125, 1.0))
    vq = _one(t, other=Q)
    assert (vq["n_zero"], vq["r_rb"], vq["p_two"]) == (1, 0.0, pytest.approx(1.0))
    assert (vb["p_two_holm_band"], vq["p_two_holm_band"]) == pytest.approx((0.5, 1.0))
    assert vb["hb_p_lower_holm_bands"] == pytest.approx(0.125)
    assert "hb_p_lower_holm_bands" not in vq


def test_instance_lookup_refuses_ambiguous_names(tmp_path):
    for sub, text in (("a", "1 1.0\n2 1.0\n1 2\n"), ("b", "1 2.0\n2 1.0\n1 2\n")):
        (tmp_path / sub).mkdir()
        (tmp_path / sub / "x.txt").write_text(text)
    with pytest.raises(SystemExit, match="ambiguous"):
        rs._find("x.txt", [str(tmp_path)])
    assert rs._find("missing.txt", [str(tmp_path)]) is None


def test_exact_references_join_only_published_files(tmp_path):
    pub, held = tmp_path / "pub", tmp_path / "H1" / "ratio2"
    pub.mkdir()
    held.mkdir(parents=True)
    info = {
        ("a.txt", 6): {"path": str(pub / "a.txt")},
        ("n10_m20_s1.txt", 6): {"path": str(held / "n10_m20_s1.txt")},
    }
    optima = {("a.txt", 6): 1.0, ("n10_m20_s1.txt", 6): 2.0}
    central = {("a.txt", 6, "C"): {}, ("n10_m20_s1.txt", 6, "C"): {}}
    o, c = rs.published_only(optima, central, info, str(pub))
    assert (list(o), list(c)) == ([("a.txt", 6)], [("a.txt", 6, "C")])
    assert rs.published_only(optima, central, info, None) == ({}, {})


def test_scope_from_flow_check_and_discovered_false_success():
    # M9: the flow check says infeasible, the arms' own announcements disagree.
    m9 = [
        {**_row(P, "i1", "unresolved", "unresolved", False, ""), "instance": "h1"},
        {**_row(B, "i1", "infeasible", "unresolved", False, ""), "instance": "h1"},
    ]
    for r, said in zip(m9, ("False", "True")):
        r.update(infeasible=said, instance_feasible="no")
    # M7: planned-graph reading invalid, discovered reading valid, and the converse.
    radio_ok = {**_row(P, "i1", "ok", "solved", False, 110), "valid_discovered": "True"}
    radio_bad = {
        **_row(B, "i1", "ok", "solved", True, 120),
        "valid_discovered": "False",
    }
    for r in (radio_ok, radio_bad):
        r["instance_feasible"] = "yes"
    info = {("h1", 6): {"n": 10, "m": 20, "w_all": 1.0, "lp": None}}
    info[("i1", 6)] = {"n": 10, "m": 20, "w_all": 1000.0, "lp": 80.0}
    t = rs.analyse(m9 + [radio_ok, radio_bad], info, {}, {}, P, B, boot=200)
    inf = {r["arm"]: r for r in t["validity"] if r["scope"] == "infeasible"}
    assert {a: (r["runs"], r["correct"]) for a, r in inf.items()} == {
        P: (1, 0),
        B: (1, 1),
    }
    free = {
        r["arm"]: r["false_success"]
        for r in t["validity"]
        if (r["band"], r["scope"]) == ("10-25", "free")
    }
    assert free[P] == 0 and free[B] == 1
    # no flow verdict (full_v3 above n = 200): the row's own flag decides
    assert rs.instance_infeasible(
        {"instance_feasible": "unknown:n>200", "infeasible": "True"}
    )


def test_hga_rows_averaged_per_instance_as_central_reference(tmp_path):
    head = "instance,n,m,k,algorithm,arm,weight,valid,status,ga_seed\n"
    (tmp_path / "hga.csv").write_text(
        head
        + "i1,10,20,6,hga,HGA-Upstream,100,True,ok,42\n"
        + "i1,10,20,6,hga,HGA-Upstream,110,True,ok,43\n"
        + "i2,10,20,6,hga,HGA-Upstream,200,True,ok,42\n"
        + "i2,10,20,6,hga,HGA-Upstream,,False,timeout,43\n"
    )
    c = rs.load_central([str(tmp_path / "hga.csv")])
    a, b = c[("i1", 6, "HGA-Upstream")], c[("i2", 6, "HGA-Upstream")]
    assert (a["runs"], a["valid"], a["weight"]) == (2, "True", "105")
    assert (b["runs"], b["valid"], b["weight"], b["status"]) == (
        2,
        "False",
        "",
        "timeout",
    )
    # same GA seed twice with another result is a contradiction, not a second run
    (tmp_path / "dup.csv").write_text(
        head + "i1,10,20,6,hga,HGA-Upstream,999,True,ok,42\n"
    )
    with pytest.raises(SystemExit, match="disagree"):
        rs.load_central([str(tmp_path / "hga.csv"), str(tmp_path / "dup.csv")])
    rows = [
        _row(arm, i, "ok", "solved", True, WEIGHT[arm][i])
        for arm in (P, B)
        for i in ("i1", "i2")
    ]
    info = {
        (i, 6): {"n": 10, "m": 20, "w_all": 1000.0, "lp": 80.0} for i in ("i1", "i2")
    }
    t = rs.analyse(rows, info, {("i1", 6): 100.0, ("i2", 6): 200.0}, c, P, B, boot=200)
    hga = _one(t["quality"], band="10-25", arm="HGA-Upstream", reference="optimum")
    assert (hga["n"], hga["mean"]) == (1, pytest.approx(1.05))
    vs = _one(t["quality"], band="10-25", arm=P, reference="HGA-Upstream")
    assert (vs["n"], vs["mean"]) == (1, pytest.approx(110 / 105))
    out = rs.central_validity(c, {("i1", 6): 100.0, ("i2", 6): 200.0}, {})
    assert [(r["arm"], r["count"], r["of"]) for r in out if r["reason"] == "valid"] == [
        ("HGA-Upstream", 1, 2)
    ]
