#!/usr/bin/env python3
"""Senkron tur motoru (F2). `EngineContract` uygulaması.

TASARIM İLKESİ — pazarlıksız: düğüm kodu küresel çizgeyi göremez.

Motor gerçek çizgeyi, kenar örtü durumunu, kenar sahipliğini ve düğüm başına
kalan kapasiteyi kendi özel alanlarında tutar. Protokol örneğine verilen tek şey
her turda SIFIRDAN kurulan bir `LocalView`'dür. Görüşün içindeki her nesne o tur
için üretilmiş yeni bir nesnedir; protokol onu değiştirse bile motorun gerçek
durumu bozulmaz. Protokol örneğine ne motorun kendisi ne başka bir düğümün
örneği geçirilir, dolayısıyla "kazara merkezi" bir algoritma yazmak yapısal
olarak imkânsızdır.

--------------------------------------------------------------------------
TUR 0'DA DÜĞÜM NE BİLİR
--------------------------------------------------------------------------
Bir telsiz kimi duyabildiğini bilir ama karşısındakinin ağırlığını,
kapasitesini ya da niyetini konuşmadan bilemez. Bu yüzden tur 0'da düğümün
görüşü şudur:

  * kendi kimliği, ağırlığı, kapasite k'sı, kalan kapasitesi (= k)
  * örtüde olmadığı bilgisi (in_cover=False)
  * kendi komşu kenarlarının KİMLİĞİ ve SAYISI (incident sözlüğü), hepsi
    covered=False, owner=None, claimed_by_me=False
  * neighbors = {} (BOŞ), two_hop = {}, inbox = []

Yani derece tur 0'da bilinir, komşunun durumu bilinmez. Komşu kaydı ancak o
komşu kendi durumunu taşıyan bir mesaj gönderdiğinde doğar. Motor kayıtları
kendiliğinden tazelemez.

--------------------------------------------------------------------------
ESKİME
--------------------------------------------------------------------------
r turunda gönderilen mesaj r+1 turunda teslim edilir. Kayıt, mesajın
GÖNDERİLDİĞİ turu saklar; `age_rounds = görüş_turu - gönderim_turu`. Teslim
edildiği turda bir kayıt her zaman 1 turluktur (`stale` False, çünkü
`NeighborRecord.stale` eşiği `age_rounds > 1`). Komşu susarsa yaş her turda
bir artar ve iki tur sessizlikten sonra kayıt bayatlar.

--------------------------------------------------------------------------
I1 — KENAR NE ZAMAN ÖRTÜLÜ SAYILIR (uygulanan tam kural)
--------------------------------------------------------------------------
e={u,v} kenarı YALNIZ şu üç durumdan biriyle örtülü işaretlenir:

 (1) KARŞILIKLI TALEP. u ve v aynı turda e'yi talep eder (ya da biri bu turda
     talep ederken diğerinin bekleyen talebi durmaktadır). İki uç da kenarın
     örtülmesi gerektiğinde anlaşmıştır, yalnız sahibi tartışmalıdır; motor
     sahibi küçük kimlikle belirler, kapasite dolu ise diğer uca düşer, ikisi
     de doluysa kenar örtülmez. Her iki uç da sonucu kendi EdgeLocal'inde görür.

 (2) İTİRAZSIZ TEK-UÇ TALEBİ. u e'yi talep eder, bu turun katılımlarından sonra
     u örtüdedir, v örtüde DEĞİLDİR ve v aynı turda ne e'yi talep etmiş ne de
     u'yu reddetmiştir. v örtüde olmadığı için kenarı sahiplenmesi zaten
     imkânsızdır, dolayısıyla gerçek bir anlaşmazlık yoktur; kenar u'ya geçer.

 (3) AÇIK ONAY. u daha önceki bir turda talep etmiştir, talep hâlâ beklemededir
     ve v bu turda kararında u'yu `accept_claims` içine koyar (aynı turda
     `reject_claims` içinde de varsa RED kazanır). Kenar u'ya geçer.

Bunların dışında kalan tek-uç talebi BEKLEMEDE kalır; kenar örtülü sayılmaz.
Ek değişmez kural: kenarı yalnız ÖRTÜDEKİ bir düğüm sahiplenebilir; örtüde
olmayan düğümün talebi düşürülür.

--------------------------------------------------------------------------
I2 — KAPASİTE
--------------------------------------------------------------------------
Bir düğüm hiçbir anda capacity_k'dan fazla kenar sahiplenemez. Bir turda bir
düğüme birden çok kenar düşüyorsa kenarlar (tercih edilen sahip, karşı uç
kimliği) sırasıyla işlenir; yük k'ya varınca kalan talepler reddedilir ve
talep sahibinin `claimed_by_me` bayrağı düşer (geri bildirim kanalı budur,
motor sahte mesaj üretmez).

--------------------------------------------------------------------------
SONLANMA
--------------------------------------------------------------------------
Koşum ancak TÜM düğümler o turda quiescent bildirdiğinde VE hiç mesaj yolda
olmadığında yakınsar. Motor "zaten tüm kenarlar örtüldü" diye durmaz; bu
küresel bilginin durma kuralına sızması olurdu. max_rounds'a varılırsa
converged=False.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:  # paket olarak da, ccvc/ içinden de çalışsın
    from ccvc import engine_api as api
    from ccvc.bridge import CcvcGraph, Edge, edge_key, verify
    from ccvc.engine_api import (
        EdgeLocal,
        EngineContract,
        LocalView,
        Message,
        NeighborRecord,
        NodeDecision,
        NodeProtocol,
        RunResult,
    )
except ImportError:  # pragma: no cover
    import engine_api as api  # type: ignore
    from bridge import CcvcGraph, Edge, edge_key, verify  # type: ignore
    from engine_api import (  # type: ignore
        EdgeLocal,
        EngineContract,
        LocalView,
        Message,
        NeighborRecord,
        NodeDecision,
        NodeProtocol,
        RunResult,
    )


class EngineViolation(RuntimeError):
    """Protokol sözleşmeyi çiğnedi (I3 ihlali, sahte src, komşu olmayan kimlik...)."""


# durum taşıyan yük anahtarları: motor yalnız bunları komşu kaydına çevirir
STATE_KEYS = ("weight", "uncovered_degree", "remaining_capacity", "in_cover", "score")


@dataclass
class _Rec:
    """Motorun özel komşu-bilgisi kaydı. LocalView'e her turda kopyası verilir."""

    weight: float = 0.0
    uncovered_degree: int = 0
    remaining_capacity: int = 0
    in_cover: bool = False
    score: Optional[Tuple] = None
    round_sent: int = -1
    extra: Dict[str, Any] = field(default_factory=dict)


