theory TM_Helpers
  imports Cook_Levin.Satisfiability
begin

section \<open>Two helper Turing machines\<close>

subsection \<open>Equality of tape lists\<close>

text \<open>Tape lists built by updates are compared position by position.\<close>

lemma nth_list_update_if: "xs[i := x] ! j = (if i = j \<and> i < length xs then x else xs ! j)"
  by (cases "i < length xs") (auto simp: nth_list_update list_update_beyond)

lemma nlength_zero: "nlength 0 = 0"
  using nlength_0 by simp

lemma nlength_Suc0: "nlength (Suc 0) = 1"
  using nlength_1_simp by simp

lemma app_time: "7 + x - Suc x = (6::nat)"
  by simp

text \<open>Linear arithmetic on time bounds: \<open>linarith\<close> does not distribute a constant factor
over a sum, so the goal is normalised first.\<close>

method lin uses facts =
  (insert facts, (simp only: distrib_left distrib_right add_0 add_0_right mult_0_right mult_0 mult_Suc_right
     nlength_zero app_time)?, (linarith)?)

method tps_eq uses rules =
  (-, rule nth_equalityI; auto simp add: rules nth_list_update_if)


subsection \<open>Comparing numbers\<close>

text \<open>
\<open>tm_lt j1 j2 j3\<close> writes \<open>[a < b]\<close> to tape \<open>j3\<close> for numbers \<open>a\<close>, \<open>b\<close> on tapes \<open>j1\<close>, \<open>j2\<close>.
It decrements copies of both numbers until one of them is zero, so its running time is
polynomial whenever one of the two numbers is polynomially bounded in value. Every use below
compares with a list length or a vertex count. Tapes \<open>j3 + 1\<close> and \<open>j3 + 2\<close> are scratch.
\<close>

definition tm_lt :: "tapeidx \<Rightarrow> tapeidx \<Rightarrow> tapeidx \<Rightarrow> machine" where
  "tm_lt j1 j2 j3 \<equiv>
    tm_copyn j1 (j3 + 1) ;;
    tm_copyn j2 (j3 + 2) ;;
    WHILE [] ; \<lambda>rs. rs ! (j3 + 1) \<noteq> \<box> \<and> rs ! (j3 + 2) \<noteq> \<box> DO
      tm_decr (j3 + 1) ;;
      tm_decr (j3 + 2)
    DONE ;;
    IF \<lambda>rs. rs ! (j3 + 2) \<noteq> \<box> THEN tm_setn j3 1 ELSE [] ENDIF ;;
    tm_setn (j3 + 1) 0 ;;
    tm_setn (j3 + 2) 0"

lemma tm_lt_tm:
  assumes "j1 \<noteq> j2" "j1 < j3" "j2 < j3" "j3 + 2 < k" "G \<ge> 4" "k \<ge> 2"
  shows "turing_machine k G (tm_lt j1 j2 j3)"
  unfolding tm_lt_def
  using assms tm_copyn_tm tm_decr_tm tm_setn_tm Nil_tm turing_machine_loop_turing_machine
    turing_machine_branch_turing_machine
  by simp

locale turing_machine_lt =
  fixes j1 j2 j3 :: tapeidx
begin

definition "tm1 \<equiv> tm_copyn j1 (j3 + 1)"
definition "tm2 \<equiv> tm1 ;; tm_copyn j2 (j3 + 2)"
definition "tmL1 \<equiv> tm_decr (j3 + 1)"
definition "tmL2 \<equiv> tmL1 ;; tm_decr (j3 + 2)"
definition "tmL \<equiv> WHILE [] ; \<lambda>rs. rs ! (j3 + 1) \<noteq> \<box> \<and> rs ! (j3 + 2) \<noteq> \<box> DO tmL2 DONE"
definition "tm3 \<equiv> tm2 ;; tmL"
definition "tmI \<equiv> IF \<lambda>rs. rs ! (j3 + 2) \<noteq> \<box> THEN tm_setn j3 1 ELSE [] ENDIF"
definition "tm4 \<equiv> tm3 ;; tmI"
definition "tm5 \<equiv> tm4 ;; tm_setn (j3 + 1) 0"
definition "tm6 \<equiv> tm5 ;; tm_setn (j3 + 2) 0"

