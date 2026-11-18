#!/usr/bin/env python3
"""BB-CVC doğrulayıcısı: ihlal listesi üreten (C, owner) denetimi (brief §9).

Bu modül `ccvc/bridge.py` içindeki akış tabanlı kapasite denetimini YENİDEN
YAZMAZ, onu çağırır (`bridge.capacity_feasible`, Edmonds-Karp b-eşlemesi; 400
rastgele örnekte kaba kuvvetle çapraz sınanmıştır, DISCOVERY §5). Buraya eklenen
şey brief §9'un istedikleridir:

  * `owner` AÇIK bir girdidir ve verildiğinde YETKİLİDİR; akışa sorulmaz,
    doğrudan denetlenir. Brief §1: "sahiplik fonksiyonu çıktının parçasıdır;
    'uygun atama vardır' demek yetmez."
  * Sonuç üç boole değil, bir İHLAL LİSTESİDİR. Brief §8 şekil 2 kırmızıyı
    bu listeden çizer, dolayısıyla her ihlal çizilebilecek kadar bilgi taşır
    (hangi kenar açıkta, hangi düğüm ne kadar taşkın, hangi bileşen kopuk).
  * Yerel–küresel tutarlılık denetimi (`check_local_global`).
  * Brief §2'deki yapısal olgular (G1, G2, G4, G6) çağrılabilir denetimler
    olarak dışarı verilir; brief bunların testlerde assert edilmesini ister.

BAĞLILIK — İKİ TANIM, AÇIK PARAMETRE (önemli):
  Brief §1 G'nin BAĞLI olduğunu varsayar ve G[C]'nin bağlı olmasını ister.
  `bridge.is_connected_cover` bunu bilerek gevşetir ve bileşen bazlı çalışır,
  çünkü simülatör çizgeleri çoğu karede kopuktur (plan/PLAN_DCCVC.md §0.5). İkisi de
  desteklenir:

    connectivity="strict"         (VARSAYILAN, brief §1 tanımı)
        G[C] TEK parça olmalıdır. Girdi çizgesinin kendisi kopuksa bu bir
        ÇÖZÜCÜ hatası değil GİRDİ hatasıdır; ayrı bir ihlal türüyle
        ("graph_disconnected") raporlanır, sessizce geçilmez.

    connectivity="per_component"  (bridge.py'nin gevşetmesi)
        G'nin her bağlı bileşeninde, o bileşene düşen örtü parçası bağlı
        olmalıdır. Kopuk girdi çizgesi kendi başına ihlal değildir.

  Not: strict kipte kenarsız (yalıtık) düğümler de G'yi kopuk yapar. Brief §2
  G1 zaten "izole düğüm yoksa" diye başlar; yalıtık düğümlü bir örnek brief'in
  problem tanımının dışındadır ve strict kip bunu söylemek zorundadır.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

from .. import bridge
from ..bridge import CcvcGraph, Edge, edge_key
from .api import ValidationReport, Violation

# --------------------------------------------------------------------------
# ihlal türleri — api.Violation.kind için kanonik değerler
# --------------------------------------------------------------------------
# api.py'deki yorum dört tür sayar ("uncovered_edge", "overload", "disconnected",
# "bad_owner"); aşağıdaki üç tür onların ayırt edemediği durumlar içindir ve
# api.py'ye dokunmadan eklenmiştir.
UNCOVERED_EDGE = "uncovered_edge"        # iki ucu da C dışında kenar
OVERLOAD = "overload"                    # v'nin SAHİPLENDİĞİ kenar sayısı > k
FORCED_OVERLOAD = "forced_overload"      # F(v) > k; owner ne olursa olsun çözümsüz (G4)
DISCONNECTED = "disconnected"            # G[C] birden çok parça
GRAPH_DISCONNECTED = "graph_disconnected"  # GİRDİ çizgesi kopuk (yalnız strict kip)
BAD_OWNER = "bad_owner"                  # bozuk sahiplik girdisi
CAPACITY_INFEASIBLE = "capacity_infeasible"  # owner yok, akış "atama yok" diyor
LOWER_BOUND = "lower_bound"              # |C| < ceil(|E|/k) (G6)
LOCAL_GLOBAL = "local_global_mismatch"   # yerel denetimler geçti, küresel geçmedi
BAD_COVER = "bad_cover"                  # C'de çizgede olmayan düğüm

STRICT = "strict"
PER_COMPONENT = "per_component"
_MODES = (STRICT, PER_COMPONENT)

OwnerInput = Union[Mapping[Edge, int], Iterable[Tuple[Edge, int]]]


# --------------------------------------------------------------------------
# rapor
# --------------------------------------------------------------------------
@dataclass
class LoadViolation(Violation):
    """Taşkın ihlali; "ne kadar" bilgisini kaybetmemek için fazladan alan taşır.

    api.Violation bir dataclass olduğundan alt sınıflamak güvenlidir; ihlal
    listesini gezen kod (şekil 2) bunu düz bir Violation gibi kullanabilir.
    """

    load: int = 0
    capacity: int = 0
    excess: int = 0


@dataclass
class BbValidationReport(ValidationReport):
    """api.ValidationReport + BB-CVC'nin ihtiyaç duyduğu bağlam.

    `owner` verilmediğinde kapasite sorusunun yalnız VARLIK olarak
    yanıtlandığı burada açıkça söylenir (`owner_source == "flow"`).
    """

    owner_supplied: bool = False
    owner_source: str = "none"           # "explicit" | "flow" | "none"
    connectivity_mode: str = STRICT
    resolved_owner: Dict[Edge, int] = field(default_factory=dict)
    load: Dict[int, int] = field(default_factory=dict)
    forced: Dict[int, int] = field(default_factory=dict)
    cover_components: List[Tuple[int, ...]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> List[Violation]:
        return [v for v in self.violations if v.kind == kind]

    def summary(self) -> str:
        if self.valid:
            return "VALID"
        parts = sorted({v.kind for v in self.violations})
        return "INVALID: " + ", ".join(parts)


# --------------------------------------------------------------------------
# küçük yardımcılar
# --------------------------------------------------------------------------
def make_graph(
    edges: Sequence[Edge],
    capacity_k: int,
    weight: Optional[Mapping[int, float]] = None,
    nodes: Optional[Sequence[int]] = None,
) -> CcvcGraph:
    """Elle yazılmış birim testler için kısa yol; `CcvcGraph` üretir."""
    ekeys = sorted({edge_key(int(u), int(v)) for u, v in edges})
    if nodes is None:
        ns: Set[int] = set()
        for u, v in ekeys:
            ns.add(u)
            ns.add(v)
        node_list = sorted(ns)
    else:
        node_list = sorted(set(int(n) for n in nodes))
    w = {n: float(weight[n]) if weight and n in weight else 1.0 for n in node_list}
    return CcvcGraph(nodes=node_list, edges=ekeys, weight=w, capacity_k=capacity_k)


def forced_load(g: CcvcGraph, cover: Iterable[int], v: int) -> int:
    """G4: F(v) = |{u ∈ N(v) : u ∉ C}|. v için zorunlu kenar sayısı."""
    cov = cover if isinstance(cover, (set, frozenset)) else set(cover)
    return sum(1 for u in g.adj[v] if u not in cov)


def forced_edges(g: CcvcGraph, cover: Iterable[int], v: int) -> Tuple[Edge, ...]:
    """F(v)'yi oluşturan kenarlar; sahibi zorunlu olarak v olmak durumundadır."""
    cov = cover if isinstance(cover, (set, frozenset)) else set(cover)
    return tuple(edge_key(v, u) for u in sorted(g.adj[v]) if u not in cov)


