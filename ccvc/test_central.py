#!/usr/bin/env python3
"""ccvc/central.py testleri: üç doğruluk kapısı, optimallik, determinizm.

Koşum (depo kökünden):
    python3 -m pytest ccvc/test_central.py -q
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from typing import List, Set, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccvc import bridge, central  # noqa: E402
from ccvc.bridge import CcvcGraph, edge_key  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(REPO, "results", "mds_campus_seed0_frames.json")
GREEDY = ("gccvc", "grccvc", "gwccvc")


# ==========================================================================
# yardımcılar
# ==========================================================================
def random_graph(n: int, p: float, k: int, scheme: str, seed: int) -> CcvcGraph:
    """G(n,p) üstünde CCVC örneği; ağırlıklar bridge şemalarından."""
    rnd = random.Random(seed)
    nodes = list(range(n))
    edges = sorted(
        {edge_key(u, v) for u in range(n) for v in range(u + 1, n) if rnd.random() < p}
    )
    adj = {v: set() for v in nodes}
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    pos = {v: (rnd.uniform(0, 100), rnd.uniform(0, 100), 0.0) for v in nodes}
    w = bridge.weights_for(nodes, adj, scheme, pos, seed)
    return CcvcGraph(nodes=nodes, edges=edges, weight=w, capacity_k=k, adj=adj, pos=pos)


def instance_is_feasible(g: CcvcGraph) -> bool:
    """Zemin gerçeği: örtüye düğüm eklemek kapasiteyi asla bozmaz, yani tüm V
    uygun değilse hiçbir örtü uygun değildir. Tüm V örtüdür ve bileşen bazlı
    bağlıdır, dolayısıyla bu tam bir uygunluk ölçütüdür."""
    return central.capacity_assignment(g, g.nodes)[0]


def check_gates(g: CcvcGraph, res: central.CentralResult) -> None:
    """Üç kapıyı testin kendisi de bağımsızca doğrular (çözücüye güvenmeden)."""
    cov = set(res.cover)
    assert bridge.is_vertex_cover(g, cov), "ortu degil: acikta kenar var"
    assert bridge.is_connected_cover(g, cov), "bilesen icinde ortu kopuk"
    ok, owner = central.capacity_assignment(g, cov)
    assert ok, "kapasite uygun degil"
    # atama gerçekten her kenarı tam bir sahibe veriyor ve k'yı aşmıyor mu
    assert set(owner) == set(g.edges)
    load = {}
    for e, o in owner.items():
        assert o in cov and o in e
        load[o] = load.get(o, 0) + 1
    assert all(v <= g.capacity_k for v in load.values())
    # yalıtık düğüm örtüye girmez
    assert all(g.degree(v) > 0 for v in cov)
    # rapor edilen alanlar tutarlı
    assert res.cover_size == len(cov)
    assert res.total_weight == pytest.approx(g.total_weight(cov))
    assert res.valid and res.feasible and res.status == "ok"
    assert res.bridge_verdict is not None
    assert res.bridge_verdict.vertex_cover and res.bridge_verdict.connected


def run_or_expect_infeasible(
    g: CcvcGraph, name: str, **kw
) -> central.CentralResult | None:
    """Uygunsa geçerli sonuç bekle, değilse CcvcInfeasible bekle."""
    feasible = instance_is_feasible(g)
    if not feasible:
        with pytest.raises(central.CcvcInfeasible):
            central.solve(name, g, **kw)
        soft = central.solve(name, g, strict=False, **kw)
        assert soft.status == "infeasible" and not soft.feasible
        assert soft.cover == set()
        return None
    res = central.solve(name, g, **kw)
    check_gates(g, res)
    return res


def graph_cases() -> List[Tuple[int, float, int, str, int]]:
    """Yoğunluk, boyut, k ve ağırlık şeması taraması: 60 örnek."""
    cases: List[Tuple[int, float, int, str, int]] = []
    seed = 0
    for n in (6, 9, 12, 16, 20):
        for p in (0.08, 0.18, 0.35, 0.6):
            for k, scheme in ((2, "unit"), (3, "random"), (5, "degree")):
                cases.append((n, p, k, scheme, seed))
                seed += 1
    return cases


CASES = graph_cases()


# ==========================================================================
# 1. rastgele çizgelerde üç kapı
# ==========================================================================
@pytest.mark.parametrize("name", GREEDY)
@pytest.mark.parametrize("n,p,k,scheme,seed", CASES)
def test_greedy_valid_on_random_graphs(name, n, p, k, scheme, seed):
    g = random_graph(n, p, k, scheme, seed)
    run_or_expect_infeasible(g, name)


def test_case_sweep_covers_both_outcomes():
    """Tarama hem uygun hem uygunsuz örnek içeriyor mu (test anlamlı mı)."""
    feas = [instance_is_feasible(random_graph(*c)) for c in CASES]
    assert len(CASES) >= 50
    assert sum(feas) >= 20, "uygun ornek az, kapi testi zayif"
    assert feas.count(False) >= 1, "hic uygunsuz ornek yok, k kontrolu test edilmiyor"


@pytest.mark.parametrize("k", (1, 2, 3, 6))
def test_greedy_valid_on_tight_capacity(k):
    """k'yı sıkarak kapasite yükseltmesi ve çözümsüzlük dallarını zorla."""
    for seed in range(12):
        g = random_graph(14, 0.3, k, "unit", 900 + seed)
        for name in GREEDY:
            run_or_expect_infeasible(g, name)


