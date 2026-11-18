#!/usr/bin/env python3
"""BB-CVC testleri: çalışan örnek, birim çizgeler, yapısal olgular, özellik
testleri, muhasebe kalibrasyonu ve iki zamanlayıcının karşılaştırması.

Koşum (depo kökünden):
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_bbcvc.py -q

(Düz `pytest` bu makinede çöküyor: PYTHONPATH'teki /opt/ros/jazzy, eksik bir
`lark`i içe aktaran bir eklenti getiriyor.)

SÜRE. Varsayılan matris ~31 saniyede biter ve hiçbir tek test 5 saniyeyi
geçmez. Bu dosya alfabetik sırada paketin BAŞINDA koştuğu için ağır olması
`pytest ccvc/bb/` çağıran herkesi bekletiyordu; n=60 hücreleri bu yüzden bir
kapının arkasındadır:

    BBCVC_SLOW=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_bbcvc.py -q

Protokol koşturan HER testin `max_ms` bütçesi vardır ve sonuç `converged`
üzerinden assert edilir, beklenerek değil: sonlanma kanıtlanacak özelliklerden
biridir, dolayısıyla sonlanmayan bir algoritma asılmak yerine HIZLA VE SESLİCE
düşmelidir.
"""
from __future__ import annotations

import math
import os
import random
import sys
from typing import Dict, List, Sequence, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc import bridge, central  # noqa: E402
from ccvc.bb import bbcvc, figures, sched, simnet, validate, wire  # noqa: E402
from ccvc.bb.api import MsgType, Role, from_fp  # noqa: E402
from ccvc.bb.bbcvc import (PH_CONN, PH_COVER, PH_DONE, PH_FORCED, PH_MIS,  # noqa: E402
                           PH_OWN, PH_QUIET, BbcvcNode, BbcvcParams, RunInvalid)

# --------------------------------------------------------------------------
# .tex Bölüm 1'in çalışan örneği
# --------------------------------------------------------------------------
EDGES = [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (4, 5), (4, 6), (5, 6),
         (5, 7), (6, 7), (7, 8), (7, 9), (8, 9), (8, 10), (9, 10)]
WEIGHTS = {1: 5, 2: 2, 3: 4, 4: 3, 5: 6, 6: 2, 7: 3, 8: 2, 9: 5, 10: 4}
K = 2

#: .tex Şekil "Faz 0 sonunda her düğüm komşularının anahtarını bilir"
EXPECTED_KEYS = {1: 1.67, 2: 0.50, 3: 1.00, 4: 0.60, 5: 1.50,
                 6: 0.50, 7: 0.60, 8: 0.50, 9: 1.25, 10: 1.33}

#: .tex'in verdiği kesin gerçekler (ekip lideri bağımsız olarak doğruladı):
#: optimum ağırlık 25 ve |C| = 8 = ⌈15/2⌉; İKİ optimum küme vardır, bu yüzden
#: hiçbir test TEK bir optimum kümeyi assert etmez.
OPT_WEIGHT = 25
OPT_SIZE = 8
OPTIMAL_COVERS = ({1, 2, 3, 4, 6, 7, 8, 10}, {2, 3, 4, 6, 7, 8, 9, 10})

BUDGET_MS = 600_000


def run(scheduler: str, edges=EDGES, weights=WEIGHTS, k=K, **kw) -> bbcvc.BbcvcRun:
    kw.setdefault("max_ms", BUDGET_MS)
    return bbcvc.run_bbcvc(edges, weights, k, scheduler=scheduler, **kw)


def graph_of(edges=EDGES, weights=WEIGHTS, k=K):
    return validate.make_graph(edges, k, weights)


def roles(r: bbcvc.BbcvcRun) -> Dict[int, Role]:
    return {nid: n.role for nid, n in r.nodes.items()}


def backbone(r: bbcvc.BbcvcRun) -> List[int]:
    return sorted(nid for nid, n in r.nodes.items() if n.role.in_backbone)


# ==========================================================================
# 1. Faz 0: anahtarlar
# ==========================================================================
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_keys_match_document(scheduler):
    """Anahtar w/(deg+1); derece HELLO ile keşfedilir, verilmez (api I1)."""
    r = run(scheduler)
    got = {nid: round(from_fp(n.key_fp), 2) for nid, n in r.nodes.items()}
    assert got == EXPECTED_KEYS
    # Derece de keşfedilmiştir ve gerçek çizgeyle örtüşür.
    assert {nid: n.deg for nid, n in r.nodes.items()} == {
        nid: r.net.degree(nid) for nid in r.nodes}


def test_node_never_sees_the_graph():
    """api I1: düğümün kurucusunda çizgeye dair tek bir alan yoktur."""
    import inspect
    params = set(inspect.signature(BbcvcNode.__init__).parameters) - {"self"}
    assert params == {"weight", "platform", "params", "capacity_k"}
    src = inspect.getsource(BbcvcNode)
    for forbidden in ("net.degree", "net.neighbors", "net.edges", "_adj", "SimNet"):
        assert forbidden not in src, f"düğüm kodu çizgeye uzanıyor: {forbidden}"


def test_no_rng_in_node():
    """Belirlenimcilik: BB-CVC rastgelelik KULLANMAZ, her eşitlik anahtarla kırılır."""
    import inspect
    src = inspect.getsource(BbcvcNode)
    for forbidden in ("random.", "xorshift32(", "rng"):
        assert forbidden not in src, f"düğüm kodunda rastgelelik: {forbidden}"


# ==========================================================================
# 2. Faz 1a/1b: omurga
# ==========================================================================
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_worked_example_backbone(scheduler):
    """.tex: MIS = {2,6,8}, connector = {4,7}, omurga = {2,4,6,7,8}."""
    r = run(scheduler)
    rr = roles(r)
    assert sorted(n for n, v in rr.items() if v == Role.MIS) == [2, 6, 8]
    assert sorted(n for n, v in rr.items() if v == Role.CONNECTOR) == [4, 7]
    assert backbone(r) == [2, 4, 6, 7, 8]


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_mis_is_independent_and_maximal(scheduler):
    """MIS kuralının anlamı: bağımsız (komşu iki MIS yok) ve maksimal (her
    düğüm ya MIS ya da bir MIS'e komşu)."""
    r = run(scheduler)
    mis = {n for n, v in roles(r).items() if v == Role.MIS}
    for u, v in EDGES:
        assert not (u in mis and v in mis), f"komşu iki MIS: {u},{v}"
    for v in r.nodes:
        assert v in mis or any(u in mis for u in r.net.neighbors(v))


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_smaller_key_mis_neighbour_blocks_mis(scheduler):
    """.tex Alg.1'in tersi yönü: küçük anahtarlı MIS komşusu olan MIS OLAMAZ."""
    r = run(scheduler)
    rr = roles(r)
    keys = {nid: (n.key_fp, nid) for nid, n in r.nodes.items()}
    for v in r.nodes:
        if rr[v] != Role.MIS:
            continue
        for u in r.net.neighbors(v):
            assert not (rr[u] == Role.MIS and keys[u] < keys[v])


# ==========================================================================
# 3. Faz 2/3/4: geçerli çıktı ve yapısal olgular (brief §2)
# ==========================================================================
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_worked_example_is_valid(scheduler):
    r = run(scheduler)
    rep = validate.validate(graph_of(), r.cover, r.owner)
    assert rep.valid, rep.summary()
    assert len(r.owner) == len(EDGES)      # her kenarın TAM BİR sahibi var
    assert not r.infeasible


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_structural_facts_g1_g2_g4_g6(scheduler):
    """brief §2: G1 (CVC bir CDS'tir), G2 (omurga baskındır, onarım fazı yok),
    G4 (F(v) <= k), G6 (|C| >= ceil(|E|/k))."""
    r = run(scheduler)
    g = graph_of()
    assert validate.check_g1(g, r.cover) == []
    assert validate.check_g2(g, backbone(r)) == []
    assert validate.check_g4(g, r.cover) == []
    assert validate.check_g6(g, r.cover) == []
    assert validate.is_dominating_set(g, backbone(r))
    assert len(validate.cover_components(g, backbone(r))) == 1


def test_g6_lower_bound_is_binding_here():
    """Ekip liderinin doğruladığı gerçek: burada kapasite BAĞLAYICIDIR.
    Kapasitesiz optimum 7 düğüm / 20 ağırlıktır; 7 düğüm k=2 ile en çok 14
    kenar sahiplenir, 15 kenar sığmaz. Bu yüzden |C| >= 8 = ceil(15/2)."""
    g = graph_of()
    assert validate.lower_bound_g6(g) == OPT_SIZE
    assert OPT_SIZE * K >= len(EDGES) > (OPT_SIZE - 1) * K


def test_optimum_is_25_and_not_unique():
    """İKİ optimum küme vardır; hiçbir test tek bir kümeyi assert etmemelidir."""
    g = graph_of()
    res = central.solve_exact(g, max_n=18, time_limit_s=60.0, strict=False)
    assert res.feasible
    assert round(res.total_weight) == OPT_WEIGHT
    for cov in OPTIMAL_COVERS:
        rep = validate.validate(g, cov)
        assert rep.valid, f"{cov}: {rep.summary()}"
        assert sum(WEIGHTS[v] for v in cov) == OPT_WEIGHT
    assert len(OPTIMAL_COVERS) > 1


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_worked_example_quality_vs_optimum(scheduler):
    """Yaklaşım oranı için önerme YOKTUR (brief G7); ölçülen değer sabitlenir.

    Ölçüm: her iki zamanlayıcı da |C| = 8 (alt sınıra eşit) ve ağırlık 27
    bulmaktadır; optimum 25'tir, oran 1.08. Fark FAZ 4'ün eskalasyonundandır:
    8 esnek kenara karşı 7 birim esnek bütçe olduğundan TAM BİR eskalasyon
    zorunludur, ama hangi düğümün eskale edeceğini yerel kurallar belirlemez.
    Burada düğüm 6 kazanıp 5'i (w=6) çağırır; .tex'in anlatımında düğüm 8
    kazanıp 10'u (w=4) çağırır ve 25 çıkar. İkisi de kuralların izin verdiği
    koşumlardır.
    """
    r = run(scheduler)
    assert len(r.cover) == OPT_SIZE
    assert r.total_weight == 27
    assert r.total_weight / OPT_WEIGHT <= 1.10


# ==========================================================================
# 4. Birim çizgeler, elle yazılmış beklentiler
# ==========================================================================
PATH5 = ([(1, 2), (2, 3), (3, 4), (4, 5)], {i: 1 for i in range(1, 6)}, 2)
STAR6 = ([(1, i) for i in range(2, 7)], {i: 1 for i in range(1, 7)}, 3)
K5 = ([(u, v) for u in range(1, 6) for v in range(u + 1, 6)],
      {i: 1 for i in range(1, 6)}, 3)
TWO_TRI = ([(1, 2), (2, 3), (1, 3), (3, 4), (4, 5), (5, 6), (4, 6)],
           {i: 1 for i in range(1, 7)}, 2)
SINGLE = ([(1, 2)], {1: 1, 2: 2}, 1)


def _grid(rows: int, cols: int):
    e = []
    for rr in range(rows):
        for cc in range(cols):
            i = rr * cols + cc + 1
            if cc < cols - 1:
                e.append((i, i + 1))
            if rr < rows - 1:
                e.append((i, i + cols))
    return e, {i: 1 for i in range(1, rows * cols + 1)}, 3


GRID4 = _grid(4, 4)

UNIT_GRAPHS = {
    "path5": PATH5, "star6": STAR6, "k5": K5,
    "two_triangles_bridge": TWO_TRI, "single_edge": SINGLE, "grid4x4": GRID4,
}

#: Elle hesaplanmış beklentiler. Ağırlıklar birim olduğundan ağırlık = |C|.
UNIT_EXPECT = {
    # 1-2-3-4-5: MIS {2,4} (anahtar 1/3 < 1/2), 3 connector, 1 ve 5 dışarıda
    "path5": dict(cover=[2, 3, 4], backbone=[2, 3, 4], weight=3),
    # yıldız: merkez tek MIS; F(1)=5 > k=3 olduğundan iki yaprak davet edilir
    "star6": dict(cover=[1, 2, 3], backbone=[1], weight=3),
    # K5: tek MIS; 5'in kendinden büyük anahtarlı OUT komşusu yok, dışarıda kalır
    "k5": dict(cover=[1, 2, 3, 4], backbone=[1], weight=4),
    # iki üçgen + köprü (3,4): omurga 3-4-5, 1 kapsam için eklenir
    "two_triangles_bridge": dict(cover=[1, 3, 4, 5], backbone=[3, 4, 5], weight=4),
    # tek kenar, k=1: hafif uç (w=1) MIS olur ve tek kenarı sahiplenir
    "single_edge": dict(cover=[1], backbone=[1], weight=1),
    # 4x4 ızgara: maksimum bağımsız küme 8 düğümdür, kalan 8 düğümün her biri
    # iki MIS arasında köprüdür ve çift kuralı hepsini connector yapar -> B = V.
    # Bu, .tex'in connector kuralının ARTIKLIK DENETİMİ OLMAMASININ sonucudur
    # ve raporlanmıştır; çıktı geçerlidir, yalnız gereğinden ağırdır.
    "grid4x4": dict(cover=list(range(1, 17)), backbone=list(range(1, 17)), weight=16),
}


@pytest.mark.parametrize("name", sorted(UNIT_GRAPHS))
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_unit_graphs(name, scheduler):
    edges, weights, k = UNIT_GRAPHS[name]
    exp = UNIT_EXPECT[name]
    r = run(scheduler, edges, weights, k)
    assert r.converged, f"{name}/{scheduler}: sükûnete ermedi"
    assert r.cover == exp["cover"]
    assert backbone(r) == exp["backbone"]
    assert r.total_weight == exp["weight"]
    rep = validate.validate(validate.make_graph(edges, k, weights), r.cover, r.owner)
    assert rep.valid, rep.summary()
    assert len(r.owner) == len(edges)


@pytest.mark.parametrize("name", sorted(UNIT_GRAPHS))
def test_unit_graphs_sync_async_agree(name):
    edges, weights, k = UNIT_GRAPHS[name]
    a = run("sync", edges, weights, k)
    b = run("async", edges, weights, k)
    assert a.cover == b.cover, f"{name}: sync/async farklı örtü"
    assert a.total_weight == b.total_weight
    _owner_diff_is_flexible_only(a, b, edges, k)


# ==========================================================================
# 5. Faz 1b 3-atlama boşluğu
# ==========================================================================
def test_three_hop_gap_is_bridged():
    """.tex Şekil "mesafe-3 boşluğu": a-x-y-b yolunda iki ardışık connector.

    Ağırlıklar .tex'in anahtarlarını üretecek biçimde seçilmiştir: a ve b hafif
    (MIS olurlar), x ve y arada kalır. Beklenti: omurga a'dan b'ye bağlanır.
    """
    # a=1, x=2, z=3, y=4, b=5, q=6
    edges = [(1, 2), (1, 3), (2, 4), (3, 4), (4, 5), (5, 6), (4, 6)]
    weights = {1: 1, 2: 7, 3: 9, 4: 8, 5: 1, 6: 9}
    r = run("sync", edges, weights, 4)
    g = validate.make_graph(edges, 4, weights)
    b = backbone(r)
    assert 1 in b and 5 in b, f"MIS uçları omurgada değil: {b}"
    assert validate.check_g2(g, b) == [], "omurga kopuk: 3-atlama boşluğu kapanmadı"
    assert len(validate.cover_components(g, b)) == 1
    rep = validate.validate(g, r.cover, r.owner)
    assert rep.valid, rep.summary()


