theory TM_VOwners
  imports TM_VLoads
begin

section \<open>The verifier, phase 4: the owner lists\<close>

text \<open>
Phase 4 reads the edge pairs \<open>(a, b)\<close> of the instance from tape 16 (tapes 66, 67) and, when
\<open>a \<noteq> b\<close>, \<open>a < n\<close> and \<open>b < n\<close>, checks that \<open>a \<in> S\<close> and \<open>b \<in> N\<^sub>a\<close>, or \<open>b \<in> S\<close> and
\<open>a \<in> N\<^sub>b\<close>, where \<open>N\<^sub>v\<close> is the list \<open>nssc ! (v + 1)\<close> of the certificate, fetched by
@{const tm_nthl} from tape 11. A failed check clears the flag on tape 27.
\<close>

definition "tm_erase_nl j \<equiv> tm_erase_cr j"

lemma tm_erase_nl_tm: "0 < j \<Longrightarrow> j < k \<Longrightarrow> G \<ge> 4 \<Longrightarrow> turing_machine k G (tm_erase_nl j)"
  unfolding tm_erase_nl_def using tm_erase_cr_tm by simp

lemma transforms_tm_erase_nlI [transforms_intros]:
  assumes "j < length tps" "tps ! j = (\<lfloor>ns\<rfloor>\<^sub>N\<^sub>L, 1)" "ttt = 2 * nllength ns + 7"
    "tps' = tps[j := (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)]"
  shows "transforms (tm_erase_nl j) tps ttt tps'"
  unfolding tm_erase_nl_def
  by (rule transforms_tm_erase_crI[where zs="numlist ns"])
    (use assms proper_symbols_numlist in \<open>simp_all add: nlcontents_def nllength_def numlist_Nil\<close>)

definition "tm_oread \<equiv>
  tm_nextract \<bar> 16 66 ;; tm_nextract \<bar> 16 67 ;; tm_equalsn 66 67 68 ;; tm_lt 66 19 69 ;; tm_lt 67 19 72"

definition "tm_ocompA \<equiv>
  tm_contains 33 66 75 ;; tm_copyn 66 78 ;; tm_incr 78 ;; tm_nthl 11 78 79 ;; tm_contains 79 67 81"
definition "tm_ocompB \<equiv>
  tm_contains 33 67 84 ;; tm_copyn 67 87 ;; tm_incr 87 ;; tm_nthl 11 87 88 ;; tm_contains 88 66 90"
definition "tm_ocomp \<equiv> tm_ocompA ;; tm_ocompB"

definition "tm_odec \<equiv>
  IF \<lambda>rs. (rs ! 75 \<noteq> \<box> \<and> rs ! 81 \<noteq> \<box>) \<or> (rs ! 84 \<noteq> \<box> \<and> rs ! 90 \<noteq> \<box>) THEN [] ELSE tm_setn 27 0 ENDIF"

definition "tm_oclean \<equiv>
  tm_setn 75 0 ;; tm_setn 78 0 ;; tm_erase_nl 79 ;; tm_setn 81 0 ;; tm_setn 84 0 ;; tm_setn 87 0 ;;
  tm_erase_nl 88 ;; tm_setn 90 0"

definition "tm_ochk \<equiv> tm_ocomp ;; tm_odec ;; tm_oclean"

definition "tm_oif \<equiv> IF \<lambda>rs. rs ! 68 = \<box> \<and> rs ! 69 \<noteq> \<box> \<and> rs ! 72 \<noteq> \<box> THEN tm_ochk ELSE [] ENDIF"

definition "tm_oreset \<equiv> tm_setn 66 0 ;; tm_setn 67 0 ;; tm_setn 68 0 ;; tm_setn 69 0 ;; tm_setn 72 0"

definition "tm_obody \<equiv> tm_oread ;; tm_oif ;; tm_oreset ;; tm_decr 65"