def cover_components(g: CcvcGraph, cover: Iterable[int]) -> List[Tuple[int, ...]]:
    """G[C] bileşenleri, deterministik sırada."""
    comps = bridge.cover_components(g, set(cover))
    return sorted((tuple(sorted(c)) for c in comps), key=lambda c: (c[0], len(c)))


def graph_components(g: CcvcGraph) -> List[Tuple[int, ...]]:
    comps = bridge.graph_components(g)
    return sorted((tuple(sorted(c)) for c in comps), key=lambda c: (c[0], len(c)))


def lower_bound_g6(g: CcvcGraph) -> int:
    """G6: |C| ≥ ⌈|E|/k⌉. k ≤ 0 ise sınır tanımsızdır, 0 döner."""
    if g.capacity_k <= 0 or not g.edges:
        return 0
    return math.ceil(len(g.edges) / g.capacity_k)


def normalize_owner(owner: OwnerInput) -> List[Tuple[Edge, int]]:
    """Sahiplik girdisini (kanonik kenar, sahip) çiftleri listesine indirger.

    Hem eşleme hem de çift dizisi kabul edilir. Çift dizisi biçimi ÖNEMLİDİR:
    aynı kenarın iki kez atanması ancak böyle ifade edilebilir. Eşleme
    biçiminde ise (u,v) ve (v,u) anahtarlarının ikisinin birden bulunması
    çifte atamadır.
    """
    items: Iterable[Tuple[Edge, int]]
    if isinstance(owner, Mapping):
        items = list(owner.items())
    else:
        items = list(owner)
    out: List[Tuple[Edge, int]] = []
    for e, o in items:
        u, v = e
        out.append((edge_key(int(u), int(v)), int(o)))
    return out


