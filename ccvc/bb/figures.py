#!/usr/bin/env python3
"""BB-CVC şekilleri: brief §8'in yedi şekli, HER BİRİ GERÇEK KOŞUMDAN.

Brief: `plan/MWCCVC_DAGITIK_TASARIM_BRIEF.md` §8. Veri kaynağı yalnız
`bbcvc.run_bbcvc(...) -> BbcvcRun` ve doğrulayıcıdır; bu dosyada elle yazılmış
tek bir ölçüm sayısı yoktur.

DÖRT İLKE
---------
1. **Kırmızı yalnız ihlal listesinden gelir.** Şekil 2 hiçbir kusuru kendisi
   hesaplamaz; `validate.validate(...)` çağırır ve ihlal listesini gezer. Her
   ihlal TAM OLARAK BİR kırmızı çizere dönüşür, dolayısıyla
   `count_violation_artists(fig) == len(report.violations)` bir SÖZLEŞMEDİR ve
   testte assert edilir. Şekli süs olmaktan çıkarıp kanıt yapan budur: geçerli
   bir çözümde kırmızı olamaz, çünkü çizilecek ihlal yoktur.
2. **Gri tonlamada okunur.** Rol yalnız renkle değil, AYRICA şekil (daire /
   kare / baklava) ve tarama deseniyle ayrılır; makale gri basılırsa bilgi
   kaybolmaz.
3. **Belirlenimci.** Yerleşim ya `.tex`ten gelen sabit koordinatlardır ya da
   tohumsuz (çemberden başlayan) bir Fruchterman-Reingold'dur. Aynı koşum aynı
   baytları üretir; SVG'ye tarih gömülmez.
4. **Tarihçe günlükten TÜRETİLİR, yeniden koşumdan değil.** Rol değişiklikleri
   `SimNet.log_records` içinde zaman damgasıyla durur (`mis_decided`,
   `connector`, `cover`, `joined`, `reset_phase0`). Roller monoton olduğundan
   (api I5) faz sonu durumu, o faza AİT olayların uygulanmasıyla TAM olarak
   yeniden kurulur; zaman damgasına yuvarlama yapılmaz.

VERİ BOŞLUĞU (şekil 5, rapor edildi)
------------------------------------
`Counters` faz × tip çapraz tablosunu tutmaz: `by_type_tx`, `by_type_rx` ve
`by_phase_tx` vardır; `by_phase_rx` ve bayt kırılımı YOKTUR. Tip başına bayt
burada TÜRETİLİR ve bu türetme kesindir, çünkü HELLO dışındaki her tip sabit
boyutludur (`wire.sizes()`): HELLO baytı = toplam − Σ(sabit boy × tip sayısı).
Faz başına bayt ve faz başına rx türetilemez; şekil 5 bunları ÇİZMEZ, eksikliği
yazar.
"""
from __future__ import annotations

import math
import os
import statistics
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")  # başsız; brief §11 etkileşimli görselleştirmeyi dışlar

import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import validate, wire  # noqa: E402
from ccvc.bb.api import MAX_PAYLOAD, MsgType, Role  # noqa: E402
from ccvc.bb.bbcvc import (JOIN_CONNECTOR, JOIN_ESCALATE, JOIN_FORCED,  # noqa: E402
                           PHASE_NAMES, BbcvcRun)

# SVG içindeki kimlik karmaları tohuma bağlıdır; sabitlenmezse aynı şekil iki
# farklı bayt dizisi üretir ve "aynı koşum aynı şekil" savı çöker.
matplotlib.rcParams["svg.hashsalt"] = "bb-cvc"
matplotlib.rcParams["figure.dpi"] = 110
matplotlib.rcParams["savefig.dpi"] = 160
matplotlib.rcParams["font.size"] = 9
matplotlib.rcParams["axes.grid"] = False

Edge = Tuple[int, int]
Pos = Dict[int, Tuple[float, float]]

#: İhlal rengi. Şekillerde BAŞKA HİÇBİR ŞEY bu rengi kullanmaz (ilke 1).
RED = "#c0202a"

#: Çizer etiketi: ihlalden doğan her çizer bu önekle işaretlenir.
VIOL_GID = "viol:"

#: Rol stilleri. Renk TEK AYIRT EDİCİ DEĞİLDİR (ilke 2): işaret ve tarama da
#: ayrışır. "C dışı düğüm içi boş" (brief §8/1) OUT'un beyaz dolgusudur.
ROLE_STYLE: Dict[Role, Dict[str, Any]] = {
    Role.OUT:       {"face": "#ffffff", "edge": "#4d4d4d", "hatch": "",
                     "marker": "o", "label": "OUT (C dışı, içi boş)"},
    Role.MIS:       {"face": "#1a1a1a", "edge": "#000000", "hatch": "",
                     "marker": "s", "label": "MIS (omurga)"},
    Role.CONNECTOR: {"face": "#8c8c8c", "edge": "#000000", "hatch": "///",
                     "marker": "D", "label": "CONNECTOR (omurga)"},
    Role.COVER:     {"face": "#dcdcdc", "edge": "#000000", "hatch": "..",
                     "marker": "o", "label": "COVER"},
}

#: Faz adları, şekil 3 ve 4 başlıkları için.
ALGO_PHASES: Dict[int, str] = {
    1: "Faz 1: omurga (MIS + connector)",
    2: "Faz 2: örtü genişletme",
    3: "Faz 3: kapasite onarımı",
    4: "Faz 4: esnek kenar sahipliği",
}

# --------------------------------------------------------------------------
# .tex'in çalışan örneği (10 düğüm, 15 kenar, k=2) — FIXTURE, ÖLÇÜM DEĞİL
# --------------------------------------------------------------------------
WORKED_EDGES: List[Edge] = [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (4, 5),
                            (4, 6), (5, 6), (5, 7), (6, 7), (7, 8), (7, 9),
                            (8, 9), (8, 10), (9, 10)]
WORKED_WEIGHTS: Dict[int, float] = {1: 5, 2: 2, 3: 4, 4: 3, 5: 6,
                                    6: 2, 7: 3, 8: 2, 9: 5, 10: 4}
WORKED_K = 2

#: `plan/BB-CVC_Algoritma_Ornekli_Anlatim.tex` \exgraph komutundaki tikz
#: koordinatları. Şekil 1 belgedeki resimle ÜST ÜSTE binsin diye aynen alındı.
WORKED_POS: Pos = {1: (0.0, 2.0), 2: (1.5, 3.2), 3: (1.5, 0.8), 4: (3.0, 2.0),
                   5: (4.5, 3.2), 6: (4.5, 0.8), 7: (6.0, 2.0), 8: (7.5, 3.2),
                   9: (7.5, 0.8), 10: (9.0, 2.0)}


# ==========================================================================
# 1. Yerleşim
# ==========================================================================
def auto_layout(nodes: Sequence[int], edges: Sequence[Edge], *,
                iterations: int = 220) -> Pos:
    """Tohumsuz, dolayısıyla BELİRLENİMCİ Fruchterman-Reingold.

    Başlangıç rastgele değil, düğüm sırasına göre çemberdir; rastgelelik hiç
    girmediği için aynı çizge her zaman aynı yerleşimi verir (ilke 3).
    """
    ns = list(nodes)
    n = len(ns)
    if n == 0:
        return {}
    if n == 1:
        return {ns[0]: (0.5, 0.5)}
    pos = {v: [math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)]
           for i, v in enumerate(ns)}
    adj: Dict[int, List[int]] = {v: [] for v in ns}
    for u, v in edges:
        if u in adj and v in adj:
            adj[u].append(v)
            adj[v].append(u)
    k = math.sqrt(4.0 / n)
    temp = 0.5
    for _ in range(iterations):
        disp = {v: [0.0, 0.0] for v in ns}
        for i, u in enumerate(ns):
            ux, uy = pos[u]
            for v in ns[i + 1:]:
                dx, dy = ux - pos[v][0], uy - pos[v][1]
                d2 = dx * dx + dy * dy
                if d2 < 1e-9:
                    dx, dy, d2 = 1e-3 * (i + 1), 1e-3, 1e-6
                f = k * k / d2
                disp[u][0] += dx * f
                disp[u][1] += dy * f
                disp[v][0] -= dx * f
                disp[v][1] -= dy * f
        for u in ns:
            for v in adj[u]:
                dx, dy = pos[u][0] - pos[v][0], pos[u][1] - pos[v][1]
                d = math.hypot(dx, dy) or 1e-6
                f = d / k
                disp[u][0] -= dx / d * f
                disp[u][1] -= dy / d * f
        for u in ns:
            dx, dy = disp[u]
            d = math.hypot(dx, dy) or 1e-9
            step = min(d, temp)
            pos[u][0] += dx / d * step
            pos[u][1] += dy / d * step
        temp *= 0.96
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    sx, ex = min(xs), max(xs)
    sy, ey = min(ys), max(ys)
    w = (ex - sx) or 1.0
    h = (ey - sy) or 1.0
    return {v: ((p[0] - sx) / w, (p[1] - sy) / h) for v, p in pos.items()}


# ==========================================================================
# 2. Koşumun şekle hazır görünümü
# ==========================================================================
@dataclass
class RunView:
    """Bir `BbcvcRun`'ın çizim için gereken her şeyi çıkarılmış hali.

    Ağırlık ve k düğüm nesnelerinden okunur (`node.w`, `node.k`); koşum
    özetinde ayrı alan olarak durmadıkları için başka kaynak yoktur.
    """

    run: BbcvcRun
    nodes: List[int]
    edges: List[Edge]
    pos: Pos
    weights: Dict[int, float]
    k: int
    roles: Dict[int, Role]
    graph: Any

    @property
    def backbone(self) -> List[int]:
        return [v for v in self.nodes if self.roles[v].in_backbone]

    @property
    def cover(self) -> List[int]:
        return [v for v in self.nodes if self.roles[v].in_cover]


def view_of(run: BbcvcRun, *, pos: Optional[Pos] = None,
            roles: Optional[Mapping[int, Role]] = None) -> RunView:
    """Koşumdan çizim görünümü üret. `pos` verilmezse yerleşim hesaplanır."""
    nodes = sorted(run.nodes)
    edges = [tuple(e) for e in run.net.edges]  # type: ignore[attr-defined]
    weights = {nid: float(run.nodes[nid].w) for nid in nodes}
    ks = {int(run.nodes[nid].k) for nid in nodes}
    k = sorted(ks)[0] if ks else 0
    rr = dict(roles) if roles is not None else {nid: run.nodes[nid].role for nid in nodes}
    for nid in nodes:
        rr.setdefault(nid, Role.OUT)
    if pos is None:
        pos = (dict(WORKED_POS) if _is_worked_example(nodes, edges)
               else auto_layout(nodes, edges))
    return RunView(run=run, nodes=nodes, edges=edges, pos=dict(pos),
                   weights=weights, k=k, roles=rr,
                   graph=validate.make_graph(edges, k, weights, nodes=nodes))


def _is_worked_example(nodes: Sequence[int], edges: Sequence[Edge]) -> bool:
    return (sorted(nodes) == sorted(WORKED_WEIGHTS)
            and sorted(tuple(sorted(e)) for e in edges) == sorted(WORKED_EDGES))


# ==========================================================================
# 3. Tarihçe: günlükten türetilen rol/faz zaman çizgisi
# ==========================================================================
#: Günlük olayı -> (rolü hangi değere çeker, hangi ALGORİTMA fazına ait).
#: JOIN gerekçeleri fazı belirler: connector daveti Faz 1b, zorunlu yük Faz 3,
#: eskalasyon Faz 4'tür (bbcvc.JOIN_*).
_JOIN_PHASE = {JOIN_CONNECTOR: 1, JOIN_FORCED: 3, JOIN_ESCALATE: 4}


@dataclass(frozen=True)
class RoleEvent:
    t_ms: int
    nid: int
    role: Role
    phase: int          # 0 = epoch sıfırlaması, 1..4 = algoritma fazı
    kind: str
    is_change: bool     # rolü gerçekten değiştirdi mi (OUT kararı değiştirmez)


