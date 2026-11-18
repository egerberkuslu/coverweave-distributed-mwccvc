#!/usr/bin/env python3
"""WuLi-Dominating testleri: kodlama, kural, dağıtık koşum, ölçüm ve MUTASYON.

Koşum (depo kökünden):
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_v5_wuli.py -q
    WULI_SLOW=1 ...   (yoğun çizgelerdeki tarama hücreleri)

DOSYANIN İKİ YARISI VAR.

1. Doğruluk. Wu-Li'nin işaretli kümesi elle hesaplanmış altı çizgede assert
   edilir; bağımsız referans, merkezî kestirim ve GERÇEK dağıtık koşum üç yönlü
   eşitlenir. Üçü aynı kodu paylaşmaz: referans düz küme cebridir, kestirim
   kuralları taklit ağ olmadan koşar, koşum gerçek zamanlayıcı + gerçek ağ +
   gerçek serileştirme üzerinden gider. Eşitlik bu yüzden bir şey KANITLAR.

2. Ölçüm. Boyut eğrisi, Bloom yanlış pozitif oranı, parçalı görüşün karar
   değiştirme oranı. Bu testler sayıyı VARSAYMAZ, ölçer ve ölçülen değerin
   savı desteklediğini assert eder.

MUTASYON DİSİPLİNİ (BULGULAR_BB §15). Bir tuzağın yük taşıdığı, ancak kasten
bozulmuş bir sürüme karşı koşturularak gösterilebilir. Aşağıdaki her
`test_mutation_*` bir değişmezi bozar ve ilgili tuzağın ATEŞLEDİĞİNİ assert
eder. Hiçbir iddia kaynak METNİNE bakmaz; hepsi gözlenebilir etkiye bakar.
"""
from __future__ import annotations

import itertools
import math
import os
import sys
from typing import Dict, List, Sequence, Set, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import sched, simnet, v5_wuli as wuli, validate, wire  # noqa: E402
from ccvc.bb.api import MsgType, PayloadTooLarge, Role  # noqa: E402
from ccvc.bb.bbcvc import PH_COVER, macs_for  # noqa: E402
from ccvc.bb.v5_wuli import (ENC_BLOOM, ENC_CHUNK, ENC_FULL, POL_NAIVE, POL_SAFE,  # noqa: E402
                          Bloom, Knowledge, Summary, Tri, WuLiNode, WuLiParams)

SLOW = os.environ.get("WULI_SLOW") == "1"
BUDGET_MS = 3_000_000

# --------------------------------------------------------------------------
# elle hesaplanmış birim çizgeler
# --------------------------------------------------------------------------
P5 = [(1, 2), (2, 3), (3, 4), (4, 5)]
STAR = [(1, 2), (1, 3), (1, 4), (1, 5)]
K4 = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
BOWTIE = [(1, 2), (1, 3), (2, 3), (3, 4), (4, 5), (4, 6), (5, 6)]
GRID4 = [(1, 2), (2, 3), (3, 4), (5, 6), (6, 7), (7, 8), (9, 10), (10, 11),
         (11, 12), (13, 14), (14, 15), (15, 16), (1, 5), (2, 6), (3, 7), (4, 8),
         (5, 9), (6, 10), (7, 11), (8, 12), (9, 13), (10, 14), (11, 15), (12, 16)]
#: üçgen + iki sarkan: Rule-1 budamasının GERÇEKTEN ateşlediği en küçük örnek
PRUNE4 = [(1, 2), (1, 3), (2, 3), (3, 4), (2, 4)]

#: Elle türetilmiş beklentiler. Gerekçeleri testlerin docstring'lerinde.
EXPECTED = {
    "P5": {"marked": {2, 3, 4}, "pruned": set(), "backbone": {2, 3, 4}},
    "STAR": {"marked": {1}, "pruned": set(), "backbone": {1}},
    "K4": {"marked": set(), "pruned": set(), "backbone": set()},
    "BOWTIE": {"marked": {3, 4}, "pruned": set(), "backbone": {3, 4}},
    "GRID4": {"marked": set(range(1, 17)), "pruned": set(),
              "backbone": set(range(1, 17))},
    "PRUNE4": {"marked": {2, 3}, "pruned": {2}, "backbone": {3}},
}
GRAPHS = {"P5": P5, "STAR": STAR, "K4": K4, "BOWTIE": BOWTIE, "GRID4": GRID4,
          "PRUNE4": PRUNE4}


def unit_weights(edges) -> Dict[int, float]:
    return {v: 1.0 for v in wuli.adjacency(edges)}


def ref_of(edges, weights=None):
    adj = wuli.adjacency(edges, list(weights) if weights else None)
    w = weights or {v: 1.0 for v in adj}
    return wuli.reference_backbone(adj, wuli.keys_of(adj, w))


# --------------------------------------------------------------------------
# ÖNCÜLÜ AÇIK ÖRNEK KURMA
# --------------------------------------------------------------------------
# Bir testin "üretilen bu örneğin şu özelliği var" varsayımına yaslanması
# KIRILGANdır: üreteç, tohum işleme ya da yoğunluk değişince öncül sessizce
# yanlışlanır ve test, sınadığı şey bozulmuş gibi düşer. Bugün tam olarak bu
# oldu (r=0,45 azami derece 30 verdi, oysa yorum "> 32" diyordu), dolayısıyla
# aşağıdaki iki yol kullanılır: ya özellik İNŞA GEREĞİ sağlanır (yıldız), ya da
# sağlayan örnek ARANIR ve bulunamazsa hata "şu özellikte çizge kurulamadı"
# diye okunur, "algoritma bozuldu" diye değil.

def star_with_degree(deg: int):
    """`deg` yapraklı yıldız: merkezin derecesi TANIM GEREĞİ `deg`.

    Üreteçten bağımsızdır, tohum tutmaz, 0,7 saniyede koşar. Wu-Li için
    dejenere bir çizgedir (yalnız merkez işaretlenir) ve testler bunu
    kullandıkları yerde bilerek kullanır: sınanan şey omurga kalitesi değil,
    yüksek dereceli bir düğümün özetinin telden geçmesidir.
    """
    edges = [(1, i) for i in range(2, deg + 2)]
    weights = {v: 1.0 for v in range(1, deg + 2)}
    adj = wuli.adjacency(edges, list(weights))
    assert max(len(a) for a in adj.values()) == deg
    return edges, weights


_DENSE_SHAPES = ((40, 0.50), (50, 0.50), (60, 0.50), (60, 0.55), (80, 0.50),
                 (100, 0.45), (120, 0.40))


def instance_with_max_degree(lo: int, hi=None, *, seeds=range(4)):
    """Azami derecesi [lo, hi] aralığına düşen BAĞLI bir UDG bul.

    Bulunamazsa hata mesajı öncülü söyler; böylece bir başarısızlık "bu koşulu
    sağlayan çizge üretilemedi" diye okunur ve sınanan mantıkla karıştırılmaz.
    """
    tried = []
    for n, radius in _DENSE_SHAPES:
        for seed in seeds:
            edges, weights = wuli.connected_udg(n, radius, seed)
            adj = wuli.adjacency(edges, list(weights))
            deg = max(len(a) for a in adj.values())
            tried.append(deg)
            if deg >= lo and (hi is None or deg <= hi):
                return edges, weights, deg
    raise AssertionError(
        f"azami derecesi {lo}..{hi} olan bağlı bir UDG kurulamadı; "
        f"denenen şekillerin dereceleri: {sorted(set(tried))}. Bu bir ÖNCÜL "
        f"hatasıdır, sınanan mantığın hatası değildir.")


# ==========================================================================
# 1. BLOOM
# ==========================================================================
def test_bloom_has_no_false_negatives():
    """Bloom'un TEK garantisi budur ve her şey buna dayanır: üye ASLA NO almaz."""
    for seed in range(20):
        ids = sorted({(seed * 7919 + i * 104729) % 65536 for i in range(40)})
        f = Bloom.of(ids)
        for x in ids:
            assert f.query(x) is not Tri.NO, (seed, x)


