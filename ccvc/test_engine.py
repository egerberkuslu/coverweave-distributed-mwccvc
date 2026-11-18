#!/usr/bin/env python3
"""Tur motoru testleri (F2).

Koşum:  python3 -m pytest ccvc/test_engine.py -q   (depo kökünden)

Testlerin amacı motorun sözleşmeyi GERÇEKTEN zorladığını göstermek: düğüm
küresel çizgeyi göremez, komşu olmayana mesaj gidemez, kapasite aşılamaz,
kenar iki uç anlaşmadan örtülü işaretlenemez, sonuç yoklama sırasından
bağımsızdır ve mesaj sayımı elle hesapla birebir tutar.
"""
from __future__ import annotations

import random
from typing import List, Tuple

import pytest

try:
    from ccvc.bridge import CcvcGraph, edge_key
    from ccvc.engine import EngineViolation, RoundEngine
    from ccvc.engine_api import (
        CAPACITY_STATE,
        COVER_INTENT,
        EDGE_CLAIM,
        LocalView,
        Message,
        NodeDecision,
        NodeProtocol,
    )
except ImportError:  # pragma: no cover
    from bridge import CcvcGraph, edge_key  # type: ignore
    from engine import EngineViolation, RoundEngine  # type: ignore
    from engine_api import (  # type: ignore
        CAPACITY_STATE,
        COVER_INTENT,
        EDGE_CLAIM,
        LocalView,
        Message,
        NodeDecision,
        NodeProtocol,
    )


# --------------------------------------------------------------------------
# çizge kurucuları
# --------------------------------------------------------------------------
def make_graph(edges, n=None, k=2, weight=None) -> CcvcGraph:
    edges = sorted({edge_key(u, v) for u, v in edges})
    if n is None:
        n = (max((max(e) for e in edges), default=-1)) + 1
    nodes = list(range(n))
    w = weight or {v: 1.0 for v in nodes}
    return CcvcGraph(nodes=nodes, edges=list(edges), weight=w, capacity_k=k)


def path_with_isolate() -> CcvcGraph:
    """0-1-2-3 yolu + yalıtık 4 (PLAN §0.5: çizge çoğu karede kopuk)."""
    return make_graph([(0, 1), (1, 2), (2, 3)], n=5, k=2)


def star(leaves: int = 5, k: int = 2) -> CcvcGraph:
    return make_graph([(0, i) for i in range(1, leaves + 1)], k=k)


# --------------------------------------------------------------------------
# test protokolleri
# --------------------------------------------------------------------------
class JoinAndHush(NodeProtocol):
    """Kenarı olan herkes hemen örtüye katılır, hiç talep etmez, hiç konuşmaz."""

    name = "join-and-hush"

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        dec = NodeDecision(join_cover=bool(view.incident) and not view.in_cover)
        dec.quiescent = True
        return [], dec


class JoinAndShout(JoinAndHush):
    """Aynısı ama tur 0'da bir kez komşularına yayın yapar."""

    name = "join-and-shout"

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        msgs, dec = [], NodeDecision(
            join_cover=bool(view.incident) and not view.in_cover
        )
        dec.quiescent = True
        if view.round == 0 and view.incident:
            msgs.append(
                Message(
                    kind=COVER_INTENT,
                    src=view.me,
                    dst=None,
                    payload={
                        "weight": view.weight,
                        "uncovered_degree": view.uncovered_degree(),
                        "remaining_capacity": view.remaining_capacity,
                        "in_cover": True,
                    },
                )
            )
        return msgs, dec


class TalksToStranger(NodeProtocol):
    """I3 ihlali: komşusu olmayan bir düğüme mesaj yollar."""

    name = "stranger"

    def __init__(self, target: int) -> None:
        self.target = target

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        dec = NodeDecision(quiescent=True)
        if view.me == 0 and view.round == 0:
            return [Message(COVER_INTENT, 0, self.target, {})], dec
        return [], dec


