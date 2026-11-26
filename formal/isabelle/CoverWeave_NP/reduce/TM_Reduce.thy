theory TM_Reduce
  imports TM_Edges
begin

section \<open>The reduction machine, phase 3: header and output\<close>

text \<open>
Phase 3 computes the bound \<open>N + 1 - m\<close> on tape 26 (tape 27 counts down \<open>m\<close>), writes the
header \<open>[N, N + 1 - m]\<close> to tape 28, assembles the instance \<open>[header, weights, edges]\<close> on tape 29
and writes its binary encoding to the output tape 1.
\<close>

definition tm_head :: machine where
  "tm_head \<equiv>
    tm_copyn 11 26 ;;
    tm_incr 26 ;;
    tm_copyn 8 27 ;;
    WHILE [] ; \<lambda>rs. rs ! 27 \<noteq> \<box> DO
      tm_decr 26 ;;
      tm_decr 27
    DONE ;;
    tm_append 28 11 ;;
    tm_append 28 26 ;;
    tm_cr 28 ;;
    tm_cr 24 ;;
    tm_cr 23 ;;
    tm_appendl 29 28 ;;
    tm_appendl 29 24 ;;
    tm_appendl 29 23 ;;
    tm_cr 29 ;;
    tm_binencode 29 1"

lemma tm_head_tm:
  assumes "29 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_head"
  unfolding tm_head_def
  using assms tm_copyn_tm tm_incr_tm tm_decr_tm tm_append_tm tm_cr_tm tm_appendl_tm tm_binencode_tm
    turing_machine_loop_turing_machine Nil_tm
  by simp

locale turing_machine_head
begin

definition "tm1 \<equiv> tm_copyn 11 26"
definition "tm2 \<equiv> tm1 ;; tm_incr 26"
definition "tm3 \<equiv> tm2 ;; tm_copyn 8 27"
definition "tmL \<equiv> WHILE [] ; \<lambda>rs. rs ! 27 \<noteq> \<box> DO tm_decr 26 ;; tm_decr 27 DONE"
definition "tm4 \<equiv> tm3 ;; tmL"
definition "tm5 \<equiv> tm4 ;; tm_append 28 11"
definition "tm6 \<equiv> tm5 ;; tm_append 28 26"
definition "tm7 \<equiv> tm6 ;; tm_cr 28"
definition "tm8 \<equiv> tm7 ;; tm_cr 24"
definition "tm9 \<equiv> tm8 ;; tm_cr 23"
definition "tm10 \<equiv> tm9 ;; tm_appendl 29 28"
definition "tm11 \<equiv> tm10 ;; tm_appendl 29 24"
definition "tm12 \<equiv> tm11 ;; tm_appendl 29 23"
definition "tm13 \<equiv> tm12 ;; tm_cr 29"
definition "tm14 \<equiv> tm13 ;; tm_binencode 29 1"

lemma tm14_eq_tm_head: "tm14 = tm_head"
  unfolding tm14_def tm13_def tm12_def tm11_def tm10_def tm9_def tm8_def tm7_def tm6_def tm5_def
    tm4_def tmL_def tm3_def tm2_def tm1_def tm_head_def
  by simp

context
  fixes tps0 :: "tape list" and k N m :: nat and W ES :: "nat list"
  assumes k: "29 < k" "length tps0 = k"
  assumes tps0:
    "tps0 ! 1 = (\<lfloor>[]\<rfloor>, 1)"
    "tps0 ! 8 = (\<lfloor>m\<rfloor>\<^sub>N, 1)"
    "tps0 ! 11 = (\<lfloor>N\<rfloor>\<^sub>N, 1)"
    "tps0 ! 23 = nltape ES"
    "tps0 ! 24 = nltape W"
    "tps0 ! 26 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 27 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 28 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 29 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
begin

definition "hd0 \<equiv> [N, Suc N - m]"
definition "out \<equiv> [hd0, W, ES]"
definition "zs \<equiv> numlistlist out"

definition tpsL :: "nat \<Rightarrow> tape list" where
  "tpsL t \<equiv> tps0[26 := (\<lfloor>Suc N - t\<rfloor>\<^sub>N, 1), 27 := (\<lfloor>m - t\<rfloor>\<^sub>N, 1)]"

lemma tm3 [transforms_intros]:
  assumes "ttt = 33 + 5 * N + 3 * m"
  shows "transforms tm3 tps0 ttt (tpsL 0)"
  unfolding tm3_def tm2_def tm1_def
  apply (rule transforms_monotone)
   apply (tform tps: tps0 k)
   apply (tps_eq rules: tpsL_def k tps0)?
  by (lin facts: assms nlength_le_n[of N] nlength_le_n[of m])

lemma tmL_body [transforms_intros]:
  assumes "t < m" "ttt = 16 + 2 * Suc N + 2 * m"
  shows "transforms (tm_decr 26 ;; tm_decr 27) (tpsL t) ttt (tpsL (Suc t))"
  apply (rule transforms_monotone)
   apply (tform tps: tpsL_def k)
   apply (tps_eq rules: tpsL_def k)?
  using assms nlength_le_n[of "Suc N - t"] nlength_le_n[of "m - t"] by simp

