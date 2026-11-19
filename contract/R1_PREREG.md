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
