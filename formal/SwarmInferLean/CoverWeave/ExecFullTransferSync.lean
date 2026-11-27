import SwarmInferLean.CoverWeave.ExecFullTransferLive
import SwarmInferLean.CoverWeave.ExecFullTransferRepair

/-!
# CoverWeave, Lemma 4 (`lem:lossless`, inventory C9) for the transfer layer, synchronous scheduler

Source: `CoverWeave_R1/sections/04-formaleng.tex:127-137`, Lemma `lem:lossless` and its proof, for
the transfer layer of one flexible edge under the repairs of `ExecFullTransferRepair.lean`.

The synchronous scheduler. `slot E t s` delivers every frame in flight at the start of slot `t`,
in order (no loss), first those from `a` to `b`, then those from `b` to `a`; then the chains that
end in `t` answer (`E.fin`), the timers that fire in `t` retransmit the open request (`E.rx`), and
evictions and budget changes happen (`E.misc`). The receivers' room and chain decisions are the
environment's (`E.room`, `E.chain`), unrestricted. No offer is made in a slot. `srun E s₀ t` is the
configuration at the start of slot `t`.

Results.
* `closes`: if `i`'s timer fires at least once in every `Tr` slots and the chain at `!i` ends at
  least once in every `d` slots, `i` has no open request `Tr + d + 2` slots after any slot.
* `transfer_window`: with both ends' timers and chains so bounded, from every configuration that
  satisfies the invariant, the configuration `Tr + 2 d + 3` slots after any slot is quiet.
* `transfer_window_owner`: the same from the start of Phase 4 after any finite prefix of events
  (losses and offers included), with exactly one owner at the end.
* `quiet_after_last_offer`: in a run whose slots may also offer (`EnvO`), quiet and one owner
  `Tr + 2 d + 3` slots after the last offer.

Added hypotheses (the paper states none of them for this layer, and the code fixes only some):
* no new offer in the window (built into `slot`); the paper's proof bounds new offers by its
  potential `(Γ, Θ)`, which concerns the other edges and is not modelled here;
* every timer fires at least once in every `Tr` slots: in the code the timer of an open request
  fires after `ack_timeout` and then with doubling backoff capped at `R_max` sends, so
  `Tr` = the capped backoff interval in slots;
* every chain ends at least once in every `d` slots: in the code a chain of depth `ttl ≤ D_max`
  ends when its last hop answers, so `d` is bounded by the chain's own window, which this
  one-edge model leaves to the environment.
-/

namespace SwarmInfer.CoverWeave.ExecFull

/-! ### What a delivered request can do, in general -/

/-- The effect of `onReq` at the receiver `j`, for any chain state of `j`. -/
structure ReqView (s1 : St) (j : Bool) (q : ℕ) (t : St) : Prop where
  other : t.nd (!j) = s1.nd (!j)
  otherChan : t.chan (!j) = s1.chan (!j)
  chan : t.chan j = s1.chan j ∨ ∃ r, t.chan j = s1.chan j ++ [.rep q r]
  pend : (t.nd j).pend = (s1.nd j).pend
  job : (t.nd j).job = (s1.nd j).job ∨ ((s1.nd j).job = none ∧ (t.nd j).job = some (q, false))
  noAns : t.chan j = s1.chan j → (t.nd j).job = some (q, false) ∨ ∃ b, (s1.nd j).job = some (q, b)
  jobFresh : (s1.nd j).job = none → (t.nd j).job ≠ none → Fresh (s1.nd j).mark q

theorem reqView_reply {s1 : St} {j : Bool} {q : ℕ} {n : Node} {r : Rep}
    (hj : n.job = (s1.nd j).job) (hp : n.pend = (s1.nd j).pend) : ReqView s1 j q (reply s1 j n q r) :=
  ⟨reply_nd_not .., reply_chan_not .., Or.inr ⟨r, reply_chan_self ..⟩,
    by rw [reply_nd_self]; simpa using hp, Or.inl (by rw [reply_nd_self]; simpa using hj),
    fun h => by rw [reply_chan_self] at h; simp at h,
    fun h1 h2 => by rw [reply_nd_self] at h2; simp [hj, h1] at h2⟩

theorem fresh_of_repeated {n : Node} {q : ℕ} (h : ¬ (repeated n q).2 = true) : Fresh n.mark q := by
  intro m hm
  unfold repeated at h; rw [hm] at h
  by_contra hc; simp [Nat.le_of_not_lt hc] at h

theorem onReq_view (s1 : St) (j : Bool) (q : ℕ) (pu : Bool) (g : ℕ) (room chain : Bool) :
    ReqView s1 j q (onReq repairParams s1 j q pu g room chain) := by
  unfold onReq
  cases hl : (s1.nd j).cache.lookup q with
  | some r =>
    simp only [hl]
    exact ⟨by simp, by simp, Or.inr ⟨r, by simp⟩, by simp, Or.inl (by simp),
      fun h => by simp at h, fun h1 h2 => by simp [h1] at h2⟩
  | none =>
    simp only [hl]
    cases pu
    · simp only [Bool.not_false, ite_true]
      split_ifs <;> exact reqView_reply (by simp) (by simp)
    · simp only [Bool.not_true, Bool.false_eq_true, ite_false]
      cases hj : (s1.nd j).job with
      | none =>
        simp only [Bool.false_eq_true, ite_false, Bool.not_false, Bool.true_and, Bool.and_false]
        split_ifs <;> first
          | (exfalso; simp_all; done)
          | exact reqView_reply (by simp [hj]) (by simp)
          | (simp only [accept_job, repeated_job, hj]; exact reqView_reply (by simp [hj]) (by simp))
          | (simp only [accept_job, repeated_job, hj]
             exact ⟨by simp, by simp, Or.inl (by simp), by simp,
              Or.inr ⟨hj, by simp⟩, fun _ => Or.inl (by simp),
              fun _ _ => fresh_of_repeated ‹¬ (repeated (s1.nd j) q).2 = true›⟩)
      | some jb =>
        obtain ⟨q', b⟩ := jb
        by_cases hq : q' = q
        · subst hq
          simp only [decide_true, ite_true, Bool.not_true, Bool.false_and,
            Bool.false_eq_true, ite_false, Bool.true_and]
          split_ifs <;> first
            | (exfalso; simp [repairParams] at *; done)
            | exact reqView_reply (by simp [hj]) (by simp)
            | exact ⟨by simp, by simp, Or.inl rfl, rfl, Or.inl rfl, fun _ => Or.inr ⟨b, hj⟩,
                fun h => by simp [hj] at h⟩
        · simp only [hq, decide_false, Bool.false_eq_true, ite_false, Bool.not_false, Bool.true_and,
            Bool.and_false]
          split_ifs <;> first
            | exact reqView_reply (by simp [hj]) (by simp)
            | (simp only [accept_job, repeated_job, hj, ite_false, hq]
               exact reqView_reply (by simp [hj]) (by simp))


theorem onRep_pend_other (P : Params) (s1 : St) (i : Bool) (q : ℕ) (r : Rep) {p : Pend}
    (hp : (s1.nd i).pend = [p]) (hq : p.seq ≠ q) : ((onRep P s1 i q r).nd i).pend = [p] := by
  unfold onRep
  cases r.ok <;> cases r.late <;> simp [hp, hq] <;> split_ifs <;> simp_all [release]

/-! ### Synchronous slots -/

/-- An event, skipped when it is not enabled. -/
def stepT (s : St) (e : Ev) : St := (step repairParams s e).getD s

def evsT : St → List Ev → St
  | s, [] => s
  | s, e :: es => evsT (stepT s e) es

theorem stepT_inv {s : St} (H : Inv s) (e : Ev) : Inv (stepT s e) := by
  unfold stepT
  cases h : step repairParams s e with
  | none => exact H
  | some t => exact step_pres H h

theorem evsT_inv {s : St} (H : Inv s) (es : List Ev) : Inv (evsT s es) := by
  induction es generalizing s with
  | nil => exact H
  | cons e es ih => exact ih (stepT_inv H e)

/-- The environment of a run: the choices the rest of the protocol makes in each slot. -/
structure Env where
  /-- the `k`-th delivery from `i`'s channel in slot `t` finds room / may start a chain -/
  room : ℕ → Bool → ℕ → Bool
  chain : ℕ → Bool → ℕ → Bool
  /-- `i`'s retransmission timer fires in slot `t` -/
  rx : ℕ → Bool → Bool
  /-- `i`'s push chain ends in slot `t`, with its outcome -/
  fin : ℕ → Bool → Option (Bool × Bool)
  /-- other events of slot `t`: cache evictions and budget changes -/
  misc : ℕ → List Ev

def delivs (E : Env) (t : ℕ) (i : Bool) (n : ℕ) : List Ev :=
  (List.range n).map fun k => .deliver i (E.room t i k) (E.chain t i k)

def finEv (E : Env) (t : ℕ) (i : Bool) : List Ev :=
  match E.fin t i with
  | some (ok, room) => [.finish i ok room]
  | none => []

def rxEv (E : Env) (t : ℕ) (i : Bool) (s : St) : List Ev :=
  if E.rx t i then [.retx i (s.nd i).seqc] else []

/-- One synchronous slot: every frame in flight at its start is delivered (no loss), each end
first processes what the other sent, then the chains that end answer, then the timers that fire
retransmit, then evictions and budget changes. No offer is made. -/
def slotEvs (E : Env) (t : ℕ) (s : St) : List Ev :=
  delivs E t false s.fromA.length ++ delivs E t true s.fromB.length ++ finEv E t false ++
    finEv E t true ++ rxEv E t false s ++ rxEv E t true s ++ E.misc t

def slot (E : Env) (t : ℕ) (s : St) : St := evsT s (slotEvs E t s)

/-- The run of `E` from `s₀`: the configuration at the start of slot `t`. -/
def srun (E : Env) (s₀ : St) : ℕ → St
  | 0 => s₀
  | t + 1 => slot E t (srun E s₀ t)

theorem srun_inv {E : Env} {s₀ : St} (H : Inv s₀) : ∀ t, Inv (srun E s₀ t)
  | 0 => H
  | t + 1 => evsT_inv (srun_inv H t) _

theorem evsT_append (s : St) (es es' : List Ev) : evsT s (es ++ es') = evsT (evsT s es) es' := by
  induction es generalizing s with
  | nil => rfl
  | cons e es ih => exact ih _


/-! ### Progress of one open request -/

/-- The open request `p` of `i` has an answer in flight. -/
def Ans (s : St) (i : Bool) (p : Pend) : Prop := ∃ r, Frame.rep p.seq r ∈ s.chan (!i)
/-- `j = !i` runs a push chain for it. -/
def HJob (s : St) (i : Bool) (p : Pend) : Prop := ∃ b, (s.nd !i).job = some (p.seq, b)
/-- A copy of it is in flight. -/
def Cpy (s : St) (i : Bool) (p : Pend) : Prop := ∃ pu g, Frame.req p.seq pu g ∈ s.chan i

