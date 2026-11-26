import SwarmInferLean.CoverWeave.LowerBound

/-!
# CoverWeave: ownership and feasibility (inventory C1 parts 2 and 4, C5 part a)

* C1 part (2), `thm:hardness` (`04-formaleng.tex:15`), the combinatorial step of the proof:
  with `w ≡ 1`, `Δ(G) ≤ 4 ≤ k`, the valid pairs are exactly the connected vertex covers.
* C1 part (4) in Hall form (inventory E5): for a fixed `C` a valid owner map exists iff every
  set `F` of edges satisfies `|F| ≤ k · |ends of F in C|`. This replaces the flow network `𝒩(C)`.
* C5 part (a), `thm:cap` (`04-formaleng.tex:77`): for connected `G`, a valid pair exists iff
  `(V, owner)` is valid for some owner iff `|E(Y)| ≤ k|Y|` for all `Y ⊆ V` (Hakimi's orientation
  condition), and the two infeasibility certificates `m > nk`, `∑ min(deg v, k) < m`.
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {V : Type*} [Fintype V] [DecidableEq V] {G : SimpleGraph V} [DecidableRel G.Adj]

/-! ### Loads are bounded by degrees -/

/-- A node owns only edges at it, so its load is at most its degree. -/
theorem load_le_degree {owner : G.edgeSet → V} (hend : ∀ e : G.edgeSet, owner e ∈ (e : Sym2 V)) (v : V) :
    load G owner v ≤ G.degree v := by
  rw [load, ← SimpleGraph.card_incidenceFinset_eq_degree]
  refine card_le_card_of_injOn (fun e => (e : Sym2 V)) ?_ Subtype.val_injective.injOn
  intro e he
  simp only [coe_filter, mem_univ, true_and, Set.mem_ofPred_eq] at he
  rw [mem_coe, SimpleGraph.mem_incidenceFinset]
  exact ⟨e.2, he ▸ hend e⟩

omit [Fintype V] [DecidableEq V] [DecidableRel G.Adj] in
/-- Every edge has an endpoint in a vertex cover. -/
theorem IsVertexCover.exists_mem {C : Finset V} (hC : IsVertexCover G C) (e : G.edgeSet) :
    ∃ x, x ∈ (e : Sym2 V) ∧ x ∈ C := by
  obtain ⟨e, he⟩ := e
  induction e using Sym2.ind with
  | h u v =>
    rcases hC he with h | h
    · exact ⟨u, Sym2.mem_mk_left u v, h⟩
    · exact ⟨v, Sym2.mem_mk_right u v, h⟩

/-! ### C1 part (2) -/

/-- If the capacity is at least the maximum degree, every connected vertex cover carries a valid
owner map: give each edge to any endpoint in `C`. -/
theorem exists_validPair_iff_of_maxDegree_le {k : ℕ} (hk : G.maxDegree ≤ k) (C : Finset V) :
    (∃ owner, ValidPair G k C owner) ↔ IsConnectedVertexCover G C := by
  refine ⟨fun ⟨_, h⟩ => h.1, fun hC => ?_⟩
  choose owner hend hmem using hC.1.exists_mem
  exact ⟨owner, hC, fun e => ⟨hend e, hmem e⟩,
    fun v _ => (load_le_degree hend v).trans ((G.degree_le_maxDegree v).trans hk)⟩

/-- **Theorem (Hardness)**, part (2), combinatorial step, `thm:hardness`, inventory C1. With
unit weights, maximum degree at most 4 and `k ≥ 4`, a set `C` carries a valid owner map iff it is
a connected vertex cover. With `w ≡ 1` the objective is `|C|`, so MWCCVC on these instances is
minimum connected vertex cover.

Modelling choices:
* `ValidPair` carries no weight (see `Basic.lean`), so `w ≡ 1` only affects the objective and
  does not appear in the statement.
* Connectivity of `G` is not needed for this step and is not assumed.

Stays on paper: NP-hardness on planar and planar bipartite graphs of maximum degree 4 and
APX-hardness on bipartite ones (the cited results of Garey and Johnson, Fernau and Manlove, and
Escoffier et al.). The theorem is the reduction-correctness part: the identity map sends
connected vertex cover instances to MWCCVC instances with the same solutions. -/
theorem validPair_iff_connectedVertexCover_of_maxDegree_le_four (hΔ : G.maxDegree ≤ 4)
    {k : ℕ} (hk : 4 ≤ k) (C : Finset V) :
    (∃ owner, ValidPair G k C owner) ↔ IsConnectedVertexCover G C :=
  exists_validPair_iff_of_maxDegree_le (hΔ.trans hk) C