lemma read_tpsL: "read (tpsL t) ! 27 \<noteq> \<box> \<longleftrightarrow> t < m"
proof -
  have "tpsL t ! 27 = (\<lfloor>m - t\<rfloor>\<^sub>N, 1)" "27 < length (tpsL t)"
    using k by (simp_all add: tpsL_def)
  from read_ncontents_eq_0[OF this] show ?thesis
    by (simp add: not_le)
qed

lemma tmL [transforms_intros]:
  assumes "ttt = m * (18 + 2 * Suc N + 2 * m) + 1"
  shows "transforms tmL (tpsL 0) ttt (tpsL m)"
  unfolding tmL_def
  by (tform tps: read_tpsL time: assms)

lemma tm4 [transforms_intros]:
  assumes "ttt = 33 + 5 * N + 3 * m + (m * (18 + 2 * Suc N + 2 * m) + 1)"
  shows "transforms tm4 tps0 ttt (tpsL m)"
  unfolding tm4_def
  by (tform time: assms)

definition "tpsE \<equiv> tps0
  [26 := (\<lfloor>Suc N - m\<rfloor>\<^sub>N, 1),
   23 := (\<lfloor>ES\<rfloor>\<^sub>N\<^sub>L, 1),
   24 := (\<lfloor>W\<rfloor>\<^sub>N\<^sub>L, 1),
   28 := (\<lfloor>hd0\<rfloor>\<^sub>N\<^sub>L, 1),
   29 := (\<lfloor>out\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)]"

lemma tm13:
  assumes "ttt = 33 + 5 * N + 3 * m + (m * (18 + 2 * Suc N + 2 * m) + 1) +
    100 * Suc (nllength ES + nllength W + N + m)"
  shows "transforms tm13 tps0 ttt tpsE"
  unfolding tm13_def tm12_def tm11_def tm10_def tm9_def tm8_def tm7_def tm6_def tm5_def
  apply (rule transforms_monotone)
   apply (tform tps: tps0 k tpsL_def clean_tape_nlcontents clean_tape_nllcontents)
   apply (tps_eq rules: tpsE_def tpsL_def k tps0 hd0_def out_def)?
  using assms nlength_le_n[of N] nlength_le_n[of "Suc N"] nlength_mono[of "Suc N - m" "Suc N"] k
  by (simp add: tpsL_def tps0 nlllength nllength nth_list_update_if)

definition "T13 \<equiv> 33 + 5 * N + 3 * m + (m * (18 + 2 * Suc N + 2 * m) + 1) +
    100 * Suc (nllength ES + nllength W + N + m)"

definition "tpsF \<equiv> tpsE
  [29 := (\<lfloor>zs\<rfloor>, Suc (length zs)),
   1 := (\<lfloor>binencode zs\<rfloor>, Suc (2 * length zs))]"

lemma k1: "Suc 0 < k"
  using k by linarith

lemma tm14:
  assumes "ttt = T13 + (9 * length zs + 1)"
  shows "transforms tm14 tps0 ttt tpsF"
  unfolding tm14_def
proof (rule transforms_tm_sequentialI[OF tm13[OF meta_eq_to_obj_eq[OF T13_def]]])
  show "transforms (tm_binencode 29 1) tpsE (9 * length zs + 1) tpsF"
  proof (rule transforms_tm_binencodeI[where zs=zs and k=k])
    show "binencodable zs"
      unfolding zs_def by (rule binencodable_numlistlist)
    show "tpsE ! 29 = (\<lfloor>zs\<rfloor>, 1)"
      unfolding tpsE_def zs_def using k by (simp add: nllcontents_def)
    show "tpsE ! 1 = (\<lfloor>[]\<rfloor>, 1)"
      unfolding tpsE_def using k tps0 by simp
    show "tpsF \<equiv> tpsE[29 := (\<lfloor>zs\<rfloor>, Suc (length zs)), 1 := (\<lfloor>binencode zs\<rfloor>, Suc (2 * length zs))]"
      unfolding tpsF_def .
  qed (use k k1 in \<open>simp_all add: tpsE_def\<close>)
qed (use assms k k1 in simp_all)

end

end

lemma transforms_tm_headI [transforms_intros]:
  fixes tps tps' :: "tape list" and k ttt N m :: nat and W ES :: "nat list"
  assumes "29 < k" "length tps = k"
  assumes
    "tps ! 1 = (\<lfloor>[]\<rfloor>, 1)"
    "tps ! 8 = (\<lfloor>m\<rfloor>\<^sub>N, 1)"
    "tps ! 11 = (\<lfloor>N\<rfloor>\<^sub>N, 1)"
    "tps ! 23 = nltape ES"
    "tps ! 24 = nltape W"
    "tps ! 26 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 27 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 28 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 29 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
  assumes "ttt = 33 + 5 * N + 3 * m + (m * (18 + 2 * Suc N + 2 * m) + 1) +
    100 * Suc (nllength ES + nllength W + N + m) + (9 * nlllength [[N, Suc N - m], W, ES] + 1)"
  assumes "tps' = tps
    [26 := (\<lfloor>Suc N - m\<rfloor>\<^sub>N, 1),
     23 := (\<lfloor>ES\<rfloor>\<^sub>N\<^sub>L, 1),
     24 := (\<lfloor>W\<rfloor>\<^sub>N\<^sub>L, 1),
     28 := (\<lfloor>[N, Suc N - m]\<rfloor>\<^sub>N\<^sub>L, 1),
     29 := (\<lfloor>[[N, Suc N - m], W, ES]\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1),
     29 := (\<lfloor>numlistlist [[N, Suc N - m], W, ES]\<rfloor>, Suc (nlllength [[N, Suc N - m], W, ES])),
     1 := (\<lfloor>binencode (numlistlist [[N, Suc N - m], W, ES])\<rfloor>,
       Suc (2 * nlllength [[N, Suc N - m], W, ES]))]"
  shows "transforms tm_head tps ttt tps'"
