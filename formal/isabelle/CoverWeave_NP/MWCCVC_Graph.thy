theory MWCCVC_Graph
  imports Cook_Levin.Satisfiability
begin

section \<open>Graphs, connected vertex covers and MWCCVC\<close>

text \<open>
Source: CoverWeave manuscript, \<open>sections/04-formaleng.tex\<close>, Definition \<open>def:mwccvc\<close>.
A graph on the vertex set \<open>{0..<n}\<close> is a set \<open>E\<close> of two-element sets of vertices.
The Lean counterparts are \<open>IsVertexCover\<close>, \<open>IsConnectedVertexCover\<close>, \<open>load\<close>,
\<open>IsOwnerMap\<close> and \<open>ValidPair\<close> in \<open>SwarmInferLean/CoverWeave/Basic.lean\<close>.

Modelling choices, the same as in the Lean files:
\<^item> The weight does not enter validity; it only enters the objective (here the bound \<open>B\<close>).
\<^item> Connectivity of \<open>G[C]\<close> includes nonemptiness of \<open>C\<close>, as Mathlib's \<open>Connected\<close> does.
\<^item> Connectivity of \<open>G\<close> itself is not part of a valid pair.
\<^item> Weights are natural numbers. The paper's positive rational weights become positive integers
  after multiplying by a common denominator, which preserves the order of all sums.
\<close>

definition is_edge_set :: "nat \<Rightarrow> nat set set \<Rightarrow> bool" where
  "is_edge_set n E \<equiv> \<forall>e\<in>E. \<exists>u v. e = {u, v} \<and> u \<noteq> v \<and> u < n \<and> v < n"

definition vertex_cover :: "nat set set \<Rightarrow> nat set \<Rightarrow> bool" where
  "vertex_cover E C \<equiv> \<forall>e\<in>E. e \<inter> C \<noteq> {}"

text \<open>The edge relation of the induced subgraph \<open>G[C]\<close>.\<close>

definition ind_rel :: "nat set set \<Rightarrow> nat set \<Rightarrow> (nat \<times> nat) set" where
  "ind_rel E C \<equiv> {(u, v). {u, v} \<in> E \<and> u \<in> C \<and> v \<in> C}"

definition connected_on :: "nat set set \<Rightarrow> nat set \<Rightarrow> bool" where
  "connected_on E C \<equiv> C \<noteq> {} \<and> (\<forall>u\<in>C. \<forall>v\<in>C. (u, v) \<in> (ind_rel E C)\<^sup>*)"

definition connected_vertex_cover :: "nat \<Rightarrow> nat set set \<Rightarrow> nat set \<Rightarrow> bool" where
  "connected_vertex_cover n E C \<equiv> C \<subseteq> {..<n} \<and> vertex_cover E C \<and> connected_on E C"

definition load :: "nat set set \<Rightarrow> (nat set \<Rightarrow> nat) \<Rightarrow> nat \<Rightarrow> nat" where
  "load E own v \<equiv> card {e\<in>E. own e = v}"

definition owner_map :: "nat set set \<Rightarrow> nat \<Rightarrow> nat set \<Rightarrow> (nat set \<Rightarrow> nat) \<Rightarrow> bool" where
  "owner_map E k C own \<equiv> (\<forall>e\<in>E. own e \<in> e \<and> own e \<in> C) \<and> (\<forall>v\<in>C. load E own v \<le> k)"

text \<open>Definition \<open>def:mwccvc\<close>: the four conditions of a valid pair \<open>(C, owner)\<close>.\<close>

definition valid_pair :: "nat \<Rightarrow> nat set set \<Rightarrow> nat \<Rightarrow> nat set \<Rightarrow> (nat set \<Rightarrow> nat) \<Rightarrow> bool" where
  "valid_pair n E k C own \<equiv> connected_vertex_cover n E C \<and> owner_map E k C own"

text \<open>The decision version of MWCCVC: is there a valid pair of weight at most \<open>B\<close>?\<close>