def test_bloom_never_answers_yes():
    """Bloom YES veremez; bu, `safe` ilkesinde budamayı imkânsız kılan olgudur."""
    f = Bloom.of([1, 2, 3])
    assert {f.query(x) for x in range(2000)} <= {Tri.NO, Tri.MAYBE}
    assert f.query(1) is Tri.MAYBE          # üye bile yalnız MAYBE


def test_bloom_is_constant_size_and_round_trips():
    for deg in (0, 1, 36, 120):
        f = Bloom.of(range(deg))
        assert len(f.to_words()) == 32              # 64 B = 32 sözcük, SABİT
        g = Bloom.from_words(f.to_words())
        assert g.bits == f.bits
        for x in range(deg):
            assert g.query(x) is not Tri.NO


def test_bloom_word_packing_survives_the_real_wire():
    """Özet gerçek `wire` kodlayıcısından geçip aynen geri gelmeli."""
    words = wuli.encode_summary(ENC_BLOOM, list(range(36)), True)
    payload = wire.encode(wire.Hello(src=7, key=100, deg=36, role=Role.OUT,
                                     phase=1, load=0, mis_nbrs=words))
    back = wire.decode(payload)
    assert back.mis_nbrs == words
    enc, marked, total, index = wuli.unpack_header(back.mis_nbrs[0])
    assert (enc, marked, total, index) == (ENC_BLOOM, True, 1, 0)
    f = Bloom.from_words(back.mis_nbrs[1:])
    assert all(f.query(x) is not Tri.NO for x in range(36))


@pytest.mark.parametrize("deg", [20, 36, 60])
def test_bloom_measured_fpr_tracks_the_formula(deg):
    """ÖLÇÜLEN yanlış pozitif oranı formülün 3 katı içinde olmalı.

    Bu tuzak bir hatayı YAKALADI: ilk konum türetimi Kirsch-Mitzenmacher çifte
    karmasıydı ve m=512'de ölçülen oran derece 10'da formülün BİN KATIYDI.
    Sınır bilerek gevşektir (3 kat), çünkü ölçüm örneklemdir; yakalaması
    gereken şey büyüklük mertebesi hatasıdır.
    """
    measured = wuli.measure_bloom_fpr(deg, trials=120, probes=400, seed=deg)
    formula = wuli.bloom_fpr_formula(deg)
    assert measured <= 3 * formula + 1e-4, (deg, measured, formula)
    assert measured >= formula / 5 - 1e-4, (deg, measured, formula)


def test_two_sided_query_is_measurably_better_than_one_sided():
    """`Knowledge.adjacent` iki özete birden sorar; kazancı ÖLÇÜLÜR, varsayılmaz."""
    one = wuli.measure_bloom_fpr(60, trials=150, probes=400, seed=3)
    two = wuli.measure_bloom_fpr(60, trials=150, probes=400, seed=3, two_sided=True)
    assert one > 5e-3, one                      # tek taraflı bu derecede ciddi
    assert two < one / 5, (one, two)            # iki taraflı en az 5 kat iyi


# ==========================================================================
# 2. KODLAMA VE ÖZET
# ==========================================================================
def test_header_round_trip_and_rejection():
    for enc in wuli.ENCODINGS:
        for marked in (False, True):
            for total, index in ((1, 0), (5, 4), (63, 62)):
                w = wuli.pack_header(enc, marked, total, index)
                assert 0 <= w <= 0xFFFF
                assert wuli.unpack_header(w) == (enc, marked, total, index)
    with pytest.raises(ValueError):
        wuli.pack_header(ENC_FULL, False, 3, 3)      # index >= total
    with pytest.raises(ValueError):
        wuli.pack_header(ENC_FULL, False, 64, 0)     # total 6 bite sığmaz


def test_full_encoding_carries_every_id_without_truncation():
    ids = list(range(1000, 1000 + 40))
    words = wuli.encode_summary(ENC_FULL, ids, False)
    assert len(words) == 41                      # başlık + 40 id, KIRPMA YOK
    s = Summary(enc=ENC_FULL)
    s.absorb(words)
    assert s.complete and s.ids == set(ids)
    assert s.query(1000) is Tri.YES
    assert s.query(999) is Tri.NO                # tam liste KESİN NO verir


def test_chunked_view_is_maybe_until_every_chunk_arrives():
    """Parçalının belirsizliği TERS yöndedir: gelmemiş parçadaki id NO değil MAYBE."""
    ids = list(range(10))
    s = Summary(enc=ENC_CHUNK)
    for i in range(3):
        s.absorb(wuli.encode_summary(ENC_CHUNK, ids, False, index=i, chunk_words=2))
        assert not s.complete
        assert s.query(9) is Tri.MAYBE           # son parça gelmedi: BİLİNMİYOR
        assert s.query(0) is Tri.YES             # gelen parçada: KESİN
    for i in (3, 4):
        s.absorb(wuli.encode_summary(ENC_CHUNK, ids, False, index=i, chunk_words=2))
    assert s.complete
    assert s.query(9) is Tri.YES
    assert s.query(99) is Tri.NO                 # artık kesin yokluk


def test_chunk_count_and_cycle():
    assert wuli.chunk_count(0, 8) == 1
    assert wuli.chunk_count(8, 8) == 1
    assert wuli.chunk_count(9, 8) == 2
    assert wuli.chunk_count(36, 8) == 5


def test_tri_resolution_is_the_only_place_policy_lives():
    assert wuli.resolve(Tri.YES, POL_SAFE) and wuli.resolve(Tri.YES, POL_NAIVE)
    assert not wuli.resolve(Tri.NO, POL_SAFE) and not wuli.resolve(Tri.NO, POL_NAIVE)
    assert not wuli.resolve(Tri.MAYBE, POL_SAFE)   # kesinlik yoksa hayır
    assert wuli.resolve(Tri.MAYBE, POL_NAIVE)      # belirsizi kabul et
    with pytest.raises(ValueError):
        wuli.resolve(Tri.YES, "belki")


# ==========================================================================
# 3. KURALLAR: elle hesaplanmış çizgeler
# ==========================================================================
@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_reference_matches_hand_computation(name):
    """Altı çizgenin işaretli/budanmış/omurga kümeleri ELLE türetilmiştir.

    P5: uçlar derece 1, ortadaki üçünün komşuları bitişik değil -> {2,3,4}.
    STAR: yalnız merkez; yapraklar derece 1.
    K4: HİÇ KİMSE işaretlenmez, çünkü her düğümün komşuları birbirine bitişik.
        Wu-Li'nin bilinen dejenere durumudur (tam çizgede işaretli küme boştur
        ve baskın DEĞİLDİR); Faz 2 örtüyü yine de kurar, ayrı test eder.
    BOWTIE: yalnız köprünün iki ucu {3,4}; üçgen içleri bitişik.
    GRID4: ızgara ÜÇGENSİZDİR, dolayısıyla her düğüm işaretlenir ve Rule-k
        hiç ateşleyemez (iki komşusu bitişik olan düğüm yok). Omurga = V.
    PRUNE4: 2 ve 3 işaretlenir; N[2] = N[3] = {1,2,3,4} olduğundan küçük
        anahtarlı olan (2) budanır, 3 kalır.
    """
    exp = EXPECTED[name]
    got = ref_of(GRAPHS[name])
    assert got["marked"] == exp["marked"]
    assert got["pruned"] == exp["pruned"]
    assert got["backbone"] == exp["backbone"]


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_prediction_with_full_encoding_equals_reference(name):
    """`full` kodlamasında MAYBE yoktur, dolayısıyla iki ilke de referansa eşit.

    Bu, kural katmanının (Knowledge) bağımsız referansla aynı algoritmayı
    gerçeklediğinin kanıtıdır; ikisi hiçbir kod paylaşmaz.
    """
    edges = GRAPHS[name]
    adj = wuli.adjacency(edges)
    keys = wuli.keys_of(adj, unit_weights(edges))
    ref = wuli.reference_backbone(adj, keys)
    for policy in (POL_SAFE, POL_NAIVE):
        pred = wuli.predict_backbone(adj, keys, ENC_FULL, policy)
        assert pred["marked"] == ref["marked"], (name, policy)
        assert pred["backbone"] == ref["backbone"], (name, policy)


