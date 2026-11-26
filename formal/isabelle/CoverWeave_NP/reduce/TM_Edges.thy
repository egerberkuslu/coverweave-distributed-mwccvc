theory TM_Edges
  imports TM_Occ
begin

section \<open>The reduction machine, phase 2: the edge list\<close>

text \<open>
Phase 2 reads the clause list \<open>CL\<close> (tape 9) and the literal list \<open>LIT\<close> (tape 10) of the
occurrences, of common length \<open>N\<close> (tape 11), and writes the edge list of the gadget to
tape 23 and the weight list \<open>replicate (N + 1) 0\<close> to tape 24. Tapes 12 and 14 count the
occurrences \<open>a\<close> and \<open>b\<close>, tapes 13 and 15 count down, tapes 16 to 22 are scratch and tape 25
holds the number 0.
\<close>

definition adjc :: "nat list \<Rightarrow> nat list \<Rightarrow> nat \<Rightarrow> nat \<Rightarrow> bool" where
  "adjc CL LIT a b \<equiv> CL ! a = CL ! b \<or> (LIT ! a div 2 = LIT ! b div 2 \<and> LIT ! a \<noteq> LIT ! b)"

definition adjp :: "nat list \<Rightarrow> nat list \<Rightarrow> nat \<Rightarrow> nat \<Rightarrow> nat list" where
  "adjp CL LIT a b \<equiv> if adjc CL LIT a b then [a, b] else []"

definition erow :: "nat list \<Rightarrow> nat list \<Rightarrow> nat \<Rightarrow> nat list" where
  "erow CL LIT a \<equiv> concat (map (adjp CL LIT a) [0..<length CL]) @ [a, length CL]"

definition ees :: "nat list \<Rightarrow> nat list \<Rightarrow> nat list" where
  "ees CL LIT \<equiv> concat (map (erow CL LIT) [0..<length CL])"

lemma ees_gadget: "ees (map fst (occ nss)) (map snd (occ nss)) = gadget_es nss"
proof -
  let ?CL = "map fst (occ nss)" and ?LIT = "map snd (occ nss)"
  have row: "erow ?CL ?LIT a = gadget_row nss a" if "a < length (occ nss)" for a
  proof -
    have "concat (map (adjp ?CL ?LIT a) [0..<length (occ nss)]) =
        concat (map (\<lambda>b. if karp_adj nss a b then [a, b] else []) [0..<length (occ nss)])"
      by (rule arg_cong[where f=concat], rule map_cong)
        (use that in \<open>auto simp: adjp_def adjc_def karp_adj_def\<close>)
    then show ?thesis
      unfolding erow_def gadget_row_def by simp
  qed
  have "concat (map (erow ?CL ?LIT) [0..<length (occ nss)]) =
      concat (map (gadget_row nss) [0..<length (occ nss)])"
    by (rule arg_cong[where f=concat], rule map_cong) (simp_all add: row)
  then show ?thesis
    unfolding ees_def gadget_es_def by simp
qed

lemma nlength_min_le: "nlength (min x y) \<le> nlength x"
  using nlength_mono by simp

lemma nlength_div2_le: "nlength (x div 2) \<le> nlength x"
  using nlength_mono by simp

definition tm_adj1 :: machine where
  "tm_adj1 \<equiv>
    tm_nth 9 12 16 \<bar> ;;
    tm_nth 9 14 17 \<bar> ;;
    tm_equalsn 16 17 20 ;;
    tm_nth 10 12 18 \<bar> ;;
    tm_nth 10 14 19 \<bar> ;;
    tm_equalsn 18 19 21 ;;
    tm_div2 18 ;;
    tm_div2 19 ;;
    tm_equalsn 18 19 22"

definition tm_adj2 :: machine where
  "tm_adj2 \<equiv>
    IF \<lambda>rs. rs ! 20 \<noteq> \<box> \<or> (rs ! 22 \<noteq> \<box> \<and> rs ! 21 = \<box>) THEN
      tm_append 23 12 ;;
      tm_append 23 14
    ELSE
      []
    ENDIF"