@dataclass
class RunHistory:
    """Koşumun rol tarihçesi. Tamamı `SimNet.log_records`'tan türetilmiştir."""

    events: List[RoleEvent]
    nodes: List[int]
    weights: Dict[int, float]
    unit: str                    # "slot" (senkron) | "ms" (asenkron)
    tau_ms: int                  # senkronda slot süresi, asenkronda 1
    t_end_ms: int
    phase_end_ms: Dict[int, int]
    quiet_ms: Optional[int]
    done_ms: Optional[int]

    def x_of(self, t_ms: int) -> float:
        return t_ms / self.tau_ms if self.unit == "slot" else float(t_ms)

    def roles_at_phase(self, phase: int) -> Dict[int, Role]:
        """Faz `phase` sonundaki roller.

        Zamana DEĞİL, olayın ait olduğu faza göre süzülür: roller monoton
        olduğundan (api I5) faz ≤ p olayların uygulanması o fazın sonundaki
        durumu tam olarak verir. Epoch sıfırlaması (faz 0) her zaman uygulanır.
        """
        roles = {v: Role.OUT for v in self.nodes}
        for ev in self.events:
            if ev.phase <= phase and ev.is_change:
                roles[ev.nid] = ev.role
        return roles

    def series(self) -> Dict[str, List[float]]:
        """x, rol değişimi sayısı, |C| ve Σw zaman serileri (adım fonksiyonu)."""
        times = sorted({ev.t_ms for ev in self.events if ev.is_change})
        roles = {v: Role.OUT for v in self.nodes}
        xs: List[float] = [0.0]
        changes: List[float] = [0.0]
        csize: List[float] = [0.0]
        weight: List[float] = [0.0]
        for t in times:
            n = 0
            for ev in self.events:
                if ev.t_ms == t and ev.is_change:
                    roles[ev.nid] = ev.role
                    n += 1
            cov = [v for v in self.nodes if roles[v].in_cover]
            xs.append(self.x_of(t))
            changes.append(float(n))
            csize.append(float(len(cov)))
            weight.append(float(sum(self.weights[v] for v in cov)))
        xs.append(self.x_of(self.t_end_ms))
        changes.append(0.0)
        csize.append(csize[-1])
        weight.append(weight[-1])
        return {"x": xs, "changes": changes, "cover_size": csize, "weight": weight}


def history_from_run(run: BbcvcRun) -> RunHistory:
    """Rol tarihçesini koşumun GÜNLÜĞÜNDEN kur (yeniden koşum yok)."""
    nodes = sorted(run.nodes)
    weights = {nid: float(run.nodes[nid].w) for nid in nodes}
    recs = list(run.net.log_records)  # type: ignore[attr-defined]

    events: List[RoleEvent] = []
    for r in recs:
        ev, nid, t = r.get("event"), r.get("nid"), int(r.get("t_ms", 0))
        if nid not in weights:
            continue
        if ev == "mis_decided":
            mis = r.get("role") == "MIS"
            events.append(RoleEvent(t, nid, Role.MIS if mis else Role.OUT, 1,
                                    "mis", mis))
        elif ev == "connector":
            events.append(RoleEvent(t, nid, Role.CONNECTOR, 1, "connector", True))
        elif ev == "cover":
            events.append(RoleEvent(t, nid, Role.COVER, 2, "cover", True))
        elif ev == "joined":
            code = int(r.get("reason", JOIN_FORCED))
            role = Role.CONNECTOR if code == JOIN_CONNECTOR else Role.COVER
            events.append(RoleEvent(t, nid, role, _JOIN_PHASE.get(code, 3),
                                    "joined", True))
        elif ev == "reset_phase0":
            events.append(RoleEvent(t, nid, Role.OUT, 0, "reset", True))
    events.sort(key=lambda e: (e.t_ms, e.nid, e.phase))

    # Faz sınırı = o faza ait SON olayın anı, önceki sınırla monotonlaştırılmış.
    phase_end: Dict[int, int] = {}
    last = 0
    for p in (1, 2, 3, 4):
        cand = [e.t_ms for e in events if e.phase == p]
        last = max([last] + cand)
        phase_end[p] = last

    quiet = [int(r["t_ms"]) for r in recs if r.get("event") == "quiet"]
    done = [int(r["t_ms"]) for r in recs if r.get("event") == "done"]
    t_end = max([0, run.t_conv_ms or 0] + [int(r.get("t_ms", 0)) for r in recs])

    if run.slots:
        unit, tau = "slot", max(1, _tau_of(run))
    else:
        unit, tau = "ms", 1
    return RunHistory(events=events, nodes=nodes, weights=weights, unit=unit,
                      tau_ms=tau, t_end_ms=t_end, phase_end_ms=phase_end,
                      quiet_ms=max(quiet) if quiet else None,
                      done_ms=max(done) if done else None)


def _tau_of(run: BbcvcRun) -> int:
    """Slot süresi: zamanlayıcı notlarından, yoksa t_conv/slots oranından."""
    for note in getattr(run.outcome, "notes", []) or []:
        if isinstance(note, str) and note.startswith("tau_ms="):
            try:
                return int(note.split("=", 1)[1])
            except ValueError:
                pass
    if run.slots and run.t_conv_ms:
        return max(1, run.t_conv_ms // run.slots)
    return 200


# ==========================================================================
# 4. Çizim yardımcıları
# ==========================================================================
@dataclass
class FigureResult:
    """Bir şeklin ürünü. `caption` brief §8'in istediği tek cümledir."""

    name: str
    paths: List[str]
    caption: str
    violation_artists: int = 0
    red_artists: int = 0
    data: Dict[str, Any] = field(default_factory=dict)


def _tag(artist, kind: str):
    """Çizeri ihlal çizeri olarak işaretle. Sayım bunun üzerinden yapılır."""
    artist.set_gid(f"{VIOL_GID}{kind}")
    return artist


def count_violation_artists(fig) -> int:
    """İhlalden doğan çizerlerin sayısı. Geçerli çözümde SIFIR olmalıdır."""
    n = 0
    for art in fig.findobj():
        gid = art.get_gid()
        if isinstance(gid, str) and gid.startswith(VIOL_GID):
            n += 1
    return n


def count_red_artists(fig) -> int:
    """Kırmızı RENKLİ çizerleri say (etiketten bağımsız ikinci kanıt)."""
    target = mcolors.to_rgba(RED)

    def _hit(value) -> bool:
        if value is None:
            return False
        try:
            arr = mcolors.to_rgba_array(value)
        except (ValueError, TypeError):
            return False
        if arr.size == 0:
            return False
        return any(tuple(round(float(c), 4) for c in row[:3])
                   == tuple(round(float(c), 4) for c in target[:3])
                   and row[3] > 0.05 for row in arr)

    n = 0
    for art in fig.findobj():
        for getter in ("get_color", "get_edgecolor", "get_facecolor"):
            fn = getattr(art, getter, None)
            if callable(fn):
                try:
                    if _hit(fn()):
                        n += 1
                        break
                except (TypeError, ValueError):
                    continue
    return n


def _draw_edges(ax, view: RunView, roles: Mapping[int, Role], *,
                backbone_width: float = 3.2, base_width: float = 1.0) -> None:
    """Kenarlar. İki ucu da omurgadaysa KALIN (brief §8/1)."""
    for u, v in view.edges:
        x = (view.pos[u][0], view.pos[v][0])
        y = (view.pos[u][1], view.pos[v][1])
        bb = roles[u].in_backbone and roles[v].in_backbone
        ax.plot(x, y, color="#4a4a4a" if bb else "#9a9a9a",
                lw=backbone_width if bb else base_width,
                solid_capstyle="round", zorder=1 if not bb else 2)


def _draw_nodes(ax, view: RunView, roles: Mapping[int, Role], *,
                size: float = 420.0, labels: Optional[Mapping[int, str]] = None,
                label_size: float = 7.5) -> None:
    for role in (Role.OUT, Role.COVER, Role.CONNECTOR, Role.MIS):
        st = ROLE_STYLE[role]
        vs = [v for v in view.nodes if roles[v] == role]
        if not vs:
            continue
        ax.scatter([view.pos[v][0] for v in vs], [view.pos[v][1] for v in vs],
                   s=size, marker=st["marker"], facecolors=st["face"],
                   edgecolors=st["edge"], linewidths=1.3, hatch=st["hatch"],
                   zorder=3)
    for v in view.nodes:
        txt = labels.get(v) if labels else str(v)
        if txt is None:
            continue
        dark = roles[v] == Role.MIS
        ax.annotate(txt, view.pos[v], ha="center", va="center",
                    fontsize=label_size, zorder=4,
                    color="#ffffff" if dark else "#000000",
                    path_effects=[pe.withStroke(
                        linewidth=1.8, foreground="#000000" if dark else "#ffffff")])


def _role_legend(fig, *, backbone: bool = True,
                 extra: Sequence[Any] = ()) -> None:
    """Rol göstergesi ŞEKİL düzeyinde: eksen kutusu küçülünce altyazıya girmesin."""
    handles = [Line2D([], [], marker=ROLE_STYLE[r]["marker"], linestyle="none",
                      markerfacecolor=ROLE_STYLE[r]["face"],
                      markeredgecolor=ROLE_STYLE[r]["edge"], markersize=9,
                      label=ROLE_STYLE[r]["label"])
               for r in (Role.OUT, Role.MIS, Role.CONNECTOR, Role.COVER)]
    if backbone:
        handles.append(Line2D([], [], color="#4a4a4a", lw=3.2,
                              label="omurga kenarı"))
    handles.extend(extra)
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.0),
               ncol=3, frameon=False, fontsize=7.5)


def _frame_off(ax) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_aspect("equal", adjustable="box")
    ax.set_anchor("N")
    ax.margins(0.12)


def _aspect_of(pos: Pos) -> float:
    """Yerleşimin yükseklik/genişlik oranı; şekil boyu buna göre seçilir."""
    if not pos:
        return 0.6
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    w = (max(xs) - min(xs)) or 1.0
    h = (max(ys) - min(ys)) or 1.0
    return min(max(h / w, 0.22), 1.6)


def _graph_grid(pos: Pos, *, width: float, cols: int, rows: int,
                top_in: float = 0.42, bottom_in: float = 0.80,
                title_in: float = 0.52, gap_in: float = 0.28):
    """Çok panelli çizge ızgarası; her panel kutusu baştan veri oranında.

    `tight_layout` burada İŞE YARAMAZ: en-boy düzeltmesi çizim anında yapılır,
    yani tight_layout hâlâ eski (yüksek) eksen dikdörtgenini görür ve alt satır
    başlıklarını üst satırın grafiğinin üstüne bindirir (görüldü).
    """
    aspect = _aspect_of(pos)
    side = 0.15
    panel_w = (width - 2 * side - (cols - 1) * gap_in) / cols
    panel_h = panel_w * aspect
    row_h = panel_h + title_in
    height = top_in + rows * row_h + (rows - 1) * gap_in + bottom_in
    fig = plt.figure(figsize=(width, height))
    axes = []
    for r in range(rows):
        for c in range(cols):
            left = side + c * (panel_w + gap_in)
            top_y = height - top_in - r * (row_h + gap_in) - title_in
            axes.append(fig.add_axes([left / width, (top_y - panel_h) / height,
                                      panel_w / width, panel_h / height]))
    return fig, axes, height


def _graph_fig(pos: Pos, *, width: float, top_in: float, bottom_in: float):
    """Tek eksenli çizge şekli: eksen KUTUSU baştan veri oranında kurulur.

    `set_aspect("equal", adjustable="box")` kutuyu sonradan daraltır ve artan
    yeri şeklin içinde boş bırakır; `bbox_inches="tight"` şeklin İÇİNDEKİ boşluğu
    kırpamaz. Bu yüzden kutu doğru oranda DOĞRUDAN yerleştirilir.
    """
    aspect = _aspect_of(pos)
    ax_w = max(width - 0.3, 1.0)
    ax_h = ax_w * aspect
    height = ax_h + top_in + bottom_in
    fig = plt.figure(figsize=(width, height))
    ax = fig.add_axes([0.15 / width, bottom_in / height,
                       ax_w / width, ax_h / height])
    return fig, ax


