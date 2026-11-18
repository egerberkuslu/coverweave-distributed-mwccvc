"""Small protocol and reference regression fixtures, not benchmark experiments."""
from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ccvc.bb import armnames, sweep, validate, wire
from ccvc.bb.api import MAX_PAYLOAD, MsgType, Role
from ccvc.bb.bbcvc import PH_COVER, PH_FORCED, mac_for_id
from ccvc.bb.bootstrap import BootNeighbor
from ccvc.bb.mnwifi import node_main, run as mnrun
from ccvc.greedy import central, compare, dataset, distributed


class Port:
    """Only radio identity, clock and platform primitives; no graph access."""
    mac = mac_for_id(1)

    def __init__(self):
        self.now = 1000
        self.sent = []

    def now_ms(self):
        return self.now

    def send_broadcast(self, payload):
        self.sent.append(payload)

    def send_unicast(self, destination, payload):
        self.sent.append(payload)

    def log(self, event, **fields):
        pass


def state(node, *, seq=1, weight=1.0, denominator=2.0, degree=2, color=1, epoch=0, rule=0):
    return wire.GreedyState(node, seq, weight, denominator, degree, color, epoch, rule, PH_COVER)


def local_node(rule="gccvc"):
    core = distributed.GreedyNode(2.25, Port(), distributed.GreedyParams(algorithm=rule), 4)
    core.phase = PH_COVER
    core.key = (100, core.nid)
    core.nbrs[2] = BootNeighbor(nid=2, mac=mac_for_id(2), last_ms=1000,
                                bidir=True, link_up=True, role=Role.OUT,
                                phase=PH_COVER, key=200)
    return core


def test_dataset_parser_handles_integer_and_exponential_weights(tmp_path):
    path = tmp_path / "n3_m2_s1.txt"
    path.write_text("0 1\n1 2e-1\n2 3.125\n0 1\n1 2\n")
    instance = dataset.read_instance(path)
    assert instance.weights == {0: 1.0, 1: 0.2, 2: 3.125}
    weights, edges, reverse = instance.relabeled()
    assert weights == {1: 1.0, 2: 0.2, 3: 3.125}
    assert reverse == {1: 0, 2: 1, 3: 2}
    assert edges == ((1, 2), (2, 3))


@pytest.mark.parametrize("text", [
    "0 1\n1 2\n2 3\n0 1\n1 0\n",  # duplicate reverse edge
    "0 1\n1 2\n2 3\n0 1\n1 5\n",  # unknown endpoint
    "0 nan\n1 2\n2 3\n0 1\n1 2\n",
    "0 1\n0 2\n2 3\n0 1\n1 2\n",
])
def test_corrupt_dataset_is_rejected(text, tmp_path):
    path = tmp_path / "n3_m2_s1.txt"
    path.write_text(text)
    with pytest.raises(ValueError):
        dataset.read_instance(path)


def test_pinned_dataset_manifest_matches_files():
    manifest = json.loads((dataset.DEFAULT_DATASET / "manifest.json").read_text())
    assert manifest["source_revision"] == central.REVISION
    assert manifest["file_count"] == len(manifest["files"]) == 360
    # Three actual input files suffice here; the importer validated all files.
    indexed = {entry["file"]: entry for entry in manifest["files"]}
    for instance in dataset.select_instances():
        assert instance.sha256 == indexed[instance.path.name]["sha256"]


@pytest.mark.parametrize("rule", central.ALGORITHMS)
def test_upstream_reference_preserves_initial_selection(rule, monkeypatch):
    source = central.upstream()
    original = source.select_node
    selected = []

    def record(graph, node, *args, **kwargs):
        selected.append(node.id)
        return original(graph, node, *args, **kwargs)

    monkeypatch.setattr(source, "select_node", record)
    edges = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 1), (1, 3)]
    weights = {1: 10.0, 2: 1.0, 3: 5.0, 4: 2.0, 5: 4.0}
    result = central.solve(rule, edges, weights, 6, seed=3)
    assert selected[0] == (3 if rule == "gccvc" else 2)
    assert result.valid
    assert len(result.owner) == len(edges)


def test_infeasible_instance_is_not_repaired_or_called_valid():
    result = central.solve("gwccvc", [(1, 2), (2, 3), (1, 3)], {1: 1.5, 2: 2.5, 3: 3.5}, 1)
    assert not result.instance_feasible or not result.capacity
    assert result.status != "ok"
    assert not result.valid


