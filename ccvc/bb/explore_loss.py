#!/usr/bin/env python3
"""Bounded exhaustive drop-pattern explorer for the simulator (task X1).

WHAT IT DOES. For every small instance (all connected graphs up to isomorphism
for n = 3..5, a fixed sample for n = 6, two weight vectors, capacity k = 1..3),
every arm and every scheduler, it runs the protocol once lossless, records each
frame decision of the channel, and then re-runs the instance under every drop
pattern of a bounded space:

  single  drop the i-th frame of type T on the directed link s->d
  burst   drop b consecutive frames (any type) on s->d, starting at its frame st
  pair    drop one frame on each of two different directed links

Each run is checked against every property in `check_run`; every violation is
kept with its full reproduction (graph, weights, k, arm, scheduler, pattern),
and `minimise` reduces a reproduction to a 1-minimal set of dropped frames.

THE HOOK. SimNet already has a deterministic fault predicate
`drop(t_ms, src, dst, msg_type)` at its single loss decision point
(`SimNet._drops`), reached by `run_bbcvc(drop=...)` and `run_v4(drop=...)`. It
is called exactly once per frame per receiver, so a stateful callable can count
frames per link and per type. No protocol file is edited. `Dropper` is a class,
not a closure, so the twin that `run_bbcvc` deep-copies to measure silence gets
its own counters.

INDEX SEMANTICS. Indices count frames of the PERTURBED run. The run is
deterministic and identical to the lossless one up to the first drop, so every
first drop of a pattern is a frame of the lossless trace; later indices may
name frames the lossless run never sent. A pattern that ends up dropping no
frame is the lossless run again and is not run twice (`deduped_zero`). Two
patterns that drop the same frames give the same run; only the first counts
(`deduped_same`). A burst that dropped fewer than b frames ran out of frames,
so every longer burst from the same start is the same run and is skipped.

USAGE (run from a tree root so that `ccvc` resolves to the tree under test):
  python3 -m ccvc.bb.explore_loss explore --out DIR [--procs 3] [--tier full]
  python3 -m ccvc.bb.explore_loss report  --out DIR      (aggregates, minimises)
  python3 -m ccvc.bb.explore_loss replay  FILE.json      (one reproduction)

Simulator seed 0 everywhere; no sealed seed is used.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import sys
import time
import traceback
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

if "ccvc" not in sys.modules:  # appended: a PYTHONPATH tree under test wins
    sys.path.append(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

Edge = Tuple[int, int]
SEALED = (
    set(range(101, 111))
    | set(range(201, 211))
    | set(range(301, 311))
    | set(range(401, 411))
    | set(range(501, 521))
    | set(range(901, 911))
)
SIM_SEED = 0
assert SIM_SEED not in SEALED
HELLO = 0
MAX_MS = 200_000

#: Bounds of the pattern space, per tier. `burst_starts` is the number of
#: evenly spaced start frames per directed link; `pair_cap` caps the pairs per
#: configuration (a deterministic sample when there are more).
TIERS = {
    "full": dict(
        bursts=(2, 3, 5, 8, 13, 21, 34, 55, 89, 144),
        burst_starts=4,
        pair_cap=200,
        single_cap=300,
        n6=6,
    ),
    "quick": dict(
        bursts=(2, 5, 13, 34, 89), burst_starts=3, pair_cap=40, single_cap=60, n6=3
    ),
}

#: Node fields that must be empty or None once the network is silent.
ZERO_FIELDS = (
    "_pending",
    "_push_job",
    "_far_job",
    "_fix_key",
    "_echo_due",
    "_ghs_deferred_set",
    "_cert_job",
)


# --------------------------------------------------------------------------
# the hook
# --------------------------------------------------------------------------
class Dropper:
    """Stateful drop predicate for `SimNet(drop=...)`.

    frames  {(s, d, T, i)}          i-th frame of type T on s->d
    bursts  [(s, d, st, b)]         link frames st .. st+b-1 on s->d, any type
    windows [(s, d, T, t0, t1)]     every frame of type T (-1: any) on s->d with
                                    t0 <= t_ms < t1 (the hand-built form of V4)
    """

    def __init__(self, frames=(), bursts=(), windows=(), record: bool = False) -> None:
        self.frames = frozenset(tuple(int(x) for x in f) for f in frames)
        self.bursts = tuple(tuple(int(x) for x in b) for b in bursts)
        self.windows = tuple(tuple(int(x) for x in w) for w in windows)
        self.n_type: Dict[Tuple[int, int, int], int] = {}
        self.n_link: Dict[Tuple[int, int], int] = {}
        self.dropped: List[Tuple[int, int, int, int, int, int]] = []
        self.trace: Optional[List[Tuple[int, int, int, int, int, int]]] = (
            [] if record else None
        )

    def __call__(self, t: int, s: int, d: int, m: int) -> bool:
        m = int(m)
        it = self.n_type.get((s, d, m), 0)
        self.n_type[(s, d, m)] = it + 1
        il = self.n_link.get((s, d), 0)
        self.n_link[(s, d)] = il + 1
        rec = (int(t), s, d, m, it, il)
        if self.trace is not None:
            self.trace.append(rec)
        hit = (
            (s, d, m, it) in self.frames
            or any(
                s == a and d == b and st <= il < st + n for a, b, st, n in self.bursts
            )
            or any(
                s == a and d == b and (T < 0 or T == m) and t0 <= t < t1
                for a, b, T, t0, t1 in self.windows
            )
        )
        if hit:
            self.dropped.append(rec)
        return hit

    def keys(self) -> Tuple[Tuple[int, int, int, int], ...]:
        """The dropped frames as explicit (s, d, T, i) keys: replaying them as
        `frames` gives the same run, because the prefix before each is the same."""
        return tuple((s, d, m, it) for _, s, d, m, it, _ in self.dropped)


def pattern_dict(frames=(), bursts=(), windows=()) -> Dict[str, list]:
    return {
        "frames": [list(f) for f in frames],
        "bursts": [list(b) for b in bursts],
        "windows": [list(w) for w in windows],
    }


# --------------------------------------------------------------------------
# instances
# --------------------------------------------------------------------------
def small_graphs(n6_sample: int) -> List[Tuple[str, int, Tuple[Edge, ...]]]:
    """All connected graphs up to isomorphism for n = 3..5 (atlas order) and a
    fixed sample of n = 6. Nodes are 1..n."""
    import networkx as nx

    by_n: Dict[int, list] = defaultdict(list)
    for g in nx.graph_atlas_g():
        n = g.number_of_nodes()
        if 3 <= n <= 6 and nx.is_connected(g):
            by_n[n].append(g)
    out = []
    for n in (3, 4, 5, 6):
        gs = by_n[n]
        if n == 6:
            # a fixed sample of 12; a smaller tier takes the first in run order
            idx = sorted(random.Random("x1-n6").sample(range(len(gs)), 12), key=str)
            idx = sorted(idx[:n6_sample])
            gs = [gs[i] for i in idx]
        for j, g in enumerate(gs):
            es = tuple(sorted((min(u, v) + 1, max(u, v) + 1) for u, v in g.edges()))
            out.append((f"n{n}g{j}" if n < 6 else f"n6a{idx[j]}", n, es))
    return out


def weight_vectors(name: str, n: int) -> List[Tuple[str, Dict[int, float]]]:
    rng = random.Random("x1-w-" + name)
    return [
        ("u", {i: 1.0 for i in range(1, n + 1)}),
        ("r", {i: float(rng.choice((1, 2, 3))) for i in range(1, n + 1)}),
    ]


def configs(
    tier: str, arms: Sequence[str], scheds: Sequence[str]
) -> List[Dict[str, Any]]:
    out = []
    for name, n, es in small_graphs(TIERS[tier]["n6"]):
        for wname, w in weight_vectors(name, n):
            for k in (1, 2, 3):
                for arm in arms:
                    for sch in scheds:
                        out.append(
                            dict(
                                graph=name,
                                n=n,
                                edges=[list(e) for e in es],
                                weights={str(i): x for i, x in w.items()},
                                wname=wname,
                                k=k,
                                arm=arm,
                                sched=sch,
                            )
                        )
    return out


# --------------------------------------------------------------------------
# one run and its properties
# --------------------------------------------------------------------------
def _instance(cfg) -> Tuple[List[Edge], Dict[int, float], int]:
    return (
        [tuple(e) for e in cfg["edges"]],
        {int(i): float(x) for i, x in cfg["weights"].items()},
        int(cfg["k"]),
    )


def run_one(cfg, pattern: Optional[Dict[str, list]] = None, record: bool = False):
    """(run or None, Dropper, exception text or None)."""
    from ccvc.bb import bbcvc

    edges, w, k = _instance(cfg)
    pat = pattern or {}
    dr = Dropper(
        pat.get("frames", ()), pat.get("bursts", ()), pat.get("windows", ()), record
    )
    try:
        if cfg["arm"] == "mis":
            res = bbcvc.run_bbcvc(
                edges,
                w,
                k,
                scheduler=cfg["sched"],
                drop=dr,
                max_ms=MAX_MS,
                seed=SIM_SEED,
            )
        elif cfg["arm"] == "ghs":
            from ccvc.bb import v4_mst

            res = v4_mst.run_v4(
                edges,
                w,
                k,
                scheduler=cfg["sched"],
                drop=dr,
                max_ms=MAX_MS,
                seed=SIM_SEED,
            )
        else:
            raise ValueError(cfg["arm"])
    except Exception as exc:  # noqa: BLE001  -- an exception IS a finding
        tb = traceback.extract_tb(exc.__traceback__)
        where = next(
            (
                f"{os.path.basename(f.filename)}:{f.lineno}"
                for f in reversed(tb)
                if "explore_loss" not in f.filename
            ),
            "?",
        )
        return None, dr, f"{type(exc).__name__} at {where}: {exc}"[:300]
    return res, dr, None


def feasible(cfg) -> bool:
    """Exact feasibility: a connected graph has a valid capacitated connected
    cover iff C = V admits an edge assignment of load <= k (more cover only
    helps capacity, and V is connected). Max-flow check of `ccvc.bridge`."""
    from ccvc import bridge
    from ccvc.bb import validate

    edges, w, k = _instance(cfg)
    g = validate.make_graph(edges, k, w, nodes=sorted(w))
    return bool(bridge.capacity_feasible(g, set(w))[0])


def handoff_wait_ms() -> int:
    from ccvc.bb.bbcvc import BbcvcParams

    p = BbcvcParams()
    # older trees have no adaptive window; 48 is the cap the live tree uses
    return 2 * getattr(p, "stale_periods_cap", 48) * p.t_hello_ms


def check_run(
    cfg, res, dr: Dropper, exc: Optional[str], feas: bool, base_solved: Optional[bool]
) -> List[Tuple[str, str]]:
    """Every property of one run. Returns [(property, detail)]; empty = clean.

    Properties, in order: exception; truncated (no quiescence within MAX_MS);
    not_silent (frames after quiescence, on the twin); false_solved (verdict
    solved, the final discovered graph infeasible); false_infeasible
    (infeasibility flag, discovered graph feasible); unresolved_feasible
    (discovered graph feasible, the lossless run solved it, this run says
    unresolved); the same three against the planned graph only, when the
    discovered graph lacks planned links, are the INFO tags *_reduced;
    invalid_discovered (solved but invalid on the
    final discovered graph: cover, connectivity); double_owned (an edge claimed
    by both ends, any verdict); unowned (a discovered edge nobody owns, any
    verdict); capacity (solved and a node holds more than k); epoch_split (nodes
    in different epochs; `epoch_split_exempt` when the pattern holds a burst on
    one link whose span is at least the hand-off wait, Amendment 10); nonzero
    (a node field of ZERO_FIELDS not empty at silence).
    """
    from ccvc.bb import validate

    if exc is not None:
        return [("exception", exc)]
    out: List[Tuple[str, str]] = []
    if not res.converged:
        return [("truncated", f"verdict {res.verdict}, no quiescence in {MAX_MS} ms")]
    if res.tx_after_convergence:
        out.append(("not_silent", f"{res.tx_after_convergence} tx after quiescence"))
    edges, w, k = _instance(cfg)
    disc = sorted({(min(u, v), max(u, v)) for u, v in res.discovered_edges})
    # The verdict is about the graph the nodes discovered (Amendment 4): a
    # one-way loss can remove a planned link, and the reduced graph may be
    # feasible where the planned one is not, or the reverse. Per component,
    # since C = V is the best case of every component.
    if set(disc) == {(min(u, v), max(u, v)) for u, v in edges}:
        feas_d = feas
    else:
        from ccvc import bridge

        feas_d = bool(bridge.capacity_feasible(validate.make_graph(disc, k, w, nodes=sorted(w)),
                                               set(w))[0])
    reduced = f"planned {'feasible' if feas else 'infeasible'}, discovered graph lacks " \
        f"{len({(min(u, v), max(u, v)) for u, v in edges} - set(disc))} planned links"
    if res.verdict == "solved" and not feas_d:
        out.append(("false_solved", "solved, discovered graph infeasible"))
    elif res.verdict == "solved" and not feas:
        out.append(("solved_reduced", reduced))
    # The counting bound is run-level arithmetic on the planned graph; a node's
    # own flag (in-network certificate) is about what it discovered.
    node_flag = any(getattr(n, "infeasible", False) for n in res.nodes.values()) \
        or bool(getattr(res, "infeasible_in_network", None))
    if res.infeasible_reason in ("counting_bound", "degree_deficiency") and feas:
        out.append(("false_infeasible", f"reason {res.infeasible_reason}, planned graph feasible"))
    if node_flag and feas_d:
        out.append(("false_infeasible", "node flag, discovered graph feasible"))
    elif node_flag and feas:
        out.append(("infeasible_reduced", "node flag, " + reduced))
    if feas_d and base_solved and res.verdict == "unresolved":
        out.append(("unresolved_feasible", "lossless run solves it, discovered graph feasible"))
    elif feas and base_solved and res.verdict == "unresolved":
        out.append(("unresolved_reduced", reduced))
    double = dict(res.double_claimed or {})
    if double:
        out.append(
            (
                "double_owned",
                ", ".join(f"{e}:{tuple(v)}" for e, v in sorted(double.items())),
            )
        )
    unowned = [e for e in disc if e not in res.owner]
    if unowned:
        out.append(("unowned", f"{unowned}"))
    if res.verdict == "solved":
        g = validate.make_graph(disc, k, w, nodes=sorted(w))
        mode = (
            validate.STRICT
            if len(validate.graph_components(g)) <= 1
            else validate.PER_COMPONENT
        )
        rep = validate.validate(
            g,
            res.cover,
            {e: o for e, o in res.owner.items() if e in disc},
            connectivity=mode,
        )
        kinds = sorted(
            {
                v.kind
                for v in rep.violations
                if v.kind not in ("overload", "forced_overload")
            }
        )
        if not rep.valid and kinds:
            out.append(("invalid_discovered", ",".join(kinds)))
        load = Counter(res.owner.values())
        for e, who in double.items():
            load.update(x for x in who if x != res.owner.get(e))
        over = {v: c for v, c in load.items() if c > k}
        if over:
            out.append(("capacity", f"{over}"))
    epochs = {lab: n.epoch for lab, n in res.nodes.items()}
    if len(set(epochs.values())) > 1:
        span = 0
        per_link: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for t, s, d, *_ in dr.dropped:
            per_link[(s, d)].append(t)
        span = max((max(ts) - min(ts) for ts in per_link.values()), default=0)
        tag = "epoch_split_exempt" if span >= handoff_wait_ms() else "epoch_split"
        out.append((tag, f"epochs {epochs}, longest one-link drop span {span} ms"))
    nz = []
    for lab, n in sorted(res.nodes.items()):
        for f in ZERO_FIELDS:
            if hasattr(n, f) and getattr(n, f) not in (
                None,
                (),
                [],
                {},
                set(),
                frozenset(),
            ):
                nz.append(f"{lab}.{f}")
    if nz:
        out.append(("nonzero", ",".join(nz)))
    return out


VIOLATIONS = (
    "exception",
    "truncated",
    "not_silent",
    "false_solved",
    "false_infeasible",
    "unresolved_feasible",
    "invalid_discovered",
    "double_owned",
    "unowned",
    "capacity",
    "epoch_split",
    "nonzero",
)
INFO = ("epoch_split_exempt", "solved_reduced", "infeasible_reduced", "unresolved_reduced")


# --------------------------------------------------------------------------
# the bounded pattern space of one configuration
# --------------------------------------------------------------------------
def explore_config(cfg, tier: str = "full", keep: int = 3) -> Dict[str, Any]:
    """Run the whole pattern space of one configuration. Returns counts, and up
    to `keep` reproductions per property."""
    b = TIERS[tier]
    t0 = time.time()
    feas = feasible(cfg)
    base, bdr, bexc = run_one(cfg, record=True)
    summary: Dict[str, Any] = dict(
        cfg=cfg,
        feasible=feas,
        runs=1,
        deduped_zero=0,
        deduped_same=0,
        generated=0,
        counts={},
        repros={},
    )
    bviol = check_run(cfg, base, bdr, bexc, feas, None)
    summary["baseline"] = dict(
        verdict=getattr(base, "verdict", None), viol=bviol, frames=len(bdr.trace or ())
    )
    if bexc is not None or base is None:
        summary["wall_s"] = time.time() - t0
        return summary
    base_solved = base.verdict == "solved"
    trace = list(bdr.trace)
    counts: Counter = Counter()
    repros: Dict[str, list] = defaultdict(list)
    seen = set()

    def do(kind: str, pat: Dict[str, list]) -> Optional[Dropper]:
        summary["generated"] += 1
        res, dr, exc = run_one(cfg, pat)
        summary["runs"] += 1
        if not dr.dropped and exc is None:
            summary["deduped_zero"] += 1
            return dr
        sig = dr.keys()
        if sig in seen:
            summary["deduped_same"] += 1
            return dr
        seen.add(sig)
        counts["distinct_" + kind] += 1
        for prop, detail in check_run(cfg, res, dr, exc, feas, base_solved):
            counts[prop] += 1
            if len(repros[prop]) < keep:
                repros[prop].append(
                    dict(
                        kind=kind,
                        pattern=pat,
                        drops=len(dr.dropped),
                        keys=[list(x) for x in sig],
                        detail=detail,
                    )
                )
        return dr

    # single frames: every frame decision of the lossless run, or, past
    # `single_cap`, every non-HELLO frame first and evenly spaced HELLOs after.
    # shortcut: the cap only bites on long infeasible (k = 1) repairs.
    singles = [(s, d, m, it) for _, s, d, m, it, _ in trace]
    chosen = singles
    if len(singles) > b["single_cap"]:
        other = [f for f in singles if f[2] != HELLO][: b["single_cap"]]
        hello = [f for f in singles if f[2] == HELLO]
        room = b["single_cap"] - len(other)
        step = max(1, -(-len(hello) // max(1, room)))
        chosen = other + hello[::step][:room]
        summary["singles_capped"] = len(singles)
    for f in chosen:
        do("single", pattern_dict(frames=[f]))
    # bursts: evenly spaced starts per directed link, growing lengths
    link_n = Counter((s, d) for _, s, d, *_ in trace)
    for (s, d), c in sorted(link_n.items()):
        step = max(1, -(-c // b["burst_starts"]))
        for st in range(0, c, step):
            for n in b["bursts"]:
                dr = do("burst", pattern_dict(bursts=[(s, d, st, n)]))
                if dr is not None and len(dr.dropped) < n:
                    break  # ran out of frames: every longer burst is this run
    # pairs: one frame on each of two different directed links
    rng = random.Random("x1-pairs-" + json.dumps(cfg, sort_keys=True))
    if len(singles) <= 200:
        pairs = [(a, c) for a, c in itertools.combinations(singles, 2) if a[:2] != c[:2]]
        if len(pairs) > b["pair_cap"]:
            pairs = rng.sample(pairs, b["pair_cap"])
    else:  # long traces: sample index pairs instead of listing them all
        got = set()
        while len(got) < b["pair_cap"]:
            i, j = sorted(rng.sample(range(len(singles)), 2))
            if singles[i][:2] != singles[j][:2]:
                got.add((i, j))
        pairs = [(singles[i], singles[j]) for i, j in sorted(got)]
    for a, c in pairs:
        do("pair", pattern_dict(frames=[a, c]))

    summary["counts"] = dict(counts)
    summary["repros"] = dict(repros)
    summary["wall_s"] = time.time() - t0
    return summary


# --------------------------------------------------------------------------
# minimisation
# --------------------------------------------------------------------------
def violates(cfg, keys, prop: str, feas: bool, base_solved: bool) -> bool:
    res, dr, exc = run_one(cfg, pattern_dict(frames=keys))
    return any(p == prop for p, _ in check_run(cfg, res, dr, exc, feas, base_solved))


def minimise(
    cfg, keys: Sequence[Sequence[int]], prop: str, budget: int = 400
) -> Optional[list]:
    """1-minimal set of explicit dropped frames that still shows `prop`, or None
    when the explicit replay does not reproduce it."""
    feas = feasible(cfg)
    base, _, _ = run_one(cfg)
    base_solved = base is not None and base.verdict == "solved"
    cur = [tuple(k) for k in keys]
    if not violates(cfg, cur, prop, feas, base_solved):
        return None
    spent, changed = 0, True
    while changed and spent < budget:
        changed = False
        # halves first (cheap for long bursts), then single frames
        for size in sorted(
            {max(1, len(cur) // 2), max(1, len(cur) // 4), 1}, reverse=True
        ):
            i = 0
            while i < len(cur) and spent < budget:
                trial = cur[:i] + cur[i + size :]
                spent += 1
                if trial and violates(cfg, trial, prop, feas, base_solved):
                    cur, changed = trial, True
                else:
                    i += size
    return [list(k) for k in cur]


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def _worker(args):
    cfg, tier = args
    try:
        return explore_config(cfg, tier)
    except Exception as exc:  # noqa: BLE001
        return dict(cfg=cfg, crash=f"{type(exc).__name__}: {exc}", runs=0)


def cmd_explore(a) -> int:
    from multiprocessing import Pool

    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "results.jsonl")
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                done.add(json.dumps(json.loads(line)["cfg"], sort_keys=True))
    todo = [
        c
        for c in configs(a.tier, a.arms.split(","), a.scheds.split(","))
        if json.dumps(c, sort_keys=True) not in done
    ]
    # interleave so progress is spread over arms and sizes
    todo.sort(key=lambda c: (c["n"], c["graph"]))
    t0 = time.time()
    runs = 0
    with Pool(min(3, a.procs)) as pool, open(path, "a", encoding="utf-8") as fh:
        for i, s in enumerate(
            pool.imap_unordered(_worker, [(c, a.tier) for c in todo]), 1
        ):
            fh.write(json.dumps(s) + "\n")
            fh.flush()
            runs += s.get("runs", 0)
            if i % 20 == 0 or i == len(todo):
                print(
                    f"[{time.time() - t0:7.0f} s] {i}/{len(todo)} configs, {runs} runs",
                    flush=True,
                )
    return 0


def load(out: str) -> List[Dict[str, Any]]:
    with open(os.path.join(out, "results.jsonl"), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


def aggregate(rows) -> Dict[str, Any]:
    tot = Counter()
    by_prop: Dict[str, Counter] = defaultdict(Counter)
    base = Counter()
    crashes = []
    for r in rows:
        if "crash" in r:
            crashes.append(r)
            continue
        key = f"{r['cfg']['arm']}/{r['cfg']['sched']}"
        for f in ("runs", "generated", "deduped_zero", "deduped_same"):
            tot[f] += r.get(f, 0)
            tot[key + ":" + f] += r.get(f, 0)
        tot["configs"] += 1
        tot[key + ":configs"] += 1
        tot["wall_s"] += r.get("wall_s", 0.0)
        bprops = {p for p, _ in r["baseline"]["viol"]}
        for p, c in r.get("counts", {}).items():
            by_prop[p][key] += c
            if not p.startswith("distinct_"):
                by_prop[p][key + ":configs"] += 1
                if p in bprops:
                    by_prop[p][key + ":in_lossless_configs"] += c
        for p in bprops:
            base[f"{key}:{p}"] += 1
    return dict(tot=tot, by_prop=by_prop, base=base, crashes=crashes)


def smallest_repros(rows, prop: str, limit: int = 3, arm: Optional[str] = None):
    cands = []
    for r in rows:
        if arm is not None and r["cfg"]["arm"] != arm:
            continue
        for rep in r.get("repros", {}).get(prop, []):
            cfg = r["cfg"]
            cands.append(((cfg["n"], len(cfg["edges"]), rep["drops"]), cfg, rep))
    cands.sort(key=lambda x: x[0])
    return cands[:limit]


def cmd_report(a) -> int:
    rows = load(a.out)
    agg = aggregate(rows)
    best = {}
    for prop, arm in itertools.product(VIOLATIONS + INFO, ("mis", "ghs")):
        if not agg["by_prop"].get(prop):
            continue
        found = None
        for _, cfg, rep in smallest_repros(rows, prop, a.cands, arm):
            m = minimise(cfg, rep["keys"], prop)
            if m is None:
                continue
            base = run_one(cfg)[0]
            res, dr, exc = run_one(cfg, pattern_dict(frames=m))
            det = [
                d
                for p, d in check_run(
                    cfg,
                    res,
                    dr,
                    exc,
                    feasible(cfg),
                    base is not None and base.verdict == "solved",
                )
                if p == prop
            ]
            score = (cfg["n"], len(cfg["edges"]), len(m))
            if found is None or score < found[0]:
                found = (
                    score,
                    dict(
                        cfg=cfg,
                        frames=m,
                        from_kind=rep["kind"],
                        from_drops=rep["drops"],
                        detail=det[0] if det else "",
                    ),
                )
        if found:
            best[f"{prop}/{arm}"] = found[1]
    out = dict(
        tot=dict(agg["tot"]),
        by_prop={p: dict(c) for p, c in agg["by_prop"].items()},
        base=dict(agg["base"]),
        crashes=agg["crashes"],
        minimal=best,
    )
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(
        json.dumps(
            {k: v for k, v in out.items() if k != "minimal"}, indent=1, sort_keys=True
        )
    )
    for p, m in best.items():
        print(p, json.dumps(m))
    return 0


def cmd_replay(a) -> int:
    with open(a.file, encoding="utf-8") as fh:
        rep = json.load(fh)
    cfg = rep["cfg"]
    pat = rep.get("pattern") or pattern_dict(frames=rep.get("frames", ()))
    base, _, _ = run_one(cfg)
    res, dr, exc = run_one(cfg, pat)
    viol = check_run(
        cfg, res, dr, exc, feasible(cfg), base is not None and base.verdict == "solved"
    )
    print(
        json.dumps(
            dict(
                drops=len(dr.dropped),
                verdict=getattr(res, "verdict", None),
                violations=viol,
            )
        )
    )
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("explore")
    e.add_argument("--out", required=True)
    e.add_argument("--tier", default="full", choices=sorted(TIERS))
    e.add_argument("--procs", type=int, default=3)
    e.add_argument("--arms", default="mis,ghs")
    e.add_argument("--scheds", default="sync,async")
    r = sub.add_parser("report")
    r.add_argument("--out", required=True)
    r.add_argument("--cands", type=int, default=3)
    p = sub.add_parser("replay")
    p.add_argument("file")
    a = ap.parse_args(argv)
    return {"explore": cmd_explore, "report": cmd_report, "replay": cmd_replay}[a.cmd](
        a
    )


if __name__ == "__main__":
    sys.exit(main())
