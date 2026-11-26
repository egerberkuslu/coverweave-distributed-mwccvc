theory MWCCVC_Language
  imports MWCCVC_Graph
begin

section \<open>MWCCVC as a language and the reduction from SAT\<close>

text \<open>
Instances are written as lists of lists of numbers, the data format of Cook_Levin's Turing
machine library, and then as bit strings exactly as Cook_Levin writes CNF formulas
(\<open>formula_to_string\<close>). The canonical encoding of an instance \<open>(n, E, w, k, B)\<close> is
\<open>[[k, B], [w 0, ..., w (n-1)], [u\<^sub>1, v\<^sub>1, u\<^sub>2, v\<^sub>2, ...]]\<close>, one pair per edge.

Modelling choice: decoding is total. Every list of lists of numbers denotes an instance:
missing components default to empty lists and to 0, a weight entry 0 is read as 1 (so every
decoded weight is positive), pairs \<open>u, v\<close> with \<open>u = v\<close> or an endpoint outside \<open>{0..<n}\<close> are
ignored, repeated pairs denote the same edge, and a trailing unpaired number is ignored. Bit
strings that are not the encoding of any list of lists are not in the language, as Arora and
Barak recommend for invalid strings. Canonical encodings decode to the instance they encode
(\<open>canon_nll_correct\<close>), so the language is the decision version of MWCCVC.
\<close>

definition nth_or :: "'a \<Rightarrow> 'a list \<Rightarrow> nat \<Rightarrow> 'a" where
  "nth_or d xs i \<equiv> if i < length xs then xs ! i else d"

fun pairs :: "nat list \<Rightarrow> (nat \<times> nat) list" where
  "pairs (a # b # xs) = (a, b) # pairs xs"
| "pairs _ = []"

definition edges_of :: "nat \<Rightarrow> nat list \<Rightarrow> nat set set" where
  "edges_of n es \<equiv> {{a, b} | a b. (a, b) \<in> set (pairs es) \<and> a \<noteq> b \<and> a < n \<and> b < n}"

definition hdr_of :: "nat list list \<Rightarrow> nat list" where
  "hdr_of nss \<equiv> nth_or [] nss 0"

definition wts_of :: "nat list list \<Rightarrow> nat list" where
  "wts_of nss \<equiv> nth_or [] nss (Suc 0)"

definition es_of :: "nat list list \<Rightarrow> nat list" where
  "es_of nss \<equiv> nth_or [] nss 2"

definition n_of :: "nat list list \<Rightarrow> nat" where
  "n_of nss \<equiv> length (wts_of nss)"

definition k_of :: "nat list list \<Rightarrow> nat" where
  "k_of nss \<equiv> nth_or 0 (hdr_of nss) 0"

definition B_of :: "nat list list \<Rightarrow> nat" where
  "B_of nss \<equiv> nth_or 0 (hdr_of nss) (Suc 0)"

definition w_of :: "nat list list \<Rightarrow> nat \<Rightarrow> nat" where
  "w_of nss v \<equiv> max 1 (nth_or 0 (wts_of nss) v)"

definition E_of :: "nat list list \<Rightarrow> nat set set" where
  "E_of nss \<equiv> edges_of (n_of nss) (es_of nss)"

definition inst_yes :: "nat list list \<Rightarrow> bool" where
  "inst_yes nss \<equiv> mwccvc_yes (n_of nss) (E_of nss) (w_of nss) (k_of nss) (B_of nss)"

abbreviation nll_to_string :: "nat list list \<Rightarrow> string" where
  "nll_to_string nss \<equiv> symbols_to_string (binencode (numlistlist nss))"

text \<open>The decision version of MWCCVC as a language in the sense of Cook_Levin.\<close>

definition MWCCVC :: language where
  "MWCCVC \<equiv> {nll_to_string nss | nss. inst_yes nss}"

subsection \<open>Basic facts\<close>

lemma pairs_append:
  assumes "even (length xs)"
  shows "pairs (xs @ ys) = pairs xs @ pairs ys"
  using assms by (induction xs rule: pairs.induct) auto

