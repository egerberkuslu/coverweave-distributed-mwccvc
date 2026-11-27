import SwarmInferLean.CoverWeave.ExecFullTermination
import SwarmInferLean.CoverWeave.ExecConnector
import SwarmInferLean.CoverWeave.ExecFullCap
import SwarmInferLean.CoverWeave.ExecFullTransferR2p
import SwarmInferLean.CoverWeave.ExecFullNetwork

/-!
# CoverWeave: the end-to-end correctness theorem on a lossy channel (C3, C4, C5(b), C9, C10)

Sources: `CoverWeave_R1/sections/04-formaleng.tex`, Assumption `asm:loss` (window condition),
Lemma `lem:lossless` (Lemma 4), Theorem `lem:term` (Theorem 4), Theorem `lem:cover`, Lemma
`lem:conn`, Theorem `thm:cap` (b), and the standing convention of that section that every
statement refers to the discovered graph `Ĝ*` of the final epoch of a silent run.

This file composes the results of the project into one statement about a run of the MIS arm of
the whole protocol: it becomes silent with probability one, with the tail bound of Theorem 4,
and every silent configuration it reaches carries a cover that contains the backbone and is a
connected vertex cover, and an ownership in which every edge has exactly one owner, an endpoint
in the cover, with load at most `k` at every node of the cover that has not reported
Unresolved (so a valid pair when no node of the cover reported Unresolved).

No single Lean model of the whole protocol exists in this project; each layer has its own
model (Phase 1a `ExecDecision`, Phase 1b `ExecConnector`, the echo `ExecFullEcho`, the
transfer layer of one edge `ExecFullTransfer*`, Phase 5 `ExecFullOwnership`). The whole protocol
is therefore an arbitrary synchronous protocol `P : SyncProtocol V S M` (`ExecSilence.lean`), and
what is not proved about it is collected in the structure `OpenHyps`, one named field per open
part. Each field is either Lemma 4 itself or a statement that one layer of `P`, read off a silent
reachable configuration, is a run of that layer's model (a refinement statement), or a phase
rule at silence; the proven layer theorems then do the work. No field states a conclusion.
-/

namespace SwarmInfer.CoverWeave.Main

open MeasureTheory SimpleGraph Finset
open scoped ENNReal

variable {V K S M : Type*} [Fintype V] [DecidableEq V] [LinearOrder K]

/-- What the theorem reads off the node states of the whole protocol: the role of a node, and the
ownership-relevant fields of the final epoch as an `OwnCfg` of `ExecFullOwnership.lean` (cover
flag, advertised forced load, records, settled transfer decisions, the flags Unresolved and
infeasible). `inC_iff` says the cover flag of the ownership layer is the role "not OUT". -/
structure Readout (V S : Type*) where
  role : S → Role
  own : (V → S) → ExecFull.OwnCfg V
  inC_iff : ∀ st v, (own st).inC v = true ↔ role (st v) ≠ .out

/-- The cover `C` of a configuration: the nodes whose role is not OUT. -/
def cover (R : Readout V S) (st : V → S) : Finset V := univ.filter fun v => R.role (st v) ≠ .out

omit [DecidableEq V] in
theorem coe_cover (R : Readout V S) (st : V → S) :
    (cover R st : Set V) = {v | R.role (st v) ≠ .out} := by
  ext v; simp [cover]

variable (G : SimpleGraph V) [DecidableRel G.Adj] (k : ℕ) (key : V → K)

open Classical in
/-- The owner map of a configuration: for an edge, an endpoint that owns it under the
re-derived ownership `Owns` of `ExecFullOwnership.lean` (`_recompute_owned`). When exactly one
end owns every edge (which the theorem proves at silence), this is that end. -/
noncomputable def ownerOf (R : Readout V S) (st : V → S) (e : G.edgeSet) : V :=
  if h : ∃ x y, (e : Sym2 V) = s(x, y) ∧ ExecFull.Owns k key (R.own st) x y then h.choose
  else (Quot.out (e : Sym2 V)).1

