import SwarmInferLean.CoverWeave.ExecDecision
import SwarmInferLean.CoverWeave.BackboneCover

/-!
# CoverWeave, execution model of Phase 1b (protocol part of step 2 of C3, inventory E7)

Source: `CoverWeave_R1/sections/03-system.tex`, Algorithm `alg:connector`, procedure `Connector`
(lines 88 to 96), the barrier of line 55 ("a node leaves phase `i` only after the HELLOs it has
received show that every neighbour has reached phase `i` or later") and the MIS lists `𝓜(u)`
carried in HELLO (line 47). `04-formaleng.tex:62`, proof of Lemma `lem:conn`, step "at distance
two ... the candidate with the smallest key is promoted".

The model extends the Phase 1a model of `ExecDecision.lean` without changing it: the Phase 1a
part of the run is literally `run`, and alongside it every node keeps the MIS lists it last read
from its neighbours' HELLOs (`mrec v u w`: `v`'s record of `u` lists `w`), whether it has run
`Connector` (`done`), and whether it became CONNECTOR (`conn`). In slot `t + 1` an enabled node
that has decided and whose records show every neighbour decided (the barrier) runs `Connector`
once on its records. The HELLO it sends lists the neighbours it records as MIS.

Results.
* `connector_sound`: under every loss pattern and every enabling, once a node has run
  `Connector`, the local form of the Phase 1b rule holds at it: if it is adjacent to two distinct
  key-greedy nodes and its key is below that of every neighbour adjacent to both, it is MIS or
  CONNECTOR. This is the step the inventory found unargued in `lem:conn`: the barrier makes the
  records of `a` and `b` show MIS, and MIS lists are never wrong, only late, so the recorded rival
  set is a subset of the true one.
* `phase1bRule_of_allDone`: once every node has run `Connector`, `Phase1bRule` of
  `BackboneCover.lean` holds for the key-greedy set and every `C` containing the MIS and
  CONNECTOR nodes, so `gap2Bridged_of_phase1b` gives every MIS pair at distance two a common
  neighbour in `C` (`gap2Bridged_exec`).
* `allDone_of_lossFree`: from every reachable configuration, `n + 1` loss-free slots in which
  every node is enabled make every node run `Connector`.
-/

namespace SwarmInfer.CoverWeave.Exec

open SimpleGraph Finset

/-- The Phase 1b part of a configuration. -/
structure Ext (V : Type*) where
  mrec : V → V → V → Bool
  done : V → Bool
  conn : V → Bool

variable {V K : Type*} [Fintype V] [LinearOrder K]
variable (G : SimpleGraph V) [DecidableRel G.Adj] (key : V → K)

/-- The barrier at `v` for leaving phase 1a: every neighbour recorded as decided. -/
def barrier1b (c : Cfg V) (v : V) : Prop := ∀ u, G.Adj u v → c.rcd v u ≠ .undecided

/-- `Connector` at `v` (Algorithm `alg:connector`, lines 89 to 95, read off `bbcvc.py:939-954`):
an OUT node with two recorded MIS neighbours `a ≠ b` whose key is below that of every neighbour
whose recorded MIS list contains both becomes CONNECTOR. -/
def connRule (c : Cfg V) (e : Ext V) (v : V) : Prop :=
  c.st v = .out ∧ ∃ a b, a ≠ b ∧ G.Adj v a ∧ G.Adj v b ∧ c.rcd v a = .mis ∧ c.rcd v b = .mis ∧
    ∀ u, G.Adj v u → e.mrec v u a = true → e.mrec v u b = true → key v < key u

/-- The Phase 1b part of slot `t + 1`, computed from the configuration at the end of slot `t`.
The MIS list `u` sends in slot `t + 1` holds the neighbours `u` records as MIS
(`bbcvc.py:662-680`, `mis_nbrs`). -/
noncomputable def extStep (ok : LossPattern V) (en₂ : Enabling V) (t : ℕ) (c : Cfg V)
    (e : Ext V) : Ext V := by
  classical
  exact
  { mrec := fun v u w => if ok (t + 1) u v then decide (G.Adj w u ∧ c.rcd u w = .mis)
      else e.mrec v u w
    done := fun v => e.done v ||
      decide (en₂ (t + 1) v = true ∧ c.st v ≠ .undecided ∧ barrier1b G c v)
    conn := fun v => e.conn v || decide (en₂ (t + 1) v = true ∧ e.done v = false ∧
      c.st v ≠ .undecided ∧ barrier1b G c v ∧ connRule G key c e v) }

/-- The Phase 1b part of the run from the start of Phase 1a. `en` steps Phase 1a, `en₂` gates
`Connector` (so a barrier that must hold for two periods, as in `bbcvc.py:817-823`, is a
special enabling). -/
noncomputable def extRun (ok : LossPattern V) (en en₂ : Enabling V) : ℕ → Ext V
  | 0 => ⟨fun _ _ _ => false, fun _ => false, fun _ => false⟩
  | t + 1 => extStep G key ok en₂ t (run G key ok en init t) (extRun ok en en₂ t)

