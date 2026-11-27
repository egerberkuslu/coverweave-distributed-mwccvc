import SwarmInferLean.CoverWeave.ExecFullCap
import SwarmInferLean.CoverWeave.ExecFullTransferRepair

/-!
# CoverWeave, Theorem 3(b) for the whole transfer layer of Phase 4 (inventory C5(b))

Source: `CoverWeave_R1/sections/04-formaleng.tex:77-87` (Theorem `thm:cap` (b)), with the repaired
rules of `ExecFullTransferRepair.lean`.

The network. Every edge `{v, u}` of `Ĝ*` runs the repaired transfer layer of
`ExecFullTransfer.lean`, its end `a` being the end with the smaller key (the yield rule breaks
ties on the key). A run of the network is any interleaving of events of any edges; every choice
the transfer layer leaves to the rest of the protocol (room, chains, their outcomes, budget
changes, evictions, offers) is free, so the node-level coupling of the edges (one budget, one push
chain, one sequence counter per node) is covered as one particular choice.

Results.
* `netRun_proj`: the run of each edge is the run of the one-edge model on the events of that
  edge.
* `net_explicit_consistent`: in every network run from the start of Phase 4, if every edge with
  both ends in the cover is quiet, the settled decisions form `ExplicitConsistent`.
* `thm_cap_b_network`: Theorem 3(b) with the paper's hypothesis "every accepted transfer was
  acknowledged" replaced by "the run of the repaired transfer layer is quiet on every edge of the
  cover", which is part of silence; this discharges the hypothesis `hE` of `thm_cap_b_repaired`.
-/

namespace SwarmInfer.CoverWeave.ExecFull

variable {V K : Type*} [DecidableEq V] [LinearOrder K]

/-- The state of the transfer layer of every edge: `s v u` for `key v < key u`, with `a = v`. -/
abbrev NetSt (V : Type*) := V → V → St

/-- An event of the edge `{v, u}`, `v` the end with the smaller key. -/
structure NEv (V : Type*) where
  v : V
  u : V
  e : Ev

/-- A network step: the event of one edge, `none` when it is not enabled. -/
def netStep (key : V → K) (s : NetSt V) (x : NEv V) : Option (NetSt V) :=
  if key x.v < key x.u then
    (step repairParams (s x.v x.u) x.e).map fun t => Function.update s x.v (Function.update (s x.v) x.u t)
  else none

def netRun (key : V → K) : NetSt V → List (NEv V) → Option (NetSt V)
  | s, [] => some s
  | s, x :: xs => (netStep key s x).bind fun s' => netRun key s' xs

/-- The start of Phase 4: every edge at its start, with any message-free start values. -/
def netStart (da db : V → V → Bool) : NetSt V := fun v u => start (da v u) (db v u)

/-- The events of the edge `(v, u)`. -/
def proj (v u : V) (xs : List (NEv V)) : List Ev :=
  (xs.filter fun x => x.v = v ∧ x.u = u).map NEv.e

theorem netRun_proj (key : V → K) :
    ∀ (xs : List (NEv V)) (s₀ s : NetSt V), netRun key s₀ xs = some s →
      ∀ v u, key v < key u → runEvs repairParams (s₀ v u) (proj v u xs) = some (s v u) := by
  intro xs
  induction xs with
  | nil => intro s₀ s h v u _; simp [netRun] at h; subst h; simp [proj, runEvs]
  | cons x xs ih =>
    intro s₀ s h v u hvu
    simp only [netRun] at h
    cases hs : netStep key s₀ x with
    | none => simp [hs] at h
    | some s' =>
      simp only [hs, Option.bind_some] at h
      have ih' := ih s' s h v u hvu
      simp only [netStep] at hs
      split_ifs at hs with hk
      obtain ⟨t, ht, rfl⟩ := Option.map_eq_some_iff.1 hs
      by_cases hx : x.v = v ∧ x.u = u
      · obtain ⟨rfl, rfl⟩ := hx
        have : proj x.v x.u (x :: xs) = x.e :: proj x.v x.u xs := by simp [proj]
        rw [this]
        simp only [runEvs, ht, Option.bind_some]
        simpa using ih'
      · have : proj v u (x :: xs) = proj v u xs := by simp [proj, hx]
        rw [this]
        have he : Function.update s₀ x.v (Function.update (s₀ x.v) x.u t) v u = s₀ v u := by
          by_cases h1 : x.v = v
          · subst h1
            have h2 : u ≠ x.u := fun h2 => hx ⟨rfl, h2.symm⟩
            simp [Function.update_of_ne h2]
          · simp [Function.update_of_ne (Ne.symm h1)]
        rw [← he]; exact ih'

/-- The settled decision of `v` for the edge to `u` in a network state. -/
def netExpl (key : V → K) (s : NetSt V) (v u : V) : Option Bool :=
  if key v < key u then (s v u).a.X else (s u v).b.X