class GreedyOverClaimer(NodeProtocol):
    """Merkez düğüm bütün kenarlarını tek turda talep eder (k'dan fazla)."""

    name = "over-claimer"

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        dec = NodeDecision(quiescent=True)
        if view.round == 0 and len(view.incident) > view.capacity_k:
            dec.join_cover = True
            dec.claim_edges = sorted(view.incident)  # kapasitenin çok üstünde
        return [], dec


class BothClaim(NodeProtocol):
    """Her iki uç da aynı kenarı aynı turda talep eder."""

    name = "both-claim"

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        dec = NodeDecision(quiescent=True)
        if view.round == 0 and view.incident:
            dec.join_cover = True
            dec.claim_edges = sorted(view.incident)
        return [], dec


class EvenRoundTalker(NodeProtocol):
    """0 düğümü yalnız ÇİFT turlarda konuşur; 1 düğümü komşu yaşını kaydeder."""

    name = "even-talker"

    def __init__(self, me: int, log: dict) -> None:
        self.me = me
        self.log = log

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        dec = NodeDecision(quiescent=False)  # hiç susmaz, max_rounds'a kadar koşar
        rec = view.neighbors.get(0)
        if view.me == 1:
            self.log[view.round] = None if rec is None else (rec.age_rounds, rec.stale)
        if view.me == 0 and view.round % 2 == 0:
            return (
                [
                    Message(
                        CAPACITY_STATE,
                        0,
                        None,
                        {
                            "weight": view.weight,
                            "uncovered_degree": view.uncovered_degree(),
                            "remaining_capacity": view.remaining_capacity,
                            "in_cover": view.in_cover,
                        },
                    )
                ],
                dec,
            )
        return [], dec


class NeverQuiet(NodeProtocol):
    """Hiç quiescent olmaz, hiç mesaj atmaz: max_rounds'a çarpmalı."""

    name = "never-quiet"

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        return [], NodeDecision(quiescent=False)


class ViewVandal(NodeProtocol):
    """Verilen görüşü tahrip eder. Motorun gerçek durumu etkilenmemeli."""

    name = "vandal"

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        for el in view.incident.values():
            el.covered = True
            el.owner = view.me
            el.claimed_by_me = True
        view.incident.clear()
        view.neighbors.clear()
        view.inbox.clear()
        return [], NodeDecision(quiescent=True)


class MiniGreedy(NodeProtocol):
    """Yerel-maksimum kuralıyla katılan, claim/ack ile uzlaşan küçük protokol.

    Gerçekçi trafik üretmesi için var: belirlenimcilik ve sıra bağımsızlığı
    testleri bunun üstünde koşuyor.
    """

    name = "mini-greedy"

    def on_round(self, view: LocalView) -> Tuple[List[Message], NodeDecision]:
        dec = NodeDecision()
        unc = view.uncovered_incident()
        my = (view.weight, float(view.me))
        for m in view.messages_of(EDGE_CLAIM):
            if m.src in view.incident:
                dec.accept_claims.append(m.src)
        if unc:
            better = any(
                view.neighbors[o].score is not None
                and tuple(view.neighbors[o].score) < my
                for o in unc
                if o in view.neighbors
            )
            if not better and not view.in_cover:
                dec.join_cover = True
            if view.in_cover or dec.join_cover:
                dec.claim_edges = unc[: max(0, view.remaining_capacity)]
        dec.quiescent = not unc and not dec.accept_claims
        msgs: List[Message] = []
        if not dec.quiescent:
            msgs.append(
                Message(
                    COVER_INTENT,
                    view.me,
                    None,
                    {
                        "weight": view.weight,
                        "uncovered_degree": len(unc),
                        "remaining_capacity": view.remaining_capacity,
                        "in_cover": view.in_cover or dec.join_cover,
                        "score": my,
                    },
                )
            )
            for o in dec.claim_edges:
                msgs.append(Message(EDGE_CLAIM, view.me, o, {"edge": o}))
        return msgs, dec


