import SwarmInferLean.CoverWeave.ExecFullTransferSyncR2pp
import SwarmInferLean.CoverWeave.ExecFullChain

/-!
# CoverWeave, the chain bound and Phase 4 under R2''

`ExecFullChain.lean` redone for `r2ppParams`: `closesP`, `noJob_srunO`, `ChainNet.chain_bound`,
`ChainNet.quiet_all`, `ChainNet.quiet_phase4`, in the namespace `ExecFull.R2pp`. Under R2'' a chain
whose request was refused as busy runs to its end and answers a refusal; the service discipline
`SeqOK` covers it unchanged.
-/

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-! ### Sequence numbers only grow -/

@[simp] theorem repeated_seqc (n : Node) (q : ℕ) : (repeated n q).1.seqc = n.seqc := by
  unfold repeated; split <;> (try split) <;> rfl
@[simp] theorem accept_seqc (P : Params) (n : Node) (room : Bool) :
    (accept P n room).1.seqc = n.seqc := by
  unfold accept; split_ifs <;> rfl

theorem onReq_seqc (s1 : St) (j : Bool) (q : ℕ) (pu : Bool) (g : ℕ) (room chain : Bool) :
    ((onReq r2ppParams s1 j q pu g room chain).nd j).seqc = (s1.nd j).seqc := by
  unfold onReq
  cases hl : (s1.nd j).cache.lookup q with
  | some r => simp [hl]
  | none =>
    simp only [hl]
    cases pu
    · simp only [Bool.not_false, ite_true]
      split_ifs <;> simp [reply_nd_self, cachePut]
    · simp only [Bool.not_true, Bool.false_eq_true, ite_false]
      cases hj : (s1.nd j).job with
      | none =>
        simp only [Bool.false_eq_true, ite_false, Bool.not_false, Bool.true_and, Bool.and_false]
        split_ifs <;> first
          | (rw [reply_nd_self]; simp [cachePut])
          | (simp only [accept_job, repeated_job, hj]; rw [reply_nd_self]; simp [cachePut])
          | (simp only [accept_job, repeated_job, hj]; simp)
      | some jb =>
        obtain ⟨q', b⟩ := jb
        by_cases hq : q' = q
        · subst hq
          simp only [decide_true, ite_true, Bool.not_true, Bool.false_and,
            Bool.false_eq_true, ite_false, Bool.true_and]
          split_ifs <;> first
            | (exfalso; simp [r2ppParams] at *; done)
            | (exfalso; rw [accept_eq] at *; split_ifs at * <;> simp_all; done)
            | (rw [reply_nd_self]; simp [cachePut])
            | (simp only [hj, ite_true]; rw [reply_nd_self]; simp [cachePut])
        · simp only [hq, decide_false, Bool.false_eq_true, ite_false, Bool.not_false, Bool.true_and,
            Bool.and_false]
          split_ifs <;> first
            | (rw [reply_nd_self]; simp [cachePut])
            | (simp only [accept_job, repeated_job, hj, ite_false, hq]
               rw [reply_nd_self]; simp [cachePut])

theorem onRep_seqc (P : Params) (s1 : St) (i : Bool) (q : ℕ) (r : Rep) :
    ((onRep P s1 i q r).nd i).seqc = (s1.nd i).seqc := by
  unfold onRep
  cases r.ok <;> cases r.late <;> simp <;> split <;> (try split_ifs) <;> simp [release]

theorem seqc_mono (s : St) (e : Ev) (k : Bool) : (s.nd k).seqc ≤ ((stepT s e).nd k).seqc := by
  cases e with
  | offer i push =>
    simp only [stepT, step]
    split_ifs
    · rcases bool_cases i k with rfl | rfl
      · simp
      · simp
    · simp
  | retx i q => simp only [stepT, step]; split <;> simp
  | lretx i q => simp only [stepT, step]; split_ifs <;> simp
  | evict i q =>
    simp only [stepT, step, Option.getD_some]; rcases bool_cases i k with rfl | rfl <;> simp
  | flip i =>
    simp only [stepT, step, Option.getD_some]; rcases bool_cases i k with rfl | rfl <;> simp
  | lose i => simp only [stepT, step]; split <;> simp
  | deliver c room chain =>
    cases hc : s.chan c with
    | nil => rw [stepT_nil room chain hc]
    | cons f l =>
      rcases bool_cases c k with rfl | rfl
      · cases f with
        | req q pu g =>
          rw [stepT_req room chain hc]
          have := (onReq_view (s.setChan c l) (!c) q pu g room chain).other
          rw [Bool.not_not] at this; rw [this]; simp
        | rep q r =>
          rw [stepT_rep room chain hc]
          have := (onRep_view r2ppParams (s.setChan c l) (!c) q r).1
          rw [Bool.not_not] at this; rw [this]; simp
        | conf q =>
          rw [stepT_conf room chain hc]
          have := (onConf_view (s.setChan c l) (!c) q).1
          rw [Bool.not_not] at this; rw [this]; simp
      · cases f with
        | req q pu g =>
          rw [stepT_req room chain hc, Bool.not_not, onReq_seqc]; simp
        | rep q r =>
          rw [stepT_rep room chain hc, Bool.not_not, onRep_seqc]; simp
        | conf q =>
          rw [stepT_conf room chain hc, Bool.not_not]; simp [onConf]
  | finish i ok room =>
    cases hj : (s.nd i).job with
    | none => simp [stepT, step, finishJob, hj]
    | some jb =>
      obtain ⟨q, b⟩ := jb
      simp only [stepT, step, finishJob, hj]
      split_ifs <;> simp only [Option.getD_some] <;>
      · rcases bool_cases i k with rfl | rfl
        · rw [reply_nd_self]; simp [cachePut]
        · have := reply_nd_not s (!k); rw [Bool.not_not] at this; rw [this]


theorem seqc_evsT (s : St) (es : List Ev) (k : Bool) : (s.nd k).seqc ≤ ((evsT s es).nd k).seqc := by
  induction es generalizing s with
  | nil => exact le_rfl
  | cons e es ih => exact (seqc_mono s e k).trans (ih _)

/-! ### Offers -/

theorem lv_offer_other {k : ℕ} {s : St} {i : Bool} (push : Bool) (h : Lv k s i) :
    Lv k (stepT s (.offer (!i) push)) i := by
  simp only [stepT, step]
  split_ifs
  · simp only [Option.getD_some]
    exact lv_gen (by simp) (fun _ _ h => by simp [h]) (fun x hx => by simpa using hx)
      (fun _ _ _ h => by simpa using h) h
  · exact h

theorem offer_self (s : St) (i push : Bool) :
    stepT s (.offer i push) = s ∨ ((s.nd i).pend = [] ∧
      ∃ p, ((stepT s (.offer i push)).nd i).pend = [p] ∧ p.seq = (s.nd i).seqc + 1) := by
  simp only [stepT, step]
  split_ifs with h
  · right
    obtain ⟨-, -, hp⟩ := h
    exact ⟨hp, ⟨(s.nd i).seqc + 1, push, (s.nd i).takes, (s.nd i).gen⟩, by simp [hp], rfl⟩
  · left; rfl

/-! ### Progress of one given request -/

