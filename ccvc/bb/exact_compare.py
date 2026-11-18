#!/usr/bin/env python3
"""Compare the BB-CVC arms against proven optima and the centralized greedies.

WHY THIS MODULE EXISTS. `sweep.py` already writes an `exact_weight` column, but
it gives up at `exact_max_n = 18`, so in `sweep_small_full_k6_clean_v2` only the
n = 10 and n = 15 instances carry an optimum and the "weight / optimum" column
of the comparison table is an average over 15 of 39 instances. Measured here,
the exact solver in `ccvc/central.py` finishes every feasible instance of the
small group at k = 6 in well under a second, and the whole n = 50 group in
seconds, because it seeds branch-and-bound with the best of the three greedy
covers and prunes a branch as soon as an excluded vertex has an excluded decided
neighbour. The 18-vertex ceiling was a guess, not a measurement. This module
runs the solver once, stores the optima, and joins them onto the sweep rows.

THE CAPACITY k IS PART OF THE INSTANCE, NOT A DETAIL. The group's own published
run over the same Dagdeviren files (`MWCCVC-GNN-yayin/data/raw/small.json`)
optimizes k per instance for best weight, so its 130 small optima sit at k
between 3 and 18 and only one of the 39 instances our sweeps use lands on k = 6.
An optimum at k = 9 is a lower bound for an optimum at k = 6 and dividing one
arm's k = 6 weight by it would understate the ratio. The two sources are
therefore kept in the same inventory but joined on (instance, k), never pooled;
`import-upstream` records theirs, `optima` measures ours.

UNITS. `sweep.prepare` quantizes the real-valued benchmark weights to integers
with `weight_scale = 10`, and the sweep's `total_weight` is in those units. The
solver here is run on exactly the same quantized instance, so `optimum` is in
the same units and the ratio is the ratio of one problem, not of two. The
original-scale value is kept alongside as `optimum_unscaled` for readers who
compare against a published table.

Commands:
    optima          measure optima with `ccvc.central.solve_exact` at one k
    central         run the pinned upstream GCCVC/GRCCVC/GWCCVC at the same k
    import-upstream record the group's published optima at their own k
    table           join optima onto sweep rows and write the LaTeX table
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import armnames, matrix, sweep, validate

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: One arm per Phase-1 mechanism, plus the Trickle pacing of the annealing arm,
#: which is the only family member whose message count differs from its sibling
#: while its weight does not. `MIS-Connector-TreeAgg` and
#: `WuLi-Dominating-Chunked` are omitted because they are weight-identical to
#: their family head in every sweep measured so far, so they would add two rows
#: that repeat two others exactly.
REPRESENTATIVE_ARMS: Tuple[str, ...] = (
    "GHS-MST-Backbone",
    "Anneal-Local",
    "Anneal-Trickle",
    "DFS-Spanning-Backbone",
    "MIS-Connector-Backbone",
    "WuLi-Dominating-Exact",
)

#: The distributed greedy baselines, named by the score they maximise.
GREEDY_ARMS: Tuple[str, ...] = (
    "Greedy-Degree-Backbone",
    "Greedy-Ratio-Backbone",
    "Greedy-Weight-Backbone",
)

#: The centralized references, run here rather than read from a sweep.
CENTRAL_ALGORITHMS: Tuple[str, ...] = ("gccvc", "grccvc", "gwccvc")

CENTRAL_LABEL: Dict[str, str] = {
    "gccvc": "Greedy-Degree-Upstream",
    "grccvc": "Greedy-Ratio-Upstream",
    "gwccvc": "Greedy-Weight-Upstream",
}

OPTIMA_FIELDS = ("instance", "n", "m", "k", "optimum", "method", "seconds",
                 "source", "optimum_unscaled", "weight_scale", "cover_size",
                 "status", "graph_connected", "components")

CENTRAL_FIELDS = ("instance", "n", "m", "k", "algorithm", "arm", "weight",
                  "weight_unscaled", "weight_scale", "cover_size", "valid",
                  "status", "seconds", "source")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _f(row: dict, key: str) -> Optional[float]:
    raw = (row.get(key) or "").strip()
    if raw in ("", "None", "n/a", "NA", "nan"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _truthy(row: dict, key: str) -> bool:
    return (row.get(key) or "").strip().lower() in ("1", "true", "yes")


def _write_csv(path: str, fields: Sequence[str], rows: Sequence[dict]) -> None:
    """Write through a temporary file: an interrupted run must not truncate."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in fields})
    os.replace(tmp, path)