definition mwccvc_yes :: "nat \<Rightarrow> nat set set \<Rightarrow> (nat \<Rightarrow> nat) \<Rightarrow> nat \<Rightarrow> nat \<Rightarrow> bool" where
  "mwccvc_yes n E w k B \<equiv> \<exists>C own. valid_pair n E k C own \<and> sum w C \<le> B"

definition degree :: "nat set set \<Rightarrow> nat \<Rightarrow> nat" where
  "degree E v \<equiv> card {e\<in>E. v \<in> e}"

definition independent :: "nat set set \<Rightarrow> nat set \<Rightarrow> bool" where
  "independent E S \<equiv> \<forall>e\<in>E. \<not> e \<subseteq> S"

lemma is_edge_set_finite:
  assumes "is_edge_set n E"
  shows "finite E"
proof -
  have "E \<subseteq> Pow {..<n}"
    using assms unfolding is_edge_set_def by auto
  then show ?thesis
    using finite_subset by blast
qed

lemma is_edge_setD:
  assumes "is_edge_set n E" and "e \<in> E"
  shows "\<exists>u v. e = {u, v} \<and> u \<noteq> v \<and> u < n \<and> v < n"
  using assms unfolding is_edge_set_def by (rule bspec)

lemma owner_map_vertex_cover:
  assumes "owner_map E k C own"
  shows "vertex_cover E C"
  using assms unfolding owner_map_def vertex_cover_def by blast

lemma degree_le:
  assumes "is_edge_set n E"
  shows "degree E v \<le> n - 1"
proof (cases "v < n")
  case True
  have "{e\<in>E. v \<in> e} \<subseteq> (\<lambda>u. {v, u}) ` ({..<n} - {v})"
  proof
    fix e assume e: "e \<in> {e\<in>E. v \<in> e}"
    then obtain a b where ab: "e = {a, b}" "a \<noteq> b" "a < n" "b < n"
      using is_edge_setD[OF assms] by blast
    show "e \<in> (\<lambda>u. {v, u}) ` ({..<n} - {v})"
    proof (cases "v = a")
      case True
      then show ?thesis using ab by auto
    next
      case False
      then have "v = b" using e ab by auto
      then show ?thesis using ab by (auto simp: insert_commute)
    qed
  qed
  then have "degree E v \<le> card ((\<lambda>u. {v, u}) ` ({..<n} - {v}))"
    unfolding degree_def by (intro card_mono) auto
  also have "\<dots> \<le> card ({..<n} - {v})"
    by (rule card_image_le) auto
  also have "\<dots> = n - 1"
    using True by simp
  finally show ?thesis .
next
  case False
  have empty: "{e\<in>E. v \<in> e} = {}"
    using assms False unfolding is_edge_set_def by fastforce
  show ?thesis
    unfolding degree_def by (simp add: empty)
qed

subsection \<open>Capacity at least the maximum degree\<close>

text \<open>
Source: proof of Theorem \<open>thm:hardness\<close>, first paragraph: if \<open>\<Delta>(G) \<le> k\<close> then
\<open>\<ell>(v) \<le> deg(v) \<le> k\<close> for any owner map, so valid pairs are connected vertex covers.
Lean counterpart: \<open>exists_validPair_iff_of_maxDegree_le\<close> (Ownership.lean).
\<close>

theorem valid_pair_iff_cvc:
  assumes "finite E" and "\<And>v. degree E v \<le> k"
  shows "(\<exists>own. valid_pair n E k C own) \<longleftrightarrow> connected_vertex_cover n E C"
proof
  assume "\<exists>own. valid_pair n E k C own"
  then show "connected_vertex_cover n E C"
    unfolding valid_pair_def by blast
