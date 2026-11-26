theory TM_VLoads
  imports TM_VWeights
begin

section \<open>The verifier, phase 3: the capacity bound\<close>

text \<open>
Phase 3 reads the lists \<open>N\<^sub>1, \<dots>, N\<^sub>n\<close> of the certificate one after another from tape 11 into
tape 60, counts each of them (tape 61) and clears the flag on tape 27 if a list is missing or
longer than the capacity \<open>k\<close> on tape 17. Tape 59 counts the vertices down.
\<close>

definition "tm_lchk \<equiv> IF \<lambda>rs. rs ! 62 \<noteq> \<box> THEN tm_setn 27 0 ELSE [] ENDIF"

definition "tm_lread1 \<equiv> tm_nextract \<sharp> 11 60 ;; tm_count 60 61 \<bar> ;; tm_lt 17 61 62"
definition "tm_lzero \<equiv> tm_setn 61 0 ;; tm_setn 62 0"
definition "tm_lread3 \<equiv> tm_erase_cr 60 ;; tm_lzero"
definition "tm_lread \<equiv> tm_lread1 ;; tm_lchk ;; tm_lread3"

definition "tm_lif \<equiv> IF \<lambda>rs. rs ! 11 = \<box> THEN tm_setn 27 0 ELSE tm_lread ENDIF"

definition "tm_lbody \<equiv> tm_lif ;; tm_decr 59"

definition tm_loads :: machine where
  "tm_loads \<equiv> tm_copyn 19 59 ;; WHILE [] ; \<lambda>rs. rs ! 59 \<noteq> \<box> DO tm_lbody DONE"

lemma tm_loads_tm:
  assumes "92 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_loads"
  unfolding tm_loads_def tm_lbody_def tm_lif_def tm_lread_def tm_lread1_def tm_lread3_def tm_lchk_def
    tm_lzero_def
  using assms tm_nextract_tm tm_count_tm tm_lt_tm tm_setn_tm tm_erase_cr_tm tm_decr_tm tm_copyn_tm
    Nil_tm turing_machine_loop_turing_machine turing_machine_branch_turing_machine
  by simp

locale turing_machine_loads
begin

context
  fixes tps0 :: "tape list" and nssc :: "nat list list" and n kk :: nat
  assumes k: "length tps0 = 93"
  assumes ne: "1 \<le> length nssc"
  assumes tps0:
    "tps0 ! 11 = nlltape' nssc 1"
    "tps0 ! 17 = (\<lfloor>kk\<rfloor>\<^sub>N, 1)"
    "tps0 ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps0 ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps0 ! 59 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 60 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 61 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 62 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 63 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 64 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

definition lok :: "nat \<Rightarrow> bool" where
  "lok v \<equiv> \<forall>u<v. Suc u < length nssc \<and> length (nssc ! Suc u) \<le> kk"

definition tpsL :: "nat \<Rightarrow> tape list" where
  "tpsL v \<equiv> tps0
    [11 := nlltape' nssc (min (Suc v) (length nssc)),
     27 := (\<lfloor>lok v\<rfloor>\<^sub>B, 1),
     59 := (\<lfloor>n - v\<rfloor>\<^sub>N, 1)]"

definition "HL \<equiv> nlllength nssc + nlength kk + n + 2"

lemma HL_ge: "1 \<le> HL" "HL \<le> HL ^ 2" "nlllength nssc \<le> HL" "nlength kk \<le> HL" "n \<le> HL"
proof -
  show 1: "1 \<le> HL"
    unfolding HL_def by simp
  show "HL \<le> HL ^ 2"
    using 1 by (simp add: power2_eq_square)
  show "nlllength nssc \<le> HL" "nlength kk \<le> HL" "n \<le> HL"
    unfolding HL_def by simp_all
qed

lemma lok_Suc:
  "lok (Suc v) \<longleftrightarrow> lok v \<and> Suc v < length nssc \<and> length (nssc ! Suc v) \<le> kk"
  unfolding lok_def using less_Suc_eq by auto

context
  fixes v :: nat
  assumes v: "v < n"
begin

definition "tpsR1 \<equiv> (tpsL v)
  [11 := nlltape' nssc (Suc (Suc v)),
   60 := (\<lfloor>nssc ! Suc v\<rfloor>\<^sub>N\<^sub>L, 1),
   61 := (\<lfloor>length (nssc ! Suc v)\<rfloor>\<^sub>N, 1),
   62 := (\<lfloor>kk < length (nssc ! Suc v)\<rfloor>\<^sub>B, 1)]"

