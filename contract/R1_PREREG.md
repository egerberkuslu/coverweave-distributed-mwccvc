# CoverWeave R1 pre-registration (Access-2026-53199)

Written 2026-11-18, before any held-out instance is generated and before any
revision run. It answers Reviewer 2 points (iii)(c), (iv), (x), (xi), (xii),
(xiii), (xiv). Nothing below may change after the frozen tag exists, except
through a dated amendment appended at the end of this file.

## 1. Frozen version

- One code version, identified by a content hash (sha256 over the bytes of the
  modules on the measurement import path) and by the annotated git tag
  `coverweave-r1-frozen` in the release repository.
- Every number in the revised manuscript comes from runs of that tag. Rows
  measured with earlier versions are not reported.
- No measurement code changes after the tag. A defect found on held-out data is
  reported as found. A repair is a new version, evaluated only on the sealed
  reserve seeds (section 3), and reported next to the unrepaired result.

## 2. Development set (used during development, reported as such)

The 360 benchmark files of the published dataset, `k = 6`. Re-run at the tag:
every feasible instance with all 25 configurations, and one witness
configuration on every infeasible instance. The paired loss experiment, the
worked example and the 27 Mininet-WiFi runs are re-run at the tag as well.

## 3. Held-out sets (never seen by any development run)

Instances are generated only after this file is committed. Generator and
per-file sha256 go into `manifest.json` before the first run.

| Set | Family | Cells | Instance seeds | Instances |
|---|---|---|---|---|
| H1 | connected G(n,m), spanning tree plus uniform extra edges, weights U[20,120) | n in {10,15,20,25,50,100,150,200} x m/n in {2,4} | 101-110 | 160 |
| H1-large | same | n in {500,1000} x m/n in {2,4} | 101-102 | 8 |
| H2a | connected unit disk graph | n in {25,50,100,200} x average degree in {4,8} | 201-210 | 80 |
| H2b | Barabasi-Albert, attachment 2 and 4, weights U[20,120) | n in {25,50,100,200} | 301-310 | 80 |
| W | connected unit disk graph with coordinates, average degree about 6 | n in {30,50} | 401-410 | 20 |
| Reserve | all families, generated but not run | as above | 901-910 | sealed |

Rules.
- Cells with m = nk are excluded from quality comparisons because the cover is
  forced to C = V there. They are still run and reported for validity.
- Instances proved infeasible by the counting bound, the degree-gap witness or
  the flow check are not scored for quality. Their count is reported.
- The H1 generator is checked against the 360 published files (degree
  distribution per cell, weight range) before seeds are drawn. If it cannot be
  matched, H1 is described as a G(n,m) family and not as the published
  generator.

## 4. Arms and references

- Primary arm, fixed from the development set: the simulated-annealing backbone
  arm under the asynchronous scheduler (code name `anneal`, paper name
  TemperFlux), the arm with the lowest mean ratio to the proven optimum on the
  107 development instances with n <= 50.
- Other arms: all 25 configurations of the development sweep, with duplicates
  that produce identical outputs reported once.
- References: proven optimum (n <= 50), the trivial cover C = V with weight
  W(V), the centralized greedy heuristics, and an LP-relaxation lower bound
  where the optimum is unavailable. The "ratio to the best arm" is not used.

## 5. Experiment blocks

| Block | Content | Runs |
|---|---|---|
| M2 | frozen re-run of the development set | 5325 + 147 |
| M3 | H1 and H1-large, 25 configurations | 4200 |
| M4 | H2a and H2b, 25 configurations, exact optimum for n <= 50 | 4000 |
| M5 | capacity sensitivity: tightness m/(nk) in {0.67, 0.5, 0.33, 0.25}, that is k in {3,4,6,8} at m/n = 2 and k in {6,8,12,16} at m/n = 4, on H1 and H2a at n in {15,25,50,100}, 10 configurations | 6400 |
| M6 | loss: 60 held-out instances (H1 and H2a, n in {25,50,100}, 10 per cell) x 9 conditions x 5 configurations x 3 channel seeds. Conditions: independent loss 0, 5, 10, 20, 30 percent; Gilbert-Elliott with stationary loss 5, 10, 20 percent and mean burst length 4 frames; per-link loss resampled from the measured Mininet-WiFi delivery ratios | 8100 |
| M7 | Mininet-WiFi: the 27 development runs at the tag, and set W with 3 arms | 87 |
| M8 | parameter sensitivity, one factor at a time around the defaults, on 40 H1 instances (n in {25,50}), primary arm and the spanning-tree arm: gap patience, escalation patience, quiescence window, stale timeout, cooling factor, initial and final temperature, penalty weight, and a second weight distribution | fixed in an amendment once the parameter list is read from the code, before any M8 run |

