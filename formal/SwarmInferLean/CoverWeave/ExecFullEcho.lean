import Mathlib

/-!
# CoverWeave, Theorem 3(b): records in a silent configuration (inventory C5(b), E7)

Source: proof of `thm:cap` (b), `CoverWeave_R1/sections/04-formaleng.tex:85` ("in a silent
configuration every frozen neighbor has echoed the role and forced load that a node advertises,
so both ends of a flexible edge use the same budgets"), `03-system.tex:47` (confirmation echoes
in HELLO after DONE) and `03-system.tex:208` ("A DONE node asks every frozen neighbor to confirm
it ... an unconfirmed node stays open").

The text gives the mechanism but not the argument. It is read off the code: `_maybe_hello`
(`bbcvc.py:1529-1633`), `_confirm_state` (`bbcvc.py:1758-1789`), `_unconfirmed`
(`bbcvc.py:1748-1756`) and `_owes` (`bbcvc.py:1493-1509`, an unconfirmed node is not closed).

The model is one directed pair: `x` advertises, `u` records. `x`'s state has a version `cur` that
grows with every change of its role or forced load; `adv` is the version of the last HELLO `x`
sent (`_adv_role`, `_adv_forced`); `u`'s record of `x` is `rcd` (`none` after an expiry). HELLOs
travel `x → u` and echoes `u → x` on FIFO channels that may lose frames. `x`'s confirmation of `u`
is `conf`: `none` before `x`'s first DONE HELLO, `some false` once asked or reset, `some true`
once an echo equal to what `x` advertises arrived.

Result: `rec_eq_adv_of_confirmed`. In every reachable state in which `x` has `u` confirmed, `u`
holds a record and no HELLO is in flight, `u`'s record is what `x` advertises. With "no rule can
fire" (`cur = adv`, a change would be announced at once, `bbcvc.py:1532-1536`), it is `x`'s state.
This is the property `RecordsAccurate` of `ExecFullOwnership.lean`.
-/

namespace SwarmInfer.CoverWeave.ExecFull

/-- The state of one directed pair. `hi` is a ghost: the highest version `u` ever recorded. -/
structure EPair where
  cur : ℕ
  adv : ℕ
  told : Bool
  conf : Option Bool
  rcd : Option ℕ
  hi : ℕ
  hellos : List ℕ
  echoes : List ℕ
  deriving DecidableEq

/-- The events. -/
inductive EStep : EPair → EPair → Prop
  /-- `x`'s role or forced load changes. -/
  | change (p : EPair) : EStep p { p with cur := p.cur + 1 }
  /-- `x` sends a HELLO with its current state (`done`: `x` is DONE). A changed announcement
  after the DONE HELLO resets the confirmation (`bbcvc.py:1600-1602`), the first DONE HELLO asks
  for it (`bbcvc.py:1603-1607`). -/
  | hello (p : EPair) (done : Bool) :
      EStep p { p with
        conf := if (p.told && p.cur != p.adv) || (done && p.conf.isNone) then some false
          else p.conf
        adv := p.cur
        told := p.told || done
        hellos := p.hellos ++ [p.cur] }
  /-- the first HELLO in flight reaches `u` (`bootstrap.py:713-718`) -/
  | recvHello (p : EPair) (v : ℕ) (l : List ℕ) (h : p.hellos = v :: l) :
      EStep p { p with rcd := some v, hi := max p.hi v, hellos := l }
  | loseHello (p : EPair) (v : ℕ) (l : List ℕ) (h : p.hellos = v :: l) :
      EStep p { p with hellos := l }
  /-- `u` echoes the record it holds (`hello_echo`, `bbcvc.py:1611-1613`) -/
  | echo (p : EPair) (v : ℕ) (h : p.rcd = some v) : EStep p { p with echoes := p.echoes ++ [v] }
  /-- the first echo in flight reaches `x`; it counts only when it equals what `x` advertises -/
  | recvEcho (p : EPair) (v : ℕ) (l : List ℕ) (h : p.echoes = v :: l) :
      EStep p { p with
        conf := if p.conf.isSome && v == p.adv then some true else p.conf
        echoes := l }
  | loseEcho (p : EPair) (v : ℕ) (l : List ℕ) (h : p.echoes = v :: l) :
      EStep p { p with echoes := l }
  /-- `u` expires its record of `x` (soft state, `_expire`, `bbcvc.py:1635-1668`) -/
  | expire (p : EPair) : EStep p { p with rcd := none }

/-- The start: nothing sent, nothing recorded. -/
def EPair.start : EPair := ⟨0, 0, false, none, none, 0, [], []⟩

/-- The invariant. -/
def EInv (p : EPair) : Prop :=
  p.adv ≤ p.cur ∧ p.hi ≤ p.adv ∧ (∀ v ∈ p.hellos, p.hi ≤ v ∧ v ≤ p.adv) ∧
    p.hellos.Pairwise (· ≤ ·) ∧ (∀ v ∈ p.echoes, v ≤ p.hi) ∧
    (∀ v, p.rcd = some v → v = p.hi) ∧ (p.conf.isSome → p.told = true) ∧
    (p.conf = some true → p.adv ≤ p.hi)

theorem eInv_start : EInv EPair.start := by
  refine ⟨le_rfl, le_rfl, by simp [EPair.start], by simp [EPair.start], by simp [EPair.start],
    by simp [EPair.start], by simp [EPair.start], by simp [EPair.start]⟩

theorem eInv_step {p q : EPair} (h : EStep p q) (hp : EInv p) : EInv q := by
  obtain ⟨h1, h2, h3, h4, h5, h6, h7, h8⟩ := hp
  cases h with
  | change => exact ⟨by simp; omega, h2, h3, h4, h5, h6, h7, h8⟩
  | hello done =>
    refine ⟨le_rfl, by simp; omega, ?_, ?_, h5, h6, ?_, ?_⟩
    · intro v hv
      simp only [List.mem_append, List.mem_singleton] at hv
      rcases hv with hv | rfl
      · have := h3 v hv; exact ⟨this.1, by simp; omega⟩
      · exact ⟨by simp; omega, le_rfl⟩
    · simp only
      rw [List.pairwise_append]
      refine ⟨h4, List.pairwise_singleton _ _, fun a ha b hb => ?_⟩
      simp only [List.mem_singleton] at hb
      subst hb
      have := (h3 a ha).2; omega
    · intro hs
      simp only [Bool.or_eq_true] at hs ⊢
      split_ifs at hs with hc
      · simp only [Bool.and_eq_true] at hc
        rcases hc with ⟨ht, -⟩ | ⟨hd, -⟩
        · exact Or.inl ht
        · exact Or.inr hd
      · exact Or.inl (h7 hs)
    · intro hs
      simp only at hs ⊢
      split_ifs at hs with hc
      · simp at hs
      · simp only [Bool.or_eq_true, Bool.and_eq_true, not_or, not_and, bne_iff_ne, ne_eq,
          Decidable.not_not] at hc
        have ht := h7 (by rw [hs]; rfl)
        have := hc.1 ht
        rw [this]; exact h8 hs
  | recvHello v l h =>
    rw [h] at h3 h4
    have hv := h3 v (by simp)
    simp only [List.pairwise_cons] at h4
    refine ⟨h1, by simp; omega, fun w hw => ?_, h4.2, fun w hw => ?_, ?_, h7, ?_⟩
    · have := h3 w (by simp [hw]); have := h4.1 w hw; simp; omega
    · have := h5 w hw; simp; omega
    · intro w hw; simp at hw; subst hw; simp; omega
    · intro hs; have := h8 hs; simp; omega
  | loseHello v l h =>
    rw [h] at h3 h4
    simp only [List.pairwise_cons] at h4
    exact ⟨h1, h2, fun w hw => h3 w (by simp [hw]), h4.2, h5, h6, h7, h8⟩
  | echo v h =>
    refine ⟨h1, h2, h3, h4, fun w hw => ?_, h6, h7, h8⟩
    simp only [List.mem_append, List.mem_singleton] at hw
    rcases hw with hw | rfl
    · exact h5 w hw
    · exact (h6 _ h).le
  | recvEcho v l h =>
    rw [h] at h5
    have hv := h5 v (by simp)
    refine ⟨h1, h2, h3, h4, fun w hw => h5 w (by simp [hw]), h6, ?_, ?_⟩
    · intro hs
      simp only at hs ⊢
      split_ifs at hs with hc
      · simp only [Bool.and_eq_true] at hc; exact h7 hc.1
      · exact h7 hs
    · intro hs
      simp only at hs ⊢
      split_ifs at hs with hc
      · simp only [Bool.and_eq_true, beq_iff_eq] at hc; rw [← hc.2]; exact hv
      · exact h8 hs
  | loseEcho v l h =>
    rw [h] at h5
    exact ⟨h1, h2, h3, h4, fun w hw => h5 w (by simp [hw]), h6, h7, h8⟩
  | expire =>
    exact ⟨h1, h2, h3, h4, h5, by simp, h7, h8⟩

theorem eInv_of_reach {p : EPair} (h : Relation.ReflTransGen EStep EPair.start p) : EInv p := by
  induction h with
  | refl => exact eInv_start
  | tail _ hs ih => exact eInv_step hs ih

/-- **Records in a silent configuration.** In every reachable state of the pair in which `x` has
`u` confirmed and `u` holds a record of `x`, that record is the version `x` advertises. If
moreover no rule can fire at `x` (`cur = adv`), the record is `x`'s state.

Modelling choices:
* A version stands for the pair (role, forced load) of `x`; comparing versions instead of values
  uses that after DONE a role only rises and the forced load only falls, so a value never recurs
  (`bbcvc.py:1772-1774`), and that before DONE no echo counts (`conf = none`).
* Channels are FIFO with loss; nothing else is assumed about timing. Expiry may drop `u`'s
  record at any time.
* Only `x`'s confirmation of `u` is modelled; `u`'s record of `x` is what `x`'s flexible-edge
  rule compares with at `u`.

Added hypotheses: none. -/
theorem rec_eq_adv_of_confirmed {p : EPair} (h : Relation.ReflTransGen EStep EPair.start p)
    (hc : p.conf = some true) {v : ℕ} (hr : p.rcd = some v) : v = p.adv := by
  obtain ⟨-, h2, -, -, -, h6, -, h8⟩ := eInv_of_reach h
  have := h6 v hr
  have := h8 hc
  omega

/-- A reachable state with all hypotheses: `x` changed twice, announced, was confirmed. -/
example : ∃ p, Relation.ReflTransGen EStep EPair.start p ∧ p.conf = some true ∧
    p.rcd = some 2 ∧ p.adv = 2 := by
  refine ⟨_, ((((((Relation.ReflTransGen.refl.tail (EStep.change _)).tail (EStep.change _)).tail
    (EStep.hello _ true)).tail (EStep.recvHello _ 2 [] rfl)).tail (EStep.echo _ 2 rfl)).tail
    (EStep.recvEcho _ 2 [] rfl)), rfl, rfl, rfl⟩

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms rec_eq_adv_of_confirmed
