#!/usr/bin/env python3
"""`ccvc/bb/figures.py` testleri (brief §8).

Koşum:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_figures.py -q

Testlerin sorduğu soru "şekil çizildi mi" DEĞİLDİR. Şekil bir KANIT olduğunu
iddia ediyor; testler o iddiayı sınar:

  * Şekil 2'nin kırmızısı gerçekten doğrulayıcının ihlal listesinden mi geliyor?
    Geçerli çözümde sıfır kırmızı OLMALI, bozulmuş sahiplikte ihlal sayısı
    KADAR kırmızı olmalı. Sınırın tuttuğunu değil, BOZULMANIN GÖRÜNDÜĞÜNÜ
    sınarız (BULGULAR_BB'nin üç sessiz hatasından çıkan ders).
  * Şekil 3'ün panelleri örtünün monoton büyüdüğünü mü gösteriyor?
  * Şekil 6 iki rejimi de çizebiliyor mu (düz VE yükselen)?
  * Bayrağı kalkmış (INFEASIBLE / çözülemedi) koşumlar şekli ÇÖKERTİYOR mu?
"""
from __future__ import annotations

import dataclasses
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc import bridge  # noqa: E402
from ccvc.bb import bbcvc, figures, validate  # noqa: E402
from ccvc.bb.api import MAX_PAYLOAD, MsgType, Role  # noqa: E402

BUDGET_MS = 600_000
SLOW = os.environ.get("BBCVC_SLOW") == "1"


# --------------------------------------------------------------------------
# koşumlar bir kez kurulur: her test kendi koşumunu yaparsa dosya dakikalarca
# sürer ve ölçülen şey değişmez
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sync_run():
    return bbcvc.run_bbcvc(figures.WORKED_EDGES, figures.WORKED_WEIGHTS,
                           figures.WORKED_K, scheduler="sync", max_ms=BUDGET_MS)


@pytest.fixture(scope="module")
def async_run():
    return bbcvc.run_bbcvc(figures.WORKED_EDGES, figures.WORKED_WEIGHTS,
                           figures.WORKED_K, scheduler="async", max_ms=BUDGET_MS)


@pytest.fixture(scope="module")
def size_series():
    return figures.message_size_runs(slow=SLOW)


@pytest.fixture(scope="module")
def size_points(size_series):
    return figures.size_points_from_runs(size_series)


#: Kapasite bakımından YAPI GEREĞİ çözümsüz iki örnek. İkisi de "bugün
#: başarısız olan" örnek değil, "hiçbir doğru algoritmanın çözemeyeceği" örnek:
#:   * K4, k=1      -> |E|=6 > k·|V|=4 (Hakimi; .tex'in kendi uygunsuz örneği)
#:   * UDG15, k=2   -> ⌈m/k⌉ alt sınırı |V|'yi aşıyor
#: Ayrım, bu sabah bir tuzağın boşalmasına mal oldu: eski fixture "şu örnek
#: çözülemiyor" diye çivilenmişti ve bb-algo eskalasyonu onarınca örnek
#: çözülür hale gelip test YANLIŞ SEBEPTEN kırmızıya döndü. Başarısızlık burada
#: amaç değil ARAÇTI: gereken şey BİR ihlalli koşumdu, O koşum değil.
INFEASIBLE_BY_CONSTRUCTION = "kapasite atanamaz (bridge.capacity_feasible = False)"


def _assert_infeasible_by_construction(edges, weights, k):
    """Örneğin matematiksel olarak çözümsüz olduğunu DOĞRULA.

    Fixture'ın dayandığı gerçek budur ve algoritmadan bağımsızdır; algoritmanın
    o an hangi bayrağı kaldırdığı bb-algo'nun değişmezi, bu dosyanın değil.
    """
    g = validate.make_graph(list(edges), k, dict(weights))
    assert not bridge.capacity_feasible(g, set(weights))[0], \
        "örnek aslında çözülebilir; fixture yanlış kurulmuş"
    return g


@pytest.fixture(scope="module")
def infeasible_run():
    """K4, k=1: GERÇEK koşum, GERÇEK ihlaller (.tex'in uygunsuz örneği)."""
    edges = [(u, v) for u in range(1, 5) for v in range(u + 1, 5)]
    weights = {i: 1 for i in range(1, 5)}
    _assert_infeasible_by_construction(edges, weights, 1)
    return bbcvc.run_bbcvc(edges, weights, 1, scheduler="sync", max_ms=BUDGET_MS)


@pytest.fixture(scope="module")
def unresolved_run():
    """UDG(15, 0.38, tohum 2) k=2: GERÇEK koşum, GERÇEK taşkın ihlalleri.

    Aynı çizge k=3'te çözülüyor; k=2'de ⌈m/k⌉ alt sınırı |V|'yi aştığı için
    ÇÖZÜLEMEZ. Yani başarısızlık ayarlanmış değil, KURULMUŞTUR ve algoritma
    iyileştikçe kaybolmaz.

    Bayrağı elle koymak (`dataclasses.replace(run, unresolved=True)`) daha
    önceki çözümümdü ve DAHA KÖTÜYDÜ: bu dosyanın sözleşmesi
    `violation_artists == len(report.violations)` ve elle konmuş bir bayrağın
    arkasında sıfır ihlal vardır, yani test geçerken şekil hiçbir kırmızı yol
    çizmezdi. Gerçek ihlalli koşum, kırmızının kendisini sınar.
    """
    edges, weights, _ = figures.udg_instance(15, 0.38, 2)
    _assert_infeasible_by_construction(edges, weights, 2)
    return bbcvc.run_bbcvc(edges, weights, 2, scheduler="sync", max_ms=1_500_000)


@pytest.fixture(scope="module")
def stalled_run():
    """Duvar bütçesi dolmuş, dolayısıyla yakınsamamış gerçek koşum."""
    r = bbcvc.run_bbcvc(figures.WORKED_EDGES, figures.WORKED_WEIGHTS,
                        figures.WORKED_K, scheduler="sync", max_ms=1_000)
    assert not r.converged
    return r


def _nonempty(res: figures.FigureResult) -> None:
    assert len(res.paths) == 2, "her şekil PNG ve SVG üretir"
    exts = sorted(os.path.splitext(p)[1] for p in res.paths)
    assert exts == [".png", ".svg"]
    for p in res.paths:
        assert os.path.exists(p), p
        assert os.path.getsize(p) > 2000, f"{p} neredeyse boş"
    assert res.caption.strip(), "şeklin altında bir cümle olmalı (brief §8)"