# --------------------------------------------------------------------------
# brief §2 yapısal olguları — çağrılabilir denetimler
# --------------------------------------------------------------------------
def isolated_nodes(g: CcvcGraph) -> Tuple[int, ...]:
    return tuple(v for v in g.nodes if not g.adj[v])


def is_dominating_set(g: CcvcGraph, s: Iterable[int]) -> bool:
    """Her düğüm S'de ya da S'den bir komşuya sahip mi."""
    ss = set(s)
    return all(v in ss or any(u in ss for u in g.adj[v]) for v in g.nodes)


def check_g1(g: CcvcGraph, cover: Iterable[int]) -> List[Violation]:
    """G1: izole düğüm yoksa her BAĞLI tepe örtüsü bağlı baskın kümedir.

    Önkoşul sağlanmıyorsa (izole düğüm var ya da C örtü/bağlı değil) denetim
    uygulanmaz ve boş liste döner; olgu yalnız önkoşullar altında iddia edilir.
    """
    cov = set(cover)
    if isolated_nodes(g):
        return []
    if bridge.uncovered_edges(g, cov):
        return []
    if len(cover_components(g, cov)) > 1:
        return []
    if is_dominating_set(g, cov):
        return []
    missing = tuple(
        v for v in g.nodes if v not in cov and not any(u in cov for u in g.adj[v])
    )
    return [
        Violation(
            kind="structural_g1",
            detail=f"G1 çürüdü: bağlı tepe örtüsü baskın değil, örtülmeyen düğüm {missing}",
            nodes=missing,
        )
    ]


def check_g2(g: CcvcGraph, backbone: Iterable[int]) -> List[Violation]:
    """G2: CDS B verildiğinde örtülmemiş kenarlar TAM OLARAK iki ucu da B dışında olanlardır.

    B baskın ve bağlı değilse denetim uygulanmaz (olgunun önkoşulu yok).
    """
    b = set(backbone)
    if not is_dominating_set(g, b):
        return []
    if len(cover_components(g, b)) > 1:
        return []
    expected = {e for e in g.edges if e[0] not in b and e[1] not in b}
    actual = set(bridge.uncovered_edges(g, b))
    if expected == actual:
        return []
    diff = tuple(sorted(expected ^ actual))
    return [
        Violation(
            kind="structural_g2",
            detail=f"G2 çürüdü: açıktaki kenar kümesi beklenenden farklı, fark {diff}",
            edges=diff,
        )
    ]


