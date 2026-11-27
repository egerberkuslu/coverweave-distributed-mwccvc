# Machine-checked proofs of Section IV

This folder contains Lean 4 proofs of the guarantees in Section IV of the paper. Lean is a proof assistant: a
theorem is accepted only when its kernel has checked every step of the proof, so a compiled file leaves no gap
in its own argument. Mathlib supplies the graph theory, measure theory and analysis the proofs build on.

Three kinds of result are covered.

1. The graph cores of the guarantees. These are statements about the final configuration, such as the backbone
   being independent and dominating or a valid pair existing exactly when a Hall-type condition holds.
2. The running times stated in Theorem 1. Each algorithm is written as a function that counts its own steps
   under an explicit cost model.
3. Part of the protocol claims, on execution models of Phases 1a and 1b, of the transfer layer and Phase 4,
   and of the epoch mechanism. The models have synchronous slots. Where a statement holds under loss, the loss
   pattern is arbitrary.

## How to read a result

A Lean proof certifies the Lean statement, not the English sentence of the paper. The value of this folder
therefore rests on the two saying the same thing. Every main theorem carries a docstring with the following
parts.

* The source: the statement in the paper and its label.
* `Modelling choices:` everything that was fixed to make the statement formal. Examples are "the graph is a
  finite simple graph" and "a frame arrives in the next slot or is lost". Where the paper is silent, the
  choice was read off the code, and the docstring gives the file and line.
* `Added hypotheses:` every hypothesis the paper does not state, with the reason the statement fails without
  it. Where possible the failure is itself proven as a counterexample.

After the main theorems each file runs `#print axioms`. Every result depends only on `propext`,
`Classical.choice` and `Quot.sound`, the standard axioms of Mathlib. No file uses `sorry`, `admit`,
`native_decide` or a new axiom.

## What is proven

