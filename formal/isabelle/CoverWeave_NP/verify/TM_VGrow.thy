theory TM_VGrow
  imports TM_VFields
begin

section \<open>The verifier, phase 1: growing the cover along the certificate\<close>

text \<open>
Phase 1 starts with \<open>S = [c\<^sub>0]\<close> on tape 33 and reads the edge indices \<open>t\<close> of the certificate
from tape 21 into tape 34. While the flag on tape 27 is set, it performs @{const grow_step}: it
checks \<open>2t + 1 < |es|\<close>, reads the endpoints \<open>a, b\<close> of pair \<open>t\<close> (tapes 40, 41), checks
\<open>a \<noteq> b\<close>, \<open>a < n\<close>, \<open>b < n\<close> and appends the endpoint that is not yet known to be in \<open>S\<close>. Every
failure clears the flag. Tapes 35 to 54 are scratch.
\<close>

definition tm_gdec :: machine where
  "tm_gdec \<equiv>
    IF \<lambda>rs. rs ! 42 = \<box> \<and> rs ! 43 \<noteq> \<box> \<and> rs ! 46 \<noteq> \<box> \<and> rs ! 49 \<noteq> \<box> THEN
      tm_append 33 41 ;;
      tm_cr 33
    ELSE
      IF \<lambda>rs. rs ! 42 = \<box> \<and> rs ! 43 \<noteq> \<box> \<and> rs ! 46 \<noteq> \<box> \<and> rs ! 52 \<noteq> \<box> THEN
        tm_append 33 40 ;;
        tm_cr 33
      ELSE
        tm_setn 27 0
      ENDIF
    ENDIF"

definition tm_ginner1 :: machine where
  "tm_ginner1 \<equiv>
    tm_nth 16 35 40 \<bar> ;;
    tm_nth 16 36 41 \<bar> ;;
    tm_equalsn 40 41 42 ;;
    tm_lt 40 19 43 ;;
    tm_lt 41 19 46 ;;
    tm_contains 33 40 49 ;;
    tm_contains 33 41 52"

definition tm_ginner3 :: machine where
  "tm_ginner3 \<equiv>
    tm_setn 40 0 ;;
    tm_setn 41 0 ;;
    tm_setn 42 0 ;;
    tm_setn 43 0 ;;
    tm_setn 46 0 ;;
    tm_setn 49 0 ;;
    tm_setn 52 0"

definition tm_ginner :: machine where
  "tm_ginner \<equiv> tm_ginner1 ;; tm_gdec ;; tm_ginner3"

definition tm_gstep1 :: machine where
  "tm_gstep1 \<equiv>
    tm_copyn 34 35 ;;
    tm_times2 35 ;;
    tm_copyn 35 36 ;;
    tm_incr 36 ;;
    tm_lt 36 20 37"

definition tm_gstep2 :: machine where
  "tm_gstep2 \<equiv> IF \<lambda>rs. rs ! 37 \<noteq> \<box> THEN tm_ginner ELSE tm_setn 27 0 ENDIF"

definition tm_gstep3 :: machine where
  "tm_gstep3 \<equiv> tm_setn 35 0 ;; tm_setn 36 0 ;; tm_setn 37 0"

definition tm_gstep :: machine where
  "tm_gstep \<equiv> tm_gstep1 ;; tm_gstep2 ;; tm_gstep3"

definition tm_gbody :: machine where
  "tm_gbody \<equiv>
    tm_nextract \<bar> 21 34 ;;
    IF \<lambda>rs. rs ! 27 \<noteq> \<box> THEN tm_gstep ELSE [] ENDIF ;;
    tm_setn 34 0"

definition tm_grow :: machine where
  "tm_grow \<equiv>
    tm_append 33 23 ;;
    tm_cr 33 ;;
    WHILE [] ; \<lambda>rs. rs ! 21 \<noteq> \<box> DO tm_gbody DONE"

lemma tm_grow_tm:
  assumes "92 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_grow"
  unfolding tm_grow_def tm_gbody_def tm_gstep_def tm_gstep1_def tm_gstep2_def tm_gstep3_def
    tm_ginner_def tm_ginner1_def tm_ginner3_def tm_gdec_def
  using assms tm_append_tm tm_cr_tm tm_nextract_tm tm_setn_tm tm_copyn_tm tm_times2_tm tm_incr_tm
    tm_lt_tm tm_nth_tm tm_equalsn_tm tm_contains_tm Nil_tm turing_machine_loop_turing_machine
    turing_machine_branch_turing_machine
  by simp

lemma grow_step_set:
  assumes "set (snd st) \<subseteq> {..<n}"
  shows "set (snd (grow_step n es st t)) \<subseteq> {..<n}"
  using assms unfolding grow_step_def by (auto split: if_splits)

lemma grow_step_length: "length (snd (grow_step n es st t)) \<le> Suc (length (snd st))"
  unfolding grow_step_def by (auto split: if_splits)