def test_key_tiebreak_prevents_mutual_pruning():
    """PRUNE4'te 2 ve 3'ün kapalı komşulukları AYNI; ikisi de budanırsa omurga
    boşalır ve baskınlık gider. Anahtar sıralaması bunu imkânsız kılar."""
    got = ref_of(PRUNE4)
    assert got["pruned"] == {2}
    assert got["backbone"] == {3}
    adj = wuli.adjacency(PRUNE4)
    assert wuli.is_dominating(adj, got["backbone"])


def test_complete_graph_is_wuli_degenerate_case_but_cover_is_still_valid():
    """K_n'de omurga BOŞtur (Wu-Li'nin önkoşulu tam çizgede sağlanmaz).

    Bu bir hata değil, algoritmanın bilinen sınırıdır ve GİZLENMEZ: Faz 2 her
    kenarın küçük anahtarlı ucunu örtüye aldığından sonuç yine geçerli bir
    bağlı örtüdür. Yani boş omurga kalite kaybıdır, doğruluk kaybı değil.
    """
    weights = unit_weights(K4)
    adj = wuli.adjacency(K4)
    keys = wuli.keys_of(adj, weights)
    assert wuli.reference_backbone(adj, keys)["backbone"] == set()
    cover = wuli.cover_from_backbone(adj, keys, set())
    assert len(cover) == 3 and wuli.is_connected_subset(adj, cover)
    g = validate.make_graph(K4, 3, weights)
    assert validate.validate(g, sorted(cover)).vertex_cover


# ==========================================================================
# 4. SAFE+BLOOM DEJENERASYONU (türetim + ölçüm)
# ==========================================================================
@pytest.mark.parametrize("name", ["P5", "BOWTIE", "GRID4", "PRUNE4"])
def test_safe_bloom_degenerates_to_all_nodes_with_degree_at_least_two(name):
    """Bloom YES veremez; `safe` MAYBE'yi hayır sayar. Sonuç ZORUNLUDUR:

      * her komşu çifti "bitişik değil" görünür -> derece >= 2 olan herkes işaretlenir,
      * örtülülük YES ister, bloom veremez -> HİÇ budama olmaz.

    Yani 64 baytın bedeli boyut değil KALİTEdir. Burada ölçülen tam olarak bu.
    """
    edges = GRAPHS[name]
    adj = wuli.adjacency(edges)
    keys = wuli.keys_of(adj, unit_weights(edges))
    pred = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_SAFE)
    assert pred["backbone"] == {v for v in adj if len(adj[v]) >= 2}
    assert pred["pruned"] == set()


def test_safe_bloom_backbone_is_still_a_connected_dominating_set():
    """Dejenere ama GÜVENLİ: yapraksız alt çizge bağlı ve baskındır."""
    for n, r, seed in ((20, 0.38, 0), (30, 0.30, 1), (30, 0.30, 2)):
        edges, weights = wuli.connected_udg(n, r, seed)
        adj = wuli.adjacency(edges, list(weights))
        keys = wuli.keys_of(adj, weights)
        b = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_SAFE)["backbone"]
        assert wuli.is_dominating(adj, b)
        assert wuli.is_connected_subset(adj, b)


def test_safe_policy_never_shrinks_the_backbone_below_the_reference():
    """`safe` belirsizliği hep omurgayı BÜYÜTEN yönde çözer.

    İddia küme kapsaması DEĞİL, CDS özelliğidir: budama adayları da
    değiştiğinden kapsama her zaman tutmaz, ama baskınlık ve bağlılık tutmak
    ZORUNDADIR; brief §5/1'in güvenlik savı tam olarak budur.
    """
    for enc in (ENC_BLOOM, ENC_CHUNK):
        for seed in range(6):
            edges, weights = wuli.connected_udg(25, 0.34, seed)
            adj = wuli.adjacency(edges, list(weights))
            keys = wuli.keys_of(adj, weights)
            b = wuli.predict_backbone(adj, keys, enc, POL_SAFE,
                                      chunks_seen=1, chunk_words=2)["backbone"]
            assert wuli.is_dominating(adj, b), (enc, seed)
            assert wuli.is_connected_subset(adj, b), (enc, seed)


# ==========================================================================
# 5. DAĞITIK KOŞUM: üç yönlü eşitlik
# ==========================================================================
def run(edges, weights, k, **kw) -> wuli.WuLiRun:
    kw.setdefault("max_ms", BUDGET_MS)
    return wuli.run_wuli(edges, weights, k, **kw)


@pytest.mark.parametrize("scheduler", ["sync", "async"])
@pytest.mark.parametrize("name", ["P5", "STAR", "BOWTIE", "PRUNE4"])
def test_distributed_full_run_equals_reference_and_prediction(name, scheduler):
    """Referans == merkezî kestirim == GERÇEK dağıtık koşum.

    Üçü ayrı yollardır: küme cebri, kural katmanı, gerçek ağ + zamanlayıcı +
    serileştirme. Eşitlik bu yüzden taklitle örtüşme değil, kanıttır.
    """
    edges = GRAPHS[name]
    weights = unit_weights(edges)
    adj = wuli.adjacency(edges)
    keys = wuli.keys_of(adj, weights)
    k = max(2, max(len(a) for a in adj.values()))
    r = run(edges, weights, k, scheduler=scheduler,
            params=WuLiParams(encoding=ENC_FULL))
    assert r.converged, name
    assert set(r.backbone) == EXPECTED[name]["backbone"]
    assert set(r.marked) == EXPECTED[name]["marked"]
    assert r.backbone_divergence == ()
    pred = wuli.predict_backbone(adj, keys, ENC_FULL, POL_SAFE)
    assert set(r.backbone) == pred["backbone"]


@pytest.mark.parametrize("scheduler", ["sync", "async"])
@pytest.mark.parametrize("encoding", list(wuli.ENCODINGS))
@pytest.mark.parametrize("policy", [POL_SAFE, POL_NAIVE])
def test_every_encoding_and_policy_produces_a_valid_cover(encoding, policy, scheduler):
    """Altı hücre × iki zamanlayıcı: doğrulayıcı sıfır ihlal vermeli."""
    edges, weights = wuli.connected_udg(20, 0.38, 0)
    adj = wuli.adjacency(edges, list(weights))
    k = max(len(a) for a in adj.values())
    r = run(edges, weights, k, scheduler=scheduler,
            params=WuLiParams(encoding=encoding, policy=policy, chunk_words=4))
    assert r.converged
    g = validate.make_graph(edges, k, weights)
    rep = validate.validate(g, r.cover, r.owner)
    assert rep.valid, f"{encoding}/{policy}/{scheduler}: {rep.summary()}"
    assert len(r.owner) == len(edges)


@pytest.mark.parametrize("encoding", list(wuli.ENCODINGS))
def test_sync_and_async_agree_on_the_backbone(encoding):
    """Faz 1 belirlenimcidir: iki saat aynı omurgayı vermeli (brief §3.2)."""
    edges, weights = wuli.connected_udg(25, 0.34, 3)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    p = WuLiParams(encoding=encoding, chunk_words=4)
    a = run(edges, weights, k, scheduler="sync", params=p)
    b = run(edges, weights, k, scheduler="async", params=p)
    assert a.converged and b.converged
    assert a.backbone == b.backbone, (encoding, a.backbone, b.backbone)


