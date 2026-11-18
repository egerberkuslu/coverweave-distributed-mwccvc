#!/usr/bin/env python3
"""The single source of the house style for every MEASURED figure.

Three modules draw from measured sweeps -- `compare_figures`, `reliability_figure`
and `wifi_figure` -- and before this file each carried its own copy of the
palette. Two copies of a palette is two palettes: `wifi_figure` had already
drifted to a five-key subset with no purple, so the greedy family had no colour
there and the same family could have been drawn in two hues across one report.

WHAT THE STYLE COMMITS TO.

  * Okabe-Ito, colour-blind safe, with the ROLE of each hue fixed here and
    nowhere else. Colour means family, always and only.
  * 181 mm print width. A figure that is wider is scaled down by the document
    and its 7 pt labels stop being 7 pt. `PRINT_W` is that width in inches and
    every figure here is built at it, so what is measured on screen is what
    lands on the page.
  * No caption paragraph inside the figure. A figure carries a title, a short
    provenance line, and marks that explain themselves; the sentences that used
    to wrap under the axes live in the table captions, which the same pipeline
    writes from the same rows.
  * Keys are copies of the marks. A legend entry is the patch, the glyph or the
    ring that appears in the plot, next to two or three words. A legend that
    spells out thirteen arm names is a list of text, and a reader has to carry
    it back into the cloud by hand; the arms that carry the message are labelled
    where they sit instead, and `ratio_spread` names all of them on its axis.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, Iterable, List, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

#: Okabe-Ito, colour-blind safe.
OKABE_ITO = {
    "black": "#000000", "orange": "#E69F00", "sky": "#56B4E9",
    "green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
    "vermillion": "#D55E00", "purple": "#CC79A7", "grey": "#999999",
}
#: Text and rule ink. Not pure black: pure black against white at 7 pt vibrates.
INK = "#1A1A1A"
MUTED = "#6B6B6B"
#: Structure that must recede behind the data: diagonals, reference lines.
FAINT = "#C9C9C9"

#: 181 mm, the double-column text width, in inches.
PRINT_W = 7.13

#: PAPER MODE. The report renders these figures for a screen-sized page where a
#: 6.4 pt annotation is still legible. The manuscript places the same files at
#: 181 mm inside a two-column journal page, where the same annotation is read at
#: arm's length off paper, and the house rule there is that NO text element may
#: print below 8 pt. Turning the floor up is not a measurement change: the same
#: rows, the same means and the same marks are drawn, only larger, so the mode
#: is a switch over sizes and over what is a title rather than a second code
#: path. Set BBCVC_PAPER_FIGS=1 to build the manuscript copies.
PAPER = os.environ.get("BBCVC_PAPER_FIGS", "").strip() not in ("", "0", "no")

#: Smallest label the style allows at that width.
MIN_PT = 8.5 if PAPER else 6.0
#: Axis labels sit one step above the floor so the two read as a hierarchy.
LABEL_PT = 9.5 if PAPER else 8.0
#: The tallest a full-width float may print, in inches. 70 mm, set by the
#: document: a figure taller than this pushes a column of text off its page.
MAX_H = 2.73
#: The tallest a single-column float may print. 60 mm.
MAX_H_COL = 2.33
#: 88.9 mm, the single-column text width, in inches, less the trim the document
#: applies. Figures built for one column are built at this.
COL_W = 3.46
#: The provenance line under a title, and the tint notes inside a panel.
NOTE_PT = MIN_PT if PAPER else 6.4
#: A name written beside the point it names.
FLAG_PT = MIN_PT if PAPER else 6.6
#: Key entries and axis-listed arm names.
KEY_PT = MIN_PT if PAPER else 6.8
#: The smallest thing the style prints: counts stacked over a bar.
TINY_PT = MIN_PT if PAPER else 5.8
#: Bold panel and figure titles.
TITLE_PT = 9.5 if PAPER else 9.0
#: A TITLE INSIDE A FIGURE IS A CAPTION IN THE WRONG PLACE. In the manuscript
#: the sentence over the axes is the float's caption, so the figure prints the
#: panel letters and nothing else; the provenance line goes to the caption with
#: it. `titled(..., panel=True)` marks the labels that identify a panel and
#: therefore survive.
SHOW_TITLE = not PAPER

#: Colour is family, and only family. Order is deliberate: the two families a
#: reader compares most often get the two most separable hues.
FAMILY_COLOUR = {
    "mst": OKABE_ITO["blue"], "bb": OKABE_ITO["orange"],
    "dfs": OKABE_ITO["green"], "anneal": OKABE_ITO["vermillion"],
    "greedy-backbone": OKABE_ITO["purple"],
}
#: Two or three words. These are key entries, not sentences.
FAMILY_LABEL = {
    "mst": "FabricTree", "bb": "NexusWarp, Wu-Li", "dfs": "TokenTrail",
    "anneal": "TemperFlux", "greedy-backbone": "Greedy baselines",
}
FAMILY_ORDER = ("mst", "bb", "dfs", "anneal", "greedy-backbone")

#: Within a family, variants are separated by marker shape rather than by
#: inline text. Text labels on a scatter this dense overlap into an unreadable
#: smear -- measured: five BB arms landed inside one 100-pixel box and their
#: names printed on top of each other.
FAMILY_MARKERS = ("o", "s", "^", "D", "v", "P")


def apply_rc() -> None:
    """Typography and rules, once, for every measured figure."""
    plt.rcParams.update({
        "figure.dpi": 200, "savefig.dpi": 200,
        # TrueType, not Type 3. IEEE rejects Type 3 fonts in submitted figures
        # and matplotlib embeds Type 3 by default.
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "font.size": max(8.0, MIN_PT),
        "axes.titlesize": TITLE_PT, "axes.titleweight": "bold",
        "axes.labelsize": LABEL_PT,
        "xtick.labelsize": max(7.0, MIN_PT), "ytick.labelsize": max(7.0, MIN_PT),
        "axes.grid": True, "grid.alpha": 0.9, "grid.linewidth": 0.5,
        "grid.color": "#E6E6E6",
        "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#8A8A8A", "axes.linewidth": 0.8,
        "xtick.color": "#8A8A8A", "ytick.color": "#8A8A8A",
        "xtick.labelcolor": INK, "ytick.labelcolor": INK,
        "xtick.major.size": 3.0, "ytick.major.size": 3.0,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8,
        "text.color": INK, "axes.labelcolor": INK,
        "legend.frameon": True, "legend.framealpha": 0.88,
        "legend.facecolor": "white", "legend.edgecolor": "none",
        "legend.fontsize": KEY_PT, "legend.handletextpad": 0.55,
        "legend.labelspacing": 0.5, "legend.borderpad": 0.5,
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })


@contextmanager
def type_floor(pt: float):
    """Raise the type floor for ONE figure, sizes and module constants alike.

    A figure that prints across both columns is read at the same distance as
    one that prints inside a single column, so the floor that keeps a
    single-column label legible is not the floor a full-width figure needs.
    `apply_rc` sets the module's floor once at import and the helpers here read
    the constants directly, so raising `rcParams` alone would move the axis
    labels and leave the key, the flags and the reference-line notes behind at
    8.5 pt.

    Everything is restored on the way out, so the next figure is drawn at the
    module's own sizes. A caller that passes an explicit size to `flag` or a
    `fontsize` to a legend must read the constant off THIS module rather than
    binding it at import, or its call site keeps the old number.
    """
    names = ("MIN_PT", "LABEL_PT", "NOTE_PT", "FLAG_PT", "KEY_PT", "TINY_PT",
             "TITLE_PT")
    g = globals()
    saved = {k: g[k] for k in names}
    saved_rc = {k: plt.rcParams[k] for k in
                ("font.size", "axes.labelsize", "axes.titlesize",
                 "xtick.labelsize", "ytick.labelsize", "legend.fontsize")}
    try:
        for k in names:
            g[k] = max(g[k], pt)
        plt.rcParams.update({
            "font.size": max(saved_rc["font.size"], pt),
            "axes.labelsize": g["LABEL_PT"],
            "axes.titlesize": g["TITLE_PT"],
            "xtick.labelsize": g["MIN_PT"], "ytick.labelsize": g["MIN_PT"],
            "legend.fontsize": g["KEY_PT"],
        })
        yield
    finally:
        g.update(saved)
        plt.rcParams.update(saved_rc)


def axlabels(ax, x: str, y: str, x_short=None, y_short=None) -> None:
    """Axis labels, with the short spelling used where the frame is short.

    A rotated y label is centred on the axes and runs past it in both
    directions, and in paper mode the saved box is the figure rectangle, so a
    label longer than the frame is CLIPPED rather than collected. MEASURED: at
    70 mm the sentence "Solution weight / exact optimum (lower is better)" ran
    210 pt against 150 pt of room and lost its last word. The short spelling
    keeps the quantity and hands the reading direction to the caption.
    """
    # An EMPTY short spelling means "no label here", which is what a shared
    # axis wants; falling back to the long one printed the seed label twice on
    # the stacked copy.
    ax.set_xlabel(x_short if PAPER and x_short is not None else x)
    ax.set_ylabel(y_short if PAPER and y_short is not None else y)


def titled(ax, title: str, note: str = "", panel: bool = False) -> None:
    """Left-aligned title with a small grey provenance line under it.

    The provenance sits ABOVE the axes and holds one short line. It replaces
    the wrapped paragraph that used to run under the figure: the counts it
    carries are the counts the table caption carries, so nothing is lost by
    saying them once here and in full there.
    """
    if not SHOW_TITLE:
        # Manuscript copy: the sentence belongs to the float's caption, and the
        # provenance line goes there with it. Only a panel letter stays.
        if panel:
            ax.set_title(title, loc="left", pad=6)
        return
    ax.set_title(title, loc="left", pad=15 if note else 6)
    if note:
        ax.text(0.0, 1.015, note, transform=ax.transAxes, fontsize=NOTE_PT,
                color=MUTED, ha="left", va="bottom")


def family_patch(fam: str) -> Patch:
    """A key entry that is literally the colour used, next to two words."""
    return Patch(facecolor=FAMILY_COLOUR[fam], edgecolor="none",
                 label=FAMILY_LABEL[fam])


def family_handles(families: Iterable[str]) -> List[Patch]:
    got = set(families)
    return [family_patch(f) for f in FAMILY_ORDER if f in got]


def scheduler_handles(marker: str = "o") -> List[Line2D]:
    """The fill distinction, drawn exactly as the plot draws it."""
    return [
        Line2D([], [], color=MUTED, marker=marker, ls="", markersize=5,
               label="synchronous"),
        Line2D([], [], color=MUTED, marker=marker, ls="", markersize=5,
               markerfacecolor="none", markeredgewidth=1.2,
               label="asynchronous"),
    ]


def ring_handle(label: str = "lightest cover") -> Line2D:
    return Line2D([], [], color=INK, marker="o", ls="", markersize=9,
                  markerfacecolor="none", markeredgewidth=0.9, label=label)


def spacer() -> Line2D:
    return Line2D([], [], color="none", label=" ")


def highlight(ax, x: float, y: float, colour: str = INK) -> None:
    """Two concentric rings: the mark that says "this one" without a word.

    Drawn in ink rather than in the point's own hue, because the hue is already
    spoken for -- it means family -- and a ring in that hue would read as a
    sixth family rather than as an annotation.
    """
    ax.scatter([x], [y], s=190, facecolor="none", edgecolor=colour,
               linewidth=1.0, zorder=6, clip_on=False)
    ax.scatter([x], [y], s=380, facecolor="none", edgecolor=colour,
               linewidth=0.6, alpha=0.45, zorder=6, clip_on=False)


def flag(ax, x: float, y: float, text: str, dx: float = 9.0, dy: float = 9.0,
         colour: str = INK, size: float = 0.0, auto_side: bool = False) -> None:
    """Name one point where it sits, with a hairline leader back to it.

    `auto_side` turns the label towards whichever side has room. Without it a
    label on an outermost point runs off the figure -- measured both ways:
    DFS-Spanning-Backbone printed past the right edge of the communication
    panel, and Anneal-Local past the left edge of the weight panel.
    """
    size = size or FLAG_PT
    if auto_side:
        lo, hi = ax.get_xlim()
        frac = (x - lo) / ((hi - lo) or 1.0)
        if frac > 0.62:
            dx = -abs(dx)
        elif frac < 0.25:
            dx = abs(dx)       # near the left edge the label would run off it
    ha = "left" if dx >= 0 else "right"
    ax.annotate(text, xy=(x, y), xytext=(dx, dy), textcoords="offset points",
                fontsize=size, color=colour, ha=ha, va="center", zorder=7,
                arrowprops=dict(arrowstyle="-", lw=0.6, color=FAINT,
                                shrinkA=0.0, shrinkB=4.0))


def reference_line(ax, value: float, axis: str = "y", label: str = "",
                   at: float = 0.015) -> None:
    """A reference at a meaningful value, with its name riding on the line."""
    if axis == "y":
        ax.axhline(value, color=MUTED, lw=0.8, ls=(0, (5, 4)), zorder=1)
        if label:
            ax.text(at, value, f" {label} ", transform=ax.get_yaxis_transform(),
                    fontsize=NOTE_PT, color=MUTED, va="center", ha="left",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
    else:
        ax.axvline(value, color=MUTED, lw=0.8, ls=(0, (5, 4)), zorder=1)
        if label:
            ax.text(value, at, f" {label} ", transform=ax.get_xaxis_transform(),
                    fontsize=NOTE_PT, color=MUTED, ha="left", rotation=90,
                    va="top" if at > 0.5 else "bottom",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))


def pareto(points: Dict[str, Tuple[float, float]]) -> List[str]:
    """Keys no other key beats on BOTH axes, lower being better on both."""
    out = []
    for a, (x, y) in points.items():
        if not any(b != a and bx <= x and by <= y and (bx < x or by < y)
                   for b, (bx, by) in points.items()):
            out.append(a)
    return sorted(out, key=lambda a: points[a][0])


def variant_style(rows: Sequence[dict]) -> Dict[str, Tuple[str, str]]:
    """Colour by family, marker by variant within that family."""
    fam_of = {r["variant"]: r["family"] for r in rows}
    out: Dict[str, Tuple[str, str]] = {}
    for fam in sorted(set(fam_of.values())):
        for i, v in enumerate(sorted(x for x, f in fam_of.items() if f == fam)):
            out[v] = (FAMILY_COLOUR.get(fam, OKABE_ITO["grey"]),
                      FAMILY_MARKERS[i % len(FAMILY_MARKERS)])
    return out


def save(fig, outdir: str, name: str) -> List[str]:
    """Write the figure, and in paper mode write it at EXACTLY its built size.

    `bbox_inches="tight"` is right for the report, where a figure is looked at
    on its own. It is wrong for the manuscript, because it trims the file to
    whatever the artists happened to occupy and the document then rescales that
    to the column. The scale factor is invisible and it moves with the longest
    legend entry: MEASURED, one figure saved 2.4 per cent WIDER than the text
    block and shrank an 8.5 pt label to 8.3 pt, while its neighbour saved 19 per
    cent narrower and stretched the same label to 10.1 pt. Neither the height
    limit nor the type floor can be held under a scale nobody wrote down.

    In paper mode the saved box is the figure rectangle itself, so width and
    height are what the code asked for. The price is that an artist placed
    OUTSIDE that rectangle is clipped rather than collected, which is why every
    key in this module now sits inside the figure.
    """
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for ext in ("png", "svg", "pdf"):
        p = os.path.join(outdir, f"{name}.{ext}")
        if PAPER:
            fig.savefig(p, format=ext, pad_inches=0.0)
        else:
            fig.savefig(p, format=ext, bbox_inches="tight", pad_inches=0.03)
        paths.append(p)
    plt.close(fig)
    return paths