Budgets. Every run uses the time limit of the development sweep for its size.
A run that hits the limit counts as a failure and is never re-run with a larger
limit in the main tables.

Channel seeds are separate from instance seeds. Results are averaged per
instance first, and tests are made across instances.

## 6. Endpoints

Validity under the independent validator, false successes (a run reported as
solved that the validator rejects), deadlocks or truncations, ratio to the
optimum, to W(V) and to the centralized heuristics, transmissions, deliveries,
transmitted bytes, slots, largest payload.

## 7. Hypotheses and tests

- H-a. No false success on any held-out run. Reported with a one-sided 95%
  Clopper-Pearson upper bound.
- H-b. On H1, H2a and H2b the primary arm has a lower ratio to the reference
  than the best distributed baseline of the development set. One-sided Wilcoxon
  signed-rank test over instances with Pratt handling of zeros, per size band,
  Holm correction over bands, with the matched-pairs rank-biserial effect size
  and a bootstrap 95% interval (10 000 resamples) of the mean ratio.
- H-c. Validity of every loss-hardened arm stays at 100% in each M6 condition.
  Reported per condition with Clopper-Pearson intervals. No correction is
  applied, since any failure is reported.
- H-d. Quality differences between arms shrink as tightness m/(nk) falls.
  Reported descriptively with intervals. No significance claim.

A hypothesis that fails is reported as failed in the manuscript and in the
response letter.

## 8. What is stated as a limitation and not run

No physical testbed. Energy values are model estimates. No approximation ratio
is proved. Proven optima stop at n = 50. Mininet-WiFi runs use one host and one
emulated network at a time.

## Amendments

### Amendment 1, 2026-11-18, before the frozen tag and before any held-out instance exists

Source. A proof audit of Section IV (not a held-out run) found, by deterministic
fault injection on the worked example of the manuscript (n = 10, m = 15, k = 2,
a development instance), that the submitted protocol does not satisfy
Theorem 4 and the ownership clause of Theorem 3 under loss:
- three lost copies of one escalation JOIN stall a run forever,
- one lost DONE HELLO and its single answer leave beaconing that never stops,
- three lost HANDOVER_ACK copies end an all-DONE run with a doubly owned edge,
  and the sweep validator does not see double ownership.

Repairs, fixed here before any evaluation and included in the frozen tag.
- F1. Persistent requests: a JOIN is re-armed while its trigger holds, and
  HANDOVER and PUSH are retransmitted with capped backoff until answered,
  given up only if the peer is no longer verified or the epoch changed.
- F2. DONE barrier: a one-bit open-barrier flag in HELLO, and a DONE node
  answers every open-flag beacon of a DONE neighbour at most once per stale
  window.
- F3. A one-byte epoch in JOIN and edge messages, and frames of another epoch
  are dropped.
- F4. Decision rules read the frozen neighbour view of the epoch, and a frozen
  neighbour whose record is stale means wait.
- F5. The duplicate-reply cache is bounded per peer.
- F6. Validation: a doubly claimed edge is a violation in every validator path.

Regression tests that must pass at the tag: the three fault scenarios above
must respectively converge, end with no double claim, and reach silence.

Reporting rule. The response letter and the manuscript state that these
defects were found by the audit and repaired before the freeze. The three
fault scenarios are reported for the submitted version and for the frozen
version. If a repair cannot be made to pass its regression test, the weaker
statement is used instead: termination is claimed for the lossless channel
only, and the stalling executions are described.

Instrumentation added before the tag (no effect on protocol behaviour):
realized MIS decision depth per run, protocol-state bytes per node at run end,
restart count per run, transmissions after the convergence verdict, exact
flow feasibility for every instance size, per-run parameter overrides for
block M8.

Added held-out block.
- M9. Twenty instances that are infeasible by the flow check while the
  counting bound and the degree-gap witness are silent, built by the generator
  with seeds 501-520 and confirmed by the flow check before any protocol run.
  Endpoint: verdict and cost of every arm on them.

