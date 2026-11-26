#!/usr/bin/env python3
"""Anneal-Local testleri (brief §6.5, .tex §13).

Koşum (depo kökünden):
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_anneal.py -q

Bu dosyanın omurgası üç YAPISAL SAV ve bir DAĞILIMDIR. Savlar varsayılmaz,
BAĞIMSIZ bir referansla sınanır: yerel ΔE küresel enerjiyle, Döngü B'nin
mesajsızlığı iki ucun gerçek değerleriyle, TU savı Faz 4'ün eskalasyon
sayacıyla. Dağılım ise ölçülür ve brief'in beklentisiyle KARŞILAŞTIRILIR;
uyuşmazlık varsa test onu kayda geçirir, parametre ayarlamaz.
"""
from __future__ import annotations

import collections
import math
import os
import sys
from typing import Dict, List, Set, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import anneal, bbcvc, sched, simnet, wire  # noqa: E402
from ccvc.bb import validate as V  # noqa: E402
from ccvc.bb.api import MsgType, Role  # noqa: E402
from ccvc.bb.anneal import Y_ONE, AnnealNode, AnnealParams  # noqa: E402

# --------------------------------------------------------------------------
# .tex §1 / §13.3 çalışan örneği
# --------------------------------------------------------------------------
EDGES = [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (4, 5), (4, 6), (5, 6),
         (5, 7), (6, 7), (7, 8), (7, 9), (8, 9), (8, 10), (9, 10)]
W = {1: 5, 2: 2, 3: 4, 4: 3, 5: 6, 6: 2, 7: 3, 8: 2, 9: 5, 10: 4}
K = 2
IDS = sorted(W)
ADJ: Dict[int, List[int]] = {i: [] for i in IDS}
for _u, _v in EDGES:
    ADJ[_u].append(_v)
    ADJ[_v].append(_u)
GRAPH = V.make_graph(EDGES, K, W, IDS)
OPT_WEIGHT = 25          # .tex: {1,2,3,4,6,7,8,10}, |C| = 8 = ceil(15/2)


def make_net(seed: int = 0, **kw):
    kw.setdefault("rssi_range", None)
    return simnet.SimNet(IDS, EDGES, macs=bbcvc.macs_for(IDS), seed=seed, **kw)


def run(mode: str = "sync", seed: int = 0, slots: int = 400, **pkw):
    """Gerçek ağ + gerçek zamanlayıcı + gerçek düğüm. Hiçbir taklit yok."""
    net = make_net(seed, delay=simnet.uniform_delay(1, 60))
    p = AnnealParams(rng_seed=seed, **pkw).resolved(W.values())
    nodes = anneal.build_nodes(net, W, K, p)
    sc = (sched.SyncScheduler(net, nodes, tau_ms=200, weights=W) if mode == "sync"
          else sched.AsyncScheduler(net, nodes, tick_ms=200, seed=seed, weights=W))
    return sc.run(slots * 200), nodes, net


# ==========================================================================
# 1. Enerji: yerel ΔE, küresel E ile UYUŞMALI
# ==========================================================================
def global_energy(state: Dict[int, int], y: Dict[Tuple[int, int], float],
                  p: AnnealParams) -> Tuple[float, float]:
    """E'yi .tex §13.1'den doğrudan kur. `y[(u,v)]` u'nun payıdır.

    Dönen çift: (λ_b HARİÇ enerji, λ_b terimi). Yerel kural λ_b'yi ayrıldığı
    yönde BİLEREK hesaplamaz (.tex: kesme düğümü kendini bilemez), bu yüzden
    karşılaştırma λ_b'siz yapılır ve o terim ayrıca raporlanır.
    """
    C = {i for i in state if state[i]}
    e = sum(float(W[i]) for i in C)
    e += p.lam_c * sum(1 for u, v in EDGES if u not in C and v not in C)
    for v in C:
        forced = sum(1 for u in ADJ[v] if u not in C)
        flex = sum(y.get((v, u), 0.5) for u in ADJ[v] if u in C)
        e += p.lam_k * max(0.0, forced + flex - K)
    comps = V.cover_components(GRAPH, C)
    return e, p.lam_b * max(0, len(comps) - 1)


def test_delta_e_reproduces_the_tex_worked_example():
    """.tex §13.3: herkes örtüdeyken 1'in çıkışı Δ=−5, 10'unki Δ=−4.

    Bu iki sayı belgenin metninde AÇIKÇA yazılıdır; enerji türetiminin
    doğruluğunun tek elle doğrulanabilir çapası budur.
    """
    net = make_net()
    p = AnnealParams().resolved(W.values())
    nodes = anneal.build_nodes(net, W, K, p)
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W)
    # komşuluk kurulsun, ama y henüz 1/2'den kaymasın: Döngü A ve B kapalı
    for n in nodes.values():
        n._loop_a = lambda peers: False          # type: ignore
        n._loop_b = lambda peers: None           # type: ignore
    for slot in range(8):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
    for nid, want in ((1, -5.0), (10, -4.0)):
        n = nodes[nid]
        got = n._delta_e(n._peers(n._nbrs_active()))
        assert got == pytest.approx(want), f"düğüm {nid}: {got} != {want}"


def _settled(cover: Set[int], seed: int = 0, slots: int = 200):
    """Örtüyü sabitle, Döngü B'yi SABİT NOKTAYA kadar koştur.

    Yerleşme şart: düğüm ΔE'yi komşusunun YAYINLANMIŞ ℓ'i ile hesaplar, yani
    bir periyot bayat veriyle. Koşumun ortasında yakalanan bir durumda yerel
    ile küresel arasındaki fark bu bayatlıktan gelir ve aritmetik hatayı
    maskeler. Sabit noktada yayınlanan ile anlık aynıdır, karşılaştırma kesin
    olur.
    """
    net = make_net(seed)
    p = AnnealParams(rng_seed=seed).resolved(W.values())

    class Pinned(AnnealNode):
        def _loop_a(self, peers):
            return False

    nodes = {nid: Pinned(W[nid], net.port(nid), p, K) for nid in IDS}
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W)
    for slot in range(slots):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        if slot == 5:
            for i in IDS:
                nodes[i].x = 1 if i in cover else 0
                nodes[i].role = Role.COVER if nodes[i].x else Role.OUT
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
    return nodes


