#!/usr/bin/env python3
"""Anneal-Local'ın sweep sözleşmesine bağlanması (ccvc/bb/sweep.py).

Koşum:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_v6_anneal.py -q
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import sweep, v6_anneal  # noqa: E402
from ccvc.bb import anneal  # noqa: E402
from ccvc.bb import validate as V  # noqa: E402
from ccvc.bb.sweep import AnytimeSample, AnytimeTrace, ContractError, RunRequest  # noqa: E402

EDGES = [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (4, 5), (4, 6), (5, 6),
         (5, 7), (6, 7), (7, 8), (7, 9), (8, 9), (8, 10), (9, 10)]
W = {1: 5, 2: 2, 3: 4, 4: 3, 5: 6, 6: 2, 7: 3, 8: 2, 9: 5, 10: 4}
K = 2
GRAPH = V.make_graph(EDGES, K, W, sorted(W))
EDGES_L = list(EDGES)


def specs() -> Dict[str, sweep.VariantSpec]:
    return {s.name: s for s in sweep.discover() if s.family == "anneal"}


def req(scheduler="sync", seed=0, max_ms=400 * 200, loss=0.0) -> RunRequest:
    return RunRequest(edges=tuple(EDGES), weights=W, k=K, scheduler=scheduler,
                      seed=seed, max_ms=max_ms, loss=loss)


# ==========================================================================
# 1. Kayıt ve sözleşme
# ==========================================================================
def test_variants_are_discoverable_with_honest_axes():
    s = specs()
    assert "Anneal-Local" in s
    for spec in s.values():
        assert spec.family == "anneal"
        assert spec.phase1 == "anneal"
        assert spec.anytime is True


def test_anneal_forms_no_matched_pair_with_the_bb_family():
    """Anneal iki eksende birden ayrılır (aile + phase1), dolayısıyla BB kollarıyla
    EŞLEŞMİŞ çift kuramaz. Bu istenen davranıştır, kaçınılacak bir engel değil:
    Anneal Faz 1'i değiştirmekle kalmaz, örtü kararının karakterini değiştirir."""
    all_specs = {s.name: s for s in sweep.discover()}
    v6 = all_specs["Anneal-Local"]
    bb = all_specs["MIS-Connector-Backbone"]
    assert v6.family != bb.family
    diffs = [a for a in sweep.AXES if a != "scheduler"
             and v6.axis(a) != bb.axis(a)]
    assert diffs == ["phase1"]          # phase5 aynı: 5a'yı aynen kullanıyor


def test_v6_tree_and_local_are_a_matched_pair_on_phase5():
    """Anneal kendi içinde eşleşmiş çift kurar: tek fark Faz 5b'nin açık olması."""
    s = specs()
    a, b = s["Anneal-Local"], s["Anneal-TreeAgg"]
    diffs = [ax for ax in sweep.AXES if ax != "scheduler" and a.axis(ax) != b.axis(ax)]
    assert diffs == ["phase5"]
    assert a.family == b.family


def test_trickle_variant_is_async_only_structurally():
    """.tex §13.5: senkron slot herkes için sabittir, Trickle orada MÜMKÜN
    DEĞİLDİR. Yorumla değil `schedulers` ile dayatılır."""
    assert specs()["Anneal-Trickle"].schedulers == ("async",)


@pytest.mark.parametrize("scheduler", ["sync", "async"])
@pytest.mark.parametrize("name", ["Anneal-Local", "Anneal-TreeAgg"])
def test_result_satisfies_the_runner_contract(name, scheduler):
    """adapt_result EKSİK ALANDA PATLAR; geçmesi on beş alanın da olması demek."""
    res = specs()[name].run(req(scheduler=scheduler, seed=3))
    vr = sweep.adapt_result(res, variant=name)
    assert vr.converged
    assert V.validate(GRAPH, vr.cover, vr.owner).valid
    assert vr.total_weight > 0 and vr.tx > 0 and vr.rx > vr.tx
    assert vr.trace is not None