# ==========================================================================
# 1. Yedi şeklin hepsi gerçek koşumdan üretiliyor ve dosya yazıyor
# ==========================================================================
def test_all_seven_figures_are_written(tmp_path, sync_run, async_run, size_series):
    out = str(tmp_path / "run")
    figs = figures.make_all_figures(sync_run, out, async_run=async_run,
                                    size_series=size_series)
    assert sorted(figs) == ["convergence", "message_size", "messages",
                            "ownership", "phases", "sync_async", "topology"], \
        "brief §8 yedi şekil ister"
    for res in figs.values():
        _nonempty(res)
    idx = os.path.join(out, "index.md")
    assert os.path.exists(idx)
    body = open(idx, encoding="utf-8").read()
    for res in figs.values():
        assert res.caption in body, "her şeklin cümlesi index'e girmeli"


@pytest.mark.parametrize("fn,kwargs", [
    ("figure_topology", {}),
    ("figure_ownership", {}),
    ("figure_phase_snapshots", {}),
    ("figure_convergence", {}),
])
def test_single_figure_entry_points(tmp_path, sync_run, fn, kwargs):
    res = getattr(figures, fn)(sync_run, str(tmp_path), **kwargs)
    _nonempty(res)


def test_worked_example_fixture_matches_the_tex_document():
    """Fixture belgedeki örnekle birebir: 10 düğüm, 15 kenar, k=2, ağırlıklar."""
    assert len(figures.WORKED_WEIGHTS) == 10
    assert len(figures.WORKED_EDGES) == 15
    assert figures.WORKED_K == 2
    assert [figures.WORKED_WEIGHTS[i] for i in range(1, 11)] == \
        [5, 2, 4, 3, 6, 2, 3, 2, 5, 4]
    assert sorted(figures.WORKED_POS) == sorted(figures.WORKED_WEIGHTS), \
        ".tex koordinatları her düğüm için verilmiş olmalı"


def test_figures_are_drawn_from_the_run_not_from_constants(sync_run):
    """Ölçülmüş gerçekler (BULGULAR_BB) koşumdan gelmeli, dosyadan değil."""
    v = figures.view_of(sync_run)
    assert sorted(v.backbone) == [2, 4, 6, 7, 8], "omurga {2,4,6,7,8}"
    assert len(v.cover) == 8 == math.ceil(len(v.edges) / v.k), "|C| = ⌈|E|/k⌉"
    assert sync_run.total_weight == 27


# ==========================================================================
# 2. Şekil 2: kırmızı YALNIZ doğrulayıcının ihlal listesinden
# ==========================================================================
def test_figure2_has_no_red_on_a_valid_solution(tmp_path, sync_run):
    res = figures.figure_ownership(sync_run, str(tmp_path))
    report = res.data["report"]
    assert report.valid, "çalışan örnek geçerli olmalı"
    assert res.violation_artists == 0, "geçerli çözümde ihlal çizeri olamaz"
    assert res.red_artists == 0, "geçerli çözümde HİÇ kırmızı olamaz"


def _corrupt(owner):
    """Üç ayrı bozulma: sahipsiz kenar, uç olmayan sahip, kapasite taşkını."""
    bad = dict(owner)
    del bad[(8, 10)]          # sahipsiz kenar
    bad[(9, 10)] = 2          # sahip kenarın ucu değil
    bad[(2, 3)] = 2           # 2'nin yükü k=2'yi aşar
    bad[(2, 4)] = 2
    bad[(1, 2)] = 2
    return bad


def test_figure2_draws_exactly_one_red_artist_per_violation(tmp_path, sync_run):
    """SINIRIN TUTTUĞUNU DEĞİL, BOZULMANIN GÖRÜNDÜĞÜNÜ sına.

    Bozulmamış bir sahiplikte kırmızı olmaması tek başına hiçbir şey kanıtlamaz;
    kırmızıyı hiç çizmeyen bir uygulama da o testi geçerdi.
    """
    res = figures.figure_ownership(sync_run, str(tmp_path),
                                   owner=_corrupt(sync_run.owner),
                                   name="fig2_corrupt")
    report = res.data["report"]
    assert not report.valid
    kinds = {v.kind for v in report.violations}
    assert validate.BAD_OWNER in kinds and validate.OVERLOAD in kinds
    assert res.violation_artists == len(report.violations), \
        "her ihlal tam bir kırmızı çizer (sözleşme)"
    assert res.violation_artists >= 2
    assert res.red_artists >= res.violation_artists
    _nonempty(res)


def test_figure2_red_grows_when_the_cover_itself_is_broken(tmp_path, sync_run):
    """Örtüden düğüm düşürmek AÇIKTA KENAR üretir ve şekle kırmızı olarak girer."""
    cover = [v for v in sync_run.cover if v != 3]
    owner = {e: o for e, o in sync_run.owner.items() if o != 3}
    res = figures.figure_ownership(sync_run, str(tmp_path), owner=owner,
                                   cover=cover, name="fig2_broken_cover")
    report = res.data["report"]
    assert validate.BAD_OWNER in {v.kind for v in report.violations}
    assert res.violation_artists == len(report.violations)
    assert res.violation_artists > 0


def test_figure2_labels_carry_load_over_k(tmp_path, sync_run):
    res = figures.figure_ownership(sync_run, str(tmp_path), name="fig2_labels")
    load = res.data["load"]
    assert sum(load.values()) == len(sync_run.owner) == 15
    assert all(load[v] <= figures.WORKED_K for v in sync_run.cover)


# ==========================================================================
# 3. Şekil 3: dört panel, monoton büyüyen örtü
# ==========================================================================
def test_figure3_cover_is_non_decreasing_across_the_four_panels(tmp_path, sync_run):
    res = figures.figure_phase_snapshots(sync_run, str(tmp_path))
    sizes = res.data["cover_size"]
    weights = res.data["weight"]
    assert len(sizes) == 4, "brief §8/3 dört panel ister"
    assert sizes == sorted(sizes), f"|C| geri gitti: {sizes}"
    assert weights == sorted(weights), f"Σw geri gitti: {weights}"
    assert sizes[-1] == len(sync_run.cover), "son panel koşumun çıktısı olmalı"
    assert weights[-1] == sync_run.total_weight
    _nonempty(res)


