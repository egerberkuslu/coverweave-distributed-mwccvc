theory TM_VCert
  imports TM_VOwners
begin

section \<open>The certificate check\<close>

text \<open>
The certificate check runs phase 0 and then, as long as the flag on tape 27 stays set, the
phases 1 to 4. At the end the flag on tape 27 is @{const cert_ok}.
\<close>

definition "tm_c3 \<equiv> tm_loads ;; IF \<lambda>rs. rs ! 27 \<noteq> \<box> THEN tm_owners ELSE [] ENDIF"
definition "tm_c2 \<equiv> tm_weights ;; IF \<lambda>rs. rs ! 27 \<noteq> \<box> THEN tm_c3 ELSE [] ENDIF"
definition "tm_c1 \<equiv> tm_grow ;; IF \<lambda>rs. rs ! 27 \<noteq> \<box> THEN tm_c2 ELSE [] ENDIF"
definition "tm_cert \<equiv> tm_fields ;; IF \<lambda>rs. rs ! 27 \<noteq> \<box> THEN tm_c1 ELSE [] ENDIF"

lemma tm_cert_tm:
  assumes "92 < k" and "G \<ge> 6"
  shows "turing_machine k G tm_cert"
  unfolding tm_cert_def tm_c1_def tm_c2_def tm_c3_def
  using assms tm_fields_tm tm_grow_tm tm_weights_tm tm_loads_tm tm_owners_tm Nil_tm
    turing_machine_branch_turing_machine
  by simp

lemma ifT:
  assumes "cond (read tps)" "transforms M1 tps t tps'"
  shows "transforms (IF cond THEN M1 ELSE M2 ENDIF) tps (t + 2) tps'"
  by (rule transforms_branchI[where tT=t and tpsT=tps' and tF=0 and tpsF=tps']) (use assms in simp_all)

lemma ifF:
  assumes "\<not> cond (read tps)"
  shows "transforms (IF cond THEN M1 ELSE [] ENDIF) tps 1 tps"
  by (rule transforms_branchI[where tF=0]) (use assms transforms_Nil in simp_all)

lemma read27: "length tps = 93 \<Longrightarrow> tps ! 27 = (\<lfloor>P\<rfloor>\<^sub>B, 1) \<Longrightarrow> read tps ! 27 \<noteq> \<box> \<longleftrightarrow> P"
  using read_ncontents_eq_0[of tps 27] by simp

lemma cube_bound:
  fixes x c s :: nat
  assumes "x \<le> c * s ^ 2"
  shows "x ^ 3 \<le> c ^ 3 * s ^ 6"
proof -
  have "x ^ 3 \<le> (c * s ^ 2) ^ 3"
    using assms by (rule power_mono) simp
  also have "\<dots> = c ^ 3 * s ^ 6"
    by (simp add: power_mult_distrib power_mult[symmetric])
  finally show ?thesis .
qed

context
  fixes nss nssc :: "nat list list"
begin

abbreviation "wts \<equiv> nth_or [] nss 1"
abbreviation "es \<equiv> nth_or [] nss 2"
abbreviation "hdr \<equiv> nth_or [] nss 0"
abbreviation "kk \<equiv> nth_or 0 hdr 0"
abbreviation "BB \<equiv> nth_or 0 hdr 1"
abbreviation "n \<equiv> length wts"
abbreviation "L0 \<equiv> nth_or [] nssc 0"
abbreviation "c0 \<equiv> nth_or 0 L0 1"
abbreviation "d \<equiv> nth_or 0 L0 0"
abbreviation "g \<equiv> grow n es (L0 ! 1) (drop 2 L0)"
abbreviation "S \<equiv> snd g"

abbreviation "ok0 \<equiv> 1 < length L0 \<and> c0 < n"
abbreviation "ok1 \<equiv> fst g"
abbreviation "ok2 \<equiv> d + wsum wts S = BB"
abbreviation "ok3 \<equiv> n < length nssc \<and> (\<forall>v<n. length (nssc ! Suc v) \<le> kk)"
abbreviation "ok4 \<equiv> own_ok n es S nssc"