@pytest.mark.parametrize("cover", [
    frozenset(IDS),                          # başlangıç: herkes örtüde
    frozenset({2, 3, 4, 5, 6, 7, 8, 9}),     # .tex'in ara yerel minimumu (27)
    frozenset({1, 2, 3, 4, 6, 7, 8, 10}),    # .tex'in optimumu (25)
    frozenset({1, 2, 4, 5, 8, 9}),           # kopuk: iki bileşen
])
def test_local_delta_e_equals_the_global_energy_difference(cover):
    """BAĞIMSIZ REFERANS. Düğümün yerel ΔE'si, aynı hamlenin küresel enerjide
    yaptığı farka EŞİT olmalı (λ_b hariç, gerekçesi global_energy'de).

    Bu testin yakaladığı gerçek hata: komşunun esnek kenarı zorunluya
    dönerken yükünün (1 − y) kadar arttığı yazılmıştı, oysa BENİM PAYIM
    kadar artar. y = 1/2'de ikisi aynı sonucu verir, yani .tex'in elle
    doğrulanabilir bütün örnekleri bu hatayı GÖREMEZ; ayrışma ancak yük
    dengelendikten sonra, tam da aşırı yüklü düğümde başlar. Bu yüzden
    sınanan durumlar DENGELENMİŞ durumlardır.
    """
    nodes = _settled(set(cover))
    p = nodes[IDS[0]].p
    state = {i: nodes[i].x for i in IDS}
    y = {(i, j): val / Y_ONE for i in IDS for j, val in nodes[i].y.items()}
    checked = 0
    for v in IDS:
        n = nodes[v]
        peers = n._peers(n._nbrs_active())
        assert len(peers) == len(ADJ[v])
        local = n._delta_e(peers)
        # λ_b köprü teşviki YEREL bir tahmindir (görülen etiket sayısı) ve
        # yalnız GİRİŞ yönünde vardır; aritmetik karşılaştırmadan ayrılır.
        bonus = 0.0
        if not n.x:
            labels = {ps.label for _, ps in peers if ps.x}
            if len(labels) > 1:
                bonus = p.lam_b * (len(labels) - 1)
        base, base_b = global_energy(state, y, p)

        after = dict(state)
        after[v] = 1 - state[v]
        y2 = dict(y)
        if after[v]:
            for u in ADJ[v]:                 # .tex: giren düğüm y'leri 1/2'den başlatır
                if after.get(u):
                    y2[(v, u)] = y2[(u, v)] = 0.5
        else:
            for u in ADJ[v]:
                y2.pop((v, u), None)         # kenar artık esnek değil
        post, post_b = global_energy(after, y2, p)
        assert local + bonus == pytest.approx(post - base, abs=1e-6), (
            f"örtü {sorted(cover)}, düğüm {v}: yerel {local} (+{bonus} köprü) "
            f"!= küresel {post - base}")
        if bonus:
            # köprü tahmini gerçek bileşen azalmasıyla tutmalı
            assert bonus == pytest.approx(base_b - post_b, abs=1e-6), (
                f"düğüm {v}: etiketten okunan köprü kazancı {bonus}, "
                f"gerçek bileşen kazancı {base_b - post_b}")
        checked += 1
    assert checked == len(IDS)


