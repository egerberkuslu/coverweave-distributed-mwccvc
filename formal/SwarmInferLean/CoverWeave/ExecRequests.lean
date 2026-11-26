import Mathlib

/-!
# CoverWeave, C8: duplicate requests change ownership at most once at each end

Source: `CoverWeave_R1/sections/04-formaleng.tex:115`, Lemma `lem:dup` (Duplicate requests), and
Algorithm `alg:ownership` (`03-system.tex:151-169`, `OnAck` with the acquisition count `θ(e)`).

The lemma is a property of the message handlers, so the model is a handler model: one node, the
frames it receives in an arbitrary order (any interleaving, any number of copies, which covers
every loss pattern and every reordering), and the state those frames change.

* Receiver end (`recvChanges_le_one`). A HANDOVER, PUSH or relay JOIN carries its sender and
  sequence number; the receiver keeps per sender the highest sequence number it executed
  (`mark`), answers a copy at or below the mark from its state, and otherwise executes the
  request: refused when its edge count differs from the receiver's modulo 256, otherwise taken
  or refused by an arbitrary admission rule `accept`. Every copy of one request changes the
  receiver's ownership at most once in total.
* Sender end, as the text writes it (`ackChanges_le_one`). An acknowledgment of request `r`
  releases the edge only if `θ(e)` still equals the value stored when `r` was sent. Every copy
  of the acknowledgment of `r` changes the sender's ownership at most once in total, whatever
  else happens in between.
* Sender end, as the code writes it (`code_late_ack_twice`). An acknowledgment whose request is no
  longer pending goes to the late-acknowledgment path (`bbcvc.py:2058-2061` to `_on_late_ack`,
  `bbcvc.py:2504-2548`), which releases the edge when it is offered and still held, without
  comparing `θ(e)`. Then two copies of one acknowledgment can change ownership twice: the first
  releases the edge, the edge comes back (`_accept_edge` cancels the offer, `bbcvc.py:2373`), it
  is offered again in a new request (`bbcvc.py:1913`), and a second copy of the old
  acknowledgment releases it again.
* Sequence numbers in the code are 16-bit serial numbers (`_repeated`, `bbcvc.py:2007-2024`);
  `serialNew_wraps` shows that an old copy counts as new once the mark has advanced by more than
  `2^15`, so the receiver statement needs that bound (the model uses unbounded naturals).

Left out: push chains (the lemma names its own exception for a copy of a PUSH whose chain still
runs), the reply cache (it changes only what is answered, not the state), epochs (a frame of
another epoch is dropped before every check, so it changes nothing).
-/

namespace SwarmInfer.CoverWeave.Exec

/-! ### Receiver end -/

/-- A request as the receiver sees it: sender, sequence number, edge, carried edge count. -/
structure Req (P E : Type*) where
  sender : P
  seq : ℕ
  edge : E
  count : ℕ

/-- Receiver state: highest executed sequence number per sender (`0` before any), ownership,
and the count of completed transfers per edge. -/
structure RState (P E : Type*) where
  mark : P → ℕ
  owned : E → Bool
  count : E → ℕ

variable {P E : Type*} [DecidableEq P] [DecidableEq E]

/-- The receiver handler of `lem:dup`: a copy at or below the mark changes nothing; otherwise
the mark moves to the request, a request whose edge count differs modulo 256 is refused, and
an admitted request takes the edge and counts the transfer. `accept` is any admission rule (room,
the yield rule of mutual transfers, ...). -/
def recv (accept : RState P E → Req P E → Bool) (st : RState P E) (r : Req P E) : RState P E :=
  if st.mark r.sender < r.seq then
    let st' : RState P E := { st with mark := Function.update st.mark r.sender r.seq }
    if r.count % 256 = st.count r.edge % 256 ∧ accept st r = true then
      { st' with owned := Function.update st.owned r.edge true,
                 count := Function.update st.count r.edge (st.count r.edge + 1) }
    else st'
  else st

/-- The number of arrivals of copies of request `(p, q)` that change the receiver's ownership. -/
def recvChanges (accept : RState P E → Req P E → Bool) (p : P) (q : ℕ) :
    RState P E → List (Req P E) → ℕ
  | _, [] => 0
  | st, r :: rs =>
    (if r.sender = p ∧ r.seq = q ∧ (recv accept st r).owned r.edge ≠ st.owned r.edge then 1
      else 0) +
      recvChanges accept p q (recv accept st r) rs

