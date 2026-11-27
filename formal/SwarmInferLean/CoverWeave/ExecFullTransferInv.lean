import SwarmInferLean.CoverWeave.ExecFullTransfer

/-!
# CoverWeave, Theorem 3(b): the inductive invariant of the repaired transfer layer (C5(b), C8)

The model is the one of `ExecFullTransfer.lean` (one flexible edge between its two ends, FIFO
channels that may lose frames, unbounded sequence numbers and edge counts) under `repairParams`:
the yield rule, the `θ` check on the late path, R2 (no reply to a busy copy of a PUSH), R3 (a repeat
is acknowledged only if the receiver holds the edge with its edge count one above the carried one)
and R4 (`θ(e)` counts only successful takes). `DInv i ni nj ci cj` is the invariant for the requests
of end `i` to end `j = !i`; `Inv s` asks it in both directions. `step_pres` proves that every event
preserves `Inv`, `inv_start` that the start of Phase 4 satisfies it, and `cp_of_quiet` that a quiet
configuration satisfying it has complementary or absent settled decisions. The main theorem is in
`ExecFullTransferRepair.lean`.

The invariant says, in words: an end has at most one open request; every answer to the open request
`p` that exists (cached or in flight) is positive exactly when the receiver holds the edge with edge
count `p.gen + 1` (the R3 test), and none exists before the receiver executed `p`; a request whose
edge count is current at its sender keeps `θ(e)` current (`live`), one that is not is refused
(`doom`); the edge counts of the two ends differ by at most one, equal counts mean complementary or
absent decisions, and a receiver one ahead holds the edge for the open request of its sender
(`owe`); every other positive answer, and every R3 answer that could still be produced, reaches its
sender only when the late path ignores it (`Harm`); a push chain serves the open PUSH of its sender
or an answered one, and while it serves the open one without the edge no answer exists.
-/

namespace SwarmInfer.CoverWeave.ExecFull

/-- `q` was not executed yet by a receiver whose mark is `m`. -/
def Fresh (m : Option ℕ) (q : ℕ) : Prop := ∀ x, m = some x → x < q

/-- `q` is the open request of `n`. -/
def Cur (n : Node) (q : ℕ) : Prop := ∃ p, n.pend = [p] ∧ p.seq = q

/-- A positive answer to request `q` of `n` that arrives when `q` is not open changes nothing at
`n`: the late path of `onRep` finds the edge released or `q` below the retake mark. -/
def Harm (n : Node) (q : ℕ) : Prop := n.X = some false ∨ ∃ f, n.retake = some f ∧ q ≤ f

/-- The R3 answer of `nj` to a request with edge count `g`. -/
def Okj (nj : Node) (g : ℕ) : Prop := nj.X = some true ∧ nj.gen = g + 1

/-- Complementary or both absent. -/
def CP : Option Bool → Option Bool → Prop
  | none, none => True
  | some true, some false => True
  | some false, some true => True
  | _, _ => False

/-- The sequence numbers of the requests on a channel, in order. -/
def reqSeqs : List Frame → List ℕ
  | [] => []
  | .req q _ _ :: l => q :: reqSeqs l
  | _ :: l => reqSeqs l

/-- A frame on the channel from `i` (its requests and its replies). -/
def FI (ni nj : Node) : Frame → Prop
  | .req q pu g => q ≤ ni.seqc ∧ (∀ p, ni.pend = [p] → p.seq = q → pu = p.push ∧ g = p.gen) ∧
      (Fresh nj.mark q → Cur ni q) ∧ (∀ m, nj.mark = some m → m ≤ q) ∧
      (¬ Cur ni q → Okj nj g → Harm ni q)
  | .rep _ r => r.late = false
  | .conf _ => False

/-- An answer `r` of `j` to request `q` of `i`, cached or in flight. -/
def A1 (ni nj : Node) (q : ℕ) (r : Rep) : Prop :=
  ¬ Fresh nj.mark q ∧ (∀ p, ni.pend = [p] → p.seq = q → (r.ok = true ↔ Okj nj p.gen)) ∧
    (r.ok = true → ¬ Cur ni q → Harm ni q) ∧ (∀ b, nj.job = some (q, b) → Cur ni q → nj.X = some true)

/-- A frame on the channel from `j`, as far as it answers `i`. -/
def FJ (ni nj : Node) : Frame → Prop
  | .rep q r => A1 ni nj q r
  | _ => True

/-- The invariant of the repaired transfer layer, for the requests of `i` to `j = !i` (`i = false`
is `a`, the smaller key), with `ci` the channel from `i` and `cj` the channel from `j`. -/
structure DInv (i : Bool) (ni nj : Node) (ci cj : List Frame) : Prop where
  late : ni.late = []
  job : ∀ q b, ni.job = some (q, b) → b = false
  pend : ni.pend = [] ∨ ∃ p, ni.pend = [p] ∧ p.seq = ni.seqc
  xnone : ni.X = none ↔ ni.gen = 0
  jobA : i = false → ni.job ≠ none → ni.pend = []
  retakeLe : ∀ f, ni.retake = some f → f ≤ ni.seqc
  chanI : ∀ f ∈ ci, FI ni nj f
  chanJ : ∀ f ∈ cj, FJ ni nj f
  cacheJ : ∀ e ∈ nj.cache, A1 ni nj e.1 e.2
  cacheLate : ∀ e ∈ nj.cache, e.2.late = false
  sorted : (reqSeqs ci).Pairwise (· ≤ ·)
  markLe : ∀ m, nj.mark = some m → m ≤ ni.seqc
  jobEx : ∀ q b, nj.job = some (q, b) → ¬ Fresh nj.mark q
  jobPush : ∀ q b p, nj.job = some (q, b) → ni.pend = [p] → p.seq = q → p.push = true
  jobOld : ∀ q b, nj.job = some (q, b) → ¬ Cur ni q → nj.X = some true ∧ Harm ni q
  jobGen : ∀ q b p, nj.job = some (q, b) → ni.pend = [p] → p.seq = q →
    (nj.gen = p.gen ∧ nj.X ≠ some true) ∨ (nj.gen = p.gen + 1 ∧ nj.X = some true)
  jobPendLe : ∀ q b p pj, nj.job = some (q, b) → ni.pend = [p] → p.seq = q → nj.pend = [pj] →
    pj.gen ≤ p.gen
  jobPendX : ∀ q b pj, nj.job = some (q, b) → nj.pend = [pj] → nj.X = some true → pj.gen < nj.gen
  genLe : ∀ p, ni.pend = [p] → p.gen ≤ ni.gen
  live : ∀ p, ni.pend = [p] → p.gen = ni.gen → ni.takes = p.theta ∧ ni.X ≠ some false
  doom : ∀ p, ni.pend = [p] → p.gen < ni.gen →
    i = true ∧ (p.gen < nj.gen ∨ ni.gen = nj.gen + 1) ∧ ¬ Okj nj p.gen
  gap : ni.gen ≤ nj.gen + 1
  owe : nj.gen = ni.gen + 1 → nj.X = some true ∧ ni.X ≠ some false ∧
    ∃ p, ni.pend = [p] ∧ p.gen = ni.gen ∧ ¬ Fresh nj.mark p.seq ∧ ni.takes = p.theta
  bal : ni.gen = nj.gen → CP ni.X nj.X

/-- The invariant of a configuration, both directions. -/
def Inv (s : St) : Prop :=
  DInv false s.a s.b s.fromA s.fromB ∧ DInv true s.b s.a s.fromB s.fromA

theorem inv_iff (s : St) : Inv s ↔ ∀ i, DInv i (s.nd i) (s.nd !i) (s.chan i) (s.chan !i) := by
  constructor
  · rintro ⟨h1, h2⟩ i; cases i <;> assumption
  · intro h; exact ⟨h false, h true⟩

theorem inv_start (da db : Bool) : Inv (start da db) := by
  refine ⟨?_, ?_⟩ <;>
  · constructor <;> simp [start, startNode, Fresh, Cur, reqSeqs, Okj, CP]



/-! ### Local steps -/

theorem reqSeqs_tail {f : Frame} {l : List Frame} (h : (reqSeqs (f :: l)).Pairwise (· ≤ ·)) :
    (reqSeqs l).Pairwise (· ≤ ·) := by
  cases f <;> simp_all [reqSeqs]

theorem reqSeqs_append (l : List Frame) (f : Frame) :
    reqSeqs (l ++ [f]) = reqSeqs l ++ reqSeqs [f] := by
  induction l with
  | nil => simp [reqSeqs]
  | cons x l ih => cases x <;> simp [reqSeqs, ih]

theorem mem_reqSeqs {l : List Frame} {q : ℕ} : q ∈ reqSeqs l ↔ ∃ pu g, Frame.req q pu g ∈ l := by
  induction l with
  | nil => simp [reqSeqs]
  | cons x l ih =>
    cases x with
    | req q' pu g =>
      simp only [reqSeqs, List.mem_cons, ih, Frame.req.injEq]
      constructor
      · rintro (rfl | ⟨pu', g', h⟩)
        · exact ⟨pu, g, Or.inl ⟨rfl, rfl, rfl⟩⟩
        · exact ⟨pu', g', Or.inr h⟩
      · rintro ⟨pu', g', (⟨rfl, -, -⟩ | h)⟩
        · exact Or.inl rfl
        · exact Or.inr ⟨pu', g', h⟩
    | rep => simp [reqSeqs, ih]
    | conf => simp [reqSeqs, ih]

/-- Appending a request `q` that is at least every request on the channel keeps it sorted. -/
theorem sorted_append_req {l : List Frame} (h : (reqSeqs l).Pairwise (· ≤ ·)) {q pu g}
    (hq : ∀ q' pu' g', Frame.req q' pu' g' ∈ l → q' ≤ q) :
    (reqSeqs (l ++ [Frame.req q pu g])).Pairwise (· ≤ ·) := by
  rw [reqSeqs_append]
  simp only [reqSeqs, List.pairwise_append, h, List.pairwise_singleton, List.mem_singleton,
    forall_eq, true_and]
  intro a ha
  obtain ⟨pu', g', h'⟩ := mem_reqSeqs.1 ha
  exact hq a pu' g' h'

theorem sorted_append_nonreq {l : List Frame} (h : (reqSeqs l).Pairwise (· ≤ ·)) {q r} :
    (reqSeqs (l ++ [Frame.rep q r])).Pairwise (· ≤ ·) := by
  rw [reqSeqs_append]; simpa [reqSeqs] using h

/-- The head of a sorted channel is at most every later request. -/
theorem head_le {q pu g} {l : List Frame} (h : (reqSeqs (Frame.req q pu g :: l)).Pairwise (· ≤ ·))
    {q' pu' g'} (h' : Frame.req q' pu' g' ∈ l) : q ≤ q' := by
  simp only [reqSeqs, List.pairwise_cons] at h
  exact h.1 q' (mem_reqSeqs.2 ⟨pu', g', h'⟩)

/-- A frame is consumed (delivered without effect or lost). -/
theorem tail_pres {i : Bool} {ni nj : Node} {f : Frame} {l cj : List Frame}
    (H1 : DInv i ni nj (f :: l) cj) (H2 : DInv (!i) nj ni cj (f :: l)) :
    DInv i ni nj l cj ∧ DInv (!i) nj ni cj l :=
  ⟨{ H1 with
      chanI := fun x hx => H1.chanI x (List.mem_cons_of_mem _ hx)
      sorted := reqSeqs_tail H1.sorted },
   { H2 with chanJ := fun x hx => H2.chanJ x (List.mem_cons_of_mem _ hx) }⟩

/-- A budget change. -/
theorem flip_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) :
    DInv i { ni with dflt := !ni.dflt } nj ci cj ∧ DInv (!i) nj { ni with dflt := !ni.dflt } cj ci :=
  ⟨{ H1 with }, { H2 with }⟩