def check_g4(g: CcvcGraph, cover: Iterable[int]) -> List[Violation]:
    """G4: F(v) > k ise çözüm geçersizdir; owner ne olursa olsun kurtarılamaz."""
    cov = set(cover)
    out: List[Violation] = []
    for v in sorted(cov):
        if v not in g.adj:
            continue
        fe = forced_edges(g, cov, v)
        f = len(fe)
        if f > g.capacity_k:
            out.append(
                LoadViolation(
                    kind=FORCED_OVERLOAD,
                    detail=(
                        f"düğüm {v}: zorunlu yük F(v)={f} > k={g.capacity_k}; "
                        f"en az {f - g.capacity_k} komşusu daha C'ye girmeli (G4)"
                    ),
                    nodes=(v,),
                    edges=fe,
                    load=f,
                    capacity=g.capacity_k,
                    excess=f - g.capacity_k,
                )
            )
    return out


def check_g6(g: CcvcGraph, cover: Iterable[int]) -> List[Violation]:
    """G6: |C| ≥ ⌈|E|/k⌉."""
    lb = lower_bound_g6(g)
    n = len(set(cover))
    if lb == 0 or n >= lb:
        return []
    return [
        Violation(
            kind=LOWER_BOUND,
            detail=f"|C|={n} < ⌈|E|/k⌉=⌈{len(g.edges)}/{g.capacity_k}⌉={lb} (G6)",
            nodes=tuple(sorted(set(cover))),
        )
    ]


