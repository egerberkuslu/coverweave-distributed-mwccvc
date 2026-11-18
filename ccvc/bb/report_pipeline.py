#!/usr/bin/env python3
"""One command that turns measured sweeps into every figure and table.

WHY A PIPELINE AND NOT A FOLDER OF SCRIPTS. A table typed by hand and a figure
drawn by hand drift apart from each other and from the data behind them, and
nothing in the document says when that happened. Here every artefact is derived
from `rows.csv` in one pass, each one carries the provenance of the run it came
from, and a stale sweep is refused rather than silently averaged in.

OUTPUT IS ENGLISH. Figures, captions, column headings and table notes are all
English regardless of the language of the document that includes them.

REFUSALS, because a report that quietly drops evidence is worse than one that
stops. A sweep whose rows carry more than one `code_fingerprint` is rejected:
its rows were measured against different versions of the repository and cannot
be pooled. This has happened in practice and the audit caught it.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import subprocess
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from ccvc.bb import armnames

# --------------------------------------------------------------------------
# 0. Scales: which sweep directory answers which question
# --------------------------------------------------------------------------
#: label -> (directory, note). The note is printed in the table so a reader can
#: see the shape of the evidence without opening the CSV.
DEFAULT_SCALES: Tuple[Tuple[str, str, str], ...] = (
    ("Small, n = 10 to 25", "results/bb/sweep_small_full_k6_clean_v2",
     "three seeds per cell, both schedulers"),
    ("Medium, n = 50", "results/bb/sweep_medium_n50_k6_join_v2",
     "six seeds per cell, both schedulers"),
    ("Medium, n = 100", "results/bb/sweep_medium_n100_fixed_v2",
     "three seeds per cell, annealing excluded"),
)

#: Emulator node kind (what `--node` takes and what a run-id carries) to the
#: published arm name. The wireless tables and figures read run-id stems, and
#: a stem carries the node kind, not the paper's name for the arm.
ARM_DISPLAY = {"bbcvc": "MIS-Connector-Backbone",
               "mst": "GHS-MST-Backbone",
               "anneal": "Anneal-Local",
               "wuli": "WuLi-Dominating-Exact",
               "dfs": "DFS-Spanning-Backbone"}

#: Row order in every table. Not alphabetical: the arms a reader compares first
#: come first, and a family stays together.
ARM_ORDER = ("GHS-MST-Backbone",
             "Anneal-Local", "Anneal-TreeAgg", "Anneal-Trickle",
             "DFS-Spanning-Backbone",
             "MIS-Connector-Backbone", "MIS-Connector-TreeAgg",
             "WuLi-Dominating-Exact", "WuLi-Dominating-Bloom",
             "WuLi-Dominating-Chunked",
             "Greedy-Degree-Backbone", "Greedy-Ratio-Backbone",
             "Greedy-Weight-Backbone")


def _f(row: dict, key: str) -> Optional[float]:
    raw = (row.get(key) or "").strip()
    if raw in ("", "None", "n/a", "NA"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _truthy(row: dict, key: str) -> bool:
    return (row.get(key) or "").strip().lower() in ("1", "true", "yes")


def load_rows(path: str) -> List[dict]:
    """Read a sweep CSV and translate pre-rename arm names on the way in.

    The arms were renamed after these sweeps were measured, and a sweep costs
    hours, so the old spellings stay in the files and are translated here, at
    the single point where measured data enters the report. Without this an
    old row and a new row for the SAME arm would be counted as two arms: each
    half would be averaged on its own, and the table would show a difference
    between two spellings of one thing. `ccvc/bb/armnames.py` holds the map.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        return armnames.canonical_rows(list(csv.DictReader(fh)))


#: Code versions the `full_v3` sweep is allowed to contain, and why each exists.
#: A fingerprint absent from this table still aborts a build, because the point
#: of the check is that nobody pools two code versions without saying so. The
#: reasons are recorded in `results/bb/full_v3/FINGERPRINTS.md`.
SANCTIONED_FINGERPRINTS = {
    "798b4393cb4f": "first measurement",
    "bebb0f917410": "GHS-MST-Backbone after the §106 fix, plus rows the "
                    "wall-clock budget skipped on the first pass and that were "
                    "re-run later against the same snapshot",
    "be8a9f9c1e43": "the three annealing arms after the §107 fix",
    "956bf8aa4130": "the densecomplete stage and its fills: the 36 files no "
                    "other stage measured, all of which have m > nk, plus the "
                    "(instance, arm, scheduler) pairs an earlier stage wrote "
                    "as `skipped`. A reboot destroyed the snapshot in /tmp; "
                    "the replacement holds byte-identical measurement code, "
                    "verified per file in FINGERPRINTS.md",
}

