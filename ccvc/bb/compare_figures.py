#!/usr/bin/env python3
"""Comparison figures from a measured sweep, in English, Okabe-Ito palette.

Reads `rows.csv` written by `ccvc.bb.sweep` and plots only what was measured.
Every figure is restricted to the COMMON VALID SUBSET -- the instances on which
every arm produced a validator-clean answer -- because an arm that fails on an
instance disappears from an average rather than appearing as a bad value, and
comparing arms over different instance sets rewards failure.

Rows whose instance is provably capacity-infeasible (m > n*k) are dropped
before anything else. They are not arm failures and averaging them in would
measure k rather than the algorithms.

The style lives in `ccvc.bb.figstyle`, and so does the reason these figures no
longer carry a paragraph under the axes: the counts that paragraph recited are
in the caption of the table the same pipeline writes from the same rows.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ccvc.bb import armnames, figstyle, report_pipeline  # noqa: E402
from ccvc.bb.figstyle import (  # noqa: E402  (re-exported: other modules import from here)
    FAMILY_COLOUR, FAMILY_LABEL, FAMILY_MARKERS, FAINT, KEY_PT, MAX_H, MUTED,
    NOTE_PT, OKABE_ITO, PAPER, PRINT_W, SHOW_TITLE, TITLE_PT,
)

figstyle.apply_rc()

#: The height is the document's ceiling for a full-width float that shares
#: its page with a table, 66 mm.
QCOST_H = 2.6
#: TYPE MATCHED TO ITS NEIGHBOUR, NOT TO ITS OWN WIDTH. `fig:qcost` and
#: `fig:qrel` face each other across two pages of the same section and a
#: reader compares them directly, so the two must set their axes in one size.
#: `fig:qrel` is built as two column-wide panels at `reliability_figure`'s
#: 7.5 pt with a 7 pt key, and `fig:qcost` was raised to a 9 pt floor instead,
#: which printed its ticks and axis labels a fifth larger than the panels
#: beside it. The floor is not what keeps this figure legible -- it prints at
#: 181 mm unscaled, so 7.5 pt on the page is 7.5 pt in the file, above the
#: document's 7 pt minimum -- and matching the neighbour is what a reader
#: needs. The annotations keep the module's own `FLAG_PT`, exactly as the
#: panels of `fig:qrel` do, so the two figures also name points at one size.
QCOST_PT = 7.5
#: Key entries, one step under the axis type, as in `reliability_figure`.
QCOST_KEY_PT = 7.0


def load(path: str) -> List[dict]:
    """Sweep rows, with pre-rename arm names translated on read.

    The same reason as `report_pipeline.load_rows`: a sweep measured before the
    arms were renamed still spells them `V4-BB-MST` and the like, and plotting
    the old and new spellings as separate series would invent a difference.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        return armnames.canonical_rows(list(csv.DictReader(fh)))


