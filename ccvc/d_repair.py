#!/usr/bin/env python3
"""D-REPAIR: merkezi CCVC akışının dürüst dağıtık portu (F3) — TABAN KOL.

Bu kol katkı değildir. Amacı tek: "önce örtüyü kur, sonra bağlılığı onar"
yaklaşımının dağıtıkta gerçekte neye mal olduğunu (mesaj, tur, ağırlık) ölçmek.
Üç çeşit tek bir iskeleti paylaşır, yalnız yerel öncelik anahtarı değişir
(küçük olan iyidir, son bileşen daima kimlik -> belirlenimci):

    D-GCCVC   (-ortulmemis_derece,  w,                   id)
    D-GRCCVC  (oran,  w,  -ortulmemis_derece,            id)   oran = w / komsu_agirlik_toplami
    D-GWCCVC  (w,     -ortulmemis_derece,                id)

Üçü de LocalView'den hesaplanır; küresel çizgeye erişim yoktur ve olamaz.

==========================================================================
DÖRT ZOR PARÇA — verilen kararlar
==========================================================================

(1) KÜRESEL ARGMIN -> YEREL MAKSİMUMLUK
    Merkezi kod her yinelemede TÜM çizgenin en iyi düğümünü seçer. Düğüm bunu
    yapamaz. Yerine: örtülmemiş kenarı olan düğüm, örtülmemiş kenarı olan
    KOMŞULARI arasında önceliği en iyiyse örtüye katılır. Eşitlik kimlikle
    kırılır (anahtarın son bileşeni). Bu davranışı değiştirir: bir turda birden
    çok düğüm katılır, dolayısıyla merkezi sıraya göre "gereksiz" katılımlar
    olur. Bedeli test_d_repair.py'de merkezi çözücüye karşı ölçülüyor.

    İki ek yerel kural kaliteyi kurtarır ve ikisi de 1 atlamada hesaplanır:
      * GEREK KURALI: örtülmemiş kenarlarımın HEPSİNİN karşı ucu zaten örtüde
        ve kapasitesi varsa katılmam gereksizdir, o uç kenarı talep edecektir.
      * TEKLİF BAYRAĞI (`bid`): "maksimum olsam katılır mıydım" bilgisi
        duyuruda taşınır. Teklif vermeyen bir komşuya boyun eğmek kilitlenme
        üretirdi (o hiç katılmaz, ben sonsuza dek beklerim); bu yüzden yalnız
        `bid=True` komşulara boyun eğilir. Bayrak yalnız kendi komşu
        durumumdan hesaplandığı için döngüsel bağımlılık yoktur.

(2) KIRMIZI KURAL — küresel olanın yerel karşılığı
    Merkezi kodda ortulmemis_derece <= 1 olan düğüm KIRMIZI'dır ve çizgenin
    HERHANGİ bir yerinde kırmızı varken hiçbir beyaz seçilemez. Bu indirgenemez
    biçimde küreseldir. İki çeşit yapıcı bayrakla sunuluyor:
      red_mode="none"   kural tamamen kalkar.
      red_mode="local"  kendisi kırmızı olmayan düğüm, kırmızı bir komşusu
                        varken katılmayı erteler. Kırmızı düğümler birbirine
                        boyun eğmez, aralarında (1)'deki maksimumluk işler.
    Kırmızılık ölçüsü merkezi koddaki gibi ÖRTÜDEKİ komşular hariç tutularak
    sayılır ve duyuruda `red` alanıyla taşınır.

(3) KENAR TALEBİ VE ESKİME
    Motor kuralı (engine.py I1): kenar ancak iki uç anlaşınca örtülür. İki
    bozulma biçiminden biri güvenlik ihlalidir ("ikimiz de karşı taraf halleder
    sandık" -> kenar açıkta kalır), diğeri yalnız israftır ("ikimiz de talep
    ettik").
    Karar: TALEBİ ASLA KARŞI TARAFA DAİR BİR İNANÇLA BASTIRMA. Örtüdeki her
    düğüm, örtülmemiş her komşu kenarını kapasitesi elverdiğince talep eder;
    bekleyen talepler kapasiteden düşülür, dolayısıyla I2 hiç zorlanmaz bile.
    Gelen her talep kabul edilir, hiçbir talep reddedilmez — reddetmek kenarı
    açıkta bırakmanın tek yoludur ve bu protokol onu hiç kullanmaz. Çakışan
    talepleri motor belirlenimci çözer (küçük kimlik, doluysa diğer uç), biz
    onunla güreşmiyoruz, üstüne kuruyoruz. Talep sırası "karşı ucu örtüde
    OLMAYAN kenarlar önce"dir: motorun (2) itirazsız-tek-uç kuralı o kenarları
    aynı turda kapatır.
    KAPASİTE KİLİDİ VE ARTIRICI YOL. Bir kenarı yalnız kendi iki ucundan biri
    sahiplenebilir; iki uç da örtüde ve doymuşsa hiçbir üçüncü düğüm devralamaz
    (plan/PLAN_DCCVC.md §1'deki 2026-09-11 düzeltmesiyle aynı gözlem). Tek çıkış:
    doymuş ucun BAŞKA bir kenarını karşı ucuna devretmek. Üç adımda kurulmuştur:
      * devir (`release_edges` + CAPACITY_STATE): kilitli düğüm sahip olduğu bir
        kenarı komşusuna bırakır, boşalan yuvayla kilitli kenarı alır.
      * zincir: devralan komşu da doymuşsa o da kilitlenir ve kendi devrini
        yapar. Yerel adımlardan oluşan bu zincir b-eşlemedeki artırıcı yolun ta
        kendisidir; kimse onu bütün olarak görmez.
      * yön (`capacity_push`): zincirin nereye gideceğini bilmesi için
        "bir yuvayı boşaltmam kaç devir sürer" değeri SAHİP OLDUĞUM kenarlar
        üzerinden gevşetilip (Bellman-Ford) duyuruda taşınır. Bütün komşular
        üzerinden hesaplanan iyimser bir sürüm denendi ve zinciri çıkmaz sokağa
        soktu; ölçüm kayıtta, o sürüm geri alındı.
    Salınıma karşı üç koruma: düğüm başına `relief_budget`, devredilen kenarın
    `handoff_wait` tur geri istenmemesi, ve bize devredene geri devretme yasağı.
    ÖLÇÜLDÜ (kampüs kareleri, k=2,3): gradyan açıkken 84/84 geçerli ve koşum
    başına ~651 mesaj, kapalıyken 80/84 geçerli ve ~491 mesaj. Yön bilgisi
    yaklaşık %30 mesaja mal oluyor ve kalan kapasite kilitlerini kapatıyor.

(4) DAĞITIK BAĞLILIK ONARIMI, BİLEŞEN BAZLI
    Çizge çoğu karede kopuktur (plan/PLAN_DCCVC.md §0.5), onarım BİLEŞEN İÇİNDEDİR.
    a) Parça kimliği: örtü alt çizgesinde min-kimlik seli. Örtüdeki düğüm
       `piece = min(kendi kimliği, örtü komşularının parça kimlikleri)` tutar ve
       yalnız DEĞİŞTİĞİNDE yayınlar. Sabit noktası parçanın en küçük kimliği,
       yani liderdir.
    b) Köprü adayı: örtü DIŞINDAKİ düğüm, örtü komşularında iki FARKLI parça
       kimliği görürse aday olur, maliyeti kendi ağırlığıdır.
    c) Seçim: aday, örtü komşularının duyurduğu "en iyi aday" özetiyle
       karşılaştırılır; en iyiyse katılır, değilse bekler. Bu yine (1)'deki
       yerel maksimumluktur; çatışma bağıntısı simetrik ve sıra tam olduğu için
       kilitlenme imkânsızdır, her zaman en küçük aday ilerler.
    d) İki lider birbirine aynı anda köprülenirse sonuç yalnız israftır:
       katılım tek yönlüdür (örtü büyür, küçülmez), bu yüzden eşzamanlı
       birleşme hatalı bir duruma götüremez. Belirlenimcilik (maliyet, kimlik)
       tam sırasından gelir.

    NEDEN 1 ARA DÜĞÜM HER ZAMAN YETER (ve hop_bound'ın anlamı):
      Örtü evresi bittiğinde V∖C bir BAĞIMSIZ KÜMEDİR — iki komşu düğüm birden
      örtü dışında olsaydı aralarındaki kenar örtülmemiş olurdu. Dolayısıyla
      bir bileşende iki örtü düğümü arasındaki her yolda ardışık iki örtü
      düğümü en fazla 2 uzaklıktadır; yani iki örtü parçasını birleştirmek için
      GEREKEN ARA DÜĞÜM SAYISI EN FAZLA 1'DİR. `hop_bound` yine de parametre:
      0 = onarımı tamamen kapat (onarımın ne kazandırdığını ölçen ablasyon),
      >=1 = tek ara düğümlü köprü. >=2 değerleri geçerli bir koşumda asla
      bağlayıcı olmaz; ölü kod yazmamak için çok atlamalı röle uygulanmadı,
      gerekçesi budur ve bileşenler arası köprüleme yapısal olarak imkânsızdır
      (köprü adayı iki parçaya da BİTİŞİKTİR, bu yüzden ikisi de aynı çizge
      bileşenindedir).

==========================================================================
SONLANMA (ve neden doğru)
==========================================================================
Motor ancak tüm düğümler quiescent VE yolda mesaj yokken durur. Duyurular
yalnız durum değiştiğinde yapılır, dolayısıyla "mesaj yok" = "sel sabit
noktasına ulaştı" demektir. Sabit noktada her örtü düğümünün parça kimliği
komşularının minimumuna eşittir, yani parça kimlikleri gerçektir. Aday kalmamış
olması da her örtü dışı düğümün tek bir parça görmesi demektir; yukarıdaki
bağımsızlık savıyla birlikte bu, örtünün her çizge bileşeni içinde bağlı olduğu
anlamına gelir. Örtülmemiş kenarı olan düğüm asla quiescent olmaz; tek istisna
`stall_limit` turluk tam durgunluktan sonraki pes etmedir, o da yalnız gerçekten
çözümsüz (kapasite kilitli) örneklerde tetiklenir ve sonuç bridge.verify ile
dürüstçe "hangi kapı düştü" diye kayda geçer, gizlenmez.

ÖLÇÜLEN BULGULAR (test_d_repair.py, `-s` ile basılır)
==========================================================================
  * Geçerlilik: 288/288 rastgele koşum ve 204/204 kampüs karesi üç kapıdan da
    geçti; bağımsız 768 koşumluk ikinci süpürmede de 0 başarısızlık.
  * Kalite. Kampüs karelerinde 254 örnek, tam çözüme oran (küçük iyi):
        tüm düğümler (taban)     1,90
        sıralı merkezi greedy    1,43 / 1,41 / 1,44
        KÂHİN (paralel+tam bilgi) 1,12 / 1,17 / 1,23
        D-REPAIR (paralel+yerel) 1,15 / 1,20 / 1,26
    Dağıtık kol merkezi greedy'den ORTALAMA DAHA İYİ çıkıyor. Kâhin bunu
    ikiye ayırıyor (eşleştirilmiş, tam çözüme oran farkı olarak):
        yerellik + eskime bedeli  +0,034 ± 0,011   (üç çeşitte de aynı)
        paralel - sıralı seçim    -0,21 ... -0,32
    Yani üstünlüğün TAMAMI paralel-vs-sıralı seçim farkından geliyor,
    yerellikten değil. Merkezi kod "aynı algoritmanın tam bilgili hali"
    DEĞİL, başka bir algoritmadır: o her yinelemede tek bir küresel argmin
    seçer, bu kol her turda bütün yerel maksimumları birden alır.
  * Maliyet: tur ortalaması 26, mesaj ortalaması 2328 (en yoğun örnekte 152 tur
    / 23283 mesaj; n=30, p=0,8).
  * Kırmızı kural: 153 karşılaştırmanın 92'sinde iki kip FARKLI örtü üretti.
    Toplam ağırlık none=56682, local=66751 -> kuralın yerel portu ağırlığı
    yaklaşık %18 KÖTÜLEŞTİRİYOR, mesaj ve tur sayısını ise pratikte
    değiştirmiyor. Merkezi (küresel) kuralın yerel karşılığı bir kazanç değil,
    bir kayıp; bu kayda geçiyor.
  * Onarımın bedeli: hop_bound=0 ile örtünün parçalı kaldığı 73 örnekte onarım
    açıldığında ağırlık ortalama 1,52 katına çıkıyor, koşum başına ~169 ek
    mesaj ve ~7,6 ek tur gerekiyor. Onarım tabanlı bağlılığın dağıtıktaki
    fiyatı budur.
  * Eskime BAZEN kazandırıyor. 759 eşleştirilmiş koşumun 18'inde (%2,4)
    D-REPAIR kendi kâhininden HAFİF çıkıyor. Kural ayrışması değil: iki kol
    aynı modül düzeyi fonksiyonları çağırıyor ve `test_oracle_and_node_share_
    one_rule_set` kuralı bozup ikisinin birden bozulduğunu doğruluyor.
    Mekanizma şu: `beats_all_bidders` örtüye girmiş komşuyu rakip saymaz.
    Tam bilgide az önce katılan komşu anında "örtüde" görünür, boyun eğen
    düğüm kendini yerel maksimum sanıp GEREKSİZ katılır. Bir tur eski bilgide
    ise o komşu hâlâ rakip görünür, düğüm bir tur daha bekler ve bu arada
    komşunun talepleri kenarlarını kapatır, düğüm hiç katılmaz. Eskime
    paralel açgözlüye kazara SIRALAYICI görevi görüyor. Ölçüldü: kâhinin
    örtüsü bu örneklerin 11'inde D-REPAIR örtüsünün ÖZ ÜST KÜMESİ, ortalama
    0,58 düğüm fazla.
  * Kalan kusur: koşumların ~%5'inde küme geçerli olduğu hâlde motorun kenar
    ataması eksik kalıyor (bütün açık kenarların iki ucu da doymuş). Bu bir
    eşgüdüm hatası DEĞİL: test `test_open_edge_always_means_real_capacity_lock`
    açık kenarın ucunda boş yuva bulunmadığını her koşumda doğruluyor.
    Eksikliğin nedeni artırıcı yol aramasının `relief_budget` ile sınırlı
    olması; sınırsız arama D-CDS kolunun işi (plan/PLAN_DCCVC.md §1 Kol B/3).

==========================================================================
Kullanılan mesaj tipleri (hepsi engine_api.py'de tanımlı, yenisi eklenmedi):
  COVER_INTENT      durum duyurusu (yayın, yalnız değişimde)
  EDGE_CLAIM        kenar talebi (tekil)
  EDGE_CLAIM_ACK    talebin kabulü (tekil) — motorun karar kanalı bedavaymış
                    gibi davranmamak için gerçekten gönderilir ve sayılır
  CAPACITY_STATE    kapasite devri bildirimi (tekil)
  COVER_MEMBERSHIP  parça kimliği + en iyi köprü adayı özeti (yayın)
  BRIDGE_REQUEST    köprü adaylığı ilanı (yayın)
  BRIDGE_ACCEPT     köprü rolünün üstlenildiği ilanı (yayın)
  COVER_WITHDRAW    köprü adaylığından çekilme (yayın)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:  # paket olarak da, ccvc/ içinden de çalışsın
    from ccvc import engine_api as api
    from ccvc.bridge import CcvcGraph, Edge, edge_key, verify
    from ccvc.engine import run_protocol
    from ccvc.engine_api import (
        LocalView,
        Message,
        NodeDecision,
        NodeProtocol,
        RunResult,
    )
except ImportError:  # pragma: no cover
    import engine_api as api  # type: ignore
    from bridge import CcvcGraph, Edge, edge_key, verify  # type: ignore
    from engine import run_protocol  # type: ignore
    from engine_api import (  # type: ignore
        LocalView,
        Message,
        NodeDecision,
        NodeProtocol,
        RunResult,
    )

_PUSH_INF = 99  # "sahip olduğum kenarları devredebileceğim bir boş yuva yok"

VARIANTS = ("gccvc", "grccvc", "gwccvc")
RED_MODES = ("none", "local")


# --------------------------------------------------------------------------
# PAYLAŞILAN D-REPAIR ÇEKİRDEĞİ
# --------------------------------------------------------------------------
# Aşağıdaki fonksiyonlar kuralların TEK kopyasıdır. Hem dağıtık düğüm
# (`DRepairNode`, kendi eksik ve BİR TUR ESKİ defterini vererek) hem merkezi
# kâhin (`solve_repair_oracle`, gerçek çizgenin o anki halini vererek) bunları
# çağırır. İki kol arasındaki tek fark `NodeFacts`ın nereden doldurulduğudur;
# "aynı strateji" bir söz değil, yapısal bir olgudur.


@dataclass(frozen=True)
class NodeFacts:
    """Bir kuralın bir düğüm hakkında bilmesi gereken HER ŞEY.

    Düğüm bunu `LocalView` + komşu kaydından doldurur (eksik ve eski olabilir),
    kâhin gerçek durumdan doldurur (`ready` her zaman True, çünkü eskime yok).
    """

    node: int
    weight: float
    in_cover: bool
    remaining_capacity: int
    uncovered_degree: int
    score: Optional[Tuple] = None
    red: bool = False
    bid: bool = False
    ready: bool = False
    push: int = _PUSH_INF


def priority_key(
    variant: str,
    weight: float,
    node: int,
    uncovered_degree: int,
    nbr_weight_sum: float,
) -> Tuple[float, ...]:
    """Yerel öncelik anahtarı (küçük iyi). plan/PLAN_DCCVC.md §3 ile birebir."""
    ud = float(uncovered_degree)
    if variant == "gccvc":
        return (-ud, float(weight), float(node))
    if variant == "gwccvc":
        return (float(weight), -ud, float(node))
    ratio = math.inf if nbr_weight_sum <= 0.0 else float(weight) / nbr_weight_sum
    return (ratio, float(weight), -ud, float(node))


def red_flag(open_degree: int) -> bool:
    """KIRMIZI ölçüsü: örtüdeki komşular hariç, örtülmemiş derece <= 1."""
    return open_degree <= 1


def need_to_join(partners: Sequence[Optional[NodeFacts]]) -> bool:
    """GEREK KURALI: her örtülmemiş kenarımı kapasiteli bir örtü komşusu alacaksa gerek yok."""
    for r in partners:
        if r is None:
            return True
        if not (r.in_cover and r.remaining_capacity > 0):
            return True
    return False


def red_allows(red_mode: str, red_self: bool, neighbors: Sequence[NodeFacts]) -> bool:
    """(2) yerel kırmızı kuralı: kırmızı olmayan, kırmızı komşusu varken erteler."""
    if red_mode != "local" or red_self:
        return True
    for r in neighbors:
        if r.in_cover or r.uncovered_degree <= 0:
            continue
        if r.red:
            return False
    return True


def beats_all_bidders(my_key: Tuple, neighbors: Sequence[NodeFacts]) -> bool:
    """(1) yerel maksimumluk: teklif veren, örtülmemiş kenarı olan komşular arasında en iyi miyim."""
    for r in neighbors:
        if r.in_cover or r.uncovered_degree <= 0:
            continue
        if not r.bid:
            continue  # hiç katılmayacak komşuya boyun eğmek kilitlenme olurdu
        if r.score is None or not r.ready:
            return False  # anahtarı henüz tam komşu bilgisiyle hesaplanmamış
        if tuple(r.score) < my_key:
            return False
    return True


def claim_order(candidates: Sequence[int], facts_of) -> List[int]:
    """(3) talep sırası: karşı ucu örtüde OLMAYAN kenarlar önce (motorun (2) kuralı
    onları aynı turda kapatır), sonra kimlik sırası."""

    def key(o: int):
        r = facts_of(o)
        return (1 if (r is not None and r.in_cover) else 0, o)

    return sorted(candidates, key=key)


def is_capacity_locked(partners: Sequence[Optional[NodeFacts]]) -> bool:
    """Kilit: örtülmemiş bir kenarın karşı ucu örtüde VE doymuş."""
    for r in partners:
        if r is not None and r.in_cover and r.remaining_capacity <= 0:
            return True
    return False


def handoff_target(owned: Sequence[NodeFacts], use_push: bool) -> Optional[int]:
    """(3b) devir hedefi: en kısa yoldan boş yuvaya, eşitlikte bedava olan, sonra ucuz olan."""
    best = None
    for r in owned:
        push = int(r.push) if use_push else 0
        if push >= _PUSH_INF:
            continue
        free = 0 if (r.in_cover and r.remaining_capacity > 0) else 1
        key = (push, free, r.weight, r.node)
        if best is None or key < best[0]:
            best = (key, r.node)
    return None if best is None else best[1]


def bridge_key(weight: float, node: int) -> Tuple[float, int]:
    """(4) köprü adayı maliyeti; tam sıra olduğu için seçimde kilitlenme olamaz."""
    return (float(weight), int(node))


class DRepairNode(NodeProtocol):
    """Tek düğümün D-REPAIR protokolü. Başka düğümün örneğine ERİŞMEZ."""

    def __init__(
        self,
        variant: str = "gccvc",
        *,
        red_mode: str = "none",
        hop_bound: int = 1,
        relief_budget: int = 12,
        capacity_push: bool = True,
        stall_limit: int = 40,
        cand_stall: int = 6,
    ) -> None:
        if variant not in VARIANTS:
            raise ValueError(f"bilinmeyen çeşit: {variant} (seçenek: {VARIANTS})")
        if red_mode not in RED_MODES:
            raise ValueError(f"bilinmeyen red_mode: {red_mode} (seçenek: {RED_MODES})")
        if hop_bound < 0:
            raise ValueError("hop_bound >= 0 olmalı")
        self.variant = variant
        self.red_mode = red_mode
        self.hop_bound = int(hop_bound)
        self.relief_budget = int(relief_budget)
        self.capacity_push = bool(capacity_push)
        self.stall_limit = int(stall_limit)
        self.cand_stall = int(cand_stall)
        self.name = f"D-{variant.upper()}[red={red_mode},hop={hop_bound}]"

        # --- yalnız kendi yerel durumu ---
        self.me: int = -1
        self.w: float = 0.0
        self.k: int = 0
        self.deg: int = 0
        self.piece: Optional[int] = None
        self.nbr_piece: Dict[int, int] = {}
        self.nbr_best: Dict[int, Optional[Tuple[float, int]]] = {}
        self.member_seen: Dict[int, int] = {}
        self.cand_nbrs: Dict[int, Tuple[float, int]] = {}
        self.declared: Optional[Tuple[float, int]] = None
        self.declared_round: int = -1
        self.last_intent: Optional[Tuple] = None
        self.last_member: Optional[Tuple] = None
        self.relief_used: int = 0
        self.handed: Dict[int, int] = {}
        self.got_handoff: Dict[int, int] = {}
        self.handoff_wait: int = 4
        self.stall: int = 0
        self.cand_wait: int = 0
        self.push: int = _PUSH_INF
        self.gave_up: bool = False
        self.last_sig: Optional[Tuple] = None

    # ------------------------------------------------------------------
    def on_start(self, me: int, weight: float, capacity_k: int, degree: int) -> None:
        self.me = me
        self.w = float(weight)
        self.k = int(capacity_k)
        self.deg = int(degree)

    # ------------------------------------------------------------------
    # yerel öncelik anahtarı (küçük iyi)
    # ------------------------------------------------------------------
    def priority(self, view: LocalView) -> Tuple[float, ...]:
        return priority_key(
            self.variant,
            view.weight,
            view.me,
            view.uncovered_degree(),
            view.sum_uncovered_neighbor_weights(),
        )

    @staticmethod
    def _facts(rec) -> NodeFacts:
        """Komşu kaydını PAYLAŞILAN kuralların anladığı olgulara çevirir.

        Buradaki her alan komşunun KENDİ duyurduğudur ve bir tur eskidir;
        kâhin aynı yapıyı gerçek durumdan doldurur. Kurallar ikisini ayırt
        edemez, ayırt etmemeli de.
        """
        return NodeFacts(
            node=rec.node,
            weight=float(rec.weight),
            in_cover=bool(rec.in_cover),
            remaining_capacity=int(rec.remaining_capacity),
            uncovered_degree=int(rec.uncovered_degree),
            score=None if rec.score is None else tuple(rec.score),
            red=bool(rec.extra.get("red", False)),
            bid=bool(rec.extra.get("bid", True)),
            ready=bool(rec.extra.get("ready", False)),
            push=int(rec.extra.get("push", _PUSH_INF)),
        )

    def local_score(self, view: LocalView) -> Tuple:
        return self.priority(view)

    # ------------------------------------------------------------------
    # ana döngü
    # ------------------------------------------------------------------
    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        dec = NodeDecision()
        msgs: List[Message] = []
        nbrs = view.neighbors
        unc = view.uncovered_incident()
        ud = len(unc)
        pending = [o for o in unc if view.incident[o].claimed_by_me]

        answer_needed = self._read_inbox(view)

        # --- gelen talepler: hepsi kabul, hiçbiri reddedilmez (bkz. zor parça 3)
        for m in sorted(view.messages_of(api.EDGE_CLAIM), key=lambda x: x.src):
            o = m.src
            if o in view.incident and not view.incident[o].covered:
                if o not in dec.accept_claims:
                    dec.accept_claims.append(o)
                    msgs.append(Message(api.EDGE_CLAIM_ACK, view.me, o, {"edge": o}))

        # --- yerel türetilmiş büyüklükler
        known_all = all(o in nbrs for o in view.incident)
        ud_open = sum(1 for o in unc if not (o in nbrs and nbrs[o].in_cover))
        red_self = red_flag(ud_open)
        need = self._need_to_join(view, unc, nbrs)
        red_ok = self._red_allows(view, nbrs, red_self)
        # `bid` "maksimum olsaydım katılır mıydım" demektir; komşu bilgisinin
        # tam olmasını BEKLEMEZ, yoksa tur 0'da herkes bid=False duyurur ve
        # tur 1'de kimse kimseye boyun eğmeyip hep birlikte katılır.
        bid = bool(ud) and not view.in_cover and need and red_ok

        # --- (1) katılım: yerel maksimumluk
        my = self.priority(view)
        join = False
        if (
            bid
            and known_all
            and not self.gave_up
            and self._locally_best(view, nbrs, my)
        ):
            join = True
        now_cover = view.in_cover or join

        # --- (3) talep: inançla bastırma yok, yalnız kapasite sınırlar
        if now_cover and not self.gave_up:
            free = view.remaining_capacity - len(pending)
            if free > 0:
                order = claim_order(
                    [
                        o
                        for o in unc
                        if not view.incident[o].claimed_by_me
                        and view.round - self.handed.get(o, -99) >= self.handoff_wait
                    ],
                    lambda o: self._facts(nbrs[o]) if o in nbrs else None,
                )
                for o in order[:free]:
                    dec.claim_edges.append(o)
                    msgs.append(Message(api.EDGE_CLAIM, view.me, o, {"edge": o}))

        # --- (3b) kapasite kilidi: 1 uzunluklu artırıcı yol
        if (
            view.in_cover
            and ud
            and not dec.claim_edges
            and view.remaining_capacity <= 0
            and self.relief_used < self.relief_budget
            and not self.gave_up
        ):
            x = self._relief_target(view, unc, nbrs)
            if x is not None:
                dec.release_edges.append(x)
                msgs.append(Message(api.CAPACITY_STATE, view.me, x, {"handoff": x}))
                self.relief_used += 1
                self.handed[x] = view.round

        # --- (4) onarım evresi
        # `done` = "örtü evresinde benden beklenen bitti"; kapasite yüzünden
        # pes etmiş düğüm de done sayılır, yoksa onarım evresi hiç başlamaz ve
        # kapasite kapısı düşen bir koşum bağlılık kapısını da gereksiz yere
        # düşürür (iki ayrı kusur tek kök nedenden doğmuş gibi görünürdü).
        done = (ud == 0 and not pending) or self.gave_up
        settled = (
            known_all
            and done
            and all(
                bool(nbrs[o].extra.get("done", nbrs[o].uncovered_degree <= 0))
                for o in view.incident
            )
        )
        bridge_join = self._repair(view, msgs, settled, now_cover, answer_needed)
        if bridge_join:
            now_cover = True
        dec.join_cover = bool(join or bridge_join)

        # --- devir gradyanı (`push`): "bir yuvayı boşaltmam kaç devir sürer"
        # Kapasite kilidini çözen şey her zaman ağın BİR YERİNDEKİ boş yuvadır;
        # kilitli düğüm hangi yöne devretmesi gerektiğini ancak bu uzaklık
        # komşudan komşuya yayılırsa bilir. Gevşetme SAHİP OLDUĞUM kenarlar
        # üzerinden yapılır, çünkü yalnız onları devredebilirim — bütün
        # komşular üzerinden hesaplanan bir gradyan iyimser çıkar ve zinciri
        # çıkmaz sokağa sokar (ölçüldü, kazanç vermedi).
        if not self.capacity_push:
            self.push = 0
        elif (not now_cover) or view.remaining_capacity > 0:
            self.push = 0
        else:
            best_push = _PUSH_INF
            for o in sorted(view.incident):
                if view.incident[o].owner != view.me:
                    continue
                r = nbrs.get(o)
                if r is None:
                    continue
                best_push = min(best_push, int(r.extra.get("push", _PUSH_INF)))
            self.push = min(_PUSH_INF, best_push + 1)

        # --- durum duyurusu (yalnız değişimde)
        intent = (
            round(float(view.weight), 9),
            ud,
            view.remaining_capacity,
            now_cover,
            my,
            red_self,
            bid,
            known_all,
            (ud == 0 and not pending) or self.gave_up,
            self.push,
        )
        if intent != self.last_intent and view.incident:
            # kenarsız düğümün duyuracak kimsesi yoktur: tur 0'da sessizce
            # quiescent olur, koşum tek turda biter
            self.last_intent = intent
            msgs.append(
                Message(
                    api.COVER_INTENT,
                    view.me,
                    None,
                    {
                        "weight": float(view.weight),
                        "uncovered_degree": ud,
                        "remaining_capacity": view.remaining_capacity,
                        "in_cover": now_cover,
                        "score": my,
                        "red": red_self,
                        "bid": bid,
                        "ready": known_all,
                        "done": (ud == 0 and not pending) or self.gave_up,
                        "push": self.push,
                    },
                )
            )

        # --- meşguliyet ve sonlanma
        acted = bool(msgs) or bool(dec.claim_edges) or bool(dec.accept_claims)
        acted = acted or dec.join_cover or bool(dec.release_edges)
        busy = acted
        if not self.gave_up:
            if ud > 0 or pending:
                busy = True
        if (not now_cover) and self.declared is not None:
            busy = True
        dec.quiescent = not busy

        self._update_stall(view, ud, acted)
        dec.note = f"{self.name} r={view.round} ud={ud} piece={self.piece}"
        return msgs, dec

    # ------------------------------------------------------------------
    # gelen kutusu
    # ------------------------------------------------------------------
    def _read_inbox(self, view: LocalView) -> bool:
        """Onarım mesajlarını işle. Döndürür: bu turda cevap yayını gerekiyor mu."""
        answer = False
        for m in sorted(view.inbox, key=lambda x: (x.kind, x.src)):
            if m.kind == api.COVER_MEMBERSHIP:
                p = m.payload.get("piece")
                if p is not None:
                    prev = self.nbr_piece.get(m.src)
                    self.nbr_piece[m.src] = (
                        int(p) if prev is None else min(prev, int(p))
                    )
                b = m.payload.get("best_cand")
                self.nbr_best[m.src] = (float(b[0]), int(b[1])) if b else None
                self.member_seen[m.src] = m.round_sent
            elif m.kind == api.BRIDGE_REQUEST:
                self.cand_nbrs[m.src] = (float(m.payload.get("cost", 0.0)), int(m.src))
                answer = True
            elif m.kind == api.COVER_WITHDRAW:
                self.cand_nbrs.pop(m.src, None)
                answer = True
            elif m.kind == api.CAPACITY_STATE:
                self.got_handoff[m.src] = m.round_sent
            elif m.kind == api.BRIDGE_ACCEPT:
                self.cand_nbrs.pop(m.src, None)
                answer = True
        return answer

    # ------------------------------------------------------------------
    # katılım kuralları
    # ------------------------------------------------------------------
    def _need_to_join(self, view: LocalView, unc: Sequence[int], nbrs) -> bool:
        return need_to_join(
            [None if o not in nbrs else self._facts(nbrs[o]) for o in unc]
        )

    def _red_allows(self, view: LocalView, nbrs, red_self: bool) -> bool:
        return red_allows(
            self.red_mode,
            red_self,
            [self._facts(nbrs[o]) for o in sorted(nbrs)],
        )

    def _locally_best(self, view: LocalView, nbrs, my: Tuple) -> bool:
        return beats_all_bidders(my, [self._facts(nbrs[o]) for o in sorted(nbrs)])

    def _relief_target(self, view: LocalView, unc: Sequence[int], nbrs):
        """(3b) kapasite kilidi: 1 uzunluklu artırıcı yol.

        Kilidin tanımı: örtülmemiş bir komşu kenarın karşı ucu ÖRTÜDE ve DOYMUŞ.
        O kenarı yalnız iki ucundan biri sahiplenebilir, ikisi de doluysa
        ilerleme ancak birinin sahip olduğu BAŞKA bir kenarı karşı ucuna
        devretmesiyle olur. Devir hedefi iki türlü olabilir:
          * kapasitesi kalan bir ÖRTÜ komşusu (bedava, ağırlık artmaz)
          * örtü DIŞINDA bir komşu — devirden sonra o kenar örtüsüz kalır,
            karşı uç doymuş olduğu için komşunun `need` kuralı tetiklenir ve
            komşu örtüye katılır. Merkezi koddaki `escalate_capacity`nin
            dağıtık karşılığı budur: örtüye düğüm ekleyerek toplam kapasiteyi
            büyütmek.
        Salınım iki koruma ile engellenir: düğüm başına `relief_budget` ve
        devredilen kenarın `handoff_wait` tur boyunca geri istenmemesi.
        """
        parts = [None if o not in nbrs else self._facts(nbrs[o]) for o in unc]
        if not is_capacity_locked(parts):
            return None
        owned = [
            self._facts(nbrs[o])
            for o in sorted(view.incident)
            if view.incident[o].owner == view.me
            and o in nbrs
            and view.round - self.handed.get(o, -99) >= self.handoff_wait
            and view.round - self.got_handoff.get(o, -99) >= self.handoff_wait
        ]
        return handoff_target(owned, self.capacity_push)

    # ------------------------------------------------------------------
    # (4) onarım
    # ------------------------------------------------------------------
    def _repair(
        self,
        view: LocalView,
        msgs: List[Message],
        settled: bool,
        now_cover: bool,
        answer_needed: bool,
    ) -> bool:
        if self.hop_bound <= 0:
            return False  # ablasyon: onarım kapalı
        if now_cover:
            self._repair_cover_side(view, msgs, settled, answer_needed)
            return False
        return self._repair_free_side(view, msgs, settled)

    def _repair_cover_side(
        self, view: LocalView, msgs: List[Message], settled: bool, answer_needed: bool
    ) -> None:
        """Örtü tarafı: min-kimlik seli + en iyi aday özeti."""
        cand = view.me
        for o in sorted(self.nbr_piece):
            if o in view.incident and self.nbr_piece[o] < cand:
                cand = self.nbr_piece[o]
        self.piece = cand if self.piece is None else min(self.piece, cand)
        if not settled:
            return
        best: Optional[Tuple[float, int]] = None
        for o in sorted(self.cand_nbrs):
            c = self.cand_nbrs[o]
            if best is None or c < best:
                best = c
        member = (self.piece, best)
        if member != self.last_member or answer_needed:
            self.last_member = member
            msgs.append(
                Message(
                    api.COVER_MEMBERSHIP,
                    view.me,
                    None,
                    {
                        "piece": self.piece,
                        "best_cand": None if best is None else [best[0], best[1]],
                    },
                )
            )

    def _repair_free_side(
        self, view: LocalView, msgs: List[Message], settled: bool
    ) -> bool:
        """Örtü dışı taraf: iki farklı parça gören düğüm köprü adayıdır."""
        labels = sorted(
            {self.nbr_piece[o] for o in view.incident if o in self.nbr_piece}
        )
        want = settled and len(labels) >= 2
        cand = bridge_key(view.weight, view.me) if want else None

        if cand != self.declared:
            self.declared = cand
            self.declared_round = view.round
            self.cand_wait = 0
            if cand is None:
                msgs.append(Message(api.COVER_WITHDRAW, view.me, None, {}))
            else:
                msgs.append(
                    Message(
                        api.BRIDGE_REQUEST,
                        view.me,
                        None,
                        {"cost": float(view.weight), "labels": labels},
                    )
                )
            return False

        if cand is None:
            return False

        # örtü komşularının HEPSİ ilanımdan SONRA cevap vermiş olmalı
        fresh = all(o in self.nbr_piece for o in view.incident) and all(
            self.member_seen.get(o, -1) > self.declared_round for o in view.incident
        )
        if not fresh:
            self.cand_wait += 1
            if self.cand_wait < self.cand_stall:
                return False

        best: Optional[Tuple[float, int]] = None
        for o in sorted(view.incident):
            b = self.nbr_best.get(o)
            if b is not None and (best is None or b < best):
                best = b
        if best is not None and best < cand and self.cand_wait < self.cand_stall:
            self.cand_wait += 1
            return False

        # köprü rolünü üstlen
        self.piece = min([int(view.me)] + labels)
        self.declared = None
        self.cand_wait = 0
        self.last_member = None
        msgs.append(
            Message(
                api.BRIDGE_ACCEPT,
                view.me,
                None,
                {"bridge": labels, "piece": self.piece},
            )
        )
        return True

    # ------------------------------------------------------------------
    def _update_stall(self, view: LocalView, ud: int, acted: bool) -> None:
        sig = (
            ud,
            view.in_cover,
            view.remaining_capacity,
            self.piece,
            tuple(sorted(self.nbr_piece.items())),
            self.declared,
        )
        if view.inbox or acted or sig != self.last_sig:
            self.stall = 0
        else:
            self.stall += 1
        self.last_sig = sig
        if self.stall >= self.stall_limit:
            self.gave_up = True


# --------------------------------------------------------------------------
# kolaylık sarmalayıcıları
# --------------------------------------------------------------------------
def d_repair_factory(variant: str = "gccvc", **kw):
    """`run_protocol`'un beklediği protocol_factory'yi üretir."""

    def make(node_id: int) -> DRepairNode:
        return DRepairNode(variant, **kw)

    return make


def run_d_repair(
    graph: CcvcGraph,
    variant: str = "gccvc",
    *,
    max_rounds: int = 600,
    poll_order: Optional[Sequence[int]] = None,
    **kw: Any,
) -> RunResult:
    """Tek çağrıda D-REPAIR koşumu. Mesajları motor sayar, biz saymayız."""
    probe = DRepairNode(variant, **kw)
    return run_protocol(
        graph,
        d_repair_factory(variant, **kw),
        max_rounds=max_rounds,
        poll_order=poll_order,
        algorithm=probe.name,
    )


# --------------------------------------------------------------------------
# MERKEZİ KÂHİN: aynı strateji, tam bilgi
# --------------------------------------------------------------------------
# 2x2'nin eksik hücresi. `DRepairNode` kuralları bir tur eski, kısmi bir
# defterle çağırır; buradaki sürücü AYNI kuralları gerçek durumla çağırır.
# Mesaj yok, tur yok, eskime yok. Dolayısıyla
#     kâhin - D-REPAIR   = yalnız YERELLİK ve ESKİME'nin bedeli
#     kâhin - merkezi greedy = yalnız PARALEL-vs-SIRALI seçimin farkı
# çünkü başka hiçbir şey değişmiyor. Kurallar tek kopya olduğu için iki kolun
# zamanla ayrışması mümkün değil.

_ORACLE_HANDOFF_WAIT = 4


def _piece_labels(cover: Set[int], adj: Dict[int, List[int]]) -> Dict[int, int]:
    """Min-kimlik selinin SABİT NOKTASI: örtü bileşeninin en küçük kimliği."""
    labels: Dict[int, int] = {}
    left = set(cover)
    while left:
        start = min(left)
        comp = {start}
        stack = [start]
        while stack:
            x = stack.pop()
            for y in adj[x]:
                if y in cover and y not in comp:
                    comp.add(y)
                    stack.append(y)
        lead = min(comp)
        for x in comp:
            labels[x] = lead
        left -= comp
    return labels


def repair_oracle_cover(
    g: CcvcGraph,
    variant: str = "grccvc",
    *,
    red_mode: str = "none",
    relief_budget: int = 12,
    capacity_push: bool = True,
    hop_bound: int = 1,
    max_steps: int = 500,
) -> Tuple[Set[int], Dict[Edge, int], List[str]]:
    nodes = sorted(g.nodes)
    adj = {v: sorted(g.adj.get(v, ())) for v in nodes}
    k = int(g.capacity_k)
    w = {v: float(g.weight[v]) for v in nodes}
    cover: Set[int] = set()
    owner: Dict[Edge, int] = {}
    load = {v: 0 for v in nodes}
    relief_used = {v: 0 for v in nodes}
    handed: Dict[Tuple[int, int], int] = {}
    got: Dict[Tuple[int, int], int] = {}
    notes: List[str] = []

    def uncovered(v: int) -> List[int]:
        return [o for o in adj[v] if edge_key(v, o) not in owner]

    def push_values() -> Dict[int, int]:
        """Devir gradyanının TAM değeri: sahip olunan kenarlar üstünden boş yuvaya uzaklık."""
        push = {v: (0 if (v not in cover or load[v] < k) else _PUSH_INF) for v in nodes}
        if not capacity_push:
            return {v: 0 for v in nodes}
        for _ in range(len(nodes) + 1):
            moved = False
            for v in nodes:
                if push[v] == 0:
                    continue
                best = _PUSH_INF
                for o in adj[v]:
                    if owner.get(edge_key(v, o)) == v and push[o] < best:
                        best = push[o]
                nv = min(_PUSH_INF, best + 1)
                if nv < push[v]:
                    push[v] = nv
                    moved = True
            if not moved:
                break
        return push

    def build() -> Tuple[Dict[int, NodeFacts], Dict[int, List[int]]]:
        push = push_values()
        unc = {v: uncovered(v) for v in nodes}
        base = {}
        for v in nodes:
            u = unc[v]
            base[v] = (
                len(u),
                red_flag(sum(1 for o in u if o not in cover)),
                priority_key(variant, w[v], v, len(u), sum(w[o] for o in u)),
            )

        def mk(v: int, bid: bool) -> NodeFacts:
            ud, red, key = base[v]
            return NodeFacts(
                node=v,
                weight=w[v],
                in_cover=v in cover,
                remaining_capacity=k - load[v],
                uncovered_degree=ud,
                score=key,
                red=red,
                bid=bid,
                ready=True,  # eskime yok: anahtar her zaman güncel
                push=push[v],
            )

        # `bid` kendi kuralları bid kullanmadığı için iki geçişte kurulur
        tmp = {v: mk(v, False) for v in nodes}
        facts = {}
        for v in nodes:
            ud, red, _key = base[v]
            bid = (
                bool(ud)
                and v not in cover
                and need_to_join([tmp[o] for o in unc[v]])
                and red_allows(red_mode, red, [tmp[o] for o in adj[v]])
            )
            facts[v] = mk(v, bid)
        return facts, unc

    # ---------------- örtü evresi ----------------
    steps = 0
    for step in range(max_steps):
        steps = step + 1
        changed = False
        facts, unc = build()

        # (1) yerel maksimumluk — paralel, aynı adımda birden çok düğüm katılır
        joiners = [
            v
            for v in nodes
            if facts[v].bid
            and beats_all_bidders(facts[v].score, [facts[o] for o in adj[v]])
        ]
        if joiners:
            cover.update(joiners)
            changed = True
            facts, unc = build()  # tam bilgi: katılımlar anında görünür

        # (3) talep — motorun I1/I2 çözümüyle birebir aynı kurallar
        claims: Dict[Edge, Set[int]] = {}
        for v in sorted(cover):
            free = k - load[v]
            if free <= 0:
                continue
            cands = [
                o
                for o in unc[v]
                if step - handed.get((v, o), -99) >= _ORACLE_HANDOFF_WAIT
            ]
            for o in claim_order(cands, lambda o: facts[o])[:free]:
                claims.setdefault(edge_key(v, o), set()).add(v)
        eligible = []
        for e, cs in claims.items():
            a, b = e
            if len(cs) == 2:
                pref, fb = (a, b) if a < b else (b, a)
                eligible.append((pref, fb, e, fb))
            else:
                c = next(iter(cs))
                eligible.append((c, b if c == a else a, e, None))
        for pref, other, e, fb in sorted(eligible, key=lambda t: (t[0], t[1])):
            winner = None
            if load[pref] < k:
                winner = pref
            elif fb is not None and fb in cover and load[fb] < k:
                winner = fb
            if winner is None:
                continue
            owner[e] = winner
            load[winner] += 1
            changed = True

        # (3b) kapasite kilidi: aynı devir kuralı, gerçek gradyanla
        facts, unc = build()
        for v in sorted(cover):
            if load[v] < k or not unc[v] or relief_used[v] >= relief_budget:
                continue
            if not is_capacity_locked([facts[o] for o in unc[v]]):
                continue
            owned = [
                facts[o]
                for o in adj[v]
                if owner.get(edge_key(v, o)) == v
                and step - handed.get((v, o), -99) >= _ORACLE_HANDOFF_WAIT
                and step - got.get((v, o), -99) >= _ORACLE_HANDOFF_WAIT
            ]
            t = handoff_target(owned, capacity_push)
            if t is None:
                continue
            del owner[edge_key(v, t)]
            load[v] -= 1
            relief_used[v] += 1
            handed[(v, t)] = step
            got[(t, v)] = step
            changed = True
        if not changed:
            break
    else:
        notes.append(f"kâhin max_steps={max_steps} adımında durdu")

    open_edges = [e for e in g.edges if e not in owner]
    if open_edges:
        notes.append(f"kapasite kilidi: {len(open_edges)} kenar sahipsiz kaldı")

    # ---------------- onarım evresi ----------------
    bridges = 0
    if hop_bound >= 1:
        for _ in range(len(nodes) + 1):
            labels = _piece_labels(cover, adj)
            cands = [
                x
                for x in nodes
                if x not in cover
                and len({labels[o] for o in adj[x] if o in cover}) >= 2
            ]
            if not cands:
                break
            cset = set(cands)
            winners = []
            for x in cands:
                kx = bridge_key(w[x], x)
                rivals = {
                    y
                    for o in adj[x]
                    if o in cover
                    for y in adj[o]
                    if y in cset and y != x
                }
                if all(bridge_key(w[y], y) > kx for y in rivals):
                    winners.append(x)
            if not winners:
                break
            cover.update(winners)
            bridges += len(winners)
    notes.append(f"köprü düğümü: {bridges}, örtü evresi adımı: {steps}")
    return cover, owner, notes


def solve_repair_oracle(
    g: CcvcGraph, variant: str = "grccvc", *, red_mode: str = "none"
) -> RunResult:
    """Onarım-önce stratejisinin MERKEZİ kâhini. Mesaj yok, tur yok, eskime yok."""
    cover, owner, notes = repair_oracle_cover(g, variant, red_mode=red_mode)
    verdict = verify(g, cover)
    notes = list(notes)
    notes.append(f"verify: {verdict.as_dict()}")
    if not verdict.valid:
        notes.append(
            "UYARI: kâhin de kapılardan geçemedi "
            f"(örtü={verdict.vertex_cover}, bağlı={verdict.connected}, "
            f"kapasite={verdict.capacity_feasible})"
        )
    return RunResult(
        algorithm=f"repair-oracle-{variant}",
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
# deney koşum hattı kaydı (ccvc/experiment.py `SPECS` ile otomatik bulur)
# --------------------------------------------------------------------------
def _spec_runner(variant: str, red_mode: str):
    def run(graph: CcvcGraph) -> RunResult:
        return run_d_repair(graph, variant, max_rounds=800, red_mode=red_mode)

    return run


#: (etiket, callable(graph) -> RunResult). Üç anahtarın iki kırmızı kipi.
#: Kırmızı kipi etikete giriyor çünkü iki kip ölçülen örneklerin yarısından
#: fazlasında FARKLI örtü veriyor; tek etiket altında toplamak karşılaştırmayı
#: gizlerdi. Etiketlerin hiçbiri "central" içermez, dolayısıyla hepsi hattın
#: gözünde gerçekten dağıtık koldur.
SPECS = [
    (f"d_repair_{variant}_red{red_mode}", _spec_runner(variant, red_mode))
    for variant in VARIANTS
    for red_mode in RED_MODES
] + [
    # AYNI stratejinin tam bilgili kâhini: strateji etkisini yerellikten ayırır
    ("repair_oracle", lambda g: solve_repair_oracle(g, "grccvc")),
    ("repair_oracle_gccvc", lambda g: solve_repair_oracle(g, "gccvc")),
    ("repair_oracle_gwccvc", lambda g: solve_repair_oracle(g, "gwccvc")),
]