def _read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _cells(groups: Sequence[str], max_n: Optional[int]) -> List[matrix.Cell]:
    wanted = set(groups)
    out = [c for c in matrix.feasible_cells() if c.group in wanted]
    if max_n is not None:
        out = [c for c in out if c.n <= max_n]
    return out


# --------------------------------------------------------------------------
# 1. measure optima with the project's own exact solver
# --------------------------------------------------------------------------
def run_optima(cells: Sequence[matrix.Cell], k: int, *, max_seeds: Optional[int],
               time_limit_s: float, dataset_dir: Optional[str] = None,
               progress: bool = True) -> List[dict]:
    """Solve every instance of `cells` exactly at capacity `k`.

    A timed-out or infeasible instance is recorded with its reason rather than
    dropped: a missing row and a row that says "no optimum exists at this k"
    are different facts and the table has to be able to tell them apart.
    """
    from ccvc import bridge, central

    instances = sweep.dataset_instances(cells, max_seeds=max_seeds,
                                        directory=dataset_dir)
    rows: List[dict] = []
    for i, inst in enumerate(instances, 1):
        name = os.path.basename(inst.path)
        graph = validate.make_graph(list(inst.edges), k, dict(inst.weights))
        components = len(bridge.graph_components(graph))
        t0 = time.perf_counter()
        status = "ok"
        optimum: Optional[float] = None
        cover_size = ""
        try:
            result = central.solve_exact(graph, max_n=None,
                                         time_limit_s=time_limit_s, strict=False)
        except Exception as exc:                      # noqa: BLE001
            elapsed = time.perf_counter() - t0
            status = f"error:{type(exc).__name__}"
            result = None
        else:
            elapsed = time.perf_counter() - t0
            if not result.feasible:
                status = "infeasible_at_k"
            elif result.timed_out:
                status = "timed_out"
            elif not result.valid:
                status = "invalid"
            else:
                optimum = round(sum(float(inst.weights[v]) for v in result.cover), 6)
                cover_size = len(result.cover)
        scale = inst.adaptation.weight_scale
        rows.append({
            "instance": name,
            "n": inst.cell.n,
            "m": inst.cell.m,
            "k": k,
            "optimum": "" if optimum is None else f"{optimum:.6g}",
            "method": "branch-and-bound (ccvc.central.solve_exact), per component",
            "seconds": f"{elapsed:.4f}",
            "source": "MDS_SKYFABRIC/ccvc/central.py",
            "optimum_unscaled": "" if optimum is None else f"{optimum / scale:.6g}",
            "weight_scale": scale,
            "cover_size": cover_size,
            "status": status,
            "graph_connected": components == 1,
            "components": components,
        })
        if progress:
            last = rows[-1]
            print(f"[{i}/{len(instances)}] {name} k={k} "
                  f"{last['status']} w={last['optimum'] or '-'} "
                  f"{elapsed:.2f}s", flush=True)
    return rows


