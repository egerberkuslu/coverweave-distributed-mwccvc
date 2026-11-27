import SwarmInferLean.CoverWeave.ExecFullController

/-!
# CoverWeave, Phase 4: the hypotheses of the chain bound are satisfiable

A concrete network of four edges, each run in the synchronous scheduler, in which:
* edge 0 carries a push chain at end `true` for the PUSH of end `false`, from slot 2 to slot 8;
* the chain probes end `true` of edge 1 (open in slots 3-4) and then of edge 2 (open in slots 6-7),
  so it follows `SeqOK` with two probes (`ex_seqOK`);
* end `true` of edge 3 makes two offers, the first one refused (`ex_offerSeq`);
* every hypothesis of `quiet_phase4` holds, `hServe` with that two-probe chain (`ex_phase4`);
* for the controller of `ExecFullController`: a star whose hypotheses (`CtlStart`, degree bound,
  timers) hold and in which the controller runs a chain that makes two probes (`ex_ctl_tried`) and
  follows `SeqOK` with both (`ex_ctl_seqOK`), so `ctl_seqOK` and `ctl_chain_bound` are not vacuous.

The runs are evaluated by `decide`; from slot 10 on every edge is idle and stays so. The same
network is checked twice: for the R2'' layer (`R2pp`, the definitions of `ExecFullChainR2pp`) and
for the R2 layer (the definitions of `ExecFullChain`).
-/

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

def exEnv : Fin 4 → EnvO
  | 0 => { room := fun _ _ _ => false, chain := fun t i _ => t == 1 && i == false,
           rx := fun t _ => t % 20 == 0,
           fin := fun t i => if t = 8 ∧ i = true then some (false, false) else none,
           misc := fun _ => [], off := fun t i => if t = 0 ∧ i = false then some true else none }
  | 1 => { room := fun _ _ _ => true, chain := fun _ _ _ => false, rx := fun t _ => t % 20 == 0,
           fin := fun _ _ => none, misc := fun _ => [],
           off := fun t i => if t = 2 ∧ i = true then some true else none }
  | 2 => { room := fun _ _ _ => true, chain := fun _ _ _ => false, rx := fun t _ => t % 20 == 0,
           fin := fun _ _ => none, misc := fun _ => [],
           off := fun t i => if t = 5 ∧ i = true then some true else none }
  | 3 => { room := fun _ _ _ => false, chain := fun _ _ _ => false, rx := fun t _ => t % 20 == 0,
           fin := fun _ _ => none, misc := fun _ => [],
           off := fun t i => if (t = 2 ∨ t = 5) ∧ i = true then some true else none }

def exInit : Fin 4 → St
  | 0 => start true false
  | 1 => start true true
  | 2 => start true true
  | 3 => start false true

abbrev exNet : ChainNet where
  Ed := Fin 4
  env := exEnv
  init := exInit
  inv e := by fin_cases e <;> exact inv_start _ _
  misc e t ev h := by fin_cases e <;> simp [exEnv] at h
  ttl e _ _ := if e = 0 then 2 else 1

theorem ex_run (e : Fin 4) (t : ℕ) : exNet.run e t = srunO (exEnv e) (exInit e) t := rfl

/-- A slot without deliveries, chain ends, offers or evictions, from a configuration with nothing
open, leaves it alone. -/
theorem slotO_idle {E : EnvO} {t : ℕ} {s : St} (hA : s.fromA = []) (hB : s.fromB = [])
    (hpa : s.a.pend = []) (hpb : s.b.pend = []) (hf : ∀ i, E.fin t i = none)
    (ho : ∀ i, E.off t i = none) (hm : E.misc t = []) : slotO E t s = s := by
  simp only [slotO, slot, slotEvs, hA, hB, List.length_nil, delivs, List.range_zero, List.map_nil,
    finEv, hf, rxEv, offEv, ho, hm, List.nil_append, List.append_nil]
  split_ifs <;> simp [evsT, stepT, step, St.nd, hpa, hpb]