#: The arms allowed to carry `be8a9f9c1e43`. That re-measurement changed
#: behaviour, so unlike the other two it must not appear under any other arm.
REMEASURED_ARMS = frozenset(
    {"Anneal-Local", "Anneal-TreeAgg", "Anneal-Trickle"})
ANNEAL_FINGERPRINT = "be8a9f9c1e43"


def check_single_version(rows: Sequence[dict], where: str) -> str:
    """A pooled table needs code versions that are accounted for, not identical.

    ONE VERSION IS THE DEFAULT AND STILL THE RULE for any sweep that is not
    `full_v3`: the check exists because a mid-run edit once put two code
    versions in one CSV with nothing but a column to say so.

    `full_v3` holds three, and each is here for a reason that was written down
    before the rows were measured rather than discovered afterwards. A fix
    landed for GHS-MST-Backbone and another for the annealing arms, both after
    parts of the sweep had already run, and re-measuring every arm for a change
    that cannot touch it would have cost a day and produced identical numbers.
    So the versions are enumerated above with their reasons, and a fingerprint
    that is NOT enumerated still aborts the build. The difference between this
    and silently pooling is that an unexplained version cannot get through.

    The annealing fingerprint is checked harder than the others, because that
    fix changed behaviour: two runs that had claimed success were rejected by
    the validator afterwards. Any non-annealing arm carrying it means rows were
    folded wrongly, so that aborts too.
    """
    by_fp: Dict[str, set] = {}
    for r in rows:
        by_fp.setdefault(r.get("code_fingerprint", ""), set()).add(
            r.get("variant", ""))
    seen = sorted(by_fp)
    if len(seen) == 1:
        return seen[0]
    unknown = [f for f in seen if f not in SANCTIONED_FINGERPRINTS]
    if unknown:
        raise SystemExit(
            f"{where}: rows carry {len(seen)} code fingerprints and "
            f"{sorted(unknown)} is not accounted for in "
            "SANCTIONED_FINGERPRINTS. They were measured against different "
            "versions of the repository and must not be pooled; re-run the "
            "sweep without editing ccvc/bb/*.py while it runs.")
    stray = by_fp.get(ANNEAL_FINGERPRINT, set()) - REMEASURED_ARMS
    if stray:
        raise SystemExit(
            f"{where}: {sorted(stray)} carry {ANNEAL_FINGERPRINT}, which "
            "belongs to the annealing re-measurement alone. Rows were folded "
            "wrongly.")
    return "+".join(seen)


# --------------------------------------------------------------------------
# 1. The common valid subset, the only fair basis for a comparison
# --------------------------------------------------------------------------
def _run_infeasible(r: dict) -> bool:
    """Is this instance PROVABLY unsolvable, by the strongest test on the row?

    THE COUNTING BOUND IS NOT THE ONLY ONE ANY MORE. `m > nk` was the original
    witness and it is still correct, but section 96 added a strictly stronger
    one: sum over v of min(deg(v), k) < m. It catches cases the counting bound
    lets through, `m == nk` among them, and the sweep writes its verdict in
    `infeasible` with the witness in `infeasible_reason`.

    This function used to read the counting bound alone, so an instance that no
    arm can possibly solve stayed in the denominator and every arm lost a point
    for it. MEASURED on the n = 50 sweep: `n50_m300_s6` is degree-deficient,
    `counting_bound_infeasible` is False for it, and all twenty-five arms read
    17/18 when the honest number over feasible instances is 17/17.

    Older CSVs have no `infeasible` column, so the counting bound remains the
    fallback and those tables keep reading exactly as they did.
    """
    if "infeasible" in r:
        return _truthy(r, "infeasible")
    if (r.get("instance_feasible") or "") == "no":
        return True
    return _truthy(r, "counting_bound_infeasible")


def _infeasible_witness(rows: Sequence[dict], names) -> str:
    """Which bound rejected the excluded instances, in the caption's words."""
    reasons = {(r.get("infeasible_reason") or "").strip()
               for r in rows if r["instance"] in names}
    reasons.discard("")
    if reasons == {"degree_deficiency"}:
        return r"$\sum_v \min(\deg v, k) < m$"
    if len(reasons) > 1:
        return r"$m > nk$ or $\sum_v \min(\deg v, k) < m$"
    return r"$m > nk$"


