"""Prepare station plans or export verified archived runs; never execute Wi-Fi.

The exporter refuses unverified namespaces, altered input data, changed code,
incomplete ownership and a wireless topology that differs from the dataset.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ccvc.bb.mnwifi import collect, run as driver
from ccvc.bb import validate
from ccvc.bb.mnwifi.config import station_params
from types import SimpleNamespace
from ccvc.greedy import dataset
from ccvc.bb import armnames
from ccvc.greedy.audit import ARM_CONFIGS, arm_config, dataset_provenance, verify_run


def prepare(comparison_plan, out):
    manifest = json.loads(Path(comparison_plan).read_text())
    cases = {case["case"]: case for case in manifest["cases"]}
    records = []
    for entry in manifest["entries"]:
        if entry["backend"] == "centralized-python":
            continue
        case = cases[entry["case"]]
        original = dataset.read_instance(case["source_file"])
        if original.sha256 != case["source_sha256"]:
            raise ValueError("Comparison input changed after preparation")
        weights, edges, _ = original.relabeled()
        arm = armnames.canonical(entry["arm"])
        kind, overrides = arm_config(arm)
        run_id = f"{case['case']}_{arm}_{entry['scheduler']}"
        plan = driver.make_plan(edges, weights, case["k"], run_id=run_id, run_root=str(out),
            mode=entry["scheduler"], seed=case["seed"], max_ms=manifest["max_ms"],
            node_kind=kind, node_params=overrides)
        plan.dataset_case = dataset_provenance(case["graph_json"], plan)
        driver.write_plan(plan)
        records.append({"arm": arm, "scheduler": entry["scheduler"],
                        "run_dir": str(Path(plan.run_dir).resolve()), "case": case["case"],
                        "geometric_target_exact": plan.spec.geometric_diff.exact,
                        "command_for_later": driver.sudo_command(plan), "execution_status": "PENDING"})
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "index.json").write_text(json.dumps({"comparison_plan": str(Path(comparison_plan).resolve()),
        "runs": records, "experiments_executed": False}, indent=2) + "\n")
    return records


def export(run_dirs, out):
    rows = []
    for run_dir in run_dirs:
        proof = verify_run(run_dir)
        if not proof["dataset_comparison_eligible"]:
            raise ValueError(f"Refusing unverified experiment {run_dir}: {proof['checks']}")
        meta = json.loads((Path(run_dir) / "run.json").read_text())
        original = dataset.read_instance(meta["dataset_case"]["file"])
        if meta["seed"] != original.seed:
            raise ValueError("Protocol seed differs from the prepared paired dataset seed")
        kind, params = meta["node_kind"], meta["node_params"]
        matches = [arm for arm, (node_kind, overrides) in ARM_CONFIGS.items()
                   if node_kind == kind and all(params.get(key) == value for key, value in overrides.items())]
        if len(matches) != 1:
            raise ValueError(f"Ambiguous/unsupported experiment arm for {kind}: {matches}")
        weights, edges, reverse = original.relabeled()
        canonical = station_params(kind, weights, SimpleNamespace(t_hello_ms=meta["channel"]["t_hello_ms"]),
            meta["mis_nbrs_max"], overrides=ARM_CONFIGS[matches[0]][1], mode=meta["mode"], seed=meta["seed"])
        if canonical != params:
            raise ValueError("Custom deployment configuration cannot masquerade as a canonical comparison arm")
        counters, _, _ = collect.collect(str(run_dir), tau_ms=meta["channel"]["tau_ms"], t0_ms=meta["t0_ms"],
            target_edges=edges, weights=weights)
        totals = counters.totals()
        graph = validate.make_graph(edges, meta["k"], weights, nodes=sorted(weights))
        claims = [(edge, node) for node, owned in counters.owned.items() for edge in owned]
        validity = validate.validate(graph, counters.cover, claims)
        status = ("infeasible_instance" if counters.infeasible else "not_converged" if not counters.converged
                  else "unresolved" if counters.unresolved else "invalid_solution" if not validity.valid else "ok")
        rows.append({"case": original.path.stem, "arm": matches[0], "scheduler": meta["mode"],
            "backend": "mininet-wifi", "source": "dataset", "source_revision": meta["dataset_case"]["source_revision"],
            "source_sha256": original.sha256, "code_fingerprint": meta["code_fingerprint"], "seed": meta["seed"],
            "n": original.n, "m": original.m, "k": meta["k"], "weight_transform": "none", "status": status,
            "valid": validity.valid, "converged": counters.converged, "unresolved": counters.unresolved,
            "total_weight": sum(weights[node] for node in counters.cover),
            "cover": counters.cover, "original_cover": [reverse[node] for node in counters.cover],
            "owner": [[list(edge), node] for edge, node in sorted(counters.owner.items())],
            "tx": totals.tx, "rx": totals.rx, "retx": totals.retx, "bytes_tx": totals.bytes_tx,
            "max_payload": totals.max_payload, "slots": counters.slots,
            "slots_label": "local-quiescence-derived proxy",
            "local_quiescence_time_ms": counters.t_conv_ms,
            "protocol_time_ms": meta.get("orchestrator_stop_ms"),
            "protocol_time_label": "harness stop time, includes quiescence guard; not pure node-compute time",
            "ownership_source": "node-local claims from station logs", "namespace_execution_verified": True,
            "run_dir": str(Path(run_dir).resolve()), "log_sha256": proof["log_sha256"]})
    if not rows:
        raise ValueError("No verified archived station runs supplied")
    identities = [(row["case"], row["arm"], row["scheduler"], row["seed"], row["k"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate archived paired run; repeated logs are not independent seeds")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "rows.csv").exists():
        raise ValueError("Use a fresh export directory; existing rows will not be overwritten")
    (out / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")
    fields = sorted({key for row in rows for key in row})
    with (out / "rows.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    planned = sub.add_parser("prepare")
    planned.add_argument("comparison_plan", type=Path)
    planned.add_argument("--out", type=Path, required=True)
    archived = sub.add_parser("export")
    archived.add_argument("run_dirs", type=Path, nargs="+")
    archived.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(f"Prepared {len(prepare(args.comparison_plan, args.out))} station plans; no network started.")
    else:
        print(f"Exported {len(export(args.run_dirs, args.out))} verified stationary runs from station logs.")