theorem ex_idle (e : Fin 4) : ∀ k, exNet.run e (10 + k) = exNet.run e 10
  | 0 => rfl
  | k + 1 => by
    show slotO (exEnv e) (10 + k) (exNet.run e (10 + k)) = _
    rw [ex_idle e k]
    have h10 : ∀ e : Fin 4, (exNet.run e 10).fromA = [] ∧ (exNet.run e 10).fromB = [] ∧
        (exNet.run e 10).a.pend = [] ∧ (exNet.run e 10).b.pend = [] := by decide
    obtain ⟨h1, h2, h3, h4⟩ := h10 e
    apply slotO_idle h1 h2 h3 h4 <;> fin_cases e <;> simp [exEnv] <;> omega

theorem ex_job_small : ∀ e : Fin 4, ∀ c : Bool, ∀ v < 11, ((exNet.run e v).nd c).job =
    if e = 0 ∧ c = true ∧ 2 ≤ v ∧ v ≤ 8 then some (1, false) else none := by decide

theorem ex_job (e : Fin 4) (c : Bool) (v : ℕ) : ((exNet.run e v).nd c).job =
    if e = 0 ∧ c = true ∧ 2 ≤ v ∧ v ≤ 8 then some (1, false) else none := by
  by_cases hv : v < 11
  · exact ex_job_small e c v hv
  · obtain ⟨k, rfl⟩ : ∃ k, v = 10 + k := ⟨v - 10, by omega⟩
    rw [ex_idle e k, ex_job_small e c 10 (by omega)]
    simp only [show ¬ (10 ≤ 8) by omega, show ¬ (10 + k ≤ 8) by omega, and_false]

theorem ex_off (e : Fin 4) (i : Bool) {v : ℕ} (hv : 6 ≤ v) : (exNet.env e).off v i = none := by
  fin_cases e <;> simp [exEnv] <;> omega

/-- The PUSH of end `false` of edge 0. -/
def p0 : Pend := ⟨1, true, 0, 0⟩
def pr1 : exNet.Probe := ⟨(1 : Fin 4), true, p0, 3⟩
def pr2 : exNet.Probe := ⟨(2 : Fin 4), true, p0, 6⟩

/-- **`SeqOK` holds for a chain with two probes.** The chain at end `true` of edge 0, running from
slot 2, probes edge 1 (open in slots 3 and 4, closed at 5), then edge 2 (open in slots 6 and 7,
closed at 8), and is gone at slot 9. -/
theorem ex_seqOK (p : Pend) : exNet.SeqOK 0 false p 2 [pr1, pr2] := by
  have hJ9 : ¬ HJob (exNet.run 0 9) false p := by
    rintro ⟨b, hb⟩; rw [ex_job] at hb; simp at hb
  refine ⟨by decide, by decide, by decide, by simp [exNet, pr1], ?_⟩
  intro c hc hne hfirst
  change 3 ≤ c at hc
  rcases (by omega : c = 3 ∨ c = 4 ∨ c = 5 ∨ 6 ≤ c) with rfl | rfl | rfl | h6
  · exact absurd (by decide) hne
  · exact absurd (by decide) hne
  · refine ⟨by decide, by decide, by decide, by simp [exNet, pr2], ?_⟩
    intro c hc hne hfirst
    change 6 ≤ c at hc
    rcases (by omega : c = 6 ∨ c = 7 ∨ c = 8 ∨ 9 ≤ c) with rfl | rfl | rfl | h9
    · exact absurd (by decide) hne
    · exact absurd (by decide) hne
    · exact hJ9
    · exact absurd (hfirst 8 (by decide) (by omega)) (by decide)
  · exact absurd (hfirst 5 (by decide) (by omega)) (by decide)

/-- The chain is real: it serves the PUSH `p0` from slot 2. -/
theorem ex_chain : HJob (exNet.run 0 2) false p0 := ⟨false, by rw [ex_job]; rfl⟩