/-- Level `k` of the progress of `i`'s request: closed, or open with an answer in flight
(`k ≥ 1`), a chain serving it (`k ≥ 2`) or a copy in flight (`k ≥ 3`). -/
def Lv (k : ℕ) (s : St) (i : Bool) : Prop :=
  (s.nd i).pend = [] ∨ ∃ p, (s.nd i).pend = [p] ∧
    ((1 ≤ k ∧ Ans s i p) ∨ (2 ≤ k ∧ HJob s i p) ∨ (3 ≤ k ∧ Cpy s i p))

theorem Lv.mono {k k' : ℕ} {s : St} {i : Bool} (h : Lv k s i) (hk : k ≤ k') : Lv k' s i := by
  rcases h with h | ⟨p, hp, h⟩
  · exact Or.inl h
  · refine Or.inr ⟨p, hp, ?_⟩
    rcases h with ⟨h1, h⟩ | ⟨h1, h⟩ | ⟨h1, h⟩
    · exact Or.inl ⟨by omega, h⟩
    · exact Or.inr (Or.inl ⟨by omega, h⟩)
    · exact Or.inr (Or.inr ⟨by omega, h⟩)

/-- Every piece of evidence survives. -/
theorem lv_gen {k : ℕ} {s t : St} {i : Bool} (hp : (t.nd i).pend = (s.nd i).pend)
    (hA : ∀ q r, Frame.rep q r ∈ s.chan (!i) → Frame.rep q r ∈ t.chan (!i))
    (hJ : ∀ x, (s.nd !i).job = some x → (t.nd !i).job = some x)
    (hC : ∀ q pu g, Frame.req q pu g ∈ s.chan i → Frame.req q pu g ∈ t.chan i)
    (h : Lv k s i) : Lv k t i := by
  rcases h with h | ⟨p, hp', h⟩
  · exact Or.inl (hp ▸ h)
  · refine Or.inr ⟨p, hp ▸ hp', ?_⟩
    rcases h with ⟨h1, r, h⟩ | ⟨h1, b, h⟩ | ⟨h1, pu, g, h⟩
    · exact Or.inl ⟨h1, r, hA _ _ h⟩
    · exact Or.inr (Or.inl ⟨h1, b, hJ _ h⟩)
    · exact Or.inr (Or.inr ⟨h1, pu, g, hC _ _ _ h⟩)

theorem bool_cases (c i : Bool) : c = i ∨ c = !i := by cases c <;> cases i <;> simp

theorem mem_append_of {l : List Frame} {f x : Frame} (h : x ∈ l) : x ∈ l ++ [f] :=
  List.mem_append_left _ h


theorem stepT_req {s : St} {c : Bool} {q : ℕ} {pu : Bool} {g : ℕ} {l : List Frame} (room chain : Bool)
    (h : s.chan c = .req q pu g :: l) :
    stepT s (.deliver c room chain) = onReq repairParams (s.setChan c l) (!c) q pu g room chain := by
  simp [stepT, step, h]
theorem stepT_rep {s : St} {c : Bool} {q : ℕ} {r : Rep} {l : List Frame} (room chain : Bool)
    (h : s.chan c = .rep q r :: l) :
    stepT s (.deliver c room chain) = onRep repairParams (s.setChan c l) (!c) q r := by
  simp [stepT, step, h]
theorem stepT_conf {s : St} {c : Bool} {q : ℕ} {l : List Frame} (room chain : Bool)
    (h : s.chan c = .conf q :: l) :
    stepT s (.deliver c room chain) = onConf (s.setChan c l) (!c) q := by
  simp [stepT, step, h]
theorem stepT_nil {s : St} {c : Bool} (room chain : Bool) (h : s.chan c = []) :
    stepT s (.deliver c room chain) = s := by
  simp [stepT, step, h]

