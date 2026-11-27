import SwarmInferLean.CoverWeave.ExecFullChainExamples

/-!
# CoverWeave, Phase 4: the offers of an end follow `OfferSeq` (R2'')

`ChainNet.quiet_phase4` of `ExecFullChainR2pp.lean` assumes that every end offers by the
discipline `OfferSeq`. Here that discipline is derived from two properties of the offers of one end
`(e, i)` after slot `T₀`, for any network of edge runs under R2'' and then for the controller of
`ExecFullController.lean`:

* a budget: every slot `v ≥ T₀` at which the end offers lies in a finite set `F` (`offers_le` of
  `ExecFullLadder.lean` bounds the ladder's offers per signature, the controller adds the probes of
  the node's chains);
* idleness is final: once the end has had no open request of its own for `π + 1` consecutive slots
  after `T₀`, it never offers again (the ladder of `_fix_overload` runs on its tick and stops when
  its tried set is exhausted).

`ChainNet.offerSeq_of_idle`: under these, the end follows `OfferSeq π` from `T₀` with at most
`|F| + 1` anchors (one for a request already open at `T₀`). The proof uses only that an end holds at
most one open request (`Inv`) and that a request appears only in a slot with an offer
(`slotO_psub`). `OfferSeq` is monotone in its start slot (`offerSeq_mono`).

Added hypotheses (not stated in the source; the paper's proof counts offers per round, not when they
come):
* idleness is final (`hidle`). It cannot be derived from the controller's rules: an idle end can be
  offered again by a later ladder slot (a new ladder step after a clear of the tried set) or by a
  probe of a chain that a neighbour's PUSH starts at its node. Without it the conclusion fails:
  `ex_not_offerSeq` (`ExecFullPhase4.lean`) has a leaf that pushes at slots 0 and 6, satisfies the
  budget with `F = {0, 6}`, and follows `OfferSeq 1` for no list of anchors. Stated as a property
  of the ladder's schedule: `_fix_overload` runs on every tick and offers while its tried set has a
  fresh tuple, so it falls idle only when the set is exhausted, and that lasts until a clear.
* the budget `F`. `offers_le` of `ExecFullLadder.lean` bounds the ladder's offers per signature by
  `(C + 1) |U|`, but the controller's ladder `E.ladder` is an oblivious schedule without a tried
  set, so `|F|` is not linked to that count here; that link needs a ladder with state and stays
  open.

`ctl_offerSeq`: for the controller, an offer at an end is a probe of its node's chain or an offer of
the ladder (`offAt_cases`), so the budget is the ladder's slots plus the probe slots;
`ctl_offerSeq_single`: an end whose node has no other end is never probed. `ex_ctl_offerSeq`: in
the star of `ExecFullChainExamples.lean`, the leaf end that pushes at slot 0 satisfies the
hypotheses with `F = {0}`, `π = 1`, so the hypothesis set is not vacuous.
-/

namespace SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull

namespace ChainNet

variable (N : ChainNet)

theorem offerSeq_mono {π : ℕ} {e : N.Ed} {i : Bool} :
    ∀ (os : List N.Probe) {prev prev' : ℕ}, prev ≤ prev' → N.OfferSeq π e i prev os →
      N.OfferSeq π e i prev' os
  | [], _, _, h, hs => by
    simp only [OfferSeq] at hs ⊢
    exact fun v hv => hs v (by omega)
  | _ :: _, _, _, h, hs => by
    simp only [OfferSeq] at hs ⊢
    obtain ⟨h1, h2, h3, h4, h5, h6⟩ := hs
    exact ⟨h1, h2, by omega, h4, fun v hv hv' => h5 v (by omega) hv', h6⟩

theorem pend_cases (e : N.Ed) (i : Bool) (t : ℕ) :
    ((N.run e t).nd i).pend = [] ∨ ∃ p, ((N.run e t).nd i).pend = [p] := by
  rcases ((inv_iff _).1 (srunO_inv (N.inv e) t) i).pend with h | ⟨p, h, -⟩
  · exact Or.inl h
  · exact Or.inr ⟨p, h⟩

theorem psub_run {e : N.Ed} {i : Bool} {p : Pend} {t : ℕ} (h : PSub p (N.run e t) i)
    (ho : (N.env e).off t i = none) : PSub p (N.run e (t + 1)) i :=
  slotO_psub (N.misc e) h ho

/-- A request appears only in a slot with an offer: if `p` is open at `t + 1` and `t` had no offer,
then `p` was open at `t` already. -/
theorem offer_of_new {e : N.Ed} {i : Bool} {p : Pend} {t : ℕ}
    (h1 : ((N.run e (t + 1)).nd i).pend = [p]) (h0 : ((N.run e t).nd i).pend ≠ [p]) :
    (N.env e).off t i ≠ none := by
  intro ho
  rcases N.pend_cases e i t with hn | ⟨p', hp'⟩
  · -- from an empty set only an offer opens a request
    let q : Pend := ⟨p.seq + 1, true, 0, 0⟩
    rcases N.psub_run (p := q) (Or.inr hn) ho with h | h
    · rw [h1] at h; simp only [List.cons.injEq, and_true] at h
      have := congrArg Pend.seq h; simp [q] at this
    · rw [h1] at h; simp at h
  · rcases N.psub_run (p := p') (Or.inl hp') ho with h | h
    · rw [h1] at h; simp only [List.cons.injEq, and_true] at h; subst h; exact h0 hp'
    · rw [h1] at h; simp at h

/-- The slots `v ≥ a` at which end `i` of `e` offers lie in `G`. -/
def Bud (e : N.Ed) (i : Bool) (a : ℕ) (G : Finset ℕ) : Prop :=
  ∀ v, a ≤ v → (N.env e).off v i ≠ none → v ∈ G

theorem Bud.mono {e : N.Ed} {i : Bool} {a b : ℕ} {G : Finset ℕ} (h : N.Bud e i a G) (hab : a ≤ b) :
    N.Bud e i b G := fun v hv ho => h v (by omega) ho

theorem Bud.erase {e : N.Ed} {i : Bool} {a w : ℕ} {G : Finset ℕ} (h : N.Bud e i a G) (hw : w < a) :
    N.Bud e i a (G.erase w) := fun v hv ho => Finset.mem_erase.2 ⟨by omega, h v hv ho⟩

section Build

variable {π T₀ : ℕ} {e : N.Ed} {i : Bool}

/-- What is built for a request `p` open at `a`: the anchors after its closure. -/
def SA (π T₀ : ℕ) (e : N.Ed) (i : Bool) (m : ℕ) : Prop :=
  ∀ (G : Finset ℕ) (a : ℕ) (p : Pend), G.card ≤ m → T₀ ≤ a → N.Bud e i a G →
    ((N.run e a).nd i).pend = [p] → ∃ rest : List N.Probe, rest.length ≤ m ∧
      ∀ c, a ≤ c → ((N.run e c).nd i).pend ≠ [p] → N.OfferSeq π e i c rest

/-- What is built from an idle slot `prev`. -/
def SB (π T₀ : ℕ) (e : N.Ed) (i : Bool) (m : ℕ) : Prop :=
  ∀ (G : Finset ℕ) (prev : ℕ), G.card ≤ m → T₀ ≤ prev → N.Bud e i prev G →
    ((N.run e prev).nd i).pend = [] → ∃ os : List N.Probe, os.length ≤ m ∧ N.OfferSeq π e i prev os

variable (hidle : ∀ t, T₀ ≤ t → (∀ v, t ≤ v → v ≤ t + π → ((N.run e v).nd i).pend = []) →
  ∀ v, t ≤ v → (N.env e).off v i = none)
include hidle

theorem sB (m : ℕ) (ih : ∀ k < m, N.SA π T₀ e i k) : N.SB π T₀ e i m := by
  intro G prev hG hT hB h0
  classical
  by_cases hI : ∀ v, prev ≤ v → v ≤ prev + π → ((N.run e v).nd i).pend = []
  · refine ⟨[], by simp, ?_⟩
    simp only [OfferSeq]
    exact fun v hv => hidle prev hT hI v (by omega)
  · have hex : ∃ k, k ≤ π ∧ ((N.run e (prev + k)).nd i).pend ≠ [] := by
      push Not at hI
      obtain ⟨v, h1, h2, h3⟩ := hI
      exact ⟨v - prev, by omega, by rwa [show prev + (v - prev) = v by omega]⟩
    obtain ⟨hk1, hk2⟩ := Nat.find_spec hex
    have hk0 : Nat.find hex ≠ 0 := fun h => hk2 (by rw [h]; simpa using h0)
    obtain ⟨j, hj⟩ : ∃ j, Nat.find hex = j + 1 := ⟨Nat.find hex - 1, by omega⟩
    rw [hj] at hk1 hk2
    have hjm : ((N.run e (prev + j)).nd i).pend = [] := by
      have := Nat.find_min hex (show j < Nat.find hex by omega)
      push Not at this
      exact this (by omega)
    obtain ⟨p, hp⟩ : ∃ p, ((N.run e (prev + (j + 1))).nd i).pend = [p] := by
      rcases N.pend_cases e i (prev + (j + 1)) with h | h
      · exact absurd h hk2
      · exact h
    have hoff := N.offer_of_new (t := prev + j) hp (by rw [hjm]; simp)
    have hw : prev + j ∈ G := hB _ (by omega) hoff
    have hm : 1 ≤ m := by
      have := Finset.card_pos.2 ⟨_, hw⟩; omega
    obtain ⟨rest, hlen, hrest⟩ := ih (m - 1) (by omega) (G.erase (prev + j)) (prev + (j + 1)) p
      (by rw [Finset.card_erase_of_mem hw]; omega) (by omega)
      ((hB.mono N (by omega)).erase N (by omega)) hp
    refine ⟨⟨e, i, p, prev + (j + 1)⟩ :: rest, by simp; omega, ?_⟩
    rw [OfferSeq]
    exact ⟨rfl, rfl, by dsimp only; omega, hp, fun v h1 h2 => by dsimp only at h2; omega, hrest⟩

theorem sA (m : ℕ) (ih : ∀ k < m, N.SA π T₀ e i k) : N.SA π T₀ e i m := by
  intro G a p hG hT hB hp
  classical
  by_cases hex : ∃ c, a ≤ c ∧ ((N.run e c).nd i).pend ≠ [p]
  · obtain ⟨hc1, hc2⟩ := Nat.find_spec hex
    have hmin : ∀ c, a ≤ c → ((N.run e c).nd i).pend ≠ [p] → Nat.find hex ≤ c :=
      fun c h1 h2 => Nat.find_min' hex ⟨h1, h2⟩
    have hc0 : Nat.find hex ≠ a := fun h => hc2 (by rw [h]; exact hp)
    obtain ⟨j, hj⟩ : ∃ j, Nat.find hex = j + 1 := ⟨Nat.find hex - 1, by omega⟩
    have hjp : ((N.run e j).nd i).pend = [p] := by
      have := Nat.find_min hex (show j < Nat.find hex by omega)
      push Not at this
      exact this (by omega)
    rw [hj] at hc1 hc2 hmin
    rcases N.pend_cases e i (j + 1) with h0 | ⟨p', hp'⟩
    · obtain ⟨rest, hlen, hrest⟩ := N.sB hidle m ih G (j + 1) hG (by omega) (hB.mono N (by omega)) h0
      exact ⟨rest, hlen, fun c h1 h2 => N.offerSeq_mono rest (hmin c h1 h2) hrest⟩
    · have hoff := N.offer_of_new (t := j) hp' (by rw [hjp]; intro h; exact hc2 (by rw [hp', ← h]))
      have hw : j ∈ G := hB _ (by omega) hoff
      have hm : 1 ≤ m := by
        have := Finset.card_pos.2 ⟨_, hw⟩; omega
      obtain ⟨rest, hlen, hrest⟩ := ih (m - 1) (by omega) (G.erase j) (j + 1) p'
        (by rw [Finset.card_erase_of_mem hw]; omega) (by omega)
        ((hB.mono N (by omega)).erase N (by omega)) hp'
      refine ⟨⟨e, i, p', j + 1⟩ :: rest, by simp; omega, fun c h1 h2 => ?_⟩
      refine N.offerSeq_mono _ (hmin c h1 h2) ?_
      rw [OfferSeq]
      exact ⟨rfl, rfl, by dsimp only; omega, hp', fun v h1 h2 => by dsimp only at h2; omega, hrest⟩
  · push Not at hex
    exact ⟨[], by simp, fun c h1 h2 => absurd (hex c h1) h2⟩