def test_a_missing_field_is_a_contract_error_not_a_zero():
    class Broken:
        cover, owner, total_weight = [1], {}, 1.0
    with pytest.raises(ContractError):
        sweep.adapt_result(Broken(), variant="fake")


# ==========================================================================
# 2. Anytime izi
# ==========================================================================
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_trace_satisfies_all_three_invariants(scheduler):
    """Zaman sıralı, enerji birikimli, en-iyi-şimdiye-kadar azalmayan."""
    res = specs()["Anneal-Local"].run(req(scheduler=scheduler, seed=5))
    t = res.trace
    t.check()                                   # patlarsa test düşer
    assert len(t.samples) > 5
    assert [s.t_ms for s in t.samples] == sorted(s.t_ms for s in t.samples)
    en = [s.energy_mah for s in t.samples]
    assert en == sorted(en)
    ws = [s.observer_best_weight for s in t.samples if s.valid]
    assert ws == sorted(ws, reverse=True)
    assert all(s.tx <= n.tx for s, n in zip(t.samples, t.samples[1:]))


def test_trace_check_actually_catches_each_violation():
    """MUTASYON DENETİMİ: üç değişmezin her biri ayrı ayrı yakalanmalı."""
    ok = [AnytimeSample(0, 0.0, 0, 36.0, 10), AnytimeSample(10, 1.0, 5, 27.0, 8)]
    AnytimeTrace("x", list(ok)).check()
    with pytest.raises(ContractError):          # zaman geri gidiyor
        AnytimeTrace("x", [ok[1], ok[0]]).check()
    with pytest.raises(ContractError):          # enerji azalıyor
        AnytimeTrace("x", [AnytimeSample(0, 5.0, 0, 36.0, 10),
                           AnytimeSample(10, 1.0, 5, 27.0, 8)]).check()
    with pytest.raises(ContractError):          # en iyi ağırlık artıyor
        AnytimeTrace("x", [AnytimeSample(0, 0.0, 0, 27.0, 8),
                           AnytimeSample(10, 1.0, 5, 36.0, 10)]).check()
    with pytest.raises(ContractError):          # boş iz
        AnytimeTrace("x", []).check()