def test_gap_rule_does_not_fire_when_backbone_is_a_single_mis():
    """Yıldız ve K_n'de omurga TEK düğümdür, yani zaten bağlıdır. .tex'in
    MIS-güdümlü 3-atlama kuralı buralarda yanlış ateşler; bizim x-güdümlü
    sürümümüz ateşlememelidir (bkz. bbcvc._rule_gap sapma notu)."""
    for name in ("star6", "k5"):
        edges, weights, k = UNIT_GRAPHS[name]
        r = run("sync", edges, weights, k)
        assert len(backbone(r)) == 1, f"{name}: omurga gereksiz büyüdü {backbone(r)}"


# ==========================================================================
# 6. Faz 3: zorunlu yük
# ==========================================================================
def test_forced_load_invites_smallest_keys():
    """.tex Faz 3 mini örneği: h örtüde, 5 komşusu dışarıda, k=3 -> iki davet.

    Burada yıldızın merkezi h'dir; F = 5 > 3 olduğundan en küçük anahtarlı iki
    komşu davet edilir. Ağırlıklar eşit olduğundan anahtar kimlikle kırılır.
    """
    edges, weights, k = STAR6
    r = run("sync", edges, weights, k)
    assert r.cover == [1, 2, 3]                       # en küçük iki kimlik
    assert validate.forced_load(validate.make_graph(edges, k, weights), r.cover, 1) == 3
    assert validate.check_g4(validate.make_graph(edges, k, weights), r.cover) == []


# ==========================================================================
# 7. Faz 4: INFEASIBLE yalnız GERÇEKTEN uygunsuzken
# ==========================================================================
def test_node_never_claims_infeasibility_it_cannot_prove():
    """DÜZELTİLMİŞ HATA (bb-bootstrap buldu, ölçümle doğrulandı).

    Eski kapı "kendi F'im 0 VE bütün komşularımın F'i 0" idi ve bunu .tex'in
    "C = V" koşulunun tanığı sayıyordum. SAĞLAM DEĞİLDİ: koşul yalnız benim iki
    atlamalık görüşümün örtü içinde olduğunu söyler, örtünün TAMAMINI kapsadığını
    değil. n=100, r=0.15, tohum 4, k=4'te düğüm 62 ve 94 koşulu sağlıyordu, oysa
    |C| = 89 < 100 ve örnek UYGUNDU: merkezî gwccvc |C| = 91 ile geçerli çözüm
    buluyor. Bayrak yanlış alarmdı ve bu, doğrulayıcının değil ALGORİTMANIN
    yalanıydı.

    Bugünkü HELLO ile SAĞLAM bir yerel uygunsuzluk tanığı HESAPLANAMAZ (bkz.
    test_counting_witness_needs_information_the_wire_does_not_carry). Düğümün
    dürüst cevabı "çözemedim"dir; uygunluk sorusunun yetkili mercii
    doğrulayıcıdır.
    """
    edges, weights, _ = figures.udg_instance(100, 0.15, 4)
    g = validate.make_graph(edges, 4, weights)
    assert bridge.capacity_feasible(g, set(weights))[0], "örnek gerçekten uygun"
    r = run("sync", edges, weights, 4, max_ms=300_000)
    assert not r.infeasible, "YANLIŞ UYGUNSUZLUK: örnek uygun, düğüm uygunsuz dedi"
    assert r.unresolved, "çözemediğini bildirmeli"
    assert r.converged, "ve yine de sonlanmalı"


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_infeasible_flag_is_never_a_false_alarm(scheduler):
    """EKİP LİDERİNİN KOŞULU: kesin çözücü "uygun" diyorsa INFEASIBLE HATADIR."""
    for edges, weights, k in (PATH5, STAR6, K5, TWO_TRI, SINGLE, GRID4,
                              (EDGES, WEIGHTS, K)):
        r = run(scheduler, edges, weights, k)
        if not r.infeasible:
            continue
        g = validate.make_graph(edges, k, weights)
        assert not bridge.capacity_feasible(g, set(weights)), (
            f"YANLIŞ UYGUNSUZLUK: C=V ile uygun atama var, |E|={len(edges)}, k={k}")


INFEASIBLE_BY_COUNTING = [
    ("K4", 4, 1), ("K5", 5, 1), ("K6", 6, 1), ("K6", 6, 2),
]


@pytest.mark.parametrize("name,n,k", INFEASIBLE_BY_COUNTING)
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_provably_infeasible_instances_are_declared_not_merely_unsolved(
        name, n, k, scheduler):
    """m > n*k ise HİÇBİR örtü işe yaramaz; bunu "çözemedim" diye raporlamak
    en kanıtlanabilir durumda en zayıf cevabı vermektir.

    `unresolved` "yerel onarım pes etti", `infeasible` "çözümü olmadığı
    kanıtlandı" demektir ve bb-bootstrap'ın sınıflandırıcısı bu ayrımın
    üstünde duruyor. Sınır koşum düzeyinde iki tam sayının aritmetiğidir;
    düğüm n ile m'yi göremez, dolayısıyla bu bir SİSTEM kanıtıdır ve
    `infeasible_reason` bunu açıkça söyler.
    """
    edges = [(u, v) for u in range(1, n + 1) for v in range(u + 1, n + 1)]
    weights = {i: 1 for i in range(1, n + 1)}
    g = validate.make_graph(edges, k, weights)
    assert not bridge.capacity_feasible(g, set(weights))[0], "örnek gerçekten uygunsuz"
    assert len(edges) > n * k, "sayma sınırı bu örneği kapsamalı"
    r = run(scheduler, edges, weights, k)
    assert r.converged, f"{name} k={k} {scheduler}: sonlanmadı"
    assert r.infeasible, f"{name} k={k} {scheduler}: uygunsuzluk İLAN EDİLMEDİ"
    assert r.infeasible_reason == "counting_bound"


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_a_run_never_reports_success_on_an_impossible_instance(scheduler):
    """EN SERT KOŞUL: uygunsuz bir örnekte koşum BAŞARI göstermemeli.

    Görünür bir başarısızlık satırı sonuç tablosuna girmez; sessiz bir başarı
    girer ve ortalamaya karışır. Bu yüzden denetim bayrakların VEYA'sı üzerinde:
    hangi bayrağın kalktığı ayrı bir testin konusu, burada sınanan şey hiçbirinin
    kalkmamasının imkânsız olduğudur.
    """
    for name, n, k in INFEASIBLE_BY_COUNTING:
        edges = [(u, v) for u in range(1, n + 1) for v in range(u + 1, n + 1)]
        weights = {i: 1 for i in range(1, n + 1)}
        r = run(scheduler, edges, weights, k)
        assert r.infeasible or r.unresolved, (
            f"{name} k={k} {scheduler}: imkânsız örnekte BAŞARI raporlandı "
            f"(yük {max(len(x.owned) for x in r.nodes.values())} > k={k})")
        rep = validate.validate(validate.make_graph(edges, k, weights),
                                r.cover, r.owner)
        assert not rep.valid, "doğrulayıcı da yakalamalı"


def test_counting_bound_is_arithmetic_and_stays_at_run_level():
    """Sınır iki tam sayının aritmetiğidir ve KOŞUM düzeyindedir.

    Düğüm n ile m'yi göremez (api I1), dolayısıyla bunu yerel bir yordama
    genişletmek mümkün değildir — ve denenmemelidir: öbür uygunsuzluk sınıfı
    ölçümle YEREL OLARAK SAPTANAMAZ çıktı (engel G[C] içinde 13 atlama geniş,
    1-4 yarıçaplarında hiçbir sayma ihlali yok). İki sınıfı ayrı tutmak
    `unresolved` ile `infeasible` ayrımının anlamıdır.
    """
    assert bbcvc.counting_bound_infeasible(4, 6, 1)      # K4, k=1
    assert bbcvc.counting_bound_infeasible(6, 15, 2)     # K6, k=2
    assert not bbcvc.counting_bound_infeasible(6, 15, 3)
    assert not bbcvc.counting_bound_infeasible(10, 15, 2)   # çalışan örnek
    # düğüm gövdesi bu fonksiyonu ÇAĞIRMAZ
    import ast
    import inspect
    body = ast.unparse(ast.parse(inspect.getsource(BbcvcNode)))
    assert "counting_bound_infeasible" not in body, (
        "sayma sınırı düğüm gövdesine sızmış: n ve m küresel büyüklüklerdir")


def test_k4_with_k1_terminates_and_the_validator_is_authoritative():
    """.tex Şekil "uygunsuz örnek": K4, k=1. |E|=6 > k*|V|=4 (Hakimi).

    .tex düğümün INFEASIBLE bayrağı kaldırmasını ister. Bugün düğüm bunu SAĞLAM
    biçimde YAPAMAZ (aşağıdaki teste bakınız), dolayısıyla doğru davranış
    sonlanmak ve çözemediğini bildirmektir. Sistemin cevabı yine de doğrudur:
    doğrulayıcı taşkını ve alt sınır ihlalini raporlar.
    """
    edges = [(u, v) for u in range(1, 5) for v in range(u + 1, 5)]
    weights = {i: 1 for i in range(1, 5)}
    g = validate.make_graph(edges, 1, weights)
    assert not bridge.capacity_feasible(g, set(weights))[0]
    for scheduler in ("sync", "async"):
        r = run(scheduler, edges, weights, 1)
        assert r.converged, f"{scheduler}: sonlanmadı"
        assert r.unresolved, f"{scheduler}: yerel onarımın pes ettiğini bildirmedi"
        assert r.infeasible and r.infeasible_reason == "counting_bound"
        rep = validate.validate(g, r.cover, r.owner)
        assert not rep.valid and {v.kind for v in rep.violations} >= {validate.OVERLOAD}


# --------------------------------------------------------------------------
# sayma tanığı: SAĞLAM ama TAM DEĞİL (ekip liderinin önerisi, ölçümle sınandı)
# --------------------------------------------------------------------------
def test_counting_witness_is_sound_by_construction():
    """|E(S)| > k|S| ise atama yoktur: S'in içindeki her kenarın sahibi S'in
    içindedir ve her düğüm en çok k kenar sahiplenir. Sayma kanıtı."""
    assert bbcvc.counting_witness(4, 6, 1)        # K4, k=1: 6 > 4
    assert not bbcvc.counting_witness(4, 6, 2)    # k=2: 6 <= 8
    assert bbcvc.counting_witness(16, 73, 4)      # ekip liderinin düğüm 58'i
    assert not bbcvc.counting_witness(16, 64, 4)  # tam sınırda: ateşlemez
    assert not bbcvc.counting_witness(1, 0, 1)


def test_counting_witness_fires_only_on_genuinely_infeasible_instances():
    """SAĞLAMLIK, çizge üzerinde doğrudan sınanır: tanık nerede ateşlerse akış
    çözücüsü de "uygun değil" demelidir. Tek istisna bile kanıtın yanlış
    uygulandığı anlamına gelir."""
    import collections
    checked = fired = 0
    for n, p, seed in ((10, 0.35, 1), (12, 0.30, 2), (14, 0.25, 3), (9, 0.45, 4)):
        rng = random.Random(seed)
        e = [(u, v) for u in range(1, n + 1) for v in range(u + 1, n + 1)
             if rng.random() < p]
        if not e:
            continue
        adj = collections.defaultdict(set)
        for u, v in e:
            adj[u].add(v)
            adj[v].add(u)
        for k in (1, 2, 3):
            g = validate.make_graph(e, k, {i: 1 for i in range(1, n + 1)})
            nodes = set(g.nodes)
            hit = False
            for v in nodes:
                clos = adj[v] | {v}
                m_in = sum(1 for a in clos for b in adj[a] if b in clos) // 2
                if bbcvc.counting_witness(len(clos), m_in, k):
                    hit = True
                    break
            checked += 1
            if hit:
                fired += 1
                assert not bridge.capacity_feasible(g, nodes)[0], (
                    f"SAĞLAMLIK İHLALİ n={n} k={k}: tanık ateşledi ama örnek uygun")
    assert fired > 0, "hiç ateşlemediyse test boştur"


def test_counting_witness_is_not_complete():
    """TAMLIK KAYITTA: tanığın susması uygunluk KANITLAMAZ, bu yüzden erken
    çıkıştır, karar yordamı değil.

    Ölçüm (580 örnek; UDG, G(n,p) ve klik-artı-kuyruk aileleri; n=10..35;
    k=1,2,3,4,6): sağlamlık ihlali 0/225, ama uygunsuz 254 örneğin yalnız 225'i
    yakalandı, yani %88,6. Ekip liderinin 30/30'u dar bir aileden gelen küçük
    örneklem; geniş ailede tanığın göremediği örnekler GERÇEKTEN vardır.

    Somut karşı örnek aşağıda: k=1, 10 düğüm, 12 kenar. Küresel sayım
    m > k*n ile uygunsuz (12 > 10), ama hiçbir KAPALI KOMŞULUK çelişki vermiyor.
    """
    # hiçbir N[v] çelişki vermeyen, ama küresel olarak uygunsuz bir örnek
    assert not bbcvc.counting_witness(4, 4, 1)      # en iyi yerel pay 0
    # küresel sayım aynı örneği yakalar: m > k*n
    n, m, k = 10, 12, 1
    assert m > k * n, "küresel sayım bu örneği yakalar, radius-1 yakalamaz"


def test_counting_witness_needs_information_the_wire_does_not_carry():
    """Tanık N[v]'nin İÇİNDEKİ kenar sayısını ister, yani komşularımın birbirine
    komşu olup olmadığını. Bugünkü HELLO bunu taşımıyor, dolayısıyla düğüm
    tanığı hesaplayamıyor ve `local_infeasibility_witness` "bilmiyorum" diyor.

    `None` ile `False` BİLEREK ayrı: `False` "tanık ateşlemedi", `None`
    "hesaplayacak bilgim yok". İkisini karıştırmak, az önce düzeltilen hatanın
    biçimidir — bilmemeyi bilmek sanmak.
    """
    import dataclasses
    fields = {f.name for f in dataclasses.fields(wire.Hello)}
    assert "mis_nbrs" in fields
    assert not (fields & {"nbr_set", "nbr_bloom", "induced_edges", "adj"}), (
        "Komşu bitişikliği taşıyıcısı gelmiş. KARAR (ekip lideri): taşıyıcıyı BU "
        "İŞ İÇİN eklemeyin -- HELLO'yu 13 B'den 13+2(1+d)'ye çıkarır (d=36'da "
        "87 B) ve HELLO iletimlerin yarısıdır; kazanç ise koşum düzeyindeki "
        "sayma sınırı varken yalnız-yerel 40 örnek. AMA başka bir gerekçeyle "
        "zaten geldiyse bağlamak neredeyse bedavadır: "
        "`local_infeasibility_witness` içine `_induced_edges`i doldurun.")
    r = run("sync")
    for node in r.nodes.values():
        assert node.local_infeasibility_witness() is None
    # Kanca ÇALIŞIR DURUMDA bekliyor: elle doldurulunca tanık hesaplanır. Bağlı
    # bir şey olmaması unutulmuşluk değil, ölçülmüş bir takas kararıdır.
    node = list(r.nodes.values())[0]
    node._induced_edges = 10 * node.k * (node.deg + 1)
    assert node.local_infeasibility_witness() is True
    node._induced_edges = 0
    assert node.local_infeasibility_witness() is False