/-- A frame of `i`'s channel is delivered to `j`. -/
theorem lv_deliver_own {k : ℕ} {s : St} {i : Bool} (room chain : Bool) (h : Lv k s i) :
    Lv k (stepT s (.deliver i room chain)) i := by
  cases hc : s.chan i with
  | nil => rw [stepT_nil room chain hc]; exact h
  | cons f l =>
    cases f with
    | req q pu g =>
      rw [stepT_req room chain hc]
      have V := onReq_view (s.setChan i l) (!i) q pu g room chain
      have ho := V.other; rw [Bool.not_not] at ho
      have hoc := V.otherChan; rw [Bool.not_not] at hoc
      rcases h with h | ⟨p, hp, h⟩
      · left; rw [ho]; simpa using h
      · right; refine ⟨p, by rw [ho]; simpa using hp, ?_⟩
        rcases h with ⟨h1, r, h⟩ | ⟨h1, b, h⟩ | ⟨h1, pu', g', h⟩
        · refine Or.inl ⟨h1, r, ?_⟩
          rcases V.chan with hch | ⟨r', hch⟩ <;> rw [hch] <;> simp [h]
        · refine Or.inr (Or.inl ⟨h1, b, ?_⟩)
          rcases V.job with hj | ⟨hj, -⟩
          · rw [hj]; simpa using h
          · simp at hj; rw [hj] at h; simp at h
        · rw [hc] at h
          rcases List.mem_cons.1 h with h | h
          · simp only [Frame.req.injEq] at h
            obtain ⟨hq, -, -⟩ := h
            rcases V.chan with hch | ⟨r', hch⟩
            · rcases V.noAns hch with hj | ⟨b, hj⟩
              · exact Or.inr (Or.inl ⟨by omega, false, by rw [hq]; exact hj⟩)
              · refine Or.inr (Or.inl ⟨by omega, b, ?_⟩)
                rcases V.job with hj' | ⟨hj', -⟩
                · rw [hj', hq]; simpa using hj
                · simp at hj'; simp [hj'] at hj
            · exact Or.inl ⟨by omega, r', by rw [hch, hq]; simp⟩
          · exact Or.inr (Or.inr ⟨h1, pu', g', by rw [hoc]; simpa using h⟩)
    | rep q r =>
      rw [stepT_rep room chain hc]
      obtain ⟨v1, v2, v3, v4⟩ := onRep_view repairParams (s.setChan i l) (!i) q r
      rw [Bool.not_not] at v1 v2
      refine lv_gen (by rw [v1]; simp) (fun q' r' h' => ?_) (fun x hx => by rw [v4]; simpa using hx)
        (fun q' pu g h' => by rw [v2]; rw [hc] at h'; simpa using h') h
      rcases v3 with v3 | v3 <;> rw [v3] <;> simp [h']
    | conf q =>
      rw [stepT_conf room chain hc]
      obtain ⟨v1, v2, v3, -⟩ := onConf_view (s.setChan i l) (!i) q
      rw [Bool.not_not] at v1
      refine lv_gen (by rw [v1]; simp) (fun q' r' h' => by rw [v2]; simpa using h')
        (fun x hx => by rw [v3]; simpa using hx)
        (fun q' pu g h' => by rw [v2]; rw [hc] at h'; simpa using h') h


/-- A frame of `j`'s channel is delivered to `i`. -/
theorem lv_deliver_other {k : ℕ} {s : St} {i : Bool} (room chain : Bool) (h : Lv k s i) :
    Lv k (stepT s (.deliver (!i) room chain)) i := by
  cases hc : s.chan (!i) with
  | nil => rw [stepT_nil room chain hc]; exact h
  | cons f l =>
    cases f with
    | req q pu g =>
      rw [stepT_req room chain hc, Bool.not_not]
      have V := onReq_view (s.setChan (!i) l) i q pu g room chain
      refine lv_gen (by rw [V.pend]; simp) (fun q' r' h' => ?_)
        (fun x hx => by rw [V.other]; simpa using hx) (fun q' pu' g' h' => ?_) h
      · rw [V.otherChan]; rw [hc] at h'; simpa using h'
      · rcases V.chan with hch | ⟨r, hch⟩ <;> rw [hch] <;> simp [h']
    | rep q r =>
      rw [stepT_rep room chain hc, Bool.not_not]
      obtain ⟨v1, v2, v3, v4⟩ := onRep_view repairParams (s.setChan (!i) l) i q r
      rcases h with h | ⟨p, hp, h⟩
      · left
        exact onRep_pend_nil repairParams (s.setChan (!i) l) i q r (by simpa using h)
      · by_cases hq : p.seq = q
        · left
          rw [← hq]; exact onRep_closes repairParams (s.setChan (!i) l) i (p := p) r (by simpa using hp)
        · right
          have hp' := onRep_pend_other repairParams (s.setChan (!i) l) i q r (p := p)
            (by simpa using hp) hq
          refine ⟨p, hp', ?_⟩
          rcases h with ⟨h1, r', h⟩ | ⟨h1, b, h⟩ | ⟨h1, pu, g, h⟩
          · refine Or.inl ⟨h1, r', ?_⟩
            rw [hc] at h
            rcases List.mem_cons.1 h with h | h
            · simp at h; exact absurd h.1 hq
            · rw [v2]; simpa using h
          · exact Or.inr (Or.inl ⟨h1, b, by rw [v1]; simpa using h⟩)
          · refine Or.inr (Or.inr ⟨h1, pu, g, ?_⟩)
            rcases v3 with v3 | v3 <;> rw [v3] <;> simp [h]
    | conf q =>
      rw [stepT_conf room chain hc, Bool.not_not]
      obtain ⟨v1, v2, -, v4⟩ := onConf_view (s.setChan (!i) l) i q
      refine lv_gen (by rw [v4]; simp) (fun q' r' h' => ?_) (fun x hx => by rw [v1]; simpa using hx)
        (fun q' pu g h' => by rw [v2]; simpa using h') h
      rw [v2]; rw [hc] at h'; simpa using h'

theorem lv_finish {k : ℕ} {s : St} {i c : Bool} (ok room : Bool) (h : Lv k s i) :
    Lv k (stepT s (.finish c ok room)) i := by
  cases hj : (s.nd c).job with
  | none =>
    have : stepT s (.finish c ok room) = s := by simp [stepT, step, finishJob, hj]
    rw [this]; exact h
  | some jb =>
    obtain ⟨q, b⟩ := jb
    -- the view of `finishJob` for any outcome
    have hv : ∃ r, (stepT s (.finish c ok room)).nd (!c) = s.nd (!c) ∧
        (stepT s (.finish c ok room)).chan (!c) = s.chan (!c) ∧
        (stepT s (.finish c ok room)).chan c = s.chan c ++ [.rep q r] ∧
        ((stepT s (.finish c ok room)).nd c).pend = (s.nd c).pend := by
      simp only [stepT, step, finishJob, hj]
      split_ifs <;> simp only [Option.getD_some] <;>
        exact ⟨_, reply_nd_not .., reply_chan_not .., reply_chan_self .., by
          rw [reply_nd_self]; simp⟩
    obtain ⟨r, v1, v2, v3, v4⟩ := hv
    rcases bool_cases c i with rfl | rfl
    · exact lv_gen v4 (fun q r h => by rw [v2]; exact h) (fun x hx => by rw [v1]; exact hx)
        (fun q pu g h => by rw [v3]; exact mem_append_of h) h
    · rw [Bool.not_not] at v1 v2
      rcases h with h | ⟨p, hp, h⟩
      · exact Or.inl (by rw [v1]; exact h)
      · refine Or.inr ⟨p, by rw [v1]; exact hp, ?_⟩
        rcases h with ⟨h1, r', h⟩ | ⟨h1, b', h⟩ | ⟨h1, pu, g, h⟩
        · exact Or.inl ⟨h1, r', by rw [v3]; exact mem_append_of h⟩
        · rw [hj] at h; simp at h
          exact Or.inl ⟨by omega, r, by rw [v3, ← h.1]; simp⟩
        · exact Or.inr (Or.inr ⟨h1, pu, g, by rw [v2]; exact h⟩)

theorem lv_retx {k : ℕ} {s : St} {i c : Bool} (q : ℕ) (h : Lv k s i) :
    Lv k (stepT s (.retx c q)) i := by
  simp only [stepT, step]
  split
  · rename_i p _
    simp only [Option.getD_some]
    rcases bool_cases c i with rfl | rfl
    · exact lv_gen (by simp) (fun _ _ h => by simpa using h) (fun _ h => by simpa using h)
        (fun _ _ _ h => by simp [h]) h
    · exact lv_gen (by simp) (fun _ _ h => by simp [h]) (fun _ h => by simpa using h)
        (fun _ _ _ h => by simpa using h) h
  · exact h

theorem lv_misc {k : ℕ} {s : St} {i : Bool} {e : Ev}
    (he : (∃ c q, e = .evict c q) ∨ (∃ c, e = .flip c)) (h : Lv k s i) : Lv k (stepT s e) i := by
  rcases he with ⟨c, q, rfl⟩ | ⟨c, rfl⟩ <;> simp only [stepT, step, Option.getD_some] <;>
  · rcases bool_cases c i with rfl | rfl
    · exact lv_gen (by simp) (fun _ _ h => by simpa using h) (fun _ h => by simpa using h)
        (fun _ _ _ h => by simpa using h) h
    · exact lv_gen (by simp) (fun _ _ h => by simpa using h) (fun x h => by simpa using h)
        (fun _ _ _ h => by simpa using h) h


/-- The events of a slot. -/
def WinEv : Ev → Prop
  | .deliver _ _ _ => True
  | .finish _ _ _ => True
  | .retx _ _ => True
  | .evict _ _ => True
  | .flip _ => True
  | _ => False

theorem lv_step {k : ℕ} {s : St} {i : Bool} {e : Ev} (he : WinEv e) (h : Lv k s i) :
    Lv k (stepT s e) i := by
  cases e with
  | deliver c room chain =>
    rcases bool_cases c i with rfl | rfl
    · exact lv_deliver_own room chain h
    · exact lv_deliver_other room chain h
  | finish c ok room => exact lv_finish ok room h
  | retx c q => exact lv_retx q h
  | evict c q => exact lv_misc (Or.inl ⟨c, q, rfl⟩) h
  | flip c => exact lv_misc (Or.inr ⟨c, rfl⟩) h
  | _ => exact absurd he id

theorem lv_evsT {k : ℕ} {s : St} {i : Bool} {es : List Ev} (he : ∀ e ∈ es, WinEv e)
    (h : Lv k s i) : Lv k (evsT s es) i := by
  induction es generalizing s with
  | nil => exact h
  | cons e es ih =>
    exact ih (fun e' h' => he e' (List.mem_cons_of_mem _ h')) (lv_step (he e List.mem_cons_self) h)

/-- The open request only closes. -/
def PSub (p : Pend) (s : St) (i : Bool) : Prop := (s.nd i).pend = [p] ∨ (s.nd i).pend = []

theorem psub_step {p : Pend} {s : St} {i : Bool} {e : Ev} (he : WinEv e) (h : PSub p s i) :
    PSub p (stepT s e) i := by
  rcases h with h | h
  · have hl : Lv 3 s i ∨ True := Or.inr trivial
    clear hl
    -- the pending list is kept or emptied
    cases e with
    | deliver c room chain =>
      rcases bool_cases c i with rfl | rfl
      · cases hc : s.chan c with
        | nil => rw [stepT_nil room chain hc]; exact Or.inl h
        | cons f l =>
          cases f with
          | req q pu g =>
            rw [stepT_req room chain hc]
            have := (onReq_view (s.setChan c l) (!c) q pu g room chain).other
            rw [Bool.not_not] at this; left; rw [this]; simpa using h
          | rep q r =>
            rw [stepT_rep room chain hc]
            have := (onRep_view repairParams (s.setChan c l) (!c) q r).1
            rw [Bool.not_not] at this; left; rw [this]; simpa using h
          | conf q =>
            rw [stepT_conf room chain hc]
            have := (onConf_view (s.setChan c l) (!c) q).1
            rw [Bool.not_not] at this; left; rw [this]; simpa using h
      · cases hc : s.chan (!i) with
        | nil => rw [stepT_nil room chain hc]; exact Or.inl h
        | cons f l =>
          cases f with
          | req q pu g =>
            rw [stepT_req room chain hc, Bool.not_not]
            left; rw [(onReq_view (s.setChan (!i) l) i q pu g room chain).pend]; simpa using h
          | rep q r =>
            rw [stepT_rep room chain hc, Bool.not_not]
            by_cases hq : p.seq = q
            · right; rw [← hq]; exact onRep_closes repairParams _ i r (by simpa using h)
            · left; exact onRep_pend_other repairParams _ i q r (by simpa using h) hq
          | conf q =>
            rw [stepT_conf room chain hc, Bool.not_not]
            left; rw [(onConf_view (s.setChan (!i) l) i q).2.2.2]; simpa using h
    | finish c ok room =>
      left
      cases hj : (s.nd c).job with
      | none =>
        have : stepT s (.finish c ok room) = s := by simp [stepT, step, finishJob, hj]
        rw [this]; exact h
      | some jb =>
        obtain ⟨q, b⟩ := jb
        simp only [stepT, step, finishJob, hj]
        split_ifs <;> simp only [Option.getD_some] <;>
        · rcases bool_cases c i with rfl | rfl
          · rw [reply_nd_self]; simpa using h
          · have := reply_nd_not s (!i)
            rw [Bool.not_not] at this; rw [this]; exact h
    | retx c q =>
      left; simp only [stepT, step]
      split
      · simpa using h
      · exact h
    | evict c q =>
      left; simp only [stepT, step, Option.getD_some]
      rcases bool_cases c i with rfl | rfl <;> simpa using h
    | flip c =>
      left; simp only [stepT, step, Option.getD_some]
      rcases bool_cases c i with rfl | rfl <;> simpa using h
    | _ => exact absurd he id
  · exact Or.inr (lv_step (k := 0) he (Or.inl h) |>.elim id fun ⟨_, _, h⟩ => by
      rcases h with ⟨h, -⟩ | ⟨h, -⟩ | ⟨h, -⟩ <;> omega)


/-! ### Deliveries consume the channel in order -/

theorem chan_deliver (u : St) (c room chain : Bool) :
    (stepT u (.deliver c room chain)).chan c = (u.chan c).tail ∧
      ∃ ext, (stepT u (.deliver c room chain)).chan (!c) = u.chan (!c) ++ ext := by
  cases hc : u.chan c with
  | nil => rw [stepT_nil room chain hc]; exact ⟨by rw [hc]; rfl, [], by simp⟩
  | cons f l =>
    cases f with
    | req q pu g =>
      rw [stepT_req room chain hc]
      have V := onReq_view (u.setChan c l) (!c) q pu g room chain
      have h1 := V.otherChan; rw [Bool.not_not] at h1
      refine ⟨by rw [h1]; simp, ?_⟩
      rcases V.chan with h | ⟨r, h⟩
      · exact ⟨[], by rw [h]; simp⟩
      · exact ⟨[.rep q r], by rw [h]; simp⟩
    | rep q r =>
      rw [stepT_rep room chain hc]
      obtain ⟨-, h1, h3, -⟩ := onRep_view repairParams (u.setChan c l) (!c) q r
      rw [Bool.not_not] at h1
      refine ⟨by rw [h1]; simp, ?_⟩
      rcases h3 with h | h
      · exact ⟨[], by rw [h]; simp⟩
      · exact ⟨[.conf q], by rw [h]; simp⟩
    | conf q =>
      rw [stepT_conf room chain hc]
      obtain ⟨-, h2, -, -⟩ := onConf_view (u.setChan c l) (!c) q
      exact ⟨by rw [h2 c]; simp, [], by rw [h2 (!c)]; simp⟩

/-- A list of deliveries from channel `c`. -/
def AllDel (c : Bool) (es : List Ev) : Prop := ∀ e ∈ es, ∃ room chain, e = .deliver c room chain

theorem AllDel.tail {c : Bool} {e : Ev} {es : List Ev} (h : AllDel c (e :: es)) : AllDel c es :=
  fun e' h' => h e' (List.mem_cons_of_mem _ h')

/-- Deliveries from `c` only append to the other channel. -/
theorem other_append {c : Bool} {es : List Ev} (h : AllDel c es) (u : St) :
    ∃ ext, (evsT u es).chan (!c) = u.chan (!c) ++ ext := by
  induction es generalizing u with
  | nil => exact ⟨[], by simp [evsT]⟩
  | cons e es ih =>
    obtain ⟨room, chain, rfl⟩ := h e List.mem_cons_self
    obtain ⟨ext1, h1⟩ := (chan_deliver u c room chain).2
    obtain ⟨ext2, h2⟩ := ih h.tail (stepT u _)
    exact ⟨ext1 ++ ext2, by simp only [evsT]; rw [h2, h1, List.append_assoc]⟩

theorem evsT_pres {c : Bool} {Q : St → Prop}
    (hQ : ∀ u room chain, Q u → Q (stepT u (.deliver c room chain))) :
    ∀ (es : List Ev) (u : St), AllDel c es → Q u → Q (evsT u es) := by
  intro es
  induction es with
  | nil => intro u _ h; exact h
  | cons e es ih =>
    intro u hd hq
    obtain ⟨room, chain, rfl⟩ := hd e List.mem_cons_self
    exact ih _ hd.tail (hQ u room chain hq)

/-- **A frame in flight is delivered.** If `f` sits behind `pre` on channel `c`, a list of more than
`|pre|` deliveries from `c` delivers it; if delivering it from any configuration where `P` holds
gives `Q`, and the deliveries keep `P` and `Q`, then `Q` holds at the end. -/
theorem delivered {c : Bool} {P Q : St → Prop} {f : Frame}
    (hP : ∀ u room chain, P u → P (stepT u (.deliver c room chain)))
    (hQ : ∀ u room chain, Q u → Q (stepT u (.deliver c room chain)))
    (hPQ : ∀ u l room chain, u.chan c = f :: l → P u → Q (stepT u (.deliver c room chain))) :
    ∀ (es : List Ev) (pre post : List Frame) (u : St), AllDel c es → u.chan c = pre ++ f :: post →
      pre.length < es.length → P u → Q (evsT u es) := by
  intro es
  induction es with
  | nil => intro pre post u _ _ h; simp at h
  | cons e es ih =>
    intro pre post u hd hc hl hp
    obtain ⟨room, chain, rfl⟩ := hd e List.mem_cons_self
    simp only [evsT]
    cases pre with
    | nil =>
      exact evsT_pres hQ es _ hd.tail (hPQ u post room chain (by simpa using hc) hp)
    | cons x pre' =>
      have hc' : (stepT u (.deliver c room chain)).chan c = pre' ++ f :: post := by
        rw [(chan_deliver u c room chain).1, hc]; rfl
      exact ih pre' post _ hd.tail hc' (by simp at hl; omega) (hP u room chain hp)


/-! ### What one delivery, chain end or retransmission achieves -/

theorem trig_ans {u : St} {i : Bool} {p : Pend} {r : Rep} {l : List Frame} (room chain : Bool)
    (hc : u.chan (!i) = .rep p.seq r :: l) (hp : PSub p u i) :
    Lv 0 (stepT u (.deliver (!i) room chain)) i := by
  rw [stepT_rep room chain hc, Bool.not_not]
  left
  rcases hp with hp | hp
  · exact onRep_closes repairParams _ i r (by simpa using hp)
  · exact onRep_pend_nil repairParams _ i _ r (by simpa using hp)

theorem trig_cpy {u : St} {i : Bool} {p : Pend} {pu : Bool} {g : ℕ} {l : List Frame}
    (room chain : Bool) (hc : u.chan i = .req p.seq pu g :: l) (hp : PSub p u i) :
    Lv 2 (stepT u (.deliver i room chain)) i := by
  rw [stepT_req room chain hc]
  have V := onReq_view (u.setChan i l) (!i) p.seq pu g room chain
  have ho := V.other; rw [Bool.not_not] at ho
  rcases hp with hp | hp
  · right; refine ⟨p, by rw [ho]; simpa using hp, ?_⟩
    rcases V.chan with hch | ⟨r', hch⟩
    · rcases V.noAns hch with hj | ⟨b, hj⟩
      · exact Or.inr (Or.inl ⟨le_rfl, false, hj⟩)
      · refine Or.inr (Or.inl ⟨le_rfl, b, ?_⟩)
        rcases V.job with hj' | ⟨hj', -⟩
        · rw [hj']; exact hj
        · rw [hj'] at hj; simp at hj
    · exact Or.inl ⟨by omega, r', by rw [hch]; simp⟩
  · left; rw [ho]; simpa using hp

theorem trig_fin {u : St} {i : Bool} (ok room : Bool) (h : Lv 2 u i) :
    Lv 1 (stepT u (.finish (!i) ok room)) i := by
  cases hj : (u.nd (!i)).job with
  | none =>
    have : stepT u (.finish (!i) ok room) = u := by simp [stepT, step, finishJob, hj]
    rw [this]
    rcases h with h | ⟨p, hp, h⟩
    · exact Or.inl h
    · refine Or.inr ⟨p, hp, ?_⟩
      rcases h with ⟨h1, h⟩ | ⟨-, b, h⟩ | ⟨h1, -⟩
      · exact Or.inl ⟨le_rfl, h⟩
      · rw [hj] at h; simp at h
      · omega
  | some jb =>
    obtain ⟨q, b⟩ := jb
    have hv : ∃ r, (stepT u (.finish (!i) ok room)).nd i = u.nd i ∧
        (stepT u (.finish (!i) ok room)).chan (!i) = u.chan (!i) ++ [.rep q r] := by
      simp only [stepT, step, finishJob, hj]
      split_ifs <;> simp only [Option.getD_some] <;>
      · refine ⟨_, ?_, reply_chan_self ..⟩
        have := reply_nd_not u (!i); rw [Bool.not_not] at this; exact this ..
    obtain ⟨r, v1, v2⟩ := hv
    rcases h with h | ⟨p, hp, h⟩
    · exact Or.inl (by rw [v1]; exact h)
    · refine Or.inr ⟨p, by rw [v1]; exact hp, ?_⟩
      rcases h with ⟨h1, r', h⟩ | ⟨-, b', h⟩ | ⟨h1, -⟩
      · exact Or.inl ⟨le_rfl, r', by rw [v2]; exact mem_append_of h⟩
      · rw [hj] at h; simp at h
        exact Or.inl ⟨le_rfl, r, by rw [v2, ← h.1]; simp⟩
      · omega

theorem trig_rx {u : St} {i : Bool} {p : Pend} (hp : PSub p u i) :
    Lv 3 (stepT u (.retx i p.seq)) i := by
  rcases hp with hp | hp
  · have hf : (u.nd i).pend.find? (·.seq = p.seq) = some p := by simp [hp]
    have : stepT u (.retx i p.seq) = u.send i (.req p.seq p.push p.gen) := by
      simp [stepT, step, hf]
    rw [this]
    right; exact ⟨p, by simpa using hp, Or.inr (Or.inr ⟨le_rfl, p.push, p.gen, by simp⟩)⟩
  · have hf : (u.nd i).pend.find? (·.seq = p.seq) = none := by simp [hp]
    have : stepT u (.retx i p.seq) = u := by simp [stepT, step, hf]
    rw [this]; exact Or.inl hp


/-! ### One slot -/

/-- The other events of a slot are evictions and budget changes. -/
def MiscOK (E : Env) : Prop := ∀ t, ∀ e ∈ E.misc t, (∃ c q, e = .evict c q) ∨ (∃ c, e = .flip c)

theorem allDel_delivs (E : Env) (t : ℕ) (c : Bool) (n : ℕ) : AllDel c (delivs E t c n) := by
  intro e he; simp only [delivs, List.mem_map] at he
  obtain ⟨k, -, rfl⟩ := he; exact ⟨_, _, rfl⟩

theorem delivs_length (E : Env) (t : ℕ) (c : Bool) (n : ℕ) : (delivs E t c n).length = n := by
  simp [delivs]

theorem slotEvs_win {E : Env} (hM : MiscOK E) (t : ℕ) (s : St) : ∀ e ∈ slotEvs E t s, WinEv e := by
  intro e he
  simp only [slotEvs, List.mem_append] at he
  rcases he with (((((h | h) | h) | h) | h) | h) | h
  · obtain ⟨_, _, rfl⟩ := allDel_delivs E t false _ e h; trivial
  · obtain ⟨_, _, rfl⟩ := allDel_delivs E t true _ e h; trivial
  · simp only [finEv] at h; split at h <;> simp at h; subst h; trivial
  · simp only [finEv] at h; split at h <;> simp at h; subst h; trivial
  · simp only [rxEv] at h; split at h <;> simp at h; subst h; trivial
  · simp only [rxEv] at h; split at h <;> simp at h; subst h; trivial
  · rcases hM t e h with ⟨c, q, rfl⟩ | ⟨c, rfl⟩ <;> trivial

theorem evsT_win {X : St → Prop} (hX : ∀ u e, WinEv e → X u → X (stepT u e)) :
    ∀ (es : List Ev) (u : St), (∀ e ∈ es, WinEv e) → X u → X (evsT u es) := by
  intro es
  induction es with
  | nil => intro u _ h; exact h
  | cons e es ih =>
    intro u hes h
    exact ih _ (fun e' h' => hes e' (List.mem_cons_of_mem _ h')) (hX u e (hes e List.mem_cons_self) h)

theorem slot_split (E : Env) (t : ℕ) (s : St) :
    slot E t s = evsT (evsT (evsT s (delivs E t false s.fromA.length)) (delivs E t true s.fromB.length))
      (finEv E t false ++ finEv E t true ++ rxEv E t false s ++ rxEv E t true s ++ E.misc t) := by
  simp only [slot, slotEvs, List.append_assoc, evsT_append]

/-- **A frame in flight at the start of a slot is delivered in it.** -/
theorem slot_hit {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} {c : Bool} {f : Frame} {P Q : St → Prop}
    (hP : ∀ u e, WinEv e → P u → P (stepT u e)) (hQ : ∀ u e, WinEv e → Q u → Q (stepT u e))
    (hPQ : ∀ u l room chain, u.chan c = f :: l → P u → Q (stepT u (.deliver c room chain)))
    (hf : f ∈ s.chan c) (hp : P s) : Q (slot E t s) := by
  obtain ⟨pre, post, hc⟩ := List.append_of_mem hf
  have hwin := slotEvs_win hM t s
  rw [slot_split]
  have hrest : ∀ e ∈ finEv E t false ++ finEv E t true ++ rxEv E t false s ++ rxEv E t true s ++
      E.misc t, WinEv e := fun e he => hwin e (by simp only [slotEvs, List.mem_append] at he ⊢; tauto)
  refine evsT_win hQ _ _ hrest ?_
  have hPd : ∀ c' u room chain, P u → P (stepT u (.deliver c' room chain)) :=
    fun c' u room chain h => hP u _ trivial h
  have hQd : ∀ c' u room chain, Q u → Q (stepT u (.deliver c' room chain)) :=
    fun c' u room chain h => hQ u _ trivial h
  cases c with
  | false =>
    refine evsT_pres (hQd true) _ _ (allDel_delivs E t true _) ?_
    exact delivered (hPd false) (hQd false) hPQ _ pre post s (allDel_delivs E t false _) hc
      (by rw [delivs_length]; have := congrArg List.length hc; simp [St.chan] at this; omega) hp
  | true =>
    obtain ⟨ext, hext⟩ := other_append (allDel_delivs E t false s.fromA.length) s
    simp only [Bool.not_false] at hext
    refine delivered (hPd true) (hQd true) hPQ _ pre (post ++ ext) _ (allDel_delivs E t true _)
      (by rw [hext, hc]; simp) ?_ (evsT_pres (hPd false) _ _ (allDel_delivs E t false _) hp)
    rw [delivs_length]; have := congrArg List.length hc; simp [St.chan] at this; omega

theorem lv_slot {E : Env} (hM : MiscOK E) {k : ℕ} {t : ℕ} {s : St} {i : Bool} (h : Lv k s i) :
    Lv k (slot E t s) i :=
  evsT_win (X := fun u => Lv k u i) (fun _ _ he h => lv_step he h) _ _ (slotEvs_win hM t s) h

theorem psub_win {p : Pend} {i : Bool} : ∀ u e, WinEv e → PSub p u i → PSub p (stepT u e) i :=
  fun _ _ he h => psub_step he h

/-- An answer in flight closes the request in the next slot. -/
theorem slot_ans {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} {i : Bool} (h : Lv 1 s i) :
    Lv 0 (slot E t s) i := by
  rcases h with h | ⟨p, hp, h⟩
  · exact lv_slot hM (Or.inl h)
  · rcases h with ⟨-, r, hr⟩ | ⟨h, -⟩ | ⟨h, -⟩
    · exact slot_hit (P := fun u => PSub p u i) (Q := fun u => Lv 0 u i) hM psub_win
        (fun _ _ he h => lv_step he h)
        (fun u l room chain hc hp' => trig_ans room chain hc hp') hr (Or.inl hp)
    · omega
    · omega

/-- A copy in flight is answered or taken up by a chain in the next slot. -/
theorem slot_cpy {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} {i : Bool} (h : Lv 3 s i) :
    Lv 2 (slot E t s) i := by
  rcases h with h | ⟨p, hp, h⟩
  · exact lv_slot hM (Or.inl h)
  · rcases h with ⟨_, h⟩ | ⟨_, h⟩ | ⟨-, pu, g, h⟩
    · exact lv_slot hM (Or.inr ⟨p, hp, Or.inl ⟨by omega, h⟩⟩)
    · exact lv_slot hM (Or.inr ⟨p, hp, Or.inr (Or.inl ⟨le_rfl, h⟩)⟩)
    · exact slot_hit (P := fun u => PSub p u i) (Q := fun u => Lv 2 u i) hM psub_win
        (fun _ _ he h => lv_step he h)
        (fun u l room chain hc hp' => trig_cpy room chain hc hp') h (Or.inl hp)

/-- A chain that ends answers the request it serves. -/
theorem slot_fin {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} {i : Bool} (h : Lv 2 s i)
    (hf : (E.fin t (!i)).isSome) : Lv 1 (slot E t s) i := by
  have hwin := slotEvs_win hM t s
  obtain ⟨⟨ok, room⟩, hfo⟩ := Option.isSome_iff_exists.1 hf
  rw [slot_split]
  have h2 := evsT_win (X := fun u => Lv _ u i) (fun _ _ he h => lv_step he h) (delivs E t true s.fromB.length) _
    (fun e he => by obtain ⟨_, _, rfl⟩ := allDel_delivs E t true _ e he; trivial)
    (evsT_win (X := fun u => Lv _ u i) (fun _ _ he h => lv_step he h) (delivs E t false s.fromA.length) _
      (fun e he => by obtain ⟨_, _, rfl⟩ := allDel_delivs E t false _ e he; trivial) h)
  have hrest : ∀ e ∈ rxEv E t false s ++ rxEv E t true s ++ E.misc t, WinEv e :=
    fun e he => hwin e (by simp only [slotEvs, List.mem_append] at he ⊢; tauto)
  simp only [List.append_assoc]
  rw [evsT_append, evsT_append]
  refine evsT_win (X := fun u => Lv _ u i) (fun _ _ he h => lv_step he h) _ _
    (fun e he => hrest e (by simpa [List.append_assoc] using he)) ?_
  cases i with
  | false =>
    simp only [Bool.not_false] at hfo
    have : finEv E t true = [.finish true ok room] := by simp [finEv, hfo]
    rw [this]
    have hA : ∀ e ∈ finEv E t false, WinEv e := fun e he => by
      simp only [finEv] at he; split at he <;> simp at he; subst he; trivial
    exact trig_fin (i := false) ok room (evsT_win (X := fun u => Lv _ u false) (fun _ _ he h => lv_step he h) _ _ hA h2)
  | true =>
    simp only [Bool.not_true] at hfo
    have : finEv E t false = [.finish false ok room] := by simp [finEv, hfo]
    rw [this]
    have hB : ∀ e ∈ finEv E t true, WinEv e := fun e he => by
      simp only [finEv] at he; split at he <;> simp at he; subst he; trivial
    exact evsT_win (X := fun u => Lv _ u true) (fun _ _ he h => lv_step he h) _ _ hB (trig_fin (i := true) ok room h2)


theorem slot_split2 (E : Env) (t : ℕ) (s : St) :
    slot E t s = evsT (evsT (evsT (evsT s (delivs E t false s.fromA.length ++
      delivs E t true s.fromB.length ++ finEv E t false ++ finEv E t true)) (rxEv E t false s))
      (rxEv E t true s)) (E.misc t) := by
  simp only [slot, slotEvs, List.append_assoc, evsT_append]

/-- A retransmission puts a copy in flight. -/
theorem slot_rx {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} {i : Bool} (H : Inv s)
    (hr : E.rx t i = true) : Lv 3 (slot E t s) i := by
  have hwin := slotEvs_win hM t s
  rcases ((inv_iff s).1 H i).pend with hp | ⟨p, hp, hs⟩
  · exact (lv_slot (k := 0) hM (Or.inl hp)).mono (by omega)
  · rw [slot_split2]
    have hmisc : ∀ e ∈ E.misc t, WinEv e := fun e he => hwin e (by simp [slotEvs, he])
    refine evsT_win (X := fun u => Lv 3 u i) (fun _ _ he h => lv_step he h) _ _ hmisc ?_
    have hpre : PSub p (evsT s (delivs E t false s.fromA.length ++ delivs E t true s.fromB.length ++
        finEv E t false ++ finEv E t true)) i :=
      evsT_win (X := fun u => PSub p u i) psub_win _ _
        (fun e he => hwin e (by simp only [slotEvs, List.mem_append] at he ⊢; tauto)) (Or.inl hp)
    have hrx : rxEv E t i s = [.retx i p.seq] := by simp [rxEv, hr, hs]
    have hA : ∀ e ∈ rxEv E t false s, WinEv e := fun e he => by
      simp only [rxEv] at he; split at he <;> simp at he; subst he; trivial
    have hB : ∀ e ∈ rxEv E t true s, WinEv e := fun e he => by
      simp only [rxEv] at he; split at he <;> simp at he; subst he; trivial
    cases i with
    | false =>
      rw [hrx]
      exact evsT_win (X := fun u => Lv 3 u false) (fun _ _ he h => lv_step he h) _ _ hB
        (trig_rx hpre)
    | true =>
      rw [hrx]
      exact trig_rx (evsT_win (X := fun u => PSub p u true) psub_win _ _ hA hpre)

theorem lv_srun {E : Env} (hM : MiscOK E) {s₀ : St} {k : ℕ} {i : Bool} {a : ℕ}
    (h : Lv k (srun E s₀ a) i) : ∀ b, a ≤ b → Lv k (srun E s₀ b) i := by
  intro b hab
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact h
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · exact lv_slot hM (ih (by omega))
    · have : a = b + 1 := by omega
      subst this; exact h

/-- **An open request closes within `Tr + d + 2` slots.** If `i`'s timer fires at least once in
every `Tr` consecutive slots and the chain at `j = !i` ends at least once in every `d`
consecutive slots, then from any slot `u` on, `i` has no open request by slot `u + Tr + d + 2`. -/
theorem closes {E : Env} (hM : MiscOK E) {s₀ : St} (H : Inv s₀) {i : Bool} {Tr d : ℕ}
    (hR : ∀ u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v i = true)
    (hF : ∀ u, ∃ v, u ≤ v ∧ v < u + d ∧ (E.fin v (!i)).isSome) (u : ℕ) :
    Lv 0 (srun E s₀ (u + Tr + d + 2)) i := by
  obtain ⟨v1, hv1, hv1', hr⟩ := hR u
  have l3 : Lv 3 (srun E s₀ (v1 + 1)) i := slot_rx hM (srun_inv H v1) hr
  have l2 : Lv 2 (srun E s₀ (v1 + 2)) i := slot_cpy hM l3
  obtain ⟨v2, hv2, hv2', hf⟩ := hF (v1 + 2)
  have l2' : Lv 2 (srun E s₀ v2) i := lv_srun hM l2 v2 hv2
  have l1 : Lv 1 (srun E s₀ (v2 + 1)) i := slot_fin hM l2' hf
  have l0 : Lv 0 (srun E s₀ (v2 + 2)) i := slot_ans hM l1
  exact lv_srun hM l0 _ (by omega)


/-! ### After every request closed: chains end, the channels drain -/

def NoReqL (l : List Frame) : Prop := ∀ q pu g, Frame.req q pu g ∉ l

theorem noReqL_append {l l' : List Frame} (h : NoReqL l) (h' : NoReqL l') : NoReqL (l ++ l') :=
  fun q pu g hm => (List.mem_append.1 hm).elim (h q pu g) (h' q pu g)

/-- A delivery appends at most an answer or a confirmation to the other channel. -/
theorem deliver_ext (u : St) (c room chain : Bool) :
    ∃ ext, (stepT u (.deliver c room chain)).chan (!c) = u.chan (!c) ++ ext ∧ NoReqL ext := by
  cases hc : u.chan c with
  | nil => rw [stepT_nil room chain hc]; exact ⟨[], by simp, by simp [NoReqL]⟩
  | cons f l =>
    cases f with
    | req q pu g =>
      rw [stepT_req room chain hc]
      rcases (onReq_view (u.setChan c l) (!c) q pu g room chain).chan with h | ⟨r, h⟩
      · exact ⟨[], by rw [h]; simp, by simp [NoReqL]⟩
      · exact ⟨[.rep q r], by rw [h]; simp, by simp [NoReqL]⟩
    | rep q r =>
      rw [stepT_rep room chain hc]
      rcases (onRep_view repairParams (u.setChan c l) (!c) q r).2.2.1 with h | h
      · exact ⟨[], by rw [h]; simp, by simp [NoReqL]⟩
      · exact ⟨[.conf q], by rw [h]; simp, by simp [NoReqL]⟩
    | conf q =>
      rw [stepT_conf room chain hc]
      exact ⟨[], by rw [(onConf_view (u.setChan c l) (!c) q).2.1 (!c)]; simp, by simp [NoReqL]⟩

/-- A delivery of anything but a request appends nothing (answers are never late, `Inv`). -/
theorem deliver_noapp {u : St} (H : Inv u) (c room chain : Bool) (hn : ∀ q pu g l,
    u.chan c ≠ .req q pu g :: l) : (stepT u (.deliver c room chain)).chan (!c) = u.chan (!c) := by
  cases hc : u.chan c with
  | nil => rw [stepT_nil room chain hc]
  | cons f l =>
    cases f with
    | req q pu g => exact absurd hc (hn q pu g l)
    | rep q r =>
      rw [stepT_rep room chain hc]
      have hl : r.late = false := ((inv_iff u).1 H c).chanI (.rep q r) (by rw [hc]; simp)
      rw [onRep_chan_nolate _ _ _ _ _ hl]; simp
    | conf q =>
      exact False.elim (((inv_iff u).1 H c).chanI (.conf q) (by rw [hc]; simp))

/-- Deliveries from `c` consume its prefix. -/
theorem consume {c : Bool} : ∀ (es : List Ev) (pre post : List Frame) (u : St), AllDel c es →
    u.chan c = pre ++ post → es.length = pre.length → (evsT u es).chan c = post := by
  intro es
  induction es with
  | nil => intro pre post u _ hc hl; cases pre with
    | nil => simpa [evsT] using hc
    | cons => simp at hl
  | cons e es ih =>
    intro pre post u hd hc hl
    obtain ⟨room, chain, rfl⟩ := hd e List.mem_cons_self
    cases pre with
    | nil => simp at hl
    | cons x pre' =>
      simp only [evsT]
      exact ih pre' post _ hd.tail (by rw [(chan_deliver u c room chain).1, hc]; rfl)
        (by simpa using hl)

theorem other_noreq {c : Bool} : ∀ (es : List Ev) (u : St), AllDel c es →
    ∃ ext, (evsT u es).chan (!c) = u.chan (!c) ++ ext ∧ NoReqL ext := by
  intro es
  induction es with
  | nil => intro u _; exact ⟨[], by simp [evsT], by simp [NoReqL]⟩
  | cons e es ih =>
    intro u hd
    obtain ⟨room, chain, rfl⟩ := hd e List.mem_cons_self
    obtain ⟨e1, h1, n1⟩ := deliver_ext u c room chain
    obtain ⟨e2, h2, n2⟩ := ih (stepT u _) hd.tail
    exact ⟨e1 ++ e2, by simp only [evsT]; rw [h2, h1, List.append_assoc], noReqL_append n1 n2⟩

/-- Nothing remains open and no chain runs at `k`, so none starts there. -/
theorem job_none_step {u : St} {k : Bool} {e : Ev} (H : Inv u) (hp : ∀ k', (u.nd k').pend = [])
    (hj : (u.nd k).job = none) (he : WinEv e) : ((stepT u e).nd k).job = none := by
  cases e with
  | deliver c room chain =>
    cases hc : u.chan c with
    | nil => rw [stepT_nil room chain hc]; exact hj
    | cons f l =>
      rcases bool_cases c k with rfl | rfl
      · cases f with
        | req q pu g =>
          rw [stepT_req room chain hc]
          have := (onReq_view (u.setChan c l) (!c) q pu g room chain).other
          rw [Bool.not_not] at this; rw [this]; simpa using hj
        | rep q r =>
          rw [stepT_rep room chain hc]
          have := (onRep_view repairParams (u.setChan c l) (!c) q r).1
          rw [Bool.not_not] at this; rw [this]; simpa using hj
        | conf q =>
          rw [stepT_conf room chain hc]
          have := (onConf_view (u.setChan c l) (!c) q).1
          rw [Bool.not_not] at this; rw [this]; simpa using hj
      · cases f with
        | req q pu g =>
          rw [stepT_req room chain hc, Bool.not_not]
          have V := onReq_view (u.setChan (!k) l) k q pu g room chain
          rcases V.job with h | ⟨-, h⟩
          · rw [h]; simpa using hj
          · exfalso
            have hfr := V.jobFresh (by simpa using hj) (by rw [h]; simp)
            have hFI := ((inv_iff u).1 H (!k)).chanI (.req q pu g) (by rw [hc]; simp)
            obtain ⟨p, hp', -⟩ := hFI.2.2.1 (by rw [Bool.not_not]; simpa using hfr)
            rw [hp (!k)] at hp'; simp at hp'
        | rep q r =>
          rw [stepT_rep room chain hc, Bool.not_not]
          rw [(onRep_view repairParams (u.setChan (!k) l) k q r).2.2.2]; simpa using hj
        | conf q =>
          rw [stepT_conf room chain hc, Bool.not_not]
          rw [(onConf_view (u.setChan (!k) l) k q).2.2.1]; simpa using hj
  | finish c ok room =>
    rcases bool_cases c k with rfl | rfl
    · have : stepT u (.finish c ok room) = u := by simp [stepT, step, finishJob, hj]
      rw [this]; exact hj
    · cases hjc : (u.nd (!k)).job with
      | none =>
        have : stepT u (.finish (!k) ok room) = u := by simp [stepT, step, finishJob, hjc]
        rw [this]; exact hj
      | some jb =>
        obtain ⟨q, b⟩ := jb
        simp only [stepT, step, finishJob, hjc]
        split_ifs <;> simp only [Option.getD_some] <;>
        · have := reply_nd_not u (!k); rw [Bool.not_not] at this; rw [this]; exact hj
  | retx c q =>
    simp only [stepT, step]; split
    · simpa using hj
    · exact hj
  | evict c q =>
    simp only [stepT, step, Option.getD_some]
    rcases bool_cases c k with rfl | rfl <;> simpa using hj
  | flip c =>
    simp only [stepT, step, Option.getD_some]
    rcases bool_cases c k with rfl | rfl <;> simpa using hj
  | _ => exact absurd he id

theorem job_none_fin {u : St} {k : Bool} (ok room : Bool) :
    ((stepT u (.finish k ok room)).nd k).job = none ∨ (u.nd k).job = none := by
  cases hj : (u.nd k).job with
  | none => exact Or.inr rfl
  | some jb =>
    obtain ⟨q, b⟩ := jb
    left
    simp only [stepT, step, finishJob, hj]
    split_ifs <;> simp only [Option.getD_some] <;> rw [reply_nd_self] <;> simp


/-- No request is open at either end. -/
def Calm0 (u : St) : Prop := ∀ k, (u.nd k).pend = []

theorem calm0_step {u : St} {e : Ev} (he : WinEv e) (h : Calm0 u) : Calm0 (stepT u e) := fun k => by
  rcases lv_step (k := 0) (i := k) he (Or.inl (h k)) with h' | ⟨_, _, h'⟩
  · exact h'
  · rcases h' with ⟨h', -⟩ | ⟨h', -⟩ | ⟨h', -⟩ <;> omega

theorem slot_job {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} {k : Bool} (H : Inv s) (hc : Calm0 s)
    (hj : (s.nd k).job = none) : ((slot E t s).nd k).job = none :=
  (evsT_win (X := fun u => Inv u ∧ Calm0 u ∧ (u.nd k).job = none)
    (fun _ e he ⟨h1, h2, h3⟩ => ⟨stepT_inv h1 e, calm0_step he h2, job_none_step h1 h2 h3 he⟩)
    _ _ (slotEvs_win hM t s) ⟨H, hc, hj⟩).2.2

theorem slot_split3 (E : Env) (t : ℕ) (s : St) :
    slot E t s = evsT (evsT (evsT (evsT s (delivs E t false s.fromA.length ++
      delivs E t true s.fromB.length)) (finEv E t false)) (finEv E t true))
      (rxEv E t false s ++ rxEv E t true s ++ E.misc t) := by
  simp only [slot, slotEvs, List.append_assoc, evsT_append]

theorem slot_job_fin {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} {k : Bool} (H : Inv s) (hc : Calm0 s)
    (hf : (E.fin t k).isSome) : ((slot E t s).nd k).job = none := by
  have hwin := slotEvs_win hM t s
  obtain ⟨⟨ok, room⟩, hfo⟩ := Option.isSome_iff_exists.1 hf
  have pres : ∀ u e, WinEv e → (Inv u ∧ Calm0 u) → (Inv (stepT u e) ∧ Calm0 (stepT u e)) :=
    fun u e he ⟨h1, h2⟩ => ⟨stepT_inv h1 e, calm0_step he h2⟩
  have presJ : ∀ u e, WinEv e → (Inv u ∧ Calm0 u ∧ (u.nd k).job = none) →
      (Inv (stepT u e) ∧ Calm0 (stepT u e) ∧ ((stepT u e).nd k).job = none) :=
    fun u e he ⟨h1, h2, h3⟩ => ⟨stepT_inv h1 e, calm0_step he h2, job_none_step h1 h2 h3 he⟩
  have hfin : ∀ u, Inv u → Calm0 u → ((stepT u (.finish k ok room)).nd k).job = none := by
    intro u h1 h2
    rcases job_none_fin (u := u) (k := k) ok room with h | h
    · exact h
    · exact job_none_step h1 h2 h trivial
  have h0 := evsT_win (X := fun u => Inv u ∧ Calm0 u) pres
    (delivs E t false s.fromA.length ++ delivs E t true s.fromB.length) s
    (fun e he => hwin e (by simp only [slotEvs, List.mem_append] at he ⊢; tauto)) ⟨H, hc⟩
  have hrest : ∀ e ∈ rxEv E t false s ++ rxEv E t true s ++ E.misc t, WinEv e :=
    fun e he => hwin e (by simp only [slotEvs, List.mem_append] at he ⊢; tauto)
  have hA : ∀ e ∈ finEv E t false, WinEv e := fun e he => by
    simp only [finEv] at he; split at he <;> simp at he; subst he; trivial
  have hB : ∀ e ∈ finEv E t true, WinEv e := fun e he => by
    simp only [finEv] at he; split at he <;> simp at he; subst he; trivial
  rw [slot_split3]
  refine (evsT_win (X := fun u => Inv u ∧ Calm0 u ∧ (u.nd k).job = none) presJ _ _ hrest ?_).2.2
  cases k with
  | false =>
    have : finEv E t false = [.finish false ok room] := by simp [finEv, hfo]
    rw [this]
    exact evsT_win (X := fun u => Inv u ∧ Calm0 u ∧ (u.nd false).job = none) presJ _ _ hB
      ⟨stepT_inv h0.1 _, calm0_step trivial h0.2, hfin _ h0.1 h0.2⟩
  | true =>
    have : finEv E t true = [.finish true ok room] := by simp [finEv, hfo]
    rw [this]
    have h1 := evsT_win (X := fun u => Inv u ∧ Calm0 u) pres _ _ hA h0
    exact ⟨stepT_inv h1.1 _, calm0_step trivial h1.2, hfin _ h1.1 h1.2⟩


/-- Events of a slot other than deliveries. -/
def NonDel (e : Ev) : Prop := WinEv e ∧ ∀ c room chain, e ≠ .deliver c room chain

theorem nondel_ext {u : St} {e : Ev} (he : NonDel e) (hc : Calm0 u) (c : Bool) :
    ∃ ext, (stepT u e).chan c = u.chan c ++ ext ∧ NoReqL ext := by
  obtain ⟨hw, hnd⟩ := he
  cases e with
  | deliver c' room chain => exact absurd rfl (hnd c' room chain)
  | finish k ok room =>
    cases hj : (u.nd k).job with
    | none =>
      have : stepT u (.finish k ok room) = u := by simp [stepT, step, finishJob, hj]
      rw [this]; exact ⟨[], by simp, by simp [NoReqL]⟩
    | some jb =>
      obtain ⟨q, b⟩ := jb
      simp only [stepT, step, finishJob, hj]
      split_ifs <;> simp only [Option.getD_some] <;>
      · rcases bool_cases c k with rfl | rfl
        · exact ⟨_, reply_chan_self .., by simp [NoReqL]⟩
        · exact ⟨[], by rw [reply_chan_not u k]; simp, by simp [NoReqL]⟩
  | retx k q =>
    have hf : (u.nd k).pend.find? (·.seq = q) = none := by simp [hc k]
    have : stepT u (.retx k q) = u := by simp [stepT, step, hf]
    rw [this]; exact ⟨[], by simp, by simp [NoReqL]⟩
  | evict k q =>
    exact ⟨[], by simp [stepT, step], by simp [NoReqL]⟩
  | flip k =>
    exact ⟨[], by simp [stepT, step], by simp [NoReqL]⟩
  | _ => exact absurd hw id

