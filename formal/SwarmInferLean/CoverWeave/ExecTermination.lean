import SwarmInferLean.CoverWeave.ExecDecision
import SwarmInferLean.CoverWeave.Termination

/-!
# CoverWeave, C10 on the execution model of Phase 1a

`lem:term` (`CoverWeave_R1/sections/04-formaleng.tex:139`) derives termination with probability
one from Lemma `lem:lossless` (C9) and Assumption `asm:loss` (E8). `Termination.lean` proves the
probabilistic core for an abstract process with the two protocol facts as hypotheses. Here both
facts are discharged for the Phase 1a model of `ExecDecision.lean`: the process is the run of
that model under a random loss pattern, the absorbing set is "every node decided", the window
length is `W = n` and Lemma C9 is `phase1a_window`. What remains a hypothesis is only what is
about the probability space: Assumption `asm:loss` itself, measurability of its event, and that
the configuration at slot `t` is part of the history up to `t`.
-/

namespace SwarmInfer.CoverWeave.Exec

open MeasureTheory
open scoped ENNReal

variable {V K : Type*} [Fintype V] [LinearOrder K] (G : SimpleGraph V) [DecidableRel G.Adj]
  (key : V → K)
variable {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]

/-- The event of `asm:loss`: every frame sent in slots `t + 1, …, t + W` is delivered. -/
def windowGood (L : Ω → LossPattern V) (W t : ℕ) : Set Ω :=
  {ω | ∀ s, t < s → s ≤ t + W → ∀ u v, L ω s u v = true}

/-- The run of Phase 1a under the random loss pattern `L`, every node stepping in every slot. -/
def randomRun (L : Ω → LossPattern V) (t : ℕ) (ω : Ω) : Cfg V :=
  run G key (L ω) always init t

theorem allDecided_absorbing (L : Ω → LossPattern V) (t : ℕ) (ω : Ω)
    (h : randomRun G key L t ω ∈ {c | AllDecided c}) :
    randomRun G key L (t + 1) ω ∈ {c | AllDecided c} := fun v => by
  have hv := h v
  unfold randomRun at *
  rw [run_succ_of_ne hv]
  exact hv

theorem allDecided_of_window (L : Ω → LossPattern V) (t : ℕ) (ω : Ω)
    (hω : ω ∈ windowGood L (Fintype.card V) t) :
    randomRun G key L (t + Fintype.card V) ω ∈ {c | AllDecided c} :=
  (phase1a_window (L ω) always t (fun s h1 h2 u v => hω s h1 h2 u v) fun _ _ _ _ => rfl).1

/-- **Theorem `lem:term` (C10) for Phase 1a on the execution model.** Let the loss pattern be
random, `L : Ω → LossPattern V`, and let it satisfy Assumption `asm:loss` for `W = n` in the
conditional expectation form: for every slot `t`, almost surely the conditional probability given
the history `ℱ t` that every frame of slots `t + 1, …, t + n` is delivered is at least `ε > 0`.
Then Phase 1a ends (every node decided) with probability one, and the probability that it has not
ended by slot `j n` is at most `(1 − ε)^j`.

Modelling choices: those of `prop_mischain_exec`; the scheduler steps every node in every slot;
`ℱ` is any filtration and `μ` any probability measure.

Added hypotheses:
* `hadapt`: whether Phase 1a has ended at slot `t` is `ℱ t`-measurable. This holds when `ℱ t`
  contains the loss pattern up to slot `t`, which is what "history up to `t`" means; it is kept as
  a hypothesis because the paper fixes no σ-algebra.
* `hGood`: the event of `asm:loss` is measurable, so its probability is defined. -/
theorem phase1a_terminates (ℱ : Filtration ℕ m0) (L : Ω → LossPattern V) {ε : ℝ} (hε : 0 < ε)
    (hadapt : ∀ t, MeasurableSet[ℱ t] {ω | randomRun G key L t ω ∉ {c | AllDecided c}})
    (hGood : ∀ t, MeasurableSet (windowGood L (Fintype.card V) t))
    (hce : ∀ t, ∀ᵐ ω ∂μ, ε ≤
      (μ[(windowGood L (Fintype.card V) t).indicator (fun _ => (1 : ℝ)) | ℱ t]) ω) :
    μ {ω | ∀ t, randomRun G key L t ω ∉ {c | AllDecided c}} = 0 ∧
    ∀ j, μ {ω | ∀ t ≤ j * Fintype.card V, randomRun G key L t ω ∉ {c | AllDecided c}} ≤
      (1 - ENNReal.ofReal ε) ^ j := by
  have hwin := window_of_condExp ℱ (windowGood L (Fintype.card V)) hε.le hGood hce
  refine ⟨silent_ae ℱ (randomRun G key L) {c | AllDecided c} (Fintype.card V)
      (windowGood L (Fintype.card V)) (ENNReal.ofReal_pos.2 hε) hadapt hGood hwin
      (allDecided_of_window G key L) (allDecided_absorbing G key L), fun j => ?_⟩
  exact silent_tail_bound ℱ (randomRun G key L) {c | AllDecided c} (Fintype.card V)
    (windowGood L (Fintype.card V)) _ hadapt hGood hwin
    (allDecided_of_window G key L) (allDecided_absorbing G key L) j

end SwarmInfer.CoverWeave.Exec

open SwarmInfer.CoverWeave.Exec in
#print axioms phase1a_terminates
