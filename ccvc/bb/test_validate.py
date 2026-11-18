#!/usr/bin/env python3
"""ccvc/bb/validate.py testleri (brief §9).

Koşum (depo kökünden):
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_validate.py -q

Birim çizgelerin beklenen C, owner ve ihlalleri ELLE yazılmıştır; hiçbiri
doğrulayıcının kendi çıktısından üretilmemiştir.
"""
from __future__ import annotations

import itertools
import math
import os
import random
import sys
from typing import Dict, List, Sequence, Set, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc import bridge  # noqa: E402
from ccvc.bridge import CcvcGraph, Edge, edge_key  # noqa: E402
from ccvc.bb import validate as V  # noqa: E402
from ccvc.bb.api import ValidationReport, Violation  # noqa: E402


# ==========================================================================
# elle yazılmış birim çizgeler
# ==========================================================================
def _g(edges, k, weight=None, nodes=None) -> CcvcGraph:
    return V.make_graph(edges, k, weight, nodes)


SINGLE_EDGE = [(1, 2)]
PATH5 = [(1, 2), (2, 3), (3, 4), (4, 5)]
STAR5 = [(1, 2), (1, 3), (1, 4), (1, 5)]
K4 = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
BOWTIE = [(1, 2), (1, 3), (2, 3), (3, 4), (4, 5), (4, 6), (5, 6)]  # köprülü iki üçgen

# 4x4 ızgara, id = 4*satır + sütun + 1
GRID4 = [
    (1, 2), (2, 3), (3, 4),
    (5, 6), (6, 7), (7, 8),
    (9, 10), (10, 11), (11, 12),
    (13, 14), (14, 15), (15, 16),
    (1, 5), (2, 6), (3, 7), (4, 8),
    (5, 9), (6, 10), (7, 11), (8, 12),
    (9, 13), (10, 14), (11, 15), (12, 16),
]


def test_single_edge():
    """Tek kenar: C={1}, owner {(1,2):1}. G[C] tek düğüm, bağlı sayılır."""
    g = _g(SINGLE_EDGE, k=1)
    r = V.validate(g, [1], {(1, 2): 1})
    assert r.valid, r.violations
    assert r.vertex_cover and r.connected and r.capacity
    assert r.violations == []
    assert r.load == {1: 1}
    assert r.forced == {1: 1}       # komşu 2 C dışında, kenar zorunlu
    assert V.lower_bound_g6(g) == 1


def test_single_edge_empty_cover_is_uncovered():
    g = _g(SINGLE_EDGE, k=1)
    r = V.validate(g, [], {})
    assert not r.valid
    kinds = [v.kind for v in r.violations]
    assert kinds.count(V.UNCOVERED_EDGE) == 1
    # sahipsizlik de ayrıca yakalanır
    assert any(v.kind == V.BAD_OWNER and v.edges == ((1, 2),) for v in r.violations)
    unc = r.by_kind(V.UNCOVERED_EDGE)[0]
    assert unc.edges == ((1, 2),) and unc.nodes == (1, 2)


def test_path_p5():
    """Yol 1-2-3-4-5: C={2,3,4}, zorunlu (1,2)->2 ve (4,5)->4, ortadakiler 3'e."""
    g = _g(PATH5, k=2)
    cover = [2, 3, 4]
    owner = {(1, 2): 2, (2, 3): 3, (3, 4): 3, (4, 5): 4}
    r = V.validate(g, cover, owner)
    assert r.valid, r.violations
    assert r.load == {2: 1, 3: 2, 4: 1}
    assert r.forced == {2: 1, 3: 0, 4: 1}
    assert V.lower_bound_g6(g) == 2 and len(cover) >= 2


def test_path_p5_k1_forced_overload():
    """k=1'de aynı C çözümsüz: 3'ün iki esnek kenarı var, ama asıl kanıt akış."""
    g = _g(PATH5, k=1)
    r = V.validate(g, [2, 3, 4])           # owner yok -> akış yedeği
    assert not r.capacity
    assert r.owner_source == "flow"
    assert r.by_kind(V.CAPACITY_INFEASIBLE)


def test_star():
    """Yıldız: C={1} tek başına örtü, bağlı ve k=4 ile uygun."""
    g = _g(STAR5, k=4)
    owner = {(1, 2): 1, (1, 3): 1, (1, 4): 1, (1, 5): 1}
    r = V.validate(g, [1], owner)
    assert r.valid, r.violations
    assert r.load == {1: 4} and r.forced == {1: 4}
    # k=3 olsaydı G4 zorunlu yük ihlali verirdi
    g3 = _g(STAR5, k=3)
    r3 = V.validate(g3, [1], owner)
    assert not r3.valid
    fo = r3.by_kind(V.FORCED_OVERLOAD)
    assert len(fo) == 1 and fo[0].nodes == (1,) and fo[0].excess == 1