lemma foldl_grow_set:
  assumes "set (snd st) \<subseteq> {..<n}"
  shows "set (snd (foldl (grow_step n es) st xs)) \<subseteq> {..<n}"
  using assms by (induction xs arbitrary: st) (simp_all add: grow_step_set)

lemma foldl_grow_length: "length (snd (foldl (grow_step n es) st xs)) \<le> length (snd st) + length xs"
proof (induction xs arbitrary: st)
  case (Cons x xs)
  have "length (snd (foldl (grow_step n es) (grow_step n es st x) xs)) \<le>
      length (snd (grow_step n es st x)) + length xs"
    by (rule Cons.IH)
  then show ?case
    using grow_step_length[of n es st x] by simp
qed simp

locale turing_machine_gstep
begin

context
  fixes tps0 :: "tape list" and es S :: "nat list" and n t :: nat
  assumes k: "length tps0 = 93"
  assumes S: "set S \<subseteq> {..<n}"
  assumes tps0:
    "tps0 ! 16 = (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps0 ! 20 = (\<lfloor>length es\<rfloor>\<^sub>N, 1)"
    "tps0 ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps0 ! 33 = (\<lfloor>S\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 34 = (\<lfloor>t\<rfloor>\<^sub>N, 1)"
    "\<And>j. 35 \<le> j \<Longrightarrow> j \<le> 54 \<Longrightarrow> tps0 ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

lemma tps0z:
  "tps0 ! 35 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 36 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 37 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 38 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 39 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 40 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 41 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 42 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 43 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 44 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 45 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 46 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 47 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 48 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 49 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 50 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 51 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 52 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  "tps0 ! 53 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps0 ! 54 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  using tps0(7) by simp_all

abbreviation "g \<equiv> grow_step n es (True, S) t"

definition "tps1 \<equiv> tps0
  [35 := (\<lfloor>2 * t\<rfloor>\<^sub>N, 1),
   36 := (\<lfloor>Suc (2 * t)\<rfloor>\<^sub>N, 1),
   37 := (\<lfloor>Suc (2 * t) < length es\<rfloor>\<^sub>B, 1)]"

definition "hs \<equiv> nllength es + nllength S + nlength t + n + 1"

lemma hs_ge:
  "1 \<le> hs" "hs \<le> hs ^ 2" "nllength es \<le> hs" "nllength S \<le> hs" "nlength t \<le> hs" "n \<le> hs"
  "length es \<le> hs" "nlength (length es) \<le> hs" "nlength n \<le> hs" "length S \<le> hs"
proof -
  show 1: "1 \<le> hs"
    unfolding hs_def by simp
  show "hs \<le> hs ^ 2"
    using 1 by (simp add: power2_eq_square)
  show e: "nllength es \<le> hs" and "nllength S \<le> hs" and "nlength t \<le> hs" and n: "n \<le> hs"
    unfolding hs_def by simp_all
  show l: "length es \<le> hs"
    using length_le_nllength[of es] e by simp
  show "nlength (length es) \<le> hs"
    using nlength_le_n[of "length es"] l by simp
  show "nlength n \<le> hs"
    using nlength_le_n[of n] n by simp
  show "length S \<le> hs"
    using length_le_nllength[of S] unfolding hs_def by simp
qed

lemma lt1_time:
  "100 * Suc (min (Suc (2 * t)) (length es)) * Suc (nlength (Suc (2 * t)) + nlength (length es)) \<le>
    800 * hs ^ 2"
proof -
  have "nlength (Suc (2 * t)) \<le> Suc (nlength t)"
    using nlength_times2plus1[of t] by simp
  then have "100 * Suc (min (Suc (2 * t)) (length es)) * Suc (nlength (Suc (2 * t)) + nlength (length es)) \<le>
      100 * (2 * hs) * (4 * hs)"
    using hs_ge by (intro mult_le_mono) simp_all
  also have "\<dots> = 800 * hs ^ 2"
    by (simp add: power2_eq_square algebra_simps)
  finally show ?thesis .
qed

lemma tm_gstep1 [transforms_intros]:
  assumes "ttt = 1000 * hs ^ 2"
  shows "transforms tm_gstep1 tps0 ttt tps1"
  unfolding tm_gstep1_def
  apply (rule transforms_monotone)
   apply (tform tps: tps0 tps0z k)
   apply (tps_eq rules: tps1_def tps0 tps0z k)?
  by (lin facts: assms lt1_time hs_ge nlength_times2[of t] nlength_zero)

context
  assumes R1: "Suc (2 * t) < length es"
begin

abbreviation "a \<equiv> es ! (2 * t)"
abbreviation "b \<equiv> es ! Suc (2 * t)"

