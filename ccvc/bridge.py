#!/usr/bin/env python3
"""Simülatör çizgesi -> CCVC girdisi köprüsü (F0).

MDS_SKYFABRIC her karede düğüm konumu + kenar listesi üretiyor; CCVC çözücüleri
düğüm ağırlığı + kenar listesi bekliyor. Bu modül ikisini bağlar ve CCVC'nin üç
kısıtını programatik doğrular.

Ağırlık şemaları (deneyde bağımsız değişken):
  unit      w=1, saf küme boyutu
  degree    w=derece, yüksek dereceliyi seçmek pahalı
  invdeg    w=1/(1+derece), yüksek dereceliyi seçmek ucuz (greedy'ye yakın)
  rssi      w=komşulara ortalama yol kaybı (zayıf bağlı düğüm pahalı)
  random    w~U(1,100), Dagdeviren veri kümesindeki dağılıma yakın

Kapasite k düğüm başına sabit; CLI ile taranır.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Set, Tuple

Edge = Tuple[int, int]


def edge_key(u: int, v: int) -> Edge:
    """Yönsüz kenar için kanonik anahtar."""
    return (u, v) if u <= v else (v, u)


# --------------------------------------------------------------------------
# çizge
# --------------------------------------------------------------------------
@dataclass
class CcvcGraph:
    """CCVC örneği: düğümler, kenarlar, ağırlıklar, kapasite."""

    nodes: List[int]
    edges: List[Edge]
    weight: Dict[int, float]
    capacity_k: int
    adj: Dict[int, Set[int]] = field(default_factory=dict)
    pos: Dict[int, Tuple[float, float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.adj:
            self.adj = {n: set() for n in self.nodes}
            for u, v in self.edges:
                self.adj[u].add(v)
                self.adj[v].add(u)

    @property
    def max_degree(self) -> int:
        return max((len(a) for a in self.adj.values()), default=0)

    def degree(self, v: int) -> int:
        return len(self.adj[v])

    def total_weight(self, cover: Iterable[int]) -> float:
        return sum(self.weight[v] for v in cover)


def weights_for(
    nodes: Sequence[int],
    adj: Dict[int, Set[int]],
    scheme: str,
    pos: Dict[int, Tuple[float, float, float]] | None = None,
    seed: int = 0,
) -> Dict[int, float]:
    """Ağırlık şemasını uygula. Tüm şemalar pozitif değer döndürür."""
    rnd = random.Random(seed)
    if scheme == "unit":
        return {v: 1.0 for v in nodes}
    if scheme == "degree":
        return {v: float(1 + len(adj[v])) for v in nodes}
    if scheme == "invdeg":
        return {v: round(1.0 / (1 + len(adj[v])), 6) for v in nodes}
    if scheme == "random":
        return {v: round(rnd.uniform(1.0, 100.0), 4) for v in nodes}
    if scheme == "rssi":
        if pos is None:
            raise ValueError("rssi şeması konum ister")
        out = {}
        for v in nodes:
            if not adj[v]:
                out[v] = 100.0
                continue
            ds = [math.dist(pos[v], pos[u]) for u in adj[v]]
            out[v] = round(sum(ds) / len(ds), 4)  # ortalama mesafe ~ yol kaybı vekili
        return out
    raise ValueError(f"bilinmeyen ağırlık şeması: {scheme}")


def graph_from_frame(
    frame: dict,
    capacity_k: int,
    weight_scheme: str = "unit",
    edge_field: str = "edges_obs",
    seed: int = 0,
) -> CcvcGraph:
    """Simülatör karesinden (`*_frames.json` içindeki bir kayıt) CCVC örneği kurar.

    edge_field: 'edges_obs' bina-farkında çizge; mesafe-tek çizge için kareye
    'edges_free' yazılmışsa o da kullanılabilir.
    """
    pos_list = frame["pos"]
    nodes = list(range(len(pos_list)))
    pos = {i: tuple(p) for i, p in enumerate(pos_list)}
    edges = sorted({edge_key(int(u), int(v)) for u, v in frame[edge_field]})
    adj: Dict[int, Set[int]] = {n: set() for n in nodes}
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    w = weights_for(nodes, adj, weight_scheme, pos, seed)
    return CcvcGraph(
        nodes=nodes, edges=edges, weight=w, capacity_k=capacity_k, adj=adj, pos=pos
    )


def load_frames(path: str) -> Tuple[List[dict], dict]:
    """`results/**/mds_campus_seed0_frames.json` ya da iot_static_frames.json okur."""
    d = json.load(open(path))
    return d["frames"], {k: v for k, v in d.items() if k != "frames"}


def to_runtime_graph(g: CcvcGraph) -> Tuple[List[dict], List[Edge]]:
    """MWCCVC-MININET `normalize_runtime_graph` çıktısıyla aynı biçim.

    Çözücüler 1 tabanlı tamsayı kimlik bekliyor, burada +1 kaydırılır.
    """
    vertex_data = [{"id": v + 1, "weight": float(g.weight[v])} for v in g.nodes]
    edge_data = [(u + 1, v + 1) for u, v in g.edges]
    return vertex_data, edge_data


# --------------------------------------------------------------------------
# doğruluk kapıları — her karede koşar, ihlal hatadır
# --------------------------------------------------------------------------
def is_vertex_cover(g: CcvcGraph, cover: Set[int]) -> bool:
    """Her kenarın en az bir ucu örtüde mi."""
    return all(u in cover or v in cover for u, v in g.edges)


def uncovered_edges(g: CcvcGraph, cover: Set[int]) -> List[Edge]:
    return [(u, v) for u, v in g.edges if u not in cover and v not in cover]


def graph_components(g: CcvcGraph) -> List[Set[int]]:
    """G'nin bağlı bileşenleri (yalıtık düğümler tekil bileşen olarak gelir)."""
    left, out = set(g.nodes), []
    while left:
        start = next(iter(left))
        comp, stack = {start}, [start]
        while stack:
            x = stack.pop()
            for y in g.adj[x]:
                if y not in comp:
                    comp.add(y)
                    stack.append(y)
        out.append(comp)
        left -= comp
    return out