theorem sA_all : ∀ m, N.SA π T₀ e i m := by
  intro m
  induction m using Nat.strong_induction_on with
  | _ m ih => exact N.sA hidle m ih

end Build

/-- **The offers of an end follow `OfferSeq`.** In a network of edge runs under R2'', if every slot
`v ≥ T₀` at which end `i` of `e` offers lies in `F`, and the end never offers again once it has had
no open request of its own for `π + 1` consecutive slots after `T₀`, then it follows `OfferSeq π`
from `T₀` with at most `|F| + 1` anchors. -/
theorem offerSeq_of_idle {π T₀ : ℕ} {e : N.Ed} {i : Bool} (F : Finset ℕ)
    (hF : ∀ v, T₀ ≤ v → (N.env e).off v i ≠ none → v ∈ F)
    (hidle : ∀ t, T₀ ≤ t → (∀ v, t ≤ v → v ≤ t + π → ((N.run e v).nd i).pend = []) →
      ∀ v, t ≤ v → (N.env e).off v i = none) :
    ∃ os : List N.Probe, os.length ≤ F.card + 1 ∧ N.OfferSeq π e i T₀ os := by
  rcases N.pend_cases e i T₀ with h0 | ⟨p, hp⟩
  · obtain ⟨os, hl, hs⟩ := N.sB hidle F.card (fun k _ => N.sA_all hidle k) F T₀ le_rfl le_rfl hF h0
    exact ⟨os, by omega, hs⟩
  · obtain ⟨rest, hl, hr⟩ := N.sA_all hidle F.card F T₀ p le_rfl le_rfl hF hp
    refine ⟨⟨e, i, p, T₀⟩ :: rest, by simp; omega, ?_⟩
    rw [OfferSeq]
    exact ⟨rfl, rfl, by dsimp only; omega, hp, fun v h1 h2 => by dsimp only at h2; omega, hr⟩