lemma tm6_eq_tm_lt: "tm6 = tm_lt j1 j2 j3"
  unfolding tm6_def tm5_def tm4_def tmI_def tm3_def tmL_def tmL2_def tmL1_def tm2_def tm1_def
    tm_lt_def
  by simp

context
  fixes tps0 :: "tape list" and k a b :: nat
  assumes jk: "j1 \<noteq> j2" "j1 < j3" "j2 < j3" "j3 + 2 < k" "length tps0 = k"
  assumes tps0:
    "tps0 ! j1 = (\<lfloor>a\<rfloor>\<^sub>N, 1)"
    "tps0 ! j2 = (\<lfloor>b\<rfloor>\<^sub>N, 1)"
    "tps0 ! j3 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! (j3 + 1) = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! (j3 + 2) = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

definition "tps1 \<equiv> tps0[j3 + 1 := (\<lfloor>a\<rfloor>\<^sub>N, 1)]"

lemma tm1 [transforms_intros]:
  assumes "ttt = 14 + 3 * nlength a"
  shows "transforms tm1 tps0 ttt tps1"
  unfolding tm1_def by (tform tps: tps0 tps1_def jk time: assms)

definition tpsL :: "nat \<Rightarrow> tape list" where
  "tpsL t \<equiv> tps0[j3 + 1 := (\<lfloor>a - t\<rfloor>\<^sub>N, 1), j3 + 2 := (\<lfloor>b - t\<rfloor>\<^sub>N, 1)]"

lemma tm2 [transforms_intros]:
  assumes "ttt = 28 + 3 * nlength a + 3 * nlength b"
  shows "transforms tm2 tps0 ttt (tpsL 0)"
  unfolding tm2_def by (tform tps: tps0 tps1_def tpsL_def jk time: assms)

definition tpsL1 :: "nat \<Rightarrow> tape list" where
  "tpsL1 t \<equiv> tps0[j3 + 1 := (\<lfloor>a - Suc t\<rfloor>\<^sub>N, 1), j3 + 2 := (\<lfloor>b - t\<rfloor>\<^sub>N, 1)]"

lemma tmL1 [transforms_intros]:
  assumes "ttt = 8 + 2 * nlength (a - t)"
  shows "transforms tmL1 (tpsL t) ttt (tpsL1 t)"
  unfolding tmL1_def by (tform tps: tpsL_def tpsL1_def jk time: assms)

lemma tmL2:
  assumes "ttt = 8 + 2 * nlength (a - t) + (8 + 2 * nlength (b - t))"
  shows "transforms tmL2 (tpsL t) ttt (tpsL (Suc t))"
  unfolding tmL2_def by (tform tps: tpsL_def tpsL1_def jk time: assms)

lemma tmL2' [transforms_intros]:
  assumes "ttt = 16 + 2 * nlength a + 2 * nlength b"
  shows "transforms tmL2 (tpsL t) ttt (tpsL (Suc t))"
proof -
  have "8 + 2 * nlength (a - t) + (8 + 2 * nlength (b - t)) \<le> ttt"
    using assms nlength_mono[of "a - t" a] nlength_mono[of "b - t" b] by simp
  then show ?thesis
    using tmL2 transforms_monotone by blast
qed

lemma read_tpsL:
  "read (tpsL t) ! (j3 + 1) \<noteq> \<box> \<longleftrightarrow> t < a"
  "read (tpsL t) ! (j3 + 2) \<noteq> \<box> \<longleftrightarrow> t < b"
