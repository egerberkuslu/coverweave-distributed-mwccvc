import Mathlib

/-!
# CoverWeave, epochs: when DONE survives the restart rule, and the restart storm

Source: `ccvc/bb/bootstrap.py` of `bbcvc-release` (branch `m7-collector`, identical on
`r2r3-repair` and the frozen tag): `_gate` (a node past the freeze whose set of verified links has
differed from its frozen set for `_restart_wait_ms` raises the epoch and resets, `epoch_bump`,
reason `bidir_changed`, around line 945), `_on_hello` (a node that hears a larger epoch adopts it
and resets, `epoch_adopt`, around line 673), `_reset_to_phase0` (the reset clears every verified
link and restarts the handshakes), `on_timer` (the stability window restarts whenever the verified
set changes), and Amendment 18 of `contract/R1_PREREG.md` (the restart storm at `n = 50`, stated
there as a liveness limitation of both versions).

The model `run` (synchronous slots, every HELLO heard, a fixed radio graph `G`): a node holds an
epoch, its frozen view (none in phase 0), its verified set `view`, the age of its view, the slots
for which the view has differed from the frozen one, and the flag DONE. In a slot a node that
hears a larger epoch adopts the largest and resets; otherwise the links that complete their
handshake in that slot (`Env.ver`, a free choice, restricted to neighbours) join its view; in phase
0 it freezes its view once the view has been unchanged for `tstab` slots; past the freeze it
raises its epoch and resets once its view has differed from the frozen one for `wait` slots, and
while the two agree the rest of the protocol may finish it (`Env.fin`, a free choice).

* `done_stable`, `done_forever_iff`: **the condition.** From a configuration in which every node
  is DONE in one epoch with its view equal to its frozen view, every node stays DONE at every later
  slot if and only if no handshake adds a link to any node's view at any later slot. One late
  verification anywhere, even of a link of the fixed radio graph, ends DONE.
* `done_forever_iff_complete`: with fair handshakes (every missing link of the radio graph is
  completed at some later slot), DONE survives the restart rule if and only if, when every node is
  DONE, every frozen view already holds all radio neighbours of its node.
* `restart_spreads`: one restart undoes DONE everywhere: if every node is in epoch `e` or lower at
  slot `t` and some node `v` raises its epoch in slot `t`, then every node `u` is not DONE at some
  slot in `(t, t + 1 + dist v u]`.
* Non-vacuity: `a_allDone`, `a_complete`, `a_fair`, `a_done_forever` (two nodes that verify at
  once are DONE for good from slot 4), and the storm for `restart_spreads`.
* **Loss-free epochs behind the freeze gate (Lemma 4, epoch part).** With the gate of G4
  (`Env.pend`, `_pending_links`) and the two hypotheses read off the code for a loss-free window
  from slot `T` with gates that keep their state (`hM`: only links gated open at both ends are
  verified; `hG4`: in an epoch entered at a slot `≥ T`, a node that passes the freeze gate has
  verified all of them), `fresh_complete`: every such epoch freezes with the complete view and
  never counts a difference; `fresh_no_storm`: once every node is in such an epoch, no epoch rises
  above the largest one of that slot, so the storm is impossible; `fresh_done_forever`: DONE in
  one such epoch is DONE for good. `storm_breaks_G4`: the storm violates exactly `hG4`. The gated
  two-node run `bE` is the non-vacuity example (`b_hG4`, `b_done_forever`).
* `storm_*`: **the restart storm as a counterexample to a naive liveness claim.** Two nodes on one
  edge, nothing in the radio graph ever changes, and every handshake completes at each end at least
  once in every 5 slots (`storm_fair`); end 1 completes its handshake only once it is DONE (a link
  verified after the freeze, the case of G4 in `bootstrap.py`). The run raises its epoch every 5
  slots for ever (`storm_epoch`), each node is DONE again and again (`storm_done_io`), but from
  slot 10 on the two are never DONE in the same slot (`storm_never_both`), so the run never
  converges (`storm_not_converged`), although every node was DONE at some slot. So "fixed radio
  graph and every handshake completing within a bound" does not give liveness, and "every node
  has been DONE once" does not mean convergence (the collector defect of Amendment 18).

Modelling choices: time is slots; every node hears every neighbour's HELLO in every slot (the
storm needs no loss); epochs are unwrapped natural numbers (the code's 1-byte epoch with
`epoch_newer` behaves the same while fewer than 128 epochs are in flight); the stability window
and the restart wait are counted in slots; the handshakes, the neighbour tables, the expiry of
records and Phases 1 to 5 are abstracted to `Env.ver` (when a link becomes verified at an end) and
`Env.fin` (when a frozen node with an agreeing view becomes DONE); the freeze gate's wait for
heard but unverified links (G4, `link_rounds_max` rounds) is folded into `tstab`, so the storm
needs a handshake slower than the whole wait of the gate, which Amendment 18 reports under the
contention of 50 stations; a link once verified is not removed within an epoch (no expiry: the
radio graph is fixed), which only makes the storm harder.
-/

namespace SwarmInfer.CoverWeave.Epoch

/-- Stability window and restart wait, in slots. -/
structure Params where
  tstab : ℕ
  wait : ℕ

/-- The state of a node. -/
structure ENode (V : Type) where
  ep : ℕ
  fr : Option (Finset V)
  view : Finset V
  age : ℕ
  dif : Option ℕ
  done : Bool
  deriving DecidableEq

variable {V : Type} [Fintype V] [DecidableEq V]

/-- `_reset_to_phase0` in epoch `e`. -/
def reset (e : ℕ) : ENode V := ⟨e, none, ∅, 0, none, false⟩

/-- The free choices: the links whose handshake completes at `v` in slot `t`, and whether the rest
of the protocol finishes `v`. -/
structure Env (V : Type) where
  ver : ℕ → V → ENode V → Finset V
  fin : ℕ → V → ENode V → Bool
  /-- A handshake is still owed: the freeze gate waits (`_pending_links`, G4). -/
  pend : ℕ → V → ENode V → Bool

variable (P : Params) (G : SimpleGraph V) [DecidableRel G.Adj]

def nbrs (v : V) : Finset V := Finset.univ.filter (G.Adj v)

/-- The largest epoch `v` hears. -/
def nbrMax (c : V → ENode V) (v : V) : ℕ := (nbrs G v).sup fun u => (c u).ep

/-- The verified set becomes `w`; its age restarts if it changed. -/
def upd (n : ENode V) (w : Finset V) : ENode V :=
  { n with view := w, age := if w = n.view then n.age + 1 else 0 }

/-- One slot at a node that hears no larger epoch, with new verified set `w` and the protocol's
choice `f` to finish it. -/
def stepL (n : ENode V) (w : Finset V) (p f : Bool) : ENode V :=
  match n.fr with
  | none => if P.tstab ≤ (upd n w).age ∧ p = false then { upd n w with fr := some w } else upd n w
  | some F =>
    if w = F then { upd n w with dif := none, done := n.done || f }
    else
      match n.dif with
      | none => { upd n w with dif := some 0 }
      | some k => if P.wait ≤ k + 1 then reset (n.ep + 1) else { upd n w with dif := some (k + 1) }

