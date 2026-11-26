import SwarmInferLean.CoverWeave.Witness

/-!
# CoverWeave: no connected instance with `n ≤ 6` separates the witness from the counting bound
(inventory C7, the search claim inside the proof of `cor:witness`)

Source: `CoverWeave_R1/sections/04-formaleng.tex:104`, proof of Corollary `cor:witness` and
Figure `fig:witness`: "a smallest connected instance it captures, `n = 7`, `k = 2` and `m = 14`,
[…] while exhaustive search finds no such instance for `n ≤ 6`."

"Captures" is read from the corollary: the instance lies in the first difference, i.e. the
degree-gap witness `∑_v min(deg v, k) < m` fires while the counting bound `m > nk` does not
(`WitnessCaptures`).

Instead of a kernel enumeration this file proves a general bound by double counting, which
implies the search result for every `k` at once: an instance without isolated nodes captured at
capacity `k` has `k ≥ 2`, at least `2k + 2` nodes of degree above `k`, `n ≥ 2k + 3` and
`m ≥ 2k² + 2k + 2`. At `k = 2` this is `n ≥ 7` and `m ≥ 14`, attained by the instance `G7` of
`Witness.lean`, so `G7` is smallest both in `n` and in `m`.
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {V : Type*} [Fintype V] [DecidableEq V] {G : SimpleGraph V} [DecidableRel G.Adj]

/-- The witness captures `(G, k)`: the degree-gap witness fires and the counting bound does not. -/
def WitnessCaptures (G : SimpleGraph V) [DecidableRel G.Adj] (k : ℕ) : Prop :=
  ∑ v, min (G.degree v) k < #G.edgeFinset ∧ #G.edgeFinset ≤ Fintype.card V * k

omit [DecidableEq V] in
theorem degree_eq_sum_ite (v : V) : G.degree v = ∑ u, if G.Adj v u then 1 else 0 := by
  rw [← SimpleGraph.card_neighborFinset_eq_degree, SimpleGraph.neighborFinset_eq_filter,
    card_filter]