definition "tpsI1 \<equiv> tps1
  [40 := (\<lfloor>a\<rfloor>\<^sub>N, 1),
   41 := (\<lfloor>b\<rfloor>\<^sub>N, 1),
   42 := (\<lfloor>a = b\<rfloor>\<^sub>B, 1),
   43 := (\<lfloor>a < n\<rfloor>\<^sub>B, 1),
   46 := (\<lfloor>b < n\<rfloor>\<^sub>B, 1),
   49 := (\<lfloor>a \<in> set S\<rfloor>\<^sub>B, 1),
   52 := (\<lfloor>b \<in> set S\<rfloor>\<^sub>B, 1)]"

lemma ab_le: "nlength a \<le> hs" "nlength b \<le> hs"
  using R1 member_le_nllength[of a es] member_le_nllength[of b es] hs_ge(3) by simp_all

lemma lt_ab_time:
  "100 * Suc (min a n) * Suc (nlength a + nlength n) \<le> 600 * hs ^ 2"
  "100 * Suc (min b n) * Suc (nlength b + nlength n) \<le> 600 * hs ^ 2"
proof -
  have "100 * Suc (min a n) * Suc (nlength a + nlength n) \<le> 100 * (2 * hs) * (3 * hs)"
    using hs_ge ab_le by (intro mult_le_mono) simp_all
  then show "100 * Suc (min a n) * Suc (nlength a + nlength n) \<le> 600 * hs ^ 2"
    by (simp add: power2_eq_square algebra_simps)
  have "100 * Suc (min b n) * Suc (nlength b + nlength n) \<le> 100 * (2 * hs) * (3 * hs)"
    using hs_ge ab_le by (intro mult_le_mono) simp_all
  then show "100 * Suc (min b n) * Suc (nlength b + nlength n) \<le> 600 * hs ^ 2"
    by (simp add: power2_eq_square algebra_simps)
qed

lemma sq_le: "(nllength es)\<^sup>2 \<le> hs ^ 2" "(nllength S)\<^sup>2 \<le> hs ^ 2"
  using hs_ge by (simp_all add: power_mono)

lemma tm_ginner1 [transforms_intros]:
  assumes "ttt = 1500 * hs ^ 2"
  shows "transforms tm_ginner1 tps1 ttt tpsI1"
  unfolding tm_ginner1_def
  apply (rule transforms_monotone)
   apply (tform tps: tps0 tps0z k tps1_def R1)
   apply (tps_eq rules: tpsI1_def tps1_def tps0 tps0z k)?
  by (lin facts: assms lt_ab_time sq_le hs_ge ab_le nlength_mono[OF min.cobounded1[of a b]])

lemma g_R1: "g = (if a \<noteq> b \<and> a < n \<and> b < n then
    (if a \<in> set S then (True, S @ [b]) else if b \<in> set S then (True, S @ [a]) else (False, S))
    else (False, S))"
  using R1 unfolding grow_step_def by simp

definition "tpsI2 \<equiv> tpsI1[27 := (\<lfloor>fst g\<rfloor>\<^sub>B, 1), 33 := (\<lfloor>snd g\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma read_tpsI1:
  "read tpsI1 ! 42 = \<box> \<longleftrightarrow> a \<noteq> b" "read tpsI1 ! 43 \<noteq> \<box> \<longleftrightarrow> a < n"
  "read tpsI1 ! 46 \<noteq> \<box> \<longleftrightarrow> b < n" "read tpsI1 ! 49 \<noteq> \<box> \<longleftrightarrow> a \<in> set S"
  "read tpsI1 ! 52 \<noteq> \<box> \<longleftrightarrow> b \<in> set S"
proof -
  have l: "length tpsI1 = 93"
    using k by (simp add: tpsI1_def tps1_def)
  have v: "tpsI1 ! 42 = (\<lfloor>a = b\<rfloor>\<^sub>B, 1)" "tpsI1 ! 43 = (\<lfloor>a < n\<rfloor>\<^sub>B, 1)"
    "tpsI1 ! 46 = (\<lfloor>b < n\<rfloor>\<^sub>B, 1)" "tpsI1 ! 49 = (\<lfloor>a \<in> set S\<rfloor>\<^sub>B, 1)"
    "tpsI1 ! 52 = (\<lfloor>b \<in> set S\<rfloor>\<^sub>B, 1)"
    using k by (simp_all add: tpsI1_def tps1_def)
  show "read tpsI1 ! 42 = \<box> \<longleftrightarrow> a \<noteq> b" "read tpsI1 ! 43 \<noteq> \<box> \<longleftrightarrow> a < n"
    "read tpsI1 ! 46 \<noteq> \<box> \<longleftrightarrow> b < n" "read tpsI1 ! 49 \<noteq> \<box> \<longleftrightarrow> a \<in> set S"
    "read tpsI1 ! 52 \<noteq> \<box> \<longleftrightarrow> b \<in> set S"
    using read_ncontents_eq_0[OF v(1)] read_ncontents_eq_0[OF v(2)] read_ncontents_eq_0[OF v(3)]
      read_ncontents_eq_0[OF v(4)] read_ncontents_eq_0[OF v(5)] l
    by simp_all