| Statement in the paper | What is checked | Lean theorem | File |
|---|---|---|---|
| Theorem 1, unit weights | with `k` at least the maximum degree, valid pairs are exactly the connected vertex covers | `validPair_iff_connectedVertexCover_of_maxDegree_le_four` | `Ownership.lean` |
| Theorem 1, ownership for fixed `C` | an owner map exists iff the Hall condition holds, which is equivalent to the flow condition | `exists_ownerMap_iff_hall` | `Ownership.lean` |
| Theorem 1, set cover transfer | for a set-cover instance whose sets cover `U`, connected covers of the gadget read off set covers, and the cost transfers up to the additive term `ε(\|U\|+1)` | `readOff_isSetCover`, `gadgetCover_validPair`, `setCover_gadget_transfer` | `SetCoverGadget.lean` |
| Theorem 1, running times | a valid-pair checker on adjacency lists, correct and within `3(n+m)` steps | `checkValid_correct`, `checkValid_steps_le` | `CheckRuntime.lean` |
| Theorem 1, running times | the owner map by augmenting paths finds a map exactly when one exists, within `m(2m+3n)` steps on any graph and `8m²` on a connected graph, the case Definition 1 assumes | `ownerFlow_isSome_iff`, `ownerFlow_steps_le`, `ownerFlow_steps_le_sq` | `OwnerFlow.lean` |
| Lemma 1, backbone domination | the key-greedy set is independent, dominates every node with an edge and is maximal on a connected graph with at least two nodes. Counterexamples for one node and for an isolated node | `keyGreedy_isIndepSet`, `keyGreedy_dominates`, `keyGreedy_maximal_of_connected`, `lem_backbone_false_one_node`, `lem_backbone_false_isolated` | `BackboneDomination.lean` |
| Lemma 1, protocol part | in the Phase 1a model, a decided node has its key-greedy role under every loss pattern | `run_sound` | `ExecDecision.lean` |
| Lemma 2, cover connectivity | the induced cover is connected when the Phase 1b and Gap3 rules hold on the final configuration and `n` is at least 2 | `lem_conn_core`, `induce_connected_of_bridged` | `BackboneCover.lean` |
| Lemma 2, Phase 1b step | in the Phase 1b model, two backbone nodes at distance two are bridged by the connector rule under every loss pattern, and `n+1` loss-free slots complete the phase | `connector_sound`, `gap2Bridged_exec`, `allDone_of_lossFree` | `ExecConnector.lean` |
| Theorem 2, cover and connectivity | the cover contains the backbone and is a connected vertex cover under the rules of Phases 1b, 2 and Gap3 | `lem_cover_core` | `BackboneCover.lean` |
| Theorem 3(a), feasibility | equivalence of a valid pair, a valid pair with `C = V` and the Hall-type counting condition, and both certificates | `feasible_tfae`, `not_exists_validPair_of_sum_min_lt`, `not_exists_validPair_of_card_mul_lt` | `Ownership.lean` |
| Theorem 3(b), under the registered rules | for one flexible edge under the five rules of Amendment 17, which are the yield rule, the `θ` check on the late path, R2'', R3 and R4, every quiet configuration reachable from the start of Phase 4 has complementary or absent settled decisions. When the message-free start is agreed, the edge has exactly one owner. The same holds for every edge of the network | `thm3b_transfer_r2pp`, `net_explicit_consistent_r2pp`, `thm_cap_b_network_r2pp` | `ExecFullTransferR2p.lean` |
| Lemma 3, duplicate requests | all copies of one request, in any order and number, change ownership at most once at the receiver. With the `θ` check of `OnAck` they change it at most once at the sender | `recvChanges_le_one`, `ackChanges_le_one` | `ExecRequests.lean` |
| Lemma 4, loss-free window, Phase 1a | from every reachable configuration, `n` loss-free slots decide every node, and the decided state is never left | `phase1a_window` | `ExecDecision.lean` |
| Lemma 4, offers of an end in Phase 4 | if every slot after `T₀` at which an end offers lies in a finite set `F`, and an end that has had no open request for `π + 1` slots never offers again, then the end follows `OfferSeq π` from `T₀` with at most `\|F\| + 1` anchors. Under the controller the set is the ladder's slots `F` and the probe slots `P` of the node's chains, with at most `\|F\| + \|P\| + 1` anchors, and a leaf end is never probed | `offerSeq_of_idle`, `ctl_offerSeq`, `ctl_offerSeq_single`, `ex_ctl_offerSeq` | `ExecFullOffers.lean` |
| Lemma 4, idleness is a necessary hypothesis | if the only request of an end before slot `c` is one request, the end is idle on `[c, c + π]` and it offers again at a slot `L ≥ c + π`, no list of anchors makes it follow `OfferSeq π` from a slot at most `c`. A leaf that pushes at slots 0 and 6 meets the budget with `F = {0, 6}` and follows `OfferSeq 1` for no list of anchors | `not_offerSeq_of_gap`, `ex_not_offerSeq` | `ExecFullPhase4.lean` |
| Lemma 4, Phase 4 under the controller | under `Phase4Hyps` every edge is quiet at slot `phase4Bound T₀ Δ Tr D π n` and its two settled decisions are consistent. The hypotheses are that Phase 4 starts with no chain and every edge in the invariant of the transfer layer, every node has at most `Δ` edge ends, every retransmission timer fires in every `Tr` slots, every hop limit is at most `D`, and from the slot `T₀` at which the signatures have settled each end offers at no more than `n` slots and never again once idle for `π + 1` slots. The chain discipline and its bound are proven for the controller. One edge between two leaves meets the hypotheses | `ctl_phase4_window`, `ex_phase4Hyps` | `ExecFullPhase4.lean` |
| Lemma 4, epoch part | for a loss-free window from slot `T`, with the freeze gate hypotheses `hG4` and `hM` read off the code, a node in an epoch entered at a slot of at least `T` freezes with its complete view and never counts a difference. Once every node is in such an epoch, no epoch rises above the largest epoch of that slot, so no restart storm follows. If every node is DONE and frozen in one such epoch, every node is DONE at every later slot | `fresh_complete`, `fresh_no_storm`, `fresh_done_forever` | `Epochs.lean` |
| Epochs, when DONE survives | from a configuration in which every node is DONE in one epoch with its view equal to its frozen view, every node stays DONE for ever if and only if no handshake adds a link later. With fair handshakes this holds if and only if every frozen view already holds all radio neighbours. One restart at `v` undoes DONE at every node `u` within `1 + dist v u` slots | `done_forever_iff`, `done_forever_iff_complete`, `restart_spreads` | `Epochs.lean` |
| Epochs, the restart storm | two nodes on one edge with a fixed radio graph and every handshake completing at each end in every 5 slots. The epoch rises every 5 slots for ever, each node is DONE again and again, and from slot 10 on the two are never DONE in the same slot. So the claim that a fixed radio graph, bounded handshakes and every node DONE at some slot give a network that is eventually DONE for good is false. The storm breaks exactly the gate hypothesis `hG4` | `storm_not_converged`, `naive_liveness_false`, `storm_breaks_G4` | `Epochs.lean` |
| Lemma 4, silence is never left | in a synchronous message-passing model, a silent configuration is a fixed point of every slot under every loss pattern. This needs a DONE node with a closed barrier to send no frame, which the code satisfies | `sslot_of_silent`, `silent_never_left`, `beaconing_never_silent` | `ExecSilence.lean` |
| Theorem 4, termination | the absorption argument `Pr[T_sil > jW] ≤ (1-ε_W)^j` and silence with probability one, for an abstract process and for the Phase 1a model | `silent_tail_bound`, `silent_ae`, `phase1a_terminates` | `Termination.lean`, `ExecTermination.lean` |
| Theorem 5, cost identity | `tx = h + 4m + 2J + 2Z + Λ` and the receive identity. A counterexample shows that bounds counting distinct requests do not bound `J`, and the bound with a repeat factor holds | `cost_identity_tx`, `cost_identity_rx`, `table_bound_does_not_bound_J`, `tx_le_of_repeats` | `CostIdentity.lean` |
| Proposition 1, lower bound | `\|C\| ≥ ⌈m/k⌉` | `lower_bound` | `LowerBound.lean` |
| Proposition 2, decision chain | on a lossless channel a node decides in round `d(v)+1`, Phase 1a takes exactly `R+1` rounds and computes the key-greedy set, and `R ≤ L ≤ n − 1` with attainment on a path | `prop_mischain_exec`, `depth_le_of_keyPath_bound`, `depth_lt_card`, `depth_pathGraph` | `ExecDecision.lean`, `BackboneChain.lean` |
| Proposition 3, first bound | `\|C\| ≤ k·OPT + 1` | `card_le_mul_opt_add_one` | `LowerBound.lean` |
| Proposition 3, unit disk bound | a node of a unit disk graph has at most five pairwise nonadjacent neighbours, and `\|C\| ≤ 6·OPT` | `card_le_five_of_isUnitDiskGraph`, `card_le_six_mul_opt_of_isUnitDiskGraph` | `UnitDisk.lean`, `UnitDiskBound.lean` |
| Corollary 1, witness scope | both containments and both instances, the instances checked by computation | `witness_scope` | `Witness.lean` |
| Corollary 1, smallest captured instance | every connected instance the witness captures has `k ≥ 2`, `n ≥ 2k+3` and `m ≥ 2k²+2k+2`, so no connected instance with `n ≤ 6` is captured and the instance of Figure 7 is smallest in `n` and `m`. Connectivity is needed, as a captured disconnected instance with `n = 5` shows | `witnessCaptures_size_of_connected`, `no_witnessCaptures_of_card_le_six`, `witnessCaptures_G5` | `Exhaustive.lean` |
| Theorem 1, size of the reductions | the set-cover gadget has `\|I\|+\|U\|+1` nodes and `\|I\|+Σ\|S_i\|` edges, so its size is at most three times the input size plus three, and the unit-weight map keeps the graph | `gadget_size`, `unitImage_size` | `ReductionSize.lean` |