def common_subset(rows: Sequence[dict]):
    """Instances every arm solved validly, with the infeasible ones removed.

    An arm that fails on an instance DISAPPEARS from that instance's average
    rather than scoring badly in it, so an average taken over each arm's own
    successes rewards giving up on the hard cases.
    """
    # A ROW THAT NEVER RAN CANNOT TESTIFY TO FEASIBILITY. `sweep._skipped_row`
    # fills `infeasible` with False because the dataclass needs a value, not
    # because anything was measured, and reading that default as evidence turns
    # a wall-clock cut into a claim about the instance. MEASURED on the
    # `largedense` stage, where all twelve instances have m > nk at k = 6 and
    # therefore admit no cover at all: half its rows were skipped by the time
    # budget, and with those defaults counted the stage reported twelve
    # FEASIBLE instances and an empty common subset, which reads as twenty-five
    # arms failing on twelve solvable problems. The verdict is therefore taken
    # per instance from the rows that actually ran.
    infeasible = infeasible_instances(rows)
    feasible = [r for r in rows if r["instance"] not in infeasible]
    arms = {f"{r['variant']}/{r['scheduler']}" for r in feasible}
    solved: Dict[str, set] = defaultdict(set)
    for r in feasible:
        if _truthy(r, "valid") and (r.get("verdict") or "") == "solved":
            solved[r["instance"]].add(f"{r['variant']}/{r['scheduler']}")
    common = {i for i, got in solved.items() if len(got) == len(arms)}
    return [r for r in feasible if r["instance"] in common], {
        "arms": len(arms),
        "instances_total": len({r["instance"] for r in rows}),
        "instances_infeasible": len(infeasible),
        "infeasible_witness": _infeasible_witness(rows, infeasible),
        "instances_feasible": len({r["instance"] for r in feasible}),
        "instances_common": len(common),
    }


def infeasible_instances(rows: Sequence[dict]) -> set:
    """Instance names that provably admit no cover, judged only on rows that ran.

    A ROW THAT NEVER RAN CANNOT TESTIFY. `sweep._skipped_row` fills `infeasible`
    with False because the dataclass needs a value, not because anything was
    measured. Read as evidence, that default turns a wall-clock cut into a claim
    about the instance, and the claim is the flattering direction: the instance
    looks solvable and every arm looks like it failed on it.

    MEASURED on the `largedense` stage, where all twelve instances have m > nk
    at k = 6 and none admits a cover: half its rows were skipped by the budget,
    and with the defaults counted the stage reported twelve feasible instances,
    an empty common subset, and a reliability column reading nought per cent for
    every arm that happened to have a skipped row. The honest reading of that
    column is a dash, because there was nothing there to answer.
    """
    ran = [r for r in rows if (r.get("status") or "") != "skipped"]
    if not ran:
        return {r["instance"] for r in rows if _run_infeasible(r)}
    return {r["instance"] for r in ran if _run_infeasible(r)}


def arm_stats(rows: Sequence[dict], common: Sequence[dict]) -> Dict[str, dict]:
    """Per arm: quality on the common subset, cost, and how often it answered."""
    dead = infeasible_instances(rows)
    feasible = [r for r in rows
                if r["instance"] not in dead
                and (r.get("status") or "") != "skipped"]
    total: Dict[str, int] = defaultdict(int)
    ok: Dict[str, int] = defaultdict(int)
    for r in feasible:
        a = f"{r['variant']}/{r['scheduler']}"
        total[a] += 1
        if _truthy(r, "valid") and (r.get("verdict") or "") == "solved":
            ok[a] += 1
    weight: Dict[str, List[float]] = defaultdict(list)
    exact: Dict[str, List[float]] = defaultdict(list)
    tx: Dict[str, List[float]] = defaultdict(list)
    algo_tx: Dict[str, List[float]] = defaultdict(list)
    rounds: Dict[str, List[float]] = defaultdict(list)
    conv_ms: Dict[str, List[float]] = defaultdict(list)
    for r in common:
        a = f"{r['variant']}/{r['scheduler']}"
        w, e, t = _f(r, "total_weight"), _f(r, "exact_weight"), _f(r, "tx")
        if w is not None:
            weight[a].append(w)
        if w is not None and e:
            exact[a].append(w / e)
        if t is not None:
            tx[a].append(t)
        h = _f(r, "hello_tx")
        if t is not None and h is not None:
            # ALGORITHM MESSAGES, HELLO SEPARATED OUT. A single `tx` number
            # conflates two different things: the work the algorithm does, and
            # the periodic neighbour beacon, which is proportional to nodes
            # times ROUNDS and therefore charges a slow arm for being slow
            # rather than for being chatty.
            # MEASURED at n=100: DFS-Spanning-Backbone sends 66,554 messages of which 97.1%
            # are HELLO. Its own algorithm traffic is 1,929, LESS than
            # GHS-MST-Backbone's 2,407. It takes 783 rounds against MIS-Connector-Backbone's 34.
            algo_tx[a].append(t - h)
        # ROUNDS AND TIME ARE NOT THE SAME COLUMN. `slots` exists only under
        # the synchronous scheduler, because an asynchronous run has no global
        # round. Falling back to `t_conv_ms` when slots is missing would put
        # milliseconds and rounds in one column under one heading, which is the
        # kind of unit mixing a reader cannot see and cannot recover from.
        rd = _f(r, "slots")
        if rd is not None:
            rounds[a].append(rd)
        ms = _f(r, "t_conv_ms")
        if ms is not None:
            conv_ms[a].append(ms)
    best = min((sum(v) / len(v) for v in weight.values() if v), default=None)
    out = {}
    for a in sorted(total):
        mean_w = (sum(weight[a]) / len(weight[a])) if weight[a] else None
        out[a] = {
            "valid": ok[a], "runs": total[a],
            "rel_best": (mean_w / best) if (mean_w and best) else None,
            "rel_exact": (sum(exact[a]) / len(exact[a])) if exact[a] else None,
            "tx": (sum(tx[a]) / len(tx[a])) if tx[a] else None,
            "algo_tx": (sum(algo_tx[a]) / len(algo_tx[a])) if algo_tx[a] else None,
            "rounds": (sum(rounds[a]) / len(rounds[a])) if rounds[a] else None,
            "conv_ms": (sum(conv_ms[a]) / len(conv_ms[a])) if conv_ms[a] else None,
        }
    return out