def _save(fig, outdir: str, name: str, caption: str, *,
          data: Optional[Dict[str, Any]] = None) -> FigureResult:
    """PNG + SVG yaz ve altına 'bu şekil neyi doğruluyor' cümlesini bas."""
    os.makedirs(outdir, exist_ok=True)
    fig.text(0.5, -0.025, caption, ha="center", va="top", fontsize=7.5,
             color="#333333", wrap=True)
    paths = []
    for ext in ("png", "svg"):
        p = os.path.join(outdir, f"{name}.{ext}")
        # SVG'ye tarih gömülmez: aynı koşum aynı baytı vermeli (ilke 3).
        fig.savefig(p, format=ext, bbox_inches="tight",
                    metadata={"Date": None} if ext == "svg" else None)
        paths.append(p)
    res = FigureResult(name=name, paths=paths, caption=caption,
                       violation_artists=count_violation_artists(fig),
                       red_artists=count_red_artists(fig),
                       data=dict(data or {}))
    plt.close(fig)
    return res


def _flag_note(run: BbcvcRun) -> str:
    """INFEASIBLE / çözülemedi / yakınsamadı bayrakları; sessizce geçilmez."""
    bits = []
    if not run.converged:
        bits.append("YAKINSAMADI")
    if run.infeasible:
        bits.append("INFEASIBLE")
    if run.unresolved:
        bits.append("SAHİPLİK ÇÖZÜLEMEDİ")
    return " · ".join(bits)


def _stamp_flags(ax, run: BbcvcRun) -> None:
    note = _flag_note(run)
    if note:
        # Bayraklar ihlal DEĞİLDİR; kırmızı ayrıcalığı doğrulayıcıdadır (ilke 1).
        # Başlığın ALTINA değil, eksenin sol üst köşesine: başlık bandıyla
        # çakışınca iki yazı da okunmuyordu.
        ax.text(0.01, 0.99, note, transform=ax.transAxes, ha="left", va="top",
                fontsize=8, fontweight="bold", color="#000000",
                bbox={"facecolor": "#f0f0f0", "edgecolor": "#000000", "pad": 2.5})


# ==========================================================================
# ŞEKİL 1 — Topoloji ve roller
# ==========================================================================
def figure_topology(run: BbcvcRun, outdir: str, *, pos: Optional[Pos] = None,
                    name: str = "fig1_topology",
                    view: Optional[RunView] = None) -> FigureResult:
    v = view or view_of(run, pos=pos)
    fig, ax = _graph_fig(v.pos, width=8.2, top_in=0.45, bottom_in=0.80)
    _draw_edges(ax, v, v.roles)
    _draw_nodes(ax, v, v.roles)
    _frame_off(ax)
    ax.set_title(f"Topoloji ve roller — |V|={len(v.nodes)}, |E|={len(v.edges)}, "
                 f"k={v.k}, |C|={len(v.cover)}, |B|={len(v.backbone)}, "
                 f"Σw={run.total_weight:g}")
    _stamp_flags(ax, run)
    _role_legend(fig)
    return _save(fig, outdir, name,
                 "Bu şekil, omurganın (MIS + CONNECTOR) bağlı olduğunu ve örtünün "
                 "onu kapsadığını gösterir: içi boş düğümler C dışındadır, kalın "
                 "kenarlar omurgayı taşır.",
                 data={"cover": v.cover, "backbone": v.backbone})


# ==========================================================================
# ŞEKİL 2 — Sahiplik (kırmızı YALNIZ ihlal listesinden)
# ==========================================================================
def _owner_arrow(ax, p_from, p_to, *, color: str, lw: float, ls: str = "-"):
    """Kenarın ortasında sahibine bakan kısa ok."""
    (x0, y0), (x1, y1) = p_from, p_to
    a = (x0 + 0.34 * (x1 - x0), y0 + 0.34 * (y1 - y0))
    b = (x0 + 0.72 * (x1 - x0), y0 + 0.72 * (y1 - y0))
    arr = FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=11,
                          color=color, lw=lw, linestyle=ls, zorder=5,
                          shrinkA=0, shrinkB=0)
    ax.add_patch(arr)
    return arr


def figure_ownership(run: BbcvcRun, outdir: str, *, pos: Optional[Pos] = None,
                     owner: Optional[Mapping[Edge, int]] = None,
                     cover: Optional[Sequence[int]] = None,
                     connectivity: str = validate.STRICT,
                     name: str = "fig2_ownership",
                     view: Optional[RunView] = None) -> FigureResult:
    """Sahiplik okları + doğrulayıcının ihlal listesi.

    `owner`/`cover` dışarıdan verilebilir; testler BOZULMUŞ bir sahiplik
    tablosu vererek kırmızının gerçekten ihlalden doğduğunu sınar.
    """
    v = view or view_of(run, pos=pos)
    own = dict(owner) if owner is not None else dict(run.owner)
    cov = sorted(cover) if cover is not None else sorted(run.cover)
    report = validate.validate(v.graph, cov, own, connectivity=connectivity)

    load: Dict[int, int] = {x: 0 for x in v.nodes}
    for o in own.values():
        if o in load:
            load[o] += 1

    bad_edges = {tuple(sorted(e)) for vi in report.violations
                 if vi.kind in (validate.UNCOVERED_EDGE, validate.BAD_OWNER)
                 for e in vi.edges}
    bad_nodes = {x for vi in report.violations
                 if vi.kind in (validate.OVERLOAD, validate.FORCED_OVERLOAD)
                 for x in vi.nodes}

    fig, ax = _graph_fig(v.pos, width=8.6, top_in=0.55, bottom_in=0.85)
    for u, w in v.edges:
        e = (u, w) if u <= w else (w, u)
        p_u, p_w = v.pos[u], v.pos[w]
        broken = e in bad_edges
        ax.plot((p_u[0], p_w[0]), (p_u[1], p_w[1]),
                color="#b5b5b5" if not broken else "#dddddd",
                lw=1.0, zorder=1)
        o = own.get(e)
        if o in e and not broken:
            src = p_w if o == u else p_u
            dst = p_u if o == u else p_w
            _owner_arrow(ax, src, dst, color="#2b2b2b", lw=1.2)

    _draw_nodes(ax, v, v.roles, size=520,
                labels={x: f"{x}\n{load[x]}/{v.k}" if v.roles[x].in_cover else str(x)
                        for x in v.nodes},
                label_size=6.6)

    reds = _draw_violations(ax, v, report, bad_nodes)
    _frame_off(ax)
    ax.set_title(f"Sahiplik ve doğrulama — {report.summary()} "
                 f"({len(report.violations)} ihlal)")
    _stamp_flags(ax, run)
    extra = ([Line2D([], [], color=RED, lw=1.6, ls="--",
                     label="ihlal (doğrulayıcı)")] if reds else [])
    _role_legend(fig, backbone=False, extra=extra)
    res = _save(fig, outdir, name,
                "Bu şekil sahiplik fonksiyonunun geçerliliğini doğrular: her ok bir "
                "kenarın sahibini gösterir, etiketler yük/k okunur ve kırmızının "
                "tamamı doğrulayıcının ihlal listesinden gelir, dolayısıyla geçerli "
                "bir çözümde kırmızı bulunamaz.",
                data={"violations": len(report.violations),
                      "summary": report.summary(), "load": load})
    res.data["report"] = report
    return res


def _draw_violations(ax, v: RunView, report, bad_nodes) -> int:
    """HER İHLAL TAM BİR KIRMIZI ÇİZER. Sayı sözleşmesi budur.

    Coğrafyası olmayan ihlaller (girdi çizgesi kopuk, alt sınır, akış
    uygunsuzluğu) da tek bir kırmızı metin satırıyla çizilir; böylece
    `count_violation_artists(fig) == len(report.violations)` her durumda tutar.
    """
    text_slot = 0
    for vi in report.violations:
        if vi.kind in (validate.UNCOVERED_EDGE, validate.BAD_OWNER) and vi.edges:
            xs: List[float] = []
            ys: List[float] = []
            for (a, b) in vi.edges:
                if a in v.pos and b in v.pos:
                    xs += [v.pos[a][0], v.pos[b][0], math.nan]
                    ys += [v.pos[a][1], v.pos[b][1], math.nan]
            if xs:
                ln, = ax.plot(xs, ys, color=RED, lw=2.0, ls="--", zorder=6)
                _tag(ln, vi.kind)
                continue
        if vi.kind in (validate.OVERLOAD, validate.FORCED_OVERLOAD) and vi.nodes:
            pts = [v.pos[x] for x in vi.nodes if x in v.pos]
            if pts:
                sc = ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=980,
                                marker="o", facecolors="none", edgecolors=RED,
                                linewidths=2.4, zorder=6)
                _tag(sc, vi.kind)
                continue
        if vi.kind == validate.DISCONNECTED and vi.nodes:
            pts = [v.pos[x] for x in vi.nodes if x in v.pos]
            if pts:
                sc = ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=1300,
                                marker="s", facecolors="none", edgecolors=RED,
                                linewidths=2.2, linestyle=":", zorder=6)
                _tag(sc, vi.kind)
                continue
        # coğrafyası olmayan ihlal: tek satır kırmızı metin
        txt = ax.text(0.01, 0.02 + 0.045 * text_slot, f"■ {vi.kind}: {vi.detail}",
                      transform=ax.transAxes, fontsize=6.4, color=RED,
                      ha="left", va="bottom", zorder=7)
        _tag(txt, vi.kind)
        text_slot += 1
    return len(report.violations)


# ==========================================================================
# ŞEKİL 3 — Faz anlık görüntüleri
# ==========================================================================
def figure_phase_snapshots(run: BbcvcRun, outdir: str, *,
                           pos: Optional[Pos] = None,
                           history: Optional[RunHistory] = None,
                           name: str = "fig3_phases",
                           view: Optional[RunView] = None) -> FigureResult:
    v = view or view_of(run, pos=pos)
    h = history or history_from_run(run)
    fig, axes, height = _graph_grid(v.pos, width=10.4, cols=2, rows=2,
                                    top_in=0.50, bottom_in=0.78)
    sizes: List[int] = []
    weights: List[float] = []
    for ax, p in zip(axes, (1, 2, 3, 4)):
        roles = h.roles_at_phase(p)
        cov = [x for x in v.nodes if roles[x].in_cover]
        sizes.append(len(cov))
        weights.append(sum(v.weights[x] for x in cov))
        _draw_edges(ax, v, roles, backbone_width=2.6, base_width=0.8)
        _draw_nodes(ax, v, roles, size=210, label_size=6.0)
        _frame_off(ax)
        ax.set_title(f"{ALGO_PHASES[p]}\n|C|={len(cov)}, Σw={weights[-1]:g}",
                     fontsize=8.5)
    _role_legend(fig)
    fig.text(0.5, 1.0 - 0.22 / height,
             "Faz sonu anlık görüntüleri: örtü monoton büyür ve bağlı kalır",
             ha="center", va="top", fontsize=10)
    return _save(fig, outdir, name,
                 "Bu şekil örtünün fazlar boyunca monoton büyüdüğünü ve hiçbir "
                 f"fazda bağlılığını yitirmediğini doğrular: |C| sırasıyla {sizes}.",
                 data={"cover_size": sizes, "weight": weights})


# ==========================================================================
# ŞEKİL 4 — Yakınsama zaman çizgisi
# ==========================================================================
def figure_convergence(run: BbcvcRun, outdir: str, *,
                       history: Optional[RunHistory] = None,
                       name: str = "fig4_convergence") -> FigureResult:
    h = history or history_from_run(run)
    s = h.series()
    xlabel = "slot (senkron)" if h.unit == "slot" else "ms (asenkron)"

    fig, axes = plt.subplots(3, 1, figsize=(8.2, 6.2), sharex=True)
    width = max((s["x"][-1] or 1.0) / 90.0, 0.35)
    axes[0].bar(s["x"], s["changes"], width=width, color="#3a3a3a")
    axes[0].set_ylabel("rol değişimi")
    axes[1].step(s["x"], s["cover_size"], where="post", color="#000000", lw=1.6)
    axes[1].set_ylabel("|C|")
    axes[2].step(s["x"], s["weight"], where="post", color="#000000", lw=1.6,
                 ls="--")
    axes[2].set_ylabel("Σw")
    axes[2].set_xlabel(xlabel)

    # Faz sınırları üst üste düşebilir (örtü fazında hiç rol değişmediğinde
    # F2 ile F3 aynı ana oturur); etiketler dönüşümlü yükseklikte yazılır.
    for p in (1, 2, 3, 4):
        x = h.x_of(h.phase_end_ms[p])
        for ax in axes:
            ax.axvline(x, color="#8c8c8c", lw=0.9, ls=":")
        axes[0].text(x, 0.97 - 0.16 * (p % 2), f"F{p}",
                     transform=axes[0].get_xaxis_transform(), fontsize=7,
                     ha="center", va="top", color="#5a5a5a",
                     bbox={"facecolor": "#ffffff", "edgecolor": "none",
                           "pad": 0.8})
    for ax in axes:
        ax.grid(axis="y", color="#e2e2e2", lw=0.6)
        ax.set_axisbelow(True)

    conv = f"{run.slots} slot" if run.slots else f"{run.t_conv_ms} ms"
    axes[0].set_title(f"Yakınsama — {run.outcome.scheduler}, {conv}, "
                      f"tx={run.tx}, Σw={run.total_weight:g}"
                      + (f"  [{_flag_note(run)}]" if _flag_note(run) else ""))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return _save(fig, outdir, name,
                 "Bu şekil kararların sonlandığını doğrular: rol değişimleri faz "
                 "sınırlarında toplanır, |C| ve Σw monoton artıp sabitlenir, "
                 "sükûnetten sonra hiçbir değişim yoktur.",
                 data={"phase_end_ms": dict(h.phase_end_ms),
                       "final_cover": s["cover_size"][-1]})


