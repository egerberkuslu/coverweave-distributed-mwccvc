"""English, measured smoke plots; every dot is one recorded run.

Usage: python -m ccvc.bb.smoke_figures --rows results/bb/smoke_codex/rows.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from ccvc.bb import armnames

PALETTE = ['#0072B2', '#009E73', '#E69F00', '#CC79A7', '#56B4E9', '#D55E00', '#607D8B']


def generate(rows_path: Path, out: Path) -> dict:
    with rows_path.open(newline='') as stream:
        rows = armnames.canonical_rows(list(csv.DictReader(stream)))
    if not rows:
        raise ValueError('Cannot plot an empty measurement file')
    backends = {r.get('backend', '') for r in rows}
    if not backends <= {'event-simulator', 'mininet-wifi'} or len(backends) != 1:
        raise ValueError('Exactly one explicitly identified execution backend is required')
    groups = defaultdict(list)
    for row in rows:
        groups[row['variant']].append(row)
    names = sorted(groups)
    backend = 'Event Simulator' if backends == {'event-simulator'} else 'Mininet-WiFi'
    sources = ', '.join(sorted({r['source'] for r in rows}))
    out.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#37474F', 'text.color': '#263238',
                         'svg.hashsalt': 'bb-smoke', 'svg.fonttype': 'none'}):
        fig, axes = plt.subplots(1, 3, figsize=(13, 5.8), gridspec_kw={'width_ratios': [1, 1, 1]})
        panels = [('valid', 'Valid Solutions', 'Validated / Recorded Runs'),
                  ('tx', 'Communication Cost', 'Transmitted Messages'),
                  ('total_weight', 'Solution Weight', 'Weight (Valid Solutions Only)')]
        for ax, (metric, title, xlabel) in zip(axes, panels):
            for y, name in enumerate(names):
                records = groups[name]
                color = PALETTE[y % len(PALETTE)]
                valid = [r for r in records if r['valid'].lower() == 'true']
                if metric == 'valid':
                    ax.barh(y, len(records), color='#ECEFF1', height=.53)
                    ax.barh(y, len(valid), color=color, height=.53)
                    ax.text(len(records) + .1, y, f'{len(valid)}/{len(records)}', va='center', fontsize=9)
                else:
                    selected = valid if metric == 'total_weight' else records
                    for j, row in enumerate(selected):
                        raw = row[metric]
                        if raw in ('', 'None'):
                            continue
                        value = float(raw)
                        offset = (j - (len(selected) - 1) / 2) * .15
                        is_valid = row['valid'].lower() == 'true'
                        ax.scatter(value, y + offset, s=43, marker='o' if is_valid else 'X',
                                   color=color, edgecolors='white', linewidths=.6, zorder=3)
            ax.set_title(title, loc='left', fontweight='bold', pad=15)
            ax.set_xlabel(xlabel, labelpad=12)
            ax.set_yticks(range(len(names)))
            ax.set_yticklabels(names if metric == 'valid' else [])
            ax.invert_yaxis()
            ax.set_axisbelow(True)
            ax.grid(axis='x', color='#ECEFF1')
            ax.tick_params(axis='y', length=0)
            ax.set_xlim(left=0)
            if metric == 'valid':
                ax.set_xlim(0, max(map(len, groups.values())) + 1)
                ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        fig.suptitle(f'BB-CVC Small Validation | {backend}', x=.02, ha='left', fontsize=17, fontweight='bold')
        fig.text(.02, .91, f'{len(rows)} recorded runs | {len(names)} variants | Input source: {sources}', fontsize=10)
        fig.legend(handles=[Line2D([], [], marker='o', color='#607D8B', linestyle='', label='Valid run'),
                            Line2D([], [], marker='X', color='#607D8B', linestyle='', label='Invalid / unresolved run')],
                   loc='lower right', bbox_to_anchor=(.98, .01), frameon=False, ncol=2)
        fig.text(.02, .065, 'Every dot is a recorded run. Communication includes unsuccessful runs.', fontsize=9)
        fig.text(.02, .025, 'Small-sample smoke validation; no statistical ranking or radio-performance claim.', fontsize=9)
        fig.tight_layout(rect=(0, .12, 1, .88), w_pad=2)
        for ext in ('png', 'svg', 'pdf'):
            metadata = {'Date': None} if ext == 'svg' else ({'CreationDate': None, 'ModDate': None} if ext == 'pdf' else {})
            fig.savefig(out / f'smoke_overview.{ext}', dpi=190, metadata=metadata)
        plt.close(fig)
    manifest = {'source_csv': str(rows_path.resolve()), 'source_sha256': hashlib.sha256(rows_path.read_bytes()).hexdigest(),
                'backend': next(iter(backends)), 'runs': len(rows), 'variants': names,
                'style': 'figure-maker STYLE.md / Okabe-Ito palette',
                'semantics': 'One point per recorded run; weight includes valid solutions only; no confidence intervals.'}
    (out / 'provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('results/bb/figures/smoke_codex'))
    args = parser.parse_args()
    print(json.dumps(generate(args.rows, args.out), indent=2))


if __name__ == '__main__':
    main()
