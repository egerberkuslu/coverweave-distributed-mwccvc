theory TM_Verify
  imports TM_VCert CoverWeave_Base.MWCCVC_NP_Assembly
begin

section \<open>The verifier machine for MWCCVC\<close>

text \<open>
The verifier decodes the pair \<open>\<langle>x, u\<rangle>\<close> exactly as Cook_Levin's verifier for \<open>SAT\<close> does
(@{const tm_verify_sat}): it checks that \<open>x\<close> encodes a list of lists of numbers, strips the
padding symbols \<open>\<bar>\<close> from the certificate and checks that the rest encodes a list of lists of
numbers. Then it runs the certificate check and copies its flag to the output tape. The
machine computes @{const verify_mw}.
\<close>

definition "tm_vD \<equiv>
  tm_bindecode 4 11 ;; tm_rstrip \<bar> 11 ;; tm_numlistlist_wf 11 12 ;;
  IF \<lambda>rs. rs ! 12 \<noteq> \<box> THEN tm_cert ;; tm_copyn 27 1 ELSE [] ENDIF"

definition "tm_vC \<equiv> tm_proper_symbols_lt 4 10 4 ;; IF \<lambda>rs. rs ! 10 \<noteq> \<box> THEN tm_vD ELSE [] ENDIF"

definition "tm_vB \<equiv> tm_bindecode 3 7 ;; tm_numlistlist_wf 7 8 ;; IF \<lambda>rs. rs ! 8 \<noteq> \<box> THEN tm_vC ELSE [] ENDIF"

definition "tm_rm93 \<equiv> tm_right_many {0..<93}"

definition "tm_vA \<equiv>
  tm_rm93 ;;
  tm_bindecode 0 2 ;;
  tm_unpair 2 3 4 ;;
  tm_even_length 3 5 ;;
  tm_proper_symbols_lt 3 6 4 ;;
  tm_and 6 5"

definition tm_verify :: machine where
  "tm_verify \<equiv> tm_vA ;; IF \<lambda>rs. rs ! 6 \<noteq> \<box> THEN tm_vB ELSE [] ENDIF"

lemma tm_verify_tm: "turing_machine 93 6 tm_verify"
  unfolding tm_verify_def tm_vA_def tm_vB_def tm_vC_def tm_vD_def tm_rm93_def
  using tm_right_many_tm tm_bindecode_tm tm_unpair_tm tm_even_length_tm tm_proper_symbols_lt_tm tm_and_tm
    tm_numlistlist_wf_tm tm_rstrip_tm tm_cert_tm tm_copyn_tm Nil_tm turing_machine_branch_turing_machine
  by simp

lemma proper_rstrip: "proper_symbols zs \<Longrightarrow> proper_symbols (rstrip z zs)"
  unfolding rstrip_def by simp

lemma map_upt_nth': "map f xs = map (\<lambda>i. f (xs ! i)) [0..<length xs]"
proof -
  have "map f xs = map f (map ((!) xs) [0..<length xs])"
    by (simp only: List.map_nth)
  also have "\<dots> = map (\<lambda>i. f (xs ! i)) [0..<length xs]"
    by (simp only: map_map comp_def)
  finally show ?thesis .
qed

definition "TVB m \<equiv> 4000000 * (2 * m + 1) ^ 6 + 200 * m + 1000"

lemma bit_iff_lt4: "proper_symbols_lt 4 zs = bit_symbols zs"
  by fastforce

locale turing_machine_verify
begin

context
  fixes tps0 :: "tape list" and zs :: "symbol list"
  assumes zs: "bit_symbols zs"
  assumes tps0: "tps0 = snd (start_config 93 zs)"
begin

definition "tps1 \<equiv> map (\<lambda>tp. tp |#=| 1) tps0"

lemma tps1:
  "tps1 ! 0 = (\<lfloor>zs\<rfloor>, 1)"
  "0 < j \<Longrightarrow> j < 93 \<Longrightarrow> tps1 ! j = (\<lfloor>[]\<rfloor>, 1)"
  "length tps1 = 93"
  using tps0 start_config_def tps1_def by auto