def o1 : exNet.Probe := ⟨(3 : Fin 4), true, p0, 3⟩
def o2 : exNet.Probe := ⟨(3 : Fin 4), true, ⟨2, true, 0, 0⟩, 6⟩

/-- **`OfferSeq` holds for an end with two offers.** End `true` of edge 3 offers in slot 2 (open
in slots 3 and 4, refused) and again in slot 5 (open in slots 6 and 7). -/
theorem ex_offerSeq : exNet.OfferSeq 6 3 true 0 [o1, o2] := by
  refine ⟨rfl, rfl, by decide, by decide, fun v h1 h2 => ex_off 3 true h1, ?_⟩
  intro c hc _
  change 3 ≤ c at hc
  refine ⟨rfl, rfl, by change 6 ≤ c + 6; omega, by decide,
    fun _ h1 _ => ex_off 3 true (by omega), ?_⟩
  intro c' _ _ _ hv
  exact ex_off 3 true (by omega)

theorem ex_offerSeq_one {e : Fin 4} {i : Bool} {a : ℕ} {q : Pend} (ha : a ≤ 6)
    (hp : ((exNet.run e a).nd i).pend = [q]) :
    exNet.OfferSeq 6 e i 0 [⟨e, i, q, a⟩] :=
  ⟨rfl, rfl, ha, hp, fun v h1 _ => ex_off e i h1, fun _ _ _ _ hv => ex_off e i (by omega)⟩

theorem ex_offerSeq_nil (e : Fin 4) (i : Bool) : exNet.OfferSeq 6 e i 0 [] :=
  fun _ hv => ex_off e i hv

/-- **The hypotheses of `quiet_phase4` hold** for the example network, with degree bound 3, timer
period 20, hop bound 2, offer gap 6 and at most two offers per end; `hServe` is met by the chain
with two probes, `hOff` by ends with one or two offers. -/
theorem ex_phase4 :
    (∀ e i u, ∃ v, u ≤ v ∧ v < u + 20 ∧ (exNet.env e).rx v i = true) ∧
    (∀ e i p v, HJob (exNet.run e v) i p → 1 ≤ exNet.ttl e i p) ∧
    (∀ e i p v, HJob (exNet.run e v) i p → ∃ s, s ≤ v ∧ HJob (exNet.run e s) i p ∧
      ∃ probes : List exNet.Probe, probes.length + 1 ≤ 3 ∧ exNet.SeqOK e i p s probes) ∧
    (∀ e i p, exNet.ttl e i p ≤ 2) ∧
    (∀ e i, ∃ os : List exNet.Probe, os.length ≤ 2 ∧ exNet.OfferSeq 6 e i 0 os) := by
  refine ⟨?_, ?_, ?_, ?_, ?_⟩
  · intro e i u
    refine ⟨u + (20 - u % 20) % 20, by omega, by omega, ?_⟩
    fin_cases e <;> simp [exEnv] <;> omega
  · intro e i p v _; show 1 ≤ ite _ _ _; split_ifs <;> omega
  · intro e i p v ⟨b, hb⟩
    rw [ex_job] at hb
    split_ifs at hb with hc
    · obtain ⟨rfl, hi, h2, -⟩ := hc
      simp only [Option.some.injEq, Prod.mk.injEq] at hb
      have hi' : i = false := by simpa using hi
      subst hi'
      refine ⟨2, h2, ⟨false, by rw [ex_job]; simp [← hb.1]⟩, [pr1, pr2], by simp,
        ex_seqOK p⟩
  · intro e i p; show ite _ _ _ ≤ 2; split_ifs <;> omega
  · intro e i
    fin_cases e <;> cases i
    · refine ⟨_, ?_, ex_offerSeq_one (a := 1) (q := p0) (by omega) ?_⟩ <;> decide
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · refine ⟨_, ?_, ex_offerSeq_one (a := 3) (q := p0) (by omega) ?_⟩ <;> decide
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · refine ⟨_, ?_, ex_offerSeq_one (a := 6) (q := p0) (by omega) ?_⟩ <;> decide
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · exact ⟨[o1, o2], by simp, ex_offerSeq⟩

