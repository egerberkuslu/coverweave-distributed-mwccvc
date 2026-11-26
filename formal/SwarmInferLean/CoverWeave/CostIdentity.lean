import Mathlib

/-!
# CoverWeave: the cost identity (inventory C11)

`thm:msg` (`CoverWeave_R1/sections/04-formaleng.tex:155`), Theorem (Cost identity), with Table
`tab:phaseslots`. In a lossless run of the MIS arm without tree aggregation, certificate wave or
relayed invitation,

  `tx = h + 4m + 2J + 2Z + Λ`,  `rx = h̄ + 4m + 2J + 2Z + Λ`,

with `J` the JOIN and `Z` the HANDOVER and PUSH transmissions *counted with repeats*, and under
the synchronous scheduler `h ≤ nS`, `h̄ ≤ 2mS`.

The run is abstracted to its finite set of frame transmissions `ι`, each with a family label.
The proof's three facts ("each edge runs one LINK handshake per direction, every request
transmission gets one reply, a late acknowledgment one confirmation") become hypotheses on the
family counts. The file then settles the mismatch the inventory reports: the table bounds
`J ≤ 8m` and the bound on `Z` count *distinct* requests, the identity counts transmissions, and
the example `table_bound_does_not_bound_J` shows that the former does not bound the latter.
`tx_le_of_repeats` is the corrected bound.
-/

namespace SwarmInfer.CoverWeave.Cost

open Finset

/-- Frame families of a lossless MIS run without tree aggregation, certificate wave or relayed
invitation, as the proof of `thm:msg` lists them. `edgeReq` is a HANDOVER or PUSH, `edgeRep` its
reply, `conf` the confirmation of a late acknowledgment. -/
inductive Family
  | hello | linkReq | linkRep | join | joinRep | edgeReq | edgeRep | conf
  deriving DecidableEq, Fintype

variable {ι : Type*} [Fintype ι] (fam : ι → Family)

/-- Number of transmissions of family `f`. -/
def cnt (f : Family) : ℕ := #{i | fam i = f}

theorem card_eq_sum_cnt : Fintype.card ι = ∑ f, cnt fam f := by
  rw [← card_univ, card_eq_sum_card_fiberwise (f := fam) (t := univ) (fun _ _ => mem_univ _)]
  rfl

theorem sum_family (g : Family → ℕ) : ∑ f, g f =
    g .hello + g .linkReq + g .linkRep + g .join + g .joinRep + g .edgeReq + g .edgeRep + g .conf := by
  rw [show (univ : Finset Family) = {.hello, .linkReq, .linkRep, .join, .joinRep, .edgeReq,
    .edgeRep, .conf} by decide]
  simp [add_assoc]

/-- **Theorem (Cost identity)**, transmissions, `thm:msg`, inventory C11, equation `eq:costid`.
If the HELLO count is `h`, each LINK family has `2m` frames (one handshake per direction of each
edge), the JOIN replies equal the JOIN transmissions `J`, the edge replies equal the HANDOVER and
PUSH transmissions `Z` (both with repeats), and the confirmations number `Λ`, then
`tx = h + 4m + 2J + 2Z + Λ`.

Modelling choices:
* A run is its finite set `ι` of frame transmissions; `tx = |ι|`. The quantities are parameters.
* The family list `Family` is the one in the proof. That a lossless run of the stated arm sends
  no other frame (completeness of the list) is a property of the protocol that the type encodes
  and the paper asserts without proof; it stays on paper, as does the derivation of the count
  hypotheses from the execution model (inventory E7).
As the inventory notes, the identity is an accounting identity once those hypotheses are granted:
the theorem formalizes it as stated. -/
theorem cost_identity_tx {h m J Z Λ : ℕ} (hH : cnt fam .hello = h)
    (hLq : cnt fam .linkReq = 2 * m) (hLp : cnt fam .linkRep = 2 * m)
    (hJ : cnt fam .join = J) (hJr : cnt fam .joinRep = J)
    (hZ : cnt fam .edgeReq = Z) (hZr : cnt fam .edgeRep = Z) (hC : cnt fam .conf = Λ) :
    Fintype.card ι = h + 4 * m + 2 * J + 2 * Z + Λ := by
  rw [card_eq_sum_cnt, sum_family]
  rw [hH, hLq, hLp, hJ, hJr, hZ, hZr, hC]
  ring

/-- **Theorem (Cost identity)**, deliveries, `thm:msg`, inventory C11. With `d i` the number of
deliveries of transmission `i`, `h̄` the HELLO deliveries, and every non-HELLO frame (a unicast on a
lossless channel) delivered exactly once, `rx = h̄ + 4m + 2J + 2Z + Λ`.

