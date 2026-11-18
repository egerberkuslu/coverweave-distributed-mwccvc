#!/usr/bin/env python3
"""D-CDS kolu testleri (F4).

Koşum:
    env -u PYTHONPATH -u AMENT_PREFIX_PATH -u ROS_DISTRO \
        python3 -m pytest ccvc/test_d_cds.py -q -p no:cacheprovider

Testlerin sorduğu sorular, sırayla:
  * omurga gerçekten bağlı baskın küme mi (bileşen bazlı)
  * dağıtık işaretleme/budama, merkezi Wu-Li referansıyla birebir aynı mı
  * nihai örtü üç doğruluk kapısından geçiyor mu, hem rastgele çizgede hem
    simülatörün GERÇEK karelerinde, birden çok kapasitede
  * bağlılık değişmezi HER EKLEMEDEN sonra ayakta mı (sonunda değil, her turda)
  * kopuk çizge ve yalıtık düğüm doğru mu ele alınıyor
  * sonuç belirlenimci mi (tekrar koşumda ve yoklama sırası değişince)
  * iki atlama bilgisi ADAYA KOŞULLU mu kullanılıyor (dejenerasyon tuzağı)
  * iki atlama bilgisi VARSAYILMIYOR, mesajla mı kazanılıyor
  * merkezi ve tam çözüme göre kalite oranı ne
  * dar kapasitede artırıcı yol gerçekten ateşleniyor mu
  * bayat bilgi altında kenar açıkta kalıyor mu
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pytest

try:
    from ccvc import central
    from ccvc.bridge import (
        CcvcGraph,
        Verdict,
        edge_key,
        graph_components,
        graph_from_frame,
        is_connected_cover,
        load_frames,
        verify,
    )
    from ccvc.d_cds import (
        SHED_ACCEPT,
        SHED_REQUEST,
        SPECS,
        DcdsNode,
        DcdsParams,
        _max_assignment,
        cds_central_cover,
        make_factory,
        run_d_cds,
        solve_cds_central,
    )
    from ccvc.engine import RoundEngine
    from ccvc.engine_api import (
        COVER_MEMBERSHIP,
        EDGE_CLAIM,
        MARK_STATE,
        TWO_HOP_DIGEST,
        EdgeLocal,
        LocalView,
        Message,
        NeighborRecord,
        NodeDecision,
    )
except ImportError:  # pragma: no cover
    import central  # type: ignore
    from bridge import (  # type: ignore
        CcvcGraph,
        Verdict,
        edge_key,
        graph_components,
        graph_from_frame,
        is_connected_cover,
        load_frames,
        verify,
    )
    from d_cds import (  # type: ignore
        SHED_ACCEPT,
        SHED_REQUEST,
        SPECS,
        DcdsNode,
        DcdsParams,
        _max_assignment,
        cds_central_cover,
        make_factory,
        run_d_cds,
        solve_cds_central,
    )
    from engine import RoundEngine  # type: ignore
    from engine_api import (  # type: ignore
        COVER_MEMBERSHIP,
        EDGE_CLAIM,
        MARK_STATE,
        TWO_HOP_DIGEST,
        EdgeLocal,
        LocalView,
        Message,
        NeighborRecord,
        NodeDecision,
    )

import os

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(os.path.dirname(HERE), "results", "mds_campus_seed0_frames.json")

# testler arası rapor defteri (son testte özet olarak basılır)
REPORT: Dict[str, object] = {}


# ==========================================================================
# yardımcılar
# ==========================================================================
def mk(edges, n: Optional[int] = None, k: int = 2, weight=None) -> CcvcGraph:
    edges = sorted({edge_key(u, v) for u, v in edges})
    if n is None:
        n = (max((max(e) for e in edges), default=-1)) + 1
    nodes = list(range(n))
    w = weight or {v: 1.0 for v in nodes}
    return CcvcGraph(nodes=nodes, edges=list(edges), weight=w, capacity_k=k)


def random_graph(seed: int, n: int, p: float, k: int, weighted: bool = False) -> CcvcGraph:
    """Erdos-Renyi; kopukluk ve yalıtık düğüm doğal olarak çıkar (PLAN §0.5)."""
    rr = random.Random(seed)
    edges = sorted(
        {edge_key(u, v) for u in range(n) for v in range(u + 1, n) if rr.random() < p}
    )
    nodes = list(range(n))
    if weighted:
        w = {v: round(rr.uniform(1.0, 10.0), 3) for v in nodes}
    else:
        w = {v: 1.0 for v in nodes}
    return CcvcGraph(nodes=nodes, edges=list(edges), weight=w, capacity_k=k)


K_LADDER = (1, 2, 3, 4, 6, 8, 12, 20)
_SUITE_CACHE: Dict[str, List[CcvcGraph]] = {}


def _central_reference(g: CcvcGraph) -> Optional[float]:
    """Merkezi çözücülerden HERHANGİ biri geçerli çözüm buluyor mu, buluyorsa ağırlığı.

    Kapasite kısıtı çok dar olduğunda örneğin hiç çözümü YOKTUR; böyle bir örnekte
    dağıtık kolun kapasite kapısından geçememesi kusur değildir. Bu yüzden asıl
    örnek kümesi, merkezi bir referansın çözebildiği örneklerden kurulur.
    """
    best = None
    for name in ("gccvc", "grccvc", "gwccvc"):
        c = central.solve(name, g, strict=False)
        if c.valid and (best is None or c.total_weight < best):
            best = c.total_weight
    return best


def random_suite(count: int = 48) -> List[CcvcGraph]:
    """Yoğunluk süpüren, kapasitesi EN DAR ÇÖZÜLEBİLİR değere ayarlanmış örnekler.

    k merdiveni en küçükten denenir ve merkezi referansın çözebildiği ilk değerde
    durulur; böylece kapasite kısıtı hep sıkıdır ve artırıcı yol gerçekten çalışır.
    Küme belirlenimcidir ve süreç başına bir kez kurulur.
    """
    key = f"suite{count}"
    if key in _SUITE_CACHE:
        return _SUITE_CACHE[key]
    out: List[CcvcGraph] = []
    i = 0
    while len(out) < count and i < count * 4:
        n = 5 + (i % 10)
        p = [0.12, 0.2, 0.3, 0.45, 0.6, 0.8][i % 6]
        weighted = bool(i % 3)
        i += 1
        for k in K_LADDER:
            g = random_graph(1000 + i, n, p, k, weighted=weighted)
            if not g.edges:
                out.append(g)  # kenarsız çizge de kümede kalsın
                break
            if _central_reference(g) is not None:
                out.append(g)
                break
    _SUITE_CACHE[key] = out
    return out


def infeasible_suite() -> List[CcvcGraph]:
    """Kapasitesi GERÇEKTEN yetmeyen örnekler: hiçbir merkezi çözücü çözemiyor."""
    key = "infeasible"
    if key in _SUITE_CACHE:
        return _SUITE_CACHE[key]
    out: List[CcvcGraph] = []
    for i in range(40):
        n = 8 + (i % 5)
        p = [0.6, 0.8, 0.9][i % 3]
        g = random_graph(2000 + i, n, p, 2, weighted=bool(i % 2))
        if g.edges and _central_reference(g) is None:
            out.append(g)
    _SUITE_CACHE[key] = out
    return out


def run_with_nodes(
    g: CcvcGraph,
    params: Optional[DcdsParams] = None,
    max_rounds: int = 300,
    poll_order: Optional[Sequence[int]] = None,
    cls=DcdsNode,
    **kw,
):
    """Koşumu yap ve düğüm ÖRNEKLERİNİ de döndür.

    Örnekleri TEST tutar, düğümler birbirini görmez: motor her düğüme kendi
    örneğini verir, örnekler arasında hiçbir yapı paylaşılmaz.
    """
    holder: Dict[int, DcdsNode] = {}

    def factory(node_id: int):
        node = cls(params, **kw) if kw else cls(params)
        holder[node_id] = node
        return node

    res = RoundEngine(g, poll_order=poll_order, algorithm="d-cds").run(
        factory, max_rounds=max_rounds
    )
    return res, holder


def backbone_of(holder: Dict[int, DcdsNode]) -> Set[int]:
    return {v for v, node in holder.items() if node._backbone}


def is_clique(g: CcvcGraph, comp: Set[int]) -> bool:
    return all(
        (v in g.adj[u]) for u in comp for v in comp if u != v
    )


def dominates(g: CcvcGraph, comp: Set[int], b: Set[int]) -> bool:
    return all(v in b or (g.adj[v] & b) for v in comp)


def ref_wu_li(g: CcvcGraph) -> Set[int]:
    """Merkezi Wu-Li referansı: tüm çizgeyi görerek işaretle ve buda.

    Dağıtık kolun ÇIKTISI bununla birebir tutmalı. Burada küresel bilgi
    kullanmak serbesttir; bu bir test oracle'ıdır, algoritma değil.
    """
    closed = {v: set(g.adj[v]) | {v} for v in g.nodes}
    prio = {v: (g.weight[v], v) for v in g.nodes}
    marked: Set[int] = set()
    for v in g.nodes:
        nb = sorted(g.adj[v])
        if any(
            nb[j] not in g.adj[nb[i]]
            for i in range(len(nb))
            for j in range(i + 1, len(nb))
        ):
            marked.add(v)
    out: Set[int] = set()
    for v in sorted(marked):
        cand = [u for u in sorted(g.adj[v]) if u in marked and prio[u] < prio[v]]
        drop = any(closed[v] <= closed[u] for u in cand)
        if not drop:
            drop = any(
                closed[v] <= (closed[u] | closed[x])
                for i, u in enumerate(cand)
                for x in cand[i + 1 :]
                if x in g.adj[u]
            )
        if not drop:
            out.add(v)
    return out


class Recorder(DcdsNode):
    """Kendi kararlarını dışarıdaki bir deftere yazan test alt sınıfı.

    Defter TESTİN'dir, protokolün değil: `DcdsNode` hiçbir paylaşılan yapıya
    dokunmaz, kayıt tamamen test tarafında kalır.
    """

    def __init__(self, params=None, log=None):
        super().__init__(params)
        self._log = log if log is not None else {}

    def on_round(self, view: LocalView):
        msgs, dec = super().on_round(view)
        # kayıt KARARDAN SONRA alınır: düğümün karar anındaki bilgisi budur
        cover_neighbours = {o for o in view.incident if self._led.in_cover.get(o)}
        if dec.join_cover:
            self._log.setdefault(view.round, []).append(
                (view.me, sorted(cover_neighbours), self._backbone, self._clique is not None)
            )
        return msgs, dec


def frames_subset(count: int = 24) -> List[dict]:
    frames, _ = load_frames(FRAMES)
    step = max(1, len(frames) // count)
    return [frames[i] for i in range(0, len(frames), step)][:count]


# ==========================================================================
# 1. omurga gerçekten CDS mi
# ==========================================================================
def test_backbone_is_connected_dominating_set_per_component():
    """40+ rastgele çizgede omurga, her bileşen içinde baskın VE bağlı olmalı.

    Klik bileşeni istisnadır: orada hiç kimse işaretlenmez (Wu-Li tanımı gereği)
    ve omurga boş kalır; o bileşeni klik kuralı örter.
    """
    graphs = random_suite(48)
    assert len(graphs) >= 40
    checked_components = 0
    clique_components = 0
    for g in graphs:
        res, holder = run_with_nodes(g)
        b = backbone_of(holder)
        for comp in graph_components(g):
            if len(comp) == 1:
                assert not (comp & b), "yalıtık düğüm omurgaya giremez"
                continue
            part = b & comp
            if is_clique(g, comp):
                clique_components += 1
                assert part == set(), "klik bileşeninde Wu-Li kimseyi işaretlemez"
                continue
            checked_components += 1
            assert part, f"bileşen {sorted(comp)} için omurga boş"
            assert dominates(g, comp, part), f"omurga baskın değil: {sorted(comp)}"
            assert is_connected_cover(g, part), f"omurga kopuk: {sorted(comp)}"
    assert checked_components >= 40, checked_components
    REPORT["cds_components"] = (checked_components, clique_components)


def test_distributed_backbone_equals_central_wu_li_reference():
    """Dağıtık işaretleme+budama, tüm çizgeyi gören referansla birebir aynı olmalı."""
    for g in random_suite(48):
        res, holder = run_with_nodes(g)
        assert backbone_of(holder) == ref_wu_li(g), g.edges


def test_pruning_priority_keeps_the_cheap_node():
    """Budama (ağırlık, kimlik) önceliğiyle PAHALI olanı atar, ucuzu tutar.

    0 ve 1 komşu ve N[0] = N[1] = {0,1,2,3}; ikisi de işaretlenir, biri budanır.
    Kural 1 simetrik olduğu için hangisinin kalacağını yalnız öncelik belirler.
    """
    edges = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3)]
    cheap_is_zero = mk(edges, k=4, weight={0: 1.0, 1: 9.0, 2: 5.0, 3: 5.0})
    cheap_is_one = mk(edges, k=4, weight={0: 9.0, 1: 1.0, 2: 5.0, 3: 5.0})
    _, h0 = run_with_nodes(cheap_is_zero)
    _, h1 = run_with_nodes(cheap_is_one)
    b0, b1 = backbone_of(h0), backbone_of(h1)
    assert 0 in b0 and 1 not in b0, (b0, b1)
    assert 1 in b1 and 0 not in b1, (b0, b1)


# ==========================================================================
# 2. nihai örtü: üç kapı
# ==========================================================================
def test_final_cover_passes_all_gates_on_random_graphs():
    graphs = random_suite(48)
    for g in graphs:
        res = run_d_cds(g, max_rounds=300)
        v = verify(g, res.cover)
        assert res.converged, (g.edges, res.rounds)
        assert v.vertex_cover, (g.edges, res.cover)
        assert v.connected, (g.edges, res.cover)
        assert v.capacity_feasible, (g.edges, g.capacity_k, res.cover)


def test_genuinely_infeasible_instances_fail_honestly():
    """Kapasite hiçbir çözüme izin vermiyorsa: koşum yine de durur, örtü ve bağlılık
    kapıları geçer, yalnız kapasite kapısı dürüstçe False döner. Sonsuz döngü yok."""
    suite = infeasible_suite()
    assert len(suite) >= 5, len(suite)
    for g in suite:
        res = run_d_cds(g, max_rounds=300)
        v = verify(g, res.cover)
        assert res.rounds < 300, "umutsuz kenar koşumu kilitlememeli"
        assert v.vertex_cover, (g.edges, res.cover)
        assert v.connected, (g.edges, res.cover)
        assert not v.capacity_feasible
        load: Dict[int, int] = {}
        for _, o in res.owner.items():
            load[o] = load.get(o, 0) + 1
        assert all(c <= g.capacity_k for c in load.values())
    REPORT["infeasible_instances"] = len(suite)


def solution_can_exist(g: CcvcGraph) -> bool:
    """Verilen k altında HERHANGİ bir geçerli çözüm var mı?

    Kenarı olan tüm düğümleri almak, olası en geniş örtüdür ve kenar başına en çok
    sahip adayını verir; bu örtü kapasite kapısından geçemiyorsa hiçbir örtü geçemez.
    Yani bu sınama kesindir, sezgisel değil.
    """
    trivial = {v for v in g.nodes if g.degree(v) > 0}
    return verify(g, trivial).capacity_feasible


@pytest.mark.parametrize("k", [3, 4, 6])
def test_real_frames_pass_all_gates(k: int):
    """Simülatörün GERÇEK kareleri: 91 karenin TAMAMI, üç kapasitede.

    Çözümü olan her karede üç kapı da geçilmeli. Çözümü OLMAYAN karede (kapasite
    hiçbir örtüye yetmiyor) örtü ve bağlılık yine geçmeli, kapasite dürüstçe
    False dönmeli. Hangi karelerin çözümsüz olduğu rapora yazılır.
    """
    frames, _ = load_frames(FRAMES)
    assert len(frames) >= 20
    solvable = 0
    unsolvable: List[int] = []
    for idx, fr in enumerate(frames):
        g = graph_from_frame(fr, capacity_k=k, weight_scheme="unit")
        res = run_d_cds(g, max_rounds=400)
        v = verify(g, res.cover)
        assert res.converged, (idx, k, res.rounds)
        assert v.vertex_cover, (idx, k, res.cover)
        assert v.connected, (idx, k, res.cover)
        if solution_can_exist(g):
            solvable += 1
            assert v.capacity_feasible, (idx, k, v.as_dict())
        else:
            unsolvable.append(idx)
    assert solvable >= 20, solvable
    REPORT.setdefault("frames_gates", {})[k] = {
        "frames": len(frames),
        "solvable": solvable,
        "unsolvable": unsolvable,
    }


def test_real_frames_with_weight_schemes():
    """Ağırlık şeması bağımsız değişken: invdeg ve random şemalarında da kapılar geçmeli."""
    for scheme in ("invdeg", "random", "degree"):
        for fr in frames_subset(10):
            g = graph_from_frame(fr, capacity_k=4, weight_scheme=scheme, seed=7)
            res = run_d_cds(g, max_rounds=300)
            assert verify(g, res.cover).valid, (scheme, res.cover)


# ==========================================================================
# 3. bağlılık değişmezi: HER EKLEMEDEN sonra
# ==========================================================================
def test_connectivity_invariant_holds_after_every_single_addition():
    """İki ayrı kontrol:

    (a) her turun sonunda o ana kadarki örtü, bileşen bazında bağlı olmalı
    (b) inşa evresi DIŞINDA katılan her düğümün, katıldığı turun BAŞINDA örtüde
        bir komşusu olmalı (omurgaya asılma önermesi)
    """
    extension_joins = 0
    for g in random_suite(48):
        log: Dict[int, List[Tuple]] = {}
        res, holder = run_with_nodes(g, cls=Recorder, log=log)
        cover: Set[int] = set()
        for rnd in range(res.rounds):
            for me, cover_nbrs, was_backbone, was_clique in log.get(rnd, []):
                if not (was_backbone or was_clique):
                    extension_joins += 1
                    assert cover_nbrs, (
                        f"düğüm {me} tur {rnd}: örtüde komşusu yokken katıldı"
                    )
                    assert set(cover_nbrs) <= cover, (me, rnd, cover_nbrs, cover)
                cover.add(me)
            assert is_connected_cover(g, cover), (
                f"tur {rnd} sonunda örtü kopuk: {sorted(cover)}"
            )
        assert cover == set(res.cover)
    assert extension_joins > 0, "genişletme hiç çalışmadıysa test bir şey kanıtlamaz"
    REPORT["extension_joins"] = extension_joins


def test_no_node_reports_an_invariant_violation():
    for g in random_suite(48):
        res, holder = run_with_nodes(g)
        for v, node in holder.items():
            assert node.violations == 0, (v, node.notes)


def test_strict_invariant_raises_when_attachment_is_missing():
    """Kapı gerçekten kapı mı: bitişik olmayan bir katılım denemesi hata atmalı."""
    from ccvc.d_cds import DcdsInvariantError

    node = DcdsNode(DcdsParams(strict_invariant=True))
    node.on_start(0, 1.0, 2, 1)
    view = LocalView(
        me=0,
        round=9,
        weight=1.0,
        capacity_k=2,
        remaining_capacity=2,
        in_cover=False,
        incident={1: EdgeLocal(other=1)},
        neighbors={},
    )
    node._nbrs = {1}
    with pytest.raises(DcdsInvariantError):
        node._guard_join(view, "test")
    lax = DcdsNode(DcdsParams(strict_invariant=False))
    lax.on_start(0, 1.0, 2, 1)
    lax._nbrs = {1}
    assert lax._guard_join(view, "test") is True
    assert lax.violations == 1


# ==========================================================================
# 4. kopuk çizge ve yalıtık düğüm
# ==========================================================================
def test_isolated_vertices_never_join_and_never_speak():
    g = mk([(0, 1), (1, 2)], n=6, k=2)  # 3,4,5 yalıtık
    res, holder = run_with_nodes(g)
    assert set(res.cover) <= {0, 1, 2}
    assert holder[3]._backbone is False
    for v in (3, 4, 5):
        assert v not in res.cover
    assert verify(g, res.cover).valid


def test_disconnected_components_are_solved_independently():
    """İki ayrı bileşen: her biri kendi içinde örtülür, aralarında köprü kurulmaz."""
    g = mk([(0, 1), (1, 2), (2, 3), (10, 11), (11, 12), (12, 13)], n=14, k=3)
    res = run_d_cds(g, max_rounds=200)
    v = verify(g, res.cover)
    assert v.valid
    left = {c for c in res.cover if c < 10}
    right = {c for c in res.cover if c >= 10}
    assert left and right
    assert is_connected_cover(g, set(res.cover))
    # bileşenler arası hiçbir düğüm "bağlantı" uğruna eklenmiş olamaz
    assert set(res.cover) <= set(range(14))
    for v_ in (4, 5, 6, 7, 8, 9):
        assert v_ not in res.cover


def test_edgeless_graph_converges_with_empty_cover():
    g = mk([], n=5, k=2)
    res = run_d_cds(g, max_rounds=10)
    assert res.cover == []
    assert res.messages == 0
    assert res.converged
    assert res.rounds == 1


def test_single_edge_and_single_node():
    assert run_d_cds(mk([], n=1, k=1), max_rounds=5).cover == []
    res = run_d_cds(mk([(0, 1)], k=1), max_rounds=20)
    assert res.cover == [0]  # eşit ağırlıkta küçük kimlik kalır
    assert verify(mk([(0, 1)], k=1), res.cover).valid


def test_clique_components_use_the_clique_rule():
    """Klikte omurga boştur; kural c<=2k iken en pahalıyı dışarıda bırakır."""
    tri = mk([(0, 1), (0, 2), (1, 2)], k=2, weight={0: 5.0, 1: 1.0, 2: 2.0})
    res, holder = run_with_nodes(tri)
    assert backbone_of(holder) == set()
    assert res.cover == [1, 2]  # en pahalı 0 dışarıda
    assert verify(tri, res.cover).valid
    # c > 2k: kapasite yüzünden herkes girmeli (K5, k=2 -> 10 kenar, 5*2=10)
    k5 = mk([(u, v) for u in range(5) for v in range(u + 1, 5)], k=2)
    res5 = run_d_cds(k5, max_rounds=60)
    assert res5.cover == [0, 1, 2, 3, 4]
    assert verify(k5, res5.cover).valid


# ==========================================================================
# 5. belirlenimcilik
# ==========================================================================
def test_same_graph_same_result_every_time():
    for g in random_suite(20):
        a = run_d_cds(g, max_rounds=300)
        b = run_d_cds(g, max_rounds=300)
        assert a.as_dict() == b.as_dict()
        assert a.owner == b.owner


def test_result_is_independent_of_poll_order():
    for g in random_suite(20):
        base = run_d_cds(g, max_rounds=300)
        rev = run_d_cds(g, max_rounds=300, poll_order=list(reversed(sorted(g.nodes))))
        rr = random.Random(4)
        shuffled = sorted(g.nodes)
        rr.shuffle(shuffled)
        shuf = run_d_cds(g, max_rounds=300, poll_order=shuffled)
        assert base.as_dict() == rev.as_dict() == shuf.as_dict()
        assert base.owner == rev.owner == shuf.owner


# ==========================================================================
# 6. iki atlama: dejenerasyon tuzağı
# ==========================================================================
def two_hop_probe_graph() -> CcvcGraph:
    """İki bileşen; 0 ile 5 düğümü ADAYDAN BAĞIMSIZ her istatistikte aynı.

    Bileşen A (0'ın komşuları BİRBİRİNE KOMŞU):   0-1, 0-2, 1-2, 1-3, 2-4, 3-4
    Bileşen B (5'in komşuları KOMŞU DEĞİL):       5-6, 5-7, 6-8, 6-9, 7-8, 7-9

    İkisinin de derecesi 2, komşu dereceleri {3,3}, iki atlama kümesi 2 elemanlı
    ve o kümenin dereceleri {2,2}, tüm ağırlıklar eşit. Tek fark 0'ın komşuları
    arasında kenar olması. Wu-Li buna bakar: 0 işaretlenmez, 5 işaretlenir.
    """
    return mk(
        [
            (0, 1),
            (0, 2),
            (1, 2),
            (1, 3),
            (2, 4),
            (3, 4),
            (5, 6),
            (5, 7),
            (6, 8),
            (6, 9),
            (7, 8),
            (7, 9),
        ],
        k=4,
    )


def candidate_independent_profile(g: CcvcGraph, v: int) -> Tuple:
    """Adaydan BAĞIMSIZ hesaplanabilecek her şey: derece, komşu/iki-atlama toplamları."""
    n1 = set(g.adj[v])
    n2 = set()
    for u in n1:
        n2 |= set(g.adj[u])
    n2 -= n1 | {v}
    return (
        len(n1),
        sorted(len(g.adj[u]) for u in n1),
        sorted(round(g.weight[u], 6) for u in n1),
        round(g.weight[v], 6),
        len(n2),
        sorted(len(g.adj[u]) for u in n2),
        round(sum(g.weight[u] for u in n2), 6),
        round(sum(g.weight[u] for u in n1), 6),
    )


def test_two_hop_use_is_candidate_conditional_not_a_shared_constant():
    """Dejenerasyon testi.

    Adaydan bağımsız bir iki-atlama özeti (toplam ağırlık, iki-atlama sayısı,
    derece dizisi...) kullanılsaydı, 0 ve 5 için aynı sabiti verirdi ve kol
    tek-atlama kuralına çökerdi. Aşağıdaki iki savın İKİSİ birden geçmeli:
    profiller birebir aynı, kararlar farklı.
    """
    g = two_hop_probe_graph()
    assert candidate_independent_profile(g, 0) == candidate_independent_profile(g, 5)
    res, holder = run_with_nodes(g)
    assert holder[0]._marked is False, "N(0) klik: işaretlenmemeliydi"
    assert holder[5]._marked is True, "N(5) klik değil: işaretlenmeliydi"
    assert holder[0]._backbone != holder[5]._backbone
    assert verify(g, res.cover).valid


def test_marking_reacts_to_a_single_two_hop_edge():
    """Tek bir iki-atlama kenarını silmek kararı çevirmeli (yerel profil sabitken)."""
    with_edge = mk([(0, 1), (0, 2), (1, 2), (1, 3), (2, 4), (3, 4)], k=4)
    without = mk([(0, 1), (0, 2), (1, 3), (2, 4), (3, 4)], k=4)
    _, h1 = run_with_nodes(with_edge)
    _, h2 = run_with_nodes(without)
    assert h1[0]._marked is False
    assert h2[0]._marked is True


def test_two_hop_knowledge_is_acquired_by_messages_not_assumed():
    """Tur 0'da düğümün iki atlama defteri BOŞ; bilgi yayınla gelir ve bedeli sayılır."""
    seen: Dict[int, Dict[int, object]] = {}

    class Peek(DcdsNode):
        def on_round(self, view):
            out = super().on_round(view)
            # o turun mesajları SİNDİRİLDİKTEN sonraki defter
            seen.setdefault(view.round, {})[view.me] = dict(self._led.adj)
            return out

    g = two_hop_probe_graph()
    res, _ = run_with_nodes(g, cls=Peek)
    assert all(d == {} for d in seen[0].values()), "tur 0'da iki atlama bilgisi olamaz"
    assert all(d for v, d in seen[1].items()), "tur 1'de komşu listeleri gelmiş olmalı"
    assert seen[1][0][1] == set(g.adj[1])
    assert seen[1][0][2] == set(g.adj[2])
    # iki atlama edinme bedeli: her düğüm bir kez yayın -> derece kadar mesaj
    assert res.messages_by_kind[TWO_HOP_DIGEST] == 2 * len(g.edges)
    REPORT["digest_cost"] = (res.messages_by_kind[TWO_HOP_DIGEST], 2 * len(g.edges))


def test_message_budget_is_reported_by_kind():
    g = two_hop_probe_graph()
    res = run_d_cds(g, max_rounds=200)
    kinds = res.messages_by_kind
    assert kinds[TWO_HOP_DIGEST] == 2 * len(g.edges)
    assert kinds[MARK_STATE] == 2 * len(g.edges)
    assert kinds.get(COVER_MEMBERSHIP, 0) >= 2 * len(g.edges)
    assert res.messages == sum(kinds.values())


# ==========================================================================
# 7. kalite: merkezi ve tam çözüme oran
# ==========================================================================
def test_quality_versus_central_greedies_and_exact():
    """Kalite kaydı. Negatif sonuç da sonuçtur; burada oran ÖLÇÜLÜR ve sınırlanır."""
    rows = []
    for g in random_suite(48):
        if not g.edges:
            continue
        res = run_d_cds(g, max_rounds=300)
        v = verify(g, res.cover)
        assert v.valid
        ours = v.total_weight
        best_greedy = None
        for name in ("gccvc", "grccvc", "gwccvc"):
            c = central.solve(name, g, strict=False)
            if c.valid and (best_greedy is None or c.total_weight < best_greedy):
                best_greedy = c.total_weight
        ex = None
        if max((len(c) for c in graph_components(g)), default=0) <= 14:
            e = central.solve_exact(g, max_n=14, time_limit_s=20.0, strict=False)
            if e.valid and not e.timed_out:
                ex = e.total_weight
        rows.append((ours, best_greedy, ex))
    greedy_pairs = [(o, b) for o, b, _ in rows if b]
    exact_pairs = [(o, e) for o, _, e in rows if e]
    assert len(exact_pairs) >= 20, len(exact_pairs)
    r_greedy = sum(o / b for o, b in greedy_pairs) / len(greedy_pairs)
    r_exact = sum(o / e for o, e in exact_pairs) / len(exact_pairs)
    worst_exact = max(o / e for o, e in exact_pairs)
    REPORT["quality"] = {
        "instances_greedy": len(greedy_pairs),
        "instances_exact": len(exact_pairs),
        "mean_ratio_vs_best_central_greedy": round(r_greedy, 4),
        "mean_ratio_vs_exact": round(r_exact, 4),
        "worst_ratio_vs_exact": round(worst_exact, 4),
    }
    assert r_exact < 1.6, REPORT["quality"]
    assert r_greedy < 1.6, REPORT["quality"]


def test_quality_versus_the_trivial_upper_bound():
    """Omurga kenar örtmeyen düğüm ekliyor. Bu, kolu "kenarı olan herkesi al"
    çözümünün ötesine itiyor mu? İtiyorsa kol değersizdir ve bu RAPORLANIR.

    Karşılaştırma hem gerçek karelerde hem dar kapasiteli rastgele kümede yapılır.
    """
    out: Dict[str, object] = {}
    for tag, graphs in (
        ("frames", [
            graph_from_frame(fr, capacity_k=k, weight_scheme="unit")
            for k in (3, 4, 6)
            for fr in frames_subset(24)
        ]),
        ("random_tight", random_suite(48)),
    ):
        ratios = []
        ties = 0
        greedy_ties = 0
        dead_nodes = []
        cover_sizes = []
        for g in graphs:
            if not g.edges:
                continue
            res, holder = run_with_nodes(g, max_rounds=400)
            v = verify(g, res.cover)
            trivial = [x for x in g.nodes if g.degree(x) > 0]
            wt = g.total_weight(trivial)
            if wt <= 0:
                continue
            ratios.append(v.total_weight / wt)
            # ÖNEMLİ: hiçbir örnekte trivialden AĞIR olmamalı (aşağıda sınanır)
            assert v.total_weight <= wt + 1e-9, (g.edges, res.cover)
            if v.total_weight >= wt - 1e-9:
                ties += 1
                best = None
                for name in ("gccvc", "grccvc", "gwccvc"):
                    c = central.solve(name, g, strict=False)
                    if c.valid and (best is None or c.total_weight < best):
                        best = c.total_weight
                if best is not None and best >= wt - 1e-9:
                    greedy_ties += 1
            owners = set(res.owner.values())
            backbone = backbone_of(holder)
            dead = [x for x in res.cover if x not in owners]
            dead_nodes.append((len(dead), len([x for x in dead if x in backbone])))
            cover_sizes.append(len(res.cover))
        out[tag] = {
            "instances": len(ratios),
            "mean_ratio_vs_trivial": round(sum(ratios) / len(ratios), 4),
            "worst_ratio_vs_trivial": round(max(ratios), 4),
            "ties_with_trivial": ties,
            "central_greedy_also_ties": greedy_ties,
            "mean_cover_size": round(sum(cover_sizes) / len(cover_sizes), 2),
            "mean_cover_nodes_owning_no_edge": round(
                sum(a for a, _ in dead_nodes) / len(dead_nodes), 3
            ),
            "of_which_backbone": round(
                sum(b for _, b in dead_nodes) / len(dead_nodes), 3
            ),
        }
    REPORT["trivial"] = out
    # sert kural: kol hiçbir örnekte "kenarı olan herkesi al" çözümünden AĞIR olamaz
    for tag, row in out.items():
        assert row["worst_ratio_vs_trivial"] <= 1.0, (tag, row)
        assert row["mean_ratio_vs_trivial"] < 1.0, (tag, row)
    # gerçek karelerde beraberlik de olmamalı; dar kapasiteli rastgele kümede
    # beraberlikler SAYILIR ve raporlanır (negatif sonuç saklanmaz)
    assert out["frames"]["ties_with_trivial"] == 0, out["frames"]


def test_quality_on_real_frames_versus_central():
    rows = []
    for k in (3, 4, 6):
        for fr in frames_subset(24):
            g = graph_from_frame(fr, capacity_k=k, weight_scheme="unit")
            res = run_d_cds(g, max_rounds=300)
            v = verify(g, res.cover)
            assert v.valid
            c = central.solve_grccvc(g, strict=False)
            if c.valid and c.total_weight > 0:
                rows.append((k, v.total_weight / c.total_weight, res.messages, res.rounds))
    assert len(rows) >= 60
    ratio = sum(r for _, r, _, _ in rows) / len(rows)
    REPORT["frames"] = {
        "instances": len(rows),
        "mean_ratio_vs_grccvc": round(ratio, 4),
        "mean_messages": round(sum(m for _, _, m, _ in rows) / len(rows), 1),
        "mean_rounds": round(sum(t for _, _, _, t in rows) / len(rows), 2),
    }
    assert ratio < 1.5, REPORT["frames"]


# ==========================================================================
# 8. kapasite: artırıcı yol
# ==========================================================================
def tight_capacity_case() -> CcvcGraph:
    """k=1: her örtü düğümü tam olarak BİR kenar taşıyabilir.

    8 kenar, dolayısıyla 8 sahip gerekir; kenarı yalnız iki ucundan biri
    alabildiği için kapasite ancak uzun bir devir zinciriyle dengelenir.
    """
    return mk(
        [(0, 1), (0, 3), (0, 5), (1, 6), (2, 3), (2, 5), (6, 7)], n=8, k=1
    )


def test_tight_capacity_forces_augmenting_path_and_still_passes_gates():
    g = tight_capacity_case()
    res = run_d_cds(g, max_rounds=300)
    v = verify(g, res.cover)
    assert res.messages_by_kind.get(SHED_REQUEST, 0) > 0, "artırıcı yol hiç ateşlenmedi"
    assert res.messages_by_kind.get(SHED_ACCEPT, 0) > 0, "hiç devir kabulü olmadı"
    assert res.converged
    assert v.valid, v.as_dict()
    assert len(res.owner) == len(g.edges)
    load: Dict[int, int] = {}
    for _, o in res.owner.items():
        load[o] = load.get(o, 0) + 1
    assert all(c <= g.capacity_k for c in load.values()), load
    REPORT["tight"] = {
        "shed_requests": res.messages_by_kind.get(SHED_REQUEST, 0),
        "shed_accepts": res.messages_by_kind.get(SHED_ACCEPT, 0),
        "rounds": res.rounds,
    }


def test_hop_limit_is_the_knob_that_decides_solvability():
    """Sınırlı uzunluk gerçekten SINIR: 1 atlamayla çözülemeyen örnek 4 atlamayla çözülür."""
    g = tight_capacity_case()
    short = run_d_cds(g, params=DcdsParams(augment_max_hops=1), max_rounds=300)
    long = run_d_cds(g, params=DcdsParams(augment_max_hops=4), max_rounds=300)
    assert not verify(g, short.cover).capacity_feasible
    assert verify(g, long.cover).valid
    REPORT["hop_knob"] = (
        verify(g, short.cover).as_dict()["capacity_feasible"],
        verify(g, long.cover).as_dict()["capacity_feasible"],
    )


def test_capacity_is_never_exceeded_anywhere():
    for g in random_suite(48):
        res = run_d_cds(g, max_rounds=300)
        load: Dict[int, int] = {}
        for _, o in res.owner.items():
            load[o] = load.get(o, 0) + 1
        assert all(c <= g.capacity_k for c in load.values()), (g.edges, load)
        assert set(load) <= set(res.cover), "örtü dışı düğüm kenar sahiplenemez"


def test_saturated_peer_is_absorbed_by_the_other_endpoint():
    """Doymuş örtü ucunun kenarını, örtü dışındaki diğer uç devralır (yük emme)."""
    # 0 yıldızın merkezi, k=2: 0 iki kenar taşır, üçüncü kenarı yaprak almalı
    g = mk([(0, 1), (0, 2), (0, 3), (1, 2)], k=2)
    res = run_d_cds(g, max_rounds=200)
    v = verify(g, res.cover)
    assert v.valid, v.as_dict()
    assert 3 in res.cover, "kenar (0,3) için 3 örtüye girmeliydi"
    assert res.owner[edge_key(0, 3)] == 3


# ==========================================================================
# 9. eskime altında güvenlik
# ==========================================================================
def _lonely_view(round_: int, score_age: Optional[int]) -> LocalView:
    """Tek komşulu, örtüde OLMAYAN düğümün görüşü; komşu kaydı istenen yaşta."""
    nbr = NeighborRecord(
        node=1,
        weight=1.0,
        uncovered_degree=1,
        remaining_capacity=2,
        in_cover=False,
        score=(0.0, 0.0, 0, 1),  # komşunun skoru BENDEN İYİ
        age_rounds=0 if score_age is None else score_age,
    )
    return LocalView(
        me=0,
        round=round_,
        weight=1.0,
        capacity_k=2,
        remaining_capacity=2,
        in_cover=False,
        incident={1: EdgeLocal(other=1)},
        neighbors={1: nbr},
    )


def _node_with_stale_peer(stale: bool) -> Tuple[DcdsNode, NodeDecision]:
    node = DcdsNode(DcdsParams(strict_invariant=True))
    node.on_start(0, 1.0, 2, 1)
    node._nbrs = {1}
    node._led.in_cover[2] = True  # omurga komşusu var -> bitişiklik sağlanmış
    node._nbrs = {1, 2}
    node._led.score[1] = (0.0, 0.0, 0, 1)
    node._led.score_round[1] = 0 if stale else 9
    view = LocalView(
        me=0,
        round=10,
        weight=1.0,
        capacity_k=2,
        remaining_capacity=2,
        in_cover=False,
        incident={1: EdgeLocal(other=1), 2: EdgeLocal(other=2, covered=True, owner=2)},
        neighbors={},
    )
    msgs, dec = node._steady(view)
    return node, dec


def test_stale_neighbour_score_is_resolved_towards_covering():
    """Komşunun skoru TAZE ve daha iyiyse bekle; BAYATSA kendin katıl.

    Bayat bilgiye güvenip beklemek kenarı açıkta bırakabilir (güvenlik ihlali);
    fazladan katılmak yalnız israftır.
    """
    _, fresh = _node_with_stale_peer(stale=False)
    _, stale = _node_with_stale_peer(stale=True)
    assert fresh.join_cover is False, "taze ve daha iyi skorlu komşu varken katılmamalı"
    assert stale.join_cover is True, "bayat bilgi altında güvenli taraf KATILMAKTIR"


def test_unknown_two_hop_adjacency_is_conservative_towards_marking():
    """Komşuların komşu olup olmadığı bilinmiyorsa 'komşu değil' sayılır -> işaretle."""
    node = DcdsNode()
    node.on_start(0, 1.0, 2, 2)
    node._nbrs = {1, 2}
    assert node.marking_rule() is True  # defter boş: bilinmiyor -> işaretle
    node._led.adj[1] = {0, 2}
    node._led.adj[2] = {0, 1}
    assert node.marking_rule() is False  # artık biliyor: N(0) klik


def test_unknown_closed_neighbourhood_blocks_pruning():
    """N[u] bilinmiyorsa budama yapılmaz: omurga büyür ama bağlılık riske girmez."""
    node = DcdsNode()
    node.on_start(0, 5.0, 2, 2)
    node._nbrs = {1, 2}
    node._marked = True
    node._led.marked[1] = True
    node._led.weight[1] = 1.0  # 1 daha yüksek öncelikli (ucuz)
    assert node.pruned() is False  # N[1] bilinmiyor -> budama yok
    node._led.adj[1] = {0, 1, 2}
    assert node.pruned() is True  # N[0] ⊆ N[1] ve 1 daha ucuz -> budan


def test_cover_membership_belief_is_monotone():
    """Örtü üyeliği tek yönlüdür; bayat 'evet' yanlışa dönmez, bu yüzden kapı güvenli."""
    node = DcdsNode()
    node.on_start(0, 1.0, 2, 1)
    node._nbrs = {1}
    view = LocalView(
        me=0,
        round=5,
        weight=1.0,
        capacity_k=2,
        remaining_capacity=2,
        in_cover=False,
        incident={1: EdgeLocal(other=1)},
        neighbors={},
        inbox=[
            Message(COVER_MEMBERSHIP, 1, None, {"weight": 1.0, "in_cover": True}, 4),
            Message(COVER_MEMBERSHIP, 1, None, {"weight": 1.0, "in_cover": False}, 4),
        ],
    )
    node._ingest(view)
    assert node._believes_cover(1) is True


# ==========================================================================
# 10. yalıtım: protokol örneği hiçbir küresel tutamaç taşımaz
# ==========================================================================
def test_node_instance_holds_no_engine_graph_or_peer_reference():
    g = random_graph(7, 9, 0.4, 3)
    res, holder = run_with_nodes(g)
    banned = (CcvcGraph, RoundEngine, DcdsNode, LocalView)
    for v, node in holder.items():
        for name, value in vars(node).items():
            assert not isinstance(value, banned), (v, name, type(value))
            if isinstance(value, dict):
                for kk, vv in value.items():
                    assert not isinstance(vv, banned), (v, name, kk)
            if isinstance(value, (list, tuple, set)):
                for vv in value:
                    assert not isinstance(vv, banned), (v, name)
    # iki düğümün defteri aynı nesne olamaz
    nodes = sorted(holder)
    assert holder[nodes[0]]._led is not holder[nodes[1]]._led


def test_two_instances_of_the_same_graph_do_not_share_state():
    g = random_graph(11, 8, 0.5, 3)
    _, h1 = run_with_nodes(g)
    _, h2 = run_with_nodes(g)
    assert h1[0] is not h2[0]
    assert backbone_of(h1) == backbone_of(h2)




# ==========================================================================
# 12. merkezi kâhin: 2x2 tasarımın dördüncü gözü
# ==========================================================================
def test_specs_export_matches_harness_contract():
    """ccvc/experiment.py `SPECS` ile keşfediyor: (etiket, callable(graph)->RunResult)."""
    labels = [lab for lab, _ in SPECS]
    assert labels[0] == "d_cds", labels
    assert "cds_central" in labels
    assert len(set(labels)) == len(labels)
    g = random_graph(3, 8, 0.4, 3)
    for lab, fn in SPECS:
        rr = fn(g)
        assert hasattr(rr, "cover") and hasattr(rr, "messages") and hasattr(rr, "rounds")
        assert verify(g, rr.cover).vertex_cover, lab


def test_oracle_uses_the_same_backbone_as_the_distributed_arm():
    """Kâhin ile dağıtık kol AYNI çekirdeği çağırır: omurga birebir aynı olmalı.

    Bu, "aynı işaretleme, aynı budama, aynı öncelik" savının kanıtıdır. Aradaki
    fark yalnız bilgi ve zamanlamadır, kural değil.
    """
    for g in random_suite(48):
        res, holder = run_with_nodes(g, max_rounds=400)
        _, backbone, _, _ = cds_central_cover(g)
        assert backbone == backbone_of(holder), g.edges
        assert backbone == ref_wu_li(g), g.edges


def test_oracle_passes_all_three_gates():
    for g in random_suite(48):
        rr = solve_cds_central(g)
        v = verify(g, rr.cover)
        assert v.valid, (g.edges, g.capacity_k, v.as_dict())
        assert rr.messages == 0 and rr.rounds == 0
    for k in (3, 4, 6):
        for fr in frames_subset(24):
            g = graph_from_frame(fr, capacity_k=k, weight_scheme="unit")
            if not solution_can_exist(g):
                continue
            assert verify(g, solve_cds_central(g).cover).valid, (k,)


def test_oracle_is_deterministic():
    for g in random_suite(20):
        assert solve_cds_central(g).as_dict() == solve_cds_central(g).as_dict()


def test_distributed_arm_never_beats_its_own_oracle():
    """Yerellik BEDELDİR. Dağıtık kol kendi kâhinini geçiyorsa bir şey yanlıştır.

    Kâhin aynı stratejiyi tam bilgiyle koşar; dağıtık kol ondan iyi olamaz.
    Beraberlik olabilir (kâhinin de aç gözlü olduğu yerlerde), ama ÜSTÜNLÜK olamaz.
    """
    worse = ties = 0
    ratios = []
    graphs = list(random_suite(48))
    graphs += [
        graph_from_frame(fr, capacity_k=k, weight_scheme=ws, seed=sd)
        for k in (3, 4, 6)
        for ws in ("unit", "random")
        for sd in (0, 1, 2)
        for fr in frames_subset(12)
    ]
    for g in graphs:
        if not g.edges or not solution_can_exist(g):
            continue
        oracle = verify(g, solve_cds_central(g).cover)
        dist = verify(g, run_d_cds(g, max_rounds=400).cover)
        assert oracle.valid and dist.valid
        assert dist.total_weight >= oracle.total_weight - 1e-9, (
            f"dağıtık kol kendi kâhinini geçti: {dist.total_weight} < "
            f"{oracle.total_weight} on {g.edges}"
        )
        ratios.append(dist.total_weight / oracle.total_weight)
        if abs(dist.total_weight - oracle.total_weight) < 1e-9:
            ties += 1
        else:
            worse += 1
    REPORT["locality_cost"] = {
        "instances": len(ratios),
        "mean_d_cds_over_oracle": round(sum(ratios) / len(ratios), 4),
        "worst": round(max(ratios), 4),
        "identical": ties,
        "distributed_worse": worse,
        "distributed_better": 0,
    }
    assert REPORT["locality_cost"]["mean_d_cds_over_oracle"] >= 1.0


def test_oracle_capacity_assignment_agrees_with_central_flow():
    """Kâhinin akış yardımcısı, merkezi modülün b-eşlemesiyle aynı kararı vermeli."""
    for g in random_suite(48):
        rr = solve_cds_central(g)
        cover = set(rr.cover)
        flow, owner = _max_assignment(g.edges, cover, g.capacity_k)
        ok, ref_owner = central.capacity_assignment(g, cover)
        assert ok == (flow == len(g.edges)), (g.edges, flow)
        if ok:
            assert set(owner) == set(g.edges)
            load: Dict[int, int] = {}
            for e, o in owner.items():
                assert o in e, (e, o)  # kenarı yalnız bir UCU sahiplenebilir
                load[o] = load.get(o, 0) + 1
            assert all(c <= g.capacity_k for c in load.values())


def test_two_by_two_factorial_strategy_versus_locality():
    """2x2: strateji etkisi ile yerellik bedeli AYRI AYRI ölçülür.

        onarım + merkezi  = central GRCCVC
        CDS    + merkezi  = solve_cds_central
        CDS    + dağıtık  = D-CDS
    """
    cells: Dict[int, Dict[str, float]] = {}
    for k in (3, 4, 6):
        gr, oc, di, n = [], [], [], 0
        for ws in ("unit", "random"):
            for sd in ((0,) if ws == "unit" else (0, 1, 2)):
                for fr in frames_subset(12):
                    g = graph_from_frame(fr, capacity_k=k, weight_scheme=ws, seed=sd)
                    if not solution_can_exist(g):
                        continue
                    e = central.solve_exact(g, max_n=18, time_limit_s=10.0, strict=False)
                    if not (e.valid and not e.timed_out):
                        continue
                    n += 1
                    c = central.solve_grccvc(g, strict=False)
                    gr.append(c.total_weight / e.total_weight)
                    oc.append(verify(g, solve_cds_central(g).cover).total_weight / e.total_weight)
                    di.append(verify(g, run_d_cds(g, max_rounds=400).cover).total_weight / e.total_weight)
        cells[k] = {
            "instances": n,
            "repair_central_grccvc": round(sum(gr) / n, 4),
            "cds_central_oracle": round(sum(oc) / n, 4),
            "cds_distributed": round(sum(di) / n, 4),
            "strategy_effect": round(sum(gr) / n - sum(oc) / n, 4),
            "locality_cost": round(sum(di) / n - sum(oc) / n, 4),
        }
        # strateji etkisi pozitif olmalı: CDS-önce, onarımdan iyi
        assert cells[k]["strategy_effect"] > 0, cells[k]
        # yerellik bedeli negatif OLAMAZ: dağıtık kol kâhinden iyi olamaz
        assert cells[k]["locality_cost"] >= -1e-9, cells[k]
    REPORT["two_by_two"] = cells



# ==========================================================================
# 13. özet (koşum sonunda -s ile görünür)
# ==========================================================================
def test_zz_report():
    for key in ("cds_components", "quality", "frames", "tight", "hop_knob",
                "trivial", "two_by_two", "locality_cost"):
        assert key in REPORT, f"{key} ölçülmedi"
    print("\n--- D-CDS ölçüm defteri ---")
    for k, v in REPORT.items():
        print(f"{k}: {v}")