# --------------------------------------------------------------------------
# 2. run the pinned upstream centralized greedies at the same k
# --------------------------------------------------------------------------
def run_central(cells: Sequence[matrix.Cell], k: int, *,
                max_seeds: Optional[int], dataset_dir: Optional[str] = None,
                seed: int = 42, progress: bool = True) -> List[dict]:
    """The group's own GCCVC/GRCCVC/GWCCVC on the same quantized instances.

    This is the pinned checkout under `external_sources/MWCCVC`, executed by
    `ccvc.greedy.central`, not a reimplementation: it is the only way to put a
    centralized number next to a distributed one at the SAME k, because the
    group's published per-instance results were measured at a per-instance
    optimized k.
    """
    from ccvc.greedy import central as upstream

    instances = sweep.dataset_instances(cells, max_seeds=max_seeds,
                                        directory=dataset_dir)
    rows: List[dict] = []
    for i, inst in enumerate(instances, 1):
        name = os.path.basename(inst.path)
        scale = inst.adaptation.weight_scale
        for algorithm in CENTRAL_ALGORITHMS:
            t0 = time.perf_counter()
            try:
                run = upstream.solve(algorithm, list(inst.edges),
                                     dict(inst.weights), k, seed=seed)
            except Exception as exc:                  # noqa: BLE001
                rows.append({
                    "instance": name, "n": inst.cell.n, "m": inst.cell.m, "k": k,
                    "algorithm": algorithm, "arm": CENTRAL_LABEL[algorithm],
                    "weight": "", "weight_unscaled": "", "weight_scale": scale,
                    "cover_size": "", "valid": False,
                    "status": f"error:{type(exc).__name__}",
                    "seconds": f"{time.perf_counter() - t0:.4f}",
                    "source": f"external_sources/MWCCVC@{upstream.REVISION[:12]}",
                })
                continue
            elapsed = time.perf_counter() - t0
            rows.append({
                "instance": name, "n": inst.cell.n, "m": inst.cell.m, "k": k,
                "algorithm": algorithm, "arm": CENTRAL_LABEL[algorithm],
                "weight": f"{run.total_weight:.6g}" if run.valid else "",
                "weight_unscaled": (f"{run.total_weight / scale:.6g}"
                                    if run.valid else ""),
                "weight_scale": scale,
                "cover_size": len(run.cover) if run.valid else "",
                "valid": run.valid, "status": run.status,
                "seconds": f"{elapsed:.4f}",
                "source": f"external_sources/MWCCVC@{upstream.REVISION[:12]}",
            })
        if progress:
            print(f"[{i}/{len(instances)}] central {name} k={k}", flush=True)
    return rows


# --------------------------------------------------------------------------
# 3. record the group's published optima, at their own k
# --------------------------------------------------------------------------
def import_upstream_optima(json_paths: Sequence[str]) -> List[dict]:
    """Read `graphAnalysis.graphs[*].results.exact` out of a preset-run JSON.

    Only a run that finished carries an optimum. The medium and large presets
    gave the branch-and-bound a time budget of twice the longest non-exact
    method and every one of them stopped on that budget, so their "exact" entry
    is the best incumbent, which is usually just the GRCCVC seed. Those rows are
    recorded with `status = timed_out` and no optimum.
    """
    import json

    rows: List[dict] = []
    for path in json_paths:
        with open(path, encoding="utf-8") as fh:
            document = json.load(fh)
        analysis = document.get("graphAnalysis") or {}
        for graph in analysis.get("graphs") or []:
            result = (graph.get("results") or {}).get("exact")
            name = graph.get("file", "")
            scale = graph.get("scale") or {}
            k = graph.get("capacityK")
            if not result:
                rows.append({
                    "instance": name, "n": scale.get("n", ""),
                    "m": scale.get("m", ""), "k": k, "optimum": "",
                    "method": "branch-and-bound (upstream backend/app/algorithms.py)",
                    "seconds": "", "source": os.path.relpath(path, PROJECT)
                    if path.startswith(PROJECT) else path,
                    "optimum_unscaled": "", "weight_scale": 1, "cover_size": "",
                    "status": "not_run", "graph_connected": "", "components": "",
                })
                continue
            verification = result.get("verification") or {}
            timed_out = bool(result.get("timedOut"))
            valid = bool(verification.get("isValid"))
            weight = verification.get("totalWeight")
            status = ("timed_out" if timed_out
                      else "ok" if valid else "invalid")
            rows.append({
                "instance": name,
                "n": scale.get("n", ""),
                "m": scale.get("m", ""),
                "k": k,
                "optimum": "" if status != "ok" else f"{float(weight):.6g}",
                "method": "branch-and-bound (upstream backend/app/algorithms.py)"
                          + ("" if status == "ok" else ", stopped on time budget"),
                "seconds": (f"{float(result.get('time', 0.0)) / 1000.0:.4f}"
                            if result.get("time") is not None else ""),
                "source": os.path.relpath(path, PROJECT)
                if path.startswith(PROJECT) else path,
                "optimum_unscaled": "" if status != "ok" else f"{float(weight):.6g}",
                "weight_scale": 1,
                "cover_size": verification.get("coverSize", ""),
                "status": status,
                "graph_connected": (verification.get("numComponents") == 1
                                    if verification.get("numComponents") is not None
                                    else ""),
                "components": verification.get("numComponents", ""),
            })
    return rows


