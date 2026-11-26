#!/usr/bin/env python3
"""Dispersion, intervals and paired tests for the R1 revision. REPORTING ONLY.

Reviewer 2 of Access-2026-53199 asked for spread, confidence intervals, runs per
cell and paired significance tests instead of means, and called the ratio to the
best arm circular. This module answers that from `rows.csv` files alone and
follows paper/CoverWeave_R1/contract/R1_PREREG.md, sections 3, 4, 6 and 7.

* The unit is the instance. Runs of one (condition, instance, arm), for example
  channel seeds, are averaged first; tests are made across instances and are
  paired on the same instances.
* Every reference is external to the arms: the proven optimum (n <= 50), the
  trivial cover C = V of weight W(V), the centralized greedies, and an LP lower
  bound (capacitated vertex cover relaxation without connectivity) that replaces
  the "ratio to the best arm" where no optimum exists.
* Instances with m = nk force C = V. They are kept out of every quality number
  and get their own validity table. Provably infeasible instances are never
  scored for quality.

No measurement module may import this file (it is in sweep.REPORTING_MODULES).

    python3 -m ccvc.bb.revision_stats               # full_v3 -> results/bb/r1_stats/
    python3 -m ccvc.bb.revision_stats --rows R.csv --instance-dir DIR --out OUT
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import warnings
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse
from scipy.optimize import linprog
from scipy.stats import binomtest, rankdata, wilcoxon

from ccvc.bb import armnames
from ccvc.bb.report_pipeline import ARM_ORDER

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAGES = (
    "small",
    "medium",
    "mediumdense",
    "large",
    "largedense",
    "densecomplete",
    "xlarge",
)
DEFAULT_ROWS = tuple(f"results/bb/full_v3/{s}/rows.csv" for s in STAGES)
DEFAULT_OPTIMA = ("results/bb/exact/optima.csv", "results/bb/exact/optima_n50.csv")
DEFAULT_CENTRAL = ("results/bb/exact/central.csv", "results/bb/exact/central_n50.csv")
DEFAULT_OUT = "results/bb/r1_stats"

#: Prereg section 4: the primary arm, fixed from the development set.
PRIMARY = "Anneal-Local/async"
#: Prereg H-b: the best distributed baseline of the development set, i.e. the
#: non-annealing configuration with the lowest mean ratio to the proven optimum
#: on the pooled n <= 50 basis of full_v3 (printed under "Development ranking"
#: in summary.md, so the choice can be re-checked from the rows).
BASELINE = "GHS-MST-Backbone/async"
#: Columns that make two runs of the same instance a different experiment.
CONDITION_COLUMNS = ("k", "loss")
#: Disjoint size bands for tests; "<=50" is a pooled view for descriptives only.
BANDS = (
    ("10-25", 10, 25),
    ("50", 50, 50),
    ("100", 100, 100),
    ("150-200", 150, 200),
    ("250+", 250, 10**9),
)
POOLED = "<=50"
BOOT = 10_000
BOOT_SEED = 20261118
#: The three greedies of the published Table 3 (exact_compare.py central).
GREEDY_LABEL = {
    "gccvc": "Greedy-Degree-Upstream",
    "grccvc": "Greedy-Ratio-Upstream",
    "gwccvc": "Greedy-Weight-Upstream",
}
#: Centralized references; the hybrid genetic solver of kol2026 writes its rows
#: with ccvc/bb/hga_ref.py (arm HGA-Upstream, one row per GA seed).
CENTRAL_LABEL = {**GREEDY_LABEL, "hga": "HGA-Upstream"}


# --------------------------------------------------------------------------
# 1. Statistics (pure functions, each one has a known-answer test)
# --------------------------------------------------------------------------
def holm(pvalues: Sequence[float]) -> List[float]:
    """Holm step-down adjusted p-values, in input order."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    out, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        out[i] = running
    return out


def clopper_pearson(x: int, n: int) -> Tuple[float, float]:
    """Two-sided exact 95% interval of a binomial proportion."""
    ci = binomtest(x, n).proportion_ci(0.95, method="exact")
    return float(ci.low), float(ci.high)


def upper_one_sided(x: int, n: int) -> float:
    """One-sided exact 95% upper bound (Clopper-Pearson); 1 - 0.05**(1/n) at x = 0."""
    return float(binomtest(x, n, alternative="less").proportion_ci(0.95).high)


def boot_mean_ci(
    values: Sequence[float], B: int = BOOT, seed: int = BOOT_SEED
) -> Tuple[float, float]:
    """Percentile bootstrap 95% interval of the mean, fixed seed per call."""
    x = np.asarray(values, dtype=float)
    idx = np.random.default_rng(seed).integers(0, len(x), size=(B, len(x)))
    lo, hi = np.percentile(x[idx].mean(axis=1), [2.5, 97.5])
    return float(lo), float(hi)


def describe(values: Sequence[float], B: int = BOOT) -> dict:
    x = np.asarray(values, dtype=float)
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    lo, hi = boot_mean_ci(x, B)
    return {
        "n": len(x),
        "median": med,
        "q1": q1,
        "q3": q3,
        "mean": x.mean(),
        "sd": x.std(ddof=1) if len(x) > 1 else float("nan"),
        "ci_lo": lo,
        "ci_hi": hi,
    }