/-- **The open parts**, each a named hypothesis about the whole protocol `P` started at `c₀`,
read through `R`, on the final-epoch graph `G` with capacity `k`, key `key` and window `W`.
"Silent reachable" is `Exec.Reachable P c₀ c ∧ Exec.Silent P c`. -/
structure OpenHyps (P : Exec.SyncProtocol V S M) (c₀ : Exec.SCfg V S M) (R : Readout V S)
    (W : ℕ) : Prop where
  /-- (H_window) Lemma 4 (`lem:lossless`) for the whole protocol: from every reachable
  configuration, `W` loss-free slots end silent. Discharged for Phase 1a (`phase1a_window`),
  Phase 1b (`allDone_of_lossFree`) and the transfer layer of one edge (`transfer_window_owner`),
  not for the whole protocol. For Phase 4 under the node controller of
  `ExecFullController.lean` the window is proven from the slot `T₀` at which the signatures
  settle (`R2pp.ctl_phase4_window` of `ExecFullPhase4.lean`, under `R2pp.Phase4Hyps`: start
  without chains, degree `Δ`, timers `Tr`, hop limits `D`, and per end an offer budget `n` and
  final idleness `π` from `T₀`); that the signatures settle at some `T₀` is not derived. -/
  window : Exec.LossFreeWindow P c₀ W
  /-- (H_phase1) Refinement of Phases 1a and 1b: the Phase 1 part of a silent reachable
  configuration is the state of the Phase 1 model (`Exec.run`, `Exec.extRun`) at some slot `t`
  of a run under some loss pattern and enablings, at which every node has run `Connector`; its
  MIS roles are the MIS decisions of that run and its CONNECTORs are in the cover. The paper's
  claims built on this (MIS = key-greedy set, Phase 1b rule at silence) are then proved by
  `run_sound` and `connector_sound`, not assumed. -/
  phase1 : ∀ c, Exec.Reachable P c₀ c → Exec.Silent P c →
    ∃ (ok : Exec.LossPattern V) (en en₂ : Exec.Enabling V) (t : ℕ),
      (∀ v, (Exec.extRun G key ok en en₂ t).done v = true) ∧
      (∀ v, R.role (c.st v) = .mis ↔ (Exec.run G key ok en Exec.init t).st v = .mis) ∧
      (∀ v, (Exec.extRun G key ok en en₂ t).conn v = true → R.role (c.st v) ≠ .out)
  /-- (H_gap3) The Gap3 rule of Phase 2 (`Gap3Rule`, `BackboneCover.lean`) holds at silence, on
  the MIS nodes of the configuration (proof of `lem:conn`, "a silent configuration ... has
  `y ∈ C`"). Per bridge node `x` and neighbour `y`. -/
  gap3 : ∀ c, Exec.Reachable P c₀ c → Exec.Silent P c →
    Gap3Rule G {v | R.role (c.st v) = .mis} {v | R.role (c.st v) ≠ .out}
  /-- (H_phase2) The Phase 2 cover rule (`Phase2Rule`) holds at silence: no OUT node has an OUT
  neighbour of larger key (proof of `lem:cover`, Phase 2 and the check of Phase 3). Per edge. -/
  phase2 : ∀ c, Exec.Reachable P c₀ c → Exec.Silent P c →
    Phase2Rule G key (fun v => R.role (c.st v))
  /-- (H_echo) Refinement of the confirmation echo, per ordered edge `x → u`: the pair is a
  reachable state of the echo model (`ExecFullEcho.lean`) in which `x` has `u` confirmed, `u`
  holds a record, no change is unannounced (`cur = adv`), the record is version `i` of `x`'s
  (cover role, forced load) and `x`'s state is version `cur` (premise 1 of
  `thm_cap_b_repaired`). -/
  echo : ∀ c, Exec.Reachable P c₀ c → Exec.Silent P c → ∀ x u, G.Adj x u →
    ∃ (p : ExecFull.EPair) (val : ℕ → Bool × ℕ),
      Relation.ReflTransGen ExecFull.EStep ExecFull.EPair.start p ∧ p.conf = some true ∧
      p.cur = p.adv ∧
      (∃ i, p.rcd = some i ∧ (R.own c.st).recC u x = (val i).1 ∧
        (R.own c.st).recF u x = (val i).2) ∧
      (R.own c.st).inC x = (val p.cur).1 ∧ (R.own c.st).advF x = (val p.cur).2
  /-- (H_transfer) Refinement of the transfer layer, per flexible edge `{v, u}` (both ends in the
  cover, `v` the end of smaller key): the transfer layer of the edge, read on its two ends, is a
  run of the one-edge model under the registered rules (`r2ppParams`: yield rule, `θ` check on
  the late path, R2'', R3, R4; Amendment 17 of `contract/R1_PREREG.md`) from the start of Phase 4,
  quiet at silence, and its settled decisions are the configuration's. `thm3b_transfer_r2pp`
  then gives consistency. -/
  transfer : ∀ c, Exec.Reachable P c₀ c → Exec.Silent P c → ∀ v u, G.Adj v u →
    (R.own c.st).inC v = true → (R.own c.st).inC u = true → key v < key u →
    ∃ (da db : Bool) (es : List ExecFull.Ev) (s : ExecFull.St),
      ExecFull.runEvs ExecFull.r2ppParams (ExecFull.start da db) es = some s ∧
      ExecFull.Quiet s ∧ (R.own c.st).expl v u = s.a.X ∧ (R.own c.st).expl u v = s.b.X
  /-- (H_phase5) Refinement of Phase 5, per node of the cover: its Phase 5 fields are reached from
  Phase 4 by the steps of `Q5Step`, it is DONE, the infeasible branch of `_rule_ownership` cannot
  fire, its Phase 5 load is its load in the configuration and its flag Unresolved is the
  configuration's (premise 4 of `thm_cap_b_repaired`, restricted to the cover). -/
  phase5 : ∀ c, Exec.Reachable P c₀ c → Exec.Silent P c → ∀ v ∈ cover R c.st,
    ∃ q₀ q : ExecFull.Q5, Relation.ReflTransGen (ExecFull.Q5Step k) q₀ q ∧
      q₀.ph = .own ∧ q.ph = .done ∧ ¬ (k < q.load ∧ q.infeas = true ∧ q.unres = false) ∧
      q.load = ExecFull.loadOf G k key (R.own c.st) v ∧ q.unres = (R.own c.st).unres v

