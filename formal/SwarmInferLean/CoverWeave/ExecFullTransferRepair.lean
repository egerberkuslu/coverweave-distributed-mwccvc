import SwarmInferLean.CoverWeave.ExecFullTransferInv
import SwarmInferLean.CoverWeave.ExecFullOwnership

/-!
# CoverWeave, Theorem 3(b) after the repairs R2, R3 and R4 (inventory C5(b), C8)

Source: `CoverWeave_R1/sections/04-formaleng.tex:77-87` (Theorem `thm:cap` (b)), `04-formaleng.tex:115-121`
(Lemma `lem:dup`), the code of branch `r2r3-repair` of `bbcvc-release` (`ccvc/bb/bbcvc.py`,
Amendment 17: `_on_push`, `_refuse`, `_repeat_ok`, `_finish_push_job`).

`ExecFullTransfer.lean` refutes Theorem 3(b) for the transfer layer of one flexible edge with three
traces. The branch `r2r3-repair` adds two rules, both modelled there as switches of `Params`:
R2 (`quietBusy`), a copy of the PUSH my chain serves gets no reply unless it takes the edge, and
R3 (`repeatByCount`), a repeat that missed the cache is acknowledged only if the receiver holds the
edge with its edge count one above the carried one.

Results.
* `thm3b_fails_r2r3`: R2 and R3 are not enough. `_accept_edge` counts an acquisition (`θ(e)`),
  cancels the offer and moves the retake mark before it knows that it fails for want of room, so a
  refused incoming HANDOVER makes the acknowledgement of the receiver's own HANDOVER stale, the
  receiver keeps its message-free claim and the other end holds the edge explicitly. With HANDOVERs
  only and without any eviction, the run ends quiet, with every positive answer delivered and the
  start agreed, and both ends own the edge. The repair R4 counts an acquisition only when it
  succeeds (`takeOnFail = false`, the text's `θ(e)`).
* `repaired_traces`: under R2, R3 and R4 none of the four counterexample traces ends badly.
* `thm3b_transfer_repaired`: under R2, R3 and R4, every quiet configuration reachable from the
  start of Phase 4 has complementary or absent settled decisions (`ConsistentPair`, the edge's
  instance of `ExplicitConsistent` of `ExecFullOwnership.lean`), hence exactly one owner once the
  message-free start is agreed. No acknowledgement hypothesis. General: any number of transfers,
  retransmissions, losses, evictions, budget changes and chain outcomes, unbounded sequence numbers
  and edge counts; one edge between its two ends, in-order channels. The proof is the inductive
  invariant of `ExecFullTransferInv.lean`.
* `each_rule_needed`: none of the five rules can be dropped. Without the yield rule, without the `θ`
  check on the late path, without R2, without R3 or without R4 (the other four kept) a run ends
  quiet, with every positive answer delivered and the start agreed, with two owners or none.
-/

namespace SwarmInfer.CoverWeave.ExecFull

/-! ### R2 and R3 do not suffice -/

/-- Two HANDOVERs of the same edge (both ends hold it by the message-free start). `b`'s budget
changes, so the start no longer gives `e` to `b`, which is full; `a`'s HANDOVER reaches `b`, which does
not yield, fails to take the edge for want of room and still counts an acquisition; `b`'s HANDOVER is
lost and retransmitted; `a` reads the refusal; `b`'s HANDOVER reaches `a`, which takes the edge;
`b` reads the acknowledgement with `θ` moved and keeps its claim. The budgets then change so that the
start gives `e` to `b`. -/
def traceTake : List Ev :=
  [.offer false false, .offer true false, .flip true, .deliver false false false, .lose true,
    .retx true 1, .deliver true false false, .deliver true false false,
    .deliver false false false, .flip true, .flip false]

/-- **Theorem 3(b) fails for the code of branch `r2r3-repair`.** With the yield rule, R2, R3 and
the code's `θ(e)` (an acquisition is counted when `_accept_edge` fails), there is a run of one
flexible edge, with HANDOVERs only and no eviction, that ends quiet, with every accepted transfer
acknowledged, every frame delivered in order and the message-free start agreed, in which both ends
own the edge.

Modelling choices: those of `ExecFullTransfer.lean`.

Added hypotheses: none. Smallest repair: R4, `_accept_edge` changes `_takes`, `_retake_seq` and
`_offered` only when it returns `True`. -/
theorem thm3b_fails_r2r3 :
    ∃ s, runEvs r2r3Params (start true true) traceTake = some s ∧ Quiet s ∧ AllAcked s ∧
      Agreed s ∧ owns s.a = true ∧ owns s.b = true :=
  bad_of_any (by decide)

/-- The first ten events of `traceBusy` (up to the end of `b`'s chain), then delivery of what is
in flight: under R2 the busy copy got no reply, so the chain's acknowledgement is the answer. -/
def traceBusyR2 : List Ev :=
  traceBusy.take 10 ++ [.deliver false false false, .deliver true false false]

/-- **The counterexample traces under R2, R3 and R4.** `traceNoYield`, `traceRepeat` and
`traceTake` end quiet with exactly one owner; `traceBusy` is not a run any more (its thirteenth
event delivers the busy refusal, which R2 removed), and its natural completion `traceBusyR2` ends
quiet with exactly one owner. -/
theorem repaired_traces :
    (runEvs repairParams (start true true) traceNoYield).any
      (fun s => quietB s && (owns s.a != owns s.b)) = true ∧
    runEvs repairParams (start true true) traceBusy = none ∧
    (runEvs repairParams (start true true) traceBusyR2).any
      (fun s => quietB s && (owns s.a != owns s.b)) = true ∧
    (runEvs repairParams (start true true) traceRepeat).any
      (fun s => quietB s && (owns s.a != owns s.b)) = true ∧
    (runEvs repairParams (start true true) traceTake).any
      (fun s => quietB s && (owns s.a != owns s.b)) = true := by
  decide

/-! ### The repaired transfer layer -/

theorem cp_iff (x y : Option Bool) : CP x y ↔ ConsistentPair x y := by
  rcases x with _ | _ | _ <;> rcases y with _ | _ | _ <;> simp [CP, ConsistentPair]

/-- **Theorem 3(b) for the transfer layer, repaired.** Under the yield rule, the `θ` check on the
late path, R2, R3 and R4 (`repairParams`), every quiet configuration reached by a run of one flexible
edge from the start of Phase 4 (any start values `da`, `db` of the message-free rule) has
complementary or absent settled decisions, and, once the two ends agree on the message-free start,
exactly one of them owns the edge.

Modelling choices: those of `ExecFullTransfer.lean` (one edge and its two ends, each direction a
FIFO channel that may lose any frame, unbounded sequence numbers and edge counts, the other edges
and the chain's further hops abstracted as the environment's choices `room`, `chain`, `ok` and
the budget changes `flip`, the reply cache evicting any entry at any time). "Quiet" is the part of
"silent" that concerns the edge: no frame in flight, no open request, no push chain.

Added hypotheses: none. The paper's hypothesis "every accepted transfer was acknowledged" is not
needed. The statement is about the repaired protocol (R2, R3, R4 and the two rules of the code the
text does not state); `each_rule_needed` shows each of them is necessary. -/
theorem thm3b_transfer_repaired (da db : Bool) (es : List Ev) {s : St}
    (hrun : runEvs repairParams (start da db) es = some s) (hq : Quiet s) :
    ConsistentPair s.a.X s.b.X ∧ (Agreed s → owns s.a ≠ owns s.b) := by
  have hcp := cp_of_quiet (runEvs_pres (inv_start da db) hrun) hq
  refine ⟨(cp_iff _ _).1 hcp, fun hag => ?_⟩
  simp only [Agreed, bne_iff_ne, ne_eq] at hag
  unfold owns
  revert hcp
  rcases s.a.X with _ | _ | _ <;> rcases s.b.X with _ | _ | _ <;>
    cases ha : s.a.dflt <;> cases hb : s.b.dflt <;> simp_all [CP]

/-- **Lemma 3 (`lem:dup`), the part about late answers, after the repairs.** In every reachable
configuration, an answer that reaches its requester when its request is no longer open leaves the
requester unchanged: the late path of `onRep` never releases the edge. Together with the receiver
side (a repeat is answered from the cache or by R3 and changes no ownership, a busy copy takes the
edge at most once) this is what "a request changes ownership at most once at each end" needs. -/
theorem late_answer_inert (da db : Bool) (es : List Ev) {s : St}
    (hrun : runEvs repairParams (start da db) es = some s) {i : Bool} {q : ℕ} {r : Rep}
    {l : List Frame} (hc : s.chan i = .rep q r :: l) (hnc : ¬ Cur (s.nd !i) q) :
    repNode (s.nd !i) q r = s.nd !i := by
  have H := runEvs_pres (inv_start da db) hrun
  have Hk := (inv_iff s).1 H (!i)
  rw [Bool.not_not, hc] at Hk
  have hA : A1 (s.nd !i) (s.nd i) q r := Hk.chanJ _ List.mem_cons_self
  refine repNode_late ?_ fun hr => hA.2.2.1 hr hnc
  rcases Hk.pend with hp | ⟨p, hp, -⟩
  · simp [hp]
  · have : p.seq ≠ q := fun h => hnc ⟨p, hp, h⟩
    simp [hp, this]

/-- The hypotheses of `thm3b_transfer_repaired` can hold together with an explicit transfer: the
run `traceTake` ends quiet, agreed, with `a` holding the edge explicitly and `b` having released
it. -/
example : (runEvs repairParams (start true true) traceTake).any (fun s =>
    quietB s && (s.a.dflt != s.b.dflt) && s.a.X == some true && s.b.X == some false) = true := by
  decide

/-- The run that needs the `θ` check on the late path: an acknowledgement copy of an offer made
before the edge came back releases it a second time (found by bounded search). -/
def traceFloor : List Ev :=
  [.offer false false, .retx false 1, .deliver false false false, .offer true false,
    .deliver true false false, .deliver false false false, .deliver true true false,
    .offer false false, .deliver false false false, .deliver false false false,
    .deliver true false false, .deliver true false false, .flip false]

/-- **Each rule is needed.** Dropping one of the five rules of `repairParams` and keeping the other
four, a run of one flexible edge ends quiet, with every positive answer delivered to its sender and
the message-free start agreed, with two owners or with none: without the yield rule
(`traceNoYield`), without the `θ` check on the late path (`traceFloor`), without R2 (`traceBusy`),
without R3 (`traceRepeat`), without R4 (`traceTake`). -/
theorem each_rule_needed :
    (∃ s, runEvs ⟨false, false, true, true, true, false, false⟩ (start true true) traceNoYield = some s ∧
      Quiet s ∧ AllAcked s ∧ Agreed s ∧ owns s.a = true ∧ owns s.b = true) ∧
    (∃ s, runEvs ⟨true, false, false, true, true, false, false⟩ (start true true) traceFloor = some s ∧
      Quiet s ∧ AllAcked s ∧ Agreed s ∧ owns s.a = false ∧ owns s.b = false) ∧
    (∃ s, runEvs ⟨true, false, true, false, true, false, false⟩ (start true true) traceBusy = some s ∧
      Quiet s ∧ AllAcked s ∧ Agreed s ∧ owns s.a = true ∧ owns s.b = true) ∧
    (∃ s, runEvs ⟨true, false, true, true, false, false, false⟩ (start true true) traceRepeat = some s ∧
      Quiet s ∧ AllAcked s ∧ Agreed s ∧ owns s.a = false ∧ owns s.b = false) ∧
    (∃ s, runEvs ⟨true, true, true, true, true, false, false⟩ (start true true) traceTake = some s ∧
      Quiet s ∧ AllAcked s ∧ Agreed s ∧ owns s.a = true ∧ owns s.b = true) :=
  ⟨bad_of_any (by decide), bad_of_any (by decide), bad_of_any (by decide),
    bad_of_any (by decide), thm3b_fails_r2r3⟩

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_transfer_repaired
open SwarmInfer.CoverWeave.ExecFull in
#print axioms each_rule_needed
open SwarmInfer.CoverWeave.ExecFull in
#print axioms late_answer_inert
open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_fails_r2r3
open SwarmInfer.CoverWeave.ExecFull in
#print axioms repaired_traces
