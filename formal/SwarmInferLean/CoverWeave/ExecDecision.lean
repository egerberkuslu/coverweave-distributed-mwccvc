import SwarmInferLean.CoverWeave.BackboneChain
import SwarmInferLean.CoverWeave.BackboneDomination

/-!
# CoverWeave, execution model of Phase 1a (inventory E7 for C12, C2 protocol part, C9 for Phase 1a)

Sources. `CoverWeave_R1/sections/03-system.tex`, Algorithm `alg:mis` (lines 63 to 81) and the
listing convention of line 59 (`role_u`, `phase_u` are what `v` last read from `u`'s HELLO);
`04-formaleng.tex`, Definition `def:model` (line 30: "under the synchronous scheduler a node takes
one step per slot, and a frame arrives in the next slot or is lost"), Proposition
`prop:mischain` (line 179) and Lemma `lem:backbone` (line 50).

The model. Time is slotted. `run ok en c₀ t` is the configuration at the end of slot `t`. In
slot `t + 1` every enabled node evaluates the rule of Algorithm `alg:mis` on its records (the
HELLOs that arrived by the start of the slot, sent in slot `t` or earlier), then broadcasts one
HELLO carrying its new state; the copy to `w` arrives in slot `t + 2` exactly when
`ok (t+1) v w = true`, otherwise it is lost and `w` keeps its older record. The loss pattern
`ok : ℕ → V → V → Bool` and the enabling `en : ℕ → V → Bool` are arbitrary.

Results.
* `run_sound`: for every loss pattern and enabling, a decided node has the role of the key-greedy
  set of `Backbone.lean` (safety, C2 protocol part), and a decided record is the true role.
* `decided_of_lossFree`: from every configuration reachable under any loss pattern, a stretch of
  `j` slots in which every frame between neighbours is delivered and every node is enabled
  decides every node of decision depth `< j` (`depth` of `BackboneChain.lean`).
* `depth_lt_of_decided`: from the start of Phase 1a, under every loss pattern, a node decided by
  the end of slot `t` has depth `< t`.
* `prop_mischain_exec` (C12): on a lossless channel a node decides in slot `d(v) + 1` exactly,
  Phase 1a ends in slot `R + 1` and not earlier, `R ≤ n − 1`, and the MIS role set it computes
  is exactly the key-greedy set.
* `phase1a_window` (C9 restricted to Phase 1a): `W = n` loss-free slots from every reachable
  configuration decide every node, and a configuration in which every node has decided is never
  left.
-/

namespace SwarmInfer.CoverWeave.Exec

open SimpleGraph Finset

/-- The Phase 1a part of a node state and of a HELLO record: undecided (phase 1a), or decided
with role MIS or OUT (phase 1b). A record holds both fields of one HELLO, so role and phase are
read together. -/
inductive Dec
  | undecided
  | mis
  | out
  deriving DecidableEq, Repr

/-- Loss pattern: `ok s u v = true` when the frame `u` sends in slot `s` reaches `v` in slot
`s + 1`. -/
abbrev LossPattern (V : Type*) := ℕ → V → V → Bool

/-- Enabling: `en s v = true` when `v` runs its rule in slot `s` (it is false while `v` is still
in Phase 0 or its keys are not ready). -/
abbrev Enabling (V : Type*) := ℕ → V → Bool

/-- A configuration: the own state `st v` of every node and the record `rcd v u` that `v`
holds of `u`, the Phase 1a fields of the last HELLO of `u` that reached `v`. -/
structure Cfg (V : Type*) where
  st : V → Dec
  rcd : V → V → Dec

variable {V K : Type*} [Fintype V] [LinearOrder K]
variable (G : SimpleGraph V) [DecidableRel G.Adj] (key : V → K)

/-- Algorithm `alg:mis` at node `v` on the records `r`. Lines 68 to 71: no incident edge gives
OUT. Lines 73 to 74: a smaller-key neighbour recorded as MIS gives OUT. Lines 75 to 76: every
smaller-key neighbour recorded at phase 1b or later (decided) gives MIS. Line 78: wait. -/
def misRule (v : V) (r : V → Dec) : Dec :=
  if ∃ u, G.Adj u v then
    if ∃ u, G.Adj u v ∧ key u < key v ∧ r u = .mis then .out
    else if ∀ u, G.Adj u v → key u < key v → r u ≠ .undecided then .mis
    else .undecided
  else .out

/-- One step of node `v`: an undecided node runs `misRule`, a decided one keeps its decision
("the decision is monotone", line 78). -/
def nodeStep (v : V) (s : Dec) (r : V → Dec) : Dec :=
  if s = .undecided then misRule G key v r else s

/-- The own state of `v` at the end of slot `t + 1`. -/
def stepSt (en : Enabling V) (t : ℕ) (c : Cfg V) (v : V) : Dec :=
  if en (t + 1) v then nodeStep G key v (c.st v) (c.rcd v) else c.st v

/-- Slot `t + 1`: step, then broadcast; a delivered HELLO overwrites the record. -/
def slot (ok : LossPattern V) (en : Enabling V) (t : ℕ) (c : Cfg V) : Cfg V :=
  ⟨stepSt G key en t c, fun v u => if ok (t + 1) u v then stepSt G key en t c u else c.rcd v u⟩

/-- The run from `c₀`: `run ok en c₀ t` is the configuration at the end of slot `t`. -/
def run (ok : LossPattern V) (en : Enabling V) (c₀ : Cfg V) : ℕ → Cfg V
  | 0 => c₀
  | t + 1 => slot G key ok en t (run ok en c₀ t)

/-- Start of Phase 1a: every node and every record undecided. -/
def init : Cfg V := ⟨fun _ => .undecided, fun _ _ => .undecided⟩

/-- The lossless channel and the scheduler that steps every node in every slot. -/
def lossless : LossPattern V := fun _ _ _ => true
def always : Enabling V := fun _ _ => true

open Classical in
/-- The role of `v` in the key-greedy set. -/
noncomputable def truth (v : V) : Dec := if keyGreedy G key v then .mis else .out

/-- The realized decision depth `R = max_v d(v)`. -/
noncomputable def realizedDepth : ℕ := univ.sup (depth G key)

/-- Soundness of a configuration: every decided state and every decided record is the true
key-greedy role, and a decided record belongs to a decided node. -/
def Sound (c : Cfg V) : Prop :=
  (∀ v, c.st v = .undecided ∨ c.st v = truth G key v) ∧
    ∀ v u, c.rcd v u = .undecided ∨ (c.rcd v u = truth G key u ∧ c.st u = truth G key u)

variable {G key}

omit [DecidableRel G.Adj] in
theorem truth_eq_mis_iff (v : V) : truth G key v = .mis ↔ keyGreedy G key v := by
  unfold truth; split_ifs with h <;> simp [h]

omit [DecidableRel G.Adj] in
theorem truth_ne_undecided (v : V) : truth G key v ≠ .undecided := by
  unfold truth; split_ifs <;> simp

omit [DecidableRel G.Adj] in
theorem truth_eq_out_of_not {v : V} (h : ¬ keyGreedy G key v) : truth G key v = .out := by
  unfold truth; simp [h]

theorem misRule_isolated {v : V} {r : V → Dec} (h : ¬ ∃ u, G.Adj u v) :
    misRule G key v r = .out := by
  unfold misRule; rw [ite_eq_right h]

theorem misRule_misNbr {v : V} {r : V → Dec} (h1 : ∃ u, G.Adj u v)
    (h : ∃ u, G.Adj u v ∧ key u < key v ∧ r u = .mis) : misRule G key v r = .out := by
  unfold misRule; rw [ite_eq_left h1, ite_eq_left h]

theorem misRule_all {v : V} {r : V → Dec} (h1 : ∃ u, G.Adj u v)
    (h2 : ¬ ∃ u, G.Adj u v ∧ key u < key v ∧ r u = .mis)
    (h3 : ∀ u, G.Adj u v → key u < key v → r u ≠ .undecided) : misRule G key v r = .mis := by
  unfold misRule; rw [ite_eq_left h1, ite_eq_right h2, ite_eq_left h3]

/-- When the rule waits. -/
theorem misRule_eq_undecided {v : V} {r : V → Dec} (h : misRule G key v r = .undecided) :
    (∃ u, G.Adj u v) ∧ (¬ ∃ u, G.Adj u v ∧ key u < key v ∧ r u = .mis) ∧
      ¬ ∀ u, G.Adj u v → key u < key v → r u ≠ .undecided := by
  by_cases h1 : ∃ u, G.Adj u v
  · by_cases h2 : ∃ u, G.Adj u v ∧ key u < key v ∧ r u = .mis
    · rw [misRule_misNbr h1 h2] at h; exact absurd h (by decide)
    · by_cases h3 : ∀ u, G.Adj u v → key u < key v → r u ≠ .undecided
      · rw [misRule_all h1 h2 h3] at h; exact absurd h (by decide)
      · exact ⟨h1, h2, h3⟩
  · rw [misRule_isolated h1] at h; exact absurd h (by decide)

theorem stepSt_of_ne {en : Enabling V} {t : ℕ} {c : Cfg V} {v : V}
    (h : c.st v ≠ .undecided) : stepSt G key en t c v = c.st v := by
  unfold stepSt nodeStep; split_ifs <;> rfl

theorem stepSt_of_und {en : Enabling V} {t : ℕ} {c : Cfg V} {v : V}
    (hen : en (t + 1) v = true) (h : c.st v = .undecided) :
    stepSt G key en t c v = misRule G key v (c.rcd v) := by
  unfold stepSt nodeStep; rw [ite_eq_left hen, ite_eq_left h]

theorem stepSt_cases {en : Enabling V} {t : ℕ} {c : Cfg V} {v : V} :
    stepSt G key en t c v = c.st v ∨
      (c.st v = .undecided ∧ stepSt G key en t c v = misRule G key v (c.rcd v)) := by
  by_cases h : c.st v = .undecided
  · by_cases hen : en (t + 1) v = true
    · exact Or.inr ⟨h, stepSt_of_und hen h⟩
    · left; unfold stepSt; rw [ite_eq_right hen]
  · exact Or.inl (stepSt_of_ne h)

/-- The rule of Algorithm `alg:mis` is sound on sound records. -/
theorem misRule_sound (v : V) (r : V → Dec)
    (hr : ∀ u, r u = .undecided ∨ r u = truth G key u) :
    misRule G key v r = .undecided ∨ misRule G key v r = truth G key v := by
  by_cases h1 : ∃ u, G.Adj u v
  · by_cases h2 : ∃ u, G.Adj u v ∧ key u < key v ∧ r u = .mis
    · right
      rw [misRule_misNbr h1 h2]
      obtain ⟨u, hadj, hlt, hu⟩ := h2
      have hgu : keyGreedy G key u := by
        rcases hr u with h | h
        · rw [hu] at h; exact absurd h (by decide)
        · exact (truth_eq_mis_iff u).1 (h ▸ hu)
      exact (truth_eq_out_of_not fun h => ((keyGreedy_iff G key v).1 h).2 u hadj hlt hgu).symm
    · by_cases h3 : ∀ u, G.Adj u v → key u < key v → r u ≠ .undecided
      · right
        rw [misRule_all h1 h2 h3]
        have : keyGreedy G key v := (keyGreedy_iff G key v).2 ⟨h1, fun u hadj hlt hgu => by
          rcases hr u with h | h
          · exact h3 u hadj hlt h
          · exact h2 ⟨u, hadj, hlt, h.trans ((truth_eq_mis_iff u).2 hgu)⟩⟩
        exact ((truth_eq_mis_iff v).2 this).symm
      · left
        unfold misRule; rw [ite_eq_left h1, ite_eq_right h2, ite_eq_right h3]
  · right
    rw [misRule_isolated h1]
    exact (truth_eq_out_of_not fun h => h1 ((keyGreedy_iff G key v).1 h).1).symm

omit [DecidableRel G.Adj] in
theorem sound_init : Sound G key (init : Cfg V) :=
  ⟨fun _ => Or.inl rfl, fun _ _ => Or.inl rfl⟩

theorem stepSt_sound {en : Enabling V} {t : ℕ} {c : Cfg V} (hc : Sound G key c) (v : V) :
    stepSt G key en t c v = .undecided ∨ stepSt G key en t c v = truth G key v := by
  rcases stepSt_cases (G := G) (key := key) (en := en) (t := t) (c := c) (v := v) with h | ⟨-, h⟩
  · rw [h]; exact hc.1 v
  · rw [h]; exact misRule_sound v _ fun u => (hc.2 v u).imp id (·.1)

/-- Soundness is preserved by every slot, whatever is lost and whoever is enabled. -/
theorem sound_slot {ok : LossPattern V} {en : Enabling V} {t : ℕ} {c : Cfg V}
    (hc : Sound G key c) : Sound G key (slot G key ok en t c) := by
  refine ⟨stepSt_sound hc, fun v u => ?_⟩
  show (if ok (t + 1) u v then stepSt G key en t c u else c.rcd v u) = .undecided ∨
    ((if ok (t + 1) u v then stepSt G key en t c u else c.rcd v u) = truth G key u ∧
      stepSt G key en t c u = truth G key u)
  by_cases hok : ok (t + 1) u v = true
  · rw [ite_eq_left hok]
    rcases stepSt_sound (en := en) (t := t) hc u with h | h
    · exact Or.inl h
    · exact Or.inr ⟨h, h⟩
  · rw [ite_eq_right hok]
    rcases hc.2 v u with h | ⟨h, hs⟩
    · exact Or.inl h
    · exact Or.inr ⟨h, by rw [stepSt_of_ne (hs ▸ truth_ne_undecided u), hs]⟩

theorem run_sound_of {ok : LossPattern V} {en : Enabling V} {c₀ : Cfg V}
    (h₀ : Sound G key c₀) : ∀ t, Sound G key (run G key ok en c₀ t)
  | 0 => h₀
  | t + 1 => sound_slot (run_sound_of h₀ t)

/-- **Safety of Phase 1a under every loss pattern.** In every run from the start of Phase 1a, a
node that has decided has the role of the key-greedy set. -/
theorem run_sound (ok : LossPattern V) (en : Enabling V) (t : ℕ) (v : V)
    (h : (run G key ok en init t).st v ≠ .undecided) :
    (run G key ok en init t).st v = truth G key v :=
  ((run_sound_of sound_init t).1 v).resolve_left h

/-- A decision is never revised. -/
theorem run_succ_of_ne {ok : LossPattern V} {en : Enabling V} {c₀ : Cfg V} {t : ℕ} {v : V}
    (h : (run G key ok en c₀ t).st v ≠ .undecided) :
    (run G key ok en c₀ (t + 1)).st v = (run G key ok en c₀ t).st v :=
  stepSt_of_ne h

omit [DecidableRel G.Adj] in
/-- A smaller-key neighbour in the key-greedy set bounds the depth (the `1 + min` case). -/
theorem depth_le_of_misNbr {u v : V} (hadj : G.Adj u v) (hlt : key u < key v)
    (hu : keyGreedy G key u) : depth G key v ≤ depth G key u + 1 := by
  classical
  have hmem : u ∈ ((univ.filter fun w => G.Adj w v ∧ key w < key v).filter
      fun w => keyGreedy G key w) := by simp [hadj, hlt, hu]
  rw [depth_eq]
  unfold depthStep
  rw [dite_eq_left ⟨u, hmem⟩]
  have := Finset.inf'_le (depth G key) hmem
  omega

/-- **Liveness in a loss-free stretch.** From a sound configuration at the end of slot `t₀`,
if every frame between neighbours sent in slots `t₀ + 1, …, t₀ + j − 1` is delivered and every
node is enabled in slots `t₀ + 1, …, t₀ + j`, then every node of depth `< j` has decided at the
end of slot `t₀ + j`. -/
theorem decided_of_lossFree (ok : LossPattern V) (en : Enabling V) (c₀ : Cfg V)
    (h₀ : Sound G key c₀) (t₀ : ℕ) :
    ∀ j, (∀ s, t₀ < s → s < t₀ + j → ∀ u v, G.Adj u v → ok s u v = true) →
      (∀ s, t₀ < s → s ≤ t₀ + j → ∀ v, en s v = true) →
      ∀ v, depth G key v < j → (run G key ok en c₀ (t₀ + j)).st v ≠ .undecided := by
  intro j
  induction j with
  | zero => intro _ _ v h; omega
  | succ j ih =>
    intro hok hen v hv
    have ih' := ih (fun s h1 h2 => hok s h1 (by omega)) (fun s h1 h2 => hen s h1 (by omega))
    have hcs : Sound G key (run G key ok en c₀ (t₀ + j)) := run_sound_of h₀ _
    -- records of neighbours of depth `< j` are fresh and decided
    have hfresh : ∀ u, G.Adj u v → depth G key u < j →
        (run G key ok en c₀ (t₀ + j)).rcd v u = truth G key u := by
      intro u hadj hu
      obtain ⟨j', rfl⟩ : ∃ j', j = j' + 1 := ⟨j - 1, by omega⟩
      have hdel : ok (t₀ + j' + 1) u v = true := hok _ (by omega) (by omega) u v hadj
      have hst := ih' u hu
      have hrec : (run G key ok en c₀ (t₀ + (j' + 1))).rcd v u =
          (run G key ok en c₀ (t₀ + (j' + 1))).st u := by
        show (if ok (t₀ + j' + 1) u v then _ else _) = _
        rw [ite_eq_left hdel]
        rfl
      rw [hrec]
      exact (hcs.1 u).resolve_left hst
    show stepSt G key en (t₀ + j) (run G key ok en c₀ (t₀ + j)) v ≠ .undecided
    rcases stepSt_cases (G := G) (key := key) (en := en) (t := t₀ + j) (c := run G key ok en c₀ (t₀ + j)) (v := v)
      with h | ⟨hund, h⟩
    · rw [h]
      intro hund
      have hen' : en (t₀ + j + 1) v = true := hen _ (by omega) (by omega) v
      rw [stepSt_of_und hen' hund] at h
      rw [← h] at hund
      obtain ⟨-, hM2, hM3⟩ := misRule_eq_undecided hund
      obtain ⟨hA, hB⟩ := depth_ready G key v
      by_cases hM : ∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u
      · obtain ⟨u, hadj, hlt, hgu, hdu⟩ := hA hM
        exact hM2 ⟨u, hadj, hlt,
          (hfresh u hadj (by omega)).trans ((truth_eq_mis_iff u).2 hgu)⟩
      · exact hM3 fun u hadj hlt => by
          rw [hfresh u hadj (by have := hB hM u hadj hlt; omega)]
          exact truth_ne_undecided u
    · rw [h]
      intro hu
      obtain ⟨-, hM2, hM3⟩ := misRule_eq_undecided hu
      obtain ⟨hA, hB⟩ := depth_ready G key v
      by_cases hM : ∃ u, G.Adj u v ∧ key u < key v ∧ keyGreedy G key u
      · obtain ⟨u, hadj, hlt, hgu, hdu⟩ := hA hM
        exact hM2 ⟨u, hadj, hlt,
          (hfresh u hadj (by omega)).trans ((truth_eq_mis_iff u).2 hgu)⟩
      · exact hM3 fun u hadj hlt => by
          rw [hfresh u hadj (by have := hB hM u hadj hlt; omega)]
          exact truth_ne_undecided u

/-- **Lower bound under every loss pattern.** From the start of Phase 1a, a node decided by the
end of slot `t`, and every node of which some record shows a decision, has depth `< t`. -/
theorem depth_lt_of_decided (ok : LossPattern V) (en : Enabling V) :
    ∀ t, (∀ v, (run G key ok en init t).st v ≠ .undecided → depth G key v < t) ∧
      (∀ v u, (run G key ok en init t).rcd v u ≠ .undecided → depth G key u < t) := by
  intro t
  induction t with
  | zero => exact ⟨fun v h => absurd rfl h, fun v u h => absurd rfl h⟩
  | succ t ih =>
    have hcs : Sound G key (run G key ok en init t) := run_sound_of sound_init t
    have hst : ∀ v, stepSt G key en t (run G key ok en init t) v ≠ .undecided →
        depth G key v < t + 1 := by
      intro v hv
      rcases stepSt_cases (G := G) (key := key) (en := en) (t := t) (c := run G key ok en init t) (v := v)
        with h | ⟨-, h⟩
      · rw [h] at hv; have := ih.1 v hv; omega
      · rw [h] at hv
        set r := (run G key ok en init t).rcd v
        by_cases h1 : ∃ u, G.Adj u v
        · by_cases h2 : ∃ u, G.Adj u v ∧ key u < key v ∧ r u = .mis
          · obtain ⟨u, hadj, hlt, hu⟩ := h2
            have hdu := ih.2 v u (by simp only [r] at hu; rw [hu]; decide)
            have hgu : keyGreedy G key u := by
              rcases hcs.2 v u with h | ⟨h, -⟩
              · simp only [r] at hu; rw [hu] at h; exact absurd h (by decide)
              · exact (truth_eq_mis_iff u).1 (h ▸ hu)
            have := depth_le_of_misNbr hadj hlt hgu
            omega
          · have h3 : ∀ u, G.Adj u v → key u < key v → r u ≠ .undecided := by
              by_contra h3
              exact hv (by unfold misRule; rw [ite_eq_left h1, ite_eq_right h2, ite_eq_right h3])
            rcases depth_cases G key v with ⟨-, h⟩ | ⟨-, u, hadj, hlt, hgu, -⟩ |
              ⟨-, -, -, u, hadj, hlt, he⟩
            · omega
            · rcases hcs.2 v u with h | ⟨h, -⟩
              · exact absurd h (h3 u hadj hlt)
              · exact absurd ⟨u, hadj, hlt, h.trans ((truth_eq_mis_iff u).2 hgu)⟩ h2
            · have := ih.2 v u (h3 u hadj hlt)
              omega
        · rcases depth_cases G key v with ⟨-, h⟩ | ⟨⟨u, hadj, -⟩, -⟩ | ⟨⟨u, hadj, -⟩, -⟩
          · omega
          · exact absurd ⟨u, hadj⟩ h1
          · exact absurd ⟨u, hadj⟩ h1
    refine ⟨hst, fun v u hvu => ?_⟩
    change (if ok (t + 1) u v then stepSt G key en t (run G key ok en init t) u
      else (run G key ok en init t).rcd v u) ≠ .undecided at hvu
    by_cases hok : ok (t + 1) u v = true
    · rw [ite_eq_left hok] at hvu; exact hst u hvu
    · rw [ite_eq_right hok] at hvu; have := ih.2 v u hvu; omega

theorem decided_iff_lossless (v : V) (t : ℕ) :
    (run G key lossless always init t).st v ≠ .undecided ↔ depth G key v < t := by
  refine ⟨(depth_lt_of_decided lossless always t).1 v, fun h => ?_⟩
  have := decided_of_lossFree (G := G) (key := key) lossless always init sound_init 0 t
    (fun _ _ _ _ _ _ => rfl) (fun _ _ _ _ => rfl) v h
  rwa [Nat.zero_add] at this

omit [DecidableRel G.Adj] in
theorem depth_le_realizedDepth (v : V) : depth G key v ≤ realizedDepth G key :=
  Finset.le_sup (f := depth G key) (mem_univ v)

/-- The MIS role set after Phase 1a on a lossless channel is the key-greedy set. -/
theorem phase1a_computes_keyGreedy (v : V) :
    (run G key lossless always init (realizedDepth G key + 1)).st v = .mis ↔
      keyGreedy G key v := by
  rw [run_sound lossless always _ v ((decided_iff_lossless v _).2
    (Nat.lt_succ_of_le (depth_le_realizedDepth v))), truth_eq_mis_iff]

/-- **Proposition `prop:mischain` (C12) on the execution model, and the protocol part of
`lem:backbone` (C2).** On a lossless channel under the synchronous scheduler, from the start of
Phase 1a:
1. node `v` has decided at the end of slot `t` exactly when `d(v) < t`, so it decides in slot
   `d(v) + 1`;
2. every node has decided at the end of slot `R + 1`, and if `V` is nonempty some node has not
   decided at the end of slot `R` (Phase 1a ends in slot `R + 1`, not earlier);
3. `R ≤ L` for every bound `L` on the length of key-increasing paths, and `R + 1 ≤ n`;
4. the decided roles are the key-greedy set: `v` ends MIS exactly when `keyGreedy G key v`.

Part 4 holds in every run under every loss pattern for every decided node (`run_sound`), and
the "only if" of part 1 holds under every loss pattern (`depth_lt_of_decided`).

Modelling choices:
* Ĝ* is a fixed `SimpleGraph` on a `Fintype` (the final epoch, `def:model` line 39), the keys are
  frozen and every node knows its neighbours' keys (`def:key`), so keys are a global map.
* A node's Phase 1a state is `Dec` (undecided = phase 1a; MIS or OUT = phase 1b). A record holds
  the role and the phase of one HELLO together (read off `bootstrap.py:713-718`, where
  `_on_hello` writes `nbr.role`, `nbr.phase` and `nbr.mis_nbrs` from the same frame).
* One slot: read the HELLOs of the previous slot, step, broadcast one HELLO (read off
  `sched.py:104-131`, `SyncScheduler._slot` delivers the previous slot's frames and then fires
  each node's timer, and `bbcvc.py:616-631`, `on_timer` drains, steps, then calls
  `_maybe_hello`).
* A decided node keeps its decision (`bbcvc.py:899-937`, `_rule_mis` sets `phase = PH_CONN` and
  is not called again).
* Rounds are slots; Phase 1a starts in the same slot at every node, with undecided records.
* Left out: Phase 0, the epoch mechanism and record expiry (the view is the frozen Ĝ*), and
  every later phase. Phase 1a reads no other frame type.

Added hypotheses: none. -/
theorem prop_mischain_exec :
    (∀ v t, (run G key lossless always init t).st v ≠ .undecided ↔ depth G key v < t) ∧
    (∀ v, (run G key lossless always init (realizedDepth G key + 1)).st v ≠ .undecided) ∧
    (Nonempty V → ∃ v, (run G key lossless always init (realizedDepth G key)).st v =
      .undecided) ∧
    (∀ L : ℕ, (∀ (x y : V) (p : G.Walk x y), KeyIncreasing key p → p.length ≤ L) →
      realizedDepth G key ≤ L) ∧
    (Nonempty V → realizedDepth G key + 1 ≤ Fintype.card V) ∧
    (∀ v, (run G key lossless always init (realizedDepth G key + 1)).st v = .mis ↔
      keyGreedy G key v) := by
  refine ⟨decided_iff_lossless, fun v => (decided_iff_lossless v _).2
    (Nat.lt_succ_of_le (depth_le_realizedDepth v)), fun hne => ?_,
    fun L hL => Finset.sup_le fun v _ => depth_le_of_keyPath_bound G key L hL v,
    fun hV => ?_, phase1a_computes_keyGreedy⟩
  · obtain ⟨v, -, hv⟩ := Finset.exists_mem_eq_sup univ (univ_nonempty_iff.2 hne) (depth G key)
    refine ⟨v, ?_⟩
    by_contra h
    have := (decided_iff_lossless v _).1 h
    unfold realizedDepth at this
    omega
  · obtain ⟨v, -, hv⟩ := Finset.exists_mem_eq_sup univ (univ_nonempty_iff.2 hV) (depth G key)
    have := depth_lt_card G key v
    unfold realizedDepth
    omega

/-- The configurations in which every node has decided. -/
def AllDecided (c : Cfg V) : Prop := ∀ v, c.st v ≠ .undecided

/-- **Lemma `lem:lossless` (C9) restricted to Phase 1a.** Let `W = n`. From every configuration
reachable from the start of Phase 1a under any loss pattern and any enabling, a stretch of `W`
slots in which every frame is delivered and every node is enabled ends with every node decided,
and a configuration in which every node has decided is never left, whatever is lost afterwards.

Modelling choices: as in `prop_mischain_exec`. "Silent" is read here as "every node decided":
Phase 1a alone has no closing barrier, and the HELLOs keep flowing, so the frame part of the
paper's silent configuration belongs to Phase 5 and is not modelled.

Added hypotheses: none. `W = n` depends on `n` only, as the lemma requires. -/
theorem phase1a_window (ok : LossPattern V) (en : Enabling V) (t₀ : ℕ)
    (hok : ∀ s, t₀ < s → s ≤ t₀ + Fintype.card V → ∀ u v, ok s u v = true)
    (hen : ∀ s, t₀ < s → s ≤ t₀ + Fintype.card V → ∀ v, en s v = true) :
    AllDecided (run G key ok en init (t₀ + Fintype.card V)) ∧
    ∀ t, AllDecided (run G key ok en init t) → AllDecided (run G key ok en init (t + 1)) :=
  ⟨fun v => decided_of_lossFree ok en init sound_init t₀ _
      (fun s h1 h2 u w _ => hok s h1 h2.le u w) hen v (depth_lt_card G key v),
    fun _ h v => by rw [run_succ_of_ne (h v)]; exact h v⟩


section Example

/-- The path `0 — 1 — 2`, adjacency as a Boolean function. -/
def p3Adj (i j : Fin 3) : Bool := i.val + 1 == j.val || j.val + 1 == i.val

/-- The path on three nodes. -/
def P3 : SimpleGraph (Fin 3) where
  Adj i j := p3Adj i j = true
  symm := ⟨by decide⟩
  loopless := ⟨by decide⟩

instance : DecidableRel P3.Adj := fun i j => inferInstanceAs (Decidable (p3Adj i j = true))

/-- Concrete runs on the path with key `i`. Lossless: node 2 (depth 2) is undecided after
slot 2 and MIS after slot 3, node 1 is OUT. With every frame of slot 1 lost, node 2 decides one
slot later, still as MIS. -/
example :
    (run P3 (fun i : Fin 3 => i.val) lossless always init 2).st 2 = .undecided ∧
    (run P3 (fun i : Fin 3 => i.val) lossless always init 3).st 2 = .mis ∧
    (run P3 (fun i : Fin 3 => i.val) lossless always init 3).st 1 = .out ∧
    (run P3 (fun i : Fin 3 => i.val) (fun s _ _ => s != 1) always init 3).st 2 = .undecided ∧
    (run P3 (fun i : Fin 3 => i.val) (fun s _ _ => s != 1) always init 4).st 2 = .mis := by
  decide

end Example

end SwarmInfer.CoverWeave.Exec

open SwarmInfer.CoverWeave.Exec in
#print axioms run_sound
open SwarmInfer.CoverWeave.Exec in
#print axioms decided_of_lossFree
open SwarmInfer.CoverWeave.Exec in
#print axioms depth_lt_of_decided
open SwarmInfer.CoverWeave.Exec in
#print axioms prop_mischain_exec
open SwarmInfer.CoverWeave.Exec in
#print axioms phase1a_computes_keyGreedy
open SwarmInfer.CoverWeave.Exec in
#print axioms phase1a_window