/-- `quiet_phase4` applies to the example network. -/
example (e : Fin 4) : Quiet (exNet.run e (0 + 2 * (6 + 20 + ChainNet.dBound 3 20 2 + 2) + 6 + 20 +
    2 * ChainNet.dBound 3 20 2 + 4)) :=
  have h := ex_phase4
  exNet.quiet_phase4 h.1 h.2.1 h.2.2.1 h.2.2.2.1 h.2.2.2.2 e

end SwarmInfer.CoverWeave.ExecFull.R2pp

namespace SwarmInfer.CoverWeave.ExecFull


def exEnv : Fin 4 → EnvO
  | 0 => { room := fun _ _ _ => false, chain := fun t i _ => t == 1 && i == false,
           rx := fun t _ => t % 20 == 0,
           fin := fun t i => if t = 8 ∧ i = true then some (false, false) else none,
           misc := fun _ => [], off := fun t i => if t = 0 ∧ i = false then some true else none }
  | 1 => { room := fun _ _ _ => true, chain := fun _ _ _ => false, rx := fun t _ => t % 20 == 0,
           fin := fun _ _ => none, misc := fun _ => [],
           off := fun t i => if t = 2 ∧ i = true then some true else none }
  | 2 => { room := fun _ _ _ => true, chain := fun _ _ _ => false, rx := fun t _ => t % 20 == 0,
           fin := fun _ _ => none, misc := fun _ => [],
           off := fun t i => if t = 5 ∧ i = true then some true else none }
  | 3 => { room := fun _ _ _ => false, chain := fun _ _ _ => false, rx := fun t _ => t % 20 == 0,
           fin := fun _ _ => none, misc := fun _ => [],
           off := fun t i => if (t = 2 ∨ t = 5) ∧ i = true then some true else none }

def exInit : Fin 4 → St
  | 0 => start true false
  | 1 => start true true
  | 2 => start true true
  | 3 => start false true

abbrev exNet : ChainNet where
  Ed := Fin 4
  env := exEnv
  init := exInit
  inv e := by fin_cases e <;> exact inv_start _ _
  misc e t ev h := by fin_cases e <;> simp [exEnv] at h
  ttl e _ _ := if e = 0 then 2 else 1

theorem ex_run (e : Fin 4) (t : ℕ) : exNet.run e t = srunO (exEnv e) (exInit e) t := rfl

/-- A slot without deliveries, chain ends, offers or evictions, from a configuration with nothing
open, leaves it alone. -/
theorem slotO_idle {E : EnvO} {t : ℕ} {s : St} (hA : s.fromA = []) (hB : s.fromB = [])
    (hpa : s.a.pend = []) (hpb : s.b.pend = []) (hf : ∀ i, E.fin t i = none)
    (ho : ∀ i, E.off t i = none) (hm : E.misc t = []) : slotO E t s = s := by
  simp only [slotO, slot, slotEvs, hA, hB, List.length_nil, delivs, List.range_zero, List.map_nil,
    finEv, hf, rxEv, offEv, ho, hm, List.nil_append, List.append_nil]
  split_ifs <;> simp [evsT, stepT, step, St.nd, hpa, hpb]

theorem ex_idle (e : Fin 4) : ∀ k, exNet.run e (10 + k) = exNet.run e 10
  | 0 => rfl
  | k + 1 => by
    show slotO (exEnv e) (10 + k) (exNet.run e (10 + k)) = _
    rw [ex_idle e k]
    have h10 : ∀ e : Fin 4, (exNet.run e 10).fromA = [] ∧ (exNet.run e 10).fromB = [] ∧
        (exNet.run e 10).a.pend = [] ∧ (exNet.run e 10).b.pend = [] := by decide
    obtain ⟨h1, h2, h3, h4⟩ := h10 e
    apply slotO_idle h1 h2 h3 h4 <;> fin_cases e <;> simp [exEnv] <;> omega