# --------------------------------------------------------------------------
# 1. sessiz protokol: tek tur, sıfır mesaj, örtü = yalıtık olmayan düğümler
# --------------------------------------------------------------------------
def test_silent_join_terminates_with_zero_messages():
    g = path_with_isolate()
    res = RoundEngine(g).run(lambda v: JoinAndHush(), max_rounds=10)
    assert res.converged is True
    assert res.rounds == 1
    assert res.messages == 0
    assert res.messages_by_kind == {}
    assert res.cover == [0, 1, 2, 3]  # 4 yalıtık, örtüye girmez
    assert res.owner == {}  # hiç talep yok -> motor defterinde sahip yok
    assert any("verify" in n for n in res.notes)


def test_round_zero_view_knows_only_itself():
    """Tur 0'da düğüm kendi kimliğini/derecesini bilir, komşu durumunu bilmez."""
    seen = {}

    class Peek(NodeProtocol):
        name = "peek"

        def on_round(self, view):
            if view.round == 0:
                seen[view.me] = (
                    sorted(view.incident),
                    dict(view.neighbors),
                    view.in_cover,
                    view.remaining_capacity,
                    view.capacity_k,
                    view.weight,
                )
            return [], NodeDecision(quiescent=True)

    g = path_with_isolate()
    RoundEngine(g).run(lambda v: Peek(), max_rounds=3)
    assert seen[1][0] == [0, 2]  # kendi kenarlarını bilir
    assert seen[1][1] == {}  # komşu kaydı YOK
    assert seen[1][2] is False
    assert seen[1][3] == g.capacity_k == seen[1][4]
    assert seen[4][0] == []  # yalıtık düğümün kenarı yok


def test_broadcast_message_count_matches_hand_computation():
    """Yayın = derece kadar mesaj. 3 kenarlı yol -> 2|E| = 6 teslim."""
    g = path_with_isolate()
    res = RoundEngine(g).run(lambda v: JoinAndShout(), max_rounds=10)
    assert res.converged is True
    assert res.rounds == 2  # tur 0 gönderir, tur 1 teslim alır ve susar
    assert res.messages == 2 * len(g.edges) == 6
    assert res.messages_by_kind == {COVER_INTENT: 6}
    assert [row["delivered"] for row in res.per_round] == [0, 6]
    assert [row["sent"] for row in res.per_round] == [6, 0]


def test_neighbour_record_appears_only_after_neighbour_speaks():
    log = {}

    class Watcher(JoinAndShout):
        name = "watcher"

        def on_round(self, view):
            log.setdefault(view.me, {})[view.round] = sorted(view.neighbors)
            return super().on_round(view)

    g = path_with_isolate()
    RoundEngine(g).run(lambda v: Watcher(), max_rounds=5)
    assert log[1][0] == []  # tur 0: kimse konuşmadı
    assert log[1][1] == [0, 2]  # tur 1: tur 0 yayınları teslim edildi


# --------------------------------------------------------------------------
# 2. I3 — komşu olmayana mesaj
# --------------------------------------------------------------------------
def test_message_to_non_neighbour_raises():
    g = path_with_isolate()  # 0'ın komşusu yalnız 1
    with pytest.raises(EngineViolation) as ei:
        RoundEngine(g).run(lambda v: TalksToStranger(3), max_rounds=5)
    assert "I3" in str(ei.value)


def test_message_to_isolated_node_raises():
    g = path_with_isolate()
    with pytest.raises(EngineViolation):
        RoundEngine(g).run(lambda v: TalksToStranger(4), max_rounds=5)


def test_forged_sender_raises():
    class Forger(NodeProtocol):
        name = "forger"

        def on_round(self, view):
            if view.me == 1 and view.round == 0:
                return [Message(COVER_INTENT, 0, 2, {})], NodeDecision(quiescent=True)
            return [], NodeDecision(quiescent=True)

    with pytest.raises(EngineViolation):
        RoundEngine(path_with_isolate()).run(lambda v: Forger(), max_rounds=3)


def test_decision_about_non_neighbour_raises():
    class BadClaim(NodeProtocol):
        name = "bad-claim"

        def on_round(self, view):
            dec = NodeDecision(quiescent=True)
            if view.me == 0 and view.round == 0:
                dec.join_cover = True
                dec.claim_edges = [3]  # 0'ın komşusu değil
            return [], dec

    with pytest.raises(EngineViolation):
        RoundEngine(path_with_isolate()).run(lambda v: BadClaim(), max_rounds=3)