def test_three_score_rules_and_local_red_priority():
    a, b = state(1, weight=8, degree=4, denominator=40), state(2, weight=3, degree=2, denominator=6)
    assert distributed.candidate_key("gccvc", a) < distributed.candidate_key("gccvc", b)
    assert distributed.candidate_key("grccvc", a) < distributed.candidate_key("grccvc", b)
    assert distributed.candidate_key("gwccvc", b) < distributed.candidate_key("gwccvc", a)
    for rule in central.ALGORITHMS:
        assert distributed.candidate_key(rule, replace(b, color=0)) < distributed.candidate_key(rule, a)


def test_score_codec_has_exact_small_payload_and_preserves_weight():
    message = state(1, weight=29.278536798674715, rule=1)
    raw = wire.encode(message)
    assert len(raw) == 29 < MAX_PAYLOAD
    assert wire.decode(raw) == message
    assert wire.peek_type(raw) is MsgType.GREEDY_STATE
    for damaged in (raw[:-1], raw + b"\x00"):
        with pytest.raises(ValueError):
            wire.decode(damaged)


@pytest.mark.parametrize("field,value", [("weight", float("nan")), ("weight", -1),
                                          ("denominator", float("inf")), ("rule", 8), ("color", 9)])
def test_invalid_score_cannot_enter_wire(field, value):
    with pytest.raises(ValueError):
        wire.encode(replace(state(1), **{field: value}))


def test_missing_stale_forged_and_reordered_scores_do_not_select():
    core = local_node()
    core._rule_cover(core._nbrs_active())
    assert core.role is Role.OUT
    peer = core.nbrs[2]
    advertised = state(2, seq=3, weight=100, degree=1, color=0)
    core._on_algo(1000, peer.mac + 1, advertised)
    assert not core._greedy_info
    core._on_algo(1000, peer.mac, advertised)
    core._on_algo(1001, peer.mac, replace(advertised, seq=2, weight=0.5))
    assert core._greedy_info[2][0].weight == 100
    core.plat.now = 10000
    core._rule_cover(core._nbrs_active())
    assert core.role is Role.OUT
    core.plat.now = 1002
    core._rule_cover(core._nbrs_active())
    assert core.role is Role.COVER
    assert core.phase == PH_FORCED


def test_epoch_reset_discards_greedy_scores_and_red_marking():
    core = local_node()
    core._greedy_info[2] = (state(2), 1000)
    core._greedy_red = True
    core._reset_to_phase0(1100, "fixture")
    assert not core._greedy_info and not core._greedy_red


@pytest.mark.parametrize("rule", central.ALGORITHMS)
@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_same_core_converges_and_owns_edges_on_small_fixture(rule, scheduler, monkeypatch):
    # Hand-built protocol fixture only: no dataset sweep, Mininet or namespace.
    monkeypatch.setattr(central, "solve", lambda *a, **k: pytest.fail("A distributed node cannot call a central solver"))
    edges = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 1), (2, 5)]
    weights = {1: 2.125, 2: 1.25, 3: 4.125, 4: 2.25, 5: 3.75, 6: 1.875}
    result = distributed.run_greedy(edges, weights, 4, algorithm=rule, scheduler=scheduler,
                                    max_ms=30_000, rssi_range=(-60, -60))
    report = compare.collect_distributed(result, edges, weights, 4)
    assert report["status"] == "ok"
    assert report["valid"] and len(result.owner) == len(edges)
    station_class, _ = node_main.resolve_node_kind(rule)
    assert all(type(node) is station_class for node in result.nodes.values())
    assert result.tx > 0 and result.rx > result.tx
    assert result.max_payload <= MAX_PAYLOAD
    assert result.by_type_tx[int(MsgType.GREEDY_STATE)] > 0


@pytest.mark.parametrize("scheduler", ["sync", "async"])
def test_greedy_stage_selects_a_residual_edge_and_capacity_repair_is_shared(scheduler):
    edges, weights = [(1, 2), (2, 3), (1, 3)], {1: 1.25, 2: 2.75, 3: 3.125}
    result = distributed.run_greedy(edges, weights, 1, scheduler=scheduler,
                                    max_ms=30_000, rssi_range=(-60, -60))
    assert any(node.greedy_selections for node in result.nodes.values())
    assert compare.collect_distributed(result, edges, weights, 1)["status"] == "ok"
    assert len(result.cover) == 3  # Three edges at k=1 require all three owners.


