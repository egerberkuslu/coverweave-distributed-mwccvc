import SwarmInferLean.CoverWeave.Ownership

/-!
# CoverWeave: strict scope of the degree-gap witness (inventory C7)

Corollary `cor:witness` (`04-formaleng.tex:99`): infeasibility by the counting bound `m > nk` is
strictly contained in infeasibility by the degree-gap witness `∑_v min(deg v, k) < m`, which is
strictly contained in infeasibility. The two strictness instances of the proof are built here
as concrete graphs and checked by `decide`.
-/

namespace SwarmInfer.CoverWeave

open Finset

/-- The counting bound implies the degree-gap witness, on every finite graph. -/
theorem sum_min_lt_of_card_mul_lt {V : Type*} [Fintype V] {G : SimpleGraph V}
    [DecidableRel G.Adj] {k : ℕ} (h : Fintype.card V * k < #G.edgeFinset) :
    ∑ v, min (G.degree v) k < #G.edgeFinset :=
  (sum_min_degree_le k).trans_lt h

/-! ### First instance: `K₆` minus `(1,2)` and `(4,5)`, plus node 7 pendant to node 4

Paper nodes `1, …, 7` are `0, …, 6` here, so the removed edges are `(0,1)`, `(3,4)` and the
pendant edge is `(3,6)`. -/

/-- Adjacency of the first instance as a Boolean function. -/
def g7Adj (i j : Fin 7) : Bool :=
  i != j &&
    ((i.val < 6 && j.val < 6 && !(min i.val j.val == 0 && max i.val j.val == 1) &&
        !(min i.val j.val == 3 && max i.val j.val == 4)) ||
      (min i.val j.val == 3 && max i.val j.val == 6))

/-- First instance of `cor:witness`: `n = 7`, `m = 14`, degrees `5,5,5,4,4,4,1`. -/
def G7 : SimpleGraph (Fin 7) where
  Adj i j := g7Adj i j = true
  symm := ⟨by decide⟩
  loopless := ⟨by decide⟩

instance : DecidableRel G7.Adj := fun i j => inferInstanceAs (Decidable (g7Adj i j = true))

theorem G7_connected : G7.Connected := by
  rw [SimpleGraph.connected_iff_exists_forall_reachable]
  refine ⟨2, fun w => ?_⟩
  fin_cases w
  case «2» => exact SimpleGraph.Reachable.refl _
  case «6» =>
    exact (SimpleGraph.Adj.reachable (show G7.Adj 2 3 by decide)).trans
      (SimpleGraph.Adj.reachable (show G7.Adj 3 6 by decide))
  all_goals exact SimpleGraph.Adj.reachable (by decide)

theorem G7_card_edgeFinset : #G7.edgeFinset = 14 := by decide

theorem G7_sum_min_degree : ∑ v, min (G7.degree v) 2 = 13 := by decide

/-! ### Second instance: `K₆` plus a path of four new nodes between two of its nodes

The path is `0 — 6 — 7 — 8 — 9 — 1`. -/

/-- Adjacency of the second instance as a Boolean function. -/
def g10Adj (i j : Fin 10) : Bool :=
  let a := min i.val j.val
  let b := max i.val j.val
  i != j &&
    ((b < 6) || (a == 0 && b == 6) || (a == 6 && b == 7) || (a == 7 && b == 8) ||
      (a == 8 && b == 9) || (a == 1 && b == 9))

/-- Second instance of `cor:witness`: `n = 10`, `m = 20`, every degree at least 2. -/
def G10 : SimpleGraph (Fin 10) where
  Adj i j := g10Adj i j = true
  symm := ⟨by decide⟩
  loopless := ⟨by decide⟩

instance : DecidableRel G10.Adj := fun i j => inferInstanceAs (Decidable (g10Adj i j = true))

theorem G10_connected : G10.Connected := by
  rw [SimpleGraph.connected_iff_exists_forall_reachable]
  refine ⟨0, fun w => ?_⟩
  fin_cases w
  case «0» => exact SimpleGraph.Reachable.refl _
  case «7» =>
    exact (SimpleGraph.Adj.reachable (show G10.Adj 0 6 by decide)).trans
      (SimpleGraph.Adj.reachable (show G10.Adj 6 7 by decide))
  case «8» =>
    exact ((SimpleGraph.Adj.reachable (show G10.Adj 0 1 by decide)).trans
      (SimpleGraph.Adj.reachable (show G10.Adj 1 9 by decide))).trans
      (SimpleGraph.Adj.reachable (show G10.Adj 9 8 by decide))
  case «9» =>
    exact (SimpleGraph.Adj.reachable (show G10.Adj 0 1 by decide)).trans
      (SimpleGraph.Adj.reachable (show G10.Adj 1 9 by decide))
  all_goals exact SimpleGraph.Adj.reachable (by decide)

theorem G10_card_edgeFinset : #G10.edgeFinset = 20 := by decide

theorem G10_sum_min_degree : ∑ v, min (G10.degree v) 2 = 20 := by decide

/-- The first six nodes span the 15 edges of `K₆`. -/
theorem G10_innerEdges : innerEdges G10 (univ.filter (fun i : Fin 10 => i.val < 6)) = 15 := by
  decide

/-- **Corollary (Scope of the witness)**, `cor:witness`, inventory C7. On connected graphs,
(1) the counting bound `m > nk` implies the degree-gap witness `∑_v min(deg v, k) < m`, and
the witness implies that no valid pair exists; (2) the first implication is strict: `G7` at
`k = 2` is connected, has `m = nk = 14` and witness sum 13; (3) the second is strict: `G10` at
`k = 2` is connected, has witness sum `20 = m`, and admits no valid pair because its first six
nodes span `15 > 12` edges.

Modelling choices:
* "Strictly contained" is stated as the two implications plus one connected instance in each
  difference, which is what the proof shows.
* The instances are the paper's, with nodes renumbered from 0; the path of the second instance
  joins nodes 0 and 1 (the paper does not say which two nodes).
* Not formalized: the claim inside the proof that no connected instance with `n ≤ 6` lies in
  the first difference (an exhaustive search, not part of the statement). -/
theorem witness_scope :
    (∀ {V : Type} [Fintype V] [DecidableEq V] (G : SimpleGraph V) [DecidableRel G.Adj] (k : ℕ),
        (Fintype.card V * k < #G.edgeFinset → ∑ v, min (G.degree v) k < #G.edgeFinset) ∧
        (∑ v, min (G.degree v) k < #G.edgeFinset → ¬ ∃ C owner, ValidPair G k C owner)) ∧
    (G7.Connected ∧ ¬ Fintype.card (Fin 7) * 2 < #G7.edgeFinset ∧
        ∑ v, min (G7.degree v) 2 < #G7.edgeFinset) ∧
    (G10.Connected ∧ ¬ ∑ v, min (G10.degree v) 2 < #G10.edgeFinset ∧
        ¬ ∃ C owner, ValidPair G10 2 C owner) := by
  refine ⟨fun G _ k => ⟨sum_min_lt_of_card_mul_lt, not_exists_validPair_of_sum_min_lt⟩,
    ⟨G7_connected, ?_, ?_⟩, ⟨G10_connected, ?_, ?_⟩⟩
  · rw [G7_card_edgeFinset, Fintype.card_fin]; omega
  · rw [G7_card_edgeFinset, G7_sum_min_degree]; omega
  · rw [G10_card_edgeFinset, G10_sum_min_degree]; omega
  · rintro ⟨C, owner, h⟩
    have := h.2.innerEdges_le (univ.filter (fun i : Fin 10 => i.val < 6))
    rw [G10_innerEdges] at this
    have hc : #(univ.filter (fun i : Fin 10 => i.val < 6)) = 6 := by decide
    omega

#print axioms witness_scope

end SwarmInfer.CoverWeave
