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

### Amendment 10, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Outcome of F16 as registered in Amendment 9. The rule was implemented as
written and changed nothing: the node that stays in the earlier epoch never
receives a frame of the newer one, and its neighbour's new view no longer
contains it. On three constructed development runs every surviving node
receives exactly the frames it receives when that node is switched off after
its last frame, slot by slot. A finished node is silent, so its neighbours
cannot tell a long burst on its link from its departure. An exploratory
variant in which the neighbour keeps announcing the new epoch until it hears
the node again ends the three runs in one epoch but never becomes silent after
a real departure, so it is rejected. F16 as registered is dropped.

Repair F16b, bounded epoch hand-off. A node that restarts, or adopts a newer
epoch, while a neighbour it held as finished has expired from its table keeps
its barrier open and keeps announcing the epoch until it hears that neighbour
in the new epoch or until a hand-off wait of twice the stale-window cap has
passed, whichever comes first. The wait is a fixed multiple of an existing
parameter and is not tuned.

Claim to be tested, on development instances only. With F16b, every burst on
one link that is shorter than the hand-off wait ends with all nodes in one
epoch, whatever the activity of the neighbour, and a real departure still ends
in silence at a bounded extra cost.

Acceptance. On the three constructed runs and their variants with a later
burst start, every burst length from 1 up to the hand-off wait ends in one
epoch; the departure twins become silent; the lossless worked example keeps
its cover and weight; no development instance changes validity. The extra
frames after a departure are measured and reported.

If the claim fails, F16b is reverted, and the manuscript states that a node
can miss a restart under a burst of positive probability, that the final epoch
is common to the nodes that hear the restart, that the discovered graph lacks
the links of a node that missed it, and reports the count of such links per
block. With or without F16b the manuscript states the bound beyond which a
burst is treated as a departure, and every block reports planned links missing
from the discovered graph.

### Amendment 11, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Defect found on development instances. Repair F11 lets every overloaded node
deepen its push up to min(n, 255) hops, and each push waits up to 2d+4 periods.
On an infeasible instance every such repair fails, nothing bounds the total
futile work, and the number of slots grows with n: 2.5 times the code before
F11 at n = 20, 5.2 times at n = 100, 10.4 times at n = 200, more at n = 500
(development instances with m = 8n and k = 6, lossless). The cost per slot is
unchanged; feasible runs are unchanged. The spanning-tree arm is not affected
when its in-network certificate (F12b) fires.

Repair F17, two parts, both measured on development instances only.
- F17a, certificate on every arm. The counting certificate of F12b (sum over
  nodes of min(deg, k) against m, and m against nk) is aggregated once per epoch
  over a tree rooted in the backbone, for the arms that have no spanning tree.
  A node that learns a certified verdict starts no repair and reports
  unresolved, as on the spanning-tree arm.
- F17b, bounded depth. The push depth of F11 is capped at a constant D_max
  chosen on the development set as the smallest power of two that keeps every
  repair F11 resolved on the 75 development runs with m = nk at their F11
  outcome. The value is fixed in this amendment's acceptance note before any
  held-out instance exists and is not tuned again.

Acceptance. The 75 development runs with m = nk keep their verdicts and covers;
infeasible development instances at m = 8n and k = 6 cost at most 2 times the
code before F11 in slots for n up to 200; certified runs report unresolved with
the verdict equal to the run-level flow check and no false certificate on any
feasible development run; the lossless worked example is unchanged in cover
and weight. Infeasible instances that the counting certificate misses are
reported with their cost (block M9).

If F17a is dropped, the manuscript states that only the spanning-tree arm
certifies infeasibility in the network and reports the cost on infeasible
instances per arm. If F17b is dropped, the depth bound stays at min(n, 255) and
every large infeasible run is reported with its cost and any time-limit
truncation.

### Amendment 12, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any calibration run

Defects found while estimating the run time of the registered blocks on
development instances and smoke seeds 1 to 3.

- Spanning-tree arm under loss. A lost INITIATE that a fragment forwards to a
  child is never sent again, so the child stays one level behind and the TEST
  messages addressed to it are deferred for ever; the GHS frames carry no epoch,
  so frames of an earlier epoch are processed after a restart, and one
  asynchronous run crashes when a REPORT reaches a node that was never
  initiated. Under 5 percent independent loss at n = 100, and in some conditions
  at n = 50, the arm runs to the time limit, so hypothesis H-c would fail for it
  for an implementation reason.
- Depth-first comparison arm. A TOKEN of a larger walk is answered with a bounce
  instead of being ignored as the extinction principle of the published
  algorithm prescribes, so a stale token travels between two absorbed nodes for
  ever and the run never ends, under the synchronous scheduler on unit disk
  graphs even without loss.

Repairs, each with a regression test from the run that exposed it.
- F18: INITIATE is repeated until the child reports at the new level (the
  persistent-request rule of repair F1), and GHS frames carry the epoch byte of
  repair F3, so frames of an earlier epoch are dropped.
- F19: the comparison arm ignores a TOKEN of a larger walk, as the published
  algorithm does. This restores the published behaviour and does not improve
  the arm.

Acceptance. F18: lossy spanning-tree runs at 5, 20 and 30 percent independent
loss and under the Gilbert-Elliott channel on development instances with n = 50
and 100 end within the time limit and valid; lossless spanning-tree runs keep
verdict, cover and weight; the worked example is unchanged. F19: the stalled
development and smoke runs end solved and valid; lossless runs of the arm keep
their cover and weight where they ended before. If F18 is dropped, H-c is
reported as failed for the spanning-tree arm with its cost.

Acceptance note to Amendment 12, 2026-11-18, before the frozen tag and before any held-out instance exists. The mechanism of F18 as built and measured on development instances differs from the wording above, and the wording is corrected to it: a fragment repeats INITIATE to a child whose HELLO shows an older round, and repeats CHANGE_ROOT with its level until the next round (a lost CHANGE_ROOT caused 9 of the 57 truncated development runs); the arm drops GHS frames whose sender's epoch, as recorded from its HELLO, differs from the receiver's; a REPORT of a round the receiver has not entered is deferred, which removes the crash. No epoch byte is added to GHS frames. Measured: 66 of 66 lossy development and smoke runs solved and valid against 57 of 66 truncated before; 480 lossless runs identical in verdict, cover, weight and slots, with at most 0.48 percent more frames. F19 is accepted as registered.

### Amendment 13, 2026-11-18, before the frozen tag, before any held-out instance exists and before any calibration run. Consolidation of the repair conditions into six general rules (D1).

Motivation. The bounded exhaustive explorer (X1, `ccvc/bb/explore_loss.py`) and the design analysis D1 found six violation classes on the live tree (fingerprint d40573c10255): runs reported converged while frames remain; asymmetric frozen views giving false solved verdicts and covers disconnected on the discovered graph; a refusal treated as final after a transient re-verification; a false in-network infeasibility certificate on the spanning-tree arm; phase-1 state left at silence; decisions reading neighbour records announced in an older epoch; and a closed node that owes a request to a departed peer and never stops. Each is an instance of a condition that earlier repairs applied locally. The following rules replace those conditions. They are stated for every arm, and each is implemented once.

G1, epoch rule. A decision rule reads a neighbour only through the frozen-view accessor, and that accessor returns only records whose last HELLO carried the reader's epoch. A record of another epoch counts as not heard, so the rule waits (the F4 wait). Records are filtered, not deleted, because liveness and the signal-strength gate are properties of the link. The HELLO-borne epoch tests of F12b, F15 and F16b, and F18's record test, use the same predicate. F3's frame byte stays.

G2, mutual verification per epoch. (a) A restart or an epoch adoption sets every record unverified and starts its handshake again. (b) A LINK is answered only by a node that holds a record of the asker with its gate open. A LINK that arrives before the asker's HELLO is answered when that HELLO arrives. (c) A node's DONE HELLO carries its frozen view as a list of identifiers. A node that finds itself missing from the DONE view of a frozen neighbour marks that neighbour unverified, so its view difference restarts the epoch. Together these make the final frozen views symmetric on every backend, which replaces the assumption of symmetric final views in Section IV.

G3, request rule. Every request (JOIN of every reason, HANDOVER, PUSH, relayed invitation, late acknowledgement, CERT) is repeated with the capped doubling backoff until it is answered or the epoch changes. The give-up and re-arm of JOIN (F1) is withdrawn. A receiver answers every copy: from the reply cache or the high-water mark (F5, F14), by a refusal only if the sender is outside its frozen view (F7), and by silence if the sender is a frozen neighbour whose record is momentarily unverified or older (the F4 wait). A refusal is therefore final for the epoch.

G4, finishing rule. A node owes something while it has an open request, a push chain, a relayed search, a certificate wave, an unconfirmed announcement (F15), a hand-off (F16b) or a stale frozen record (F4/G1). Its barrier is closed exactly when it is DONE, owes nothing and every frozen record is DONE. It is `done` exactly when its barrier is closed. It falls silent and suspends expiry only when closed, so a node that owes something keeps beaconing and expires a silent peer (F13 windows).

G5, certificate rule. The in-network infeasibility verdict is issued only by a completed echo wave over the frozen views (F17a, docs/r1_patches/F17.patch). A wave is complete only when every node has heard from every frozen neighbour. The spanning-tree arm's REPORT sums (F12b) no longer certify; on that arm a positive sum starts a wave. F17b: the F11 push depth is capped at D_max, the smallest power of two that keeps every F11 resolution on the 75 development runs with m = nk at its F11 outcome (rule of Amendment 11); the measured value is entered in the acceptance note of this amendment before any held-out instance exists.