next
  assume cvc: "connected_vertex_cover n E C"
  define own where "own e = (SOME x. x \<in> e \<and> x \<in> C)" for e :: "nat set"
  have own: "own e \<in> e \<and> own e \<in> C" if "e \<in> E" for e
  proof -
    from cvc that have "e \<inter> C \<noteq> {}"
      unfolding connected_vertex_cover_def vertex_cover_def by blast
    then obtain x where "x \<in> e" "x \<in> C" by blast
    then show ?thesis
      unfolding own_def using someI[where P="\<lambda>y. y \<in> e \<and> y \<in> C"] by blast
  qed
  have "load E own v \<le> k" for v
  proof -
    have "{e\<in>E. own e = v} \<subseteq> {e\<in>E. v \<in> e}"
      using own by auto
    then have "load E own v \<le> degree E v"
      unfolding load_def degree_def using assms(1) by (intro card_mono) auto
    then show ?thesis
      using assms(2) le_trans by blast
  qed
  then have "valid_pair n E k C own"
    using own cvc unfolding valid_pair_def owner_map_def by blast
  then show "\<exists>own. valid_pair n E k C own"
    by blast
qed

subsection \<open>Vertex cover reduces to connected vertex cover\<close>

text \<open>
The paper cites the NP-hardness of connected vertex cover. Here it is proved by the
standard reduction from vertex cover: add a hub \<open>N\<close> adjacent to every vertex. A cover of
size at most \<open>s\<close> of \<open>G\<close> plus the hub is a connected cover of size at most \<open>s + 1\<close>, and a
connected cover of size at most \<open>s + 1\<close> of the new graph yields a cover of size at most
\<open>s\<close> of \<open>G\<close>, either by dropping the hub or, if the hub is missing, by dropping any one vertex
from the then forced set \<open>{0..<N}\<close>.
\<close>

definition add_hub :: "nat \<Rightarrow> nat set set \<Rightarrow> nat set set" where
  "add_hub N E0 \<equiv> E0 \<union> {{a, N} | a. a < N}"

lemma add_hub_is_edge_set:
  assumes "is_edge_set N E0"
  shows "is_edge_set (Suc N) (add_hub N E0)"
  using assms unfolding is_edge_set_def add_hub_def by fastforce

theorem hub_cvc_iff:
  assumes "is_edge_set N E0"
  shows "(\<exists>C'. connected_vertex_cover (Suc N) (add_hub N E0) C' \<and> card C' \<le> Suc s) \<longleftrightarrow>
    (\<exists>C. C \<subseteq> {..<N} \<and> vertex_cover E0 C \<and> card C \<le> s)"
proof
  assume "\<exists>C. C \<subseteq> {..<N} \<and> vertex_cover E0 C \<and> card C \<le> s"
  then obtain C where C: "C \<subseteq> {..<N}" "vertex_cover E0 C" "card C \<le> s"
    by blast
  define C' where "C' = insert N C"
  have fin: "finite C"
    using C(1) finite_subset by blast
  have "C' \<subseteq> {..<Suc N}"
    using C(1) C'_def by auto
  moreover have "vertex_cover (add_hub N E0) C'"
    using C(2) unfolding vertex_cover_def add_hub_def C'_def by auto
  moreover have "connected_on (add_hub N E0) C'"
  proof -
    have hubpath: "(u, N) \<in> ind_rel (add_hub N E0) C'" "(N, u) \<in> ind_rel (add_hub N E0) C'"
      if "u \<in> C" for u
      using that C(1) unfolding ind_rel_def add_hub_def C'_def by (auto simp: insert_commute)
    have "(u, v) \<in> (ind_rel (add_hub N E0) C')\<^sup>*" if "u \<in> C'" "v \<in> C'" for u v
    proof -
      have "(u, N) \<in> (ind_rel (add_hub N E0) C')\<^sup>*"
        using that(1) hubpath(1) unfolding C'_def by auto
      moreover have "(N, v) \<in> (ind_rel (add_hub N E0) C')\<^sup>*"
        using that(2) hubpath(2) unfolding C'_def by auto
      ultimately show ?thesis by simp
    qed
    then show ?thesis
      unfolding connected_on_def C'_def by auto
  qed
  moreover have "card C' \<le> Suc s"
    using C(3) fin card_insert_le_m1 unfolding C'_def
    by (metis card_insert_if le_SucI not_less_eq_eq)
  ultimately show "\<exists>C'. connected_vertex_cover (Suc N) (add_hub N E0) C' \<and> card C' \<le> Suc s"
    unfolding connected_vertex_cover_def by blast
