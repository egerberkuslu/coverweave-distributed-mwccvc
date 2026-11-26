theory MWCCVC_Verifier_Spec
  imports MWCCVC_Language
begin

section \<open>A polynomial certificate for MWCCVC\<close>

text \<open>
Source: proof of Theorem \<open>thm:hardness\<close>, first sentence: a valid pair is checked in
polynomial time, so the decision version lies in NP. Lean counterpart: \<open>checkValid_correct\<close>
and \<open>checkValid_steps_le\<close> (CheckRuntime.lean), which check a given pair \<open>(C, owner)\<close>.

Here the certificate is designed so that a Turing machine can check it with list operations
only. It is a list of lists of numbers \<open>[d # c\<^sub>0 # ts, N\<^sub>0, ..., N\<^sub>n\<^sub>-\<^sub>1, ...]\<close>:
\<^item> \<open>c\<^sub>0\<close> and the edge indices \<open>ts\<close> grow \<open>C\<close> as a list \<open>S\<close>: each index names an edge pair
  with one endpoint already in \<open>S\<close>, and the other endpoint is appended. This witnesses that
  \<open>G[C]\<close> is connected.
\<^item> \<open>N\<^sub>v\<close> lists the other endpoints of the edges owned by \<open>v\<close>; the owner of the edge
  \<open>{a, b}\<close> with \<open>a < b\<close> is \<open>a\<close> if \<open>a \<in> C\<close> and \<open>b \<in> N\<^sub>a\<close>, and \<open>b\<close> otherwise. The
  capacity check is \<open>|N\<^sub>v| \<le> k\<close>; repeated pairs in the instance cannot inflate a load.
\<^item> \<open>d\<close> is the slack in the weight bound: \<open>\<Sum>\<^sub>c\<^sub>\<in>\<^sub>S w c + d = B\<close>.
\<close>

definition grow_step :: "nat \<Rightarrow> nat list \<Rightarrow> bool \<times> nat list \<Rightarrow> nat \<Rightarrow> bool \<times> nat list" where
  "grow_step n es st t \<equiv>
    if \<not> fst st then st else
    (if Suc (2 * t) < length es \<and> es ! (2 * t) \<noteq> es ! Suc (2 * t) \<and>
        es ! (2 * t) < n \<and> es ! Suc (2 * t) < n
     then (if es ! (2 * t) \<in> set (snd st) then (fst st, snd st @ [es ! Suc (2 * t)])
           else if es ! Suc (2 * t) \<in> set (snd st) then (fst st, snd st @ [es ! (2 * t)])
           else (False, snd st))
     else (False, snd st))"

definition grow :: "nat \<Rightarrow> nat list \<Rightarrow> nat \<Rightarrow> nat list \<Rightarrow> bool \<times> nat list" where
  "grow n es c0 ts \<equiv> foldl (grow_step n es) (True, [c0]) ts"

definition own_ok :: "nat \<Rightarrow> nat list \<Rightarrow> nat list \<Rightarrow> nat list list \<Rightarrow> bool" where
  "own_ok n es S nssc \<equiv> \<forall>(u, x)\<in>set (pairs es). u \<noteq> x \<and> u < n \<and> x < n \<longrightarrow>
     (u \<in> set S \<and> x \<in> set (nssc ! Suc u)) \<or> (x \<in> set S \<and> u \<in> set (nssc ! Suc x))"

definition cert_ok :: "nat list list \<Rightarrow> nat list list \<Rightarrow> bool" where
  "cert_ok nss nssc \<equiv>
    (let n = n_of nss; es = es_of nss; L0 = nth_or [] nssc 0;
         g = grow n es (L0 ! Suc 0) (drop 2 L0)
     in 2 \<le> length L0 \<and> L0 ! Suc 0 < n \<and> n < length nssc \<and> fst g \<and>
        sum_list (map (w_of nss) (snd g)) + L0 ! 0 = B_of nss \<and>
        (\<forall>v<n. length (nssc ! Suc v) \<le> k_of nss) \<and>
        own_ok n es (snd g) nssc)"

subsection \<open>Soundness\<close>

lemma ind_rel_sym: "sym (ind_rel E C)"
  unfolding ind_rel_def sym_def by (auto simp: insert_commute)

lemma rtrancl_sym:
  assumes "sym R" and "(x, y) \<in> R\<^sup>*"
  shows "(y, x) \<in> R\<^sup>*"
  using assms by (metis rtrancl_converseI sym_conv_converse_eq)

lemma ind_rel_mono:
  assumes "C \<subseteq> C'"
  shows "(ind_rel E C)\<^sup>* \<subseteq> (ind_rel E C')\<^sup>*"
proof -
  have "ind_rel E C \<subseteq> ind_rel E C'"
    using assms unfolding ind_rel_def by auto
  then show ?thesis
    using rtrancl_mono by blast
qed

lemma pair_in_pairs:
  assumes "Suc (2 * t) < length es"
  shows "(es ! (2 * t), es ! Suc (2 * t)) \<in> set (pairs es)"
proof -
  have "t < length (pairs es)"
    using assms length_pairs by simp
  then show ?thesis
    using nth_pairs by (metis nth_mem)
qed

lemma grow_step_fst:
  assumes "fst (grow_step n es st t)"
  shows "fst st"
  using assms unfolding grow_step_def by (auto split: if_splits)

lemma grow_False: "fst (foldl (grow_step n es) (False, S) ts) = False"
proof (induction ts arbitrary: S rule: rev_induct)
  case (snoc t ts)
  then show ?case
    by (simp add: grow_step_def)
qed simp

lemma grow_inv:
  assumes "c0 < n"
    and "fst (foldl (grow_step n es) (True, [c0]) ts)"
    and "S = snd (foldl (grow_step n es) (True, [c0]) ts)"
  shows "set S \<subseteq> {..<n}" "c0 \<in> set S"
    "\<forall>x\<in>set S. (c0, x) \<in> (ind_rel (edges_of n es) (set S))\<^sup>*"
    "length S = Suc (length ts)"
  using assms(2,3)
proof (induction ts arbitrary: S rule: rev_induct)
  case Nil
  {
    case 1 then show ?case using assms(1) by simp
  next
    case 2 then show ?case by simp
  next
    case 3 then show ?case by simp
  next
    case 4 then show ?case by simp
  }
next
  case (snoc t ts)
  let ?st = "foldl (grow_step n es) (True, [c0]) ts"
  have step: "foldl (grow_step n es) (True, [c0]) (ts @ [t]) = grow_step n es ?st t"
    by simp
  let ?a = "es ! (2 * t)" and ?b = "es ! Suc (2 * t)"
  have ok: "fst ?st" and cond: "Suc (2 * t) < length es" "?a \<noteq> ?b" "?a < n" "?b < n"
    and grow: "(?a \<in> set (snd ?st) \<and> snd (grow_step n es ?st t) = snd ?st @ [?b]) \<or>
      (?a \<notin> set (snd ?st) \<and> ?b \<in> set (snd ?st) \<and> snd (grow_step n es ?st t) = snd ?st @ [?a])"
    if "fst (grow_step n es ?st t)"
    using that unfolding grow_step_def by (auto split: if_splits)
  {
    case 1
    then show ?case
      using snoc.IH(1) step ok cond grow by auto
  next
    case 2
    then show ?case
      using snoc.IH(2) step ok cond grow by auto
  next
    case 3
    have IH: "\<forall>x\<in>set (snd ?st). (c0, x) \<in> (ind_rel (edges_of n es) (set (snd ?st)))\<^sup>*"
      using snoc.IH(3) 3 step ok by auto
    have Sst: "set (snd ?st) \<subseteq> set S"
      using 3 step grow by auto
    have edge: "{?a, ?b} \<in> edges_of n es"
      using 3 step cond pair_in_pairs unfolding edges_of_def by fastforce
    show ?case
    proof
      fix x assume x: "x \<in> set S"
      show "(c0, x) \<in> (ind_rel (edges_of n es) (set S))\<^sup>*"
      proof (cases "x \<in> set (snd ?st)")
        case True
        then show ?thesis
          using IH ind_rel_mono[OF Sst] by blast
      next
        case False
        then have "(x = ?b \<and> ?a \<in> set (snd ?st)) \<or> (x = ?a \<and> ?b \<in> set (snd ?st))"
          using x 3 step grow by auto
        then show ?thesis
        proof
          assume xb: "x = ?b \<and> ?a \<in> set (snd ?st)"
          then have "(c0, ?a) \<in> (ind_rel (edges_of n es) (set S))\<^sup>*"
            using IH ind_rel_mono[OF Sst] by blast
          moreover have "(?a, ?b) \<in> ind_rel (edges_of n es) (set S)"
            using edge xb x Sst unfolding ind_rel_def by auto
          ultimately show ?thesis
            using xb by simp
        next
          assume xa: "x = ?a \<and> ?b \<in> set (snd ?st)"
          then have "(c0, ?b) \<in> (ind_rel (edges_of n es) (set S))\<^sup>*"
            using IH ind_rel_mono[OF Sst] by blast
          moreover have "(?b, ?a) \<in> ind_rel (edges_of n es) (set S)"
            using edge xa x Sst unfolding ind_rel_def by (auto simp: insert_commute)
          ultimately show ?thesis
            using xa by simp
        qed
      qed
    qed
  next
    case 4
    then show ?case
      using snoc.IH(4) step ok grow by auto
  }
qed

lemma sum_set_le_sum_list:
  fixes w :: "nat \<Rightarrow> nat"
  shows "sum w (set xs) \<le> sum_list (map w xs)"
proof (induction xs)
  case (Cons x xs)
  have "sum w (set (x # xs)) \<le> w x + sum w (set xs)"
    by (simp add: sum.insert_if)
  then show ?case
    using Cons by simp
qed simp

theorem cert_ok_sound:
  assumes "cert_ok nss nssc"
  shows "inst_yes nss"
proof -
  let ?n = "n_of nss" and ?es = "es_of nss"
  let ?L0 = "nth_or [] nssc 0"
  let ?c0 = "?L0 ! Suc 0"
  let ?g = "grow ?n ?es ?c0 (drop 2 ?L0)"
  let ?S = "snd ?g"
  let ?E = "E_of nss"
  define N where "N v = nssc ! Suc v" for v
  define C where "C = set ?S"
  have a: "2 \<le> length ?L0" "?c0 < ?n" "?n < length nssc" "fst ?g"
      "sum_list (map (w_of nss) ?S) + ?L0 ! 0 = B_of nss"
      "\<forall>v<?n. length (N v) \<le> k_of nss" "own_ok ?n ?es ?S nssc"
    using assms unfolding cert_ok_def Let_def N_def by simp_all
  have E: "?E = edges_of ?n ?es"
    unfolding E_of_def by simp
  have inv: "set ?S \<subseteq> {..<?n}" "?c0 \<in> set ?S"
      "\<forall>x\<in>set ?S. (?c0, x) \<in> (ind_rel ?E (set ?S))\<^sup>*"
    using grow_inv[OF a(2), of ?es "drop 2 ?L0" ?S] a(4) E unfolding grow_def by simp_all
  have conn: "connected_on ?E C"
  proof -
    have "(u, v) \<in> (ind_rel ?E C)\<^sup>*" if "u \<in> C" "v \<in> C" for u v
    proof -
      have "(?c0, u) \<in> (ind_rel ?E C)\<^sup>*" "(?c0, v) \<in> (ind_rel ?E C)\<^sup>*"
        using inv(3) that C_def by simp_all
      then have "(u, ?c0) \<in> (ind_rel ?E C)\<^sup>*"
        using rtrancl_sym[OF ind_rel_sym] by blast
      then show ?thesis
        using \<open>(?c0, v) \<in> (ind_rel ?E C)\<^sup>*\<close> by simp
    qed
    then show ?thesis
      unfolding connected_on_def using inv(2) C_def by auto
  qed
  have pair_cond: "(a \<in> C \<and> b \<in> set (N a)) \<or> (b \<in> C \<and> a \<in> set (N b))"
    if "e \<in> ?E" "e = {a, b}" for e a b
  proof -
    have "e \<in> edges_of ?n ?es"
      using that(1) E by simp
    then obtain u x where ux: "e = {u, x}" "(u, x) \<in> set (pairs ?es)" "u \<noteq> x" "u < ?n" "x < ?n"
      unfolding edges_of_def by blast
    then have "(u \<in> C \<and> x \<in> set (N u)) \<or> (x \<in> C \<and> u \<in> set (N x))"
      using a(7) unfolding own_ok_def N_def C_def by fastforce
    moreover have "(a = u \<and> b = x) \<or> (a = x \<and> b = u)"
      using ux(1) that(2) by (auto simp: doubleton_eq_iff)
    ultimately show ?thesis
      by blast
  qed
  define own where "own e = (if Min e \<in> C \<and> Max e \<in> set (N (Min e)) then Min e else Max e)" for e
  have edge_form: "\<exists>a b. e = {a, b} \<and> a < b \<and> Min e = a \<and> Max e = b" if "e \<in> ?E" for e
  proof -
    have "e \<in> edges_of ?n ?es"
      using that E by simp
    then obtain u x where "e = {u, x}" "u \<noteq> x"
      unfolding edges_of_def by blast
    then show ?thesis
      by (cases "u < x") (auto simp: insert_commute)
  qed
  have own_in: "own e \<in> e \<and> own e \<in> C" if eE: "e \<in> ?E" for e
  proof -
    obtain a b where ab: "e = {a, b}" "a < b" "Min e = a" "Max e = b"
      using edge_form[OF eE] by blast
    show ?thesis
      using pair_cond[OF eE ab(1)] ab unfolding own_def by auto
  qed
  have load: "load ?E own v \<le> k_of nss" if "v \<in> C" for v
  proof -
    define g where "g e = (if Min e = v then Max e else Min e)" for e :: "nat set"
    have v_n: "v < ?n"
      using that inv(1) C_def by auto
    have g_in: "g e \<in> set (N v)" and g_e: "e = {v, g e}" if eE: "e \<in> ?E" "own e = v" for e
    proof -
      obtain a b where ab: "e = {a, b}" "a < b" "Min e = a" "Max e = b"
        using edge_form[OF eE(1)] by blast
      show "g e \<in> set (N v)"
      proof (cases "a \<in> C \<and> b \<in> set (N a)")
        case True
        then have "v = a"
          using that(2) ab(3,4) unfolding own_def by simp
        then show ?thesis
          using True ab unfolding g_def by simp
      next
        case False
        then have "v = b"
          using that(2) ab(3,4) unfolding own_def by (auto split: if_splits)
        moreover have "b \<in> C \<and> a \<in> set (N b)"
          using pair_cond[OF that(1) ab(1)] False by blast
        ultimately show ?thesis
          using ab unfolding g_def by simp
      qed
      show "e = {v, g e}"
        using own_in[OF that(1)] that(2) ab unfolding g_def by (auto simp: insert_commute)
    qed
    have "inj_on g {e\<in>?E. own e = v}"
    proof (rule inj_onI)
      fix e1 e2
      assume e1: "e1 \<in> {e\<in>?E. own e = v}" and e2: "e2 \<in> {e\<in>?E. own e = v}"
        and eq: "g e1 = g e2"
      have 1: "e1 = {v, g e1}"
        using g_e e1 by blast
      have 2: "e2 = {v, g e2}"
        using g_e e2 by blast
      show "e1 = e2"
        by (subst 1, subst 2) (simp add: eq)
    qed
    then have "card {e\<in>?E. own e = v} = card (g ` {e\<in>?E. own e = v})"
      by (simp add: card_image)
    also have "\<dots> \<le> card (set (N v))"
      using g_in by (intro card_mono) auto
    also have "\<dots> \<le> length (N v)"
      by (rule card_length)
    also have "\<dots> \<le> k_of nss"
      using a(6) v_n by simp
    finally show ?thesis
      unfolding load_def .
  qed
  have cvc: "connected_vertex_cover ?n ?E C"
  proof -
    have "vertex_cover ?E C"
      using own_in unfolding vertex_cover_def by blast
    then show ?thesis
      unfolding connected_vertex_cover_def using inv(1) C_def conn by simp
  qed
  have "valid_pair ?n ?E (k_of nss) C own"
    unfolding valid_pair_def owner_map_def using cvc own_in load by blast
  moreover have "sum (w_of nss) C \<le> B_of nss"
    using sum_set_le_sum_list[of "w_of nss" ?S] a(5) C_def by simp
  ultimately show ?thesis
    unfolding inst_yes_def mwccvc_yes_def by blast
qed

subsection \<open>Completeness\<close>

lemma rtrancl_leaves:
  assumes "(u, v) \<in> R\<^sup>*" and "u \<in> A" and "v \<notin> A"
  shows "\<exists>x y. (x, y) \<in> R \<and> x \<in> A \<and> y \<notin> A"
  using assms by (induction rule: rtrancl_induct) auto

lemma grow_extend:
  assumes "connected_on (edges_of n es) C"
    and "ok" and "set S \<subseteq> C" and "S \<noteq> []" and "set S \<noteq> C"
  shows "\<exists>t y. grow_step n es (ok, S) t = (True, S @ [y]) \<and> y \<in> C - set S"
proof -
  let ?E = "edges_of n es"
  obtain u where u: "u \<in> set S"
    using assms(4) by (cases S) auto
  obtain v where v: "v \<in> C" "v \<notin> set S"
    using assms(3,5) by blast
  have uC: "u \<in> C"
    using u assms(3) by blast
  have "(u, v) \<in> (ind_rel ?E C)\<^sup>*"
    using assms(1) uC v(1) unfolding connected_on_def by blast
  from rtrancl_leaves[OF this u v(2)]
  obtain x y where xy: "(x, y) \<in> ind_rel ?E C" "x \<in> set S" "y \<notin> set S"
    by blast
  then have e: "{x, y} \<in> ?E" "y \<in> C"
    unfolding ind_rel_def by simp_all
  then obtain a b where ab: "{x, y} = {a, b}" "(a, b) \<in> set (pairs es)" "a \<noteq> b" "a < n" "b < n"
    unfolding edges_of_def by blast
  then obtain t where t: "t < length (pairs es)" "pairs es ! t = (a, b)"
    by (metis in_set_conv_nth)
  then have es: "Suc (2 * t) < length es" "es ! (2 * t) = a" "es ! Suc (2 * t) = b"
    using nth_pairs length_pairs by fastforce+
  show ?thesis
  proof (cases "a \<in> set S")
    case True
    then have "a = x" "b = y"
      using ab(1) xy(2,3) by (auto simp: doubleton_eq_iff)
    then have "grow_step n es (ok, S) t = (True, S @ [y])"
      using assms(2) True es ab unfolding grow_step_def by simp
    then show ?thesis
      using e(2) xy(3) by blast
  next
    case False
    then have "a = y" "b = x"
      using ab(1) xy(2,3) by (auto simp: doubleton_eq_iff)
    then have "grow_step n es (ok, S) t = (True, S @ [y])"
      using assms(2) False es ab xy(2) unfolding grow_step_def by simp
    then show ?thesis
      using e(2) xy(3) by blast
  qed
qed

lemma grow_exists:
  assumes "connected_on (edges_of n es) C" and "C \<subseteq> {..<n}" and "c0 \<in> C"
  shows "\<exists>ts. fst (grow n es c0 ts) \<and> distinct (snd (grow n es c0 ts)) \<and>
    set (snd (grow n es c0 ts)) = C"
proof -
  have fin: "finite C"
    using assms(2) finite_subset by blast
  have "\<forall>ts. fst (grow n es c0 ts) \<and> distinct (snd (grow n es c0 ts)) \<and>
      set (snd (grow n es c0 ts)) \<subseteq> C \<and> card C - length (snd (grow n es c0 ts)) = m \<longrightarrow>
      (\<exists>ts'. fst (grow n es c0 ts') \<and> distinct (snd (grow n es c0 ts')) \<and>
        set (snd (grow n es c0 ts')) = C)" for m
  proof (induction m)
    case 0
    show ?case
    proof (intro allI impI)
      fix ts assume a: "fst (grow n es c0 ts) \<and> distinct (snd (grow n es c0 ts)) \<and>
        set (snd (grow n es c0 ts)) \<subseteq> C \<and> card C - length (snd (grow n es c0 ts)) = 0"
      let ?S = "snd (grow n es c0 ts)"
      have "card (set ?S) = length ?S"
        using a distinct_card by blast
      then have "card C \<le> card (set ?S)"
        using a by simp
      then have "set ?S = C"
        using a fin card_seteq by blast
      then show "\<exists>ts'. fst (grow n es c0 ts') \<and> distinct (snd (grow n es c0 ts')) \<and>
          set (snd (grow n es c0 ts')) = C"
        using a by blast
    qed
  next
    case (Suc m)
    show ?case
    proof (intro allI impI)
      fix ts assume a: "fst (grow n es c0 ts) \<and> distinct (snd (grow n es c0 ts)) \<and>
        set (snd (grow n es c0 ts)) \<subseteq> C \<and> card C - length (snd (grow n es c0 ts)) = Suc m"
      let ?S = "snd (grow n es c0 ts)"
      have len: "length ?S = Suc (length ts)"
        using grow_inv(4)[of c0 n es ts ?S] assms(2,3) a unfolding grow_def by auto
      have "set ?S \<noteq> C"
      proof
        assume "set ?S = C"
        then have "card C = length ?S"
          using a distinct_card by metis
        then show False
          using a by simp
      qed
      moreover have ne: "?S \<noteq> []"
        using len by auto
      moreover have ok: "fst (grow n es c0 ts)"
        using a by blast
      moreover have sub: "set ?S \<subseteq> C"
        using a by blast
      ultimately obtain t y where ty: "grow_step n es (fst (grow n es c0 ts), ?S) t = (True, ?S @ [y])"
          "y \<in> C - set ?S"
        using grow_extend[OF assms(1) ok sub ne] by blast
      have g: "grow n es c0 (ts @ [t]) = (True, ?S @ [y])"
        using ty(1) unfolding grow_def by simp
      have "fst (grow n es c0 (ts @ [t])) \<and> distinct (snd (grow n es c0 (ts @ [t]))) \<and>
          set (snd (grow n es c0 (ts @ [t]))) \<subseteq> C \<and>
          card C - length (snd (grow n es c0 (ts @ [t]))) = m"
        using g a ty(2) by auto
      then show "\<exists>ts'. fst (grow n es c0 ts') \<and> distinct (snd (grow n es c0 ts')) \<and>
          set (snd (grow n es c0 ts')) = C"
        using Suc.IH by blast
    qed
  qed
  moreover have "fst (grow n es c0 []) \<and> distinct (snd (grow n es c0 [])) \<and>
      set (snd (grow n es c0 [])) \<subseteq> C"
    unfolding grow_def using assms(3) by simp
  ultimately show ?thesis
    by blast
qed

text \<open>Size bounds in terms of the length \<open>\<ell>\<close> of the instance's symbol representation.\<close>

lemma nllength_nth_le:
  assumes "i < length nss"
  shows "nllength (nss ! i) \<le> nlllength nss"
proof -
  have "nllength (nss ! i) \<le> (\<Sum>ns\<leftarrow>nss. Suc (nllength ns))"
    using assms
  proof (induction nss arbitrary: i)
    case (Cons ns nss)
    then show ?case
      by (cases i) fastforce+
  qed simp
  then show ?thesis
    using nlllength by simp
qed

lemma nllength_nth_or_le: "nllength (nth_or [] nss i) \<le> nlllength nss"
  unfolding nth_or_def using nllength_nth_le by (simp add: nllength_def numlist_Nil)

lemma length_nth_or_le: "length (nth_or [] nss i) \<le> nlllength nss"
  using nllength_nth_or_le length_le_nllength le_trans by blast

lemma nlength_elem_le:
  assumes "x \<in> set ns"
  shows "nlength x \<le> nllength ns"
proof -
  have "nlength x \<le> (\<Sum>n\<leftarrow>ns. Suc (nlength n))"
    using assms by (induction ns) auto
  then show ?thesis
    using nllength by simp
qed

lemma nllength_bound:
  assumes "\<And>x. x \<in> set ns \<Longrightarrow> nlength x \<le> b"
  shows "nllength ns \<le> length ns * Suc b"
proof -
  have "(\<Sum>n\<leftarrow>ns. Suc (nlength n)) \<le> (\<Sum>n\<leftarrow>ns. Suc b)"
    using assms by (intro sum_list_mono) simp
  then show ?thesis
    using nllength sum_list_const by (metis mult.commute)
qed

lemma nlllength_append: "nlllength (xss @ yss) = nlllength xss + nlllength yss"
  using nlllength by simp

lemma nlllength_map_le:
  assumes "\<And>v. v < n \<Longrightarrow> nllength (f v) \<le> length (f v) * Suc b"
  shows "nlllength (map f [0..<n]) \<le> (\<Sum>v\<leftarrow>[0..<n]. length (f v)) * Suc b + n"
proof -
  have "nlllength (map f [0..<n]) = (\<Sum>v\<leftarrow>[0..<n]. Suc (nllength (f v)))"
    using nlllength by (simp add: comp_def)
  also have "\<dots> \<le> (\<Sum>v\<leftarrow>[0..<n]. Suc (length (f v) * Suc b))"
    using assms by (intro sum_list_mono) simp
  also have "\<dots> = (\<Sum>v\<leftarrow>[0..<n]. length (f v)) * Suc b + n"
    by (induction n) (simp_all add: algebra_simps)
  finally show ?thesis .
qed

lemma nlength_less_le:
  assumes "x < m" and "m \<le> b"
  shows "nlength x \<le> b"
  using assms nlength_le_n by (meson le_trans less_imp_le)

theorem cert_ok_complete:
  assumes "inst_yes nss"
  shows "\<exists>nssc. cert_ok nss nssc \<and> nlllength nssc \<le> 8 * (Suc (nlllength nss))\<^sup>2 \<and>
    (\<exists>nssc'. nssc = nssc' @ [[0]])"
proof -
  let ?n = "n_of nss" and ?es = "es_of nss" and ?E = "E_of nss" and ?k = "k_of nss"
  let ?l = "nlllength nss"
  obtain C own where C: "valid_pair ?n ?E ?k C own" "sum (w_of nss) C \<le> B_of nss"
    using assms unfolding inst_yes_def mwccvc_yes_def by blast
  have cvc: "C \<subseteq> {..<?n}" "vertex_cover ?E C" "connected_on ?E C"
    using C(1) unfolding valid_pair_def connected_vertex_cover_def by simp_all
  have om: "\<forall>e\<in>?E. own e \<in> e \<and> own e \<in> C" "\<forall>v\<in>C. load ?E own v \<le> ?k"
    using C(1) unfolding valid_pair_def owner_map_def by simp_all
  have E: "?E = edges_of ?n ?es"
    unfolding E_of_def by simp
  have finE: "finite ?E"
    using is_edge_set_finite edges_of_is_edge_set E by metis
  obtain c0 where c0: "c0 \<in> C"
    using cvc(3) unfolding connected_on_def by blast
  then have c0n: "c0 < ?n"
    using cvc(1) by auto
  obtain ts where ts: "fst (grow ?n ?es c0 ts)" "distinct (snd (grow ?n ?es c0 ts))"
      "set (snd (grow ?n ?es c0 ts)) = C"
    using grow_exists[OF _ cvc(1) c0] cvc(3) E by metis
  let ?S = "snd (grow ?n ?es c0 ts)"
  have lenS: "length ?S = Suc (length ts)"
    using grow_inv(4)[OF c0n] ts(1) unfolding grow_def by simp
  have sumS: "sum_list (map (w_of nss) ?S) = sum (w_of nss) C"
    using ts(2,3) sum_list_distinct_conv_sum_set by metis
  define d where "d = B_of nss - sum (w_of nss) C"
  define N where "N v = sorted_list_of_set {y. {v, y} \<in> ?E \<and> own {v, y} = v}" for v
  have finN: "finite {y. {v, y} \<in> ?E \<and> own {v, y} = v}" for v
  proof -
    have "{y. {v, y} \<in> ?E \<and> own {v, y} = v} \<subseteq> {..<?n}"
      unfolding E edges_of_def by (auto simp: doubleton_eq_iff)
    then show ?thesis
      using finite_subset by blast
  qed
  have setN: "set (N v) = {y. {v, y} \<in> ?E \<and> own {v, y} = v}" for v
    unfolding N_def using finN by simp
  have lenN: "length (N v) = load ?E own v" for v
  proof -
    have "length (N v) = card {y. {v, y} \<in> ?E \<and> own {v, y} = v}"
      unfolding N_def using finN by simp
    also have "\<dots> = card ((\<lambda>y. {v, y}) ` {y. {v, y} \<in> ?E \<and> own {v, y} = v})"
    proof -
      have "inj_on (\<lambda>y. {v, y}) {y. {v, y} \<in> ?E \<and> own {v, y} = v}"
        by (auto simp: inj_on_def doubleton_eq_iff)
      then show ?thesis
        by (simp add: card_image)
    qed
    also have "(\<lambda>y. {v, y}) ` {y. {v, y} \<in> ?E \<and> own {v, y} = v} = {e\<in>?E. own e = v}"
    proof
      show "(\<lambda>y. {v, y}) ` {y. {v, y} \<in> ?E \<and> own {v, y} = v} \<subseteq> {e\<in>?E. own e = v}"
        by auto
      show "{e\<in>?E. own e = v} \<subseteq> (\<lambda>y. {v, y}) ` {y. {v, y} \<in> ?E \<and> own {v, y} = v}"
      proof
        fix e assume e: "e \<in> {e\<in>?E. own e = v}"
        then have "v \<in> e"
          using om(1) by blast
        moreover obtain a b where "e = {a, b}"
          using e unfolding E edges_of_def by blast
        ultimately obtain y where "e = {v, y}"
          by blast
        then show "e \<in> (\<lambda>y. {v, y}) ` {y. {v, y} \<in> ?E \<and> own {v, y} = v}"
          using e by blast
      qed
    qed
    finally show ?thesis
      unfolding load_def .
  qed
  have loadN: "length (N v) \<le> ?k" for v
  proof (cases "v \<in> C")
    case True
    then show ?thesis
      using lenN om(2) by simp
  next
    case False
    have empty: "{e\<in>?E. own e = v} = {}"
      using om(1) False by blast
    show ?thesis
      using lenN[of v] unfolding load_def by (simp add: empty)
  qed
  define nssc where "nssc = (d # c0 # ts) # map N [0..<?n] @ [[0]]"
  have L0: "nth_or [] nssc 0 = d # c0 # ts"
    unfolding nssc_def nth_or_def by simp
  have nssc_N: "nssc ! Suc v = N v" if "v < ?n" for v
    unfolding nssc_def using that by (simp add: nth_append)
  have own_ok: "own_ok ?n ?es ?S nssc"
  proof -
    have "(u \<in> set ?S \<and> x \<in> set (nssc ! Suc u)) \<or> (x \<in> set ?S \<and> u \<in> set (nssc ! Suc x))"
      if ux: "(u, x) \<in> set (pairs ?es)" "u \<noteq> x" "u < ?n" "x < ?n" for u x
    proof -
      have e: "{u, x} \<in> ?E"
        using ux unfolding E edges_of_def by blast
      then have o: "own {u, x} = u \<or> own {u, x} = x" "own {u, x} \<in> C"
        using om(1) by auto
      have e': "{x, u} \<in> ?E"
        using e by (simp add: insert_commute)
      show ?thesis
      proof (cases "own {u, x} = u")
        case True
        then have "x \<in> set (N u)"
          using setN e by simp
        then show ?thesis
          using True o(2) ts(3) nssc_N ux(3) by simp
      next
        case False
        then have own_x: "own {x, u} = x"
          using o(1) by (simp add: insert_commute)
        then have "u \<in> set (N x)"
          using setN e' by simp
        moreover have "x \<in> C"
          using o False by simp
        ultimately show ?thesis
          using ts(3) nssc_N ux(4) by simp
      qed
    qed
    then show ?thesis
      unfolding own_ok_def by blast
  qed
  have ok: "cert_ok nss nssc"
    unfolding cert_ok_def Let_def L0 grow_def[symmetric]
    using c0n ts(1) sumS C(2) d_def loadN nssc_N own_ok
    by (simp add: nssc_def grow_def)
  have last: "\<exists>nssc'. nssc = nssc' @ [[0]]"
    unfolding nssc_def by simp

  text \<open>The size bound.\<close>
  have n_le: "?n \<le> ?l"
    unfolding n_of_def wts_of_def using length_nth_or_le by simp
  have es_le: "length ?es \<le> ?l"
    unfolding es_of_def using length_nth_or_le by simp
  have B_le: "nlength (B_of nss) \<le> ?l"
  proof -
    have "nlength (B_of nss) \<le> nllength (hdr_of nss)"
      unfolding B_of_def nth_or_def using nlength_elem_le by (simp add: nlength_0_simp)
    then show ?thesis
      unfolding hdr_of_def using nllength_nth_or_le le_trans by blast
  qed
  have d_le: "nlength d \<le> ?l"
    using B_le nlength_mono[of d "B_of nss"] d_def by simp
  have ts_lt: "t < length (pairs ?es)" if "t \<in> set ts" for t
  proof -
    have "Suc (2 * t) < length ?es" if "t \<in> set ts'" "fst (grow ?n ?es c0 ts')" for t ts'
      using that
    proof (induction ts' rule: rev_induct)
      case (snoc t' ts')
      have "fst (grow ?n ?es c0 ts')"
        using grow_step_fst[of ?n ?es "foldl (grow_step ?n ?es) (True, [c0]) ts'" t'] snoc.prems(2)
        unfolding grow_def by simp
      moreover have "Suc (2 * t') < length ?es"
        using snoc.prems(2) unfolding grow_def grow_step_def by (auto split: if_splits)
      ultimately show ?case
        using snoc by auto
    qed simp
    then show ?thesis
      using that ts(1) length_pairs by fastforce
  qed
  have ts_le: "nlength t \<le> ?l" if "t \<in> set ts" for t
    using ts_lt[OF that] length_pairs es_le by (metis div_le_dividend nlength_less_le le_trans)
  have len_ts: "length ts \<le> ?l"
  proof -
    have "length ?S \<le> ?n"
      using ts(2,3) cvc(1) by (metis card_lessThan card_mono distinct_card finite_lessThan)
    then show ?thesis
      using lenS n_le by simp
  qed
  have c0_le: "nlength c0 \<le> ?l"
    using c0n n_le nlength_less_le by blast
  have L0_le: "nllength (d # c0 # ts) \<le> (Suc (Suc ?l)) * Suc ?l"
  proof -
    have "nllength (d # c0 # ts) \<le> length (d # c0 # ts) * Suc ?l"
      using d_le c0_le ts_le by (intro nllength_bound) auto
    moreover have "length (d # c0 # ts) * Suc ?l \<le> (Suc (Suc ?l)) * Suc ?l"
      using len_ts by (intro mult_le_mono1) simp
    ultimately show ?thesis
      by (rule le_trans)
  qed
  have N_elem: "nlength y \<le> ?l" if "y \<in> set (N v)" for v y
  proof -
    have "{v, y} \<in> ?E"
      using that setN by blast
    then have "y < ?n"
      unfolding E edges_of_def by (auto simp: doubleton_eq_iff)
    then show ?thesis
      using n_le nlength_less_le by blast
  qed
  have sum_load: "(\<Sum>v\<leftarrow>[0..<?n]. length (N v)) \<le> ?l"
  proof -
    have "(\<Sum>v\<leftarrow>[0..<?n]. length (N v)) = (\<Sum>v<?n. load ?E own v)"
      using lenN by (simp add: sum_list_distinct_conv_sum_set atLeast0LessThan)
    also have "\<dots> = (\<Sum>v<?n. card {e\<in>?E. own e = v})"
      unfolding load_def by simp
    also have "\<dots> = card (\<Union>v<?n. {e\<in>?E. own e = v})"
      using finE by (intro card_UN_disjoint[symmetric]) auto
    also have "\<dots> \<le> card ?E"
      using finE by (intro card_mono) auto
    also have "\<dots> \<le> length (pairs ?es)"
    proof -
      have "?E \<subseteq> (\<lambda>(a, b). {a, b}) ` set (pairs ?es)"
        unfolding E edges_of_def by auto
      then have "card ?E \<le> card ((\<lambda>(a, b). {a, b}) ` set (pairs ?es))"
        by (intro card_mono) auto
      also have "\<dots> \<le> card (set (pairs ?es))"
        by (rule card_image_le) simp
      also have "\<dots> \<le> length (pairs ?es)"
        by (rule card_length)
      finally show ?thesis .
    qed
    also have "\<dots> \<le> ?l"
      using length_pairs es_le by simp
    finally show ?thesis .
  qed
  have N_le: "nlllength (map N [0..<?n]) \<le> ?l * Suc ?l + ?l"
  proof -
    have "nlllength (map N [0..<?n]) \<le> (\<Sum>v\<leftarrow>[0..<?n]. length (N v)) * Suc ?l + ?n"
      using N_elem nllength_bound by (intro nlllength_map_le) blast
    also have "\<dots> \<le> ?l * Suc ?l + ?l"
      using sum_load n_le by (intro add_mono mult_le_mono1) auto
    finally show ?thesis .
  qed
  have "nlllength nssc = Suc (nllength (d # c0 # ts)) + nlllength (map N [0..<?n]) + 2"
    unfolding nssc_def using nlllength_Cons nlllength_append
    by (simp add: nllength_def numlist_def canrepr_0)
  also have "\<dots> \<le> Suc ((Suc (Suc ?l)) * Suc ?l) + (?l * Suc ?l + ?l) + 2"
    using L0_le N_le by simp
  also have "\<dots> \<le> 8 * (Suc ?l)\<^sup>2"
    by (simp add: power2_eq_square algebra_simps)
  finally show ?thesis
    using ok last by blast
qed

subsection \<open>The verifier function\<close>

text \<open>
The verifier reads \<open>\<langle>x, u\<rangle>\<close>. The instance \<open>x\<close> must encode a list of lists, the
certificate \<open>u\<close> is a list of lists followed by padding symbols \<open>\<bar>\<close>, which the verifier strips;
the encoding of a nonempty list of lists ends with \<open>\<sharp>\<close>, so stripping removes the padding
only. Every failure leads to the output \<open>[]\<close>.
\<close>

definition verify_mw :: "symbol list \<Rightarrow> symbol list" where
  "verify_mw zs \<equiv>
    let ys = bindecode zs;
        xs = bindecode (first ys);
        vs = rstrip \<bar> (bindecode (second ys))
    in if even (length (first ys)) \<and> bit_symbols (first ys) \<and> numlistlist_wf xs \<and>
          bit_symbols (second ys) \<and> numlistlist_wf vs \<and>
          cert_ok (THE nss. numlistlist nss = xs) (THE nss. numlistlist nss = vs)
       then [\<one>] else []"

lemma rstrip_append_replicate:
  assumes "xs = [] \<or> last xs \<noteq> z"
  shows "rstrip z (xs @ replicate m z) = xs"
proof -
  let ?zs = "xs @ replicate m z"
  have "(LEAST i. i \<le> length ?zs \<and> set (drop i ?zs) \<subseteq> {z}) = length xs"
  proof (rule Least_equality)
    show "length xs \<le> length ?zs \<and> set (drop (length xs) ?zs) \<subseteq> {z}"
      by auto
    show "length xs \<le> i" if "i \<le> length ?zs \<and> set (drop i ?zs) \<subseteq> {z}" for i
    proof (rule ccontr)
      assume "\<not> length xs \<le> i"
      then have i: "i < length xs"
        by simp
      then have xs: "xs \<noteq> []" "last xs \<noteq> z"
        using assms by auto
      have L: "last xs \<in> set (drop i xs)"
      proof -
        have "drop i xs \<noteq> []"
          using i by simp
        then have "last (drop i xs) \<in> set (drop i xs)"
          by (rule last_in_set)
        then show ?thesis
          using last_drop[OF i] by simp
      qed
      have D: "drop i ?zs = drop i xs @ replicate m z"
        using i by simp
      show False
        using that xs(2) L D by auto
    qed
  qed
  then show ?thesis
    unfolding rstrip_def by simp
qed

lemma bit_symbols_verify_mw: "bit_symbols (verify_mw zs)"
  unfolding verify_mw_def Let_def by simp

definition p_cert :: "nat \<Rightarrow> nat" where
  "p_cert m \<equiv> 16 * (Suc m)\<^sup>2"

lemma polynomial_p_cert: "polynomial p_cert"
proof -
  have "\<forall>m. p_cert m = (\<Sum>i\<leftarrow>[0..<length [16, 32, 16::nat]]. [16, 32, 16::nat] ! i * m ^ i)"
    unfolding p_cert_def by (simp add: power2_eq_square algebra_simps)
  then show ?thesis
    unfolding polynomial_def by blast
qed

lemma numlistlist_snoc_0: "numlistlist (nss @ [[0]]) = numlistlist nss @ [\<bar>, \<sharp>]"
  unfolding numlistlist_def numlist_def by (simp add: canrepr_0)

theorem verify_mw_NP:
  "x \<in> MWCCVC \<longleftrightarrow> (\<exists>u. length u = p_cert (length x) \<and> verify_mw \<langle>x; u\<rangle> = [\<one>])"
proof
  assume "x \<in> MWCCVC"
  then obtain nss where nss: "x = nll_to_string nss" "inst_yes nss"
    unfolding MWCCVC_def by blast
  obtain nssc where c: "cert_ok nss nssc" "nlllength nssc \<le> 8 * (Suc (nlllength nss))\<^sup>2"
      "\<exists>nssc'. nssc = nssc' @ [[0]]"
    using cert_ok_complete[OF nss(2)] by blast
  have lx: "length x = 2 * nlllength nss"
    using nss(1) by (simp add: nlllength_def)
  define L where "L = 8 * (Suc (length x))\<^sup>2"
  have L: "nlllength nssc \<le> L"
  proof -
    have "(Suc (nlllength nss))\<^sup>2 \<le> (Suc (length x))\<^sup>2"
      unfolding lx by (intro power_mono) auto
    then have "8 * (Suc (nlllength nss))\<^sup>2 \<le> L"
      unfolding L_def by simp
    then show ?thesis
      using c(2) by simp
  qed
  define vs0 where "vs0 = numlistlist nssc @ replicate (L - nlllength nssc) \<bar>"
  define u where "u = symbols_to_string (binencode vs0)"
  have bin_vs0: "binencodable vs0"
    unfolding vs0_def using binencodable_numlistlist binencodable_append
    by (simp add: nth_append)
  have u_sym: "string_to_symbols u = binencode vs0"
    unfolding u_def using bin_vs0 bit_symbols_binencode bit_symbols_to_symbols by simp
  have len_u: "length u = p_cert (length x)"
  proof -
    have lv: "length vs0 = L"
      unfolding vs0_def using L by (simp add: nlllength_def)
    have "length u = length (binencode vs0)"
      unfolding u_def by simp
    also have "\<dots> = 2 * L"
      using lv by simp
    also have "\<dots> = p_cert (length x)"
      unfolding p_cert_def L_def by simp
    finally show ?thesis .
  qed
  let ?zs = "\<langle>x; u\<rangle>"
  let ?ys = "bindecode ?zs"
  have first: "first ?ys = string_to_symbols x"
    using first_pair by simp
  have second: "second ?ys = string_to_symbols u"
    using second_pair by simp
  have xs: "bindecode (first ?ys) = numlistlist nss"
    using first nss(1) nll_to_string_symbols bindecode_encode binencodable_numlistlist by simp
  have ev: "even (length (first ?ys))"
    using first nss(1) nll_to_string_symbols by simp
  obtain nssc' where nssc': "nssc = nssc' @ [[0]]"
    using c(3) by blast
  have b2: "bindecode (second ?ys) = numlistlist nssc @ replicate (L - nlllength nssc) \<bar>"
    using second u_sym bindecode_encode bin_vs0 vs0_def by simp
  have last: "last (numlistlist nssc) \<noteq> \<bar>"
    unfolding nssc' numlistlist_snoc_0 by simp
  have vs: "rstrip \<bar> (bindecode (second ?ys)) = numlistlist nssc"
    unfolding b2 using last by (intro rstrip_append_replicate) simp
  have the1: "(THE nss'. numlistlist nss' = bindecode (first ?ys)) = nss"
    using xs numlistlist_inj by auto
  have the2: "(THE nss'. numlistlist nss' = rstrip \<bar> (bindecode (second ?ys))) = nssc"
    using vs numlistlist_inj by auto
  have c1: "even (length (first ?ys)) \<and> bit_symbols (first ?ys) \<and> numlistlist_wf (bindecode (first ?ys))"
    using ev first xs numlistlist_wf_def by auto
  have c2: "bit_symbols (second ?ys) \<and> numlistlist_wf (rstrip \<bar> (bindecode (second ?ys)))"
    using second vs numlistlist_wf_def by auto
  have c3: "cert_ok (THE nss'. numlistlist nss' = bindecode (first ?ys))
      (THE nss'. numlistlist nss' = rstrip \<bar> (bindecode (second ?ys)))"
    using the1 the2 c(1) by simp
  have "verify_mw ?zs = [\<one>]"
    unfolding verify_mw_def Let_def using c1 c2 c3 by simp
  then show "\<exists>u. length u = p_cert (length x) \<and> verify_mw \<langle>x; u\<rangle> = [\<one>]"
    using len_u by blast
next
  assume "\<exists>u. length u = p_cert (length x) \<and> verify_mw \<langle>x; u\<rangle> = [\<one>]"
  then obtain u where u: "verify_mw \<langle>x; u\<rangle> = [\<one>]"
    by blast
  let ?ys = "bindecode \<langle>x; u\<rangle>"
  have first: "first ?ys = string_to_symbols x"
    using first_pair by simp
  have conds: "even (length (first ?ys))" "numlistlist_wf (bindecode (first ?ys))"
      "cert_ok (THE nss. numlistlist nss = bindecode (first ?ys))
         (THE nss. numlistlist nss = rstrip \<bar> (bindecode (second ?ys)))"
    using u unfolding verify_mw_def Let_def by (simp_all split: if_splits)
  obtain nss where nss: "x = nll_to_string nss"
    using ex_nll_iff conds(1,2) first by metis
  have "(THE nss. numlistlist nss = bindecode (first ?ys)) = nss"
    using the_nll[OF nss] first by simp
  then have "inst_yes nss"
    using cert_ok_sound conds(3) by metis
  then show "x \<in> MWCCVC"
    unfolding MWCCVC_def using nss by blast
qed

end
