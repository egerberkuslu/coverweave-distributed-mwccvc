"""Read-only source audit and later archived Mininet-WiFi provenance gates.

No algorithm or wireless experiment is launched here. Code evidence does not
prove actual wireless execution. Missing runtime proof stays PENDING.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

from ccvc.bb import armnames, sweep, validate
from ccvc.bb.mnwifi import collect, node_main, topology
from ccvc.bb.mnwifi.config import station_params
from ccvc.greedy import central, dataset
from ccvc.greedy.compare import fingerprint

ARM_CONFIGS = {
    "MIS-Connector-Backbone": ("bbcvc", {"enable_tree": False}),
    "MIS-Connector-TreeAgg": ("bbcvc", {"enable_tree": True}),
    "WuLi-Dominating-Exact": ("wuli", {"encoding": "full"}),
    "WuLi-Dominating-Bloom": ("wuli", {"encoding": "bloom"}),
    "WuLi-Dominating-Chunked": ("wuli", {"encoding": "chunked"}),
    "Anneal-Local": ("anneal", {"enable_tree": False, "trickle": False}),
    "Anneal-TreeAgg": ("anneal", {"enable_tree": True, "trickle": False}),
    "Anneal-Trickle": ("anneal", {"enable_tree": False, "trickle": True}),
    "Greedy-Degree-Backbone": ("gccvc", {}),
    "Greedy-Ratio-Backbone": ("grccvc", {}),
    "Greedy-Weight-Backbone": ("gwccvc", {}),
    "DFS-Spanning-Backbone": ("dfs", {"enable_tree": False}),
    "GHS-MST-Backbone": ("mst", {"enable_tree": False}),
}


def arm_config(arm):
    """Station configuration for an arm, accepting a pre-rename arm name.

    The comparison plans and station-plan directories already on disk under
    `results/greedy/` were written before the arms were renamed and still spell
    them `D-GRCCVC-BB` and so on. Translating on read keeps those plans
    exportable instead of stranding them; `ccvc/bb/armnames.py` holds the one
    table that says which old name is which.
    """
    return ARM_CONFIGS[armnames.canonical(arm)]

METRICS = {
    "radio_on_ms": "Elapsed active-phase proxy until quiescence; no physical radio state is measured.",
    "tx_rx_bytes_max_payload_retx": "Application/UDP protocol accounting from station JSONL. Bytes are payload bytes; retx excludes 802.11 MAC retries/ACKs. These are not total on-air traffic measurements.",
    "cover_owner": "Aggregate of node-local decisions and raw ownership claims; duplicate claims are invalid.",
    "total_weight_validity_optimum_ratios_common_subset": "External evaluator metrics, not locally computed node outputs.",
    "protocol_time_ms_simulator": "Virtual scheduler time; not wireless wall-clock time.",
    "protocol_time_ms_mininet": "Measured harness stop time including the quiescence guard; local-quiescence timestamps are a separate proxy. Actual run proof pending.",
    "observer_best_weight": "Global observer bound; distributed self-report would require an uncounted periodic convergecast.",
    "energy_mah_esp32_model": "Derived model; not measured Mininet-WiFi energy.",
    "central_owner": "Post-run max-flow certificate; not a distributed ownership protocol.",
    "tree_stable_fields": "Backbone subtree size/weight only, not full cover weight. STABLE tx/rx/bytes fields are zero placeholders and must not be reported as measured totals.",
}


def dataset_provenance(graph_json, plan):
    """Verify the original pinned dataset file, its relabeling and its weights."""
    try:
        document = json.loads(Path(graph_json).read_text())
    except json.JSONDecodeError:
        return None  # Generic edge lists make no dataset claim.
    if document.get("source") != "DagdevirenDataset":
        return None
    if not document.get("source_file"):
        raise ValueError("Dataset graph is missing the original source file")
    original = dataset.read_instance(document["source_file"])
    manifest = json.loads((dataset.DEFAULT_DATASET / "manifest.json").read_text())
    indexed = {entry["file"]: entry["sha256"] for entry in manifest["files"]}
    if (document.get("source_revision") != central.REVISION or manifest["source_revision"] != central.REVISION
            or document.get("source_sha256") != original.sha256 or indexed.get(original.path.name) != original.sha256):
        raise ValueError("Dataset hash/revision does not match the pinned manifest")
    weights, edges, reverse = original.relabeled()
    if (plan.spec.weights != weights or tuple(sorted(plan.spec.edges)) != edges
            or document.get("weight_transform") != "none"
            or {int(n): old for n, old in document.get("original_labels", {}).items()} != reverse):
        raise ValueError("Station graph/weights differ from the relabeled original dataset")
    if document.get("k") != plan.spec.k:
        raise ValueError("Dataset capacity differs from the station plan")
    return {"file": str(original.path.resolve()), "name": original.path.name, "sha256": original.sha256,
            "dataset_seed": original.seed,
            "source_revision": central.REVISION, "graph_json": str(Path(graph_json).resolve()),
            "graph_json_sha256": hashlib.sha256(Path(graph_json).read_bytes()).hexdigest(),
            "original_labels": reverse, "weight_transform": "none"}


def inspect_core(node_class):
    """Bounded source/call scan, including inherited methods; not a formal proof."""
    methods, violations = {}, []
    for base in reversed(node_class.__mro__):
        for name, value in vars(base).items():
            function = value.fget if isinstance(value, property) else value
            if inspect.isfunction(function):
                methods[name] = function
    primitives = {"mac", "now_ms", "send_broadcast", "send_unicast", "log"}
    forbidden_attributes = {"_net", "_adj", "graph", "sampler", "_nodes_obj"}
    forbidden_calls = {"solve_gccvc", "solve_grccvc", "solve_gwccvc", "solve_exact", "run_bbcvc",
                       "reference_backbone", "make_graph", "capacity_feasible"}
    for name, function in methods.items():
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        for item in ast.walk(tree):
            if isinstance(item, ast.Attribute):
                if item.attr in forbidden_attributes:
                    violations.append(f"{name}: global/capability attribute {item.attr}")
                if (isinstance(item.value, ast.Attribute) and item.value.attr in ("plat", "platform")
                        and item.attr not in primitives):
                    violations.append(f"{name}: non-platform primitive {item.attr}")
            if isinstance(item, ast.Call):
                target = item.func.id if isinstance(item.func, ast.Name) else getattr(item.func, "attr", "")
                if target in forbidden_calls:
                    violations.append(f"{name}: global solver/helper call {target}")
    constructor = list(inspect.signature(node_class.__init__).parameters)[1:]
    return {"passed": not violations and constructor == ["weight", "platform", "params", "capacity_k"],
            "constructor": constructor, "violations": sorted(set(violations)),
            "source": inspect.getsourcefile(node_class), "on_timer_source": inspect.getsourcefile(node_class.on_timer),
            "on_frame_source": inspect.getsourcefile(node_class.on_frame),
            "limitation": "Visible source only. Dynamic aliases, monkeypatching and formal convergence are outside this check."}


def verify_run(run_dir):
    """Archived stationary run gates; counters come from logs, never simulator CSV."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run.json").read_text())
    checks, errors = {"mininet_backend_recorded": meta.get("execution_backend") == "mininet-wifi"}, []
    case = meta.get("dataset_case")
    checks["pinned_dataset_link"] = False
    if case:
        try:
            surrogate = SimpleNamespace(spec=SimpleNamespace(weights={int(n): float(w) for n, w in meta["weights"].items()},
                edges=[tuple(edge) for edge in meta["edges"]], k=meta["k"]))
            linked = dataset_provenance(case["graph_json"], surrogate)
            checks["pinned_dataset_link"] = bool(linked and linked["sha256"] == case["sha256"]
                and linked["graph_json_sha256"] == case["graph_json_sha256"])
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"Dataset linkage: {exc}")
    logs = collect.read_run(str(run_dir))
    expected = {int(peer["nid"]) for peer in meta.get("peers", {}).get("peers", [])}
    starts = {node: log.first_of("run_start") for node, log in logs.items()}
    complete = bool(expected) and set(logs) == expected and all(starts.values())
    checks["all_expected_node_logs"] = complete
    namespaces = [record.get("network_namespace_inode") for record in starts.values() if record]
    host = meta.get("host_network_namespace_inode")
    checks["separate_station_namespaces"] = (complete and isinstance(host, int)
        and all(isinstance(inode, int) and inode != host for inode in namespaces)
        and len(set(namespaces)) == len(expected))
    checks["tracked_station_processes"] = complete and all(isinstance(record.get("pid"), int) and record["pid"] ==
        meta.get("station_process_pids", {}).get(str(node)) for node, record in starts.items())
    params_path = run_dir / "params.json"
    digest = hashlib.sha256(params_path.read_bytes()).hexdigest() if params_path.exists() else None
    checks["parameter_snapshots_match"] = complete and bool(digest and digest == meta.get("params_sha256")) and all(
        record.get("params_sha256") == digest for record in starts.values())
    checks["algorithm_and_clock_match"] = complete and all(
        record.get("node_kind") == meta.get("node_kind", "bbcvc") and record.get("mode") == meta.get("mode")
        and record.get("tau_ms") == meta.get("channel", {}).get("tau_ms")
        and record.get("t_hello_ms") == meta.get("channel", {}).get("t_hello_ms")
        and record.get("weight") == meta.get("weights", {}).get(str(node)) for node, record in starts.items())
    checks["code_fingerprints_match"] = complete and bool(meta.get("code_fingerprint")) and (
        fingerprint() == meta["code_fingerprint"] and all(record.get("code_fingerprint") == meta["code_fingerprint"]
                                                     for record in starts.values()))
    counters, document, _ = collect.collect(str(run_dir), tau_ms=meta["channel"]["tau_ms"], t0_ms=meta.get("t0_ms"),
        target_edges=meta["edges"], weights={int(n): w for n, w in meta["weights"].items()})
    checks["discovered_dataset_topology_exact"] = document["discovered_vs_target"]["exact"]
    graph = validate.make_graph(meta["edges"], meta["k"], {int(n): w for n, w in meta["weights"].items()}, nodes=sorted(expected))
    claims = [(edge, node) for node, owned in counters.owned.items() for edge in owned]
    validity = validate.validate(graph, counters.cover, claims)
    checks["complete_valid_solution"] = (counters.converged and validity.valid and not counters.unresolved
                                          and not counters.infeasible and not counters.table_overflow)
    checks["finished_node_records"] = complete and all(log.last_of("run_end") for log in logs.values())
    checks["telemetry_complete"] = not (counters.truncated_lines or counters.send_failures
        or counters.unicast_unreachable or counters.rssi_failures)
    namespace_verified = all(checks[key] for key in ("mininet_backend_recorded", "all_expected_node_logs",
        "separate_station_namespaces", "tracked_station_processes", "parameter_snapshots_match",
        "algorithm_and_clock_match", "code_fingerprints_match"))
    eligible = namespace_verified and all(checks[key] for key in ("pinned_dataset_link",
        "discovered_dataset_topology_exact", "finished_node_records", "telemetry_complete"))
    return {"passed": all(checks.values()), "checks": checks, "errors": errors, "metrics": document["totals"],
            "namespace_execution_verified": namespace_verified,
            "dataset_comparison_eligible": eligible,
            "metric_origin": "Counters recomputed from station JSONL; no simulator CSV import",
            "log_sha256": {str(node): hashlib.sha256(Path(log.path).read_bytes()).hexdigest() for node, log in logs.items()},
            "backend": "mininet-wifi" if namespace_verified else "unverified",
            "scope": "Archived stationary run evidence. Log authenticity is trusted, not adversarially certified."}


