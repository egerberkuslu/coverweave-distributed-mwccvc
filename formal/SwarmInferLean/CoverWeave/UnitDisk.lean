import Mathlib

/-!
# CoverWeave: unit disk graphs and the five-neighbor bound (inventory E6, C13a)

* E6: a unit disk graph is given by positions `p : V → EuclideanSpace ℝ (Fin 2)`, and `u`, `v`
  are adjacent iff `u ≠ v` and `dist (p u) (p v) ≤ 1` (`IsUnitDiskGraph`). The variant with
  `< 1` is `IsUnitDiskGraphLt`.
* C13a (`04-formaleng.tex:172`, unlabeled prose after `thm:msg`): in a unit disk graph a node has
  at most five pairwise nonadjacent neighbors (`card_le_five_of_isUnitDiskGraph`, and
  `card_le_five_of_isUnitDiskGraphLt` for the strict convention).

The geometric core is `exists_pair_norm_sub_le_max`: among six points of the plane (here `ℂ`)
two satisfy `‖x - y‖ ≤ max ‖x‖ ‖y‖`. The proof is the paper's: two of the six directions
make an angle of at most 60 degrees (a pigeonhole on arguments, `exists_cos_sub_ge_half`), and
then the law of cosines gives `‖x - y‖² = a² + b² - 2ab cos θ ≤ a² + b² - ab ≤ max a b ²`.
A point at the center itself, which the paper does not mention, is handled separately.
-/

namespace SwarmInfer.CoverWeave

open Finset Real

/-- `cos t ≥ 1/2` for `|t| ≤ π/3`. -/
theorem half_le_cos_of_abs_le {t : ℝ} (ht : |t| ≤ π / 3) : 1 / 2 ≤ Real.cos t := by
  rw [← Real.cos_abs, ← Real.cos_pi_div_three]
  exact Real.cos_le_cos_of_nonneg_of_le_pi (abs_nonneg t) (by linarith [Real.pi_pos]) ht