# --------------------------------------------------------------------------
# 2. LaTeX tables
# --------------------------------------------------------------------------
def _tex_escape(text: str) -> str:
    return text.replace("_", r"\_").replace("&", r"\&").replace("%", r"\%")


def _table_nothing_solvable(prov: dict, label: str, note: str,
                            tex_label: str) -> str:
    """The table for a scale on which no instance admits a cover at all."""
    return "\n".join([
        r"\begin{table}[tb]", r"\centering",
        r"\caption{" + _tex_escape(label) + ". "
        + _tex_escape(note[:1].upper() + note[1:]) + ". "
        + f"No instance at this scale admits a cover: all "
          f"{prov['instances_infeasible']} of "
          f"{prov['instances_total']} are infeasible ({prov['infeasible_witness']}), "
          r"so there is no quality comparison to draw and every arm's task "
          r"here is to announce impossibility.}",
        r"\label{" + tex_label + "}",
        r"\begin{tabular}{ll}", r"\toprule",
        r"Instances & " + str(prov["instances_total"]) + r" \\",
        r"Feasible & " + str(prov["instances_feasible"]) + r" \\",
        r"Infeasible & " + str(prov["instances_infeasible"]) + r" \\",
        r"Common valid subset & " + str(prov["instances_common"]) + r" \\",
        r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])