def test_complete_k4():
    """K4: C={1,2,3}, 4 dışarıda. Zorunlu (1,4),(2,4),(3,4); esnek üçgen paylaşılır."""
    g = _g(K4, k=2)
    cover = [1, 2, 3]
    owner = {(1, 4): 1, (2, 4): 2, (3, 4): 3, (1, 2): 1, (2, 3): 2, (1, 3): 3}
    r = V.validate(g, cover, owner)
    assert r.valid, r.violations
    assert r.load == {1: 2, 2: 2, 3: 2}
    assert r.forced == {1: 1, 2: 1, 3: 1}
    assert V.lower_bound_g6(g) == 3 == len(cover)   # ⌈6/2⌉ = 3, sınıra oturuyor


def test_complete_k4_two_node_cover_is_not_a_cover():
    """K4'te iki düğümlük C örtü değildir: (3,4) açıkta kalır."""
    g = _g(K4, k=3)
    r = V.validate(g, [1, 2])
    assert not r.vertex_cover
    unc = r.by_kind(V.UNCOVERED_EDGE)
    assert len(unc) == 1 and unc[0].edges == ((3, 4),)


def test_bowtie_two_triangles_bridge():
    """Köprülü iki üçgen: C={2,3,4,5}, elle atanmış owner."""
    g = _g(BOWTIE, k=2)
    cover = [2, 3, 4, 5]
    owner = {
        (1, 2): 2, (1, 3): 3,          # zorunlu (1 dışarıda)
        (4, 6): 4, (5, 6): 5,          # zorunlu (6 dışarıda)
        (2, 3): 2, (3, 4): 3, (4, 5): 5,
    }
    r = V.validate(g, cover, owner)
    assert r.valid, r.violations
    assert r.load == {2: 2, 3: 2, 4: 1, 5: 2}
    assert r.forced == {2: 1, 3: 1, 4: 1, 5: 1}
    assert V.lower_bound_g6(g) == 4 == len(cover)   # ⌈7/2⌉ = 4


def test_bowtie_bridge_endpoint_dropped_breaks_connectivity():
    """C'den 3 çıkarılırsa hem (1,3) açıkta kalır hem G[C] ikiye bölünür."""
    g = _g(BOWTIE, k=3)
    r = V.validate(g, [2, 4, 5])
    assert not r.valid
    assert r.by_kind(V.UNCOVERED_EDGE)[0].edges == ((1, 3),)
    disc = r.by_kind(V.DISCONNECTED)
    assert len(disc) == 2
    assert sorted(v.nodes for v in disc) == [(2,), (4, 5)]


GRID_COVER = [2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15]   # dört köşe (1,4,13,16) dışarıda
GRID_OWNER = {
    # yatay
    (1, 2): 2, (2, 3): 2, (3, 4): 3,
    (5, 6): 5, (6, 7): 6, (7, 8): 7,
    (9, 10): 9, (10, 11): 10, (11, 12): 11,
    (13, 14): 14, (14, 15): 14, (15, 16): 15,
    # dikey
    (1, 5): 5, (2, 6): 2, (3, 7): 3, (4, 8): 8,
    (5, 9): 5, (6, 10): 6, (7, 11): 7, (8, 12): 8,
    (9, 13): 9, (10, 14): 10, (11, 15): 11, (12, 16): 12,
}


def test_grid_4x4():
    """4x4 ızgara: köşeler bağımsız küme, C = geri kalan 12 düğüm.

    owner kuralı elle uygulanmıştır: kenarın sahibi küçük uçtur, küçük uç
    C dışındaysa büyük uçtur. En büyük yük 3, dolayısıyla k=3.
    """
    g = _g(GRID4, k=3)
    r = V.validate(g, GRID_COVER, GRID_OWNER)
    assert r.valid, r.violations
    assert len(g.edges) == 24
    assert r.load == {
        2: 3, 3: 2, 5: 3, 6: 2, 7: 2, 8: 2,
        9: 2, 10: 2, 11: 2, 12: 1, 14: 2, 15: 1,
    }
    assert sum(r.load.values()) == 24
    # her köşe iki zorunlu kenar doğurur
    assert r.forced == {
        2: 1, 3: 1, 5: 1, 6: 0, 7: 0, 8: 1,
        9: 1, 10: 0, 11: 0, 12: 1, 14: 1, 15: 1,
    }
    assert V.lower_bound_g6(g) == 8 and len(GRID_COVER) == 12