/-- The local Phase 1b rule at `v`, on the true MIS set (the key-greedy set). -/
def LocalRule (st : V → Dec) (conn : V → Bool) (v : V) : Prop :=
  ∀ a b, keyGreedy G key a → keyGreedy G key b → a ≠ b → G.Adj v a → G.Adj v b →
    (∀ u, G.Adj v u → G.Adj u a → G.Adj u b → key v < key u) → st v = .mis ∨ conn v = true

variable {G key}

/-- Recorded MIS lists are never wrong: a listed node is a neighbour of the lister and in the
key-greedy set. -/
theorem mrec_sound (ok : LossPattern V) (en en₂ : Enabling V) :
    ∀ t v u w, (extRun G key ok en en₂ t).mrec v u w = true → G.Adj w u ∧ keyGreedy G key w
  | 0, _, _, _, h => by simp [extRun] at h
  | t + 1, v, u, w, h => by
    simp only [extRun, extStep] at h
    split_ifs at h
    · simp only [decide_eq_true_eq] at h
      obtain ⟨hadj, hm⟩ := h
      refine ⟨hadj, (truth_eq_mis_iff w).1 ?_⟩
      rcases (run_sound_of (G := G) (key := key) (ok := ok) (en := en) sound_init t).2 u w with h' | ⟨h', -⟩
      · rw [hm] at h'; exact absurd h' (by decide)
      · exact h' ▸ hm
    · exact mrec_sound ok en en₂ t v u w h

theorem conn_mono (ok : LossPattern V) (en en₂ : Enabling V) (t : ℕ) (v : V)
    (h : (extRun G key ok en en₂ t).conn v = true) : (extRun G key ok en en₂ (t + 1)).conn v = true := by
  simp only [extRun, extStep, Bool.or_eq_true]; exact Or.inl h

/-- **Safety of `Connector` under every loss pattern.** Once `v` has run `Connector`, the local
Phase 1b rule holds at `v`, and it keeps holding.

Modelling choices: those of `prop_mischain_exec`; a record holds role, phase and MIS list of one
HELLO (`bootstrap.py:713-718`); `Connector` runs once (`bbcvc.py:953`, `phase = PH_COVER`); roles
after Phase 1b are not modelled (they only move from OUT into the cover, so membership in
`C ⊇ MIS ∪ CONNECTOR` persists).

Added hypotheses: none. -/
theorem connector_sound (ok : LossPattern V) (en en₂ : Enabling V) :
    ∀ t v, (extRun G key ok en en₂ t).done v = true →
      LocalRule G key (run G key ok en init t).st (extRun G key ok en en₂ t).conn v
  | 0, v, h => by simp [extRun] at h
  | t + 1, v, h => by
    intro a b ha hb hab hva hvb hriv
    have hcs := run_sound_of (G := G) (key := key) (ok := ok) (en := en) sound_init t
    simp only [extRun, extStep, Bool.or_eq_true, decide_eq_true_eq] at h
    rcases h with hold | ⟨hen, hdec, hbar⟩
    · rcases connector_sound ok en en₂ t v hold a b ha hb hab hva hvb hriv with h | h
      · left; rw [run_succ_of_ne (by rw [h]; decide), h]
      · right; exact conn_mono ok en en₂ t v h
    · by_cases hmis : (run G key ok en init t).st v = .mis
      · left; rw [run_succ_of_ne hdec, hmis]
      by_cases hd : (extRun G key ok en en₂ t).done v = true
      · rcases connector_sound ok en en₂ t v hd a b ha hb hab hva hvb hriv with h | h
        · exact absurd h hmis
        · right; exact conn_mono ok en en₂ t v h
      right
      have hrec : ∀ x, G.Adj x v → keyGreedy G key x → (run G key ok en init t).rcd v x = .mis := by
        intro x hx hgx
        rcases hcs.2 v x with h | ⟨h, -⟩
        · exact absurd h (hbar x hx)
        · exact h.trans ((truth_eq_mis_iff x).2 hgx)
      have hout : (run G key ok en init t).st v = .out := by
        rcases hcs.1 v with h | h
        · exact absurd h hdec
        · rw [h] at hmis ⊢; unfold truth at hmis ⊢; split_ifs at hmis ⊢ <;> simp_all
      have hrule : connRule G key (run G key ok en init t) (extRun G key ok en en₂ t) v := by
        refine ⟨hout, a, b, hab, hva, hvb, hrec a hva.symm ha, hrec b hvb.symm hb,
          fun u hvu hua hub => hriv u hvu ?_ ?_⟩
        · exact (mrec_sound ok en en₂ t v u a hua).1.symm
        · exact (mrec_sound ok en en₂ t v u b hub).1.symm
      simp only [extRun, extStep, Bool.or_eq_true, decide_eq_true_eq]
      exact Or.inr ⟨hen, by simpa using hd, hdec, hbar, hrule⟩

