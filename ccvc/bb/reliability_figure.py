#!/usr/bin/env python3
"""Quality against reliability, the trade-off the mean solution weight hides.

An arm that fails on an instance DISAPPEARS from that instance's average rather
than appearing as a bad value, so ranking arms by mean weight alone rewards
failing on the hard cases. This figure puts the two axes side by side: how good
the answers are, and how often there IS an answer.

Reliability is measured over the instances that are not provably infeasible, so
a capacity-infeasible instance is never counted against an arm.

The sentence that used to wrap under the axes is now in two places that cannot
drift from the data: "lower is better" and "further right is better" ride on
the axis labels, and the reason -- an arm that fails leaves the average rather
than scoring badly in it -- is the caption of `tab:reliability`, which the same
pipeline writes from the same rows.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
from collections import defaultdict
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from ccvc.bb import armnames, figstyle, report_pipeline  # noqa: E402
from ccvc.bb.compare_figures import _f, _truthy, arm  # noqa: E402
from ccvc.bb.figstyle import (  # noqa: E402
    COL_W, FAMILY_COLOUR, FAMILY_MARKERS, MAX_H, MUTED, OKABE_ITO, PAPER,
    PRINT_W,
)

figstyle.apply_rc()

#: A STAND-ALONE PANEL IS A SUB-FIGURE, not the combined float cut in two.
#: 88.9 mm wide, the single-column text width, and 61 mm tall, which is
#: inside the 70 mm ceiling the document sets for any float.
PANEL_W = COL_W
#: 66 mm once placed at 0.48\textwidth, inside the 70 mm float ceiling.
#: The extra 5 mm over the old 61 mm is the key strip under the axes.
PANEL_H = 2.62
#: Type inside a single-column panel: one step under the module floor.
PANEL_PT = 7.5
PANEL_KEY_PT = 7.0


def load(path: str) -> List[dict]:
    """Sweep rows, with pre-rename arm names translated on read.

    The same reason as `report_pipeline.load_rows`: a sweep measured before the
    arms were renamed still spells them `V4-BB-MST` and the like, and plotting
    the old and new spellings as separate series would invent a difference.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        return armnames.canonical_rows(list(csv.DictReader(fh)))


def _stats(rows):
    """Per arm: fraction of feasible instances answered validly, and mean weight.

    FEASIBILITY IS THE STRONGEST TEST ON THE ROW, the same one
    `tab:reliability` is written with. The counting bound alone leaves a
    degree-deficient instance in the denominator, and MEASURED on the n = 50
    sweep that one instance -- which no arm can solve -- pulled all twenty-five
    configurations to 17/18 and printed a panel in which every arm missed 100%.
    A figure and a table drawn from the same rows must not disagree about which
    instances were answerable.

    AND IT IS JUDGED PER INSTANCE, FROM THE ROWS THAT RAN. Reading the verdict
    row by row has a second failure: `sweep._skipped_row` sets `infeasible` to
    False because the dataclass needs a value, not because anything was
    measured, so a run the wall-clock budget cut reads as a claim that the
    instance is solvable and the arm failed on it. MEASURED on the extra-large
    stage, where 37 rows were skipped across three instances no arm can solve:
    row by row this panel showed arms at 72.7 and 88.9 per cent while the table
    built from the same rows showed every arm at 8 of 8. The table was right.
    `report_pipeline.infeasible_instances` is the shared decision and this is
    now the same call the table makes.
    """
    dead = report_pipeline.infeasible_instances(rows)
    feasible = [r for r in rows
                if r["instance"] not in dead
                and (r.get("status") or "") != "skipped"]
    total: Dict[str, int] = defaultdict(int)
    good: Dict[str, int] = defaultdict(int)
    weight: Dict[str, List[float]] = defaultdict(list)
    for r in feasible:
        a = arm(r)
        total[a] += 1
        if _truthy(r, "valid") and (r.get("verdict") or "") == "solved":
            good[a] += 1
            w = _f(r, "total_weight")
            if w is not None:
                weight[a].append(w)
    return total, good, weight


def _relative(weight, good, total):
    """Weight relative to the best arm, on each arm's own valid instances.

    Stated plainly on the axis: this is NOT an approximation ratio. At n=50 no
    exact solver runs, so the only available reference is the best arm.
    """
    best = min((sum(v) / len(v) for v in weight.values() if v), default=None)
    out = {}
    for a, v in weight.items():
        if v and best:
            out[a] = (sum(v) / len(v) / best, good[a] / total[a])
    return out


