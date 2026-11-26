theory TM_VFields
  imports CoverWeave_Base.MWCCVC_Verifier_Spec CoverWeave_Base.TM_Helpers
begin

section \<open>The verifier, phase 0: reading the fields of the instance and of the certificate\<close>

text \<open>
The verifier works on 93 tapes. The instance \<open>nss\<close> is on tape 7 and the certificate
\<open>nssc\<close> on tape 11, both as lists of lists of numbers. Phase 0 extracts the header, the weights
and the edge list of the instance (tapes 14, 15, 16), the capacity \<open>k\<close> and the bound \<open>B\<close>
(tapes 17, 18), the number \<open>n\<close> of vertices (tape 19), the length of the edge list (tape 20), the
first list \<open>L\<^sub>0\<close> of the certificate (tape 21), its first two entries \<open>d\<close> and \<open>c\<^sub>0\<close>
(tapes 22, 23), and the flag \<open>2 \<le> |L\<^sub>0| \<and> c\<^sub>0 < n\<close> on tape 27, which serves as the flag
\<open>OK\<close> of all later phases. Missing list elements default as in @{const nth_or}.
\<close>

subsection \<open>Reading an element if there is one\<close>

definition tm_next_or :: "symbol \<Rightarrow> tapeidx \<Rightarrow> tapeidx \<Rightarrow> machine" where
  "tm_next_or z j1 j2 \<equiv> IF \<lambda>rs. rs ! j1 \<noteq> \<box> THEN tm_nextract z j1 j2 ELSE [] ENDIF"

lemma tm_next_or_tm:
  assumes "G \<ge> 6" and "z < 6" and "0 < j2" and "j2 < k" and "j1 < k" and "k \<ge> 2"
  shows "turing_machine k G (tm_next_or z j1 j2)"
  unfolding tm_next_or_def
  using assms tm_nextract_tm Nil_tm turing_machine_branch_turing_machine by simp

lemma nth_or_min: "nth_or d xs (min i (length xs)) = nth_or d xs i"
  unfolding nth_or_def by (simp add: min_def)

text \<open>The head position after reading one more element, kept opaque for the simplifier.\<close>

definition nxt :: "nat \<Rightarrow> nat \<Rightarrow> nat" where
  "nxt L i \<equiv> if i < L then Suc i else i"

lemma nxt_min: "nxt L (min i L) = min (i + 1) L"
  unfolding nxt_def by (simp add: min_def)

lemma nlength_nth_or_le: "nlength (nth_or 0 xs j) \<le> nllength xs"
  unfolding nth_or_def using member_le_nllength nlength_zero by simp

lemma nxt_0: "nxt L 0 = min 1 L"
  unfolding nxt_def by (simp add: min_def)

lemma transforms_tm_next_or_4I [transforms_intros]:
  fixes j1 j2 :: tapeidx and tps tps' :: "tape list" and k i ttt :: nat and ns :: "nat list"
  assumes "j1 < k" "j2 < k" "0 < j1" "0 < j2" "j1 \<noteq> j2" "length tps = k"
  assumes "tps ! j1 = nltape' ns i" "tps ! j2 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 14 + 2 * nllength ns"
  assumes "tps' = tps
    [j1 := nltape' ns (nxt (length ns) i),
     j2 := (\<lfloor>nth_or 0 ns i\<rfloor>\<^sub>N, 1)]"
  shows "transforms (tm_next_or \<bar> j1 j2) tps ttt tps'"
  unfolding tm_next_or_def
proof (rule transforms_branchI)
  have rd: "read tps ! j1 \<noteq> \<box> \<longleftrightarrow> i < length ns"
    using tapes_at_read'[of j1 tps] assms(1,6,7) nltape'_tape_read[of ns i] by (simp add: not_le)
  show "transforms (tm_nextract \<bar> j1 j2) tps (12 + 2 * nlength 0 + 2 * nlength (ns ! i)) tps'"
    if "read tps ! j1 \<noteq> \<box>"
  proof (rule transforms_tm_nextract_4I[where dummy=0, OF assms(1-6)])
    show "i < length ns"
      using that rd by simp
    show "tps' = tps[j1 := nltape' ns (Suc i), j2 := (\<lfloor>ns ! i\<rfloor>\<^sub>N, 1)]"
      using assms(10) that rd unfolding nth_or_def nxt_def by simp
  qed (use assms canrepr_0 in simp_all)
  show "transforms [] tps 0 tps" if "\<not> read tps ! j1 \<noteq> \<box>"
    using transforms_Nil .
  show "12 + 2 * nlength 0 + 2 * nlength (ns ! i) + 2 \<le> ttt" if "read tps ! j1 \<noteq> \<box>"
  proof -
    have "nlength (ns ! i) \<le> nllength ns"
      using that rd member_le_nllength by simp
    then show ?thesis
      using assms(9) nlength_zero by simp
  qed
  show "0 + 1 \<le> ttt" if "\<not> read tps ! j1 \<noteq> \<box>"
    using assms(9) by simp
  show "tps' = tps'" if "read tps ! j1 \<noteq> \<box>"
    by simp
  show "tps' = tps" if "\<not> read tps ! j1 \<noteq> \<box>"
  proof -
    have "\<not> i < length ns"
      using that rd by simp
    then have "tps' = tps[j1 := tps ! j1, j2 := tps ! j2]"
      using assms(7,8,10) unfolding nth_or_def nxt_def by simp
    then show ?thesis
      by simp
  qed