def test_figure3_panels_are_the_real_phase_states(sync_run):
    """Faz 1 sonu omurgadır; faz 2 sonu örtü genişlemesini içerir."""
    h = figures.history_from_run(sync_run)
    p1 = h.roles_at_phase(1)
    assert {v for v, r in p1.items() if r == Role.MIS} == {2, 6, 8}
    assert {v for v, r in p1.items() if r.in_backbone} == {2, 4, 6, 7, 8}
    p2 = h.roles_at_phase(2)
    assert {v for v, r in p2.items() if r.in_cover} >= {2, 4, 6, 7, 8}
    p4 = h.roles_at_phase(4)
    assert sorted(v for v, r in p4.items() if r.in_cover) == sorted(sync_run.cover)


def test_history_is_reconstructed_from_the_log_only(sync_run):
    """Tarihçe yeniden koşumdan değil `SimNet.log_records`'tan gelir."""
    assert sync_run.net.log_records, "günlük boş; tarihçe türetilemez"
    h = figures.history_from_run(sync_run)
    assert h.events, "rol olayı bulunamadı"
    assert all(e.t_ms >= 0 for e in h.events)
    assert h.unit == "slot" and h.tau_ms == 200
    ends = [h.phase_end_ms[p] for p in (1, 2, 3, 4)]
    assert ends == sorted(ends), f"faz sınırları monoton değil: {ends}"


def test_async_history_is_measured_in_milliseconds(async_run):
    h = figures.history_from_run(async_run)
    assert h.unit == "ms" and h.tau_ms == 1
    assert h.x_of(1234) == 1234.0


# ==========================================================================
# 4. Şekil 4: zaman çizgisi
# ==========================================================================
def test_figure4_timeline_ends_at_the_runs_cover(tmp_path, sync_run):
    res = figures.figure_convergence(sync_run, str(tmp_path))
    assert res.data["final_cover"] == len(sync_run.cover)
    _nonempty(res)


def test_timeline_series_is_monotone_in_cover_and_weight(sync_run):
    s = figures.history_from_run(sync_run).series()
    assert s["cover_size"] == sorted(s["cover_size"])
    assert s["weight"] == sorted(s["weight"])
    assert s["x"] == sorted(s["x"])
    assert s["cover_size"][-1] == len(sync_run.cover)


# ==========================================================================
# 5. Şekil 5: mesaj kırılımı
# ==========================================================================
def test_figure5_puts_sync_and_async_side_by_side(tmp_path, sync_run, async_run):
    res = figures.figure_message_breakdown({"sync": sync_run, "async": async_run},
                                           str(tmp_path))
    assert res.data["modes"] == ["sync", "async"]
    assert res.data["tx"] == {"sync": sync_run.tx, "async": async_run.tx}
    _nonempty(res)


def test_derived_bytes_per_type_sum_back_to_the_measured_total(sync_run):
    """Tip başına bayt TÜRETİLİR; türetme kesin değilse toplam tutmaz."""
    per = figures.bytes_by_type(sync_run)
    assert sum(per.values()) == sync_run.bytes_tx
    hello = per[int(MsgType.HELLO)]
    n_hello = sync_run.by_type_tx[int(MsgType.HELLO)]
    assert hello >= 13 * n_hello, "HELLO en az sabit başlık kadar olmalı"
    assert hello <= MAX_PAYLOAD * n_hello


def test_every_message_type_is_either_modelled_or_declared_unmodelled():
    """Bayt modeli ile `MsgType` arasında SESSİZ boşluk kalamaz.

    İkisi tam bir bölüntü olmalı: ya tipin telde gövdesi var ve boyu kesin
    biliniyor, ya da gövdesi henüz yok ve bu AÇIKÇA listeleniyor. Üçüncü hâl
    (tip var, boy bilinmiyor, kimse söylemiyor) baytı sessizce HELLO'ya yazar.
    """
    sizes = figures.fixed_sizes()
    unmodelled = figures.unmodelled_types()
    assert int(MsgType.HELLO) not in sizes
    assert set(sizes) | set(unmodelled) == \
        {int(m) for m in MsgType if m is not MsgType.HELLO}
    assert not (set(sizes) & set(unmodelled)), "bir tip iki yerde birden"
    assert all(0 < b <= MAX_PAYLOAD for b in sizes.values())


def test_an_unmodelled_message_type_raises_instead_of_landing_in_hello(sync_run):
    """SINIRIN TUTTUĞUNU DEĞİL, BOZULMANIN GÖRÜNDÜĞÜNÜ sına.

    HELLO baytı çıkarmayla bulunuyor; modellenmemiş bir tipin baytı sessizce
    HELLO'ya yazılırsa TOPLAM YİNE TUTAR, dolayısıyla hata hiçbir toplamda
    görünmez. Bu yüzden uydurma bir tip numarası enjekte edilip patladığı
    doğrulanır.
    """
    poisoned = dict(sync_run.by_type_tx)
    poisoned[99] = 7
    doctored = dataclasses.replace(sync_run, by_type_tx=poisoned)
    with pytest.raises(figures.MissingData) as err:
        figures.bytes_by_type(doctored)
    assert "99" in str(err.value)


def test_a_declared_unmodelled_type_also_raises_when_it_actually_appears(sync_run):
    """Gövdesi henüz yazılmamış tip (ör. DFS-Spanning-Backbone'un TOKEN'ı) koşumda görünürse.

    Listede olmak bir muafiyet değildir: tip ölçümde GERÇEKTEN çıktığı anda
    baytı bilinmiyor demektir ve hesap reddedilir.
    """
    unmodelled = figures.unmodelled_types()
    if not unmodelled:
        pytest.skip("şu an modellenmemiş tip yok; tel bütün tipleri tanıyor")
    poisoned = dict(sync_run.by_type_tx)
    poisoned[unmodelled[0]] = 3
    doctored = dataclasses.replace(sync_run, by_type_tx=poisoned)
    with pytest.raises(figures.MissingData):
        figures.bytes_by_type(doctored)


# ==========================================================================
# 6. Şekil 6: iki rejim
# ==========================================================================
def test_figure6_renders_a_flat_and_a_rising_curve(tmp_path, size_points):
    """BULGU 3: G8 birim diskte tutuyor, kıyas rejiminde tutmuyor."""
    res = figures.figure_message_size(size_points, str(tmp_path))
    flat, rising = res.data["flat"], res.data["rising"]
    assert flat, f"düz eğri yok: {res.data['summary']}"
    assert rising, f"yükselen eğri yok: {res.data['summary']}"
    for label in flat:
        assert "UDG" in label
        span = res.data["summary"][label]
        assert span["deg_max"] - span["deg_min"] >= 4, \
            "düzlük iddiası için derece gerçekten artmış olmalı"
    for label in rising:
        assert res.data["summary"][label]["payload_span"] > 2
    assert not res.data["over_ceiling"], "250 B aşılmış"
    _nonempty(res)


