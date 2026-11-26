import SwarmInferLean.CoverWeave.Ownership

/-!
# CoverWeave: the set cover gadget (inventory C1 part 3)

`thm:hardness` (`CoverWeave_R1/sections/04-formaleng.tex:15`), third sentence of the statement and
second paragraph of the proof: "join a root to every set node of a set-cover instance on universe
`U` and each set node to its elements, weigh the root and the elements `ε`, and let `k = Δ(G)`. A
connected cover then contains a set for each element, and the root, `U` and any set cover form a
valid pair, so set cover […] carries over."

This file proves the two combinatorial directions and the exact weight relation, and states the
approximation transfer that they give, with the additive term `ε (|U| + 1)` visible.
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {ι U : Type*} [DecidableEq ι] [DecidableEq U]

/-- Vertices of the gadget: `none` is the root, `some (inl i)` the set node of `S i`,
`some (inr x)` the element node of `x`. -/
abbrev GadgetV (ι U : Type*) := Option (ι ⊕ U)

/-- The one-directional relation of the gadget: root to every set, set `i` to each `x ∈ S i`. -/
def gadgetRel (S : ι → Finset U) : GadgetV ι U → GadgetV ι U → Prop
  | none, some (.inl _) => True
  | some (.inl i), some (.inr x) => x ∈ S i
  | _, _ => False

instance (S : ι → Finset U) : DecidableRel (gadgetRel S) := fun a b => by
  rcases a with _ | (i | x) <;> rcases b with _ | (j | y) <;> simp only [gadgetRel] <;>
    infer_instance

/-- The gadget graph of the set system `S` on the universe `U`. -/
def gadget (S : ι → Finset U) : SimpleGraph (GadgetV ι U) :=
  SimpleGraph.fromRel (gadgetRel S)

instance (S : ι → Finset U) : DecidableRel (gadget S).Adj := fun a b =>
  decidable_of_iff' _ (SimpleGraph.fromRel_adj (gadgetRel S) a b)

variable {S : ι → Finset U}

omit [DecidableEq ι] [DecidableEq U] in

@[simp] theorem gadget_adj_root_set (i : ι) : (gadget S).Adj none (some (.inl i)) := by
  simp [gadget, gadgetRel]

omit [DecidableEq ι] [DecidableEq U] in
@[simp] theorem gadget_adj_set_elem {i : ι} {x : U} :
    (gadget S).Adj (some (.inl i)) (some (.inr x)) ↔ x ∈ S i := by
  simp [gadget, gadgetRel]

omit [DecidableEq ι] [DecidableEq U] in
/-- The neighbours of an element node are exactly the set nodes that contain it. -/
theorem gadget_adj_elem {x : U} {b : GadgetV ι U} :
    (gadget S).Adj (some (.inr x)) b ↔ ∃ i, b = some (.inl i) ∧ x ∈ S i := by
  rcases b with _ | (j | y) <;> simp [gadget, gadgetRel]

variable [Fintype ι] [Fintype U]

/-- Weights of the gadget: `ε` on the root and the elements, `c i` on the set node of `S i`. -/
def gadgetWeight (c : ι → ℝ) (ε : ℝ) : GadgetV ι U → ℝ
  | some (.inl i) => c i
  | _ => ε

/-- The sets read off a vertex set `C`: `{i | S_i ∈ C}`. -/
def readOff (C : Finset (GadgetV ι U)) : Finset ι := {i | some (.inl i) ∈ C}

/-- The cover built from a family `I`: the root, every element, and the set nodes of `I`. -/
def gadgetCover (I : Finset ι) : Finset (GadgetV ι U) :=
  insert none (I.image (fun i => some (.inl i)) ∪ univ.image (fun x => some (.inr x)))

/-- `I` is a set cover of `U` by `S`. -/
def IsSetCover (S : ι → Finset U) (I : Finset ι) : Prop := ∀ x : U, ∃ i ∈ I, x ∈ S i

