theory MWCCVC_NP_Complete
  imports CoverWeave_Reduce.TM_Reduce CoverWeave_Verify.TM_Verify
begin

section \<open>Decision MWCCVC is NP-complete\<close>

text \<open>
Source: CoverWeave R1 manuscript, Definition \<open>def:mwccvc\<close> and the first sentence of Theorem
\<open>thm:hardness\<close> with its proof sketch (sections/04-formaleng.tex). Lean counterparts:
\<open>Ownership.lean\<close> (valid pairs, \<open>exists_validPair_iff_of_maxDegree_le\<close>) and
\<open>CheckRuntime.lean\<close> (certificate check).

The base is the AFP entry Cook_Levin (Balbach): languages over \<open>bool\<close> strings, \<open>\<N>\<P>\<close> by
polynomial-time verifier Turing machines, \<open>\<le>\<^sub>p\<close> by polynomial-time transducer Turing machines,
and @{thm NP_complete_SAT} proved there down to the Cook-Levin construction.

Modelling choices.
\<^item> The decision version asks for a valid pair \<open>(C, owner)\<close> with \<open>w(C) \<le> B\<close>
  (@{const mwccvc_yes}); the bound \<open>B\<close> is part of the instance. Weights are positive
  naturals, the capacity \<open>k\<close> is a natural number.
\<^item> The input graph is not required to be connected. The hardness instances are connected
  (they contain a hub adjacent to every other vertex), so hardness also holds for the
  connected restriction; membership in NP holds for the general language and hence for the
  restriction, as connectivity of the input is checkable in polynomial time.
\<^item> Instances are encoded as Cook_Levin lists of lists of numbers \<open>[[k, B], w, edge pairs]\<close>
  (@{const MWCCVC}). A certificate lists the slack \<open>d\<close> of the weight bound, a start vertex
  \<open>c\<^sub>0\<close> and edge indices that grow \<open>C\<close> along edges of \<open>G[C]\<close> (connectivity), then for each
  vertex the far endpoints of the edges it owns (the owner map and the loads); it is padded
  with \<open>\<bar>\<close> to the fixed certificate length (@{const verify_mw}).
\<^item> Hardness chain (machine-checked as one polynomial-time transducer, @{const tm_red}):
  CNF SAT to Independent Set (Karp's clause gadget, @{thm sat_iff_independent}), to Vertex
  Cover by complement, to Connected Vertex Cover by adding a hub (@{thm hub_cvc_iff}), to
  MWCCVC with unit weights and \<open>k = N \<ge> \<Delta>\<close> (@{thm valid_pair_iff_cvc}); the composite is
  @{thm sat_iff_mwccvc_gadget}.
\<close>

theorem MWCCVC_NP_complete: "NP_complete MWCCVC"
  using NP_complete_reducible[OF NP_complete_SAT MWCCVC_in_NP SAT_reducible_MWCCVC] .

end