def test_figure6_also_plots_bytes_normalised_per_node(size_points, tmp_path):
    """Çerçeveyi küçültmek toplam baytı küçültmek DEĞİLDİR; iki eksen de gerek.

    Bayt ekseni DÜĞÜM BAŞINA olmalı: ham `bytes_tx` |V| ile büyüdüğü için,
    farklı n'de koşan iki seriyi aynı eksende kıyaslamak boyut farkını yoğunluk
    farkı diye okutur. Testin sınadığı şey, serilerin n aralıklarının gerçekten
    ayrıştığı ve buna rağmen normalleştirilmiş eksenin tanımlı olduğu.
    """
    res = figures.figure_message_size(size_points, str(tmp_path), name="fig6_bytes")
    summ = res.data["summary"]
    for label, v in summ.items():
        assert v["bytes_min"] > 0 and v["bytes_max"] >= v["bytes_min"], label
        assert v["bytes_per_node_min"] > 0
        assert v["points"] >= 2, f"{label}: eğri çizmeye tek nokta yetmez"
    spans = {(v["n_min"], v["n_max"]) for v in summ.values()}
    assert len(spans) > 1, \
        "seriler aynı n'de koşuyorsa normalleştirme testi bir şey kanıtlamaz"


def test_figure6_uses_the_same_mis_cap_in_both_regimes(size_series):
    """Düzlük GEOMETRİDEN gelmeli, `mis_nbrs_max` sınırından değil.

    İki rejim farklı sınırla koşsaydı birim disk eğrisinin düz çıkması hiçbir
    şey kanıtlamazdı; sınır zaten 5'te keserdi.
    """
    assert figures.MIS_CAP_FOR_SIZE_STUDY > 5
    for runs in size_series.values():
        for r in runs:
            caps = {n.p.mis_nbrs_max for n in r.nodes.values()}
            assert caps == {figures.MIS_CAP_FOR_SIZE_STUDY}


def test_message_size_runs_never_exceed_the_250_byte_ceiling(size_series):
    for label, runs in size_series.items():
        for r in runs:
            assert r.max_payload <= MAX_PAYLOAD, f"{label}: I3 ihlali"


def test_figure6_refuses_to_draw_without_data(tmp_path):
    """Eksik veri bir grafik değil, BİR HATA üretmeli.

    Boş bir eğri, o varyant için ölçüm yapılmış ama sonuç çıkmamış gibi okunur;
    oysa hiç koşulmamıştır. Sessiz boşluk, yanlış sayıdan daha kötüdür çünkü
    kimse sorgulamaz.
    """
    with pytest.raises(figures.MissingData):
        figures.figure_message_size({}, str(tmp_path), name="fig6_none")
    with pytest.raises(figures.MissingData) as err:
        figures.figure_message_size({"boş": []}, str(tmp_path), name="fig6_empty")
    assert "boş" in str(err.value)


def test_size_point_refuses_missing_measurements():
    with pytest.raises(figures.MissingData) as err:
        figures.SizePoint.of("V", n=10, m=20, max_payload=None, bytes_tx=5,
                             converged=True)
    assert "max_payload" in str(err.value)
    with pytest.raises(figures.MissingData):
        figures.SizePoint.of("V", n=10, m=20, max_payload=23, bytes_tx=None,
                             converged=True)


def test_figure6_rejects_raw_runs_instead_of_crashing_obscurely(tmp_path, sync_run):
    with pytest.raises(figures.MissingData) as err:
        figures.figure_message_size({"V": [sync_run]}, str(tmp_path),
                                    name="fig6_raw")
    assert "SizePoint" in str(err.value)


# ==========================================================================
# 7. Şekil 7: sync/async
# ==========================================================================
def test_figure7_reports_the_cover_difference(tmp_path, sync_run, async_run):
    res = figures.figure_sync_vs_async(sync_run, async_run, str(tmp_path))
    assert res.data["same_cover"] is (set(sync_run.cover) == set(async_run.cover))
    assert res.data["only_sync"] == sorted(set(sync_run.cover) - set(async_run.cover))
    assert res.data["only_async"] == sorted(set(async_run.cover) - set(sync_run.cover))
    _nonempty(res)


def test_figure7_compares_convergence_in_the_same_unit(tmp_path, sync_run, async_run):
    """Slot ile milisaniyeyi aynı eksende kıyaslamak ölçüm hatası olurdu."""
    res = figures.figure_sync_vs_async(sync_run, async_run, str(tmp_path),
                                       name="fig7_units")
    t = res.data["t_conv_ms"]
    assert t["sync"] == sync_run.slots * 200, "senkron süre slot × τ"
    assert t["async"] == async_run.t_conv_ms


# ==========================================================================
# 8. Bayraklı koşumlar şekli çökertmiyor
# ==========================================================================
def test_every_figure_survives_an_infeasible_run(tmp_path, infeasible_run):
    out = str(tmp_path / "infeasible")
    figs = figures.make_all_figures(infeasible_run, out, async_run=infeasible_run)
    for res in figs.values():
        _nonempty(res)
    own = figs["ownership"]
    assert own.violation_artists == len(own.data["report"].violations) > 0


def test_the_red_count_tracks_the_violation_list_across_both_infeasible_cases(
        tmp_path, infeasible_run, unresolved_run):
    """Sözleşme TEK bir örnekte değil, ihlal sayısı FARKLI iki koşumda tutmalı.

    Tek örnekte doğrulanan bir eşitlik, sabit bir sayı döndüren bir uygulamayla
    da geçerdi. İki koşumun ihlal sayıları farklı olduğundan (K4/k=1 ile
    UDG15/k=2) eşitlik ancak gerçekten listeden çizildiğinde tutar.
    """
    counts = []
    for i, run in enumerate((infeasible_run, unresolved_run)):
        res = figures.figure_ownership(run, str(tmp_path), name=f"fig2_case{i}")
        assert res.violation_artists == len(res.data["report"].violations)
        counts.append(res.violation_artists)
    assert len(set(counts)) == 2, \
        f"iki örnek aynı sayıda ihlal veriyor ({counts}); eşitlik sabitle de geçerdi"


