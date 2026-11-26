# Machine-checked proofs of Section IV

This folder contains Lean 4 proofs of the guarantees in Section IV of the paper. Lean is a proof assistant: a
theorem is accepted only when its kernel has checked every step of the proof, so a compiled file leaves no gap
in its own argument. Mathlib supplies the graph theory, measure theory and analysis the proofs build on.

Three kinds of result are covered.

1. The graph cores of the guarantees. These are statements about the final configuration, such as the backbone
   being independent and dominating or a valid pair existing exactly when a Hall-type condition holds.
2. The running times stated in Theorem 1. Each algorithm is written as a function that counts its own steps
   under an explicit cost model.
3. Part of the protocol claims, on an execution model of Phases 1a and 1b. The model has synchronous slots and
   an arbitrary loss pattern.

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
| Lemma 3, duplicate requests | all copies of one request, in any order and number, change ownership at most once at the receiver. With the `θ` check of `OnAck` they change it at most once at the sender | `recvChanges_le_one`, `ackChanges_le_one` | `ExecRequests.lean` |
| Lemma 4, loss-free window, Phase 1a | from every reachable configuration, `n` loss-free slots decide every node, and the decided state is never left | `phase1a_window` | `ExecDecision.lean` |
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

The checks also confirmed one statement that an earlier reading had weakened. On a lossless channel Phase 1a
takes exactly `R+1` rounds, so "needs `R+1` rounds" in Proposition 2 is right as stated.

## What is not checked here

The paper proves no statement about the asynchronous scheduler, whose runs are only measured in Section V, so
there is nothing to check for it. The written proofs remain the only support for the following.

* The cited hardness results. Mathlib has no complexity classes, so NP-hardness itself is not formalized, only
  the correctness of the reductions.
* Theorem 3(b).
* Lemma 4 and Theorem 4 beyond Phase 1a. Phases 0 and 2 to 5, epochs and record expiry are not in the model.
* The running time of the reduction maps in a step-count model. Their output sizes are checked, and each map
  writes every node and edge once.

## Files

`Basic.lean` holds the shared definitions: cover, owner map, valid pair and weight. `Backbone*.lean` hold the
key-greedy backbone. `Exec*.lean` hold the execution model. The remaining files hold one statement or a small
group of statements each, as the table shows.

## Checking the proofs

Install Lean through [elan](https://github.com/leanprover/elan). The toolchain (`leanprover/lean4:v4.37.0-rc1`)
and the Mathlib commit are pinned by `lean-toolchain` and `lake-manifest.json`. Then run

    cd formal
    lake exe cache get   # downloads the prebuilt Mathlib for the pinned commit
    lake build

The build compiles all 23 files. It succeeds with no error, and the only messages are style hints of the
linter.