# ==========================================================================
# ŞEKİL 5 — Mesaj kırılımı
# ==========================================================================
def _try_encode(mt: MsgType) -> Optional[int]:
    """Bu tipin telde kaç bayt ettiği; wire onu tanımıyorsa None.

    Gövdeler DENENİR, elle eşlenmez: `MsgType`e yeni bir üye eklenip telde
    gövdesi yazıldığı anda burası kendiliğinden öğrenir, gövdesi henüz yokken
    de sessizce yanlış bir boy uydurmaz.
    """
    enc = wire.encode
    for build in (lambda: wire.Ctrl(mt, 1, 0),
                  lambda: wire.Join(mt, 1, 0, 0),
                  lambda: wire.EdgeMsg(mt, 1, 0, 1, 2, 3),
                  lambda: wire.Tree(1, 0, 1, 1, 0),
                  lambda: wire.Stable(1, 0, 1, 1, 0, 0, 0, 0),
                  lambda: wire.Finish(1, 0, 1)):
        try:
            msg = build()
        except (TypeError, ValueError):
            continue
        if getattr(msg, "mtype", None) != mt:
            continue
        try:
            return len(enc(msg))
        except (TypeError, ValueError):
            continue
    return None


def fixed_sizes() -> Dict[int, int]:
    """HELLO dışında telde SABİT boyutlu olan her tipin kesin bayt boyu."""
    out: Dict[int, int] = {}
    for mt in MsgType:
        if mt is MsgType.HELLO:
            continue
        size = _try_encode(mt)
        if size is not None:
            out[int(mt)] = size
    return out


def unmodelled_types() -> List[int]:
    """`MsgType`te olan ama telde gövdesi OLMAYAN tipler.

    Bunlar bir eksiklik değil bir SIRA meselesidir: numaralandırma üyesi,
    kodlayıcıdan önce eklenebilir (DFS-Spanning-Backbone'un TOKEN'ı böyle geldi). Şekil 5'in
    bayt kırılımı bu tiplerden biri koşumda GERÇEKTEN görünürse hesap yapmayı
    reddeder; görünmedikçe eksikliğin bir sonucu yoktur.
    """
    known = fixed_sizes()
    return sorted(int(m) for m in MsgType
                  if m is not MsgType.HELLO and int(m) not in known)


def bytes_by_type(run: BbcvcRun) -> Dict[int, int]:
    """Tip başına bayt. HELLO ÇIKARMA ile bulunur ve bu KESİNDİR.

    `Counters` bayt kırılımı tutmaz; ama HELLO dışındaki her tip sabit
    boyutludur, dolayısıyla HELLO baytı = toplam − Σ(sabit boy × sayı).
    """
    fixed = fixed_sizes()
    unknown = sorted(int(mt) for mt in run.by_type_tx
                     if int(mt) != int(MsgType.HELLO) and int(mt) not in fixed)
    if unknown:
        # HELLO baytı ÇIKARMAYLA bulunuyor; modellenmemiş bir tip sessizce
        # HELLO'ya yazılır ve sayı temiz görünür. Yeni bir mesaj tipi eklendiğinde
        # patlaması, yanlış bayt raporlamasından iyidir.
        names = [MsgType(t).name if t in set(MsgType) else str(t) for t in unknown]
        raise MissingData(
            f"bayt kırılımı modellenmemiş mesaj tipi içeriyor: {names}. "
            "fixed_sizes() güncellenmeli; yoksa bu tiplerin baytı HELLO'ya "
            "yazılır ve toplam yine tutar, dolayısıyla hata görünmez olur")
    out: Dict[int, int] = {}
    rest = 0
    for mt, cnt in run.by_type_tx.items():
        if int(mt) == int(MsgType.HELLO):
            continue
        b = fixed[int(mt)] * int(cnt)
        out[int(mt)] = b
        rest += b
    hello_tx = int(run.by_type_tx.get(int(MsgType.HELLO), 0))
    if hello_tx:
        out[int(MsgType.HELLO)] = run.bytes_tx - rest
    return out


def rx_by_type(run: BbcvcRun) -> Dict[int, int]:
    """Tip başına rx. `BbcvcRun` bunu düzleştirmiyor, `RunOutcome` tutuyor."""
    return {int(t): int(c) for t, c in run.outcome.totals().by_type_rx.items()}


def receiver_breakdown(run: BbcvcRun) -> Dict[str, Dict]:
    """Alıcı tarafına ATFEDİLMİŞ rx kırılımları (bb-core, SimNet).

    Brief §8/5 faz × tip için tx, rx ve bytes_tx istiyor. `Counters.rx` GÖNDERME
    anında karar verilir, yani "benim iletimlerimin yol açtığı teslim sayısı"
    demektir; brief'in tablosunun kastettiği ise İŞLEME/tampon maliyetidir ve o
    ALICIYA aittir. İki atıf küresel toplamda birbirine yakındır, bu yüzden
    faz kırılımı istenene kadar fark görünmez kaldı.

    Ölçüldü (bb-core): her tikte faz ilerleten düğümlerle, kayıpsız senkronda
    gönderen kırılımı {0:10, 1:10, 2:10, 3:10, 4:10} iken alıcı kırılımı
    {1:30, 2:30, 3:30, 4:30} — TAMAMEN farklı fazlar, çünkü slot t'de gönderilen
    çerçeve slot t+1'de işlenir. Gönderen atıflı bir `by_phase_rx` her alınan
    çerçeveyi bir faz erken gösterir ve makul görünürdü.
    """
    net = run.net  # type: ignore[attr-defined]
    fn = getattr(net, "receiver_totals", None)
    if not callable(fn):
        raise MissingData(
            "SimNet.receiver_totals() yok; alıcı atıflı rx kırılımı olmadan "
            "faz × tip tablosu çizilemez ve gönderen atıflı sayılarla "
            "değiştirilemez (farklı fazları gösterirler)")
    return fn()


def figure_message_breakdown(runs: Mapping[str, BbcvcRun], outdir: str, *,
                             name: str = "fig5_messages") -> FigureResult:
    """`runs`: {"sync": ..., "async": ...}; yan yana çubuklar.

    DÖRT PANEL ve her birinin ATFI adında: tip başına tx (gönderen), tip başına
    bayt (gönderen, türetilmiş), faz başına tx (GÖNDERENİN fazı) ve faz başına
    işlenen rx + bayt (ALICININ fazı). Son ikisi aynı çerçeveleri farklı
    fazlara yazar ve bu bir tutarsızlık değil, iki ayrı sorunun iki ayrı
    yanıtıdır; eksen başlıkları hangisini sorduğunu söyler.
    """
    modes = [m for m in ("sync", "async") if m in runs] or list(runs)
    recv = {m: receiver_breakdown(runs[m]) for m in modes}
    types = sorted({int(t) for m in modes for t in runs[m].by_type_tx})
    phases = sorted({int(p) for m in modes for p in runs[m].by_phase_tx}
                    | {int(p) for m in modes
                       for p in recv[m]["rx_by_receiver_phase"]})
    tnames = [MsgType(t).name for t in types]
    hatch = {"sync": "", "async": "///"}
    face = {"sync": "#3a3a3a", "async": "#cfcfcf"}

    fig, axes = plt.subplots(2, 2, figsize=(11.4, 7.0))
    w = 0.38

    def _bars(ax, keys, getter, title, ylab, xlabels, log=False):
        """HELLO diğer tipleri ezdiği için tip panelleri LOG ölçektedir."""
        idx = list(range(len(keys)))
        for j, m in enumerate(modes):
            vals = [getter(m, key) for key in keys]
            ax.bar([i + (j - (len(modes) - 1) / 2) * w for i in idx], vals,
                   width=w, label=m, color=face.get(m, "#8c8c8c"),
                   edgecolor="#000000", linewidth=0.6, hatch=hatch.get(m, ""))
        if log:
            ax.set_yscale("log")
            ax.set_ylim(bottom=0.7)
        ax.set_xticks(idx)
        ax.set_xticklabels(xlabels, rotation=45, ha="right", fontsize=6.5)
        ax.set_title(title, fontsize=9)
        ax.set_ylabel(ylab + (" (log)" if log else ""), fontsize=8)
        ax.grid(axis="y", color="#e6e6e6", lw=0.6)
        ax.set_axisbelow(True)

    _bars(axes[0][0], types, lambda m, t: int(runs[m].by_type_tx.get(t, 0)),
          "(a) tip başına tx — GÖNDEREN", "tx", tnames, log=True)
    _bars(axes[0][1], types, lambda m, t: int(bytes_by_type(runs[m]).get(t, 0)),
          "(b) tip başına bytes_tx — GÖNDEREN (türetilmiş)", "bayt", tnames,
          log=True)
    _bars(axes[1][0], phases, lambda m, p: int(runs[m].by_phase_tx.get(p, 0)),
          "(c) faz başına tx — GÖNDERENİN fazı", "tx",
          [f"{p}·{PHASE_NAMES.get(p, p)}" for p in phases])
    _bars(axes[1][1], phases,
          lambda m, p: int(recv[m]["rx_by_receiver_phase"].get(p, 0)),
          "(d) faz başına işlenen rx — ALICININ fazı", "rx",
          [f"{p}·{PHASE_NAMES.get(p, p)}" for p in phases])
    axes[0][0].legend(fontsize=7.5, frameon=False)

    caused = {m: runs[m].rx for m in modes}
    processed = {m: int(recv[m]["rx_at_receiver"]) for m in modes}
    gap = ", ".join(f"{m}: {caused[m]}/{processed[m]}" for m in modes)
    fig.suptitle("Mesaj kırılımı: senkron ve asenkron yan yana", fontsize=10)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    fig.text(0.5, 0.012,
             "(c) ile (d) AYNI çerçeveleri farklı fazlara yazar: slot t'de "
             "gönderilen çerçeve slot t+1'de işlenir. Yol açılan / işlenen rx "
             f"({gap}): fark, koşum bittiğinde hâlâ yolda olan çerçevelerdir; "
             "ikisi de doğrudur ve ayrı soruları yanıtlar.",
             ha="center", va="bottom", fontsize=6.6, color="#555555")
    return _save(fig, outdir, name,
                 "Bu şekil haberleşme maliyetinin nereye gittiğini doğrular: "
                 "iletim tipe ve gönderenin fazına, işleme maliyeti ise "
                 "alıcının fazına göre ayrışır ve ikisinin farklı fazlara "
                 "düşmesi slot gecikmesinin doğrudan ölçüsüdür.",
                 data={"modes": modes,
                       "tx": {m: runs[m].tx for m in modes},
                       "bytes": {m: runs[m].bytes_tx for m in modes},
                       "rx_caused": caused, "rx_processed": processed,
                       "rx_by_receiver_phase": {
                           m: dict(recv[m]["rx_by_receiver_phase"]) for m in modes},
                       "bytes_rx_by_receiver_phase": {
                           m: dict(recv[m]["bytes_rx_by_receiver_phase"])
                           for m in modes},
                       "phase_type_cells": {
                           m: len(recv[m]["rx_by_receiver_phase_type"])
                           for m in modes}})