The first claim of Theorem 1, NP-completeness of the decision version, is machine-checked in Isabelle/HOL down
to the Cook-Levin theorem; see [isabelle/](isabelle/README.md).

## What the checks found

The Lean pass found defects in the submitted text and in the code. Each one is repaired in the revised
manuscript or in the code, and the response letters say where.

* **Lemma 1 was false on a one-node graph and on a graph with an isolated node.** The repaired lemma is stated
  for connected graphs with at least two nodes. A scope sentence in Section IV-B splits a disconnected
  discovered graph into its components.
* **The cost bounds of Theorem 5 fell below the measurements.** The identity counts every transmission of a
  request, while the bounds of Table 3 counted distinct requests, so a JOIN sent again after a lost reply
  raised `J` without changing the bound. The proof now names the `J₀ ≤ 8m` distinct JOIN requests and states
  `J ≤ a·J₀` for at most `a` sends per request.
* **The set cover transfer of Theorem 1 was overstated.** The transfer holds up to an additive `ρ·ε·(|U|+1)`,
  and the inapproximability carries over as some ratio `c'·ln n`, not as the same `c·ln |U|`. The gadget also
  needs every element to lie in some set.
* **The late acknowledgement path of the code lacked the `θ` check of `OnAck`.** `code_late_ack_twice` in
  `ExecRequests.lean` gives the sequence. An edge is offered, its acknowledgement releases it, the edge comes
  back and is offered again, and then a delayed copy of the first acknowledgement released it a second time.
  * The code now applies the check on that path too, through `_retake_seq` in `ccvc/bb/bbcvc.py`.
  * The regression test `test_a_stale_copy_of_an_old_ack_does_not_release_a_reacquired_edge` in
    `ccvc/bb/test_bbcvc.py` fails on the earlier code and passes on the corrected one.
  * No emulated or simulated run behind the reported results that ended solved has an ownership violation or
    a doubly claimed edge. The 23 false successes reported in Section V-D all have a cover that is not
    connected, and ownership violations appear only in runs cut off at their slot limit.
  * The line numbers in the docstring of `ExecRequests.lean` refer to the code before the fix.
  * The fix stays in the repaired code below as the second of the five rules of Theorem 3(b).