def paired_test(primary: Sequence[float], other: Sequence[float]) -> dict:
    """Wilcoxon signed-rank on d = other - primary, Pratt zeros.

    d > 0 means the primary arm has the lower (better) ratio. `p_lower` is the
    one-sided p for "primary lower". The exact null distribution is used only
    when it is valid in scipy 1.11 (n <= 50, no zero and no tied |d|); otherwise
    the normal approximation with Pratt and tie corrections. `r_rb` is the
    matched-pairs rank-biserial correlation (Kerby's simple difference over the
    non-zero pairs): +1 when the primary is lower on every non-tied instance.
    """
    d = np.round(np.asarray(other, float) - np.asarray(primary, float), 12)
    nz = d[d != 0]
    out = {"n_pairs": len(d), "n_zero": int(len(d) - len(nz))}
    if len(nz) == 0:
        return {
            **out,
            "T": 0.0,
            "p_two": 1.0,
            "p_lower": 1.0,
            "r_rb": 0.0,
            "method": "all-tied",
        }
    ranks = rankdata(np.abs(nz))
    rp, rm = ranks[nz > 0].sum(), ranks[nz < 0].sum()
    exact = len(d) <= 50 and len(nz) == len(d) and len(np.unique(np.abs(d))) == len(d)
    method = "exact" if exact else "approx"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        two = wilcoxon(d, zero_method="pratt", alternative="two-sided", method=method)
        one = wilcoxon(d, zero_method="pratt", alternative="greater", method=method)
    return {
        **out,
        "T": float(two.statistic),
        "p_two": float(two.pvalue),
        "p_lower": float(one.pvalue),
        "r_rb": float((rp - rm) / (rp + rm)),
        "method": method,
    }


def lp_bound(
    weights: Dict[int, float], edges: Sequence[Tuple[int, int]], k: int
) -> Tuple[str, Optional[float]]:
    """LP relaxation of capacitated vertex cover, connectivity dropped.

    min sum w_v x_v  s.t.  y_eu + y_ev = 1,  y_ev <= x_v,  sum_e y_ev <= k x_v,
    0 <= x <= 1, y >= 0. Every MWCCVC cover is feasible here, so the value is a
    lower bound on the optimum. Setting x = 1 relaxes every constraint, and a
    fractional orientation with loads <= k exists iff an integral one does
    (flow integrality), so the LP is infeasible exactly when C = V is.
    """
    nodes = sorted(weights)
    idx = {v: i for i, v in enumerate(nodes)}
    n, m = len(nodes), len(edges)
    nv = n + 2 * m
    c = np.zeros(nv)
    c[:n] = [weights[v] for v in nodes]
    ends = np.array([idx[v] for e in edges for v in e], dtype=int)  # u, v per edge
    ys = n + np.arange(2 * m)
    a_eq = sparse.csr_matrix(
        (np.ones(2 * m), (np.repeat(np.arange(m), 2), ys)), shape=(m, nv)
    )
    r = np.arange(2 * m)
    rows = np.concatenate([r, r, 2 * m + ends, 2 * m + np.arange(n)])
    cols = np.concatenate([ys, ends, ys, np.arange(n)])
    vals = np.concatenate(
        [np.ones(2 * m), -np.ones(2 * m), np.ones(2 * m), -float(k) * np.ones(n)]
    )
    a_ub = sparse.csr_matrix((vals, (rows, cols)), shape=(2 * m + n, nv))
    bounds = [(0, 1)] * n + [(0, None)] * (2 * m)
    res = linprog(
        c,
        A_ub=a_ub,
        b_ub=np.zeros(2 * m + n),
        A_eq=a_eq,
        b_eq=np.ones(m),
        bounds=bounds,
        method="highs",
    )
    if res.status == 0:
        return "optimal", float(res.fun)
    return ("infeasible" if res.status == 2 else f"status{res.status}"), None


def bands_of(n: int) -> List[str]:
    out = [label for label, lo, hi in BANDS if lo <= n <= hi]
    return out + ([POOLED] if n <= 50 else [])


# --------------------------------------------------------------------------
# 2. Inputs
# --------------------------------------------------------------------------
def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes")


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def instance_infeasible(r: dict) -> bool:
    """The flow check of the instance (`instance_feasible`), else the row's `infeasible`.

    In r1_run rows `infeasible` is the arm's own announcement; on an M9 instance
    (flow-infeasible, both witnesses silent) an arm that ends Unresolved would
    otherwise put the instance into the feasible scope. Rows without a flow
    verdict (full_v3 says `unknown:n>200` above n = 200) keep the old reading.
    """
    flow = r.get("instance_feasible")
    return flow == "no" if flow in ("yes", "no") else _truthy(r.get("infeasible"))


def invalid_on_discovered(r: dict) -> bool:
    """Amendment 4: invalid on the final discovered graph, else on the planned one.

    Rows of arms or backends that report no discovered graph leave
    `valid_discovered` empty; a lossless simulator run discovers the planned graph.
    """
    v = r.get("valid_discovered")
    return not _truthy(r["valid"] if v in (None, "") else v)


def read_csvs(paths: Sequence[str]) -> List[dict]:
    rows: List[dict] = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def load_optima(paths: Sequence[str]) -> Dict[Tuple[str, int], float]:
    out: Dict[Tuple[str, int], float] = {}
    for r in read_csvs(paths):
        if r.get("status") == "ok" and _num(r.get("optimum")) is not None:
            key = (r["instance"], int(r["k"]))
            if key in out and out[key] != float(r["optimum"]):
                raise SystemExit(f"optima disagree for {key}")
            out[key] = float(r["optimum"])
    return out