qed

lemma transforms_tm_next_or_5I [transforms_intros]:
  fixes j1 j2 :: tapeidx and tps tps' :: "tape list" and k i ttt :: nat and nss :: "nat list list"
  assumes "j1 < k" "j2 < k" "0 < j1" "0 < j2" "j1 \<noteq> j2" "length tps = k"
  assumes "tps ! j1 = nlltape' nss i" "tps ! j2 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
  assumes "ttt = 14 + 2 * nlllength nss"
  assumes "tps' = tps
    [j1 := nlltape' nss (nxt (length nss) i),
     j2 := (\<lfloor>nth_or [] nss i\<rfloor>\<^sub>N\<^sub>L, 1)]"
  shows "transforms (tm_next_or \<sharp> j1 j2) tps ttt tps'"
  unfolding tm_next_or_def
proof (rule transforms_branchI)
  have rd: "read tps ! j1 \<noteq> \<box> \<longleftrightarrow> i < length nss"
    using tapes_at_read'[of j1 tps] assms(1,6,7) nlltape'_tape_read[of nss i] by (simp add: not_le)
  show "transforms (tm_nextract \<sharp> j1 j2) tps (12 + 2 * nllength [] + 2 * nllength (nss ! i)) tps'"
    if "read tps ! j1 \<noteq> \<box>"
  proof (rule transforms_tm_nextract_5I[where dummy="[]", OF assms(1-6)])
    show "i < length nss"
      using that rd by simp
    show "tps' = tps[j1 := nlltape' nss (Suc i), j2 := (\<lfloor>nss ! i\<rfloor>\<^sub>N\<^sub>L, 1)]"
      using assms(10) that rd unfolding nth_or_def nxt_def by simp
  qed (use assms nllength_Nil in simp_all)
  show "transforms [] tps 0 tps" if "\<not> read tps ! j1 \<noteq> \<box>"
    using transforms_Nil .
  show "12 + 2 * nllength [] + 2 * nllength (nss ! i) + 2 \<le> ttt" if "read tps ! j1 \<noteq> \<box>"
  proof -
    have "nllength (nss ! i) \<le> nlllength nss"
      using that rd member_le_nlllength_1[of "nss ! i" nss] by simp
    then show ?thesis
      using assms(9) by simp
  qed
  show "0 + 1 \<le> ttt" if "\<not> read tps ! j1 \<noteq> \<box>"
    using assms(9) by simp
  show "tps' = tps'" if "read tps ! j1 \<noteq> \<box>"
    by simp
  show "tps' = tps" if "\<not> read tps ! j1 \<noteq> \<box>"
  proof -
    have "\<not> i < length nss"
      using that rd by simp
    then have "tps' = tps[j1 := tps ! j1, j2 := tps ! j2]"
      using assms(7,8,10) unfolding nth_or_def nxt_def by simp
    then show ?thesis
      by simp
  qed
qed


text \<open>The same machine at the start of a list, where the head stands on the first cell.\<close>

definition tm_first_or :: "symbol \<Rightarrow> tapeidx \<Rightarrow> tapeidx \<Rightarrow> machine" where
  "tm_first_or \<equiv> tm_next_or"

lemma tm_first_or_tm:
  assumes "G \<ge> 6" and "z < 6" and "0 < j2" and "j2 < k" and "j1 < k" and "k \<ge> 2"
  shows "turing_machine k G (tm_first_or z j1 j2)"
  unfolding tm_first_or_def using assms tm_next_or_tm by simp