Added hypotheses (modelling of "lossless"): `hd`, every non-HELLO transmission is delivered
exactly once. -/
theorem cost_identity_rx (d : ι → ℕ) {h m J Z Λ hbar : ℕ} (hH : cnt fam .hello = h)
    (hLq : cnt fam .linkReq = 2 * m) (hLp : cnt fam .linkRep = 2 * m)
    (hJ : cnt fam .join = J) (hJr : cnt fam .joinRep = J)
    (hZ : cnt fam .edgeReq = Z) (hZr : cnt fam .edgeRep = Z) (hC : cnt fam .conf = Λ)
    (hd : ∀ i, fam i ≠ .hello → d i = 1) (hbar_def : ∑ i ∈ {i | fam i = .hello}, d i = hbar) :
    ∑ i, d i = hbar + 4 * m + 2 * J + 2 * Z + Λ := by
  have hsplit := sum_filter_add_sum_filter_not univ (fun i => fam i = .hello) d
  have hrest : ∑ i ∈ {i | ¬ fam i = .hello}, d i = #{i | ¬ fam i = .hello} := by
    rw [card_eq_sum_ones]
    exact sum_congr rfl fun i hi => hd i (mem_filter.mp hi).2
  have hcard := card_filter_add_card_filter_not (s := univ) (fun i => fam i = .hello)
  rw [card_univ, cost_identity_tx fam hH hLq hLp hJ hJr hZ hZr hC] at hcard
  have : cnt fam .hello = #{i | fam i = .hello} := rfl
  omega

/-! ### The HELLO bounds -/

variable {V : Type*} [Fintype V] [DecidableEq V]

omit [DecidableEq V] in
/-- `h ≤ nS`: if no node sends two HELLOs in one slot of the `S` slots, there are at most `nS`
HELLO transmissions. -/
theorem hello_le {S : ℕ} (snd : ι → V) (slot : ι → Fin S)
    (hone : Set.InjOn (fun i => (snd i, slot i)) {i | fam i = .hello}) :
    cnt fam .hello ≤ Fintype.card V * S := by
  calc cnt fam .hello ≤ #(univ : Finset (V × Fin S)) :=
        card_le_card_of_injOn _ (fun _ _ => mem_univ _) fun x hx y hy hxy =>
          hone (by simpa using hx) (by simpa using hy) hxy
    _ = Fintype.card V * S := by simp

/-- `h̄ ≤ 2mS`: if moreover each HELLO of `v` is delivered to at most `deg(v)` nodes of the graph
`G` the HELLOs travel on, there are at most `2|E(G)| S` HELLO deliveries.

Modelling choice: `G` is the graph on which HELLOs are delivered (the radio graph). As the
inventory notes, `m` in `h̄ ≤ 2mS` is its edge count, which equals `|E(Ĝ*)|` only when the radio
graph and the discovered graph coincide; the paper should say which `m` it means. -/
theorem helloDeliveries_le (G : SimpleGraph V) [DecidableRel G.Adj] {S : ℕ} (snd : ι → V)
    (slot : ι → Fin S) (hone : Set.InjOn (fun i => (snd i, slot i)) {i | fam i = .hello})
    (d : ι → ℕ) (hdeg : ∀ i, fam i = .hello → d i ≤ G.degree (snd i)) :
    ∑ i ∈ {i | fam i = .hello}, d i ≤ 2 * #G.edgeFinset * S := by
  calc ∑ i ∈ {i | fam i = .hello}, d i ≤ ∑ i ∈ {i | fam i = .hello}, G.degree (snd i) :=
        sum_le_sum fun i hi => hdeg i (mem_filter.mp hi).2
    _ = ∑ p ∈ ({i | fam i = .hello} : Finset ι).image (fun i => (snd i, slot i)),
          G.degree p.1 := (sum_image (f := fun p => G.degree p.1)
            (s := ({i | fam i = .hello} : Finset ι)) fun x hx y hy hxy =>
            hone (by simpa using hx) (by simpa using hy) hxy).symm
    _ ≤ ∑ p : V × Fin S, G.degree p.1 :=
        sum_le_sum_of_subset_of_nonneg (subset_univ _) fun _ _ _ => Nat.zero_le _
    _ = 2 * #G.edgeFinset * S := by
        have hg : ∀ g : V → ℕ, ∑ p : V × Fin S, g p.1 = (∑ v, g v) * S := fun g => by
          rw [Fintype.sum_prod_type, sum_mul]; simp [mul_comm]
        rw [hg (fun v => G.degree v), G.sum_degrees_eq_twice_card_edges]

#print axioms cost_identity_tx
#print axioms cost_identity_rx
#print axioms hello_le
#print axioms helloDeliveries_le

/-! ### Repeats: the table does not bound the identity, and the corrected bound -/

/-- `J₀`: the number of distinct JOIN requests, `rq i` being the request (sender and sequence
number) that transmission `i` carries. Repeats of a request keep its sequence number. -/
def distinctReq {R : Type*} [DecidableEq R] (rq : ι → R) (f : Family) : ℕ :=
  (({i | fam i = f} : Finset ι).image rq).card