theorem nondel_same {u : St} {e : Ev} (he : NonDel e) (hc : Calm0 u)
    (hj : ∀ k, (u.nd k).job = none) (c : Bool) : (stepT u e).chan c = u.chan c := by
  obtain ⟨hw, hnd⟩ := he
  cases e with
  | deliver c' room chain => exact absurd rfl (hnd c' room chain)
  | finish k ok room =>
    have : stepT u (.finish k ok room) = u := by simp [stepT, step, finishJob, hj k]
    rw [this]
  | retx k q =>
    have hf : (u.nd k).pend.find? (·.seq = q) = none := by simp [hc k]
    have : stepT u (.retx k q) = u := by simp [stepT, step, hf]
    rw [this]
  | evict k q => simp [stepT, step]
  | flip k => simp [stepT, step]
  | _ => exact absurd hw id

theorem tailEvs_nondel (E : Env) (hM : MiscOK E) (t : ℕ) (s : St) :
    ∀ e ∈ finEv E t false ++ finEv E t true ++ rxEv E t false s ++ rxEv E t true s ++ E.misc t,
      NonDel e := by
  intro e he
  simp only [List.mem_append] at he
  rcases he with (((h | h) | h) | h) | h
  · simp only [finEv] at h; split at h <;> simp at h; subst h; exact ⟨trivial, by simp⟩
  · simp only [finEv] at h; split at h <;> simp at h; subst h; exact ⟨trivial, by simp⟩
  · simp only [rxEv] at h; split at h <;> simp at h; subst h; exact ⟨trivial, by simp⟩
  · simp only [rxEv] at h; split at h <;> simp at h; subst h; exact ⟨trivial, by simp⟩
  · rcases hM t e h with ⟨c, q, rfl⟩ | ⟨c, rfl⟩ <;> exact ⟨trivial, by simp⟩