/-- Cost of a family of sets. -/
def setCost (c : ι → ℝ) (I : Finset ι) : ℝ := ∑ i ∈ I, c i

omit [Fintype ι] in
theorem mem_gadgetCover {I : Finset ι} {a : GadgetV ι U} :
    a ∈ gadgetCover (U := U) I ↔ a = none ∨ (∃ i ∈ I, a = some (.inl i)) ∨ ∃ x, a = some (.inr x) := by
  rcases a with _ | (j | y) <;> simp [gadgetCover]

omit [Fintype U] in
/-- **Direction 1** (inventory C1(iii), part 3). From any connected vertex cover of the gadget one
reads off a set cover, provided every element lies in some set.

Added hypotheses:
* `hcov : ∀ x, ∃ i, x ∈ S i`. Without it an element in no set is an isolated node, a connected
  cover need not contain any set for it, and no set cover exists at all. It is the standard
  assumption on a set cover instance and implies that there is at least one set. -/
theorem readOff_isSetCover (hcov : ∀ x : U, ∃ i, x ∈ S i) {C : Finset (GadgetV ι U)}
    (hC : IsConnectedVertexCover (gadget S) C) : IsSetCover S (readOff C) := by
  intro x
  obtain ⟨i, hi⟩ := hcov x
  by_cases hx : some (.inr x) ∈ C
  · -- the root–set edge at `i` puts a second vertex `b` into `C`
    have hb : ∃ b ∈ C, b ≠ some (.inr x) := by
      rcases hC.1 (gadget_adj_root_set (S := S) i) with h | h
      · exact ⟨none, h, by simp⟩
      · exact ⟨_, h, by simp⟩
    obtain ⟨b, hbC, hbx⟩ := hb
    obtain ⟨p⟩ := hC.2.preconnected ⟨some (.inr x), hx⟩ ⟨b, hbC⟩
    cases p with
    | nil => exact absurd rfl hbx
    | @cons _ z _ hadj _ =>
      obtain ⟨j, hj, hxj⟩ := gadget_adj_elem.mp (SimpleGraph.induce_adj.mp hadj)
      refine ⟨j, ?_, hxj⟩
      simp only [readOff, mem_filter, mem_univ, true_and]
      exact hj ▸ z.2
  · rcases hC.1 (gadget_adj_set_elem.mpr hi) with h | h
    · exact ⟨i, by simpa [readOff] using h, hi⟩
    · exact absurd h hx

/-- **Direction 2** (inventory C1(iii), part 3). For every set cover `I`, the root, all elements
and the sets of `I` form a connected vertex cover of the gadget that carries a valid owner map at
capacity `k = Δ(G)`. -/
theorem gadgetCover_validPair {I : Finset ι} (hI : IsSetCover S I) :
    ∃ owner, ValidPair (gadget S) (gadget S).maxDegree (gadgetCover I) owner := by
  refine (exists_validPair_iff_of_maxDegree_le le_rfl _).mpr ⟨?_, ?_⟩
  · intro a b hab
    simp only [gadget, SimpleGraph.fromRel_adj] at hab
    rcases hab with ⟨-, h | h⟩ <;>
      rcases a with _ | (i | x) <;> rcases b with _ | (j | y) <;>
      simp_all [gadgetRel, mem_gadgetCover]
  · have hroot : none ∈ gadgetCover (U := U) I := mem_gadgetCover.mpr (Or.inl rfl)
    have hset : ∀ i (hi : i ∈ I),
        ((gadget S).induce (gadgetCover (U := U) I : Set (GadgetV ι U))).Reachable
        ⟨none, hroot⟩ ⟨some (.inl i), Finset.mem_coe.mpr (mem_gadgetCover.mpr (Or.inr (Or.inl ⟨i, hi, rfl⟩)))⟩ :=
      fun i _ => (SimpleGraph.induce_adj.mpr (gadget_adj_root_set i)).reachable
    rw [SimpleGraph.connected_iff_exists_forall_reachable]
    refine ⟨⟨none, hroot⟩, fun ⟨a, ha⟩ => ?_⟩
    rcases mem_gadgetCover.mp ha with rfl | ⟨i, hi, rfl⟩ | ⟨x, rfl⟩
    · rfl
    · exact hset i hi
    · obtain ⟨i, hi, hxi⟩ := hI x
      exact (hset i hi).trans
        (SimpleGraph.induce_adj.mpr (gadget_adj_set_elem.mpr hxi)).reachable

