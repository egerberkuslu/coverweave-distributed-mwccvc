import SwarmInferLean.CoverWeave.ExecFullChainR2pp

/-!
# CoverWeave, Phase 4: a concrete controller for the push chains (R2'')

A network of edges, each running the repaired transfer layer (`r2ppParams`) in the synchronous
scheduler, with a node controller read off `_service_push_job` and `_fix_overload` (`bbcvc.py`):
a node serves at most one push chain, probes its other ends one at a time with one hop less, goes
on only once the probe is closed, and ends the chain when a probe succeeded or no eligible end is
left. The result `ctl_seqOK` is that every chain follows `ChainNet.SeqOK` with at most `Δ - 1`
probes; with `ctl_base` this gives `ctl_chain_bound`, the chain bound `dBound` for the concrete
controller.

Modelling choices: decisions of a slot are taken from the configuration at its start; an end is
probed only when nothing is in flight towards it (otherwise a delivery in the same slot could
disable the offer; the code checks this at the moment of the offer); a chain is started only at an
end whose incoming requests all carry hops (`ttl > 0`, the code's check on the delivered PUSH);
hop limits are a ghost map set when a request is made. Rooms, timers, evictions and the ladder's
offers at nodes without a chain are free.

Part 1: what one synchronous slot of one edge does to the push chain of an end.
-/

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-- Without the chain flag a request starts no chain. -/
theorem onReq_job_none {s1 : St} {j : Bool} {q : ℕ} {pu : Bool} {g : ℕ} {room : Bool}
    (hj : (s1.nd j).job = none) :
    ((onReq r2ppParams s1 j q pu g room false).nd j).job = none := by
  unfold onReq
  cases hl : (s1.nd j).cache.lookup q with
  | some r => simpa [hl] using hj
  | none =>
    simp only [hl]
    cases pu
    · simp only [Bool.not_false, ite_true]
      split_ifs <;> simp [reply_nd_self, hj]
    · simp only [Bool.not_true, Bool.false_eq_true, ite_false, hj]
      split_ifs <;> simp_all [reply_nd_self]

/-- What one event does to the chain of `c`: nothing, a chain end, a busy copy marks it nacked, or
a delivered request with the chain flag starts it. -/
theorem job_ev (u : St) (ev : Ev) (c : Bool) :
    ((stepT u ev).nd c).job = (u.nd c).job ∨ (∃ ok room, ev = .finish c ok room) ∨
      (∃ q b, (u.nd c).job = some (q, b) ∧ ((stepT u ev).nd c).job = some (q, true)) ∨
      (∃ room q pu g l, ev = .deliver (!c) room true ∧ u.chan (!c) = .req q pu g :: l ∧
        (u.nd c).job = none ∧ ((stepT u ev).nd c).job = some (q, false)) := by
  cases ev with
  | deliver d room chain =>
    cases hc : u.chan d with
    | nil => left; rw [stepT_nil room chain hc]
    | cons f l =>
      rcases bool_cases d c with rfl | rfl
      · left
        cases f with
        | req q pu g =>
          rw [stepT_req room chain hc]
          have := (onReq_view (u.setChan d l) (!d) q pu g room chain).other
          rw [Bool.not_not] at this; rw [this]; simp
        | rep q r =>
          rw [stepT_rep room chain hc]
          have := (onRep_view r2ppParams (u.setChan d l) (!d) q r).1
          rw [Bool.not_not] at this; rw [this]; simp
        | conf q =>
          rw [stepT_conf room chain hc]
          have := (onConf_view (u.setChan d l) (!d) q).1
          rw [Bool.not_not] at this; rw [this]; simp
      · cases f with
        | req q pu g =>
          rw [stepT_req room chain hc, Bool.not_not]
          have V := onReq_view (u.setChan (!c) l) c q pu g room chain
          rcases V.job with h | ⟨h0, h⟩ | ⟨b', hb', h⟩
          · left; rw [h]; simp
          · cases chain
            · exfalso
              have := onReq_job_none (pu := pu) (g := g) (room := room) (q := q) h0
              rw [this] at h; simp at h
            · exact Or.inr (Or.inr (Or.inr ⟨room, q, pu, g, l, rfl, hc, by simpa using h0, h⟩))
          · exact Or.inr (Or.inr (Or.inl ⟨q, b', by simpa using hb', h⟩))
        | rep q r =>
          left; rw [stepT_rep room chain hc, Bool.not_not]
          rw [(onRep_view r2ppParams (u.setChan (!c) l) c q r).2.2.2]; simp
        | conf q =>
          left; rw [stepT_conf room chain hc, Bool.not_not]
          rw [(onConf_view (u.setChan (!c) l) c q).2.2.1]; simp
  | finish d ok room =>
    rcases bool_cases d c with rfl | rfl
    · exact Or.inr (Or.inl ⟨ok, room, rfl⟩)
    · left
      cases hjc : (u.nd (!c)).job with
      | none => simp [stepT, step, finishJob, hjc]
      | some jb =>
        obtain ⟨q, b⟩ := jb
        simp only [stepT, step, finishJob, hjc]
        split_ifs <;> simp only [Option.getD_some] <;>
        · have := reply_nd_not u (!c); rw [Bool.not_not] at this; rw [this]
  | offer d push =>
    left
    simp only [stepT, step]
    split_ifs
    · rcases bool_cases d c with rfl | rfl <;> simp
    · rfl
  | retx d q =>
    left; simp only [stepT, step]; split <;> simp
  | lretx d q =>
    left; simp only [stepT, step]; split_ifs <;> simp
  | evict d q =>
    left; simp only [stepT, step, Option.getD_some]
    rcases bool_cases d c with rfl | rfl <;> simp
  | flip d =>
    left; simp only [stepT, step, Option.getD_some]
    rcases bool_cases d c with rfl | rfl <;> simp
  | lose d =>
    left; simp only [stepT, step]; split <;> simp

/-! ### Over a list of events -/

def NoFin (c : Bool) (es : List Ev) : Prop := ∀ ev ∈ es, ∀ ok room, ev ≠ .finish c ok room
def NoDel (es : List Ev) : Prop := ∀ ev ∈ es, ∀ d room ch, ev ≠ .deliver d room ch
def AllD (es : List Ev) : Prop := ∀ ev ∈ es, ∃ d room ch, ev = .deliver d room ch

theorem job_keep_evsT {c : Bool} {q : ℕ} : ∀ (es : List Ev) (u : St), NoFin c es →
    (∃ b, (u.nd c).job = some (q, b)) → ∃ b, ((evsT u es).nd c).job = some (q, b) := by
  intro es
  induction es with
  | nil => intro u _ h; exact h
  | cons ev es ih =>
    intro u hf ⟨b, hb⟩
    apply ih _ (fun e he => hf e (List.mem_cons_of_mem _ he))
    rcases job_ev u ev c with h | ⟨ok, room, rfl⟩ | ⟨q', b', h0, h⟩ | ⟨_, _, _, _, _, -, -, h0, -⟩
    · exact ⟨b, h ▸ hb⟩
    · exact absurd rfl (hf _ List.mem_cons_self ok room)
    · rw [hb] at h0; simp at h0; obtain ⟨rfl, -⟩ := h0; exact ⟨true, h⟩
    · rw [hb] at h0; simp at h0

theorem job_none_evsT {c : Bool} : ∀ (es : List Ev) (u : St), NoDel es →
    (u.nd c).job = none → ((evsT u es).nd c).job = none := by
  intro es
  induction es with
  | nil => intro u _ h; exact h
  | cons ev es ih =>
    intro u hd hj
    apply ih _ (fun e he => hd e (List.mem_cons_of_mem _ he))
    rcases job_ev u ev c with h | ⟨ok, room, rfl⟩ | ⟨q', b', h0, h⟩ | ⟨room, _, _, _, _, rfl, -⟩
    · rw [h, hj]
    · have : stepT u (.finish c ok room) = u := by simp [stepT, step, finishJob, hj]
      rw [this]; exact hj
    · rw [hj] at h0; simp at h0
    · exact absurd rfl (hd _ List.mem_cons_self (!c) room true)

/-- After the deliveries, a chain that survives to the end of the slot is the one that was there. -/
theorem job_rest_evsT {c : Bool} {q q' : ℕ} {b : Bool} : ∀ (es : List Ev) (u : St) (b' : Bool),
    NoDel es → (u.nd c).job = some (q', b') → ((evsT u es).nd c).job = some (q, b) → q' = q := by
  intro es
  induction es with
  | nil => intro u _ _ h h'; simp only [evsT] at h'; rw [h] at h'; simp at h'; exact h'.1
  | cons ev es ih =>
    intro u b' hd hj hf
    have hd' : NoDel es := fun e he => hd e (List.mem_cons_of_mem _ he)
    rcases job_ev u ev c with h | ⟨ok, room, rfl⟩ | ⟨q'', b'', h0, h⟩ | ⟨room, _, _, _, _, rfl, -⟩
    · exact ih _ _ hd' (h ▸ hj) hf
    · rcases job_none_fin (u := u) (k := c) ok room with h | h
      · have := job_none_evsT es _ hd' h
        simp only [evsT] at hf; rw [this] at hf; simp at hf
      · rw [hj] at h; simp at h
    · rw [hj] at h0; simp at h0; obtain ⟨rfl, -⟩ := h0; exact ih _ _ hd' h hf
    · exact absurd rfl (hd _ List.mem_cons_self (!c) room true)

/-- Requests on the channel into `c` that were there at the start (deliveries append none). -/
def ReqFrom (c : Bool) (l0 : List Frame) (u : St) : Prop :=
  ∀ q pu g, Frame.req q pu g ∈ u.chan (!c) → Frame.req q pu g ∈ l0

theorem reqFrom_deliver {c : Bool} {l0 : List Frame} {u : St} (h : ReqFrom c l0 u)
    (d room ch : Bool) : ReqFrom c l0 (stepT u (.deliver d room ch)) := by
  intro q pu g hm
  rcases bool_cases d c with rfl | rfl
  · obtain ⟨ext, he, hn⟩ := deliver_ext u d room ch
    rw [he] at hm
    rcases List.mem_append.1 hm with hm | hm
    · exact h q pu g hm
    · exact absurd hm (hn q pu g)
  · rw [(chan_deliver u (!c) room ch).1] at hm
    exact h q pu g (List.mem_of_mem_tail hm)

/-- **A chain starts only from a request that was in flight, with the chain flag.** -/
theorem job_new_D {c : Bool} {l0 : List Frame} {q : ℕ} {b : Bool} : ∀ (es : List Ev) (u : St),
    AllD es → ReqFrom c l0 u → (u.nd c).job = none → ((evsT u es).nd c).job = some (q, b) →
    (∃ room, Ev.deliver (!c) room true ∈ es) ∧ ∃ pu g, Frame.req q pu g ∈ l0 := by
  intro es
  induction es with
  | nil => intro u _ _ hj h; simp only [evsT] at h; rw [hj] at h; simp at h
  | cons ev es ih =>
    intro u hd hr hj hf
    have hd' : AllD es := fun e he => hd e (List.mem_cons_of_mem _ he)
    obtain ⟨d, room, ch, rfl⟩ := hd _ List.mem_cons_self
    rcases job_ev u (.deliver d room ch) c with h | ⟨_, _, h⟩ | ⟨q', b', h0, -⟩ |
        ⟨room', q', pu, g, l, he, hc, -, h⟩
    · obtain ⟨⟨r, hr'⟩, hm⟩ := ih _ hd' (reqFrom_deliver hr d room ch) (h ▸ hj) hf
      exact ⟨⟨r, List.mem_cons_of_mem _ hr'⟩, hm⟩
    · simp at h
    · rw [hj] at h0; simp at h0
    · have hnf : NoFin c es := fun e he ok r h' => by
        obtain ⟨_, _, _, h''⟩ := hd' e he; rw [h''] at h'; simp at h'
      obtain ⟨b'', hb''⟩ := job_keep_evsT es _ hnf ⟨false, h⟩
      simp only [evsT] at hf; rw [hb''] at hf; simp at hf; obtain ⟨rfl, -⟩ := hf
      refine ⟨⟨room', by rw [← he]; exact List.mem_cons_self⟩, pu, g, hr _ _ _ (by rw [hc]; simp)⟩

/-! ### One slot of one edge -/

theorem slotO_split4 (E : EnvO) (t : ℕ) (s : St) :
    slotO E t s = evsT (evsT s (delivs E.toEnv t false s.fromA.length ++
      delivs E.toEnv t true s.fromB.length)) (finEv E.toEnv t false ++ finEv E.toEnv t true ++
      (rxEv E.toEnv t false s ++ rxEv E.toEnv t true s ++ E.misc t ++
      (offEv E t false ++ offEv E t true))) := by
  simp only [slotO, slot, slotEvs, List.append_assoc, evsT_append]

theorem allD_delivs (E : Env) (t : ℕ) (s : St) :
    AllD (delivs E t false s.fromA.length ++ delivs E t true s.fromB.length) := by
  intro e he
  rcases List.mem_append.1 he with h | h
  · obtain ⟨r, ch, rfl⟩ := allDel_delivs E t false _ e h; exact ⟨_, _, _, rfl⟩
  · obtain ⟨r, ch, rfl⟩ := allDel_delivs E t true _ e h; exact ⟨_, _, _, rfl⟩

theorem noDel_tail (E : EnvO) (hM : MiscOK E.toEnv) (t : ℕ) (s : St) :
    NoDel (rxEv E.toEnv t false s ++ rxEv E.toEnv t true s ++ E.misc t ++
      (offEv E t false ++ offEv E t true)) := by
  intro ev hev d room ch h
  subst h
  simp only [List.mem_append, rxEv, offEv] at hev
  rcases hev with ((h | h) | h) | h | h
  · split at h <;> simp at h
  · split at h <;> simp at h
  · rcases hM t _ h with ⟨_, _, h⟩ | ⟨_, h⟩ <;> simp at h
  · split at h <;> simp at h
  · split at h <;> simp at h

theorem noDel_fin (E : Env) (t : ℕ) (c : Bool) : NoDel (finEv E t c) := by
  intro ev hev d room ch h; subst h; simp only [finEv] at hev; split at hev <;> simp at hev

theorem noFin_D (E : Env) (t : ℕ) (s : St) (c : Bool) :
    NoFin c (delivs E t false s.fromA.length ++ delivs E t true s.fromB.length) := by
  intro ev hev ok room h; subst h
  obtain ⟨_, _, _, h⟩ := allD_delivs E t s _ hev; simp at h

theorem noFin_tail (E : EnvO) (hM : MiscOK E.toEnv) (t : ℕ) (s : St) (c : Bool) :
    NoFin c (rxEv E.toEnv t false s ++ rxEv E.toEnv t true s ++ E.misc t ++
      (offEv E t false ++ offEv E t true)) := by
  intro ev hev ok room h
  subst h
  simp only [List.mem_append, rxEv, offEv] at hev
  rcases hev with ((h | h) | h) | h | h
  · split at h <;> simp at h
  · split at h <;> simp at h
  · rcases hM t _ h with ⟨_, _, h⟩ | ⟨_, h⟩ <;> simp at h
  · split at h <;> simp at h
  · split at h <;> simp at h

theorem noFin_fin_other (E : Env) (t : ℕ) (c : Bool) : NoFin c (finEv E t (!c)) := by
  intro ev hev ok room h; subst h; simp only [finEv] at hev; split at hev <;> simp at hev

theorem noFin_fin_none {E : Env} {t : ℕ} {c : Bool} (h : E.fin t c = none) : NoFin c (finEv E t c) := by
  intro ev hev; simp [finEv, h] at hev

theorem fin_cases (E : Env) (t : ℕ) (c : Bool) :
    finEv E t false ++ finEv E t true = finEv E t c ++ finEv E t (!c) ∨
      finEv E t false ++ finEv E t true = finEv E t (!c) ++ finEv E t c := by
  cases c
  · left; rfl
  · right; rfl

/-- **The chain of `c` survives a slot without its end.** -/
theorem slotO_job_keep {E : EnvO} (hM : MiscOK E.toEnv) {t : ℕ} {s : St} {c : Bool} {q : ℕ}
    (hf : E.fin t c = none) (h : ∃ b, (s.nd c).job = some (q, b)) :
    ∃ b, ((slotO E t s).nd c).job = some (q, b) := by
  rw [slotO_split4, evsT_append]
  refine job_keep_evsT _ _ (noFin_tail E hM t s c) (job_keep_evsT _ _ ?_
    (job_keep_evsT _ _ (noFin_D _ t s c) h))
  intro ev hev
  rcases fin_cases E.toEnv t c with he | he <;> rw [he] at hev <;>
    rcases List.mem_append.1 hev with h | h
  · exact noFin_fin_none hf ev h
  · exact noFin_fin_other _ t c ev h
  · exact noFin_fin_other _ t c ev h
  · exact noFin_fin_none hf ev h

/-- **The end of a chain ends it.** -/
theorem slotO_job_fin {E : EnvO} (hM : MiscOK E.toEnv) {t : ℕ} {s : St} {c : Bool} {q : ℕ}
    {b ok room : Bool} (hf : E.fin t c = some (ok, room)) (h : (s.nd c).job = some (q, b)) :
    ((slotO E t s).nd c).job = none := by
  rw [slotO_split4, evsT_append]
  apply job_none_evsT _ _ (noDel_tail E hM t s)
  have hD := job_keep_evsT _ _ (noFin_D E.toEnv t s c) ⟨b, h⟩
  generalize evsT s _ = u at hD
  have hfc : finEv E.toEnv t c = [.finish c ok room] := by simp [finEv, hf]
  have fin1 : ∀ v, (∃ b, (v.nd c).job = some (q, b)) → ((stepT v (.finish c ok room)).nd c).job = none :=
    fun v ⟨b, hb⟩ => by
      rcases job_none_fin (u := v) (k := c) ok room with h | h
      · exact h
      · rw [hb] at h; simp at h
  rcases fin_cases E.toEnv t c with he | he <;> rw [he, hfc, evsT_append]
  · exact job_none_evsT _ _ (noDel_fin _ t _) (fin1 u hD)
  · apply fin1
    exact job_keep_evsT _ _ (noFin_fin_other _ t c) hD

/-- **A chain starts only with the chain flag, from a request in flight at the start of the
slot.** -/
theorem slotO_job_new {E : EnvO} (hM : MiscOK E.toEnv) {t : ℕ} {s : St} {c : Bool} {q : ℕ}
    {b : Bool} (h0 : (s.nd c).job = none) (h : ((slotO E t s).nd c).job = some (q, b)) :
    (∃ k, E.chain t (!c) k = true) ∧ ∃ pu g, Frame.req q pu g ∈ s.chan (!c) := by
  rw [slotO_split4] at h
  generalize hu : evsT s (delivs E.toEnv t false s.fromA.length ++
    delivs E.toEnv t true s.fromB.length) = u at h
  cases hju : (u.nd c).job with
  | none =>
    have hnd : NoDel (finEv E.toEnv t false ++ finEv E.toEnv t true ++
        (rxEv E.toEnv t false s ++ rxEv E.toEnv t true s ++ E.misc t ++
        (offEv E t false ++ offEv E t true))) := by
      intro ev hev
      rcases List.mem_append.1 hev with h' | h'
      · rcases List.mem_append.1 h' with h'' | h''
        · exact noDel_fin _ t false ev h''
        · exact noDel_fin _ t true ev h''
      · exact noDel_tail E hM t s ev h'
    rw [job_none_evsT _ _ hnd hju] at h; simp at h
  | some jb =>
    obtain ⟨q', b'⟩ := jb
    have hnd : NoDel (finEv E.toEnv t false ++ finEv E.toEnv t true ++
        (rxEv E.toEnv t false s ++ rxEv E.toEnv t true s ++ E.misc t ++
        (offEv E t false ++ offEv E t true))) := by
      intro ev hev
      rcases List.mem_append.1 hev with h' | h'
      · rcases List.mem_append.1 h' with h'' | h''
        · exact noDel_fin _ t false ev h''
        · exact noDel_fin _ t true ev h''
      · exact noDel_tail E hM t s ev h'
    have hq := job_rest_evsT _ _ _ hnd hju h
    subst hq
    obtain ⟨⟨room, hm⟩, hfr⟩ := job_new_D (l0 := s.chan (!c)) _ s (allD_delivs E.toEnv t s)
      (fun _ _ _ h => h) h0 (by rw [hu]; exact hju)
    refine ⟨?_, hfr⟩
    simp only [List.mem_append, delivs, List.mem_map, List.mem_range] at hm
    rcases hm with ⟨k, -, hk⟩ | ⟨k, -, hk⟩
    · simp only [Ev.deliver.injEq] at hk; obtain ⟨h1, -, h3⟩ := hk
      exact ⟨k, by rw [← h1, h3]⟩
    · simp only [Ev.deliver.injEq] at hk; obtain ⟨h1, -, h3⟩ := hk
      exact ⟨k, by rw [← h1, h3]⟩

/-! ### An eligible end offers successfully -/

/-- What `offer` reads and writes of a node. -/
def Core (n : Node) : Option Bool × Bool × Option (ℕ × Bool) × List Pend × ℕ × ℕ × ℕ :=
  (n.X, n.dflt, n.job, n.pend, n.seqc, n.takes, n.gen)

/-- The events of a slot that leave `c` alone, as far as `offer` sees it. -/
def Allowed (c : Bool) (ev : Ev) : Prop :=
  (∃ r ch, ev = .deliver c r ch) ∨ (∃ ok r, ev = .finish (!c) ok r) ∨ (∃ d q, ev = .retx d q) ∨
    (∃ d q, ev = .evict d q) ∨ (∃ p, ev = .offer (!c) p)

theorem core_ev (u : St) {c : Bool} {ev : Ev} (h : Allowed c ev) :
    Core ((stepT u ev).nd c) = Core (u.nd c) := by
  rcases h with ⟨room, ch, rfl⟩ | ⟨ok, room, rfl⟩ | ⟨d, q, rfl⟩ | ⟨d, q, rfl⟩ | ⟨pu, rfl⟩
  · cases hc : u.chan c with
    | nil => rw [stepT_nil room ch hc]
    | cons f l =>
      cases f with
      | req q pu g =>
        rw [stepT_req room ch hc]
        have := (onReq_view (u.setChan c l) (!c) q pu g room ch).other
        rw [Bool.not_not] at this; rw [this]; simp
      | rep q r =>
        rw [stepT_rep room ch hc]
        have := (onRep_view r2ppParams (u.setChan c l) (!c) q r).1
        rw [Bool.not_not] at this; rw [this]; simp
      | conf q =>
        rw [stepT_conf room ch hc]
        have := (onConf_view (u.setChan c l) (!c) q).1
        rw [Bool.not_not] at this; rw [this]; simp
  · cases hjc : (u.nd (!c)).job with
    | none => simp [stepT, step, finishJob, hjc]
    | some jb =>
      obtain ⟨q, b⟩ := jb
      simp only [stepT, step, finishJob, hjc]
      split_ifs <;> simp only [Option.getD_some] <;>
      · have := reply_nd_not u (!c); rw [Bool.not_not] at this; rw [this]
  · simp only [stepT, step]; split <;> simp
  · simp only [stepT, step, Option.getD_some]
    rcases bool_cases d c with rfl | rfl <;> simp [Core]
  · simp only [stepT, step]; split_ifs
    · simp
    · rfl

theorem core_evsT {c : Bool} : ∀ (es : List Ev) (u : St), (∀ ev ∈ es, Allowed c ev) →
    Core ((evsT u es).nd c) = Core (u.nd c) := by
  intro es
  induction es with
  | nil => intro u _; rfl
  | cons ev es ih =>
    intro u h
    simp only [evsT]
    rw [ih _ (fun e he => h e (List.mem_cons_of_mem _ he)), core_ev u (h ev List.mem_cons_self)]

/-- Cache evictions are the only other events of the slot. -/
def EvictOnly (E : Env) : Prop := ∀ t, ∀ ev ∈ E.misc t, ∃ d q, ev = .evict d q

theorem EvictOnly.misc {E : Env} (h : EvictOnly E) : MiscOK E := fun t ev hev => by
  obtain ⟨d, q, rfl⟩ := h t ev hev; exact Or.inl ⟨d, q, rfl⟩

theorem slotEvs_allowed {E : Env} (hE : EvictOnly E) {t : ℕ} {s : St} {c : Bool}
    (hch : s.chan (!c) = []) (hf : E.fin t c = none) : ∀ ev ∈ slotEvs E t s, Allowed c ev := by
  intro ev hev
  simp only [slotEvs, List.mem_append] at hev
  rcases hev with (((((h | h) | h) | h) | h) | h) | h
  · obtain ⟨r, ch, rfl⟩ := allDel_delivs E t false _ ev h
    cases c
    · exact Or.inl ⟨r, ch, rfl⟩
    · simp [St.chan] at hch; simp [hch, delivs] at h
  · obtain ⟨r, ch, rfl⟩ := allDel_delivs E t true _ ev h
    cases c
    · simp [St.chan] at hch; simp [hch, delivs] at h
    · exact Or.inl ⟨r, ch, rfl⟩
  · simp only [finEv] at h; split at h <;> simp at h; subst h
    cases c
    · simp_all
    · exact Or.inr (Or.inl ⟨_, _, rfl⟩)
  · simp only [finEv] at h; split at h <;> simp at h; subst h
    cases c
    · exact Or.inr (Or.inl ⟨_, _, rfl⟩)
    · simp_all
  · simp only [rxEv] at h; split at h <;> simp at h; subst h; exact Or.inr (Or.inr (Or.inl ⟨_, _, rfl⟩))
  · simp only [rxEv] at h; split at h <;> simp at h; subst h; exact Or.inr (Or.inr (Or.inl ⟨_, _, rfl⟩))
  · obtain ⟨d, q, rfl⟩ := hE t _ h; exact Or.inr (Or.inr (Or.inr (Or.inl ⟨d, q, rfl⟩)))

theorem offEv_allowed (E : EnvO) (t : ℕ) (c : Bool) : ∀ ev ∈ offEv E t (!c), Allowed c ev := by
  intro ev hev; simp only [offEv] at hev; split at hev <;> simp at hev
  subst hev; exact Or.inr (Or.inr (Or.inr (Or.inr ⟨_, rfl⟩)))

/-- **An eligible end with an empty incoming channel opens its offer.** -/
theorem slotO_offer {E : EnvO} (hE : EvictOnly E.toEnv) {t : ℕ} {s : St} {c : Bool}
    (hX : (s.nd c).X = some true ∨ ((s.nd c).X = none ∧ (s.nd c).dflt = true))
    (hj : (s.nd c).job = none) (hp : (s.nd c).pend = []) (hch : s.chan (!c) = [])
    (hf : E.fin t c = none) (ho : E.off t c = some true) :
    ((slotO E t s).nd c).pend = [⟨(s.nd c).seqc + 1, true, (s.nd c).takes, (s.nd c).gen⟩] ∧
      ((slotO E t s).nd c).seqc = (s.nd c).seqc + 1 := by
  have hc := core_evsT _ s (slotEvs_allowed hE hch hf)
  unfold slotO slot
  generalize evsT s (slotEvs E.toEnv t s) = u at hc ⊢
  have hoff : ∀ v : St, Core (v.nd c) = Core (s.nd c) →
      ((stepT v (.offer c true)).nd c).pend =
        [⟨(s.nd c).seqc + 1, true, (s.nd c).takes, (s.nd c).gen⟩] ∧
      ((stepT v (.offer c true)).nd c).seqc = (s.nd c).seqc + 1 := by
    intro v hv
    simp only [Core, Prod.mk.injEq] at hv
    obtain ⟨h1, h2, h3, h4, h5, h6, h7⟩ := hv
    have hpre : ((v.nd c).X = some true ∨ ((v.nd c).X = none ∧ (v.nd c).dflt = true)) ∧
        (v.nd c).job = none ∧ (v.nd c).pend = [] := by
      rw [h1, h2, h3, h4]; exact ⟨hX, hj, hp⟩
    simp only [stepT, step, hpre, and_self, ite_true, Option.getD_some]
    simp [h5, h6, h7]
  cases c
  · simp only [offEv, ho, List.singleton_append, evsT]
    have h1 := hoff u hc
    have h2 := core_evsT _ (stepT u (.offer false true)) (offEv_allowed E t false)
    simp only [Core, Prod.mk.injEq, offEv] at h2
    simp only [Bool.not_false] at h2
    exact ⟨h2.2.2.2.1 ▸ h1.1, h2.2.2.2.2.1 ▸ h1.2⟩
  · have h0 := core_evsT _ u (offEv_allowed E t true)
    simp only [Bool.not_true] at h0
    rw [evsT_append]
    simp only [offEv, ho, evsT]
    exact hoff _ (h0.trans hc)

/-- **An open request of `c` only closes in a slot without an offer of `c`.** -/
theorem slotO_psub {E : EnvO} (hM : MiscOK E.toEnv) {t : ℕ} {s : St} {c : Bool} {p : Pend}
    (h : PSub p s c) (ho : E.off t c = none) : PSub p (slotO E t s) c := by
  have h1 : PSub p (slot E.toEnv t s) c :=
    evsT_win (X := fun u => PSub p u c) psub_win _ _ (slotEvs_win hM t s) h
  unfold slotO
  generalize slot E.toEnv t s = u at h1 ⊢
  have hk : ∀ v : St, PSub p v c → ∀ es, (∀ ev ∈ es, Allowed c ev) → PSub p (evsT v es) c := by
    intro v hv es hes
    have := core_evsT es v hes
    simp only [Core, Prod.mk.injEq] at this
    unfold PSub; rw [this.2.2.2.1]; exact hv
  cases c
  · simp only [offEv, ho, List.nil_append]
    exact hk u h1 _ (offEv_allowed E t false)
  · simp only [offEv, ho, List.append_nil]
    exact hk u h1 _ (offEv_allowed E t true)

/-! ## The network and its controller

Every node serves at most one chain. Its decisions in slot `t` are taken from the configuration at
the start of slot `t`: in the first slot of its chain, and in every slot after the probe of the
chain closed, it ends the chain (the probe succeeded: the probed end no longer holds its edge; or no
eligible end is left) or probes the next eligible end with one hop less. An end is eligible when
it may offer and nothing is in flight towards it, so that nothing in the slot can disable its
offer. A chain is started at an end whose incoming requests all carry hops. Rooms, timers,
evictions and the offers of the ladder at nodes without a chain are free. -/

/-- The graph: nodes, edges, and for every node its edge ends (`(e, c)`: the node is end `c` of
edge `e`). -/
structure Topo where
  W : Type
  Ed : Type
  dW : DecidableEq W
  dE : DecidableEq Ed
  ends : W → List (Ed × Bool)
  own : Ed → Bool → W
  hown : ∀ w e c, (e, c) ∈ ends w ↔ own e c = w
  nodup : ∀ w, (ends w).Nodup

attribute [instance] Topo.dW Topo.dE

/-- The controller's record of a chain: its end, the ends it probed, and the open probe (edge end
and sequence number). -/
structure CRec (T : Topo) where
  J : T.Ed × Bool
  tried : List (T.Ed × Bool)
  probe : Option (T.Ed × Bool × ℕ)

