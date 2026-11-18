#!/usr/bin/env python3
"""Figures from REAL Mininet-WiFi runs, kept separate from simulator figures.

Two things are plotted and they must not be merged. Panel (a) is about the
CHANNEL: how much of the planned topology the stations actually discovered.
Panel (b) is about the ALGORITHM: the solution each arm produced on the graph
it actually saw, paired by seed.

Every run here is validated against the DISCOVERED graph, not the planned one,
because the node's RSSI gate does not reproduce the planner's unit disc and
judging a cover against edges the stations never saw blames the channel on the
algorithm.

The paragraph that used to wrap under the axes is now in `tab:wireless`, whose
caption carries the same run count, the same pairing argument and the story of
the one invalid seed. What stays here is what a reader cannot get from a table
in one glance: the SIZE of the discovery loss, drawn as a fall from planned to
discovered with the lost edges counted on the drop.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ccvc.bb import figstyle  # noqa: E402
from ccvc.bb.figstyle import (  # noqa: E402
    COL_W, INK, KEY_PT, MAX_H, MUTED, NOTE_PT, OKABE_ITO, PAPER, PRINT_W,
    SHOW_TITLE, TINY_PT, TITLE_PT,
)

#: A single-column copy is 55 mm tall, and at that height a key entry spelling
#: out an arm name three times over eats a third of the frame. The short
#: spellings are keys, not identifiers; the tables carry the full names.
SHORT_LABEL = {"MIS-Connector-Backbone": "MIS-Connector",
               "GHS-MST-Backbone": "GHS-MST",
               "Anneal-Local": "Anneal-Local"}

#: Arm colours come from the family map, so a family cannot be one hue in the
#: simulator figures and another here.
ARM_COLOUR = {"mst": figstyle.FAMILY_COLOUR["mst"],
              "bbcvc": figstyle.FAMILY_COLOUR["bb"],
              "anneal": figstyle.FAMILY_COLOUR["anneal"]}
ARM_LABEL = {"mst": "GHS-MST-Backbone", "bbcvc": "MIS-Connector-Backbone",
             "anneal": "Anneal-Local"}
#: Drawing order, so a redraw cannot silently reorder the bars.
ARM_ORDER = ("bbcvc", "mst", "anneal")

figstyle.apply_rc()


def _documents(indir: str) -> List[str]:
    """Run documents, whether they were collected flat or left where they ran.

    A collected directory holds `<tag>_<arm>_n<N>_m<M>_s<seed>.json` side by
    side. An archive of the runs themselves holds one DIRECTORY per run with a
    `summary.json` inside it, and that is what `results/bb/wifi_dagdeviren`
    is. Reading both means the manuscript figure is built from the archive
    itself rather than from a hand-made copy of it, and a hand-made copy is
    exactly where a stale run slips back in.
    """
    flat = sorted(glob.glob(os.path.join(indir, "*.json")))
    if flat:
        return flat
    return sorted(p for p in glob.glob(os.path.join(indir, "*", "summary.json")))


def load(indir: str) -> List[dict]:
    out = []
    for path in _documents(indir):
        if os.path.getsize(path) < 100:
            continue
        text = open(path, encoding="utf-8").read()
        i = text.find("{")
        if i < 0:
            continue
        try:
            doc = json.loads(text[i:])
        except json.JSONDecodeError:
            continue
        # A per-run directory names the run; a collected file names it in its
        # own basename.
        stem = (os.path.basename(os.path.dirname(path))
                if os.path.basename(path) == "summary.json"
                else os.path.basename(path)[:-5])   # <tag>_<arm>_n<N>_s<seed>
        parts = stem.split("_")
        # A run directory also holds plans and other side files. Only a stem
        # that ends in s<digits> is a run document; anything else is skipped
        # rather than parsed into a crash.
        if len(parts) < 3 or not (parts[-1][:1] == "s"
                                  and parts[-1][1:].isdigit()):
            continue
        doc["_arm"], doc["_seed"] = parts[1], int(parts[-1][1:])
        # The family is the instance size, so runs of different scales cannot
        # be averaged into one pair of axes by accident.
        doc["_family"] = "_".join(parts[2:-1]) or "n?"
        out.append(doc)
    return out


def figure(docs, outdir, name="wifi_n10", single_column=False):
    """One figure per instance family. THE ARM COUNT IS READ, NOT ASSUMED.

    This used to hard-code two arms and drop every seed that did not have
    exactly two, so adding a third arm produced an empty figure and no error.
    The arms are now whatever the run documents contain, in `ARM_ORDER`.
    """
    by_seed: Dict[int, Dict[str, dict]] = defaultdict(dict)
    for d in docs:
        by_seed[d["_seed"]][d["_arm"]] = d
    arms = [a for a in ARM_ORDER if any(a in v for v in by_seed.values())]
    arms += sorted({a for v in by_seed.values() for a in v} - set(arms))
    seeds = sorted(s for s, v in by_seed.items() if len(v) == len(arms))
    if not seeds:
        return []

    narrow = bool(single_column and PAPER)
    if narrow:
        # STACKED, NOT SIDE BY SIDE. Two panels beside each other in 88.9 mm
        # give each one 40 mm of width for three groups of three bars, and the
        # seed ticks collide. Stacked they share one seed axis and each keeps
        # the full column width.
        fig, (ax1, ax2) = plt.subplots(
            2, 1, sharex=True, figsize=(COL_W, 2.12),
            gridspec_kw={"height_ratios": (1.0, 1.25)})
    else:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(PRINT_W,
                                                     MAX_H if PAPER else 4.2))

    # (a) the channel: planned against discovered, drawn as a fall.
    # Every arm of a seed saw the same graph -- MEASURED, not assumed -- so any
    # one of them speaks for the seed; `agreed` records whether that held.
    agreed = all(len({by_seed[s][a]["discovered_vs_target"]["n_observed"]
                      for a in arms}) == 1 for s in seeds)
    for s in seeds:
        dv = by_seed[s][arms[0]]["discovered_vs_target"]
        kept = dv["n_target"] - dv["n_missing"]     # planned AND seen
        # Planned edges as one bar split into kept and lost, with the spurious
        # ones stacked on top. THE RADIO CAN OVERSHOOT: at these ranges it
        # usually finds MORE edges than were planned, so a single
        # "planned minus discovered" number would print as a negative loss and
        # hide the two errors that actually happened.
        ax1.bar(s, kept, width=0.55, color=OKABE_ITO["green"], zorder=2)
        ax1.bar(s, dv["n_missing"], width=0.55, bottom=kept,
                facecolor="white", edgecolor=OKABE_ITO["vermillion"],
                hatch="///", linewidth=1.0, zorder=2)
        ax1.bar(s, dv["n_extra"], width=0.55, bottom=dv["n_target"],
                color=OKABE_ITO["orange"], alpha=0.85, zorder=2)
        ax1.plot([s - 0.34, s + 0.34], [dv["n_target"]] * 2, color=INK,
                 lw=1.4, zorder=4)
        if not PAPER:
            ax1.annotate(f"+{dv['n_extra']}",
                         xy=(s, dv["n_target"] + dv["n_extra"]),
                         xytext=(0, 3), textcoords="offset points",
                         fontsize=NOTE_PT, color=OKABE_ITO["orange"],
                         ha="center", va="bottom")
        if dv["n_missing"]:
            # Outside the bar: over the hatching the digits are unreadable.
            ax1.annotate(f"-{dv['n_missing']}",
                         xy=(s + 0.28, kept + dv["n_missing"] / 2),
                         xytext=(4, 0), textcoords="offset points", fontsize=NOTE_PT,
                         color=OKABE_ITO["vermillion"], ha="left", va="center")
    ax1.set_xticks(seeds)
    ax1.set_xlim(min(seeds) - 0.6, max(seeds) + 0.6)
    # Headroom so the legend sits ABOVE the tallest bar instead of over the
    # count printed on it.
    _top = max(by_seed[s][arms[0]]["discovered_vs_target"]["n_target"]
               + by_seed[s][arms[0]]["discovered_vs_target"]["n_extra"]
               for s in seeds)
    ax1.set_ylim(0, _top * (1.04 if PAPER else 1.18))
    figstyle.axlabels(ax1, "Instance seed", "Edges in the topology",
                      "" if narrow else "Instance seed", "Edges")
    figstyle.titled(ax1, "" if narrow else "(a)" if PAPER
                    else "(a) Channel: planned against discovered",
                    "the line is the planned count; the radio misses some "
                    "edges and invents others", panel=True)
    channel_keys = [
        plt.Line2D([], [], color=INK, lw=1.4, label="planned"),
        plt.Rectangle((0, 0), 1, 1, facecolor=OKABE_ITO["green"],
                      label="seen" if narrow else "planned and seen"),
        plt.Rectangle((0, 0), 1, 1, facecolor="white",
                      edgecolor=OKABE_ITO["vermillion"], hatch="///",
                      linewidth=1.0,
                      label="never seen" if narrow else "planned, never seen"),
        plt.Rectangle((0, 0), 1, 1, facecolor=OKABE_ITO["orange"], alpha=0.85,
                      label="unplanned" if narrow else "seen, not planned")]
    if not PAPER:
        # BENEATH THE AXES. Inside the frame the key sat over the counts
        # printed on the bars, and the bars are the same height across seeds
        # so there is no free corner to move it to.
        ax1.legend(handles=channel_keys, loc="upper center",
                   bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False,
                   fontsize=KEY_PT)

    # (b) the algorithm, paired by seed on the graph each run actually saw
    width = 0.78 / len(arms)
    tallest = 0.0
    for i, arm in enumerate(arms):
        off = (i - (len(arms) - 1) / 2.0) * width
        xs = [s + off for s in seeds]
        ys = [by_seed[s][arm]["cover_weight"] for s in seeds]
        tallest = max(tallest, max(ys))
        # An INVALID run is drawn hatched, never as a plain bar. Its weight is
        # not comparable with a valid one: a cover that fails a gate can be
        # lighter precisely BECAUSE it failed, so plotting it unmarked would
        # reward the failure. MEASURED: on seed 5 the radio isolated node 9 and
        # MIS-Connector-Backbone admitted the edgeless node into the cover, splitting G[C].
        ok = [(by_seed[s][arm].get("validation_vs_discovered")
               or by_seed[s][arm]["validation"])["valid"] for s in seeds]
        _lab = (SHORT_LABEL.get(ARM_LABEL[arm], ARM_LABEL[arm]) if narrow
                else ARM_LABEL[arm])
        ax2.bar([x for x, v in zip(xs, ok) if v], [y for y, v in zip(ys, ok) if v],
                width=width, color=ARM_COLOUR[arm], label=_lab, zorder=2)
        ax2.bar([x for x, v in zip(xs, ok) if not v],
                [y for y, v in zip(ys, ok) if not v], width=width,
                facecolor="white", edgecolor=ARM_COLOUR[arm], hatch="///",
                linewidth=1.2, zorder=2)
        for x, y, s, good in zip(xs, ys, seeds, ok):
            empty = not by_seed[s][arm].get("cover")
            tx = by_seed[s][arm].get("totals", {}).get("tx")
            if tx and not empty and not PAPER:
                # Upright: with three arms per seed the numbers sit closer than
                # their own width and printed flat they overlap into mush.
                ax2.text(x, y + 0.015 * tallest, f"{tx}", ha="center",
                         va="bottom", fontsize=TINY_PT, color=MUTED,
                         rotation=90)
            if empty:
                # AN ARM THAT RETURNED NOTHING MUST NOT LOOK LIKE THE WINNER.
                # Its cover weight is 0, so a plain bar would draw the shortest
                # column on the panel and the eye reads short as best. The
                # column is replaced by a full-height marker that says what
                # actually happened.
                ax2.bar(x, tallest * 1.16, width=width, facecolor="white",
                        edgecolor=MUTED, hatch="xx", linewidth=1.0, zorder=2)
                ax2.text(x, tallest * 0.58, "no\ncover", ha="center",
                         va="center", fontsize=max(8.0, TINY_PT), color=INK,
                         zorder=5)
                if tx and not PAPER:
                    ax2.text(x, tallest * 1.175, f"{tx}", ha="center",
                             va="bottom", fontsize=TINY_PT, color=MUTED,
                             rotation=90)
            elif not good:
                # A cross where the bar fails, so the exception is found by
                # shape and not only by hatching, which prints faintly.
                ax2.scatter([x], [y * 0.5], marker="x", s=42, color=INK,
                            linewidth=1.4, zorder=4)
    ax2.set_xticks(seeds)
    ax2.set_xlim(min(seeds) - 0.6, max(seeds) + 0.6)
    ax2.set_ylim(0, tallest * (1.06 if PAPER else 1.32))
    figstyle.axlabels(ax2, "Instance seed", "Cover weight (lower is better)",
                      "Seed" if narrow else "Instance seed",
                      "Weight" if narrow else "Cover weight")
    figstyle.titled(ax2, "" if narrow else "(b)" if PAPER
                    else "(b) Algorithm: solution on the discovered graph",
                    "numbers above the bars are messages sent (tx)", panel=True)
    h, l = ax2.get_legend_handles_labels()
    h.append(plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=MUTED,
                           hatch="///", linewidth=1.0,
                           label="invalid" if narrow
                           else "invalid, not comparable"))
    if any(not by_seed[s][a].get("cover") for s in seeds for a in arms):
        h.append(plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=MUTED,
                               hatch="xx", linewidth=1.0,
                               label="returned no cover"))
    if not PAPER:
        ax2.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, -0.16),
                   ncol=2, frameon=False, fontsize=KEY_PT)

    n_valid = sum(1 for d in docs
                  if (d.get("validation_vs_discovered") or d["validation"])["valid"])
    first = by_seed[seeds[0]][arms[0]]
    n_nodes = first.get("n_nodes") or first.get("n") or "?"
    # k and the scheduler are NOT in the run document, so they are not printed
    # from a guess; the table carries them.
    if PAPER:
        # ONE SHARED KEY ROW for both panels. Two keys, one under each panel,
        # are each wider than the panel they belong to and grew into each
        # other; one row under the figure says every mark once.
        fig.tight_layout(rect=(0, 0.28 if narrow else 0.235, 1, 1.0),
                         h_pad=0.6 if narrow else 1.08)
        fig.legend(handles=channel_keys + h, loc="lower center",
                   ncol=3 if narrow else 4, bbox_to_anchor=(0.5, -0.012),
                   columnspacing=1.0 if narrow else 1.4, handlelength=1.4,
                   frameon=False, fontsize=KEY_PT)
    else:
        fig.tight_layout(rect=(0, 0.02, 1, 0.915 if SHOW_TITLE else 1.0))
    same = ("every arm in a seed saw the same graph" if agreed
            else "ARMS IN A SEED SAW DIFFERENT GRAPHS")
    if SHOW_TITLE:
        fig.suptitle(f"Real Mininet-WiFi runs, n = {n_nodes}",
                     x=0.006, y=0.995, ha="left", va="top", fontsize=TITLE_PT,
                     fontweight="bold")
        fig.text(0.006, 0.947,
                 f"{len(seeds) * len(arms)} runs, {n_valid} validator-clean "
                 f"against the graph the stations discovered; {same}",
                 fontsize=NOTE_PT, color=MUTED, ha="left", va="top")
    else:
        # The manuscript copy prints no title, so the run count, the clean
        # count and the same-graph check are handed to the caption instead.
        print(f"  caption: n={n_nodes}, {len(seeds) * len(arms)} runs, "
              f"{n_valid} validator-clean against the discovered graph; {same}")
    return figstyle.save(fig, outdir, name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", default="results/bb/figures/wifi")
    ap.add_argument("--single-column", action="store_true",
                    help="55 mm stacked copy for a one-column float")
    a = ap.parse_args(argv)
    docs = load(a.indir)
    if not docs:
        print("no run documents found")
        return 1
    print(f"loaded {len(docs)} runs")
    families: Dict[str, List[dict]] = defaultdict(list)
    for d in docs:
        families[d["_family"]].append(d)
    wrote = 0
    for fam, group in sorted(families.items()):
        paths = figure(group, a.outdir, name=f"wifi_{fam}",
                       single_column=a.single_column)
        if not paths:
            print(f"  {fam}: no seed has every arm; skipped")
            continue
        for p in paths:
            print("  wrote", p)
            wrote += 1
    return 0 if wrote else 1


if __name__ == "__main__":
    raise SystemExit(main())
