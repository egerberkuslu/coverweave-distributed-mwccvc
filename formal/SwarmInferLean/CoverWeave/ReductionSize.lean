import SwarmInferLean.CoverWeave.SetCoverGadget

/-!
# CoverWeave: sizes of the reductions of `thm:hardness` (inventory C1, parts 2 and 3)

Source: `CoverWeave_R1/sections/04-formaleng.tex:15–24`, Theorem `thm:hardness` and its proof.
The reductions must be polynomial; this file proves the exact sizes of their images.

* Set cover gadget (`SetCoverGadget.lean`): the image of `(U, (S_i)_{i ∈ ι}, c)` has
  `|ι| + |U| + 1` nodes and `|ι| + ∑_i |S_i|` edges, every weight is an input cost `c i` or `ε`,
  and `k = Δ(G) < n`.
* Unit-weight case: the map is the identity on `G` with `w ≡ 1` and the capacity fixed.

Encoding size counted (one symbol each): for a set cover instance, every element, every set, every
membership `x ∈ S_i` and every cost `c i`; for an MWCCVC instance, every node, every edge, every
weight `w v` and the capacity `k`. A symbol's own bit length is not counted, but the weight
lemmas show that every output number is an input number, `ε`, `1`, or (for `k`) below `n`.
-/

namespace SwarmInfer.CoverWeave

open Finset

/-- Encoding size of an MWCCVC instance on `G`: `n` nodes, `m` edges, `n` weights, one capacity. -/
def mwccvcSize {V : Type*} [Fintype V] (G : SimpleGraph V) [DecidableRel G.Adj] : ℕ :=
  Fintype.card V + #G.edgeFinset + Fintype.card V + 1

section Gadget

variable {ι U : Type*} [Fintype ι] [Fintype U] [DecidableEq ι] [DecidableEq U]

/-- Encoding size of a weighted set cover instance: elements, sets, memberships, costs. -/
def setCoverSize (S : ι → Finset U) : ℕ :=
  Fintype.card U + Fintype.card ι + ∑ i, #(S i) + Fintype.card ι

/-- The edge of the gadget named by a set (root edge) or by a membership `x ∈ S_i`. -/
def gadgetEdge : ι ⊕ (Σ _ : ι, U) → Sym2 (GadgetV ι U)
  | .inl i => s(none, some (.inl i))
  | .inr ⟨i, x⟩ => s(some (.inl i), some (.inr x))

omit [Fintype ι] [Fintype U] [DecidableEq ι] [DecidableEq U] in
theorem gadgetEdge_injective : Function.Injective (gadgetEdge (ι := ι) (U := U)) := by
  rintro (i | ⟨i, x⟩) (j | ⟨j, y⟩) h <;> simp_all [gadgetEdge]

/-- The edges of the gadget are exactly the root edges and the membership edges. -/
theorem gadget_edgeFinset (S : ι → Finset U) :
    (gadget S).edgeFinset = (univ.disjSum (univ.sigma S)).image gadgetEdge := by
  ext e
  induction e using Sym2.ind with
  | h a b =>
    simp only [SimpleGraph.mem_edgeFinset, SimpleGraph.mem_edgeSet, mem_image, Sum.exists,
      Sigma.exists, inl_mem_disjSum, inr_mem_disjSum, mem_sigma, mem_univ, true_and]
    rcases a with _ | (i | x) <;> rcases b with _ | (j | y) <;>
      simp [gadget, gadgetRel, gadgetEdge, eq_comm]

omit [DecidableEq ι] [DecidableEq U] in
/-- Node count of the gadget: `|ι| + |U| + 1`. -/
theorem gadget_card_verts : Fintype.card (GadgetV ι U) = Fintype.card ι + Fintype.card U + 1 := by
  simp [Fintype.card_option, Fintype.card_sum]

/-- Edge count of the gadget: `|ι| + ∑_i |S_i|`. -/
theorem gadget_card_edgeFinset (S : ι → Finset U) :
    #(gadget S).edgeFinset = Fintype.card ι + ∑ i, #(S i) := by
  rw [gadget_edgeFinset, card_image_of_injective _ gadgetEdge_injective, card_disjSum,
    card_sigma, card_univ]

omit [Fintype ι] [Fintype U] [DecidableEq ι] [DecidableEq U] in
/-- Every gadget weight is an input cost or `ε`. -/
theorem gadgetWeight_mem (c : ι → ℝ) (ε : ℝ) (a : GadgetV ι U) :
    gadgetWeight c ε a = ε ∨ ∃ i, gadgetWeight c ε a = c i := by
  rcases a with _ | (i | x) <;> simp [gadgetWeight]

