import SwarmInferLean.CoverWeave.Basic
import SwarmInferLean.CoverWeave.SearchRuntime

/-!
# CoverWeave: a valid pair is checked in `O(n + m)` steps (inventory C1, part 1)

Source: CoverWeave R1 manuscript, `sections/04-formaleng.tex:20`, proof of Theorem `thm:hardness`:
"For rational weights a valid pair is checked in `O(n+m)` time, so the decision version lies in
NP." This file gives a checker that returns `true` exactly on valid pairs (Definition
`def:mwccvc`, `ValidPair` of `Basic.lean`) and proves the bound `steps ≤ 3 (n + m)`.

Input model (adjacency lists). `AdjRep G` holds, for every node `x`, the list of its incident
edges with their other endpoints, and the list of all edges, each once; `AdjRep.ofGraph` shows
that every finite graph has one. The owner map is an array indexed by edges, `C` a bit array
indexed by nodes.

Cost model (one step each):
* edge phase: reading one edge `e`, which tests `owner e ∈ e` and `owner e ∈ C` and adds one to
  the counter of `owner e`,
* load phase: reading one node `v ∈ C`, which tests `counter v ≤ k`,
* connectivity phase: the search of `SearchRuntime.lean` in `G[C]` from the first node of `C`
  (one step per node popped, one per incident edge read, `deg x + 1` per node), then reading one
  node `v ∈ C` to test that it was visited.
The weight `w` does not enter validity, so "rational weights" plays no role in the check (it
matters only for the size of the NP certificate, which stays on paper).
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {V : Type*} [Fintype V] [DecidableEq V]

/-- Adjacency-list representation of `G`: incident edges with their other endpoint at every
node, and the list of all edges, each once. -/
structure AdjRep (G : SimpleGraph V) where
  inc : V → List (G.edgeSet × V)
  mem_inc : ∀ x e y, (e, y) ∈ inc x ↔ G.Adj x y ∧ (e : Sym2 V) = s(x, y)
  inc_nodup : ∀ x, (inc x).Nodup
  edges : List G.edgeSet
  edges_nodup : edges.Nodup
  mem_edges : ∀ e, e ∈ edges

variable {G : SimpleGraph V} [DecidableRel G.Adj]

/-- Every finite graph has an adjacency-list representation, so the input model is not vacuous. -/
noncomputable def AdjRep.ofGraph (G : SimpleGraph V) [DecidableRel G.Adj] : AdjRep G where
  inc x := ((univ : Finset (G.edgeSet × V)).filter
    fun p => G.Adj x p.2 ∧ (p.1 : Sym2 V) = s(x, p.2)).toList
  mem_inc x e y := by simp
  inc_nodup _ := nodup_toList _
  edges := (univ : Finset G.edgeSet).toList
  edges_nodup := nodup_toList _
  mem_edges e := by simp

/-- The incidence list of `x` has `deg x` entries. -/
theorem AdjRep.inc_length (R : AdjRep G) (x : V) : (R.inc x).length = G.degree x := by
  classical
  rw [← SimpleGraph.card_neighborFinset_eq_degree, ← List.toFinset_card_of_nodup (R.inc_nodup x)]
  refine card_bij (fun p _ => p.2) ?_ ?_ ?_
  · rintro ⟨e, y⟩ hp
    rw [List.mem_toFinset, R.mem_inc] at hp
    exact (SimpleGraph.mem_neighborFinset _ _ _).mpr hp.1
  · rintro ⟨e, y⟩ hp ⟨e', y'⟩ hp' (rfl : y = y')
    rw [List.mem_toFinset, R.mem_inc] at hp hp'
    have : e = e' := Subtype.ext (hp.2.trans hp'.2.symm)
    rw [this]
  · intro y hy
    rw [SimpleGraph.mem_neighborFinset] at hy
    exact ⟨(⟨s(x, y), (SimpleGraph.mem_edgeSet G).mpr hy⟩, y),
      by rw [List.mem_toFinset, R.mem_inc]; exact ⟨hy, rfl⟩, rfl⟩

