#!/usr/bin/env python3
"""Progress of the densecomplete pool, against the cut actually being run.

Measured core-hours UNDERSTATE progress: a configuration contributes its
seconds only when it finishes, so whatever the thirteen workers are in the
middle of is invisible here. The extrapolation is therefore pessimistic by
roughly one job per worker.
"""
import collections, csv, glob, json, os, time
FV3 = "/home/ege/Desktop/MDS_SKYFABRIC/results/bb/full_v3"
S, F = FV3 + "/densecomplete", FV3 + "/_topup/densecomplete_fills"
jobs = [json.loads(l) for l in open(S + "/jobs.jsonl")]
cut = S + "/CUT_LIST"
if os.path.exists(cut):
    allowed = {l.strip() for l in open(cut) if l.strip() and not l.startswith("#")}
    jobs = [j for j in jobs if j["id"] in allowed]
    print(f"witness cut active: {len(jobs)} jobs of the full plan")
names = {0: "1 xlarge fills", 1: "2 largedense fills",
         2: "3 n=150/200 files", 3: "4 witness runs"}
rows = []
for p in glob.glob(S + "/parts/*.csv") + glob.glob(F + "/parts/*.csv"):
    rows += list(csv.DictReader(open(p)))
secs = sum(float(r["seconds"] or 0) for r in rows)
est_tot = sum(j["est"] for j in jobs)
runs_tot = sum(len(j["configs"]) for j in jobs)
done = sum(1 for j in jobs if os.path.exists(j["out"] + ".done"))
start = max(float(l.split()[2].replace("T", " ")[:0] or 0) for l in [" "]) if False else None
t0 = None
for line in open(S + "/pool.log"):
    if line.startswith("POOL START"):
        t0 = time.mktime(time.strptime(line.split()[2][:19], "%Y-%m-%dT%H:%M:%S"))
el = (time.time() - t0) / 3600 if t0 else 0
fails = [l for l in open(S + "/pool.log") if " rc=" in l and " rc=0 " not in l]
print(f"runs {len(rows)}/{runs_tot}  jobs {done}/{len(jobs)}  "
      f"core-hours {secs/3600:.1f}/{est_tot/3600:.0f}  elapsed {el:.1f} h  "
      f"failed {len(fails)}")
for r in (0, 1, 2, 3):
    sel = [j for j in jobs if j["milestone"] == r]
    if sel:
        d = sum(1 for j in sel if os.path.exists(j["out"] + ".done"))
        print(f"  {names[r]}: {d}/{len(sel)} jobs")
if secs > 0 and el > 0:
    rate = secs / 3600 / el
    print(f"  rate {rate:.1f} core-h per wall hour (13 is the ceiling); "
          f"{(est_tot/3600 - secs/3600)/rate:.1f} h left at that rate, "
          f"pessimistic because in-flight runs do not count yet")
for l in fails[:5]:
    print("  FAIL", l.strip())
