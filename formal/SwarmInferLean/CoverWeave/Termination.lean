import Mathlib

/-!
# CoverWeave: termination under a lossy channel (inventory C10, E8)

`lem:term` (`CoverWeave_R1/sections/04-formaleng.tex:139`), Theorem (Termination under a lossy
channel): under the hypotheses of Lemma `lem:lossless` (C9) and Assumption `asm:loss` (the window
condition), a run of the MIS arm becomes silent with probability one, and its hitting time
satisfies `Pr[T_sil > jW] ≤ (1 − ε_W)^j` for every `j ≥ 1`.

This file proves the probabilistic core, the absorption argument of the proof, on an arbitrary
probability space. The run is a process `X : ℕ → Ω → Cfg` (the configuration after slot `t`), the
history up to slot `t` is a filtration `ℱ t`, the silent configurations form a set `Sil`, and
`Good t` is the event that every frame sent in slots `t+1, …, t+W` is delivered. The two
ingredients that come from the protocol are hypotheses: Lemma C9 (`hlossless`: a loss-free
window of `W` slots ends silent) and "silence is never left" (`habs`).

The window condition is used in its elementary form `ε μ(H) ≤ μ(H ∩ Good t)` for every history
event `H ∈ ℱ t` (`silent_tail_bound`). `window_of_condExp` derives this form from the conditional
expectation form `μ[1_{Good t} | ℱ t] ≥ ε` a.e., which is how `asm:loss` reads in measure theory
("for every history, delivered with conditional probability at least `ε_W`").
-/

namespace SwarmInfer.CoverWeave

open MeasureTheory Filter Topology
open scoped ENNReal

variable {Ω Cfg : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]

/-- If silence is never left, it persists over any number of slots. -/
theorem silent_persist {X : ℕ → Ω → Cfg} {Sil : Set Cfg}
    (habs : ∀ t ω, X t ω ∈ Sil → X (t + 1) ω ∈ Sil) {t : ℕ} {ω : Ω} (h : X t ω ∈ Sil) :
    ∀ s, X (t + s) ω ∈ Sil
  | 0 => h
  | s + 1 => habs _ ω (silent_persist habs h s)

/-- One block: the probability of not being silent at slot `(j+1)W` is at most `1 − ε` times that
of not being silent at slot `jW`. -/
theorem not_silent_step (ℱ : Filtration ℕ m0) (X : ℕ → Ω → Cfg) (Sil : Set Cfg) (W : ℕ)
    (Good : ℕ → Set Ω) (ε : ℝ≥0∞)
    (hadapt : ∀ t, MeasurableSet[ℱ t] {ω | X t ω ∉ Sil})
    (hGood : ∀ t, MeasurableSet (Good t))
    (hwin : ∀ t H, MeasurableSet[ℱ t] H → ε * μ H ≤ μ (H ∩ Good t))
    (hlossless : ∀ t ω, ω ∈ Good t → X (t + W) ω ∈ Sil)
    (habs : ∀ t ω, X t ω ∈ Sil → X (t + 1) ω ∈ Sil) (j : ℕ) :
    μ {ω | X ((j + 1) * W) ω ∉ Sil} ≤ (1 - ε) * μ {ω | X (j * W) ω ∉ Sil} := by
  set N := {ω | X (j * W) ω ∉ Sil}
  have hsub : {ω | X ((j + 1) * W) ω ∉ Sil} ⊆ N \ Good (j * W) := by
    intro ω hω
    simp only [Set.mem_ofPred_eq, Nat.succ_mul] at hω
    refine ⟨fun hS => hω (silent_persist habs hS W), fun hG => hω (hlossless _ ω hG)⟩
  have hsplit := measure_inter_add_sdiff (μ := μ) N (hGood (j * W))
  have hw := hwin (j * W) N (hadapt _)
  have hfin : μ N ≠ ∞ := measure_ne_top μ N
  calc μ {ω | X ((j + 1) * W) ω ∉ Sil} ≤ μ (N \ Good (j * W)) := measure_mono hsub
    _ ≤ μ N - ε * μ N := by
        refine ENNReal.le_sub_of_add_le_right (ne_top_of_le_ne_top (measure_ne_top μ _) hw) ?_
        calc μ (N \ Good (j * W)) + ε * μ N ≤ μ (N \ Good (j * W)) + μ (N ∩ Good (j * W)) :=
              add_le_add_right hw _
          _ = μ N := by rw [add_comm, hsplit]
    _ = (1 - ε) * μ N := by rw [ENNReal.sub_mul fun _ _ => hfin, one_mul]