def table_comparison(stats: Dict[str, dict], prov: dict, label: str,
                     note: str, tex_label: str) -> str:
    """One scale, one table. Bold marks the best value in each numeric column."""
    rows = [(a, s) for a, s in stats.items() if s["rel_best"] is not None]
    rows.sort(key=lambda kv: (ARM_ORDER.index(kv[0].split("/")[0])
                              if kv[0].split("/")[0] in ARM_ORDER else 99,
                              kv[0]))
    if not rows:
        # A SCALE WHERE NOTHING IS SOLVABLE STILL HAS TO SAY SO. Every instance
        # in the `largedense` stage has m > nk at k = 6, so no cover exists, no
        # arm is valid anywhere and the common valid subset is empty. There is
        # no quality table to draw and the honest output is the sentence saying
        # why, not a crash on `min()` of nothing and not a table of dashes that
        # reads as twenty-five arms failing.
        return _table_nothing_solvable(prov, label, note, tex_label)
    has_exact = any(s["rel_exact"] is not None for _, s in rows)
    best_rel = min(s["rel_best"] for _, s in rows)
    # NAME THE REFERENCE. "1.000" is meaningless until the reader knows which
    # arm it is, and here it can be an arm that is unreliable at other scales:
    # the normalisation is computed on the common subset, where every arm is
    # valid, so it is fair, but a reader comparing two tables needs to see that
    # the baseline changed between them.
    ref_arm = min(rows, key=lambda kv: kv[1]["rel_best"])[0]
    best_exact = min((s["rel_exact"] for _, s in rows
                      if s["rel_exact"] is not None), default=None)
    cheap_algo = min((s["algo_tx"] for _, s in rows
                      if s["algo_tx"] is not None), default=0.0)

    cols = "l" + "r" * (7 if has_exact else 6)
    out = [r"\begin{table}[tb]", r"\centering",
           r"\caption{" + _tex_escape(label) + ". " + _tex_escape(note[:1].upper() + note[1:]) + ". "
           + f"Common valid subset: {prov['instances_common']} of "
             f"{prov['instances_feasible']} feasible instances"
           # NAME THE WITNESS THAT ACTUALLY FIRED. Two bounds prove
           # infeasibility and they are not the same: $m > nk$ counts
           # edges against total capacity, while the degree deficiency
           # $\sum_v \min(\deg v, k) < m$ is strictly stronger. Printing
           # the counting bound for a row the degree bound rejected
           # states a fact that is not true of that instance.
           + (f"; {prov['instances_infeasible']} instance(s) excluded as "
              f"provably capacity-infeasible ({prov['infeasible_witness']})"
              if prov["instances_infeasible"] else "")
           + ". Weights are relative to " + _tex_escape(ref_arm)
           + ", the lightest arm on this subset.}",
           r"\label{" + tex_label + "}",
           r"\begin{tabular}{" + cols + "}", r"\toprule",
           ("Arm & Valid runs & Weight / best"
            + (" & Weight / optimum" if has_exact else "")
            + r" & Algorithm msgs & HELLO msgs & Rounds & Time (ms) \\"),
           r"\midrule"]
    for a, s in rows:
        rel = f"{s['rel_best']:.3f}"
        if abs(s["rel_best"] - best_rel) < 1e-9:
            rel = r"\textbf{" + rel + "}"
        ex = ""
        if has_exact:
            if s["rel_exact"] is None:
                ex = " & --"
            else:
                v = f"{s['rel_exact']:.3f}"
                if best_exact and abs(s["rel_exact"] - best_exact) < 1e-9:
                    v = r"\textbf{" + v + "}"
                ex = " & " + v
        algo = "--" if s["algo_tx"] is None else f"{s['algo_tx']:.0f}"
        if s["algo_tx"] is not None and abs(s["algo_tx"] - cheap_algo) < 1e-9:
            algo = r"\textbf{" + algo + "}"
        hello = ("--" if (s["tx"] is None or s["algo_tx"] is None)
                 else f"{s['tx'] - s['algo_tx']:.0f}")
        rnd = "--" if s["rounds"] is None else f"{s['rounds']:.0f}"
        cms = "--" if s["conv_ms"] is None else f"{s['conv_ms']:.0f}"
        out.append(f"{_tex_escape(a)} & {s['valid']}/{s['runs']} & {rel}{ex} "
                   f"& {algo} & {hello} & {rnd} & {cms} " + r"\\")
    out += [r"\bottomrule", r"\end{tabular}",
            r"\begin{flushleft}\footnotesize",
            r"``Rounds'' is defined only under the synchronous scheduler; an "
            r"asynchronous run has no global round, so those cells are empty "
            r"and the time column carries the comparison instead. "
            r"Messages are split because a single total conflates two things: "
            r"``algorithm msgs'' is the protocol's own traffic, while HELLO is "
            r"the periodic neighbour beacon and grows with nodes times rounds, "
            r"so it charges a SLOW arm rather than a CHATTY one. "
            r"``Weight / best'' is relative to the best arm on the same "
            r"instances and is NOT an approximation ratio; ``weight / optimum'' "
            r"is, and is defined only where the exact solver ran. ``Valid runs'' "
            r"counts rows that both terminated and passed the validator, over "
            r"the feasible instances. Lower is better in every numeric column.",
            r"\end{flushleft}", r"\end{table}", ""]
    return "\n".join(out)


def table_reliability(scales: Sequence[Tuple[str, Dict[str, dict], dict]]) -> str:
    """How often each arm produced a valid answer, across every scale.

    Separated from quality on purpose: an arm can look good on weight precisely
    because it failed on the instances that were hard.
    """
    arms = sorted({a.split("/")[0] for _, st, _ in scales for a in st},
                  key=lambda v: ARM_ORDER.index(v) if v in ARM_ORDER else 99)
    out = [r"\begin{table}[tb]", r"\centering",
           r"\caption{Reliability across scales: share of feasible runs that "
           r"terminated and passed the validator. Quality is reported "
           r"separately, because an arm that fails on the hard instances "
           r"leaves them out of its own average.}",
           r"\label{tab:reliability}",
           r"\begin{tabular}{l" + "r" * len(scales) + "}", r"\toprule",
           "Arm & " + " & ".join(_tex_escape(lbl) for lbl, _, _ in scales)
           + r" \\", r"\midrule"]
    for arm in arms:
        cells = []
        for _, st, _ in scales:
            got = [(s["valid"], s["runs"]) for a, s in st.items()
                   if a.split("/")[0] == arm]
            if not got:
                cells.append("--")
                continue
            v, r_ = sum(x for x, _ in got), sum(y for _, y in got)
            if not r_:
                # AN EMPTY DENOMINATOR IS NOT A SCORE OF ZERO. The `largedense`
                # scale has m > nk at k = 6 on every instance, so no arm has a
                # feasible instance to answer there and the share is undefined.
                # Printing 0 per cent instead read as twenty-five arms failing
                # on twelve problems, when the truth is that the problems have
                # no solution and every arm said so.
                cells.append("--")
                continue
            pct = 100.0 * v / r_
            cells.append(f"{pct:.0f}\\%" if pct == 100 else
                         r"\textit{" + f"{pct:.0f}\\%" + "}")
        out.append(_tex_escape(armnames.display(arm)) + " & "
                   + " & ".join(cells) + r" \\")
    out += [r"\bottomrule", r"\end{tabular}",
            r"\begin{flushleft}\footnotesize",
            r"Italic marks a share below 100\%. Capacity-infeasible instances "
            r"($m > nk$) are excluded from the denominator, so a value below "
            r"100\% is an arm failure and not a property of the instance. A "
            r"dash marks a scale where the arm has no feasible instance to "
            r"answer, either because it was not run there or because no "
            r"instance at that scale admits a cover.",
            r"\end{flushleft}", r"\end{table}", ""]
    return "\n".join(out)