def _f(row: dict, key: str):
    raw = (row.get(key) or "").strip()
    if raw in ("", "None", "n/a", "NA"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _truthy(row: dict, key: str) -> bool:
    return (row.get(key) or "").strip().lower() in ("1", "true", "yes")


def arm(row: dict) -> str:
    return f"{row['variant']}/{row['scheduler']}"


def common_valid(rows: Sequence[dict]) -> Tuple[List[dict], List[str], Dict]:
    """Drop infeasible instances, then keep instances every arm solved.

    Returns the surviving rows, the instance keys, and a small provenance dict
    that the figure prints in one line, so a figure can never claim a subset it
    did not use.
    """
    # THE STRONGEST TEST, AND JUDGED PER INSTANCE FROM THE ROWS THAT RAN. A
    # degree-deficient instance no arm can solve is not an arm failure, and
    # leaving it in the denominator made the provenance line understate how
    # much of the sweep the subset covers. Reading the verdict row by row has
    # a second failure though: `sweep._skipped_row` fills `infeasible` with
    # False because the dataclass needs a value, not because anything was
    # measured, so a run the wall-clock budget cut looks like a claim that the
    # instance is solvable. MEASURED on the dense stage, where every instance
    # has m > nk and none admits a cover: row by row it reported twelve
    # feasible instances with nothing solved, which reads as every arm failing
    # on twelve solvable problems. `report_pipeline` already decides this the
    # right way and the tables use it, so the figures now share that rule
    # rather than keeping their own.
    infeasible_names = report_pipeline.infeasible_instances(rows)
    feasible = [r for r in rows if r["instance"] not in infeasible_names]
    dropped_infeasible = {r["instance"] for r in rows} - {r["instance"] for r in feasible}
    arms = sorted({arm(r) for r in feasible})
    ok: Dict[str, set] = defaultdict(set)
    for r in feasible:
        if _truthy(r, "valid") and (r.get("verdict") or "") == "solved":
            ok[r["instance"]].add(arm(r))
    common = sorted(i for i, got in ok.items() if len(got) == len(arms))
    keep = [r for r in feasible if r["instance"] in common]
    prov = {
        "arms": len(arms),
        "instances_total": len({r["instance"] for r in rows}),
        "instances_infeasible": len(dropped_infeasible),
        "instances_common": len(common),
    }
    return keep, common, prov


def by_arm(rows: Sequence[dict], key: str) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        v = _f(r, key)
        if v is not None:
            out[arm(r)].append(v)
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _family(rows: Sequence[dict]) -> Dict[str, str]:
    return {arm(r): r["family"] for r in rows}


def _ratios(rows: Sequence[dict]) -> Dict[str, List[float]]:
    per: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        e, w = _f(r, "exact_weight"), _f(r, "total_weight")
        if e and w:
            per[arm(r)].append(w / e)
    return per


def _note(prov: dict) -> str:
    """One line of provenance. The full sentence is the table's caption."""
    feasible = prov["instances_total"] - prov["instances_infeasible"]
    return (f"common valid subset: {prov['instances_common']} of {feasible} "
            f"feasible instances, all {prov['arms']} arms clean")


def _save(fig, outdir: str, name: str) -> List[str]:
    return figstyle.save(fig, outdir, name)


def _variant_style(rows) -> Dict[str, Tuple[str, str]]:
    """Colour by family, marker by variant within that family."""
    return figstyle.variant_style(rows)


# ---------------------------------------------------------------- figure 1
def figure_quality_vs_cost(rows, prov, outdir):
    """The central trade-off: solution weight against messages sent.

    Both axes are measured, neither is modelled. `tx` is frames offered to the
    radio, counted at the sender; it is NOT airtime and NOT energy.

    The arms that carry the message are the ones nothing beats on both axes at
    once, so those are named where they sit and the rest are left to colour.
    Naming all twenty-five put a block of text beside the plot that a reader
    had to carry back into the cloud by hand; `ratio_spread` lists every arm on
    its own axis, and the tables carry the numbers.
    """
    tx = by_arm(rows, "tx")
    exact = _ratios(rows)
    style = _variant_style(rows)
    fams = _family(rows)

    pts = {a: (_mean(tx[a]), _mean(exact[a])) for a in sorted(exact) if tx[a]}
    with (_qcost_type() if PAPER else contextlib.nullcontext()):
        return _qcost_body(pts, style, fams, prov, outdir)


@contextlib.contextmanager
def _qcost_type():
    """Axis type at `fig:qrel`'s size, for the length of this one figure.

    `figstyle.type_floor` cannot do this: it RAISES every constant to the size
    it is handed and the module already sits at 8.5 pt in paper mode, so
    handing it 7.5 would leave the labels where they are. The sizes are set on
    `rcParams` directly instead, which is what `reliability_figure.panels`
    does for the very panels this figure is being matched to, and the module
    constants are left alone so `FLAG_PT` still names points at 8.5 pt in both
    figures. Everything is restored on the way out, so the next figure in the
    same process is drawn at the module's own sizes.
    """
    keep = {k: plt.rcParams[k] for k in
            ("font.size", "axes.labelsize", "xtick.labelsize",
             "ytick.labelsize")}
    plt.rcParams.update({"font.size": QCOST_PT, "axes.labelsize": QCOST_PT,
                         "xtick.labelsize": QCOST_PT,
                         "ytick.labelsize": QCOST_PT})
    try:
        yield
    finally:
        plt.rcParams.update(keep)


def _qcost_body(pts, style, fams, prov, outdir):
    fig, ax = plt.subplots(figsize=(PRINT_W, QCOST_H if PAPER else 4.0))

    front = figstyle.pareto(pts)
    if len(front) > 1:
        ax.plot([pts[a][0] for a in front], [pts[a][1] for a in front],
                color=FAINT, lw=1.2, ls="-", zorder=1)

    for a, (x, y) in pts.items():
        variant, sched = a.rsplit("/", 1)
        colour, marker = style[variant]
        filled = sched == "sync"
        # The same glyph size and stroke `fig:qrel` draws, so a marker means
        # the same thing at the same weight in both figures.
        ax.scatter(x, y, s=48, marker=marker,
                   facecolor=colour if filled else "white",
                   edgecolor=colour, linewidth=1.3, zorder=3)

    figstyle.reference_line(ax, 1.0, "y", "" if PAPER else "exact optimum")

    # The lightest cover gets the ring; on this data it is also on the front.
    best = min(pts, key=lambda a: pts[a][1])
    figstyle.highlight(ax, *pts[best])

    xlo = min(x for x, _ in pts.values())
    xhi = max(x for x, _ in pts.values())
    span = xhi - xlo
    ax.set_xlim(xlo - 0.10 * span, xhi + 0.14 * span)
    ylo = min(y for _, y in pts.values())
    yhi = max(y for _, y in pts.values())
    # Headroom for the named front points. At 8 pt the name of the topmost arm
    # is a third taller than it was at 6.6 pt and printed into the frame edge.
    ax.set_ylim(min(0.99, ylo - 0.05 * (yhi - ylo)),
                yhi + (0.34 if PAPER else 0.09) * (yhi - ylo))

    # ONE LABEL PER VARIANT. Both schedulers of a variant can sit on the front,
    # and naming the variant twice printed the same word over itself; the
    # second point stays drawn, its fill still says which scheduler it is.
    named, seen = [], set()
    for a in front:
        v = a.rsplit("/", 1)[0]
        if v not in seen:
            seen.add(v)
            named.append(a)
    if PAPER:
        # TWO NAMES, NOT THREE. The manuscript allows two annotations in a
        # frame, so the two that carry the finding are kept: the cheapest arm on
        # the front, and the arm the ring already points at.
        named = [a for a in (named[0], best) if a in pts][:2]
    for i, a in enumerate(named):
        x, y = pts[a]
        # The offset scales with the type. At 8 pt a 13 pt drop left the second
        # name lying across the ring that marks the lightest cover.
        _off = 16.0 if PAPER else 13.0
        # A NAME IS AXIS TYPE, NOT A SIZE OF ITS OWN. `FLAG_PT` sits at the
        # module floor, and once the axes came down to `fig:qrel`'s 7.5 pt the
        # two names printed a step LARGER than the labels around them, which
        # reads as emphasis nobody meant. 7.5 pt keeps them above the
        # document's 7 pt minimum and level with the rest of the frame.
        figstyle.flag(ax, x, y, armnames.display(a.rsplit("/", 1)[0]),
                      dx=16.0 if PAPER else 13.0,
                      dy=_off if i % 2 == 0 else -_off,
                      size=QCOST_PT if PAPER else 0.0,
                      colour=FAMILY_COLOUR.get(fams[a], MUTED), auto_side=True)

    figstyle.axlabels(ax,
                      "Messages sent per run (tx, mean; fewer is better)",
                      "Solution weight / exact optimum (lower is better)",
                      "Messages sent per run, tx mean",
                      "Weight / exact optimum")
    figstyle.titled(ax, "Quality against communication cost", _note(prov))

    handles = (figstyle.family_handles(fams.values())
               + ([] if PAPER else [figstyle.spacer()])
               + figstyle.scheduler_handles()
               + [figstyle.ring_handle("lightest cover"),
                  plt.Line2D([], [], color=FAINT, lw=1.2, label="best trade-offs")])
    if PAPER:
        # ONE SHARED KEY ROW, inside the figure rectangle. Ten entries stacked
        # in the corner of a 70 mm frame cover the cloud they explain.
        handles.append(plt.Line2D([], [], color=MUTED, lw=0.8, ls=(0, (5, 4)),
                                  label="exact optimum"))
        # The strip is reserved rather than left to `bbox_inches`, because in
        # paper mode the saved box is the figure rectangle and a key anchored
        # below it would be cut off rather than collected. Two rows of 7 pt
        # entries need less of the frame than two rows of 8.5 pt ones did.
        fig.tight_layout(rect=(0, 0.135, 1, 1.0))
        fig.legend(handles=handles, loc="lower center", ncol=5,
                   bbox_to_anchor=(0.5, -0.004), columnspacing=1.0,
                   handletextpad=0.4, handlelength=1.2, labelspacing=0.3,
                   borderpad=0.0, borderaxespad=0.0, markerscale=0.85,
                   frameon=False, fontsize=QCOST_KEY_PT)
    else:
        ax.legend(handles=handles, loc="upper right", ncol=2,
                  columnspacing=1.1, borderpad=0.55)
    return _save(fig, outdir, "quality_vs_cost")


# ---------------------------------------------------------------- figure 2
def figure_ratio_spread(rows, prov, outdir):
    """Per-instance approximation ratio, not just its mean.

    A mean hides whether an arm is uniformly mediocre or occasionally awful,
    and those call for different conclusions.

    One ROW PER VARIANT rather than one per arm: the two schedulers of a
    variant ran the same instances, so putting them on the same row and joining
    their means turns the scheduler effect into a length a reader can see,
    instead of two rows that have to be found in a list of twenty-five and
    subtracted by eye.
    """
    per = _ratios(rows)
    fams = {r["variant"]: r["family"] for r in rows}
    style = _variant_style(rows)

    split: Dict[str, Dict[str, List[float]]] = defaultdict(dict)
    for a, vals in per.items():
        variant, sched = a.rsplit("/", 1)
        split[variant][sched] = vals

    order = sorted(split, key=lambda v: -min(_mean(x) for x in split[v].values()))
    off = {"sync": -0.17, "async": 0.17}

    fig, ax = plt.subplots(figsize=(PRINT_W, (0.36 if PAPER else 0.30)
                                     * len(order) + 1.75))
    best_pt = None
    for i, v in enumerate(order):
        colour, marker = style[v]
        means = {}
        for sched, vals in split[v].items():
            y = i + off.get(sched, 0.0)
            ax.scatter(vals, [y] * len(vals), s=9, color=colour, alpha=0.30,
                       edgecolor="none", zorder=2)
            means[sched] = (_mean(vals), y)
        if len(means) == 2:
            (x1, y1), (x2, y2) = means["sync"], means["async"]
            ax.plot([x1, x2], [y1, y2], color=colour, lw=0.9, alpha=0.55,
                    zorder=3)
        for sched, (mx, my) in means.items():
            ax.scatter([mx], [my], s=40, marker=marker, zorder=4,
                       facecolor=colour if sched == "sync" else "white",
                       edgecolor=colour, linewidth=1.3)
            if best_pt is None or mx < best_pt[0]:
                best_pt = (mx, my)

    figstyle.reference_line(ax, 1.0, "x", "exact optimum", at=0.995)
    if best_pt:
        figstyle.highlight(ax, *best_pt)

    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([armnames.display(v) for v in order], fontsize=KEY_PT)
    # Tick labels stay in ink. Drawn in their family hue the pink ones fell
    # under 3:1 against white at this size; the family is already on the
    # marker beside the row and in the key.
    ax.set_ylim(-0.75, len(order) + 0.55)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Solution weight / exact optimum, one faint dot per instance")
    figstyle.titled(ax, "Approximation ratio, per instance and mean",
                    _note(prov))

    handles = (figstyle.family_handles(fams.values())
               + figstyle.scheduler_handles()
               + [plt.Line2D([], [], color=MUTED, lw=0.9, alpha=0.7,
                             label="scheduler gap"),
                  figstyle.ring_handle("lightest cover")])
    # Upper right, in the strip the extra headroom opened: at lower right the
    # key sat on the tail of the two heaviest rows and hid their dots.
    ax.legend(handles=handles, loc="upper right", ncol=3, columnspacing=1.1)
    return _save(fig, outdir, "ratio_spread")


# ---------------------------------------------------------------- figure 3
def figure_scheduler_effect(rows, prov, outdir):
    """Paired sync-against-async, one point per variant.

    Paired because both members of a pair ran the SAME instances; an unpaired
    comparison of these numbers would confound the scheduler with the instance.

    The half of the square that favours the asynchronous scheduler is tinted,
    so "below the diagonal is better" is a region a reader sees rather than a
    sentence under the figure.
    """
    w: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    t: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        wt, tx = _f(r, "total_weight"), _f(r, "tx")
        if wt is not None:
            w[r["variant"]][r["scheduler"]].append(wt)
        if tx is not None:
            t[r["variant"]][r["scheduler"]].append(tx)
    fams = {r["variant"]: r["family"] for r in rows}
    style = _variant_style(rows)
    both = [v for v in w if {"sync", "async"} <= set(w[v])]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(PRINT_W, 4.0 if PAPER else 3.5))
    panels = ((ax1, w, "(a) Solution weight", "total weight",
               "asynchronous lighter"),
              (ax2, t, "(b) Communication", "messages sent (tx)",
               "asynchronous cheaper"))
    for ax, data, title, unit, tint in panels:
        xs = [_mean(data[v]["sync"]) for v in both]
        ys = [_mean(data[v]["async"]) for v in both]
        lo, hi = min(xs + ys), max(xs + ys)
        pad = 0.10 * (hi - lo) or 1.0
        lo, hi = lo - pad, hi + pad
        ax.fill_between([lo, hi], [lo, hi], [lo, lo], color=OKABE_ITO["sky"],
                        alpha=0.10, lw=0, zorder=0)
        ax.plot([lo, hi], [lo, hi], color=MUTED, lw=0.8, ls=(0, (5, 4)),
                zorder=1)
        for v, x, y in zip(both, xs, ys):
            colour, marker = style[v]
            ax.scatter(x, y, s=46, marker=marker, color=colour,
                       edgecolor="white", linewidth=0.6, zorder=3)
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(f"synchronous, {unit}")
        ax.set_ylabel(f"asynchronous, {unit}")
        ax.set_title(title, loc="left", pad=6)
        ax.text(0.97, 0.05, tint, transform=ax.transAxes,
                fontsize=NOTE_PT, color=MUTED, ha="right", va="bottom")
        # Name the variant the scheduler moves most: that pair is the finding,
        # and it is the one a reader would otherwise measure off the diagonal
        # with a ruler.
        far = max(zip(both, xs, ys), key=lambda z: abs(z[2] - z[1]) / (z[1] or 1.0))
        # Away from the diagonal, never across it: a label laid over the
        # reference line is read as a point sitting on it.
        above = far[2] > far[1]
        figstyle.flag(ax, far[1], far[2], armnames.display(far[0]),
                      dx=11.0, dy=11.0 if above else -11.0,
                      colour=FAMILY_COLOUR.get(fams[far[0]], MUTED),
                      auto_side=True)

    ax2.legend(handles=figstyle.family_handles(fams[v] for v in both),
               loc="upper left", fontsize=KEY_PT)
    fig.tight_layout(rect=(0, 0, 1, 0.90 if SHOW_TITLE else 1.0))
    if SHOW_TITLE:
        fig.suptitle("Scheduler effect, paired by variant", x=0.006, y=1.0,
                     ha="left", va="top", fontsize=TITLE_PT, fontweight="bold")
        fig.text(0.006, 0.955, _note(prov), fontsize=NOTE_PT, color=MUTED,
                 ha="left", va="top")
    return _save(fig, outdir, "scheduler_effect")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", default="results/bb/sweep_small_k6/rows.csv")
    ap.add_argument("--outdir", default="results/bb/figures/compare")
    args = ap.parse_args(argv)
    rows = load(args.rows)
    keep, common, prov = common_valid(rows)
    if not keep:
        print("no common valid subset; nothing plotted")
        return 1
    print(f"common valid subset: {prov}")
    for fn in (figure_quality_vs_cost, figure_ratio_spread,
               figure_scheduler_effect):
        for p in fn(keep, prov, args.outdir):
            print("  wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
