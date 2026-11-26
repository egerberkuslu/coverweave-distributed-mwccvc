import SwarmInferLean.CoverWeave.Ownership
import SwarmInferLean.CoverWeave.CheckRuntime

/-!
# CoverWeave: the owner map by augmenting paths, with a step count (inventory C1, part 4)

Source: CoverWeave R1 manuscript, `sections/04-formaleng.tex:16` (Theorem `thm:hardness`, last
sentence): "For fixed `C`, a valid owner map exists if and only if the flow network `𝒩(C)` …
carries a flow of value `m`, decided in `O(m²)` time", and its proof (line 24): "…an integral
flow of value `m`, found by `m` augmenting paths in `O(m²)` time, is a valid owner map."

`Ownership.lean` proves the existence part in Hall form (`exists_ownerMap_iff_hall`). This file
formalizes the algorithm. The edges are assigned one after the other. For a new edge `e` the
algorithm searches, from the ends of `e` in `C`, the nodes reachable by alternating moves
"`x` owns `e'`, the other end `y` of `e'` is in `C`, move `e'` from `x` to `y`". If a reached node
has spare capacity (load `< k`), the moves along the stored path are applied from that node back
to an end `x₀` of `e`, each move keeping every load `≤ k`, and `e` goes to `x₀`. Otherwise the
algorithm stops and reports that no owner map exists. This is one augmenting path per edge in
`𝒩(C)`: source → `x_e` → `x₀` → … → spare node → sink. The `k` slots of a node are
interchangeable, so the search runs on the nodes of `C` with capacity `k`, as the arcs of
capacity `k` of `𝒩(C)` do, not on `C × Fin k`.

Results:
* `ownerFlow_some`: a returned map is an owner map (conditions 3 and 4 of `def:mwccvc`),
* `ownerFlow_none`: if the algorithm stops, no owner map exists, proved by exhibiting a set of
  edges that violates the Hall condition of `exists_ownerMap_iff_hall`,
* `ownerFlow_of_hall`: under the Hall condition the algorithm assigns all `m` edges,
* `ownerFlow_steps_le`: at most `m (2m + 3n)` steps, that is `O(m (n + m))`,
* `ownerFlow_steps_le_sq`: on a connected graph (`n ≤ m + 1`) at most `8 m²` steps, the paper's
  `O(m²)`.

Cost model (one step each), with adjacency lists `AdjRep G`, a load counter per node, owner and
membership arrays: in the search, popping a node and reading one incident edge of it
(`SearchRuntime.lean`); reading one visited node in the scan for a spare node; applying one move
of the path; assigning the new edge.
-/

namespace SwarmInfer.CoverWeave

open Finset

variable {V : Type*} [Fintype V] [DecidableEq V] {G : SimpleGraph V} [DecidableRel G.Adj]

/-- Load of `v` counted only on the assigned edges `A`. -/
def loadOn (A : Finset G.edgeSet) (o : G.edgeSet → V) (v : V) : ℕ := #(A.filter (o · = v))

/-- The partial assignment `o` on `A` respects conditions 3 and 4 of `def:mwccvc`. -/
def PartialOK (k : ℕ) (C : Finset V) (A : Finset G.edgeSet) (o : G.edgeSet → V) : Prop :=
  (∀ e ∈ A, o e ∈ (e : Sym2 V) ∧ o e ∈ C) ∧ ∀ v ∈ C, loadOn A o v ≤ k

/-- Arcs of the search: from `x` along an assigned edge `e'` that `x` owns, to its other end
`y ∈ C`. -/
abbrev okArc (A : Finset G.edgeSet) (owner : G.edgeSet → V) (C : Finset V) :
    V → G.edgeSet → V → Prop :=
  fun x e' y => e' ∈ A ∧ owner e' = x ∧ y ∈ C

/-- Apply the moves of a path, newest first: the edge of the arc `x → y` goes to `y`, then
continue from `x`. Returns the new map and the node reached (an end of the new edge). -/
def shift : (G.edgeSet → V) → V → List (V × G.edgeSet × V) → (G.edgeSet → V) × V
  | cur, y, [] => (cur, y)
  | cur, y, (x, e', _) :: π => shift (Function.update cur e' y) x π

