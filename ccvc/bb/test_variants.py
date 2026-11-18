#!/usr/bin/env python3
"""DFS-Spanning-Backbone ve GHS-MST-Backbone testleri.

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_variants.py -q

KURAL: dikiş sözleşmesi DAVRANIŞLA sınanır. `_backbone_step`in çağrıldığını
assert eden bir test, düzeltmenin NEREYE yazıldığını sabitler ve aynı derecede
geçerli bir yeniden düzenlemede yeşil kalır. Sorulan soru her yerde şudur:
omurga Faz 3'e GEÇERLİ ROLLERLE varıyor mu?
"""
from __future__ import annotations

import inspect
import os
import random
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb.api import Role  # noqa: E402
from ccvc.bb.variants import (  # noqa: E402
    adjacency,
    saturated_flexible_edges,
    assert_connected,
    default_key,
    mst_backbone_roles,
    mst_internal_nodes,
    roles_from_backbone,
)

EDGES = [
    (1, 2),
    (1, 3),
    (2, 3),
    (2, 4),
    (3, 4),
    (4, 5),
    (4, 6),
    (5, 6),
    (5, 7),
    (6, 7),
    (7, 8),
    (7, 9),
    (8, 9),
    (8, 10),
    (9, 10),
]
WEIGHTS = {i + 1: w for i, w in enumerate([5, 2, 4, 3, 6, 2, 3, 2, 5, 4])}


def backbone_of(roles):
    return {v for v, r in roles.items() if r in (Role.MIS, Role.CONNECTOR)}


def is_connected(adj, S):
    if not S:
        return False
    s = next(iter(S))
    seen, stack = set(), [s]
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        stack.extend(v for v in adj[u] if v in S and v not in seen)
    return seen == set(S)


def is_dominating(adj, S):
    return all(v in S or (adj[v] & S) for v in adj)


def connected_geometric(n, avg, seed, tries=200):
    """BAĞLI bir birim disk çizgesi üret. Bağlı olmayanı DÖNDÜRMEZ."""
    rng = random.Random(seed)
    for _ in range(tries):
        pts = {i: (rng.random(), rng.random()) for i in range(1, n + 1)}
        r = (avg / (3.14159 * (n - 1))) ** 0.5
        edges = [
            (u, v)
            for u in pts
            for v in pts
            if u < v
            and (pts[u][0] - pts[v][0]) ** 2 + (pts[u][1] - pts[v][1]) ** 2 <= r * r
        ]
        w = {i: rng.randint(1, 100) for i in pts}
        try:
            assert_connected(sorted(pts), edges)
        except ValueError:
            continue
        return sorted(pts), edges, w
    return None


# ==========================================================================
# 1. Girdi kapısı (ekip lideri uyarısı: ölçmeden ÖNCE bağlılık)
# ==========================================================================
def test_disconnected_input_is_refused_before_any_measurement():
    """Kopuk çizgede kol karşılaştırması sessizce çizge üretimini ölçer."""
    with pytest.raises(ValueError, match="KOPUK"):
        assert_connected([1, 2, 3, 4], [(1, 2), (3, 4)])
    with pytest.raises(ValueError, match="KOPUK"):
        assert_connected([1, 2, 3], [(1, 2)])
    assert_connected([1, 2, 3], [(1, 2), (2, 3)])  # atmamalı


def test_the_seeder_itself_refuses_a_disconnected_graph():
    with pytest.raises(ValueError, match="KOPUK"):
        mst_backbone_roles([1, 2, 3, 4], [(1, 2), (3, 4)], {1: 1, 2: 1, 3: 1, 4: 1})


def test_malformed_edges_are_refused():
    with pytest.raises(ValueError, match="ilmek"):
        adjacency([1, 2], [(1, 1)])
    with pytest.raises(ValueError, match="bilinmeyen"):
        adjacency([1, 2], [(1, 9)])