def load_central(paths: Sequence[str]) -> Dict[Tuple[str, int, str], dict]:
    """(instance, k, label) -> central row; duplicate files must agree.

    Rows of one instance that differ in `ga_seed` (hga_ref.py) are runs of one
    reference. As for the arms (prereg section 5), they are averaged per
    instance first: the instance is valid only if every run is, and its weight
    is the mean weight of the runs; `runs` counts them.
    """
    runs: Dict[Tuple[str, int, str], Dict[str, dict]] = defaultdict(dict)
    for r in read_csvs(paths):
        key = (
            r["instance"],
            int(r["k"]),
            r.get("arm") or CENTRAL_LABEL[r["algorithm"]],
        )
        old = runs[key].get(r.get("ga_seed", ""))
        if old is not None and (old["status"], old["weight"]) != (
            r["status"],
            r["weight"],
        ):
            raise SystemExit(f"central files disagree for {key}")
        runs[key][r.get("ga_seed", "")] = r
    out: Dict[Tuple[str, int, str], dict] = {}
    for key, by_seed in runs.items():
        rs_ = [by_seed[s] for s in sorted(by_seed)]
        bad = [x for x in rs_ if not _truthy(x["valid"])]
        out[key] = {
            **rs_[0],
            "runs": len(rs_),
            "valid": str(not bad),
            "status": bad[0]["status"] if bad else rs_[0]["status"],
            "weight": ""
            if bad
            else f"{np.mean([float(x['weight']) for x in rs_]):.10g}",
        }
    return out


def _find(name: str, dirs: Sequence[str]) -> Optional[str]:
    """The one file called `name` under `dirs`, searched recursively.

    Held-out sets keep one directory per cell (heldout.py), so a basename is
    looked up in the whole tree; two different files with one name abort.
    """
    hits = {
        os.path.realpath(os.path.join(root, name))
        for d in dirs
        for root, _, files in os.walk(d)
        if name in files
    }
    if len(hits) > 1:
        raise SystemExit(f"instance name {name} is ambiguous: {sorted(hits)}")
    return hits.pop() if hits else None


def _prepared(path: str, scale: int):
    from ccvc.bb import matrix, sweep

    raw_w, raw_e = matrix.load_instance(path)
    w, e, _ = sweep.prepare(raw_w, raw_e, weight_scale=scale)
    return w, e


LP_FIELDS = (
    "instance",
    "sha256",
    "n",
    "m",
    "k",
    "weight_scale",
    "w_all",
    "lp_status",
    "lp_bound",
)


def instance_info(
    rows: Sequence[dict], dirs: Sequence[str], cache_path: str
) -> Dict[Tuple[str, int], dict]:
    """(instance, k) -> n, m, W(V), LP bound; cached by file sha256, k and scale."""
    cache = {}
    if os.path.exists(cache_path):
        cache = {
            (r["sha256"], r["k"], r["weight_scale"]): r for r in read_csvs([cache_path])
        }
    wanted = sorted(
        {(r["instance"], r["k"], r.get("weight_scale") or "10") for r in rows}
    )
    info: Dict[Tuple[str, int], dict] = {}
    for name, k, scale in wanted:
        path = _find(name, dirs)
        if path is None:
            raise SystemExit(f"instance file {name} not found under {list(dirs)}")
        sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
        hit = cache.get((sha, k, scale))
        if hit is None:
            w, e = _prepared(path, int(scale))
            status, value = lp_bound(w, e, int(k))
            hit = {
                "instance": name,
                "sha256": sha,
                "n": len(w),
                "m": len(e),
                "k": k,
                "weight_scale": scale,
                "w_all": f"{sum(w.values()):.10g}",
                "lp_status": status,
                "lp_bound": "" if value is None else f"{value:.10g}",
            }
            cache[(sha, k, scale)] = hit
        info[(name, int(k))] = {
            "n": int(hit["n"]),
            "m": int(hit["m"]),
            "w_all": float(hit["w_all"]),
            "lp_status": hit["lp_status"],
            "lp": _num(hit["lp_bound"]),
            "path": path,
        }
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    _write(
        cache_path,
        LP_FIELDS,
        sorted(cache.values(), key=lambda r: (r["instance"], r["k"])),
    )
    return info


def published_only(optima, central, info, dataset_dir):
    """Keep exact/central rows only for instances read from the published dataset.

    optima*.csv and central*.csv carry a file name but no file hash, and held-out
    files reuse the published name pattern (n10_m20_s1.txt), so a name join alone
    would attach a development optimum to a held-out instance.
    """
    home = os.path.realpath(dataset_dir) if dataset_dir else None
    keep = {
        key
        for key, it in info.items()
        if home and os.path.dirname(os.path.realpath(it["path"])) == home
    }
    return (
        {k: v for k, v in optima.items() if k in keep},
        {k: v for k, v in central.items() if k[:2] in keep},
    )