theorem tail_noreq : ∀ (es : List Ev) (u : St), (∀ e ∈ es, NonDel e) → Calm0 u → ∀ c,
    ∃ ext, (evsT u es).chan c = u.chan c ++ ext ∧ NoReqL ext := by
  intro es
  induction es with
  | nil => intro u _ _ c; exact ⟨[], by simp [evsT], by simp [NoReqL]⟩
  | cons e es ih =>
    intro u hes hc c
    have he := hes e List.mem_cons_self
    obtain ⟨e1, h1, n1⟩ := nondel_ext he hc c
    obtain ⟨e2, h2, n2⟩ := ih (stepT u e) (fun e' h' => hes e' (List.mem_cons_of_mem _ h'))
      (calm0_step he.1 hc) c
    exact ⟨e1 ++ e2, by simp only [evsT]; rw [h2, h1, List.append_assoc], noReqL_append n1 n2⟩

theorem tail_same : ∀ (es : List Ev) (u : St), (∀ e ∈ es, NonDel e) → Inv u → Calm0 u →
    (∀ k, (u.nd k).job = none) → ∀ c, (evsT u es).chan c = u.chan c := by
  intro es
  induction es with
  | nil => intro u _ _ _ _ c; rfl
  | cons e es ih =>
    intro u hes H hc hj c
    have he := hes e List.mem_cons_self
    simp only [evsT]
    rw [ih (stepT u e) (fun e' h' => hes e' (List.mem_cons_of_mem _ h')) (stepT_inv H e)
      (calm0_step he.1 hc) (fun k => job_none_step H hc (hj k) he.1) c]
    exact nondel_same he hc hj c