next
  assume "\<exists>C'. connected_vertex_cover (Suc N) (add_hub N E0) C' \<and> card C' \<le> Suc s"
  then obtain C' where C': "C' \<subseteq> {..<Suc N}" "vertex_cover (add_hub N E0) C'"
      "connected_on (add_hub N E0) C'" "card C' \<le> Suc s"
    unfolding connected_vertex_cover_def by blast
  have fin: "finite C'"
    using C'(1) finite_subset by blast
  have E0N: "N \<notin> e" if "e \<in> E0" for e
    using assms that unfolding is_edge_set_def by fastforce
  show "\<exists>C. C \<subseteq> {..<N} \<and> vertex_cover E0 C \<and> card C \<le> s"
  proof (cases "N \<in> C'")
    case True
    define C where "C = C' - {N}"
    have "C \<subseteq> {..<N}"
      using C'(1) C_def by auto
    moreover have "vertex_cover E0 C"
    proof -
      have "e \<inter> C \<noteq> {}" if "e \<in> E0" for e
      proof -
        have "e \<inter> C' \<noteq> {}"
          using C'(2) that unfolding vertex_cover_def add_hub_def by blast
        then show ?thesis
          using E0N[OF that] C_def by blast
      qed
      then show ?thesis unfolding vertex_cover_def by blast
    qed
    moreover have "card C \<le> s"
      using C'(4) True fin C_def by simp
    ultimately show ?thesis by blast
  next
    case False
    have all: "a \<in> C'" if "a < N" for a
    proof -
      have "{a, N} \<in> add_hub N E0"
        using that unfolding add_hub_def by blast
      then have "{a, N} \<inter> C' \<noteq> {}"
        using C'(2) unfolding vertex_cover_def by blast
      then show ?thesis
        using False by blast
    qed
    have C'eq: "C' = {..<N}"
      using all C'(1) False by (auto simp: less_Suc_eq)
    then have "N \<noteq> 0"
      using C'(3) unfolding connected_on_def by auto
    define C where "C = {..<N} - {0}"
    have "C \<subseteq> {..<N}"
      using C_def by auto
    moreover have "vertex_cover E0 C"
    proof -
      have "e \<inter> C \<noteq> {}" if eE: "e \<in> E0" for e
      proof -
        obtain u v where uv: "e = {u, v}" "u \<noteq> v" "u < N" "v < N"
          using is_edge_setD[OF assms eE] by blast
        then show ?thesis
          unfolding C_def by auto
      qed
      then show ?thesis unfolding vertex_cover_def by blast
    qed
    moreover have "card C \<le> s"
      using C'(4) C'eq `N \<noteq> 0` unfolding C_def by simp
    ultimately show ?thesis by blast
  qed
qed

lemma vertex_cover_iff_independent:
  assumes "is_edge_set N E0" and "C \<subseteq> {..<N}"
  shows "vertex_cover E0 C \<longleftrightarrow> independent E0 ({..<N} - C)"
proof -
  have "e \<subseteq> {..<N}" if "e \<in> E0" for e
    using assms(1) that unfolding is_edge_set_def by fastforce
  then show ?thesis
    unfolding vertex_cover_def independent_def by blast
qed

lemma ex_vertex_cover_iff_ex_independent:
  assumes "is_edge_set N E0" and "m \<le> N"
  shows "(\<exists>C. C \<subseteq> {..<N} \<and> vertex_cover E0 C \<and> card C \<le> N - m) \<longleftrightarrow>
    (\<exists>S. S \<subseteq> {..<N} \<and> independent E0 S \<and> m \<le> card S)"
