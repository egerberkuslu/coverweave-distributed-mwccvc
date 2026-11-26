#!/usr/bin/env python3
"""WuLi-Dominating: Faz 1 yerine Wu-Li işaretleme + Rule-k budama (brief §6, §5).

NE OLDUĞU. BB-CVC'nin yalnız Faz 1'i (MIS + connector) değiştirilir; Faz 2, 3,
4, 5 `bbcvc.py`den AYNEN miras alınır. Değişen tek şey omurganın nasıl
kurulduğudur, dolayısıyla bu bir algoritma değişikliği değil, bir OMURGA
DEĞİŞİKLİĞİDİR. Brief §6 tablosu bu kolu hâlâ `V5-BB-WuLi` diye anmakta
olup kolun bugünkü adı `WuLi-Dominating`dir; eşleme
`ccvc/bb/armnames.py` içindedir.

NEDEN VAR. Wu-Li her düğümün KOMŞULARININ KOMŞU KÜMESİNİ bilmesini ister, yani
2-atlama bilgisi. BB-CVC'nin bütün mesaj-boyutu savunması (brief §5, G8) tam da
bunu taşımamaya dayanır. WuLi-Dominating bu yüzden bir algoritma yarışı değil MESAJ BOYUTU
DENEYİdir: aynı algoritma üç ayrı kodlamayla koşar ve ölçülen şey
`max_payload` ile `bytes_tx`in ortalama dereceye göre eğrisidir (brief §12/8,
şekil 6).

  full      N(v) tam liste, 2 B/id. Kesin bilgi, boyut dereceyle büyür.
  bloom     N(v) 64 baytlık Bloom özeti (brief §5/1). Boyut SABİT, bilgi
            belirsiz: yalnız yanlış pozitif verir, yanlış negatif vermez.
  chunked   tam liste `seq/total` ile birden çok çerçeveye bölünür (brief §5/2).
            Boyut sabit, bilgi EKSİK: gelmemiş parçadaki id "yok" değil
            "bilinmiyor"dur.

ÜÇ DEĞERLİ BİLGİ, İKİ İLKE. Kodlamaların ikisi de belirsizlik üretir ama
belirsizliğin YÖNÜ TERSTİR ve bu farkı `Tri` üç değerli cevabı taşır:

              "x, N(u) içinde mi?"        YES        NO        MAYBE
  full        kesin liste                 var        yok       -
  bloom       bit taraması                -          bit boş   bit dolu
  chunked     gelen parçalar              var        tamsa yok eksikse yok

  Yani bloom YANLIŞ POZİTİF (MAYBE = belki var), chunked YANLIŞ NEGATİF
  (MAYBE = belki var ama parçası gelmedi) tarafında belirsizdir.

İKİ İLKE (`policy`):
  safe   brief §5/1'in kuralı: karar YALNIZ KESİNLİĞE dayanır, MAYBE hep
         "hayır" sayılır. İşaretlemede "komşu değil" demek DAHA ÇOK düğümü
         işaretler, budamada "örtülü değil" demek DAHA AZ budar; ikisi de
         omurgayı BÜYÜTÜR, dolayısıyla baskınlık ve bağlılık kaybedilemez.
  naive  belirsizi olduğu gibi kabul et (bloom "bit dolu" = komşu). Bir
         uygulayıcının boyut kazancını korumak için yapacağı şey budur ve
         GÜVENLİ DEĞİLDİR: yanlış pozitif eksik işaretlemeye ya da fazla
         budamaya yol açar, omurga CDS olmaktan çıkar ve Faz 2'nin G2 savı
         çöker. Sonuç YALNIZ daha ağır bir örtü değil, GEÇERSİZ bir örtüdür.
         Bu dosya bunu varsaymaz, ÖLÇER (`invalid_rate`).

SAFE+BLOOM'UN DEJENERASYONU (türetildi, sonra ölçüldü). Bloom hiçbir zaman
YES veremez, yalnız NO ya da MAYBE verir. `safe` MAYBE'yi "hayır" saydığından:
  * işaretleme: her komşu çifti "bitişik değil" görünür, yani derecesi >= 2 olan
    HER düğüm işaretlenir,
  * budama: örtülülük için YES gerekir, bloom YES veremez, yani HİÇ BUDAMA OLMAZ.
Sonuç: safe+bloom omurgası tam olarak {v : deg(v) >= 2}. Geçerlidir (yapraksız
alt çizge bağlı ve baskındır) ama Wu-Li'nin bütün kazancı gider. Yani 64 baytın
bedeli boyut değil KALİTEdir. `test_v5_wuli.py` bunu hem türetimden hem ölçümden
doğrular.

ÖLÇÜLEN BULGULAR (hepsi `test_v5_wuli.py`de assert edilir; hiçbiri tahmin değil)

  B1. 64 BAYTLIK ÖZET, YERİNE GEÇTİĞİ LİSTEDEN BÜYÜK. Tam liste 13+2(1+d)
      bayttır, Bloom sabit 79 bayttır; eşitlik derece 32'de. Kıyas kümesinin
      ortalama dereceleri 6-16, en büyük derecesi 36'dır. Yani brief §5/1'in
      "sabit 64 bayt" kazancı BU veri kümesinde ÇOĞU DÜĞÜM İÇİN KAYIPTIR:
      daha çok bayt ödenip kesin bilgi yerine belirsizlik alınır.

  B2. 250 B SINIRINA ULAŞILAMIYOR. Tam liste 117 komşuya kadar sığar, 118'de
      `wire` PayloadTooLarge yükseltir. Ama komşu tablosu 64 giriştir
      (`nbr_table_max`) ve taşması koşumu zaten geçersiz kılar; 64 komşuluk
      tam liste 143 bayttır. Brief §5'in "yoğun çizgede 250 B aşılır" cümlesi
      ancak tablo sınırı da büyütülürse doğrudur. İki sınır birlikte raporlanmalı.

  B3. YANLIŞ POZİTİF GEÇERSİZLİK ÜRETEBİLİR (gösterildi). `naive` ilkesiyle
      4 baytlık filtre, n=30 / ort. derece 6,2 çizgelerinde 25 tohumun 2'sinde
      G[C]'yi KOPARIYOR; gerçek koşum + `validate.validate` bunu `disconnected`
      olarak yakalıyor ve kopan bileşeni adıyla veriyor (tohum 16: {8,18},
      tohum 17: {5}). Zincir: bit dolu -> "bitişik" -> bitişik olmayan çift
      bulunamaz -> işaretlenmez -> omurga CDS değil -> G2 çöker.

  B4. 64 BAYT BU DERECELERDE KAZAEN GÜVENLİ. Aynı tarama 64 baytla sıfır sapma
      veriyor; sapma ortalama derece ~60'ta başlıyor (8 örnekte 1), ~72'de 2/8.
      Yani güvenlik bir garanti değil NİCEL BİR KAZAdır ve rapor onu
      "gözlenmedi" diye yazmalıdır, "olamaz" diye değil.

  B5. PARÇALAMA `tx`İ ARTIRMAZ (sıra ile), GECİKME ÖDER. Ölçüm: parça döngüsü
      bootstrap penceresinden (7 çerçeve) uzunsa bütün düğümler eksik görüşle
      karar veriyor ve işaretlerin %0-25'i tam listeninkinden farklı çıkıyor;
      FARK HEP FAZLA İŞARETLEME yönünde (eksik işaretleme sıfır, ölçüldü),
      dolayısıyla geçerlilik korunuyor. Döngü pencereye sığdığında (parça >= 4
      id) sapma sıfır. Topluca parçalamada `tx` döngü katına çıkıyor.

  B6. BLOOM'UN KONUM TÜRETİMİ ÖLÇÜLEREK DÜZELTİLDİ. Kirsch-Mitzenmacher çifte
      karması m=512'de formülün bin katı yanlış pozitif veriyordu; k bağımsız
      karma formüle oturuyor. Ayrıntı `Bloom` docstring'inde.

TELE NE KONUR. Özet, HELLO'nun zaten var olan değişken uzunluklu 16-bit sözcük
dizisine konur. O alanın BB-CVC'deki adı `mis_nbrs`tir; WuLi-Dominating'de MIS yoktur ve alan
brief §5'in "HELLO2" özetidir. Kazanç: boyut muhasebesi gerçek kodlayıcıdan
geçer, 250 B sınırını gerçek `wire._guard` dayatır, `Counters.max_payload`
gerçek çerçeveyi ölçer. Taklit yoktur.

  BU BİR SEÇİM DEĞİL, YANLIŞ BİR VARSAYIMIN SONUCUYDU (kayda geçsin). Gerekçem
  "`api.py` ve `wire.py` dondurulmuştur" idi; DOĞRU DEĞİLDİ. wire.py başka
  agent'ların dosyası olmak ile değişemez olmak aynı şey değil: bb-core bu
  oturumda istek üzerine TOKEN ve TOKEN_DONE tiplerini ekledi ve yenisini
  eklemeyi teklif etti. Ben sormadım. Kendi koyduğun kısıt, hiçbir şey onu
  sınamadığı için asla yanlışlayamayacağın tek kısıt türüdür.
  Ekip lideri kararı: tel yeniden yapılandırılmayacak, çünkü `hello_size`
  13+2n olmaktan çıkarsa BULGU 16'nın aritmetiği, çalışan örneğin kalibrasyonu,
  şekil 6'nın ölçülen noktaları ve bir bb-figures testi yeniden ölçülmek zorunda
  kalır; kapatılan tehlike ise gizil. Yeniden açılırsa doğru tasarım YENİ BİR
  MsgType DEĞİL, Hello gövdesinde ayrı bir alandır: WuLi-Dominating'in gönderdiği şey her
  bakımdan bir HELLO'dur ve ayrı tip vermek `by_type_tx`te HELLO'nun maliyetini
  olduğundan küçük gösterirdi.

  ALANIN İKİ ANLAMLI OLMASININ BEDELİ (ölçüldü). Taban sınıftaki ERİŞİLEBİLİR
  bir metoda `n.mis_nbrs`i MIS listesi sanan dördüncü bir okuyucu eklemek, WuLi-Dominating'i
  SESSİZCE bozar: n=20 tohum 1'de örtü 12'den 20 düğüme, Σw 957'den 1180'e
  çıkıyor (+%23) ve koşum yine `converged` ve doğrulayıcıya göre GEÇERLİ
  görünüyor. Yani hata bir istisna değil, farklı bir cevap olarak çıkar.
  KORUMA (bb-algo uyguladı, 2026-09-15). Taban sınıf alanı artık TEK bir
  erişimciden okuyor (`BbcvcNode._nbr_mis`, dört okuma yeri oradan geçiyor) ve
  bu sınıf o erişimciyi ezip YÜKSELTİYOR. Yarın taban sınıfa eklenen bir
  okuyucu, sessiz bir cevap değişikliği yerine ilk çalıştığı anda yığın izi
  veriyor; testi bunu mutasyonla gösteriyor.
  Bunun bir yan sonucu, eski bir ALARM testinin GARANTİye dönüşmesi oldu:
  3-atlama kuralı geri açıldığında eskiden sessizce çalışıp kendini bastırıyordu
  (tam komşu listesi kuralın mesafe-2 koşulunu sağladığı için -- bir KAZA);
  şimdi çalışamıyor, çünkü erişimci yükseliyor.
  SINIR AYNEN DURUYOR: koruma yalnız erişimciden GEÇEN okuyucu içindir.
  `n.mis_nbrs`i doğrudan yazan biri WuLi-Dominating'i yine sessizce bozar. Tehlike tek
  dosyada tek satırlık bir disipline indirgenmiştir, yok edilmemiştir.
"""
from __future__ import annotations