def test_every_figure_survives_an_unresolved_run(tmp_path, unresolved_run):
    """Çözümü OLMAYAN örnekte şekiller çökmez ve kırmızıyı gerçekten çizer."""
    out = str(tmp_path / "unresolved")
    figs = figures.make_all_figures(unresolved_run, out, async_run=unresolved_run)
    for res in figs.values():
        _nonempty(res)
    own = figs["ownership"]
    report = own.data["report"]
    assert not report.valid, "çözümsüz örnekte doğrulayıcı geçerli demiş"
    assert own.violation_artists == len(report.violations) > 0, \
        "her ihlal tam bir kırmızı çizer; burada çizilecek ihlal VAR"
    assert own.red_artists > 0


def test_every_figure_survives_a_stalled_run(tmp_path, stalled_run):
    out = str(tmp_path / "stalled")
    figs = figures.make_all_figures(stalled_run, out, async_run=stalled_run)
    for res in figs.values():
        _nonempty(res)
    assert "YAKINSAMADI" in figures._flag_note(stalled_run)


def test_a_run_that_never_converged_is_stamped_not_hidden(tmp_path):
    """Duvar bütçesi dolmuş koşum sessizce geçilmez; şeklin üstüne yazılır."""
    r = bbcvc.run_bbcvc(figures.WORKED_EDGES, figures.WORKED_WEIGHTS,
                        figures.WORKED_K, scheduler="sync", max_ms=1_000)
    assert not r.converged
    assert "YAKINSAMADI" in figures._flag_note(r)
    _nonempty(figures.figure_topology(r, str(tmp_path), name="fig1_stalled"))


# ==========================================================================
# 9. Gri tonlama ve belirlenimcilik
# ==========================================================================
def test_roles_are_distinguishable_without_colour():
    """Makale gri basılırsa bilgi kaybolmamalı: işaret ve dolgu da ayrışır."""
    markers = [figures.ROLE_STYLE[r]["marker"] for r in Role]
    fills = [figures.ROLE_STYLE[r]["face"] for r in Role]
    assert len(set(markers)) >= 3, "roller yalnız renkle ayrılıyor"
    assert len(set(fills)) == len(fills), "dolgu tonları da ayrık olmalı"
    assert figures.ROLE_STYLE[Role.OUT]["face"] == "#ffffff", \
        "C dışı düğüm içi boş (brief §8/1)"
    assert figures.ROLE_STYLE[Role.COVER]["hatch"], "tarama deseni gri tonlama için"


def test_layout_is_deterministic():
    edges = [(1, 2), (2, 3), (3, 4), (4, 1), (1, 3)]
    a = figures.auto_layout([1, 2, 3, 4], edges)
    b = figures.auto_layout([1, 2, 3, 4], edges)
    assert a == b, "yerleşimde rastgelelik var"
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in a.values())


def test_the_same_run_produces_the_same_svg_bytes(tmp_path, sync_run):
    one = figures.figure_topology(sync_run, str(tmp_path / "a"))
    two = figures.figure_topology(sync_run, str(tmp_path / "b"))
    svg_a = [p for p in one.paths if p.endswith(".svg")][0]
    svg_b = [p for p in two.paths if p.endswith(".svg")][0]
    assert open(svg_a, "rb").read() == open(svg_b, "rb").read(), \
        "aynı koşum iki farklı şekil üretiyor"


def test_worked_example_uses_the_tex_coordinates(sync_run):
    v = figures.view_of(sync_run)
    assert v.pos == figures.WORKED_POS, \
        "belgedeki resimle üst üste binsin diye .tex koordinatları kullanılır"


def test_auto_layout_is_used_for_unknown_graphs():
    edges = [(1, 2), (2, 3), (3, 1)]
    r = bbcvc.run_bbcvc(edges, {1: 1, 2: 2, 3: 3}, 2, scheduler="sync",
                        max_ms=BUDGET_MS)
    v = figures.view_of(r)
    assert set(v.pos) == {1, 2, 3}
    assert v.pos != figures.WORKED_POS


# ==========================================================================
# 10. Şekil 8 — anytime görünüm, ve ONUN veri sözleşmesi
# ==========================================================================
@pytest.fixture(scope="module")
def anneal_trace():
    """GERÇEK ölçümden anytime izi: aynı örnek, artan duvar bütçesi.

    Uydurulmuş sayı yok; her nokta koşturulmuş bir BB-CVC ve doğrulayıcıdan
    geçmiş bir çözümdür. BB-CVC anytime DEĞİL, dolayısıyla iz ilk geçerli
    çözüme kadar boştur; bu bir kusur değil ölçülen gerçektir ve ANNEAL'ın
    eğrisiyle yan yana konduğunda fark tam olarak budur.
    """
    return figures.anytime_trace_from_budgets(
        figures.WORKED_EDGES, figures.WORKED_WEIGHTS, figures.WORKED_K,
        [1_000, 3_000, 6_000, 9_000, 20_000])


def test_figure8_draws_energy_time_and_time_to_first_solution(tmp_path, anneal_trace):
    res = figures.figure_anneal_anytime([anneal_trace], str(tmp_path))
    _nonempty(res)
    lab = next(iter(res.data["traces"]))
    info = res.data["traces"][lab]
    assert info["t_first_valid_ms"] == anneal_trace.t_first_valid_ms
    assert info["energy_total_mah"] > 0, "enerji ölçülmemiş"
    assert info["observer_best_weight"] == 27.0, "çalışan örneğin ölçülmüş ağırlığı"


def test_figure8_refuses_to_draw_without_traces(tmp_path):
    """Veri yoksa makul görünen bir grafik değil, GÜRÜLTÜLÜ bir hata."""
    with pytest.raises(figures.MissingData) as err:
        figures.figure_anneal_anytime([], str(tmp_path), name="fig8_none")
    assert "AnytimeTrace" in str(err.value)


def test_figure8_refuses_a_trace_that_is_not_the_contract(tmp_path):
    with pytest.raises(figures.MissingData):
        figures.figure_anneal_anytime([object()], str(tmp_path), name="fig8_bad")


def test_figure8_refuses_a_trace_that_violates_its_own_invariant(tmp_path):
    """BOZULMANIN GÖRÜNDÜĞÜNÜ sına: 'en iyi' artan bir iz çizilmemeli.

    Bu tam olarak `anytime_trace_from_budgets`ın doğrulayıcı kapısı olmasa
    üreteceği izdir: düğüm kodu 3000 ms'de Σw=21 bildiriyor ama o örtü geçerli
    değil, ve ham sayı yazılsaydı iz 21'den 27'ye çıkardı.
    """
    from ccvc.bb.sweep import AnytimeSample, AnytimeTrace
    bad = AnytimeTrace("V-bozuk", [
        AnytimeSample(0, 0.1, 10, 21.0, 5),
        AnytimeSample(10, 0.2, 20, 27.0, 8),
    ])
    with pytest.raises(Exception) as err:
        figures.figure_anneal_anytime([bad], str(tmp_path), name="fig8_bozuk")
    assert "artıyor" in str(err.value)