definition tm_adj3 :: machine where
  "tm_adj3 \<equiv>
    tm_setn 16 0 ;;
    tm_setn 17 0 ;;
    tm_setn 18 0 ;;
    tm_setn 19 0 ;;
    tm_setn 20 0 ;;
    tm_setn 21 0 ;;
    tm_setn 22 0 ;;
    tm_incr 14 ;;
    tm_decr 15"

definition tm_edges :: machine where
  "tm_edges \<equiv>
    tm_copyn 11 13 ;;
    WHILE [] ; \<lambda>rs. rs ! 13 \<noteq> \<box> DO
      tm_copyn 11 15 ;;
      WHILE [] ; \<lambda>rs. rs ! 15 \<noteq> \<box> DO
        tm_adj1 ;;
        tm_adj2 ;;
        tm_adj3
      DONE ;;
      tm_append 23 12 ;;
      tm_append 23 11 ;;
      tm_append 24 25 ;;
      tm_setn 14 0 ;;
      tm_incr 12 ;;
      tm_decr 13
    DONE ;;
    tm_append 24 25"

lemma tm_edges_tm:
  assumes "25 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_edges"
  unfolding tm_edges_def tm_adj1_def tm_adj2_def tm_adj3_def
  using assms tm_nth_tm tm_equalsn_tm tm_div2_tm tm_append_tm tm_setn_tm tm_incr_tm tm_decr_tm
    tm_copyn_tm Nil_tm turing_machine_loop_turing_machine turing_machine_branch_turing_machine
  by simp

locale turing_machine_edges
begin

definition "tmB \<equiv> WHILE [] ; \<lambda>rs. rs ! 15 \<noteq> \<box> DO tm_adj1 ;; tm_adj2 ;; tm_adj3 DONE"
definition "tmA1 \<equiv> tm_copyn 11 15"
definition "tmA2 \<equiv> tmA1 ;; tmB"
definition "tmA3 \<equiv> tmA2 ;; tm_append 23 12"
definition "tmA4 \<equiv> tmA3 ;; tm_append 23 11"
definition "tmA5 \<equiv> tmA4 ;; tm_append 24 25"
definition "tmA6 \<equiv> tmA5 ;; tm_setn 14 0"
definition "tmA7 \<equiv> tmA6 ;; tm_incr 12"
definition "tmA8 \<equiv> tmA7 ;; tm_decr 13"
definition "tmA \<equiv> WHILE [] ; \<lambda>rs. rs ! 13 \<noteq> \<box> DO tmA8 DONE"
definition "tm1 \<equiv> tm_copyn 11 13"
definition "tm2 \<equiv> tm1 ;; tmA"
definition "tm3 \<equiv> tm2 ;; tm_append 24 25"

lemma tm3_eq_tm_edges: "tm3 = tm_edges"
  unfolding tm3_def tm2_def tm1_def tmA_def tmA8_def tmA7_def tmA6_def tmA5_def tmA4_def tmA3_def
    tmA2_def tmA1_def tmB_def tm_edges_def
  by simp

context
  fixes tps0 :: "tape list" and k :: nat and CL LIT :: "nat list"
  assumes k: "25 < k" "length tps0 = k"
    and len: "length LIT = length CL"
  assumes tps0:
    "tps0 ! 9 = (\<lfloor>CL\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 10 = (\<lfloor>LIT\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 11 = (\<lfloor>length CL\<rfloor>\<^sub>N, 1)"
    "tps0 ! 12 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 13 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 14 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 15 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 16 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 17 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 18 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 19 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 20 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 21 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 22 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 23 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 24 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 25 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

abbreviation "N \<equiv> length CL"
definition h :: nat where
  "h \<equiv> nllength CL + nllength LIT + 1"

definition pre :: "nat \<Rightarrow> nat \<Rightarrow> nat list" where
  "pre a b \<equiv> concat (map (erow CL LIT) [0..<a]) @ concat (map (adjp CL LIT a) [0..<b])"

definition tpsA :: "nat \<Rightarrow> tape list" where
  "tpsA a \<equiv> tps0
    [12 := (\<lfloor>a\<rfloor>\<^sub>N, 1),
     13 := (\<lfloor>N - a\<rfloor>\<^sub>N, 1),
     23 := nltape (concat (map (erow CL LIT) [0..<a])),
     24 := nltape (replicate a 0)]"