# ==========================================================================
# 8. Mesaj boyutu: yoğunluktan BAĞIMSIZ (brief §5, G8)
# ==========================================================================
def test_hello_size_does_not_grow_with_degree():
    """Tam komşu listesi asla taşınmaz; büyüyebilen tek alan mis_nbrs'tir."""
    sizes = set()
    for deg in (1, 5, 20, 60, 200):
        h = wire.Hello(src=1, key=100, deg=min(deg, 255), role=Role.OUT,
                       phase=PH_OWN, load=0, epoch=0, mis_nbrs=())
        sizes.add(len(wire.encode(h)))
    assert sizes == {wire.hello_size(0)}, "HELLO boyu dereceyle değişiyor"
    cap = BbcvcParams().mis_nbrs_max
    assert cap == wire.MIS_NBRS_SOFT_MAX == 5, "varsayılan G8 sınırı"
    assert wire.hello_size(cap) <= 32
    assert wire.hello_size(cap) - wire.hello_size(0) == 2 * cap


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_measured_payload_is_bounded(scheduler):
    """Ölçülen en büyük yük, yoğunluk ne olursa olsun HELLO(5) sınırının altında."""
    cap = BbcvcParams().mis_nbrs_max
    caps = []
    for n, radius, k in ((10, 0.55, 6), (25, 0.40, 8)):
        # k bilerek BOL seçilmiştir: burada ölçülen şey YÜK BOYUTU, kapasite
        # onarımı değil. Dar k, kapasitesi uygunsuz bir örnekte bütün onarım
        # turlarını koşturur ve testi saniyelerce uzatır.
        edges, weights = _udg(n, radius, seed=5)
        r = run(scheduler, edges, weights, k)
        caps.append(r.max_payload)
        assert r.max_payload <= wire.hello_size(cap)
    assert max(caps) < 250


def test_node_never_transmits_a_full_neighbour_list():
    """Her yayın ya HELLO'dur (<= 23 B) ya da sabit boyutlu bir unicast'tir."""
    r = run("sync")
    assert r.max_payload <= wire.hello_size(BbcvcParams().mis_nbrs_max)
    for mt in r.by_type_tx:
        assert MsgType(mt) in (MsgType.HELLO, MsgType.LINK, MsgType.LINK_ACK,
                               MsgType.JOIN, MsgType.JOIN_ACK,
                               MsgType.HANDOVER, MsgType.HANDOVER_ACK,
                               MsgType.HANDOVER_NACK, MsgType.PUSH,
                               MsgType.PUSH_ACK, MsgType.PUSH_NACK)


# ==========================================================================
# 9. Sonlanma ve monotonluk
# ==========================================================================
def _role_trace(edges, weights, k, slots=200):
    """Slot slot koşup her düğümün rol/faz dizisini toplar."""
    ids = sorted(weights)
    net = simnet.SimNet(ids, edges, macs=bbcvc.macs_for(ids), rssi_range=None)
    nodes = bbcvc.build_nodes(net, weights, k, BbcvcParams())
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=weights)
    trace: Dict[int, List[Tuple[int, int]]] = {i: [] for i in ids}
    for slot in range(slots):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
        net.set_now(t0 + 200)
        for nid in ids:
            trace[nid].append((int(nodes[nid].role), nodes[nid].phase))
        if all(n.done for n in nodes.values()) and net.in_flight == 0:
            break
    return nodes, trace


def test_roles_are_monotone_and_run_terminates():
    """api I5: rol yalnız OUT -> {MIS, CONNECTOR, COVER} yönünde değişir ve bir
    kez değiştikten sonra bir daha değişmez. Faz da monotondur; tek istisna
    QUIET/DONE'dan OWN'a dönüştür ve o BİLEREK vardır (yeni iş çıkması)."""
    nodes, trace = _role_trace(EDGES, WEIGHTS, K)
    assert all(n.done for n in nodes.values()), "koşum sonlanmadı"
    assert all(n.epoch_bumps == 0 for n in nodes.values()), "kayıpsız kanalda epoch arttı"
    for nid, seq in trace.items():
        seen_non_out = None
        for role, _ in seq:
            if role != int(Role.OUT):
                if seen_non_out is None:
                    seen_non_out = role
                assert role == seen_non_out, f"düğüm {nid}: rol geri gitti"
        # faz, OWN ile kırpıldığında monotondur
        caps = [min(ph, PH_OWN) for _, ph in seq]
        assert caps == sorted(caps), f"düğüm {nid}: faz geri gitti"


def test_phases_are_visited_in_order():
    """Beş faz tek gövdededir ve sırayla geçilir (.tex "Tam durum makinesi")."""
    _, trace = _role_trace(EDGES, WEIGHTS, K)
    for nid, seq in trace.items():
        phases = sorted({min(ph, PH_DONE) for _, ph in seq})
        for p in (PH_MIS, PH_CONN, PH_COVER, PH_FORCED, PH_OWN, PH_QUIET, PH_DONE):
            assert p in phases, f"düğüm {nid} faz {p} atladı: {phases}"


# ==========================================================================
# 10. Muhasebe: belgenin 214 / 614 / 20 ve 74 / 194 sayıları
# ==========================================================================
def test_accounting_is_consistent():
    """Sayaçlar kendi içinde tutarlı: rx = yayınların derece toplamı + unicast."""
    r = run("sync")
    assert r.tx == sum(c.tx for c in r.outcome.counters_by_node.values())
    assert r.rx == sum(c.rx for c in r.outcome.counters_by_node.values())
    assert r.retx == 0, "kayıpsız kanalda yeniden gönderim olmamalı"
    assert r.bytes_tx > 0 and r.max_payload <= 250
    assert sum(r.by_type_tx.values()) == r.tx
    assert sum(r.by_phase_tx.values()) == r.tx


def test_phase_attribution_order_is_advance_then_transmit():
    """SEÇİM (bb-core'un ikinci tuzağı): ÖNCE faz ilerletilir, SONRA iletilir.

    Kuralın gözlemlenebilir biçimi: bir HELLO, YÜKÜNDE TAŞIDIĞI faza yazılır.
    "phase=5'e geçtim" diyen HELLO faz 5'e sayılır, faz 4'e değil. Aynı ilke
    unicast'lerde de geçerlidir: bir kuralın ürettiği unicast o kuralın fazına
    yazılır, çünkü faz yalnız `_step` içinde ve gönderimden ÖNCE ilerler.

    Test bunu muhasebe kancasından ölçer: `SimNet._account` hangi faz kovasına
    yazdığını bilir, yükün kendisi de fazı taşır; ikisi HER HELLO için aynı
    olmalıdır.
    """
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    nodes = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=WEIGHTS)

    seen: List[Tuple[int, int, int]] = []          # (nid, kova, yükteki faz)
    orig = net._account

    def spy(nid, payload, fanout):
        bucket = net._phase_of(nid)
        if wire.peek_type(payload) is MsgType.HELLO:
            seen.append((nid, bucket, wire.decode(payload).phase))
        orig(nid, payload, fanout)

    net._account = spy
    sc.run(BUDGET_MS)

    assert seen, "hiç HELLO sayılmadı"
    for nid, bucket, carried in seen:
        assert bucket == carried, (
            f"düğüm {nid}: HELLO faz {carried} taşıyor ama faz {bucket} "
            f"kovasına yazıldı; gönderim sırası bozulmuş")
    buckets = {b for _, b, _ in seen}
    assert PH_OWN in buckets and PH_MIS in buckets, buckets


def test_document_counter_comparison_sync():
    """.tex Tablo "Çalışan örnekte sayılar": 214 tx / 614 rx / 20 slot.

    ÖLÇÜLEN DEĞER BAŞKADIR ve AYARLANMAMIŞTIR. Farkın üç kaynağı vardır:
      1. Belge Faz 0'a TEK slot verir; gerçek bootstrap (kararlılık kapısı
         T_stab = 3 periyot + LINK el sıkışması) 6 slot harcar.
      2. Belge yerel bariyere slot ayırmaz; her fazın mis_nbrs/rol bilgisinin
         bir tur yayılması gerekir.
      3. Belge, 8'in başarısız PUSH zincirini 6 slot sayar; gerçekte zincir
         hem ileri hem geri gider ve derinleşerek yeniden denenir.
    Test sayıyı SABİTLER ki bir gerileme fark edilsin.
    """
    r = run("sync")
    # RAISED DELIBERATELY, 482 -> 507 tx and 1294 -> 1367 rx, slots unchanged at
    # 53. A DONE node used to fall silent the moment IT was done; it now keeps
    # its periodic beacon until every neighbour has also reached PH_DONE, which
    # is what stops one lost frame from deadlocking termination for the whole
    # network (see `_barrier_closed`). The extra traffic is entirely post-
    # convergence beaconing and buys the barrier: on the run that exposed the
    # defect the number of nodes left hanging below PH_DONE goes from 17 to 0
    # and the run turns from truncated into solved at one per cent loss.
    # UPDATED: the quiet phase now repairs a lost DONE HELLO. A node that has
    # finished answers a neighbour which is still beaconing at PH_DONE, once,
    # on the SECOND such beacon after its own DONE HELLO. That neighbour could
    # only still be beaconing because it missed mine, and without the answer it
    # beacons for ever while I stay silent, so the network never goes quiet even
    # though every node has finished. Price on this example: four HELLOs, tx 507
    # to 510 and rx 1367 to 1373, with SLOTS UNCHANGED at 53 and the emulator
    # still matching the simulator exactly.
    assert (r.slots, r.tx, r.rx) == (53, 510, 1373)
    # Belgenin sayıları, karşılaştırma için:
    assert (20, 214, 614) != (r.slots, r.tx, r.rx)
    assert r.tx / 214 < 2.5 and r.rx / 614 < 2.5
    # Kırılım: belgenin HİÇ SAYMADIĞI iki kalem burada gerçek maliyettir.
    link = (r.by_type_tx.get(int(MsgType.LINK), 0)
            + r.by_type_tx.get(int(MsgType.LINK_ACK), 0))
    assert link == 60, "çift yön doğrulaması 15 kenar x 2 yön x 2 mesaj"
    boot = r.by_phase_tx.get(0, 0)
    assert boot == 120, "bootstrap fazına yazılan iletim (belge bunu 1 slot sayar)"
    algo_unicast = r.tx - link - r.hello_change_tx - r.hello_periodic_tx
    assert algo_unicast == 40, "belge 14 unicast sayar; fark Faz 4 denemelerinde"


def test_document_counter_comparison_async():
    """.tex: asenkron 74 tx / 194 rx, "canlılık HELLO'ları hariç".

    Bizim düğümümüz canlılık HELLO'sunu KESMEZ (kesmek uyku demektir, brief
    §3.6 bu aşamada yasaklar), bu yüzden toplam sayı belgeninkinden büyüktür.
    Belgenin dışladığı payı görebilmek için değişiklik-güdümlü ve periyodik
    HELLO'lar ayrı sayılmaktadır.
    """
    r = run("async")
    # Same deliberate rise as the synchronous pin above, 368 -> 376 tx and
    # 932 -> 956 rx: a DONE node keeps beaconing until the barrier has closed.
    # UPDATED: the quiet phase now repairs a lost DONE HELLO. A node that has
    # finished answers a neighbour which is still beaconing at PH_DONE, once,
    # on the SECOND such beacon after its own DONE HELLO. That neighbour could
    # only still be beaconing because it missed mine, and without the answer it
    # beacons for ever while I stay silent, so the network never goes quiet even
    # though every node has finished. Price on this example: four HELLOs, tx 507
    # to 510 and rx 1367 to 1373, with SLOTS UNCHANGED at 53 and the emulator
    # still matching the simulator exactly.
    assert (r.tx, r.rx) == (379, 962)
    assert r.hello_periodic_tx + r.hello_change_tx <= r.tx
    # Belgenin dışladığı canlılık payı ayrı sayılır: bir HELLO ancak DURUM
    # DEĞİŞİKLİĞİ taşıyorsa "olay HELLO'su"dur.
    # The liveness share rises 165 -> 173 -> 176 while the event share stays at
    # 109 through both fixes. That invariance is the point: the barrier and the
    # lost-DONE repair add only PERIODIC beacons after DONE, never a new state
    # change. The repair was first written through `_hello_dirty`, which pushed
    # the event share to 113 and made the split claim a state change that never
    # happened; sending it as the liveness beacon it actually is restores 109.
    assert (r.hello_change_tx, r.hello_periodic_tx) == (109, 176)
    link = (r.by_type_tx.get(int(MsgType.LINK), 0)
            + r.by_type_tx.get(int(MsgType.LINK_ACK), 0))
    doc_like = r.hello_change_tx + (r.tx - link - r.hello_change_tx
                                    - r.hello_periodic_tx)
    assert doc_like == 143, "belgenin 74'üne karşılık gelen kalem"
    # asenkron, senkrondan az iletim yapar: DONE düğümler erken susar
    assert r.tx < run("sync").tx


def test_async_is_cheaper_than_sync():
    a, b = run("sync"), run("async")
    assert b.tx < a.tx and b.rx < a.rx


# ==========================================================================
# 11. İki zamanlayıcı, tek düğüm kodu
# ==========================================================================
def _owner_diff_is_flexible_only(a, b, edges, k) -> List[Tuple[int, int]]:
    """Sahiplik farkının YALNIZ esnek kenarlarda olduğunu doğrular.

    Zorunlu kenarın (bir ucu örtü dışında) başka sahibi OLAMAZ; orada bir fark
    Faz 2/3'ün ayrıştığı anlamına gelir ve bu bir BULGUDUR. Esnek kenardaki
    fark ise brief §3.2'nin beklediği şeydir.
    """
    cov = set(a.cover)
    diff = [e for e in sorted(set(a.owner) | set(b.owner))
            if a.owner.get(e) != b.owner.get(e)]
    for (u, v) in diff:
        assert u in cov and v in cov, (
            f"ZORUNLU kenar {(u, v)} sahibi ayrıştı: Faz 4'ten ÖNCE bir fark var")
    return diff


def test_sync_and_async_agree_on_the_worked_example():
    """brief §3.2: Faz 0-3 belirlenimci anahtarla yazıldığından aynı C'ye
    yakınsamalı; fark ANCAK Faz 4 sahiplikte çıkabilir.

    ÖLÇÜM: örtü, roller ve omurga birebir aynıdır; sahiplik iki esnek kenarda
    ayrılmaktadır ((4,5)/(4,6)/(5,6) üçlüsünün yönlendirmesi). İkisi de
    geçerlidir ve toplam ağırlık aynıdır. Beklentiyle uyumlu, gizlenecek bir
    şey yok.
    """
    a, b = run("sync"), run("async")
    assert a.cover == b.cover
    assert {nid: n.role for nid, n in a.nodes.items()} == \
           {nid: n.role for nid, n in b.nodes.items()}
    assert a.total_weight == b.total_weight
    diff = _owner_diff_is_flexible_only(a, b, EDGES, K)
    assert len(diff) <= 4, f"beklenenden çok sahiplik farkı: {diff}"


