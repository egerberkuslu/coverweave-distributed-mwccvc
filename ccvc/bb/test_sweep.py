#!/usr/bin/env python3
"""`ccvc/bb/sweep.py` testleri: koşucunun disiplin kurallarını GERÇEKTEN tuttuğu.

Koşum:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_sweep.py -q

Bu dosyanın sorduğu soru "koşucu koştu mu" değil. Koşucunun dört iddiası var ve
her birinin BOZULMUŞ hâli sınanır, çünkü sınırın tuttuğunu doğrulayan test
sınırın aşıldığında ne olacağını söylemez:

  1. Hayatta kalma yanlılığı: bir kol düşünce oranı `common` altkümede düzelmeli.
     Test, kolu KASTEN düşürüp `own` ile `common` arasında farkın AÇILDIĞINI
     ölçer; eşitliği doğrulamak hiçbir şey kanıtlamazdı.
  2. Eşleşmiş hücre: iki eksende birden ayrılan kol çiftinin listeye GİREMEDİĞİ.
  3. Başarısızlık veridir: `unresolved` satırının slot ve tx'iyle CSV'de
     DURDUĞU, eksik satır olmadığı.
  4. Tohum sayısı: tek tohumlu hücrenin `TEK KOŞUM` diye işaretlendiği.

Ek olarak sözleşme: eksik alan döndüren varyantın SESSİZCE 0 yazmadığı.
"""
from __future__ import annotations

import csv
import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import matrix, sweep  # noqa: E402
from ccvc.bb.sweep import (AnytimeSample, AnytimeTrace, ContractError,  # noqa: E402
                           RunRequest, SweepOptions, VariantSpec)

SMALL = SweepOptions(k=4, max_ms=600_000)


def tiny_cells(n: int = 10, ratio: int = 2):
    return [c for c in matrix.feasible_cells() if c.n == n and c.ratio == ratio]


@pytest.fixture(scope="module")
def instances():
    return [sweep.synthetic_instance(c, s) for c in tiny_cells() for s in range(3)]


@pytest.fixture(scope="module")
def builtin():
    return sweep.builtin_variants()


@pytest.fixture(scope="module")
def rows(instances, builtin):
    return sweep.sweep(instances, builtin, opts=SMALL)


# ==========================================================================
# 1. Sözleşme: eksik alan SESSİZCE doldurulmuyor
# ==========================================================================
class _Incomplete:
    """`cover` var, `tx` yok. Gerçek bir varyantın yarım bırakılmış hâli."""

    cover = [1, 2]
    owner = {(1, 2): 1}
    total_weight = 3.0


def test_a_variant_missing_a_field_raises_instead_of_defaulting():
    with pytest.raises(ContractError) as err:
        sweep.adapt_result(_Incomplete(), variant="V-yarım")
    msg = str(err.value)
    assert "tx" in msg and "V-yarım" in msg, \
        "hata hangi alanın eksik olduğunu söylemeli"


def test_the_missing_field_does_not_become_a_zero_in_the_csv(instances, builtin):
    """Eksik alanı 0 yazmak ölçülmemişi ölçülmüş gibi gösterirdi."""
    broken = VariantSpec("V-yarım", "bb", "mis", "local",
                         lambda req: _Incomplete(), schedulers=("sync",))
    row = sweep.run_one(instances[0], broken, "sync", SMALL)
    assert row.status == "error"
    assert row.tx is None and row.bytes_tx is None and row.slots is None, \
        "ölçülmemiş maliyet 0 değil BOŞ olmalı"
    assert "tx" in row.detail


def test_builtin_result_satisfies_its_own_contract(instances, builtin):
    res = sweep.adapt_result(builtin[0].run(RunRequest(
        edges=instances[0].edges, weights=dict(instances[0].weights), k=4,
        scheduler="sync", seed=0, max_ms=600_000)), variant="MIS-Connector-Backbone")
    for field in sweep.REQUIRED_RESULT_FIELDS:
        assert hasattr(res, field)
    assert res.backbone, "omurga türetilmedi"


# ==========================================================================
# 2. Eşleşmiş hücreler: YAPISAL süzgeç
# ==========================================================================
def test_only_single_axis_differences_form_a_matched_pair(builtin):
    pairs = sweep.matched_pairs(builtin, ("sync", "async"))
    names = {(a, b) for a, b, _ in pairs}
    assert ("MIS-Connector-Backbone/sync", "MIS-Connector-Backbone/async") in names
    assert ("MIS-Connector-Backbone/sync", "MIS-Connector-TreeAgg/sync") in names
    # iki eksen birden değişiyor: zamanlayıcı VE faz 5
    assert ("MIS-Connector-Backbone/sync", "MIS-Connector-TreeAgg/async") not in names
    for a, b, axis in pairs:
        assert axis in sweep.AXES


def test_a_two_axis_difference_is_filtered_out_pairwise(builtin):
    """SINIRIN TUTTUĞUNU DEĞİL, İKİ EKSENLİ ÇİFTİN ELENDİĞİNİ sına.

    Süzgeç KOLU değil ÇİFTİ eler, ve bu ayrım önemli: `mst/tree` kolu
    `mis/local`den iki eksende (Faz 1 VE Faz 5) ayrıldığı için onunla
    kıyaslanamaz, ama `mis/tree` ile yalnız Faz 1'de ayrıldığı için onunla
    kıyaslanabilir. İlk yazdığım iddia "bu kol hiçbir şeyle eşleşemez" idi ve
    YANLIŞTI; test kodu değil beni düzeltti.
    """
    both = VariantSpec("V-mst-tree", "bb", "mst", "tree", lambda r: None)
    pairs = {(a, b): ax for a, b, ax in
             sweep.matched_pairs(list(builtin) + [both], ("sync",))}
    assert ("MIS-Connector-Backbone/sync", "V-mst-tree/sync") not in pairs, \
        "Faz 1 ve Faz 5 birlikte değişmiş; kıyas 'aynı algoritma' olmaz"
    assert pairs.get(("MIS-Connector-TreeAgg/sync", "V-mst-tree/sync")) == "phase1", \
        "yalnız Faz 1'de ayrılan çift kıyaslanabilir olmalı"


def test_a_variant_unique_on_two_axes_pairs_with_nothing(builtin):
    """Hem Faz 1'i hem Faz 5'i eşi olmayan bir kol hiçbir çifte giremez."""
    lone = VariantSpec("V-yalnız", "bb", "anneal", "gossip", lambda r: None)
    pairs = sweep.matched_pairs(list(builtin) + [lone], ("sync",))
    involved = {n for a, b, _ in pairs for n in (a, b)}
    assert "V-yalnız/sync" not in involved


def test_different_families_never_form_a_matched_pair(builtin):
    """Farklı algoritma ailesi 'farklı koşul' değildir."""
    other = VariantSpec("Anneal-Local", "anneal", "anneal", "local", lambda r: None)
    pairs = sweep.matched_pairs(list(builtin) + [other], ("sync", "async"))
    cross = [(a, b) for a, b, _ in pairs if "Anneal" in a or "Anneal" in b]
    assert cross == [("Anneal-Local/sync", "Anneal-Local/async")], \
        "tavlama yalnız kendi zamanlayıcı ekseninde eşleşebilir"


