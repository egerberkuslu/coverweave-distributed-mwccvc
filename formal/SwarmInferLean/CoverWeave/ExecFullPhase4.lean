import SwarmInferLean.CoverWeave.ExecFullOffers
import SwarmInferLean.CoverWeave.ExecFullTransferR2p

/-!
# CoverWeave, Lemma 4 for Phase 4 under the controller, from the slot `T₀` (R2'', inventory C9)

Source: `CoverWeave_R1/sections/04-formaleng.tex:131-137` (`lem:lossless`, steps 2 and 3: the
signatures settle, then each round sends at most one HANDOVER and one PUSH per flexible neighbour
and a PUSH of depth `d` spawns at most `ν_d` requests), `bbcvc.py` `_fix_overload`,
`_service_push_job` of branch `r2r3-repair` with R2''.

This file fixes the assumptions under which Lemma 4 holds for Phase 4 of the controller of
`ExecFullController.lean`, all stated from one slot `T₀` (`Phase4Hyps`), and proves the window
from them (`ctl_phase4_window`): every edge is quiet at `phase4Bound T₀ Δ Tr D π n` and its
settled decisions are consistent (Theorem 3(b) under R2''). Of the assumptions of
`ChainNet.quiet_phase4`, the chain discipline and its bound are proven for the controller
(`ctl_seqOK`, `ctl_base`), the hop limits are bounded by those of the ladder (`ttlC_le`), and the
offering discipline comes from `ctl_offerSeq`. What stays assumed, per field of `Phase4Hyps`:

* `start`: Phase 4 starts with no chain and every edge in the invariant of the transfer layer;
* `deg`, `rx`: degree at most `Δ`, every retransmission timer fires in every `Tr` slots
  (`timer_fires` of `ExecFullLadder.lean` with `Tr = 2^(R-1) T₀`);
* `ladTtl`, `ttl0`: the ladder pushes with hop limit at most `D`;
* `offers`: from `T₀` on, at every end the ladder's slots and the probe slots of the node's chains
  lie in sets of total size at most `n`, and an end idle for `π + 1` slots never offers again.
  `T₀` is the slot after which no signature changes (step 2 of the proof of `lem:lossless`,
  `γ_v` changes per node); `n` per end is what `offers_le` bounds per signature. That signatures
  stop changing, and the moment `T₀`, are not derived here (Phases 1 to 3 and the epochs are other
  models).

`ex_phase4_window`: the hypotheses hold for one edge between two leaves whose end `false` pushes
at slot 0 (`T₀ = 0`, `Δ = 1`, `Tr = 20`, `D = 2`, `π = 1`, `n = 1`).
-/

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

variable {T : Topo}

/-! ### Hop limits stay below the ladder's -/

theorem jobTtl_le {S : NS T} {D : ℕ} (h : ∀ e c q, S.ttl e c q ≤ D) (w : T.W) :
    jobTtl S w ≤ D := by
  unfold jobTtl
  cases S.crec w with
  | none => exact Nat.zero_le _
  | some r =>
    simp only
    cases (nodeAt S.es r.J).job with
    | none => exact Nat.zero_le _
    | some jb => exact h _ _ _

theorem ttl_le_step {E : NEnv T} {S : NS T} {t D : ℕ} (hL : ∀ e c, E.ladTtl t e c ≤ D)
    (h : ∀ e c q, S.ttl e c q ≤ D) : ∀ e c q, (ctlStep E S t).ttl e c q ≤ D := by
  intro e c q
  show ttlNext E S t e c q ≤ D
  unfold ttlNext
  split_ifs
  · cases offAt E S t e c with
    | none => exact h e c q
    | some b =>
      simp only
      cases cact S (T.own e c) with
      | probe x => exact (Nat.sub_le _ _).trans (jobTtl_le h _)
      | idle => exact hL e c
      | fin ok => exact hL e c
  · exact h e c q

theorem ttl_run_le {E : NEnv T} {S₀ : NS T} {D : ℕ} (hL : ∀ t e c, E.ladTtl t e c ≤ D)
    (h0 : ∀ e c q, S₀.ttl e c q ≤ D) : ∀ t e c q, (netRunC E S₀ t).ttl e c q ≤ D
  | 0 => h0
  | t + 1 => ttl_le_step (hL t) (ttl_run_le hL h0 t)

theorem ttlC_le {E : NEnv T} {S₀ : NS T} {D : ℕ} (hL : ∀ t e c, E.ladTtl t e c ≤ D)
    (h0 : ∀ e c q, S₀.ttl e c q ≤ D) (e : T.Ed) (c : Bool) (q : ℕ) : ttlC E S₀ e c q ≤ D := by
  classical
  unfold ttlC
  split
  · exact ttl_run_le hL h0 _ _ _ _
  · exact Nat.zero_le _

