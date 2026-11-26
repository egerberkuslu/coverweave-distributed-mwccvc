#!/usr/bin/env python3
"""Held-out instance sets of the CoverWeave R1 pre-registration (section 3).

    python3 -m ccvc.bb.heldout --set H1|H1-large|H2a|H2b|W|M9|reserve --out DIR
    python3 -m ccvc.bb.heldout --set H1 --out DIR --seeds 1-3     # smoke run
    python3 -m ccvc.bb.heldout --validate                         # seeds 1-5

Files use the format of the published 360-file benchmark (vertex lines
`id weight` with ids 0..n-1, then sorted `u v` edge lines, name
`n<N>_m<M>_s<S>.txt`), so `matrix.load_instance` reads them unchanged. Layout:
`DIR/<family>/<param><value>/n.._m.._s...txt` plus `DIR/manifest.json` with the
generator, parameters, seed and sha256 of every file. W instances also get a
`.json` graph (`edges`, `weights`, `positions`) for `mnwifi/run.py --graph`.

Randomness is seeded from sha256(family, n, cell parameter, seed). The
pre-registered seeds are drawn only by the default path, and only once the
annotated tag coverweave-r1-frozen exists in the release repository (the check
of hga_ref.py and mnwifi/run_m7.sh); `--seeds` and `--validate` refuse them.

Set M8-weights (Amendment 1, block M8) holds the four families H1-unit,
H1-degree, H1-lognormal and H1-energy: the graph of the H1 instance with the
same n, ratio and seed under another weight law, named n.._m.._s.._<law>.txt so
that every file name is unique across the sets.
"""
from __future__ import annotations

import argparse
import bisect
import glob
import hashlib
import json
import os
import random
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc import bridge  # noqa: E402
from ccvc.bb import bbcvc, matrix, sweep  # noqa: E402
from ccvc.bb import validate as bb_validate  # noqa: E402  (validate() is defined below)
from ccvc.bb.mnwifi import topology as topo  # noqa: E402

PREREG = "paper/CoverWeave_R1/contract/R1_PREREG.md"
WEIGHT_LO, WEIGHT_HI = 20.0, 120.0
#: `mnwifi/run.py --range` default, so W coordinates need no extra flag.
RADIO_RANGE_M = 100.0
#: measured connected fraction at exact degree 4: 0.05 at n=50, 0/200 at n=100 and 200
UDG_TRIES = 2000
VALIDATION_SEEDS = tuple(range(1, 6))
#: Amendment 1, block M8: weight law of each family on the H1 graphs
WEIGHT_FAMILIES = {
    f"H1-{law}": law for law in ("unit", "degree", "lognormal", "energy")
}
M8_WEIGHTS = "M8-weights"

#: family -> (cell parameter name, cells as (n, parameter), pre-registered seeds)
FAMILIES: Dict[str, Tuple[str, List[Tuple[int, int]], Tuple[int, ...]]] = {
    "H1": (
        "ratio",
        [(n, r) for n in (10, 15, 20, 25, 50, 100, 150, 200) for r in (2, 4)],
        tuple(range(101, 111)),
    ),
    "H1-large": (
        "ratio",
        [(n, r) for n in (500, 1000) for r in (2, 4)],
        tuple(range(101, 103)),
    ),
    "H2a": (
        "deg",
        # Amendment 2: degree {6, 8}; a connected UDG at degree 4 is near impossible at n >= 100
        [(n, d) for n in (25, 50, 100, 200) for d in (6, 8)],
        tuple(range(201, 211)),
    ),
    "H2b": (
        "attach",
        [(n, a) for n in (25, 50, 100, 200) for a in (2, 4)],
        tuple(range(301, 311)),
    ),
    "W": ("deg", [(30, 6), (50, 6)], tuple(range(401, 411))),
    # Amendment 1, block M9: n is fixed by the seed (M9_SIZES[seed % 3]), cell parameter is k
    "M9": ("k", [(n, 6) for n in (20, 30, 50)], tuple(range(501, 521))),
    # Amendment 1, block M8: 30 H1 instances (n in {25,50,100}, m/n in {2,4}, seeds 101-105)
    **{
        f: (
            "ratio",
            [(n, r) for n in (25, 50, 100) for r in (2, 4)],
            tuple(range(101, 106)),
        )
        for f in WEIGHT_FAMILIES
    },
}
M9_SIZES = (20, 30, 50)
RESERVE_FIRST = 901  # the reserve covers the section 3 families, not M9
PREREGISTERED = frozenset(
    s for _, _, seeds in FAMILIES.values() for s in seeds
) | frozenset(range(RESERVE_FIRST, RESERVE_FIRST + 10))