def test_node_cannot_tell_which_scheduler_runs_it():
    """Düğüm GÖVDESİNDE kip ayrımı yoktur; zamanlayıcı adı her ikisinde de aynı.

    Denetim `BbcvcNode` sınıfının kaynağı üzerindedir: modül başlığı iki
    zamanlayıcıyı ADIYLA anlatır (anlatmalıdır da), ama gövde onları göremez.
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(BbcvcNode))
    for node in ast.walk(tree):                      # belge dizgilerini at
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            body.pop(0)
    code = ast.unparse(tree)                         # yorumlar da düşer
    for forbidden in ("SyncScheduler", "AsyncScheduler", "tau_ms", "tick_ms",
                      "slot", "scheduler"):
        assert forbidden not in code, f"düğüm gövdesi kipi görüyor: {forbidden}"
    # Zamanlayıcının verdiği tek ad; düğüm bu adı bile ayırt etmeye çalışmaz.
    assert sched.TIMER_TICK == "tick"


# ==========================================================================
# 12. Belirlenimcilik ve kayıplı kanal
# ==========================================================================
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_determinism(scheduler):
    a = run(scheduler)
    b = run(scheduler)
    assert (a.cover, a.owner, a.tx, a.rx, a.slots, a.t_conv_ms) == \
           (b.cover, b.owner, b.tx, b.rx, b.slots, b.t_conv_ms)


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_lossy_channel_produces_retx_and_still_validates(scheduler):
    """brief §3.4: kayıp gerçektir. `retx` HAREKET ETMELİDİR (bb-core'un birinci
    tuzağı: log("retx") unutulursa sayaç temiz görünür ve yanlıştır)."""
    p = BbcvcParams(t_hello_ms=200, ack_max_attempts=5, link_max_attempts=5)
    r = run(scheduler, loss=0.15, seed=3, params=p, max_ms=1_200_000)
    assert r.retx > 0, "%15 kayıpta hiç yeniden gönderim sayılmadı"
    if r.converged and not r.infeasible:
        rep = validate.validate(graph_of(), r.cover, r.owner)
        assert rep.valid, rep.summary()


def test_retx_counter_is_wired_to_the_log():
    """Sözleşme denetimi: sayaç YALNIZ log("retx") ile artar (api.Counters)."""
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    before = net.counters[1].retx
    net.port(1).log("retx", n=3)
    assert net.counters[1].retx == before + 3


# ==========================================================================
# 13. Özellik testleri: rastgele birim disk çizgeleri
# ==========================================================================
def _udg(n: int, radius: float, seed: int):
    """Bağlı birim disk çizgesi üret. Çizge YALNIZ testin elindedir."""
    rng = random.Random(seed * 7919 + n)
    for _ in range(500):
        pts = {i: (rng.random(), rng.random()) for i in range(1, n + 1)}
        edges = [(u, v) for u in pts for v in pts
                 if u < v and math.dist(pts[u], pts[v]) <= radius]
        adj = {i: set() for i in pts}
        for u, v in edges:
            adj[u].add(v)
            adj[v].add(u)
        seen, stack = {1}, [1]
        while stack:
            x = stack.pop()
            for y in adj[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        if len(seen) == n and edges:
            weights = {i: rng.randint(1, 9) for i in range(1, n + 1)}
            return edges, weights
    pytest.skip(f"n={n}, r={radius} için bağlı UDG üretilemedi")


#: Varsayılan matris KASITLI OLARAK küçüktür. Ölçüm: n=60 hücreleri tek başına
#: dosyanın 134 saniyesinin 100'ünü yiyordu ve `pytest ccvc/bb/` alfabetik
#: sırada bu dosyayla başladığı için bütün paketi kilitliyordu. Ağır hücreler
#: kaybolmadı, kapının arkasına alındı:
#:     BBCVC_SLOW=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_bbcvc.py
#: Bu bir kapsam kaybıdır ve bilerek yapılmıştır: n=60'ta doğrulanan şey
#: n=30'da da doğrulanmaktadır, değişen yalnız ölçektir.
SLOW = os.environ.get("BBCVC_SLOW") == "1"

_UDG_SHAPES = [(8, 0.50), (15, 0.38), (30, 0.28)]
if SLOW:
    _UDG_SHAPES.append((60, 0.20))

UDG_CASES = [(n, radius, seed) for n, radius in _UDG_SHAPES for seed in (1, 2)]


@pytest.mark.parametrize("n,radius,seed", UDG_CASES)
@pytest.mark.parametrize("k", [2, 3, 5])
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_property_random_udg(n, radius, seed, k, scheduler):
    """Her koşum ya SIFIR İHLALLE geçer ya da kesin çözücü de uygunsuz der."""
    edges, weights = _udg(n, radius, seed)
    g = validate.make_graph(edges, k, weights)
    r = run(scheduler, edges, weights, k, max_ms=1_500_000)
    assert r.converged, f"n={n} k={k} {scheduler}: sükûnete ermedi"
    if r.infeasible:
        assert not bridge.capacity_feasible(g, set(weights))[0], (
            f"YANLIŞ UYGUNSUZLUK n={n} k={k} {scheduler}: C=V ile uygun atama var")
        return
    rep = validate.validate(g, r.cover, r.owner)
    if r.unresolved:
        # "Çözemedim". İKİ AYRI durum buraya düşer ve ayırt edilmeleri gerekir,
        # çünkü biri algoritmanın kusuru, diğeri örneğin gerçeği.
        kinds = {v.kind for v in rep.violations}
        capacity_family = {validate.OVERLOAD, validate.FORCED_OVERLOAD,
                           validate.LOWER_BOUND}
        if bridge.capacity_feasible(g, set(weights))[0]:
            # Örnek UYGUN: yerel onarım yetmedi, bu bir kalite kaybıdır.
            # Alt sınır ihlali burada BEKLENMEZ; çıkarsa örtü seçimi bozulmuş
            # demektir, yalnız yönlendirme değil.
            assert kinds <= {validate.OVERLOAD, validate.FORCED_OVERLOAD}, (
                f"n={n} k={k} {scheduler}: uygun örnekte onarım başarısızlığı "
                f"kapasitenin dışına taştı: {sorted(kinds)}")
        else:
            # Örnek GERÇEKTEN uygunsuz: hiçbir örtü geçerli atama kabul etmez,
            # dolayısıyla |C| >= ceil(m/k) alt sınırı da sağlanamaz. Bunu
            # algoritmaya yazmak, çözümü olmayan bir soruyu çözememeyi kusur
            # saymak olurdu.
            assert kinds <= capacity_family, (
                f"n={n} k={k} {scheduler}: uygunsuz örnekte kapasite dışı "
                f"ihlal: {sorted(kinds)}")
        # Her iki durumda da örtü ve bağlılık DOĞRU olmak zorundadır.
        assert rep.vertex_cover and rep.connected
        return
    assert rep.valid, f"n={n} k={k} {scheduler}: {rep.summary()}"
    assert len(r.owner) == len(edges)
    # yapısal olgular
    assert validate.check_g1(g, r.cover) == []
    assert validate.check_g4(g, r.cover) == []
    assert validate.check_g6(g, r.cover) == []
    b = backbone(r)
    assert validate.check_g2(g, b) == []
    assert len(validate.cover_components(g, b)) == 1
    # G8: birim diskte MIS komşusu sayısı <= 5, yani HELLO sabit boyutludur
    assert r.max_payload <= wire.hello_size(BbcvcParams().mis_nbrs_max)


@pytest.mark.parametrize("n,radius,seed", UDG_CASES[:4])
@pytest.mark.parametrize("k", [3])
def test_property_sync_async_same_cover(n, radius, seed, k):
    """brief §3.2 beklentisi: Faz 0-3 aynı sonucu vermeli, fark yalnız Faz 4'te.

    Örtü farkı ÇIKARSA bu bir BULGUDUR ve gizlenmez; testin mesajı farkı
    hangi düğümlerde olduğunu yazar.
    """
    edges, weights = _udg(n, radius, seed)
    a = run("sync", edges, weights, k, max_ms=1_500_000)
    b = run("async", edges, weights, k, max_ms=1_500_000)
    if a.infeasible or b.infeasible or a.unresolved or b.unresolved:
        pytest.skip("uygunsuz ya da yerel onarımın yetmediği örnek")
    diff = set(a.cover) ^ set(b.cover)
    assert not diff, f"n={n} seed={seed}: örtü Faz 4'ten ÖNCE ayrıştı: {sorted(diff)}"


@pytest.mark.parametrize("n,radius,seed", UDG_CASES[:4])
def test_property_mis_is_maximal_independent(n, radius, seed):
    edges, weights = _udg(n, radius, seed)
    r = run("sync", edges, weights, 3, max_ms=1_500_000)
    mis = {nid for nid, node in r.nodes.items() if node.role == Role.MIS}
    for u, v in edges:
        assert not (u in mis and v in mis)
    for v in weights:
        assert v in mis or any(u in mis for u in r.net.neighbors(v))


@pytest.mark.parametrize("n,radius,seed", UDG_CASES[:4])
def test_property_mis_nbrs_stays_within_g8(n, radius, seed):
    """brief G8: birim disk çizgesinde bir düğümün en çok 5 bağımsız komşusu
    vardır; bu yüzden hiçbir HELLO kırpılmak zorunda kalmamalıdır."""
    edges, weights = _udg(n, radius, seed)
    # Koşumun kendisi kapıdır: G8 aşılsaydı `_hello_payload` YÜKSELİRDİ ve bu
    # test hata alırdı. Sessiz bir kırpma bayrağı aramıyoruz, çünkü kırpma yok.
    r = run("sync", edges, weights, 3, max_ms=1_500_000)
    cap = BbcvcParams().mis_nbrs_max
    for node in r.nodes.values():
        assert len(node.mis_nbrs()) <= cap


# ==========================================================================
# 14. Faz 5b: omurga convergecast (ÖLÇÜM; karar vermez)
# ==========================================================================
def tree_params() -> BbcvcParams:
    return BbcvcParams(enable_tree=True)


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_phase5b_never_changes_the_answer(scheduler):
    """brief §4/Faz 5b ve §6 (MIS-Connector-TreeAgg): toplama ÖLÇÜM amaçlıdır.

    Aynı topolojide 5b'li ve 5b'siz koşum AYNI örtüyü ve AYNI sahipliği
    vermelidir; değişen yalnız mesaj sayısıdır.
    """
    base = run(scheduler)
    tree = run(scheduler, params=tree_params())
    assert base.cover == tree.cover
    assert base.owner == tree.owner
    assert base.total_weight == tree.total_weight
    assert tree.tx > base.tx, "5b hiç mesaj üretmemiş"


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_phase5b_root_is_smallest_id_mis(scheduler):
    """Kök EN KÜÇÜK KİMLİKLİ MIS düğümüdür; düğüm bunu min-kimlik dedikodusuyla
    öğrenir, kimse ona söylemez."""
    r = run(scheduler, params=tree_params())
    mis = sorted(nid for nid, n in r.nodes.items() if n.role == Role.MIS)
    assert r.tree_root == min(mis) == 2
    bb = [n for n in r.nodes.values() if n.role.in_backbone]
    assert all(n.tree_root == r.tree_root for n in bb), "kökte anlaşma yok"
    assert sum(1 for n in bb if n.tree_parent is None) == 1, "birden çok kök"
    assert all(n.tree_finished for n in bb)


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_phase5b_convergecast_collects_the_backbone(scheduler):
    """Kökte toplanan alt ağaç boyutu ve ağırlığı, omurganın gerçeğiyle eşleşir."""
    r = run(scheduler, params=tree_params())
    bb = backbone(r)
    root = [n for n in r.nodes.values() if n.role.in_backbone and n.tree_parent is None][0]
    assert root.tree_subtree == len(bb) == 5
    assert round(root.tree_weight_fp / 65536.0, 3) == sum(WEIGHTS[v] for v in bb) == 12


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_phase5b_uses_backbone_only_and_is_cheaper_than_broadcast(scheduler):
    """.tex: toplama 9 unicast, aynı bilgiyi yayınla toplamak 30 teslim.

    ÖLÇÜM: STABLE + FINISH sayısı |B| mertebesindedir ve 2m = 30'un altındadır.
    TREE (kök seçimi dedikodusu) belgede ayrı sayılmamıştır; burada ayrı
    raporlanır, çünkü kökü bulmanın bedeli gerçektir.
    """
    r = run(scheduler, params=tree_params())
    stable = r.by_type_tx.get(int(MsgType.STABLE), 0)
    finish = r.by_type_tx.get(int(MsgType.FINISH), 0)
    tree = r.by_type_tx.get(int(MsgType.TREE), 0)
    assert finish == 4 == len(backbone(r)) - 1
    assert stable + finish < 2 * len(EDGES), "toplama yayından pahalı"
    assert tree > 0
    # 5b yalnız omurgada konuşur: omurga dışı düğüm TREE/STABLE/FINISH göndermez
    for nid, node in r.nodes.items():
        if node.role.in_backbone:
            continue
        c = r.outcome.counters_by_node[nid]
        for mt in (MsgType.TREE, MsgType.STABLE, MsgType.FINISH):
            assert c.by_type_tx.get(int(mt), 0) == 0, f"düğüm {nid} omurga dışı"


def test_phase5b_terminates_on_unit_graphs():
    for name in sorted(UNIT_GRAPHS):
        edges, weights, k = UNIT_GRAPHS[name]
        r = run("sync", edges, weights, k, params=tree_params())
        assert r.converged, f"{name}: 5b ile sükûnete ermedi"
        base = run("sync", edges, weights, k)
        assert r.cover == base.cover and r.owner == base.owner, name


# ==========================================================================
# 15. Yerel onarımın yetmediği örnek: UYGUNSUZLUKTAN AYRI raporlanır
# ==========================================================================
def test_relayed_escalation_resolves_what_local_escalation_could_not():
    """ÖLÇÜLMÜŞ BULGU ve ONARIMI (n=100, m=275, k=4 üzerinde teşhis edildi).

    .tex'in eskalasyonu "dışarıdaki en küçük anahtarlı komşuma JOIN" der ve bu,
    taşan düğümün örtünün SINIRINDA olduğunu varsayar. Ölçüm bunun tersini
    gösterdi: çözülemeyen koşumlarda taşan düğümlerin TAMAMININ (3/3) örtü dışı
    komşusu YOKTU, yani örtüyü büyüten tek mekanizma tam ihtiyaç duyulduğu anda
    devre dışıydı. Akış çözücüsü aynı koşumlarda BB-CVC'nin KENDİ örtüsü için
    "uygun atama yok" diyordu, yani örtü gerçekten yetersizdi.

    Kademe 3b bunu bir atlamalık bilgiyle çözer: HELLO'nun `load` alanı F'tir,
    dolayısıyla F(u) > 0 olan komşu u'nun örtü dışı komşusu olduğu görülür; u'ya
    "benim adıma eskale et" denir, u kendi dış komşusunu davet eder, F(u) azalır,
    bütçesi açılır ve devri kabul edebilir hâle gelir.

    Bu örnek (n=15, k=3) eskiden `unresolved` ile bitiyordu ve bu test onu öyle
    SABİTLİYORDU; artık geçerli bitiyor.
    """
    edges, weights = _udg(15, 0.38, 2)
    g = validate.make_graph(edges, 3, weights)
    assert bridge.capacity_feasible(g, set(weights))[0], "örnek gerçekten uygun"
    for scheduler in ("sync", "async"):
        r = run(scheduler, edges, weights, 3, max_ms=1_500_000)
        assert r.converged and not r.unresolved and not r.infeasible
        rep = validate.validate(g, r.cover, r.owner)
        assert rep.valid, f"{scheduler}: {rep.summary()}"
        relays = [x for x in r.net.log_records if x["event"] == "relay_escalate"]
        assert relays, f"{scheduler}: kademe 3b hiç ateşlemedi, örnek başka yolla çözüldü"
        # ve seçilen örtü için GERÇEKTEN uygun bir atama vardır
        assert bridge.capacity_feasible(g, set(r.cover))[0]


def test_relay_only_targets_neighbours_that_can_actually_escalate():
    """Vekil, dış komşusu OLAN bir komşu olmalı. Bu bilgi telde vardır: HELLO'nun
    `load` alanı F'tir ve F(u) > 0 tam olarak "u'nun örtü dışı komşusu var"
    demektir. F = 0 olan bir komşuya vekâlet vermek boşa mesajdır."""
    edges, weights = _udg(15, 0.38, 2)
    r = run("sync", edges, weights, 3, max_ms=1_500_000)
    relays = [x for x in r.net.log_records if x["event"] == "relay_escalate"]
    assert relays
    for rec in relays:
        # vekil, KENDİ dış komşusunu davet etmiş olmalı
        agent = r.nodes[rec["nid"]]
        assert rec["to"] in r.net.neighbors(rec["nid"]), "vekil komşusunu davet etmedi"
        assert (rec["to"], bbcvc.JOIN_ESCALATE) in agent._join_sent


def test_push_deepening_is_off_by_default():
    """Derinleştirme false-INFEASIBLE için eklenmişti; ölçüm gerekçeyi çürüttü.

    Yanlış uygunsuzluğu kapatan şey "C = V tanığı"dır: property matrisi
    push_ttl_max=3 ile de sıfır yanlış uygunsuzluk verir. Bedeli ise ağırdır,
    çünkü PUSH bir YOL değil AĞAÇ olarak yayılır ve derinlik dallanmayı çarpar.
    Ölçüm (n=100, m=275, k=4, tohum 43): D<=3 -> 111 slot ve GEÇERLİ;
    D<=8 -> 1223 slot ve GEÇERSİZ. Derinleştirme yalnız pahalı değil, geçerli
    cevabı da kaybettiriyordu.
    """
    p = BbcvcParams()
    assert p.push_ttl_max == p.push_ttl == 3, "derinleştirme varsayılanda kapalı"


def test_unresolved_still_terminates_the_run():
    """`unresolved` artık ürettiğim hiçbir örnekte gözlenmiyor, ama SİLİNEMEZ:
    sonlanmayı garanti eden şey odur. Yerel onarım bir gün yine yetmezse düğüm
    sükûnete erebilmeli ki koşum assın değil, dursun ve doğrulayıcı taşkını
    raporlasın. Bayrağın bu görevi doğrudan sınanır.
    """
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    nodes = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())
    node = nodes[2]
    node.phase = PH_OWN
    node.owned = {(1, 2), (2, 3), (2, 4)}          # 3 > k = 2, taşkın
    node._last_change_ms = 0
    node._last_fp = node._fingerprint()
    net.set_now(BbcvcParams().t_quiet_ms + 1)
    node._quiescence(net.now_ms(), [])
    assert node.phase == PH_OWN, "taşkın düğüm bayraksız sükûnete ermemeli"
    node.unresolved = True
    node._quiescence(net.now_ms(), [])
    # Komşu listesi boş olduğundan "bütün komşular >= QUIET" boşuna doğrudur ve
    # düğüm aynı çağrıda DONE'a kadar gider; sınanan şey sükûnete GİREBİLMESİ.
    assert node.phase >= PH_QUIET, "`unresolved` sükûnete izin vermeli"
    assert node.done, "koşum sonlanamaz: taşkın düğüm hiç DONE demiyor"



# ==========================================================================
# 16. Sessiz bozulma yolları: BAŞARISIZLIĞIN GERÇEKTEN OLDUĞUNU assert et
# ==========================================================================
# Ekip liderinin bugün üç ayrı hata yakalayan kalıbı: sınırın tuttuğunu değil,
# İHLALİN YÜKSELDİĞİNİ sına. Aşağıdaki üç yolun her biri sistemi çalışır ve
# temiz sayılar üretir hâlde bırakabilirdi.

def _heavy_star(leaves: int):
    """Merkezi AĞIR bir yıldız: yapraklar küçük anahtarlı olduğundan hepsi MIS
    olur ve merkezin mis_nbrs'i yaprak sayısı kadar olur. G8'i kasıtlı kırar."""
    edges = [(1, i) for i in range(2, 2 + leaves)]
    weights = {1: 100}
    weights.update({i: 1 for i in range(2, 2 + leaves)})
    return edges, weights


def test_mis_nbrs_overflow_raises_instead_of_truncating():
    """Altı MIS komşusu TELDE sorunsuz gider (25 B, tam tur). Sınırı uygulamak
    üreticinin işidir ve o üretici Faz 1'dir. Kırpma OLMAMALI, hata OLMALI."""
    # önce telin gerçekten kırpmadığını göster
    big = wire.Hello(src=1, key=100, deg=6, role=Role.MIS, phase=PH_OWN,
                     load=0, epoch=0, mis_nbrs=(2, 3, 4, 5, 6, 7))
    assert wire.decode(wire.encode(big)).mis_nbrs == (2, 3, 4, 5, 6, 7)
    assert len(wire.encode(big)) == wire.hello_size(6) == 25

    edges, weights = _heavy_star(6)
    with pytest.raises(ValueError, match="mis_nbrs"):
        run("sync", edges, weights, 3, max_ms=400_000)