abbreviation "ys \<equiv> bindecode zs"
abbreviation "f \<equiv> first ys"
abbreviation "sc \<equiv> second ys"
abbreviation "xs \<equiv> bindecode f"
abbreviation "vs \<equiv> rstrip \<bar> (bindecode sc)"
abbreviation "c1 \<equiv> proper_symbols_lt 4 f \<and> even (length f)"
abbreviation "c2 \<equiv> numlistlist_wf xs"
abbreviation "c3 \<equiv> proper_symbols_lt 4 sc"
abbreviation "c4 \<equiv> numlistlist_wf vs"

lemma pf: "proper_symbols ys" "proper_symbols f" "proper_symbols sc"
  using proper_bindecode first_def second_def by simp_all

definition "tps6 \<equiv> tps1
  [2 := (\<lfloor>ys\<rfloor>, 1),
   3 := (\<lfloor>f\<rfloor>, 1),
   4 := (\<lfloor>sc\<rfloor>, 1),
   5 := (\<lfloor>even (length f)\<rfloor>\<^sub>B, 1),
   6 := (\<lfloor>c1\<rfloor>\<^sub>B, 1)]"

lemma tm_rm93 [transforms_intros]: "transforms tm_rm93 tps0 1 tps1"
  unfolding tm_rm93_def
proof (rule transforms_tm_right_manyI)
  have "length tps0 = 93"
    using tps0 start_config_def by simp
  then have "map (\<lambda>j. if j \<in> {0..<93} then tps0 ! j |+| 1 else tps0 ! j) [0..<length tps0] =
      map (\<lambda>j. tps0 ! j |#=| 1) [0..<length tps0]"
    using tps0 start_config_pos by simp
  also have "\<dots> = tps1"
    using tps1_def map_upt_nth'[of "\<lambda>tp. tp |#=| 1" tps0] by simp
  finally show "tps1 = map (\<lambda>j. if j \<in> {0..<93} then tps0 ! j |+| 1 else tps0 ! j) [0..<length tps0]"
    by simp
qed simp

lemma tm_vA:
  "transforms tm_vA tps0 (1 + (7 + 3 * length zs) + (6 * length ys + 13) + (7 * length f + 7) +
     (5 + 7 * length f) + 3) tps6"
  unfolding tm_vA_def
  apply (tform tps: zs tps1 pf canrepr_0)
  by (tps_eq rules: tps6_def tps1 pf)

abbreviation "nss \<equiv> THE nss. numlistlist nss = xs"
abbreviation "nssc \<equiv> THE nss. numlistlist nss = vs"

lemma lens: "length ys \<le> length zs" "length f \<le> length zs" "length sc \<le> length zs"
  "length xs \<le> length zs" "length (bindecode sc) \<le> length zs" "length vs \<le> length zs"
proof -
  show 1: "length ys \<le> length zs"
    by simp
  show 2: "length f \<le> length zs"
    using 1 length_first le_trans by blast
  show 3: "length sc \<le> length zs"
    using 1 length_second le_trans by blast
  show "length xs \<le> length zs"
    using 2 by simp
  show 4: "length (bindecode sc) \<le> length zs"
    using 3 by simp
  show "length vs \<le> length zs"
    using 4 length_rstrip_le le_trans by blast
qed

lemma the_nll': "numlistlist_wf ws \<Longrightarrow> numlistlist (THE nss. numlistlist nss = ws) = ws"
  using numlistlist_wf_def numlistlist_inj by (metis (mono_tags, lifting) theI)

definition "tB \<equiv> tps6[7 := (\<lfloor>xs\<rfloor>, 1), 8 := (\<lfloor>c2\<rfloor>\<^sub>B, 1)]"
definition "tC \<equiv> tB[10 := (\<lfloor>c3\<rfloor>\<^sub>B, 1)]"
definition "tD \<equiv> tC[11 := (\<lfloor>vs\<rfloor>, 1), 12 := (\<lfloor>c4\<rfloor>\<^sub>B, 1)]"

lemma lenD: "length tps6 = 93" "length tB = 93" "length tC = 93" "length tD = 93"
  using tps1 by (simp_all add: tps6_def tB_def tC_def tD_def)