proof
  assume "\<exists>C. C \<subseteq> {..<N} \<and> vertex_cover E0 C \<and> card C \<le> N - m"
  then obtain C where C: "C \<subseteq> {..<N}" "vertex_cover E0 C" "card C \<le> N - m"
    by blast
  have "card ({..<N} - C) = N - card C"
    using C(1) by (simp add: card_Diff_subset finite_subset)
  then have "m \<le> card ({..<N} - C)"
    using C(3) assms(2) by simp
  moreover have "independent E0 ({..<N} - C)"
    using vertex_cover_iff_independent[OF assms(1) C(1)] C(2) by simp
  moreover have "{..<N} - C \<subseteq> {..<N}"
    by (rule Diff_subset)
  ultimately show "\<exists>S. S \<subseteq> {..<N} \<and> independent E0 S \<and> m \<le> card S"
    by (intro exI[of _ "{..<N} - C"]) simp
next
  assume "\<exists>S. S \<subseteq> {..<N} \<and> independent E0 S \<and> m \<le> card S"
  then obtain S where S: "S \<subseteq> {..<N}" "independent E0 S" "m \<le> card S"
    by blast
  define C where "C = {..<N} - S"
  have SC: "{..<N} - C = S"
    using S(1) C_def by auto
  have "C \<subseteq> {..<N}"
    using C_def by auto
  moreover have "vertex_cover E0 C"
    using vertex_cover_iff_independent[OF assms(1) \<open>C \<subseteq> {..<N}\<close>] SC S(2) by simp
  moreover have "card C \<le> N - m"
  proof -
    have "card C = N - card S"
      using S(1) C_def by (simp add: card_Diff_subset finite_subset)
    then show ?thesis
      using S(3) by simp
  qed
  ultimately show "\<exists>C. C \<subseteq> {..<N} \<and> vertex_cover E0 C \<and> card C \<le> N - m"
    by blast
qed

subsection \<open>SAT reduces to independent set (Karp)\<close>

text \<open>
A CNF formula is given in Cook_Levin's number representation: a list \<open>nss\<close> of clauses, a
clause a list of literals, the literal \<open>2i\<close> standing for \<open>\<not>x\<^sub>i\<close> and \<open>2i+1\<close> for \<open>x\<^sub>i\<close>
(\<open>formula_n\<close>, \<open>n_formula\<close>). The vertices of Karp's graph are the literal occurrences,
numbered in reading order; two occurrences are adjacent when they lie in the same clause or
carry complementary literals.
\<close>

definition occ :: "nat list list \<Rightarrow> (nat \<times> nat) list" where
  "occ nss \<equiv> concat (map (\<lambda>j. map (\<lambda>l. (j, l)) (nss ! j)) [0..<length nss])"

definition karp_adj :: "nat list list \<Rightarrow> nat \<Rightarrow> nat \<Rightarrow> bool" where
  "karp_adj nss a b \<equiv>
    fst (occ nss ! a) = fst (occ nss ! b) \<or>
    (snd (occ nss ! a) div 2 = snd (occ nss ! b) div 2 \<and> snd (occ nss ! a) \<noteq> snd (occ nss ! b))"

definition karp_edges :: "nat list list \<Rightarrow> nat set set" where
  "karp_edges nss \<equiv>
    {{a, b} | a b. a < length (occ nss) \<and> b < length (occ nss) \<and> a \<noteq> b \<and> karp_adj nss a b}"

lemma set_occ: "set (occ nss) = {(j, l). j < length nss \<and> l \<in> set (nss ! j)}"
  unfolding occ_def by auto

lemma occ_nth:
  assumes "a < length (occ nss)"
  shows "fst (occ nss ! a) < length nss" "snd (occ nss ! a) \<in> set (nss ! fst (occ nss ! a))"
proof -
  have "occ nss ! a \<in> set (occ nss)"
    using assms by simp
  then show "fst (occ nss ! a) < length nss" "snd (occ nss ! a) \<in> set (nss ! fst (occ nss ! a))"
    using set_occ by auto
qed