lemma length_pairs: "length (pairs xs) = length xs div 2"
  by (induction xs rule: pairs.induct) auto

lemma nth_pairs:
  assumes "i < length (pairs xs)"
  shows "pairs xs ! i = (xs ! (2 * i), xs ! Suc (2 * i))"
  using assms
proof (induction xs arbitrary: i rule: pairs.induct)
  case (1 a b xs)
  then show ?case
    by (cases i) auto
qed auto

lemma pairs_concat:
  assumes "\<And>x. x \<in> set xs \<Longrightarrow> even (length (f x))"
  shows "pairs (concat (map f xs)) = concat (map (\<lambda>x. pairs (f x)) xs)"
  using assms
proof (induction xs)
  case (Cons x xs)
  then show ?case
    using pairs_append by simp
qed simp

lemma edges_of_is_edge_set: "is_edge_set n (edges_of n es)"
  unfolding is_edge_set_def edges_of_def by blast

lemma numlistlist_wf_iff: "numlistlist_wf zs \<longleftrightarrow> (\<exists>nss. numlistlist nss = zs)"
  using numlistlist_wf_def by simp

lemma binencodable_numlistlist: "binencodable (numlistlist nss)"
  by (simp add: Suc_le_eq numeral_2_eq_2 proper_symbols_numlistlist symbols_lt_numlistlist)

lemma nll_to_string_symbols:
  "string_to_symbols (nll_to_string nss) = binencode (numlistlist nss)"
  using binencodable_numlistlist bit_symbols_binencode bit_symbols_to_symbols by simp

lemma nll_to_string_inj:
  assumes "nll_to_string nss1 = nll_to_string nss2"
  shows "nss1 = nss2"
proof -
  have "string_to_symbols (nll_to_string nss1) = string_to_symbols (nll_to_string nss2)"
    using assms by (rule arg_cong)
  then have "binencode (numlistlist nss1) = binencode (numlistlist nss2)"
    unfolding nll_to_string_symbols .
  then have "numlistlist nss1 = numlistlist nss2"
    using binencode_inj binencodable_numlistlist by metis
  then show ?thesis
    using numlistlist_inj by simp
qed

lemma formula_to_string_eq: "formula_to_string \<phi> = nll_to_string (formula_n \<phi>)"
  by simp

text \<open>A bit string encodes a list of lists of numbers exactly when the Turing machines below
can recognise it: even length and a well-formed decoding.\<close>

lemma ex_nll_iff:
  fixes x :: string
  defines "zs \<equiv> string_to_symbols x"
  shows "(\<exists>nss. x = nll_to_string nss) \<longleftrightarrow> even (length zs) \<and> numlistlist_wf (bindecode zs)"
proof
  assume "\<exists>nss. x = nll_to_string nss"
  then obtain nss where nss: "x = nll_to_string nss"
    by blast
  then have "zs = binencode (numlistlist nss)"
    using zs_def nll_to_string_symbols by simp
  then show "even (length zs) \<and> numlistlist_wf (bindecode zs)"
    using bindecode_encode binencodable_numlistlist numlistlist_wf_def by auto
next
  assume a: "even (length zs) \<and> numlistlist_wf (bindecode zs)"
  then obtain nss where nss: "numlistlist nss = bindecode zs"
    using numlistlist_wf_def by auto
  have "binencode (bindecode zs) = zs"
    using a zs_def binencode_decode by simp
  then have "binencode (numlistlist nss) = zs"
    using nss by simp
  then have "nll_to_string nss = x"
    using zs_def symbols_to_string_to_symbols by metis
  then show "\<exists>nss. x = nll_to_string nss"
    by metis
qed

lemma the_nll:
  assumes "x = nll_to_string nss"
  shows "(THE nss'. numlistlist nss' = bindecode (string_to_symbols x)) = nss"
proof -
  have "bindecode (string_to_symbols x) = numlistlist nss"
    using assms nll_to_string_symbols bindecode_encode binencodable_numlistlist by simp
  then show ?thesis
    using numlistlist_inj by auto
qed

