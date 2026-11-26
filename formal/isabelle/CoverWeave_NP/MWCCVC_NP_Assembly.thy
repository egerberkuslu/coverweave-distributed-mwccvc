theory MWCCVC_NP_Assembly
  imports MWCCVC_Verifier_Spec Cook_Levin.Reduction_TM
begin

section \<open>From Turing machines to NP-completeness\<close>

text \<open>
The two lemmas below turn a polynomial-time Turing machine for the verifier function and one
for the reduction function into membership in \<open>\<N>\<P>\<close> and a polynomial-time reduction from
\<open>SAT\<close>. The machines themselves are constructed in \<open>TM_Verify\<close> and \<open>TM_Reduce\<close>.
\<close>

lemma MWCCVC_in_NP_from_TM:
  assumes "turing_machine k G M" and "big_oh_poly T"
    and "computes_in_time k M (\<lambda>z. symbols_to_string (verify_mw (string_to_symbols z))) T"
  shows "MWCCVC \<in> \<N>\<P>"
proof -
  define f where "f = (\<lambda>z. symbols_to_string (verify_mw (string_to_symbols z)))"
  have "x \<in> MWCCVC \<longleftrightarrow> (\<exists>u. length u = p_cert (length x) \<and> f \<langle>x, u\<rangle> = [\<bbbI>])" for x
  proof -
    have "f \<langle>x, u\<rangle> = [\<bbbI>] \<longleftrightarrow> verify_mw \<langle>x; u\<rangle> = [\<one>]" for u
    proof -
      have "verify_mw \<langle>x; u\<rangle> = [\<one>] \<or> verify_mw \<langle>x; u\<rangle> = []"
        unfolding verify_mw_def Let_def by simp
      then show ?thesis
        unfolding f_def by auto
    qed
    then show ?thesis
      using verify_mw_NP by simp
  qed
  then show ?thesis
    unfolding complexity_class_NP_def
    using assms polynomial_p_cert f_def by blast
qed

lemma SAT_reducible_from_TM:
  assumes "turing_machine k G M" and "big_oh_poly T" and "computes_in_time k M sat_red T"
  shows "SAT \<le>\<^sub>p MWCCVC"
  unfolding reducible_def using assms sat_red_correct by blast

lemma MWCCVC_NP_complete_from_TMs:
  assumes "turing_machine k1 G1 M1" and "big_oh_poly T1"
    and "computes_in_time k1 M1 (\<lambda>z. symbols_to_string (verify_mw (string_to_symbols z))) T1"
  assumes "turing_machine k2 G2 M2" and "big_oh_poly T2" and "computes_in_time k2 M2 sat_red T2"
  shows "NP_complete MWCCVC"
  using NP_complete_reducible[OF NP_complete_SAT] MWCCVC_in_NP_from_TM[OF assms(1-3)]
    SAT_reducible_from_TM[OF assms(4-6)]
  by simp

end
