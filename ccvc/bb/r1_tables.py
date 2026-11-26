#!/usr/bin/env python3
"""LaTeX tables and number macros of the revised Section V. REPORTING ONLY.

One generator per registered block of paper/CoverWeave_R1/contract/R1_PREREG.md.
Every statistic comes from `revision_stats` (medians, bootstrap intervals,
Clopper-Pearson bounds, paired Wilcoxon with Holm, rank-biserial r); this file
only selects, arranges and prints. Inputs are the plain `r1_run` row CSVs of
each block (block M7: the `m7_rows.csv` of ccvc/bb/mnwifi/m7.py, whose
runs/<run_id>/summary.json give the ESP32 charge estimate) and the instance
files (for W(V), the LP bound and the chain length L).

    python3 -m ccvc.bb.r1_tables \\
        --block M2 'results/bb/r1/M2/*.csv' --block M3 'results/bb/r1/M3/*.csv' \\
        --instances M3 results/bb/r1/heldout ...  \\
        --block M7 results/bb/r1_m7/m7_rows.csv --instances M7 ...

writes paper/CoverWeave_R1/tables/r1/*.tex, numbers.tex and, through
`r1_figures`, the figures under paper/CoverWeave_R1/figures/r1/. A block
without rows is skipped and says so.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter, defaultdict
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np

from ccvc.bb import armnames
from ccvc.bb import revision_stats as rs

PROJECT = rs.PROJECT
OUT_TABLES = "paper/CoverWeave_R1/tables/r1"
OUT_FIGURES = "paper/CoverWeave_R1/figures/r1"
PRIMARY, BASELINE = rs.PRIMARY, rs.BASELINE
#: Multi-arm tables print the primary arm's scheduler; the CSVs of
#: revision_stats keep both.
SCHEDULER = PRIMARY.split("/")[1]
#: C = V as a reference arm, so it shares the common valid basis and the tests.
TRIVIAL = "Trivial-Cover/none"
#: Prereg Amendment 4: the token-based arm is not loss-hardened.
NOT_HARDENED = ("DFS-Spanning-Backbone",)
ALPHA = 0.05

#: NOTATION.md spelling where it differs from armnames.DISPLAY_NAMES.
R1_NAMES = {
    "TemperFlux-T": "TemperFlux with tree aggregation",
    "TemperFlux-Tk": "TemperFlux with Trickle timing",
    "NexusWarp-T": "NexusWarp with tree aggregation",
    "Wu-Li CDS/B": "Wu-Li CDS (Bloom)",
    "Wu-Li CDS/C": "Wu-Li CDS (chunked)",
    "D-GCCVC": "Distributed GCCVC",
    "D-GRCCVC": "Distributed GRCCVC",
    "D-GWCCVC": "Distributed GWCCVC",
    "C-GCCVC": "Centralized GCCVC",
    "C-GRCCVC": "Centralized GRCCVC",
    "C-GWCCVC": "Centralized GWCCVC",
    "Trivial-Cover": "Trivial cover $C = V$",
    "LP-bound": "LP bound",
}
FAMILY_LABEL = {
    "dev": "Published benchmark",
    "H1": "Path plus random edges",
    "H1-large": "Path plus random edges",
    "H2a": "Unit disk graph",
    "H2b": "Barab\\'asi-Albert",
    "M9": "Flow-only infeasible",
}
#: Band column of the held-out table, under an "$n$" header.
BAND_SHORT = {
    "10-25": "10-25",
    "50": "50",
    "100": "100",
    "150-200": "150-200",
    "250+": "250+",
}
BAND_LABEL = {
    "10-25": "$n = 10$ to $25$",
    "50": "$n = 50$",
    "100": "$n = 100$",
    "150-200": "$n = 150$ to $200$",
    "250+": "$n \\ge 250$",
}
#: Parameter override names (block M8, F9 ablation) in words.
PARAM_LABEL = {
    "gap_patience": "Gap patience",
    "escalate_patience": "Escalation patience",
    "quiet_periods": "Quiescence periods",
    "stale_periods": "Stale periods",
    "max_repair_rounds": "Repair rounds",
    "ack_max_attempts": "Acknowledgement attempts",
    "alpha": "Cooling factor",
    "cool_every": "Cooling interval",
    "t0_scale": "Initial temperature scale",
    "t_min_frac": "Final temperature fraction",
    "lam_scale": "Penalty scale",
    "adaptive_stale": "Adaptive stale window",
}
#: A boolean repair switched off, in words (the F9 ablation of block M6).
PARAM_OFF = {"adaptive_stale": "fixed stale window"}
#: Block M8 weight distributions: row `group` -> label (board interface, E3).
WEIGHT_GROUPS = {
    "H1": "Uniform",
    "H1-unit": "Unit",
    "H1-degree": "Degree-correlated",
    "H1-lognormal": "Lognormal",
    "H1-energy": "Inverse residual energy",
}


class Block(NamedTuple):
    rows: List[dict]
    info: Dict[Tuple[str, int], dict]
    optima: Dict[Tuple[str, int], float]
    central: Dict[Tuple[str, int, str], dict]


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------
_truthy, _num = rs._truthy, rs._num


def prepare(rows: Sequence[dict]) -> List[dict]:
    """Canonical arm names, and the instance's feasibility in `infeasible`.

    In a run row `infeasible` is the arm's own announcement, and revision_stats
    scopes instances by it; an M9 run that ends Unresolved on a flow-infeasible
    instance would otherwise be scored as a feasible one. `instance_feasible`
    is the flow check of the instance.
    """
    out = armnames.canonical_rows([dict(r) for r in rows])
    for r in out:
        if r.get("instance_feasible") in ("yes", "no"):
            r["infeasible"] = str(r["instance_feasible"] == "no")
    return out


def with_trivial(rows: Sequence[dict], info) -> List[dict]:
    """Adds C = V, of weight W(V), on every free feasible instance."""
    seen = {}
    for r in rows:
        if not _truthy(r["infeasible"]) and int(r["m"]) < int(r["n"]) * int(r["k"]):
            seen.setdefault((r["instance"], r["k"], r.get("loss")), r)
    triv = TRIVIAL.split("/")
    return list(rows) + [
        {
            **r,
            "variant": triv[0],
            "scheduler": triv[1],
            "status": "ok",
            "verdict": "solved",
            "valid": "True",
            "valid_discovered": "True",
            "total_weight": str(info[(r["instance"], int(r["k"]))]["w_all"]),
            "cover_size": r["n"],
        }
        for r in seen.values()
    ]


def optima_of(rows: Sequence[dict], extra=None) -> Dict[Tuple[str, int], float]:
    """Proven optima: an optima CSV, plus the rows' own exact reference."""
    out = dict(extra or {})
    for r in rows:
        if r.get("exact_status") == "ok" and _num(r.get("exact_weight")) is not None:
            key, v = (r["instance"], int(r["k"])), float(r["exact_weight"])
            if out.setdefault(key, v) != v:
                raise SystemExit(f"optima disagree for {key}")
    return out