/-! ### The assumptions from `T₀` and the window -/

/-- **The assumptions of Lemma 4 for Phase 4**, for the controller run from `S₀` under `E`, from
the slot `T₀` at which the signatures have settled. -/
structure Phase4Hyps (E : NEnv T) (S₀ : NS T) (T₀ Δ Tr D π n : ℕ) : Prop where
  /-- Phase 4 starts with no chain and every edge in the invariant of the transfer layer. -/
  start : CtlStart S₀
  /-- Every node has at most `Δ` edge ends. -/
  deg : ∀ w, (T.ends w).length ≤ Δ
  /-- Every retransmission timer fires at least once in every `Tr` slots. -/
  rx : ∀ e c u, ∃ v, u ≤ v ∧ v < u + Tr ∧ E.rx v e c = true
  /-- The ladder pushes with hop limit at most `D`. -/
  ladTtl : ∀ t e c, E.ladTtl t e c ≤ D
  /-- The hop limits of the start are at most `D`. -/
  ttl0 : ∀ e c q, S₀.ttl e c q ≤ D
  /-- From `T₀` on, the ladder's slots and the probe slots of every end lie in sets of total size
  at most `n`, and an end idle for `π + 1` consecutive slots never offers again. -/
  offers : ∀ e c, ∃ F P : Finset ℕ, F.card + P.card ≤ n ∧
    (∀ v, T₀ ≤ v → E.ladder v e c ≠ none → v ∈ F) ∧
    (∀ v, T₀ ≤ v → cact (netRunC E S₀ v) (T.own e c) = .probe (e, c) → v ∈ P) ∧
    (∀ t, T₀ ≤ t → (∀ v, t ≤ v → v ≤ t + π → (((netRunC E S₀ v).es e).nd c).pend = []) →
      ∀ v, t ≤ v → offAt E (netRunC E S₀ v) v e c = none)

/-- The slot by which Phase 4 is quiet: `T₀ + (n + 1)(π + Tr + d + 2) + π + Tr + 2 d + 4`,
`d = dBound Δ Tr D`. -/
def phase4Bound (T₀ Δ Tr D π n : ℕ) : ℕ :=
  T₀ + (n + 1) * (π + Tr + ChainNet.dBound Δ Tr D + 2) + π + Tr + 2 * ChainNet.dBound Δ Tr D + 4

/-- **Lemma 4 for Phase 4 under the controller.** Under `Phase4Hyps`, every edge is quiet at slot
`phase4Bound T₀ Δ Tr D π n`, and its two settled decisions are consistent. -/
theorem ctl_phase4_window {E : NEnv T} {S₀ : NS T} {T₀ Δ Tr D π n : ℕ}
    (H : Phase4Hyps E S₀ T₀ Δ Tr D π n) (e : T.Ed) :
    Quiet ((netRunC E S₀ (phase4Bound T₀ Δ Tr D π n)).es e) ∧
      ConsistentPair ((netRunC E S₀ (phase4Bound T₀ Δ Tr D π n)).es e).a.X
        ((netRunC E S₀ (phase4Bound T₀ Δ Tr D π n)).es e).b.X := by
  have hq := (ctlNet E S₀ H.start).quiet_phase4 (Δ := Δ) (Tr := Tr) (D := D) (π := π)
    (n := n + 1) (T₀ := T₀) (fun e c u => H.rx e c u) (ctl_base E S₀ H.start)
    (ctl_seqOK E S₀ H.start H.deg) (fun e i p => ttlC_le H.ladTtl H.ttl0 e i p.seq)
    (fun e c => by
      obtain ⟨F, P, hn, hF, hP, hI⟩ := H.offers e c
      obtain ⟨os, hl, hs⟩ := ctl_offerSeq E S₀ H.start F P hF hP hI
      exact ⟨os, by omega, hs⟩) e
  rw [ctlNet_run] at hq
  exact ⟨hq, (cp_iff _ _).1 (cp_of_quiet (run_inv E S₀ H.start _ e) hq)⟩

/-- At a node with one end, an offer comes only from the ladder. -/
theorem offAt_none_single {E : NEnv T} {S : NS T} (H : RecOK S) {t : ℕ} {e : T.Ed} {c : Bool}
    (hw : (T.ends (T.own e c)).length ≤ 1) (hl : E.ladder t e c = none) :
    offAt E S t e c = none := by
  by_contra h
  rcases offAt_cases h with h | h
  · exact cact_single H hw _ h
  · exact h hl

/-! ### Non-vacuity: one edge between two leaves -/

/-- Node 0 is end `false`, node 1 end `true` of the one edge. -/
abbrev exTopo2 : Topo where
  W := Fin 2
  Ed := Fin 1
  dW := inferInstance
  dE := inferInstance
  ends w := [(0, decide (w = 1))]
  own _ c := if c then 1 else 0
  hown := by decide
  nodup := by decide