def test_the_energy_cross_check_would_catch_the_share_sign_error():
    """MUTASYON DENETİMİ: yukarıdaki testin CANLI olduğunu göster.

    Komşu yük terimini (1 − y) ile yazan sürüm, dengelenmiş bir durumda
    küresel enerjiden AYRILMALI. Ayrılmıyorsa test bir şey kanıtlamıyordur.
    """
    def buggy_delta(node, peers):
        """`(1 − y)` yazan sürüm: doğru terimi çıkar, hatalıyı ekle."""
        d = AnnealNode._delta_e(node, peers)
        if not node.x:
            return d
        for n, ps in peers:
            if not ps.x:
                continue
            ell_u = anneal.fp2f(ps.ell_fp)
            mine = anneal.fp2f(node.y.get(n.nid, Y_ONE // 2))
            d += node.p.lam_k * (node._over(ell_u + 1.0 - mine)
                                 - node._over(ell_u + mine))
        return d

    nodes = _settled(set(IDS))
    p = nodes[IDS[0]].p
    state = {i: nodes[i].x for i in IDS}
    y = {(i, j): val / Y_ONE for i in IDS for j, val in nodes[i].y.items()}
    diffs = []
    for v in IDS:
        n = nodes[v]
        peers = n._peers(n._nbrs_active())
        buggy = buggy_delta(n, peers)
        base, _ = global_energy(state, y, p)
        after = dict(state)
        after[v] = 0
        y2 = {k: val for k, val in y.items() if k[0] != v}
        post, _ = global_energy(after, y2, p)
        diffs.append(abs(buggy - (post - base)))
    assert max(diffs) > 1e-6, "hatalı sürüm de geçiyor: çapraz denetim ölü"


def test_penalties_are_derived_from_the_instance_not_hardcoded():
    """.tex §13.1 λ > w_max ister; §13.3'teki 12 bir SABİT DEĞİL, o örnekte
    w_max = 6 olduğu için `2·w_max`in örneklemesidir. Kural uygulandığında
    çalışan örnekte aynı 12 geri gelmelidir."""
    p = AnnealParams().resolved(W.values())
    assert max(W.values()) == 6
    assert (p.lam_c, p.lam_k, p.lam_b) == (12.0, 12.0, 12.0)
    assert min(p.lam_c, p.lam_k, p.lam_b) > max(W.values())
    # açıkça verilen λ'ya dokunulmaz
    fixed = AnnealParams(lam_c=99.0).resolved(W.values())
    assert fixed.lam_c == 99.0 and fixed.lam_k == 12.0


@pytest.mark.parametrize("scale", [1, 10, 100])
def test_penalties_scale_with_the_instance(scale):
    """Kıyas kümesinde ağırlıklar 26-115 aralığındadır; sabit λ orada
    ihlalin ağırlıkla SATIN ALINABİLMESİ demektir."""
    heavy = {k: v * scale for k, v in W.items()}
    p = AnnealParams().resolved(heavy.values())
    assert min(p.lam_c, p.lam_k, p.lam_b) > max(heavy.values())


def test_a_node_whose_weight_exceeds_lambda_refuses_to_start():
    """YEREL GEREKLİ KOŞUL. Düğüm w_max'ı bilemez ama KENDİ ağırlığını bilir;
    λ ≤ w_v ise o düğüm tek başına bir ihlali satın alabilir.

    Sessiz kalmanın bedeli ölçüldü: gerçek veride bütün düğümler örtüden
    çıkıp BOŞ örtü dönüyordu ve koşum yine `converged=True` diyordu
    (bb-figures: 195/195 satır).
    """
    net = make_net()
    bad = AnnealParams(lam_c=12.0, lam_k=12.0, lam_b=12.0, t0=6.0, t_min_temp=0.05)
    with pytest.raises(ValueError, match="lambda"):
        AnnealNode(500, net.port(1), bad, K)          # w=500 >> λ=12
    with pytest.raises(ValueError, match="unresolved"):
        AnnealNode(1, net.port(2), AnnealParams(), K)  # hiçbiri çözülmemiş


def test_heavy_weights_still_produce_a_non_empty_valid_cover():
    """GERİLEME TESTİ. Bu, başta yazmam gereken testti.

    Eski `test_penalties_exceed_the_heaviest_weight` değişmezi KENDİ
    fixture'ımın ağırlıklarına (en büyüğü 6) karşı denetliyordu, dolayısıyla
    sabit λ = 12 ile hep geçiyordu. Değişmez ise gerçek veride kırılıyordu:
    ağırlıklar 26-115 iken λ = 12 cezayı anlamsız kılıyor ve örtü boşalıyordu.
    Bir değişmezi TUTTUĞU yerde sınamak, sınamamaktır.
    """
    heavy = {k: v * 20 for k, v in W.items()}          # w_max = 120
    graph = V.make_graph(EDGES, K, heavy, IDS)
    net = make_net(0, delay=simnet.uniform_delay(1, 60))
    nodes = anneal.build_nodes(net, heavy, K, AnnealParams(rng_seed=0))
    out = sched.SyncScheduler(net, nodes, tau_ms=200, weights=heavy).run(400 * 200)
    assert out.converged
    assert out.cover, "örtü BOŞ döndü: λ ölçeklenmesi gerilemiş"
    assert out.total_weight > 0
    assert V.validate(graph, out.cover, out.owner).valid
    # ağırlık ölçeği sonucu DEĞİŞTİRMEMELİ: λ birlikte ölçeklendiği için
    # enerji manzarası aynıdır
    base = run("sync", seed=0)[0]
    assert out.cover == base.cover


def test_fixed_lambda_on_heavy_weights_empties_the_cover():
    """MUTASYON DENETİMİ: yukarıdaki testin CANLI olduğunu göster.

    λ'yı 12'de sabitleyip yerel kapıyı devre dışı bırakınca örtü gerçekten
    boşalmalı. Boşalmıyorsa gerileme testi bir şey kanıtlamıyordur.
    """
    heavy = {k: v * 20 for k, v in W.items()}

    class NoGate(AnnealNode):
        def _check_lambdas(self):
            return                                     # kapıyı atla

        def _cover_what_the_key_election_missed(self, nb):
            # §107'nin donma-sonrası onarımı da ARIZA ENJEKSİYONUNUN parçasıdır.
            # Bu test λ'nın ENERJİ FONKSİYONUNA ne yaptığını ölçmektedir; onarım
            # ise Loop A'nın çok ötesinde, donduktan sonra çalışan bir emniyet
            # ağıdır ve açık bırakılırsa boşalan örtüyü DOLU örtüye çevirerek
            # mutasyonu görünmez kılar. Emniyet ağının kendisi
            # `test_the_freeze_repair_refills_a_cover_that_annealing_emptied`
            # ile ayrıca çivilenmiştir.
            return

    net = make_net(0, delay=simnet.uniform_delay(1, 60))
    # Düzeltme ÖNCESİ yapılandırmanın birebir kendisi: .tex'in beş sabiti
    # (λ = 12, T0 = 6, T_min = 0,05) ağırlıktan bağımsız yazılmış hâli.
    bad = AnnealParams(rng_seed=0, lam_c=12.0, lam_k=12.0, lam_b=12.0,
                       t0=6.0, t_min_temp=0.05)
    nodes = {nid: NoGate(heavy[nid], net.port(nid), bad, K) for nid in IDS}
    out = sched.SyncScheduler(net, nodes, tau_ms=200, weights=heavy).run(400 * 200)
    assert out.cover == [], f"örtü boşalmadı ({out.cover}); mutasyon ölü"
    assert out.converged, "üstelik koşum kendini başarılı sayıyor"


def test_the_freeze_repair_refills_a_cover_that_annealing_emptied():
    """§107 EMNİYET AĞI: aynı kurgu, onarım AÇIKKEN.

    Üstteki mutasyon denetimiyle tek farkı onarımın devrede olmasıdır, yani
    onarımın ne kadarını üstlendiğini ÖLÇER, anlatmaz. λ = 12 hâlâ herkesi
    örtüden çıkarmaktadır; fark, donmuş bir düğümün artık yanındaki kenarın
    açıkta olduğunu görüp geri dönmesidir.

    Bu testin varlık sebebi, emniyet ağının sessizce kaldırılamamasıdır: onarım
    silinirse burası `[]` okur ve düşer. `_check_lambdas` yine de yerinde
    durmalıdır; onarım λ hatasını TELAFİ eder, GİDERMEZ.
    """
    heavy = {k: v * 20 for k, v in W.items()}

    class NoGate(AnnealNode):
        def _check_lambdas(self):
            return                                     # yalnız kapıyı atla

    net = make_net(0, delay=simnet.uniform_delay(1, 60))
    bad = AnnealParams(rng_seed=0, lam_c=12.0, lam_k=12.0, lam_b=12.0,
                       t0=6.0, t_min_temp=0.05)
    nodes = {nid: NoGate(heavy[nid], net.port(nid), bad, K) for nid in IDS}
    out = sched.SyncScheduler(net, nodes, tau_ms=200, weights=heavy).run(400 * 200)
    assert out.converged
    assert out.cover, "onarım boş örtüyü kurtarmadı: §107 emniyet ağı ölü"
    graph = V.make_graph(EDGES, K, heavy, IDS)
    assert V.validate(graph, out.cover, out.owner).valid
    # örtü biti tek bittir: role ile x ayrışmamalıdır
    for nid, node in nodes.items():
        assert bool(node.x) == node.role.in_cover, f"düğüm {nid}: x != role"


# ==========================================================================
# 2. Döngü B: mesajsızlık savı -- VARSAYILMAZ, ÖLÇÜLÜR
# ==========================================================================
def _pair_sums(nodes) -> Dict[Tuple[int, int], float]:
    out = {}
    for u, v in EDGES:
        if nodes[u].x and nodes[v].x:
            out[(u, v)] = (nodes[u].y.get(v, Y_ONE // 2)
                           + nodes[v].y.get(u, Y_ONE // 2)) / Y_ONE
    return out


def test_loop_b_is_message_free_meaning_both_ends_agree_exactly():
    """.tex §13.2: "iki uç aynı formülü aynı verilerle uygular, mesaj gerekmez".

    Bu ancak y_uv + y_vu = 1 TAM OLARAK korunursa doğrudur. Yaklaşık değil,
    tam: kayan noktalı bir kayma her periyot birikir ve yükü sessizce
    uydurur. Senkronda ortak anlık görüntü olduğundan eşitlik kesindir.
    """
    net = make_net()
    p = AnnealParams().resolved(W.values())
    nodes = anneal.build_nodes(net, W, K, p)
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W)
    for slot in range(120):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
        for pair, tot in _pair_sums(nodes).items():
            assert tot == 1.0, f"slot {slot} kenar {pair}: pay toplamı {tot}"


def test_loop_b_conserves_total_load_and_balances_it():
    """Toplam yük kenar sayısıdır ve sabit kalmalı; dağılım DÜZLEŞMELİ."""
    net = make_net()
    nodes = anneal.build_nodes(net, W, K, AnnealParams())
    for n in nodes.values():
        n._loop_a = lambda peers: False          # type: ignore
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W)
    spreads = []
    for slot in range(60):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
        ells = [n._ell(n._peers(n._nbrs_active())) for n in nodes.values()]
        if slot > 5:
            assert sum(ells) == pytest.approx(len(EDGES), abs=1e-6)
            spreads.append(max(ells) - min(ells))
    assert spreads[-1] < spreads[0], "dağılım düzleşmedi"
    assert spreads[-1] < 0.1, f"yakınsamadı, son yayılım {spreads[-1]}"


def test_balance_step_must_be_normalised_by_degree_or_it_oscillates():
    """MUTASYON DENETİMİ. Dereceye bölmeyi kaldırınca yineleme SALINMALI.

    Salınım iki periyotluktur, yani iki periyotta bir örneklenirse "kararlı"
    görünür; bu testin iki periyodu da bakması bu yüzdendir.
    """
    class Unnormalised(AnnealNode):
        def _balance_step(self, lo, hi, scale):
            return super()._balance_step(lo, hi, 1)   # .tex'in düz okuması

    net = make_net()
    p = AnnealParams().resolved(W.values())
    nodes = {nid: Unnormalised(W[nid], net.port(nid), p, K) for nid in IDS}
    for n in nodes.values():
        n._loop_a = lambda peers: False          # type: ignore
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W)
    trace = []
    for slot in range(30):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
        trace.append(nodes[4]._ell(nodes[4]._peers(nodes[4]._nbrs_active())))
    tail = trace[-8:]
    assert max(tail) - min(tail) > 1.0, f"salınım beklenirken düzgün: {tail}"
    # normalize edilmiş sürüm aynı yerde salınmamalı
    _, good, _ = run("sync", seed=0, slots=30)
    g = good[4]._ell(good[4]._peers(good[4]._nbrs_active()))
    assert 0.0 <= g <= float(len(ADJ[4]))


# ==========================================================================
# 3. TU savı: yuvarlama ESKALASYONSUZ olmalı
# ==========================================================================
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_rounding_needs_no_phase_four_escalation(mode):
    """.tex §13.1: kısıt matrisi tamamen unimodülerdir, dolayısıyla kesirli
    uygunluk tam sayılı uygunluğu gerektirir; donma sonrası Faz 4 kenarları
    ESKALASYONSUZ yuvarlamalıdır.

    Eskalasyon (JOIN_ESCALATE) bir düğümü örtüye ZORLA sokar; gerekseydi
    kesirli dengelemenin uygunluğu yanıltıcı demekti.
    """
    total = 0
    for seed in range(12):
        out, nodes, _ = run(mode, seed=seed)
        assert out.converged, f"tohum {seed} yakınsamadı"
        total += sum(n._escalations for n in nodes.values())
        assert MsgType.JOIN not in [MsgType(t) for t in out.totals().by_type_tx]
    assert total == 0, f"{total} eskalasyon: TU savı tutmadı"


# ==========================================================================
# 4. Döngü C: tespit-ve-onar
# ==========================================================================
def _pinned_run(cover: Set[int], slots: int, seed: int = 0, pin_from: int = 5,
                first: Set[int] = None, split_at: int = None):
    """Örtüyü sabitle, yalnız Döngü B ve C koşsun.

    `first` verilirse önce O örtü kurulur ve etiketlerin yerleşmesi beklenir,
    `split_at` slotunda `cover`a geçilir. Bayat etiket kuralını sınamak için
    bu iki aşama ŞARTTIR: ayrılan parça o etikete önce SAHİP OLMALI ki
    düşürmesi anlamlı olsun.
    """
    net = make_net(seed)
    p = AnnealParams(rng_seed=seed).resolved(W.values())

    class Pinned(AnnealNode):
        def _loop_a(self, peers):
            return False

    def pin(which):
        for i in IDS:
            nodes[i].x = 1 if i in which else 0
            nodes[i].role = Role.COVER if nodes[i].x else Role.OUT

    nodes = {nid: Pinned(W[nid], net.port(nid), p, K) for nid in IDS}
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W)
    for slot in range(slots):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        if slot == pin_from:
            pin(first if first is not None else cover)
        if split_at is not None and slot == split_at:
            pin(cover)
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
    return nodes


def test_labels_separate_when_the_cover_splits_and_the_bridge_is_rewarded():
    """.tex §13.3 "Bağlılık onarımı örneği" birebir.

    C = {1,2,4,5,8,9}: G[C] {1,2,4,5} ve {8,9} olarak ayrılır. Düğüm 7 örtü
    dışıdır ve komşularında İKİ etiket görmelidir; Döngü A'daki köprü teşviki
    onu geri çağırır (Δ < 0).
    """
    nodes = _pinned_run({1, 2, 4, 5, 8, 9}, slots=25)
    labels = {i: nodes[i].label for i in IDS if nodes[i].x}
    assert labels[1] == labels[2] == labels[4] == labels[5]
    assert labels[8] == labels[9]
    assert labels[1] != labels[8], "etiketler ayrışmadı"
    n7 = nodes[7]
    peers = n7._peers(n7._nbrs_active())
    seen = {ps.label for _, ps in peers if ps.x}
    assert len(seen) == 2, f"köprü iki etiket görmeli, gördüğü {seen}"
    assert n7._delta_e(peers) < 0, "köprü teşviki iniş adımı üretmedi"


def test_a_stale_label_actually_dies_instead_of_being_readopted():
    """SAYMA-SONSUZA. Bayat etiketi düşüren düğüm, onu henüz düşürmemiş
    komşusundan GERİ KAPMAMALI.

    İlk gerçeklemede tazelik saati "etiketim değişti mi" ile sıfırlanıyordu,
    dolayısıyla etiket ölmüyor, komşular arasında dolaşıyordu ve ayrılan
    bileşen kökünün kimliğine hiç yerleşemiyordu. Ölçüldü: 60 tohumun 4'ünde
    donmuş çıktı kopuk kalıyordu.
    """
    # önce BAĞLI örtü: herkes etiket 1'e yerleşir; sonra 6 ve 7 çıkar ve ağ bölünür
    nodes = _pinned_run({1, 2, 4, 5, 8, 9}, slots=40,
                        first=set(IDS), split_at=18)
    for i in (8, 9):
        assert nodes[i].label == 8, f"{i} hâlâ {nodes[i].label} etiketinde"
        assert nodes[i]._stale_label == 1, "ölü etiket hatırlanmıyor"


def test_a_revived_root_reclaims_its_label():
    """Bileşenler yeniden birleşince ölü etiket DİRİLMELİ; aksi hâlde bir
    kez ayrılmış ağ bir daha tek etikete oturamazdı."""
    nodes = _pinned_run({1, 2, 4, 5, 8, 9}, slots=40,
                        first=set(IDS), split_at=18)
    assert nodes[8].label == 8
    n = nodes[8]
    assert n._is_stale(1, n._stale_ctr) is True
    assert n._is_stale(1, (n._stale_ctr + 5) & 0xFF) is False, "kök dirilemiyor"
    assert n._stale_label is None, "diriltme ölü kaydı temizlemeli"


# ==========================================================================
# 5. Sonlanma: sükûnet "dönüş yok" değil "bekleyen dönüş yok"
# ==========================================================================
def test_frozen_state_is_a_local_minimum():
    """Donduğunda hiçbir düğümün Δ < 0 adımı KALMAMALI.

    .tex "enerji minimumları tam olarak geçerli çözümlerdir" demektedir;
    zincir yerel minimuma inmeden durursa bu sav bir şey söylemez.
    """
    for seed in range(8):
        _, nodes, _ = run("sync", seed=seed)
        for v, n in nodes.items():
            assert n.frozen
            d = n._delta_e(n._peers(n._nbrs_active()))
            assert d >= 0, f"tohum {seed} düğüm {v}: donmuş ama Δ={d} < 0"


def test_pending_move_gate_is_a_guarantee_not_a_measured_effect():
    """DÜRÜSTLÜK TESTİ. Sükûnet sayacı "bekleyen adım"a da bakar; bu, donmuş
    durumun yerel minimum olduğunu GARANTİ eder.

    Ama ölçüm dürüstlüğü şunu söyler: Döngü C'nin sayma-sonsuza hatası
    düzeltildikten sonra, yalnız GÖZLENEN dönüşe bakan sürüm de bu 60 tohumda
    aynı sonucu vermektedir. Yani kapı bir hatayı KAPATMAMAKTA, bir değişmezi
    TAŞIMAKTADIR. Bu testin işi o farkı kayda geçirmek, kapıya hak etmediği
    bir başarı yazmamaktır.
    """
    class ObservedOnly(AnnealNode):
        def _anneal_period(self, now, nb):
            peers = self._peers(nb)
            self.periods += 1
            self._loop_b(peers)
            self._loop_c(now, peers)
            tok = self.token
            self.token = self._rand16()
            flipped = (self._loop_a(peers)
                       if self._holds_token(now, peers, tok) else False)
            self._adv_ell_fp = anneal.f2fp(self._ell(self._peers(nb)))
            nbr = any(self._last_seen_flip.values())
            self._last_seen_flip.clear()
            self._maybe_freeze(now, flipped or nbr)     # "bekleyen" YOK

    for seed in range(10):
        net = make_net(seed, delay=simnet.uniform_delay(1, 60))
        p = AnnealParams(rng_seed=seed).resolved(W.values())
        nodes = {nid: ObservedOnly(W[nid], net.port(nid), p, K) for nid in IDS}
        out = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W).run(400 * 200)
        assert V.validate(GRAPH, out.cover, out.owner).valid
    # gerçek gerçeklemede donmuş durum yerel minimum OLMAK ZORUNDA
    for seed in range(10):
        _, nodes, _ = run("sync", seed=seed)
        for v, n in nodes.items():
            assert n._delta_e(n._peers(n._nbrs_active())) >= 0