def test_grid_4x4_k2_is_overloaded():
    """Aynı owner k=2 ile taşkın verir: 2 ve 5 düğümleri birer kenar fazla taşır."""
    g = _g(GRID4, k=2)
    r = V.validate(g, GRID_COVER, GRID_OWNER)
    assert not r.valid
    over = {v.nodes[0]: v.excess for v in r.by_kind(V.OVERLOAD)}
    assert over == {2: 1, 5: 1}


# ==========================================================================
# bozuk sahiplik girdileri
# ==========================================================================
def test_double_assigned_edge_is_caught():
    """Aynı kenar iki kez atanmış: (u,v) ve (v,u) anahtarları ya da çift listesi."""
    g = _g(PATH5, k=2)
    pairs = [((1, 2), 2), ((2, 1), 1), ((2, 3), 3), ((3, 4), 3), ((4, 5), 4)]
    r = V.validate(g, [2, 3, 4], pairs)
    assert not r.valid
    dup = [v for v in r.by_kind(V.BAD_OWNER) if "kez atandı" in v.detail]
    assert len(dup) == 1
    assert dup[0].edges == ((1, 2),)
    assert set(dup[0].nodes) == {1, 2}


def test_owner_not_an_endpoint_is_caught():
    g = _g(PATH5, k=2)
    owner = {(1, 2): 3, (2, 3): 3, (3, 4): 3, (4, 5): 4}   # (1,2) sahibi 3, ucu değil
    r = V.validate(g, [2, 3, 4], owner)
    assert not r.valid
    bad = [v for v in r.by_kind(V.BAD_OWNER) if "ucu değil" in v.detail]
    assert len(bad) == 1 and bad[0].nodes == (3,) and bad[0].edges == ((1, 2),)


def test_owner_outside_cover_is_caught():
    g = _g(PATH5, k=2)
    owner = {(1, 2): 1, (2, 3): 3, (3, 4): 3, (4, 5): 4}   # 1 ∉ C
    r = V.validate(g, [2, 3, 4], owner)
    assert not r.valid
    bad = [v for v in r.by_kind(V.BAD_OWNER) if "C'de değil" in v.detail]
    assert len(bad) == 1 and bad[0].nodes == (1,) and bad[0].edges == ((1, 2),)


def test_missing_owner_entry_is_caught():
    g = _g(PATH5, k=2)
    owner = {(1, 2): 2, (2, 3): 3, (4, 5): 4}              # (3,4) yok
    r = V.validate(g, [2, 3, 4], owner)
    assert not r.valid
    miss = [v for v in r.by_kind(V.BAD_OWNER) if "sahipsiz" in v.detail]
    assert len(miss) == 1 and miss[0].edges == ((3, 4),)


def test_unknown_edge_in_owner_is_caught():
    g = _g(PATH5, k=2)
    owner = {(1, 2): 2, (2, 3): 3, (3, 4): 3, (4, 5): 4, (2, 5): 2}
    r = V.validate(g, [2, 3, 4], owner)
    assert not r.valid
    unk = [v for v in r.by_kind(V.BAD_OWNER) if "çizgede olmayan" in v.detail]
    assert len(unk) == 1 and unk[0].edges == ((2, 5),)


def test_overload_reports_correct_excess():
    """Yıldızda bütün kenarları 1 sahiplenir, k=2 -> yük 4, aşım 2."""
    g = _g(STAR5, k=2)
    owner = {(1, 2): 1, (1, 3): 1, (1, 4): 1, (1, 5): 1}
    r = V.validate(g, [1], owner)
    assert not r.valid
    over = r.by_kind(V.OVERLOAD)
    assert len(over) == 1
    v = over[0]
    assert v.nodes == (1,) and v.load == 4 and v.capacity == 2 and v.excess == 2
    assert set(v.edges) == {(1, 2), (1, 3), (1, 4), (1, 5)}
    assert isinstance(v, V.LoadViolation) and isinstance(v, Violation)


def test_cover_node_outside_graph():
    g = _g(PATH5, k=2)
    r = V.validate(g, [2, 3, 4, 99], {(1, 2): 2, (2, 3): 3, (3, 4): 3, (4, 5): 4})
    assert not r.valid
    bc = r.by_kind(V.BAD_COVER)
    assert len(bc) == 1 and bc[0].nodes == (99,)


# ==========================================================================
# bağlılık: strict (brief §1) vs per_component (bridge.py)
# ==========================================================================
DISJOINT = [(1, 2), (3, 4)]      # iki ayrı kenar: çizgenin kendisi kopuk


