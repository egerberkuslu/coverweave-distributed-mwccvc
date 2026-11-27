import SwarmInferLean.CoverWeave.Basic

/-!
# CoverWeave, Theorem 3(b) (`thm:cap` part (b), inventory C5(b)): the final-state layer

Source: `CoverWeave_R1/sections/04-formaleng.tex:77-87`, Theorem `thm:cap` part (b) and its proof;
`03-system.tex:148-169` (Algorithm `alg:ownership`), `03-system.tex:183-204` (Algorithm
`alg:quiescence`).

Theorem 3(b) is a statement about a silent configuration. Its proof has three ingredients, and the
model is split along them:

1. Ownership is a function of the node state. The code re-derives it in every step
   (`_recompute_owned`, `bbcvc.py:1123-1142`): a node outside the cover owns nothing; a node of
   the cover owns the edge to a neighbour it records as OUT (forced); otherwise a decision settled
   by a transfer (`_explicit`) wins; otherwise the message-free start of Algorithm `alg:ownership`
   on advertised budgets decides (`_default_owner`, `bbcvc.py:1106-1121`). In a silent
   configuration no rule can fire, so the stored ownership equals this derived one. This file
   proves the final-state theorem `owner_exactly_one` from three properties of the silent
   configuration: records equal what their node advertises (`RecordsAccurate`), the explicit
   decisions of the two ends of a flexible edge are complementary (`ExplicitConsistent`), and no
   edge has both ends outside the cover (Theorem `lem:cover`).
2. The load bound comes from Phase 5: a node turns QUIET only when settled, a change of its owned
   edges sends it back to Phase 4, and the flag Unresolved is cleared only once the load is at
   most `k` (`QuietInv`, `quietInv_step`, `load_le_of_silent`).
3. `ExplicitConsistent` is the content of the transfer protocol and is the subject of
   `ExecFullTransfer.lean`; `RecordsAccurate` is the content of the confirmation echo and is the
   subject of `ExecFullEcho.lean`. `ExecFullCap.lean` assembles the three.
-/

namespace SwarmInfer.CoverWeave.ExecFull

open Finset

variable {V K : Type*} [Fintype V] [DecidableEq V] [LinearOrder K]

/-- The ownership-relevant part of a node state in the final epoch. `recC v u` and `recF v u` are
the cover role and the forced load that `v` last read from `u`'s HELLO, `advF v` is the forced load
that `v` advertised last (`_adv_forced`), `expl v u` is `v`'s settled decision for the edge to `u`
(`_explicit`, `none` when no transfer of that edge touched `v`). -/
structure OwnCfg (V : Type*) where
  inC : V → Bool
  advF : V → ℕ
  recC : V → V → Bool
  recF : V → V → ℕ
  expl : V → V → Option Bool
  unres : V → Bool
  infeas : V → Bool

variable (G : SimpleGraph V) [DecidableRel G.Adj] (k : ℕ) (key : V → K)

/-- The message-free start of Algorithm `alg:ownership` at `v` for the edge to `u`: `v` takes it
iff `cap(v) > cap(u)`, ties to the smaller key, with `cap = k − F` on advertised values
(`bbcvc.py:1117-1121`, Python integers, so `cap` may be negative). -/
def dflt (c : OwnCfg V) (v u : V) : Prop :=
  (k : ℤ) - c.advF u < (k : ℤ) - c.advF v ∨ ((k : ℤ) - c.advF v = (k : ℤ) - c.advF u ∧ key v < key u)

/-- The same rule as `v` evaluates it, on its record of `u`. -/
def dfltRec (c : OwnCfg V) (v u : V) : Prop :=
  (k : ℤ) - c.recF v u < (k : ℤ) - c.advF v ∨
    ((k : ℤ) - c.advF v = (k : ℤ) - c.recF v u ∧ key v < key u)

/-- `v` owns the edge to `u` (`_recompute_owned`, `bbcvc.py:1123-1142`). -/
def Owns (c : OwnCfg V) (v u : V) : Prop :=
  c.inC v = true ∧
    (c.recC v u = false ∨ c.expl v u = some true ∨ (c.expl v u = none ∧ dfltRec k key c v u))

/-- Records equal what their node advertises: `v`'s record of a neighbour `u` shows `u`'s role and
its advertised forced load. -/
def RecordsAccurate (c : OwnCfg V) : Prop :=
  ∀ v u, G.Adj v u → c.recC v u = c.inC u ∧ c.recF v u = c.advF u