def is_connected_cover(g: CcvcGraph, cover: Set[int]) -> bool:
    """Örtü bağlılığı, BİLEŞEN BAZLI.

    Çizgenin kendisi çoğu karede kopuk (bkz. plan/PLAN_DCCVC.md §0.5), o yüzden
    "G[C] tek parça" şartı çözülemez bir istektir. Doğru şart: G'nin her bağlı
    bileşeni içinde, o bileşene düşen örtü parçası bağlı olmalı. Kenarsız
    bileşenler (yalıtık düğümler) örtüye hiç girmediği için sorun çıkarmaz.
    """
    if len(cover) <= 1:
        return True
    for comp in graph_components(g):
        part = cover & comp
        if len(part) <= 1:
            continue
        start = next(iter(part))
        seen, stack = {start}, [start]
        while stack:
            x = stack.pop()
            for y in g.adj[x]:
                if y in part and y not in seen:
                    seen.add(y)
                    stack.append(y)
        if seen != part:
            return False
    return True


def cover_components(g: CcvcGraph, cover: Set[int]) -> List[Set[int]]:
    """G[cover] bileşenleri."""
    left, out = set(cover), []
    while left:
        start = next(iter(left))
        comp, stack = {start}, [start]
        while stack:
            x = stack.pop()
            for y in g.adj[x]:
                if y in cover and y not in comp:
                    comp.add(y)
                    stack.append(y)
        out.append(comp)
        left -= comp
    return out


