theory TM_VWeights
  imports TM_VGrow
begin

section \<open>The verifier, phase 2: the weight bound\<close>

text \<open>
Phase 2 sums the weights \<open>max 1 (w v)\<close> of the vertices in \<open>S\<close> on tape 57, adds the slack
\<open>d\<close> of the certificate and compares with the bound \<open>B\<close>; the flag on tape 27, which is set when
the phase starts, becomes the result of the comparison. Tapes 55 and 56 are scratch.
\<close>

definition "tm_wA \<equiv> tm_nextract \<bar> 33 55 ;; tm_nth 15 55 56 \<bar>"
definition "tm_wI \<equiv> IF \<lambda>rs. rs ! 56 = \<box> THEN tm_setn 56 1 ELSE [] ENDIF"
definition "tm_wC \<equiv> tm_add 56 57 ;; tm_setn 55 0 ;; tm_setn 56 0"

definition tm_wbody :: machine where
  "tm_wbody \<equiv> tm_wA ;; tm_wI ;; tm_wC"

definition tm_weights :: machine where
  "tm_weights \<equiv>
    WHILE [] ; \<lambda>rs. rs ! 33 \<noteq> \<box> DO tm_wbody DONE ;;
    tm_cr 33 ;;
    tm_add 22 57 ;;
    tm_equalsn 57 18 58 ;;
    tm_and 27 58"

lemma tm_weights_tm:
  assumes "92 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_weights"
  unfolding tm_weights_def tm_wbody_def tm_wA_def tm_wI_def tm_wC_def
  using assms tm_nextract_tm tm_nth_tm tm_setn_tm tm_add_tm tm_cr_tm tm_equalsn_tm tm_and_tm Nil_tm
    turing_machine_loop_turing_machine turing_machine_branch_turing_machine
  by simp

definition wsum :: "nat list \<Rightarrow> nat list \<Rightarrow> nat" where
  "wsum wts S \<equiv> sum_list (map (\<lambda>v. max 1 (wts ! v)) S)"

lemma wsum_take_Suc:
  "i < length S \<Longrightarrow> wsum wts (take (Suc i) S) = max 1 (wts ! (S ! i)) + wsum wts (take i S)"
  unfolding wsum_def by (simp add: take_Suc_conv_app_nth)

locale turing_machine_weights
begin

definition "tmL \<equiv> WHILE [] ; \<lambda>rs. rs ! 33 \<noteq> \<box> DO tm_wbody DONE"
definition "tm2 \<equiv> tmL ;; tm_cr 33"
definition "tm3 \<equiv> tm2 ;; tm_add 22 57"
definition "tm4 \<equiv> tm3 ;; tm_equalsn 57 18 58"
definition "tm5 \<equiv> tm4 ;; tm_and 27 58"

lemma tm5_eq_tm_weights: "tm5 = tm_weights"
  unfolding tm5_def tm4_def tm3_def tm2_def tmL_def tm_weights_def by simp

context
  fixes tps0 :: "tape list" and wts S :: "nat list" and d B :: nat
  assumes k: "length tps0 = 93"
  assumes S: "set S \<subseteq> {..<length wts}"
  assumes tps0:
    "tps0 ! 15 = (\<lfloor>wts\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 18 = (\<lfloor>B\<rfloor>\<^sub>N, 1)"
    "tps0 ! 22 = (\<lfloor>d\<rfloor>\<^sub>N, 1)"
    "tps0 ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps0 ! 33 = (\<lfloor>S\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 55 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 56 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 57 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 58 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

definition tpsL :: "nat \<Rightarrow> tape list" where
  "tpsL i \<equiv> tps0[33 := nltape' S i, 57 := (\<lfloor>wsum wts (take i S)\<rfloor>\<^sub>N, 1)]"

definition "Wm \<equiv> Suc (Max (set (0 # wts)))"
definition "HW \<equiv> nllength wts + nllength S + nlength d + 2"

lemma HW_ge: "1 \<le> HW" "HW \<le> HW ^ 2" "nllength wts \<le> HW" "nllength S \<le> HW" "nlength d \<le> HW"
  "length S \<le> HW"
