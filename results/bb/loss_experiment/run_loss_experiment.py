"""Paired lossless/lossy experiment on the graphs the stations actually saw."""
import argparse, csv, json, os, sys, glob
sys.path.insert(0, "/home/ege/Desktop/MDS_SKYFABRIC")
from ccvc.bb import sweep, validate

ARMS = {"dag_mst": "GHS-MST-Backbone",
        "dag_bbcvc": "MIS-Connector-Backbone",
        "dag_anneal": "Anneal-Local"}
SPECS = {s.name: s for s in sweep.discover()}
ROOT = "/home/ege/Desktop/MDS_SKYFABRIC/results/bb/wifi_dagdeviren"

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--conditions", default="lossless:0.0,lossy:0.05",
                help="comma separated name:loss pairs")
ap.add_argument("--arms", default="",
                help="comma separated arm names; empty means all three")
ap.add_argument("--seeds", type=int, default=5)
args = ap.parse_args()

OUT = args.out
CONDS = [(p.split(":")[0], float(p.split(":")[1]))
         for p in args.conditions.split(",") if p]
KEEP = {a for a in args.arms.split(",") if a}
FP = sweep.code_fingerprint()
print("code_fingerprint:", FP, flush=True)


def load(d):
    S = json.load(open(os.path.join(d, "summary.json")))
    R = json.load(open(os.path.join(d, "run.json")))
    dv = S["discovered_vs_target"]
    tgt = {tuple(sorted(e)) for e in R["edges"]}
    seen = (tgt - {tuple(sorted(e)) for e in dv["missing"]}) \
        | {tuple(sorted(e)) for e in dv["extra"]}
    w = {int(a): float(b) for a, b in R["weights"].items()}
    return sorted(seen), w, int(R["k"]), int(R["mis_nbrs_max"])


rows = []
dirs = sorted(glob.glob(os.path.join(ROOT, "dag_*")))
for d in dirs:
    name = os.path.basename(d)
    arm = ARMS[name.rsplit("_n", 1)[0]]
    if KEEP and arm not in KEEP:
        continue
    edges, w, k, mis = load(d)
    n = len({v for e in edges for v in e})
    for cond, loss in CONDS:
        for rng in range(args.seeds):
            req = sweep.RunRequest(edges=edges, weights=w, k=k, scheduler="sync",
                                   max_ms=200_000, loss=loss, seed=rng,
                                   mis_nbrs_max=mis)
            res = SPECS[arm].run(req)
            g = validate.make_graph(list(edges), k, dict(w), nodes=sorted(w))
            rep = validate.validate(g, res.cover, res.owner)
            rows.append(dict(graph=name, n=n, m=len(edges), k=k, arm=arm,
                             condition=cond, loss=loss, rng=rng,
                             verdict=res.verdict, valid=int(bool(rep.valid)),
                             cover_size=len(res.cover),
                             weight=round(float(res.total_weight), 4),
                             slots=res.slots,
                             violations="|".join(sorted({v.kind for v in rep.violations})),
                             code_fp=FP))
            print(f"{name:26s} {arm:23s} {cond:9s} rng={rng} "
                  f"{res.verdict:10s} valid={rep.valid}", flush=True)

tmp = OUT + ".tmp"
with open(tmp, "w", newline="") as fh:
    wtr = csv.DictWriter(fh, fieldnames=list(rows[0]))
    wtr.writeheader()
    wtr.writerows(rows)
os.replace(tmp, OUT)
print("YAZILDI", OUT, len(rows), "fp", FP)