# ==========================================================================
# 2. gerçek simülatör kareleri
# ==========================================================================
def load_real_graphs(k: int, scheme: str = "unit") -> List[CcvcGraph]:
    frames, _meta = bridge.load_frames(FRAMES)
    return [
        bridge.graph_from_frame(f, capacity_k=k, weight_scheme=scheme) for f in frames
    ]


def test_frames_file_present():
    assert os.path.exists(FRAMES), f"kare dosyasi yok: {FRAMES}"


@pytest.mark.parametrize("name", GREEDY)
@pytest.mark.parametrize("k,scheme", ((2, "unit"), (4, "random"), (8, "invdeg")))
def test_greedy_valid_on_real_frames(name, k, scheme):
    graphs = load_real_graphs(k, scheme)
    assert len(graphs) >= 50
    seen_disconnected = False
    for g in graphs:
        if len(bridge.graph_components(g)) > 1:
            seen_disconnected = True
        run_or_expect_infeasible(g, name)
    assert seen_disconnected, "gercek karelerde kopuk cizge bekleniyordu"


def test_real_frames_have_isolated_vertices():
    """PLAN §0.5: karelerde yalıtık düğüm var; örtüye asla girmemeli."""
    graphs = load_real_graphs(4)
    isolated_seen = False
    for g in graphs:
        iso = {v for v in g.nodes if g.degree(v) == 0}
        if not iso:
            continue
        isolated_seen = True
        res = central.solve("grccvc", g)
        assert not (res.cover & iso)
    assert isolated_seen, "hicbir karede yalitik dugum yok"


# ==========================================================================
# 3. tam çözüm optimum, greedy onu geçemez
# ==========================================================================
EXACT_CASES = [
    (n, p, k, scheme, 5000 + i)
    for i, (n, p, k, scheme) in enumerate(
        [
            (n, p, k, scheme)
            for n in (6, 8, 10, 12)
            for p in (0.15, 0.3, 0.5)
            for k, scheme in ((2, "unit"), (3, "random"))
        ]
    )
]


@pytest.mark.parametrize("n,p,k,scheme,seed", EXACT_CASES)
def test_exact_never_worse_than_greedy(n, p, k, scheme, seed):
    g = random_graph(n, p, k, scheme, seed)
    if not instance_is_feasible(g):
        with pytest.raises(central.CcvcInfeasible):
            central.solve_exact(g, max_n=18, time_limit_s=60.0)
        return
    ex = central.solve_exact(g, max_n=18, time_limit_s=60.0)
    check_gates(g, ex)
    assert not ex.timed_out and ex.exact
    for name in GREEDY:
        gr = central.solve(name, g)
        check_gates(g, gr)
        assert (
            ex.total_weight <= gr.total_weight + 1e-9
        ), f"tam cozum {name}'den kotu: {ex.total_weight} > {gr.total_weight}"


@pytest.mark.parametrize("n,p,k,scheme,seed", EXACT_CASES[:12])
def test_greedy_never_better_than_exact(n, p, k, scheme, seed):
    """Aynı iddianın diğer yönü: hiçbir greedy optimumun altına inemez."""
    g = random_graph(n, p, k, scheme, seed)
    if not instance_is_feasible(g):
        pytest.skip("uygunsuz ornek")
    ex = central.solve_exact(g, max_n=18, time_limit_s=60.0)
    for name in GREEDY:
        gr = central.solve(name, g)
        assert gr.total_weight >= ex.total_weight - 1e-9


def test_exact_matches_brute_force_on_tiny_graphs():
    """Dal-sınır'ı bağımsız kaba kuvvetle karşılaştır (n <= 10, tüm altkümeler)."""
    for seed in range(25):
        g = random_graph(8, 0.35, 2, "random", 7000 + seed)
        best = float("inf")
        nodes = list(g.nodes)
        for mask in range(1 << len(nodes)):
            cov = {nodes[i] for i in range(len(nodes)) if mask >> i & 1}
            if not bridge.is_vertex_cover(g, cov):
                continue
            if not bridge.is_connected_cover(g, cov):
                continue
            if not central.capacity_assignment(g, cov)[0]:
                continue
            best = min(best, g.total_weight(cov))
        if best == float("inf"):
            with pytest.raises(central.CcvcInfeasible):
                central.solve_exact(g, max_n=18, time_limit_s=60.0)
            continue
        ex = central.solve_exact(g, max_n=18, time_limit_s=60.0)
        assert ex.total_weight == pytest.approx(best), f"seed={seed}"


def test_exact_rejects_oversized_component():
    g = random_graph(24, 0.5, 6, "unit", 31)
    with pytest.raises(ValueError):
        central.solve_exact(g, max_n=18)


def test_exact_time_limit_is_honoured():
    """Süre sıfıra yakınken zaman aşımı bayrağı kalkar, sonuç yine geçerlidir."""
    g = random_graph(18, 0.35, 4, "random", 41)
    if not instance_is_feasible(g):
        pytest.skip("uygunsuz ornek")
    res = central.solve_exact(g, max_n=18, time_limit_s=1e-6)
    check_gates(g, res)
    assert res.timed_out and not res.exact


# ==========================================================================
# 4. determinizm
# ==========================================================================
@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_determinism_same_process(name):
    for seed in (11, 12, 13, 14, 15):
        g = random_graph(12, 0.3, 3, "random", seed)
        if not instance_is_feasible(g):
            continue
        kw = {"max_n": 18, "time_limit_s": 60.0} if name == "exact" else {}
        a = json.dumps(central.solve(name, g, **kw).as_dict(), sort_keys=True)
        b = json.dumps(central.solve(name, g, **kw).as_dict(), sort_keys=True)
        assert a == b


