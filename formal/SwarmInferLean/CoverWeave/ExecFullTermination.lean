import SwarmInferLean.CoverWeave.ExecSilence
import SwarmInferLean.CoverWeave.Termination

/-!
# CoverWeave, Theorem 4 (`lem:term`, inventory C10) from Lemma 4 for a synchronous protocol

`Termination.lean` proves the probabilistic core of Theorem 4 for an abstract process with two
protocol facts as hypotheses: Lemma 4 (`lem:lossless`) and "silence is never left". This file
instantiates the process with the run of an arbitrary synchronous message-passing protocol
(`SyncProtocol` of `ExecSilence.lean`) under a random loss pattern, discharges "silence is never
left" from the definition of a silent configuration (`sslot_of_silent`), and states Lemma 4 in the
paper's form, "from every reachable configuration, a run that delivers every frame of `W`
consecutive slots is silent at their end", as the one remaining protocol hypothesis.

What is not done here, and why: Lemma 4 itself for CoverWeave. The models of this project cover
Phase 1a (`phase1a_window`), Phase 1b (`allDone_of_lossFree`) and the final-state layers of
Theorem 3(b); Phases 0, 2 to 5, epochs and record expiry are not modelled as one protocol, and
`ExecFullTransfer.lean` shows that the transfer layer of Phase 4 does not even meet Theorem 3(b),
so a proof of Lemma 4 on the protocol as written would have to start from a repaired transfer
layer.
-/

namespace SwarmInfer.CoverWeave.Exec

open MeasureTheory
open scoped ENNReal

variable {V S M : Type*}

/-- The run of a synchronous protocol from `c₀` under the loss pattern `ok`: slot `t + 1`
delivers what `ok (t + 1)` lets through of the frames sent in slot `t`. -/
def srun (P : SyncProtocol V S M) (ok : LossPattern V) (c₀ : SCfg V S M) : ℕ → SCfg V S M
  | 0 => c₀
  | t + 1 => sslot P ok (t + 1) (srun P ok c₀ t)

/-- A run restarted at slot `t` is the run with the shifted loss pattern. -/
theorem srun_add (P : SyncProtocol V S M) (ok : LossPattern V) (c₀ : SCfg V S M) (t : ℕ) :
    ∀ s, srun P ok c₀ (t + s) = srun P (fun r => ok (t + r)) (srun P ok c₀ t) s
  | 0 => rfl
  | s + 1 => by
    show sslot P ok (t + s + 1) (srun P ok c₀ (t + s)) = _
    rw [srun_add P ok c₀ t s]
    rfl

/-- The configurations reachable from `c₀` under some loss pattern. -/
def Reachable (P : SyncProtocol V S M) (c₀ : SCfg V S M) (c : SCfg V S M) : Prop :=
  ∃ ok t, c = srun P ok c₀ t

/-- **Lemma 4 in the paper's form**: from every reachable configuration, a run that delivers
every frame of the `W` slots that follow is silent at their end. -/
def LossFreeWindow (P : SyncProtocol V S M) (c₀ : SCfg V S M) (W : ℕ) : Prop :=
  ∀ c, Reachable P c₀ c → ∀ ok : LossPattern V, (∀ s, 1 ≤ s → s ≤ W → ∀ u v, ok s u v = true) →
    Silent P (srun P ok c W)

variable {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]

/-- The event of `asm:loss` for the window after slot `t`. -/
def goodWindow (L : Ω → LossPattern V) (W t : ℕ) : Set Ω :=
  {ω | ∀ s, t < s → s ≤ t + W → ∀ u v, L ω s u v = true}

/-- **Theorem 4 (`lem:term`) for a synchronous protocol, given Lemma 4.** Let the loss pattern
be random, `L : Ω → LossPattern V`, satisfying Assumption `asm:loss` for the window length `W` of
Lemma 4 in conditional expectation form: for every slot `t`, almost surely, the conditional
probability given the history `ℱ t` that every frame of slots `t + 1, …, t + W` is delivered is
at least `ε > 0`. If Lemma 4 holds with this `W`, the run becomes silent with probability one and
`Pr[T_sil > jW] ≤ (1 − ε)^j` for every `j`.

Modelling choices: synchronous slots, at most one frame per ordered pair per slot, the protocol
`P` arbitrary; "silent" is `Silent P` (no frame in flight, a node that receives nothing changes
nothing and sends nothing, which for CoverWeave needs closed DONE nodes not to beacon,
`ExecSilence.lean`).

Added hypotheses:
* `hlem4`: Lemma 4. It is the protocol fact this theorem rests on and is not proved for CoverWeave.
* `hadapt`, `hGood`: measurability of "not silent at slot `t`" for the history `ℱ t` and of the
  window event, as in `phase1a_terminates`; the paper fixes no σ-algebra.

"Silence is never left" is not a hypothesis: it follows from `Silent` (`sslot_of_silent`). -/
theorem term_of_lossFreeWindow (P : SyncProtocol V S M) (c₀ : SCfg V S M) {W : ℕ}
    (hlem4 : LossFreeWindow P c₀ W) (ℱ : Filtration ℕ m0) (L : Ω → LossPattern V) {ε : ℝ}
    (hε : 0 < ε)
    (hadapt : ∀ t, MeasurableSet[ℱ t] {ω | srun P (L ω) c₀ t ∉ {c | Silent P c}})
    (hGood : ∀ t, MeasurableSet (goodWindow L W t))
    (hce : ∀ t, ∀ᵐ ω ∂μ, ε ≤ (μ[(goodWindow L W t).indicator (fun _ => (1 : ℝ)) | ℱ t]) ω) :
    μ {ω | ∀ t, srun P (L ω) c₀ t ∉ {c | Silent P c}} = 0 ∧
    ∀ j, μ {ω | ∀ t ≤ j * W, srun P (L ω) c₀ t ∉ {c | Silent P c}} ≤ (1 - ENNReal.ofReal ε) ^ j := by
  set X : ℕ → Ω → SCfg V S M := fun t ω => srun P (L ω) c₀ t
  have hwin := window_of_condExp ℱ (goodWindow L W) hε.le hGood hce
  have hlossless : ∀ t ω, ω ∈ goodWindow L W t → X (t + W) ω ∈ {c | Silent P c} := by
    intro t ω hω
    show Silent P (srun P (L ω) c₀ (t + W))
    rw [srun_add]
    exact hlem4 _ ⟨L ω, t, rfl⟩ _ fun s h1 h2 u v => hω (t + s) (by omega) (by omega) u v
  have habs : ∀ t ω, X t ω ∈ {c | Silent P c} → X (t + 1) ω ∈ {c | Silent P c} :=
    fun t ω h => silent_never_left P (L ω) (t + 1) h
  exact ⟨silent_ae ℱ X _ W (goodWindow L W) (ENNReal.ofReal_pos.2 hε) hadapt hGood hwin
      hlossless habs,
    silent_tail_bound ℱ X _ W (goodWindow L W) _ hadapt hGood hwin hlossless habs⟩

/-- Non-vacuity of `LossFreeWindow`: the protocol in which no node ever sends meets it with
`W = 0`. -/
example : LossFreeWindow (V := Unit) (S := Unit) (M := Unit) ⟨fun _ s _ => (s, fun _ => none)⟩
    ⟨fun _ => (), fun _ _ => none⟩ 0 := by
  rintro c ⟨ok, t, rfl⟩ ok' -
  refine ⟨fun u v => ?_, fun v => rfl⟩
  cases t <;> rfl

end SwarmInfer.CoverWeave.Exec

open SwarmInfer.CoverWeave.Exec in
#print axioms term_of_lossFreeWindow
