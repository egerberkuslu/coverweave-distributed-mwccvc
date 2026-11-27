import Mathlib

/-!
# CoverWeave, Theorem 3(b): the transfer layer of one flexible edge (inventory C5(b), C8, E7)

Source: `CoverWeave_R1/sections/04-formaleng.tex:77-87` (Theorem `thm:cap` (b) and its proof),
`04-formaleng.tex:115-121` (Lemma `lem:dup`), `03-system.tex:148-174` (Algorithm `alg:ownership`
and the paragraph after it), `03-system.tex:206-208` (Section `sec:loss`).

`ExecFullOwnership.lean` reduces the "exactly one owner" part of Theorem 3(b) to
`ExplicitConsistent`: in a silent configuration the settled decisions (`_explicit`) of the two
ends of a flexible edge must be complementary or both absent. This file models what writes those
decisions, the transfer protocol of one flexible edge `e = {a, b}` between its two ends, `a` the
end with the smaller key, and shows that silence together with the hypothesis of Theorem 3(b)
("every accepted transfer was acknowledged") does **not** give `ExplicitConsistent`.

The model. Each end keeps the fields of `bbcvc.py` that the handlers of `e` read or write:
`X` (`_explicit[e]`), `takes` (`_takes[e]`, the acquisition count `θ(e)`), `gen` (`_gen[e]`, the
edge count of `lem:dup`, here without the reduction modulo 256), `offered` (`e ∈ _offered`), its open
requests for `e` with the stored `θ` and edge count (`_pending`), `retake` (`_retake_seq[e]`), its
sequence counter, the mark and the reply cache of the other end's requests (`_mark`, `_seen`), the
push chain it serves for the other end's PUSH of `e` (`_push_job`), its open late
acknowledgements (`_pending` under `_LATE_KEY`), and `dflt`, whether the message-free start
currently gives it `e` (`_default_owner`, which reads advertised budgets that change during a
run). Each direction is a FIFO channel that may lose any frame (`lose`), so the channel keeps the
order of frames, as Theorem 3(b) assumes. A step is an event with the choices the environment
makes (the other edges decide whether there is room, and whether a chain succeeds).