/-- A network configuration: every edge's state, every node's chain record, and the hop limit of
every request (edge, end, sequence number). -/
structure NS (T : Topo) where
  es : T.Ed → St
  crec : T.W → Option (CRec T)
  ttl : T.Ed → Bool → ℕ → ℕ

/-- The free choices of the rest of the protocol. -/
structure NEnv (T : Topo) where
  room : ℕ → T.Ed → Bool → ℕ → Bool
  rx : ℕ → T.Ed → Bool → Bool
  ladder : ℕ → T.Ed → Bool → Option Bool
  ladTtl : ℕ → T.Ed → Bool → ℕ
  evict : ℕ → T.Ed → List (Bool × ℕ)

variable {T : Topo}

def nodeAt (es : T.Ed → St) (x : T.Ed × Bool) : Node := (es x.1).nd x.2
/-- The frames in flight towards end `x`. -/
def inChan (es : T.Ed → St) (x : T.Ed × Bool) : List Frame := (es x.1).chan (!x.2)

/-- `offer` is enabled at `x`. -/
def offerable (es : T.Ed → St) (x : T.Ed × Bool) : Bool :=
  (decide ((nodeAt es x).X = some true) ||
    (decide ((nodeAt es x).X = none) && (nodeAt es x).dflt)) &&
  (nodeAt es x).job.isNone && (nodeAt es x).pend.isEmpty