# ==========================================================================
# 2. Dikiş sözleşmesi: B bağlı ve baskın, roller geçerli, MIS bağımsız
# ==========================================================================
def assert_contract(nodes, edges, weights, roles):
    adj = adjacency(nodes, edges)
    assert set(roles) == set(adj), "her düğümün bir rolü olmalı"
    assert all(
        r in (Role.MIS, Role.CONNECTOR, Role.OUT) for r in roles.values()
    ), "Faz 1 COVER rolü ATAMAZ; o Faz 2'nin işidir"
    B = backbone_of(roles)
    assert is_connected(adj, B), "B bağlı değil (brief G1/G2)"
    assert is_dominating(adj, B), "B baskın değil (brief G2)"
    mis = {v for v, r in roles.items() if r is Role.MIS}
    assert all(not (adj[v] & mis) for v in mis), "MIS bağımsız olmalı"
    return B


def test_v4_contract_holds_on_the_calibration_graph():
    roles = mst_backbone_roles(sorted(WEIGHTS), EDGES, WEIGHTS)
    B = assert_contract(sorted(WEIGHTS), EDGES, WEIGHTS, roles)
    # Düğüm 1 ağacın KÖKÜ ve tek çocuğu var, yani ağaç derecesi 1: yaprak,
    # iç düğüm değil. `children > 0` sayan ilk sürüm onu omurgaya alıyordu ve
    # örtüyü gereksiz yere ağırlaştırıyordu (ağırlık 17 yerine 12).
    assert B == {2, 4, 6, 7, 8}
    assert sum(WEIGHTS[v] for v in B) == 12


@pytest.mark.parametrize(
    "n,avg,seed",
    [(n, a, s) for n, a in ((20, 5), (60, 8), (120, 12)) for s in range(4)],
)
def test_v4_contract_holds_on_connected_geometric_graphs(n, avg, seed):
    got = connected_geometric(n, avg, seed)
    if got is None:
        pytest.skip("bu tohumda bağlı örnek üretilemedi")
    nodes, edges, w = got
    assert_contract(nodes, edges, w, mst_backbone_roles(nodes, edges, w))


def test_v4_seeding_is_deterministic():
    a = mst_backbone_roles(sorted(WEIGHTS), EDGES, WEIGHTS)
    b = mst_backbone_roles(sorted(WEIGHTS), list(reversed(EDGES)), WEIGHTS)
    assert a == b, "kenar sırası ağacı değiştirmemeli"


# ==========================================================================
# 3. İç düğüm matematiği
# ==========================================================================
def test_internal_nodes_of_a_spanning_tree_are_a_connected_dominating_set():
    nodes, edges, w = connected_geometric(40, 6, 3)
    adj = adjacency(nodes, edges)
    internal = mst_internal_nodes(nodes, edges, w)
    assert is_connected(adj, internal) and is_dominating(adj, internal)


def test_a_two_node_graph_still_yields_a_nonempty_backbone():
    """n=2'de ağacın iki ucu da yapraktır; iç küme boş kalamaz."""
    roles = mst_backbone_roles([1, 2], [(1, 2)], {1: 3, 2: 7})
    assert backbone_of(roles), "omurga boş olamaz"
    assert_contract([1, 2], [(1, 2)], {1: 3, 2: 7}, roles)


def test_a_path_graph_makes_every_interior_node_backbone():
    nodes, edges = [1, 2, 3, 4, 5], [(1, 2), (2, 3), (3, 4), (4, 5)]
    w = {v: 1 for v in nodes}
    roles = mst_backbone_roles(nodes, edges, w)
    assert backbone_of(roles) == {2, 3, 4}, "yol çizgesinde iç düğümler tektir"


def test_roles_from_backbone_rejects_nothing_and_covers_everything():
    adj = adjacency(sorted(WEIGHTS), EDGES)
    key = default_key(adj, WEIGHTS)
    roles = roles_from_backbone({1, 2, 4, 6, 7, 8}, adj, key)
    assert backbone_of(roles) == {1, 2, 4, 6, 7, 8}
    assert {v for v, r in roles.items() if r is Role.OUT} == {3, 5, 9, 10}


# ==========================================================================
# 4. GERÇEK KIYAS KÜMESİ: sözleşme 310 örneğin hepsinde tutmalı
#     Rastgele geometrik çizge kolaylık için seçilmiş bir ailedir; MWCCVC'nin
#     Dagdeviren kümesi algoritmanın optimize ettiği GERÇEK düğüm ağırlığı
#     dağılımını taşır. Sözleşme orada tutmuyorsa hiçbir yerde tutmuyordur.
# ==========================================================================
def _benchmark_instances():
    from ccvc.bb import matrix

    if matrix.dataset_dir() is None:
        return []
    out = []
    for c in matrix.feasible_cells():
        for s in matrix.seeds_available(c):
            out.append((c, s))
    return out