def test_mis_nbrs_cap_is_a_parameter_not_the_literal_five():
    """G8 bir BİRİM DİSK teoremidir ve kıyas kümesinde geçerli değildir
    (ölçüm: Dagdeviren n=200'de her düğüm 5'i aşıyor, en büyüğü 17). Sabit 5
    dayatmak BB-CVC'yi o kümede hiç koşturamaz hâle getirirdi."""
    edges, weights = _heavy_star(6)
    r = run("sync", edges, weights, 3, params=BbcvcParams(mis_nbrs_max=6),
            max_ms=400_000)
    assert r.converged
    assert r.nodes[1].mis_nbrs() == (2, 3, 4, 5, 6, 7)
    assert r.max_payload == wire.hello_size(6) == 25
    rep = validate.validate(validate.make_graph(edges, 3, weights), r.cover, r.owner)
    assert rep.valid, rep.summary()
    # HELLO artık yoğunlukla BÜYÜR; brief §5'in savı bu kipte geçerli değildir
    assert r.max_payload > wire.hello_size(BbcvcParams().mis_nbrs_max)


def test_neighbour_table_overflow_invalidates_the_run():
    """Kırpılmış tablo -> yanlış derece -> yanlış anahtar -> yanlış MIS sırası.
    Sonuç sessizce yanlış olur ve doğrusundan ayırt edilemez. `run_bbcvc`
    RAPORLAMAYI REDDETMELİ."""
    # Kapı koşum BİTTİKTEN sonra işler, bu yüzden bütçeyi kısa tutmak yeter:
    # sınanan şey yakınsama değil, RAPORLAMANIN REDDEDİLMESİ.
    with pytest.raises(RunInvalid, match="raporlanamaz"):
        run("sync", params=BbcvcParams(nbr_table_max=2), max_ms=40_000)
    # sınır bağlayıcı değilken aynı koşum sorunsuz
    ok = run("sync", params=BbcvcParams(nbr_table_max=64))
    assert ok.converged and all(n.table_overflow == 0 for n in ok.nodes.values())


def test_no_float_ever_reaches_a_key():
    """Sabit nokta disiplini: 16.16 anahtarın float'a düşmesi hassasiyet kaybı
    değil ÇÖKÜŞTÜR (1.67 -> telde 1 -> geri 0.00002) ve MIS sıralaması tam da
    o değere bakar. Düğüm anahtarı yalnız api.key_of'tan alır ve üzerinde
    kayan noktalı aritmetik yapmaz."""
    import ast
    import inspect
    r = run("sync")
    for node in r.nodes.values():
        assert isinstance(node.key_fp, int) and not isinstance(node.key_fp, bool)
        for nbr in node._nbrs_active():
            assert isinstance(nbr.key, int) and not isinstance(nbr.key, bool)
    # karar yolunda `key_value()` (float, yalnız rapor için) KULLANILMAZ
    tree = ast.parse(inspect.getsource(BbcvcNode))
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute):
            assert n.attr != "key_value", "karar yolunda float anahtar"
    # üretici tarafı float'ı reddeder
    node = list(r.nodes.values())[0]
    node.key = (1.67, node.nid)
    with pytest.raises(TypeError, match="sabit nokta"):
        node._hello_payload(())


def test_every_edge_has_exactly_one_owner_or_the_run_is_rejected():
    """Sessizce düşen bir kenar, başarılı bir atamayla AYNI görünür. Doğrulayıcı
    onu `bad_owner` olarak yakalamak ZORUNDA; testin yakaladığını test et."""
    r = run("sync")
    g = graph_of()
    assert validate.validate(g, r.cover, r.owner).valid
    # bir kenarı düşür: doğrulayıcı sessiz kalmamalı
    crippled = dict(r.owner)
    dropped = sorted(crippled)[0]
    del crippled[dropped]
    rep = validate.validate(g, r.cover, crippled)
    assert not rep.valid
    assert any(v.kind == validate.BAD_OWNER for v in rep.violations)
    # iki sahipli kenar da yakalanmalı
    doubled = list(r.owner.items()) + [(dropped, [x for x in dropped
                                                 if x != r.owner[dropped]][0])]
    rep2 = validate.validate(g, r.cover, doubled)
    assert not rep2.valid


# ==========================================================================
# 17. Saat tabanı: duvar saati altında kapı ilk tıkta AÇILMAMALI
# ==========================================================================
# bb-mnwifi'nin bulgusu: `BbcvcNode.on_timer` bilerek ezilmiş ve `super()`
# çağırmıyor, dolayısıyla `BootstrapNode.on_timer`ın saat tabanını kuran
# satırları BU YOLDA hiç koşmuyordu. BB-CVC eski hatayı sergilemiyordu ama
# gerekçesi tesadüfîydi ("çift yönlü küme değişti" satırı tabanı yan etki
# olarak kuruyordu). Aşağıdaki testler değişmezin SÖYLENEREK sağlandığını
# sınar ve iki yönde birden kapan: kapı erken açılırsa da, hiç açılmazsa da.

WALL_MS = 1_700_000_000_000      # gerçek bir duvar saati değeri, ~2023
TAU_MS = 200


def _wall_clock_pair(edges, weights, k=2, ticks=1, params=None):
    """İki düğümü DUVAR SAATİ altında `ticks` tık koştur ve düğümleri döndür."""
    ids = sorted(weights)
    net = simnet.SimNet(ids, edges, macs=bbcvc.macs_for(ids), rssi_range=None)
    nodes = bbcvc.build_nodes(net, weights, k, params or BbcvcParams())
    for nid, node in nodes.items():
        net.attach(nid, node)
    for t in range(ticks):
        now = WALL_MS + t * TAU_MS
        net.set_now(now)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sorted(nodes):
            net.set_now(now)
            nodes[nid].on_timer(sched.TIMER_TICK)
    return net, nodes


def test_clock_baseline_is_established_on_the_first_tick():
    """İLK YARI: taban ilk tıkta kurulur ve kapı o tıkta AÇILMAZ.

    Sıfırdan başlatılan bir zaman alanı duvar saatinde `now - 0` ~ 1.7e12 ms
    verir; kararlılık kapısı anında açılır ve her düğüm deg=0 ile anahtarını
    dondurur, yani kapı tam olarak var olma nedeninin tersini yapar.
    """
    weights = {1: 5, 2: 3}
    _, nodes = _wall_clock_pair([(1, 2)], weights, ticks=1)
    for nid, node in nodes.items():
        assert node._t0_ms == WALL_MS, f"{nid}: saat tabanı kurulmadı"
        assert node.stable_since_ms == WALL_MS, f"{nid}: pencere kurulmadı"
        assert node._last_change_ms == WALL_MS
        assert node.key is None, f"{nid}: anahtar İLK TIKTA donduruldu"
        assert node.deg is None, f"{nid}: derece İLK TIKTA donduruldu"
        assert node.phase == 0


def test_clock_baseline_still_lets_the_gate_open_afterwards():
    """İKİNCİ YARI: kapı DOĞRU ZAMANDA açılır ve DOĞRU dereceyle dondurur.

    Bu yarı olmadan test boş olurdu: kapıyı kalıcı olarak kilitleyen bir
    "düzeltme" de ilk yarıyı geçerdi. Tek düğümlü yalıtık bir kurguda da boş
    olurdu, çünkü o düğüm hiç çift yönlü komşu edinmez ve pencere hiç kurulmaz;
    bu yüzden kurgu İKİ DÜĞÜMLÜ ve gerçekten bir kenarı var.
    """
    from ccvc.bb.api import key_of
    weights = {1: 5, 2: 3}
    net, nodes = _wall_clock_pair([(1, 2)], weights, ticks=40)
    for nid, node in nodes.items():
        assert node.deg == 1, f"{nid}: derece {node.deg}, oysa tek komşu var"
        assert node.key == key_of(weights[nid], 1, nid), f"{nid}: anahtar yanlış"
        assert node.frozen_at_ms is not None
        assert node.frozen_at_ms >= WALL_MS + BbcvcParams().t_stab_ms, (
            f"{nid}: kapı T_stab dolmadan açıldı")
        assert node.epoch_bumps == 0 and node.epoch == 0
    events = [r["event"] for r in net.log_records]
    assert "reset_phase0" not in events, "duvar saatinde Faz 0'a dönüş var"
    assert events.count("key_frozen") == len(nodes), "anahtar bir kez donmalı"


def test_clock_baseline_does_not_depend_on_acquiring_a_neighbour():
    """Taban, komşu kümesinin DEĞİŞMESİNE bağlı olamaz.

    Eski yol tabanı yalnız "çift yönlü küme değişti" satırında kuruyordu, yani
    hiç çift yönlü komşu edinemeyen bir düğüm (yalıtık, ya da bütün HELLO'ları
    düşen) pencereyi hiç kurmuyor ve anahtarını hiç dondurmuyordu. Kenarsız iki
    düğüm bu yolu doğrudan yürür: taban yine kurulmalı ve kapı T_stab sonunda
    doğru cevapla, deg=0 ile açılmalıdır.
    """
    from ccvc.bb.api import key_of
    weights = {1: 5, 2: 3}
    _, nodes = _wall_clock_pair([], weights, ticks=1)
    for node in nodes.values():
        assert node._t0_ms == WALL_MS, "komşusuz düğümde taban kurulmadı"
        assert node.key is None
    _, nodes = _wall_clock_pair([], weights, ticks=20)
    for nid, node in nodes.items():
        assert node.deg == 0, "yalıtık düğümün derecesi 0'dır"
        assert node.key == key_of(weights[nid], 0, nid)


def test_no_time_field_is_initialised_to_zero():
    """Sıfır başlatılan bir zaman alanı, duvar saatinde süre ölçen her kapıyı
    ilk tıkta açar. Bu kusur bugün üç ayrı alanda bulundu; sınıfın tamamını
    kapatalım: taban kurulmadan ÖNCE her zaman alanı None olmalı."""
    ids = [1, 2]
    net = simnet.SimNet(ids, [(1, 2)], macs=bbcvc.macs_for(ids), rssi_range=None)
    node = bbcvc.BbcvcNode(5, net.port(1), BbcvcParams(), 2)
    for field in ("_t0_ms", "stable_since_ms", "_last_hello_ms", "_hello_due_ms",
                  "_last_change_ms", "_tree_sent_ms", "_tree_stable_since",
                  "_tree_started_ms", "frozen_at_ms"):
        assert getattr(node, field) is None, f"{field} sıfırdan/erken kurulmuş"


def test_on_timer_states_the_baseline_rather_than_inheriting_it():
    """`on_timer` bilerek ezilmiştir (sıra: karar SONRA iletim). O yüzden tabanı
    KENDİSİ kurmak zorundadır, `super()`den miras alamaz. Değişmez kodda
    görünür olmalı ki sonraki bir düzenleme onu sessizce düşürmesin."""
    import ast
    import inspect
    src = inspect.getsource(BbcvcNode.on_timer)
    assert "super().on_timer" not in src, "ezme bilerek; bu değişirse sırayı gözden geçir"
    assert "_establish_clock_baseline" in src, "taban on_timer'da kurulmuyor"
    # ve taban sınıfın alanlarını YENİDEN YAZMAK yerine ona devreder
    helper = inspect.getsource(BbcvcNode._establish_clock_baseline)
    assert "super()._establish_clock_baseline" in helper, (
        "taban sınıfın uzatma noktası çağrılmıyor; iki ayrı taban doğar")
    # Ezme, taban sınıfın alanlarını YENİDEN YAZMAZ, ona devreder; kendi
    # alanlarını ise KENDİSİ kurar, çünkü taban sınıfın onlardan haberi yok.
    body = ast.parse(inspect.getsource(BbcvcNode._establish_clock_baseline).strip())
    names = {n.attr for n in ast.walk(body) if isinstance(n, ast.Attribute)}
    assert "_establish_clock_baseline" in names, "uzatma noktası çağrılmıyor"
    assert {"_last_change_ms", "_tree_sent_ms"} <= names, "kendi alanları kurulmuyor"
    assert "_t0_ms" not in names, "taban sınıfın alanı burada yeniden yazılmış"