/-- After a slot that starts with no open request, no request is in flight. -/
theorem slot_noreq {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} (H : Inv s) (hc : Calm0 s) (c : Bool) :
    NoReqL ((slot E t s).chan c) := by
  have pres : ∀ u e, WinEv e → (Inv u ∧ Calm0 u) → (Inv (stepT u e) ∧ Calm0 (stepT u e)) :=
    fun u e he ⟨h1, h2⟩ => ⟨stepT_inv h1 e, calm0_step he h2⟩
  have hdA : ∀ e ∈ delivs E t false s.fromA.length, WinEv e := fun e he => by
    obtain ⟨_, _, rfl⟩ := allDel_delivs E t false _ e he; trivial
  set u1 := evsT s (delivs E t false s.fromA.length) with hu1
  have hX1 := evsT_win (X := fun u => Inv u ∧ Calm0 u) pres _ _ hdA ⟨H, hc⟩
  have a1 : u1.chan false = [] :=
    consume _ s.fromA [] s (allDel_delivs E t false _) (by simp [St.chan]) (delivs_length ..)
  obtain ⟨e1, b1, n1⟩ := other_noreq (c := false) _ s (allDel_delivs E t false s.fromA.length)
  simp only [Bool.not_false] at b1
  have hdB : ∀ e ∈ delivs E t true s.fromB.length, WinEv e := fun e he => by
    obtain ⟨_, _, rfl⟩ := allDel_delivs E t true _ e he; trivial
  set u2 := evsT u1 (delivs E t true s.fromB.length) with hu2
  have hX2 := evsT_win (X := fun u => Inv u ∧ Calm0 u) pres _ _ hdB hX1
  have a2 : u2.chan true = e1 :=
    consume _ s.fromB e1 u1 (allDel_delivs E t true _) (by rw [hu1, b1]; rfl) (delivs_length ..)
  obtain ⟨e2, b2, n2⟩ := other_noreq (c := true) _ u1 (allDel_delivs E t true s.fromB.length)
  simp only [Bool.not_true] at b2
  rw [slot_split]
  obtain ⟨e3, b3, n3⟩ := tail_noreq _ u2 (tailEvs_nondel E hM t s) hX2.2 c
  rw [b3]
  refine noReqL_append ?_ n3
  cases c with
  | false => rw [hu2, b2, a1]; simpa using n2
  | true => rw [a2]; exact n1