#print axioms validPair_iff_connectedVertexCover_of_maxDegree_le_four

/-! ### C1 part (4) in Hall form -/

/-- The endpoints of an edge that lie in `C`. -/
def endsIn (C : Finset V) (e : G.edgeSet) : Finset V :=
  {x ∈ C | x ∈ (e : Sym2 V)}

/-- **Theorem (Hardness)**, part (4) in Hall form, `thm:hardness`, inventory C1(4) and E5. For
a fixed `C`, an owner map satisfying conditions 3 and 4 of `def:mwccvc` exists iff every set `F`
of edges satisfies `|F| ≤ k · |N_C(F)|`, where `N_C(F)` is the set of endpoints in `C` of the
edges of `F`.

Modelling choices:
* The flow network `𝒩(C)` and its flow of value `m` are replaced by the Hall condition, which
  is the max-flow min-cut condition of that network. Proof by Mathlib's Hall theorem applied to
  edges and the `k` copies `C × Fin k` of the nodes of `C`.
* Stays on paper: the equivalence with the flow formulation and the `O(m²)` running time. -/
theorem exists_ownerMap_iff_hall (k : ℕ) (C : Finset V) :
    (∃ owner, IsOwnerMap G k C owner) ↔
      ∀ F : Finset G.edgeSet, #F ≤ k * #(F.biUnion (endsIn C)) := by
  constructor
  · rintro ⟨owner, h⟩ F
    refine (h.card_le_mul_card_image F).trans (Nat.mul_le_mul_left k (card_le_card ?_))
    intro v hv
    obtain ⟨e, he, rfl⟩ := mem_image.mp hv
    exact mem_biUnion.mpr ⟨e, he, mem_filter.mpr ⟨(h.1 e).2, (h.1 e).1⟩⟩
  · intro hall
    set t : G.edgeSet → Finset (V × Fin k) := fun e => endsIn C e ×ˢ univ
    have ht : ∀ F : Finset G.edgeSet, F.biUnion t = F.biUnion (endsIn C) ×ˢ univ := by
      intro F
      ext ⟨x, i⟩
      simp [t]
    obtain ⟨f, hinj, hf⟩ := (Finset.all_card_le_biUnion_card_iff_exists_injective t).mp
      (fun F => by rw [ht, card_product, card_univ, Fintype.card_fin, mul_comm]; exact hall F)
    have hf' : ∀ e, (f e).1 ∈ C ∧ (f e).1 ∈ (e : Sym2 V) := fun e => by
      have := hf e
      simp only [t, endsIn, mem_product, mem_filter, mem_univ, and_true] at this
      exact this
    refine ⟨fun e => (f e).1, fun e => ⟨(hf' e).2, (hf' e).1⟩, fun v _ => ?_⟩
    calc load G (fun e => (f e).1) v ≤ #(({v} : Finset V) ×ˢ (univ : Finset (Fin k))) := by
          refine card_le_card_of_injOn f ?_ hinj.injOn
          intro e he
          simp only [coe_filter, mem_univ, true_and, Set.mem_ofPred_eq] at he
          simp [← he]
      _ = k := by simp

#print axioms exists_ownerMap_iff_hall

/-! ### C5 part (a) -/

/-- `|E(Y)|`, the number of edges with both endpoints in `Y`. -/
def innerEdges (G : SimpleGraph V) [DecidableRel G.Adj] (Y : Finset V) : ℕ :=
  #{e : G.edgeSet | (e : Sym2 V) ∈ Y.sym2}

/-- An owner map for any `C` gives Hakimi's condition `|E(Y)| ≤ k|Y|` for every `Y`. -/
theorem IsOwnerMap.innerEdges_le {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : IsOwnerMap G k C owner) (Y : Finset V) : innerEdges G Y ≤ k * #Y := by
  refine (h.card_le_mul_card_image _).trans (Nat.mul_le_mul_left k (card_le_card ?_))
  intro v hv
  obtain ⟨e, he, rfl⟩ := mem_image.mp hv
  exact mem_sym2_iff.mp (mem_filter.mp he).2 _ (h.1 e).1

omit [DecidableEq V] [DecidableRel G.Adj] in
theorem isConnectedVertexCover_univ (hG : G.Connected) : IsConnectedVertexCover G univ := by
  refine ⟨fun u _ _ => Or.inl (mem_univ u), ?_⟩
  rw [coe_univ]
  exact (SimpleGraph.induceUnivIso G).connected_iff.mpr hG