/-- **Theorem (Termination under a lossy channel)**, tail bound, `lem:term`, inventory C10.
The probability that the run is not silent at any slot up to `jW`, which is `Pr[T_sil > jW]` for
the hitting time `T_sil = min {t | X t ∈ Sil}`, is at most `(1 − ε)^j`, for every `j`
(the paper states `j ≥ 1`; `j = 0` holds trivially).

Modelling choices:
* `Ω` is any probability space, `X t` the configuration after slot `t`, `ℱ t` the history up to
  slot `t` (a `Filtration`), `Sil` the silent configurations, `Good t` the event that all frames
  of slots `t+1, …, t+W` are delivered. Probabilities are in `ℝ≥0∞`.
* `Pr[T_sil > jW]` is the event `{∀ t ≤ jW, X t ∉ Sil}`, so no hitting-time random variable is
  defined.
* `hwin` is Assumption `asm:loss` in elementary form, for every history event `H ∈ ℱ t`; it
  follows from the conditional expectation form by `window_of_condExp`.
* `hlossless` is Lemma `lem:lossless` (C9), `habs` is "silence is never left", and `hadapt`
  says that whether the run is silent at slot `t` is part of the history up to `t`. These come
  from the execution model (inventory E7) and stay on paper. As the inventory notes, `habs`
  needs that a silent configuration sends no frames, so closed DONE nodes must stop beaconing;
  the paper should state this as a property of the model, and `W` and `ε` must be those of C9.