theorem ex_job_small : ∀ e : Fin 4, ∀ c : Bool, ∀ v < 11, ((exNet.run e v).nd c).job =
    if e = 0 ∧ c = true ∧ 2 ≤ v ∧ v ≤ 8 then some (1, false) else none := by decide

theorem ex_job (e : Fin 4) (c : Bool) (v : ℕ) : ((exNet.run e v).nd c).job =
    if e = 0 ∧ c = true ∧ 2 ≤ v ∧ v ≤ 8 then some (1, false) else none := by
  by_cases hv : v < 11
  · exact ex_job_small e c v hv
  · obtain ⟨k, rfl⟩ : ∃ k, v = 10 + k := ⟨v - 10, by omega⟩
    rw [ex_idle e k, ex_job_small e c 10 (by omega)]
    simp only [show ¬ (10 ≤ 8) by omega, show ¬ (10 + k ≤ 8) by omega, and_false]

theorem ex_off (e : Fin 4) (i : Bool) {v : ℕ} (hv : 6 ≤ v) : (exNet.env e).off v i = none := by
  fin_cases e <;> simp [exEnv] <;> omega

/-- The PUSH of end `false` of edge 0. -/
def p0 : Pend := ⟨1, true, 0, 0⟩
def pr1 : exNet.Probe := ⟨(1 : Fin 4), true, p0, 3⟩
def pr2 : exNet.Probe := ⟨(2 : Fin 4), true, p0, 6⟩

/-- **`SeqOK` holds for a chain with two probes.** The chain at end `true` of edge 0, running from
slot 2, probes edge 1 (open in slots 3 and 4, closed at 5), then edge 2 (open in slots 6 and 7,
closed at 8), and is gone at slot 9. -/
theorem ex_seqOK (p : Pend) : exNet.SeqOK 0 false p 2 [pr1, pr2] := by
  have hJ9 : ¬ HJob (exNet.run 0 9) false p := by
    rintro ⟨b, hb⟩; rw [ex_job] at hb; simp at hb
  refine ⟨by decide, by decide, by decide, by simp [exNet, pr1], ?_⟩
  intro c hc hne hfirst
  change 3 ≤ c at hc
  rcases (by omega : c = 3 ∨ c = 4 ∨ c = 5 ∨ 6 ≤ c) with rfl | rfl | rfl | h6
  · exact absurd (by decide) hne
  · exact absurd (by decide) hne
  · refine ⟨by decide, by decide, by decide, by simp [exNet, pr2], ?_⟩
    intro c hc hne hfirst
    change 6 ≤ c at hc
    rcases (by omega : c = 6 ∨ c = 7 ∨ c = 8 ∨ 9 ≤ c) with rfl | rfl | rfl | h9
    · exact absurd (by decide) hne
    · exact absurd (by decide) hne
    · exact hJ9
    · exact absurd (hfirst 8 (by decide) (by omega)) (by decide)
  · exact absurd (hfirst 5 (by decide) (by omega)) (by decide)

/-- The chain is real: it serves the PUSH `p0` from slot 2. -/
theorem ex_chain : HJob (exNet.run 0 2) false p0 := ⟨false, by rw [ex_job]; rfl⟩

def o1 : exNet.Probe := ⟨(3 : Fin 4), true, p0, 3⟩
def o2 : exNet.Probe := ⟨(3 : Fin 4), true, ⟨2, true, 0, 0⟩, 6⟩

/-- **`OfferSeq` holds for an end with two offers.** End `true` of edge 3 offers in slot 2 (open
in slots 3 and 4, refused) and again in slot 5 (open in slots 6 and 7). -/
theorem ex_offerSeq : exNet.OfferSeq 6 3 true 0 [o1, o2] := by
  refine ⟨rfl, rfl, by decide, by decide, fun v h1 h2 => ex_off 3 true h1, ?_⟩
  intro c hc _
  change 3 ≤ c at hc
  refine ⟨rfl, rfl, by change 6 ≤ c + 6; omega, by decide,
    fun _ h1 _ => ex_off 3 true (by omega), ?_⟩
  intro c' _ _ _ hv
  exact ex_off 3 true (by omega)