def ok(r: dict) -> bool:
    return r["status"] == "ok" and _truthy(r["valid"]) and r["verdict"] == "solved"


def solved_on_discovered(r: dict) -> bool:
    """Amendment 4 reading: Solved and valid on the final discovered graph.

    A lossless run discovers the planned graph, so a row without the reading
    (an arm that reports no graph) falls back to planned-graph validity.
    """
    v = r.get("valid_discovered")
    return r["verdict"] == "solved" and _truthy(r["valid"] if v in (None, "") else v)


def scope(r: dict) -> str:
    if _truthy(r["infeasible"]):
        return "infeasible"
    return "forced" if int(r["m"]) == int(r["n"]) * int(r["k"]) else "free"


def arm_of(r: dict) -> str:
    return f"{r['variant']}/{r['scheduler']}"


def condition(r: dict) -> str:
    """M6 channel condition: the loss label plus any parameter override."""
    return f"{r.get('loss', '')}|{r.get('params', '') or ''}"


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------
def name(arm: str) -> str:
    variant, _, sched = arm.partition("/")
    d = armnames.display(variant)
    return R1_NAMES.get(variant, R1_NAMES.get(d, d))


def f2(x: Optional[float], places: int = 2) -> str:
    return "--" if x is None or x != x else f"{x:.{places}f}"


def ci(d: dict) -> str:
    return f"{f2(d['mean'])} [{f2(d['ci_lo'])}, {f2(d['ci_hi'])}]"


def iqr(d: dict) -> str:
    return f"{f2(d['median'])} [{f2(d['q1'])}, {f2(d['q3'])}]"


def pval(p: float) -> str:
    return "$<0.001$" if p < 0.001 else f"{p:.3f}"


def frac(x: int, n: int) -> str:
    return f"{x}/{n}" if n else "--"


def pct(x: float) -> str:
    return f"{100 * x:.1f}"


def float_env(
    caption: str,
    label: str,
    cols: str,
    head: List[str],
    body: List[str],
    note: str = "",
    wide: bool = True,
) -> str:
    env = "table*" if wide else "table"
    width = r"\textwidth" if wide else r"\columnwidth"
    out = [
        rf"\begin{{{env}}}[!t]" if wide else rf"\begin{{{env}}}[!b]",
        r"\centering",
        r"\footnotesize",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\setlength{\tabcolsep}{3pt}",
        rf"\begin{{tabular*}}{{{width}}}{{@{{\extracolsep{{\fill}}}}{cols}@{{}}}}",
        r"\toprule",
        *head,
        r"\midrule",
        *body,
        r"\bottomrule",
        r"\end{tabular*}",
    ]
    if note:
        out += [r"\par\vspace{3pt}{\footnotesize\raggedright", note + r"\par}"]
    return "\n".join(out + [rf"\end{{{env}}}", ""])


