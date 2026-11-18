#!/usr/bin/env python3
"""The manuscript's result tables, derived in one pass from the measured rows.

WHY A SECOND TABLE SCRIPT AND NOT AN EDIT TO `report_pipeline`. That pipeline
writes the report's own tables and is the thing several other artefacts are
pinned to; the manuscript wants a different cut of the SAME rows, arranged by
node count rather than by sweep, and a per-arm wireless summary that the report
prints as three separate tables. Adding both to the pipeline would change what
every existing consumer gets. Nothing here re-measures anything: every number is
a mean over rows that `ccvc.bb.sweep` already wrote, selected by exactly the
rule `ccvc.bb.compare_figures` uses for its figures, so a table and a figure can
never disagree about which instances they are talking about.

THE COMMON VALID SUBSET IS THE SELECTION RULE, imported rather than reimplemented.
Instances that are provably infeasible are dropped, then only the instances every
arm of that sweep answered cleanly are kept. An arm that fails an instance
otherwise vanishes from that instance's average instead of scoring badly in it,
and ranking arms over different instance sets rewards failure.

ONE n COMES FROM ONE SWEEP. `sweep_medium_n100_fixed_v2` holds six instances at
n = 50 and six at n = 100, and `sweep_medium_n50_k6_join_v2` holds eighteen at
n = 50. Pooling the two would average across instance sets that were never
compared, so each node count is served by the single sweep that measured it
most, and the caption says which.

ENERGY. The scaling table CANNOT carry the ESP32 estimate. That model is
`api.Counters.energy_mah_esp32_model` and it needs `radio_on_ms`, which the
simulator sweep does not write to `rows.csv`; substituting `t_conv_ms` for it
would be an invention, and on the wireless runs the two differ by a factor of
ten. What the sweep does record is the radio-activity term of the Mininet-WiFi
model, and this script recomputes it from `bytes_tx`, `rx` and `retx` with the
coefficients in `ccvc.bb.energy` and CHECKS its own arithmetic against the
stored column. The ESP32 estimate appears only in the wireless table, where the
run documents actually carry it.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from ccvc.bb import armnames, compare_figures, report_pipeline
from ccvc.bb.energy import EnergyCoefficients

#: The sweeps the manuscript draws on, in the order `report_pipeline` names them.
SCALES: Tuple[Tuple[str, str], ...] = (
    ("Small, n = 10 to 25", "results/bb/sweep_small_full_k6_clean_v2"),
    ("Medium, n = 50", "results/bb/sweep_medium_n50_k6_join_v2"),
    ("Medium, n = 100", "results/bb/sweep_medium_n100_fixed_v2"),
)

#: Five arms named outright, plus whichever Wu-Li variant is lightest on this
#: evidence. The sixth is CHOSEN FROM THE DATA rather than fixed here, because
#: the three Wu-Li variants differ in how the dominating set is announced and
#: not in what it contains, and naming the wrong one in a table of quality would
#: be a claim the rows do not support.
NAMED_ARMS = (
    "GHS-MST-Backbone",
    "MIS-Connector-Backbone",
    "Anneal-Local",
    "Anneal-Trickle",
    "DFS-Spanning-Backbone",
)
WULI_VARIANTS = (
    "WuLi-Dominating-Exact",
    "WuLi-Dominating-Bloom",
    "WuLi-Dominating-Chunked",
)

#: How close two variants have to be before the choice between them stops being
#: a measurement and becomes noise, and which one wins when that happens.
WULI_TIE_TOLERANCE = 0.001
WULI_PREFERRED = "WuLi-Dominating-Exact"

#: The scheduler the tables report. Both were measured; one is shown so that a
#: row is one number rather than a pair, and the scheduler comparison has its
#: own figure.
SCHEDULER = "sync"

#: Wireless families, in the order the evidence was collected.
WIFI_ORDER = ("n10_m20", "n15_m90", "n20_m160")
#: Wireless run directory prefix -> the arm it holds. The second field is a
#: REPOSITORY arm name and is translated through `armnames.display` where the
#: row is printed, so this tuple never needs editing when the paper renames.
WIFI_ARMS = (("bbcvc", "MIS-Connector-Backbone"), ("mst", "GHS-MST-Backbone"),
             ("anneal", "Anneal-Local"))


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _f(row: dict, key: str) -> Optional[float]:
    return compare_figures._f(row, key)


def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _tex(text: str) -> str:
    return text.replace("_", r"\_").replace("&", r"\&").replace("%", r"\%")


def _arm(arm: str) -> str:
    """An arm name as the manuscript prints it, escaped for LaTeX."""
    return _tex(armnames.display(arm))


def _sci(value: float) -> str:
    """A coefficient in LaTeX maths, not in Python's exponent spelling.

    `f"{2e-05:g}"` prints `2e-05`, and inside maths mode that sets as an
    italic letter e wedged between two numbers.
    """
    mantissa, _, exponent = f"{value:e}".partition("e")
    mant = f"{float(mantissa):g}"
    exp = int(exponent)
    if exp == 0:
        return mant
    power = r"10^{" + str(exp) + "}"
    return power if mant == "1" else mant + r" \times " + power


def _num(value: Optional[float], places: int = 0) -> str:
    return "--" if value is None else f"{value:.{places}f}"


def radio_proxy_mJ(row: dict, coeff: EnergyCoefficients) -> Optional[float]:
    """The traffic term of the Mininet-WiFi model, from the row's own counts.

    Recomputed rather than read so that the table is reproducible from the raw
    counters; `check_energy_recomputation` then compares it with the value the
    sweep stored, and a mismatch stops the script instead of printing a number
    whose provenance is ambiguous.
    """
    b, rx, retx = _f(row, "bytes_tx"), _f(row, "rx"), _f(row, "retx")
    if b is None or rx is None:
        return None
    return (
        b * coeff.tx_cost_mJ_per_byte
        + rx * coeff.rx_cost_mJ_per_delivery
        + (retx or 0.0) * coeff.retx_cost_mJ
    )


def check_energy_recomputation(rows: Sequence[dict], coeff: EnergyCoefficients) -> int:
    """Refuse to publish a model output this script cannot reproduce."""
    checked = 0
    for r in rows:
        stored = _f(r, "radio_activity_mJ_proxy")
        if stored is None:
            continue
        mine = radio_proxy_mJ(r, coeff)
        if mine is None or abs(mine - stored) > 1e-4:
            raise SystemExit(
                f"energy recomputation disagrees with the stored column on "
                f"{r.get('instance')} / {r.get('variant')}: recomputed {mine}, "
                f"stored {stored}. The coefficients in ccvc/bb/energy.py are "
                f"not the ones this sweep was measured with."
            )
        checked += 1
    return checked


# --------------------------------------------------------------------------
# 1. the scaling table
# --------------------------------------------------------------------------
def stages_are_disjoint(loaded: Dict[str, List[dict]]) -> bool:
    """Do these sweeps measure entirely different instances?

    THIS IS THE QUESTION THAT DECIDES HOW NODE COUNTS ARE COMBINED, and it is
    answered from the instance names rather than from a directory naming
    convention. The v2 sweeps overlap: six instances at n = 50 appear in two of
    them, so the same instance would be counted twice and one arm's answer to
    it required twice over, which is why those sweeps give each node count to a
    single owner. The full sweep's stages are cut by node count and density and
    share nothing, so their rows can simply be put together.
    """
    total = sum(len({r["instance"] for r in rows}) for rows in loaded.values())
    union = len(set().union(*({r["instance"] for r in rows}
                              for rows in loaded.values()))) if loaded else 0
    return total == union


def gather(scales=SCALES) -> Tuple[Dict[int, List[dict]], Dict[int, str], dict]:
    """Common-valid rows indexed by node count, combined to suit the sweeps.

    TWO WAYS TO COMBINE, CHOSEN BY MEASUREMENT. When the sweeps share instances
    a node count is given to the single sweep that measured the most of them,
    because pooling would double count the overlap. When they share none the
    rows are pooled per node-count band and the common valid subset is taken
    over the union, so no stage's instances are thrown away merely because a
    neighbouring stage is larger. The band is the unit because the band is what
    the tables print.
    """
    coeff = EnergyCoefficients()
    loaded: Dict[str, List[dict]] = {}
    fingerprints: Dict[str, str] = {}
    labels: Dict[str, str] = {}
    for label, path in scales:
        csv_path = os.path.join(path, "rows.csv")
        if not os.path.exists(csv_path):
            continue
        rows = compare_figures.load(csv_path)
        fingerprints[path] = report_pipeline.check_single_version(rows, path)
        labels[path] = label
        loaded[path] = rows
    if not loaded:
        return {}, {}, {"sweeps": {}, "energy_rows_checked": 0,
                        "coefficients": coeff, "pooled": False}

    prov: Dict[str, dict] = {}
    checked = 0
    if stages_are_disjoint(loaded):
        pooled: List[dict] = []
        for rows in loaded.values():
            pooled.extend(rows)
        by_n: Dict[int, List[dict]] = defaultdict(list)
        owner: Dict[int, str] = {}
        contributors: Dict[Tuple[int, int, str], set] = {}
        for band in SCALE_RANGES:
            band_rows = [r for r in pooled
                         if (r.get("n") or "").isdigit()
                         and band[0] <= int(r["n"]) <= band[1]]
            if not band_rows:
                continue
            # FEASIBILITY FIRST, AND FROM THE ROWS THAT RAN. `common_valid`
            # still judges feasibility row by row, which reads `sweep`'s
            # skipped-row default of False as evidence that the instance is
            # solvable; on a dense stage where half the rows were cut by the
            # time budget that turns a wall-clock cut into twelve solvable
            # problems every arm failed. The instances are therefore removed
            # here, by the rule that looks only at rows which actually ran, and
            # what reaches `common_valid` is already feasible. This matters for
            # more than the denominator: an instance left in as feasible also
            # contributes its arms to the set that every instance in the band
            # must then have been solved by.
            infeasible = report_pipeline.infeasible_instances(band_rows)
            feasible_rows = [r for r in band_rows
                             if r["instance"] not in infeasible]
            keep, _common, p = compare_figures.common_valid(feasible_rows)
            p["instances_total"] = len({r["instance"] for r in band_rows})
            p["instances_infeasible"] = len(infeasible)
            checked += check_energy_recomputation(keep, coeff)
            for r in keep:
                by_n[int(r["n"])].append(r)
            key = "+".join(sorted(os.path.basename(path) for path in loaded
                                  if any(r in band_rows for r in loaded[path][:1])))
            contributors[band] = {os.path.basename(path) for path in loaded
                                  if any((r.get("n") or "").isdigit()
                                         and band[0] <= int(r["n"]) <= band[1]
                                         for r in loaded[path])}
            name = "+".join(sorted(contributors[band])) or band[2]
            prov[name] = {"label": band[2],
                          "fingerprint": "+".join(sorted(
                              {fingerprints[path] for path in loaded
                               if os.path.basename(path) in contributors[band]})),
                          **p}
            for n in {int(r["n"]) for r in keep}:
                owner[n] = name
            _ = key
        return (dict(by_n), owner,
                {"sweeps": prov, "energy_rows_checked": checked,
                 "coefficients": coeff, "pooled": True})

    per_sweep: Dict[str, Dict[int, List[dict]]] = {}
    for path, rows in loaded.items():
        keep, _common, p = compare_figures.common_valid(rows)
        checked += check_energy_recomputation(keep, coeff)
        mine: Dict[int, List[dict]] = defaultdict(list)
        for r in keep:
            if (r.get("n") or "").isdigit():
                mine[int(r["n"])].append(r)
        per_sweep[path] = mine
        prov[path] = {"label": labels[path], "fingerprint": fingerprints[path], **p}

    # One sweep per node count: the one that measured the most instances there.
    owner = {}
    for path, mine in per_sweep.items():
        for n, rows in mine.items():
            got = len({r["instance"] for r in rows})
            best = owner.get(n)
            if best is None or got > len({r["instance"] for r in per_sweep[best][n]}):
                owner[n] = path
    out = {n: per_sweep[path][n] for n, path in owner.items()}
    return (
        out,
        owner,
        {"sweeps": prov, "energy_rows_checked": checked, "coefficients": coeff,
         "pooled": False},
    )


def pick_wuli(by_n: Dict[int, List[dict]]) -> Tuple[str, Dict[str, float]]:
    """The lightest Wu-Li variant on this evidence, and every variant's mean."""
    means: Dict[str, List[float]] = defaultdict(list)
    for rows in by_n.values():
        for r in rows:
            if r["variant"] in WULI_VARIANTS and r["scheduler"] == SCHEDULER:
                w = _f(r, "total_weight")
                if w is not None:
                    means[r["variant"]].append(w)
    scored = {v: sum(xs) / len(xs) for v, xs in means.items() if xs}
    if not scored:
        return WULI_VARIANTS[0], {}
    # A NEAR TIE IS BROKEN TOWARDS Exact, NOT BY THE THIRD DECIMAL. Exact and
    # Chunked return the same cover on this evidence and differ only in how the
    # dominating set is announced, so on the current rows their means are equal
    # to the tenth of a unit. An exact-equality rule is still not stable enough:
    # the subset is common-valid, so a change anywhere else in the sweep, the
    # annealing re-measurement included, shifts the instance set under all three
    # variants at once and a fraction of a unit would then decide which name
    # appears in five tables. Anything within a tenth of a per cent of the
    # lightest therefore counts as tied, and Exact wins a tie because it is the
    # variant that computes the dominating set rather than approximating it.
    best = min(scored.values())
    tied = [v for v in WULI_VARIANTS
            if v in scored and scored[v] <= best * (1.0 + WULI_TIE_TOLERANCE)]
    if WULI_PREFERRED in tied:
        return WULI_PREFERRED, scored
    return (tied[0] if tied else
            min(scored, key=lambda v: (scored[v], WULI_VARIANTS.index(v)))), scored