proof -
  have "tpsL t ! (j3 + 1) = (\<lfloor>a - t\<rfloor>\<^sub>N, 1)" "tpsL t ! (j3 + 2) = (\<lfloor>b - t\<rfloor>\<^sub>N, 1)"
    "j3 + 1 < length (tpsL t)" "j3 + 2 < length (tpsL t)"
    using jk unfolding tpsL_def by simp_all
  then show "read (tpsL t) ! (j3 + 1) \<noteq> \<box> \<longleftrightarrow> t < a"
      "read (tpsL t) ! (j3 + 2) \<noteq> \<box> \<longleftrightarrow> t < b"
    using read_ncontents_eq_0 by (simp_all add: not_le)
qed

lemma tmL [transforms_intros]:
  assumes "ttt = min a b * (18 + 2 * nlength a + 2 * nlength b) + 1"
  shows "transforms tmL (tpsL 0) ttt (tpsL (min a b))"
  unfolding tmL_def
proof (tform)
  show "read (tpsL i) ! (j3 + 1) \<noteq> \<box> \<and> read (tpsL i) ! (j3 + 2) \<noteq> \<box>" if "i < min a b" for i
    using that read_tpsL by simp
  show "\<not> (read (tpsL (min a b)) ! (j3 + 1) \<noteq> \<box> \<and> read (tpsL (min a b)) ! (j3 + 2) \<noteq> \<box>)"
    using read_tpsL by simp
  show "min a b * (16 + 2 * nlength a + 2 * nlength b + 2) + 1 \<le> ttt"
    using assms by simp
qed

lemma tm3 [transforms_intros]:
  assumes "ttt = 29 + 3 * nlength a + 3 * nlength b + min a b * (18 + 2 * nlength a + 2 * nlength b)"
  shows "transforms tm3 tps0 ttt (tpsL (min a b))"
  unfolding tm3_def by (tform time: assms)

definition "tps4 \<equiv> tps0
  [j3 := (\<lfloor>a < b\<rfloor>\<^sub>B, 1),
   j3 + 1 := (\<lfloor>a - min a b\<rfloor>\<^sub>N, 1),
   j3 + 2 := (\<lfloor>b - min a b\<rfloor>\<^sub>N, 1)]"

lemma tmI [transforms_intros]:
  assumes "ttt = 14"
  shows "transforms tmI (tpsL (min a b)) ttt tps4"
  unfolding tmI_def
proof (tform tps: tpsL_def jk tps0 time: assms nlength_1_simp)
  show "10 + 2 * nlength 0 + 2 * nlength 1 + 2 \<le> ttt"
    using assms nlength_0 nlength_1_simp by simp
  have *: "read (tpsL (min a b)) ! (j3 + 2) \<noteq> \<box> \<longleftrightarrow> a < b"
    using read_tpsL(2)[of "min a b"] by (auto simp: min_def)
  show "tps4 = (tpsL (min a b))[j3 := (\<lfloor>1\<rfloor>\<^sub>N, 1)]"
    if "read (tpsL (min a b)) ! (j3 + 2) \<noteq> \<box>"
    using that * jk unfolding tps4_def tpsL_def by (simp add: list_update_swap)
  show "tps4 = tpsL (min a b)" if "\<not> read (tpsL (min a b)) ! (j3 + 2) \<noteq> \<box>"
  proof -
    have "\<not> a < b"
      using that * by simp
    then have "(\<lfloor>a < b\<rfloor>\<^sub>B, 1) = tps0 ! j3"
      using tps0 by simp
    then show ?thesis
      unfolding tps4_def tpsL_def using jk
      by (intro nth_equalityI) (auto simp: nth_list_update)
  qed
qed

definition "tps6 \<equiv> tps0[j3 := (\<lfloor>a < b\<rfloor>\<^sub>B, 1)]"

lemma tm6:
  assumes "ttt = 83 + 7 * nlength a + 7 * nlength b + min a b * (18 + 2 * nlength a + 2 * nlength b)"
  shows "transforms tm6 tps0 ttt tps6"