lemma nth_or_lt: "i < length xs \<Longrightarrow> nth_or dd xs i = xs ! i"
  unfolding nth_or_def by simp

lemma S_sub:
  assumes "ok0"
  shows "set S \<subseteq> {..<n}"
proof -
  have "L0 ! 1 < n"
    using assms nth_or_lt[of 1 L0 0] by simp
  then show ?thesis
    unfolding grow_def by (intro foldl_grow_set) simp
qed

lemma S_len: "length S \<le> Suc (length L0)"
proof -
  have "length S \<le> 1 + length (drop 2 L0)"
    unfolding grow_def using foldl_grow_length[of n es "(True, [L0 ! 1])" "drop 2 L0"] by simp
  then show ?thesis
    by simp
qed

lemma cert_ok_iff: "cert_ok nss nssc \<longleftrightarrow> ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4"
proof
  assume c: "cert_ok nss nssc"
  then have l: "2 \<le> length L0"
    unfolding cert_ok_def Let_def by simp
  then have l1: "1 < length L0" "0 < length L0"
    by linarith+
  have e: "c0 = L0 ! 1" "d = L0 ! 0"
    using nth_or_lt[OF l1(1)] nth_or_lt[OF l1(2)] by simp_all
  have "ok0"
    using c l e unfolding cert_ok_def Let_def n_of_def wts_of_def by simp
  then have sub: "set S \<subseteq> {..<n}"
    by (rule S_sub)
  have w: "sum_list (map (w_of nss) S) = wsum wts S"
    unfolding wsum_def w_of_def wts_of_def
    using sub nth_or_lt[of _ wts 0] by (intro arg_cong[where f=sum_list] map_cong) auto
  show "ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4"
    using c l e w \<open>ok0\<close> unfolding cert_ok_def Let_def n_of_def wts_of_def es_of_def B_of_def k_of_def
      hdr_of_def
    by auto
next
  assume c: "ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4"
  then have l: "2 \<le> length L0"
    by simp
  then have l1: "1 < length L0" "0 < length L0"
    by linarith+
  have e: "c0 = L0 ! 1" "d = L0 ! 0"
    using nth_or_lt[OF l1(1)] nth_or_lt[OF l1(2)] by simp_all
  have sub: "set S \<subseteq> {..<n}"
    using c S_sub by simp
  have w: "sum_list (map (w_of nss) S) = wsum wts S"
    unfolding wsum_def w_of_def wts_of_def
    using sub nth_or_lt[of _ wts 0] by (intro arg_cong[where f=sum_list] map_cong) auto
  show "cert_ok nss nssc"
    using c l e w unfolding cert_ok_def Let_def n_of_def wts_of_def es_of_def B_of_def k_of_def
      hdr_of_def
    by (auto simp: add.commute)
qed

definition sg :: nat where
  "sg \<equiv> nlllength nss + nlllength nssc + 1"

lemma cert_sizes:
  "nllength wts \<le> sg" "nllength es \<le> sg" "n \<le> sg" "nlength n \<le> sg" "nllength L0 \<le> sg"
  "length L0 \<le> sg" "nlength d \<le> sg" "nlength kk \<le> sg" "nlength BB \<le> sg"
  "nlllength nssc \<le> sg" "1 \<le> sg"
proof -
  show w: "nllength wts \<le> sg"
    using nllength_nth_or_le[of nss 1] unfolding sg_def by simp
  show "nllength es \<le> sg"
    using nllength_nth_or_le[of nss 2] unfolding sg_def by simp
  show n: "n \<le> sg"
    using length_le_nllength[of wts] w by simp
  show "nlength n \<le> sg"
    using nlength_le_n[of n] n by simp
  show l: "nllength L0 \<le> sg"
    using nllength_nth_or_le[of nssc 0] unfolding sg_def by simp
  show "length L0 \<le> sg"
    using length_le_nllength[of L0] l by simp
  show "nlength d \<le> sg"
    using nlength_nth_or_le[of L0 0] l by simp
  have h: "nllength hdr \<le> sg"
    using nllength_nth_or_le[of nss 0] unfolding sg_def by simp
  show "nlength kk \<le> sg" "nlength BB \<le> sg"
    using nlength_nth_or_le[of hdr 0] nlength_nth_or_le[of hdr 1] h by simp_all
  show "nlllength nssc \<le> sg" "1 \<le> sg"
    unfolding sg_def by simp_all
