theory TM_Occ
  imports CoverWeave_Base.MWCCVC_Language CoverWeave_Base.TM_Helpers
begin

section \<open>The reduction machine, phase 1: the literal occurrences\<close>

text \<open>
The reduction from \<open>SAT\<close> works on the list of clauses \<open>nss\<close> on tape 2. Phase 1 reads the
clauses one after another and writes two lists of numbers: tape 9 receives the clause index
and tape 10 the literal of every occurrence, in the order of @{const occ}.
Tapes 6, 7 and 8 hold the current clause, the current literal and the clause counter.
\<close>

definition tm_occ :: machine where
  "tm_occ \<equiv>
    WHILE [] ; \<lambda>rs. rs ! 2 \<noteq> \<box> DO
      tm_nextract \<sharp> 2 6 ;;
      WHILE [] ; \<lambda>rs. rs ! 6 \<noteq> \<box> DO
        tm_nextract \<bar> 6 7 ;;
        tm_append 9 8 ;;
        tm_append 10 7 ;;
        tm_setn 7 0
      DONE ;;
      tm_erase_cr 6 ;;
      tm_incr 8
    DONE"

lemma tm_occ_tm:
  assumes "10 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_occ"
  unfolding tm_occ_def
  using assms tm_nextract_tm tm_append_tm tm_setn_tm tm_erase_cr_tm tm_incr_tm Nil_tm
    turing_machine_loop_turing_machine
  by simp

lemma occ_snoc: "occ (xs @ [x]) = occ xs @ map (\<lambda>l. (length xs, l)) x"
proof -
  have "concat (map (\<lambda>j. map (Pair j) ((xs @ [x]) ! j)) [0..<length xs]) =
      concat (map (\<lambda>j. map (Pair j) (xs ! j)) [0..<length xs])"
    by (rule arg_cong[where f=concat], rule map_cong) (simp_all add: nth_append)
  then show ?thesis
    unfolding occ_def by simp
qed

lemma occ_take_Suc:
  assumes "j < length nss"
  shows "occ (take (Suc j) nss) = occ (take j nss) @ map (\<lambda>l. (j, l)) (nss ! j)"
  using assms occ_snoc[of "take j nss" "nss ! j"] by (simp add: take_Suc_conv_app_nth)

lemma replicate_Suc_snoc: "replicate (Suc t) x = replicate t x @ [x]"
  by (simp add: replicate_append_same)

lemma nllength_concat_le: "nllength (concat nss) \<le> nlllength nss"
proof (induction nss)
  case (Cons ns nss)
  then show ?case
    by (simp add: nllength numlist_append nlllength_Cons nllength_def[symmetric])
qed simp

locale turing_machine_occ
begin

definition "tmI1 \<equiv> tm_nextract \<bar> 6 7"
definition "tmI2 \<equiv> tmI1 ;; tm_append 9 8"
definition "tmI3 \<equiv> tmI2 ;; tm_append 10 7"
definition "tmI4 \<equiv> tmI3 ;; tm_setn 7 0"
definition "tmI \<equiv> WHILE [] ; \<lambda>rs. rs ! 6 \<noteq> \<box> DO tmI4 DONE"
definition "tmO1 \<equiv> tm_nextract \<sharp> 2 6"
definition "tmO2 \<equiv> tmO1 ;; tmI"
definition "tmO3 \<equiv> tmO2 ;; tm_erase_cr 6"
definition "tmO4 \<equiv> tmO3 ;; tm_incr 8"
definition "tmO \<equiv> WHILE [] ; \<lambda>rs. rs ! 2 \<noteq> \<box> DO tmO4 DONE"

lemma tmO_eq_tm_occ: "tmO = tm_occ"
  unfolding tmO_def tmO4_def tmO3_def tmO2_def tmO1_def tmI_def tmI4_def tmI3_def tmI2_def
    tmI1_def tm_occ_def
  by simp

context
  fixes tps0 :: "tape list" and k :: nat and nss :: "nat list list"
  assumes k: "10 < k" "length tps0 = k"
  assumes tps0:
    "tps0 ! 2 = nlltape' nss 0"
    "tps0 ! 6 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 7 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 8 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 9 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 10 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