proof -
  let ?t = "29 + 3 * nlength a + 3 * nlength b + min a b * (18 + 2 * nlength a + 2 * nlength b) + 14 +
    (10 + 2 * nlength (a - min a b) + 2 * nlength 0) + (10 + 2 * nlength (b - min a b) + 2 * nlength 0)"
  have "transforms tm6 tps0 ?t tps6"
    unfolding tm6_def tm5_def tm4_def
  proof (tform tps: tps4_def tps6_def jk)
    show "tps6 = tps4[j3 + 1 := (\<lfloor>0\<rfloor>\<^sub>N, 1), j3 + 2 := (\<lfloor>0\<rfloor>\<^sub>N, 1)]"
      unfolding tps6_def tps4_def using tps0 jk
      by (intro nth_equalityI) (auto simp: nth_list_update)
  qed
  moreover have "?t \<le> ttt"
    using assms nlength_mono[of "a - min a b" a] nlength_mono[of "b - min a b" b] by simp
  ultimately show ?thesis
    using transforms_monotone by blast
qed

end

end

lemma transforms_tm_ltI [transforms_intros]:
  fixes j1 j2 j3 :: tapeidx
  fixes tps tps' :: "tape list" and ttt k a b :: nat
  assumes "j1 \<noteq> j2" "j1 < j3" "j2 < j3" "j3 + 2 < k" "length tps = k"
  assumes
    "tps ! j1 = (\<lfloor>a\<rfloor>\<^sub>N, 1)"
    "tps ! j2 = (\<lfloor>b\<rfloor>\<^sub>N, 1)"
    "tps ! j3 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! (j3 + 1) = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! (j3 + 2) = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 100 * Suc (min a b) * Suc (nlength a + nlength b)"
  assumes "tps' = tps[j3 := (\<lfloor>a < b\<rfloor>\<^sub>B, 1)]"
  shows "transforms (tm_lt j1 j2 j3) tps ttt tps'"
proof -
  interpret loc: turing_machine_lt j1 j2 j3 .
  let ?t = "83 + 7 * nlength a + 7 * nlength b + min a b * (18 + 2 * nlength a + 2 * nlength b)"
  have "transforms (tm_lt j1 j2 j3) tps ?t tps'"
    using loc.tm6 loc.tm6_eq_tm_lt loc.tps6_def assms by metis
  moreover have "?t \<le> ttt"
  proof -
    have "?t \<le> 100 * Suc (nlength a + nlength b) + min a b * (100 * Suc (nlength a + nlength b))"
      by (intro add_mono) auto
    also have "\<dots> = ttt"
      using assms(11) by (simp add: algebra_simps)
    finally show ?thesis .
  qed
  ultimately show ?thesis
    using transforms_monotone by blast
qed

subsection \<open>Indexing a list of lists\<close>

text \<open>
\<open>tm_nthl j1 j2 j3\<close> writes element \<open>i\<close> of the list of lists on tape \<open>j1\<close> to tape \<open>j3\<close>,
for the index \<open>i\<close> on tape \<open>j2\<close>; tape \<open>j3 + 1\<close> is scratch. It extracts elements
\<open>0, \<dots>, i\<close> one after another. Like Cook_Levin's \<open>tm_nth\<close> it must only be used in range.
\<close>

definition tm_nthl :: "tapeidx \<Rightarrow> tapeidx \<Rightarrow> tapeidx \<Rightarrow> machine" where
  "tm_nthl j1 j2 j3 \<equiv>
    tm_copyn j2 (j3 + 1) ;;
    WHILE [] ; \<lambda>rs. rs ! (j3 + 1) \<noteq> \<box> DO
      tm_nextract \<sharp> j1 j3 ;;
      tm_decr (j3 + 1)
    DONE ;;
    tm_nextract \<sharp> j1 j3 ;;
    tm_cr j1"

lemma tm_nthl_tm:
  assumes "0 < j1" "j1 \<noteq> j2" "j1 < j3" "j2 < j3" "j3 + 1 < k" "G \<ge> 6" "k \<ge> 2"
  shows "turing_machine k G (tm_nthl j1 j2 j3)"
  unfolding tm_nthl_def
  using assms tm_copyn_tm tm_decr_tm tm_nextract_tm tm_cr_tm Nil_tm turing_machine_loop_turing_machine
  by simp