lemma ex_formula_iff_ex_nll: "(\<exists>\<phi>. x = formula_to_string \<phi>) \<longleftrightarrow> (\<exists>nss. x = nll_to_string nss)"
  by (metis formula_n_formula)

subsection \<open>Canonical encodings\<close>

text \<open>Every instance with positive weights has an encoding, and decoding it gives back the
instance; the language is therefore faithful to Definition \<open>def:mwccvc\<close>.\<close>

definition edge_pairs :: "nat \<Rightarrow> nat set set \<Rightarrow> (nat \<times> nat) list" where
  "edge_pairs n E \<equiv>
    concat (map (\<lambda>u. map (\<lambda>v. (u, v)) (filter (\<lambda>v. u < v \<and> {u, v} \<in> E) [0..<n])) [0..<n])"

definition canon_nll :: "nat \<Rightarrow> nat set set \<Rightarrow> (nat \<Rightarrow> nat) \<Rightarrow> nat \<Rightarrow> nat \<Rightarrow> nat list list" where
  "canon_nll n E w k B \<equiv> [[k, B], map w [0..<n], concat (map (\<lambda>(u, v). [u, v]) (edge_pairs n E))]"

lemma mwccvc_yes_cong:
  assumes "\<And>v. v < n \<Longrightarrow> w v = w' v"
  shows "mwccvc_yes n E w k B \<longleftrightarrow> mwccvc_yes n E w' k B"
proof -
  have "sum w C = sum w' C" if "C \<subseteq> {..<n}" for C
    using assms that by (intro sum.cong) auto
  then show ?thesis
    unfolding mwccvc_yes_def valid_pair_def connected_vertex_cover_def by metis
qed

theorem canon_nll_correct:
  assumes "is_edge_set n E" and "\<And>v. v < n \<Longrightarrow> 0 < w v"
  shows "inst_yes (canon_nll n E w k B) \<longleftrightarrow> mwccvc_yes n E w k B"
proof -
  let ?nss = "canon_nll n E w k B"
  let ?P = "{(u, v). u < v \<and> {u, v} \<in> E}"
  have Psub: "?P \<subseteq> {..<n} \<times> {..<n}"
  proof
    fix p assume "p \<in> ?P"
    then obtain u v where p: "p = (u, v)" "u < v" "{u, v} \<in> E"
      by blast
    then obtain a b where "{u, v} = {a, b}" "a < n" "b < n"
      using assms(1) unfolding is_edge_set_def by blast
    then show "p \<in> {..<n} \<times> {..<n}"
      using p by (auto simp: doubleton_eq_iff)
  qed
  have n: "n_of ?nss = n"
    unfolding n_of_def wts_of_def nth_or_def canon_nll_def by simp
  have k: "k_of ?nss = k" and B: "B_of ?nss = B"
    unfolding k_of_def B_of_def hdr_of_def nth_or_def canon_nll_def by simp_all
  have w: "w_of ?nss v = w v" if "v < n" for v
    using that assms(2)[OF that] unfolding w_of_def wts_of_def nth_or_def canon_nll_def
    by (simp add: max_def)
  have "set (pairs (concat (map (\<lambda>(u, v). [u, v]) (edge_pairs n E)))) = ?P"
  proof -
    have "pairs (concat (map (\<lambda>(u, v). [u, v]) ps)) = ps" for ps :: "(nat \<times> nat) list"
      by (induction ps) auto
    then have "set (pairs (concat (map (\<lambda>(u, v). [u, v]) (edge_pairs n E)))) = set (edge_pairs n E)"
      by simp
    also have "\<dots> = {(u, v). u < n \<and> v < n \<and> u < v \<and> {u, v} \<in> E}"
    proof (intro equalityI subsetI)
      fix p assume "p \<in> set (edge_pairs n E)"
      then show "p \<in> {(u, v). u < n \<and> v < n \<and> u < v \<and> {u, v} \<in> E}"
        unfolding edge_pairs_def by auto
    next
      fix p assume "p \<in> {(u, v). u < n \<and> v < n \<and> u < v \<and> {u, v} \<in> E}"
      then obtain u v where uv: "p = (u, v)" "u < n" "v < n" "u < v" "{u, v} \<in> E"
        by blast
      then have "v \<in> set (filter (\<lambda>v. u < v \<and> {u, v} \<in> E) [0..<n])"
        by simp
      then have "(u, v) \<in> set (map (\<lambda>v. (u, v)) (filter (\<lambda>v. u < v \<and> {u, v} \<in> E) [0..<n]))"
        by simp
      then show "p \<in> set (edge_pairs n E)"
        unfolding edge_pairs_def using uv(1,2) by auto
    qed
    also have "\<dots> = ?P"
      using Psub by auto
    finally show ?thesis .
  qed
  then have es: "set (pairs (es_of ?nss)) = ?P"
    unfolding es_of_def nth_or_def canon_nll_def by simp
  have E: "E_of ?nss = E"
  proof
    show "E_of ?nss \<subseteq> E"
      unfolding E_of_def edges_of_def es n by (auto simp: insert_commute)
    show "E \<subseteq> E_of ?nss"
    proof
      fix e assume e: "e \<in> E"
      then obtain a b where ab: "e = {a, b}" "a \<noteq> b" "a < n" "b < n"
        using assms(1) unfolding is_edge_set_def by blast
      show "e \<in> E_of ?nss"
      proof (cases "a < b")
        case True
        then have "(a, b) \<in> set (pairs (es_of ?nss))"
          using es e ab by simp
        then show ?thesis
          unfolding E_of_def edges_of_def n using ab by blast
      next
        case False
        then have "b < a"
          using ab(2) by simp
        then have "(b, a) \<in> set (pairs (es_of ?nss))"
          using es e ab by (simp add: insert_commute)
        then show ?thesis
          unfolding E_of_def edges_of_def n using ab by (auto simp: insert_commute)
      qed
    qed
  qed
  show ?thesis
    unfolding inst_yes_def n k B E using mwccvc_yes_cong[of n "w_of ?nss" w] w by simp