/-- **The reported mismatch is real.** A run abstraction that satisfies every count hypothesis
of `cost_identity_tx` with `m = 1`, `h = Z = Λ = 0`, in which the one JOIN request is repeated
nine times: the distinct JOIN requests obey the table's `J₀ ≤ 8m`, the JOIN transmissions do
not, `J = 9 > 8 = 8m`, and `tx = 22` exceeds `h + 4m + 2·8m + 2Z + Λ = 20`, the value the
table's bound would give for the right side of `eq:costid`. So `J ≤ 8m` (and likewise the
bound on `Z`, which also counts requests without repeats) bounds neither `J` nor `tx`. -/
theorem table_bound_does_not_bound_J :
    ∃ (fam : Fin 22 → Family) (rq : Fin 22 → Unit),
      cnt fam .hello = 0 ∧ cnt fam .linkReq = 2 * 1 ∧ cnt fam .linkRep = 2 * 1 ∧
      cnt fam .join = 9 ∧ cnt fam .joinRep = 9 ∧ cnt fam .edgeReq = 0 ∧
      cnt fam .edgeRep = 0 ∧ cnt fam .conf = 0 ∧
      distinctReq fam rq .join ≤ 8 * 1 ∧ ¬ cnt fam .join ≤ 8 * 1 ∧
      ¬ Fintype.card (Fin 22) ≤ 0 + 4 * 1 + 2 * (8 * 1) + 2 * 0 + 0 := by
  refine ⟨fun i => if i.val < 2 then .linkReq else if i.val < 4 then .linkRep
    else if i.val < 13 then .join else .joinRep, fun _ => (), ?_⟩
  refine ⟨?_, ?_, ?_, ?_, ?_, ?_, ?_, ?_, ?_, ?_, by simp⟩ <;> decide

/-- **Corrected bound.** Let `J₀` and `Z₀` be the distinct JOIN and HANDOVER/PUSH requests
(the quantities the table bounds), and let every request be transmitted at most `a` times.
Then `J ≤ a J₀`, `Z ≤ a Z₀`, and with the table's `J₀ ≤ 8m`, `Z₀ ≤ zb` and the count hypotheses of
the identity,

  `tx ≤ h + 4m + 16 a m + 2 a zb + Λ`.

The paper has two ways to close its gap: bound the attempts per request in a lossless run (a
reply latency below `t_ack` gives `a = 1`, which the paper would have to show for push chains,
whose reply waits for the chain), or state the bound with `a`, as here.

Added hypotheses: `hrep`, at most `a` transmissions per request (the repeat bound the paper does
not state). -/
theorem tx_le_of_repeats {R : Type*} [DecidableEq R] (rq : ι → R) {a h m Λ zb : ℕ}
    (hrep : ∀ f r, (f = .join ∨ f = .edgeReq) → #{i | fam i = f ∧ rq i = r} ≤ a)
    (hH : cnt fam .hello = h) (hLq : cnt fam .linkReq = 2 * m) (hLp : cnt fam .linkRep = 2 * m)
    (hJr : cnt fam .joinRep = cnt fam .join) (hZr : cnt fam .edgeRep = cnt fam .edgeReq)
    (hC : cnt fam .conf = Λ)
    (hJ0 : distinctReq fam rq .join ≤ 8 * m) (hZ0 : distinctReq fam rq .edgeReq ≤ zb) :
    cnt fam .join ≤ a * distinctReq fam rq .join ∧
      cnt fam .edgeReq ≤ a * distinctReq fam rq .edgeReq ∧
      Fintype.card ι ≤ h + 4 * m + 16 * a * m + 2 * a * zb + Λ := by
  have key : ∀ f, (f = .join ∨ f = .edgeReq) → cnt fam f ≤ a * distinctReq fam rq f := by
    intro f hf
    refine card_le_mul_card_image _ a fun r _ => le_trans (le_of_eq ?_) (hrep f r hf)
    congr 1
    ext i
    simp
  have hJ := key .join (Or.inl rfl)
  have hZ := key .edgeReq (Or.inr rfl)
  refine ⟨hJ, hZ, ?_⟩
  rw [cost_identity_tx fam hH hLq hLp rfl hJr rfl hZr hC]
  have h1 : cnt fam .join ≤ a * (8 * m) := hJ.trans (Nat.mul_le_mul_left a hJ0)
  have h2 : cnt fam .edgeReq ≤ a * zb := hZ.trans (Nat.mul_le_mul_left a hZ0)
  nlinarith

#print axioms table_bound_does_not_bound_J
#print axioms tx_le_of_repeats

/-- Non-vacuity of the identity: a run with one edge (`m = 1`), one HELLO and nothing else
besides the two LINK handshakes. -/
example : Fintype.card (Fin 5) = 1 + 4 * 1 + 2 * 0 + 2 * 0 + 0 :=
  cost_identity_tx (fun i : Fin 5 => if i.val = 0 then .hello else if i.val < 3 then .linkReq
    else .linkRep) (by decide) (by decide) (by decide) (by decide) (by decide) (by decide)
    (by decide) (by decide)

end SwarmInfer.CoverWeave.Cost
