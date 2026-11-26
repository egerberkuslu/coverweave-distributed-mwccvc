import SwarmInferLean.CoverWeave.Backbone

/-!
# CoverWeave, C12: the decision chain of Phase 1a (combinatorial core)

Source: `CoverWeave_R1/sections/04-formaleng.tex:178`, label `prop:mischain`, "MIS decision chain":
"On a lossless channel under the synchronous scheduler, Phase 1a needs R+1 rounds, where R is
its realized decision depth, and R ≤ L ≤ n-1, where L is the length of the longest
key-increasing path in Ĝ*."

The proof defines the depth `d(v) = 0` without a smaller-key neighbor, `1 + min d(u)` over the
smaller-key MIS neighbors if there is one, and `1 + max d(u)` over the smaller-key neighbors
otherwise. This file defines that depth on the key order and proves the core:
* `depth_ready`: the decision of a node depends only on nodes of smaller depth (the
  dependency the round count rests on),
* `exists_keyIncreasing_walk_depth`: every node `v` is the end of a key-increasing walk of
  length `d v`, so `R = max d ≤ L` (`depth_le_of_keyPath_bound`),
* `depth_lt_card`: `d v ≤ n - 1`,
* `depth_pathGraph`: on a path with increasing keys `d i = i`, so the bound is attained.

Not formalized: "Phase 1a needs R+1 rounds". It needs the synchronous execution model
(one step per slot, a frame read in the next slot, records, barrier) that the text does not fix
(inventory E7). The proof itself only argues "decides by round d+1", an upper bound.
-/

namespace SwarmInfer.CoverWeave

open SimpleGraph Finset

variable {V K : Type*} [LinearOrder K] [Fintype V]

open Classical in
/-- One step of the depth recursion, given the depths `r` of the other nodes. -/
noncomputable def depthStep (G : SimpleGraph V) (key : V → K) (v : V) (r : V → ℕ) : ℕ :=
  if hM : ((univ.filter fun u => G.Adj u v ∧ key u < key v).filter
      fun u => keyGreedy G key u).Nonempty then
    1 + ((univ.filter fun u => G.Adj u v ∧ key u < key v).filter
      fun u => keyGreedy G key u).inf' hM r
  else if (univ.filter fun u => G.Adj u v ∧ key u < key v).Nonempty then
    1 + (univ.filter fun u => G.Adj u v ∧ key u < key v).sup r
  else 0

open Classical in
/-- The decision depth `d(v)` of the proof of `prop:mischain`. -/
noncomputable def depth (G : SimpleGraph V) (key : V → K) : V → ℕ :=
  (keyLt_wf key).fix fun v rec =>
    depthStep G key v fun u => if h : keyLt key u v then rec u h else 0