def _wireless_docs(indir: str) -> List[dict]:
    """Load run documents, skipping the side files a run directory also holds.

    TWO LAYOUTS, BECAUSE THE RUNNER CHANGED AND THE TABLE OUTLIVED IT. Early
    batches wrote one flat `<stem>.json` per run; the current runner writes a
    DIRECTORY per run with `summary.json` inside it. Reading only the flat form
    made this return nothing for an archive that was perfectly intact, so the
    published `wireless.tex` could no longer be regenerated from the evidence it
    was built on. A table that cannot be rebuilt is a table nobody can check,
    which is the failure this whole pipeline exists to prevent, so both layouts
    are accepted and the stem is taken from the file or the directory name.
    """
    import glob
    paths = sorted(glob.glob(os.path.join(indir, "*.json")))
    paths += sorted(glob.glob(os.path.join(indir, "*", "summary.json")))
    docs = []
    for path in paths:
        if os.path.getsize(path) < 100:
            continue
        text = open(path, encoding="utf-8").read()
        i = text.find("{")
        if i < 0:
            continue
        try:
            d = json.loads(text[i:])
        except json.JSONDecodeError:
            continue
        stem = (os.path.basename(os.path.dirname(path))
                if os.path.basename(path) == "summary.json"
                else os.path.basename(path)[:-5])
        parts = stem.split("_")
        # Only a stem ending in s<digits> is a run document; plans and errors
        # are skipped rather than parsed into a crash.
        if len(parts) < 3 or not (parts[-1][:1] == "s" and parts[-1][1:].isdigit()):
            continue
        d["_arm"], d["_seed"] = parts[1], int(parts[-1][1:])
        d["_family"] = "_".join(parts[2:-1]) or "n?"
        docs.append(d)
    return docs


def table_wireless(indir: str) -> Optional[str]:
    """Real Mininet-WiFi runs, ONE TABLE PER INSTANCE FAMILY.

    Everything here is read from the run documents. The previous version had
    the scale, the capacity, the arm list and even the story of one invalid
    seed written into the caption as literal text, so it kept describing a
    batch that had since been replaced.
    """
    docs = _wireless_docs(indir)
    if not docs:
        return None
    names = ARM_DISPLAY
    families: Dict[str, List[dict]] = {}
    for d in docs:
        families.setdefault(d["_family"], []).append(d)

    out: List[str] = []
    for fam, group in sorted(families.items()):
        group.sort(key=lambda d: (d["_seed"], d["_arm"]))
        n_nodes = group[0].get("n_nodes", "?")
        # Did every arm of a seed see the same graph? That is what makes the
        # comparison paired, and it is MEASURED here rather than asserted.
        by_seed: Dict[int, List[dict]] = {}
        for d in group:
            by_seed.setdefault(d["_seed"], []).append(d)
        paired = all(len({x["discovered_vs_target"]["n_observed"] for x in v}) == 1
                     for v in by_seed.values())
        n_valid = sum(1 for d in group
                      if (d.get("validation_vs_discovered") or d["validation"])["valid"])
        n_empty = sum(1 for d in group if not d.get("cover"))
        out += [r"\begin{table}[tb]", r"\centering",
                r"\caption{Real Mininet-WiFi runs, $n=" + str(n_nodes) +
                r"$, family \texttt{" + _tex_escape(fam) + r"}. The stations do "
                r"not always discover the planned topology, so a cover is judged "
                r"against the graph they actually saw; judging it against the "
                r"plan would charge the channel to the algorithm.}",
                r"\label{tab:wireless_" + fam + "}",
                r"\begin{tabular}{llrrrrrl}", r"\toprule",
                r"Seed & Arm & Planned $m$ & Discovered $m$ & Cover weight & "
                r"Slots & Messages & Valid \\", r"\midrule"]
        for d in group:
            dv = d["discovered_vs_target"]
            vd = d.get("validation_vs_discovered") or d["validation"]
            if not d.get("cover"):
                # An arm that returned nothing has cover weight 0, which in a
                # "lower is better" column would read as the best result on the
                # page. It is named instead of being printed as a number.
                weight = r"\textit{no cover}"
                ok = r"\textbf{no}"
            else:
                weight = f"{d.get('cover_weight', '--')}"
                ok = r"\checkmark" if vd["valid"] else r"\textbf{no}"
            out.append(f"{d['_seed']} & {names.get(d['_arm'], d['_arm'])} & "
                       f"{dv['n_target']} & {dv['n_observed']} & {weight} & "
                       f"{d.get('slots') or '--'} & "
                       f"{d.get('totals', {}).get('tx', '--')} & {ok} " + r"\\")
        note = ("Every arm in a seed discovered the same graph, so the "
                "comparison is paired."
                if paired else
                r"\textbf{Arms within a seed did not all discover the same "
                r"graph}, so rows of one seed are not strictly paired.")
        if n_empty:
            note += (f" {n_empty} of {len(group)} runs returned no cover at all "
                     f"within the time budget.")
        out += [r"\bottomrule", r"\end{tabular}",
                r"\begin{flushleft}\footnotesize",
                note + f" {n_valid} of {len(group)} runs are validator-clean "
                f"against the discovered graph.",
                r"\end{flushleft}", r"\end{table}", ""]
    return "\n".join(out)