definition "tm_opre \<equiv> tm_cr 11 ;; tm_copyn 20 65 ;; tm_div2 65"

definition tm_owners :: machine where
  "tm_owners \<equiv> tm_opre ;; WHILE [] ; \<lambda>rs. rs ! 65 \<noteq> \<box> DO tm_obody DONE"

lemma tm_owners_tm:
  assumes "92 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_owners"
  unfolding tm_owners_def tm_opre_def tm_obody_def tm_oread_def tm_oif_def tm_ochk_def tm_ocomp_def
    tm_ocompA_def tm_ocompB_def
    tm_odec_def tm_oclean_def tm_oreset_def
  using assms tm_nextract_tm tm_equalsn_tm tm_lt_tm tm_contains_tm tm_copyn_tm tm_incr_tm tm_nthl_tm
    tm_setn_tm tm_erase_nl_tm tm_decr_tm tm_cr_tm tm_div2_tm Nil_tm turing_machine_loop_turing_machine
    turing_machine_branch_turing_machine
  by simp

definition ocond :: "nat \<Rightarrow> nat list \<Rightarrow> nat list \<Rightarrow> nat list list \<Rightarrow> nat \<Rightarrow> bool" where
  "ocond n es S nssc t \<equiv>
    es ! (2 * t) \<noteq> es ! Suc (2 * t) \<and> es ! (2 * t) < n \<and> es ! Suc (2 * t) < n \<longrightarrow>
      (es ! (2 * t) \<in> set S \<and> es ! Suc (2 * t) \<in> set (nssc ! Suc (es ! (2 * t)))) \<or>
      (es ! Suc (2 * t) \<in> set S \<and> es ! (2 * t) \<in> set (nssc ! Suc (es ! Suc (2 * t))))"

lemma own_ok_iff: "own_ok n es S nssc \<longleftrightarrow> (\<forall>t<length es div 2. ocond n es S nssc t)"
proof -
  have eq: "t < length (pairs es) \<Longrightarrow> pairs es ! t = (es ! (2 * t), es ! Suc (2 * t))" for t
    by (rule nth_pairs)
  show ?thesis
    unfolding own_ok_def all_set_conv_all_nth length_pairs[symmetric]
    by (simp add: eq ocond_def)
qed

locale turing_machine_owners
begin

context
  fixes tps0 :: "tape list" and nssc :: "nat list list" and es S :: "nat list" and n p :: nat
  assumes k: "length tps0 = 93"
  assumes nlen: "n < length nssc"
  assumes S: "set S \<subseteq> {..<n}"
  assumes p: "p \<le> length nssc"
  assumes tps0:
    "tps0 ! 11 = nlltape' nssc p"
    "tps0 ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps0 ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps0 ! 33 = (\<lfloor>S\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 79 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 88 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "\<And>j. 66 \<le> j \<Longrightarrow> j \<le> 92 \<Longrightarrow> j \<noteq> 79 \<Longrightarrow> j \<noteq> 88 \<Longrightarrow> tps0 ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes tps0':
    "tps0 ! 16 = (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 65 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 20 = (\<lfloor>length es\<rfloor>\<^sub>N, 1)"
begin

lemma tps0z:
  "tps0 ! 66 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 67 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 68 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 69 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 70 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 71 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 72 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 73 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 74 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 75 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 76 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 77 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 78 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 80 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 81 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 82 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 83 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 84 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 85 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 86 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 87 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 89 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 90 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 91 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 92 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  using tps0(7) by simp_all

abbreviation "P \<equiv> length es div 2"

definition "oc t \<equiv> \<forall>i<t. ocond n es S nssc i"

definition tpsL :: "nat \<Rightarrow> tape list" where
  "tpsL t \<equiv> tps0
    [11 := (\<lfloor>nssc\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1),
     16 := nltape' es (2 * t),
     27 := (\<lfloor>oc t\<rfloor>\<^sub>B, 1),
     65 := (\<lfloor>P - t\<rfloor>\<^sub>N, 1)]"

