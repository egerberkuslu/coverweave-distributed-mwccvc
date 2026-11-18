# Stage `mediumdense` — BB-CVC full Dagdeviren sweep

Integrity verdict: **CLEAN**

| field | value |
|---|---|
| ns | 100 |
| ratios | 10 |
| max_seeds | 10 |
| k | 6 |
| max_ms | 12000000 |
| mis_nbrs_max | 64 |
| schedulers | sync,async |
| shards | 10 |
| seconds | 54820.3 |
| code fingerprint | `bebb0f917410` |
| rows | 250 (expected 250) |
| instances | 10 |
| arm x scheduler configs | 25 |
| missing / duplicate rows | 0 / 0 |
| false successes (verdict=solved, valid=False) | **0** |
| contradiction rows | 0 |
| skipped (time budget) | 0 |
| instances provably infeasible (flow witness) | 10 |
| instances infeasible by counting bound m > nk | 10 |
| instances feasibility unknown (n > 200) | 0 |
| instances scored (neither) | 0 |
| common valid subset | 0 |

## What the exact-optimum column does and does not cover

`exact_weight` is filled only where `SweepOptions.exact_max_n` lets the solver run, and that limit is 18, so at most the n = 10 and n = 15 cells carry a proven optimum while every larger cell reports a ratio against the best arm instead. The limit is a stale guess: `docs/EXACT_COMPARE.md` measures `ccvc.central.solve_exact` proving optima for every feasible instance up to n = 50 within minutes. It was left alone on purpose, because `exact_max_n` lives in `sweep.py` and editing it would move the code fingerprint under a running sweep; the wider comparison comes from the exact-compare join against these same instances.

## Which code measured which rows

See `FINGERPRINTS.md` for why this can hold two values: the twelve non-GHS arms are measured against a snapshot frozen at the start of the night, and GHS-MST-Backbone is measured in a later pass against whatever `v4_mst.py` is declared final.

| fingerprint | arms |
|---|---|
| `bebb0f917410` | 13 arms: `Anneal-Local`, `Anneal-TreeAgg`, `Anneal-Trickle`, `DFS-Spanning-Backbone`, `GHS-MST-Backbone`, `Greedy-Degree-Backbone`, `Greedy-Ratio-Backbone`, `Greedy-Weight-Backbone`, `MIS-Connector-Backbone`, `MIS-Connector-TreeAgg`, `WuLi-Dominating-Bloom`, `WuLi-Dominating-Chunked`, `WuLi-Dominating-Exact` |

## Status inventory

| status | rows |
|---|---|
| `infeasible` | 250 |

## Valid share per arm, on scored instances only

Instances that are provably infeasible or infeasible by the counting bound are excluded from the denominator: no arm can solve them, so counting them as arm failures would move every arm together.

| arm | valid / scored |
|---|---|

## Valid share by node count

| n | valid / scored rows |
|---|---|

Source: `results/bb/full_v3/mediumdense`