/-- `x` may be probed: `offer` is enabled and nothing is in flight towards it. -/
def eligible (es : T.Ed → St) (x : T.Ed × Bool) : Bool := offerable es x && (inChan es x).isEmpty

def ttlOK (S : NS T) (x : T.Ed × Bool) : Bool :=
  (inChan S.es x).all fun f => match f with
    | .req q _ _ => decide (1 ≤ S.ttl x.1 (!x.2) q)
    | _ => true

def hasPush (S : NS T) (x : T.Ed × Bool) : Bool :=
  (inChan S.es x).any fun f => match f with
    | .req _ true _ => true
    | _ => false

/-- The end at which `w` may start a chain in this slot. -/
def chainEnd (S : NS T) (w : T.W) : Option (T.Ed × Bool) :=
  match S.crec w with
  | some _ => none
  | none => (T.ends w).find? fun x => hasPush S x && ttlOK S x

/-- The controller's action at a node. -/
inductive CAct (T : Topo)
  | idle
  | fin (ok : Bool)
  | probe (x : T.Ed × Bool)

def cands (S : NS T) (w : T.W) (r : CRec T) : List (T.Ed × Bool) :=
  (T.ends w).filter fun x => decide (x ≠ r.J) && decide (x ∉ r.tried) && eligible S.es x