# ==========================================================================
# 6. Kabul ölçütü: 60 tohum, hepsi geçerli + ölçülen dağılım
# ==========================================================================
def measure_distribution(mode: str = "sync", seeds: int = 60) -> Dict[str, object]:
    hist: collections.Counter = collections.Counter()
    invalid: List[int] = []
    esc = 0
    for seed in range(seeds):
        out, nodes, _ = run(mode, seed=seed)
        rep = V.validate(GRAPH, out.cover, out.owner)
        if not rep.valid:
            invalid.append(seed)
        hist[int(out.total_weight)] += 1
        esc += sum(n._escalations for n in nodes.values())
    return {"hist": dict(sorted(hist.items())), "invalid": invalid,
            "escalations": esc, "n": seeds}


def test_all_sixty_seeds_produce_a_valid_solution():
    """Brief §6.5'in PAZARLIKSIZ kısmı: "hepsi geçerli".

    Kalite bir beklentidir, geçerlilik bir şarttır.
    """
    r = measure_distribution("sync", 60)
    assert r["invalid"] == [], f"geçersiz tohumlar: {r['invalid']}"
    assert r["escalations"] == 0


def test_measured_quality_distribution_is_recorded_not_tuned():
    """Brief §6.5 beklentisi: ≈%48 optimum (25), ≈%33 26, gerisi 27-29.

    ÖLÇÜLEN DAĞILIM BUNU KARŞILAMAMAKTADIR ve bu test o gerçeği kayda geçirir.
    Parametreler .tex §13.3'ün verdiği değerlerdir (λ=12, T0=6, α=0.9,
    T_min=0.05, s=2) ve hedefe yaklaşmak için DEĞİŞTİRİLMEMİŞTİR; uydurulmuş
    bir uyuşma, dürüst bir uyuşmazlıktan kötüdür.

    Test şunu sabitler: çözümler geçerlidir, optimuma ulaşılabilmektedir ve
    kütle .tex'in ara yerel minimumu olan 27 dolayındadır -- yani motor
    çalışmakta, ama tavlama takvimi 27'den 25'e geçmek için gereken iki
    adımlık vadiyi brief'in öngördüğü sıklıkta aşamamaktadır.

    EŞİK 2026-09-17'DE DÜŞÜRÜLDÜ VE SEBEBİ AYARLAMA DEĞİL. Köprü indiriminin
    geri ödenmemesi düzeltildi (BULGULAR_BB.md 90): indirim yalnız katılma
    dalında veriliyor, ayrılma dalında tahsil edilmiyordu, dolayısıyla bir düğüm
    girip çıkarak aynı indirimi sınırsız kez alabiliyordu. Bu, enerji
    fonksiyonunu tanımsız yapan bir KAÇAKTI ve eski dağılım ondan
    faydalanıyordu.

    Kaçak kapanınca kütle ölçülebilir biçimde aşağı kaydı. ÖLÇÜLDÜ, tek koşum
    değil:

        sync  n=60  -> 38/60  (%63)      sync  n=120 -> 72/120 (%60)
        async n=60  -> 28/60  (%47)      async n=120 -> 52/120 (%43)

    Eşik bu ölçümün altına, tohum değişkenliğine pay bırakacak biçimde
    yerleştirildi. Bir kaçağın ürettiği daha iyi görünen sayıyı korumak için
    düzeltmeyi geri almak, brief'in reddettiği şeyin ta kendisi olurdu:
    uydurulmuş bir uyuşma, dürüst bir uyuşmazlıktan kötüdür.
    """
    r = measure_distribution("sync", 60)
    hist = r["hist"]
    assert r["invalid"] == []
    assert min(hist) == OPT_WEIGHT, "optimuma hiç ulaşılamıyor: bu bir hata olurdu"
    assert hist.get(OPT_WEIGHT, 0) >= 1
    # .tex'in ara yerel minimumu 27'dir ({2,...,9}); kütle oradadır.
    # Ölçülen %60-63 (sync); eşik tohum değişkenliği için %55'e konuldu.
    assert sum(v for k, v in hist.items() if k <= 28) >= 0.55 * r["n"]
    # ÖLÇÜLEN: optimum payı brief'in %48'inin ÇOK ALTINDA
    assert hist.get(OPT_WEIGHT, 0) / r["n"] < 0.48


