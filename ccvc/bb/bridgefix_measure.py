"""Measure the unpaid bridge discount, before and after the fix.

Table 4 of the report used to be typed by hand from a session's notes. That
makes the numbers unfalsifiable: nothing regenerates them, and nothing notices
when the code moves underneath. This module runs BOTH settings of
`AnnealParams.repay_bridge_credit` over the same instances, seeds and
schedulers, and writes the comparison out as data.

The defect itself is in BULGULAR_BB.md §90. In one sentence: joining the cover
was granted a discount of `lam_b*(labels-1)` and leaving was charged nothing,
so `delta(join) + delta(leave)` came to `-lam_b*(labels-1)` instead of zero and
a node could flip back and forth forever, harvesting energy. A node that never
freezes never reaches quiescence, so the run ends truncated rather than solved.

Usage:
    python3 -m ccvc.bb.bridgefix_measure --out results/bb/bridgefix
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from ccvc.bb import matrix as _matrix  # noqa: E402
from ccvc.bb import validate as V  # noqa: E402
from ccvc.bb.mnwifi import topology as _topo  # noqa: E402
from ccvc.bb.anneal import AnnealParams  # noqa: E402
from ccvc.bb.v6_anneal import run_anneal  # noqa: E402

#: The cells §90 was diagnosed on. Both are feasible: m <= n*k.
CELLS: Sequence[Dict[str, Any]] = (
    {"instance": "n50_m100_s%d.txt", "k": 6, "seeds": (1, 2, 3)},
    {"instance": "n25_m50_s%d.txt", "k": 6, "seeds": (1, 2, 3)},
)
SCHEDULERS = ("sync", "async")
DATASET = os.path.join("data", "DagdevirenDataset")
WEIGHT_SCALE = 10


def load_instance(path: str):
    """Same relabel-and-scale rule the wireless runner uses, so the cells match."""
    w_raw, edges_raw = _matrix.load_instance(path)
    ids = sorted(w_raw)
    relabel = {old: i + 1 for i, old in enumerate(ids)}
    edges = sorted({_topo.edge(relabel[u], relabel[v]) for u, v in edges_raw})
    weights = {relabel[o]: max(1, round(x * WEIGHT_SCALE)) for o, x in w_raw.items()}
    return edges, weights


def measure_one(path: str, k: int, scheduler: str, seed: int,
                repay: bool, max_ms: int) -> Dict[str, Any]:
    edges, weights = load_instance(path)
    p = AnnealParams(rng_seed=seed, repay_bridge_credit=repay)
    res = run_anneal(edges, weights, k, scheduler=scheduler, seed=seed,
                     params=p, max_ms=max_ms, trace=False)
    nodes = res.nodes
    graph = V.make_graph(list(edges), k, weights, sorted(weights))
    rep = V.validate(graph, res.cover, res.owner)
    labels = {getattr(n, "label", None) for n in nodes.values() if n.x}
    return {
        "instance": os.path.basename(path), "k": k, "scheduler": scheduler,
        "seed": seed, "repay_bridge_credit": repay,
        "flips_total": res.flips,
        "flips_worst_node": max((n.flips for n in nodes.values()), default=0),
        "frozen_nodes": sum(1 for n in nodes.values() if getattr(n, "frozen", False)),
        "n_nodes": len(nodes),
        "periods_total": res.total_periods,
        "distinct_labels": len([x for x in labels if x is not None]),
        "cover_components": len(rep.cover_components),
        "cover_weight": sum(weights[c] for c in res.cover),
        "verdict": res.verdict,
        "valid": rep.valid,
    }


def measure(max_ms: int = 200_000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for cell in CELLS:
        for seed in cell["seeds"]:
            path = os.path.join(DATASET, cell["instance"] % seed)
            if not os.path.exists(path):
                continue
            for scheduler in SCHEDULERS:
                for repay in (False, True):
                    rows.append(measure_one(path, cell["k"], scheduler,
                                            seed, repay, max_ms))
    return rows


def _span(vals: Sequence[Any]) -> str:
    """A single value when every run agreed, a range when they did not."""
    lo, hi = min(vals), max(vals)
    return f"{lo:,}" if lo == hi else f"{lo:,}--{hi:,}"


def summarize(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for repay in (False, True):
        side = [r for r in rows if r["repay_bridge_credit"] is repay]
        if not side:
            continue
        out["after" if repay else "before"] = {
            "runs": len(side),
            "flips_worst_node": _span([r["flips_worst_node"] for r in side]),
            # SCALE-INDEPENDENT. "24--50 frozen of 25--50 nodes" mixes the
            # n=25 and n=50 cells into one unreadable cell; what matters is
            # whether every node in a run froze, which is a count of runs.
            "runs_fully_frozen": sum(1 for r in side
                                     if r["frozen_nodes"] == r["n_nodes"]),
            "periods_total": _span([r["periods_total"] for r in side]),
            "distinct_labels": _span([r["distinct_labels"] for r in side]),
            "cover_components": _span([r["cover_components"] for r in side]),
            "solved_and_valid": sum(1 for r in side
                                    if r["verdict"] == "solved" and r["valid"]),
            "truncated": sum(1 for r in side if r["verdict"] == "truncated"),
        }
    return out


def latex_table(summary: Dict[str, Any]) -> str:
    b, a = summary.get("before"), summary.get("after")
    if not (b and a):
        return ""
    n = b["runs"]
    lines = [
        r"\begin{table}[tb]", r"\centering",
        r"\caption{The unpaid bridge discount, before and after the fix. "
        r"Measured on $n=50$, $m=100$ and $n=25$, $m=50$ with three seeds and "
        r"both schedulers. A node that never freezes exhausts the period "
        r"budget, which is why the run ends truncated rather than solved.}",
        r"\label{tab:bridgefix}",
        r"\begin{tabular}{lrr}", r"\toprule",
        r"Symptom & Before & After \\", r"\midrule",
        rf"Flips, worst node & {b['flips_worst_node']} & {a['flips_worst_node']} \\",
        rf"Runs where every node froze & {b['runs_fully_frozen']} / {n} & "
        rf"{a['runs_fully_frozen']} / {n} \\",
        rf"Periods used & {b['periods_total']} & {a['periods_total']} \\",
        rf"Distinct component labels & {b['distinct_labels']} & {a['distinct_labels']} \\",
        rf"Components of $G[C]$ & {b['cover_components']} & {a['cover_components']} \\",
        rf"Solved and valid & {b['solved_and_valid']} / {n} & "
        rf"{a['solved_and_valid']} / {n} \\",
        r"\bottomrule", r"\end{tabular}",
        r"\begin{flushleft}\footnotesize",
        r"Source: \texttt{ccvc/bb/bridgefix\_measure.py}; regenerate with "
        r"\texttt{python3 -m ccvc.bb.bridgefix\_measure}. A single number is "
        r"the value every run produced, a range is the spread over the "
        rf"{n} runs of that column.",
        r"\end{flushleft}", r"\end{table}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join("results", "bb", "bridgefix"))
    ap.add_argument("--max-ms", type=int, default=200_000)
    args = ap.parse_args(argv)

    rows = measure(max_ms=args.max_ms)
    if not rows:
        print("olculecek ornek bulunamadi", file=sys.stderr)
        return 1
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "rows.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = summarize(rows)
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    with open(os.path.join(args.out, "tab_bridgefix.tex"), "w",
              encoding="utf-8") as fh:
        fh.write(latex_table(summary))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