Edges = List[Tuple[int, int]]
Positions = Dict[int, Tuple[float, float]]


def derived_seed(family: str, n: int, param: int, seed: int) -> int:
    digest = hashlib.sha256(
        f"coverweave-r1:{family}:{n}:{param}:{seed}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _weights(n: int, rng: random.Random) -> Dict[int, float]:
    return {v: WEIGHT_LO + (WEIGHT_HI - WEIGHT_LO) * rng.random() for v in range(n)}


def _barabasi_albert(n: int, a: int, rng: random.Random) -> Edges:
    """Star on a+1 nodes, then each new node attaches to `a` distinct nodes by degree."""
    edges = {(0, v) for v in range(1, a + 1)}
    repeated = [0] * a + list(range(1, a + 1))  # each node once per incident edge
    for v in range(a + 1, n):
        targets: set = set()
        while len(targets) < a:
            targets.add(rng.choice(repeated))
        edges |= {(t, v) for t in targets}
        repeated += sorted(targets) + [v] * a
    return sorted(edges)


def generate_one(
    family: str, n: int, param: int, seed: int
) -> Tuple[Dict[int, float], Edges, Optional[Positions]]:
    """One instance: weights and sorted edges on ids 0..n-1; positions for W (ids 1..n)."""
    s = derived_seed(family, n, param, seed)
    rng = random.Random(s)
    pos: Optional[Positions] = None
    if family in ("H1", "H1-large"):
        # all 360 published files contain the path 0-1-..-(n-1); a random recursive
        # tree (sweep.synthetic_instance) gave too many degree-1 nodes (validation)
        edge_set = {(v, v + 1) for v in range(n - 1)}
        while len(edge_set) < n * param:  # every H1 cell has n * param <= C(n, 2)
            u, v = sorted(rng.sample(range(n), 2))
            edge_set.add((u, v))
        edges = sorted(edge_set)
    elif family == "H2b":
        edges = _barabasi_albert(n, param, rng)
    elif family == "M9":
        edges = _flow_infeasible(n, param, rng)
    elif family in WEIGHT_FAMILIES:
        # the graph of the H1 instance with this seed, so block M8 pairs on graphs
        edges = generate_one("H1", n, param, seed)[1]
        weights = _law_weights(WEIGHT_FAMILIES[family], n, edges, rng)
        sweep.prepare(weights, edges)  # a quantized weight that overflows fails here
        return weights, edges, None
    else:  # H2a, W
        edges, pos = _unit_disk_graph(n, param, rng)
        if family != "W":
            pos = None
    return _weights(n, rng), edges, pos


def _law_weights(
    law: str, n: int, edges: Edges, rng: random.Random
) -> Dict[int, float]:
    """Block M8 weight laws. A common factor leaves the optimal cover unchanged;
    WEIGHT_LO keeps lognormal and energy weights where weight_scale 10 quantizes
    them with a small error and below the 16.16 key limit of sweep.prepare."""
    if law == "unit":
        return {v: 1.0 for v in range(n)}
    if law == "degree":
        deg = Counter(v for e in edges for v in e)
        return {v: float(deg[v]) for v in range(n)}
    if law == "lognormal":
        return {v: WEIGHT_LO * rng.lognormvariate(0.0, 1.0) for v in range(n)}
    # inverse residual energy, energy uniform on [0.1, 1]
    return {v: WEIGHT_LO / rng.uniform(0.1, 1.0) for v in range(n)}


def _connected(n: int, edges: Edges) -> bool:
    adj: List[List[int]] = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    seen, stack = {0}, [0]
    while stack:
        for y in adj[stack.pop()]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return len(seen) == n


def _flow_infeasible(n: int, k: int, rng: random.Random) -> Edges:
    """Connected, infeasible by the flow check, silent counting bound and degree-gap witness.

    A near-clique S with |E(S)| = k|S| + 1..3 cannot own its own edges, since an
    owner is an endpoint and S has capacity k|S|. Every S node keeps degree >= k, and
    a sparse connected remainder R with |E(R)| >= the excess keeps sum(min(deg, k)) >= m
    and m <= nk. The three checks below are re-run, so a draw that slips fails loudly.
    """
    s = rng.choice((2 * k + 2, 2 * k + 3))  # smallest sizes with C(s, 2) > k * s
    labels = list(range(n))
    rng.shuffle(labels)
    S, R = labels[:s], labels[s:]
    clique = [(min(a, b), max(a, b)) for i, a in enumerate(S) for b in S[i + 1 :]]
    excess = rng.randint(1, 3)
    for _ in range(100):
        edges = set(rng.sample(clique, k * s + excess))
        deg_s = Counter(v for e in edges for v in e)
        if min(deg_s[v] for v in S) >= k:
            break
    else:
        raise RuntimeError(f"M9 n={n}: no near-clique with min degree {k}")
    for i, v in enumerate(R):  # random tree on R, its first node hangs on S
        u = rng.choice(R[:i] if i else S)
        edges.add((min(u, v), max(u, v)))
    for _ in range(rng.randint(0, 2)):  # extra S-R edges
        u, v = rng.choice(S), rng.choice(R)
        edges.add((min(u, v), max(u, v)))
    for _ in range(rng.randint(0, len(R) // 4)):  # extra R-R edges
        u, v = sorted(rng.sample(R, 2))
        edges.add((u, v))
    edges = sorted(edges)
    m, deg = len(edges), Counter(v for e in edges for v in e)
    flow_ok, _ = bridge.capacity_feasible(
        bb_validate.make_graph(edges, k, nodes=list(range(n))), set(range(n))
    )  # the flow check of sweep.instance_feasibility, with C = V
    if (
        flow_ok
        or bbcvc.counting_bound_infeasible(n, m, k)
        or bbcvc.degree_deficiency_infeasible([deg[v] for v in range(n)], m, k)
        or not _connected(n, edges)
    ):
        raise RuntimeError(
            f"M9 n={n} m={m}: construction is not a hidden infeasible instance"
        )
    return edges


def _unit_disk_graph(n: int, deg: int, rng: random.Random) -> Tuple[Edges, Positions]:
    """Connected UDG with exactly m = n*deg/2 edges, by rejection.

    mnwifi.run.unit_disk_graph shrinks the side until connected, which moved the
    realised degree away from the target (deg 4 and 8 cells overlapped), so the
    density is fixed exactly here and disconnected draws are redrawn.
    """
    m = n * deg // 2
    for _ in range(UDG_TRIES):
        p = [(rng.random(), rng.random()) for _ in range(n)]
        pairs = sorted(
            ((p[i][0] - p[j][0]) ** 2 + (p[i][1] - p[j][1]) ** 2, i, j)
            for i in range(n)
            for j in range(i + 1, n)
        )
        edges = sorted((i, j) for _, i, j in pairs[:m])
        if not _connected(n, edges):
            continue
        # range halfway between the m-th and (m+1)-th distance, scaled to RADIO_RANGE_M
        scale = 2 * RADIO_RANGE_M / (pairs[m - 1][0] ** 0.5 + pairs[m][0] ** 0.5)
        pos = {
            i + 1: (round(x * scale, 2), round(y * scale, 2))
            for i, (x, y) in enumerate(p)
        }
        # make_plan rounds to 0.01 m too; keep only draws whose rounded positions realise `edges`
        if sorted(topo.realised_edges(pos, RADIO_RANGE_M)) == [
            (u + 1, v + 1) for u, v in edges
        ]:
            return edges, pos
    raise RuntimeError(
        f"no connected unit disk graph with n={n}, average degree {deg} in {UDG_TRIES} draws"
    )


def instance_text(weights: Dict[int, float], edges: Edges) -> str:
    lines = [f"{v} {weights[v]!r}" for v in range(len(weights))]
    return "\n".join(lines + [f"{u} {v}" for u, v in edges]) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan(
    set_name: str, seeds: Optional[Sequence[int]] = None
) -> List[Tuple[str, int, int, int]]:
    """(family, n, param, seed) for every instance of a set."""
    if set_name == M8_WEIGHTS:
        return [x for f in WEIGHT_FAMILIES for x in plan(f, seeds)]
    if set_name == "reserve":
        return [
            x
            for f, (_, _, pre) in FAMILIES.items()
            if f != "M9" and f not in WEIGHT_FAMILIES
            for x in plan(
                f,
                range(RESERVE_FIRST, RESERVE_FIRST + len(pre))
                if seeds is None
                else seeds,
            )
        ]
    _, cells, pre = FAMILIES[set_name]
    seeds = pre if seeds is None else seeds
    if set_name == "M9":
        return [("M9", M9_SIZES[s % 3], cells[0][1], s) for s in seeds]
    return [(set_name, n, p, s) for n, p in cells for s in seeds]


def generate(set_name: str, out: Path, seeds: Optional[Sequence[int]] = None) -> Dict:
    """Write one set and its manifest. `seeds=None` draws the pre-registered seeds."""
    from ccvc.bb.hga_ref import RELEASE_REPO, TAG, frozen_tag_exists

    if seeds is None and not frozen_tag_exists():
        raise PermissionError(
            f"set {set_name} draws pre-registered seeds; held-out instances are "
            f"generated only after the annotated tag {TAG} exists in {RELEASE_REPO}"
        )
    if seeds is not None and PREREGISTERED.intersection(seeds):
        raise ValueError(
            f"pre-registered seeds are drawn only without --seeds: "
            f"{sorted(PREREGISTERED.intersection(seeds))}"
        )
    out = Path(out)
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"{manifest_path} exists; a held-out set is written once")
    files = []
    # draw everything before writing, so a failing cell leaves no partial set on disk
    drawn = [(*c, generate_one(*c)) for c in plan(set_name, seeds)]
    for family, n, param, seed, (weights, edges, pos) in drawn:
        pname = FAMILIES[family][0]
        cell_dir = out / family / f"{pname}{param}"
        cell_dir.mkdir(parents=True, exist_ok=True)
        law = f"_{WEIGHT_FAMILIES[family]}" if family in WEIGHT_FAMILIES else ""
        path = cell_dir / f"n{n}_m{len(edges)}_s{seed}{law}.txt"
        path.write_text(instance_text(weights, edges))
        entry = {
            "file": str(path.relative_to(out)),
            "family": family,
            pname: param,
            "n": n,
            "m": len(edges),
            "seed": seed,
            "rng_seed": derived_seed(family, n, param, seed),
            "sha256": _sha256(path),
        }
        if pos is not None:
            # same relabelling (old id + 1) and unscaled weights as greedy/compare.py graphs
            graph = path.with_suffix(".json")
            graph.write_text(
                json.dumps(
                    {
                        "edges": [[u + 1, v + 1] for u, v in edges],
                        "weights": {str(v + 1): w for v, w in weights.items()},
                        "positions": {str(i): list(p) for i, p in sorted(pos.items())},
                        "radio_range_m": RADIO_RANGE_M,
                        "source": "heldout",
                        "source_file": path.name,
                        "source_sha256": entry["sha256"],
                        "original_labels": {str(v + 1): v for v in range(n)},
                        "weight_transform": "none",
                    },
                    indent=2,
                )
                + "\n"
            )
            entry.update(
                graph_json=str(graph.relative_to(out)), graph_json_sha256=_sha256(graph)
            )
        files.append(entry)
    here = Path(__file__).resolve().parent
    manifest = {
        "generator": "ccvc.bb.heldout",
        "set": set_name,
        "preregistration": PREREG,
        "preregistered_seeds": seeds is None,
        "parameters": {
            "families": {
                f: {
                    "cell_parameter": p,
                    "cells": [list(c) for c in cells],
                    "seeds": list(pre),
                }
                for f, (p, cells, pre) in FAMILIES.items()
            },
            "reserve_first_seed": RESERVE_FIRST,
            "seeds_override": list(seeds or []),
            "weights": f"uniform [{WEIGHT_LO:g}, {WEIGHT_HI:g}), all families except "
            f"the M8 weight families",
            "M8_weights": f"graph of the H1 instance with the same n, ratio and seed; "
            f"H1-unit w = 1, H1-degree w = degree, H1-lognormal w = {WEIGHT_LO:g} * "
            f"exp(N(0, 1)), H1-energy w = {WEIGHT_LO:g} / E with E uniform on [0.1, 1]; "
            f"file name suffix _<law>",
            "H1": "spanning path 0-1-..-(n-1) as in the published files, plus uniform "
            "extra edges until m = n * ratio",
            "H2a_W": f"uniform points in a square, range halfway between the m-th and "
            f"(m+1)-th pair distance so m = n * deg / 2 exactly, redrawn until connected "
            f"(at most {UDG_TRIES} draws); coordinates scaled to radio_range_m="
            f"{RADIO_RANGE_M:g} and rounded to 0.01 m, draws whose rounding changes an "
            f"edge are redrawn",
            "H2b": "Barabasi-Albert from a star on attach+1 nodes, m = attach * (n - attach)",
            "M9": "n = (20, 30, 50)[seed % 3], k = 6: near-clique S (|S| in {14, 15}, "
            "|E(S)| = k|S| + 1..3, S degrees >= k) plus a random tree on the rest and a few "
            "extra edges; each file is confirmed infeasible by the flow check "
            "(bridge.capacity_feasible, C = V) with the counting bound and the degree-gap "
            "witness silent",
            "rng_seed": "first 8 bytes of sha256('coverweave-r1:<family>:<n>:<param>:<seed>')",
        },
        "python": sys.version.split()[0],
        "source_sha256": {
            str(p.relative_to(here.parent.parent)): _sha256(p)
            for p in (
                here / "heldout.py",
                here / "mnwifi" / "topology.py",
            )
        },
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


# --------------------------------------------------------------------------
# validation of the H1 generator against the published files
# --------------------------------------------------------------------------
def ks_statistic(a: Sequence[float], b: Sequence[float]) -> float:
    """Two-sample Kolmogorov-Smirnov D: largest gap between the two ECDFs."""
    a, b = sorted(a), sorted(b)
    return max(
        abs(bisect.bisect_right(a, x) / len(a) - bisect.bisect_right(b, x) / len(b))
        for x in set(a) | set(b)
    )


def _graph_stats(graphs: Sequence[Tuple[Dict[int, float], Edges]]) -> Dict:
    degrees, mins, maxs, weights = [], [], [], []
    for w, edges in graphs:
        deg = {v: 0 for v in w}
        for u, v in edges:
            deg[u] += 1
            deg[v] += 1
        degrees += list(deg.values())
        mins.append(min(deg.values()))
        maxs.append(max(deg.values()))
        weights += list(w.values())
    return {
        "degrees": degrees,
        "min_deg": statistics.mean(mins),
        "max_deg": statistics.mean(maxs),
        "w_min": min(weights),
        "w_max": max(weights),
        "w_mean": statistics.mean(weights),
    }


def validate(
    seeds: Iterable[int] = VALIDATION_SEEDS,
    directory: Optional[str] = None,
    cells: Optional[Sequence[Tuple[str, int, int]]] = None,
) -> List[Dict]:
    """Per H1 cell: KS D of pooled degrees (generated vs published, and published
    first half vs second half as the noise reference), mean per-file min and max
    degree, weight range and mean."""
    seeds = list(seeds)
    if PREREGISTERED.intersection(seeds):
        raise ValueError("validation never uses a pre-registered seed")
    d = directory or matrix.dataset_dir()
    if d is None:
        raise FileNotFoundError("published dataset not found (set MWCCVC_DATASET)")
    cells = cells or [(f, n, r) for f in ("H1", "H1-large") for n, r in FAMILIES[f][1]]
    rows = []
    for family, n, r in cells:
        paths = sorted(
            glob.glob(os.path.join(d, f"n{n}_m{n * r}_s*.txt")),
            key=lambda p: int(p.rsplit("_s", 1)[1][:-4]),
        )
        pub = [matrix.load_instance(p) for p in paths]
        pub = [(w, list(e)) for w, e in pub]
        gen = [generate_one(family, n, r, s)[:2] for s in seeds]
        gs, ps = _graph_stats(gen), _graph_stats(pub)
        half = len(pub) // 2
        ref = (
            ks_statistic(
                _graph_stats(pub[:half])["degrees"], _graph_stats(pub[half:])["degrees"]
            )
            if half
            else None
        )
        rows.append(
            {
                "n": n,
                "m": n * r,
                "files_pub": len(pub),
                "files_gen": len(gen),
                "ks_gen_pub": ks_statistic(gs["degrees"], ps["degrees"]),
                "ks_pub_halves": ref,
                "gen": {k: v for k, v in gs.items() if k != "degrees"},
                "pub": {k: v for k, v in ps.items() if k != "degrees"},
            }
        )
    return rows


def validation_table(rows: Sequence[Dict]) -> str:
    out = [
        "| n | m | pub files | KS D gen vs pub | KS D pub halves | min deg gen/pub "
        "| max deg gen/pub | w min gen/pub | w max gen/pub | w mean gen/pub |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        g, p = r["gen"], r["pub"]
        ref = "n/a" if r["ks_pub_halves"] is None else f"{r['ks_pub_halves']:.3f}"
        out.append(
            f"| {r['n']} | {r['m']} | {r['files_pub']} | {r['ks_gen_pub']:.3f} | {ref} "
            f"| {g['min_deg']:.1f}/{p['min_deg']:.1f} | {g['max_deg']:.1f}/{p['max_deg']:.1f} "
            f"| {g['w_min']:.2f}/{p['w_min']:.2f} | {g['w_max']:.2f}/{p['w_max']:.2f} "
            f"| {g['w_mean']:.2f}/{p['w_mean']:.2f} |"
        )
    return "\n".join(out)


def parse_seeds(text: str) -> List[int]:
    """`1-3` or `1,2,5`."""
    if "-" in text:
        lo, hi = map(int, text.split("-"))
        return list(range(lo, hi + 1))
    return [int(x) for x in text.split(",") if x.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", choices=(*FAMILIES, M8_WEIGHTS, "reserve"))
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--seeds",
        type=parse_seeds,
        default=None,
        help="smoke/test seeds such as 1-3; pre-registered seeds are refused",
    )
    ap.add_argument(
        "--validate",
        action="store_true",
        help="compare the H1 generator with the published files (seeds 1-5)",
    )
    a = ap.parse_args(argv)
    if a.validate:
        print(validation_table(validate(a.seeds or VALIDATION_SEEDS)))
        return 0
    if not (a.set and a.out):
        ap.error("--set and --out are required unless --validate is given")
    try:
        m = generate(a.set, a.out, a.seeds)
    except PermissionError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 2
    print(f"{len(m['files'])} instances -> {a.out}/manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
