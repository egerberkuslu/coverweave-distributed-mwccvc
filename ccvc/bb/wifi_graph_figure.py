#!/usr/bin/env python3
"""One real Mininet-WiFi run drawn as a graph, with no text inside the frame.

WHY THIS FIGURE EXISTS SEPARATELY FROM `wifi_figure`. That one aggregates three
seeds into bars and answers how much of the plan the radio delivered and what
each arm paid for it. It never shows a single answer, and a reader who has
followed the cover rule through the text wants to see one: which stations ended
up in the cover, and on which graph.

WHAT IS DRAWN AND WHAT IS NOT. The graph is the one the STATIONS DISCOVERED,
because that is the graph the run was validated against; judging a cover against
edges nobody saw blames the channel on the algorithm. Planned edges the radio
never saw are drawn faintly so that the loss is visible rather than asserted,
and edges the radio found outside the plan are drawn faintly too, because they
are real edges the cover had to satisfy.

NO TEXT CHIPS. The earlier composed version of this figure carried the counts,
the weight and the message total on labelled boxes inside the frame. A number
inside a figure has to be kept in step with a caption that repeats it, and one
of the two drifts. The numbers are printed on the console for the caption to
carry, and the frame holds node identifiers, marks and a key.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from ccvc.bb import figstyle  # noqa: E402
from ccvc.bb.figstyle import (  # noqa: E402
    COL_W, FAINT, INK, MAX_H_COL, MIN_PT, MUTED, OKABE_ITO,
)

figstyle.apply_rc()

#: Colour is role, once. The cover fill is the family blue the measured figures
#: already give to a backbone, so it cannot read as a sixth family.
COVER = OKABE_ITO["blue"]
#: Edges that are in the plan AND in what the stations saw.
SEEN = "#6F6F6F"
#: Edges the radio found that the planner never drew.
EXTRA = OKABE_ITO["orange"]
#: Edges the planner drew that the radio never found.
LOST = FAINT


def _pair(e) -> Tuple[int, int]:
    u, v = int(e[0]), int(e[1])
    return (u, v) if u < v else (v, u)


def load(rundir: str):
    run = json.load(open(os.path.join(rundir, "run.json"), encoding="utf-8"))
    summ = json.load(open(os.path.join(rundir, "summary.json"), encoding="utf-8"))
    planned = {_pair(e) for e in run["edges"]}
    dv = summ["discovered_vs_target"]
    missing = {_pair(e) for e in dv.get("missing", [])}
    extra = {_pair(e) for e in dv.get("extra", [])}
    return run, summ, planned, missing, extra


def layout(run, nodes: Sequence[int], edges: Sequence[Tuple[int, int]],
           seed: int, kind: str) -> Dict[int, Tuple[float, float]]:
    """Where the nodes sit.

    `measured` is the station placement the emulator actually used. It is the
    truthful layout for a radio topology and it is NOT the default, because it
    is unreadable at one column: the stations that the planner put within a few
    metres of each other print as overlapping discs and their identifiers sit on
    top of each other. MEASURED on this run: 1 and 10 are 3.4 m apart, 2 and 5
    are 3.2 m apart, and at 88.9 mm both pairs collide.

    The default embeds the DISCOVERED graph, the same graph the figure draws and
    the run was validated against, so an edge is short because the two stations
    are joined rather than because of where the planner put them.
    """
    if kind == "measured" and run.get("positions"):
        return {int(k): (float(v[0]), float(v[1]))
                for k, v in run["positions"].items()}
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    g.add_edges_from(edges)
    if kind == "kamada":
        return nx.kamada_kawai_layout(g)
    # The seed is not arbitrary. Sixty embeddings were scored by the smallest
    # clearance between two discs once the weight scale and the frame are
    # applied, and seed 30 is the only one that leaves every pair apart by more
    # than a disc radius at 88.9 mm; the default drew node 7 touching node 10.
    return nx.spring_layout(g, seed=seed)


def draw(rundir: str, outdir: str, name: str, layout_kind: str = "spring",
         seed: int = 30) -> List[str]:
    run, summ, planned, missing, extra = load(rundir)
    nodes = sorted(int(x) for x in run["weights"])
    weights = {int(k): float(v) for k, v in run["weights"].items()}
    cover = {int(x) for x in summ["cover"]}
    discovered = (planned - missing) | extra
    pos = layout(run, nodes, sorted(discovered), seed, layout_kind)

    fig, ax = plt.subplots(figsize=(COL_W, MAX_H_COL))

    # Three edge classes, drawn faintest first so a solid edge is never half
    # hidden under one of them. THE CLASSES ARE COMPUTED, NOT ASSUMED: the lost
    # class is the plan minus what the stations saw, and on this run it is
    # empty, so it does not appear in the key either.
    for e, colour, lw, style in (
            [(e, LOST, 0.9, (0, (1, 2))) for e in sorted(missing)]
            + [(e, EXTRA, 0.9, (0, (3.2, 2.0))) for e in sorted(extra)]
            + [(e, SEEN, 1.1, "-") for e in sorted(planned - missing)]):
        (x1, y1), (x2, y2) = pos[e[0]], pos[e[1]]
        ax.plot([x1, x2], [y1, y2], color=colour, lw=lw, ls=style,
                zorder=1 if colour is not SEEN else 2)

    # AREA CARRIES WEIGHT, because weight is the quantity the cover minimises
    # and a reader who sees a big disc left out of the cover has read the point
    # of the figure without a word of text. The scale is linear in area, so a
    # disc twice the area is a node twice the weight.
    lo = min(weights.values())
    area = {n: 168.0 * weights[n] / lo for n in nodes}
    for n in nodes:
        x, y = pos[n]
        inside = n in cover
        ax.scatter([x], [y], s=area[n],
                   facecolor=COVER if inside else "white",
                   edgecolor=COVER if inside else MUTED,
                   linewidth=1.0, zorder=3)
        ax.text(x, y, str(n), ha="center", va="center", zorder=4,
                fontsize=MIN_PT, color="white" if inside else INK)

    ax.set_aspect("equal", adjustable="datalim")
    ax.set_axis_off()
    ax.margins(0.10)

    handles = [
        Line2D([], [], color=COVER, marker="o", ls="", markersize=8,
               markerfacecolor=COVER, markeredgewidth=1.0, label="in the cover"),
        Line2D([], [], color=MUTED, marker="o", ls="", markersize=8,
               markerfacecolor="white", markeredgewidth=1.0, label="outside it"),
        Line2D([], [], color=SEEN, lw=1.1, label="planned and seen"),
        Line2D([], [], color=EXTRA, lw=0.9, ls=(0, (3.2, 2.0)),
               label="seen, not planned"),
    ]
    if missing:
        handles.append(Line2D([], [], color=LOST, lw=0.9, ls=(0, (1, 2)),
                              label="planned, never seen"))
    fig.tight_layout(rect=(0, 0.17, 1, 1.0))
    fig.legend(handles=handles, loc="lower center", ncol=2,
               bbox_to_anchor=(0.5, -0.015), columnspacing=1.1,
               frameon=False, fontsize=MIN_PT)

    t = summ.get("totals", {})
    print(f"  caption: n={run['n']}, k={run['k']}, planned {len(planned)} edges, "
          f"discovered {len(discovered)} "
          f"({len(missing)} never seen, {len(extra)} unplanned), "
          f"|C|={len(cover)} of {len(nodes)}, weight {summ['cover_weight']:g}, "
          f"slots {summ.get('slots')}, tx {t.get('tx')}, rx {t.get('rx')}, "
          f"bytes_tx {t.get('bytes_tx')}, max payload {t.get('max_payload')}")
    return figstyle.save(fig, outdir, name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rundir",
                    default="results/bb/wifi_dagdeviren/dag_bbcvc_n10_m20_s1")
    ap.add_argument("--outdir", default="results/bb/figures/wifi")
    ap.add_argument("--name", default="wifi-discovered-graph")
    ap.add_argument("--layout", default="spring",
                    choices=("measured", "spring", "kamada"))
    ap.add_argument("--seed", type=int, default=30)
    a = ap.parse_args(argv)
    for p in draw(a.rundir, a.outdir, a.name, a.layout, a.seed):
        print("  wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