/-- End `false` pushes at slot 0 with hop limit 2; the other end has no room. -/
def exEnv2 : NEnv exTopo2 where
  room _ _ _ _ := false
  rx t _ _ := t % 20 == 0
  ladder t _ c := if t = 0 ∧ c = false then some true else none
  ladTtl _ _ _ := 2
  evict _ _ := []

def exStart2 : NS exTopo2 where
  es _ := start true false
  crec _ := none
  ttl _ _ _ := 0

theorem ex_start2 : CtlStart exStart2 where
  inv _ := inv_start _ _
  nojob x := by obtain ⟨e, c⟩ := x; cases c <;> rfl
  norec _ := rfl

theorem ex_phase4Hyps : Phase4Hyps exEnv2 exStart2 0 1 20 2 1 1 := by
  have hw : ∀ (e : Fin 1) (c : Bool), (exTopo2.ends (exTopo2.own e c)).length ≤ 1 := by decide
  have hlad : ∀ v (e : Fin 1) c, (v ≠ 0 ∨ c = true) → exEnv2.ladder v e c = none := by
    intro v e c h
    simp only [exEnv2]
    rcases h with h | rfl
    · simp [h]
    · simp
  have hopen : (((netRunC exEnv2 exStart2 1).es 0).nd false).pend ≠ [] := by decide +kernel
  refine ⟨ex_start2, by decide, fun _ _ u => ⟨u + (20 - u % 20) % 20, by omega, by omega,
    by simp [exEnv2]; omega⟩, fun _ _ _ => le_refl _, fun _ _ _ => Nat.zero_le _, ?_⟩
  intro e c
  have he : e = 0 := Subsingleton.elim _ _
  subst he
  cases c
  · refine ⟨{0}, ∅, by simp, fun v _ h => ?_, fun v _ h => ?_, fun t _ hI v hv => ?_⟩
    · simp only [Finset.mem_singleton]
      by_contra hv; exact h (hlad v 0 false (Or.inl hv))
    · exact absurd h (cact_single (run_rec exEnv2 exStart2 ex_start2 v) (hw 0 false) _)
    · rcases Nat.eq_zero_or_pos t with rfl | ht
      · exact absurd (hI 1 (by omega) (by omega)) hopen
      · exact offAt_none_single (run_rec exEnv2 exStart2 ex_start2 v) (hw 0 false)
          (hlad v 0 false (Or.inl (by omega)))
  · refine ⟨∅, ∅, by simp, fun v _ h => absurd (hlad v 0 true (Or.inr rfl)) h,
      fun v _ h => absurd h (cact_single (run_rec exEnv2 exStart2 ex_start2 v) (hw 0 true) _),
      fun t _ _ v _ => offAt_none_single (run_rec exEnv2 exStart2 ex_start2 v) (hw 0 true)
        (hlad v 0 true (Or.inr rfl))⟩

/-- So `ctl_phase4_window` applies to a run with a push and a chain. -/
example : Quiet ((netRunC exEnv2 exStart2 (phase4Bound 0 1 20 2 1 1)).es 0) :=
  (ctl_phase4_window ex_phase4Hyps 0).1

/-- The push of slot 0 does start a chain at the other end (slot 2), so the run is not trivial. -/
theorem ex_phase4_chain : (((netRunC exEnv2 exStart2 2).es 0).nd true).job.isSome = true := by
  decide +kernel

/-! ### Idleness is not final: `OfferSeq` fails without `hidle`

In the controller an idle end can be offered again in two ways: a later slot of the ladder (the
oblivious `E.ladder`, standing for a new ladder step after a clear of the tried set) and a probe of a
chain that a neighbour's PUSH starts at its node. Neither is excluded by the controller's rules, so
the hypothesis `hidle` of `ctl_offerSeq` cannot be derived from them; it is a property of the
ladder's schedule (`_fix_overload` runs on every tick and stops offering only when its tried set
is exhausted, which a clear undoes). The run below shows that the conclusion fails without it. -/