def nextAct (S : NS T) (w : T.W) (r : CRec T) : CAct T :=
  match cands S w r with
  | [] => .fin false
  | x :: _ => .probe x

def cact (S : NS T) (w : T.W) : CAct T :=
  match S.crec w with
  | none => .idle
  | some r =>
    if (nodeAt S.es r.J).job.isNone then .idle else
    match r.probe with
    | some pr =>
      if (nodeAt S.es (pr.1, pr.2.1)).pend.any (fun p => decide (p.seq = pr.2.2)) then .idle
      else if decide ((nodeAt S.es (pr.1, pr.2.1)).X = some false) then .fin true
      else nextAct S w r
    | none => nextAct S w r

/-- The hop limit of the request that `w`'s chain serves. -/
def jobTtl (S : NS T) (w : T.W) : ℕ :=
  match S.crec w with
  | some r =>
    match (nodeAt S.es r.J).job with
    | some (q, _) => S.ttl r.J.1 (!r.J.2) q
    | none => 0
  | none => 0

def offAt (E : NEnv T) (S : NS T) (t : ℕ) (e : T.Ed) (c : Bool) : Option Bool :=
  match cact S (T.own e c) with
  | .probe x => if x = (e, c) then some true else none
  | _ =>
    if (S.crec (T.own e c)).isNone && (chainEnd S (T.own e c)).isNone && offerable S.es (e, c)
    then E.ladder t e c else none

def finAt (E : NEnv T) (S : NS T) (t : ℕ) (e : T.Ed) (c : Bool) : Option (Bool × Bool) :=
  match cact S (T.own e c) with
  | .fin ok => if (S.crec (T.own e c)).map CRec.J = some (e, c) then some (ok, E.room t e c 0) else none
  | _ => none

/-- The environment of edge `e` in slot `t`, as the controller sets it from `S`. -/
def envAt (E : NEnv T) (S : NS T) (t : ℕ) (e : T.Ed) : EnvO where
  room _ c k := E.room t e c k
  chain _ c _ := decide (chainEnd S (T.own e (!c)) = some (e, !c))
  rx _ c := E.rx t e c
  fin _ c := finAt E S t e c
  misc _ := (E.evict t e).map fun x => .evict x.1 x.2
  off _ c := offAt E S t e c