qed

subsection \<open>The reduction from SAT\<close>

definition gadget_row :: "nat list list \<Rightarrow> nat \<Rightarrow> nat list" where
  "gadget_row nss a \<equiv>
    concat (map (\<lambda>b. if karp_adj nss a b then [a, b] else []) [0..<length (occ nss)]) @
    [a, length (occ nss)]"

definition gadget_es :: "nat list list \<Rightarrow> nat list" where
  "gadget_es nss \<equiv> concat (map (gadget_row nss) [0..<length (occ nss)])"

definition gadget_nll :: "nat list list \<Rightarrow> nat list list" where
  "gadget_nll nss \<equiv>
    [[length (occ nss), Suc (length (occ nss)) - length nss],
     replicate (Suc (length (occ nss))) 0,
     gadget_es nss]"

lemma set_pairs_gadget_es:
  "set (pairs (gadget_es nss)) =
    {(a, b). a < length (occ nss) \<and> b < length (occ nss) \<and> karp_adj nss a b} \<union>
    {(a, length (occ nss)) | a. a < length (occ nss)}"
proof -
  let ?N = "length (occ nss)"
  have ev_inner: "even (length (if karp_adj nss a b then [a, b] else []))" for a b
    by simp
  have pinner: "pairs (concat (map (\<lambda>b. if karp_adj nss a b then [a, b] else []) xs)) =
      concat (map (\<lambda>b. if karp_adj nss a b then [(a, b)] else []) xs)" for a xs
    by (subst pairs_concat) (auto intro: arg_cong[where f=concat])
  have ev_row: "even (length (gadget_row nss a))" for a
  proof -
    have "even (length (concat (map (\<lambda>b. if karp_adj nss a b then [a, b] else []) xs)))"
      for xs :: "nat list"
      by (induction xs) auto
    then show ?thesis
      unfolding gadget_row_def by simp
  qed
  have prow: "pairs (gadget_row nss a) =
      concat (map (\<lambda>b. if karp_adj nss a b then [(a, b)] else []) [0..<?N]) @ [(a, ?N)]" for a
  proof -
    have "even (length (concat (map (\<lambda>b. if karp_adj nss a b then [a, b] else []) [0..<?N])))"
      using ev_row unfolding gadget_row_def by simp
    then show ?thesis
      unfolding gadget_row_def using pairs_append pinner by simp
  qed
  have "pairs (gadget_es nss) = concat (map (\<lambda>a. pairs (gadget_row nss a)) [0..<?N])"
    unfolding gadget_es_def by (rule pairs_concat, rule ev_row)
  then show ?thesis
    using prow by auto