def macro(name_: str, value) -> str:
    assert name_.isalpha(), name_
    return rf"\newcommand{{\rone{name_}}}{{{value}}}"


# --------------------------------------------------------------------------
# quality: revision_stats on one family
# --------------------------------------------------------------------------
#: id(rows) -> (rows, tables); holding `rows` keeps its id from being reused.
_ANALYSED: Dict[int, Tuple[list, dict]] = {}


def analyse(b: Block) -> dict:
    """revision_stats.analyse with C = V added, once per block (10 000 resamples)."""
    if id(b.rows) not in _ANALYSED:
        rows = with_trivial(prepare(b.rows), b.info)
        _ANALYSED[id(b.rows)] = (b.rows, rs.analyse(rows, b.info, b.optima, b.central))
    return _ANALYSED[id(b.rows)][1]


def band_reference(t: dict, cond: str, band: str) -> str:
    """The band's reference: the optimum if every basis instance has one."""
    q = [
        r
        for r in t["quality"]
        if (r["condition"], r["band"], r["arm"]) == (cond, band, PRIMARY)
    ]
    full = [r for r in q if r["reference"] == "optimum" and r["n"] == r["basis"]]
    return "optimum" if full else "LP"


def quality_of(t: dict, cond: str, band: str, arm: str, ref: str) -> Optional[dict]:
    hit = [
        r
        for r in t["quality"]
        if (r["condition"], r["band"], r["arm"], r["reference"])
        == (cond, band, arm, ref)
    ]
    return hit[0] if hit else None


def bands_in(t: dict) -> List[Tuple[str, str]]:
    order = [b[0] for b in rs.BANDS]
    seen = {(r["condition"], r["band"]) for r in t["quality"] if r["band"] != rs.POOLED}
    return sorted(seen, key=lambda cb: (cb[0], order.index(cb[1])))


def primary_supported(t: dict, cond: str, band: str) -> bool:
    """Bold is earned: the primary arm is lower than every tested arm after Holm."""
    tests = [x for x in t["tests"] if (x["condition"], x["band"]) == (cond, band)]
    return bool(tests) and all(
        x["p_two_holm_band"] < ALPHA and x["r_rb"] > 0 for x in tests
    )


def table_quality(b: Block, label: str = "tab:r1quality") -> Tuple[str, List[str]]:
    """Block M2 (points x, xi, xiii): every arm and reference, per size band."""
    t = analyse(b)
    cb = bands_in(t)
    refs = {c: band_reference(t, *c) for c in cb}
    arms = [
        a
        for a in sorted({r["arm"] for r in t["quality"]}, key=rs._arm_key)
        if a.endswith("/" + SCHEDULER)
    ]
    arms += [TRIVIAL] + list(rs.CENTRAL_LABEL.values()) + ["LP-bound"]
    head = [
        "Arm & " + " & ".join(BAND_LABEL[b] for _, b in cb) + r" \\",
        "& "
        + " & ".join(
            ("opt." if refs[c] == "optimum" else "LP")
            + f", {quality_of(t, *c, PRIMARY, refs[c])['basis']} inst."
            for c in cb
        )
        + r" \\",
    ]
    body = []
    for a in arms:
        cells = []
        for c in cb:
            d = quality_of(t, *c, a, refs[c])
            txt = ci(d) if d else "--"
            if d and a == PRIMARY and primary_supported(t, *c):
                txt = r"\textbf{" + txt + "}"
            cells.append(txt)
        if any(x != "--" for x in cells):
            body.append(name(a) + " & " + " & ".join(cells) + r" \\")
    pooled = quality_of(t, cb[0][0], rs.POOLED, PRIMARY, "optimum")
    macros = [macro("DevPrimaryRatioOpt", f2(pooled["mean"], 3))] if pooled else []
    tex = float_env(
        "Cover weight over the proven optimum, opt., or the LP lower bound, LP, on "
        "the published benchmark graphs, as the mean with a bootstrap 95\\% interval "
        "over instances. Instances with $m = nk$ or without a cover are excluded and "
        "the scheduler is asynchronous.",
        label,
        "l" + "r" * len(cb),
        head,
        body,
        f"Bold marks {name(PRIMARY)} where a paired Wilcoxon test with Holm "
        "correction finds it lighter than every other arm of that band.",
    )
    return tex, macros