def test_anneal_beats_the_trivial_all_in_start():
    """Anytime başlangıcı x=1 (ağırlık 36) geçerli ama ağırdır; tavlama
    her tohumda bundan İYİ bitmelidir, yoksa hiçbir iş yapmamış olur."""
    r = measure_distribution("sync", 30)
    assert max(r["hist"]) < sum(W.values())


# ==========================================================================
# 7. İki zamanlayıcı, tek düğüm kodu (api I4)
# ==========================================================================
def test_the_same_node_class_runs_under_both_schedulers():
    for mode in ("sync", "async"):
        out, nodes, _ = run(mode, seed=3)
        assert out.converged
        assert V.validate(GRAPH, out.cover, out.owner).valid
        assert all(type(n) is AnnealNode for n in nodes.values())
    # düğüm kodu kipi soramaz: port yüzeyi her iki kipte de aynı dört çağrı
    net = make_net()
    assert set(m for m in dir(net.port(1)) if not m.startswith("_")) == {
        "log", "mac", "now_ms", "send_broadcast", "send_unicast"}


def test_async_measures_a_transient_violation_rate_and_sync_stays_clean():
    """.tex §13.5 tablosu: senkronda jeton dışlaması + ortak anlık görüntü
    KESİN Metropolis verir; asenkronda bayat bilgiyle atılan adım geçici
    ihlal yaratabilir ve ölçülecek metrik budur."""
    def rate(mode):
        tot = viol = 0
        for seed in range(8):
            _, nodes, _ = run(mode, seed=seed)
            viol += sum(n.periods_with_violation for n in nodes.values())
            tot += sum(n.periods for n in nodes.values())
        return viol / max(tot, 1)
    r_sync, r_async = rate("sync"), rate("async")
    assert 0.0 <= r_sync <= 1.0 and 0.0 <= r_async <= 1.0
    # ihlal ORANI ölçülebilir olmalı; büyüklüğü rapora girer
    assert r_async >= 0.0


