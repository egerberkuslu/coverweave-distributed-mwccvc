#!/usr/bin/env python3
"""BB-CVC karşılaştırma varyantları (brief §6): DFS-Spanning-Backbone ve GHS-MST-Backbone.

İKİSİ DE YALNIZ FAZ 1'İ DEĞİŞTİRİR. Faz 2-5 harfi harfine `BbcvcNode`ın kodudur;
`_backbone_step` dikişi (bbcvc.py) dışında tek satır kopyalanmamıştır. Kopya
çıkarmak karşılaştırmayı sessizce karşılaştırma olmaktan çıkarırdı: iki kol
zamanla birbirinden uzaklaşır ve fark artık omurga seçiminden mi yoksa
sürüklenmeden mi geliyor bilinemez.

DİKİŞ SÖZLEŞMESİ (bbcvc.BbcvcNode._backbone_step). `phase` PH_COVER'a ulaştığı
anda her düğümün rolü MIS / CONNECTOR / OUT olmalı ve B = MIS u CONNECTOR bağlı
ve baskın olmalıdır (brief G1/G2). Buradaki varyantlar bu sözleşmeyi sağlar ve
testler sözleşmeyi DAVRANIŞLA sınar: `_backbone_step`in çağrıldığı değil,
omurganın Faz 3'e geçerli rollerle vardığı assert edilir.

BULGU (GHS-MST-Backbone, kıyas kümesi): "MST YANLIŞ AĞAÇ" DESTEKLENMİYOR.
Ölçüm: GHS-MST-Backbone örtüsü MIS-Connector-Backbone'dan %1,11 HAFİF, 7 eşleşmiş örneğin 7'sinde de daha ağır
değil (n<=25, k=4, senkron, hücre başına bir tohum). Merkezi ön ölçüm de aynı
yönü veriyordu: MIS+connector, MST'ye göre 1,005 ortalama, medyan aynı.

BULGUNUN HEDEFİ TAM OLARAK NEDİR (bb-algo'nun keskinleştirmesi). G3, DFS
özelliğini YALNIZCA ağırlıksız tepe örtüsü ve k=sonsuz için iddia eder.
Bizim örneklerimiz AĞIRLIKLI ve k SIKI. Dolayısıyla bu ölçüm G3'ü değil,
brief'in çok daha geniş ifade edilmiş "MST neden yanlış ağaç" GLOSUNU
çürütmektedir. Gloss, atıf yaptığı teoremin desteklediğinden fazlasını
söylemektedir; ayrımı yapmak bulguyu savuşturulması zor kılar ve projedeki
örüntüye oturtur: yapısal savlar tuttu, nicel/gayriresmi kestirimler tutmadı.

KAPSAM (tam olarak, çünkü bu sayı tabloya girecek):
  * dağıtık koşum: n <= 25, hücre başına TEK tohum, YALNIZ senkron
    zamanlayıcı, k = 4, 13 örnek koşuldu, ikisinin de geçerli olduğu
    7 EŞLEŞMİŞ örnek üzerinde karşılaştırıldı.
  * her iki kolda 5'er koşum bütçeyle kesildi (truncated) ve kapsam dışıdır.
  * merkezi ön ölçüm: yaklaşık Faz 3 ve yaklaşık Faz 1 kullanır; 310 örneğin
    7'si en az bir kolda geçersiz örtü ürettiği için dışarıda bırakılmıştır.
  * asenkron zamanlayıcı HİÇ koşulmamıştır.
YÖN KURULMUŞTUR, BÜYÜKLÜK KURULMAMIŞTIR. Yedi eşleşmiş örnek bir eğilim
gösterir, bir kat sayısı vermez.

GHS-MST-Backbone TAM BİLGİLİ BİR KOLDUR (ekip lideri kararı, brief §6 okuma (a)).
"Mevcut MST" ifadesi budur: ağaç MERKEZİ hesaplanır ve iç düğümleri role olarak
TOHUMLANIR. Dolayısıyla GHS-MST-Backbone I1'i (düğüm çizgeyi göremez) BİLEREK çiğner ve
bunun sonucu şudur: GHS-MST-Backbone KALİTE tablolarında yer alır, MESAJ MALİYETİ
tablolarında YER ALMAZ. Kendi omurgasını kurmayan bir kolun o sütuna koyacak
dürüst bir sayısı yoktur; nedeni yazılı boş bir hücre, komşularından farklı bir
şey ifade eden sessiz bir sayıdan iyidir. Yayımlanmış GHS sınırlarından
sentezlenmiş bir maliyet de konmaz: ölçüm sütununda literatür değeri ikisinin
en kötüsü olurdu.
"""
from __future__ import annotations

import heapq
import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import wire  # noqa: E402
from ccvc.bb.api import MsgType, Role  # noqa: E402
from ccvc.bb.bbcvc import (
    PH_CONN,
    PH_COVER,
    PH_MIS,
    BbcvcNode,
    BbcvcParams,
)  # noqa: E402
from ccvc.bb.bootstrap import BootNeighbor, RunInvalid  # noqa: E402

Edge = Tuple[int, int]


# ==========================================================================
# 1. Girdi kapısı: ÖLÇMEDEN ÖNCE bağlılık
# ==========================================================================
def adjacency(nodes: Iterable[int], edges: Iterable[Edge]) -> Dict[int, Set[int]]:
    adj: Dict[int, Set[int]] = {int(v): set() for v in nodes}
    for u, v in edges:
        u, v = int(u), int(v)
        if u == v:
            raise ValueError(f"ilmek kenar: {u}")
        if u not in adj or v not in adj:
            raise ValueError(f"kenar bilinmeyen düğüme değiyor: {(u, v)}")
        adj[u].add(v)
        adj[v].add(u)
    return adj


def assert_connected(nodes: Iterable[int], edges: Iterable[Edge]) -> None:
    """Brief §1 BAĞLI çizge varsayar. Ölçümden ÖNCE burada dayatılır.

    Kopuk bir çizgede kol-karşılaştırması sessizce ÇİZGE ÜRETİMİNİ ölçmeye
    başlar: bir kol büyük bileşende, diğeri parçalanmış bir örnekte koşar ve
    fark algoritmadan geliyor sanılır. Bu kapı ölçüm hattında bir kez
    çağrılır ve koşumu durdurur.
    """
    adj = adjacency(nodes, edges)
    if not adj:
        raise ValueError("boş çizge")
    start = min(adj)
    seen, stack = set(), [start]
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        stack.extend(v for v in adj[u] if v not in seen)
    if seen != set(adj):
        missing = sorted(set(adj) - seen)
        raise ValueError(
            f"çizge KOPUK: {len(adj)} düğümün {len(seen)}'i erişilebilir, "
            f"ilk erişilemeyen {missing[:5]}. Brief §1 bağlı çizge ister; "
            f"kopuk girdide kol karşılaştırması çizge üretimini ölçer."
        )