/-- If the only request of end `i` before slot `c` is `q`, the end is idle on `[c, c + π]` and it
offers at a slot `L ≥ c + π`, no list of anchors makes it follow `OfferSeq π` from a slot `≤ c`. -/
theorem ChainNet.not_offerSeq_of_gap (N : ChainNet) {π : ℕ} {e : N.Ed} {i : Bool} {c L : ℕ}
    {q : List Pend} (hbefore : ∀ v, v < c → ((N.run e v).nd i).pend = [] ∨ ((N.run e v).nd i).pend = q)
    (hgap : ∀ v, c ≤ v → v ≤ c + π → ((N.run e v).nd i).pend = [])
    (hL : c + π ≤ L) (hoff : (N.env e).off L i ≠ none) :
    ∀ (os : List N.Probe) (prev : ℕ), prev ≤ c → ¬ N.OfferSeq π e i prev os := by
  intro os
  induction os with
  | nil =>
    intro prev hp h
    rw [ChainNet.OfferSeq] at h
    exact hoff (h L (by omega))
  | cons pr rest ih =>
    intro prev hp h
    rw [ChainNet.OfferSeq] at h
    obtain ⟨-, -, ha, hpa, -, hnext⟩ := h
    have hlt : pr.a < c := by
      by_contra hc
      have := hgap pr.a (by omega) (by omega)
      rw [hpa] at this; simp at this
    have hq : q = [pr.p] := by
      rcases hbefore pr.a hlt with h | h
      · rw [hpa] at h; simp at h
      · rw [← h, hpa]
    refine ih c le_rfl (hnext c hlt.le ?_)
    rw [hgap c le_rfl (by omega)]; simp

theorem ctl_off {T : Topo} (E : NEnv T) (S₀ : NS T) (hS : CtlStart S₀) (e : T.Ed) (t : ℕ) (c : Bool) :
    ((ctlNet E S₀ hS).env e).off t c = offAt E (netRunC E S₀ t) t e c := rfl

/-- The leaf of `exTopo2` pushes at slot 0 and again at slot 6. -/
def exEnv3 : NEnv exTopo2 where
  room _ _ _ _ := false
  rx t _ _ := t % 20 == 0
  ladder t _ c := if (t = 0 ∨ t = 6) ∧ c = false then some true else none
  ladTtl _ _ _ := 2
  evict _ _ := []

/-- **Without `hidle` the conclusion of `ctl_offerSeq` fails.** The leaf's first PUSH is open in
slots 1 to 3 and closed at 4; the end is idle in slots 4 and 5 and pushes again at slot 6. The
budget hypotheses hold (`F = {0, 6}`, no probes at a leaf), `hidle` fails, and no list of anchors
makes the end follow `OfferSeq 1` from slot 0. -/
theorem ex_not_offerSeq :
    (∀ v, 0 ≤ v → exEnv3.ladder v 0 false ≠ none → v ∈ ({0, 6} : Finset ℕ)) ∧
    ¬ (∀ t, 0 ≤ t → (∀ v, t ≤ v → v ≤ t + 1 → (((netRunC exEnv3 exStart2 v).es 0).nd false).pend = []) →
        ∀ v, t ≤ v → offAt exEnv3 (netRunC exEnv3 exStart2 v) v 0 false = none) ∧
    ∀ os : List (ctlNet exEnv3 exStart2 ex_start2).Probe,
      ¬ (ctlNet exEnv3 exStart2 ex_start2).OfferSeq 1 (0 : Fin 1) false 0 os := by
  have h4 : (((netRunC exEnv3 exStart2 4).es 0).nd false).pend = [] := by decide +kernel
  have h5 : (((netRunC exEnv3 exStart2 5).es 0).nd false).pend = [] := by decide +kernel
  have h6 : offAt exEnv3 (netRunC exEnv3 exStart2 6) 6 0 false ≠ none := by decide +kernel
  have hb : ∀ v, v < 4 → (((netRunC exEnv3 exStart2 v).es 0).nd false).pend = [] ∨
      (((netRunC exEnv3 exStart2 v).es 0).nd false).pend =
        (((netRunC exEnv3 exStart2 1).es 0).nd false).pend := by
    intro v hv
    interval_cases v
    · left; decide +kernel
    · right; rfl
    · right; decide +kernel
    · right; decide +kernel
  refine ⟨fun v _ h => ?_, fun H => h6 (H 4 (by omega) (fun v h1 h2 => ?_) 6 (by omega)), fun os => ?_⟩
  · by_contra hv
    simp only [Finset.mem_insert, Finset.mem_singleton, not_or] at hv
    exact h (by simp [exEnv3, hv.1, hv.2])
  · rcases (by omega : v = 4 ∨ v = 5) with rfl | rfl
    · exact h4
    · exact h5
  · refine (ctlNet exEnv3 exStart2 ex_start2).not_offerSeq_of_gap (c := 4) (L := 6)
      (q := (((netRunC exEnv3 exStart2 1).es 0).nd false).pend)
      (fun v hv => by rw [ctlNet_run]; exact hb v hv)
      (fun v h1 h2 => by
        rw [ctlNet_run]
        rcases (by omega : v = 4 ∨ v = 5) with rfl | rfl
        · exact h4
        · exact h5) (by omega) (by rw [ctl_off]; exact h6) os 0 (by omega)

end SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ctl_phase4_window
open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ex_phase4Hyps
open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ex_not_offerSeq