def test_determinism_across_processes():
    """Ayrı yorumlayıcı süreçlerinde de bit birebir aynı (küme sırası tuzağı)."""
    script = (
        "import json,sys;sys.path.insert(0,%r);"
        "from ccvc import bridge, central;"
        "f,_=bridge.load_frames(%r);"
        "g=bridge.graph_from_frame(f[3],capacity_k=4,weight_scheme='random');"
        "print(json.dumps([central.solve(n,g).as_dict() for n in "
        "('gccvc','grccvc','gwccvc')],sort_keys=True))" % (REPO, FRAMES)
    )
    outs = [
        subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=True
        ).stdout
        for _ in range(2)
    ]
    assert outs[0] == outs[1] and outs[0].strip()


def test_owner_map_is_deterministic():
    g = random_graph(14, 0.3, 3, "unit", 77)
    if not instance_is_feasible(g):
        pytest.skip("uygunsuz ornek")
    runs = [central.solve("gccvc", g).owner for _ in range(5)]
    assert all(r == runs[0] for r in runs)


# ==========================================================================
# 5. mark_red_nodes: temizlenmiş sürüm sadık sürümle birebir aynı
# ==========================================================================
def test_mark_red_cleanup_matches_faithful_version():
    """Denetim iddiası: (b) dalı ölü kod, cover_set kullanılmıyor.

    30'dan fazla rastgele çizgede her üç greedy'nin ürettiği örtü (ve kenar
    ataması) iki sürümde birebir aynı olmalı.
    """
    checked = 0
    for seed in range(60):
        n = 8 + seed % 13
        p = (0.12, 0.25, 0.45, 0.7)[seed % 4]
        k = (1, 2, 3, 5)[seed % 4]
        g = random_graph(n, p, k, ("unit", "random", "degree")[seed % 3], 2000 + seed)
        if not instance_is_feasible(g):
            continue
        for name in GREEDY:
            clean = central.solve(name, g, faithful_red=False)
            faith = central.solve(name, g, faithful_red=True)
            assert clean.as_dict() == faith.as_dict(), f"{name} seed={seed}"
        checked += 1
    assert checked >= 30, f"yalnizca {checked} ornek denendi, >=30 gerek"


def test_mark_red_cleanup_matches_faithful_on_real_frames():
    for k in (3, 6):
        for g in load_real_graphs(k, "random"):
            if not instance_is_feasible(g):
                continue
            for name in GREEDY:
                assert (
                    central.solve(name, g, faithful_red=False).as_dict()
                    == central.solve(name, g, faithful_red=True).as_dict()
                )


def test_mark_red_branch_b_is_a_noop_directly():
    """Renk sabit noktası düzeyinde doğrudan kanıt: iki sürüm aynı renkleri verir."""
    for seed in range(30):
        g = random_graph(10 + seed % 8, 0.3, 2 + seed % 4, "unit", 3000 + seed)
        for comp in central._components(g):
            sub = central._subgraph(g, comp)
            a = central._Component(sub)
            b = central._Component(sub)
            a.mark_red_nodes(faithful=False)
            b.mark_red_nodes(faithful=True)
            assert a.color == b.color


# ==========================================================================
# 6. kopuk çizge, yalıtık düğüm, kenarsız çizge
# ==========================================================================
def make_graph(nodes, edges, k, weights=None) -> CcvcGraph:
    w = weights or {v: 1.0 for v in nodes}
    return CcvcGraph(
        nodes=list(nodes),
        edges=sorted(edge_key(u, v) for u, v in edges),
        weight=w,
        capacity_k=k,
    )


@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_two_disjoint_triangles(name):
    """Küresel bağlı örtü VAR OLAMAZ; bileşen bazlı tanım çözüyor."""
    g = make_graph(range(6), [(0, 1), (1, 2), (0, 2), (3, 4), (4, 5), (3, 5)], 3)
    res = central.solve(name, g)
    check_gates(g, res)
    assert not bridge.is_connected_cover.__doc__.startswith("x")  # tanım bileşen bazlı
    assert len(bridge.cover_components(g, res.cover)) == 2


@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_isolated_vertices_never_enter_cover(name):
    g = make_graph(range(7), [(0, 1), (1, 2), (2, 0)], 3)  # 3,4,5,6 yalıtık
    res = central.solve(name, g)
    check_gates(g, res)
    assert res.cover & {3, 4, 5, 6} == set()


@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_graph_with_no_edges(name):
    g = make_graph(range(5), [], 2)
    res = central.solve(name, g)
    assert res.cover == set() and res.valid and res.total_weight == 0.0


@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_empty_graph(name):
    g = make_graph([], [], 2)
    res = central.solve(name, g)
    assert res.cover == set() and res.valid


@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_single_edge(name):
    g = make_graph([0, 1], [(0, 1)], 1)
    res = central.solve(name, g)
    check_gates(g, res)
    assert res.cover_size == 1


def test_disconnected_path_components_need_bridging():
    """Bir yolun iki ucu örtüde, orta düğüm köprü olarak eklenmeli."""
    g = make_graph(
        range(5),
        [(0, 1), (1, 2), (2, 3), (3, 4)],
        4,
        weights={0: 1.0, 1: 1.0, 2: 50.0, 3: 1.0, 4: 1.0},
    )
    for name in GREEDY + ("exact",):
        res = central.solve(name, g)
        check_gates(g, res)