def table_heldout(
    blocks: Dict[str, Block], label: str = "tab:r1heldout"
) -> Tuple[str, List[str]]:
    """Blocks M3 and M4 (points iv, x, xiii), hypothesis H-b per family and band."""
    body, macros, met, tested, last = [], [], 0, 0, None
    for fam, b in blocks.items():
        t = analyse(b)
        for c in bands_in(t):
            test = [
                x
                for x in t["tests"]
                if (x["condition"], x["band"], x["other"]) == (*c, BASELINE)
            ]
            if not test:
                continue
            x, ref = test[0], band_reference(t, *c)
            p, q = quality_of(t, *c, PRIMARY, ref), quality_of(t, *c, BASELINE, ref)
            hb = x["hb_p_lower_holm_bands"] < ALPHA
            met, tested = met + hb, tested + 1
            mean = ci(p)
            if FAMILY_LABEL.get(fam, fam) != last:
                last = FAMILY_LABEL.get(fam, fam)
                body.append(r"\multicolumn{10}{@{}l}{" + last + r"} \\")
            body.append(
                " & ".join(
                    [
                        BAND_SHORT[c[1]],
                        str(x["n_pairs"]),
                        "opt."
                        if x["ref_lp"] == 0
                        else "LP"
                        if x["ref_optimum"] == 0
                        else "mixed",
                        iqr(p),
                        r"\textbf{" + mean + "}" if hb else mean,
                        iqr(q),
                        ci(q),
                        pval(x["hb_p_lower_holm_bands"]),
                        f"{x['r_rb']:+.2f}",
                        "met" if hb else "not met",
                    ]
                )
                + r" \\"
            )
    if not body:
        return "", []
    macros += [macro("HbMet", met), macro("HbTested", tested)]
    head = [
        rf"$n$ & Inst. & Ref. & \multicolumn{{2}}{{c}}{{{name(PRIMARY)}}} & "
        rf"\multicolumn{{2}}{{c}}{{{name(BASELINE)}}} & $p$ & $r$ & H-b \\",
        r"\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
        r"& & & Median [IQR] & Mean [95\% CI] & Median [IQR] & Mean [95\% CI] & & & \\",
    ]
    tex = float_env(
        "Cover weight over the proven optimum or the LP bound on the held-out "
        f"families, {name(PRIMARY)} against {name(BASELINE)} under the asynchronous "
        "scheduler. One-sided paired Wilcoxon test over instances with Holm "
        "correction over bands and the matched-pairs rank-biserial $r$.",
        label,
        "lrlrrrrrrl",
        head,
        body,
        f"Bold marks {name(PRIMARY)} where the test rejects at the 5\\% level.",
    )
    return tex, macros


# --------------------------------------------------------------------------
# reliability: M2, M3, M4, M9 and the centralized references
# --------------------------------------------------------------------------
def tally(rows: Sequence[dict]) -> Dict[str, Counter]:
    """Per arm: runs by scope, valid, Unresolved, Truncated, false successes."""
    out: Dict[str, Counter] = defaultdict(Counter)
    for r in prepare(rows):
        t, s = out[arm_of(r)], scope(r)
        t["runs"] += 1
        t[s] += 1
        t[s + "_ok"] += ok(r) if s != "infeasible" else r["status"] == "infeasible"
        if s != "infeasible":
            t["unresolved"] += r["status"] == "unresolved"
            t["truncated"] += r["status"] == "truncated"
        t["false_success"] += r["verdict"] == "solved" and not solved_on_discovered(r)
    return out


def central_tally(b: Block) -> Dict[str, Counter]:
    """Per centralized heuristic: valid counts on m < nk and m = nk instances."""
    out: Dict[str, Counter] = defaultdict(Counter)
    # by_family shares one central dict across families; count this block's instances only
    mine = {(r["instance"], int(r["k"])) for r in b.rows}
    for (inst, k, lab), r in b.central.items():
        info = b.info.get((inst, k))
        if (inst, k) not in mine or info is None or info["lp_status"] == "infeasible":
            continue
        s = "forced" if info["m"] == info["n"] * k else "free"
        out[lab][s] += 1
        out[lab][s + "_ok"] += _truthy(r["valid"])
    return out


def fs_cell(t: Counter) -> str:
    return (
        f"{t['false_success']} ({pct(rs.upper_one_sided(t['false_success'], t['runs']))})"
        if t["runs"]
        else "--"
    )