#: (column head, row key, decimal places). `radio` is computed, not read.
COLUMNS: Tuple[Tuple[str, str, int], ...] = (
    (r"$|C|$", "cover_size", 1),
    ("Weight", "total_weight", 0),
    ("tx", "tx", 0),
    ("rx", "rx", 0),
    ("Slots", "slots", 1),
    (r"$t_{\mathrm{conv}}$ (ms)", "t_conv_ms", 0),
    # NO WALL-CLOCK COLUMN. `seconds` is how long the run took on the machine
    # that measured it, and the sweep was measured on a shared box whose load
    # varied by a factor of three between passes. Averaged over rows from
    # different passes it is not one quantity, and the spread inside a single
    # pass is already wider than the difference between passes: among the 4858
    # scored first-pass rows the median is 0.49 s, the 99th percentile 51.4 s
    # and the maximum 5028.3 s. A code fingerprint cannot rescue it either,
    # because a fingerprint records which code ran and not how loaded the box
    # was. The timing argument these tables make is carried by t_conv_ms, which
    # is simulated and therefore identical no matter what else the machine was
    # doing.
    ("Radio (mJ)", "radio", 2),
)


def arm_rows(rows: Sequence[dict], arm: str) -> Tuple[List[dict], str]:
    """This arm's rows and the scheduler they were actually measured under.

    ONE ARM WAS NEVER RUN SYNCHRONOUSLY. Anneal-Trickle has 32 asynchronous
    rows in the small sweep, 17 in the medium one and no synchronous row
    anywhere, and it sits on the quality-against-cost front, so dropping it
    would delete a result while showing it unmarked would claim a scheduler it
    was not measured under. The fallback is generic and the row is flagged.
    """
    mine = [r for r in rows if r["variant"] == arm and r["scheduler"] == SCHEDULER]
    if mine:
        return mine, SCHEDULER
    for sched in sorted({r["scheduler"] for r in rows if r["variant"] == arm}):
        alt = [r for r in rows if r["variant"] == arm and r["scheduler"] == sched]
        if alt:
            return alt, sched
    return [], SCHEDULER


def cells(
    rows: Sequence[dict], arm: str, coeff: EnergyCoefficients
) -> Optional[List[str]]:
    mine, _sched = arm_rows(rows, arm)
    if not mine:
        return None
    out = []
    for _head, key, places in COLUMNS:
        if key == "radio":
            vals = [
                v for v in (radio_proxy_mJ(r, coeff) for r in mine) if v is not None
            ]
        else:
            vals = [v for v in (_f(r, key) for r in mine) if v is not None]
        out.append(_num(_mean(vals), places))
    return out


#: The node-count bands the manuscript reports, as (low, high, head). BLOCKS AND
#: COLUMNS ARE BANDS, NOT SWEEP DIRECTORIES OR SINGLE NODE COUNTS, so the number
#: of floats and columns is a property of the manuscript rather than of how many
#: stages the sweep happened to be run in. A stage added later lands inside an
#: existing band instead of adding a thirteenth block and a third float.
SCALE_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (10, 25, "n = 10 to 25"),
    (50, 100, "n = 50 to 100"),
    (150, 200, "n = 150 to 200"),
    (250, 1000, "n = 250 to 1000"),
)


def band_of(n: int) -> Optional[Tuple[int, int, str]]:
    for band in SCALE_RANGES:
        if band[0] <= n <= band[1]:
            return band
    return None


def group_bands(by_n: Dict[int, List[dict]]) -> List[Tuple[str, List[dict], List[int]]]:
    """Rows gathered into node-count bands, in ascending order.

    POOLING WITHIN A BAND IS POOLING INSTANCES, NOT AVERAGES. Every row kept
    here already survived its own sweep's common valid subset, so an instance
    in the band was answered cleanly by every arm of the sweep that measured
    it, and a mean over the band is a mean over instances rather than a mean of
    per-node-count means that would weight six instances at one node count
    equally with thirty at another.
    """
    buckets: Dict[Tuple[int, int, str], List[dict]] = {}
    ns: Dict[Tuple[int, int, str], set] = {}
    for n in sorted(by_n):
        band = band_of(n)
        if band is None:
            continue
        buckets.setdefault(band, []).extend(by_n[n])
        ns.setdefault(band, set()).add(n)
    return [(band, buckets[band], sorted(ns[band]))
            for band in SCALE_RANGES if band in buckets]


def band_heading(ncols: int, band: Tuple[int, int, str],
                 rows: Sequence[dict]) -> str:
    """The band's heading, with only the numbers in maths.

    "to" MUST NOT SIT INSIDE THE DOLLARS. Written `$n = 10 to 25$` it sets as
    three italic variables run together, `10to25`, because maths mode has no
    words; the band reads as a product of t and o. Each number is therefore
    closed off on its own.
    """
    lo, hi, _plain = band
    inst = len({r["instance"] for r in rows})
    dens = density_qualifier(rows)
    span = f"$n = {lo}$" if lo == hi else f"$n = {lo}$ to ${hi}$"
    return (r"\multicolumn{" + str(ncols) + r"}{@{}l}{\textit{" + span
            + (r", " + dens if dens else "")
            + r", " + str(inst) + r" instances}} \\")