def test_many_components_mixed_sizes():
    edges = [(0, 1), (1, 2), (3, 4), (5, 6), (6, 7), (7, 5), (8, 9)]
    g = make_graph(range(12), edges, 2)  # 10, 11 yalıtık
    for name in GREEDY + ("exact",):
        res = central.solve(name, g)
        check_gates(g, res)
        assert res.cover & {10, 11} == set()


# ==========================================================================
# 7. k çok küçük: çözümsüzlük bildirilir, çöp döndürülmez
# ==========================================================================
@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_k_too_small_reports_infeasible(name):
    """Üçgende k=1: 3 kenar en fazla 3 sahip x 1 = 3 taşınabilir gibi görünse de
    bağlı örtü en fazla 2 düğüm gerektirmez; asıl kilit tüm V ile bile
    uygunsuz olan durumdur. K4, k=1: 6 kenar, 4 düğüm x 1 = 4 < 6."""
    g = make_graph(range(4), [(a, b) for a in range(4) for b in range(a + 1, 4)], 1)
    assert not instance_is_feasible(g)
    with pytest.raises(central.CcvcInfeasible):
        central.solve(name, g)
    soft = central.solve(name, g, strict=False)
    assert soft.status == "infeasible"
    assert not soft.feasible and not soft.valid
    assert soft.cover == set() and soft.owner == {}
    assert any("cozumsuz" in n for n in soft.notes)


@pytest.mark.parametrize("name", GREEDY + ("exact",))
def test_k_zero_is_infeasible_when_edges_exist(name):
    g = make_graph(range(3), [(0, 1), (1, 2)], 0)
    with pytest.raises(central.CcvcInfeasible):
        central.solve(name, g)


def test_k_zero_ok_when_no_edges():
    g = make_graph(range(3), [], 0)
    for name in GREEDY + ("exact",):
        assert central.solve(name, g).valid


def test_infeasibility_is_per_component():
    """Bir bileşen çözümsüzse tüm örnek çözümsüz sayılır ve bu bildirilir."""
    edges = [(a, b) for a in range(4) for b in range(a + 1, 4)] + [(4, 5)]
    g = make_graph(range(6), edges, 1)
    assert not instance_is_feasible(g)
    soft = central.solve("gccvc", g, strict=False)
    assert soft.status == "infeasible"
    # cozumsuz bilesen K4 (kok dugum 0); saglam olan {4,5} bileseni sonuca giremez
    assert any("[0]" in n for n in soft.notes), soft.notes
    assert soft.cover == set()


# ==========================================================================
# 8. kapasite kapısı: bridge.capacity_feasible yanlış pozitif veriyor
# ==========================================================================
def assert_owner_map_is_sound(g: CcvcGraph, cov: Set[int], owner: dict) -> None:
    """Atama gerçekten her kenarı örtüdeki bir uca veriyor ve k'yı aşmıyor mu."""
    assert set(owner) == set(g.edges), "her kenar tam olarak bir kez atanmali"
    load = {}
    for e, o in owner.items():
        assert o in e and o in cov, f"sahip {o} kenarin ucu ve ortude olmali: {e}"
        load[o] = load.get(o, 0) + 1
    assert max(load.values(), default=0) <= g.capacity_k, f"k={g.capacity_k} asildi"


def test_bridge_triangle_regression():
    """GERİLEME TESTİ: üçgen 0-1-2, C={0,1}, k=1 uygunsuz olmalı.

    bridge.capacity_feasible'in eski sezgisel sürümü buna "uygun" diyordu
    (tahliye ettiği kenarı aynı düğüme geri koyup yükü k+1'e çıkarıyordu).
    2026-09-11'de tam Edmonds-Karp b-eşlemesiyle değiştirildi. 3 kenar, 2 sahip,
    k=1 -> 2 < 3, yani doğru yanıt kesinlikle False.
    """
    g = make_graph([0, 1, 2], [(0, 1), (0, 2), (1, 2)], 1)
    bridge_ok, bridge_owner = bridge.capacity_feasible(g, {0, 1})
    assert not bridge_ok, "3 kenar 2 sahibe k=1 ile sigmaz"
    assert bridge_owner == {}
    ours_ok, ours_owner = central.capacity_assignment(g, {0, 1})
    assert not ours_ok and ours_owner == {}

    # tüm V ile uygun, ve iki gerçekleme de saglam bir atama vermeli
    for ok, owner in (
        bridge.capacity_feasible(g, {0, 1, 2}),
        central.capacity_assignment(g, {0, 1, 2}),
    ):
        assert ok
        assert_owner_map_is_sound(g, {0, 1, 2}, owner)


def test_bridge_and_dinic_agree_on_random_instances():
    """İki bağımsız maksimum akış her zaman aynı yanıtı vermeli. Ayrışma = HATA.

    bridge.capacity_feasible Edmonds-Karp, central._bmatching Dinic. Farklı
    algoritmalar, aynı b-eşleme örgüsü. Ayrışırlarsa biri bozulmuştur ve bunu
    derhal bilmek isteriz, o yüzden burada sert hata.
    """
    rnd = random.Random(20260911)
    checked = 0
    both_outcomes = [0, 0]
    for _ in range(400):
        n = rnd.randint(3, 12)
        k = rnd.randint(1, 4)
        g = random_graph(n, rnd.choice((0.15, 0.3, 0.5, 0.75)), k, "unit", rnd.randint(0, 10**9))
        if not g.edges:
            continue
        cov = {v for v in g.nodes if rnd.random() < rnd.choice((0.4, 0.7, 1.0))}
        b_ok, b_owner = bridge.capacity_feasible(g, cov)
        d_ok, d_owner = central.capacity_assignment(g, cov)
        assert b_ok == d_ok, (
            f"KAPASITE AYRISMASI: bridge={b_ok} dinic={d_ok} "
            f"n={n} k={k} |E|={len(g.edges)} cover={sorted(cov)} edges={g.edges}"
        )
        if b_ok:
            # yalnız evet/hayır değil, ürettikleri atama da geçerli olmalı
            assert_owner_map_is_sound(g, cov, b_owner)
            assert_owner_map_is_sound(g, cov, d_owner)
        both_outcomes[int(b_ok)] += 1
        checked += 1
    assert checked >= 300, f"yalnizca {checked} ornek denendi"
    assert min(both_outcomes) >= 30, f"tek yonlu tarama, dagilim={both_outcomes}"