# ==========================================================================
# 2. Ağaçlar ve iç düğümler
# ==========================================================================
def mst_internal_nodes(
    nodes: Iterable[int], edges: Iterable[Edge], weight: Dict[int, float]
) -> Set[int]:
    """Minimum kapsayan ağacın İÇ (yaprak olmayan) düğümleri.

    Kenar ölçütü w(u)+w(v)'dir: çizge yalnız DÜĞÜM ağırlığı taşır, MST ise
    kenar ağırlığı ister, dolayısıyla ölçüt türetilmek zorundadır. Eşitlik
    (u, v) ile kırılır, yani ağaç deterministiktir.

    Herhangi bir kapsayan ağacın iç düğümleri bağlı ve baskındır: yaprakları
    atmak ağacı bağlı bırakır ve her yaprak bir iç düğüme komşudur. n <= 2
    için iç küme boş kalır, o durumda kök tek başına omurgadır.
    """
    adj = adjacency(nodes, edges)
    root = min(adj)
    seen = {root}
    children: Dict[int, int] = {v: 0 for v in adj}
    heap = [((weight[root] + weight[v], root, v), root, v) for v in sorted(adj[root])]
    heapq.heapify(heap)
    while heap:
        _, u, v = heapq.heappop(heap)
        if v in seen:
            continue
        seen.add(v)
        children[u] += 1
        for x in sorted(adj[v]):
            if x not in seen:
                heapq.heappush(heap, ((weight[v] + weight[x], v, x), v, x))
    # İÇ DÜĞÜM = ağaç derecesi >= 2, yani YAPRAK OLMAYAN. Kök için derece
    # çocuk sayısıdır; kök olmayan için çocuk sayısı + 1 (ebeveyn). `children>0`
    # demek kökü tek çocuğu olsa bile iç sayardı: bir yol çizgesinde uçtaki kök
    # yaprak olduğu hâlde omurgaya girer ve örtü gereksiz yere ağırlaşırdı.
    internal = {v for v in seen if children[v] + (0 if v == root else 1) >= 2}
    return internal or {root}


def dfs_internal_nodes(
    nodes: Iterable[int], edges: Iterable[Edge], root: Optional[int] = None
) -> Set[int]:
    """DFS ağacının İÇ (yaprak olmayan) düğümleri — Savage 1982 (brief G3).

    Bu MERKEZİ referanstır: DFS-Spanning-Backbone'un dağıtık jeton gezintisinin ÜRETMESİ
    gereken kümeyi tanımlar ve testlerde ona karşı kıyaslanır. Kendisi bir kol
    DEĞİLDİR; kol, aynı kümeyi dört ilkelle kurmak zorundadır.

    Kök verilmezse en küçük kimlik seçilir; DFS komşuları sıralı gezer, yani
    ağaç deterministiktir.
    """
    adj = adjacency(nodes, edges)
    root = min(adj) if root is None else int(root)
    seen = {root}
    deg = {v: 0 for v in adj}
    stack = [root]
    while stack:
        u = stack[-1]
        nxt = next((v for v in sorted(adj[u]) if v not in seen), None)
        if nxt is None:
            stack.pop()
            continue
        seen.add(nxt)
        deg[u] += 1
        deg[nxt] += 1  # ağaç DERECESİ: ebeveyn + çocuklar
        stack.append(nxt)
    internal = {v for v in adj if deg[v] >= 2}
    return internal or {root}


def dfs_backbone_roles(
    nodes: Iterable[int],
    edges: Iterable[Edge],
    weight: Dict[int, float],
    root: Optional[int] = None,
) -> Dict[int, Role]:
    """DFS-Spanning-Backbone'un merkezi referans tohumu (kolun kendisi DEĞİL)."""
    assert_connected(nodes, edges)
    adj = adjacency(nodes, edges)
    internal = dfs_internal_nodes(nodes, edges, root)
    return roles_from_backbone(internal, adj, default_key(adj, weight))


def roles_from_backbone(
    backbone: Set[int], adj: Dict[int, Set[int]], key: Dict[int, Tuple]
) -> Dict[int, Role]:
    """Omurga düğümlerini MIS / CONNECTOR'a böl, gerisi OUT.

    Dikiş sözleşmesi rollerin MIS/CONNECTOR/OUT olmasını ister ve `mis_nbrs`
    alanını MIS rolündeki komşularla doldurur; Faz 1b ve 3-atlama kuralı onu
    okur. MIS'i BAĞIMSIZ tutmak bu yüzden anlamlıdır: omurganın tamamını MIS
    işaretlemek alanın taşıdığı anlamı bozar ve sonraki fazlara yalan söyler.
    Bağımsız altküme anahtar sırasıyla açgözlü seçilir (deterministik), kalan
    omurga düğümleri CONNECTOR olur.
    """
    roles: Dict[int, Role] = {v: Role.OUT for v in adj}
    mis: Set[int] = set()
    for v in sorted(backbone, key=lambda x: key[x]):
        if not (adj[v] & mis):
            mis.add(v)
    for v in backbone:
        roles[v] = Role.MIS if v in mis else Role.CONNECTOR
    return roles


def default_key(adj: Dict[int, Set[int]], weight: Dict[int, float]) -> Dict[int, Tuple]:
    """key(v) = (w(v)/(deg(v)+1), v). BB-CVC'nin kendi sırası, aynı kırılma."""
    return {v: (weight[v] / (len(adj[v]) + 1), v) for v in adj}


def mst_backbone_roles(
    nodes: Iterable[int], edges: Iterable[Edge], weight: Dict[int, float]
) -> Dict[int, Role]:
    """GHS-MST-Backbone'un tohumu: merkezi MST -> iç düğümler -> MIS/CONNECTOR/OUT."""
    assert_connected(nodes, edges)
    adj = adjacency(nodes, edges)
    internal = mst_internal_nodes(nodes, edges, weight)
    return roles_from_backbone(internal, adj, default_key(adj, weight))


