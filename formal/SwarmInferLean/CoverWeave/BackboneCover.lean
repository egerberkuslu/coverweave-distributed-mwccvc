import SwarmInferLean.CoverWeave.BackboneDomination

/-!
# CoverWeave, C3 and C4: cover connectivity, cover and connectivity (combinatorial cores)

Sources: `CoverWeave_R1/sections/04-formaleng.tex`
* line 57, label `lem:conn`, "Cover connectivity" (C3): "If Ĝ* is connected, then Ĝ*[C] is
  connected in a silent configuration", with `C` the nodes whose role is MIS, CONNECTOR or COVER;
* line 65, label `lem:cover`, "Cover and connectivity" (C4): "In a silent configuration on a
  connected Ĝ*, C contains the backbone B of MIS and CONNECTOR nodes and is a connected vertex
  cover."

The proofs reduce connectivity to two bridging properties of MIS pairs:
* (D2) every MIS pair at distance 2 has a common neighbor in `C` (`Gap2Bridged`),
* (D3) every MIS pair at distance 3 has a path `a — x — y — b` with `x, y ∈ C`, or a detour
  through a further MIS node at distance 2 from both ends (`Gap3Bridged`).

What is proved here:
* `induce_connected_of_bridged`: for any dominating set `I ⊆ C` of a connected graph, (D2) and
  (D3) give `G[C]` connected (the path-chaining argument of the proof, first sentence);
* `gap2Bridged_of_phase1b`: (D2) follows from the Phase 1b rule read as a property of the final
  configuration (the global minimum-key common neighbor is promoted, although rival sets are
  local);
* `gap3Bridged_of_gap3Rule`: (D3) follows from the Gap3 rule read as a property of the final
  configuration at both ends of the middle edge (the case analysis of the last three
  sentences of the proof);
* `lem_conn_core`, `lem_cover_core`: the two statements for the key-greedy MIS set;
* `lem_conn_false_one_node`: for `n = 1` the lemma is false under the convention that the
  empty graph is not connected.

Not formalized (inventory E7): that a silent configuration of the distributed run satisfies
the three rule properties used as hypotheses. This is where the proofs have holes: the
Phase 1b rule runs once, and the text does not show that the records of `a` and `b` already
show MIS when it runs, nor that the Gap3 rule (which runs "from Phase 2 on") and the Phase 2
rule are still evaluated, on fresh records, in the phases reached at silence.
-/

namespace SwarmInfer.CoverWeave

open SimpleGraph

variable {V K : Type*} [LinearOrder K]

/-- `a` and `b` lie in `C` and are joined by a path inside `G[C]`. -/
def CReach (G : SimpleGraph V) (C : Set V) (a b : V) : Prop :=
  ∃ (ha : a ∈ C) (hb : b ∈ C), (G.induce C).Reachable ⟨a, ha⟩ ⟨b, hb⟩

theorem CReach.refl {G : SimpleGraph V} {C : Set V} {a : V} (ha : a ∈ C) : CReach G C a a :=
  ⟨ha, ha, Reachable.refl _⟩

theorem CReach.trans {G : SimpleGraph V} {C : Set V} {a b c : V} (h₁ : CReach G C a b)
    (h₂ : CReach G C b c) : CReach G C a c := by
  obtain ⟨ha, hb, r₁⟩ := h₁
  obtain ⟨hb', hc, r₂⟩ := h₂
  exact ⟨ha, hc, r₁.trans r₂⟩

theorem CReach.symm {G : SimpleGraph V} {C : Set V} {a b : V} (h : CReach G C a b) :
    CReach G C b a := by
  obtain ⟨ha, hb, r⟩ := h
  exact ⟨hb, ha, r.symm⟩

theorem CReach.of_adj {G : SimpleGraph V} {C : Set V} {a b : V} (ha : a ∈ C) (hb : b ∈ C)
    (h : G.Adj a b) : CReach G C a b :=
  ⟨ha, hb, Adj.reachable (G := G.induce C) (u := ⟨a, ha⟩) (v := ⟨b, hb⟩) h⟩