def test_role_never_moves_backwards_even_though_wuli_unmarks(monkeypatch):
    """api I5: rol YALNIZ ileri gider. Wu-Li budaması bir İŞARETİ kaldırır.

    Budama rolü geri almasaydı bu test boş geçerdi; bu yüzden aynı koşumda
    GERÇEKTEN budanmış bir düğüm olduğu da assert edilir (PRUNE4'te düğüm 2).
    """
    seen: Dict[int, List[int]] = {}

    class Recording(WuLiNode):
        def on_timer(self, name: str = "tick") -> None:
            seen.setdefault(self.nid, []).append(int(self.role))
            super().on_timer(name)
            seen[self.nid].append(int(self.role))

    weights = unit_weights(PRUNE4)
    ids = sorted(weights)
    net = simnet.SimNet(ids, PRUNE4, loss=0.0, seed=0,
                        delay=simnet.fixed_delay(1), macs=macs_for(ids))
    p = WuLiParams(encoding=ENC_FULL)
    nodes = {nid: Recording(weights[nid], net.port(nid), p, 3) for nid in ids}
    out = sched.SyncScheduler(net, nodes, tau_ms=200, weights=weights).run(BUDGET_MS)
    assert out.converged
    assert any(n._wl_pruned_by is not None for n in nodes.values()), "budama olmadı"
    for nid, hist in seen.items():
        assert hist == sorted(hist), (nid, hist)      # monoton artan
    # 2 işaretlendi, sonra budandı: omurgaya GİRMEDİ. Faz 2 onu ayrıca COVER
    # yapabilir (yapar da), ama bu İLERİ yönde bir geçiştir; budama rolü geri
    # almaz, yalnız MIS'e terfiyi engeller.
    assert nodes[2]._wl_marked and nodes[2]._wl_pruned_by is not None
    assert not nodes[2].role.in_backbone
    assert nodes[3].role == Role.MIS


# ==========================================================================
# 6. BLOOM YANLIŞ POZİTİFİ ÖRTÜYÜ GEÇERSİZ KILABİLİR (baş bulgu)
# ==========================================================================
#: 4 baytlık filtre brief'in 64 baytı DEĞİLDİR; mekanizmayı görünür kılmak için
#: küçültülmüştür. 64 bayt bu derecelerde yanlış pozitif üretmiyor (ayrı test).
_TINY_BLOOM = 4
_SCAN = tuple(range(25))
_broken_cache: List[int] = []


def instances_where_naive_bloom_breaks_connectivity(limit: int = 2) -> List[int]:
    """Merkezî tarama: hangi tohumlarda kopuk örtü KESTİRİLİYOR?

    Tohum SABİTLENMEZ, ARANIR. İlk hâlde 16 ve 17 gömülüydü; üreteç değişse o
    iki tohum sessizce geçerli örnekler üretir ve "bu örnek geçersiz olmalıydı"
    diye düşen bir test, aslında bozulmayan bir mekanizmayı suçlardı. Arama
    ucuzdur (tarama başına ~0,03 s) ve öncül bulunamazsa hata bunu söyler.
    """
    if not _broken_cache:
        for seed in _SCAN:
            edges, weights = wuli.connected_udg(30, 0.28, seed)
            adj = wuli.adjacency(edges, list(weights))
            keys = wuli.keys_of(adj, weights)
            sc = wuli.screen_instance(adj, keys, ENC_BLOOM, POL_NAIVE,
                                      bloom_bytes=_TINY_BLOOM)
            if not sc["cover_connected"]:
                _broken_cache.append(seed)
        assert _broken_cache, (
            f"{len(_SCAN)} tohumun hiçbirinde {_TINY_BLOOM} baytlık filtre kopuk "
            f"örtü kestirmedi; yanlış pozitif mekanizmasını gösteren bir örnek "
            f"KURULAMADI. Bu bir ÖNCÜL hatasıdır: ya üreteç ya da filtre değişti.")
    return _broken_cache[:limit]


def test_naive_bloom_false_positive_produces_an_invalid_cover():
    """YANLIŞ POZİTİF YALNIZ KALİTE KAYBI DEĞİL, GEÇERSİZLİK ÜRETİR.

    Zincir: bloom "bit dolu" -> `naive` bunu "bitişik" sayar -> düğüm bitişik
    olmayan komşu çiftini bulamaz -> İŞARETLENMEZ -> omurga CDS olmaktan çıkar
    -> Faz 2'nin G2 savı (bir ucu C'ye girince bağlılık korunur) çöker -> G[C]
    KOPUK. Doğrulayıcı bunu `disconnected` olarak yakalar ve kopan bileşeni
    adıyla söyler; deney bu oranı raporlar, gizlemez.
    """
    seeds = instances_where_naive_bloom_breaks_connectivity()
    shown = 0
    for seed in seeds:
        edges, weights = wuli.connected_udg(30, 0.28, seed)
        adj = wuli.adjacency(edges, list(weights))
        k = max(len(a) for a in adj.values())
        r = run(edges, weights, k, params=WuLiParams(
            encoding=ENC_BLOOM, policy=POL_NAIVE, bloom_bytes=_TINY_BLOOM))
        assert r.converged
        g = validate.make_graph(edges, k, weights)
        rep = validate.validate(g, r.cover, r.owner)
        if rep.valid:
            # Kestirim kopuk dedi, koşum geçerli çıktı: Faz 3/4'ün eklediği
            # düğümler bağlılığı kazara onarmış olabilir (screen_instance bunu
            # docstring'inde söylüyor). Bu bir hata değil, bu tohumun konu dışı
            # olmasıdır; başka tohuma bak.
            continue
        shown += 1
        disc = rep.by_kind(validate.DISCONNECTED)
        assert disc, sorted({v.kind for v in rep.violations})
        assert sum(len(v.nodes) for v in disc) == len(r.cover)
        assert len(r.backbone_divergence) > 0
        # aynı örnek `safe` ile GEÇERLİ olmalı: fark ilkede, çizgede değil
        safe = run(edges, weights, k, params=WuLiParams(
            encoding=ENC_BLOOM, policy=POL_SAFE, bloom_bytes=_TINY_BLOOM))
        assert validate.validate(g, safe.cover, safe.owner).valid
        # ve tam listeyle de GEÇERLİ: kusur çizgede değil KODLAMADA
        full = run(edges, weights, k, params=WuLiParams(
            encoding=ENC_FULL, policy=POL_NAIVE))
        assert validate.validate(g, full.cover, full.owner).valid
        assert full.backbone_divergence == ()
    assert shown, (
        f"kestirimin kopuk dediği {len(seeds)} örneğin hiçbiri gerçek koşumda "
        f"geçersiz çıkmadı; yanlış pozitifin GEÇERSİZLİK ürettiği "
        f"GÖSTERİLEMEDİ")