omit [Fintype ι] in
/-- **Weight identity.** The cover built from `I` weighs exactly `ε (|U| + 1) + c(I)`. -/
theorem weight_gadgetCover (c : ι → ℝ) (ε : ℝ) (I : Finset ι) :
    weight (gadgetWeight c ε) (gadgetCover (U := U) I) = setCost c I + ε * (Fintype.card U + 1) := by
  rw [weight, gadgetCover, sum_insert (by simp), sum_union (by
    rw [disjoint_left]; simp), sum_image (fun _ _ _ _ h => by simpa using h),
    sum_image (fun _ _ _ _ h => by simpa using h)]
  simp [gadgetWeight, setCost]
  ring

omit [Fintype U] in
/-- **Weight inequality.** With nonnegative weights, a vertex set weighs at least the cost of the
sets read off it. -/
theorem setCost_readOff_le (c : ι → ℝ) {ε : ℝ} (hc : ∀ i, 0 ≤ c i) (hε : 0 ≤ ε)
    (C : Finset (GadgetV ι U)) : setCost c (readOff C) ≤ weight (gadgetWeight c ε) C := by
  have hnn : ∀ a, 0 ≤ gadgetWeight (U := U) c ε a := by
    rintro (_ | (i | x)) <;> simp [gadgetWeight, hc, hε]
  calc setCost c (readOff C) = ∑ a ∈ (readOff C).image
        (fun i => (some (.inl i) : GadgetV ι U)), gadgetWeight c ε a := by
          rw [sum_image (by simp)]; rfl
    _ ≤ weight (gadgetWeight c ε) C := by
        refine sum_le_sum_of_subset_of_nonneg ?_ fun a _ _ => hnn a
        intro a ha
        obtain ⟨i, hi, rfl⟩ := mem_image.mp ha
        simpa [readOff] using hi

/-- **Theorem (Hardness)**, part (3), the set cover gadget, `thm:hardness`, inventory C1.
Let every element lie in some set, let the set weights `c` be nonnegative and `ε ≥ 0`. If a
connected vertex cover `C` of the gadget is within a factor `ρ` of the cover built from a set
cover `I` (in particular, if `C` is a `ρ`-approximate MWCCVC solution, since that cover is valid by
`gadgetCover_validPair`), then the sets read off `C` form a set cover of cost

  `c(readOff C) ≤ ρ · (c(I) + ε (|U| + 1))`.

This is what the gadget gives, and all of it: a `ρ`-approximation for MWCCVC on gadget instances
yields a set cover within `ρ` of the optimum *plus the additive term* `ρ ε (|U| + 1)`.

Modelling choices:
* Sets are indexed by a `Fintype ι`, elements form a `Fintype U`; the gadget lives on
  `Option (ι ⊕ U)` with `none` the root. Weights are real, `gadgetWeight c ε`.
* `k = Δ(G)` is `(gadget S).maxDegree`; validity of the built cover is `gadgetCover_validPair`.
* The paper's weights are positive; here `c ≥ 0`, `ε ≥ 0` suffices.

Added hypotheses:
* `hcov`: every element is in some set (see `readOff_isSetCover`).