/-- A copy at or below the mark changes no state. -/
theorem recv_of_not_new (accept : RState P E → Req P E → Bool) {st : RState P E} {r : Req P E}
    (h : ¬ st.mark r.sender < r.seq) : recv accept st r = st := by
  unfold recv; rw [ite_eq_right h]

/-- The mark never decreases. -/
theorem le_mark_recv (accept : RState P E → Req P E → Bool) (st : RState P E) (r : Req P E)
    (p : P) : st.mark p ≤ (recv accept st r).mark p := by
  unfold recv
  split_ifs with h1 h2
  · simp only [Function.update_apply]; split_ifs with h
    · subst h; omega
    · exact le_rfl
  · simp only [Function.update_apply]; split_ifs with h
    · subst h; omega
    · exact le_rfl
  · exact le_rfl

theorem recvChanges_eq_zero (accept : RState P E → Req P E → Bool) (p : P) (q : ℕ) :
    ∀ (rs : List (Req P E)) (st : RState P E), q ≤ st.mark p → recvChanges accept p q st rs = 0
  | [], _, _ => rfl
  | r :: rs, st, h => by
    unfold recvChanges
    rw [recvChanges_eq_zero accept p q rs _ (h.trans (le_mark_recv accept st r p))]
    split_ifs with hc
    · obtain ⟨hp, hq, hch⟩ := hc
      exact absurd (by rw [recv_of_not_new accept (by rw [hp, hq]; omega)]) hch
    · rfl

/-- **Lemma `lem:dup`, receiver end.** Whatever the order of arrivals and whatever other
requests arrive in between, the copies of one request `(p, q)` change the receiver's ownership at
most once in total, and a copy at or below the mark changes no state (`recv_of_not_new`).

Modelling choices: sequence numbers are naturals (no wrap-around), `mark p = 0` before the first
request of `p`, and the admission rule is arbitrary. Ownership is a map `E → Bool`.

Added hypotheses: none in the model; in the code the sequence numbers wrap at `2^16`
(`serialNew_wraps`), so the statement needs that fewer than `2^15` newer requests of the same
sender are executed while an old copy is still in flight. -/
theorem recvChanges_le_one (accept : RState P E → Req P E → Bool) (p : P) (q : ℕ) :
    ∀ (rs : List (Req P E)) (st : RState P E), recvChanges accept p q st rs ≤ 1
  | [], _ => Nat.zero_le _
  | r :: rs, st => by
    unfold recvChanges
    by_cases hc : r.sender = p ∧ r.seq = q ∧ (recv accept st r).owned r.edge ≠ st.owned r.edge
    · rw [ite_eq_left hc]
      obtain ⟨hp, hq, hch⟩ := hc
      have hnew : st.mark r.sender < r.seq := by
        by_contra h; exact hch (by rw [recv_of_not_new accept h])
      have hmark : q ≤ (recv accept st r).mark p := by
        unfold recv
        rw [ite_eq_left hnew]
        split_ifs <;> simp [← hp, hq]
      rw [recvChanges_eq_zero accept p q rs _ hmark]
    · rw [ite_eq_right hc, Nat.zero_add]
      exact recvChanges_le_one accept p q rs _

/-- The serial-number test of the code (RFC 1982, 16 bits): `seq` counts as new against `mark`
when `0 < (seq − mark) mod 2^16 < 2^15`. -/
def serialNew (seq mark : ℕ) : Bool :=
  0 < (seq + 65536 - mark % 65536) % 65536 && (seq + 65536 - mark % 65536) % 65536 < 32768

/-- Wrap-around: once the mark is `2^15 + 1` above an old request, a copy of it counts as new
again and would be executed twice. -/
theorem serialNew_wraps : serialNew 0 32769 = true ∧ serialNew 0 1 = false := by decide

/-! ### Sender end -/

/-- Sender state for one node: ownership and the acquisition count `θ(e)` of every edge. -/
structure SState (E : Type*) where
  owned : E → Bool
  theta : E → ℕ

/-- Events at the sender: it takes an edge (a transfer in, `θ(e)` counts it), or a copy of the
acknowledgment of request `r` arrives. Each request has an edge and the `θ` stored when it was
sent. -/
inductive SEv (R E : Type*)
  | take (e : E)
  | ack (r : R)
  deriving DecidableEq