/-- The search for a new edge `e`. -/
noncomputable def flowSearch (R : AdjRep G) (C : Finset V) (A : Finset G.edgeSet)
    (owner : G.edgeSet → V) (e : G.edgeSet) : Search.St V G.edgeSet :=
  Search.search R.inc (okArc A owner C) (endsIn C e)

/-- One augmentation: search, scan the visited nodes for a spare one, apply the moves of its path
and assign `e`. Returns the new map (`none` if no spare node is reached) and the steps. -/
noncomputable def augment (R : AdjRep G) (k : ℕ) (C : Finset V) (A : Finset G.edgeSet)
    (owner : G.edgeSet → V) (e : G.edgeSet) : Option (G.edgeSet → V) × ℕ :=
  match (flowSearch R C A owner e).vis.toList.find? (fun z => decide (loadOn A owner z < k)) with
  | none => (none, (flowSearch R C A owner e).cnt + #(flowSearch R C A owner e).vis)
  | some z =>
    (some (Function.update (shift owner z ((flowSearch R C A owner e).lab z)).1 e
        (shift owner z ((flowSearch R C A owner e).lab z)).2),
      (flowSearch R C A owner e).cnt + #(flowSearch R C A owner e).vis +
        ((flowSearch R C A owner e).lab z).length + 1)

/-- Assign the edges of a list one after the other; stop at the first failure. -/
noncomputable def flowLoop (R : AdjRep G) (k : ℕ) (C : Finset V) :
    List G.edgeSet → Finset G.edgeSet → (G.edgeSet → V) → ℕ → Option (G.edgeSet → V) × ℕ
  | [], _, owner, c => (some owner, c)
  | e :: es, A, owner, c =>
    match augment R k C A owner e with
    | (none, c') => (none, c + c')
    | (some o, c') => flowLoop R k C es (insert e A) o (c + c')

/-- **The owner map by augmenting paths.** Runs over the edge list of `R` from the empty
assignment (the initial values of the map are never read). -/
noncomputable def ownerFlow (R : AdjRep G) (k : ℕ) (C : Finset V) : Option (G.edgeSet → V) × ℕ :=
  flowLoop R k C R.edges ∅ (fun e => (Quot.out (e : Sym2 V)).1) 0

/-! ### Loads under one move and one new edge -/

omit [Fintype V] [DecidableRel G.Adj] in
theorem loadOn_update (A : Finset G.edgeSet) (cur : G.edgeSet → V) {e' : G.edgeSet}
    (he : e' ∈ A) (y v : V) :
    loadOn A (Function.update cur e' y) v + (if cur e' = v then 1 else 0) =
      loadOn A cur v + (if y = v then 1 else 0) := by
  simp only [loadOn, card_filter]
  rw [← add_sum_erase A _ he, ← add_sum_erase A _ he, Function.update_self]
  have : ∑ x ∈ A.erase e', (if Function.update cur e' y x = v then 1 else 0) =
      ∑ x ∈ A.erase e', (if cur x = v then 1 else 0) :=
    sum_congr rfl fun x hx => by rw [Function.update_of_ne (ne_of_mem_erase hx)]
  rw [this]; ring

omit [Fintype V] [DecidableRel G.Adj] in
theorem loadOn_insert (A : Finset G.edgeSet) (cur : G.edgeSet → V) {e : G.edgeSet}
    (he : e ∉ A) (x v : V) :
    loadOn (insert e A) (Function.update cur e x) v = loadOn A cur v + (if x = v then 1 else 0) := by
  simp only [loadOn, card_filter]
  rw [sum_insert he, Function.update_self, add_comm]
  congr 1
  exact sum_congr rfl fun y hy => by rw [Function.update_of_ne (ne_of_mem_of_not_mem hy he)]

/-! ### Paths of the search -/

omit [Fintype V] [DecidableEq V] in
theorem pathNodes_head {α : Type*} (y : V) :
    ∀ π : List (V × α × V), ∃ t, Search.pathNodes y π = y :: t
  | [] => ⟨[], rfl⟩
  | (x, _, _) :: π => ⟨Search.pathNodes x π, rfl⟩

omit [Fintype V] [DecidableEq V] in
theorem pathNodes_length {α : Type*} :
    ∀ (y : V) (π : List (V × α × V)), (Search.pathNodes y π).length = π.length + 1
  | _, [] => rfl
  | _, (x, _, _) :: π => by simp [Search.pathNodes, pathNodes_length x π]

omit [Fintype V] [DecidableRel G.Adj] in
theorem arcPath_mem_C (R : AdjRep G) {C : Finset V} {A : Finset G.edgeSet} {owner : G.edgeSet → V}
    {e : G.edgeSet} {y : V} {π : List (V × G.edgeSet × V)}
    (h : Search.ArcPath R.inc (okArc A owner C) (endsIn C e) y π) : y ∈ C := by
  rcases π with _ | ⟨⟨x, e', z⟩, π⟩
  · simp only [Search.ArcPath, endsIn, mem_filter] at h; exact h.1
  · exact h.2.2.1.2.2

omit [Fintype V] [DecidableRel G.Adj] in
/-- **Applying the moves of a path keeps every load `≤ k` and frees capacity at its start.** -/
theorem shift_spec (R : AdjRep G) {k : ℕ} {C : Finset V} {A : Finset G.edgeSet}
    {owner₀ : G.edgeSet → V} {e : G.edgeSet} :
    ∀ (π : List (V × G.edgeSet × V)) (y : V) (cur : G.edgeSet → V),
      Search.ArcPath R.inc (okArc A owner₀ C) (endsIn C e) y π →
      (Search.pathNodes y π).Nodup → PartialOK k C A cur → y ∈ C → loadOn A cur y < k →
      (∀ e'' ∈ A, owner₀ e'' ∈ (Search.pathNodes y π).tail → cur e'' = owner₀ e'') →
      PartialOK k C A (shift cur y π).1 ∧ (shift cur y π).2 ∈ endsIn C e ∧
        loadOn A (shift cur y π).1 (shift cur y π).2 < k
  | [], y, cur, hp, _, hok, _, hy, _ => ⟨hok, hp, hy⟩
  | (x, e', z) :: π, y, cur, hp, hnd, hok, hyC, hy, hag => by
    obtain ⟨-, hinc, ⟨he'A, hown, -⟩, hπ⟩ := hp
    simp only [Search.pathNodes, List.tail_cons] at hnd hag
    obtain ⟨hyπ, hndπ⟩ := List.nodup_cons.mp hnd
    obtain ⟨t, ht⟩ := pathNodes_head x π
    have hxπ : x ∈ Search.pathNodes x π := by rw [ht]; exact List.mem_cons_self ..
    have hcur : cur e' = x := by rw [hag e' he'A (hown ▸ hxπ), hown]
    have hxy : x ≠ y := fun h => hyπ (h ▸ hxπ)
    have hxC : x ∈ C := hcur ▸ (hok.1 e' he'A).2
    have hmem := (R.mem_inc x e' y).mp hinc
    have hl := fun v => loadOn_update A cur he'A y v
    rw [hcur] at hl
    set cur' := Function.update cur e' y with hcur'
    have hok' : PartialOK k C A cur' := by
      refine ⟨fun f hf => ?_, fun v hv => ?_⟩
      · by_cases hfe : f = e'
        · subst hfe
          rw [hcur', Function.update_self, hmem.2]
          exact ⟨Sym2.mem_mk_right _ _, hyC⟩
        · rw [hcur', Function.update_of_ne hfe]; exact hok.1 f hf
      · have := hl v; have := hok.2 v hv
        by_cases h1 : x = v <;> by_cases h2 : y = v <;> simp_all
        omega
    refine shift_spec R π x cur' hπ hndπ hok' hxC ?_ ?_
    · have := hl x; simp only [Ne.symm hxy, ite_true, ite_false] at this
      have := hok.2 x hxC; omega
    · intro f hf hft
      rw [ht, List.tail_cons] at hft
      have hne : f ≠ e' := by
        rintro rfl
        rw [ht] at hndπ
        exact (List.nodup_cons.mp hndπ).1 (hown ▸ hft)
      rw [hcur', Function.update_of_ne hne]
      exact hag f hf (by rw [ht]; exact List.mem_cons_of_mem _ hft)

/-! ### One augmentation -/

/-- **One augmentation is correct.** If a spare node is reached, the new map is a partial owner
map on `insert e A`. If none is reached, the edges owned by visited nodes together with `e`
violate the Hall condition, so no owner map exists. The steps are at most `2m + 3n`. -/
theorem augment_spec (R : AdjRep G) (k : ℕ) (C : Finset V) (A : Finset G.edgeSet)
    (owner : G.edgeSet → V) (e : G.edgeSet) (he : e ∉ A) (hinv : PartialOK k C A owner) :
    (∀ o, (augment R k C A owner e).1 = some o → PartialOK k C (insert e A) o) ∧
      ((augment R k C A owner e).1 = none → ¬ ∃ o, IsOwnerMap G k C o) ∧
      (augment R k C A owner e).2 ≤ 2 * #G.edgeFinset + 3 * Fintype.card V := by
  set st := flowSearch R C A owner e with hst
  have hcnt : st.cnt ≤ 2 * #G.edgeFinset + Fintype.card V := by
    have h1 := Search.search_cnt_le (succ := R.inc) (ok := okArc A owner C) (endsIn C e)
    have h2 : ∑ x, ((R.inc x).length + 1) = 2 * #G.edgeFinset + Fintype.card V := by
      simp [R.inc_length, sum_add_distrib, SimpleGraph.sum_degrees_eq_twice_card_edges G]
    rw [hst, flowSearch]; omega
  have hvis : #st.vis ≤ Fintype.card V := card_le_univ _
  have hvisC : ∀ z ∈ st.vis, z ∈ C := fun z hz =>
    arcPath_mem_C R (Search.search_label (succ := R.inc) (ok := okArc A owner C) _ hz).1
  rcases hf : st.vis.toList.find? (fun z => decide (loadOn A owner z < k)) with _ | z
  · -- no spare node: Hall violation
    have hres : augment R k C A owner e = (none, st.cnt + #st.vis) := by
      simp only [augment, ← hst, hf]
    rw [hres]
    refine ⟨fun o h => absurd h (by simp), fun _ => ?_, by simp only; omega⟩
    have hfull : ∀ z ∈ st.vis, loadOn A owner z = k := by
      intro z hz
      have := List.find?_eq_none.mp hf z (mem_toList.mpr hz)
      simp only [decide_eq_true_eq, not_lt] at this
      exact le_antisymm (hinv.2 z (hvisC z hz)) this
    rw [exists_ownerMap_iff_hall]
    intro hall
    set F := insert e (A.filter (fun f => owner f ∈ st.vis)) with hF
    have hsub : F.biUnion (endsIn C) ⊆ st.vis := by
      intro x hx
      obtain ⟨f, hfF, hxf⟩ := mem_biUnion.mp hx
      rcases mem_insert.mp hfF with rfl | hfA
      · exact Search.search_start (succ := R.inc) (ok := okArc A owner C) _ hxf
      · obtain ⟨hfA, hfv⟩ := mem_filter.mp hfA
        obtain ⟨hxC, hxf⟩ := mem_filter.mp hxf
        obtain ⟨y, hy⟩ := Sym2.mem_iff_exists.mp (hinv.1 f hfA).1
        rw [hy, Sym2.mem_iff] at hxf
        rcases hxf with rfl | rfl
        · exact hfv
        · have hadj : G.Adj (owner f) x := by
            have := f.2; rw [hy] at this; exact (SimpleGraph.mem_edgeSet G).mp this
          exact Search.search_closed (succ := R.inc) (ok := okArc A owner C) _ hfv
            ((R.mem_inc _ f x).mpr ⟨hadj, hy⟩) ⟨hfA, rfl, hxC⟩
    have hcardF : #F = k * #st.vis + 1 := by
      have heF : e ∉ A.filter (fun f => owner f ∈ st.vis) := fun h => he (mem_filter.mp h).1
      rw [hF, card_insert_of_notMem heF,
        card_eq_sum_card_fiberwise (s := A.filter (fun f => owner f ∈ st.vis)) (f := owner)
          (t := st.vis) (fun f hf => (mem_filter.mp (mem_coe.mp hf)).2)]
      congr 1
      rw [mul_comm, ← smul_eq_mul, ← sum_const]
      refine sum_congr rfl fun z hz => ?_
      rw [← hfull z hz, loadOn, filter_filter]
      congr 1
      ext f; simp only [mem_filter]
      constructor
      · rintro ⟨h1, -, h2⟩; exact ⟨h1, h2⟩
      · rintro ⟨h1, h2⟩; exact ⟨h1, h2 ▸ hz, h2⟩
    have := hall F
    have := Nat.mul_le_mul_left k (card_le_card hsub)
    omega
  · -- a spare node `z`: apply the moves of its path and assign `e`
    have hz : z ∈ st.vis := mem_toList.mp (List.mem_of_find?_eq_some hf)
    have hzk : loadOn A owner z < k := by
      have := List.find?_some hf; simpa using this
    obtain ⟨hp, hnd, hin⟩ := Search.search_label (succ := R.inc) (ok := okArc A owner C) _ hz
    obtain ⟨hok, hend, hsp⟩ := shift_spec R (k := k) (st.lab z) z owner hp hnd hinv (hvisC z hz)
      hzk (fun _ _ _ => rfl)
    set r := shift owner z (st.lab z) with hr
    have hres : augment R k C A owner e =
        (some (Function.update r.1 e r.2), st.cnt + #st.vis + (st.lab z).length + 1) := by
      simp only [augment, ← hst, hf, hr]
    rw [hres]
    have hlen : (st.lab z).length + 1 ≤ Fintype.card V := by
      rw [← pathNodes_length z]; exact hnd.length_le_card
    refine ⟨fun o ho => ?_, fun h => absurd h (by simp), by simp only; omega⟩
    simp only [Option.some.injEq] at ho
    subst ho
    obtain ⟨hr2C, hr2e⟩ := mem_filter.mp hend
    refine ⟨fun f hf => ?_, fun v hv => ?_⟩
    · rcases mem_insert.mp hf with rfl | hfA
      · rw [Function.update_self]; exact ⟨hr2e, hr2C⟩
      · rw [Function.update_of_ne (ne_of_mem_of_not_mem hfA he)]; exact hok.1 f hfA
    · rw [loadOn_insert A r.1 he]
      have := hok.2 v hv
      split_ifs with h
      · subst h; omega
      · omega

/-! ### The loop over all edges -/

theorem flowLoop_spec (R : AdjRep G) (k : ℕ) (C : Finset V) :
    ∀ (es : List G.edgeSet) (A : Finset G.edgeSet) (owner : G.edgeSet → V) (c : ℕ),
      PartialOK k C A owner → es.Nodup → (∀ e ∈ es, e ∉ A) → (∀ e, e ∈ A ∨ e ∈ es) →
      (∀ o, (flowLoop R k C es A owner c).1 = some o → IsOwnerMap G k C o) ∧
      ((flowLoop R k C es A owner c).1 = none → ¬ ∃ o, IsOwnerMap G k C o) ∧
      (flowLoop R k C es A owner c).2 ≤
        c + es.length * (2 * #G.edgeFinset + 3 * Fintype.card V)
  | [], A, owner, c, hinv, _, _, hall => by
    have hA : A = univ := eq_univ_iff_forall.mpr fun e => (hall e).resolve_right (by simp)
    subst hA
    refine ⟨fun o ho => ?_, fun h => absurd h (by simp [flowLoop]), by simp [flowLoop]⟩
    simp only [flowLoop, Option.some.injEq] at ho
    subst ho
    exact ⟨fun e => hinv.1 e (mem_univ e), hinv.2⟩
  | e :: es, A, owner, c, hinv, hnd, hdis, hall => by
    have heA := hdis e (List.mem_cons_self ..)
    obtain ⟨h1, h2, h3⟩ := augment_spec R k C A owner e heA hinv
    rcases hres : augment R k C A owner e with ⟨_ | o, c'⟩
    · rw [hres] at h2 h3
      simp only [flowLoop, hres]
      refine ⟨fun o h => absurd h (by simp), fun _ => h2 rfl, ?_⟩
      simp only [List.length_cons] at h3 ⊢
      nlinarith
    · rw [hres] at h1 h3
      simp only [flowLoop, hres]
      have ih := flowLoop_spec R k C es (insert e A) o (c + c') (h1 o rfl)
        (List.nodup_cons.mp hnd).2
        (fun f hf hfA => by
          rcases mem_insert.mp hfA with rfl | hfA
          · exact (List.nodup_cons.mp hnd).1 hf
          · exact hdis f (List.mem_cons_of_mem _ hf) hfA)
        (fun f => by
          rcases hall f with h | h
          · exact Or.inl (mem_insert_of_mem h)
          · rcases List.mem_cons.mp h with rfl | h
            · exact Or.inl (mem_insert_self _ _)
            · exact Or.inr h)
      refine ⟨ih.1, ih.2.1, ?_⟩
      have := ih.2.2
      simp only [List.length_cons] at h3 ⊢
      nlinarith

/-! ### Main results -/

theorem ownerFlow_spec (R : AdjRep G) (k : ℕ) (C : Finset V) :
    (∀ o, (ownerFlow R k C).1 = some o → IsOwnerMap G k C o) ∧
      ((ownerFlow R k C).1 = none → ¬ ∃ o, IsOwnerMap G k C o) ∧
      (ownerFlow R k C).2 ≤ #G.edgeFinset * (2 * #G.edgeFinset + 3 * Fintype.card V) := by
  have h := flowLoop_spec R k C R.edges ∅ (fun e => (Quot.out (e : Sym2 V)).1) 0
    ⟨by simp, fun v _ => by simp [loadOn]⟩ R.edges_nodup (by simp) (fun e => Or.inr (R.mem_edges e))
  have hm : R.edges.length = #G.edgeFinset := by rw [R.edges_length, SimpleGraph.edgeFinset_card]
  rw [hm, zero_add] at h
  exact h

/-- **Theorem (Hardness), part (4), the algorithm is correct: a returned map is an owner map**
(C1 part 4). Every map returned by `ownerFlow` satisfies conditions 3 and 4 of `def:mwccvc`.

Modelling choices:
* adjacency lists `R : AdjRep G` (exist for every graph, `AdjRep.ofGraph`), `C` a `Finset`,
* the flow network `𝒩(C)` is not built: an augmenting path of `𝒩(C)` is a path of the search
  over the nodes of `C` (see the module docstring), and the integral flow of value `m` is the
  owner map,
* the algorithm stops at the first edge it cannot assign; `ownerFlow_none` shows that this
  happens only when no owner map exists, so stopping loses nothing.
Added hypotheses: none. -/
theorem ownerFlow_some (R : AdjRep G) (k : ℕ) (C : Finset V) (o : G.edgeSet → V)
    (h : (ownerFlow R k C).1 = some o) : IsOwnerMap G k C o :=
  (ownerFlow_spec R k C).1 o h

/-- **If the algorithm stops, no owner map exists** (C1 part 4). -/
theorem ownerFlow_none (R : AdjRep G) (k : ℕ) (C : Finset V) (h : (ownerFlow R k C).1 = none) :
    ¬ ∃ o, IsOwnerMap G k C o :=
  (ownerFlow_spec R k C).2.1 h

/-- **Under the Hall condition the algorithm assigns all `m` edges** (C1 part 4): it returns an
owner map. With `exists_ownerMap_iff_hall` this is the flow test of the paper. -/
theorem ownerFlow_of_hall (R : AdjRep G) (k : ℕ) (C : Finset V)
    (hall : ∀ F : Finset G.edgeSet, #F ≤ k * #(F.biUnion (endsIn C))) :
    ∃ o, (ownerFlow R k C).1 = some o ∧ IsOwnerMap G k C o := by
  rcases h : (ownerFlow R k C).1 with _ | o
  · exact absurd ((exists_ownerMap_iff_hall k C).mpr hall) (ownerFlow_none R k C h)
  · exact ⟨o, rfl, ownerFlow_some R k C o h⟩

/-- The decision form: the algorithm succeeds iff an owner map exists. -/
theorem ownerFlow_isSome_iff (R : AdjRep G) (k : ℕ) (C : Finset V) :
    (ownerFlow R k C).1.isSome ↔ ∃ o, IsOwnerMap G k C o := by
  rcases h : (ownerFlow R k C).1 with _ | o
  · simp only [Option.isSome_none, Bool.false_eq_true, false_iff]
    exact ownerFlow_none R k C h
  · simp only [Option.isSome_some, true_iff]
    exact ⟨o, ownerFlow_some R k C o h⟩

/-- **The step bound `O(m (n + m))`** (C1 part 4): at most `m (2m + 3n)` steps. -/
theorem ownerFlow_steps_le (R : AdjRep G) (k : ℕ) (C : Finset V) :
    (ownerFlow R k C).2 ≤ #G.edgeFinset * (2 * #G.edgeFinset + 3 * Fintype.card V) :=
  (ownerFlow_spec R k C).2.2

omit [DecidableEq V] in
/-- A connected graph has `n ≤ m + 1`, the link the paper's `O(m²)` needs. -/
theorem card_le_card_edgeFinset_add_one (hG : G.Connected) :
    Fintype.card V ≤ #G.edgeFinset + 1 := by
  have := hG.card_vert_le_card_edgeSet_add_one
  rwa [Nat.card_eq_fintype_card, Nat.card_eq_fintype_card, ← SimpleGraph.edgeFinset_card] at this

/-- **The paper's `O(m²)`** (C1 part 4): on a connected graph the algorithm takes at most `8 m²`
steps.

Hypothesis from the source, not added: `G` connected, as `def:mwccvc` assumes. The proof uses it
only through `n ≤ m + 1` (`card_le_card_edgeFinset_add_one`), the link the paper leaves implicit.
The bound `O(m (n + m))` of `ownerFlow_steps_le` holds for every graph. -/
theorem ownerFlow_steps_le_sq (R : AdjRep G) (k : ℕ) (C : Finset V) (hG : G.Connected) :
    (ownerFlow R k C).2 ≤ 8 * #G.edgeFinset ^ 2 := by
  have h1 := ownerFlow_steps_le R k C
  have h2 := card_le_card_edgeFinset_add_one hG
  have h3 : #G.edgeFinset ≤ #G.edgeFinset ^ 2 := by nlinarith
  calc (ownerFlow R k C).2 ≤ #G.edgeFinset * (2 * #G.edgeFinset + 3 * (#G.edgeFinset + 1)) :=
        h1.trans (Nat.mul_le_mul_left _ (by omega))
    _ ≤ 8 * #G.edgeFinset ^ 2 := by nlinarith

end SwarmInfer.CoverWeave

#print axioms SwarmInfer.CoverWeave.ownerFlow_some
#print axioms SwarmInfer.CoverWeave.ownerFlow_none
#print axioms SwarmInfer.CoverWeave.ownerFlow_of_hall
#print axioms SwarmInfer.CoverWeave.ownerFlow_isSome_iff
#print axioms SwarmInfer.CoverWeave.ownerFlow_steps_le
#print axioms SwarmInfer.CoverWeave.ownerFlow_steps_le_sq