BENCH = _benchmark_instances()


@pytest.mark.skipif(not BENCH, reason="Dagdeviren veri kümesi bulunamadı")
def test_every_benchmark_instance_is_connected_before_we_measure_anything():
    """Brief §1 bağlı çizge ister. Kopuk bir örnek ölçüme HİÇ girmemeli."""
    from ccvc.bb import matrix

    for c, s in BENCH:
        w, e = matrix.load_instance(matrix.instance_path(c, s))
        assert_connected(sorted(w), e)


@pytest.mark.skipif(not BENCH, reason="Dagdeviren veri kümesi bulunamadı")
def test_v4_contract_holds_on_every_benchmark_instance():
    """310 örneğin hepsinde B bağlı, baskın ve MIS bağımsız."""
    from ccvc.bb import matrix

    checked = 0
    for c, s in BENCH:
        w, e = matrix.load_instance(matrix.instance_path(c, s))
        assert_contract(sorted(w), e, w, mst_backbone_roles(sorted(w), e, w))
        checked += 1
    assert checked == 310, f"kıyas kümesi 310 örnek bekliyordu, {checked} bulundu"


@pytest.mark.skipif(not BENCH, reason="Dagdeviren veri kümesi bulunamadı")
def test_benchmark_max_degree_fits_the_neighbour_table():
    """Ölçüldü: kıyas kümesindeki en büyük derece 36, tablo sınırı 64."""
    from ccvc.bb import matrix
    from ccvc.bb.bootstrap import BootstrapParams

    worst = 0
    for c, s in BENCH:
        w, e = matrix.load_instance(matrix.instance_path(c, s))
        adj = adjacency(sorted(w), e)
        worst = max(worst, max(len(a) for a in adj.values()))
    assert worst == 36, f"kıyas kümesinin en büyük derecesi 36 idi, {worst} çıktı"
    assert worst < BootstrapParams().nbr_table_max, "tablo taşar, dereceler kırpılır"


# ==========================================================================
# 5. Kol ölçütü: iki uygunsuzluk kipi KARIŞMAMALI
# ==========================================================================
from ccvc.bb.variants import (  # noqa: E402
    INFEASIBLE_COVER,
    INFEASIBLE_INSTANCE,
    UNRESOLVED,
    VALID,
    classify_outcome,
)


def test_an_infeasible_instance_is_not_blamed_on_the_arm():
    """Örnek k altında çözümsüzse bu kolun başarısızlığı DEĞİLDİR."""
    assert classify_outcome(True, True) == INFEASIBLE_INSTANCE
    # Kol uygun dese bile örnek uygunsuzsa sınıflandırma örneğe bakar.
    assert classify_outcome(False, True) == INFEASIBLE_INSTANCE


def test_an_infeasible_cover_on_a_feasible_instance_is_the_arms_fault():
    """İLGİNÇ OLAN kip: örnek çözülebilir, kolun örtüsü uygun değil."""
    assert classify_outcome(True, False) == INFEASIBLE_COVER
    assert classify_outcome(False, False) == VALID


def test_arms_can_only_differ_in_the_cover_bucket():
    """Aynı örnek kümesinde koşan kollar örnek kovasında AYRILAMAZ.

    `instance_infeasible` merkezi çözücüden gelir ve koldan bağımsızdır;
    dolayısıyla kollar arası her fark `infeasible_cover` kovasındadır.
    İki kipi tek sayıda toplamak bu ayrımı yok ederdi.
    """
    for inst_infeasible in (True, False):
        buckets = {classify_outcome(arm, inst_infeasible) for arm in (True, False)}
        if inst_infeasible:
            assert buckets == {INFEASIBLE_INSTANCE}, "örnek kovası kola duyarsız"
        else:
            assert buckets == {INFEASIBLE_COVER, VALID}, "fark yalnız burada"