# --------------------------------------------------------------------------
# 3. I2 — kapasite
# --------------------------------------------------------------------------
def test_over_claim_is_capped_at_k():
    g = star(leaves=5, k=2)
    res = RoundEngine(g).run(lambda v: GreedyOverClaimer(), max_rounds=5)
    mine = [e for e, o in res.owner.items() if o == 0]
    assert len(mine) == 2  # k=2, beşi birden değil
    assert sorted(mine) == [(0, 1), (0, 2)]  # komşu kimliğine göre belirlenimci
    assert res.per_round[0]["cap_blocked"] == 3
    assert res.converged is True


def test_capacity_never_exceeded_in_any_run():
    g = make_graph([(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)], k=2)
    res = RoundEngine(g).run(lambda v: MiniGreedy(), max_rounds=60)
    load = {}
    for _, o in res.owner.items():
        load[o] = load.get(o, 0) + 1
    assert all(c <= g.capacity_k for c in load.values())


# --------------------------------------------------------------------------
# 4. I1 — kenar iki uç anlaşmadan örtülmez
# --------------------------------------------------------------------------
def test_same_edge_claimed_by_both_endpoints_one_winner():
    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: BothClaim(), max_rounds=5)
    assert res.owner == {(0, 1): 0}  # küçük kimlik kazanır
    again = RoundEngine(g).run(lambda v: BothClaim(), max_rounds=5)
    assert again.owner == res.owner  # yeniden koşumda aynı kazanan


def test_double_claim_falls_back_when_winner_is_full():
    """Küçük kimlik doluysa kenar diğer uca düşer, kaybolmaz."""
    g = make_graph([(0, 1), (0, 2), (0, 3)], k=1)

    class Claimer(NodeProtocol):
        name = "claimer"

        def on_round(self, view):
            dec = NodeDecision(quiescent=True)
            if view.round == 0 and view.incident:
                dec.join_cover = True
                dec.claim_edges = sorted(view.incident)
            return [], dec

    res = RoundEngine(g).run(lambda v: Claimer(), max_rounds=5)
    assert res.owner[(0, 1)] == 0  # 0 tek kapasitesini en küçük komşuya harcar
    assert res.owner[(0, 2)] == 2  # 0 doldu -> karşı uca düştü
    assert res.owner[(0, 3)] == 3


def test_uncontested_claim_needs_claimer_in_cover():
    """Örtüde olmayan düğümün talebi düşer, kenar örtülü olmaz."""

    class ClaimWithoutJoining(NodeProtocol):
        name = "no-join"

        def on_round(self, view):
            dec = NodeDecision(quiescent=True)
            if view.round == 0 and view.me == 0:
                dec.claim_edges = sorted(view.incident)  # join_cover YOK
            return [], dec

    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: ClaimWithoutJoining(), max_rounds=5)
    assert res.owner == {}
    assert res.cover == []
    assert res.per_round[0]["claims_dropped"] == 1


def test_claim_against_cover_member_waits_for_explicit_accept():
    """Karşı uç da örtüdeyse kenar ONAY gelene kadar örtülü sayılmaz (I1)."""
    covered_at = {}

    class ClaimThenAccept(NodeProtocol):
        name = "claim-then-accept"

        def on_round(self, view):
            dec = NodeDecision()
            msgs = []
            if view.round == 0:
                dec.join_cover = True  # iki uç da örtüye girer
            if view.round == 1 and view.me == 0:
                dec.claim_edges = [1]
                msgs.append(Message(EDGE_CLAIM, 0, 1, {}))
            if view.me == 1 and view.messages_of(EDGE_CLAIM):
                dec.accept_claims = [m.src for m in view.messages_of(EDGE_CLAIM)]
            covered_at[(view.me, view.round)] = view.incident[1 - view.me].covered
            dec.quiescent = view.round >= 3
            return msgs, dec

    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: ClaimThenAccept(), max_rounds=8)
    # tur 1'de talep var ama onay yok -> tur 2 başında hâlâ örtülü değil
    assert covered_at[(0, 2)] is False
    assert covered_at[(1, 2)] is False
    # onay tur 2'de verilir -> tur 3'te görülür
    assert covered_at[(0, 3)] is True
    assert res.owner == {(0, 1): 0}