variable {R : Type*} [DecidableEq R]

/-- `OnAck` of Algorithm `alg:ownership`: release `e` iff `θ(e) = θ_sent`. -/
def sstep (edge : R → E) (θs : R → ℕ) (st : SState E) : SEv R E → SState E
  | .take e => ⟨Function.update st.owned e true, Function.update st.theta e (st.theta e + 1)⟩
  | .ack r => if st.theta (edge r) = θs r then
      { st with owned := Function.update st.owned (edge r) false } else st

/-- The number of acknowledgment copies of `r` that change the sender's ownership. -/
def ackChanges (edge : R → E) (θs : R → ℕ) (r : R) : SState E → List (SEv R E) → ℕ
  | _, [] => 0
  | st, ev :: evs =>
    (if ev = .ack r ∧ (sstep edge θs st ev).owned (edge r) ≠ st.owned (edge r) then 1
      else 0) +
      ackChanges edge θs r (sstep edge θs st ev) evs

/-- After the acknowledgment of `r` has acted, it can act no more: either the edge is released
and `θ` is still the stored value, or `θ` has moved past it. -/
def Spent (edge : R → E) (θs : R → ℕ) (r : R) (st : SState E) : Prop :=
  (st.owned (edge r) = false ∧ st.theta (edge r) = θs r) ∨ θs r < st.theta (edge r)

omit [DecidableEq R] in
theorem spent_sstep (edge : R → E) (θs : R → ℕ) (r : R) {st : SState E}
    (h : Spent edge θs r st) (ev : SEv R E) : Spent edge θs r (sstep edge θs st ev) := by
  unfold Spent at h ⊢
  cases ev with
  | take e =>
    simp only [sstep]
    by_cases he : e = edge r
    · subst he; right; simp only [Function.update_self]; rcases h with ⟨-, h⟩ | h <;> omega
    · simpa [Function.update_of_ne (Ne.symm he)] using h
  | ack r' =>
    simp only [sstep]
    split_ifs
    · by_cases he : edge r' = edge r
      · simp only [he, Function.update_self]
        rcases h with ⟨-, h⟩ | h
        · exact Or.inl ⟨trivial, h⟩
        · exact Or.inr h
      · simpa [Function.update_of_ne (Ne.symm he)] using h
    · exact h

theorem ackChanges_eq_zero (edge : R → E) (θs : R → ℕ) (r : R) :
    ∀ (evs : List (SEv R E)) (st : SState E), Spent edge θs r st →
      ackChanges edge θs r st evs = 0
  | [], _, _ => rfl
  | ev :: evs, st, h => by
    unfold ackChanges
    rw [ackChanges_eq_zero edge θs r evs _ (spent_sstep edge θs r h ev)]
    split_ifs with hc
    · obtain ⟨rfl, hch⟩ := hc
      exfalso
      apply hch
      simp only [sstep]
      split_ifs with hθ
      · rcases h with ⟨ho, -⟩ | h
        · show Function.update st.owned (edge r) false (edge r) = st.owned (edge r)
          rw [Function.update_self, ho]
        · omega
      · rfl
    · rfl

/-- **Lemma `lem:dup`, sender end, as the text states it.** With `OnAck` comparing `θ(e)`
(Algorithm `alg:ownership`), the copies of the acknowledgment of one request change the
sender's ownership at most once in total, for every order of arrivals and every interleaving
with other takes and acknowledgments.