def test_the_saturated_flexible_trigger_is_a_diagnostic_not_a_verdict():
    """Açgözlü tetikleyici üçüncü bir verdikt kovası OLAMAZ.

    Uygun örneklerde de ateşlediği için uygunsuzluğu ilan edemez; ayrıca ekip
    liderinin ölçümüne göre engel G[C] içinde 13 atlama uzanıyor ve 1..4
    yarıçaplı hiçbir topta sayım ihlali yok, yani hiçbir yerel yüklem
    uygunsuzluğu KANITLAYAMAZ. Verdikt üç kovada kalır.
    """
    from ccvc.bb import variants

    assert {
        variants.VALID,
        variants.INFEASIBLE_COVER,
        variants.INFEASIBLE_INSTANCE,
    } == {variants.classify_outcome(a, b) for a in (True, False) for b in (True, False)}
    src = inspect.getsource(variants.classify_outcome)
    assert "saturated" not in src, "teşhis verdikte sızmamalı"


def test_saturated_flexible_edges_finds_both_ends_at_capacity():
    class _Run:
        cover = [1, 2, 3]
        owner = {(1, 2): 1, (1, 3): 1, (2, 3): 2, (2, 4): 2}

    adj = {1: {2, 3}, 2: {1, 3, 4}, 3: {1, 2}, 4: {2}}
    # k=2: dugum 1 iki kenar sahibi, dugum 2 iki kenar sahibi -> (1,2) doygun
    got = saturated_flexible_edges(_Run(), adj, k=2)
    assert (1, 2) in got
    # k=4: kimse doygun degil
    assert saturated_flexible_edges(_Run(), adj, k=4) == []


def test_an_unresolved_run_is_not_counted_as_valid():
    """Çözülemeden biten koşum geçerli bir cevap ÜRETMEMİŞTİR.

    İlk sürümüm yalnız `infeasible`a bakıyordu, dolayısıyla unresolved bir
    koşumu VALID sayıyor ve kolu olduğundan başarılı gösteriyordu.
    """
    assert classify_outcome(False, False, True) == UNRESOLVED
    assert classify_outcome(False, False, False) == VALID
    assert classify_outcome(True, False, True) == INFEASIBLE_COVER


def test_the_k4_k1_trap_cannot_contaminate_the_arm_column():
    """Ekip lideri bildirdi: K4/k=1 en kaba sayım sınırını çiğnediği hâlde
    `unresolved` dönüyor (bb-algo'da). Merkezi çözücü onu uygunsuz ilan
    ettiği için örnek kovasına düşer, bütün kollarda aynıdır ve kol farkını
    kirletmez. Örnek verdikti ÖNCE bakıldığı için bu kendiliğinden doğrudur.
    """
    for arm_infeasible in (True, False):
        for arm_unresolved in (True, False):
            assert (
                classify_outcome(arm_infeasible, True, arm_unresolved)
                == INFEASIBLE_INSTANCE
            ), "örnek uygunsuzsa kolun bayrakları sonucu değiştiremez"


# ==========================================================================
# 6. DFS-Spanning-Backbone protokolü: TELDEN ÖNCE doğruluk
# ==========================================================================
from ccvc.bb.variants import dfs_internal_nodes, simulate_dfs_walk  # noqa: E402


def test_the_dfs_protocol_reaches_the_same_tree_as_the_reference():
    """Protokol (yerel başlatıcılar, teklif, geri dönme, önalma) referansla aynı.

    Ağın üstünde bir sapma çıkarsa suçlunun TAŞIMA katmanı olduğunu bilmek
    için: mantık burada, telden bağımsız olarak doğrulanmıştır.
    """
    for nodes, edges in (
        ([1, 2, 3, 4, 5], [(1, 2), (2, 3), (3, 4), (4, 5)]),
        (sorted(WEIGHTS), EDGES),
    ):
        got, _ = simulate_dfs_walk(nodes, edges)
        assert got == dfs_internal_nodes(nodes, edges)


@pytest.mark.skipif(not BENCH, reason="Dagdeviren veri kümesi bulunamadı")
def test_the_dfs_protocol_matches_the_reference_on_every_benchmark_instance():
    from ccvc.bb import matrix

    for c, s in BENCH:
        w, e = matrix.load_instance(matrix.instance_path(c, s))
        got, _ = simulate_dfs_walk(sorted(w), e)
        assert got == dfs_internal_nodes(sorted(w), e), f"{c} seed {s}"