end ChainNet

/-! ### The controller -/

variable {T : Topo}

/-- An offer of the controller at an end is a probe of its node's chain or an offer of the
ladder. -/
theorem offAt_cases {E : NEnv T} {S : NS T} {t : ℕ} {e : T.Ed} {c : Bool}
    (h : offAt E S t e c ≠ none) : cact S (T.own e c) = .probe (e, c) ∨ E.ladder t e c ≠ none := by
  unfold offAt at h
  split at h
  · rename_i x hx
    split_ifs at h with hxe
    · exact Or.inl (hxe ▸ hx)
    · exact absurd rfl h
  · right
    split_ifs at h
    · exact h
    · exact absurd rfl h

/-- A probe is one of the node's ends other than the end of its chain. -/
theorem cact_probe_mem {S : NS T} {w : T.W} {x : T.Ed × Bool} (h : cact S w = .probe x) :
    ∃ r, S.crec w = some r ∧ x ∈ T.ends w ∧ x ≠ r.J := by
  have hn : ∀ r, nextAct S w r = .probe x → x ∈ T.ends w ∧ x ≠ r.J := by
    intro r hr
    unfold nextAct at hr
    split at hr
    · cases hr
    · rename_i y l hl
      cases hr
      have := (mem_cands (S := S)).1 (by rw [hl]; exact List.mem_cons_self)
      exact ⟨this.1, this.2.1⟩
  cases hcr : S.crec w with
  | none => simp [cact, hcr] at h
  | some r =>
    refine ⟨r, rfl, hn r ?_⟩
    have h' := h
    simp only [cact, hcr] at h'
    by_cases hj : (nodeAt S.es r.J).job.isNone = true
    · simp [hj] at h'
    · simp only [hj, Bool.false_eq_true, ite_false] at h'
      cases hp : r.probe with
      | none => simpa [hp] using h'
      | some pr =>
        simp only [hp] at h'
        by_cases h1 : (nodeAt S.es (pr.1, pr.2.1)).pend.any (fun p => decide (p.seq = pr.2.2)) = true
        · simp [h1] at h'
        · by_cases h2 : (nodeAt S.es (pr.1, pr.2.1)).X = some false
          · simp [h1, h2] at h'
          · simpa [h1, h2] using h'