def test_bridge_and_dinic_agree_on_real_frames():
    """Gerçek karelerde de, çözücü örtüleri ve rastgele örtüler üstünde."""
    rnd = random.Random(7)
    for k in (2, 4, 8):
        for g in load_real_graphs(k, "random"):
            for _ in range(3):
                cov = {v for v in g.nodes if rnd.random() < 0.6}
                b_ok, b_owner = bridge.capacity_feasible(g, cov)
                d_ok, d_owner = central.capacity_assignment(g, cov)
                assert b_ok == d_ok, f"AYRISMA k={k} cover={sorted(cov)}"
                if b_ok:
                    assert_owner_map_is_sound(g, cov, b_owner)
                    assert_owner_map_is_sound(g, cov, d_owner)


def test_solver_results_never_report_capacity_disagreement():
    """Çözücü çıktılarında bridge ile Dinic ayrışmamalı; ayrışırsa not düşülür."""
    for k in (2, 4):
        for g in load_real_graphs(k, "unit"):
            if not instance_is_feasible(g):
                continue
            for name in GREEDY:
                res = central.solve(name, g)
                assert res.bridge_capacity == res.capacity_feasible
                assert not any("AYRISMA" in n for n in res.notes), res.notes


def test_capacity_assignment_agrees_with_brute_force():
    """Küçük örneklerde akış yanıtı, tüm atamaların kaba kuvvet taramasıyla aynı."""
    rnd = random.Random(4242)
    for _ in range(120):
        n = rnd.randint(3, 6)
        g = random_graph(n, 0.55, rnd.randint(1, 3), "unit", rnd.randint(0, 10**6))
        if not g.edges:
            continue
        cov = {v for v in g.nodes if rnd.random() < 0.7}
        flow_ok, owner = central.capacity_assignment(g, cov)

        brute = False
        for mask in range(1 << len(g.edges)):
            load = {}
            good = True
            for i, (u, v) in enumerate(g.edges):
                pick = v if mask >> i & 1 else u
                if pick not in cov:
                    good = False
                    break
                load[pick] = load.get(pick, 0) + 1
                if load[pick] > g.capacity_k:
                    good = False
                    break
            if good:
                brute = True
                break
        assert flow_ok == brute
        if flow_ok:
            load = {}
            for e, o in owner.items():
                assert o in e and o in cov
                load[o] = load.get(o, 0) + 1
            assert set(owner) == set(g.edges)
            assert max(load.values(), default=0) <= g.capacity_k


# ==========================================================================
# 9. arayüz sözleşmesi
# ==========================================================================
def test_result_carries_required_fields():
    g = random_graph(12, 0.3, 4, "random", 8)
    res = central.solve("grccvc", g)
    assert res.algorithm == "GRCCVC"
    assert isinstance(res.cover, set) and isinstance(res.owner, dict)
    assert res.total_weight >= 0 and res.cover_size == len(res.cover)
    assert res.vertex_cover and res.connected and res.capacity_feasible
    assert res.bridge_verdict is not None and res.time_ms >= 0.0


def test_unknown_solver_name():
    g = random_graph(5, 0.4, 2, "unit", 1)
    with pytest.raises(ValueError):
        central.solve("nope", g)


def test_solvers_registry_complete():
    assert set(central.SOLVERS) == {"gccvc", "grccvc", "gwccvc", "exact"}


def test_solver_error_on_invalid_cover():
    """_finish bir kapıdan geçmeyen örtüyü sessizce döndürmez."""
    g = make_graph([0, 1, 2], [(0, 1), (1, 2)], 2)
    with pytest.raises(central.CcvcSolverError):
        central._finish("FAKE", g, {0}, 0.0, [], strict=True)
    soft = central._finish("FAKE", g, {0}, 0.0, [], strict=False)
    assert soft.status == "invalid" and not soft.valid


# ==========================================================================
# 10. geri-çekilme siyaseti (force_cover_remaining denetimi)
# ==========================================================================
def main_loop_exit_state(g: CcvcGraph, algo: str):
    """Ana greedy döngüsünü elle koştur ve TAM ÇIKIŞ ANINDAKİ durumu döndür.

    Döndürür: (örtü, açıkta kalan kenarlar, evre-durumu) bileşen bileşen.
    """
    _lbl, picker, sorter = central._RULES[algo]
    out = []
    for comp in central._components(g):
        sub = central._subgraph(g, comp)
        c = central._Component(sub)
        if not c.edges:
            continue
        while c.has_uncovered():
            c.mark_red_nodes(False)
            v = picker(c, False)
            if v is None:
                break
            c.select_node(v, sorter, False)
        out.append((comp[0], c, [e for e in c.edges if e not in c.covered]))
    return out


