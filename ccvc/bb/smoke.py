"""Bounded algorithm preflight for the Mininet-WiFi validation workflow.

This command executes the event simulator, never a wireless emulator. It keeps
one small graph cell and three or four seeds per variant. A failing gate exits
with status 1 after saving every row; it never starts a larger experiment.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Sequence

from ccvc.bb import matrix, sweep

BACKEND = "event-simulator"
TARGET_BACKEND = "mininet-wifi"


def select_variants(names: str, scheduler: str) -> list[sweep.VariantSpec]:
    specs = sweep.discover()
    requested = {name.strip() for name in names.split(",") if name.strip()}
    if requested:
        missing = requested - {spec.name for spec in specs}
        if missing:
            raise ValueError(f"Unknown or unavailable variants: {sorted(missing)}")
        specs = [spec for spec in specs if spec.name in requested]
    incompatible = [spec.name for spec in specs if scheduler not in spec.schedulers]
    if incompatible:
        raise ValueError(f"Scheduler {scheduler!r} is unsupported by {incompatible}; select async or explicit variants")
    if not specs:
        raise ValueError("No runnable variants selected")
    return specs


def validation_report(rows: Sequence[sweep.Row], entries: Sequence[sweep.PlanEntry]) -> dict:
    """Require complete paired coverage and independently validated solutions."""
    expected = Counter((entry.instance.source, entry.instance.cell.n,
                        len(entry.instance.edges), entry.instance.seed,
                        entry.spec.name, entry.scheduler) for entry in entries)
    actual = Counter((row.source, row.n, row.m, row.seed, row.variant,
                      row.scheduler) for row in rows)
    gates = {
        "complete_paired_coverage": bool(expected) and expected == actual,
        "all_runs_solved": bool(rows) and all(row.status == "ok" and row.converged
                                              and not row.truncated and not row.unresolved
                                              and not row.infeasible for row in rows),
        "cover_connectivity_capacity": bool(rows) and all(
            row.valid and row.vertex_cover and row.connected and row.capacity
            and row.violations == 0 for row in rows),
        "verdict_and_trace_consistency": bool(rows) and all(
            row.verdict_agrees == "yes" and row.trace_agrees in ("yes", "none") for row in rows),
        "costs_recorded": bool(rows) and all(all(
            getattr(row, name) is not None and getattr(row, name) >= 0
            for name in ("tx", "rx", "retx", "bytes_tx", "max_payload")) for row in rows),
        "single_code_revision": len({row.code_fingerprint for row in rows}) == 1,
    }
    return {
        "passed": all(gates.values()), "gates": gates,
        "expected_runs": sum(expected.values()), "recorded_runs": len(rows),
        "status_counts": dict(sorted(Counter(row.status for row in rows).items())),
        "next_step": "Review the preflight, then validate the same cases on Mininet-WiFi."
        if all(gates.values()) else "Inspect failed rows and fix the small cases before increasing scale.",
        "mininet_wifi_validated": False,
    }


def write_outputs(out: Path, rows: Sequence[sweep.Row], manifest: dict,
                  summary: dict, validation: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*sweep.CSV_FIELDS, "backend", "target_backend"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row.as_dict(), "backend": BACKEND, "target_backend": TARGET_BACKEND})
    for name, payload in (("summary.json", {"manifest": manifest, "summary": summary,
                                           "cells": sweep.cell_coverage(rows)}),
                          ("validation.json", validation)):
        (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Small BB-CVC validation", "",
             f"- Execution backend: **{BACKEND}**", f"- Target platform: **{TARGET_BACKEND}**",
             f"- Source: **{manifest['source']}**; nodes: **{manifest['n']}**; edges: **{manifest['m']}**; capacity: **{manifest['k']}**.",
             f"- Seeds per variant: **{manifest['seeds']}**; scheduler: **{manifest['scheduler']}**.",
             f"- Gate result: **{'PASS' if validation['passed'] else 'FAIL'}**.",
             "", "These are algorithm preflight results. Wireless emulation and hardware energy were not measured.",
             "Three or four seeds are a smoke check, not evidence for broad performance claims.",
             "", "## Variant results", "", "| Variant | Runs | Solved | Other statuses |", "|---|---:|---:|---|"]
    for name in manifest["variants"]:
        selected = [row for row in rows if row.variant == name]
        statuses = Counter(row.status for row in selected if row.status != "ok")
        lines.append(f"| {name} | {len(selected)} | {sum(row.status == 'ok' for row in selected)} | {dict(statuses) if statuses else 'None'} |")
    lines += ["", "## Validation gates", ""]
    lines += [f"- {name}: **{'PASS' if passed else 'FAIL'}**" for name, passed in validation["gates"].items()]
    lines += ["", "## Adapter coverage", "",
              "DFS-Spanning-Backbone and GHS-MST-Backbone exist in variants.py but are not registered with the sweep interface. They are excluded from this preflight and require adapters before paired experiments.",
              "", validation["next_step"], "", "All unsuccessful runs remain in rows.csv with their measured costs.",
              "Comparative ratios in summary.json use the common valid subset to expose survivorship bias.", ""]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("dataset", "synthetic"), default="dataset")
    parser.add_argument("--dataset-dir")
    parser.add_argument("--seeds", type=int, choices=(3, 4), default=3)
    parser.add_argument("--n", type=int, choices=matrix.SMALL_N, default=10)
    parser.add_argument("--ratio", type=int, choices=matrix.SMALL_RATIOS, default=2)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--scheduler", choices=("sync", "async"), default="async")
    parser.add_argument("--variants", default="", help="Comma-separated names; default: all available adapters")
    parser.add_argument("--max-ms", type=int, default=600_000)
    parser.add_argument("--out", type=Path, default=Path("results/bb/smoke_codex"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    cell = matrix.Cell("small", args.n, args.ratio)
    if not cell.possible or args.k < 1 or args.max_ms < 1:
        parser.error("Require a possible simple graph, positive capacity and positive simulated time budget")
    try:
        specs = select_variants(args.variants, args.scheduler)
    except ValueError as exc:
        parser.error(str(exc))
    directory = None
    if args.source == "dataset":
        bundled = Path(__file__).resolve().parents[2] / "data/bb_smoke"
        directory = args.dataset_dir or (str(bundled) if bundled.is_dir()
                                        and args.n == 10 and args.ratio == 2
                                        else matrix.dataset_dir())
        if not directory or not Path(directory).is_dir():
            parser.error("Dataset unavailable; set --dataset-dir or explicitly select --source synthetic")
        instances = sweep.dataset_instances([cell], max_seeds=args.seeds, directory=directory)
        if len(instances) != args.seeds:
            parser.error(f"Requested {args.seeds} seeds, but found {len(instances)} instances")
    else:
        instances = [sweep.synthetic_instance(cell, seed) for seed in range(args.seeds)]
    entries = sweep.plan(instances, specs, schedulers=[args.scheduler])
    manifest = {"backend": BACKEND, "target_backend": TARGET_BACKEND, "source": args.source,
                "dataset_dir": directory, "n": args.n, "m": cell.m, "ratio": args.ratio,
                "k": args.k, "seeds": args.seeds, "seed_ids": [inst.seed for inst in instances],
                "scheduler": args.scheduler, "variants": [spec.name for spec in specs],
                "max_ms": args.max_ms, "planned_runs": len(entries), "wireless_emulation": False}
    print(json.dumps(manifest, indent=2), flush=True)
    if args.dry_run:
        return 0
    started = time.monotonic()
    rows = sweep.sweep(instances, specs, schedulers=[args.scheduler],
                       opts=sweep.SweepOptions(k=args.k, max_ms=args.max_ms),
                       progress=lambda line: print(line, flush=True))
    manifest["seconds"] = round(time.monotonic() - started, 3)
    summary = sweep.summarize(rows, specs=specs, schedulers=[args.scheduler])
    for arm in summary["_arms"]:
        if "survivorship_warning" in summary[arm]:
            summary[arm]["survivorship_warning"] = "Own-valid and common-valid ratios differ; inspect failure patterns."
    validation = validation_report(rows, entries)
    write_outputs(args.out, rows, manifest, summary, validation)
    print(f"Validation {'PASS' if validation['passed'] else 'FAIL'}: {args.out / 'validation.json'}")
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