def test_sixtyfour_byte_bloom_is_accidentally_safe_at_our_degrees():
    """Brief'in 64 baytı BU kıyas aralığında yanlış pozitif üretmiyor.

    Bu bir garanti DEĞİL, ölçülmüş bir kaza: aynı mekanizma 4 baytta aynı
    çizgelerde geçersizlik üretiyor (üstteki test). Rapor bunu "güvenli" diye
    değil, "bu derecelerde gözlenmedi" diye yazmalıdır.
    """
    bad = 0
    for seed in range(8):
        edges, weights = wuli.connected_udg(30, 0.28, seed)
        adj = wuli.adjacency(edges, list(weights))
        keys = wuli.keys_of(adj, weights)
        ref = wuli.reference_backbone(adj, keys)["backbone"]
        pred = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_NAIVE)["backbone"]
        bad += (pred != ref)
    assert bad == 0, (
        f"64 baytlık filtre bu derecelerde {bad} örnekte sapma verdi; "
        f"'bu aralıkta gözlenmedi' savı artık doğru değil, rapor güncellenmeli")
    # ve aynı taramada 4 bayt BOZULUYOR: ölçüt gerçekten ayırt ediyor
    small = 0
    for seed in range(8):
        edges, weights = wuli.connected_udg(30, 0.28, seed)
        adj = wuli.adjacency(edges, list(weights))
        keys = wuli.keys_of(adj, weights)
        ref = wuli.reference_backbone(adj, keys)["backbone"]
        pred = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_NAIVE,
                                     bloom_bytes=4)["backbone"]
        small += (pred != ref)
    assert small >= 4, (
        f"4 baytlık filtre 8 örneğin yalnız {small}'inde saptı; ölçüt 64 bayt "
        f"ile 4 baytı ARTIK AYIRT ETMİYOR, dolayısıyla üstteki 'sapma yok' "
        f"iddiası bir şey kanıtlamıyor")


# ==========================================================================
# 7. BOYUT: şekil 6 verisi ve GERÇEK sınırlar
# ==========================================================================
def test_size_curve_is_computed_through_the_real_encoder():
    """Boyutlar `wire.hello_size` ile hesaplanır; formül ikinci kez yazılmaz."""
    for d in (0, 5, 36, 117):
        words = wuli.encode_summary(ENC_FULL, list(range(d)), False)
        payload = wire.encode(wire.Hello(src=1, key=1, deg=min(d, 255),
                                         role=Role.OUT, phase=1, load=0,
                                         mis_nbrs=words))
        assert len(payload) == wuli.frame_bytes(ENC_FULL, d)


def test_bloom_is_bigger_than_the_full_list_below_degree_33():
    """ÖLÇÜLEN ters sonuç: kıyas kümesinin ortalama derecelerinde (6-16) sabit
    64 baytlık özet, yerine geçtiği KESİN listeden DAHA BÜYÜKTÜR."""
    assert wuli.frame_bytes(ENC_BLOOM, 0) == 79
    cross = min(d for d in range(1, 200) if wuli.frame_bytes(ENC_FULL, d) >= 79)
    assert cross == 32                       # 13 + 2*(1+32) = 79, tam eşitlik
    for d in (5, 10, 16, 31):
        assert wuli.frame_bytes(ENC_FULL, d) < wuli.frame_bytes(ENC_BLOOM, d)
    for d in (40, 60, 117):
        assert wuli.frame_bytes(ENC_FULL, d) > wuli.frame_bytes(ENC_BLOOM, d)


def test_full_list_crosses_the_250_byte_limit_and_the_wire_raises():
    """Sınırın TUTTUĞU değil, AŞILDIĞINDA NE OLDUĞU test edilir.

    117 komşuya kadar sığar, 118'de `wire` PayloadTooLarge yükseltir. Kırpma
    yoktur: kırpılmış bir komşu listesi Wu-Li'nin işaretleme kuralını sessizce
    yanlış cevaplardı.
    """
    assert wuli.max_degree_within_limit(ENC_FULL) == 117
    ok = wuli.encode_summary(ENC_FULL, list(range(117)), False)
    assert len(wire.encode(wire.Hello(src=1, key=1, deg=117, role=Role.OUT,
                                      phase=1, load=0, mis_nbrs=ok))) == 249
    big = wuli.encode_summary(ENC_FULL, list(range(118)), False)
    assert len(big) == 119                      # üretici KIRPMADI
    with pytest.raises(PayloadTooLarge):
        wire.encode(wire.Hello(src=1, key=1, deg=118, role=Role.OUT, phase=1,
                               load=0, mis_nbrs=big))


def test_the_neighbour_table_cap_binds_long_before_the_wire_limit():
    """BULGU: bu gerçeklemede 250 B sınırına ULAŞILAMAZ.

    Komşu tablosu 64 giriştir (`nbr_table_max`, brief §3.6) ve taşması koşumu
    zaten geçersiz kılar. 64 komşulu tam liste 143 bayttır, yani telin sınırının
    yarısından az. Brief §5'in "yoğun çizgede 250 B aşılır" cümlesi ancak tablo
    sınırı da büyütülürse geçerlidir; ikisi birlikte raporlanmalıdır.
    """
    cap = WuLiParams().nbr_table_max
    assert cap == 64
    assert wuli.frame_bytes(ENC_FULL, cap) == 143 <= wire.MAX_PAYLOAD
    assert wuli.max_degree_within_limit(ENC_FULL) > cap


def test_constant_size_encodings_are_really_constant():
    sizes_bloom = {wuli.frame_bytes(ENC_BLOOM, d) for d in range(0, 200, 7)}
    assert sizes_bloom == {79}
    sizes_chunk = {wuli.frame_bytes(ENC_CHUNK, d) for d in range(8, 200, 7)}
    assert sizes_chunk == {31}                  # 8 id + başlık
    assert wuli.max_degree_within_limit(ENC_BLOOM) is None
    assert wuli.max_degree_within_limit(ENC_CHUNK) is None


def test_size_curve_rows_carry_what_figure_six_needs():
    rows = wuli.size_curve([10, 36, 120], chunk_burst=True)
    by = {(r["degree"], r["encoding"]): r for r in rows}
    assert by[(120, ENC_FULL)]["over_limit"] is True
    assert by[(120, ENC_BLOOM)]["over_limit"] is False
    assert by[(36, ENC_CHUNK)]["chunks"] == 5
    assert by[(36, ENC_CHUNK)]["bytes_per_period"] == 5 * 31
    assert by[(36, ENC_FULL)]["bytes_per_period"] == wuli.frame_bytes(ENC_FULL, 36)


# ==========================================================================
# 8. PARÇALAMA: iki tasarım, iki bedel
# ==========================================================================
def test_round_robin_chunking_costs_no_extra_transmissions():
    """Sıra ile parçalama `tx`i ARTIRMAZ; bedeli gecikmedir."""
    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    full = run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
    chunk = run(edges, weights, k,
                params=WuLiParams(encoding=ENC_CHUNK, chunk_words=2))
    assert chunk.tx == full.tx
    assert chunk.max_payload < full.max_payload
    assert chunk.bytes_tx < full.bytes_tx


def test_burst_chunking_multiplies_transmissions_as_the_brief_predicts():
    """Topluca parçalama brief §5/2'nin dediğini yapar: `tx` katlanır."""
    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    base = run(edges, weights, k,
               params=WuLiParams(encoding=ENC_CHUNK, chunk_words=2))
    burst = run(edges, weights, k,
                params=WuLiParams(encoding=ENC_CHUNK, chunk_words=2,
                                  chunk_burst=True))
    assert burst.tx > 1.5 * base.tx, (base.tx, burst.tx)
    assert burst.max_payload == base.max_payload      # çerçeve yine küçük


def test_partial_view_is_real_and_only_over_marks():
    """Parça döngüsü karar penceresinden UZUNSA düğümler kısmi görüşle karar verir.

    Ölçülen: kısmi görüş kararı DEĞİŞTİRİR (omurga referanstan farklıdır) ama
    farkın yönü hep aynıdır -- parçalının belirsizliği yanlış NEGATİF olduğundan
    yalnız FAZLA işaretleme üretir, eksik değil. Geçerlilik korunur.
    """
    edges, weights = wuli.connected_udg(20, 0.38, 0)
    adj = wuli.adjacency(edges, list(weights))
    k = max(len(a) for a in adj.values())
    r = run(edges, weights, k,
            params=WuLiParams(encoding=ENC_CHUNK, chunk_words=1))
    assert r.chunk_cycle > r.frames_at_decision      # pencere gerçekten dar
    assert r.partial_decisions > 0
    assert len(r.backbone) >= len(r.reference_backbone)
    g = validate.make_graph(edges, k, weights)
    assert validate.validate(g, r.cover, r.owner).valid
    # geniş parça: döngü pencereye sığar, karar tam listeyle aynı olur
    wide = run(edges, weights, k,
               params=WuLiParams(encoding=ENC_CHUNK, chunk_words=4))
    assert wide.backbone_divergence == ()