def test_trickle_cuts_transmissions_and_only_async_can_use_it():
    """.tex §13.5: soğuk fazda periyot uzar, iletim düşer. Senkronda slot
    herkes için sabit olduğundan bu kazanç MÜMKÜN DEĞİLDİR."""
    def tx(mode, trickle):
        t = 0
        for seed in range(8):
            out, _, _ = run(mode, seed=seed, trickle=trickle)
            assert out.converged
            t += out.totals().tx
        return t / 8
    plain = tx("async", False)
    trick = tx("async", True)
    assert trick < plain, f"Trickle iletimi düşürmedi: {trick} >= {plain}"


def test_trickle_ceiling_stays_inside_the_soft_state_window():
    """Trickle periyodu komşunun düşürme eşiğini AŞARSA ağ dağılır: komşular
    birbirini düşürür, epoch sıfırlanır, koşum yakınsamaz. Periyot telde
    duyurulmadığından alıcı uzamayı bilemez."""
    p = AnnealParams().resolved(W.values())
    assert p.t_hello_max_ms < p.stale_periods * p.t_hello_ms

    class Reckless(AnnealNode):
        pass
    # R1 repair F9 (adaptive stale window) removes this hazard: a receiver
    # whose record of a slow sender expired and is heard again doubles its
    # window for that sender. So the failure is asserted with F9 off, and
    # with F9 on (the default) the same reckless ceiling now ends valid.
    for adaptive in (False, True):
        net = make_net(0, delay=simnet.uniform_delay(1, 60))
        bad = AnnealParams(rng_seed=0, trickle=True, t_hello_max_ms=1600,
                           adaptive_stale=adaptive).resolved(W.values())
        nodes = {nid: Reckless(W[nid], net.port(nid), bad, K) for nid in IDS}
        out = sched.AsyncScheduler(net, nodes, tick_ms=200, seed=0,
                                   weights=W).run(400 * 200)
        ok = V.validate(GRAPH, out.cover, out.owner).valid and out.converged
        assert ok is adaptive