# ==========================================================================
# 3. Hayatta kalma yanlılığı: KOL DÜŞÜRÜLÜNCE FARK AÇILMALI
# ==========================================================================
def _fragile(good: VariantSpec, fail_on_seed: int) -> VariantSpec:
    """Belirli tohumda ÇÖKEN kol: kolay örneklerde sağ kalır, zorunda düşer."""
    def run(req: RunRequest):
        if req.seed == fail_on_seed:
            raise RuntimeError("bu örnekte düştüm")
        return good.run(req)
    return VariantSpec("V-kırılgan", good.family, good.phase1, good.phase5,
                       run, schedulers=("sync",))


def test_survivorship_shrinks_the_common_subset_when_an_arm_fails(instances, builtin):
    good = dataclasses.replace(builtin[0], schedulers=("sync",))
    fragile = _fragile(good, fail_on_seed=instances[0].seed)
    specs = [good, fragile]
    rs = sweep.sweep(instances, specs, schedulers=("sync",), opts=SMALL)
    summ = sweep.summarize(rs, specs=specs, schedulers=("sync",))

    solved = {r.instance_key for r in rs
              if r.arm == "V-kırılgan/sync" and r.status == "ok"}
    everything = {r.instance_key for r in rs}
    assert solved < everything, "kırılgan kol düşmedi, test yanlış kurulmuş"
    assert summ["_common_subset_size"] == len(solved), \
        "ortak altküme, düşen kolun sağ kaldığı örneklere daralmalı"
    assert summ["V-kırılgan/sync"]["status"].get("error"), "düşüş kayda geçmedi"


def test_common_subset_excludes_an_instance_no_arm_shares(instances, builtin):
    """Ortak altküme KESİŞİMDİR: bir kolun tek başına çözdüğü örnek girmez."""
    good = dataclasses.replace(builtin[0], schedulers=("sync",))
    a = _fragile(good, fail_on_seed=instances[0].seed)
    b = dataclasses.replace(_fragile(good, fail_on_seed=instances[1].seed),
                            name="V-kırılgan2")
    rs = sweep.sweep(instances, [a, b], schedulers=("sync",), opts=SMALL)
    summ = sweep.summarize(rs, specs=[a, b], schedulers=("sync",))
    assert summ["_common_subset_size"] <= len(instances) - 2


def test_ratio_own_and_common_are_reported_separately(rows, builtin):
    summ = sweep.summarize(rows, specs=builtin)
    for arm in summ["_arms"]:
        e = summ[arm]
        if "ratio_exact_own_mean" in e:
            assert "ratio_exact_common_mean" in e, \
                "yanlı ve yansız oran birlikte raporlanmalı"


# ==========================================================================
# 4. Başarısızlık veridir
# ==========================================================================
def _always(status_flags) -> VariantSpec:
    """Gerçek koşumu yapan ama bayrağı KASTEN kaldıran kol."""
    base = sweep.builtin_variants()[0]

    def run(req: RunRequest):
        return dataclasses.replace(base.run(req), **status_flags)
    return VariantSpec("V-bayraklı", "bb", "mis", "local", run,
                       schedulers=("sync",))


def test_an_unresolved_run_is_a_row_with_its_slots_and_tx(instances):
    spec = _always({"unresolved": True})
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.status == "unresolved"
    assert row.slots is not None and row.slots > 0, "slot sayısı kaybolmuş"
    assert row.tx is not None and row.tx > 0, "tx kaybolmuş"
    assert row.unresolved is True


def test_failed_rows_are_not_dropped_from_the_csv(tmp_path, instances, builtin):
    spec = _always({"unresolved": True})
    rs = sweep.sweep(instances, [spec], schedulers=("sync",), opts=SMALL)
    path = sweep.write_csv(rs, str(tmp_path / "rows.csv"))
    with open(path, encoding="utf-8") as fh:
        got = list(csv.DictReader(fh))
    assert len(got) == len(instances) == len(rs), "satır düşmüş"
    assert all(r["status"] == "unresolved" for r in got)
    assert all(int(r["tx"]) > 0 for r in got), "başarısız satırın maliyeti boş"


def test_the_status_label_is_lossy_but_the_flags_are_not(instances):
    """Tek etiket iki bayrağı birden anlatamaz; ikisi de sütun olarak durur."""
    spec = _always({"unresolved": True, "converged": False})
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.status == "unresolved"
    assert row.unresolved is True and row.converged is False, \
        "etiket kayıplı olabilir, bayraklar olamaz"


def test_time_budget_writes_skipped_rows_instead_of_dropping_them(instances, builtin):
    opts = dataclasses.replace(SMALL, time_budget_s=-1.0)   # anında dolu
    rs = sweep.sweep(instances, builtin[:1], schedulers=("sync",), opts=opts)
    assert len(rs) == len(instances)
    assert all(r.status == "skipped" for r in rs)
    assert all("bütçe" in r.detail for r in rs)


# ==========================================================================
# 5. Tohum sayısı gizlenmiyor
# ==========================================================================
def test_single_seed_cells_are_labelled_not_averaged(builtin):
    one = [sweep.synthetic_instance(tiny_cells()[0], 0)]
    rs = sweep.sweep(one, builtin[:1], schedulers=("sync",), opts=SMALL)
    cells = sweep.cell_coverage(rs)
    assert len(cells) == 1
    assert cells[0]["seeds_run"] == 1 and cells[0]["single_run"] is True
    assert "TEK KOŞUM" in cells[0]["label"]


def test_failures_on_infeasible_instances_stay_in_the_status_inventory(instances):
    """SINIRIN TUTTUĞUNU DEĞİL, SAYIMIN KAYBOLMADIĞINI sına.

    Oran ortalamaları kanıtlanabilir uygunsuz örnekleri dışlar ve dışlamalıdır.
    Ama aynı süzgeç DURUM ENVANTERİNE de uygulanırsa, o örneklerde harcanan
    gerçek slot ve tx envanterden düşer ve kol hiç başarısız olmamış gibi
    görünür. Gerçek kıyas koşusunda tam olarak bu oldu: 24 `unresolved` satır
    varken tablo `ok=33` yazıyordu.
    """
    spec = _always({"unresolved": True})
    rs = sweep.sweep(instances, [spec], schedulers=("sync",), opts=SMALL)
    for r in rs:                      # örnekleri uygunsuz İLAN et
        r.instance_feasible = "no"
    summ = sweep.summarize(rs, specs=[spec], schedulers=("sync",))
    e = summ["V-bayraklı/sync"]
    assert e["status"] == {}, "uygun altküme boş olmalı"
    assert e["status_all"]["unresolved"] == len(rs), \
        "bütün satırlar envanterden düşmüş"
    assert e["rows_total"] == len(rs)
    md = sweep.summary_markdown(rs, summ, {})
    assert "unresolved" in md, "başarısızlık özette hiç görünmüyor"