qed

lemma S_size: "ok0 \<Longrightarrow> nllength S \<le> 4 * sg ^ 2"
proof -
  assume ok: "ok0"
  have "\<forall>x\<in>set S. x \<le> n"
    using S_sub[OF ok] by fastforce
  then have "nllength S \<le> Suc (nlength n) * length S"
    by (rule nllength_le_len_mult_max)
  also have "\<dots> \<le> (2 * sg) * (2 * sg)"
    by (intro mult_le_mono; lin facts: cert_sizes S_len)
  also have "\<dots> = 4 * sg ^ 2"
    by (simp add: power2_eq_square)
  finally show ?thesis .
qed

lemma cert_time:
  assumes "ok0"
  shows "2000 * sg ^ 2 + (3300 * (nllength es + Suc n * nllength L0 + nllength L0 + n + 1) ^ 3 +
      (400 * (nllength wts + nllength S + nlength d + 2) ^ 3 + 3 * nlength BB +
      (1200 * (nlllength nssc + nlength kk + n + 2) ^ 3 +
      (3400 * (nlllength nssc + nllength es + nllength S + n + 2) ^ 3 + 2) + 2) + 2) + 2)
    \<le> 4000000 * sg ^ 6"
proof -
  note cs = cert_sizes and ss = S_size[OF assms]
  have p: "sg \<le> sg ^ 2" "sg ^ 2 \<le> sg ^ 6" "sg \<le> sg ^ 6" "1 \<le> sg ^ 6" "sg ^ 3 \<le> sg ^ 6"
    using power_increasing[of 1 2 sg] power_increasing[of 2 6 sg] power_increasing[of 1 6 sg]
      power_increasing[of 3 6 sg] cs(11) by simp_all
  have m: "Suc n * nllength L0 \<le> 2 * sg ^ 2"
  proof -
    have "Suc n * nllength L0 \<le> (2 * sg) * sg"
      by (intro mult_le_mono; lin facts: cs)
    then show ?thesis
      by (simp add: power2_eq_square)
  qed
  have g0: "(nllength es + Suc n * nllength L0 + nllength L0 + n + 1) \<le> 6 * sg ^ 2"
    by (lin facts: cs m p)
  have g: "(nllength es + Suc n * nllength L0 + nllength L0 + n + 1) ^ 3 \<le> 216 * sg ^ 6"
    using cube_bound[OF g0] by simp
  have w0: "(nllength wts + nllength S + nlength d + 2) \<le> 8 * sg ^ 2"
    by (lin facts: cs ss p)
  have w: "(nllength wts + nllength S + nlength d + 2) ^ 3 \<le> 512 * sg ^ 6"
    using cube_bound[OF w0] by simp
  have l0: "(nlllength nssc + nlength kk + n + 2) \<le> 5 * sg ^ 2"
    by (lin facts: cs p)
  have l: "(nlllength nssc + nlength kk + n + 2) ^ 3 \<le> 125 * sg ^ 6"
    using cube_bound[OF l0] by simp
  have o0: "(nlllength nssc + nllength es + nllength S + n + 2) \<le> 9 * sg ^ 2"
    by (lin facts: cs ss p)
  have o: "(nlllength nssc + nllength es + nllength S + n + 2) ^ 3 \<le> 729 * sg ^ 6"
    using cube_bound[OF o0] by simp
  show ?thesis
    by (lin facts: g w l o cs p)
qed