proof -
  show 1: "1 \<le> HW"
    unfolding HW_def by simp
  show "HW \<le> HW ^ 2"
    using 1 by (simp add: power2_eq_square)
  show "nllength wts \<le> HW" "nllength S \<le> HW" "nlength d \<le> HW"
    unfolding HW_def by simp_all
  show "length S \<le> HW"
    using length_le_nllength[of S] unfolding HW_def by simp
qed

lemma w_le_Wm: "v < length wts \<Longrightarrow> max 1 (wts ! v) \<le> Wm"
  unfolding Wm_def by (simp add: le_SucI)

lemma nlength_Wm: "nlength Wm \<le> Suc (nllength wts)"
proof -
  have "Max (set (0 # wts)) \<in> set (0 # wts)"
    by (rule Max_in) simp_all
  then have "nlength (Max (set (0 # wts))) \<le> nllength wts"
    using member_le_nllength nlength_zero by auto
  then show ?thesis
    unfolding Wm_def using nlength_Suc[of "Max (set (0 # wts))"] by simp
qed

lemma wsum_le_gen: "set xs \<subseteq> {..<length wts} \<Longrightarrow> wsum wts xs \<le> length xs * Wm"
proof (induction xs)
  case (Cons x xs)
  then have "max 1 (wts ! x) \<le> Wm" "wsum wts xs \<le> length xs * Wm"
    using w_le_Wm by auto
  then have "max 1 (wts ! x) + wsum wts xs \<le> Wm + length xs * Wm"
    by (rule add_mono)
  then show ?case
    unfolding wsum_def by simp
qed (simp add: wsum_def)

lemma nlength_wsum: "nlength (wsum wts (take i S)) \<le> 3 * HW"
proof -
  have "set (take i S) \<subseteq> {..<length wts}"
    using S set_take_subset by fastforce
  then have "wsum wts (take i S) \<le> length (take i S) * Wm"
    by (rule wsum_le_gen)
  also have "\<dots> \<le> length S * Wm"
    by (rule mult_le_mono1) simp
  finally have "wsum wts (take i S) \<le> length S * Wm" .
  then have "nlength (wsum wts (take i S)) \<le> nlength (length S * Wm)"
    by (rule nlength_mono)
  also have "\<dots> \<le> nlength (length S) + nlength Wm"
    by (rule nlength_prod)
  also have "\<dots> \<le> HW + Suc (nllength wts)"
    using nlength_le_n[of "length S"] HW_ge nlength_Wm by (intro add_mono) linarith+
  finally show ?thesis
    using HW_ge by simp
qed

lemma S_lt: "i < length S \<Longrightarrow> S ! i < length wts"
  using S nth_mem by blast

lemma wv_le: "i < length S \<Longrightarrow> nlength (max 1 (wts ! (S ! i))) \<le> HW"
proof -
  assume i: "i < length S"
  have "nlength (wts ! (S ! i)) \<le> nllength wts"
    using member_le_nllength S_lt[OF i] by simp
  moreover have "nlength (max 1 (wts ! (S ! i))) \<le> Suc (nlength (wts ! (S ! i)))"
    by (cases "wts ! (S ! i) = 0") (simp_all add: max_def nlength_Suc0)
  ultimately show ?thesis
    unfolding HW_def by simp
qed

lemma s_le: "i < length S \<Longrightarrow> nlength (S ! i) \<le> HW"
  using member_le_nllength[of "S ! i" S] HW_ge by simp

definition "tpsA i \<equiv> (tpsL i)
  [33 := nltape' S (Suc i),
   55 := (\<lfloor>S ! i\<rfloor>\<^sub>N, 1),
   56 := (\<lfloor>wts ! (S ! i)\<rfloor>\<^sub>N, 1)]"

definition "tpsB i \<equiv> (tpsA i)[56 := (\<lfloor>max 1 (wts ! (S ! i))\<rfloor>\<^sub>N, 1)]"

lemma tmA [transforms_intros]:
  assumes "i < length S" "ttt = 12 + 2 * nlength 0 + 2 * nlength (S ! i) + (21 * nllength wts ^ 2 + 26)"
  shows "transforms tm_wA (tpsL i) ttt (tpsA i)"
  unfolding tm_wA_def
  apply (tform tps: tpsL_def tps0 k assms S_lt[OF assms(1)] time: assms)
  by (tps_eq rules: tpsA_def tpsL_def k assms(1))