import itertools
import math
import os
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from ccvc.bb import wire
except ImportError:  # pragma: no cover - doğrudan çalıştırma
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    from ccvc.bb import wire

from ccvc.bb.api import MsgType, PayloadTooLarge, Role, key_of
from ccvc.bb.bbcvc import (PH_CONN, PH_COVER, PH_MIS, BbcvcNode, BbcvcParams,
                           BbcvcRun)
from ccvc.bb.bootstrap import BootNeighbor

Edge = Tuple[int, int]

# kodlama adları (brief §5 maddeleri)
ENC_FULL = "full"
ENC_BLOOM = "bloom"
ENC_CHUNK = "chunked"
ENCODINGS = (ENC_FULL, ENC_BLOOM, ENC_CHUNK)

# belirsizliğin nasıl çözüleceği
POL_SAFE = "safe"      # brief §5/1: yalnız kesin negatifler
POL_NAIVE = "naive"    # belirsizi olduğu gibi kabul et
POLICIES = (POL_SAFE, POL_NAIVE)

_ENC_CODE = {ENC_FULL: 1, ENC_BLOOM: 2, ENC_CHUNK: 3}
_CODE_ENC = {v: k for k, v in _ENC_CODE.items()}


class Tri(IntEnum):
    """Üç değerli üyelik cevabı. MAYBE bir hata değil, kodlamanın BEDELİdir."""

    NO = 0
    MAYBE = 1
    YES = 2


def resolve(t: Tri, policy: str) -> bool:
    """Üç değerli cevabı iki değerliye indir.

    `safe`: yalnız YES "evet"tir. Bu tek satır brief §5/1'in iki kuralını da
    kapsar, çünkü işaretlemede aranan şey BİTİŞİK DEĞİLLİK, budamada aranan şey
    ÖRTÜLÜLÜKTÜR; ikisinde de "evet"i kısmak omurgayı büyütür.
    `naive`: MAYBE "evet"tir; boyut kazancı korunur, kesinlik kaybedilir.
    """
    if policy == POL_SAFE:
        return t is Tri.YES
    if policy == POL_NAIVE:
        return t is not Tri.NO
    raise ValueError(f"bilinmeyen ilke: {policy!r} (beklenen {POLICIES})")


# ==========================================================================
# 64 baytlık Bloom (brief §5/1)
# ==========================================================================
def _mix32(x: int) -> int:
    """32 bitlik çığ karması. RNG DEĞİLDİR: aynı id her düğümde aynı biti verir."""
    x &= 0xFFFFFFFF
    x = ((x >> 16) ^ x) * 0x45D9F3B & 0xFFFFFFFF
    x = ((x >> 16) ^ x) * 0x45D9F3B & 0xFFFFFFFF
    return (x >> 16) ^ x


@dataclass
class Bloom:
    """Sabit boyutlu üyelik özeti. Yanlış negatif YOKTUR, yanlış pozitif vardır.

    KONUM TÜRETİMİ ÖLÇÜLEREK SEÇİLDİ. İlk sürüm Kirsch-Mitzenmacher çifte
    karmasıydı (h1 + i*h2); "iki karma k karma kadar iyidir" savı literatürde
    büyük m için doğrudur, m=512'de DEĞİL:

        derece      formül     çifte karma   gelişmiş çifte   k bağımsız karma
        10          1,9e-7     2,1e-4        1,0e-4           0,0 (300 denemede)
        20          2,7e-5     5,5e-4        1,8e-4           2,5e-5
        36          1,2e-3     2,4e-3        1,6e-3           1,2e-3

    Sebep yapısaldır: m ikinin kuvveti olduğundan adım h2 mod 512 yalnız 256
    tek değer alabilir ve bir elemanın konumları ARİTMETİK DİZİdir; diziler
    birbirini beklenenden çok örter. Düşük derecede ölçülen oran formülün ÜÇ
    KAT BÜYÜKLÜĞÜ kadar üstündeydi, yani formüle güvenmek deneyin bütün
    yanlış pozitif muhasebesini bozardı. k bağımsız karma formüle oturuyor;
    bedeli ESP32'de iki çarpma yerine k çarpmadır ve bu bilinçli bir seçimdir.
    """

    nbytes: int = 64
    k: int = 8
    bits: bytearray = field(default_factory=bytearray)

    def __post_init__(self) -> None:
        if self.nbytes % 2:
            raise ValueError("Bloom boyutu 16-bit sözcüklere bölünebilmeli")
        if not self.bits:
            self.bits = bytearray(self.nbytes)
        elif len(self.bits) != self.nbytes:
            raise ValueError(f"bit dizisi {len(self.bits)} B, beklenen {self.nbytes}")

    @property
    def nbits(self) -> int:
        return self.nbytes * 8

    def _positions(self, x: int) -> Tuple[int, ...]:
        m = self.nbits
        base = (int(x) * 0x9E3779B1) & 0xFFFFFFFF
        return tuple(_mix32(base + i * 0x85EBCA77) % m for i in range(self.k))

    def add(self, x: int) -> None:
        for p in self._positions(int(x)):
            self.bits[p >> 3] |= 1 << (p & 7)

    def query(self, x: int) -> Tri:
        """Bloom ASLA YES demez: dolu bitler yalnız MAYBE'dir."""
        for p in self._positions(int(x)):
            if not (self.bits[p >> 3] >> (p & 7)) & 1:
                return Tri.NO
        return Tri.MAYBE

    def popcount(self) -> int:
        return sum(bin(b).count("1") for b in self.bits)

    def to_words(self) -> Tuple[int, ...]:
        return tuple(
            self.bits[i] | (self.bits[i + 1] << 8) for i in range(0, self.nbytes, 2)
        )

    @classmethod
    def from_words(cls, words: Sequence[int], k: int = 8) -> "Bloom":
        b = bytearray()
        for w in words:
            b.append(w & 0xFF)
            b.append((w >> 8) & 0xFF)
        return cls(nbytes=len(b), k=k, bits=b)

    @classmethod
    def of(cls, ids: Iterable[int], nbytes: int = 64, k: int = 8) -> "Bloom":
        f = cls(nbytes=nbytes, k=k)
        for x in ids:
            f.add(x)
        return f


def bloom_fpr_formula(n: int, nbytes: int = 64, k: int = 8) -> float:
    """(1 - e^{-kn/m})^k. KURAMSAL değerdir; testler ÖLÇÜLENİ kullanır."""
    m = nbytes * 8
    if n <= 0:
        return 0.0
    return (1.0 - math.exp(-k * n / m)) ** k


def bloom_optimal_k(n: int, nbytes: int = 64) -> int:
    """m/n * ln2, aşağı/yukarı yuvarlamanın iyisi. Seçimi belgelemek için."""
    m = nbytes * 8
    if n <= 0:
        return 1
    lo = max(1, int((m / n) * math.log(2)))
    return min((lo, lo + 1), key=lambda k: bloom_fpr_formula(n, nbytes, k))


# ==========================================================================
# HELLO'nun sözcük dizisine konan özet
# ==========================================================================
# başlık sözcüğü: enc(3) | marked(1) | total(6) | index(6)
_H_ENC_SHIFT = 13
_H_MARK_SHIFT = 12
_H_TOTAL_SHIFT = 6
_MAX_CHUNKS = 63