def table_reliability(
    dev: Optional[Block],
    held: Sequence[Block],
    m9: Optional[Block],
    label: str = "tab:r1reliability",
) -> Tuple[str, List[str]]:
    """Points iv, viii, xi: validity, Unresolved rate, witness coverage, M9."""
    sets = [("dev", [dev] if dev else []), ("held", list(held))]
    tal = {k: tally([r for b in bs for r in b.rows]) for k, bs in sets}
    cen = {k: defaultdict(Counter) for k, _ in sets}
    for k, bs in sets:
        for b in bs:
            for lab, c in central_tally(b).items():
                cen[k][lab].update(c)
    t9 = tally(m9.rows) if m9 else {}
    dup = set()
    for bs in sets[0][1] + sets[1][1]:
        dup |= {d["arm"] for d in analyse(bs)["duplicates"]}
    arms = sorted({a for k in tal for a in tal[k]} | set(t9), key=rs._arm_key)
    arms = [a for a in arms if a.endswith("/" + SCHEDULER) and a not in dup]

    def cells(t: Counter) -> List[str]:
        if not t:
            return ["--"] * 4
        return [
            frac(t["free_ok"], t["free"]),
            frac(t["forced_ok"], t["forced"]),
            f"{t['unresolved']}/{t['truncated']}",
            fs_cell(t),
        ]

    body = []
    for a in arms:
        dv, hd, nine = (
            tal["dev"].get(a, Counter()),
            tal["held"].get(a, Counter()),
            t9.get(a, Counter()),
        )
        wit = dv + hd
        body.append(
            " & ".join(
                [
                    name(a),
                    *cells(dv),
                    *cells(hd),
                    frac(wit["infeasible_ok"], wit["infeasible"]),
                    frac(nine["infeasible_ok"], nine["infeasible"]),
                    str(nine["false_success"]) if nine else "--",
                ]
            )
            + r" \\"
        )
    for lab in rs.CENTRAL_LABEL.values():
        row = []
        for k, _ in sets:
            c = cen[k].get(lab)
            row += (
                [
                    frac(c["free_ok"], c["free"]),
                    frac(c["forced_ok"], c["forced"]),
                    "--",
                    "--",
                ]
                if c
                else ["--"] * 4
            )
        if any(x != "--" for x in row):
            body.append(" & ".join([name(lab), *row, "--", "--", "--"]) + r" \\")
    head = [
        r"& \multicolumn{4}{c}{Published benchmark} & \multicolumn{4}{c}{Held-out} & "
        r"\multicolumn{3}{c}{Infeasible instances} \\",
        r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-12}",
        r"& Valid & Valid & \textsc{Unres.} & False & Valid & Valid & \textsc{Unres.} & "
        r"False & & Flow & False \\",
        r"Arm & $m<nk$ & $m=nk$ & \textsc{Trunc.} & succ. & $m<nk$ & $m=nk$ & "
        r"\textsc{Trunc.} & succ. & Witness & only & succ. \\",
    ]
    held_all = Counter()
    for a in arms:
        held_all.update(tal["held"].get(a, Counter()))
    macros = []
    if held_all["runs"]:
        macros += [
            macro("HeldRuns", held_all["runs"]),
            macro("HeldFalseSucc", held_all["false_success"]),
            macro(
                "HeldFsUpper",
                pct(rs.upper_one_sided(held_all["false_success"], held_all["runs"])),
            ),
        ]
    if t9:
        n9 = sum(t9[a]["runs"] for a in t9)
        macros += [
            macro("NineRuns", n9),
            macro("NineAnnounced", sum(t9[a]["infeasible_ok"] for a in t9)),
        ]
    tex = float_env(
        "Valid runs, \\textsc{Unresolved} and \\textsc{Truncated} runs on feasible "
        "instances, and false successes with the one-sided 95\\% Clopper-Pearson "
        "upper bound in percent. The last columns count \\textsc{Infeasible} "
        "announcements on instances without a cover.",
        label,
        "l" + "r" * 11,
        head,
        body,
        "Witness counts the run-level witness and counting bound on the published "
        "and held-out families, flow only counts instances that only the flow "
        "check rejects.",
    )
    return tex, macros


# --------------------------------------------------------------------------
# loss: block M6
# --------------------------------------------------------------------------
def condition_label(cond: str) -> Tuple[str, str]:
    """(group row, row label) of an M6 channel condition."""
    loss, _, params = cond.partition("|")
    if loss.startswith("ge:"):
        _, p, burst = loss.split(":")
        group, row_ = (
            f"Gilbert-Elliott loss, mean burst {burst}",
            f"{float(p) * 100:g}\\%",
        )
    elif loss == "emp":
        group, row_ = "Measured delivery ratios", "Per link"
    elif float(loss) == 0:
        group, row_ = "Lossless", "0\\%"
    else:
        group, row_ = "Independent loss", f"{float(loss) * 100:g}\\%"
    for k, v in sorted(json.loads(params).items()) if params else ():
        what = PARAM_OFF.get(k) if v is False else None
        group += ", " + (what or f"{PARAM_LABEL.get(k, k).lower()} {v}")
    return group, row_