# ==========================================================================
# ŞEKİL 9 — Faz 0 kimliği: 6n + 4m ve el sıkışma oranı
# ==========================================================================
@dataclass(frozen=True)
class BootstrapPoint:
    """Bir koşumun Faz 0 ölçümü. Hepsi GERÇEK koşumdan, hiçbiri uydurma."""

    scheduler: str
    n: int
    m: int
    phase0_tx: int
    link_per_edge: float
    link_ack_per_edge: float
    hello_tx: int

    @property
    def predicted(self) -> int:
        return 6 * self.n + 4 * self.m

    @property
    def residual(self) -> float:
        return (self.phase0_tx - self.predicted) / self.predicted


def bootstrap_points(graphs: Sequence[Tuple[str, Sequence[Edge], Mapping[int, float]]],
                     *, k: int = 4, schedulers: Sequence[str] = ("sync", "async"),
                     max_ms: int = 900_000, params: Any = None
                     ) -> List[BootstrapPoint]:
    """Faz 0 maliyetini GERÇEK koşumlardan ölç (şekil 9'un verisi)."""
    from ccvc.bb import bbcvc as _bb

    out: List[BootstrapPoint] = []
    for _label, edges, weights in graphs:
        for sch in schedulers:
            r = _bb.run_bbcvc(list(edges), dict(weights), k, scheduler=sch,
                              max_ms=max_ms, params=params)
            tot = r.outcome.totals()
            m = len(edges)
            out.append(BootstrapPoint(
                scheduler=sch, n=len(weights), m=m,
                phase0_tx=int(r.by_phase_tx.get(0, 0)),
                link_per_edge=tot.by_type_tx.get(int(MsgType.LINK), 0) / m,
                link_ack_per_edge=tot.by_type_tx.get(int(MsgType.LINK_ACK), 0) / m,
                hello_tx=int(tot.by_type_tx.get(int(MsgType.HELLO), 0))))
    return out


def figure_bootstrap_identity(points: Sequence[BootstrapPoint], outdir: str, *,
                              name: str = "fig9_bootstrap") -> FigureResult:
    """Faz 0'ın 6n+4m kimliği ve el sıkışmanın kenar başına 2 çerçevesi.

    İKİ TERİM, İKİ FARKLI DAVRANIŞ — şeklin bütün anlamı bu karşıtlıkta:

    * **Keşif terimi zamanlayıcıya BAĞLIDIR.** `6n` içindeki 6, paylaşılan
      keşif penceresinin SLOT cinsinden uzunluğudur ve senkronda sabittir tam
      da her düğüm en yavaş olan bitene kadar aynı slot sınırında tutulduğu
      için. Asenkronda paylaşılan pencere yoktur: keşfi erken biten düğüm
      beklemek yerine periyodik HELLO göndermeyi bırakır.
    * **El sıkışma terimi zamanlayıcıdan BAĞIMSIZDIR:** kenar başına tam
      2.000 çerçeve, her iki kipte de artıksız.

    Bu yüzden senkron ÇİZGİ, asenkron AYRI İŞARETLİ seri olarak çizilir. Tek
    çizgi geçirmek, asenkronun kimliğe uyduğunu ima ederdi.

    ÖNEMLİ, ÇÜNKÜ İLK AÇIKLAMAM YANLIŞTI: bu bir muhasebe sınırı değil.
    Çerçeveler faz 1'e yeniden yazılmıyor; ekip liderinin ölçümünde faz 1 DE
    düşüyor, faz 0+1 toplamı düşüyor ve toplam HELLO 79 azalıyor. O çerçeveler
    hiç gönderilmemiş.
    """
    if not points:
        raise MissingData(
            "şekil 9 için Faz 0 ölçümü yok; kimlik gerçek koşumdan doğrulanır")
    by_sch: Dict[str, List[BootstrapPoint]] = {}
    for p in points:
        by_sch.setdefault(p.scheduler, []).append(p)

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.4))
    style = {"sync": ("o", "#1a1a1a", "-"), "async": ("s", "#ffffff", "--")}
    summary: Dict[str, Dict[str, float]] = {}

    lo = min(p.predicted for p in points)
    hi = max(p.predicted for p in points)
    axes[0].plot([lo, hi], [lo, hi], color="#000000", lw=1.4,
                 label="6n + 4m (kimlik)", zorder=2)
    for sch in sorted(by_sch):
        ps = sorted(by_sch[sch], key=lambda p: p.predicted)
        mk, fc, ls = style.get(sch, ("^", "#8c8c8c", ":"))
        axes[0].scatter([p.predicted for p in ps], [p.phase0_tx for p in ps],
                        s=62, marker=mk, facecolors=fc, edgecolors="#000000",
                        linewidths=1.1, zorder=3, label=f"{sch} ölçülen")
        res = [100.0 * p.residual for p in ps]
        axes[1].plot([p.predicted for p in ps], res, color="#000000", lw=1.2,
                     ls=ls, zorder=2)
        axes[1].scatter([p.predicted for p in ps], res, s=62, marker=mk,
                        facecolors=fc, edgecolors="#000000", linewidths=1.1,
                        zorder=3, label=sch)
        summary[sch] = {
            "runs": float(len(ps)),
            "residual_mean_pct": round(statistics.mean(res), 3),
            "residual_max_abs_pct": round(max(abs(x) for x in res), 3),
            "link_per_edge_min": round(min(p.link_per_edge for p in ps), 4),
            "link_per_edge_max": round(max(p.link_per_edge for p in ps), 4),
            "link_ack_per_edge_min": round(min(p.link_ack_per_edge for p in ps), 4),
            "link_ack_per_edge_max": round(max(p.link_ack_per_edge for p in ps), 4),
        }
    axes[1].axhline(0.0, color="#000000", lw=1.0)

    axes[0].set_xlabel("6n + 4m (öngörülen)")
    axes[0].set_ylabel("Faz 0 tx (ölçülen)")
    axes[0].set_title("(a) keşif maliyeti — kimlik yalnız senkronda", fontsize=9)
    axes[1].set_xlabel("6n + 4m")
    axes[1].set_ylabel("artık (%)")
    axes[1].set_title("(b) artık: senkron 0, asenkron altında", fontsize=9)
    for ax in axes:
        ax.grid(color="#ececec", lw=0.6)
        ax.set_axisbelow(True)
        ax.legend(fontsize=7.5, frameon=False)

    lp = sorted({round(p.link_per_edge, 4) for p in points})
    la = sorted({round(p.link_ack_per_edge, 4) for p in points})
    handshake = (f"LINK {lp[0]:.3f}" + ("" if len(lp) == 1 else f"–{lp[-1]:.3f}")
                 + f", LINK_ACK {la[0]:.3f}"
                 + ("" if len(la) == 1 else f"–{la[-1]:.3f}"))
    fig.suptitle("Faz 0: keşif terimi zamanlayıcıya bağlı, el sıkışma değil",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))

    sync_res = summary.get("sync", {}).get("residual_max_abs_pct")
    async_res = summary.get("async", {}).get("residual_mean_pct")
    return _save(fig, outdir, name,
                 "Bu şekil Faz 0 maliyetinin iki teriminin farklı davrandığını "
                 f"doğrular: keşif terimi senkronda 6n+4m kimliğini artıksız "
                 f"tutar (en büyük |artık| %{_fmt_num(sync_res)}) ama "
                 "asenkronda ortalama "
                 f"%{_fmt_num(None if async_res is None else abs(async_res))} "
                 "ALTINDA kalır, "
                 f"çünkü paylaşılan keşif penceresi yoktur; el sıkışma terimi "
                 f"ise kenar başına {handshake} ile her iki kipte de aynıdır.",
                 data={"summary": summary,
                       "points": [{"scheduler": p.scheduler, "n": p.n, "m": p.m,
                                   "phase0_tx": p.phase0_tx,
                                   "predicted": p.predicted,
                                   "residual_pct": round(100 * p.residual, 3)}
                                  for p in points]})


def _fmt_num(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:g}"


# ==========================================================================
# ŞEKİL 6 VE 8 İÇİN VERİ SÖZLEŞMESİ
# ==========================================================================
class MissingData(RuntimeError):
    """Şeklin istediği ölçüm yok. ÇİZİM YAPILMAZ, hata yükselir.

    Bir şekil eksik veriyi sıfırla, enterpolasyonla ya da boş bir eğriyle
    doldurursa, bakan kişi bir ölçüm gördüğünü sanır. Eksik verinin doğru
    görüntüsü bir grafik değil, neyin eksik olduğunu SÖYLEYEN bir hatadır.
    """


@dataclass(frozen=True)
class SizePoint:
    """Şekil 6'nın tek noktası. Her alan ölçülmüş olmak ZORUNDA.

    `bytes_tx` ya da `max_payload` None ise nokta üretilmez; sıfır yazmak
    "hiç bayt göndermedi" demek olurdu ve o farklı bir iddiadır.
    """

    variant: str
    avg_degree: float
    max_payload: int
    bytes_tx: int
    converged: bool
    n: int
    m: int
    backbone: Optional[int] = None
    """Omurga büyüklüğü — KALİTE ekseni, isteğe bağlı.

    Bloom kolu yalnız yüke bakıldığında kazanan görünür; ölçüldü ki bedelini
    kalitede ödüyor (omurga bütün düğüm kümesine eşitleniyor). Yükü çizip
    kaliteyi çizmemek, ödünleşmenin yalnız kazançlı yarısını göstermek olurdu.
    """

    @staticmethod
    def of(variant: str, *, n: int, m: int, max_payload: Optional[int],
           bytes_tx: Optional[int], converged: bool,
           backbone: Optional[int] = None) -> "SizePoint":
        missing = [name for name, val in (("max_payload", max_payload),
                                          ("bytes_tx", bytes_tx)) if val is None]
        if missing:
            raise MissingData(
                f"{variant} n={n} m={m}: {missing} ölçülmemiş; şekil 6 bu noktayı "
                "uyduramaz")
        if n <= 0:
            raise MissingData(f"{variant}: n={n}, ortalama derece tanımsız")
        return SizePoint(variant, 2.0 * m / n, int(max_payload), int(bytes_tx),
                         bool(converged), int(n), int(m),
                         None if backbone is None else int(backbone))


def size_points_from_runs(series: Mapping[str, Sequence[BbcvcRun]]
                          ) -> Dict[str, List[SizePoint]]:
    """`BbcvcRun` koleksiyonunu şekil 6 noktalarına çevir."""
    out: Dict[str, List[SizePoint]] = {}
    for label, runs in series.items():
        pts = []
        for r in runs:
            n = len(r.nodes)
            m = len(r.net.edges)  # type: ignore[attr-defined]
            pts.append(SizePoint.of(label, n=n, m=m,
                                    max_payload=r.max_payload,
                                    bytes_tx=r.bytes_tx, converged=r.converged))
        out[label] = pts
    return out


def size_points_from_wuli(seeds: Sequence[int] = (0, 1), *,
                          max_ms: int = 3_000_000) -> Dict[str, List[SizePoint]]:
    """Şekil 6'yı WuLi-Dominating'in KENDİ ölçümlerinden besle, yeniden üretmeden.

    `v5_wuli.experiment()` zaten `variant, n, avg_degree, max_payload,
    bytes_tx, backbone, backbone_ref, valid` döndürüyor. Aynı büyüklüğü burada
    yeniden koşturmak iki sayı dizisi yaratır ve ikisi zamanla ayrışır; ayrışma
    da sessiz olur, çünkü her ikisi de kendi içinde tutarlı görünür.
    """
    from ccvc.bb import v5_wuli

    out: Dict[str, List[SizePoint]] = {}
    for r in v5_wuli.experiment(v5_wuli.default_cases(tuple(seeds)),
                                max_ms=max_ms):
        out.setdefault(str(r["variant"]), []).append(
            SizePoint.of(str(r["variant"]), n=int(r["n"]), m=int(r["m"]),
                         max_payload=r.get("max_payload"),
                         bytes_tx=r.get("bytes_tx"),
                         converged=bool(r.get("converged")),
                         backbone=r.get("backbone")))
    if not out:
        raise MissingData("v5_wuli.experiment() hiç satır döndürmedi")
    return out


