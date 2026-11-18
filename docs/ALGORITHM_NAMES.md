# Algorithm names

The code names an arm after its mechanism, for example `GHS-MST-Backbone` or
`Anneal-Trickle`. The manuscript prints a shorter set of names. Nothing in the
code is renamed. The `variant` column of every result row, the registry keys,
the station plan directories, the module names and the tests keep the code
spellings. The translation happens only when a name is printed, through
`DISPLAY_NAMES` and `display(name)` in `ccvc/bb/armnames.py`. That module is the
only copy of the map, and `ccvc/bb/test_armnames.py` fails if a registered arm
is missing from it or if a key in it names no arm.

The baselines keep the names used in the literature. `Wu-Li CDS` implements
the marking and pruning rule of Wu and Li, and `D-GCCVC`, `D-GRCCVC` and
`D-GWCCVC` are the names that the problem paper (Kol et al., Sensors 2026) uses
for the greedy algorithms.

| Code name | Paper name | Expansion | What it does | Family | Where it lives |
|---|---|---|---|---|---|
| `BB-CVC` | **CoverWeave** | Connected capacitated cover woven from one-hop rules over a backbone | The protocol itself. Six phases: backbone, cover election, forced load, ownership contract, quiescence. Every decision comes from one-hop information in a fixed-size HELLO, and connectivity is never tested globally because the cover only grows onto vertices adjacent to a connected dominating backbone. | ours | `ccvc/bb/bbcvc.py` |
| `MIS-Connector-Backbone` | **NexusWarp** | Nexus-elected connectors on weighted-key anchors forming the backbone warp | Phase 1 is a maximal independent set plus the connectors that join it, both elected without spending a message: a node compares the key `(w/(deg+1), id)` it already hears against its own. Phase 5 stays local. | ours | `ccvc/bb/sweep.py` |
| `MIS-Connector-TreeAgg` | **NexusWarp-T** | the same, with tree-aggregated quiescence | Identical Phase 1. Phase 5 aggregates over the tree. The pair differs in the `enable_tree` flag alone. | ours | `ccvc/bb/sweep.py` |
| `GHS-MST-Backbone` | **FabricTree** | Spanning tree hardened with unicast timers, tagged levels and edge-named fragments | Phase 1 is a distributed minimum spanning tree in the Gallager, Humblet and Spira line. The backbone is the tree's internal vertices. The hardening is what the lossy channel forced: TEST, CONNECT and REPORT are all re-askable, a fragment is named by the edge rather than by its weight, and a report carries the round it belongs to. | ours | `ccvc/bb/v4_mst.py` |
| `Anneal-Local` | **TemperFlux** | Temperature-driven edge-ownership minimisation with periodic exclusion and repair | Elects no backbone at all. It reaches connectivity through an energy term instead, taking local decisions only. | ours | `ccvc/bb/v6_anneal.py` |
| `Anneal-TreeAgg` | **TemperFlux-T** | the same, reporting through tree aggregation | Identical annealing. The report path aggregates over the tree. | ours | `ccvc/bb/v6_anneal.py` |
| `Anneal-Trickle` | **TemperFlux-Tk** | the same, on a Trickle-scheduled HELLO | Identical annealing, paced by Trickle-timed HELLO suppression, which is what makes it the quietest arm of the family. | ours | `ccvc/bb/v6_anneal.py` |
| `DFS-Spanning-Backbone` | **TokenTrail** | Token-relayed depth-first spanning tree with local assignment | A token walk builds a depth-first spanning tree and its internal vertices are the cover, which is Savage's provable 2-approximation. Fully distributed, with no seeding. | ours | `ccvc/bb/v1_dfs.py` |
| `WuLi-Dominating-Exact` | **Wu-Li CDS** | Wu and Li marking with Rule-k pruning | Marking and pruning as published, carrying the exact neighbour list in HELLO. | baseline | `ccvc/bb/v5_wuli.py` |
| `WuLi-Dominating-Bloom` | **Wu-Li CDS/B** | the same marking, Bloom-filter encoding | Identical rule. The neighbour set is summarised into a Bloom filter. | baseline | `ccvc/bb/v5_wuli.py` |
| `WuLi-Dominating-Chunked` | **Wu-Li CDS/C** | the same marking, chunked encoding | Identical rule. The neighbour set is spread across periods in chunks. | baseline | `ccvc/bb/v5_wuli.py` |
| `Greedy-Degree-Backbone` | **D-GCCVC** | distributed greedy connected capacitated vertex cover, degree score | Our distributed adaptation on the shared CoverWeave node core. A node maximises its degree. | baseline | `ccvc/greedy/distributed.py` |
| `Greedy-Ratio-Backbone` | **D-GRCCVC** | the same, weight-over-degree ratio score | Identical machinery. A node maximises the weight-over-degree ratio. | baseline | `ccvc/greedy/distributed.py` |
| `Greedy-Weight-Backbone` | **D-GWCCVC** | the same, weight score | Identical machinery. A node takes the lowest weight. | baseline | `ccvc/greedy/distributed.py` |
| `Greedy-Degree-Upstream` | **C-GCCVC** | centralized reference, degree score | The pinned central reference implementation of the same score, used as a yardstick and never as a distributed arm. | baseline | `ccvc/greedy/central.py`, over the pinned published MWCCVC code |
| `Greedy-Ratio-Upstream` | **C-GRCCVC** | centralized reference, ratio score | As above, ratio score. | baseline | `ccvc/greedy/central.py` |
| `Greedy-Weight-Upstream` | **C-GWCCVC** | centralized reference, weight score | As above, weight score. | baseline | `ccvc/greedy/central.py` |

Two names in the paper are not arms and therefore have no row above and no key
in `DISPLAY_NAMES`.

| Paper name | What it names | What it does | Where it lives |
|---|---|---|---|
| **CoverAudit** | the independent validator | Recomputes the eight MWCCVC rules from raw output and reads no counter a node kept. A run's verdict says only the termination mode, so a frozen but invalid run still has to report `solved` for the validator to be able to contradict it. The name answers the danger the paper calls silent success. | `ccvc/bb/validate.py` |
| **ProAsk** | the loss invariant of the discussion | A question asked once with no way back is a defect. Every message must be re-askable, and a repeat is only safe where answering twice changes nothing, so idempotence is the other half of the rule. | stated in the discussion section, enforced across the arms |