def diagnose_central(
    central: Dict[Tuple[str, int, str], dict], info: Dict[Tuple[str, int], dict]
) -> Dict[Tuple[str, int, str], str]:
    """Re-run each invalid centralized solution and name the rule it breaks.

    central.csv keeps only `invalid_solution`; the upstream greedies are seeded
    (seed 42, as exact_compare ran them), so a re-run reproduces the cover and
    the independent validator says which MWCCVC rule rejects it.
    """
    from ccvc.greedy import central as upstream

    algo = {v: k for k, v in GREEDY_LABEL.items()}
    out = {}
    for key, r in central.items():
        if r["status"] != "invalid_solution" or (key[0], key[1]) not in info:
            continue
        if key[2] not in algo:  # hga_ref rows carry the validator's verdict already
            out[key] = f"violations={r.get('violation_kinds', '')}"
            continue
        it = info[(key[0], key[1])]
        w, e = _prepared(it["path"], int(r["weight_scale"]))
        run = upstream.solve(algo[key[2]], list(e), dict(w), key[1], seed=42)
        kinds = "+".join(sorted({v["kind"] for v in run.violations}))
        out[key] = (
            f"{run.status}; vertex_cover={run.vertex_cover}; connected="
            f"{run.connected}; capacity={run.capacity}; |C|-n={len(run.cover) - it['n']}; "
            f"violations={kinds}"
        )
    return out


# --------------------------------------------------------------------------
# 3. Analysis
# --------------------------------------------------------------------------
def _arm_key(arm: str):
    variant, _, sched = arm.partition("/")
    pos = ARM_ORDER.index(variant) if variant in ARM_ORDER else len(ARM_ORDER)
    return (pos, variant, sched != "async", sched)


def _band_key(cond: str, band: str):
    order = [b[0] for b in BANDS] + [POOLED]
    return (cond, order.index(band) if band in order else len(order), band)


def _cond(r: dict) -> str:
    return ",".join(f"{c}={r.get(c, '')}" for c in CONDITION_COLUMNS)