/-- A node with one end never probes. -/
theorem cact_single {S : NS T} (H : RecOK S) {w : T.W} (hw : (T.ends w).length ≤ 1)
    (x : T.Ed × Bool) : cact S w ≠ .probe x := by
  intro h
  obtain ⟨r, hr, hx, hxJ⟩ := cact_probe_mem h
  have hJ : r.J ∈ T.ends w := (T.hown w r.J.1 r.J.2).2 (H.2.1 w r hr)
  match hl : T.ends w, hw with
  | [], _ => rw [hl] at hx; simp at hx
  | [y], _ => rw [hl] at hx hJ; simp at hx hJ; exact hxJ (hx.trans hJ.symm)

section Ctl

variable (E : NEnv T) (S₀ : NS T) (hS : CtlStart S₀)

/-- **The offers of a controller end follow `OfferSeq`.** In the network run by the controller from
a start without chains, take an end `(e, c)` and a slot `T₀`. If the ladder offers there after
`T₀` only at slots in `F`, the node's chains probe it after `T₀` only at slots in `P`, and the end
never offers again once it has had no open request for `π + 1` consecutive slots after `T₀`, then
the end follows `OfferSeq π` from `T₀` with at most `|F| + |P| + 1` anchors. -/
theorem ctl_offerSeq {π T₀ : ℕ} {e : T.Ed} {c : Bool} (F P : Finset ℕ)
    (hF : ∀ v, T₀ ≤ v → E.ladder v e c ≠ none → v ∈ F)
    (hP : ∀ v, T₀ ≤ v → cact (netRunC E S₀ v) (T.own e c) = .probe (e, c) → v ∈ P)
    (hidle : ∀ t, T₀ ≤ t →
      (∀ v, t ≤ v → v ≤ t + π → (((netRunC E S₀ v).es e).nd c).pend = []) →
      ∀ v, t ≤ v → offAt E (netRunC E S₀ v) v e c = none) :
    ∃ os : List (ctlNet E S₀ hS).Probe, os.length ≤ F.card + P.card + 1 ∧
      (ctlNet E S₀ hS).OfferSeq π e c T₀ os := by
  obtain ⟨os, hl, hs⟩ := (ctlNet E S₀ hS).offerSeq_of_idle (π := π) (T₀ := T₀) (e := e) (i := c)
    (F ∪ P) (fun v hv ho => by
      rcases offAt_cases ho with h | h
      · exact Finset.mem_union_right _ (hP v hv h)
      · exact Finset.mem_union_left _ (hF v hv h))
    (fun t ht hI v hv => hidle t ht (fun v h1 h2 => by
      have := hI v h1 h2; rwa [ctlNet_run] at this) v hv)
  exact ⟨os, hl.trans (by have := Finset.card_union_le F P; omega), hs⟩