def _spread(points, tol=0.045, step=0.155, cap=0.28):
    """Separate ties INSIDE a column, where horizontal room means nothing.

    Two arms whose mean weights differ in the third decimal print one on top of
    the other. The column index is the measured value; the offset is only room,
    and it never leaves the column.
    """
    ys = [y for _, y in points.values()]
    yspan = (max(ys) - min(ys)) or 1.0
    out = dict(points)
    by_col = {}
    for k, (x, _) in points.items():
        by_col.setdefault(x, []).append(k)

    def flush(group, x):
        if len(group) < 2:
            return
        room = min(step, cap * 2.0 / max(1, len(group) - 1))
        for i, k in enumerate(group):
            out[k] = (x + (i - (len(group) - 1) / 2.0) * room, points[k][1])

    for x, keys in by_col.items():
        keys.sort(key=lambda k: points[k][1])
        cluster = []
        for k in keys:
            if cluster and (points[k][1] - points[cluster[-1]][1]) > tol * yspan:
                flush(cluster, x)
                cluster = []
            cluster.append(k)
        flush(cluster, x)
    return out


def _draw_panel(ax, title, rows, style, fams, *, ylabel, letter=None,
                top_pad=0.14, show_title=True):
    """One scale on one axes: the whole body of the figure, drawn once.

    The combined float and the two stand-alone sub-figures show the SAME marks
    from the SAME rows, so the drawing lives here and the callers differ only
    in how large a rectangle they hand it and where the key goes.
    """
    total, good, weight = _stats(rows)
    pts = _relative(weight, good, total)
    # RELIABILITY IS A COLUMN, NOT A COORDINATE. Almost every arm answers
    # every feasible instance, so a linear axis puts fourteen markers on
    # one vertical line and they eat each other. Nudging them along x was
    # tried and rejected: it drew arms measured at 100% across 99.6 to
    # 100.4, and that is a reader's first reading of the axis. The axis is
    # categorical instead -- one column per reliability value that actually
    # occurred -- so horizontal room inside a column separates ties without
    # standing for anything, and the value itself stays on the tick.
    vals = sorted({round(rel * 100, 4) for _, rel in pts.values()})
    col = {v: k for k, v in enumerate(vals)}
    drawn = _spread({a: (float(col[round(rel * 100, 4)]), q)
                     for a, (q, rel) in pts.items()})
    if 100.0 in col:
        ax.axvspan(col[100.0] - 0.5, col[100.0] + 0.5,
                   color=OKABE_ITO["green"], alpha=0.07, lw=0, zorder=0)
    halo = [pe.withStroke(linewidth=2.4, foreground="white")]
    for a, (x, y) in sorted(drawn.items()):
        variant, sched = a.rsplit("/", 1)
        colour, marker = style[variant]
        ax.scatter(x, y, s=48, marker=marker, zorder=3,
                   facecolor=colour if sched == "sync" else "white",
                   edgecolor=colour, linewidth=1.3, path_effects=halo)

    ax.set_xticks(range(len(vals)))
    # 96.9697% is arithmetic, not a measurement a reader wants on a tick.
    ax.set_xticklabels([f"{round(v, 1):g}%" for v in vals])
    ax.set_xlim(-0.62, len(vals) - 0.38)
    ax.grid(axis="x", visible=False)
    for k in range(len(vals)):     # a stem anchors the column as a column
        ax.axvline(k, color="#E2E2E2", lw=0.8, zorder=0)
    qs = [q for q, _ in pts.values()]
    span = (max(qs) - min(qs)) or 0.02
    ax.set_ylim(min(qs) - 0.16 * span, max(qs) + top_pad * span)

    # An arm short of 100% is the finding in this figure, so it is named
    # where it sits; the rest are left to colour and to tab:reliability.
    # ONE LABEL PER VARIANT: both schedulers of a variant can miss 100%,
    # and naming the variant twice printed the same word over itself.
    short = sorted((a for a in pts if pts[a][1] < 0.9999),
                   key=lambda a: pts[a][0])
    named, seen = [], set()
    for a in short:
        v = a.rsplit("/", 1)[0]
        if v not in seen:
            seen.add(v)
            named.append((a, v))
    # Labels lean OUTWARD along the stack. Alternating up and down sent the
    # two middle ones towards each other and they printed on top of each
    # other; the lowest goes below, the highest above, the rest sit level.
    # The offset scales with the type, and a LONE label leans upward. At
    # 8 pt a single name dropped below its point ran into the cluster that
    # sits at 100 %, where every other arm is drawn.
    _o = 14.0 if PAPER else 12.0
    for i, (a, v) in enumerate(named):
        if len(named) == 1:
            dy = _o
        else:
            dy = -_o if i == 0 else (_o if i == len(named) - 1 else 0.0)
        figstyle.flag(ax, drawn[a][0], drawn[a][1], v,
                      dx=14.0 if PAPER else 11.0, dy=dy,
                      colour=FAMILY_COLOUR.get(fams[v], MUTED))
    best = min(pts, key=lambda a: pts[a][0])
    figstyle.highlight(ax, drawn[best][0], drawn[best][1])

    n_inst = len({r["instance"] for r in rows
                  if r["instance"] not in
                  report_pipeline.infeasible_instances(rows)})
    figstyle.axlabels(
        ax, "Feasible instances answered validly",
        "Mean solution weight / best arm (lower is better)" if ylabel else "",
        "Feasible instances answered validly",
        "Weight / best arm" if ylabel else "")
    # A STAND-ALONE SUB-FIGURE HAS A SUBFLOAT CAPTION, and that caption
    # already spells the band and the node counts. Printing the same words in
    # bold over the axes said them twice and spent 9 mm of a 66 mm frame on
    # the repetition, so the sub-figure copies leave the strip to the data.
    if show_title:
        figstyle.titled(ax, f"({letter}) {title}" if letter else title,
                        f"{n_inst} feasible instances", panel=True)