# --------------------------------------------------------------------------
# 3. Driver
# --------------------------------------------------------------------------
def table_bridgefix(indir: str) -> Optional[str]:
    """Emit tab:bridgefix from measured data instead of a typed-in table.

    The before/after comparison used to live as literal numbers in the .tex,
    which meant nothing regenerated it and nothing noticed when the code moved.
    `ccvc/bb/bridgefix_measure.py` runs both settings of
    `AnnealParams.repay_bridge_credit` and writes the table next to its rows;
    the pipeline only has to carry it through, and says so if it is missing.
    """
    tex = os.path.join(indir, "tab_bridgefix.tex")
    if not os.path.exists(tex):
        return None
    return open(tex, encoding="utf-8").read()


def _scored_scales(scales, collected):
    """The scales that have something to plot: a non-empty common valid subset.

    The quality-against-reliability figure takes two scales and plots arms in
    both. A scale on which no instance admits a cover at all has no arm with a
    mean weight, so handing it over produces an exception, not a figure; the
    `largedense` stage is exactly that and happens to sort last. Picking the
    endpoints from the scored scales keeps the figure at the widest span that
    has data instead of failing on the widest span that exists.
    """
    scored = [s[1] for s, c in zip(scales, collected)
              if c[2]["instances_common"] > 0]
    return scored or [scales[0][1]]


def _first_scored_scale(scales, collected):
    return _scored_scales(scales, collected)[0]


def _last_scored_scale(scales, collected):
    return _scored_scales(scales, collected)[-1]