definition "HO \<equiv> nlllength nssc + nllength es + nllength S + n + 2"

lemma HO_ge: "1 \<le> HO" "HO \<le> HO ^ 2" "nlllength nssc \<le> HO" "nllength es \<le> HO" "nllength S \<le> HO"
  "n \<le> HO" "nlength n \<le> HO" "length es \<le> HO"
proof -
  show 1: "1 \<le> HO"
    unfolding HO_def by simp
  show "HO \<le> HO ^ 2"
    using 1 by (simp add: power2_eq_square)
  show "nlllength nssc \<le> HO" and e: "nllength es \<le> HO" and "nllength S \<le> HO" and nn: "n \<le> HO"
    unfolding HO_def by simp_all
  show "nlength n \<le> HO"
    using nlength_le_n[of n] nn by simp
  show "length es \<le> HO"
    using length_le_nllength[of es] e by simp
qed

context
  fixes t :: nat
  assumes t: "t < P"
begin

abbreviation "a \<equiv> es ! (2 * t)"
abbreviation "b \<equiv> es ! Suc (2 * t)"

lemma t2: "2 * t < length es" "Suc (2 * t) < length es"
  using t by linarith+

lemma ab_le: "nlength a \<le> HO" "nlength b \<le> HO"
  using t2 member_le_nllength[of a es] member_le_nllength[of b es] HO_ge(4) by simp_all

definition "tpsR \<equiv> (tpsL t)
  [16 := nltape' es (Suc (Suc (2 * t))),
   66 := (\<lfloor>a\<rfloor>\<^sub>N, 1),
   67 := (\<lfloor>b\<rfloor>\<^sub>N, 1),
   68 := (\<lfloor>a = b\<rfloor>\<^sub>B, 1),
   69 := (\<lfloor>a < n\<rfloor>\<^sub>B, 1),
   72 := (\<lfloor>b < n\<rfloor>\<^sub>B, 1)]"

lemma lt_time: "100 * Suc (min x n) * Suc (nlength x + nlength n) \<le> 600 * HO ^ 2" if "nlength x \<le> HO" for x
proof -
  have "100 * Suc (min x n) * Suc (nlength x + nlength n) \<le> 100 * (2 * HO) * (3 * HO)"
    using that HO_ge by (intro mult_le_mono) simp_all
  then show ?thesis
    by (simp add: power2_eq_square algebra_simps)
qed

lemma tm_oread [transforms_intros]:
  assumes "ttt = 1300 * HO ^ 2"
  shows "transforms tm_oread (tpsL t) ttt tpsR"
proof -
  show ?thesis
    unfolding tm_oread_def
    apply (rule transforms_monotone)
     apply (tform tps: tpsL_def tps0(1-6) tps0z k t2)
     apply (tps_eq rules: tpsR_def tpsL_def tps0(1-6) tps0z k)?
    by (lin facts: assms lt_time[OF ab_le(1)] lt_time[OF ab_le(2)] ab_le HO_ge
      nlength_mono[OF min.cobounded1[of a b]] nlength_zero)
qed

lemma oc_Suc: "oc (Suc t) \<longleftrightarrow> oc t \<and> ocond n es S nssc t"
  unfolding oc_def using less_Suc_eq by auto

context
  assumes guard: "a \<noteq> b" "a < n" "b < n"
begin

abbreviation "NA \<equiv> nssc ! Suc a"
abbreviation "NB \<equiv> nssc ! Suc b"

