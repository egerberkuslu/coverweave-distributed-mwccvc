#!/usr/bin/env python3
"""Merkezi CCVC referans çözücüleri (F1).

MWCCVC'nin merkezi greedy'lerinin (`backend/app/algorithms.py`) bu depoya
determinist ve bileşen bazlı portu. Dağıtık kolların (D-REPAIR, D-CDS) karşısına
konacak taban budur; ayrıca küçük örneklerde tam (branch & bound) çözüm optimum
gerçeği olarak koşar.

Problem. G=(V,E), düğüm ağırlığı w(v), düğüm başına kapasite k. Aranan C ⊆ V:
  1. örtü: her kenarın en az bir ucu C'de,
  2. bağlılık: G'nin HER BAĞLI BİLEŞENİ İÇİNDE C'nin o bileşene düşen parçası
     bağlı (bkz. plan/PLAN_DCCVC.md §0.5 -- veri çoğu karede kopuk, küresel bağlı
     örtü var olamaz),
  3. kapasite: her v ∈ C en fazla k komşu kenarı sahiplenir, her kenar tam
     olarak bir uca atanır,
  4. amaç: Σ w(v) en küçük.

Akış (her bağlı bileşen için ayrı, sonuç bileşen çözümlerinin birleşimi):
    greedy seçim -> artık kenarları zorla örtme -> bağlılık onarımı
    (Dijkstra + birleşim-bul MST) -> kapasite yükseltmesi -> üç kapı doğrulaması.
Kenarsız bileşenler (yalıtık düğümler) hiç işlenmez, örtüye asla girmez.

--------------------------------------------------------------------------
DETERMINISM DEVIATIONS
--------------------------------------------------------------------------
Kaynak kod eşitlikleri paylaşılan bir RNG ile bozuyor (`random_choice`,
algorithms.py 623-627). Tekrar üretilebilirlik keyfi bir RNG'ye sadakatten daha
değerli olduğu için her rastgelelik determinist bir kuralla değiştirildi. Aynı
girdi her koşumda bit birebir aynı çıktıyı verir (bkz. test_central.py).

D1. `solve_gccvc` düğüm seçimi (algorithms.py 648-655). Kaynak: en büyük
    örtülmemiş derece, eşitlikte en küçük ağırlık, kalan eşitlikte RASTGELE.
    Burada: son eşitlik bozucu en küçük düğüm kimliği, yani
    min (-örtülmemiş_derece, ağırlık, kimlik).

D2. `solve_grccvc` düğüm seçimi (algorithms.py 705-713). Kaynak: en küçük oran
    w(v)/Σ w(komşu), eşitlikte en küçük ağırlık, kalan eşitlikte RASTGELE.
    Burada: min (oran, ağırlık, kimlik).

D3. `solve_gwccvc` düğüm seçimi (algorithms.py 757-765). Kaynak: en küçük
    ağırlık, eşitlikte en büyük örtülmemiş derece, kalan eşitlikte RASTGELE.
    Burada: min (ağırlık, -örtülmemiş_derece, kimlik).

D4. `solve_grccvc` kenar sırası (algorithms.py 717). Kaynak: `rnd.shuffle`.
    Burada: komşu kimliği artan sırada. Karıştırmanın "yansız" determinist
    karşılığı yok; en yalın ve açıklanabilir sabit sıra seçildi.

D5. Komşu taraması. Kaynak `graph.adj[v]` bir KÜME üzerinde dönüyor
    (algorithms.py 130, 145, 158); küme sırası veri yapısının geçmişine bağlı.
    Burada her komşu listesi önce kimliğe göre sıralanır, algoritmaya özgü
    sıralama bunun üstüne KARARLI (stable) uygulanır. Bu özellikle `gwccvc`
    kenar sıralamasını (algorithms.py 768-774, yalnız BEYAZ-önce anahtarı)
    tam belirli hale getirir.

D6. Küme üzerinden "herhangi bir eleman". Kaynak birkaç yerde
    `next(iter(some_set))` kullanıyor (algorithms.py 171, 330). Burada her
    yerde `min(...)`, yani en küçük kimlik.

D7. Köprü sıralaması (algorithms.py 456-459). Kaynak yalnız maliyete göre
    sıralıyor, eşit maliyetler liste sırasına düşüyor. Burada anahtar
    (maliyet, bileşen_i, bileşen_j, yol) -- tam sıralı.

D8. `force_cover_remaining` (algorithms.py 608-611) `list(cover_set)` üzerinde
    dönüyor. Burada `sorted(cover)`.

Bunların hiçbiri algoritmanın yapısını değiştirmez; yalnız eşitlik anında hangi
düğümün seçileceğini sabitler.

--------------------------------------------------------------------------
mark_red_nodes BULGUSU (algorithms.py 525-540)
--------------------------------------------------------------------------
Kaynak fonksiyon iki şey yapıyor:
  (a) örtülmemiş derecesi <= 1 olan her BEYAZ düğümü KIRMIZI boyar,
  (b) örtülmemiş derecesi k'yı aşan bir BEYAZ düğümün, örtülmemiş derecesi <= 1
      olan BEYAZ komşularını KIRMIZI boyar.
`get_candidate_pool` (algorithms.py 558-562) ise çizgede TEK BİR kırmızı düğüm
varsa bütün beyaz düğümleri aday havuzundan atar. Yani kırmızı boyama küresel
bir önceliklendirme anahtarıdır; bu davranış aynen korunmuştur.

İki denetim bulgusu:
  * Fonksiyon `cover_set` argümanını kullanmıyor (algorithms.py 526: `_ = cover_set`).
  * (b) dalı KANITLANABİLİR ÖLÜ KOD. (b)'nin kırmızıya boyadığı her komşu, tanım
    gereği örtülmemiş derecesi <= 1 olan BEYAZ bir düğümdür; (a) dalı zaten
    bütün BEYAZ düğümleri tarayıp aynı koşulla kırmızıya boyar. Döngü sırası da
    sonucu değiştirmez: KIRMIZI'ya boyamak `uncovered_degree`'yi etkilemez
    (o yalnız SİYAH komşuları eler, algorithms.py 128-138), dolayısıyla döngü
    boyunca hiçbir düğümün örtülmemiş derecesi değişmez. Komşu daha önce
    gezildiyse (a) onu zaten boyamıştır; daha sonra gezilecekse (b) erken
    boyar ama (a) yine aynı sonucu verirdi. (b) çıkarıldığında sabit nokta aynı.
    Dolayısıyla `capacity_k` parametresi de gereksizdir.

Burada TEMİZLENMİŞ eşdeğer (`_mark_red_nodes`) kullanılır. Sadık sürüm
(`_mark_red_nodes_faithful`) da korunmuştur ve test_central.py rastgele
çizgelerde ikisinin BİREBİR aynı örtüyü ürettiğini doğrular.

--------------------------------------------------------------------------
GERİ-ÇEKİLME SİYASETİ: force_cover_remaining neden ve ne sıklıkta koşuyor
--------------------------------------------------------------------------
Ana greedy döngüsü (algorithms.py 668-674) aday havuzu boşalınca açıkta kenar
bırakarak çıkabiliyor, sonra `force_cover_remaining` (algorithms.py 601-620)
devreye giriyor. Kampüs karelerinde bu istisna değil, baskın yol: ölçülen
oranlar GCCVC %55,6, GRCCVC %48,4, GWCCVC %47,2 (432 uygun örnek, harness
ayarları). Denetim sonucu iki parçalı.

NEDEN ÇIKIYOR. `get_candidate_pool` bir düğümü ancak
`uncovered_degree(v, exclude_black=True) > 0` ise havuza alıyor
(algorithms.py 548), ve `uncovered_degree` SİYAH komşulara giden kenarları
saymıyor (algorithms.py 134-135). Bir düğüm seçildiğinde kapasitesi kadar kenar
sahipleniyor ve doyunca duruyor (algorithms.py 577-582); sahiplik ilk gelene
veriliyor ve BİR DAHA HİÇ gözden geçirilmiyor. Böylece "u SİYAH ve dolu, (u,v)
sahipsiz" durumundaki kenar, v için görünmez oluyor: v havuza girmiyor, havuz
boşalıyor, döngü çıkıyor.

KRİTİK OLGU (ölçüldü, 2077 açık kenar, hepsi). Döngü çıkışında açıkta kalan her
kenarın EN AZ BİR ucu zaten örtüde: %74,7'sinde iki uç da SİYAH, %25,3'ünde bir
uç SİYAH, iki ucu da siyah olmayan kenar HİÇ YOK (%0,0). Bunun kanıtı da var:
iki ucu da siyah olmayan sahipsiz bir kenar (u,v) olsaydı, v için
uncovered_degree(v, exclude_black=True) >= 1 olurdu ve v havuzda olurdu; havuz
dışı kalmasının tek yolu remaining[v] <= 0, o da yalnız v örtüdeyse olur (k>=1).
Yani ÖRTÜ ZATEN GEÇERLİ BİR TEPE ÖRTÜSÜDÜR. Döngü örtü eksikliğinden değil,
greedy'nin kendi sahiplik defterinin tükenmesinden çıkıyor.

BUNUN BEDELİ. Problem tanımı bir atamanın VAR OLMASINI istiyor, greedy'nin
bulduğu atamayı değil. Fallback ateşlendiği durumların %63,7-%67,9'unda örtü
maksimum akışa göre ZATEN kapasite-uygun; yani eklenen düğümlerin tamamı
gereksiz. Greedy doyan bir düğümün yükünü komşusuna kaydırmak yerine örtüye
yeni düğüm ekliyor.

İKİ SİYASET, İKİSİ DE ERİŞİLEBİLİR (`fallback_policy`):
  "eager"  VARSAYILAN, yayımlanmış algoritma OLDUĞU GİBİ: açıkta kenar varsa
           koşulsuz force_cover_remaining.
  "flow"   yayımlanmış algoritma kusuru giderilmiş hâli, açıkça seçilir.
           Önce maksimum akışa sorulur; örtü zaten
           kapasite-uygunsa hiçbir düğüm eklenmez. Seçim kuralına (skor, RED
           katmanı, sıralama) HİÇ DOKUNMAZ; yalnız gereksiz eklemeyi durdurur.

EŞLEŞTİRİLMİŞ ÖLÇÜM (2026-09-11): iki siyaset AYNI 432 örnekte koşuldu, yani bu
nedensel bir karşılaştırmadır, örnek seçimi etkisi değildir. "flow"un kazancı
oran cinsinden yalnız 0,008-0,018. Fallback ne kadar sık ateşlenirse ateşlensin
tabanın 1,3 civarı oranını AÇIKLAMIYOR. Bu yüzden varsayılan sadık sürümdür;
"flow" yalnız denetim izi olarak duruyor. Asıl maliyet bağlılık onarımında
(aşağıdaki evre ayrıştırması).

--------------------------------------------------------------------------
KAPASİTE: iki bağımsız maksimum akış, kasıtlı artıklık
--------------------------------------------------------------------------
Bu modülün ilk sürümü yazılırken `bridge.capacity_feasible` artırıcı yollu bir
SEZGİSELDİ ve yanlış pozitif veriyordu: tahliye ettiği kenarı aynı düğüme geri
koyup yükü k+1'e çıkarabiliyordu. Üçgen 0-1-2, C={0,1}, k=1 örneğinde "uygun"
diyordu, oysa 3 kenar 2 sahibe k=1 ile sığmaz. Bulgu bildirildi ve bridge.py
2026-09-11'de tam bir Edmonds-Karp b-eşlemesiyle değiştirildi; artık doğrudur.

Buradaki `_bmatching` (Dinic) yine de duruyor ve kapasite kapısının YETKİLİ
yanıtı odur. Gerekçe: iki bağımsız akış gerçeklemesi birbirini denetler. İkisi
aynı b-eşleme örgüsünü kuruyor ama farklı algoritmalarla çözüyor (Dinic'in
seviye çizgesi + engelleyici akışı, Edmonds-Karp'ın BFS artırıcı yolu), yani
ortak bir gerçekleme hatasına birlikte düşmeleri beklenmez. `_finish` her
çağrıda ikisini karşılaştırır ve ayrıştıklarında sonucun notlarına yazar;
test_central.py bunu birkaç yüz rastgele örnekte SERT HATA olarak sınar.
Üç kapı sonucu yine `bridge.verify`'dan taşınır, bridge'in kapasite yanıtı
ayrıca `bridge_capacity` alanında raporlanır. bridge.py bu modülden
DEĞİŞTİRİLMEDİ (salt okunur sözleşme).
"""
from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import bridge
from .bridge import CcvcGraph, Edge, Verdict, edge_key

