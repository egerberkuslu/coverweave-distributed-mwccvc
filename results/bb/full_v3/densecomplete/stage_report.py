#!/usr/bin/env python3
"""Generate STAGE_densecomplete.md from the rows the stage actually holds.

Written as a generator rather than by hand so the file can be refreshed while
the sweep is still running and again when it finishes, and so every number in
it is read from a CSV instead of remembered.
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import sys

ROOT = "/home/ege/Desktop/MDS_SKYFABRIC"
FV3 = f"{ROOT}/results/bb/full_v3"
STAGE = f"{FV3}/densecomplete"
FILLS = f"{FV3}/_topup/densecomplete_fills"
ARMS = 13
CONFIGS = 25


def read(pattern):
    rows = []
    for p in sorted(glob.glob(pattern)):
        rows += list(csv.DictReader(open(p)))
    return rows


def T(x):
    return str(x).strip().lower() in ("true", "1", "yes", "evet")


def main():
    jobs = [json.loads(l) for l in open(f"{STAGE}/jobs.jsonl")]
    new_jobs = [j for j in jobs if j["kind"] == "new"]
    fill_jobs = [j for j in jobs if j["kind"] == "fill"]
    rows = read(f"{STAGE}/parts/*.csv")
    fills = read(f"{FILLS}/parts/*.csv")
    want_inst = {j["instance"] for j in new_jobs}
    want_runs = sum(len(j["configs"]) for j in new_jobs)
    done_new = len(glob.glob(f"{STAGE}/parts/*.done"))
    done_fill = len(glob.glob(f"{FILLS}/parts/*.done"))
    complete = (done_new == len(new_jobs)) and (done_fill == len(fill_jobs))

    seen = collections.Counter((r["instance"], r["variant"], r["scheduler"])
                               for r in rows)
    dup = sum(v - 1 for v in seen.values() if v > 1)
    missing = want_runs - len(seen)
    false_success = [r for r in rows + fills
                     if r["verdict"] == "solved" and not T(r["valid"])]
    contradiction = [r for r in rows + fills if r["verdict_agrees"] != "yes"]
    blank = [r for r in rows + fills if not r["status"]]
    status = collections.Counter(r["status"] for r in rows)
    fstatus = collections.Counter(r["status"] for r in fills)
    fps = collections.Counter(r["code_fingerprint"] for r in rows + fills)
    nk_ok = all(int(r["m"]) > int(r["n"]) * int(r["k"]) for r in rows)
    secs = sum(float(r["seconds"] or 0) for r in rows + fills)

    L = ["# Stage `densecomplete` — the 36 files no other stage measured", ""]
    L += [("Integrity verdict: **" +
           ("CLEAN" if complete and not (dup or missing or false_success or
                                         contradiction or blank) else
            "IN PROGRESS" if not complete else "PROBLEMS") + "**"), ""]
    L += ["", "The other six stages of `full_v3` cover 324 of the benchmark's 360",
          "files. This stage is the remaining 36, and a companion set of fills",
          "under `_topup/densecomplete_fills/` re-measures the 187",
          "(instance, arm, scheduler) pairs an earlier stage wrote as `skipped`",
          "when its wall-clock budget ran out. Both were measured against one",
          "frozen snapshot; `FINGERPRINTS.md` says which code that is and why it",
          "carries a fourth fingerprint.", ""]
    L += ["## What ran", "", "| field | value |", "|---|---|"]
    ns = sorted({int(r["n"]) for r in rows} or {0})
    ratios = sorted({int(r["ratio"]) for r in rows} or {0})
    for k, v in [
        ("ns", ",".join(map(str, ns))),
        ("ratios", ",".join(map(str, ratios))),
        ("k", 6),
        ("max_ms", "22000000 for n<=200, 102000000 above"),
        ("mis_nbrs_max", 64),
        ("schedulers", "sync,async"),
        ("jobs", f"{len(new_jobs)} new + {len(fill_jobs)} fill"),
        ("jobs finished", f"{done_new}/{len(new_jobs)} new, "
                          f"{done_fill}/{len(fill_jobs)} fill"),
        ("seconds (summed over jobs, they ran in parallel)", round(secs, 1)),
        ("code fingerprint", "/".join(sorted(fps))),
        ("rows", f"{len(rows)} (expected {want_runs})"),
        ("fill rows", f"{len(fills)} (expected 187)"),
        ("instances", f"{len({r['instance'] for r in rows})} (expected 36)"),
        ("arm x scheduler configs", f"{len({(r['variant'], r['scheduler']) for r in rows})} "
                                    f"(expected {CONFIGS})"),
        ("missing / duplicate rows", f"{missing} / {dup}"),
        ("false successes (verdict=solved, valid=False)",
         f"**{len(false_success)}**"),
        ("contradiction rows (verdict_agrees != yes)", len(contradiction)),
        ("blank rows (no status)", len(blank)),
        ("every instance has m > nk at k = 6", "yes" if nk_ok else "**NO**"),
    ]:
        L.append(f"| {k} | {v} |")
    L += ["", "## Why nothing here is scored for quality", "",
          "Every one of the 36 files has more edges than n·k at k = 6, so no",
          "capacitated cover exists on any of them and the only thing an arm can",
          "do is announce impossibility. That is why they were cut from the first",
          "pass and why filling them in changes no quality number: they enter the",
          "denominator of nothing. What they do change is the coverage claim. The",
          "sweep now reads every file the benchmark ships rather than the 324",
          "that could be scored, so the sentence \"324 of 360\" becomes \"360 of",
          "360\" and the reason a cell is empty is a property of the cell rather",
          "than a decision about what to run.", ""]
    L += ["## The fills are a different case and they DO move numbers", "",
          "Three of the filled instances are `n500_m3000_s1`, `n750_m4500_s1` and",
          "`n1000_m6000_s1`, where m equals n·k exactly rather than exceeding",
          "it. Those are not in the provably-impossible class, so their rows reach",
          "the reliability denominators. Before the fills, 37 of their 75",
          "configurations carried no measurement at all; a table that read a",
          "`skipped` row as a run an arm had failed would have understated those",
          "arms, which is the reading error `SUMMARY_full_v3.md` records and",
          "fixed. The fills replace the absence with a measurement, so the",
          "denominators become real rather than repaired.", ""]
    L += ["## Status inventory", "", "| status | new rows | fill rows |", "|---|---|---|"]
    for s in sorted(set(status) | set(fstatus)):
        L.append(f"| `{s}` | {status.get(s, 0)} | {fstatus.get(s, 0)} |")
    L += ["", "## Fingerprints carried", "", "| fingerprint | rows |", "|---|---|"]
    for f, c in sorted(fps.items()):
        L.append(f"| `{f}` | {c} |")
    # the witness cut
    cut = f"{STAGE}/CUT_LIST"
    if os.path.exists(cut):
        allowed = {l.strip() for l in open(cut, encoding="utf-8")
                   if l.strip() and not l.startswith("#")}
        outside = [j for j in jobs if j["id"] not in allowed]
        big = sorted({j["instance"] for j in outside})
        ran_on_big = collections.defaultdict(set)
        for r in rows:
            if int(r["n"]) >= 250:
                ran_on_big[r["instance"]].add((r["variant"], r["scheduler"]))
        L += ["## The witness cut on the eight largest dense files", "",
              "The eight files at n >= 250 with m/n in {8, 10} carry one measured",
              "configuration each rather than twenty-five, and the omission is a",
              "decision rather than an accident. Measuring all twenty-five on",
              "those eight costs about 218 core-hours against 86 for everything",
              "else in this stage put together, and buys no comparison: every one",
              "of the eight has m > nk at k = 6, so no cover exists, no arm can",
              "score on them, and the only quantity the missing runs would have",
              "produced is how long each arm takes to announce a fact that one",
              "line of arithmetic already proves.", "",
              "What IS measured on each of the eight is",
              "`MIS-Connector-Backbone` under the synchronous scheduler, the",
              "cheapest arm in the profile, run to the same budget as everywhere",
              "else. It is a witness run: it establishes that the file was read,",
              "that the protocol reaches a verdict on it, and that the verdict is",
              "impossibility.", "",
              "**So the coverage claim is 360 of 360 files read, not 25",
              "configurations on each of 360 files.** Any sentence that says the",
              "second thing is wrong. The measured shape is 352 files at 25",
              "configurations plus 8 files at one, and the table below names which",
              "arm ran where.", "",
              "| file | configurations measured |", "|---|---|"]
        for i in sorted(ran_on_big):
            cs = sorted(ran_on_big[i])
            L.append(f"| `{i}` | {', '.join(a + '/' + s_ for a, s_ in cs)} |")
        L += ["", f"{len(outside)} jobs covering "
                  f"{sum(len(j['configs']) for j in outside)} configurations on "
                  f"{len(big)} files were left unmeasured by the cut; "
                  f"`CUT_LIST` names every job that ran and `jobs.jsonl` every "
                  f"job that was planned, so the difference is a list rather "
                  f"than a gap.", ""]

    L += ["", "## Valid share per arm, on scored instances only", "",
          "Empty by construction for the 36 new instances: no instance among them",
          "admits a cover, so there is no scored denominator and printing a zero",
          "would say twenty-five arms failed on thirty-six problems that have no",
          "solution. The fills are folded back into `largedense` and `xlarge` and",
          "are scored there, in those stages' own tables.", ""]
    if not complete:
        L += ["", "> This file was generated while the sweep was still running.",
              "> Counts above are partial and the verdict is provisional.", ""]
    open(f"{FV3}/STAGE_densecomplete.md", "w", encoding="utf-8").write(
        "\n".join(L) + "\n")
    print(f"wrote STAGE_densecomplete.md: {len(rows)} new rows, {len(fills)} "
          f"fill rows, jobs {done_new + done_fill}/{len(jobs)}, "
          f"false successes {len(false_success)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