proof -
  interpret loc: turing_machine_head .
  have "length (numlistlist [[N, Suc N - m], W, ES]) = nlllength [[N, Suc N - m], W, ES]"
    by (simp add: nlllength_def)
  then show ?thesis
    using loc.tm14[OF assms(1-11)] loc.tpsF_def[OF assms(1-11)] loc.tpsE_def[OF assms(1-11)]
      loc.T13_def[OF assms(1-11)] loc.zs_def[OF assms(1-11)] loc.out_def[OF assms(1-11)]
      loc.hd0_def[OF assms(1-11)] loc.tm14_eq_tm_head assms(12,13)
    by simp
qed


section \<open>The reduction machine\<close>

text \<open>
The machine decodes its input, checks that it is the encoding of a list of lists of numbers,
replaces it by the empty list otherwise, and runs the three phases. Every list of lists of
numbers encodes a CNF formula (@{thm formula_n_formula}), so the machine computes the gadget
of the formula, and for inputs that encode no formula it computes the gadget of the empty
formula, which is the fixed yes instance @{const yes_nll}.
\<close>

definition tm_red :: machine where
  "tm_red \<equiv>
    tm_right_many {0..<30} ;;
    tm_bindecode 0 2 ;;
    tm_even_length 0 3 ;;
    tm_numlistlist_wf 2 4 ;;
    tm_and 3 4 ;;
    IF \<lambda>rs. rs ! 3 = \<box> THEN tm_erase_cr 2 ELSE [] ENDIF ;;
    tm_occ ;;
    tm_cr 9 ;;
    tm_cr 10 ;;
    tm_count 10 11 \<bar> ;;
    tm_edges ;;
    tm_head"

lemma tm_red_tm: "turing_machine 30 6 tm_red"
  unfolding tm_red_def
  using tm_right_many_tm tm_bindecode_tm tm_even_length_tm tm_numlistlist_wf_tm tm_and_tm
    tm_erase_cr_tm tm_occ_tm tm_cr_tm tm_count_tm tm_edges_tm tm_head_tm Nil_tm
    turing_machine_branch_turing_machine
  by simp

definition red_nll :: "symbol list \<Rightarrow> nat list list" where
  "red_nll zs \<equiv>
    if even (length zs) \<and> numlistlist_wf (bindecode zs)
    then (THE nss. numlistlist nss = bindecode zs) else []"

lemma red_nll_ok:
  assumes "even (length zs) \<and> numlistlist_wf (bindecode zs)"
  shows "numlistlist (red_nll zs) = bindecode zs"
proof -
  obtain nss where "numlistlist nss = bindecode zs"
    using assms numlistlist_wf_def by auto
  moreover from this have "(THE nss. numlistlist nss = bindecode zs) = nss"
    using numlistlist_inj by auto
  ultimately show ?thesis
    unfolding red_nll_def using assms by simp
qed

lemma red_nll_size: "nlllength (red_nll zs) \<le> length zs"
proof (cases "even (length zs) \<and> numlistlist_wf (bindecode zs)")
  case True
  then have "nlllength (red_nll zs) = length (bindecode zs)"
    using red_nll_ok by (metis nlllength_def)
  then show ?thesis
    by simp
next
  case False
  then show ?thesis
    unfolding red_nll_def by auto
qed

lemma sat_red_red_nll:
  "sat_red x = symbols_to_string (binencode (numlistlist (gadget_nll (red_nll (string_to_symbols x)))))"
proof (cases "\<exists>nss. x = nll_to_string nss")
  case True
  then obtain nss where nss: "x = nll_to_string nss"
    by blast
  have ok: "even (length (string_to_symbols x)) \<and> numlistlist_wf (bindecode (string_to_symbols x))"
    using ex_nll_iff True by blast
  have "numlistlist (red_nll (string_to_symbols x)) = numlistlist nss"
    using red_nll_ok[OF ok] nss nll_to_string_symbols bindecode_encode binencodable_numlistlist by simp
  then have "red_nll (string_to_symbols x) = nss"
    using numlistlist_inj by simp
  moreover have "(THE nss. x = nll_to_string nss) = nss"
    using nss nll_to_string_inj by blast
  ultimately show ?thesis
    unfolding sat_red_def using True nss by simp
next
  case False
  then have "\<not> (even (length (string_to_symbols x)) \<and> numlistlist_wf (bindecode (string_to_symbols x)))"
    using ex_nll_iff by blast
  then have "red_nll (string_to_symbols x) = []"
    unfolding red_nll_def by auto
  moreover have "gadget_nll [] = yes_nll"
    unfolding gadget_nll_def yes_nll_def gadget_es_def occ_def by simp
  ultimately show ?thesis
    unfolding sat_red_def using False by simp