Modelling choices: a take of an edge raises `θ` by one (`θ(e)` is "the number of times `v` has
taken `e`"); releases come only from acknowledgments; ownership is a map `E → Bool`.

Added hypotheses: none. -/
theorem ackChanges_le_one (edge : R → E) (θs : R → ℕ) (r : R) :
    ∀ (evs : List (SEv R E)) (st : SState E), ackChanges edge θs r st evs ≤ 1
  | [], _ => Nat.zero_le _
  | ev :: evs, st => by
    unfold ackChanges
    by_cases hc : ev = .ack r ∧ (sstep edge θs st ev).owned (edge r) ≠ st.owned (edge r)
    · rw [ite_eq_left hc]
      obtain ⟨rfl, hch⟩ := hc
      have hθ : st.theta (edge r) = θs r := by
        by_contra h; exact hch (by simp only [sstep]; rw [ite_eq_right h])
      have hsp : Spent edge θs r (sstep edge θs st (.ack r)) := by
        left; simp only [sstep]; rw [ite_eq_left hθ]; simp [hθ]
      rw [ackChanges_eq_zero edge θs r evs _ hsp]
    · rw [ite_eq_right hc, Nat.zero_add]
      exact ackChanges_le_one edge θs r evs _

/-! ### Sender end as the code implements it -/

/-- Sender state of the code: ownership, `θ` (`_takes`), offered edges (`_offered`) and the
pending requests (`_pending`). -/
structure CState (R E : Type*) where
  owned : E → Bool
  theta : E → ℕ
  offered : E → Bool
  pending : R → Bool

/-- Events: send request `r` (records it as pending, marks its edge offered,
`bbcvc.py:1900-1916`), take an edge (`_accept_edge`, which cancels the offer and counts the take,
`bbcvc.py:2352-2392`), or a copy of the acknowledgment of `r` arrives. -/
inductive CEv (R E : Type*)
  | offer (r : R)
  | take (e : E)
  | ack (r : R)
  deriving DecidableEq

/-- The code's handling (`bbcvc.py:2058-2061`): an acknowledgment of a pending request resolves
it with the `θ` check (`_resolve`, `bbcvc.py:2554-2575`); one of a request no longer pending goes
to `_on_late_ack`, which releases an edge that is offered and still held (read as owned here),
without a `θ` check. -/
def cstep (edge : R → E) (θs : R → ℕ) (st : CState R E) : CEv R E → CState R E
  | .offer r => { st with pending := Function.update st.pending r true,
                          offered := Function.update st.offered (edge r) true }
  | .take e => { st with owned := Function.update st.owned e true,
                         theta := Function.update st.theta e (st.theta e + 1),
                         offered := Function.update st.offered e false }
  | .ack r =>
    if st.pending r then
      let st' := { st with pending := Function.update st.pending r false }
      if st.theta (edge r) = θs r then
        { st' with owned := Function.update st.owned (edge r) false } else st'
    else if st.offered (edge r) ∧ st.owned (edge r) then
      { st with owned := Function.update st.owned (edge r) false }
    else st

/-- The number of acknowledgment copies of `r` that change the sender's ownership (code). -/
def cackChanges (edge : R → E) (θs : R → ℕ) (r : R) : CState R E → List (CEv R E) → ℕ
  | _, [] => 0
  | st, ev :: evs =>
    (if ev = .ack r ∧ (cstep edge θs st ev).owned (edge r) ≠ st.owned (edge r) then 1
      else 0) +
      cackChanges edge θs r (cstep edge θs st ev) evs

/-- **Counterexample to "at most once at the sender" for the code's late-acknowledgment path.**
One edge, two requests: `0` offers the edge with `θ = 0`, `1` offers it again later with `θ = 1`.
Arrivals: offer `0`, acknowledgment of `0` (releases), the edge is taken back, offer `1`, a second
copy of the acknowledgment of `0` (releases again, through `_on_late_ack`). Two changes. The
text's `OnAck` (`sstep`) ignores the second copy because `θ` moved from `0` to `1`. -/
theorem code_late_ack_twice :
    cackChanges (R := Fin 2) (E := Unit) (fun _ => ()) (fun r => r.val) 0
      ⟨fun _ => true, fun _ => 0, fun _ => false, fun _ => false⟩
      [.offer 0, .ack 0, .take (), .offer 1, .ack 0] = 2 ∧
    ackChanges (R := Fin 2) (E := Unit) (fun _ => ()) (fun r => r.val) 0
      ⟨fun _ => true, fun _ => 0⟩ [.ack 0, .take (), .ack 0] = 1 := by
  refine ⟨?_, ?_⟩ <;> decide

end SwarmInfer.CoverWeave.Exec

open SwarmInfer.CoverWeave.Exec in
#print axioms recvChanges_le_one
open SwarmInfer.CoverWeave.Exec in
#print axioms ackChanges_le_one
open SwarmInfer.CoverWeave.Exec in
#print axioms code_late_ack_twice
open SwarmInfer.CoverWeave.Exec in
#print axioms serialNew_wraps