lemma tB1:
  assumes c1
  shows "transforms (tm_bindecode 3 7 ;; tm_numlistlist_wf 7 8) tps6 (7 + 3 * length f + (206 + 39 * length xs)) tB"
proof -
  have bs: "bit_symbols f"
    using assms bit_iff_lt4 by simp
  show ?thesis
    apply (tform tps: tps6_def tps1 bs proper_bindecode canrepr_0)
    by (tps_eq rules: tB_def tps6_def tps1)
qed

lemma tC1:
  "transforms (tm_proper_symbols_lt 4 10 4) tB (5 + 7 * length sc) tC"
  apply (tform tps: tB_def tps6_def tps1 pf)
  by (tps_eq rules: tC_def tB_def tps6_def tps1)

lemma tD1:
  assumes c3
  shows "transforms (tm_bindecode 4 11 ;; tm_rstrip \<bar> 11 ;; tm_numlistlist_wf 11 12) tC
    (7 + 3 * length sc + (3 * length (bindecode sc) + 5) + (206 + 39 * length vs)) tD"
proof -
  have bs: "bit_symbols sc"
    using assms bit_iff_lt4 by simp
  have pv: "proper_symbols vs"
    using proper_rstrip proper_bindecode by simp
  have l: "length tC = 93"
    using tps1 by (simp add: tC_def tB_def tps6_def)
  have c11: "tC ! 11 = (\<lfloor>[]\<rfloor>, 1)" "tC ! 4 = (\<lfloor>sc\<rfloor>, 1)" "tC ! 12 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tC ! 13 = (\<lfloor>[]\<rfloor>, 1)" "tC ! 12 = (\<lfloor>[]\<rfloor>, 1)"
    using tps1 canrepr_0 by (simp_all add: tC_def tB_def tps6_def)
  have 1: "transforms (tm_bindecode 4 11) tC (7 + 3 * length sc) (tC[11 := (\<lfloor>bindecode sc\<rfloor>, 1)])"
    by (rule transforms_tm_bindecodeI) (use l c11 bs in simp_all)
  have 2: "transforms (tm_rstrip \<bar> 11) (tC[11 := (\<lfloor>bindecode sc\<rfloor>, 1)]) (3 * length (bindecode sc) + 5)
      (tC[11 := (\<lfloor>vs\<rfloor>, 1)])"
    by (rule transforms_tm_rstripI[where zs="bindecode sc"]) (use l proper_bindecode in simp_all)
  have 3: "transforms (tm_numlistlist_wf 11 12) (tC[11 := (\<lfloor>vs\<rfloor>, 1)]) (206 + 39 * length vs) tD"
    by (rule transforms_tm_numlistlist_wfI[where zs=vs]) (use l c11 pv in \<open>simp_all add: tD_def\<close>)
  show ?thesis
    using transforms_tm_sequentialI[OF transforms_tm_sequentialI[OF 1 2 refl] 3 refl] by simp
qed

lemma read_flag: "length tps = 93 \<Longrightarrow> j < 93 \<Longrightarrow> tps ! j = (\<lfloor>P\<rfloor>\<^sub>B, 1) \<Longrightarrow> read tps ! j \<noteq> \<box> \<longleftrightarrow> P"
  using read_ncontents_eq_0[of tps j] by simp

lemmas ifT6 = ifT[where cond="\<lambda>rs. rs ! 6 \<noteq> \<box>" and ?M2.0="[]"]
lemmas ifF6 = ifF[where cond="\<lambda>rs. rs ! 6 \<noteq> \<box>"]
lemmas ifT8 = ifT[where cond="\<lambda>rs. rs ! 8 \<noteq> \<box>" and ?M2.0="[]"]
lemmas ifF8 = ifF[where cond="\<lambda>rs. rs ! 8 \<noteq> \<box>"]
lemmas ifT10 = ifT[where cond="\<lambda>rs. rs ! 10 \<noteq> \<box>" and ?M2.0="[]"]
lemmas ifF10 = ifF[where cond="\<lambda>rs. rs ! 10 \<noteq> \<box>"]
lemmas ifT12 = ifT[where cond="\<lambda>rs. rs ! 12 \<noteq> \<box>" and ?M2.0="[]"]
lemmas ifF12 = ifF[where cond="\<lambda>rs. rs ! 12 \<noteq> \<box>"]