def recNext (S : NS T) (es' : T.Ed → St) (w : T.W) : Option (CRec T) :=
  match S.crec w with
  | none =>
    match chainEnd S w with
    | some x => if (nodeAt es' x).job.isSome then some ⟨x, [], none⟩ else none
    | none => none
  | some r =>
    match cact S w with
    | .idle => if (nodeAt S.es r.J).job.isNone then none else some r
    | .fin _ => none
    | .probe x => some ⟨r.J, x :: r.tried, some (x.1, x.2, (nodeAt S.es x).seqc + 1)⟩

/-- A probe carries one hop less than the request its chain serves, a ladder offer the ladder's
limit. -/
def ttlNext (E : NEnv T) (S : NS T) (t : ℕ) (e : T.Ed) (c : Bool) (q : ℕ) : ℕ :=
  if q = (nodeAt S.es (e, c)).seqc + 1 then
    match offAt E S t e c with
    | some _ =>
      match cact S (T.own e c) with
      | .probe _ => jobTtl S (T.own e c) - 1
      | _ => E.ladTtl t e c
    | none => S.ttl e c q
  else S.ttl e c q

def ctlStep (E : NEnv T) (S : NS T) (t : ℕ) : NS T where
  es e := slotO (envAt E S t e) t (S.es e)
  crec w := recNext S (fun e => slotO (envAt E S t e) t (S.es e)) w
  ttl e c q := ttlNext E S t e c q

def netRunC (E : NEnv T) (S₀ : NS T) : ℕ → NS T
  | 0 => S₀
  | t + 1 => ctlStep E (netRunC E S₀ t) t

/-- The environment of edge `e` over the whole run. -/
def envOf (E : NEnv T) (S₀ : NS T) (e : T.Ed) : EnvO where
  room t := (envAt E (netRunC E S₀ t) t e).room t
  chain t := (envAt E (netRunC E S₀ t) t e).chain t
  rx t := (envAt E (netRunC E S₀ t) t e).rx t
  fin t := (envAt E (netRunC E S₀ t) t e).fin t
  misc t := (envAt E (netRunC E S₀ t) t e).misc t
  off t := (envAt E (netRunC E S₀ t) t e).off t

theorem slotO_congr {E E' : EnvO} {t : ℕ} (s : St) (h1 : E.room t = E'.room t)
    (h2 : E.chain t = E'.chain t) (h3 : E.rx t = E'.rx t) (h4 : E.fin t = E'.fin t)
    (h5 : E.misc t = E'.misc t) (h6 : E.off t = E'.off t) : slotO E t s = slotO E' t s := by
  simp only [slotO, slot, slotEvs, delivs, finEv, rxEv, offEv, h1, h2, h3, h4, h5, h6]

/-- **Each edge runs the one-edge model.** -/
theorem netRunC_proj (E : NEnv T) (S₀ : NS T) (e : T.Ed) :
    ∀ t, (netRunC E S₀ t).es e = srunO (envOf E S₀ e) (S₀.es e) t
  | 0 => rfl
  | t + 1 => by
    show slotO (envAt E (netRunC E S₀ t) t e) t ((netRunC E S₀ t).es e) =
      slotO (envOf E S₀ e) t (srunO (envOf E S₀ e) (S₀.es e) t)
    rw [netRunC_proj E S₀ e t]
    exact slotO_congr _ rfl rfl rfl rfl rfl rfl

theorem envAt_evict (E : NEnv T) (S : NS T) (t : ℕ) (e : T.Ed) :
    EvictOnly (envAt E S t e).toEnv := by
  intro t' ev hev
  simp only [envAt, List.mem_map] at hev
  obtain ⟨x, -, rfl⟩ := hev; exact ⟨_, _, rfl⟩

theorem envOf_evict (E : NEnv T) (S₀ : NS T) (e : T.Ed) : EvictOnly (envOf E S₀ e).toEnv :=
  fun t => envAt_evict E (netRunC E S₀ t) t e t

/-! ### The controller's actions -/

theorem mem_cands {S : NS T} {w : T.W} {r : CRec T} {x : T.Ed × Bool} :
    x ∈ cands S w r ↔ x ∈ T.ends w ∧ x ≠ r.J ∧ x ∉ r.tried ∧ eligible S.es x = true := by
  simp [cands, and_assoc]

theorem cact_open {S : NS T} {w : T.W} {r : CRec T} {pr : T.Ed × Bool × ℕ}
    (h : S.crec w = some r) (hj : (nodeAt S.es r.J).job.isNone = false) (hp : r.probe = some pr)
    (ho : (nodeAt S.es (pr.1, pr.2.1)).pend.any (fun p => decide (p.seq = pr.2.2)) = true) :
    cact S w = .idle := by
  simp only [cact, h, hj, hp, ho]; rfl

theorem cact_dec {S : NS T} {w : T.W} {r : CRec T}
    (h : S.crec w = some r) (hj : (nodeAt S.es r.J).job.isNone = false)
    (hc : r.probe = none ∨ ∃ pr, r.probe = some pr ∧
      (nodeAt S.es (pr.1, pr.2.1)).pend.any (fun p => decide (p.seq = pr.2.2)) = false) :
    (∃ ok, cact S w = .fin ok) ∨ ∃ x, cact S w = .probe x ∧ x ∈ cands S w r := by
  have hn : (∃ ok, nextAct S w r = .fin ok) ∨ ∃ x, nextAct S w r = .probe x ∧ x ∈ cands S w r := by
    unfold nextAct
    split
    · exact Or.inl ⟨false, rfl⟩
    · rename_i x l hl; exact Or.inr ⟨x, rfl, by rw [hl]; exact List.mem_cons_self⟩
  have hcact : cact S w = .fin true ∨ cact S w = nextAct S w r := by
    rcases hc with hp | ⟨pr, hp, ho⟩
    · right; simp only [cact, h, hj, hp]; rfl
    · by_cases hX : (nodeAt S.es (pr.1, pr.2.1)).X = some false
      · left; simp only [cact, h, hj, hp, ho, hX]; rfl
      · right; simp only [cact, h, hj, hp, ho, hX]; rfl
  rcases hcact with hc | hc
  · exact Or.inl ⟨true, hc⟩
  · rw [hc]; exact hn

theorem finAt_some {E : NEnv T} {S : NS T} {t : ℕ} {e : T.Ed} {c ok : Bool} {r : CRec T}
    (h : cact S (T.own e c) = .fin ok) (hr : S.crec (T.own e c) = some r) (hJ : r.J = (e, c)) :
    ∃ room, finAt E S t e c = some (ok, room) :=
  ⟨E.room t e c 0, by simp [finAt, h, hr, hJ]⟩

theorem finAt_none {E : NEnv T} {S : NS T} {t : ℕ} {e : T.Ed} {c : Bool}
    (h : ∀ ok, cact S (T.own e c) ≠ .fin ok) : finAt E S t e c = none := by
  unfold finAt
  cases hc : cact S (T.own e c) with
  | fin ok => exact absurd hc (h ok)
  | _ => rfl

theorem offAt_probe {E : NEnv T} {S : NS T} {t : ℕ} {e : T.Ed} {c : Bool}
    (h : cact S (T.own e c) = .probe (e, c)) : offAt E S t e c = some true := by
  simp [offAt, h]

theorem offAt_idle {E : NEnv T} {S : NS T} {t : ℕ} {e : T.Ed} {c : Bool}
    (h : cact S (T.own e c) = .idle) (hr : (S.crec (T.own e c)).isSome) : offAt E S t e c = none := by
  simp only [offAt, h]
  cases hc : S.crec (T.own e c) with
  | none => rw [hc] at hr; simp at hr
  | some r => simp

/-! ### Facts of the transfer layer used here -/

theorem job_le_seqc {s : St} (H : Inv s) {c : Bool} {q : ℕ} {b : Bool}
    (h : (s.nd c).job = some (q, b)) : q ≤ (s.nd (!c)).seqc := by
  have D := (inv_iff s).1 H (!c)
  rw [Bool.not_not] at D
  exact D.not_fresh_le (D.jobEx q b h)

theorem req_le_seqc {s : St} (H : Inv s) {c : Bool} {q : ℕ} {pu : Bool} {g : ℕ}
    (h : Frame.req q pu g ∈ s.chan (!c)) : q ≤ (s.nd (!c)).seqc :=
  ((inv_iff s).1 H (!c)).req_le h

theorem slotO_inv {E : EnvO} {t : ℕ} {s : St} (H : Inv s) : Inv (slotO E t s) :=
  evsT_inv (evsT_inv H _) _

theorem slotO_seqc (E : EnvO) (t : ℕ) (s : St) (c : Bool) :
    (s.nd c).seqc ≤ ((slotO E t s).nd c).seqc :=
  (seqc_evsT _ _ c).trans (seqc_evsT _ _ c)

/-! ### Invariants of the network -/

/-- Every chain is recorded at its node, every record names an end of its node, every chain
serves a request with hops left. -/
def RecOK (S : NS T) : Prop :=
  (∀ x : T.Ed × Bool, (nodeAt S.es x).job ≠ none →
    ∃ r, S.crec (T.own x.1 x.2) = some r ∧ r.J = x) ∧
  (∀ w r, S.crec w = some r → T.own r.J.1 r.J.2 = w) ∧
  (∀ x q b, (nodeAt S.es x).job = some (q, b) → 1 ≤ S.ttl x.1 (!x.2) q)

theorem ttl_step (E : NEnv T) (S : NS T) (t : ℕ) {e : T.Ed} {c : Bool} {q : ℕ}
    (hq : q ≤ (nodeAt S.es (e, c)).seqc) : (ctlStep E S t).ttl e c q = S.ttl e c q := by
  simp only [ctlStep, ttlNext]
  rw [ite_eq_right_iff.2 (fun h => absurd h (by omega))]

/-- A chain that appears in a slot was started by the chain flag of its node. -/
theorem new_chain {E : NEnv T} {S : NS T} {t : ℕ} {x : T.Ed × Bool} {q : ℕ} {b : Bool}
    (h0 : (nodeAt S.es x).job = none)
    (h : (nodeAt (ctlStep E S t).es x).job = some (q, b)) :
    chainEnd S (T.own x.1 x.2) = some x ∧ ∃ pu g, Frame.req q pu g ∈ inChan S.es x := by
  obtain ⟨⟨k, hk⟩, hf⟩ := slotO_job_new (envAt_evict E S t x.1).misc h0 h
  refine ⟨?_, hf⟩
  simp only [envAt, Bool.not_not, decide_eq_true_eq] at hk
  exact hk

theorem chainEnd_spec {S : NS T} {w : T.W} {x : T.Ed × Bool} (h : chainEnd S w = some x) :
    S.crec w = none ∧ x ∈ T.ends w ∧ ttlOK S x = true := by
  unfold chainEnd at h
  cases hc : S.crec w with
  | some _ => rw [hc] at h; simp at h
  | none =>
    rw [hc] at h
    refine ⟨rfl, List.mem_of_find?_eq_some h, ?_⟩
    have := List.find?_some h
    simp only [Bool.and_eq_true] at this
    exact this.2

theorem recOK_step (E : NEnv T) {S : NS T} (t : ℕ) (HI : ∀ e, Inv (S.es e)) (H : RecOK S) :
    RecOK (ctlStep E S t) := by
  obtain ⟨H1, H2, H3⟩ := H
  refine ⟨?_, ?_, ?_⟩
  · intro x hx
    obtain ⟨⟨q, b⟩, hjb⟩ := Option.ne_none_iff_exists'.1 hx
    cases hj0 : (nodeAt S.es x).job with
    | none =>
      obtain ⟨hce, -⟩ := new_chain hj0 hjb
      have hcr := (chainEnd_spec hce).1
      refine ⟨⟨x, [], none⟩, ?_, rfl⟩
      simp only [ctlStep, recNext, hcr, hce]
      have : (nodeAt (fun e => slotO (envAt E S t e) t (S.es e)) x).job.isSome = true := by
        show (nodeAt (ctlStep E S t).es x).job.isSome = true
        rw [hjb]; rfl
      simp [this]
    | some jb =>
      obtain ⟨r, hr, hJ⟩ := H1 x (by rw [hj0]; simp)
      have hjr : (nodeAt S.es r.J).job.isNone = false := by rw [hJ, hj0]; rfl
      cases hca : cact S (T.own x.1 x.2) with
      | fin ok =>
        exfalso
        obtain ⟨room, hfa⟩ := finAt_some (E := E) (t := t) hca hr hJ
        have := slotO_job_fin (E := envAt E S t x.1) (t := t) (envAt_evict E S t x.1).misc
          (c := x.2) (q := jb.1) (b := jb.2) hfa (by rw [← hj0]; rfl)
        exact hx this
      | idle =>
        refine ⟨r, ?_, hJ⟩
        simp only [ctlStep, recNext, hr, hca, hjr]; rfl
      | probe y =>
        refine ⟨⟨r.J, y :: r.tried, some (y.1, y.2, (nodeAt S.es y).seqc + 1)⟩, ?_, hJ⟩
        simp only [ctlStep, recNext, hr, hca]
  · intro w r' h
    simp only [ctlStep, recNext] at h
    cases hc : S.crec w with
    | none =>
      rw [hc] at h; simp only at h
      cases hce : chainEnd S w with
      | none => rw [hce] at h; simp at h
      | some x =>
        rw [hce] at h; simp only at h
        split_ifs at h; cases h
        exact (T.hown w x.1 x.2).1 (chainEnd_spec hce).2.1
    | some r =>
      rw [hc] at h; simp only at h
      have := H2 w r hc
      cases hca : cact S w <;> rw [hca] at h <;> simp only at h
      all_goals (try split_ifs at h)
      all_goals (simp only [Option.some.injEq, reduceCtorEq] at h)
      all_goals (subst h; exact this)
  · intro x q b hjb
    have HIx := HI x.1
    cases hj0 : (nodeAt S.es x).job with
    | none =>
      obtain ⟨hce, pu, g, hm⟩ := new_chain hj0 hjb
      have hok := (chainEnd_spec hce).2.2
      simp only [ttlOK, List.all_eq_true] at hok
      have h1 := hok _ hm
      simp only [decide_eq_true_eq] at h1
      rw [ttl_step E S t (e := x.1) (c := !x.2) (req_le_seqc HIx hm)]
      exact h1
    | some jb =>
      obtain ⟨q', b'⟩ := jb
      cases hfa : finAt E S t x.1 x.2 with
      | some v =>
        exfalso
        have := slotO_job_fin (E := envAt E S t x.1) (t := t) (envAt_evict E S t x.1).misc
          (c := x.2) (q := q') (b := b') (ok := v.1) (room := v.2) hfa (by rw [← hj0]; rfl)
        have h' : (nodeAt (ctlStep E S t).es x).job = none := this
        rw [h'] at hjb; simp at hjb
      | none =>
        obtain ⟨b'', hb''⟩ := slotO_job_keep (E := envAt E S t x.1) (t := t) (envAt_evict E S t x.1).misc
          (c := x.2) (q := q') hfa ⟨b', by rw [← hj0]; rfl⟩
        have h' : (nodeAt (ctlStep E S t).es x).job = some (q', b'') := hb''
        rw [h'] at hjb; simp only [Option.some.injEq, Prod.mk.injEq] at hjb
        obtain ⟨rfl, -⟩ := hjb
        rw [ttl_step E S t (e := x.1) (c := !x.2) (job_le_seqc HIx (c := x.2) (by rw [← hj0]; rfl))]
        exact H3 x q' b' hj0

/-! ### The run of the network -/

/-- The start: every edge satisfies the invariant of the transfer layer, no chain runs. -/
structure CtlStart (S₀ : NS T) : Prop where
  inv : ∀ e, Inv (S₀.es e)
  nojob : ∀ x, (nodeAt S₀.es x).job = none
  norec : ∀ w, S₀.crec w = none

section Run

variable (E : NEnv T) (S₀ : NS T)

theorem run_inv (hS : CtlStart S₀) : ∀ t e, Inv ((netRunC E S₀ t).es e)
  | 0, e => hS.inv e
  | t + 1, e => slotO_inv (run_inv hS t e)

theorem run_rec (hS : CtlStart S₀) : ∀ t, RecOK (netRunC E S₀ t)
  | 0 => ⟨fun x h => absurd (hS.nojob x) h,
      fun w r h => by change S₀.crec w = some r at h; rw [hS.norec w] at h; simp at h,
      fun x q b h => by change (nodeAt S₀.es x).job = some (q, b) at h; rw [hS.nojob x] at h; simp at h⟩
  | t + 1 => recOK_step E t (run_inv E S₀ hS t) (run_rec hS t)

theorem seqc_run (t : ℕ) (x : T.Ed × Bool) : ∀ k,
    (nodeAt (netRunC E S₀ t).es x).seqc ≤ (nodeAt (netRunC E S₀ (t + k)).es x).seqc
  | 0 => le_rfl
  | k + 1 => (seqc_run t x k).trans (slotO_seqc _ _ _ _)

theorem ttl_run {t : ℕ} {e : T.Ed} {c : Bool} {q : ℕ}
    (h : q ≤ (nodeAt (netRunC E S₀ t).es (e, c)).seqc) :
    ∀ k, (netRunC E S₀ (t + k)).ttl e c q = (netRunC E S₀ t).ttl e c q
  | 0 => rfl
  | k + 1 => by
    show (ctlStep E (netRunC E S₀ (t + k)) (t + k)).ttl e c q = _
    rw [ttl_step E _ _ (h.trans (seqc_run E S₀ t (e, c) k)), ttl_run h k]

open Classical in
/-- The hop limit of request `q` of end `c` of `e`: fixed once the request is made. -/
noncomputable def ttlC (e : T.Ed) (c : Bool) (q : ℕ) : ℕ :=
  if h : ∃ t, q ≤ (nodeAt (netRunC E S₀ t).es (e, c)).seqc then
    (netRunC E S₀ (Nat.find h)).ttl e c q else 0

theorem ttlC_spec {t : ℕ} {e : T.Ed} {c : Bool} {q : ℕ}
    (h : q ≤ (nodeAt (netRunC E S₀ t).es (e, c)).seqc) :
    ttlC E S₀ e c q = (netRunC E S₀ t).ttl e c q := by
  classical
  have hex : ∃ t, q ≤ (nodeAt (netRunC E S₀ t).es (e, c)).seqc := ⟨t, h⟩
  unfold ttlC
  simp only [hex, ↓reduceDIte]
  obtain ⟨k, hk⟩ := Nat.exists_eq_add_of_le (Nat.find_min' hex h)
  rw [hk, ttl_run E S₀ (Nat.find_spec hex) k]

/-- The network as a `ChainNet`: each edge with the environment the controller gives it. -/
noncomputable def ctlNet (hS : CtlStart S₀) : ChainNet where
  Ed := T.Ed
  env := envOf E S₀
  init := S₀.es
  inv := hS.inv
  misc e := (envOf_evict E S₀ e).misc
  ttl e c p := ttlC E S₀ e c p.seq

theorem ctlNet_run (hS : CtlStart S₀) (e : T.Ed) (t : ℕ) :
    (ctlNet E S₀ hS).run e t = (netRunC E S₀ t).es e := (netRunC_proj E S₀ e t).symm

end Run

/-- The ends a chain may still probe. -/
def meas (w : T.W) (r : CRec T) : ℕ :=
  ((T.ends w).filter fun y => decide (y ≠ r.J) && decide (y ∉ r.tried)).length

theorem meas_lt {w : T.W} {J x : T.Ed × Bool} {tried : List (T.Ed × Bool)} {pr pr'}
    (hx : x ∈ T.ends w) (hJ : x ≠ J) (ht : x ∉ tried) :
    meas w ⟨J, x :: tried, pr'⟩ < meas w ⟨J, tried, pr⟩ := by
  unfold meas
  have : ((T.ends w).filter fun y => decide (y ≠ J) && decide (y ∉ x :: tried)) =
      ((T.ends w).filter fun y => decide (y ≠ J) && decide (y ∉ tried)).filter
        fun y => decide (y ≠ x) := by
    rw [List.filter_filter]
    apply List.filter_congr
    intro y _
    by_cases h1 : y = x <;> by_cases h2 : y = J <;> by_cases h3 : y ∈ tried <;> simp_all
  rw [this]
  apply List.length_filter_lt_length_iff_exists.2
  exact ⟨x, List.mem_filter.2 ⟨hx, by simp [hJ, ht]⟩, by simp⟩

theorem meas_le (w : T.W) (r : CRec T) (hJ : r.J ∈ T.ends w) : meas w r + 1 ≤ (T.ends w).length := by
  unfold meas
  have : ((T.ends w).filter fun y => decide (y ≠ r.J) && decide (y ∉ r.tried)).length <
      (T.ends w).length := List.length_filter_lt_length_iff_exists.2 ⟨r.J, hJ, by simp⟩
  omega

theorem eligible_spec {es : T.Ed → St} {x : T.Ed × Bool} (h : eligible es x = true) :
    ((nodeAt es x).X = some true ∨ ((nodeAt es x).X = none ∧ (nodeAt es x).dflt = true)) ∧
      (nodeAt es x).job = none ∧ (nodeAt es x).pend = [] ∧ inChan es x = [] := by
  simp only [eligible, offerable, Bool.and_eq_true, Bool.or_eq_true, decide_eq_true_eq,
    Option.isNone_iff_eq_none, List.isEmpty_iff] at h
  exact ⟨h.1.1.1, h.1.1.2, h.1.2, h.2⟩

section Serve

variable (E : NEnv T) (S₀ : NS T) (hS : CtlStart S₀)

/-- **The controller follows the service discipline.** A chain of `w` at a decision point (its
probe closed, or none yet) is served by a list of probes, one per end it may still probe, that
satisfies `SeqOK`. -/
theorem serve (p : Pend) (w : T.W) : ∀ n u (r : CRec T), meas w r < n →
    (netRunC E S₀ u).crec w = some r →
    (∃ b, (nodeAt (netRunC E S₀ u).es r.J).job = some (p.seq, b)) →
    (r.probe = none ∨ ∃ pr, r.probe = some pr ∧
      (nodeAt (netRunC E S₀ u).es (pr.1, pr.2.1)).pend.any
        (fun p' => decide (p'.seq = pr.2.2)) = false) →
    ∃ probes : List (ctlNet E S₀ hS).Probe, probes.length ≤ meas w r ∧
      (ctlNet E S₀ hS).SeqOK r.J.1 (!r.J.2) p u probes := by
  intro n
  induction n with
  | zero => intro u r hm; omega
  | succ n ih =>
    intro u r hm hr hj hc
    have HR := run_rec E S₀ hS u
    have HI := run_inv E S₀ hS u
    obtain ⟨b, hjb⟩ := hj
    have hjr : (nodeAt (netRunC E S₀ u).es r.J).job.isNone = false := by rw [hjb]; rfl
    have hown : T.own r.J.1 r.J.2 = w := HR.2.1 w r hr
    rcases cact_dec hr hjr hc with ⟨ok, hca⟩ | ⟨x, hca, hx⟩
    · -- the chain ends in this slot
      refine ⟨[], by simp, ?_⟩
      obtain ⟨room, hfa⟩ := finAt_some (E := E) (t := u) (e := r.J.1) (c := r.J.2)
        (by rw [hown]; exact hca) (by rw [hown]; exact hr) rfl
      have h0 := slotO_job_fin (E := envAt E (netRunC E S₀ u) u r.J.1) (t := u)
        (envAt_evict E _ u r.J.1).misc (c := r.J.2) hfa hjb
      show ¬ HJob ((ctlNet E S₀ hS).run r.J.1 (u + 1)) (!r.J.2) p
      rw [ctlNet_run]
      rintro ⟨b', hb'⟩
      rw [Bool.not_not] at hb'
      have : (((netRunC E S₀ (u + 1)).es r.J.1).nd r.J.2).job = none := h0
      rw [this] at hb'; simp at hb'
    · -- the chain probes `x`
      obtain ⟨hxe, hxJ, hxt, hxel⟩ := mem_cands.1 hx
      have hownx : T.own x.1 x.2 = w := (T.hown w x.1 x.2).1 hxe
      obtain ⟨hX, hxj, hxp, hxc⟩ := eligible_spec hxel
      have hcax : cact (netRunC E S₀ u) (T.own x.1 x.2) = .probe (x.1, x.2) := by
        rw [hownx]; exact hca
      have hoff := offAt_probe (E := E) (t := u) hcax
      have hfx : finAt E (netRunC E S₀ u) u x.1 x.2 = none :=
        finAt_none (by rw [hcax]; intro ok h; cases h)
      obtain ⟨hpend1, hseqc1⟩ := slotO_offer (E := envAt E (netRunC E S₀ u) u x.1) (t := u)
        (envAt_evict E _ u x.1) hX hxj hxp hxc hfx hoff
      have hfJ : finAt E (netRunC E S₀ u) u r.J.1 r.J.2 = none :=
        finAt_none (by rw [hown, hca]; intro ok h; cases h)
      obtain ⟨b1, hjb1⟩ := slotO_job_keep (E := envAt E (netRunC E S₀ u) u r.J.1) (t := u)
        (envAt_evict E _ u r.J.1).misc hfJ ⟨b, hjb⟩
      let q' := (nodeAt (netRunC E S₀ u).es x).seqc + 1
      let p' : Pend := ⟨q', true, (nodeAt (netRunC E S₀ u).es x).takes,
        (nodeAt (netRunC E S₀ u).es x).gen⟩
      let r' : CRec T := ⟨r.J, x :: r.tried, some (x.1, x.2, q')⟩
      have hr1 : (netRunC E S₀ (u + 1)).crec w = some r' := by
        show recNext (netRunC E S₀ u) _ w = some r'
        simp only [recNext, hr, hca]; rfl
      -- the hop limits
      have hseqJ : p.seq ≤ (nodeAt (netRunC E S₀ u).es (r.J.1, !r.J.2)).seqc :=
        job_le_seqc (HI r.J.1) (c := r.J.2) hjb
      have httlJ : (ctlNet E S₀ hS).ttl r.J.1 (!r.J.2) p =
          (netRunC E S₀ u).ttl r.J.1 (!r.J.2) p.seq := ttlC_spec E S₀ hseqJ
      have hone := HR.2.2 r.J p.seq b hjb
      have httlx : (ctlNet E S₀ hS).ttl x.1 x.2 p' =
          (netRunC E S₀ u).ttl r.J.1 (!r.J.2) p.seq - 1 := by
        refine (ttlC_spec E S₀ (t := u + 1) (e := x.1) (c := x.2) (q := q')
          (le_of_eq hseqc1.symm)).trans ?_
        show ttlNext E (netRunC E S₀ u) u x.1 x.2 q' = _
        unfold ttlNext
        rw [ite_eq_left rfl, hoff]
        simp only [hcax]
        unfold jobTtl
        rw [hownx, hr]
        simp only [hjb]
      have hlt : meas w r' < meas w r := meas_lt hxe hxJ hxt
      have hp1 : ((netRunC E S₀ (u + 1)).es x.1).nd x.2 = _ := rfl
      have hpend1' : (((netRunC E S₀ (u + 1)).es x.1).nd x.2).pend = [p'] := hpend1
      -- the probe is open until it first closes
      classical
      by_cases hex : ∃ c, u + 1 ≤ c ∧ (((ctlNet E S₀ hS).run x.1 c).nd x.2).pend ≠ [p']
      · let c := Nat.find hex
        have hcs : u + 1 ≤ c ∧ (((ctlNet E S₀ hS).run x.1 c).nd x.2).pend ≠ [p'] := Nat.find_spec hex
        rw [ctlNet_run] at hcs
        have hmin : ∀ t, u + 1 ≤ t → t < c → (((netRunC E S₀ t).es x.1).nd x.2).pend = [p'] := by
          intro t h1 h2
          by_contra h3
          exact Nat.find_min hex h2 ⟨h1, by rw [ctlNet_run]; exact h3⟩
        have hopen : ∀ t, u + 1 ≤ t → t < c → (netRunC E S₀ t).crec w = some r' →
            (∃ b, (nodeAt (netRunC E S₀ t).es r.J).job = some (p.seq, b)) →
            cact (netRunC E S₀ t) w = .idle := by
          intro t h1 h2 hrt ⟨bt, hjt⟩
          refine cact_open hrt (by rw [hjt]; rfl) rfl ?_
          show ((((netRunC E S₀ t).es x.1).nd x.2).pend.any fun p'' => decide (p''.seq = q')) = true
          rw [hmin t h1 h2]; simp [p']
        have K : ∀ k, u + 1 + k ≤ c → (netRunC E S₀ (u + 1 + k)).crec w = some r' ∧
            ∃ b, (nodeAt (netRunC E S₀ (u + 1 + k)).es r.J).job = some (p.seq, b) := by
          intro k
          induction k with
          | zero => intro _; exact ⟨hr1, b1, hjb1⟩
          | succ k ihk =>
            intro hk
            obtain ⟨hrk, bk, hjk⟩ := ihk (by omega)
            have hcak := hopen (u + 1 + k) (by omega) (by omega) hrk ⟨bk, hjk⟩
            have hjrk : (nodeAt (netRunC E S₀ (u + 1 + k)).es r'.J).job.isNone = false := by
              show (nodeAt (netRunC E S₀ (u + 1 + k)).es r.J).job.isNone = false
              rw [hjk]; rfl
            refine ⟨?_, ?_⟩
            · show recNext (netRunC E S₀ (u + 1 + k)) _ w = some r'
              simp only [recNext, hrk, hcak, hjrk]; rfl
            · have hfk : finAt E (netRunC E S₀ (u + 1 + k)) (u + 1 + k) r.J.1 r.J.2 = none :=
                finAt_none (by rw [hown, hcak]; intro ok h; cases h)
              exact slotO_job_keep (E := envAt E (netRunC E S₀ (u + 1 + k)) (u + 1 + k) r.J.1)
                (t := u + 1 + k) (envAt_evict E _ _ r.J.1).misc hfk ⟨bk, hjk⟩
        have hc2 : u + 2 ≤ c := by
          by_contra h
          have hc1 : c = u + 1 := by omega
          exact hcs.2 (by rw [hc1]; exact hpend1')
        have Kc : ∀ t, u + 1 ≤ t → t ≤ c → (netRunC E S₀ t).crec w = some r' ∧
            ∃ b, (nodeAt (netRunC E S₀ t).es r.J).job = some (p.seq, b) := by
          intro t h1 h2
          have := K (t - (u + 1)) (by omega)
          rwa [show u + 1 + (t - (u + 1)) = t by omega] at this
        obtain ⟨hrc1, bc1, hjc1⟩ := Kc (c - 1) (by omega) (by omega)
        have hpc1 := hmin (c - 1) (by omega) (by omega)
        have hcac1 := hopen (c - 1) (by omega) (by omega) hrc1 ⟨bc1, hjc1⟩
        have hoffc1 : offAt E (netRunC E S₀ (c - 1)) (c - 1) x.1 x.2 = none :=
          offAt_idle (by rw [hownx]; exact hcac1) (by rw [hownx, hrc1]; rfl)
        have hps := slotO_psub (E := envAt E (netRunC E S₀ (c - 1)) (c - 1) x.1) (t := c - 1)
          (envAt_evict E _ _ x.1).misc (Or.inl hpc1) hoffc1
        have hRc : netRunC E S₀ c = ctlStep E (netRunC E S₀ (c - 1)) (c - 1) := by
          obtain ⟨m, hm⟩ : ∃ m, c = m + 1 := ⟨c - 1, by omega⟩
          rw [hm]; rfl
        have hpc : (((netRunC E S₀ c).es x.1).nd x.2).pend = [] := by
          rw [hRc]
          rcases hps with h | h
          · exact absurd (by rw [hRc]; exact h) hcs.2
          · exact h
        obtain ⟨hrc, bc, hjc⟩ := Kc c (by omega) le_rfl
        obtain ⟨rest, hlen, hseq⟩ := ih c r' (by omega) hrc ⟨bc, hjc⟩
          (Or.inr ⟨_, rfl, by
            show ((((netRunC E S₀ c).es x.1).nd x.2).pend.any fun p'' => decide (p''.seq = q')) = false
            rw [hpc]; rfl⟩)
        refine ⟨⟨x.1, x.2, p', u + 1⟩ :: rest, by simp; omega, ?_⟩
        refine ⟨Nat.le_succ u, le_rfl, by rw [ctlNet_run]; exact hpend1', by rw [httlx, httlJ]; omega, ?_⟩
        intro c' h1 h2 h3
        have hcc : c' = c := by
          apply le_antisymm
          · by_contra hlt
            rw [not_le] at hlt
            exact hcs.2 (by have := h3 c hcs.1 hlt; rwa [ctlNet_run] at this)
          · exact Nat.find_min' hex ⟨h1, h2⟩
        rw [hcc]; exact hseq
      · refine ⟨[⟨x.1, x.2, p', u + 1⟩], by simp; omega, ?_⟩
        refine ⟨Nat.le_succ u, le_rfl, by rw [ctlNet_run]; exact hpend1', by rw [httlx, httlJ]; omega, ?_⟩
        intro c' h1 h2 _
        exact absurd ⟨c', h1, h2⟩ hex

/-- **Every chain of the controller follows the service discipline `SeqOK`**, with at most one
probe per other end of its node, from the slot at which it first runs. -/
theorem ctl_seqOK {Δ : ℕ} (hΔ : ∀ w, (T.ends w).length ≤ Δ) :
    ∀ (e : T.Ed) i p v, HJob ((ctlNet E S₀ hS).run e v) i p → ∃ s, s ≤ v ∧
      HJob ((ctlNet E S₀ hS).run e s) i p ∧ ∃ probes : List (ctlNet E S₀ hS).Probe,
        probes.length + 1 ≤ Δ ∧ (ctlNet E S₀ hS).SeqOK e i p s probes := by
  intro e i p v hv
  rw [ctlNet_run E S₀ hS e v] at hv
  classical
  have hex : ∃ t, HJob ((netRunC E S₀ t).es e) i p := ⟨v, hv⟩
  have hs1 := Nat.find_spec hex
  have hle : Nat.find hex ≤ v := Nat.find_min' hex hv
  have hpos : Nat.find hex ≠ 0 := by
    intro h0
    rw [h0] at hs1
    obtain ⟨b, hb⟩ := hs1
    have := hS.nojob (e, !i)
    change ((S₀.es e).nd (!i)).job = none at this
    change ((S₀.es e).nd (!i)).job = some (p.seq, b) at hb
    rw [this] at hb; simp at hb
  obtain ⟨s0, hs0⟩ : ∃ s0, Nat.find hex = s0 + 1 := ⟨Nat.find hex - 1, by omega⟩
  have hn0 : ¬ HJob ((netRunC E S₀ s0).es e) i p := Nat.find_min hex (by omega)
  rw [hs0] at hs1
  obtain ⟨b1, hb1⟩ := hs1
  have hjob1 : (nodeAt (ctlStep E (netRunC E S₀ s0) s0).es (e, !i)).job = some (p.seq, b1) := hb1
  have h0 : (nodeAt (netRunC E S₀ s0).es (e, !i)).job = none := by
    cases hj : (nodeAt (netRunC E S₀ s0).es (e, !i)).job with
    | none => rfl
    | some jb =>
      exfalso
      obtain ⟨q', b'⟩ := jb
      cases hfa : finAt E (netRunC E S₀ s0) s0 e (!i) with
      | some vv =>
        have := slotO_job_fin (E := envAt E (netRunC E S₀ s0) s0 e) (t := s0)
          (envAt_evict E _ _ e).misc (c := !i) (q := q') (b := b') (ok := vv.1) (room := vv.2) hfa hj
        have h' : (nodeAt (ctlStep E (netRunC E S₀ s0) s0).es (e, !i)).job = none := this
        rw [h'] at hjob1; simp at hjob1
      | none =>
        obtain ⟨b'', hb''⟩ := slotO_job_keep (E := envAt E (netRunC E S₀ s0) s0 e) (t := s0)
          (envAt_evict E _ _ e).misc (c := !i) (q := q') hfa ⟨b', hj⟩
        have h' : (nodeAt (ctlStep E (netRunC E S₀ s0) s0).es (e, !i)).job = some (q', b'') := hb''
        rw [h'] at hjob1; simp only [Option.some.injEq, Prod.mk.injEq] at hjob1
        obtain ⟨rfl, -⟩ := hjob1
        exact hn0 ⟨b', hj⟩
  obtain ⟨hce, -⟩ := new_chain h0 hjob1
  obtain ⟨hcr0, hxe, -⟩ := chainEnd_spec hce
  let r : CRec T := ⟨(e, !i), [], none⟩
  have hr1 : (netRunC E S₀ (s0 + 1)).crec (T.own e (!i)) = some r := by
    show recNext (netRunC E S₀ s0) _ (T.own e (!i)) = some r
    have : (nodeAt (fun e' => slotO (envAt E (netRunC E S₀ s0) s0 e') s0 ((netRunC E S₀ s0).es e'))
        (e, !i)).job.isSome = true := by
      show (nodeAt (ctlStep E (netRunC E S₀ s0) s0).es (e, !i)).job.isSome = true
      rw [hjob1]; rfl
    simp only [recNext, hcr0, hce, this]; rfl
  obtain ⟨probes, hlen, hseq⟩ := serve E S₀ hS p (T.own e (!i)) (meas (T.own e (!i)) r + 1)
    (s0 + 1) r (by omega) hr1 ⟨b1, hjob1⟩ (Or.inl rfl)
  refine ⟨s0 + 1, by omega, by rw [ctlNet_run E S₀ hS e]; exact ⟨b1, hb1⟩, probes, ?_, ?_⟩
  · have := meas_le (T.own e (!i)) r hxe
    have := hΔ (T.own e (!i))
    omega
  · simpa [r] using hseq

/-- No chain serves a request without hops left. -/
theorem ctl_base : ∀ (e : T.Ed) i p v, HJob ((ctlNet E S₀ hS).run e v) i p →
    1 ≤ (ctlNet E S₀ hS).ttl e i p := by
  intro e i p v hv
  rw [ctlNet_run E S₀ hS e v] at hv
  obtain ⟨b, hb⟩ := hv
  have hb' : (nodeAt (netRunC E S₀ v).es (e, !i)).job = some (p.seq, b) := hb
  have h1 := (run_rec E S₀ hS v).2.2 (e, !i) p.seq b hb'
  have hle := job_le_seqc (run_inv E S₀ hS v e) (c := !i) hb
  simp only [Bool.not_not] at h1 hle
  show 1 ≤ ttlC E S₀ e i p.seq
  rw [ttlC_spec E S₀ (t := v) (e := e) (c := i) hle]
  exact h1

include hS in
/-- **Push chains of the controller end within `dBound Δ Tr t` slots.** In the network run by the
controller, from a start without chains, with every timer firing at least once in every `Tr` slots
and every node of degree at most `Δ`, every chain that serves a request of hop limit at most `t`
is gone within `dBound Δ Tr t` slots of any slot at which it runs. -/
theorem ctl_chain_bound {Δ Tr : ℕ} (hΔ : ∀ w, (T.ends w).length ≤ Δ)
    (hRx : ∀ e c u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v e c = true) :
    ∀ t e i p v, ttlC E S₀ e i p.seq ≤ t → HJob ((netRunC E S₀ v).es e) i p →
      ∃ w, v ≤ w ∧ w ≤ v + ChainNet.dBound Δ Tr t ∧ ¬ HJob ((netRunC E S₀ w).es e) i p := by
  intro t e i p v ht hv
  obtain ⟨w, h1, h2, h3⟩ := (ctlNet E S₀ hS).chain_bound (fun e c u => hRx e c u)
    (ctl_base E S₀ hS) (ctl_seqOK E S₀ hS hΔ) t e i p v ht (by rw [ctlNet_run E S₀ hS e v]; exact hv)
  exact ⟨w, h1, h2, by rwa [ctlNet_run E S₀ hS e w] at h3⟩

end Serve




end SwarmInfer.CoverWeave.ExecFull.R2pp