definition tpsB :: "nat \<Rightarrow> nat \<Rightarrow> tape list" where
  "tpsB a b \<equiv> tps0
    [12 := (\<lfloor>a\<rfloor>\<^sub>N, 1),
     13 := (\<lfloor>N - a\<rfloor>\<^sub>N, 1),
     14 := (\<lfloor>b\<rfloor>\<^sub>N, 1),
     15 := (\<lfloor>N - b\<rfloor>\<^sub>N, 1),
     23 := nltape (pre a b),
     24 := nltape (replicate a 0)]"

definition tpsP :: "nat \<Rightarrow> nat \<Rightarrow> tape list" where
  "tpsP a b \<equiv> (tpsB a b)
    [16 := (\<lfloor>CL ! a\<rfloor>\<^sub>N, 1),
     17 := (\<lfloor>CL ! b\<rfloor>\<^sub>N, 1),
     18 := (\<lfloor>LIT ! a div 2\<rfloor>\<^sub>N, 1),
     19 := (\<lfloor>LIT ! b div 2\<rfloor>\<^sub>N, 1),
     20 := (\<lfloor>if CL ! a = CL ! b then 1 else 0\<rfloor>\<^sub>N, 1),
     21 := (\<lfloor>if LIT ! a = LIT ! b then 1 else 0\<rfloor>\<^sub>N, 1),
     22 := (\<lfloor>if LIT ! a div 2 = LIT ! b div 2 then 1 else 0\<rfloor>\<^sub>N, 1)]"

definition tpsQ :: "nat \<Rightarrow> nat \<Rightarrow> tape list" where
  "tpsQ a b \<equiv> (tpsP a b)[23 := nltape (pre a (Suc b))]"

lemma CL_le: "x < N \<Longrightarrow> nlength (CL ! x) \<le> h"
  using member_le_nllength[of "CL ! x" CL] unfolding h_def by simp

lemma LIT_le: "x < N \<Longrightarrow> nlength (LIT ! x) \<le> h"
  using member_le_nllength[of "LIT ! x" LIT] len unfolding h_def by simp

lemma N_le: "N \<le> h"
  using length_le_nllength[of CL] unfolding h_def by simp

lemma CL_LIT_le: "nllength CL \<le> h" "nllength LIT \<le> h"
  unfolding h_def by simp_all

lemma idx_le: "x \<le> N \<Longrightarrow> nlength x \<le> h"
  using N_le nlength_le_n le_trans by blast

lemma h_ge: "1 \<le> h" "h \<le> h ^ 2" "1 \<le> h ^ 2"
proof -
  show 1: "1 \<le> h"
    unfolding h_def by simp
  show "h \<le> h ^ 2"
    using power_increasing[of 1 2 h] 1 by simp
  show "1 \<le> h ^ 2"
    using 1 by simp
qed

lemma tm_adj1 [transforms_intros]:
  assumes "a < N" "b < N" "ttt = 250 * h ^ 2"
  shows "transforms tm_adj1 (tpsB a b) ttt (tpsP a b)"
proof -
  have sq: "(nllength CL)\<^sup>2 \<le> h ^ 2" "(nllength LIT)\<^sup>2 \<le> h ^ 2"
    using CL_LIT_le by (simp_all add: power_mono)
  have m: "nlength (min (CL ! a) (CL ! b)) \<le> h" "nlength (min (LIT ! a) (LIT ! b)) \<le> h"
    "nlength (min (LIT ! a div 2) (LIT ! b div 2)) \<le> h"
    "nlength (LIT ! a) \<le> h" "nlength (LIT ! b) \<le> h"
    using CL_le[OF assms(1)] LIT_le[OF assms(1)] LIT_le[OF assms(2)]
      nlength_min_le[of "CL ! a" "CL ! b"] nlength_min_le[of "LIT ! a" "LIT ! b"]
      nlength_min_le[of "LIT ! a div 2" "LIT ! b div 2"] nlength_div2_le[of "LIT ! a"]
    by linarith+
  show ?thesis
    unfolding tm_adj1_def
    apply (rule transforms_monotone)
     apply (tform tps: assms tps0 k len tpsB_def)
     apply (tps_eq rules: tpsP_def tpsB_def k)?
    using sq m h_ge assms(3) by linarith