definition "tpsR2 \<equiv> tpsR1[27 := (\<lfloor>lok (Suc v)\<rfloor>\<^sub>B, 1)]"

definition "tpsR3 \<equiv> (tpsL v)
  [11 := nlltape' nssc (Suc (Suc v)),
   27 := (\<lfloor>lok (Suc v)\<rfloor>\<^sub>B, 1)]"

context
  assumes in_range: "Suc v < length nssc"
begin

lemma Nv_le: "nllength (nssc ! Suc v) \<le> HL" "length (nssc ! Suc v) \<le> HL"
proof -
  show 1: "nllength (nssc ! Suc v) \<le> HL"
    using member_le_nlllength_1[of "nssc ! Suc v" nssc] in_range HL_ge by simp
  show "length (nssc ! Suc v) \<le> HL"
    using length_le_nllength[of "nssc ! Suc v"] 1 by simp
qed

lemma tm_lread1 [transforms_intros]:
  assumes "ttt = 800 * HL ^ 2"
  shows "transforms tm_lread1 (tpsL v) ttt tpsR1"
proof -
  have m: "min (Suc v) (length nssc) = Suc v"
    using in_range by simp
  have lt: "100 * Suc (min kk (length (nssc ! Suc v))) * Suc (nlength kk + nlength (length (nssc ! Suc v)))
      \<le> 600 * HL ^ 2"
  proof -
    have "100 * Suc (min kk (length (nssc ! Suc v))) * Suc (nlength kk + nlength (length (nssc ! Suc v)))
      \<le> 100 * (2 * HL) * (3 * HL)"
      using Nv_le HL_ge nlength_le_n[of "length (nssc ! Suc v)"] by (intro mult_le_mono) simp_all
    then show ?thesis
      by (simp add: power2_eq_square algebra_simps)
  qed
  have sq: "nllength (nssc ! Suc v) ^ 2 \<le> HL ^ 2"
    using Nv_le by (simp add: power_mono)
  show ?thesis
    unfolding tm_lread1_def
    apply (rule transforms_monotone)
     apply (tform tps: tpsL_def tps0 k m in_range)
     apply (tps_eq rules: tpsR1_def tpsL_def tps0 k m)?
    by (lin facts: lt sq Nv_le HL_ge assms nllength_Nil)
qed

lemma tm_lchk [transforms_intros]:
  assumes "ttt = 15"
  shows "transforms tm_lchk tpsR1 ttt tpsR2"
  unfolding tm_lchk_def
proof (rule transforms_branchI)
  have r: "read tpsR1 ! 62 \<noteq> \<box> \<longleftrightarrow> kk < length (nssc ! Suc v)"
  proof -
    have "tpsR1 ! 62 = (\<lfloor>kk < length (nssc ! Suc v)\<rfloor>\<^sub>B, 1)" "62 < length tpsR1"
      using k by (simp_all add: tpsR1_def tpsL_def)
    from read_ncontents_eq_0[OF this] show ?thesis
      by simp
  qed
  show "transforms (tm_setn 27 0) tpsR1 (10 + 2 * nlength (if lok v then 1 else 0) + 2 * nlength 0) tpsR2"
    if "read tpsR1 ! 62 \<noteq> \<box>"
  proof -
    have l: "\<not> lok (Suc v)"
      using that r lok_Suc by simp
    show ?thesis
      apply (tform tps: tpsR1_def tpsL_def k)
      by (tps_eq rules: tpsR2_def tpsR1_def tpsL_def k l)
  qed
  show "transforms [] tpsR1 0 tpsR2" if "\<not> read tpsR1 ! 62 \<noteq> \<box>"
  proof -
    have l: "lok (Suc v) = lok v"
      using that r lok_Suc in_range by simp
    have "tpsR2 = tpsR1"
      by (tps_eq rules: tpsR2_def tpsR1_def tpsL_def k l)
    then show ?thesis
      using transforms_Nil by simp
  qed
qed (use assms nlength_1_simp in \<open>simp_all add: nlength_zero\<close>)

lemma tm_lread3 [transforms_intros]:
  assumes "ttt = 100 * HL"
  shows "transforms tm_lread3 tpsR2 ttt tpsR3"
