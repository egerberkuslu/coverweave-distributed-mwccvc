#!/usr/bin/env python3
"""BB-CVC bootstrap katmanı: düğüm hiçbir şeyi hazır bulmaz.

Brief: plan/MWCCVC_DAGITIK_TASARIM_BRIEF.md §3.1, §3.5, §3.6
Anlatım: plan/BB-CVC_Algoritma_Ornekli_Anlatim.tex, "Sıfırdan inşa" bölümü
Sözleşme: ccvc/bb/api.py (DEĞİŞTİRİLMEZ)

İLKE (api.py I1/I2). Düğüme çizge verilmez. Elinde yalnız kendi MAC'i, ağırlığı
ve dört platform çağrısı vardır: send_broadcast, send_unicast, on_frame, now_ms.
Komşuluk, derece, kimlik ve anahtar bu dosyada HESAPLANIR; hiçbiri parametre
olarak alınmaz. `BootstrapNode.__init__` imzasında çizgeye dair tek bir alan
bile bulunmamaktadır ve bu, test_bootstrap.py içinde assert edilmektedir.

KATMANIN ÜRETTİĞİ TEK ÇIKTI: (deg, key). Bundan sonraki bütün fazlar (MIS,
connector, örtü genişletme, sahiplik) donmuş anahtar üzerine kurulur; anahtar
yanlış donarsa o noktadan sonraki her karar tutarsızlaşır. Kararlılık kapısı
bu yüzden vardır.

GEÇİCİ BAĞIMSIZLIK NOTU. `wire.py`, `sched.py` ve `simnet.py` başka bir ajan
tarafından yazılmaktadır. Bu dosya onlara bağlanmaz; ihtiyaç duyduğu iki şeyi
(serileştirme ve bir koşum ortamı) aşağıda açıkça işaretli iki bölümde kendi
içinde tutar. Onlar geldiğinde yapılacak iş, bu iki bölümü silip yerine
wire/simnet çağrılarını koymaktır; algoritma gövdesine dokunulmaz.
"""
from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

try:
    from ccvc.bb import wire
    from ccvc.bb.api import (
        MAX_PAYLOAD,
        Counters,
        MsgType,
        Neighbor,
        NodeCore,
        NodeSnapshot,
        PayloadTooLarge,
        Platform,
        Role,
        from_fp,
        key_of,
        to_fp,
    )
except ImportError:  # doğrudan çalıştırma
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    from ccvc.bb import wire
    from ccvc.bb.api import (
        MAX_PAYLOAD,
        Counters,
        MsgType,
        Neighbor,
        NodeCore,
        NodeSnapshot,
        PayloadTooLarge,
        Platform,
        Role,
        from_fp,
        key_of,
        to_fp,
    )


# ==========================================================================
# 1. Kimlik: id = hash16(MAC)   (brief §3.5 madde 1)
# ==========================================================================
_FNV32_OFFSET = 0x811C9DC5
_FNV32_PRIME = 0x01000193
MAC_BYTES = 6
MAC_MASK = (1 << (8 * MAC_BYTES)) - 1


def hash16(mac: int, salt: int = 0) -> int:
    """MAC'in 16 bitlik kimliği. FNV-1a, 32 bitten 16 bite katlanır.

    id 0 ayrılmıştır (geçersiz/bilinmiyor), çakışırsa 1'e taşınır. Tuz,
    kimlik çakışması görüldüğünde yeniden türetme içindir (§3.5 madde 1).
    """
    h = _FNV32_OFFSET
    for shift in range(0, 8 * MAC_BYTES, 8):
        h = ((h ^ ((mac >> shift) & 0xFF)) * _FNV32_PRIME) & 0xFFFFFFFF
    for shift in (0, 8, 16, 24):
        h = ((h ^ ((salt >> shift) & 0xFF)) * _FNV32_PRIME) & 0xFFFFFFFF
    folded = ((h >> 16) ^ h) & 0xFFFF
    return folded if folded else 1


def xorshift32(state: int) -> int:
    """Brief §3.5 madde 7: jitter ve tavlama için tek RNG. Float yok."""
    x = state & 0xFFFFFFFF
    if x == 0:
        x = 0x9E3779B9
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    return x & 0xFFFFFFFF


def epoch_newer(a: int, b: int) -> bool:
    """1 baytlık epoch için sarmalamaya dayanıklı 'daha yeni' (RFC 1982 kipi).

    Düz `a > b` karşılaştırması 255 -> 0 geçişinde ağı kilitler; epoch alanı
    brief §3.5 madde 6 gereği 1 bayttır, dolayısıyla sarmalama gerçektir.
    """
    d = (a - b) & 0xFF
    return d != 0 and d < 128


# ==========================================================================
# 2. Serileştirme: ccvc/bb/wire.py TEK kaynaktır.
#    Burada bir zamanlar ikinci bir HELLO kodlayıcı vardı; iki kodlayıcı
#    kaçınılmaz olarak birbirinden uzaklaşır ve iki test takımı da bunu
#    göremez, çünkü her biri kendi kodlayıcısını sınar. Silindi.
#    wire.py tipi payload[0]'a koyar; ağ katmanı böylece yükü çözmeden
#    tip başına muhasebe yapabilir ve simnet buna dayanır.
#
#    ÖLÇEK SORUMLULUĞU. wire.py yalnız 250 B sınırını dayatır (I3); G8'in
#    "en fazla 5 mis komşusu" kuralı bir ÇİZGE olgusudur, telin işi değildir
#    ve wire orada bilerek susar. Dolayısıyla sınırı ÜRETEN dayatır: aşağıdaki
#    `_hello_payload` hem G8'i hem de bir baytlık `deg` alanını denetler.
# ==========================================================================


