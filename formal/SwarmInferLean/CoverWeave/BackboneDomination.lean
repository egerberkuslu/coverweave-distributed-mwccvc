import SwarmInferLean.CoverWeave.Backbone

/-!
# CoverWeave, C2: backbone domination (combinatorial core)

Source: `CoverWeave_R1/sections/04-formaleng.tex:49`, label `lem:backbone`, "Backbone domination":
"After Phase 1a, the MIS set is a maximal independent set on Ĝ* and hence dominates every node
with an edge in Ĝ*."

The MIS set of Phase 1a is read as the key-greedy set `keyGreedy G key` of `Backbone.lean`.
The statement as written is false whenever Ĝ* has an isolated vertex, because Algorithm
`alg:mis` puts such a node into OUT and an isolated vertex can always be added to an
independent set. This holds even for a connected Ĝ* with one node. This file proves the
counterexamples and the repaired statements (a) to (d) of the inventory entry C2.

Not formalized: that the distributed Phase 1a run computes exactly `keyGreedy G key` (it needs
the execution model E7: frames, records read atomically from one HELLO, the phase barrier).
-/

namespace SwarmInfer.CoverWeave

open SimpleGraph

variable {V K : Type*} [LinearOrder K] [Finite V]

/-- (a) The key-greedy set is independent. -/
theorem keyGreedy_isIndepSet (G : SimpleGraph V) {key : V → K} (hkey : Function.Injective key) :
    G.IsIndepSet {v | keyGreedy G key v} := by
  intro u hu v hv huv hadj
  rcases lt_or_gt_of_ne (hkey.ne huv) with h | h
  · exact ((keyGreedy_iff G key v).1 hv).2 u hadj h hu
  · exact ((keyGreedy_iff G key u).1 hu).2 v hadj.symm h hv

/-- (b) The key-greedy set dominates every node with an incident edge. -/
theorem keyGreedy_dominates (G : SimpleGraph V) (key : V → K) {v : V} (hv : ∃ u, G.Adj u v) :
    keyGreedy G key v ∨ ∃ u, keyGreedy G key u ∧ G.Adj u v := by
  by_cases h : keyGreedy G key v
  · exact Or.inl h
  · right
    by_contra hno
    push Not at hno
    exact h ((keyGreedy_iff G key v).2 ⟨hv, fun u hadj _ hu => hno u hu hadj⟩)

omit [Finite V] in
/-- An isolated vertex outside an independent set shows that the set is not maximal. -/
theorem not_maximal_of_isolated (G : SimpleGraph V) {S : Set V} (hS : G.IsIndepSet S) {v : V}
    (hiso : ∀ u, ¬ G.Adj u v) (hv : v ∉ S) : ¬ Maximal G.IsIndepSet S := by
  intro hmax
  have hind : G.IsIndepSet (insert v S) := by
    exact hS.insert fun u _ _ => ⟨fun h => hiso u h.symm, hiso u⟩
  exact hv (hmax.2 hind (Set.subset_insert v S) (Set.mem_insert v S))

/-- Counterexample to `lem:backbone` as written, on a connected graph: the one-node graph is
connected, its only node is isolated and becomes OUT, and the empty MIS set is not a maximal
independent set. -/
theorem lem_backbone_false_one_node :
    (⊥ : SimpleGraph (Fin 1)).Connected ∧
      ¬ Maximal (⊥ : SimpleGraph (Fin 1)).IsIndepSet
        {v | keyGreedy (⊥ : SimpleGraph (Fin 1)) (fun i : Fin 1 => (i : ℕ)) v} := by
  refine ⟨?_, ?_⟩
  · exact (connected_iff_exists_forall_reachable _).2 ⟨0, fun v => by
      rw [Subsingleton.elim v 0]⟩
  · refine not_maximal_of_isolated _ (keyGreedy_isIndepSet _ Fin.val_injective)
      (v := 0) (fun u h => h) ?_
    intro h
    obtain ⟨u, hu⟩ := ((keyGreedy_iff _ _ 0).1 h).1
    exact hu

