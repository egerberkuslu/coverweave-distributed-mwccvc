import Mathlib

/-!
# CoverWeave: a graph search with a step count (support for C1 parts 1 and 4)

A worklist search over a finite vertex type. Each vertex `x` has a list `succ x` of arcs
`(a, y)` (label `a`, target `y`), and an arc is followed only if `ok x a y` holds. The search
starts from a set `S`, keeps a visited set, a stack, and for each visited vertex the path by which
it was reached (newest arc first). It returns

* the visited set, which is exactly the set of vertices reachable from `S` by followed arcs
  (`search_mem_iff`),
* for each visited vertex a path from `S` with no repeated vertex (`search_label`),
* the number of steps, which is `∑_{x visited} (|succ x| + 1)` (`search_cnt`).

Cost model (one step each): popping a vertex from the stack, reading one arc of its list. The
test `ok`, the visited test, inserting into the visited set, pushing, and storing the path of a new
vertex (one `cons` onto the path of its parent, shared, as with parent pointers) are part of the
step of the arc read. This is the adjacency-list model of the paper's `O(n+m)` and of the
augmenting-path search.

The search runs `Fintype.card V` iterations; `search_stk` shows that the stack is then empty, so
this is enough (an iteration on an empty stack does nothing and costs nothing).

Used by `CheckRuntime.lean` (connectivity of `G[C]`) and `OwnerFlow.lean` (augmenting paths).
-/

namespace SwarmInfer.CoverWeave.Search

open Finset

variable {V α : Type*} [Fintype V] [DecidableEq V]

/-- State of the search: visited set, stack, the path of each visited vertex, step counter. -/
structure St (V α : Type*) where
  vis : Finset V
  stk : List V
  lab : V → List (V × α × V)
  cnt : ℕ

section Defs

variable (succ : V → List (α × V)) (ok : V → α → V → Prop) [∀ x a y, Decidable (ok x a y)]

/-- Read one arc `(a, y)` of `x`: if it is followed and `y` is new, visit `y`. One step. -/
def visit (x : V) (a : α) (y : V) (st : St V α) : St V α :=
  if ok x a y ∧ y ∉ st.vis then
    ⟨insert y st.vis, y :: st.stk, Function.update st.lab y ((x, a, y) :: st.lab x), st.cnt + 1⟩
  else ⟨st.vis, st.stk, st.lab, st.cnt + 1⟩

/-- Read a list of arcs of `x`. -/
def scanArcs (x : V) : List (α × V) → St V α → St V α
  | [], st => st
  | (a, y) :: rest, st => scanArcs x rest (visit ok x a y st)

/-- One iteration: pop a vertex (one step) and read all its arcs. -/
def step (st : St V α) : St V α :=
  match st.stk with
  | [] => st
  | x :: rest => scanArcs ok x (succ x) ⟨st.vis, rest, st.lab, st.cnt + 1⟩

/-- Start: `S` visited and on the stack, empty paths, no steps. -/
noncomputable def init (S : Finset V) : St V α := ⟨S, S.toList, fun _ => [], 0⟩

/-- The search: `Fintype.card V` iterations from `init S`. -/
noncomputable def search (S : Finset V) : St V α := (step succ ok)^[Fintype.card V] (init S)

/-- The vertices of a path ending at `y` (newest first). -/
def pathNodes : V → List (V × α × V) → List V
  | y, [] => [y]
  | y, (x, _, _) :: π => y :: pathNodes x π

/-- `π` is a path of followed arcs from a vertex of `S` to `y`, newest arc first. -/
def ArcPath (S : Finset V) : V → List (V × α × V) → Prop
  | y, [] => y ∈ S
  | y, (x, a, z) :: π => z = y ∧ (a, y) ∈ succ x ∧ ok x a y ∧ ArcPath S x π

/-- A followed arc from `x` to `y`. -/
def Arc (x y : V) : Prop := ∃ a, (a, y) ∈ succ x ∧ ok x a y

/-- A stored path is valid, has no repeated vertex and stays in the visited set. -/
def LabOK (S vis : Finset V) (y : V) (π : List (V × α × V)) : Prop :=
  ArcPath succ ok S y π ∧ (pathNodes y π).Nodup ∧ ∀ z ∈ pathNodes y π, z ∈ vis

/-- Vertices already popped and scanned. -/
def done (st : St V α) : Finset V := st.vis.filter (· ∉ st.stk)