def analyse(
    rows: Sequence[dict],
    info: Dict[Tuple[str, int], dict],
    optima: Dict[Tuple[str, int], float],
    central: Dict[Tuple[str, int, str], dict],
    primary: str = PRIMARY,
    baseline: str = BASELINE,
    boot: int = BOOT,
) -> Dict[str, List[dict]]:
    rows = armnames.canonical_rows([dict(r) for r in rows])
    runs = defaultdict(list)  # (cond, inst, arm) -> rows
    inst_meta: Dict[Tuple[str, str], dict] = {}
    for r in rows:
        cond, inst, k = _cond(r), r["instance"], int(r["k"])
        runs[(cond, inst, f"{r['variant']}/{r['scheduler']}")].append(r)
        n, m = int(r["n"]), int(r["m"])
        scope = (
            "infeasible"
            if instance_infeasible(r)
            else "forced"
            if m == n * k
            else "free"
        )
        meta = inst_meta.setdefault(
            (cond, inst), {"n": n, "m": m, "k": k, "scope": scope}
        )
        if meta["scope"] != scope:
            raise SystemExit(f"rows disagree on the feasibility of {inst} under {cond}")
    arms = sorted({a for _, _, a in runs}, key=_arm_key)

    def ok(r):
        return r["status"] == "ok" and _truthy(r["valid"]) and r["verdict"] == "solved"

    # Arms with the same verdict, weight and cover size on every instance are one arm.
    sig = {a: {} for a in arms}
    for (cond, inst, a), rs in runs.items():
        sig[a][(cond, inst)] = tuple(
            sorted(
                (
                    x["status"],
                    x["verdict"],
                    x["valid"],
                    x["total_weight"],
                    x["cover_size"],
                )
                for x in rs
            )
        )
    reps: List[str] = []
    dup_of: Dict[str, str] = {}
    for a in sorted(arms, key=lambda a: (a != primary, _arm_key(a))):
        # identical wherever `a` ran (a witness-only extra instance of `b` does not split them)
        same = next(
            (b for b in reps if all(sig[b].get(i) == v for i, v in sig[a].items())),
            None,
        )
        if same is None:
            reps.append(a)
        else:
            dup_of[a] = same
    reps.sort(key=_arm_key)
    if primary not in reps:
        raise SystemExit(f"primary arm {primary} has no rows")
    duplicates = [
        {
            "arm": a,
            "display": armnames.display(a),
            "identical_to": b,
            "instances": len(sig[a]),
        }
        for a, b in sorted(dup_of.items(), key=lambda x: _arm_key(x[0]))
    ]

    # Instance inventory per condition and band.
    inventory = defaultdict(Counter)
    for (cond, inst), meta in inst_meta.items():
        for band in bands_of(meta["n"]):
            inventory[(cond, band)][meta["scope"]] += 1
            inventory[(cond, band)]["optimum"] += (inst, meta["k"]) in optima and meta[
                "scope"
            ] == "free"
    instances = [
        {
            "condition": c,
            "band": b,
            "instances": sum(v[s] for s in ("free", "forced", "infeasible")),
            "free_feasible": v["free"],
            "forced_m_eq_nk": v["forced"],
            "infeasible": v["infeasible"],
            "free_with_optimum": v["optimum"],
        }
        for (c, b), v in sorted(inventory.items(), key=lambda kv: _band_key(*kv[0]))
    ]

    # Validity per scope; "correct" = solved and valid on a feasible instance,
    # announced infeasible on an infeasible one.
    tally = defaultdict(Counter)
    for (cond, inst, a), rs in runs.items():
        if a not in reps:
            continue
        meta = inst_meta[(cond, inst)]
        for band in bands_of(meta["n"]):
            t = tally[(cond, band, a, meta["scope"])]
            for x in rs:
                t["runs"] += 1
                t["correct"] += (
                    ok(x)
                    if meta["scope"] != "infeasible"
                    else x["status"] == "infeasible"
                )
                t["false_success"] += x[
                    "verdict"
                ] == "solved" and invalid_on_discovered(x)
                t["unresolved"] += x["status"] == "unresolved"
                t["weight_eq_wall"] += (
                    meta["scope"] == "forced"
                    and ok(x)
                    and float(x["total_weight"]) == info[(inst, meta["k"])]["w_all"]
                )
    validity = []
    for (cond, band, a, scope), t in sorted(
        tally.items(),
        key=lambda kv: (*_band_key(kv[0][0], kv[0][1]), kv[0][3], _arm_key(kv[0][2])),
    ):
        lo, hi = clopper_pearson(t["correct"], t["runs"])
        validity.append(
            {
                "condition": cond,
                "band": band,
                "scope": scope,
                "arm": a,
                "display": armnames.display(a),
                "runs": t["runs"],
                "correct": t["correct"],
                "rate": t["correct"] / t["runs"],
                "cp_lo": lo,
                "cp_hi": hi,
                "unresolved": t["unresolved"],
                "false_success": t["false_success"],
                "fs_upper95": upper_one_sided(t["false_success"], t["runs"]),
                "weight_eq_wall": t["weight_eq_wall"] if scope == "forced" else "",
            }
        )

    # Centralized references on forced instances (the Table 3 question).
    forced_central = Counter()
    for (cond, inst), meta in inst_meta.items():
        if meta["scope"] != "forced":
            continue
        for label in CENTRAL_LABEL.values():
            c = central.get((inst, meta["k"], label))
            if c is not None:
                forced_central[(cond, label, "runs")] += 1
                forced_central[(cond, label, "valid")] += _truthy(c["valid"])
    forced = [r for r in validity if r["scope"] == "forced"]
    for (cond, label, what), v in sorted(forced_central.items()):
        if what == "runs":
            x = forced_central[(cond, label, "valid")]
            lo, hi = clopper_pearson(x, v)
            forced.append(
                {
                    "condition": cond,
                    "band": "all with central run",
                    "scope": "forced",
                    "arm": label,
                    "display": armnames.display(label),
                    "runs": v,
                    "correct": x,
                    "rate": x / v,
                    "cp_lo": lo,
                    "cp_hi": hi,
                }
            )

    # Quality on the common valid basis of free feasible instances.
    quality, tests = [], []
    groups = defaultdict(set)
    for (cond, inst), meta in inst_meta.items():
        if meta["scope"] == "free":
            for band in bands_of(meta["n"]):
                groups[(cond, band)].add(inst)
    for (cond, band), insts in sorted(groups.items(), key=lambda kv: _band_key(*kv[0])):
        present = [a for a in reps if any((cond, i, a) in runs for i in insts)]
        basis = sorted(
            i
            for i in insts
            if all(
                (cond, i, a) in runs and all(ok(x) for x in runs[(cond, i, a)])
                for a in present
            )
        )
        k_of = {i: inst_meta[(cond, i)]["k"] for i in basis}
        weight = {
            (a, i): float(
                np.mean([float(x["total_weight"]) for x in runs[(cond, i, a)]])
            )
            for a in present
            for i in basis
        }
        refs = {
            "optimum": {i: optima.get((i, k_of[i])) for i in basis},
            "W(V)": {i: info[(i, k_of[i])]["w_all"] for i in basis},
            "LP": {i: info[(i, k_of[i])]["lp"] for i in basis},
        }
        cw = {}
        for label in CENTRAL_LABEL.values():
            refs[label] = {}
            for i in basis:
                c = central.get((i, k_of[i], label))
                refs[label][i] = (
                    float(c["weight"])
                    if c is not None and _truthy(c["valid"])
                    else None
                )
                if refs[label][i] is not None:
                    cw[(label, i)] = refs[label][i]
        subjects = [(a, weight) for a in present] + [
            (label, cw) for label in CENTRAL_LABEL.values()
        ]
        for ref_name, ref in refs.items():
            for a, wmap in subjects:
                # central heuristics are scored against the three absolute references only
                if a in CENTRAL_LABEL.values() and ref_name not in (
                    "optimum",
                    "W(V)",
                    "LP",
                ):
                    continue
                vals = [
                    wmap[(a, i)] / ref[i] for i in basis if ref[i] and (a, i) in wmap
                ]
                if vals:
                    quality.append(
                        {
                            "condition": cond,
                            "band": band,
                            "arm": a,
                            "display": armnames.display(a),
                            "reference": ref_name,
                            "basis": len(basis),
                            **describe(vals, boot),
                        }
                    )
        lp_opt = [
            refs["LP"][i] / refs["optimum"][i]
            for i in basis
            if refs["optimum"][i] and refs["LP"][i]
        ]
        if lp_opt:
            quality.append(
                {
                    "condition": cond,
                    "band": band,
                    "arm": "LP-bound",
                    "display": "LP bound",
                    "reference": "optimum",
                    "basis": len(basis),
                    **describe(lp_opt, boot),
                }
            )

        if band == POOLED or primary not in present:
            continue
        ref = {i: refs["optimum"][i] or refs["LP"][i] for i in basis}
        pairs = [i for i in basis if ref[i]]
        n_opt = sum(1 for i in pairs if refs["optimum"][i])
        block = []
        for a in present:
            if a == primary:
                continue
            res = paired_test(
                [weight[(primary, i)] / ref[i] for i in pairs],
                [weight[(a, i)] / ref[i] for i in pairs],
            )
            block.append(
                {
                    "condition": cond,
                    "band": band,
                    "primary": primary,
                    "other": a,
                    "display": armnames.display(a),
                    "ref_optimum": n_opt,
                    "ref_lp": len(pairs) - n_opt,
                    **res,
                }
            )
        for row, p in zip(block, holm([b["p_two"] for b in block])):
            row["p_two_holm_band"] = p
        tests.extend(block)

    # Prereg H-b: primary vs the named baseline, one-sided, Holm over bands.
    hb = defaultdict(list)
    for t in tests:
        if t["other"] == baseline:
            hb[t["condition"]].append(t)
    for block in hb.values():
        for t, p in zip(block, holm([t["p_lower"] for t in block])):
            t["hb_p_lower_holm_bands"] = p
    return {
        "instances": instances,
        "duplicates": duplicates,
        "validity": validity,
        "forced": forced,
        "quality": quality,
        "tests": tests,
    }