def test_disconnected_cover_named_components():
    """Bağlı çizgede kopuk örtü: her parça ayrı ihlal olarak adıyla gelir."""
    g = _g(PATH5, k=2)
    r = V.validate(g, [2, 4], {(1, 2): 2, (2, 3): 2, (3, 4): 4, (4, 5): 4})
    assert r.vertex_cover and not r.connected
    disc = r.by_kind(V.DISCONNECTED)
    assert len(disc) == 2
    assert sorted(v.nodes for v in disc) == [(2,), (4,)]
    assert all("2 parça" in v.detail for v in disc)


def test_strict_mode_flags_disconnected_input_graph():
    """Girdi çizgesi kopuksa strict kip bunu AYRI türle söyler, sessizce geçmez."""
    g = _g(DISJOINT, k=1)
    r = V.validate(g, [1, 3], {(1, 2): 1, (3, 4): 3})
    assert r.vertex_cover and r.capacity
    gd = r.by_kind(V.GRAPH_DISCONNECTED)
    assert len(gd) == 1 and "girdi hatası" in gd[0].detail
    assert not r.valid                      # ihlal listesi boş değil


def test_per_component_mode_accepts_disconnected_input_graph():
    """Aynı örnek bileşen bazlı kipte geçerlidir; bridge.is_connected_cover ile aynı yargı."""
    g = _g(DISJOINT, k=1)
    r = V.validate(g, [1, 3], {(1, 2): 1, (3, 4): 3}, connectivity=V.PER_COMPONENT)
    assert r.valid, r.violations
    assert r.connected is bridge.is_connected_cover(g, {1, 3})
    assert r.connectivity_mode == V.PER_COMPONENT


def test_per_component_still_catches_split_inside_one_component():
    g = _g(PATH5 + [(7, 8)], k=2)          # P5 + ayrı bir kenar
    r = V.validate(g, [2, 4, 7], connectivity=V.PER_COMPONENT)
    disc = r.by_kind(V.DISCONNECTED)
    assert sorted(v.nodes for v in disc) == [(2,), (4,)]     # 7 tek başına, sorun değil


def test_isolated_node_is_an_input_problem_in_strict_mode():
    g = _g(SINGLE_EDGE, k=1, nodes=[1, 2, 3])
    r = V.validate(g, [1], {(1, 2): 1})
    gd = r.by_kind(V.GRAPH_DISCONNECTED)
    assert len(gd) == 1 and "yalıtık" in gd[0].detail
    r2 = V.validate(g, [1], {(1, 2): 1}, connectivity=V.PER_COMPONENT)
    assert r2.valid, r2.violations


def test_unknown_connectivity_mode_raises():
    g = _g(PATH5, k=2)
    with pytest.raises(ValueError):
        V.validate(g, [2, 3, 4], None, connectivity="bileşen")


# ==========================================================================
# brief §2 yapısal olguları
# ==========================================================================
def test_g1_connected_vertex_cover_is_connected_dominating_set():
    """G1: izole düğüm yoksa bağlı tepe örtüsü baskındır. Altı çizgede de assert."""
    cases = [
        (SINGLE_EDGE, 1, [1]),
        (PATH5, 2, [2, 3, 4]),
        (STAR5, 4, [1]),
        (K4, 2, [1, 2, 3]),
        (BOWTIE, 2, [2, 3, 4, 5]),
        (GRID4, 3, GRID_COVER),
    ]
    for edges, k, cover in cases:
        g = _g(edges, k)
        assert not V.isolated_nodes(g)
        assert not bridge.uncovered_edges(g, set(cover))
        assert len(V.cover_components(g, cover)) == 1
        assert V.is_dominating_set(g, cover)
        assert V.check_g1(g, cover) == []


def test_g2_uncovered_edges_are_exactly_both_endpoints_outside():
    """G2: CDS B verildiğinde açıktaki kenarlar tam olarak iki ucu B dışında olanlardır."""
    g = _g(GRID4, k=3)
    backbone = [2, 3, 6, 7, 10, 11, 14, 15]       # ızgaranın orta iki sütunu
    assert V.is_dominating_set(g, backbone)
    assert len(V.cover_components(g, backbone)) == 1
    expected = {e for e in g.edges if e[0] not in set(backbone) and e[1] not in set(backbone)}
    assert set(bridge.uncovered_edges(g, set(backbone))) == expected
    # elle: açıkta kalanlar yalnız dış iki sütunun dikey kenarlarıdır
    assert expected == {(1, 5), (5, 9), (9, 13), (4, 8), (8, 12), (12, 16)}
    assert V.check_g2(g, backbone) == []


