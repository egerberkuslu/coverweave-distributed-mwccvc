import Mathlib

/-!
# CoverWeave, shared definitions E3 and E4: the priority key and the key-greedy set

The CoverWeave paper (`CoverWeave_R1/sections/04-formaleng.tex`, line 13 and Definition
`def:key`) orders the nodes by `key(v) = (w(v)/(deg(v)+1), id(v))` in lexicographic order. The
identifier breaks ties, so the key is an injective map into a linear order. Here the key is
any map `key : V → K` into a linear order; injectivity is a separate hypothesis wherever it is
used.

Phase 1a (Algorithm `alg:mis`, `03-system.tex:63`) puts a node with no incident edge into OUT
and otherwise lets it join MIS exactly when no smaller-key neighbor joined. Read on a fixed
graph, this defines the key-greedy set by well-founded recursion on the key order:
`inS v ↔ (∃ u, G.Adj u v) ∧ ∀ u, G.Adj u v → key u < key v → ¬ inS u`.

Used by C2 (`BackboneDomination.lean`), C12 (`BackboneChain.lean`), C3 and C4
(`BackboneCover.lean`).
-/

namespace SwarmInfer.CoverWeave

variable {V K : Type*} [LinearOrder K]

/-- The strict key order on the nodes: `u` precedes `v` when its key is smaller. -/
def keyLt (key : V → K) (u v : V) : Prop := key u < key v

instance (key : V → K) : IsTrans V (keyLt key) := ⟨fun _ _ _ h₁ h₂ => lt_trans h₁ h₂⟩

instance (key : V → K) : Std.Irrefl (keyLt key) := ⟨fun a => lt_irrefl (key a)⟩

/-- On a finite node set the key order is well founded, whatever the order on `K`. -/
theorem keyLt_wf [Finite V] (key : V → K) : WellFounded (keyLt key) :=
  Finite.wellFounded_of_trans_of_irrefl _

/-- The key-greedy set (shared definition E4): a node is in it when it has an incident edge
and none of its smaller-key neighbors is in it. -/
def keyGreedy [Finite V] (G : SimpleGraph V) (key : V → K) (v : V) : Prop :=
  (keyLt_wf key).fix
    (fun v rec => (∃ u, G.Adj u v) ∧ ∀ u (h : keyLt key u v), G.Adj u v → ¬ rec u h) v

/-- The defining equation of the key-greedy set. -/
theorem keyGreedy_iff [Finite V] (G : SimpleGraph V) (key : V → K) (v : V) :
    keyGreedy G key v ↔
      (∃ u, G.Adj u v) ∧ ∀ u, G.Adj u v → key u < key v → ¬ keyGreedy G key u := by
  unfold keyGreedy
  rw [WellFounded.fix_eq]
  exact and_congr Iff.rfl ⟨fun h u hadj hlt => h u hlt hadj, fun h u hlt hadj => h u hadj hlt⟩

end SwarmInfer.CoverWeave