/-- **A leaf end follows `OfferSeq`**: an end whose node has no other end is never probed, so the
budget is the ladder's slots alone. -/
theorem ctl_offerSeq_single {π T₀ : ℕ} {e : T.Ed} {c : Bool} (F : Finset ℕ)
    (hw : (T.ends (T.own e c)).length ≤ 1)
    (hF : ∀ v, T₀ ≤ v → E.ladder v e c ≠ none → v ∈ F)
    (hidle : ∀ t, T₀ ≤ t →
      (∀ v, t ≤ v → v ≤ t + π → (((netRunC E S₀ v).es e).nd c).pend = []) →
      ∀ v, t ≤ v → offAt E (netRunC E S₀ v) v e c = none) :
    ∃ os : List (ctlNet E S₀ hS).Probe, os.length ≤ F.card + 1 ∧
      (ctlNet E S₀ hS).OfferSeq π e c T₀ os := by
  obtain ⟨os, hl, hs⟩ := ctl_offerSeq E S₀ hS F ∅ hF
    (fun v _ h => absurd h (cact_single (run_rec E S₀ hS v) hw _)) hidle
  exact ⟨os, by simpa using hl, hs⟩

end Ctl

/-! ### Non-vacuity: the leaf end of the star that pushes at slot 0 -/