def _key(fams):
    """The shared key, as the panels draw their marks."""
    return (figstyle.family_handles(fams.values())
            + ([] if PAPER else [figstyle.spacer()])
            + figstyle.scheduler_handles()
            + [figstyle.ring_handle("lightest cover")])


def _style_of(rows_by_scale):
    fams = {}
    for rows in rows_by_scale.values():
        for r in rows:
            fams[r["variant"]] = r["family"]
    style = {}
    for fam in sorted(set(fams.values())):
        for i, v in enumerate(sorted(x for x, f in fams.items() if f == fam)):
            style[v] = (FAMILY_COLOUR.get(fam, OKABE_ITO["grey"]),
                        FAMILY_MARKERS[i % len(FAMILY_MARKERS)])
    return style, fams


def _slug(title: str) -> str:
    """The first word of a panel title, which is the scale it shows."""
    return re.sub(r"[^a-z]", "", title.split(",")[0].split()[0].lower())


def figure(rows_by_scale, outdir, name="quality_vs_reliability"):
    style, fams = _style_of(rows_by_scale)
    n_panel = len(rows_by_scale)
    fig, axes = plt.subplots(1, n_panel, squeeze=False,
                             figsize=(PRINT_W if n_panel > 1 else 4.0,
                                      MAX_H if PAPER else 3.5))
    for idx, (ax, (title, rows)) in enumerate(zip(axes[0], rows_by_scale.items())):
        _draw_panel(ax, title, rows, style, fams, ylabel=(idx == 0),
                    letter=chr(97 + idx) if PAPER else None)

    handles = _key(fams)
    # The key sits UNDER the panels. Inside either one it covered arms: at
    # lower left of the last panel it sat on the ringed best arm, and at upper
    # left of the first it sat on the DFS pair at 1.20.
    if PAPER:
        # ONE SHARED KEY ROW inside the figure rectangle, eight entries over
        # two rows. In paper mode the saved box is the figure itself, so a key
        # anchored below it would be cut off rather than collected.
        fig.tight_layout(rect=(0, 0.20, 1, 1))
        fig.legend(handles=handles, loc="lower center", ncol=4,
                   bbox_to_anchor=(0.5, -0.012), columnspacing=1.4,
                   frameon=False, fontsize=figstyle.KEY_PT)
    else:
        fig.tight_layout(rect=(0, 0.11, 1, 1))
        fig.legend(handles=handles, loc="lower center", ncol=4,
                   bbox_to_anchor=(0.5, -0.01), columnspacing=1.6)
    return figstyle.save(fig, outdir, name)