/-- (D2): every pair of `I` at distance 2 has a common neighbor in `C`. -/
def Gap2Bridged (G : SimpleGraph V) (I C : Set V) : Prop :=
  ∀ a ∈ I, ∀ b ∈ I, a ≠ b → ¬ G.Adj a b → (∃ z, G.Adj a z ∧ G.Adj z b) →
    ∃ x ∈ C, G.Adj a x ∧ G.Adj x b

/-- (D3): every pair of `I` at distance 3 has a path `a — x — y — b` with both inner nodes in
`C`, or with a detour: an `a' ∈ I` adjacent to `x` that shares a neighbor with `b`, or a
`b' ∈ I` adjacent to `y` that shares a neighbor with `a`. -/
def Gap3Bridged (G : SimpleGraph V) (I C : Set V) : Prop :=
  ∀ a ∈ I, ∀ b ∈ I, ¬ G.Adj a b → (¬ ∃ z, G.Adj a z ∧ G.Adj z b) →
    (∃ x y, G.Adj a x ∧ G.Adj x y ∧ G.Adj y b) →
    ∃ x y, G.Adj a x ∧ G.Adj x y ∧ G.Adj y b ∧
      ((x ∈ C ∧ y ∈ C) ∨ (∃ a' ∈ I, G.Adj x a' ∧ ∃ u, G.Adj u a' ∧ G.Adj u b) ∨
        (∃ b' ∈ I, G.Adj y b' ∧ ∃ u, G.Adj u b' ∧ G.Adj u a))

section Chaining

variable {G : SimpleGraph V} {I C : Set V}

/-- Two nodes of `I` within distance 2 are joined inside `G[C]`. -/
theorem creach_of_within2 (hIC : I ⊆ C) (h2 : Gap2Bridged G I C) {a b : V} (ha : a ∈ I)
    (hb : b ∈ I) (h : a = b ∨ G.Adj a b ∨ ∃ z, G.Adj a z ∧ G.Adj z b) : CReach G C a b := by
  by_cases hab : a = b
  · subst hab; exact CReach.refl (hIC ha)
  by_cases hadj : G.Adj a b
  · exact CReach.of_adj (hIC ha) (hIC hb) hadj
  have hz : ∃ z, G.Adj a z ∧ G.Adj z b := by tauto
  obtain ⟨x, hx, hax, hxb⟩ := h2 a ha b hb hab hadj hz
  exact (CReach.of_adj (hIC ha) hx hax).trans (CReach.of_adj hx (hIC hb) hxb)

/-- Two nodes of `I` that dominate the two ends of an edge are joined inside `G[C]`. -/
theorem creach_of_dominated_edge (hIC : I ⊆ C) (h2 : Gap2Bridged G I C)
    (h3 : Gap3Bridged G I C) {a b v w : V} (ha : a ∈ I) (hb : b ∈ I)
    (hav : a = v ∨ G.Adj a v) (hvw : G.Adj v w) (hwb : w = b ∨ G.Adj w b) :
    CReach G C a b := by
  by_cases hnear : a = b ∨ G.Adj a b ∨ ∃ z, G.Adj a z ∧ G.Adj z b
  · exact creach_of_within2 hIC h2 ha hb hnear
  push Not at hnear
  obtain ⟨hab, hadj, hz⟩ := hnear
  have hz' : ¬ ∃ z, G.Adj a z ∧ G.Adj z b := fun ⟨z, h₁, h₂⟩ => hz z h₁ h₂
  have hpath : ∃ x y, G.Adj a x ∧ G.Adj x y ∧ G.Adj y b := by
    rcases hav with rfl | hav
    · rcases hwb with rfl | hwb
      · exact absurd hvw hadj
      · exact absurd hwb (hz w hvw)
    · rcases hwb with rfl | hwb
      · exact absurd hvw (hz v hav)
      · exact ⟨v, w, hav, hvw, hwb⟩
  obtain ⟨x, y, hax, hxy, hyb, hcase⟩ := h3 a ha b hb hadj hz' hpath
  rcases hcase with ⟨hx, hy⟩ | ⟨a', ha', hxa', u, hua', hub⟩ | ⟨b', hb', hyb', u, hub', hua⟩
  · exact ((CReach.of_adj (hIC ha) hx hax).trans (CReach.of_adj hx hy hxy)).trans
      (CReach.of_adj hy (hIC hb) hyb)
  · exact (creach_of_within2 hIC h2 ha ha' (Or.inr (Or.inr ⟨x, hax, hxa'⟩))).trans
      (creach_of_within2 hIC h2 ha' hb (Or.inr (Or.inr ⟨u, hua'.symm, hub⟩)))
  · exact (creach_of_within2 hIC h2 ha hb' (Or.inr (Or.inr ⟨u, hua.symm, hub'⟩))).trans
      (creach_of_within2 hIC h2 hb' hb (Or.inr (Or.inr ⟨y, hyb'.symm, hyb⟩)))