def run(scales, wireless_dir, outdir, figures=True,
        bridgefix_dir=None) -> dict:
    os.makedirs(outdir, exist_ok=True)
    tex_dir = os.path.join(outdir, "tables")
    os.makedirs(tex_dir, exist_ok=True)
    manifest = {"tables": [], "figures": [], "scales": []}
    collected = []

    for label, path, note in scales:
        csv_path = os.path.join(path, "rows.csv")
        if not os.path.exists(csv_path):
            print(f"  skipped (no rows.csv): {path}")
            continue
        rows = load_rows(csv_path)
        fp = check_single_version(rows, path)
        common, prov = common_subset(rows)
        stats = arm_stats(rows, common)
        collected.append((label, stats, prov))
        slug = os.path.basename(path)
        tex = table_comparison(stats, prov, label, note, f"tab:cmp-{slug}")
        dst = os.path.join(tex_dir, f"comparison_{slug}.tex")
        open(dst, "w", encoding="utf-8").write(tex)
        manifest["tables"].append(dst)
        manifest["scales"].append(
            {"label": label, "dir": path, "code_fingerprint": fp, **prov})
        print(f"  table: {dst}  ({prov['instances_common']} common instances, "
              f"fingerprint {fp})")

    if collected:
        dst = os.path.join(tex_dir, "reliability.tex")
        open(dst, "w", encoding="utf-8").write(table_reliability(collected))
        manifest["tables"].append(dst)
        print(f"  table: {dst}")

    if wireless_dir and os.path.isdir(wireless_dir):
        tex = table_wireless(wireless_dir)
        if tex:
            dst = os.path.join(tex_dir, "wireless.tex")
            open(dst, "w", encoding="utf-8").write(tex)
            manifest["tables"].append(dst)
            print(f"  table: {dst}")

    if bridgefix_dir and os.path.isdir(bridgefix_dir):
        tex = table_bridgefix(bridgefix_dir)
        if tex:
            dst = os.path.join(tex_dir, "bridgefix.tex")
            open(dst, "w", encoding="utf-8").write(tex)
            manifest["tables"].append(dst)
            print(f"  table: {dst}")
        else:
            print(f"  NOTE: {bridgefix_dir} has no tab_bridgefix.tex; "
                  f"run `python3 -m ccvc.bb.bridgefix_measure` to make it")

    if figures:
        jobs = [
            ("ccvc.bb.compare_figures",
             ["--rows", os.path.join(scales[0][1], "rows.csv"),
              "--outdir", os.path.join(outdir, "figures_small")]),
            ("ccvc.bb.reliability_figure",
             ["--small", os.path.join(_first_scored_scale(scales, collected), "rows.csv"),
              "--medium", os.path.join(_last_scored_scale(scales, collected), "rows.csv"),
              "--outdir", os.path.join(outdir, "figures_scale")]),
        ]
        if wireless_dir and os.path.isdir(wireless_dir):
            jobs.append(("ccvc.bb.wifi_figure",
                         ["--indir", wireless_dir,
                          "--outdir", os.path.join(outdir, "figures_wifi")]))
        env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        for mod, args in jobs:
            res = subprocess.run(["python3", "-m", mod] + args,
                                 capture_output=True, text=True, env=env)
            if res.returncode != 0:
                print(f"  FIGURE FAILED {mod}: {res.stderr.strip()[:200]}")
                continue
            for line in res.stdout.splitlines():
                if line.strip().startswith("wrote"):
                    p = line.split("wrote", 1)[1].strip()
                    manifest["figures"].append(p)
                    print(f"  figure: {p}")

    open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8").write(
        json.dumps(manifest, indent=2) + "\n")
    return manifest


def resolve_scales(specs):
    """The sweeps to report on: the manuscript's three, or ones named outright.

    WHY. `DEFAULT_SCALES` names the evidence the manuscript currently stands
    on, and a replacement run holds the same columns under different directory
    names. Editing the constant to point the pipeline at a new run would change
    the generator at the same moment as the data, and two outputs produced by
    two generators cannot be diffed against each other to see what the new data
    did. A spec is a sweep directory, a rows.csv inside one, or a glob over
    either; the label is the directory name, because a sentence about seeds and
    node counts would be a claim about a sweep this function has not opened.
    """
    if not specs:
        return [s for s in DEFAULT_SCALES if os.path.isdir(s[1])]
    out, seen = [], set()
    for spec in specs:
        hits = sorted(glob.glob(spec))
        # A NAME AND A PATTERN ARE DIFFERENT PROMISES. Naming a directory that
        # holds no sweep is a mistake worth stopping for; a glob is a request
        # for whatever matches, and `results/bb/full_v3/*` legitimately matches
        # the archive and top-up directories beside the stages.
        globbed = bool(hits)
        for hit in (hits or [spec]):
            path = os.path.dirname(hit) if os.path.basename(hit) == "rows.csv" else hit
            path = path.rstrip("/")
            if path in seen:
                continue
            if not os.path.exists(os.path.join(path, "rows.csv")):
                if globbed:
                    continue
                raise SystemExit(f"no rows.csv under {path}")
            seen.add(path)
            out.append((os.path.basename(path), path, "see the sweep manifest"))
    if not out:
        raise SystemExit(f"--sweeps matched nothing: {' '.join(specs)}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default="results/bb/report")
    ap.add_argument("--wireless-dir", default=None,
                    help="directory of collected Mininet-WiFi run documents")
    ap.add_argument("--bridgefix-dir", default="results/bb/bridgefix",
                    help="directory written by ccvc.bb.bridgefix_measure")
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument(
        "--sweeps",
        nargs="+",
        metavar="DIR",
        help="sweep directories or globs to read instead of the manuscript's "
             "three, e.g. 'results/bb/full_v3/*'",
    )
    a = ap.parse_args(argv)
    scales = resolve_scales(a.sweeps)
    if not scales:
        raise SystemExit("no sweep directories found")
    print(f"building report from {len(scales)} scale(s)")
    m = run(scales, a.wireless_dir, a.outdir, figures=not a.no_figures,
            bridgefix_dir=a.bridgefix_dir)
    print(f"\n{len(m['tables'])} table(s), {len(m['figures'])} figure file(s)")
    print(f"manifest: {os.path.join(a.outdir, 'manifest.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