# --------------------------------------------------------------------------
# ana doğrulayıcı
# --------------------------------------------------------------------------
def validate(
    graph: CcvcGraph,
    cover: Iterable[int],
    owner: Optional[OwnerInput] = None,
    *,
    connectivity: str = STRICT,
    check_lower_bound: bool = True,
) -> BbValidationReport:
    """(C, owner) çiftini denetler ve İHLAL LİSTESİ döndürür (brief §9).

    owner verilmişse YETKİLİDİR: her kenar tam bir kez geçmeli, her sahip kendi
    kenarının ucu ve C üyesi olmalı, hiçbir düğüm k'dan çok kenar sahiplenmemeli.
    owner verilmemişse kapasite sorusu `bridge.capacity_feasible` akışıyla
    yalnız "uygun atama VAR MI" düzeyinde yanıtlanır; bu durum raporda
    `owner_source == "flow"` ve bir not olarak açıkça yazılır.

    connectivity: "strict" (brief §1) ya da "per_component" (bridge.py gevşetmesi).
    """
    if connectivity not in _MODES:
        raise ValueError(f"bilinmeyen bağlılık kipi: {connectivity!r} (beklenen {_MODES})")

    g = graph
    k = g.capacity_k
    cov = set(int(v) for v in cover)
    violations: List[Violation] = []
    notes: List[str] = []

    # 0. C çizgenin içinde mi
    unknown = tuple(sorted(v for v in cov if v not in g.adj))
    if unknown:
        violations.append(
            Violation(
                kind=BAD_COVER,
                detail=f"C'de çizgede bulunmayan düğüm var: {unknown}",
                nodes=unknown,
            )
        )
        cov -= set(unknown)

    # 1. örtü
    uncov = bridge.uncovered_edges(g, cov)
    for e in uncov:
        violations.append(
            Violation(
                kind=UNCOVERED_EDGE,
                detail=f"kenar {e} açıkta: iki ucu da C dışında",
                nodes=e,
                edges=(e,),
            )
        )
    is_vc = not uncov

    # 2. bağlılık
    comps = cover_components(g, cov)
    if connectivity == STRICT:
        gcomps = graph_components(g)
        if len(gcomps) > 1:
            iso = isolated_nodes(g)
            extra = f"; bunların {len(iso)} tanesi yalıtık düğüm" if iso else ""
            violations.append(
                Violation(
                    kind=GRAPH_DISCONNECTED,
                    detail=(
                        f"GİRDİ çizgesi kopuk: {len(gcomps)} bileşen{extra}. "
                        "Brief §1 G'nin bağlı olduğunu varsayar; bu bir çözücü hatası "
                        "değil girdi hatasıdır. Bileşen bazlı denetim için "
                        "connectivity='per_component' kullanın."
                    ),
                    nodes=tuple(c[0] for c in gcomps),
                )
            )
        connected = len(comps) <= 1
        if not connected:
            for i, c in enumerate(comps):
                violations.append(
                    Violation(
                        kind=DISCONNECTED,
                        detail=(
                            f"G[C] {len(comps)} parçaya ayrıldı; parça {i + 1}/{len(comps)} = {c}"
                        ),
                        nodes=c,
                        edges=tuple(
                            e for e in g.edges if e[0] in set(c) and e[1] in set(c)
                        ),
                    )
                )
    else:
        connected = bridge.is_connected_cover(g, cov)
        if not connected:
            gc_of: Dict[int, int] = {}
            for i, gc in enumerate(graph_components(g)):
                for v in gc:
                    gc_of[v] = i
            groups: Dict[int, List[Tuple[int, ...]]] = {}
            for c in comps:
                groups.setdefault(gc_of[c[0]], []).append(c)
            for gi, parts in sorted(groups.items()):
                if len(parts) <= 1:
                    continue
                for j, c in enumerate(parts):
                    violations.append(
                        Violation(
                            kind=DISCONNECTED,
                            detail=(
                                f"çizge bileşeni {gi} içinde örtü {len(parts)} parça; "
                                f"parça {j + 1}/{len(parts)} = {c}"
                            ),
                            nodes=c,
                            edges=tuple(
                                e for e in g.edges if e[0] in set(c) and e[1] in set(c)
                            ),
                        )
                    )

    # 3. zorunlu yük (G4) — owner'dan bağımsız, örtünün kendi kusuru
    forced = {v: forced_load(g, cov, v) for v in sorted(cov)}
    if is_vc:
        violations.extend(check_g4(g, cov))

    # 4. kapasite
    load: Dict[int, int] = {v: 0 for v in sorted(cov)}
    resolved: Dict[Edge, int] = {}
    owner_supplied = owner is not None
    owner_source = "none"
    capacity_ok = True

    if k <= 0 and g.edges:
        capacity_ok = False
        violations.append(
            Violation(
                kind=CAPACITY_INFEASIBLE,
                detail=f"k={k} ≤ 0 ve |E|={len(g.edges)} > 0: hiçbir kenar sahiplenilemez",
                edges=tuple(g.edges),
            )
        )

    if owner_supplied:
        owner_source = "explicit"
        pairs = normalize_owner(owner)  # type: ignore[arg-type]
        edge_set = set(g.edges)
        seen: Dict[Edge, List[int]] = {}
        for e, o in pairs:
            seen.setdefault(e, []).append(o)

        # 4a. çizgede olmayan kenar
        for e in sorted(set(seen) - edge_set):
            violations.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=f"sahiplik tablosunda çizgede olmayan kenar {e}",
                    nodes=tuple(sorted(set(seen[e]))),
                    edges=(e,),
                )
            )
        # 4b. çifte atama
        for e in sorted(e for e, os in seen.items() if len(os) > 1):
            violations.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=(
                        f"kenar {e} {len(seen[e])} kez atandı (sahip iddiaları {tuple(seen[e])}); "
                        "her kenar tam bir kez geçmelidir"
                    ),
                    nodes=tuple(sorted(set(seen[e]))),
                    edges=(e,),
                )
            )
        # 4c. sahipsiz kenar
        for e in sorted(edge_set - set(seen)):
            violations.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=f"kenar {e} sahipsiz: sahiplik tablosunda yok",
                    nodes=e,
                    edges=(e,),
                )
            )
        # 4d. sahip ucu mu, C üyesi mi + yük
        for e in sorted(seen):
            for o in seen[e]:
                load[o] = load.get(o, 0) + 1
                if o not in e:
                    violations.append(
                        Violation(
                            kind=BAD_OWNER,
                            detail=f"kenar {e} sahibi {o} bu kenarın ucu değil",
                            nodes=(o,),
                            edges=(e,),
                        )
                    )
                elif o not in cov:
                    violations.append(
                        Violation(
                            kind=BAD_OWNER,
                            detail=f"kenar {e} sahibi {o} C'de değil",
                            nodes=(o,),
                            edges=(e,),
                        )
                    )
            if len(seen[e]) == 1 and seen[e][0] in e and seen[e][0] in cov:
                resolved[e] = seen[e][0]
        # 4e. taşkın
        for v in sorted(load):
            if load[v] > k:
                owned = tuple(sorted(e for e in seen if v in seen[e]))
                violations.append(
                    LoadViolation(
                        kind=OVERLOAD,
                        detail=(
                            f"düğüm {v}: sahiplenilen kenar {load[v]} > k={k}, "
                            f"aşım {load[v] - k}"
                        ),
                        nodes=(v,),
                        edges=owned,
                        load=load[v],
                        capacity=k,
                        excess=load[v] - k,
                    )
                )
        capacity_ok = capacity_ok and not any(
            v.kind in (OVERLOAD, BAD_OWNER, FORCED_OVERLOAD) for v in violations
        )
    else:
        notes.append(
            "owner verilmedi: kapasite sorusu yalnız akış tabanlı VARLIK denetimiyle "
            "yanıtlandı (bridge.capacity_feasible). Raporlanan sahiplik bir TANIKtır, "
            "algoritmanın ürettiği atama değildir."
        )
        if is_vc and k > 0:
            feasible, witness = bridge.capacity_feasible(g, cov)
            owner_source = "flow"
            if feasible:
                resolved = dict(witness)
                for e, o in resolved.items():
                    load[o] = load.get(o, 0) + 1
            else:
                capacity_ok = False
                hot = tuple(v for v in sorted(cov) if forced.get(v, 0) > k) or tuple(
                    sorted(cov)
                )
                violations.append(
                    Violation(
                        kind=CAPACITY_INFEASIBLE,
                        detail=(
                            f"akış denetimi: C (|C|={len(cov)}, k={k}) için kenarları "
                            f"uçlarına dağıtan HİÇBİR atama yok"
                        ),
                        nodes=hot,
                        edges=tuple(g.edges),
                    )
                )
        elif not is_vc:
            capacity_ok = False
            notes.append("örtü değil: kapasite denetimi anlamsız, atlandı.")

    if any(v.kind == FORCED_OVERLOAD for v in violations):
        capacity_ok = False

    # 5. G6 alt sınırı
    if check_lower_bound:
        violations.extend(check_g6(g, cov))

    return BbValidationReport(
        vertex_cover=is_vc,
        connected=connected,
        capacity=capacity_ok,
        violations=violations,
        owner_supplied=owner_supplied,
        owner_source=owner_source,
        connectivity_mode=connectivity,
        resolved_owner=resolved,
        load=load,
        forced=forced,
        cover_components=comps,
        notes=notes,
    )