# ==========================================================================
# 3. GHS-MST-Backbone düğümü
# ==========================================================================
class V4MstNode(BbcvcNode):
    """Faz 1 = merkezi MST'nin iç düğümleri. TAM BİLGİLİ KOL.

    Düğüme rolü DOĞRUDAN VERİLİR; kendisi keşfetmez. I1 bilerek çiğnenir ve
    kolun mesaj maliyeti bu yüzden raporlanmaz. Faz 2-5 hiç değişmez.
    """

    def __init__(
        self,
        weight,
        platform,
        params=None,
        capacity_k: int = 2,
        seed_role: Role = Role.OUT,
    ) -> None:
        super().__init__(weight, platform, params, capacity_k)
        self._seed_role = Role(seed_role)

    def _backbone_step(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        if self.phase == PH_MIS:
            self.role = self._seed_role
            self.phase = PH_CONN
            self._log("mst_seeded", role=int(self._seed_role))
            self._touch()
            return
        # Bir bariyer adımı BEKLENİR: roller tohumlansa da komşuların rol ve
        # mis_nbrs bilgisinin bir HELLO turu yayılması gerekir, çünkü Faz 2
        # ve 3-atlama kuralı onları okur. Tohumlamak yayılmayı gereksiz
        # kılmaz, yalnız pazarlığı gereksiz kılar.
        if self.phase == PH_CONN and self._barrier(nb, PH_CONN):
            self.phase = PH_COVER
            self._touch()


def build_v4_nodes(net, weights, k: int, edges, params=None):
    """GHS-MST-Backbone düğümleri: roller merkezi MST'den tohumlanır.

    `bbcvc.build_nodes` düğüm sınıfını sabitlediği için burada kendi
    kurucumuz var; bu, Faz 2-5 kodunun kopyalanması DEĞİLDİR, yalnız
    nesne kurulumudur.
    """
    roles = mst_backbone_roles(sorted(weights), edges, weights)
    return {
        nid: V4MstNode(weights[nid], net.port(nid), params, k, roles[nid])
        for nid in net.nodes
    }


# ==========================================================================
# 4. Kol karşılaştırma ölçütü (brief §6)
#     Ekip lideri kararı: uygunsuzluk oranı DİPNOT DEĞİL, kol başına ölçüttür.
#     Ancak iki kip AYRI raporlanmalıdır, çünkü biri ilginç diğeri örnekleme:
#       * uygunsuz ÖRNEK: örneğin kendisi k altında çözümsüz. Kolun suçu
#         değildir ve kollar AYNI örneklerde koştuğu sürece hepsinde aynıdır.
#       * uygunsuz ÖRTÜ: örnek çözülebilir, ama KOLUN ürettiği örtü kapasite
#         bakımından uygun değil. ASIL İLGİNÇ OLAN BUDUR ve omurga şeklinin
#         bir sonucudur, yani dikişin değiştirdiği şeyin ta kendisidir.
#     İkisini tek sayıda toplamak, omurga farkını örnekleme gürültüsüyle
#     karıştırır ve karşılaştırmayı anlamsızlaştırır.
# ==========================================================================
INFEASIBLE_INSTANCE = "infeasible_instance"
INFEASIBLE_COVER = "infeasible_cover"
UNRESOLVED = "unresolved"
TRUNCATED = "truncated"
VALID = "valid"


def classify_outcome(
    arm_infeasible: bool,
    instance_infeasible: bool,
    arm_unresolved: bool = False,
    arm_converged: bool = True,
) -> str:
    """Bir koşumun sonucunu DÖRT kovadan birine koy.

    `instance_infeasible` MERKEZİ çözücüden gelir ve KOLDAN BAĞIMSIZDIR; aynı
    örnek için bütün kollarda aynı değerdir ve İLK bakılan şeydir. Bu yüzden
    kollar arası fark örnek kovasında ASLA görünemez.

    `arm_unresolved` AYRI bir kovadır, VALID DEĞİL. Çözülemeden biten bir
    koşum geçerli bir cevap üretmemiştir; onu VALID saymak kolu olduğundan
    başarılı gösterirdi. İlk sürümüm yalnız `infeasible`a bakıyordu ve tam
    olarak bu hatayı yapıyordu.

    `arm_converged` False ise koşum BÜTÇEYLE KESİLMİŞTİR ve TRUNCATED kovasına
    düşer, VALID'e değil. Ölçüldü: aynı örnekte max_ms=3000'de `converged`
    False iken `infeasible` ve `unresolved` İKİSİ DE False ve sahiplik bile TAM
    (15/15) — kesilmiş bir koşum başarılıdan başka hiçbir alanla ayırt
    edilemiyor. Kesilme kolun kendi bayraklarından ÖNCE bakılır: bitmemiş bir
    koşumun "uygun" ya da "çözülemedi" demesi anlamsızdır.

    K4/k=1 TUZAĞI (ekip lideri bildirdi, bb-algo'da): o örnek en kaba sayım
    sınırını çiğnediği hâlde (n*k = 4 < m = 6) `unresolved` döndürüyor.
    Burada ZARARSIZDIR, çünkü örnek verdikti ÖNCE bakılır ve merkezi çözücü
    onu uygunsuz ilan eder; INFEASIBLE_INSTANCE kovasına düşer, bütün
    kollarda aynı olur ve kol farkını kirletmez.
    """
    if instance_infeasible:
        return INFEASIBLE_INSTANCE
    if not arm_converged:
        return TRUNCATED
    if arm_infeasible:
        return INFEASIBLE_COVER
    return UNRESOLVED if arm_unresolved else VALID


def relay_escalate_count(run) -> int:
    """`relay_escalate` olayı: aşırı yüklü düğüm örtünün İÇİNDE kaldı.

    bb-algo'nun ölçtüğü kip budur. TEK BAŞINA "Faz 4 düzeltemedi"nin tam
    sayacı DEĞİLDİR: aşırı yüklü düğümü hiç olmayan, yani maxF <= k olduğu
    hâlde kapasite bakımından uygunsuz biten koşumlarda SIFIR okur (ölçüldü:
    udg_instance(100, 0.15, 4), k=4, maxF=2, uygunsuz). O yüzden ayrı
    raporlanır, toplanmaz.
    """
    net = getattr(run, "net", None)
    if net is None:
        return 0
    return sum(
        1 for r in getattr(net, "log_records", []) if r.get("event") == "relay_escalate"
    )


def forced_load_max(run, adj: Dict[int, Set[int]]) -> int:
    """max F(v) = örtüdeki bir düğümün örtü dışı komşu sayısı (brief G4)."""
    C = set(run.cover)
    if not C:
        return 0
    return max(sum(1 for u in adj[v] if u not in C) for v in C)


def saturated_flexible_edges(
    run, adj: Dict[int, Set[int]], k: int
) -> List[Tuple[int, int]]:
    """Doygun esnek kenar: iki ucu da örtüde, iki ucu da k kenar sahiplenmiş.

    EKİP LİDERİ ÖLÇÜMÜ (seed 4). Bu, `F(v) > k`nın SESSİZ kaldığı uygunsuzluk
    sınıfının yerel olarak görülebilen tetikleyicisidir: hiçbir uç aşırı yüklü
    değildir, dolayısıyla hem `F(v) > k` hem de onun iki-atlamalı hâli olan
    relay eskalasyonu susar, ama koşum yine de kapasite bakımından uygunsuz
    biter (ölçüldü: maxF=2, k=4, uygunsuz).

    AÇGÖZLÜDÜR, KESİN DEĞİLDİR: uygun örneklerde de ateşler. Bu yüzden ÜÇÜNCÜ
    BİR VERDİKT SÜTUNU OLAMAZ; `classify_outcome` üç kovada kalır. Kol başına
    TEŞHİS olarak tutulur, çünkü relay sayacının ayıramadığı yerde kolları
    ayırabilir. Uygunsuzluğu İLAN ETMEZ: ekip liderinin ölçtüğü gibi engel
    G[C] içinde 13 atlama boyunca uzanıyor ve 1..4 yarıçaplı hiçbir topta
    sayım ihlali görünmüyor, yani hiçbir yerel yüklem uygunsuzluğu kanıtlayamaz.
    """
    C = set(run.cover)
    owned: Dict[int, int] = {v: 0 for v in C}
    for e, v in getattr(run, "owner", {}).items():
        if v in owned:
            owned[v] += 1
    out: List[Tuple[int, int]] = []
    for u, v in sorted({(min(a, b), max(a, b)) for a in C for b in adj[a] if b in C}):
        if owned.get(u, 0) >= k and owned.get(v, 0) >= k:
            out.append((u, v))
    return out


def arm_row(run, adj: Dict[int, Set[int]], k: int, instance_infeasible: bool) -> Dict:
    """Bir kol-örnek koşumunun karşılaştırma satırı.

    İki uygunsuzluk kipi AYRI sütunlardır ve toplanmaz; `relay_escalate` ile
    `saturated_flexible` ise verdikt değil TEŞHİStir.
    """
    return {
        "verdict": classify_outcome(
            bool(run.infeasible),
            instance_infeasible,
            bool(getattr(run, "unresolved", False)),
            bool(getattr(run, "converged", True)),
        ),
        "weight": run.total_weight,
        "cover_size": len(run.cover),
        "max_forced_load": forced_load_max(run, adj),
        "relay_escalate": relay_escalate_count(run),
        "saturated_flexible": len(saturated_flexible_edges(run, adj, k)),
        "unowned_edges": len(
            unowned_edges(run, [(u, v) for u in adj for v in adj[u] if u < v])
        ),
        "double_owned_edges": len(double_owned_edges(run)),
        "slots": run.slots,
        "tx": run.tx,
    }


# ==========================================================================
# 5. DFS-Spanning-Backbone: dağıtık DFS jeton gezintisi (brief §6, Savage 1982 / G3)
# ==========================================================================
class V1DfsNode(BbcvcNode):
    """Faz 1 = DFS ağacının iç düğümleri. TAM DAĞITIK; tohumlama YOKTUR.

    BAŞLATICI SEÇİMİ: EN KÜÇÜK KİMLİK JETON BİRLEŞTİRMESİ (ekip lideri kararı).
    Her yerel en küçük kimlik bir gezinti başlatır, jeton başlatıcısını taşır
    ve daha küçük başlatıcılı bir gezinti daha büyüğünü ÖNALIR. Böylece ayrı
    bir seçim fazı olmadan tek bir kapsayan ağaç kalır.

    NEDEN TOHUMLAMA DEĞİL. DFS-Spanning-Backbone'un varlık sebebi, kanıtlı 2-yaklaşımın DAĞITIK
    ortamda NEYE MAL OLDUĞUNU göstermektir. Kökü dışarıdan vermek kolu kısmen
    tam bilgili yapar ve tam da ölçmek istediğimiz maliyeti siler. Önalınan
    kısmi gezintiler israf değil, ÖLÇÜLEN ŞEYİN KENDİSİDİR; bu yüzden
    `dfs_preempted` sayacıyla ayrıca görünür kılınır (ekip lideri şartı:
    maliyet çıkarsanabilir değil OKUNABİLİR olmalı).

    S6 İLKESİYLE İLİŞKİ. Bu, 5b'nin en-küçük-kimlik KÖKÜYLE aynı soru DEĞİLDİR
    ve iki yanıtın eşleşmesi gerekmez. 5b'nin kökü KALICI ve AYRICALIKLIDIR:
    bütün koşum boyunca yaşar ve toplama ondan geçer. DFS-Spanning-Backbone'un başlatıcısı ise
    GEÇİCİDİR: gezintiyi başlatır ve jeton hemen ilerler, hiçbir düğümde özel
    bir rol kalmaz. "Hiçbir düğüm küresel bilgi tutamaz" okumasında ikisi de
    uygundur; daha sert olan "hiçbir düğüm ayrıcalıklı olamaz" okumasında 5b
    tartışmalıdır ve DFS-Spanning-Backbone yine uygundur, çünkü tek adım süren ayrıcalık
    koordinatör değildir.

    ======================================================================
    DURUM: BU KOL KOŞMAZ. KASITLI OLARAK YARIM BIRAKILMIŞTIR (ekip lideri
    kararı: kapsamla, aceleye getirme). Bağımlılıkların ikisi de İNDİ —
    `wire.Token` (init alanlı) ve `node_factory` yerinde — yani eksik olan
    bağımlılık değil, DAĞITIK DENETİM katmanıdır.

    NE VAR: durum, karar mantığı (`dfs_next_offer`, `dfs_on_token`,
    `dfs_visited_in`) ve `simulate_dfs_walk`. Protokol — yerel en küçük
    başlatıcılar, jeton teklifi, ziyaretliye çarpıp dönme, küçük başlatıcının
    önalması — 310 kıyas örneğinin HEPSİNDE referans DFS ağacıyla birebir
    aynı kümeyi veriyor, SIFIR uyuşmazlık. Yani protokolün DOĞRULUĞU telden
    bağımsız olarak kanıtlanmıştır; devralan kişi bunu yeniden kurmaz.

    NE YOK (üç parça; ikisi ayrı birer dağıtık problem, tutkal değil):

    1. GEZİNTİYİ SÜRME — `_backbone_step` ezmesi + `_on_algo` üzerinde
       TOKEN/TOKEN_DONE işleyicileri. Mevcut `_arm`/`_retry_pending`/`_reply`
       ACK makinesi yeniden kullanılır. Tek gerçek tutkal parçası budur.

    2. DAĞITIK SONLANMA SAPTAMA. Başlatıcı kendi yığını boşalınca gezintinin
       bittiğini bilir; BAŞKA HİÇBİR DÜĞÜM BİLMEZ. Faz 1, ağaç tamamlanmadan
       PH_COVER'a ilerlememelidir. `_barrier` BURADA İŞE YARAMAZ: faz üzerinde
       senkronlar, oysa karar verilmesi gereken şey tam da fazın ilerleyip
       ilerlemeyeceğidir. Kendi mekanizmasını ister (başlatıcıdan tamamlanma
       seli ya da daha incesi) ve önalmayla etkileşir, çünkü bir gezinti yolun
       ortasında terk edilebilir.

    3. OMURGA ÜZERİNDE DAĞITIK MIS. GHS-MST-Backbone bu bölmeyi MERKEZİ yapar, çünkü tam
       bilgili bir koldur; DFS-Spanning-Backbone KATEGORİK OLARAK YAPAMAZ. Donmuş anahtarlar
       çözümü elverişli kılar (bir omurga düğümü, kendisinden küçük anahtarlı
       hiçbir omurga komşusu MIS değilse MIS olur — `_rule_mis`in B'ye
       kısıtlanmış hâli), ama bu, birincinin üstüne binen İKİNCİ bir dağıtık
       algoritmadır ve kendi yakınsaması ile kendi bariyeri vardır.

    SESSİZ BOZULMA UYARISI (bb-algo). İç düğümlerin hepsi CONNECTOR
    işaretlenip hiçbiri MIS olmazsa `mis_nbrs` her yerde BOŞ kalır ve 3-atlama
    boşluk kuralı SESSİZCE hiç ateşlemez. Çökmez; sessizce hiçbir şey yapmaz.
    Yani (3) yapılmazsa kol koşar, yakınsar, temiz sayaç raporlar ve yanlış
    olur — bu projede bugün defalarca görülen arıza biçiminin ta kendisi.

    ÖLÇÜM ŞARTI RESMEN KARŞILANMAMIŞTIR. Ekip lideri önalınan gezintilerin
    bedelinin ÇIKARSANABİLİR değil OKUNABİLİR olmasını şart koşmuştu.
    `dfs_preempted` GERÇEK BİR KOŞUMDA HİÇ ARTMAMIŞTIR, çünkü kol hiç
    koşmamıştır. `simulate_dfs_walk` bunu kapatmaz: yalnız kazanan gezintiyi
    işletir, bu yüzden sayacı `offers_winning_walk_only` adını taşır.

    NEDEN YARIM BIRAKMAK YARIM YAPMAKTAN İYİ. Sonlanma ya da MIS fazı ince
    biçimde yanlış olan, ama KOŞAN bir DFS-Spanning-Backbone, üç kollu tabloya makul görünen
    sayılar sokardı. Bugün bulunan Faz 4 kusurlarının üçü de yakınsadı, temiz
    sayaç raporladı ve yanlıştı; kesilmiş koşumlar tam sahiplik haritasıyla
    başarılı göründü. Koşmayan bir kol, sonuçlara sessizce yanlış sayı sokan
    bir koldan iyidir ve yokluğu yazılı bir kısıttır.
    ======================================================================
    """

    def __init__(self, weight, platform, params=None, capacity_k: int = 2) -> None:
        super().__init__(weight, platform, params, capacity_k)
        self.dfs_init: Optional[int] = None  # ait olduğum gezintinin başlatıcısı
        self.dfs_parent: Optional[int] = None  # jetonu bana veren
        self.dfs_tree_deg = 0  # ağaç derecesi: ebeveyn + çocuklar
        self.dfs_tried: Set[int] = set()  # bu gezintide teklif ettiklerim
        self.dfs_holding = False
        self.dfs_preempted = 0  # how many times a smaller initiator took over
        self.dfs_offers = 0  # how many TOKEN offers I sent
        # -- distributed control state (see the driver below) --------------
        self._v1_started = False        # did I start my own walk?
        self._v1_offer_out = None       # neighbour I am currently offering to
        self._v1_done_seen = False      # have I forwarded the completion flood?
        self._v1_in_backbone = False    # frozen at DFS_DONE
        self._v1_mis_claim = None       # None = undecided, True = MIS
        self._v1_bb_members = set()     # neighbours that announced backbone
        self._v1_bb_decided = {}        # nid -> True (MIS) / False (CONNECTOR)

    # -- ölçüm ----------------------------------------------------------
    @property
    def dfs_internal(self) -> bool:
        """Ağaç derecesi >= 2 olan düğüm İÇ düğümdür, yani omurgadadır."""
        return self.dfs_tree_deg >= 2

    def _adopt_walk(self, init: int, parent: Optional[int]) -> None:
        """Daha küçük başlatıcılı bir gezintiye geç: eski durum ATILIR.

        Önalma bir yama değildir; eski gezintinin bütün yerel durumu düşer ve
        düğüm yeni ağaçta sıfırdan başlar. Yamalamak iki ağacın parçalarını
        karıştırır ve ortaya kapsayan olmayan bir yapı çıkarırdı.
        """
        if self.dfs_init is not None and init < self.dfs_init:
            self.dfs_preempted += 1
            self._log("dfs_preempted", old=self.dfs_init, new=init)
        self.dfs_init = init
        self.dfs_parent = parent
        self.dfs_tree_deg = 0 if parent is None else 1
        self.dfs_tried = set()

    # -- KARAR MANTIĞI: telden BAĞIMSIZ -------------------------------------
    # Aşağıdaki üç yöntem hiçbir şey kodlamaz ve hiçbir şey göndermez; yalnız
    # NE YAPILACAĞINA karar verir. Böylece protokol, `wire.Token` inmeden
    # sınanabilir ve indiğinde geriye yalnız ince bir gönderme/alma tutkalı
    # kalır. Mantığı taşımadan önce doğrulamanın tek yolu budur.

    def dfs_next_offer(self, neighbours: Sequence[int]) -> Optional[int]:
        """Jetonu sırada kime teklif edeyim? Denenmemiş en küçük kimlik.

        Ziyaret edilmişlik SORULMAZ: bilinemez. Teklif edilen komşu zaten
        ziyaretliyse jetonu hemen geri yollar. Bu, deneme-yanılma DFS'idir ve
        2m mesaja kadar çıkabilir; DFS-Spanning-Backbone'un ölçtüğü maliyet tam da budur, o
        yüzden eniyilenmez.
        """
        for v in sorted(neighbours):
            if v != self.dfs_parent and v not in self.dfs_tried:
                return v
        return None

    def dfs_on_token(self, init: int, sender: int) -> str:
        """Bir TOKEN geldi. 'accept' | 'reject' | 'preempt' kararı ver."""
        if self.dfs_init is None:
            return "accept"  # hiç gezintiye ait değilim
        if init < self.dfs_init:
            return "preempt"  # daha küçük başlatıcı kazanır
        if init > self.dfs_init:
            return "reject"  # kendi gezintim daha iyi
        return "reject" if self.dfs_visited_in(init) else "accept"

    def dfs_visited_in(self, init: int) -> bool:
        """Bu gezintide zaten ziyaret edildim mi?"""
        return self.dfs_init == init and (
            self.dfs_parent is not None or self.dfs_tree_deg > 0 or self.dfs_holding
        )

    # ==================================================================
    # DISTRIBUTED CONTROL LAYER
    # ==================================================================
    # Three pieces, written in this order because each needs the one before it:
    #   1a  drive the walk            TOKEN / TOKEN_DONE
    #   1b  detect global termination DFS_DONE flood over the finished tree
    #   1c  maximal independent set restricted to the backbone   BB_MIS
    #
    # Nothing here reads a graph, an adjacency list or a central solver. Every
    # decision uses `self.nbrs` (frame-derived neighbour records) and frozen
    # keys, which is the same information every other arm gets.

    #: BB_MIS codes. Separate codes rather than one "state" byte, so that a
    #: node can distinguish "has not decided yet" from "decided CONNECTOR":
    #: conflating them is what made an earlier infeasibility witness unsound.
    BB_JOINED = 0     # I am in the backbone; I have not decided MIS yet
    BB_IS_MIS = 1     # I claim MIS
    BB_NOT_MIS = 2    # I am in the backbone and I am NOT MIS

    def _edge_nbrs(self, nb):
        """Verified bidirectional neighbours. The only topology a node sees."""
        return [n for n in nb if n.is_edge]

    def _nbr_by_id(self, nid):
        n = self.nbrs.get(nid)
        return n if (n is not None and n.is_edge) else None

    # ---------------------------------------------------------- phase 1 seam
    def _backbone_step(self, now, nb):
        """Phase 1 for DFS-Spanning-Backbone: token walk, then termination, then backbone MIS."""
        edges = self._edge_nbrs(nb)
        if not edges:
            # An isolated node is its own tree: degree 0, so it is not internal.
            self._v1_finish_roles(now, [])
            return
        if self.phase == PH_MIS:
            self._v1_walk_step(now, edges)
        elif self.phase == PH_CONN:
            self._v1_mis_step(now, edges)

    # ------------------------------------------------------------- 1a  walk
    def _v1_walk_step(self, now, edges):
        """Start a walk if I am a local minimum; otherwise drive the one I hold."""
        if self.dfs_init is None and not self._v1_started:
            ids = [n.nid for n in edges]
            if self.nid < min(ids):
                # Local minimum: start my own walk. No election phase; a walk
                # with a smaller initiator absorbs a larger one on contact.
                self._v1_started = True
                self._adopt_walk(self.nid, None)
                self.dfs_holding = True
                self._log("dfs_walk_start", init=self.nid)
        if self.dfs_holding and not self._v1_offer_out:
            self._v1_offer_next(now, edges)

    def _v1_offer_next(self, now, edges):
        """Offer the token to the next untried neighbour, or backtrack."""
        target = self.dfs_next_offer([n.nid for n in edges])
        if target is not None:
            n = self._nbr_by_id(target)
            if n is None:
                self.dfs_tried.add(target)
                return
            self.dfs_tried.add(target)
            self.dfs_offers += 1
            self._v1_offer_out = target
            self._v1_send_token(now, n, MsgType.TOKEN, self.dfs_init)
            return
        # Nothing left to try: this subtree is finished.
        self.dfs_holding = False
        if self.dfs_parent is None:
            # I am the initiator and my stack is empty: the walk is complete.
            # NOBODY ELSE KNOWS THIS YET, which is what 1b exists to fix.
            self._v1_walk_complete(now)
        else:
            p = self._nbr_by_id(self.dfs_parent)
            if p is not None:
                self._v1_send_token(now, p, MsgType.TOKEN_DONE, self.dfs_init)

    def _v1_send_token(self, now, n, mtype, init):
        seq = self._next_seq()
        payload = wire.encode(wire.Token(mtype, self.nid, seq, init))
        self._ucast(n, payload)

    def _on_v1_token(self, now, n, msg):
        """A TOKEN arrived: either an offer to me, or my own offer bounced back.

        HOW A PARENT LEARNS WHETHER ITS OFFER WAS TAKEN. A node that refuses
        returns the TOKEN ITSELF ("here, take it back"); a node that accepts
        keeps it and later sends TOKEN_DONE when its subtree is finished. So the
        two replies are different message types and the parent can tell them
        apart without a new field:

            TOKEN back      -> refused, NOT a child, try the next neighbour
            TOKEN_DONE back -> accepted and finished, COUNT IT AS A CHILD

        Without that distinction a parent cannot count children, every tree
        degree stays 0, no node is ever internal and the backbone comes out
        empty -- which is exactly what the first version of this driver did.
        """
        if self._v1_offer_out == n.nid and msg.init == self.dfs_init:
            # My own offer bounced: the peer was already in this walk.
            self._v1_offer_out = None
            self.dfs_holding = True
            return
        decision = self.dfs_on_token(msg.init, n.nid)
        if decision == "reject":
            self._v1_send_token(now, n, MsgType.TOKEN, msg.init)   # bounce back
            return
        # accept or preempt: both adopt the incoming walk, and `_adopt_walk`
        # counts the preemption when the initiator is smaller than mine.
        self._adopt_walk(msg.init, n.nid)
        self.dfs_tree_deg = 1            # the edge to my parent
        self.dfs_holding = True
        self._v1_offer_out = None
        self._v1_done_seen = False

    def _on_v1_token_done(self, now, n, msg):
        """A child finished its subtree. Count it and carry on."""
        if msg.init != self.dfs_init:
            return                        # stale: belongs to an absorbed walk
        if self._v1_offer_out == n.nid:
            self._v1_offer_out = None
            self.dfs_tree_deg += 1        # that neighbour IS a child of mine
        self.dfs_holding = True

    def _v1_walk_complete(self, now):
        """Initiator only: flood DFS_DONE so every node learns phase 1 is over."""
        self._v1_done_seen = True
        self._log("dfs_walk_complete", init=self.dfs_init,
                  offers=self.dfs_offers, preempted=self.dfs_preempted)
        self._v1_flood_done(now)
        # The initiator must leave phase 1 too. It learns the walk is over from
        # its own empty stack rather than from the flood, so it will never
        # receive the DFS_DONE that moves everybody else on.
        self._v1_enter_mis(now)

    def _v1_flood_done(self, now):
        """Flood the completion over verified neighbours. Idempotent by `init`."""
        seq = self._next_seq()
        payload = wire.encode(wire.Token(MsgType.DFS_DONE, self.nid, seq,
                                         self.dfs_init))
        self._bcast(payload)

    def _on_v1_done(self, now, n, msg):
        """Termination flood. Freeze the tree, then move to the MIS sub-phase."""
        if self.dfs_init is not None and msg.init > self.dfs_init:
            return                        # a larger walk cannot end mine
        if self._v1_done_seen and msg.init == self.dfs_init:
            return                        # already forwarded: keeps it finite
        if self.dfs_init is None or msg.init < self.dfs_init:
            self._adopt_walk(msg.init, n.nid)
            self.dfs_tree_deg = 1
        self._v1_done_seen = True
        self._v1_flood_done(now)          # forward once
        self._v1_enter_mis(now)

    # -------------------------------------------------------------- 1b -> 1c
    def _v1_enter_mis(self, now):
        """Tree degrees are frozen. Announce backbone membership and start MIS."""
        if self.phase != PH_MIS:
            return
        self.phase = PH_CONN
        self._v1_in_backbone = self.dfs_internal
        if self._v1_in_backbone:
            self._v1_announce(now, self.BB_JOINED)

    def _v1_announce(self, now, code):
        seq = self._next_seq()
        self._bcast(wire.encode(wire.Join(MsgType.BB_MIS, self.nid, seq, code)))

    def _on_v1_bb(self, now, n, msg):
        """Backbone membership and MIS claims from a neighbour."""
        if msg.code == self.BB_JOINED:
            self._v1_bb_members.add(n.nid)
        elif msg.code == self.BB_IS_MIS:
            self._v1_bb_members.add(n.nid)
            self._v1_bb_decided[n.nid] = True
        elif msg.code == self.BB_NOT_MIS:
            self._v1_bb_members.add(n.nid)
            self._v1_bb_decided[n.nid] = False

    # --------------------------------------------------------------- 1c  MIS
    def _v1_mis_step(self, now, edges):
        """MIS restricted to the backbone, by frozen key order.

        A backbone node claims MIS when every smaller-key backbone neighbour has
        DECIDED and none of them is MIS. Keys are a total order, so the globally
        smallest backbone key decides first and the decision cascades; this
        terminates without a round counter.

        Without this step every internal node would be CONNECTOR, `mis_nbrs`
        would be empty everywhere, and the 3-hop gap rule would silently never
        fire. It would not crash; it would quietly do nothing.
        """
        if not self._v1_in_backbone:
            self._v1_finish_roles(now, edges)
            return
        if self._v1_mis_claim is not None:
            self._v1_finish_roles(now, edges)
            return
        mk = self._mykey()
        smaller = [n for n in edges
                   if n.nid in self._v1_bb_members and self._nkey(n) < mk]
        if any(self._v1_bb_decided.get(n.nid) is None for n in smaller):
            return                        # wait: somebody smaller has not decided
        if any(self._v1_bb_decided.get(n.nid) for n in smaller):
            self._v1_mis_claim = False
            self._v1_announce(now, self.BB_NOT_MIS)
        else:
            self._v1_mis_claim = True
            self._v1_announce(now, self.BB_IS_MIS)
        self._v1_finish_roles(now, edges)

    def _v1_finish_roles(self, now, edges):
        """Write `role` ONCE and advance to PH_COVER.

        Role is written exactly once, at the end, so role monotonicity (api I5)
        holds even though backbone membership and the MIS claim were negotiated
        over several steps.
        """
        if self.phase >= PH_COVER:
            return
        if self._v1_in_backbone:
            if self._v1_mis_claim is None:
                return
            self.role = Role.MIS if self._v1_mis_claim else Role.CONNECTOR
        else:
            self.role = Role.OUT
        self.phase = PH_COVER
        self._log("v1_phase1_done", role=int(self.role),
                  tree_deg=self.dfs_tree_deg, internal=self.dfs_internal,
                  offers=self.dfs_offers, preempted=self.dfs_preempted)

    # ------------------------------------------------------------- dispatch
    def _on_algo(self, now, src_mac, msg):
        """DFS-Spanning-Backbone handles its four control types and defers the rest to the base."""
        peer = msg.src
        n = self.nbrs.get(peer)
        if n is None or n.mac != src_mac or not n.is_edge:
            return
        mt = msg.mtype
        if mt is MsgType.TOKEN:
            self._on_v1_token(now, n, msg)
        elif mt is MsgType.TOKEN_DONE:
            self._on_v1_token_done(now, n, msg)
        elif mt is MsgType.DFS_DONE:
            self._on_v1_done(now, n, msg)
        elif mt is MsgType.BB_MIS:
            self._on_v1_bb(now, n, msg)
        else:
            super()._on_algo(now, src_mac, msg)


def simulate_dfs_walk(
    nodes: Iterable[int], edges: Iterable[Edge], trace: Optional[List] = None
) -> Tuple[Set[int], Dict[str, int]]:
    """DFS-Spanning-Backbone'un protokolünü TEL OLMADAN koştur ve iç düğüm kümesini döndür.

    Bu bir referans DFS DEĞİLDİR: gerçek dağıtık protokolü — yerel en küçük
    başlatıcılar, jeton teklifleri, ziyaret edilmişe çarpıp geri dönme,
    küçük başlatıcının önalması — mesaj mesaj işletir. Amacı, kodu ağın
    üstüne taşımadan ÖNCE `dfs_internal_nodes` ile aynı kümeye vardığını
    kanıtlamaktır; ağın üstünde bir hata çıkarsa suçlunun taşıma katmanı
    olduğunu bilmek için.

    KAPSAM UYARISI — BU SİMÜLASYON MALİYETİ ÖLÇMEZ. Yalnız KAZANAN gezintiyi
    işletir; önalınan gezintilerin çarçur ettiği teklifler sayılmaz. Dolayısıyla
    `offers` gerçek dağıtık maliyetin ALT SINIRIDIR ve tam da ekip liderinin
    "önalma bedeli görünür olmalı" şartını KARŞILAMAZ. Bu kasıtlıdır: eşzamanlı
    gezintilerin birbirini nerede kestiğini sadakatle modellemek, taşıma
    katmanının kendisini yeniden yazmak demektir ve o iş gerçek koşumun işidir.
    Buradaki amaç DOĞRULUKTUR — çıkan ağacın referans DFS ile aynı olduğunu
    telden önce kanıtlamak. Önalma bedeli `V1DfsNode.dfs_preempted` sayacından,
    gerçek koşumda ölçülecektir.
    """
    adj = adjacency(nodes, edges)
    init_of: Dict[int, Optional[int]] = {v: None for v in adj}
    parent: Dict[int, Optional[int]] = {v: None for v in adj}
    deg: Dict[int, int] = {v: 0 for v in adj}
    tried: Dict[int, Set[int]] = {v: set() for v in adj}
    stats = {
        "offers_winning_walk_only": 0,
        "rejects": 0,
        "preempted_walks": 0,
        "walks_started": 0,
    }

    # Yerel en küçükler gezinti başlatır; en küçük kimlik en sonda kazanır.
    starters = sorted(v for v in adj if all(v < u for u in adj[v]))
    for root in starters:
        stats["walks_started"] += 1
        winner = all(root < s for s in starters if s != root)
        for v in adj:
            if init_of[v] is not None and root < init_of[v]:
                stats["preempted_walks"] += 1
        if not winner:
            continue  # bu gezinti sonunda önalınacak; yerel durumu yazmayız
        for v in adj:
            init_of[v] = root
            parent[v] = None
            deg[v] = 0
            tried[v] = set()
        stack = [root]
        visited = {root}
        while stack:
            u = stack[-1]
            nxt = None
            for cand in sorted(adj[u]):
                if cand == parent[u] or cand in tried[u]:
                    continue
                tried[u].add(cand)
                stats["offers_winning_walk_only"] += 1
                if cand in visited:
                    stats["rejects"] += 1  # ziyaretli: jetonu hemen geri yollar
                    continue
                nxt = cand
                break
            if nxt is None:
                stack.pop()
                continue
            visited.add(nxt)
            parent[nxt] = u
            deg[u] += 1
            deg[nxt] += 1
            stack.append(nxt)
            if trace is not None:
                trace.append((u, nxt))
    internal = {v for v in adj if deg[v] >= 2}
    return (internal or {min(adj)}), stats


def unowned_edges(run, edges: Iterable[Edge]) -> List[Edge]:
    """Sahipsiz kenarlar. Boş olmalıdır: owner: E -> C TAM bir fonksiyondur.

    bb-algo'nun dosyasında bu denetim ÜÇ ayrı hatayı yakaladı ve üçü de farklı
    nedendendi: sıra numarası çakışması, yok sayılan bir dönüş değeri ve iki
    yönlü bir devralma yarışı. Üçünde de koşum yakınsadı, sayaçlar temiz
    okudu ve cevap yanlıştı — yani "koşum doğru görünüyordu" hiçbirini
    yakalamazdı. Brief §1 sahipliği çıktının parçası sayar, dolayısıyla eksik
    bir sahiplik geçerli bir cevap değildir, eksik bir rapor değil.

    Kollar Faz 4'ü değiştirmeden devraldığı için bu sınıf hata DFS-Spanning-Backbone ve GHS-MST-Backbone'a de
    miras kalır; ucuz olduğu için her koşumda denetlenir.
    """
    seen = {(min(u, v), max(u, v)) for u, v in getattr(run, "owner", {})}
    want = {(min(u, v), max(u, v)) for u, v in edges}
    return sorted(want - seen)


def double_owned_edges(run) -> List[Tuple[Edge, Tuple[int, ...]]]:
    """BİRDEN ÇOK düğümün sahiplendiği kenarlar ve sahipleri.

    DÜĞÜM BAŞINA `owned` KÜMELERİNDEN sayılır, `owner` HARİTASINDAN DEĞİL, ve
    fark bunun tamamıdır. Harita `owner[e] = nid` ile kurulur, yani ikinci
    yazan birinciyi SESSİZCE EZER: harita tam okur, her kenarın tam bir sahibi
    görünür, kimse aşırı yüklü görünmez ve doğrulayıcı temiz geçer. Çift
    sahiplik haritada TEMSİL EDİLEMEZ, dolayısıyla haritayı okuyan bir denetim
    onu HİÇBİR ZAMAN göremez; sayım TOPLANMADAN ÖNCE yapılmalıdır.

    Ekip liderinin ölçtüğü örnek: bir kenarı iki uç da sahiplendi, 150 kenar
    için 151 iddia, sahipsiz sıfır. Düğümün özel `owned` kümesi k=6'ya karşı
    7 kenar tuttuğu için düğüm doğru biçimde `unresolved` dedi ve hiç
    toparlanamadı — DÜĞÜM HAKLIYDI, harita yanıltıcıydı. Bu, bb-algo'nun
    kataloglara aldığı ailenin dördüncüsü ve TERS yönlüsüdür: onların üçü
    kenar KAYBEDİYORDU, bu biri kenar ÇOĞALTIYOR.

    Tanım gereği ihlaldir, muhasebe kazası değil: problem her kenarın TAM
    OLARAK BİR uca atanmasını ister ve kapasite savı buna dayanır.
    """
    claims: Dict[Edge, List[int]] = {}
    for nid, node in sorted(getattr(run, "nodes", {}).items()):
        for u, v in getattr(node, "owned", ()):  # düğümün ÖZEL kümesi
            claims.setdefault((min(u, v), max(u, v)), []).append(nid)
    return [(e, tuple(who)) for e, who in sorted(claims.items()) if len(who) > 1]


def assert_ownership_is_total(run, edges: Iterable[Edge]) -> None:
    """Her kenarın TAM OLARAK BİR sahibi olmalı. Eksik de fazla da hatadır.

    İlk sürümüm yalnız "en az bir" soruyordu ve çift sahipliği YAPISAL OLARAK
    göremiyordu: baktığı yer (`owner` haritası) kusuru temsil edemiyordu.
    """
    missing = unowned_edges(run, edges)
    if missing:
        raise RunInvalid(
            f"{len(missing)} kenarın sahibi yok, örnek: {missing[:5]}. "
            f"owner: E -> C tam bir fonksiyondur (brief §1); eksik sahiplik "
            f"geçerli bir cevap değildir."
        )
    doubled = double_owned_edges(run)
    if doubled:
        raise RunInvalid(
            f"{len(doubled)} kenar BİRDEN ÇOK sahiplenilmiş, örnek: "
            f"{doubled[:3]}. Her kenar tam olarak bir uca atanmalıdır; "
            f"`owner` haritası bunu gösteremez çünkü ikinci yazan birinciyi ezer."
        )


# ==========================================================================
# 8. Kıyas kümesi 0-tabanlı, kimlik uzayı 0'ı AYIRIYOR
# ==========================================================================
def relabel_from_one(
    weights: Dict[int, float], edges: Sequence[Edge]
) -> Tuple[Dict[int, float], List[Edge], Dict[int, int]]:
    """Düğümleri 1..n'e yeniden etiketle ve geri eşlemeyi döndür.

    NEDEN GEREKLİ. Dagdeviren örneklerinin HEPSİ (310/310) 0 kimlikli bir
    düğüm içerir, ama `hash16` 0 döndüremez (0 ayrılmıştır), dolayısıyla
    `mac_for_id(0)` ön görüntü bulamaz ve HİÇBİR kıyas örneği koşturulamaz.

    NEDEN AYIRMAYI KALDIRMIYORUZ. Ayırma yalnız bir belge cümlesi değil,
    taşıyıcı bir varsayım: `bbcvc.py` TREE mesajında kökü `self.tree_root or 0`
    ile kodlar, yani 0 "henüz kök yok" demektir. Kimlik uzayı 0'ı serbest
    bıraksaydı gerçek 0 köklü bir ağaç "köksüz"den ayırt edilemezdi ve hata
    sessiz olurdu. Bu yüzden düzeltme kimlik uzayında değil, GİRDİDE yapılır.

    Geri eşleme ölçüm içindir: örtü ve sahiplik özgün etiketlere çevrilerek
    raporlanır, yoksa sonuçlar kıyas kümesiyle karşılaştırılamaz.
    """
    order = sorted(weights)
    fwd = {old: i + 1 for i, old in enumerate(order)}
    back = {new: old for old, new in fwd.items()}
    w2 = {fwd[o]: weights[o] for o in order}
    e2 = sorted({(min(fwd[u], fwd[v]), max(fwd[u], fwd[v])) for u, v in edges})
    return w2, e2, back


def load_benchmark_instance(cell, seed: int):
    """Kıyas örneğini KOŞULABİLİR biçimde yükle: 1..n etiketli ve BAĞLI.

    İki kapı da ölçümden önce burada geçilir; brief §1 bağlı çizge ister ve
    kimlik uzayı 0'ı kabul etmez.
    """
    from ccvc.bb import matrix

    w, e = matrix.load_instance(matrix.instance_path(cell, seed))
    w2, e2, back = relabel_from_one(w, e)
    assert_connected(sorted(w2), e2)
    return w2, e2, back
