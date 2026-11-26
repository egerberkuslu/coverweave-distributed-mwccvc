import SwarmInferLean.CoverWeave.Basic

/-!
# CoverWeave: lower bound and the first simple bound (inventory C6, C13 part 1)

* C6, `prop:lb` (`04-formaleng.tex:91`): every valid pair satisfies `|C| ≥ ⌈m/k⌉`.
* C13 part 1, `prop:approx` (`04-formaleng.tex:190`): for `w ≡ 1`, connected `G` with `n ≥ 2`
  and `OPT` the minimum size of a valid pair, every valid pair satisfies `|C| ≤ k·OPT + 1`.
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {V : Type*} [Fintype V] [DecidableEq V] {G : SimpleGraph V} [DecidableRel G.Adj]

/-- Counting core shared by C6, C1(4) and C5(a): under an owner map with capacity `k`, any set
`F` of edges has at most `k` times as many elements as the set of its owners. -/
theorem IsOwnerMap.card_le_mul_card_image {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : IsOwnerMap G k C owner) (F : Finset G.edgeSet) : #F ≤ k * #(F.image owner) := by
  refine Finset.card_le_mul_card_image F k (fun v _ => le_trans ?_ (h.load_le v))
  exact card_le_card (filter_subset_filter _ (subset_univ F))

/-- `m ≤ k |C|` for every owner map, the integral form of C6. -/
theorem IsOwnerMap.card_edgeFinset_le {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : IsOwnerMap G k C owner) : #G.edgeFinset ≤ k * #C := by
  rw [SimpleGraph.edgeFinset_card, ← card_univ]
  refine (h.card_le_mul_card_image univ).trans (Nat.mul_le_mul_left k (card_le_card ?_))
  intro v hv
  obtain ⟨e, -, rfl⟩ := mem_image.mp hv
  exact (h.1 e).2

/-- **Proposition (Lower bound)**, `prop:lb`, inventory C6. Every valid pair satisfies
`|C| ≥ ⌈m/k⌉`.

Modelling choices:
* `⌈m/k⌉` is `⌈(m : ℚ) / k⌉₊`. For `k = 0` the paper's ceiling is undefined; Lean's `m / 0 = 0`
  makes the statement trivially true there, and `no_ownerMap_of_capacity_zero` records what
  happens instead (no valid pair exists once there is an edge).
* The proof uses only conditions 3 and 4 (`IsOwnerMap`); the connectivity of `G` and of `G[C]`
  is not needed, as the inventory notes. -/
theorem lower_bound {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : ValidPair G k C owner) : ⌈(#G.edgeFinset : ℚ) / k⌉₊ ≤ #C := by
  have hm := h.2.card_edgeFinset_le
  rw [Nat.ceil_le]
  rcases Nat.eq_zero_or_pos k with rfl | hk
  · simp
  · rw [div_le_iff₀ (by exact_mod_cast hk), mul_comm]
    exact_mod_cast hm

/-- With capacity `0` no owner map exists as soon as `G` has an edge, so C6 is vacuous at
`k = 0` for every graph with an edge. -/
theorem no_ownerMap_of_capacity_zero (hm : 0 < #G.edgeFinset) (C : Finset V)
    (owner : G.edgeSet → V) : ¬ IsOwnerMap G 0 C owner := fun h => by
  have := h.card_edgeFinset_le
  omega

#print axioms lower_bound
#print axioms no_ownerMap_of_capacity_zero

/-- Core of C13 part 1 in the form the proof uses: on a connected graph, any `C` (not only a
valid one) has at most `k |C₀| + 1` nodes whenever `C₀` carries an owner map. -/
theorem card_le_mul_card_add_one (hG : G.Connected) {k : ℕ} (C : Finset V) {C₀ : Finset V}
    {owner₀ : G.edgeSet → V} (h₀ : IsOwnerMap G k C₀ owner₀) : #C ≤ k * #C₀ + 1 := by
  have hn := hG.card_vert_le_card_edgeSet_add_one
  rw [Nat.card_eq_fintype_card, Nat.card_eq_fintype_card, ← SimpleGraph.edgeFinset_card] at hn
  have := h₀.card_edgeFinset_le
  have := card_le_univ C
  omega

/-- **Proposition (Simple bounds)**, part 1, `prop:approx`, inventory C13. For `w ≡ 1`, a
connected `G` with `n ≥ 2` and `OPT` the minimum size of a valid pair, every valid pair satisfies
`|C| ≤ k·OPT + 1`.

Modelling choices:
* `w ≡ 1` makes the weight of `C` its size, so `OPT` is given as a natural number together with a
  valid pair of that size and the statement that no valid pair is smaller.
* The proof is that of the paper: C6 and `m ≥ n − 1` give `k·OPT ≥ n − 1 ≥ |C| − 1`.

The hypotheses `2 ≤ Fintype.card V` and minimality of `OPT` are stated as in the paper but are
not used: `card_le_mul_card_add_one` shows the bound for every set `C` and the size of every
valid pair in place of `OPT`. The source's implicit `k ≥ 1` is not needed either (for `k = 0`
there is no valid pair on a graph with an edge, and on a graph without edges `n = 1`). -/
theorem card_le_mul_opt_add_one (hG : G.Connected) (_hn : 2 ≤ Fintype.card V) {k OPT : ℕ}
    (hOPT : ∃ C₀ owner₀, ValidPair G k C₀ owner₀ ∧ #C₀ = OPT)
    (_hmin : ∀ C owner, ValidPair G k C owner → OPT ≤ #C)
    {C : Finset V} {owner : G.edgeSet → V} (_h : ValidPair G k C owner) :
    #C ≤ k * OPT + 1 := by
  obtain ⟨C₀, owner₀, h₀, rfl⟩ := hOPT
  exact card_le_mul_card_add_one hG C h₀.2

/-- The hypotheses of `card_le_mul_opt_add_one` hold together: the path `0 — 1` with `k = 1`
and `OPT = 1`, attained by `C = {0}`. -/
example : ∃ C₀ owner₀, ValidPair (SimpleGraph.pathGraph 2) 1 C₀ owner₀ ∧ #C₀ = 1 := by
  refine ⟨{0}, fun _ => 0, ⟨⟨?_, ?_⟩, ?_, ?_⟩, rfl⟩
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

#print axioms card_le_mul_card_add_one
#print axioms card_le_mul_opt_add_one

end SwarmInfer.CoverWeave