@pytest.mark.parametrize("algo", GREEDY)
def test_main_loop_exit_always_leaves_a_valid_vertex_cover(algo):
    """YAPISAL İDDİA. Ana döngü açıkta kenarla çıktığında örtü ZATEN tepe örtüsüdür.

    Açıkta kalan hiçbir kenarın iki ucu birden SİYAH-olmayan olamaz: öyle bir
    (u,v) olsaydı uncovered_degree(v, exclude_black=True) >= 1 olur ve v aday
    havuzunda kalırdı (algorithms.py 548 + 134-135), döngü de çıkmazdı.
    Bu test o iddiayı gerçek ve rastgele çizgelerde doğrular. İddia çökerse
    "flow" siyasetinin gerekçesi de çöker, o yüzden burada sert hata.
    """
    graphs = load_real_graphs(3, "unit") + load_real_graphs(2, "random")
    graphs += [random_graph(n, p, k, "random", 400 + n) for n in (10, 14, 18) for p in (0.2, 0.4) for k in (1, 2, 3)]
    saw_exit = False
    for g in graphs:
        if not instance_is_feasible(g):
            continue
        for _root, c, leftover in main_loop_exit_state(g, algo):
            if not leftover:
                continue
            saw_exit = True
            for u, v in leftover:
                assert c.color[u] == "BLACK" or c.color[v] == "BLACK", (
                    f"iki ucu da siyah olmayan acik kenar {(u, v)}: yapisal iddia coktu"
                )
            assert all(u in c.cover or v in c.cover for u, v in c.edges), (
                "ana dongu cikisinda ortu tepe ortusu degil"
            )
    assert saw_exit, "hicbir ornekte ana dongu erken cikmadi, test bos kosuyor"


@pytest.mark.parametrize("policy", central.FALLBACK_POLICIES)
@pytest.mark.parametrize("algo", GREEDY)
def test_both_policies_produce_valid_covers(algo, policy):
    """Her iki siyaset de erişilebilir ve her ikisi de üç kapıdan geçer."""
    for g in load_real_graphs(3, "random")[:40]:
        if not instance_is_feasible(g):
            continue
        check_gates(g, central.solve(algo, g, fallback_policy=policy))
    for n, p, k, scheme, seed in CASES[:20]:
        g = random_graph(n, p, k, scheme, seed)
        if not instance_is_feasible(g):
            continue
        check_gates(g, central.solve(algo, g, fallback_policy=policy))


@pytest.mark.parametrize("algo", GREEDY)
def test_flow_policy_is_never_worse_than_eager(algo):
    """"flow" yalnız gereksiz eklemeyi durdurur, asla ağırlık ekleyemez."""
    strictly_better = 0
    total = 0
    for k in (2, 3, 4, 6):
        for g in load_real_graphs(k, "random")[:25]:
            if not instance_is_feasible(g):
                continue
            e = central.solve(algo, g, fallback_policy="eager")
            f = central.solve(algo, g, fallback_policy="flow")
            check_gates(g, e)
            check_gates(g, f)
            assert f.total_weight <= e.total_weight + 1e-9
            assert f.cover_size <= e.cover_size
            total += 1
            if f.total_weight < e.total_weight - 1e-9:
                strictly_better += 1
    assert total > 0
    assert strictly_better > 0, "flow hicbir yerde kazanmadi, siyaset olcum disi"


@pytest.mark.parametrize("algo", GREEDY)
def test_flow_policy_skips_only_when_flow_really_says_feasible(algo):
    """Atlama kararı keyfi değil: atlandığı her yerde örtü gerçekten uygun."""
    checked = 0
    for k in (2, 3, 4):
        for g in load_real_graphs(k, "unit"):
            if not instance_is_feasible(g):
                continue
            res = central.solve(algo, g, fallback_policy="flow")
            # notlar bilesen bazli: "bilesen@<kok>: ..." -- kok ile eslestir
            skipped = {
                int(n.split("@", 1)[1].split(":", 1)[0])
                for n in res.notes
                if "fallback atlandi" in n
            }
            fired = {
                int(n.split("@", 1)[1].split(":", 1)[0])
                for n in res.notes
                if "force_cover_remaining kostu" in n
            }
            assert not (skipped & fired), "ayni bilesen hem atlandi hem kostu"
            for root, c, leftover in main_loop_exit_state(g, algo):
                if not leftover:
                    assert root not in skipped and root not in fired
                    continue
                feas = central._bmatching(c.edges, c.cover, c.k)[0]
                if root in skipped:
                    assert feas, "fallback atlandi ama ortu akisa gore uygun degil"
                    checked += 1
                else:
                    assert root in fired
                    assert not feas, "akis uygun dedigi halde fallback kostu"
    assert checked > 0, "hicbir atlama gozlenmedi, test bos kosuyor"


def test_eager_policy_still_fires_the_fallback():
    """Sadık siyaset hâlâ ölçülebilir sıklıkta fallback'e düşüyor (denetim izi)."""
    fired = 0
    total = 0
    for k in (2, 3, 4, 6):
        for g in load_real_graphs(k, "unit"):
            if not instance_is_feasible(g):
                continue
            total += 1
            res = central.solve("gccvc", g, fallback_policy="eager")
            if any("force_cover_remaining kostu" in n for n in res.notes):
                fired += 1
    assert total > 0
    assert fired / total > 0.2, f"fallback orani beklenenden dusuk: {fired}/{total}"


