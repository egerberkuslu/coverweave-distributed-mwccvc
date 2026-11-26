import SwarmInferLean.CoverWeave.ExecDecision

/-!
# CoverWeave: "silence is never left" in a synchronous message-passing model (C9, C10, E7)

`lem:term` (`CoverWeave_R1/sections/04-formaleng.tex:144`) uses "silence is never left", and
`Termination.lean` takes it as the hypothesis `habs`. A configuration is silent when every node is
DONE with a closed barrier, no rule can fire and no frame is in flight or unprocessed
(`04-formaleng.tex:39`). This file states the property in a general synchronous model, where a
node's step maps its state and the frames it received in the slot to a new state and the frame it
sends to each node, and proves that a silent configuration is a fixed point of every slot under
every loss pattern.

The content is the second clause of `Silent`: a node in a silent configuration that receives
nothing changes nothing and sends nothing. For CoverWeave this needs that a DONE node with a
closed barrier sends no HELLO (inventory C10, `BULGULAR.md` item 10). The code satisfies it:
`_maybe_hello` returns without broadcasting when the node is DONE, its barrier is closed, its
state did not change and no echo is owed (`bbcvc.py:1557-1590`), and a closed node does not
expire records (`_expire`, `bbcvc.py:1631`), so its timers change nothing. The text says only
that an open DONE node beacons once per stale window (Algorithm `alg:quiescence`, line 197), not
that a closed one stops. `beaconing_never_silent` shows that without this clause no
configuration is silent at all.
-/

namespace SwarmInfer.CoverWeave.Exec

variable {V S M : Type*}

/-- A synchronous protocol: node `v` in state `s` that received `inbox u` from each `u` moves to
the first component and sends the second component's frame to each node (`none`: no frame). -/
structure SyncProtocol (V S M : Type*) where
  δ : V → S → (V → Option M) → S × (V → Option M)

/-- A configuration: states and the frames sent in the last slot (`inflight u v`). -/
structure SCfg (V S M : Type*) where
  st : V → S
  inflight : V → V → Option M

/-- One slot: the frames of the previous slot that the loss pattern delivers form the inboxes,
then every node steps. -/
def sslot (P : SyncProtocol V S M) (ok : LossPattern V) (t : ℕ) (c : SCfg V S M) :
    SCfg V S M :=
  ⟨fun v => (P.δ v (c.st v) fun u => if ok t u v then c.inflight u v else none).1,
    fun u v => (P.δ u (c.st u) fun w => if ok t w u then c.inflight w u else none).2 v⟩

/-- Silent configuration: no frame in flight, and every node that receives nothing keeps its
state and sends nothing ("no rule can fire", and a closed DONE node does not beacon). -/
def Silent (P : SyncProtocol V S M) (c : SCfg V S M) : Prop :=
  (∀ u v, c.inflight u v = none) ∧ ∀ v, P.δ v (c.st v) (fun _ => none) = (c.st v, fun _ => none)

/-- **Silence is never left**, under every loss pattern: a silent configuration is a fixed point
of every slot. This is the hypothesis `habs` of `silent_tail_bound` and `silent_ae`.

Modelling choices: synchronous slots, at most one frame per ordered pair of nodes per slot,
the loss pattern decides delivery; the protocol is arbitrary.

Added hypotheses: none; the clause about sending is part of `Silent`. -/
theorem sslot_of_silent (P : SyncProtocol V S M) (ok : LossPattern V) (t : ℕ) {c : SCfg V S M}
    (h : Silent P c) : sslot P ok t c = c := by
  have hin : ∀ v, (fun u => if ok t u v then c.inflight u v else none) = fun _ => none :=
    fun v => funext fun u => by split_ifs <;> simp [h.1 u v]
  cases c with
  | mk st inflight =>
    simp only [sslot, SCfg.mk.injEq]
    refine ⟨funext fun v => ?_, funext fun u => funext fun v => ?_⟩
    · rw [hin v, h.2 v]
    · rw [hin u, h.2 u]; exact (h.1 u v).symm

theorem silent_never_left (P : SyncProtocol V S M) (ok : LossPattern V) (t : ℕ)
    {c : SCfg V S M} (h : Silent P c) : Silent P (sslot P ok t c) := by
  rw [sslot_of_silent P ok t h]; exact h

/-- Without the clause, silence is impossible: if every node sends a HELLO to some node in every
slot, whatever it received, no configuration is silent. -/
theorem beaconing_never_silent (P : SyncProtocol V S M)
    (hbeacon : ∀ v s inbox, ∃ w, (P.δ v s inbox).2 w ≠ none) [Nonempty V] (c : SCfg V S M) :
    ¬ Silent P c := by
  intro h
  obtain ⟨v⟩ := ‹Nonempty V›
  obtain ⟨w, hw⟩ := hbeacon v (c.st v) fun _ => none
  rw [h.2 v] at hw
  exact hw rfl

end SwarmInfer.CoverWeave.Exec

open SwarmInfer.CoverWeave.Exec in
#print axioms sslot_of_silent
open SwarmInfer.CoverWeave.Exec in
#print axioms silent_never_left
open SwarmInfer.CoverWeave.Exec in
#print axioms beaconing_never_silent