theorem ex_offerSeq_one {e : Fin 4} {i : Bool} {a : ℕ} {q : Pend} (ha : a ≤ 6)
    (hp : ((exNet.run e a).nd i).pend = [q]) :
    exNet.OfferSeq 6 e i 0 [⟨e, i, q, a⟩] :=
  ⟨rfl, rfl, ha, hp, fun v h1 _ => ex_off e i h1, fun _ _ _ _ hv => ex_off e i (by omega)⟩

theorem ex_offerSeq_nil (e : Fin 4) (i : Bool) : exNet.OfferSeq 6 e i 0 [] :=
  fun _ hv => ex_off e i hv

/-- **The hypotheses of `quiet_phase4` hold** for the example network, with degree bound 3, timer
period 20, hop bound 2, offer gap 6 and at most two offers per end; `hServe` is met by the chain
with two probes, `hOff` by ends with one or two offers. -/
theorem ex_phase4 :
    (∀ e i u, ∃ v, u ≤ v ∧ v < u + 20 ∧ (exNet.env e).rx v i = true) ∧
    (∀ e i p v, HJob (exNet.run e v) i p → 1 ≤ exNet.ttl e i p) ∧
    (∀ e i p v, HJob (exNet.run e v) i p → ∃ s, s ≤ v ∧ HJob (exNet.run e s) i p ∧
      ∃ probes : List exNet.Probe, probes.length + 1 ≤ 3 ∧ exNet.SeqOK e i p s probes) ∧
    (∀ e i p, exNet.ttl e i p ≤ 2) ∧
    (∀ e i, ∃ os : List exNet.Probe, os.length ≤ 2 ∧ exNet.OfferSeq 6 e i 0 os) := by
  refine ⟨?_, ?_, ?_, ?_, ?_⟩
  · intro e i u
    refine ⟨u + (20 - u % 20) % 20, by omega, by omega, ?_⟩
    fin_cases e <;> simp [exEnv] <;> omega
  · intro e i p v _; show 1 ≤ ite _ _ _; split_ifs <;> omega
  · intro e i p v ⟨b, hb⟩
    rw [ex_job] at hb
    split_ifs at hb with hc
    · obtain ⟨rfl, hi, h2, -⟩ := hc
      simp only [Option.some.injEq, Prod.mk.injEq] at hb
      have hi' : i = false := by simpa using hi
      subst hi'
      refine ⟨2, h2, ⟨false, by rw [ex_job]; simp [← hb.1]⟩, [pr1, pr2], by simp,
        ex_seqOK p⟩
  · intro e i p; show ite _ _ _ ≤ 2; split_ifs <;> omega
  · intro e i
    fin_cases e <;> cases i
    · refine ⟨_, ?_, ex_offerSeq_one (a := 1) (q := p0) (by omega) ?_⟩ <;> decide
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · refine ⟨_, ?_, ex_offerSeq_one (a := 3) (q := p0) (by omega) ?_⟩ <;> decide
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · refine ⟨_, ?_, ex_offerSeq_one (a := 6) (q := p0) (by omega) ?_⟩ <;> decide
    · exact ⟨[], by simp, ex_offerSeq_nil _ _⟩
    · exact ⟨[o1, o2], by simp, ex_offerSeq⟩

/-- `quiet_phase4` applies to the example network. -/
example (e : Fin 4) : Quiet (exNet.run e (0 + 2 * (6 + 20 + ChainNet.dBound 3 20 2 + 2) + 6 + 20 +
    2 * ChainNet.dBound 3 20 2 + 4)) :=
  have h := ex_phase4
  exNet.quiet_phase4 h.1 h.2.1 h.2.2.1 h.2.2.2.1 h.2.2.2.2 e

end SwarmInfer.CoverWeave.ExecFull