qed

lemma pre_Suc: "pre a (Suc b) = pre a b @ adjp CL LIT a b"
  unfolding pre_def by simp

lemma read_tpsP:
  assumes "a < N" "b < N"
  shows "read (tpsP a b) ! 20 \<noteq> \<box> \<longleftrightarrow> CL ! a = CL ! b"
    "read (tpsP a b) ! 21 = \<box> \<longleftrightarrow> LIT ! a \<noteq> LIT ! b"
    "read (tpsP a b) ! 22 \<noteq> \<box> \<longleftrightarrow> LIT ! a div 2 = LIT ! b div 2"
  using read_ncontents_eq_0[of "tpsP a b" 20] read_ncontents_eq_0[of "tpsP a b" 21]
    read_ncontents_eq_0[of "tpsP a b" 22] k
  by (simp_all add: tpsP_def tpsB_def)

lemma tm_adj2 [transforms_intros]:
  assumes "a < N" "b < N" "ttt = 20 * h"
  shows "transforms tm_adj2 (tpsP a b) ttt (tpsQ a b)"
proof -
  let ?c = "read (tpsP a b) ! 20 \<noteq> \<box> \<or> (read (tpsP a b) ! 22 \<noteq> \<box> \<and> read (tpsP a b) ! 21 = \<box>)"
  have c_iff: "?c \<longleftrightarrow> adjc CL LIT a b"
    using read_tpsP[OF assms(1,2)] unfolding adjc_def by auto
  have i: "nlength a \<le> h" "nlength b \<le> h"
    using idx_le assms(1,2) by simp_all
  show ?thesis
    unfolding tm_adj2_def
  proof (rule transforms_branchI)
    show "transforms (tm_append 23 12 ;; tm_append 23 14) (tpsP a b) (14 + 4 * h) (tpsQ a b)"
      if ?c
    proof -
      have p: "pre a (Suc b) = pre a b @ [a, b]"
        using that c_iff pre_Suc unfolding adjp_def by simp
      show ?thesis
        apply (rule transforms_monotone)
         apply (tform tps: assms tps0 k len tpsP_def tpsB_def)
         apply (tps_eq rules: tpsQ_def tpsP_def tpsB_def k p)?
        using i by simp
    qed
    show "transforms [] (tpsP a b) 0 (tpsP a b)" if "\<not> ?c"
      using transforms_Nil .
    show "14 + 4 * h + 2 \<le> ttt" if ?c
      using assms(3) h_ge by simp
    show "0 + 1 \<le> ttt" if "\<not> ?c"
      using assms(3) h_ge by simp
    show "tpsQ a b = tpsQ a b" if ?c
      by simp
    show "tpsQ a b = tpsP a b" if "\<not> ?c"
    proof -
      have na: "\<not> adjc CL LIT a b"
        using that c_iff by blast
      have p: "pre a (Suc b) = pre a b"
        using na pre_Suc unfolding adjp_def by simp
      show ?thesis
        by (tps_eq rules: tpsQ_def tpsP_def tpsB_def k p)
    qed
  qed
qed

lemma tm_adj3 [transforms_intros]:
  assumes "a < N" "b < N" "ttt = 100 + 20 * h"
  shows "transforms tm_adj3 (tpsQ a b) ttt (tpsB a (Suc b))"
