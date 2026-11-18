# Reproducing the revised manuscript

This guide follows the pre-registration in
[contract/R1_PREREG.md](../contract/R1_PREREG.md) and the docstrings of the
modules it names. Run every command from the repository root.

## 1. Environment

Use Python 3.12 on Linux. The protocol, the simulator, the validator, the
held-out generator and the runner need the standard library only. The
statistics need `numpy` and `scipy`, the figures and tables need `matplotlib`,
and the tests need `pytest`. The emulation block needs Mininet-WiFi with
wmediumd and root.

```bash
python3 -m pip install numpy scipy matplotlib networkx pytest
python3 tools/fetch_dagdeviren.py
```

The second command downloads the 360 benchmark files into
`data/DagdevirenDataset/` at a pinned revision and checks their bytes.

## 2. Frozen version

```bash
git fetch --tags
git checkout coverweave-r1-frozen
python3 -c 'from ccvc.bb import sweep; print(sweep.code_fingerprint())'
```

The printed fingerprint must equal the `code_fingerprint` column of every
published result row. Export it so that the runner refuses any other code.

```bash
export R1_FROZEN_FINGERPRINT=$(python3 -c 'from ccvc.bb import sweep; print(sweep.code_fingerprint())')
export BB_SNAPSHOT=$PWD PYTHONPATH=$PWD
```

## 3. Tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc -q
```

The regression tests of the repairs F1 to F6 are in
`ccvc/bb/test_r1_repairs.py` and `ccvc/bb/test_validator_double_owner.py`.

## 4. Held-out instance sets

```bash
for s in H1 H1-large H2a H2b W M9; do
  python3 -m ccvc.bb.heldout --set $s --out heldout
done
```

Without `--seeds` the generator draws the pre-registered seeds of section 3 of
the pre-registration and its amendments. It writes the files in the format of
the published benchmark under `heldout/<family>/<cell>/` and records the
generator, parameters, seed and sha256 of every file in
`heldout/manifest.json`. Compare that manifest with the one published with the
frozen results before running anything. The reserve set (`--set reserve`) is
sealed and is generated only if a repaired version has to be evaluated, as
section 1 of the pre-registration describes.

## 5. Running the blocks

Every block is a list of jobs for `ccvc/bb/r1_run.py`, one JSON object per line.
A job names one instance, one capacity `k`, one channel condition `loss`, one
channel seed `rng_seed` and the arm and scheduler configurations to run. The
docstring of `ccvc/bb/r1_run.py` lists every key.

```bash
python3 -m ccvc.bb.r1_run --jobs <block>/jobs.jsonl --id <job id>
```

Each job appends its rows to its own CSV and leaves `<out>.done` when it is
finished, so a crash costs at most one run and a restart skips finished
configurations. Provably infeasible instances run one witness configuration,
except in block M9, whose jobs set `all_configs_on_infeasible`. Block M8 passes
parameter overrides in `params`, which the rows record.

| Block | Content | Jobs |
| --- | --- | --- |
| M2 | development set at the tag, all 25 configurations on every feasible instance and one witness configuration on every infeasible one | `data/DagdevirenDataset` |
| M3 | H1 and H1-large, 25 configurations | `heldout/H1` |
| M4 | H2a and H2b, 25 configurations | `heldout/H2a`, `heldout/H2b` |
| M5 | capacity tightness, k varied per cell | `heldout/H1`, `heldout/H2a` |
| M6 | loss conditions `0`, `0.05`, `0.1`, `0.2`, `0.3`, `ge:0.05:4`, `ge:0.1:4`, `ge:0.2:4` and `emp` | 60 held-out instances, 3 channel seeds |
| M7 | Mininet-WiFi, the 27 development runs and set W | `ccvc/bb/mnwifi/run.py` |
| M8 | one factor at a time around the default parameters | `params` overrides |
| M9 | instances that only the flow check proves infeasible | `heldout/M9` |

> The `jobs.jsonl` file of each block is published with the frozen results, and
> this table will then name its path.

Block M7 runs on the emulator. For each station graph,

```bash
python3 -m ccvc.bb.mnwifi.run plan --graph <graph.json> --k <k> --mode <sync|async> \
    --node <bbcvc|mst|anneal> --run-id <name> --run-root <directory>
sudo -E env PYTHONPATH=$PWD python3 ccvc/bb/mnwifi/run.py run --resume <directory>/<name>
python3 -m ccvc.bb.mnwifi.run collect <directory>/<name>
```

`plan` prints the exact privileged command. The per-link delivery ratios that
the `emp` condition of M6 uses are derived from the logs of these runs, as
amendment 3 of the pre-registration states.

## 6. Statistics

```bash
python3 -m ccvc.bb.revision_stats --rows <block>/*.csv \
    --instance-dir <instance directory> --out <block>/stats
```

The unit of analysis is the instance. Runs of one condition, instance and arm
are averaged first, and paired tests are made across instances. Instances with
m = nk, whose only cover is the set of all nodes, are kept out of every quality
number and get their own validity table. Provably infeasible instances are
never scored for quality. Proven optima and centralized results are joined only
to instances read from the published benchmark directory. The script writes `summary.md`, `validity.csv`, `quality.csv`,
`tests.csv`, `lp_bounds.csv` and further CSV files.

## 7. Tables

The tables of the revised manuscript are built from the files of step 6.

> The table generator of the revised manuscript is named here when the frozen
> results are published.