/-- The correct output of a configuration: `C` contains the backbone of MIS and CONNECTOR nodes,
`C` is a connected vertex cover, every edge has exactly one owner, the owner is an endpoint in
`C`, every node of `C` that has not reported Unresolved owns at most `k` edges, and so
`(C, owner)` is a valid pair (`ValidPair`, Definition MWCCVC) when no node of `C` reported
Unresolved. -/
def CorrectOutput (R : Readout V S) (st : V → S) : Prop :=
  {v | R.role (st v) = .mis ∨ R.role (st v) = .connector} ⊆ (cover R st : Set V) ∧
  IsConnectedVertexCover G (cover R st) ∧
  (∀ v u, G.Adj v u →
    (ExecFull.Owns k key (R.own st) v u ↔ ¬ ExecFull.Owns k key (R.own st) u v)) ∧
  (∀ e : G.edgeSet, ownerOf G k key R st e ∈ (e : Sym2 V) ∧ ownerOf G k key R st e ∈ cover R st) ∧
  (∀ v ∈ cover R st, (R.own st).unres v = false → load G (ownerOf G k key R st) v ≤ k) ∧
  ((∀ v ∈ cover R st, (R.own st).unres v = false) → ValidPair G k (cover R st) (ownerOf G k key R st))

variable {G k key}

/-! ### Small lemmas -/

omit [DecidableEq V] in
/-- A node that has run `Connector` has decided. -/
theorem decided_of_done {ok : Exec.LossPattern V} {en en₂ : Exec.Enabling V} :
    ∀ t v, (Exec.extRun G key ok en en₂ t).done v = true →
      (Exec.run G key ok en Exec.init t).st v ≠ .undecided
  | 0, v, h => by simp [Exec.extRun] at h
  | t + 1, v, h => by
    simp only [Exec.extRun, Exec.extStep, Bool.or_eq_true, decide_eq_true_eq] at h
    have hd : (Exec.run G key ok en Exec.init t).st v ≠ .undecided := by
      rcases h with h | ⟨-, h, -⟩
      · exact decided_of_done t v h
      · exact h
    rw [Exec.run_succ_of_ne hd]; exact hd

theorem consistentPair_symm {a b : Option Bool} (h : ExecFull.ConsistentPair a b) :
    ExecFull.ConsistentPair b a := by
  unfold ExecFull.ConsistentPair at *; tauto

omit [DecidableRel G.Adj] in
/-- If every edge has an owning end, the chosen owner owns it. -/
theorem ownerOf_spec {R : Readout V S} {st : V → S}
    (hex : ∀ v u, G.Adj v u → ExecFull.Owns k key (R.own st) v u ∨ ExecFull.Owns k key (R.own st) u v)
    (e : G.edgeSet) :
    ∃ y, (e : Sym2 V) = s(ownerOf G k key R st e, y) ∧
      ExecFull.Owns k key (R.own st) (ownerOf G k key R st e) y := by
  classical
  obtain ⟨e, he⟩ := e
  induction e using Sym2.ind with
  | _ v u =>
    have h : ∃ x y, (s(v, u) : Sym2 V) = s(x, y) ∧ ExecFull.Owns k key (R.own st) x y := by
      rcases hex v u he with h | h
      · exact ⟨v, u, rfl, h⟩
      · exact ⟨u, v, Sym2.eq_swap, h⟩
    unfold ownerOf
    split
    · next h' => exact h'.choose_spec
    · next h' => exact absurd h h'

