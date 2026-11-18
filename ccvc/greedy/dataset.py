"""Strict Dagdeviren instances: preserve weights and original vertex labels."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "data/DagdevirenDataset"
FILENAME = re.compile(r"n(\d+)_m(\d+)_s(\d+)\.txt$")


@dataclass(frozen=True)
class Instance:
    path: Path
    n: int
    m: int
    seed: int
    weights: dict[int, float]
    edges: tuple[tuple[int, int], ...]
    sha256: str

    def relabeled(self) -> tuple[dict[int, float], tuple[tuple[int, int], ...], dict[int, int]]:
        """Reserve zero for the protocol; do not round or rescale weights."""
        forward = {old: index + 1 for index, old in enumerate(sorted(self.weights))}
        reverse = {new: old for old, new in forward.items()}
        weights = {forward[old]: weight for old, weight in self.weights.items()}
        edges = tuple(sorted((min(forward[u], forward[v]), max(forward[u], forward[v]))
                             for u, v in self.edges))
        return weights, edges, reverse


def read_instance(path: str | Path) -> Instance:
    path = Path(path)
    match = FILENAME.fullmatch(path.name)
    if match is None:
        raise ValueError(f"Expected n<N>_m<M>_s<S>.txt, got {path.name}")
    n, m, seed = map(int, match.groups())
    raw = path.read_bytes()
    lines = [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]
    # The repository's files have no header. Also accept an explicit n/m header.
    if len(lines) == n + m + 1 and lines[0].split() == [str(n), str(m)]:
        lines = lines[1:]
    if n < 1 or m > n * (n - 1) // 2 or len(lines) != n + m:
        raise ValueError(f"{path.name}: expected {n} weights and {m} edges; got {len(lines)} lines")
    weights: dict[int, float] = {}
    for line in lines[:n]:
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"{path.name}: malformed vertex line {line!r}")
        node, weight = int(parts[0]), float(parts[1])
        if node in weights or not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"{path.name}: duplicate vertex or nonpositive/nonfinite weight")
        weights[node] = weight
    edges: set[tuple[int, int]] = set()
    for line in lines[n:]:
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"{path.name}: malformed edge {line!r}")
        u, v = map(int, parts)
        edge = (min(u, v), max(u, v))
        if u == v or u not in weights or v not in weights or edge in edges:
            raise ValueError(f"{path.name}: self-loop, unknown endpoint or duplicate edge {edge}")
        edges.add(edge)
    adjacency = {node: set() for node in weights}
    for u, v in edges:
        adjacency[u].add(v)
        adjacency[v].add(u)
    seen, pending = set(), [min(weights)]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(adjacency[node] - seen)
    if len(seen) != n:
        raise ValueError(f"{path.name}: disconnected graph cannot have a global connected cover")
    return Instance(path, n, m, seed, weights, tuple(sorted(edges)), hashlib.sha256(raw).hexdigest())


def select_instances(directory: Path = DEFAULT_DATASET, *, n: int = 10,
                     ratio: int = 2, seeds: int = 3) -> list[Instance]:
    """Select actual paired files; missing seeds never become synthetic data."""
    if seeds not in (3, 4):
        raise ValueError("Small validation requires three or four seeds")
    files = []
    for path in directory.glob(f"n{n}_m{n * ratio}_s*.txt"):
        match = FILENAME.fullmatch(path.name)
        if match:
            files.append((int(match[3]), path))
    files.sort()
    if len(files) < seeds:
        raise ValueError(f"Requested {seeds} dataset seeds, found {len(files)} for n={n}, m={n * ratio}")
    instances = [read_instance(path) for _, path in files[:seeds]]
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        manifest_path = DEFAULT_DATASET / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Pinned dataset manifest unavailable; import the real dataset before comparisons")
    manifest = json.loads(manifest_path.read_text())
    from ccvc.greedy.central import REVISION
    if manifest.get("source_revision") != REVISION:
        raise ValueError("Dataset manifest revision differs from the audited upstream reference")
    indexed = {entry["file"]: entry["sha256"] for entry in manifest["files"]}
    if any(indexed.get(instance.path.name) != instance.sha256 for instance in instances):
        raise ValueError("Comparison file differs from the pinned Dagdeviren dataset; no synthetic substitution is allowed")
    return instances