def _cond_key(cond: str):
    loss, _, params = cond.partition("|")
    kind = (
        2
        if loss.startswith("ge:")
        else 3
        if loss == "emp"
        else 0
        if float(loss) == 0
        else 1
    )
    level = (
        float(loss.split(":")[1]) if kind == 2 else 0.0 if kind == 3 else float(loss)
    )
    return (kind, params, level)


def instance_median(rows: Sequence[dict], key: str) -> Optional[float]:
    """Median over instances of the per-instance mean (prereg section 5)."""
    per = defaultdict(list)
    for r in rows:
        v = _num(r.get(key))
        if v is not None:
            per[r["instance"]].append(v)
    return float(np.median([np.mean(v) for v in per.values()])) if per else None


def table_loss(b: Block, label: str = "tab:r1loss") -> Tuple[str, List[str]]:
    """Block M6 (points v, vi, xii), hypothesis H-c per channel condition."""
    by = defaultdict(list)
    for r in prepare(b.rows):
        by[condition(r)].append(r)
    body, macros, worst, last = [], [], 1.0, None
    for cond in sorted(by, key=_cond_key):
        rs_ = by[cond]
        group, row_label = condition_label(cond)
        if group != last:
            body.append(r"\multicolumn{13}{@{}l}{" + group + r"} \\")
            last = group
        hard = [r for r in rs_ if r["variant"] not in NOT_HARDENED]
        tok = [r for r in rs_ if r["variant"] in NOT_HARDENED]
        if any(r.get("valid_discovered") in (None, "") for r in hard):
            raise SystemExit(
                f"M6 {cond}: a loss-hardened run has no discovered-graph reading"
            )
        n = len(hard)
        vd = sum(solved_on_discovered(r) for r in hard)
        vp = sum(ok(r) for r in hard)
        fs = sum(r["verdict"] == "solved" and not solved_on_discovered(r) for r in hard)
        per_arm = defaultdict(lambda: [0, 0])
        for r in hard:
            per_arm[arm_of(r)][0] += solved_on_discovered(r)
            per_arm[arm_of(r)][1] += 1
        low = min(x / m for x, m in per_arm.values())
        worst = min(worst, low)
        lo, hi = rs.clopper_pearson(vd, n)
        body.append(
            " & ".join(
                [
                    row_label,
                    str(n),
                    f"{pct(vd / n)} [{pct(lo)}, {pct(hi)}]",
                    pct(low),
                    pct(vp / n),
                    str(fs),
                    str(sum(r["status"] == "truncated" for r in hard)),
                    f2(instance_median(hard, "restarts"), 0),
                    f2(np.mean([_num(r.get("planned_missing")) or 0 for r in hard])),
                    str(sum(int(_num(r.get("double_claims")) or 0) for r in hard)),
                    f2(instance_median(hard, "slots"), 0),
                    f2(instance_median(hard, "tx"), 0),
                    frac(sum(ok(r) for r in tok), len(tok)),
                ]
            )
            + r" \\"
        )
    macros.append(macro("LossWorstArmValid", pct(worst)))
    head = [
        r"Loss & Runs & Valid on $\Ghat^{*}$ & Lowest & Valid & False & & & Missing & "
        r"Double & & & \\",
        r"& & [95\% CI] & arm & on $G$ & succ. & \textsc{Trunc.} & Restarts & links & "
        r"owners & Slots & tx & TokenTrail \\",
    ]
    tex = float_env(
        "Validity under loss for the loss-hardened arms, in percent of runs, with "
        "the Clopper-Pearson 95\\% interval on the discovered graph and the share "
        "of the weakest arm. Restarts, slots and tx are medians over instances, "
        "missing links a mean per run and double owners a total.",
        label,
        "l" + "r" * 12,
        head,
        body,
        "TokenTrail is a comparison arm without loss hardening and is reported as "
        "valid runs on the planned graph.",
    )
    return tex, macros


# --------------------------------------------------------------------------
# cost: blocks M2 and M3, lossless
# --------------------------------------------------------------------------
#: Synchronous: slots and the depth R are defined there, as in the cost identity.
COST_ARMS = (
    "Anneal-Local/sync",
    "GHS-MST-Backbone/sync",
    "MIS-Connector-Backbone/sync",
    "DFS-Spanning-Backbone/sync",
)
COST_COLS = (
    ("tx", "tx", 0),
    ("rx", "rx", 0),
    ("bytes_tx", "Bytes", 0),
    ("max_payload", "Payload", 0),
    ("slots", "Slots", 0),
    ("mis_depth", "$R$", 0),
    ("state_bytes_max", "State bytes", 0),
    ("radio_activity_mJ_proxy", "Radio mJ", 1),
)


