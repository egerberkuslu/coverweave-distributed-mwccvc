#!/usr/bin/env python3
"""Üç kolu yan yana gösteren CCVC karşılaştırma animasyonu.

Koş:
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m ccvc.compare_viz \
      --frames results/mds_campus_seed0_frames.json --name kampus --k 3 --stride 3

Aynı karede aynı çizge üstünde: merkezi sıralı greedy, D-REPAIR (dağıtık),
D-CDS (dağıtık). Her panelde örtü, kenar sahipliği ve kapasite doluluğu; başlıkta
optimale oran ve dağıtık kollar için GERÇEK mesaj/tur sayısı.
"""
from __future__ import annotations

import argparse, json, os
from typing import Any, Dict, List, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Circle, Polygon, Wedge

from . import bridge, central
from .d_cds import run_d_cds
from .d_repair import run_d_repair

COVER_C, OWN_C, FREE_C, CUT_C = "#2F5DA8", "#1F3F72", "#B9C0C9", "#C44E52"
DEEP = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]

ARMS = [
    ("merkezi GRCCVC\n(sıralı, tam bilgi)", lambda g: central.solve("grccvc", g), False),
    ("D-REPAIR\n(paralel, dağıtık)", lambda g: run_d_repair(g, "grccvc"), True),
    ("D-CDS\n(omurga, dağıtık)", run_d_cds, True),
]


def solve_all(frame: dict, k: int, ws: str, seed: int) -> Dict[str, Any]:
    g = bridge.graph_from_frame(frame, capacity_k=k, weight_scheme=ws, seed=seed)
    try:
        ex = central.solve_exact(g, max_n=18, time_limit_s=5.0)
        ev = bridge.verify(g, ex.cover)
        opt = ev.total_weight if ev.valid else None
    except Exception:
        opt = None
    out = {"g": g, "opt": opt, "arms": []}
    for label, fn, is_dist in ARMS:
        rec = {"label": label, "cover": None, "owner": {}, "ratio": None,
               "messages": None, "rounds": None, "status": "ok"}
        try:
            r = fn(g)
            cover = list(getattr(r, "cover", []) or [])
            v = bridge.verify(g, cover)
            rec.update(cover=cover, owner=v.owner, load={}, status="ok" if v.valid else "kapı düştü")
            if v.valid and opt:
                rec["ratio"] = v.total_weight / opt
            if is_dist:
                rec["messages"] = getattr(r, "messages", None)
                rec["rounds"] = getattr(r, "rounds", None)
        except Exception as exc:                      # noqa: BLE001
            rec["status"] = f"{type(exc).__name__}"
        ld: Dict[int, int] = {}
        for _e, o in (rec["owner"] or {}).items():
            ld[o] = ld.get(o, 0) + 1
        rec["load"] = ld
        out["arms"].append(rec)
    return out


