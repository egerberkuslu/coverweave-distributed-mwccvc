import SwarmInferLean.CoverWeave.ExecFullTransferInvR2pp
import SwarmInferLean.CoverWeave.ExecFullNetwork

/-!
# CoverWeave, Theorem 3(b) under the repair R2' of commit 5d9936a (inventory C5(b))

Source: branch `r2r3-repair` of `bbcvc-release`, commit 5d9936a, `ccvc/bb/bbcvc.py` (`_on_push`,
`_refuse`, `_finish_push_job`, `_repeat_ok`). Instead of R2 (no reply to a busy copy), the code
implements R2' (`finalBusy`): a busy refusal is final; the chain of a refused request runs to its
end but never takes the edge, and a later copy cannot take it either.

* `thm3b_fails_branch`: the code of commit 5d9936a (R2', R3, no R4) admits `traceTake`.
* `thm3b_fails_r2p`: R2' with R3 and R4 still admits a run that ends quiet, with the start agreed,
  in which both ends hold the edge. A chain refused as busy ends while its node holds the edge
  through a later HANDOVER; `_finish_push_job` then answers the refused PUSH with an
  acknowledgement (`took = ... or explicit is True`), the sender reads it as a late
  acknowledgement and releases the edge although it owes the edge to that HANDOVER.
* The repair R2'' (`finalNack`): a request refused as busy gets only refusals, from the chain's end
  and from busy copies alike.
* `thm3b_transfer_r2pp`: under the yield rule, the `θ` check on the late path, R2'', R3 and R4
  (`r2ppParams`), every quiet configuration reachable from the start of Phase 4 has complementary
  or absent settled decisions and, the start agreed, exactly one owner (the invariant of
  `ExecFullTransferInvR2pp.lean`).
* `net_explicit_consistent_r2pp`, `thm_cap_b_network_r2pp`: the same for every edge of the
  network, and Theorem 3(b) with `ExplicitConsistent` discharged.
-/

namespace SwarmInfer.CoverWeave.ExecFull

/-- **Theorem 3(b) fails for the code of commit 5d9936a**: R4 is missing, `traceTake` applies. -/
theorem thm3b_fails_branch :
    ∃ s, runEvs branchParams (start true true) traceTake = some s ∧ Quiet s ∧ AllAcked s ∧
      Agreed s ∧ owns s.a = true ∧ owns s.b = true :=
  bad_of_any (by decide)

/-- The run for R2' (found by bounded search at two offers per end and two frames per channel). -/
def traceFinalNack : List Ev :=
  [.offer true true, .retx true 1, .deliver true false true, .deliver true false false,
    .deliver false false false, .offer true false, .retx true 2, .deliver true true false,
    .lose false, .finish false false false, .offer false true, .deliver false false false,
    .deliver false false true, .deliver true false false, .retx false 1, .deliver false false false,
    .finish true true true, .evict true 1, .deliver false false false, .lose true,
    .deliver true false false]

/-- **Theorem 3(b) fails under R2', R3 and R4.** There is a run of one flexible edge that ends
quiet, with the message-free start agreed, in which both ends hold the edge. -/
theorem thm3b_fails_r2p :
    ∃ s, runEvs r2pParams (start false true) traceFinalNack = some s ∧ Quiet s ∧
      Agreed s ∧ owns s.a = true ∧ owns s.b = true := by
  have h : (runEvs r2pParams (start false true) traceFinalNack).any
      (fun s => quietB s && (s.a.dflt != s.b.dflt) && owns s.a && owns s.b) = true := by decide
  cases ho : runEvs r2pParams (start false true) traceFinalNack with
  | none => simp [ho] at h
  | some s =>
    simp only [ho, Option.any_some, Bool.and_eq_true] at h
    exact ⟨s, rfl, h.1.1.1, h.1.1.2, h.1.2, h.2⟩

/-- Under R2'' the same events are not a run any more, or end with one owner. -/
theorem r2pp_traces :
    (runEvs r2ppParams (start false true) traceFinalNack).all
      (fun s => !quietB s || (owns s.a != owns s.b)) = true ∧
    (runEvs r2ppParams (start true true) traceTake).all
      (fun s => !quietB s || (owns s.a != owns s.b)) = true ∧
    (runEvs r2ppParams (start true true) traceBusy).all
      (fun s => !quietB s || (owns s.a != owns s.b)) = true ∧
    (runEvs r2ppParams (start true true) traceRepeat).all
      (fun s => !quietB s || (owns s.a != owns s.b)) = true := by
  decide

/-- **Theorem 3(b) for the transfer layer under R2''.** -/
theorem thm3b_transfer_r2pp (da db : Bool) (es : List Ev) {s : St}
    (hrun : runEvs r2ppParams (start da db) es = some s) (hq : Quiet s) :
    ConsistentPair s.a.X s.b.X ∧ (Agreed s → owns s.a ≠ owns s.b) := by
  have hcp := R2pp.cp_of_quiet (R2pp.runEvs_pres (R2pp.inv_start da db) hrun) hq
  refine ⟨(cp_iff _ _).1 hcp, fun hag => ?_⟩
  simp only [Agreed, bne_iff_ne, ne_eq] at hag
  unfold owns
  revert hcp
  rcases s.a.X with _ | _ | _ <;> rcases s.b.X with _ | _ | _ <;>
    cases ha : s.a.dflt <;> cases hb : s.b.dflt <;> simp_all [CP]

/-! ### The network under R2'' -/

variable {V K : Type*} [DecidableEq V] [LinearOrder K]

/-- A network step under the parameters `P`. -/
def netStepP (P : Params) (key : V → K) (s : NetSt V) (x : NEv V) : Option (NetSt V) :=
  if key x.v < key x.u then
    (step P (s x.v x.u) x.e).map fun t => Function.update s x.v (Function.update (s x.v) x.u t)
  else none

def netRunP (P : Params) (key : V → K) : NetSt V → List (NEv V) → Option (NetSt V)
  | s, [] => some s
  | s, x :: xs => (netStepP P key s x).bind fun s' => netRunP P key s' xs

theorem netRunP_proj (P : Params) (key : V → K) :
    ∀ (xs : List (NEv V)) (s₀ s : NetSt V), netRunP P key s₀ xs = some s →
      ∀ v u, key v < key u → runEvs P (s₀ v u) (proj v u xs) = some (s v u) := by
  intro xs
  induction xs with
  | nil => intro s₀ s h v u _; simp [netRunP] at h; subst h; simp [proj, runEvs]
  | cons x xs ih =>
    intro s₀ s h v u hvu
    simp only [netRunP] at h
    cases hs : netStepP P key s₀ x with
    | none => simp [hs] at h
    | some s' =>
      simp only [hs, Option.bind_some] at h
      have ih' := ih s' s h v u hvu
      simp only [netStepP] at hs
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

variable [Fintype V] {G : SimpleGraph V} [DecidableRel G.Adj]

omit [Fintype V] [DecidableRel G.Adj] in
/-- **The settled decisions of the network are consistent under R2''.** -/
theorem net_explicit_consistent_r2pp {key : V → K} (hkey : Function.Injective key)
    {da db : V → V → Bool} {xs : List (NEv V)} {s : NetSt V}
    (hrun : netRunP r2ppParams key (netStart da db) xs = some s) {c : OwnCfg V}
    (hq : ∀ v u, G.Adj v u → c.inC v = true → c.inC u = true → key v < key u → Quiet (s v u))
    (hc : ∀ v u, c.expl v u = netExpl key s v u) : ExplicitConsistent G c := by
  have hcp : ∀ v u, G.Adj v u → c.inC v = true → c.inC u = true → key v < key u →
      ConsistentPair (s v u).a.X (s v u).b.X := by
    intro v u h hv hu hk
    have hr := netRunP_proj r2ppParams key xs _ s hrun v u hk
    exact (thm3b_transfer_r2pp (da v u) (db v u) _ hr (hq v u h hv hu hk)).1
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
/-- **Theorem 3(b), repaired with R2'', for the network.** -/
theorem thm_cap_b_network_r2pp {key : V → K} (hkey : Function.Injective key) (c : OwnCfg V)
    (ep : V → V → EPair) (val : V → ℕ → Bool × ℕ)
    (hreach : ∀ x u, G.Adj x u → Relation.ReflTransGen EStep EPair.start (ep x u))
    (hconf : ∀ x u, G.Adj x u → (ep x u).conf = some true)
    (hrcd : ∀ x u, G.Adj x u → ∃ i, (ep x u).rcd = some i ∧
      c.recC u x = (val x i).1 ∧ c.recF u x = (val x i).2)
    (hcur : ∀ x u, G.Adj x u → (ep x u).cur = (ep x u).adv ∧
      c.inC x = (val x (ep x u).cur).1 ∧ c.advF x = (val x (ep x u).cur).2)
    {da db : V → V → Bool} {xs : List (NEv V)} {s : NetSt V}
    (hrun : netRunP r2ppParams key (netStart da db) xs = some s)
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
    (net_explicit_consistent_r2pp hkey hrun hq hexp) hC q₀ q hq5 hq₀ hdone hfire hload hun

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_transfer_r2pp
open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm_cap_b_network_r2pp
open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_fails_branch
open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_fails_r2p
open SwarmInfer.CoverWeave.ExecFull in
#print axioms r2pp_traces