/-- Delivering a channel that carries no request appends nothing to the other one. -/
theorem phase_noapp {c : Bool} : ∀ (es : List Ev) (u : St), AllDel c es →
    es.length = (u.chan c).length → NoReqL (u.chan c) → Inv u →
    (evsT u es).chan c = [] ∧ (evsT u es).chan (!c) = u.chan (!c) := by
  intro es
  induction es with
  | nil => intro u _ hl _ _; exact ⟨List.eq_nil_of_length_eq_zero (by simpa [evsT] using hl.symm), rfl⟩
  | cons e es ih =>
    intro u hd hl hn H
    obtain ⟨room, chain, rfl⟩ := hd e List.mem_cons_self
    cases hc : u.chan c with
    | nil => rw [hc] at hl; simp at hl
    | cons x l =>
      have hnr : ∀ q pu g l', u.chan c ≠ .req q pu g :: l' := fun q pu g l' h => by
        rw [hc] at h; simp at h; obtain ⟨rfl, -⟩ := h
        exact hn q pu g (by rw [hc]; simp)
      have h1 := deliver_noapp H c room chain hnr
      have h2 : (stepT u (.deliver c room chain)).chan c = l := by
        rw [(chan_deliver u c room chain).1, hc]; rfl
      simp only [evsT]
      obtain ⟨r1, r2⟩ := ih _ hd.tail (by rw [h2]; rw [hc] at hl; simpa using hl)
        (by rw [h2]; intro q pu g h; exact hn q pu g (by rw [hc]; exact List.mem_cons_of_mem _ h))
        (stepT_inv H _)
      exact ⟨r1, by rw [r2, h1]⟩

/-- A slot that starts with no open request, no chain and no request in flight empties both
channels. -/
theorem slot_empty {E : Env} (hM : MiscOK E) {t : ℕ} {s : St} (H : Inv s) (hc : Calm0 s)
    (hj : ∀ k, (s.nd k).job = none) (hn : ∀ c, NoReqL (s.chan c)) (c : Bool) :
    (slot E t s).chan c = [] := by
  have presJ : ∀ u e, WinEv e → (Inv u ∧ Calm0 u ∧ ∀ k, (u.nd k).job = none) →
      (Inv (stepT u e) ∧ Calm0 (stepT u e) ∧ ∀ k, ((stepT u e).nd k).job = none) :=
    fun u e he ⟨h1, h2, h3⟩ => ⟨stepT_inv h1 e, calm0_step he h2, fun k => job_none_step h1 h2 (h3 k) he⟩
  have hdA : ∀ e ∈ delivs E t false s.fromA.length, WinEv e := fun e he => by
    obtain ⟨_, _, rfl⟩ := allDel_delivs E t false _ e he; trivial
  have hdB : ∀ e ∈ delivs E t true s.fromB.length, WinEv e := fun e he => by
    obtain ⟨_, _, rfl⟩ := allDel_delivs E t true _ e he; trivial
  have X1 := evsT_win (X := fun u => Inv u ∧ Calm0 u ∧ ∀ k, (u.nd k).job = none) presJ _ _ hdA
    ⟨H, hc, hj⟩
  obtain ⟨a1, b1⟩ := phase_noapp (c := false) (delivs E t false s.fromA.length) s
    (allDel_delivs E t false _) (by rw [delivs_length]; rfl) (hn false) H
  simp only [Bool.not_false] at b1
  have X2 := evsT_win (X := fun u => Inv u ∧ Calm0 u ∧ ∀ k, (u.nd k).job = none) presJ _ _ hdB X1
  obtain ⟨a2, b2⟩ := phase_noapp (c := true) (delivs E t true s.fromB.length)
    (evsT s (delivs E t false s.fromA.length)) (allDel_delivs E t true _)
    (by rw [delivs_length, b1]; rfl) (by rw [b1]; exact hn true) X1.1
  simp only [Bool.not_true] at b2
  rw [slot_split, tail_same _ _ (tailEvs_nondel E hM t s) X2.1 X2.2.1 X2.2.2 c]
  cases c with
  | false => rw [b2, a1]
  | true => exact a2