def table_scaling(
    by_n: Dict[int, List[dict]], owner: Dict[int, str], meta: dict, wuli: str
) -> str:
    coeff = meta["coefficients"]
    arms = list(NAMED_ARMS) + [wuli]
    head = " & ".join(h for h, _, _ in COLUMNS)
    off_scheduler = set()
    out = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\caption{Arm behaviour by node-count band on the common valid "
        r"subset of the pooled sweeps, synchronous scheduler, every column a "
        r"mean over the instances every arm answered cleanly.}",
        r"\label{tab:scaling}",
        r"\small",
        r"\setlength{\tabcolsep}{5pt}",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}l"
        + "r" * len(COLUMNS) + r"@{}}",
        r"\toprule",
        "Arm & " + head + r" \\",
    ]
    for band, rows, _ns in group_bands(by_n):
        out.append(r"\midrule")
        # THE DENSITY QUALIFIER STAYS, AND NOW USUALLY VANISHES. A band that
        # pools the sparse and the dense stage of its node counts covers every
        # ratio the benchmark defines, so the qualifier is empty and the head
        # is just the band; it reappears only where a band genuinely holds a
        # narrower set of densities than the benchmark.
        out.append(band_heading(len(COLUMNS) + 1, band, rows))
        for arm in arms:
            got = cells(rows, arm, coeff)
            _mine, sched = arm_rows(rows, arm)
            body = " & ".join(got) if got else " & ".join(["--"] * len(COLUMNS))
            mark = r"$^{\ddagger}$" if (got and sched != SCHEDULER) else ""
            if mark:
                off_scheduler.add((arm, sched))
            out.append(_arm(arm) + mark + " & " + body + r" \\")
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        (
            r"$^{\ddagger}$ Measured under the asynchronous scheduler only. "
            if off_scheduler
            else ""
        )
        + r"The Wu-Li row is the lightest of the three variants, with any "
        r"within a tenth of a per cent of it counted as tied and the exact "
        r"variant preferred among those, and a dash marks an arm that sweep "
        r"did not run, while an empty slot "
        r"count marks the asynchronous scheduler, which has no round structure "
        r"to count. Radio is the traffic term of the simulator's radio energy "
        r"model, recomputed from the recorded bytes sent, deliveries and "
        r"retransmissions with its declared per-byte and per-frame "
        r"coefficients "
        r"($" + _sci(coeff.tx_cost_mJ_per_byte) + r"$ mJ per byte sent, "
        r"$" + _sci(coeff.rx_cost_mJ_per_delivery) + r"$ mJ per delivery, "
        r"$" + _sci(coeff.retx_cost_mJ) + r"$ mJ per retransmission). "
        r"It is a model estimate under declared coefficients and not a "
        r"measurement, and it is not the ESP32 model, whose listening term "
        r"needs a radio-on time the simulator does not record.",
        r"\end{flushleft}",
        r"\end{table*}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 2. reliability, the pipeline's own table with a one-sentence caption
# --------------------------------------------------------------------------
#: The densities the Dagdeviren benchmark actually contains.
DATASET_RATIOS = (2, 4, 6, 8, 10)


def density_qualifier(rows: Sequence[dict]) -> str:
    """How a column's densities differ from the whole benchmark, in one phrase.

    WHY A COLUMN HEAD NEEDS THIS. Node count alone stopped identifying a column
    once the sweep was split by density: `large` holds n = 150 and 200 at
    m/n <= 6 and `largedense` holds the SAME node counts at m/n >= 8, so both
    columns came out headed "n = 150, 200" and a reader had no way to tell
    which was which, or that one of them contains no solvable instance at all.
    The phrase is derived from the rows rather than written into a table of
    names, so a column cannot end up labelled with a density it does not hold.
    """
    got = sorted({int(r["ratio"]) for r in rows
                  if (r.get("ratio") or "").lstrip("-").isdigit()})
    if not got or tuple(got) == DATASET_RATIOS:
        return ""
    if len(got) == 1:
        return f"$m/n = {got[0]}$"
    if got[0] == DATASET_RATIOS[0]:
        return f"$m/n \\le {got[-1]}$"
    if got[-1] == DATASET_RATIOS[-1]:
        return f"$m/n \\ge {got[0]}$"
    return f"$m/n$ {got[0]} to {got[-1]}"


def table_reliability(scales=SCALES) -> Optional[str]:
    """One column per node-count band, pooled across the stages that measured it.

    A COLUMN USED TO BE A SWEEP DIRECTORY AND THAT MADE THE TABLE'S SHAPE AN
    ACCIDENT OF HOW THE RUN WAS STAGED. Splitting one node count across a sparse
    and a dense stage added a column headed with the same node counts as its
    neighbour, and a stage added later would add another; worse, the column
    order then followed the order the directories were passed. Bands fix the
    shape: the same four columns whatever the sweep was cut into.

    THE DENSE STAGES CANNOT MOVE A BAND'S NUMBERS. Every instance they hold has
    m > nk at k = 6, so no cover exists and the feasibility rule drops all of
    them before the common valid subset is taken. Pooling them in is therefore
    safe, and what they contribute is the denominator's honesty, not an average.
    """
    pooled: List[dict] = []
    seen_instances: set = set()
    for _label, path in scales:
        csv_path = os.path.join(path, "rows.csv")
        if not os.path.exists(csv_path):
            continue
        rows = report_pipeline.load_rows(csv_path)
        report_pipeline.check_single_version(rows, path)
        # AN INSTANCE MEASURED TWICE IS STILL ONE INSTANCE. Two stages can hold
        # the same instance, and counting it once per stage would inflate the
        # denominator and let one arm's answer be required twice over.
        for r in rows:
            key = (r["instance"], r.get("variant"), r.get("scheduler"))
            if key in seen_instances:
                continue
            seen_instances.add(key)
            pooled.append(r)

    collected = []
    dense_dropped = False
    for band in SCALE_RANGES:
        rows = [r for r in pooled
                if (r.get("n") or "").isdigit() and band[0] <= int(r["n"]) <= band[1]]
        if not rows:
            continue
        common, prov = report_pipeline.common_subset(rows)
        if prov["instances_infeasible"]:
            dense_dropped = True
        head = band[2]
        dens = density_qualifier(rows)
        if dens:
            head = f"{head}, {dens}"
        collected.append((head, report_pipeline.arm_stats(rows, common), prov))
    if not collected:
        return None
    tex = report_pipeline.table_reliability(collected)
    # ONE SENTENCE. The pipeline's caption explains why reliability is reported
    # apart from quality, and the manuscript says that in the body instead.
    start = tex.index(r"\caption{")
    stop = tex.index(r"\label{")
    tex = (
        tex[:start] + "\\caption{Share of feasible instances each arm terminated on "
        "and passed the validator, at every scale.}\n" + tex[stop:]
    )
    # THE HOUSE FLOAT RULE, APPLIED HERE RATHER THAN BY HAND, EXCEPT THAT THIS
    # TABLE NO LONGER FITS ONE COLUMN. Measured: with five scale columns and
    # the density qualifiers in their heads the tabular set 463 pt wide against
    # a 252 pt column, 211 pt over, and no padding change or stacked head
    # closes a gap that large. It therefore goes full width at the top of a
    # page like the other wide tables. While it still fits a column it keeps
    # the single-column form the house rule asks for.
    wide = len(collected) > 3
    if wide:
        tex = tex.replace(r"\begin{table}[tb]", r"\begin{table*}[!t]", 1)
        tex = tex.replace(r"\end{table}", r"\end{table*}", 1)
    else:
        tex = tex.replace(r"\begin{table}[tb]", r"\begin{table}[!b]", 1)
    # FULL MEASURE, NOT NATURAL WIDTH. Four band columns of short shares set
    # this tabular about half the text block wide and the float then reads as
    # a half-page table with a caption running past it on both sides. tabular*
    # with a filling intercolumn glue pins the rules to the measure the float
    # actually occupies, \textwidth when the table is wide and \columnwidth
    # when it still fits a column.
    measure = r"\textwidth" if wide else r"\columnwidth"
    tex = tex.replace(r"\begin{tabular}{l", "\\small\n"
                      r"\setlength{\tabcolsep}{4pt}" "\n"
                      r"\begin{tabular*}{" + measure
                      + r"}{@{\extracolsep{\fill}}l", 1)
    tex = tex.replace(r"rrr}" + "\n" + r"\toprule",
                      r"rrr@{}}" + "\n" + r"\toprule", 1)
    tex = tex.replace(r"\end{tabular}", r"\end{tabular*}", 1)
    a = tex.index(r"\begin{flushleft}")
    b = tex.index(r"\end{flushleft}")
    note = (
        "Italic marks a share below 100\\%, and capacity-infeasible instances "
        "are excluded from the denominator."
    )
    if dense_dropped:
        note += (
            " The $m/n \\ge 8$ cells admit no cover at $k = 6$, since a cover "
            "would have to own more edges than $nk$, so they are counted as "
            "infeasible and contribute to no arm's share."
        )
    return (
        tex[:a] + "\\begin{flushleft}\\footnotesize\n" + note + "\n" + tex[b:]
    )


# --------------------------------------------------------------------------
# 3. the wireless table, one table instead of three
# --------------------------------------------------------------------------
def wireless_runs(indir: str) -> Dict[Tuple[str, str], List[dict]]:
    """Run documents grouped by (family, node kind), read from the archive."""
    out: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for summ_path in sorted(glob.glob(os.path.join(indir, "*", "summary.json"))):
        rundir = os.path.dirname(summ_path)
        stem = os.path.basename(rundir)
        parts = stem.split("_")
        if len(parts) < 4 or not (parts[-1][:1] == "s" and parts[-1][1:].isdigit()):
            continue
        doc = json.load(open(summ_path, encoding="utf-8"))
        run_path = os.path.join(rundir, "run.json")
        doc["_run"] = (
            json.load(open(run_path, encoding="utf-8"))
            if os.path.exists(run_path)
            else {}
        )
        out[("_".join(parts[2:-1]), parts[1])].append(doc)
    return out