qed

lemma map_upt_nth: "map f xs = map (\<lambda>i. f (xs ! i)) [0..<length xs]"
proof -
  have "map f xs = map f (map (\<lambda>i. xs ! i) [0..<length xs])"
    by (simp add: map_nth)
  then show ?thesis
    by simp
qed

lemma map_snd_occ: "map snd (occ nss) = concat nss"
proof -
  have "map snd (occ nss) = concat (map (\<lambda>j. nss ! j) [0..<length nss])"
    unfolding occ_def by (simp add: map_concat comp_def)
  then show ?thesis
    using map_upt_nth[of "\<lambda>x. x" nss] by simp
qed

lemma length_occ: "length (occ nss) = length (concat nss)"
  using map_snd_occ[of nss] length_map by metis

lemma fst_occ_lt: "x \<in> set (map fst (occ nss)) \<Longrightarrow> x < length nss"
  using set_occ by auto

lemma length_concat_adjp: "length (concat (map (adjp CL LIT a) xs)) \<le> 2 * length xs"
  by (induction xs) (auto simp: adjp_def)

lemma length_ees: "length (ees CL LIT) \<le> length CL * (2 * length CL + 2)"
proof -
  have "length (erow CL LIT a) \<le> 2 * length CL + 2" for a
    unfolding erow_def using length_concat_adjp[of CL LIT a "[0..<length CL]"] by simp
  then have "length (concat (map (erow CL LIT) xs)) \<le> length xs * (2 * length CL + 2)" for xs
  proof (induction xs)
    case (Cons x xs)
    have "length (erow CL LIT x) + length (concat (map (erow CL LIT) xs)) \<le>
        (2 * length CL + 2) + length xs * (2 * length CL + 2)"
      by (rule add_mono[OF Cons.prems Cons.IH[OF Cons.prems]])
    then show ?case
      by simp
  qed simp
  then show ?thesis
    unfolding ees_def by (metis length_upt minus_nat.diff_0)
qed

lemma set_ees: "x \<in> set (ees CL LIT) \<Longrightarrow> x \<le> length CL"
  unfolding ees_def erow_def adjp_def by (auto split: if_splits)

lemma pow_chain:
  fixes S :: nat
  assumes "1 \<le> S"
  shows "S \<le> S ^ 2" "S ^ 2 \<le> S ^ 3" "S ^ 3 \<le> S ^ 8" "S \<le> S ^ 8" "S ^ 2 \<le> S ^ 8" "1 \<le> S ^ 8"
  using assms power_increasing[of 1 2 S] power_increasing[of 2 3 S] power_increasing[of 3 8 S]
    power_increasing[of 1 8 S] power_increasing[of 2 8 S] by simp_all

locale turing_machine_red
begin

definition "tm1 \<equiv> tm_right_many {0..<30}"
definition "tm2 \<equiv> tm1 ;; tm_bindecode 0 2"
definition "tm3 \<equiv> tm2 ;; tm_even_length 0 3"
definition "tm4 \<equiv> tm3 ;; tm_numlistlist_wf 2 4"
definition "tm5 \<equiv> tm4 ;; tm_and 3 4"
definition "tmI \<equiv> IF \<lambda>rs. rs ! 3 = \<box> THEN tm_erase_cr 2 ELSE [] ENDIF"
definition "tm6 \<equiv> tm5 ;; tmI"
definition "tm7 \<equiv> tm6 ;; tm_occ"
definition "tm8 \<equiv> tm7 ;; tm_cr 9"
definition "tm9 \<equiv> tm8 ;; tm_cr 10"
definition "tm10 \<equiv> tm9 ;; tm_count 10 11 \<bar>"
definition "tm11 \<equiv> tm10 ;; tm_edges"
definition "tm12 \<equiv> tm11 ;; tm_head"

lemma tm12_eq_tm_red: "tm12 = tm_red"
  unfolding tm12_def tm11_def tm10_def tm9_def tm8_def tm7_def tm6_def tmI_def tm5_def tm4_def
    tm3_def tm2_def tm1_def tm_red_def
  by simp

context
  fixes tps0 :: "tape list" and zs :: "symbol list"
  assumes zs: "bit_symbols zs"
  assumes tps0: "tps0 = snd (start_config 30 zs)"
begin

definition "tps1 \<equiv> map (\<lambda>tp. tp |#=| 1) tps0"

lemma tps1:
  "tps1 ! 0 = (\<lfloor>zs\<rfloor>, 1)"
  "0 < j \<Longrightarrow> j < 30 \<Longrightarrow> tps1 ! j = (\<lfloor>[]\<rfloor>, 1)"
  "length tps1 = 30"
  using tps0 start_config_def tps1_def by auto

lemma tm1 [transforms_intros]: "transforms tm1 tps0 1 tps1"
  unfolding tm1_def