M8 parameter list (replaces the placeholder in section 5). One factor at a
time around the defaults, on 40 held-out instances (H1 and H2a, n in {50,100},
m/n or average degree in {2,4} and {4,8}, seeds 101-105 and 201-205), loss 0
and 5 percent. Core factors on the MIS-connector arm (synchronous) and the
spanning-tree arm (both schedulers): gap patience {1,4,8}, escalation patience
{1,4,8}, quiescence periods {2,5,8}, stale periods {2,5}, repair rounds {2,8},
acknowledgement attempts {5,8}. Annealing factors on the two annealing
configurations: cooling factor {0.8,0.95}, cooling interval {1,4}, initial
temperature scale {0.5,2}, final temperature fraction {half, double}, penalty
scale {1.5,4}. Weight distributions on 30 H1 instances (n in {25,50,100},
m/n in {2,4}, seeds 101-105): unit, degree-correlated, lognormal with sigma 1,
inverse residual energy with energy uniform on [0.1,1].

### Amendment 2, 2026-11-18, before any held-out instance is generated

Source. A generator feasibility check that used no pre-registered seed. A
connected unit disk graph with average degree 4 almost never occurs for
uniform points in a square at n >= 100 (0 of 1000 draws at n = 200).

- H2a uses average degree in {6, 8} instead of {4, 8}. Each instance has
  exactly m = n * degree / 2 edges and disconnected placements are redrawn.
  The reserve set changes in the same way.
- Vertex weights of H2a, H2b and W are U[20,120), as in H1.
- The H1 family is the published construction, a path over all nodes plus
  uniform extra edges. It matched the 360 published files in degree
  distribution and weight range, so H1 is described as that construction.
- M5 uses the H1 cells with m/n in {2, 4} and the H2a cells with average
  degree 8, which is m/n = 4.
- M8 uses the H2a cells with average degree in {6, 8}.
- Set W is run through the emulator's own layout planner, as the development
  runs were, and the generated coordinates are kept only as a record.

### Amendment 3, 2026-11-18, before the frozen tag

The station logs of the development Mininet-WiFi runs no longer exist, so the
per-link delivery ratios for the empirical loss condition of M6 cannot be
derived from them. The empirical condition of M6 uses the delivery ratios
measured in the M7 re-runs at the frozen tag, whose logs are kept. M6 runs its
other eight conditions first. If M7 is not run, the empirical condition is
dropped and the manuscript says so.

### Amendment 4, 2026-11-18, before the frozen tag and before any held-out instance exists

Source. The repair work of Amendment 1 on development instances only (the
worked example, n15_m90_s1, n50_m300_s2 and small loss runs on development
graphs). No held-out instance exists yet.

Decisions.
- F2 is kept exactly as registered. A cheaper variant that raises the flag
  only for a silent neighbour was measured and not adopted. It is reported as
  such.
- Verdict clause. A node with an open request or a running push chain is not
  done. Without it, asynchronous runs were declared finished while chains were
  still running.
- F7. A node answers a request from a peer it hears but has not verified with
  a refusal, so that a request is always answered when gates are one-way on
  the emulated backend.
- F8. The spanning-tree arm stalled in its own backbone phase in 1 of 12 lossy
  development runs, in the submitted and in the repaired code. One bounded
  repair attempt is made before the tag, with the stalling run as its
  regression test. If it needs a redesign, the arm is frozen as it is and the
  stall rate is reported.
- The token-based depth-first arm is a comparison arm from the literature and
  is not loss-hardened. Its runs under loss are reported as they end.

Known and reported, not repaired. A late acknowledgement of a push chain that
outlasted its sender's timeout is sent once. If it is lost, both ends own the
edge. The ownership theorem therefore keeps the assumption that every accepted
transfer was acknowledged, and the validator counts every doubly owned edge.

Two validity readings, both reported for every run.
- Validity on the final discovered graph, which is the graph the guarantees
  refer to. A false success is a run reported as solved that is invalid on
  this graph.
- Validity on the planned graph. Planned links that are missing from the
  discovered graph, and discovered links that were not planned, are counted
  per run, together with the transmissions sent after the verdict and the
  number of restarts.
Hypothesis H-a and H-c are evaluated on the first reading. The second reading
is reported next to it in every table that reports validity under loss.

### Amendment 5, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Source. Smoke runs on four development instances (the worked example,
n10_m20_s1, n10_m40_s1, n15_m30_s1). Under Gilbert-Elliott loss with stationary
rate 10 percent and mean burst 4 frames, 67 of 72 runs of the repaired code and
66 of 72 runs of the submitted code hit the time limit. The cause is the
soft-state timeout. A neighbour record expires after 3 missed HELLOs, a burst
lasts 4 frames on average, so records keep expiring and the protocol restarts
about every 1.8 s. No run ended with an invalid cover.