def central_validity(
    central: Dict[Tuple[str, int, str], dict],
    optima: Dict[Tuple[str, int], float],
    diagnosis: Dict[Tuple[str, int, str], str],
) -> List[dict]:
    """Per heuristic, on the instances with a proven optimum: valid or why not."""
    out = []
    for label in CENTRAL_LABEL.values():
        keys = [key for key in central if key[2] == label and key[:2] in optima]
        if not keys:
            continue
        tally = Counter()
        for key in keys:
            r = central[key]
            forced = int(r["m"]) == int(r["n"]) * key[1]
            if _truthy(r["valid"]):
                tally["valid"] += 1
                continue
            tally[
                f"{r['status']} on {'m = nk' if forced else 'm < nk'} :: "
                f"{diagnosis.get(key, 'not re-run')}"
            ] += 1
        out.append(
            {
                "arm": label,
                "display": armnames.display(label),
                "reason": "valid",
                "count": tally.pop("valid", 0),
                "of": len(keys),
            }
        )
        out += [
            {
                "arm": label,
                "display": armnames.display(label),
                "reason": k,
                "count": v,
                "of": len(keys),
            }
            for k, v in sorted(tally.items())
        ]
    # The paired basis of the published Table 3 required all three to be valid.
    insts = {key[:2]: central[key] for key in central if key[:2] in optima}
    both = [
        key
        for key, r in insts.items()
        if all(
            _truthy(central.get((*key, lab), {}).get("valid"))
            for lab in GREEDY_LABEL.values()
        )
    ]
    n_forced = sum(
        int(insts[key]["m"]) == int(insts[key]["n"]) * key[1] for key in both
    )
    out.append(
        {
            "arm": "all three",
            "display": "all three",
            "reason": f"all three valid ({n_forced} of them m = nk)",
            "count": len(both),
            "of": len(insts),
        }
    )
    return out


# --------------------------------------------------------------------------
# 4. Output
# --------------------------------------------------------------------------
def _fmt(v):
    if isinstance(v, (float, np.floating)):
        return "" if v != v else f"{v:.6g}"
    return v


def _write(path: str, fields: Sequence[str], rows: Sequence[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k, "")) for k in fields})


