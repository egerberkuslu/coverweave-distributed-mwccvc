"""Seeded upstream GCCVC/GRCCVC/GWCCVC, with independent output validation.

These references preserve the source's candidate pool, RNG and separate
connectivity repairs. An invalid result is reported rather than repaired by a
different algorithm. The flow assignment is a post-run feasibility certificate;
it is not the upstream greedy's internal edge ledger or a distributed action.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ccvc import bridge, central as certificates
from ccvc.bb import validate

REVISION = "8ca814ff78c9dc0705e951eb3d864344d8adaa80"
SOURCE_SHA256 = "b0a18b6952ea8818b9c5d880d2d8990a2662a09476c3ed7083db7267119a5044"
SOURCE = Path(__file__).resolve().parents[2] / "external_sources/MWCCVC/backend/app/algorithms.py"
ALGORITHMS = ("gccvc", "grccvc", "gwccvc")


@lru_cache(maxsize=1)
def upstream():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("Pinned upstream algorithms.py changed; audit the revision before comparing results")
    name = "_mwccvc_greedy_reference_8ca814f"
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module during import
    # Do not modify the pinned checkout by writing a bytecode cache into it.
    exec(compile(raw, str(SOURCE), "exec"), module.__dict__)
    return module


def check_input(edges, weights, k):
    if isinstance(k, bool) or not isinstance(k, int) or k < 1 or not weights:
        raise ValueError("Require positive integer capacity and a nonempty weighted graph")
    if any(not math.isfinite(float(w)) or float(w) <= 0 for w in weights.values()):
        raise ValueError("Weights must be finite and positive")
    if any(isinstance(node, bool) or not isinstance(node, int) or node < 0 for node in weights):
        raise ValueError("Vertex IDs must be nonnegative integers")
    if any(u == v or u not in weights or v not in weights for u, v in edges):
        raise ValueError("Edges must connect two known distinct vertices")
    graph = validate.make_graph(edges, k, weights, nodes=sorted(weights))
    if len(bridge.graph_components(graph)) != 1:
        raise ValueError("Connected input is required for a global connected cover")
    return graph


@dataclass
class CentralRun:
    algorithm: str
    cover: list[int]
    owner: dict[tuple[int, int], int]
    total_weight: float
    valid: bool
    vertex_cover: bool
    connected: bool
    capacity: bool
    instance_feasible: bool
    status: str
    time_ms: float
    seed: int
    violations: list[dict]
    source_revision: str = REVISION
    backend: str = "centralized-python"
    ownership_source: str = "post-run max-flow certificate; not a protocol ledger"


def solve(algorithm: str, edges, weights, k: int, *, seed: int = 42) -> CentralRun:
    if algorithm.lower() not in ALGORITHMS:
        raise ValueError(f"Unknown greedy algorithm {algorithm!r}")
    algorithm = algorithm.lower()
    graph = check_input(edges, weights, k)
    vertices = [{"id": node, "weight": float(weights[node])} for node in sorted(weights)]
    result = getattr(upstream(), f"solve_{algorithm}")(vertices, graph.edges, k, seed=seed)
    cover = sorted(result["cover"])
    capacity, owner = certificates.capacity_assignment(graph, set(cover))
    report = validate.validate(graph, cover, owner if capacity else None)
    feasible, _ = bridge.capacity_feasible(graph, set(weights))
    status = "ok" if report.valid else ("infeasible_instance" if not feasible else "invalid_solution")
    return CentralRun(algorithm.upper(), cover, owner, graph.total_weight(cover),
                      report.valid, report.vertex_cover, report.connected,
                      capacity, feasible, status, result["time_ms"], seed,
                      [{"kind": item.kind, "detail": item.detail} for item in report.violations])


def solve_gccvc(edges, weights, k, **kwargs):
    return solve("gccvc", edges, weights, k, **kwargs)


def solve_grccvc(edges, weights, k, **kwargs):
    return solve("grccvc", edges, weights, k, **kwargs)


def solve_gwccvc(edges, weights, k, **kwargs):
    return solve("gwccvc", edges, weights, k, **kwargs)