def test_explicit_reject_beats_accept_and_keeps_edge_uncovered():
    class ClaimThenReject(NodeProtocol):
        name = "claim-then-reject"

        def on_round(self, view):
            dec = NodeDecision(quiescent=view.round >= 3)
            msgs = []
            if view.round == 0:
                dec.join_cover = True
            if view.round == 1 and view.me == 0:
                dec.claim_edges = [1]
                msgs.append(Message(EDGE_CLAIM, 0, 1, {}))
            if view.me == 1 and view.messages_of(EDGE_CLAIM):
                srcs = [m.src for m in view.messages_of(EDGE_CLAIM)]
                dec.accept_claims = list(srcs)
                dec.reject_claims = list(srcs)  # çelişki -> red kazanmalı
            return msgs, dec

    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: ClaimThenReject(), max_rounds=8)
    assert res.owner == {}


def test_leave_cover_denied_while_owning_edges():
    class JoinClaimLeave(NodeProtocol):
        name = "join-claim-leave"

        def on_round(self, view):
            dec = NodeDecision(quiescent=view.round >= 3)
            if view.round == 0 and view.me == 0:
                dec.join_cover = True
                dec.claim_edges = [1]
            if view.round == 2 and view.me == 0:
                dec.leave_cover = True
            return [], dec

    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: JoinClaimLeave(), max_rounds=8)
    assert res.cover == [0]  # ayrılma reddedildi
    assert res.per_round[2]["leave_denied"] == 1
    assert res.owner == {(0, 1): 0}


def test_release_then_leave_is_allowed():
    class JoinClaimReleaseLeave(NodeProtocol):
        name = "release-leave"

        def on_round(self, view):
            dec = NodeDecision(quiescent=view.round >= 4)
            if view.me != 0:
                return [], dec
            if view.round == 0:
                dec.join_cover = True
                dec.claim_edges = [1]
            if view.round == 2:
                dec.release_edges = [1]
            if view.round == 3:
                dec.leave_cover = True
            return [], dec

    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: JoinClaimReleaseLeave(), max_rounds=8)
    assert res.cover == []
    assert res.owner == {}


# --------------------------------------------------------------------------
# 5. eskime
# --------------------------------------------------------------------------
def test_staleness_grows_when_neighbour_stays_silent():
    """0 yalnız çift turlarda konuşur.

    r turunda gönderilen r+1'de teslim edilir, yani teslim turunda kayıt tam
    1 turluktur (taze). Bir tur daha susarsa yaş 2 olur ve kayıt bayatlar.
    """
    log = {}
    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: EvenRoundTalker(v, log), max_rounds=7)
    assert res.converged is False  # hiçbiri quiescent değil
    assert log[0] is None  # tur 0: hiç kayıt yok
    assert log[1] == (1, False)  # tur 0 yayını, 1 turluk, taze
    assert log[2] == (2, True)  # bir tur sessizlik -> BAYAT
    assert log[3] == (1, False)
    assert log[4] == (2, True)
    assert log[5] == (1, False)
    assert log[6] == (2, True)
    assert any(a > 1 for a, _ in (x for x in log.values() if x is not None))


def test_neighbour_record_carries_only_declared_state():
    """Motor kaydı küresel durumdan tazelemez; yalnız yükte beyan edileni yazar."""
    seen = {}

    class Liar(NodeProtocol):
        name = "liar"

        def on_round(self, view):
            dec = NodeDecision(quiescent=view.round >= 2)
            if view.me == 1 and view.round == 1:
                seen["rec"] = view.neighbors.get(0)
            if view.me == 0 and view.round == 0:
                return (
                    [
                        Message(
                            CAPACITY_STATE,
                            0,
                            None,
                            {"weight": 99.0, "remaining_capacity": 7, "in_cover": True},
                        )
                    ],
                    dec,
                )
            return [], dec

    g = make_graph([(0, 1)], k=2, weight={0: 1.0, 1: 1.0})
    RoundEngine(g).run(lambda v: Liar(), max_rounds=6)
    rec = seen["rec"]
    assert rec is not None
    assert rec.weight == 99.0  # gerçek ağırlık 1.0; motor beyanı yazar, düzeltmez
    assert rec.remaining_capacity == 7
    assert rec.in_cover is True


