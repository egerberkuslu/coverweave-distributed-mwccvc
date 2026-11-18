#!/usr/bin/env python3
"""Worked solution examples: what a VALID answer actually looks like.

The comparison figures show aggregate behaviour over many instances, which is
what a claim about quality needs, but it never shows a single answer. A reader
who has followed the algorithm through the text wants to see one instance
solved, and wants to see WHERE two arms differ on the same graph rather than
only that one produced a smaller number.

Both panels use the SAME layout for the SAME graph, so the only thing that
changes between them is the solution. Anything else would invite the reader to
read a difference in the drawing as a difference in the answer.

Only VALID solutions are drawn. An invalid cover has no business being shown as
an example of what the algorithm does, and if the run under a caption is not
clean the figure refuses to render rather than illustrating a failure as a
success.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ccvc.bb import matrix, validate  # noqa: E402
from ccvc.bb.api import Role  # noqa: E402
from ccvc.bb.bbcvc import BbcvcParams, run_bbcvc  # noqa: E402
from ccvc.bb.figures import auto_layout  # noqa: E402
from ccvc.bb.v4_mst import run_v4  # noqa: E402
from ccvc.bridge import CcvcGraph  # noqa: E402

OKABE_ITO = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
             "vermillion": "#D55E00", "grey": "#999999", "pale": "#D9D9D9",
             "black": "#000000"}

ARMS = {
    "GHS-MST-Backbone": (run_v4, OKABE_ITO["blue"]),
    "MIS-Connector-Backbone": (run_bbcvc, OKABE_ITO["orange"]),
}

plt.rcParams.update({
    "figure.dpi": 160, "savefig.dpi": 160, "font.size": 9,
    "axes.titlesize": 10, "legend.frameon": False, "legend.fontsize": 8,
})


def load_instance(stem: str, seed: int, scale: int = 10):
    cells = [c for c in matrix.feasible_cells() if c.stem == stem]
    if not cells:
        raise SystemExit(f"unknown cell {stem!r}")
    path = matrix.instance_path(cells[0], seed)
    if path is None:
        raise SystemExit(f"instance {stem} seed {seed} is not in the dataset")
    w0, e0 = matrix.load_instance(path)
    ids = sorted(w0)
    relabel = {old: i + 1 for i, old in enumerate(ids)}
    edges = sorted({(min(relabel[u], relabel[v]), max(relabel[u], relabel[v]))
                    for u, v in e0})
    weights = {relabel[o]: max(1, round(x * scale)) for o, x in w0.items()}
    return edges, weights


def solve(arm: str, edges, weights, k: int, scheduler: str, seed: int):
    fn, _ = ARMS[arm]
    params = BbcvcParams()
    params.mis_nbrs_max = 64
    res = fn(edges, weights, k, scheduler=scheduler, params=params,
             max_ms=4_000_000, seed=seed)
    graph = CcvcGraph(nodes=sorted(weights), edges=edges, weight=weights,
                      capacity_k=k)
    report = validate.validate(graph, res.cover, res.owner)
    return res, report


def _draw(ax, pos, edges, weights, res, colour, k: int):
    cover = set(res.cover)
    owner = dict(res.owner)
    # THE BACKBONE IS READ FROM THE ROLE, not from an arm-specific method.
    # `mst_internal` exists only on GHS-MST-Backbone, so keying the drawing on it marked the
    # backbone in one panel and silently left the other bare while the caption
    # promised both. MIS and CONNECTOR are the two backbone roles in every arm;
    # COVER is a node pulled in to cover an edge, which is not backbone.
    backbone = {n for n, nd in res.nodes.items()
                if Role(nd.role) in (Role.MIS, Role.CONNECTOR)}

    for u, v in edges:
        who = owner.get((min(u, v), max(u, v)))
        x = [pos[u][0], pos[v][0]]
        y = [pos[u][1], pos[v][1]]
        if who is None:
            ax.plot(x, y, color=OKABE_ITO["vermillion"], lw=2.0, zorder=1,
                    ls=":")                       # unowned: must not happen
        else:
            ax.plot(x, y, color=OKABE_ITO["pale"], lw=1.1, zorder=1)

    # an owned edge gets a short stub at its owner, so ownership is visible
    # without drawing an arrow across every edge
    for (u, v), who in owner.items():
        other = v if who == u else u
        if who not in pos or other not in pos:
            continue
        ox, oy = pos[who]
        tx, ty = pos[other]
        ax.plot([ox, ox + 0.28 * (tx - ox)], [oy, oy + 0.28 * (ty - oy)],
                color=colour, lw=2.2, zorder=2, solid_capstyle="round")

    load: Dict[int, int] = {}
    for who in owner.values():
        load[who] = load.get(who, 0) + 1
    for n, (x, y) in pos.items():
        inside = n in cover
        ax.scatter([x], [y], s=270 if inside else 150,
                   facecolor=colour if inside else "white",
                   edgecolor=(OKABE_ITO["black"] if n in backbone
                              else (colour if inside else OKABE_ITO["grey"])),
                   linewidth=2.4 if n in backbone else 1.2, zorder=3)
        ax.annotate(f"{n}", (x, y), ha="center", va="center", fontsize=7,
                    color="white" if inside else "#444444", zorder=4)
        if inside and load.get(n):
            ax.annotate(f"{load[n]}/{k}", (x, y), xytext=(0, -13),
                        textcoords="offset points", ha="center", fontsize=6,
                        color="#444444", zorder=4)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)


def _backbone(res) -> List[int]:
    """Backbone nodes read from the ROLE, never from an arm-specific field."""
    return sorted(n for n, nd in res.nodes.items()
                  if Role(nd.role) in (Role.MIS, Role.CONNECTOR))


def export_data(stem: str, seed: int, k: int, scheduler: str,
                arms: Sequence[str], path: str) -> str:
    """Write the solved instance as JSON for the figure-maker scene.

    The scene draws what this file says and nothing else, so every number in
    the published figure comes from the same solver run as the tables. A scene
    that carried its own copy of the numbers would keep printing them long
    after the solver changed its answer.
    """
    edges, weights = load_instance(stem, seed)
    pos = auto_layout(sorted(weights), edges)
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    sx = (max(xs) - min(xs)) or 1.0
    sy = (max(ys) - min(ys)) or 1.0
    norm = {n: [round((x - min(xs)) / sx, 4), round((y - min(ys)) / sy, 4)]
            for n, (x, y) in pos.items()}

    out: Dict[str, object] = {
        "meta": {"stem": stem, "seed": seed, "k": k, "scheduler": scheduler,
                 "n": len(weights), "m": len(edges)},
        "edges": [list(e) for e in edges],
        "weights": {str(n): weights[n] for n in sorted(weights)},
        "pos": {str(n): norm[n] for n in sorted(norm)},
        "arms": {},
    }
    for arm in arms:
        res, rep = solve(arm, edges, weights, k, scheduler, seed)
        if not rep.valid:
            raise SystemExit(
                f"{arm} on {stem} seed {seed} is NOT valid ({rep.summary()}). "
                "Refusing to export an invalid cover as a worked example.")
        load: Dict[int, int] = {}
        for who in res.owner.values():
            load[who] = load.get(who, 0) + 1
        out["arms"][arm] = {
            "cover": sorted(res.cover),
            "weight": round(res.total_weight),
            "backbone": _backbone(res),
            "owner": {f"{u}-{v}": w for (u, v), w in res.owner.items()},
            "load": {str(n): load[n] for n in sorted(load)},
        }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh)
    return path


def figure(stem: str, seed: int, k: int, scheduler: str, outdir: str,
           arms: Sequence[str]) -> List[str]:
    edges, weights = load_instance(stem, seed)
    pos = auto_layout(sorted(weights), edges)
    solved = []
    for arm in arms:
        res, rep = solve(arm, edges, weights, k, scheduler, seed)
        if not rep.valid:
            raise SystemExit(
                f"{arm} on {stem} seed {seed} is NOT valid ({rep.summary()}). "
                "This figure shows worked examples of correct answers; "
                "refusing to draw an invalid cover as one.")
        solved.append((arm, res, rep))

    fig, axes = plt.subplots(1, len(solved), figsize=(5.2 * len(solved), 5.0),
                             squeeze=False)
    for ax, (arm, res, _) in zip(axes[0], solved):
        _draw(ax, pos, edges, weights, res, ARMS[arm][1], k)
        ax.set_title(f"{arm}\ncover weight {res.total_weight:.0f}, "
                     f"|C| = {len(res.cover)}")

    best = min(r.total_weight for _, r, _ in solved)
    lighter = [a for a, r, _ in solved if r.total_weight == best]
    verdict = ("" if len(solved) < 2 else
               f"Both arms found the same cover, weight {best:.0f}."
               if len(lighter) == len(solved) else
               f"Lighter cover: {lighter[0]} at {best:.0f} against "
               f"{max(r.total_weight for _, r, _ in solved):.0f}.")
    fig.suptitle(f"One instance solved: {stem}, seed {seed}, k = {k}, "
                 f"{scheduler} schedule", y=1.02)
    # A DRAWN LEGEND, NOT A PARAGRAPH. Four glyphs carry what three lines of
    # prose used to: the reader matches a shape on the plot to a shape in the
    # strip instead of holding a sentence in mind while looking for it.
    from matplotlib.lines import Line2D
    ink = "#222222"
    swatch = ARMS[solved[0][0]][1]
    keys = [
        (Line2D([], [], marker="o", ls="", markersize=9, markerfacecolor=swatch,
                markeredgecolor=ink, markeredgewidth=2.0),
         "backbone (MIS / connector)"),
        (Line2D([], [], marker="o", ls="", markersize=9, markerfacecolor=swatch,
                markeredgecolor="white", markeredgewidth=0.8),
         "in cover, to cover an edge"),
        (Line2D([], [], marker="o", ls="", markersize=9, markerfacecolor="white",
                markeredgecolor="#999999", markeredgewidth=1.2),
         "outside the cover"),
        (Line2D([], [], color=swatch, lw=3.0), "stub points at the OWNER"),
        (Line2D([], [], marker="$^{3}\\!/\\!_{6}$", ls="", markersize=13,
                color="#555555"), "load against k"),
    ]
    fig.legend([h for h, _ in keys], [t for _, t in keys],
               loc="lower center", ncol=len(keys), frameon=False,
               fontsize=7.6, handletextpad=0.5, columnspacing=1.6,
               bbox_to_anchor=(0.5, -0.045))
    # One short line, and only the part a legend cannot draw: the verdict.
    fig.text(0.5, -0.085,
             "Every edge is owned exactly once and each cover is connected. "
             + verdict,
             ha="center", fontsize=7.6, color="#444444")
    fig.tight_layout()
    os.makedirs(outdir, exist_ok=True)
    name = f"solution_{stem}_s{seed}_{scheduler}"
    out = []
    for ext in ("png", "svg", "pdf"):
        p = os.path.join(outdir, f"{name}.{ext}")
        fig.savefig(p, format=ext, bbox_inches="tight")
        out.append(p)
    plt.close(fig)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stem", default="n15_m30")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--scheduler", default="sync", choices=("sync", "async"))
    ap.add_argument("--arms", default="GHS-MST-Backbone,MIS-Connector-Backbone")
    ap.add_argument("--outdir", default="results/bb/figures/solution")
    ap.add_argument("--export-json", default=None,
                    help="write the solved instance as JSON for the "
                         "figure-maker scene instead of drawing it here")
    a = ap.parse_args(argv)
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    if a.export_json:
        print("  wrote", export_data(a.stem, a.seed, a.k, a.scheduler, arms,
                                     a.export_json))
        return 0
    for p in figure(a.stem, a.seed, a.k, a.scheduler, a.outdir, arms):
        print("  wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