class RoundEngine(EngineContract):
    """Senkron tur motoru.

    `poll_order` yalnız test içindir: düğümlerin hangi sırayla yoklandığını
    değiştirir. Sonuç bu sıradan ETKİLENMEMELİDİR (bütün çıktılar toplanmadan
    hiçbir şey uygulanmaz), test_engine.py bunu doğrular.
    """

    def __init__(
        self,
        graph: CcvcGraph,
        poll_order: Optional[Sequence[int]] = None,
        algorithm: Optional[str] = None,
    ) -> None:
        self._g = graph
        self._nodes: List[int] = sorted(graph.nodes)
        self._adj: Dict[int, Tuple[int, ...]] = {
            v: tuple(sorted(graph.adj.get(v, ()))) for v in self._nodes
        }
        self._edges: List[Edge] = sorted({edge_key(u, v) for u, v in graph.edges})
        self._k = int(graph.capacity_k)
        self._algorithm = algorithm
        if poll_order is None:
            self._poll: List[int] = list(self._nodes)
        else:
            self._poll = list(poll_order)
            if sorted(self._poll) != self._nodes:
                raise EngineViolation("poll_order tüm düğümleri tam bir kez içermeli")
        self._reset()

    # ------------------------------------------------------------------
    # özel durum
    # ------------------------------------------------------------------
    def _reset(self) -> None:
        self._covered: Dict[Edge, bool] = {e: False for e in self._edges}
        self._owner: Dict[Edge, Optional[int]] = {e: None for e in self._edges}
        self._pending: Dict[Edge, Optional[int]] = {e: None for e in self._edges}
        self._load: Dict[int, int] = {v: 0 for v in self._nodes}
        self._in_cover: Set[int] = set()
        self._known: Dict[int, Dict[int, _Rec]] = {v: {} for v in self._nodes}
        self._two_hop: Dict[int, Dict[int, _Rec]] = {v: {} for v in self._nodes}
        self._via: Dict[int, Dict[int, int]] = {v: {} for v in self._nodes}
        # yolda olan mesajlar: (src, idx, dst, Message) — yayın burada açılır
        self._outq: List[Tuple[int, int, int, Message]] = []
        self._msg_total = 0
        self._by_kind: Dict[str, int] = {}
        self._notes: List[str] = []

    # ------------------------------------------------------------------
    # görüş kurma — her tur sıfırdan, paylaşılan değişebilir nesne YOK
    # ------------------------------------------------------------------
    def _build_view(self, v: int, rnd: int, inbox: List[Message]) -> LocalView:
        incident: Dict[int, EdgeLocal] = {}
        for o in self._adj[v]:
            e = edge_key(v, o)
            own = self._owner[e]
            incident[o] = EdgeLocal(
                other=o,
                covered=self._covered[e],
                owner=own,
                claimed_by_me=(own == v) or (self._pending[e] == v),
            )
        neighbors: Dict[int, NeighborRecord] = {}
        for o, rec in sorted(self._known[v].items()):
            neighbors[o] = NeighborRecord(
                node=o,
                weight=rec.weight,
                uncovered_degree=rec.uncovered_degree,
                remaining_capacity=rec.remaining_capacity,
                in_cover=rec.in_cover,
                score=rec.score,
                age_rounds=rnd - rec.round_sent,
                extra=copy.deepcopy(rec.extra),
            )
        two_hop: Dict[int, NeighborRecord] = {}
        for o, rec in sorted(self._two_hop[v].items()):
            two_hop[o] = NeighborRecord(
                node=o,
                weight=rec.weight,
                uncovered_degree=rec.uncovered_degree,
                remaining_capacity=rec.remaining_capacity,
                in_cover=rec.in_cover,
                score=rec.score,
                age_rounds=rnd - rec.round_sent,
                extra=copy.deepcopy(rec.extra),
            )
        return LocalView(
            me=v,
            round=rnd,
            weight=float(self._g.weight[v]),
            capacity_k=self._k,
            remaining_capacity=self._k - self._load[v],
            in_cover=v in self._in_cover,
            incident=incident,
            neighbors=neighbors,
            inbox=inbox,
            two_hop=two_hop,
            via=dict(self._via[v]),
        )

    # ------------------------------------------------------------------
    # teslim
    # ------------------------------------------------------------------
    def _deliver(self, rnd: int) -> Tuple[Dict[int, List[Message]], int]:
        """Bir önceki turda kuyruklananları dağıt, GERÇEKTEN sayarak."""
        inboxes: Dict[int, List[Message]] = {v: [] for v in self._nodes}
        # (src, idx) anahtarı yoklama sırasından bağımsızdır -> belirlenimci
        for src, idx, dst, msg in sorted(self._outq, key=lambda t: (t[0], t[1], t[2])):
            fresh = Message(
                kind=msg.kind,
                src=msg.src,
                dst=msg.dst,
                payload=copy.deepcopy(msg.payload),
                round_sent=msg.round_sent,
            )
            inboxes[dst].append(fresh)
            self._msg_total += 1
            self._by_kind[msg.kind] = self._by_kind.get(msg.kind, 0) + 1
            self._absorb(dst, fresh)
        delivered = sum(len(b) for b in inboxes.values())
        self._outq = []
        return inboxes, delivered

    def _absorb(self, dst: int, msg: Message) -> None:
        """Mesajın taşıdığı DURUM BEYANINI komşu kaydına yaz.

        Motor kaydı kendiliğinden tazelemez: buraya yazılan her şey gönderenin
        kendi yükünde beyan ettiğidir. Beyan eksikse eksik alanlar önceki
        kayıttan devralınır, hiç kayıt yoksa muhafazakâr varsayılan kullanılır.
        """
        src = msg.src
        pay = msg.payload or {}
        if msg.kind == api.TWO_HOP_DIGEST and isinstance(pay.get("digest"), list):
            self._absorb_digest(dst, msg)
        if not any(kk in pay for kk in STATE_KEYS):
            return
        old = self._known[dst].get(src)
        rec = _Rec(
            weight=float(pay.get("weight", old.weight if old else 0.0)),
            uncovered_degree=int(
                pay.get("uncovered_degree", old.uncovered_degree if old else 0)
            ),
            remaining_capacity=int(
                pay.get("remaining_capacity", old.remaining_capacity if old else 0)
            ),
            in_cover=bool(pay.get("in_cover", old.in_cover if old else False)),
            score=pay.get("score", old.score if old else None),
            round_sent=msg.round_sent,
            extra={kk: vv for kk, vv in pay.items() if kk not in STATE_KEYS},
        )
        if rec.score is not None and not isinstance(rec.score, tuple):
            rec.score = tuple(rec.score)
        self._known[dst][src] = rec

    def _absorb_digest(self, dst: int, msg: Message) -> None:
        """İki atlama özeti: komşunun beyan ettiği komşu listesi."""
        for ent in msg.payload.get("digest", []):
            if not isinstance(ent, dict):
                continue
            node = ent.get("node")
            if node is None or int(node) == dst:
                continue
            node = int(node)
            prev_via = self._via[dst].get(node)
            if prev_via is not None and prev_via < msg.src:
                continue  # en küçük röle kimliği kazanır -> belirlenimci
            self._two_hop[dst][node] = _Rec(
                weight=float(ent.get("weight", 0.0)),
                uncovered_degree=int(ent.get("uncovered_degree", 0)),
                remaining_capacity=int(ent.get("remaining_capacity", 0)),
                in_cover=bool(ent.get("in_cover", False)),
                score=tuple(ent["score"]) if ent.get("score") is not None else None,
                round_sent=msg.round_sent,
                extra={
                    kk: vv
                    for kk, vv in ent.items()
                    if kk not in STATE_KEYS and kk != "node"
                },
            )
            self._via[dst][node] = msg.src

    # ------------------------------------------------------------------
    # protokol çıktısı doğrulama (I3 burada zorlanır)
    # ------------------------------------------------------------------
    def _validate(
        self, v: int, out: Any, rnd: int
    ) -> Tuple[List[Message], NodeDecision]:
        if not (isinstance(out, tuple) and len(out) == 2):
            raise EngineViolation(f"düğüm {v}: on_round (mesajlar, karar) döndürmeli")
        msgs, dec = out
        if msgs is None:
            msgs = []
        if not isinstance(msgs, (list, tuple)):
            raise EngineViolation(f"düğüm {v}: mesaj listesi bekleniyor")
        if not isinstance(dec, NodeDecision):
            raise EngineViolation(f"düğüm {v}: NodeDecision bekleniyor")
        nbrs = set(self._adj[v])
        checked: List[Message] = []
        for m in msgs:
            if not isinstance(m, Message):
                raise EngineViolation(f"düğüm {v}: Message olmayan nesne gönderdi")
            if m.src != v:
                raise EngineViolation(
                    f"düğüm {v}: başkasının adına mesaj gönderemez (src={m.src})"
                )
            if m.dst is not None and m.dst not in nbrs:
                raise EngineViolation(
                    f"I3 ihlali: düğüm {v} komşusu olmayan {m.dst} düğümüne mesaj gönderdi"
                )
            checked.append(
                Message(
                    kind=m.kind,
                    src=m.src,
                    dst=m.dst,
                    payload=copy.deepcopy(m.payload),
                    round_sent=rnd,
                )
            )
        for fieldname in (
            "claim_edges",
            "release_edges",
            "accept_claims",
            "reject_claims",
        ):
            for o in getattr(dec, fieldname):
                if o not in nbrs:
                    raise EngineViolation(
                        f"düğüm {v}: {fieldname} içinde komşu olmayan {o} var"
                    )
        return checked, dec

    def _queue(self, v: int, msgs: List[Message]) -> int:
        """Mesajları bir sonraki tur için kuyrukla; yayını komşu başına aç."""
        sent = 0
        for idx, m in enumerate(msgs):
            if m.dst is None:
                for o in self._adj[v]:
                    self._outq.append((v, idx, o, m))
                    sent += 1
            else:
                self._outq.append((v, idx, m.dst, m))
                sent += 1
        return sent

    # ------------------------------------------------------------------
    # kararların uygulanması (I1, I2 burada zorlanır)
    # ------------------------------------------------------------------
    def _apply(self, dec: Dict[int, NodeDecision], rnd: int) -> Dict[str, int]:
        st = {
            "joined": 0,
            "left": 0,
            "leave_denied": 0,
            "claims": 0,
            "claims_dropped": 0,
            "claims_rejected": 0,
            "covered_now": 0,
            "released": 0,
            "cap_blocked": 0,
        }

        # --- 1) örtüye katılma (kimlik sırasıyla, sıradan bağımsız sonuç) ---
        for v in self._nodes:
            d = dec[v]
            if d.join_cover and v not in self._in_cover:
                self._in_cover.add(v)
                st["joined"] += 1

        # --- 2) serbest bırakma (sahiplikten vazgeçme) ---
        for v in self._nodes:
            for o in sorted(set(dec[v].release_edges)):
                e = edge_key(v, o)
                if self._owner[e] == v:
                    self._owner[e] = None
                    self._covered[e] = False
                    self._load[v] -= 1
                    st["released"] += 1
                elif self._pending[e] == v:
                    self._pending[e] = None

        # --- 3) bu turun talepleri ---
        claims_this: Dict[Edge, Set[int]] = {}
        for v in self._nodes:
            for o in sorted(set(dec[v].claim_edges)):
                e = edge_key(v, o)
                if self._covered[e]:
                    continue  # zaten örtülü, talep anlamsız
                if v not in self._in_cover:
                    st["claims_dropped"] += 1  # örtü dışı düğüm kenar sahiplenemez
                    continue
                claims_this.setdefault(e, set()).add(v)
                st["claims"] += 1

        # --- 4) açık redler: bekleyen ya da bu turki talebi düşürür ---
        rejected: Set[Tuple[Edge, int]] = set()
        for v in self._nodes:
            for o in sorted(set(dec[v].reject_claims)):
                e = edge_key(v, o)
                rejected.add((e, o))
                if self._pending[e] == o:
                    self._pending[e] = None
                    st["claims_rejected"] += 1
                if e in claims_this and o in claims_this[e]:
                    claims_this[e].discard(o)
                    st["claims_rejected"] += 1

        accepted: Set[Tuple[Edge, int]] = set()
        for v in self._nodes:
            for o in sorted(set(dec[v].accept_claims)):
                e = edge_key(v, o)
                if (e, o) not in rejected:  # aynı turda hem onay hem red -> red kazanır
                    accepted.add((e, o))

        # --- 5) I1: hangi kenar bu turda örtülebilir, tercih edilen sahip kim ---
        eligible: List[
            Tuple[int, int, Edge, Optional[int]]
        ] = []  # (pref, other, e, fallback)
        for e in self._edges:
            if self._covered[e]:
                continue
            u, v = e
            now = set(claims_this.get(e, ()))
            pend = self._pending[e]
            if pend is not None and pend not in now and (e, pend) not in rejected:
                now.add(pend)
            now = {x for x in now if x in self._in_cover}
            if not now:
                self._pending[e] = None  # talep sahibi çekildi ya da reddedildi
                continue

            if len(now) == 2:
                # (1) KARŞILIKLI TALEP -> küçük kimlik sahibi, dolu ise diğeri
                pref, fb = (u, v) if u < v else (v, u)
                eligible.append((pref, fb, e, fb))
                self._pending[e] = None
                continue

            c = next(iter(now))
            other = v if c == u else u
            if (e, c) in accepted:
                # (3) AÇIK ONAY (onaylayan karşı uçtur)
                eligible.append((c, other, e, None))
                self._pending[e] = None
            elif other not in self._in_cover and other not in claims_this.get(e, ()):
                # (2) İTİRAZSIZ TEK-UÇ TALEBİ
                eligible.append((c, other, e, None))
                self._pending[e] = None
            else:
                # anlaşma yok -> beklemede kalır, kenar ÖRTÜLÜ DEĞİL
                self._pending[e] = c

        # --- 6) I2: kapasiteyi zorlayarak sahiplik yaz ---
        for pref, other, e, fb in sorted(eligible, key=lambda t: (t[0], t[1])):
            winner = None
            if self._load[pref] < self._k:
                winner = pref
            elif fb is not None and fb in self._in_cover and self._load[fb] < self._k:
                winner = fb
            if winner is None:
                st["cap_blocked"] += 1
                self._pending[e] = None  # talep reddedildi; claimed_by_me düşer
                continue
            self._owner[e] = winner
            self._covered[e] = True
            self._load[winner] += 1
            st["covered_now"] += 1

        # --- 7) örtüden ayrılma: yalnız hiç kenar sahiplenmiyorsa ---
        for v in self._nodes:
            d = dec[v]
            if not d.leave_cover or v not in self._in_cover or d.join_cover:
                continue
            if self._load[v] > 0:
                st["leave_denied"] += 1
                continue
            self._in_cover.discard(v)
            for o in self._adj[v]:
                e = edge_key(v, o)
                if self._pending[e] == v:
                    self._pending[e] = None
            st["left"] += 1
        return st

    # ------------------------------------------------------------------
    # koşum
    # ------------------------------------------------------------------
    def run(self, protocol_factory, max_rounds: int = 200) -> RunResult:
        if max_rounds < 1:
            raise EngineViolation("max_rounds >= 1 olmalı")
        self._reset()
        protos: Dict[int, NodeProtocol] = {}
        for v in self._nodes:
            p = protocol_factory(v)
            if not isinstance(p, NodeProtocol):
                raise EngineViolation(
                    f"düğüm {v}: protocol_factory NodeProtocol vermeli"
                )
            p.on_start(v, float(self._g.weight[v]), self._k, len(self._adj[v]))
            protos[v] = p
        algo = self._algorithm
        if algo is None:
            algo = (
                getattr(protos[self._nodes[0]], "name", "unnamed")
                if self._nodes
                else "unnamed"
            )

        per_round: List[Dict[str, Any]] = []
        converged = False
        rounds_done = 0
        for rnd in range(max_rounds):
            inboxes, delivered = self._deliver(rnd)
            views = {v: self._build_view(v, rnd, inboxes[v]) for v in self._nodes}
            # ÖNCE hepsi toplanır, SONRA uygulanır -> yoklama sırası sonucu değiştiremez
            outs: Dict[int, Tuple[List[Message], NodeDecision]] = {}
            for v in self._poll:
                outs[v] = self._validate(v, protos[v].on_round(views[v]), rnd)
            decisions = {v: outs[v][1] for v in self._nodes}
            st = self._apply(decisions, rnd)
            sent = 0
            for v in self._nodes:  # kuyruklama da kimlik sırasıyla
                sent += self._queue(v, outs[v][0])
            quiet = sum(1 for v in self._nodes if decisions[v].quiescent)
            rounds_done = rnd + 1
            row = {
                "round": rnd,
                "delivered": delivered,
                "sent": sent,
                "quiescent": quiet,
                "nodes": len(self._nodes),
                "cover_size": len(self._in_cover),
                "uncovered_edges": sum(1 for e in self._edges if not self._covered[e]),
                "in_flight": len(self._outq),
            }
            row.update(st)
            per_round.append(row)
            if quiet == len(self._nodes) and not self._outq:
                converged = True
                break

        cover = sorted(self._in_cover)
        owner = {e: o for e, o in self._owner.items() if o is not None}
        notes = list(self._notes)
        if not converged:
            notes.append(f"max_rounds={max_rounds} aşıldı, düğümler quiescent olmadı")
        if self._outq:
            notes.append(
                f"teslim edilmeden kalan mesaj: {len(self._outq)} (sayıma girmedi)"
            )
        open_edges = sum(1 for e in self._edges if not self._covered[e])
        notes.append(
            f"motor defteri: {len(self._edges) - open_edges}/{len(self._edges)} kenar iki uç anlaşmasıyla sahiplendi"
        )
        verdict = verify(self._g, cover)
        notes.append(f"verify: {verdict.as_dict()}")
        if not verdict.valid:
            notes.append(
                "UYARI: çözüm doğruluk kapılarından geçmedi "
                f"(örtü={verdict.vertex_cover}, bağlı={verdict.connected}, "
                f"kapasite={verdict.capacity_feasible}) — protokolün sonucu, motor hatası değil"
            )
        return RunResult(
            algorithm=algo or "unnamed",
            cover=cover,
            owner=owner,
            rounds=rounds_done,
            messages=self._msg_total,
            messages_by_kind=dict(sorted(self._by_kind.items())),
            converged=converged,
            per_round=per_round,
            notes=notes,
        )


def run_protocol(
    graph: CcvcGraph,
    protocol_factory,
    max_rounds: int = 200,
    poll_order: Optional[Sequence[int]] = None,
    algorithm: Optional[str] = None,
) -> RunResult:
    """Tek çağrılık kolaylık sarmalayıcısı."""
    return RoundEngine(graph, poll_order=poll_order, algorithm=algorithm).run(
        protocol_factory, max_rounds=max_rounds
    )