def test_chunk_wait_trades_divergence_for_latency():
    """`chunk_wait` kararı erteler; ertelemenin bir üst sınırı vardır."""
    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    p = WuLiParams(encoding=ENC_CHUNK, chunk_words=1, chunk_wait=True)
    r = run(edges, weights, k, params=p)
    assert r.converged
    g = validate.make_graph(edges, k, weights)
    assert validate.validate(g, r.cover, r.owner).valid
    assert r.slots is not None


# ==========================================================================
# 9. MUTASYON: tuzakların yük taşıdığının kanıtı
# ==========================================================================
def test_mutation_safe_policy_collapsed_into_naive_is_caught(monkeypatch):
    """`resolve` bozulup MAYBE'yi EVET sayarsa safe+bloom dejenerasyonu kaybolur.

    Dejenerasyon testi bu mutasyona karşı ATEŞLEMELİDİR; ateşlemiyorsa o test
    hiçbir şey kanıtlamıyor demektir.
    """
    edges = BOWTIE
    adj = wuli.adjacency(edges)
    keys = wuli.keys_of(adj, unit_weights(edges))
    healthy = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_SAFE)["backbone"]
    assert healthy == {v for v in adj if len(adj[v]) >= 2}

    monkeypatch.setattr(wuli, "resolve", lambda t, policy: t is not Tri.NO)
    mutated = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_SAFE)["backbone"]
    assert mutated != healthy, "mutasyon gözlenebilir bir fark üretmedi"


def test_mutation_double_hashing_bloom_is_measurably_worse(monkeypatch):
    """Konum türetimi eski (çifte karma) hâline döndürülürse ÖLÇÜM bozulmayı görür.

    Bu, düzeltmenin nereye yazıldığına değil, ETKİYE bakan bir tuzaktır: yanlış
    pozitif oranı derece 10'da büyüklük mertebesi atlar.
    """
    from ccvc.bb.v5_wuli import _mix32

    def double_hash_positions(self, x: int):
        h1 = _mix32(x)
        h2 = _mix32(x ^ 0x9E3779B9) | 1
        return tuple((h1 + i * h2) % self.nbits for i in range(self.k))

    good = wuli.measure_bloom_fpr(10, trials=150, probes=400, seed=11)
    monkeypatch.setattr(Bloom, "_positions", double_hash_positions)
    bad = wuli.measure_bloom_fpr(10, trials=150, probes=400, seed=11)
    assert bad > good + 1e-5, (good, bad)
    assert bad > 20 * wuli.bloom_fpr_formula(10)


def test_mutation_bloom_claiming_certainty_is_caught(monkeypatch):
    """Bloom YES demeye başlarsa `safe` budamaya başlar ve dejenerasyon kaybolur."""
    monkeypatch.setattr(
        Bloom, "query",
        lambda self, x: Tri.NO if any(
            not (self.bits[p >> 3] >> (p & 7)) & 1 for p in self._positions(x))
        else Tri.YES)
    adj = wuli.adjacency(PRUNE4)
    keys = wuli.keys_of(adj, unit_weights(PRUNE4))
    mutated = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_SAFE)
    assert mutated["pruned"] != set(), "mutasyon budamayı açmadı"


def test_mutation_emptying_the_summary_changes_the_backbone(monkeypatch):
    """Özet yükü taşınmazsa ne olur? Karar bilgisi kalmaz, omurga şişer.

    HELLO'nun sözcük dizisinden gövde çıkarılır, yalnız başlık kalır. O anda
    her komşuluk sorusu MAYBE'ye düşer ve `safe` ilkesi hepsini "bitişik değil"
    sayar: derece >= 2 olan herkes işaretlenir. Bu, "özet gerçekten okunuyor ve
    karara giriyor" iddiasının gözlenebilir kanıtıdır.
    """
    edges, weights = wuli.connected_udg(20, 0.38, 1)
    adj = wuli.adjacency(edges, list(weights))
    k = max(len(a) for a in adj.values())
    clean = run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
    assert clean.backbone_divergence == ()

    def header_only(self):
        return (wuli.pack_header(ENC_FULL, self._wl_marked, 1, 0),)

    monkeypatch.setattr(WuLiNode, "mis_nbrs", header_only)
    blind = run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
    assert set(blind.backbone) == {v for v in adj if len(adj[v]) >= 2}
    assert len(blind.backbone) > len(clean.backbone)


def test_restoring_the_gap_rule_now_raises_instead_of_reading_the_wrong_field():
    """Bu test bir ALARM'dı, artık bir GARANTİ. Değişimin kendisi kayda değer.

    ESKİ HÂLİ: BB-CVC'nin 3-atlama kuralı WuLi-Dominating'de geri açıldığında omurganın
    DEĞİŞMEDİĞİNİ assert ediyordu. Kural sessizce çalışıyor ama `mis_nbrs`i
    tam komşu listesi olarak okuduğu için kendi bastırma koşulunu ("{a,b}
    çiftini bağlayan mesafe-2 köprüsü var") neredeyse her zaman sağlıyor ve
    kendini susturuyordu. Bu bir KAZAydı; test onun sürdüğünü izliyordu.

    YENİ HÂLİ: bb-algo taban sınıfa tek okuma yolu (`_nbr_mis`) ekledi ve WuLi-Dominating onu
    ezip yükseltiyor, dolayısıyla geri açılan kural artık ÇALIŞAMIYOR. Kazanın
    yerini zorunluluk aldı: alanı yanlış anlamda okumak sessiz bir cevap
    değişikliği değil, yığın izi üretiyor.
    """
    from ccvc.bb.bbcvc import BbcvcNode

    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    clean = run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
    assert clean.converged

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(WuLiNode, "_rule_gap", BbcvcNode._rule_gap)
        with pytest.raises(NotImplementedError) as exc:
            run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
    assert "KOMŞU ÖZETİ" in str(exc.value)


def test_mutation_dropping_an_owner_entry_is_caught_by_the_validator():
    """Doğrulayıcının bu koşumda GERÇEKTEN yük taşıdığının kanıtı."""
    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    r = run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
    g = validate.make_graph(edges, k, weights)
    assert validate.validate(g, r.cover, r.owner).valid
    broken = dict(r.owner)
    broken.pop(sorted(broken)[0])
    assert not validate.validate(g, r.cover, broken).valid


# ==========================================================================
# 10. DENEY UCU
# ==========================================================================
def test_run_case_reports_every_column_figure_six_needs():
    row = wuli.run_case(wuli.Case(n=20, radius=0.38, seed=0, encoding=ENC_BLOOM),
                        max_ms=BUDGET_MS)
    for col in ("variant", "avg_degree", "max_payload", "bytes_tx", "tx",
                "backbone", "backbone_ref", "weight", "valid", "violations"):
        assert col in row
    assert row["variant"] == "WuLi-Dominating/sync/bloom/safe"
    assert row["valid"] is True
    assert row["max_payload"] == wuli.frame_bytes(ENC_BLOOM, 0)


def test_default_cases_cover_three_encodings_and_two_schedulers():
    cases = wuli.default_cases(seeds=(0,))
    assert {c.encoding for c in cases} == set(wuli.ENCODINGS)
    assert {c.scheduler for c in cases} == {"sync", "async"}
    assert {c.name.split("/")[0] for c in cases} == {"WuLi-Dominating"}


def test_csv_has_a_header_and_one_line_per_row():
    rows = [wuli.run_case(wuli.Case(n=20, radius=0.38, seed=0), max_ms=BUDGET_MS)]
    text = wuli.to_csv(rows)
    assert text.splitlines()[0].startswith("variant,")
    assert len(text.splitlines()) == 2