def table_wireless(indir: str) -> Optional[str]:
    groups = wireless_runs(indir)
    if not groups:
        return None
    fams = [f for f in WIFI_ORDER if any(k[0] == f for k in groups)]
    fams += sorted({k[0] for k in groups} - set(fams))

    out = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\caption{Every archived Mininet-WiFi run, by scale and arm, with "
        r"each cover judged against the graph the stations discovered.}",
        r"\label{tab:wireless}",
        r"\small",
        r"\setlength{\tabcolsep}{5pt}",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrrrrr@{}}",
        r"\toprule",
        r"$n$ / $m$ / $k$ & Arm & Valid & Weight & $|C|$ & Slots & Messages & "
        r"Payload & mAh \\",
    ]
    footmarks = []
    for fam in fams:
        first = True
        for kind, shown in WIFI_ARMS:
            docs = groups.get((fam, kind), [])
            if not docs:
                continue
            run = docs[0].get("_run", {})
            # THE SCALE IS THREE NUMBERS, NOT THREE EQUATIONS. Spelled out as
            # "$n = 20$, $m = 160$, $k = 12$" this column alone ran the table
            # 64 pt past the text block.
            scale = (f"{run.get('n', '?')} / {run.get('m', '?')} / "
                     f"{run.get('k', '?')}")
            if first:
                out.append(r"\midrule")
            valid = sum(
                1
                for d in docs
                if (d.get("validation_vs_discovered") or d["validation"])["valid"]
            )
            weight = _mean([d["cover_weight"] for d in docs])
            csize = _mean([float(len(d.get("cover") or [])) for d in docs])
            slots = [d["slots"] for d in docs if d.get("slots") is not None]
            tx = _mean([d["totals"]["tx"] for d in docs])
            payload = max(d["totals"]["max_payload"] for d in docs)
            # NO DELIVERY COLUMN. `Counters.record_tx` writes `rx += fanout`
            # at the SENDER, so `totals.rx` is what the sender expected the
            # broadcast to reach, and `rx_delivered_total` matching it is an
            # identity rather than a measurement. Printing it as 100 per cent
            # would also contradict the measured HELLO delivery the findings
            # log derives from sequence gaps, 0.971 median over 6108 pairs.
            energy = _mean(
                [
                    d["totals"]["energy_mah_esp32_model"]
                    for d in docs
                    if d["totals"].get("energy_mah_esp32_model") is not None
                ]
            )
            slot_cell = _num(_mean([float(s) for s in slots]), 0)
            if len(slots) < len(docs):
                slot_cell += r"$^{\dagger}$"
                footmarks.append(f"{armnames.display(shown)} at {fam}")
            out.append(
                (scale if first else "")
                + " & "
                + _arm(shown)
                + " & "
                + f"{valid}/{len(docs)}"
                + " & "
                + _num(weight, 0)
                + " & "
                + _num(csize, 1)
                + " & "
                + slot_cell
                + " & "
                + _num(tx, 0)
                + " & "
                + str(payload)
                + " & "
                + _num(energy, 2)
                + r" \\"
            )
            first = False
    note = (
        r"Payload is the largest single payload in bytes and mAh is an ESP32 "
        r"model estimate, not a measurement."
    )
    if footmarks:
        note += (
            r" $^{\dagger}$ One run did not report a slot count and is "
            r"excluded from that mean."
        )
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        note,
        r"\end{flushleft}",
        r"\end{table*}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 4. where the traffic goes: HELLO against the protocol's own messages
# --------------------------------------------------------------------------
#: The three scales the manuscript reads, each pooling the node counts that one
#: sweep owns. `gather` has already decided which sweep owns which node count,
#: so pooling here re-forms exactly that sweep's common valid subset and never
#: mixes two instance sets.
SCALE_GROUPS: Tuple[Tuple[str, Tuple[int, ...]], ...] = (
    (r"Small, $n = 10$ to $25$", (10, 15, 20, 25)),
    (r"$n = 50$", (50,)),
    (r"$n = 100$", (100,)),
)

SCHEDULERS = ("sync", "async")


def split_cells(rows: Sequence[dict], arm: str, sched: str) -> Optional[List[str]]:
    """HELLO, algorithm, HELLO share and rx for one arm under one scheduler.

    A SINGLE `tx` TOTAL CONFOUNDS TWO THINGS. HELLO grows with the node count
    times the number of rounds a run lasts, so a slow arm looks talkative even
    when its own protocol is quiet, while the algorithm traffic is the price of
    the design. Subtracting the one from the other is the whole point of this
    table, and both terms are columns the sweep already wrote.
    """
    mine = [r for r in rows if r["variant"] == arm and r["scheduler"] == sched]
    if not mine:
        return None
    hello = _mean([v for v in (_f(r, "hello_tx") for r in mine) if v is not None])
    total = _mean([v for v in (_f(r, "tx") for r in mine) if v is not None])
    rx = _mean([v for v in (_f(r, "rx") for r in mine) if v is not None])
    if hello is None or total is None or not total:
        return None
    return [
        _num(hello, 0),
        _num(total - hello, 0),
        _num(100.0 * hello / total, 1),
        _num(rx, 0),
    ]


def table_msgsplit(by_n: Dict[int, List[dict]], wuli: str) -> str:
    arms = list(NAMED_ARMS) + [wuli]
    ncol = 1 + 4 * len(SCHEDULERS)
    out = [
        r"\begin{table*}[!t]",
        r"\centering",
        # THE SCOPE IS NAMED BECAUSE IT IS NARROWER THAN THE EVIDENCE. The
        # scale groups below are a fixed three and stop at n = 100, while the
        # sweeps now reach n = 1000, so "at every scale" and "the same common
        # valid subsets as" the scaling table both became false the moment the
        # larger stages landed. The groups are deliberately not derived from
        # the data here: the HELLO against algorithm argument is carried in
        # full at these scales, and a second float would cost a page slot the
        # section does not have.
        r"\caption{Message traffic split into HELLO frames and the arm's own "
        r"algorithm frames at the scales up to $n = 100$, on the common valid "
        r"subsets those scales contribute to Table~\ref{tab:scaling}.}",
        r"\label{tab:msgsplit}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{5pt}",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}l"
        + "rrrr" * len(SCHEDULERS) + r"@{}}",
        r"\toprule",
        r"& \multicolumn{4}{c}{Synchronous} & "
        r"\multicolumn{4}{c}{Asynchronous} \\",
        r"\cmidrule(lr){2-5}\cmidrule(l){6-9}",
        r"Arm & HELLO & Algorithm & HELLO \% & rx & HELLO & Algorithm & "
        r"HELLO \% & rx \\",
    ]
    for label, ns in SCALE_GROUPS:
        rows = [r for n in ns if n in by_n for r in by_n[n]]
        if not rows:
            continue
        inst = len({r["instance"] for r in rows})
        out.append(r"\midrule")
        out.append(
            r"\multicolumn{" + str(ncol) + r"}{@{}l}{\textit{" + label
            + ", " + str(inst) + r" instances}} \\"
        )
        for arm in arms:
            cells_out: List[str] = []
            for sched in SCHEDULERS:
                got = split_cells(rows, arm, sched)
                cells_out += got if got else ["--"] * 4
            out.append(_arm(arm) + " & " + " & ".join(cells_out) + r" \\")
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        r"HELLO \% is the HELLO mean over the mean total sent, rx is counted "
        r"at the sender as the fanout of each broadcast, and a dash marks a "
        r"scheduler that sweep did not run for that arm.",
        r"\end{flushleft}",
        r"\end{table*}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 5. the approximation ratio read node count by node count
# --------------------------------------------------------------------------
#: The node counts the small sweep carries. A column is written only where an
#: exact optimum exists for every instance in it.
RATIO_NS: Tuple[int, ...] = (10, 15, 20, 25)


def ratio_cells(rows: Sequence[dict], arm: str) -> Tuple[Optional[float], str]:
    """Mean weight over the exact optimum, and the scheduler it was measured under."""
    mine, sched = arm_rows(rows, arm)
    vals = []
    for r in mine:
        e, w = _f(r, "exact_weight"), _f(r, "total_weight")
        if e and w:
            vals.append(w / e)
    return _mean(vals), sched


def table_ratio_by_n(by_n: Dict[int, List[dict]], wuli: str) -> Optional[str]:
    """Quality against the exact optimum, one column per node count.

    THE EXACT SOLVER DOES NOT RUN ON EVERY COLUMN. It is skipped above
    eighteen nodes, so the small sweep carries an optimum at n = 10 and n = 15
    and none at n = 20 or n = 25. A column of dashes would suggest the arms
    failed there, so a node count without a reference is left out of the table
    and the note says why.
    """
    arms = list(NAMED_ARMS) + [wuli]
    cols = []
    for n in RATIO_NS:
        if n not in by_n:
            continue
        vals = {a: ratio_cells(by_n[n], a) for a in arms}
        if any(v is not None for v, _ in vals.values()):
            cols.append((n, len({r["instance"] for r in by_n[n]}), vals))
    if not cols:
        return None

    off_scheduler = False
    best = {n: min((v for v, _ in vals.values() if v is not None), default=None)
            for n, _inst, vals in cols}
    out = [
        r"\begin{table}[!b]",
        r"\centering",
        r"\caption{Mean solution weight over the exact optimum at each node "
        r"count of the small group for which an exact optimum was computed, synchronous scheduler.}",
        r"\label{tab:ration}",
        r"\small",
        r"\setlength{\tabcolsep}{5pt}",
        r"\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}l"
        + "r" * len(cols) + r"@{}}",
        r"\toprule",
        "Arm & "
        + " & ".join(rf"$n = {n}$" for n, _inst, _v in cols)
        + r" \\",
        "& "
        + " & ".join(f"{inst} inst." for _n, inst, _v in cols)
        + r" \\",
        r"\midrule",
    ]
    for arm in arms:
        cells_out = []
        mark = ""
        for n, _inst, vals in cols:
            value, sched = vals[arm]
            if value is None:
                cells_out.append("--")
                continue
            if sched != SCHEDULER:
                mark = r"$^{\ddagger}$"
                off_scheduler = True
            txt = f"{value:.3f}"
            if best[n] is not None and abs(value - best[n]) < 5e-4:
                txt = r"\textbf{" + txt + "}"
            cells_out.append(txt)
        out.append(_arm(arm) + mark + " & " + " & ".join(cells_out) + r" \\")
    note = (
        r"Bold marks the lightest arm in a column, and the exact solver was "
        r"not run above eighteen nodes, so the larger node counts of the same "
        r"sweep carry no optimum to divide by."
    )
    if off_scheduler:
        note = (
            r"$^{\ddagger}$ Measured under the asynchronous scheduler only. "
            + note
        )
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        note,
        r"\end{flushleft}",
        r"\end{table}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# the node counts on their own, beside the bands