locale turing_machine_nthl =
  fixes j1 j2 j3 :: tapeidx
begin

definition "tm1 \<equiv> tm_copyn j2 (j3 + 1)"
definition "tmL1 \<equiv> tm_nextract \<sharp> j1 j3"
definition "tmL2 \<equiv> tmL1 ;; tm_decr (j3 + 1)"
definition "tmL \<equiv> WHILE [] ; \<lambda>rs. rs ! (j3 + 1) \<noteq> \<box> DO tmL2 DONE"
definition "tm2 \<equiv> tm1 ;; tmL"
definition "tm3 \<equiv> tm2 ;; tm_nextract \<sharp> j1 j3"
definition "tm4 \<equiv> tm3 ;; tm_cr j1"

lemma tm4_eq_tm_nthl: "tm4 = tm_nthl j1 j2 j3"
  unfolding tm4_def tm3_def tm2_def tmL_def tmL2_def tmL1_def tm1_def tm_nthl_def by simp

context
  fixes tps0 :: "tape list" and k i :: nat and nss :: "nat list list"
  assumes jk: "0 < j1" "j1 \<noteq> j2" "j1 < j3" "j2 < j3" "j3 + 1 < k" "length tps0 = k"
    and i: "i < length nss"
  assumes tps0:
    "tps0 ! j1 = (\<lfloor>nss\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
    "tps0 ! j2 = (\<lfloor>i\<rfloor>\<^sub>N, 1)"
    "tps0 ! j3 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! (j3 + 1) = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

definition dum :: "nat \<Rightarrow> nat list" where
  "dum t \<equiv> if t = 0 then [] else nss ! (t - 1)"

definition tpsL :: "nat \<Rightarrow> tape list" where
  "tpsL t \<equiv> tps0
    [j1 := nlltape' nss t,
     j3 := (\<lfloor>dum t\<rfloor>\<^sub>N\<^sub>L, 1),
     j3 + 1 := (\<lfloor>i - t\<rfloor>\<^sub>N, 1)]"

lemma tm1 [transforms_intros]:
  assumes "ttt = 14 + 3 * nlength i"
  shows "transforms tm1 tps0 ttt (tpsL 0)"
  unfolding tm1_def
proof (tform tps: tps0 jk)
  show "ttt = 14 + 3 * (nlength i + nlength 0)"
    using assms by simp
  show "tpsL 0 = tps0[j3 + 1 := (\<lfloor>i\<rfloor>\<^sub>N, 1)]"
    unfolding tpsL_def dum_def using tps0 jk nlltape'_0
    by (intro nth_equalityI) (auto simp: nth_list_update)
qed

definition tpsL1 :: "nat \<Rightarrow> tape list" where
  "tpsL1 t \<equiv> tps0
    [j1 := nlltape' nss (Suc t),
     j3 := (\<lfloor>nss ! t\<rfloor>\<^sub>N\<^sub>L, 1),
     j3 + 1 := (\<lfloor>i - t\<rfloor>\<^sub>N, 1)]"

lemma tmL1 [transforms_intros]:
  assumes "t < length nss" and "ttt = 12 + 2 * nllength (dum t) + 2 * nllength (nss ! t)"
  shows "transforms tmL1 (tpsL t) ttt (tpsL1 t)"
  unfolding tmL1_def
proof (tform tps: assms(1) tpsL_def tpsL1_def jk time: assms(2))
  show "tpsL1 t = (tpsL t)[j1 := nlltape' nss (Suc t), j3 := (\<lfloor>nss ! t\<rfloor>\<^sub>N\<^sub>L, 1)]"
    unfolding tpsL1_def tpsL_def using jk by (simp add: list_update_swap)
qed