def test_the_trace_helper_only_counts_validated_solutions(anneal_trace):
    """Doğrulayıcı kapısı olmasa iz kendi sözleşmesini ihlal ederdi."""
    weights = [s.observer_best_weight for s in anneal_trace.samples if s.valid]
    assert weights == sorted(weights, reverse=True)
    assert anneal_trace.samples[0].observer_best_weight is None, \
        "ilk bütçede geçerli çözüm yok; boş olmalı, sıfır değil"


def test_figure8_reports_runs_that_never_reached_a_valid_solution(tmp_path):
    """Hiç çözüm bulamamak VERİ EKSİĞİ DEĞİL SONUÇTUR; çizilmez, sayılır."""
    short = figures.anytime_trace_from_budgets(
        figures.WORKED_EDGES, figures.WORKED_WEIGHTS, figures.WORKED_K,
        [1_000, 2_000], variant="kısa bütçe")
    assert short.t_first_valid_ms is None
    res = figures.figure_anneal_anytime([short], str(tmp_path), name="fig8_never")
    assert res.data["never_valid"], "hiç çözüm bulamayan koşum raporlanmadı"
    assert res.data["valid_axis_fraction"]["kısa bütçe#1"] == 0.0
    _nonempty(res)


# ==========================================================================
# 11. Şekil 6'nın süpürme satırlarından beslenmesi
# ==========================================================================
def test_size_points_can_be_built_from_sweep_rows():
    from ccvc.bb import matrix, sweep
    cell = [c for c in matrix.feasible_cells() if c.n == 10 and c.ratio == 2][0]
    insts = [sweep.synthetic_instance(cell, s) for s in range(2)]
    rows = sweep.sweep(insts, sweep.builtin_variants(), schedulers=("sync",),
                       opts=sweep.SweepOptions(k=4, max_ms=600_000))
    pts = figures.size_points_from_rows(rows)
    assert set(pts) == {"MIS-Connector-Backbone", "MIS-Connector-TreeAgg"}
    for label, series in pts.items():
        assert len(series) == 2
        for p in series:
            assert p.max_payload > 0 and p.bytes_tx > 0
            assert p.avg_degree == pytest.approx(2 * p.m / p.n)


def test_size_points_from_rows_raises_when_everything_was_skipped():
    from ccvc.bb import matrix, sweep
    cell = [c for c in matrix.feasible_cells() if c.n == 10 and c.ratio == 2][0]
    insts = [sweep.synthetic_instance(cell, 0)]
    rows = sweep.sweep(insts, sweep.builtin_variants()[:1], schedulers=("sync",),
                       opts=dataclasses.replace(
                           sweep.SweepOptions(k=4), time_budget_s=-1.0))
    assert all(r.status == "skipped" for r in rows)
    with pytest.raises(figures.MissingData):
        figures.size_points_from_rows(rows)


# ==========================================================================
# 12. Şekil 8: zarf ile son durum AYRI çizilmeli ve etiketlenmeli
# ==========================================================================
def _excursion_trace(variant="Anneal-Local"):
    """Yokuş yukarı hamleleri olan iz: zarf azalırken yörünge SALINIR.

    Bu, Metropolis'in gerçek davranışının şekli: son durum (30) ziyaret edilen
    en iyiden (27) kötü. bb-core bunu 60 tohumun 29'unda ölçtü.
    """
    from ccvc.bb.sweep import AnytimeSample, AnytimeTrace
    steps = [(0, 0.0, 40.0, 40.0), (10, 0.5, 35.0, 35.0), (20, 0.9, 35.0, 44.0),
             (30, 1.3, 27.0, 27.0), (40, 1.6, 27.0, 33.0), (50, 1.9, 27.0, 30.0)]
    return AnytimeTrace(variant, [
        AnytimeSample(t_ms=t, energy_mah=e, tx=t * 2, observer_best_weight=b,
                      cover_size=6, current_weight=c) for t, e, b, c in steps])


def test_figure8_plots_the_trajectory_alongside_the_envelope(tmp_path):
    """Yalnız zarfı çizmek, tablodaki sayıya yakınsamayan bir hikâye anlatırdı."""
    tr = _excursion_trace()
    res = figures.figure_anneal_anytime([tr], str(tmp_path),
                                        final_weights={"Anneal-Local": 30.0},
                                        name="fig8_excursion")
    info = res.data["traces"]["Anneal-Local#1"]
    assert res.data["has_trajectory"] is True
    assert info["trajectory_points"] == 6
    assert info["observer_best_weight"] == 27.0
    assert info["final_weight_reported"] == 30.0
    assert info["observer_best_weight"] < info["final_weight_reported"], \
        "bu izin bütün anlamı ikisinin ayrışmasında; ayrışmıyorsa test boş"
    _nonempty(res)


def test_figure8_caption_labels_the_envelope_as_an_observer_bound(tmp_path):
    """Çıplak bırakılırsa zarf, sistemin kendisi hakkında bildiği bir şey
    diye okunur. Geçerlilik örtü+bağlılık+kapasitedir ve hiçbiri 1-atlama
    durumundan bilinemez; ağ bunu sayılmayan bir convergecast olmadan
    bildiremez."""
    from ccvc.bb.sweep import AnytimeTrace
    res = figures.figure_anneal_anytime([_excursion_trace()], str(tmp_path),
                                        final_weights={"Anneal-Local": 30.0},
                                        name="fig8_label")
    assert AnytimeTrace.OBSERVER_LABEL in res.caption
    assert "gözlemci" in res.caption
    assert "son donmuş durum" in res.caption, \
        "altyazı raporlanan sayının hangisi olduğunu söylemeli"


def test_figure8_says_so_when_the_trajectory_was_never_measured(tmp_path,
                                                                anneal_trace):
    """`current_weight` taşımayan iz sessizce zarf gibi çizilmemeli."""
    from ccvc.bb.sweep import AnytimeSample, AnytimeTrace
    stripped = AnytimeTrace(anneal_trace.variant, [
        AnytimeSample(t_ms=s.t_ms, energy_mah=s.energy_mah, tx=s.tx,
                      observer_best_weight=s.observer_best_weight,
                      cover_size=s.cover_size, current_weight=None)
        for s in anneal_trace.samples])
    res = figures.figure_anneal_anytime([stripped], str(tmp_path),
                                        name="fig8_no_traj")
    assert res.data["has_trajectory"] is False
    assert "Yörünge çizilmedi" in res.caption