omit [Fintype V] [DecidableRel G.Adj] in
/-- The edge list has `m` entries. -/
theorem AdjRep.edges_length (R : AdjRep G) [Fintype G.edgeSet] :
    R.edges.length = Fintype.card G.edgeSet := by
  rw [← List.toFinset_card_of_nodup R.edges_nodup, ← card_univ]
  congr 1
  ext e; simp [R.mem_edges e]

/-! ### Edge phase -/

/-- One step per edge: test `owner e ∈ e ∧ owner e ∈ C` and count `e` at `owner e`. -/
def edgePhase (C : Finset V) (owner : G.edgeSet → V) :
    List G.edgeSet → Bool × (V → ℕ) × ℕ → Bool × (V → ℕ) × ℕ
  | [], st => st
  | e :: es, (b, cnt, c) =>
    edgePhase C owner es (b && decide (owner e ∈ (e : Sym2 V) ∧ owner e ∈ C),
      Function.update cnt (owner e) (cnt (owner e) + 1), c + 1)

omit [Fintype V] [DecidableRel G.Adj] in
theorem edgePhase_spec (C : Finset V) (owner : G.edgeSet → V) :
    ∀ (l : List G.edgeSet) (b : Bool) (cnt : V → ℕ) (c : ℕ),
      ((edgePhase C owner l (b, cnt, c)).1 = true ↔
        b = true ∧ ∀ e ∈ l, owner e ∈ (e : Sym2 V) ∧ owner e ∈ C) ∧
      (∀ v, (edgePhase C owner l (b, cnt, c)).2.1 v = cnt v + l.countP (owner · = v)) ∧
      (edgePhase C owner l (b, cnt, c)).2.2 = c + l.length
  | [], b, cnt, c => by simp [edgePhase]
  | e :: es, b, cnt, c => by
    obtain ⟨h1, h2, h3⟩ := edgePhase_spec C owner es
      (b && decide (owner e ∈ (e : Sym2 V) ∧ owner e ∈ C))
      (Function.update cnt (owner e) (cnt (owner e) + 1)) (c + 1)
    refine ⟨?_, fun v => ?_, ?_⟩
    · rw [edgePhase, h1]; simp [and_assoc]
    · rw [edgePhase, h2, List.countP_cons, Function.update_apply]
      by_cases h : v = owner e
      · subst h; simp; omega
      · simp [h, Ne.symm h]
    · rw [edgePhase, h3, List.length_cons]; omega

/-- Counting over the edge list is the load. -/
theorem AdjRep.countP_eq_load (R : AdjRep G) (owner : G.edgeSet → V) (v : V) :
    R.edges.countP (owner · = v) = load G owner v := by
  classical
  rw [List.countP_eq_length_filter, load,
    ← List.toFinset_card_of_nodup (R.edges_nodup.filter _), List.toFinset_filter]
  congr 1
  ext e; simp [R.mem_edges e]

/-! ### Connectivity phase -/

/-- The arcs followed by the search in `G[C]`. -/
abbrev inC (C : Finset V) : V → G.edgeSet → V → Prop := fun _ _ y => y ∈ C

omit [Fintype V] [DecidableEq V] [DecidableRel G.Adj] in
theorem arc_inC_iff (R : AdjRep G) (C : Finset V) (x y : V) :
    Search.Arc R.inc (inC (G := G) C) x y ↔ G.Adj x y ∧ y ∈ C := by
  constructor
  · rintro ⟨e, hmem, hy⟩
    exact ⟨((R.mem_inc x e y).mp hmem).1, hy⟩
  · rintro ⟨h, hy⟩
    exact ⟨⟨s(x, y), (SimpleGraph.mem_edgeSet G).mpr h⟩, (R.mem_inc _ _ _).mpr ⟨h, rfl⟩, hy⟩