def size_points_from_rows(rows: Iterable[Any]) -> Dict[str, List[SizePoint]]:
    """Süpürme satırlarını (ccvc.bb.sweep.Row) şekil 6 noktalarına çevir.

    Koşulmamış satır (`skipped`) ve çöken satır (`error`) ATLANIR: onların
    ölçümü yoktur. Atlanan satır sayısı hiç nokta kalmazsa hataya döner, yani
    "hepsi atlandı" sessizce boş bir grafik üretemez.
    """
    out: Dict[str, List[SizePoint]] = {}
    skipped = 0
    for r in rows:
        if getattr(r, "status", "") in ("skipped", "error", "invalid"):
            skipped += 1
            continue
        out.setdefault(r.variant, []).append(
            SizePoint.of(r.variant, n=r.n, m=r.m, max_payload=r.max_payload,
                         bytes_tx=r.bytes_tx, converged=bool(r.converged)))
    if not out:
        raise MissingData(
            f"şekil 6 için tek ölçüm yok ({skipped} satır koşulmamış ya da çökmüş)")
    return out


# --- şekil 6 için GERÇEK koşum üreten örnekleyici ---------------------------
#: İki rejim de AYNI `mis_nbrs_max` ile koşar. Başka türlüsü hile olurdu:
#: varsayılan 5 sınırıyla birim disk eğrisi zaten düz çıkardı ve düzlüğün
#: geometriden mi sınırdan mı geldiği ayırt edilemezdi (BULGU 3).
MIS_CAP_FOR_SIZE_STUDY = 30


def udg_instance(n: int, radius: float, seed: int
                 ) -> Optional[Tuple[List[Edge], Dict[int, float], Pos]]:
    """Bağlı birim disk çizgesi; G8'in geçerli olduğu rejim."""
    import random as _random
    rng = _random.Random(seed * 7919 + n)
    for _ in range(400):
        pts = {i: (rng.random(), rng.random()) for i in range(1, n + 1)}
        edges = [(u, v) for u in pts for v in pts
                 if u < v and math.dist(pts[u], pts[v]) <= radius]
        if edges and _connected(range(1, n + 1), edges):
            return edges, {i: rng.randint(1, 9) for i in pts}, dict(pts)
    return None


def er_instance(n: int, prob: float, seed: int
                ) -> Optional[Tuple[List[Edge], Dict[int, float]]]:
    """Bağlı Erdős-Rényi çizgesi; G8'in GEÇMEDİĞİ rejim (BULGU 3)."""
    import random as _random
    rng = _random.Random(seed * 104729 + n)
    for _ in range(200):
        edges = [(u, v) for u in range(1, n + 1) for v in range(u + 1, n + 1)
                 if rng.random() < prob]
        if edges and _connected(range(1, n + 1), edges):
            return edges, {i: rng.randint(1, 9) for i in range(1, n + 1)}
    return None


def _connected(nodes: Iterable[int], edges: Sequence[Edge]) -> bool:
    adj: Dict[int, List[int]] = {v: [] for v in nodes}
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    if not adj:
        return False
    start = next(iter(adj))
    seen, stack = {start}, [start]
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return len(seen) == len(adj)


#: Sabit n, artan yoğunluk. Ortalama derece merdiven boyunca tek yönde artsın
#: diye n sabit tutulur; n ile yoğunluğu birlikte oynatmak eğriyi gürültülü
#: yapıyordu (ölçüldü).
UDG_LADDER = ((24, 0.32), (24, 0.40), (24, 0.48), (24, 0.56), (24, 0.66))
UDG_LADDER_SLOW = ((40, 0.30), (40, 0.40))
ER_LADDER = ((100, 0.04), (100, 0.06), (100, 0.08), (100, 0.10), (100, 0.12))
ER_LADDER_SLOW = ((150, 0.09), (180, 0.10))


def _k_for(edges: Sequence[Edge], nodes: int) -> int:
    """Kapasite ortalama dereceye bağlanır.

    k mesaj BOYUTUNU etkilemez; yalnız Faz 3-4 onarımının ne kadar zorlandığını
    belirler. Yoğun çizgede sabit küçük k bırakılırsa onarım bütçeyi yiyor ve
    koşum sükûnete ermeden bitiyordu (ölçüldü: n=24, r=0.48'de k=6 ile 6,8 s ve
    yakınsama yok; k=12 ile 0,1 s ve yakınsama var). Ölçülen büyüklük aynı
    kalır, koşum bitmiş olur.
    """
    return max(4, math.ceil(2.0 * len(edges) / max(nodes, 1)))


def message_size_runs(*, seed: int = 3, slow: bool = False,
                      max_ms: int = 600_000) -> Dict[str, List[BbcvcRun]]:
    """Şekil 6'nın iki rejimini GERÇEK koşumlarla üret."""
    from ccvc.bb.bbcvc import BbcvcParams, run_bbcvc

    params = BbcvcParams(mis_nbrs_max=MIS_CAP_FOR_SIZE_STUDY)
    udg_key = "UDG (birim disk, G8 geçerli)"
    er_key = "Erdős-Rényi (birim disk dışı)"
    out: Dict[str, List[BbcvcRun]] = {udg_key: [], er_key: []}
    for n, radius in UDG_LADDER + (UDG_LADDER_SLOW if slow else ()):
        inst = udg_instance(n, radius, seed)
        if inst is None:
            continue
        edges, weights, _ = inst
        out[udg_key].append(run_bbcvc(edges, weights, _k_for(edges, n),
                                      scheduler="sync", params=params,
                                      max_ms=max_ms))
    for n, prob in ER_LADDER + (ER_LADDER_SLOW if slow else ()):
        inst = er_instance(n, prob, seed)
        if inst is None:
            continue
        edges, weights = inst
        out[er_key].append(run_bbcvc(edges, weights, _k_for(edges, n),
                                     scheduler="sync", params=params,
                                     max_ms=max_ms))
    return out


def analytic_size_curve(degrees: Sequence[int] = ()) -> Dict[str, List[Tuple[int, int]]]:
    """Kodlama başına ÇERÇEVE BOYU / DÜĞÜM DERECESİ — v5_wuli'nin kanonik eğrisi.

    Aritmetiği burada yeniden yazmam: `v5_wuli.size_curve()` her baytı
    `wire.hello_size(...)`'tan alıyor, dolayısıyla telin başlığı değişirse eğri
    onunla birlikte oynar. İki kopya tutmak, ikisinin sessizce ayrışması demek.
    """
    from ccvc.bb import v5_wuli

    degs = list(degrees) or [2, 4, 8, 16, 24, 32, 40, 48, 56, 64, 80, 100,
                             117, 118, 130]
    out: Dict[str, List[Tuple[int, int]]] = {}
    for r in v5_wuli.size_curve(degs):
        out.setdefault(str(r["encoding"]), []).append(
            (int(r["degree"]), int(r["frame_bytes"])))
    for v in out.values():
        v.sort()
    return out