/-- Invariant used while reading arcs. -/
def Pre (S : Finset V) (st : St V α) : Prop :=
  (∀ y ∈ st.stk, y ∈ st.vis) ∧ st.stk.Nodup ∧
    ∀ y ∈ st.vis, LabOK succ ok S st.vis y (st.lab y)

/-- Invariant between iterations. -/
def Inv (S : Finset V) (st : St V α) : Prop :=
  Pre succ ok S st ∧ S ⊆ st.vis ∧
    (∀ x ∈ done st, ∀ a y, (a, y) ∈ succ x → ok x a y → y ∈ st.vis) ∧
    st.cnt = ∑ x ∈ done st, ((succ x).length + 1)

end Defs

variable {succ : V → List (α × V)} {ok : V → α → V → Prop} [∀ x a y, Decidable (ok x a y)]

omit [Fintype V] [DecidableEq V] [∀ x a y, Decidable (ok x a y)] in
theorem LabOK.mono {S vis vis' : Finset V} {y : V} {π : List (V × α × V)}
    (h : LabOK succ ok S vis y π) (hv : vis ⊆ vis') : LabOK succ ok S vis' y π :=
  ⟨h.1, h.2.1, fun z hz => hv (h.2.2 z hz)⟩

omit [Fintype V] in
theorem visit_spec {S : Finset V} {x : V} {a : α} {y : V} {st : St V α}
    (hpre : Pre succ ok S st) (hx : x ∈ st.vis) (hxy : (a, y) ∈ succ x) :
    st.vis ⊆ (visit ok x a y st).vis ∧ Pre succ ok S (visit ok x a y st) ∧
      (ok x a y → y ∈ (visit ok x a y st).vis) ∧ done (visit ok x a y st) = done st ∧
      (visit ok x a y st).cnt = st.cnt + 1 := by
  obtain ⟨hsub, hnd, hlab⟩ := hpre
  unfold visit
  split_ifs with h
  · obtain ⟨hok, hy⟩ := h
    refine ⟨subset_insert _ _, ⟨?_, ?_, ?_⟩, fun _ => mem_insert_self _ _, ?_, rfl⟩
    · intro z hz
      rcases List.mem_cons.mp hz with rfl | hz
      · exact mem_insert_self _ _
      · exact mem_insert_of_mem (hsub z hz)
    · exact List.nodup_cons.mpr ⟨fun hy' => hy (hsub y hy'), hnd⟩
    · intro z hz
      dsimp only at hz ⊢
      by_cases hzy : z = y
      · subst hzy
        rw [Function.update_self]
        obtain ⟨hp, hn, hin⟩ := hlab x hx
        refine ⟨⟨rfl, hxy, hok, hp⟩, ?_, ?_⟩
        · exact List.nodup_cons.mpr ⟨fun hz' => hy (hin _ hz'), hn⟩
        · intro w hw
          rcases List.mem_cons.mp hw with rfl | hw
          · exact mem_insert_self _ _
          · exact mem_insert_of_mem (hin w hw)
      · rw [Function.update_of_ne hzy]
        exact (hlab z ((mem_insert.mp hz).resolve_left hzy)).mono (subset_insert _ _)
    · ext z
      simp only [done, mem_filter, mem_insert, List.mem_cons, not_or]
      constructor
      · rintro ⟨h1 | h1, h2, h3⟩
        · exact absurd h1 h2
        · exact ⟨h1, h3⟩
      · rintro ⟨h1, h3⟩
        exact ⟨Or.inr h1, fun h => hy (h ▸ h1), h3⟩
  · refine ⟨subset_rfl, ⟨hsub, hnd, hlab⟩, fun hok => ?_, rfl, rfl⟩
    by_contra hy
    exact h ⟨hok, hy⟩

omit [Fintype V] in
theorem scan_spec {S : Finset V} {x : V} :
    ∀ (rest : List (α × V)) (st : St V α), (∀ p ∈ rest, p ∈ succ x) →
      Pre succ ok S st → x ∈ st.vis →
      st.vis ⊆ (scanArcs ok x rest st).vis ∧ Pre succ ok S (scanArcs ok x rest st) ∧
      (∀ a y, (a, y) ∈ rest → ok x a y → y ∈ (scanArcs ok x rest st).vis) ∧
      done (scanArcs ok x rest st) = done st ∧
      (scanArcs ok x rest st).cnt = st.cnt + rest.length
  | [], st, _, hpre, _ => ⟨subset_rfl, hpre, by simp, rfl, rfl⟩
  | (a, y) :: rest, st, hrest, hpre, hx => by
    obtain ⟨h1, h2, h3, h4, h5⟩ := visit_spec hpre hx (hrest _ (List.mem_cons_self ..))
    obtain ⟨g1, g2, g3, g4, g5⟩ := scan_spec rest (visit ok x a y st)
      (fun p hp => hrest p (List.mem_cons_of_mem _ hp)) h2 (h1 hx)
    refine ⟨h1.trans g1, g2, ?_, g4.trans h4, ?_⟩
    · intro b z hbz hok
      rcases List.mem_cons.mp hbz with h | h
      · obtain ⟨rfl, rfl⟩ := Prod.mk.inj h
        exact g1 (h3 hok)
      · exact g3 b z h hok
    · simp only [scanArcs]; rw [g5, h5, List.length_cons]; ring