@pytest.mark.parametrize("rule", central.ALGORITHMS)
def test_station_plan_and_resume_keep_algorithm_and_fractional_weight(rule, tmp_path):
    weights = {1: 29.278536798674715, 2: 26.20965451126096}
    plan = mnrun.make_plan([(1, 2)], weights, 1, node_kind=rule,
                           run_root=str(tmp_path), run_id="greedy")
    mnrun.write_plan(plan)
    restored = mnrun.load_plan(plan.run_dir)
    assert restored.node_kind == rule and restored.spec.weights == weights
    argv = mnrun.node_argv(restored, 1)
    assert argv[argv.index("--node") + 1] == rule
    assert float(argv[argv.index("--weight") + 1]) == weights[1]
    node_class, params_class = node_main.resolve_node_kind(rule)
    core = node_class(weights[1], Port(), params_class(), 1)
    assert core.p.algorithm == rule and core.w == weights[1]


def test_plan_preparation_never_calls_algorithms(tmp_path, monkeypatch):
    monkeypatch.setattr(central, "solve", lambda *a, **k: pytest.fail("preparation must not execute"))
    monkeypatch.setattr(distributed, "run_greedy", lambda *a, **k: pytest.fail("preparation must not execute"))
    manifest, instances, _ = compare.prepare(out=tmp_path, include_bb=False)
    assert len(instances) == 3 and manifest["planned_runs"] == 27
    assert not manifest["experiments_executed"]
    assert manifest["weight_transform"] == "none"


def test_failures_are_kept_and_common_valid_means_are_paired():
    rows = [{"case": case, "arm": arm, "scheduler": "async", "tx": 2,
             "status": "ok", "total_weight": 10} for case in ("a", "b") for arm in ("x", "y")]
    rows[-1]["status"] = "unresolved"
    rows[-1]["total_weight"] = 1
    result = compare.summarize(rows)
    assert result["common_valid_cases"] == ["a"]
    assert not result["all_runs_ok"]
    assert all(arm["runs"] == 2 and arm["common_valid_mean_weight"] == 10 for arm in result["arms"])


def test_sweep_discovers_both_clocks_for_every_distributed_greedy():
    specs = {spec.name: spec for spec in sweep.discover()}
    for rule in central.ALGORITHMS:
        arm = armnames.greedy_arm(rule, "Backbone")
        assert specs[arm].schedulers == ("sync", "async")


def test_dataset_claim_is_verified_and_changed_weights_are_rejected(tmp_path):
    from ccvc.greedy.audit import dataset_provenance
    manifest, _, _ = compare.prepare(out=tmp_path, include_bb=False)
    graph_path = manifest["cases"][0]["graph_json"]
    doc = json.loads(open(graph_path).read())
    plan = mnrun.make_plan(doc["edges"], {int(n): w for n, w in doc["weights"].items()}, doc["k"])
    linked = dataset_provenance(graph_path, plan)
    assert linked["sha256"] == manifest["cases"][0]["source_sha256"]
    plan.spec.weights[1] += .01
    with pytest.raises(ValueError, match="Station graph/weights differ"):
        dataset_provenance(graph_path, plan)


def test_prepared_plan_never_counts_as_actual_mininet_evidence(tmp_path):
    from ccvc.greedy.audit import verify_run
    plan = mnrun.make_plan([(1, 2)], {1: 1.25, 2: 2.5}, 1,
                           run_root=str(tmp_path), run_id="not-executed")
    mnrun.write_plan(plan)
    report = verify_run(plan.run_dir)
    assert not report["passed"] and report["backend"] == "unverified"
    assert not report["checks"]["mininet_backend_recorded"]
    assert not report["checks"]["separate_station_namespaces"]


def test_annealing_observer_has_no_graph_capability_on_nodes():
    from ccvc.bb.anneal import AnnealParams
    from ccvc.bb.v6_anneal import _TracedAnnealNode
    from ccvc.greedy.audit import inspect_core
    core = _TracedAnnealNode(1.25, Port(), AnnealParams().resolved([1.25, 2.5]), 2)
    assert not hasattr(core, "sampler")
    assert inspect_core(_TracedAnnealNode)["passed"]