# ==========================================================================
# 18. LINK el sıkışmasının TAM maliyeti: kenar başına 4 iletim
# ==========================================================================
def test_link_handshake_costs_exactly_four_transmissions_per_edge():
    """Ekip liderinin ölçtüğü değişmez, bağımsız olarak doğrulandı ve SINIRI
    bulundu.

    Çift yön doğrulaması her kenarı İKİ YÖNDE kurar ve her yön bir LINK ile bir
    LINK_ACK harcar, dolayısıyla kenar başına tam olarak 2 LINK + 2 LINK_ACK
    düşer. Bu bir üst sınır değil EŞİTLİKTİR, o yüzden oran-tolerans değil tam
    eşitlik assert edilir.

    KAPSAM KOŞULU (ölçüldü, lider bunu görmemiş olabilir çünkü altı koşum da
    kayıpsızdı): eşitlik YALNIZ KAYIPSIZ kanalda geçerlidir. Kayıp varsa LINK
    yeniden gönderilir, üstelik düşen komşu `bidir` kümesini değiştirip epoch
    sıfırlaması tetiklediğinden el sıkışmalar baştan koşar. n=40, m=120'de
    ölçülen: %0 -> 2.00m, %5 -> 2.27m, %15 -> 29.46m. Yani değişmez kanal
    kalitesine göre bir sabit değil, kayıpsız durumun tam sayımıdır.
    """
    shapes = [(15, 40, 3), (20, 60, 3)]
    if SLOW:
        shapes += [(40, 120, 3), (40, 240, 5)]
    for n, m_target, k in shapes:
        edges, weights = _udg_dense(n, m_target, seed=1)
        m = len(edges)
        for scheduler in ("sync", "async"):
            r = run(scheduler, edges, weights, k,
                    params=BbcvcParams(mis_nbrs_max=30), max_ms=2_000_000)
            link = r.by_type_tx.get(int(MsgType.LINK), 0)
            ack = r.by_type_tx.get(int(MsgType.LINK_ACK), 0)
            assert link == 2 * m, f"n={n} m={m} {scheduler}: LINK {link} != {2*m}"
            assert ack == 2 * m, f"n={n} m={m} {scheduler}: LINK_ACK {ack} != {2*m}"
            assert link + ack == 4 * m


def test_link_invariant_is_a_lossless_statement_only():
    """Değişmezin KAPSAMINI de sabitle: kayıpta tutmadığını göstermezsek bir
    sonraki okuyan onu evrensel bir yasa sanır ve kayıplı ölçümü hata sayar."""
    edges, weights = _udg_dense(20, 60, seed=1)
    m = len(edges)
    p = BbcvcParams(mis_nbrs_max=30, ack_max_attempts=5, link_max_attempts=5)
    # Bütçe kasten KISA: sınanan şey yakınsama değil, kayıpta el sıkışmanın
    # yinelenmesi. %15 kayıpta koşum zaten sükûnete ermez, uzun bütçe yalnız
    # testi yavaşlatır (ölçüldü: 3e6 ms -> 16 s, 4e5 ms -> 2 s, aynı sonuç).
    clean = run("sync", edges, weights, 3, params=p, max_ms=400_000)
    assert clean.by_type_tx.get(int(MsgType.LINK), 0) == 2 * m
    lossy = run("sync", edges, weights, 3, params=p, loss=0.15, seed=5,
                max_ms=400_000)
    assert lossy.by_type_tx.get(int(MsgType.LINK), 0) > 2 * m, (
        "kayıpta el sıkışma yinelenmiyorsa ya kayıp uygulanmıyor ya retx ölü")
    assert lossy.retx > clean.retx


# ==========================================================================
# 19. Kademe 3b mesaj yolundan çağrılır: `_step`in kapısı onu KORUMAZ
# ==========================================================================
def test_relay_escalation_survives_unfrozen_neighbour_keys():
    """GERİLEME TESTİ. Vekâleten eskalasyon `_on_join`dan, yani `_drain_rx`
    içinden çağrılır; `_step`in `_keys_ready` kapısının ARKASINDA DEĞİLDİR.
    Anahtarı henüz donmamış (ya da epoch sıfırlamasıyla None'a dönmüş) bir
    komşu sıralamaya girdiğinde ham demet karşılaştırması `None < int` ile
    çöküyordu; %5 kayıpta ölçüldü.
    """
    edges, weights = _udg_dense(20, 60, seed=1)
    p = BbcvcParams(mis_nbrs_max=30, ack_max_attempts=5, link_max_attempts=5)
    for loss in (0.05, 0.15):
        r = run("sync", edges, weights, 3, params=p, loss=loss, seed=5,
                max_ms=400_000)       # çökmeden bitmeli; yakınsama şart değil
        assert r.tx > 0
    # ve sıralama anahtarı donmamış komşuyu EN SONA koyar, çökmez
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    node = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())[2]
    frozen = bbcvc.BootNeighbor(nid=3, mac=1, last_ms=0); frozen.key = 10
    unfrozen = bbcvc.BootNeighbor(nid=4, mac=2, last_ms=0); unfrozen.key = None
    assert node._nkey(frozen) < node._nkey(unfrozen)
    assert sorted([unfrozen, frozen], key=node._nkey)[0] is frozen


def _udg_dense(n: int, m_target: int, seed: int):
    """Kenar sayısı HEDEFLİ birim disk çizgesi; yarıçap ikili aramayla bulunur."""
    rng = random.Random(seed)
    pts = {i: (rng.random(), rng.random()) for i in range(1, n + 1)}
    lo, hi = 0.01, 0.9
    for _ in range(60):
        r = (lo + hi) / 2
        e = [(u, v) for u in pts for v in pts
             if u < v and math.dist(pts[u], pts[v]) <= r]
        if len(e) < m_target:
            lo = r
        else:
            hi = r
    edges = [(u, v) for u in pts for v in pts
             if u < v and math.dist(pts[u], pts[v]) <= hi]
    return edges, {i: rng.randint(1, 9) for i in range(1, n + 1)}


# ==========================================================================
# 20. Karşılıklı devir yarışı: kenar iki uçta birden bırakılamaz
# ==========================================================================
def test_simultaneous_opposing_transfers_never_lose_the_edge():
    """ÜÇÜNCÜ kez aynı sınıf hata: kenarın SAHİPSİZ kalması.

    Üçünün de nedeni farklıydı ve üçünü de doğrulayıcının `bad_owner` denetimi
    yakaladı, koşumun görüntüsü değil — üç seferinde de koşum yakınsıyor ve
    temiz sayılar üretiyordu:
      1. `_pending` yalnız seq ile anahtarlıydı; seq gönderene özeldir, bir
         komşudan gelen ACK başka bir komşuya yazılmış isteği kapatıyordu.
      2. `_finish_push_job` `_accept_edge`in dönüşünü yok sayıp ACK yolluyordu.
      3. (bu) İki uç AYNI kenarı AYNI ANDA birbirine devretti; her iki devir de
         tek başına doğruydu, ikisi birlikte kenarı kaybetti.

    Ölçülmüş örnek: n=30, r=0.28, tohum 2, k=3, kenar (6,17), slot 147-148.
    """
    edges, weights = _udg(30, 0.28, 2)
    g = validate.make_graph(edges, 3, weights)
    for scheduler in ("sync", "async"):
        r = run(scheduler, edges, weights, 3, max_ms=1_500_000)
        rep = validate.validate(g, r.cover, r.owner)
        assert not rep.by_kind(validate.BAD_OWNER), (
            f"{scheduler}: " + "; ".join(v.detail for v in rep.by_kind(validate.BAD_OWNER)))
        # her kenarın TAM BİR sahibi: sahipsiz de yok, çift sahipli de
        assert len(r.owner) == len(edges)


def test_transfer_tie_break_is_antisymmetric():
    """Yarışı kıran kural ANTİSİMETRİK olmalı: aynı kenarın iki ucu da aynı
    yönde karar veremez. İkisi de çekilirse devir hiç olmaz (kilitlenme),
    ikisi de kazanırsa kenar kaybolur (az önceki hata)."""
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    nodes = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())
    a, b = nodes[2], nodes[4]
    a.key, b.key = (100, 2), (200, 4)          # a daha küçük anahtarlı
    e = bbcvc.edge(2, 4)
    na = bbcvc.BootNeighbor(nid=2, mac=1, last_ms=0); na.key = 100
    nb = bbcvc.BootNeighbor(nid=4, mac=2, last_ms=0); nb.key = 200

    # ikisinin de aynı kenar için isteği yolda
    a._pending[(4, 1)] = bbcvc.Pending(seq=1, peer=4, mtype=MsgType.PUSH,
                                       payload=b"", e=e)
    b._pending[(2, 1)] = bbcvc.Pending(seq=1, peer=2, mtype=MsgType.HANDOVER,
                                       payload=b"", e=e)
    a_yields = a._yields_to_inbound(e, nb)
    b_yields = b._yields_to_inbound(e, na)
    assert a_yields != b_yields, "iki uç aynı yönde karar verdi"
    assert a_yields and not b_yields, "küçük anahtarlı uç kendi isteğini korur"

    # kendi isteği OLMAYAN uç asla çekilmez: sıradan devir etkilenmez
    c = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())[3]
    c.key = (150, 3)
    assert not c._yields_to_inbound(e, nb)


# ==========================================================================
# 21. Varyant kancaları: node_factory ve result_cls
# ==========================================================================
def test_node_factory_default_is_byte_identical():
    """Kanca varsayılan yolu DEĞİŞTİRMEZ; bu, kancanın bedelsiz olduğunun kanıtı."""
    a = run("sync")
    b = bbcvc.run_bbcvc(EDGES, WEIGHTS, K, scheduler="sync", max_ms=BUDGET_MS,
                        node_factory=bbcvc.build_nodes)
    assert (a.cover, a.owner, a.tx, a.rx, a.slots) == (b.cover, b.owner, b.tx, b.rx, b.slots)


def test_node_factory_carries_per_node_seed_data_and_a_pre_run_hook():
    """GHS-MST-Backbone DÜĞÜM BAŞINA tohum verisi (MST'den türetilen rol) ister, Anneal ise
    zamanlayıcı BAŞLAMADAN düğümlere gözlemci takmak ister. Ağ düzeyindeki tek
    fabrika ikisini birden karşılar; düğüm düzeyinde bir `node_cls` hiçbirini
    karşılamazdı, hazır kurulmuş düğümler de olmazdı çünkü portlar
    `run_bbcvc`in İÇİNDE kurulan ağdan gelir."""
    from dataclasses import dataclass

    @dataclass
    class VariantParams(BbcvcParams):
        extra: int = 7

    class SeededNode(BbcvcNode):
        def __init__(self, w, port, params, k, seed_role=None):
            super().__init__(w, port, params, k)
            self.seed_role = seed_role
            self.trace = []

    def factory(net, weights, k, params):
        assert isinstance(params, VariantParams) and params.extra == 7, (
            "params alt tipi BbcvcParams'a zorlanmış")
        out = {}
        for nid in net.nodes:
            node = SeededNode(weights[nid], net.port(nid), params, k,
                              seed_role=f"seed-{nid}")
            node.trace.append("koşumdan önce")
            out[nid] = node
        return out

    r = bbcvc.run_bbcvc(EDGES, WEIGHTS, K, scheduler="sync", max_ms=BUDGET_MS,
                        params=VariantParams(), node_factory=factory)
    base = run("sync")
    assert r.cover == base.cover and r.owner == base.owner
    assert len(r.nodes) == len(WEIGHTS)                    # gereksinim 2
    assert r.nodes[3].seed_role == "seed-3"                # gereksinim 1
    assert r.nodes[3].trace[0] == "koşumdan önce"          # gereksinim 3


def test_result_cls_keeps_the_result_type_open():
    """Anneal `BbcvcRun`ın on beş alanına dört alan daha ekler. Sonuç tipi
    sabitlenseydi Anneal yine bir uyarlayıcı yazar, kopya yok olmaz yer
    değiştirirdi."""
    from dataclasses import dataclass

    @dataclass
    class VariantRun(bbcvc.BbcvcRun):
        observer_best_weight: float = 0.0

    r = bbcvc.run_bbcvc(EDGES, WEIGHTS, K, scheduler="sync", max_ms=BUDGET_MS,
                        result_cls=VariantRun)
    assert isinstance(r, VariantRun) and isinstance(r, bbcvc.BbcvcRun)
    assert r.observer_best_weight == 0.0
    assert r.cover == run("sync").cover


# ==========================================================================
# 22. Kesilmiş koşum BAŞARI olarak okunamaz
# ==========================================================================
def test_a_truncated_run_is_never_reported_as_solved():
    """ÖLÇÜLMÜŞ HATA (ekip lideri buldu, kendi teşhisini düzelterek).

    Duvar bütçesi dolduğunda hiçbir düğüm henüz pes etmemiştir, dolayısıyla
    `infeasible=False, unresolved=False` döner ve bayrakların YOKLUĞUNDAN
    başarı çıkaran bir tüketici satırı geçerli bir kol sonucu olarak kaydeder.
    Ölçüm, çalışan örnek üzerinde: max_ms=2000'de koşum 10 slotta kesiliyor ve
    |C|=3, SIFIR sahiplik, KOPUK bir örtüyle "bayraksız" dönüyordu.

    Bu, sonuç tablolarını KİRLETEN tek başarısızlık biçimidir: görünür bir
    başarısızlık satırı tabloya girmez, sessiz bir başarı girer ve ortalamaya
    karışır.
    """
    budgets = [2_000, 4_000, 8_000]
    seen = set()
    for mm in budgets:
        r = run("sync", max_ms=mm)
        seen.add(r.verdict)
        assert not r.converged, f"max_ms={mm} beklenenden hızlı bitti, test boş"
        assert r.verdict == "truncated", f"max_ms={mm}: hüküm {r.verdict!r}"
        assert r.truncated
        # ve tam bu yüzden: bayrakların yokluğu BAŞARI DEĞİLDİR
        assert not (r.infeasible or r.unresolved), (
            "kesilmiş koşumda bayrak kalkmış; o zaman bu test yanlış şeyi sınıyor")
    assert seen == {"truncated"}
    # bol bütçeyle aynı örnek çözülür: test kesintiyi ölçüyor, kırıklığı değil
    assert run("sync").verdict == "solved"


def test_a_truncated_run_can_pass_validation_and_still_be_worthless():
    """EN KEŞKİN DURUM, ekip liderinin n=50 örneğinden çıktı: kesilmiş bir koşum
    DOĞRULAYICIYI GEÇEBİLİR.

    Ölçüm (n=50, m=144, k=6; sayma sınırı sessiz çünkü n*k=300 > m):
        max_ms= 2000 -> 10 slot, kesik, 241 ihlal
        max_ms= 5000 -> 25 slot, kesik, SIFIR ihlal      <-- tehlikeli olan bu
        max_ms=20000 -> 29 slot, çözüldü, sıfır ihlal
    241 ihlalli satırı doğrulama zaten yakalar. Ortadaki satırı YAKALAMAZ: örtü
    o anda tutarlıdır, ama koşum bitmemiştir ve devam etseydi başka bir cevap
    verebilirdi. Yani GEÇERLİLİK, `verdict`in yerine geçmez; bir satırı kol
    sonucu olarak kaydetmenin koşulu "doğrulayıcı temiz" değil, "koşum bitti"dir.
    """
    edges, weights = _udg_dense(50, 144, seed=1)
    k = 6
    g = validate.make_graph(edges, k, weights)
    assert not bbcvc.counting_bound_infeasible(len(weights), len(edges), k), (
        "sayma sınırı ateşlerse bu test yanlış şeyi ölçer")
    p = BbcvcParams(mis_nbrs_max=30)
    cut = run("sync", edges, weights, k, params=p, max_ms=5_000)
    assert cut.verdict == "truncated" and not cut.converged
    assert validate.validate(g, cut.cover, cut.owner).valid, (
        "bu örnek kesikken doğrulayıcıyı geçmiyorsa testin can alıcı noktası kayboldu")
    # bayraklar temiz, doğrulayıcı temiz, ve koşum YİNE DE kol sonucu değil
    assert not (cut.infeasible or cut.unresolved)
    full = run("sync", edges, weights, k, params=p, max_ms=20_000)
    assert full.verdict == "solved" and full.converged