Results.
* `thm3b_fails_without_yield`: with the mechanisms the text names (OnAck with `θ`, the edge count,
  the reply cache and the mark, accepting cancels one's own offer), two HANDOVERs of the same edge
  that cross leave both ends holding `e` in a quiet configuration in which every accepted transfer
  was acknowledged. The code closes this race with a rule the text does not state
  (`_yields_to_inbound`, `bbcvc.py:2332-2354`: an end with its own open request for `e` refuses
  an incoming one iff its key is smaller).
* `thm3b_fails_with_yield`: with that rule, and with every handler as the frozen code writes it,
  a PUSH refused as busy whose chain later succeeds (the late acknowledgement of `lem:dup`,
  `bbcvc.py:2474-2501`) and a HANDOVER of the same edge in the other direction again leave both
  ends holding `e`, with every frame delivered in order, no request, chain or late
  acknowledgement open and every positive answer delivered to its sender. The trace was found by
  a bounded exhaustive search of this model and replayed on the handlers of the frozen code.

The repairs R2 and R3 of branch `r2r3-repair` are the switches `quietBusy` and `repeatByCount` of
`Params`; `ExecFullTransferRepair.lean` shows that they need a third repair R4 (`takeOnFail =
false`) and proves Theorem 3(b) for the transfer layer under all five rules.
-/

namespace SwarmInfer.CoverWeave.ExecFull

/-- A reply: to a PUSH (`push`), positive (`ok`), a late acknowledgement asking for a
confirmation (`late`, `LATE_ASK`). -/
structure Rep where
  push : Bool
  ok : Bool
  late : Bool
  deriving DecidableEq, Repr

/-- Frames of the edge: a request (sequence number, PUSH or HANDOVER, carried edge count), a
reply to the request with that sequence number, a confirmation of a late acknowledgement. -/
inductive Frame
  | req (seq : ℕ) (push : Bool) (gen : ℕ)
  | rep (seq : ℕ) (r : Rep)
  | conf (seq : ℕ)
  deriving DecidableEq, Repr

/-- An open request: sequence number, kind, `θ(e)` and edge count when sent (`Pending`,
`bbcvc.py:403-417`, `_send_edge_msg`, `bbcvc.py:1904-1920`). -/
structure Pend where
  seq : ℕ
  push : Bool
  theta : ℕ
  gen : ℕ
  deriving DecidableEq, Repr

/-- The state of one end, restricted to the edge. -/
structure Node where
  X : Option Bool
  takes : ℕ
  gen : ℕ
  offered : Bool
  pend : List Pend
  retake : Option ℕ
  seqc : ℕ
  mark : Option ℕ
  cache : List (ℕ × Rep)
  job : Option (ℕ × Bool)
  late : List ℕ
  dflt : Bool
  deriving DecidableEq, Repr

/-- Both ends (`false` is `a`, the smaller key; `true` is `b`), the channel from each end, and two
ghost lists: the requests answered positively and the requests whose positive answer reached
their sender, each as (sender, sequence number). -/
structure St where
  a : Node
  b : Node
  fromA : List Frame
  fromB : List Frame
  acc : List (Bool × ℕ)
  ackd : List (Bool × ℕ)
  deriving DecidableEq, Repr

/-- Switches between the text and the code. `yieldRule`: `_yields_to_inbound`, which the text does
not state. `takeOnFail`: the code counts an acquisition, cancels the offer and moves the retake
mark before it knows whether the acceptance succeeds (`bbcvc.py:2375-2379`); the text's `θ(e)` is
"the number of times `v` has taken `e`". `floorCheck`: the `θ` check on the late path
(`bbcvc.py:2539-2548`, the one post-freeze change). `quietBusy`: repair R2 of branch `r2r3-repair`
(Amendment 17): a copy of the PUSH that my chain serves gets no reply when I cannot take the edge
(no busy NACK, hence no late acknowledgement). `repeatByCount`: repair R3: a repeat that missed
the cache is acknowledged only if the receiver holds `e` and its edge count is the carried one plus
one (`_repeat_ok`). `finalBusy`: repair R2' of commit 5d9936a: a busy refusal is final, a chain
whose request was refused as busy (`nacked`) never takes the edge, nor does a later copy.
`finalNack`: the further repair R2'' (Lean `traceFinalNack`): a refused request gets only refusals,
also from a chain that ends while its node holds the edge and from a busy copy. -/
structure Params where
  yieldRule : Bool
  takeOnFail : Bool
  floorCheck : Bool
  quietBusy : Bool
  repeatByCount : Bool
  finalBusy : Bool
  finalNack : Bool
  deriving DecidableEq, Repr

/-- The code as frozen, with the post-freeze `θ` check on the late path. -/
def codeParams : Params := ⟨true, true, true, false, false, false, false⟩
/-- The text: no yield rule, `θ(e)` counts takes, `OnAck` checks `θ` on every path. -/
def textParams : Params := ⟨false, false, true, false, false, false, false⟩
/-- The code of branch `r2r3-repair`: the frozen code with R2 and R3. -/
def r2r3Params : Params := ⟨true, true, true, true, true, false, false⟩
/-- R2 and R3 with R4: `θ(e)` counts only successful takes, so a failed `_accept_edge` changes
nothing (the text's `θ`). -/
def repairParams : Params := ⟨true, false, true, true, true, false, false⟩
/-- The code of commit 5d9936a of branch `r2r3-repair`: R2' and R3, without R4. -/
def branchParams : Params := ⟨true, true, true, false, true, true, false⟩
/-- R2', R3 and R4. -/
def r2pParams : Params := ⟨true, false, true, false, true, true, false⟩
/-- R2'' (R2' with refusals final), R3 and R4. -/
def r2ppParams : Params := ⟨true, false, true, false, true, true, true⟩

@[simp] theorem repairParams_finalBusy : repairParams.finalBusy = false := rfl
@[simp] theorem repairParams_finalNack : repairParams.finalNack = false := rfl
@[simp] theorem repairParams_quietBusy : repairParams.quietBusy = true := rfl
@[simp] theorem r2ppParams_finalBusy : r2ppParams.finalBusy = true := rfl
@[simp] theorem r2ppParams_finalNack : r2ppParams.finalNack = true := rfl
@[simp] theorem r2ppParams_quietBusy : r2ppParams.quietBusy = false := rfl

/-- The events and the choices the environment makes. -/
inductive Ev
  /-- `i` offers `e` (stage 1 HANDOVER or stage 2 PUSH of `_fix_overload`) -/
  | offer (i : Bool) (push : Bool)
  /-- `i` retransmits its open request `seq` with the same payload (`_retry_pending`) -/
  | retx (i : Bool) (seq : ℕ)
  /-- `i` retransmits its open late acknowledgement `seq` -/
  | lretx (i : Bool) (seq : ℕ)
  /-- `i`'s reply cache evicts the reply to `seq` (`σ` replies per peer, `_seen_put`) -/
  | evict (i : Bool) (seq : ℕ)
  /-- the message-free start at `i` changes its answer (an advertised budget changed) -/
  | flip (i : Bool)
  /-- the first frame on `i`'s channel is lost -/
  | lose (i : Bool)
  /-- the first frame on `i`'s channel is delivered; `room`: the receiver has room for `e`
  (`len(owned) < k`), `chain`: a PUSH without room starts a push chain (ttl > 0) -/
  | deliver (i : Bool) (room chain : Bool)
  /-- the push chain served at `i` ends, successfully or not, `room` as above -/
  | finish (i : Bool) (ok room : Bool)
  deriving DecidableEq, Repr

namespace St

def nd (s : St) : Bool → Node
  | false => s.a
  | true => s.b

def setNd (s : St) : Bool → Node → St
  | false, n => { s with a := n }
  | true, n => { s with b := n }

def chan (s : St) : Bool → List Frame
  | false => s.fromA
  | true => s.fromB

def setChan (s : St) : Bool → List Frame → St
  | false, l => { s with fromA := l }
  | true, l => { s with fromB := l }

/-- `i` sends a frame on its channel. -/
def send (s : St) (i : Bool) (f : Frame) : St := s.setChan i (s.chan i ++ [f])

end St

/-- `_accept_edge` (`bbcvc.py:2356-2397`), with `room` for `len(owned) < k`. -/
def accept (P : Params) (n : Node) (room : Bool) : Node × Bool :=
  let n' := { n with offered := false, takes := n.takes + 1, retake := some n.seqc }
  if n.X = some true then (n', true)
  else if n.X = none ∧ n.dflt = true then ({ n' with X := some true, gen := n.gen + 1 }, true)
  else if room then ({ n' with X := some true, gen := n.gen + 1 }, true)
  else (if P.takeOnFail then n' else n, false)

/-- `_release_edge` (`bbcvc.py:2403-2408`), with `_drop_late_ack`. -/
def release (n : Node) : Node := { n with gen := n.gen + 1, X := some false, late := [] }

def cachePut (n : Node) (seq : ℕ) (r : Rep) : Node :=
  { n with cache := (n.cache.filter fun x => x.1 ≠ seq) ++ [(seq, r)] }

/-- `j` answers request `seq` of the other end with `r`: the reply is cached and sent, a
positive one is recorded in the ghost list `acc`. -/
def reply (s : St) (j : Bool) (n : Node) (seq : ℕ) (r : Rep) : St :=
  let s' := (s.setNd j (cachePut n seq r)).send j (.rep seq r)
  if r.ok then { s' with acc := s'.acc ++ [(!j, seq)] } else s'

/-- `_repeated` (`bbcvc.py:2011-2028`) on unbounded sequence numbers: at or below the mark is a
repeat, otherwise the mark moves. -/
def repeated (n : Node) (seq : ℕ) : Node × Bool :=
  match n.mark with
  | some m => if seq ≤ m then (n, true) else ({ n with mark := some seq }, false)
  | none => ({ n with mark := some seq }, false)

/-- The answer to a repeat that missed the cache (`_on_handover`, `_on_push` with `_repeat_ok`):
the frozen code answers "do I hold `e`", R3 adds that the edge count is the carried one plus one. -/
def repOk (P : Params) (n : Node) (g : ℕ) : Bool :=
  decide (n.X = some true) && (!P.repeatByCount || decide (n.gen = g + 1))

/-- `_yields_to_inbound` at `j`: an own open request for `e`, and `j`'s key is the smaller one. -/
def yields (P : Params) (j : Bool) (n : Node) : Bool :=
  P.yieldRule && !n.pend.isEmpty && !j

/-- `j` receives request `seq` of the other end: `_on_handover` (`bbcvc.py:2313-2330`) and
`_on_push` (`bbcvc.py:2417-2455`). -/
def onReq (P : Params) (s : St) (j : Bool) (seq : ℕ) (push : Bool) (g : ℕ) (room chain : Bool) :
    St :=
  let n := s.nd j
  match n.cache.lookup seq with
  | some r => s.send j (.rep seq r)
  | none =>
    if !push then
      let (n1, rep) := repeated n seq
      if rep then reply s j n1 seq ⟨false, repOk P n1 g, false⟩
      else if g ≠ n1.gen then reply s j n1 seq ⟨false, false, false⟩
      else if yields P j n1 then reply s j n1 seq ⟨false, false, false⟩
      else
        let (n2, ok) := accept P n1 room
        reply s j n2 seq ⟨false, ok, false⟩
    else
      let busy : Bool := match n.job with
        | some (q, _) => q = seq
        | none => false
      let nk : Bool := match n.job with
        | some (_, b) => b
        | none => false
      let (n1, rep) := if busy then (n, false) else repeated n seq
      if rep then reply s j n1 seq ⟨true, repOk P n1 g, false⟩
      else if yields P j n1 || (!busy && g ≠ n1.gen) then reply s j n1 seq ⟨true, false, false⟩
      else
        let (n2, took) :=
          if busy && n1.X = some true && !(P.finalNack && nk) then (n1, true)
          else if !busy then accept P n1 room
          else if P.finalBusy && nk then (n1, false)
          else if (n1.X = none ∧ n1.dflt = true) ∨ room = true then accept P n1 room
          else (n1, false)
        if took then reply s j n2 seq ⟨true, true, false⟩
        else if P.quietBusy && busy then s
        else
          match n2.job with
          | some (q, _) =>
            let n3 := if q = seq then { n2 with job := some (q, true) } else n2
            reply s j n3 seq ⟨true, false, false⟩
          | none =>
            if chain then s.setNd j { n2 with job := some (seq, false) }
            else reply s j n2 seq ⟨true, false, false⟩

/-- `i` receives reply `r` to its request `seq`: `_on_ack`/`_resolve` (`bbcvc.py:2503-2507`,
`2565-2589`) for an open request, `_on_late_ack` (`bbcvc.py:2509-2563`) for a positive reply to a
request no longer open, and the confirmation of a late acknowledgement (`bbcvc.py:2074-2077`). -/
def onRep (P : Params) (s : St) (i : Bool) (seq : ℕ) (r : Rep) : St :=
  let s := if r.ok then { s with ackd := s.ackd ++ [(i, seq)] } else s
  let n := s.nd i
  let n' :=
    match n.pend.find? (·.seq = seq) with
    | some p =>
      let n1 := { n with pend := n.pend.filter (·.seq ≠ seq) }
      if r.ok then (if n1.takes = p.theta then release n1 else n1) else n1
    | none =>
      if !r.ok then n
      else if n.X = some false then n
      else if !n.offered then n
      else if P.floorCheck && (match n.retake with | some f => decide (seq ≤ f) | none => false)
        then n
      else release n
  let s := s.setNd i n'
  if r.ok && r.late then s.send i (.conf seq) else s

/-- `j` receives the confirmation of its late acknowledgement `seq`. -/
def onConf (s : St) (j : Bool) (seq : ℕ) : St :=
  let n := s.nd j
  s.setNd j { n with late := n.late.erase seq }

/-- `_finish_push_job` (`bbcvc.py:2474-2501`) at `j`. -/
def finishJob (P : Params) (s : St) (j : Bool) (ok room : Bool) : Option St :=
  let n := s.nd j
  match n.job with
  | none => none
  | some (seq, nacked) =>
    let n0 := { n with job := none }
    let (n1, t) := if ok && !(P.finalBusy && nacked) then accept P n0 room else (n0, false)
    let took := (t || decide (n1.X = some true)) && !(P.finalNack && nacked)
    if took && nacked && !P.finalBusy then
      let s' := reply s j { n1 with late := n1.late ++ [seq] } seq ⟨true, true, true⟩
      some s'
    else some (reply s j n1 seq ⟨true, took, false⟩)

/-- One event; `none` when it is not enabled. -/
def step (P : Params) (s : St) : Ev → Option St
  | .offer i push =>
    let n := s.nd i
    if (n.X = some true ∨ (n.X = none ∧ n.dflt = true)) ∧ n.job = none ∧ n.pend = [] then
      let q := n.seqc + 1
      let n' : Node := { n with seqc := q, offered := true, pend := n.pend ++ [⟨q, push, n.takes, n.gen⟩] }
      some ((s.setNd i n').send i (.req q push n.gen))
    else none
  | .retx i seq =>
    match (s.nd i).pend.find? (·.seq = seq) with
    | some p => some (s.send i (.req p.seq p.push p.gen))
    | none => none
  | .lretx i seq =>
    if seq ∈ (s.nd i).late then some (s.send i (.rep seq ⟨true, true, true⟩)) else none
  | .evict i seq =>
    let n := s.nd i
    some (s.setNd i { n with cache := n.cache.filter fun x => x.1 ≠ seq })
  | .flip i =>
    let n := s.nd i
    some (s.setNd i { n with dflt := !n.dflt })
  | .lose i =>
    match s.chan i with
    | [] => none
    | _ :: l => some (s.setChan i l)
  | .deliver i room chain =>
    match s.chan i with
    | [] => none
    | f :: l =>
      let s := s.setChan i l
      match f with
      | .req seq push g => some (onReq P s (!i) seq push g room chain)
      | .rep seq r => some (onRep P s (!i) seq r)
      | .conf seq => some (onConf s (!i) seq)
  | .finish i ok room => finishJob P s i ok room

/-- A run of a list of events, `none` if some event is not enabled. -/
def runEvs (P : Params) : St → List Ev → Option St
  | s, [] => some s
  | s, e :: es => (step P s e).bind fun s' => runEvs P s' es

/-- The start of Phase 4 for the edge: no transfer yet, `dflt` as given. -/
def startNode (d : Bool) : Node :=
  ⟨none, 0, 0, false, [], none, 0, none, [], none, [], d⟩

def start (da db : Bool) : St := ⟨startNode da, startNode db, [], [], [], []⟩

/-- Nothing is open and nothing is in flight: no frame on either channel, no open request, no
push chain, no open late acknowledgement (the part of "silent" that concerns this edge). -/
def quietB (s : St) : Bool :=
  s.fromA.isEmpty && s.fromB.isEmpty && s.a.pend.isEmpty && s.b.pend.isEmpty &&
    s.a.job.isNone && s.b.job.isNone && s.a.late.isEmpty && s.b.late.isEmpty

def Quiet (s : St) : Prop := quietB s = true

/-- The hypothesis of Theorem 3(b): every accepted transfer was acknowledged, read as "every
positive answer reached the sender of its request". -/
def AllAcked (s : St) : Prop := (s.acc.all fun x => s.ackd.contains x) = true

/-- Ownership of `e` at one end after re-derivation (`_recompute_owned`, both ends in the cover). -/
def owns (n : Node) : Bool := n.X = some true || (n.X = none && n.dflt)

/-- The two ends agree on the message-free start: it gives `e` to exactly one of them, as it does
on agreed budgets (`dflt_antisymm` in `ExecFullOwnership.lean`). -/
def Agreed (s : St) : Prop := (s.a.dflt != s.b.dflt) = true

/-- The end of a run that violates Theorem 3(b) with owners `oa` at `a` and `ob` at `b`, as one
Boolean. -/
def badB (oa ob : Bool) (s : St) : Bool :=
  quietB s && (s.acc.all fun x => s.ackd.contains x) && (s.a.dflt != s.b.dflt) &&
    owns s.a == oa && owns s.b == ob

theorem bad_of_any {oa ob : Bool} {o : Option St} (h : o.any (badB oa ob) = true) :
    ∃ s, o = some s ∧ Quiet s ∧ AllAcked s ∧ Agreed s ∧ owns s.a = oa ∧ owns s.b = ob := by
  cases o with
  | none => simp at h
  | some s =>
    simp only [Option.any_some, badB, Bool.and_eq_true, beq_iff_eq] at h
    exact ⟨s, rfl, h.1.1.1.1, h.1.1.1.2, h.1.1.2, h.1.2, h.2⟩

/-- The crossing of two HANDOVERs (text parameters). Both ends hold `e` by the message-free
start (their budgets disagree), both offer it, both accept, both acknowledgements arrive after
`θ` moved, so neither releases. Then the budgets agree. -/
def traceNoYield : List Ev :=
  [.offer false false, .offer true false, .deliver false false false,
    .deliver true false false, .deliver true false false, .deliver false false false,
    .flip true]

/-- **Theorem 3(b) fails for the mechanisms the text states.** Under the text's parameters (no
yield rule), there is a run of one flexible edge that ends quiet, with every accepted transfer
acknowledged, every frame delivered in order and the message-free start agreed, in which both ends
hold the edge: `ExplicitConsistent` fails and the edge has two owners.

Modelling choices: those of the module docstring; the run uses no loss at all.

Smallest repair of the text: state the yield rule of `_yields_to_inbound`. -/
theorem thm3b_fails_without_yield :
    ∃ s, runEvs textParams (start true true) traceNoYield = some s ∧ Quiet s ∧ AllAcked s ∧
      Agreed s ∧ owns s.a = true ∧ owns s.b = true :=
  bad_of_any (by decide)

/-- With the yield rule the crossing of two HANDOVERs is refused at `a`: the same events end with
one owner. -/
example : (runEvs codeParams (start true true) traceNoYield).any
    (fun s => owns s.a != owns s.b) = true := by
  decide

/-- A PUSH refused as busy and a HANDOVER that cross (found by bounded search, replayed on the
frozen handlers). `a` offers `e` by PUSH and retransmits it; `b` offers `e` by HANDOVER; the start
no longer gives `e` to `b`, which is full; `a`'s PUSH reaches `b`, which starts a push chain; the
copy of the PUSH is refused as busy; `b`'s HANDOVER is lost and retransmitted; `a` reads the busy
refusal and keeps `e`; `b`'s chain succeeds and `b` takes `e`, its answer now a late
acknowledgement; `b`'s HANDOVER reaches `a`, which has no open request any more and accepts; `b`
reads the acknowledgement after `θ` moved and keeps `e`; `a` reads the late acknowledgement after
its acceptance cancelled its offer, ignores it and confirms; `b` reads the confirmation. -/
def traceBusy : List Ev :=
  [.offer false true, .retx false 1, .offer true false, .flip true,
    .deliver false false true, .deliver false false false, .lose true, .retx true 1,
    .deliver true false false, .finish true true true, .deliver true false false,
    .deliver false false false, .deliver true false false, .deliver false false false]

/-- **Theorem 3(b) fails for the protocol as the code implements it.** With the yield rule, the
code's acceptance and the `θ` check on the late path, there is a run of one flexible edge that
ends quiet, with every accepted transfer acknowledged, every frame delivered in order and the
message-free start agreed, in which both ends hold the edge. The same run exists with the text's
`θ` (counting only successful takes).

Modelling choices: those of the module docstring. What the run needs from the rest of the
protocol is that the message-free start gives `e` to both ends while their advertised budgets
disagree, that it stops giving `e` to `b` before `a`'s PUSH arrives, that `b` is full at that
moment and that its chain frees a slot; the handler-level replay sets these by hand.

Added hypotheses: none. This refutes the statement; see `ExecFullCap.lean` for what does hold. -/
theorem thm3b_fails_with_yield :
    (∃ s, runEvs codeParams (start true true) traceBusy = some s ∧ Quiet s ∧ AllAcked s ∧
      Agreed s ∧ owns s.a = true ∧ owns s.b = true) ∧
    (∃ s, runEvs ⟨true, false, true, false, false, false, false⟩ (start true true) traceBusy = some s ∧ Quiet s ∧
      AllAcked s ∧ Agreed s ∧ owns s.a = true ∧ owns s.b = true) :=
  ⟨bad_of_any (by decide), bad_of_any (by decide)⟩

/-- HANDOVERs only, one at a time per end, and a reply evicted from the cache. `a` hands `e` to
`b` (`b` takes it, `a` releases); `b` hands it back, `a` takes it but its acknowledgement is lost;
`a` offers `e` again with edge count 2, which `b` (count 1) refuses as stale; `b`'s cache evicts
that refusal; `a`'s retransmission of the same request is then a repeat at `b`, answered from
`b`'s state (`ok = _explicit[e] is True`, `bbcvc.py:2322-2323`), that is positively; `b` reads the
cached acknowledgement of its own request and releases; the refusal is lost and `a` reads the
positive answer and releases too. -/
def traceRepeat : List Ev :=
  [.offer false false, .flip false, .deliver false false false, .offer true false,
    .deliver true false false, .retx true 1, .deliver true true false, .offer false false,
    .lose false, .retx false 2, .deliver false false false, .evict true 2,
    .deliver true false false, .deliver false false false, .deliver false false false,
    .lose true, .deliver true false false]

/-- **Theorem 3(b) fails even without push chains.** With HANDOVER as the only transfer, one open
request per end, the yield rule and the edge count, a reply evicted from the cache makes the
answer to a repeat differ from the answer to the request: a refused request is answered
positively from the receiver's state, and both ends release the edge. The run ends quiet, with
every positive answer delivered to its sender (the hypothesis of Theorem 3(b) read on answers)
and the start agreed, and the edge has no owner. This contradicts `lem:dup` as written as well: a
repeat "receives its reply ... from the highest sequence number executed for its sender", and
that reply is not the one the request received.

Modelling choices: those of the module docstring; the eviction stands for `σ = 4` later replies
of `b` to `a` while `a`'s copy is in flight (`_seen_put`, `bbcvc.py:2003-2009`). -/
theorem thm3b_fails_repeat :
    (∃ s, runEvs codeParams (start true true) traceRepeat = some s ∧ Quiet s ∧ AllAcked s ∧
      Agreed s ∧ owns s.a = false ∧ owns s.b = false) ∧
    (∃ s, runEvs ⟨true, false, true, false, false, false, false⟩ (start true true) traceRepeat = some s ∧ Quiet s ∧
      AllAcked s ∧ Agreed s ∧ owns s.a = false ∧ owns s.b = false) :=
  ⟨bad_of_any (by decide), bad_of_any (by decide)⟩

end SwarmInfer.CoverWeave.ExecFull

open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_fails_without_yield
open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_fails_with_yield
open SwarmInfer.CoverWeave.ExecFull in
#print axioms thm3b_fails_repeat