@pytest.mark.parametrize("algo", GREEDY)
def test_phase_accounting_is_complete(algo):
    """Evre muhasebesi tam: ağırlıklar ve sayımlar toplamı sonuca eşit."""
    for g in load_real_graphs(4, "random")[:30]:
        if not instance_is_feasible(g):
            continue
        r = central.solve(algo, g)
        assert set(r.phase) == r.cover
        assert set(r.phase.values()) <= {"greedy", "fallback", "bridge", "escalate"}
        assert sum(r.weight_by_phase.values()) == pytest.approx(r.total_weight)
        assert sum(r.count_by_phase.values()) == r.cover_size


def test_unknown_fallback_policy_is_rejected():
    g = random_graph(10, 0.3, 3, "unit", 2)
    with pytest.raises(ValueError):
        central.solve("gccvc", g, fallback_policy="hizli")


def test_exact_stays_optimal_under_both_policies():
    """Tam çözüm siyasetten bağımsız: greedy yalnız üst sınır tohumu."""
    for seed in range(15):
        g = random_graph(9, 0.35, 2, "random", 9100 + seed)
        if not instance_is_feasible(g):
            continue
        ex = central.solve_exact(g, max_n=18, time_limit_s=30.0)
        for algo in GREEDY:
            for pol in central.FALLBACK_POLICIES:
                assert (
                    central.solve(algo, g, fallback_policy=pol).total_weight
                    >= ex.total_weight - 1e-9
                )


# ==========================================================================
# 11. bağlılık onarımının bedeli (asıl maliyet kalemi)
# ==========================================================================
@pytest.mark.parametrize("algo", GREEDY)
def test_bridge_nodes_never_cover_a_new_edge(algo):
    """YAPISAL İDDİA. Köprü düğümleri yalnız bağlılık için orada.

    Onarım başladığında örtü ZATEN tepe örtüsüdür, ve köprü düğümü o sırada
    örtüde değildir. Dolayısıyla köprü düğümü v çıkarılınca geriye kalan küme
    hâlâ tepe örtüsüdür: hiçbir kenarın tek örtü-ucu v olamaz. D-CDS'in
    "bağlılığı onarımla değil inşa ile al" savının ölçülebilir dayanağı budur.
    """
    seen = 0
    for k in (2, 3, 4, 6):
        for g in load_real_graphs(k, "random")[:30]:
            if not instance_is_feasible(g):
                continue
            r = central.solve(algo, g)
            for v, ph in r.phase.items():
                if ph != "bridge":
                    continue
                seen += 1
                assert bridge.is_vertex_cover(g, r.cover - {v}), (
                    f"kopru dugumu {v} bir kenarin TEK ortu-ucu: yapisal iddia coktu"
                )
    assert seen > 0, "hic kopru dugumu gorulmedi, test bos kosuyor"


@pytest.mark.parametrize("algo", GREEDY)
def test_repair_adds_nodes_only_when_cover_is_split(algo):
    """Onarım gereksiz yere düğüm eklemiyor: köprü evresi ⟹ örtü gerçekten kopuktu."""
    for k in (2, 4):
        for g in load_real_graphs(k, "unit")[:35]:
            if not instance_is_feasible(g):
                continue
            for policy in central.FALLBACK_POLICIES:
                r = central.solve(algo, g, fallback_policy=policy)
                if not any(ph == "bridge" for ph in r.phase.values()):
                    continue
                split = any(
                    len(c.cover_components()) > 1
                    for _root, c, _left in main_loop_exit_state_after_fallback(
                        g, algo, policy
                    )
                )
                assert split, f"[{policy}] ortu bagliyken kopru dugumu eklendi"


def main_loop_exit_state_after_fallback(g: CcvcGraph, algo: str, policy: str = "eager"):
    """Ana döngü + (siyasete göre) fallback sonrası, ONARIMDAN ÖNCEKİ durum.

    `policy` çözücünün kullandığıyla AYNI olmalı, yoksa yeniden kurulan durum
    çözücünün gerçek durumundan sapar ve karşılaştırma anlamsızlaşır.
    """
    _lbl, picker, sorter = central._RULES[algo]
    out = []
    for comp in central._components(g):
        sub = central._subgraph(g, comp)
        c = central._Component(sub)
        if not c.edges:
            continue
        while c.has_uncovered():
            c.mark_red_nodes(False)
            v = picker(c, False)
            if v is None:
                break
            c.select_node(v, sorter, False)
        if c.has_uncovered():
            if not (policy == "flow" and central._bmatching(c.edges, c.cover, c.k)[0]):
                c.force_cover_remaining(picker, sorter)
        out.append((comp[0], c, [e for e in c.edges if e not in c.covered]))
    return out


def phase_shares(algo: str, k: int, scheme: str = "unit", policy: str = "eager"):
    """Kampüs karelerinde evre bazlı ağırlık payı ve fallback tetiklenme oranı.

    Varsayılan olarak YAYIMLANMIŞ siyaseti ("eager") ölçer: bu fonksiyonun
    müşterisi olan testler yayımlanmış algoritmayı karakterize ediyor, çözücünün
    güncel varsayılanını değil.
    """
    w = {}
    fired = total = 0
    for g in load_real_graphs(k, scheme):
        if not instance_is_feasible(g):
            continue
        r = central.solve(algo, g, fallback_policy=policy)
        total += 1
        if any("force_cover_remaining kostu" in n for n in r.notes):
            fired += 1
        for ph, val in r.weight_by_phase.items():
            w[ph] = w.get(ph, 0.0) + val
    tot = sum(w.values())
    return {p: v / tot for p, v in w.items()}, (fired / total if total else 0.0), total