qed

lemma edges_of_gadget:
  "edges_of (Suc (length (occ nss))) (gadget_es nss) = add_hub (length (occ nss)) (karp_edges nss)"
proof (intro equalityI subsetI)
  let ?N = "length (occ nss)"
  have P: "set (pairs (gadget_es nss)) =
    {(a, b). a < ?N \<and> b < ?N \<and> karp_adj nss a b} \<union> {(a, ?N) | a. a < ?N}"
    by (rule set_pairs_gadget_es)
  fix e assume "e \<in> edges_of (Suc ?N) (gadget_es nss)"
  then obtain a b where ab: "e = {a, b}" "(a, b) \<in> set (pairs (gadget_es nss))" "a \<noteq> b"
    unfolding edges_of_def by blast
  then have "(a < ?N \<and> b < ?N \<and> karp_adj nss a b) \<or> (a < ?N \<and> b = ?N)"
    using P by blast
  then show "e \<in> add_hub ?N (karp_edges nss)"
  proof
    assume "a < ?N \<and> b < ?N \<and> karp_adj nss a b"
    then have "e \<in> karp_edges nss"
      unfolding karp_edges_def using ab(1,3) by blast
    then show ?thesis
      unfolding add_hub_def by blast
  next
    assume "a < ?N \<and> b = ?N"
    then show ?thesis
      unfolding add_hub_def using ab(1) by blast
  qed
next
  let ?N = "length (occ nss)"
  have P: "set (pairs (gadget_es nss)) =
    {(a, b). a < ?N \<and> b < ?N \<and> karp_adj nss a b} \<union> {(a, ?N) | a. a < ?N}"
    by (rule set_pairs_gadget_es)
  fix e assume "e \<in> add_hub ?N (karp_edges nss)"
  then have "e \<in> karp_edges nss \<or> (\<exists>a. e = {a, ?N} \<and> a < ?N)"
    unfolding add_hub_def by blast
  then show "e \<in> edges_of (Suc ?N) (gadget_es nss)"
  proof
    assume "e \<in> karp_edges nss"
    then obtain a b where ab: "e = {a, b}" "a < ?N" "b < ?N" "a \<noteq> b" "karp_adj nss a b"
      unfolding karp_edges_def by blast
    then have "(a, b) \<in> set (pairs (gadget_es nss))"
      using P by blast
    moreover have "a < Suc ?N" "b < Suc ?N"
      using ab by simp_all
    ultimately show ?thesis
      unfolding edges_of_def using ab by blast
  next
    assume "\<exists>a. e = {a, ?N} \<and> a < ?N"
    then obtain a where a: "e = {a, ?N}" "a < ?N"
      by blast
    then have "(a, ?N) \<in> set (pairs (gadget_es nss))"
      using P by blast
    moreover have "a < Suc ?N" "?N < Suc ?N" "a \<noteq> ?N"
      using a by simp_all
    ultimately show ?thesis
      unfolding edges_of_def using a by blast
  qed
qed