definition "tpsC \<equiv> tpsR
  [75 := (\<lfloor>a \<in> set S\<rfloor>\<^sub>B, 1),
   78 := (\<lfloor>Suc a\<rfloor>\<^sub>N, 1),
   79 := (\<lfloor>NA\<rfloor>\<^sub>N\<^sub>L, 1),
   81 := (\<lfloor>b \<in> set NA\<rfloor>\<^sub>B, 1),
   84 := (\<lfloor>b \<in> set S\<rfloor>\<^sub>B, 1),
   87 := (\<lfloor>Suc b\<rfloor>\<^sub>N, 1),
   88 := (\<lfloor>NB\<rfloor>\<^sub>N\<^sub>L, 1),
   90 := (\<lfloor>a \<in> set NB\<rfloor>\<^sub>B, 1)]"

lemma idx: "Suc a < length nssc" "Suc b < length nssc"
  using guard nlen by simp_all

lemma NAB_le: "nllength NA \<le> HO" "nllength NB \<le> HO"
  using idx member_le_nlllength_1[of NA nssc] member_le_nlllength_1[of NB nssc] HO_ge(3) by simp_all

definition "tpsCA \<equiv> tpsR
  [75 := (\<lfloor>a \<in> set S\<rfloor>\<^sub>B, 1),
   78 := (\<lfloor>Suc a\<rfloor>\<^sub>N, 1),
   79 := (\<lfloor>NA\<rfloor>\<^sub>N\<^sub>L, 1),
   81 := (\<lfloor>b \<in> set NA\<rfloor>\<^sub>B, 1)]"

lemma sqs: "nllength S ^ 2 \<le> HO ^ 2" "nllength NA ^ 2 \<le> HO ^ 2" "nllength NB ^ 2 \<le> HO ^ 2"
  "(Suc (nlllength nssc)) ^ 2 \<le> 4 * HO ^ 2"
proof -
  show "nllength S ^ 2 \<le> HO ^ 2" "nllength NA ^ 2 \<le> HO ^ 2" "nllength NB ^ 2 \<le> HO ^ 2"
    using HO_ge NAB_le by (simp_all add: power_mono)
  have "(Suc (nlllength nssc)) ^ 2 \<le> (2 * HO) ^ 2"
    using HO_ge by (intro power_mono) simp_all
  then show "(Suc (nlllength nssc)) ^ 2 \<le> 4 * HO ^ 2"
    by (simp add: power_mult_distrib)
qed

lemma tm_ocompA [transforms_intros]:
  assumes "ttt = 600 * HO ^ 2"
  shows "transforms tm_ocompA tpsR ttt tpsCA"
  unfolding tm_ocompA_def
  apply (rule transforms_monotone)
   apply (tform tps: tpsR_def tpsL_def tps0(1-6) tps0z k idx(1))
   apply (tps_eq rules: tpsCA_def tpsR_def tpsL_def tps0(1-6) tps0z k)?
  by (lin facts: assms sqs ab_le HO_ge nlength_zero)

lemma tm_ocompB [transforms_intros]:
  assumes "ttt = 600 * HO ^ 2"
  shows "transforms tm_ocompB tpsCA ttt tpsC"
  unfolding tm_ocompB_def
  apply (rule transforms_monotone)
   apply (tform tps: tpsCA_def tpsR_def tpsL_def tps0(1-6) tps0z k idx(2))
   apply (tps_eq rules: tpsC_def tpsCA_def tpsR_def tpsL_def tps0(1-6) tps0z k)?
  by (lin facts: assms sqs ab_le HO_ge nlength_zero)

lemma tm_ocomp [transforms_intros]:
  assumes "ttt = 1200 * HO ^ 2"
  shows "transforms tm_ocomp tpsR ttt tpsC"
  unfolding tm_ocomp_def by (tform time: assms)

definition "tpsD \<equiv> tpsC[27 := (\<lfloor>oc (Suc t)\<rfloor>\<^sub>B, 1)]"

lemma tm_odec [transforms_intros]:
  assumes "ttt = 15"
  shows "transforms tm_odec tpsC ttt tpsD"
  unfolding tm_odec_def