/-- In the star of `ExecFullChainExamples.lean`, end `false` of edge 0 (node 1, a leaf) offers only
at slot 0. -/
theorem ex_ctl_leaf_off : ∀ v, 1 ≤ v → offAt exCtlEnv (netRunC exCtlEnv exCtlStart v) v 0 false = none := by
  intro v hv
  by_contra h
  rcases offAt_cases h with h | h
  · exact cact_single (run_rec exCtlEnv exCtlStart ex_ctl_start v) (by decide) _ h
  · apply h; simp [exCtlEnv, show v ≠ 0 by omega]

/-- **The hypotheses of `ctl_offerSeq_single` hold for the leaf**, with `T₀ = 0`, `F = {0}` and
`π = 1`: its PUSH of slot 0 is open at slot 1, so the end is not idle over slots 0 and 1, and it
never offers after slot 0. Hence it follows `OfferSeq 1` from slot 0 with at most two anchors. -/
theorem ex_ctl_offerSeq : ∃ os : List (ctlNet exCtlEnv exCtlStart ex_ctl_start).Probe,
    os.length ≤ 2 ∧ (ctlNet exCtlEnv exCtlStart ex_ctl_start).OfferSeq 1 (0 : Fin 3) false 0 os := by
  have hopen : (((netRunC exCtlEnv exCtlStart 1).es 0).nd false).pend ≠ [] := by decide +kernel
  obtain ⟨os, hl, hs⟩ := ctl_offerSeq_single exCtlEnv exCtlStart ex_ctl_start (π := 1) (T₀ := 0)
    (e := 0) (c := false) {0} (by decide)
    (fun v _ h => by
      simp only [Finset.mem_singleton]
      by_contra hv; apply h; simp [exCtlEnv, show v ≠ 0 by omega])
    (fun t _ hI v hv => by
      rcases Nat.eq_zero_or_pos t with rfl | ht
      · exact absurd (hI 1 (by omega) (by omega)) hopen
      · exact ex_ctl_leaf_off v (by omega))
  exact ⟨os, by simpa using hl, hs⟩

end SwarmInfer.CoverWeave.ExecFull.R2pp

open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ChainNet.offerSeq_of_idle
open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ctl_offerSeq
open SwarmInfer.CoverWeave.ExecFull in
#print axioms R2pp.ex_ctl_offerSeq