def test_saved_annealing_and_wuli_policies_survive_resume(tmp_path):
    cases = [("anneal", {"trickle": True}, "async"), ("wuli", {"encoding": "bloom"}, "sync"),
             ("bbcvc", {"enable_tree": True}, "sync")]
    for kind, overrides, mode in cases:
        plan = mnrun.make_plan([(1, 2)], {1: 1.25, 2: 2.5}, 1, node_kind=kind,
            node_params=overrides, mode=mode, run_root=str(tmp_path), run_id=kind)
        mnrun.write_plan(plan)
        restored = mnrun.load_plan(plan.run_dir)
        assert restored.node_params == plan.node_params
        for field, value in overrides.items():
            assert restored.node_params[field] == value
        if kind == "anneal":
            assert restored.node_params["lam_c"] == 5


def test_unknown_deployment_fields_and_sync_trickle_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown deployment parameters"):
        mnrun.make_plan([(1, 2)], {1: 1.25, 2: 2.5}, 1, node_params={"invented_flag": True})
    with pytest.raises(ValueError, match="asynchronous-only"):
        mnrun.make_plan([(1, 2)], {1: 1.25, 2: 2.5}, 1, node_kind="anneal", node_params={"trickle": True})


def test_archived_counter_provenance_gates_on_coherent_offline_fixture(tmp_path):
    """Synthetic log fixture tests the verifier, not real wireless execution."""
    from ccvc.greedy.audit import dataset_provenance, verify_run
    from ccvc import central as certificates
    manifest, _, _ = compare.prepare(out=tmp_path / "inputs", include_bb=False)
    graph_path = manifest["cases"][0]["graph_json"]
    document = json.loads(open(graph_path).read())
    weights = {int(n): w for n, w in document["weights"].items()}
    plan = mnrun.make_plan(document["edges"], weights, 4, node_kind="gccvc",
                           run_root=str(tmp_path), run_id="offline-fixture")
    plan.dataset_case = dataset_provenance(graph_path, plan)
    mnrun.write_plan(plan)
    meta_path = tmp_path / "offline-fixture/run.json"
    meta = json.loads(meta_path.read_text())
    meta.update(execution_backend="mininet-wifi", host_network_namespace_inode=999,
                station_process_pids={str(n): 10000 + n for n in weights}, t0_ms=0)
    meta_path.write_text(json.dumps(meta))
    graph = validate.make_graph(document["edges"], 4, weights, nodes=sorted(weights))
    feasible, owners = certificates.capacity_assignment(graph, set(weights))
    assert feasible
    tau = plan.spec.channel.tau_ms
    for node, peer in plan.spec.peers.items():
        records = [{"event": "open", "t_ms": 0, "mac": peer.mac_str},
                   {"event": "run_start", "t_ms": 0, "node_kind": "gccvc", "mode": "sync",
                    "tau_ms": tau, "t_hello_ms": plan.spec.channel.t_hello_ms,
                    "weight": weights[node], "params_sha256": meta["params_sha256"],
                    "code_fingerprint": meta["code_fingerprint"], "network_namespace_inode": 1000 + node,
                    "pid": 10000 + node},
                   {"event": "tx", "t_ms": tau, "bytes": 13, "mtype": 0, "phase": 3}]
        records += [{"event": "rx", "t_ms": tau, "src": plan.spec.peers[n].mac_str, "mtype": 0}
                    for n in graph.adj[node]]
        records += [{"event": "node_done", "t_ms": 3 * tau, "t_end_ms": 3 * tau},
                    {"event": "run_end", "t_ms": 4 * tau, "role": int(Role.COVER),
                     "owned": [list(edge) for edge, owner in owners.items() if owner == node],
                     "bidir": sorted(graph.adj[node]), "tx": 999999}]
        (tmp_path / f"offline-fixture/{node}.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records))
    report = verify_run(meta_path.parent)
    assert report["passed"], report["checks"]
    assert report["metrics"]["tx"] == 10  # Ignore the fake self-reported 999999.
    assert report["metrics"]["rx"] == 40
    path = tmp_path / "offline-fixture/1.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[1]["network_namespace_inode"] = 999  # Host loopback cannot count as station evidence.
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    rejected = verify_run(meta_path.parent)
    assert not rejected["passed"] and not rejected["checks"]["separate_station_namespaces"]
