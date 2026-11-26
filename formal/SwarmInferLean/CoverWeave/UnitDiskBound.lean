import SwarmInferLean.CoverWeave.Basic
import SwarmInferLean.CoverWeave.UnitDisk

/-!
# CoverWeave: the unit disk bound of `prop:approx` (inventory C13 part 2)

`prop:approx` (`04-formaleng.tex:190`), second half: for `w ≡ 1`, a connected `G` with `n ≥ 2`
and `OPT` the minimum size of a valid pair, every valid pair satisfies `|C| ≤ 6·OPT` on a unit
disk graph.

* `card_le_six_mul_of_isVertexCover` is the combinatorial core, conditional on the five-neighbor
  bound C13a given as a hypothesis `hfive`: every vertex cover `T` has `n ≤ 6|T|`.
* `card_le_six_mul_opt` is part 2 with `hfive` as hypothesis (conditional form).
* `card_le_six_mul_opt_of_isUnitDiskGraph` (and the `…Lt` variant for the strict convention)
  discharges `hfive` with C13a from `UnitDisk.lean`, so it is unconditional.
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {V : Type*} [Fintype V] [DecidableEq V] {G : SimpleGraph V} [DecidableRel G.Adj]

/-- The five-neighbor property of C13a as a predicate on graphs. -/
def FiveIndependentNeighbors (G : SimpleGraph V) [DecidableRel G.Adj] : Prop :=
  ∀ v (I : Finset V), I ⊆ G.neighborFinset v →
    (I : Set V).Pairwise (fun a b => ¬ G.Adj a b) → #I ≤ 5