@pytest.mark.skipif(not SLOW, reason="WULI_SLOW=1 ile koşar")
def test_slow_dense_sweep_reports_where_bloom_starts_to_diverge():
    """Yoğunlukla yanlış pozitifin karar değiştirme oranı: ölçüm, tahmin değil."""
    seen = {}
    for n, r in ((60, 0.30), (60, 0.45), (100, 0.60)):
        diff = 0
        for seed in range(6):
            edges, weights = wuli.connected_udg(n, r, seed)
            adj = wuli.adjacency(edges, list(weights))
            keys = wuli.keys_of(adj, weights)
            ref = wuli.reference_backbone(adj, keys)["backbone"]
            pred = wuli.predict_backbone(adj, keys, ENC_BLOOM, POL_NAIVE)["backbone"]
            diff += (pred != ref)
        seen[round(2 * len(edges) / n)] = diff
    assert min(seen) < max(seen)
    assert seen[max(seen)] >= seen[min(seen)]


def test_chunk_divergence_sweep_reports_a_rate_and_the_direction_of_the_error():
    """Parçalı görüşün karar değiştirme ORANI ölçülür ve YÖNÜ assert edilir.

    Beklenti türetimden gelir: eksik parça "yok" değil "bilinmiyor" demektir,
    `safe` bunu "bitişik değil" sayar, yani hata FAZLA işaretleme yönündedir.
    Eksik işaretleme çıkarsa güvenlik savı çürümüş demektir; test bunu ayrıca
    assert eder.
    """
    rows = wuli.chunk_divergence_sweep(chunk_words=(1, 4), seeds=(0, 1),
                                       max_ms=BUDGET_MS)
    assert len(rows) == 4
    by_cw = {}
    for r in rows:
        by_cw.setdefault(r["chunk_words"], []).append(r)
        assert r["under_marked"] == 0, r        # asla EKSİK işaretleme
        assert r["valid"] is True
    narrow = by_cw[1]
    wide = by_cw[4]
    assert all(r["chunk_cycle"] > r["frames_at_decision"] for r in narrow)
    assert max(r["mark_divergence_rate"] for r in narrow) > 0
    assert max(r["mark_divergence_rate"] for r in wide) == 0
    assert all(r["max_payload"] < 25 for r in narrow)


def test_per_query_fpr_is_the_wrong_unit_per_node_exposure_is_the_right_one():
    """Ekip liderinin sorusu: 36 derecede 64 baytlık filtrenin oranı kabul edilebilir mi?

    Ölçülen cevap: SORGU BAŞINA evet, DÜĞÜM BAŞINA hayır. İşaretleme kuralı bir
    düğümde C(36,2)=630 çift sorar; tek taraflı sorguda beklenen bozuk cevap
    sayısı düğüm başına 0,5'in üstüne çıkar, yani yanlış pozitif "nadir" değil
    TİPİKtir. Kararı kurtaran şey filtrenin küçüklüğü değil, iki özete birden
    sorma kuralıdır: maruziyeti iki büyüklük mertebesi aşağı çeker.
    """
    one = wuli.measure_bloom_fpr(36, trials=150, probes=400, seed=5)
    two = wuli.measure_bloom_fpr(36, trials=150, probes=400, seed=5, two_sided=True)
    assert wuli.decision_exposure(36, one) > 0.5, one
    assert wuli.decision_exposure(36, two) < 0.05, two
    assert wuli.decision_exposure(36, wuli.bloom_fpr_formula(36)) > 0.5


# ==========================================================================
# 11. SWEEP KAYDI (bb-figures sözleşmesi)
# ==========================================================================
def test_bb_variants_registers_three_arms_on_distinct_phase1_axes():
    from ccvc.bb.sweep import VariantSpec

    specs = wuli.BB_VARIANTS
    assert len(specs) == 3
    assert all(isinstance(s, VariantSpec) for s in specs)
    assert [s.name for s in specs] == ["WuLi-Dominating-Exact", "WuLi-Dominating-Bloom",
                                       "WuLi-Dominating-Chunked"]
    assert {s.phase1 for s in specs} == {"wuli_full", "wuli_bloom", "wuli_frag"}
    assert len({s.phase1 for s in specs}) == 3      # eşleşmiş çift kurulabilsin
    assert {s.family for s in specs} == {"bb"}
    assert {s.phase5 for s in specs} == {"local"}
    assert all(s.schedulers == ("sync", "async") for s in specs)
    assert not any(s.anytime for s in specs)


def test_sweep_discovers_the_v5_arms():
    from ccvc.bb import sweep

    names = {s.name for s in sweep.discover()}
    assert {"WuLi-Dominating-Exact", "WuLi-Dominating-Bloom", "WuLi-Dominating-Chunked"} <= names


@pytest.mark.parametrize("idx", [0, 1, 2])
def test_each_arm_satisfies_the_result_contract(idx):
    """`adapt_result` eksik alanda ContractError atar; üç kol da geçmeli."""
    from ccvc.bb.sweep import RunRequest, adapt_result

    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    spec = wuli.BB_VARIANTS[idx]
    req = RunRequest(edges=tuple(edges), weights=weights, k=k, scheduler="sync",
                     seed=0, max_ms=BUDGET_MS)
    res = adapt_result(spec.run(req), variant=spec.name)
    assert res.converged
    assert res.backbone, "omurga sütunu boş; kalite ekseni çizilemez"
    assert res.max_payload == wuli.frame_bytes(
        {"wuli_full": ENC_FULL, "wuli_bloom": ENC_BLOOM, "wuli_frag": ENC_CHUNK}[
            spec.phase1],
        max(len(a) for a in wuli.adjacency(edges, list(weights)).values()))


def test_request_mis_nbrs_cap_cannot_strangle_the_summary():
    """`RunRequest.mis_nbrs_max=32` WuLi-Dominating'de 32 komşuyu aşan düğümü reddederdi.

    Alan WuLi-Dominating'de MIS listesi değil komşu özetidir; kapı bu yüzden yükseltilir ve
    gerçek sınır `wire`ın 250 baytı olarak kalır. İstek daha büyük verirse ona
    uyulur.

    Yüksek dereceli düğüm İNŞA GEREĞİ kurulur (40 yapraklı yıldız), üretilen bir
    örneğin rastlantısal derecesiyle değil: bu testin ilk hâli `connected_udg`in
    azami derecesinin 32'yi aşacağını VARSAYIYORDU ve varsayım yanlış çıkınca
    asıl iddia hiç koşmadı.
    """
    from ccvc.bb.sweep import RunRequest

    cap = 32
    edges, weights = star_with_degree(cap + 8)
    adj = wuli.adjacency(edges, list(weights))
    deg = max(len(a) for a in adj.values())
    assert deg > cap                                   # inşa gereği, aranmadı
    req = RunRequest(edges=tuple(edges), weights=weights, k=deg,
                     scheduler="sync", seed=0, max_ms=BUDGET_MS,
                     mis_nbrs_max=cap)
    res = wuli.BB_VARIANTS[0].run(req)                 # tam liste kolu
    assert res.converged
    assert res.max_payload == wuli.frame_bytes(ENC_FULL, deg)
    assert res.max_payload <= wire.MAX_PAYLOAD
    # kapı gerçekten yükseltilmeseydi üretici `ValueError` atardı: aynı çizgeyi
    # kapıyı yükseltmeyen bir parametreyle koşmak bunu gösterir
    with pytest.raises(ValueError):
        run(edges, weights, deg,
            params=WuLiParams(encoding=ENC_FULL, mis_nbrs_max=cap))