def test_g4_forced_load_definition_and_violation():
    """G4: F(v) komşularının C dışında olanlarının sayısıdır, F(v)>k geçersizdir."""
    g = _g(STAR5, k=2)
    assert V.forced_load(g, [1], 1) == 4
    assert V.forced_edges(g, [1], 1) == ((1, 2), (1, 3), (1, 4), (1, 5))
    vs = V.check_g4(g, [1])
    assert len(vs) == 1 and vs[0].kind == V.FORCED_OVERLOAD and vs[0].excess == 2
    # yıldızın tamamı C ise zorunlu yük sıfırdır
    g2 = _g(STAR5, k=2)
    assert V.check_g4(g2, [1, 2, 3, 4, 5]) == []
    assert all(V.forced_load(g2, [1, 2, 3, 4, 5], v) == 0 for v in g2.nodes)


def test_g6_lower_bound_check():
    g = _g(K4, k=2)
    assert V.lower_bound_g6(g) == 3
    assert V.check_g6(g, [1, 2, 3]) == []
    vs = V.check_g6(g, [1, 2])
    assert len(vs) == 1 and vs[0].kind == V.LOWER_BOUND


@pytest.mark.parametrize("seed", range(40))
def test_g6_holds_on_random_graphs(seed):
    """G6 rastgele çizgelerde: geçerli her çözümde |C| ≥ ⌈|E|/k⌉."""
    rnd = random.Random(1000 + seed)
    n = rnd.randint(4, 12)
    p = rnd.uniform(0.25, 0.7)
    edges = [(u, v) for u in range(n) for v in range(u + 1, n) if rnd.random() < p]
    if not edges:
        pytest.skip("kenarsız örnek")
    k = rnd.randint(1, 4)
    g = V.make_graph(edges, k)
    cover = set(g.nodes)                      # her şey C'de: en gevşek örtü
    lb = V.lower_bound_g6(g)
    r = V.validate(g, cover, connectivity=V.PER_COMPONENT)
    if r.capacity:
        assert len(cover) >= lb
        assert r.by_kind(V.LOWER_BOUND) == []
    # sınırın kendisi tanımla tutarlı
    assert lb == math.ceil(len(g.edges) / k)


# ==========================================================================
# akış yedeği ile açık owner'ın uyuşması
# ==========================================================================
def _random_instance(rnd) -> Tuple[CcvcGraph, Set[int]]:
    """Rastgele çizge + rastgele bağımsız kümenin tümleyeni olan bir örtü."""
    n = rnd.randint(3, 9)
    p = rnd.uniform(0.2, 0.8)
    edges = [(u, v) for u in range(n) for v in range(u + 1, n) if rnd.random() < p]
    k = rnd.randint(1, 3)
    g = V.make_graph(edges, k, nodes=list(range(n)))
    # bağımsız küme kur, tümleyeni tepe örtüsüdür
    indep: Set[int] = set()
    for v in rnd.sample(g.nodes, len(g.nodes)):
        if rnd.random() < 0.45 and all(u not in indep for u in g.adj[v]):
            indep.add(v)
    return g, set(g.nodes) - indep


def _brute_force_owner(g: CcvcGraph, cover: Set[int]):
    """Küçük örnekte bütün atamaları dener; uygun bir owner varsa döndürür."""
    edges = list(g.edges)
    for choice in itertools.product(*[[u, v] for u, v in edges]):
        load: Dict[int, int] = {}
        ok = True
        for o in choice:
            if o not in cover:
                ok = False
                break
            load[o] = load.get(o, 0) + 1
            if load[o] > g.capacity_k:
                ok = False
                break
        if ok:
            return {e: o for e, o in zip(edges, choice)}
    return None


def test_flow_fallback_agrees_with_explicit_owner_200_instances():
    """En az 200 rastgele örnek; akış yedeği ile açık owner denetimi sıfır uyuşmazlık.

    İki yön de sınanır: akış "uygun" derse verdiği tanık açık owner olarak
    denetimden geçmeli; akış "uygun değil" derse kaba kuvvetle de atama
    bulunamamalı.
    """
    rnd = random.Random(20260915)
    checked = feasible_cases = infeasible_cases = 0
    while checked < 220:
        g, cover = _random_instance(rnd)
        if bridge.uncovered_edges(g, cover) or not g.edges:
            continue
        checked += 1
        flow = V.validate(g, cover, connectivity=V.PER_COMPONENT)
        assert flow.owner_source == "flow" and not flow.owner_supplied
        brute = _brute_force_owner(g, cover) if len(g.edges) <= 12 else None

        if flow.capacity:
            feasible_cases += 1
            explicit = V.validate(
                g, cover, flow.resolved_owner, connectivity=V.PER_COMPONENT
            )
            assert explicit.capacity, (g.edges, cover, g.capacity_k)
            assert explicit.owner_source == "explicit"
            assert not explicit.by_kind(V.BAD_OWNER)
            assert not explicit.by_kind(V.OVERLOAD)
            assert len(explicit.resolved_owner) == len(g.edges)
            assert explicit.valid == flow.valid
        else:
            infeasible_cases += 1
            assert flow.by_kind(V.CAPACITY_INFEASIBLE) or flow.by_kind(V.FORCED_OVERLOAD)
            if len(g.edges) <= 12:
                assert brute is None, (g.edges, cover, g.capacity_k, brute)

        if brute is not None:
            assert flow.capacity, (g.edges, cover, g.capacity_k)

    assert checked >= 200
    assert feasible_cases > 0 and infeasible_cases > 0


