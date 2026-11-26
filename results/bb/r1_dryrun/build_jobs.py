#!/usr/bin/env python3
"""Job lists of the R1 blocks for ccvc/bb/r1_run.py.

    PYTHONPATH=<snapshot> python3 build_jobs.py --block M3 \
        --instances results/bb/r1/instances/H1 --instances results/bb/r1/instances/H1-large \
        --out results/bb/r1/M3

Blocks follow paper/CoverWeave_R1/contract/R1_PREREG.md (section 5 and
Amendments 1 to 9). `--instances` is a set written by `ccvc.bb.heldout`
(DIR/manifest.json), the published dataset directory (M2, calibration) or, for
`lossexp`, a directory of Mininet-WiFi run folders (`dag_*`). Writes
OUT/jobs.jsonl; every job writes OUT/parts/<id>.csv. Run it with run_pool.sh.

Choices the pre-registration leaves open are marked OPEN below and listed in
docs/R1_RUN_PLAN.md; they must be fixed by an amendment before the block runs.
A set generated with the pre-registered seeds is refused until the tag
`coverweave-r1-frozen` exists in the release repository.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

RELEASE_REPO = os.path.expanduser("~/Desktop/bbcvc-release")
TAG = "coverweave-r1-frozen"
NAME = re.compile(r"^n(\d+)_m(\d+)_s(\d+)\.txt$")
MIS_NBRS_MAX = 64  # development sweep (results/bb/full_v3/STAGE_*.md)

ARMS = (
    "MIS-Connector-Backbone",
    "MIS-Connector-TreeAgg",
    "DFS-Spanning-Backbone",
    "GHS-MST-Backbone",
    "WuLi-Dominating-Exact",
    "WuLi-Dominating-Bloom",
    "WuLi-Dominating-Chunked",
    "Anneal-Local",
    "Anneal-TreeAgg",
    "Anneal-Trickle",
    "Greedy-Degree-Backbone",
    "Greedy-Ratio-Backbone",
    "Greedy-Weight-Backbone",
)
#: r1_run runs only the first configuration on an infeasible instance; this one is
#: among the cheapest there (full_v3) and the only one measured at n > 200.
WITNESS = ("MIS-Connector-Backbone", "sync")
ALL25 = [WITNESS] + [
    (a, s)
    for a in ARMS
    for s in ("sync", "async")
    if (a, s) != WITNESS and not (a == "Anneal-Trickle" and s == "sync")
]
NEXUS_S, NEXUS_A = ("MIS-Connector-Backbone", "sync"), (
    "MIS-Connector-Backbone",
    "async",
)
FABRIC_S, FABRIC_A = ("GHS-MST-Backbone", "sync"), ("GHS-MST-Backbone", "async")
TEMPER_A, TRICKLE_A = ("Anneal-Local", "async"), ("Anneal-Trickle", "async")
#: OPEN: M5's ten configurations are not named in the prereg; this is A3's proposal.
M5_CONFIGS = [
    NEXUS_S,
    NEXUS_A,
    FABRIC_S,
    FABRIC_A,
    TEMPER_A,
    TRICKLE_A,
    ("WuLi-Dominating-Exact", "sync"),
    ("Greedy-Ratio-Backbone", "sync"),
    ("Greedy-Degree-Backbone", "sync"),
    ("DFS-Spanning-Backbone", "sync"),
]
#: OPEN: M6's five configurations are not named; the three calibration arms.
M6_CONFIGS = [NEXUS_S, NEXUS_A, FABRIC_S, FABRIC_A, TEMPER_A]
M6_LOSSES = [0.0, 0.05, 0.10, 0.20, 0.30, "ge:0.05:4", "ge:0.10:4", "ge:0.20:4"]
M6_GE = [x for x in M6_LOSSES if isinstance(x, str)]
#: Amendment 15: the default stale window under loss, kept as the ablation
M6_ABLATION = (0.05, "ge:0.10:4")
#: OPEN: "10 per cell" over 60 instances fixes one density per family; m/n = 4 for both.
M6_CELLS = {"H1": 4, "H2a": 8}
WEIGHT_LAWS = (
    "H1-unit",
    "H1-degree",
    "H1-lognormal",
    "H1-energy",
)  # heldout M8-weights
M5_K = {2: (3, 4, 6, 8), 4: (6, 8, 12, 16)}  # by m/n; H2a degree 8 is m/n = 4
M8_CORE = {
    "gap_patience": (1, 4, 8),
    "escalate_patience": (1, 4, 8),
    "quiet_periods": (2, 5, 8),
    "stale_periods": (2, 5),
    "max_repair_rounds": (2, 8),
    "ack_max_attempts": (5, 8),
}
M8_ANNEAL = {
    "alpha": (0.8, 0.95),
    "cool_every": (1, 4),
    "t0_scale": (0.5, 2.0),
    "t_min_frac": (0.05 / 12, 0.05 / 3),  # half and double of 0.05/6
    "lam_scale": (1.5, 4.0),
}
CAL_NAMES = (
    "n10_m20_s1.txt",
    "n10_m40_s1.txt",
    "n15_m30_s1.txt",
    "n25_m50_s1.txt",
    "n25_m100_s1.txt",
    "n50_m100_s1.txt",
    "n50_m200_s1.txt",
)
CAL_CONFIGS = [NEXUS_S, NEXUS_A, FABRIC_S, FABRIC_A, ("Anneal-Local", "sync"), TEMPER_A]
CAL_SETTINGS = [None, {"adaptive_stale": False}] + [
    {"adaptive_stale": False, "stale_periods": s, "stab_periods": s}
    for s in (6, 12, 24, 48)
]
#: the submitted bridge-discount experiment (ccvc/bb/bridgefix_measure.py): two cells, seeds 1-3
BRIDGE_NAMES = tuple(f"n{n}_m{2 * n}_s{s}.txt" for n in (25, 50) for s in (1, 2, 3))
BRIDGE_CONFIGS = [("Anneal-Local", "sync"), TEMPER_A]
LOSSEXP_ARMS = {
    "dag_mst": "GHS-MST-Backbone",
    "dag_bbcvc": "MIS-Connector-Backbone",
    "dag_anneal": "Anneal-Local",
}


def budget_ms(n: int) -> int:
    """Time limit of the development sweep for the smallest size >= n (STAGE_*.md)."""
    return (
        4_500_000
        if n <= 25
        else 12_000_000
        if n <= 100
        else 22_000_000
        if n <= 200
        else 102_000_000
    )


def dev_group(n: int) -> str:
    return "small" if n <= 25 else "medium" if n <= 200 else "large"


def load_set(d: str):
    """(instances, sealed) of one directory: a ccvc.bb.heldout set, else dataset files."""
    d = os.path.abspath(d)
    man = os.path.join(d, "manifest.json")
    m = {}
    if os.path.exists(man):
        with open(man, encoding="utf-8") as fh:
            m = json.load(fh)
    if m.get("generator") == "ccvc.bb.heldout":
        out = [
            dict(
                dataset=os.path.join(d, os.path.dirname(f["file"])),
                instance=os.path.basename(f["file"]),
                family=f["family"],
                param=next(f[p] for p in ("ratio", "deg", "attach", "k") if p in f),
                n=f["n"],
                m=f["m"],
                seed=f["seed"],
            )
            for f in m["files"]
        ]
        return out, bool(m["preregistered_seeds"])
    out = []
    for name in sorted(os.listdir(d)):
        hit = NAME.match(name)
        if hit:
            n, m, s = map(int, hit.groups())
            out.append(
                dict(
                    dataset=d,
                    instance=name,
                    family="Development",
                    param=m // n,
                    n=n,
                    m=m,
                    seed=s,
                )
            )
    return out, False


def write_worked(out_dir: str):
    """The worked example (n = 10, m = 15, k = 2) as a dataset-format file."""
    from ccvc.bb import figures

    d = os.path.join(out_dir, "instance")
    os.makedirs(d, exist_ok=True)
    w, e = figures.WORKED_WEIGHTS, figures.WORKED_EDGES
    path = os.path.join(d, f"n{len(w)}_m{len(e)}_s0.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(f"{v} {w[v]!r}\n" for v in sorted(w)))
        fh.write("".join(f"{u} {v}\n" for u, v in sorted(e)))
    return dict(
        dataset=d,
        instance=os.path.basename(path),
        family="Worked",
        param=1,
        n=len(w),
        m=len(e),
        seed=0,
        k=figures.WORKED_K,
    )


def write_lossexp(root: str, out_dir: str):
    """The graphs the development stations discovered, as dataset-format files.

    Same reconstruction as results/bb/loss_experiment/run_loss_experiment.py
    (target edges minus missing plus extra); ids and weights as in run.json.
    """
    d = os.path.join(out_dir, "instance")
    os.makedirs(d, exist_ok=True)
    out = []
    for run in sorted(x for x in os.listdir(root) if x.startswith("dag_")):
        with open(os.path.join(root, run, "summary.json"), encoding="utf-8") as fh:
            dv = json.load(fh)["discovered_vs_target"]
        with open(os.path.join(root, run, "run.json"), encoding="utf-8") as fh:
            r = json.load(fh)
        key = lambda e: tuple(sorted(e))  # noqa: E731
        seen = ({key(e) for e in r["edges"]} - {key(e) for e in dv["missing"]}) | {
            key(e) for e in dv["extra"]
        }
        w = {int(a): float(b) for a, b in r["weights"].items()}
        nodes = sorted(w)
        path = os.path.join(d, f"n{len(nodes)}_m{len(seen)}_s{len(out)}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(f"{v} {w[v]!r}\n" for v in nodes))
            fh.write("".join(f"{u} {v}\n" for u, v in sorted(seen)))
        out.append(
            dict(
                dataset=d,
                instance=os.path.basename(path),
                family="LossExp",
                param=len(seen) // len(nodes),
                n=len(nodes),
                m=len(seen),
                seed=len(out),
                k=int(r["k"]),
                mis=int(r["mis_nbrs_max"]),
                arm=LOSSEXP_ARMS[run.rsplit("_n", 1)[0]],
                run=run,
            )
        )
    return out


def feasible(inst, k: int) -> bool:
    """The flow check r1_run applies (sweep.instance_feasibility), or the counting bound."""
    if inst["m"] > inst["n"] * k:
        return False
    from ccvc.bb import matrix, sweep

    raw_w, raw_e = matrix.load_instance(os.path.join(inst["dataset"], inst["instance"]))
    w, e, _ = sweep.prepare(raw_w, raw_e)
    cell = matrix.Cell("x", inst["n"], inst["param"])
    one = sweep.Instance("dataset", cell, inst["seed"], "", tuple(e), w, 0)
    return sweep.instance_feasibility(one, sweep.SweepOptions(k=k)) == "yes"


def jobs_for(inst, k, loss, rng, configs, out, params=None, all_inf=False, split=True):
    """One job per configuration above n = 200 (so no job holds hours of runs),
    one job for all configurations otherwise or on an infeasible instance."""
    label = "_".join(f"{a}{b}" for a, b in sorted((params or {}).items()))
    base = (
        f"{inst['family']}_{inst['instance'][:-4]}_k{k}_l{loss}_r{rng}"
        + (f"_{label}" if label else "")
    ).replace(":", "-")
    groups = [configs]
    if (
        split
        and inst["n"] > 200
        and len(configs) > 1
        and (all_inf or feasible(inst, k))
    ):
        groups = [[c] for c in configs]
    jobs = []
    for i, cfgs in enumerate(groups):
        jid = base if len(groups) == 1 else f"{base}_c{i:02d}"
        group = (
            dev_group(inst["n"])
            if inst["family"] in ("Development", "Worked", "LossExp")
            else inst["family"]
        )
        j = dict(
            id=jid,
            dataset=inst["dataset"],
            instance=inst["instance"],
            group=group,
            n=inst["n"],
            m=inst["m"],
            ratio=inst["m"] // inst["n"],
            seed=inst["seed"],
            k=k,
            loss=loss,
            rng_seed=rng,
            configs=[list(c) for c in cfgs],
            max_ms=budget_ms(inst["n"]),
            mis_nbrs_max=inst.get("mis", MIS_NBRS_MAX),
            out=os.path.join(out, "parts", jid + ".csv"),
        )
        if params:
            j["params"] = params
        if all_inf:
            j["all_configs_on_infeasible"] = True
        jobs.append(j)
    return jobs


def first_seeds(insts, count):
    """The `count` smallest seeds of every (family, n, param) cell."""
    cells = {}
    for i in insts:
        cells.setdefault((i["family"], i["n"], i["param"]), []).append(i)
    return [
        i for c in cells.values() for i in sorted(c, key=lambda x: x["seed"])[:count]
    ]


#: second run of each M6 Gilbert-Elliott condition: F9 off if F9 is accepted (Amendment 6)
F9_OFF = {"adaptive_stale": False}


def build(
    block,
    insts,
    out,
    ge_second=F9_OFF,
    emp=False,
    lossexp_losses=(0.0, 0.05),
    profile=None,
):
    J = []
    fam = lambda *f: [i for i in insts if i["family"] in f]  # noqa: E731
    if (
        block == "M2"
    ):  # development set, rng seed = instance seed as in the development sweep
        for i in fam("Development"):
            J += jobs_for(i, 6, 0.0, i["seed"], ALL25, out)
    elif block == "worked":
        for i in fam("Worked"):
            J += jobs_for(i, i["k"], 0.0, 1, ALL25, out)
    elif (
        block == "lossexp"
    ):  # paired loss experiment: each graph with its own arm, sync
        for i in fam("LossExp"):
            for loss in lossexp_losses:
                for rng in range(5):
                    j = jobs_for(i, i["k"], loss, rng, [(i["arm"], "sync")], out)
                    for x in j:
                        x["max_ms"] = 200_000  # the experiment's own budget
                    J += j
    elif (
        block == "bridge"
    ):  # submitted experiment 2: bridge discount off and on (BULGULAR 90)
        dev = [i for i in fam("Development") if i["instance"] in BRIDGE_NAMES]
        held = [
            i for i in fam("H1") if i["n"] in (25, 50) and i["param"] == 2
        ]  # same cells, held out
        for i in dev + held:
            for p in (None, {"repay_bridge_credit": False}):
                j = jobs_for(
                    i,
                    6,
                    0.0,
                    i["seed"] if i in dev else 1,
                    BRIDGE_CONFIGS,
                    out,
                    params=p,
                )
                if i in dev:
                    for x in j:
                        x["max_ms"] = 200_000  # the submitted experiment's budget
                J += j
    elif block in ("M3", "M4", "M9"):
        want = {"M3": ("H1", "H1-large"), "M4": ("H2a", "H2b"), "M9": ("M9",)}[block]
        for i in fam(*want):
            J += jobs_for(i, 6, 0.0, 1, ALL25, out, all_inf=block == "M9")
    elif block == "M5":
        for i in fam("H1", "H2a"):
            r = i["m"] // i["n"]
            if i["n"] in (15, 25, 50, 100) and (i["family"] == "H1" or i["param"] == 8):
                for k in M5_K[r]:
                    J += jobs_for(i, k, 0.0, 1, M5_CONFIGS, out)
    elif block == "M6":
        sel = [
            i
            for i in fam("H1", "H2a")
            if i["n"] in (25, 50, 100) and i["param"] == M6_CELLS[i["family"]]
        ]
        for i in sel:
            for loss in ["emp"] if emp else M6_LOSSES:  # Amendment 3: "emp" after M7
                for rng in (1, 2, 3):
                    if profile is None:  # F9 accepted: Amendment 14 design
                        J += jobs_for(i, 6, loss, rng, M6_CONFIGS, out)
                        if (
                            loss in M6_GE
                        ):  # every GE condition twice (Amendments 5 and 6)
                            J += jobs_for(
                                i, 6, loss, rng, M6_CONFIGS, out, params=ge_second
                            )
                        continue
                    # Amendment 15: every lossy condition runs with the profile; lossless
                    # runs the default and, for the profile's cost, the profile (Amendment 5);
                    # the default under loss is the ablation on n 25 and 50, channel seed 1
                    if loss == 0.0 or (
                        i["n"] in (25, 50) and rng == 1 and loss in M6_ABLATION
                    ):
                        J += jobs_for(i, 6, loss, rng, M6_CONFIGS, out)
                    J += jobs_for(i, 6, loss, rng, M6_CONFIGS, out, params=profile)
    elif block == "M8":
        sel = first_seeds(
            [
                i
                for i in fam("H1", "H2a")
                if i["n"] in (50, 100) and (i["family"] == "H1" or i["param"] in (6, 8))
            ],
            5,
        )
        levels = lambda f: [{k: v} for k, vs in f.items() for v in vs]  # noqa: E731
        for i in sel:
            for loss in (0.0, 0.05):
                for rng in (1, 2, 3):
                    # OPEN: channel seeds (A3 proposal): sync lossless 1, otherwise 3
                    core = [
                        c
                        for c in (NEXUS_S, FABRIC_S, FABRIC_A)
                        if c[1] == "async" or loss or rng == 1
                    ]
                    # Amendment 15: the lossy runs sit at the profile, and the stale
                    # window factor is half and double of it, stabilisation window equal
                    base = profile if (profile and loss) else {}
                    core_levels = levels(M8_CORE)
                    if base:
                        w = base["stale_periods"]
                        core_levels = [
                            p for p in core_levels if "stale_periods" not in p
                        ] + [
                            {"stale_periods": s, "stab_periods": s}
                            for s in (w // 2, 2 * w)
                        ]
                    # defaults once, for all five configurations
                    J += jobs_for(
                        i, 6, loss, rng, core + [TEMPER_A, TRICKLE_A], out,
                        params=base or None,
                    )  # fmt: skip
                    for p in core_levels:
                        J += jobs_for(i, 6, loss, rng, core, out, params={**base, **p})
                    for p in levels(M8_ANNEAL):
                        J += jobs_for(
                            i, 6, loss, rng, [TEMPER_A, TRICKLE_A], out,
                            params={**base, **p},
                        )  # fmt: skip
        # weight laws (heldout --set M8-weights); uniform weights are the M3 rows.
        # OPEN: configurations and loss are not registered; A3 proposed ten, lossless.
        for i in fam(*WEIGHT_LAWS):
            J += jobs_for(i, 6, 0.0, 1, M5_CONFIGS, out)
    elif block == "calibration":  # Amendments 5 and 6
        for i in [
            x for x in insts if x["family"] == "Worked" or x["instance"] in CAL_NAMES
        ]:
            for p in CAL_SETTINGS:
                for rng in (1, 2, 3):
                    J += jobs_for(
                        i, i.get("k", 6), "ge:0.10:4", rng, CAL_CONFIGS, out, params=p
                    )
    else:
        raise SystemExit(f"unknown block {block}")
    for (
        j
    ) in (
        J
    ):  # block prefix: M3, M5, M6 and M8 share instances, so ids must differ across lists
        j["id"] = f"{block}_{j['id']}"
        j["out"] = os.path.join(out, "parts", j["id"] + ".csv")
    J.sort(key=lambda j: (-j["n"], -j["m"], j["id"]))  # large first: shorter makespan
    ids = [j["id"] for j in J]
    assert len(ids) == len(set(ids)), "duplicate job id"
    return J


def tag_exists() -> bool:
    """The ANNOTATED tag (prereg section 1); `^{tag}` fails on a lightweight one."""
    r = subprocess.run(
        [
            "git",
            "-C",
            RELEASE_REPO,
            "rev-parse",
            "-q",
            "--verify",
            f"refs/tags/{TAG}^{{tag}}",
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--block",
        required=True,
        choices=(
            "calibration",
            "M2",
            "worked",
            "lossexp",
            "bridge",
            "M3",
            "M4",
            "M5",
            "M6",
            "M8",
            "M9",
        ),
    )
    ap.add_argument("--instances", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--losses",
        type=lambda t: [float(x) for x in t.split(",")],
        default=[0.0, 0.05],
        help="lossexp: conditions; the submitted experiment has 0,0.05 (proposal: 0,0.05,0.10)",
    )
    ap.add_argument(
        "--emp",
        action="store_true",
        help="M6: only the empirical condition, once M7 has written its delivery ratios",
    )
    ap.add_argument(
        "--ge-second",
        type=json.loads,
        default=F9_OFF,
        help="M6: overrides of the second run of each Gilbert-Elliott condition; "
        "default F9 off, or the Amendment 5 profile if F9 is not accepted",
    )
    ap.add_argument(
        "--profile",
        type=json.loads,
        default=None,
        help="Amendment 15: the Amendment 5 profile for every lossy run of M6 and M8, "
        'e.g. \'{"adaptive_stale": false, "stale_periods": 24, "stab_periods": 24}\'',
    )
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    insts = []
    for d in a.instances:
        if a.block == "lossexp":
            insts += write_lossexp(d, out)
            continue
        got, sealed = load_set(d)
        if sealed and not tag_exists():
            print(
                f"REFUSED: {d} holds pre-registered seeds and {TAG} does not exist "
                f"in {RELEASE_REPO}",
                file=sys.stderr,
            )
            return 2
        insts += got
    if a.block in ("worked", "calibration"):
        insts.append(write_worked(out))
    jobs = build(
        a.block,
        insts,
        out,
        ge_second=a.ge_second,
        emp=a.emp,
        lossexp_losses=a.losses,
        profile=a.profile,
    )
    os.makedirs(os.path.join(out, "parts"), exist_ok=True)
    with open(os.path.join(out, "jobs.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(j) + "\n" for j in jobs))
    runs = sum(len(j["configs"]) for j in jobs)
    print(
        f"{a.block}: {len(insts)} instances, {len(jobs)} jobs, {runs} configurations "
        f"(infeasible instances run only the first) -> {out}/jobs.jsonl"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