proof -
  have m: "nlength (CL ! a) \<le> h" "nlength (CL ! b) \<le> h"
    "nlength (LIT ! a div 2) \<le> h" "nlength (LIT ! b div 2) \<le> h"
    "nlength b \<le> h" "nlength (N - b) \<le> h"
    using CL_le[OF assms(1)] CL_le[OF assms(2)] LIT_le[OF assms(1)] LIT_le[OF assms(2)]
      nlength_div2_le[of "LIT ! a"] nlength_div2_le[of "LIT ! b"] idx_le[of b] idx_le[of "N - b"] assms
    by linarith+
  have bl: "nlength (if P then 1 else 0) \<le> 1" for P :: bool
    using nlength_1_simp by simp
  show ?thesis
    unfolding tm_adj3_def
    apply (rule transforms_monotone)
     apply (tform tps: assms tps0 k len tpsQ_def tpsP_def tpsB_def)
     apply (tps_eq rules: tpsQ_def tpsP_def tpsB_def k tps0)?
    using m assms(3) by (simp add: nlength_Suc0 nlength_zero nlength_1_simp)
qed

lemma tm_body [transforms_intros]:
  assumes "a < N" "b < N" "ttt = 250 * h ^ 2 + 20 * h + (100 + 20 * h)"
  shows "transforms (tm_adj1 ;; tm_adj2 ;; tm_adj3) (tpsB a b) ttt (tpsB a (Suc b))"
  by (tform tps: assms)

lemma read_tpsB: "read (tpsB a b) ! 15 \<noteq> \<box> \<longleftrightarrow> b < N"
proof -
  have "tpsB a b ! 15 = (\<lfloor>N - b\<rfloor>\<^sub>N, 1)" "15 < length (tpsB a b)"
    using k by (simp_all add: tpsB_def)
  from read_ncontents_eq_0[OF this] show ?thesis
    by (simp add: not_le)
qed

definition "TB \<equiv> N * (250 * h ^ 2 + 40 * h + 102) + 1"

lemma tmB [transforms_intros]:
  assumes "a < N" "ttt = TB"
  shows "transforms tmB (tpsB a 0) ttt (tpsB a N)"
  unfolding tmB_def
  by (tform tps: assms read_tpsB time: assms TB_def)

lemma tmA1 [transforms_intros]:
  assumes "a < N" "ttt = 14 + 3 * (nlength N + nlength 0)"
  shows "transforms tmA1 (tpsA a) ttt (tpsB a 0)"
  unfolding tmA1_def
  apply (tform tps: assms tps0 k tpsA_def time: assms)
  by (tps_eq rules: tpsA_def tpsB_def pre_def k tps0)

lemma tmA2 [transforms_intros]:
  assumes "a < N" "ttt = 14 + 3 * (nlength N + nlength 0) + TB"
  shows "transforms tmA2 (tpsA a) ttt (tpsB a N)"
  unfolding tmA2_def by (tform tps: assms)

definition "TA \<equiv> TB + 60 + 20 * h"

lemma tmA8 [transforms_intros]:
  assumes "a < N" "ttt = TA"
  shows "transforms tmA8 (tpsA a) ttt (tpsA (Suc a))"
proof -
  have row: "concat (map (erow CL LIT) [0..<a]) @ erow CL LIT a = pre a N @ [a, N]"
    unfolding pre_def erow_def by simp
  have m: "nlength a \<le> h" "nlength N \<le> h" "nlength (N - a) \<le> h"
    using idx_le assms(1) by simp_all
  show ?thesis
    unfolding tmA8_def tmA7_def tmA6_def tmA5_def tmA4_def tmA3_def
    apply (rule transforms_monotone)
     apply (tform tps: assms tps0 k tpsB_def)
     apply (tps_eq rules: tpsA_def tpsB_def k tps0 row replicate_append_same)?
    using m assms(2) unfolding TA_def by (simp add: app_time nlength_zero)
qed

lemma read_tpsA: "read (tpsA a) ! 13 \<noteq> \<box> \<longleftrightarrow> a < N"
proof -
  have "tpsA a ! 13 = (\<lfloor>N - a\<rfloor>\<^sub>N, 1)" "13 < length (tpsA a)"
    using k by (simp_all add: tpsA_def)
  from read_ncontents_eq_0[OF this] show ?thesis
    by (simp add: not_le)
qed

lemma tmA [transforms_intros]:
  assumes "ttt = N * (TA + 2) + 1"
  shows "transforms tmA (tpsA 0) ttt (tpsA N)"
  unfolding tmA_def
  by (tform tps: read_tpsA time: assms)