lemma tmIF [transforms_intros]:
  assumes "i < length S" "ttt = 14"
  shows "transforms tm_wI (tpsA i) ttt (tpsB i)"
  unfolding tm_wI_def
proof (rule transforms_branchI)
  have r: "read (tpsA i) ! 56 = \<box> \<longleftrightarrow> wts ! (S ! i) = 0"
  proof -
    have "tpsA i ! 56 = (\<lfloor>wts ! (S ! i)\<rfloor>\<^sub>N, 1)" "56 < length (tpsA i)"
      using k by (simp_all add: tpsA_def tpsL_def)
    from read_ncontents_eq_0[OF this] show ?thesis .
  qed
  show "transforms (tm_setn 56 1) (tpsA i) 12 (tpsB i)" if "read (tpsA i) ! 56 = \<box>"
    apply (rule transforms_monotone)
     apply (tform tps: tpsA_def tpsL_def k)
     apply (tps_eq rules: tpsB_def tpsA_def tpsL_def k)?
    using that r by (simp_all add: tpsB_def tpsA_def tpsL_def k nlength_Suc0)
  show "transforms [] (tpsA i) 0 (tpsB i)" if "\<not> read (tpsA i) ! 56 = \<box>"
  proof -
    have w: "max (Suc 0) (wts ! (S ! i)) = wts ! (S ! i)"
      using that r by simp
    have "tpsB i = tpsA i"
      by (tps_eq rules: tpsB_def tpsA_def tpsL_def k w)
    then show ?thesis
      using transforms_Nil by simp
  qed
qed (use assms in simp_all)

lemma tmC [transforms_intros]:
  assumes "i < length S"
    and "ttt = 3 * max (nlength (max 1 (wts ! (S ! i)))) (nlength (wsum wts (take i S))) + 10 +
      (10 + 2 * nlength (S ! i) + 2 * nlength 0) + (10 + 2 * nlength (max 1 (wts ! (S ! i))) + 2 * nlength 0)"
  shows "transforms tm_wC (tpsB i) ttt (tpsL (Suc i))"
  unfolding tm_wC_def
  apply (tform tps: assms(1) tpsB_def tpsA_def tpsL_def k time: assms(2))
  by (tps_eq rules: tpsL_def tpsB_def tpsA_def k tps0 wsum_take_Suc assms(1))

lemma tm_wbody [transforms_intros]:
  assumes "i < length S" "ttt = 150 * HW ^ 2"
  shows "transforms tm_wbody (tpsL i) ttt (tpsL (Suc i))"
proof -
  have sq: "nllength wts ^ 2 \<le> HW ^ 2"
    using HW_ge by (simp add: power_mono)
  have m: "max (nlength (max 1 (wts ! (S ! i)))) (nlength (wsum wts (take i S))) \<le> 3 * HW"
    using wv_le[OF assms(1)] nlength_wsum[of i] by simp
  have "transforms tm_wbody (tpsL i)
      (12 + 2 * nlength 0 + 2 * nlength (S ! i) + (21 * nllength wts ^ 2 + 26) + 14 +
       (3 * max (nlength (max 1 (wts ! (S ! i)))) (nlength (wsum wts (take i S))) + 10 +
       (10 + 2 * nlength (S ! i) + 2 * nlength 0) +
       (10 + 2 * nlength (max 1 (wts ! (S ! i))) + 2 * nlength 0))) (tpsL (Suc i))"
    unfolding tm_wbody_def by (tform tps: assms(1))
  then show ?thesis
    by (rule transforms_monotone)
      (lin facts: s_le[OF assms(1)] wv_le[OF assms(1)] m sq HW_ge assms(2) nlength_zero)
qed

lemma read_tpsL: "read (tpsL i) ! 33 \<noteq> \<box> \<longleftrightarrow> i < length S"
proof -
  have "read (tpsL i) ! 33 = |.| (nltape' S i)"
    using tapes_at_read'[of 33 "tpsL i"] k by (simp add: tpsL_def)
  then show ?thesis
    using nltape'_tape_read[of S i] by auto
qed

lemma tmL [transforms_intros]:
  assumes "ttt = length S * (150 * HW ^ 2 + 2) + 1"
  shows "transforms tmL (tpsL 0) ttt (tpsL (length S))"
  unfolding tmL_def by (tform tps: read_tpsL time: assms)