Added hypotheses: `hGood`, the loss-free event is measurable (needed for its probability to be
meaningful). -/
theorem silent_tail_bound (ℱ : Filtration ℕ m0) (X : ℕ → Ω → Cfg) (Sil : Set Cfg) (W : ℕ)
    (Good : ℕ → Set Ω) (ε : ℝ≥0∞)
    (hadapt : ∀ t, MeasurableSet[ℱ t] {ω | X t ω ∉ Sil})
    (hGood : ∀ t, MeasurableSet (Good t))
    (hwin : ∀ t H, MeasurableSet[ℱ t] H → ε * μ H ≤ μ (H ∩ Good t))
    (hlossless : ∀ t ω, ω ∈ Good t → X (t + W) ω ∈ Sil)
    (habs : ∀ t ω, X t ω ∈ Sil → X (t + 1) ω ∈ Sil) (j : ℕ) :
    μ {ω | ∀ t ≤ j * W, X t ω ∉ Sil} ≤ (1 - ε) ^ j := by
  have hN : ∀ j, μ {ω | X (j * W) ω ∉ Sil} ≤ (1 - ε) ^ j := by
    intro j
    induction j with
    | zero => simpa using prob_le_one
    | succ j ih =>
      calc μ {ω | X ((j + 1) * W) ω ∉ Sil} ≤ (1 - ε) * μ {ω | X (j * W) ω ∉ Sil} :=
            not_silent_step ℱ X Sil W Good ε hadapt hGood hwin hlossless habs j
        _ ≤ (1 - ε) * (1 - ε) ^ j := by gcongr
        _ = (1 - ε) ^ (j + 1) := (pow_succ' _ _).symm
  exact (measure_mono (s := {ω | ∀ t ≤ j * W, X t ω ∉ Sil}) (t := {ω | X (j * W) ω ∉ Sil}) fun ω hω => hω (j * W) le_rfl).trans (hN j)

/-- **Theorem (Termination under a lossy channel)**, almost sure silence, `lem:term`, inventory
C10. If moreover `ε > 0`, the run becomes silent with probability one. Same modelling choices as
`silent_tail_bound`. -/
theorem silent_ae (ℱ : Filtration ℕ m0) (X : ℕ → Ω → Cfg) (Sil : Set Cfg) (W : ℕ)
    (Good : ℕ → Set Ω) {ε : ℝ≥0∞} (hε : 0 < ε)
    (hadapt : ∀ t, MeasurableSet[ℱ t] {ω | X t ω ∉ Sil})
    (hGood : ∀ t, MeasurableSet (Good t))
    (hwin : ∀ t H, MeasurableSet[ℱ t] H → ε * μ H ≤ μ (H ∩ Good t))
    (hlossless : ∀ t ω, ω ∈ Good t → X (t + W) ω ∈ Sil)
    (habs : ∀ t ω, X t ω ∈ Sil → X (t + 1) ω ∈ Sil) :
    μ {ω | ∀ t, X t ω ∉ Sil} = 0 := by
  have hlt : 1 - ε < 1 := ENNReal.sub_lt_self ENNReal.one_ne_top one_ne_zero hε.ne'
  refine le_antisymm (ge_of_tendsto' (ENNReal.tendsto_pow_atTop_nhds_zero_of_lt_one hlt)
    fun j => ?_) zero_le
  exact (measure_mono (s := {ω | ∀ t, X t ω ∉ Sil})
    (t := {ω | ∀ t ≤ j * W, X t ω ∉ Sil}) fun ω hω t _ => hω t).trans
    (silent_tail_bound ℱ X Sil W Good ε hadapt hGood hwin hlossless habs j)

#print axioms silent_tail_bound
#print axioms silent_ae

/-- **Assumption `asm:loss` in conditional expectation form implies its elementary form.** If
`μ[1_{Good t} | ℱ t] ≥ ε` almost surely, then `ε μ(H) ≤ μ(H ∩ Good t)` for every `H ∈ ℱ t`. This
is the step from "for every history, delivered with conditional probability at least `ε`" to the
hypothesis `hwin` of `silent_tail_bound`, so together they prove the probabilistic part of
`lem:term` from the assumption as the paper states it. -/
theorem window_of_condExp (ℱ : Filtration ℕ m0) (Good : ℕ → Set Ω) {ε : ℝ} (hε : 0 ≤ ε)
    (hGood : ∀ t, MeasurableSet (Good t))
    (hce : ∀ t, ∀ᵐ ω ∂μ, ε ≤ (μ[(Good t).indicator (fun _ => (1 : ℝ)) | ℱ t]) ω)
    (t : ℕ) (H : Set Ω) (hH : MeasurableSet[ℱ t] H) :
    ENNReal.ofReal ε * μ H ≤ μ (H ∩ Good t) := by
  have hH0 : MeasurableSet H := ℱ.le t H hH
  have hint : Integrable ((Good t).indicator (fun _ => (1 : ℝ))) μ :=
    (integrable_const (1 : ℝ)).indicator (hGood t)
  have key : ε * μ.real H ≤ μ.real (H ∩ Good t) := by
    calc ε * μ.real H = ∫ _ in H, ε ∂μ := by simp [mul_comm]
      _ ≤ ∫ ω in H, (μ[(Good t).indicator (fun _ => (1 : ℝ)) | ℱ t]) ω ∂μ :=
          setIntegral_mono_ae (integrableOn_const (measure_ne_top _ _))
            integrable_condExp.integrableOn (hce t)
      _ = ∫ ω in H, (Good t).indicator (fun _ => (1 : ℝ)) ω ∂μ :=
          setIntegral_condExp (ℱ.le t) hint hH
      _ = μ.real (H ∩ Good t) := by
          rw [integral_indicator_const _ (hGood t), measureReal_restrict_apply (hGood t),
            Set.inter_comm, smul_eq_mul, mul_one]
  have := ENNReal.ofReal_le_ofReal key
  rwa [ENNReal.ofReal_mul hε, ofReal_measureReal (measure_ne_top _ _),
    ofReal_measureReal (measure_ne_top _ _)] at this

#print axioms window_of_condExp

/-- Non-vacuity: all hypotheses of `silent_tail_bound` hold together, with `ε = 1`, for the run on
the one-point space that is silent from slot `W` on. -/
example (W : ℕ) : (Measure.dirac ()) {_ω : Unit | ∀ t ≤ 1 * W, decide (W ≤ t) ∉ ({true} : Set Bool)}
    ≤ (1 - 1) ^ 1 :=
  silent_tail_bound (μ := Measure.dirac ()) ⟨fun _ => inferInstance, monotone_const, fun _ => le_rfl⟩
    (fun t (_ : Unit) => decide (W ≤ t)) {true} W (fun _ => Set.univ) 1
    (fun _ => MeasurableSet.of_discrete) (fun _ => MeasurableSet.univ)
    (fun _ H _ => by simp) (fun t _ _ => by simp) (fun t _ h => by simp at h ⊢; omega) 1

end SwarmInfer.CoverWeave