__all__ = [
    "CcvcInfeasible",
    "CcvcSolverError",
    "CentralResult",
    "solve_gccvc",
    "solve_grccvc",
    "solve_gwccvc",
    "solve_exact",
    "solve",
    "SOLVERS",
    "capacity_assignment",
]


class CcvcInfeasible(Exception):
    """Verilen k altında hiçbir geçerli örtü yok (kapasite kısıtı çözümsüz)."""


class CcvcSolverError(Exception):
    """Çözücü bir kapıdan geçemeyen örtü üretti: bu bir hatadır, sonuç değil."""


# ==========================================================================
# sonuç nesnesi
# ==========================================================================
@dataclass
class CentralResult:
    """Bir merkezi çözücünün çıktısı ve üç doğruluk kapısının sonucu."""

    algorithm: str
    cover: Set[int]
    owner: Dict[Edge, int]
    total_weight: float
    cover_size: int
    vertex_cover: bool
    connected: bool
    capacity_feasible: bool
    feasible: bool = True
    status: str = "ok"
    bridge_capacity: Optional[bool] = None
    bridge_verdict: Optional[Verdict] = None
    time_ms: float = 0.0
    timed_out: bool = False
    exact: bool = False
    fallback_policy: Optional[str] = None
    phase: Dict[int, str] = field(default_factory=dict)
    weight_by_phase: Dict[str, float] = field(default_factory=dict)
    count_by_phase: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.vertex_cover and self.connected and self.capacity_feasible

    def as_dict(self) -> dict:
        """Determinist, süre içermeyen özet (tekrar üretilebilirlik testi bunu kullanır)."""
        return {
            "algorithm": self.algorithm,
            "status": self.status,
            "feasible": self.feasible,
            "valid": self.valid,
            "vertex_cover": self.vertex_cover,
            "connected": self.connected,
            "capacity_feasible": self.capacity_feasible,
            "bridge_capacity": self.bridge_capacity,
            "total_weight": round(self.total_weight, 6),
            "cover_size": self.cover_size,
            "cover": sorted(self.cover),
            "owner": sorted((list(e), o) for e, o in self.owner.items()),
            "timed_out": self.timed_out,
            "exact": self.exact,
            "fallback_policy": self.fallback_policy,
            "phase": sorted(self.phase.items()),
            "weight_by_phase": {k: round(v, 6) for k, v in sorted(self.weight_by_phase.items())},
            "count_by_phase": dict(sorted(self.count_by_phase.items())),
            "notes": list(self.notes),
        }