/-- An eviction from the reply cache of `i` (replies to `j`). -/
theorem evict_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) (q : ℕ) :
    DInv i { ni with cache := ni.cache.filter fun x => x.1 ≠ q } nj ci cj ∧
      DInv (!i) nj { ni with cache := ni.cache.filter fun x => x.1 ≠ q } cj ci :=
  ⟨{ H1 with }, { H2 with
      cacheJ := fun e he => H2.cacheJ e (List.mem_of_mem_filter he)
      cacheLate := fun e he => H2.cacheLate e (List.mem_of_mem_filter he) }⟩


theorem DInv.pend_seq {i : Bool} {ni nj : Node} {ci cj : List Frame} (H : DInv i ni nj ci cj)
    {p : Pend} (hp : ni.pend = [p]) : p.seq = ni.seqc := by
  rcases H.pend with h | ⟨p', h, h'⟩
  · simp [h] at hp
  · rw [hp, List.singleton_inj] at h; subst h; exact h'

theorem DInv.req_le {i : Bool} {ni nj : Node} {ci cj : List Frame} (H : DInv i ni nj ci cj)
    {q pu g} (h : Frame.req q pu g ∈ ci) : q ≤ ni.seqc :=
  (H.chanI _ h).1

/-- A retransmission of the open request. -/
theorem retx_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {p : Pend} (hp : ni.pend = [p]) :
    DInv i ni nj (ci ++ [.req p.seq p.push p.gen]) cj ∧
      DInv (!i) nj ni cj (ci ++ [.req p.seq p.push p.gen]) := by
  have hs := H1.pend_seq hp
  refine ⟨{ H1 with chanI := ?_, sorted := ?_ }, { H2 with chanJ := ?_ }⟩
  · intro f hf
    rcases List.mem_append.1 hf with hf | hf
    · exact H1.chanI f hf
    · rw [List.mem_singleton] at hf; subst hf
      refine ⟨hs.le, fun p' hp' _ => ?_, fun _ => ⟨p, hp, rfl⟩, fun m hm => hs ▸ H1.markLe m hm,
        fun h => absurd ⟨p, hp, rfl⟩ h⟩
      rw [hp, List.singleton_inj] at hp'; subst hp'; exact ⟨rfl, rfl⟩
  · exact sorted_append_req H1.sorted fun q pu g h => hs ▸ H1.req_le h
  · intro f hf
    rcases List.mem_append.1 hf with hf | hf
    · exact H2.chanJ f hf
    · rw [List.mem_singleton] at hf; subst hf; trivial


theorem DInv.not_fresh_le {i : Bool} {ni nj : Node} {ci cj : List Frame} (H : DInv i ni nj ci cj)
    {q : ℕ} (h : ¬ Fresh nj.mark q) : q ≤ ni.seqc := by
  simp only [Fresh, not_forall, not_lt] at h
  obtain ⟨m, hm, hq⟩ := h
  exact hq.trans (H.markLe m hm)

/-- The node after an offer, as in `step`. -/
def offerNode (n : Node) (push : Bool) : Node :=
  { n with seqc := n.seqc + 1, offered := true, pend := n.pend ++ [⟨n.seqc + 1, push, n.takes, n.gen⟩] }