theorem inst_yes_gadget: "inst_yes (gadget_nll nss) \<longleftrightarrow> satisfiable (n_formula nss)"
proof -
  let ?nss = "gadget_nll nss"
  let ?N = "length (occ nss)"
  have n: "n_of ?nss = Suc ?N"
    unfolding n_of_def wts_of_def nth_or_def gadget_nll_def by simp
  have k: "k_of ?nss = ?N" and B: "B_of ?nss = Suc ?N - length nss"
    unfolding k_of_def B_of_def hdr_of_def nth_or_def gadget_nll_def by simp_all
  have w: "w_of ?nss = (\<lambda>_. 1)"
  proof
    fix v
    show "w_of ?nss v = 1"
      unfolding w_of_def wts_of_def nth_or_def gadget_nll_def
      by (simp add: nth_Cons' split: if_split)
  qed
  have E: "E_of ?nss = add_hub ?N (karp_edges nss)"
    unfolding E_of_def n using edges_of_gadget
    by (simp add: es_of_def nth_or_def gadget_nll_def)
  show ?thesis
    unfolding inst_yes_def n k B w E using sat_iff_mwccvc_gadget by simp
qed

text \<open>A fixed yes-instance for the strings that do not encode a formula (they belong to
\<open>SAT\<close> by Cook_Levin's convention): one vertex of weight 1, no edges, \<open>k = 0\<close>, \<open>B = 1\<close>.\<close>

definition yes_nll :: "nat list list" where
  "yes_nll \<equiv> [[0, 1], [0], []]"

lemma inst_yes_yes_nll: "inst_yes yes_nll"
proof -
  have n: "n_of yes_nll = 1" and E: "E_of yes_nll = {}"
    unfolding n_of_def wts_of_def E_of_def edges_of_def es_of_def nth_or_def yes_nll_def by simp_all
  have k: "k_of yes_nll = 0" and B: "B_of yes_nll = 1"
    unfolding k_of_def B_of_def hdr_of_def nth_or_def yes_nll_def by simp_all
  have w: "w_of yes_nll 0 = 1"
    unfolding w_of_def wts_of_def nth_or_def yes_nll_def by simp
  have "valid_pair 1 {} 0 {0} (\<lambda>_. 0)"
    unfolding valid_pair_def connected_vertex_cover_def vertex_cover_def connected_on_def
      owner_map_def load_def by auto
  then show ?thesis
    unfolding inst_yes_def mwccvc_yes_def n E k B using w by fastforce
qed

definition sat_red :: "string \<Rightarrow> string" where
  "sat_red x \<equiv>
    if \<exists>nss. x = nll_to_string nss
    then nll_to_string (gadget_nll (THE nss. x = nll_to_string nss))
    else nll_to_string yes_nll"

theorem sat_red_correct: "x \<in> SAT \<longleftrightarrow> sat_red x \<in> MWCCVC"
proof (cases "\<exists>nss. x = nll_to_string nss")
  case True
  then obtain nss where nss: "x = nll_to_string nss"
    by blast
  have the: "(THE nss. x = nll_to_string nss) = nss"
    using nss nll_to_string_inj by blast
  have "x \<in> SAT \<longleftrightarrow> satisfiable (n_formula nss)"
  proof
    assume "x \<in> SAT"
    moreover have "x = formula_to_string (n_formula nss)"
      using nss formula_n_formula by simp
    ultimately obtain \<phi> where "x = formula_to_string \<phi>" "satisfiable \<phi>"
      unfolding SAT_def by blast
    then show "satisfiable (n_formula nss)"
      using \<open>x = formula_to_string (n_formula nss)\<close> formula_to_string_inj by metis
  next
    assume "satisfiable (n_formula nss)"
    moreover have "x = formula_to_string (n_formula nss)"
      using nss formula_n_formula by simp
    ultimately show "x \<in> SAT"
      unfolding SAT_def by blast
  qed
  also have "\<dots> \<longleftrightarrow> inst_yes (gadget_nll nss)"
    using inst_yes_gadget by simp
  also have "\<dots> \<longleftrightarrow> nll_to_string (gadget_nll nss) \<in> MWCCVC"
    unfolding MWCCVC_def using nll_to_string_inj by blast
  finally show ?thesis
    unfolding sat_red_def using True the by simp
next
  case False
  then have "x \<in> SAT"
    unfolding SAT_def using ex_formula_iff_ex_nll by blast
  moreover have "sat_red x \<in> MWCCVC"
    unfolding sat_red_def MWCCVC_def using False inst_yes_yes_nll by auto
  ultimately show ?thesis
    by simp
qed

end