/-- Chaining along a walk: dominators of the two ends of a walk are joined inside `G[C]`. -/
theorem creach_of_walk (hIC : I ⊆ C) (hdom : ∀ v, v ∈ I ∨ ∃ a ∈ I, G.Adj a v)
    (h2 : Gap2Bridged G I C) (h3 : Gap3Bridged G I C) {v w : V} (p : G.Walk v w) :
    ∀ m m', m ∈ I → (m = v ∨ G.Adj m v) → m' ∈ I → (m' = w ∨ G.Adj m' w) →
      CReach G C m m' := by
  induction p with
  | nil =>
    intro m m' hm hmv hm' hm'v
    apply creach_of_within2 hIC h2 hm hm'
    rcases hmv with rfl | hmv
    · rcases hm'v with rfl | hm'v
      · exact Or.inl rfl
      · exact Or.inr (Or.inl hm'v.symm)
    · rcases hm'v with rfl | hm'v
      · exact Or.inr (Or.inl hmv)
      · exact Or.inr (Or.inr ⟨_, hmv, hm'v.symm⟩)
  | cons hadj p ih =>
    rename_i x y z
    intro m m' hm hmv hm' hm'w
    obtain ⟨m'', hm'', hm''y⟩ : ∃ m'' ∈ I, m'' = y ∨ G.Adj m'' y := by
      rcases hdom y with h | ⟨a, ha, h⟩
      · exact ⟨y, h, Or.inl rfl⟩
      · exact ⟨a, ha, Or.inr h⟩
    have hyx : y = m'' ∨ G.Adj y m'' := by
      rcases hm''y with h | h
      · exact Or.inl h.symm
      · exact Or.inr h.symm
    exact (creach_of_dominated_edge hIC h2 h3 hm hm'' hmv hadj hyx).trans
      (ih m'' m' hm'' hm''y hm' hm'w)

/-- **Core of `lem:conn` (C3), graph form.** In a connected graph, let `I ⊆ C` dominate every
vertex. If every pair of `I` at distance 2 and every pair at distance 3 is bridged as in (D2)
and (D3), then `G[C]` is connected.

Modelling choices:
* Ĝ* is a `SimpleGraph` (finiteness is not needed for this step),
* "distance 2" is read as "distinct, not adjacent, with a common neighbor", and "distance 3"
  as "not adjacent, no common neighbor, joined by a walk of length 3" (equivalent readings),
* the detour case of the proof ("a neighbor of x bridges b and an MIS neighbor a' of x") is
  weakened: the bridging node need not be a neighbor of `x`.

Added hypotheses: none. `I` is only required to dominate every vertex, which a maximal
independent set does (`Maximal.dominates`); independence is not used in this step. -/
theorem induce_connected_of_bridged (hG : G.Connected) (hIC : I ⊆ C)
    (hdom : ∀ v, v ∈ I ∨ ∃ a ∈ I, G.Adj a v) (h2 : Gap2Bridged G I C)
    (h3 : Gap3Bridged G I C) : (G.induce C).Connected := by
  have dom : ∀ v, ∃ m ∈ I, m = v ∨ G.Adj m v := fun v => by
    rcases hdom v with h | ⟨a, ha, h⟩
    · exact ⟨v, h, Or.inl rfl⟩
    · exact ⟨a, ha, Or.inr h⟩
  have hdomC : ∀ c ∈ C, ∃ m ∈ I, CReach G C m c := fun c hc => by
    obtain ⟨m, hm, h⟩ := dom c
    rcases h with rfl | h
    · exact ⟨m, hm, CReach.refl hc⟩
    · exact ⟨m, hm, CReach.of_adj (hIC hm) hc h⟩
  obtain ⟨v₀⟩ := hG.nonempty
  obtain ⟨m₀, hm₀, -⟩ := dom v₀
  refine (connected_iff _).2 ⟨fun c₁ c₂ => ?_, ⟨⟨m₀, hIC hm₀⟩⟩⟩
  obtain ⟨m₁, hm₁, r₁⟩ := hdomC c₁ c₁.2
  obtain ⟨m₂, hm₂, r₂⟩ := hdomC c₂ c₂.2
  obtain ⟨p⟩ := hG.preconnected m₁ m₂
  have hm : CReach G C m₁ m₂ :=
    creach_of_walk hIC hdom h2 h3 p m₁ m₂ hm₁ (Or.inl rfl) hm₂ (Or.inl rfl)
  obtain ⟨_, _, r⟩ := (r₁.symm.trans hm).trans r₂
  exact r

end Chaining

section Rules

variable {G : SimpleGraph V} {I C : Set V}

/-- The Phase 1b connector rule (Algorithm `alg:connector`, procedure `Connector`) read as a
property of the final configuration: a node adjacent to two distinct MIS nodes `a, b` whose key
is below the key of every neighbor that also lists both (its rival set) is in `C`. The MIS lists
`𝓜(u)` are read as the true MIS neighbors of `u`. -/
def Phase1bRule (G : SimpleGraph V) (key : V → K) (I C : Set V) : Prop :=
  ∀ v, ∀ a ∈ I, ∀ b ∈ I, a ≠ b → G.Adj v a → G.Adj v b →
    (∀ u, G.Adj v u → G.Adj u a → G.Adj u b → key v < key u) → v ∈ C

/-- The Gap3 rule (Algorithm `alg:connector`, procedure `Gap3`) read as a property of a silent
final configuration at a bridge node `x ∉ I`: for a neighbor `y` of `x` that lists an MIS node
`b` not adjacent to `x`, and no neighbor of `x` that lists `b` together with an MIS neighbor of
`x`, the node `y` is in `C` (otherwise `y` is OUT, the rule fires and the JOIN is open, so the
configuration is not silent). -/
def Gap3Rule (G : SimpleGraph V) (I C : Set V) : Prop :=
  ∀ x ∉ I, ∀ y, G.Adj x y → ∀ b ∈ I, G.Adj y b → ¬ G.Adj x b →
    (¬ ∃ a ∈ I, G.Adj x a ∧ ∃ u, G.Adj x u ∧ G.Adj u a ∧ G.Adj u b) → y ∈ C

/-- (D2) from the Phase 1b rule: the global minimum-key common neighbor of an MIS pair at
distance 2 sees only rivals with larger keys, so it is promoted. -/
theorem gap2Bridged_of_phase1b [Fintype V] {key : V → K} (hkey : Function.Injective key)
    (hP : Phase1bRule G key I C) : Gap2Bridged G I C := by
  classical
  intro a ha b hb hab _ hz
  let S := Finset.univ.filter fun z => G.Adj a z ∧ G.Adj z b
  have hS : S.Nonempty := by
    obtain ⟨z, hz⟩ := hz
    exact ⟨z, by simp [S, hz]⟩
  obtain ⟨x, hxS, hmin⟩ := S.exists_min_image key hS
  simp only [S, Finset.mem_filter, Finset.mem_univ, true_and] at hxS hmin
  refine ⟨x, hP x a ha b hb hab hxS.1.symm hxS.2 fun u hxu hua hub => ?_, hxS⟩
  exact lt_of_le_of_ne (hmin u ⟨hua.symm, hub⟩) (hkey.ne hxu.ne)

/-- (D3) from the Gap3 rule at both ends of the middle edge: at `x` either a detour exists or
`y ∈ C`, at `y` either a detour exists or `x ∈ C`. -/
theorem gap3Bridged_of_gap3Rule (hI : G.IsIndepSet I) (hP : Gap3Rule G I C) :
    Gap3Bridged G I C := by
  intro a ha b hb _ hz hpath
  obtain ⟨x, y, hax, hxy, hyb⟩ := hpath
  refine ⟨x, y, hax, hxy, hyb, ?_⟩
  have hxI : x ∉ I := fun hx => hI ha hx hax.ne hax
  have hyI : y ∉ I := fun hy => hI hy hb hyb.ne hyb
  have hxb : ¬ G.Adj x b := fun h => hz ⟨x, hax, h⟩
  have hya : ¬ G.Adj y a := fun h => hz ⟨y, h.symm, hyb⟩
  by_cases hdx : ∃ a' ∈ I, G.Adj x a' ∧ ∃ u, G.Adj x u ∧ G.Adj u a' ∧ G.Adj u b
  · obtain ⟨a', ha', hxa', u, -, hua', hub⟩ := hdx
    exact Or.inr (Or.inl ⟨a', ha', hxa', u, hua', hub⟩)
  by_cases hdy : ∃ b' ∈ I, G.Adj y b' ∧ ∃ u, G.Adj y u ∧ G.Adj u b' ∧ G.Adj u a
  · obtain ⟨b', hb', hyb', u, -, hub', hua⟩ := hdy
    exact Or.inr (Or.inr ⟨b', hb', hyb', u, hub', hua⟩)
  exact Or.inl ⟨hP y hyI x hxy.symm a ha hax.symm hya hdy, hP x hxI y hxy b hb hyb hxb hdx⟩

end Rules

/-- **Lemma `lem:conn` (C3), core for the key-greedy MIS set.** Let Ĝ* be connected with at
least two nodes, let the MIS set be the key-greedy set, let `C` contain it, and let the final
configuration satisfy the Phase 1b rule and the Gap3 rule. Then `Ĝ*[C]` is connected.

Modelling choices:
* Ĝ* is a `SimpleGraph` on a `Fintype`, the key an injective map into a linear order,
* the MIS set after Phase 1a is `keyGreedy G key` (C2; that the run computes it is not
  formalized),
* "silent configuration" enters only through `Phase1bRule` and `Gap3Rule`, read on the true
  MIS neighborhoods (records assumed fresh). That a silent run satisfies them is not
  formalized: it needs the execution model, and the text leaves two steps unargued (the
  records of `a, b` show MIS when Phase 1b runs; the Gap3 rule is still evaluated at silence).

Added hypotheses:
* `2 ≤ Fintype.card V`: for `n = 1` the only node is OUT, `C = ∅`, and `G[∅]` is not connected
  (`lem_conn_false_one_node`). -/
theorem lem_conn_core [Fintype V] (G : SimpleGraph V) {key : V → K}
    (hkey : Function.Injective key) (hG : G.Connected) (hcard : 2 ≤ Fintype.card V)
    (C : Set V) (hIC : {v | keyGreedy G key v} ⊆ C) (h1b : Phase1bRule G key {v | keyGreedy G key v} C)
    (hg3 : Gap3Rule G {v | keyGreedy G key v} C) : (G.induce C).Connected := by
  have hmax := keyGreedy_maximal_of_connected G hkey hG hcard
  exact induce_connected_of_bridged hG hIC (Maximal.dominates hmax) (gap2Bridged_of_phase1b hkey h1b)
    (gap3Bridged_of_gap3Rule hmax.1 hg3)

/-- For `n = 1` the lemma fails: the key-greedy set is empty, `C = ∅` satisfies every rule
property vacuously, and `G[∅]` is not connected (Mathlib's `Connected` needs a vertex). -/
theorem lem_conn_false_one_node :
    let G : SimpleGraph (Fin 1) := ⊥
    let key : Fin 1 → ℕ := fun i => i
    G.Connected ∧ {v | keyGreedy G key v} ⊆ (∅ : Set (Fin 1)) ∧
      Phase1bRule G key {v | keyGreedy G key v} ∅ ∧ Gap3Rule G {v | keyGreedy G key v} ∅ ∧
      ¬ (G.induce (∅ : Set (Fin 1))).Connected := by
  intro G key
  refine ⟨lem_backbone_false_one_node.1, fun v hv => ?_, fun v a _ b _ _ h => h.elim,
    fun x _ y h => h.elim, fun h => ?_⟩
  · obtain ⟨u, hu⟩ := ((keyGreedy_iff G key v).1 hv).1
    exact hu.elim
  · obtain ⟨⟨_, hv⟩⟩ := h.nonempty
    exact hv

/-- Node roles of CoverWeave. -/
inductive Role
  | mis
  | connector
  | cover
  | out
  deriving DecidableEq

/-- The Phase 2 cover rule (Algorithm `alg:cover`, procedure `Cover`) read as a property of the
final configuration: no OUT node has an OUT neighbor with a larger key. -/
def Phase2Rule (G : SimpleGraph V) (key : V → K) (role : V → Role) : Prop :=
  ∀ u v, G.Adj u v → role v = .out → role u = .out → ¬ key v < key u

/-- Core of step 2 of `lem:cover`: with the Phase 2 rule and an injective key no edge has two
OUT ends, so the non-OUT nodes form a vertex cover. -/
theorem isVertexCover_of_phase2 (G : SimpleGraph V) {key : V → K}
    (hkey : Function.Injective key) (role : V → Role) (hP : Phase2Rule G key role) :
    G.IsVertexCover {v | role v ≠ .out} := by
  intro u v hadj
  by_contra h
  simp only [Set.mem_ofPred_eq, ne_eq, not_or, not_not] at h
  rcases lt_or_gt_of_ne (hkey.ne hadj.ne) with hlt | hlt
  · exact hP v u hadj.symm h.1 h.2 hlt
  · exact hP u v hadj h.2 h.1 hlt

/-- Core of step 3 of `lem:cover` (the Repair branch): if every node has reached phase 3 and
no OUT node has an OUT neighbor at phase 3 or later, the non-OUT nodes form a vertex cover. -/
theorem isVertexCover_of_repair (G : SimpleGraph V) (role : V → Role) (phase : V → ℕ)
    (hphase : ∀ v, 3 ≤ phase v)
    (hR : ∀ u v, G.Adj u v → role v = .out → role u = .out → ¬ 3 ≤ phase u) :
    G.IsVertexCover {v | role v ≠ .out} := by
  intro u v hadj
  by_contra h
  simp only [Set.mem_ofPred_eq, ne_eq, not_or, not_not] at h
  exact hR u v hadj h.2 h.1 (hphase u)

/-- **Theorem `lem:cover` (C4), core as a property of the final configuration.** Let Ĝ* be
connected with at least two nodes and let the final roles satisfy: the MIS nodes are the
key-greedy set, and the Phase 1b, Gap3 and Phase 2 rules hold. Then `C = {role ≠ OUT}` contains
the backbone `B` of MIS and CONNECTOR nodes and is a connected vertex cover.

Modelling choices: as in `lem_conn_core`; the configuration is a map `role : V → Role`, with
`C` the non-OUT nodes and `B` the MIS and CONNECTOR nodes.

Added hypotheses:
* `2 ≤ Fintype.card V`, as in `lem_conn_core`,
* `hmis`: the MIS role is the key-greedy set (the protocol part of C2, not formalized),
* `h2`: the Phase 2 rule holds at the end. The text runs Phase 2 once and argues the lossy case
  through Repair (step 3), without showing that both ends cannot leave phase 3 while seeing
  each other's stale roles. `isVertexCover_of_repair` gives the same conclusion from the Repair
  rule instead. -/
theorem lem_cover_core [Fintype V] (G : SimpleGraph V) {key : V → K}
    (hkey : Function.Injective key) (hG : G.Connected) (hcard : 2 ≤ Fintype.card V)
    (role : V → Role) (hmis : ∀ v, role v = .mis ↔ keyGreedy G key v)
    (h1b : Phase1bRule G key {v | keyGreedy G key v} {v | role v ≠ .out})
    (hg3 : Gap3Rule G {v | keyGreedy G key v} {v | role v ≠ .out})
    (h2 : Phase2Rule G key role) :
    {v | role v = .mis ∨ role v = .connector} ⊆ {v | role v ≠ .out} ∧
      G.IsVertexCover {v | role v ≠ .out} ∧ (G.induce {v | role v ≠ .out}).Connected := by
  refine ⟨fun v hv => ?_, isVertexCover_of_phase2 G hkey role h2, ?_⟩
  · rcases hv with h | h <;> simp [Set.mem_ofPred_eq, h]
  · refine lem_conn_core G hkey hG hcard _ (fun v hv => ?_) h1b hg3
    have : role v = .mis := (hmis v).2 hv
    simp [Set.mem_ofPred_eq, this]

/-- The hypotheses of `lem_cover_core` hold together: on the path `0 — 1 — 2` with key `i` the
key-greedy set is `{0, 2}`, and the roles MIS, CONNECTOR, MIS satisfy every rule. -/
example : ∃ role : Fin 3 → Role,
    (∀ v, role v = .mis ↔ keyGreedy (pathGraph 3) (fun i : Fin 3 => (i : ℕ)) v) ∧
    Phase1bRule (pathGraph 3) (fun i : Fin 3 => (i : ℕ))
      {v | keyGreedy (pathGraph 3) (fun i : Fin 3 => (i : ℕ)) v} {v | role v ≠ .out} ∧
    Gap3Rule (pathGraph 3) {v | keyGreedy (pathGraph 3) (fun i : Fin 3 => (i : ℕ)) v}
      {v | role v ≠ .out} ∧
    Phase2Rule (pathGraph 3) (fun i : Fin 3 => (i : ℕ)) role := by
  let G := pathGraph 3
  let key : Fin 3 → ℕ := fun i => i
  have h0 : keyGreedy G key 0 := (keyGreedy_iff G key 0).2
    ⟨⟨1, by simp [G, pathGraph_adj]⟩, fun u hu hlt => by simp [key] at hlt⟩
  have h1 : ¬ keyGreedy G key 1 := fun h =>
    ((keyGreedy_iff G key 1).1 h).2 0 (by simp [G, pathGraph_adj]) (by simp [key]) h0
  have h2 : keyGreedy G key 2 := (keyGreedy_iff G key 2).2
    ⟨⟨1, by simp [G, pathGraph_adj]⟩, fun u hu hlt => by
      rw [pathGraph_adj] at hu
      have : u = 1 := by fin_cases u <;> simp_all [key]
      subst this; exact h1⟩
  refine ⟨![.mis, .connector, .mis], fun v => ?_, ?_, ?_, ?_⟩
  · fin_cases v <;> simp <;> first | exact h0 | exact h1 | exact h2
  · intro v _ _ _ _ _ _ _ _; fin_cases v <;> simp
  · intro x _ y _ _ _ _ _ _; fin_cases y <;> simp
  · intro u v _ hv hu _
    fin_cases u <;> fin_cases v <;> simp_all

end SwarmInfer.CoverWeave

#print axioms SwarmInfer.CoverWeave.induce_connected_of_bridged
#print axioms SwarmInfer.CoverWeave.gap2Bridged_of_phase1b
#print axioms SwarmInfer.CoverWeave.gap3Bridged_of_gap3Rule
#print axioms SwarmInfer.CoverWeave.lem_conn_core
#print axioms SwarmInfer.CoverWeave.lem_conn_false_one_node
#print axioms SwarmInfer.CoverWeave.isVertexCover_of_phase2
#print axioms SwarmInfer.CoverWeave.isVertexCover_of_repair
#print axioms SwarmInfer.CoverWeave.lem_cover_core