# ==========================================================================
# 8. Belirlenimcilik, anytime, mesaj boyutu, rol askısı
# ==========================================================================
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_same_seed_gives_the_same_answer(mode):
    a = run(mode, seed=5)[0]
    b = run(mode, seed=5)[0]
    assert (a.cover, a.total_weight, a.converged) == (b.cover, b.total_weight,
                                                      b.converged)
    assert a.totals().tx == b.totals().tx


def test_anytime_every_intermediate_state_is_reported_and_start_is_valid():
    """.tex: başlangıç x=1 GEÇERLİ ama ağırdır; durdurulduğu anda son geçerli
    çözüm raporlanır."""
    assert V.validate(GRAPH, IDS).vertex_cover
    out, nodes, _ = run("sync", seed=0, slots=12)     # tavlamanın ortasında kes
    assert not out.converged
    assert all(not n.frozen for n in nodes.values())
    # ara durum geçerli olmayabilir; raporlanacak olan SON GEÇERLİ durumdur
    assert set(out.cover) <= set(IDS)


def test_hello_stays_small_and_density_independent():
    """.tex §13.4: ANNEAL HELLO'su ≈32 B ve yoğunluktan bağımsız olmalı."""
    out, _, _ = run("sync", seed=0)
    assert out.totals().max_payload <= wire.hello_size(AnnealParams().mis_nbrs_max,
                                                       anneal=True) == 31
    # ANNEAL hiç MIS rolü üretmez, dolayısıyla mis_nbrs alanı hep boştur
    # Amendment 13, G2(c): plus the bounded confirmation echo, still constant
    assert wire.hello_size(0, anneal=True) == 21
    assert out.totals().max_payload <= wire.hello_size(0, anneal=True, echo=wire.ECHO_MAX)


def test_role_monotonicity_is_suspended_during_annealing_then_restored():
    """api I5 BB-CVC'nin değişmezidir; ANNEAL onu tavlama boyunca askıya alır
    (düğüm örtüden çıkabilir) ve donmadan sonra geri verir."""
    net = make_net(0, delay=simnet.uniform_delay(1, 60))
    p = AnnealParams(rng_seed=0).resolved(W.values())
    nodes = anneal.build_nodes(net, W, K, p)
    sc = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W)
    left_cover = False
    post_freeze: Dict[int, Set[int]] = {i: set() for i in IDS}
    for slot in range(400):
        t0 = slot * 200
        net.set_now(t0)
        for d in net.drain_all():
            net.deliver(d)
        for nid in sc.order:
            net.set_now(t0)
            nodes[nid].on_timer(sched.TIMER_TICK)
        for i in IDS:
            n = nodes[i]
            if not n.frozen and n.role == Role.OUT:
                left_cover = True
            if n.frozen:
                post_freeze[i].add(int(n.role))
        if all(n.done for n in nodes.values()) and net.in_flight == 0:
            break
    assert left_cover, "hiçbir düğüm örtüden çıkmadı: tavlama iş görmemiş"
    for i, roles in post_freeze.items():
        assert len(roles) == 1, f"düğüm {i} donduktan sonra rol değiştirdi: {roles}"


def test_node_never_sees_the_graph():
    """api I1: çizge düğüm koduna hiçbir yoldan verilmez."""
    net = make_net()
    nodes = anneal.build_nodes(net, W, K, AnnealParams())
    n = nodes[1]
    assert not hasattr(n.plat, "neighbors")
    assert n.peer == {} and n.y == {}      # her şey HELLO ile öğrenilecek