def test_flow_fallback_notes_that_owner_was_not_verified():
    g = _g(PATH5, k=2)
    r = V.validate(g, [2, 3, 4])
    assert r.valid, r.violations
    assert r.owner_source == "flow" and not r.owner_supplied
    assert any("VARLIK" in n for n in r.notes)
    assert len(r.resolved_owner) == len(g.edges)


# ==========================================================================
# yerel–küresel tutarlılık (brief §9)
# ==========================================================================
def test_local_global_consistent_on_valid_solution():
    g = _g(BOWTIE, k=2)
    cover = [2, 3, 4, 5]
    owner = {
        (1, 2): 2, (1, 3): 3, (4, 6): 4, (5, 6): 5,
        (2, 3): 2, (3, 4): 3, (4, 5): 5,
    }
    views = V.views_from_solution(g, cover, owner)
    report, local = V.check_local_global(g, views)
    assert report.valid, report.violations
    assert all(v == [] for v in local.values())
    assert not report.by_kind(V.LOCAL_GLOBAL)


def test_local_check_catches_node_that_lies_about_forced_load():
    g = _g(BOWTIE, k=2)
    cover = [2, 3, 4, 5]
    owner = {
        (1, 2): 2, (1, 3): 3, (4, 6): 4, (5, 6): 5,
        (2, 3): 2, (3, 4): 3, (4, 5): 5,
    }
    views = V.views_from_solution(g, cover, owner)
    views[4] = V.LocalView(nid=4, in_cover=True, owned=views[4].owned, forced_load=0)
    report, local = V.check_local_global(g, views)
    assert local[4] and any("F iddiası" in v.detail for v in local[4])
    assert all(local[n] == [] for n in local if n != 4)
    # küresel taraf hâlâ geçerli: bu yalnız düğümün muhasebe hatası
    assert report.valid, report.violations


def test_local_check_catches_uncovered_edge_at_both_endpoints():
    """İki komşu birden C dışındaysa ikisinin de yerel denetimi düşer."""
    g = _g(PATH5, k=2)
    cover = [2, 4]
    owner = {(1, 2): 2, (2, 3): 2, (3, 4): 4, (4, 5): 4}
    views = V.views_from_solution(g, cover, owner)
    views[3] = V.LocalView(nid=3, in_cover=False, owned=(), forced_load=0)
    report, local = V.check_local_global(g, views)
    # (2,3) ve (3,4) 2 ve 4'te kalıyor; asıl sorun bağlılık, kenarlar örtülü
    assert report.by_kind(V.DISCONNECTED)
    assert local[3] == []
    # 3'ün komşularından biri de C dışına çıkarsa kenar gerçekten açıkta kalır
    views[3] = V.LocalView(nid=3, in_cover=False)
    views[4] = V.LocalView(nid=4, in_cover=False)
    views[2] = V.LocalView(nid=2, in_cover=True, owned=((1, 2), (2, 3)), forced_load=2)
    report2, local2 = V.check_local_global(g, views)
    assert any(v.kind == V.UNCOVERED_EDGE for v in local2[3])
    assert any(v.kind == V.UNCOVERED_EDGE for v in local2[4])
    assert report2.by_kind(V.UNCOVERED_EDGE)


def test_local_check_catches_double_owned_and_unowned_edges():
    g = _g(PATH5, k=2)
    cover = [2, 3, 4]
    owner = {(1, 2): 2, (2, 3): 3, (3, 4): 3, (4, 5): 4}
    views = V.views_from_solution(g, cover, owner)
    views[2] = V.LocalView(nid=2, in_cover=True, owned=((1, 2), (2, 3)), forced_load=1)
    report, local = V.check_local_global(g, views)
    assert any("hem 2 hem 3" in v.detail for v in local[2])
    assert any("hem 3 hem 2" in v.detail for v in local[3])
    assert report.by_kind(V.BAD_OWNER)          # küresel de çifte atamayı görür

    views[2] = V.LocalView(nid=2, in_cover=True, owned=((1, 2),), forced_load=1)
    views[3] = V.LocalView(nid=3, in_cover=True, owned=((3, 4),), forced_load=0)
    report2, local2 = V.check_local_global(g, views)
    assert any("ne 2 ne 3" in v.detail for v in local2[2])