Repair. No code change. The stale window is a parameter, and a bursty channel
needs a stale window longer than its bursts. A bursty-channel profile is
calibrated on development instances only, by the rule fixed here before any
calibration run.
- Calibration set. The four instances above plus n25_m50_s1, n25_m100_s1,
  n50_m100_s1 and n50_m200_s1, three arms (MIS-connector, spanning tree,
  annealing), both schedulers, channel seeds 1 to 3, loss ge:0.10:4, the time
  limit of the development sweep.
- Candidates. Stale periods in {6, 12, 24, 48}, with the stabilisation window
  kept equal to the stale window as in the default.
- Rule. The profile is the smallest candidate for which at least 95 percent of
  the calibration runs end within the time limit with a cover that is valid on
  the discovered graph. If no candidate reaches 95 percent, the candidate with
  the highest share is taken and the shortfall is reported.
- The profile is then fixed. It is never adjusted on held-out data.

Use in the blocks. M6 runs every Gilbert-Elliott condition twice, with the
default stale window and with the bursty-channel profile, and reports both.
Independent-loss and lossless conditions use the default. M8 keeps its stale
window factor. The cost of the profile, slower detection of a neighbour that
has really gone, is reported from the lossless runs of the same instances with
the profile.

### Amendment 6, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Source. The same development smoke runs as Amendment 5. No calibration run has
been made.

The restart loop under bursty loss is a design defect and is repaired in the
protocol, not by a hand-chosen parameter. The protocol treated a neighbour
that was silent for three HELLO periods as a neighbour that had left, and
restarted the whole network.

- F9, adaptive stale window. Every node keeps one stale window per neighbour,
  starting at the default of 3 periods. When a neighbour whose record expired
  is heard again, the expiry was a false suspicion, and the stale window of
  that neighbour doubles, up to a cap of 48 periods. The value is kept across
  epoch restarts. The restart gate for a missing neighbour waits for that
  neighbour's stale window. A neighbour that never returns is still removed
  and still triggers a restart.
- Required properties, each with a test. Lossless runs and runs without any
  false suspicion are identical to the runs without F9. A run under
  Gilbert-Elliott loss that restarted until the time limit now ends. A node
  that is really removed is still detected, within the cap.

Acceptance on the calibration set of Amendment 5 (development instances only,
loss ge:0.10:4, the same three arms, schedulers and channel seeds). F9 is
accepted if at least 95 percent of the calibration runs end within the time
limit with a cover that is valid on the discovered graph. The fixed stale
windows of Amendment 5 (6, 12, 24, 48) are run on the same set as the
comparison baseline, together with the default.

Use in the blocks. If F9 is accepted it is part of the frozen protocol and is
on in every block, and M6 additionally reports the Gilbert-Elliott conditions
with F9 switched off, as the ablation. If F9 is not accepted, the profile rule
of Amendment 5 applies and the failure of F9 is reported.

### Amendment 7, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Principle, set by the authors. A weakness found during the revision is
repaired in the protocol where a repair exists, and the manuscript and the
response letter state the weakness, its cause and the repair. A weakness is
only reported without repair when no sound repair exists, and the reason is
given. This amendment replaces the "known and reported, not repaired" item of
Amendment 4 and adds three more repairs. All sources are development
instances and the proof audit.

- F10, late acknowledgement. The acknowledgement of a push chain that outlasted
  its sender's timeout is sent as a request that is repeated until it is
  answered. Regression test: the late acknowledgement is lost three times and
  the run ends with no doubly owned edge.
- F11, deepening ownership repair. When the bounded repair rounds are used up
  at an overloaded node, the push depth is raised step by step, up to the
  number of nodes, before the node reports unresolved. Acceptance on the three
  feasible development instances with m = nk on which 25 runs ended
  unresolved (n200_m1200_s3, s6 and s10): every arm ends valid on a lossless
  channel. The added message cost is reported. No other development instance
  may lose validity.
- F12, in-network infeasibility certificate. In the arms that build a rooted
  tree, the two sums of the degree-gap witness and of the counting bound are
  aggregated over the tree and the root announces the verdict. Acceptance: on
  infeasible development instances the nodes announce infeasibility
  themselves, the verdict equals the run-level check, and the message cost is
  measured. Arms without a rooted tree keep the run-level check, and the
  manuscript says which is which.