/-- Level `k` of the progress of the request `p` of `i`: closed for good (`p` is not open and never
will be, its sequence number being behind the counter), or open at level `k`. -/
def LvP (k : ℕ) (p : Pend) (s : St) (i : Bool) : Prop :=
  ((s.nd i).pend ≠ [p] ∧ p.seq ≤ (s.nd i).seqc) ∨ ((s.nd i).pend = [p] ∧ Lv k s i)

theorem LvP.mono {k k' : ℕ} {p : Pend} {s : St} {i : Bool} (h : LvP k p s i) (hk : k ≤ k') :
    LvP k' p s i := by
  rcases h with h | ⟨h1, h2⟩
  · exact Or.inl h
  · exact Or.inr ⟨h1, h2.mono hk⟩

theorem lvP_of {k : ℕ} {p : Pend} {t : St} {i : Bool} (hl : Lv k t i) (hs : PSub p t i)
    (hq : p.seq ≤ (t.nd i).seqc) : LvP k p t i := by
  rcases hs with hs | hs
  · exact Or.inr ⟨hs, hl⟩
  · exact Or.inl ⟨by rw [hs]; simp, hq⟩

theorem lvP_step {k : ℕ} {p : Pend} {s : St} {i : Bool} {e : Ev} (H : Inv s)
    (he : WinEv e ∨ ∃ c push, e = .offer c push) (h : LvP k p s i) : LvP k p (stepT s e) i := by
  have hseq := seqc_mono s e i
  rcases he with he | ⟨c, push, rfl⟩
  · rcases h with ⟨h1, h2⟩ | ⟨h1, h2⟩
    · left; refine ⟨?_, h2.trans hseq⟩
      rcases ((inv_iff s).1 H i).pend with h0 | ⟨p', h0, -⟩
      · rcases lv_step (k := 0) (i := i) he (Or.inl h0) with h' | ⟨_, _, h'⟩
        · rw [h']; simp
        · rcases h' with ⟨h', -⟩ | ⟨h', -⟩ | ⟨h', -⟩ <;> omega
      · rcases psub_step (p := p') he (Or.inl h0) with h' | h'
        · rw [h']; rw [h0] at h1; exact h1
        · rw [h']; simp
    · have hq : p.seq ≤ (s.nd i).seqc := (((inv_iff s).1 H i).pend_seq h1).le
      exact lvP_of (lv_step he h2) (psub_step he (Or.inl h1)) (hq.trans hseq)
  · rcases bool_cases c i with rfl | rfl
    · rcases offer_self s c push with h' | ⟨hp0, p', hp', hs'⟩
      · rw [h']; exact h
      · left
        refine ⟨by rw [hp']; intro he; simp at he; subst he
                   rcases h with ⟨h1, h2⟩ | ⟨h1, -⟩
                   · omega
                   · rw [hp0] at h1; simp at h1, ?_⟩
        rcases h with ⟨-, h2⟩ | ⟨h1, -⟩
        · exact h2.trans hseq
        · rw [hp0] at h1; simp at h1
    · have hn : (stepT s (.offer (!i) push)).nd i = s.nd i := by
        simp only [stepT, step]; split_ifs <;> simp
      rcases h with ⟨h1, h2⟩ | ⟨h1, h2⟩
      · left; rw [hn]; exact ⟨h1, h2⟩
      · right; rw [hn]; exact ⟨h1, lv_offer_other push h2⟩

theorem lvP_evsT {k : ℕ} {p : Pend} {i : Bool} : ∀ (es : List Ev) (s : St), Inv s →
    (∀ e ∈ es, WinEv e ∨ ∃ c push, e = .offer c push) → LvP k p s i → LvP k p (evsT s es) i := by
  intro es
  induction es with
  | nil => intro s _ _ h; exact h
  | cons e es ih =>
    intro s H hes h
    exact ih _ (stepT_inv H e) (fun e' h' => hes e' (List.mem_cons_of_mem _ h'))
      (lvP_step H (hes e List.mem_cons_self) h)

theorem offEv_ok (E : EnvO) (t : ℕ) : ∀ e ∈ offEv E t false ++ offEv E t true,
    WinEv e ∨ ∃ c push, e = .offer c push := by
  intro e he
  simp only [List.mem_append, offEv] at he
  rcases he with h | h <;> (split at h <;> simp at h; subst h; exact Or.inr ⟨_, _, rfl⟩)

/-- A slot with offers keeps the level of the request; `step` lifts a slot lemma. -/
theorem lvP_slotO {E : EnvO} (hM : MiscOK E.toEnv) {t : ℕ} {s : St} (H : Inv s) {k k' : ℕ}
    {p : Pend} {i : Bool} (_hk : k' ≤ k)
    (hslot : Lv k s i → Lv k' (slot E.toEnv t s) i) (h : LvP k p s i) :
    LvP k' p (slotO E t s) i := by
  unfold slotO
  refine lvP_evsT _ _ (evsT_inv H _) (offEv_ok E t) ?_
  rcases h with ⟨h1, h2⟩ | ⟨h1, h2⟩
  · exact lvP_evsT (k := k') _ _ H (fun e he => Or.inl (slotEvs_win hM t s e he)) (Or.inl ⟨h1, h2⟩)
  · have hq : p.seq ≤ (s.nd i).seqc := (((inv_iff s).1 H i).pend_seq h1).le
    exact lvP_of (hslot h2)
      (evsT_win (X := fun u => PSub p u i) psub_win _ _ (slotEvs_win hM t s) (Or.inl h1))
      (hq.trans (seqc_evsT s _ i))


theorem slotO_ok (E : EnvO) (hM : MiscOK E.toEnv) (t : ℕ) (s : St) :
    ∀ e ∈ slotEvs E.toEnv t s ++ (offEv E t false ++ offEv E t true),
      WinEv e ∨ ∃ c push, e = .offer c push := by
  intro e he
  rcases List.mem_append.1 he with h | h
  · exact Or.inl (slotEvs_win hM t s e h)
  · exact offEv_ok E t e h

theorem slotO_eq (E : EnvO) (t : ℕ) (s : St) :
    slotO E t s = evsT s (slotEvs E.toEnv t s ++ (offEv E t false ++ offEv E t true)) := by
  simp [slotO, slot, evsT_append]

theorem lvP_srunO {E : EnvO} (hM : MiscOK E.toEnv) {s₀ : St} (H : Inv s₀) {k : ℕ} {p : Pend}
    {i : Bool} {a : ℕ} (h : LvP k p (srunO E s₀ a) i) : ∀ b, a ≤ b → LvP k p (srunO E s₀ b) i := by
  intro b hab
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact h
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · show LvP k p (slotO E b (srunO E s₀ b)) i
      rw [slotO_eq]
      exact lvP_evsT _ _ (srunO_inv H b) (slotO_ok E hM b _) (ih (by omega))
    · have : a = b + 1 := by omega
      subst this; exact h

/-- Open or closed for good. -/
def TopP (p : Pend) (s : St) (i : Bool) : Prop := LvP 0 p s i ∨ (s.nd i).pend = [p]

theorem topP_step {p : Pend} {s : St} {i : Bool} {e : Ev} (H : Inv s)
    (he : WinEv e ∨ ∃ c push, e = .offer c push) (h : TopP p s i) : TopP p (stepT s e) i := by
  rcases h with h | hp
  · exact Or.inl (lvP_step H he h)
  · have hq : p.seq ≤ (s.nd i).seqc := (((inv_iff s).1 H i).pend_seq hp).le
    rcases he with he | ⟨c, push, rfl⟩
    · rcases psub_step he (Or.inl hp) with h' | h'
      · exact Or.inr h'
      · exact Or.inl (Or.inl ⟨by rw [h']; simp, hq.trans (seqc_mono s e i)⟩)
    · rcases bool_cases c i with rfl | rfl
      · rcases offer_self s c push with h' | ⟨h0, -⟩
        · rw [h']; exact Or.inr hp
        · rw [hp] at h0; simp at h0
      · have hn : (stepT s (.offer (!i) push)).nd i = s.nd i := by
          simp only [stepT, step]; split_ifs <;> simp
        right; show ((stepT s (.offer (!i) push)).nd i).pend = [p]; rw [hn]; exact hp

theorem topP_evsT {p : Pend} {i : Bool} : ∀ (es : List Ev) (s : St), Inv s →
    (∀ e ∈ es, WinEv e ∨ ∃ c push, e = .offer c push) → TopP p s i → TopP p (evsT s es) i := by
  intro es
  induction es with
  | nil => intro s _ _ h; exact h
  | cons e es ih =>
    intro s H hes h
    exact ih _ (stepT_inv H e) (fun e' h' => hes e' (List.mem_cons_of_mem _ h'))
      (topP_step H (hes e List.mem_cons_self) h)

theorem topP_srunO {E : EnvO} (hM : MiscOK E.toEnv) {s₀ : St} (H : Inv s₀) {p : Pend}
    {i : Bool} {a : ℕ} (h : TopP p (srunO E s₀ a) i) : ∀ b, a ≤ b → TopP p (srunO E s₀ b) i := by
  intro b hab
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact h
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · show TopP p (slotO E b (srunO E s₀ b)) i
      rw [slotO_eq]
      exact topP_evsT _ _ (srunO_inv H b) (slotO_ok E hM b _) (ih (by omega))
    · have : a = b + 1 := by omega
      subst this; exact h

/-- **A request closes once the chain serving it ends (compositional form of `closes`).** In a
loss-free synchronous run in which both ends may offer, let the request `p` of `i` be open at slot
`u₀`, let `i`'s timer fire at least once in every `Tr` slots, and let every chain at `!i` serving
`p` be gone within `d` slots of any slot at which it runs. Then `p` is closed at slot
`u₀ + Tr + d + 2`. -/
theorem closesP {E : EnvO} (hM : MiscOK E.toEnv) {s₀ : St} (H : Inv s₀) {i : Bool} {Tr d : ℕ}
    {p : Pend} {u₀ : ℕ} (hp : ((srunO E s₀ u₀).nd i).pend = [p])
    (hR : ∀ u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v i = true)
    (hJ : ∀ v, HJob (srunO E s₀ v) i p → ∃ w, v ≤ w ∧ w ≤ v + d ∧ ¬ HJob (srunO E s₀ w) i p) :
    ((srunO E s₀ (u₀ + Tr + d + 2)).nd i).pend ≠ [p] := by
  obtain ⟨v1, hv1, hv1', hr⟩ := hR u₀
  have hT : TopP p (srunO E s₀ v1) i := topP_srunO hM H (Or.inr hp) v1 hv1
  have HI := srunO_inv (E := E) H
  -- after the retransmission
  have l3 : LvP 3 p (srunO E s₀ (v1 + 1)) i := by
    show LvP 3 p (slotO E v1 (srunO E s₀ v1)) i
    unfold slotO
    refine lvP_evsT _ _ (evsT_inv (HI v1) _) (offEv_ok E v1) ?_
    rcases hT with h | hp'
    · exact (lvP_evsT (k := 0) _ _ (HI v1) (fun e he => Or.inl (slotEvs_win hM v1 _ e he)) h).mono
        (by omega)
    · have hq : p.seq ≤ ((srunO E s₀ v1).nd i).seqc := (((inv_iff _).1 (HI v1) i).pend_seq hp').le
      exact lvP_of (slot_rx hM (HI v1) hr)
        (evsT_win (X := fun u => PSub p u i) psub_win _ _ (slotEvs_win hM v1 _) (Or.inl hp'))
        (hq.trans (seqc_evsT _ _ i))
  have l2 : LvP 2 p (srunO E s₀ (v1 + 2)) i :=
    lvP_slotO hM (HI (v1 + 1)) (by omega) (fun h => slot_cpy hM h) l3
  -- the chain serving `p` ends
  have l1 : ∃ w, w ≤ v1 + 2 + d ∧ LvP 1 p (srunO E s₀ w) i := by
    by_cases hj : HJob (srunO E s₀ (v1 + 2)) i p
    · obtain ⟨w, hw, hw', hnj⟩ := hJ _ hj
      refine ⟨w, hw', ?_⟩
      rcases lvP_srunO hM H l2 w hw with h | ⟨h1, h2⟩
      · exact Or.inl h
      · refine Or.inr ⟨h1, ?_⟩
        rcases h2 with h2 | ⟨p', hp', h2⟩
        · exact Or.inl h2
        · rw [h1, List.singleton_inj] at hp'; subst hp'
          rcases h2 with h2 | ⟨_, h2⟩ | ⟨h2, -⟩
          · exact Or.inr ⟨p, h1, Or.inl ⟨le_rfl, h2.2⟩⟩
          · exact absurd h2 hnj
          · omega
    · refine ⟨v1 + 2, by omega, ?_⟩
      rcases l2 with h | ⟨h1, h2⟩
      · exact Or.inl h
      · refine Or.inr ⟨h1, ?_⟩
        rcases h2 with h2 | ⟨p', hp', h2⟩
        · exact Or.inl h2
        · rw [h1, List.singleton_inj] at hp'; subst hp'
          rcases h2 with h2 | ⟨_, h2⟩ | ⟨h2, -⟩
          · exact Or.inr ⟨p, h1, Or.inl ⟨le_rfl, h2.2⟩⟩
          · exact absurd h2 hj
          · omega
  obtain ⟨w, hw, hl1⟩ := l1
  have l0 : LvP 0 p (srunO E s₀ (w + 1)) i :=
    lvP_slotO hM (HI w) (by omega) (fun h => slot_ans hM h) hl1
  rcases lvP_srunO hM H l0 _ (show w + 1 ≤ u₀ + Tr + d + 2 by omega) with ⟨h, -⟩ | ⟨h1, h2⟩
  · exact h
  · rcases h2 with h2 | ⟨_, _, h2⟩
    · rw [h1] at h2; simp at h2
    · rcases h2 with ⟨h, -⟩ | ⟨h, -⟩ | ⟨h, -⟩ <;> omega

end SwarmInfer.CoverWeave.ExecFull.R2pp

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-! ### A chain that has ended never comes back -/

/-- `j`'s mark is at least `q`: `q` was executed. -/
def Done (n : Node) (q : ℕ) : Prop := ¬ Fresh n.mark q

theorem done_of_le {n n' : Node} {q : ℕ} (h : Done n q)
    (hm : ∀ x, n.mark = some x → ∃ y, n'.mark = some y ∧ x ≤ y) : Done n' q := by
  simp only [Done, Fresh, not_forall, not_lt] at h ⊢
  obtain ⟨x, hx, hq⟩ := h
  obtain ⟨y, hy, hxy⟩ := hm x hx
  exact ⟨y, hy, hq.trans hxy⟩

theorem repeated_mark (n : Node) (q : ℕ) :
    ∀ x, n.mark = some x → ∃ y, (repeated n q).1.mark = some y ∧ x ≤ y := by
  intro x hx
  unfold repeated; rw [hx]
  dsimp only
  split_ifs with h
  · exact ⟨x, hx, le_rfl⟩
  · exact ⟨q, rfl, by omega⟩

@[simp] theorem accept_mark (P : Params) (n : Node) (room : Bool) :
    (accept P n room).1.mark = n.mark := by
  unfold accept; split_ifs <;> rfl

theorem onReq_mark (s1 : St) (j : Bool) (q : ℕ) (pu : Bool) (g : ℕ) (room chain : Bool) :
    ∀ x, (s1.nd j).mark = some x →
      ∃ y, ((onReq r2ppParams s1 j q pu g room chain).nd j).mark = some y ∧ x ≤ y := by
  intro x hx
  have hr := repeated_mark (s1.nd j) q x hx
  obtain ⟨y, hy, hxy⟩ := hr
  unfold onReq
  cases hl : (s1.nd j).cache.lookup q with
  | some r => simp only [hl]; exact ⟨x, by simpa using hx, le_rfl⟩
  | none =>
    simp only [hl]
    cases pu
    · simp only [Bool.not_false, ite_true]
      split_ifs <;> exact ⟨y, by rw [reply_nd_self]; simpa [cachePut] using hy, hxy⟩
    · simp only [Bool.not_true, Bool.false_eq_true, ite_false]
      cases hj : (s1.nd j).job with
      | none =>
        simp only [Bool.false_eq_true, ite_false, Bool.not_false, Bool.true_and, Bool.and_false]
        split_ifs <;> first
          | exact ⟨y, by rw [reply_nd_self]; simpa [cachePut] using hy, hxy⟩
          | (simp only [accept_job, repeated_job, hj]
             first
               | exact ⟨y, by rw [reply_nd_self]; simpa [cachePut] using hy, hxy⟩
               | exact ⟨y, by simp [hy], hxy⟩)
      | some jb =>
        obtain ⟨q', b⟩ := jb
        by_cases hq : q' = q
        · subst hq
          simp only [decide_true, ite_true, Bool.not_true, Bool.false_and,
            Bool.false_eq_true, ite_false, Bool.true_and]
          split_ifs <;> first
            | (exfalso; simp [r2ppParams] at *; done)
            | (exfalso; rw [accept_eq] at *; split_ifs at * <;> simp_all; done)
            | exact ⟨x, by rw [reply_nd_self]; simpa [cachePut] using hx, le_rfl⟩
            | (simp only [hj, ite_true]; exact ⟨x, by rw [reply_nd_self]; simpa [cachePut] using hx, le_rfl⟩)
        · simp only [hq, decide_false, Bool.false_eq_true, ite_false, Bool.not_false, Bool.true_and,
            Bool.and_false]
          split_ifs <;> first
            | exact ⟨y, by rw [reply_nd_self]; simpa [cachePut] using hy, hxy⟩
            | (simp only [accept_job, repeated_job, hj, ite_false, hq]
               exact ⟨y, by rw [reply_nd_self]; simp [cachePut, hy], hxy⟩)

end SwarmInfer.CoverWeave.ExecFull.R2pp

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

theorem onRep_mark (P : Params) (s1 : St) (i : Bool) (q : ℕ) (r : Rep) :
    ((onRep P s1 i q r).nd i).mark = (s1.nd i).mark := by
  unfold onRep
  cases r.ok <;> cases r.late <;> simp <;> split <;> (try split_ifs) <;> simp [release]

theorem onRep_job (P : Params) (s1 : St) (i : Bool) (q : ℕ) (r : Rep) :
    ((onRep P s1 i q r).nd i).job = (s1.nd i).job := (onRep_view P s1 i q r).2.2.2

/-- What one event does to the chain and the mark of end `j`. -/
theorem job_mark_step (s : St) (e : Ev) (j : Bool) :
    (∀ x, (s.nd j).mark = some x → ∃ y, ((stepT s e).nd j).mark = some y ∧ x ≤ y) ∧
    (((stepT s e).nd j).job = (s.nd j).job ∨ ((stepT s e).nd j).job = none ∨
      (∃ q, (s.nd j).job = none ∧ ((stepT s e).nd j).job = some (q, false) ∧ Fresh (s.nd j).mark q) ∨
      ∃ q b, (s.nd j).job = some (q, b) ∧ ((stepT s e).nd j).job = some (q, true)) := by
  have same : ∀ t : St, t.nd j = s.nd j →
      (∀ x, (s.nd j).mark = some x → ∃ y, (t.nd j).mark = some y ∧ x ≤ y) ∧
      ((t.nd j).job = (s.nd j).job ∨ (t.nd j).job = none ∨
        (∃ q, (s.nd j).job = none ∧ (t.nd j).job = some (q, false) ∧ Fresh (s.nd j).mark q) ∨
        ∃ q b, (s.nd j).job = some (q, b) ∧ (t.nd j).job = some (q, true)) :=
    fun t ht => ⟨fun x hx => ⟨x, by rw [ht]; exact hx, le_rfl⟩, Or.inl (by rw [ht])⟩
  cases e with
  | offer i push =>
    simp only [stepT, step]
    split_ifs
    · rcases bool_cases i j with rfl | rfl
      · exact ⟨fun x hx => ⟨x, by simpa using hx, le_rfl⟩, Or.inl (by simp)⟩
      · exact same _ (by simp)
    · exact same _ rfl
  | retx i q => simp only [stepT, step]; split <;> exact same _ (by simp)
  | lretx i q => simp only [stepT, step]; split_ifs <;> exact same _ (by simp)
  | evict i q =>
    simp only [stepT, step, Option.getD_some]
    rcases bool_cases i j with rfl | rfl
    · exact ⟨fun x hx => ⟨x, by simpa using hx, le_rfl⟩, Or.inl (by simp)⟩
    · exact same _ (by simp)
  | flip i =>
    simp only [stepT, step, Option.getD_some]
    rcases bool_cases i j with rfl | rfl
    · exact ⟨fun x hx => ⟨x, by simpa using hx, le_rfl⟩, Or.inl (by simp)⟩
    · exact same _ (by simp)
  | lose i => simp only [stepT, step]; split <;> exact same _ (by simp)
  | deliver c room chain =>
    cases hc : s.chan c with
    | nil => rw [stepT_nil room chain hc]; exact same _ rfl
    | cons f l =>
      rcases bool_cases c j with rfl | rfl
      · cases f with
        | req q pu g =>
          rw [stepT_req room chain hc]
          have := (onReq_view (s.setChan c l) (!c) q pu g room chain).other
          rw [Bool.not_not] at this; exact same _ (by rw [this]; simp)
        | rep q r =>
          rw [stepT_rep room chain hc]
          have := (onRep_view r2ppParams (s.setChan c l) (!c) q r).1
          rw [Bool.not_not] at this; exact same _ (by rw [this]; simp)
        | conf q =>
          rw [stepT_conf room chain hc]
          have := (onConf_view (s.setChan c l) (!c) q).1
          rw [Bool.not_not] at this; exact same _ (by rw [this]; simp)
      · cases f with
        | req q pu g =>
          rw [stepT_req room chain hc, Bool.not_not]
          have V := onReq_view (s.setChan (!j) l) j q pu g room chain
          refine ⟨fun x hx => onReq_mark (s.setChan (!j) l) j q pu g room chain x (by simpa using hx), ?_⟩
          rcases V.job with h | ⟨h0, h⟩ | ⟨b, hb, h⟩
          · exact Or.inl (by rw [h]; simp)
          · exact Or.inr (Or.inr (Or.inl ⟨q, by simpa using h0, h, by
              simpa using V.jobFresh h0 (by rw [h]; simp)⟩))
          · exact Or.inr (Or.inr (Or.inr ⟨q, b, by simpa using hb, h⟩))
        | rep q r =>
          rw [stepT_rep room chain hc, Bool.not_not]
          exact ⟨fun x hx => ⟨x, by rw [onRep_mark]; simpa using hx, le_rfl⟩,
            Or.inl (by rw [onRep_job]; simp)⟩
        | conf q =>
          rw [stepT_conf room chain hc, Bool.not_not]
          exact ⟨fun x hx => ⟨x, by simpa [onConf] using hx, le_rfl⟩, Or.inl (by simp [onConf])⟩
  | finish i ok room =>
    cases hj : (s.nd i).job with
    | none =>
      have : stepT s (.finish i ok room) = s := by simp [stepT, step, finishJob, hj]
      rw [this]; exact same _ rfl
    | some jb =>
      obtain ⟨q, b⟩ := jb
      simp only [stepT, step, finishJob, hj]
      split_ifs <;> simp only [Option.getD_some] <;>
      · rcases bool_cases i j with rfl | rfl
        · exact ⟨fun x hx => ⟨x, by rw [reply_nd_self]; simpa [cachePut] using hx, le_rfl⟩,
            Or.inr (Or.inl (by rw [reply_nd_self]; simp [cachePut]))⟩
        · have := reply_nd_not s (!j); rw [Bool.not_not] at this
          exact same _ (this ..)

/-- **A chain that has ended does not restart.** Once `j = !i` has executed `p` and runs no chain
for it, no chain for `p` ever runs there again. -/
theorem noJob_step {s : St} {i : Bool} {p : Pend} (e : Ev) (hd : Done (s.nd !i) p.seq)
    (hn : ¬ HJob s i p) : Done ((stepT s e).nd !i) p.seq ∧ ¬ HJob (stepT s e) i p := by
  obtain ⟨hm, hj⟩ := job_mark_step s e (!i)
  refine ⟨done_of_le hd hm, ?_⟩
  rintro ⟨b, hb⟩
  rcases hj with h | h | ⟨q, h0, h1, hf⟩ | ⟨q, b', h0, h1⟩
  · exact hn ⟨b, by rw [← h]; exact hb⟩
  · rw [h] at hb; simp at hb
  · rw [h1] at hb; simp at hb; obtain ⟨rfl, -⟩ := hb; exact hd hf
  · rw [h1] at hb; simp at hb; obtain ⟨rfl, -⟩ := hb; exact hn ⟨b', h0⟩

theorem noJob_evsT {i : Bool} {p : Pend} : ∀ (es : List Ev) (s : St), Done (s.nd !i) p.seq →
    ¬ HJob s i p → Done ((evsT s es).nd !i) p.seq ∧ ¬ HJob (evsT s es) i p := by
  intro es
  induction es with
  | nil => intro s h1 h2; exact ⟨h1, h2⟩
  | cons e es ih =>
    intro s h1 h2
    obtain ⟨h1', h2'⟩ := noJob_step e h1 h2
    exact ih _ h1' h2'

theorem noJob_srunO {E : EnvO} {s₀ : St} {i : Bool} {p : Pend} {a : ℕ}
    (hd : Done ((srunO E s₀ a).nd !i) p.seq) (hn : ¬ HJob (srunO E s₀ a) i p) :
    ∀ b, a ≤ b → ¬ HJob (srunO E s₀ b) i p := by
  intro b hab
  suffices Done ((srunO E s₀ b).nd !i) p.seq ∧ ¬ HJob (srunO E s₀ b) i p from this.2
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact ⟨hd, hn⟩
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · obtain ⟨h1, h2⟩ := ih (by omega)
      show Done ((slotO E b (srunO E s₀ b)).nd !i) p.seq ∧ ¬ HJob (slotO E b (srunO E s₀ b)) i p
      rw [slotO_eq]; exact noJob_evsT _ _ h1 h2
    · have : a = b + 1 := by omega
      subst this; exact ⟨hd, hn⟩

/-- A chain for `p` that runs at some slot implies `p` was executed there. -/
theorem done_of_hjob {s : St} {i : Bool} {p : Pend} (H : Inv s) (h : HJob s i p) :
    Done (s.nd !i) p.seq := by
  obtain ⟨b, hb⟩ := h
  exact ((inv_iff s).1 H i).jobEx p.seq b hb

theorem done_evsT {j : Bool} {q : ℕ} : ∀ (es : List Ev) (s : St), Done (s.nd j) q →
    Done ((evsT s es).nd j) q := by
  intro es
  induction es with
  | nil => intro s h; exact h
  | cons e es ih => intro s h; exact ih _ (done_of_le h (job_mark_step s e j).1)

theorem done_srunO {E : EnvO} {s₀ : St} (_H : Inv s₀) {i : Bool} {p : Pend} {a : ℕ}
    (hd : Done ((srunO E s₀ a).nd !i) p.seq) : ∀ b, a ≤ b → Done ((srunO E s₀ b).nd !i) p.seq := by
  intro b hab
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact hd
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · have h1 := ih (by omega)
      show Done ((slotO E b (srunO E s₀ b)).nd !i) p.seq
      rw [slotO_eq]
      exact done_evsT _ _ h1
    · have : a = b + 1 := by omega
      subst this; exact hd

end SwarmInfer.CoverWeave.ExecFull.R2pp

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-! ### Push chains across edges: the chain bound `d` -/

/-- A network of edge runs in the synchronous scheduler: each edge `e` runs the repaired transfer
layer from `init e` under its environment `env e`, whose choices (rooms, chains and their ends,
timers, offers) the nodes make; `ttl e i p` is the hop limit of the request `p` of end `i` of `e`
(its PUSH TTL; 0 for a HANDOVER). -/
structure ChainNet where
  Ed : Type
  env : Ed → EnvO
  init : Ed → St
  inv : ∀ e, Inv (init e)
  misc : ∀ e, MiscOK (env e).toEnv
  ttl : Ed → Bool → Pend → ℕ

namespace ChainNet

variable (N : ChainNet)

def run (e : N.Ed) (t : ℕ) : St := srunO (N.env e) (N.init e) t

/-- A probe of a chain: request `p` of end `i` of edge `e`, open at slot `a`. -/
structure Probe (N : ChainNet) where
  e : N.Ed
  i : Bool
  p : Pend
  a : ℕ

/-- The service discipline of a chain at `!i` for the PUSH `p` of `i` on `e` (`_service_push_job`,
`_resolve`, `_finish_push_job`): after the step that ended at slot `prev`, the next probe is open
from slot `prev` or `prev + 1` on and carries one hop less; the chain goes on from the first slot
`c` at which the probe is closed; once the list is exhausted (or a probe succeeded, which ends the
list), the chain is gone at slot `prev + 1`. -/
def SeqOK (e : N.Ed) (i : Bool) (p : Pend) : ℕ → List N.Probe → Prop
  | prev, [] => ¬ HJob (N.run e (prev + 1)) i p
  | prev, pr :: rest => prev ≤ pr.a ∧ pr.a ≤ prev + 1 ∧ ((N.run pr.e pr.a).nd pr.i).pend = [pr.p] ∧
      N.ttl pr.e pr.i pr.p + 1 = N.ttl e i p ∧
      ∀ c, pr.a ≤ c → ((N.run pr.e c).nd pr.i).pend ≠ [pr.p] →
        (∀ c', pr.a ≤ c' → c' < c → ((N.run pr.e c').nd pr.i).pend = [pr.p]) → SeqOK e i p c rest

/-- The chain bound: `d 0 = 0`, `d (t + 1) = 1 + (Δ - 1) (Tr + d t + 3)`. -/
def dBound (Δ Tr : ℕ) : ℕ → ℕ
  | 0 => 0
  | t + 1 => 1 + (Δ - 1) * (Tr + dBound Δ Tr t + 3)

theorem seq_bound {Δ Tr : ℕ}
    (hR : ∀ e i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ (N.env e).rx v i = true) {t : ℕ}
    (IH : ∀ e i p v, N.ttl e i p ≤ t → HJob (N.run e v) i p →
      ∃ w, v ≤ w ∧ w ≤ v + dBound Δ Tr t ∧ ¬ HJob (N.run e w) i p)
    {e : N.Ed} {i : Bool} {p : Pend} (hT : N.ttl e i p ≤ t + 1) :
    ∀ (probes : List N.Probe) (prev : ℕ), N.SeqOK e i p prev probes →
      ∃ w, prev < w ∧ w ≤ prev + 1 + probes.length * (Tr + dBound Δ Tr t + 3) ∧
        ¬ HJob (N.run e w) i p := by
  intro probes
  induction probes with
  | nil => intro prev h; exact ⟨prev + 1, by omega, by simp, h⟩
  | cons pr rest ih =>
    intro prev ⟨ha0, ha, hp, httl, hnext⟩
    have hc := closesP (N.misc pr.e) (N.inv pr.e) (i := pr.i) (Tr := Tr) (d := dBound Δ Tr t)
      (u₀ := pr.a) hp (hR pr.e pr.i)
      (fun v hv => IH pr.e pr.i pr.p v (by omega) hv)
    -- the first slot at which the probe is closed
    have hex : ∃ c, pr.a ≤ c ∧ ((N.run pr.e c).nd pr.i).pend ≠ [pr.p] :=
      ⟨_, by omega, hc⟩
    classical
    let c := Nat.find hex
    have hcs : pr.a ≤ c ∧ ((N.run pr.e c).nd pr.i).pend ≠ [pr.p] := Nat.find_spec hex
    have hfirst : ∀ c', pr.a ≤ c' → c' < c → ((N.run pr.e c').nd pr.i).pend = [pr.p] := by
      intro c' h1 h2
      by_contra h3
      exact Nat.find_min hex h2 ⟨h1, h3⟩
    have hcle : c ≤ pr.a + Tr + dBound Δ Tr t + 2 := Nat.find_min' hex ⟨by omega, hc⟩
    obtain ⟨w, hw0, hw, hj⟩ := ih _ (hnext c hcs.1 hcs.2 hfirst)
    refine ⟨w, by omega, ?_, hj⟩
    simp only [List.length_cons]
    nlinarith

/-- **Push chains end within `dBound Δ Tr t` slots.** In a network of edge runs in which every
timer fires at least once in every `Tr` slots, no chain serves a request without hops left, and
every chain follows the service discipline with at most `Δ - 1` probes (`Δ` the largest degree),
every chain serving a request of hop limit at most `t` is gone within `dBound Δ Tr t` slots of any
slot at which it runs. -/
theorem chain_bound {Δ Tr : ℕ}
    (hR : ∀ e i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ (N.env e).rx v i = true)
    (hBase : ∀ e i p v, HJob (N.run e v) i p → 1 ≤ N.ttl e i p)
    (hServe : ∀ e i p v, HJob (N.run e v) i p → ∃ s, s ≤ v ∧ HJob (N.run e s) i p ∧
      ∃ probes : List N.Probe, probes.length + 1 ≤ Δ ∧ N.SeqOK e i p s probes) :
    ∀ t e i p v, N.ttl e i p ≤ t → HJob (N.run e v) i p →
      ∃ w, v ≤ w ∧ w ≤ v + dBound Δ Tr t ∧ ¬ HJob (N.run e w) i p := by
  intro t
  induction t with
  | zero => intro e i p v ht hj; have := hBase e i p v hj; omega
  | succ t ih =>
    intro e i p v ht hj
    obtain ⟨s, hsv, hjs, probes, hlen, hseq⟩ := hServe e i p v hj
    obtain ⟨w, hw0, hw, hnj⟩ := N.seq_bound hR ih ht probes s hseq
    have hle : probes.length * (Tr + dBound Δ Tr t + 3) ≤ (Δ - 1) * (Tr + dBound Δ Tr t + 3) :=
      Nat.mul_le_mul_right _ (by omega)
    have hd : Done ((N.run e s).nd !i) p.seq := done_of_hjob (srunO_inv (N.inv e) s) hjs
    by_cases hwv : v ≤ w
    · exact ⟨w, hwv, by simp only [dBound]; omega, hnj⟩
    · exact absurd hj (noJob_srunO (done_srunO (N.inv e) hd w (by omega)) hnj v (by omega))

end ChainNet

end SwarmInfer.CoverWeave.ExecFull.R2pp

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-! ### Quiet after the last offer, with chains bounded by their duration -/

theorem psub_srun {E : Env} (hM : MiscOK E) {s₀ : St} {p : Pend} {i : Bool} {a : ℕ}
    (h : PSub p (srun E s₀ a) i) : ∀ b, a ≤ b → PSub p (srun E s₀ b) i := by
  intro b hab
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact h
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · exact evsT_win (X := fun u => PSub p u i) psub_win _ _ (slotEvs_win hM b _) (ih (by omega))
    · have : a = b + 1 := by omega
      subst this; exact h

/-- A chain that runs while nothing is open stays the same or ends. -/
theorem job_keep_step {u : St} {k : Bool} {q : ℕ} {e : Ev} (H : Inv u) (hc : Calm0 u)
    (he : WinEv e) (h : (∃ b, (u.nd k).job = some (q, b)) ∨ (u.nd k).job = none) :
    (∃ b, ((stepT u e).nd k).job = some (q, b)) ∨ ((stepT u e).nd k).job = none := by
  rcases h with ⟨b, h⟩ | h
  · rcases (job_mark_step u e k).2 with h' | h' | ⟨q', h0, -⟩ | ⟨q', b', h0, h1⟩
    · exact Or.inl ⟨b, h' ▸ h⟩
    · exact Or.inr h'
    · rw [h] at h0; simp at h0
    · rw [h] at h0; simp at h0; obtain ⟨rfl, -⟩ := h0; exact Or.inl ⟨true, h1⟩
  · exact Or.inr (job_none_step H hc h he)

theorem job_keep_srun {E : Env} (hM : MiscOK E) {s₀ : St} (H : Inv s₀) {k : Bool} {q : ℕ}
    {a : ℕ} (hc : Calm0 (srun E s₀ a))
    (h : (∃ b, ((srun E s₀ a).nd k).job = some (q, b)) ∨ ((srun E s₀ a).nd k).job = none) :
    ∀ b, a ≤ b → (∃ b', ((srun E s₀ b).nd k).job = some (q, b')) ∨
      ((srun E s₀ b).nd k).job = none := by
  intro b hab
  induction b with
  | zero => have : a = 0 := by omega
            subst this; exact h
  | succ b ih =>
    rcases Nat.lt_or_ge a (b + 1) with h' | h'
    · exact (evsT_win (X := fun u => Inv u ∧ Calm0 u ∧
          ((∃ b', (u.nd k).job = some (q, b')) ∨ (u.nd k).job = none))
        (fun u e he ⟨h1, h2, h3⟩ => ⟨stepT_inv h1 e, calm0_step he h2, job_keep_step h1 h2 he h3⟩)
        _ _ (slotEvs_win hM b _)
        ⟨srun_inv H b, calm0_srun hM hc b (by omega), ih (by omega)⟩).2.2
    · have : a = b + 1 := by omega
      subst this; exact h

/-- **Quiet after the last offer, chains bounded by their duration.** In a loss-free synchronous
run of the edge from any configuration satisfying the invariant, in which offers stop after slot
`T`, every timer fires at least once in every `Tr` slots and every chain at either end is gone
within `d` slots of any slot at which it runs, the edge is quiet at slot `T + Tr + 2 d + 4`. -/
theorem quiet_after_last_offer_chains {E : EnvO} {s₀ : St} (H : Inv s₀) (hM : MiscOK E.toEnv)
    {T Tr d : ℕ} (hoff : ∀ v i, T ≤ v → E.off v i = none)
    (hR : ∀ i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v i = true)
    (hJ : ∀ i p v, HJob (srunO E s₀ v) i p → ∃ w, v ≤ w ∧ w ≤ v + d ∧ ¬ HJob (srunO E s₀ w) i p) :
    Quiet (srunO E s₀ (T + Tr + 2 * d + 4)) := by
  have hM' : MiscOK (E.shift T) := fun t => hM (T + t)
  have hsh0 := srunO_shift (s₀ := s₀) hoff
  obtain ⟨s₁, hs₁⟩ : ∃ s₁, srunO E s₀ T = s₁ := ⟨_, rfl⟩
  have hsh : ∀ n, srunO E s₀ (T + n) = srun (E.shift T) s₁ n := fun n => by rw [hsh0, hs₁]
  have H₁ : Inv s₁ := hs₁ ▸ srunO_inv H T
  have HI : ∀ n, Inv (srun (E.shift T) s₁ n) := srun_inv H₁
  -- every request open at `T` closes
  have hc : Calm0 (srun (E.shift T) s₁ (Tr + d + 2)) := by
    intro i
    rcases ((inv_iff s₁).1 H₁ i).pend with h0 | ⟨p, hp', -⟩
    · rcases lv_srun (k := 0) (i := i) hM' (s₀ := s₁) (a := 0) (Or.inl h0) _ (by omega) with h | ⟨_, _, h⟩
      · exact h
      · rcases h with ⟨h, -⟩ | ⟨h, -⟩ | ⟨h, -⟩ <;> omega
    · have hp : ((srunO E s₀ T).nd i).pend = [p] := by rw [hs₁]; exact hp'
      have hcl := closesP hM H (i := i) (u₀ := T) hp (hR i) (hJ i p)
      rw [show T + Tr + d + 2 = T + (Tr + d + 2) by omega, hsh] at hcl
      rcases psub_srun (p := p) (i := i) hM' (s₀ := s₁) (a := 0) (Or.inl hp') (Tr + d + 2) (by omega)
        with h | h
      · exact absurd h hcl
      · exact h
  obtain ⟨T₁, hT₁⟩ : ∃ T₁, Tr + d + 2 = T₁ := ⟨_, rfl⟩
  rw [hT₁] at hc
  -- every chain running at `T₁` ends within `d` slots, and none starts
  have hjob : ∀ k, ((srun (E.shift T) s₁ (T₁ + d)).nd k).job = none := by
    intro k
    cases hj : ((srun (E.shift T) s₁ T₁).nd k).job with
    | none =>
      exact job_srun hM' H₁ hc hj _ (by omega)
    | some x =>
      obtain ⟨q, b⟩ := x
      have hj' : HJob (srunO E s₀ (T + T₁)) (!k) ⟨q, false, 0, 0⟩ := ⟨b, by rw [hsh]; simpa using hj⟩
      obtain ⟨w, hw, hw', hnj⟩ := hJ _ _ _ hj'
      have hwT : w = T + (w - T) := by omega
      rw [hwT, hsh] at hnj
      have hk := job_keep_srun hM' H₁ hc (Or.inl ⟨b, hj⟩) (w - T) (by omega)
      have hnone : ((srun (E.shift T) s₁ (w - T)).nd k).job = none := by
        rcases hk with ⟨b', h⟩ | h
        · exact absurd ⟨b', by simpa using h⟩ hnj
        · exact h
      exact job_srun hM' H₁ (calm0_srun hM' hc _ (by omega)) hnone _ (by omega)
  have hjob1 : ∀ k, ((srun (E.shift T) s₁ (T₁ + d + 1)).nd k).job = none := fun k =>
    slot_job hM' (HI _) (calm0_srun hM' hc _ (by omega)) (hjob k)
  have hnr : ∀ c, NoReqL ((srun (E.shift T) s₁ (T₁ + d + 1)).chan c) :=
    slot_noreq hM' (HI _) (calm0_srun hM' hc _ (by omega))
  have hemp : ∀ c, (srun (E.shift T) s₁ (T₁ + d + 2)).chan c = [] :=
    slot_empty hM' (HI _) (calm0_srun hM' hc _ (by omega)) hjob1 hnr
  have heq : T + Tr + 2 * d + 4 = T + (T₁ + d + 2) := by omega
  rw [heq, hsh]
  have hc' := calm0_srun hM' hc (T₁ + d + 2) (by omega)
  have hj' : ∀ k, ((srun (E.shift T) s₁ (T₁ + d + 2)).nd k).job = none := fun k =>
    slot_job hM' (HI _) (calm0_srun hM' hc _ (by omega)) (hjob1 k)
  have Hs := HI (T₁ + d + 2)
  generalize srun (E.shift T) s₁ (T₁ + d + 2) = t at hemp hc' hj' Hs ⊢
  simp only [Quiet, quietB, Bool.and_eq_true, List.isEmpty_iff, Option.isNone_iff_eq_none]
  exact ⟨⟨⟨⟨⟨⟨⟨hemp false, hemp true⟩, hc' false⟩, hc' true⟩, hj' false⟩, hj' true⟩, Hs.1.late⟩,
    Hs.2.late⟩

end SwarmInfer.CoverWeave.ExecFull.R2pp

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-- **The transfer layer of the network is quiet `Tr + 2 d(D) + 4` slots after the last offer.**
In a network of edge runs in which every timer fires at least once in every `Tr` slots, push chains
follow the service discipline with at most `Δ - 1` probes, no chain serves a request without hops
left, every hop limit is at most `D` and no edge sees an offer after slot `T`, every edge is quiet at
slot `T + Tr + 2 dBound Δ Tr D + 4`. -/
theorem ChainNet.quiet_all (N : ChainNet) {Δ Tr D T : ℕ}
    (hR : ∀ e i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ (N.env e).rx v i = true)
    (hBase : ∀ e i p v, HJob (N.run e v) i p → 1 ≤ N.ttl e i p)
    (hServe : ∀ e i p v, HJob (N.run e v) i p → ∃ s, s ≤ v ∧ HJob (N.run e s) i p ∧
      ∃ probes : List N.Probe, probes.length + 1 ≤ Δ ∧ N.SeqOK e i p s probes)
    (hD : ∀ e i p, N.ttl e i p ≤ D) (hoff : ∀ e v i, T ≤ v → (N.env e).off v i = none) (e : N.Ed) :
    Quiet (N.run e (T + Tr + 2 * ChainNet.dBound Δ Tr D + 4)) :=
  quiet_after_last_offer_chains (N.inv e) (N.misc e) (hoff e) (hR e)
    (fun i p v hj => N.chain_bound hR hBase hServe D e i p v (hD e i p) hj)

end SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull.R2pp in
#print axioms closesP
open SwarmInfer.CoverWeave.ExecFull.R2pp in
#print axioms ChainNet.chain_bound
open SwarmInfer.CoverWeave.ExecFull.R2pp in
#print axioms quiet_after_last_offer_chains
open SwarmInfer.CoverWeave.ExecFull.R2pp in
#print axioms ChainNet.quiet_all

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-! ### When the offers stop -/

namespace ChainNet

variable (N : ChainNet)

/-- The offering discipline of end `i` of edge `e` after slot `prev` (the ladder of
`_fix_overload` and the probes of `_service_push_job`, one own transfer open at a time): the next
offer, if any, opens within `π` slots after the previous request closed, with no offer in
between; after the last one no offer follows `π` slots after its closure. -/
def OfferSeq (π : ℕ) (e : N.Ed) (i : Bool) : ℕ → List N.Probe → Prop
  | prev, [] => ∀ v, prev + π ≤ v → (N.env e).off v i = none
  | prev, pr :: rest => pr.e = e ∧ pr.i = i ∧ pr.a ≤ prev + π ∧
      ((N.run e pr.a).nd i).pend = [pr.p] ∧
      (∀ v, prev + π ≤ v → v < pr.a → (N.env e).off v i = none) ∧
      ∀ c, pr.a ≤ c → ((N.run e c).nd i).pend ≠ [pr.p] → OfferSeq π e i c rest

theorem offerSeq_stop {π Tr d : ℕ}
    (hR : ∀ e i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ (N.env e).rx v i = true)
    (hJ : ∀ e i p v, HJob (N.run e v) i p → ∃ w, v ≤ w ∧ w ≤ v + d ∧ ¬ HJob (N.run e w) i p)
    {e : N.Ed} {i : Bool} :
    ∀ (os : List N.Probe) (prev : ℕ), N.OfferSeq π e i prev os →
      ∀ v, prev + os.length * (π + Tr + d + 2) + π ≤ v → (N.env e).off v i = none := by
  intro os
  induction os with
  | nil => intro prev h v hv; exact h v (by simpa using hv)
  | cons pr rest ih =>
    intro prev ⟨he, hi, ha, hp, hgap, hnext⟩ v hv
    subst he; subst hi
    have hc := closesP (N.misc pr.e) (N.inv pr.e) (i := pr.i) (Tr := Tr) (d := d) (u₀ := pr.a) hp
      (hR pr.e pr.i) (fun v hv => hJ pr.e pr.i pr.p v hv)
    exact ih _ (hnext _ (by omega) hc) v (by simp only [List.length_cons] at hv; nlinarith)

/-- **Phase 4 is quiet `W` slots after the signatures settle.** In a network of edge runs with
bounded timers (`Tr`), push chains that follow the service discipline (at most `Δ - 1` probes,
hop limits at most `D`) and ends that offer by the discipline `OfferSeq` with at most `n` offers
each after slot `T₀` and idle gaps of at most `π` slots, every edge is quiet at
`T₀ + n (π + Tr + d + 2) + π + Tr + 2 d + 4`, `d = dBound Δ Tr D`. -/
theorem quiet_phase4 {Δ Tr D π n T₀ : ℕ}
    (hR : ∀ e i u, ∃ v, u ≤ v ∧ v < u + Tr ∧ (N.env e).rx v i = true)
    (hBase : ∀ e i p v, HJob (N.run e v) i p → 1 ≤ N.ttl e i p)
    (hServe : ∀ e i p v, HJob (N.run e v) i p → ∃ s, s ≤ v ∧ HJob (N.run e s) i p ∧
      ∃ probes : List N.Probe, probes.length + 1 ≤ Δ ∧ N.SeqOK e i p s probes)
    (hD : ∀ e i p, N.ttl e i p ≤ D)
    (hOff : ∀ e i, ∃ os : List N.Probe, os.length ≤ n ∧ N.OfferSeq π e i T₀ os) (e : N.Ed) :
    Quiet (N.run e (T₀ + n * (π + Tr + dBound Δ Tr D + 2) + π + Tr + 2 * dBound Δ Tr D + 4)) := by
  have hJ := fun e i p v hj => N.chain_bound hR hBase hServe D e i p v (hD e i p) hj
  have hstop : ∀ e v i, T₀ + n * (π + Tr + dBound Δ Tr D + 2) + π ≤ v → (N.env e).off v i = none := by
    intro e v i hv
    obtain ⟨os, hlen, hos⟩ := hOff e i
    exact N.offerSeq_stop (d := dBound Δ Tr D) hR hJ os T₀ hos v
      (le_trans (by have := Nat.mul_le_mul_right (π + Tr + dBound Δ Tr D + 2) hlen; omega) hv)
  exact quiet_after_last_offer_chains (N.inv e) (N.misc e) (hstop e) (hR e)
    (fun i p v hj => hJ e i p v hj)

end ChainNet

end SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull.R2pp in
#print axioms ChainNet.quiet_phase4