def test_local_global_mismatch_is_reported_with_node_names():
    """Sav: yerel hepsi temiz + G[C] bağlı ise küresel de geçmeli.

    Savı bilerek çürüten bir kurgu: her düğüm kendi yerel kurallarını sağlıyor
    ama k aşılıyor. Böyle bir çıktı gelirse dağıtık algoritmada hata vardır ve
    ihlal sorumlu düğümü adıyla anmalıdır.
    """
    g = _g(STAR5, k=2)
    # yıldız merkezi bütün kenarları sahiplenir; yerel denetim |owned| ≤ k'yı
    # gördüğü için düşer, dolayısıyla sav çürütülemez: mismatch ÜRETİLMEZ.
    views = {
        1: V.LocalView(nid=1, in_cover=True, owned=((1, 2), (1, 3), (1, 4), (1, 5)), forced_load=4),
        2: V.LocalView(nid=2, in_cover=False),
        3: V.LocalView(nid=3, in_cover=False),
        4: V.LocalView(nid=4, in_cover=False),
        5: V.LocalView(nid=5, in_cover=False),
    }
    report, local = V.check_local_global(g, views)
    assert local[1] and any(v.kind == V.OVERLOAD for v in local[1])
    assert report.by_kind(V.OVERLOAD)
    assert not report.by_kind(V.LOCAL_GLOBAL)   # yerel zaten yakaladı, sav ayakta

    # Şimdi savın gerçekten çalıştığını gösteren yön: yerel denetimleri geçen
    # ve G[C] bağlı olan her çözümde küresel denetim de geçer.
    g2 = _g(BOWTIE, k=2)
    owner = {
        (1, 2): 2, (1, 3): 3, (4, 6): 4, (5, 6): 5,
        (2, 3): 2, (3, 4): 3, (4, 5): 5,
    }
    views2 = V.views_from_solution(g2, [2, 3, 4, 5], owner)
    rep2, loc2 = V.check_local_global(g2, views2)
    assert all(v == [] for v in loc2.values()) and rep2.connected
    assert rep2.valid and not rep2.by_kind(V.LOCAL_GLOBAL)


def test_local_global_theorem_on_random_instances():
    """Rastgele örneklerde sav: bütün yerel denetimler geçti + G[C] bağlı => küresel geçer."""
    rnd = random.Random(7)
    tested = 0
    for _ in range(400):
        g, cover = _random_instance(rnd)
        if bridge.uncovered_edges(g, cover) or not g.edges:
            continue
        flow = V.validate(g, cover, connectivity=V.PER_COMPONENT)
        if not flow.capacity:
            continue
        views = V.views_from_solution(g, cover, flow.resolved_owner)
        report, local = V.check_local_global(g, views, connectivity=V.PER_COMPONENT)
        all_local_ok = all(v == [] for v in local.values())
        if all_local_ok and report.connected:
            assert report.valid, (g.edges, cover, g.capacity_k, report.violations)
            tested += 1
    assert tested >= 20


def test_local_view_from_snapshot():
    from ccvc.bb.api import Counters, NodeSnapshot, Role

    snap = NodeSnapshot(
        nid=3, role=Role.COVER, phase=4, key=None, deg=2,
        owned=((3, 2), (3, 4)), forced_load=1, counters=Counters(), epoch=0,
    )
    lv = V.LocalView.from_snapshot(snap)
    assert lv.nid == 3 and lv.in_cover and lv.owned == ((2, 3), (3, 4)) and lv.forced_load == 1


def test_check_local_global_notes_missing_views():
    g = _g(PATH5, k=2)
    views = {2: V.LocalView(nid=2, in_cover=True, owned=((1, 2), (2, 3)), forced_load=1)}
    report, local = V.check_local_global(g, views)
    assert any("yerel görüş verilmeyen" in n for n in report.notes)
    assert not report.by_kind(V.LOCAL_GLOBAL)