lemma tmL2:
  assumes "t < length nss"
    and "ttt = 12 + 2 * nllength (dum t) + 2 * nllength (nss ! t) + (8 + 2 * nlength (i - t))"
  shows "transforms tmL2 (tpsL t) ttt (tpsL (Suc t))"
  unfolding tmL2_def
proof (tform tps: assms(1) tpsL1_def jk time: assms(2))
  show "tpsL (Suc t) = (tpsL1 t)[j3 + 1 := (\<lfloor>i - t - 1\<rfloor>\<^sub>N, 1)]"
    unfolding tpsL1_def tpsL_def dum_def by (simp add: list_update_swap)
qed

lemma len_le: "nllength (nss ! t) \<le> nlllength nss" if "t < length nss" for t
  using that member_le_nlllength_1 by (meson diff_le_self le_trans nth_mem)

lemma dum_le: "nllength (dum t) \<le> nlllength nss" if "t \<le> length nss" for t
  using that len_le unfolding dum_def by (simp add: nllength_def numlist_Nil)

lemma tmL2' [transforms_intros]:
  assumes "t < i" and "ttt = 20 + 4 * nlllength nss + 2 * nlength i"
  shows "transforms tmL2 (tpsL t) ttt (tpsL (Suc t))"
proof -
  have t: "t < length nss"
    using assms(1) i by simp
  have "12 + 2 * nllength (dum t) + 2 * nllength (nss ! t) + (8 + 2 * nlength (i - t)) \<le> ttt"
    using assms(2) dum_le[of t] len_le[OF t] t nlength_mono[of "i - t" i] by simp
  then show ?thesis
    using tmL2[OF t] transforms_monotone by blast
qed

lemma read_tpsL: "read (tpsL t) ! (j3 + 1) \<noteq> \<box> \<longleftrightarrow> t < i"
proof -
  have "tpsL t ! (j3 + 1) = (\<lfloor>i - t\<rfloor>\<^sub>N, 1)" "j3 + 1 < length (tpsL t)"
    using jk unfolding tpsL_def by simp_all
  then show ?thesis
    using read_ncontents_eq_0 by (simp add: not_le)
qed

lemma tmL [transforms_intros]:
  assumes "ttt = i * (22 + 4 * nlllength nss + 2 * nlength i) + 1"
  shows "transforms tmL (tpsL 0) ttt (tpsL i)"
  unfolding tmL_def
proof (tform)
  show "read (tpsL t) ! (j3 + 1) \<noteq> \<box>" if "t < i" for t
    using that read_tpsL by simp
  show "\<not> read (tpsL i) ! (j3 + 1) \<noteq> \<box>"
    using read_tpsL by simp
  show "i * (20 + 4 * nlllength nss + 2 * nlength i + 2) + 1 \<le> ttt"
    using assms by simp
qed