/-! ### The window -/

theorem calm0_srun {E : Env} (hM : MiscOK E) {s₀ : St} {a : ℕ} (h : Calm0 (srun E s₀ a)) :
    ∀ b, a ≤ b → Calm0 (srun E s₀ b) := fun b hab k => by
  rcases lv_srun (k := 0) (i := k) hM (Or.inl (h k)) b hab with h' | ⟨_, _, h'⟩
  · exact h'
  · rcases h' with ⟨h', -⟩ | ⟨h', -⟩ | ⟨h', -⟩ <;> omega

theorem job_srun {E : Env} (hM : MiscOK E) {s₀ : St} (H : Inv s₀) {a : ℕ} {k : Bool}
    (hc : Calm0 (srun E s₀ a)) (h : ((srun E s₀ a).nd k).job = none) :
    ∀ b, a ≤ b → ((srun E s₀ b).nd k).job = none := by
  intro b hab
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact h
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · exact slot_job hM (srun_inv H b) (calm0_srun hM hc b (by omega)) (ih (by omega))
    · have : a = b + 1 := by omega
      subst this; exact h

/-- **Lemma 4 for the transfer layer under the synchronous scheduler.** Let the run of one
flexible edge be loss-free and free of new offers (both are built into `slot`), let every timer
fire at least once in every `Tr` consecutive slots and every chain end at least once in every `d`
consecutive slots, and let the other events be evictions and budget changes. Then from every
configuration satisfying the invariant (every reachable one), whatever the receivers' room and
chain choices, the configuration at slot `u + Tr + 2 d + 3` is quiet, for every `u`. -/
theorem transfer_window {E : Env} (hM : MiscOK E) {s₀ : St} (H : Inv s₀) {Tr d : ℕ}
    (hR : ∀ i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v i = true)
    (hF : ∀ k u, ∃ v, u ≤ v ∧ v < u + d ∧ (E.fin v k).isSome) (u : ℕ) :
    Quiet (srun E s₀ (u + Tr + 2 * d + 3)) := by
  set T1 := u + Tr + d + 2 with hT1
  have hc : Calm0 (srun E s₀ T1) := fun i => by
    rcases closes hM H (i := i) (hR i) (hF (!i)) u with h | ⟨_, _, h⟩
    · exact h
    · rcases h with ⟨h, -⟩ | ⟨h, -⟩ | ⟨h, -⟩ <;> omega
  have hd : 1 ≤ d := by obtain ⟨v, h1, h2, -⟩ := hF false 0; omega
  have hjob : ∀ k, ((srun E s₀ (T1 + d)).nd k).job = none := fun k => by
    obtain ⟨v, hv, hv', hf⟩ := hF k T1
    have := slot_job_fin hM (srun_inv H v) (calm0_srun hM hc v hv) hf
    exact job_srun hM H (calm0_srun hM hc (v + 1) (by omega)) this _ (by omega)
  have hnr : ∀ c, NoReqL ((srun E s₀ (T1 + d)).chan c) := by
    have : T1 + d = (T1 + d - 1) + 1 := by omega
    rw [this]
    exact slot_noreq hM (srun_inv H _) (calm0_srun hM hc _ (by omega))
  have hemp : ∀ c, (srun E s₀ (T1 + d + 1)).chan c = [] :=
    slot_empty hM (srun_inv H _) (calm0_srun hM hc _ (by omega)) hjob hnr
  have heq : u + Tr + 2 * d + 3 = T1 + d + 1 := by omega
  rw [heq]
  have Hs := srun_inv (E := E) H (T1 + d + 1)
  have hc' := calm0_srun hM hc (T1 + d + 1) (by omega)
  have hj' : ∀ k, ((srun E s₀ (T1 + d + 1)).nd k).job = none := fun k =>
    slot_job hM (srun_inv H _) (calm0_srun hM hc _ (by omega)) (hjob k)
  simp only [Quiet, quietB, Bool.and_eq_true, List.isEmpty_iff, Option.isNone_iff_eq_none]
  exact ⟨⟨⟨⟨⟨⟨⟨hemp false, hemp true⟩, hc' false⟩, hc' true⟩, hj' false⟩, hj' true⟩, Hs.1.late⟩,
    Hs.2.late⟩

/-- The same, from the start of Phase 4 after any finite prefix of events (any losses and offers):
the window bound and exactly one owner at its end. -/
theorem transfer_window_owner (da db : Bool) (es : List Ev) {s₀ : St}
    (hrun : runEvs repairParams (start da db) es = some s₀) {E : Env} (hM : MiscOK E) {Tr d : ℕ}
    (hR : ∀ i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v i = true)
    (hF : ∀ k u, ∃ v, u ≤ v ∧ v < u + d ∧ (E.fin v k).isSome) (u : ℕ) :
    Quiet (srun E s₀ (u + Tr + 2 * d + 3)) ∧
      ConsistentPair (srun E s₀ (u + Tr + 2 * d + 3)).a.X (srun E s₀ (u + Tr + 2 * d + 3)).b.X := by
  have H := runEvs_pres (inv_start da db) hrun
  have hq := transfer_window hM H hR hF u
  have hI := srun_inv (E := E) H (u + Tr + 2 * d + 3)
  generalize srun E s₀ (u + Tr + 2 * d + 3) = t at hq hI ⊢
  exact ⟨hq, (cp_iff t.a.X t.b.X).1 (cp_of_quiet hI hq)⟩

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms transfer_window
open SwarmInfer.CoverWeave.ExecFull in
#print axioms transfer_window_owner

namespace SwarmInfer.CoverWeave.ExecFull

/-! ### Runs with offers: quiet a window after the last offer -/

/-- An environment that may also offer: in slot `t`, after the other events, end `i` offers the
edge by HANDOVER (`some false`) or PUSH (`some true`) if `off t i` says so and the offer is
enabled (it is skipped otherwise). -/
structure EnvO extends Env where
  off : ℕ → Bool → Option Bool

def offEv (E : EnvO) (t : ℕ) (i : Bool) : List Ev :=
  match E.off t i with
  | some push => [.offer i push]
  | none => []

def slotO (E : EnvO) (t : ℕ) (s : St) : St :=
  evsT (slot E.toEnv t s) (offEv E t false ++ offEv E t true)

def srunO (E : EnvO) (s₀ : St) : ℕ → St
  | 0 => s₀
  | t + 1 => slotO E t (srunO E s₀ t)

theorem srunO_inv {E : EnvO} {s₀ : St} (H : Inv s₀) : ∀ t, Inv (srunO E s₀ t)
  | 0 => H
  | t + 1 => evsT_inv (evsT_inv (srunO_inv H t) _) _

/-- The environment from slot `T` on. -/
def EnvO.shift (E : EnvO) (T : ℕ) : Env where
  room t := E.room (T + t)
  chain t := E.chain (T + t)
  rx t := E.rx (T + t)
  fin t := E.fin (T + t)
  misc t := E.misc (T + t)

theorem slot_shift (E : EnvO) (T t : ℕ) (s : St) :
    slot (E.shift T) t s = slot E.toEnv (T + t) s := rfl

theorem srunO_shift {E : EnvO} {s₀ : St} {T : ℕ} (hoff : ∀ v i, T ≤ v → E.off v i = none) :
    ∀ n, srunO E s₀ (T + n) = srun (E.shift T) (srunO E s₀ T) n
  | 0 => rfl
  | n + 1 => by
    show slotO E (T + n) (srunO E s₀ (T + n)) = slot (E.shift T) n _
    rw [srunO_shift hoff n, slot_shift]
    simp [slotO, offEv, hoff (T + n) false (by omega), hoff (T + n) true (by omega), evsT]

/-- **Quiet within the window after the last offer.** In a loss-free synchronous run of the edge
from any configuration satisfying the invariant, in which offers stop after slot `T`, every timer
fires at least once in every `Tr` slots and every chain ends at least once in every `d` slots, the
configuration at slot `T + Tr + 2 d + 3` is quiet and the edge has exactly one owner once the
message-free start is agreed. -/
theorem quiet_after_last_offer {E : EnvO} {s₀ : St} (H : Inv s₀) (hM : MiscOK E.toEnv) {T Tr d : ℕ}
    (hoff : ∀ v i, T ≤ v → E.off v i = none)
    (hR : ∀ i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v i = true)
    (hF : ∀ k u, ∃ v, u ≤ v ∧ v < u + d ∧ (E.fin v k).isSome) :
    Quiet (srunO E s₀ (T + Tr + 2 * d + 3)) ∧
      (Agreed (srunO E s₀ (T + Tr + 2 * d + 3)) →
        owns (srunO E s₀ (T + Tr + 2 * d + 3)).a ≠ owns (srunO E s₀ (T + Tr + 2 * d + 3)).b) := by
  have hM' : MiscOK (E.shift T) := fun t => hM (T + t)
  have hR' : ∀ i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ (E.shift T).rx v i = true := fun i u => by
    obtain ⟨v, h1, h2, h3⟩ := hR i (T + u)
    exact ⟨v - T, by omega, by omega, by simp only [EnvO.shift]; rw [show T + (v - T) = v by omega]; exact h3⟩
  have hF' : ∀ k u, ∃ v, u ≤ v ∧ v < u + d ∧ ((E.shift T).fin v k).isSome := fun k u => by
    obtain ⟨v, h1, h2, h3⟩ := hF k (T + u)
    exact ⟨v - T, by omega, by omega, by simp only [EnvO.shift]; rw [show T + (v - T) = v by omega]; exact h3⟩
  have hq := transfer_window hM' (srunO_inv (E := E) H T) hR' hF' 0
  rw [show 0 + Tr + 2 * d + 3 = Tr + 2 * d + 3 by omega, ← srunO_shift hoff,
    show T + (Tr + 2 * d + 3) = T + Tr + 2 * d + 3 by omega] at hq
  have hI := srunO_inv (E := E) H (T + Tr + 2 * d + 3)
  generalize srunO E s₀ (T + Tr + 2 * d + 3) = t at hq hI ⊢
  refine ⟨hq, fun hag => ?_⟩
  have hcp := cp_of_quiet hI hq
  simp only [Agreed, bne_iff_ne, ne_eq] at hag
  unfold owns
  revert hcp
  rcases t.a.X with _ | _ | _ <;> rcases t.b.X with _ | _ | _ <;>
    cases ha : t.a.dflt <;> cases hb : t.b.dflt <;> simp_all [CP]

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms quiet_after_last_offer