proof (tform tps: tps0 tps1_def)
  have "length tps0 = 30"
    using tps0 start_config_def by simp
  then have "map (\<lambda>j. if j \<in> {0..<30} then tps0 ! j |+| 1 else tps0 ! j) [0..<length tps0] =
      map (\<lambda>j. tps0 ! j |+| 1) [0..<length tps0]"
    by simp
  also have "\<dots> = map (\<lambda>j. tps0 ! j |#=| 1) [0..<length tps0]"
    using tps0 \<open>length tps0 = 30\<close> start_config_pos by simp
  also have "\<dots> = map (\<lambda>tp. tp |#=| 1) tps0"
    using map_upt_nth[of "\<lambda>tp. tp |#=| 1" tps0] by simp
  also have "\<dots> = tps1"
    using tps1_def by simp
  finally show "tps1 = map (\<lambda>j. if j \<in> {0..<30} then tps0 ! j |+| 1 else tps0 ! j) [0..<length tps0]"
    by simp
qed

abbreviation "ok \<equiv> even (length zs) \<and> numlistlist_wf (bindecode zs)"

definition "tps5 \<equiv> tps1
  [2 := (\<lfloor>bindecode zs\<rfloor>, 1),
   3 := (\<lfloor>ok\<rfloor>\<^sub>B, 1),
   4 := (\<lfloor>numlistlist_wf (bindecode zs)\<rfloor>\<^sub>B, 1)]"

lemma tm5 [transforms_intros]:
  assumes "ttt = 224 + 10 * length zs + 39 * length (bindecode zs)"
  shows "transforms tm5 tps0 ttt tps5"
  unfolding tm5_def tm4_def tm3_def tm2_def
  apply (tform tps: assms zs tps1 proper_bindecode proper_bit_symbols[OF zs] canrepr_0 time: assms)
   apply (use proper_bindecode[of zs] in simp)
  by (tps_eq rules: tps5_def tps1)

abbreviation "nss \<equiv> red_nll zs"
abbreviation "CL \<equiv> map fst (occ nss)"
abbreviation "LIT \<equiv> map snd (occ nss)"
abbreviation "N \<equiv> length (occ nss)"
abbreviation "m \<equiv> length nss"
abbreviation "ES \<equiv> ees CL LIT"
abbreviation "W \<equiv> replicate (Suc N) (0::nat)"

definition "tps6 \<equiv> tps5[2 := nlltape' nss 0]"

lemma read_tps5: "read tps5 ! 3 = \<box> \<longleftrightarrow> \<not> ok"
proof -
  have "tps5 ! 3 = (\<lfloor>ok\<rfloor>\<^sub>B, 1)" "3 < length tps5"
    using tps1 by (simp_all add: tps5_def)
  from read_ncontents_eq_0[OF this] show ?thesis
    by simp
qed

lemma tmI [transforms_intros]:
  assumes "ttt = 2 * length zs + 10"
  shows "transforms tmI tps5 ttt tps6"
  unfolding tmI_def
proof (rule transforms_branchI)
  show "transforms (tm_erase_cr 2) tps5 (1 + 2 * length (bindecode zs) + 6) tps6"
    if "read tps5 ! 3 = \<box>"
  proof (rule transforms_tm_erase_crI[where zs="bindecode zs"])
    have "nss = []"
      using that read_tps5 unfolding red_nll_def by auto
    then show "tps6 = tps5[2 := (\<lfloor>[]\<rfloor>, 1)]"
      unfolding tps6_def using nllcontents_Nil by simp
  qed (use tps1 proper_bindecode in \<open>simp_all add: tps5_def\<close>)
  show "transforms [] tps5 0 tps5" if "\<not> read tps5 ! 3 = \<box>"
    using transforms_Nil .
  show "1 + 2 * length (bindecode zs) + 6 + 2 \<le> ttt" if "read tps5 ! 3 = \<box>"
    using assms by simp
  show "0 + 1 \<le> ttt" if "\<not> read tps5 ! 3 = \<box>"
    using assms by simp
  show "tps6 = tps6" if "read tps5 ! 3 = \<box>"
    by simp
  show "tps6 = tps5" if "\<not> read tps5 ! 3 = \<box>"
  proof -
    have "ok"
      using that read_tps5 by simp
    then have "numlistlist nss = bindecode zs"
      using red_nll_ok by simp
    then have "tps5 ! 2 = nlltape' nss 0"
      using tps1 by (simp add: tps5_def nlltape'_0 nllcontents_def)
    then show ?thesis
      unfolding tps6_def by (metis list_update_id)
  qed
qed

definition "T6 \<equiv> 224 + 10 * length zs + 39 * length (bindecode zs) + (2 * length zs + 10)"

lemma tm6 [transforms_intros]:
  assumes "ttt = T6"
  shows "transforms tm6 tps0 ttt tps6"
  unfolding tm6_def by (tform time: assms T6_def)

definition "tps7 \<equiv> tps6
  [2 := nlltape' nss m,
   8 := (\<lfloor>m\<rfloor>\<^sub>N, 1),
   9 := nltape CL,
   10 := nltape LIT]"

definition "T7 \<equiv> T6 + (m * (27 + 7 * nlllength nss + nlllength nss * (36 + 8 * nlllength nss)) + 1)"

lemma tm7 [transforms_intros]:
  assumes "ttt = T7"
  shows "transforms tm7 tps0 ttt tps7"
  unfolding tm7_def
  by (tform tps: tps6_def tps5_def tps1 nlcontents_Nil ncontents_0 tps7_def time: assms T7_def)

definition "tps9 \<equiv> tps7
  [9 := (\<lfloor>CL\<rfloor>\<^sub>N\<^sub>L, 1),
   10 := (\<lfloor>LIT\<rfloor>\<^sub>N\<^sub>L, 1)]"

definition "T9 \<equiv> T7 + (Suc (nllength CL) + 2) + (Suc (nllength LIT) + 2)"

lemma tm9 [transforms_intros]:
  assumes "ttt = T9"
  shows "transforms tm9 tps0 ttt tps9"
  unfolding tm9_def tm8_def
  apply (tform tps: tps7_def tps6_def tps5_def tps1 clean_tape_nlcontents
    time: assms T9_def tps7_def tps6_def tps5_def tps1)
  by (tps_eq rules: tps9_def tps7_def tps6_def tps5_def tps1)

definition "tps10 \<equiv> tps9[11 := (\<lfloor>N\<rfloor>\<^sub>N, 1)]"

definition "T10 \<equiv> T9 + (14 * nllength LIT ^ 2 + 5)"

lemma tm10 [transforms_intros]:
  assumes "ttt = T10"
  shows "transforms tm10 tps0 ttt tps10"
  unfolding tm10_def
  by (tform tps: tps9_def tps7_def tps6_def tps5_def tps1 ncontents_0 tps10_def time: assms T10_def)

definition "tps11 \<equiv> tps10
  [12 := (\<lfloor>N\<rfloor>\<^sub>N, 1),
   23 := nltape ES,
   24 := nltape W]"

definition "T11 \<equiv> T10 + 600 * (nllength CL + nllength LIT + 1) ^ 4"

lemma tm11 [transforms_intros]:
  assumes "ttt = T11"
  shows "transforms tm11 tps0 ttt tps11"
  unfolding tm11_def
proof (rule transforms_tm_sequentialI[OF tm10[OF refl] transforms_tm_edgesI[where CL=CL and LIT=LIT and k=30]])
  show "ttt = T10 + 600 * (nllength CL + nllength LIT + 1) ^ 4"
    using assms T11_def by simp
  show "tps11 = tps10[12 := (\<lfloor>length CL\<rfloor>\<^sub>N, 1), 23 := nltape ES,
      24 := nltape (replicate (Suc (length CL)) 0)]"
    unfolding tps11_def by simp