def draw_panel(ax, g, rec, buildings, half, altitude, k) -> None:
    for b in buildings:
        obs = b["h"] >= altitude
        ax.add_patch(Polygon(b["ring"], closed=True,
                             facecolor="#A8B0B9" if obs else "#E6E6E6",
                             edgecolor="#7A838D" if obs else "#D0D0D0", lw=0.3, zorder=0))
    ax.set_xlim(-half, half); ax.set_ylim(-half, half); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    cov = set(rec["cover"] or [])
    owner, load = rec["owner"] or {}, rec["load"]
    pos = g.pos
    for (u, v) in g.edges:
        pu, pv = pos[u], pos[v]
        mid = ((pu[0] + pv[0]) / 2, (pu[1] + pv[1]) / 2)
        o = owner.get((u, v))
        if o is None:
            ax.plot([pu[0], pv[0]], [pu[1], pv[1]], color=CUT_C, lw=0.9, ls=":", zorder=2); continue
        near, far = (pu, pv) if o == u else (pv, pu)
        ax.plot([near[0], mid[0]], [near[1], mid[1]], color=OWN_C, lw=1.7, zorder=3)
        ax.plot([mid[0], far[0]], [mid[1], far[1]], color=FREE_C, lw=1.0, zorder=2)
    for v in g.nodes:
        x, y = pos[v][0], pos[v][1]
        if v in cov:
            frac = min(1.0, load.get(v, 0) / max(1, k))
            ax.add_patch(Circle((x, y), 5.0, facecolor="white", edgecolor=COVER_C, lw=0.9, zorder=4))
            if frac > 0:
                ax.add_patch(Wedge((x, y), 5.0, 90, 90 - 360 * frac, width=1.8,
                                   facecolor=COVER_C, edgecolor="none", zorder=5))
            ax.scatter([x], [y], s=44, c=COVER_C, edgecolors="black", lw=0.4, zorder=6)
        else:
            ax.scatter([x], [y], s=20, c="white", edgecolors="#7A838D", lw=0.6, zorder=4)
    parts = [f"|C| = {len(cov)}"]
    if rec["ratio"]: parts.append(f"oran {rec['ratio']:.3f}")
    if rec["messages"] is not None: parts.append(f"{rec['messages']} mesaj / {rec['rounds']} tur")
    if rec["status"] != "ok": parts.append(f"[{rec['status']}]")
    ax.set_title(rec["label"] + "\n" + "   ".join(parts), fontsize=8.5)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--k", type=int, default=3); ap.add_argument("--weight", default="random")
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--outdir", default="results/ccvc/viz")
    a = ap.parse_args()

    frames, meta = bridge.load_frames(a.frames)
    frames = frames[:: a.stride]
    buildings = meta.get("buildings", [])
    params = meta.get("params", {})
    half = float(params.get("half", 120.0)); altitude = float(params.get("altitude", 5.0))
    print(f"{len(frames)} kare çözülüyor...", flush=True)
    solved = [solve_all(f, a.k, a.weight, a.seed) for f in frames]

    fig = plt.figure(figsize=(14.5, 6.6))
    gs = fig.add_gridspec(2, 3, height_ratios=[3.1, 1.0], hspace=0.3, wspace=0.08)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    axr = fig.add_subplot(gs[1, :])
    fig.suptitle(f"Bağlı kapasiteli tepe örtüsü, aynı çizge üstünde üç kol — k = {a.k}, "
                 f"ağırlık {a.weight} ({a.name})", fontsize=11)

    def draw(i: int) -> None:
        s = solved[i]
        for ax, rec in zip(axes, s["arms"]):
            ax.clear(); draw_panel(ax, s["g"], rec, buildings, half, altitude, a.k)
        axr.clear()
        xs = list(range(i + 1))
        for j, (label, _fn, _d) in enumerate(ARMS):
            ys = [solved[q]["arms"][j]["ratio"] for q in xs]
            axr.plot(xs, [y if y else float("nan") for y in ys], color=DEEP[j], lw=1.7,
                     label=label.replace("\n", " "))
        axr.axhline(1.0, color="black", lw=0.8, ls="--", label="optimal")
        allr = [x["arms"][j]["ratio"] for x in solved for j in range(len(ARMS))
                if x["arms"][j]["ratio"]]
        axr.set_xlim(0, len(solved) - 1)
        axr.set_ylim(0.95, (max(allr) * 1.06) if allr else 2.0)  # kırpma YOK
        axr.set_xlabel("kare"); axr.set_ylabel("optimale oran")
        axr.grid(alpha=0.3); axr.legend(fontsize=7.5, ncol=4, loc="upper left")

    anim = FuncAnimation(fig, draw, frames=len(solved), interval=200)
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.join(a.outdir, f"kiyas_{a.name}_k{a.k}.gif")
    anim.save(out, writer=PillowWriter(fps=5))
    draw(len(solved) - 1)
    fig.savefig(out.replace(".gif", "_last.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("yazıldı:", out)


if __name__ == "__main__":
    main()
