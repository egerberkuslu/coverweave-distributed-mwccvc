"""English PNG/SVG/PDF comparison figures from recorded paired rows only.

Usage: python3 -m ccvc.greedy.figures --rows <comparison>/rows.csv --out <figures>
No benchmark, central solver or wireless network is started by this module.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from ccvc.bb import armnames

PALETTE = ["#0072B2", "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#D55E00", "#607D8B"]


def generate(rows_path, out):
    from ccvc.greedy.compare import summarize
    rows_path, out = Path(rows_path), Path(out)
    with rows_path.open(newline="") as stream:
        rows = armnames.canonical_rows(list(csv.DictReader(stream)), column="arm")
    if not rows:
        raise ValueError("No recorded comparison rows")
    required = {"arm", "scheduler", "backend", "case", "status", "total_weight", "tx"}
    if not required <= set(rows[0]):
        raise ValueError(f"Missing comparison columns: {required - set(rows[0])}")
    backends = {row["backend"] for row in rows}
    if not backends <= {"centralized-python", "event-simulator", "mininet-wifi"}:
        raise ValueError("Every row must identify its actual supported backend")
    if {"event-simulator", "mininet-wifi"} <= backends:
        raise ValueError("Plot emulator and simulator runs separately; central references may accompany either")
    for row in rows:
        for field in ("total_weight", "tx"):
            row[field] = float(row[field]) if row[field] not in ("", "None", "null") else None
    groups = sorted({(row["arm"], row["scheduler"]) for row in rows})
    common = set(summarize(rows)["common_valid_cases"])
    out.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none", "text.color": "#37474F"}):
        fig, axes = plt.subplots(1, 3, figsize=(14, max(5.5, len(groups) * .34 + 2)))
        for y, group in enumerate(groups):
            records = [row for row in rows if (row["arm"], row["scheduler"]) == group]
            color = PALETTE[y % len(PALETTE)]
            solved = sum(row["status"] == "ok" for row in records)
            axes[0].barh(y, len(records), color="#ECEFF1", height=.55)
            axes[0].barh(y, solved, color=color, height=.55)
            axes[0].text(len(records) + .12, y, f"{solved}/{len(records)}", va="center")
            for panel, metric in ((1, "total_weight"), (2, "tx")):
                selected = [row for row in records if row["case"] in common] if panel == 1 else records
                if panel == 2 and all(row["tx"] is None for row in records):
                    axes[panel].text(.025, y, "Not measured", va="center", fontsize=8,
                                     transform=axes[panel].get_yaxis_transform())
                for j, row in enumerate(selected):
                    value = row[metric]
                    if value is None:
                        continue
                    offset = (j - (len(selected) - 1) / 2) * .14
                    marker = "o" if row["status"] == "ok" else "X"
                    axes[panel].scatter(value, y + offset, color=color, marker=marker,
                                        edgecolors="white", linewidth=.6, s=38, zorder=3)
        labels = [f"{arm} / {scheduler}" for arm, scheduler in groups]
        for index, ax in enumerate(axes):
            ax.set_yticks(range(len(groups)), labels if index == 0 else [])
            ax.invert_yaxis()
            ax.grid(axis="x", color="#ECEFF1")
            ax.set_axisbelow(True)
            ax.set_xlim(left=0)
            ax.tick_params(axis="y", length=0)
        axes[0].set_xlim(0, max(sum((row["arm"], row["scheduler"]) == group for row in rows)
                              for group in groups) + 1)
        axes[0].set_title("Completed & Valid", loc="left", fontweight="bold")
        axes[0].set_xlabel("Valid / Recorded Runs")
        axes[1].set_title("Paired Solution Weight", loc="left", fontweight="bold")
        axes[1].set_xlabel("Weight (Common Valid Cases)")
        axes[2].set_title("Communication Cost", loc="left", fontweight="bold")
        axes[2].set_xlabel("Transmitted Messages (All Outcomes)")
        fig.suptitle("MWCCVC Paired Greedy Comparison", x=.02, ha="left", fontweight="bold", fontsize=17)
        fig.text(.02, .91, f"{len(rows)} recorded runs | {len(common)} common valid cases | Backends: {', '.join(sorted(backends))}")
        fig.text(.02, .045, "Central communication is unmeasured. Small samples do not establish a statistical ranking.", fontsize=9)
        fig.text(.02, .02, "Event-simulator traffic is modeled traffic; Mininet-WiFi traffic requires actual station logs.", fontsize=9)
        fig.legend(handles=[Line2D([], [], marker="o", color="#607D8B", linestyle="", label="Completed & valid"),
                            Line2D([], [], marker="X", color="#607D8B", linestyle="", label="Other outcome")],
                   loc="lower right", frameon=False, ncol=2, bbox_to_anchor=(.98, .07))
        fig.tight_layout(rect=(0, .12, 1, .88), w_pad=2)
        for ext in ("png", "svg", "pdf"):
            fig.savefig(out / f"greedy_comparison.{ext}", dpi=190)
        plt.close(fig)
    manifest = {"source_csv": str(rows_path.resolve()),
                "source_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
                "backends": sorted(backends), "runs": len(rows), "common_valid_cases": sorted(common),
                "style": "Okabe-Ito palette; English labels", "experiments_executed_by_renderer": False}
    (out / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.rows, args.out), indent=2))