def test_the_simulation_does_not_claim_to_measure_preemption_cost():
    """Sayaç adı, ÖLÇMEDİĞİ şeyi ölçüyormuş gibi okunmamalı.

    Simülasyon yalnız kazanan gezintiyi işletir, dolayısıyla önalınan
    gezintilerin teklifleri sayılmaz. Ad bunu söylemek zorundadır; "offers"
    deseydik alt sınır gerçek maliyet sanılırdı.
    """
    _, stats = simulate_dfs_walk(sorted(WEIGHTS), EDGES)
    assert "offers_winning_walk_only" in stats
    assert "offers" not in stats, "çıplak 'offers' adı yanıltıcı olurdu"


# ==========================================================================
# 7. Sahiplik TAM olmalı — bb-algo'nun dosyasında üç hata yakalamış denetim
# ==========================================================================
from ccvc.bb.variants import (  # noqa: E402
    assert_ownership_is_total,
    double_owned_edges,
    unowned_edges,
)


class _FakeRun:
    def __init__(self, owner):
        self.owner = owner


def test_an_unowned_edge_makes_the_run_unreportable():
    """owner: E -> C TAM bir fonksiyondur (brief §1); eksik sahiplik hatadır.

    Üç ayrı hata bu denetimle yakalandı ve üçünde de koşum YAKINSADI ve
    sayaçlar TEMİZ okudu. "Koşum doğru görünüyordu" hiçbirini yakalamazdı.
    """
    from ccvc.bb.bootstrap import RunInvalid

    edges = [(1, 2), (2, 3), (3, 1)]
    assert unowned_edges(_FakeRun({(1, 2): 1, (2, 3): 2, (3, 1): 3}), edges) == []
    assert_ownership_is_total(_FakeRun({(1, 2): 1, (2, 3): 2, (3, 1): 3}), edges)

    partial = _FakeRun({(1, 2): 1, (2, 3): 2})
    assert unowned_edges(partial, edges) == [(1, 3)]
    with pytest.raises(RunInvalid, match="sahibi yok"):
        assert_ownership_is_total(partial, edges)


def test_edge_orientation_does_not_hide_an_owner():
    """(u,v) ile (v,u) aynı kenardır; yön farkı sahipsizlik gibi okunmamalı."""
    assert unowned_edges(_FakeRun({(2, 1): 1}), [(1, 2)]) == []


from ccvc.bb.variants import TRUNCATED  # noqa: E402


def test_a_budget_truncated_run_is_not_counted_as_valid():
    """ÖLÇÜLDÜ: kesilmiş koşum başarılıdan HİÇBİR bayrakla ayrılmıyordu.

    max_ms=3000'de aynı örnekte `converged` False, ama `infeasible` ve
    `unresolved` ikisi de False ve sahiplik TAM (15/15). Yani yalnız o iki
    bayrağa bakan bir sınıflandırıcı kesilmiş koşumu VALID sayar.
    """
    assert classify_outcome(False, False, False, False) == TRUNCATED
    assert classify_outcome(False, False, False, True) == VALID
    # Kesilme kolun kendi bayraklarından ÖNCE gelir: bitmemiş koşumun
    # "uygun" ya da "çözülemedi" demesi anlamsızdır.
    assert classify_outcome(True, False, False, False) == TRUNCATED
    assert classify_outcome(False, False, True, False) == TRUNCATED
    # Ama örnek verdikti hâlâ en üstte ve kola duyarsız.
    assert classify_outcome(False, True, False, False) == INFEASIBLE_INSTANCE


def test_truncation_is_detectable_on_a_real_run():
    """Sinyalin gerçek koşumda var olduğunu doğrula, varsayma."""
    from ccvc.bb import bbcvc

    full = bbcvc.run_bbcvc(EDGES, WEIGHTS, 2, scheduler="sync", max_ms=200_000)
    cut = bbcvc.run_bbcvc(EDGES, WEIGHTS, 2, scheduler="sync", max_ms=3_000)
    assert full.converged and not cut.converged
    assert not cut.infeasible and not cut.unresolved, "bayraklar kesilmeyi GÖSTERMİYOR"
    assert (
        classify_outcome(
            bool(full.infeasible), False, bool(full.unresolved), bool(full.converged)
        )
        == VALID
    )
    assert (
        classify_outcome(
            bool(cut.infeasible), False, bool(cut.unresolved), bool(cut.converged)
        )
        == TRUNCATED
    )