omit [DecidableRel G.Adj] in
/-- With exactly one owner per edge, the owner of `s(v, u)` is `v` iff `v` owns it. -/
theorem ownerOf_eq_iff {R : Readout V S} {st : V → S}
    (hx1 : ∀ v u, G.Adj v u →
      (ExecFull.Owns k key (R.own st) v u ↔ ¬ ExecFull.Owns k key (R.own st) u v))
    {v u : V} (h : G.Adj v u) :
    ownerOf G k key R st ⟨s(v, u), h⟩ = v ↔ ExecFull.Owns k key (R.own st) v u := by
  have hex : ∀ v u, G.Adj v u →
      ExecFull.Owns k key (R.own st) v u ∨ ExecFull.Owns k key (R.own st) u v := fun v u h => by
    by_cases hv : ExecFull.Owns k key (R.own st) v u
    · exact Or.inl hv
    · exact Or.inr ((hx1 u v h.symm).2 hv)
  obtain ⟨y, hy, hown⟩ := ownerOf_spec hex ⟨s(v, u), h⟩
  rcases Sym2.eq_iff.1 hy with ⟨h1, h2⟩ | ⟨h1, h2⟩
  · refine ⟨fun _ => ?_, fun _ => h1.symm⟩
    rw [← h1, ← h2] at hown; exact hown
  · refine ⟨fun hxv => absurd (h2.trans hxv).symm h.ne, fun hvu => ?_⟩
    rw [← h2, ← h1] at hown
    exact absurd hown ((hx1 v u h).1 hvu)

/-- With exactly one owner per edge, the load of the owner map is the load `loadOf` of
`ExecFullCap.lean`. -/
theorem load_ownerOf {R : Readout V S} {st : V → S}
    (hx1 : ∀ v u, G.Adj v u →
      (ExecFull.Owns k key (R.own st) v u ↔ ¬ ExecFull.Owns k key (R.own st) u v)) (v : V) :
    load G (ownerOf G k key R st) v = ExecFull.loadOf G k key (R.own st) v := by
  classical
  have hex : ∀ v u, G.Adj v u →
      ExecFull.Owns k key (R.own st) v u ∨ ExecFull.Owns k key (R.own st) u v := fun v u h => by
    by_cases hv : ExecFull.Owns k key (R.own st) v u
    · exact Or.inl hv
    · exact Or.inr ((hx1 u v h.symm).2 hv)
  unfold load ExecFull.loadOf
  symm
  refine Finset.card_bij (fun u hu => ⟨s(v, u), by simp at hu; exact hu.1⟩) ?_ ?_ ?_
  · intro u hu
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hu ⊢
    exact (ownerOf_eq_iff hx1 hu.1).2 hu.2
  · intro u₁ _ u₂ _ h
    exact Sym2.congr_right.1 (congrArg Subtype.val h)
  · intro e he
    have heq : ownerOf G k key R st e = v := (Finset.mem_filter.1 he).2
    obtain ⟨y, hy, hown⟩ := ownerOf_spec hex e
    rw [heq] at hy hown
    have hadj : G.Adj v y := by
      have := e.2; rw [hy] at this; exact this
    exact ⟨y, by simp [hadj, hown], Subtype.ext hy.symm⟩

omit [Fintype V] [DecidableRel G.Adj] in
/-- **The field `transfer` from one network run.** If the settled decisions of a configuration are
those of one run of the repaired transfer layer on all edges (`ExecFullNetwork.lean`) from the start
of Phase 4 that is quiet on every edge between two cover nodes, the per-edge field `transfer` of
`OpenHyps` holds: the run of each edge is its projection (`netRunP_proj`). The per-edge form is
kept as the field because it is implied by the network form and asks less (`netExpl` is needed
only on edges, and each edge may come from a different run). -/
theorem transfer_of_netRun {oc : ExecFull.OwnCfg V} {da db : V → V → Bool}
    {xs : List (ExecFull.NEv V)} {s : ExecFull.NetSt V}
    (hrun : ExecFull.netRunP ExecFull.r2ppParams key (ExecFull.netStart da db) xs = some s)
    (hq : ∀ v u, G.Adj v u → oc.inC v = true → oc.inC u = true → key v < key u →
      ExecFull.Quiet (s v u))
    (hexp : ∀ v u, G.Adj v u → oc.expl v u = ExecFull.netExpl key s v u) :
    ∀ v u, G.Adj v u → oc.inC v = true → oc.inC u = true → key v < key u →
      ∃ (da db : Bool) (es : List ExecFull.Ev) (s : ExecFull.St),
        ExecFull.runEvs ExecFull.r2ppParams (ExecFull.start da db) es = some s ∧
        ExecFull.Quiet s ∧ oc.expl v u = s.a.X ∧ oc.expl u v = s.b.X := by
  intro v u h hv hu hk
  refine ⟨da v u, db v u, ExecFull.proj v u xs, s v u, ExecFull.netRunP_proj ExecFull.r2ppParams key xs _ s hrun v u hk,
    hq v u h hv hu hk, ?_, ?_⟩
  · rw [hexp v u h]; simp only [ExecFull.netExpl, hk, ite_true]
  · rw [hexp u v h.symm]; simp only [ExecFull.netExpl, not_lt.2 hk.le, ite_false]

/-! ### Correctness of a silent configuration -/