/-- One slot at node `v`: adopt a larger epoch and reset, or `stepL`. -/
def step (E : Env V) (t : ℕ) (c : V → ENode V) (v : V) : ENode V :=
  if (c v).ep < nbrMax G c v then reset (nbrMax G c v)
  else stepL P (c v) ((c v).view ∪ (E.ver t v (c v) ∩ nbrs G v)) (E.pend t v (c v)) (E.fin t v (c v))

def run (E : Env V) (c₀ : V → ENode V) : ℕ → V → ENode V
  | 0 => c₀
  | t + 1 => fun v => step P G E t (run E c₀ t) v

/-- Every node is DONE in epoch `e`, with its view equal to its frozen view. -/
def AllDone (c : V → ENode V) (e : ℕ) : Prop :=
  ∀ v, (c v).ep = e ∧ (c v).done = true ∧ (c v).fr = some (c v).view ∧ (c v).dif = none

/-! ### Facts of one slot -/

variable {P G}

omit [DecidableEq V] in
theorem nbrMax_le {c : V → ENode V} {e : ℕ} (h : ∀ u, (c u).ep ≤ e) (v : V) : nbrMax G c v ≤ e :=
  Finset.sup_le fun u _ => h u

omit [DecidableEq V] in
theorem le_nbrMax {c : V → ENode V} {v u : V} (h : G.Adj v u) : (c u).ep ≤ nbrMax G c v :=
  Finset.le_sup (f := fun u => (c u).ep) (by simp [nbrs, h])

omit [Fintype V] in
theorem stepL_cases (n : ENode V) (w : Finset V) (p f : Bool) :
    stepL P n w p f = reset (n.ep + 1) ∨
      ((stepL P n w p f).ep = n.ep ∧ (stepL P n w p f).view = w ∧
        ∀ F, n.fr = some F → (stepL P n w p f).fr = some F) := by
  unfold stepL
  rcases hf : n.fr with _ | F
  · simp only
    split_ifs <;> simp [upd]
  · simp only
    split_ifs
    · simp [upd, hf]
    · rcases hd : n.dif with _ | k
      · simp [upd, hf]
      · simp only
        split_ifs
        · simp
        · simp [upd, hf]

