#!/usr/bin/env python3
"""CCVC görselleştirme (F6): örtü kümesi, kenar sahipliği, kapasite doluluğu.

Koş:
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m ccvc.visualize \
      --frames results/mds_campus_seed0_frames.json --name kampus_drone \
      --k 3 --weight random --seed 0 --solver grccvc

Üç şeyi aynı anda gösterir, çünkü CCVC'nin üç kısıtı var:
  * ÖRTÜ       hangi düğümler seçildi (büyük, dolu)
  * SAHİPLİK   her kenarın hangi ucun hesabına yazıldığı (kenarın sahip tarafı koyu)
  * KAPASİTE   her seçili düğümün yükü / k (halka göstergesi)

Ayrıca bağlılığın bileşen bazlı olduğu görünür: ayrı bileşenler ayrı örtü
parçalarıyla çözülür, aralarında köprü YOKTUR ve olmamalıdır.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Circle, Polygon, Wedge

from . import bridge, central
from .bridge import CcvcGraph

DEEP = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860"]
COVER_C = "#2F5DA8"
OWN_C = "#1F3F72"
FREE_C = "#B9C0C9"
CUT_C = "#C44E52"


def draw_buildings(ax, buildings: Sequence[dict], altitude: float, half: float) -> None:
    for b in buildings:
        obs = b["h"] >= altitude
        ax.add_patch(
            Polygon(
                b["ring"],
                closed=True,
                facecolor="#9CA5B0" if obs else "#E3E3E3",
                edgecolor="#6B7580" if obs else "#CCCCCC",
                lw=0.4,
                zorder=0,
            )
        )
    ax.set_xlim(-half, half)
    ax.set_ylim(-half, half)
    ax.set_aspect("equal")


def solve_frame(
    frame: dict, k: int, weight_scheme: str, seed: int, solver: str
) -> Tuple[CcvcGraph, Optional[List[int]], Dict, str]:
    """Bir kareyi çöz. Uygunsuzsa cover None döner ve durum yazılır."""
    g = bridge.graph_from_frame(
        frame, capacity_k=k, weight_scheme=weight_scheme, seed=seed
    )
    try:
        r = central.solve(solver, g)
        cover = list(getattr(r, "cover", []) or [])
    except central.CcvcInfeasible:
        return g, None, {}, "uygunsuz"
    except Exception as exc:  # noqa: BLE001
        return g, None, {}, f"hata: {type(exc).__name__}"
    v = bridge.verify(g, cover)
    if not v.valid:
        return g, cover, v.owner, "kapı düştü"
    return g, cover, v.owner, "ok"


def render(
    frames: Sequence[dict],
    buildings: Sequence[dict],
    k: int,
    weight_scheme: str,
    seed: int,
    solver: str,
    half: float,
    altitude: float,
    out: str,
    title_extra: str = "",
) -> Dict[str, Any]:
    """Kare dizisini çözüp animasyon üretir; özet istatistik döndürür."""
    solved = []
    for f in frames:
        g, cover, owner, status = solve_frame(f, k, weight_scheme, seed, solver)
        comps = [c for c in bridge.graph_components(g) if len(c) > 1]
        load: Dict[int, int] = {}
        for e, o in (owner or {}).items():
            load[o] = load.get(o, 0) + 1
        solved.append(
            {
                "frame": f,
                "g": g,
                "cover": cover,
                "owner": owner or {},
                "status": status,
                "load": load,
                "ncomp": len(comps),
            }
        )

    fig = plt.figure(figsize=(13.5, 6.4))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.3, 1], hspace=0.42, wspace=0.22)
    ax = fig.add_subplot(gs[:, 0])
    ax1 = fig.add_subplot(gs[0, 1])
    ax2 = fig.add_subplot(gs[1, 1])
    fig.suptitle(
        f"Connected capacitated vertex cover, {solver.upper()}, k = {k}, "
        f"weights = {weight_scheme}{title_extra}",
        fontsize=11,
    )

    def draw(i: int) -> None:
        s = solved[i]
        g, cover, owner, load = s["g"], s["cover"], s["owner"], s["load"]
        pos = {v: g.pos[v] for v in g.nodes}
        ax.clear()
        draw_buildings(ax, buildings, altitude, half)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        cov = set(cover or [])
        head = (
            f"kare {i}   |C| = {len(cov)}   bileşen = {s['ncomp']}   "
            f"kenar = {len(g.edges)}"
        )
        if s["status"] != "ok":
            head += f"   [{s['status']}]"
        ax.set_title(head, fontsize=9)

        # kenarlar: sahip tarafı koyu, diğer yarısı açık
        for u, v in g.edges:
            pu, pv = pos[u], pos[v]
            mid = ((pu[0] + pv[0]) / 2, (pu[1] + pv[1]) / 2)
            o = owner.get((u, v))
            if o is None:
                ax.plot(
                    [pu[0], pv[0]],
                    [pu[1], pv[1]],
                    color=CUT_C,
                    lw=1.0,
                    ls=":",
                    zorder=2,
                )
                continue
            near, far = (pu, pv) if o == u else (pv, pu)
            ax.plot([near[0], mid[0]], [near[1], mid[1]], color=OWN_C, lw=1.9, zorder=3)
            ax.plot([mid[0], far[0]], [mid[1], far[1]], color=FREE_C, lw=1.1, zorder=2)

        # düğümler
        for v in g.nodes:
            x, y = pos[v][0], pos[v][1]
            if v in cov:
                # kapasite halkası: dolu kısım yük/k
                frac = min(1.0, load.get(v, 0) / max(1, k))
                ax.add_patch(
                    Circle(
                        (x, y),
                        4.6,
                        facecolor="white",
                        edgecolor=COVER_C,
                        lw=1.0,
                        zorder=4,
                    )
                )
                if frac > 0:
                    ax.add_patch(
                        Wedge(
                            (x, y),
                            4.6,
                            90,
                            90 - 360 * frac,
                            width=1.7,
                            facecolor=COVER_C,
                            edgecolor="none",
                            zorder=5,
                        )
                    )
                ax.scatter(
                    [x], [y], s=52, c=COVER_C, edgecolors="black", lw=0.5, zorder=6
                )
                ax.annotate(
                    f"{load.get(v, 0)}",
                    (x, y),
                    ha="center",
                    va="center",
                    fontsize=5.5,
                    color="white",
                    zorder=7,
                )
            else:
                ax.scatter(
                    [x], [y], s=26, c="white", edgecolors="#6B7580", lw=0.7, zorder=4
                )

        ax.plot([], [], color=OWN_C, lw=2, label="kenarın sahibi bu uç")
        ax.plot([], [], color=CUT_C, lw=1, ls=":", label="sahipsiz kenar")
        ax.scatter(
            [],
            [],
            s=52,
            c=COVER_C,
            edgecolors="black",
            label=f"örtüde (halka = yük/{k})",
        )
        ax.scatter([], [], s=26, c="white", edgecolors="#6B7580", label="örtü dışı")
        ax.legend(loc="lower left", fontsize=7, framealpha=0.9)

        xs = list(range(i + 1))
        ax1.clear()
        ax1.plot(
            xs,
            [len(x["cover"] or []) for x in solved[: i + 1]],
            color=COVER_C,
            lw=1.8,
            label="|C| örtü boyutu",
        )
        ax1.plot(
            xs,
            [len(x["g"].nodes) for x in solved[: i + 1]],
            color="#6B7580",
            lw=1,
            ls="--",
            label="düğüm sayısı",
        )
        ax1.plot(
            xs,
            [x["ncomp"] for x in solved[: i + 1]],
            color=DEEP[2],
            lw=1.2,
            label="çizge bileşeni",
        )
        bad = [j for j in xs if solved[j]["status"] != "ok"]
        if bad:
            ax1.scatter(
                bad, [0] * len(bad), marker="|", color=CUT_C, s=60, label="çözüm yok"
            )
        ax1.set_xlim(0, len(solved) - 1)
        ax1.set_ylim(0, max(len(x["g"].nodes) for x in solved) + 1)
        ax1.grid(alpha=0.3)
        ax1.legend(fontsize=7, loc="upper left")
        ax1.set_title("örtü boyutu ve parçalanma", fontsize=9)

        ax2.clear()
        util = []
        for x in solved[: i + 1]:
            c = x["cover"] or []
            util.append(
                100 * sum(x["load"].get(v, 0) for v in c) / max(1, k * len(c))
                if c
                else 0
            )
        ax2.plot(xs, util, color=DEEP[1], lw=1.8)
        ax2.axhline(100, color=CUT_C, lw=0.8, ls=":")
        ax2.set_xlim(0, len(solved) - 1)
        ax2.set_ylim(0, 110)
        ax2.set_xlabel("kare")
        ax2.set_ylabel("% dolu")
        ax2.grid(alpha=0.3)
        ax2.set_title(f"kapasite doluluğu (toplam yük / k·|C|)", fontsize=9)

    anim = FuncAnimation(fig, draw, frames=len(solved), interval=160)
    anim.save(out, writer=PillowWriter(fps=6))
    draw(len(solved) - 1)
    fig.savefig(out.replace(".gif", "_last.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    ok = [s for s in solved if s["status"] == "ok"]
    return {
        "frames": len(solved),
        "solved": len(ok),
        "cover_mean": (sum(len(s["cover"]) for s in ok) / len(ok)) if ok else None,
        "components_mean": sum(s["ncomp"] for s in solved) / len(solved),
        "unsolved": [s["status"] for s in solved if s["status"] != "ok"][:5],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--weight", default="random")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--solver", default="grccvc")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--outdir", default="")
    a = ap.parse_args()

    frames, meta = bridge.load_frames(a.frames)
    frames = frames[:: a.stride]
    buildings = meta.get("buildings", [])
    params = meta.get("params", {})
    half = float(params.get("half", 120.0))
    altitude = float(params.get("altitude", 5.0))
    outdir = a.outdir or os.path.join("results", "ccvc", "viz")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"{a.name}_{a.solver}_k{a.k}.gif")
    stats = render(
        frames,
        buildings,
        a.k,
        a.weight,
        a.seed,
        a.solver,
        half,
        altitude,
        out,
        title_extra=f", {a.name}",
    )
    json.dump(
        stats, open(out.replace(".gif", ".json"), "w"), indent=1, ensure_ascii=False
    )
    print(f"{out}  ->  {stats}")


if __name__ == "__main__":
    main()