qed

lemma app_cr_time:
  "7 + nllength S - Suc 0 + 2 * nlength x + (Suc (nllength (S @ [x])) + 2) \<le> 30 * hs"
  if "nlength x \<le> hs" for x
  using that hs_ge by (simp add: nllength)

lemma tm_gdec [transforms_intros]:
  assumes "ttt = 40 * hs"
  shows "transforms tm_gdec tpsI1 ttt tpsI2"
  unfolding tm_gdec_def
proof (rule transforms_branchI)
  let ?c1 = "read tpsI1 ! 42 = \<box> \<and> read tpsI1 ! 43 \<noteq> \<box> \<and> read tpsI1 ! 46 \<noteq> \<box> \<and> read tpsI1 ! 49 \<noteq> \<box>"
  let ?c2 = "read tpsI1 ! 42 = \<box> \<and> read tpsI1 ! 43 \<noteq> \<box> \<and> read tpsI1 ! 46 \<noteq> \<box> \<and> read tpsI1 ! 52 \<noteq> \<box>"
  have c1: "?c1 \<longleftrightarrow> a \<noteq> b \<and> a < n \<and> b < n \<and> a \<in> set S"
    using read_tpsI1 by simp
  have c2: "?c2 \<longleftrightarrow> a \<noteq> b \<and> a < n \<and> b < n \<and> b \<in> set S"
    using read_tpsI1 by simp
  show "transforms (tm_append 33 41 ;; tm_cr 33) tpsI1 (30 * hs) tpsI2" if ?c1
  proof -
    have gg: "g = (True, S @ [b])"
      using that c1 g_R1 by simp
    show ?thesis
      apply (rule transforms_monotone)
       apply (tform tps: tpsI1_def tps1_def tps0 k clean_tape_nlcontents)
       apply (tps_eq rules: tpsI2_def tpsI1_def tps1_def tps0 k gg)?
      using app_cr_time[OF ab_le(2)] by (simp add: tpsI1_def tps1_def k tps0)
  qed
  show "transforms (IF \<lambda>rs. rs ! 42 = \<box> \<and> rs ! 43 \<noteq> \<box> \<and> rs ! 46 \<noteq> \<box> \<and> rs ! 52 \<noteq> \<box> THEN
        tm_append 33 40 ;; tm_cr 33 ELSE tm_setn 27 0 ENDIF) tpsI1 (35 * hs) tpsI2" if "\<not> ?c1"
  proof (rule transforms_branchI)
    show "transforms (tm_append 33 40 ;; tm_cr 33) tpsI1 (30 * hs) tpsI2" if ?c2
    proof -
      have gg: "g = (True, S @ [a])"
        using that \<open>\<not> ?c1\<close> c1 c2 g_R1 by auto
      show ?thesis
        apply (rule transforms_monotone)
         apply (tform tps: tpsI1_def tps1_def tps0 k clean_tape_nlcontents)
         apply (tps_eq rules: tpsI2_def tpsI1_def tps1_def tps0 k gg)?
        using app_cr_time[OF ab_le(1)] by (simp add: tpsI1_def tps1_def k tps0)
    qed
    show "transforms (tm_setn 27 0) tpsI1 12 tpsI2" if "\<not> ?c2"
    proof -
      have gg: "g = (False, S)"
        using that \<open>\<not> ?c1\<close> c1 c2 g_R1 by auto
      show ?thesis
        apply (rule transforms_monotone)
         apply (tform tps: tpsI1_def tps1_def tps0 k)
         apply (tps_eq rules: tpsI2_def tpsI1_def tps1_def tps0 k gg)?
        by (simp add: nlength_Suc0 nlength_zero)
    qed
  qed (use hs_ge in simp_all)
qed (use hs_ge assms in simp_all)

definition "tpsI3 \<equiv> tps1[27 := (\<lfloor>fst g\<rfloor>\<^sub>B, 1), 33 := (\<lfloor>snd g\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma tm_ginner3 [transforms_intros]:
  assumes "ttt = 100 * hs"
  shows "transforms tm_ginner3 tpsI2 ttt tpsI3"
proof -
  have bl: "nlength (if P then 1 else 0) \<le> 1" for P :: bool
    using nlength_1_simp nlength_zero by simp
  show ?thesis
    unfolding tm_ginner3_def
    apply (rule transforms_monotone)
     apply (tform tps: tpsI2_def tpsI1_def tps1_def tps0 k)
     apply (tps_eq rules: tpsI3_def tpsI2_def tpsI1_def tps1_def tps0 tps0z k)?
    using assms ab_le hs_ge by (simp add: nlength_zero nlength_1_simp nlength_Suc0)