# ==========================================================================
# kapasite: iki taraflı b-eşleme, Dinic maksimum akış
# ==========================================================================
class _Dinic:
    """Küçük örnekler için yinelemesiz (iteratif) Dinic. Özyineleme sınırı yok."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.to: List[int] = []
        self.cap: List[int] = []
        self.head: List[List[int]] = [[] for _ in range(n)]

    def add(self, u: int, v: int, cap: int) -> int:
        idx = len(self.to)
        self.to.append(v)
        self.cap.append(cap)
        self.head[u].append(idx)
        self.to.append(u)
        self.cap.append(0)
        self.head[v].append(idx + 1)
        return idx

    def max_flow(self, src: int, dst: int) -> int:
        to, cap, head = self.to, self.cap, self.head
        flow = 0
        while True:
            level = [-1] * self.n
            level[src] = 0
            queue = [src]
            qi = 0
            while qi < len(queue):
                u = queue[qi]
                qi += 1
                for eid in head[u]:
                    if cap[eid] > 0 and level[to[eid]] < 0:
                        level[to[eid]] = level[u] + 1
                        queue.append(to[eid])
            if level[dst] < 0:
                return flow
            it = [0] * self.n
            while True:  # engelleyici akis: tikanana dek artirici yol bul
                path: List[int] = []
                u = src
                found = False
                while True:
                    if u == dst:
                        found = True
                        break
                    if it[u] < len(head[u]):
                        eid = head[u][it[u]]
                        v = to[eid]
                        if cap[eid] > 0 and level[v] == level[u] + 1:
                            path.append(eid)
                            u = v
                        else:
                            it[u] += 1
                        continue
                    if u == src:
                        break
                    level[u] = -1  # cikmaz, bir daha girme
                    eid = path.pop()
                    u = to[eid ^ 1]
                    it[u] += 1
                if not found:
                    break
                push = min(cap[eid] for eid in path)
                for eid in path:
                    cap[eid] -= push
                    cap[eid ^ 1] += push
                flow += push


def _bmatching(
    edges: Sequence[Edge], cover: Set[int], k: int
) -> Tuple[bool, Dict[Edge, int]]:
    """Her kenarı örtüdeki bir ucuna ata, hiçbir düğüm k'yı aşmasın.

    Kaynak -> kenar (kap 1) -> uygun uç (kap 1) -> hedef (kap k) akışı;
    doygun akış ⟺ uygun atama. Döndürür: (uygun mu, kenar -> sahip).
    """
    if not edges:
        return True, {}
    if k <= 0:
        return False, {}
    for u, v in edges:
        if u not in cover and v not in cover:
            return False, {}
    if len(cover) * k < len(edges):
        return False, {}

    cover_ids = sorted(cover)
    cidx = {v: i for i, v in enumerate(cover_ids)}
    m = len(edges)
    src = 0
    e0 = 1
    c0 = e0 + m
    dst = c0 + len(cover_ids)
    din = _Dinic(dst + 1)
    arc: List[List[Tuple[int, int]]] = []  # kenar başına (ark kimliği, sahip)
    for i, (u, v) in enumerate(edges):
        din.add(src, e0 + i, 1)
        row: List[Tuple[int, int]] = []
        for end in (u, v):
            if end in cidx and all(end != o for _, o in row):
                row.append((din.add(e0 + i, c0 + cidx[end], 1), end))
        arc.append(row)
    for v in cover_ids:
        din.add(c0 + cidx[v], dst, k)

    if din.max_flow(src, dst) != m:
        return False, {}

    owner: Dict[Edge, int] = {}
    for i, e in enumerate(edges):
        for aid, end in arc[i]:
            if din.cap[aid] == 0:  # doygun => bu uç sahiplendi
                owner[e] = end
                break
    return True, owner


def capacity_assignment(
    g: CcvcGraph, cover: Iterable[int]
) -> Tuple[bool, Dict[Edge, int]]:
    """Kapasite kapısı, düzgün maksimum akışla. bridge.capacity_feasible'ın doğru sürümü."""
    return _bmatching(list(g.edges), set(cover), g.capacity_k)