def table_cost(b: Block, label: str = "tab:r1cost") -> Tuple[str, List[str]]:
    """Points ix, xii, xv: messages, bytes, payload, depth R, state and energy."""
    rows = [r for r in prepare(b.rows) if ok(r)]
    by = defaultdict(list)
    for r in rows:
        for band in rs.bands_of(int(r["n"])):
            if band != rs.POOLED:
                by[(band, arm_of(r))].append(r)
    order = [x[0] for x in rs.BANDS]
    body, macros = [], []
    for band in sorted({k[0] for k in by}, key=order.index):
        first = True
        for a in COST_ARMS:
            got = by.get((band, a))
            if not got:
                continue
            body.append(
                " & ".join(
                    [BAND_LABEL[band] if first else "", name(a)]
                    + [f2(instance_median(got, key), p) for key, _, p in COST_COLS]
                )
                + r" \\"
            )
            first = False
    state = [
        _num(r.get("state_bytes_max"))
        for r in rows
        if _num(r.get("state_bytes_max")) is not None
    ]
    if state:
        macros.append(macro("StateBytesMax", f2(max(state), 0)))
    head = ["Band & Arm & " + " & ".join(h for _, h, _ in COST_COLS) + r" \\"]
    tex = float_env(
        "Cost of valid lossless runs on the published benchmark graphs under the "
        "synchronous scheduler, median over instances. Radio energy is the radio term of the emulator energy model, a "
        "model estimate and not a measurement.",
        label,
        "ll" + "r" * len(COST_COLS),
        head,
        body,
        "$R$ is the realised decision depth of the independent set phase and state "
        "bytes the largest protocol state of a node.",
    )
    return tex, macros


# --------------------------------------------------------------------------
# wireless: block M7
# --------------------------------------------------------------------------
#: M7 row `block` (E2, ccvc/bb/mnwifi/m7.py) -> set name in the table.
WIFI_SET = {"dev": "Published benchmark", "W": "Unit disk graph"}


def esp32_charge(csv_paths: Sequence[str]) -> Dict[str, float]:
    """run_id -> ESP32 radio-model charge in mAh, from runs/<run_id>/summary.json
    next to each M7 rows CSV; the rows themselves carry no ESP32 estimate."""
    out = {}
    for p in csv_paths:
        for doc in glob.glob(
            os.path.join(os.path.dirname(p), "runs", "*", "summary.json")
        ):
            v = (
                json.load(open(doc, encoding="utf-8"))
                .get("totals", {})
                .get("energy_mah_esp32_model")
            )
            if v is not None:
                out[os.path.basename(os.path.dirname(doc))] = float(v)
    return out


def table_wireless(
    b: Block, charge: Dict[str, float], label: str = "tab:r1wireless"
) -> Tuple[str, List[str]]:
    """Block M7 (points v, xii, xv): both validity readings and the cost per arm."""
    rows = prepare(b.rows)
    bad = {r.get("execution_backend") for r in rows} - {"mininet-wifi"}
    if bad:
        raise SystemExit(
            f"M7 rows from backend {sorted(map(str, bad))}, not Mininet-WiFi"
        )
    keys = ("tx", "rx", "bytes_tx", "max_payload", "state_bytes_max")
    body = []
    for blk in sorted(
        {r.get("block", "") for r in rows},
        key=lambda x: ((list(WIFI_SET) + [x]).index(x), x),
    ):
        mine = [r for r in rows if r.get("block", "") == blk]
        for i, arm in enumerate(sorted({arm_of(r) for r in mine}, key=rs._arm_key)):
            got = [r for r in mine if arm_of(r) == arm]
            mah = [charge[r["run_id"]] for r in got if r.get("run_id") in charge]
            missing = [
                _num(r.get("planned_missing"))
                for r in got
                if _num(r.get("planned_missing")) is not None
            ]
            body.append(
                " & ".join(
                    [
                        WIFI_SET.get(blk, blk) if i == 0 else "",
                        name(arm),
                        str(len(got)),
                        frac(sum(solved_on_discovered(r) for r in got), len(got)),
                        frac(
                            sum(
                                r["verdict"] == "solved" and _truthy(r["valid"])
                                for r in got
                            ),
                            len(got),
                        ),
                        f2(np.mean(missing) if missing else None),
                        *[f2(instance_median(got, k), 0) for k in keys],
                        f2(float(np.median(mah)) if mah else None, 3),
                    ]
                )
                + r" \\"
            )
    if not body:
        return "", []
    head = [
        r"Set & Arm & Runs & Valid on $\Ghat^{*}$ & Valid on $G$ & Missing links & "
        r"tx & rx & Bytes & Payload & State bytes & mAh \\"
    ]
    tex = float_env(
        "Mininet-WiFi runs, one process per station, with validity on the discovered "
        "and on the planned graph and medians of the cost over instances. The charge "
        "in mAh is an ESP32 radio model estimate and not a measurement.",
        label,
        "ll" + "r" * 10,
        head,
        body,
    )
    return tex, []