/-- **Theorem (Feasibility and ownership)**, part (a), `thm:cap`, inventory C5. For connected
`G` the following are equivalent: (i) a valid pair exists, (ii) `(V, owner)` is valid for some
`owner`, (iii) every `Y ⊆ V` satisfies `|E(Y)| ≤ k|Y|`.

Modelling choices:
* `E(Y)` is `innerEdges G Y`, counted on the edge subtype.
* The fourth equivalent statement of the paper, a flow of value `m` in `𝒩(V)`, is not
  formalized; its role is taken by the Hall form `exists_ownerMap_iff_hall` with `C = V`, which
  the proof of (iii) ⇒ (ii) uses.
* Connectivity of `G` is used only in (i) ⇒ (ii) (for `G[V]` to be connected), as the inventory
  notes. -/
theorem feasible_tfae (hG : G.Connected) (k : ℕ) :
    List.TFAE [∃ C owner, ValidPair G k C owner,
      ∃ owner, ValidPair G k univ owner,
      ∀ Y : Finset V, innerEdges G Y ≤ k * #Y] := by
  tfae_have 1 → 2 := by
    rintro ⟨C, owner, h⟩
    exact ⟨owner, isConnectedVertexCover_univ hG,
      fun e => ⟨(h.2.1 e).1, mem_univ _⟩, fun v _ => h.2.load_le v⟩
  tfae_have 2 → 1 := fun ⟨owner, h⟩ => ⟨univ, owner, h⟩
  tfae_have 2 → 3 := fun ⟨_, h⟩ => h.2.innerEdges_le
  tfae_have 3 → 2 := by
    intro hY
    obtain ⟨owner, h⟩ := (exists_ownerMap_iff_hall (G := G) k univ).mpr fun F => by
      refine le_trans ?_ (hY (F.biUnion (endsIn univ)))
      refine card_le_card fun e he => mem_filter.mpr ⟨mem_univ e, mem_sym2_iff.mpr ?_⟩
      intro a ha
      exact mem_biUnion.mpr ⟨e, he, mem_filter.mpr ⟨mem_univ a, ha⟩⟩
    exact ⟨owner, isConnectedVertexCover_univ hG, h⟩
  tfae_finish

#print axioms feasible_tfae

/-- Under any owner map, `m ≤ ∑_v min(deg v, k)`: the ownable capacity bounds the edge count. -/
theorem IsOwnerMap.card_edgeFinset_le_sum_min {k : ℕ} {C : Finset V} {owner : G.edgeSet → V}
    (h : IsOwnerMap G k C owner) : #G.edgeFinset ≤ ∑ v, min (G.degree v) k := by
  rw [SimpleGraph.edgeFinset_card, ← card_univ,
    card_eq_sum_card_fiberwise (f := owner) (t := univ) (fun _ _ => mem_univ _)]
  exact sum_le_sum fun v _ =>
    le_min (load_le_degree (fun e => (h.1 e).1) v) (h.load_le v)

/-- **Theorem (Feasibility and ownership)**, part (a), degree-gap certificate: if
`∑_v min(deg v, k) < m`, no valid pair exists. No connectivity of `G` is needed. -/
theorem not_exists_validPair_of_sum_min_lt {k : ℕ}
    (hgap : ∑ v, min (G.degree v) k < #G.edgeFinset) :
    ¬ ∃ C owner, ValidPair G k C owner := by
  rintro ⟨C, owner, h⟩
  exact (h.2.card_edgeFinset_le_sum_min).not_gt hgap

omit [DecidableEq V] in
/-- `∑_v min(deg v, k) ≤ n k`. -/
theorem sum_min_degree_le (k : ℕ) : ∑ v, min (G.degree v) k ≤ Fintype.card V * k := by
  calc ∑ v, min (G.degree v) k ≤ ∑ _v : V, k := sum_le_sum fun v _ => min_le_right _ _
    _ = Fintype.card V * k := by simp

/-- **Theorem (Feasibility and ownership)**, part (a), counting certificate: if `m > nk`, no
valid pair exists. -/
theorem not_exists_validPair_of_card_mul_lt {k : ℕ}
    (hcount : Fintype.card V * k < #G.edgeFinset) :
    ¬ ∃ C owner, ValidPair G k C owner :=
  not_exists_validPair_of_sum_min_lt ((sum_min_degree_le k).trans_lt hcount)

#print axioms not_exists_validPair_of_sum_min_lt
#print axioms not_exists_validPair_of_card_mul_lt

end SwarmInfer.CoverWeave