# --------------------------------------------------------------------------
#: Every node count the benchmark defines, in order. The bands answer "how does
#: this scale", and they answer it better than twelve blocks did; this table
#: answers the different question of what happens AT a given size, which a band
#: cannot because it averages several sizes into one row.
BY_N_ORDER: Tuple[int, ...] = (10, 15, 20, 25, 50, 100, 150, 200, 250, 500, 750, 1000)


def table_scaling_by_n(by_n: Dict[int, List[dict]], wuli: str) -> Optional[str]:
    """Weight against the lightest arm, and messages sent, node count by node count.

    WEIGHT IS RELATIVE AND MESSAGES ARE ABSOLUTE, ON PURPOSE. Solution weight
    has no meaning across node counts, since a hundred-node cover weighs more
    than a ten-node one whatever the arm did, so the only comparison a reader
    can make down a weight column is against the other arms at that same size,
    and the column is normalised to the lightest of them. Messages are left
    absolute because their growth with the node count IS the result.
    """
    arms = list(NAMED_ARMS) + [wuli]
    present = [n for n in BY_N_ORDER if n in by_n]
    if not present:
        return None

    off = {}
    heads, subs = [], []
    for arm in arms:
        sched = SCHEDULER
        for n in present:
            _mine, got = arm_rows(by_n[n], arm)
            if _mine:
                sched = got
                break
        mark = r"$^{\ddagger}$" if sched != SCHEDULER else ""
        if mark:
            off[arm] = sched
        heads.append(r"\multicolumn{2}{c}{" + _short(arm) + mark + "}")
        subs += [r"$w/w^{*}$", "tx"]

    rules = []
    for i in range(len(arms)):
        lo = 3 + 2 * i
        rules.append(r"\cmidrule(" + ("l" if i == len(arms) - 1 else "lr")
                     + "){" + f"{lo}-{lo + 1}" + "}")

    out = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\caption{Solution weight relative to the lightest arm at the same "
        r"node count and mean messages sent, read node count by node count "
        r"rather than by band, synchronous scheduler.}",
        r"\label{tab:scalingn}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}rr"
        + "rr" * len(arms) + r"@{}}",
        r"\toprule",
        r"$n$ & Inst. & " + " & ".join(heads) + r" \\",
        "".join(rules),
        r" &  & " + " & ".join(subs) + r" \\",
        r"\midrule",
    ]
    for n in present:
        rows = by_n[n]
        inst = len({r["instance"] for r in rows})
        weights, txs = {}, {}
        for arm in arms:
            mine, _sched = arm_rows(rows, arm)
            weights[arm] = _mean(_col(mine, "total_weight")) if mine else None
            txs[arm] = _mean(_col(mine, "tx")) if mine else None
        got = [w for w in weights.values() if w]
        best = min(got) if got else None
        cells_out = []
        for arm in arms:
            w, t = weights[arm], txs[arm]
            if w is None or not best:
                cells_out += ["--", "--"]
                continue
            rel = w / best
            txt = f"{rel:.3f}"
            # BOLD THE LIGHTEST, so the column that is normalised to one arm
            # says which arm that was rather than leaving the reader to hunt
            # for the 1.000.
            if abs(rel - 1.0) < 5e-4:
                txt = r"\textbf{" + txt + "}"
            cells_out += [txt, _num(t, 0)]
        out.append(f"{n} & {inst} & " + " & ".join(cells_out) + r" \\")

    note = (
        r"Weight is divided by the lightest arm's mean weight at that node "
        r"count, so a column compares arms at one size and never one size "
        r"against another, bold marks that lightest arm, and tx is the mean "
        r"number of messages sent."
    )
    if off:
        note = (r"$^{\ddagger}$ Measured under the asynchronous scheduler only. "
                + note)
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        note,
        r"\end{flushleft}",
        r"\end{table*}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 6. the distributed-systems cost columns a protocol paper is asked for
# --------------------------------------------------------------------------
#: Short arm names for the two single-column tables. The full spelling of
#: `MIS-Connector-Backbone` is 22 characters and alone runs a 252 pt column
#: past the text block, so the suffix that every constructive arm shares is
#: dropped and the part that distinguishes the arms is kept.
SHORT = {
    "GHS-MST-Backbone": "FabricTree",
    "MIS-Connector-Backbone": "NexusWarp",
    "Anneal-Local": "TemperFlux",
    "Anneal-Trickle": "TemperFlux-Tk",
    "DFS-Spanning-Backbone": "TokenTrail",
    "WuLi-Dominating-Exact": "Wu-Li CDS",
    "WuLi-Dominating-Bloom": "Wu-Li CDS/B",
    "WuLi-Dominating-Chunked": "Wu-Li CDS/C",
}


def _short(arm: str) -> str:
    return _tex(SHORT.get(arm) or armnames.display(arm))


def _ratio(rows: Sequence[dict], num: str, den: str) -> Optional[float]:
    """Mean of a PER-ROW ratio, never a ratio of two means.

    Bytes per node and the cover over its lower bound both divide by a quantity
    that changes from instance to instance, and a sweep group holds several
    node counts at once. Dividing the group's mean sent bytes by the group's
    mean node count would weight the instances by their own denominator and
    report a number no single run ever produced.
    """
    vals = []
    for r in rows:
        a, b = _f(r, num), _f(r, den)
        if a is not None and b:
            vals.append(a / b)
    return _mean(vals)


def _col(rows: Sequence[dict], key: str) -> List[float]:
    return [v for v in (_f(r, key) for r in rows) if v is not None]


#: (column head, how to read it, decimal places). Everything is a mean over the
#: arm's rows except the round maximum and the payload, which are maxima: the
#: node whose battery empties first is not the average node, and a payload that
#: fits on average still overflows the frame that did not.
DIST_COLUMNS: Tuple[Tuple[str, str, int], ...] = (
    ("Mean", "slots_mean", 1),
    ("Max", "slots_max", 0),
    ("Msg/node", "tx_per_n", 1),
    ("Bytes/node", "bytes_per_n", 0),
    ("Retx", "retx", 1),
    ("Payload (B)", "payload_max", 0),
    (r"$t_{\mathrm{conv}}$ (ms)", "t_conv_ms", 0),
    # See COLUMNS: wall-clock seconds are not comparable across passes and
    # t_conv_ms already carries the timing argument in simulated units.
)


def dist_cells(rows: Sequence[dict], arm: str) -> Optional[List[str]]:
    mine, _sched = arm_rows(rows, arm)
    if not mine:
        return None
    out = []
    for _head, key, places in DIST_COLUMNS:
        if key == "slots_mean":
            value = _mean(_col(mine, "slots"))
        elif key == "slots_max":
            got = _col(mine, "slots")
            value = max(got) if got else None
        elif key == "payload_max":
            got = _col(mine, "max_payload")
            value = max(got) if got else None
        elif key == "tx_per_n":
            value = _ratio(mine, "tx", "n")
        elif key == "bytes_per_n":
            value = _ratio(mine, "bytes_tx", "n")
        else:
            value = _mean(_col(mine, key))
        out.append(_num(value, places))
    return out


def table_distmetrics(by_n: Dict[int, List[dict]], wuli: str) -> str:
    """Rounds, per-node traffic and time, the cost columns read per node.

    WHY PER NODE AND NOT PER RUN. A total sent count grows with the node count
    for a reason that has nothing to do with the protocol, so comparing 100
    nodes against 10 on totals measures the sweep design. Dividing by the node
    count is what the deployment question actually asks, namely what one
    station has to send, and it is the quantity a battery budget is written in.
    """
    arms = list(NAMED_ARMS) + [wuli]
    head = " & ".join(h for h, _, _ in DIST_COLUMNS)
    off_scheduler = set()
    empty_rounds = False
    out = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\caption{Round count, per-node message and byte load, retransmissions, "
        r"largest payload and convergence time for every arm at every scale "
        r"under the synchronous scheduler.}",
        r"\label{tab:distmetrics}",
        r"\small",
        r"\setlength{\tabcolsep}{5pt}",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}l"
        + "r" * len(DIST_COLUMNS) + r"@{}}",
        r"\toprule",
        r"& \multicolumn{2}{c}{Rounds} & \multicolumn{2}{c}{Per node} & "
        r"\multicolumn{" + str(len(DIST_COLUMNS) - 4) + r"}{c}{Cost} \\",
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(l){6-" + str(len(DIST_COLUMNS) + 1) + r"}",
        "Arm & " + head + r" \\",
    ]
    for band, rows, _ns in group_bands(by_n):
        out.append(r"\midrule")
        out.append(band_heading(len(DIST_COLUMNS) + 1, band, rows))
        for arm in arms:
            got = dist_cells(rows, arm)
            _mine, sched = arm_rows(rows, arm)
            mark = r"$^{\ddagger}$" if (got and sched != SCHEDULER) else ""
            if mark:
                off_scheduler.add((arm, sched))
            body = " & ".join(got) if got else " & ".join(["--"] * len(DIST_COLUMNS))
            if got and got[0] == "--":
                empty_rounds = True
            out.append(_arm(arm) + mark + " & " + body + r" \\")
    note = (
        r"Rounds, per-node load, retransmissions and time are means over the "
        r"instances every arm answered cleanly, while the round maximum and "
        r"the payload are maxima over the same rows, because the first station "
        r"to run out of budget is not the average one."
    )
    if empty_rounds:
        note += (
            r" An empty round pair marks the asynchronous scheduler, which has "
            r"no global round to count, and the convergence time carries the "
            r"comparison there."
        )
    if off_scheduler:
        note = r"$^{\ddagger}$ Measured under the asynchronous scheduler only. " + note
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        note,
        r"\end{flushleft}",
        r"\end{table*}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 7. how the work is spread: ownership load, backbone share, lower bound