proof (rule transforms_branchI)
  let ?c = "read tpsC ! 75 \<noteq> \<box> \<and> read tpsC ! 81 \<noteq> \<box> \<or> read tpsC ! 84 \<noteq> \<box> \<and> read tpsC ! 90 \<noteq> \<box>"
  have c: "?c \<longleftrightarrow> ocond n es S nssc t"
  proof -
    have l: "length tpsC = 93"
      using k by (simp add: tpsC_def tpsR_def tpsL_def)
    have v: "tpsC ! 75 = (\<lfloor>a \<in> set S\<rfloor>\<^sub>B, 1)" "tpsC ! 81 = (\<lfloor>b \<in> set NA\<rfloor>\<^sub>B, 1)"
      "tpsC ! 84 = (\<lfloor>b \<in> set S\<rfloor>\<^sub>B, 1)" "tpsC ! 90 = (\<lfloor>a \<in> set NB\<rfloor>\<^sub>B, 1)"
      using k by (simp_all add: tpsC_def tpsR_def tpsL_def)
    show ?thesis
      using read_ncontents_eq_0[OF v(1)] read_ncontents_eq_0[OF v(2)] read_ncontents_eq_0[OF v(3)]
        read_ncontents_eq_0[OF v(4)] l guard unfolding ocond_def by simp
  qed
  show "transforms [] tpsC 0 tpsD" if ?c
  proof -
    have e: "oc (Suc t) = oc t"
      using that c oc_Suc by blast
    have "tpsD = tpsC"
      by (tps_eq rules: tpsD_def tpsC_def tpsR_def tpsL_def k e)
    then show ?thesis
      using transforms_Nil by simp
  qed
  show "transforms (tm_setn 27 0) tpsC (10 + 2 * nlength (if oc t then 1 else 0) + 2 * nlength 0) tpsD"
    if "\<not> ?c"
  proof -
    have e: "\<not> oc (Suc t)"
      using that c oc_Suc by blast
    show ?thesis
      apply (tform tps: tpsC_def tpsR_def tpsL_def k)
      by (tps_eq rules: tpsD_def tpsC_def tpsR_def tpsL_def k e)
  qed
qed (use assms in \<open>simp_all add: nlength_zero nlength_Suc0\<close>)

definition "tpsE \<equiv> tpsR[27 := (\<lfloor>oc (Suc t)\<rfloor>\<^sub>B, 1)]"

lemma tm_oclean [transforms_intros]:
  assumes "ttt = 200 * HO"
  shows "transforms tm_oclean tpsD ttt tpsE"
  unfolding tm_oclean_def
  apply (rule transforms_monotone)
   apply (tform tps: tpsD_def tpsC_def tpsR_def tpsL_def k)
   apply (tps_eq rules: tpsE_def tpsD_def tpsC_def tpsR_def tpsL_def tps0(1-6) tps0z k)?
  using assms ab_le NAB_le HO_ge nlength_Suc[of a] nlength_Suc[of b]
  by (simp add: nlength_zero nlength_1_simp nlength_Suc0)

lemma tm_ochk [transforms_intros]:
  assumes "ttt = 1200 * HO ^ 2 + 15 + 200 * HO"
  shows "transforms tm_ochk tpsR ttt tpsE"
  unfolding tm_ochk_def by (tform time: assms)

end

definition "tpsE' \<equiv> tpsR[27 := (\<lfloor>oc (Suc t)\<rfloor>\<^sub>B, 1)]"

lemma tm_oif [transforms_intros]:
  assumes "ttt = 1600 * HO ^ 2"
  shows "transforms tm_oif tpsR ttt tpsE'"
  unfolding tm_oif_def