def test_verdict_is_about_the_run_and_infeasible_is_about_the_instance():
    """İki AYRI soru, iki ayrı alan. Bir örnek aritmetikle uygunsuz olabilir VE
    aynı koşum bütçe dolduğu için kesik olabilir; ikisi birden doğrudur ve
    birini diğerinin yerine okumak yanlış cevap verir."""
    n, k = 6, 2
    edges = [(u, v) for u in range(1, n + 1) for v in range(u + 1, n + 1)]
    weights = {i: 1 for i in range(1, n + 1)}
    short = run("sync", edges, weights, k, max_ms=60_000)
    full = run("sync", edges, weights, k, max_ms=300_000)
    # ÖRNEK hakkındaki cevap bütçeden BAĞIMSIZ: sayma kanıtı koşumu beklemez
    assert short.infeasible and full.infeasible
    assert short.infeasible_reason == full.infeasible_reason == "counting_bound"
    # KOŞUM hakkındaki cevap bütçeye bağlı, ve öyle olmalı
    assert short.verdict == "truncated"
    assert full.verdict == "unresolved"


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_verdict_covers_every_run_exactly_once(scheduler):
    """Üç hüküm ayrık ve tüketici: her koşum tam birine düşer, ve "solved"
    ancak yakınsamış VE hiçbir düğümün pes etmediği koşum için verilir."""
    cases = [
        (EDGES, WEIGHTS, K, BUDGET_MS),                       # çözülür
        (EDGES, WEIGHTS, K, 4_000),                           # kesilir
        ([(u, v) for u in range(1, 7) for v in range(u + 1, 7)],
         {i: 1 for i in range(1, 7)}, 2, BUDGET_MS),          # pes eder
    ]
    seen = set()
    for edges, weights, k, mm in cases:
        r = run(scheduler, edges, weights, k, max_ms=mm)
        assert r.verdict in ("solved", "unresolved", "truncated")
        seen.add(r.verdict)
        assert (r.verdict == "solved") == (r.converged and not r.unresolved)
        assert (r.verdict == "truncated") == (not r.converged) == r.truncated
    assert seen == {"solved", "unresolved", "truncated"}, seen


# ==========================================================================
# 23. Ölçek değişmezliği: hiçbir sabit ağırlığa göre ayarlanmamış
# ==========================================================================
def test_no_parameter_is_scaled_to_the_worked_example_weights():
    """bb-core'un Anneal'da ödediği hatanın BB-CVC'ye ULAŞAMADIĞINI göster.

    Onların lambda, T0 ve T_min değerleri .tex'in 10 düğümlük örneğinden
    alınmıştı ve orada w_max=6 idi. Dagdeviren kümesinde ağırlıklar 26-115
    arasında koşunca cezalar "satın alınabilir" hâle geldi, her düğüm örtüden
    çıktı ve 195/195 sweep satırı BOŞ ÖRTÜ döndürürken `converged=True`
    raporladı.

    BB-CVC bu sınıfa yapısal olarak kapalıdır ve nedeni tek cümledir: her
    eşitlik anahtarların KARŞILAŞTIRILMASIYLA kırılır, hiçbir anahtar bir
    EŞİĞE karşı sınanmaz. Karşılaştırma ölçekten bağımsızdır, eşik değildir.
    Ağırlıklar 1-9 da olsa 26-115 de olsa `key_u < key_v` aynı sıralamayı
    verir.

    Test bunu iki yönden kapatır: parametrelerin hiçbiri ağırlık boyutunda
    değildir, ve aynı topoloji 1000 katına ölçeklenmiş ağırlıklarla AYNI
    örtüyü üretir.
    """
    # (a) her parametre atlama/adım/periyot sayısıdır, ağırlık değil
    p = BbcvcParams()
    for field, value in (("push_ttl", p.push_ttl), ("push_ttl_max", p.push_ttl_max),
                         ("quiet_periods", p.quiet_periods), ("ack_periods", p.ack_periods),
                         ("ack_max_attempts", p.ack_max_attempts),
                         ("settle_steps", p.settle_steps), ("gap_patience", p.gap_patience),
                         ("escalate_patience", p.escalate_patience),
                         ("max_repair_rounds", p.max_repair_rounds)):
        assert isinstance(value, int) and 0 <= value <= 64, (
            f"{field}={value}: ağırlık boyutunda bir sabite benziyor")

    # (b) ağırlıkları 1000 katına çıkar: karar AYNI kalmalı
    base = run("sync")
    big = {nid: w * 1000 for nid, w in WEIGHTS.items()}
    scaled = run("sync", EDGES, big, K)
    assert scaled.cover == base.cover, "ağırlık ölçeği örtüyü değiştirdi"
    assert scaled.owner == base.owner, "ağırlık ölçeği sahipliği değiştirdi"
    assert scaled.total_weight == base.total_weight * 1000

    # (c) ve kaydırma da: w -> w + 1000 sıralamayı korumaz, ama BOŞ ÖRTÜ üretmez
    shifted = run("sync", EDGES, {nid: w + 1000 for nid, w in WEIGHTS.items()}, K)
    assert shifted.cover, "kaydırılmış ağırlıkta örtü BOŞALDI"
    assert validate.validate(validate.make_graph(EDGES, K, {n: w + 1000
                                                           for n, w in WEIGHTS.items()}),
                             shifted.cover, shifted.owner).valid


def test_a_solved_verdict_is_not_a_validity_claim():
    """`verdict` KOŞUMUN bittiğini söyler, cevabın DOĞRU olduğunu değil.

    bb-core'un boş-örtü hatası tam olarak buraya düşerdi: koşum yakınsıyordu,
    hiçbir düğüm pes etmemişti, yani hüküm "solved" olurdu — ve cevap yine de
    çöptü. Doğrulayıcı onu yakalar, hüküm yakalamaz.

    Bu yüzden bir satırı kol sonucu olarak kaydetmenin koşulu İKİSİ BİRDEN:
    `verdict == "solved"` VE doğrulayıcı temiz. Tek başına hiçbiri yetmez —
    kesik bir koşum doğrulayıcıyı geçebiliyor (bkz. n=50 testi), çözülmüş bir
    koşum da geçersiz bir cevap taşıyabilir.
    """
    r = run("sync")
    rep = validate.validate(graph_of(), r.cover, r.owner)
    assert r.verdict == "solved" and rep.valid        # sağlıklı hâl: ikisi de
    # hüküm yalnız SONLANMA hakkındadır; tanımı bunu açıkça söyler
    assert (r.verdict == "solved") == (r.converged and not r.unresolved)
    # ve geçerlilik hükmün İÇİNDE DEĞİLDİR: bozuk bir sahiplikle hüküm değişmez
    crippled = dict(r.owner)
    del crippled[sorted(crippled)[0]]
    assert not validate.validate(graph_of(), r.cover, crippled).valid
    assert r.verdict == "solved", "hüküm geçerlilikten türetilseydi burada düşerdi"


# ==========================================================================
# 24. Dış dosyada tutulan değişmezler: nöbetçi ve kesirli ağırlık
# ==========================================================================
def test_phase5b_sentinel_depends_on_hash16_reserving_zero():
    """Faz 5b'nin kodlaması BU DOSYADA OLMAYAN bir değişmeze dayanıyor.

    `wire.Tree` kök ve ebeveyni düz 16 bitlik sayı taşır, Optional taşıyamaz,
    bu yüzden "yok" için bir nöbetçi gerekir ve o nöbetçi 0'dır. Doğruluğu
    `bootstrap.hash16`ın 0'ı ayırmasına bağlıdır.

    BASKI GERÇEK: kıyas kümesinin 310 örneğinin hepsi 0-indekslidir, yani ilk
    tepki "hash16'da 0'ı serbest bırak" olur ve o an kökü 0 olan bir ağaç
    "kök yok" ile ayırt edilemez hâle gelir -- SESSİZCE, bu dosyada.
    Test hem değişmezi hem de onu gevşetenin gürültülü bir hata alacağını pinler.
    """
    from ccvc.bb.bootstrap import hash16
    # (a) değişmezin kendisi: hash16 asla 0 döndürmez
    assert all(hash16(mac) != 0 for mac in range(0, 4000)), "hash16 0'ı serbest bırakmış"
    assert hash16(0) != 0

    # (b) gevşetilirse SESSİZ değil GÜRÜLTÜLÜ olur: kodlayıcı koşum anında denetler
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    node = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams(enable_tree=True))[2]
    node.nid = bbcvc._TREE_NO_NODE          # 0 serbest bırakılmış gibi davran
    node.tree_root = 5
    with pytest.raises(ValueError, match="nöbetçi"):
        node._tree_send(0, [], force=True)


def test_runs_on_fractional_weights_like_the_real_benchmark():
    """KÖR NOKTA: 162 testin hepsi TAMSAYI ağırlık kullanıyordu.

    Kıyas kümesinin 310 örneğinin ağırlıkları kesirlidir (26.20965 gibi).
    bb-bootstrap tam bu yüzden yanıldı: "tamsayı girdi" kısıtını problemin
    özelliği sandılar, oysa §3.6'nın istediği şey sabit noktalı ARİTMETİK.
    Kısıt test ettikleri rejimde geçerliydi, problemde değil -- brief'in G8 ile
    yaptığı hatanın aynısı, bir kat aşağıda.

    BB-CVC ağırlığı yalnız anahtar üretiminde kullanır ve anahtar `api.key_of`
    ile 16.16 sabit noktaya çevrilir, dolayısıyla kesirli GİRDİ sorun değildir;
    yasak olan kayan noktalı ANAHTARDIR. Bu test o ayrımı pinler.
    """
    frac = {1: 26.20965, 2: 31.5, 3: 44.125, 4: 38.0, 5: 52.75,
            6: 29.33, 7: 41.8, 8: 27.05, 9: 55.2, 10: 47.9}
    g = validate.make_graph(EDGES, K, frac)
    for scheduler in ("sync", "async"):
        r = run(scheduler, EDGES, frac, K)
        assert r.verdict == "solved", f"{scheduler}: {r.verdict}"
        rep = validate.validate(g, r.cover, r.owner)
        assert rep.valid, rep.summary()
        assert len(r.owner) == len(EDGES)
        # anahtarlar YİNE tam sayı (16.16 sabit nokta); kesirli girdi buraya sızmaz
        for node in r.nodes.values():
            assert isinstance(node.key_fp, int) and not isinstance(node.key_fp, bool)
    # ve toplam ağırlık gerçekten kesirli, yani test kesirliliği kaybetmiyor
    assert run("sync", EDGES, frac, K).total_weight != int(
        run("sync", EDGES, frac, K).total_weight)


def test_a_truncated_run_can_have_a_complete_owner_map():
    """EN KÖTÜ İMZA (bb-bootstrap ölçtü, kıyas koşumlarında 13'te 5 kesik).

    max_ms=3000'de çalışan örnek: converged=False, infeasible=False,
    unresolved=False VE sahiplik 15/15 TAM. Yani kesilmiş bir koşum, bir
    tüketicinin doğal olarak bakacağı HER alanda başarılı bir koşumdan
    ayırt edilemez -- eksiksiz bir sahiplik tablosu dahil.

    Bu, kesinti kovasının kolun KENDİ bayraklarından ÖNCE denetlenmesi
    gerektiğinin kanıtıdır: bitmemiş bir koşumun "uygun" demesi anlamsızdır.
    """
    r = run("sync", max_ms=3_000)
    assert not r.converged and r.verdict == "truncated"
    assert not (r.infeasible or r.unresolved)
    assert len(r.owner) == len(EDGES), (
        "bu bütçede sahiplik tam değilse testin can alıcı noktası kayboldu")
    # doğrulayıcı da temiz olabilir; o zaman HİÇBİR alan kesintiyi ele vermez
    # `verdict` DIŞINDA. Tek savunma odur.
    assert r.verdict == "truncated"


# ==========================================================================
# 25. `mis_nbrs` alanının tek okuma yolu
# ==========================================================================
def test_mis_nbrs_has_exactly_one_read_path():
    """Alanı okuyan HER yer `_nbr_mis`ten geçmeli.

    `mis_nbrs`, Hello gövdesindeki tek değişken uzunluklu sözcük dizisidir, bu
    yüzden 2-atlama bilgisi taşıması gereken WuLi-Dominating komşu ÖZETİNİ oraya
    koyuyor. Orada alan MIS kimliği DEĞİLDİR. Taban sınıfa eklenen dördüncü bir
    okuyucu WuLi-Dominating'de sessizce yanlış şeyi okur; bb-validate ölçtü: n=20'de örtü
    12'den 20'ye, ağırlık %23 arttı ve HİÇBİR ŞEY düşmedi -- koşum yakınsadı,
    doğrulayıcı VALID dedi.

    Denetim KAYNAK METNİ üzerinde değil, AST üzerinde: `n.mis_nbrs` biçiminde
    bir öznitelik erişimi yalnız `_nbr_mis`in gövdesinde bulunabilir.
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(BbcvcNode))
    offenders = []
    for fn in [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)]:
        if fn.name in ("_nbr_mis", "mis_nbrs"):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and node.attr == "mis_nbrs":
                base = node.value
                # self.mis_nbrs (kendi üretimim) serbest; komşununki değil
                if not (isinstance(base, ast.Name) and base.id == "self"):
                    offenders.append(fn.name)
    assert not offenders, (
        f"`mis_nbrs` {sorted(set(offenders))} içinde doğrudan okunuyor; "
        f"`self._nbr_mis(n)` kullanın, yoksa WuLi-Dominating sessizce bozulur")


def test_overriding_the_accessor_turns_a_silent_break_into_a_loud_one():
    """Tek okuma yolunun VARLIK SEBEBİ: ezen varyant kendini koruyabilsin.

    WuLi-Dominating `_nbr_mis`i yükseltmeye ezer; taban sınıftaki her okuyucu o anda yığın
    iziyle ölür. Sessiz yanlış cevap yerine anında hata.
    """
    class GuardedNode(BbcvcNode):
        def _nbr_mis(self, n):
            raise RuntimeError("WuLi-Dominating: sözcük dizisi MIS listesi değil, "
                               "komşu özeti")

    def factory(net, weights, k, params):
        return {nid: GuardedNode(weights[nid], net.port(nid), params, k)
                for nid in net.nodes}

    with pytest.raises(RuntimeError, match="komşu özeti"):
        bbcvc.run_bbcvc(EDGES, WEIGHTS, K, scheduler="sync", max_ms=BUDGET_MS,
                        node_factory=factory)
    # ve ezilmeden aynı koşum sorunsuz: kapı yalnız ezene ait
    assert run("sync").verdict == "solved"


def test_backbone_contract_dominance_clause_excludes_complete_graphs():
    """Sözleşme maddesi 2'nin İSTİSNASI belgelenmiş olmalı.

    Wu-Li "iki komşusu birbirine komşu olmayan düğümü işaretle" der; K_n'de her
    komşuluk kliktir, kimse işaretlenmez, B boş kalır. Teoremin kapsamı bağlı ve
    TAM OLMAYAN çizgelerdir, yani bu WuLi-Dominating'in kusuru değil.

    Bizim MIS tabanlı omurgamız K_n'de ETKİLENMEZ -- tek düğümlük bir MIS hem
    bağlı hem baskındır -- ve test bunu gösterir, ki istisnanın MIS-Connector-Backbone'u kapsadığı
    sanılmasın.
    """
    import inspect
    doc = inspect.getdoc(BbcvcNode._backbone_step)
    assert "TAM DEĞİLSE" in doc and "WuLi-Dominating" in doc, (
        "madde 2'nin tam-çizge istisnası sözleşmede yazılı değil")
    # MIS-Connector-Backbone K_n'de sağlam: omurga tek MIS düğümü, bağlı ve baskın
    edges, weights, k = K5
    r = run("sync", edges, weights, k)
    g = validate.make_graph(edges, k, weights)
    b = backbone(r)
    assert len(b) == 1
    assert validate.check_g2(g, b) == [] and validate.is_dominating_set(g, b)


# ==========================================================================
# 26. `unresolved` ŞİMDİKİ durumu anlatır, geçmişteki bir anı değil
# ==========================================================================
def _udg_w10(n: int, m_target: int, seed: int):
    """bb-figures'ın ailesiyle aynı üretici (ağırlık 1..10)."""
    rng = random.Random(seed)
    pts = {i: (rng.random(), rng.random()) for i in range(1, n + 1)}
    lo, hi = 0.01, 0.9
    for _ in range(60):
        r = (lo + hi) / 2
        e = [(u, v) for u in pts for v in pts
             if u < v and math.dist(pts[u], pts[v]) <= r]
        if len(e) < m_target:
            lo = r
        else:
            hi = r
    edges = [(u, v) for u in pts for v in pts
             if u < v and math.dist(pts[u], pts[v]) <= hi]
    return edges, {i: rng.randint(1, 10) for i in range(1, n + 1)}


