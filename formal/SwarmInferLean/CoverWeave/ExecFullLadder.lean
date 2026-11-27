import Mathlib

/-!
# CoverWeave, the proof of Lemma 4: how many offers the ladder of Phase 4 makes, and the timer

Source: `CoverWeave_R1/sections/04-formaleng.tex:131` ("between two changes a round of
Algorithm `alg:ownership` sends at most one HANDOVER and one PUSH per flexible neighbor, at most
`2 r̄` rounds ... precede Unresolved") and `bbcvc.py` `_fix_overload`, `_rule_ownership`,
`_retry_pending`, `_backoff_ms` of branch `r2r3-repair`.

* `offers_le`: the ladder offers an edge only with an attempt tuple not yet tried and records it
  (`_tried`, `bbcvc.py:1231-1245`); the tried set is cleared by a signature change, a repair round,
  a deepening of F11 or the end of the relayed search. A run of the ladder with at most `C` clears,
  all of whose tuples lie in a finite set `U`, makes at most `(C + 1) · |U|` offers. With `U` the
  tuples `(peer, HANDOVER)` and `(peer, PUSH, ttl)` of the `deg v` flexible peers and the `L`
  push depths, `|U| ≤ deg v · (1 + L)`, and between two signature changes
  `C ≤ r_max + L_F11 + 1` (rounds, F11 deepenings, the relayed search).
* `timer_fires`: the retransmission timer of an open request fires after `T₀` and then after
  doubling backoff capped at `2^(R-1) T₀` (`_backoff_ms`); in every window of
  `2^(R-1) T₀` consecutive ticks while the request is open it fires at least once. This is the
  hypothesis on `E.rx` of `ExecFullTransferSync.lean`, with `Tr = 2^(R-1) T₀` in slots.
-/

namespace SwarmInfer.CoverWeave.Ladder

/-- An action of the ladder on its attempt set: offer with tuple `x`, or clear the set. -/
inductive Act (α : Type*)
  | offer (x : α)
  | clear

variable {α : Type*} [DecidableEq α]

/-- Run the actions from a tried set: an offer is made only with a fresh tuple, which is then
recorded; a clear empties the set. Returns the number of offers made, or `none` if an offer used
a tuple already tried (the ladder never does that). -/
def run : Finset α → List (Act α) → Option ℕ
  | _, [] => some 0
  | S, .offer x :: as => if x ∈ S then none else (run (insert x S) as).map (· + 1)
  | _, .clear :: as => run ∅ as

def clears : List (Act α) → ℕ
  | [] => 0
  | .offer _ :: as => clears as
  | .clear :: as => clears as + 1

def tuples : List (Act α) → List α
  | [] => []
  | .offer x :: as => x :: tuples as
  | .clear :: as => tuples as

/-- Between clears, every offer adds a new element of `U` to the tried set. -/
theorem run_le (U : Finset α) :
    ∀ (as : List (Act α)) (S : Finset α) (n : ℕ), S ⊆ U → (∀ x ∈ tuples as, x ∈ U) →
      run S as = some n → n + S.card ≤ (clears as + 1) * U.card := by
  intro as
  induction as with
  | nil =>
    intro S n hS _ h
    simp [run] at h; subst h
    simpa [clears] using Finset.card_le_card hS
  | cons a as ih =>
    intro S n hS hU h
    cases a with
    | offer x =>
      simp only [run] at h
      split_ifs at h with hx
      obtain ⟨m, hm, rfl⟩ := Option.map_eq_some_iff.1 h
      have hxU : x ∈ U := hU x (by simp [tuples])
      have := ih (insert x S) m (Finset.insert_subset hxU hS)
        (fun y hy => hU y (by simp [tuples, hy])) hm
      rw [Finset.card_insert_of_notMem hx] at this
      simp only [clears]; omega
    | clear =>
      simp only [run] at h
      have := ih ∅ n (Finset.empty_subset _) (fun y hy => hU y (by simpa [tuples] using hy)) h
      simp only [clears, Finset.card_empty] at this ⊢
      have := Finset.card_le_card hS
      nlinarith

/-- **The ladder's offers are bounded.** From an empty tried set, a run with `C` clears whose
tuples all lie in `U` makes at most `(C + 1) · |U|` offers. -/
theorem offers_le (U : Finset α) (as : List (Act α)) (n : ℕ) (hU : ∀ x ∈ tuples as, x ∈ U)
    (h : run ∅ as = some n) : n ≤ (clears as + 1) * U.card := by
  have := run_le U as ∅ n (Finset.empty_subset _) hU h
  simpa using this

/-! ### The retransmission timer -/

/-- The backoff after the `k`-th send (`k ≥ 1`): `T₀ · 2^min(k-1, R-1)` (`_backoff_ms`). -/
def backoff (T₀ R k : ℕ) : ℕ := T₀ * 2 ^ min (k - 1) (R - 1)

theorem backoff_le (T₀ R k : ℕ) : backoff T₀ R k ≤ T₀ * 2 ^ (R - 1) :=
  Nat.mul_le_mul_left _ (Nat.pow_le_pow_right (by norm_num) (min_le_right _ _))

/-- The send times of an open request: the first at `t₀`, then each after its backoff. -/
def sendAt (t₀ T₀ R : ℕ) : ℕ → ℕ
  | 0 => t₀
  | k + 1 => sendAt t₀ T₀ R k + backoff T₀ R (k + 1)

/-- **The timer fires in every window of `2^(R-1) T₀ + 1` ticks.** With `T₀ ≥ 1`, for every tick
`u ≥ t₀` there is a send in `[u, u + 2^(R-1) T₀]`. -/
theorem timer_fires (t₀ T₀ R : ℕ) (hT : 1 ≤ T₀) (u : ℕ) (hu : t₀ ≤ u) :
    ∃ k, u ≤ sendAt t₀ T₀ R k ∧ sendAt t₀ T₀ R k ≤ u + T₀ * 2 ^ (R - 1) := by
  -- the send times are strictly increasing, so some send is the first at or after `u`
  have hpos : ∀ k, 1 ≤ backoff T₀ R (k + 1) := fun k =>
    Nat.one_le_iff_ne_zero.2 (Nat.mul_ne_zero (by omega) (by positivity))
  have hmono : ∀ k, k ≤ sendAt t₀ T₀ R k - t₀ ∧ t₀ ≤ sendAt t₀ T₀ R k := by
    intro k
    induction k with
    | zero => simp [sendAt]
    | succ k ih => have := hpos k; simp only [sendAt]; omega
  have hex : ∃ k, u ≤ sendAt t₀ T₀ R k := ⟨u, by have := hmono u; omega⟩
  let k := Nat.find hex
  have hk : u ≤ sendAt t₀ T₀ R k := Nat.find_spec hex
  refine ⟨k, hk, ?_⟩
  rcases Nat.eq_zero_or_pos k with h0 | hpos'
  · rw [h0] at hk ⊢; simp only [sendAt] at hk ⊢; omega
  · obtain ⟨j, hj⟩ : ∃ j, k = j + 1 := ⟨k - 1, by omega⟩
    have hlt : sendAt t₀ T₀ R j < u := by
      by_contra hc
      exact Nat.find_min hex (show j < k by omega) (by omega)
    rw [hj]; simp only [sendAt]
    have := backoff_le T₀ R (j + 1)
    omega

end SwarmInfer.CoverWeave.Ladder

open SwarmInfer.CoverWeave.Ladder in
#print axioms offers_le
open SwarmInfer.CoverWeave.Ladder in
#print axioms timer_fires