# --------------------------------------------------------------------------
# inputs and main
# --------------------------------------------------------------------------
def load_block(
    paths: Sequence[str],
    dirs: Sequence[str],
    optima_csv: Sequence[str],
    central_csv: Sequence[str],
    cache: str,
) -> Block:
    rows = rs.read_csvs(paths)
    info = rs.instance_info(rows, dirs, cache)
    return Block(
        rows,
        info,
        optima_of(rows, rs.load_optima(optima_csv)),
        rs.load_central(central_csv),
    )


def _pairs(items) -> Dict[str, List[str]]:
    out = defaultdict(list)
    for key, val in items or ():
        out[key] += sorted(glob.glob(val, recursive=True)) or [val]
    return out


def by_family(b: Block) -> Dict[str, Block]:
    fams = defaultdict(list)
    for r in b.rows:
        fams[r.get("group", "")].append(r)
    return {
        f: Block(rs_, b.info, b.optima, b.central) for f, rs_ in sorted(fams.items())
    }


def write_all(
    blocks: Dict[str, Block],
    out_tables: str,
    out_figures: Optional[str],
    charge: Optional[Dict[str, float]] = None,
) -> List[str]:
    os.makedirs(out_tables, exist_ok=True)
    held = {}
    for key in ("M3", "M4"):
        if key in blocks:
            held.update(by_family(blocks[key]))
    jobs = {
        "quality": lambda: table_quality(blocks["M2"]) if "M2" in blocks else ("", []),
        "heldout": lambda: table_heldout(held) if held else ("", []),
        "reliability": lambda: table_reliability(
            blocks.get("M2"), list(held.values()), blocks.get("M9")
        )
        if blocks.get("M2") or held or blocks.get("M9")
        else ("", []),
        "loss": lambda: table_loss(blocks["M6"]) if "M6" in blocks else ("", []),
        "cost": lambda: table_cost(blocks["M2"]) if "M2" in blocks else ("", []),
        "wireless": lambda: table_wireless(blocks["M7"], charge or {})
        if "M7" in blocks
        else ("", []),
    }
    wrote, macros = [], [
        "% Generated by python3 -m ccvc.bb.r1_tables; do not edit by hand."
    ]
    for name_, job in jobs.items():
        tex, mac = job()
        if not tex:
            print(f"  {name_}: no rows, skipped")
            continue
        path = os.path.join(out_tables, f"{name_}.tex")
        open(path, "w", encoding="utf-8").write(tex)
        wrote.append(path)
        macros += mac
    if out_figures:
        from ccvc.bb import r1_figures

        fig_paths, fig_macros = r1_figures.write_all(blocks, held, out_figures)
        wrote += fig_paths
        macros += fig_macros
    path = os.path.join(out_tables, "numbers.tex")
    open(path, "w", encoding="utf-8").write("\n".join(macros) + "\n")
    return wrote + [path]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--block",
        nargs=2,
        action="append",
        metavar=("NAME", "GLOB"),
        help="rows of a block, e.g. M3 'results/bb/r1/M3/*.csv' (repeatable)",
    )
    ap.add_argument(
        "--instances",
        nargs=2,
        action="append",
        metavar=("NAME", "DIR"),
        help="instance directory of a block; M2 defaults to the published dataset",
    )
    ap.add_argument("--optima", nargs=2, action="append", metavar=("NAME", "CSV"))
    ap.add_argument("--central", nargs=2, action="append", metavar=("NAME", "CSV"))
    ap.add_argument("--out", default=os.path.join(PROJECT, OUT_TABLES))
    ap.add_argument("--figures", default=os.path.join(PROJECT, OUT_FIGURES))
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args(argv)
    rows, dirs = _pairs(a.block), _pairs(a.instances)
    optima, central = _pairs(a.optima), _pairs(a.central)
    if "M2" in rows and "M2" not in dirs:
        from ccvc.bb import matrix

        dirs["M2"] = [matrix.dataset_dir()]
    if any("r1_calibration_aborted" in p for ps in rows.values() for p in ps):
        raise SystemExit("rows of the aborted calibration are not reported (prereg)")
    blocks = {
        k: load_block(
            ps,
            dirs[k],
            optima.get(k, []),
            central.get(k, []),
            os.path.join(a.out, ".cache", f"lp_{k}.csv"),
        )
        for k, ps in rows.items()
    }
    charge = esp32_charge(rows.get("M7", []))
    for p in write_all(blocks, a.out, None if a.no_figures else a.figures, charge):
        print("  wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