def test_unresolved_is_cleared_when_the_overload_is_relieved():
    """ÖLÇÜLMÜŞ HATA (bb-figures buldu). Bayrak bir kez kalkıyor ve BİR DAHA
    İNMİYORDU.

    `unresolved` "yerel onarım pes etti" demektir. Pes ettikten sonra taşkın
    BAŞKASININ işiyle geçebilir: bir komşu eskale eder, F'i düşer, varsayılan
    kural kenarı ona kaydırır ve düğüm k'nin altına iner. Bayrak temizlenmezse
    artık yaşanmayan bir başarısızlık iddia edilir -- bir kolun destekleyemediği
    bir başarısızlığı öne sürmesi, sağlam olmayan uygunsuzluk iddiasının aynası.

    MEKANİZMA DOĞRUDAN SINANIR, bir örneğe sabitlenmez. İlk sürümü "şu örnekte
    şu düğüm toparlanıyor" diye pinlemiştim ve sahiplik yarışı düzeltilince o
    örnek artık pes etmediği için test BOŞALDI. Aynı ders bb-figures'ın iki kez
    kırılan fixture'ında da çıktı: bir testi "bu örnek şu hatayı gösteriyor"
    üzerine kurmak, algoritma düzeldiğinde testi kırar.
    """
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    node = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())[2]
    node.phase = PH_OWN
    node.role = Role.MIS
    node.unresolved = True

    def nbr(nid, role):
        n = bbcvc.BootNeighbor(nid=nid, mac=nid, last_ms=0)
        n.key, n.role, n.bidir, n.link_up = nid * 10, role, True, True
        return n

    # TEK dış komşu -> zorunlu kenar 1 <= k=2: taşkın geçmiş, bayrak DÜŞMELİ
    light = [nbr(1, Role.OUT)]
    node._rule_ownership(1000, light)
    assert len(node.owned) <= node.k
    assert not node.unresolved, "taşkın geçtiği hâlde bayrak kalkık kaldı"

    # ÜÇ dış komşu -> zorunlu kenar 3 > k=2: taşkın sürüyor, bayrak KALMALI
    node.unresolved = True
    heavy = [nbr(1, Role.OUT), nbr(3, Role.OUT), nbr(4, Role.OUT)]
    node._rule_ownership(2000, heavy)
    assert len(node.owned) > node.k, "kurgu taşkın üretmedi, test boş"
    assert node.unresolved, "taşkın sürerken bayrak düştü"


def test_a_persistent_overload_keeps_the_flag():
    """Ters yön: taşkın GERÇEKTEN sürüyorsa bayrak düşmemeli. Bu olmadan
    "temizle" düzeltmesi bayrağı tamamen işlevsiz kılabilirdi."""
    edges = [(u, v) for u in range(1, 7) for v in range(u + 1, 7)]
    weights = {i: 1 for i in range(1, 7)}
    r = run("sync", edges, weights, 2)
    rep = validate.validate(validate.make_graph(edges, 2, weights), r.cover, r.owner)
    assert r.unresolved, "kalıcı taşkında bayrak düşmüş"
    assert not rep.valid and max(len(n.owned) for n in r.nodes.values()) > 2


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_no_run_claims_failure_the_validator_cannot_support(scheduler):
    """DEĞİŞMEZ: `unresolved` ise doğrulayıcı TEMİZ OLAMAZ.

    Bir kolun destekleyemediği bir başarısızlığı öne sürmesi, yanlış bir
    başarıdan daha az zararlıdır ama aynı sınıftandır: iddia ile kanıt
    ayrışmıştır. Fark şu ki bu yön sonuç tablosunu kirletmez, kolu haksız yere
    kötü gösterir.
    """
    for n, m, k in ((25, 150, 6), (20, 90, 4), (30, 120, 6)):
        edges, weights = _udg_w10(n, m, seed=2)
        g = validate.make_graph(edges, k, weights)
        r = run(scheduler, edges, weights, k, params=BbcvcParams(mis_nbrs_max=30),
                max_ms=2_000_000)
        if not r.unresolved:
            continue
        rep = validate.validate(g, r.cover, r.owner)
        assert not rep.valid, (
            f"n={n} m={m} k={k} {scheduler}: kol 'çözemedim' diyor ama "
            f"doğrulayıcı sıfır ihlal buluyor")


# ==========================================================================
# 27. Kenar İKİ UÇTA birden sahiplenilemez (ailenin dördüncü üyesi)
# ==========================================================================
def test_owner_map_does_not_collapse_a_double_claim():
    """`owner` bir SÖZLÜKTÜR ve `owner[e] = nid` çifte iddiayı sessizce
    tek girdiye çökertir.

    Ekip liderinin bulduğu biçim: bir düğümün kendi `owned` kümesinde k'den
    fazla kenar var, ama harita 150 kenarın 150'sini kapsıyor, hiçbir düğüm
    taşkın GÖRÜNMÜYOR ve doğrulayıcı GEÇİYOR. Çifte iddianın tek izi düğümün
    özel görüşünün toplamla çelişmesiydi ve hiçbir tüketici ona bakmıyordu.
    `double_claimed` alanı tam olarak bu izi görünür kılar.
    """
    r = run("sync")
    assert r.double_claimed == {}, r.double_claimed
    # alanın gerçekten dolduğunu göster: elle çakıştırılmış bir durumda yakalar
    claims = {}
    for nid, node in r.nodes.items():
        for e in node.owned:
            claims.setdefault(e, []).append(nid)
    assert all(len(v) == 1 for v in claims.values())
    assert sum(len(v) for v in claims.values()) == len(EDGES), (
        "iddia sayısı kenar sayısından farklı: sahipsiz ya da çifte iddia var")


def test_a_late_ack_from_a_cancelled_epoch_does_not_release_the_edge():
    """An ACK that outlived its epoch confirms a transfer that no longer exists.

    The release above is sound INSIDE one epoch: the neighbour said explicitly
    that it took the edge and holds it in `_explicit`, so letting go cannot
    leave the edge unowned. An epoch restart cancels the transfer on BOTH sides
    -- `_init_algo_state` clears `_explicit`, `owned` and `_pending` everywhere
    -- so honouring the ACK afterwards releases an edge nobody has taken.

    MEASURED at five per cent loss, the level the real channel runs at: six of
    forty-five MIS-Connector runs came back `solved` AND invalid, every one with
    `bad_owner`, and in each the giver held `_explicit[e] = False` while the
    taker had no entry at all.
    """
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    node = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())[2]
    e = bbcvc.edge(2, 4)
    node.owned = {e}
    node._explicit[e] = True
    node._offered.add(e)
    nbr = bbcvc.BootNeighbor(nid=4, mac=2, last_ms=0)
    nbr.key = 10
    node.nbrs[4] = nbr

    node._reset_to_phase0(0, reason="test")      # the epoch restarts
    node.owned = {e}                             # the rule re-derives ownership
    node._explicit[e] = True

    node._on_late_ack(0, nbr, wire.EdgeMsg(MsgType.PUSH_ACK, 4, 999, e[0], e[1]))

    assert e in node.owned, (
        "iptal edilmiş bir epoch'un ACK'i kenarı bıraktırdı: kenar sahipsiz kalır")


def test_a_late_ack_after_giving_up_releases_the_edge():
    """ÖLÇÜLMÜŞ HATA: PES ETTİKTEN SONRA gelen olumlu yanıt.

    Uzun bir PUSH zincirinde alıcının yanıtı, gönderenin `R_max` denemesi
    tükendikten SONRA dönebiliyor. Gönderen isteği çoktan NACK sayıp kenarı
    kendinde tutmuş, alıcı ise `_finish_push_job` içinde kenarı KABUL etmiş
    olur: kenarın İKİ SAHİBİ olur.

    Bu ailenin DÖRDÜNCÜSÜ ve ilk üçünün AYNASI: onlar kenar kaybediyordu, bu
    kenar çoğaltıyor. Ve daha sinsi, çünkü kayıp kenarı doğrulayıcı `bad_owner`
    ile yakalıyordu; çoğaltılmış kenarı hiçbir tüketici göremiyordu.

    Çözüm: geç gelen olumlu yanıt YETKİLİDİR. Komşum kenarı aldığını açıkça
    söylüyor ve `_explicit` ile kendinde tutuyor, dolayısıyla benim bırakmam
    kenarı SAHİPSİZ bırakamaz -- komşu ancak kendisi bir ACK alırsa bırakır.
    """
    ids = sorted(WEIGHTS)
    net = simnet.SimNet(ids, EDGES, macs=bbcvc.macs_for(ids), rssi_range=None)
    node = bbcvc.build_nodes(net, WEIGHTS, K, BbcvcParams())[2]
    e = bbcvc.edge(2, 4)
    node.owned = {e}
    node._explicit[e] = True
    # The node really did offer this edge in THIS epoch; a late ACK is only
    # authoritative for a transfer that is still live (see `_offered`).
    node._offered.add(e)
    nbr = bbcvc.BootNeighbor(nid=4, mac=2, last_ms=0)
    nbr.key = 10
    node.nbrs[4] = nbr
    msg = wire.EdgeMsg(MsgType.PUSH_ACK, 4, 999, e[0], e[1])
    assert not node._pending, "bekleyen istek varsa bu geç ACK değildir"
    node._on_late_ack(0, nbr, msg)
    assert e not in node.owned and node._explicit[e] is False, (
        "geç gelen ACK'ten sonra kenar hâlâ bende: çifte sahiplik")
    # bana ait olmayan bir kenar için gelen geç ACK HİÇBİR ŞEY yapmaz
    other = bbcvc.edge(7, 8)
    node.owned = {other}
    node._on_late_ack(0, nbr, wire.EdgeMsg(MsgType.PUSH_ACK, 4, 998, 7, 8))
    assert other in node.owned, "ilgisiz kenar bırakıldı"


def test_every_edge_is_claimed_exactly_once_across_all_nodes():
    """Problem tanımı her kenarın TAM BİR uca atanmasını ister (brief §1).
    Sahipsiz de olmayacak, çifte de. İki yön birlikte sınanır, çünkü bugüne
    kadar bu ailenin dört hatası da tek yönlü denetimden kaçtı."""
    for scheduler in ("sync", "async"):
        for edges, weights, k in ((EDGES, WEIGHTS, K), PATH5, TWO_TRI, GRID4):
            r = run(scheduler, edges, weights, k)
            if r.verdict == "truncated":
                continue
            claims = {}
            for nid, node in r.nodes.items():
                for e in node.owned:
                    claims.setdefault(e, []).append(nid)
            doubles = {e: v for e, v in claims.items() if len(v) > 1}
            assert not doubles, f"{scheduler}: çifte iddia {doubles}"
            assert r.double_claimed == {}
            cov = set(r.cover)
            covered = [e for e in map(lambda x: bbcvc.edge(*x), edges)
                       if e[0] in cov or e[1] in cov]
            missing = [e for e in covered if e not in claims]
            assert not missing, f"{scheduler}: sahipsiz kenar {missing}"


# --------------------------------------------------------------------------
# DEGREE DEFICIENCY: THE WITNESS THE COUNTING BOUND CANNOT SEE
#
# An owner must be an ENDPOINT of the edge it owns, so a node can own at most
# min(deg(v), k) edges. MEASURED on the n50_m300 cell, where m = n*k = 300 and
# the counting bound holds with equality and therefore says nothing: seeds 6
# and 8 have available capacity 298 < 300 and are provably unsolvable, while
# the other eight seeds have exactly 300 and are solvable. Before this check
# those two were reported `unresolved`, which reads as an arm failing on a
# solvable instance.
# --------------------------------------------------------------------------
def test_degree_deficiency_sees_what_the_counting_bound_cannot():
    from ccvc.bb.bbcvc import (counting_bound_infeasible,
                               degree_deficiency_infeasible)
    # n = 50, k = 6, m = 300: the counting bound is tight, so it is silent.
    assert counting_bound_infeasible(50, 300, 6) is False
    # One node of degree 4 leaves 298 of the 300 units of capacity reachable.
    degrees = [4] + [6] * 49
    assert sum(min(d, 6) for d in degrees) == 298
    assert degree_deficiency_infeasible(degrees, 300, 6) is True
    # Every node at exactly k is feasible as far as this witness can tell.
    assert degree_deficiency_infeasible([6] * 50, 300, 6) is False


def test_degree_deficiency_dominates_the_counting_bound():
    """Anything the counting bound rejects, this rejects too."""
    from ccvc.bb.bbcvc import (counting_bound_infeasible,
                               degree_deficiency_infeasible)
    for n, m, k in ((50, 400, 6), (10, 100, 3), (4, 20, 2)):
        degrees = [k] * n                      # the most generous degrees possible
        if counting_bound_infeasible(n, m, k):
            assert degree_deficiency_infeasible(degrees, m, k), (n, m, k)


def test_a_degree_deficient_run_is_infeasible_not_unresolved():
    """The run-level verdict must name the reason, not shrug."""
    # A star: the centre has degree 3, every leaf degree 1, k = 3.
    # Capacity is min(3,3) + 3*min(1,3) = 6 >= 3 edges, so the star is fine;
    # shrink k to 1 and the centre can own one edge, each leaf one, total 4 > 3.
    from ccvc.bb.bbcvc import degree_deficiency_infeasible
    star = [(1, 2), (1, 3), (1, 4)]
    deg = {1: 3, 2: 1, 3: 1, 4: 1}
    assert degree_deficiency_infeasible(deg.values(), len(star), 3) is False
    # Now a triangle with k = 1: capacity 3*min(2,1) = 3 == m, still feasible.
    assert degree_deficiency_infeasible([2, 2, 2], 3, 1) is False
    # An isolated node cannot help any edge: capacity drops below m.
    assert degree_deficiency_infeasible([2, 2, 2, 0], 4, 1) is True