qed

lemma tm_ginner [transforms_intros]:
  assumes "ttt = 1500 * hs ^ 2 + 40 * hs + 100 * hs"
  shows "transforms tm_ginner tps1 ttt tpsI3"
  unfolding tm_ginner_def by (tform time: assms)

end

definition "tpsG2 \<equiv> tps1[27 := (\<lfloor>fst g\<rfloor>\<^sub>B, 1), 33 := (\<lfloor>snd g\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma read_tps1: "read tps1 ! 37 \<noteq> \<box> \<longleftrightarrow> Suc (2 * t) < length es"
proof -
  have "tps1 ! 37 = (\<lfloor>Suc (2 * t) < length es\<rfloor>\<^sub>B, 1)" "37 < length tps1"
    using k by (simp_all add: tps1_def)
  from read_ncontents_eq_0[OF this] show ?thesis
    by simp
qed

lemma tm_gstep2 [transforms_intros]:
  assumes "ttt = 2000 * hs ^ 2"
  shows "transforms tm_gstep2 tps1 ttt tpsG2"
  unfolding tm_gstep2_def
proof (rule transforms_branchI)
  show "transforms tm_ginner tps1 (1500 * hs ^ 2 + 40 * hs + 100 * hs) tpsG2" if "read tps1 ! 37 \<noteq> \<box>"
    using tm_ginner that read_tps1 tpsI3_def tpsG2_def by simp
  show "transforms (tm_setn 27 0) tps1 12 tpsG2" if "\<not> read tps1 ! 37 \<noteq> \<box>"
  proof -
    have gg: "g = (False, S)"
      using that read_tps1 unfolding grow_step_def by simp
    show ?thesis
      apply (rule transforms_monotone)
       apply (tform tps: tps1_def tps0 k)
       apply (tps_eq rules: tpsG2_def tps1_def tps0 k gg)?
      by (simp add: nlength_Suc0 nlength_zero)
  qed
  show "1500 * hs ^ 2 + 40 * hs + 100 * hs + 2 \<le> ttt" if "read tps1 ! 37 \<noteq> \<box>"
    using assms hs_ge by simp
qed (use assms hs_ge in simp_all)

definition "tpsG \<equiv> tps0[27 := (\<lfloor>fst g\<rfloor>\<^sub>B, 1), 33 := (\<lfloor>snd g\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma tm_gstep3 [transforms_intros]:
  assumes "ttt = 50 * hs"
  shows "transforms tm_gstep3 tpsG2 ttt tpsG"
  unfolding tm_gstep3_def
  apply (rule transforms_monotone)
   apply (tform tps: tpsG2_def tps1_def tps0 k)
   apply (tps_eq rules: tpsG_def tpsG2_def tps1_def tps0 tps0z k)?
  using assms hs_ge nlength_times2[of t] nlength_times2plus1[of t]
  by (simp add: nlength_zero nlength_1_simp nlength_Suc0)

lemma tm_gstep:
  assumes "ttt = 3100 * hs ^ 2"
  shows "transforms tm_gstep tps0 ttt tpsG"
  unfolding tm_gstep_def
  apply (rule transforms_monotone)
   apply (tform)
  using assms hs_ge by simp

end

end


lemma transforms_tm_gstepI:
  fixes tps tps' :: "tape list" and es S :: "nat list" and n t ttt :: nat
  assumes "length tps = 93" "set S \<subseteq> {..<n}"
  assumes
    "tps ! 16 = (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps ! 20 = (\<lfloor>length es\<rfloor>\<^sub>N, 1)"
    "tps ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps ! 33 = (\<lfloor>S\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 34 = (\<lfloor>t\<rfloor>\<^sub>N, 1)"
    "\<And>j. 35 \<le> j \<Longrightarrow> j \<le> 54 \<Longrightarrow> tps ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 3100 * (nllength es + nllength S + nlength t + n + 1) ^ 2"
  assumes "tps' = tps
    [27 := (\<lfloor>fst (grow_step n es (True, S) t)\<rfloor>\<^sub>B, 1),
     33 := (\<lfloor>snd (grow_step n es (True, S) t)\<rfloor>\<^sub>N\<^sub>L, 1)]"
  shows "transforms tm_gstep tps ttt tps'"
proof -
  interpret loc: turing_machine_gstep .
  show ?thesis
    using loc.tm_gstep[OF assms(1-9)] loc.tpsG_def[OF assms(1-9)] loc.hs_def[OF assms(1-9)] assms(10,11)
    by simp
qed

locale turing_machine_grow
begin

definition "tmB \<equiv> WHILE [] ; \<lambda>rs. rs ! 21 \<noteq> \<box> DO tm_gbody DONE"
definition "tm2 \<equiv> tm_append 33 23 ;; tm_cr 33"
definition "tm3 \<equiv> tm2 ;; tmB"