qed (simp_all add: tps10_def tps9_def tps7_def tps6_def tps5_def tps1 ncontents_0 nlcontents_Nil)

definition "out \<equiv> [[N, Suc N - m], W, ES]"

definition "tps12 \<equiv> tps11
    [26 := (\<lfloor>Suc N - m\<rfloor>\<^sub>N, 1),
     23 := (\<lfloor>ES\<rfloor>\<^sub>N\<^sub>L, 1),
     24 := (\<lfloor>W\<rfloor>\<^sub>N\<^sub>L, 1),
     28 := (\<lfloor>[N, Suc N - m]\<rfloor>\<^sub>N\<^sub>L, 1),
     29 := (\<lfloor>out\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1),
     29 := (\<lfloor>numlistlist out\<rfloor>, Suc (nlllength out)),
     1 := (\<lfloor>binencode (numlistlist out)\<rfloor>, Suc (2 * nlllength out))]"

definition "T12 \<equiv> T11 + (33 + 5 * N + 3 * m + (m * (18 + 2 * Suc N + 2 * m) + 1) +
    100 * Suc (nllength ES + nllength W + N + m) + (9 * nlllength out + 1))"

lemma tm12:
  assumes "ttt = T12"
  shows "transforms tm12 tps0 ttt tps12"
  unfolding tm12_def
  by (tform tps: tps11_def tps10_def tps9_def tps7_def tps6_def tps5_def tps1 ncontents_0 nlcontents_Nil
    nllcontents_Nil tps12_def out_def time: assms T12_def out_def)

lemma out_gadget: "out = gadget_nll nss"
  unfolding out_def gadget_nll_def using ees_gadget by simp

lemma len_tps11: "length tps11 = 30"
  by (simp add: tps11_def tps10_def tps9_def tps7_def tps6_def tps5_def tps1)

lemma tps12_1: "tps12 ! 1 = (\<lfloor>binencode (numlistlist (gadget_nll nss))\<rfloor>, Suc (2 * nlllength out))"
  unfolding tps12_def using len_tps11 out_gadget by simp

abbreviation "S \<equiv> Suc (length zs)"

lemma sizes:
  "nlllength nss \<le> length zs" "m \<le> length zs" "N \<le> length zs" "nllength LIT \<le> length zs"
  "nllength CL \<le> Suc (length zs) * length zs"
  "nlength N \<le> length zs" "nlength m \<le> length zs"