omit [Fintype V] [∀ x a y, Decidable (ok x a y)] in
theorem init_inv (S : Finset V) : Inv succ ok S (init S : St V α) := by
  have hdone : done (init S : St V α) = ∅ := by
    ext z; simp [done, init]
  refine ⟨⟨fun y hy => mem_toList.mp hy, nodup_toList S, fun y hy => ?_⟩, subset_rfl, ?_, ?_⟩
  · refine ⟨hy, List.nodup_singleton y, fun z hz => ?_⟩
    simp only [init, pathNodes, List.mem_singleton] at hz ⊢
    exact hz ▸ hy
  · intro x hx; rw [hdone] at hx; simp at hx
  · rw [hdone]; rfl

omit [Fintype V] in
theorem step_inv {S : Finset V} {st : St V α} (h : Inv succ ok S st) :
    Inv succ ok S (step succ ok st) ∧
      (st.stk ≠ [] → #(done (step succ ok st)) = #(done st) + 1) := by
  obtain ⟨vis, stk, lab, cnt⟩ := st
  rcases stk with _ | ⟨x, rest⟩
  · exact ⟨h, fun h => absurd rfl h⟩
  obtain ⟨⟨hsub, hnd, hlab⟩, hS, hcl, hcnt⟩ := h
  simp only at hsub hnd hlab hS hcl hcnt
  have hx : x ∈ vis := hsub x (List.mem_cons_self ..)
  have hxr : x ∉ rest := (List.nodup_cons.mp hnd).1
  set st0 : St V α := ⟨vis, rest, lab, cnt + 1⟩ with hst0
  have hpre0 : Pre succ ok S st0 :=
    ⟨fun y hy => hsub y (List.mem_cons_of_mem _ hy), (List.nodup_cons.mp hnd).2, hlab⟩
  have hdone0 : done st0 = insert x (done ⟨vis, x :: rest, lab, cnt⟩) := by
    ext z
    simp only [done, hst0, mem_filter, mem_insert, List.mem_cons, not_or]
    constructor
    · rintro ⟨h1, h2⟩
      by_cases hz : z = x
      · exact Or.inl hz
      · exact Or.inr ⟨h1, hz, h2⟩
    · rintro (rfl | ⟨h1, -, h2⟩)
      · exact ⟨hx, hxr⟩
      · exact ⟨h1, h2⟩
  have hxd : x ∉ done ⟨vis, x :: rest, lab, cnt⟩ := by simp [done]
  obtain ⟨g1, g2, g3, g4, g5⟩ := scan_spec (S := S) (succ x) st0 (fun _ hp => hp) hpre0 hx
  have hstep : step succ ok ⟨vis, x :: rest, lab, cnt⟩ = scanArcs ok x (succ x) st0 := rfl
  rw [hstep]
  refine ⟨⟨g2, hS.trans g1, ?_, ?_⟩, fun _ => ?_⟩
  · intro z hz a y hzy hok
    rw [g4, hdone0, mem_insert] at hz
    rcases hz with rfl | hz
    · exact g3 a y hzy hok
    · exact g1 (hcl z hz a y hzy hok)
  · rw [g5, g4, hdone0, sum_insert hxd, ← hcnt]; ring
  · rw [g4, hdone0, card_insert_of_notMem hxd]

omit [Fintype V] in
theorem step_nil {st : St V α} (h : st.stk = []) : step succ ok st = st := by
  unfold step; rw [h]

omit [Fintype V] in
theorem iterate_inv (S : Finset V) :
    ∀ i, Inv succ ok S ((step succ ok)^[i] (init S : St V α)) ∧
      (((step succ ok)^[i] (init S : St V α)).stk = [] ∨
        i ≤ #(done ((step succ ok)^[i] (init S : St V α))))
  | 0 => ⟨init_inv S, Or.inr (Nat.zero_le _)⟩
  | i + 1 => by
    obtain ⟨hinv, hor⟩ := iterate_inv S i
    rw [Function.iterate_succ_apply']
    obtain ⟨hinv', hcard⟩ := step_inv hinv
    refine ⟨hinv', ?_⟩
    by_cases hs : ((step succ ok)^[i] (init S : St V α)).stk = []
    · left
      rw [step_nil hs]; exact hs
    · right
      rw [hcard hs]
      exact Nat.succ_le_succ (hor.resolve_left hs)

theorem search_inv (S : Finset V) : Inv succ ok S (search succ ok S : St V α) :=
  (iterate_inv S _).1

/-- The stack is empty at the end: `Fintype.card V` iterations suffice. -/
theorem search_stk (S : Finset V) : (search succ ok S : St V α).stk = [] := by
  set st : St V α := search succ ok S with hst
  rcases hstk : st.stk with _ | ⟨x, rest⟩
  · rfl
  · exfalso
    rcases (iterate_inv (succ := succ) (ok := ok) S (Fintype.card V)).2 with h | h
    · have h' : st.stk = [] := h
      rw [hstk] at h'
      exact List.cons_ne_nil _ _ h'
    · have huniv : done st = univ := eq_univ_of_card _ (le_antisymm (card_le_univ _) h)
      have : x ∈ done st := huniv ▸ mem_univ x
      simp [done, hstk] at this

theorem search_done (S : Finset V) :
    done (search succ ok S : St V α) = (search succ ok S : St V α).vis := by
  simp [done, search_stk]

/-- The starts are visited. -/
theorem search_start (S : Finset V) : S ⊆ (search succ ok S : St V α).vis :=
  (search_inv S).2.1

/-- The visited set is closed under followed arcs. -/
theorem search_closed (S : Finset V) {x : V} (hx : x ∈ (search succ ok S : St V α).vis)
    {a : α} {y : V} (hxy : (a, y) ∈ succ x) (hok : ok x a y) :
    y ∈ (search succ ok S : St V α).vis :=
  (search_inv S).2.2.1 x (by rw [search_done]; exact hx) a y hxy hok

/-- Every visited vertex carries a valid path from `S` with no repeated vertex. -/
theorem search_label (S : Finset V) {y : V} (hy : y ∈ (search succ ok S : St V α).vis) :
    LabOK succ ok S (search succ ok S : St V α).vis y ((search succ ok S : St V α).lab y) :=
  (search_inv S).1.2.2 y hy

/-- The step count: one per visited vertex and one per arc of a visited vertex. -/
theorem search_cnt (S : Finset V) :
    (search succ ok S : St V α).cnt =
      ∑ x ∈ (search succ ok S : St V α).vis, ((succ x).length + 1) := by
  rw [(search_inv S).2.2.2, search_done]

theorem search_cnt_le (S : Finset V) :
    (search succ ok S : St V α).cnt ≤ ∑ x, ((succ x).length + 1) := by
  rw [search_cnt]
  exact sum_le_sum_of_subset (subset_univ _)

omit [Fintype V] [DecidableEq V] [∀ x a y, Decidable (ok x a y)] in
theorem ArcPath.reach {S : Finset V} :
    ∀ (y : V) (π : List (V × α × V)), ArcPath succ ok S y π →
      ∃ s ∈ S, Relation.ReflTransGen (Arc succ ok) s y
  | y, [], h => ⟨y, h, .refl⟩
  | y, (x, a, z) :: π, ⟨_, hs, hok, hπ⟩ => by
    obtain ⟨s, hsS, hr⟩ := ArcPath.reach x π hπ
    exact ⟨s, hsS, hr.tail ⟨a, hs, hok⟩⟩

/-- **The visited set is the set reachable from `S` by followed arcs.** -/
theorem search_mem_iff (S : Finset V) (y : V) :
    y ∈ (search succ ok S : St V α).vis ↔ ∃ s ∈ S, Relation.ReflTransGen (Arc succ ok) s y := by
  constructor
  · intro hy
    exact (search_label S hy).1.reach y _
  · rintro ⟨s, hs, hr⟩
    induction hr with
    | refl => exact search_start S hs
    | tail _ hbc ih =>
      obtain ⟨a, hmem, hok⟩ := hbc
      exact search_closed S ih hmem hok

end SwarmInfer.CoverWeave.Search

#print axioms SwarmInfer.CoverWeave.Search.search_mem_iff
#print axioms SwarmInfer.CoverWeave.Search.search_cnt
#print axioms SwarmInfer.CoverWeave.Search.search_label
