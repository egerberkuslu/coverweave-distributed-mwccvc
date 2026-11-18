"""Paired Dagdeviren comparison preparation; experiments require --execute.

Default: three real seeds in one small cell, upstream central references,
local distributed greedy in sync/async, and the existing registered BB arms.
Preparing a plan never runs an algorithm or allocates Mininet namespaces.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import time
from collections import Counter
from pathlib import Path

from ccvc.bb import armnames, sweep, validate
from ccvc.greedy.central import ALGORITHMS, REVISION, solve
from ccvc.greedy.dataset import DEFAULT_DATASET, select_instances

PROJECT = Path(__file__).resolve().parents[2]

#: Central reference arm -> the pinned upstream rule it runs.
CENTRAL_ARM_RULE = {armnames.greedy_arm(rule, "Upstream"): rule
                    for rule in ALGORITHMS}


def fingerprint():
    paths = [*sorted((PROJECT / "ccvc/greedy").glob("*.py")),
             *[PROJECT / f"ccvc/bb/{name}.py" for name in
               ("bbcvc", "bootstrap", "wire", "api", "sched", "simnet", "sweep", "validate",
                "v5_wuli", "v6_anneal", "anneal")],
             PROJECT / "ccvc/bridge.py", PROJECT / "ccvc/central.py"]
    paths += sorted((PROJECT / "ccvc/bb/mnwifi").glob("*.py"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(PROJECT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare(directory=DEFAULT_DATASET, *, n=10, ratio=2, seeds=3, k=4,
            include_bb=True, out=Path("results/greedy/prepared"), max_ms=600_000):
    instances = select_instances(Path(directory), n=n, ratio=ratio, seeds=seeds)
    specs = sweep.discover()
    if not include_bb:
        specs = [spec for spec in specs if spec.family == "greedy-backbone"]
    out = Path(out)
    (out / "graphs").mkdir(parents=True, exist_ok=True)
    records, entries = [], []
    for instance in instances:
        weights, edges, reverse = instance.relabeled()
        graph_path = out / "graphs" / f"{instance.path.stem}.json"
        graph_path.write_text(json.dumps({
            "edges": edges, "weights": weights, "k": k,
            "source": "DagdevirenDataset", "source_sha256": instance.sha256,
            "source_file": str(instance.path.resolve()), "source_revision": REVISION,
            "original_labels": reverse, "weight_transform": "none"}, indent=2) + "\n")
        record = {"case": instance.path.stem, "source_file": str(instance.path.resolve()),
                  "source_sha256": instance.sha256, "seed": instance.seed,
                  "n": instance.n, "m": instance.m, "k": k,
                  "graph_json": str(graph_path.resolve()), "original_labels": reverse}
        records.append(record)
        for algorithm in ALGORITHMS:
            entries.append({"case": record["case"],
                            "arm": armnames.greedy_arm(algorithm, "Upstream"),
                            "backend": "centralized-python", "scheduler": "centralized"})
        for spec in specs:
            for scheduler in spec.schedulers:
                entries.append({"case": record["case"], "arm": spec.name,
                                "backend": "event-simulator", "scheduler": scheduler})
    manifest = {"source": "DagdevirenDataset", "source_revision": REVISION,
                "source_directory": str(Path(directory).resolve()), "cases": records,
                "entries": entries, "planned_runs": len(entries), "seeds_per_arm": seeds,
                "code_fingerprint": fingerprint(), "weight_transform": "none",
                "max_ms": max_ms, "experiments_executed": False,
                "wireless_emulation_executed": False, "target_platform": "mininet-wifi",
                "missing_arms": ["DFS-Spanning-Backbone: distributed driver unfinished", "GHS-MST-Backbone: no sweep adapter"],
                "semantics": "Central upstream and local backbone adaptations are distinct methods; sync and async share a node core."}
    (out / "plan.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest, instances, specs


def collect_distributed(result, edges, weights, k):
    """Check raw ownership claims; do not validate an overwritten owner map."""
    graph = validate.make_graph(edges, k, weights, nodes=sorted(weights))
    claims = [(edge, node) for node, core in result.nodes.items() for edge in core.owned]
    report = validate.validate(graph, result.cover, claims)
    status = ("infeasible_instance" if result.infeasible else
              "not_converged" if not result.converged else
              "unresolved" if result.unresolved else
              "invalid_solution" if not report.valid else "ok")
    return {"status": status, "valid": report.valid, "converged": result.converged,
            "vertex_cover": report.vertex_cover, "connected": report.connected,
            "capacity": report.capacity, "unresolved": result.unresolved,
            "cover": sorted(result.cover), "total_weight": sum(weights[n] for n in result.cover),
            "tx": result.tx, "rx": result.rx, "retx": result.retx,
            "bytes_tx": result.bytes_tx, "max_payload": result.max_payload,
            "slots": result.slots, "protocol_time_ms": result.t_conv_ms,
            "violations": [{"kind": item.kind, "detail": item.detail} for item in report.violations],
            "owner": [[list(edge), node] for edge, node in sorted(result.owner.items())]}


def summarize(rows):
    """Keep every status, and use the same valid cases for all arm means."""
    arms = sorted({(row["arm"], row["scheduler"]) for row in rows})
    cases = {row["case"] for row in rows}
    consistent = {case for case in cases if len({
        tuple(row.get(key) for key in ("source_sha256", "seed", "n", "m", "k", "weight_transform"))
        for row in rows if row["case"] == case}) == 1}
    common = {case for case in consistent if all(
        sum(row["case"] == case and (row["arm"], row["scheduler"]) == arm
            and row["status"] == "ok" for row in rows) == 1 for arm in arms)}
    results = []
    for arm, scheduler in arms:
        selected = [row for row in rows if (row["arm"], row["scheduler"]) == (arm, scheduler)]
        paired = [row for row in selected if row["case"] in common]
        results.append({"arm": arm, "scheduler": scheduler, "runs": len(selected),
                        "statuses": dict(Counter(row["status"] for row in selected)),
                        "common_valid_runs": len(paired),
                        "common_valid_mean_weight": statistics.mean(row["total_weight"] for row in paired)
                            if paired else None,
                        "mean_tx_all_recorded_runs": statistics.mean(row["tx"] for row in selected if row["tx"] is not None)
                            if any(row["tx"] is not None for row in selected) else None})
    return {"common_valid_cases": sorted(common), "arms": results,
            "case_context_consistent": len(consistent) == len(cases),
            "all_runs_ok": bool(rows) and len(consistent) == len(cases) and all(row["status"] == "ok" for row in rows)}


def execute(manifest, instances, specs, out):
    rows = []
    by_case = {instance.path.stem: instance for instance in instances}
    by_arm = {spec.name: spec for spec in specs}
    for entry in manifest["entries"]:
        instance = by_case[entry["case"]]
        weights, edges, reverse = instance.relabeled()
        row = {**entry, "source": "dataset", "source_sha256": instance.sha256,
               "source_revision": REVISION, "code_fingerprint": manifest["code_fingerprint"],
               "seed": instance.seed, "n": instance.n, "m": instance.m,
               "k": manifest["cases"][0]["k"], "weight_transform": "none",
               "tx": None, "rx": None, "retx": None, "bytes_tx": None,
               "max_payload": None, "slots": None, "protocol_time_ms": None,
               "solver_time_ms": None, "original_labels": reverse}
        started = time.perf_counter()
        try:
            if entry["backend"] == "centralized-python":
                # LOOK THE RULE UP, do not slice the name. The arm used to be
                # `C-GRCCVC-UPSTREAM`, where field 1 happened to be the rule;
                # after the rename field 1 is the word "Ratio", so a positional
                # slice would silently solve the wrong problem.
                algorithm = CENTRAL_ARM_RULE[armnames.canonical(entry["arm"])]
                result = solve(algorithm, edges, weights, row["k"], seed=instance.seed)
                row.update(status=result.status, valid=result.valid,
                           vertex_cover=result.vertex_cover, connected=result.connected,
                           capacity=result.capacity, total_weight=result.total_weight,
                           cover=result.cover, owner=[[list(edge), node] for edge, node in sorted(result.owner.items())],
                           violations=result.violations, solver_time_ms=result.time_ms,
                           ownership_source=result.ownership_source)
            else:
                request = sweep.RunRequest(edges, weights, row["k"], entry["scheduler"],
                                           instance.seed, manifest["max_ms"])
                result = by_arm[entry["arm"]].run(request)
                row.update(collect_distributed(result, edges, weights, row["k"]))
                row["ownership_source"] = "node-local protocol claims"
        except Exception as exc:
            row.update(status="error", valid=False, error=f"{type(exc).__name__}: {exc}",
                       total_weight=None)
        row["wall_time_ms"] = (time.perf_counter() - started) * 1000
        row["original_cover"] = [reverse[node] for node in row.get("cover", [])]
        rows.append(row)
        print(f"[{len(rows)}/{len(manifest['entries'])}] {row['case']} {row['arm']}/{row['scheduler']} -> {row['status']}", flush=True)
        # Preserve partial runs even if the experiment is interrupted later.
        with (out / "rows.jsonl").open("a" if len(rows) > 1 else "w") as stream:
            stream.write(json.dumps(row) + "\n")
    manifest["experiments_executed"] = True
    manifest["code_revision_unchanged"] = fingerprint() == manifest["code_fingerprint"]
    summary = summarize(rows)
    (out / "summary.json").write_text(json.dumps({"manifest": manifest, "summary": summary}, indent=2) + "\n")
    fields = sorted({key for row in rows for key in row})
    with (out / "rows.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value
                             for key, value in row.items()})
    lines = ["# Paired Dagdeviren comparison", "", manifest["semantics"], "",
             "Central owner maps are post-run flow certificates. Central tx/rx and protocol time are unmeasured, so they remain empty.",
             "Simulator protocol time is virtual; central solver time and host wall time are separate columns.", "",
             f"Common valid cases: {len(summary['common_valid_cases'])}. All failures remain recorded.", "",
             "| Arm | Scheduler | Runs | Status counts | Common valid mean weight |",
             "|---|---|---:|---|---:|"]
    for arm in summary["arms"]:
        lines.append(f"| {arm['arm']} | {arm['scheduler']} | {arm['runs']} | {arm['statuses']} | {arm['common_valid_mean_weight']} |")
    lines += ["", "Three or four seeds are an incremental check, not a statistical ranking.",
              "No Mininet-WiFi wireless measurements are included.", ""]
    (out / "summary.md").write_text("\n".join(lines))
    return 0 if summary["all_runs_ok"] and manifest["code_revision_unchanged"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--n", type=int, choices=(10, 15, 20, 25), default=10)
    parser.add_argument("--ratio", type=int, default=2)
    parser.add_argument("--seeds", type=int, choices=(3, 4), default=3)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--max-ms", type=int, default=600_000)
    parser.add_argument("--greedy-only", action="store_true", help="Exclude existing BB comparison arms")
    parser.add_argument("--out", type=Path, default=Path("results/greedy/prepared"))
    parser.add_argument("--execute", action="store_true", help="Explicitly run the prepared central/simulator experiments")
    args = parser.parse_args(argv)
    if args.k < 1 or args.max_ms < 1 or args.ratio < 1:
        parser.error("Require positive capacity, density and protocol time budget")
    if args.execute and (args.out / "rows.jsonl").exists():
        parser.error("Output already contains experiment rows; use a new --out directory")
    try:
        manifest, instances, specs = prepare(args.dataset_dir, n=args.n, ratio=args.ratio,
            seeds=args.seeds, k=args.k, include_bb=not args.greedy_only, out=args.out, max_ms=args.max_ms)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Prepared {len(instances)} paired cases and {manifest['planned_runs']} entries: {args.out / 'plan.json'}")
    if not args.execute:
        print("No algorithm or wireless experiment executed. Pass --execute only when experiments are requested.")
        return 0
    return execute(manifest, instances, specs, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
