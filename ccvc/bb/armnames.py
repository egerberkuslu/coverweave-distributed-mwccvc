#!/usr/bin/env python3
"""The one place that knows what an experiment arm is called.

WHY THIS MODULE EXISTS. The arms used to be called `V1-DFS`, `V2-BB-local`,
`V4-BB-MST`, `V5-BB-WuLi-frag`, `D-GRCCVC-BB` and so on. Those names encode the
order in which the arms were written, not what they do, so every table, figure
and paragraph had to be read next to a legend. The names now say the mechanism:
what replaces Phase 1 and, where a family has variants, what distinguishes them.

THE OLD NAMES SURVIVE IN MEASURED DATA. A sweep writes its arm into the
`variant` column of `rows.csv`, and those files were measured over hours; every
sweep recorded before the rename carries the old spelling. Re-running them to
change a string would discard evidence for nothing. `canonical` therefore
translates on read, and `LEGACY_NAMES` is the single table that records the
correspondence. Nothing else in the repository may hold a private copy of it.

READ DIRECTION ONLY. Old names are accepted where measured data or an archived
plan is loaded. Nothing writes an old name again: `VariantSpec.name` and the
registries below carry the new spelling, so a fresh sweep produces only new
names and a pooled table of old and new rows agrees with itself.
"""
from __future__ import annotations

from typing import Dict

#: Old arm name -> new arm name.
#:
#: The left column is frozen: it is what earlier `results/bb/sweep_*/rows.csv`,
#: `results/greedy/*/plan.json` and the archived station-plan directory names
#: actually contain. Adding a row here is how a further rename stays readable
#: against data already on disk; editing or deleting a row silently orphans it.
LEGACY_NAMES: Dict[str, str] = {
    # Phase 1 replaced by a DFS spanning tree; its internal vertices are the
    # cover (Savage 1982, the provable 2-approximation).
    "V1-DFS": "DFS-Spanning-Backbone",
    # Phase 1 is the MIS plus connectors; Phase 5 stays local (5a) or adds the
    # tree aggregation (5b). The pair differs in `enable_tree` alone.
    "V2-BB-local": "MIS-Connector-Backbone",
    "V3-BB-tree": "MIS-Connector-TreeAgg",
    # Phase 1 replaced by a distributed minimum spanning tree (Gallager,
    # Humblet and Spira); the backbone is the tree's internal vertices.
    "V4-BB-MST": "GHS-MST-Backbone",
    # Wu and Li marking with Rule-k pruning. The three arms differ only in how
    # a node encodes its neighbour set into HELLO, so the suffix names the
    # encoding: the exact list, a Bloom filter, or chunks across periods.
    "V5-BB-WuLi-full": "WuLi-Dominating-Exact",
    "V5-BB-WuLi-bloom": "WuLi-Dominating-Bloom",
    "V5-BB-WuLi-frag": "WuLi-Dominating-Chunked",
    "V5-BB-WuLi": "WuLi-Dominating",          # family prefix, message-size runs
    # Distributed annealing. The suffix names how the arm reports and paces:
    # local decisions only, tree aggregation, or Trickle-timed suppression.
    "V6-ANNEAL": "Anneal-Local",
    "V6-ANNEAL-tree": "Anneal-TreeAgg",
    "V6-ANNEAL-trickle": "Anneal-Trickle",
    # The three greedy baselines differ ONLY in the score a node maximises, so
    # the middle word is that score, not the shared word "cover": `gccvc`
    # takes the highest degree, `grccvc` the best weight-over-degree ratio and
    # `gwccvc` the lowest weight. "Backbone" is our distributed adaptation on
    # the shared BB-CVC node core; "Upstream" is the pinned central reference
    # implementation in external_sources/MWCCVC.
    "D-GCCVC-BB": "Greedy-Degree-Backbone",
    "D-GRCCVC-BB": "Greedy-Ratio-Backbone",
    "D-GWCCVC-BB": "Greedy-Weight-Backbone",
    "C-GCCVC-UPSTREAM": "Greedy-Degree-Upstream",
    "C-GRCCVC-UPSTREAM": "Greedy-Ratio-Upstream",
    "C-GWCCVC-UPSTREAM": "Greedy-Weight-Upstream",
}

#: Greedy scoring rule -> the word that names it in an arm name. The rule keys
#: are the upstream identifiers and must not be renamed: they are the function
#: names inside the pinned `external_sources/MWCCVC` checkout and the
#: `node_kind` recorded in archived `run.json` documents.
GREEDY_RULE_WORD: Dict[str, str] = {
    "gccvc": "Degree",
    "grccvc": "Ratio",
    "gwccvc": "Weight",
}