lemma occ_index:
  assumes "j < length nss" and "l \<in> set (nss ! j)"
  shows "\<exists>a<length (occ nss). occ nss ! a = (j, l)"
proof -
  have "(j, l) \<in> set (occ nss)"
    using assms set_occ by auto
  then show ?thesis
    by (metis in_set_conv_nth)
qed

lemma karp_edges_is_edge_set: "is_edge_set (length (occ nss)) (karp_edges nss)"
  unfolding is_edge_set_def karp_edges_def by blast

definition lit_true :: "assignment \<Rightarrow> nat \<Rightarrow> bool" where
  "lit_true \<alpha> l \<equiv> (if even l then \<not> \<alpha> (l div 2) else \<alpha> (l div 2))"

lemma satisfiable_n_formula:
  "satisfiable (n_formula nss) \<longleftrightarrow> (\<exists>\<alpha>. \<forall>j<length nss. \<exists>l\<in>set (nss ! j). lit_true \<alpha> l)"
proof -
  have lit: "satisfies_literal \<alpha> (n_literal l) = lit_true \<alpha> l" for \<alpha> l
    unfolding n_literal_def lit_true_def by simp
  have "\<alpha> \<Turnstile> n_formula nss \<longleftrightarrow> (\<forall>j<length nss. \<exists>l\<in>set (nss ! j). lit_true \<alpha> l)" for \<alpha>
  proof -
    have "\<alpha> \<Turnstile> n_formula nss \<longleftrightarrow> (\<forall>c\<in>set nss. \<exists>l\<in>set c. lit_true \<alpha> l)"
      unfolding satisfies_def satisfies_clause_def n_formula_def n_clause_def using lit by auto
    also have "\<dots> \<longleftrightarrow> (\<forall>j<length nss. \<exists>l\<in>set (nss ! j). lit_true \<alpha> l)"
      by (metis in_set_conv_nth)
    finally show ?thesis .
  qed
  then show ?thesis
    unfolding satisfiable_def by simp
qed

lemma complementary_parity:
  fixes x y :: nat
  assumes "x div 2 = y div 2" and "x \<noteq> y"
  shows "even x \<longleftrightarrow> odd y"
proof -
  have "x = 2 * (x div 2) + x mod 2" "y = 2 * (y div 2) + y mod 2"
    by simp_all
  then show ?thesis
    using assms by (metis even_iff_mod_2_eq_zero odd_iff_mod_2_eq_one)
qed

theorem sat_iff_independent:
  "satisfiable (n_formula nss) \<longleftrightarrow>
    (\<exists>S. S \<subseteq> {..<length (occ nss)} \<and> independent (karp_edges nss) S \<and> length nss \<le> card S)"
  (is "?sat \<longleftrightarrow> ?ind")
