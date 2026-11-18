#!/usr/bin/env python3
"""D-REPAIR testleri (F3).

Sözleşme: her koşum ya üç doğruluk kapısından geçer ya da HANGİ kapının
düştüğü dürüstçe kayda geçer. Testler ikisini de kontrol eder; "geçemediyse
görmezden gel" diye bir dal yok.

Ölçülen büyüklükler (mesaj, tur, merkeziye oran) testlerin içinde hesaplanıp
`-s` ile basılır; sayılar motorun gerçek sayımıdır, tahmin değildir.
"""
from __future__ import annotations

import math
import os
import random
import sys
from typing import Dict, List, Set, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccvc import bridge, central  # noqa: E402
from ccvc.bridge import CcvcGraph, verify  # noqa: E402
from ccvc.d_repair import (  # noqa: E402
    DRepairNode,
    d_repair_factory,
    run_d_repair,
    solve_repair_oracle,
)
from ccvc.engine import run_protocol  # noqa: E402
from ccvc.engine_api import NodeProtocol  # noqa: E402

VARIANTS = ("gccvc", "grccvc", "gwccvc")
MAX_ROUNDS = 800
FRAMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "results",
    "mds_campus_seed0_frames.json",
)


# --------------------------------------------------------------------------
# yardımcılar
# --------------------------------------------------------------------------
def random_graph(n: int, p: float, k: int, seed: int) -> CcvcGraph:
    r = random.Random(seed)
    edges = sorted(
        {(u, v) for u in range(n) for v in range(u + 1, n) if r.random() < p}
    )
    w = {v: round(r.uniform(1.0, 100.0), 4) for v in range(n)}
    return CcvcGraph(nodes=list(range(n)), edges=edges, weight=w, capacity_k=k)


def all_non_isolated(g: CcvcGraph) -> Set[int]:
    """Taban çözüm: kenarı olan her düğüm örtüde. Her zaman örtü ve bileşen-bağlı."""
    return {v for v in g.nodes if g.adj[v]}


def instance_feasible(g: CcvcGraph) -> bool:
    """Bu k altında GEÇERLİ BİR ÇÖZÜM VAR MI.

    En geniş örtü (kenarı olan tüm düğümler) kapasite kapısından geçiyorsa
    geçerli çözüm vardır (örtü ve bileşen-bağlılık zaten sağlanır); geçmiyorsa
    daha küçük hiçbir örtü de geçemez, çünkü örtüyü küçültmek sahip adayı
    kümesini yalnız daraltır.
    """
    return bridge.capacity_feasible(g, all_non_isolated(g))[0]


def honest_failure(g: CcvcGraph, res) -> bool:
    """Geçersiz sonuç DÜRÜSTÇE kayda geçmiş mi.

    Kabul edilen tek başarısızlık biçimi: kapasite kapısı düşmüş, düşme nedeni
    motor defterinde de görünüyor (gerçekten sahiplenilmemiş kenar var) ve
    RunResult notlarında verify çıktısı duruyor.
    """
    vd = verify(g, res.cover)
    if vd.valid:
        return True
    if not vd.vertex_cover or not vd.connected:
        return False  # bu iki kapı hiç düşmemeli
    unowned = [e for e in g.edges if e not in res.owner]
    return bool(unowned) and any("verify:" in n for n in res.notes)


def sweep_capacities(g_unit: CcvcGraph) -> List[int]:
    md = max(1, g_unit.max_degree)
    return sorted({2, max(2, math.ceil(md / 2)), max(2, md)})


