#!/usr/bin/env python3
"""Measured figures of the revised Section V. REPORTING ONLY.

Each figure is a row of panel files that the manuscript assembles with
`\\subfloat`, plus one full-width key strip, drawn in the house style of
`figstyle`: Okabe-Ito, colour = arm family, marker = variant, filled =
synchronous and hollow = asynchronous (`figstyle.scheduler_handles`), an 8.5 pt
floor, panels plus key under 70 mm. Called by `python3 -m ccvc.bb.r1_tables`,
which loads the blocks once for tables and figures alike.

    quality_*.{png,svg,pdf} + quality_key   blocks M2, M3, M4
    sens_*.{png,svg,pdf} + sens_key         blocks M5, M8
    chain.{png,svg,pdf}                     blocks M2 to M4, one column
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Dict, List, Sequence, Tuple

# Manuscript copies: figstyle reads this once at import (8.5 pt floor, no titles).
os.environ.setdefault("BBCVC_PAPER_FIGS", "1")

import numpy as np  # noqa: E402
from matplotlib import ticker  # noqa: E402

from ccvc.bb import figstyle  # noqa: E402
from ccvc.bb import r1_tables as T  # noqa: E402
from ccvc.bb import revision_stats as rs  # noqa: E402
from ccvc.bb.api import key_of  # noqa: E402

plt = figstyle.plt
OI = figstyle.OKABE_ITO
FC = figstyle.FAMILY_COLOUR
#: variant -> (colour, marker); the scheduler sets the fill.
VARIANT_STYLE = {
    "Anneal-Local": (FC["anneal"], "o"),
    "GHS-MST-Backbone": (FC["mst"], "s"),
    "MIS-Connector-Backbone": (FC["bb"], "^"),
    "DFS-Spanning-Backbone": (FC["dfs"], "D"),
    "Greedy-Ratio-Upstream": (FC["greedy-backbone"], "v"),
    "Trivial-Cover": (OI["grey"], "X"),
}
#: Quality and tightness panels: the primary arm, its baseline, two more
#: distributed arms, the best centralized heuristic of the development set and C = V.
FIG_ARMS = (
    T.PRIMARY,
    T.BASELINE,
    "MIS-Connector-Backbone/async",
    "DFS-Spanning-Backbone/async",
    "Greedy-Ratio-Upstream",
    T.TRIVIAL,
)
#: Block M8 arms (Amendment 1): MIS-connector (sync), spanning tree, annealing.
FIG_ARMS_M8 = (
    "MIS-Connector-Backbone/sync",
    "GHS-MST-Backbone/sync",
    "GHS-MST-Backbone/async",
    "Anneal-Local/sync",
    "Anneal-Local/async",
)
PANEL_H = 2.15  # in; with the key strip and the subfloat letter under 70 mm
STRIP_H = 0.3
FAMILY_MARK = {"dev": "o", "H1": "s", "H1-large": "s", "H2a": "^", "H2b": "D"}
WEIGHT_TICK = {
    "H1": "Uniform",
    "H1-unit": "Unit",
    "H1-degree": "Degree",
    "H1-lognormal": "Lognormal",
    "H1-energy": "Energy",
}
BAND_TICK = {
    "10-25": "10-25",
    "50": "50",
    "100": "100",
    "150-200": "150-200",
    "250+": "250+",
}


def style(arm: str) -> dict:
    variant, _, sched = arm.partition("/")
    colour, marker = VARIANT_STYLE[variant]
    return dict(
        color=colour, marker=marker, mfc="white" if sched == "async" else colour
    )


def _fig(width: float, height: float = PANEL_H):
    figstyle.apply_rc()
    return plt.subplots(figsize=(width, height), layout="constrained")


def key_strip(
    outdir: str, name: str, arms: Sequence[str], with_scheduler: bool
) -> List[str]:
    """One-row key over a row of subfloats, so no panel gives plot area to it.

    One entry per variant in its family colour and marker; with both
    schedulers drawn, the fill is keyed once by `figstyle.scheduler_handles`.
    """
    figstyle.apply_rc()
    fig = plt.figure(figsize=(figstyle.PRINT_W, STRIP_H))
    variants = list(dict.fromkeys(a.partition("/")[0] for a in arms))
    handles = [
        figstyle.Line2D([], [], ms=4.5, lw=1.0, label=T.name(v), **style(v + "/sync"))
        for v in variants
    ]
    if with_scheduler:
        for h in figstyle.scheduler_handles():
            h.set_label(h.get_label().capitalize())
            handles.append(h)
    fig.legend(
        handles=handles,
        loc="center",
        ncol=len(handles),
        frameon=False,
        handlelength=1.5,
        columnspacing=1.0,
        handletextpad=0.4,
    )
    return figstyle.save(fig, outdir, name)


def _errorbar(ax, x, d: Sequence[dict], arm: str) -> None:
    """Mean with the bootstrap 95% interval of `revision_stats.describe`."""
    y = np.array([r["mean"] for r in d])
    err = np.array(
        [[r["mean"] - r["ci_lo"] for r in d], [r["ci_hi"] - r["mean"] for r in d]]
    )
    ax.errorbar(x, y, yerr=err, ms=4.5, lw=1.0, capsize=2, elinewidth=0.8, **style(arm))


def _offsets(k: int):
    return np.linspace(-0.25, 0.25, k) if k > 1 else [0.0]


# --------------------------------------------------------------------------
# quality: M2, M3, M4
# --------------------------------------------------------------------------
def quality_panel(
    blocks: Sequence[T.Block], outdir: str, name: str
) -> Tuple[List[str], set]:
    """One family: mean ratio per band; optimum bands left of the dashed line."""
    order = [b[0] for b in rs.BANDS]
    pts, refs = defaultdict(list), {}
    for b in blocks:
        t = T.analyse(b)
        for c in T.bands_in(t):
            i = order.index(c[1])
            refs[i] = T.band_reference(t, *c)
            for arm in FIG_ARMS:
                d = T.quality_of(t, *c, arm, refs[i])
                if d:
                    pts[arm].append((i, d))
    if not refs:
        return [], set()
    xs = sorted(refs)
    fig, ax = _fig(figstyle.PRINT_W / 4)
    for arm, off in zip(FIG_ARMS, _offsets(len(FIG_ARMS))):
        got = sorted(pts.get(arm, []), key=lambda p: p[0])
        if got:
            _errorbar(ax, [xs.index(i) + off for i, _ in got], [d for _, d in got], arm)
    split = [j for j, i in enumerate(xs) if refs[i] == "LP"]
    if split and split[0] > 0:
        ax.axvline(split[0] - 0.5, color=figstyle.MUTED, lw=0.8, ls=(0, (5, 4)))
    ax.set_xticks(
        range(len(xs)),
        [BAND_TICK[order[i]] for i in xs],
        rotation=35,
        ha="right",
        rotation_mode="anchor",
    )
    ax.set_xlim(-0.6, len(xs) - 0.4)
    ax.set_xlabel("Nodes $n$")
    ax.set_ylabel("Weight / reference")
    return figstyle.save(fig, outdir, name), set(pts)


# --------------------------------------------------------------------------
# sensitivity: M5, M8
# --------------------------------------------------------------------------
def ratio_per_instance(
    rows: Sequence[dict], info, arms: Sequence[str]
) -> Dict[Tuple, Dict[str, float]]:
    """(group, instance, k) -> arm -> mean weight / LP over valid runs, common basis only."""
    w, bad = defaultdict(lambda: defaultdict(list)), set()
    for r in T.prepare(rows):
        a = T.arm_of(r)
        if a not in arms or T.scope(r) != "free":
            continue
        key = (r.get("group", ""), r["instance"], int(r["k"]))
        if T.ok(r):
            w[key][a].append(
                float(r["total_weight"]) / info[(r["instance"], int(r["k"]))]["lp"]
            )
        else:
            bad.add(key)
    return {
        key: {a: float(np.mean(v)) for a, v in got.items()}
        for key, got in w.items()
        if key not in bad and set(got) == set(arms)
    }


def present(rows: Sequence[dict], arms: Sequence[str]) -> List[str]:
    got = {T.arm_of(r) for r in T.prepare(rows)}
    return [a for a in arms if a in got]


def tightness_panel(b: T.Block, outdir: str) -> Tuple[List[str], List[str]]:
    """Block M5 (H-d): mean ratio to the LP bound against m/(nk), descriptive."""
    arms = present(b.rows, FIG_ARMS)
    by = defaultdict(list)
    for (_, inst, k), v in ratio_per_instance(b.rows, b.info, arms).items():
        it = b.info[(inst, k)]
        by[round(it["m"] / (it["n"] * k), 2)].append(v)
    if not by:
        return [], []
    fig, ax = _fig(figstyle.PRINT_W / 4)
    taus = sorted(by)
    for arm in arms:
        _errorbar(ax, taus, [rs.describe([v[arm] for v in by[t]]) for t in taus], arm)
    ax.set_xticks(taus, [f"{t:.2f}" for t in taus])
    ax.set_xlabel("Tightness $m/(nk)$")
    ax.set_ylabel("Weight / LP bound")
    return figstyle.save(fig, outdir, "sens_tightness"), arms


def factor_effects(
    rows: Sequence[dict], info
) -> Tuple[Dict[Tuple[str, str], Dict[str, float]], int]:
    """Block M8: mean paired change of the ratio to LP per (arm, factor) and value.

    Pairs are (instance, loss) units on which the default and the setting both
    ended valid. Also counts the settings whose valid share differs from the
    default on the same units.
    """
    runs = defaultdict(list)  # (arm, params, instance, k, loss) -> rows
    for r in T.prepare(rows):
        other_weights = r.get("group") in T.WEIGHT_GROUPS and r["group"] != "H1"
        if other_weights or T.scope(r) != "free":
            continue
        runs[
            (
                T.arm_of(r),
                r.get("params") or "",
                r["instance"],
                int(r["k"]),
                r.get("loss"),
            )
        ].append(r)
    out: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(dict)
    changed = 0
    for arm, params in sorted({(a, p) for a, p, *_ in runs if p}):
        over = json.loads(params)
        if len(over) != 1:
            raise SystemExit(f"M8 runs change one factor at a time, got {params}")
        ((factor, value),) = over.items()
        units = [(i, k, l) for a, p, i, k, l in runs if (a, p) == (arm, params)]
        deltas, valid_set, valid_def = [], 0, 0
        for i, k, l in units:
            s, d = runs[(arm, params, i, k, l)], runs.get((arm, "", i, k, l), [])
            valid_set += all(T.ok(r) for r in s)
            valid_def += bool(d) and all(T.ok(r) for r in d)
            if d and all(T.ok(r) for r in s + d):
                lp = info[(i, k)]["lp"]
                deltas.append(
                    np.mean([float(r["total_weight"]) for r in s]) / lp
                    - np.mean([float(r["total_weight"]) for r in d]) / lp
                )
        changed += valid_set != valid_def
        if deltas:
            out[(arm, factor)][str(value)] = float(np.mean(deltas))
    return out, changed


def factor_panel(b: T.Block, outdir: str) -> Tuple[List[str], List[str], List[str]]:
    """Range of the mean paired change over the values of each factor, per arm."""
    eff, changed = factor_effects(b.rows, b.info)
    if not eff:
        return [], [], []
    factors = sorted({f for _, f in eff}, key=lambda f: T.PARAM_LABEL.get(f, f))
    arms = [a for a in FIG_ARMS_M8 if any(a == x for x, _ in eff)]
    fig, ax = _fig(figstyle.PRINT_W / 2)
    for arm, off in zip(arms, _offsets(len(arms))):
        st = style(arm)
        for j, f in enumerate(factors):
            vals = list(eff.get((arm, f), {}).values())
            if vals:
                ax.plot(
                    [min(vals), max(vals)], [j + off] * 2, color=st["color"], lw=1.0
                )
                ax.plot(vals, [j + off] * len(vals), ls="", ms=3.5, **st)
    ax.axvline(0, color=figstyle.MUTED, lw=0.8, ls=(0, (5, 4)))
    ax.set_yticks(range(len(factors)), [T.PARAM_LABEL.get(f, f) for f in factors])
    ax.invert_yaxis()
    ax.set_xlabel("Change of the ratio")
    biggest = max(abs(v) for d in eff.values() for v in d.values())
    macros = [
        T.macro("SensValidityChanged", changed),
        T.macro("SensLargestChange", T.f2(biggest, 3)),
    ]
    return figstyle.save(fig, outdir, "sens_factors"), macros, arms


def weights_panel(b: T.Block, outdir: str) -> Tuple[List[str], List[str]]:
    """Block M8, four weight distributions next to the uniform default, lossless."""
    rows = [
        r
        for r in b.rows
        if r.get("group") in T.WEIGHT_GROUPS
        and not r.get("params")
        and float(r.get("loss") or 0) == 0
    ]
    groups = [g for g in T.WEIGHT_GROUPS if any(r["group"] == g for r in rows)]
    if len(groups) < 2:
        return [], []
    arms = present(rows, FIG_ARMS_M8)
    per = ratio_per_instance(rows, b.info, arms)
    fig, ax = _fig(figstyle.PRINT_W / 4)
    for arm, off in zip(arms, _offsets(len(arms))):
        xs, ds = [], []
        for j, g in enumerate(groups):
            vals = [v[arm] for key, v in per.items() if key[0] == g]
            if vals:
                xs.append(j + off)
                ds.append(rs.describe(vals))
        if xs:
            _errorbar(ax, xs, ds, arm)
    ax.set_xticks(
        range(len(groups)),
        [WEIGHT_TICK[g] for g in groups],
        rotation=45,
        ha="right",
        rotation_mode="anchor",
    )
    ax.set_ylabel("Weight / LP bound")
    return figstyle.save(fig, outdir, "sens_weights"), arms


# --------------------------------------------------------------------------
# chain length L and depth R: M2 to M4
# --------------------------------------------------------------------------
def chain_length(weights: Dict[int, float], edges) -> int:
    """L: edges on the longest key-increasing path, key(v) = (w/(deg+1), id)."""
    deg, adj = Counter(), defaultdict(list)
    for u, v in edges:
        deg[u] += 1
        deg[v] += 1
        adj[u].append(v)
        adj[v].append(u)
    key = {v: key_of(w, deg[v], v) for v, w in weights.items()}
    depth: Dict[int, int] = {}
    for v in sorted(weights, key=key.get):
        depth[v] = max((depth[u] + 1 for u in adj[v] if key[u] < key[v]), default=0)
    return max(depth.values(), default=0)


def chain_points(blocks: Dict[str, T.Block]) -> Tuple[Dict[str, Dict[int, Tuple]], int]:
    """family -> n -> (max L, max R over lossless synchronous runs); runs with R > L."""
    L, R, viol = defaultdict(dict), defaultdict(dict), 0
    for fam, b in blocks.items():
        lens = {}
        for r in b.rows:
            key = (r["instance"], int(r["k"]))
            if key not in lens:
                it = b.info[key]
                lens[key] = chain_length(
                    *rs._prepared(it["path"], int(r.get("weight_scale") or 10))
                )
                L[fam][it["n"]] = max(L[fam].get(it["n"], 0), lens[key])
            d = T._num(r.get("mis_depth"))
            if (
                d is not None
                and r["scheduler"] == "sync"
                and float(r.get("loss") or 0) == 0
            ):
                n = int(r["n"])
                R[fam][n] = max(R[fam].get(n, 0), int(d))
                viol += d > lens[key]
    return {f: {n: (L[f][n], R[f].get(n)) for n in L[f]} for f in L}, viol


def chain_figure(
    blocks: Dict[str, T.Block], outdir: str
) -> Tuple[List[str], List[str]]:
    pts, viol = chain_points(blocks)
    if not pts:
        return [], []
    fig, ax = _fig(figstyle.COL_W)
    for fam, by_n in pts.items():
        ns, mk = sorted(by_n), FAMILY_MARK.get(fam, "o")
        ax.plot(
            ns, [by_n[n][0] for n in ns], ls="", marker=mk, ms=4.5, color=OI["blue"]
        )
        rn = [n for n in ns if by_n[n][1] is not None]
        # R = 0 has no place on a log axis; it is drawn on the axis floor
        ax.plot(
            rn,
            [max(by_n[n][1], 0.8) for n in rn],
            ls="",
            marker=mk,
            ms=4.5,
            color=OI["vermillion"],
            mfc="white",
        )
    ns = sorted({n for d in pts.values() for n in d})
    ax.plot(ns, [n - 1 for n in ns], color=figstyle.MUTED, lw=0.8, ls=(0, (5, 4)))
    ax.set_xscale("log")
    ax.set_yscale("log")
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        axis.set_minor_formatter(ticker.NullFormatter())
    ax.set_xlabel("Nodes $n$")
    ax.set_ylabel("Chain length or depth")
    line = figstyle.Line2D
    handles = [
        line(
            [], [], ls="", marker="o", color=OI["blue"], label="$L$, longest key path"
        ),
        line(
            [],
            [],
            ls="",
            marker="o",
            color=OI["vermillion"],
            mfc="white",
            label="$R$, realised depth",
        ),
        line([], [], color=figstyle.MUTED, ls=(0, (5, 4)), label="$n - 1$"),
    ] + [
        line(
            [],
            [],
            ls="",
            marker=FAMILY_MARK.get(f, "o"),
            color=figstyle.MUTED,
            label=T.FAMILY_LABEL.get(f, f),
        )
        for f in pts
        if f != "H1-large"
    ]
    ax.legend(
        handles=handles,
        loc="upper left",
        handlelength=1.2,
        borderpad=0.3,
        labelspacing=0.25,
    )
    Ls = [v[0] for d in pts.values() for v in d.values()]
    Rs = [v[1] for d in pts.values() for v in d.values() if v[1] is not None]
    macros = [T.macro("LMax", max(Ls)), T.macro("RAboveL", viol)]
    macros += [T.macro("RMax", max(Rs))] if Rs else []
    return figstyle.save(fig, outdir, "chain"), macros


# --------------------------------------------------------------------------
def write_all(
    blocks: Dict[str, T.Block], held: Dict[str, T.Block], outdir: str
) -> Tuple[List[str], List[str]]:
    paths, macros, drawn = [], [], set()
    panels = [("quality_dev", [blocks["M2"]])] if "M2" in blocks else []
    for name, fams in (
        ("quality_h1", ("H1", "H1-large")),
        ("quality_h2a", ("H2a",)),
        ("quality_h2b", ("H2b",)),
    ):
        if any(f in held for f in fams):
            panels.append((name, [held[f] for f in fams if f in held]))
    for name, bs in panels:
        p, arms = quality_panel(bs, outdir, name)
        paths, drawn = paths + p, drawn | arms
    if drawn:
        paths += key_strip(
            outdir, "quality_key", [a for a in FIG_ARMS if a in drawn], False
        )
    sens = []
    if "M5" in blocks:
        p, arms = tightness_panel(blocks["M5"], outdir)
        paths, sens = paths + p, sens + arms
    if "M8" in blocks:
        p, m, arms = factor_panel(blocks["M8"], outdir)
        q, arms2 = weights_panel(blocks["M8"], outdir)
        paths, macros, sens = paths + p + q, macros + m, sens + arms + arms2
    if sens:
        order = list(dict.fromkeys(FIG_ARMS + FIG_ARMS_M8))
        paths += key_strip(outdir, "sens_key", sorted(set(sens), key=order.index), True)
    fams = {"dev": blocks["M2"]} if "M2" in blocks else {}
    fams.update(held)
    if fams:
        p, m = chain_figure(fams, outdir)
        paths, macros = paths + p, macros + m
    return paths, macros