def test_registered_fragment_arm_counts_every_fragment_as_a_transmission():
    """Şeklin tx paneli ancak bu doğruysa doğru okunur (bb-figures sordu)."""
    from ccvc.bb.sweep import RunRequest

    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    req = RunRequest(edges=tuple(edges), weights=weights, k=k, scheduler="sync",
                     seed=0, max_ms=BUDGET_MS)
    frag = wuli.BB_VARIANTS[2].run(req)                  # topluca
    full = wuli.BB_VARIANTS[0].run(req)
    assert frag.max_payload < full.max_payload           # çerçeve küçüldü
    assert frag.tx > full.tx                             # ama iletim sayısı arttı
    round_robin = run(edges, weights, k,
                      params=WuLiParams(encoding=ENC_CHUNK, chunk_burst=False))
    assert round_robin.tx == full.tx                     # sıra ile: tx sabit


def test_seam_contract_holds_except_on_complete_graphs():
    """bb-algo'nun dikiş sözleşmesi: PH_COVER'a varıldığında B bağlı ve baskın.

    Wu-Li bunu bağlı ve TAM OLMAYAN çizgelerde sağlar. K_n'de işaretli küme
    boştur, dolayısıyla "baskın" maddesi DÜŞER. Bu sapma gizlenmez: burada
    assert edilir ve raporlanmıştır. Örtünün kendisi yine geçerlidir.
    """
    for name in ("P5", "STAR", "BOWTIE", "GRID4", "PRUNE4"):
        edges = GRAPHS[name]
        weights = unit_weights(edges)
        adj = wuli.adjacency(edges)
        k = max(2, max(len(a) for a in adj.values()))
        r = run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
        b = set(r.backbone)
        assert wuli.is_dominating(adj, b), name
        assert wuli.is_connected_subset(adj, b), name
        assert all(nd.role in (Role.OUT, Role.MIS, Role.COVER)
                   for nd in r.nodes.values())
    # tam çizge: sözleşmenin baskınlık maddesi düşer, örtü yine geçerli
    weights = unit_weights(K4)
    r = run(K4, weights, 3, params=WuLiParams(encoding=ENC_FULL))
    assert set(r.backbone) == set()
    assert not wuli.is_dominating(wuli.adjacency(K4), set())
    g = validate.make_graph(K4, 3, weights)
    assert validate.validate(g, r.cover, r.owner).valid


def test_densest_converging_instance_stops_far_below_the_wire_limit():
    """Şekil 6'nın en yoğun ÖLÇÜLEN noktası (bb-figures istedi).

    Tablo sınırının (64) altında kalan ama 32'yi aşan bir örnek ARANIR; hangi
    derecenin çıktığı sabitlenmez, çünkü sabitlenen sayı üreteç değişince
    testi yanlış yerden düşürür. Sabitlenen İDDİA şudur: ölçülen `max_payload`
    analitik eğriyle BİREBİR aynıdır ve 250 B'nin epey altında kalır.
    """
    edges, weights, deg = instance_with_max_degree(33, WuLiParams().nbr_table_max)
    r = run(edges, weights, deg, params=WuLiParams(encoding=ENC_FULL))
    assert r.converged
    assert r.max_payload == wuli.frame_bytes(ENC_FULL, deg)
    assert r.max_payload < wire.MAX_PAYLOAD
    assert r.max_payload <= wuli.frame_bytes(ENC_FULL, WuLiParams().nbr_table_max)


@pytest.mark.skipif(not SLOW, reason="WULI_SLOW=1 ile koşar (~90 s)")
def test_beyond_the_table_cap_the_run_is_invalid_not_merely_large():
    """Derece 64'ü aşınca ne olur: büyük çerçeve DEĞİL, GEÇERSİZ koşum.

    Tablo sınırını aşan bir örnek aranır. Çerçevesi tele SIĞARDI (147 B < 250 B),
    ama komşu tablosu taşar ve `validate_bootstrap` koşumu reddeder. 250 B
    sınırına bu yüzden ULAŞILAMAZ: yol tel tıkanmadan önce tabloda kapanır.
    Sınırın tuttuğu değil, aşıldığında ne olduğu sınanmaktadır.
    """
    from ccvc.bb.bootstrap import RunInvalid

    cap = WuLiParams().nbr_table_max
    edges, weights, deg = instance_with_max_degree(cap + 1)
    assert deg > cap
    assert wuli.frame_bytes(ENC_FULL, deg) <= wire.MAX_PAYLOAD
    with pytest.raises(RunInvalid) as exc:
        run(edges, weights, deg, params=WuLiParams(encoding=ENC_FULL),
            max_ms=200_000)
    assert "komşu tablosu" in str(exc.value)


# ==========================================================================
# 12. TABAN SINIFIN TEK OKUMA YOLU (_nbr_mis sözleşmesi)
# ==========================================================================
def test_wuli_node_refuses_to_answer_the_mis_list_accessor():
    """`_backbone_step` sözleşmesi bunu zorunlu kılıyor: WuLi-Dominating erişimciyi ezip
    YÜKSELTİR. Boş demet döndürmek "MIS komşum yok" diye geçerli ama yanlış bir
    cevap olurdu ve kuralları sessizce çalıştırırdı."""
    edges, weights = star_with_degree(4)
    ids = sorted(weights)
    net = simnet.SimNet(ids, edges, loss=0.0, seed=0,
                        delay=simnet.fixed_delay(1), macs=macs_for(ids))
    node = WuLiNode(1.0, net.port(1), WuLiParams(encoding=ENC_FULL), 3)
    with pytest.raises(NotImplementedError) as exc:
        node._nbr_mis(object())
    assert "KOMŞU ÖZETİ" in str(exc.value)


def test_no_legitimate_v5_path_touches_the_accessor():
    """Meşru koşum erişimciye HİÇ uğramamalı; uğrasaydı bu test düşerdi.

    Üç kodlama × iki zamanlayıcı koşuyor ve hepsi yeşil kalıyor, yani
    `mis_nbrs()` üreticisi, boş `_rule_gap` ve erişilemez `_rule_connector`
    birlikte alanı taban sınıftan tamamen kesiyor.
    """
    edges, weights = wuli.connected_udg(20, 0.38, 0)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    for enc in wuli.ENCODINGS:
        for scheduler in ("sync", "async"):
            r = run(edges, weights, k, scheduler=scheduler,
                    params=WuLiParams(encoding=enc, chunk_words=4))
            assert r.converged, (enc, scheduler)


def test_a_new_base_class_reader_now_dies_loudly_instead_of_silently():
    """TUZAĞIN ATEŞLEDİĞİNİN KANITI (bozulmayı test et, sınırı değil).

    Ölçülmüştü: erişimci YOKKEN taban sınıfa eklenen dördüncü bir okuyucu WuLi-Dominating'i
    sessizce bozuyordu -- n=20 tohum 1'de örtü 12'den 20'ye, Σw 957'den 1180'e
    (+%23), koşum yakınsadı ve doğrulayıcı VALID dedi. Aşağıda aynı okuyucu
    erişimci üzerinden ekleniyor ve artık YÜKSELİYOR. İki yarı birlikte yük
    taşıyor: temiz koşumun geçerliliği, mutasyonun gürültülü ölümü.
    """
    from ccvc.bb.bbcvc import BbcvcNode

    edges, weights = wuli.connected_udg(20, 0.38, 1)
    k = max(len(a) for a in wuli.adjacency(edges, list(weights)).values())
    clean = run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
    assert clean.converged and clean.backbone_divergence == ()

    original = BbcvcNode._rule_cover

    def fourth_reader(self, nb):
        for n in nb:
            if self.nid in self._nbr_mis(n) and self.role == Role.OUT:
                self.role = Role.COVER
        return original(self, nb)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(BbcvcNode, "_rule_cover", fourth_reader)
        with pytest.raises(NotImplementedError):
            run(edges, weights, k, params=WuLiParams(encoding=ENC_FULL))