proof -
  let ?l = "nlllength nss"
  show l: "?l \<le> length zs"
    by (rule red_nll_size)
  show m: "m \<le> length zs"
    using length_le_nlllength l le_trans by blast
  have "nllength LIT \<le> ?l"
    using map_snd_occ nllength_concat_le by metis
  then show lit: "nllength LIT \<le> length zs"
    using l by simp
  show N: "N \<le> length zs"
    using length_le_nllength[of LIT] lit by simp
  show "nlength N \<le> length zs" "nlength m \<le> length zs"
    using N m nlength_le_n le_trans by blast+
  have "\<forall>x\<in>set CL. x \<le> m"
    using fst_occ_lt less_imp_le by blast
  then have "nllength CL \<le> Suc (nlength m) * length CL"
    by (rule nllength_le_len_mult_max)
  also have "\<dots> \<le> Suc (length zs) * length zs"
    using \<open>nlength m \<le> length zs\<close> N by (intro mult_le_mono) simp_all
  finally show "nllength CL \<le> Suc (length zs) * length zs" .
qed

lemma T12_bound: "T12 \<le> 2000 * S ^ 8"
proof -
  let ?n = "length zs"
  have S1: "1 \<le> S"
    by simp
  note pc = pow_chain[OF S1]
  note sz = sizes
  have sq: "S * S = S ^ 2" "S * S ^ 2 = S ^ 3" "S ^ 2 * S = S ^ 3"
    by (simp_all add: power2_eq_square power3_eq_cube)
  have hS: "nllength CL + nllength LIT + 1 \<le> S ^ 2"
  proof -
    have "nllength CL + nllength LIT + 1 \<le> Suc ?n * ?n + ?n + 1"
      using sz by simp
    also have "\<dots> = S ^ 2"
      by (simp add: power2_eq_square)
    finally show ?thesis .
  qed
  have h4: "(nllength CL + nllength LIT + 1) ^ 4 \<le> S ^ 8"
  proof -
    have "(nllength CL + nllength LIT + 1) ^ 4 \<le> (S ^ 2) ^ 4"
      using hS by (rule power_mono) simp
    then show ?thesis
      by (simp add: power_mult[symmetric])
  qed
  have ES: "nllength ES \<le> 2 * S ^ 3"
  proof -
    have "\<forall>x\<in>set ES. x \<le> N"
      using set_ees[of _ CL LIT] by simp
    then have "nllength ES \<le> Suc (nlength N) * length ES"
      by (rule nllength_le_len_mult_max)
    also have "\<dots> \<le> S * (?n * (2 * ?n + 2))"
    proof (rule mult_le_mono)
      show "Suc (nlength N) \<le> S"
        using sz by simp
      have "length ES \<le> N * (2 * N + 2)"
        using length_ees[of CL LIT] by simp
      also have "\<dots> \<le> ?n * (2 * ?n + 2)"
        using sz by (intro mult_le_mono add_mono) simp_all
      finally show "length ES \<le> ?n * (2 * ?n + 2)" .
    qed
    also have "\<dots> \<le> S * (S * (2 * S))"
      by (intro mult_le_mono) simp_all
    also have "\<dots> = 2 * S ^ 3"
      by (simp add: power3_eq_cube)
    finally show ?thesis .
  qed
  have Wl: "nllength W = S - (?n - N)"
  proof -
    have "nllength W = Suc N"
      by (simp add: nllength nlength_zero sum_list_replicate)
    then show ?thesis
      using sz by simp
  qed
  have W: "nllength W \<le> S"
    using Wl by simp
  have hd: "nllength [N, Suc N - m] \<le> 2 * S + 1"
  proof -
    have "nlength (Suc N - m) \<le> Suc N - m"
      by (rule nlength_le_n)
    then have "nlength (Suc N - m) \<le> S"
      using sz by simp
    then show ?thesis
      using sz by (simp add: nllength)
  qed
  have out: "nlllength out \<le> 10 * S ^ 3"
  proof -
    have "nlllength out = Suc (nllength [N, Suc N - m]) + Suc (nllength W) + Suc (nllength ES)"
      unfolding out_def by (simp add: nlllength)
    then have o: "nlllength out \<le> 2 * S ^ 3 + 3 * S + 4"
      using hd W ES by simp
    show ?thesis
      by (lin facts: o pc)
  qed
  have T6: "T6 \<le> 300 * S"
    unfolding T6_def by simp
  have occ: "m * (27 + 7 * nlllength nss + nlllength nss * (36 + 8 * nlllength nss)) \<le> 79 * S ^ 3"
  proof -
    have "m * (27 + 7 * nlllength nss + nlllength nss * (36 + 8 * nlllength nss)) \<le>
        S * (27 + 7 * S + S * (36 + 8 * S))"
      using sz by (intro mult_le_mono add_mono) simp_all
    also have "\<dots> = 27 * S + 43 * S ^ 2 + 8 * S ^ 3"
      by (simp add: power2_eq_square power3_eq_cube algebra_simps)
    finally have o: "m * (27 + 7 * nlllength nss + nlllength nss * (36 + 8 * nlllength nss)) \<le>
      27 * S + 43 * S ^ 2 + 8 * S ^ 3" .
    show ?thesis
      by (lin facts: o pc)
  qed
  have LIT2: "nllength LIT ^ 2 \<le> S ^ 2"
    using sz by (intro power_mono) simp_all
  have CL2: "nllength CL \<le> S ^ 2"
    using hS by simp
  have hm: "m * (18 + 2 * Suc N + 2 * m) \<le> 24 * S ^ 2"
  proof -
    have "m * (18 + 2 * Suc N + 2 * m) \<le> S * (24 * S)"
      using sz by (intro mult_le_mono) simp_all
    also have "S * (24 * S) = 24 * S ^ 2"
      by (simp add: power2_eq_square algebra_simps)
    finally show ?thesis .
  qed
  have "T12 \<le> 300 * S + (79 * S ^ 3 + 1) + (S ^ 2 + S + 6) + (14 * S ^ 2 + 5) + 600 * S ^ 8 +
      (33 + 8 * S + (24 * S ^ 2 + 1) + 100 * (1 + 2 * S ^ 3 + S + S + S) + (90 * S ^ 3 + 1))"
  proof -
    have "T12 = T6 + (m * (27 + 7 * nlllength nss + nlllength nss * (36 + 8 * nlllength nss)) + 1) +
        (Suc (nllength CL) + 2) + (Suc (nllength LIT) + 2) + (14 * nllength LIT ^ 2 + 5) +
        600 * (nllength CL + nllength LIT + 1) ^ 4 +
        (33 + 5 * N + 3 * m + (m * (18 + 2 * Suc N + 2 * m) + 1) +
          100 * Suc (nllength ES + nllength W + N + m) + (9 * nlllength out + 1))"
      unfolding T12_def T11_def T10_def T9_def T7_def by simp
    then show ?thesis
      by (lin facts: T6 occ CL2 sz LIT2 h4 hm ES W out)
  qed
  then have o: "T12 \<le> 300 * S + (79 * S ^ 3 + 1) + (S ^ 2 + S + 6) + (14 * S ^ 2 + 5) + 600 * S ^ 8 +
      (33 + 8 * S + (24 * S ^ 2 + 1) + 100 * (1 + 2 * S ^ 3 + S + S + S) + (90 * S ^ 3 + 1))" .
  show ?thesis
    by (lin facts: o pc)