def figure_message_size(points: Mapping[str, Sequence[SizePoint]], outdir: str, *,
                        analytic: bool = True,
                        name: str = "fig6_message_size") -> FigureResult:
    """Varyant başına ölçülen yük, ANALİTİK boy eğrisi, toplam hacim ve kalite.

    DÖRT PANEL, VE İKİSİNİN X EKSENİ AYNI ŞEY DEĞİL — karıştırmak ölçüm hatası
    olurdu:

      (a) ölçülen `max_payload` / ORTALAMA derece — koşumdan gelen gözlem;
      (b) analitik çerçeve boyu / DÜĞÜM derecesi — aritmetik, gözlem değil;
      (c) ölçülen `bytes_tx` düğüm başına / ortalama derece;
      (d) ölçülen omurga büyüklüğü / ortalama derece — KALİTE ekseni.

    (b) ayrı durur çünkü çerçeve boyu düğümün KENDİ derecesinin fonksiyonudur,
    ortalamanın değil; ikisini tek eksende çizmek iki farklı büyüklüğü
    üst üste bindirmek olurdu.

    250 B TAVANI ÖLÇÜLEBİLİR DEĞİLDİR ve (b) bunu söyler. Tam liste 250 B'ye
    derece 118'de varır, ama komşu tablosu 64 girişte dolar ve taşma koşumu
    `RunInvalid` ile geçersiz kılar; yani rapor edilebilir en yoğun koşumda
    çerçeve 143 B, tavanın ancak yarısı. Sınır telde değil BELLEKTE. BULGU 3'ün
    "118 girişte 250 B" cümlesi de aynı aritmetik ve aynı ulaşılmazlık.

    (d) Bloom kolu için zorunlu: yalnız yüke bakan bir okuyucu Bloom'u kazanan
    sanır; 64 baytlık özet bu derecelerde yerine geçtiği listeden büyüktür VE
    omurgayı bütün düğüm kümesine şişirir.
    """
    if not points:
        raise MissingData("şekil 6 için hiç varyant verilmedi")
    bad = sorted(k for k, v in points.items()
                 if any(not isinstance(p, SizePoint) for p in v))
    if bad:
        raise MissingData(
            f"şekil 6 artık SizePoint bekliyor, ham koşum değil ({bad}); "
            "size_points_from_runs() ya da size_points_from_rows() kullanın")
    empty = sorted(k for k, v in points.items() if not v)
    if empty:
        raise MissingData(
            f"şu varyantların tek ölçümü yok: {empty}; boş eğri çizmek o varyant "
            "için ölçüm yapılmış izlenimi verirdi")

    markers = ["o", "s", "D", "^", "v", "P", "X", "*"]
    fills = ["#1a1a1a", "#ffffff", "#8c8c8c", "#dcdcdc", "#5a5a5a", "#ededed",
             "#3f3f3f", "#b5b5b5"]
    styles = ["-", "--", "-.", ":"]
    fig, axg = plt.subplots(2, 2, figsize=(11.6, 7.4))
    axes = axg.ravel()
    summary: Dict[str, Dict[str, float]] = {}
    any_quality = False

    for i, label in enumerate(sorted(points)):
        pts = sorted(points[label], key=lambda p: (p.avg_degree, p.n, p.m))
        xs = [p.avg_degree for p in pts]
        pay = [p.max_payload for p in pts]
        byt = [p.bytes_tx / p.n for p in pts]
        kw = {"color": "#000000", "lw": 1.3, "ls": styles[i % 4], "zorder": 3,
              "label": label}
        sk = {"s": 56, "marker": markers[i % len(markers)],
              "facecolors": fills[i % len(fills)], "edgecolors": "#000000",
              "linewidths": 1.0, "zorder": 4}
        for ax, ys in ((axes[0], pay), (axes[2], byt)):
            ax.plot(xs, ys, **kw)
            ax.scatter(xs, ys, **sk)
        qual = [(p.avg_degree, p.backbone / p.n) for p in pts
                if p.backbone is not None]
        if qual:
            any_quality = True
            axes[3].plot([q[0] for q in qual], [q[1] for q in qual], **kw)
            axes[3].scatter([q[0] for q in qual], [q[1] for q in qual], **sk)
        bad_pts = [(p.avg_degree, p.max_payload) for p in pts if not p.converged]
        if bad_pts:
            axes[0].scatter([b[0] for b in bad_pts], [b[1] for b in bad_pts],
                            s=165, marker="o", facecolors="none",
                            edgecolors="#000000", linewidths=0.9,
                            linestyle=":", zorder=5)
        summary[label] = {
            "payload_min": float(min(pay)), "payload_max": float(max(pay)),
            "payload_span": float(max(pay) - min(pay)),
            "bytes_min": float(min(p.bytes_tx for p in pts)),
            "bytes_max": float(max(p.bytes_tx for p in pts)),
            "bytes_per_node_min": round(float(min(byt)), 3),
            "bytes_per_node_max": round(float(max(byt)), 3),
            "deg_min": float(min(xs)), "deg_max": float(max(xs)),
            "n_min": float(min(p.n for p in pts)),
            "n_max": float(max(p.n for p in pts)),
            "points": float(len(pts)), "not_converged": float(len(bad_pts)),
        }
        if qual:
            summary[label]["backbone_frac_min"] = round(min(q[1] for q in qual), 4)
            summary[label]["backbone_frac_max"] = round(max(q[1] for q in qual), 4)

    # --- (b) ANALİTİK panel: eksen DÜĞÜM derecesi, ölçüm değil aritmetik ----
    table_cap = _nbr_table_max()
    analytic_info: Dict[str, Any] = {"drawn": False}
    if analytic:
        try:
            curves = analytic_size_curve()
        except Exception as exc:                  # noqa: BLE001
            raise MissingData(
                f"analitik boy eğrisi alınamadı ({exc}); elle yeniden "
                "hesaplamam, iki kopya sessizce ayrışır") from exc
        for j, (enc, pairs) in enumerate(sorted(curves.items())):
            axes[1].plot([d for d, _ in pairs], [b for _, b in pairs],
                         color="#000000", lw=1.1, ls=styles[j % 4],
                         label=f"{enc} (analitik)", zorder=2)
        axes[1].axhline(MAX_PAYLOAD, color="#000000", lw=1.6)
        axes[1].axvline(table_cap, color="#000000", lw=1.2, ls=(0, (1, 1)))
        full = dict(curves.get("full", []))
        at_cap = full.get(table_cap)
        crossing = min((d for d, b in sorted(full.items()) if b > MAX_PAYLOAD),
                       default=None)
        axes[1].annotate(
            f"komşu tablosu {table_cap} giriş\nGEÇERLİ koşumun duvarı"
            + (f" ({at_cap} B)" if at_cap else ""),
            (table_cap, MAX_PAYLOAD * 0.62), ha="right", va="center",
            fontsize=7, xytext=(-6, 0), textcoords="offset points")
        if crossing:
            axes[1].annotate(f"{MAX_PAYLOAD} B ancak derece {crossing}'de;\n"
                             "tabloyu aştığı için ÖLÇÜLEMEZ",
                             (0.98, MAX_PAYLOAD), xycoords=("axes fraction", "data"),
                             ha="right", va="bottom", fontsize=7)
        analytic_info = {"drawn": True, "table_cap_degree": table_cap,
                         "bytes_at_table_cap": at_cap,
                         "ceiling_crossing_degree": crossing,
                         "encodings": sorted(curves)}
        axes[1].set_ylim(0, MAX_PAYLOAD * 1.18)
    else:
        axes[1].axis("off")
        axes[1].text(0.5, 0.5, "analitik eğri istenmedi", ha="center",
                     va="center", transform=axes[1].transAxes, fontsize=8)

    axes[0].set_title("(a) ÖLÇÜLEN max_payload / ortalama derece", fontsize=9)
    axes[0].set_ylabel("max_payload (bayt)")
    axes[1].set_title("(b) ANALİTİK çerçeve boyu / DÜĞÜM derecesi", fontsize=9)
    axes[1].set_xlabel("düğümün kendi derecesi")
    axes[1].set_ylabel("çerçeve (bayt)")
    axes[2].set_title("(c) ÖLÇÜLEN bytes_tx / |V|", fontsize=9)
    axes[2].set_ylabel("bytes_tx / |V| (bayt)")
    axes[2].set_yscale("log")
    axes[3].set_title("(d) ÖLÇÜLEN omurga / |V| — kalite", fontsize=9)
    axes[3].set_ylabel("|B| / |V|")
    if not any_quality:
        axes[3].text(0.5, 0.5, "omurga ölçümü yok:\nkalite ekseni çizilmedi",
                     ha="center", va="center", transform=axes[3].transAxes,
                     fontsize=8, color="#555555")
    spans = {(v["n_min"], v["n_max"]) for v in summary.values()}
    if len(spans) == 1:
        lo_n, hi_n = spans.pop()
        rng = f"|V|={int(lo_n)}" + ("" if lo_n == hi_n else f"–{int(hi_n)}")
        base_x = f"ortalama derece  (bütün seriler {rng})"
    else:
        base_x = "ortalama derece"
    for ax in (axes[0], axes[2], axes[3]):
        ax.set_xlabel(base_x, fontsize=7.5)
    for ax in axes:
        ax.grid(color="#ececec", lw=0.6)
        ax.set_axisbelow(True)
    for ax in (axes[0], axes[1]):
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=6.8, frameon=False)
    fig.suptitle("Mesaj boyutu: ölçülen, analitik, hacim ve kalite", fontsize=10)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))

    flat = [k for k, v in summary.items() if v["payload_span"] <= 2]
    rising = [k for k, v in summary.items() if v["payload_span"] > 2]
    over = [k for k, v in summary.items() if v["payload_max"] > MAX_PAYLOAD]

    def _name(group: List[str]) -> str:
        if not group:
            return "hiçbir"
        if len(group) <= 2:
            return " ve ".join(group)
        return f"{len(group)} seri (ör. {group[0]})"

    smallest = min(summary, key=lambda kk: summary[kk]["payload_max"])
    heaviest = max(summary, key=lambda kk: summary[kk]["bytes_per_node_max"])
    tradeoff = ""
    if heaviest != smallest and len(summary) > 1:
        tradeoff = (f" En küçük çerçeveyi {smallest} taşırken düğüm başına en "
                    f"çok baytı {heaviest} harcar: çerçeveyi küçültmek toplam "
                    "hacmi küçültmez.")
    quality = ""
    if any_quality:
        worst = max((k for k in summary if "backbone_frac_max" in summary[k]),
                    key=lambda kk: summary[kk]["backbone_frac_max"], default=None)
        if worst:
            quality = (f" Kalite ekseninde en kötüsü {worst}: omurgası "
                       f"|V|'nin %{round(100 * summary[worst]['backbone_frac_max'])}"
                       " kadarına şişer.")
    ceiling = ""
    if analytic_info.get("drawn"):
        ceiling = (f" {MAX_PAYLOAD} B tavanı ÖLÇÜLEBİLİR DEĞİLDİR: aritmetik onu "
                   f"derece {analytic_info['ceiling_crossing_degree']}'e koyar ama "
                   f"komşu tablosu {analytic_info['table_cap_degree']} girişte "
                   "dolup koşumu geçersiz kılar, yani sınır telde değil bellekte.")
    return _save(fig, outdir, name,
                 "Bu şekil çerçeve boyutu, toplam hacim ve kaliteyi birlikte "
                 f"doğrular: max_payload {_name(flat)} seride düz, "
                 f"{_name(rising)} seride yükselir." + tradeoff + quality
                 + ceiling,
                 data={"summary": summary, "flat": flat, "rising": rising,
                       "over_ceiling": over, "smallest_frame": smallest,
                       "heaviest_total": heaviest, "analytic": analytic_info,
                       "has_quality": any_quality})


def _nbr_table_max() -> int:
    from ccvc.bb.bootstrap import BootstrapParams
    return int(BootstrapParams().nbr_table_max)