/-- Double counting: the degrees inside `H` are at most the `|H|(|H| - 1)` ordered pairs inside
`H` plus the degrees outside `H`. -/
theorem sum_degree_le_of_compl (H : Finset V) :
    ∑ v ∈ H, G.degree v ≤ #H * (#H - 1) + ∑ u ∈ Hᶜ, G.degree u := by
  have hsplit : ∀ v, G.degree v = (∑ u ∈ H, if G.Adj v u then 1 else 0) +
      ∑ u ∈ Hᶜ, if G.Adj v u then 1 else 0 := fun v => by
    rw [sum_add_sum_compl, degree_eq_sum_ite]
  rw [sum_congr rfl fun v _ => hsplit v, sum_add_distrib]
  refine add_le_add ?_ ?_
  · calc ∑ v ∈ H, ∑ u ∈ H, (if G.Adj v u then 1 else 0)
        ≤ ∑ _v ∈ H, (#H - 1) := by
          refine sum_le_sum fun v hv => ?_
          rw [← card_filter, ← card_erase_of_mem hv]
          refine card_le_card fun u hu => ?_
          obtain ⟨huH, hadj⟩ := mem_filter.mp hu
          exact mem_erase.mpr ⟨(G.ne_of_adj hadj).symm, huH⟩
      _ = #H * (#H - 1) := by rw [sum_const, smul_eq_mul]
  · calc ∑ v ∈ H, ∑ u ∈ Hᶜ, (if G.Adj v u then 1 else 0)
        = ∑ u ∈ Hᶜ, ∑ v ∈ H, (if G.Adj u v then 1 else 0) := by
          rw [sum_comm]; simp_rw [G.adj_comm]
      _ ≤ ∑ u ∈ Hᶜ, G.degree u := by
          gcongr with u
          rw [degree_eq_sum_ite]
          exact sum_le_sum_of_subset (subset_univ H)

/-- **Size of a captured instance.** If `G` has no isolated node and the witness captures
`(G, k)`, then `k ≥ 2`, at least `2k + 2` nodes have degree above `k`, `n ≥ 2k + 3` and
`m ≥ 2k² + 2k + 2`.

Proof: with `H` the nodes of degree above `k` and `L` the rest, the witness sum is
`|H| k + ∑_L deg` and `2m ≤ |H|(|H| - 1) + 2 ∑_L deg` by double counting, so the witness gives
`2 |H| k < |H| (|H| - 1)`; the failed counting bound `m ≤ (|H| + |L|) k` gives `∑_L deg < |L| k`,
which with `deg ≥ 1` on `L` forces `|L| ≥ 1` and `k ≥ 2`.

Modelling choices: as in `Witness.lean`; `n` is `Fintype.card V`, `m` is `#G.edgeFinset`.
Added hypotheses: `hdeg`, no isolated node; it is what connectivity gives for `n ≥ 2`
(`witnessCaptures_size_of_connected`), and without it the bound fails
(`witnessCaptures_G5`). -/
theorem witnessCaptures_size (hdeg : ∀ v, 0 < G.degree v) {k : ℕ} (h : WitnessCaptures G k) :
    2 ≤ k ∧ 2 * k + 2 ≤ #(univ.filter fun v => k < G.degree v) ∧
      2 * k + 3 ≤ Fintype.card V ∧ 2 * k * k + 2 * k + 2 ≤ #G.edgeFinset := by
  obtain ⟨hw, hc⟩ := h
  set H := univ.filter fun v => k < G.degree v with hH
  set a := #H
  set l := #Hᶜ
  set sL := ∑ u ∈ Hᶜ, G.degree u
  have hn : a + l = Fintype.card V := card_add_card_compl H
  -- the witness sum is `a k + ∑_L deg`
  have hsum : ∑ v, min (G.degree v) k = a * k + sL := by
    rw [← sum_add_sum_compl H]
    congr 1
    · rw [sum_congr rfl fun v hv => min_eq_right (mem_filter.mp hv).2.le, sum_const,
        smul_eq_mul]
    · exact sum_congr rfl fun v hv => min_eq_left (by simpa [hH] using hv)
  have h2m : ∑ v ∈ H, G.degree v + sL = 2 * #G.edgeFinset := by
    rw [sum_add_sum_compl, SimpleGraph.sum_degrees_eq_twice_card_edges]
  have hdc : ∑ v ∈ H, G.degree v ≤ a * (a - 1) + sL := sum_degree_le_of_compl H
  have hL : l ≤ sL := by
    calc l = ∑ _u ∈ Hᶜ, 1 := by simp [l]
      _ ≤ sL := sum_le_sum fun u _ => hdeg u
  rw [hsum] at hw
  -- `2 a k < a (a - 1)`, hence `a ≥ 2k + 2`
  have hak : 2 * (a * k) < a * (a - 1) := by omega
  have ha : 2 * k + 2 ≤ a := by
    by_contra hlt
    have : a * (a - 1) ≤ a * (2 * k) := Nat.mul_le_mul_left a (by omega)
    have : a * (2 * k) = 2 * (a * k) := by ring
    omega
  -- `∑_L deg < l k`, hence `l ≥ 1` and `k ≥ 2`
  have hlk : sL < l * k := by
    have : Fintype.card V * k = a * k + l * k := by rw [← hn]; ring
    omega
  have hk : 2 ≤ k := by
    by_contra hlt
    have : l * k ≤ l * 1 := Nat.mul_le_mul_left l (by omega)
    omega
  have hl : 1 ≤ l := by
    rcases Nat.eq_zero_or_pos l with h0 | h0
    · simp [h0] at hlk
    · exact h0
  refine ⟨hk, ha, by omega, ?_⟩
  have : (2 * k + 2) * k ≤ a * k := Nat.mul_le_mul_right k ha
  have : (2 * k + 2) * k = 2 * k * k + 2 * k := by ring
  omega

/-- Connected version: on a connected graph the witness never captures unless `n ≥ 2k + 3`,
`k ≥ 2` and `m ≥ 2k² + 2k + 2`. A one-node graph has no edge, so the witness cannot fire. -/
theorem witnessCaptures_size_of_connected (hG : G.Connected) {k : ℕ} (h : WitnessCaptures G k) :
    2 ≤ k ∧ 2 * k + 3 ≤ Fintype.card V ∧ 2 * k * k + 2 * k + 2 ≤ #G.edgeFinset := by
  rcases subsingleton_or_nontrivial V with hV | hV
  · have hm : #G.edgeFinset = 0 := by
      have := G.card_edgeFinset_le_card_choose_two
      rwa [Nat.choose_eq_zero_of_lt (by
        have := Fintype.card_le_one_iff_subsingleton.mpr hV; omega), Nat.le_zero] at this
    have := h.1
    omega
  · obtain ⟨hk, -, hn, hm⟩ := witnessCaptures_size (fun v => hG.preconnected.degree_pos_of_nontrivial v) h
    exact ⟨hk, hn, hm⟩

/-- **The search claim of `cor:witness`**, `04-formaleng.tex:104`, inventory C7. No connected
instance with `n ≤ 6` is captured by the degree-gap witness, at any capacity `k`; and the
instance `G7` of the figure (`n = 7`, `k = 2`, `m = 14`) is connected and captured. Together with
`witnessCaptures_size_of_connected` at `k = 2`, `G7` is smallest in `n` and in `m`.

Modelling choices:
* "Captures" is `WitnessCaptures`: `∑_v min(deg v, k) < m ≤ nk`, the first difference of the
  corollary.
* Every finite vertex type and every `k : ℕ` are covered, not only `Fin n` and `k ≤ n`.
* Proved by the double-counting bound `witnessCaptures_size`, not by enumeration; no kernel
  search is needed.

Added hypotheses: none beyond the paper's connectivity, which is needed (`witnessCaptures_G5`). -/
theorem no_witnessCaptures_of_card_le_six :
    (∀ {V : Type} [Fintype V] [DecidableEq V] (G : SimpleGraph V) [DecidableRel G.Adj] (k : ℕ),
        G.Connected → Fintype.card V ≤ 6 → ¬ WitnessCaptures G k) ∧
      (G7.Connected ∧ WitnessCaptures G7 2) := by
  refine ⟨fun G _ k hG hn h => ?_, G7_connected, ?_, ?_⟩
  · have := (witnessCaptures_size_of_connected hG h).2.1
    have := (witnessCaptures_size_of_connected hG h).1
    omega
  · rw [G7_card_edgeFinset, G7_sum_min_degree]; omega
  · rw [G7_card_edgeFinset, Fintype.card_fin]

#print axioms witnessCaptures_size
#print axioms witnessCaptures_size_of_connected
#print axioms no_witnessCaptures_of_card_le_six

/-! ### Connectivity is needed

`K₄` minus one edge on nodes `0, …, 3` plus the isolated node 4: `n = 5`, `m = 5`, and at `k = 1`
the witness sum is 4, so the witness captures a disconnected instance with `n = 5`. -/

/-- Adjacency of `K₄` minus `(0,1)`, plus an isolated node 4. -/
def g5Adj (i j : Fin 5) : Bool :=
  i != j && i.val < 4 && j.val < 4 && !(min i.val j.val == 0 && max i.val j.val == 1)

/-- A disconnected instance captured at `n = 5`, `k = 1`. -/
def G5 : SimpleGraph (Fin 5) where
  Adj i j := g5Adj i j = true
  symm := ⟨by decide⟩
  loopless := ⟨by decide⟩

instance : DecidableRel G5.Adj := fun i j => inferInstanceAs (Decidable (g5Adj i j = true))

/-- Without connectivity the search claim fails already at `n = 5`. -/
theorem witnessCaptures_G5 : ¬ G5.Connected ∧ WitnessCaptures G5 1 := by
  refine ⟨fun hG => ?_, by decide, by decide⟩
  have := hG.preconnected.degree_pos_of_nontrivial (4 : Fin 5)
  have h0 : G5.degree 4 = 0 := by decide
  omega

#print axioms witnessCaptures_G5

end SwarmInfer.CoverWeave