# --------------------------------------------------------------------------
# yerel–küresel tutarlılık (brief §9)
# --------------------------------------------------------------------------
@dataclass
class LocalView:
    """Bir düğümün KENDİ iddiası: rolü, sahiplendiği kenarlar, zorunlu yükü.

    Düğüm çizgeyi görmez (api.py I1); bu görüş `NodeSnapshot`tan doğrudan
    kurulabilir. Denetim bu iddiaları çizgenin gerçeğiyle karşılaştırır.
    """

    nid: int
    in_cover: bool
    owned: Tuple[Edge, ...] = ()
    forced_load: int = 0

    @staticmethod
    def from_snapshot(snap) -> "LocalView":
        """api.NodeSnapshot -> LocalView."""
        return LocalView(
            nid=snap.nid,
            in_cover=snap.role.in_cover,
            owned=tuple(edge_key(*e) for e in snap.owned),
            forced_load=snap.forced_load,
        )


def local_check(
    g: CcvcGraph, views: Mapping[int, LocalView], nid: int
) -> List[Violation]:
    """Tek düğümün YEREL denetimi: yalnız kendi ve 1-atlama komşularının iddiası.

    Denetlenenler (hepsi düğümün erişebileceği bilgiyle):
      * C dışındaysam bütün komşularım C'de olmalı (yoksa yanımda açık kenar var),
        hiçbir kenar sahiplenmemeliyim, F=0.
      * C'deysem sahiplendiğim her kenar bana komşu olmalı, |owned| ≤ k olmalı,
        F(v) iddiam komşularımın rolleriyle uyuşmalı, zorunlu kenarlarımın hepsi
        bende olmalı ve her komşu kenarı ikimizden TAM BİRİNDE olmalı.
    """
    k = g.capacity_k
    me = views[nid]
    out: List[Violation] = []
    inc = {edge_key(nid, u) for u in g.adj[nid]}
    owned = set(me.owned)

    for e in sorted(owned - inc):
        out.append(
            Violation(
                kind=BAD_OWNER,
                detail=f"düğüm {nid} kendisine komşu olmayan {e} kenarını sahipleniyor",
                nodes=(nid,),
                edges=(e,),
            )
        )

    if not me.in_cover:
        if owned:
            out.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=f"düğüm {nid} C dışında ama {tuple(sorted(owned))} kenarlarını sahipleniyor",
                    nodes=(nid,),
                    edges=tuple(sorted(owned)),
                )
            )
        if me.forced_load != 0:
            out.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=f"düğüm {nid} C dışında ama F={me.forced_load} bildiriyor",
                    nodes=(nid,),
                )
            )
        for u in sorted(g.adj[nid]):
            if u in views and not views[u].in_cover:
                out.append(
                    Violation(
                        kind=UNCOVERED_EDGE,
                        detail=f"düğüm {nid}: komşum {u} da C dışında, aramızdaki kenar açıkta",
                        nodes=(nid, u),
                        edges=(edge_key(nid, u),),
                    )
                )
        return out

    if len(owned) > k:
        out.append(
            LoadViolation(
                kind=OVERLOAD,
                detail=f"düğüm {nid}: yerel yük {len(owned)} > k={k}",
                nodes=(nid,),
                edges=tuple(sorted(owned)),
                load=len(owned),
                capacity=k,
                excess=len(owned) - k,
            )
        )

    true_forced = tuple(
        edge_key(nid, u)
        for u in sorted(g.adj[nid])
        if u in views and not views[u].in_cover
    )
    if me.forced_load != len(true_forced):
        out.append(
            Violation(
                kind=BAD_OWNER,
                detail=(
                    f"düğüm {nid}: F iddiası {me.forced_load}, komşu rollerinden çıkan "
                    f"gerçek F {len(true_forced)}"
                ),
                nodes=(nid,),
                edges=true_forced,
            )
        )
    for e in true_forced:
        if e not in owned:
            out.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=f"düğüm {nid}: zorunlu kenar {e} sahiplenilmemiş",
                    nodes=(nid,),
                    edges=(e,),
                )
            )

    for u in sorted(g.adj[nid]):
        if u not in views:
            continue
        e = edge_key(nid, u)
        mine = e in owned
        theirs = e in set(views[u].owned)
        if mine and theirs:
            out.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=f"kenar {e} hem {nid} hem {u} tarafından sahiplenilmiş",
                    nodes=(nid, u),
                    edges=(e,),
                )
            )
        elif not mine and not theirs:
            out.append(
                Violation(
                    kind=BAD_OWNER,
                    detail=f"kenar {e} ne {nid} ne {u} tarafından sahiplenilmiş",
                    nodes=(nid, u),
                    edges=(e,),
                )
            )
    return out