# --------------------------------------------------------------------------
# 6. belirlenimcilik ve sıra bağımsızlığı
# --------------------------------------------------------------------------
def mesh_graph(k: int = 3) -> CcvcGraph:
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (1, 3), (5, 6), (6, 7), (5, 7)]
    w = {v: float(1 + (v * 7) % 5) for v in range(9)}  # 8 yalıtık
    return make_graph(edges, n=9, k=k, weight=w)


def _snapshot(res):
    return (
        res.rounds,
        res.messages,
        tuple(sorted(res.messages_by_kind.items())),
        tuple(res.cover),
        tuple(sorted(res.owner.items())),
        res.converged,
        tuple(tuple(sorted(row.items())) for row in res.per_round),
    )


def test_same_run_twice_is_identical():
    g = mesh_graph()
    a = RoundEngine(g).run(lambda v: MiniGreedy(), max_rounds=60)
    b = RoundEngine(g).run(lambda v: MiniGreedy(), max_rounds=60)
    assert _snapshot(a) == _snapshot(b)


def test_engine_instance_can_be_rerun_cleanly():
    g = mesh_graph()
    eng = RoundEngine(g)
    a = eng.run(lambda v: MiniGreedy(), max_rounds=60)
    b = eng.run(lambda v: MiniGreedy(), max_rounds=60)
    assert _snapshot(a) == _snapshot(b)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_poll_order_does_not_change_outcome(seed):
    g = mesh_graph()
    base = RoundEngine(g).run(lambda v: MiniGreedy(), max_rounds=60)
    order = sorted(g.nodes)
    random.Random(seed).shuffle(order)
    shuffled = RoundEngine(g, poll_order=order).run(
        lambda v: MiniGreedy(), max_rounds=60
    )
    assert _snapshot(shuffled) == _snapshot(base)


def test_poll_order_must_be_a_permutation():
    with pytest.raises(EngineViolation):
        RoundEngine(mesh_graph(), poll_order=[0, 1])


# --------------------------------------------------------------------------
# 7. sonlanma
# --------------------------------------------------------------------------
def test_never_quiescent_hits_max_rounds():
    g = path_with_isolate()
    res = RoundEngine(g).run(lambda v: NeverQuiet(), max_rounds=7)
    assert res.converged is False
    assert res.rounds == 7
    assert res.messages == 0
    assert any("max_rounds" in n for n in res.notes)


def test_engine_does_not_stop_just_because_all_edges_are_covered():
    """Kenarlar tur 0'da örtülür ama düğümler tur 3'e kadar quiescent demez."""

    class LateQuiet(NodeProtocol):
        name = "late-quiet"

        def on_round(self, view):
            dec = NodeDecision(quiescent=view.round >= 3)
            if view.round == 0 and view.me == 0 and view.incident:
                dec.join_cover = True
                dec.claim_edges = sorted(view.incident)
            return [], dec

    g = star(leaves=2, k=2)
    res = RoundEngine(g).run(lambda v: LateQuiet(), max_rounds=20)
    assert res.per_round[0]["uncovered_edges"] == 0  # tur 0 sonunda hepsi örtülü
    assert res.rounds == 4  # yine de 0..3 turları koşuldu
    assert res.converged is True


def test_messages_in_flight_block_convergence():
    """Herkes quiescent ama mesaj yolda -> tur daha koşulur."""
    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: JoinAndShout(), max_rounds=10)
    assert res.per_round[0]["quiescent"] == len(g.nodes)
    assert res.per_round[0]["in_flight"] == 2
    assert res.rounds == 2