qed

end

end


lemma transforms_tm_red:
  assumes "bit_symbols zs" and "tps = snd (start_config 30 zs)"
  shows "\<exists>tps'. tps' ::: 1 = \<lfloor>binencode (numlistlist (gadget_nll (red_nll zs)))\<rfloor> \<and>
    transforms tm_red tps (2000 * Suc (length zs) ^ 8) tps'"
proof -
  interpret loc: turing_machine_red .
  have "transforms tm_red tps (2000 * Suc (length zs) ^ 8) (loc.tps12 tps zs)"
    using transforms_monotone[OF loc.tm12[OF assms refl] loc.T12_bound[OF assms]] loc.tm12_eq_tm_red
    by simp
  moreover have "loc.tps12 tps zs ::: 1 = \<lfloor>binencode (numlistlist (gadget_nll (red_nll zs)))\<rfloor>"
    using loc.tps12_1[OF assms] by simp
  ultimately show ?thesis
    by blast
qed

definition T_red :: "nat \<Rightarrow> nat" where
  "T_red n \<equiv> 2000 * Suc n ^ 8"

lemma big_oh_poly_T_red: "big_oh_poly T_red"
proof (rule big_oh_polyI[of 0 _ "2000 * 2 ^ 8" 8])
  fix n :: nat
  assume "0 < n"
  then have "Suc n \<le> 2 * n"
    by simp
  then have "Suc n ^ 8 \<le> (2 * n) ^ 8"
    by (rule power_mono) simp
  then show "T_red n \<le> 2000 * 2 ^ 8 * n ^ 8"
    unfolding T_red_def by (simp add: power_mult_distrib)
qed

theorem computes_in_time_tm_red: "computes_in_time 30 tm_red sat_red T_red"
proof
  fix x :: string
  let ?zs = "string_to_symbols x"
  let ?ys = "binencode (numlistlist (gadget_nll (red_nll ?zs)))"
  have bs: "bit_symbols ?zs"
    by simp
  obtain tps where tps: "tps ::: 1 = \<lfloor>?ys\<rfloor>"
      "transforms tm_red (snd (start_config 30 ?zs)) (2000 * Suc (length ?zs) ^ 8) tps"
    using transforms_tm_red[OF bs refl] by blast
  have "bit_symbols ?ys"
    using bit_symbols_binencode binencodable_numlistlist by blast
  then have "\<lfloor>?ys\<rfloor> = string_to_contents (symbols_to_string ?ys)"
    by (rule bit_symbols_to_contents)
  also have "symbols_to_string ?ys = sat_red x"
    by (rule sat_red_red_nll[symmetric])
  finally have "\<lfloor>?ys\<rfloor> = string_to_contents (sat_red x)" .
  then show "\<exists>tps. tps ::: 1 = string_to_contents (sat_red x) \<and>
      transforms tm_red (snd (start_config 30 (string_to_symbols x))) (T_red (length x)) tps"
    using tps T_red_def by auto
qed

text \<open>
SAT reduces to the decision version of MWCCVC in polynomial time, by a Turing machine with
30 tapes and 6 symbols running in time \<open>2000 (n + 1)\<^sup>8\<close>.
\<close>

theorem SAT_reducible_MWCCVC: "SAT \<le>\<^sub>p MWCCVC"
  unfolding reducible_def using tm_red_tm big_oh_poly_T_red computes_in_time_tm_red sat_red_correct
  by blast

end