# ==========================================================================
# bileşen ayrıştırma
# ==========================================================================
def _components(g: CcvcGraph) -> List[List[int]]:
    """G'nin bağlı bileşenleri, her biri kimliğe göre sıralı, dış liste de sıralı."""
    left = set(g.nodes)
    out: List[List[int]] = []
    while left:
        start = min(left)
        comp = {start}
        stack = [start]
        while stack:
            x = stack.pop()
            for y in sorted(g.adj[x]):
                if y not in comp:
                    comp.add(y)
                    stack.append(y)
        out.append(sorted(comp))
        left -= comp
    out.sort(key=lambda c: c[0])
    return out


def _subgraph(g: CcvcGraph, comp: Sequence[int]) -> CcvcGraph:
    """Bileşenin kendi CcvcGraph'ı (kenarlar sıralı, ağırlık ve k aynı)."""
    members = set(comp)
    edges = [e for e in g.edges if e[0] in members and e[1] in members]
    adj = {v: set(g.adj[v]) & members for v in comp}
    return CcvcGraph(
        nodes=list(comp),
        edges=edges,
        weight={v: g.weight[v] for v in comp},
        capacity_k=g.capacity_k,
        adj=adj,
        pos={v: g.pos[v] for v in comp if v in g.pos},
    )


# ==========================================================================
# greedy çekirdek: tek bir bağlı bileşen üstünde çalışır
# ==========================================================================
NodePicker = Callable[["_Component", bool], Optional[int]]
EdgeSorter = Callable[["_Component", int, bool], List[Tuple[int, Edge]]]