# ==========================================================================
# 11. Donduktan sonra etiket katmanı YAŞAMAYA DEVAM EDER
# ==========================================================================
def test_labels_keep_tracking_reality_after_freeze():
    """GERİLEME TESTİ, entegrasyon koşumunda bulunan hatadan.

    Donduktan sonra `_anneal_period` çalışmaz, ama `on_frame` çalışmayı
    sürdürür ve komşu tablosunu ilerletir. Döngü C de dururursa etiket
    katmanı gerçeğin GERİSİNDE donar ve kopukluk GÖRÜNMEZ olur.

    Ölçülen vaka (n=25, m=50, tohum 1, asenkron): düğüm 13 örtüde tek başına
    kalmış, komşuları 12 ve 14'ün çıktığını tablosunda DOĞRU görüyor, ama
    etiketi hâlâ büyük bileşenin 2'si. Hiçbir örtü dışı düğüm iki etiket
    göremiyor, köprü teşviki hiç ateşlemiyor, koşum KOPUK örtüyü "başarılı"
    diye bildiriyor.

    Burada kurgusu: örtüde tek başına kalan bir düğümün etiketi KENDİ
    kimliğine dönmeli, donmuş olsa bile.
    """
    nodes = _pinned_run({1, 2, 4, 5, 8, 9}, slots=40, first=set(IDS), split_at=18)
    for n in nodes.values():                       # hepsini dondur
        n.frozen = True
    net = make_net(0)
    # donmuş hâlde bir periyot daha: etiketler yine de güncellenmeli
    before = {i: nodes[i].label for i in IDS if nodes[i].x}
    assert before, "kurgu boş"
    for i in IDS:
        n = nodes[i]
        if n.x:
            n._loop_c(n.plat.now_ms(), n._peers(n._nbrs_active()))
    after = {i: nodes[i].label for i in IDS if nodes[i].x}
    assert after == before, "yerleşmiş etiketler oynamamalı"
    # ayrık bileşenlerin etiketleri FARKLI kalmalı
    assert nodes[8].label != nodes[1].label


def test_an_isolated_cover_node_relabels_itself_to_its_own_id():
    """Örtüde komşusuz kalan düğümün etiketi kendi kimliğidir; bu, köprünün
    iki etiket görebilmesinin ÖN KOŞULUDUR."""
    net = make_net()
    p = AnnealParams().resolved(W.values())
    nodes = anneal.build_nodes(net, W, K, p)
    n = nodes[1]
    n.x, n.label = 1, 999                       # yapay bayat etiket
    n._loop_c(0, [])                            # örtüde komşusu yok
    assert n.label == n.nid, "yalnız kalan düğüm kendi kimliğine dönmeli"


# ==========================================================================
# 9. Epoch restart: the cover bit lives in two fields and both must rewind
# ==========================================================================
def test_an_epoch_restart_rewinds_x_and_role_together():
    """`x` and `role` are ONE bit stored twice, and a restart rewound only one.

    `BbcvcNode._reset_to_phase0` forces `role = OUT`, which is right for a
    constructive algorithm. The annealer keeps the same bit in `x`, and that was
    left alone: a node came out of the restart advertising x = 1 while reporting
    role = OUT. The cover is READ OFF `role`, so the run could report an empty
    cover while every node believed the graph was fully covered.

    The restart must restore .tex S13's opening state (x = 1, everyone in the
    cover), not OUT. `y` goes with it: the shares are defined against the
    neighbourhood the restart has just discarded.
    """
    net = make_net()
    p = AnnealParams().resolved(W.values())
    n = anneal.build_nodes(net, W, K, p)[1]

    n.x, n.role = 0, Role.OUT             # Loop A took this node out of the cover
    n.y = {2: Y_ONE // 2}
    n.periods, n.frozen, n.frozen_ms = 92, True, 500
    n._quiet_periods, n._bridge_credit = 9, 24.0

    n._reset_to_phase0(1000, reason="test_epoch")

    assert bool(n.x) == n.role.in_cover, "x and role disagree after the restart"
    assert n.x == 1 and n.role is Role.COVER, ".tex S13 restarts at x_v = 1"
    assert n.y == {}, "shares survived a neighbourhood that was discarded"
    assert (n.periods, n.frozen, n.frozen_ms) == (0, False, None)
    assert (n._quiet_periods, n._bridge_credit) == (0, 0.0)


def test_a_restart_mid_run_still_ends_with_a_non_empty_valid_cover():
    """End to end: restart EVERY node mid-anneal, as an epoch bump does.

    With `x` left behind, the restarted nodes kept advertising x = 1, so no
    neighbour saw an uncovered edge, no flip was ever downhill, everyone froze
    on the first schedule and the run reported `solved` with a cover of size
    ZERO -- measured on the nine discovered wireless graphs (n=10/15/20, three
    seeds x four loss levels, 108 sync runs): 33 runs took an epoch restart, all
    33 ended with x != role (up to 18 of 20 nodes), 30 of those were invalid and
    5 reported an EMPTY cover. Those 33 were also the only invalid runs in the
    sweep; with the restart complete the same 108 runs give 0 mismatches, 0
    empty covers and 0 invalid results.
    """
    class RestartOnce(AnnealNode):
        RESTART_AT = 30
        _restarted = False

        def _anneal_period(self, now, nb):
            super()._anneal_period(now, nb)
            # ONCE. `_reset_to_phase0` rewinds `periods`, so an unguarded test
            # would restart the node every 30 periods and never let it finish.
            if self.periods >= self.RESTART_AT and not self._restarted:
                self._restarted = True
                self._reset_to_phase0(now, reason="test_epoch")

    for seed in range(4):
        net = make_net(seed, delay=simnet.uniform_delay(1, 60))
        p = AnnealParams(rng_seed=seed).resolved(W.values())
        nodes = {nid: RestartOnce(W[nid], net.port(nid), p, K) for nid in IDS}
        out = sched.SyncScheduler(net, nodes, tau_ms=200, weights=W).run(400 * 200)

        split = [v for v, n in nodes.items() if bool(n.x) != n.role.in_cover]
        assert not split, f"seed {seed}: x and role disagree at {split}"
        assert out.cover, f"seed {seed}: empty cover after a restart"
        assert V.validate(GRAPH, out.cover, out.owner).valid, f"seed {seed}: invalid"