proof
  let ?N = "length (occ nss)"
  let ?m = "length nss"
  assume ?sat
  then obtain \<alpha> where \<alpha>: "\<forall>j<?m. \<exists>l\<in>set (nss ! j). lit_true \<alpha> l"
    using satisfiable_n_formula by blast
  have "\<forall>j<?m. \<exists>a<?N. fst (occ nss ! a) = j \<and> lit_true \<alpha> (snd (occ nss ! a))"
  proof (intro allI impI)
    fix j assume j: "j < ?m"
    then obtain l where "l \<in> set (nss ! j)" "lit_true \<alpha> l"
      using \<alpha> by blast
    then show "\<exists>a<?N. fst (occ nss ! a) = j \<and> lit_true \<alpha> (snd (occ nss ! a))"
      using occ_index[OF j] by fastforce
  qed
  then obtain f where f: "\<And>j. j < ?m \<Longrightarrow> f j < ?N \<and> fst (occ nss ! f j) = j \<and> lit_true \<alpha> (snd (occ nss ! f j))"
    by metis
  define S where "S = f ` {..<?m}"
  have inj: "inj_on f {..<?m}"
    using f by (metis inj_onI lessThan_iff)
  have "S \<subseteq> {..<?N}"
    using f S_def by auto
  moreover have "card S = ?m"
    using inj S_def by (simp add: card_image)
  moreover have "independent (karp_edges nss) S"
  proof -
    have "\<not> e \<subseteq> S" if "e \<in> karp_edges nss" for e
    proof
      assume sub: "e \<subseteq> S"
      from that obtain a b where ab: "e = {a, b}" "a \<noteq> b" "karp_adj nss a b"
        unfolding karp_edges_def by auto
      then obtain i j where ij: "i < ?m" "j < ?m" "a = f i" "b = f j"
        using sub S_def by auto
      show False
      proof (cases "fst (occ nss ! a) = fst (occ nss ! b)")
        case True
        then have "i = j"
          using f ij by metis
        then show False
          using ab(2) ij by simp
      next
        case False
        then have c: "snd (occ nss ! a) div 2 = snd (occ nss ! b) div 2"
            "snd (occ nss ! a) \<noteq> snd (occ nss ! b)"
          using ab(3) unfolding karp_adj_def by simp_all
        have ta: "lit_true \<alpha> (snd (occ nss ! a))" and tb: "lit_true \<alpha> (snd (occ nss ! b))"
          using f ij by blast+
        have "even (snd (occ nss ! a)) \<longleftrightarrow> odd (snd (occ nss ! b))"
          using complementary_parity[OF c] .
        then show False
          using ta tb c(1) unfolding lit_true_def by (auto split: if_splits)
      qed
    qed
    then show ?thesis unfolding independent_def by blast
  qed
  ultimately show ?ind by auto
next
  let ?N = "length (occ nss)"
  let ?m = "length nss"
  assume ?ind
  then obtain S where S: "S \<subseteq> {..<?N}" "independent (karp_edges nss) S" "?m \<le> card S"
    by blast
  define f where "f a = fst (occ nss ! a)" for a
  have edge: "{a, b} \<in> karp_edges nss" if "a \<in> S" "b \<in> S" "a \<noteq> b" "karp_adj nss a b" for a b
    using that S(1) unfolding karp_edges_def by blast
  have no_edge: "\<not> karp_adj nss a b" if "a \<in> S" "b \<in> S" "a \<noteq> b" for a b
  proof
    assume "karp_adj nss a b"
    then have "{a, b} \<in> karp_edges nss"
      using edge that by blast
    moreover have "{a, b} \<subseteq> S"
      using that by blast
    ultimately show False
      using S(2) unfolding independent_def by blast
  qed
  have inj: "inj_on f S"
    using no_edge unfolding inj_on_def f_def karp_adj_def by blast
  have fS: "f ` S \<subseteq> {..<?m}"
    using S(1) occ_nth f_def by auto
  have "card (f ` S) = card S"
    using inj by (simp add: card_image)
  then have "card {..<?m} \<le> card (f ` S)"
    using S(3) by simp
  then have fS_eq: "f ` S = {..<?m}"
    using fS by (simp add: card_seteq)
  define \<alpha> where "\<alpha> v = (\<exists>a\<in>S. snd (occ nss ! a) = Suc (2 * v))" for v
  have "\<forall>j<?m. \<exists>l\<in>set (nss ! j). lit_true \<alpha> l"
  proof (intro allI impI)
    fix j assume j: "j < ?m"
    then obtain a where a: "a \<in> S" "f a = j"
      using fS_eq by (metis imageE lessThan_iff)
    let ?l = "snd (occ nss ! a)"
    have l: "?l \<in> set (nss ! j)"
      using occ_nth a S(1) f_def by auto
    have "lit_true \<alpha> ?l"
    proof (cases "even ?l")
      case False
      then have "?l = Suc (2 * (?l div 2))"
        by simp
      then have "\<alpha> (?l div 2)"
        unfolding \<alpha>_def using a(1) by metis
      then show ?thesis
        unfolding lit_true_def using False by simp
    next
      case True
      have "\<not> \<alpha> (?l div 2)"
      proof
        assume "\<alpha> (?l div 2)"
        then obtain b where b: "b \<in> S" "snd (occ nss ! b) = Suc (2 * (?l div 2))"
          unfolding \<alpha>_def by blast
        have "?l = 2 * (?l div 2)"
          using True by simp
        then have "snd (occ nss ! b) = Suc ?l"
          using b(2) by simp
        then have "karp_adj nss a b" "a \<noteq> b"
          unfolding karp_adj_def using True by auto
        then show False
          using no_edge a(1) b(1) by blast
      qed
      then show ?thesis
        unfolding lit_true_def using True by simp
    qed
    then show "\<exists>l\<in>set (nss ! j). lit_true \<alpha> l"
      using l by blast
  qed
  then show ?sat
    using satisfiable_n_formula by blast