lemma tm2 [transforms_intros]:
  assumes "ttt = 14 + 3 * (nlength 0 + nlength N) + (N * (TA + 2) + 1)"
  shows "transforms tm2 tps0 ttt (tpsA N)"
  unfolding tm2_def tm1_def
  apply (tform tps: tps0 k time: assms)
  by (tps_eq rules: tpsA_def k tps0)

definition "tps3 \<equiv> tps0
  [12 := (\<lfloor>N\<rfloor>\<^sub>N, 1),
   23 := nltape (ees CL LIT),
   24 := nltape (replicate (Suc N) 0)]"

lemma tm3:
  assumes "ttt = 600 * h ^ 4"
  shows "transforms tm3 tps0 ttt tps3"
proof -
  have p: "h \<le> h ^ 2" "h ^ 2 \<le> h ^ 3" "h ^ 3 \<le> h ^ 4" "1 \<le> h"
    using h_ge power_increasing[of 2 3 h] power_increasing[of 3 4 h] by simp_all
  have "N * (250 * h ^ 2 + 40 * h + 102) \<le> h * (250 * h ^ 2 + 40 * h + 102)"
    by (rule mult_le_mono1[OF N_le])
  also have "\<dots> = 250 * h ^ 3 + 40 * h ^ 2 + 102 * h"
    by (simp add: power2_eq_square power3_eq_cube algebra_simps)
  finally have "TB \<le> 250 * h ^ 3 + 40 * h ^ 2 + 102 * h + 1"
    unfolding TB_def by simp
  then have TA: "TA \<le> 480 * h ^ 3"
    unfolding TA_def using p by linarith
  have "N * (TA + 2) \<le> h * (482 * h ^ 3)"
    using N_le TA p by (intro mult_le_mono) linarith+
  also have "\<dots> = 482 * h ^ 4"
    by (simp add: power_def)
  finally have P: "N * (TA + 2) \<le> 482 * h ^ 4" .
  have hN: "nlength N \<le> h" "h \<le> h ^ 4" "1 \<le> h ^ 4"
    using idx_le p by simp_all
  obtain Q where Q: "Q = N * (TA + 2)"
    by simp
  have "14 + 3 * (nlength 0 + nlength N) + (Q + 1) + (7 + nllength (replicate N 0) -
      Suc (nllength (replicate N 0)) + 2 * nlength 0) \<le> ttt"
    by (lin facts: P[folded Q] hN assms)
  then have *: "14 + 3 * (nlength 0 + nlength N) + (N * (TA + 2) + 1) + (7 + nllength (replicate N 0) -
      Suc (nllength (replicate N 0)) + 2 * nlength 0) \<le> ttt"
    unfolding Q .
  show ?thesis
    unfolding tm3_def
    apply (rule transforms_monotone[OF _ *])
    apply (tform tps: tps0 k tpsA_def)
    by (tps_eq rules: tps3_def tpsA_def k tps0 ees_def replicate_append_same)
qed

end

end

lemma transforms_tm_edgesI [transforms_intros]:
  fixes tps tps' :: "tape list" and k ttt :: nat and CL LIT :: "nat list"
  assumes "25 < k" "length tps = k" "length LIT = length CL"
  assumes
    "tps ! 9 = (\<lfloor>CL\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 10 = (\<lfloor>LIT\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 11 = (\<lfloor>length CL\<rfloor>\<^sub>N, 1)"
    "tps ! 12 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 13 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 14 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 15 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 16 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 17 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 18 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 19 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 20 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 21 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 22 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 23 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 24 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 25 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 600 * (nllength CL + nllength LIT + 1) ^ 4"
  assumes "tps' = tps
    [12 := (\<lfloor>length CL\<rfloor>\<^sub>N, 1),
     23 := nltape (ees CL LIT),
     24 := nltape (replicate (Suc (length CL)) 0)]"
  shows "transforms tm_edges tps ttt tps'"
proof -
  interpret loc: turing_machine_edges .
  show ?thesis
    using loc.tm3[OF assms(1-20)] loc.tps3_def[OF assms(1-20)] loc.tm3_eq_tm_edges assms(21,22)
      loc.h_def[OF assms(1-20)]
    by simp
qed

end