# ==========================================================================
# kalibrasyon: brief'in çalışan örneği (10 düğüm, 15 kenar, k=2, Σw=25)
# ==========================================================================
CAL_EDGES = [
    (1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (4, 5), (4, 6), (5, 6),
    (5, 7), (6, 7), (7, 8), (7, 9), (8, 9), (8, 10), (9, 10),
]
CAL_W = {1: 5, 2: 2, 3: 4, 4: 3, 5: 6, 6: 2, 7: 3, 8: 2, 9: 5, 10: 4}
CAL_COVER = [1, 2, 3, 4, 6, 7, 8, 10]
CAL_OWNER = {
    # zorunlu kenarlar (5 ve 9 C dışında)
    (4, 5): 4, (5, 6): 6, (5, 7): 7, (7, 9): 7, (8, 9): 8, (9, 10): 10,
    # esnek kenarlar
    (6, 7): 6, (7, 8): 8, (4, 6): 4, (2, 4): 2, (3, 4): 3,
    (2, 3): 2, (1, 2): 1, (1, 3): 1,
    (8, 10): 10,
}


def _cal_graph(k: int = 2) -> CcvcGraph:
    return V.make_graph(CAL_EDGES, k, CAL_W, nodes=list(range(1, 11)))


def test_calibration_cover_is_valid_and_weight_is_25():
    g = _cal_graph()
    assert len(g.nodes) == 10 and len(g.edges) == 15
    r = V.validate(g, CAL_COVER, CAL_OWNER)
    assert r.valid, r.violations
    assert g.total_weight(CAL_COVER) == 25.0
    assert r.load == {1: 2, 2: 2, 3: 1, 4: 2, 6: 2, 7: 2, 8: 2, 10: 2}
    assert r.forced == {1: 0, 2: 0, 3: 0, 4: 1, 6: 1, 7: 2, 8: 1, 10: 1}


def test_calibration_meets_lower_bound():
    g = _cal_graph()
    assert V.lower_bound_g6(g) == 8 == len(CAL_COVER)      # ⌈15/2⌉ = 8
    assert V.check_g6(g, CAL_COVER) == []


def test_calibration_flow_fallback_finds_an_assignment():
    g = _cal_graph()
    r = V.validate(g, CAL_COVER)
    assert r.capacity and r.owner_source == "flow"
    assert len(r.resolved_owner) == 15
    back = V.validate(g, CAL_COVER, r.resolved_owner)
    assert back.valid, back.violations


def test_calibration_weight_25_is_the_optimum():
    """Belgenin "optimum 25" iddiası kaba kuvvetle doğrulanır (2^10 alt küme).

    Not: 25 ağırlığında İKİ optimum vardır; belgenin verdiği {1,2,3,4,6,7,8,10}
    onlardan biridir. Belge "optimum ... ile" dediği için bu bir çelişki değildir,
    ama tekliği varsayan kod yazılmamalıdır.
    """
    g = _cal_graph()
    best: List[Tuple[float, Tuple[int, ...]]] = []
    for size in range(1, 11):
        for c in itertools.combinations(g.nodes, size):
            cs = set(c)
            if bridge.uncovered_edges(g, cs):
                continue
            if len(V.cover_components(g, cs)) > 1:
                continue
            if not bridge.capacity_feasible(g, cs)[0]:
                continue
            best.append((g.total_weight(cs), tuple(sorted(cs))))
    best.sort()
    assert best[0][0] == 25.0
    optima = {c for w, c in best if w == 25.0}
    assert tuple(CAL_COVER) in optima
    assert optima == {(1, 2, 3, 4, 6, 7, 8, 10), (2, 3, 4, 6, 7, 8, 9, 10)}


def test_calibration_local_global_consistency():
    g = _cal_graph()
    views = V.views_from_solution(g, CAL_COVER, CAL_OWNER)
    report, local = V.check_local_global(g, views)
    assert all(v == [] for v in local.values()), local
    assert report.valid, report.violations
    assert not report.by_kind(V.LOCAL_GLOBAL)


def test_calibration_key_matches_brief_worked_example():
    """api.key_of'un brief'teki üç değeri: w=5,deg=2 -> 1.67; w=2,deg=3 -> 0.50; w=3,deg=4 -> 0.60."""
    from ccvc.bb.api import from_fp, key_of

    g = _cal_graph()
    assert g.degree(1) == 2 and g.degree(2) == 3 and g.degree(4) == 4
    assert round(from_fp(key_of(CAL_W[1], g.degree(1), 1)[0]), 2) == 1.67
    assert round(from_fp(key_of(CAL_W[2], g.degree(2), 2)[0]), 2) == 0.50
    assert round(from_fp(key_of(CAL_W[4], g.degree(4), 4)[0]), 2) == 0.60


# ==========================================================================
# api sözleşmesi
# ==========================================================================
def test_report_is_an_api_validation_report():
    g = _g(PATH5, k=2)
    r = V.validate(g, [2, 3, 4], {(1, 2): 2, (2, 3): 3, (3, 4): 3, (4, 5): 4})
    assert isinstance(r, ValidationReport)
    assert r.valid and r.summary() == "VALID"
    bad = V.validate(g, [2, 4])
    assert bad.summary().startswith("INVALID: ")