Stays on paper, and how the paper should word it. The paper writes that set cover "carries over"
with its `c ln |U|` bound. What follows is weaker in two ways.
1. The additive term: choosing `ε (|U| + 1) ≤ δ · min_i c i` (possible since `ε` is free) turns
   the bound into `ρ (1 + δ) · OPT_SC`, see `setCost_readOff_le_of_eps`. The paper must say that
   `ε` is chosen this small.
2. The ratio's argument: set cover hardness is in `|U|`, while a ratio for MWCCVC is measured in
   `n = 1 + |ι| + |U|`. Since `|ι|` is polynomial in `|U|` on hard instances, `ln n ≤ c'' ln |U|`
   only for some constant `c''`, so the transfer gives "no polynomial `c' ln n`-approximation
   for some constant `c' > 0` unless P = NP", not the same `c`. The NP-hardness of approximating
   set cover (Dinur and Steurer 2014) and polynomiality of the gadget stay on paper.
Suggested sentence: "With arbitrary weights and `k` in the input there is a constant `c' > 0`
such that MWCCVC has no polynomial-time `c' ln n` approximation unless P = NP." -/
theorem setCover_gadget_transfer (hcov : ∀ x : U, ∃ i, x ∈ S i) (c : ι → ℝ)
    (hc : ∀ i, 0 ≤ c i) {ε : ℝ} (hε : 0 ≤ ε) {I : Finset ι} {C : Finset (GadgetV ι U)}
    (hC : IsConnectedVertexCover (gadget S) C) {ρ : ℝ}
    (hρ : weight (gadgetWeight c ε) C ≤ ρ * weight (gadgetWeight c ε) (gadgetCover (U := U) I)) :
    IsSetCover S (readOff C) ∧
      setCost c (readOff C) ≤ ρ * (setCost c I + ε * (Fintype.card U + 1)) :=
  ⟨readOff_isSetCover hcov hC,
    (setCost_readOff_le c hc hε C).trans (by rwa [weight_gadgetCover] at hρ)⟩

/-- The additive term absorbed: if `ε (|U| + 1) ≤ δ · c(I)` and `ρ ≥ 0`, the read-off cover is
within `ρ (1 + δ)` of `c(I)`. -/
theorem setCost_readOff_le_of_eps (hcov : ∀ x : U, ∃ i, x ∈ S i) (c : ι → ℝ)
    (hc : ∀ i, 0 ≤ c i) {ε δ : ℝ} (hε : 0 ≤ ε) {I : Finset ι} {C : Finset (GadgetV ι U)}
    (hC : IsConnectedVertexCover (gadget S) C) {ρ : ℝ} (hρ0 : 0 ≤ ρ)
    (hρ : weight (gadgetWeight c ε) C ≤ ρ * weight (gadgetWeight c ε) (gadgetCover (U := U) I))
    (hεδ : ε * (Fintype.card U + 1) ≤ δ * setCost c I) :
    setCost c (readOff C) ≤ ρ * (1 + δ) * setCost c I := by
  have := (setCover_gadget_transfer hcov c hc hε hC hρ).2
  nlinarith [mul_le_mul_of_nonneg_left hεδ hρ0]

#print axioms readOff_isSetCover
#print axioms gadgetCover_validPair
#print axioms weight_gadgetCover
#print axioms setCover_gadget_transfer
#print axioms setCost_readOff_le_of_eps

/-- Non-vacuity: two sets `{0}`, `{0, 1}` over a two-element universe; `{1}` (the second set) is
a set cover, and the hypotheses of the transfer hold together. -/
example : IsSetCover (fun i : Fin 2 => if i = 0 then ({0} : Finset (Fin 2)) else univ) {1} ∧
    ∀ x : Fin 2, ∃ i, x ∈ (fun i : Fin 2 => if i = 0 then ({0} : Finset (Fin 2)) else univ) i :=
  ⟨by unfold IsSetCover; decide, by decide⟩

end SwarmInfer.CoverWeave
