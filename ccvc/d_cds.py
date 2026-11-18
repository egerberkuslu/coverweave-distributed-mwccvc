#!/usr/bin/env python3
"""D-CDS (F4): bağlılığı ONARIMLA değil İNŞAYLA garantileyen dağıtık CCVC kolu.

Karşı kol D-REPAIR önce örtü kurup sonra kopan parçaları köprüler. Bu kol tam
tersini yapar: önce bağlı baskın küme (CDS) omurgasını kurar, örtüyü o omurganın
ÜSTÜNE büyütür ve böylece hiç onarım evresi olmaz.

--------------------------------------------------------------------------
NEDEN ONARIM GEREKMİYOR (kolun tek önermesi)
--------------------------------------------------------------------------
Omurga B, G'nin her bağlı bileşeninde bağlı ve BASKINDIR. Baskın olduğu için
B dışındaki her düğümün B'de bir komşusu vardır. Örtüye sonradan eklenen her
düğüm bu yüzden omurgaya bitişiktir, dolayısıyla C = B ∪ (ek düğümler) kendi
bileşeni içinde bağlı kalır. Ek düğümlerin birbirine bağlanması gerekmez;
hepsi omurgaya asılır, omurga zaten tek parçadır.

Bu önerme kodda yorum değil, KAPI: `DcdsNode._attachable` her katılımdan önce
"örtüde bir komşum var mı" diye bakar ve `strict_invariant` açıkken ihlalde
`DcdsInvariantError` atar. Testler bunu her tur, her eklemeden sonra ayrıca
dışarıdan da doğrular.

--------------------------------------------------------------------------
İŞARETLEME VE BUDAMA (Wu-Li), ÖNCELİK SEÇİMİ
--------------------------------------------------------------------------
İşaretleme kuralı (Wu & Li 1999): v kendini işaretler ⇔ N(v) içinde birbirine
komşu OLMAYAN en az iki düğüm vardır. Yani N(v) klik değilse v işaretlenir.
Bu saf yerel bir karardır ama iki atlama bilgisi ister: v, komşularının komşu
listelerini bilmelidir. Bu bilgi VARSAYILMAZ, `TWO_HOP_DIGEST` mesajıyla
KAZANILIR (tur 0 yayını, tur 1'de teslim).

Budama, işaretlemeden SONRA ve tur 1'deki ÖZGÜN işaretli kümeye göre uygulanır:

  Kural 1: v'nin işaretli bir u komşusu için N[v] ⊆ N[u] ve öncelik(u) <
           öncelik(v) ise v işareti düşer.
  Kural 2: v'nin işaretli, BİRBİRİNE KOMŞU iki komşusu u,x için
           N[v] ⊆ N[u] ∪ N[x] ve öncelik(u), öncelik(x) < öncelik(v) ise
           v işareti düşer.

ÖNCELİK = (ağırlık, kimlik), küçük olan yüksek önceliklidir. Wu-Li özgün
kuralda kimlik kullanır; burada bilerek ağırlık öne alındı, çünkü budama
"kimi ATACAĞINI" değil "kimi TUTACAĞINI" seçiyor: küçük anahtar tutulur,
büyük anahtarlı (pahalı) düğüm atılır. Kimlik yalnız eşitliği bozar, dolayısıyla
sıralama hâlâ TAM sıralamadır ve Wu-Li'nin budama ispatı geçerli kalır.
Tek sapma budur.

Baskınlık neden budamadan sağ çıkar (kodun dayandığı kısa ispat): v'nin işaretli
komşuları arasında EN YÜKSEK öncelikli olan u budanamaz, çünkü budanması için
N[u]'yu örten daha yüksek öncelikli işaretli bir komşusu gerekir; v ∈ N[u]
olduğundan o düğüm v'ye de komşudur ve u'dan daha yüksek önceliklidir, bu da
u'nun seçimiyle çelişir. Yani her v'nin kapalı komşuluğunda budamadan sağ çıkan
bir omurga düğümü kalır.

KLİK BİLEŞENİ İSTİSNASI. Wu-Li teoremi "tam çizge olmayan bağlı çizge" ister.
Bileşen bir klikse hiç kimse işaretlenmez, omurga boş kalır ve baskınlık
argümanı çöker. Bu durum YEREL olarak kesin saptanabilir: N(v) klik ise ve her
u ∈ N(v) için N[u] ⊆ N[v] ise, N[v] bileşenin tamamıdır ve kliktir. O zaman
omurga hiç kurulmaz, doğrudan klik kuralı işler: c=|N[v]| düğümlü klikte
c ≤ 2k iken en kötü öncelikli tek düğüm dışarıda bırakılır (klikte her altküme
bağlı olduğu için bağlılık bedavadır), c > 2k iken kapasite yüzünden hepsi
girer. Klik üyelerinin hepsi birbirinin komşusu olduğundan hepsi AYNI veriyle
AYNI kararı verir; anlaşma turu gerekmez.

--------------------------------------------------------------------------
İKİ ATLAMA TUZAĞI
--------------------------------------------------------------------------
Tezde bir kez yaşanan hata: adaydan BAĞIMSIZ bir iki-atlama özeti her adaya aynı
sabiti ekler, argmin'i değiştirmez ve iki-atlama kolu sessizce tek-atlama
kuralına çöker. Burada kullanılan iki-atlama büyüklüğü toplam/özet DEĞİL,
adayın kendisine koşullu bir YÜKLEM'dir: "N(v) içindeki şu iki düğüm komşu mu"
ve "N[v] ⊆ N[u] mu". İkisi de v'ye (ve u'ya) özgüdür; iki düğüm birebir aynı
tek-atlama profiline ve birebir aynı adaydan-bağımsız iki-atlama toplamlarına
sahipken bile FARKLI karar alırlar. `test_d_cds.py` bunu tam da böyle kurulmuş
bir çizgeyle sınar.

--------------------------------------------------------------------------
ESKİME (staleness) KARŞISINDA GÜVENLİK
--------------------------------------------------------------------------
Her komşu kaydı yaş taşır. Bozulabilecek üç karar var ve üçü de aynı ilkeyle
güvenli tarafa yaslanır: ŞÜPHE ÖRTMEDEN YANA ÇÖZÜLÜR. Çift örtme israftır,
açıkta kalan kenar güvenlik ihlalidir.

  1. İşaretleme: iki komşunun komşu olup olmadığı BİLİNMİYORSA "komşu değil"
     sayılır. Bu daha çok işaretlemeye, yani daha BÜYÜK omurgaya yol açar;
     baskınlık ve bağlılık yönünde güvenlidir, yalnız ağırlık artar.
  2. Budama: N[u] bilinmiyorsa ya da bayatsa budama YAPILMAZ. Yine büyük omurga
     yönünde hata.
  3. Örtü genişletmesi: komşunun skoru bilinmiyor ya da bayatsa, "ben katılmam,
     o katılır" varsayımı YAPILMAZ; düğüm kendisi katılır. İki uç birden
     katılırsa kenar iki kez örtülür (israf), hiçbiri katılmazsa kenar açıkta
     kalırdı (ihlal).
  4. Kapasite: "karşı uç alsın" ertelemesi en fazla `defer_limit` tur sürer,
     sonra düğüm kenarı kendisi talep eder.

Örtü üyeliği TEK YÖNLÜDÜR (düğüm örtüden hiç çıkmaz), bu yüzden bayat bir
"örtüde" beyanı asla yanlışa dönüşmez; bayatlık yalnız bir örtü üyesini
GÖRMEMEYE yol açar, olmayanı var sanmaya değil. `_attachable` kapısının
tek yönlü hata yapması bu sayededir.

--------------------------------------------------------------------------
KAPASİTE: SINIRLI UZUNLUKTA ARTIRICI YOL
--------------------------------------------------------------------------
Bir kenarı yalnız İKİ UCUNDAN biri sahiplenebilir. İki uç da doymuşsa üçüncü
bir düğüm o kenarı alamaz; alabileceği tek şey doymuş ucun BAŞKA bir kenarıdır.
Artırıcı yol tam olarak budur:

    v doymuş, (v,u) sahipsiz  ->  v'nin sahip olduğu (v,w) kenarını w devralır
    ->  v'de yer açılır  ->  v (v,u) kenarını alır

w da doymuşsa aynı istek w'den ileri taşınır; `augment_max_hops` bu zincirin
uzunluğunu sınırlar. Devir iki turluk el sıkışmadır: kabul eden taraf bir tur
sonra talep eder, bırakan taraf aynı turda hem `release_edges` hem
`accept_claims` bildirir (motorun I1 (3) açık onay kuralı). Zincir tümden
başarısızsa son çare, doymuş ucun örtüde OLMAYAN bir komşusunu örtüye alıp
aradaki kenarı ona devretmektir; o komşunun omurgada komşusu olduğu için
bağlılık yine bozulmaz.

Mesaj türleri: omurga evresi TWO_HOP_DIGEST/MARK_STATE/COVER_MEMBERSHIP,
kapasite evresi EDGE_CLAIM ve bu modülün tanımladığı iki tür. Motor mesajı
türüne göre gerçekten saydığı için yeni tür eklemek muhasebeyi bozmaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:  # paket olarak da, ccvc/ içinden de çalışsın
    from ccvc.bridge import CcvcGraph, Edge, verify
    from ccvc.engine import run_protocol
    from ccvc.engine_api import (
        COVER_MEMBERSHIP,
        EDGE_CLAIM,
        MARK_STATE,
        TWO_HOP_DIGEST,
        LocalView,
        Message,
        NodeDecision,
        NodeProtocol,
        RunResult,
    )
except ImportError:  # pragma: no cover
    from bridge import CcvcGraph, Edge, verify  # type: ignore
    from engine import run_protocol  # type: ignore
    from engine_api import (  # type: ignore
        COVER_MEMBERSHIP,
        EDGE_CLAIM,
        MARK_STATE,
        TWO_HOP_DIGEST,
        LocalView,
        Message,
        NodeDecision,
        NodeProtocol,
        RunResult,
    )

# kapasite artırıcı yolun iki mesaj türü (motor tür adını serbest sayar)
SHED_REQUEST = "CAPACITY_SHED_REQUEST"
SHED_ACCEPT = "CAPACITY_SHED_ACCEPT"

# bilinmeyen ağırlık: en kötü öncelik. 0.0 verilseydi bilinmeyen düğüm en ucuz
# görünür ve kendimizi onun lehine budardık; bu sessiz bir bağlılık riski olurdu.
WORST_PRIO: Tuple[float, int] = (float("inf"), 1 << 60)

# sabit evre turları
R_DIGEST = 0  # komşu listesi yayını
R_MARK = 1  # işaretleme kararı + yayını
R_BACKBONE = 2  # budama + omurga/klik katılımı + üyelik yayını
R_STEADY = 3  # örtü genişletmesi, talep, kapasite artırımı


# --------------------------------------------------------------------------
# PAYLAŞILAN WU-LI ÇEKİRDEĞİ
# --------------------------------------------------------------------------
# Aşağıdaki dört fonksiyon kuralların TEK kopyasıdır. Hem dağıtık düğüm
# (`DcdsNode`, kendi eksik defterini vererek) hem merkezi kâhin
# (`solve_cds_central`, tam çizgeyi vererek) bunları çağırır. Böylece "aynı
# işaretleme, aynı budama, aynı öncelik" bir söz değil, YAPISAL bir olgudur:
# iki kol arasındaki tek fark `adj_of`'un ne kadarını bildiğidir.
#
# adj_of(u) -> u'nun komşu kümesi, BİLİNMİYORSA None.
# prio_of(v) -> öncelik anahtarı; küçük olan tutulur.
# marked_of(v) -> v tur 1'de işaretlendi mi.


def pair_adjacent(a: int, b: int, adj_of) -> bool:
    """a~b mi? Bilinmiyorsa KOMŞU DEĞİL sayılır (daha çok işaretleme, güvenli yön)."""
    na = adj_of(a)
    if na is not None and b in na:
        return True
    nb = adj_of(b)
    if nb is not None and a in nb:
        return True
    return False


def wu_li_mark(nbrs: Set[int], adj_of) -> bool:
    """İşaretleme kuralı: N(v) klik DEĞİLSE işaretle. ADAYA KOŞULLU iki atlama yüklemi."""
    nb = sorted(nbrs)
    for i in range(len(nb)):
        for j in range(i + 1, len(nb)):
            if not pair_adjacent(nb[i], nb[j], adj_of):
                return True
    return False


def wu_li_prune(me: int, nbrs: Set[int], adj_of, marked_of, prio_of) -> bool:
    """Budama kural 1 ve 2; ÖZGÜN işaretli kümeye ve verilen TAM sıralamaya göre."""
    me_closed = set(nbrs) | {me}
    my_prio = prio_of(me)

    def closed(u: int) -> Optional[Set[int]]:
        a = adj_of(u)
        return None if a is None else (set(a) | {u})

    cand = [
        u
        for u in sorted(nbrs)
        if marked_of(u) and closed(u) is not None and prio_of(u) < my_prio
    ]
    for u in cand:  # kural 1: N[v] ⊆ N[u]
        if me_closed <= closed(u):  # type: ignore[operator]
            return True
    for i, u in enumerate(cand):  # kural 2: N[v] ⊆ N[u] ∪ N[x], u~x
        cu = closed(u)
        for x in cand[i + 1 :]:
            if not pair_adjacent(u, x, adj_of):
                continue
            if me_closed <= (cu | closed(x)):  # type: ignore[operator]
                return True
    return False


def clique_component_of(me: int, nbrs: Set[int], adj_of) -> Optional[List[int]]:
    """N[me] bütün bir bileşen VE klik ise üyelerini döndür, değilse None."""
    if not nbrs:
        return None
    closed = set(nbrs) | {me}
    for u in sorted(nbrs):
        cu = adj_of(u)
        if cu is None:
            return None  # bilgi eksik -> iddia etme
        if not (set(cu) | {u}) <= closed:
            return None  # u dışarı uzanıyor -> bileşen daha büyük
    nb = sorted(nbrs)
    for i in range(len(nb)):
        for j in range(i + 1, len(nb)):
            if not pair_adjacent(nb[i], nb[j], adj_of):
                return None
    return sorted(closed)


def clique_join(me: int, members: Sequence[int], k: int, prio_of) -> bool:
    """Klik bileşeninde me örtüye girmeli mi? Tüm üyeler aynı veriyle aynı sonucu bulur."""
    c = len(members)
    if c <= 1:
        return False
    if k > 0 and c <= 2 * k:
        return me != max(members, key=prio_of)  # en pahalıyı dışarıda bırak
    return True  # kapasite c-1 düğüme sığmıyor: herkes girsin


def extension_score(weight: float, me: int, needy: int) -> Tuple:
    """Genişletme skoru (D-GRCCVC ruhu). KÜÇÜK olan önce katılır. TAM sıralama."""
    return (round(weight / max(1, needy), 9), round(weight, 9), -int(needy), int(me))


class DcdsInvariantError(RuntimeError):
    """Bağlılık değişmezi çiğnendi: omurgaya bitişik olmayan bir düğüm örtüye giriyor."""


@dataclass
class DcdsParams:
    """Kolun ayarları. Hepsi yerel; hiçbiri küresel çizge büyüklüğüne bakmaz."""

    # Artırıcı yol zincirinin atlama sınırı. Ölçüldü (111 tam-çözülebilir rastgele
    # örnek): sınır 2'de 2 örnek, 3'te 1 örnek kapasite kapısından geçemiyor, 4'te
    # hiçbiri kalmıyor; bedeli ortalama %12 daha fazla mesaj. Varsayılan bu yüzden 4.
    augment_max_hops: int = 4
    shed_timeout: int = 4  # devir isteği cevapsızsa kaç tur sonra yeniden dene
    defer_limit: int = 2  # "karşı uç alsın" ertelemesinin üst sınırı
    forced_join_after: int = 8  # bitişik olmadan katılmadan önce beklenen tur
    absorb_after: int = 4  # doymuş örtü ucunun kenarını devralmak için beklenen tur
    give_up_after: int = 24  # umutsuz kenarı bırakıp susma eşiği
    strict_invariant: bool = True  # bitişiklik ihlalinde hata at
    # Budama önceliği: "weight" -> (ağırlık, kimlik), ucuz düğüm tutulur (bizim seçim);
    # "id" -> Wu-Li'nin özgün kimlik sıralaması. Ablasyon kolu bunu değiştirir.
    prune_priority: str = "weight"


@dataclass
class _Ledger:
    """Mesajla kazanılan bilgi + ne zaman kazanıldığı. Motor bunu tazelemez."""

    adj: Dict[int, Set[int]] = field(default_factory=dict)
    adj_round: Dict[int, int] = field(default_factory=dict)
    weight: Dict[int, float] = field(default_factory=dict)
    marked: Dict[int, bool] = field(default_factory=dict)
    in_cover: Dict[int, bool] = field(default_factory=dict)
    cover_round: Dict[int, int] = field(default_factory=dict)
    score: Dict[int, Tuple] = field(default_factory=dict)
    score_round: Dict[int, int] = field(default_factory=dict)
    spare: Dict[int, int] = field(default_factory=dict)
    spare_round: Dict[int, int] = field(default_factory=dict)


class DcdsNode(NodeProtocol):
    """Tek düğümün D-CDS protokolü. Örnek başına BİR düğüm; paylaşılan durum yok."""

    name = "d-cds"

    def __init__(self, params: Optional[DcdsParams] = None) -> None:
        self.p = params or DcdsParams()
        self.me: int = -1
        self.w: float = 0.0
        self.k: int = 0
        self._nbrs: Set[int] = set()
        self._led = _Ledger()
        # omurga evresi
        self._marked: Optional[bool] = None
        self._backbone: bool = False
        self._clique: Optional[List[int]] = None
        self._clique_member: Optional[bool] = None
        # kapasite evresi
        self._promise: Dict[int, int] = {}  # komşu -> hangi turda talep sözü verdim
        self._upstream: Optional[int] = None  # devir isteğini kimin adına taşıyorum
        self._upstream_until: int = -1  # taşıdığım isteğin son kullanma turu
        self._shed_until: int = -1  # bu tura kadar yeni devir isteği yok
        self._allow_join: bool = False  # son çare: örtü dışı komşuyu da çağır
        self._defer: Dict[int, int] = {}
        self._age: Dict[int, int] = {}  # sahipsiz kenarın kaç turdur sahipsiz olduğu
        self._hopeless: Set[int] = set()
        self._starve: int = 0
        self._last_say: Optional[Tuple] = None  # en son yayınladığım durum
        # rapor
        self.violations: int = 0
        self.notes: List[str] = []

    # ------------------------------------------------------------------
    # kurulum
    # ------------------------------------------------------------------
    def on_start(self, me: int, weight: float, capacity_k: int, degree: int) -> None:
        self.me = int(me)
        self.w = float(weight)
        self.k = int(capacity_k)

    # ------------------------------------------------------------------
    # bilgi sindirimi: gelen mesajlardan deftere yaz
    # ------------------------------------------------------------------
    def _ingest(self, view: LocalView) -> None:
        self.me = view.me
        self.w = view.weight
        self.k = view.capacity_k
        self._nbrs = set(view.incident)
        led = self._led
        for m in sorted(view.inbox, key=lambda x: (x.src, x.kind)):
            pay = m.payload or {}
            src = m.src
            if src not in self._nbrs:
                continue  # motor zaten engeller, yine de savunma
            if isinstance(pay.get("nbrs"), (list, tuple)):
                led.adj[src] = {int(x) for x in pay["nbrs"]}
                led.adj_round[src] = m.round_sent
            if "weight" in pay:
                led.weight[src] = float(pay["weight"])
            if "marked" in pay:
                led.marked[src] = bool(pay["marked"])
            if "in_cover" in pay:
                # üyelik TEK YÖNLÜ: bir kez doğruysa hep doğru (düğüm örtüden çıkmaz)
                if bool(pay["in_cover"]):
                    led.in_cover[src] = True
                led.cover_round[src] = m.round_sent
            if pay.get("score") is not None:
                led.score[src] = tuple(pay["score"])
                led.score_round[src] = m.round_sent
            if "remaining_capacity" in pay:
                led.spare[src] = int(pay["remaining_capacity"])
                led.spare_round[src] = m.round_sent

    # ------------------------------------------------------------------
    # iki atlama yüklemleri — hepsi ADAYA KOŞULLU
    # ------------------------------------------------------------------
    def _closed(self, u: int) -> Optional[Set[int]]:
        """N[u]; bilinmiyorsa None (budama o zaman yapılmaz)."""
        a = self._led.adj.get(u)
        return None if a is None else (set(a) | {u})

    def _adjacent(self, a: int, b: int) -> bool:
        return pair_adjacent(a, b, self._adj_of)

    def _prio(self, v: int) -> Tuple[float, int]:
        """Budama önceliği; KÜÇÜK olan yüksek öncelikli, yani budamada TUTULUR.

        Varsayılan (ağırlık, kimlik): budama pahalı düğümü atar. "id" kipi Wu-Li'nin
        özgün sıralamasıdır ve ablasyon kolunda ağırlık duyarlılığının katkısını
        ölçmek için vardır. İkisi de TAM sıralamadır, budama ispatı ikisinde de geçerli.
        """
        if self.p.prune_priority == "id":
            return (float(v), v)
        if v == self.me:
            return (self.w, self.me)
        w = self._led.weight.get(v)
        return WORST_PRIO if w is None else (w, v)

    # ------------------------------------------------------------------
    # Wu-Li işaretleme
    # ------------------------------------------------------------------
    def _adj_of(self, u: int) -> Optional[Set[int]]:
        """Defterdeki komşu listesi; öğrenilmemişse None. Kâhin bunun yerine tam
        çizgeyi verir; kurallar aynı, bilgi farklı."""
        return self._led.adj.get(u)

    def marking_rule(self) -> bool:
        return wu_li_mark(self._nbrs, self._adj_of)

    def pruned(self) -> bool:
        if not self._marked:
            return False
        return wu_li_prune(
            self.me,
            self._nbrs,
            self._adj_of,
            lambda u: bool(self._led.marked.get(u)),
            self._prio,
        )

    # ------------------------------------------------------------------
    # klik bileşeni: Wu-Li'nin tanımsız kaldığı tek durum
    # ------------------------------------------------------------------
    def clique_component(self) -> Optional[List[int]]:
        return clique_component_of(self.me, self._nbrs, self._adj_of)

    def _clique_decision(self) -> bool:
        return clique_join(self.me, self._clique or [], self.k, self._prio)

    # ------------------------------------------------------------------
    # bağlılık kapısı
    # ------------------------------------------------------------------
    def _attachable(self, view: LocalView) -> bool:
        """Örtüde bir komşum var mı? Omurga bitişikliği bu yüklemle zorlanır."""
        if view.in_cover:
            return True
        return any(self._led.in_cover.get(o) for o in sorted(self._nbrs))

    def _guard_join(self, view: LocalView, why: str) -> bool:
        """Omurga/klik dışı her katılım buradan geçer. İhlalde hata ya da not."""
        if self._attachable(view):
            return True
        self.violations += 1
        msg = f"düğüm {self.me} tur {view.round}: örtüde komşusu yokken katıldı ({why})"
        self.notes.append(msg)
        if self.p.strict_invariant:
            raise DcdsInvariantError(msg)
        return True

    # ------------------------------------------------------------------
    # yardımcılar
    # ------------------------------------------------------------------
    def _fresh(self, rnd: int, stamp: Optional[int]) -> bool:
        """Kayıt taze mi? Motorla aynı eşik: bir turdan eski olan bayattır."""
        return stamp is not None and (rnd - stamp) <= 1

    def _believes_cover(self, o: int) -> bool:
        """Komşu örtüde mi? Üyelik tek yönlü olduğu için bayat 'evet' de geçerlidir."""
        return bool(self._led.in_cover.get(o))

    def ext_score(self, needy: int) -> Tuple:
        """Genişletme skoru; kâhinle AYNI fonksiyon, yalnız `needy` yerel sayımdır."""
        return extension_score(self.w, self.me, needy)

    def local_score(self, view: LocalView) -> Tuple:
        needy = [
            o
            for o in view.uncovered_incident()
            if not view.in_cover and not self._believes_cover(o)
        ]
        return self.ext_score(len(needy))

    def _state_payload(self, view: LocalView, in_cover: bool, needy: int) -> Dict[str, Any]:
        return {
            "weight": self.w,
            "uncovered_degree": view.uncovered_degree(),
            "remaining_capacity": view.remaining_capacity,
            "in_cover": bool(in_cover),
            "score": list(self.ext_score(needy)),
        }

    # ------------------------------------------------------------------
    # tur
    # ------------------------------------------------------------------
    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        self._ingest(view)
        dec = NodeDecision()
        msgs: List[Message] = []
        if not self._nbrs:  # yalıtık düğüm: örtüye girmez, konuşmaz
            dec.quiescent = True
            dec.note = "isolated"
            return msgs, dec
        r = view.round

        if r == R_DIGEST:
            msgs.append(
                Message(
                    TWO_HOP_DIGEST,
                    self.me,
                    None,
                    dict(
                        self._state_payload(view, False, view.uncovered_degree()),
                        nbrs=sorted(self._nbrs),
                        digest=[{"node": o} for o in sorted(self._nbrs)],
                    ),
                )
            )
            dec.note = "digest"
            return msgs, dec

        if r == R_MARK:
            self._marked = self.marking_rule()
            msgs.append(
                Message(
                    MARK_STATE,
                    self.me,
                    None,
                    dict(
                        self._state_payload(view, False, view.uncovered_degree()),
                        marked=bool(self._marked),
                        prio=list(self._prio(self.me)),
                        # komşu listesi TEKRAR gönderilmez: tur 0 özeti zaten ulaştı.
                        # Mesaj SAYISI değişmez ama iki atlama muhasebesi netleşir:
                        # iki atlama komşuluğu düğüm başına TEK yayınla kazanılır.
                    ),
                )
            )
            dec.note = f"mark={self._marked}"
            return msgs, dec

        if r == R_BACKBONE:
            self._clique = self.clique_component()
            if self._clique is not None:
                self._clique_member = self._clique_decision()
                self._backbone = False
                want = self._clique_member
                why = "clique"
            else:
                self._backbone = bool(self._marked) and not self.pruned()
                want = self._backbone
                why = "backbone"
            if want and not view.in_cover:
                dec.join_cover = True  # omurga/klik İNŞADIR, bitişiklik kapısına tabi değil
            msgs.append(
                Message(
                    COVER_MEMBERSHIP,
                    self.me,
                    None,
                    dict(
                        self._state_payload(view, want, view.uncovered_degree()),
                        backbone=bool(self._backbone),
                        clique=self._clique is not None,
                    ),
                )
            )
            dec.note = f"{why}={want}"
            return msgs, dec

        return self._steady(view)

    # ------------------------------------------------------------------
    # kararlı evre: genişletme + talep + kapasite artırımı
    # ------------------------------------------------------------------
    def _steady(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        r = view.round
        dec = NodeDecision()
        msgs: List[Message] = []
        unowned = view.uncovered_incident()
        for o in sorted(self._nbrs):
            if o in unowned:
                self._age[o] = self._age.get(o, 0) + 1
            else:
                self._age.pop(o, None)
                self._defer.pop(o, None)
                self._hopeless.discard(o)
        live = [o for o in unowned if o not in self._hopeless]
        if self._upstream is not None and r > self._upstream_until:
            self._upstream = None  # taşıdığım istek cevapsız kaldı, defteri kapat

        in_cover = view.in_cover
        # --- 1) örtü genişletmesi
        # (i) iki ucu da örtüde olmayan sahipsiz kenar: yarışmalı, yerel maksimum katılır
        needy = [o for o in live if not in_cover and not self._believes_cover(o)]
        # (ii) karşı uç örtüde ama kenarı hâlâ sahiplenememiş: o uç doymuş demektir ve
        #      artırıcı yol da işe yaramamıştır. Bu kenarı alabilecek TEK diğer düğüm
        #      benim (kenarı yalnız iki ucundan biri sahiplenebilir), o yüzden yükü ben
        #      emerim. Karşı uç örtüde olduğu için bitişiklik zaten sağlanmıştır.
        #      Bekleme süresi artırıcı yola öncelik tanır; eşik dolmadan katılınmaz.
        absorb = [
            o
            for o in live
            if not in_cover
            and self._believes_cover(o)
            and self._age.get(o, 0) >= self.p.absorb_after
        ]
        if absorb and not in_cover:
            self._guard_join(view, "absorb-saturated-peer")
            dec.join_cover = True
        elif needy and not in_cover:
            mine = self.ext_score(len(needy))
            win = True
            for o in needy:
                s = self._led.score.get(o)
                if (
                    s is not None
                    and self._fresh(r, self._led.score_round.get(o))
                    and s < mine
                ):
                    win = False  # daha iyi skorlu komşu var, o katılsın
                    break
                # bayat ya da bilinmeyen skor -> ŞÜPHE ÖRTMEDEN YANA: win korunur
            if win:
                if self._attachable(view):
                    dec.join_cover = True
                    self._starve = 0
                else:
                    # omurga henüz duyulmadı; birkaç tur bekle, sonra güvenliği seç
                    self._starve += 1
                    if self._starve >= self.p.forced_join_after:
                        self._guard_join(view, "forced-after-starvation")
                        dec.join_cover = True
        cover_now = in_cover or dec.join_cover

        # --- 2) talepler: önce verilen sözler, sonra sahipsiz kenarlar
        budget = view.remaining_capacity
        claims: List[int] = []
        for o in sorted(k_ for k_, due in self._promise.items() if due == r):
            if o in self._nbrs and budget > 0 and cover_now:
                claims.append(o)  # söz koşulsuz tutulur; kenar hâlâ sahipliyse motor düşürür
                budget -= 1
        self._promise = {o: d for o, d in self._promise.items() if d > r}

        if cover_now:
            order = sorted(live, key=lambda o: (self._believes_cover(o), o))
            for o in order:
                if budget <= 0:
                    break
                if o in claims:
                    continue
                if self._believes_cover(o):
                    # iki uç da örtüde: boş kapasitesi çok olan alsın, eşitlikte küçük kimlik
                    sp = self._led.spare.get(o)
                    if (
                        sp is not None
                        and self._fresh(r, self._led.spare_round.get(o))
                        and (-sp, o) < (-view.remaining_capacity, self.me)
                        and self._defer.get(o, 0) < self.p.defer_limit
                    ):
                        self._defer[o] = self._defer.get(o, 0) + 1
                        continue
                claims.append(o)
                budget -= 1
        dec.claim_edges = sorted(set(claims))

        # talep mesajı yalnız karşı uç ÖRTÜDEYSE gerekir: örtüde olmayan uç
        # motorun I1 (2) kuralıyla zaten itiraz edemez, mesaj israf olurdu
        for o in dec.claim_edges:
            if self._believes_cover(o):
                msgs.append(Message(EDGE_CLAIM, self.me, o, {"edge": o}))

        # --- 3) gelen talepleri onayla (kendi talebim değilse)
        for m in sorted(view.messages_of(EDGE_CLAIM), key=lambda x: x.src):
            if m.src in self._nbrs and m.src not in dec.claim_edges:
                dec.accept_claims.append(m.src)

        # --- 4) kapasite artırıcı yol
        self._augment(view, msgs, dec, cover_now)

        # --- 5) durum yayını
        # Her tur yayın yapmak mesajın çoğunu yiyor. Yayın YALNIZ (a) evre açılışında,
        # (b) beyan DEĞİŞTİĞİNDE ve (c) düğüm hâlâ muhtaçken yapılır; muhtaç düğümün
        # skoru komşusunun yerel-maksimum kararına girdiği için susması yanlış
        # katılıma yol açardı. Susan düğümün kaydı bayatlar, karşı taraf da
        # "şüphe örtmeden yana" kuralıyla güvenli tarafa düşer.
        say = self._state_payload(view, cover_now, len(needy))
        stamp = (say["in_cover"], say["remaining_capacity"], tuple(say["score"]))
        if r <= R_STEADY or needy or stamp != self._last_say:
            msgs.insert(0, Message(COVER_MEMBERSHIP, self.me, None, say))
            self._last_say = stamp

        dec.quiescent = (
            not live
            and not msgs
            and not self._promise
            and self._upstream is None
            and not dec.accept_claims
        )
        dec.note = f"cover={cover_now} unowned={len(live)}"
        return msgs, dec

    # ------------------------------------------------------------------
    # artırıcı yol: devir isteği / kabulü
    # ------------------------------------------------------------------
    def _augment(
        self, view: LocalView, msgs: List[Message], dec: NodeDecision, cover_now: bool
    ) -> None:
        r = view.round
        released: Optional[int] = None

        # (a) bana gelen KABUL: kenarı bırak, karşı taraf bu turda talep ediyor
        for m in sorted(view.messages_of(SHED_ACCEPT), key=lambda x: x.src):
            a = m.src
            el = view.incident.get(a)
            if released is not None or el is None or el.owner != self.me:
                continue  # ilk kabulü kullan, gerisi boşa düşer (zararsız)
            dec.release_edges.append(a)
            dec.accept_claims.append(a)  # I1 (3): açık onay
            released = a
            self._shed_until = -1
            up = self._upstream
            if up is not None and up in self._nbrs:
                # yer açıldı: yukarı akıştaki istekçiye kabul ver
                msgs.append(Message(SHED_ACCEPT, self.me, up, {"edge": up}))
                self._promise[up] = r + 1
                self._upstream = None

        # (b) bana gelen İSTEK: "senin komşun olan (src,me) kenarını devral"
        used = len(dec.claim_edges) + sum(1 for d in self._promise.values() if d > r)
        for m in sorted(view.messages_of(SHED_REQUEST), key=lambda x: x.src):
            src = m.src
            el = view.incident.get(src)
            if el is None or el.owner != src:
                continue  # istek geçersizleşmiş
            if src in self._promise:
                continue
            budget = int((m.payload or {}).get("budget", 0))
            allow_join = bool((m.payload or {}).get("allow_join", False))
            spare = view.remaining_capacity - used
            joining = False
            if not cover_now and allow_join and spare > 0:
                # SON ÇARE: örtüye gir ve yükü emen ol. Bitişiklik kapısı burada da işler.
                self._guard_join(view, "absorb-load")
                dec.join_cover = True
                cover_now = True
                joining = True
            if (cover_now or joining) and spare > 0:
                msgs.append(Message(SHED_ACCEPT, self.me, src, {"edge": src}))
                self._promise[src] = r + 1
                used += 1
                continue
            if budget > 0 and self._upstream is None:
                fwd = [
                    o
                    for o in sorted(self._nbrs)
                    if o != src and view.incident[o].owner == self.me
                ]
                if fwd:
                    self._upstream = src
                    self._upstream_until = r + self.p.shed_timeout
                    for o in fwd:
                        msgs.append(
                            Message(
                                SHED_REQUEST,
                                self.me,
                                o,
                                {"budget": budget - 1, "allow_join": allow_join},
                            )
                        )

        # (c) kendi tıkanıklığım: doymuşum ve sahipsiz kenarım var
        if not cover_now or r <= self._shed_until:
            return
        stuck = [
            o
            for o in view.uncovered_incident()
            if o not in self._hopeless and self._age.get(o, 0) >= 2
        ]
        if not stuck or view.remaining_capacity > 0:
            return
        if released is not None:
            return  # bu turda zaten yer açıldı
        # gerçekten karşı uç da alamıyor mu
        blocked = []
        for o in stuck:
            if not self._believes_cover(o):
                blocked.append(o)
                continue
            sp = self._led.spare.get(o)
            if sp is not None and sp <= 0:
                blocked.append(o)
        if not blocked:
            return
        owned = [o for o in sorted(self._nbrs) if view.incident[o].owner == self.me]
        targets = [o for o in owned if self._believes_cover(o)]
        if self._allow_join:
            targets = owned  # son çare turunda örtü dışı komşular da çağrılır
        if not targets:
            self._allow_join = True
            self._bump_hopeless(blocked)
            return
        for o in targets:
            msgs.append(
                Message(
                    SHED_REQUEST,
                    self.me,
                    o,
                    {
                        "budget": max(0, self.p.augment_max_hops - 1),
                        "allow_join": self._allow_join,
                    },
                )
            )
        self._shed_until = r + self.p.shed_timeout
        self._allow_join = True  # bir sonraki deneme son çare kipinde
        self._bump_hopeless(blocked)

    def _bump_hopeless(self, blocked: Sequence[int]) -> None:
        """Çok uzun süredir sahiplenilemeyen kenarı bırak: koşum sonsuza dek sürmesin."""
        for o in blocked:
            if self._age.get(o, 0) >= self.p.give_up_after:
                if o not in self._hopeless:
                    self._hopeless.add(o)
                    self.notes.append(
                        f"düğüm {self.me}: kenar ({self.me},{o}) kapasiteyle sahiplenilemedi"
                    )


# --------------------------------------------------------------------------
# koşum kolaylığı
# --------------------------------------------------------------------------
def make_factory(params: Optional[DcdsParams] = None):
    """`RoundEngine.run` için üretici. Her düğüme AYRI örnek verir."""

    def factory(node_id: int) -> DcdsNode:
        return DcdsNode(params)

    return factory


def run_d_cds(
    g: CcvcGraph,
    params: Optional[DcdsParams] = None,
    max_rounds: int = 200,
    poll_order: Optional[Sequence[int]] = None,
) -> RunResult:
    """D-CDS kolunu bir çizge üstünde koş ve gerçek sayımlı sonucu döndür."""
    return run_protocol(
        g,
        make_factory(params),
        max_rounds=max_rounds,
        poll_order=poll_order,
        algorithm="d-cds",
    )


# ==========================================================================
# MERKEZİ KÂHİN: aynı strateji, tam bilgiyle
# ==========================================================================
# Bu, D-CDS'in dağıtık OLMAYAN ikizidir. Amacı 2x2 çarpanlı tasarımın eksik
# gözünü doldurmak:
#
#     onarım tabanlı  + merkezi   = central GRCCVC
#     onarım tabanlı  + dağıtık   = D-REPAIR
#     CDS önce        + merkezi   = solve_cds_central   <-- burası
#     CDS önce        + dağıtık   = D-CDS
#
# Böylece "CDS önce kurmak, sonradan onarmaktan iyidir" (strateji etkisi) ile
# "dağıtık olmak bilgi kaybettirir" (yerellik bedeli) AYRIŞTIRILABİLİR. İkisi
# tek sayıda karışırsa sonuç savunulamaz.
#
# AYNI olan: işaretleme kuralı, budama kuralları, (ağırlık, kimlik) önceliği,
# klik bileşeni kuralı, genişletme skoru. Hepsi yukarıdaki paylaşılan
# çekirdekten çağrılır, ikinci bir kopya YOKTUR.
#
# FARKLI olan, yalnızca bilgi ve zamanlama:
#   * `adj_of` tam çizgedir; hiçbir şey bilinmiyor değildir, hiçbir kayıt bayat
#     değildir, muhafazakâr "bilinmiyorsa işaretle" kolu hiç çalışmaz.
#   * Genişletme KÜRESEL argmin'dir: her adımda tüm çizgedeki en iyi aday
#     eklenir ve skorlar yeniden hesaplanır. Dağıtık kol bunu yapamaz, ancak
#     YEREL maksimum kuralına razı olur ve bir turda birden çok düğüm katılır.
#   * Kapasite TAM b-eşlemeyle (maksimum akış) atanır. Dağıtık kol bunun yerine
#     sınırlı uzunlukta artırıcı yol arar ve zincir uzunsa bulamaz.
#   * Mesaj yok, tur yok: messages=0, rounds=0.


def _max_assignment(
    edges: Sequence[Edge], cover: Set[int], k: int
) -> Tuple[int, Dict[Edge, int]]:
    """Kaç kenar kapasiteyi aşmadan bir ucuna atanabilir? TAM maksimum akış.

    Kaynak -> kenar (kapasite 1) -> örtüdeki uç (1) -> havuz (k). Doygun akış
    ancak ve ancak atama tamdır. Onarım döngüsü boolean değil AKIŞ DEĞERİ ister:
    bir düğüm eklemek atamayı tamamlamasa bile ilerletiyorsa bunu görmek gerekir.
    """
    edges = list(edges)
    m = len(edges)
    if m == 0:
        return 0, {}
    if k <= 0 or not cover:
        return 0, {}
    cover_list = sorted(cover)
    cidx = {v: m + 1 + i for i, v in enumerate(cover_list)}
    sink = m + 1 + len(cover_list)
    cap: List[Dict[int, int]] = [dict() for _ in range(sink + 1)]

    def add(a: int, b: int, c: int) -> None:
        cap[a][b] = cap[a].get(b, 0) + c
        cap[b].setdefault(a, 0)

    for i, (u, v) in enumerate(edges, start=1):
        if u not in cidx and v not in cidx:
            continue  # hiçbir ucu örtüde değil: bu kenar hiç atanamaz
        add(0, i, 1)
        for end in (u, v):
            if end in cidx:
                add(i, cidx[end], 1)
    for v in cover_list:
        add(cidx[v], sink, k)

    flow = 0
    while True:  # Edmonds-Karp; örneklerimizde kenar sayısı birkaç yüzü geçmiyor
        prev = [-1] * (sink + 1)
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
        node, bottleneck = sink, 1 << 30
        while node != 0:
            bottleneck = min(bottleneck, cap[prev[node]][node])
            node = prev[node]
        node = sink
        while node != 0:
            cap[prev[node]][node] -= bottleneck
            cap[node][prev[node]] += bottleneck
            node = prev[node]
        flow += bottleneck

    owner: Dict[Edge, int] = {}
    back = {i: v for v, i in cidx.items()}
    for i, e in enumerate(edges, start=1):
        for b, c in cap[i].items():
            if b in back and c == 0:
                owner[e] = back[b]
                break
    return flow, owner


def cds_central_cover(g: CcvcGraph) -> Tuple[Set[int], Set[int], Dict[Edge, int], List[str]]:
    """Kâhinin örtüsü. Döndürür: (örtü, omurga, kenar sahipliği, notlar)."""
    notes: List[str] = []
    adj_of = lambda u: set(g.adj[u])  # noqa: E731 — tam bilgi, hiç None yok
    prio_of = lambda v: (float(g.weight[v]), v)  # noqa: E731 — (ağırlık, kimlik)
    k = int(g.capacity_k)

    # --- 1) omurga: AYNI işaretleme + AYNI budama + AYNI öncelik
    marked = {v for v in g.nodes if wu_li_mark(set(g.adj[v]), adj_of)}
    backbone = {
        v
        for v in marked
        if not wu_li_prune(v, set(g.adj[v]), adj_of, marked.__contains__, prio_of)
    }
    cover: Set[int] = set(backbone)

    # --- 2) klik bileşenleri: AYNI kural
    for v in sorted(g.nodes):
        members = clique_component_of(v, set(g.adj[v]), adj_of)
        if members is not None and clique_join(v, members, k, prio_of):
            cover.add(v)

    def attachable(x: int) -> bool:
        return bool(set(g.adj[x]) & cover)

    # --- 3) genişletme: AYNI skor, ama KÜRESEL argmin ve adım adım yeniden hesap
    while True:
        open_edges = [(u, v) for u, v in g.edges if u not in cover and v not in cover]
        if not open_edges:
            break
        need: Dict[int, int] = {}
        for u, v in open_edges:
            need[u] = need.get(u, 0) + 1
            need[v] = need.get(v, 0) + 1
        best = min(
            sorted(need), key=lambda x: extension_score(g.weight[x], x, need[x])
        )
        # Bağlılık değişmezi kâhinde de kapıdır: baskınlık gereği her aday
        # omurgaya bitişiktir; değilse bu bir hatadır, sessizce geçilmez.
        if not attachable(best):
            raise DcdsInvariantError(
                f"kâhin: düğüm {best} örtüye bitişik değilken eklenecekti"
            )
        cover.add(best)

    # --- 4) kapasite: TAM b-eşleme, yetmezse küresel onarım
    flow, owner = _max_assignment(g.edges, cover, k)
    while flow < len(g.edges):
        best_key = None
        best_x = None
        for x in sorted(set(g.nodes) - cover):
            if not attachable(x):
                continue  # bağlılığı bozacak ekleme yapılmaz
            f2, _ = _max_assignment(g.edges, cover | {x}, k)
            gain = f2 - flow
            if gain <= 0:
                continue
            key = (round(g.weight[x] / gain, 9), round(g.weight[x], 9), x)
            if best_key is None or key < best_key:
                best_key, best_x = key, x
        if best_x is None:
            notes.append(
                f"kapasite tam atamaya yetmedi: {flow}/{len(g.edges)} kenar atandı, "
                "hiçbir ekleme akışı artırmıyor (örnek gerçekten çözümsüz)"
            )
            break
        cover.add(best_x)
        flow, owner = _max_assignment(g.edges, cover, k)
    return cover, backbone, owner, notes


def solve_cds_central(g: CcvcGraph) -> RunResult:
    """CDS-önce stratejisinin MERKEZİ kâhini. Mesaj yok, tur yok, eskime yok."""
    cover, backbone, owner, notes = cds_central_cover(g)
    verdict = verify(g, cover)
    notes = list(notes)
    notes.append(f"omurga: {sorted(backbone)}")
    notes.append(f"verify: {verdict.as_dict()}")
    if not verdict.valid:
        notes.append(
            "UYARI: kâhin de kapılardan geçemedi "
            f"(örtü={verdict.vertex_cover}, bağlı={verdict.connected}, "
            f"kapasite={verdict.capacity_feasible})"
        )
    return RunResult(
        algorithm="cds-central",
        cover=sorted(cover),
        owner=dict(owner),
        rounds=0,
        messages=0,
        messages_by_kind={},
        converged=True,
        per_round=[],
        notes=notes,
    )


# --------------------------------------------------------------------------
# deney koşum defteri (ccvc/experiment.py bunu `SPECS` diye bulur)
# --------------------------------------------------------------------------
def _arm(params: Optional[DcdsParams] = None):
    def run(g: CcvcGraph) -> RunResult:
        return run_d_cds(g, params=params, max_rounds=400)

    return run


# (etiket, callable(graph) -> RunResult). Varsayılan kol + iki ablasyon:
#   d_cds_hop1  artırıcı yol sınırı 1'e çekilir; kapasite dar örneklerde kaybı gösterir
#   d_cds_idprio  Wu-Li'nin ÖZGÜN kimlik önceliği; ağırlık duyarlı budamanın katkısını ölçer
#   cds_central   AYNI stratejinin merkezi kâhini: strateji etkisini yerellik
#                 bedelinden ayırmak için 2x2 tasarımın dördüncü gözü
SPECS = [
    ("d_cds", _arm()),
    ("d_cds_hop1", _arm(DcdsParams(augment_max_hops=1))),
    ("d_cds_idprio", _arm(DcdsParams(prune_priority="id"))),
    ("cds_central", solve_cds_central),
]