def test_summary_markdown_states_the_seed_count_per_cell(tmp_path, rows, builtin):
    summ = sweep.summarize(rows, specs=builtin)
    md = sweep.summary_markdown(rows, summ, {"source": "synthetic"})
    assert "tohum" in md
    assert "3'ten az" in md or "TEK KOŞUM" in md
    assert "Hayatta kalma" in md and "Eşleşmiş" in md
    assert "imkânsız" in md, "matematiksel olarak imkânsız hücreler yazılmalı"


def test_matrix_impossible_cells_are_named_in_the_summary(rows, builtin):
    md = sweep.summary_markdown(rows, sweep.summarize(rows, specs=builtin), {})
    for c in matrix.impossible_cells():
        assert f"n={c.n}, m/n={c.ratio}" in md


# ==========================================================================
# 6. Kaynak dürüstlüğü ve örnek uyarlaması
# ==========================================================================
def test_synthetic_rows_are_labelled_so_they_cannot_pass_as_benchmark(rows):
    assert {r.source for r in rows} == {"synthetic"}
    assert "source" in sweep.CSV_FIELDS


def test_benchmark_mode_refuses_to_fall_back_to_synthetic(monkeypatch, tmp_path):
    monkeypatch.setattr(matrix, "dataset_dir", lambda: None)
    code = sweep.main(["--groups", "small", "--max-n", "10", "--max-seeds", "1",
                       "--out", str(tmp_path)])
    assert code == 2, "veri kümesi yokken kıyas koşusu sessizce sentetiğe düşmemeli"


def test_prepare_relabels_zero_based_ids_and_records_it():
    """Kıyas kümesi 0 tabanlı; `mac_for_id(0)` ön görüntü bulamıyor."""
    w, e, adapt = sweep.prepare({0: 1.0, 1: 2.0, 2: 3.0}, [(0, 1), (1, 2)])
    assert sorted(w) == [1, 2, 3]
    assert e == [(1, 2), (2, 3)]
    assert adapt.relabelled is True


def test_prepare_quantises_weights_and_measures_the_error():
    raw = {1: 76.168, 2: 29.2785, 3: 31.46}
    w, _, adapt = sweep.prepare(raw, [(1, 2), (2, 3)], weight_scale=10)
    assert all(float(v).is_integer() for v in w.values())
    assert adapt.weight_scale == 10
    assert 0 < adapt.weight_rel_error < 0.01, "nicemleme hatası ölçülmeli"


def test_prepare_refuses_a_scale_that_overflows_the_fixed_point_key():
    with pytest.raises(ContractError) as err:
        sweep.prepare({1: 5000.0, 2: 1.0}, [(1, 2)], weight_scale=1000)
    assert "int32" in str(err.value)


def test_relabelling_and_scale_are_columns_not_silent(instances, builtin):
    row = sweep.run_one(instances[0], builtin[0], "sync", SMALL)
    assert "relabelled" in sweep.CSV_FIELDS
    assert "weight_scale" in sweep.CSV_FIELDS
    assert "weight_rel_error" in sweep.CSV_FIELDS
    assert row.weight_scale >= 1


# ==========================================================================
# 7. Anytime iz sözleşmesi (şekil 8 buna dayanıyor)
# ==========================================================================
def _trace(pairs, variant="Anneal-Local"):
    return AnytimeTrace(variant, [
        AnytimeSample(t_ms=t, energy_mah=e, tx=t, observer_best_weight=w,
                      cover_size=None if w is None else 3)
        for t, e, w in pairs])


def test_a_valid_anytime_trace_passes():
    _trace([(0, 0.0, None), (10, 0.5, 30.0), (20, 0.9, 28.0)]).check()


def test_a_trace_whose_best_weight_increases_is_rejected():
    """'O ana kadarki en iyi' büyüyemez; büyüyorsa iz en iyiyi değil ANLIK
    değeri taşıyordur ve eğri olmayan bir garantiyi varmış gibi gösterir."""
    with pytest.raises(ContractError) as err:
        _trace([(0, 0.0, 28.0), (10, 0.5, 30.0)]).check()
    assert "artıyor" in str(err.value)


def test_a_trace_with_decreasing_energy_is_rejected():
    with pytest.raises(ContractError):
        _trace([(0, 1.0, None), (10, 0.5, None)]).check()


def test_an_out_of_order_trace_is_rejected():
    with pytest.raises(ContractError):
        _trace([(10, 0.1, None), (0, 0.2, None)]).check()


def test_an_empty_trace_is_rejected():
    with pytest.raises(ContractError):
        AnytimeTrace("Anneal-Local", []).check()


def test_adapt_result_validates_an_attached_trace(instances, builtin):
    """Bozuk iz koşucunun sınırında patlar, şekle hiç ulaşmaz."""
    base = builtin[0]

    def run(req: RunRequest):
        res = base.run(req)
        res.trace = _trace([(0, 0.0, 28.0), (10, 0.5, 30.0)])
        return res
    spec = VariantSpec("V-bozukiz", "anneal", "anneal", "local", run,
                       schedulers=("sync",))
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.status == "error" and "artıyor" in row.detail


def test_t_first_valid_is_the_first_valid_sample():
    t = _trace([(0, 0.0, None), (5, 0.2, None), (9, 0.4, 30.0), (12, 0.6, 29.0)])
    assert t.t_first_valid_ms == 9
    assert _trace([(0, 0.0, None)]).t_first_valid_ms is None


# ==========================================================================
# 8. Keşif
# ==========================================================================
def test_discovery_survives_variants_that_do_not_exist_yet():
    specs = sweep.discover()
    assert {s.name for s in specs} >= {"MIS-Connector-Backbone", "MIS-Connector-TreeAgg"}


def test_strict_discovery_reports_the_missing_module():
    with pytest.raises(ContractError):
        sweep.discover(strict=True)


def test_duplicate_variant_names_are_refused(builtin):
    dupe = dataclasses.replace(builtin[0])
    with pytest.raises(ContractError) as err:
        sweep.discover(extra=[dupe])
    assert "çakışma" in str(err.value)


def test_plan_counts_runs_without_running_them(instances, builtin):
    entries = sweep.plan(instances, builtin, schedulers=("sync", "async"))
    assert len(entries) == len(instances) * len(builtin) * 2