# --------------------------------------------------------------------------
# 8. yalıtım: görüş tahribi motoru bozmaz, küresel bilgi sızmaz
# --------------------------------------------------------------------------
def test_mutating_the_view_cannot_corrupt_engine_state():
    g = mesh_graph()
    res = RoundEngine(g).run(lambda v: ViewVandal(), max_rounds=5)
    assert res.owner == {}  # görüşte covered=True yazmak gerçeği değiştirmez
    assert res.cover == []
    assert res.per_round[-1]["uncovered_edges"] == len(g.edges)


def test_local_view_exposes_no_global_handles():
    grabbed = {}

    class Snoop(NodeProtocol):
        name = "snoop"

        def on_round(self, view):
            grabbed[view.me] = view
            return [], NodeDecision(quiescent=True)

    g = mesh_graph()
    RoundEngine(g).run(lambda v: Snoop(), max_rounds=3)
    v = grabbed[1]
    assert set(vars(v)) == {
        "me",
        "round",
        "weight",
        "capacity_k",
        "remaining_capacity",
        "in_cover",
        "incident",
        "neighbors",
        "inbox",
        "two_hop",
        "via",
    }
    assert set(v.incident) <= set(g.adj[1])  # yalnız kendi komşuları
    for other in grabbed.values():
        if other is not v:
            assert other.incident is not v.incident  # paylaşılan nesne yok


def test_inbox_messages_are_private_copies():
    payloads = {}

    class Tamper(NodeProtocol):
        name = "tamper"

        def on_round(self, view):
            for m in view.inbox:
                payloads.setdefault(view.me, []).append(dict(m.payload))
                m.payload["weight"] = -1.0  # bir alıcı yükü bozarsa
            if view.round == 0 and view.incident:
                return (
                    [Message(COVER_INTENT, view.me, None, {"weight": view.weight})],
                    NodeDecision(quiescent=True),
                )
            return [], NodeDecision(quiescent=True)

    g = star(leaves=3, k=3)
    RoundEngine(g).run(lambda v: Tamper(), max_rounds=5)
    # merkez, üç yaprağın bozulmamış yüklerini görmeli
    assert payloads[0] == [{"weight": 1.0}, {"weight": 1.0}, {"weight": 1.0}]


# --------------------------------------------------------------------------
# 9. doğrulama kapısı sonuca iliştirilir
# --------------------------------------------------------------------------
def test_verdict_is_attached_even_when_cover_is_invalid():
    g = path_with_isolate()
    res = RoundEngine(g).run(lambda v: NeverQuiet(), max_rounds=3)
    assert res.cover == []
    joined = " ".join(res.notes)
    assert "verify" in joined
    assert "'vertex_cover': False" in joined
    assert "UYARI" in joined  # kötü protokol dürüstçe raporlanır, çökme yok


def test_valid_cover_passes_all_three_gates():
    g = path_with_isolate()
    res = RoundEngine(g).run(lambda v: JoinAndHush(), max_rounds=5)
    joined = " ".join(res.notes)
    assert "'valid': True" in joined
    assert "UYARI" not in joined


def test_as_dict_reports_real_counts():
    g = path_with_isolate()
    res = RoundEngine(g).run(lambda v: JoinAndShout(), max_rounds=10)
    d = res.as_dict()
    assert d["messages"] == 6
    assert d["cover_size"] == 4
    assert d["algorithm"] == "join-and-shout"
    assert d["converged"] is True


def test_undelivered_messages_are_not_counted_but_are_reported():
    """max_rounds'ta yolda kalan mesaj sayıma girmez; sayım teslim edilendir."""

    class ChatterBox(NodeProtocol):
        name = "chatter"

        def on_round(self, view):
            msgs = []
            if view.incident:
                msgs.append(
                    Message(COVER_INTENT, view.me, None, {"weight": view.weight})
                )
            return msgs, NodeDecision(quiescent=False)

    g = make_graph([(0, 1)], k=2)
    res = RoundEngine(g).run(lambda v: ChatterBox(), max_rounds=4)
    assert res.converged is False
    # 4 tur gönderir (tur başına 2), son turunki teslim edilmez -> 6 teslim
    assert res.messages == 6
    assert any("teslim edilmeden kalan mesaj: 2" in n for n in res.notes)