* **Theorem 3(b) was false for the submitted transfer handlers.** The Lean model of the transfer layer of one
  flexible edge gives three runs that end quiet, with every frame delivered in order and every accepted
  transfer acknowledged, in which the edge has two owners or none. They are `thm3b_fails_without_yield`,
  `thm3b_fails_with_yield` and `thm3b_fails_repeat` in `ExecFullTransfer.lean`. A bounded search of the same
  model found a fourth run through the room test of `_accept_edge`.
  * Five rules repair it. They are registered in Amendment 17 of `contract/R1_PREREG.md` before any run of
    the repaired code. The yield rule makes an end with its own open request for the edge refuse an incoming
    one when its key is smaller. The `θ` check on the late path is the fix above. R2'' answers a PUSH refused
    as busy with NACK for ever. R3 answers a copy of a request as the request was answered. R4 counts a take
    only when the acceptance succeeds. The first form of the busy rule, R2', still admits two owners, as
    `thm3b_fails_r2p` shows.
  * The repaired code is `ccvc/bb/bbcvc.py` at fingerprint 026c2dc5f381. The regression tests in
    `ccvc/bb/test_r2r3.py` drive the handlers through the counterexample runs and check one owner per edge.
  * The repair was tested on the existing held-out sets, paired with the frozen rows, as Amendments 17 to 19
    register. Under Amendment 19 the decision reads safety and validity on the lossless block S1 and the
    measured loss block M6emp. There no solved run has an ownership violation or a double claim, which is 0
    of 13,976 runs with a one-sided 95 percent upper bound of 0.021 percent, and no block loses validity. By
    that rule the repair is accepted.
  * The one violation in the wireless block M7, run `m7_W_mst_n50_m150_s404`, is a collector defect and not an
    ownership defect. The collector called the run converged from done stamps of different epochs while the
    network was in the middle of a restart, and no station owned any edge at its end. Amendment 18 fixes the
    collector and the harness in `ccvc/bb/mnwifi/`. With the fixed collector the row reads truncated and the
    count over all 14,063 runs is 0. That reading is not confirmatory, because its outcome was known when the
    amendment was written.
  * Block M6 beyond its first 20 jobs and the confirmatory wireless block M7b were stopped for time under
    Amendment 19. The lossy evidence is therefore one measured loss condition, and the wireless evidence has
    no run under the repaired harness.