/-- A new offer (stage 1 HANDOVER or stage 2 PUSH). -/
theorem offer_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) (push : Bool)
    (ho : ni.X = some true ∨ (ni.X = none ∧ ni.dflt = true)) (hj : ni.job = none)
    (hpe : ni.pend = []) :
    let ni' : Node := offerNode ni push
    DInv i ni' nj (ci ++ [.req (ni.seqc + 1) push ni.gen]) cj ∧
      DInv (!i) nj ni' cj (ci ++ [.req (ni.seqc + 1) push ni.gen]) := by
  intro ni'
  have hpn : ni'.pend = [⟨ni.seqc + 1, push, ni.takes, ni.gen⟩] := by simp [ni', offerNode, hpe]
  have hnc : ∀ q, ¬ Cur ni q := fun q ⟨p, hp, _⟩ => by simp [hpe] at hp
  have hcur : ∀ q, Cur ni' q ↔ q = ni.seqc + 1 := fun q => by
    simp only [Cur, hpn, List.singleton_inj]
    exact ⟨fun ⟨p, hp, h⟩ => by subst hp; exact h.symm, fun h => ⟨_, rfl, h.symm⟩⟩
  have hnf : ∀ q, ¬ Fresh nj.mark q → q ≠ ni.seqc + 1 := fun q h h' => by
    have := H1.not_fresh_le h; omega
  have hX : ni.X ≠ some false := by rcases ho with h | ⟨h, -⟩ <;> simp [h]
  have hA : ∀ q r, A1 ni nj q r → A1 ni' nj q r := by
    rintro q r ⟨h1, -, h3, h4⟩
    refine ⟨h1, fun p hp hq => ?_, fun hr _ => h3 hr (hnc q), fun b hb hc => ?_⟩
    · simp only [hpn, List.singleton_inj] at hp; subst hp; exact absurd hq.symm (hnf q h1)
    · exact absurd ((hcur q).1 hc) (hnf q h1)
  refine ⟨{
      late := H1.late, job := fun q b h => by simp [ni', offerNode, hj] at h, pend := Or.inr ⟨_, hpn, rfl⟩,
      xnone := H1.xnone, jobA := fun _ h => absurd hj h,
      retakeLe := fun f hf => (H1.retakeLe f hf).trans (Nat.le_succ _),
      chanI := ?_, chanJ := ?_, cacheJ := fun e he => hA _ _ (H1.cacheJ e he), cacheLate := H1.cacheLate, sorted := ?_,
      markLe := fun m hm => (H1.markLe m hm).trans (Nat.le_succ _), jobEx := H1.jobEx,
      jobPush := ?_, jobOld := fun q b h hc => ?_, jobGen := ?_, jobPendLe := ?_,
      jobPendX := H1.jobPendX, genLe := ?_, live := ?_, doom := ?_, gap := H1.gap, owe := ?_,
      bal := H1.bal },
    { H2 with chanJ := ?_, jobPendLe := ?_, jobPendX := ?_ }⟩
  · intro f hf
    rcases List.mem_append.1 hf with hf | hf
    · have h := H1.chanI f hf
      cases f with
      | req q pu g =>
        obtain ⟨h1, -, h3, h4, h5⟩ := h
        have hnf' : ¬ Fresh nj.mark q := fun hf' => hnc q (h3 hf')
        refine ⟨h1.trans (Nat.le_succ _), fun p hp hq => ?_, fun hf' => absurd hf' hnf', h4,
          fun _ hok => h5 (hnc q) hok⟩
        simp only [hpn, List.singleton_inj] at hp; subst hp; exact absurd hq.symm (hnf q hnf')
      | rep q r => exact h
      | conf q => exact h
    · rw [List.mem_singleton] at hf; subst hf
      refine ⟨le_rfl, fun p hp _ => ?_, fun _ => (hcur _).2 rfl, fun m hm => ?_,
        fun h => absurd ((hcur _).2 rfl) h⟩
      · simp only [hpn, List.singleton_inj] at hp; subst hp; exact ⟨rfl, rfl⟩
      · exact (H1.markLe m hm).trans (Nat.le_succ _)
  · intro f hf
    have h := H1.chanJ f hf
    cases f with
    | rep q r => exact hA q r h
    | req => trivial
    | conf => trivial
  · exact sorted_append_req H1.sorted fun q pu g h => (H1.req_le h).trans (Nat.le_succ _)
  · intro q b p hb hp hq
    simp only [hpn, List.singleton_inj] at hp; subst hp
    exact absurd hq.symm (hnf q (H1.jobEx q b hb))
  · exact H1.jobOld q b h (hnc q)
  · intro q b p hb hp hq
    simp only [hpn, List.singleton_inj] at hp; subst hp
    exact absurd hq.symm (hnf q (H1.jobEx q b hb))
  · intro q b p pj hb hp hq
    simp only [hpn, List.singleton_inj] at hp; subst hp
    exact absurd hq.symm (hnf q (H1.jobEx q b hb))
  · intro p hp; simp only [hpn, List.singleton_inj] at hp; subst hp; exact le_rfl
  · intro p hp _; simp only [hpn, List.singleton_inj] at hp; subst hp; exact ⟨rfl, hX⟩
  · intro p hp h; simp only [hpn, List.singleton_inj] at hp; subst hp; exact absurd h (lt_irrefl _)
  · intro h
    obtain ⟨-, -, p, hp, -⟩ := H1.owe h
    simp [hpe] at hp
  · intro f hf
    rcases List.mem_append.1 hf with hf | hf
    · exact H2.chanJ f hf
    · rw [List.mem_singleton] at hf; subst hf; trivial
  · intro q b p pj hb; simp [ni', offerNode, hj] at hb
  · intro q b pj hb; simp [ni', offerNode, hj] at hb


/-! ### Replies at the requester -/

theorem DInv.pend_eq {i : Bool} {ni nj : Node} {ci cj : List Frame} (_H : DInv i ni nj ci cj)
    {p p' : Pend} (hp : ni.pend = [p]) (hp' : ni.pend = [p']) : p' = p := by
  rw [hp, List.singleton_inj] at hp'; exact hp'.symm

/-- If an answer to the open request `p` exists, `p` was executed. -/
theorem A1.not_fresh {ni nj : Node} {q : ℕ} {r : Rep} (h : A1 ni nj q r) : ¬ Fresh nj.mark q := h.1

/-- A positive answer to the open request makes it live and the receiver owe nothing more. -/
theorem DInv.pos_live {i : Bool} {ni nj : Node} {ci cj : List Frame} (H : DInv i ni nj ci cj)
    {p : Pend} (hp : ni.pend = [p]) (hok : Okj nj p.gen) : p.gen = ni.gen := by
  rcases Nat.lt_or_ge p.gen ni.gen with h | h
  · exact absurd hok (H.doom p hp h).2.2
  · exact le_antisymm (H.genLe p hp) h

/-- A refusal of the open request `p` is read: the request is closed and nothing else changes. -/
theorem neg_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {p : Pend} (hp : ni.pend = [p]) {r : Rep}
    (hA1 : A1 ni nj p.seq r) (hr : r.ok = false) :
    DInv i { ni with pend := [] } nj ci cj ∧ DInv (!i) nj { ni with pend := [] } cj ci := by
  have hnf := hA1.1
  have hneg : ¬ Okj nj p.gen := fun h => by
    have := (hA1.2.1 p hp rfl).2 h; simp [hr] at this
  have hcur : ∀ q, Cur ni q ↔ q = p.seq := fun q => by
    simp only [Cur, hp, List.singleton_inj]
    exact ⟨fun ⟨p', hp', h⟩ => by subst hp'; exact h.symm, fun h => ⟨_, rfl, h.symm⟩⟩
  have hnc : ∀ q, ¬ Cur { ni with pend := [] } q := fun q ⟨p', hp', _⟩ => by simp at hp'
  have hA : ∀ q r, A1 ni nj q r → A1 { ni with pend := [] } nj q r := by
    rintro q r ⟨h1, h2, h3, -⟩
    refine ⟨h1, fun p' hp' _ => by simp at hp', fun hr _ => ?_, fun b _ hc => absurd hc (hnc q)⟩
    by_cases hq : q = p.seq
    · subst hq; exact absurd ((h2 p hp rfl).1 hr) hneg
    · exact h3 hr fun hc => hq ((hcur q).1 hc)
  have hnojob : ∀ b, nj.job ≠ some (p.seq, b) := by
    intro b hb
    have hX := hA1.2.2.2 b hb ⟨p, hp, rfl⟩
    rcases H1.jobGen p.seq b p hb hp rfl with ⟨-, hX'⟩ | ⟨hg, -⟩
    · exact hX' hX
    · exact hneg ⟨hX, hg⟩
  refine ⟨{
      late := H1.late, job := H1.job, pend := Or.inl rfl, xnone := H1.xnone,
      jobA := fun _ _ => rfl, retakeLe := H1.retakeLe, chanI := ?_,
      chanJ := fun f hf => ?_, cacheJ := fun e he => hA _ _ (H1.cacheJ e he), cacheLate := H1.cacheLate,
      sorted := H1.sorted, markLe := H1.markLe, jobEx := H1.jobEx,
      jobPush := fun _ _ _ _ h => by simp at h, jobOld := fun q b hb _ => ?_,
      jobGen := fun _ _ _ _ h => by simp at h, jobPendLe := fun _ _ _ _ _ h => by simp at h,
      jobPendX := H1.jobPendX, genLe := fun _ h => by simp at h, live := fun _ h => by simp at h,
      doom := fun _ h => by simp at h, gap := H1.gap, owe := fun h => ?_, bal := H1.bal },
    { H2 with jobPendLe := fun _ _ _ _ _ _ _ h => by simp at h,
              jobPendX := fun _ _ _ _ h => by simp at h }⟩
  · intro f hf
    have h := H1.chanI f hf
    cases f with
    | req q pu g =>
      obtain ⟨h1, h2, h3, h4, h5⟩ := h
      refine ⟨h1, fun _ h => by simp at h, fun hf' => ?_, h4, fun _ hok => ?_⟩
      · exact absurd (((hcur q).1 (h3 hf')) ▸ hf') hnf
      · by_cases hq : q = p.seq
        · subst hq; exact absurd ((h2 p hp rfl).2 ▸ hok) hneg
        · exact h5 (fun hc => hq ((hcur q).1 hc)) hok
    | rep q r => exact h
    | conf q => exact h
  · have h := H1.chanJ f hf
    cases f with
    | rep q r => exact hA q r h
    | req => trivial
    | conf => trivial
  · by_cases hq : q = p.seq
    · subst hq; exact absurd hb (hnojob b)
    · exact H1.jobOld q b hb fun hc => hq ((hcur q).1 hc)
  · obtain ⟨hX, -, p', hp', hg, -⟩ := H1.owe h
    rw [hp, List.singleton_inj] at hp'; subst hp'
    exact (hneg ⟨hX, by rw [hg]; exact h⟩).elim


/-- An acknowledgement of the open request `p` is read and `θ(e)` is current: the sender releases
the edge. -/
theorem pos_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {p : Pend} (hp : ni.pend = [p]) {r : Rep}
    (hA1 : A1 ni nj p.seq r) (hr : r.ok = true) :
    DInv i (release { ni with pend := [] }) nj ci cj ∧
      DInv (!i) nj (release { ni with pend := [] }) cj ci := by
  have hnf := hA1.1
  have hok : Okj nj p.gen := (hA1.2.1 p hp rfl).1 hr
  have hlive := H1.pos_live hp hok
  obtain ⟨hX, hgj⟩ := hok
  rw [hlive] at hgj
  have hcur : ∀ q, Cur ni q ↔ q = p.seq := fun q => by
    simp only [Cur, hp, List.singleton_inj]
    exact ⟨fun ⟨p', hp', h⟩ => by subst hp'; exact h.symm, fun h => ⟨_, rfl, h.symm⟩⟩
  have hnc : ∀ q, ¬ Cur (release { ni with pend := [] }) q := fun q ⟨p', hp', _⟩ => by
    simp [release] at hp'
  have hA : ∀ q r, A1 ni nj q r → A1 (release { ni with pend := [] }) nj q r := by
    rintro q r ⟨h1, -, -, -⟩
    exact ⟨h1, fun p' hp' _ => by simp [release] at hp', fun _ _ => Or.inl rfl,
      fun b _ hc => absurd hc (hnc q)⟩
  -- `j`'s open request cannot be answered positively by `i`
  have hnok : ∀ pj, nj.pend = [pj] → ¬ Okj ni pj.gen := by
    intro pj hpj ⟨hXi, hgi⟩
    have hle := H2.genLe pj hpj
    exact (H2.doom pj hpj (by omega)).2.2 ⟨hXi, hgi⟩
  have hnojob : ∀ q b, ni.job ≠ some (q, b) := by
    intro q b hb
    cases i with
    | false => exact absurd hp (by rw [H1.jobA rfl (by simp [hb])]; simp)
    | true =>
      by_cases hXi : ni.X = some true
      · exact absurd hlive (Nat.ne_of_lt (H2.jobPendX q b p hb hp hXi))
      · by_cases hc : Cur nj q
        · obtain ⟨pj, hpj, hq⟩ := hc
          have hg := H2.jobGen q b pj hb hpj hq
          have hle := H2.jobPendLe q b pj p hb hpj hq hp
          have hd := H2.doom pj hpj (by rcases hg with ⟨h, -⟩ | ⟨-, h⟩ <;> [omega; exact absurd h hXi])
          simp at hd
        · exact hXi (H2.jobOld q b hb hc).1
  refine ⟨{
      late := rfl, job := H1.job, pend := Or.inl rfl, xnone := by simp [release],
      jobA := fun _ _ => rfl, retakeLe := H1.retakeLe, chanI := ?_,
      chanJ := fun f hf => ?_, cacheJ := fun e he => hA _ _ (H1.cacheJ e he), cacheLate := H1.cacheLate,
      sorted := H1.sorted, markLe := H1.markLe, jobEx := H1.jobEx,
      jobPush := fun _ _ _ _ h => by simp [release] at h,
      jobOld := fun q b hb _ => ⟨hX, Or.inl rfl⟩,
      jobGen := fun _ _ _ _ h => by simp [release] at h,
      jobPendLe := fun _ _ _ _ _ h => by simp [release] at h,
      jobPendX := H1.jobPendX, genLe := fun _ h => by simp [release] at h,
      live := fun _ h => by simp [release] at h, doom := fun _ h => by simp [release] at h,
      gap := by simp [release]; omega, owe := fun h => by simp [release] at h; omega,
      bal := fun _ => by simp [release, hX, CP] },
    { late := H2.late, job := H2.job, pend := H2.pend, xnone := H2.xnone, jobA := H2.jobA,
      retakeLe := H2.retakeLe, chanI := ?_, chanJ := ?_, cacheJ := ?_, cacheLate := H2.cacheLate,
      sorted := H2.sorted,
      markLe := H2.markLe, jobEx := fun q b hb => absurd hb (hnojob q b),
      jobPush := fun q b _ hb => absurd hb (hnojob q b),
      jobOld := fun q b hb => absurd hb (hnojob q b),
      jobGen := fun q b _ hb => absurd hb (hnojob q b),
      jobPendLe := fun q b _ _ hb => absurd hb (hnojob q b),
      jobPendX := fun q b _ hb => absurd hb (hnojob q b),
      genLe := H2.genLe, live := H2.live, doom := fun pj hpj hlt => ?_,
      gap := by simp [release]; omega, owe := fun h => by simp [release] at h; omega,
      bal := fun _ => by simp [release, hX, CP] }⟩
  · intro f hf
    have h := H1.chanI f hf
    cases f with
    | req q pu g =>
      obtain ⟨h1, -, h3, h4, -⟩ := h
      exact ⟨h1, fun _ h => by simp [release] at h,
        fun hf' => absurd (((hcur q).1 (h3 hf')) ▸ hf') hnf, h4, fun _ _ => Or.inl rfl⟩
    | rep q r => exact h
    | conf q => exact h
  · have h := H1.chanJ f hf
    cases f with
    | rep q r => exact hA q r h
    | req => trivial
    | conf => trivial
  · intro f hf
    have h := H2.chanI f hf
    cases f with
    | req q pu g =>
      obtain ⟨h1, h2, h3, h4, -⟩ := h
      exact ⟨h1, h2, h3, h4, fun _ hok => absurd hok.1 (by simp [release])⟩
    | rep q r => exact h
    | conf q => exact h
  · have hA' : ∀ q r, A1 nj ni q r → A1 nj (release { ni with pend := [] }) q r := by
      rintro q r ⟨h1, h2, h3, -⟩
      refine ⟨h1, fun pj hpj hq => ?_, h3, fun b hb => absurd hb (hnojob q b)⟩
      have := h2 pj hpj hq
      simp only [Okj, release] at this ⊢
      constructor
      · intro hr'; exact absurd (this.1 hr') (hnok pj hpj)
      · rintro ⟨h, -⟩; simp at h
    intro f hf
    have h := H2.chanJ f hf
    cases f with
    | rep q r => exact hA' q r h
    | req => trivial
    | conf => trivial
  · intro e he
    have h := H2.cacheJ e he
    obtain ⟨h1, h2, h3, -⟩ := h
    refine ⟨h1, fun pj hpj hq => ?_, h3, fun b hb => absurd hb (hnojob _ b)⟩
    have := h2 pj hpj hq
    simp only [Okj, release] at this ⊢
    constructor
    · intro hr'; exact absurd (this.1 hr') (hnok pj hpj)
    · rintro ⟨h, -⟩; simp at h
  · obtain ⟨h1, -, -⟩ := H2.doom pj hpj hlt
    refine ⟨h1, Or.inl ?_, fun h => by simp [Okj, release] at h⟩
    simp only [release]; omega


/-! ### Requests at the receiver -/

theorem fresh_some {q q' : ℕ} : Fresh (some q) q' ↔ q < q' := by
  simp [Fresh]

theorem not_fresh_mono {m : Option ℕ} {q q' : ℕ} (h : ¬ Fresh m q')
    (hm : ∀ x, m = some x → x ≤ q) : ¬ Fresh (some q) q' := by
  simp only [Fresh, not_forall, not_lt] at h
  obtain ⟨x, hx, h⟩ := h
  rw [fresh_some]; have := hm x hx; omega

/-- The head request of the channel from `i` is new at `j`: `j` moves its mark to it. -/
theorem fresh_pres {i : Bool} {ni nj : Node} {q : ℕ} {pu : Bool} {g : ℕ} {l cj : List Frame}
    (H1 : DInv i ni nj (.req q pu g :: l) cj) (H2 : DInv (!i) nj ni cj (.req q pu g :: l))
    (hfr : Fresh nj.mark q) :
    DInv i ni { nj with mark := some q } l cj ∧ DInv (!i) { nj with mark := some q } ni cj l := by
  obtain ⟨hq, -, hfc, hmk, -⟩ := H1.chanI _ List.mem_cons_self
  obtain ⟨p, hp, hpq⟩ := hfc hfr
  have hs := H1.pend_seq hp
  have nf : ∀ q', ¬ Fresh nj.mark q' → ¬ Fresh (some q) q' := fun q' h => not_fresh_mono h hmk
  have hall : ∀ q' pu' g', Frame.req q' pu' g' ∈ l → q' = q := fun q' pu' g' h => by
    have h1 := head_le H1.sorted h
    have h2 := H1.req_le (List.mem_cons_of_mem _ h)
    omega
  have hA : ∀ q' r, A1 ni nj q' r → A1 ni { nj with mark := some q } q' r :=
    fun q' r ⟨h1, h2, h3, h4⟩ => ⟨nf q' h1, h2, h3, h4⟩
  refine ⟨{ H1 with
      chanI := fun f hf => ?_
      chanJ := fun f hf => ?_
      cacheJ := fun e he => hA _ _ (H1.cacheJ e he)
      sorted := reqSeqs_tail H1.sorted
      markLe := fun m hm => by simp at hm; omega
      jobEx := fun q' b hb => nf q' (H1.jobEx q' b hb)
      owe := fun h => ?_ },
    { H2 with chanJ := fun x hx => H2.chanJ x (List.mem_cons_of_mem _ hx) }⟩
  · have h := H1.chanI f (List.mem_cons_of_mem _ hf)
    cases f with
    | req q' pu' g' =>
      have hq' := hall q' pu' g' hf
      subst hq'
      obtain ⟨a1, a2, -, -, -⟩ := h
      exact ⟨a1, a2, fun _ => ⟨p, hp, hpq⟩, fun m hm => by simp at hm; omega,
        fun hnc => absurd ⟨p, hp, hpq⟩ hnc⟩
    | rep => exact h
    | conf => exact h
  · have h := H1.chanJ f hf
    cases f with
    | rep q' r => exact hA q' r h
    | req => trivial
    | conf => trivial
  · obtain ⟨a, b, p', c, d, hnf', e⟩ := H1.owe h
    exact ⟨a, b, p', c, d, nf _ hnf', e⟩

/-- `j` answers request `q` of `i` with `r`, caching the answer. -/
theorem answer_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {q : ℕ} {r : Rep} (hA : A1 ni nj q r) (hl : r.late = false) :
    DInv i ni (cachePut nj q r) ci (cj ++ [.rep q r]) ∧
      DInv (!i) (cachePut nj q r) ni (cj ++ [.rep q r]) ci := by
  refine ⟨{ H1 with
      chanJ := fun f hf => ?_
      cacheJ := fun e he => ?_
      cacheLate := fun e he => ?_ },
    { H2 with
      chanI := fun f hf => ?_
      sorted := sorted_append_nonreq H2.sorted }⟩
  · rcases List.mem_append.1 hf with hf | hf
    · exact H1.chanJ f hf
    · rw [List.mem_singleton] at hf; subst hf; exact hA
  · simp only [cachePut, List.mem_append, List.mem_filter, List.mem_singleton] at he
    rcases he with ⟨he, -⟩ | rfl
    · exact H1.cacheJ e he
    · exact hA
  · simp only [cachePut, List.mem_append, List.mem_filter, List.mem_singleton] at he
    rcases he with ⟨he, -⟩ | rfl
    · exact H1.cacheLate e he
    · exact hl
  · rcases List.mem_append.1 hf with hf | hf
    · exact H2.chanI f hf
    · rw [List.mem_singleton] at hf; subst hf; exact hl

/-- `j` sends a cached answer again. -/
theorem resend_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {q : ℕ} {r : Rep} (hA : A1 ni nj q r) (hl : r.late = false) :
    DInv i ni nj ci (cj ++ [.rep q r]) ∧ DInv (!i) nj ni (cj ++ [.rep q r]) ci := by
  refine ⟨{ H1 with chanJ := fun f hf => ?_ },
    { H2 with chanI := fun f hf => ?_, sorted := sorted_append_nonreq H2.sorted }⟩
  · rcases List.mem_append.1 hf with hf | hf
    · exact H1.chanJ f hf
    · rw [List.mem_singleton] at hf; subst hf; exact hA
  · rcases List.mem_append.1 hf with hf | hf
    · exact H2.chanI f hf
    · rw [List.mem_singleton] at hf; subst hf; exact hl

/-- `j`'s push chain ends (the job is dropped before the answer). -/
theorem jobEnd_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) :
    DInv i ni { nj with job := none } ci cj ∧ DInv (!i) { nj with job := none } ni cj ci := by
  have hA : ∀ q r, A1 ni nj q r → A1 ni { nj with job := none } q r :=
    fun q r ⟨h1, h2, h3, _⟩ => ⟨h1, h2, h3, fun b hb => by simp at hb⟩
  refine ⟨{ H1 with
      chanJ := fun f hf => ?_
      cacheJ := fun e he => hA _ _ (H1.cacheJ e he)
      jobEx := fun _ _ h => by simp at h
      jobPush := fun _ _ _ h => by simp at h
      jobOld := fun _ _ h => by simp at h
      jobGen := fun _ _ _ h => by simp at h
      jobPendLe := fun _ _ _ _ h => by simp at h
      jobPendX := fun _ _ _ h => by simp at h },
    { H2 with job := fun _ _ h => by simp at h, jobA := fun _ h => absurd rfl h }⟩
  · have h := H1.chanJ f hf
    cases f with
    | rep q r => exact hA q r h
    | req => trivial
    | conf => trivial


/-- No answer to request `q` of `i` exists at `j` or on its channel. -/
def NoAns (nj : Node) (cj : List Frame) (q : ℕ) : Prop :=
  (∀ r, (q, r) ∉ nj.cache) ∧ ∀ r, Frame.rep q r ∉ cj

/-- `j` starts a push chain for the open PUSH `p` of `i`. -/
theorem jobStart_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {p : Pend} (hp : ni.pend = [p]) (hnf : ¬ Fresh nj.mark p.seq)
    (hX : nj.X ≠ some true) (hg : nj.gen = p.gen) (hpush : p.push = true)
    (hy : i = true → nj.pend = []) (hno : NoAns nj cj p.seq) :
    DInv i ni { nj with job := some (p.seq, false) } ci cj ∧
      DInv (!i) { nj with job := some (p.seq, false) } ni cj ci := by
  have hA : ∀ q r, A1 ni nj q r → q ≠ p.seq → A1 ni { nj with job := some (p.seq, false) } q r :=
    fun q r ⟨h1, h2, h3, _⟩ hq => ⟨h1, h2, h3, fun b hb => by simp at hb; exact absurd hb.1.symm hq⟩
  refine ⟨{ H1 with
      chanJ := fun f hf => ?_
      cacheJ := fun e he => hA _ _ (H1.cacheJ e he) fun h => hno.1 e.2 (h ▸ he)
      jobEx := fun q b hb => by simp at hb; exact hb.1 ▸ hnf
      jobPush := fun q b p' hb hp' hq => by
        rw [hp, List.singleton_inj] at hp'; subst hp'; exact hpush
      jobOld := fun q b hb hc => by simp at hb; exact absurd ⟨p, hp, hb.1⟩ hc
      jobGen := fun q b p' hb hp' hq => by
        rw [hp, List.singleton_inj] at hp'; subst hp'; exact Or.inl ⟨hg, hX⟩
      jobPendLe := fun q b p' pj hb hp' hq hpj => by
        rw [hp, List.singleton_inj] at hp'; subst hp'; exact hg ▸ H2.genLe pj hpj
      jobPendX := fun _ _ _ _ _ h => absurd h hX },
    { H2 with
      job := fun q b hb => by simp at hb; exact hb.2
      jobA := fun h _ => hy (by simpa using h) }⟩
  · have h := H1.chanJ f hf
    cases f with
    | rep q r => exact hA q r h fun hq => hno.2 r (hq ▸ hf)
    | req => trivial
    | conf => trivial

/-- The node after `_accept_edge` succeeds on an edge it did not hold. -/
def takeNode (n : Node) : Node :=
  { n with
    offered := false, takes := n.takes + 1, retake := some n.seqc, X := some true,
    gen := n.gen + 1 }

@[simp] theorem takeNode_X (n : Node) : (takeNode n).X = some true := rfl
@[simp] theorem takeNode_gen (n : Node) : (takeNode n).gen = n.gen + 1 := rfl
@[simp] theorem takeNode_seqc (n : Node) : (takeNode n).seqc = n.seqc := rfl
@[simp] theorem takeNode_retake (n : Node) : (takeNode n).retake = some n.seqc := rfl
@[simp] theorem takeNode_pend (n : Node) : (takeNode n).pend = n.pend := rfl
@[simp] theorem takeNode_job (n : Node) : (takeNode n).job = n.job := rfl
@[simp] theorem takeNode_mark (n : Node) : (takeNode n).mark = n.mark := rfl

/-- `j` takes the edge (it did not hold it) for the open request `p` of `i`, all of whose copies
on the channel are the request itself and which has no answer yet. -/
theorem take_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {p : Pend} (hp : ni.pend = [p]) (hnf : ¬ Fresh nj.mark p.seq)
    (hg : nj.gen = p.gen) (hy : i = true → nj.pend = [])
    (hno : NoAns nj cj p.seq) (hall : ∀ q pu g, Frame.req q pu g ∈ ci → q = p.seq) :
    DInv i ni (takeNode nj) ci cj ∧ DInv (!i) (takeNode nj) ni cj ci := by
  have hcur : Cur ni p.seq := ⟨p, hp, rfl⟩
  have hlive : p.gen = ni.gen := by
    rcases Nat.lt_or_ge p.gen ni.gen with h | h
    · obtain ⟨hi, h2, -⟩ := H1.doom p hp h
      rcases h2 with h2 | h2
      · omega
      · obtain ⟨-, -, pj, hpj, -⟩ := H2.owe (by simpa using h2)
        rw [hy hi] at hpj; simp at hpj
    · exact le_antisymm (H1.genLe p hp) h
  obtain ⟨hθ, hXi⟩ := H1.live p hp hlive
  have hA : ∀ q r, A1 ni nj q r → q ≠ p.seq → A1 ni (takeNode nj) q r := by
    rintro q r ⟨h1, -, h3, -⟩ hq
    refine ⟨h1, fun p' hp' hq' => ?_, h3, fun _ _ _ => rfl⟩
    rw [hp, List.singleton_inj] at hp'; subst hp'; exact absurd hq'.symm hq
  have hA' : ∀ q r, A1 nj ni q r → A1 (takeNode nj) ni q r := by
    rintro q r ⟨h1, h2, h3, h4⟩
    exact ⟨h1, h2, fun _ _ => Or.inr ⟨_, rfl, H2.not_fresh_le h1⟩, h4⟩
  refine ⟨{ H1 with
      chanI := fun f hf => ?_
      chanJ := fun f hf => ?_
      cacheJ := fun e he => hA _ _ (H1.cacheJ e he) fun h => hno.1 e.2 (h ▸ he)
      jobOld := fun q b hb hc => ⟨rfl, (H1.jobOld q b hb hc).2⟩
      jobGen := fun q b p' hb hp' hq => by
        rw [hp, List.singleton_inj] at hp'; subst hp'
        exact Or.inr ⟨by simp [hg], rfl⟩
      jobPendX := fun q b pj _ hpj _ => by
        have := H2.genLe pj hpj; simp only [takeNode_gen]; omega
      doom := fun p' hp' h => by
        rw [hp, List.singleton_inj] at hp'; subst hp'; exact absurd h (by omega)
      gap := by simp only [takeNode_gen]; omega
      owe := fun _ => ⟨rfl, hXi, p, hp, hlive, hnf, hθ⟩
      bal := fun h => by simp only [takeNode_gen] at h; omega },
    {
      late := H2.late, job := H2.job, pend := H2.pend, xnone := by simp,
      jobA := H2.jobA, retakeLe := fun f hf => by simp at hf ⊢; omega,
      chanI := fun f hf => ?_, chanJ := fun f hf => ?_,
      cacheJ := fun e he => hA' _ _ (H2.cacheJ e he), cacheLate := H2.cacheLate,
      sorted := H2.sorted, markLe := H2.markLe, jobEx := H2.jobEx, jobPush := H2.jobPush,
      jobOld := fun q b hb hc => ⟨(H2.jobOld q b hb hc).1,
        Or.inr ⟨_, rfl, H2.not_fresh_le (H2.jobEx q b hb)⟩⟩,
      jobGen := H2.jobGen, jobPendLe := H2.jobPendLe, jobPendX := H2.jobPendX,
      genLe := fun pj hpj => by have := H2.genLe pj hpj; simp only [takeNode_gen]; omega,
      live := fun pj hpj h => by
        have := H2.genLe pj hpj; simp only [takeNode_gen] at h; omega,
      doom := fun pj hpj hlt => ?_,
      gap := by simp only [takeNode_gen]; omega,
      owe := fun h => by simp only [takeNode_gen] at h; omega,
      bal := fun h => by simp only [takeNode_gen] at h; omega }⟩
  · have h := H1.chanI f hf
    cases f with
    | req q pu g =>
      have hq := hall q pu g hf
      subst hq
      obtain ⟨a1, a2, -, a4, -⟩ := h
      exact ⟨a1, a2, fun _ => hcur, a4, fun hnc => absurd hcur hnc⟩
    | rep => exact h
    | conf => exact h
  · have h := H1.chanJ f hf
    cases f with
    | rep q r => exact hA q r h fun hq => hno.2 r (hq ▸ hf)
    | req => trivial
    | conf => trivial
  · have h := H2.chanI f hf
    cases f with
    | req q pu g =>
      obtain ⟨a1, a2, a3, a4, -⟩ := h
      exact ⟨a1, a2, a3, a4, fun _ _ => Or.inr ⟨_, rfl, a1⟩⟩
    | rep => exact h
    | conf => exact h
  · have h := H2.chanJ f hf
    cases f with
    | rep q r => exact hA' q r h
    | req => trivial
    | conf => trivial
  · have hle := H2.genLe pj hpj
    have hi : i = false := by
      cases i
      · rfl
      · simp only [takeNode_pend, hy rfl] at hpj; simp at hpj
    subst hi
    refine ⟨rfl, Or.inr (by simp only [takeNode_gen]; omega), fun ⟨hXi', hgi⟩ => ?_⟩
    rcases Nat.lt_or_ge pj.gen nj.gen with h | h
    · exact (H2.doom pj hpj h).2.2 ⟨hXi', hgi⟩
    · omega

/-- `j` takes the edge again while holding it (a chain that ends after a copy of its PUSH took the
edge, or a chain for an answered request): only `θ(e)`, the offer and the retake mark change. -/
def retakeNode (n : Node) : Node :=
  { n with offered := false, takes := n.takes + 1, retake := some n.seqc }

@[simp] theorem retakeNode_seqc (n : Node) : (retakeNode n).seqc = n.seqc := rfl
@[simp] theorem retakeNode_retake (n : Node) : (retakeNode n).retake = some n.seqc := rfl

theorem retake_pres {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) (hdj : ∀ pj, nj.pend = [pj] → pj.gen < nj.gen) :
    DInv i ni (retakeNode nj) ci cj ∧ DInv (!i) (retakeNode nj) ni cj ci := by
  have hA' : ∀ q r, A1 nj ni q r → A1 (retakeNode nj) ni q r := by
    rintro q r ⟨h1, h2, h3, h4⟩
    exact ⟨h1, h2, fun _ _ => Or.inr ⟨_, rfl, H2.not_fresh_le h1⟩, h4⟩
  refine ⟨{ H1 with }, { H2 with
      retakeLe := fun f hf => by simp at hf ⊢; omega
      chanI := fun f hf => ?_
      chanJ := fun f hf => ?_
      cacheJ := fun e he => hA' _ _ (H2.cacheJ e he)
      jobOld := fun q b hb hc => ⟨(H2.jobOld q b hb hc).1,
        Or.inr ⟨_, rfl, H2.not_fresh_le (H2.jobEx q b hb)⟩⟩
      live := fun pj hpj h => absurd h (Nat.ne_of_lt (hdj pj hpj))
      owe := fun h => by
        obtain ⟨-, -, pj, hpj, hg, -⟩ := H2.owe h
        exact absurd hg (Nat.ne_of_lt (hdj pj hpj)) }⟩
  · have h := H2.chanI f hf
    cases f with
    | req q pu g =>
      obtain ⟨a1, a2, a3, a4, -⟩ := h
      exact ⟨a1, a2, a3, a4, fun _ _ => Or.inr ⟨_, rfl, a1⟩⟩
    | rep => exact h
    | conf => exact h
  · have h := H2.chanJ f hf
    cases f with
    | rep q r => exact hA' q r h
    | req => trivial
    | conf => trivial


/-! ### Configurations -/

namespace St

@[simp] theorem nd_setNd_self (s : St) (i : Bool) (n : Node) : (s.setNd i n).nd i = n := by
  cases i <;> rfl
@[simp] theorem nd_setNd_not (s : St) (i : Bool) (n : Node) : (s.setNd i n).nd (!i) = s.nd (!i) := by
  cases i <;> rfl
@[simp] theorem nd_setNd_not' (s : St) (i : Bool) (n : Node) : (s.setNd (!i) n).nd i = s.nd i := by
  cases i <;> rfl
@[simp] theorem chan_setNd (s : St) (i k : Bool) (n : Node) : (s.setNd i n).chan k = s.chan k := by
  cases i <;> cases k <;> rfl
@[simp] theorem nd_setChan (s : St) (i k : Bool) (l : List Frame) : (s.setChan i l).nd k = s.nd k := by
  cases i <;> cases k <;> rfl
@[simp] theorem chan_setChan_self (s : St) (i : Bool) (l : List Frame) : (s.setChan i l).chan i = l := by
  cases i <;> rfl
@[simp] theorem chan_setChan_not (s : St) (i : Bool) (l : List Frame) :
    (s.setChan i l).chan (!i) = s.chan (!i) := by
  cases i <;> rfl
@[simp] theorem chan_setChan_not' (s : St) (i : Bool) (l : List Frame) :
    (s.setChan (!i) l).chan i = s.chan i := by
  cases i <;> rfl
@[simp] theorem send_eq (s : St) (i : Bool) (f : Frame) : s.send i f = s.setChan i (s.chan i ++ [f]) :=
  rfl
@[simp] theorem nd_acc (s : St) (x : List (Bool × ℕ)) (k : Bool) : ({ s with acc := x }).nd k = s.nd k := by
  cases k <;> rfl
@[simp] theorem chan_acc (s : St) (x : List (Bool × ℕ)) (k : Bool) :
    ({ s with acc := x }).chan k = s.chan k := by
  cases k <;> rfl
@[simp] theorem nd_ackd (s : St) (x : List (Bool × ℕ)) (k : Bool) :
    ({ s with ackd := x }).nd k = s.nd k := by
  cases k <;> rfl
@[simp] theorem chan_ackd (s : St) (x : List (Bool × ℕ)) (k : Bool) :
    ({ s with ackd := x }).chan k = s.chan k := by
  cases k <;> rfl

end St

theorem inv_of (t : St) (i : Bool) (h1 : DInv i (t.nd i) (t.nd !i) (t.chan i) (t.chan !i))
    (h2 : DInv (!i) (t.nd !i) (t.nd i) (t.chan !i) (t.chan i)) : Inv t := by
  cases i
  · exact ⟨h1, h2⟩
  · exact ⟨h2, h1⟩

theorem reply_nd_self (s : St) (j : Bool) (n : Node) (q : ℕ) (r : Rep) :
    (reply s j n q r).nd j = cachePut n q r := by
  unfold reply; split <;> simp
theorem reply_nd_not' (s : St) (j : Bool) (n : Node) (q : ℕ) (r : Rep) :
    (reply s (!j) n q r).nd j = s.nd j := by
  unfold reply; split <;> simp
theorem reply_chan_self (s : St) (j : Bool) (n : Node) (q : ℕ) (r : Rep) :
    (reply s j n q r).chan j = s.chan j ++ [.rep q r] := by
  unfold reply; split <;> simp
theorem reply_chan_not' (s : St) (j : Bool) (n : Node) (q : ℕ) (r : Rep) :
    (reply s (!j) n q r).chan j = s.chan j := by
  unfold reply; split <;> simp

/-- The invariant after `j = !i` answers request `q` of `i` from a configuration with the channel
from `i` already advanced. -/
theorem inv_reply {s1 : St} {i : Bool} {n : Node} {q : ℕ} {r : Rep}
    (h : DInv i (s1.nd i) (cachePut n q r) (s1.chan i) (s1.chan (!i) ++ [.rep q r]) ∧
      DInv (!i) (cachePut n q r) (s1.nd i) (s1.chan (!i) ++ [.rep q r]) (s1.chan i)) :
    Inv (reply s1 (!i) n q r) := by
  apply inv_of _ i
  · rw [reply_nd_self, reply_nd_not', reply_chan_self, reply_chan_not']; exact h.1
  · rw [reply_nd_self, reply_nd_not', reply_chan_self, reply_chan_not']; exact h.2

theorem accept_eq (n : Node) (room : Bool) :
    accept repairParams n room =
      if n.X = some true then (retakeNode n, true)
      else if (n.X = none ∧ n.dflt = true) ∨ room = true then (takeNode n, true)
      else (n, false) := by
  unfold accept
  by_cases h1 : n.X = some true
  · rw [ite_eq_left h1, ite_eq_left h1]; rfl
  · rw [ite_eq_right h1, ite_eq_right h1]
    by_cases h2 : n.X = none ∧ n.dflt = true
    · rw [ite_eq_left h2, ite_eq_left (Or.inl h2)]; rfl
    · rw [ite_eq_right h2]
      by_cases h3 : room = true
      · rw [ite_eq_left h3, ite_eq_left (Or.inr h3)]; rfl
      · rw [ite_eq_right h3,
          ite_eq_right (show ¬((n.X = none ∧ n.dflt = true) ∨ room = true) by tauto)]; rfl

theorem repeated_fresh {n : Node} {q : ℕ} (h : Fresh n.mark q) :
    repeated n q = ({ n with mark := some q }, false) := by
  unfold repeated
  cases hm : n.mark with
  | none => rfl
  | some m => have := h m hm; simp [Nat.not_le.2 this]

theorem repeated_old {n : Node} {q : ℕ} (h : ¬ Fresh n.mark q) : repeated n q = (n, true) := by
  simp only [Fresh, not_forall, not_lt] at h
  obtain ⟨m, hm, hq⟩ := h
  unfold repeated; rw [hm]; simp [hq]

theorem repOk_iff (n : Node) (g : ℕ) : repOk repairParams n g = true ↔ Okj n g := by
  simp [repOk, repairParams, Okj]


/-! ### The receiver's handlers -/

theorem DInv.fresh_head {i : Bool} {ni nj : Node} {q : ℕ} {pu : Bool} {g : ℕ} {l cj : List Frame}
    (H1 : DInv i ni nj (.req q pu g :: l) cj) (hfr : Fresh nj.mark q) :
    ∃ p, ni.pend = [p] ∧ p.seq = q ∧ pu = p.push ∧ g = p.gen := by
  obtain ⟨-, h2, h3, -, -⟩ := H1.chanI _ List.mem_cons_self
  obtain ⟨p, hp, hq⟩ := h3 hfr
  exact ⟨p, hp, hq, (h2 p hp hq).1, (h2 p hp hq).2⟩

theorem DInv.fresh_noAns {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    {q : ℕ} (hfr : Fresh nj.mark q) : NoAns nj cj q :=
  ⟨fun _ h => (H1.cacheJ _ h).1 hfr, fun _ h => (H1.chanJ _ h).1 hfr⟩

theorem DInv.fresh_hall {i : Bool} {ni nj : Node} {q : ℕ} {pu : Bool} {g : ℕ} {l cj : List Frame}
    (H1 : DInv i ni nj (.req q pu g :: l) cj) (hfr : Fresh nj.mark q) :
    ∀ q' pu' g', Frame.req q' pu' g' ∈ l → q' = q := by
  obtain ⟨p, hp, hpq, -, -⟩ := H1.fresh_head hfr
  have hs := H1.pend_seq hp
  intro q' pu' g' h
  have h1 := head_le H1.sorted h
  have h2 := H1.req_le (List.mem_cons_of_mem _ h)
  omega

/-- A request not yet executed cannot be acknowledged by the R3 rule. -/
theorem DInv.fresh_not_okj {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    {p : Pend} (hp : ni.pend = [p]) (hfr : Fresh nj.mark p.seq) : ¬ Okj nj p.gen := by
  intro hok
  rcases Nat.lt_or_ge p.gen ni.gen with h | h
  · exact (H1.doom p hp h).2.2 hok
  · have hl : p.gen = ni.gen := le_antisymm (H1.genLe p hp) h
    obtain ⟨-, -, p', hp', -, hnf, -⟩ := H1.owe (by rw [hok.2, hl])
    rw [hp, List.singleton_inj] at hp'; subst hp'
    exact hnf hfr

theorem CP.not_true {x y : Option Bool} (h : CP x y) (hx : x ≠ some false) : y ≠ some true := by
  rcases x with _ | _ | _ <;> rcases y with _ | _ | _ <;> simp_all [CP]

/-- A new request whose edge count matches the receiver's, at a receiver that does not yield, is
live and finds the receiver without the edge. -/
theorem DInv.fresh_live {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    (H2 : DInv (!i) nj ni cj ci) {p : Pend} (hp : ni.pend = [p]) (hg : nj.gen = p.gen)
    (hy : i = true → nj.pend = []) : p.gen = ni.gen ∧ nj.X ≠ some true := by
  have hlive : p.gen = ni.gen := by
    rcases Nat.lt_or_ge p.gen ni.gen with h | h
    · obtain ⟨hi, h2, -⟩ := H1.doom p hp h
      rcases h2 with h2 | h2
      · omega
      · obtain ⟨-, -, pj, hpj, -⟩ := H2.owe (by simpa using h2)
        rw [hy hi] at hpj; simp at hpj
    · exact le_antisymm (H1.genLe p hp) h
  exact ⟨hlive, (H1.bal (by omega)).not_true (H1.live p hp hlive).2⟩

/-- The refusal of a request just executed (stale, yielded, or without room). -/
theorem DInv.fresh_refuse {i : Bool} {ni nj : Node} {q : ℕ} {pu : Bool} {g : ℕ} {l cj : List Frame}
    (H1 : DInv i ni nj (.req q pu g :: l) cj) (hfr : Fresh nj.mark q) (pu' : Bool) :
    A1 ni { nj with mark := some q } q ⟨pu', false, false⟩ := by
  obtain ⟨p, hp, hpq, -, -⟩ := H1.fresh_head hfr
  refine ⟨by simp [fresh_some], fun p' hp' _ => ?_, fun h => by simp at h, fun b hb _ => ?_⟩
  · rw [hp, List.singleton_inj] at hp'; subst hp'
    have := H1.fresh_not_okj hp (hpq ▸ hfr)
    simp only [Okj] at this ⊢
    simpa using this
  · exact absurd hfr (H1.jobEx q b hb)

/-- The answer to a repeat that missed the cache (R3). -/
theorem DInv.repeat_A1 {i : Bool} {ni nj : Node} {q : ℕ} {pu : Bool} {g : ℕ} {l cj : List Frame}
    (H1 : DInv i ni nj (.req q pu g :: l) cj) (hnf : ¬ Fresh nj.mark q)
    (hjob : ∀ b, nj.job = some (q, b) → Cur ni q → False) :
    A1 ni nj q ⟨pu, repOk repairParams nj g, false⟩ := by
  obtain ⟨-, h2, -, -, h5⟩ := H1.chanI _ List.mem_cons_self
  refine ⟨hnf, fun p hp hq => ?_, fun h hc => h5 hc ((repOk_iff nj g).1 h),
    fun b hb hc => (hjob b hb hc).elim⟩
  rw [(h2 p hp hq).2]; exact repOk_iff nj p.gen


theorem inv_reply' {s1 : St} {i : Bool} {ni n : Node} {l cj : List Frame} {q : ℕ} {r : Rep}
    (e1 : s1.nd i = ni) (e3 : s1.chan i = l) (e4 : s1.chan (!i) = cj)
    (h : DInv i ni (cachePut n q r) l (cj ++ [.rep q r]) ∧
      DInv (!i) (cachePut n q r) ni (cj ++ [.rep q r]) l) :
    Inv (reply s1 (!i) n q r) := by
  subst e1 e3 e4; exact inv_reply h

theorem inv_local {t : St} {i : Bool} {ni nj : Node} {ci cj : List Frame} (e1 : t.nd i = ni)
    (e2 : t.nd (!i) = nj) (e3 : t.chan i = ci) (e4 : t.chan (!i) = cj)
    (h : DInv i ni nj ci cj ∧ DInv (!i) nj ni cj ci) : Inv t := by
  subst e1 e2 e3 e4; exact inv_of t i h.1 h.2

theorem mem_of_lookup {l : List (ℕ × Rep)} {q : ℕ} {r : Rep} (h : l.lookup q = some r) :
    (q, r) ∈ l := by
  obtain ⟨l1, l2, rfl, -⟩ := List.lookup_eq_some_iff.1 h
  simp

theorem yields_eq (i : Bool) (n : Node) :
    yields repairParams (!i) n = (!n.pend.isEmpty && i) := by
  simp [yields, repairParams]

theorem not_yields {i : Bool} {n : Node} (h : ¬ yields repairParams (!i) n = true) :
    i = true → n.pend = [] := by
  intro hi; subst hi
  rw [yields_eq] at h
  simpa using h

/-- The acknowledgement of a request the receiver has just taken. -/
theorem take_A1 {ni nj : Node} {p : Pend}
    (hp : ni.pend = [p]) (hm : ¬ Fresh nj.mark p.seq) (hg : nj.gen = p.gen) (pu : Bool) :
    A1 ni (takeNode nj) p.seq ⟨pu, true, false⟩ := by
  refine ⟨hm, fun p' hp' _ => ?_, fun _ hc => absurd ⟨p, hp, rfl⟩ hc, fun _ _ _ => rfl⟩
  rw [hp, List.singleton_inj] at hp'; subst hp'
  simp [Okj, hg]

/-- While `j` has executed the open request `p` of `i`, every request on the channel from `i` is a
copy of `p`. -/
theorem DInv.all_cur {i : Bool} {ni nj : Node} {ci cj : List Frame} (H1 : DInv i ni nj ci cj)
    {p : Pend} (hp : ni.pend = [p]) (hnf : ¬ Fresh nj.mark p.seq) :
    ∀ q pu g, Frame.req q pu g ∈ ci → q = p.seq := by
  intro q pu g h
  have hs := H1.pend_seq hp
  simp only [Fresh, not_forall, not_lt] at hnf
  obtain ⟨m, hm, hpm⟩ := hnf
  have h1 := (H1.chanI _ h).2.2.2.1 m hm
  have h2 := H1.req_le h
  have h3 := H1.markLe m hm
  omega

theorem onReq_pres {s : St} {i : Bool} {q : ℕ} {pu : Bool} {g : ℕ} {l : List Frame}
    (room chain : Bool) (H : Inv s) (hc : s.chan i = .req q pu g :: l) :
    Inv (onReq repairParams (s.setChan i l) (!i) q pu g room chain) := by
  have H1 := (inv_iff s).1 H i
  have H2 := (inv_iff s).1 H (!i)
  rw [Bool.not_not] at H2
  rw [hc] at H1 H2
  have e1 : (s.setChan i l).nd i = s.nd i := by simp
  have e2 : (s.setChan i l).nd (!i) = s.nd (!i) := by simp
  have e3 : (s.setChan i l).chan i = l := by simp
  have e4 : (s.setChan i l).chan (!i) = s.chan (!i) := by simp
  generalize s.setChan i l = s1 at e1 e2 e3 e4 ⊢
  generalize s.nd i = ni at H1 H2 e1
  generalize s.nd (!i) = nj at H1 H2 e2
  generalize s.chan (!i) = cj at H1 H2 e4
  unfold onReq
  rw [e2]
  cases hl : nj.cache.lookup q with
  | some r =>
    simp only [hl]
    have hm := mem_of_lookup hl
    have hT := tail_pres H1 H2
    exact inv_local (by simpa using e1) (by simpa using e2) (by simpa using e3)
      (by simpa using e4) (resend_pres hT.1 hT.2 (H1.cacheJ _ hm) (H1.cacheLate _ hm))
  | none =>
    simp only [hl]
    cases pu with
    | false =>
      simp only [Bool.not_false, ite_true]
      by_cases hfr : Fresh nj.mark q
      · rw [repeated_fresh hfr]
        simp only [Bool.false_eq_true, ite_false]
        have hF := fresh_pres H1 H2 hfr
        obtain ⟨p, hp, hpq, -, hgp⟩ := H1.fresh_head hfr
        subst hpq
        have hR := H1.fresh_refuse hfr false
        by_cases hgg : g = nj.gen
        · rw [ite_eq_right (not_not.2 hgg)]
          by_cases hy : yields repairParams (!i) { nj with mark := some p.seq } = true
          · rw [ite_eq_left hy]; exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
          · rw [ite_eq_right hy]
            have hy' := not_yields hy
            have hXj := (H1.fresh_live H2 hp (by omega) hy').2
            rw [accept_eq, ite_eq_right (show ¬ ({ nj with mark := some p.seq } : Node).X = some true
              from hXj)]
            by_cases hacc : (({ nj with mark := some p.seq } : Node).X = none ∧
                ({ nj with mark := some p.seq } : Node).dflt = true) ∨ room = true
            · rw [ite_eq_left hacc]
              have hT := take_pres hF.1 hF.2 hp (by simp [fresh_some]) (by simp; omega) hy'
                (H1.fresh_noAns hfr) (H1.fresh_hall hfr)
              exact inv_reply' e1 e3 e4 (answer_pres hT.1 hT.2
                (take_A1 (nj := { nj with mark := some p.seq }) hp (by simp [fresh_some])
                  (show nj.gen = p.gen by omega) false) rfl)
            · rw [ite_eq_right hacc]; exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
        · rw [ite_eq_left hgg]; exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
      · rw [repeated_old hfr]
        simp only [ite_true]
        have hT := tail_pres H1 H2
        refine inv_reply' e1 e3 e4 (answer_pres hT.1 hT.2 (H1.repeat_A1 hfr ?_) rfl)
        intro b hb ⟨p, hp, hq⟩
        obtain ⟨-, h2, -, -, -⟩ := H1.chanI _ List.mem_cons_self
        have := H1.jobPush q b p hb hp hq
        exact absurd ((h2 p hp hq).1.trans this) (by decide)
    | true =>
      simp only [Bool.not_true, Bool.false_eq_true, ite_false]
      cases hj : nj.job with
      | some jb =>
        obtain ⟨q', b⟩ := jb
        by_cases hq' : q' = q
        · -- a copy of the PUSH my chain serves
          subst hq'
          have hnf := H1.jobEx q' b hj
          have hT := tail_pres H1 H2
          have hny : yields repairParams (!i) nj = false := by
            rw [yields_eq]
            cases i
            · simp
            · simp [H2.jobA rfl (by simp [hj])]
          simp only [decide_true, ite_true, hny, Bool.false_or, Bool.not_true,
            Bool.false_and, Bool.false_eq_true, ite_false, Bool.true_and]
          by_cases hX : nj.X = some true
          · simp only [hX]
            refine inv_reply' e1 e3 e4 (answer_pres (r := ⟨true, true, false⟩) hT.1 hT.2 ⟨hnf, fun p hp hq => ?_,
              fun _ hc => (H1.jobOld q' b hj hc).2, fun _ _ _ => hX⟩ rfl)
            rcases H1.jobGen q' b p hj hp hq with ⟨-, h⟩ | ⟨h, -⟩
            · exact absurd hX h
            · simp [Okj, hX, h]
          · have hc : Cur ni q' := by
              by_contra hc; exact hX (H1.jobOld q' b hj hc).1
            obtain ⟨p, hp, hpq⟩ := hc
            subst hpq
            have hg : nj.gen = p.gen := by
              rcases H1.jobGen p.seq b p hj hp rfl with ⟨h, -⟩ | ⟨-, h⟩
              · exact h
              · exact absurd h hX
            have hy : i = true → nj.pend = [] := fun hi => by
              subst hi; exact H2.jobA rfl (by simp [hj])
            have hno : NoAns nj cj p.seq := ⟨fun r h => hX ((H1.cacheJ _ h).2.2.2 b hj ⟨p, hp, rfl⟩),
              fun r h => hX ((H1.chanJ _ h).2.2.2 b hj ⟨p, hp, rfl⟩)⟩
            simp only [hX]
            by_cases hacc : (nj.X = none ∧ nj.dflt = true) ∨ room = true
            · rw [ite_eq_left hacc, accept_eq, ite_eq_right hX, ite_eq_left hacc]
              simp only [decide_false]
              have hK := take_pres hT.1 hT.2 hp hnf hg hy hno
                (fun q pu g h => H1.all_cur hp hnf q pu g (List.mem_cons_of_mem _ h))
              exact inv_reply' e1 e3 e4 (answer_pres hK.1 hK.2 (take_A1 hp hnf hg true) rfl)
            · rw [ite_eq_right hacc]
              simp only [repairParams, Bool.true_and, ite_true]
              exact inv_local e1 e2 e3 e4 hT
        · have hnb : ∀ b', nj.job ≠ some (q, b') := fun b' h => by
            rw [hj] at h; simp at h; exact hq' h.1
          simp only [hq', decide_false, Bool.false_eq_true, ite_false]
          by_cases hfr : Fresh nj.mark q
          · rw [repeated_fresh hfr]
            simp only [Bool.false_eq_true, ite_false]
            have hF := fresh_pres H1 H2 hfr
            obtain ⟨p, hp, hpq, hpu, hgp⟩ := H1.fresh_head hfr
            subst hpq
            have hR := H1.fresh_refuse hfr true
            by_cases hgg : g = nj.gen
            · by_cases hy : yields repairParams (!i) { nj with mark := some p.seq } = true
              · simp only [hy, Bool.true_or, ite_true]
                exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
              · have hy' := not_yields hy
                have hXj := (H1.fresh_live H2 hp (by omega) hy').2
                simp only [hy, hgg, ne_eq, not_true_eq_false, decide_false, Bool.false_or,
                  Bool.not_false, Bool.and_false, Bool.false_eq_true, ite_false]
                rw [accept_eq, ite_eq_right (show ¬ ({ nj with mark := some p.seq } : Node).X =
                  some true from hXj)]
                by_cases hacc : (({ nj with mark := some p.seq } : Node).X = none ∧
                    ({ nj with mark := some p.seq } : Node).dflt = true) ∨ room = true
                · rw [ite_eq_left hacc]
                  simp only [Bool.false_and, Bool.false_eq_true, ite_false, ite_true]
                  have hT := take_pres hF.1 hF.2 hp (by simp [fresh_some]) (by simp; omega) hy'
                    (H1.fresh_noAns hfr) (H1.fresh_hall hfr)
                  exact inv_reply' e1 e3 e4 (answer_pres hT.1 hT.2
                    (take_A1 (nj := { nj with mark := some p.seq }) hp (by simp [fresh_some])
                      (show nj.gen = p.gen by omega) true) rfl)
                · rw [ite_eq_right hacc]
                  simp only [Bool.false_and, Bool.false_eq_true, ite_false, ite_true]
                  simp only [hj]
                  rw [hj] at hF hR
                  rw [ite_eq_right (show ¬ q' = p.seq from hq')]
                  exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
            · simp only [hgg, ne_eq, not_false_eq_true, decide_true, Bool.not_false, Bool.and_true,
                Bool.or_true, ite_true]
              exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
          · rw [repeated_old hfr]
            simp only [ite_true]
            have hT := tail_pres H1 H2
            exact inv_reply' e1 e3 e4 (answer_pres hT.1 hT.2
              (H1.repeat_A1 hfr fun b hb _ => hnb b hb) rfl)
      | none =>
        have hnb : ∀ b', nj.job ≠ some (q, b') := fun b' h => by rw [hj] at h; simp at h
        simp only [Bool.false_eq_true, ite_false]
        by_cases hfr : Fresh nj.mark q
        · rw [repeated_fresh hfr]
          simp only [Bool.false_eq_true, ite_false]
          have hF := fresh_pres H1 H2 hfr
          obtain ⟨p, hp, hpq, hpu, hgp⟩ := H1.fresh_head hfr
          subst hpq
          have hR := H1.fresh_refuse hfr true
          by_cases hgg : g = nj.gen
          · by_cases hy : yields repairParams (!i) { nj with mark := some p.seq } = true
            · simp only [hy, Bool.true_or, ite_true]
              exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
            · have hy' := not_yields hy
              have hXj := (H1.fresh_live H2 hp (by omega) hy').2
              simp only [hy, hgg, ne_eq, not_true_eq_false, decide_false, Bool.false_or,
                Bool.not_false, Bool.and_false, Bool.false_eq_true, ite_false]
              rw [accept_eq, ite_eq_right (show ¬ ({ nj with mark := some p.seq } : Node).X =
                some true from hXj)]
              by_cases hacc : (({ nj with mark := some p.seq } : Node).X = none ∧
                  ({ nj with mark := some p.seq } : Node).dflt = true) ∨ room = true
              · rw [ite_eq_left hacc]
                simp only [Bool.false_and, Bool.false_eq_true, ite_false, ite_true]
                have hT := take_pres hF.1 hF.2 hp (by simp [fresh_some]) (by simp; omega) hy'
                  (H1.fresh_noAns hfr) (H1.fresh_hall hfr)
                exact inv_reply' e1 e3 e4 (answer_pres hT.1 hT.2
                  (take_A1 (nj := { nj with mark := some p.seq }) hp (by simp [fresh_some])
                    (show nj.gen = p.gen by omega) true) rfl)
              · rw [ite_eq_right hacc]
                simp only [Bool.false_and, Bool.false_eq_true, ite_false, ite_true]
                simp only [hj]
                rw [hj] at hF hR
                cases chain with
                | true =>
                  simp only [ite_true]
                  have hK := jobStart_pres hF.1 hF.2 hp (by simp [fresh_some]) hXj
                    (by simp; omega) hpu.symm hy' (H1.fresh_noAns hfr)
                  exact inv_local (by simpa using e1) (by simp) (by simpa using e3)
                    (by simpa using e4) hK
                | false =>
                  simp only [Bool.false_eq_true, ite_false]
                  exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
          · simp only [hgg, ne_eq, not_false_eq_true, decide_true, Bool.not_false, Bool.and_true,
                Bool.or_true, ite_true]
            exact inv_reply' e1 e3 e4 (answer_pres hF.1 hF.2 hR rfl)
        · rw [repeated_old hfr]
          simp only [ite_true]
          have hT := tail_pres H1 H2
          exact inv_reply' e1 e3 e4 (answer_pres hT.1 hT.2
            (H1.repeat_A1 hfr fun b hb _ => hnb b hb) rfl)


/-! ### The requester's handler -/

/-- The node of the requester after `onRep`, as in its definition, with `P = repairParams`. -/
def repNode (n : Node) (seq : ℕ) (r : Rep) : Node :=
  match n.pend.find? (·.seq = seq) with
  | some p =>
    let n1 := { n with pend := n.pend.filter (·.seq ≠ seq) }
    if r.ok then (if n1.takes = p.theta then release n1 else n1) else n1
  | none =>
    if !r.ok then n
    else if n.X = some false then n
    else if !n.offered then n
    else if repairParams.floorCheck && (match n.retake with | some f => decide (seq ≤ f) | none => false)
      then n
    else release n

theorem onRep_eq (s : St) (i : Bool) (seq : ℕ) (r : Rep) (hl : r.late = false) :
    onRep repairParams s i seq r =
      (if r.ok then { s with ackd := s.ackd ++ [(i, seq)] } else s).setNd i
        (repNode (s.nd i) seq r) := by
  unfold onRep repNode
  cases r.ok <;> simp [hl] <;> rfl

/-- A positive answer to a request that is not open changes nothing (`Harm`). -/
theorem repNode_late {n : Node} {q : ℕ} {r : Rep} (hnone : n.pend.find? (·.seq = q) = none)
    (hh : r.ok = true → Harm n q) : repNode n q r = n := by
  unfold repNode
  rw [hnone]
  cases hr : r.ok
  · simp
  · rcases hh hr with h | ⟨f, hf, hq⟩
    · simp [h]
    · simp [hf, hq, repairParams]

theorem onRep_pres {s : St} {i : Bool} {q : ℕ} {r : Rep} {l : List Frame} (H : Inv s)
    (hc : s.chan i = .rep q r :: l) : Inv (onRep repairParams (s.setChan i l) (!i) q r) := by
  have Hi := (inv_iff s).1 H i
  have Hk := (inv_iff s).1 H (!i)
  rw [Bool.not_not] at Hk
  rw [hc] at Hi Hk
  have hA : A1 (s.nd !i) (s.nd i) q r := Hk.chanJ _ List.mem_cons_self
  have hl : r.late = false := Hi.chanI _ List.mem_cons_self
  have hT := tail_pres Hi Hk
  rw [onRep_eq _ _ _ _ hl]
  have key : DInv i (s.nd i) (repNode (s.nd !i) q r) l (s.chan !i) ∧
      DInv (!i) (repNode (s.nd !i) q r) (s.nd i) (s.chan !i) l := by
    generalize s.nd i = nr at hA hT
    generalize s.nd (!i) = nk at hA hT
    generalize s.chan (!i) = ck at hT
    obtain ⟨T1, T2⟩ := hT
    rcases T2.pend with hp | ⟨p, hp, -⟩
    · rw [repNode_late (by simp [hp]) fun hr => hA.2.2.1 hr fun ⟨p, h, _⟩ => by simp [hp] at h]
      exact ⟨T1, T2⟩
    · by_cases hq : p.seq = q
      · subst hq
        have hfind : nk.pend.find? (·.seq = p.seq) = some p := by simp [hp]
        have hfil : nk.pend.filter (·.seq ≠ p.seq) = [] := by simp [hp]
        unfold repNode
        rw [hfind]
        simp only [hfil]
        cases hr : r.ok
        · simp only [Bool.false_eq_true, ite_false]
          have := neg_pres T2 (by rw [Bool.not_not]; exact T1) hp hA hr
          rw [Bool.not_not] at this
          exact ⟨this.2, this.1⟩
        · have hok : Okj nr p.gen := (hA.2.1 p hp rfl).1 hr
          have hθ := (T2.live p hp (T2.pos_live hp hok)).1
          simp only [ite_true]
          rw [ite_eq_left hθ]
          have := pos_pres T2 (by rw [Bool.not_not]; exact T1) hp hA hr
          rw [Bool.not_not] at this
          exact ⟨this.2, this.1⟩
      · rw [repNode_late (by simp [hp, hq]) fun hr => hA.2.2.1 hr fun ⟨p', h, h'⟩ => by
          rw [hp, List.singleton_inj] at h; subst h; exact hq h']
        exact ⟨T1, T2⟩
  apply inv_local (i := i) _ _ _ _ key <;> cases r.ok <;> simp


/-! ### The end of a push chain -/

theorem finish_pres {s t : St} {k : Bool} {ok room : Bool} (H : Inv s)
    (h : finishJob repairParams s (!k) ok room = some t) : Inv t := by
  have H1 := (inv_iff s).1 H k
  have H2 := (inv_iff s).1 H (!k)
  rw [Bool.not_not] at H2
  unfold finishJob at h
  cases hj : (s.nd !k).job with
  | none => simp [hj] at h
  | some jb =>
    obtain ⟨q, nacked⟩ := jb
    have hn : nacked = false := H2.job q nacked hj
    subst hn
    simp only [hj, Bool.and_false, Bool.false_eq_true, ite_false, Option.some.injEq,
      repairParams_finalBusy, repairParams_finalNack, Bool.not_false, Bool.and_true] at h
    subst h
    generalize hni : s.nd k = ni at H1 H2
    generalize hnj : s.nd (!k) = nj at H1 H2 hj
    generalize hci : s.chan k = ci at H1 H2
    generalize hcj : s.chan (!k) = cj at H1 H2
    have hnf := H1.jobEx q false hj
    have hE := jobEnd_pres H1 H2
    by_cases hX : nj.X = some true
    · -- the receiver holds the edge: the answer is positive
      have hdj : ∀ pj, ({ nj with job := none } : Node).pend = [pj] →
          pj.gen < ({ nj with job := none } : Node).gen :=
        fun pj hpj => H1.jobPendX q false pj hj hpj hX
      have hA1 : ∀ n : Node, n.X = some true → n.gen = nj.gen → n.mark = nj.mark → n.job = none →
          A1 ni n q ⟨true, true, false⟩ := by
        intro n hnX hng hnm hnj'
        refine ⟨hnm ▸ hnf, fun p hp hq => ?_, fun _ hc => ?_, fun b hb => by simp [hnj'] at hb⟩
        · rcases H1.jobGen q false p hj hp hq with ⟨-, h⟩ | ⟨h, -⟩
          · exact absurd hX h
          · simp [Okj, hnX, hng, h]
        · exact (H1.jobOld q false hj hc).2
      cases ok with
      | true =>
        simp only [ite_true]
        rw [accept_eq, ite_eq_left (show ({ nj with job := none } : Node).X = some true from hX)]
        simp only [Bool.true_or]
        have hR := retake_pres hE.1 hE.2 hdj
        exact inv_reply' hni hci hcj
          (answer_pres hR.1 hR.2 (hA1 _ hX rfl rfl rfl) rfl)
      | false =>
        simp only [Bool.false_eq_true, ite_false, Bool.false_or, decide_eq_true hX]
        exact inv_reply' hni hci hcj
          (answer_pres hE.1 hE.2 (hA1 _ hX rfl rfl rfl) rfl)
    · -- the chain serves the open PUSH `p`, and nothing answered it yet
      have hc : Cur ni q := by by_contra hc; exact hX (H1.jobOld q false hj hc).1
      obtain ⟨p, hp, hpq⟩ := hc
      subst hpq
      have hg : nj.gen = p.gen := by
        rcases H1.jobGen p.seq false p hj hp rfl with ⟨h, -⟩ | ⟨-, h⟩
        · exact h
        · exact absurd h hX
      have hno : NoAns { nj with job := none } cj p.seq :=
        ⟨fun r h => hX ((H1.cacheJ _ h).2.2.2 false hj ⟨p, hp, rfl⟩),
          fun r h => hX ((H1.chanJ _ h).2.2.2 false hj ⟨p, hp, rfl⟩)⟩
      have hy : k = true → ({ nj with job := none } : Node).pend = [] := fun hk => by
        subst hk; exact H2.jobA rfl (by simp [hj])
      have hR : A1 ni { nj with job := none } p.seq ⟨true, false, false⟩ := by
        refine ⟨hnf, fun p' hp' _ => ?_, fun h => by simp at h, fun b hb => by simp at hb⟩
        simp only [Okj]
        exact ⟨fun h => by simp at h, fun h => absurd h.1 hX⟩
      cases ok with
      | true =>
        simp only [ite_true]
        rw [accept_eq, ite_eq_right (show ¬ ({ nj with job := none } : Node).X = some true from hX)]
        by_cases hacc : (({ nj with job := none } : Node).X = none ∧
            ({ nj with job := none } : Node).dflt = true) ∨ room = true
        · rw [ite_eq_left hacc]
          simp only [Bool.true_or]
          have hK := take_pres hE.1 hE.2 hp hnf hg hy hno (H1.all_cur hp hnf)
          exact inv_reply' hni hci hcj
            (answer_pres hK.1 hK.2 (take_A1 (nj := { nj with job := none }) hp hnf hg true) rfl)
        · rw [ite_eq_right hacc]
          simp only [Bool.false_or, decide_eq_false hX]
          exact inv_reply' hni hci hcj
            (answer_pres hE.1 hE.2 hR rfl)
      | false =>
        simp only [Bool.false_eq_true, ite_false, Bool.false_or, decide_eq_false hX]
        exact inv_reply' hni hci hcj
          (answer_pres hE.1 hE.2 hR rfl)


/-! ### Every event -/

theorem step_pres {s t : St} {e : Ev} (H : Inv s) (h : step repairParams s e = some t) : Inv t := by
  cases e with
  | offer i push =>
    simp only [step] at h
    split_ifs at h with hc
    obtain ⟨ho, hj, hpe⟩ := hc
    simp only [Option.some.injEq] at h
    subst h
    have H1 := (inv_iff s).1 H i
    have H2 := (inv_iff s).1 H (!i)
    rw [Bool.not_not] at H2
    exact inv_local (i := i) (by simp; rfl) (by simp) (by simp) (by simp)
      (offer_pres H1 H2 push ho hj hpe)
  | retx i seq =>
    simp only [step] at h
    split at h
    · rename_i p hp
      simp only [Option.some.injEq] at h
      subst h
      have H1 := (inv_iff s).1 H i
      have H2 := (inv_iff s).1 H (!i)
      rw [Bool.not_not] at H2
      have hpp : (s.nd i).pend = [p] := by
        have hm := List.mem_of_find?_eq_some hp
        rcases H1.pend with h0 | ⟨p', h0, -⟩
        · simp [h0] at hm
        · rw [h0, List.mem_singleton] at hm; subst hm; exact h0
      exact inv_local (i := i) (by simp) (by simp) (by simp) (by simp) (retx_pres H1 H2 hpp)
    · simp at h
  | lretx i seq =>
    have H1 := (inv_iff s).1 H i
    simp [step, H1.late] at h
  | evict i seq =>
    simp only [step, Option.some.injEq] at h
    subst h
    have H1 := (inv_iff s).1 H i
    have H2 := (inv_iff s).1 H (!i)
    rw [Bool.not_not] at H2
    exact inv_local (i := i) (by simp) (by simp) (by simp) (by simp) (evict_pres H1 H2 seq)
  | flip i =>
    simp only [step, Option.some.injEq] at h
    subst h
    have H1 := (inv_iff s).1 H i
    have H2 := (inv_iff s).1 H (!i)
    rw [Bool.not_not] at H2
    exact inv_local (i := i) (by simp) (by simp) (by simp) (by simp) (flip_pres H1 H2)
  | lose i =>
    simp only [step] at h
    split at h
    · simp at h
    · rename_i f l hc
      simp only [Option.some.injEq] at h
      subst h
      have H1 := (inv_iff s).1 H i
      have H2 := (inv_iff s).1 H (!i)
      rw [Bool.not_not] at H2
      rw [hc] at H1 H2
      exact inv_local (i := i) (by simp) (by simp) (by simp) (by simp) (tail_pres H1 H2)
  | deliver i room chain =>
    simp only [step] at h
    split at h
    · simp at h
    · rename_i f l hc
      cases f with
      | req q pu g =>
        simp only [Option.some.injEq] at h; subst h
        exact onReq_pres room chain H hc
      | rep q r =>
        simp only [Option.some.injEq] at h; subst h
        exact onRep_pres H hc
      | conf q =>
        have H1 := (inv_iff s).1 H i
        rw [hc] at H1
        exact (H1.chanI _ List.mem_cons_self).elim
  | finish i ok room =>
    have := @finish_pres s t (!i) ok room H
    rw [Bool.not_not] at this
    exact this h

theorem runEvs_pres {s t : St} {es : List Ev} (H : Inv s) (h : runEvs repairParams s es = some t) :
    Inv t := by
  induction es generalizing s with
  | nil => simp [runEvs] at h; exact h ▸ H
  | cons e es ih =>
    simp only [runEvs] at h
    cases he : step repairParams s e with
    | none => simp [he] at h
    | some s' => simp [he] at h; exact ih (step_pres H he) h

/-- In a quiet configuration the two settled decisions are complementary or both absent. -/
theorem cp_of_quiet {s : St} (H : Inv s) (hq : Quiet s) : CP s.a.X s.b.X := by
  obtain ⟨Ha, Hb⟩ := H
  simp only [Quiet, quietB, Bool.and_eq_true, List.isEmpty_iff] at hq
  have hpa : s.a.pend = [] := hq.1.1.1.1.1.2
  have hpb : s.b.pend = [] := hq.1.1.1.1.2
  have hab : s.a.gen = s.b.gen := by
    have g1 := Ha.gap
    have g2 := Hb.gap
    rcases Nat.lt_or_ge s.a.gen s.b.gen with h | h
    · obtain ⟨-, -, p, hp, -⟩ := Ha.owe (by omega); simp [hpa] at hp
    · rcases Nat.lt_or_ge s.b.gen s.a.gen with h' | h'
      · obtain ⟨-, -, p, hp, -⟩ := Hb.owe (by omega); simp [hpb] at hp
      · omega
  exact Ha.bal hab

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms step_pres
open SwarmInfer.CoverWeave.ExecFull in
#print axioms cp_of_quiet
