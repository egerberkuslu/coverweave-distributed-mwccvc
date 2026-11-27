import SwarmInferLean.CoverWeave.ExecFullTransferInv

/-!
# CoverWeave, Lemma 4 (`lem:lossless`, inventory C9): the transfer layer cannot get stuck

Source: `CoverWeave_R1/sections/04-formaleng.tex:127-137`, the proof of Lemma `lem:lossless`, third
paragraph ("requests are answered within a timeout"), for the transfer layer of one flexible edge
under the repairs of `ExecFullTransferRepair.lean`.

`quiet_reachable`: from every reachable configuration of the repaired model there is a loss-free
continuation of at most `Wt s + 12` events, without offers or budget changes, that ends quiet.
This is the existential (no deadlock) form of the transfer part of Lemma 4. It is not Lemma 4:
the lemma quantifies over every loss-free run of `W` synchronous slots of the whole protocol, and
the bound on how often overload produces new offers (the potential `(Γ, Θ)` of its proof) and the
duration of push chains belong to the parts of the protocol this one-edge model leaves to the
environment.
-/

namespace SwarmInfer.CoverWeave.ExecFull

/-! ### Structure of the handlers -/

theorem runEvs_append (P : Params) (s : St) (es es' : List Ev) :
    runEvs P s (es ++ es') = (runEvs P s es).bind fun t => runEvs P t es' := by
  induction es generalizing s with
  | nil => simp [runEvs]
  | cons e es ih =>
    simp only [List.cons_append, runEvs]
    cases step P s e <;> simp [ih]

@[simp] theorem repeated_job (n : Node) (q : ℕ) : (repeated n q).1.job = n.job := by
  unfold repeated; split <;> (try split) <;> rfl
@[simp] theorem repeated_pend (n : Node) (q : ℕ) : (repeated n q).1.pend = n.pend := by
  unfold repeated; split <;> (try split) <;> rfl
@[simp] theorem accept_job (P : Params) (n : Node) (room : Bool) : (accept P n room).1.job = n.job := by
  unfold accept; split_ifs <;> rfl
@[simp] theorem accept_pend (P : Params) (n : Node) (room : Bool) :
    (accept P n room).1.pend = n.pend := by
  unfold accept; split_ifs <;> rfl
@[simp] theorem cachePut_job (n : Node) (q : ℕ) (r : Rep) : (cachePut n q r).job = n.job := rfl
@[simp] theorem cachePut_pend (n : Node) (q : ℕ) (r : Rep) : (cachePut n q r).pend = n.pend := rfl

theorem reply_nd_not (s : St) (j : Bool) (n : Node) (q : ℕ) (r : Rep) :
    (reply s j n q r).nd (!j) = s.nd (!j) := by
  unfold reply; split <;> simp
theorem reply_chan_not (s : St) (j : Bool) (n : Node) (q : ℕ) (r : Rep) :
    (reply s j n q r).chan (!j) = s.chan (!j) := by
  unfold reply; split <;> simp

/-- What a delivered request does to the configuration when the receiver serves no chain and
starts none: one answer on its channel, nothing else visible here changes. -/
def Good (s1 : St) (j : Bool) (q : ℕ) (t : St) : Prop :=
  t.nd (!j) = s1.nd (!j) ∧ t.chan (!j) = s1.chan (!j) ∧ (∃ r, t.chan j = s1.chan j ++ [.rep q r]) ∧
    (t.nd j).job = none ∧ (t.nd j).pend = (s1.nd j).pend

theorem good_reply {s1 : St} {j : Bool} {q : ℕ} {n : Node} {r : Rep} (hj : n.job = none)
    (hp : n.pend = (s1.nd j).pend) : Good s1 j q (reply s1 j n q r) :=
  ⟨reply_nd_not .., reply_chan_not .., ⟨r, reply_chan_self ..⟩, by rw [reply_nd_self]; simpa using hj,
    by rw [reply_nd_self]; simpa using hp⟩

theorem onReq_good (P : Params) (s1 : St) (j : Bool) (q : ℕ) (pu : Bool) (g : ℕ) (room : Bool)
    (hj : (s1.nd j).job = none) : Good s1 j q (onReq P s1 j q pu g room false) := by
  unfold onReq
  cases hl : (s1.nd j).cache.lookup q with
  | some r =>
    simp only [hl]
    exact ⟨by simp, by simp, ⟨r, by simp⟩, by simpa using hj, by simp⟩
  | none =>
    simp only [hl]
    cases pu
    · simp only [Bool.not_false, ite_true]
      split_ifs <;> exact good_reply (by simp [hj]) (by simp)
    · simp only [hj, Bool.not_true, Bool.false_eq_true, ite_false, Bool.not_false, Bool.true_and,
        Bool.and_false]
      split_ifs <;> first
        | exact good_reply (by simp [hj]) (by simp)
        | (simp only [accept_job, repeated_job, hj]; exact good_reply (by simp [hj]) (by simp))


theorem onRep_view (P : Params) (s1 : St) (i : Bool) (q : ℕ) (r : Rep) :
    (onRep P s1 i q r).nd (!i) = s1.nd (!i) ∧ (onRep P s1 i q r).chan (!i) = s1.chan (!i) ∧
      ((onRep P s1 i q r).chan i = s1.chan i ∨ (onRep P s1 i q r).chan i = s1.chan i ++ [.conf q]) ∧
      ((onRep P s1 i q r).nd i).job = (s1.nd i).job := by
  unfold onRep
  cases r.ok <;> cases r.late <;> simp only [Bool.false_and, Bool.true_and,
    Bool.false_eq_true, ite_false, ite_true] <;>
    refine ⟨by simp, by simp, by simp, ?_⟩ <;> simp only [St.send_eq, St.nd_setChan,
      St.nd_setNd_self] <;> split <;> (try split_ifs) <;> simp [release]

theorem onRep_closes (P : Params) (s1 : St) (i : Bool) {p : Pend} (r : Rep)
    (hp : (s1.nd i).pend = [p]) : ((onRep P s1 i p.seq r).nd i).pend = [] := by
  unfold onRep
  have hf : (s1.nd i).pend.find? (·.seq = p.seq) = some p := by simp [hp]
  cases r.ok <;> cases r.late <;> simp [hp] <;> split_ifs <;> simp [release]

theorem onConf_view (s1 : St) (i : Bool) (q : ℕ) :
    (onConf s1 i q).nd (!i) = s1.nd (!i) ∧ (∀ k, (onConf s1 i q).chan k = s1.chan k) ∧
      ((onConf s1 i q).nd i).job = (s1.nd i).job ∧ ((onConf s1 i q).nd i).pend = (s1.nd i).pend := by
  unfold onConf; simp


theorem onRep_chan_nolate (P : Params) (s1 : St) (i : Bool) (q : ℕ) (r : Rep) (hl : r.late = false) :
    (onRep P s1 i q r).chan i = s1.chan i := by
  unfold onRep; cases r.ok <;> simp [hl]

theorem onRep_pend_nil (P : Params) (s1 : St) (i : Bool) (q : ℕ) (r : Rep)
    (hp : (s1.nd i).pend = []) : ((onRep P s1 i q r).nd i).pend = [] := by
  unfold onRep
  cases r.ok <;> cases r.late <;> simp [hp] <;> split_ifs <;> simp [release, hp]

/-! ### A loss-free continuation to a quiet configuration -/

/-- Weights of frames: a request costs its delivery and the delivery of its answer. -/
def wt : Frame → ℕ
  | .req _ _ _ => 3
  | .rep _ _ => 2
  | .conf _ => 1

/-- The weight of what is in flight. -/
def Wt (s : St) : ℕ := (s.fromA.map wt).sum + (s.fromB.map wt).sum

theorem Wt_eq (s : St) (i : Bool) : Wt s = ((s.chan i).map wt).sum + ((s.chan !i).map wt).sum := by
  cases i <;> simp [Wt, St.chan, Nat.add_comm]

/-- No push chain runs and the given ends have no open request. -/
def Calm (s : St) : Prop := ∀ k, (s.nd k).job = none

theorem deliver_step {s : St} {i : Bool} {f : Frame} {l : List Frame} (hj : Calm s)
    (hc : s.chan i = f :: l) :
    ∃ t, step repairParams s (.deliver i false false) = some t ∧ Wt t < Wt s ∧ Calm t ∧
      (∀ k, (s.nd k).pend = [] → (t.nd k).pend = []) := by
  have hW := Wt_eq s i
  rw [hc] at hW
  simp only [List.map_cons, List.sum_cons] at hW
  cases f with
  | req q pu g =>
    have hG := onReq_good repairParams (s.setChan i l) (!i) q pu g false (by simpa using hj (!i))
    obtain ⟨h1, h2, ⟨r, h3⟩, h4, h5⟩ := hG
    rw [Bool.not_not] at h1 h2
    refine ⟨onReq repairParams (s.setChan i l) (!i) q pu g false false, by simp [step, hc], ?_, ?_, ?_⟩
    · rw [Wt_eq _ i, h2, h3]; simp [wt] at hW ⊢; omega
    · intro k; have ha := hj false; have hb := hj true; cases k <;> cases i <;> simp_all
    · intro k hk; cases k <;> cases i <;> simp_all
  | rep q r =>
    obtain ⟨h1, h2, h3, h4⟩ := onRep_view repairParams (s.setChan i l) (!i) q r
    rw [Bool.not_not] at h1 h2
    refine ⟨onRep repairParams (s.setChan i l) (!i) q r, by simp [step, hc], ?_, ?_, ?_⟩
    · rw [Wt_eq _ i, h2]
      rcases h3 with h3 | h3 <;> rw [h3] <;> simp [wt] at hW ⊢ <;> omega
    · intro k; have ha := hj false; have hb := hj true; cases k <;> cases i <;> simp_all
    · intro k hk
      have := onRep_pend_nil repairParams (s.setChan i l) (!i) q r
      cases k <;> cases i <;> simp_all
  | conf q =>
    obtain ⟨h1, h2, h3, h4⟩ := onConf_view (s.setChan i l) (!i) q
    rw [Bool.not_not] at h1
    refine ⟨onConf (s.setChan i l) (!i) q, by simp [step, hc], ?_, ?_, ?_⟩
    · rw [Wt_eq _ i, h2 i, h2 (!i)]; simp [wt] at hW ⊢; omega
    · intro k; have ha := hj false; have hb := hj true; cases k <;> cases i <;> simp_all
    · intro k hk; cases k <;> cases i <;> simp_all

/-- Delivering everything in flight, with no new chain, empties both channels. -/
theorem drain (n : ℕ) : ∀ s : St, Wt s ≤ n → Inv s → Calm s →
    ∃ es t, runEvs repairParams s es = some t ∧ es.length ≤ Wt s ∧ t.fromA = [] ∧ t.fromB = [] ∧
      Calm t ∧ Inv t ∧ (∀ k, (s.nd k).pend = [] → (t.nd k).pend = []) ∧
      ∀ e ∈ es, ∃ i, e = .deliver i false false := by
  induction n with
  | zero =>
    intro s hs H hj
    refine ⟨[], s, rfl, by simp, ?_, ?_, hj, H, fun _ h => h, by simp⟩ <;>
    · by_contra h
      obtain ⟨f, l, hfl⟩ := List.exists_cons_of_ne_nil h
      simp [Wt, hfl] at hs
      cases f <;> simp [wt] at hs
  | succ n ih =>
    intro s hs H hj
    by_cases he : s.fromA = [] ∧ s.fromB = []
    · exact ⟨[], s, rfl, by simp, he.1, he.2, hj, H, fun _ h => h, by simp⟩
    · have : ∃ i f l, s.chan i = f :: l := by
        by_cases ha : s.fromA = []
        · obtain ⟨f, l, h⟩ := List.exists_cons_of_ne_nil (fun h => he ⟨ha, h⟩)
          exact ⟨true, f, l, h⟩
        · obtain ⟨f, l, h⟩ := List.exists_cons_of_ne_nil ha
          exact ⟨false, f, l, h⟩
      obtain ⟨i, f, l, hc⟩ := this
      obtain ⟨t, ht, hlt, hjt, hpt⟩ := deliver_step hj hc
      obtain ⟨es, u, hu, hlen, h1, h2, h3, h4, h5, h6⟩ :=
        ih t (by omega) (step_pres H ht) hjt
      refine ⟨.deliver i false false :: es, u, by simp [runEvs, ht, hu], by simp; omega, h1, h2, h3,
        h4, fun k hk => h5 k (hpt k hk), ?_⟩
      intro e he'
      simp only [List.mem_cons] at he'
      rcases he' with rfl | he'
      · exact ⟨i, rfl⟩
      · exact h6 e he'


/-- The events of a loss-free continuation without new offers or budget changes: deliveries
that start no chain, retransmissions, and chains that end. -/
def Prog : Ev → Prop
  | .deliver _ room chain => room = false ∧ chain = false
  | .retx _ _ => True
  | .finish _ ok room => ok = false ∧ room = false
  | _ => False

theorem finish_view {s : St} {i : Bool} {q : ℕ} {b : Bool} (hj : (s.nd i).job = some (q, b)) :
    ∃ t, finishJob repairParams s i false false = some t ∧ (t.nd i).job = none ∧
      t.nd (!i) = s.nd (!i) ∧ t.chan (!i) = s.chan (!i) ∧ (∃ r, t.chan i = s.chan i ++ [.rep q r]) ∧
      (t.nd i).pend = (s.nd i).pend := by
  unfold finishJob
  simp only [hj, Bool.false_eq_true, ite_false, Bool.false_or, Bool.false_and,
    repairParams_finalBusy, repairParams_finalNack, Bool.not_false, Bool.and_true]
  split_ifs
  · exact ⟨_, rfl, by rw [reply_nd_self]; rfl, reply_nd_not .., reply_chan_not ..,
      ⟨_, reply_chan_self ..⟩, by rw [reply_nd_self]; rfl⟩
  · exact ⟨_, rfl, by rw [reply_nd_self]; rfl, reply_nd_not .., reply_chan_not ..,
      ⟨_, reply_chan_self ..⟩, by rw [reply_nd_self]; rfl⟩

/-- End the push chain at `i`, if one runs. -/
theorem finish_one (s : St) (i : Bool) (H : Inv s) :
    ∃ es t, runEvs repairParams s es = some t ∧ es.length ≤ 1 ∧ (t.nd i).job = none ∧
      t.nd (!i) = s.nd (!i) ∧ (t.nd i).pend = (s.nd i).pend ∧ Wt t ≤ Wt s + 2 ∧ Inv t ∧
      ∀ e ∈ es, Prog e := by
  cases hj : (s.nd i).job with
  | none => exact ⟨[], s, rfl, by simp, hj, rfl, rfl, by omega, H, by simp⟩
  | some jb =>
    obtain ⟨q, b⟩ := jb
    obtain ⟨t, ht, h1, h2, h3, ⟨r, h4⟩, h5⟩ := finish_view hj
    have hst : step repairParams s (.finish i false false) = some t := ht
    refine ⟨[.finish i false false], t, by simp [runEvs, hst], by simp, h1, h2, h5, ?_,
      step_pres H hst, by simp [Prog]⟩
    rw [Wt_eq t i, Wt_eq s i, h3, h4]; simp [wt]; omega

/-- With nothing in flight and no chain, an open request of `i` is retransmitted, answered and
closed in three events. -/
theorem round (s : St) (i : Bool) (H : Inv s) (hj : Calm s) (he : ∀ k, s.chan k = []) :
    ∃ es t, runEvs repairParams s es = some t ∧ es.length ≤ 3 ∧ (∀ k, t.chan k = []) ∧ Calm t ∧
      Inv t ∧ (t.nd i).pend = [] ∧ (t.nd !i).pend = (s.nd !i).pend ∧ ∀ e ∈ es, Prog e := by
  have Hi := (inv_iff s).1 H i
  rcases Hi.pend with hp | ⟨p, hp, -⟩
  · exact ⟨[], s, rfl, by simp, he, hj, H, hp, rfl, by simp⟩
  · -- retransmit
    have h1 : step repairParams s (.retx i p.seq) = some (s.send i (.req p.seq p.push p.gen)) := by
      simp [step, hp]
    set s2 := s.send i (.req p.seq p.push p.gen) with hs2
    have H2 := step_pres H h1
    have hc2 : s2.chan i = [.req p.seq p.push p.gen] := by simp [s2, he i]
    -- deliver it
    have hG := onReq_good repairParams (s2.setChan i []) (!i) p.seq p.push p.gen false
      (by simpa [s2] using hj (!i))
    obtain ⟨g1, g2, ⟨r, g3⟩, g4, g5⟩ := hG
    rw [Bool.not_not] at g1 g2
    set s3 := onReq repairParams (s2.setChan i []) (!i) p.seq p.push p.gen false false with hs3
    have h2 : step repairParams s2 (.deliver i false false) = some s3 := by simp [step, hc2, s3]
    have H3 := step_pres H2 h2
    have hc3 : s3.chan (!i) = [.rep p.seq r] := by rw [g3]; simp [s2, he (!i)]
    have hl : r.late = false := by
      have := ((inv_iff s3).1 H3 (!i)).chanI (.rep p.seq r) (by rw [hc3]; simp)
      exact this
    -- deliver the answer
    set s4 := onRep repairParams (s3.setChan (!i) []) (!(!i)) p.seq r with hs4
    have h3 : step repairParams s3 (.deliver (!i) false false) = some s4 := by simp [step, hc3, s4]
    have H4 := step_pres H3 h3
    rw [Bool.not_not] at hs4
    obtain ⟨v1, v2, -, v4⟩ := onRep_view repairParams (s3.setChan (!i) []) i p.seq r
    have v3 := onRep_chan_nolate repairParams (s3.setChan (!i) []) i p.seq r hl
    have hp3 : (s3.nd i).pend = [p] := by rw [g1]; simpa [s2] using hp
    have v5 := onRep_closes repairParams (s3.setChan (!i) []) i r (by simpa using hp3)
    refine ⟨[.retx i p.seq, .deliver i false false, .deliver (!i) false false], s4,
      by simp [runEvs, h1, h2, h3], by simp, ?_, ?_, H4, ?_, ?_, by simp [Prog]⟩
    · have c1 : s4.chan i = [] := by rw [hs4, v3, St.chan_setChan_not', g2, St.chan_setChan_self]
      have c2 : s4.chan (!i) = [] := by rw [hs4, v2, St.chan_setChan_self]
      intro k; cases i <;> cases k <;> simpa using (by assumption)
    · have c1 : (s4.nd i).job = none := by
        rw [hs4, v4, St.nd_setChan, g1]; simpa [s2] using hj i
      have c2 : (s4.nd (!i)).job = none := by rw [hs4, v1, St.nd_setChan]; exact g4
      intro k; cases i <;> cases k <;> simpa using (by assumption)
    · rw [hs4]; exact v5
    · rw [hs4, v1]; simp [g5, s2]


/-- **The transfer layer cannot get stuck.** From every configuration reachable from the start of
Phase 4 under the repaired protocol, a loss-free continuation without new offers and without
budget changes, of at most `Wt s + 12` events (`Wt s` is three per request, two per answer and one
per confirmation in flight), reaches a quiet configuration; by `thm3b_transfer_repaired` that
configuration has exactly one owner once the start is agreed. The continuation's other choices
are those of a chain that fails and of a receiver without room. -/
theorem quiet_reachable (da db : Bool) (es : List Ev) {s : St}
    (hrun : runEvs repairParams (start da db) es = some s) :
    ∃ es' t, runEvs repairParams s es' = some t ∧ Quiet t ∧ es'.length ≤ Wt s + 12 ∧
      ∀ e ∈ es', Prog e := by
  have H := runEvs_pres (inv_start da db) hrun
  obtain ⟨e1, t1, r1, l1, j1, n1, -, w1, H1, P1⟩ := finish_one s false H
  obtain ⟨e2, t2, r2, l2, j2, n2, -, w2, H2, P2⟩ := finish_one t1 true H1
  have c2 : Calm t2 := by
    intro k; cases k
    · have := congrArg Node.job n2; simp only [Bool.not_true] at this; rw [this]; exact j1
    · exact j2
  obtain ⟨e3, t3, r3, l3, ha3, hb3, c3, H3, -, P3⟩ := drain (Wt t2) t2 le_rfl H2 c2
  have he3 : ∀ k, t3.chan k = [] := fun k => by cases k <;> assumption
  obtain ⟨e4, t4, r4, l4, he4, c4, H4, p4, -, P4⟩ := round t3 false H3 c3 he3
  obtain ⟨e5, t5, r5, l5, he5, c5, H5, p5, q5, P5⟩ := round t4 true H4 c4 he4
  refine ⟨e1 ++ e2 ++ e3 ++ e4 ++ e5, t5, ?_, ?_, ?_, ?_⟩
  · simp [runEvs_append, r1, r2, r3, r4, r5]
  · have hA := H5.1
    have hfa := he5 false; have hfb := he5 true
    have ja := c5 false; have jb := c5 true
    simp only [Bool.not_true] at q5
    rw [p4] at q5
    simp only [Quiet, quietB, Bool.and_eq_true, List.isEmpty_iff, Option.isNone_iff_eq_none]
    exact ⟨⟨⟨⟨⟨⟨⟨hfa, hfb⟩, q5⟩, p5⟩, ja⟩, jb⟩, hA.late⟩, H5.2.late⟩
  · simp only [List.length_append]; omega
  · intro e he
    simp only [List.mem_append] at he
    rcases he with (((h | h) | h) | h) | h
    · exact P1 e h
    · exact P2 e h
    · obtain ⟨i, rfl⟩ := P3 e h; exact ⟨rfl, rfl⟩
    · exact P4 e h
    · exact P5 e h

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms quiet_reachable