* **The proof of Lemma 4 missed a restart in its count of view changes.** The proof says that in a loss-free
  window each directed link changes a view at most twice. A restart clears every verified link of a node, and
  one restart undoes DONE at every node within its distance, as `restart_spreads` shows. With a fixed radio
  graph and fair handshakes the restarts can repeat for ever, as `naive_liveness_false` shows. This is the
  liveness limitation that Amendment 18 states for both versions of the code. The count holds for an epoch
  entered inside the window when the freeze gate waits for pending links, and such an epoch never restarts,
  as `fresh_complete` and `fresh_no_storm` show.

The checks also confirmed one statement that an earlier reading had weakened. On a lossless channel Phase 1a
takes exactly `R+1` rounds, so "needs `R+1` rounds" in Proposition 2 is right as stated.

## What is not checked here

The paper proves no statement about the asynchronous scheduler, whose runs are only measured in Section V, so
there is nothing to check for it. The written proofs remain the only support for the following.

* The cited hardness results beyond NP-completeness: planar and maximum-degree-4 hardness, APX and the set-cover
  bound. NP-completeness itself is checked in Isabelle/HOL, see above.
* Lemma 4 and Theorem 4 for the whole protocol. `coverweave_correct` in `MainTheorem.lean` composes the proven
  layers into one statement about a run of the whole protocol, and every part that is not proven is a named
  field of `OpenHyps`. The field `window`, which is Lemma 4 for the whole protocol, is open. It is proven for
  Phase 1a, for Phase 1b, for the transfer layer of one edge and for Phase 4 under the controller, and these
  hypotheses remain.
  * The signatures settle at some slot `T₀`. Phase 4 is proven from that slot on, and the slot itself is not
    derived.
  * The offer budget per end. `offers_le` bounds the ladder's offers per signature, but the ladder of the
    controller model is a fixed schedule without a tried set, so the budget `n` of `Phase4Hyps` is not linked
    to that count.
  * Final idleness. An end that has been idle for `π + 1` slots never offers again. The rules of the
    controller do not give it, and `ex_not_offerSeq` shows that the conclusion fails without it.
  * The gate hypothesis `hG4` of the epoch part, with `hM`. Both are read off `bootstrap.py` and `sched.py`
    and are not derived from a model of the handshakes.
  * Phases 1 to 3 and 5 inside the window. They enter only through their own models or through rules at
    silence, and no theorem joins them with Phase 4 into one window of the whole protocol. The refinement
    fields of `OpenHyps`, which say that the phases of the code are runs of these models, are not checked.
  * Record expiry, which is not in any model.
* The running time of the reduction maps in a step-count model. Their output sizes are checked, and each map
  writes every node and edge once.

## Files

`Basic.lean` holds the shared definitions: cover, owner map, valid pair and weight. `Backbone*.lean` hold the
key-greedy backbone. `Exec*.lean` hold the execution models, and among them `ExecFull*.lean` hold the transfer
layer, the push chains, the Phase 4 controller and Phase 5. `Epochs.lean` holds the epoch mechanism, and
`MainTheorem.lean` composes the layers. The remaining files hold one statement or a small group of statements
each, as the table shows.

## Checking the proofs

Install Lean through [elan](https://github.com/leanprover/elan). The toolchain (`leanprover/lean4:v4.37.0-rc1`)
and the Mathlib commit are pinned by `lean-toolchain` and `lake-manifest.json`. Then run

    cd formal
    lake exe cache get   # downloads the prebuilt Mathlib for the pinned commit
    lake build

The build compiles all 45 files. It succeeds with no error, and the only messages are style hints of the
linter.