@pytest.mark.parametrize("algo", GREEDY)
def test_fallback_cost_and_trigger_rate_are_decoupled(algo):
    """ÖLÇÜM BULGUSU. Yüksek k'da fallback hâlâ ateşleniyor ama HİÇ ağırlık eklemiyor.

    force_cover_remaining'in ilk adımı (algorithms.py 607-610) yalnız mevcut
    örtü düğümlerinin artan kapasitesini kullanıyor, düğüm eklemiyor. k büyükse
    açık kenarlar orada kapanıyor. Yani tetiklenme oranı maliyetin vekili DEĞİL;
    tabanın oranını fallback açıklamıyor.
    """
    shares, rate, n = phase_shares(algo, 6)
    assert n > 20
    assert rate > 0.05, f"k=6'da fallback hic atesleme yok ({rate:.2f}), test bos"
    assert shares.get("fallback", 0.0) < 0.01, (
        f"k=6'da fallback agirligi beklenenden yuksek: {shares.get('fallback', 0.0):.3f}"
    )


@pytest.mark.parametrize("algo", GREEDY)
def test_bridging_is_the_dominant_non_greedy_cost(algo):
    """Köprüleme her kapasitede fallback'ten pahalı ve k'dan bağımsız.

    Bu, tabanın exact'e oranının kapasiteyle neden düz kaldığını açıklıyor:
    baskın maliyet kalemi kapasiteye duyarsız.
    """
    for k in (3, 4, 6):
        shares, _rate, n = phase_shares(algo, k)
        assert n > 20
        assert shares.get("bridge", 0.0) > shares.get("fallback", 0.0), (
            f"k={k}: kopruleme fallback'ten ucuz cikti, bulgu degismis"
        )
        assert 0.05 < shares["bridge"] < 0.25, f"k={k} kopru payi: {shares['bridge']:.3f}"


@pytest.mark.parametrize("algo", GREEDY)
def test_k2_is_the_documented_exception(algo):
    """DÜRÜST İSTİSNA: en sıkı kapasitede (k=2) fallback köprülemeyle yarışıyor.

    k=2 uygunsuzluk sınırına yakın; fallback hem sık ateşleniyor hem gerçekten
    düğüm ekliyor, kapasite yükseltmesi de burada devreye giriyor. "Köprüleme
    baskın maliyet" savı k>=3 icindir, k=2 icin degildir. Bu test o sinirin
    nerede oldugunu kayda geciriyor.
    """
    shares, rate, n = phase_shares(algo, 2)
    assert n > 20
    assert rate > 0.5, f"k=2'de fallback orani beklenenden dusuk: {rate:.2f}"
    assert shares.get("fallback", 0.0) > 0.02, "k=2'de fallback bedava cikti"
    assert shares.get("escalate", 0.0) > 0.0, "k=2'de kapasite yukseltmesi hic kosmadi"


# ==========================================================================
# 12. seçim kalitesi: onarım öncesi ara kümeler
# ==========================================================================
@pytest.mark.parametrize("policy", central.FALLBACK_POLICIES)
@pytest.mark.parametrize("algo", GREEDY)
def test_pre_repair_subsets_are_valid_vertex_covers(algo, policy):
    """ÖLÇÜM TEMELİ. "Onarım öncesi oran" ancak ara küme tepe örtüsüyse anlamlı.

    Hem yalnız-greedy kümesi hem greedy+fallback kümesi tepe örtüsü olmalı.
    Birincisi Lemma 1'in doğrudan sonucu, ikincisi ona düğüm eklediği için.
    Bu doğrulanmadan R_greedy ve R_core sayıları yorumlanamaz.
    """
    checked = 0
    for k in (2, 3, 4, 6):
        for g in load_real_graphs(k, "random")[:25]:
            if not instance_is_feasible(g):
                continue
            r = central.solve(algo, g, fallback_policy=policy)
            greedy_only = {v for v, ph in r.phase.items() if ph == "greedy"}
            core = {v for v, ph in r.phase.items() if ph in ("greedy", "fallback")}
            assert bridge.is_vertex_cover(g, greedy_only), "yalniz-greedy kumesi tepe ortusu degil"
            assert bridge.is_vertex_cover(g, core), "greedy+fallback kumesi tepe ortusu degil"
            assert greedy_only <= core <= r.cover
            checked += 1
    assert checked > 20


@pytest.mark.parametrize("algo", GREEDY)
def test_selection_error_exists_and_grows_with_capacity(algo):
    """ÖLÇÜM BULGUSU. Seçim hatası k ile BÜYÜR, onarım bedeli k ile KÜÇÜLÜR.

    İkisi ters yönde hareket ettiği için toplam fazlalık kapasiteye görece düz
    kalıyor. Tabanın exact'e oranının neden düz olduğunun mekanizması budur;
    tek bir kalemin düz olması değil, iki kalemin birbirini götürmesi.
    """
    sel = {}
    for k in (2, 6):
        num = den = 0.0
        for g in load_real_graphs(k, "unit"):
            if not instance_is_feasible(g):
                continue
            ex = central.solve_exact(g, max_n=18, time_limit_s=5.0)
            if ex.timed_out or ex.total_weight <= 0:
                continue
            r = central.solve(algo, g, fallback_policy="eager")
            greedy_only = {v for v, ph in r.phase.items() if ph == "greedy"}
            num += g.total_weight(greedy_only) / ex.total_weight
            den += 1
        sel[k] = num / den - 1.0
    assert sel[2] >= 0.0 and sel[6] > 0.0
    assert sel[6] > sel[2], f"secim hatasi k ile buyumedi: k2={sel[2]:.3f} k6={sel[6]:.3f}"