# ==========================================================================
# 9. Uçtan uca
# ==========================================================================
def test_end_to_end_writes_csv_json_and_markdown(tmp_path, rows, builtin):
    summ = sweep.summarize(rows, specs=builtin)
    paths = sweep.write_outputs(rows, summ, {"source": "synthetic"},
                                str(tmp_path / "out"))
    for key in ("csv", "json", "md"):
        assert os.path.getsize(paths[key]) > 200, key
    with open(paths["csv"], encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == list(sweep.CSV_FIELDS), "CSV şeması sabit olmalı"


def test_every_row_carries_the_cost_columns(rows):
    for r in rows:
        if r.status in ("ok", "unresolved", "not_converged", "gate_fail"):
            assert r.tx is not None and r.bytes_tx is not None, r
            assert r.lower_bound_g6 > 0


# ==========================================================================
# 10. Girdi bağlılığı: brief §1'in ÖNCÜLÜ, satır kaydından önce
# ==========================================================================
def _disconnected(cell, seed=0):
    """İki ayrı üçgen: bağlı DEĞİL, ama her bileşen kendi içinde çözülebilir."""
    return sweep.Instance(
        "synthetic", cell, seed, f"synthetic:kopuk_s{seed}",
        ((1, 2), (2, 3), (1, 3), (4, 5), (5, 6), (4, 6)),
        {i: 1.0 for i in range(1, 7)}, 0, sweep.Adaptation(False, 1, 0.0))


def test_a_disconnected_input_is_refused_not_measured(builtin):
    """SINIRIN TUTTUĞUNU DEĞİL, KOPUK ÇİZGENİN ELENDİĞİNİ sına.

    Ekip liderinin docs/message_complexity.md'yi baştan yazmasına yol açan
    hata tam olarak buydu: ölçüm koşumu kopuk çizge üretiyordu, doğrulayıcı
    görüyordu, koşucu görmüyordu ve bütün sayılar temiz duruyordu.
    """
    cell = tiny_cells()[0]
    row = sweep.run_one(_disconnected(cell), builtin[0], "sync", SMALL)
    assert row.status == "bad_input"
    assert row.graph_connected is False
    assert row.tx is None and row.slots is None, \
        "kopuk çizgede ölçüm YAPILMAMALI, satır boş maliyetle durmalı"
    assert "kopuk" in row.detail


def test_connected_inputs_are_marked_connected(instances, builtin):
    row = sweep.run_one(instances[0], builtin[0], "sync", SMALL)
    assert row.graph_connected is True and row.status != "bad_input"


def test_disconnected_rows_never_enter_the_cost_averages(instances, builtin):
    """Kopuk satır ortalamaya girerse iki farklı popülasyon karışır."""
    cell = tiny_cells()[0]
    mixed = list(instances) + [_disconnected(cell, seed=99)]
    rs = sweep.sweep(mixed, builtin[:1], schedulers=("sync",), opts=SMALL)
    bad = [r for r in rs if r.status == "bad_input"]
    assert len(bad) == 1
    summ = sweep.summarize(rs, specs=builtin[:1], schedulers=("sync",))
    e = summ["MIS-Connector-Backbone/sync"]
    assert e["status_all"].get("bad_input") == 1, "envanterde görünmeli"
    assert e["valid"] == len(instances), "kopuk örnek geçerli sayılmış"


def test_the_summary_shouts_about_disconnected_input(instances, builtin):
    cell = tiny_cells()[0]
    rs = sweep.sweep(list(instances) + [_disconnected(cell, 99)], builtin[:1],
                     schedulers=("sync",), opts=SMALL)
    md = sweep.summary_markdown(rs, sweep.summarize(rs, specs=builtin[:1],
                                                    schedulers=("sync",)), {})
    assert "KOPUK GİRDİ" in md and "girdi kusurudur" in md


def test_a_clean_sweep_states_that_every_input_was_connected(rows, builtin):
    md = sweep.summary_markdown(rows, sweep.summarize(rows, specs=builtin), {})
    assert "Girdi bağlılığı" in md and "bağlı" in md


def test_per_component_mode_is_an_explicit_opt_in(builtin):
    """Bileşen bazlı ölçüm yapılabilir ama İSTENMEK zorunda."""
    cell = tiny_cells()[0]
    opts = dataclasses.replace(SMALL, require_connected=False,
                               connectivity="per_component")
    row = sweep.run_one(_disconnected(cell), builtin[0], "sync", opts)
    assert row.status != "bad_input"
    assert row.graph_connected is False, "kopukluk yine de KAYDEDİLİR"
    assert row.tx is not None


def test_is_connected_agrees_with_the_validator(builtin):
    """Kapının kendi bağlılık kararı doğrulayıcıyla çelişmemeli."""
    from ccvc.bb import validate as V
    cell = tiny_cells()[0]
    bad = _disconnected(cell)
    assert sweep.is_connected(sorted(bad.weights), bad.edges) is False
    g = V.make_graph(list(bad.edges), 4, dict(bad.weights))
    rep = V.validate(g, sorted(bad.weights), None, connectivity=V.STRICT)
    assert any(v.kind == V.GRAPH_DISCONNECTED for v in rep.violations)
    ok = sweep.synthetic_instance(cell, 0)
    assert sweep.is_connected(sorted(ok.weights), ok.edges) is True


# ==========================================================================
# 11. Maliyet parametreleri KAYDEDİLİYOR
# ==========================================================================
def test_the_cost_parameters_actually_used_are_recorded(instances, builtin):
    """`push_ttl_max` tek başına maliyeti ~3 kat değiştiriyor (ekip lideri ölçtü).

    Test DEĞERİ çivilemez, KAYDEDİLDİĞİNİ çiviler: 3 mü 8 mi olduğu bb-algo'nun
    ayar kararı, ama CSV hangi değerle ölçüldüğünü taşımazsa iki süpürmenin
    maliyet sütunları sessizce kıyaslanamaz hale gelir.
    """
    from ccvc.bb.bbcvc import BbcvcParams
    row = sweep.run_one(instances[0], builtin[0], "sync", SMALL)
    assert row.push_ttl_max == BbcvcParams().push_ttl_max, \
        "kaydedilen değer kütüphanenin gerçekten kullandığıyla aynı olmalı"
    assert row.push_ttl_max > 0
    assert "push_ttl_max" in sweep.CSV_FIELDS


def test_the_recorded_mis_cap_is_the_one_used_not_the_one_asked_for(instances):
    """Varyant isteği yok sayarsa CSV İSTEĞİ değil GERÇEĞİ yazmalı."""
    from ccvc.bb.bbcvc import BbcvcParams, run_bbcvc

    def run(req: RunRequest):
        return run_bbcvc(list(req.edges), dict(req.weights), req.k,
                         scheduler=req.scheduler, max_ms=req.max_ms,
                         seed=req.seed, params=BbcvcParams(mis_nbrs_max=9))
    spec = VariantSpec("V-inatçı", "bb", "mis", "local", run, schedulers=("sync",))
    row = sweep.run_one(instances[0], spec, "sync",
                        dataclasses.replace(SMALL, mis_nbrs_max=32))
    assert row.mis_nbrs_max == 9, "istenen 32 yazılmış, kullanılan 9 kaybolmuş"


# ==========================================================================
# 12. Varyant bildirimi: KİMLİK değil YAPI denetlenir
# ==========================================================================
def test_a_spec_from_a_second_import_of_this_module_is_accepted(builtin):
    """`python -m ccvc.bb.sweep` modülü `__main__` adıyla İKİNCİ kez yükler.

    O zaman `__main__.VariantSpec` ile `ccvc.bb.sweep.VariantSpec` farklı sınıf
    nesneleridir ve `isinstance` tamamen doğru bir bildirimi reddeder. Gerçekte
    oldu: bb-validate'in v5_wuli modülü yüklendiğinde koşucu

        BB_VARIANTS içinde VariantSpec değil: <class 'ccvc.bb.sweep.VariantSpec'>

    diyerek çöktü; hata metni kendi kendiyle çelişiyordu. Burada ikinci yükleme
    TAKLİT EDİLMEZ, gerçekten yapılır.
    """
    import importlib.util
    name = "sweep_ikinci_kopya"
    spec = importlib.util.spec_from_file_location(name, sweep.__file__)
    twin = importlib.util.module_from_spec(spec)
    sys.modules[name] = twin          # dataclass kurucusu modülü arıyor
    try:
        spec.loader.exec_module(twin)
    finally:
        pass
    assert twin.VariantSpec is not sweep.VariantSpec, \
        "ikinci yükleme olmadı; test bir şey kanıtlamıyor"
    foreign = twin.VariantSpec("V-yabancı", "bb", "mis", "local",
                               lambda r: None, schedulers=("sync",))
    sweep._check_spec(foreign, "ikinci_kopya")          # patlamamalı
    got = sweep.discover(extra=[foreign])
    assert "V-yabancı" in {s.name for s in got}
    sys.modules.pop(name, None)


def test_a_genuinely_wrong_declaration_is_still_refused():
    """Yapısal denetim gevşeme DEĞİL: alanı eksik olan hâlâ reddedilir."""
    with pytest.raises(ContractError) as err:
        sweep._check_spec(("V", "bb", "mis"), "uydurma")
    assert "phase1" in str(err.value) or "eksik" in str(err.value)

    class _NoRun:
        name, family, phase1, phase5, schedulers = "V", "bb", "mis", "local", ()
        run = "çağrılabilir değil"
    with pytest.raises(ContractError):
        sweep._check_spec(_NoRun(), "uydurma")

    class _BadAxis:
        name, family, phase5, schedulers = "V", "bb", "local", ()
        phase1 = 3                      # metin olmalı; eksen kıyası buna bakıyor
        run = staticmethod(lambda r: None)
    with pytest.raises(ContractError) as err2:
        sweep._check_spec(_BadAxis(), "uydurma")
    assert "eksen" in str(err2.value)


# ==========================================================================
# 13. İz ile çözümün ÇAPRAZ tutarlılığı
# ==========================================================================
def _with_trace(samples, cover_override=None):
    base = sweep.builtin_variants()[0]

    def run(req: RunRequest):
        res = base.run(req)
        made = samples(res)
        if cover_override is not None:
            # ÖNCE replace, SONRA iz: `trace` BbcvcRun'ın alanı değil, dinamik
            # bir nitelik, dolayısıyla `dataclasses.replace` onu taşımaz.
            res = dataclasses.replace(res, cover=cover_override, owner={},
                                      total_weight=0.0)
        res.trace = AnytimeTrace("V-izli", made)
        return res
    return VariantSpec("V-izli", "anneal", "anneal", "local", run,
                       schedulers=("sync",))


def test_a_trace_that_contradicts_an_empty_cover_is_recorded(instances):
    """ÖLÇÜLDÜ: Anneal-Local'ın izi |C|=10 derken koşum boş örtü döndürüyordu.

    İki görünüm çeliştiğinde biri yanlıştır ve tek başına hiçbir çıktıdan
    görünmez: şekil 8 ize bakar ve sağlıklı görünür, CSV çözüme bakar ve
    algoritma hiçbir şey örtmemiş gibi okunur.
    """
    spec = _with_trace(
        lambda res: [AnytimeSample(0, 0.0, 0, None, None),
                     AnytimeSample(10, 1.0, res.tx, 42.0, 7)],
        cover_override=[])
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.trace_agrees.startswith("no:")
    assert "BOŞ" in row.trace_agrees
    assert row.tx is not None and row.tx > 0, \
        "tutarsızlık satırı DÜŞÜRMEMELİ; slot ve tx gerçek ölçüm"


def test_a_trace_that_matches_the_solution_is_marked_agreeing(instances):
    spec = _with_trace(lambda res: [
        AnytimeSample(0, 0.0, 0, None, None),
        AnytimeSample(10, 1.0, res.tx, res.total_weight, len(res.cover))])
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.trace_agrees == "yes"


def test_a_cover_size_mismatch_alone_is_NOT_flagged(instances):
    """BU TEST TERSİNE ÇEVRİLDİ ve gerekçesi kayda değer.

    Önce boy uyuşmazlığını çelişki sayıyordum ve bu test onu sabitliyordu.
    bb-core ölçtü ki yanlış büyüklüğü kıyaslıyorum: zarf AĞIRLIĞI enküçültür,
    ağırlık ile boy birlikte artmaz, dolayısıyla boy farkı sözleşmeye tamamen
    uygun. Testi silmek yerine iddiayı tersine çevirmek, bir kez yanlış
    yakaladığımız şeyin bir daha sessizce geri gelmemesini sağlıyor.
    """
    spec = _with_trace(lambda res: [
        AnytimeSample(10, 1.0, res.tx, res.total_weight, len(res.cover) + 3)])
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.trace_agrees == "yes", \
        "boy farkı yeniden çelişki sayılmaya başlanmış"


def test_runs_without_a_trace_are_not_accused(instances, builtin):
    row = sweep.run_one(instances[0], builtin[0], "sync", SMALL)
    assert row.trace_agrees == "none"


def test_the_summary_shouts_about_a_contradicting_trace(instances):
    spec = _with_trace(
        lambda res: [AnytimeSample(10, 1.0, res.tx, 42.0, 7)], cover_override=[])
    rs = sweep.sweep(instances, [spec], schedulers=("sync",), opts=SMALL)
    summ = sweep.summarize(rs, specs=[spec], schedulers=("sync",))
    assert summ["V-izli/sync"]["trace_disagrees"] == len(rs)
    md = sweep.summary_markdown(rs, summ, {})
    assert "anytime izi çözümle ÇELİŞİYOR" in md


# ==========================================================================
# 14. Kolun beyanı ile doğrulayıcının kararı: YANLIŞ BAŞARI yakalanmalı
# ==========================================================================
def _lying(cover, owner) -> VariantSpec:
    """GERÇEK koşum, sonra çözümü BOZ ve hiçbir bayrak kaldırma.

    Ekip liderinin elle yakaladığı durumun taklidi: K6/k=2'de kol
    `unresolved=False, infeasible=False` ile başarı bildirirken düğüm 1
    k=2 iken 5 kenar sahipleniyordu. Elle yakalanan bir şeyin bir dahaki sefere
    de yakalanacağının garantisi yok; bu yüzden tuzak kurulur.
    """
    base = sweep.builtin_variants()[0]

    def run(req: RunRequest):
        res = base.run(req)
        return dataclasses.replace(res, cover=cover, owner=owner,
                                   infeasible=False, unresolved=False,
                                   converged=True)
    return VariantSpec("V-yalancı", "bb", "mis", "local", run,
                       schedulers=("sync",))


def test_an_arm_claiming_success_on_an_invalid_solution_is_a_contradiction(instances):
    """Yanlış başarı SESSİZCE geçerli bir satır olamaz."""
    inst = instances[0]
    one = sorted(inst.weights)[0]
    # bütün kenarları TEK düğüme yükle: k ne olursa olsun taşkın
    spec = _lying([one], {e: one for e in inst.edges if one in e})
    row = sweep.run_one(inst, spec, "sync", SMALL)
    assert row.status == "contradiction", \
        f"yanlış başarı '{row.status}' diye kaydedilmiş"
    assert row.valid is False
    assert row.verdict_agrees.startswith("no:")
    assert "başarı bildirdi" in row.verdict_agrees


def test_the_false_success_never_counts_as_valid_in_the_summary(instances):
    inst = instances[0]
    one = sorted(inst.weights)[0]
    spec = _lying([one], {e: one for e in inst.edges if one in e})
    rs = sweep.sweep([inst], [spec], schedulers=("sync",), opts=SMALL)
    summ = sweep.summarize(rs, specs=[spec], schedulers=("sync",))
    e = summ["V-yalancı/sync"]
    assert e["valid"] == 0, "yanlış başarı geçerli sayılmış"
    assert e["false_success"] == 1
    assert e["verdict_disagrees"] == 1
    md = sweep.summary_markdown(rs, summ, {})
    assert "YANLIŞ BAŞARI" in md


def test_status_is_derived_from_the_validator_not_from_the_flags(instances):
    """Bayraklar temizken doğrulayıcı ihlal bulduysa satır `ok` OLAMAZ.

    Bu, koşucunun tek bir tasarım kararına dayanıyor: her satır için
    doğrulayıcı KOŞULUR ve `status` onun kararından türetilir. Bayraklardan
    türeseydi, yanlış beyan eden bir kol ortalamalara geçerli sonuç olarak
    girerdi ve hiçbir sütunda başarısızlık gibi görünmezdi.
    """
    inst = instances[0]
    one = sorted(inst.weights)[0]
    spec = _lying([one], {e: one for e in inst.edges if one in e})
    row = sweep.run_one(inst, spec, "sync", SMALL)
    assert (row.infeasible, row.unresolved, row.converged) == (False, False, True), \
        "kol gerçekten başarı iddia etmiş olmalı, yoksa test bir şey kanıtlamaz"
    assert row.status != "ok"


def test_the_opposite_direction_is_also_recorded(instances, builtin):
    """Kol 'çözemedim' derken doğrulayıcı temizse, o da bir tespit kusurudur."""
    base = builtin[0]

    def run(req: RunRequest):
        # Hem bayrağı hem hükmü koyar: gerçek bir kol ikisini tutarlı bildirir,
        # tutarsızlık ayrı bir çelişki biçimi olarak sınanıyor (aşağıda).
        return dataclasses.replace(base.run(req), unresolved=True,
                                   verdict="unresolved")
    spec = VariantSpec("V-karamsar", "bb", "mis", "local", run,
                       schedulers=("sync",))
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.valid is True and row.status == "unresolved"
    assert row.verdict_agrees.startswith("no:")
    assert "doğrulayıcı temiz" in row.verdict_agrees


def test_a_verdict_that_contradicts_its_own_flags_is_caught(instances, builtin):
    """`verdict` ile bayraklar birbiriyle de çelişebilir; o da sessiz kalmamalı."""
    base = builtin[0]

    def run(req: RunRequest):
        return dataclasses.replace(base.run(req), unresolved=True,
                                   verdict="solved")
    spec = VariantSpec("V-tutarsız", "bb", "mis", "local", run,
                       schedulers=("sync",))
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.verdict_agrees.startswith("no:")
    assert "verdict='solved'" in row.verdict_agrees


def test_an_honest_failure_is_not_flagged_as_disagreement(instances, builtin):
    """Dürüstçe bildirilen başarısızlık ÇELİŞKİ DEĞİLDİR; gürültü yapmamalı."""
    E = [(u, v) for u in range(1, 7) for v in range(u + 1, 7)]
    W = {i: 1.0 for i in range(1, 7)}
    k6 = sweep.Instance("synthetic", matrix.Cell("small", 6, 5), 0, "K6",
                        tuple(E), W, 0, sweep.Adaptation(False, 1, 0.0))
    opts = dataclasses.replace(SMALL, k=2)
    row = sweep.run_one(k6, builtin[0], "sync", opts,
                        feasible=sweep.instance_feasibility(k6, opts))
    assert row.instance_feasible == "no", "K6/k=2 kanıtlanabilir uygunsuz olmalı"
    if row.unresolved or row.infeasible:
        assert row.verdict_agrees == "yes", \
            "dürüst başarısızlık bildirimi çelişki sayılmamalı"


def test_a_clean_run_agrees(instances, builtin):
    row = sweep.run_one(instances[0], builtin[0], "sync", SMALL)
    assert row.status == "ok" and row.verdict_agrees == "yes"


# ==========================================================================
# 15. Kesilmiş koşum: BAYRAKLARIN YOKLUĞU başarı demek değil
# ==========================================================================
def test_a_truncated_run_is_never_ok_even_when_its_cover_is_valid(instances,
                                                                  builtin):
    """SINIRIN TUTTUĞUNU DEĞİL, TEHLİKELİ HALİN YAKALANDIĞINI sına.

    Kesilmiş koşum iki türlü biter. Geçersiz bir atamayla kesilirse doğrulayıcı
    zaten yakalar. TEHLİKELİ olan ikincisi: GEÇERLİ bir örtüyle kesilmek. O
    satır dürüstçe `ok` görünür, çünkü geçerli örtü gerçekten geçerlidir; ama
    aynı kol daha uzun bütçeyle daha iyisini bulurdu ve bütçe kollara ortak
    olduğundan önce ZOR olanı bağlar, yani tam da kıyaslanan kolları.
    """
    inst = instances[0]
    found = None
    for ms in (3000, 3500, 4000, 4500, 5000, 6000):
        row = sweep.run_one(inst, builtin[0], "sync",
                            dataclasses.replace(SMALL, max_ms=ms))
        if row.truncated and row.valid:
            found = row
            break
    assert found is not None, "geçerli-ama-kesik satır üretilemedi; test boş"
    assert found.status == "truncated", \
        f"geçerli örtüsü olan kesik koşum '{found.status}' diye kaydedilmiş"
    assert found.verdict == "truncated"
    assert found.verdict_agrees == "yes", \
        "kesinti tespit kusuru değildir; çelişki sütununu kirletmemeli"


def test_a_completed_run_is_not_marked_truncated(instances, builtin):
    row = sweep.run_one(instances[0], builtin[0], "sync", SMALL)
    assert row.status == "ok" and row.verdict == "solved"
    assert row.truncated is False


def test_the_verdict_is_derived_when_a_variant_does_not_report_one(
        instances, builtin):
    """Eski varyantlar `verdict` bildirmiyor; türetme onları kırmamalı."""
    base = builtin[0]

    class _NoVerdict:
        pass

    def run(req: RunRequest):
        res = base.run(req)
        plain = _NoVerdict()
        for f in sweep.REQUIRED_RESULT_FIELDS:
            setattr(plain, f, getattr(res, f))
        plain.converged = False        # duvar bütçesi bağlamış gibi
        return plain
    spec = VariantSpec("V-eski", "bb", "mis", "local", run, schedulers=("sync",))
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.verdict == "truncated", "converged=False'tan türetilmeliydi"
    assert row.status == "truncated"


def test_an_unknown_verdict_is_refused(instances, builtin):
    base = builtin[0]

    def run(req: RunRequest):
        return dataclasses.replace(base.run(req), verdict="harika")
    spec = VariantSpec("V-uydurma", "bb", "mis", "local", run,
                       schedulers=("sync",))
    row = sweep.run_one(instances[0], spec, "sync", SMALL)
    assert row.status == "error" and "verdict" in row.detail


def test_verdict_and_infeasible_answer_different_questions(instances, builtin):
    """`verdict` KOŞUM, `infeasible` ÖRNEK hakkında; ikisi birden doğru olabilir."""
    E = [(u, v) for u in range(1, 7) for v in range(u + 1, 7)]
    W = {i: 1.0 for i in range(1, 7)}
    k6 = sweep.Instance("synthetic", matrix.Cell("small", 6, 5), 0, "K6",
                        tuple(E), W, 0, sweep.Adaptation(False, 1, 0.0))
    opts = dataclasses.replace(SMALL, k=2, max_ms=2_000)
    row = sweep.run_one(k6, builtin[0], "sync", opts,
                        feasible=sweep.instance_feasibility(k6, opts))
    assert row.instance_feasible == "no", "örnek kanıtlanabilir uygunsuz"
    assert row.verdict == "truncated", "koşum kesilmiş"
    assert "verdict" in sweep.CSV_FIELDS and "instance_feasible" in sweep.CSV_FIELDS


def test_infeasible_reason_distinguishes_proof_from_ignorance(instances, builtin):
    """`missed_infeasible`ın 'kanıtladık' ile 'ayırt edemedik'i ayırması için."""
    assert "infeasible_reason" in sweep.CSV_FIELDS
    edges = [(u, v) for u in range(1, 5) for v in range(u + 1, 5)]
    weights = {i: 1.0 for i in range(1, 5)}
    k4 = sweep.Instance("synthetic", matrix.Cell("small", 4, 3), 0, "K4",
                        tuple(edges), weights, 0, sweep.Adaptation(False, 1, 0.0))
    opts = dataclasses.replace(SMALL, k=1)
    row = sweep.run_one(k4, builtin[0], "sync", opts,
                        feasible=sweep.instance_feasibility(k4, opts))
    if row.infeasible:
        assert row.infeasible_reason in ("counting_bound", "node"), \
            "uygunsuzluk ilan edildiyse gerekçesi kayda geçmeli"


# ==========================================================================
# 16. Çapraz denetim AĞIRLIĞI kıyaslar, ÖRTÜ BOYUNU değil
# ==========================================================================
def _res_with_trace(total_weight, cover, samples, **kw):
    return sweep.VariantResult(
        cover=list(cover), owner={}, total_weight=float(total_weight), tx=1,
        rx=1, retx=0, bytes_tx=1, max_payload=1, slots=1, t_conv_ms=1,
        converged=True, infeasible=False, unresolved=False, by_phase_tx={},
        by_type_tx={}, trace=AnytimeTrace("Anneal-Local", samples), **kw)


def test_a_cover_size_difference_alone_is_not_a_contradiction():
    """ÖLÇÜLEN karşı örnek (bb-core): ağırlık ile boy birlikte artmaz.

    n=10 m=20 tohum 4 async: zarf |C|=6 ve Σw=2821, son durum |C|=7 ve
    Σw=4045 — daha AZ düğüm VE daha az ağırlık. İlk yazdığım kıyas boya
    bakıyordu ve bunu çelişki sayıyordu; sözleşmenin söz verdiği ağırlık
    sıralaması ise tam olarak tutuyor.
    """
    res = _res_with_trace(4045.0, list(range(7)), [
        AnytimeSample(0, 0.0, 0, None, None),
        AnytimeSample(10, 1.0, 5, 2821.0, 6)])
    assert sweep._trace_agreement(res) == "yes", \
        "boy farkı hâlâ çelişki sayılıyor"


def test_the_weight_ordering_is_still_enforced():
    """Gevşeme değil: zarf son durumdan KÖTÜ ise ihlal olarak kalır."""
    res = _res_with_trace(20.0, [1, 2, 3], [
        AnytimeSample(10, 1.0, 5, 30.0, 3)])
    verdict = sweep._trace_agreement(res)
    assert verdict.startswith("no:") and "kaçırmış" in verdict


def test_an_empty_cover_against_a_valid_trace_is_still_caught():
    """Asıl yakalanması gereken durum boy kıyası kalkınca kaybolmamalı."""
    res = _res_with_trace(0.0, [], [AnytimeSample(10, 1.0, 5, 5328.0, 10)])
    verdict = sweep._trace_agreement(res)
    assert verdict.startswith("no:") and "BOŞ örtü" in verdict


def test_an_infeasible_instance_is_not_counted_as_a_disagreement():
    """Çözümü olmayan örnekte iz ile koşum ÇELİŞMİYOR, ikisi de doğru.

    Rutin olarak beklenen uyuşmazlık bildiren bir çapraz denetim göz atılıp
    geçilir ve gerçek olan da içinde saklanır; bu yüzden ayrı değer alır.
    """
    res = _res_with_trace(100.0, [1, 2, 3], [AnytimeSample(0, 0.0, 0, None, None)])
    assert sweep._trace_agreement(res, feasible="no").startswith("n/a:")
    assert not sweep._trace_agreement(res, feasible="no").startswith("no:")
    # uygun örnekte AYNI iz uyuşmazlık sayılır
    assert sweep._trace_agreement(res, feasible="yes").startswith("no:")


def test_infeasible_rows_do_not_inflate_the_disagreement_count(instances):
    spec = sweep.builtin_variants()[0]
    rs = sweep.sweep(instances, [spec], schedulers=("sync",), opts=SMALL)
    for r in rs:
        assert not r.trace_agrees.startswith("no:")
    summ = sweep.summarize(rs, specs=[spec], schedulers=("sync",))
    assert summ[f"{spec.name}/sync"]["trace_disagrees"] == 0


# ==========================================================================
# 17. Uygunsuzluk: UCUZCA KANITLANABİLİR olan ile olmayan
# ==========================================================================
def test_the_counting_bound_column_separates_provable_from_flow_only(builtin):
    """m > n·k dejenere sınıfı yakalar; gerisi yalnız akışla görülür.

    Ayrım kusur atfı için belirleyici: bugünkü HELLO ile sağlam bir YEREL
    tanık hesaplanamıyor, dolayısıyla akış-görünür bir uygunsuzluğu düğümün
    bildirememesi BEKLENEN davranıştır, kusur değil.
    """
    E = [(u, v) for u in range(1, 7) for v in range(u + 1, 7)]   # K6, m=15
    W = {i: 1.0 for i in range(1, 7)}
    k6 = sweep.Instance("synthetic", matrix.Cell("small", 6, 5), 0, "K6",
                        tuple(E), W, 0, sweep.Adaptation(False, 1, 0.0))
    o2 = dataclasses.replace(SMALL, k=2)                 # 15 > 6*2=12 -> kanıtlı
    r2 = sweep.run_one(k6, builtin[0], "sync", o2,
                       feasible=sweep.instance_feasibility(k6, o2))
    assert r2.counting_bound_infeasible is True
    assert r2.instance_feasible == "no"

    o3 = dataclasses.replace(SMALL, k=3)                 # 15 <= 18 -> sayma sınırı susar
    r3 = sweep.run_one(k6, builtin[0], "sync", o3,
                       feasible=sweep.instance_feasibility(k6, o3))
    assert r3.counting_bound_infeasible is False, \
        "sayma sınırı burada kanıtlamamalı; ayrım yoksa sütun bir şey söylemiyor"


def test_the_summary_separates_the_two_kinds_of_missed_infeasibility(builtin):
    E = [(u, v) for u in range(1, 7) for v in range(u + 1, 7)]
    W = {i: 1.0 for i in range(1, 7)}
    k6 = sweep.Instance("synthetic", matrix.Cell("small", 6, 5), 0, "K6",
                        tuple(E), W, 0, sweep.Adaptation(False, 1, 0.0))
    opts = dataclasses.replace(SMALL, k=2)
    rs = sweep.sweep([k6], builtin[:1], schedulers=("sync",), opts=opts)
    summ = sweep.summarize(rs, specs=builtin[:1], schedulers=("sync",))
    e = summ["MIS-Connector-Backbone/sync"]
    assert "missed_provable_infeasible" in e
    assert "infeasible_not_cheaply_provable" in e
    assert e["missed_provable_infeasible"] <= e["missed_infeasible"]
    md = sweep.summary_markdown(rs, summ, {})
    assert "missed_provable_infeasible" in md and "YEREL tanık" in md


# ==========================================================================
# 18. Sıralama YÜK TAŞIYOR: geçerlilik-önce kesintiyi göremez
# ==========================================================================
def test_validity_first_ordering_would_miss_a_truncated_but_clean_run(
        instances, builtin):
    """`verdict` KOŞUM, doğrulayıcı CEVAP hakkında; ikisi de gerekli.

    İki yönde de karşı örnek ölçüldü:
      * verdict='solved' + doğrulayıcı kirli  -> bb-core'un boş örtüsü;
        verdict bunu göremez.
      * verdict='truncated' + doğrulayıcı TEMİZ -> kesilmiş ama tutarlı örtü;
        geçerlilik bunu göremez.
    Kesinti denetiminin geçerlilikten ÖNCE gelmesi bu yüzden rastlantı değil
    yük taşıyan bir sıralama; test tam olarak o satırı üretip sınar.
    """
    found = None
    for ms in (3000, 3500, 4000, 4500, 5000, 6000, 8000):
        row = sweep.run_one(instances[0], builtin[0], "sync",
                            dataclasses.replace(SMALL, max_ms=ms))
        if row.truncated and row.valid and row.violations == 0:
            found = row
            break
    assert found is not None, "kesik-ama-temiz satır üretilemedi; test boş"
    assert found.valid is True and found.violations == 0, \
        "doğrulayıcı bu satırda hiçbir şey görmüyor"
    assert found.status == "truncated", \
        ("geçerlilik önce denetlenseydi bu satır 'ok' olurdu; "
         f"şu an '{found.status}'")


def test_the_scorecard_is_printed_even_when_every_check_is_clean(rows, builtin):
    """SIFIR DA BİR ÖLÇÜMDÜR: temiz koşumda da karne yazılmalı.

    Yalnız sorun varken beliren bir bölüm, "denetim koştu ve bir şey bulmadı"
    ile "denetim hiç koşmadı"yı ayırt edilemez kılar. Bu, gün boyunca
    kovaladığımız boş-test sınıfının rapor tarafındaki hâli.
    """
    summ = sweep.summarize(rows, specs=builtin)
    md = sweep.summary_markdown(rows, summ, {})
    assert all(r.status != "contradiction" for r in rows), "koşum temiz olmalı"
    assert "Çapraz denetim karnesi" in md
    assert "yanlış başarı (`contradiction`) | **0**" in md
    assert "iz-çözüm uyuşmazlığı | **0**" in md
    # Karne, ayrıntı bölümlerinden ÖNCE gelmeli: "sade biçimde belirtilsin"
    # demek, okuyucunun aramak zorunda kalmaması demek.
    assert md.index("Çapraz denetim karnesi") < md.index("Matris kapsamı")


def test_the_scorecard_reports_a_real_failure_too(instances):
    """Karne yalnız sıfır basmıyor; gerçek sayıyı da taşıyor."""
    inst = instances[0]
    one = sorted(inst.weights)[0]
    spec = _lying([one], {e: one for e in inst.edges if one in e})
    rs = sweep.sweep([inst], [spec], schedulers=("sync",), opts=SMALL)
    md = sweep.summary_markdown(
        rs, sweep.summarize(rs, specs=[spec], schedulers=("sync",)), {})
    assert "yanlış başarı (`contradiction`) | **1**" in md


# ==========================================================================
# 19. Kod sürümü: uzun süpürme sırasında inen yama GÖRÜNÜR olmalı
# ==========================================================================
def test_every_row_records_the_code_version_it_was_measured_against(instances,
                                                                    builtin):
    row = sweep.run_one(instances[0], builtin[0], "sync", SMALL)
    assert row.code_fingerprint and len(row.code_fingerprint) == 12
    assert "code_fingerprint" in sweep.CSV_FIELDS


def test_a_csv_spanning_two_code_versions_is_called_out(rows, builtin):
    """ÖLÇÜLDÜ: süpürme 20 dakika sürüyor ve depo canlı.

    Bugün süpürme sürerken bb-algo'nun `unresolved` temizleme yaması indi.
    Biten CSV üç uyuşmazlık gösteriyordu; aynı örnek tek başına koşturulunca
    temizdi. Yani tablo iki farklı kod sürümünden ölçülmüş satırları aynı
    ortalamada topluyordu ve hiçbir sütun bunu söylemiyordu. Bu, gün boyunca
    kovaladığımız "birbiriyle çelişemeyen iki görünüm" sınıfının depo
    tarafındaki hâli.
    """
    mixed = [dataclasses.replace(r) for r in rows]
    mixed[0].code_fingerprint = "farklısürüm"
    summ = sweep.summarize(mixed, specs=builtin)
    md = sweep.summary_markdown(mixed, summ, {})
    assert "birden çok KOD SÜRÜMÜNDEN" in md
    assert "yeniden koşulmalıdır" in md


def test_a_single_version_sweep_says_so_explicitly(rows, builtin):
    """Temiz hâlde de yazılır: sessizlik 'denetlenmedi' anlamına gelmemeli."""
    assert len({r.code_fingerprint for r in rows}) == 1
    md = sweep.summary_markdown(rows, sweep.summarize(rows, specs=builtin), {})
    assert "TEK bir kod sürümünden" in md


def test_the_fingerprint_moves_when_the_package_changes(tmp_path, monkeypatch):
    """Parmak izi gerçekten DEĞİŞMELİ; sabit bir dizge hiçbir şey yakalamaz."""
    import pathlib
    before = sweep.code_fingerprint()
    assert before == sweep.code_fingerprint(), "aynı ağaçta kararlı olmalı"
    target = pathlib.Path(sweep.__file__).parent / "api.py"
    st = target.stat()
    try:
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        assert sweep.code_fingerprint() != before, \
            "dosya değişti ama parmak izi kıpırdamadı"
    finally:
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert sweep.code_fingerprint() == before, "geri alma da yansımalı"