G6, phase rule. Deferred questions of a finished arm phase (the spanning-tree arm's deferred GHS questions at halt) are discarded at the transition.

Replaced conditions: F1's JOIN re-arm (by G3); the scattered epoch tests of F12b, F15, F16b and F18 (by G1); the per-predicate obligation lists in `done`, `_barrier_closed` and `settled` (by G4); F12b's certificate (by G5); and the symmetric-view assumption (by G2). Every other repair (F2 to F19) is kept unchanged.

Acceptance, all on a private copy before anything is applied to the live tree:
(i) the full `ccvc/bb` suite passes, one process per file;
(ii) X1's explorer, re-run on the copy with the same tier, reports zero violations, apart from `epoch_split_exempt` and symmetric missing edges (G ≠ Ĝ*), and every remaining one is named with the assumption it lies outside;
(iii) the constructed failing runs of F1 to F19 and of D1 (older-epoch reads, closed departure) pass;
(iv) the worked example has the same cover, weight and verdict under both schedulers, and its slots, tx, rx and bytes are reported against the submitted 54/522/1397/6866 (sync) and 381/966/4813 (async);
(v) on the lossless development runs, verdicts, covers and weights are identical, and frame counts, bytes, maximum payload and convergence time are reported per file.

If (iv) or (v) fails for a rule, that rule is withdrawn or revised and re-registered before it is used.

Correction to the acceptance note of Amendment 12: the F18 repeat of INITIATE is triggered by a child's REPORT of an older round or its CHANGE_ROOT of an older level, once the parent's round is at least 600 ms old; it is not triggered by HELLO.

Not included, and stated in the manuscript instead: several decisions (the connector pair rule, the gap rule, Phase 2, the transfer ladder, the end of phase 1 on the spanning-tree arm) depend on message timing, so the lossless cover can differ between the synchronous and the asynchronous scheduler (measured on 1 of 20 development files, +10.7 percent weight in sync). A phase-ordering rule that removes this changes lossless covers and is not part of this amendment; results are reported per scheduler.


Correction to Amendment 13, rule G2(c), 2026-11-18, before any code of the amendment is accepted. Carrying the frozen view in every DONE HELLO would make the HELLO size grow with the node degree and break the bounded HELLO of Section III. G2(c) is replaced by: every node asks, with its first DONE HELLO, every frozen neighbour to confirm it (the F15 confirmation, now asked unconditionally at DONE); a neighbour echoes only a node it holds in its frozen view of the same epoch; an unconfirmed node stays open and keeps beaconing until the other end verifies it, so a view difference restarts the epoch. The HELLO keeps its bounded size (the F15 echo bound of at most 2 entries). The worked example then needs 55 slots and 530 transmissions instead of 54 and 522 under the synchronous scheduler, with the same cover and weight; the manuscript reports the numbers of the frozen version.

Acceptance note to Amendments 11 and 13 (F17b), 2026-11-18, before the frozen tag and before any held-out instance exists. Measured D_max = 8. On the 75 development runs with m = nk, the uncapped F11 deepening reaches depth 6, 12, 24 or 200 in 25 runs; caps 2 and 4 each turn 3 of them from solved to unresolved (n200_m1200_s6: MIS-connector, tree-aggregation and annealing arms asynchronous for cap 2; depth-first synchronous and Wu-Li asynchronous for cap 4); with cap 8 all 14 runs that push deeper than 8 keep verdict and cover, and the other 61 never reach the cap. The annealing arm, asynchronous, on that instance takes 2.8 times as long with cap 8 and finds the same solution. D_max = 8 is fixed and not tuned again.

Addendum to Amendment 13, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any code of the amendment is accepted. Replaying the explorer's kept repros on the first build left two further classes on the live tree's shared code. Each one is closed by an extension of the rules above.

G4, extended. (a) The F13 wait for a heard but unverified neighbour is bounded: a link whose handshake failed in two rounds of the current epoch is not waited for again. Under G2(b) such a link is one-way, so a permanent wait would never end on a one-way gate. (b) A LINK handshake in progress is owed like any request, so a node is not closed and not done while a handshake round is open.

G6, extended. The spanning-tree arm does not defer a GHS question once its phase 1 has ended.

G7, edge version rule. Each end of an edge counts the completed transfers of that edge it took part in: the receiver counts at an accepted transfer, the sender at the release on the answer. The two requests HANDOVER and PUSH carry the sender's count in one added byte, modulo 256. A receiver refuses a request whose count differs from its own, after the reply cache and the high-water mark have had their turn (F5, F14), because such a request was overtaken by a transfer that has since completed. Explorer class: double_owned. On n5g17 k = 2, with HELLO 8 on 1→5 lost, node 1's PUSH of (1,5) was executed by node 5 after node 5 had handed the same edge to node 1, and both ends held it at silence (both arms). Cost: one byte per HANDOVER and PUSH frame. Lossless decisions are unchanged, because versions always match there.

Remaining classes, stated and not repaired. (1) A planned edge missing at both ends after a burst longer than the discovery or restart window. The run is valid on Ĝ*, the scope of every theorem, and reported as G ≠ Ĝ*. (2) FabricTree: the core halts on its partner's REPORT before a child it has just absorbed has reported (n4g1 k = 2, burst of 5 on 4→1), so that child ends phase 1 as OUT and the cover is disconnected on Ĝ*. This is a correctness defect of a reported arm and is not left open: it is repaired by an extension of G6 registered before acceptance; if no general form is found, the class is reported with its count per block.

Second correction note to Amendment 13, 2026-11-18, before the frozen tag, before any held-out instance exists, and before any code of the amendment is accepted.

G4, owed echo. An echo a node owes (a neighbour asked it to confirm, F15 and G2(c), and the echo is not yet sent) counts among the obligations of G4. Found by the explorer on the consolidated copy: on two four-node development graphs under the asynchronous scheduler, with two HELLOs lost, the run was declared done before the owed echo went out, and one frame followed the verdict. With the rule the worked example needs 54 slots, 528 transmissions, 1417 deliveries and 7121 bytes under the synchronous scheduler (388, 988 and 5076 bytes asynchronously), with the same cover and weight.

G6, extension (round content). A repeated message of a round repeats the content the round was opened with, as G3 already requires of every request. On the spanning-tree arm the INITIATE that F18 repeats to a child carries the level, fragment and search state of the original INITIATE to that child, not the sender's current state, so a node searches in every round it enters, and a core halts only after its own half has searched and every child of the round has reported. Defect traced on a four-node development graph with capacity 2 and a burst of 5 frames on one link: a repeated INITIATE carried the state FOUND, the receiving node entered the round without searching, absorbed a neighbour and halted on a deferred REPORT before that neighbour had reported, so the neighbour ended phase 1 outside the backbone and the cover was disconnected on the discovered graph. This accounts for every remaining disconnected cover of the explorer and for the earlier false certificate on a five-node star. Lossless runs never repeat an INITIATE, so they are unchanged by construction; this is confirmed in the acceptance run. Every other repeated request of every arm is checked once before the tag to carry its original content.

Wording correction to the G6 extension of the second correction note, 2026-11-18, before any code of the amendment is accepted. Two repeat paths of the spanning-tree arm rebuilt INITIATE from the sender's current state: the F18 repeat to a child in an older round, and the answer to a repeated CONNECT on an edge that is already a branch in the current round (including the absorb branch, where the merge partner that never received the INITIATE repeats its level-0 CONNECT). The rule reads: a repeated message of a round repeats the content it was first sent with in that round, as G3 requires of every request; on the spanning-tree arm every repeat of an INITIATE carries the level, fragment and search state of the INITIATE first sent to that neighbour in the round, so a node searches in every round it enters, and a core halts only after both halves have searched and every child of the round has reported. In the traced execution the merge partner's INITIATE was lost, the partner's repeated level-0 CONNECT was answered with an INITIATE carrying the state FOUND, and the receiving node entered the round without searching.

### Amendment 14, 2026-11-19, before the frozen tag and before any held-out instance exists. Open choices of the blocks, the centralized reference and the order of generation.

Source. The builder of the job lists (E1), the pre-freeze gap check (P1), the hybrid genetic reference (H1) and the Mininet-WiFi harness check (E2) listed every choice the blocks need that the registration above leaves open. Each is fixed here as the builder already applies it, on development data only. No held-out instance exists.

Configurations. M5 runs ten configurations: NexusWarp sync and async, FabricTree sync and async, TemperFlux/async, TemperFlux-Tk/async, Wu-Li CDS/sync, D-GRCCVC/sync, D-GCCVC/sync and TokenTrail/sync. After Amendment 2 only H2a degree 8 remains and H2a has no n = 15 cell, so M5 has 4400 runs, not 6400. M6 runs five configurations, the three arms of the calibration: NexusWarp sync and async, FabricTree sync and async, and TemperFlux/async. Its 60 instances are the m/n = 4 cells of H1 and the degree 8 cells of H2a. Every Gilbert-Elliott condition runs twice (Amendments 5 and 6), the second time with F9 off, which adds 2700 runs. M8 uses one channel seed for synchronous lossless runs and three otherwise; its two annealing configurations are TemperFlux/async and TemperFlux-Tk/async; its weight laws run the ten M5 configurations, lossless, channel seed 1, on the set M8-weights. M8-weights uses the H1 graph of the same seed with n 25, 50 and 100, m/n 2 and 4, seeds 101 to 105, and four laws: unit weight 1, degree weight deg(v), lognormal 20 exp(N(0,1)), and energy 20/U[0.1,1].

Time limits. Every block uses the limit of the development sweep for the size: 4 500 000 ms for n <= 25, 12 000 000 for n <= 100, 22 000 000 for n <= 200 and 102 000 000 above. M9 (n = 30) uses 12 000 000. The exact optimum and the LP bound are computed by r1_optima with 3600 s of process CPU time per file; a file that reaches the limit keeps the LP bound as its reference and is reported as timed out. Set W of M7 uses capacity 6 and 600 s per run.

Added blocks. M10, the bridge-discount ablation of the submitted experiment 2: the 24 submitted runs with the repayment of the bridge credit off and on, plus H1 n 25 and 50, m/n 2, seeds 101 to 110 (80 runs). Reported: validity, verdict, weight and frames per run. Replays of the submitted wireless claims: the 10 percent loss replay (135 runs), the two host-UDP socket equivalence tests, and the development-set optima and centralized greedies at the frozen version (190 files). The paired loss experiment is re-expressed through r1_run on the 27 discovered graphs, synchronous, loss 0 and 0.05, channel seeds 0 to 4, with its own budget of 200 000 ms.

Centralized reference. The hybrid genetic algorithm of kol2026 is added to the references of section 4, as `solve_hga` of the pinned upstream file (sha256 b0a18b6952ea8818b9c5d880d2d8990a2662a09476c3ed7083db7267119a5044), run by hga_ref on H1, H2a and H2b with n at most 200 (320 instances), capacity 6, population 40 and 60 generations (kol2026, Table 2), one run per instance with GA seed 42, and 3600 s of process CPU time. A run that reaches the limit is a failure and is not re-run. Three seeds would cost about 120 CPU hours instead of 40. The seed spread measured on development instances, at most 1.91 percent of the weight, is reported as the uncertainty of the reference. The cover is checked by CoverAudit, with the owner map reconstructed by max-flow. The solver does not replace the reference of hypothesis H-b, and no test is made against it. hga_ref and r1_optima enter the code fingerprint before the tag.

Order and guards. The held-out sets are generated only after the annotated tag coverweave-r1-frozen exists. The generator, build_jobs, hga_ref and r1_optima refuse a pre-registered seed until then, and only an annotated tag counts.

Third correction note to Amendment 13, 2026-11-19, before the frozen tag, before any held-out instance exists and before any calibration row is used. The acceptance explorer on the consolidated copy (840 configurations, 756 086 runs) left 32 violations against about 71 000 on the live tree. All 199 kept repros were replayed and classified: 179 lie in the registered out-of-scope classes (G ≠ Ĝ*, and bursts longer than the hand-off wait of Amendment 10), three classes are breaks inside scope, and one class breaks no claim. The three breaks are closed by clarifications of rules G4 and G1.

G4, owed answers and owed input. (a) An answer a node owes is cancelled only by the event that makes it false. F10's late acknowledgement is dropped when the edge is released, as before, and no longer when the node offers the same edge again. A re-offer carries the advanced version (G7), and the peer refuses it until the owed acknowledgement has arrived. With the cancellation in place a permanent double ownership occurred (six-node graph, capacity 2, both arms, synchronous). (b) Frames a node has received but not yet processed are owed input, so such a node is not done (five-node graph, capacity 1, asynchronous).

G1, waiting in handlers. A request that is decided over the frozen view (JOIN, HANDOVER, PUSH, CERT) is not acted on while the view is stale, and its sender repeats it (G3). The spanning-tree arm does not wake GHS on a stale view, because waking orders all of a node's edges. Before this, a CONNECT woke a node on a partial edge set and five level-0 CONNECTs waited on each other (five- and six-node graphs, asynchronous).

Stated, not repaired. Under loss, a node's repair ladder can end before capacity freed later elsewhere reaches it. The node reports Unresolved, which no theorem excludes (five-node graph, capacity 1, 4 repros). It is reported as a quality outcome per run.

Acceptance, on a private copy before the live tree changes: the full ccvc/bb suite; the explorer on the full tier; the worked example under both schedulers (the asynchronous convergence time may change by G4(b), the frames, cover and weight may not); and the lossless development identity of verdicts, covers and weights.

### Amendment 15, 2026-11-19, before the frozen tag and before any held-out instance exists. Calibration outcome and the stale window under loss.

Calibration, as registered (Amendments 5 and 6). 864 runs on code fingerprint b0309c3321be: eight development instances, the six calibration configurations, channel seeds 1 to 3, ge:0.10:4. A run counts when it ends within the time limit with a cover valid on the discovered graph. Shares: F9 on 92 of 144 (63.9 percent); default window of 3 periods without F9, 7 of 144 (4.9 percent); fixed windows 6, 12, 24 and 48: 46, 135, 144 and 144 of 144 (31.9, 93.8, 100 and 100 percent). F9 is not accepted. The Amendment 5 rule takes the smallest candidate at or above 95 percent, so the bursty-channel profile is a fixed stale window of 24 periods with the stabilisation window equal and F9 off: {"adaptive_stale": false, "stale_periods": 24, "stab_periods": 24}. It is not adjusted again.

Why F9 failed. F9 learns one window per directed link, and each lesson is paid with a network-wide restart, because any one expired record restarts the epoch. A graph with m edges has 2m directed records and each needs four doublings from 3 to 48 periods, so learning costs on the order of 8m restarts before the windows are long enough. Median restarts per run: F9 4188, default window 5129, fixed 12 102.5, fixed 24 12.5, fixed 48 0.

Development observation that widens the defect beyond bursty loss. Four timing probes on the development instance n100_m400_s1, channel seed 1, default window with F9 on: independent loss 5 percent, NexusWarp/async solved after 5 050 243 ms with 1885 restarts, FabricTree/sync solved after 4 331 200 ms with 1425 restarts; independent loss 30 percent, FabricTree/async truncated with 4607 restarts; ge:0.10:4, NexusWarp/sync truncated with 4194 restarts. The cause is the same: a false suspicion anywhere restarts everything, and with 800 directed records a window of 3 periods expires falsely every few seconds even at 5 percent independent loss. The default window is therefore not a usable operating point for any lossy channel at n = 100, and Amendment 5's restriction of the profile to Gilbert-Elliott conditions does not hold.

Repair, no code change to a measurement file (the fingerprint stays b0309c3321be). The stale window is a channel parameter, chosen by the deployer for the channel. Every lossy run of every block uses the profile; lossless runs use the default, so the lossless blocks stay comparable with the submitted results.
- M6. All seven lossy conditions and the empirical condition run at the profile, channel seeds 1 to 3. The lossless condition runs with the default and, for the cost of the profile that Amendment 5 asks for, with the profile. The default window under loss is kept as the ablation on n = 25 and 50, channel seed 1, conditions 0.05 and ge:0.10:4 (400 runs). M6 has 8500 runs before the empirical condition, replacing the 7200 plus 2700 of Amendment 14.
- M8. The lossy runs (5 percent) take the profile as their base, and each factor level is applied on top of it. The stale window factor is re-centred on the profile: levels 12 and 48, half and double of 24 as for t_min_frac, with the stabilisation window equal. The lossless runs keep the default base and the registered levels 2 and 5. The run count is unchanged.
- M7. A wireless channel is lossy, so every M7 run uses the profile (set in the M7 job builder, not a measurement file).
- The paired loss experiment of M2 reproduces the submitted experiment and keeps the submitted settings.
- F9 stays in the code. It is inert on lossless runs (registered property of Amendment 6, tested), so the lossless blocks do not depend on it, and it is off wherever the profile is used. The paper reports F9 as a repair that was tried and rejected by its registered acceptance test, with the shares above and the cause.

A second defect, found before the tag and under repair. Three further development probes with the profile on n100_m400_s1 truncated with about 1000 restarts each: 30 percent independent loss (FabricTree/async), ge:0.10:4 (TemperFlux/async) and ge:0.20:4 (NexusWarp/sync); at 5 percent the profile solved with 2 restarts. A window of 24 periods cannot expire falsely at 30 percent independent loss (0.3 to the power 24 is about 3e-13), so the stale window is not the cause. Recording the cause of every epoch bump on NexusWarp/sync over 300 s showed no lost link and only gained links (375 at 30 percent, 116 at ge:0.10:4), and every gained link had a failed LINK handshake when the node froze its view. The freeze gate waits only for a handshake with attempts left; the failed handshake is retried 12 periods later, its success changes the verified view, and the view change restarts the epoch, where G2 verifies every link again. The chance that some handshake fails grows with 2m, so the loop does not end at n = 100. Rule G4(a) already bounds this wait at DONE to two failed rounds, but the freeze gate does not apply the bound. The repair is analysed as one change and registered in a note to this amendment before the tag, with its acceptance: the full suite, the full-tier explorer, the lossless development identity and a repeat of the calibration on the repaired code.

Note to Amendment 15 (link gate), 2026-11-19, before the frozen tag and before any held-out instance exists. Repair of the second defect above, analysed as one change (D2).

- Rule, G4 with one wait bound. A node does not freeze its verified neighbourhood, and a QUIET node does not become DONE, while it hears a link-up, unverified neighbour whose handshake has failed fewer than R rounds in the current epoch. After R rounds the link is not waited for. Its cooldown retry continues, a later success restarts the epoch as before, and a link that never verifies stays out of Ĝ* at both ends. Keeping the retry keeps the asymmetric case (one end verified, the other not) and the deadlock that the cooldown retry was added for closed.
- R is the parameter link_rounds_max, default 4, shared by both gates; it replaces the constant 2 of G4(a). R was chosen on development data after measuring R = 2, 3, 4 and 6 on n100_m400_s1, NexusWarp/sync, the profile, 300 s simulated: at 30 percent independent loss 61, 12, 0 and 0 epoch bumps; at 5 percent and ge:0.10:4 none from R = 2 on. The value is the smallest of {2, 3, 4, 6, 8} for which these runs and the probes FabricTree/async 30 percent, TemperFlux/async ge:0.10:4 and NexusWarp/sync ge:0.20:4 solve without a restart. The expected number of links failing all R rounds, 2m times 0.133 to the power R, is 14, 1.9 and 0.25 for R = 2, 3 and 4, which is where the step lies. The choice is reported as made after these development measurements; R is not changed on held-out data.
- Cost. A node whose link is really one-way waits up to R rounds, about 4 times 33 periods with the defaults, before it freezes and again at DONE. Lossless runs never fail a handshake, so the rule never binds there.
- Results on the repaired copy (fingerprint 09af268d95e0). Full ccvc/bb suite 1298 passed, 0 failed, 24 skipped, with five new tests and four updated test horizons. All six probes solve with no restart, valid on the planned and on the discovered graph (t_conv 30 to 118 s). The lossless development identity holds in every field against b0309c3321be, 560 of 560 runs. A replay of the 199 explorer repros kept from the consolidated copy: solved_reduced 169 to 0, epoch_split_exempt 10 to 10, unresolved_feasible 5 to 5.
- Acceptance before the tag: the full-tier explorer with no class above its count on b0309c3321be, and the calibration of Amendment 5 repeated on 09af268d95e0; the profile is re-derived by the same rule. The calibration on b0309c3321be is kept and reported as the calibration of the pre-repair candidate.

Second note to Amendment 15 (calibration on the repaired code), 2026-11-19, before the frozen tag and before any held-out instance exists.

- Result. The calibration of Amendments 5 and 6 was repeated on 09af268d95e0: 864 runs, no failed job. F9 on: 144 of 144 (100 percent). Default window without F9: 8 of 144 (5.6 percent). Fixed windows 6, 12, 24 and 48: 55, 143, 144 and 144 of 144 (38.2, 99.3, 100 and 100 percent). On the pre-repair code F9 and the window of 12 periods failed, mostly because of the link-gate defect, not because of the stale window.
- Consequence under the registered rules. F9 now passes the acceptance test of Amendment 6, and the Amendment 5 rule now gives a window of 12 periods instead of 24. Amendment 15 extended the profile to every lossy run because of n = 100 probes on the pre-repair code, while the calibration set stops at n = 50. The two registered texts therefore set the lossy runs differently.
- Resolution rule. It is fixed and committed here before any of the runs below exists. The six development probes of the link-gate note (n100_m400_s1, channel seed 1, time limit 12 000 000 ms: NexusWarp/sync at 5 percent, 30 percent, ge:0.10:4 and ge:0.20:4; FabricTree/async at 30 percent; TemperFlux/async at ge:0.10:4) are run on 09af268d95e0 with two candidates: (a) F9 on with the default window, and (b) the fixed window of 12 periods. A candidate passes when all six runs end within the time limit with a cover valid on the discovered graph. This is the criterion of Amendments 5 and 6.
  - If (a) passes, F9 is the frozen protocol under loss, as Amendment 6 registers. Every block uses the default parameters, M6 runs each Gilbert-Elliott condition a second time with F9 off as the ablation (the design of Amendment 14), M8 keeps its registered levels, and M7 uses the default.
  - If (a) fails and (b) passes, Amendment 15 applies with a window of 12 in place of 24, and the M8 stale-window levels become 6 and 24.
  - If neither passes, the smallest window in {24, 48} for which all six probes pass is taken. A window of 24 passed all six in the link-gate note. The rule's shortfall is then reported.
- Sizes above n = 100 are not probed. This is reported.
- Outcome of the probes (run after the rule above was committed). (a) F9 with the default window: all six solved and valid on the discovered graph. Restarts were 0, 29, 74, 78, 104 and 62, and t_conv was 16.4, 255.2, 308.8, 1138.5, 378.3 and 450.2 s, in the order listed above. (b) Window of 12: five solved and one failed. The run at ge:0.20:4 was truncated with 1525 restarts, and TemperFlux/async at ge:0.10:4 needed 1119 restarts and 9 804 s. Branch (a) therefore applies. F9 is the frozen protocol under loss. Every block, M7 included, runs the default parameters. M6 and M8 follow the design of Amendment 14: each Gilbert-Elliott condition of M6 runs a second time with F9 off, M8 keeps the default base and levels 2 and 5. The fixed-window profile of Amendment 15 is not used in any block, and its calibration shares are reported as the comparison baseline of Amendment 6. The pre-repair rejection of F9 and its cause are reported as well. F9 failed on b0309c3321be because each learnt window was paid with a restart, and the late-verified links made that restart loop endless. The link gate removed the loop.
- Explorer acceptance on 09af268d95e0, full tier, default parameters (F9 on): 840 configurations, 786 193 runs, no crash. double_owned, not_silent, truncated, false_solved, false_infeasible, invalid_discovered, unowned, capacity, nonzero and exception are all 0. epoch_split_exempt 9 (b0309c3321be: 9). unresolved_feasible 4 (4). solved_reduced, an INFO class, 3 (2474). No class is above its count on b0309c3321be, so the candidate is accepted for the tag.
- Correction to the suite count above. The 1298 passed and 24 skipped were measured in a copy without the development data, so 22 data-dependent tests were skipped. With the data present, two tests failed on 09af268d95e0, and both fail on b0309c3321be as well. (1) test_r1_repairs2, F11 deepening: the test expected every push depth to be a multiple of 3, but F17b (Amendment 11, D_max = 8) stops the doubling at 8. The run is solved and valid, so the test was corrected to allow the cap. (2) test_r1_f14 (n10_m40_s2, 30 percent loss, F17 switched off by the test): seed 6 ends unresolved at 3 092 800 ms, after the test's horizon of 3 000 000 ms, because the link gate waits up to R rounds. The horizon became 6 000 000 ms. With the gate, the evicted-copy case no longer occurs on seeds 0, 6 and 14, so seed 1 was added. 24 seeds were checked, all end unresolved with no double claim and no inconsistent answer. On b0309c3321be the same runs truncate with 1058 restarts, which is the loop the link gate removed. Neither change touches a measurement file. The suite with the data present: 1320 passed, 0 failed, 2 skipped (slow Wu-Li tests).

### Amendment 16, 2026-11-20, after the frozen tag and after the held-out runs, before any reserve instance is run. False successes of TemperFlux, and of FabricTree under loss.

Finding, reported as found (section 1). On 09af268d95e0, rows where an arm reports solved and the independent validator rejects the cover: M4 (H2b, lossless) 15, namely Anneal-Local async 5 and sync 2, Anneal-TreeAgg async 5 and sync 2, Anneal-Trickle async 1; M5 1 (Anneal-Trickle async, H1); M8 5 (H2a, Anneal-Local async 2, Anneal-Trickle async 3, altered cooling or 5 percent loss); bridge 1 (Anneal-Local sync, the repay-off ablation); M6 1 (GHS-MST-Backbone async, H2a, ge:0.05:4). Every violation is a disconnected cover; vertex cover and capacity hold. H-a therefore fails on the frozen version, for the primary arm among others. The frozen rows stay the reported rows of every block, and H-a is reported as failed with its counts and Clopper-Pearson bounds.

Causes, from a diagnosis that reran the rows on the frozen snapshot (scripts kept with the repair).
- A, TemperFlux, connectivity is only a soft term. Freeze and DONE are local (no pending move with negative energy change, quiet periods, neighbour barrier). A join resets the flexible shares to one half, so a hub whose degree is well above 2k sees an overload term that outweighs the single bridge discount. The only move that reconnects a stranded cover component is then uphill and is blocked once T <= T_min. Barabasi-Albert graphs grown from a star have hubs of degree 16 to 45 next to pendant nodes, which is why H2b carries 15 of the 21 TemperFlux rows.
- B, TemperFlux, stale labels. When a cut vertex leaves, the stranded part keeps its old component label until a heartbeat timeout of 3 HELLO periods removes it, while a node freezes after 3 quiet periods. Connectors can therefore freeze seeing one label, and the second label appears after Loop A is off.
- C, FabricTree under loss. The halt test of the spanning-tree arm ("best is infinite on both halves") certified a fragment whose BRANCH marks were asymmetric after an epoch restart; the halt flood ended Phase 1 everywhere and the backbone built on the forest was disconnected.

Repair, one version, named R1-repair. Each rule restores one invariant that the paper states or needs.
- T1, exact labels (B). The Loop C label carries a hop count. A label whose hop count exceeds the node-count bound n_bar is dead, independent of any heartbeat. A change of the (label, hops) a node holds counts as not quiet for the freeze rule.
- T2, bridge obligation (A). Lemma: if C is a vertex cover of a connected graph, V \ C is independent, so C is connected if and only if no OUT node is adjacent to two cover components. Rule: an OUT node that sees two or more labels among its cover neighbours is pending regardless of the energy change, and joins when it holds the move right; once T <= T_min this join is the only move it may make. A node freezes only when no OUT neighbour in its view reports two labels. After the freeze, joins of OUT nodes with a cover neighbour remain allowed, since they keep the cover connected.
- F1, certified halt (C). The core halts only after an echo wave over its branch tree, started after the halt test and answered by every node of the tree in the current fragment identity, confirms that every BRANCH mark is symmetric and that no node holds a basic edge. Any other answer, a timeout or an epoch change cancels the halt and Phase 1 continues.
No other rule changes. No new tuned parameter is introduced: the hop bound is n_bar by design. If an implementation constant is needed it is chosen on development instances only and recorded here before any reserve run.

Acceptance on development, before any reserve run, on a private copy:
- regression tests that fail on 09af268d95e0 and pass on R1-repair, one per cause, built on development seeds;
- the full ccvc/bb suite;
- the full-tier explorer with no class above its count on 09af268d95e0, false_solved and invalid_discovered 0;
- lossless development identity in every field against 09af268d95e0 for every configuration outside the TemperFlux family and FabricTree (their code paths do not change); for those two, validity on every development run and the change of weight, tx and slots reported;
- the six n = 100 probes of the link-gate note, solved and valid.
If an acceptance item fails, the repair is analysed again as a whole on development data and this amendment gets a note before any reserve run.

Evaluation on the sealed reserve set (seeds 901 to 910, families H1, H2a and H2b at the cells of M3 and M4 with n <= 200, k = 6), both versions, same jobs:
- lossless, the seven affected configurations (Anneal-Local, Anneal-TreeAgg and FabricTree under both schedulers, Anneal-Trickle async); the other configurations are code-identical in both versions and are not rerun;
- under loss, FabricTree under both schedulers and TemperFlux async, on H1 and H2a with n in {25, 50, 100}, the seven lossy M6 conditions, channel seed 1.
Endpoints: false successes per version (H-a on the reserve set, one-sided 95 percent Clopper-Pearson bound), validity, truncations; paired changes of the ratio to the LP bound, tx, slots and t_conv between the versions (Wilcoxon signed-rank, Holm over families, rank-biserial r). The repair is accepted if R1-repair has no false success on the reserve set. The result is reported next to the frozen result in the manuscript and the response letter, whichever way it falls. The reserve set is used once; a failed repair is reported and not tuned on it.

Note to Amendment 16 (implementation), 2026-11-20, before any reserve run. R1-repair is implemented in a private copy, code fingerprint aedb4a3287bc. Choices the amendment text leaves open, fixed here:
- T1: hops are 0 at the root and the smallest neighbour hops plus 1 elsewhere; n_bar is the node-count bound n_bound that the run sets. The ANNEAL HELLO tail grows from 8 to 10 bytes (hops in 15 bits, the T2 obligation flag in bit 15); an anneal HELLO is 23 to 33 bytes.
- T2: the obligation holds at every temperature; above T_min the obliged join is accepted whatever the energy change, below T_min it is the node's only move. A node does not freeze while an OUT neighbour advertises the flag, and a frozen obliged OUT node joins.
- F1: only the core with the smaller identifier runs the echo wave (the other core halts on the DONE flood). The wave times out after n_bar x ack_timeout x 2^(ack_max_attempts - 1), derived from existing constants. After a cancel the next wave follows the capped doubling backoff already used for repeated requests. A BRANCH mark on an edge that is not live counts as asymmetric. Two new message types, GHS_CHECK and GHS_CHECK_ACK, 15 bytes each.
- The Mininet-WiFi node program does not set n_bound, so there the hop bound falls back to 32 767. M7 runs the frozen version only; R1-repair is not run on Mininet-WiFi, and this is reported.
- Regression tests (test_r1_a16.py, development seeds and instances only): hub overload on a synthetic Barabasi-Albert development seed, the hop bound, no freeze on two labels (development n50_m100_s3, repay off), refused halt with an asymmetric BRANCH mark. All four fail on 09af268d95e0 and pass on aedb4a3287bc.
- The three diagnosed rows (M4 n25_m84_s306 and n100_m196_s307 Anneal-Local async, M6 H2a n100_m400_s210 ge:0.05:4 FabricTree async) were rerun for diagnosis only and are valid on aedb4a3287bc; they are not evidence for the repair, which is judged on the reserve set alone.
Open acceptance items before the reserve run: full suite, full-tier explorer, lossless development identity, the six n = 100 probes. They run after M7, because M7 needs an idle host.

Second note to Amendment 16 (H-b on the reserve set), 2026-11-20, before any reserve run. On the frozen held-out runs H-b is met in 5 of 13 bands, all five on H1; it is not met on H2a or H2b. This is a quality outcome, not a defect with a known cause, so no protocol change follows from it and none is tuned on held-out data. Since the lossless reserve runs of Amendment 16 contain both TemperFlux and FabricTree under the asynchronous scheduler, H-b is also tested on the reserve set for R1-repair, with the same test, bands and correction as section 7, and reported next to the frozen held-out verdicts. The bands of the reserve set are those of M3 and M4 with n <= 200.

### Amendment 17, 2026-11-26, after the frozen tag, after the held-out runs and after the reserve runs of Amendment 16, before any run of the version below. Theorem 3(b) refuted by the Lean model of the transfer handlers, and repair R2R3 (rules R2, R3 and R4).

Finding, reported as found (section 1). The Lean 4 model of the transfer layer of one flexible edge (`SwarmInferLean/CoverWeave/ExecFullTransfer.lean` in the Lean project; it models the fields of `bbcvc.py` that the HANDOVER and PUSH handlers read and write, with one FIFO channel per direction that may lose frames) refutes Theorem 3(b) of the revised manuscript (`sections/04-formaleng.tex`, `thm:cap` (b)). Three machine-checked counterexamples end quiet, with every frame delivered in order, every accepted transfer acknowledged and the message-free start agreed, and with the edge owned twice or not at all.
- `thm3b_fails_without_yield` (`traceNoYield`). Without a yield rule two HANDOVERs of the same edge that cross are both accepted and both acknowledgements arrive after the acquisition count moved, so neither end releases: two owners. The code closes this race with `_yields_to_inbound`, which the text does not state. This is a defect of the text only.
- `thm3b_fails_with_yield` (`traceBusy`). With every handler as the frozen code writes it: a's PUSH reaches b, which starts a push chain; a's retransmission gets the busy NACK of F10 and a keeps the edge; b's crossing HANDOVER of the edge reaches a, which no longer has an open request and accepts; b's chain succeeds and b takes the edge; b reads the HANDOVER acknowledgement after its acquisition count moved and keeps the edge; a reads F10's late acknowledgement after its acceptance cancelled its offer and ignores it. Two owners. This is a defect of the code (F10).
- `thm3b_fails_repeat` (`traceRepeat`). HANDOVERs only: b refuses a's request as stale (G7), its reply cache evicts the refusal, and a's retransmission is a repeat that F14 answers from state ("do I hold e"), positively, because b still holds the edge under its own open offer. b reads the acknowledgement of its own offer and releases, a reads the positive answer and releases. No owner. This also contradicts Lemma `lem:dup` ("a repeated request receives its reply"). This is a defect of the code (F14).
- A fourth run, found afterwards by the bounded search of the same model on the code with R2 and R3. HANDOVERs only, no busy PUSH, no eviction: both ends offer e; the message-free start stops giving e to b, which is full; a's request reaches b, which does not yield, and `_accept_edge` refuses it for lack of room, but counts a take (theta(e) becomes 1), stamps `_retake_seq` and retracts b's own offer before the room test; b's own request is lost and retransmitted, and a, its offer answered, accepts it and acknowledges; b reads the acknowledgement with theta 1 against the stored 0 and refuses it as stale; once the start gives e to b again, both ends hold it. This is a defect of the code (`_accept_edge`).
The frozen rows stay the reported rows of every block. In the frozen held-out blocks no row reports a double claim and every validator rejection is a disconnected cover (Amendment 16), so no measured row shows these runs; the counterexamples need a busy chain that crosses an opposite transfer of the same edge, or an evicted refusal.

Repair, one version, named R2R3-repair, on top of R1-repair and the post-freeze late-acknowledgement correction (main at commit ec40190, fingerprint 54fcf00c82b5). Only `ccvc/bb/bbcvc.py` changes among the measurement files (commits 5d9936a for R2' and R3, 6508e3e for R4 and bd9cbab for R2'' on branch r2r3-repair of the release repository; the commit that appends this amendment carries the annotated tag coverweave-r2r3-repair). Code fingerprint 026c2dc5f381.
- R2'', a busy refusal is final (replaces F10). A copy of a PUSH that arrives while the chain serving it runs, without room for the edge, is refused as before (busy NACK, or F7's refusal when the sender is heard but not verified), and the chain is marked. Every later answer to a marked request is PUSH_NACK: the chain runs to its end but never takes the edge, a later copy does not take it, and neither the chain's end nor a copy on the busy path answers ACK because the node holds the edge, which it may by a later transfer from the same sender. The first form, R2', answered ACK in that case (`took = ... or _explicit[e] is True`); the Lean search of 5d9936a found a 21-event run in which the cache then held ACK for a request already refused and both ends held e. The late acknowledgement of F10 is therefore never sent, and the sender's NACK and the receiver's state agree. `_finish_push_job`, `_on_push`, `_refuse`.
- R3, a copy is answered as its request was (corrects F14). A repeated HANDOVER or PUSH that missed the reply cache is acknowledged only if the receiver holds the edge and its edge count (G7) equals the count the request carries plus one, the state that accepting this request left; otherwise it is refused. The state lasts until the sender reads an answer, because the sender has one open transfer per neighbour (F14b) and G7 refuses every other transfer of the edge between the two ends until then. F7's refusal path applies the same rule: it replays a cached reply, and without one answers by R3, instead of refusing unconditionally. `_repeat_ok`, `_on_handover`, `_on_push`, `_refuse`.
- R4, only a successful acceptance counts. In `_accept_edge` the room test comes first; the retraction of my own offer, the take count theta(e) and the `_retake_seq` stamp are made only on the success branches. A refusal for lack of room changes none of them. `_accept_edge`.
- The yield rule of the code is stated in the manuscript (text repair for `traceNoYield`); no code change.

The five rules of the one-owner theorem. The Lean worker proved one ownership of every flexible edge in every quiet state of the transfer layer from five rules together, and showed each necessary: dropping any one of them gives a counterexample. (1) The yield rule `_yields_to_inbound` (`_loses_race`): an end with its own open request for e refuses an incoming one iff its key is smaller. (2) The theta floor on the late-acknowledgement path (`_retake_seq` in `_on_late_ack`, the post-freeze correction of commit a52ed25), kept exactly as on main. (3) R2''. (4) R3. (5) R4. The manuscript states all five in Algorithm `alg:ownership` and in the proof of Theorem 3(b). The proof models R2'' as registered here (a refused request is answered NACK for ever), not the no-reply form first proposed; with the five rules the Lean search of the code is clean (455 000 states at K = 1, L = 3 and 7.39 million at K = 2, L = 2), and without R4 it finds 140 bad quiet states.
Why not the form first proposed (a copy of a running chain gets no reply). It was implemented and measured on development data before this amendment (the patches are kept outside the registered files and are not part of any version): with no reply the sender keeps its request open, the chain becomes an exhaustive depth-first search, and the development tests time out (M9 generator, development seed 1, n = 25, k = 6, infeasible: truncated at 7 000 000 ms instead of unresolved after F17b; the F11 and F17 tests did not finish in 25 minutes against 81 s). Bounding that search by the sender's copies (first copy, or R_max copies) ends the runs but loses the m = nk development instance and changes the F17 wave count. R2'' as registered is the smallest form that keeps the timeout pruning of the frozen code and removes the late acknowledgement.

Known cost, measured on development data before this amendment, on R2 and R3 (d61d935edce3) and confirmed by the suite on 026c2dc5f381. The frozen code solved the development instance n200_m1200_s6 (k = 6, m = nk) through 129 late acknowledgements; under R2 the run ends unresolved with one overloaded node, no double claim, in 1 127 800 ms instead of 196 800 ms with 38 079 retransmissions instead of 2129. On udg_instance(100, 0.15, 4), k = 4, synchronous, the run is solved with |C| = 90 in 23 200 ms instead of 194 600 ms without the relayed invitation of F11b. The amendment's endpoints therefore include verdict changes, not only validity.

Acceptance on development, before any run below:
- regression tests in ccvc/bb/test_r2r3.py driving the handlers through `traceNoYield`, `traceBusy`, `traceRepeat` and the R4 sequence and asserting one owner per edge at the end, plus the F7 path of R2 and R3; `traceBusy`, `traceRepeat` and the F7 tests fail on 54fcf00c82b5 and pass on 026c2dc5f381; the R4 test ends with two owners on 54fcf00c82b5 and on 5d9936a and passes on 026c2dc5f381; the R2'' test (a refused PUSH answered ACK after a later HANDOVER of the edge was accepted) gets PUSH_ACK on 5d9936a and PUSH_NACK on 026c2dc5f381;
- the full ccvc/bb suite with the development data present: 1328 passed, 2 failed, 3 skipped on 026c2dc5f381; the two failures (test_hga_ref, the pinned upstream solver file is absent from the release tree) fail on 54fcf00c82b5 as well. Outside ccvc/bb, 74 tests fail on both versions (missing result files), so the count does not grow. Existing tests changed: test_r1_repairs2 F10 (two tests rewritten, one deleted: they asserted F10's late acknowledgement, the mechanism of `traceBusy`), F11 on n200_m1200_s6 (now records unresolved with no double claim, see the known cost), F11b on udg_instance(100, 0.15, 4) (the relay is no longer needed there; the solved, valid, |C| = 90 assertions stay), and test_r1_f14's lossy audit (seed 5 added, because the evicted-copy case no longer occurs on seeds 0, 6, 14 and 1, as in the note to Amendment 15);
- no other acceptance run. In particular no held-out, reserve or Mininet-WiFi run of 026c2dc5f381 exists when this amendment is committed.

Deviation from section 1, stated. Section 1 evaluates a repair on the sealed reserve set, and Amendment 16 used the reserve set once. No sealed set is left. R2R3 is evaluated on the held-out sets that already exist, paired against the frozen rows on the same jobs. Its rules come from the Lean model and from development data, not from held-out rows, and nothing is tuned on the rows below. The held-out sets were seen by the frozen version only.

Experiment. Version R2R3-repair runs from a snapshot of an annotated tag coverweave-r2r3-repair (fingerprint 026c2dc5f381); the frozen rows of results/bb/r1 are the comparison and are not rerun. Every one of the 25 configurations is a BbcvcNode subclass and shares the transfer handlers, so all configurations run. Jobs are the frozen job lists with only `id` (prefix A17-) and `out` (under results/bb/a17/<block>/parts) changed; instance, k, loss, rng_seed, configs, max_ms and params are identical, so every repaired row pairs with one frozen row.
- S1 lossless held-out: M3 (H1 and H1-large, 4200 runs), M4 (H2a and H2b, 4000), M5 (capacity sensitivity, 4400), M9 (500). 13 100 runs.
- S2 loss: M6 at channel seed 1 only (3300 runs, the seven lossy conditions, the empirical condition and the F9-off ablation as frozen), and M6emp (900). Channel seed 1 is the choice of Amendment 16 for the lossy reserve runs; the other two seeds are not run.
- M7 Mininet-WiFi: the 87 jobs of the frozen M7 (27 development runs and set W with three arms), serial, run_m7.sh with M7_TAG.
For the seven configurations that Amendment 16 changed (Anneal-Local, Anneal-TreeAgg and GHS-MST-Backbone under both schedulers, Anneal-Trickle async) the pair compares the frozen version with R1-repair plus R2R3 and is reported as that combined change; R2R3 alone is attributed only on the other 18 configurations, whose code paths Amendment 16 showed identical between the frozen version and R1-repair (lossless development identity).

Commands (from the release repository root; the live tree is ~/Desktop/MDS_SKYFABRIC).
1. Tag and snapshot: `git tag -a coverweave-r2r3-repair -m "R2R3-repair, amendment 17, fingerprint 026c2dc5f381" r2r3-repair`; `mkdir -p ~/Desktop/MDS_SKYFABRIC/results/bb/a17/_snap && git archive coverweave-r2r3-repair | tar -x -C ~/Desktop/MDS_SKYFABRIC/results/bb/a17/_snap`; check `cd _snap && python3 -c 'from ccvc.bb import sweep; print(sweep.code_fingerprint())'` prints 026c2dc5f381.
2. Job lists: `python3 results/bb/a17/make_jobs.py` in the live tree (git blob b97c3e91fb77e3e17b8ac74f5150cb6ff39e38b6, committed in 9ec51cbfa417 of the live-tree repository before this amendment). For B in M3 M4 M5 M9 M6 M6emp it reads results/bb/r1/B/jobs.jsonl and writes results/bb/a17/B/jobs.jsonl with `id = "A17-" + id` and `out = results/bb/a17/B/parts/<basename of out>`, keeping, for M6 only, the lines with `rng_seed == 1`, and it refuses to overwrite a job list. It runs once, after this commit.
3. Simulator pools, one block at a time, the whole pool under one cap: `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 env SNAP=$HOME/Desktop/MDS_SKYFABRIC/results/bb/a17/_snap R1_FROZEN_FINGERPRINT=026c2dc5f381 WORKERS=W bash results/bb/r1_dryrun/run_pool.sh $HOME/Desktop/MDS_SKYFABRIC/results/bb/a17/B`. r1_run refuses any other fingerprint, and a killed pool resumes.
4. M7: `M7_TAG=coverweave-r2r3-repair R1_FROZEN_FINGERPRINT=026c2dc5f381 bash ccvc/bb/mnwifi/run_m7.sh --w-set ~/Desktop/MDS_SKYFABRIC/results/bb/r1/instances/W --dataset ~/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset --out ~/Desktop/MDS_SKYFABRIC/results/bb/a17_m7` (run_m7.sh reads the tag from M7_TAG; its default stays the frozen tag; a separate --out keeps the frozen snapshot and rows apart). Needs an idle host: no simulator pool, Lean or Isabelle build at the same time.
5. Statistics: `python3 results/bb/a17/analyse.py` in the live tree (git blob 7890cd811d3988fc151e14cb37e70b2cb2755d67, commit 9ec51cbfa417 of the live-tree repository, made before any repaired row existed). It implements H17-a to H17-e below with the tests of ccvc.bb.revision_stats, writes results/bb/a17/LEDGER.md and marks the ledger PRELIMINARY while a repaired job has no .done marker. It was tested only by a dry pairing of the frozen rows of results/bb/r1 and results/bb/r1_m7 against themselves (23 487 paired runs, every test all-tied, no ownership violation, H-a 17 false successes as registered in Amendment 16). Repaired rows without a frozen partner are counted and not analysed.

Time and memory, estimated from the `seconds` column of the frozen rows (time of one process per run) and from peak resident memory measured on development instances.

| Block | Runs | Frozen CPU hours | Longest frozen run | Largest n | Wall time at W = 8 |
|---|---|---|---|---|---|
| M3 | 4200 | 19.7 (H1-large n = 1000: 14.0) | 2.8 h | 1000 | about 3 h (sum / 8, the longest run fits) |
| M4 | 4000 | 20.5 (n = 200: 18.4) | 7.3 h | 200 | about 7.5 h, set by its longest run |
| M5 | 4400 | 1.7 | 48 s | 100 | about 15 min |
| M9 | 500 | 2.2 | 81 s | 50 | about 20 min |
| M6, seed 1 | 3300 | 146.6 (one third of 439.8) | 52 min | 100 | about 18.5 h |
| M6emp | 900 | 0.8 | 88 s | 100 | about 10 min |
| M7 | 87 | 4.2 inside the runs, serial | 10 min | 50 | about 6 to 8 h with the idle waits |

Memory. Peak resident memory of one run, measured on development seed 1 of the generator (not a registered seed) at d61d935edce3 (R2 and R3, before R4; R4 adds no state), asynchronous MIS-connector arm: H1 n = 100, m/n = 4, lossless 32 MB and loss 0.1 32 MB; H1 n = 200 lossless 37 MB; H1-large n = 1000 lossless 82 MB (138 s); H1 n = 100 at ge:0.20:4 60 MB. Memory grows with the run's event log, so a run that reaches its limit holds more; 0.5 GB per run is taken as the planning bound. The whole pool runs in one scope with MemoryMax=6G and MemorySwapMax=0, so W = 8 workers (8 x 0.5 GB = 4 GB, plus about 1 GB for the pool, the interpreter start-up and the shell) fits with a margin, on 16 cores shared with the Lean and Isabelle builds. If the scope is killed, the pool loses only the runs in flight and resumes with W = 4. S1 and S2 run one after the other, never together, and not while M7 runs. Total about 30 h of simulator wall time plus M7.

The estimates assume the repaired version costs what the frozen version cost. On development data R2 can cost more (the m = nk instance took 5.7 times the simulated time). A block is not stopped for time: a run that hits its registered limit counts as truncated, as in section 5.

Endpoints, all per block and per configuration, paired by job file and configuration (M7: block, instance, configuration and channel seed): (1) ownership violations in runs that end solved: `double_claims > 0`, or the validator's owner class `bad_owner` (an edge without a valid owner, an unowned edge included) in a run that is not valid on its final discovered graph. `violation_kinds` is the planned-graph reading, so a lossy or wireless run whose discovered graph differs reports `bad_owner` for edges outside the planned graph; it is judged on the discovered graph (Amendment 4), and an invalid discovered reading counts its planned kinds, which can only overcount. (2) Validity rate: solved and valid on the final discovered graph (Amendment 4; a lossless run discovers the planned graph); (3) false successes (solved and rejected by the validator; H-a); (4) verdict (solved, unresolved, infeasible, truncated); (5) tx; (6) t_conv.

Hypotheses and decision rules, fixed before any repaired row exists.
- H17-a, safety. No repaired run that ends solved has an ownership violation or a double claim. Count over all S1, S2 and M7 runs, with the one-sided 95 percent Clopper-Pearson upper bound. The same count is reported for the frozen rows.
- H17-b, validity is not lower. Per block, McNemar's exact test on the paired runs (valid in one version only), one-sided for a decrease, Holm over the blocks at 0.05. Holds if no block shows a significant decrease.
- H17-c, false successes. The count of the repaired version per block, next to the frozen count, with Clopper-Pearson bounds; H-a is re-evaluated on the repaired rows with the procedure of section 7. Descriptive comparison, no test.
- H17-d, verdicts. Per block, the paired table of verdicts; McNemar's exact test, two-sided, for solved against not solved, Holm over blocks. The test is made on the runs outside the m = nk cells, and the same table and test on the m = nk cells alone where a block has any, since R2'' is known to lose one m = nk development instance.
- H17-e, cost. Paired change of tx and of t_conv per unit (block, instance file, loss, parameters, configuration), channel seeds averaged first, runs valid in both versions; Wilcoxon signed-rank with Pratt zeros, two-sided, Holm over blocks, rank-biserial r and the median of repaired over frozen with a bootstrap 95 percent interval (10 000 resamples). Descriptive, no accept rule.
- Decision. R2R3 is accepted, and Theorem 3(b) is stated for it with the yield rule in the text, if H17-a and H17-b hold. Results are reported next to the frozen results in the manuscript and the response letter whichever way they fall.

What is reported if a rule fails.
- H17-a fails: every such run is listed with its job, the version stays reported as not accepted, and Theorem 3(b) is not claimed for the code. The run is analysed for cause on its own, and any further repair is a new amendment with its own acceptance; nothing is tuned on these rows.
- H17-b fails: the decrease is reported per block with its runs. Theorem 3(b) is claimed for R2R3 only if H17-a holds, with the validity loss stated next to it as the price of the repair.
- H17-d shows fewer solved runs: reported as a quality loss of R2, with the count of unresolved runs that the frozen version solved and how many of those used F10's late acknowledgement (`late_ack_release` in the frozen logs where kept). Not repaired on these rows.
- A run that crashes or a job that fails keeps its row as failed, as in section 5.

Not run, stated. M8, the bridge ablation, the reserve set, M6 channel seeds 2 and 3, and the development set M2 at the repaired version. The Lean proof of the five-rule theorem is reported with its own statement and is not part of this experiment.

Committed 2026-11-26T20:59:20+03:00, before any run of 026c2dc5f381 and before its job lists exist. Code: branch r2r3-repair of the release repository, tag coverweave-r2r3-repair. Analysis and job builder: live-tree commit 9ec51cbfa417.

### Amendment 18, 2026-11-27, after the M7 runs of Amendment 17 and before any run of the harness below. A collector and harness defect in how the wireless backend decides convergence, and a measurement repair.

Finding, reported as found. Hypothesis H17-a of Amendment 17 failed on one run of block M7, the repaired run `m7_W_mst_n50_m150_s404` with GHS-MST-Backbone under the synchronous scheduler at n = 50. Its row reads verdict solved, converged True, status contradiction, cover size 0, no double claim, 101 of the 150 planned edges missing from the discovered graph and 17 extra links. The frozen run of the same job is solved and valid. The station logs show that the run never converged. At the end of the run every one of the 50 stations reports `done` false, role OUT, no owned edge and epoch 16. Every station restarted 16 times, which gives 800 `reset_phase0` records. The last `epoch_bump` came at 589 355 ms, 10.7 s before the run limit of 600 000 ms, and it restarted the whole network. Every station then wrote its `deadline` record at about 600 024 ms. The orchestrator never saw quiescence and stopped only at its own limit, at 616 061 ms. The empty cover is therefore a true reading of a network in the middle of a restart, and the run should have been labelled truncated.

Why the row said solved. The collector in `ccvc/bb/mnwifi/collect.py` kept the first `node_done` record of each station and, for a station without one, the station's own `done` event as a fallback, and it called a run converged as soon as every station had one such stamp. It never read the final state in `run_end` and never looked at restarts that came after a stamp. In this run 41 stations had a `node_done` record, written between 187.1 s and 490.5 s, and the other 9 stations counted only through their own `done` event. That event marks the entry into phase DONE, which is weaker than the `done` property that the scheduler reads, because the property also waits for the closing barrier and, for a backbone station, for the finished tree. The stamps came from different epochs. In no epoch were more than 39 stations done, yet the stamps added up to 50, so the collector reported convergence after 2668 slots. The orchestrator had a related defect. Its stop rule in `ccvc/bb/mnwifi/run.py` read the first `node_done` of each station, and `ccvc/bb/mnwifi/node_main.py` wrote that record only once per process. A run whose stations had each been done once in some epoch could therefore be stopped while they ran a new one. In this run that did not happen only because 9 stations never wrote a `node_done`. The simulator does not share the defect, since `sched.py` calls a run converged only when all nodes are done in the same slot with no frame in flight.

The defect is present in both versions. The collector, the row builder `m7.py`, the orchestrator `run.py`, the station process `node_main.py`, the bootstrap layer and the GHS-MST arm are byte identical in the snapshots of coverweave-r1-frozen and coverweave-r2r3-repair. Amendment 17 changed only `ccvc/bb/bbcvc.py`, and only its transfer handlers. Applied to the existing logs, the rule below changes none of the 78 converged frozen M7 rows and one of the 83 converged repaired M7 rows, the row above. The frozen M7 rows show no such run because no collapsed frozen run accumulated a stamp for all 50 stations. The frozen run `m7_W_mst_n50_m150_s401` reached 25 of 50 and ended truncated.

The run is not an ownership defect. No edge of the run is owned by any station at its end, so no edge is owned twice and no station holds an edge that another station also claims. The validator kind `bad_owner` comes only from the 150 planned edges that have no owner.

Why 101 planned edges were missing. The discovered graph is read from the links that each station counts as verified in its `run_end` record. A restart clears every verified link and starts every LINK handshake again at the same moment. In the 10.7 s after the last restart the stations sent 1344 LINK frames and 472 LINK_ACK frames, and 66 mutual links were verified when the run ended, 49 planned and 17 extra, against 188 before. Every collapsed run at n = 50 in both versions ended at its limit with its last restart within 40 s of the end. These are 6 frozen runs, one of which is a host failure with empty station logs, and 4 repaired runs. Runs that reached the limit with their last restart 84 s or more before the end did not collapse. The median HELLO RSSI was the same in every minute of both s404 runs, at minus 82 dBm, and neighbour expiries and restarts came at similar rates in both versions. The frames added by R2'' were 0.57 percent of all frames sent in the repaired run, against 0.34 percent for the frozen run of the same job. The collapse is therefore a property of the moment at which the graph is read, not of the repair.

Repair, a measurement repair registered before any data it produces. Branch m7-collector of the release repository, made from r2r3-repair at commit 6e5d9f1. The commit that appends this amendment carries the annotated tag coverweave-r2r3-repair-m7h. Three harness files change, and no file of the algorithm.
1. `collect.py`. A run is converged only when the latest done record of every station is `node_done`, not followed by `node_undone`, when the `run_end` record of every station reports `done` true, and when no station wrote `reset_phase0` or `epoch_bump` after the latest stamp. The fallback to the station's own `done` event is removed. The stamp of each station is its latest `node_done`, and the slot count, t_conv and radio-on time are computed from it as before.
2. `node_main.py`. The station process writes `node_done` on every entry into done and `node_undone` on every exit from done, both stamped at the end of the slot. The last such record of a station therefore states whether its latest state is done.
3. `run.py`. The orchestrator stops on quiescence only when the latest done record of every surviving station is `node_done` and no surviving station restarted after the latest stamp, and then only after the three quiet slots of the existing rule.

Fingerprints. The code fingerprint of `sweep.code_fingerprint` stays 026c2dc5f381, because it covers the measurement modules of the simulator and none of the harness files. Rows of the new harness therefore carry the same `code_fingerprint` as the rows of Amendment 17. The wireless fingerprint that the harness writes into `run.json` and that the rows carry as `wifi_fingerprint` changes from 547470f07af42e980413b4a0b444a2b99c4da03caa0cc24e9614a8d9245154b7 to 302a66d05649fb95d7beddc9e9ca2e55ebaccb3b0a73cfe74ac4e216b9d733f5. That fingerprint also covers `ccvc/greedy`, whose test fixture changes as stated below. `ccvc/bb/bbcvc.py`, `ccvc/bb/bootstrap.py` and `ccvc/bb/v4_mst.py` are unchanged.

Acceptance on development, before any run below. Four regression tests are added. In `ccvc/bb/test_mnwifi_m7.py` the first rebuilds the run above in miniature: two stations stamped done, a third with only its own `done` event, then a restart of all three and a final state with no station done. The second checks that a station which left done and came back counts from its latest stamp, and that a restart after the latest stamp or a final state that is not done is not convergence. In `ccvc/bb/test_mnwifi.py` the third checks the stop rule of the orchestrator with a station that restarts after its stamp, and the fourth drives the station process through done, not done and done again and checks the records it writes. All four fail on coverweave-r2r3-repair and pass on the repaired harness. Three fixtures change because the final state is now read: the synthetic `run_end` records in `test_mnwifi.py`, `test_mnwifi_m7.py` and `ccvc/greedy/test_greedy.py` gain `done` true, as every `run_end` written by `node_main.py` already has. With the development data present, the suites ccvc/bb and ccvc/greedy give 1368 passed, 4 skipped and 0 failed on coverweave-r2r3-repair, and 1373 passed, 3 skipped and 0 failed on the repaired harness. Four of the five additional passes are the new tests. The fifth is `test_report_pipeline`, which needs files outside ccvc and therefore ran only in the full checkout of the repaired branch, not in the export of the old tag. Without the development data both versions fail the same 9 tests, which read the dataset, the pinned upstream source or the untracked hello-delivery script. The re-derivation script below was run on the 57 rows with n at most 30 of each version and reproduced every cell of the existing rows. A row at n = 50 needs more than 3 GB, so its re-derivation waits until no simulator pool runs.

Readings of block M7.

Reading a, as registered. The rows of results/bb/r1_m7 and results/bb/a17_m7 and the ledger of Amendment 17 stay reported as they are. In that reading H17-a fails on M7 by one row, and R2R3-repair is not accepted.

Reading b, secondary. The repaired collector is applied to the existing station logs of both versions by `results/bb/a17/rederive_m7.py`, which writes `m7_rows_a18.csv` and a sidecar `m7_rows_a18.json` beside each `m7_rows.csv`, never over it, and refuses to write rows if any cell outside converged, verdict, status, truncated, slots and t_conv_ms changes. Both arms are read by the same collector and were run by the same harness, so the pairing of frozen and repaired rows stays fair. The outcome of this reading was known before this amendment: the rule was checked on the raw logs during the diagnosis and changes one row, the row above, which becomes truncated. For that reason reading b is not confirmatory. It is reported next to reading a for H17-b, H17-c and H17-d on M7. Rows of stations that restarted after their first `node_done` keep that first stamp, because the old harness wrote no later one. This affects 15 frozen and 11 repaired converged rows, so t_conv and radio-on time on M7 in reading b can understate the time to quiescence.

Confirmatory test, block M7b. The 87 jobs of the repaired M7 are run again with the repaired harness and collector from a snapshot of tag coverweave-r2r3-repair-m7h, with algorithm fingerprint 026c2dc5f381, into results/bb/a18_m7b. Instance, k, arm, scheduler, limit and channel are those of the M7 jobs. H17-a is judged on S1, S2 and M7b, with the count and the one-sided 95 percent Clopper-Pearson upper bound of Amendment 17, and holds if the count is 0. H17-b and H17-d on M7 are those of reading b. M7b is paired with the frozen rows of reading b and reported descriptively for validity, false successes, verdicts, tx and t_conv, since its arms ran under different stop rules. R2R3-repair is accepted if H17-a holds on S1, S2 and M7b and H17-b holds on S1, S2 and M7 in reading b. Whichever way it falls, both readings and M7b are reported in the manuscript and the response letter.

Not run, stated. The frozen M7 is not run again. The safety hypothesis concerns the repaired version, and the frozen rows serve only as its comparison, which reading b provides with the same collector in both arms. The new stop rule changes only when a run is stopped. In every converged frozen M7 row every station reports done in its final state, so the new rule would have stopped none of them earlier. A new frozen run would be a new random sample of the emulation and not a correction of the old one, at the cost of 6 to 8 h of an idle host. The development runs of the frozen M7 are not run again for the same reason.

Limitation, stated and not repaired here. Both versions share a liveness weakness. A station whose set of verified links stays changed for one stability window raises the epoch, and the new epoch spreads to the whole network and restarts it. Under the contention of 50 stations this happens again and again. At n = 50 the frozen version ended 8 runs at their limit after repeated restarts, besides one host failure, and the repaired version 5, counting the run above. The same restarts explain every collapsed discovered graph. It is a property of the bootstrap layer, not of the transfer handlers, and in the M7 rows it creates no false success once convergence is read correctly. Damping restarts would change the algorithm and needs its own amendment with a new run of S1, S2 and M7. It is reported as a limitation of the wireless results.

Commands, from the release repository root, the live tree being ~/Desktop/MDS_SKYFABRIC.
1. Tag and snapshot: `git tag -a coverweave-r2r3-repair-m7h -m "R2R3-repair with the M7 collector and harness of amendment 18, fingerprint 026c2dc5f381" m7-collector`. Then `mkdir -p ~/Desktop/MDS_SKYFABRIC/results/bb/a18/_snap && git archive coverweave-r2r3-repair-m7h | tar -x -C ~/Desktop/MDS_SKYFABRIC/results/bb/a18/_snap` and check that `cd ~/Desktop/MDS_SKYFABRIC/results/bb/a18/_snap && python3 -c 'from ccvc.bb import sweep; print(sweep.code_fingerprint())'` prints 026c2dc5f381.
2. Reading b, after S2 and with no pool running, in the live tree: `systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 python3 results/bb/a17/rederive_m7.py --code ~/Desktop/MDS_SKYFABRIC/results/bb/a18/_snap`, then `python3 results/bb/a17/analyse.py --frozen-m7 results/bb/r1_m7/m7_rows_a18.csv --repaired-m7 results/bb/a17_m7/m7_rows_a18.csv --out results/bb/a17/LEDGER_A18b.md`.
3. M7b, on an idle host with no simulator pool, Lean or Isabelle build, in the live tree: `M7_TAG=coverweave-r2r3-repair-m7h R1_FROZEN_FINGERPRINT=026c2dc5f381 bash ccvc/bb/mnwifi/run_m7.sh --w-set ~/Desktop/MDS_SKYFABRIC/results/bb/r1/instances/W --dataset ~/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset --out ~/Desktop/MDS_SKYFABRIC/results/bb/a18_m7b`. The script makes its own snapshot of the tag under the output directory and refuses another tree there.
4. Statistics for M7b: `python3 results/bb/a17/analyse.py --frozen-m7 results/bb/r1_m7/m7_rows_a18.csv --repaired-m7 results/bb/a18_m7b/m7_rows.csv --out results/bb/a17/LEDGER_A18_M7b.md`. H17-a is read from this ledger over S1, S2 and M7b, and its M7 tables are the descriptive M7b comparison.

Committed 2026-11-27 15:43 +0300, before any run of the harness of coverweave-r2r3-repair-m7h and before any row of reading b exists. No S2 row was read for this amendment. Code: branch m7-collector of the release repository, tag coverweave-r2r3-repair-m7h. Re-derivation script: results/bb/a17/rederive_m7.py in the live tree, commit 4b1e973d7b7f of the live-tree repository.

### Amendment 19, 2026-11-27 16:28 +0300, after 20 of the 660 jobs of block M6 finished and before any row of S2 was read. Block M6 and block M7b are stopped, block M6emp is run in full.

Decision. The authors stop the lossy block M6 of S2 and the confirmatory wireless block M7b of Amendment 18 for time. After the pool was cut to four workers by its memory cap and the CPU boost was switched off to keep the host below its thermal limit, M6 alone was estimated at about 44 hours, and M7b adds about 10 hours on an idle host. The decision was taken before any row of S2 was opened, and no statistic of S2 has been computed. The 20 finished M6 jobs and the runs cut off in flight are kept on disk and are not analysed or reported as evidence, so that no part of the stopped block can enter the result selectively.

What runs. Block M6emp of S2, the 900 runs on the measured empirical loss condition of Amendment 17, in full, with the pool of Amendment 17 at four workers under a memory cap of 12 GB. The cap and the worker count guard the host and change no run.

Evidence for the repair, as it now stands. The repair of Theorem 3(b) rests on the Lean proof for the whole network under rule R2'' (`thm3b_transfer_r2pp`, `ctl_phase4_window`), on S1, on M6emp and on M7.
1. H17-a, safety, is judged on S1 and M6emp, with the count and the one-sided 95 percent Clopper-Pearson upper bound of Amendment 17, and holds if the count is 0.
2. H17-b, validity, is judged on S1 and M6emp with the tests of Amendment 17.
3. M7 is reported in reading a, as registered, where H17-a fails by one row, and in reading b of Amendment 18, which applies the repaired collector to the logs of both versions. Reading b was not confirmatory, since its outcome was known when Amendment 18 was written, and it is reported as such.
4. R2R3-repair is accepted if H17-a and H17-b hold on S1 and M6emp. The wireless result then stands as reading a and reading b of M7 without a confirmatory run, and the manuscript says so.

Not run, stated. M6 at channel seed 1 beyond the 20 finished jobs, and M7b. The lossy evidence is therefore one measured loss condition and not the seven synthetic conditions of M6, and the wireless evidence has no run under the repaired harness. Both are stated as limitations in the manuscript and in the response letter.

Commands, in the live tree ~/Desktop/MDS_SKYFABRIC.
1. M6emp: `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0 env SNAP=$HOME/Desktop/MDS_SKYFABRIC/results/bb/a17/_snap R1_FROZEN_FINGERPRINT=026c2dc5f381 WORKERS=4 bash results/bb/a17/_snap/results/bb/r1_dryrun/run_pool.sh $HOME/Desktop/MDS_SKYFABRIC/results/bb/a17/M6emp`.
2. Ledger: `python3 results/bb/a17/analyse.py --exclude M6 --out results/bb/a17/LEDGER_A19.md` for S1, M6emp and M7 in reading a, and `python3 results/bb/a17/analyse.py --exclude M6 --frozen-m7 results/bb/r1_m7/m7_rows_a18.csv --repaired-m7 results/bb/a17_m7/m7_rows_a18.csv --out results/bb/a17/LEDGER_A19b.md` for M7 in reading b, after `rederive_m7.py` of Amendment 18 has written the a18 rows.

Committed 2026-11-27 16:28 +0300, before any row of S2 was read. Analysis option `--exclude`: commit d314e7bffedd of the live-tree repository.

### Amendment 20, 2026-11-28 17:59 +0300, a correction of a factual statement in Amendment 17, after all runs and ledgers of Amendments 17 to 19. No run, hypothesis, endpoint or decision rule changes.

Finding. Amendment 17 says that R2R3-repair was built "on top of R1-repair and the post-freeze late-acknowledgement correction (main at commit ec40190, fingerprint 54fcf00c82b5)", and that for the seven configurations changed by Amendment 16 the pair "compares the frozen version with R1-repair plus R2R3 and is reported as that combined change". Both statements are false. Commit ec40190 of main is the frozen version plus the late-acknowledgement correction a52ed25 only, and the R1-repair commit b1481df (tag coverweave-r1-repair) is not an ancestor of coverweave-r2r3-repair. The files that R1-repair changes (ccvc/bb/anneal.py, v4_mst.py, wire.py, api.py) have the same content in the frozen version, in coverweave-r2r3-repair and in main, and a different one at coverweave-r1-repair. The fingerprints are 09af268d95e0 frozen, aedb4a3287bc R1-repair, 54fcf00c82b5 for ec40190 and 026c2dc5f381 for R2R3-repair. The repaired S1 rows also keep the 15 M4 and 1 M5 false successes of the frozen version that R1-repair removed.

Consequence. R2R3-repair is the frozen version plus the late-acknowledgement correction and the five rules of Amendment 17, and nothing else. Every pair of Amendments 17 to 19, the seven configurations of Amendment 16 included, compares the frozen version with that version alone, so every difference reported in the ledgers is attributed to R2R3-repair. No effect of R1-repair enters them. The manuscript names this version R2-repair, with public tag coverweave-r2r3-repair, and R1-repair keeps its own tag coverweave-r1-repair.