def test_the_envelope_may_differ_from_the_final_state_without_being_an_error():
    """Zarf ile son durumun ayrışması SÖZLEŞMEYE UYGUNDUR, çelişki değildir.

    Metropolis yokuş yukarı kabul ettiği için son durum yerel minimumdur.
    Çapraz denetim yalnız TERS yönü, yani zarfın son durumdan kötü olmasını
    ihlal sayar; onu da sınarız, yoksa denetim hiçbir şeyi reddetmiyor olurdu.
    """
    from ccvc.bb import sweep as S
    tr = _excursion_trace()
    worse_final = S.VariantResult(
        cover=[1, 2, 3, 4, 5, 6], owner={}, total_weight=30.0, tx=1, rx=1,
        retx=0, bytes_tx=1, max_payload=1, slots=1, t_conv_ms=1, converged=True,
        infeasible=False, unresolved=False, by_phase_tx={}, by_type_tx={},
        trace=tr)
    assert S._trace_agreement(worse_final) == "yes", \
        "zarfın son durumdan iyi olması normaldir"
    better_final = dataclasses.replace(worse_final, total_weight=20.0)
    verdict = S._trace_agreement(better_final)
    assert verdict.startswith("no:") and "kaçırmış" in verdict, \
        "zarf son durumdan KÖTÜ ise bu bir sözleşme ihlalidir"


# ==========================================================================
# 13. Şekil 5: alıcı atıflı rx, gönderen atıflı tx'ten AYRI
# ==========================================================================
def test_figure5_reports_both_attributions(tmp_path, sync_run, async_run):
    res = figures.figure_message_breakdown({"sync": sync_run, "async": async_run},
                                           str(tmp_path), name="fig5_attr")
    d = res.data
    assert d["rx_by_receiver_phase"] and d["bytes_rx_by_receiver_phase"]
    assert d["phase_type_cells"]["sync"] > 0, "faz × tip çapraz tablosu boş"
    assert set(d["rx_caused"]) == set(d["rx_processed"]) == {"sync", "async"}
    _nonempty(res)


def test_sender_and_receiver_phase_breakdowns_are_not_the_same_numbers(sync_run):
    """SINIRIN TUTTUĞUNU DEĞİL, İKİ ATFIN AYRIŞTIĞINI sına.

    Slot t'de gönderilen çerçeve slot t+1'de işlenir, dolayısıyla iki kırılım
    aynı çerçeveleri farklı fazlara yazar. Eşit çıksalardı biri diğerinin
    kopyası olurdu ve şeklin (d) paneli hiçbir şey eklemezdi.
    """
    recv = figures.receiver_breakdown(sync_run)["rx_by_receiver_phase"]
    sender = sync_run.by_phase_tx
    assert recv and sender
    assert dict(recv) != dict(sender), "iki atıf ayırt edilemiyor"


def test_figure5_refuses_a_run_whose_network_lacks_receiver_counters(sync_run):
    """Gönderen atıflı sayılarla ikame etmek her çerçeveyi bir faz erken gösterir."""
    class _OldNet:
        edges = []
    stripped = dataclasses.replace(sync_run, net=_OldNet())
    with pytest.raises(figures.MissingData) as err:
        figures.receiver_breakdown(stripped)
    assert "receiver_totals" in str(err.value)


# ==========================================================================
# 14. Şekil 9: Faz 0 kimliği ve el sıkışma oranı
# ==========================================================================
@pytest.fixture(scope="module")
def bootstrap_pts():
    graphs = [("worked", figures.WORKED_EDGES, figures.WORKED_WEIGHTS)]
    for n, rad in ((14, 0.42), (18, 0.38), (22, 0.38)):
        inst = figures.udg_instance(n, rad, 3)
        if inst:
            graphs.append((f"udg{n}", inst[0], inst[1]))
    return figures.bootstrap_points(graphs)


def test_figure9_shows_the_identity_holding_only_under_sync(tmp_path, bootstrap_pts):
    """6n+4m senkronda KİMLİK, asenkronda DEĞİL — ölçülmüş karşıtlık."""
    res = figures.figure_bootstrap_identity(bootstrap_pts, str(tmp_path))
    summ = res.data["summary"]
    assert summ["sync"]["residual_max_abs_pct"] == 0.0, \
        "senkronda kimlik artıksız tutmalı"
    assert summ["async"]["residual_mean_pct"] < -1.0, \
        "asenkron kimliğin ALTINDA kalmalı; eşit çıkıyorsa karşıtlık yok"
    _nonempty(res)


def test_the_handshake_term_is_scheduler_independent(bootstrap_pts):
    """El sıkışma kenar başına tam 2 çerçeve, HER İKİ kipte de artıksız."""
    for p in bootstrap_pts:
        assert p.link_per_edge == 2.0, f"{p.scheduler} n={p.n}: {p.link_per_edge}"
        assert p.link_ack_per_edge == 2.0


def test_the_async_shortfall_is_not_reattribution(bootstrap_pts):
    """Çerçeveler faza YENİDEN YAZILMIYOR, hiç gönderilmiyor.

    İlk açıklamam muhasebe sınırıydı ve ekip liderinin ölçümü onu çürüttü:
    yeniden atfedilseler faz 1'de görünürlerdi. Burada TOPLAM HELLO sayısı
    karşılaştırılır, ki faz atfından tamamen bağımsızdır.
    """
    by = {}
    for p in bootstrap_pts:
        by.setdefault((p.n, p.m), {})[p.scheduler] = p
    compared = 0
    for (_n, _m), d in by.items():
        if {"sync", "async"} <= set(d):
            compared += 1
            assert d["async"].hello_tx < d["sync"].hello_tx, \
                "asenkron daha az HELLO göndermiyorsa açıklama yeniden atıftır"
    assert compared >= 3, "karşılaştırılacak eşleşmiş koşum yok"


def test_figure9_refuses_to_draw_without_measurements(tmp_path):
    with pytest.raises(figures.MissingData):
        figures.figure_bootstrap_identity([], str(tmp_path), name="fig9_none")