/-- Counterexample to `lem:backbone` read component by component (line 41 of the source: "a
disconnected Ĝ* splits the statements by component"): one edge `0 — 1` and an isolated node `2`.
Node `2` becomes OUT, so the MIS set misses it and is not maximal. -/
theorem lem_backbone_false_isolated :
    ¬ Maximal (fromEdgeSet {s(0, 1)} : SimpleGraph (Fin 3)).IsIndepSet
        {v | keyGreedy (fromEdgeSet {s(0, 1)} : SimpleGraph (Fin 3)) (fun i : Fin 3 => (i : ℕ)) v} := by
  have hiso : ∀ u, ¬ (fromEdgeSet {s(0, 1)} : SimpleGraph (Fin 3)).Adj u 2 := by
    intro u
    fin_cases u <;> simp
  refine not_maximal_of_isolated _ (keyGreedy_isIndepSet _ Fin.val_injective) hiso ?_
  intro h
  exact hiso _ ((keyGreedy_iff _ _ 2).1 h).1.choose_spec

/-- (c) Repaired statement, general graph. The key-greedy set together with the isolated
vertices is a maximal independent set.

Source: `lem:backbone` (see the module docstring).

Modelling choices:
* the graph Ĝ* is a `SimpleGraph` on a finite type,
* the priority key is an injective map into a linear order (Definition `def:key`),
* the MIS set after Phase 1a is the key-greedy set `keyGreedy G key` (protocol part not
  formalized).

Added hypotheses: none. The conclusion is changed: the isolated vertices are added, because
without them the statement is false (`lem_backbone_false_one_node`,
`lem_backbone_false_isolated`). -/
theorem keyGreedy_union_isolated_maximal (G : SimpleGraph V) {key : V → K}
    (hkey : Function.Injective key) :
    Maximal G.IsIndepSet ({v | keyGreedy G key v} ∪ {v | ∀ u, ¬ G.Adj u v}) := by
  refine ⟨?_, ?_⟩
  · intro u hu v hv huv hadj
    rcases hu with hu | hu
    · rcases hv with hv | hv
      · exact keyGreedy_isIndepSet G hkey hu hv huv hadj
      · exact hv u hadj
    · exact hu v hadj.symm
  · intro T hT hsub v hv
    by_contra hnot
    simp only [Set.mem_union, Set.mem_ofPred_eq, not_or] at hnot
    obtain ⟨hns, hni⟩ := hnot
    push Not at hni
    rcases keyGreedy_dominates G key hni with h | ⟨u, hu, hadj⟩
    · exact hns h
    · have huT : u ∈ T := hsub (Or.inl hu)
      have huv : u ≠ v := hadj.ne
      exact hT huT hv huv hadj

omit [Finite V] in
/-- In a connected graph with at least two vertices no vertex is isolated. -/
theorem exists_adj_of_connected [Fintype V] {G : SimpleGraph V} (hG : G.Connected)
    (hcard : 2 ≤ Fintype.card V) (v : V) : ∃ u, G.Adj u v := by
  obtain ⟨w, hw⟩ : ∃ w, w ≠ v := by
    by_contra h
    push Not at h
    have : Fintype.card V ≤ 1 := Fintype.card_le_one_iff.2 fun a b => (h a).trans (h b).symm
    omega
  obtain ⟨p⟩ := hG.preconnected w v
  cases p with
  | nil => exact absurd rfl hw
  | cons h p =>
    rename_i x
    clear hw
    induction p generalizing w with
    | nil => exact ⟨w, h⟩
    | cons h' p ih => exact ih _ h'

/-- (d) Repaired statement, the reading of the source for a connected Ĝ* with `n ≥ 2`: the
key-greedy set is a maximal independent set and dominates every node.

Source: `lem:backbone` (see the module docstring).

Modelling choices: as in `keyGreedy_union_isolated_maximal`.

Added hypotheses:
* `G.Connected`: on a graph with an isolated vertex the statement is false
  (`lem_backbone_false_isolated`),
* `2 ≤ Fintype.card V`: the one-node graph is connected and the statement fails there
  (`lem_backbone_false_one_node`). -/
theorem keyGreedy_maximal_of_connected [Fintype V] (G : SimpleGraph V) {key : V → K}
    (hkey : Function.Injective key) (hG : G.Connected) (hcard : 2 ≤ Fintype.card V) :
    Maximal G.IsIndepSet {v | keyGreedy G key v} := by
  have hiso : {v | ∀ u, ¬ G.Adj u v} = (∅ : Set V) := by
    ext v
    simp only [Set.mem_ofPred_eq, Set.mem_empty_iff_false, iff_false, not_forall, not_not]
    exact exists_adj_of_connected hG hcard v
  simpa [hiso] using keyGreedy_union_isolated_maximal G hkey

omit [Finite V] in
/-- A maximal independent set dominates every vertex. -/
theorem Maximal.dominates {G : SimpleGraph V} {S : Set V} (hS : Maximal G.IsIndepSet S) (v : V) :
    v ∈ S ∨ ∃ a ∈ S, G.Adj a v := by
  by_contra h
  push Not at h
  have hind : G.IsIndepSet (insert v S) :=
    hS.1.insert fun u hu _ => ⟨fun hadj => h.2 u hu hadj.symm, h.2 u hu⟩
  exact h.1 (hS.2 hind (Set.subset_insert v S) (Set.mem_insert v S))

/-- Example: the hypotheses of (d) hold together, on the path `0 — 1 — 2`. -/
example : (pathGraph 3).Connected ∧ 2 ≤ Fintype.card (Fin 3) :=
  ⟨connected_pathGraph.2 (by norm_num), by simp⟩

end SwarmInfer.CoverWeave

#print axioms SwarmInfer.CoverWeave.keyGreedy_isIndepSet
#print axioms SwarmInfer.CoverWeave.keyGreedy_dominates
#print axioms SwarmInfer.CoverWeave.lem_backbone_false_one_node
#print axioms SwarmInfer.CoverWeave.lem_backbone_false_isolated
#print axioms SwarmInfer.CoverWeave.keyGreedy_union_isolated_maximal
#print axioms SwarmInfer.CoverWeave.keyGreedy_maximal_of_connected