def _md(headers: Sequence[str], rows: Sequence[Sequence]) -> List[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return out + ["| " + " | ".join(str(_fmt(c)) for c in r) + " |" for r in rows]


def summary(tables: Dict[str, List[dict]], meta: dict) -> str:
    L = [
        "# R1 statistics from run rows",
        "",
        "Generated by `python3 -m ccvc.bb.revision_stats`; every number below is in the CSV "
        "files next to this one. Unit = instance; ratios are cover weight over a reference "
        f"external to the arms; bootstrap {meta['boot']} resamples, seed {BOOT_SEED}, percentile "
        "95% interval of the mean. Instances with m = nk (C = V forced) and provably infeasible "
        "instances are excluded from every quality number and test.",
        "",
        "Band tables: `test pairs/zeros` = instances in the paired Wilcoxon signed-rank test "
        "(Pratt zeros) between the primary arm and that arm, on the ratio to the proven optimum "
        "where one exists and to the LP bound otherwise; `p Holm (band)` = two-sided p, Holm "
        "over the comparisons of that band; `r_rb` = matched-pairs rank-biserial correlation, "
        "positive when the primary arm is lighter. Centralized rows are references and are "
        "not tested.",
        "",
        f"Inputs: {meta['n_rows']} rows from {len(meta['rows'])} files; code fingerprints "
        f"{', '.join(meta['fingerprints'])}; primary arm `{meta['primary']}`, H-b baseline "
        f"`{meta['baseline']}`.",
        "",
        "## Instances per band",
        "",
    ]
    L += _md(
        [
            "condition",
            "band",
            "instances",
            "free feasible",
            "m = nk",
            "infeasible",
            "free with optimum",
        ],
        [
            [
                r["condition"],
                r["band"],
                r["instances"],
                r["free_feasible"],
                r["forced_m_eq_nk"],
                r["infeasible"],
                r["free_with_optimum"],
            ]
            for r in tables["instances"]
        ],
    )
    L += ["", "## Checks", ""] + [f"- {c}" for c in meta["checks"]]
    L += ["", "## Arms with identical outputs (reported once)", ""]
    L += (
        _md(
            ["arm", "identical to", "instances compared"],
            [
                [d["arm"], d["identical_to"], d["instances"]]
                for d in tables["duplicates"]
            ],
        )
        if tables["duplicates"]
        else ["none"]
    )
    L += [
        "",
        "## Development ranking: mean ratio to the proven optimum, pooled n <= 50",
        "",
    ]
    rank = sorted(
        (
            q
            for q in tables["quality"]
            if q["band"] == POOLED and q["reference"] == "optimum"
        ),
        key=lambda q: q["mean"],
    )
    L += _md(
        ["arm", "n", "mean", "95% CI", "median [IQR]", "SD"],
        [
            [
                q["arm"],
                q["n"],
                f"{q['mean']:.4f}",
                f"[{q['ci_lo']:.4f}, {q['ci_hi']:.4f}]",
                f"{q['median']:.4f} [{q['q1']:.4f}, {q['q3']:.4f}]",
                f"{q['sd']:.4f}",
            ]
            for q in rank
        ],
    )
    for cond, band in sorted(
        {(t["condition"], t["band"]) for t in tables["quality"]},
        key=lambda cb: _band_key(*cb),
    ):
        qs = [
            q for q in tables["quality"] if q["condition"] == cond and q["band"] == band
        ]
        basis = qs[0]["basis"]
        L += [
            "",
            f"## {cond}, n in {band}: {basis} instances in the common valid basis",
            "",
        ]
        by = defaultdict(dict)
        for q in qs:
            by[q["arm"]][q["reference"]] = q
        ts = {
            t["other"]: t
            for t in tables["tests"]
            if t["condition"] == cond and t["band"] == band
        }
        refs = [
            r for r in ("optimum", "LP", "W(V)") if any(r in v for v in by.values())
        ]
        rows = []
        for a, v in by.items():
            cells = [a]
            for r in refs:
                q = v.get(r)
                cells.append(
                    ""
                    if q is None
                    else f"{q['mean']:.3f} [{q['ci_lo']:.3f}, {q['ci_hi']:.3f}] (n={q['n']})"
                )
            t = ts.get(a)
            cells += [
                "" if t is None else f"{t['n_pairs']}/{t['n_zero']}",
                "" if t is None else f"{t['p_two_holm_band']:.3g}",
                "" if t is None else f"{t['r_rb']:+.2f}",
            ]
            rows.append(cells)
        L += _md(
            ["arm"]
            + [f"ratio to {r}, mean [95% CI]" for r in refs]
            + ["test pairs/zeros", "p Holm (band)", "r_rb"],
            rows,
        )
    hb = [t for t in tables["tests"] if "hb_p_lower_holm_bands" in t]
    L += [
        "",
        f"## Prereg H-b: `{meta['primary']}` lower than `{meta['baseline']}` "
        "(one-sided Wilcoxon, Pratt, Holm over bands)",
        "",
    ]
    L += _md(
        [
            "condition",
            "band",
            "pairs",
            "zeros",
            "ref optimum/LP",
            "p one-sided",
            "p Holm",
            "r_rb",
            "method",
        ],
        [
            [
                t["condition"],
                t["band"],
                t["n_pairs"],
                t["n_zero"],
                f"{t['ref_optimum']}/{t['ref_lp']}",
                f"{t['p_lower']:.3g}",
                f"{t['hb_p_lower_holm_bands']:.3g}",
                f"{t['r_rb']:+.2f}",
                t["method"],
            ]
            for t in hb
        ],
    )
    L += ["", "## Validity on free feasible instances (worst per band)", ""]
    worst = [v for v in tables["validity"] if v["scope"] == "free" and v["rate"] < 1]
    L += (
        _md(
            ["condition", "band", "arm", "correct/runs", "95% CP", "unresolved"],
            [
                [
                    v["condition"],
                    v["band"],
                    v["arm"],
                    f"{v['correct']}/{v['runs']}",
                    f"[{v['cp_lo']:.3f}, {v['cp_hi']:.3f}]",
                    v["unresolved"],
                ]
                for v in worst
            ],
        )
        if worst
        else ["Every arm is valid on every free feasible run."]
    )
    fs = sum(v["false_success"] for v in tables["validity"])
    runs = sum(v["runs"] for v in tables["validity"] if v["band"] != POOLED)
    L += [
        "",
        f"False successes (solved verdict rejected by the validator on the final discovered "
        f"graph, Amendment 4, or on the planned graph for rows without that reading): {fs} "
        f"over {runs} runs "
        "of the representative arms; per-arm one-sided 95% upper bounds in validity.csv.",
    ]
    inf = [
        v
        for v in tables["validity"]
        if v["scope"] == "infeasible" and v["band"] != POOLED
    ]
    L += [
        f"Infeasible instances announced as infeasible: {sum(v['correct'] for v in inf)} of "
        f"{sum(v['runs'] for v in inf)} runs."
    ]
    L += ["", "## m = nk instances (C = V forced): validity", ""]
    L += _md(
        ["condition", "band", "arm", "correct/runs", "95% CP", "weight = W(V)"],
        [
            [
                f["condition"],
                f["band"],
                f["arm"],
                f"{f['correct']}/{f['runs']}",
                f"[{f['cp_lo']:.3f}, {f['cp_hi']:.3f}]",
                f.get("weight_eq_wall", ""),
            ]
            for f in tables["forced"]
            if f["band"] in ("all with central run",)
            or (f["band"] != POOLED and f["correct"] < f["runs"])
        ],
    )
    L += [
        "",
        "Rows not listed above are correct on every m = nk run (see forced.csv).",
        "",
        "## Table 3 question: centralized heuristics on instances with a proven optimum",
        "",
    ]
    L += _md(
        ["heuristic", "count", "of", "outcome"],
        [[c["display"], c["count"], c["of"], c["reason"]] for c in tables["central"]],
    )
    return "\n".join(L) + "\n"


FIELDS = {
    "instances": (
        "condition",
        "band",
        "instances",
        "free_feasible",
        "forced_m_eq_nk",
        "infeasible",
        "free_with_optimum",
    ),
    "duplicates": ("arm", "display", "identical_to", "instances"),
    "validity": (
        "condition",
        "band",
        "scope",
        "arm",
        "display",
        "runs",
        "correct",
        "rate",
        "cp_lo",
        "cp_hi",
        "unresolved",
        "false_success",
        "fs_upper95",
        "weight_eq_wall",
    ),
    "forced": (
        "condition",
        "band",
        "scope",
        "arm",
        "display",
        "runs",
        "correct",
        "rate",
        "cp_lo",
        "cp_hi",
        "unresolved",
        "false_success",
        "weight_eq_wall",
    ),
    "quality": (
        "condition",
        "band",
        "arm",
        "display",
        "reference",
        "basis",
        "n",
        "median",
        "q1",
        "q3",
        "mean",
        "sd",
        "ci_lo",
        "ci_hi",
    ),
    "tests": (
        "condition",
        "band",
        "primary",
        "other",
        "display",
        "n_pairs",
        "n_zero",
        "ref_optimum",
        "ref_lp",
        "T",
        "p_two",
        "p_two_holm_band",
        "p_lower",
        "hb_p_lower_holm_bands",
        "r_rb",
        "method",
    ),
    "central": ("arm", "display", "reason", "count", "of"),
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--rows", nargs="+", default=[os.path.join(PROJECT, p) for p in DEFAULT_ROWS]
    )
    ap.add_argument(
        "--optima",
        nargs="*",
        default=[os.path.join(PROJECT, p) for p in DEFAULT_OPTIMA],
    )
    ap.add_argument(
        "--central",
        nargs="*",
        default=[os.path.join(PROJECT, p) for p in DEFAULT_CENTRAL],
    )
    ap.add_argument(
        "--instance-dir",
        action="append",
        default=None,
        help="directory holding the instance files (repeatable); "
        "default: the Dagdeviren dataset",
    )
    ap.add_argument("--primary", default=PRIMARY)
    ap.add_argument("--baseline", default=BASELINE)
    ap.add_argument("--out", default=os.path.join(PROJECT, DEFAULT_OUT))
    a = ap.parse_args(argv)
    if any("_archive" in p for p in a.rows):
        raise SystemExit("rows under _archive are superseded measurements; not read")
    if a.instance_dir is None:
        from ccvc.bb import matrix

        a.instance_dir = [matrix.dataset_dir()]
    rows = read_csvs(a.rows)
    os.makedirs(a.out, exist_ok=True)
    info = instance_info(rows, a.instance_dir, os.path.join(a.out, "lp_bounds.csv"))
    from ccvc.bb import matrix

    optima, central = published_only(
        load_optima(a.optima), load_central(a.central), info, matrix.dataset_dir()
    )
    tables = analyse(rows, info, optima, central, a.primary, a.baseline)
    tables["central"] = central_validity(
        central, optima, diagnose_central(central, info)
    )

    checks = []
    bad_lp = [
        i
        for (i, k), o in optima.items()
        if (i, k) in info
        and info[(i, k)]["lp"] is not None
        and info[(i, k)]["lp"] > o * (1 + 1e-9)
    ]
    n_cmp = sum(1 for key in optima if key in info and info[key]["lp"] is not None)
    checks.append(
        f"LP bound <= proven optimum on {n_cmp - len(bad_lp)} of {n_cmp} instances"
        + (f"; VIOLATED on {bad_lp}" if bad_lp else "")
    )
    flag = {(r["instance"], int(r["k"])): instance_infeasible(r) for r in rows}
    disagree = sorted(
        i
        for (i, k), inf in flag.items()
        if inf != (info[(i, k)]["lp_status"] == "infeasible")
    )
    checks.append(
        f"rows' feasibility (flow check, else `infeasible`) agrees with LP infeasibility on {len(flag) - len(disagree)} "
        f"of {len(flag)} instances" + (f"; disagree on {disagree}" if disagree else "")
    )
    forced_ok = [
        v for v in tables["validity"] if v["scope"] == "forced" and v["band"] != POOLED
    ]
    eq, tot = sum(v["weight_eq_wall"] for v in forced_ok), sum(
        v["correct"] for v in forced_ok
    )
    checks.append(
        f"on m = nk instances {eq} of {tot} valid runs have weight exactly W(V)"
    )
    checks.append(
        "runs per (condition, instance, arm): "
        + ", ".join(
            f"{k} run(s) x {v}"
            for k, v in sorted(
                Counter(
                    Counter(
                        (_cond(r), r["instance"], r["variant"], r["scheduler"])
                        for r in rows
                    ).values()
                ).items()
            )
        )
    )

    for name, fields in FIELDS.items():
        _write(os.path.join(a.out, f"{name}.csv"), fields, tables[name])
    meta = {
        "rows": a.rows,
        "n_rows": len(rows),
        "primary": a.primary,
        "baseline": a.baseline,
        "boot": BOOT,
        "checks": checks,
        "fingerprints": sorted({r.get("code_fingerprint", "") for r in rows}),
    }
    text = summary(tables, meta)
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text[text.index("## Checks") : text.index("## Arms")])
    print(text[text.index("## Table 3 question") :])
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