# --------------------------------------------------------------------------
def load_cells(rows: Sequence[dict], arm: str) -> Optional[List[str]]:
    """Ownership load against the budget, backbone share, cover over its bound.

    THE BACKBONE COLUMNS ARE EMPTY FOR THE ANNEALING ARMS AND THAT IS A RESULT.
    Those arms reach connectivity through the energy term rather than by
    electing a backbone, so they write no backbone size or weight at all;
    filling the cell with the cover itself would invent a structure the arm
    does not build, and filling it with zero would read as a backbone of no
    nodes.
    """
    mine, _sched = arm_rows(rows, arm)
    if not mine:
        return None
    ks = _col(mine, "k")
    bb_size = _mean(_col(mine, "backbone_size"))
    share = _ratio(mine, "backbone_weight", "total_weight")
    return [
        _num(_mean(_col(mine, "owner_load_max")), 1),
        _num(_mean(_col(mine, "owner_load_mean")), 2),
        _num(_mean(ks), 0) if ks else "--",
        _num(bb_size, 1),
        "--" if share is None else _num(100.0 * share, 1),
        _num(_ratio(mine, "cover_size", "lower_bound_g6"), 2),
    ]


LOAD_HEADS = (
    r"$\ell_{\max}$",
    r"$\bar{\ell}$",
    "$k$",
    "$|B|$",
    r"$B$ wt.\%",
    r"$|C|/\lceil m/k\rceil$",
)


def table_loadbalance(by_n: Dict[int, List[dict]], wuli: str) -> str:
    arms = list(NAMED_ARMS) + [wuli]
    ncol = len(LOAD_HEADS) + 1
    no_backbone = set()
    off_scheduler = set()
    out = [
        r"\begin{table}[!b]",
        r"\centering",
        r"\caption{Ownership load against the shared capacity, backbone size "
        r"and weight share of the cover, and cover size over its counting "
        r"lower bound, per arm and scale.}",
        r"\label{tab:loadbal}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}l"
        + "r" * len(LOAD_HEADS) + r"@{}}",
        r"\toprule",
        "Arm & " + " & ".join(LOAD_HEADS) + r" \\",
    ]
    for band, rows, _ns in group_bands(by_n):
        out.append(r"\midrule")
        out.append(band_heading(ncol, band, rows))
        for arm in arms:
            got = load_cells(rows, arm)
            _mine, sched = arm_rows(rows, arm)
            mark = r"$^{\ddagger}$" if (got and sched != SCHEDULER) else ""
            if mark:
                off_scheduler.add((arm, sched))
            if got and got[3] == "--":
                no_backbone.add(arm)
            body = " & ".join(got) if got else " & ".join(["--"] * len(LOAD_HEADS))
            out.append(_short(arm) + mark + " & " + body + r" \\")
    note = (
        r"$\ell_{\max}$ and $\bar{\ell}$ are the largest and the mean number "
        r"of edges one station owns, $k$ is the shared capacity every station "
        r"obeys, $B$ is the backbone and its share is backbone weight over "
        r"cover weight, and the last column reads the cover against the "
        r"$\lceil m/k\rceil$ bound of Prop.~\ref{prop:lb}, which no valid cover "
        r"can undercut."
    )
    if no_backbone:
        note += (
            r" The annealing arms leave the backbone columns empty because "
            r"they reach connectivity through the energy term instead of "
            r"electing a backbone, so no backbone is recorded."
        )
    if off_scheduler:
        note = r"$^{\ddagger}$ Measured under the asynchronous scheduler only. " + note
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        note,
        r"\end{flushleft}",
        r"\end{table}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 8. the analytical bounds beside the measurement that tests them
# --------------------------------------------------------------------------
#: Per arm: the backbone phase's own message bound, its time bound, its memory
#: bound, and where each is stated. EVERY ENTRY IS QUOTED, NOT DERIVED HERE.
#: The shared envelope is Thm.~\ref{thm:msg} and applies to every arm because
#: the arms differ in one decision and share all the remaining code; what the
#: per-arm rows add is the cost of that one decision, taken from the paper
#: where the paper states it and from the cited source where it does not.
ENVELOPE = (
    r"$nS + 2(XD{+}\rho)$",
    # NO "$S=$" PREFIX AND A TIGHT diam. Spelled out, this single entry ran
    # the tabular 20.9 pt past the 252 pt column, and the quantity column
    # already says which symbol the row is bounding.
    r"$\bigO(L{+}R_c{+}XD{+}\mathrm{diam}B{+}T_q)$",
    r"$\bigO(\Delta\log n)$ bits",
    r"Thm.~\ref{thm:msg}",
)

COMPLEXITY: Tuple[Tuple[str, str, str, str, str], ...] = (
    (
        "GHS-MST-Backbone",
        r"$\bigO(m + n\log n)$",
        r"$\bigO(n\log n)$",
        r"$\bigO(\Delta\log n)$ bits",
        r"\cite{ghs1983}",
    ),
    (
        "MIS-Connector-Backbone",
        r"$\le 2|\mathrm{MIS}|$ unicast",
        r"$\Theta(L)$, $L=\bigO(\log^2 n)$",
        r"$\bigO(\Delta\log n)$ bits",
        r"Prop.~\ref{prop:mischain}",
    ),
    (
        "Anneal-Local",
        r"none claimed",
        r"none claimed",
        r"$\bigO(\Delta\log n)$ bits",
        r"Prop.~\ref{prop:anneal}",
    ),
    (
        "Anneal-Trickle",
        r"none claimed",
        r"none claimed",
        r"$\bigO(\Delta\log n)$ bits",
        r"Prop.~\ref{prop:anneal}",
    ),
    (
        "DFS-Spanning-Backbone",
        r"$\bigO(m)$",
        r"$\bigO(n)$",
        r"$\bigO(\Delta\log n)$ bits",
        r"\cite{awerbuch1985}",
    ),
    (
        "WuLi-Dominating-Exact",
        r"$\bigO(n)$ broadcast",
        r"$\bigO(1)$ rounds",
        r"$\bigO(\Delta^2\log n)$ bits",
        r"\cite{wuli1999}",
    ),
    (
        "WuLi-Dominating-Bloom",
        r"$\bigO(n)$ broadcast",
        r"$\bigO(1)$ rounds",
        r"$\bigO(\Delta^2\log n)$ bits",
        r"\cite{wuli1999}",
    ),
    (
        "WuLi-Dominating-Chunked",
        r"$\bigO(n)$ broadcast",
        r"$\bigO(1)$ rounds",
        r"$\bigO(\Delta^2\log n)$ bits",
        r"\cite{wuli1999}",
    ),
)


def measured_at(by_n: Dict[int, List[dict]], arm: str, prefer: int = 100):
    """The arm's rows at the largest node count it was actually run at.

    THE PREFERRED SCALE IS NOT ALWAYS AVAILABLE AND THE TABLE MUST SAY SO. The
    annealing arms were not run in the $n=100$ sweep, so a row of dashes would
    read as a failure at that scale and a number borrowed from $n=50$ printed
    under an $n=100$ head would be false. The scale each cell came from is
    therefore returned with the cell and printed in its own column.
    """
    if prefer in by_n and arm_rows(by_n[prefer], arm)[0]:
        got = prefer
    else:
        have = [n for n in sorted(by_n) if arm_rows(by_n[n], arm)[0]]
        if not have:
            return None, None, SCHEDULER
        got = have[-1]
    mine, sched = arm_rows(by_n[got], arm)
    return mine, got, sched