# ==========================================================================
# ŞEKİL 7 — Senkron / asenkron karşılaştırması
# ==========================================================================
def figure_sync_vs_async(sync_run: BbcvcRun, async_run: BbcvcRun, outdir: str, *,
                         pos: Optional[Pos] = None,
                         name: str = "fig7_sync_async") -> FigureResult:
    """Aynı topolojide iki zamanlayıcı: C farkı, Σw, tx ve yakınsama süresi.

    YAKINSAMA HER İKİSİNDE DE MİLİSANİYEDİR. Senkronun 53 slotunu asenkronun
    6371 ms'siyle aynı eksende çizmek iki farklı birimi kıyaslamak olurdu;
    senkron süre `slot × τ` ile ms'ye çevrilir, slot sayısı etikete yazılır.
    """
    vs = view_of(sync_run, pos=pos)
    va = view_of(async_run, pos=vs.pos)
    cs, ca = set(vs.cover), set(va.cover)
    only_s, only_a = sorted(cs - ca), sorted(ca - cs)
    diff = only_s + only_a

    fig = plt.figure(figsize=(10.8, 5.0))
    gs = fig.add_gridspec(2, 3, width_ratios=(2.5, 1, 1), wspace=0.35,
                          hspace=0.55)
    ax = fig.add_subplot(gs[:, 0])
    _draw_edges(ax, vs, vs.roles, backbone_width=2.4, base_width=0.8)
    _draw_nodes(ax, vs, vs.roles, size=260, label_size=6.2)
    if diff:
        ax.scatter([vs.pos[x][0] for x in diff], [vs.pos[x][1] for x in diff],
                   s=760, marker="o", facecolors="none", edgecolors="#000000",
                   linewidths=2.0, linestyle="--", zorder=6)
    _frame_off(ax)
    ax.set_anchor("C")
    ax.set_title("Aynı topoloji, iki zamanlayıcı\n"
                 + (f"yalnız sync: {only_s or '—'} · yalnız async: {only_a or '—'}"
                    if diff else "C AYNI: sync ve async aynı örtüye yakınsadı"),
                 fontsize=8.5)

    t_sync = sync_run.t_conv_ms or (sync_run.slots or 0) * _tau_of(sync_run)
    t_async = async_run.t_conv_ms or 0
    metrics = [
        ("Σw (ağırlık)", sync_run.total_weight, async_run.total_weight, "{:g}"),
        ("|C|", len(cs), len(ca), "{:g}"),
        ("tx (iletim)", sync_run.tx, async_run.tx, "{:g}"),
        (f"yakınsama (ms)\nsync = {sync_run.slots or 0} slot", t_sync, t_async,
         "{:g}"),
    ]
    for j, (lab, a, b, fmt) in enumerate(metrics):
        cell = fig.add_subplot(gs[j // 2, 1 + (j % 2)])
        cell.bar([0], [a], width=0.6, color="#3a3a3a", edgecolor="#000000")
        cell.bar([1], [b], width=0.6, color="#cfcfcf", edgecolor="#000000",
                 hatch="///")
        cell.set_xticks([0, 1])
        cell.set_xticklabels(["sync", "async"], fontsize=7)
        cell.set_title(lab, fontsize=8)
        for x, val in ((0, a), (1, b)):
            cell.annotate(fmt.format(val), (x, val), ha="center", va="bottom",
                          fontsize=7)
        cell.margins(y=0.28)
        cell.grid(axis="y", color="#ececec", lw=0.6)
        cell.set_axisbelow(True)
        cell.tick_params(labelsize=7)
    fig.text(0.02, 0.015,
             "Faz 0-3 kararları belirlenimci anahtarla verildiğinden iki kip aynı "
             "C'ye yakınsamalıdır; fark çıkarsa Faz 4 sahipliktedir (brief 3.2).",
             fontsize=6.8, ha="left", va="bottom", color="#444444")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.88, bottom=0.12)
    same = "C AYNI" if not diff else f"C FARKLI ({len(diff)} düğüm: {diff})"
    return _save(fig, outdir, name,
                 f"Bu şekil iki zamanlayıcının aynı algoritmayı koştuğunu doğrular: "
                 f"aynı topolojide {same}, ağırlık {sync_run.total_weight:g} / "
                 f"{async_run.total_weight:g}, iletim {sync_run.tx} / {async_run.tx}, "
                 f"yakınsama {t_sync} / {t_async} ms.",
                 data={"only_sync": only_s, "only_async": only_a,
                       "same_cover": not diff,
                       "t_conv_ms": {"sync": t_sync, "async": t_async}})


# --- şekil 8 için GERÇEK ölçümden anytime izi ------------------------------
def anytime_trace_from_budgets(edges: Sequence[Edge], weights: Mapping[int, float],
                               k: int, budgets: Sequence[int], *,
                               variant: str = "MIS-Connector-Backbone",
                               scheduler: str = "sync",
                               params: Any = None) -> Any:
    """Aynı örneği ARTAN duvar bütçeleriyle koşarak anytime izi ölç.

    Her nokta GERÇEK bir koşumdur: bütçe t'de durdurulmuş çözümün doğrulayıcıdan
    geçip geçmediğine BAKILIR ve yalnız geçtiyse ağırlık yazılır. Bu ayrım
    süsleme değil: çalışan örnekte 3000 ms'de düğüm kodu Σw=21 bildiriyor ama o
    örtü henüz geçerli değil; ham sayıyı yazsaydık iz 21'den 27'ye ÇIKAR ve
    "o ana kadarki en iyi azalır" sözleşmesini ihlal ederdi. Yani doğrulayıcı
    kapısı olmadan bu izin kendisi yalan olurdu.

    BB-CVC anytime DEĞİLDİR: ilk geçerli çözümden önce hiçbir şey, sonra sabit
    bir değer verir. İz bunu olduğu gibi gösterir; ANNEAL'ın eğrisi yanına
    konduğunda fark tam olarak budur.
    """
    from ccvc.bb import bbcvc as _bb
    from ccvc.bb.sweep import AnytimeSample, AnytimeTrace

    graph = validate.make_graph(list(edges), k, dict(weights))
    samples: List[AnytimeSample] = []
    best: Optional[float] = None
    for b in sorted(budgets):
        run = _bb.run_bbcvc(list(edges), dict(weights), k, scheduler=scheduler,
                            max_ms=int(b), params=params)
        tot = run.outcome.totals()
        rep = validate.validate(graph, run.cover, run.owner)
        if rep.valid and (best is None or run.total_weight < best):
            best = float(run.total_weight)
        cur = float(run.total_weight) if rep.valid else None
        samples.append(AnytimeSample(
            t_ms=int(run.t_conv_ms or b), energy_mah=float(tot.energy_mah()),
            tx=int(run.tx), observer_best_weight=best,
            cover_size=len(run.cover) if best is not None else None,
            current_weight=cur))
    trace = AnytimeTrace(variant=variant, samples=samples)
    trace.check()
    return trace


# ==========================================================================
# ŞEKİL 8 — Anneal-Local: enerji-zaman ve ilk geçerli çözüme kadar geçen süre
# ==========================================================================
def figure_anneal_anytime(traces: Sequence[Any], outdir: str, *,
                          final_weights: Optional[Mapping[str, float]] = None,
                          name: str = "fig8_anneal_anytime") -> FigureResult:
    """Anneal-Local anytime görünümü: enerji-zaman, yörünge + zarf, ilk geçerli an.

    `traces`: `ccvc.bb.sweep.AnytimeTrace` dizisi. İZ KENDİNİ DOĞRULAR
    (`check()`): örnekler zaman sırasında, enerji birikimli, gözlemci zarfı
    azalan. Biri tutmuyorsa şekil ÇİZİLMEZ.

    İKİ EĞRİ, ÇÜNKÜ RAPORLANAN SAYI ZARF DEĞİL:
      * `current_weight` — o anki durumun ağırlığı, YÖRÜNGE. Monoton değildir;
        Metropolis yokuş yukarı hamle kabul eder ve son durum ziyaret edilen
        en iyi durum değil bir yerel minimumdur.
      * `observer_best_weight` — o ana kadar görülen en iyi, ZARF. Monotondur.

    60 tohumda 29'unda son durum zarftan KÖTÜ (ortalama fark 2,17, en çok 8,0),
    yani ikisi tohumların yarısında ayrışıyor. Yalnız zarfı çizmek, tablodaki
    sayıya yakınsamayan bir "istikrarlı iyileşme" anlatırdı; yalnız yörüngeyi
    çizmek de sınırı gizlerdi. Sapmalar gürültü değil MEKANİZMADIR: gösterilen
    farkın açıklaması onlardır.

    `final_weights`: kol adı -> raporlanan son durum ağırlığı. Verilirse panel
    (b)'ye yatay çizgi olarak işlenir; RAPORLANAN SAYI budur, zarf değil.
    """
    if not traces:
        raise MissingData(
            "şekil 8 için anytime izi yok. Anneal-Local sonucunda `trace` alanı "
            "(ccvc.bb.sweep.AnytimeTrace) döndürmeli; iz olmadan enerji-zaman "
            "eğrisi çizilemez, uydurulamaz")
    for t in traces:
        if not hasattr(t, "samples") or not hasattr(t, "check"):
            raise MissingData(
                f"şekil 8: {type(t).__name__} AnytimeTrace değil; sözleşme "
                "ccvc.bb.sweep.AnytimeTrace")
        t.check()          # bozuk iz burada patlar, grafikte gizlenmez

    labels = [f"{t.variant}#{i + 1}" for i, t in enumerate(traces)]
    styles = ["-", "--", "-.", ":"]
    markers = ["o", "s", "D", "^", "v", "P"]
    fills = ["#1a1a1a", "#ffffff", "#8c8c8c", "#dcdcdc", "#5a5a5a", "#ededed"]

    fig, axes = plt.subplots(1, 3, figsize=(13.4, 4.6))
    ttfv: List[Optional[int]] = []
    summary: Dict[str, Any] = {}
    any_traj = False
    for i, (lab, t) in enumerate(zip(labels, traces)):
        ts = [s.t_ms for s in t.samples]
        en = [s.energy_mah for s in t.samples]
        axes[0].plot(ts, en, color="#000000", lw=1.3, ls=styles[i % 4], label=lab)

        traj = [(s.t_ms, s.current_weight) for s in t.samples
                if s.current_weight is not None]
        if traj:
            any_traj = True
            axes[1].plot([x for x, _ in traj], [y for _, y in traj],
                         color="#8c8c8c", lw=0.9, ls="-", zorder=2,
                         label=f"{lab} yörünge (o anki)")
        valid = [s for s in t.samples if s.valid]
        if valid:
            axes[1].step([s.t_ms for s in valid],
                         [s.observer_best_weight for s in valid], where="post",
                         color="#000000", lw=1.5, ls=styles[i % 4], zorder=3,
                         label=f"{lab} gözlemci zarfı")
            first = valid[0]
            axes[1].scatter([first.t_ms], [first.observer_best_weight], s=95,
                            marker=markers[i % len(markers)],
                            facecolors=fills[i % len(fills)],
                            edgecolors="#000000", linewidths=1.2, zorder=5)
        fw = (final_weights or {}).get(t.variant, (final_weights or {}).get(lab))
        if fw is not None:
            axes[1].axhline(float(fw), color="#000000", lw=1.1, ls=(0, (1, 1)),
                            zorder=4)
            axes[1].annotate(f"raporlanan son durum {float(fw):g}",
                             (0.99, float(fw)),
                             xycoords=("axes fraction", "data"), ha="right",
                             va="bottom", fontsize=7)
        first_ms = t.t_first_valid_ms
        ttfv.append(first_ms)
        summary[lab] = {
            "t_first_valid_ms": first_ms,
            "samples": len(t.samples),
            "energy_total_mah": round(float(en[-1]), 6) if en else None,
            "observer_best_weight": (round(float(valid[-1].observer_best_weight), 6)
                                     if valid else None),
            "final_weight_reported": None if fw is None else float(fw),
            "trajectory_points": len(traj),
            "t_end_ms": ts[-1] if ts else None,
        }

    known = [(lab, v) for lab, v in zip(labels, ttfv) if v is not None]
    never = [lab for lab, v in zip(labels, ttfv) if v is None]
    if known:
        axes[2].bar(range(len(known)), [v for _, v in known], width=0.6,
                    color="#3a3a3a", edgecolor="#000000")
        axes[2].set_xticks(range(len(known)))
        axes[2].set_xticklabels([lab for lab, _ in known], rotation=45,
                                ha="right", fontsize=7)
        for j, (_, v) in enumerate(known):
            axes[2].annotate(f"{v}", (j, v), ha="center", va="bottom", fontsize=7)
    if never:
        axes[2].set_xlabel(f"{len(never)} koşum hiç geçerli çözüme ulaşmadı: "
                           + ", ".join(never[:4])
                           + ("…" if len(never) > 4 else ""), fontsize=7.5)
    if not known:
        axes[2].set_yticks([])

    axes[0].set_title("(a) enerji-zaman", fontsize=9)
    axes[0].set_xlabel("zaman (ms)")
    axes[0].set_ylabel("birikimli enerji (mAh)")
    axes[1].set_title("(b) yörünge ve gözlemci zarfı", fontsize=9)
    axes[1].set_xlabel("zaman (ms)")
    axes[1].set_ylabel("Σw")
    axes[2].set_title("(c) ilk geçerli çözüme kadar", fontsize=9)
    axes[2].set_ylabel("ms")
    for ax in axes[:2]:
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=6.5, frameon=False)
    for ax in axes:
        ax.grid(color="#ececec", lw=0.6)
        ax.set_axisbelow(True)
    who = ", ".join(sorted({t.variant for t in traces}))
    fig.suptitle(f"Anytime görünüm — durdurulduğu anda elindeki çözüm: {who}",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))

    covered = []
    for lab, t in zip(labels, traces):
        ts = [s.t_ms for s in t.samples]
        span = (ts[-1] - ts[0]) or 1
        first = t.t_first_valid_ms
        covered.append(0.0 if first is None else (ts[-1] - first) / span)
    got = len(known)
    frac = round(100.0 * (statistics.mean(covered) if covered else 0.0))
    # ZORUNLU ETİKET: zarf bir GÖZLEMCİ sınırıdır. Çıplak bırakılırsa sistemin
    # kendisi hakkında bildiği bir şey diye okunur.
    from ccvc.bb.sweep import AnytimeTrace as _AT
    caption = (f"Bu şekil anytime davranışını ölçer: {got}/{len(traces)} koşum "
               "geçerli bir çözüme ulaşmış, zaman ekseninin ortalama "
               f"%{frac} kadarında elde geçerli bir çözüm bulunmuştur. "
               "İnce gri çizgi o anki durumu, kalın çizgi gözlemci zarfını "
               f"gösterir ({_AT.OBSERVER_LABEL}); RAPORLANAN SAYI zarf değil "
               "son donmuş durumdur"
               + (" ve nokta çizgiyle işaretlidir." if final_weights else "."))
    if not any_traj:
        caption += (" Yörünge çizilmedi: izler `current_weight` taşımıyor, "
                    "dolayısıyla salınımlar ölçülmemiştir.")
    return _save(fig, outdir, name, caption,
                 data={"traces": summary, "never_valid": never,
                       "valid_axis_fraction": dict(zip(labels, covered)),
                       "has_trajectory": any_traj,
                       "observer_label": _AT.OBSERVER_LABEL,
                       "t_first_valid_ms": dict(zip(labels, ttfv))})


# ==========================================================================
# Hepsi birden
# ==========================================================================
def default_run_id(run: BbcvcRun) -> str:
    n = len(run.nodes)
    m = len(run.net.edges)  # type: ignore[attr-defined]
    k = int(next(iter(run.nodes.values())).k) if run.nodes else 0
    return f"n{n}_m{m}_k{k}_{run.outcome.scheduler}"


def make_all_figures(sync_run: BbcvcRun, outdir: str, *,
                     async_run: Optional[BbcvcRun] = None,
                     pos: Optional[Pos] = None,
                     size_series: Optional[Mapping[str, Sequence[BbcvcRun]]] = None,
                     size_points: Optional[Mapping[str, Sequence[SizePoint]]] = None,
                     anneal_traces: Optional[Sequence[Any]] = None,
                     anneal_final_weights: Optional[Mapping[str, float]] = None,
                     bootstrap: Optional[Sequence[BootstrapPoint]] = None,
                     ) -> Dict[str, FigureResult]:
    """brief §8'in yedi şekli; `outdir` genelde `results/bb/figures/<run_id>/` olur."""
    os.makedirs(outdir, exist_ok=True)
    v = view_of(sync_run, pos=pos)
    h = history_from_run(sync_run)
    out: Dict[str, FigureResult] = {}
    out["topology"] = figure_topology(sync_run, outdir, view=v)
    out["ownership"] = figure_ownership(sync_run, outdir, view=v)
    out["phases"] = figure_phase_snapshots(sync_run, outdir, view=v, history=h)
    out["convergence"] = figure_convergence(sync_run, outdir, history=h)
    runs = {"sync": sync_run}
    if async_run is not None:
        runs["async"] = async_run
    out["messages"] = figure_message_breakdown(runs, outdir)
    pts = dict(size_points or {})
    if size_series:
        pts.update(size_points_from_runs(size_series))
    if pts:
        out["message_size"] = figure_message_size(pts, outdir)
    if anneal_traces:
        out["anneal"] = figure_anneal_anytime(
            anneal_traces, outdir, final_weights=anneal_final_weights)
    if bootstrap:
        out["bootstrap"] = figure_bootstrap_identity(bootstrap, outdir)
    if async_run is not None:
        out["sync_async"] = figure_sync_vs_async(sync_run, async_run, outdir,
                                                 pos=v.pos)
    write_index(out, outdir)
    return out


def write_index(figs: Mapping[str, FigureResult], outdir: str) -> str:
    """`summary.md`'ye gömülecek parça: her şeklin altında tek cümle (brief §8)."""
    lines = ["# Şekiller", ""]
    for key in sorted(figs):
        f = figs[key]
        lines.append(f"![{f.name}]({os.path.basename(f.paths[0])})")
        lines.append("")
        lines.append(f.caption)
        lines.append("")
    path = os.path.join(outdir, "index.md")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.replace(tmp, path)
    return path