omit [Fintype V] in
theorem stepL_done (n : ENode V) (w : Finset V) (p f : Bool) (h : (stepL P n w p f).done = true) :
    (stepL P n w p f).ep = n.ep ∧ (stepL P n w p f).view = w ∧
      ∀ F, n.fr = some F → (stepL P n w p f).fr = some F := by
  rcases stepL_cases (P := P) n w p f with h' | h'
  · rw [h'] at h; simp [reset] at h
  · exact h'

omit [Fintype V] in
theorem stepL_dif (n : ENode V) (w : Finset V) (p f : Bool) {F : Finset V} (hf : n.fr = some F)
    (hw : w ≠ F) (h : (stepL P n w p f).done = true) :
    (stepL P n w p f).dif = some (n.dif.elim 0 (· + 1)) ∧ ∀ k, n.dif = some k → k + 1 < P.wait := by
  revert h
  unfold stepL
  simp only [hf, hw, ↓reduceIte]
  rcases hd : n.dif with _ | k
  · simp [upd]
  · simp only
    split_ifs with hk
    · simp [reset]
    · intro _
      refine ⟨rfl, fun k' hk' => ?_⟩
      obtain rfl := Option.some.inj hk'
      omega

/-- The epoch never falls below what the node hears or held. -/
theorem step_ep_ge (E : Env V) (t : ℕ) (c : V → ENode V) (v : V) :
    (c v).ep ≤ (step P G E t c v).ep ∧ nbrMax G c v ≤ (step P G E t c v).ep := by
  unfold step
  split_ifs with h
  · simp [reset]; omega
  · rcases stepL_cases (P := P) (c v) ((c v).view ∪ (E.ver t v (c v) ∩ nbrs G v)) (E.pend t v (c v))
      (E.fin t v (c v)) with h' | h'
    · rw [h']; simp [reset]; omega
    · rw [h'.1]; omega

/-- A slot that raises the epoch is a reset, so it ends DONE. -/
theorem step_done_of_ep (E : Env V) (t : ℕ) (c : V → ENode V) (v : V)
    (h : (c v).ep < (step P G E t c v).ep) : (step P G E t c v).done = false := by
  revert h
  unfold step
  split_ifs with h0
  · intro; rfl
  · rcases stepL_cases (P := P) (c v) ((c v).view ∪ (E.ver t v (c v) ∩ nbrs G v)) (E.pend t v (c v))
      (E.fin t v (c v)) with h' | h'
    · rw [h']; intro; rfl
    · rw [h'.1]; intro h; omega

/-- A slot that ends DONE is not a reset: the node hears no larger epoch, keeps its epoch and its
frozen view, and its view only grows. -/
theorem step_done_keep (E : Env V) (t : ℕ) (c : V → ENode V) (v : V)
    (h : (step P G E t c v).done = true) :
    ¬ (c v).ep < nbrMax G c v ∧ (step P G E t c v).ep = (c v).ep ∧
      (step P G E t c v).view = (c v).view ∪ (E.ver t v (c v) ∩ nbrs G v) ∧
      (∀ F, (c v).fr = some F → (step P G E t c v).fr = some F) := by
  revert h
  unfold step
  split_ifs with h0
  · simp [reset]
  · intro h
    exact ⟨h0, stepL_done (P := P) _ _ _ _ h⟩

theorem step_dif (E : Env V) (t : ℕ) (c : V → ENode V) (v : V) {F : Finset V}
    (hf : (c v).fr = some F) (hw : (c v).view ∪ (E.ver t v (c v) ∩ nbrs G v) ≠ F)
    (h : (step P G E t c v).done = true) :
    (step P G E t c v).dif = some ((c v).dif.elim 0 (· + 1)) ∧
      ∀ k, (c v).dif = some k → k + 1 < P.wait := by
  have h0 := (step_done_keep E t c v h).1
  revert h
  unfold step
  simp only [h0, ↓reduceIte]
  exact stepL_dif (P := P) _ _ _ _ hf hw

/-! ### The condition under which DONE survives -/

/-- With every node DONE in one epoch and no new link, a slot keeps every node DONE, its view and
its frozen view. -/
theorem step_still (E : Env V) (t : ℕ) {c : V → ENode V} {e : ℕ} (H : AllDone c e) (v : V)
    (hv : E.ver t v (c v) ∩ nbrs G v ⊆ (c v).view) :
    (step P G E t c v).ep = e ∧ (step P G E t c v).done = true ∧
      (step P G E t c v).fr = some (c v).view ∧ (step P G E t c v).view = (c v).view ∧
      (step P G E t c v).dif = none := by
  obtain ⟨h1, h2, h3, h4⟩ := H v
  have hm : ¬ (c v).ep < nbrMax G c v := by
    have := nbrMax_le (G := G) (fun u => (H u).1.le) v; omega
  have hw : (c v).view ∪ (E.ver t v (c v) ∩ nbrs G v) = (c v).view := Finset.union_eq_left.2 hv
  unfold step stepL
  simp only [hm, hw, h3, h2, Bool.true_or, upd, ↓reduceIte]
  simp [h1]

/-- DONE up to slot `s` needs no new link before `s` only. -/
theorem done_stable_upto {E : Env V} {c₀ : V → ENode V} {t₀ e : ℕ} (H : AllDone (run P G E c₀ t₀) e) :
    ∀ j, (∀ s, t₀ ≤ s → s < t₀ + j → ∀ v,
      E.ver s v (run P G E c₀ s v) ∩ nbrs G v ⊆ (run P G E c₀ s v).view) →
      AllDone (run P G E c₀ (t₀ + j)) e ∧ ∀ v, (run P G E c₀ (t₀ + j) v).view = (run P G E c₀ t₀ v).view := by
  intro j
  induction j with
  | zero => intro _; exact ⟨H, fun _ => rfl⟩
  | succ j ih =>
    intro hver
    obtain ⟨Hj, hvj⟩ := ih fun s h1 h2 => hver s h1 (by omega)
    have hr : ∀ v, run P G E c₀ (t₀ + (j + 1)) v =
        step P G E (t₀ + j) (run P G E c₀ (t₀ + j)) v := fun v => rfl
    have K := fun v => step_still (P := P) E (t₀ + j) Hj v (hver _ (by omega) (by omega) v)
    refine ⟨fun v => ?_, fun v => ?_⟩
    · rw [hr]
      obtain ⟨k1, k2, k3, k4, k5⟩ := K v
      exact ⟨k1, k2, by rw [k3, k4], k5⟩
    · rw [hr, (K v).2.2.2.1, hvj v]

/-- **DONE is stable when no link is added.** If every node is DONE in epoch `e` at slot `t₀` with
its view equal to its frozen view, and from `t₀` on no handshake adds a link to any view, every
node stays DONE in epoch `e`, with the same view, at every later slot. -/
theorem done_stable {E : Env V} {c₀ : V → ENode V} {t₀ e : ℕ} (H : AllDone (run P G E c₀ t₀) e)
    (hver : ∀ s, t₀ ≤ s → ∀ v, E.ver s v (run P G E c₀ s v) ∩ nbrs G v ⊆ (run P G E c₀ s v).view) :
    ∀ s, t₀ ≤ s → AllDone (run P G E c₀ s) e ∧ ∀ v, (run P G E c₀ s v).view = (run P G E c₀ t₀ v).view := by
  intro s hs
  obtain ⟨j, rfl⟩ := Nat.exists_eq_add_of_le hs
  exact done_stable_upto H j fun s h1 _ => hver s h1

/-- **One late link ends DONE.** If every node is DONE in one epoch at slot `t₀` with its view
equal to its frozen view and every node is DONE at every later slot, then no handshake adds a link
to any view after `t₀`. -/
theorem ver_of_done_forever {E : Env V} {c₀ : V → ENode V} {t₀ e : ℕ}
    (H : AllDone (run P G E c₀ t₀) e)
    (hd : ∀ s, t₀ ≤ s → ∀ v, (run P G E c₀ s v).done = true) :
    ∀ s, t₀ ≤ s → ∀ v, E.ver s v (run P G E c₀ s v) ∩ nbrs G v ⊆ (run P G E c₀ s v).view := by
  -- every slot after `t₀` ends DONE, so none is a reset
  have hk : ∀ s, t₀ ≤ s → ∀ v, (run P G E c₀ s v).fr = (run P G E c₀ t₀ v).fr ∧
      (run P G E c₀ t₀ v).view ⊆ (run P G E c₀ s v).view := by
    intro s hs v
    obtain ⟨j, rfl⟩ := Nat.exists_eq_add_of_le hs
    induction j with
    | zero => exact ⟨rfl, le_rfl⟩
    | succ j ih =>
      obtain ⟨i1, i2⟩ := ih (by omega)
      have hr : run P G E c₀ (t₀ + (j + 1)) v =
          step P G E (t₀ + j) (run P G E c₀ (t₀ + j)) v := rfl
      have hdj := hd (t₀ + (j + 1)) (by omega) v
      rw [hr] at hdj ⊢
      obtain ⟨-, -, k3, k4⟩ := step_done_keep (P := P) (G := G) E (t₀ + j) _ v hdj
      have hF := (H v).2.2.1
      refine ⟨(k4 _ (i1.trans hF)).trans hF.symm, i2.trans ?_⟩
      rw [k3]; exact Finset.subset_union_left
  by_contra hcon
  push Not at hcon
  obtain ⟨s₁, hs₁, v, hnew⟩ := hcon
  set F := (run P G E c₀ t₀ v).view with hFdef
  have hfr : ∀ s, t₀ ≤ s → (run P G E c₀ s v).fr = some F := fun s hs =>
    (hk s hs v).1.trans (H v).2.2.1
  -- the view grows past `F` at `s₁` and stays apart from it
  have hgrow : ∀ s, s₁ ≤ s → (run P G E c₀ s v).view ∪
      (E.ver s v (run P G E c₀ s v) ∩ nbrs G v) ≠ F ∧ F ⊆ (run P G E c₀ s v).view := by
    intro s hs
    obtain ⟨j, rfl⟩ := Nat.exists_eq_add_of_le hs
    induction j with
    | zero =>
      refine ⟨fun h => hnew ?_, (hk s₁ hs₁ v).2⟩
      have hsub := (hk s₁ hs₁ v).2
      intro x hx
      have : x ∈ F := h ▸ Finset.mem_union_right _ hx
      exact hsub this
    | succ j ih =>
      obtain ⟨i1, i2⟩ := ih (by omega)
      have hstep : (run P G E c₀ (s₁ + j + 1) v) = step P G E (s₁ + j) (run P G E c₀ (s₁ + j)) v := rfl
      have hview : (run P G E c₀ (s₁ + j + 1) v).view =
          (run P G E c₀ (s₁ + j) v).view ∪ (E.ver (s₁ + j) v (run P G E c₀ (s₁ + j) v) ∩ nbrs G v) := by
        rw [hstep]
        exact (step_done_keep E _ _ v (hd (s₁ + j + 1) (by omega) v)).2.2.1
      have hne : (run P G E c₀ (s₁ + j + 1) v).view ≠ F := by rw [hview]; exact i1
      have hsub : F ⊆ (run P G E c₀ (s₁ + j + 1) v).view := by
        rw [hview]; exact i2.trans Finset.subset_union_left
      refine ⟨fun h => hne (le_antisymm ?_ hsub), hsub⟩
      rw [← h]; exact Finset.subset_union_left
  -- the counter of the difference grows by one per slot, and cannot pass `wait`
  have hcnt : ∀ j, ((run P G E c₀ (s₁ + 1 + j) v).dif.elim 0 (· + 1)) ≥ j + 1 := by
    intro j
    induction j with
    | zero =>
      have := (step_dif (P := P) E s₁ _ v (hfr s₁ hs₁) (hgrow s₁ le_rfl).1 (hd (s₁ + 1) (by omega) v)).1
      have h' : (run P G E c₀ (s₁ + 1 + 0) v).dif = some _ := this
      rw [h']; simp
    | succ j ih =>
      have := (step_dif (P := P) E (s₁ + 1 + j) _ v (hfr _ (by omega))
        (hgrow _ (by omega)).1 (hd (s₁ + 1 + j + 1) (by omega) v)).1
      have h' : (run P G E c₀ (s₁ + 1 + (j + 1)) v).dif = some _ := this
      rw [h']
      show ((run P G E c₀ (s₁ + 1 + j) v).dif.elim 0 (· + 1)) + 1 ≥ j + 1 + 1
      omega
  have hlast := (step_dif (P := P) E (s₁ + 1 + P.wait) _ v (hfr _ (by omega))
    (hgrow _ (by omega)).1 (hd (s₁ + 1 + P.wait + 1) (by omega) v)).2
  have hc := hcnt P.wait
  cases hdv : (run P G E c₀ (s₁ + 1 + P.wait) v).dif with
  | none => rw [hdv] at hc; simp at hc
  | some k =>
    rw [hdv] at hc; simp only [Option.elim] at hc
    have := hlast k hdv; omega

/-- **The condition, as an equivalence.** From a configuration in which every node is DONE in one
epoch with its view equal to its frozen view, every node is DONE at every later slot if and only if
no handshake adds a link to any view at any later slot. -/
theorem done_forever_iff {E : Env V} {c₀ : V → ENode V} {t₀ e : ℕ}
    (H : AllDone (run P G E c₀ t₀) e) :
    (∀ s, t₀ ≤ s → ∀ v, (run P G E c₀ s v).done = true) ↔
      ∀ s, t₀ ≤ s → ∀ v, E.ver s v (run P G E c₀ s v) ∩ nbrs G v ⊆ (run P G E c₀ s v).view :=
  ⟨ver_of_done_forever H, fun h s hs v => ((done_stable H h s hs).1 v).2.1⟩

/-- `done_stable` with the new links measured against the views of `t₀`. -/
theorem done_stable' {E : Env V} {c₀ : V → ENode V} {t₀ e : ℕ} (H : AllDone (run P G E c₀ t₀) e)
    (hver : ∀ s, t₀ ≤ s → ∀ v, E.ver s v (run P G E c₀ s v) ∩ nbrs G v ⊆ (run P G E c₀ t₀ v).view) :
    ∀ s, t₀ ≤ s → AllDone (run P G E c₀ s) e ∧ ∀ v, (run P G E c₀ s v).view = (run P G E c₀ t₀ v).view := by
  intro s hs
  obtain ⟨j, rfl⟩ := Nat.exists_eq_add_of_le hs
  induction j using Nat.strong_induction_on with
  | _ j ih =>
    refine done_stable_upto H j fun s h1 h2 v => ?_
    obtain ⟨i, rfl⟩ := Nat.exists_eq_add_of_le h1
    rw [((ih i (by omega) (by omega)).2 v)]
    exact hver _ h1 v

/-- **The condition under fair handshakes.** Let every link of the radio graph that a node misses
be completed by its handshake at some later slot (`hfair`). From a configuration in which every
node is DONE in one epoch with its view equal to its frozen view, every node is DONE at every later
slot if and only if every node's frozen view already holds all its radio neighbours. A node that
froze with a link still unverified restarts the whole network (`restart_spreads`). -/
theorem done_forever_iff_complete {E : Env V} {c₀ : V → ENode V} {t₀ e : ℕ}
    (H : AllDone (run P G E c₀ t₀) e)
    (hfair : ∀ v u, G.Adj v u → ∀ s, ∃ s', s ≤ s' ∧
      u ∈ E.ver s' v (run P G E c₀ s' v) ∪ (run P G E c₀ s' v).view) :
    (∀ s, t₀ ≤ s → ∀ v, (run P G E c₀ s v).done = true) ↔
      ∀ v, nbrs G v ⊆ (run P G E c₀ t₀ v).view := by
  constructor
  · intro hd v u hu
    have hadj : G.Adj v u := by simpa [nbrs] using hu
    have hver := (done_forever_iff H).1 hd
    have hst := done_stable H hver
    obtain ⟨s', hs', hmem⟩ := hfair v u hadj t₀
    rcases Finset.mem_union.1 hmem with h | h
    · have := hver s' hs' v (Finset.mem_inter.2 ⟨h, hu⟩)
      rwa [(hst s' hs').2 v] at this
    · rwa [(hst s' hs').2 v] at h
  · intro hc s hs v
    exact ((done_stable' H (fun s _ v => Finset.inter_subset_right.trans (hc v)) s hs).1 v).2.1

/-! ### One restart spreads to every node -/

theorem ep_walk {E : Env V} {c₀ : V → ENode V} {x : ℕ} :
    ∀ {a u : V} (p : G.Walk a u) (t : ℕ), x ≤ (run P G E c₀ t a).ep →
      x ≤ (run P G E c₀ (t + p.length) u).ep
  | _, _, .nil, t, h => h
  | _, _, .cons hadj q, t, h => by
    have h1 : x ≤ (run P G E c₀ (t + 1) _).ep :=
      h.trans ((le_nbrMax (c := run P G E c₀ t) hadj.symm).trans (step_ep_ge E t _ _).2)
    have := ep_walk q (t + 1) h1
    rwa [SimpleGraph.Walk.length_cons, show t + (q.length + 1) = t + 1 + q.length by omega]

theorem ep_mono {E : Env V} {c₀ : V → ENode V} (u : V) (t : ℕ) :
    ∀ j, (run P G E c₀ t u).ep ≤ (run P G E c₀ (t + j) u).ep
  | 0 => le_rfl
  | j + 1 => (ep_mono u t j).trans (step_ep_ge E _ _ _).1

/-- **A restart undoes DONE at every node within its distance.** If every node is in epoch `e` or
lower at slot `t` and node `v` raises its epoch above `e` in slot `t`, every node `u` reachable
from `v` is not DONE at some slot in `(t, t + 1 + dist v u]`. (A node that raises its epoch by the
restart rule has had a differing view for a slot, so not every node was in `AllDone` at `t`.) -/
theorem restart_spreads {E : Env V} {c₀ : V → ENode V} {t e : ℕ} {v : V}
    (H : ∀ u, (run P G E c₀ t u).ep ≤ e) (hb : e < (run P G E c₀ (t + 1) v).ep) (u : V)
    (hr : G.Reachable v u) :
    ∃ s, t < s ∧ s ≤ t + 1 + G.dist v u ∧ (run P G E c₀ s u).done = false := by
  obtain ⟨p, hp⟩ := hr.exists_walk_length_eq_dist
  have hu := ep_walk (x := e + 1) p (t + 1) hb
  rw [hp] at hu
  have h0 : (run P G E c₀ t u).ep ≤ e := H u
  -- the epoch of `u` rises in some slot of the window, and that slot is a reset
  have key : ∀ j, e < (run P G E c₀ (t + j) u).ep →
      ∃ i, i < j ∧ (run P G E c₀ (t + i) u).ep < (run P G E c₀ (t + i + 1) u).ep := by
    intro j
    induction j with
    | zero => intro h; rw [Nat.add_zero] at h; omega
    | succ j ih =>
      intro h
      by_cases hj : e < (run P G E c₀ (t + j) u).ep
      · obtain ⟨i, hi, hi'⟩ := ih hj; exact ⟨i, by omega, hi'⟩
      · exact ⟨j, by omega, by
          rw [show t + j + 1 = t + (j + 1) by omega]; omega⟩
  obtain ⟨i, hi, hi'⟩ := key (1 + G.dist v u) (by rw [← Nat.add_assoc]; omega)
  refine ⟨t + i + 1, by omega, by omega, step_done_of_ep E _ _ u hi'⟩

/-! ### The hypotheses can hold -/

/-- One edge between nodes 0 and 1 (also the graph of the storm below). -/
abbrev sG : SimpleGraph (Fin 2) := ⊤

/-- Stability window 2 slots, restart wait 1 slot. -/
def sP : Params := ⟨2, 1⟩

/-- Both ends verify the link in every slot in which it is missing; a frozen node finishes at once. -/
def aE : Env (Fin 2) where
  ver _ v _ := Finset.univ.erase v
  fin _ _ _ := true
  pend _ _ _ := false

def aRun : ℕ → Fin 2 → ENode (Fin 2) := run sP sG aE fun _ => reset 0

theorem a_allDone : AllDone (aRun 4) 0 := by unfold AllDone; decide +kernel

/-- **Non-vacuity of `done_stable`, `done_forever_iff` and `done_forever_iff_complete`.** From slot
4 on, every node is DONE in epoch 0, and every handshake is fair. -/
theorem a_complete : ∀ v, nbrs sG v ⊆ (aRun 4 v).view := by decide +kernel

theorem a_fair : ∀ v u, sG.Adj v u → ∀ s, ∃ s', s ≤ s' ∧ u ∈ aE.ver s' v (aRun s' v) ∪ (aRun s' v).view :=
  fun v u h s => ⟨s, le_rfl, Finset.mem_union_left _ (by simpa [aE] using h.ne.symm)⟩

theorem a_done_forever : ∀ s, 4 ≤ s → ∀ v, (aRun s v).done = true :=
  (done_forever_iff_complete (P := sP) (G := sG) a_allDone a_fair).2 a_complete

example : ∀ s, 4 ≤ s → ∀ v, aE.ver s v (aRun s v) ∩ nbrs sG v ⊆ (aRun s v).view :=
  (done_forever_iff (P := sP) (G := sG) a_allDone).1 a_done_forever

/-! ### The restart storm -/

/-- Node 0 completes its handshake in every slot in which the link is missing; node 1 only once it
is DONE (its link is verified after the freeze). The rest of the protocol finishes a frozen node at
once. Nothing depends on the slot. -/
def sE : Env (Fin 2) where
  ver _ v n := if v = 0 ∨ n.done = true then Finset.univ.erase v else ∅
  fin _ _ _ := true
  pend _ _ _ := false

def sRun : ℕ → Fin 2 → ENode (Fin 2) := run sP sG sE fun _ => reset 0

/-- Every epoch raised by `k`. -/
def shiftC (c : Fin 2 → ENode (Fin 2)) (k : ℕ) : Fin 2 → ENode (Fin 2) :=
  fun v => { c v with ep := (c v).ep + k }

theorem sup_add_const {s : Finset (Fin 2)} (hs : s.Nonempty) (f : Fin 2 → ℕ) (k : ℕ) :
    (s.sup fun u => f u + k) = s.sup f + k := by
  apply le_antisymm
  · exact Finset.sup_le fun u hu => by have := Finset.le_sup (f := f) hu; omega
  · obtain ⟨i, hi, hfi⟩ := Finset.exists_mem_eq_sup s hs f
    rw [hfi]; exact Finset.le_sup (f := fun u => f u + k) hi

omit [Fintype V] in
theorem stepL_shift (n : ENode V) (w : Finset V) (p f : Bool) (k : ℕ) :
    stepL P { n with ep := n.ep + k } w p f = { stepL P n w p f with ep := (stepL P n w p f).ep + k } := by
  obtain ⟨ep, fr, view, age, dif, done⟩ := n
  unfold stepL
  rcases fr with _ | F
  · simp only [upd]; split_ifs <;> simp
  · simp only
    split_ifs
    · simp [upd]
    · rcases dif with _ | j
      · simp [upd]
      · simp only; split_ifs <;> simp [upd, reset]; omega

/-- The slot commutes with raising every epoch. -/
theorem step_shift (t : ℕ) (c : Fin 2 → ENode (Fin 2)) (k : ℕ) (v : Fin 2) :
    step sP sG sE t (shiftC c k) v = { step sP sG sE t c v with ep := (step sP sG sE t c v).ep + k } := by
  have hm : nbrMax sG (shiftC c k) v = nbrMax sG c v + k := by
    unfold nbrMax
    exact sup_add_const (by fin_cases v <;> decide) (fun u => (c u).ep) k
  unfold step
  rw [hm]
  simp only [shiftC, sE, Nat.add_lt_add_iff_right]
  split_ifs <;> first | (simp [reset]; done) | exact stepL_shift (P := sP) _ _ _ _ _

theorem sRun_succ (t : ℕ) : sRun (t + 1) = fun v => step sP sG sE t (sRun t) v := rfl

theorem sRun_shift_step (t : ℕ) (k : ℕ) (c : Fin 2 → ENode (Fin 2)) :
    (fun v => step sP sG sE t (shiftC c k) v) = shiftC (fun v => step sP sG sE t c v) k := by
  funext v; rw [step_shift]; rfl

/-- The step does not read the slot. -/
theorem step_t (t t' : ℕ) (c : Fin 2 → ENode (Fin 2)) (v : Fin 2) :
    step sP sG sE t c v = step sP sG sE t' c v := rfl

theorem storm_base : sRun 15 = shiftC (sRun 10) 1 := by decide +kernel

/-- **The period.** From slot 10 on, five slots raise every epoch by one and change nothing else. -/
theorem storm_period : ∀ t, 10 ≤ t → sRun (t + 5) = shiftC (sRun t) 1 := by
  intro t ht
  obtain ⟨j, rfl⟩ := Nat.exists_eq_add_of_le ht
  induction j with
  | zero => exact storm_base
  | succ j ih =>
    rw [show 10 + (j + 1) + 5 = (10 + j + 5) + 1 by omega, sRun_succ, ih (by omega)]
    rw [show 10 + (j + 1) = (10 + j) + 1 by omega, sRun_succ]
    funext v
    rw [step_t (10 + j + 5) (10 + j), step_shift]
    rfl

theorem shiftC_add (c : Fin 2 → ENode (Fin 2)) (a b : ℕ) :
    shiftC (shiftC c a) b = shiftC c (a + b) := by
  funext v; simp [shiftC, Nat.add_assoc]

theorem storm_iter (t : ℕ) (ht : 10 ≤ t) : ∀ n, sRun (t + 5 * n) = shiftC (sRun t) n
  | 0 => by funext v; simp [shiftC]
  | n + 1 => by
    rw [show t + 5 * (n + 1) = (t + 5 * n) + 5 by ring, storm_period _ (by omega), storm_iter t ht n,
      shiftC_add]

/-- Every slot from 10 on is a slot of `[10, 15)` shifted by whole periods. -/
theorem storm_reduce (t : ℕ) (ht : 10 ≤ t) :
    ∃ r n, 10 ≤ r ∧ r < 15 ∧ t = r + 5 * n :=
  ⟨10 + (t - 10) % 5, (t - 10) / 5, by omega, by omega, by omega⟩

theorem shift_view (c : Fin 2 → ENode (Fin 2)) (n : ℕ) (v : Fin 2) :
    (shiftC c n v).view = (c v).view ∧ (shiftC c n v).done = (c v).done ∧
      (shiftC c n v).ep = (c v).ep + n := ⟨rfl, rfl, rfl⟩

/-- **Fair handshakes.** At every slot from 10 on, each node has its one link verified at some slot
of the next five. -/
theorem storm_fair : ∀ t, 10 ≤ t → ∀ v, ∃ s, t ≤ s ∧ s < t + 5 ∧ (sRun s v).view = nbrs sG v := by
  intro t ht v
  obtain ⟨r, n, h1, h2, rfl⟩ := storm_reduce t ht
  have base : ∀ r, 10 ≤ r → r < 15 → ∀ v, ∃ i, i < 5 ∧ (sRun (r + i) v).view = nbrs sG v := by
    decide +kernel
  obtain ⟨i, hi, hv⟩ := base r h1 h2 v
  refine ⟨r + i + 5 * n, by omega, by omega, ?_⟩
  rw [storm_iter _ (by omega), (shift_view _ _ _).1, hv]

/-- **Restarts for ever.** Every five slots from slot 10 on, every epoch is raised by one. -/
theorem storm_epoch (n : ℕ) (v : Fin 2) : (sRun (10 + 5 * n) v).ep = (sRun 10 v).ep + n := by
  rw [storm_iter _ le_rfl]; rfl

/-- **Each node is DONE again and again.** -/
theorem storm_done_io (N : ℕ) (v : Fin 2) : ∃ t, N ≤ t ∧ (sRun t v).done = true := by
  have base : ∀ v, ∃ i, i < 5 ∧ (sRun (10 + i) v).done = true := by decide +kernel
  obtain ⟨i, -, hv⟩ := base v
  refine ⟨10 + i + 5 * N, by omega, ?_⟩
  rw [storm_iter _ (by omega), (shift_view _ _ _).2.1, hv]

/-- **But never both in the same slot**, from slot 10 on. -/
theorem storm_never_both (t : ℕ) (ht : 10 ≤ t) : ¬ ((sRun t 0).done = true ∧ (sRun t 1).done = true) := by
  obtain ⟨r, n, h1, h2, rfl⟩ := storm_reduce t ht
  have base : ∀ r, 10 ≤ r → r < 15 → ¬ ((sRun r 0).done = true ∧ (sRun r 1).done = true) := by
    decide +kernel
  rw [storm_iter _ h1, (shift_view _ _ _).2.1, (shift_view _ _ _).2.1]
  exact base r h1 h2

/-- **The run never converges**, although every node is DONE at some slot, the radio graph never
changes and every handshake completes at each end at least once in every five slots. -/
theorem storm_not_converged : ¬ ∃ T, ∀ t, T ≤ t → ∀ v, (sRun t v).done = true := by
  rintro ⟨T, hT⟩
  exact storm_never_both (max T 10) (le_max_right _ _)
    ⟨hT _ (le_max_left _ _) 0, hT _ (le_max_left _ _) 1⟩

/-- **The naive liveness claim is false**: "if the radio graph is fixed, every handshake completes
within a bound and every node is DONE at some slot, the network is eventually DONE for good". -/
theorem naive_liveness_false :
    ¬ ∀ (E : Env (Fin 2)) (c₀ : Fin 2 → ENode (Fin 2)),
      (∀ t, 10 ≤ t → ∀ v, ∃ s, t ≤ s ∧ s < t + 5 ∧ (run sP sG E c₀ s v).view = nbrs sG v) →
      (∀ v, ∃ t, (run sP sG E c₀ t v).done = true) →
      ∃ T, ∀ t, T ≤ t → ∀ v, (run sP sG E c₀ t v).done = true :=
  fun h => storm_not_converged (h sE _ storm_fair fun v => (storm_done_io 0 v).imp fun _ h => h.2)

/-- **Non-vacuity of `restart_spreads`**: in the storm, node 1 raises the epoch in slot 4 and
node 0 is reset by slot 6. -/
example : ∃ s, 4 < s ∧ s ≤ 4 + 1 + sG.dist 1 0 ∧ (sRun s 0).done = false :=
  restart_spreads (P := sP) (G := sG) (E := sE) (e := 0) (v := 1) (by decide +kernel)
    (by decide +kernel) 0 (SimpleGraph.connected_top.preconnected 1 0)

/-! ### Loss-free epochs behind the freeze gate: no storm

Read off `bootstrap.py` at tag `coverweave-r2r3-repair` and the synchronous scheduler `sched.py`
(slot = `t_hello` = 200 ms, a frame sent in slot `t` is processed at the start of slot `t + 1`):
a reset restarts a LINK to every link-up neighbour and sets every `link_rounds` to 0
(`_reset_to_phase0`); a LINK carries no epoch and is answered by any node whose gate is open for
the asker (`_on_link`), so in a loss-free slot pair the LINK of slot `r` is acknowledged and
processed at slot `r + 2`, before the third attempt; every neighbour's HELLO is heard in every
slot, so no record expires; and the freeze gate waits while `_pending_links` holds
(`gate_waits_for_pending_links = True`). Hence in an epoch entered inside a loss-free window,
with gates that keep their state, a node that passes the freeze gate has verified every
neighbour `u` with the gate open at both ends (`M v`). `hG4` below states exactly this, and
`hM` that only such links are ever verified. The storm above breaks `hG4` (`storm_breaks_G4`):
there the gate does not wait for the late handshake. -/

/-- The current epoch of `v` at slot `s` was entered at a slot `r ≥ T` and has not changed since. -/
def Fresh (P : Params) (G : SimpleGraph V) [DecidableRel G.Adj] (E : Env V) (c₀ : V → ENode V)
    (T s : ℕ) (v : V) : Prop :=
  ∃ r, T ≤ r ∧ r ≤ s ∧ run P G E c₀ r v = reset (run P G E c₀ s v).ep ∧
    ∀ j, r ≤ j → j ≤ s → (run P G E c₀ j v).ep = (run P G E c₀ s v).ep

/-- What a node of a fresh epoch satisfies: no difference counted, only gated links verified, and a
frozen view equal to its view and to `M v`. -/
def FreshInv (M : V → Finset V) (v : V) (n : ENode V) : Prop :=
  n.dif = none ∧ n.view ⊆ M v ∧ ∀ F, n.fr = some F → F = M v ∧ n.view = M v

omit [Fintype V] [DecidableEq V] in
theorem freshInv_reset (M : V → Finset V) (v : V) (e : ℕ) : FreshInv M v (reset e) :=
  ⟨rfl, Finset.empty_subset _, fun F h => by simp [reset] at h⟩

/-- One slot that keeps the epoch keeps `FreshInv`, given the freeze gate. -/
theorem freshInv_step {E : Env V} {t : ℕ} {c : V → ENode V} {v : V} (M : V → Finset V)
    (hM : E.ver t v (c v) ∩ nbrs G v ⊆ M v) (hI : FreshInv M v (c v))
    (hep : (step P G E t c v).ep = (c v).ep)
    (hg : (c v).fr = none → E.pend t v (c v) = false →
      M v ⊆ (c v).view ∪ (E.ver t v (c v) ∩ nbrs G v)) :
    FreshInv M v (step P G E t c v) := by
  obtain ⟨h1, h2, h3⟩ := hI
  have hwM : (c v).view ∪ (E.ver t v (c v) ∩ nbrs G v) ⊆ M v := Finset.union_subset h2 hM
  revert hep
  unfold step
  split_ifs with h0
  · intro h; simp [reset] at h; omega
  · intro _
    unfold stepL
    rcases hfr : (c v).fr with _ | F
    · simp only
      split_ifs with hfz
      · have hw := le_antisymm hwM (hg hfr hfz.2)
        exact ⟨h1, by simpa [upd] using hwM, fun F' hF' => by
          simp only [Option.some.injEq] at hF'
          exact ⟨hF'.symm.trans hw, hw⟩⟩
      · exact ⟨h1, by simpa [upd] using hwM, fun F' hF' => by simp [upd, hfr] at hF'⟩
    · obtain ⟨hFM, hvM⟩ := h3 F hfr
      have hw : (c v).view ∪ (E.ver t v (c v) ∩ nbrs G v) = F := by
        rw [hFM]; exact le_antisymm hwM (hvM ▸ Finset.subset_union_left)
      simp only [hw, ↓reduceIte]
      refine ⟨rfl, by simp [upd, hFM], fun F' hF' => ?_⟩
      simp only [upd, hfr, Option.some.injEq] at hF'
      subst hF'
      exact ⟨hFM, hFM⟩

/-- A slot at a node of `FreshInv` changes its epoch only by adopting a larger one. -/
theorem freshInv_ep {E : Env V} {t : ℕ} {c : V → ENode V} {v : V} (M : V → Finset V)
    (hM : E.ver t v (c v) ∩ nbrs G v ⊆ M v) (hI : FreshInv M v (c v))
    (h0 : ¬ (c v).ep < nbrMax G c v) : (step P G E t c v).ep = (c v).ep := by
  obtain ⟨h1, h2, h3⟩ := hI
  unfold step
  simp only [h0, ↓reduceIte]
  unfold stepL
  rcases hfr : (c v).fr with _ | F
  · simp only; split_ifs <;> rfl
  · obtain ⟨hFM, hvM⟩ := h3 F hfr
    have hw : (c v).view ∪ (E.ver t v (c v) ∩ nbrs G v) = F := by
      rw [hFM]; exact le_antisymm (Finset.union_subset h2 hM) (hvM ▸ Finset.subset_union_left)
    simp only [hw, ↓reduceIte]; rfl

section Fresh

variable {E : Env V} {c₀ : V → ENode V} {T : ℕ} (M : V → Finset V)
  (hM : ∀ t v n, E.ver t v n ∩ nbrs G v ⊆ M v)
  (hG4 : ∀ s, T ≤ s → ∀ v, Fresh P G E c₀ T s v → (run P G E c₀ s v).fr = none →
    E.pend s v (run P G E c₀ s v) = false →
    M v ⊆ (run P G E c₀ s v).view ∪ (E.ver s v (run P G E c₀ s v) ∩ nbrs G v))
include hM hG4

/-- **An epoch entered in the loss-free window freezes complete.** A node whose current epoch was
entered at a slot `≥ T` satisfies `FreshInv`: if frozen, its frozen view is `M v` and equals its
view, so it never counts a difference and never restarts the epoch. -/
theorem fresh_complete {s : ℕ} {v : V} (hf : Fresh P G E c₀ T s v) :
    FreshInv M v (run P G E c₀ s v) := by
  obtain ⟨r, hTr, hrs, hreset, hep⟩ := hf
  have key : ∀ j, r + j ≤ s → FreshInv M v (run P G E c₀ (r + j) v) := by
    intro j
    induction j with
    | zero => intro _; rw [Nat.add_zero, hreset]; exact freshInv_reset M v _
    | succ j ih =>
      intro hj
      have hI := ih (by omega)
      have hr : run P G E c₀ (r + (j + 1)) v = step P G E (r + j) (run P G E c₀ (r + j)) v := rfl
      rw [hr]
      refine freshInv_step M (hM _ _ _) hI ?_ fun h1 h2 => hG4 _ (by omega) v
        ⟨r, hTr, by omega, by rw [hep (r + j) (by omega) (by omega)]; exact hreset,
          fun i h1 h2 => (hep i h1 (by omega)).trans (hep (r + j) (by omega) (by omega)).symm⟩ h1 h2
      rw [← hr, hep _ (by omega) hj]; exact (hep _ (by omega) (by omega)).symm
  have := key (s - r) (by omega)
  rwa [show r + (s - r) = s by omega] at this

/-- Freshness is kept: a node of a fresh epoch either keeps it or adopts a larger one, which is a
new fresh epoch. -/
theorem fresh_step {s : ℕ} (hs : T ≤ s) {v : V} (hf : Fresh P G E c₀ T s v) :
    Fresh P G E c₀ T (s + 1) v := by
  have hI := fresh_complete M hM hG4 hf
  have hr : run P G E c₀ (s + 1) v = step P G E s (run P G E c₀ s) v := rfl
  by_cases h0 : (run P G E c₀ s v).ep < nbrMax G (run P G E c₀ s) v
  · refine ⟨s + 1, by omega, le_rfl, ?_, fun j h1 h2 => by rw [show j = s + 1 by omega]⟩
    rw [hr]; unfold step; simp only [h0, ↓reduceIte]; simp [reset]
  · have he := freshInv_ep (P := P) (t := s) M (hM _ _ _) hI h0
    obtain ⟨r, hTr, hrs, hreset, hep⟩ := hf
    rw [← hr] at he
    refine ⟨r, hTr, by omega, by rw [he]; exact hreset, fun j h1 h2 => ?_⟩
    rcases Nat.lt_or_ge j (s + 1) with h | h
    · rw [he]; exact hep j h1 (by omega)
    · rw [show j = s + 1 by omega]

/-- **No restart storm.** If at a slot `s₀ ≥ T` every node is in an epoch entered at a slot `≥ T`,
no node ever raises the epoch again by the restart rule: from `s₀` on, every epoch stays at most
the largest epoch of `s₀`, so each node restarts only finitely often. -/
theorem fresh_no_storm {s₀ : ℕ} (hs₀ : T ≤ s₀) (hall : ∀ v, Fresh P G E c₀ T s₀ v) {e : ℕ}
    (he : ∀ v, (run P G E c₀ s₀ v).ep ≤ e) :
    ∀ s, s₀ ≤ s → (∀ v, Fresh P G E c₀ T s v) ∧ ∀ v, (run P G E c₀ s v).ep ≤ e := by
  intro s hs
  obtain ⟨j, rfl⟩ := Nat.exists_eq_add_of_le hs
  induction j with
  | zero => exact ⟨hall, he⟩
  | succ j ih =>
    obtain ⟨hF, hE⟩ := ih (by omega)
    refine ⟨fun v => fresh_step (s := s₀ + j) M hM hG4 (by omega) (hF v), fun v => ?_⟩
    have hr : run P G E c₀ (s₀ + (j + 1)) v = step P G E (s₀ + j) (run P G E c₀ (s₀ + j)) v := rfl
    rw [hr]
    by_cases h0 : (run P G E c₀ (s₀ + j) v).ep < nbrMax G (run P G E c₀ (s₀ + j)) v
    · unfold step; simp only [h0, ↓reduceIte]
      exact nbrMax_le hE v
    · rw [freshInv_ep (P := P) (t := s₀ + j) M (hM _ _ _) (fresh_complete M hM hG4 (hF v)) h0]
      exact hE v

/-- **DONE in fresh epochs is DONE for good.** If at a slot `s₀ ≥ T` every node is DONE and frozen
in one epoch `e` entered at a slot `≥ T`, every node is DONE at every later slot: the fresh epochs
end with complete frozen views, so `done_forever_iff_complete` applies. -/
theorem fresh_done_forever {s₀ e : ℕ}
    (hall : ∀ v, Fresh P G E c₀ T s₀ v ∧ (run P G E c₀ s₀ v).ep = e ∧
      (run P G E c₀ s₀ v).done = true ∧ (run P G E c₀ s₀ v).fr ≠ none) :
    ∀ s, s₀ ≤ s → ∀ v, (run P G E c₀ s v).done = true := by
  have hI := fun v => fresh_complete M hM hG4 (hall v).1
  have hA : AllDone (run P G E c₀ s₀) e := by
    intro v
    obtain ⟨-, h1, h2, h3⟩ := hall v
    obtain ⟨F, hF⟩ := Option.ne_none_iff_exists'.1 h3
    obtain ⟨i1, -, i3⟩ := hI v
    obtain ⟨hFM, hvM⟩ := i3 F hF
    exact ⟨h1, h2, by rw [hF, hFM, hvM], i1⟩
  intro s hs v
  have := done_stable' hA (fun s _ v => by
    obtain ⟨F, hF⟩ := Option.ne_none_iff_exists'.1 (hall v).2.2.2
    obtain ⟨hFM, hvM⟩ := (hI v).2.2 F hF
    rw [hvM]; exact hM _ _ _) s hs
  exact (this.1 v).2.1

end Fresh

/-- **The storm breaks the freeze gate**: at slot 1, node 1 is in the epoch it started in, in
phase 0, its gate reports nothing pending, and yet its one gated link is unverified and is not
verified in that slot. So `hG4` is what rules the storm out. -/
theorem storm_breaks_G4 : Fresh sP sG sE (fun _ => reset 0) 0 1 1 ∧ (sRun 1 1).fr = none ∧
    sE.pend 1 1 (sRun 1 1) = false ∧
    ¬ nbrs sG 1 ⊆ (sRun 1 1).view ∪ (sE.ver 1 1 (sRun 1 1) ∩ nbrs sG 1) := by
  refine ⟨⟨0, le_rfl, by omega, by decide +kernel, fun j _ hj => ?_⟩, by decide +kernel, rfl,
    by decide +kernel⟩
  interval_cases j <;> decide +kernel

/-- **Non-vacuity of the fresh-epoch theorems**: two nodes that verify at once, behind a gate that
waits while a gated link is unverified, satisfy `hM` and `hG4` from slot 0, and every node is DONE
for good from slot 4. -/
def bE : Env (Fin 2) where
  ver _ v _ := Finset.univ.erase v
  fin _ _ _ := true
  pend _ v n := !decide (nbrs sG v ⊆ n.view)

theorem b_hM : ∀ t v n, bE.ver t v n ∩ nbrs sG v ⊆ nbrs sG v := fun _ _ _ => Finset.inter_subset_right

theorem b_hG4 : ∀ s, 0 ≤ s → ∀ v, Fresh sP sG bE (fun _ => reset 0) 0 s v →
    (run sP sG bE (fun _ => reset 0) s v).fr = none →
    bE.pend s v (run sP sG bE (fun _ => reset 0) s v) = false →
    nbrs sG v ⊆ (run sP sG bE (fun _ => reset 0) s v).view ∪
      (bE.ver s v (run sP sG bE (fun _ => reset 0) s v) ∩ nbrs sG v) := by
  intro s _ v _ _ hp
  simp only [bE, Bool.not_eq_false', decide_eq_true_eq] at hp
  exact hp.trans Finset.subset_union_left

theorem b_done_forever : ∀ s, 4 ≤ s → ∀ v, (run sP sG bE (fun _ => reset 0) s v).done = true := by
  refine fresh_done_forever (e := 0) (nbrs sG) b_hM b_hG4 fun v => ?_
  refine ⟨⟨0, le_rfl, by omega, ?_, fun j _ hj => ?_⟩, ?_⟩
  · revert v; decide +kernel
  · revert v; interval_cases j <;> decide +kernel
  · revert v; decide +kernel

/-- `fresh_no_storm` applies to the gated run: its epochs stay at 0. -/
example : ∀ s, 0 ≤ s → ∀ v, (run sP sG bE (fun _ => reset 0) s v).ep ≤ 0 := fun s hs =>
  (fresh_no_storm (e := 0) (nbrs sG) b_hM b_hG4 le_rfl
    (fun _ => ⟨0, le_rfl, le_rfl, rfl, fun j _ hj => by rw [show j = 0 by omega]⟩)
    (fun _ => le_rfl) s hs).2

end SwarmInfer.CoverWeave.Epoch

open SwarmInfer.CoverWeave.Epoch in
#print axioms done_forever_iff
open SwarmInfer.CoverWeave.Epoch in
#print axioms done_forever_iff_complete
open SwarmInfer.CoverWeave.Epoch in
#print axioms fresh_no_storm
open SwarmInfer.CoverWeave.Epoch in
#print axioms fresh_done_forever
open SwarmInfer.CoverWeave.Epoch in
#print axioms restart_spreads
open SwarmInfer.CoverWeave.Epoch in
#print axioms storm_not_converged
open SwarmInfer.CoverWeave.Epoch in
#print axioms naive_liveness_false