def check_local_global(
    graph: CcvcGraph,
    views: Union[Mapping[int, LocalView], Iterable[LocalView]],
    *,
    connectivity: str = STRICT,
) -> Tuple[BbValidationReport, Dict[int, List[Violation]]]:
    """Brief §9: yerel denetimler geçiyorsa ve G[C] bağlıysa küresel de geçmeli.

    Yerel görüşlerden C ve owner türetilir, küresel `validate` koşulur. Her
    düğümün yerel denetimi geçmiş, G[C] bağlı, ama küresel denetim düşmüşse bu
    dağıtık algoritmada BİR HATADIR; ihlal `local_global_mismatch` türüyle ve
    sorumlu düğüm adıyla rapora eklenir.

    Döner: (küresel rapor, düğüm -> yerel ihlaller).
    """
    if isinstance(views, Mapping):
        vmap = {int(k): v for k, v in views.items()}
    else:
        vmap = {v.nid: v for v in views}

    local: Dict[int, List[Violation]] = {}
    for nid in sorted(vmap):
        if nid not in graph.adj:
            local[nid] = [
                Violation(
                    kind=BAD_COVER,
                    detail=f"yerel görüş çizgede olmayan düğüm {nid} için verildi",
                    nodes=(nid,),
                )
            ]
            continue
        local[nid] = local_check(graph, vmap, nid)

    cover = sorted(v.nid for v in vmap.values() if v.in_cover)
    pairs: List[Tuple[Edge, int]] = []
    for nid in sorted(vmap):
        for e in vmap[nid].owned:
            pairs.append((edge_key(*e), nid))

    report = validate(graph, cover, pairs, connectivity=connectivity)
    all_local_ok = not any(local[n] for n in local)
    covered_nodes = set(graph.nodes) - set(vmap)
    if covered_nodes:
        report.notes.append(
            f"yerel görüş verilmeyen düğümler var: {tuple(sorted(covered_nodes))}; "
            "yerel–küresel savı yalnız bütün düğümler bildirdiğinde geçerlidir."
        )

    if all_local_ok and report.connected and not covered_nodes:
        # savın karşı örneği: yerel hepsi temiz + G[C] bağlı ama küresel düştü
        offenders = [v for v in report.violations if v.kind != GRAPH_DISCONNECTED]
        for v in offenders:
            named = v.nodes or tuple(sorted({n for e in v.edges for n in e}))
            report.violations.append(
                Violation(
                    kind=LOCAL_GLOBAL,
                    detail=(
                        f"yerel–küresel uyuşmazlığı: bütün düğümlerin yerel denetimi "
                        f"geçti ve G[C] bağlı, ama küresel denetim '{v.kind}' verdi "
                        f"({v.detail}). Sorumlu düğüm(ler): {named}. Bu dağıtık "
                        "algoritmada bir HATADIR."
                    ),
                    nodes=named,
                    edges=v.edges,
                )
            )
    return report, local


def views_from_solution(
    g: CcvcGraph, cover: Iterable[int], owner: Mapping[Edge, int]
) -> Dict[int, LocalView]:
    """Küresel bir (C, owner) çözümünden her düğümün yerel görüşünü üretir.

    Testler ve şekiller için; gerçek koşumda görüşler düğümlerin kendisinden gelir.
    """
    cov = set(cover)
    owned: Dict[int, List[Edge]] = {v: [] for v in g.nodes}
    for e, o in owner.items():
        owned.setdefault(o, []).append(edge_key(*e))
    return {
        v: LocalView(
            nid=v,
            in_cover=v in cov,
            owned=tuple(sorted(owned.get(v, ()))),
            forced_load=forced_load(g, cov, v) if v in cov else 0,
        )
        for v in g.nodes
    }