# ==========================================================================
# 8. 0-tabanlı kıyas kümesi ile 0'ı ayıran kimlik uzayı
# ==========================================================================
from ccvc.bb.variants import load_benchmark_instance, relabel_from_one  # noqa: E402


def test_the_whole_benchmark_is_zero_indexed_and_the_id_space_reserves_zero():
    """Ölçüldü: 310/310 örnekte düğüm 0 var, hash16 asla 0 döndüremez.

    Yani yeniden etiketleme olmadan HİÇBİR kıyas örneği koşturulamaz.
    """
    from ccvc.bb import matrix
    from ccvc.bb.bbcvc import mac_for_id
    from ccvc.bb.bootstrap import hash16

    assert all(hash16(m) != 0 for m in range(50_000))
    with pytest.raises(RuntimeError):
        mac_for_id(0)
    c, s = BENCH[0] if BENCH else (None, None)
    if c is None:
        pytest.skip("veri kümesi yok")
    w, _ = matrix.load_instance(matrix.instance_path(c, s))
    assert 0 in w, "kıyas örneği 0-tabanlı olmalı (bu testin dayanağı)"


def test_relabelling_preserves_the_graph_and_maps_back():
    w = {0: 5, 1: 2, 2: 4}
    e = [(0, 1), (1, 2)]
    w2, e2, back = relabel_from_one(w, e)
    assert sorted(w2) == [1, 2, 3] and 0 not in w2
    assert e2 == [(1, 2), (2, 3)]
    assert {back[n]: w2[n] for n in w2} == w, "ağırlıklar geri eşlenebilmeli"
    assert sorted((back[u], back[v]) for u, v in e2) == sorted(e)


@pytest.mark.skipif(not BENCH, reason="Dagdeviren veri kümesi bulunamadı")
def test_every_benchmark_instance_becomes_runnable_after_relabelling():
    from ccvc.bb.bbcvc import mac_for_id

    for c, s in BENCH[:40]:
        w2, e2, back = load_benchmark_instance(c, s)
        assert 0 not in w2
        assert sorted(w2) == list(range(1, len(w2) + 1))
        for nid in w2:
            mac_for_id(nid)  # ön görüntü bulunmalı; bulunmazsa yükselir


def test_a_double_owned_edge_is_invisible_in_the_map_but_caught_in_the_sets():
    """Harita kusuru TEMSİL EDEMEZ; denetim toplanmadan önce yapılmalı.

    `owner[e] = nid` ikinci yazanı birinciyi ezerek kaydeder, dolayısıyla
    harita TAM okur, her kenarın tek sahibi görünür ve doğrulayıcı temiz
    geçer. Sadece düğüm başına `owned` kümelerini saymak görebilir.
    """
    from ccvc.bb.bootstrap import RunInvalid

    class _N:
        def __init__(self, owned):
            self.owned = owned

    class _R:
        nodes = {15: _N({(15, 19), (1, 2)}), 19: _N({(19, 15)}), 2: _N({(2, 3)})}
        owner = {(15, 19): 19, (1, 2): 15, (2, 3): 2}  # ikinci yazan ezdi

    edges = [(15, 19), (1, 2), (2, 3)]
    r = _R()
    assert unowned_edges(r, edges) == [], "haritaya göre her şey yolunda"
    assert len(r.owner) == len(edges), "harita TAM okuyor"
    assert double_owned_edges(r) == [((15, 19), (15, 19))], "kümeler gerçeği söylüyor"
    with pytest.raises(RunInvalid, match="BİRDEN ÇOK"):
        assert_ownership_is_total(r, edges)


def test_edge_orientation_does_not_create_a_phantom_double_owner():
    class _N:
        def __init__(self, owned):
            self.owned = owned

    class _R:
        nodes = {1: _N({(1, 2)})}
        owner = {(2, 1): 1}

    assert double_owned_edges(_R()) == [], "(u,v) ile (v,u) aynı kenardır"