/-- Combinatorial core of C13 part 2 (paper's proof): on a connected graph with `n ≥ 2` in which
every node has at most five pairwise nonadjacent neighbors, every vertex cover `T` satisfies
`n ≤ 6|T|`. Each node outside `T` has a neighbor, which lies in `T`; the nodes sent to one
`t ∈ T` are pairwise nonadjacent neighbors of `t`, hence at most five. -/
theorem card_le_six_mul_of_isVertexCover (hG : G.Connected) (hn : 2 ≤ Fintype.card V)
    (hfive : FiveIndependentNeighbors G) {T : Finset V} (hT : IsVertexCover G T) :
    Fintype.card V ≤ 6 * #T := by
  have hex : ∀ u ∈ univ \ T, ∃ t, G.Adj u t ∧ t ∈ T := by
    intro u hu
    have huT : u ∉ T := (mem_sdiff.mp hu).2
    obtain ⟨w, hw⟩ := Fintype.exists_ne_of_one_lt_card (by omega) u
    obtain ⟨t, ht⟩ := (hG.preconnected u w).nonempty_neighborSet_left hw.symm
    exact ⟨t, ht, (hT ht).resolve_left huT⟩
  choose! f hfadj hfT using hex
  have hout : #(univ \ T) ≤ 5 * #((univ \ T).image f) := by
    refine card_le_mul_card_image _ 5 (fun t _ => hfive t _ ?_ ?_)
    · intro x hx
      obtain ⟨hx', rfl⟩ := mem_filter.mp hx
      exact (G.mem_neighborFinset _ x).mpr (hfadj x hx').symm
    · intro x hx y hy _ hxy
      have hxT := (mem_sdiff.mp (mem_filter.mp hx).1).2
      have hyT := (mem_sdiff.mp (mem_filter.mp hy).1).2
      rcases hT hxy with h | h
      · exact hxT h
      · exact hyT h
  have himg : #((univ \ T).image f) ≤ #T := card_le_card fun t ht => by
    obtain ⟨u, hu, rfl⟩ := mem_image.mp ht
    exact hfT u hu
  have hsplit := card_sdiff_add_card_inter univ T
  rw [univ_inter, card_univ] at hsplit
  omega

/-- **Proposition (Simple bounds)**, part 2, `prop:approx`, inventory C13, **conditional on
C13a**, which enters as the hypothesis `hfive`. For `w ≡ 1`, a connected `G` with `n ≥ 2` and
`OPT` the minimum size of a valid pair, every valid pair satisfies `|C| ≤ 6·OPT`.

Modelling choices:
* As in part 1 (`card_le_mul_opt_add_one`): `w ≡ 1`, so `OPT` is a natural number attained by a
  valid pair, with no valid pair smaller.
* The paper's minimum vertex cover `T` is replaced by the optimal cover `C₀` itself, which is a
  vertex cover; this is the paper's chain `n ≤ 6|T| ≤ 6·OPT` with the middle step skipped.

Minimality of `OPT` and the validity of `C` are not used (`|C| ≤ n` holds for every set);
`n ≥ 2` and connectivity of `G` are used to give every node outside the cover a neighbor. -/
theorem card_le_six_mul_opt (hG : G.Connected) (hn : 2 ≤ Fintype.card V)
    (hfive : FiveIndependentNeighbors G) {k OPT : ℕ}
    (hOPT : ∃ C₀ owner₀, ValidPair G k C₀ owner₀ ∧ #C₀ = OPT)
    (_hmin : ∀ C owner, ValidPair G k C owner → OPT ≤ #C)
    {C : Finset V} {owner : G.edgeSet → V} (_h : ValidPair G k C owner) :
    #C ≤ 6 * OPT := by
  obtain ⟨C₀, owner₀, h₀, rfl⟩ := hOPT
  exact (card_le_univ C).trans (card_le_six_mul_of_isVertexCover hG hn hfive h₀.1.1)

/-- **Proposition (Simple bounds)**, part 2, `prop:approx`, inventory C13, unconditional: on a
unit disk graph (E6, adjacency at distance `≤ 1`) every valid pair satisfies `|C| ≤ 6·OPT`.
Modelling choices as in `card_le_six_mul_opt` and `card_le_five_of_isUnitDiskGraph`. -/
theorem card_le_six_mul_opt_of_isUnitDiskGraph (hG : G.Connected) (hn : 2 ≤ Fintype.card V)
    {p : V → EuclideanSpace ℝ (Fin 2)} (hud : IsUnitDiskGraph G p) {k OPT : ℕ}
    (hOPT : ∃ C₀ owner₀, ValidPair G k C₀ owner₀ ∧ #C₀ = OPT)
    (hmin : ∀ C owner, ValidPair G k C owner → OPT ≤ #C)
    {C : Finset V} {owner : G.edgeSet → V} (h : ValidPair G k C owner) :
    #C ≤ 6 * OPT :=
  card_le_six_mul_opt hG hn (card_le_five_of_isUnitDiskGraph hud) hOPT hmin h

/-- C13 part 2 for the strict convention (adjacency at distance `< 1`). -/
theorem card_le_six_mul_opt_of_isUnitDiskGraphLt (hG : G.Connected) (hn : 2 ≤ Fintype.card V)
    {p : V → EuclideanSpace ℝ (Fin 2)} (hud : IsUnitDiskGraphLt G p) {k OPT : ℕ}
    (hOPT : ∃ C₀ owner₀, ValidPair G k C₀ owner₀ ∧ #C₀ = OPT)
    (hmin : ∀ C owner, ValidPair G k C owner → OPT ≤ #C)
    {C : Finset V} {owner : G.edgeSet → V} (h : ValidPair G k C owner) :
    #C ≤ 6 * OPT :=
  card_le_six_mul_opt hG hn (card_le_five_of_isUnitDiskGraphLt hud) hOPT hmin h

#print axioms card_le_six_mul_of_isVertexCover
#print axioms card_le_six_mul_opt
#print axioms card_le_six_mul_opt_of_isUnitDiskGraph
#print axioms card_le_six_mul_opt_of_isUnitDiskGraphLt

/-- The hypotheses of `card_le_six_mul_opt_of_isUnitDiskGraph` hold together: the path `0 — 1`
is the unit disk graph of the points `(0,0)` and `(1,0)`, and `({0}, ·)` is a valid pair with
`k = 1`. -/
example : IsUnitDiskGraph (SimpleGraph.pathGraph 2) ![!₂[0, 0], !₂[1, 0]] ∧
    ∃ C₀ owner₀, ValidPair (SimpleGraph.pathGraph 2) 1 C₀ owner₀ ∧ #C₀ = 1 := by
  refine ⟨fun u v => ?_, {0}, fun _ => 0, ⟨⟨?_, ?_⟩, ?_, ?_⟩, rfl⟩
  · rw [EuclideanSpace.dist_eq, Fin.sum_univ_two]
    fin_cases u <;> fin_cases v <;> simp [SimpleGraph.pathGraph_adj]
  · intro u v huv
    fin_cases u <;> fin_cases v <;> simp_all [SimpleGraph.pathGraph_adj]
  · rw [SimpleGraph.connected_iff]
    refine ⟨fun a b => ?_, ⟨⟨0, by simp⟩⟩⟩
    have : a = b := Subtype.ext (by have := a.2; have := b.2; simp_all)
    rw [this]
  · rintro ⟨e, he⟩
    induction e using Sym2.ind with
    | h u v =>
      fin_cases u <;> fin_cases v <;> simp at he ⊢
  · intro v hv
    rw [mem_singleton] at hv
    subst hv
    decide

end SwarmInfer.CoverWeave