/-- **Phase 1b rule at the end of Phase 1b, every loss pattern.** Once every node has run
`Connector`, `Phase1bRule` of `BackboneCover.lean` holds for the key-greedy set and every `C`
that contains the MIS and CONNECTOR nodes. -/
theorem phase1bRule_of_allDone (ok : LossPattern V) (en en₂ : Enabling V) (t : ℕ)
    (hall : ∀ v, (extRun G key ok en en₂ t).done v = true) (C : Set V)
    (hC : ∀ v, (run G key ok en init t).st v = .mis ∨ (extRun G key ok en en₂ t).conn v = true →
      v ∈ C) :
    Phase1bRule G key {v | keyGreedy G key v} C := fun v a ha b hb hab hva hvb hriv =>
  hC v (connector_sound ok en en₂ t v (hall v) a b ha hb hab hva hvb hriv)

/-- **(D2) of `lem:conn` from the execution model.** With an injective key, once every node has
run `Connector`, every pair of key-greedy nodes at distance two has a common neighbour in `C`,
under every loss pattern, for every `C` containing the MIS and CONNECTOR nodes. -/
theorem gap2Bridged_exec (hkey : Function.Injective key) (ok : LossPattern V)
    (en en₂ : Enabling V) (t : ℕ) (hall : ∀ v, (extRun G key ok en en₂ t).done v = true)
    (C : Set V)
    (hC : ∀ v, (run G key ok en init t).st v = .mis ∨ (extRun G key ok en en₂ t).conn v = true →
      v ∈ C) :
    Gap2Bridged G {v | keyGreedy G key v} C :=
  gap2Bridged_of_phase1b hkey (phase1bRule_of_allDone ok en en₂ t hall C hC)

theorem done_mono (ok : LossPattern V) (en en₂ : Enabling V) (t : ℕ) (v : V)
    (h : (extRun G key ok en en₂ t).done v = true) : (extRun G key ok en en₂ (t + 1)).done v = true := by
  simp only [extRun, extStep, Bool.or_eq_true]; exact Or.inl h

/-- **Liveness of Phase 1b.** From every configuration reachable under any loss pattern, if every
frame of slots `t₀ + 1, …, t₀ + n` is delivered and every node is enabled for both rules in slots
`t₀ + 1, …, t₀ + n + 1`, every node has run `Connector` at the end of slot `t₀ + n + 1`. -/
theorem allDone_of_lossFree [Nonempty V] (ok : LossPattern V) (en en₂ : Enabling V) (t₀ : ℕ)
    (hok : ∀ s, t₀ < s → s ≤ t₀ + Fintype.card V → ∀ u v, ok s u v = true)
    (hen : ∀ s, t₀ < s → s ≤ t₀ + Fintype.card V + 1 → ∀ v, en s v = true)
    (hen₂ : ∀ s, t₀ < s → s ≤ t₀ + Fintype.card V + 1 → ∀ v, en₂ s v = true) (v : V) :
    (extRun G key ok en en₂ (t₀ + Fintype.card V + 1)).done v = true := by
  set n := Fintype.card V
  have hn : 0 < n := Fintype.card_pos
  have hdec : ∀ w, (run G key ok en init (t₀ + n)).st w ≠ .undecided := fun w =>
    decided_of_lossFree ok en init sound_init t₀ n (fun s h1 h2 u w _ => hok s h1 h2.le u w)
      (fun s h1 h2 => hen s h1 (by omega)) w (depth_lt_card G key w)
  have hbar : barrier1b G (run G key ok en init (t₀ + n)) v := by
    intro u _
    obtain ⟨n', hn'⟩ : ∃ n', n = n' + 1 := ⟨n - 1, by omega⟩
    have hrec : (run G key ok en init (t₀ + n)).rcd v u = (run G key ok en init (t₀ + n)).st u := by
      rw [hn', show t₀ + (n' + 1) = (t₀ + n') + 1 by omega]
      show (if ok (t₀ + n' + 1) u v then _ else _) = _
      rw [ite_eq_left (hok _ (by omega) (by omega) u v)]
      rfl
    rw [hrec]; exact hdec u
  simp only [extRun, extStep, Bool.or_eq_true, decide_eq_true_eq]
  exact Or.inr ⟨hen₂ _ (by omega) le_rfl v, hdec v, hbar⟩

end SwarmInfer.CoverWeave.Exec

open SwarmInfer.CoverWeave.Exec in
#print axioms mrec_sound
open SwarmInfer.CoverWeave.Exec in
#print axioms connector_sound
open SwarmInfer.CoverWeave.Exec in
#print axioms phase1bRule_of_allDone
open SwarmInfer.CoverWeave.Exec in
#print axioms gap2Bridged_exec
open SwarmInfer.CoverWeave.Exec in
#print axioms allDone_of_lossFree