omit [Fintype V] [DecidableEq V] [DecidableRel G.Adj] in
theorem rtg_of_walk (R : AdjRep G) (C : Finset V) {a b : (C : Set V)}
    (p : (G.induce (C : Set V)).Walk a b) :
    Relation.ReflTransGen (Search.Arc R.inc (inC (G := G) C)) a.1 b.1 := by
  induction p with
  | nil => exact .refl
  | cons h _ ih =>
    exact Relation.ReflTransGen.head ((arc_inC_iff R C _ _).mpr ⟨h, Subtype.mem _⟩) ih

omit [Fintype V] [DecidableEq V] [DecidableRel G.Adj] in
theorem reachable_of_rtg (R : AdjRep G) (C : Finset V) {s : V} (hs : s ∈ C) {y : V}
    (h : Relation.ReflTransGen (Search.Arc R.inc (inC (G := G) C)) s y) :
    ∃ hy : y ∈ C, (G.induce (C : Set V)).Reachable ⟨s, hs⟩ ⟨y, hy⟩ := by
  induction h with
  | refl => exact ⟨hs, .refl _⟩
  | tail _ hbc ih =>
    obtain ⟨hb, hr⟩ := ih
    obtain ⟨hadj, hc⟩ := (arc_inC_iff R C _ _).mp hbc
    exact ⟨hc, hr.trans (SimpleGraph.Adj.reachable (G := G.induce (C : Set V))
      (u := ⟨_, hb⟩) (v := ⟨_, hc⟩) hadj)⟩

omit [Fintype V] [DecidableEq V] [DecidableRel G.Adj] in
/-- `G[C]` is connected iff every node of `C` is reached from one node `s ∈ C`. -/
theorem connected_iff_rtg (R : AdjRep G) (C : Finset V) {s : V} (hs : s ∈ C) :
    (G.induce (C : Set V)).Connected ↔
      ∀ v ∈ C, Relation.ReflTransGen (Search.Arc R.inc (inC (G := G) C)) s v := by
  constructor
  · intro hc v hv
    obtain ⟨p⟩ := hc.preconnected ⟨s, hs⟩ ⟨v, hv⟩
    exact rtg_of_walk R C p
  · intro h
    rw [SimpleGraph.connected_iff]
    refine ⟨fun a b => ?_, ⟨⟨s, hs⟩⟩⟩
    obtain ⟨_, ha⟩ := reachable_of_rtg R C hs (h a.1 a.2)
    obtain ⟨_, hb⟩ := reachable_of_rtg R C hs (h b.1 b.2)
    exact ha.symm.trans hb