proof (rule transforms_branchI)
  let ?g = "read tpsR ! 68 = \<box> \<and> read tpsR ! 69 \<noteq> \<box> \<and> read tpsR ! 72 \<noteq> \<box>"
  have g: "?g \<longleftrightarrow> a \<noteq> b \<and> a < n \<and> b < n"
  proof -
    have l: "length tpsR = 93"
      using k by (simp add: tpsR_def tpsL_def)
    have v: "tpsR ! 68 = (\<lfloor>a = b\<rfloor>\<^sub>B, 1)" "tpsR ! 69 = (\<lfloor>a < n\<rfloor>\<^sub>B, 1)" "tpsR ! 72 = (\<lfloor>b < n\<rfloor>\<^sub>B, 1)"
      using k by (simp_all add: tpsR_def tpsL_def)
    show ?thesis
      using read_ncontents_eq_0[OF v(1)] read_ncontents_eq_0[OF v(2)] read_ncontents_eq_0[OF v(3)] l
      by simp
  qed
  show "transforms tm_ochk tpsR (1200 * HO ^ 2 + 15 + 200 * HO) tpsE'" if ?g
    using tm_ochk[of "1200 * HO ^ 2 + 15 + 200 * HO"] that g tpsE_def tpsE'_def by simp
  show "transforms [] tpsR 0 tpsE'" if "\<not> ?g"
  proof -
    have e: "oc (Suc t) = oc t"
      using that g oc_Suc unfolding ocond_def by blast
    have "tpsE' = tpsR"
      by (tps_eq rules: tpsE'_def tpsR_def tpsL_def k e)
    then show ?thesis
      using transforms_Nil by simp
  qed
  show "1200 * HO ^ 2 + 15 + 200 * HO + 2 \<le> ttt" if ?g
    by (lin facts: assms HO_ge)
qed (use assms HO_ge in simp_all)

definition "tpsF \<equiv> (tpsL t)
  [16 := nltape' es (Suc (Suc (2 * t))),
   27 := (\<lfloor>oc (Suc t)\<rfloor>\<^sub>B, 1)]"

lemma tm_oreset [transforms_intros]:
  assumes "ttt = 100 * HO"
  shows "transforms tm_oreset tpsE' ttt tpsF"
  unfolding tm_oreset_def
  apply (rule transforms_monotone)
   apply (tform tps: tpsE'_def tpsR_def tpsL_def k)
   apply (tps_eq rules: tpsF_def tpsE'_def tpsR_def tpsL_def tps0(1-6) tps0z k)?
  using assms ab_le HO_ge by (simp add: nlength_zero nlength_1_simp nlength_Suc0)

lemma tm_obody [transforms_intros]:
  assumes "ttt = 3100 * HO ^ 2"
  shows "transforms tm_obody (tpsL t) ttt (tpsL (Suc t))"
  unfolding tm_obody_def
  apply (rule transforms_monotone)
   apply (tform tps: tpsF_def tpsL_def k)
   apply (tps_eq rules: tpsL_def tpsF_def k)?
  using assms ab_le HO_ge nlength_le_n[of "P - t"] t
  by (simp add: nlength_zero nlength_1_simp nlength_Suc0)
end

lemma read_tpsL: "read (tpsL t) ! 65 \<noteq> \<box> \<longleftrightarrow> t < P"
proof -
  have "tpsL t ! 65 = (\<lfloor>P - t\<rfloor>\<^sub>N, 1)" "65 < length (tpsL t)"
    using k by (simp_all add: tpsL_def)
  from read_ncontents_eq_0[OF this] show ?thesis
    by (simp add: not_le)
qed

lemma tm_opre:
  "transforms tm_opre tps0 (tps0 :#: 11 + 2 + (14 + 3 * (nlength (length es) + nlength 0)) +
      (2 * nlength (length es) + 3)) (tpsL 0)"
  unfolding tm_opre_def
  apply (tform tps: tps0(1-6) tps0' tps0z k clean_tape_nllcontents)
  by (tps_eq rules: tpsL_def tps0(1-6) tps0' k oc_def)

lemma tmL:
  assumes "ttt = P * (3100 * HO ^ 2 + 2) + 1"
  shows "transforms (WHILE [] ; \<lambda>rs. rs ! 65 \<noteq> \<box> DO tm_obody DONE) (tpsL 0) ttt (tpsL P)"
  by (tform tps: read_tpsL time: assms)

lemma tm_owners:
  assumes "ttt = 3400 * HO ^ 3"
  shows "transforms tm_owners tps0 ttt (tpsL P)"
proof -
  have pos: "tps0 :#: 11 \<le> Suc (nlllength nssc)"
  proof -
    have "nlllength (take p nssc) \<le> nlllength nssc"
      using p by (metis append_take_drop_id le_add1 nlllength_append)
    then show ?thesis
      using tps0(1) by simp
  qed
  have h: "1 \<le> HO" "HO \<le> HO ^ 2" "HO ^ 2 \<le> HO ^ 3" "HO \<le> HO ^ 3" "1 \<le> HO ^ 3"
    using HO_ge power_increasing[of 2 3 HO] power_increasing[of 1 3 HO] by simp_all
  have l: "nlength (length es) \<le> HO"
    using nlength_le_n[of "length es"] HO_ge by simp
  have "P * (3100 * HO ^ 2 + 2) \<le> HO * (3102 * HO ^ 2)"
    using HO_ge h by (intro mult_le_mono) simp_all
  also have "\<dots> = 3102 * HO ^ 3"
    by (simp add: power2_eq_square power3_eq_cube)
  finally have q: "P * (3100 * HO ^ 2 + 2) \<le> 3102 * HO ^ 3" .
  have "transforms tm_owners tps0 (tps0 :#: 11 + 2 + (14 + 3 * (nlength (length es) + nlength 0)) +
      (2 * nlength (length es) + 3) + (P * (3100 * HO ^ 2 + 2) + 1)) (tpsL P)"
    unfolding tm_owners_def by (rule transforms_tm_sequentialI[OF tm_opre tmL[OF refl] refl])
  then show ?thesis
    by (rule transforms_monotone) (lin facts: pos q h l HO_ge assms nlength_zero)
qed

lemma oc_P: "oc P \<longleftrightarrow> own_ok n es S nssc"
  unfolding oc_def using own_ok_iff by simp

end

end

lemma transforms_tm_ownersI [transforms_intros]:
  fixes tps tps' :: "tape list" and nssc :: "nat list list" and es S :: "nat list" and n p ttt :: nat
  assumes "length tps = 93" "n < length nssc" "set S \<subseteq> {..<n}" "p \<le> length nssc"
  assumes
    "tps ! 11 = nlltape' nssc p"
    "tps ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps ! 33 = (\<lfloor>S\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 79 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 88 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "\<And>j. 66 \<le> j \<Longrightarrow> j \<le> 92 \<Longrightarrow> j \<noteq> 79 \<Longrightarrow> j \<noteq> 88 \<Longrightarrow> tps ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 16 = (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 65 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 20 = (\<lfloor>length es\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 3400 * (nlllength nssc + nllength es + nllength S + n + 2) ^ 3"
  assumes "tps' = tps
    [11 := (\<lfloor>nssc\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1),
     16 := nltape' es (2 * (length es div 2)),
     27 := (\<lfloor>own_ok n es S nssc\<rfloor>\<^sub>B, 1),
     65 := (\<lfloor>0\<rfloor>\<^sub>N, 1)]"
  shows "transforms tm_owners tps ttt tps'"
proof -
  interpret loc: turing_machine_owners .
  have "tps' = loc.tpsL tps nssc es S n (length es div 2)"
    by (tps_eq rules: loc.tpsL_def[OF assms(1-14)] loc.oc_P[OF assms(1-14)] assms(16) assms(1))
  then show ?thesis
    using loc.tm_owners[OF assms(1-14)] loc.HO_def[OF assms(1-14)] assms(15) by simp
qed

end