lemma tm3_eq_tm_grow: "tm3 = tm_grow"
  unfolding tm3_def tm2_def tmB_def tm_grow_def by simp

context
  fixes tps0 :: "tape list" and es L0 :: "nat list" and n :: nat
  assumes k: "length tps0 = 93"
  assumes L0: "2 \<le> length L0" "L0 ! 1 < n"
  assumes tps0:
    "tps0 ! 16 = (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps0 ! 20 = (\<lfloor>length es\<rfloor>\<^sub>N, 1)"
    "tps0 ! 21 = nltape' L0 2"
    "tps0 ! 23 = (\<lfloor>L0 ! 1\<rfloor>\<^sub>N, 1)"
    "tps0 ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps0 ! 33 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "\<And>j. 34 \<le> j \<Longrightarrow> j \<le> 54 \<Longrightarrow> tps0 ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

abbreviation "ts \<equiv> drop 2 L0"
abbreviation "c0 \<equiv> L0 ! 1"

definition st :: "nat \<Rightarrow> bool \<times> nat list" where
  "st i \<equiv> foldl (grow_step n es) (True, [c0]) (take i ts)"

definition tpsL :: "nat \<Rightarrow> tape list" where
  "tpsL i \<equiv> tps0
    [21 := nltape' L0 (2 + i),
     27 := (\<lfloor>fst (st i)\<rfloor>\<^sub>B, 1),
     33 := (\<lfloor>snd (st i)\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma tm2 [transforms_intros]:
  assumes "ttt = 20 + 4 * nlength c0"
  shows "transforms tm2 tps0 ttt (tpsL 0)"
  unfolding tm2_def
  apply (rule transforms_monotone)
   apply (tform tps: tps0 k clean_tape_nlcontents)
   apply (tps_eq rules: tpsL_def st_def tps0 k)?
  using assms k by (simp add: nllength nth_list_update_if)

definition "HG \<equiv> nllength es + Suc n * nllength L0 + nllength L0 + n + 1"

lemma st_set: "set (snd (st i)) \<subseteq> {..<n}"
  unfolding st_def using foldl_grow_set L0 by simp

lemma st_length: "length (snd (st i)) \<le> length L0"
proof -
  have "length (snd (st i)) \<le> 1 + length (take i ts)"
    unfolding st_def using foldl_grow_length[of n es "(True, [c0])" "take i ts"] by simp
  also have "\<dots> \<le> length L0"
    using L0 by simp
  finally show ?thesis .
qed

lemma hs_HG:
  assumes "i < length ts"
  shows "nllength es + nllength (snd (st i)) + nlength (ts ! i) + n + 1 \<le> HG"
proof -
  have "\<forall>x\<in>set (snd (st i)). x \<le> n"
    using st_set by fastforce
  then have "nllength (snd (st i)) \<le> Suc (nlength n) * length (snd (st i))"
    by (rule nllength_le_len_mult_max)
  also have "\<dots> \<le> Suc n * nllength L0"
  proof (rule mult_le_mono)
    show "Suc (nlength n) \<le> Suc n"
      using nlength_le_n[of n] by simp
    show "length (snd (st i)) \<le> nllength L0"
      using st_length[of i] length_le_nllength[of L0] by linarith
  qed
  finally have 1: "nllength (snd (st i)) \<le> Suc n * nllength L0" .
  have "ts ! i \<in> set L0"
    using assms by (metis in_set_dropD nth_mem)
  then have "nlength (ts ! i) \<le> nllength L0"
    using member_le_nllength by blast
  then show ?thesis
    unfolding HG_def using 1 by simp
qed

lemma HG_ge: "1 \<le> HG" "HG \<le> HG ^ 2" "nllength L0 \<le> HG" "nlength c0 \<le> HG"
proof -
  show 1: "1 \<le> HG"
    unfolding HG_def by simp
  show "HG \<le> HG ^ 2"
    using 1 by (simp add: power2_eq_square)
  show l: "nllength L0 \<le> HG"
    unfolding HG_def by simp
  show "nlength c0 \<le> HG"
    using member_le_nllength[of c0 L0] L0 l by simp
qed

lemma st_Suc: "i < length ts \<Longrightarrow> st (Suc i) = grow_step n es (st i) (ts ! i)"
  unfolding st_def by (simp add: take_Suc_conv_app_nth)

lemma tps0z: "tps0 ! 34 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  using tps0(8) by simp

definition "tpsA i \<equiv> (tpsL i)[21 := nltape' L0 (Suc (2 + i)), 34 := (\<lfloor>ts ! i\<rfloor>\<^sub>N, 1)]"
definition "tpsB i \<equiv> (tpsA i)
  [27 := (\<lfloor>fst (st (Suc i))\<rfloor>\<^sub>B, 1),
   33 := (\<lfloor>snd (st (Suc i))\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma tmA:
  assumes "i < length ts" "ttt = 12 + 2 * nlength 0 + 2 * nlength (L0 ! (2 + i))"
  shows "transforms (tm_nextract \<bar> 21 34) (tpsL i) ttt (tpsA i)"
  apply (tform tps: tpsL_def tps0 tps0z k assms time: assms)
  by (tps_eq rules: tpsA_def tpsL_def k nth_drop assms(1) L0)

lemma tmIF:
  assumes "i < length ts" "ttt = 3100 * HG ^ 2 + 2"
  shows "transforms (IF \<lambda>rs. rs ! 27 \<noteq> \<box> THEN tm_gstep ELSE [] ENDIF) (tpsA i) ttt (tpsB i)"
proof (rule transforms_branchI)
  have r27: "read (tpsA i) ! 27 \<noteq> \<box> \<longleftrightarrow> fst (st i)"
  proof -
    have "tpsA i ! 27 = (\<lfloor>fst (st i)\<rfloor>\<^sub>B, 1)" "27 < length (tpsA i)"
      using k by (simp_all add: tpsA_def tpsL_def)
    from read_ncontents_eq_0[OF this] show ?thesis
      by simp
  qed
  let ?S = "snd (st i)" and ?t = "ts ! i"
  have hs: "3100 * (nllength es + nllength ?S + nlength ?t + n + 1) ^ 2 \<le> 3100 * HG ^ 2"
    using hs_HG[OF assms(1)] by (simp add: power_mono)
  show "transforms tm_gstep (tpsA i) (3100 * (nllength es + nllength ?S + nlength ?t + n + 1) ^ 2) (tpsB i)"
    if "read (tpsA i) ! 27 \<noteq> \<box>"
  proof (rule transforms_tm_gstepI[where S="?S" and n=n and es=es and t="?t"])
    have f: "fst (st i)"
      using that r27 by simp
    then have "st i = (True, ?S)"
      by (metis prod.collapse)
    then have "grow_step n es (True, ?S) ?t = st (Suc i)"
      using st_Suc[OF assms(1)] by simp
    then show "tpsB i = (tpsA i)
        [27 := (\<lfloor>fst (grow_step n es (True, ?S) ?t)\<rfloor>\<^sub>B, 1),
         33 := (\<lfloor>snd (grow_step n es (True, ?S) ?t)\<rfloor>\<^sub>N\<^sub>L, 1)]"
      unfolding tpsB_def by simp
    show "tpsA i ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
      using f k by (simp add: tpsA_def tpsL_def)
    show "tpsA i ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "35 \<le> j" "j \<le> 54" for j
      using that tps0(8) k by (simp add: tpsA_def tpsL_def)
  qed (use st_set k tps0 in \<open>simp_all add: tpsA_def tpsL_def\<close>)
  show "transforms [] (tpsA i) 0 (tpsA i)" if "\<not> read (tpsA i) ! 27 \<noteq> \<box>"
    using transforms_Nil .
  show "3100 * (nllength es + nllength ?S + nlength ?t + n + 1) ^ 2 + 2 \<le> ttt"
    if "read (tpsA i) ! 27 \<noteq> \<box>"
    using hs assms(2) by simp
  show "0 + 1 \<le> ttt" if "\<not> read (tpsA i) ! 27 \<noteq> \<box>"
    using assms(2) by simp
  show "tpsB i = tpsB i" if "read (tpsA i) ! 27 \<noteq> \<box>"
    by simp
  show "tpsB i = tpsA i" if "\<not> read (tpsA i) ! 27 \<noteq> \<box>"
  proof -
    have "\<not> fst (st i)"
      using that r27 by simp
    then have eq: "st (Suc i) = st i"
      using st_Suc[OF assms(1)] unfolding grow_step_def by simp
    show ?thesis
      by (tps_eq rules: tpsB_def tpsA_def tpsL_def k eq)
  qed
qed

lemma tmL_body [transforms_intros]:
  assumes "i < length ts" and "ttt = 3200 * HG ^ 2"
  shows "transforms tm_gbody (tpsL i) ttt (tpsL (Suc i))"
proof -
  have t: "nlength (L0 ! (2 + i)) \<le> HG"
  proof -
    have "L0 ! (2 + i) \<in> set L0"
      using assms(1) by simp
    then show ?thesis
      using member_le_nllength HG_ge(3) le_trans by blast
  qed
  have 3: "transforms (tm_setn 34 0) (tpsB i) (10 + 2 * nlength (L0 ! (2 + i)) + 2 * nlength 0)
      (tpsL (Suc i))"
    apply (tform tps: tpsB_def tpsA_def tpsL_def k assms(1) nth_drop time: nth_drop assms(1))
    by (tps_eq rules: tpsL_def tpsB_def tpsA_def k tps0z)
  have "transforms tm_gbody (tpsL i) (12 + 2 * nlength 0 + 2 * nlength (L0 ! (2 + i)) +
      (3100 * HG ^ 2 + 2) + (10 + 2 * nlength (L0 ! (2 + i)) + 2 * nlength 0)) (tpsL (Suc i))"
    unfolding tm_gbody_def
    by (rule transforms_tm_sequentialI[OF transforms_tm_sequentialI[OF tmA[OF assms(1) refl]
      tmIF[OF assms(1) refl]] 3]) simp_all
  then show ?thesis
    by (rule transforms_monotone) (lin facts: assms(2) t HG_ge nlength_zero)
qed

lemma read_tpsL: "read (tpsL i) ! 21 \<noteq> \<box> \<longleftrightarrow> i < length ts"
proof -
  have "read (tpsL i) ! 21 = |.| (nltape' L0 (2 + i))"
    using tapes_at_read'[of 21 "tpsL i"] k by (simp add: tpsL_def)
  then show ?thesis
    using nltape'_tape_read[of L0 "2 + i"] by auto
qed

lemma tmB [transforms_intros]:
  assumes "ttt = length ts * (3200 * HG ^ 2 + 2) + 1"
  shows "transforms tmB (tpsL 0) ttt (tpsL (length ts))"
  unfolding tmB_def
  by (tform tps: read_tpsL time: assms)

definition "tpsE \<equiv> tps0
  [21 := nltape' L0 (length L0),
   27 := (\<lfloor>fst (grow n es c0 ts)\<rfloor>\<^sub>B, 1),
   33 := (\<lfloor>snd (grow n es c0 ts)\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma tpsL_end: "tpsL (length ts) = tpsE"
  unfolding tpsL_def tpsE_def st_def grow_def using L0 by simp

lemma tm3:
  assumes "ttt = 3300 * HG ^ 3"
  shows "transforms tm3 tps0 ttt tpsE"
proof -
  have p: "HG ^ 2 \<le> HG ^ 3" "1 \<le> HG ^ 3" "HG \<le> HG ^ 3"
    using HG_ge power_increasing[of 2 3 HG] power_increasing[of 1 3 HG] by simp_all
  have "length ts * (3200 * HG ^ 2 + 2) \<le> HG * (3202 * HG ^ 2)"
  proof (rule mult_le_mono)
    show "length ts \<le> HG"
      using length_le_nllength[of L0] HG_ge(3) by simp
    show "3200 * HG ^ 2 + 2 \<le> 3202 * HG ^ 2"
      using HG_ge by simp
  qed
  also have "\<dots> = 3202 * HG ^ 3"
    by (simp add: power2_eq_square power3_eq_cube)
  finally have q: "length ts * (3200 * HG ^ 2 + 2) \<le> 3202 * HG ^ 3" .
  have "transforms tm3 tps0 (20 + 4 * nlength c0 + (length ts * (3200 * HG ^ 2 + 2) + 1)) (tpsL (length ts))"
    unfolding tm3_def by (tform time: assms)
  then show ?thesis
    unfolding tpsL_end by (rule transforms_monotone) (lin facts: q p HG_ge assms)
qed

end

end

lemma transforms_tm_growI [transforms_intros]:
  fixes tps tps' :: "tape list" and es L0 :: "nat list" and n ttt :: nat
  assumes "length tps = 93" "2 \<le> length L0" "L0 ! 1 < n"
  assumes
    "tps ! 16 = (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 19 = (\<lfloor>n\<rfloor>\<^sub>N, 1)"
    "tps ! 20 = (\<lfloor>length es\<rfloor>\<^sub>N, 1)"
    "tps ! 21 = nltape' L0 2"
    "tps ! 23 = (\<lfloor>L0 ! 1\<rfloor>\<^sub>N, 1)"
    "tps ! 27 = (\<lfloor>1\<rfloor>\<^sub>N, 1)"
    "tps ! 33 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "\<And>j. 34 \<le> j \<Longrightarrow> j \<le> 54 \<Longrightarrow> tps ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 3300 * (nllength es + Suc n * nllength L0 + nllength L0 + n + 1) ^ 3"
  assumes "tps' = tps
    [21 := nltape' L0 (length L0),
     27 := (\<lfloor>fst (grow n es (L0 ! 1) (drop 2 L0))\<rfloor>\<^sub>B, 1),
     33 := (\<lfloor>snd (grow n es (L0 ! 1) (drop 2 L0))\<rfloor>\<^sub>N\<^sub>L, 1)]"
  shows "transforms tm_grow tps ttt tps'"
proof -
  interpret loc: turing_machine_grow .
  show ?thesis
    using loc.tm3[OF assms(1-11)] loc.tpsE_def[OF assms(1-11)] loc.HG_def[OF assms(1-11)]
      loc.tm3_eq_tm_grow assms(12,13)
    by simp
qed

end