begin

abbreviation "l \<equiv> nlllength nss"

definition oc :: "nat \<Rightarrow> (nat \<times> nat) list" where
  "oc j \<equiv> occ (take j nss)"

definition tpsO :: "nat \<Rightarrow> tape list" where
  "tpsO j \<equiv> tps0
    [2 := nlltape' nss j,
     8 := (\<lfloor>j\<rfloor>\<^sub>N, 1),
     9 := nltape (map fst (oc j)),
     10 := nltape (map snd (oc j))]"

definition tpsI :: "nat \<Rightarrow> nat \<Rightarrow> tape list" where
  "tpsI j t \<equiv> tps0
    [2 := nlltape' nss (Suc j),
     6 := nltape' (nss ! j) t,
     8 := (\<lfloor>j\<rfloor>\<^sub>N, 1),
     9 := nltape (map fst (oc j) @ replicate t j),
     10 := nltape (map snd (oc j) @ take t (nss ! j))]"

lemma lit_le:
  assumes "j < length nss" "t < length (nss ! j)"
  shows "nlength (nss ! j ! t) \<le> l"
proof -
  have "nlength (nss ! j ! t) \<le> nllength (nss ! j)"
    using assms member_le_nllength by simp
  also have "\<dots> \<le> l"
    using member_le_nlllength_1[OF nth_mem[OF assms(1)]] by simp
  finally show ?thesis .
qed

lemma clause_le:
  assumes "j < length nss"
  shows "nllength (nss ! j) \<le> l" "length (nss ! j) \<le> l"
proof -
  show *: "nllength (nss ! j) \<le> l"
    using member_le_nlllength_1[OF nth_mem[OF assms]] by simp
  show "length (nss ! j) \<le> l"
    using * length_le_nllength le_trans by blast
qed

lemma idx_le:
  assumes "j < length nss"
  shows "nlength j \<le> l"
  using assms length_le_nlllength nlength_le_n by (meson le_trans less_imp_le_nat)

lemma tmI4 [transforms_intros]:
  assumes "j < length nss" "t < length (nss ! j)" "ttt = 34 + 8 * l"
  shows "transforms tmI4 (tpsI j t) ttt (tpsI j (Suc t))"
  unfolding tmI4_def tmI3_def tmI2_def tmI1_def
proof (rule transforms_monotone)
  let ?A = "map fst (oc j) @ replicate t j"
  let ?B = "map snd (oc j) @ take t (nss ! j)"
  let ?x = "nss ! j ! t"
  show "transforms (tm_nextract \<bar> 6 7 ;; tm_append 9 8 ;; tm_append 10 7 ;; tm_setn 7 0)
      (tpsI j t)
      ((12 + 2 * nlength 0 + 2 * nlength ?x) + (7 + nllength ?A - Suc (nllength ?A) + 2 * nlength j) +
       (7 + nllength ?B - Suc (nllength ?B) + 2 * nlength ?x) + (10 + 2 * nlength ?x + 2 * nlength 0))
      (tpsI j (Suc t))"
  proof (tform tps: assms tps0 k tpsI_def)
    show "tpsI j (Suc t) = (tpsI j t)
        [6 := nltape' (nss ! j) (Suc t), 7 := (\<lfloor>nss ! j ! t\<rfloor>\<^sub>N, 1),
         9 := nltape (?A @ [j]), 10 := nltape (?B @ [?x]), 7 := (\<lfloor>0\<rfloor>\<^sub>N, 1)]"
      by (tps_eq rules: tpsI_def k tps0 assms replicate_append_same take_Suc_conv_app_nth)
  qed
  show "(12 + 2 * nlength 0 + 2 * nlength ?x) + (7 + nllength ?A - Suc (nllength ?A) + 2 * nlength j) +
       (7 + nllength ?B - Suc (nllength ?B) + 2 * nlength ?x) + (10 + 2 * nlength ?x + 2 * nlength 0) \<le> ttt"
    using assms(3) lit_le[OF assms(1,2)] idx_le[OF assms(1)] by simp