/-- The capacity `k = Δ(G)` of the gadget is below its node count. -/
theorem gadget_maxDegree_lt (S : ι → Finset U) :
    (gadget S).maxDegree < Fintype.card ι + Fintype.card U + 1 :=
  gadget_card_verts (ι := ι) (U := U) ▸ (gadget S).maxDegree_lt_card_verts

/-- **Theorem (Hardness)**, size of the set cover gadget, `thm:hardness`, inventory C1(3). The
image of `(U, S, c)` under the gadget map has exactly `|ι| + |U| + 1` nodes and
`|ι| + ∑_i |S_i|` edges, each weight is an input cost or `ε`, `k = Δ(G) < n`, and its encoding
size is `3|ι| + 2|U| + ∑_i |S_i| + 3 ≤ 3 · size(U, S, c) + 3`: linear in the input.

Modelling choices:
* Sizes count symbols as in the module docstring; numbers are not measured in bits, but every
  output number is an input number, `ε` or below `n`.
* `ε` is a parameter of the map; its bit length is chosen on paper.

Stays on paper: the running time of the map (it writes each node and each edge once, so
`O(n + m)` steps). -/
theorem gadget_size (S : ι → Finset U) (c : ι → ℝ) (ε : ℝ) :
    Fintype.card (GadgetV ι U) = Fintype.card ι + Fintype.card U + 1 ∧
      #(gadget S).edgeFinset = Fintype.card ι + ∑ i, #(S i) ∧
      (∀ a : GadgetV ι U, gadgetWeight c ε a = ε ∨ ∃ i, gadgetWeight c ε a = c i) ∧
      (gadget S).maxDegree < Fintype.card (GadgetV ι U) ∧
      mwccvcSize (gadget S) = 3 * Fintype.card ι + 2 * Fintype.card U + ∑ i, #(S i) + 3 ∧
      mwccvcSize (gadget S) ≤ 3 * setCoverSize S + 3 := by
  have hv := gadget_card_verts (ι := ι) (U := U)
  have he := gadget_card_edgeFinset S
  refine ⟨hv, he, gadgetWeight_mem c ε, hv ▸ gadget_maxDegree_lt S, ?_, ?_⟩ <;>
    simp only [mwccvcSize, setCoverSize, hv, he] <;> omega

#print axioms gadget_size

/-- Non-vacuity: two sets `{0}`, `{0, 1}` over a two-element universe give a gadget with
`2 + 2 + 1 = 5` nodes and `2 + 3 = 5` edges. -/
example : #(gadget (fun i : Fin 2 => if i = 0 then ({0} : Finset (Fin 2)) else univ)).edgeFinset
    = 5 := by
  rw [gadget_card_edgeFinset]; decide

end Gadget

/-! ### Unit-weight case -/

/-- The unit-weight reduction: connected vertex cover on `G` maps to MWCCVC on `G` with `w ≡ 1`
and a fixed capacity `k` (the paper uses any fixed `k ≥ 4`). -/
def unitImage {V : Type*} (G : SimpleGraph V) (k : ℕ) : SimpleGraph V × (V → ℝ) × ℕ :=
  (G, fun _ => 1, k)

/-- **Theorem (Hardness)**, size of the unit-weight reduction, `thm:hardness`, inventory C1(2).
The image of `G` is `G` itself with every weight `1` and capacity `k`, so it has the same `n`
and `m`, and its encoding size `2n + m + 1` is at most `2 (n + m) + 1`.

Modelling choices: the input size of a connected vertex cover instance is `n + m` (the budget
of its decision version is not counted). The statement is nearly definitional: the map is the
identity on the graph. -/
theorem unitImage_size {V : Type*} [Fintype V] (G : SimpleGraph V) [DecidableRel G.Adj] (k : ℕ) :
    (unitImage G k).1 = G ∧ (∀ v, (unitImage G k).2.1 v = 1) ∧ (unitImage G k).2.2 = k ∧
      mwccvcSize G = 2 * Fintype.card V + #G.edgeFinset + 1 ∧
      mwccvcSize G ≤ 2 * (Fintype.card V + #G.edgeFinset) + 1 := by
  refine ⟨rfl, fun _ => rfl, rfl, ?_, ?_⟩ <;> simp only [mwccvcSize] <;> omega

#print axioms unitImage_size

end SwarmInfer.CoverWeave