def greedy_arm(rule: str, role: str) -> str:
    """Name a greedy arm: `role` is "Backbone" (ours) or "Upstream" (central)."""
    if rule not in GREEDY_RULE_WORD:
        raise ValueError(f"unknown greedy rule {rule!r}")
    if role not in ("Backbone", "Upstream"):
        raise ValueError(f"unknown greedy role {role!r}")
    return f"Greedy-{GREEDY_RULE_WORD[rule]}-{role}"


def canonical(name: str) -> str:
    """Translate an arm name read from measured data or an archived plan.

    Unknown names pass through unchanged. A table built from a sweep older than
    the rename would otherwise list the same arm twice under two spellings and
    average each half separately, which reads as a real difference between two
    arms rather than as one arm split in two.

    Compound labels keep their shape: `arm/scheduler` and the message-size
    label `family/scheduler/encoding/policy` are translated on their first
    field only, because the remaining fields are not arm names.
    """
    if name in LEGACY_NAMES:
        return LEGACY_NAMES[name]
    head, sep, tail = name.partition("/")
    if sep and head in LEGACY_NAMES:
        return LEGACY_NAMES[head] + sep + tail
    return name


def canonical_rows(rows, column: str = "variant"):
    """Rewrite `column` in place across loaded CSV rows. Returns the rows."""
    for row in rows:
        value = row.get(column)
        if value:
            row[column] = canonical(value)
    return rows