/-! ### The controller: a star in which a chain probes two ends -/

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

/-- A star: node 0 is end `true` of edges 0, 1, 2; node `k + 1` is end `false` of edge `k`. -/
abbrev exTopo : Topo where
  W := Fin 4
  Ed := Fin 3
  dW := inferInstance
  dE := inferInstance
  ends w := if w = 0 then [(0, true), (1, true), (2, true)] else [(⟨w.val - 1, by omega⟩, false)]
  own e c := if c then 0 else ⟨e.val + 1, by omega⟩
  hown := by decide
  nodup := by decide

/-- Node 1 pushes edge 0 to node 0, which has no room and starts a chain; nodes 2 and 3 have no
room either, so both probes of the chain are refused and it ends after two probes. -/
def exCtlEnv : NEnv exTopo where
  room _ _ _ _ := false
  rx t _ _ := t % 20 == 0
  ladder t e c := if t = 0 ∧ e = (0 : Fin 3) ∧ c = false then some true else none
  ladTtl _ _ _ := 2
  evict _ _ := []

def exCtlStart : NS exTopo where
  es e := if e = (0 : Fin 3) then start true false else start false true
  crec _ := none
  ttl _ _ _ := 0

theorem ex_ctl_start : CtlStart exCtlStart where
  inv e := by fin_cases e <;> exact inv_start _ _
  nojob x := by obtain ⟨e, c⟩ := x; fin_cases e <;> cases c <;> rfl
  norec _ := rfl

theorem ex_ctl_deg : ∀ w, (exTopo.ends w).length ≤ 3 := by decide

theorem ex_ctl_rx : ∀ e c u, ∃ v, u ≤ v ∧ v < u + 20 ∧ exCtlEnv.rx v e c = true := fun _ _ u =>
  ⟨u + (20 - u % 20) % 20, by omega, by omega, by simp [exCtlEnv]; omega⟩

/-- The controller starts a chain: from slot 2, node 0 serves the PUSH of node 1 on edge 0. -/
theorem ex_ctl_chain : HJob ((netRunC exCtlEnv exCtlStart 2).es 0) false ⟨1, true, 0, 0⟩ :=
  ⟨false, by decide⟩

/-- The controller's chain has probed two ends by slot 7. -/
theorem ex_ctl_tried : ((netRunC exCtlEnv exCtlStart 7).crec (0 : Fin 4)).map
    (fun r => r.tried) = some [((2 : Fin 3), true), ((1 : Fin 3), true)] := by decide +kernel