def load_frame_graphs(count: int, capacities=(2, 3, 5)):
    frames, _meta = bridge.load_frames(FRAMES_PATH)
    step = max(1, len(frames) // count)
    out = []
    for i in range(0, len(frames), step):
        if len(out) >= count * len(capacities):
            break
        for k in capacities:
            g = bridge.graph_from_frame(frames[i], k, weight_scheme="random", seed=i)
            out.append((f"frame{i}-k{k}", g))
    return out


def random_battery() -> List[Tuple[str, CcvcGraph]]:
    """48 farklı çizge, seyrekten yoğuna; her biri üç kapasitede koşulur."""
    out: List[Tuple[str, CcvcGraph]] = []
    seed = 0
    for n in (5, 8, 11, 14, 18, 22, 26, 30):
        for p in (0.08, 0.15, 0.25, 0.4, 0.6, 0.8):
            seed += 1
            probe = random_graph(n, p, 1, seed)
            for k in sweep_capacities(probe):
                out.append((f"n{n}-p{p}-k{k}-s{seed}", random_graph(n, p, k, seed)))
    return out


# --------------------------------------------------------------------------
# 1. geçerlilik: rastgele çizgeler
# --------------------------------------------------------------------------
def test_random_graphs_all_variants_valid():
    battery = random_battery()
    graphs = {name for name, _ in battery}
    assert len(graphs) >= 40 * 3, "en az 40 farklı çizge istenmişti"
    runs = 0
    valid = 0
    gate_fail = {"vertex_cover": 0, "connected": 0, "capacity": 0}
    for name, g in battery:
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            assert res.converged, f"{name}/{var}: yakınsamadı"
            vd = verify(g, res.cover)
            runs += 1
            if vd.valid:
                valid += 1
            else:
                assert honest_failure(
                    g, res
                ), f"{name}/{var}: başarısızlık örtbas edildi"
                if not vd.vertex_cover:
                    gate_fail["vertex_cover"] += 1
                if not vd.connected:
                    gate_fail["connected"] += 1
                if not vd.capacity_feasible:
                    gate_fail["capacity"] += 1
    rate = valid / runs
    print(
        f"\n[rastgele] koşum={runs} geçerli={valid} oran={rate:.4f} kapılar={gate_fail}"
    )
    # örtü ve bağlılık kapıları hiç düşmemeli: ikisi de protokolde kanıtlı
    assert gate_fail["vertex_cover"] == 0
    assert gate_fail["connected"] == 0
    assert rate >= 0.98, f"geçerlilik oranı çok düştü: {rate:.4f}"


# --------------------------------------------------------------------------
# 2. geçerlilik: gerçek simülatör kareleri
# --------------------------------------------------------------------------
def test_real_frames_all_variants_valid():
    cases = load_frame_graphs(24, capacities=(2, 3, 5))
    assert len({n.split("-")[0] for n, _ in cases}) >= 20, "en az 20 gerçek kare"
    runs = 0
    valid = 0
    bad_conn = 0
    for name, g in cases:
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            assert res.converged, f"{name}/{var}: yakınsamadı"
            vd = verify(g, res.cover)
            runs += 1
            valid += int(vd.valid)
            bad_conn += int(not vd.connected)
            assert honest_failure(g, res), f"{name}/{var}: başarısızlık örtbas edildi"
    print(f"\n[kareler] koşum={runs} geçerli={valid} oran={valid/runs:.4f}")
    assert bad_conn == 0
    assert valid / runs >= 0.98


# --------------------------------------------------------------------------
# 3. kopuk çizgeler ve yalıtık düğümler
# --------------------------------------------------------------------------
def test_isolated_vertices_never_enter_cover():
    g = CcvcGraph(
        nodes=[0, 1, 2, 3, 4],
        edges=[(0, 1), (1, 2)],
        weight={v: 1.0 for v in range(5)},
        capacity_k=2,
    )
    for var in VARIANTS:
        res = run_d_repair(g, var, max_rounds=50)
        assert res.converged
        assert 3 not in res.cover and 4 not in res.cover
        assert verify(g, res.cover).valid


def test_empty_graph_and_no_edges():
    g = CcvcGraph(
        nodes=[0, 1, 2], edges=[], weight={v: 1.0 for v in range(3)}, capacity_k=2
    )
    for var in VARIANTS:
        res = run_d_repair(g, var, max_rounds=10)
        assert res.cover == []
        assert res.messages == 0  # kenarsız düğüm hiç konuşmaz
        assert res.rounds == 1 and res.converged


def test_disconnected_components_are_solved_independently():
    """İki ayrı bileşen; KÖPRÜLENMEYE ÇALIŞILMAMALI, bileşen bazlı bağlılık yeter."""
    g = CcvcGraph(
        nodes=list(range(8)),
        edges=[(0, 1), (1, 2), (2, 3), (4, 5), (5, 6), (6, 7)],
        weight={v: 1.0 + v for v in range(8)},
        capacity_k=2,
    )
    for var in VARIANTS:
        res = run_d_repair(g, var, max_rounds=200)
        assert res.converged
        vd = verify(g, res.cover)
        assert vd.valid, vd.as_dict()
        # iki bileşenden de en az bir düğüm örtüde olmalı, ama tek parça olamaz
        assert any(v <= 3 for v in res.cover) and any(v >= 4 for v in res.cover)
        assert vd.components >= 2


def test_many_components_random():
    r = random.Random(3)
    for t in range(6):
        n = 24
        g = CcvcGraph(
            nodes=list(range(n)),
            edges=sorted(
                {
                    (u, v)
                    for u in range(n)
                    for v in range(u + 1, n)
                    if abs(u - v) <= 3 and r.random() < 0.35
                }
            ),
            weight={v: round(r.uniform(1, 50), 3) for v in range(n)},
            capacity_k=3,
        )
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            assert res.converged
            assert verify(g, res.cover).valid


# --------------------------------------------------------------------------
# 4. belirlenimcilik
# --------------------------------------------------------------------------
def _snapshot(res):
    return (
        sorted(res.cover),
        sorted((tuple(e), o) for e, o in res.owner.items()),
        res.rounds,
        res.messages,
        dict(sorted(res.messages_by_kind.items())),
        res.converged,
    )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_same_graph_same_result_every_time(seed):
    g = random_graph(16, 0.3, 3, seed)
    for var in VARIANTS:
        a = _snapshot(run_d_repair(g, var, max_rounds=MAX_ROUNDS))
        b = _snapshot(run_d_repair(g, var, max_rounds=MAX_ROUNDS))
        assert a == b


@pytest.mark.parametrize("seed", [4, 5])
def test_poll_order_does_not_change_outcome(seed):
    g = random_graph(14, 0.35, 3, seed)
    base = _snapshot(run_d_repair(g, "grccvc", max_rounds=MAX_ROUNDS))
    r = random.Random(seed)
    for _ in range(3):
        order = list(g.nodes)
        r.shuffle(order)
        other = _snapshot(
            run_d_repair(g, "grccvc", max_rounds=MAX_ROUNDS, poll_order=order)
        )
        assert other == base


# --------------------------------------------------------------------------
# 5. taban: "kenarı olan tüm düğümler" çözümünden kötü olamaz
# --------------------------------------------------------------------------
def test_never_worse_than_all_non_isolated_nodes():
    worst = 0
    for name, g in random_battery()[:60]:
        if not instance_feasible(g):
            continue
        base = all_non_isolated(g)
        base_w = g.total_weight(base)
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            w = g.total_weight(res.cover)
            assert w <= base_w + 1e-9, f"{name}/{var}: {w} > taban {base_w}"
            assert set(res.cover) <= base, "yalıtık düğüm örtüye girmiş"
            worst = max(worst, w / base_w if base_w else 0.0)
    print(f"\n[taban] en kötü ağırlık / tüm-düğümler = {worst:.3f}")


# --------------------------------------------------------------------------
# 6. kalite: merkezi ve tam çözüme oran (ÖLÇÜLÜR, iyi olması şart değil)
# --------------------------------------------------------------------------
def test_quality_against_central_and_exact():
    ratios: Dict[str, List[float]] = {v: [] for v in VARIANTS}
    exact_ratios: Dict[str, List[float]] = {v: [] for v in VARIANTS}
    rounds: List[int] = []
    msgs: List[int] = []
    for name, g in random_battery():
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            vd = verify(g, res.cover)
            if not vd.valid:
                continue
            rounds.append(res.rounds)
            msgs.append(res.messages)
            c = central.solve(var, g, strict=False)
            if c.valid and c.total_weight > 0:
                ratios[var].append(vd.total_weight / c.total_weight)
            comps = bridge.graph_components(g)
            if max(len(c_) for c_ in comps) <= 12:
                try:
                    ex = central.solve_exact(
                        g, max_n=12, time_limit_s=10.0, strict=False
                    )
                except ValueError:
                    ex = None
                if ex is not None and ex.valid and ex.exact and ex.total_weight > 0:
                    exact_ratios[var].append(vd.total_weight / ex.total_weight)
    print("\n[kalite] D-REPAIR ağırlığı / merkezi ağırlık")
    for var in VARIANTS:
        lst = ratios[var]
        assert lst, f"{var}: hiç karşılaştırma yapılamadı"
        print(
            f"  {var:7s} n={len(lst):4d} ort={sum(lst)/len(lst):.3f} "
            f"en iyi={min(lst):.3f} en kötü={max(lst):.3f}"
        )
        assert max(lst) <= 2.0, f"{var}: merkeziye göre 2x'ten kötü örnek var"
    print("[kalite] D-REPAIR ağırlığı / TAM çözüm")
    for var in VARIANTS:
        lst = exact_ratios[var]
        assert lst, f"{var}: tam çözümle hiç karşılaştırma yapılamadı"
        print(
            f"  {var:7s} n={len(lst):4d} ort={sum(lst)/len(lst):.3f} "
            f"en iyi={min(lst):.3f} en kötü={max(lst):.3f}"
        )
        assert (
            min(lst) >= 1.0 - 1e-9
        ), f"{var}: tam çözümden İYİ çıktı, tam çözücü hatalı"
    print(
        f"[maliyet] tur ort={sum(rounds)/len(rounds):.1f} en çok={max(rounds)} | "
        f"mesaj ort={sum(msgs)/len(msgs):.0f} en çok={max(msgs)}"
    )


# --------------------------------------------------------------------------
# 7. iki kırmızı kipi de koşar ve farkı ölçülür
# --------------------------------------------------------------------------
def test_both_red_modes_run_and_are_compared():
    diff = 0
    same = 0
    wsum = {"none": 0.0, "local": 0.0}
    msum = {"none": 0, "local": 0}
    rsum = {"none": 0, "local": 0}
    n = 0
    for name, g in random_battery()[:60]:
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            out = {}
            ok = True
            for rm in ("none", "local"):
                res = run_d_repair(g, var, max_rounds=MAX_ROUNDS, red_mode=rm)
                assert res.converged, f"{name}/{var}/{rm}: yakınsamadı"
                vd = verify(g, res.cover)
                assert honest_failure(g, res)
                ok = ok and vd.valid
                out[rm] = (vd.total_weight, res.messages, res.rounds, sorted(res.cover))
            if not ok:
                continue
            n += 1
            for rm in ("none", "local"):
                wsum[rm] += out[rm][0]
                msum[rm] += out[rm][1]
                rsum[rm] += out[rm][2]
            if out["none"][3] == out["local"][3]:
                same += 1
            else:
                diff += 1
    assert n > 0
    print(
        f"\n[kırmızı] karşılaştırılan={n} aynı örtü={same} farklı örtü={diff}\n"
        f"  none : W={wsum['none']:.1f} mesaj={msum['none']} tur={rsum['none']}\n"
        f"  local: W={wsum['local']:.1f} mesaj={msum['local']} tur={rsum['local']}"
    )
    assert diff > 0, "yerel kırmızı kural hiçbir örnekte davranışı değiştirmedi"


# --------------------------------------------------------------------------
# 8. onarımın gerçekten iş yaptığı kanıtı (hop_bound=0 ablasyonu)
# --------------------------------------------------------------------------
def _repair_needed_cases():
    """Örtü evresinin parçalı bir örtü bıraktığı örnekler."""
    found = []
    for name, g in random_battery():
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            off = run_d_repair(g, var, max_rounds=MAX_ROUNDS, hop_bound=0)
            if not verify(g, off.cover).connected:
                found.append((name, g, var, off))
    return found


def test_repair_fixes_what_the_cover_phase_breaks():
    cases = _repair_needed_cases()
    assert cases, "hiçbir örnekte onarıma ihtiyaç doğmadı, ablasyon anlamsız"
    extra_w = []
    extra_m = []
    extra_r = []
    for name, g, var, off in cases:
        on = run_d_repair(g, var, max_rounds=MAX_ROUNDS, hop_bound=1)
        vd_on = verify(g, on.cover)
        assert vd_on.connected, f"{name}/{var}: onarım bağlılığı sağlayamadı"
        assert honest_failure(g, on)
        w_off = g.total_weight(off.cover)
        if w_off > 0:
            extra_w.append(g.total_weight(on.cover) / w_off)
        extra_m.append(on.messages - off.messages)
        extra_r.append(on.rounds - off.rounds)
    print(
        f"\n[onarım] onarım gereken örnek={len(cases)} | "
        f"ağırlık artışı ort={sum(extra_w)/len(extra_w):.3f} | "
        f"ek mesaj ort={sum(extra_m)/len(extra_m):.1f} | "
        f"ek tur ort={sum(extra_r)/len(extra_r):.1f}"
    )


def test_bridge_never_joins_two_graph_components():
    """Kopuk çizgede köprüleme denenmemeli; örtü bileşen sayısı azalmamalı."""
    g = CcvcGraph(
        nodes=list(range(10)),
        edges=[(0, 1), (1, 2), (3, 4), (4, 5), (6, 7), (7, 8), (8, 9)],
        weight={v: 1.0 for v in range(10)},
        capacity_k=2,
    )
    graph_comps = [c for c in bridge.graph_components(g) if len(c) > 1]
    for var in VARIANTS:
        res = run_d_repair(g, var, max_rounds=200)
        vd = verify(g, res.cover)
        assert vd.valid
        touched = sum(1 for c in graph_comps if set(res.cover) & c)
        assert vd.components >= touched, "ayrı bileşenler köprülenmiş olamaz"


# --------------------------------------------------------------------------
# 9. kapasite baskısı: onarımı ve devri zorlayan dar k
# --------------------------------------------------------------------------
def _min_feasible_k(g_builder) -> int:
    for k in range(1, 30):
        g = g_builder(k)
        if instance_feasible(g):
            return k
    return -1


def test_tight_capacity_stress():
    """k, çözümün var olduğu en küçük değere çekilir: kenar devri kaçınılmaz olur."""
    checked = 0
    valid = 0
    relief_seen = 0
    for seed in range(1, 25):
        n = 6 + (seed % 12)
        p = (0.2, 0.35, 0.55, 0.75)[seed % 4]
        k = _min_feasible_k(lambda kk: random_graph(n, p, kk, seed))
        if k < 1:
            continue
        g = random_graph(n, p, k, seed)
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            assert res.converged, f"s{seed}/{var}: yakınsamadı"
            assert honest_failure(g, res), f"s{seed}/{var}: başarısızlık örtbas edildi"
            checked += 1
            valid += int(verify(g, res.cover).valid)
            relief_seen += res.messages_by_kind.get("CAPACITY_STATE", 0)
            # kapasite hiçbir koşulda aşılamaz (motor da zorlar, biz de bakarız)
            load: Dict[int, int] = {}
            for _e, o in res.owner.items():
                load[o] = load.get(o, 0) + 1
            assert all(v <= g.capacity_k for v in load.values())
    print(
        f"\n[dar kapasite] koşum={checked} geçerli={valid} "
        f"oran={valid/max(1,checked):.3f} devir mesajı={relief_seen}"
    )
    assert checked > 0
    assert valid / checked >= 0.95


def test_capacity_never_exceeded_anywhere():
    for name, g in random_battery()[:40]:
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            load: Dict[int, int] = {}
            for _e, o in res.owner.items():
                load[o] = load.get(o, 0) + 1
            assert all(x <= g.capacity_k for x in load.values()), name
            assert set(res.owner.values()) <= set(res.cover)


def test_open_edge_always_means_real_capacity_lock():
    """Zor parça 3-(i): kenar ASLA "karşı taraf halleder" sanıldığı için açık kalmaz.

    Motorun defterinde sahiplenilmemiş bir kenar kalabilir, ama yalnız tek bir
    nedenle: her iki ucu da ya örtüde ve DOYMUŞtur ya da örtü dışındadır (ve o
    zaman öteki uç doymuştur). Örtüde olup boş yuvası olan bir uç varken kenarın
    açık kalması eşgüdüm hatası olurdu; bu test onu yakalar.

    Ayrıca açık kenarla biten koşumların oranı ölçülür: kümesel çözüm geçerli
    olsa bile protokolün pazarlıkla ürettiği kenar ataması eksik kalabilir,
    çünkü artırıcı yol araması `relief_budget` ile sınırlıdır.
    """
    total = 0
    with_open = 0
    for name, g in random_battery():
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            res = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            total += 1
            cover = set(res.cover)
            load: Dict[int, int] = {}
            for _e, o in res.owner.items():
                load[o] = load.get(o, 0) + 1
            unowned = [e for e in g.edges if e not in res.owner]
            if unowned:
                with_open += 1
            for u, v in unowned:
                for x in (u, v):
                    assert not (x in cover and load.get(x, 0) < g.capacity_k), (
                        f"{name}/{var}: kenar ({u},{v}) açık ama {x} örtüde ve "
                        f"yükü {load.get(x, 0)} < k={g.capacity_k} — eşgüdüm hatası"
                    )
                assert x in cover or (v if x == u else u) in cover
    print(
        f"\n[kenar ataması] koşum={total} eksik atamayla biten={with_open} "
        f"oran={with_open/total:.3f}"
    )
    assert with_open / total <= 0.15


# --------------------------------------------------------------------------
# 10. yapısal: protokol küresel hiçbir şeye tutunmuyor
# --------------------------------------------------------------------------
def test_protocol_holds_no_global_handles():
    g = random_graph(10, 0.4, 3, 11)
    made: List[DRepairNode] = []

    def factory(node_id: int) -> NodeProtocol:
        p = DRepairNode("grccvc")
        made.append(p)
        return p

    run_protocol(g, factory, max_rounds=MAX_ROUNDS)
    assert made
    banned = (CcvcGraph,)
    for p in made:
        for attr, val in vars(p).items():
            assert not isinstance(val, banned), f"{attr} çizgeye tutunuyor"
            assert not isinstance(val, NodeProtocol), f"{attr} başka düğüme tutunuyor"
        # bir düğümün bildiği kimlikler yalnız kendi komşuları olabilir
        me = p.me
        nbrs = set(g.adj[me])
        assert set(p.nbr_piece) <= nbrs
        assert set(p.cand_nbrs) <= nbrs
        assert set(p.handed) <= nbrs


def test_bad_arguments_rejected():
    with pytest.raises(ValueError):
        DRepairNode("nope")
    with pytest.raises(ValueError):
        DRepairNode("gccvc", red_mode="global")
    with pytest.raises(ValueError):
        DRepairNode("gccvc", hop_bound=-1)


def test_variants_actually_differ():
    """Üç anahtar farklı örtüler üretmeli; aynıysa skor hiç kullanılmıyor demektir."""
    seen = 0
    for name, g in random_battery()[:40]:
        covers = {
            var: tuple(run_d_repair(g, var, max_rounds=MAX_ROUNDS).cover)
            for var in VARIANTS
        }
        if len(set(covers.values())) > 1:
            seen += 1
    assert seen >= 10, f"çeşitler yalnız {seen} örnekte ayrıştı"


def test_message_kinds_are_only_the_declared_ones():
    from ccvc import engine_api as api

    allowed = {
        api.COVER_INTENT,
        api.EDGE_CLAIM,
        api.EDGE_CLAIM_ACK,
        api.CAPACITY_STATE,
        api.COVER_MEMBERSHIP,
        api.BRIDGE_REQUEST,
        api.BRIDGE_ACCEPT,
        api.COVER_WITHDRAW,
    }
    kinds: Set[str] = set()
    for name, g in random_battery()[:30]:
        for var in VARIANTS:
            kinds |= set(run_d_repair(g, var, max_rounds=MAX_ROUNDS).messages_by_kind)
    assert kinds <= allowed, kinds - allowed
    print(f"\n[mesaj tipleri] kullanılan={sorted(kinds)}")


def test_capacity_push_ablation_is_measured():
    """Devir gradyanı: mesaj pahasına kapasite kilidini açıyor mu — ÖLÇ."""
    stats = {}
    for flag in (True, False):
        ok = 0
        tot = 0
        m = 0
        for name, g in load_frame_graphs(16, capacities=(2, 3)):
            if not instance_feasible(g):
                continue
            for var in VARIANTS:
                res = run_d_repair(g, var, max_rounds=MAX_ROUNDS, capacity_push=flag)
                assert honest_failure(g, res)
                tot += 1
                ok += int(verify(g, res.cover).valid)
                m += res.messages
        stats[flag] = (ok, tot, m / max(1, tot))
    print(
        f"\n[devir gradyanı] açık: {stats[True][0]}/{stats[True][1]} geçerli, "
        f"mesaj ort={stats[True][2]:.0f} | kapalı: {stats[False][0]}/{stats[False][1]} geçerli, "
        f"mesaj ort={stats[False][2]:.0f}"
    )
    assert stats[True][0] >= stats[False][0]


# --------------------------------------------------------------------------
# 11. merkezi kâhin: aynı strateji, tam bilgi
# --------------------------------------------------------------------------
def test_oracle_is_valid_and_costs_nothing():
    runs = 0
    for name, g in random_battery():
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            res = solve_repair_oracle(g, var)
            assert res.messages == 0 and res.rounds == 0, "kâhin mesaj/tur harcamamalı"
            assert res.converged
            vd = verify(g, res.cover)
            assert vd.vertex_cover and vd.connected, f"{name}/{var}: {vd.as_dict()}"
            assert honest_failure(g, res)
            runs += 1
    print(f"\n[kâhin] koşum={runs}")
    assert runs > 0


def test_oracle_is_deterministic():
    for seed in (1, 2, 3):
        g = random_graph(18, 0.3, 3, seed)
        for var in VARIANTS:
            a = solve_repair_oracle(g, var)
            b = solve_repair_oracle(g, var)
            assert sorted(a.cover) == sorted(b.cover)
            assert sorted(a.owner.items()) == sorted(b.owner.items())


def test_oracle_and_node_share_one_rule_set():
    """Yapısal: iki kol da AYNI modül düzeyi kuralları çağırır, kopya yok.

    Kuralları geçici olarak bozarsak İKİSİ BİRDEN bozulmalı. Bozulmayan kol
    kuralın ikinci bir kopyasını taşıyor demektir.
    """
    import ccvc.d_repair as mod

    g = random_graph(14, 0.35, 3, 21)
    base_node = sorted(run_d_repair(g, "grccvc", max_rounds=MAX_ROUNDS).cover)
    base_oracle = sorted(solve_repair_oracle(g, "grccvc").cover)
    original = mod.priority_key
    try:
        mod.priority_key = lambda variant, weight, node, ud, s: (float(node),)
        bent_node = sorted(run_d_repair(g, "grccvc", max_rounds=MAX_ROUNDS).cover)
        bent_oracle = sorted(solve_repair_oracle(g, "grccvc").cover)
    finally:
        mod.priority_key = original
    assert bent_node != base_node, "düğüm paylaşılan öncelik kuralını kullanmıyor"
    assert bent_oracle != base_oracle, "kâhin paylaşılan öncelik kuralını kullanmıyor"
    assert sorted(run_d_repair(g, "grccvc", max_rounds=MAX_ROUNDS).cover) == base_node


def test_locality_cost_and_parallel_vs_sequential():
    """2x2'nin eksik iki farkı, EŞLEŞTİRİLMİŞ ölçüm.

    kâhin - D-REPAIR        = yerellik + eskimenin bedeli
    kâhin - sıralı merkezi  = paralel-vs-sıralı seçimin farkı
    """
    loc: Dict[str, List[float]] = {v: [] for v in VARIANTS}
    par: Dict[str, List[float]] = {v: [] for v in VARIANTS}
    node_beats_oracle = 0
    pairs = 0
    for name, g in random_battery():
        if not instance_feasible(g):
            continue
        for var in VARIANTS:
            o = solve_repair_oracle(g, var)
            d = run_d_repair(g, var, max_rounds=MAX_ROUNDS)
            c = central.solve(var, g, strict=False)
            vo, vd = verify(g, o.cover), verify(g, d.cover)
            if not (vo.valid and vd.valid and c.valid) or c.total_weight <= 0:
                continue
            pairs += 1
            loc[var].append((vd.total_weight - vo.total_weight) / c.total_weight)
            par[var].append((vo.total_weight - c.total_weight) / c.total_weight)
            if vd.total_weight < vo.total_weight - 1e-9:
                node_beats_oracle += 1
    print("\n[2x2] merkezi greedy ağırlığına göre oransal fark")
    for var in VARIANTS:
        print(
            f"  {var:7s} yerellik bedeli={sum(loc[var])/len(loc[var]):+.4f}  "
            f"paralel-sıralı={sum(par[var])/len(par[var]):+.4f}  n={len(loc[var])}"
        )
    print(
        f"  D-REPAIR kendi kâhininden HAFİF çıkan koşum: {node_beats_oracle}/{pairs} "
        f"({node_beats_oracle/pairs:.3f})"
    )
    for var in VARIANTS:
        assert (
            sum(loc[var]) / len(loc[var]) >= -0.02
        ), "yerellik ortalamada KAZANDIRAMAZ"
        assert sum(par[var]) / len(par[var]) < 0.0, "paralel seçim sıralıdan kötü çıktı"
    # eskime bazen kazandırır; bu bir kusur değil, açgözlü sezgiselin bilinen
    # tekdüze-olmama özelliğidir. Sık olursa kural ayrışması şüphesi doğar.
    assert node_beats_oracle / pairs <= 0.10


def test_oracle_registered_in_specs():
    from ccvc.d_repair import SPECS

    labels = [lab for lab, _fn in SPECS]
    assert "repair_oracle" in labels
    assert all(
        lab.startswith("d_repair_") or lab.startswith("repair_oracle") for lab in labels
    )
    assert not any("central" in lab for lab in labels)
    g = random_graph(12, 0.35, 3, 33)
    for lab, fn in SPECS:
        rr = fn(g)
        assert (
            hasattr(rr, "cover") and hasattr(rr, "messages") and hasattr(rr, "rounds")
        )