lemma tm_verify_main:
  "\<exists>tps'. tps' ::: 1 = \<lfloor>verify_mw zs\<rfloor> \<and> transforms tm_verify tps0 (TVB (length zs)) tps'"
proof -
  let ?n = "length zs"
  let ?TA = "1 + (7 + 3 * length zs) + (6 * length ys + 13) + (7 * length f + 7) + (5 + 7 * length f) + 3"
  have TA: "?TA \<le> 40 + 23 * ?n"
    using lens by simp
  have v: "verify_mw zs = (if even (length f) \<and> bit_symbols f \<and> c2 \<and> bit_symbols sc \<and> c4 \<and>
      cert_ok nss nssc then [\<one>] else [])"
    unfolding verify_mw_def Let_def by simp
  have t1: "tps6 ! 1 = (\<lfloor>[]\<rfloor>, 1)" "tB ! 1 = (\<lfloor>[]\<rfloor>, 1)" "tC ! 1 = (\<lfloor>[]\<rfloor>, 1)" "tD ! 1 = (\<lfloor>[]\<rfloor>, 1)"
    using tps1 by (simp_all add: tps6_def tB_def tC_def tD_def)
  have p6: "TVB ?n \<ge> 200 * ?n + 1000"
    unfolding TVB_def by simp
  have v6: "tps6 ! 6 = (\<lfloor>c1\<rfloor>\<^sub>B, 1)"
    using tps1 by (simp add: tps6_def)
  have r6: "read tps6 ! 6 \<noteq> \<box> \<longleftrightarrow> c1"
    using read_flag[OF lenD(1), of 6 c1] v6 by simp
  have rB: "read tB ! 8 \<noteq> \<box> \<longleftrightarrow> c2"
    using read_flag[OF lenD(2), of 8 c2] by (simp add: tB_def lenD)
  have rC: "read tC ! 10 \<noteq> \<box> \<longleftrightarrow> c3"
    using read_flag[OF lenD(3), of 10 c3] by (simp add: tC_def lenD)
  have rD: "read tD ! 12 \<noteq> \<box> \<longleftrightarrow> c4"
    using read_flag[OF lenD(4), of 12 c4] by (simp add: tD_def lenD)
  let ?TB = "7 + 3 * length f + (206 + 39 * length xs)"
  let ?TC = "5 + 7 * length sc"
  let ?TD = "7 + 3 * length sc + (3 * length (bindecode sc) + 5) + (206 + 39 * length vs)"
  show ?thesis
  proof (cases c1)
    case False
    then have r: "\<not> read tps6 ! 6 \<noteq> \<box>"
      using r6 by simp
    have "transforms tm_verify tps0 (TVB ?n) tps6"
      unfolding tm_verify_def
      by (rule transforms_monotone[OF transforms_tm_sequentialI[OF tm_vA ifF6[OF r] refl]])
        (use TA p6 in linarith)
    moreover have "tps6 ::: 1 = \<lfloor>verify_mw zs\<rfloor>"
      using t1 v False bit_iff_lt4 by auto
    ultimately show ?thesis
      by blast
  next
    case c1: True
    then have r6': "read tps6 ! 6 \<noteq> \<box>"
      using r6 by simp
    show ?thesis
    proof (cases c2)
      case False
      then have rB': "\<not> read tB ! 8 \<noteq> \<box>"
        using rB by simp
      have "transforms tm_verify tps0 (TVB ?n) tB"
        unfolding tm_verify_def tm_vB_def
        by (rule transforms_monotone[OF transforms_tm_sequentialI[OF tm_vA ifT6[OF r6'
          transforms_tm_sequentialI[OF tB1[OF c1] ifF8[OF rB'] refl]] refl]])
          (use TA p6 lens in linarith)
      moreover have "tB ::: 1 = \<lfloor>verify_mw zs\<rfloor>"
        using t1 v False by auto
      ultimately show ?thesis
        by blast
    next
      case c2: True
      then have rB': "read tB ! 8 \<noteq> \<box>"
        using rB by simp
      show ?thesis
      proof (cases c3)
        case False
        then have rC': "\<not> read tC ! 10 \<noteq> \<box>"
          using rC by simp
        have "transforms tm_verify tps0 (TVB ?n) tC"
          unfolding tm_verify_def tm_vB_def tm_vC_def
          by (rule transforms_monotone[OF transforms_tm_sequentialI[OF tm_vA ifT6[OF r6'
            transforms_tm_sequentialI[OF tB1[OF c1] ifT8[OF rB' transforms_tm_sequentialI[OF tC1
            ifF10[OF rC'] refl]] refl]] refl]])
            (use TA p6 lens in linarith)
        moreover have "tC ::: 1 = \<lfloor>verify_mw zs\<rfloor>"
          using t1 v False bit_iff_lt4 by auto
        ultimately show ?thesis
          by blast
      next
        case c3: True
        then have rC': "read tC ! 10 \<noteq> \<box>"
          using rC by simp
        show ?thesis
        proof (cases c4)
          case False
          then have rD': "\<not> read tD ! 12 \<noteq> \<box>"
            using rD by simp
          have "transforms tm_verify tps0 (TVB ?n) tD"
            unfolding tm_verify_def tm_vB_def tm_vC_def tm_vD_def
            by (rule transforms_monotone[OF transforms_tm_sequentialI[OF tm_vA ifT6[OF r6'
              transforms_tm_sequentialI[OF tB1[OF c1] ifT8[OF rB' transforms_tm_sequentialI[OF tC1
              ifT10[OF rC' transforms_tm_sequentialI[OF tD1[OF c3] ifF12[OF rD'] refl]] refl]] refl]] refl]])
              (use TA p6 lens in linarith)
          moreover have "tD ::: 1 = \<lfloor>verify_mw zs\<rfloor>"
            using t1 v False by auto
          ultimately show ?thesis
            by blast
        next
          case c4: True
          then have rD': "read tD ! 12 \<noteq> \<box>"
            using rD by simp
          have x7: "tD ! 7 = (\<lfloor>nss\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)" "tD ! 11 = (\<lfloor>nssc\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
            using the_nll'[OF c2] the_nll'[OF c4] tps1
            by (simp_all add: tD_def tC_def tB_def tps6_def nllcontents_def)
          have bl: "tD ! j = (\<lfloor>[]\<rfloor>, 1)" if "14 \<le> j" "j < 93" for j
            using that tps1 by (simp add: tD_def tC_def tB_def tps6_def)
          obtain tps' where tps': "length tps' = 93" "tps' ! 1 = tD ! 1"
              "tps' ! 27 = (\<lfloor>cert_ok nss nssc\<rfloor>\<^sub>B, 1)"
              "transforms tm_cert tD (4000000 * sg nss nssc ^ 6) tps'"
            using tm_cert[OF lenD(4) x7 bl] by blast
          define tF where "tF = tps'[1 := (\<lfloor>cert_ok nss nssc\<rfloor>\<^sub>B, 1)]"
          let ?TF = "14 + 3 * (nlength (if cert_ok nss nssc then 1 else 0) + nlength 0)"
          have cp: "transforms (tm_copyn 27 1) tps' ?TF tF"
            by (rule transforms_tm_copynI) (use tps' t1 canrepr_0 tF_def in simp_all)
          have sgb: "sg nss nssc ^ 6 \<le> (2 * ?n + 1) ^ 6"
          proof -
            have "sg nss nssc = length xs + length vs + 1"
              unfolding sg_def using the_nll'[OF c2] the_nll'[OF c4] by (simp add: nlllength_def)
            then have "sg nss nssc \<le> 2 * ?n + 1"
              using lens by simp
            then show ?thesis
              by (rule power_mono) simp
          qed
          have sgb': "4000000 * sg nss nssc ^ 6 \<le> 4000000 * (2 * ?n + 1) ^ 6"
            using sgb by (rule mult_le_mono2)
          have tf: "?TF \<le> 20"
            using nlength_1_simp by simp
          have "transforms tm_verify tps0 (TVB ?n) tF"
            unfolding tm_verify_def tm_vB_def tm_vC_def tm_vD_def
            by (rule transforms_monotone[OF transforms_tm_sequentialI[OF tm_vA ifT6[OF r6'
              transforms_tm_sequentialI[OF tB1[OF c1] ifT8[OF rB' transforms_tm_sequentialI[OF tC1
              ifT10[OF rC' transforms_tm_sequentialI[OF tD1[OF c3] ifT12[OF rD'
              transforms_tm_sequentialI[OF tps'(4) cp refl]] refl]] refl]] refl]] refl]])
              (use TA lens sgb' tf in \<open>unfold TVB_def, linarith\<close>)
          moreover have "tF ::: 1 = \<lfloor>verify_mw zs\<rfloor>"
            using v c1 c2 c3 c4 bit_iff_lt4 tps'(1) canrepr_0 canrepr_1 unfolding tF_def by auto
          ultimately show ?thesis
            by blast
        qed
      qed
    qed
  qed
qed

end

end

section \<open>MWCCVC is in NP\<close>

lemma big_oh_poly_TVB: "big_oh_poly TVB"
proof (rule big_oh_polyI[of 0 _ 2916001200 6])
  fix n :: nat
  assume "0 < n"
  then have "2 * n + 1 \<le> 3 * n" and n1: "1 \<le> n"
    by simp_all
  then have "(2 * n + 1) ^ 6 \<le> (3 * n) ^ 6"
    by (intro power_mono) simp_all
  then have a: "4000000 * (2 * n + 1) ^ 6 \<le> 2916000000 * n ^ 6"
    by (simp add: power_mult_distrib)
  have "n \<le> n ^ 6" "1 \<le> n ^ 6"
    using n1 by (simp_all add: self_le_power)
  then have "200 * n + 1000 \<le> 1200 * n ^ 6"
    by linarith
  moreover have "TVB n = 4000000 * (2 * n + 1) ^ 6 + 200 * n + 1000"
    by (simp only: TVB_def)
  ultimately show "TVB n \<le> 2916001200 * n ^ 6"
    using a by linarith
qed

lemma computes_in_time_tm_verify:
  "computes_in_time 93 tm_verify (\<lambda>z. symbols_to_string (verify_mw (string_to_symbols z)))
     TVB"
proof
  fix x :: string
  let ?zs = "string_to_symbols x"
  let ?f = "\<lambda>z. symbols_to_string (verify_mw (string_to_symbols z))"
  have bs: "bit_symbols ?zs"
    by simp
  have "bit_symbols (verify_mw ?zs)"
    unfolding verify_mw_def Let_def by simp
  then have *: "string_to_symbols (?f x) = verify_mw ?zs"
    using bit_symbols_to_symbols by simp
  obtain tps where tps: "tps ::: 1 = \<lfloor>verify_mw ?zs\<rfloor>"
      "transforms tm_verify (snd (start_config 93 ?zs)) (TVB (length ?zs)) tps"
    using turing_machine_verify.tm_verify_main[OF bs refl] by blast
  have "tps ::: 1 = string_to_contents (?f x)"
    unfolding contents_string_to_contents * using tps(1) .
  then show "\<exists>tps. tps ::: 1 = string_to_contents (?f x) \<and>
      transforms tm_verify (snd (start_config_string 93 x)) (TVB (length x)) tps"
    using tps(2) by auto
qed

text \<open>
Membership of decision MWCCVC (Definition def:mwccvc of the manuscript with the bound \<open>B\<close> of
the decision version) in NP: the 93-tape machine @{const tm_verify} checks a certificate
\<open>\<langle>x, u\<rangle>\<close> in time \<open>O(|\<langle>x,u\<rangle>|^6)\<close>. Connectivity of the input graph is not required, so
the language is the general one; see @{theory CoverWeave_Base.MWCCVC_Language}.
\<close>

theorem MWCCVC_in_NP: "MWCCVC \<in> \<N>\<P>"
  using MWCCVC_in_NP_from_TM[OF tm_verify_tm big_oh_poly_TVB computes_in_time_tm_verify] .

end