/-- Pigeonhole on directions: among at least six angles in `(-π, π]`, two differ by an angle
whose cosine is at least `1/2`, that is, they are at most 60 degrees apart on the circle. -/
theorem exists_cos_sub_ge_half {ι : Type*} (s : Finset ι) (hs : 6 ≤ #s) (θ : ι → ℝ)
    (hθ : ∀ i ∈ s, -π < θ i ∧ θ i ≤ π) :
    ∃ i ∈ s, ∃ j ∈ s, i ≠ j ∧ 1 / 2 ≤ Real.cos (θ i - θ j) := by
  have hne : s.Nonempty := card_pos.mp (by omega)
  obtain ⟨m, hm, hmin⟩ := s.exists_min_image θ hne
  have hpi := Real.pi_pos
  -- `d i = θ i - θ m` lies in `[0, 2π)`
  have hd : ∀ i ∈ s, 0 ≤ θ i - θ m ∧ θ i - θ m < 2 * π := fun i hi =>
    ⟨by linarith [hmin i hi], by linarith [(hθ i hi).2, (hθ m hm).1]⟩
  by_cases hwrap : ∃ i ∈ s, 5 * π / 3 ≤ θ i - θ m
  · -- wrap-around gap: the point `i` is within 60 degrees of `m` going the other way
    obtain ⟨i, hi, hi5⟩ := hwrap
    refine ⟨i, hi, m, hm, fun h => by subst h; linarith, ?_⟩
    rw [← Real.cos_sub_two_pi]
    exact half_le_cos_of_abs_le (abs_le.mpr ⟨by linarith, by linarith [(hd i hi).2]⟩)
  · push Not at hwrap
    -- five bins `[kπ/3, (k+1)π/3)`, `k < 5`, for six points
    have hmaps : Set.MapsTo (fun i => ⌊(θ i - θ m) / (π / 3)⌋₊) s (range 5) := by
      intro i hi
      have := hwrap i hi
      simp only [coe_range, Set.mem_Iio]
      refine (Nat.floor_lt (div_nonneg (hd i hi).1 (by positivity))).mpr ?_
      rw [div_lt_iff₀ (by positivity)]
      push_cast
      linarith
    obtain ⟨i, hi, j, hj, hij, hfl⟩ :=
      exists_ne_map_eq_of_card_lt_of_maps_to (by simp; omega) hmaps
    refine ⟨i, hi, j, hj, hij, half_le_cos_of_abs_le ?_⟩
    have hp3 : 0 < π / 3 := by positivity
    have key : ∀ k ∈ s, (⌊(θ k - θ m) / (π / 3)⌋₊ : ℝ) * (π / 3) ≤ θ k - θ m ∧
        θ k - θ m < ((⌊(θ k - θ m) / (π / 3)⌋₊ : ℝ) + 1) * (π / 3) := fun k hk => by
      have h0 : 0 ≤ (θ k - θ m) / (π / 3) := div_nonneg (hd k hk).1 hp3.le
      constructor
      · rw [← le_div_iff₀ hp3]; exact Nat.floor_le h0
      · rw [← div_lt_iff₀ hp3]; exact Nat.lt_floor_add_one _
    have hki := key i hi
    have hkj := key j hj
    rw [hfl] at hki
    exact abs_le.mpr ⟨by linarith, by linarith⟩

/-- Law of cosines step: if the directions of two nonzero points are at most 60 degrees apart
(cosine of the argument difference at least `1/2`), their distance is at most the larger of
their norms. -/
theorem norm_sub_le_max_of_half_le_cos {x y : ℂ} (hx : x ≠ 0) (hy : y ≠ 0)
    (h : 1 / 2 ≤ Real.cos (Complex.arg x - Complex.arg y)) : ‖x - y‖ ≤ max ‖x‖ ‖y‖ := by
  have hx0 : 0 < ‖x‖ := norm_pos_iff.mpr hx
  have hy0 : 0 < ‖y‖ := norm_pos_iff.mpr hy
  have hre : (x * (starRingEnd ℂ) y).re = ‖x‖ * ‖y‖ * Real.cos (Complex.arg x - Complex.arg y) := by
    rw [Real.cos_sub, Complex.cos_arg hx, Complex.cos_arg hy, Complex.sin_arg, Complex.sin_arg]
    simp only [Complex.mul_re, Complex.conj_re, Complex.conj_im]
    field_simp
    ring
  have h2 : ‖x - y‖ ^ 2 = ‖x‖ ^ 2 + ‖y‖ ^ 2 - 2 * (x * (starRingEnd ℂ) y).re := by
    rw [Complex.sq_norm, Complex.sq_norm, Complex.sq_norm, Complex.normSq_sub]
  have hc := mul_nonneg (mul_nonneg hx0.le hy0.le) (sub_nonneg.mpr h)
  have hsq : ‖x - y‖ ^ 2 ≤ (max ‖x‖ ‖y‖) ^ 2 := by
    rw [h2, hre]
    rcases le_total ‖x‖ ‖y‖ with hab | hab
    · rw [max_eq_right hab]; nlinarith [mul_nonneg hx0.le (sub_nonneg.mpr hab)]
    · rw [max_eq_left hab]; nlinarith [mul_nonneg hy0.le (sub_nonneg.mpr hab)]
  exact (sq_le_sq₀ (norm_nonneg _) (le_max_of_le_left hx0.le)).mp hsq

/-- **Geometric core of C13a.** Among at least six points of the plane (positions relative to a
center), two distinct ones satisfy `‖x i - x j‖ ≤ max ‖x i‖ ‖x j‖`. Coincident points and a
point at the center are allowed. -/
theorem exists_pair_norm_sub_le_max {ι : Type*} (s : Finset ι) (hs : 6 ≤ #s) (x : ι → ℂ) :
    ∃ i ∈ s, ∃ j ∈ s, i ≠ j ∧ ‖x i - x j‖ ≤ max ‖x i‖ ‖x j‖ := by
  by_cases h0 : ∃ i ∈ s, x i = 0
  · obtain ⟨i, hi, hxi⟩ := h0
    obtain ⟨j, hj, hji⟩ := s.exists_mem_ne (by omega) i
    exact ⟨i, hi, j, hj, hji.symm, by simp [hxi]⟩
  · push Not at h0
    obtain ⟨i, hi, j, hj, hij, hcos⟩ := exists_cos_sub_ge_half s hs (fun i => Complex.arg (x i))
      (fun i _ => ⟨Complex.neg_pi_lt_arg _, Complex.arg_le_pi _⟩)
    exact ⟨i, hi, j, hj, hij, norm_sub_le_max_of_half_le_cos (h0 i hi) (h0 j hj) hcos⟩

#print axioms exists_pair_norm_sub_le_max

variable {V : Type*}

/-- Unit disk graph (inventory E6): `u` and `v` are adjacent iff they are distinct and their
positions in the plane are at distance at most one. -/
def IsUnitDiskGraph (G : SimpleGraph V) (p : V → EuclideanSpace ℝ (Fin 2)) : Prop :=
  ∀ u v, G.Adj u v ↔ u ≠ v ∧ dist (p u) (p v) ≤ 1

/-- Unit disk graph with the strict convention `dist < 1`. -/
def IsUnitDiskGraphLt (G : SimpleGraph V) (p : V → EuclideanSpace ℝ (Fin 2)) : Prop :=
  ∀ u v, G.Adj u v ↔ u ≠ v ∧ dist (p u) (p v) < 1

/-- The plane `EuclideanSpace ℝ (Fin 2)` seen as `ℂ`, isometrically. -/
noncomputable abbrev toComplex : EuclideanSpace ℝ (Fin 2) ≃ₗᵢ[ℝ] ℂ :=
  Complex.orthonormalBasisOneI.repr.symm

/-- Positions relative to `p v`, transported to `ℂ`, have the distances of the plane. -/
theorem exists_pair_dist_le_max (p : V → EuclideanSpace ℝ (Fin 2)) (c : EuclideanSpace ℝ (Fin 2))
    (s : Finset V) (hs : 6 ≤ #s) :
    ∃ i ∈ s, ∃ j ∈ s, i ≠ j ∧ dist (p i) (p j) ≤ max (dist (p i) c) (dist (p j) c) := by
  obtain ⟨i, hi, j, hj, hij, h⟩ :=
    exists_pair_norm_sub_le_max s hs (fun i => toComplex (p i - c))
  refine ⟨i, hi, j, hj, hij, ?_⟩
  rw [← map_sub, LinearIsometryEquiv.norm_map, LinearIsometryEquiv.norm_map,
    LinearIsometryEquiv.norm_map, sub_sub_sub_cancel_right] at h
  simpa [dist_eq_norm] using h

/-- **C13a** (`04-formaleng.tex:172`, prose). In a unit disk graph a node has at most five
pairwise nonadjacent neighbors.

Modelling choices:
* Positions are `p : V → EuclideanSpace ℝ (Fin 2)`, adjacency is `u ≠ v ∧ dist ≤ 1` (E6). The
  paper does not fix the boundary convention; `≤ 1` is used here, and
  `card_le_five_of_isUnitDiskGraphLt` proves the same bound for `< 1`.
* Positions need not be injective: several nodes may share a position, and a neighbor may sit
  at the position of `v` (the case the paper's angle argument leaves out; such a neighbor is
  adjacent to every other neighbor).
* A set of neighbors is a `Finset` `I ⊆ G.neighborFinset v` that is pairwise nonadjacent. -/
theorem card_le_five_of_isUnitDiskGraph {G : SimpleGraph V} [Fintype V] [DecidableRel G.Adj]
    {p : V → EuclideanSpace ℝ (Fin 2)} (hG : IsUnitDiskGraph G p) (v : V) (I : Finset V)
    (hI : I ⊆ G.neighborFinset v) (hind : (I : Set V).Pairwise fun a b => ¬ G.Adj a b) :
    #I ≤ 5 := by
  by_contra! h6
  obtain ⟨i, hi, j, hj, hij, hd⟩ := exists_pair_dist_le_max p (p v) I h6
  have hn : ∀ k ∈ I, dist (p k) (p v) ≤ 1 := fun k hk => by
    have := ((hG v k).mp ((G.mem_neighborFinset v k).mp (hI hk))).2
    rwa [dist_comm]
  exact hind hi hj hij ((hG i j).mpr ⟨hij, hd.trans (max_le (hn i hi) (hn j hj))⟩)

/-- C13a with the strict convention `dist < 1`. -/
theorem card_le_five_of_isUnitDiskGraphLt {G : SimpleGraph V} [Fintype V] [DecidableRel G.Adj]
    {p : V → EuclideanSpace ℝ (Fin 2)} (hG : IsUnitDiskGraphLt G p) (v : V) (I : Finset V)
    (hI : I ⊆ G.neighborFinset v) (hind : (I : Set V).Pairwise fun a b => ¬ G.Adj a b) :
    #I ≤ 5 := by
  by_contra! h6
  obtain ⟨i, hi, j, hj, hij, hd⟩ := exists_pair_dist_le_max p (p v) I h6
  have hn : ∀ k ∈ I, dist (p k) (p v) < 1 := fun k hk => by
    have := ((hG v k).mp ((G.mem_neighborFinset v k).mp (hI hk))).2
    rwa [dist_comm]
  exact hind hi hj hij ((hG i j).mpr ⟨hij, hd.trans_lt (max_lt (hn i hi) (hn j hj))⟩)

#print axioms card_le_five_of_isUnitDiskGraph
#print axioms card_le_five_of_isUnitDiskGraphLt

/-- Positions of the sharpness example: the center and five points close to a regular pentagon
of radius one, with rational coordinates. -/
noncomputable def pentagonPos : Fin 6 → EuclideanSpace ℝ (Fin 2)
  | 0 => !₂[0, 0]
  | 1 => !₂[1, 0]
  | 2 => !₂[3 / 10, 95 / 100]
  | 3 => !₂[-4 / 5, 58 / 100]
  | 4 => !₂[-4 / 5, -58 / 100]
  | 5 => !₂[3 / 10, -95 / 100]

/-- The unit disk graph of `pentagonPos`. -/
noncomputable def pentagonGraph : SimpleGraph (Fin 6) where
  Adj u v := u ≠ v ∧ dist (pentagonPos u) (pentagonPos v) ≤ 1
  symm := ⟨fun _ _ h => ⟨h.1.symm, by rw [dist_comm]; exact h.2⟩⟩
  loopless := ⟨fun _ h => h.1 rfl⟩

theorem pentagonPos_dist_sq (u v : Fin 6) :
    dist (pentagonPos u) (pentagonPos v) =
      √((pentagonPos u 0 - pentagonPos v 0) ^ 2 + (pentagonPos u 1 - pentagonPos v 1) ^ 2) := by
  rw [EuclideanSpace.dist_eq, Fin.sum_univ_two, Real.dist_eq, Real.dist_eq, sq_abs, sq_abs]

/-- C13a is sharp and its hypotheses hold together: in the unit disk graph `pentagonGraph` the
center `0` has the five pairwise nonadjacent neighbors `1, …, 5`. -/
theorem pentagon_sharp :
    IsUnitDiskGraph pentagonGraph pentagonPos ∧
    ∃ I : Finset (Fin 6), (∀ i ∈ I, pentagonGraph.Adj 0 i) ∧
      (I : Set (Fin 6)).Pairwise (fun a b => ¬ pentagonGraph.Adj a b) ∧ #I = 5 := by
  refine ⟨fun u v => Iff.rfl, {1, 2, 3, 4, 5}, ?_, ?_, rfl⟩
  · intro i hi
    simp only [mem_insert, mem_singleton] at hi
    refine ⟨by omega, ?_⟩
    rw [pentagonPos_dist_sq, Real.sqrt_le_one]
    rcases hi with rfl | rfl | rfl | rfl | rfl <;> simp [pentagonPos] <;> norm_num
  · intro a ha b hb hab hadj
    have h2 := hadj.2
    rw [pentagonPos_dist_sq, Real.sqrt_le_one] at h2
    simp only [coe_insert, coe_singleton, Set.mem_insert_iff, Set.mem_singleton_iff] at ha hb
    rcases ha with rfl | rfl | rfl | rfl | rfl <;> rcases hb with rfl | rfl | rfl | rfl | rfl <;>
      simp [pentagonPos] at hab h2 <;> norm_num at h2

#print axioms pentagon_sharp

end SwarmInfer.CoverWeave