set_option maxHeartbeats 1000000 in
/-- **`SeqOK` holds for the controller's chain with two probes**, checked on the controller run:
it probes end `true` of edge 1 (open in slots 3 to 5, closed at 6), then of edge 2 (open in slots 7
to 9, closed at 10), and is gone at slot 11. -/
theorem ex_ctl_seqOK : (ctlNet exCtlEnv exCtlStart ex_ctl_start).SeqOK (0 : Fin 3) false
    ⟨1, true, 0, 0⟩ 2 [⟨(1 : Fin 3), true, ⟨1, true, 0, 0⟩, 3⟩, ⟨(2 : Fin 3), true, ⟨1, true, 0, 0⟩, 7⟩] := by
  have ttl1 : (ctlNet exCtlEnv exCtlStart ex_ctl_start).ttl (1 : Fin 3) true ⟨1, true, 0, 0⟩ = 1 := by
    show ttlC exCtlEnv exCtlStart 1 true 1 = 1
    rw [ttlC_spec exCtlEnv exCtlStart (t := 3) (by decide +kernel)]; decide +kernel
  have ttl2 : (ctlNet exCtlEnv exCtlStart ex_ctl_start).ttl (2 : Fin 3) true ⟨1, true, 0, 0⟩ = 1 := by
    show ttlC exCtlEnv exCtlStart 2 true 1 = 1
    rw [ttlC_spec exCtlEnv exCtlStart (t := 7) (by decide +kernel)]; decide +kernel
  have ttl0 : (ctlNet exCtlEnv exCtlStart ex_ctl_start).ttl (0 : Fin 3) false ⟨1, true, 0, 0⟩ = 2 := by
    show ttlC exCtlEnv exCtlStart 0 false 1 = 2
    rw [ttlC_spec exCtlEnv exCtlStart (t := 1) (by decide +kernel)]; decide +kernel
  refine ⟨by decide, by decide, by rw [ctlNet_run]; decide +kernel, by rw [ttl1, ttl0], ?_⟩
  intro c hc hne hfirst
  change 3 ≤ c at hc
  rw [ctlNet_run] at hne
  rcases (by omega : c = 3 ∨ c = 4 ∨ c = 5 ∨ c = 6 ∨ 7 ≤ c) with rfl | rfl | rfl | rfl | h7
  · exact (hne (by decide +kernel)).elim
  · exact (hne (by decide +kernel)).elim
  · exact (hne (by decide +kernel)).elim
  · refine ⟨by decide, by decide, by rw [ctlNet_run]; decide +kernel, by rw [ttl2, ttl0], ?_⟩
    intro c hc hne hfirst
    change 7 ≤ c at hc
    rw [ctlNet_run] at hne
    rcases (by omega : c = 7 ∨ c = 8 ∨ c = 9 ∨ c = 10 ∨ 11 ≤ c) with rfl | rfl | rfl | rfl | h11
    · exact (hne (by decide +kernel)).elim
    · exact (hne (by decide +kernel)).elim
    · exact (hne (by decide +kernel)).elim
    · show ¬ HJob ((ctlNet exCtlEnv exCtlStart ex_ctl_start).run (0 : Fin 3) 11) false _
      rw [ctlNet_run]
      rintro ⟨b, hb⟩
      have : (((netRunC exCtlEnv exCtlStart 11).es (0 : Fin 3)).nd true).job = none := by
        decide +kernel
      rw [Bool.not_false, this] at hb; cases hb
    · have := hfirst 10 (by decide) (by omega)
      rw [ctlNet_run] at this
      exfalso; revert this; decide +kernel
  · have := hfirst 6 (by decide) (by omega)
    rw [ctlNet_run] at this
    exfalso; revert this; decide +kernel

/-- `ctl_chain_bound` applies to the controller's chain. -/
example : ∃ w, 2 ≤ w ∧ w ≤ 2 + ChainNet.dBound 3 20 2 ∧
    ¬ HJob ((netRunC exCtlEnv exCtlStart w).es (0 : Fin 3)) false ⟨1, true, 0, 0⟩ :=
  ctl_chain_bound exCtlEnv exCtlStart ex_ctl_start ex_ctl_deg ex_ctl_rx 2 0 false ⟨1, true, 0, 0⟩ 2
    (by rw [ttlC_spec exCtlEnv exCtlStart (t := 1) (by decide +kernel)]; decide +kernel)
    ex_ctl_chain

/-- So `ctl_seqOK` and `ctl_chain_bound` apply to a run with a chain. -/
example : ∃ s, s ≤ 2 ∧ ∃ probes : List (ctlNet exCtlEnv exCtlStart ex_ctl_start).Probe,
    probes.length + 1 ≤ 3 ∧
      (ctlNet exCtlEnv exCtlStart ex_ctl_start).SeqOK (0 : Fin 3) false ⟨1, true, 0, 0⟩ s probes := by
  obtain ⟨s, hs, -, probes, hl, hseq⟩ := ctl_seqOK exCtlEnv exCtlStart ex_ctl_start ex_ctl_deg
    (0 : Fin 3) false ⟨1, true, 0, 0⟩ 2 (by rw [ctlNet_run]; exact ex_ctl_chain)
  exact ⟨s, hs, probes, hl, hseq⟩

end SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ex_phase4
open SwarmInfer.CoverWeave.ExecFull in
#print axioms ex_phase4
open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ex_ctl_chain
open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ex_ctl_seqOK