/-- Search `G[C]` from the first node of `C`, then read every node of `C` to test that it was
visited. Returns the answer and the step count. -/
noncomputable def connPhase (R : AdjRep G) (C : Finset V) : Bool × ℕ :=
  match C.toList with
  | [] => (false, 0)
  | s :: _ =>
    ((C.toList.all fun v => decide (v ∈ (Search.search R.inc (inC (G := G) C) {s}).vis)),
      (Search.search R.inc (inC (G := G) C) {s}).cnt + #C)

theorem connPhase_spec (R : AdjRep G) (C : Finset V) :
    ((connPhase R C).1 = true ↔ (G.induce (C : Set V)).Connected) ∧
      (connPhase R C).2 ≤ 2 * #G.edgeFinset + Fintype.card V + #C := by
  rcases hC : C.toList with _ | ⟨s, rest⟩
  · have hC' : C = ∅ := toList_eq_nil.mp hC
    simp only [connPhase, hC]
    refine ⟨⟨fun h => absurd h (by simp), fun hc => ?_⟩, Nat.zero_le _⟩
    obtain ⟨⟨v, hv⟩⟩ := hc.nonempty
    simp [hC'] at hv
  · have hs : s ∈ C := by rw [← mem_toList, hC]; exact List.mem_cons_self ..
    simp only [connPhase, hC]
    constructor
    · rw [← hC, List.all_eq_true, connected_iff_rtg R C hs]
      refine forall_congr' fun v => ?_
      rw [mem_toList, decide_eq_true_iff, Search.search_mem_iff]
      simp
    · have h1 := Search.search_cnt_le (succ := R.inc) (ok := inC (G := G) C) {s}
      have h2 : ∑ x, ((R.inc x).length + 1) = 2 * #G.edgeFinset + Fintype.card V := by
        simp [R.inc_length, sum_add_distrib, SimpleGraph.sum_degrees_eq_twice_card_edges G]
      omega

/-! ### The checker -/

/-- **The valid-pair checker.** Edge phase, load phase, connectivity phase; returns the answer and
the step count of the cost model in the module docstring. -/
noncomputable def checkValid (R : AdjRep G) (k : ℕ) (C : Finset V) (owner : G.edgeSet → V) :
    Bool × ℕ :=
  ((edgePhase C owner R.edges (true, fun _ => 0, 0)).1 &&
      (C.toList.all fun v => decide ((edgePhase C owner R.edges (true, fun _ => 0, 0)).2.1 v ≤ k))
      && (connPhase R C).1,
    (edgePhase C owner R.edges (true, fun _ => 0, 0)).2.2 + #C + (connPhase R C).2)

/-- **Theorem (Hardness), proof, first sentence: the checker is correct** (C1 part 1). The checker
returns `true` exactly on valid pairs.

Modelling choices:
* the graph is given by an adjacency-list representation `R : AdjRep G` (exists for every
  graph, `AdjRep.ofGraph`), `C` as a `Finset`, `owner` as a function on the edge subtype,
* condition 1 of `def:mwccvc` (cover) is not tested separately: it follows from condition 3
  (`IsOwnerMap.isVertexCover`),
* connectivity of `G` itself is not assumed (it is not needed for the check).
Added hypotheses: none. -/
theorem checkValid_correct (R : AdjRep G) (k : ℕ) (C : Finset V) (owner : G.edgeSet → V) :
    (checkValid R k C owner).1 = true ↔ ValidPair G k C owner := by
  obtain ⟨h1, h2, -⟩ := edgePhase_spec C owner R.edges true (fun _ => 0) 0
  rw [checkValid, Bool.and_eq_true, Bool.and_eq_true, h1, (connPhase_spec R C).1,
    List.all_eq_true]
  simp only [h2, zero_add, R.countP_eq_load, mem_toList, decide_eq_true_iff, true_and]
  constructor
  · rintro ⟨⟨hend, hload⟩, hconn⟩
    have hown : IsOwnerMap G k C owner := ⟨fun e => hend e (R.mem_edges e), hload⟩
    exact ⟨⟨hown.isVertexCover, hconn⟩, hown⟩
  · rintro ⟨⟨-, hconn⟩, hend, hload⟩
    exact ⟨⟨fun e _ => hend e, hload⟩, hconn⟩

/-- **Theorem (Hardness), proof, first sentence: the `O(n + m)` bound** (C1 part 1). The checker
takes at most `3 (n + m)` steps. -/
theorem checkValid_steps_le (R : AdjRep G) (k : ℕ) (C : Finset V) (owner : G.edgeSet → V) :
    (checkValid R k C owner).2 ≤ 3 * (Fintype.card V + #G.edgeFinset) := by
  obtain ⟨-, -, h3⟩ := edgePhase_spec C owner R.edges true (fun _ => 0) 0
  have h4 := (connPhase_spec R C).2
  have h5 : #C ≤ Fintype.card V := card_le_univ C
  have h6 : R.edges.length = #G.edgeFinset := by
    rw [R.edges_length, SimpleGraph.edgeFinset_card]
  simp only [checkValid, h3, h6]
  omega

end SwarmInfer.CoverWeave

#print axioms SwarmInfer.CoverWeave.checkValid_correct
#print axioms SwarmInfer.CoverWeave.checkValid_steps_le
