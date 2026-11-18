#!/usr/bin/env python3
"""BB-CVC sözleşmesi. Bütün modüller buna bağlanır; bu dosya değiştirilmez.

Brief: plan/MWCCVC_DAGITIK_TASARIM_BRIEF.md
Keşif: DISCOVERY.md

MEVCUT MOTORDAN FARK (DISCOVERY §2, §3):
  * Mevcut `ccvc/engine.py` TUR TABANLIDIR (`on_round`). Asenkron modeli
    taşıyamaz. Burada OLAY GÜDÜMLÜ bir çekirdek tanımlanmaktadır.
  * Mevcut motor yalnız `rx` sayar. Burada tx, rx, bytes, max_payload, retx
    ayrı ayrı tutulur.
  * `ccvc/engine.py` ve `ccvc/d_*.py` BOZULMAZ; bu ayrı bir modüldür.

DEĞİŞMEZ İLKELER:
  I1  Düğüm koduna çizge VERİLMEZ. Komşu listesi bile HELLO ile keşfedilir.
  I2  Platform yalnız dört çağrı sağlar: send_broadcast, send_unicast,
      on_frame, now_ms. Geri kalan her şey algoritmanın parçasıdır.
  I3  Hiçbir yük 250 bayttan büyük olamaz. Aşım HATADIR, kırpma değil.
  I4  Aynı düğüm kodu hem senkron hem asenkron zamanlayıcıyla koşar.
      İki zamanlayıcı vardır, iki algoritma değil.
  I5  Kararlar monoton ve idempotenttir: rol yalnız OUT -> BACKBONE/COVER
      yönünde değişir, aynı mesajın tekrarı durumu değiştirmez.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_PAYLOAD = 250  # ESP-NOW sınırı, I3


class Role(IntEnum):
    """Rol. Sıralama monotonluk için anlamlıdır: yalnız artan yönde değişir."""

    OUT = 0
    MIS = 1
    CONNECTOR = 2
    COVER = 3

    @property
    def in_backbone(self) -> bool:
        return self in (Role.MIS, Role.CONNECTOR)

    @property
    def in_cover(self) -> bool:
        return self != Role.OUT


class MsgType(IntEnum):
    HELLO = 0
    LINK = 1
    LINK_ACK = 2
    JOIN = 3
    JOIN_ACK = 4
    HANDOVER = 5
    HANDOVER_ACK = 6
    HANDOVER_NACK = 7
    PUSH = 8
    PUSH_ACK = 9
    PUSH_NACK = 10
    TREE = 11
    STABLE = 12
    FINISH = 13
    #: DFS-Spanning-Backbone jeton gezintisi (brief §6). Ekip lideri onayıyla eklendi.
    #: Mevcut `wire.Ctrl` gövdesine oturur (mtype, src, seq = 5 B), yeni gövde
    #: yok, boyut savı etkilenmez. JOIN/TREE'yi ödünç almak `by_type_tx`i
    #: kirletir ve faz kırılımını yalan söyletirdi: iki dürüst üye daha ucuz.
    TOKEN = 14
    TOKEN_DONE = 15
    GREEDY_STATE = 16  # Local residual scores, not a global candidate table.
    #: DFS-Spanning-Backbone distributed control (section 6). TOKEN/TOKEN_DONE drive the walk;
    #: these two close the two pieces that were missing from the arm.
    #:
    #: DFS_DONE floods the completed spanning tree so that EVERY node learns
    #: phase 1 is over. Only the initiator can know the walk finished (its own
    #: stack emptied); nobody else can. `_barrier` cannot serve here because it
    #: synchronises on phase, and whether the phase may advance is precisely
    #: what has to be decided.
    DFS_DONE = 17
    #: BB_MIS runs a maximal independent set RESTRICTED TO THE BACKBONE, after
    #: tree degrees freeze. Without it every internal node would be CONNECTOR,
    #: `mis_nbrs` would be empty everywhere, and the 3-hop gap rule would
    #: silently never fire -- it would not crash, it would quietly do nothing.
    BB_MIS = 18
    #: GHS-MST-Backbone distributed MST (GHS). One body serves all seven so that
    #: `by_type_tx` still attributes each protocol step separately.
    GHS_CONNECT = 19
    GHS_INITIATE = 20
    GHS_TEST = 21
    GHS_ACCEPT = 22
    GHS_REJECT = 23
    GHS_REPORT = 24
    GHS_CHANGE_ROOT = 25


# --------------------------------------------------------------------------
# platform: düğümün dış dünyayla TEK teması
# --------------------------------------------------------------------------
class Platform(ABC):
    """Dört çağrı. ESP-NOW'da ve mininet-wifi'de aynı dört çağrı (brief 3.5)."""

    @abstractmethod
    def send_broadcast(self, payload: bytes) -> None:
        """Bütün komşulara tek iletim. tx += 1, rx += komşu sayısı."""

    @abstractmethod
    def send_unicast(self, dst: int, payload: bytes) -> None:
        """Tek hedefe iletim. tx += 1, rx += 1."""

    @abstractmethod
    def now_ms(self) -> int:
        """Monoton saat, milisaniye."""

    @abstractmethod
    def log(self, event: str, **fields: Any) -> None:
        """JSONL günlük. Sayaçlar buradan türetilir, düğüm kendi sayacını raporlamaz."""


# --------------------------------------------------------------------------
# muhasebe (brief 3.3)
# --------------------------------------------------------------------------
@dataclass
class Counters:
    """tx ve rx AYRI tutulur. Mevcut motorun yalnız rx saydığı hatası burada yok.

    RX ATFI (bb-core bildirdi, 2026-09-15).
    `record_tx` rx'i GÖNDERİCİYE yazar, yani "bu düğümün iletimlerinin yol açtığı
    teslim sayısı" demektir. Brief 3.3 tablosunda rx'in temsil ettiği şey
    "işleme/tampon", yani ALICI maliyetidir. Küresel toplamlar iki atıfta da
    aynıdır, dolayısıyla omurga argümanı ve kalibrasyon etkilenmez; fark yalnız
    DÜĞÜM BAŞINA okumada ortaya çıkar. Alıcı tarafı ayrıca `SimNet.rx_delivered`
    içinde tutulur ve düğüm başına tampon maliyeti oradan okunur. Raporlarda
    hangi atfın kullanıldığı yazılmalıdır.

    KARAR: `by_phase_rx` BURAYA EKLENMEZ (takım lideri, 2026-09-15).
    `by_phase_tx` gönderici taraflıdır ve doğrusu odur: "X fazındayken yaptığım
    iletimler". Aynı kalıpla eklenecek bir `by_phase_rx` ise "X fazındayken
    yaptığım iletimlerin yol açtığı teslimler" olurdu, yani yine GÖNDERİCİNİN
    fazı. Oysa rx'in ölçtüğü şey ALICININ işidir. Küresel toplamlar eşit olduğu
    için fark bugün görünmüyor, ama faz kırılımında tam da görünür hale gelir:
    bir düğüm Faz 5'teyken Faz 0'daki komşusunun çerçevesini işleyebilir.

    Alıcı taraflı faz kırılımı isteniyorsa doğru yer `SimNet.deliver()`'dır,
    çünkü alıcının fazı ancak çerçeve İŞLENDİĞİ anda bilinir. `rx_delivered`
    bile kuyruğa girişte artar, işlemede değil, dolayısıyla o da faz kırılımı
    için doğru nokta değildir. Şekil 5 alıcı maliyetini gösteriyorsa sayacı
    oradan almalı ve adı atfı ele vermelidir.

    RETX SÖZLEŞMESİ (bb-core bildirdi). Düğüm kendi sayacını raporlamaz (brief §7),
    bu yüzden yeniden gönderim `Platform.log("retx", n=...)` ile bildirilir ve
    ağ katmanı bunu `retx` alanına ekler. Bu bir SÖZLEŞMEDİR, kod tarafından
    zorlanmaz; `log` olayının adı "retx" olmak zorundadır.
    """

    tx: int = 0
    rx: int = 0
    bytes_tx: int = 0
    max_payload: int = 0
    retx: int = 0
    by_type_tx: Dict[int, int] = field(default_factory=dict)
    by_type_rx: Dict[int, int] = field(default_factory=dict)
    by_phase_tx: Dict[int, int] = field(default_factory=dict)
    radio_on_ms: int = 0

    def record_tx(self, mtype: int, phase: int, nbytes: int, fanout: int) -> None:
        if nbytes > MAX_PAYLOAD:
            raise PayloadTooLarge(f"{nbytes} B > {MAX_PAYLOAD} B (tip {mtype})")
        self.tx += 1
        self.rx += fanout
        self.bytes_tx += nbytes
        self.max_payload = max(self.max_payload, nbytes)
        self.by_type_tx[mtype] = self.by_type_tx.get(mtype, 0) + 1
        self.by_phase_tx[phase] = self.by_phase_tx.get(phase, 0) + 1

    #: Label that MUST accompany this quantity wherever it is shown to a reader.
    #: The warning lives in the code next to the value, not in a docstring,
    #: because a caveat in a docstring does not travel into a figure caption.
    ENERGY_LABEL: str = (
        "derived ESP32 radio-model estimate (100 mA listen / 240 mA transmit "
        "@ 1 Mbps), NOT measured energy; valid for comparing arms under one "
        "model, not as an absolute figure"
    )

    def energy_mah_esp32_model(self, t_frame_ms: float = 0.7) -> float:
        """DERIVED ESP32 ESTIMATE, not a measurement on the target platform.

        The target platform is mininet-wifi (see module header). A mininet-wifi
        station is a Linux process: it has no radio and draws no current, so
        this quantity is an ESP32 power model (brief §3.6: 100 mA listening,
        240 mA transmitting, 1 Mbps frame times) applied to emulated timings.

        It is kept because every arm is scored under the SAME model, so
        arm-to-arm comparison remains meaningful. It is NOT an absolute energy
        figure and must never be presented as one: any axis, caption or CSV
        column carrying it must also carry `ENERGY_LABEL`.

        (Found by bb-core while auditing which constraints survive the move
        from ESP32 to mininet-wifi. It was not on the audit list and is the
        most externally exposed number in the study, because figure 8 plots it.)
        """
        listen = self.radio_on_ms / 3_600_000.0 * 100.0
        send = self.tx * t_frame_ms / 3_600_000.0 * 240.0
        return round(listen + send, 6)

    #: Deprecated bare name. Kept so existing callers do not break silently,
    #: but the explicit name is the one to use, for the same reason
    #: `observer_best_weight` was renamed: the caveat belongs in the identifier.
    energy_mah = energy_mah_esp32_model


class PayloadTooLarge(RuntimeError):
    """I3 ihlali. Kırpma yok, hata var."""


# --------------------------------------------------------------------------
# komşu kaydı (bootstrap, brief 3.5)
# --------------------------------------------------------------------------
#: `last_ms` için "verilmedi" nöbetçisi. Dataclass kuralı gereği varsayılansız
#: alan, varsayılanlı alandan sonra gelemez; alan sırasını bozmadan zorunluluk
#: bu nöbetçiyle sağlanır.
_TIME_UNSET = -1


@dataclass
class Neighbor:
    """HELLO ile öğrenilen komşu. Hiçbiri motordan gelmez."""

    nid: int
    key: Optional[int] = None        # 16.16 sabit nokta
    role: Role = Role.OUT
    phase: int = 0
    load: int = 0
    mis_nbrs: Tuple[int, ...] = ()   # en fazla 5 (brief G8)
    epoch: int = 0
    #: En son ne zaman duyulduğu. VARSAYILANI YOKTUR ve olmamalıdır.
    #:
    #: TUZAK (2026-09-15, bb-bootstrap süpürmesi). Burada varsayılan `0` vardı.
    #: Sıfırdan başlayan bir sanal saatte zararsız görünür; GERÇEK duvar saatinde
    #: `0` "sonsuz eski" demektir, dolayısıyla yeni kurulan bir komşu kaydı
    #: doğduğu anda yumuşak-durum süresi dolmuş sayılır. Kod yalnız ŞANS ESERİ
    #: çalışıyordu: kurucudan birkaç satır sonra `last_ms = now` atanıyordu ve
    #: arada `return` yoktu. Araya bir `return` eklemek hatayı sessizce açardı.
    #: Artık zorunlu alan; çağıran `now_ms()` değerini vermek zorunda.
    last_ms: int = _TIME_UNSET
    bidir: bool = False              # LINK/LINK-ACK ile doğrulanır
    rssi_ema: Optional[float] = None

    def __post_init__(self) -> None:
        if self.last_ms == _TIME_UNSET:
            raise TypeError(
                "Neighbor(last_ms=...) zorunludur; şu anki now_ms() değerini verin. "
                "Varsayılan 0 bırakılamaz: gerçek duvar saatinde 0 'sonsuz eski' "
                "demektir ve kayıt doğduğu anda yumuşak-durumdan düşer."
            )


# --------------------------------------------------------------------------
# düğüm: olay güdümlü durum makinesi (brief 3.2)
# --------------------------------------------------------------------------
class NodeCore(ABC):
    """Tek düğümün bütün mantığı. Senkron ve asenkron aynı kodu koşar.

    Düğüm çizgeyi GÖREMEZ (I1). Elinde yalnız kendi kimliği, ağırlığı, kapasitesi
    ve HELLO ile öğrendikleri vardır.
    """

    @abstractmethod
    def on_frame(self, src: int, rssi: Optional[float], payload: bytes) -> None:
        """Bir çerçeve geldi. Durum güncellenir, gerekiyorsa mesaj gönderilir.

        KARAR (2026-09-15, bb-bootstrap'ın bildirdiği çatışma üzerine).
        `src` **GÖNDERENİN MAC ADRESİDİR**, düğüm kimliği değildir. 48 bitlik
        tamsayı olarak geçirilir.

        Gerekçe fiziksel. ESP-NOW'da ve 802.11'de gönderenin MAC'i çerçeve
        BAŞLIĞINDA taşınır, alıcı onu radyodan alır; kimse kendi MAC'ini yükün
        içine koymaz. Mininet-wifi'de de soketten okunur. Dolayısıyla MAC'i
        HELLO yüküne eklemek hem fizikle çelişir hem de boşuna 6 bayt harcar.

        Kimlik çakışması denetimi buradan çıkar ve ek bayt istemez: HELLO yükü
        gönderenin İDDİA ETTİĞİ kimliği taşır, alıcı ise MAC'i başlıktan bilir.
        Çakışma, iki farklı MAC'in aynı kimliği iddia etmesidir; büyük MAC'li
        düğüm tuzlu hash ile kimliğini yeniden türetir (brief 3.5 madde 1).

        Sonuç: wire HELLO'sunda MAC alanı YOKTUR ve olmayacaktır.
        """

    @abstractmethod
    def on_timer(self, name: str) -> None:
        """Bir zamanlayıcı ateşledi (HELLO periyodu, ACK zaman aşımı, slot sınırı)."""

    @abstractmethod
    def snapshot(self) -> "NodeSnapshot":
        """Ölçüm ve şekil için anlık görüntü. Karar için KULLANILMAZ."""

    @property
    @abstractmethod
    def done(self) -> bool:
        """Yerel sükûnet (brief 5a)."""

    #: Düğümün o anki fazı; faz başına muhasebe için ağ katmanı okur.
    #: Salt okunur ÖZELLİK DEĞİL, düz sınıf niteliğidir: düğüm buna yazar.
    #: (bb-core bildirdi: tel üzerinde faz yalnız HELLO'da taşınıyor, bu yüzden
    #: ağ katmanının düğümden okuması gerekiyor. İlk denemem property idi ve
    #: atamayı engellediği için 63 testi kırdı; ders kayıtta.)
    phase: int = 0


@dataclass
class NodeSnapshot:
    nid: int
    role: Role
    phase: int
    key: Optional[int]
    deg: int
    owned: Tuple[Tuple[int, int], ...]   # sahiplenilen kenarlar
    forced_load: int
    counters: Counters
    epoch: int


# --------------------------------------------------------------------------
# zamanlayıcı (brief 3.2: iki zamanlayıcı, tek düğüm kodu)
# --------------------------------------------------------------------------
class Scheduler(ABC):
    """Senkron slotlu ya da asenkron olay güdümlü."""

    name: str = "unnamed"

    @abstractmethod
    def run(self, max_ms: int) -> "RunOutcome":
        ...


@dataclass
class RunOutcome:
    """Bir koşumun sonucu. owner ÇIKTININ PARÇASIDIR (brief §1)."""

    scheduler: str
    cover: List[int]
    owner: Dict[Tuple[int, int], int]
    total_weight: float
    counters_by_node: Dict[int, Counters]
    slots: Optional[int] = None       # senkron
    t_conv_ms: Optional[int] = None   # asenkron
    converged: bool = False
    notes: List[str] = field(default_factory=list)

    def totals(self) -> Counters:
        agg = Counters()
        for c in self.counters_by_node.values():
            agg.tx += c.tx
            agg.rx += c.rx
            agg.bytes_tx += c.bytes_tx
            agg.retx += c.retx
            agg.radio_on_ms += c.radio_on_ms
            agg.max_payload = max(agg.max_payload, c.max_payload)
            for d, s in ((agg.by_type_tx, c.by_type_tx), (agg.by_type_rx, c.by_type_rx),
                         (agg.by_phase_tx, c.by_phase_tx)):
                for kk, vv in s.items():
                    d[kk] = d.get(kk, 0) + vv
        return agg


# --------------------------------------------------------------------------
# doğrulama (brief §9): ihlal listesi ZORUNLU
# --------------------------------------------------------------------------
@dataclass
class Violation:
    kind: str                 # "uncovered_edge" | "overload" | "disconnected" | "bad_owner"
    detail: str
    nodes: Tuple[int, ...] = ()
    edges: Tuple[Tuple[int, int], ...] = ()


@dataclass
class ValidationReport:
    vertex_cover: bool
    connected: bool
    capacity: bool
    violations: List[Violation] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.vertex_cover and self.connected and self.capacity and not self.violations


# --------------------------------------------------------------------------
# sabit nokta (brief 3.6: ESP32-C3'te FPU yok)
# --------------------------------------------------------------------------
FP_SHIFT = 16


def to_fp(x: float) -> int:
    """16.16 sabit noktaya çevir."""
    return int(round(x * (1 << FP_SHIFT)))


def from_fp(x: int) -> float:
    return x / float(1 << FP_SHIFT)


def key_of(weight: float, deg: int, nid: int) -> Tuple[int, int]:
    """key(v) = (w(v)/(deg(v)+1), id(v)); küçük = örtüye girmeye daha uygun.

    Sabit noktalı, deterministik. Çalışan örnekte doğrulanmıştır:
    w=5,deg=2 -> 1.67 | w=2,deg=3 -> 0.50 | w=3,deg=4 -> 0.60
    """
    return (to_fp(weight / (deg + 1)), nid)