def table_complexity(by_n: Dict[int, List[dict]], wuli: str) -> str:
    """Each arm's stated bound beside the measurement that is supposed to test it.

    THE TWO MESSAGE COLUMNS DO NOT COUNT THE SAME FRAMES AND THE TABLE SAYS SO.
    The shared envelope bounds everything the run sends, HELLO included, since
    a synchronous slot costs $n$ transmissions whatever the algorithm is doing.
    The per-arm bound is a bound on the backbone protocol's OWN messages, so
    the measurement beside it is the total minus the HELLO traffic; putting the
    total there instead would compare a periodic beacon against a bound that
    never claimed to cover it.
    """
    arms = list(NAMED_ARMS) + [wuli]
    rows_out: List[str] = []
    off_scheduler = False
    spec = {a: (m, t, mem, src) for a, m, t, mem, src in COMPLEXITY}

    def block(title: str, bound: Tuple[str, str, str, str],
              mine: Optional[Sequence[dict]], n: Optional[int], sched: str,
              own_messages: bool) -> None:
        nonlocal off_scheduler
        rows_out.append(r"\midrule")
        rows_out.append(r"\multicolumn{4}{@{}l}{\textit{" + title + r"}} \\")
        if mine:
            tx = _mean(_col(mine, "tx"))
            hello = _mean(_col(mine, "hello_tx"))
            msg = (tx - hello) if (own_messages and tx is not None
                                   and hello is not None) else tx
            slots = _mean(_col(mine, "slots"))
            scale = f"$n={n}$"
            if sched != SCHEDULER:
                scale += r"\,$^{\ddagger}$"
                off_scheduler = True
        else:
            msg = slots = None
            scale = "--"
        label = "Own messages" if own_messages else "Messages sent"
        rows_out.append(
            label + " & " + bound[0] + " & " + _num(msg, 0) + " & " + scale + r" \\"
        )
        rows_out.append(
            "Rounds & " + bound[1] + " & " + _num(slots, 0) + " & " + scale + r" \\"
        )
        # NO MEASURED MEMORY COLUMN CONTENT. The sweep records no per-node
        # memory, and the only figure this project has measured is the
        # emulator's resident set size for a whole Linux process, which is a
        # different quantity in a different unit and belongs to the platform
        # rather than to the arm.
        rows_out.append(
            "Memory & " + bound[2] + " & -- & " + bound[3] + r" \\"
        )

    # THE ENVELOPE IS MEASURED ON THE ARM ITS ACCOUNTING DESCRIBES. Teorem 5
    # adds to the synchronous broadcast base only the Phase 3 and Phase 4
    # unicasts, which is exactly the traffic of the MIS-Connector arm; an arm
    # that replaces the backbone phase sends its own frames on top of that,
    # and those are what the per-arm rows below count. Printing a backbone
    # arm's total beside the envelope would read as the envelope exceeded.
    ref_arm = "MIS-Connector-Backbone"
    mine, n, sched = measured_at(by_n, ref_arm)
    # PLAIN NAMES, NOT THE \BB{} AND \MIS{} MACROS. Every other block heading
    # here is a plain arm name, and the macros expand to small caps, which
    # inside the heading's \textit{} asks for a small-caps italic shape that
    # Times does not have; LaTeX warned and silently dropped the italic on
    # exactly those words. Spelling the two names out keeps the headings
    # consistent with one another and asks for a font that exists.
    block(f"{armnames.display('BB-CVC')} core envelope, "
          f"{armnames.display('MIS-Connector-Backbone')} arm",
          ENVELOPE, mine, n, sched, False)
    for arm in arms:
        bound = spec.get(arm)
        if bound is None:
            continue
        mine, n, sched = measured_at(by_n, arm)
        block(_short(arm) + " backbone", bound, mine, n, sched, True)

    note = (
        r"A bound is quoted from where it is stated and never derived here, "
        r"the envelope row bounds everything a run sends and is measured "
        r"against the total, an arm row bounds the backbone protocol's own "
        r"messages and is measured against the total minus HELLO and sits on "
        r"top of the core envelope rather than inside it, the round "
        r"column is the whole six-phase run and not the backbone phase alone "
        r"so it can only bound the phase from above, and memory carries no "
        r"measurement because the sweeps record no per-node memory."
    )
    if off_scheduler:
        note = r"$^{\ddagger}$ Measured under the asynchronous scheduler only. " + note
    out = [
        r"\begin{table}[!b]",
        r"\centering",
        r"\caption{Analytical message, time and memory bounds of each arm "
        r"beside the measurement that tests them, with the scale of every "
        r"measured cell named.}",
        r"\label{tab:complexity}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}llrl@{}}",
        r"\toprule",
        r"Quantity & Bound & Measured & Scale \\",
    ] + rows_out + [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        note,
        r"\end{flushleft}",
        r"\end{table}",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 9. the paired loss experiment, topology by topology
# --------------------------------------------------------------------------
#: The arms the loss replay covers, in the order the manuscript names them.
LOSS_ARMS = ("GHS-MST-Backbone", "MIS-Connector-Backbone", "Anneal-Local")
LOSS_SHORT = {
    "GHS-MST-Backbone": "FabricTree",
    "MIS-Connector-Backbone": "NexusWarp",
    "Anneal-Local": "TemperFlux",
}
CONDITIONS = ("lossless", "lossy")

#: Thin spaces, not interword ones: see the width note in `table_loss_topology`.
_ARROW = r"\,$\rightarrow$\,"


def _topology(graph: str) -> str:
    """The scale and seed part of a run directory name, shared by all arms.

    Each arm replayed the graph ITS OWN wireless run discovered, and those runs
    are named after the arm, so the arm prefix has to come off before the three
    can be put on one row. The edge sets behind the three names at one scale
    and seed are the same, which is what makes the row a paired comparison
    rather than three unrelated numbers.
    """
    parts = graph.split("_", 2)
    return parts[2] if len(parts) == 3 else graph


def load_loss_rows(path: str) -> List[dict]:
    import csv as _csv

    with open(path, newline="", encoding="utf-8") as fh:
        return list(_csv.DictReader(fh))


def table_loss_topology(path: str) -> Optional[str]:
    """Lossless against five per cent loss, on every discovered graph.

    NO MESSAGE COUNT HERE. The replay recorded the verdict, the validator's
    answer, the cover size, the weight and the slot count, and it did not
    record the frames offered to the radio, so a traffic column would have to
    be invented or the whole experiment re-run. Weight takes its place: it is
    measured, it is the quantity loss could plausibly spoil, and it says
    whether an arm paid for the retries in answer quality.
    """
    if not os.path.exists(path):
        return None
    rows = load_loss_rows(path)
    if not rows:
        return None
    topologies = sorted(
        {_topology(r["graph"]) for r in rows},
        key=lambda t: (int(t.split("_")[0][1:]), t),
    )

    def cell(arm: str, topo: Optional[str], cond: str) -> dict:
        sel = [
            r
            for r in rows
            if r["arm"] == arm
            and r["condition"] == cond
            and (topo is None or _topology(r["graph"]) == topo)
        ]
        return {
            "runs": len(sel),
            "valid": sum(int(r["valid"] or 0) for r in sel),
            "slots": _mean([float(r["slots"]) for r in sel if r["slots"]]),
            "weight": _mean([float(r["weight"]) for r in sel if r["weight"]]),
        }

    def body(arm: str, topo: Optional[str]) -> List[str]:
        a, b = (cell(arm, topo, c) for c in CONDITIONS)
        # A TIGHT ARROW AND NO SPACES ROUND THE SLASH. Measured against the
        # 516 pt text block, the roomy spelling set this tabular at 515.4 pt,
        # which is inside the block by six tenths of a point; one wider number
        # in a later sweep would push it out with nothing to absorb the change.
        return [
            f"{a['valid']}/{b['valid']}",
            _num(a["slots"], 1) + _ARROW + _num(b["slots"], 1),
            _num(a["weight"], 0) + _ARROW + _num(b["weight"], 0),
        ]

    ncol = 1 + 3 * len(LOSS_ARMS)
    heads = []
    rules = []
    for i, arm in enumerate(LOSS_ARMS):
        heads.append(r"\multicolumn{3}{c}{" + _tex(LOSS_SHORT[arm]) + "}")
        lo = 2 + 3 * i
        rules.append(
            r"\cmidrule(" + ("l" if i == len(LOSS_ARMS) - 1 else "lr") + "){"
            + f"{lo}-{lo + 2}" + "}"
        )
    out = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\caption{Paired lossless and lossy replays of every graph the "
        r"stations discovered, five seeds in each condition, with each arm "
        r"judged against that same graph.}",
        r"\label{tab:losstopo}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}l"
        + "rrr" * len(LOSS_ARMS) + r"@{}}",
        r"\toprule",
        "& " + " & ".join(heads) + r" \\",
        "".join(rules),
        r"$n$/$m$/seed & "
        + " & ".join(["Valid", "Slots", "Weight"] * len(LOSS_ARMS))
        + r" \\",
        r"\midrule",
    ]
    for topo in topologies:
        sample = next(r for r in rows if _topology(r["graph"]) == topo)
        seed = topo.rsplit("_s", 1)[-1]
        label = f"{sample['n']}/{sample['m']}/{seed}"
        cells_out: List[str] = []
        for arm in LOSS_ARMS:
            cells_out += body(arm, topo)
        out.append(label + " & " + " & ".join(cells_out) + r" \\")
    out.append(r"\midrule")
    totals: List[str] = []
    for arm in LOSS_ARMS:
        totals += body(arm, None)
    out.append(r"All nine & " + " & ".join(totals) + r" \\")
    out += [
        r"\bottomrule",
        r"\end{tabular*}",
        r"\begin{flushleft}\footnotesize",
        r"A valid cell counts the clean runs of five lossless and of five "
        r"lossy replays, an arrow reads lossless to lossy, loss is five per "
        r"cent, and the three arms replay the same discovered graph on every "
        r"row.",
        r"\end{flushleft}",
        r"\end{table*}",
        "",
    ]
    _ = ncol
    return "\n".join(out)


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# splitting a scale table that has outgrown the page
# --------------------------------------------------------------------------
#: How many scale blocks one float may carry. MEASURED, NOT GUESSED: with the
#: twelve scales of the full sweep, `scaling`, `distmetrics` and `loadbalance`
#: typeset 940 to 975 pt against a 696 pt text height, and LaTeX reported them
#: "Float too large for page" by 240 to 279 pt. A float it cannot place is not
#: merely late, it blocks the queue behind it, so every table referenced after
#: it is held back and the section ends up with its tables printed after the
#: bibliography. Six blocks measure about 495 pt including the caption and the
#: note, which leaves room on any page.
MAX_SCALE_BLOCKS = 6


def split_by_scale(tex: str, max_blocks: int = MAX_SCALE_BLOCKS) -> str:
    """One float per at most `max_blocks` scale blocks, or the table unchanged.

    THIS WORKS ON THE RENDERED TABLE RATHER THAN INSIDE THE THREE BUILDERS.
    Each builder lays its blocks out differently and all three are edited by
    other hands; parsing the one structure they genuinely share, a rule
    followed by a scale heading, keeps this correct when a builder's columns or
    captions change underneath it. Every row is carried over, nothing is
    dropped or rounded, and each part repeats the header and the note so it can
    be read on its own.
    """
    # ALREADY SPLIT IS LEFT ALONE. Run twice, this would treat the second
    # float's heading rows as more blocks of the first and emit several floats
    # carrying the SAME continuation label, which points every reference in the
    # manuscript at whichever one LaTeX wrote last. `main` calls this once, so
    # the guard is for the next caller rather than for today.
    if tex.count(r"\begin{table}") + tex.count(r"\begin{table*}") > 1:
        return tex
    lines = tex.split("\n")
    starts = [
        i for i in range(1, len(lines))
        if lines[i].startswith(r"\multicolumn")
        and r"\textit{$n = " in lines[i]
        and lines[i - 1] == r"\midrule"
    ]
    if len(starts) <= max_blocks:
        return tex
    try:
        stop = next(i for i, ln in enumerate(lines) if ln == r"\bottomrule")
    except StopIteration:
        return tex
    head = lines[: starts[0] - 1]
    tail = lines[stop:]
    bounds = [s - 1 for s in starts] + [stop]
    blocks = [lines[bounds[i]:bounds[i + 1]] for i in range(len(starts))]

    def caption_of(block: Sequence[str]) -> int:
        return next(i for i, ln in enumerate(block) if ln.startswith(r"\caption{"))

    # BALANCED PARTS, NOT A FULL FLOAT AND A REMAINDER. Thirteen blocks cut
    # every six leave a float carrying one block, which spends a whole page
    # slot on three rows; the section's float budget is tight enough that an
    # orphan like that costs a real table its place. The same three floats
    # balanced carry five, four and four.
    nparts = -(-len(blocks) // max_blocks)
    size, extra = divmod(len(blocks), nparts)
    cuts, at = [], 0
    for i in range(nparts):
        step = size + (1 if i < extra else 0)
        cuts.append((at, at + step))
        at += step
    parts = []
    for part_no, (first, last) in enumerate(cuts):
        chunk = blocks[first:last]
        mine = list(head)
        if part_no:
            # THE CONTINUATION CARRIES ITS OWN LABEL AND SAYS IT IS ONE. A
            # second float sharing the first one's label would silently
            # redirect every reference in the manuscript to whichever LaTeX
            # wrote last.
            ci = caption_of(mine)
            body = mine[ci][len(r"\caption{"):].rstrip()
            body = body[:-1] if body.endswith("}") else body
            body = body.rstrip().rstrip(".")
            mine[ci] = (r"\caption{" + body
                        + ", continued at the larger node counts.}")
            for i, ln in enumerate(mine):
                if ln.startswith(r"\label{tab:"):
                    name = ln[len(r"\label{"):].rstrip("}")
                    suffix = "large" if part_no == 1 else f"large{part_no}"
                    mine[i] = r"\label{" + name + suffix + "}"
                    break
        for block in chunk:
            mine += block
        mine += tail
        parts.append("\n".join(mine))
    return "\n".join(parts)


def _stage_key(path: str) -> Tuple[int, int, str]:
    """Where a sweep belongs in the column order, read from its rows alone.

    ORDERING IS NOT COSMETIC HERE. The reliability table lays out one column per
    sweep in the order it is handed them, so this key decides what a reader
    scans left to right, and it must come from the measurements rather than
    from a directory name or a file timestamp, both of which survive a copy
    badly and neither of which says what was measured.

    Two terms, in this order. The DENSE STAGES COME AFTER THE SPARSE LADDER
    instead of interleaving by node count: a stage holding only the high
    density cells covers node counts the sparse ladder already covered, so
    slotting it in by node count would break the ladder in half and put two
    columns headed with the same node counts side by side. Within each family
    the node count ascends. The result reads small, medium, large, xlarge, then
    the dense stages, which is also the order the stages were measured in.
    """
    import csv as _csv

    smallest = None
    ratios = set()
    with open(os.path.join(path, "rows.csv"), newline="", encoding="utf-8") as fh:
        for row in _csv.DictReader(fh):
            raw = (row.get("n") or "").strip()
            if raw.isdigit():
                got = int(raw)
                if smallest is None or got < smallest:
                    smallest = got
            rat = (row.get("ratio") or "").strip()
            if rat.isdigit():
                ratios.add(int(rat))
    # A sweep that never reaches the benchmark's sparsest ratio is a dense cut
    # of it, whatever it is called.
    dense = 1 if (ratios and min(ratios) > DATASET_RATIOS[0]) else 0
    return (dense, smallest if smallest is not None else 1 << 30,
            os.path.basename(path))


def resolve_sweeps(specs: Optional[Sequence[str]]):
    """The sweeps to read, given on the command line or the manuscript's own.

    WHY THIS EXISTS. The three sweeps above are the evidence the manuscript
    currently stands on, and a later `full_v3` run will hold the same columns
    under different directory names. Hard-coding the names would mean editing
    this file to re-derive the tables from a new run, and an edited generator
    is a generator whose output cannot be compared with its predecessor.

    A spec is a sweep directory, a `rows.csv` inside one, or a glob over
    either. The label is the directory name rather than a sentence, because a
    sentence about the node counts would be a claim about a sweep this function
    has not read; `gather` derives the node counts from the rows themselves.
    """
    if not specs:
        return SCALES
    out = []
    seen = set()
    for spec in specs:
        hits = sorted(glob.glob(spec))
        # A GLOB MAY LAND ON THINGS THAT ARE NOT SWEEPS AND THAT IS NOT AN
        # ERROR. `results/bb/full_v3/*` matches four stage directories and also
        # the fingerprint and stage notes that live beside them, and aborting on
        # the first note would make the natural spelling of the argument unusable
        # while offering no clue that the four real directories were fine. A
        # path the caller NAMED still has to exist, because a typed name that
        # holds no rows is a mistake rather than a stray match.
        globbed = bool(hits)
        batch = []
        for hit in hits or [spec]:
            path = os.path.dirname(hit) if os.path.basename(hit) == "rows.csv" else hit
            path = path.rstrip("/")
            if path in seen:
                continue
            if not os.path.exists(os.path.join(path, "rows.csv")):
                if globbed:
                    continue
                raise SystemExit(f"no rows.csv under {path}")
            seen.add(path)
            batch.append((os.path.basename(path), path))
        # A GLOB IS SORTED BY SCALE, AN EXPLICIT LIST IS LEFT ALONE. Alphabetical
        # expansion of `full_v3/*` would print large before medium before small
        # and read backwards. A caller who typed the directories out chose an
        # order and keeps it.
        if globbed:
            batch.sort(key=lambda lp: _stage_key(lp[1]))
        out.extend(batch)
    if not out:
        raise SystemExit(f"--sweeps matched nothing: {' '.join(specs)}")
    return tuple(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default="paper/tables")
    ap.add_argument("--wireless-dir", default="results/bb/wifi_dagdeviren")
    ap.add_argument("--loss-rows",
                    default="results/bb/loss_experiment/rows.csv")
    ap.add_argument(
        "--sweeps",
        nargs="+",
        metavar="DIR",
        help="sweep directories or globs to read instead of the manuscript's "
             "three, e.g. 'results/bb/full_v3/*'",
    )
    a = ap.parse_args(argv)
    os.makedirs(a.outdir, exist_ok=True)
    scales = resolve_sweeps(a.sweeps)

    by_n, owner, meta = gather(scales)
    if not by_n:
        raise SystemExit("no sweep directories found")
    wuli, scored = pick_wuli(by_n)
    print(f"energy recomputation checked on {meta['energy_rows_checked']} rows")
    print("Wu-Li variant means (weight, sync, common valid subset):")
    for v, w in sorted(scored.items(), key=lambda kv: kv[1]):
        print(f"  {v:28s} {w:10.1f}" + ("   <- shown" if v == wuli else ""))
    for n in sorted(owner):
        src = meta["sweeps"][owner[n]]
        print(
            f"  n = {n:3d} from {os.path.basename(owner[n])} "
            f"(fingerprint {src['fingerprint']}, "
            f"{len({r['instance'] for r in by_n[n]})} instances)"
        )

    wrote = []
    dst = os.path.join(a.outdir, "scaling.tex")
    open(dst, "w", encoding="utf-8").write(
        split_by_scale(table_scaling(by_n, owner, meta, wuli)))
    wrote.append(dst)

    tex = table_reliability(scales)
    if tex:
        dst = os.path.join(a.outdir, "reliability.tex")
        open(dst, "w", encoding="utf-8").write(tex)
        wrote.append(dst)

    tex = table_wireless(a.wireless_dir)
    if tex:
        dst = os.path.join(a.outdir, "wireless_compact.tex")
        open(dst, "w", encoding="utf-8").write(tex)
        wrote.append(dst)

    dst = os.path.join(a.outdir, "msgsplit.tex")
    open(dst, "w", encoding="utf-8").write(
        split_by_scale(table_msgsplit(by_n, wuli)))
    wrote.append(dst)

    tex = table_ratio_by_n(by_n, wuli)
    if tex:
        dst = os.path.join(a.outdir, "ratio_by_n.tex")
        open(dst, "w", encoding="utf-8").write(tex)
        wrote.append(dst)

    tex = table_loss_topology(a.loss_rows)
    if tex:
        dst = os.path.join(a.outdir, "loss_topo.tex")
        open(dst, "w", encoding="utf-8").write(tex)
        wrote.append(dst)

    dst = os.path.join(a.outdir, "distmetrics.tex")
    open(dst, "w", encoding="utf-8").write(
        split_by_scale(table_distmetrics(by_n, wuli)))
    wrote.append(dst)

    dst = os.path.join(a.outdir, "loadbalance.tex")
    open(dst, "w", encoding="utf-8").write(
        split_by_scale(table_loadbalance(by_n, wuli)))
    wrote.append(dst)

    tex = table_scaling_by_n(by_n, wuli)
    if tex:
        dst = os.path.join(a.outdir, "scaling_by_n.tex")
        open(dst, "w", encoding="utf-8").write(tex)
        wrote.append(dst)

    dst = os.path.join(a.outdir, "complexity.tex")
    open(dst, "w", encoding="utf-8").write(table_complexity(by_n, wuli))
    wrote.append(dst)

    for p in wrote:
        print("  wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