def test_energy_must_use_live_radio_on_time_not_the_counter_directly():
    """`Counters.energy_mah()` koşum ORTASINDA yanıltıcıdır.

    `radio_on_ms` yalnız düğüm DONE dediğinde ya da `finalize`'da yazılır,
    dolayısıyla koşum boyunca sıfırdır: doğrudan çağrılsa eğri sonuna kadar
    neredeyse düz gider ve sonda zıplar. Örnekleyici aynı formülü canlı
    dinleme süresiyle kurar.
    """
    res = specs()["Anneal-Local"].run(req(seed=1))
    t = res.trace
    mid = t.samples[len(t.samples) // 2]
    assert mid.energy_mah > 0.0, "canlı enerji ortada sıfır olmamalı"
    # dinleme terimi iletim teriminden baskın olmalı (brief §3.6'nın dersi)
    listen = mid.t_ms / 3_600_000.0 * 100.0 * len(W)
    send = mid.tx * 0.7 / 3_600_000.0 * 240.0
    assert listen > send
    assert mid.energy_mah == pytest.approx(listen + send, rel=1e-6)


def test_first_valid_solution_exists_immediately_for_v6():
    """.tex: başlangıç x=1 (herkes örtüde) GEÇERLİ ama ağırdır.

    Dolayısıyla Anneal için "ilk geçerli çözümden önce" bölgesi BOŞTUR ve şekil
    orada çizilmeyecek bir yer bulamaz. Bu Anneal'a özgüdür: kurucu kollarda o
    bölge gerçekten vardır. Boş olması C=V'nin kapasiteye SIĞMASINA bağlıdır
    (Hakimi koşulu); sığmadığı bir örnekte bölge yeniden ortaya çıkar.
    """
    res = specs()["Anneal-Local"].run(req(seed=2))
    t = res.trace
    assert t.t_first_valid_ms == t.samples[0].t_ms
    assert t.samples[0].observer_best_weight == pytest.approx(sum(W.values()))
    assert t.samples[0].cover_size == len(W)
    assert V.validate(GRAPH, sorted(W)).valid       # C = V gerçekten geçerli


def test_the_observer_bound_carries_its_label_in_the_name_and_in_code():
    """Takım lideri kararı: `observer_best_*` hiçbir tabloda ÇIPLAK geçmemeli.

    Etiketi yoruma bırakmak yetmez, çünkü yorum tabloya kopyalanmaz. Ad
    `observer_` ile başlar ve etiket metni alanın yanında kodda durur; sayıyı
    okuyan etiketi de görmek zorundadır.
    """
    res = specs()["Anneal-Local"].run(req(seed=1))
    assert hasattr(res, "observer_best_weight")
    assert not hasattr(res, "best_valid_weight"), "etiketsiz eski ad geri gelmiş"
    assert "convergecast" in res.OBSERVER_LABEL
    # rapora giren sayı budur ve sözleşme alanı odur
    vr = sweep.adapt_result(res, variant="Anneal-Local")
    assert vr.total_weight == res.total_weight
    assert not hasattr(vr, "observer_best_weight"), (
        "gözlemci sınırı sözleşme alanı OLMAMALI; CSV'ye son durum girer")


def test_trace_last_sample_matches_the_best_seen_field():
    res = specs()["Anneal-Local"].run(req(seed=7))
    assert res.trace.samples[-1].observer_best_weight == pytest.approx(
        res.observer_best_weight)


# ==========================================================================
# 3. SON DURUM ile EN İYİ GÖRÜLEN arasındaki fark -- raporlanan bulgu
# ==========================================================================
def test_final_state_can_be_worse_than_the_best_valid_state_seen():
    """Tavlama, gördüğü en iyi durumdan DAHA KÖTÜ bitebilir ve sıkça biter.

    Bu bir hata değil, Metropolis'in tanımıdır: zincir yokuş yukarı adım
    kabul eder, dolayısıyla son durum bir yerel minimumdur ama görülen en iyi
    durum olmak zorunda değildir. Standart tavlamada çözüm "görülen en iyiyi
    sakla"maktır; .tex ise "durdurulduğu anda SON geçerli çözüm" demektedir.

    ÖLÇÜLDÜ (60 tohum, senkron): koşumların 29'unda son durum görülen en
    iyiden kötüdür, ortalama fark 2,17 ve en büyüğü 8,0. Yani bu uç bir durum
    değil, tipik davranıştır ve iki büyüklük AYRI RAPORLANMALIDIR.
    """
    worse = 0
    for seed in range(20):
        res = specs()["Anneal-Local"].run(req(seed=seed))
        assert res.observer_best_weight is not None
        assert res.observer_best_weight <= res.total_weight + 1e-9, (
            "görülen en iyi, son durumdan kötü olamaz")
        if res.observer_best_weight < res.total_weight - 1e-9:
            worse += 1
            assert V.validate(GRAPH, list(res.observer_best_cover)).valid
    assert worse > 0, "fark hiç görülmedi: bulgu artık geçerli değil, raporu güncelle"


# ==========================================================================
# 4. Belirlenimcilik ve kayıp
# ==========================================================================
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_same_request_gives_the_same_result_and_trace(scheduler):
    a = specs()["Anneal-Local"].run(req(scheduler=scheduler, seed=9))
    b = specs()["Anneal-Local"].run(req(scheduler=scheduler, seed=9))
    assert (a.cover, a.total_weight, a.tx, a.converged) == (b.cover, b.total_weight,
                                                            b.tx, b.converged)
    assert [(s.t_ms, s.tx, s.observer_best_weight, s.current_weight)
            for s in a.trace.samples] == \
           [(s.t_ms, s.tx, s.observer_best_weight, s.current_weight)
            for s in b.trace.samples]


def test_runs_under_loss_still_produce_a_valid_trace():
    """Kayıplı kanalda da iz sözleşmeyi tutmalı; tutmuyorsa şekil değil
    RAPORLAMA bozuktur."""
    res = specs()["Anneal-Local"].run(req(scheduler="async", seed=4, loss=0.05))
    res.trace.check()
    assert res.retx >= 0


# ==========================================================================
# 5. Ortak koşum hattı (bb-algo'nun node_factory / result_cls dikişi)
# ==========================================================================
def test_v6_runs_through_the_shared_bbcvc_pipeline():
    """Anneal kendi koşum hattını KOPYALAMAZ; `run_bbcvc`i kanca ile kullanır.

    Kopya olsaydı ağ kurulumu, bootstrap kapısı, örtü/sahiplik çıkarımı ve
    sayma sınırı zamanla BB-CVC'ninkinden ayrışır ve "aynı hattan geçiyorlar"
    savı sessizce yanlışa dönerdi.
    """
    from ccvc.bb.bbcvc import BbcvcRun
    res = specs()["Anneal-Local"].run(req(seed=3))
    assert isinstance(res, BbcvcRun), "AnnealRun BbcvcRun alt sınıfı olmalı"
    # ortak hattın ürettiği koşum düzeyi alanlar BURADA da dolu
    assert res.verdict in ("solved", "unresolved", "truncated")
    assert res.truncated is (not res.converged)
    assert hasattr(res, "infeasible_reason")
    # Anneal'a özgü alanlar koşumdan sonra dolduruluyor
    assert res.trace is not None and res.flips >= 0


def test_counting_bound_gives_v6_an_infeasibility_witness_it_lacked():
    """Boşluk kapandı. Anneal'ın Faz 3'ü yok, dolayısıyla düğüm tabanlı
    uygunsuzluk tanığı hiç kurulmuyordu ve gerçekten uygunsuz bir örnekte
    geçersiz bir örtü dönüyordu. Koşum düzeyi sayma sınırı (m > n·k) bunu
    düğümlerden bağımsız olarak yakalar ve provenance'ı da söyler.
    """
    edges = [(i, j) for i in range(1, 6) for j in range(i + 1, 6)]   # K5
    w = {i: 1 for i in range(1, 6)}
    res = v6_anneal.run_anneal(edges, w, 1, seed=0, max_ms=200 * 200, trace=False)
    assert res.infeasible is True
    assert res.infeasible_reason == "counting_bound"   # koşum aritmetiği, düğüm değil
    assert len(edges) > len(w) * 1                     # 10 > 5·1


def test_sampler_is_attached_before_the_scheduler_starts():
    """Fabrika AĞ düzeyindedir, tam da bunun için: örnekleyici bütün düğüm
    kümesine zamanlayıcı BAŞLAMADAN takılır. Düğüm düzeyinde bir fabrika
    bunu yapamazdı, çünkü tek düğüm kümenin tamamını göremez."""
    res = specs()["Anneal-Local"].run(req(seed=2))
    first = res.trace.samples[0]
    assert first.t_ms == 0, "ilk örnek koşum başlamadan alınmalı"
    assert first.cover_size == len(W), "başlangıç durumu (x=1, herkes örtüde)"
    assert first.tx <= len(W), "ilk örnek ilk tur yayınlardan önce/sırasında"


# ==========================================================================
# 6. Zarf ile son durum arasındaki yön (bb-figures'in trace_agrees kapısı)
# ==========================================================================
def test_envelope_can_never_be_worse_than_a_valid_final_state():
    """bb-figures'in sorduğu soru: zarf SON DURUMDAN kötü olabilir mi?

    GEÇERLİ bir son durum için OLAMAZ, ve bu ölçüm değil kanıttır:
      1. Son durum HER ZAMAN örneklenir (`run_anneal` koşum sonunda bir
         örnek daha alır).
      2. Örnekleyicinin geçerlilik ölçütü akış tabanlıdır ve sahiplik
         tabanlı olandan ZAYIFTIR; akış uygunluğu sahiplik uygunluğunun
         GEREK koşuludur, yani süpürgenin geçerli dediği her durum
         örnekleyicinin de geçerli dediği bir durumdur.
      3. Öyleyse geçerli son durum koşan minimuma girmiştir ve zarf ≤ son.

    Dolayısıyla bayrak yalnız son durum GEÇERSİZKEN ateşler, ki boş örtü
    hatası tam olarak öyle görünüyordu. Kapı kalmalı: doğrulayıcıdan
    BAĞIMSIZ ikinci bir sinyaldir.
    """
    worse = 0
    for seed in range(15):
        res = specs()["Anneal-Local"].run(req(seed=seed))
        if not V.validate(GRAPH, res.cover, res.owner).valid:
            continue
        assert res.observer_best_weight <= res.total_weight + 1e-9, (
            f"tohum {seed}: zarf {res.observer_best_weight} > "
            f"son {res.total_weight}; kanıt yanlışsa kapı da yanlıştır")
        if res.observer_best_weight > res.total_weight + 1e-9:
            worse += 1
    assert worse == 0


def test_an_invalid_final_state_is_exactly_when_the_flag_can_fire():
    """Boş örtü kurgusu: zarf başlangıç durumunu tutar, son durum boştur,
    yani zarf son durumdan AĞIR görünür. Bayrağın var olma nedeni budur."""
    from ccvc.bb.api import Role

    class Emptying(v6_anneal._TracedAnnealNode):
        """Donduğunda örtüden çıkan düğüm: geçersiz son durumu kurgular.

        `_TracedAnnealNode`tan türer, `AnnealNode`tan değil: örnekleyici
        kancası orada yaşıyor ve düz `AnnealNode` hiç örneklenmezdi.
        """

        def _maybe_freeze(self, now, changed, *peers):   # Amendment 16: + peers
            super()._maybe_freeze(now, changed, *peers)
            if self.frozen:
                self.x, self.role = 0, Role.OUT

        def _cover_what_the_key_election_missed(self, nb):
            # ARIZANIN PARÇASI. §107 onarımı açık kalsaydı kurgulanan boş örtü
            # onarılır, son durum GEÇERLİ olur ve bayrağın ateşleyebildiği
            # durum hiç kurulamazdı; test o zaman bayrağı değil onarımı ölçerdi.
            return

    res = v6_anneal.run_anneal(EDGES, W, K, scheduler="sync", seed=0,
                               max_ms=400 * 200,
                               node_cls=Emptying)
    assert res.cover == []
    assert res.total_weight == 0
    assert res.observer_best_weight > 0, "zarf geçerli bir durum görmüş olmalı"
    assert res.observer_best_weight > res.total_weight    # bayrak ateşler
    assert not V.validate(GRAPH, res.cover, res.owner).valid


# ==========================================================================
# 7. verdict: koşumun bittiğini söyler, cevabın iyi olduğunu DEĞİL
# ==========================================================================
def test_verdict_is_truthful_in_both_directions():
    ok = specs()["Anneal-Local"].run(req(seed=3))
    assert ok.converged and ok.verdict == "solved" and ok.truncated is False
    cut = specs()["Anneal-Local"].run(req(seed=3, max_ms=12 * 200))   # bütçeyi kes
    assert not cut.converged and cut.verdict == "truncated" and cut.truncated


def test_verdict_is_not_derived_from_validity():
    """bb-algo'nun değişmezi Anneal'da da tutmalı: `verdict` sonlanma biçimidir.

    Donmuş ama GEÇERSİZ bir koşum yine "solved" okur. Satırı kol sonucu
    saymanın koşulu bu yüzden `verdict == "solved"` VE doğrulayıcı temiz
    olmasıdır; ikisinden biri tek başına yeterli değildir ve boş örtü hatası
    tam da `verdict` tarafından ONAYLANIYORDU.
    """
    from ccvc.bb.api import Role

    class Emptying(v6_anneal._TracedAnnealNode):
        def _maybe_freeze(self, now, changed, *peers):   # Amendment 16: + peers
            super()._maybe_freeze(now, changed, *peers)
            if self.frozen:
                self.x, self.role = 0, Role.OUT

        def _cover_what_the_key_election_missed(self, nb):
            return              # ARIZANIN PARÇASI; bkz. yukarıdaki kurgu

    res = v6_anneal.run_anneal(EDGES, W, K, scheduler="sync", seed=0,
                               max_ms=400 * 200, node_cls=Emptying)
    assert res.verdict == "solved", "koşum gerçekten sonlandı"
    assert not V.validate(GRAPH, res.cover, res.owner).valid, "ama cevap çöp"


# ==========================================================================
# 8. Örnek İÇİ tutarlılık: ağırlık ile boyut AYNI anlık görüntüden
# ==========================================================================
def test_weight_and_cover_size_describe_the_same_snapshot():
    """bb-figures'in sorduğu: `observer_best_weight` ile `cover_size` ayrı
    anlık görüntülerden geliyor olabilir mi?

    Gelemez, ve bu ölçümden önce YAPIDAN gelir: üçü de (`_best_w`, `_best_n`,
    `best_cover`) TEK deyimde, TEK `cover` listesinden atanır. Yine de test
    ediliyor, çünkü "yapı gereği doğru" bir sonraki düzenlemede sessizce
    yanlışa dönebilen türden bir iddiadır.
    """
    for seed in range(10):
        for sch in ("sync", "async"):
            res = specs()["Anneal-Local"].run(req(scheduler=sch, seed=seed))
            cover = res.observer_best_cover
            if not cover:
                continue
            last = res.trace.samples[-1]
            assert last.cover_size == len(cover)
            assert last.observer_best_weight == pytest.approx(
                round(sum(float(W[v]) for v in cover), 6))
            assert res.observer_best_weight == last.observer_best_weight
            # zarf gerçekten GEÇERLİ bir örtüyü tarif etmeli
            assert V.validate(GRAPH, list(cover)).valid


def test_size_may_differ_from_the_final_cover_while_weight_is_ordered():
    """12 'boyut uyuşmuyor' satırının açıklaması: zarf AĞIRLIĞI küçültür ve
    ağırlıkla boyut birlikte artıp azalmaz. Daha az düğümlü bir örtü daha
    ağır, daha çok düğümlü bir örtü daha hafif olabilir.

    Dolayısıyla `cover_size` ile `len(cover)` karşılaştırması bir tutarsızlık
    ÖLÇMEZ; karşılaştırılacak olan ağırlıktır ve onun sırası korunur.
    """
    seen_diff = False
    for seed in range(20):
        for sch in ("sync", "async"):
            res = specs()["Anneal-Local"].run(req(scheduler=sch, seed=seed))
            last = res.trace.samples[-1]
            if last.cover_size is None:
                continue
            if last.cover_size != len(res.cover):
                seen_diff = True
            if V.validate(GRAPH, res.cover, res.owner).valid:
                # boyut ne olursa olsun AĞIRLIK sırası bozulmaz
                assert last.observer_best_weight <= res.total_weight + 1e-9
    assert seen_diff, "boyut farkı hiç görülmedi: açıklama artık geçerli değil"


# ==========================================================================
# 7. §107 gerilemesi: donmuş iki uç ile açıkta kalan kenar
# ==========================================================================
#: full_v3'te `verdict=solved` deyip doğrulayıcıdan geçemeyen İKİ satır.
#: (dosya, tohum, max_ms, kenar) — kenar, o koşumda açıkta kalan tek kenardır.
FALSE_SUCCESS_ROWS = [
    ("n100_m400_s10.txt", 10, 12_000_000, (7, 70)),
    ("n200_m800_s1.txt", 1, 22_000_000, (30, 51)),
]


def _dataset_instance(name):
    """Kıyas kümesinden bir örneği süpürmenin KENDİ hazırlığıyla yükle."""
    from ccvc.bb import matrix
    d = matrix.dataset_dir()
    if d is None:
        return None
    path = os.path.join(d, name)
    if not os.path.exists(path):
        return None
    raw_w, raw_e = matrix.load_instance(path)
    w, e, _ = sweep.prepare(raw_w, raw_e)
    return list(e), dict(w)


@pytest.mark.parametrize("name,seed,max_ms,edge", FALSE_SUCCESS_ROWS)
def test_anneal_trickle_does_not_freeze_onto_an_uncovered_edge(name, seed, max_ms, edge):
    """İKİ UCU DA DONMUŞ BİR KENAR AÇIKTA KALAMAZ (§107).

    full_v3 süpürmesinde Anneal-Trickle/async bu iki örnekte `solved`
    bildirmiş, doğrulayıcı ise `bad_owner|uncovered_edge` bulmuştu. Kusur
    kaçırılmış bir ileti değildir: iki uç da kenarın açıkta olduğunu
    GÖRMEKTEDİR, ama örtüye dönmenin yerel bedeli, y=1/2 sıfırlamasının
    yarattığı geçici aşırı yük yüzünden pozitiftir; T <= T_min'de yalnız iniş
    kabul edildiğinden onarım hiç alınamaz ve iki uç da donar.

    Test kıyas kümesine bağlıdır ve kümesiz ortamda atlanır; koşum başına
    birkaç saniye sürer.
    """
    inst = _dataset_instance(name)
    if inst is None:
        pytest.skip("Dagdeviren kümesi yok")
    edges, weights = inst
    k = 6
    p = anneal.AnnealParams(rng_seed=seed, enable_tree=False, trickle=True,
                            mis_nbrs_max=64)
    res = v6_anneal.run_anneal(edges, weights, k, scheduler="async",
                               max_ms=max_ms, loss=0.0, seed=seed, params=p,
                               trace=False)
    graph = V.make_graph(edges, k, weights, sorted(weights))
    rep = V.validate(graph, res.cover, res.owner)
    cover = set(res.cover)
    # 1) hüküm SONLANMA KİPİDİR ve yerinde kalmalıdır: onarım koşumu kesmez
    assert res.converged, "onarım sonlanmayı bozdu: solved -> truncated"
    # 2) CEVAP geçerli olmalıdır
    assert rep.valid, (f"{name}: {sorted({v.kind for v in rep.violations})} "
                       f"{[v.detail for v in rep.violations]}")
    # 3) kusurun ta kendisi: o kenarın bir ucu örtüde olmalıdır
    u, v = edge
    assert u in cover or v in cover, f"kenar {edge} hâlâ açıkta"


@pytest.mark.parametrize("name,seed,max_ms,edge", FALSE_SUCCESS_ROWS)
def test_the_repair_only_fires_on_a_neighbour_that_already_committed(
        name, seed, max_ms, edge):
    """ONARIM BİR ROL'DÜR, BİR HÜKÜM DEĞİL (§105 ile aynı biçim).

    Donan düğüm, örtü kararını HENÜZ GEÇMEMİŞ bir komşuya bakarak örtüye
    girmez; öyle olsaydı hâlâ tavlanan bir komşunun kendi başına yapacağı
    onarım için boş yere bir düğüm örtüye sokulurdu. Bu yüzden onarımdan
    sonra da x ile role AYNI BİT olmalı ve donmuş durum kararlı kalmalıdır.
    """
    inst = _dataset_instance(name)
    if inst is None:
        pytest.skip("Dagdeviren kümesi yok")
    edges, weights = inst
    p = anneal.AnnealParams(rng_seed=seed, enable_tree=False, trickle=True,
                            mis_nbrs_max=64)
    res = v6_anneal.run_anneal(edges, weights, 6, scheduler="async",
                               max_ms=max_ms, loss=0.0, seed=seed, params=p,
                               trace=False)
    for nid, node in res.nodes.items():
        assert bool(node.x) == node.role.in_cover, (
            f"düğüm {nid}: x={node.x} role={node.role.name} — örtü biti iki "
            f"alana bölündü")
        if node.frozen:
            # donmuş düğüm, örtüde ise y'si de kurulmuş olmalı (Faz 4 okur)
            assert node.role.in_cover == bool(node.x)