def capacity_feasible(g: CcvcGraph, cover: Set[int]) -> Tuple[bool, Dict[Edge, int]]:
    """Her kenar bir uca atanabiliyor mu, hiçbir düğüm k'yı aşmadan.

    Kenar-uç ataması iki taraflı b-eşlemedir ve TAM olarak akışla çözülür:

        kaynak -> kenar düğümü      kapasite 1   (her kenar bir kez atanır)
        kenar düğümü -> uç          kapasite 1   (yalnız örtüdeki uçlara)
        uç -> havuz                 kapasite k   (düğüm başına kapasite)

    Uygun ancak ve ancak maksimum akış = |E|. Edmonds-Karp yeterli, örneklerimizde
    kenar sayısı birkaç yüzü geçmiyor.

    NOT (2026-09-11): Buranın ilk sürümü artırıcı-yol sezgiseliydi ve YANLIŞ
    POZİTİF veriyordu; tahliye ettiği kenarı aynı düğüme geri koyup yükü k+1'e
    çıkarabiliyordu. Üçgen 0-1-2, C={0,1}, k=1 örneğinde "uygun" diyordu, oysa
    3 kenar 2 sahibe k=1 ile sığmaz. f1-central bunu yakaladı; akışla değiştirildi.
    Döndürür: (uygun mu, kenar -> sahip).
    """
    k = g.capacity_k
    if k <= 0:
        return (len(g.edges) == 0), {}
    # örtü değilse kapasiteye bakmanın anlamı yok
    for u, v in g.edges:
        if u not in cover and v not in cover:
            return False, {}
    if not g.edges:
        return True, {}

    m = len(g.edges)
    # düğüm numaralandırma: 0 = kaynak, 1..m = kenarlar, m+1.. = örtü düğümleri, son = havuz
    cover_list = sorted(cover)
    cover_idx = {v: m + 1 + i for i, v in enumerate(cover_list)}
    sink = m + 1 + len(cover_list)
    n_nodes = sink + 1

    # kapasiteli yönlü çizge, kalıntı kenarlarıyla
    cap: List[Dict[int, int]] = [dict() for _ in range(n_nodes)]

    def add(a: int, b: int, c: int) -> None:
        cap[a][b] = cap[a].get(b, 0) + c
        cap[b].setdefault(a, 0)

    for i, (u, v) in enumerate(g.edges, start=1):
        add(0, i, 1)
        for endpoint in (u, v):
            if endpoint in cover_idx:
                add(i, cover_idx[endpoint], 1)
    for v in cover_list:
        add(cover_idx[v], sink, k)

    # Edmonds-Karp
    flow = 0
    while True:
        prev = [-1] * n_nodes
        prev[0] = 0
        queue = [0]
        while queue and prev[sink] == -1:
            nxt = []
            for a in queue:
                for b, c in cap[a].items():
                    if c > 0 and prev[b] == -1:
                        prev[b] = a
                        nxt.append(b)
            queue = nxt
        if prev[sink] == -1:
            break
        # artırıcı yol boyunca darboğaz (tüm kapasiteler 1 ya da k, yine de hesapla)
        bottleneck = float("inf")
        node = sink
        while node != 0:
            bottleneck = min(bottleneck, cap[prev[node]][node])
            node = prev[node]
        node = sink
        while node != 0:
            cap[prev[node]][node] -= bottleneck
            cap[node][prev[node]] += bottleneck
            node = prev[node]
        flow += bottleneck

    if flow != m:
        return False, {}

    owner: Dict[Edge, int] = {}
    idx_to_cover = {i: v for v, i in cover_idx.items()}
    for i, e in enumerate(g.edges, start=1):
        for b, c in cap[i].items():
            if b in idx_to_cover and c == 0:  # kapasite 1'di, tükendiyse akış buradan geçti
                owner[e] = idx_to_cover[b]
                break
    return True, owner


@dataclass
class Verdict:
    """Bir çözümün üç kapıdan geçip geçmediği."""

    vertex_cover: bool
    connected: bool
    capacity_feasible: bool
    total_weight: float
    cover_size: int
    uncovered: int
    components: int
    owner: Dict[Edge, int] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.vertex_cover and self.connected and self.capacity_feasible

    def as_dict(self) -> dict:
        return {
            "valid": self.valid,
            "vertex_cover": self.vertex_cover,
            "connected": self.connected,
            "capacity_feasible": self.capacity_feasible,
            "total_weight": round(self.total_weight, 4),
            "cover_size": self.cover_size,
            "uncovered": self.uncovered,
            "components": self.components,
        }


def verify(g: CcvcGraph, cover: Iterable[int]) -> Verdict:
    """Üç doğruluk kapısını birden koşar. Her karede çağrılmalı."""
    cov = set(cover)
    vc = is_vertex_cover(g, cov)
    conn = is_connected_cover(g, cov)
    feas, owner = capacity_feasible(g, cov) if vc else (False, {})
    return Verdict(
        vertex_cover=vc,
        connected=conn,
        capacity_feasible=feas,
        total_weight=g.total_weight(cov),
        cover_size=len(cov),
        uncovered=len(uncovered_edges(g, cov)),
        components=len(cover_components(g, cov)),
        owner=owner,
    )


# --------------------------------------------------------------------------
# k için alt sınır: kapasite yüzünden çözümün var olabilmesi
# --------------------------------------------------------------------------
def min_feasible_k_bound(g: CcvcGraph) -> int:
    """Kapasite kısıtının hiç çözümü olabilmesi için gereken kaba alt sınır.

    Bir kenar yalnız iki ucundan biri tarafından sahiplenilebildiği için,
    tüm düğümler örtüde olsa bile her v en fazla k kenar taşır: |E| <= k*|V|
    ve dahası derece d(v) olan bir v'nin komşularının hepsi doyduğunda
    v'nin kendisi en az d(v)-sum(k over neighbors) taşımak zorunda kalır.
    Burada yalnız basit ve doğru olan sınırı döndürüyoruz.
    """
    if not g.edges:
        return 0
    return max(1, math.ceil(len(g.edges) / max(1, len(g.nodes))))