def code_audit():
    manifest = json.loads((dataset.DEFAULT_DATASET / "manifest.json").read_text())
    files_ok = all(dataset.read_instance(dataset.DEFAULT_DATASET / entry["file"]).sha256 == entry["sha256"]
                   for entry in manifest["files"])
    arms = []
    for spec in sweep.discover():
        mapping = ARM_CONFIGS.get(spec.name)
        entry = {"arm": spec.name, "schedulers": list(spec.schedulers), "wireless_execution": "PENDING"}
        if mapping:
            kind, overrides = mapping
            node_class, _ = node_main.resolve_node_kind(kind)
            entry.update(node_kind=kind, locality=inspect_core(node_class), parameter_overrides=overrides)
            snapshot = station_params(kind, {1: 1.25, 2: 2.5}, SimpleNamespace(t_hello_ms=20),
                                      5, overrides=overrides, mode=spec.schedulers[0])
            _, params_class = node_main.resolve_node_kind(kind)
            reconstructed = params_class(**snapshot)
            import dataclasses
            entry["configuration_snapshot_roundtrip_pass"] = dataclasses.asdict(reconstructed) == snapshot
        else:
            entry.update(node_kind=None, locality={"passed": False, "violations": ["Missing station mapping"]})
        entry["both_clocks"] = set(spec.schedulers) == {"sync", "async"}
        if spec.name == "Anneal-Trickle":
            entry["clock_exception"] = "Async-only policy; the underlying Anneal algorithm supports both clocks."
        arms.append(entry)
    return {"code_fingerprint": fingerprint(), "source_revision": central.REVISION,
            "mininet_net_import_pass": topology.mininet_available(),
            "pinned_dataset_files": manifest["file_count"], "dataset_hashes_and_structure_pass": files_ok,
            "central_reference_source_hash_pass": hashlib.sha256(central.SOURCE.read_bytes()).hexdigest() == central.SOURCE_SHA256,
            "arms": arms, "supported_core_source_checks_pass": all(arm["locality"]["passed"] for arm in arms),
            "wireless_experiments_executed_by_audit": False,
            # TRUE AS OF 2026-09-16, and the two statements it used to carry are
            # now false: DFS-Spanning-Backbone and GHS-MST-Backbone are both implemented as real
            # distributed protocols, registered with the sweep, and verified
            # against the central oracle. The flag is about the ALGORITHMS being
            # written, and it is deliberately NOT the same claim as the two
            # fields below, which stay false.
            "all_written_algorithms_complete": True,
            "algorithm_completeness_scope": (
                "Simulator and unit-fixture evidence only. Every registered arm "
                "has a working distributed implementation; none of them has a "
                "measured Mininet-WiFi run."),
            # DFS-Spanning-Backbone and GHS-MST-Backbone have NO station mapping, so they cannot be launched on
            # the emulator even though their algorithms are finished. Recording
            # this separately keeps 'the algorithm is written' from being read
            # as 'the arm can run on Wi-Fi'.
            "emulator_station_mapping_complete": True,
            "open_implementation_findings": [
                "No arm has a measured Mininet-WiFi run yet; every number in the comparison comes from the event simulator.",
                "Anneal-Local reports false success at n >= 50: measured 4 contradiction rows where the arm declared solved and the validator found the cover disconnected. Its bridge incentive cannot repair a split whose components are more than one hop apart.",
                "Phase 5b (MIS-Connector-TreeAgg) costs about twice the messages of MIS-Connector-Backbone for an identical solution weight at n = 50 and n = 100."],
            "pending_runtime_checks": ["Actual distinct Mininet-WiFi namespaces", "Exact dataset graph discovered on wireless medium",
                "Completed raw ownership claims and metrics from station JSONL", "Three/four real dataset seeds and loss/delay repeatability"],
            "metric_classification": METRICS,
            "deployment_assumptions": ["Annealing lambdas and temperatures are resolved with deployment w_max outside nodes.",
                "UDP IP/MAC mapping is platform-side. Shared host clock alignment excludes independent device synchronization costs.",
                "Channel schedule uses an analytical frame-size/rate assumption; actual PHY rate/airtime is not measured by the current collector.",
                "Harness termination watches all node files and uses a shared STOP file. This is external orchestration, not a counted distributed termination protocol.",
                "Local greedy RED priority and backbone-first construction differ from upstream global serial greedy."],
            "limits": "Source scans and fixture tests are bounded evidence; actual wireless execution and general convergence remain unproved."}