# --------------------------------------------------------------------------
# 4. join and tabulate
# --------------------------------------------------------------------------
@dataclass
class ArmStats:
    arm: str
    valid: int
    runs: int
    ratios: List[float]
    at_optimum: int

    @property
    def mean(self) -> Optional[float]:
        return statistics.fmean(self.ratios) if self.ratios else None

    @property
    def worst(self) -> Optional[float]:
        return max(self.ratios) if self.ratios else None


def load_sweep_rows(paths: Sequence[str]) -> List[dict]:
    rows: List[dict] = []
    for path in paths:
        for row in _read_csv(path):
            row["_file"] = os.path.relpath(path, PROJECT)
            rows.append(row)
    return armnames.canonical_rows(rows)


def optimum_index(rows: Sequence[dict]) -> Dict[Tuple[str, int], float]:
    """(instance, k) -> optimum, in the sweep's quantized weight units."""
    index: Dict[Tuple[str, int], float] = {}
    for row in rows:
        if (row.get("status") or "") != "ok":
            continue
        value = _f(row, "optimum")
        if value is None:
            continue
        try:
            key = (row["instance"], int(float(row["k"])))
        except (KeyError, ValueError):
            continue
        index[key] = value
    return index


def forced_index(rows: Sequence[dict]) -> set:
    """Instances whose optimum is the whole vertex set, so no arm can choose.

    MEASURED at k = 6: the benchmark's m/n = 6 cells have m = nk exactly, the
    counting bound then forces every vertex into the cover, and all 17 arms and
    all three centralized references return the same weight and hit the optimum
    on all nine of those instances. Counting those as successes would credit an
    arm for a decision it never made, so the "at the optimum" column is taken
    over the instances where a choice exists.
    """
    out = set()
    for row in rows:
        if (row.get("status") or "") != "ok":
            continue
        try:
            if int(float(row["cover_size"])) >= int(float(row["n"])):
                out.add(row["instance"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def solved(row: dict) -> bool:
    return _truthy(row, "valid") and (row.get("verdict") or "") == "solved"


def collect(sweep_rows: Sequence[dict], optima: Dict[Tuple[str, int], float],
            arms: Sequence[str], central_rows: Sequence[dict] = (),
            forced: Sequence[str] = ()) -> Tuple[Dict[str, ArmStats], dict]:
    """Per arm, the ratio to the optimum over the PAIRED instance basis.

    The basis is the set of instances for which an optimum is known at the
    sweep's own k AND every row the table will print returned a valid cover,
    the centralized references included when they are shown. An average taken
    over each arm's own successes would reward an arm for failing on exactly
    the instances it finds hard, which is the failure mode the project's
    evidence rule exists to stop, and mixing a 32-instance distributed mean
    with a 28-instance centralized mean in one column is the same error wearing
    a different hat.
    """
    keep = [r for r in sweep_rows if r["variant"] in set(arms)]
    labels = sorted({f"{r['variant']}/{r['scheduler']}" for r in keep})
    has_optimum = {r["instance"] for r in keep
                   if (r["instance"], int(float(r["k"]))) in optima}
    got: Dict[str, set] = {}
    for r in keep:
        if solved(r) and r["instance"] in has_optimum:
            got.setdefault(r["instance"], set()).add(f"{r['variant']}/{r['scheduler']}")
    basis = {i for i, names in got.items() if len(names) == len(labels)}

    central_labels = {row.get("arm") or CENTRAL_LABEL.get(row.get("algorithm", ""), "?")
                      for row in central_rows}
    if central_rows:
        central_ok: Dict[str, set] = {}
        for row in central_rows:
            if not _truthy(row, "valid"):
                continue
            label = row.get("arm") or CENTRAL_LABEL.get(row.get("algorithm", ""), "?")
            central_ok.setdefault(row["instance"], set()).add(label)
        basis = {i for i in basis
                 if len(central_ok.get(i, set())) == len(central_labels)}

    stats: Dict[str, ArmStats] = {
        label: ArmStats(label, 0, 0, [], 0) for label in labels}
    for r in keep:
        if r["instance"] not in has_optimum:
            continue
        label = f"{r['variant']}/{r['scheduler']}"
        stats[label].runs += 1
        if solved(r):
            stats[label].valid += 1
        if r["instance"] not in basis or not solved(r):
            continue
        weight = _f(r, "total_weight")
        opt = optima[(r["instance"], int(float(r["k"])))]
        if weight is None or opt <= 0:
            continue
        ratio = weight / opt
        stats[label].ratios.append(ratio)
        if ratio <= 1.0 + 1e-9 and r["instance"] not in set(forced):
            stats[label].at_optimum += 1
    provenance = {
        "arms": len(labels),
        "instances_in_sweep": len({r["instance"] for r in sweep_rows}),
        "instances_with_optimum": len(has_optimum),
        "instances_basis": len(basis),
        "instances_dropped": len(has_optimum) - len(basis),
        "basis": sorted(basis),
        "dropped": sorted(has_optimum - basis),
        "scope": sorted(has_optimum),
        "instances_forced": len(basis & set(forced)),
        "instances_free": len(basis - set(forced)),
    }
    return stats, provenance


def collect_central(central_rows: Sequence[dict],
                    optima: Dict[Tuple[str, int], float],
                    basis: Sequence[str], scope: Sequence[str],
                    forced: Sequence[str] = ()) -> Dict[str, ArmStats]:
    """The same three numbers for each centralized reference on the same basis.

    `scope` is the instance set the sweep itself covers, so the "valid runs"
    column counts the same denominator for a centralized row as for a
    distributed one; the reference implementation was measured on more
    instances than the sweep ran and those extra runs belong in the inventory,
    not in this table. The ratios are taken on the shared basis only.
    """
    wanted = set(basis)
    inside = set(scope)
    stats: Dict[str, ArmStats] = {}
    for row in central_rows:
        try:
            key = (row["instance"], int(float(row["k"])))
        except (KeyError, ValueError):
            continue
        if key not in optima or row["instance"] not in inside:
            continue
        label = row.get("arm") or CENTRAL_LABEL.get(row.get("algorithm", ""), "?")
        entry = stats.setdefault(label, ArmStats(label, 0, 0, [], 0))
        entry.runs += 1
        if not _truthy(row, "valid"):
            continue
        entry.valid += 1
        if row["instance"] not in wanted:
            continue
        weight = _f(row, "weight")
        opt = optima[key]
        if weight is None or opt <= 0:
            continue
        ratio = weight / opt
        entry.ratios.append(ratio)
        if ratio <= 1.0 + 1e-9 and row["instance"] not in set(forced):
            entry.at_optimum += 1
    return stats


def _tex_escape(text: str) -> str:
    return text.replace("_", r"\_").replace("&", r"\&").replace("%", r"\%")


def _order_key(label: str) -> Tuple[int, str]:
    head = label.split("/")[0]
    order = list(REPRESENTATIVE_ARMS) + list(GREEDY_ARMS)
    return (order.index(head) if head in order else 99, label)


def build_table(stats: Dict[str, ArmStats], central: Dict[str, ArmStats],
                provenance: dict, k: int, caption: str, label: str) -> str:
    """One table: mean ratio, worst ratio and optimum hits, on one basis."""
    rows = sorted(stats.items(), key=lambda kv: _order_key(kv[0]))
    central_rows = sorted(central.items(), key=lambda kv: kv[0])
    everything = [s for _, s in rows + central_rows if s.ratios]
    best_mean = min((s.mean for s in everything if s.mean is not None),
                    default=None)
    best_worst = min((s.worst for s in everything if s.worst is not None),
                     default=None)
    most_hits = max((s.at_optimum for s in everything), default=0)
    basis = provenance["instances_basis"]
    free = provenance.get("instances_free", basis)

    def cell(value: Optional[float], best: Optional[float]) -> str:
        if value is None:
            return "--"
        text = f"{value:.3f}"
        if best is not None and abs(value - best) < 1e-9:
            return r"\textbf{" + text + "}"
        return text

    def hits(value: int) -> str:
        text = f"{value}/{free}"
        return r"\textbf{" + text + "}" if value == most_hits and value else text

    out = [r"\begin{table*}[!t]", r"\centering",
           r"\caption{" + _tex_escape(caption) + "}",
           r"\label{" + label + "}",
           r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrr@{}}", r"\toprule",
           r"Arm & Valid runs & Mean weight / optimum & Worst weight / optimum "
           r"& At the optimum \\",
           r"\midrule"]
    for name, s in rows:
        out.append(f"{_tex_escape(armnames.display(name))} & {s.valid}/{s.runs} & "
                   f"{cell(s.mean, best_mean)} & {cell(s.worst, best_worst)} & "
                   f"{hits(s.at_optimum)} " + r"\\")
    if central_rows:
        out.append(r"\midrule")
        out.append(r"\multicolumn{5}{l}{\emph{Centralized reference, same "
                   r"instances and same capacity}} \\")
        for name, s in central_rows:
            out.append(f"{_tex_escape(armnames.display(name))} & {s.valid}/{s.runs} & "
                       f"{cell(s.mean, best_mean)} & {cell(s.worst, best_worst)} & "
                       f"{hits(s.at_optimum)} " + r"\\")
    known = provenance["instances_with_optimum"]
    dropped = provenance.get("instances_dropped", 0)
    out += [r"\bottomrule", r"\end{tabular*}",
            r"\begin{flushleft}\footnotesize",
            r"Every ratio divides a cover's weight by the weight of a proven "
            r"optimum of the SAME instance at the SAME capacity "
            rf"$k = {k}$, so 1.000 is optimal and lower is better. Of the "
            rf"{known} instances with a proven optimum, {basis} form the "
            r"basis: they are the ones every listed row solved validly, so "
            r"each mean and each worst case is taken over one common set "
            r"rather than over each row's own successes"
            + (rf", and {dropped} instance(s) that at least one row failed are "
               r"outside it" if dropped else "")
            + r". The ``valid runs'' column counts validity over all "
            rf"{known} instances, so a row can be seen to have failed even "
            r"though its ratios are computed on the shared basis. Instances "
            r"that are provably capacity-infeasible at this capacity have no "
            r"optimum and never enter either count. "
            + (rf"On {provenance.get('instances_forced', 0)} of the {basis} "
               r"basis instances the benchmark sets $m = nk$, the counting "
               r"bound then forces every vertex into the cover and every row "
               r"is optimal without choosing anything, so the last column "
               rf"counts only the {free} instances where a choice exists. "
               if provenance.get("instances_forced") else "")
            + r"The centralized rows run "
            r"the published reference implementation on the same quantized "
            r"instances; they are a quality reference only, since they assume "
            r"a single process holding the whole graph.",
            r"\end{flushleft}", r"\end{table*}", ""]
    return "\n".join(out)


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_opt = sub.add_parser("optima", help="measure optima with the exact solver")
    p_opt.add_argument("--k", type=int, default=6)
    p_opt.add_argument("--groups", default="small")
    p_opt.add_argument("--max-n", type=int, default=None)
    p_opt.add_argument("--max-seeds", type=int, default=None)
    p_opt.add_argument("--time-limit-s", type=float, default=600.0)
    p_opt.add_argument("--dataset-dir", default=None)
    p_opt.add_argument("--out", default="results/bb/exact/optima.csv")
    p_opt.add_argument("--append", action="store_true",
                       help="merge into an existing file instead of replacing it")

    p_cen = sub.add_parser("central", help="run the pinned upstream greedies")
    p_cen.add_argument("--k", type=int, default=6)
    p_cen.add_argument("--groups", default="small")
    p_cen.add_argument("--max-n", type=int, default=None)
    p_cen.add_argument("--max-seeds", type=int, default=None)
    p_cen.add_argument("--dataset-dir", default=None)
    p_cen.add_argument("--seed", type=int, default=42)
    p_cen.add_argument("--out", default="results/bb/exact/central.csv")
    p_cen.add_argument("--append", action="store_true",
                       help="merge into an existing file instead of replacing it")

    p_imp = sub.add_parser("import-upstream",
                           help="record the group's published optima")
    p_imp.add_argument("json", nargs="+")
    p_imp.add_argument("--out", default="results/bb/exact/optima_upstream.csv")

    p_tab = sub.add_parser("table", help="join and write the LaTeX table")
    p_tab.add_argument("--optima", default="results/bb/exact/optima.csv")
    p_tab.add_argument("--central", default="results/bb/exact/central.csv")
    p_tab.add_argument("--sweep", action="append", required=True)
    p_tab.add_argument("--k", type=int, default=6)
    p_tab.add_argument("--arms", default=None,
                       help="comma separated; default is the representative set")
    p_tab.add_argument("--out", default="paper/tables/exact_compare.tex")
    p_tab.add_argument("--tex-label", default="tab:exact")
    p_tab.add_argument("--caption", default=None)
    p_tab.add_argument("--central-basis", choices=("shared", "separate"),
                       default="shared",
                       help="shared: one basis every row solved validly, the "
                            "centralized references included. separate: the "
                            "basis is fixed by the distributed arms alone and "
                            "each centralized row is averaged over its own "
                            "successes inside it, which is larger but no "
                            "longer paired.")

    args = parser.parse_args(argv)

    if args.command == "optima":
        cells = _cells(args.groups.split(","), args.max_n)
        rows = run_optima(cells, args.k, max_seeds=args.max_seeds,
                          time_limit_s=args.time_limit_s,
                          dataset_dir=args.dataset_dir)
        if args.append and os.path.exists(args.out):
            old = {(r["instance"], r["k"]): r for r in _read_csv(args.out)}
            old.update({(r["instance"], str(r["k"])): r for r in rows})
            rows = sorted(old.values(), key=lambda r: (int(float(r["n"] or 0)),
                                                       int(float(r["m"] or 0)),
                                                       r["instance"]))
        _write_csv(args.out, OPTIMA_FIELDS, rows)
        ok = sum(1 for r in rows if r["status"] == "ok")
        print(f"wrote {args.out}: {len(rows)} rows, {ok} with a proven optimum")
        return 0

    if args.command == "central":
        cells = _cells(args.groups.split(","), args.max_n)
        rows = run_central(cells, args.k, max_seeds=args.max_seeds,
                           dataset_dir=args.dataset_dir, seed=args.seed)
        if args.append and os.path.exists(args.out):
            old = {(r["instance"], r["k"], r["algorithm"]): r
                   for r in _read_csv(args.out)}
            old.update({(r["instance"], str(r["k"]), r["algorithm"]): r
                        for r in rows})
            rows = sorted(old.values(),
                          key=lambda r: (int(float(r["n"] or 0)),
                                         int(float(r["m"] or 0)),
                                         r["instance"], r["algorithm"]))
        _write_csv(args.out, CENTRAL_FIELDS, rows)
        print(f"wrote {args.out}: {len(rows)} rows")
        return 0

    if args.command == "import-upstream":
        rows = import_upstream_optima(args.json)
        _write_csv(args.out, OPTIMA_FIELDS, rows)
        ok = sum(1 for r in rows if r["status"] == "ok")
        print(f"wrote {args.out}: {len(rows)} rows, {ok} with a proven optimum")
        return 0

    # table
    optima_rows = _read_csv(args.optima)
    optima = optimum_index(optima_rows)
    forced = forced_index(optima_rows)
    sweep_rows = load_sweep_rows(args.sweep)
    arms = (tuple(a.strip() for a in args.arms.split(",")) if args.arms
            else REPRESENTATIVE_ARMS + GREEDY_ARMS)
    central_rows = _read_csv(args.central) if os.path.exists(args.central) else []
    stats, provenance = collect(
        sweep_rows, optima, arms,
        central_rows if args.central_basis == "shared" else (), forced)
    central: Dict[str, ArmStats] = {}
    if central_rows:
        central = collect_central(central_rows, optima, provenance["basis"],
                                  provenance["scope"], forced)
    caption = args.caption or (
        f"Distance to the proven optimum at capacity k = {args.k}, averaged "
        f"over the {provenance['instances_basis']} instances that have a "
        f"proven optimum and that every listed row solved validly.")
    tex = build_table(stats, central, provenance, args.k, caption, args.tex_label)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(tex)
    os.replace(tmp, args.out)
    print(f"wrote {args.out}")
    print(f"  arms: {provenance['arms']}, instances in sweep: "
          f"{provenance['instances_in_sweep']}, with optimum at k={args.k}: "
          f"{provenance['instances_with_optimum']}, common basis: "
          f"{provenance['instances_basis']}")
    for name, s in sorted(stats.items(), key=lambda kv: _order_key(kv[0])):
        print(f"  {name:38s} mean={s.mean if s.mean is None else round(s.mean, 4)} "
              f"worst={s.worst if s.worst is None else round(s.worst, 4)} "
              f"at_opt={s.at_optimum}")
    for name, s in sorted(central.items()):
        print(f"  {name:38s} mean={s.mean if s.mean is None else round(s.mean, 4)} "
              f"worst={s.worst if s.worst is None else round(s.worst, 4)} "
              f"at_opt={s.at_optimum}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