qed

subsection \<open>The composed reduction at the graph level\<close>

text \<open>
SAT to MWCCVC in one step: Karp's graph plus a hub, unit weights, capacity \<open>k = N\<close>
(every degree is at most \<open>N\<close> on \<open>N + 1\<close> vertices, so \<open>k\<close> is at least the maximum degree, as
in the proof sketch of \<open>thm:hardness\<close>), and bound \<open>B = N + 1 - m\<close> for \<open>N\<close> literal
occurrences and \<open>m\<close> clauses. If \<open>m > N\<close> some clause is empty, the formula is unsatisfiable,
and \<open>B = 0\<close> admits no valid pair because \<open>C\<close> is nonempty.
\<close>

theorem sat_iff_mwccvc_gadget:
  "satisfiable (n_formula nss) \<longleftrightarrow>
    mwccvc_yes (Suc (length (occ nss))) (add_hub (length (occ nss)) (karp_edges nss)) (\<lambda>_. 1)
      (length (occ nss)) (Suc (length (occ nss)) - length nss)"
proof -
  let ?N = "length (occ nss)"
  let ?m = "length nss"
  let ?E = "add_hub ?N (karp_edges nss)"
  have es: "is_edge_set (Suc ?N) ?E"
    using add_hub_is_edge_set karp_edges_is_edge_set by blast
  have deg: "degree ?E v \<le> ?N" for v
    using degree_le[OF es] by simp
  have yes: "mwccvc_yes (Suc ?N) ?E (\<lambda>_. 1) ?N B \<longleftrightarrow>
      (\<exists>C. connected_vertex_cover (Suc ?N) ?E C \<and> card C \<le> B)" for B
    unfolding mwccvc_yes_def
    using valid_pair_iff_cvc[OF is_edge_set_finite[OF es] deg] by simp
  show ?thesis
  proof (cases "?m \<le> ?N")
    case True
    then have B: "Suc ?N - ?m = Suc (?N - ?m)"
      by simp
    show ?thesis
      unfolding yes B
      using hub_cvc_iff[OF karp_edges_is_edge_set]
        ex_vertex_cover_iff_ex_independent[OF karp_edges_is_edge_set True]
        sat_iff_independent
      by simp
  next
    case False
    then have B: "Suc ?N - ?m = 0"
      by simp
    have "\<not> (\<exists>C. connected_vertex_cover (Suc ?N) ?E C \<and> card C \<le> 0)"
    proof
      assume "\<exists>C. connected_vertex_cover (Suc ?N) ?E C \<and> card C \<le> 0"
      then obtain C where "C \<subseteq> {..<Suc ?N}" "C \<noteq> {}" "card C = 0"
        unfolding connected_vertex_cover_def connected_on_def by auto
      then show False
        using finite_subset by fastforce
    qed
    moreover have "\<not> satisfiable (n_formula nss)"
    proof
      assume "satisfiable (n_formula nss)"
      then obtain S where "S \<subseteq> {..<?N}" "?m \<le> card S"
        using sat_iff_independent by blast
      then have "?m \<le> ?N"
        by (metis card_lessThan card_mono finite_lessThan le_trans)
      then show False
        using False by simp
    qed
    ultimately show ?thesis
      unfolding yes B by blast
  qed
qed

end