qed

lemma tmI [transforms_intros]:
  assumes "j < length nss" "ttt = length (nss ! j) * (36 + 8 * l) + 1"
  shows "transforms tmI (tpsI j 0) ttt (tpsI j (length (nss ! j)))"
  unfolding tmI_def
proof (tform tps: assms(1) time: assms(2))
  have *: "read (tpsI j t) ! 6 = |.| (nltape' (nss ! j) t)" for t
    using tapes_at_read'[of 6 "tpsI j t"] k unfolding tpsI_def by simp
  show "read (tpsI j t) ! 6 \<noteq> \<box>" if "t < length (nss ! j)" for t
    using * nltape'_tape_read that by simp
  show "\<not> read (tpsI j (length (nss ! j))) ! 6 \<noteq> \<box>"
    using *[of "length (nss ! j)"] nltape'_tape_read[of "nss ! j" "length (nss ! j)"] by simp
qed

lemma tmO1 [transforms_intros]:
  assumes "j < length nss" "ttt = 12 + 2 * nllength [] + 2 * nllength (nss ! j)"
  shows "transforms tmO1 (tpsO j) ttt (tpsI j 0)"
  unfolding tmO1_def
proof (tform tps: assms tps0 k tpsO_def time: assms(2))
  show "tpsI j 0 = (tpsO j)[2 := nlltape' nss (Suc j), 6 := (\<lfloor>nss ! j\<rfloor>\<^sub>N\<^sub>L, 1)]"
    by (tps_eq rules: tpsI_def tpsO_def k)
qed

lemma tmO2 [transforms_intros]:
  assumes "j < length nss"
    and "ttt = 12 + 2 * nllength [] + 2 * nllength (nss ! j) + (length (nss ! j) * (36 + 8 * l) + 1)"
  shows "transforms tmO2 (tpsO j) ttt (tpsI j (length (nss ! j)))"
  unfolding tmO2_def by (tform tps: assms)

lemma tmO3:
  assumes "j < length nss"
    and "ttt = 12 + 2 * nllength [] + 2 * nllength (nss ! j) + (length (nss ! j) * (36 + 8 * l) + 1) +
      (Suc (nllength (nss ! j)) + 2 * length (numlist (nss ! j)) + 6)"
  shows "transforms tmO3 (tpsO j) ttt ((tpsI j (length (nss ! j)))[6 := (\<lfloor>[]\<rfloor>, 1)])"
  unfolding tmO3_def
proof (rule transforms_tm_sequentialI[OF tmO2[OF assms(1) refl]])
  let ?tps = "tpsI j (length (nss ! j))"
  have "?tps ! 6 = nltape' (nss ! j) (length (nss ! j))"
    unfolding tpsI_def using k by simp
  then have six: "?tps ::: 6 = \<lfloor>numlist (nss ! j)\<rfloor>" "?tps :#: 6 = Suc (nllength (nss ! j))"
    by (simp_all add: nlcontents_def)
  show "transforms (tm_erase_cr 6) ?tps (Suc (nllength (nss ! j)) + 2 * length (numlist (nss ! j)) + 6)
      (?tps[6 := (\<lfloor>[]\<rfloor>, 1)])"
    by (rule transforms_tm_erase_crI[where zs="numlist (nss ! j)"])
      (use six k proper_symbols_numlist in \<open>simp_all add: tpsI_def\<close>)
  show "ttt = 12 + 2 * nllength [] + 2 * nllength (nss ! j) + (length (nss ! j) * (36 + 8 * l) + 1) +
      (Suc (nllength (nss ! j)) + 2 * length (numlist (nss ! j)) + 6)"
    using assms(2) .
qed

lemma tmO4 [transforms_intros]:
  assumes "j < length nss" and "ttt = 25 + 7 * l + l * (36 + 8 * l)"
  shows "transforms tmO4 (tpsO j) ttt (tpsO (Suc j))"
  unfolding tmO4_def
