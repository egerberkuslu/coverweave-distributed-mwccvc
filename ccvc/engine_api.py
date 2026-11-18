#!/usr/bin/env python3
"""Dağıtık CCVC motor sözleşmesi (F2 arayüzü). TÜM dağıtık algoritmalar buna bağlanır.

TASARIM İLKESİ — pazarlıksız:

    Düğüm kodu küresel çizgeyi HİÇBİR ZAMAN göremez.

Motor gerçek çizgeyi tutar ama düğüme yalnız `LocalView` verir. Bir düğüm
`LocalView` dışında hiçbir şeye erişemediği için "yanlışlıkla merkezi" bir
algoritma yazmak yapısal olarak imkânsızdır. Kaynak depodaki hatanın (her düğüm
tüm topolojiyi taşıyıp merkezi çözücüyü yerel koşuyor) tekrarlanmasını bu ilke
engeller.

Mesaj modeli:
  * r turunda gönderilen mesaj r+1 turunda teslim edilir. Yani komşu bilgisi
    doğal olarak bir tur eskidir; yapay gecikme enjekte edilmez.
  * Mesajlar gerçekten sayılır. Sentetik "mesaj sayısı" üretilmez.
  * Yalnız çizgede komşu olan düğümler arasında mesaj taşınır. Komşu olmayana
    mesaj göndermek hatadır (motor reddeder).

Değişmez kurallar (motor doğrular):
  I1  Bir kenar, iki ucu da anlaşmadan örtülü işaretlenemez.
  I2  Bir düğüm kapasitesinden fazla kenar sahiplenemez.
  I3  Düğüm yalnız kendi komşularına mesaj gönderebilir.
  I4  Düğüm kararı yalnız LocalView'e bakarak verir (tip sistemiyle zorlanır).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

Edge = Tuple[int, int]

# --------------------------------------------------------------------------
# mesaj
# --------------------------------------------------------------------------
# Kaynak depodaki sekiz tip korunuyor; anlamları plan/PLAN_DCCVC.md §2'de.
COVER_INTENT = "COVER_INTENT"
EDGE_CLAIM = "EDGE_CLAIM"
EDGE_CLAIM_ACK = "EDGE_CLAIM_ACK"
EDGE_CLAIM_NACK = "EDGE_CLAIM_NACK"
CAPACITY_STATE = "CAPACITY_STATE"
COVER_MEMBERSHIP = "COVER_MEMBERSHIP"
BRIDGE_REQUEST = "BRIDGE_REQUEST"
BRIDGE_ACCEPT = "BRIDGE_ACCEPT"
COVER_WITHDRAW = "COVER_WITHDRAW"
# D-CDS kolu için:
MARK_STATE = "MARK_STATE"  # Wu-Li işaret durumu
TWO_HOP_DIGEST = "TWO_HOP_DIGEST"  # komşunun komşu listesi özeti


@dataclass(frozen=True)
class Message:
    """Tek mesaj. `dst=None` komşulara yayın demektir (her komşuya bir mesaj sayılır)."""

    kind: str
    src: int
    dst: Optional[int]
    payload: Dict[str, Any] = field(default_factory=dict)
    round_sent: int = -1

    def fanout(self, degree: int) -> int:
        """Bu mesajın kaç mesaj olarak sayılacağı (yayın = derece kadar)."""
        return degree if self.dst is None else 1


# --------------------------------------------------------------------------
# yerel görüş
# --------------------------------------------------------------------------
@dataclass
class EdgeLocal:
    """Düğümün kendi komşu kenarı hakkında BİLDİĞİ durum.

    `covered` yalnız iki uç anlaştıktan sonra True olur (I1). `owner` bu düğümün
    inandığı sahiptir; karşı uç farklı inanıyorsa bu bir tutarsızlıktır ve
    protokolün onu çözmesi gerekir.
    """

    other: int
    covered: bool = False
    owner: Optional[int] = None
    claimed_by_me: bool = False


@dataclass
class NeighborRecord:
    """Bir komşu hakkında dedikoduyla gelen bilgi. `age_rounds` kaç tur eskidiğidir."""

    node: int
    weight: float
    uncovered_degree: int
    remaining_capacity: int
    in_cover: bool
    score: Optional[Tuple] = None
    age_rounds: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def stale(self) -> bool:
        """Bir turdan eski bilgi bayat sayılır."""
        return self.age_rounds > 1


@dataclass
class LocalView:
    """Düğümün karar anında gördüğü HER ŞEY. Küresel bilgi burada YOKTUR.

    `two_hop` yalnız protokol iki atlama özeti topluyorsa dolar ve `via` alanı
    hangi komşu üzerinden geldiğini söyler.

    UYARI (tezde bir kez yaşanan tuzak): iki atlama özeti kullanılacaksa
    **adaya koşullu** hesaplanmalı. Adaydan bağımsız bir toplam her adaya aynı
    sabiti ekler, argmin'i hiç değiştirmez ve iki-atlama kolu tek-atlama
    kuralına sessizce çöker.
    """

    me: int
    round: int
    weight: float
    capacity_k: int
    remaining_capacity: int
    in_cover: bool
    incident: Dict[int, EdgeLocal]
    neighbors: Dict[int, NeighborRecord]
    inbox: List[Message] = field(default_factory=list)
    two_hop: Dict[int, NeighborRecord] = field(default_factory=dict)
    via: Dict[int, int] = field(default_factory=dict)

    # ---- yerel türetilmiş büyüklükler (hepsi 1 atlama) ----
    def uncovered_incident(self) -> List[int]:
        """Bu düğümün henüz örtülmemiş komşu kenarlarının karşı uçları."""
        return sorted(o for o, e in self.incident.items() if not e.covered)

    def uncovered_degree(self) -> int:
        return len(self.uncovered_incident())

    def sum_uncovered_neighbor_weights(self) -> float:
        """GRCCVC paydası: örtülmemiş kenarla bağlı komşuların ağırlık toplamı."""
        total = 0.0
        for o in self.uncovered_incident():
            rec = self.neighbors.get(o)
            if rec is not None:
                total += rec.weight
        return total

    def messages_of(self, kind: str) -> List[Message]:
        return [m for m in self.inbox if m.kind == kind]

    def any_stale(self) -> bool:
        return any(r.stale for r in self.neighbors.values())


# --------------------------------------------------------------------------
# düğüm kararı
# --------------------------------------------------------------------------
@dataclass
class NodeDecision:
    """Bir düğümün bir turda motora bildirdiği niyet.

    Motor bunları toplar, çelişkileri çözer ve gerçek duruma uygular. Düğüm
    doğrudan küresel duruma yazamaz.
    """

    join_cover: bool = False
    leave_cover: bool = False
    claim_edges: List[int] = field(default_factory=list)  # karşı uç kimlikleri
    release_edges: List[int] = field(default_factory=list)
    accept_claims: List[int] = field(default_factory=list)  # onaylanan talep sahipleri
    reject_claims: List[int] = field(default_factory=list)
    quiescent: bool = False  # "benim tarafımda yapacak iş kalmadı"
    note: str = ""  # hata ayıklama


# --------------------------------------------------------------------------
# protokol arayüzü
# --------------------------------------------------------------------------
class NodeProtocol(ABC):
    """Her dağıtık algoritma bunu uygular. Tek giriş noktası `on_round`.

    Uygulayıcı SINIF ÖRNEK BAŞINA BİR DÜĞÜMDÜR. Kendi yerel durumunu kendi
    alanlarında tutabilir; ama başka bir düğümün örneğine erişmemelidir.
    Motor buna izin vermez, örnekler arasında paylaşılan hiçbir yapı geçirilmez.
    """

    name: str = "unnamed"

    @abstractmethod
    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        """Bir turluk yerel karar. Yalnız `view` kullanılabilir.

        Döndürür: (gönderilecek mesajlar, karar).
        """

    def on_start(self, me: int, weight: float, capacity_k: int, degree: int) -> None:
        """İsteğe bağlı kurulum. Küresel bilgi verilmez, yalnız kendi parametreleri."""

    def local_score(self, view: LocalView) -> Tuple:
        """İsteğe bağlı: karşılaştırma ve hata ayıklama için yerel öncelik anahtarı."""
        raise NotImplementedError


# --------------------------------------------------------------------------
# koşum sonucu
# --------------------------------------------------------------------------
@dataclass
class RunResult:
    """Bir dağıtık koşumun sonucu. `messages` GERÇEK sayımdır, tahmin değil."""

    algorithm: str
    cover: List[int]
    owner: Dict[Edge, int]
    rounds: int
    messages: int
    messages_by_kind: Dict[str, int]
    converged: bool
    per_round: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "cover": sorted(self.cover),
            "cover_size": len(self.cover),
            "rounds": self.rounds,
            "messages": self.messages,
            "messages_by_kind": dict(sorted(self.messages_by_kind.items())),
            "converged": self.converged,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# motor sözleşmesi (F2 bunu uygular)
# --------------------------------------------------------------------------
class EngineContract(ABC):
    """`ccvc/engine.py` bunu uygulayacak. Buradaki imzalar sabit.

    Motor:
      * gerçek çizgeyi tutar, düğümlere ASLA vermez
      * r turunda gönderileni r+1 turunda teslim eder
      * komşu olmayana gönderilen mesajı reddeder (I3)
      * kenar sahipliğini iki uç anlaşınca yazar (I1) ve kapasiteyi zorlar (I2)
      * mesajları tipine göre gerçekten sayar
      * yakınsama: tüm düğümler quiescent VE hiç mesaj yoksa dur
    """

    @abstractmethod
    def run(self, protocol_factory, max_rounds: int = 200) -> RunResult:
        """`protocol_factory(node_id) -> NodeProtocol` ile her düğüme bir örnek verir."""
