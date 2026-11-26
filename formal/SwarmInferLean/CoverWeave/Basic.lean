import Mathlib

/-!
# CoverWeave: shared definitions (inventory E1, E2, E5)

Definition MWCCVC (`CoverWeave_R1/sections/04-formaleng.tex`, label `def:mwccvc`). For a graph
`G = (V, E)`, a capacity `k` and a set `C ⊆ V`, an assignment `owner : E → C` is valid together
with `C` if

1. every edge has an endpoint in `C` (`IsVertexCover`),
2. `G[C]` is connected,
3. `owner e` is an endpoint of `e` lying in `C`,
4. `ℓ(v) = |{e | owner e = v}| ≤ k` at every `v ∈ C` (`load`).

Conditions 3 and 4 alone form the Hall-type ownership condition of a fixed `C` (inventory E5),
here `IsOwnerMap`. `ValidPair` is the conjunction of all four.

Modelling choices, fixed once for every CoverWeave file:
* `G : SimpleGraph V` with `[Fintype V] [DecidableEq V] [DecidableRel G.Adj]`; edges are the
  elements of the subtype `G.edgeSet`, and `m` is `G.edgeFinset.card`.
* `owner` is a function `G.edgeSet → V`; "lands in `C`" is part of `IsOwnerMap`, not of its type,
  so that owner maps for different `C` have the same type.
* The weight `w` does not enter validity, only the objective, so `ValidPair` takes no weight;
  the objective is `weight w C`. Connectivity of `G` itself is a hypothesis of the theorems that
  need it, not part of `ValidPair`.
* Empty cover and one-vertex graphs. Connectivity of `G[C]` is Mathlib's `Connected`, which
  requires a nonempty vertex type. Hence `∅` is never a connected vertex cover, even when `G`
  has no edges (`not_isConnectedVertexCover_empty`). On a one-vertex graph the valid pairs are
  exactly `({v}, owner)` and the optimum is 1 (`isConnectedVertexCover_singleton_bot`). This is
  the reading in which `G[C]` is a nonempty connected graph, and it agrees with the paper on
  every graph with an edge, where `C = ∅` is not a cover anyway. The paper's results that would
  differ (C13 assumes `n ≥ 2`) state their own hypotheses.
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {V : Type*} [Fintype V] [DecidableEq V] (G : SimpleGraph V) [DecidableRel G.Adj]

/-- `C` is a vertex cover: every edge has an endpoint in `C` (condition 1 of `def:mwccvc`). -/
def IsVertexCover (C : Finset V) : Prop :=
  ∀ ⦃u v : V⦄, G.Adj u v → u ∈ C ∨ v ∈ C

/-- Connected vertex cover (inventory E2): a vertex cover whose induced subgraph is connected.
Mathlib's `Connected` includes nonemptiness, so `∅` never qualifies. -/
def IsConnectedVertexCover (C : Finset V) : Prop :=
  IsVertexCover G C ∧ (G.induce (C : Set V)).Connected

/-- The load `ℓ(v)` of `v` under `owner`: the number of edges that `owner` gives to `v`. -/
def load (owner : G.edgeSet → V) (v : V) : ℕ :=
  #{e : G.edgeSet | owner e = v}

/-- Ownership condition for a fixed `C` (inventory E5, conditions 3 and 4 of `def:mwccvc`):
every edge goes to one of its endpoints in `C`, and no node of `C` owns more than `k` edges. -/
def IsOwnerMap (k : ℕ) (C : Finset V) (owner : G.edgeSet → V) : Prop :=
  (∀ e : G.edgeSet, owner e ∈ (e : Sym2 V) ∧ owner e ∈ C) ∧ ∀ v ∈ C, load G owner v ≤ k

/-- Valid pair (inventory E1, Definition MWCCVC): `C` is a connected vertex cover and `owner` is
an owner map for `C` with capacity `k`. -/
def ValidPair (k : ℕ) (C : Finset V) (owner : G.edgeSet → V) : Prop :=
  IsConnectedVertexCover G C ∧ IsOwnerMap G k C owner

/-- Objective of MWCCVC: the weight `∑_{v ∈ C} w(v)` of the cover. -/
def weight (w : V → ℝ) (C : Finset V) : ℝ :=
  ∑ v ∈ C, w v

variable {G}

/-- Outside `C` an owner map gives no edge to anybody. -/
theorem IsOwnerMap.load_eq_zero {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : IsOwnerMap G k C owner) {v : V} (hv : v ∉ C) : load G owner v = 0 := by
  rw [load, card_eq_zero, filter_eq_empty_iff]
  rintro e - rfl
  exact hv (h.1 e).2

/-- An owner map respects the capacity at every node, not only on `C`. -/
theorem IsOwnerMap.load_le {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : IsOwnerMap G k C owner) (v : V) : load G owner v ≤ k := by
  by_cases hv : v ∈ C
  · exact h.2 v hv
  · simp [h.load_eq_zero hv]

/-- Condition 1 of `def:mwccvc` follows from condition 3. -/
theorem IsOwnerMap.isVertexCover {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : IsOwnerMap G k C owner) : IsVertexCover G C := by
  intro u v huv
  obtain ⟨hmem, hC⟩ := h.1 ⟨s(u, v), huv⟩
  rcases Sym2.mem_iff.mp hmem with h' | h'
  · exact Or.inl (h' ▸ hC)
  · exact Or.inr (h' ▸ hC)

omit [Fintype V] [DecidableEq V] [DecidableRel G.Adj] in
/-- The empty set is never a connected vertex cover (decision for `C = ∅`). -/
theorem not_isConnectedVertexCover_empty : ¬ IsConnectedVertexCover G ∅ := by
  rintro ⟨-, hc⟩
  obtain ⟨⟨v, hv⟩⟩ := hc.nonempty
  simp at hv

/-- On the one-vertex graph, `{0}` is a connected vertex cover (decision for `n = 1`). -/
theorem isConnectedVertexCover_singleton_bot :
    IsConnectedVertexCover (⊥ : SimpleGraph (Fin 1)) {0} := by
  refine ⟨fun u v h => absurd h (by simp), ?_⟩
  rw [SimpleGraph.connected_iff]
  exact ⟨fun a b => by rw [Subsingleton.elim a b], ⟨⟨0, by simp⟩⟩⟩

end SwarmInfer.CoverWeave