def pack_header(enc: str, marked: bool, total: int, index: int) -> int:
    if not 1 <= total <= _MAX_CHUNKS or not 0 <= index < total:
        raise ValueError(f"parça göstergesi geçersiz: {index}/{total}")
    return ((_ENC_CODE[enc] << _H_ENC_SHIFT)
            | ((1 if marked else 0) << _H_MARK_SHIFT)
            | (total << _H_TOTAL_SHIFT)
            | index)


def unpack_header(word: int) -> Tuple[str, bool, int, int]:
    code = (word >> _H_ENC_SHIFT) & 0b111
    if code not in _CODE_ENC:
        raise ValueError(f"bilinmeyen kodlama kodu: {code}")
    return (_CODE_ENC[code],
            bool((word >> _H_MARK_SHIFT) & 1),
            (word >> _H_TOTAL_SHIFT) & _MAX_CHUNKS,
            word & _MAX_CHUNKS)


def chunk_count(n_ids: int, chunk_words: int) -> int:
    """Kaç çerçeveye bölünür. Boş liste bile bir çerçeve taşır (başlık)."""
    if chunk_words <= 0:
        raise ValueError("chunk_words pozitif olmalı")
    return max(1, -(-n_ids // chunk_words))


def encode_summary(enc: str, nbr_ids: Sequence[int], marked: bool, *,
                   index: int = 0, chunk_words: int = 8,
                   bloom_bytes: int = 64, bloom_k: int = 8) -> Tuple[int, ...]:
    """Bu HELLO'da taşınacak sözcükler. KIRPMA YOK; sınırı `wire` dayatır."""
    ids = sorted(int(i) for i in nbr_ids)
    if enc == ENC_FULL:
        return (pack_header(enc, marked, 1, 0),) + tuple(ids)
    if enc == ENC_BLOOM:
        return (pack_header(enc, marked, 1, 0),) + Bloom.of(
            ids, bloom_bytes, bloom_k).to_words()
    if enc == ENC_CHUNK:
        total = chunk_count(len(ids), chunk_words)
        i = index % total
        part = ids[i * chunk_words:(i + 1) * chunk_words]
        return (pack_header(enc, marked, total, i),) + tuple(part)
    raise ValueError(f"bilinmeyen kodlama: {enc!r} (beklenen {ENCODINGS})")


@dataclass
class Summary:
    """Bir komşunun özetinden ALICIDA biriken bilgi.

    `chunked` dışında tek çerçevede tamamlanır. Parçalıda parçalar biriktirilir
    ve `complete` ancak bütün indisler görüldüğünde doğrudur; o ana kadar
    "listede yok" cevabı NO değil MAYBE'dir. Bütün belirsizlik bu tek satırda.
    """

    enc: str
    marked: bool = False
    total: int = 1
    ids: Set[int] = field(default_factory=set)
    seen: Set[int] = field(default_factory=set)
    bloom: Optional[Bloom] = None
    chunks: Dict[int, Tuple[int, ...]] = field(default_factory=dict)
    frames: int = 0

    @property
    def complete(self) -> bool:
        if self.enc == ENC_CHUNK:
            return len(self.seen) >= self.total
        return self.frames > 0

    def absorb(self, words: Sequence[int], bloom_k: int = 8) -> None:
        if not words:
            raise ValueError("özet en az başlık sözcüğü taşımalı")
        enc, marked, total, index = unpack_header(words[0])
        body = tuple(words[1:])
        self.enc = enc
        self.marked = marked
        self.total = total
        self.frames += 1
        if enc == ENC_BLOOM:
            self.bloom = Bloom.from_words(body, k=bloom_k)
            return
        self.chunks[index] = body
        self.seen.add(index)
        self.ids = set()
        for part in self.chunks.values():
            self.ids.update(part)

    def query(self, x: int) -> Tri:
        """x, bu komşunun komşu kümesinde mi? Üç değerli."""
        if self.frames == 0:
            return Tri.MAYBE
        if self.enc == ENC_BLOOM:
            return Tri.MAYBE if self.bloom is None else self.bloom.query(x)
        if x in self.ids:
            return Tri.YES
        return Tri.NO if self.complete else Tri.MAYBE


# ==========================================================================
# Wu-Li kuralları, üç değerli bilgi üzerinde
# ==========================================================================
@dataclass
class Knowledge:
    """Tek bir düğümün elindeki HER ŞEY. Çizge YOKTUR (api I1).

    `me` kendi id'si, `nbrs` kendi çift yönlü komşuları (kesin bilgi),
    `summaries` komşuların özetleri, `keys` komşuların anahtarları.
    """

    me: int
    nbrs: Set[int]
    summaries: Dict[int, Summary]
    keys: Dict[int, Tuple[int, int]] = field(default_factory=dict)
    my_key: Tuple[int, int] = (0, 0)
    policy: str = POL_SAFE
    two_sided: bool = True

    def _ask(self, u: int, x: int) -> Tri:
        s = self.summaries.get(u)
        return Tri.MAYBE if s is None else s.query(x)

    def member(self, x: int, u: int) -> Tri:
        """x ∈ N[u]? (kapalı komşuluk)

        İki cevap KENDİ bilgimizden kesindir ve özete hiç sorulmaz:
        x == u her zaman doğrudur, x == ben ise u benim komşumsa doğrudur.
        Bunları özete sormak, bilinen bir gerçeği kodlamanın belirsizliğine
        teslim etmek olurdu.
        """
        if x == u:
            return Tri.YES
        if x == self.me:
            return Tri.YES if u in self.nbrs else Tri.NO
        return self._ask(u, x)

    def adjacent(self, u: int, w: int) -> Tri:
        """u ile w bitişik mi? İki özet de sorulur (bedava doğruluk).

        İKİ TARAFLI SORGU BİR SEÇİMDİR ve ölçülür (`two_sided`). u'nun özeti
        w hakkında MAYBE derken w'nin özeti u hakkında NO diyebilir; Bloom'un
        yanlış negatifi olmadığından NO KESİNDİR ve çift belirsizliği keser.
        Yanlış pozitifin karar değiştirmesi için İKİ filtrenin birden yanılması
        gerekir. Tek taraflı sorgu daha çok hata üretir; farkı ölçmek için
        parametre bırakıldı, varsayılan iki taraflıdır çünkü ek mesaj İSTEMEZ.
        """
        if u == w:
            return Tri.YES
        a = self._ask(u, w)
        if not self.two_sided:
            return a
        b = self._ask(w, u)
        if a is Tri.NO or b is Tri.NO:
            return Tri.NO
        if a is Tri.YES or b is Tri.YES:
            return Tri.YES
        return Tri.MAYBE

    # ------------------------------------------------------------ kurallar
    def mark(self) -> bool:
        """Wu-Li işaretleme: bitişik OLMAYAN iki komşum varsa işaretliyim.

        `safe` ilkesinde MAYBE "bitişik değil" sayılır, yani belirsizlik DAHA
        ÇOK işaretleme demektir (brief §5/1).
        """
        ns = sorted(self.nbrs)
        for u, w in itertools.combinations(ns, 2):
            if not resolve(self.adjacent(u, w), self.policy):
                return True
        return False

    def prune(self, k_max: int = 2) -> Optional[Tuple[int, ...]]:
        """Rule-k: N[v] ⊆ ∪ N[u_i], u_i'ler işaretli, aralarında bağlı ve
        hepsinin anahtarı benimkinden BÜYÜK ise işaretimi kaldırırım.

        Anahtar kırılması karşılıklı budamayı imkânsız kılar: v yalnız
        kendinden BÜYÜK anahtarlılara yaslanır, dolayısıyla iki düğüm birbirini
        budayamaz. (Wu-Li id kullanır; burada depo genelindeki sıkı sıralama
        olan `key = (w/(deg+1), id)` kullanılır, ikisi de sıkı tam sıralamadır.)

        Döner: budamayı gerekçelendiren örtücü küme, yoksa None.
        """
        cand = sorted(u for u in self.nbrs
                      if self.summaries.get(u) is not None
                      and self.summaries[u].marked
                      and self.keys.get(u, (0, 0)) > self.my_key)
        if not cand:
            return None
        closed = sorted({self.me} | self.nbrs)
        for size in range(1, max(1, k_max) + 1):
            for combo in itertools.combinations(cand, size):
                if not self._mutually_linked(combo):
                    continue
                if all(any(resolve(self.member(x, u), self.policy) for u in combo)
                       for x in closed):
                    return combo
        return None

    def _mutually_linked(self, combo: Sequence[int]) -> bool:
        return all(resolve(self.adjacent(a, b), self.policy)
                   for a, b in itertools.combinations(combo, 2))


# ==========================================================================
# TAM BİLGİLİ REFERANS (bağımsız gerçekleme)
# ==========================================================================
def reference_backbone(adj: Dict[int, Set[int]],
                       keys: Dict[int, Tuple[int, int]],
                       k_max: int = 2) -> Dict[str, object]:
    """Wu-Li + Rule-k'nın düz küme cebriyle yazılmış hâli.

    `Knowledge` ile HİÇBİR KOD PAYLAŞMAZ. Amacı tam olarak budur: dağıtık yol
    ile bu yol `full` kodlamasında BİREBİR aynı sonucu vermek zorundadır, ve bu
    eşitlik kodlama katmanının doğruluğunun asıl kanıtıdır. Ortak yardımcı
    kullanmak, iki tarafı aynı varsayımda anlaştırıp denetimi boşaltırdı.
    """
    marked = set()
    for v, nv in adj.items():
        ns = sorted(nv)
        if any(b not in adj[a] for a, b in itertools.combinations(ns, 2)):
            marked.add(v)
    pruned = set()
    for v in sorted(marked):
        closed_v = {v} | adj[v]
        cand = sorted(u for u in adj[v] if u in marked and keys[u] > keys[v])
        hit = None
        for size in range(1, max(1, k_max) + 1):
            for combo in itertools.combinations(cand, size):
                if any(b not in adj[a] for a, b in itertools.combinations(combo, 2)):
                    continue
                union: Set[int] = set()
                for u in combo:
                    union |= {u} | adj[u]
                if closed_v <= union:
                    hit = combo
                    break
            if hit:
                break
        if hit:
            pruned.add(v)
    return {"marked": marked, "pruned": pruned, "backbone": marked - pruned}


def adjacency(edges: Sequence[Edge], nodes: Optional[Sequence[int]] = None
              ) -> Dict[int, Set[int]]:
    ns = set(nodes or [])
    for u, v in edges:
        ns.add(u)
        ns.add(v)
    adj: Dict[int, Set[int]] = {v: set() for v in sorted(ns)}
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    return adj


def keys_of(adj: Dict[int, Set[int]], weights: Dict[int, float]
            ) -> Dict[int, Tuple[int, int]]:
    """Depo genelindeki anahtar: key(v) = (w(v)/(deg+1), id)."""
    return {v: key_of(weights[v], len(adj[v]), v) for v in adj}


# ==========================================================================
# parametreler
# ==========================================================================
@dataclass
class WuLiParams(BbcvcParams):
    """BB-CVC parametreleri + WuLi-Dominating'in kodlama ve ilke eksenleri.

    `bloom_k = 8` SEÇİLMİŞTİR, varsayılan değil. m=512 bit için kuramsal yanlış
    pozitif oranı (formül, ölçüm testte):

        derece   5       10      20      36      60      110
        k=6      3,4e-8  1,8e-6  8,3e-5  1,7e-3  1,7e-2  1,5e-1
        k=8      1,0e-9  1,9e-7  2,7e-5  1,2e-3  1,9e-2  2,1e-1
        k=10     4,9e-11 3,1e-8  1,3e-5  1,1e-3  2,5e-2  2,9e-1

    Kıyas kümesinin ÖLÇÜLEN en büyük derecesi 36'dır (BULGUR_BB §BULGU 4);
    k=8 orada en iyiye yakındır ve 36'nın ötesinde k=10/12'den daha yavaş
    bozulur. k düğümler arasında AYNI olmak zorundadır, bu yüzden dereceye göre
    seçilemez; sabitlemek bir tasarım kararıdır ve bedeli budur.

    `mis_nbrs_max` burada bilerek çok büyüktür: HELLO'nun sözcük dizisi WuLi-Dominating'de
    G8'in mis listesi DEĞİLDİR, dolayısıyla G8'in 5'lik yumuşak sınırı geçerli
    değildir. Tek gerçek sınır 250 B'dir ve onu `wire` dayatır. Sınır aşıldığında
    `PayloadTooLarge` YÜKSELİR; kırpma yoktur, çünkü kırpılmış bir komşu listesi
    Wu-Li'nin işaretleme kuralını sessizce yanlış cevaplar.
    """

    encoding: str = ENC_FULL
    policy: str = POL_SAFE
    k_max: int = 2               # Rule-k'nın k'sı (yazında Rule 1 ve Rule 2)
    chunk_words: int = 8         # parçalı kodlamada çerçeve başına id
    chunk_wait: bool = False     # görüş tamamlanana kadar karar ertelensin mi
    chunk_wait_periods: int = 8  # ertelemenin üst sınırı; sonra kısmi görüşle karar
    chunk_burst: bool = False
    """Parçalar bir periyotta TOPLUCA mı gönderilsin?

    İKİ PARÇALAMA TASARIMI VARDIR ve brief §5/2 ikincisini varsayar:
      False (varsayılan, sıra ile): her periyodik HELLO bir sonraki parçayı
        taşır. `tx` HİÇ ARTMAZ; ödenen şey GECİKMEDİR, çünkü alıcının görüşü
        ancak `total` periyot sonra tamamlanır ve o ana kadar "listede yok"
        cevabı NO değil MAYBE'dir.
      True (topluca): bir periyotta `total` çerçeve birden çıkar. Görüş hemen
        tamamlanır, `tx` `total` katına çıkar -- brief §5/2'nin "tx artar"
        cümlesi tam olarak bu tasarımı anlatır.
    İkisi de ölçülür; hangisinin seçildiği rapora yazılır.
    """
    bloom_bytes: int = 64        # brief §5/1: sabit 64 B
    bloom_k: int = 8
    two_sided: bool = True       # bitişiklik sorusu iki özete birden sorulsun mu
    mis_nbrs_max: int = 4096

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.encoding not in ENCODINGS:
            raise ValueError(f"bilinmeyen kodlama: {self.encoding!r}")
        if self.policy not in POLICIES:
            raise ValueError(f"bilinmeyen ilke: {self.policy!r}")

    @property
    def chunk_wait_ms(self) -> int:
        return self.chunk_wait_periods * self.t_hello_ms


# ==========================================================================
# düğüm
# ==========================================================================
class WuLiNode(BbcvcNode):
    """WuLi-Dominating düğümü: Faz 1 Wu-Li, gerisi BbcvcNode.

    ROL TEK YÖNLÜ KALIR (api I5). Wu-Li'nin budaması bir İŞARETİ kaldırır, rolü
    değil: düğüm işaretini HELLO başlığındaki bir bitle duyurur ve `role`u ancak
    budama da bittikten sonra, bir kez, MIS'e yazar. Böylece "rol yalnız OUT ->
    ileri" değişmezi bozulmadan Wu-Li'nin iki adımı da gerçeklenir.

    `Role.MIS` burada BAĞIMSIZ KÜME demek değildir, "omurgadayım" demektir;
    Wu-Li'nin tek bir omurga sınıfı vardır ve `Role.in_backbone` yalnız MIS ve
    CONNECTOR için doğrudur, bu yüzden MIS seçilmiştir. CONNECTOR hiç kullanılmaz
    çünkü Wu-Li'de bağlayıcı faz yoktur: işaretli küme zaten bağlıdır.
    """

    def _init_algo_state(self) -> None:
        super()._init_algo_state()
        self._wl_sum: Dict[int, Summary] = {}
        self._wl_chunk_i = 0
        self._wl_marked = False
        self._wl_pruned_by: Optional[Tuple[int, ...]] = None
        self._wl_view_complete: Optional[bool] = None
        self._wl_forced_partial = False
        self._wl_wait_since: Optional[int] = None
        self._wl_decided_ms: Optional[int] = None
        self._wl_frames_out = 0
        #: Karar ANINDA en az bilgili komşudan kaç çerçeve gelmişti. Parçalama
        #: bedava mı değil mi sorusunun ölçülen cevabı budur: `total` bu
        #: sayıdan küçükse görüş zaten tamamlanmış demektir.
        self._wl_frames_at_decision: Optional[int] = None

    # ------------------------------------------------------- tele koyulan
    def mis_nbrs(self) -> Tuple[int, ...]:
        """HELLO'nun sözcük dizisi. WuLi-Dominating'de bu bir MIS listesi DEĞİL, özettir.

        YAN ETKİLİDİR: her çağrı BİR ÇERÇEVE üretir ve parçalı kodlamada parça
        imlecini ilerletir. Tek çağıran `_maybe_hello`dur (HELLO başına tam bir
        kez), yani imleç çerçeve sayısıyla birebirdir. Ölçüm buna dayandığı için
        başka bir yerden çağrılmamalıdır.
        """
        ids = [n.nid for n in self._nbrs_active()]
        words = encode_summary(
            self.p.encoding, ids, self._wl_marked, index=self._wl_chunk_i,
            chunk_words=self.p.chunk_words, bloom_bytes=self.p.bloom_bytes,
            bloom_k=self.p.bloom_k)
        if self.p.encoding == ENC_CHUNK:
            self._wl_chunk_i = (self._wl_chunk_i + 1) % chunk_count(
                len(ids), self.p.chunk_words)
        self._wl_frames_out += 1
        return words

    def _on_hello(self, now: int, src_mac: int, rssi, h) -> None:
        super()._on_hello(now, src_mac, rssi, h)
        if h.src == self.nid or h.src not in self.nbrs or not h.mis_nbrs:
            return
        s = self._wl_sum.get(h.src)
        if s is None:
            s = Summary(enc=self.p.encoding)
            self._wl_sum[h.src] = s
        s.absorb(h.mis_nbrs, bloom_k=self.p.bloom_k)

    # --------------------------------------------------------- Faz 1 (WuLi-Dominating)
    def _knowledge(self, nb: Sequence[BootNeighbor]) -> Knowledge:
        return Knowledge(
            me=self.nid,
            nbrs={n.nid for n in nb},
            summaries={n.nid: self._wl_sum[n.nid] for n in nb if n.nid in self._wl_sum},
            keys={n.nid: (n.key, n.nid) for n in nb},
            my_key=self._mykey(),
            policy=self.p.policy,
            two_sided=self.p.two_sided,
        )

    def _wl_have_all(self, nb: Sequence[BootNeighbor]) -> bool:
        return all(n.nid in self._wl_sum and self._wl_sum[n.nid].frames > 0
                   for n in nb)

    def _wl_all_complete(self, nb: Sequence[BootNeighbor]) -> bool:
        return all(n.nid in self._wl_sum and self._wl_sum[n.nid].complete
                   for n in nb)

    def _backbone_step(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        """Faz 1 dikişi (bbcvc.BbcvcNode._backbone_step sözleşmesi).

        Kapılar taban sınıfınkiyle AYNIdır: işaretleme PH_MIS'te, budama
        yerel bariyerin arkasında PH_CONN'da. Tek fark iki kuralın içeriğidir.

        SÖZLEŞMEDEN BİR SAPMA VAR VE RAPORLANMIŞTIR. Dikiş, PH_COVER'a
        varıldığında B = MIS u CONNECTOR'ün bağlı VE BASKIN olmasını ister.
        Wu-Li bunu bağlı ve TAM OLMAYAN çizgelerde garanti eder; K_n'de
        işaretli küme BOŞtur, çünkü her düğümün komşuları birbirine bitişiktir.
        Bu Wu-Li'nin bilinen dejenere durumudur, gerçeklemenin hatası değildir;
        Faz 2 örtüyü yine kurar ve sonuç GEÇERLİdir (testle gösterilmiştir).
        Kıyas kümesinde tam çizge yoktur, ama kapı koşulu tam çizgede düşer.
        """
        if self.phase == PH_MIS:
            self._wuli_mark(now, nb)
        if self.phase == PH_CONN and self._barrier(nb, PH_CONN):
            self._wuli_prune(nb)

    def _wuli_mark(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        """Wu-Li işaretleme. Rol YAZILMAZ; yalnız işaret kurulur ve duyurulur.

        BEKLEME PENCERESİ. Parçalı kodlamada görüş birkaç HELLO boyunca EKSİKTİR.
        `chunk_wait=False` (varsayılan) ise düğüm elindekiyle karar verir; bu
        kararın tam listeyle verilenden FARKLI olup olmadığı deneyin ölçtüğü
        şeydir. `chunk_wait=True` ise tamamlanmayı bekler, ama sonsuza kadar
        değil: `chunk_wait_ms` dolduğunda kısmi görüşle karar verilir ve bu
        `forced_partial` olarak işaretlenir. Kayıp bir parça yüzünden koşumun
        asılması, ölçülmesi gereken bir gecikmeyi ölçülemez bir kilitlenmeye
        çevirirdi.
        """
        if not nb:
            self._wl_marked = False
            self._wl_view_complete = True
            self.phase = PH_CONN
            self._touch()
            return
        if not self._wl_have_all(nb):
            return
        if self._wl_wait_since is None:
            self._wl_wait_since = now
        complete = self._wl_all_complete(nb)
        if self.p.chunk_wait and not complete:
            if now - self._wl_wait_since < self.p.chunk_wait_ms:
                return
            self._wl_forced_partial = True
        kn = self._knowledge(nb)
        self._wl_marked = kn.mark()
        self._wl_view_complete = complete
        self._wl_frames_at_decision = min(
            (self._wl_sum[n.nid].frames for n in nb if n.nid in self._wl_sum),
            default=0)
        self._wl_decided_ms = now
        self.phase = PH_CONN
        self._log("wuli_mark", marked=int(self._wl_marked),
                  complete=int(complete), deg=len(nb))
        self._touch()

    def _wuli_prune(self, nb: Sequence[BootNeighbor]) -> None:
        """Rule-k budaması, sonra rolün TEK yazılışı.

        Dikiş bu kuralı ancak bütün komşular >= PH_CONN iken çağırır, yani
        komşuların işaret bitleri KESİNLEŞMİŞTİR. Budama anahtar sıralamasına
        dayandığından iki düğüm birbirini budayamaz ve karar tek turda biter.
        """
        if self._wl_marked:
            combo = self._knowledge(nb).prune(self.p.k_max)
            self._wl_pruned_by = combo
            if combo is None:
                self.role = Role.MIS
                self._log("wuli_backbone")
            else:
                self._log("wuli_pruned", by=combo)
        self.phase = PH_COVER
        self._touch()

    def _nbr_mis(self, n: BootNeighbor) -> Tuple[int, ...]:
        """Taban sınıfın MIS listesi okuma yolu. WuLi-Dominating'de CEVABI YOKTUR.

        `_backbone_step` sözleşmesi bunu ZORUNLU kılar: alanı başka bir anlamda
        kullanan varyant bu erişimciyi ezip yükseltmek durumundadır, çünkü taban
        sınıf `mis_nbrs`in MIS kimlikleri mi yoksa komşu özeti mi taşıdığını tip
        denetimiyle ayırt edemez.

        Boş demet döndürmek YANLIŞ OLURDU: o, "MIS komşum yok" diye geçerli ama
        yanlış bir cevaptır ve kuralları sessizce çalıştırır -- düzeltmeye
        çalıştığımız başarısızlık biçiminin tam olarak aynısı, yalnız bir kat
        daha derinde. Burada yükselmek, taban sınıfa yarın eklenecek bir
        okuyucunun ilk çalıştığı anda yığın iziyle ölmesini sağlar.

        Meşru bir WuLi-Dominating yolu buraya HİÇ uğramaz: `mis_nbrs()` üreticidir ve
        ezilmiştir, `_rule_gap` boştur, `_rule_connector` ise `_backbone_step`
        ezildiği için erişilemezdir. Testler bunu koşum başına doğruluyor.
        """
        raise NotImplementedError(
            "WuLi-Dominating: HELLO'nun sözcük dizisi MIS listesi değil KOMŞU ÖZETİ "
            "taşıyor (brief §5). Bu alanı MIS kimlikleri olarak okuyan bir kural "
            "WuLi-Dominating'de yanlış şeyi okur; taban sınıfa yeni bir okuyucu eklendiyse ya "
            "WuLi-Dominating için de bir yol tanımlanmalı ya da okuyucu Faz 1'e taşınmalıdır."
        )

    def _rule_gap(self, now: int, nb: Sequence[BootNeighbor]) -> None:
        """Wu-Li'de 3-atlama boşluk kuralı YOKTUR ve olmamalıdır.

        O kural MIS+connector omurgasının bir tamirid1r: bağımsız küme 3 atlama
        uzaktaki iki MIS'i bağlayamaz. Wu-Li'nin işaretli kümesi bağlı olduğunu
        kendi teoreminden alır, dolayısıyla burada çalıştırmak fazladan düğüm
        eklemekten başka bir şey yapmaz. Boş gövde BİLİNÇLİDİR.
        """
        return

    def _maybe_hello(self, now: int) -> None:
        """Topluca parçalama: bir HELLO çıktıysa kalan parçaları da çıkar.

        Taban sınıfın muhasebesi (yük alanı, duyurulan rol, dirty bayrağı,
        periyot) KOPYALANMAZ; `super()` çağrılır ve gerçekten bir çerçeve
        çıktığı `_last_hello_ms` değişiminden anlaşılır. Ek çerçeveler gerçek
        platformdan geçer, dolayısıyla tx/bytes_tx/max_payload muhasebesi
        kendiliğinden doğrudur.
        """
        before = self._last_hello_ms
        super()._maybe_hello(now)
        if not (self.p.chunk_burst and self.p.encoding == ENC_CHUNK):
            return
        if self._last_hello_ms == before:
            return
        total = chunk_count(len(self._nbrs_active()), self.p.chunk_words)
        for _ in range(total - 1):
            self._bcast(self._hello_payload(self.mis_nbrs()))

    # ---------------------------------------------------------- ölçüm ucu
    def wuli_state(self) -> Dict[str, object]:
        """Karar için KULLANILMAZ; yalnız ölçüm ve şekil okur."""
        return {
            "nid": self.nid,
            "marked": self._wl_marked,
            "pruned_by": self._wl_pruned_by,
            "backbone": self.role.in_backbone,
            "view_complete": self._wl_view_complete,
            "forced_partial": self._wl_forced_partial,
            "frames_at_decision": self._wl_frames_at_decision,
            "frames_out": self._wl_frames_out,
            "summaries": {u: s.frames for u, s in sorted(self._wl_sum.items())},
        }


# ==========================================================================
# koşum
# ==========================================================================
@dataclass
class WuLiRun(BbcvcRun):
    """BbcvcRun + WuLi-Dominating'in kendi ölçtükleri."""

    encoding: str = ENC_FULL
    policy: str = POL_SAFE
    marked: Tuple[int, ...] = ()
    backbone: Tuple[int, ...] = ()
    pruned: Tuple[int, ...] = ()
    partial_decisions: int = 0
    forced_partial: int = 0
    frames_at_decision: int = 0
    chunk_cycle: int = 1
    reference_backbone: Tuple[int, ...] = ()
    mark_divergence: Tuple[int, ...] = ()
    backbone_divergence: Tuple[int, ...] = ()


def build_wuli_nodes(net, weights: Dict[int, float], k: int,
                     params: Optional[WuLiParams] = None) -> Dict[int, WuLiNode]:
    p = params or WuLiParams()
    return {nid: WuLiNode(weights[nid], net.port(nid), p, k) for nid in net.nodes}


def run_wuli(edges: Sequence[Edge], weights: Dict[int, float], k: int, *,
             scheduler: str = "sync", params: Optional[WuLiParams] = None,
             max_ms: int = 600_000, loss: float = 0.0, seed: int = 0,
             delay=None, tau_ms: int = 200, tick_ms: int = 200,
             rssi_range=None) -> WuLiRun:
    """WuLi-Dominating/{sync,async} koşumu.

    `bbcvc.run_bbcvc`a DELEGE EDER; `node_factory` ve `result_cls` kancaları
    tam bunun içindir. İlk sürümüm kurulum gövdesini kopyalamıştı ve o kopya
    bir gün sonra bb-algo'nun eklediği sayma sınırını ve `infeasible_reason`
    alanını KAÇIRDI; kopya tam olarak böyle kayar. Artık bootstrap kapısı,
    örtü/sahiplik çıkarımı, uygunsuzluk gerekçesi ve sayaç toplamı tek yerde.

    WuLi-Dominating'e özgü alanlar sonuç kurulduktan SONRA doldurulur, çünkü hepsi düğüm
    durumundan türer ve `run_bbcvc` onları bilmez.
    """
    from ccvc.bb.bbcvc import run_bbcvc

    p = params or WuLiParams()
    run = run_bbcvc(edges, weights, k, scheduler=scheduler, params=p,
                    max_ms=max_ms, loss=loss, seed=seed, delay=delay,
                    tau_ms=tau_ms, tick_ms=tick_ms, rssi_range=rssi_range,
                    node_factory=build_wuli_nodes, result_cls=WuLiRun)
    nodes = run.nodes
    ids = sorted({a for e in edges for a in e} | set(weights))
    adj = adjacency(edges, ids)
    ref = reference_backbone(adj, keys_of(adj, weights), p.k_max)

    run.encoding = p.encoding
    run.policy = p.policy
    run.marked = tuple(sorted(n for n, nd in nodes.items() if nd._wl_marked))
    run.backbone = tuple(sorted(n for n, nd in nodes.items()
                                if nd.role.in_backbone))
    run.pruned = tuple(sorted(n for n, nd in nodes.items()
                              if nd._wl_pruned_by is not None))
    run.partial_decisions = sum(1 for n in nodes.values()
                                if n._wl_view_complete is False)
    run.forced_partial = sum(1 for n in nodes.values() if n._wl_forced_partial)
    run.frames_at_decision = min(
        (n._wl_frames_at_decision for n in nodes.values()
         if n._wl_frames_at_decision is not None), default=0)
    run.chunk_cycle = (max((chunk_count(len(adj[v]), p.chunk_words) for v in adj),
                           default=1) if p.encoding == ENC_CHUNK else 1)
    run.reference_backbone = tuple(sorted(ref["backbone"]))
    run.mark_divergence = tuple(sorted(set(run.marked) ^ set(ref["marked"])))
    run.backbone_divergence = tuple(sorted(set(run.backbone) ^ set(ref["backbone"])))
    return run


# ==========================================================================
# ÖLÇÜM: boyut eğrisi (brief §5/4, §8 şekil 6)
# ==========================================================================
def summary_words(enc: str, deg: int, *, chunk_words: int = 8,
                  bloom_bytes: int = 64) -> int:
    """Bir çerçevenin taşıdığı sözcük sayısı (başlık dâhil)."""
    if enc == ENC_FULL:
        return 1 + deg
    if enc == ENC_BLOOM:
        return 1 + bloom_bytes // 2
    if enc == ENC_CHUNK:
        return 1 + min(deg, chunk_words)
    raise ValueError(f"bilinmeyen kodlama: {enc!r}")


def frame_bytes(enc: str, deg: int, *, chunk_words: int = 8,
                bloom_bytes: int = 64) -> int:
    """HELLO'nun bayt boyu. `wire.hello_size` ile hesaplanır, tahmin edilmez."""
    return wire.hello_size(summary_words(enc, deg, chunk_words=chunk_words,
                                         bloom_bytes=bloom_bytes))


def max_degree_within_limit(enc: str, *, chunk_words: int = 8,
                            bloom_bytes: int = 64, limit: int = 250) -> Optional[int]:
    """250 B'ye sığan en büyük derece. Sığmama yoksa None (sabit boyutlu kodlama).

    Arama YAPILIR, formül YAZILMAZ: `frame_bytes` üzerinden ilerlenir, böylece
    `wire`ın başlık boyu değişirse bu sayı da değişir.
    """
    if enc != ENC_FULL:
        return None if frame_bytes(enc, 0, chunk_words=chunk_words,
                                   bloom_bytes=bloom_bytes) <= limit else 0
    d = 0
    while frame_bytes(enc, d + 1) <= limit:
        d += 1
    return d


def size_curve(degrees: Sequence[int], *, chunk_words: int = 8,
               bloom_bytes: int = 64, chunk_burst: bool = False
               ) -> List[Dict[str, object]]:
    """Şekil 6'nın verisi: derece -> çerçeve boyu ve periyot başına bayt.

    `frames_per_period` topluca parçalamada `total`, sıra ile parçalamada 1'dir;
    `bytes_per_period` ikisini çarparak parçalamanın gerçek bedelini gösterir.
    """
    rows: List[Dict[str, object]] = []
    for d in degrees:
        for enc in ENCODINGS:
            nb = frame_bytes(enc, d, chunk_words=chunk_words, bloom_bytes=bloom_bytes)
            total = chunk_count(d, chunk_words) if enc == ENC_CHUNK else 1
            fpp = total if (enc == ENC_CHUNK and chunk_burst) else 1
            rows.append({
                "degree": d,
                "encoding": enc,
                "frame_bytes": nb,
                "over_limit": nb > wire.MAX_PAYLOAD if hasattr(wire, "MAX_PAYLOAD")
                else nb > 250,
                "chunks": total,
                "frames_per_period": fpp,
                "bytes_per_period": nb * fpp,
                "periods_to_complete": total if enc == ENC_CHUNK and not chunk_burst else 1,
            })
    return rows


# ==========================================================================
# ÖLÇÜM: Bloom yanlış pozitif oranı GERÇEK id uzayında
# ==========================================================================
def measure_bloom_fpr(deg: int, *, trials: int = 200, seed: int = 0,
                      bloom_bytes: int = 64, bloom_k: int = 8,
                      probes: int = 200, two_sided: bool = False) -> float:
    """Yanlış pozitif oranını ÖLÇ (formüle güvenme).

    MODEL. Gerçekte sorulan soru "u ile w bitişik mi"dir ve cevabı u'nun
    filtresi verir. Yanlış pozitif, u ile w GERÇEKTEN bitişik değilken u'nun
    filtresinin w'yi iddia etmesidir; bu yüzden N(u) rastgele kurulur ve w
    onun DIŞINDAN seçilir.

    `two_sided=True` `Knowledge.adjacent`in kuralını ölçer: kararın bozulması
    için u'nun filtresinin w'yi VE w'nin filtresinin u'yu iddia etmesi gerekir,
    yani İKİ AYRI ve BAĞIMSIZ filtrenin birden yanılması gerekir. İki küme bu
    yüzden ayrı ayrı çekilir; ilk sürümde ikinci küme birincinin kopyasıydı ve
    ölçüm tek taraflının aynısını veriyordu (yani hiçbir şey ölçmüyordu).

    id uzayı gerçek uzaydır: kimlikler `hash16(MAC)` ile üretildiğinden 16
    bitliktir.
    """
    state = (seed * 2654435761 + 12345) & 0xFFFFFFFF

    def _rand() -> int:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        return state & 0xFFFF

    def _set_of(size: int, exclude: Set[int]) -> Set[int]:
        out: Set[int] = set()
        while len(out) < size:
            x = _rand()
            if x not in exclude:
                out.add(x)
        return out

    hits = total = 0
    for _ in range(trials):
        u = _rand()
        nu = _set_of(deg, {u})
        fu = Bloom.of(nu, bloom_bytes, bloom_k)
        for _ in range(probes):
            w = _rand()
            if w == u or w in nu:
                continue          # gerçekten bitişik: yanlış pozitif olamaz
            total += 1
            if fu.query(w) is Tri.NO:
                continue
            if not two_sided:
                hits += 1
                continue
            nw = _set_of(deg, {u, w})     # u, N(w)'de DEĞİL: gerçekten bitişik değiller
            if Bloom.of(nw, bloom_bytes, bloom_k).query(u) is not Tri.NO:
                hits += 1
    return hits / total if total else 0.0


def decision_exposure(deg: int, fpr: float) -> float:
    """Düğüm BAŞINA kaç bozuk cevap bekleniyor? Doğru ölçü birimi budur.

    Sorgu başına oran tek başına yanıltıcıdır: işaretleme kuralı bir düğümde
    C(deg,2) çift sorar, yani maruziyet dereceyle KAREsel büyür. Derece 36'da
    630 soru vardır; sorgu başına 1,2e-3 oran düğüm başına 0,77 bozuk cevap
    demektir (tek taraflı sorguda). "Oran küçük" ile "karar güvenli" aynı şey
    değildir ve fark tam olarak bu çarpandır.
    """
    return (deg * (deg - 1) / 2.0) * fpr


# ==========================================================================
# ÖLÇÜM: merkezî kestirim (dağıtık koşumun ucuz ön elemesi)
# ==========================================================================
def build_summary(enc: str, ids: Sequence[int], marked: bool, *,
                  chunks_seen: Optional[int] = None, chunk_words: int = 8,
                  bloom_bytes: int = 64, bloom_k: int = 8) -> Summary:
    """Bir alıcının elinde biriken özeti kur. GERÇEK kodlayıcı kullanılır."""
    s = Summary(enc=enc)
    total = chunk_count(len(ids), chunk_words) if enc == ENC_CHUNK else 1
    take = total if chunks_seen is None else max(0, min(chunks_seen, total))
    for i in range(take):
        s.absorb(encode_summary(enc, ids, marked, index=i,
                                chunk_words=chunk_words, bloom_bytes=bloom_bytes,
                                bloom_k=bloom_k), bloom_k=bloom_k)
    return s


def predict_backbone(adj: Dict[int, Set[int]], keys: Dict[int, Tuple[int, int]],
                     enc: str, policy: str, *, k_max: int = 2,
                     chunks_seen: Optional[int] = None, chunk_words: int = 8,
                     bloom_bytes: int = 64, bloom_k: int = 8,
                     two_sided: bool = True) -> Dict[str, object]:
    """Kodlama + ilke verildiğinde omurganın ne olacağını merkezî olarak kestir.

    Düğüm kodunun KURALLARINI kullanır (`Knowledge`), çünkü kestirilecek olan
    şey kuralın kendisidir; kural burada ikinci kez YAZILMAZ. Kestirimin doğru
    olduğunun kanıtı `full` kodlamasında dağıtık koşumla ve bağımsız referansla
    üç yönlü eşleşmesidir; test bunu assert eder.
    """
    def _all(flags: Dict[int, bool]) -> Dict[int, Summary]:
        # Özet GÖNDERİCİYE aittir, alıcıya değil: her düğüm için bir kez kurulur.
        # (İlk sürüm her alıcı için yeniden kuruyordu; sonuç aynı, maliyet n katı.)
        return {u: build_summary(enc, sorted(adj[u]), flags.get(u, False),
                                 chunks_seen=chunks_seen, chunk_words=chunk_words,
                                 bloom_bytes=bloom_bytes, bloom_k=bloom_k)
                for u in adj}

    def _kn(v: int, sums: Dict[int, Summary]) -> Knowledge:
        return Knowledge(me=v, nbrs=set(adj[v]),
                         summaries={u: sums[u] for u in adj[v]}, keys=keys,
                         my_key=keys[v], policy=policy, two_sided=two_sided)

    pre = _all({})
    marked: Dict[int, bool] = {v: _kn(v, pre).mark() for v in sorted(adj)}
    post = _all(marked)
    pruned: Set[int] = {v for v in sorted(adj)
                        if marked[v] and _kn(v, post).prune(k_max) is not None}
    mset = {v for v, m in marked.items() if m}
    return {"marked": mset, "pruned": pruned, "backbone": mset - pruned}


def is_dominating(adj: Dict[int, Set[int]], s: Set[int]) -> bool:
    return all(v in s or any(u in s for u in adj[v]) for v in adj)


def is_connected_subset(adj: Dict[int, Set[int]], s: Set[int]) -> bool:
    if len(s) <= 1:
        return True
    start = next(iter(sorted(s)))
    seen, stack = {start}, [start]
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y in s and y not in seen:
                seen.add(y)
                stack.append(y)
    return seen == s


def cover_from_backbone(adj: Dict[int, Set[int]], keys: Dict[int, Tuple[int, int]],
                        backbone: Set[int]) -> Set[int]:
    """Faz 2'nin merkezî karşılığı: iki ucu da omurga dışında olan kenarın
    KÜÇÜK anahtarlı ucu örtüye girer (bbcvc._rule_cover ile aynı kural)."""
    cover = set(backbone)
    for v in sorted(adj):
        if v in backbone:
            continue
        if any(u not in backbone and keys[v] < keys[u] for u in adj[v]):
            cover.add(v)
    return cover


def screen_instance(adj: Dict[int, Set[int]], keys: Dict[int, Tuple[int, int]],
                    enc: str, policy: str, **kw) -> Dict[str, object]:
    """Bir örnek için: omurga CDS mi, Faz 2 sonrası örtü bağlı kalıyor mu.

    Bu bir ÖN ELEMEdir. "Omurga CDS değil" ile "koşum geçersiz biter" aynı şey
    değildir, çünkü Faz 3/4 örtüye düğüm EKLEYEBİLİR ve bağlılığı kazara
    onarabilir. Kesin cevap gerçek koşum + `validate.validate`tir; bu fonksiyon
    yalnız hangi örneklerin koşulmaya değer olduğunu söyler.
    """
    pred = predict_backbone(adj, keys, enc, policy, **kw)
    b = pred["backbone"]
    cover = cover_from_backbone(adj, keys, b)
    return {
        "backbone": b,
        "backbone_size": len(b),
        "dominating": is_dominating(adj, b),
        "backbone_connected": is_connected_subset(adj, b),
        "cover_connected": is_connected_subset(adj, cover),
        "cover_size": len(cover),
        "suspect": not (is_dominating(adj, b) and is_connected_subset(adj, b))
        or not is_connected_subset(adj, cover),
    }


# ==========================================================================
# çizge üreteci (ölçüm tarafı; düğüm kodunun parçası DEĞİLDİR)
# ==========================================================================
def udg(n: int, radius: float, seed: int, *, width: float = 1.0
        ) -> Tuple[List[Edge], Dict[int, float]]:
    """Birim disk çizgesi. Deterministik: aynı tohum aynı çizge.

    Ağırlık `1..100` aralığında, `bridge.weights_for("random")` ile aynı ruhta.
    """
    import random as _random
    rnd = _random.Random(seed)
    pts = {i: (rnd.uniform(0, width), rnd.uniform(0, width)) for i in range(1, n + 1)}
    edges = []
    for u in range(1, n + 1):
        for v in range(u + 1, n + 1):
            dx = pts[u][0] - pts[v][0]
            dy = pts[u][1] - pts[v][1]
            if dx * dx + dy * dy <= radius * radius:
                edges.append((u, v))
    weights = {i: float(rnd.randint(1, 100)) for i in range(1, n + 1)}
    return edges, weights


def connected_udg(n: int, radius: float, seed: int, *, tries: int = 60
                  ) -> Tuple[List[Edge], Dict[int, float]]:
    """Bağlı bir UDG bulana kadar yarıçapı büyüt (brief §1 bağlı çizge varsayar)."""
    r = radius
    for _ in range(tries):
        edges, weights = udg(n, r, seed)
        adj = adjacency(edges, list(weights))
        if adj and is_connected_subset(adj, set(adj)):
            return edges, weights
        r *= 1.08
    raise RuntimeError(f"bağlı UDG bulunamadı: n={n} r0={radius} tohum={seed}")


# ==========================================================================
# DENEY: brief §12/8 ve şekil 6
# ==========================================================================
@dataclass
class Case:
    """Bir deney hücresi: çizge + kodlama + ilke + zamanlayıcı."""

    n: int
    radius: float
    seed: int
    encoding: str = ENC_FULL
    policy: str = POL_SAFE
    scheduler: str = "sync"
    k: Optional[int] = None          # None = max derece (kapasite bağlayıcı olmasın)
    bloom_bytes: int = 64
    chunk_words: int = 8
    chunk_burst: bool = False
    two_sided: bool = True

    @property
    def name(self) -> str:
        return f"WuLi-Dominating/{self.scheduler}/{self.encoding}/{self.policy}"


def run_case(c: Case, *, max_ms: int = 3_000_000) -> Dict[str, object]:
    """Tek hücre: koş, doğrula, kestirimle ve referansla karşılaştır.

    Doğrulama `validate.validate` iledir, yani ihlal listesi gerçek
    doğrulayıcıdan gelir; bu dosya kendi geçerlilik ölçütünü YAZMAZ.
    """
    from ccvc.bb import validate as _validate
    from ccvc.bb.sweep import validate_run

    edges, weights = connected_udg(c.n, c.radius, c.seed)
    adj = adjacency(edges, list(weights))
    keys = keys_of(adj, weights)
    k = c.k if c.k is not None else max(len(a) for a in adj.values())
    p = WuLiParams(encoding=c.encoding, policy=c.policy, bloom_bytes=c.bloom_bytes,
                   chunk_words=c.chunk_words, chunk_burst=c.chunk_burst,
                   two_sided=c.two_sided)
    r = run_wuli(edges, weights, k, scheduler=c.scheduler, params=p, max_ms=max_ms)
    g = _validate.make_graph(edges, k, weights)
    rep = validate_run(g, r)
    ref = reference_backbone(adj, keys, p.k_max)["backbone"]
    degs = [len(a) for a in adj.values()]
    return {
        "variant": c.name,
        "n": c.n,
        "m": len(edges),
        "avg_degree": round(2 * len(edges) / c.n, 2),
        "max_degree": max(degs),
        "k": k,
        "seed": c.seed,
        "encoding": c.encoding,
        "policy": c.policy,
        "scheduler": c.scheduler,
        "converged": r.converged,
        "max_payload": r.max_payload,
        "bytes_tx": r.bytes_tx,
        "tx": r.tx,
        "rx": r.rx,
        "slots": r.slots,
        "t_conv_ms": r.t_conv_ms,
        "backbone": len(r.backbone),
        "backbone_ref": len(ref),
        "backbone_divergence": len(r.backbone_divergence),
        "cover": len(r.cover),
        "weight": r.total_weight,
        "partial_decisions": r.partial_decisions,
        "frames_at_decision": r.frames_at_decision,
        "chunk_cycle": r.chunk_cycle,
        "valid": rep.valid,
        "violations": sorted({v.kind for v in rep.violations}),
    }


def chunk_divergence_sweep(chunk_words: Sequence[int] = (1, 2, 4, 8),
                           shapes: Sequence[Tuple[int, float]] = ((20, 0.38),),
                           seeds: Sequence[int] = (0, 1, 2), *,
                           max_ms: int = 3_000_000) -> List[Dict[str, object]]:
    """Parçalı görüşün KARAR DEĞİŞTİRME ORANI (ekip lideri bunu istedi).

    Her hücrede gerçek koşum yapılır ve düğüm başına iki şey sayılır:
      * kararını EKSİK görüşle veren düğüm oranı,
      * işareti tam listeninkinden FARKLI çıkan düğüm oranı.
    Fark yönü de raporlanır: parçalının belirsizliği yanlış negatif olduğundan
    beklenen yön FAZLA işaretlemedir; eksik işaretleme çıkarsa bu bir HATADIR.
    """
    from ccvc.bb import validate as _validate
    from ccvc.bb.sweep import validate_run

    rows: List[Dict[str, object]] = []
    for cw in chunk_words:
        for n, radius in shapes:
            for seed in seeds:
                edges, weights = connected_udg(n, radius, seed)
                adj = adjacency(edges, list(weights))
                k = max(len(a) for a in adj.values())
                r = run_wuli(edges, weights, k, max_ms=max_ms,
                             params=WuLiParams(encoding=ENC_CHUNK, chunk_words=cw))
                ref = reference_backbone(adj, keys_of(adj, weights))["marked"]
                extra = set(r.marked) - ref
                missing = ref - set(r.marked)
                g = _validate.make_graph(edges, k, weights)
                rows.append({
                    "chunk_words": cw,
                    "n": n,
                    "seed": seed,
                    "max_degree": max(len(a) for a in adj.values()),
                    "chunk_cycle": r.chunk_cycle,
                    "frames_at_decision": r.frames_at_decision,
                    "partial_rate": round(r.partial_decisions / n, 3),
                    "mark_divergence_rate": round(len(r.mark_divergence) / n, 3),
                    "over_marked": len(extra),
                    "under_marked": len(missing),
                    "max_payload": r.max_payload,
                    "bytes_tx": r.bytes_tx,
                    "tx": r.tx,
                    "valid": validate_run(g, r).valid,
                })
    return rows


def default_cases(seeds: Sequence[int] = (0, 1, 2)) -> List[Case]:
    """Üç kodlama × iki zamanlayıcı, artan yoğunlukta üç çizge."""
    shapes = [(20, 0.38), (30, 0.30), (40, 0.28)]
    out: List[Case] = []
    for n, r in shapes:
        for enc in ENCODINGS:
            for sch in ("sync", "async"):
                for s in seeds:
                    out.append(Case(n=n, radius=r, seed=s, encoding=enc,
                                    scheduler=sch))
    return out


def experiment(cases: Optional[Sequence[Case]] = None, *, max_ms: int = 3_000_000
               ) -> List[Dict[str, object]]:
    return [run_case(c, max_ms=max_ms) for c in (cases or default_cases())]


def to_csv(rows: Sequence[Dict[str, object]]) -> str:
    if not rows:
        return ""
    cols = list(rows[0].keys())
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")).replace(",", ";") for c in cols))
    return "\n".join(lines) + "\n"


def _print_size_table() -> None:
    limit = wire.MAX_PAYLOAD
    print(f"# şekil 6: çerçeve boyu / derece  (sınır {limit} B)")
    print(f"{'derece':>7} {'full':>7} {'bloom':>7} {'chunked':>8}  parça")
    for d in (2, 5, 10, 20, 36, 60, 110, 117, 118, 130):
        row = [frame_bytes(e, d) for e in ENCODINGS]
        flag = "  <-- 250 B AŞILDI" if row[0] > limit else ""
        print(f"{d:>7} {row[0]:>7} {row[1]:>7} {row[2]:>8}  "
              f"{chunk_count(d, 8):>2}{flag}")
    print(f"# tam listenin sığdığı en büyük derece: {max_degree_within_limit(ENC_FULL)}")


def _print_fpr_table() -> None:
    print("\n# Bloom yanlış pozitif oranı (64 B, k=8): formül vs ölçüm")
    print(f"{'derece':>7} {'formül':>10} {'tek taraflı':>12} {'iki taraflı':>12}")
    for d in (10, 20, 36, 60, 110):
        print(f"{d:>7} {bloom_fpr_formula(d):>10.2e} "
              f"{measure_bloom_fpr(d, trials=80, probes=300):>12.2e} "
              f"{measure_bloom_fpr(d, trials=80, probes=300, two_sided=True):>12.2e}")


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description="WuLi-Dominating mesaj boyutu deneyi")
    ap.add_argument("--csv", help="satırları bu dosyaya yaz")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--sizes-only", action="store_true",
                    help="yalnız boyut ve yanlış pozitif tablolarını yazdır")
    a = ap.parse_args(argv)

    _print_size_table()
    _print_fpr_table()
    if a.sizes_only:
        return 0
    rows = experiment(default_cases(tuple(range(a.seeds))))
    print("\n# koşumlar")
    keys = ("variant", "n", "avg_degree", "max_payload", "bytes_tx", "tx",
            "backbone", "backbone_ref", "weight", "valid")
    print(" ".join(f"{k:>16}" for k in keys))
    for r in rows:
        print(" ".join(f"{str(r[k]):>16}" for k in keys))
    if a.csv:
        with open(a.csv, "w") as fh:
            fh.write(to_csv(rows))
        print(f"\nyazıldı: {a.csv} ({len(rows)} satır)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# ==========================================================================
# SWEEP KAYDI (ccvc/bb/sweep.py sözleşmesi; şema orada donmuştur)
# ==========================================================================
#: HELLO'nun sözcük dizisi WuLi-Dominating'de MIS listesi değil komşu özetidir, dolayısıyla
#: `RunRequest.mis_nbrs_max` (varsayılan 32) bu kolu boğardı: 36 komşulu bir
#: düğümün tam listesi 37 sözcüktür ve üretici kapısı `ValueError` atardı.
#: Kapı bu yüzden yükseltilir; TEK gerçek sınır `wire`ın 250 baytıdır ve o
#: yerinde durur. İstek daha büyük bir değer verirse ona uyulur.
_SUMMARY_WORD_CAP = 4096


def _spec_run(encoding: str, *, chunk_burst: bool = False, policy: str = POL_SAFE):
    """`sweep.RunRequest` -> `WuLiRun`. `BbcvcRun` alt sınıfı olduğu için
    zorunlu on beş alanın hepsi zaten yerindedir; uyarlayıcı gerekmez."""

    def run(req):
        from ccvc.bb.sweep import with_overrides

        p = WuLiParams(
            encoding=encoding, policy=policy, chunk_burst=chunk_burst,
            mis_nbrs_max=max(int(getattr(req, "mis_nbrs_max", 0)), _SUMMARY_WORD_CAP),
        )
        return run_wuli(list(req.edges), dict(req.weights), req.k,
                        scheduler=req.scheduler, max_ms=req.max_ms,
                        loss=req.loss, seed=req.seed,
                        params=with_overrides(p, req))

    return run


def _build_specs():
    from ccvc.bb.sweep import VariantSpec

    return (
        VariantSpec("WuLi-Dominating-Exact", "bb", "wuli_full", "local",
                    _spec_run(ENC_FULL)),
        VariantSpec("WuLi-Dominating-Bloom", "bb", "wuli_bloom", "local",
                    _spec_run(ENC_BLOOM)),
        VariantSpec("WuLi-Dominating-Chunked", "bb", "wuli_frag", "local",
                    _spec_run(ENC_CHUNK, chunk_burst=True)),
    )


#: Üç ayrı KOL, üç ayrı `phase1` değeri. Gerekçe (bb-figures'ın okuması doğru):
#: tam liste / Bloom / parçalı AYNI Faz 1 değildir, üç ayrı kodlamadır. Ayrı
#: `phase1` değerleri hem birbirleriyle hem BB-CVC'nin `phase1="mis"`iyle
#: eşleşmiş çift kurar; aynı değeri paylaşsalardı iki kol aynı eksende
#: ayrışmadan eşleşir ve kıyas anlamını yitirirdi.
#:
#: İLKE: üçü de `safe` (brief §5/1). `naive` BİLEREK KAYDEDİLMEMİŞTİR: güvenli
#: olmadığı ÖLÇÜLMÜŞTÜR (4 baytlık filtreyle G[C] kopuyor, bkz. B3) ve bilerek
#: geçersiz bir kolu kıyas matrisine sokmak, matrisin okuyucusuna o kolun da
#: aday olduğunu söylerdi. `naive` kendi deneyinde, kendi tablosunda durur.
#:
#: PARÇALI KOL TOPLUCA gönderir (`chunk_burst=True`): brief §5/2'nin "tx artar"
#: tasarımı budur ve şekildeki tx paneli ancak böyle doğru okunur. Sıra ile
#: gönderen sürüm (tx artmaz, gecikme öder) ölçülmüştür ve istenirse ayrı bir
#: `phase1="wuli_frag_rr"` kolu olarak eklenir.
BB_VARIANTS = _build_specs()