/-- The two settled decisions of one edge are complementary or both absent. -/
def ConsistentPair (a b : Option Bool) : Prop :=
  (a = none ∧ b = none) ∨ (a = some true ∧ b = some false) ∨ (a = some false ∧ b = some true)

/-- Every flexible edge carries a consistent pair of settled decisions. -/
def ExplicitConsistent (c : OwnCfg V) : Prop :=
  ∀ v u, G.Adj v u → c.inC v = true → c.inC u = true → ConsistentPair (c.expl v u) (c.expl u v)

/-- No edge has both ends outside the cover (Theorem `lem:cover`). -/
def CoverOK (c : OwnCfg V) : Prop := ∀ v u, G.Adj v u → c.inC v = true ∨ c.inC u = true

variable {G k key}

omit [Fintype V] [DecidableEq V] in
theorem dflt_antisymm (hkey : Function.Injective key) (c : OwnCfg V) {v u : V} (hvu : v ≠ u) :
    dflt k key c v u ↔ ¬ dflt k key c u v := by
  unfold dflt
  have hk : key v ≠ key u := fun h => hvu (hkey h)
  generalize (k : ℤ) - c.advF v = a
  generalize (k : ℤ) - c.advF u = b
  rcases lt_trichotomy a b with h | rfl | h
  · simp [h, h.ne, not_lt.2 h.le]
  · rcases lt_or_gt_of_ne hk with h' | h'
    · simp [h', not_lt.2 h'.le]
    · simp [h', not_lt.2 h'.le]
  · simp only [h, h.ne', not_lt.2 h.le, false_and, or_false, true_iff]
    rintro (h1 | ⟨h1, -⟩) <;> omega

omit [Fintype V] [DecidableEq V] [DecidableRel G.Adj] in
/-- **Final-state ownership.** In a configuration where records are accurate, settled decisions are
consistent and the cover covers every edge, every edge `{v, u}` of `Ĝ*` has exactly one owner, and
that owner is an endpoint in the cover.

Modelling choices:
* `Ĝ*` is a `SimpleGraph` on a `Fintype` (the final epoch); a node's neighbours in its rules are
  its neighbours in `Ĝ*` (`_nbrs_active` on the frozen view).
* Ownership is the re-derived one (`_recompute_owned`); in a silent configuration no rule can
  fire, so the stored `owned` equals it.
* `cap = k − F` is an integer, as in Python; the key is injective (`def:key`).

Added hypotheses: none beyond the three named properties, which are the subject of
`ExecFullEcho.lean` (records), `ExecFullTransfer.lean` (settled decisions) and Theorem
`lem:cover` (cover). -/
theorem owner_exactly_one (hkey : Function.Injective key) {c : OwnCfg V}
    (hR : RecordsAccurate G c) (hE : ExplicitConsistent G c) (hC : CoverOK G c) {v u : V}
    (h : G.Adj v u) :
    (Owns k key c v u ↔ ¬ Owns k key c u v) ∧ (Owns k key c v u → c.inC v = true) := by
  refine ⟨?_, fun h' => h'.1⟩
  obtain ⟨hvC, hvF⟩ := hR v u h
  obtain ⟨huC, huF⟩ := hR u v h.symm
  have hd : dfltRec k key c v u ↔ ¬ dfltRec k key c u v := by
    have := dflt_antisymm (k := k) hkey c h.ne
    unfold dflt at this; unfold dfltRec; rw [hvF, huF]; exact this
  unfold Owns
  rw [hvC, huC]
  cases hv : c.inC v <;> cases hu : c.inC u
  · exact absurd (hC v u h) (by simp [hv, hu])
  · simp
  · simp
  · rcases hE v u h hv hu with ⟨h1, h2⟩ | ⟨h1, h2⟩ | ⟨h1, h2⟩ <;> simp [h1, h2, hd]

/-! ### The load bound: Phase 5 -/

/-- The Phase 4/5 phase of a node: still negotiating (`own`), `quiet` or `done`. -/
inductive Ph
  | own
  | quiet
  | done
  deriving DecidableEq

/-- The Phase 5 part of a node: its phase, its load, and its two flags. -/
structure Q5 where
  ph : Ph
  load : ℕ
  unres : Bool
  infeas : Bool

/-- The steps of Phase 4 and 5 that touch these fields (`_rule_ownership`, `bbcvc.py:1144-1194`;
`_fix_overload`, `bbcvc.py:1356-1364`; `_quiescence`, `bbcvc.py:1392-1425`; `_certify`,
`bbcvc.py:1791-1796`). The load and `infeasible` are part of the fingerprint
(`bbcvc.py:1367-1374`), so changing them leaves QUIET or DONE. -/
inductive Q5Step (k : ℕ) : Q5 → Q5 → Prop
  /-- the owned edges change (any new load); the fingerprint changed, so QUIET and DONE are left -/
  | change (q : Q5) (l : ℕ) : Q5Step k q ⟨.own, l, q.unres, q.infeas⟩
  /-- the network certifies infeasibility; `infeasible` is in the fingerprint -/
  | certify (q : Q5) : Q5Step k q ⟨.own, q.load, q.unres, true⟩
  /-- local repair gives up, only on an overloaded node (`bbcvc.py:1182-1188`, `1360-1364`) -/
  | giveUp (q : Q5) (h : k < q.load) : Q5Step k q { q with unres := true }
  /-- the flag describes the present: cleared once the load is at most `k` (`bbcvc.py:1158`) -/
  | recover (q : Q5) (h : q.load ≤ k) : Q5Step k q { q with unres := false }
  /-- QUIET once settled: `ℓ(v) ≤ k` or infeasible or Unresolved (line 193 of `alg:quiescence`) -/
  | quiet (q : Q5) (h : q.ph = .own) (hs : q.load ≤ k ∨ q.infeas = true ∨ q.unres = true) :
      Q5Step k q { q with ph := .quiet }
  /-- the barrier moves a QUIET node to DONE and back (lines 196 to 197) -/
  | done (q : Q5) (h : q.ph = .quiet) : Q5Step k q { q with ph := .done }
  | undone (q : Q5) (h : q.ph = .done) : Q5Step k q { q with ph := .quiet }

/-- The invariant of Phase 5: a QUIET or DONE node is settled. -/
def QuietInv (k : ℕ) (q : Q5) : Prop :=
  q.ph ≠ .own → q.load ≤ k ∨ q.infeas = true ∨ q.unres = true

theorem quietInv_step {q q' : Q5} (h : Q5Step k q q') (hq : QuietInv k q) : QuietInv k q' := by
  cases h with
  | change l => intro h'; simp at h'
  | certify => intro h'; simp at h'
  | giveUp h => intro _; simp
  | recover h => intro _; exact Or.inl h
  | quiet h hs => intro _; exact hs
  | done h => intro _; exact hq (by rw [h]; decide)
  | undone h => intro _; exact hq (by rw [h]; decide)

/-- A node reachable from Phase 4 (`own`) by the steps above satisfies the invariant. -/
theorem quietInv_of_reach {q q' : Q5} (h : Relation.ReflTransGen (Q5Step k) q q')
    (h0 : q.ph = .own) : QuietInv k q' := by
  induction h with
  | refl => intro h'; exact absurd h0 h'
  | tail _ hs ih => exact quietInv_step hs ih

/-- **The load bound of Theorem 3(b).** A DONE node of the cover at which no rule can fire
(here: the infeasible branch of `_rule_ownership`, which marks an overloaded node Unresolved) and
that has not reported Unresolved carries at most `k` edges.

Modelling choices: one node; its load changes arbitrarily (`change`), the timers of
`alg:quiescence` and the barrier are abstracted to the enabling of `quiet`, `done`, `undone`;
the flag Unresolved is raised only on an overloaded node and cleared once the load is at most
`k`, as in the code.

Added hypotheses: none; `hnofire` is part of "no rule can fire". -/
theorem load_le_of_silent {q₀ q : Q5} (h : Relation.ReflTransGen (Q5Step k) q₀ q)
    (h0 : q₀.ph = .own) (hdone : q.ph = .done)
    (hnofire : ¬ (k < q.load ∧ q.infeas = true ∧ q.unres = false)) (hun : q.unres = false) :
    q.load ≤ k := by
  rcases quietInv_of_reach h h0 (by rw [hdone]; decide) with h1 | h1 | h1
  · exact h1
  · by_contra hc; exact hnofire ⟨not_le.1 hc, h1, hun⟩
  · rw [hun] at h1; exact absurd h1 (by decide)

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms owner_exactly_one
open SwarmInfer.CoverWeave.ExecFull in
#print axioms load_le_of_silent