# ==========================================================================
# 3. Parametreler (brief §3.5 madde 2/4/5, §3.6 kanal zamanı kuralı)
# ==========================================================================
def t_hello_lower_bound_ms(
    n2: int, t_frame_ms: float = 0.7, rho_max: float = 0.1
) -> int:
    """Brief §3.6: T_hello >= N2 * t_f / rho_max.

    N2 iki-atlama komşu sayısıdır ve düğüm bunu bilemez; bu yüzden değer
    KOŞUM BETİĞİ tarafından topolojiden hesaplanıp parametre olarak verilir.
    Düğüm kodu bu fonksiyonu çağırmaz, yalnız verilen T_hello'yu kullanır.
    """
    return int(-(-(n2 * t_frame_ms / rho_max) // 1))


@dataclass
class BootstrapParams:
    """Varsayılanların gerekçesi RAPOR'da; hepsi parametriktir."""

    t_hello_ms: int = 200
    stale_periods: int = 3  # 3*T_hello yenilenmeyen giriş düşer
    stab_periods: int = 3  # T_stab = 3*T_hello
    rssi_open_dbm: float = -75.0  # brief §3.5 madde 4
    rssi_close_dbm: float = -85.0
    rssi_ema_alpha: float = 0.5
    rssi_impossible_dbm: float = 0.0
    """At or above this a reading is NOT A MEASUREMENT.

    A radio cannot receive more power than was transmitted, so a positive dBm
    reading is a wrapped signed byte rather than a strong signal.

    MEASURED on n15_m90 seed 1: the planner's embedding placed two stations
    0.04 m apart, and each read the other's RSSI as values spread over the
    WHOLE int8 range, -128 to +127, while every one of their thirteen other
    peers reported a single constant value. The wrapped samples fell below the
    close threshold about as often as they rose above the open one, so the
    hysteretic gate toggled that one link roughly every 1.2 s. Each toggle
    changed the node's bidirectional set, which bumps the epoch and resets the
    whole network to phase 0: 148 local toggles became 2057 network-wide
    resets in 240 s. MIS-Connector-Backbone still finished because its phase 1
    is short, but GHS-MST-Backbone and Anneal-Local never got an uninterrupted
    window and returned NO COVER AT ALL.
    """
    link_max_attempts: int = 3  # brief §3.4: R_max
    link_rounds_max: int = 4
    """G4 (note to Amendment 15): handshake rounds a heard, unverified link is
    waited for, at the freeze gate and at DONE alike, before it is treated as
    one-way for the epoch. A round is `link_max_attempts` LINKs; the next round
    starts `link_retry_after_periods` later on the next HELLO. The freeze gate
    used to wait only for a round in progress, so a link that failed one round
    was verified after the freeze and its success restarted the epoch; at
    n = 100 some link always did (restart loop, Amendment 15)."""
    link_retry_after_periods: int = 12
    """How long an exhausted handshake stays exhausted, in HELLO periods.

    The one-shot rule exists to stop a unicast flood and it is kept: a giving
    -up entry does NOT retry per HELLO. But making the failure PERMANENT relies
    on a recovery path that cannot happen. The documented path is the entry
    dropping through soft state and re-opening, and the entry only drops when
    the neighbour goes silent; a neighbour that keeps sending HELLOs keeps the
    entry fresh, so `link_failed` never clears and that edge is lost for the
    rest of the run.

    MEASURED in the event simulator at five per cent loss on the n=20 graph the
    stations saw: node 16's entry for node 9 ended `link_failed=True` after
    three attempts while node 9 still considered the edge up. The edge was
    therefore ASYMMETRIC, node 16 could not answer node 9's TEST, node 9 held
    that question for the whole run and the fragment never reported: the run
    returned no cover at all.

    A cooldown keeps the flood bounded (one handshake round per cooldown per
    entry) and removes the deadlock.
    """
    link_backoff_ms: int = 100  # üstel geri çekilme tabanı
    mis_nbrs_max: int = 5
    """HELLO'da taşınacak en çok MIS komşusu. Varsayılan 5, brief G8.

    G8 BİR BİRİM DİSK ÇİZGESİ TEOREMİDİR ve kıyas kümesinde GEÇERLİ DEĞİLDİR:
    Dagdeviren veri kümesinde ölçülen en büyük bağımsız komşu sayısı n=25'te 6,
    n=200'de 17'dir ve n=200'de BÜTÜN düğümler 5'i aşmaktadır. Sabit 5 dayatmak
    kıyas kümesinde her düğümü reddederdi. Bu yüzden sınır parametredir: UDG
    koşumlarında 5, UDG dışında topolojinin gerektirdiği değer.

    Sonuç, brief §5'in "HELLO sabit boyutludur, yoğunluktan bağımsızdır"
    savının KAPSAM KOŞULUDUR: 17 mis komşusunda HELLO 13+2*17=47 bayttır ve
    yoğunlukla büyür. 250 B sınırına ancak 118 girişte varılır, yani hiçbir şey
    kırılmaz, ama "250 B'ye sığar" ile "sabit boyutlu" aynı sav değildir.
    """

    nbr_table_max: int = 64
    """Statik komşu tablosu boyutu (brief §3.6: 64 giriş × 24 B, malloc yok).

    ÖLÇÜLDÜ (ekip lideri, MWCCVC Dagdeviren veri kümesinin 54 örnek grubunun
    tamamı, n=10..1000): veri kümesindeki EN BÜYÜK derece 36'dır ve hiçbir
    örnekte 64'ü aşan tek bir düğüm yoktur. En kötü durumlar n=150/m=1500'de
    35 ve n=500/m=5000'de 36'dır. Pay: 28.

    Yani sınır koşacağımız hiçbir örnekte bağlayıcı değildir. Bu, "sorun
    beklemiyoruz" değil, "bütün kıyas kümesinde en kötü durumu ölçtük ve 64'e
    karşı 36 çıktı" savıdır; ikincisi ilkinden çok daha güçlüdür. Tel
    üzerindeki bir baytlık `deg` alanının 255 sınırı daha da uzaktır.

    Aşılırsa sonuç SESSİZCE bozulmaz: `table_overflow` sayacı artar ve
    `validate_bootstrap` koşumu geçersiz sayar.
    """
    hello_jitter_ms: int = 0  # xorshift32 ile; 0 = tam deterministik
    gate_waits_for_pending_links: bool = True
    adaptive_stale: bool = True
    """Repair F9 (R1, Amendment 6): one stale window per neighbour.

    Every window starts at `stale_periods`. When a neighbour whose record
    expired is heard again, the expiry was a false suspicion and that
    neighbour's window doubles, up to `stale_periods_cap`. MEASURED without it
    under Gilbert-Elliott loss (10 per cent, mean burst 4 frames): a burst of
    three lost HELLOs expired a record, the view change restarted the whole
    network about every 1.8 s, and 67 of 72 development runs hit the time
    limit. Off, the protocol is exactly the fixed-window one.
    """
    stale_periods_cap: int = 48

    @property
    def t_stale_ms(self) -> int:
        return self.stale_periods * self.t_hello_ms

    @property
    def t_stab_ms(self) -> int:
        return self.stab_periods * self.t_hello_ms

    @property
    def link_retry_after_ms(self) -> int:
        return self.link_retry_after_periods * self.t_hello_ms


# ==========================================================================
# 4. Komşu kaydı — api.Neighbor'ın üstüne bootstrap'a özgü alanlar
# ==========================================================================
@dataclass
class BootNeighbor(Neighbor):
    """api.Neighbor + MAC + RSSI kapısı + LINK el sıkışma durumu.

    api.Neighbor MAC taşımamaktadır, ancak brief §3.5 madde 2 komşu tablosunda
    MAC'i açıkça istemektedir (ESP-NOW unicast'i MAC ile adresler ve kimlik
    çakışması MAC karşılaştırmasıyla çözülür). api.py değiştirilemediğinden
    alan burada eklenmiştir; isinstance(x, Neighbor) hâlâ doğrudur.
    """

    mac: int = 0
    link_up: bool = False  # RSSI histerezis kapısı
    rssi_untrusted: bool = False  # bkz. BootstrapParams.rssi_impossible_dbm
    awaiting_ack: bool = False
    last_ack_seq: Optional[int] = None  # bu seq için ACK zaten gönderildi mi
    link_failed: bool = False  # tek seferlik el sıkışma tükendi
    link_retry_ms: int = 0     # tükenen el sıkışmanın yeniden denenebileceği an
    link_attempts: int = 0
    link_next_ms: int = 0
    link_seq: int = 0
    link_rounds: int = 0    # G4: failed handshake rounds in this epoch

    @property
    def is_edge(self) -> bool:
        """Kenar YALNIZ çift yönlü doğrulanmış ve RSSI kapısı açık ise vardır."""
        return self.bidir and self.link_up


# ==========================================================================
# 5. Düğüm: bootstrap durum makinesi
# ==========================================================================
class ClockBaselineMissing(RuntimeError):
    """Bir alt sınıf saat tabanı sözleşmesini çiğnedi.

    Kapı, `_establish_clock_baseline` çağırdıktan sonra tabanın kurulmuş
    olmasına güvenir. Uzantı noktasını ezip kurmayan bir sınıf sessizce
    yanlış çalışmaz, burada ADIYLA durur.
    """


class RunInvalid(RuntimeError):
    """Koşum raporlanamaz: sonuç sessizce yanlış olabilir.

    Kırpılmış bir komşu tablosundan donan derece anahtarı zehirler, anahtar
    MIS sıralamasını belirler, MIS de omurgayı; dolayısıyla TEK bir taşma
    bütün bileşenin cevabını değiştirir ve bunu doğru bir cevaptan ayırt
    eden hiçbir işaret kalmaz. Sessizce yanlış bir sonuç raporlamaktansa
    raporlamayı reddetmek yeğdir.
    """


def validate_bootstrap(nodes) -> None:
    """Koşum betiği SONUÇ RAPORLAMADAN ÖNCE bunu çağırmalıdır.

    `nodes` düğüm nesnelerinin herhangi bir yinelenebiliridir. Güvenilmez tek
    bir düğüm varsa `RunInvalid` atar; sessiz bir günlük alanı değil, koşumu
    durduran bir hatadır.
    """
    bad = []
    for n in nodes:
        for reason in n.invalid_reasons:
            bad.append(f"id={n.nid}: {reason}")
    if bad:
        raise RunInvalid(
            f"{len(bad)} düğüm güvenilmez, koşum raporlanamaz:\n  " + "\n  ".join(bad)
        )


def bootstrap_report(nodes) -> Dict[str, int]:
    """Koşum betiğinin günlüğe yazacağı özet. `valid` alanı kapıdır."""
    ns = list(nodes)
    return {
        "nodes": len(ns),
        "frozen": sum(1 for n in ns if n.key is not None),
        "table_overflow": sum(n.table_overflow for n in ns),
        "epoch_bumps": sum(n.epoch_bumps for n in ns),
        "id_rederivations": sum(n.id_rederivations for n in ns),
        "valid": int(not any(n.invalid_reasons for n in ns)),
    }


class BootstrapNode(NodeCore):
    """Faz 0'ı koşan düğüm. Çizgeyi göremez; (deg, key) üretir ve dondurur.

    İMZA DİKKAT: komşu listesi, derece, düğüm sayısı, kimlik tablosu YOKTUR.
    Yalnız kendi MAC'i, kendi ağırlığı, kapasitesi ve platformu vardır.
    """

    def __init__(
        self,
        weight: int,
        platform: Platform,
        params: Optional[BootstrapParams] = None,
        capacity_k: int = 2,
    ) -> None:
        # AĞIRLIK GERÇEK SAYI OLABİLİR. Eski kapı "tamsayı olmalı" diyordu ve
        # YANLIŞ DEĞİŞMEZİ dayatıyordu: brief §3.6 sabit noktalı ARİTMETİK
        # ister (ESP32-C3'te FPU yok), tamsayı GİRDİ değil. 26.2096 bir
        # cihazda 16.16 olarak saklanır ve `to_fp` tam da bunu yapar.
        # Bedeli ölçüldü: Dagdeviren örneklerinin 310/310'u kesirli ağırlık
        # taşıyor, yani eski kapı BÜTÜN kıyas kümesini koşulamaz kılıyordu.
        # Korunan gerçek değişmez aşağıda: anahtar tamsayıdır ve kalır.
        w = float(weight)
        if w != w or w in (float("inf"), float("-inf")):
            raise TypeError(f"ağırlık sonlu olmalı, {weight!r} geldi")
        if not -32768.0 <= w <= 32767.0:
            raise ValueError(f"ağırlık 16.16 sabit noktaya sığmıyor: {weight!r}")
        # Kendi MAC'imizi bile kimse vermez: telsizden okunur (esp_wifi_get_mac
        # karşılığı). id ondan TÜRETİLİR; hiçbir yerden hazır gelmez.
        self.mac = int(platform.mac) & MAC_MASK
        self.w = int(w) if float(w).is_integer() else w
        self.w_fp = to_fp(w)  # kanonik sabit noktalı ağırlık
        self.k = int(capacity_k)
        self.plat = platform
        self.p = params or BootstrapParams()

        self.salt = 0
        self.nid = hash16(self.mac, self.salt)
        self.epoch = 0
        self.phase = 0
        self.role = Role.OUT
        self.load = 0
        #: HELLO's open-barrier flag (repair F2); the BB-CVC layer sets it.
        self.barrier_open = False
        #: HELLO's infeasible flag (repair F12); the BB-CVC layer sets it.
        self.infeasible = False
        #: HELLO's confirm request and echo block (repair F15); the BB-CVC layer sets them.
        self.hello_confirm = False
        self.hello_echo: Tuple[Tuple[int, int, int], ...] = ()

        # bootstrap'ın ürettiği iki değer; ikisi de başta BİLİNMİYOR
        self.deg: Optional[int] = None
        self.key: Optional[Tuple[int, int]] = None
        self.frozen_at_ms: Optional[int] = None
        self._frozen_bidir: Optional[frozenset] = None

        self.nbrs: Dict[int, BootNeighbor] = {}
        # SAAT TABANI. Hiçbir zaman alanı 0 ile BAŞLATILMAZ; hepsi ilk
        # gözlemlenen `now_ms()`'ten kurulur. Sıfır başlatmak yalnız saati
        # sıfırdan başlayan bir simülatörde doğrudur: duvar saatinde
        # `now - 0` ilk tıkta ~1.7e12 ms olur, kararlılık kapısı anında
        # açılır ve HER DÜĞÜM deg=0 ile anahtarını dondurur; yani kapı tam
        # olarak var olma nedeninin tersini yapar. Sanal saat altında
        # görünmez, gerçek saat altında ilk tıkta patlar.
        self._t0_ms: Optional[int] = None
        self.stable_since_ms: Optional[int] = None
        self._last_hello_ms: Optional[int] = None
        self._hello_due_ms: Optional[int] = None
        self._rxq: List[Tuple[int, Optional[float], bytes]] = []
        self._seq = 0
        self._rng = xorshift32(self.mac & 0xFFFFFFFF)
        self.id_rederivations = 0
        self.epoch_bumps = 0
        #: F9. Neighbour -> its grown stale window in periods (absent = the
        #: default), and the neighbours whose record expired and that have not
        #: been heard since. Both describe the LINK, so an epoch restart keeps
        #: them.
        self._stale_p: Dict[int, int] = {}
        self._expired: Set[int] = set()
        #: Epoch increments this node has gone through, unwrapped (the epoch
        #: byte wraps at 256). Bumped or adopted alike; a run's restart count
        #: is the largest value over its nodes.
        self.epoch_advance = 0
        #: G2: LINK asks heard before the asker's HELLO, id -> (mac, seq).
        self._link_asks: Dict[int, Tuple[int, int]] = {}
        self.rssi_implausible = 0
        self._diff_since_ms: Optional[int] = None
        """Peers whose RSSI channel was condemned as unreadable.

        NON-ZERO MEANS THE GATE IS NOT GOVERNING THOSE LINKS. They are held
        open and staleness alone decides, exactly as on a platform that
        reports no RSSI. The run is still valid; the number belongs in the
        report because the topology it produces is not the one the RSSI
        thresholds describe.
        """
        self.table_overflow = 0
        """Komşu tablosu dolduğu için kaç giriş düşürüldü.

        SIFIR DEĞİLSE BU DÜĞÜMÜN `deg`i VE ANAHTARI GÜVENİLMEZDİR: düşen komşu
        derece sayımına girmez, dolayısıyla anahtar yanlış donar ve bunu
        doğru bir donmadan ayırt eden başka hiçbir işaret yoktur. Koşum
        betiği bu sayacı raporlamalıdır; sessiz kalırsa `nbr_table_max`
        topolojiye küçük geldiğinde sonuçlar sessizce bozulur.
        """

    # ---------------------------------------------------------------- API
    # ------------------------------------------------------------ saat tabanı
    def _establish_clock_baseline(self, now: int) -> None:
        """Saat tabanını ilk gözlemlenen `now_ms()`ten kur. Yeniden çağrılabilir.

        Düğüm saatin nereden başladığını bilmez: simülatörde 0, ESP32'de
        açılıştan, mininet-wifi'de duvar saatinden. İlk gözlem taban sayılır.
        Alt sınıflar bunu ezip kendi zaman alanlarını da kurabilir.
        """
        if self._t0_ms is None:
            self._t0_ms = now
        if self.stable_since_ms is None:
            self.stable_since_ms = now

    def on_frame(self, src: int, rssi: Optional[float], payload: bytes) -> None:
        """Donanım geri çağırımı: yalnız kuyruğa yazar (.tex bootstrap algoritması).

        `src` GÖNDERENİN MAC'İDİR (48 bit tamsayı), düğüm kimliği değil: MAC
        çerçeve başlığında gelir ve radyodan/soketten okunur. Kimlik çakışması
        bu değerle saptanır; yük yalnız gönderenin İDDİA ETTİĞİ id'yi taşır.

        Gerçek ESP32'de bu kesme bağlamında koşar, içinde hesap yapılmaz.
        """
        self._rxq.append((src, rssi, bytes(payload)))

    def on_timer(self, name: str = "tick") -> None:
        now = self.plat.now_ms()
        self._establish_clock_baseline(now)
        before = self._bidir_ids()
        self._drain_rx(now)
        self._expire(now)
        self._retry_links(now)
        self._maybe_hello(now)
        after = self._bidir_ids()
        if after != before:
            # Tek yer: çift yönlü komşu kümesi değiştiyse kararlılık penceresi
            # baştan başlar. "Tablo değişmedi" tanımı budur.
            self.stable_since_ms = now
        self._gate(now, after)

    def snapshot(self) -> NodeSnapshot:
        return NodeSnapshot(
            nid=self.nid,
            role=self.role,
            phase=self.phase,
            key=None if self.key is None else self.key[0],
            deg=0 if self.deg is None else self.deg,
            owned=(),
            forced_load=0,
            counters=getattr(self.plat, "counters", Counters()),
            epoch=self.epoch,
        )

    @property
    def done(self) -> bool:
        """Bootstrap yerel sükûneti: anahtar donmuş ve bekleyen el sıkışma yok."""
        return self.phase >= 1 and not self._pending_links()

    # ------------------------------------------------------- gözlem/ölçüm
    @property
    def invalid_reasons(self) -> Tuple[str, ...]:
        """Bu düğümün sonucunu güvenilmez kılan nedenler. Boşsa güvenilir.

        Şu an tek neden tablo taşmasıdır: düşen komşu derece sayımına
        girmediği için anahtar yanlış donar ve bunu doğru bir donmadan ayıran
        başka hiçbir işaret yoktur.
        """
        out = []
        if self.table_overflow:
            out.append(
                f"komşu tablosu {self.table_overflow} kez taştı "
                f"(nbr_table_max={self.p.nbr_table_max}); deg ve key kırpılmış olabilir"
            )
        return tuple(out)

    @property
    def key_fp(self) -> Optional[int]:
        return None if self.key is None else self.key[0]

    def key_value(self) -> Optional[float]:
        """YALNIZ rapor/şekil için. Karar yolunda kullanılmaz."""
        return None if self.key is None else from_fp(self.key[0])

    def edges(self) -> frozenset:
        return self._bidir_ids()

    def candidate_deg(self) -> int:
        """Kapı OLMASAYDI şu an hangi dereceyle donardı. Yalnız test/teşhis."""
        return len(self._bidir_ids())

    def candidate_key_fp(self) -> int:
        """Kapı OLMASAYDI şu an hangi anahtarla donardı. Yalnız test/teşhis."""
        return key_of(self.w, self.candidate_deg(), self.nid)[0]

    # ----------------------------------------------------------- iç yapı
    def _bidir_ids(self) -> frozenset:
        return frozenset(n.nid for n in self.nbrs.values() if n.is_edge)

    def _pending_links(self) -> bool:
        """Is a handshake still owed before my view may freeze?

        A round in progress, or (G4, note to Amendment 15) a heard, link-up,
        unverified neighbour whose handshake has failed fewer than
        `link_rounds_max` rounds in this epoch: its next round comes on its next
        HELLO after the cooldown. The same bound as `BbcvcNode._unverified_pending`.
        """
        now = self.plat.now_ms()
        return any(
            (n.awaiting_ack and n.link_attempts < self.p.link_max_attempts)
            or (n.link_up and not n.bidir
                and n.link_rounds < self.p.link_rounds_max
                and now - n.last_ms <= self.stale_ms(n.nid))
            for n in self.nbrs.values()
        )

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    def _log(self, event: str, **fields) -> None:
        """Günlük. `log` dört ilkelden biridir, dolayısıyla SARMALANMAZ.

        Burada bir zamanlar `except Exception: pass` vardı ve `nid=` alanı
        SimNet'in `_record_log(nid, event, **fields)` imzasıyla çakışıyordu.
        Sonuç: her günlük satırı sessizce düşüyordu ve `retx` hiç sayılmıyordu.
        Kimin günlüklediğini platform zaten bilir; alanı göndermeyiz ve hatayı
        yutmayız. Sessiz yutma, teşhis edilmesi en zor arıza sınıfıdır.
        """
        self.plat.log(event, **fields)

    # ------------------------------------------------------------ gönderim
    def _bcast(self, payload: bytes) -> None:
        self.plat.send_broadcast(payload)

    def _ucast(self, nbr: BootNeighbor, payload: bytes) -> None:
        # MAC ile adreslenir: bir akran için elimizdeki TEK adres, çerçeve
        # başlığından okuduğumuz MAC'tir. id türetilmiş bir değerdir ve
        # çakışabilir; onunla adreslemek çakışma anında yanlış yönlendirirdi.
        self.plat.send_unicast(nbr.mac, payload)

    def _hello_payload(self, mis_nbrs: Tuple[int, ...] = ()) -> bytes:
        """HELLO'yu wire.py ile kodla ve ÜRETİCİ tarafında sınırları dayat.

        wire.py yalnız 250 B'yi dayatır; G8'in beş mis komşusu kuralını ve
        `deg`in bir bayta sığmasını burada denetleriz, çünkü bunlar telin
        değil algoritmanın değişmezleridir. Kırpma yok, hata var.
        """
        deg = 0 if self.deg is None else self.deg
        if self.key_fp is not None and not isinstance(self.key_fp, int):
            # wire.py `int(msg.key)` ile SESSİZCE zorlar: float 1.67 telde 1
            # olur ve doğru 16.16 değeri 109445'tir. Kayıp fark edilmez, bu
            # yüzden üretici tarafında açıkça reddediyoruz (brief §3.6).
            raise TypeError("key sabit noktalı tamsayı olmalıdır; float yasak")
        if len(mis_nbrs) > self.p.mis_nbrs_max:
            raise ValueError(
                f"mis_nbrs {len(mis_nbrs)} > {self.p.mis_nbrs_max} "
                f"(brief G8; UDG dışı koşumda params.mis_nbrs_max yükseltilmeli)"
            )
        if not 0 <= deg <= 0xFF:
            raise ValueError(f"deg {deg} bir bayta sığmıyor (tablo sınırı 64)")
        return wire.encode(
            wire.Hello(
                src=self.nid,
                key=self.key_fp,
                deg=deg,
                role=self.role,
                phase=self.phase,
                load=self.load,
                epoch=self.epoch,
                mis_nbrs=mis_nbrs,
                barrier_open=self.barrier_open,
                infeasible=self.infeasible,
                confirm=self.hello_confirm,
                echo=self.hello_echo,
            )
        )

    def _maybe_hello(self, now: int) -> None:
        if self._hello_due_ms is not None and now < self._hello_due_ms:
            return
        self._bcast(self._hello_payload())
        self._last_hello_ms = now
        jitter = 0
        if self.p.hello_jitter_ms:
            self._rng = xorshift32(self._rng)
            jitter = self._rng % (self.p.hello_jitter_ms + 1)
        self._hello_due_ms = now + self.p.t_hello_ms + jitter

    # ------------------------------------------------------------ alım
    def _drain_rx(self, now: int) -> None:
        q, self._rxq = self._rxq, []
        for src, rssi, payload in q:
            try:
                mt = wire.peek_type(payload)
            except (ValueError, IndexError, struct.error):
                continue
            if mt not in (MsgType.HELLO, MsgType.LINK, MsgType.LINK_ACK):
                continue  # sonraki fazların mesajları bootstrap'ı ilgilendirmez
            src_mac = int(src) & MAC_MASK
            msg = wire.decode(payload)
            if mt == MsgType.HELLO:
                self._on_hello(now, src_mac, rssi, msg)
            else:
                self._on_link(now, src_mac, msg)

    def _on_hello(
        self, now: int, src_mac: int, rssi: Optional[float], h: "wire.Hello"
    ) -> None:
        # (1) kimlik çakışması: yük bizim id'mizi İDDİA ediyor ama başlıktaki MAC
        #     bizimki değil -> iki cihaz aynı id'yi kullanıyor. Büyük MAC çekilir.
        if h.src == self.nid:
            if src_mac != self.mac:
                if self.mac > src_mac:
                    self._rederive_id(now, other_mac=src_mac)
                else:
                    self._log("id_collision_peer_rederives", peer_mac=src_mac)
            return  # kendi id'mizi tabloya yazmayız

        # (2) epoch: büyük epoch gören sıfırlar ve benimser (max-gossip)
        if epoch_newer(h.epoch, self.epoch):
            self.epoch_advance += (h.epoch - self.epoch) & 0xFF
            self.epoch = h.epoch
            self._reset_to_phase0(now, reason="epoch_adopt")

        # (3) RSSI histerezisi + soft-state tazeleme
        nbr = self.nbrs.get(h.src)
        fresh = nbr is None
        if fresh:
            if len(self.nbrs) >= self.p.nbr_table_max and not self._evict_weakest(
                h.src, rssi
            ):
                self.table_overflow += 1
                self._log(
                    "nbr_table_full_drop", peer=h.src, overflow=self.table_overflow
                )
                return
            # last_ms BAŞLANGIÇTA verilir: api.Neighbor'ın varsayılanı 0'dır ve
            # duvar saatinde 0 "sonsuz eski" demektir, yani giriş doğduğu anda
            # soft-state ile düşerdi. Bugün aşağıda zaten atanıyor, ama araya
            # bir `return` eklenmesi bunu sessizce bozardı.
            nbr = BootNeighbor(nid=h.src, mac=src_mac, last_ms=now)
            self.nbrs[h.src] = nbr
            if h.src in self._expired:
                # F9: it was not gone; its silence outlasted my window.
                self._expired.discard(h.src)
                cur = self._stale_p.get(h.src, self.p.stale_periods)
                self._stale_p[h.src] = max(cur, min(self.p.stale_periods_cap, 2 * cur))
                self._log("stale_window_grown", peer=h.src, periods=self._stale_p[h.src])
        elif nbr.mac != src_mac:
            # aynı id, iki farklı yabancı MAC: bizi ilgilendirmez, ama kaydı
            # kirletmesin diye yenisini yok sayıp olayı günlüğe yazarız.
            self._log("peer_id_ambiguous", peer=h.src, mac_a=nbr.mac, mac_b=src_mac)
            return

        was_up = nbr.link_up
        self._apply_rssi(nbr, rssi)
        ask = self._link_asks.pop(h.src, None)
        if ask is not None and ask[0] == src_mac and nbr.link_up:
            nbr.last_ack_seq = ask[1]   # G2: the deferred answer
            self.plat.send_unicast(
                src_mac, wire.encode(wire.Ctrl(MsgType.LINK_ACK, self.nid, ask[1])))
        nbr.last_ms = now
        nbr.key = h.key
        nbr.role = h.role
        nbr.phase = h.phase
        nbr.load = h.load
        nbr.mis_nbrs = h.mis_nbrs
        nbr.epoch = h.epoch
        if was_up and not nbr.link_up:
            nbr.bidir = False  # kapı kapandı: kenar yok
            nbr.awaiting_ack = False
            nbr.link_failed = False  # kapı yeniden açılırsa el sıkışma da yenidir
            self._log("rssi_gate_close", peer=h.src, ema=nbr.rssi_ema)
        elif (
            nbr.link_up
            and not nbr.bidir
            and not nbr.awaiting_ack
            and (not nbr.link_failed or now >= nbr.link_retry_ms)
        ):
            # TEK SEFERLİK (brief §3.5 madde 3): el sıkışma giriş başına bir kez
            # denenir ve HELLO başına yeniden denenmez, çünkü amaç sonsuz
            # unicast selini önlemektir. O amaç korunmaktadır: tükenen bir giriş
            # ancak `link_retry_after_ms` sonra bir tur daha alır.
            #
            # KALICI BAŞARISIZLIK bir kilitti. Belgelenen toparlanma yolu girişin
            # soft-state ile düşmesiydi, ama giriş yalnız komşu susunca düşer;
            # HELLO göndermeye devam eden bir komşu girişi taze tuttuğundan
            # `link_failed` hiç temizlenmez ve o kenar koşumun geri kalanında
            # kaybolur. Bkz. `BootstrapParams.link_retry_after_periods`.
            self._start_link(now, nbr)

    def _apply_rssi(self, nbr: BootNeighbor, rssi: Optional[float]) -> None:
        """Histerezis: -75 üstünde açılır, -85 altında kapanır; arası korunur."""
        if rssi is None:
            nbr.link_up = True  # RSSI vermeyen platform: kapı hep açık
            return
        if nbr.rssi_untrusted or rssi >= self.p.rssi_impossible_dbm:
            # ONE impossible sample condemns this peer's RSSI for good, and the
            # peer is then treated exactly like a platform that reports no RSSI.
            # Dropping only the positive samples would NOT be enough: the
            # wrapped values cover the whole byte, so the negative half is
            # indistinguishable from a genuinely weak signal and would still
            # close the gate on garbage. Condemning the peer is the only rule
            # that survives that, and it errs toward keeping a link that the
            # frames prove is there.
            if not nbr.rssi_untrusted:
                nbr.rssi_untrusted = True
                self.rssi_implausible += 1
                self._log("rssi_implausible", peer=nbr.nid, rssi=rssi)
            nbr.link_up = True
            return
        a = self.p.rssi_ema_alpha
        nbr.rssi_ema = (
            rssi if nbr.rssi_ema is None else a * rssi + (1.0 - a) * nbr.rssi_ema
        )
        if not nbr.link_up and nbr.rssi_ema > self.p.rssi_open_dbm:
            nbr.link_up = True
        elif nbr.link_up and nbr.rssi_ema < self.p.rssi_close_dbm:
            nbr.link_up = False

    def _evict_weakest(self, incoming: int, rssi: Optional[float]) -> bool:
        """Tablo doluysa en zayıf RSSI'li giriş düşer (brief §3.6 bellek)."""
        worst = min(
            self.nbrs.values(),
            key=lambda n: (n.rssi_ema if n.rssi_ema is not None else 0.0),
        )
        if rssi is not None and worst.rssi_ema is not None and rssi <= worst.rssi_ema:
            return False
        del self.nbrs[worst.nid]
        self.table_overflow += 1
        self._log(
            "nbr_evicted",
            peer=worst.nid,
            ema=worst.rssi_ema,
            for_peer=incoming,
            overflow=self.table_overflow,
        )
        return True

    # -------------------------------------------------- çift yön doğrulama
    def _start_link(self, now: int, nbr: BootNeighbor) -> None:
        nbr.link_seq = self._next_seq()
        nbr.awaiting_ack = True
        nbr.link_failed = False
        nbr.link_attempts = 1
        nbr.link_next_ms = now + self.p.link_backoff_ms
        self._ucast(nbr, wire.encode(wire.Ctrl(MsgType.LINK, self.nid, nbr.link_seq)))

    def _retry_links(self, now: int) -> None:
        for nbr in self.nbrs.values():
            if not nbr.awaiting_ack or now < nbr.link_next_ms:
                continue
            if nbr.link_attempts >= self.p.link_max_attempts:
                nbr.awaiting_ack = False
                nbr.link_failed = True
                nbr.link_rounds += 1   # G4: rounds of this epoch, bounds F13's wait
                nbr.link_retry_ms = now + self.p.link_retry_after_ms
                self._log("link_gave_up", peer=nbr.nid, attempts=nbr.link_attempts)
                continue
            nbr.link_attempts += 1
            nbr.link_next_ms = now + self.p.link_backoff_ms * (
                2 ** (nbr.link_attempts - 1)
            )
            # retx günlüğe yazılır; sayacı platform tutar (api.py: düğüm saymaz).
            self._log("retx", n=1, kind="link", peer=nbr.nid, attempt=nbr.link_attempts)
            self._ucast(
                nbr, wire.encode(wire.Ctrl(MsgType.LINK, self.nid, nbr.link_seq))
            )

    def _on_link(self, now: int, src_mac: int, c: "wire.Ctrl") -> None:
        nid, seq = c.src, c.seq
        if c.mtype == MsgType.LINK:
            # Aynı seq'i İKİNCİ kez ACK'liyorsak, karşı taraf ACK'imizi
            # kaybettiği için LINK'i tekrarlamıştır; bu ACK de "kayıp
            # nedeniyle tekrar gönderim"dir (brief 3.3 retx tanımı) ve
            # sayılmazsa kayıplı koşumda kanal temiz görünür.
            # SINIR: yalnız TABLODAKİ akranlar için saptanabilir. HELLO'sunu
            # hiç duymadığımız bir akranın LINK'i tabloya giriş açmaz (bu
            # kural düğüm 4 senaryosunun dürüstlüğünü sağlar), dolayısıyla
            # onun tekrarları burada görünmez. Sınırlı ve bilerek sınırlı:
            # alternatifi sınırsız bir ACK önbelleğidir, malloc yasaktır.
            peer = self.nbrs.get(nid)
            if peer is None or peer.mac != src_mac or not peer.link_up:
                # G2 (Amendment 13): only a node that hears the asker confirms
                # the link. An ask that comes before the asker's HELLO is
                # answered when that HELLO opens the record.
                if peer is None and len(self._link_asks) < self.p.nbr_table_max:
                    self._link_asks[nid] = (src_mac, seq)
                return
            if peer is not None:
                if peer.last_ack_seq == seq:
                    self._log("retx", n=1, kind="link_ack", peer=nid, seq=seq)
                peer.last_ack_seq = seq
            # LINK yanıtlanır ama TABLOYA GİRİŞ AÇMAZ. Komşuluk yalnız HELLO
            # ile kurulur; HELLO kaybı senaryosu (düğüm 4 örneği) ancak böyle
            # dürüst kalır.
            self.plat.send_unicast(
                src_mac, wire.encode(wire.Ctrl(MsgType.LINK_ACK, self.nid, seq))
            )
            return
        nbr = self.nbrs.get(nid)
        if nbr is None or seq != nbr.link_seq or nbr.mac != src_mac:
            return  # idempotent: eski / başka MAC'ten gelen ACK yok sayılır
        if nbr.bidir and not nbr.awaiting_ack:
            return  # yineleme durumu DEĞİŞTİRMEZ (api I5)
        nbr.awaiting_ack = False
        if nbr.link_up:
            nbr.bidir = True
            self._log("bidir", peer=nid)

    # ------------------------------------------------------------ soft state
    def stale_ms(self, nid: int) -> int:
        """This neighbour's stale window (F9): the default until it grows."""
        return self._stale_p.get(nid, self.p.stale_periods) * self.p.t_hello_ms

    def _restart_wait_ms(self, bidir: frozenset) -> int:
        """How long a view difference must persist before an epoch restart.

        F9: a frozen neighbour that is missing and whose window has grown is
        waited for over its own stale window; otherwise T_stab, as before. With
        the defaults (stale = stab = 3) that is the neighbour's stale window in
        every case, and a neighbour that never returns is detected after at
        most twice its window, so within twice the cap.
        """
        missing = (self._frozen_bidir or frozenset()) - bidir
        grown = [self.stale_ms(i) for i in missing if i in self._stale_p]
        return max([self.p.t_stab_ms] + grown)

    def _expiry_ms(self, nbr: BootNeighbor) -> Optional[int]:
        """After how much silence this record expires; None = not now (F13)."""
        return self.stale_ms(nbr.nid)

    def _expire(self, now: int) -> None:
        stale = []
        for n in self.nbrs.values():
            window = self._expiry_ms(n)
            if window is not None and now - n.last_ms > window:
                stale.append(n.nid)
        for nid in stale:
            self._log("nbr_expired", peer=nid, age=now - self.nbrs[nid].last_ms)
            del self.nbrs[nid]
            if self.p.adaptive_stale:
                self._expired.add(nid)

    # ------------------------------------------------ kararlılık kapısı + epoch
    def _gate(self, now: int, bidir: frozenset) -> None:
        # Taban burada da kurulur ve ASIL GARANTİ BUDUR. `on_timer` ezilebilir
        # ve ezilmektedir: `BbcvcNode.on_timer` `super()` çağırmaz, dolayısıyla
        # tabanı yalnız taban `on_timer`ında kurmak, üretimde hiç koşmayan bir
        # satır demektir (ölçen: bb-mnwifi). Değişmezi "her ezen kurmayı
        # hatırlasın" sözleşmesine bırakmak `Neighbor.last_ms`in eski hâliyle
        # aynı biçimdir: tesadüfen doğru, bir düzenleme uzağında sessizce
        # bozuk. Kapı ise ezilse de ezilmese de tek geçiş noktasıdır.
        self._establish_clock_baseline(now)
        if self.stable_since_ms is None:
            # `_establish_clock_baseline` EZİLEBİLİR bir uzantı noktasıdır;
            # ezip tabanı kurmayan bir alt sınıf, aşağıdaki `now - None`
            # aritmetiğinde ham bir TypeError ile patlardı. Çökerek saptamak
            # de saptamaktır, ama hangi sözleşmenin çiğnendiğini söylemez.
            raise ClockBaselineMissing(
                f"{type(self).__name__}._establish_clock_baseline() çağrıldı "
                f"ama stable_since_ms kurulmadı. Ezen sınıf ya super() "
                f"çağırmalı ya da stable_since_ms'i now_ms() değerine kurmalı."
            )
        if self.phase >= 1:
            if bidir == self._frozen_bidir:
                self._diff_since_ms = None
                return
            # THE SAME STABILITY TEST PHASE 0 ALREADY APPLIES. Phase 0 waits
            # `t_stab_ms` before it will freeze a neighbourhood, but phase 1
            # used to tear the network down on the FIRST disagreement, so a
            # neighbour that vanished and came back inside one stability
            # window still cost a network-wide restart. That asymmetry, not
            # the restart rule, is the defect.
            #
            # MEASURED on n20_m160 seed 1: t_hello is 132 ms and a neighbour
            # expires after three of them, 396 ms, but with twenty stations
            # sharing the medium the observed gap between receptions reached
            # 800 ms and its 99th percentile was 794 ms. Neighbours therefore
            # expired and returned constantly: two nodes produced 62 local
            # changes which became 458 network-wide resets, and the run never
            # converged. Requiring the difference to PERSIST does not patch
            # the protocol and does not weaken §3.5 item 6; it only stops a
            # blink from counting as a change. A neighbour that is really
            # gone still triggers the epoch bump, one stability window later.
            if self._diff_since_ms is None:
                self._diff_since_ms = now
                return
            if now - self._diff_since_ms < self._restart_wait_ms(bidir):
                return
            self.epoch = (self.epoch + 1) & 0xFF
            self.epoch_bumps += 1
            self.epoch_advance += 1
            self._log("epoch_bump", epoch=self.epoch)
            self._reset_to_phase0(now, reason="bidir_changed")
            return
        if self.p.gate_waits_for_pending_links and self._pending_links():
            return
        if now - self.stable_since_ms < self.p.t_stab_ms:
            return
        deg = len(bidir)
        self.deg = deg
        self.key = key_of(self.w, deg, self.nid)  # BİR KEZ, epoch boyunca sabit
        if not isinstance(self.key[0], int) or isinstance(self.key[0], bool):
            raise TypeError("anahtar sabit noktalı tamsayı olmalıdır (brief §3.6)")
        self._frozen_bidir = bidir
        self.frozen_at_ms = now
        self.phase = 1
        self._log("key_frozen", deg=deg, key_fp=self.key[0], epoch=self.epoch)

    def _reset_to_phase0(self, now: int, reason: str) -> None:
        self.phase = 0
        self.key = None
        self.deg = None
        self._frozen_bidir = None
        self.frozen_at_ms = None
        self.stable_since_ms = now
        self._diff_since_ms = None
        self._log("reset_phase0", reason=reason, epoch=self.epoch)
        # G2 (Amendment 13): verification belongs to an epoch. A record kept
        # across the restart is verified again, so a link the other end has
        # lost cannot enter the new frozen view on one side only.
        for nbr in self.nbrs.values():
            nbr.bidir = False
            nbr.awaiting_ack = False
            nbr.link_failed = False
            nbr.link_rounds = 0
            if nbr.link_up:
                self._start_link(now, nbr)

    def _rederive_id(self, now: int, other_mac: int) -> None:
        """Kimlik çakışması: BÜYÜK MAC tuzlu hash ile yeniden karar verir.

        Kimliğimiz değiştiği için komşuların bizim hakkımızda öğrendiği her şey
        geçersizdir; tablo boşaltılır, epoch artırılır ve ağ baştan koşar.
        """
        self.salt += 1
        old = self.nid
        self.nid = hash16(self.mac, self.salt)
        self.id_rederivations += 1
        self.nbrs.clear()
        self.epoch = (self.epoch + 1) & 0xFF
        self.epoch_bumps += 1
        self.epoch_advance += 1
        self._reset_to_phase0(now, reason="id_collision")
        self._last_hello_ms = None  # yeni kimliği hemen duyur
        self._log(
            "id_rederived", old=old, new=self.nid, salt=self.salt, other_mac=other_mac
        )


# ==========================================================================
# 6. Koşum ortamı: ccvc/bb/simnet.py
#    Burada bir zamanlar StubNet/StubPlatform adında ikinci bir taşıma katmanı
#    vardı. simnet.py'ye yönlü/zamanlı/tip-seçici `drop` yüklemi ve çağrılabilir
#    RSSI eklendiğinde stub'ın var oluş nedeni ortadan kalktı: brief 3.4'ün dört
#    arızası artık GERÇEK taşıma üzerinde yazılabilmektedir. Silindi; testler
#    SimNet'i sürer. Tek taşıma, tek muhasebe, tek kayıp modeli.
# ==========================================================================


__all__ = [
    "BootNeighbor",
    "BootstrapNode",
    "BootstrapParams",
    "epoch_newer",
    "hash16",
    "t_hello_lower_bound_ms",
    "xorshift32",
]