class _Component:
    """Bir bağlı bileşen üstünde greedy CCVC durumu (renk, kalan kapasite, örtü)."""

    def __init__(self, sub: CcvcGraph) -> None:
        self.g = sub
        self.nodes: List[int] = sorted(sub.nodes)
        self.adj: Dict[int, List[int]] = {v: sorted(sub.adj[v]) for v in self.nodes}
        self.w = sub.weight
        self.k = sub.capacity_k
        self.edges: List[Edge] = sorted(sub.edges)
        self.color: Dict[int, str] = {v: "WHITE" for v in self.nodes}
        self.remaining: Dict[int, int] = {v: self.k for v in self.nodes}
        self.covered: Set[Edge] = set()
        self.owner: Dict[Edge, int] = {}
        self.cover: Set[int] = set()
        self.origin: Dict[int, str] = {}  # dugum -> "greedy"|"fallback"|"bridge"|"escalate"

    # --- sorgular (algorithms.py 120-166 portu) -------------------------
    def has_uncovered(self) -> bool:
        return len(self.covered) < len(self.edges)

    def uncovered_degree(self, v: int, exclude_black: bool = True) -> int:
        c = 0
        for u in self.adj[v]:
            if edge_key(v, u) in self.covered:
                continue
            if exclude_black and self.color[u] == "BLACK":
                continue
            c += 1
        return c

    def sum_uncovered_neighbor_weights(
        self, v: int, allow_black: bool = False
    ) -> float:
        t = 0.0
        for u in self.adj[v]:
            if edge_key(v, u) in self.covered:
                continue
            if not allow_black and self.color[u] == "BLACK":
                continue
            t += self.w[u]
        return t

    def edge_candidates(
        self, v: int, allow_black: bool = False
    ) -> List[Tuple[int, Edge]]:
        """(komşu, kenar) adayları; taban sıra komşu kimliği artan (D5)."""
        out: List[Tuple[int, Edge]] = []
        for u in self.adj[v]:
            e = edge_key(v, u)
            if e in self.covered:
                continue
            if not allow_black and self.color[u] == "BLACK":
                continue
            out.append((u, e))
        return out

    # --- renklendirme (algorithms.py 525-562 portu) ---------------------
    def mark_red_nodes(self, faithful: bool = False) -> None:
        if faithful:
            self._mark_red_nodes_faithful()
        else:
            self._mark_red_nodes()

    def _mark_red_nodes(self) -> None:
        """Temizlenmiş eşdeğer: cover_set ve capacity_k gereksiz, (b) dalı ölü kod."""
        for v in self.nodes:
            if self.color[v] != "WHITE":
                continue
            if self.uncovered_degree(v, True) <= 1:
                self.color[v] = "RED"

    def _mark_red_nodes_faithful(self) -> None:
        """algorithms.py 525-540 birebir; denklik testi için tutuluyor."""
        for v in self.nodes:
            if self.color[v] != "WHITE":
                continue
            ud = self.uncovered_degree(v, True)
            if ud <= 1:
                self.color[v] = "RED"
                continue
            if ud > self.k:
                for u in self.adj[v]:
                    if self.color[u] == "WHITE" and self.uncovered_degree(u, True) <= 1:
                        self.color[u] = "RED"

    def candidate_pool(self, allow_black: bool = False) -> List[int]:
        """KIRMIZI varsa yalnız kırmızılar, yoksa beyazlar, yoksa griler (algorithms.py 541-562)."""
        red: List[int] = []
        white: List[int] = []
        gray: List[int] = []
        for v in self.nodes:
            if self.color[v] == "BLACK" or self.remaining[v] <= 0:
                continue
            if self.uncovered_degree(v, not allow_black) <= 0:
                continue
            if self.color[v] == "RED":
                red.append(v)
            elif self.color[v] == "WHITE":
                white.append(v)
            else:
                gray.append(v)
        if red:
            return red
        if white:
            return white
        return gray

    # --- seçim ve kenar sahiplenme (algorithms.py 569-599 portu) --------
    def cover_edges_from_node(
        self, v: int, sorter: EdgeSorter, allow_black: bool
    ) -> None:
        for u, e in sorter(self, v, allow_black):
            if self.remaining[v] <= 0:
                break
            if e in self.covered:
                continue
            self.covered.add(e)
            self.owner[e] = v
            self.remaining[v] -= 1
            if self.color[u] in ("WHITE", "RED"):
                self.color[u] = "GRAY"

    def select_node(
        self, v: int, sorter: EdgeSorter, allow_black: bool, phase: str = "greedy"
    ) -> None:
        self.color[v] = "BLACK"
        self.cover.add(v)
        self.origin.setdefault(v, phase)
        self.cover_edges_from_node(v, sorter, allow_black)

    def force_cover_remaining(self, picker: NodePicker, sorter: EdgeSorter) -> None:
        """algorithms.py 601-620; kapasitesi kalan örtü düğümleri önce, sonra yeni seçim."""
        for v in sorted(self.cover):  # D8
            if self.remaining[v] > 0:
                self.cover_edges_from_node(v, sorter, True)
        safety = 0
        while self.has_uncovered():
            v = picker(self, True)
            if v is None:
                break
            self.select_node(v, sorter, True, phase="fallback")
            safety += 1
            if safety > len(self.nodes):
                break

    # --- bağlılık onarımı (algorithms.py 394-482 portu) -----------------
    def cover_components(self) -> List[List[int]]:
        left = set(self.cover)
        out: List[List[int]] = []
        while left:
            start = min(left)  # D6
            comp = {start}
            stack = [start]
            while stack:
                x = stack.pop()
                for y in self.adj[x]:
                    if y in self.cover and y not in comp:
                        comp.add(y)
                        stack.append(y)
            out.append(sorted(comp))
            left -= comp
        out.sort(key=lambda c: c[0])
        return out

    def _shortest_path_between(
        self, comp_a: Sequence[int], comp_b: Sequence[int]
    ) -> Tuple[float, List[int]]:
        """Dijkstra: örtüdeki düğüm 0, yeni düğüm w(u) maliyetli (algorithms.py 406-440).

        Not: kaynaktaki `remaining <= 0` elemesi k >= 1 için ÖLÜ KOD -- örtü dışı
        bir düğümün kalan kapasitesi hiç eksilmez (yalnız sahiplenen düğümünki
        eksilir, o da örtüdedir). Yine de sadakat için korunuyor.
        """
        targets = set(comp_b)
        dist: Dict[int, float] = {}
        prev: Dict[int, int] = {}
        heap: List[Tuple[float, int]] = []
        for v in sorted(comp_a):
            dist[v] = 0.0
            heapq.heappush(heap, (0.0, v))
        while heap:
            cost, cur = heapq.heappop(heap)
            if cost > dist.get(cur, float("inf")):
                continue
            if cur in targets:
                path = [cur]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                path.reverse()
                return cost, path
            for u in self.adj[cur]:
                if u not in self.cover and self.remaining[u] <= 0:
                    continue
                step = 0.0 if u in self.cover else self.w[u]
                nc = cost + step
                if nc < dist.get(u, float("inf")):
                    dist[u] = nc
                    prev[u] = cur
                    heapq.heappush(heap, (nc, u))
        return float("inf"), []

    def add_path_to_cover(self, path: Sequence[int]) -> None:
        for v in path:
            if self.color[v] != "BLACK":
                self.color[v] = "BLACK"
                self.cover.add(v)
                self.origin.setdefault(v, "bridge")
            for u in self.adj[v]:
                if self.color[u] in ("WHITE", "RED"):
                    self.color[u] = "GRAY"

    def build_bridges(self) -> bool:
        """Bileşenler arası tüm çiftler Dijkstra + birleşim-bul MST (algorithms.py 442-474)."""
        comps = self.cover_components()
        if len(comps) <= 1:
            return False
        conns: List[Tuple[float, int, int, Tuple[int, ...]]] = []
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                cost, path = self._shortest_path_between(comps[i], comps[j])
                if path:
                    conns.append((cost, i, j, tuple(path)))
        if not conns:
            return False
        conns.sort()  # D7: (maliyet, i, j, yol) tam sıralı
        parent = list(range(len(comps)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        added = False
        groups = len(comps)
        for _cost, i, j, path in conns:
            ri, rj = find(i), find(j)
            if ri == rj:
                continue
            parent[rj] = ri
            groups -= 1
            self.add_path_to_cover(path)
            added = True
            if groups == 1:
                break
        return added

    def repair_connectivity(self) -> None:
        while len(self.cover_components()) > 1:
            if not self.build_bridges():
                break

    # --- kapasite yükseltmesi (kaynakta yok, eklendi) -------------------
    def escalate_capacity(self) -> Tuple[bool, Dict[Edge, int], int]:
        """Kapasite uygun olana dek örtüye bitişik en ucuz düğümü ekle.

        Kaynak greedy kendi kenar atamasını yaptığı için kapasite kapısından
        geçemeyen örtü döndürebiliyor. Örtüye düğüm eklemek kapasite
        uygunluğunu asla bozmaz (her kenarın sahip adayı kümesi yalnız büyür),
        bitişik ekleme bağlılığı da korur; bileşen bağlı olduğu için en kötü
        durumda tüm bileşene ulaşılır. Döndürür: (uygun mu, atama, eklenen).
        """
        added = 0
        while True:
            ok, owner = _bmatching(self.edges, self.cover, self.k)
            if ok:
                return True, owner, added
            cands = [
                v
                for v in self.nodes
                if v not in self.cover and any(u in self.cover for u in self.adj[v])
            ]
            if not cands:
                return False, {}, added
            v = min(cands, key=lambda x: (self.w[x], x))
            self.cover.add(v)
            self.color[v] = "BLACK"
            self.origin.setdefault(v, "escalate")
            added += 1


# ==========================================================================
# algoritmaya özgü seçim ve kenar sıralama kuralları
# ==========================================================================
def _pick_gccvc(c: _Component, allow_black: bool) -> Optional[int]:
    """En büyük örtülmemiş derece, sonra en küçük ağırlık, sonra kimlik (D1)."""
    pool = c.candidate_pool(allow_black)
    if not pool:
        return None
    return min(pool, key=lambda v: (-c.uncovered_degree(v, not allow_black), c.w[v], v))


def _sort_gccvc(c: _Component, v: int, allow_black: bool) -> List[Tuple[int, Edge]]:
    """Komşular (-örtülmemiş derece, ağırlık, kimlik) (algorithms.py 657-666)."""
    cands = c.edge_candidates(v, allow_black)
    cands.sort(key=lambda p: (-c.uncovered_degree(p[0], True), c.w[p[0]], p[0]))
    return cands


def _pick_grccvc(c: _Component, allow_black: bool) -> Optional[int]:
    """En küçük oran w(v)/Σw(örtülmemiş komşu), sonra ağırlık, sonra kimlik (D2)."""
    pool = c.candidate_pool(allow_black)
    if not pool:
        return None

    def key(v: int) -> Tuple[float, float, int]:
        denom = c.sum_uncovered_neighbor_weights(v, allow_black)
        ratio = float("inf") if denom <= 0 else c.w[v] / denom
        return (ratio, c.w[v], v)

    return min(pool, key=key)


def _sort_grccvc(c: _Component, v: int, allow_black: bool) -> List[Tuple[int, Edge]]:
    """Kaynakta rastgele karıştırma; burada komşu kimliği artan (D4)."""
    return c.edge_candidates(v, allow_black)


def _pick_gwccvc(c: _Component, allow_black: bool) -> Optional[int]:
    """En küçük ağırlık, sonra en büyük örtülmemiş derece, sonra kimlik (D3)."""
    pool = c.candidate_pool(allow_black)
    if not pool:
        return None
    return min(pool, key=lambda v: (c.w[v], -c.uncovered_degree(v, not allow_black), v))


def _sort_gwccvc(c: _Component, v: int, allow_black: bool) -> List[Tuple[int, Edge]]:
    """Önce BEYAZ komşular; taban sıra kimlik (algorithms.py 768-774, D5)."""
    cands = c.edge_candidates(v, allow_black)
    cands.sort(key=lambda p: (0 if c.color[p[0]] == "WHITE" else 1, p[0]))
    return cands


_RULES: Dict[str, Tuple[str, NodePicker, EdgeSorter]] = {
    "gccvc": ("GCCVC", _pick_gccvc, _sort_gccvc),
    "grccvc": ("GRCCVC", _pick_grccvc, _sort_grccvc),
    "gwccvc": ("GWCCVC", _pick_gwccvc, _sort_gwccvc),
}


# ==========================================================================
# greedy sürücü
# ==========================================================================
FALLBACK_POLICIES = ("eager", "flow")


def _greedy_component(
    sub: CcvcGraph,
    picker: NodePicker,
    sorter: EdgeSorter,
    *,
    faithful_red: bool = False,
    fallback_policy: str = "eager",
) -> Tuple[Optional[Set[int]], List[str], Dict[int, str]]:
    """Tek bileşende greedy + zorla örtme + onarım + kapasite yükseltmesi.

    fallback_policy, ana greedy döngüsü açıkta kenar bırakarak çıktığında ne
    olacağını belirler (ayrıntılı gerekçe: modül başlığı, GERİ-ÇEKİLME SİYASETİ):
      "eager"  VARSAYILAN. Yayımlanmış algoritma OLDUĞU GİBİ: koşulsuz
               `force_cover_remaining`. Varsayılan olmasının tek sebebi, hiç
               kimsenin istemediği bir varsayılan değişikliğinin bütün alt
               ölçümleri sessizce kaydırmaması.
      "flow"   yayımlanmış algoritmadan bariz kusur çıkarılmış hâli. Önce
               maksimum akışa sorulur; örtü zaten kapasite-uygunsa hiçbir şey
               eklenmez. Açıkça seçilerek kullanılır.

    Döndürür: (örtü, notlar, düğüm->evre). Örtü None ise bileşen çözümsüz.
    """
    if fallback_policy not in FALLBACK_POLICIES:
        raise ValueError(
            f"bilinmeyen fallback_policy: {fallback_policy} (secenekler: {FALLBACK_POLICIES})"
        )
    notes: List[str] = []
    c = _Component(sub)
    if not c.edges:
        return set(), notes, {}  # yalıtık düğümler örtüye girmez

    while c.has_uncovered():
        c.mark_red_nodes(faithful_red)
        v = picker(c, False)
        if v is None:
            break
        c.select_node(v, sorter, False)

    if c.has_uncovered():
        # Ana döngü çıkışında örtü ZATEN tepe örtüsüdür (kanıt: modül başlığı).
        # Açık olan tek soru kapasite; ona greedy'nin bayat atamasına değil akışa sorulur.
        skip = fallback_policy == "flow" and _bmatching(c.edges, c.cover, c.k)[0]
        if skip:
            notes.append("ana dongu acikta kenarla cikti ama ortu akisa gore ZATEN uygun: fallback atlandi")
        else:
            c.force_cover_remaining(picker, sorter)
            notes.append("force_cover_remaining kostu")

    c.repair_connectivity()
    ok, _owner, added = c.escalate_capacity()
    if added:
        notes.append(f"kapasite yukseltmesi: +{added} dugum")
    if not ok:
        return None, notes, dict(c.origin)
    return set(c.cover), notes, dict(c.origin)


def _solve_greedy(
    g: CcvcGraph,
    name: str,
    *,
    strict: bool = True,
    faithful_red: bool = False,
    fallback_policy: str = "eager",
) -> CentralResult:
    label, picker, sorter = _RULES[name]
    t0 = time.perf_counter()
    cover: Set[int] = set()
    notes: List[str] = []
    bad: List[int] = []
    origin: Dict[int, str] = {}
    for comp in _components(g):
        sub = _subgraph(g, comp)
        part, cnotes, corigin = _greedy_component(
            sub, picker, sorter, faithful_red=faithful_red, fallback_policy=fallback_policy
        )
        notes.extend(f"bilesen@{comp[0]}: {n}" for n in cnotes)
        origin.update(corigin)
        if part is None:
            bad.append(comp[0])
            continue
        cover |= part
    dt = (time.perf_counter() - t0) * 1000.0
    if bad:
        return _infeasible_result(label, g, bad, dt, notes, strict)
    res = _finish(label, g, cover, dt, notes, strict=strict)
    res.fallback_policy = fallback_policy
    res.phase = {v: origin.get(v, "greedy") for v in res.cover}
    res.weight_by_phase = {}
    res.count_by_phase = {}
    for v, ph in res.phase.items():
        res.weight_by_phase[ph] = res.weight_by_phase.get(ph, 0.0) + g.weight[v]
        res.count_by_phase[ph] = res.count_by_phase.get(ph, 0) + 1
    return res


# ==========================================================================
# tam çözüm: dal-sınır, bileşen bazlı
# ==========================================================================
def _exact_component(
    sub: CcvcGraph, deadline: Optional[float]
) -> Tuple[Optional[Set[int]], bool]:
    """Bileşende en küçük ağırlıklı geçerli örtü. Döndürür: (örtü, zaman aşımı)."""
    nodes = sorted(sub.nodes)
    edges = sorted(sub.edges)
    k = sub.capacity_k
    w = sub.weight
    if not edges:
        return set(), False

    adj = {v: set(sub.adj[v]) for v in nodes}
    n = len(nodes)
    m = len(edges)

    def connected(cs: Set[int]) -> bool:
        if len(cs) <= 1:
            return True
        start = min(cs)
        seen = {start}
        stack = [start]
        while stack:
            x = stack.pop()
            for y in adj[x]:
                if y in cs and y not in seen:
                    seen.add(y)
                    stack.append(y)
        return len(seen) == len(cs)

    def feasible(cs: Set[int]) -> bool:
        if len(cs) * k < m:
            return False
        if not all(u in cs or v in cs for u, v in edges):
            return False
        if not connected(cs):
            return False
        return _bmatching(edges, cs, k)[0]

    # üst sınır: üç greedy'nin en iyisi (dal-sınır bundan aşağısını arar)
    best: Set[int] = set()
    best_w = float("inf")
    for nm in ("gccvc", "grccvc", "gwccvc"):
        _lbl, picker, sorter = _RULES[nm]
        part, _notes, _origin = _greedy_component(sub, picker, sorter)
        if part is None or not feasible(part):
            continue
        pw = sum(w[v] for v in part)
        if pw < best_w - 1e-12:
            best_w, best = pw, set(part)
    if best_w == float("inf") and not feasible(set(nodes)):
        return None, False  # bu k altında bileşen çözümsüz

    order = sorted(nodes, key=lambda v: (-len(adj[v]), w[v], v))
    pos = {v: i for i, v in enumerate(order)}
    excluded: Set[int] = set()
    timed_out = False

    class _Timeout(Exception):
        pass

    def check_time() -> None:
        if deadline is not None and time.perf_counter() >= deadline:
            raise _Timeout()

    def dfs(idx: int, cur: Set[int], wt: float) -> None:
        nonlocal best, best_w
        check_time()
        if wt >= best_w - 1e-12:
            return
        if (len(cur) + (n - idx)) * k < m:
            return
        if idx == n:
            if feasible(cur):
                best_w = wt
                best = set(cur)
            return
        v = order[idx]
        # dal 1: v örtüde
        cur.add(v)
        dfs(idx + 1, cur, wt + w[v])
        cur.discard(v)
        # dal 2: v dışarıda -- karar verilmiş bir komşusu da dışarıdaysa kenar açıkta kalır
        for u in adj[v]:
            if pos[u] < idx and u in excluded:
                return
        excluded.add(v)
        dfs(idx + 1, cur, wt)
        excluded.discard(v)

    try:
        dfs(0, set(), 0.0)
    except _Timeout:
        timed_out = True
    if best_w == float("inf"):
        return None, timed_out
    return best, timed_out


# ==========================================================================
# ortak bitiriciler
# ==========================================================================
def _infeasible_result(
    label: str,
    g: CcvcGraph,
    bad: Sequence[int],
    dt: float,
    notes: List[str],
    strict: bool,
) -> CentralResult:
    msg = f"k={g.capacity_k} altinda cozumsuz bilesen(ler): {sorted(bad)}"
    notes = list(notes) + [msg]
    if strict:
        raise CcvcInfeasible(f"{label}: {msg}")
    return CentralResult(
        algorithm=label,
        cover=set(),
        owner={},
        total_weight=0.0,
        cover_size=0,
        vertex_cover=False,
        connected=False,
        capacity_feasible=False,
        feasible=False,
        status="infeasible",
        bridge_capacity=None,
        bridge_verdict=None,
        time_ms=dt,
        notes=notes,
    )


def _finish(
    label: str,
    g: CcvcGraph,
    cover: Set[int],
    dt: float,
    notes: List[str],
    *,
    strict: bool = True,
    timed_out: bool = False,
    exact: bool = False,
) -> CentralResult:
    """Üç kapıyı koştur, sonucu paketle; geçersiz örtü sessizce dönmez."""
    verdict = bridge.verify(g, cover)
    cap_ok, owner = capacity_assignment(g, cover)
    res = CentralResult(
        algorithm=label,
        cover=set(cover),
        owner=owner,
        total_weight=g.total_weight(cover),
        cover_size=len(cover),
        vertex_cover=verdict.vertex_cover,
        connected=verdict.connected,
        capacity_feasible=cap_ok,
        feasible=True,
        status="ok",
        bridge_capacity=verdict.capacity_feasible,
        bridge_verdict=verdict,
        time_ms=dt,
        timed_out=timed_out,
        exact=exact,
        notes=list(notes),
    )
    if verdict.capacity_feasible != cap_ok:
        res.notes.append(
            f"KAPASITE AYRISMASI: bridge.capacity_feasible={verdict.capacity_feasible}, "
            f"_bmatching={cap_ok} -- iki bagimsiz akistan biri hatali, incele"
        )
    if not res.valid and strict:
        raise CcvcSolverError(
            f"{label} gecersiz ortu dondurdu: vc={res.vertex_cover} "
            f"conn={res.connected} cap={res.capacity_feasible} "
            f"|C|={res.cover_size} k={g.capacity_k}"
        )
    if not res.valid:
        res.status = "invalid"
    return res


# ==========================================================================
# genel arayüz
# ==========================================================================
def solve_gccvc(
    g: CcvcGraph,
    *,
    strict: bool = True,
    faithful_red: bool = False,
    fallback_policy: str = "eager",
) -> CentralResult:
    """Greedy CCVC: en büyük örtülmemiş dereceyi seç (algorithms.py 629-684)."""
    return _solve_greedy(
        g, "gccvc", strict=strict, faithful_red=faithful_red,
        fallback_policy=fallback_policy,
    )


def solve_grccvc(
    g: CcvcGraph,
    *,
    strict: bool = True,
    faithful_red: bool = False,
    fallback_policy: str = "eager",
) -> CentralResult:
    """Greedy oranlı CCVC: en küçük ağırlık/komşu-ağırlığı oranı (algorithms.py 686-735)."""
    return _solve_greedy(
        g, "grccvc", strict=strict, faithful_red=faithful_red,
        fallback_policy=fallback_policy,
    )


def solve_gwccvc(
    g: CcvcGraph,
    *,
    strict: bool = True,
    faithful_red: bool = False,
    fallback_policy: str = "eager",
) -> CentralResult:
    """Greedy ağırlıklı CCVC: en küçük ağırlığı seç (algorithms.py 738-789)."""
    return _solve_greedy(
        g, "gwccvc", strict=strict, faithful_red=faithful_red,
        fallback_policy=fallback_policy,
    )


def solve_exact(
    g: CcvcGraph,
    *,
    max_n: Optional[int] = 18,
    time_limit_s: Optional[float] = 30.0,
    strict: bool = True,
) -> CentralResult:
    """Tam çözüm (dal-sınır), bileşen bazlı. Küçük örneklerde optimum gerçeği.

    max_n tek bir BİLEŞENDEKİ düğüm sayısı üst sınırı; aşılırsa ValueError.
    time_limit_s tüm çözüm için toplam süre; dolarsa en iyi bulunan döner ve
    `timed_out` işaretlenir (o durumda optimum garantisi yoktur).
    """
    t0 = time.perf_counter()
    deadline = None if time_limit_s is None else t0 + float(time_limit_s)
    cover: Set[int] = set()
    notes: List[str] = []
    bad: List[int] = []
    timed_out = False
    for comp in _components(g):
        sub = _subgraph(g, comp)
        if max_n is not None and len(comp) > int(max_n):
            raise ValueError(
                f"tam cozucu icin bilesen cok buyuk: |comp|={len(comp)} > max_n={max_n}"
            )
        part, to = _exact_component(sub, deadline)
        timed_out = timed_out or to
        if part is None:
            bad.append(comp[0])
            continue
        cover |= part
    dt = (time.perf_counter() - t0) * 1000.0
    if bad:
        return _infeasible_result("EXACT", g, bad, dt, notes, strict)
    if timed_out:
        notes.append("zaman siniri doldu: optimum garantisi yok")
    return _finish(
        "EXACT",
        g,
        cover,
        dt,
        notes,
        strict=strict,
        timed_out=timed_out,
        exact=not timed_out,
    )


SOLVERS: Dict[str, Callable[..., CentralResult]] = {
    "gccvc": solve_gccvc,
    "grccvc": solve_grccvc,
    "gwccvc": solve_gwccvc,
    "exact": solve_exact,
}


def solve(name: str, g: CcvcGraph, **kwargs) -> CentralResult:
    """İsimle çözücü çağır: gccvc | grccvc | gwccvc | exact."""
    key = name.lower()
    if key not in SOLVERS:
        raise ValueError(f"bilinmeyen cozucu: {name} (secenekler: {sorted(SOLVERS)})")
    return SOLVERS[key](g, **kwargs)