# ==========================================================================
# THE NAMES THE MANUSCRIPT PRINTS
# ==========================================================================
#: Repository arm name -> the name the paper prints for it.
#:
#: WHY A SECOND MAP AND NOT A RENAME. `LEGACY_NAMES` above translates names that
#: measured data already contains, so it is read on the way IN. This one is read
#: on the way OUT, at the moment a name is printed into a table cell, a figure
#: legend or a sentence. Nothing in the repository is renamed: the `variant`
#: column of every `rows.csv`, the registry keys, the station-plan directories,
#: the module names and the tests keep the spellings they have, so no
#: measurement is invalidated and no sweep has to be re-run to change a string.
#:
#: THE BASELINES KEEP THEIR PUBLISHED IDENTITY. The Wu and Li arms are named
#: after the published marking rule they implement, and the three greedy
#: adaptations go back to the group's own identifiers, which is what the cited
#: work calls them. Only the arms this project contributes get a new name.
#:
#: WHAT EACH NAME MEANS AND WHAT THE ARM DOES.
#:
#:   CoverWeave         BB-CVC, the protocol itself.
#:                      "Connected capacitated cover woven from one-hop rules
#:                      over a backbone." Six-phase node program: backbone,
#:                      cover election, forced load, ownership contract,
#:                      quiescence. Every decision is taken from one-hop
#:                      information carried in a fixed-size HELLO, and
#:                      connectivity is never tested globally: it is preserved
#:                      by construction because the cover only ever grows onto
#:                      vertices adjacent to a connected dominating backbone.
#:                      Lives in `ccvc/bb/bbcvc.py`.
#:
#:   NexusWarp           MIS-Connector-Backbone.
#:                      "Nexus-elected connectors on weighted-key anchors
#:                      forming the backbone warp." Phase 1 is a maximal independent set
#:                      plus the connectors that join it, both elected without
#:                      spending a message: a node compares the key
#:                      (w/(deg+1), id) it already hears against its own.
#:                      Phase 5 stays local. Lives in `ccvc/bb/sweep.py`.
#:
#:   NexusWarp-T         MIS-Connector-TreeAgg. The same Phase 1 with tree
#:                      aggregation in Phase 5; the pair differs in the
#:                      `enable_tree` flag alone.
#:
#:   FabricTree        GHS-MST-Backbone.
#:                      "Spanning tree hardened with unicast timers, tagged
#:                      levels and edge-named fragments." Phase 1 is a
#:                      distributed minimum spanning tree in the Gallager,
#:                      Humblet and Spira line, and the backbone is the tree's
#:                      internal vertices. The hardening is what the lossy
#:                      channel forced: TEST, CONNECT and REPORT are all
#:                      re-askable, a fragment is named by the edge rather than
#:                      by its weight, and a report carries the round it
#:                      belongs to. Lives in `ccvc/bb/v4_mst.py`.
#:
#:   TemperFlux         Anneal-Local.
#:                      "Temperature-driven edge-ownership minimisation with
#:                      periodic exclusion and repair." Elects no backbone at
#:                      all: it reaches connectivity through an energy term
#:                      instead, taking local decisions only. Lives in
#:                      `ccvc/bb/v6_anneal.py`.
#:
#:   TemperFlux-T       Anneal-TreeAgg. The same annealing, reporting through
#:                      tree aggregation.
#:
#:   TemperFlux-Tk      Anneal-Trickle. The same annealing, paced by
#:                      Trickle-timed HELLO suppression, which is what makes it
#:                      the quietest arm of the family.
#:
#:   TokenTrail         DFS-Spanning-Backbone.
#:                      "Token-relayed depth-first spanning tree with local
#:                      assignment." A token walk builds a depth-first spanning
#:                      tree and its internal vertices are the cover, which is
#:                      Savage's provable 2-approximation. Fully distributed,
#:                      with no seeding. Lives in `ccvc/bb/v1_dfs.py`.
#:
#:   Wu-Li CDS          WuLi-Dominating-Exact, and /B, /C for Bloom and
#:   Wu-Li CDS/B        Chunked. Wu and Li marking with Rule-k pruning. The
#:   Wu-Li CDS/C        three differ ONLY in how a node encodes its neighbour
#:                      set into HELLO, so the suffix names the encoding: the
#:                      exact list, a Bloom filter, or chunks spread across
#:                      periods. Lives in `ccvc/bb/v5_wuli.py`.
#:
#:   D-GCCVC            Greedy-Degree-Backbone, and D-GRCCVC, D-GWCCVC for the
#:   D-GRCCVC           ratio and weight scores. Our distributed adaptation of
#:   D-GWCCVC           the group's three greedy baselines on the shared
#:                      CoverWeave node core, differing only in the score a
#:                      node maximises: highest degree, best weight-over-degree
#:                      ratio, lowest weight. Lives in
#:                      `ccvc/greedy/distributed.py`.
#:
#:   C-GCCVC            Greedy-Degree-Upstream, and C-GRCCVC, C-GWCCVC. The
#:   C-GRCCVC           pinned central reference implementations of the same
#:   C-GWCCVC           three scores, used as a centralized yardstick and never
#:                      as a distributed arm. Lives in `ccvc/greedy/central.py`
#:                      over the checkout in `external_sources/MWCCVC`.
#:
#: TWO NAMES THAT ARE NOT ARMS AND THEREFORE NOT IN THIS MAP.
#:
#:   CoverAudit       The independent validator in `ccvc/bb/validate.py`. It
#:                      recomputes the eight MWCCVC rules from raw output and
#:                      reads no counter a node kept, so a run's verdict says
#:                      only the termination mode and a frozen but invalid run
#:                      still has to report `solved` for the validator to be
#:                      able to contradict it. The name answers the danger the
#:                      paper calls silent success.
#:
#:   ProAsk           The loss invariant of the discussion: a question asked
#:                      once with no way back is a defect. Every message must
#:                      be re-askable, and a repeat is only safe where
#:                      answering twice changes nothing, so idempotence is the
#:                      other half of the rule.
DISPLAY_NAMES: Dict[str, str] = {
    "BB-CVC": "CoverWeave",
    "MIS-Connector-Backbone": "NexusWarp",
    "MIS-Connector": "NexusWarp",
    "MIS-Connector-TreeAgg": "NexusWarp-T",
    "GHS-MST-Backbone": "FabricTree",
    "GHS-MST": "FabricTree",
    "Anneal-Local": "TemperFlux",
    "Anneal-TreeAgg": "TemperFlux-T",
    "Anneal-Trickle": "TemperFlux-Tk",
    "DFS-Spanning-Backbone": "TokenTrail",
    "DFS-Spanning": "TokenTrail",
    "WuLi-Dominating-Exact": "Wu-Li CDS",
    "WuLi-Dominating-Bloom": "Wu-Li CDS/B",
    "WuLi-Dominating-Chunked": "Wu-Li CDS/C",
    "WuLi-Dominating": "Wu-Li CDS",
    "WuLi-Exact": "Wu-Li CDS",
    "WuLi-Bloom": "Wu-Li CDS/B",
    "WuLi-Chunked": "Wu-Li CDS/C",
    "Greedy-Degree-Backbone": "D-GCCVC",
    "Greedy-Ratio-Backbone": "D-GRCCVC",
    "Greedy-Weight-Backbone": "D-GWCCVC",
    "Greedy-Degree-Upstream": "C-GCCVC",
    "Greedy-Ratio-Upstream": "C-GRCCVC",
    "Greedy-Weight-Upstream": "C-GWCCVC",
}


def display(name: str) -> str:
    """The manuscript spelling of an arm name. Unknown names pass through.

    A legacy name is canonicalised first, so a table built from a sweep older
    than the rename prints the same label as a table built from a fresh one.

    Compound labels keep their shape: `arm/scheduler` and the message-size
    label `family/scheduler/encoding/policy` are translated on their first
    field only, because the remaining fields are not arm names.
    """
    canon = canonical(name)
    if canon in DISPLAY_NAMES:
        return DISPLAY_NAMES[canon]
    head, sep, tail = canon.partition("/")
    if sep and head in DISPLAY_NAMES:
        return DISPLAY_NAMES[head] + sep + tail
    return canon