lemma transforms_tm_first_or_4I [transforms_intros]:
  fixes j1 j2 :: tapeidx and tps tps' :: "tape list" and k ttt :: nat and ns :: "nat list"
  assumes "j1 < k" "j2 < k" "0 < j1" "0 < j2" "j1 \<noteq> j2" "length tps = k"
  assumes "tps ! j1 = (\<lfloor>ns\<rfloor>\<^sub>N\<^sub>L, 1)" "tps ! j2 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
  assumes "ttt = 14 + 2 * nllength ns"
  assumes "tps' = tps
    [j1 := nltape' ns (nxt (length ns) 0),
     j2 := (\<lfloor>nth_or 0 ns 0\<rfloor>\<^sub>N, 1)]"
  shows "transforms (tm_first_or \<bar> j1 j2) tps ttt tps'"
  unfolding tm_first_or_def
  by (rule transforms_tm_next_or_4I[where i=0]) (use assms in simp_all)

lemma transforms_tm_first_or_5I [transforms_intros]:
  fixes j1 j2 :: tapeidx and tps tps' :: "tape list" and k ttt :: nat and nss :: "nat list list"
  assumes "j1 < k" "j2 < k" "0 < j1" "0 < j2" "j1 \<noteq> j2" "length tps = k"
  assumes "tps ! j1 = (\<lfloor>nss\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)" "tps ! j2 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
  assumes "ttt = 14 + 2 * nlllength nss"
  assumes "tps' = tps
    [j1 := nlltape' nss (nxt (length nss) 0),
     j2 := (\<lfloor>nth_or [] nss 0\<rfloor>\<^sub>N\<^sub>L, 1)]"
  shows "transforms (tm_first_or \<sharp> j1 j2) tps ttt tps'"
  unfolding tm_first_or_def
  by (rule transforms_tm_next_or_5I[where i=0]) (use assms in simp_all)

subsection \<open>Phase 0\<close>

definition tm_fields :: machine where
  "tm_fields \<equiv>
    tm_first_or \<sharp> 7 14 ;;
    tm_next_or \<sharp> 7 15 ;;
    tm_next_or \<sharp> 7 16 ;;
    tm_first_or \<bar> 14 17 ;;
    tm_next_or \<bar> 14 18 ;;
    tm_count 15 19 \<bar> ;;
    tm_count 16 20 \<bar> ;;
    tm_first_or \<sharp> 11 21 ;;
    tm_count 21 25 \<bar> ;;
    tm_setn 26 1 ;;
    tm_lt 26 25 27 ;;
    tm_first_or \<bar> 21 22 ;;
    tm_next_or \<bar> 21 23 ;;
    tm_lt 23 19 30 ;;
    tm_and 27 30"

lemma tm_fields_tm:
  assumes "92 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_fields"
  unfolding tm_fields_def
  using assms tm_first_or_tm tm_next_or_tm tm_count_tm tm_setn_tm tm_lt_tm tm_and_tm
  by simp

locale turing_machine_fields
begin

context
  fixes tps0 :: "tape list" and nss nssc :: "nat list list"
  assumes k: "length tps0 = 93"
  assumes tps0:
    "tps0 ! 7 = (\<lfloor>nss\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
    "tps0 ! 11 = (\<lfloor>nssc\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
    "tps0 ! 14 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 15 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 16 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 17 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 18 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 19 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 20 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 21 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps0 ! 22 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 23 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 25 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 26 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 27 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 28 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 29 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 30 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 31 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps0 ! 32 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
begin

abbreviation "hdr \<equiv> nth_or [] nss 0"
abbreviation "wts \<equiv> nth_or [] nss 1"
abbreviation "es \<equiv> nth_or [] nss 2"
abbreviation "L0 \<equiv> nth_or [] nssc 0"
abbreviation "c0 \<equiv> nth_or 0 L0 1"

definition "tpsV \<equiv> tps0
  [7 := nlltape' nss (min 3 (length nss)),
   14 := nltape' hdr (min 2 (length hdr)),
   15 := (\<lfloor>wts\<rfloor>\<^sub>N\<^sub>L, 1),
   16 := (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1),
   17 := (\<lfloor>nth_or 0 hdr 0\<rfloor>\<^sub>N, 1),
   18 := (\<lfloor>nth_or 0 hdr 1\<rfloor>\<^sub>N, 1),
   19 := (\<lfloor>length wts\<rfloor>\<^sub>N, 1),
   20 := (\<lfloor>length es\<rfloor>\<^sub>N, 1),
   11 := nlltape' nssc (min 1 (length nssc)),
   21 := nltape' L0 (min 2 (length L0)),
   25 := (\<lfloor>length L0\<rfloor>\<^sub>N, 1),
   26 := (\<lfloor>1\<rfloor>\<^sub>N, 1),
   27 := (\<lfloor>1 < length L0 \<and> c0 < length wts\<rfloor>\<^sub>B, 1),
   22 := (\<lfloor>nth_or 0 L0 0\<rfloor>\<^sub>N, 1),
   23 := (\<lfloor>c0\<rfloor>\<^sub>N, 1),
   30 := (\<lfloor>c0 < length wts\<rfloor>\<^sub>B, 1)]"