proof (rule transforms_monotone[OF transforms_tm_sequentialI[OF tmO3[OF assms(1) refl]]])
  let ?tps = "(tpsI j (length (nss ! j)))[6 := (\<lfloor>[]\<rfloor>, 1)]"
  show "transforms (tm_incr 8) ?tps (5 + 2 * nlength j) (tpsO (Suc j))"
  proof (rule transforms_tm_incrI[where x=j])
    show "?tps ! 8 = (\<lfloor>j\<rfloor>\<^sub>N, 1)"
      unfolding tpsI_def using k by simp
    have oc: "oc (Suc j) = oc j @ map (\<lambda>x. (j, x)) (nss ! j)"
      unfolding oc_def using occ_take_Suc assms(1) by simp
    show "tpsO (Suc j) = ?tps[8 := (\<lfloor>Suc j\<rfloor>\<^sub>N, 1)]"
      by (tps_eq rules: tpsO_def tpsI_def k tps0 oc nlcontents_Nil map_replicate_const comp_def)
  qed (use k in \<open>simp_all add: tpsI_def\<close>)
  show "12 + 2 * nllength [] + 2 * nllength (nss ! j) + (length (nss ! j) * (36 + 8 * l) + 1) +
      (Suc (nllength (nss ! j)) + 2 * length (numlist (nss ! j)) + 6) + (5 + 2 * nlength j) \<le> ttt"
  proof -
    have "length (nss ! j) * (36 + 8 * l) \<le> l * (36 + 8 * l)"
      using clause_le(2)[OF assms(1)] by simp
    moreover have "length (numlist (nss ! j)) = nllength (nss ! j)"
      by (simp add: nllength_def)
    ultimately show ?thesis
      using assms(2) clause_le[OF assms(1)] idx_le[OF assms(1)] nllength_Nil by linarith
  qed
qed simp

lemma tmO [transforms_intros]:
  assumes "ttt = length nss * (27 + 7 * l + l * (36 + 8 * l)) + 1"
  shows "transforms tmO (tpsO 0) ttt (tpsO (length nss))"
  unfolding tmO_def
proof (tform tps: assms time: assms)
  have *: "read (tpsO j) ! 2 = |.| (nlltape' nss j)" for j
    using tapes_at_read'[of 2 "tpsO j"] k unfolding tpsO_def by simp
  show "read (tpsO j) ! 2 \<noteq> \<box>" if "j < length nss" for j
    using * nlltape'_tape_read that by simp
  show "\<not> read (tpsO (length nss)) ! 2 \<noteq> \<box>"
    using *[of "length nss"] nlltape'_tape_read[of nss "length nss"] by simp
qed

lemma tpsO0: "tpsO 0 = tps0"
  by (tps_eq rules: tpsO_def oc_def occ_def k tps0 nlcontents_Nil)

lemma tpsO_end: "tpsO (length nss) = tps0
    [2 := nlltape' nss (length nss),
     8 := (\<lfloor>length nss\<rfloor>\<^sub>N, 1),
     9 := nltape (map fst (occ nss)),
     10 := nltape (map snd (occ nss))]"
  unfolding tpsO_def oc_def by simp

end

end

lemma transforms_tm_occI [transforms_intros]:
  fixes tps tps' :: "tape list" and k ttt :: nat and nss :: "nat list list"
  assumes "10 < k" "length tps = k"
  assumes
    "tps ! 2 = nlltape' nss 0"
    "tps ! 6 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 7 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 8 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 9 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 10 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
  assumes "ttt = length nss * (27 + 7 * nlllength nss + nlllength nss * (36 + 8 * nlllength nss)) + 1"
  assumes "tps' = tps
    [2 := nlltape' nss (length nss),
     8 := (\<lfloor>length nss\<rfloor>\<^sub>N, 1),
     9 := nltape (map fst (occ nss)),
     10 := nltape (map snd (occ nss))]"
  shows "transforms tm_occ tps ttt tps'"
proof -
  interpret loc: turing_machine_occ .
  show ?thesis
    using loc.tmO loc.tpsO0 loc.tpsO_end loc.tmO_eq_tm_occ assms by metis
qed

end