- F13, pending neighbour. A neighbour that is heard but not yet verified keeps
  a node from finishing until it is verified or has been silent for its stale
  window. Acceptance: on the development loss runs that ended with planned
  links missing from the discovered graph or with transmissions after the
  verdict, both counts fall, and lossless runs are unchanged.

Rules for all repairs F7 to F13. Each has a regression test that fails on the
code before the repair. Lossless results may change only in message and slot
counts, never in validity, and every change is reported. A repair that cannot
pass its test without a redesign is dropped, the code for it is reverted, and
the weakness is reported with the reason. The calibration of Amendments 5 and
6 is run once, after all repairs are in and before the tag.

Not repaired, with reasons. The token-based depth-first arm is a comparison
arm from the literature and is reported as it ends under loss. A pruning step
for the MIS-connector arm is not added, because removing a cover node keeps
the cover connected only if a property of the whole cover holds, which a node
cannot check from one-hop information. No approximation ratio is claimed and
no physical testbed is used.

### Amendment 8, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Source. The repair work of Amendment 7 on development instances.

Outcomes of Amendment 7.
- F10 is in. The regression test passes.
- F13 is in. On the 90 development loss runs, planned links missing from the
  discovered graph fell from 17 to 0.
- F11 is in with one change. The push depth is doubled at each step, not
  raised by one, because raising by one cost 6.6 to 27 times more frames on
  infeasible runs. Of the 25 unresolved development runs, 23 now end valid.
  The 2 that remain are runs of the spanning-tree arm whose cover lacks one
  node that no overloaded node can invite from where it is.
- F12 was dropped and its code was not installed. The tree-aggregation phase
  never completed on the infeasible development runs.

Two further bounded attempts, each reverted if it does not pass.
- F11b, invitation at a distance. An overloaded node that has used the full
  push depth sends an invitation that is relayed through the cover until it
  reaches a cover node with a neighbour outside the cover, which then invites
  that neighbour. Acceptance: the 2 remaining runs end valid, the other 23
  stay valid, and no other development instance changes validity.
- F12b, certificate in the spanning-tree arm. The sums of the witness ride on
  the final report wave of the spanning-tree construction, and its root
  announces the verdict. Acceptance: on the infeasible development instances
  the spanning-tree arm announces infeasibility in the network, the verdict
  equals the run-level check, and the message cost is measured. All other arms
  keep the run-level check.

Time limit. One infeasible development instance with at least 500 nodes is
run under F11 before the tag, to confirm that a run still ends within the
time limit of the development sweep. If it does not, the push depth cap is
lowered from the number of nodes to the largest value that does, and the cap
is reported.

### Amendment 9, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Source. An independent verification of the rewritten proofs against the code,
on constructed development instances with a deterministic drop pattern. No
held-out instance exists.

Defects found.
- Stale load at a closed node. A node whose barrier has closed neither beacons
  nor expires records. If the forced load of a neighbour changes after that
  and every HELLO of that neighbour on that link is lost, the closed node keeps
  the old value, the network still becomes silent, and both ends of their
  shared flexible edge own it while the verdict reads solved. Reproduced on two
  constructed instances with 13 nodes and capacity 3.
- Epoch disagreement at silence. In three constructed runs the network becomes
  silent while nodes are in different epochs.
- Reply cache. A duplicate of a request whose reply was evicted from the
  bounded cache can be executed again (registered earlier as F14).

Repairs, each bounded, each with a regression test built from the run that
exposed it, each reverted and reported if it needs a redesign.
- F15, confirmed state. A change of a node's role or forced load is not final
  for ownership until every neighbour that shares a flexible edge with it has
  confirmed the new value. The node is not done while a confirmation is
  outstanding, and it repeats the announcement until it is confirmed. A node
  whose barrier has closed reopens it when it learns a neighbour's new value.
- F16, epoch agreement. A node does not finish while a neighbour it holds in
  its frozen view advertises another epoch.
- F14, as registered.

Acceptance. The constructed runs end with no doubly owned edge and with every
node in the same epoch, the lossless worked example keeps its cover and
weight, and no development instance changes validity. The message cost of the
confirmations is measured and reported.

If F15 is dropped, the ownership theorem is stated with its condition in the
statement, the stale-load execution is described in the manuscript as a known
limitation with its probability under independent loss, and the validator's
count of doubly owned edges is reported for every block.