abbreviation "\<sigma> \<equiv> nlllength nss + nlllength nssc + 1"

lemma field_size_j:
  "nllength (nth_or [] nss j) \<le> \<sigma>" "nllength (nth_or [] nss j) ^ 2 \<le> \<sigma> ^ 2"
proof -
  show 1: "nllength (nth_or [] nss j) \<le> \<sigma>"
    using nllength_nth_or_le[of nss j] by simp
  show "nllength (nth_or [] nss j) ^ 2 \<le> \<sigma> ^ 2"
    using 1 by (simp add: power_mono)
qed

lemma field_sizes:
  "nllength L0 \<le> \<sigma>" "nllength L0 ^ 2 \<le> \<sigma> ^ 2"
  "nlllength nss \<le> \<sigma>" "nlllength nssc \<le> \<sigma>" "1 \<le> \<sigma>" "\<sigma> \<le> \<sigma> ^ 2"
proof -
  show 2: "nllength L0 \<le> \<sigma>"
    using nllength_nth_or_le[of nssc 0] by simp
  show "nllength L0 ^ 2 \<le> \<sigma> ^ 2"
    using 2 by (simp add: power_mono)
  show "nlllength nss \<le> \<sigma>" "nlllength nssc \<le> \<sigma>" "1 \<le> \<sigma>"
    by simp_all
  show "\<sigma> \<le> \<sigma> ^ 2"
    by (simp add: power2_eq_square)
qed

lemma lt_times:
  "100 * Suc (min (Suc 0) (length L0)) * Suc (nlength (Suc 0) + nlength (length L0)) \<le> 600 * \<sigma>"
  "100 * Suc (min c0 (length wts)) * Suc (nlength c0 + nlength (length wts)) \<le> 600 * \<sigma> ^ 2"
proof -
  have L: "nlength (length L0) \<le> \<sigma>"
    using nlength_le_n[of "length L0"] length_le_nllength[of L0] field_sizes(1) by linarith
  have "100 * Suc (min (Suc 0) (length L0)) * Suc (nlength (Suc 0) + nlength (length L0)) \<le>
      100 * 2 * (2 + \<sigma>)"
    using L nlength_Suc0 by (intro mult_le_mono) simp_all
  then show "100 * Suc (min (Suc 0) (length L0)) * Suc (nlength (Suc 0) + nlength (length L0)) \<le> 600 * \<sigma>"
    by simp
  have c: "nlength c0 \<le> \<sigma>"
    using nlength_nth_or_le[of L0 1] field_sizes(1) by linarith
  have w: "length wts \<le> \<sigma>" "nlength (length wts) \<le> \<sigma>"
    using nlength_le_n[of "length wts"] length_le_nllength[of wts] field_size_j(1)[of 1] by linarith+
  have "100 * Suc (min c0 (length wts)) * Suc (nlength c0 + nlength (length wts)) \<le>
      100 * (2 * \<sigma>) * (3 * \<sigma>)"
    using c w by (intro mult_le_mono) simp_all
  also have "\<dots> = 600 * \<sigma> ^ 2"
    by (simp add: power2_eq_square algebra_simps)
  finally show "100 * Suc (min c0 (length wts)) * Suc (nlength c0 + nlength (length wts)) \<le> 600 * \<sigma> ^ 2" .
qed

lemma tm_fields:
  shows "transforms tm_fields tps0 (2000 * \<sigma> ^ 2) tpsV"
  unfolding tm_fields_def
  apply (rule transforms_monotone)
   apply (tform tps: tps0 k)
   apply (tps_eq rules: tpsV_def k tps0 nxt_0 nxt_min nth_or_min numeral_2_eq_2 numeral_3_eq_3)
  apply (simp only: nxt_0 nxt_min nth_or_min one_add_one)
  by (lin facts: field_size_j[of 0] field_size_j[of 1] field_size_j[of 2] field_sizes lt_times
    nlength_1_simp nlength_Suc0)

end

end

end