def panels(rows_by_scale, outdir, name="quality_vs_reliability"):
    """The same panels again, one file each, sized for an IEEE sub-figure.

    WHY BOTH FILES EXIST. The combined two-panel figure is what the report
    shows and what an early draft placed in the manuscript, but IEEE sets a
    two-panel comparison as two sub-figures, each captioned on its own and each
    one column wide. Rendering the panels by cropping the combined file would
    rescale them by an amount nobody wrote down and the 8.5 pt floor would move
    with it, so each panel is BUILT at the column width instead and the shared
    key is drawn inside the first one, where the saved rectangle still holds it.
    """
    if not PAPER:
        return []
    style, fams = _style_of(rows_by_scale)
    out = []
    # ONE STEP DOWN FROM THE MODULE FLOOR, and only here. These two panels are
    # the only figures printed at 88.9 mm, so the 8.5 pt that keeps a
    # full-width figure legible is a step too large inside a column: the tick
    # row, the two axis labels and an eight-entry key were carrying more ink
    # than the marks they explain. 7.5 pt for the axes and 7 pt for the key
    # stay above the document's 7 pt floor, and the panel rectangle does not
    # move, so nothing around the figure shifts.
    keep = {k: plt.rcParams[k] for k in
            ("font.size", "axes.labelsize", "xtick.labelsize",
             "ytick.labelsize")}
    plt.rcParams.update({"font.size": PANEL_PT, "axes.labelsize": PANEL_PT,
                         "xtick.labelsize": PANEL_PT,
                         "ytick.labelsize": PANEL_PT})
    for title, rows in rows_by_scale.items():
        fig, ax = plt.subplots(figsize=(PANEL_W, PANEL_H))
        _draw_panel(ax, title, rows, style, fams, ylabel=True,
                    top_pad=0.30, show_title=False)
        # THE KEY SITS UNDER THE AXES, as it does on the full-width figures.
        # Inside the frame it covered the cloud it explains: eight entries in
        # two columns at the 8.5 pt floor filled the upper half of a 61 mm
        # panel and printed over the arms at 1.13 to 1.20. A strip of its own
        # is the only place a key this long fits at column width, and in paper
        # mode the saved box is the figure rectangle, so the strip has to be
        # reserved rather than left to `bbox_inches`.
        fig.tight_layout(rect=(0, 0.205, 1, 1.0), pad=0.35)
        # TWO COLUMNS, FOUR ROWS. Eight entries at the 8.5 pt floor do not fit
        # 88.9 mm in three columns: MEASURED at 3.49 in against 3.46 in of
        # frame even with the padding pulled in, and paper mode clips rather
        # than collects, so "asynchronous" and "lightest cover" lost their last
        # letters. Two columns measure 2.54 in and keep the families in their
        # own column, which is the order the key is read in.
        fig.legend(handles=_key(fams), loc="lower center", ncol=2,
                   bbox_to_anchor=(0.5, 0.008), columnspacing=0.8,
                   handletextpad=0.4, handlelength=1.2, labelspacing=0.3,
                   borderpad=0.0, borderaxespad=0.0, frameon=False,
                   markerscale=0.85, fontsize=PANEL_KEY_PT)
        out += figstyle.save(fig, outdir, f"{name}_{_slug(title)}")
    plt.rcParams.update(keep)
    return out


def _sizes(rows) -> str:
    """The node counts this panel actually holds, read from the rows.

    THE PANEL LABEL WAS A CONSTANT AND THE SWEEP BEHIND IT WAS NOT. The second
    panel was spelled "n = 50" whichever directory the report handed it, and
    the report hands it `sweep_medium_n100_fixed_v2`, whose twelve instances are
    six at n = 50 and six at n = 100. The label is now derived from the rows, so
    a figure cannot name a scale it did not plot.
    """
    ns = sorted({int(r["n"]) for r in rows if (r.get("n") or "").isdigit()})
    if not ns:
        return "n unknown"
    if len(ns) == 1:
        return f"n = {ns[0]}"
    if len(ns) == 2:
        return f"n = {ns[0]} and {ns[1]}"
    return f"n = {ns[0]} to {ns[-1]}"


def _band(rows) -> str:
    """The band this panel holds, named from the rows rather than the argument.

    SAME BUG AS `_sizes`, ONE LEVEL UP. That function was written because the
    node counts in the label were a constant while the sweep behind them was
    not; the WORD in front of them stayed a constant anyway. The report now
    hands this figure the first and last scales that have a common valid
    subset, which for the full sweep are n = 10 to 25 and n = 250 to 1000, and
    the second panel came out reading "Medium, n = 250 to 1000". Deriving both
    halves from the rows is the only version that cannot say that.
    """
    ns = [int(r["n"]) for r in rows if (r.get("n") or "").isdigit()]
    top = max(ns) if ns else 0
    if top <= 25:
        return "Small group"
    if top <= 100:
        return "Medium"
    if top <= 200:
        return "Large"
    return "Extra large"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--small", default="results/bb/sweep_small_full_k6_clean/rows.csv")
    ap.add_argument("--medium", default="results/bb/sweep_medium_n50_k6_fixed/rows.csv")
    ap.add_argument("--outdir", default="results/bb/figures/scale")
    args = ap.parse_args(argv)
    scales = {}
    if os.path.exists(args.small):
        rows = load(args.small)
        scales[f"{_band(rows)}, {_sizes(rows)}"] = rows
    if os.path.exists(args.medium):
        rows = load(args.medium)
        scales[f"{_band(rows)}, {_sizes(rows)}"] = rows
    if not scales:
        print("no row files found")
        return 1
    for p in figure(scales, args.outdir):
        print("  wrote", p)
    for p in panels(scales, args.outdir):
        print("  wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