lemma tm_cert:
  assumes len: "length tps = 93"
    and t7: "tps ! 7 = (\<lfloor>nss\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)" and t11: "tps ! 11 = (\<lfloor>nssc\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1)"
    and blank: "\<And>j. 14 \<le> j \<Longrightarrow> j < 93 \<Longrightarrow> tps ! j = (\<lfloor>[]\<rfloor>, 1)"
  shows "\<exists>tps'. length tps' = 93 \<and> tps' ! 1 = tps ! 1 \<and> tps' ! 27 = (\<lfloor>cert_ok nss nssc\<rfloor>\<^sub>B, 1) \<and>
    transforms tm_cert tps (4000000 * sg ^ 6) tps'"
proof -
  interpret F: turing_machine_fields .
  have b0: "tps ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "14 \<le> j" "j < 93" for j
    using blank[OF that] ncontents_0 by simp
  have bL: "tps ! j = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)" if "14 \<le> j" "j < 93" for j
    using blank[OF that] nlcontents_Nil by simp
  have ff: "tps ! 14 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)" "tps ! 15 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)" "tps ! 16 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
    "tps ! 17 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 18 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 19 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 20 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 21 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)" "tps ! 22 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 23 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 25 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 26 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 27 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 28 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 29 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    "tps ! 30 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 31 = (\<lfloor>0\<rfloor>\<^sub>N, 1)" "tps ! 32 = (\<lfloor>0\<rfloor>\<^sub>N, 1)"
    using bL[of 14] bL[of 15] bL[of 16] bL[of 21] b0[of 17] b0[of 18] b0[of 19] b0[of 20] b0[of 22]
      b0[of 23] b0[of 25] b0[of 26] b0[of 27] b0[of 28] b0[of 29] b0[of 30] b0[of 31] b0[of 32]
    by simp_all
  define tV where "tV = tps
    [7 := nlltape' nss (min 3 (length nss)),
     14 := nltape' hdr (min 2 (length hdr)),
     15 := (\<lfloor>wts\<rfloor>\<^sub>N\<^sub>L, 1),
     16 := (\<lfloor>es\<rfloor>\<^sub>N\<^sub>L, 1),
     17 := (\<lfloor>kk\<rfloor>\<^sub>N, 1),
     18 := (\<lfloor>BB\<rfloor>\<^sub>N, 1),
     19 := (\<lfloor>n\<rfloor>\<^sub>N, 1),
     20 := (\<lfloor>length es\<rfloor>\<^sub>N, 1),
     11 := nlltape' nssc (min 1 (length nssc)),
     21 := nltape' L0 (min 2 (length L0)),
     25 := (\<lfloor>length L0\<rfloor>\<^sub>N, 1),
     26 := (\<lfloor>1\<rfloor>\<^sub>N, 1),
     27 := (\<lfloor>ok0\<rfloor>\<^sub>B, 1),
     22 := (\<lfloor>d\<rfloor>\<^sub>N, 1),
     23 := (\<lfloor>c0\<rfloor>\<^sub>N, 1),
     30 := (\<lfloor>c0 < n\<rfloor>\<^sub>B, 1)]"
  have TF: "transforms tm_fields tps (2000 * sg ^ 2) tV"
    using F.tm_fields[OF len t7 t11 ff] F.tpsV_def[OF len t7 t11 ff] tV_def sg_def by simp
  have lV: "length tV = 93"
    using len tV_def by simp
  have rV: "read tV ! 27 \<noteq> \<box> \<longleftrightarrow> ok0"
    using read27[OF lV] tV_def len by simp
  have T: "\<exists>tps'. length tps' = 93 \<and> tps' ! 1 = tps ! 1 \<and>
      tps' ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1) \<and>
      transforms tm_cert tps (4000000 * sg ^ 6) tps'"
  proof (cases ok0)
    case False
    have "transforms tm_cert tps (2000 * sg ^ 2 + 1) tV"
      unfolding tm_cert_def using transforms_tm_sequentialI[OF TF ifF] False rV by simp
    moreover have "2000 * sg ^ 2 + 1 \<le> 4000000 * sg ^ 6"
    proof -
      have "1 \<le> sg ^ 6" "sg ^ 2 \<le> sg ^ 6"
        using cert_sizes(11) power_increasing[of 2 6 sg] by simp_all
      then show ?thesis
        by linarith
    qed
    ultimately have "transforms tm_cert tps (4000000 * sg ^ 6) tV"
      by (rule transforms_monotone)
    moreover have "tV ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1)" "tV ! 1 = tps ! 1"
    proof -
      have v27: "tV ! 27 = (\<lfloor>ok0\<rfloor>\<^sub>B, 1)"
        using len unfolding tV_def by simp
      have e: "(ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4) = ok0"
        using False by blast
      show "tV ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1)"
        unfolding e by (rule v27)
      show "tV ! 1 = tps ! 1"
        using len unfolding tV_def by simp
    qed
    ultimately show ?thesis
      using lV by blast
  next
    case ok0: True
    have L0: "2 \<le> length L0" "L0 ! 1 < n" "c0 = L0 ! 1" "min 2 (length L0) = 2" "1 \<le> length nssc"
      "min 1 (length nssc) = 1"
    proof -
      show l: "2 \<le> length L0"
        using ok0 by linarith
      show c: "c0 = L0 ! 1"
        using ok0 nth_or_lt[of 1 L0 0] by simp
      show "L0 ! 1 < n"
        using ok0 c by simp
      show "min 2 (length L0) = 2"
        using l by simp
      show ne: "1 \<le> length nssc"
      proof (rule ccontr)
        assume "\<not> 1 \<le> length nssc"
        then have "nssc = []"
          by (cases nssc) auto
        then have "L0 = []"
          unfolding nth_or_def by simp
        then show False
          using l by simp
      qed
      show "min 1 (length nssc) = 1"
        using ne by simp
    qed
    have sub: "set S \<subseteq> {..<n}"
      by (rule S_sub[OF ok0])
    have z: "tV ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "34 \<le> j" "j < 93" for j
      using that b0 len unfolding tV_def by (simp add: nth_list_update_if)
    define tG where "tG = tV[21 := nltape' L0 (length L0), 27 := (\<lfloor>ok1\<rfloor>\<^sub>B, 1), 33 := (\<lfloor>S\<rfloor>\<^sub>N\<^sub>L, 1)]"
    let ?TG = "3300 * (nllength es + Suc n * nllength L0 + nllength L0 + n + 1) ^ 3"
    have G: "transforms tm_grow tV ?TG tG"
    proof (rule transforms_tm_growI[where es=es and n=n])
      show "tV ! 33 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
        using bL len unfolding tV_def by (simp add: nth_list_update_if)
      show "tV ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "34 \<le> j" "j \<le> 54" for j
        using z that by simp
    qed (use lV L0 ok0 len tG_def in \<open>simp_all add: tV_def\<close>)
    have lG: "length tG = 93"
      using lV tG_def by simp
    have rG: "read tG ! 27 \<noteq> \<box> \<longleftrightarrow> ok1"
      using read27[OF lG] tG_def lV by simp
    show ?thesis
    proof (cases ok1)
      case False
      have "transforms tm_cert tps (2000 * sg ^ 2 + (?TG + 1 + 2)) tG"
        unfolding tm_cert_def tm_c1_def
        using transforms_tm_sequentialI[OF TF ifT[OF _ transforms_tm_sequentialI[OF G ifF]]] False rV rG ok0
        by simp
      moreover have "2000 * sg ^ 2 + (?TG + 1 + 2) \<le> 4000000 * sg ^ 6"
        using cert_time[OF ok0] by linarith
      ultimately have "transforms tm_cert tps (4000000 * sg ^ 6) tG"
        by (rule transforms_monotone)
      moreover have "tG ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1)" "tG ! 1 = tps ! 1"
        using False lV len unfolding tG_def tV_def by simp_all
      ultimately show ?thesis
        using lG by blast
    next
      case ok1: True
      define tW where "tW = tG[57 := (\<lfloor>d + wsum wts S\<rfloor>\<^sub>N, 1), 58 := (\<lfloor>ok2\<rfloor>\<^sub>B, 1),
        27 := (\<lfloor>ok2\<rfloor>\<^sub>B, 1)]"
      let ?TW = "400 * (nllength wts + nllength S + nlength d + 2) ^ 3 + 3 * nlength BB"
      have zG: "tG ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "34 \<le> j" "j < 93" "j \<noteq> 21" "j \<noteq> 27" "j \<noteq> 33" for j
        using z that lV unfolding tG_def by (simp add: nth_list_update_if)
      have W: "transforms tm_weights tG ?TW tW"
        by (rule transforms_tm_weightsI[where wts=wts and S=S and d=d and B=BB])
          (use lG sub ok1 zG tW_def in \<open>simp_all add: tG_def tV_def len\<close>)
      have lW: "length tW = 93"
        using lG tW_def by simp
      have rW: "read tW ! 27 \<noteq> \<box> \<longleftrightarrow> ok2"
        using read27[OF lW] tW_def lG by simp
      show ?thesis
      proof (cases ok2)
        case False
        have "transforms tm_cert tps (2000 * sg ^ 2 + (?TG + (?TW + 1 + 2) + 2)) tW"
          unfolding tm_cert_def tm_c1_def tm_c2_def
          using transforms_tm_sequentialI[OF TF ifT[OF _ transforms_tm_sequentialI[OF G
            ifT[OF _ transforms_tm_sequentialI[OF W ifF]]]]] False rV rG rW ok0 ok1
          by simp
        moreover have "2000 * sg ^ 2 + (?TG + (?TW + 1 + 2) + 2) \<le> 4000000 * sg ^ 6"
          using cert_time[OF ok0] by linarith
        ultimately have "transforms tm_cert tps (4000000 * sg ^ 6) tW"
          by (rule transforms_monotone)
        moreover have "tW ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1)" "tW ! 1 = tps ! 1"
          using False lG lV len unfolding tW_def tG_def tV_def by simp_all
        ultimately show ?thesis
          using lW by blast
      next
        case ok2: True
        define tL where "tL = tW[11 := nlltape' nssc (min (Suc n) (length nssc)), 27 := (\<lfloor>ok3\<rfloor>\<^sub>B, 1)]"
        let ?TL = "1200 * (nlllength nssc + nlength kk + n + 2) ^ 3"
        have zW: "tW ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "59 \<le> j" "j < 93" for j
          using zG that lG unfolding tW_def by (simp add: nth_list_update_if)
        have LD: "transforms tm_loads tW ?TL tL"
        proof (rule transforms_tm_loadsI[where nssc=nssc and n=n and kk=kk])
          show "tW ! 60 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
            using bL lG lV len unfolding tW_def tG_def tV_def by (simp add: nth_list_update_if)
        qed (use lW L0 ok2 zW tL_def in \<open>simp_all add: tW_def tG_def tV_def len\<close>)
        have lL: "length tL = 93"
          using lW tL_def by simp
        have rL: "read tL ! 27 \<noteq> \<box> \<longleftrightarrow> ok3"
          using read27[OF lL] tL_def lW by simp
        show ?thesis
        proof (cases ok3)
          case False
          have "transforms tm_cert tps (2000 * sg ^ 2 + (?TG + (?TW + (?TL + 1 + 2) + 2) + 2)) tL"
            unfolding tm_cert_def tm_c1_def tm_c2_def tm_c3_def
            using transforms_tm_sequentialI[OF TF ifT[OF _ transforms_tm_sequentialI[OF G
              ifT[OF _ transforms_tm_sequentialI[OF W ifT[OF _ transforms_tm_sequentialI[OF LD ifF]]]]]]]
              False rV rG rW rL ok0 ok1 ok2
            by simp
          moreover have "2000 * sg ^ 2 + (?TG + (?TW + (?TL + 1 + 2) + 2) + 2) \<le> 4000000 * sg ^ 6"
            using cert_time[OF ok0] by linarith
          ultimately have "transforms tm_cert tps (4000000 * sg ^ 6) tL"
            by (rule transforms_monotone)
          moreover have "tL ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1)" "tL ! 1 = tps ! 1"
          proof -
            have v27: "tL ! 27 = (\<lfloor>ok3\<rfloor>\<^sub>B, 1)"
              using lW unfolding tL_def by simp
            have e: "(ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4) = ok3"
              using False ok0 ok1 ok2 by blast
            show "tL ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1)"
              unfolding e by (rule v27)
            show "tL ! 1 = tps ! 1"
              using lW lG lV len unfolding tL_def tW_def tG_def tV_def by simp
          qed
          ultimately show ?thesis
            using lL by blast
        next
          case ok3: True
          define tO where "tO = tL[11 := (\<lfloor>nssc\<rfloor>\<^sub>N\<^sub>L\<^sub>L, 1), 16 := nltape' es (2 * (length es div 2)),
            27 := (\<lfloor>ok4\<rfloor>\<^sub>B, 1), 65 := (\<lfloor>0\<rfloor>\<^sub>N, 1)]"
          let ?TO = "3400 * (nlllength nssc + nllength es + nllength S + n + 2) ^ 3"
          have zL: "tL ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "59 \<le> j" "j < 93" for j
            using zW that lW unfolding tL_def by (simp add: nth_list_update_if)
          have OW: "transforms tm_owners tL ?TO tO"
          proof (rule transforms_tm_ownersI[where nssc=nssc and es=es and S=S and n=n
              and p="min (Suc n) (length nssc)"])
            show "tL ! 79 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)" "tL ! 88 = (\<lfloor>[]\<rfloor>\<^sub>N\<^sub>L, 1)"
              using bL lL lW lG lV len unfolding tL_def tW_def tG_def tV_def
              by (simp_all add: nth_list_update_if)
            show "tL ! j = (\<lfloor>0\<rfloor>\<^sub>N, 1)" if "66 \<le> j" "j \<le> 92" "j \<noteq> 79" "j \<noteq> 88" for j
              using zL that by simp
          qed (use lL ok3 sub ok2 zL tO_def in \<open>simp_all add: tL_def tW_def tG_def tV_def len\<close>)
          have lO: "length tO = 93"
            using lL tO_def by simp
          have "transforms tm_cert tps (2000 * sg ^ 2 + (?TG + (?TW + (?TL + (?TO + 2) + 2) + 2) + 2)) tO"
            unfolding tm_cert_def tm_c1_def tm_c2_def tm_c3_def
            using transforms_tm_sequentialI[OF TF ifT[OF _ transforms_tm_sequentialI[OF G
              ifT[OF _ transforms_tm_sequentialI[OF W ifT[OF _ transforms_tm_sequentialI[OF LD
              ifT[OF _ OW]]]]]]]] rV rG rW rL ok0 ok1 ok2 ok3
            by simp
          moreover have "2000 * sg ^ 2 + (?TG + (?TW + (?TL + (?TO + 2) + 2) + 2) + 2) \<le> 4000000 * sg ^ 6"
            using cert_time[OF ok0] by linarith
          ultimately have "transforms tm_cert tps (4000000 * sg ^ 6) tO"
            by (rule transforms_monotone)
          moreover have "tO ! 27 = (\<lfloor>ok0 \<and> ok1 \<and> ok2 \<and> ok3 \<and> ok4\<rfloor>\<^sub>B, 1)" "tO ! 1 = tps ! 1"
            using ok0 ok1 ok2 ok3 lL lW lG lV len unfolding tO_def tL_def tW_def tG_def tV_def by simp_all
          ultimately show ?thesis
            using lO by blast
        qed
      qed
    qed
  qed
  then show ?thesis
    using cert_ok_iff by simp
qed

end

end