lemma tpsL0: "tpsL 0 = tps0"
  by (tps_eq rules: tpsL_def tps0 k wsum_def)

definition "tpsW \<equiv> tps0
  [57 := (\<lfloor>d + wsum wts S\<rfloor>\<^sub>N, 1),
   58 := (\<lfloor>d + wsum wts S = B\<rfloor>\<^sub>B, 1),
   27 := (\<lfloor>d + wsum wts S = B\<rfloor>\<^sub>B, 1)]"

lemma tm5:
  assumes "ttt = 400 * HW ^ 3 + 3 * nlength B"
  shows "transforms tm5 tps0 ttt tpsW"
proof -
  have p: "HW ^ 2 \<le> HW ^ 3" "1 \<le> HW ^ 3" "HW \<le> HW ^ 3"
    using HW_ge power_increasing[of 2 3 HW] power_increasing[of 1 3 HW] by simp_all
  have q: "length S * (150 * HW ^ 2 + 2) \<le> HW * (152 * HW ^ 2)"
    using HW_ge by (intro mult_le_mono) simp_all
  also have "\<dots> = 152 * HW ^ 3"
    by (simp add: power2_eq_square power3_eq_cube)
  finally have q: "length S * (150 * HW ^ 2 + 2) \<le> 152 * HW ^ 3" .
  have w: "nlength (wsum wts S) \<le> 3 * HW" "nlength (d + wsum wts S) \<le> Suc (4 * HW)"
  proof -
    show w: "nlength (wsum wts S) \<le> 3 * HW"
      using nlength_wsum[of "length S"] by simp
    have "nlength (d + wsum wts S) \<le> Suc (max (nlength d) (nlength (wsum wts S)))"
      by (rule nlength_sum)
    then show "nlength (d + wsum wts S) \<le> Suc (4 * HW)"
      using w HW_ge by simp
  qed
  have m: "nlength (min (d + wsum wts S) B) \<le> nlength B"
    by (rule nlength_mono) simp
  have "transforms tm5 (tpsL 0)
      (length S * (150 * HW ^ 2 + 2) + 1 + (tpsL (length S) :#: 33 + 2) +
       (3 * max (nlength d) (nlength (wsum wts (take (length S) S))) + 10) +
       (3 * nlength (min (d + wsum wts (take (length S) S)) B) + 7) + 3) tpsW"
    unfolding tm5_def tm4_def tm3_def tm2_def
    apply (tform tps: tpsL_def tps0 k clean_tape_nlcontents time: tpsL_def k)
    by (tps_eq rules: tpsW_def tpsL_def tps0 k)
  then show ?thesis
    unfolding tpsL0
    apply (rule transforms_monotone)
    using q p w m HW_ge assms k by (simp add: tpsL_def max_def)
qed

end

end

lemma transforms_tm_weightsI [transforms_intros]:
  fixes tps tps' :: "tape list" and wts S :: "nat list" and d B ttt :: nat
  assumes "length tps = 93" "set S \<subseteq> {..<length wts}"
  assumes
    "tps ! 15 = (\<lfloor>wts\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 18 = (\<lfloor>B\<rfloor>\<^sub>N, 1)"
    "tps ! 22 = (\<lfloor>d\<rfloor>\<^sub>N, 1)"
    "tps ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps ! 33 = (\<lfloor>S\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 55 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 56 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 57 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 58 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 400 * (nllength wts + nllength S + nlength d + 2) ^ 3 + 3 * nlength B"
  assumes "tps' = tps
    [57 := (\<lfloor>d + wsum wts S\<rfloor>\<^sub>N, 1),
     58 := (\<lfloor>d + wsum wts S = B\<rfloor>\<^sub>B, 1),
     27 := (\<lfloor>d + wsum wts S = B\<rfloor>\<^sub>B, 1)]"
  shows "transforms tm_weights tps ttt tps'"
proof -
  interpret loc: turing_machine_weights .
  show ?thesis
    using loc.tm5[OF assms(1-11)] loc.tpsW_def[OF assms(1-11)] loc.HW_def[OF assms(1-11)]
      loc.tm5_eq_tm_weights assms(12,13)
    by simp
qed

end