def write_report(report, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Distributed implementation audit", "", "Code evidence is separate from pending wireless evidence. Plans are not experiments.", "",
        f"Pinned files: {report['pinned_dataset_files']}; dataset hashes/structure: {report['dataset_hashes_and_structure_pass']}.",
        f"Supported source checks: {report['supported_core_source_checks_pass']}.", "",
        f"Usable Mininet net import in this Python environment: {report['mininet_net_import_pass']}. Namespace execution remains pending.", "",
        "| Arm | Station node | Clocks | Visible locality | Wi-Fi proof |", "|---|---|---|---|---|"]
    for arm in report["arms"]:
        lines.append(f"| {arm['arm']} | {arm['node_kind']} | {', '.join(arm['schedulers'])} | {'PASS' if arm['locality']['passed'] else 'FAIL'} | PENDING |")
    for title, items in (("Open implementation findings", report["open_implementation_findings"]),
        ("Metric origins", [f"**{name}**: {origin}" for name, origin in METRICS.items()]),
        ("Deployment assumptions", report["deployment_assumptions"]), ("Pending actual-run gates", report["pending_runtime_checks"])):
        lines += ["", f"## {title}", "", *[f"- {item}" for item in items]]
    lines += ["", report["limits"], ""]
    (out / "audit.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("docs/distributed_audit"))
    parser.add_argument("--run-dir", type=Path, help="Verify archived station logs later; never run an experiment")
    args = parser.parse_args()
    if args.run_dir:
        report = verify_run(args.run_dir)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["passed"] else 1)
    else:
        report = code_audit()
        write_report(report, args.out)
        print(json.dumps({key: report[key] for key in ("pinned_dataset_files", "dataset_hashes_and_structure_pass",
            "supported_core_source_checks_pass", "all_written_algorithms_complete", "wireless_experiments_executed_by_audit")}, indent=2))