theorem consistentPair_comm {x y : Option Bool} (h : ConsistentPair x y) : ConsistentPair y x := by
  rcases h with ⟨h1, h2⟩ | ⟨h1, h2⟩ | ⟨h1, h2⟩
  · exact Or.inl ⟨h2, h1⟩
  · exact Or.inr (Or.inr ⟨h2, h1⟩)
  · exact Or.inr (Or.inl ⟨h2, h1⟩)

variable [Fintype V] {G : SimpleGraph V} [DecidableRel G.Adj]

omit [Fintype V] [DecidableRel G.Adj] in
/-- **The settled decisions of the network are consistent.** In every run of the repaired
transfer layer on all edges from the start of Phase 4, if the edge between every two adjacent
cover nodes is quiet, the settled decisions are complementary or both absent on every flexible
edge (`ExplicitConsistent`).

Modelling choices: those of `ExecFullTransfer.lean` for each edge; the edges interact only
through the choices the one-edge model leaves to its environment, all of which are free here.

Added hypotheses: none beyond quietness of the cover's edges, which is part of silence. -/
theorem net_explicit_consistent {key : V → K} (hkey : Function.Injective key)
    {da db : V → V → Bool} {xs : List (NEv V)} {s : NetSt V}
    (hrun : netRun key (netStart da db) xs = some s) {c : OwnCfg V}
    (hq : ∀ v u, G.Adj v u → c.inC v = true → c.inC u = true → key v < key u → Quiet (s v u))
    (hc : ∀ v u, c.expl v u = netExpl key s v u) : ExplicitConsistent G c := by
  have hcp : ∀ v u, G.Adj v u → c.inC v = true → c.inC u = true → key v < key u →
      ConsistentPair (s v u).a.X (s v u).b.X := by
    intro v u h hv hu hk
    have hr := netRun_proj key xs _ s hrun v u hk
    exact (thm3b_transfer_repaired (da v u) (db v u) _ hr (hq v u h hv hu hk)).1
  intro v u h hv hu
  rw [hc v u, hc u v]
  have hne : key v ≠ key u := fun h' => h.ne (hkey h')
  rcases lt_or_gt_of_ne hne with hk | hk
  · simp only [netExpl, hk, ite_true, not_lt.2 hk.le]
    simpa using hcp v u h hv hu hk
  · simp only [netExpl, hk, ite_true, not_lt.2 hk.le]
    exact consistentPair_comm (by simpa using hcp u v h.symm hu hv hk)

variable {k : ℕ}

omit [DecidableRel G.Adj] in
/-- **Theorem 3(b), repaired, for the network.** The statement of `thm_cap_b_repaired`, with its
hypothesis `ExplicitConsistent` discharged: the settled decisions are those of a run of the
repaired transfer layer on all edges from the start of Phase 4 that is quiet on every edge between
two cover nodes. -/
theorem thm_cap_b_network {key : V → K} (hkey : Function.Injective key) (c : OwnCfg V)
    (ep : V → V → EPair) (val : V → ℕ → Bool × ℕ)
    (hreach : ∀ x u, G.Adj x u → Relation.ReflTransGen EStep EPair.start (ep x u))
    (hconf : ∀ x u, G.Adj x u → (ep x u).conf = some true)
    (hrcd : ∀ x u, G.Adj x u → ∃ i, (ep x u).rcd = some i ∧
      c.recC u x = (val x i).1 ∧ c.recF u x = (val x i).2)
    (hcur : ∀ x u, G.Adj x u → (ep x u).cur = (ep x u).adv ∧
      c.inC x = (val x (ep x u).cur).1 ∧ c.advF x = (val x (ep x u).cur).2)
    {da db : V → V → Bool} {xs : List (NEv V)} {s : NetSt V}
    (hrun : netRun key (netStart da db) xs = some s)
    (hq : ∀ v u, G.Adj v u → c.inC v = true → c.inC u = true → key v < key u → Quiet (s v u))
    (hexp : ∀ v u, c.expl v u = netExpl key s v u) (hC : CoverOK G c)
    (q₀ q : V → Q5) (hq5 : ∀ v, Relation.ReflTransGen (Q5Step k) (q₀ v) (q v))
    (hq₀ : ∀ v, (q₀ v).ph = .own) (hdone : ∀ v, (q v).ph = .done)
    (hfire : ∀ v, ¬ (k < (q v).load ∧ (q v).infeas = true ∧ (q v).unres = false))
    (hload : ∀ v, (q v).load = loadOf G k key c v) (hun : ∀ v, (q v).unres = c.unres v) :
    (∀ v u, G.Adj v u → (Owns k key c v u ↔ ¬ Owns k key c u v)) ∧
    (∀ v u, G.Adj v u → Owns k key c v u → c.inC v = true) ∧
    (∀ v, c.inC v = true → c.unres v = false → loadOf G k key c v ≤ k) :=
  thm_cap_b_repaired hkey c ep val hreach hconf hrcd hcur
    (net_explicit_consistent hkey hrun hq hexp) hC q₀ q hq5 hq₀ hdone hfire hload hun

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms net_explicit_consistent
open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm_cap_b_network
