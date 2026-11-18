# Stage `xlarge` — BB-CVC full Dagdeviren sweep

Integrity verdict: **PROBLEMS**

| field | value |
|---|---|
| ns | 250,500,750,1000 |
| ratios | 2,4,6 |
| max_seeds | 10 |
| k | 6 |
| max_ms | 102000000 |
| mis_nbrs_max | 64 |
| schedulers | sync,async |
| shards | 12 |
| seconds | 27837.0 |
| code fingerprint | `798b4393cb4f` and `bebb0f917410` |
| rows | 300 (expected 300) |
| instances | 12 |
| arm x scheduler configs | 25 |
| missing / duplicate rows | 0 / 0 |
| false successes (verdict=solved, valid=False) | **0** |
| contradiction rows | 0 |
| skipped (time budget) | 67 |
| instances provably infeasible (flow witness) | 0 |
| instances infeasible by counting bound m > nk | 0 |
| instances feasibility unknown (n > 200) | 12 |
| instances scored (neither) | 12 |
| common valid subset | 7 |

## What the exact-optimum column does and does not cover

`exact_weight` is filled only where `SweepOptions.exact_max_n` lets the solver run, and that limit is 18, so at most the n = 10 and n = 15 cells carry a proven optimum while every larger cell reports a ratio against the best arm instead. The limit is a stale guess: `docs/EXACT_COMPARE.md` measures `ccvc.central.solve_exact` proving optima for every feasible instance up to n = 50 within minutes. It was left alone on purpose, because `exact_max_n` lives in `sweep.py` and editing it would move the code fingerprint under a running sweep; the wider comparison comes from the exact-compare join against these same instances.

## Which code measured which rows

See `FINGERPRINTS.md` for why this can hold two values: the twelve non-GHS arms are measured against a snapshot frozen at the start of the night, and GHS-MST-Backbone is measured in a later pass against whatever `v4_mst.py` is declared final.

| fingerprint | arms |
|---|---|
| `798b4393cb4f` | 12 arms: `Anneal-Local`, `Anneal-TreeAgg`, `Anneal-Trickle`, `DFS-Spanning-Backbone`, `Greedy-Degree-Backbone`, `Greedy-Ratio-Backbone`, `Greedy-Weight-Backbone`, `MIS-Connector-Backbone`, `MIS-Connector-TreeAgg`, `WuLi-Dominating-Bloom`, `WuLi-Dominating-Chunked`, `WuLi-Dominating-Exact` |
| `bebb0f917410` | `GHS-MST-Backbone` |

## Status inventory

| status | rows |
|---|---|
| `ok` | 183 |
| `skipped` | 67 |
| `infeasible` | 50 |

## Valid share per arm, on scored instances only

Instances that are provably infeasible or infeasible by the counting bound are excluded from the denominator: no arm can solve them, so counting them as arm failures would move every arm together.

| arm | valid / scored |
|---|---|
| `Anneal-Local/async` | 7/12 |
| `Anneal-Local/sync` | 7/12 |
| `Anneal-TreeAgg/async` | 7/12 |
| `Anneal-TreeAgg/sync` | 7/12 |
| `Anneal-Trickle/async` | 7/12 |
| `DFS-Spanning-Backbone/async` | 8/12 |
| `DFS-Spanning-Backbone/sync` | 8/12 |
| `GHS-MST-Backbone/async` | 8/12 |
| `GHS-MST-Backbone/sync` | 8/12 |
| `Greedy-Degree-Backbone/async` | 7/12 |
| `Greedy-Degree-Backbone/sync` | 7/12 |
| `Greedy-Ratio-Backbone/async` | 7/12 |
| `Greedy-Ratio-Backbone/sync` | 7/12 |
| `Greedy-Weight-Backbone/async` | 7/12 |
| `Greedy-Weight-Backbone/sync` | 7/12 |
| `MIS-Connector-Backbone/async` | 8/12 |
| `MIS-Connector-Backbone/sync` | 8/12 |
| `MIS-Connector-TreeAgg/async` | 8/12 |
| `MIS-Connector-TreeAgg/sync` | 8/12 |
| `WuLi-Dominating-Bloom/async` | 7/12 |
| `WuLi-Dominating-Bloom/sync` | 7/12 |
| `WuLi-Dominating-Chunked/async` | 7/12 |
| `WuLi-Dominating-Chunked/sync` | 7/12 |
| `WuLi-Dominating-Exact/async` | 7/12 |
| `WuLi-Dominating-Exact/sync` | 7/12 |

## Valid share by node count

| n | valid / scored rows |
|---|---|
| 250 | 50/75 |
| 500 | 50/75 |
| 750 | 50/75 |
| 1000 | 33/75 |

## Problems

- 67 rows skipped by the time budget

Source: `results/bb/full_v3/xlarge`
