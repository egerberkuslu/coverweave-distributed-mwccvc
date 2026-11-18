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