/-- **Correctness at silence.** Under the open hypotheses, every silent configuration reachable
from `c₀` has a correct output (`CorrectOutput`). -/
theorem correct_of_silent (hkey : Function.Injective key) (hG : G.Connected)
    (hcard : 2 ≤ Fintype.card V) {P : Exec.SyncProtocol V S M} {c₀ : Exec.SCfg V S M}
    {R : Readout V S} {W : ℕ} (H : OpenHyps G k key P c₀ R W) {c : Exec.SCfg V S M}
    (hr : Exec.Reachable P c₀ c) (hs : Exec.Silent P c) : CorrectOutput G k key R c.st := by
  classical
  set role : V → Role := fun v => R.role (c.st v) with hrole
  set oc := R.own c.st with hoc
  -- Phases 1a and 1b, from the refinement hypothesis and the proven layer theorems
  obtain ⟨ok, en, en₂, t, hall, hmisr, hconn⟩ := H.phase1 c hr hs
  have hmis : ∀ v, role v = .mis ↔ keyGreedy G key v := fun v => by
    rw [hmisr v, Exec.run_sound ok en t v (decided_of_done t v (hall v))]
    exact Exec.truth_eq_mis_iff v
  have h1b : Phase1bRule G key {v | keyGreedy G key v} {v | role v ≠ .out} :=
    Exec.phase1bRule_of_allDone ok en en₂ t hall _ fun v hv => by
      rcases hv with hv | hv
      · show R.role (c.st v) ≠ .out
        rw [(hmisr v).2 hv]; decide
      · exact hconn v hv
  have hI : {v | role v = .mis} = {v | keyGreedy G key v} := Set.ext hmis
  have hg3 : Gap3Rule G {v | keyGreedy G key v} {v | role v ≠ .out} := hI ▸ H.gap3 c hr hs
  -- Theorem `lem:cover`
  obtain ⟨hB, hvc, hconnC⟩ := lem_cover_core G hkey hG hcard role hmis h1b hg3 (H.phase2 c hr hs)
  have hcov : (cover R c.st : Set V) = {v | role v ≠ .out} := coe_cover R c.st
  have hCVC : IsConnectedVertexCover G (cover R c.st) := by
    refine ⟨fun u v h => ?_, by rw [hcov]; exact hconnC⟩
    have := hvc h
    simpa [cover] using this
  -- Theorem 3(b), repaired: records, settled decisions, cover
  have hRA : ExecFull.RecordsAccurate G oc := by
    intro v u h
    obtain ⟨p, val, hreach, hconf, hcur, ⟨i, hi, h1, h2⟩, h3, h4⟩ := H.echo c hr hs u v h.symm
    have := ExecFull.rec_eq_adv_of_confirmed hreach hconf hi
    rw [h1, h2, h3, h4, hcur, ← this]
    exact ⟨rfl, rfl⟩
  have hEC : ExecFull.ExplicitConsistent G oc := by
    intro v u h hv hu
    rcases lt_or_gt_of_ne (hkey.ne h.ne) with hlt | hlt
    · obtain ⟨da, db, es, s, hrun, hq, ha, hb⟩ := H.transfer c hr hs v u h hv hu hlt
      rw [ha, hb]; exact (ExecFull.thm3b_transfer_r2pp da db es hrun hq).1
    · obtain ⟨da, db, es, s, hrun, hq, ha, hb⟩ := H.transfer c hr hs u v h.symm hu hv hlt
      rw [ha, hb]; exact consistentPair_symm (ExecFull.thm3b_transfer_r2pp da db es hrun hq).1
  have hCO : ExecFull.CoverOK G oc := by
    intro v u h
    rcases hvc h with hv | hv
    · exact Or.inl ((R.inC_iff c.st v).2 hv)
    · exact Or.inr ((R.inC_iff c.st u).2 hv)
  have hx1 : ∀ v u, G.Adj v u → (ExecFull.Owns k key oc v u ↔ ¬ ExecFull.Owns k key oc u v) :=
    fun v u h => (ExecFull.owner_exactly_one (k := k) hkey hRA hEC hCO h).1
  have hex : ∀ v u, G.Adj v u → ExecFull.Owns k key oc v u ∨ ExecFull.Owns k key oc u v :=
    fun v u h => by
      by_cases hv : ExecFull.Owns k key oc v u
      · exact Or.inl hv
      · exact Or.inr ((hx1 u v h.symm).2 hv)
  have hend : ∀ e : G.edgeSet,
      ownerOf G k key R c.st e ∈ (e : Sym2 V) ∧ ownerOf G k key R c.st e ∈ cover R c.st := by
    intro e
    obtain ⟨y, hy, hxy⟩ := ownerOf_spec hex e
    refine ⟨by rw [hy]; exact Sym2.mem_mk_left _ _, ?_⟩
    have := (R.inC_iff c.st _).1 hxy.1
    simpa [cover] using this
  -- the load bound, from Phase 5
  have hload : ∀ v ∈ cover R c.st, oc.unres v = false →
      load G (ownerOf G k key R c.st) v ≤ k := by
    intro v hv hun
    obtain ⟨q₀, q, hq, hq₀, hdone, hfire, hl, hu⟩ := H.phase5 c hr hs v hv
    rw [load_ownerOf hx1, ← hl]
    exact ExecFull.load_le_of_silent hq hq₀ hdone hfire (by rw [hu, hun])
  refine ⟨fun v hv => ?_, hCVC, hx1, hend, hload, fun hall' => ⟨hCVC, fun e => hend e, ?_⟩⟩
  · rw [hcov]; exact hB hv
  · exact fun v hv => hload v hv (hall' v hv)

/-! ### The main theorem -/

/-- **Main theorem: end-to-end correctness of CoverWeave (MIS arm) on a lossy channel.**

Let `G` be the discovered graph `Ĝ*` of the final epoch, connected with at least two nodes, `key`
injective, `k` the capacity. Let `P` be the whole protocol under the synchronous scheduler,
started at `c₀`, read through `R`, and let the loss pattern `L` be random and satisfy Assumption
`asm:loss` for the window `W` of Lemma 4: for every slot `t`, almost surely, the conditional
probability given the history `ℱ t` that every frame of slots `t + 1, …, t + W` is delivered is
at least `ε > 0`. Assume the open parts `OpenHyps` (with the repaired ownership rules: yield
rule, `θ` check on the late path, R2'', R3, R4). Then
1. almost surely the run reaches a silent configuration, and its output is correct
   (`CorrectOutput`: `C ⊇ B`, `C` a connected vertex cover, every edge exactly one owner, an
   endpoint in `C`, `ℓ(v) ≤ k` at every `v ∈ C` that has not reported Unresolved, hence a valid
   pair when no node of `C` reported Unresolved);
2. `Pr[T_sil > jW] ≤ (1 − ε)^j` for every `j`;
3. every silent configuration reachable from `c₀`, under any loss pattern, has a correct output.

"Surely" cannot replace "almost surely": on a channel that loses every frame forever (an
outcome of probability zero under `asm:loss`) no frame of Phase 1a is ever delivered, a node
with an edge never learns its neighbours' decisions, and no protocol of this kind becomes
silent; termination is a statement about the loss process, not about every loss pattern.
Part 3, correctness at silence, holds for every loss pattern.

Source: `04-formaleng.tex`, `asm:loss`, `lem:lossless`, `lem:term`, `lem:cover`, `lem:conn`,
`thm:cap` (b), and the convention that statements refer to `Ĝ*` of the final epoch.

Modelling choices:
* `G : SimpleGraph V` on a `Fintype` is `Ĝ*`; the paper's standing restriction to silent runs
  that end in one epoch is built in, since every layer hypothesis is stated on this one `G`.
* The whole protocol is an arbitrary `SyncProtocol` (synchronous slots, at most one frame per
  ordered pair per slot, the loss pattern decides delivery); silence is `Exec.Silent`, which
  includes that a closed DONE node does not beacon (`ExecSilence.lean`).
* The cover is `{v | role ≠ OUT}`, the backbone `{v | role ∈ {MIS, CONNECTOR}}`; ownership is the
  re-derived `Owns` of `ExecFullOwnership.lean`, and the owner map picks the owning end.
* Probabilities are in `ℝ≥0∞`; `Pr[T_sil > jW]` is the event "not silent at any slot up to `jW`".

Open hypotheses (fields of `OpenHyps`) and the manuscript statement each corresponds to:
* `window` (H_window): Lemma 4 `lem:lossless` for the whole protocol.
* `phase1` (H_phase1): that the run of Phases 1a and 1b is the one of Algorithms `alg:mis` and
  `alg:connector` (refinement); with `run_sound` and `connector_sound` it gives the MIS part of
  `lem:backbone` at silence and the distance-two step of `lem:conn`.
* `gap3` (H_gap3): the distance-three step of the proof of `lem:conn` ("a silent configuration
  ... has `y ∈ C`").
* `phase2` (H_phase2): the Phase 2 and Phase 3 step of the proof of `lem:cover`.
* `echo` (H_echo): "every frozen neighbor has echoed the role and forced load that a node
  advertises" in the proof of `thm:cap` (b), as a refinement of the echo model.
* `transfer` (H_transfer): "the absence of open requests in DONE settle every transfer" in the
  proof of `thm:cap` (b), as a refinement of the one-edge transfer model under R2''; it replaces
  the paper's hypothesis "every accepted transfer was acknowledged". One network run of the
  transfer layer that is quiet on the cover's edges discharges it (`transfer_of_netRun`).
* `phase5` (H_phase5): "a node turns QUIET only with `ℓ(v) ≤ k` or Unresolved", as a
  refinement of the Phase 5 model, at the nodes of `C`.
* `hadapt`, `hGood` (H_meas): measurability of "not silent at slot `t`" for the history `ℱ t`
  and of the window event, which the paper leaves implicit.
-/
theorem coverweave_correct (hkey : Function.Injective key) (hG : G.Connected)
    (hcard : 2 ≤ Fintype.card V) (P : Exec.SyncProtocol V S M) (c₀ : Exec.SCfg V S M)
    (R : Readout V S) {W : ℕ} (H : OpenHyps G k key P c₀ R W)
    {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
    (ℱ : Filtration ℕ m0) (L : Ω → Exec.LossPattern V) {ε : ℝ} (hε : 0 < ε)
    (hadapt : ∀ t, MeasurableSet[ℱ t] {ω | Exec.srun P (L ω) c₀ t ∉ {c | Exec.Silent P c}})
    (hGood : ∀ t, MeasurableSet (Exec.goodWindow L W t))
    (hce : ∀ t, ∀ᵐ ω ∂μ,
      ε ≤ (μ[(Exec.goodWindow L W t).indicator (fun _ => (1 : ℝ)) | ℱ t]) ω) :
    (∀ᵐ ω ∂μ, ∃ t, Exec.Silent P (Exec.srun P (L ω) c₀ t) ∧
      CorrectOutput G k key R (Exec.srun P (L ω) c₀ t).st) ∧
    (∀ j, μ {ω | ∀ t ≤ j * W, ¬ Exec.Silent P (Exec.srun P (L ω) c₀ t)} ≤
      (1 - ENNReal.ofReal ε) ^ j) ∧
    (∀ c, Exec.Reachable P c₀ c → Exec.Silent P c → CorrectOutput G k key R c.st) := by
  have hT := Exec.term_of_lossFreeWindow P c₀ H.window ℱ L hε hadapt hGood hce
  have hC : ∀ c, Exec.Reachable P c₀ c → Exec.Silent P c → CorrectOutput G k key R c.st :=
    fun c hr hs => correct_of_silent hkey hG hcard H hr hs
  refine ⟨?_, hT.2, hC⟩
  rw [ae_iff]
  refine measure_mono_null (fun ω hω => ?_) hT.1
  simp only [Set.mem_ofPred_eq, not_exists, not_and] at hω ⊢
  exact fun t hs => hω t hs (hC _ ⟨L ω, t, rfl⟩ hs)

/-- **Corollary: probability one.** Under the hypotheses of `coverweave_correct`, a run of the MIS
arm almost surely becomes silent with a correct output. -/
theorem coverweave_correct_ae (hkey : Function.Injective key) (hG : G.Connected)
    (hcard : 2 ≤ Fintype.card V) (P : Exec.SyncProtocol V S M) (c₀ : Exec.SCfg V S M)
    (R : Readout V S) {W : ℕ} (H : OpenHyps G k key P c₀ R W)
    {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
    (ℱ : Filtration ℕ m0) (L : Ω → Exec.LossPattern V) {ε : ℝ} (hε : 0 < ε)
    (hadapt : ∀ t, MeasurableSet[ℱ t] {ω | Exec.srun P (L ω) c₀ t ∉ {c | Exec.Silent P c}})
    (hGood : ∀ t, MeasurableSet (Exec.goodWindow L W t))
    (hce : ∀ t, ∀ᵐ ω ∂μ,
      ε ≤ (μ[(Exec.goodWindow L W t).indicator (fun _ => (1 : ℝ)) | ℱ t]) ω) :
    ∀ᵐ ω ∂μ, ∃ t, Exec.Silent P (Exec.srun P (L ω) c₀ t) ∧
      CorrectOutput G k key R (Exec.srun P (L ω) c₀ t).st :=
  (coverweave_correct hkey hG hcard P c₀ R H ℱ L hε hadapt hGood hce).1

/-! ### The hypotheses can hold together -/

section Example

/-- A protocol on two nodes that never sends: every node keeps its role. -/
def exP : Exec.SyncProtocol (Fin 2) Role Unit := ⟨fun _ s _ => (s, fun _ => none)⟩

/-- Its start: node `0` is MIS, node `1` is COVER, nothing in flight. -/
def exC₀ : Exec.SCfg (Fin 2) Role Unit := ⟨![.mis, .cover], fun _ _ => none⟩

/-- The readout: the state is the role; every record is accurate, no transfer was settled, no
forced load, nothing Unresolved. -/
def exR : Readout (Fin 2) Role where
  role := id
  own st := ⟨fun v => decide (st v ≠ .out), fun _ => 0, fun _ _ => true, fun _ _ => 0,
    fun _ _ => none, fun _ => false, fun _ => false⟩
  inC_iff st v := by simp

theorem exC₀_silent : Exec.Silent exP exC₀ := ⟨fun _ _ => rfl, fun _ => rfl⟩

theorem ex_reach {c : Exec.SCfg (Fin 2) Role Unit} (h : Exec.Reachable exP exC₀ c) : c = exC₀ := by
  obtain ⟨ok, t, rfl⟩ := h
  induction t with
  | zero => rfl
  | succ t ih => exact (congrArg _ ih).trans (Exec.sslot_of_silent exP ok _ exC₀_silent)

/-- **Non-vacuity.** On the edge `0 — 1` (`⊤` on `Fin 2`, connected, two nodes, injective key,
`k = 2`), the never-sending protocol with roles MIS, COVER satisfies every field of `OpenHyps`
with `W = 0`. -/
example : (⊤ : SimpleGraph (Fin 2)).Connected ∧ 2 ≤ Fintype.card (Fin 2) ∧
    Function.Injective (fun i : Fin 2 => (i : ℕ)) ∧
    OpenHyps (⊤ : SimpleGraph (Fin 2)) 2 (fun i : Fin 2 => (i : ℕ)) exP exC₀ exR 0 := by
  have h0 : keyGreedy (⊤ : SimpleGraph (Fin 2)) (fun i : Fin 2 => (i : ℕ)) 0 :=
    (keyGreedy_iff _ _ 0).2 ⟨⟨1, by simp⟩, fun u _ hlt => by fin_cases u <;> simp at hlt⟩
  have h1 : ¬ keyGreedy (⊤ : SimpleGraph (Fin 2)) (fun i : Fin 2 => (i : ℕ)) 1 := fun h =>
    ((keyGreedy_iff _ _ 1).1 h).2 0 (by simp) (by simp) h0
  have hd := Exec.allDone_of_lossFree (G := (⊤ : SimpleGraph (Fin 2)))
    (key := fun i : Fin 2 => (i : ℕ)) Exec.lossless Exec.always Exec.always 0
    (fun _ _ _ _ _ => rfl) (fun _ _ _ _ => rfl) (fun _ _ _ _ => rfl)
  refine ⟨SimpleGraph.connected_top, by simp, fun a b h => Fin.ext h, ⟨?_, ?_, ?_, ?_, ?_, ?_, ?_⟩⟩
  · intro c hc ok _
    rw [ex_reach hc]; exact exC₀_silent
  · intro c hc _
    obtain rfl := ex_reach hc
    refine ⟨Exec.lossless, Exec.always, Exec.always, _, hd, fun v => ?_,
      fun v _ => by fin_cases v <;> decide⟩
    rw [Exec.run_sound _ _ _ v (decided_of_done _ v (hd v)), Exec.truth_eq_mis_iff]
    fin_cases v
    · simpa [exR, exC₀] using h0
    · simpa [exR, exC₀] using h1
  · intro c hc _ x _ y _ _ _ _ _ _
    obtain rfl := ex_reach hc
    fin_cases y <;> simp [exR, exC₀]
  · intro c hc _ u v _ hv
    obtain rfl := ex_reach hc
    fin_cases v <;> simp [exR, exC₀] at hv
  · intro c hc _ x u _
    obtain rfl := ex_reach hc
    refine ⟨_, fun _ => (true, 0),
      (((Relation.ReflTransGen.refl.tail (ExecFull.EStep.hello _ true)).tail
        (ExecFull.EStep.recvHello _ 0 [] rfl)).tail (ExecFull.EStep.echo _ 0 rfl)).tail
        (ExecFull.EStep.recvEcho _ 0 [] rfl), rfl, rfl, ⟨0, rfl, rfl, rfl⟩, ?_, rfl⟩
    fin_cases x <;> rfl
  · intro c hc _ v u _ _ _ _
    obtain rfl := ex_reach hc
    exact ⟨true, false, [], _, rfl, rfl, rfl, rfl⟩
  · intro c hc _ v _
    obtain rfl := ex_reach hc
    set L := ExecFull.loadOf (⊤ : SimpleGraph (Fin 2)) 2 (fun i : Fin 2 => (i : ℕ))
      (exR.own exC₀.st) v
    have hL : L ≤ 2 := by
      unfold L ExecFull.loadOf; exact (Finset.card_le_univ _).trans (by simp)
    exact ⟨⟨.own, L, false, false⟩, _, (Relation.ReflTransGen.refl.tail
      (ExecFull.Q5Step.quiet _ rfl (Or.inl hL))).tail (ExecFull.Q5Step.done _ rfl),
      rfl, rfl, by simp, rfl, rfl⟩

end Example

end SwarmInfer.CoverWeave.Main

open SwarmInfer.CoverWeave.Main in
#print axioms correct_of_silent
open SwarmInfer.CoverWeave.Main in
#print axioms coverweave_correct
open SwarmInfer.CoverWeave.Main in
#print axioms coverweave_correct_ae
open SwarmInfer.CoverWeave.Main in
#print axioms transfer_of_netRun