definition "tps3 \<equiv> tps0
  [j1 := nlltape' nss (Suc i),
   j3 := (\<lfloor>nss ! i\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma tm3 [transforms_intros]:
  assumes "ttt = 27 + 3 * nlength i + i * (22 + 4 * nlllength nss + 2 * nlength i) +
    4 * nlllength nss"
  shows "transforms tm3 tps0 ttt tps3"
proof -
  let ?t = "14 + 3 * nlength i + (i * (22 + 4 * nlllength nss + 2 * nlength i) + 1) +
    (12 + 2 * nllength (dum i) + 2 * nllength (nss ! i))"
  have "transforms tm3 tps0 ?t tps3"
    unfolding tm3_def tm2_def
  proof (tform tps: i tpsL_def tps3_def jk)
    show "tps3 = (tpsL i)[j1 := nlltape' nss (Suc i), j3 := (\<lfloor>nss ! i\<rfloor>\<^sub>N\<^sub>L, 1)]"
      unfolding tps3_def tpsL_def using tps0 jk
      by (intro nth_equalityI) (auto simp: nth_list_update)
  qed
  moreover have "?t \<le> ttt"
    using assms dum_le[of i] len_le[OF i] i by simp
  ultimately show ?thesis
    using transforms_monotone by blast
qed

definition "tps4 \<equiv> tps0[j3 := (\<lfloor>nss ! i\<rfloor>\<^sub>N\<^sub>L, 1)]"

lemma tm4:
  assumes "ttt = 30 + 3 * nlength i + i * (22 + 4 * nlllength nss + 2 * nlength i) +
    5 * nlllength nss"
  shows "transforms tm4 tps0 ttt tps4"
proof -
  let ?t = "27 + 3 * nlength i + i * (22 + 4 * nlllength nss + 2 * nlength i) + 4 * nlllength nss +
    (tps3 :#: j1 + 2)"
  have "transforms tm4 tps0 ?t tps4"
    unfolding tm4_def
  proof (tform tps: tps3_def tps4_def jk)
    show "clean_tape (tps3 ! j1)"
      unfolding tps3_def using jk clean_tape_nllcontents by simp
    show "tps4 = tps3[j1 := tps3 ! j1 |#=| 1]"
      unfolding tps4_def tps3_def using tps0 jk
      by (intro nth_equalityI) (auto simp: nth_list_update)
  qed
  moreover have "tps3 :#: j1 \<le> Suc (nlllength nss)"
  proof -
    have "nlllength (take (Suc i) nss) \<le> nlllength nss"
      using nlllength[of "take (Suc i) nss"] nlllength[of nss]
        sum_list_append[of "map (\<lambda>ns. Suc (nllength ns)) (take (Suc i) nss)"
          "map (\<lambda>ns. Suc (nllength ns)) (drop (Suc i) nss)"]
      by (metis append_take_drop_id le_add1 map_append)
    then show ?thesis
      unfolding tps3_def using jk by simp
  qed
  ultimately show ?thesis
    using assms transforms_monotone[of tm4 tps0 ?t tps4 ttt] by simp
qed

end

end

lemma transforms_tm_nthlI [transforms_intros]:
  fixes j1 j2 j3 :: tapeidx
  fixes tps tps' :: "tape list" and ttt k i :: nat and nss :: "nat list list"
  assumes "0 < j1" "j1 \<noteq> j2" "j1 < j3" "j2 < j3" "j3 + 1 < k" "length tps = k"
    and "i < length nss"
  assumes
    "tps ! j1 = (\<lfloor>nss\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
    "tps ! j2 = (\<lfloor>i\<rfloor>\<^sub>N, 1)"
    "tps ! j3 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! (j3 + 1) = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 100 * (Suc (nlllength nss))\<^sup>2"
  assumes "tps' = tps[j3 := (\<lfloor>nss ! i\<rfloor>\<^sub>N\<^sub>L, 1)]"
  shows "transforms (tm_nthl j1 j2 j3) tps ttt tps'"
proof -
  interpret loc: turing_machine_nthl j1 j2 j3 .
  let ?l = "nlllength nss"
  let ?t = "30 + 3 * nlength i + i * (22 + 4 * ?l + 2 * nlength i) + 5 * ?l"
  have "transforms (tm_nthl j1 j2 j3) tps ?t tps'"
    using loc.tm4 loc.tm4_eq_tm_nthl loc.tps4_def assms by metis
  moreover have "?t \<le> ttt"
  proof -
    have il: "i \<le> ?l"
      using assms(7) length_le_nlllength by (meson le_trans less_imp_le)
    have ni: "nlength i \<le> ?l"
      using il nlength_le_n le_trans by blast
    have "i * (22 + 4 * ?l + 2 * nlength i) \<le> ?l * (22 + 6 * ?l)"
      using il ni by (intro mult_le_mono) auto
    then have "?t \<le> 30 + 3 * ?l + ?l * (22 + 6 * ?l) + 5 * ?l"
      using ni by simp
    also have "\<dots> \<le> 100 * (Suc ?l)\<^sup>2"
      by (simp add: power2_eq_square algebra_simps)
    finally show ?thesis
      using assms(12) by simp
  qed
  ultimately show ?thesis
    using transforms_monotone by blast
qed

end