proof -
  have e: "tpsR2 ::: 60 = \<lfloor>numlist (nssc ! Suc v)\<rfloor>" "tpsR2 :#: 60 = 1"
    using k by (simp_all add: tpsR2_def tpsR1_def tpsL_def nlcontents_def)
  have "transforms (tm_erase_cr 60) tpsR2 (1 + 2 * length (numlist (nssc ! Suc v)) + 6)
      (tpsR2[60 := (\<lfloor>[]\<rfloor>, 1)])"
    by (rule transforms_tm_erase_crI[where zs="numlist (nssc ! Suc v)"])
      (use e k proper_symbols_numlist in \<open>simp_all add: tpsR2_def tpsR1_def tpsL_def\<close>)
  moreover have "transforms tm_lzero (tpsR2[60 := (\<lfloor>[]\<rfloor>, 1)])
      (10 + 2 * nlength (length (nssc ! Suc v)) + 2 * nlength 0 +
       (10 + 2 * nlength (if kk < length (nssc ! Suc v) then 1 else 0) + 2 * nlength 0)) tpsR3"
    unfolding tm_lzero_def
    apply (tform tps: tpsR2_def tpsR1_def tpsL_def k)
    by (tps_eq rules: tpsR3_def tpsR2_def tpsR1_def tpsL_def k tps0 nlcontents_Nil)
  ultimately have "transforms tm_lread3 tpsR2 (1 + 2 * length (numlist (nssc ! Suc v)) + 6 +
      (10 + 2 * nlength (length (nssc ! Suc v)) + 2 * nlength 0 +
       (10 + 2 * nlength (if kk < length (nssc ! Suc v) then 1 else 0) + 2 * nlength 0))) tpsR3"
    unfolding tm_lread3_def by (rule transforms_tm_sequentialI) simp_all
  then show ?thesis
    apply (rule transforms_monotone)
    using Nv_le HL_ge nlength_le_n[of "length (nssc ! Suc v)"] assms
    by (simp add: nllength_def[symmetric] nlength_1_simp nlength_Suc0)
qed

lemma tm_lread [transforms_intros]:
  assumes "ttt = 800 * HL ^ 2 + 15 + 100 * HL"
  shows "transforms tm_lread (tpsL v) ttt tpsR3"
  unfolding tm_lread_def by (tform time: assms)

end

definition "tpsQ \<equiv> (tpsL v)
  [11 := nlltape' nssc (min (Suc (Suc v)) (length nssc)),
   27 := (\<lfloor>lok (Suc v)\<rfloor>\<^sub>B, 1)]"

lemma tm_lif [transforms_intros]:
  assumes "ttt = 1000 * HL ^ 2"
  shows "transforms tm_lif (tpsL v) ttt tpsQ"
  unfolding tm_lif_def
proof (rule transforms_branchI)
  have r: "read (tpsL v) ! 11 = \<box> \<longleftrightarrow> length nssc \<le> Suc v"
  proof -
    have "read (tpsL v) ! 11 = |.| (nlltape' nssc (min (Suc v) (length nssc)))"
      using tapes_at_read'[of 11 "tpsL v"] k by (simp add: tpsL_def)
    then show ?thesis
      using nlltape'_tape_read[of nssc "min (Suc v) (length nssc)"] by simp
  qed
  show "transforms (tm_setn 27 0) (tpsL v) (10 + 2 * nlength (if lok v then 1 else 0) + 2 * nlength 0) tpsQ"
    if "read (tpsL v) ! 11 = \<box>"
  proof -
    have l: "\<not> lok (Suc v)" "min (Suc (Suc v)) (length nssc) = min (Suc v) (length nssc)"
      using that r lok_Suc by simp_all
    show ?thesis
      apply (tform tps: tpsL_def k)
      by (tps_eq rules: tpsQ_def tpsL_def k l)
  qed
  show "transforms tm_lread (tpsL v) (800 * HL ^ 2 + 15 + 100 * HL) tpsQ"
    if "\<not> read (tpsL v) ! 11 = \<box>"
  proof -
    have ir: "Suc v < length nssc"
      using that r by simp
    have m: "min (Suc (Suc v)) (length nssc) = Suc (Suc v)"
      using ir by simp
    have "tpsR3 = tpsQ"
      by (tps_eq rules: tpsR3_def tpsQ_def tpsL_def k m)
    then show ?thesis
      using tm_lread[OF ir refl] by simp
  qed
qed (use assms HL_ge nlength_1_simp in \<open>simp_all add: nlength_zero\<close>)

lemma tm_lbody [transforms_intros]:
  assumes "ttt = 1100 * HL ^ 2"
  shows "transforms tm_lbody (tpsL v) ttt (tpsL (Suc v))"