def test_figure6_names_the_size_versus_volume_tradeoff(tmp_path):
    """WuLi-Dominating'in ASIL bulgusu: en küçük çerçeve en az bayt DEMEK DEĞİL.

    Ölçüldü (bb-validate'in kendi koşumları, derece 6,5-8,4): Bloom'un 64
    baytlık özeti bu derecelerde yerine geçtiği tam listeden BÜYÜK ve düğüm
    başına ~1450 bayt harcıyor, chunked ~510 ile en küçük çerçeveyi taşıyor.
    Yalnız (a) panelini çizen bir şekil Bloom'u kazanan gösterirdi.
    """
    pts = figures.size_points_from_wuli(seeds=(0,))
    res = figures.figure_message_size(pts, str(tmp_path), name="fig6_tradeoff")
    d = res.data
    assert d["heaviest_total"] != d["smallest_frame"], \
        "boyut/hacim ödünleşmesi yoksa bu testin konusu yok"
    assert "toplam hacmi küçültmez" in res.caption
    bloom = [k for k in d["summary"] if "bloom" in k]
    chunk = [k for k in d["summary"] if "chunked" in k]
    assert bloom and chunk, "WuLi-Dominating kodlamaları beklenen adlarla gelmedi"
    assert (min(d["summary"][k]["bytes_per_node_max"] for k in bloom)
            > max(d["summary"][k]["bytes_per_node_max"] for k in chunk)), \
        "bu derecelerde Bloom toplam baytta chunked'ın üstünde olmalı"
    _nonempty(res)


def test_figure6_collapses_the_size_footnote_when_all_series_share_a_range(tmp_path):
    """Altı seriyi tek tek yazmak eksen altını okunmaz bir şeride çeviriyordu."""
    pts = figures.size_points_from_wuli(seeds=(0,))
    spans = {(min(p.n for p in v), max(p.n for p in v)) for v in pts.values()}
    assert len(spans) == 1, "seriler aynı n aralığında değil; test önkoşulu yok"
    res = figures.figure_message_size(pts, str(tmp_path), name="fig6_footnote")
    _nonempty(res)


# ==========================================================================
# 15. Şekil 6: analitik eğri ölçümden AYRI, ve 250 B ulaşılamaz
# ==========================================================================
def test_the_analytic_curve_comes_from_v5_not_from_retyped_arithmetic():
    """İki kopya tutmak, ikisinin sessizce ayrışması demektir."""
    from ccvc.bb import v5_wuli, wire
    curves = figures.analytic_size_curve([2, 8, 32, 64, 118])
    assert set(curves) >= {"full", "bloom", "chunked"}
    for deg, size in curves["full"]:
        assert size == v5_wuli.frame_bytes("full", deg), \
            "analitik eğri v5_wuli ile aynı değeri vermiyor"
    assert dict(curves["full"])[64] == wire.hello_size(65), \
        "boy telin kendi hesabından gelmeli"


def test_figure6_says_the_250_byte_ceiling_cannot_be_measured(tmp_path,
                                                              size_points):
    """Sınır TELDE DEĞİL BELLEKTE, ve şekil bunu söylemeli.

    Tam liste 250 B'ye derece 118'de varır; komşu tablosu 64 girişte dolar ve
    taşma koşumu geçersiz kılar, dolayısıyla rapor edilebilir en yoğun çerçeve
    143 B'dir — tavanın yarısı. 250 B çizgisini ölçülebilir bir hedef gibi
    çizmek, ulaşılmaz bir sınıra yaklaşıyormuşuz izlenimi verirdi.
    """
    res = figures.figure_message_size(size_points, str(tmp_path),
                                      name="fig6_ceiling")
    a = res.data["analytic"]
    assert a["drawn"] is True
    assert a["ceiling_crossing_degree"] == 118
    assert a["table_cap_degree"] == 64 and a["bytes_at_table_cap"] == 143
    assert a["bytes_at_table_cap"] < MAX_PAYLOAD, \
        "tablo sınırındaki çerçeve tavanın altında olmalı; iddia bu"
    assert "ÖLÇÜLEBİLİR DEĞİLDİR" in res.caption
    _nonempty(res)


def test_the_analytic_panel_uses_node_degree_not_average_degree(tmp_path,
                                                                size_points):
    """İki eksen AYNI büyüklük değil; tek panelde birleştirmek ölçüm hatası olur.

    Çerçeve boyu düğümün KENDİ derecesinin fonksiyonudur. Ölçülen noktaların
    x'i ise çizgenin ORTALAMA derecesidir. Analitik eğrinin derece ekseni
    ölçülen panellerinkinden çok daha geniştir ve bu, ikisinin ayrı eksende
    durduğunun gözlenebilir kanıtı.
    """
    res = figures.figure_message_size(size_points, str(tmp_path), name="fig6_ax")
    measured_max = max(v["deg_max"] for v in res.data["summary"].values())
    assert res.data["analytic"]["ceiling_crossing_degree"] > measured_max * 5, \
        "analitik eksen ölçülenle aynı aralıktaysa ayrımı sınamıyoruz"


def test_figure6_can_be_asked_to_omit_the_analytic_curve(tmp_path, size_points):
    res = figures.figure_message_size(size_points, str(tmp_path), analytic=False,
                                      name="fig6_noan")
    assert res.data["analytic"]["drawn"] is False
    assert "ÖLÇÜLEBİLİR DEĞİLDİR" not in res.caption
    _nonempty(res)


def test_figure6_plots_the_quality_axis_when_backbone_is_measured(tmp_path):
    """Bloom yalnız yüke bakınca kazanan görünür; bedelini KALİTEDE öder."""
    pts = figures.size_points_from_wuli(seeds=(0,))
    res = figures.figure_message_size(pts, str(tmp_path), name="fig6_quality")
    assert res.data["has_quality"] is True
    summ = res.data["summary"]
    bloom = [k for k in summ if "bloom" in k]
    other = [k for k in summ if "bloom" not in k]
    assert bloom and other
    assert min(summ[k]["backbone_frac_max"] for k in bloom) == 1.0, \
        "Bloom omurgası bütün düğüm kümesine şişmeli (ölçülmüş davranış)"
    assert max(summ[k]["backbone_frac_max"] for k in other) < 1.0, \
        "karşılaştırma kolu da 1.0 ise kalite ekseni ayırt etmiyor"
    assert "Kalite ekseninde" in res.caption


def test_the_quality_panel_is_skipped_not_faked_when_backbone_is_absent(tmp_path,
                                                                        size_points):
    """Omurga ölçülmediyse panel BOŞ kalır; sıfır çizmek ölçüm uydurmaktır."""
    assert all(p.backbone is None for v in size_points.values() for p in v)
    res = figures.figure_message_size(size_points, str(tmp_path), name="fig6_noq")
    assert res.data["has_quality"] is False
    assert "Kalite ekseninde" not in res.caption
    _nonempty(res)