theorem depthStep_congr (G : SimpleGraph V) (key : V → K) (v : V) {r r' : V → ℕ}
    (h : ∀ u, G.Adj u v → key u < key v → r u = r' u) :
    depthStep G key v r = depthStep G key v r' := by
  unfold depthStep
  split_ifs with h1 h2
  · congr 1
    exact Finset.inf'_congr _ rfl fun u hu => by
      simp only [mem_filter, mem_univ, true_and] at hu
      exact h u hu.1.1 hu.1.2
  · congr 1
    exact Finset.sup_congr rfl fun u hu => by
      simp only [mem_filter, mem_univ, true_and] at hu
      exact h u hu.1 hu.2
  · rfl

/-- The defining equation of the depth. -/
theorem depth_eq (G : SimpleGraph V) (key : V → K) (v : V) :
    depth G key v = depthStep G key v (depth G key) := by
  unfold depth
  rw [WellFounded.fix_eq]
  exact depthStep_congr G key v fun u _ hlt => by simp [keyLt, hlt]

/-- Three cases of the depth, as in the proof. -/
theorem depth_cases (G : SimpleGraph V) (key : V → K) (v : V) :
    ((¬ ∃ u, G.Adj u v ∧ key u < key v) ∧ depth G key v = 0) ∨
    ((∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u) ∧
      ∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u ∧ depth G key v = depth G key u + 1) ∨
    ((∃ u, G.Adj u v ∧ key u < key v) ∧
      (¬ ∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u) ∧
      (∀ u, G.Adj u v → key u < key v → depth G key u < depth G key v) ∧
      ∃ u, G.Adj u v ∧ key u < key v ∧ depth G key v = depth G key u + 1) := by
  classical
  rw [depth_eq]
  unfold depthStep
  split_ifs with h1 h2
  · right; left
    obtain ⟨u, hu, he⟩ := Finset.exists_mem_eq_inf' h1 (depth G key)
    simp only [mem_filter, mem_univ, true_and] at hu
    refine ⟨⟨u, hu.1.1, hu.1.2, hu.2⟩, u, hu.1.1, hu.1.2, hu.2, ?_⟩
    rw [he]; ring
  · right; right
    have hM : ¬ ∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u := by
      rintro ⟨u, h₁, h₂, h₃⟩
      exact h1 ⟨u, by simp [h₁, h₂, h₃]⟩
    obtain ⟨u, hu, he⟩ := Finset.exists_mem_eq_sup _ h2 (depth G key)
    simp only [mem_filter, mem_univ, true_and] at hu
    refine ⟨⟨u, hu.1, hu.2⟩, hM, fun u' h₁ h₂ => ?_, u, hu.1, hu.2, ?_⟩
    · have : depth G key u' ≤ _ := Finset.le_sup (f := depth G key)
        (by simp [h₁, h₂] : u' ∈ univ.filter fun u => G.Adj u v ∧ key u < key v)
      omega
    · rw [he]; ring
  · left
    refine ⟨fun ⟨u, h₁, h₂⟩ => h2 ⟨u, by simp [h₁, h₂]⟩, rfl⟩

/-- The decision of `v` depends only on nodes of smaller depth: a node with a smaller-key MIS
neighbor has one of smaller depth (the one whose decision makes it OUT), and otherwise all its
smaller-key neighbors have smaller depth (it decides once all of them decided). -/
theorem depth_ready (G : SimpleGraph V) (key : V → K) (v : V) :
    ((∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u) →
      ∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u ∧ depth G key u < depth G key v) ∧
    ((¬ ∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u) →
      ∀ u, G.Adj u v → key u < key v → depth G key u < depth G key v) := by
  rcases depth_cases G key v with ⟨h0, -⟩ | ⟨hM, u, h₁, h₂, h₃, he⟩ | ⟨-, hM, hall, -⟩
  · exact ⟨fun ⟨u, h₁, h₂, _⟩ => absurd ⟨u, h₁, h₂⟩ h0,
      fun _ u h₁ h₂ => absurd ⟨u, h₁, h₂⟩ h0⟩
  · exact ⟨fun _ => ⟨u, h₁, h₂, h₃, by omega⟩, fun h => absurd hM h⟩
  · exact ⟨fun h => absurd h hM, fun _ => hall⟩

/-- A node of positive depth has a smaller-key neighbor of depth one less. -/
theorem depth_step (G : SimpleGraph V) (key : V → K) (v : V) :
    depth G key v = 0 ∨ ∃ u, G.Adj u v ∧ key u < key v ∧ depth G key v = depth G key u + 1 := by
  rcases depth_cases G key v with ⟨-, h⟩ | ⟨-, u, h₁, h₂, -, he⟩ | ⟨-, -, -, u, h₁, h₂, he⟩
  · exact Or.inl h
  · exact Or.inr ⟨u, h₁, h₂, he⟩
  · exact Or.inr ⟨u, h₁, h₂, he⟩

/-- A walk is key-increasing when the keys strictly increase along its vertex list. -/
def KeyIncreasing {G : SimpleGraph V} (key : V → K) {u v : V} (p : G.Walk u v) : Prop :=
  p.support.Pairwise fun a b => key a < key b

/-- **Proposition `prop:mischain`, core part `R ≤ L`.** Every node `v` is the end of a
key-increasing walk of length `d v`.

Modelling choices:
* Ĝ* is a `SimpleGraph` on a `Fintype`, the key is any map into a linear order,
* the MIS membership used by the depth is the key-greedy set `keyGreedy G key` (C2),
* a key-increasing path of length `L` is a walk of length `L` whose vertex keys strictly
  increase (such a walk is a path, `KeyIncreasing.isPath`).

Added hypotheses: none. -/
theorem exists_keyIncreasing_walk_depth (G : SimpleGraph V) (key : V → K) (v : V) :
    ∃ (x : V) (p : G.Walk x v), KeyIncreasing key p ∧ p.length = depth G key v := by
  -- induction on the depth, building the walk backwards from `v`
  suffices h : ∀ n v, depth G key v = n →
      ∃ (x : V) (p : G.Walk v x), (p.support.Pairwise fun a b => key b < key a) ∧ p.length = n by
    obtain ⟨x, p, hp, hl⟩ := h _ v rfl
    refine ⟨x, p.reverse, ?_, by simpa using hl⟩
    unfold KeyIncreasing
    rw [Walk.support_reverse, List.pairwise_reverse]
    exact hp
  intro n
  induction n with
  | zero => exact fun v _ => ⟨v, Walk.nil, by simp, rfl⟩
  | succ n ih =>
    intro v hv
    rcases depth_step G key v with h | ⟨u, hadj, hlt, he⟩
    · omega
    · obtain ⟨x, p, hp, hl⟩ := ih u (by omega)
      refine ⟨x, Walk.cons hadj.symm p, ?_, by simp [hl]⟩
      rw [Walk.support_cons, List.pairwise_cons]
      refine ⟨fun a ha => ?_, hp⟩
      -- every vertex of `p` has key at most `key u`
      have hle : key a ≤ key u := by
        cases p with
        | nil => simp at ha; rw [ha]
        | cons h q =>
          rw [Walk.support_cons, List.mem_cons] at ha
          rcases ha with rfl | ha
          · exact le_rfl
          · rw [Walk.support_cons, List.pairwise_cons] at hp
            exact (hp.1 a ha).le
      exact lt_of_le_of_lt hle hlt

omit [Fintype V] in
/-- A key-increasing walk is a path. -/
theorem KeyIncreasing.isPath {G : SimpleGraph V} {key : V → K} {u v : V} {p : G.Walk u v}
    (hp : KeyIncreasing key p) : p.IsPath :=
  Walk.IsPath.mk' (hp.imp fun h heq => by subst heq; exact lt_irrefl _ h)

/-- `R ≤ L`: if every key-increasing walk has length at most `L`, every depth is at most `L`. -/
theorem depth_le_of_keyPath_bound (G : SimpleGraph V) (key : V → K) (L : ℕ)
    (hL : ∀ (x y : V) (p : G.Walk x y), KeyIncreasing key p → p.length ≤ L) (v : V) :
    depth G key v ≤ L := by
  obtain ⟨x, p, hp, hl⟩ := exists_keyIncreasing_walk_depth G key v
  exact hl ▸ hL x v p hp

/-- `L ≤ n - 1`: a key-increasing walk has fewer than `n` edges, hence `d v ≤ n - 1`. -/
theorem keyIncreasing_length_lt (G : SimpleGraph V) (key : V → K) {x y : V} (p : G.Walk x y)
    (hp : KeyIncreasing key p) : p.length < Fintype.card V :=
  hp.isPath.length_lt

theorem depth_lt_card (G : SimpleGraph V) (key : V → K) (v : V) :
    depth G key v < Fintype.card V := by
  obtain ⟨x, p, hp, hl⟩ := exists_keyIncreasing_walk_depth G key v
  exact hl ▸ keyIncreasing_length_lt G key p hp

/-- Tightness: on the path `0 — 1 — … — (n-1)` with key `i`, the depth of node `i` is `i`, so
`R = n - 1`. -/
theorem depth_pathGraph (n : ℕ) (i : Fin n) :
    depth (pathGraph n) (fun j : Fin n => (j : ℕ)) i = i := by
  induction' h : (i : ℕ) using Nat.strong_induction_on with m ih generalizing i
  rcases depth_step (pathGraph n) (fun j : Fin n => (j : ℕ)) i with h0 | ⟨u, hadj, hlt, he⟩
  · rw [h0]
    rcases Nat.eq_zero_or_pos m with hm | hm
    · omega
    · exfalso
      have hlt' : (i : ℕ) - 1 < n := by omega
      rcases depth_cases (pathGraph n) (fun j : Fin n => (j : ℕ)) i with ⟨hno, -⟩ | h | h
      · exact hno ⟨⟨i - 1, hlt'⟩, by rw [pathGraph_adj]; simp; omega, by simp; omega⟩
      · obtain ⟨-, u, -, -, -, he⟩ := h; omega
      · obtain ⟨-, -, -, u, -, -, he⟩ := h; omega
  · rw [pathGraph_adj] at hadj
    have hu : (u : ℕ) + 1 = i := by omega
    rw [he, ih u (by omega) u rfl]
    omega

end SwarmInfer.CoverWeave

#print axioms SwarmInfer.CoverWeave.depth_ready
#print axioms SwarmInfer.CoverWeave.exists_keyIncreasing_walk_depth
#print axioms SwarmInfer.CoverWeave.depth_le_of_keyPath_bound
#print axioms SwarmInfer.CoverWeave.depth_lt_card
#print axioms SwarmInfer.CoverWeave.depth_pathGraph