proof -
  have "transforms tm_lbody (tpsL v) (1000 * HL ^ 2 + (8 + 2 * nlength (n - v))) (tpsL (Suc v))"
    unfolding tm_lbody_def
    apply (tform tps: tpsQ_def tpsL_def k)
    by (tps_eq rules: tpsL_def tpsQ_def k)?
  moreover have "nlength (n - v) \<le> HL"
    using nlength_le_n[of "n - v"] HL_ge by simp
  ultimately show ?thesis
    using transforms_monotone assms HL_ge by fastforce
qed

end

lemma read_tpsL: "read (tpsL v) ! 59 \<noteq> \<box> \<longleftrightarrow> v < n"
proof -
  have "tpsL v ! 59 = (\<lfloor>n - v\<rfloor>\<^sub>N, 1)" "59 < length (tpsL v)"
    using k by (simp_all add: tpsL_def)
  from read_ncontents_eq_0[OF this] show ?thesis
    by (simp add: not_le)
qed

definition "tpsLD \<equiv> tps0
  [11 := nlltape' nssc (min (Suc n) (length nssc)),
   27 := (\<lfloor>lok n\<rfloor>\<^sub>B, 1)]"

lemma tm_loads:
  assumes "ttt = 1200 * HL ^ 3"
  shows "transforms tm_loads tps0 ttt tpsLD"
proof -
  have p: "HL ^ 2 \<le> HL ^ 3" "1 \<le> HL ^ 3" "HL \<le> HL ^ 3"
    using HL_ge power_increasing[of 2 3 HL] power_increasing[of 1 3 HL] by simp_all
  have q: "n * (1100 * HL ^ 2 + 2) \<le> HL * (1102 * HL ^ 2)"
    using HL_ge by (intro mult_le_mono) simp_all
  also have "\<dots> = 1102 * HL ^ 3"
    by (simp add: power2_eq_square power3_eq_cube)
  finally have q: "n * (1100 * HL ^ 2 + 2) \<le> 1102 * HL ^ 3" .
  have m0: "min (Suc 0) (length nssc) = Suc 0"
    using ne by simp
  have t1: "transforms (tm_copyn 19 59) tps0 (14 + 3 * (nlength n + nlength 0)) (tpsL 0)"
    apply (tform tps: tps0 k)
    by (tps_eq rules: tpsL_def tps0 k lok_def m0)
  have tL: "transforms (WHILE [] ; \<lambda>rs. rs ! 59 \<noteq> \<box> DO tm_lbody DONE) (tpsL 0)
      (n * (1100 * HL ^ 2 + 2) + 1) (tpsL n)"
    by (tform tps: read_tpsL)
  have "transforms tm_loads tps0 (14 + 3 * (nlength n + nlength 0) + (n * (1100 * HL ^ 2 + 2) + 1)) (tpsL n)"
    unfolding tm_loads_def by (rule transforms_tm_sequentialI[OF t1 tL refl])
  moreover have "tpsL n = tpsLD"
    by (tps_eq rules: tpsL_def tpsLD_def tps0 k)
  moreover have "nlength n \<le> HL"
    using nlength_le_n[of n] HL_ge by simp
  ultimately show ?thesis
    using transforms_monotone[of tm_loads tps0 _ tpsLD ttt] q p HL_ge assms by fastforce
qed

lemma lok_iff: "lok n \<longleftrightarrow> n < length nssc \<and> (\<forall>v<n. length (nssc ! Suc v) \<le> kk)"
  unfolding lok_def using ne by (cases n) auto

end

end


lemma transforms_tm_loadsI [transforms_intros]:
  fixes tps tps' :: "tape list" and nssc :: "nat list list" and n kk ttt :: nat
  assumes "length tps = 93" "1 \<le> length nssc"
  assumes
    "tps ! 11 = nlltape' nssc 1"
    "tps ! 17 = (\<lfloor>kk\<rfloor>\<^sub>N, 1)"
    "tps ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps ! 59 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 60 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 61 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 62 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 63 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 64 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 1200 * (nlllength nssc + nlength kk + n + 2) ^ 3"
  assumes "tps' = tps
    [11 := nlltape' nssc (min (Suc n) (length nssc)),
     27 := (\<lfloor>n < length nssc \<and> (\<forall>v<n. length (nssc ! Suc v) \<le> kk)\<rfloor>\<^sub>B, 1)]"
  shows "transforms tm_loads tps ttt tps'"
proof -
  interpret loc: turing_machine_loads .
  show ?thesis
    using loc.tm_loads[OF assms(1-12)] loc.tpsLD_def[OF assms(1-12)] loc.HL_def[OF assms(1-12)]
      loc.lok_iff[OF assms(1-12)] assms(13,14)
    by simp
qed

end
