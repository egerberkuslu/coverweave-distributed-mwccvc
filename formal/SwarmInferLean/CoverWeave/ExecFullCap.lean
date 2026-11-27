import SwarmInferLean.CoverWeave.ExecFullOwnership
import SwarmInferLean.CoverWeave.ExecFullEcho

/-!
# CoverWeave, Theorem 3(b) (`thm:cap` (b), inventory C5(b)): what holds

`ExecFullTransfer.lean` refutes Theorem 3(b) as stated: its hypothesis ("every accepted transfer
was acknowledged") together with silence and in-order delivery does not make the settled
decisions of the two ends of a flexible edge complementary, and both a doubly owned and an unowned
edge result. This file proves the statement with that hypothesis replaced by what the proof
actually needs, `ExplicitConsistent`, and with every other step of the proof derived from a model:

* records equal what their node advertises: from the confirmation echo
  (`rec_eq_adv_of_confirmed`, `ExecFullEcho.lean`);
* the message-free start gives a flexible edge to exactly one end on agreed budgets, a forced
  edge belongs to its end in the cover, an edge outside the cover has none
  (`owner_exactly_one`, `ExecFullOwnership.lean`);
* the load bound: from the Phase 5 rules (`load_le_of_silent`).

The cover property (no edge with both ends outside `C`) is Theorem `lem:cover`, a hypothesis here
as in the paper's proof.
-/

namespace SwarmInfer.CoverWeave.ExecFull

open Finset

variable {V K : Type*} [Fintype V] [DecidableEq V] [LinearOrder K]
variable {G : SimpleGraph V} [DecidableRel G.Adj] {k : ℕ} {key : V → K}

open Classical in
/-- The load `ℓ(v)`: the edges of `Ĝ*` at `v` that `v` owns. -/
noncomputable def loadOf (G : SimpleGraph V) (k : ℕ) (key : V → K) (c : OwnCfg V) (v : V) : ℕ :=
  #{u | G.Adj v u ∧ Owns k key c v u}

omit [DecidableEq V] [DecidableRel G.Adj] in
/-- **Theorem 3(b), repaired.** Consider a configuration of the final epoch on `Ĝ*` in which
1. for every edge `{x, u}`, the pair `x → u` of the echo layer is in a reachable state in which `x`
   has `u` confirmed (a closed barrier, `_unconfirmed` is empty), `u` holds a record and no rule
   can fire at `x` (its state is what it advertised), and `u`'s record and `x`'s state are the
   (role, forced load) of the corresponding versions;
2. the settled decisions of the two ends of every flexible edge are complementary or both absent
   (`ExplicitConsistent`; this replaces "every accepted transfer was acknowledged", which does
   not imply it, `thm3b_fails_with_yield`, `thm3b_fails_repeat`);
3. no edge has both ends outside the cover (Theorem `lem:cover`);
4. every node is DONE, reached from Phase 4 by the steps of Phase 5, its Phase 5 load is its
   load in the configuration, its flag Unresolved is the configuration's, and the infeasible
   branch of `_rule_ownership` cannot fire at it.

Then every edge of `Ĝ*` has exactly one owner, that owner is an endpoint in the cover, and every
node of the cover that has not reported Unresolved has load at most `k`.

Modelling choices: those of `owner_exactly_one`, `rec_eq_adv_of_confirmed` and
`load_le_of_silent`; `val x i` is the (cover role, advertised forced load) of `x` at version `i`.

Added hypotheses: item 2 replaces the paper's hypothesis (see above). -/
theorem thm_cap_b_repaired (hkey : Function.Injective key) (c : OwnCfg V)
    (ep : V → V → EPair) (val : V → ℕ → Bool × ℕ)
    (hreach : ∀ x u, G.Adj x u → Relation.ReflTransGen EStep EPair.start (ep x u))
    (hconf : ∀ x u, G.Adj x u → (ep x u).conf = some true)
    (hrcd : ∀ x u, G.Adj x u → ∃ i, (ep x u).rcd = some i ∧
      c.recC u x = (val x i).1 ∧ c.recF u x = (val x i).2)
    (hcur : ∀ x u, G.Adj x u → (ep x u).cur = (ep x u).adv ∧
      c.inC x = (val x (ep x u).cur).1 ∧ c.advF x = (val x (ep x u).cur).2)
    (hE : ExplicitConsistent G c) (hC : CoverOK G c)
    (q₀ q : V → Q5) (hq : ∀ v, Relation.ReflTransGen (Q5Step k) (q₀ v) (q v))
    (hq₀ : ∀ v, (q₀ v).ph = .own) (hdone : ∀ v, (q v).ph = .done)
    (hfire : ∀ v, ¬ (k < (q v).load ∧ (q v).infeas = true ∧ (q v).unres = false))
    (hload : ∀ v, (q v).load = loadOf G k key c v) (hun : ∀ v, (q v).unres = c.unres v) :
    (∀ v u, G.Adj v u → (Owns k key c v u ↔ ¬ Owns k key c u v)) ∧
    (∀ v u, G.Adj v u → Owns k key c v u → c.inC v = true) ∧
    (∀ v, c.inC v = true → c.unres v = false → loadOf G k key c v ≤ k) := by
  have hR : RecordsAccurate G c := by
    intro v u h
    obtain ⟨i, hi, h1, h2⟩ := hrcd u v h.symm
    have := rec_eq_adv_of_confirmed (hreach u v h.symm) (hconf u v h.symm) hi
    obtain ⟨hc, h3, h4⟩ := hcur u v h.symm
    rw [h1, h2, h3, h4, hc, ← this]
    exact ⟨rfl, rfl⟩
  refine ⟨fun v u h => (owner_exactly_one hkey hR hE hC h).1,
    fun v u h => (owner_exactly_one hkey hR hE hC h).2, fun v _ hv => ?_⟩
  rw [← hload v]
  exact load_le_of_silent (hq v) (hq₀ v) (hdone v) (hfire v) (by rw [hun v, hv])

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm_cap_b_repaired
