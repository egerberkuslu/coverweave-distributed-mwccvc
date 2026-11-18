# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **anneal_replacement**: 700 rows replaced; the originals are at _archive/small_anneal_before_107_rows.csv
- **code_fingerprint**: 798b4393cb4f/be8a9f9c1e43/bebb0f917410
- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **fingerprint_roles**: {'798b4393cb4f': 'measured on the first pass, non-annealing arms', 'bebb0f917410': 'GHS-MST-Backbone, plus rows re-run after being skipped', 'be8a9f9c1e43': 'the three annealing arms, re-measured after the §107 fix'}
- **k**: 6
- **loss**: 0
- **rows**: 3500
- **source**: dataset
- **stage**: small

## 1b. Girdi bağlılığı

Bütün 140 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **0** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 550 / 150 / 2800 |
| kesik koşum (`truncated`) | 0 |
| kopuk girdi (`bad_input`) | 0 |
| kod sürümü (parmak izi) | 798b4393cb4f/be8a9f9c1e43/bebb0f917410 |

> **UYARI: bu CSV birden çok KOD SÜRÜMÜNDEN ölçülmüş satır içeriyor** (3 ayrı parmak izi). Süpürme sürerken depoya yama inmiş demektir; satırlar aynı tabloda toplanamaz, süpürme yeniden koşulmalıdır.

`n/a` satırları uyuşmazlık DEĞİLDİR: çözümü olmayan bir örnekte izin hiç geçerli durum görmemesi ile koşumun son yapılandırmayı döndürmesi birbiriyle tam uyumludur. Ayrı sayılmalarının nedeni, rutin olarak beklenen uyuşmazlık bildiren bir denetimin göz atılıp geçilmesi ve gerçek olanın içinde saklanmasıdır.

## 2. Matris kapsamı

İstenen 52 hücrenin 3 tanesi **matematiksel olarak imkânsız** (basit çizgede m > C(n,2)), veri kümesinde eksik değil:

- n=10, m/n=6: m=60 > C(10,2)=45; bu n için en büyük oran 4.5
- n=10, m/n=8: m=80 > C(10,2)=45; bu n için en büyük oran 4.5
- n=15, m/n=8: m=120 > C(15,2)=105; bu n için en büyük oran 7.0

Kalan 49 hücrenin 49 tanesi veri kümesinde var, toplam 310 örnek. **20 hücrede 3'ten az tohum var.**

## 3. Hücre başına tohum sayısı

Deney disiplini hücre başına en az 3 tohum ister. Aşağıdaki tabloda `TEK KOŞUM` yazan satırlarda **ortalama alınamaz**: tek koşum bir ortalama değil bir gözlemdir ve öyle etiketlenmiştir.

| kaynak | grup | n | m/n | m | koşulan tohum | veri kümesinde | etiket |
|---|---|---|---|---|---|---|---|
| dataset | small | 10 | 2 | 20 | 10 | 10 | 10 tohum |
| dataset | small | 10 | 4 | 40 | 10 | 10 | 10 tohum |
| dataset | small | 15 | 2 | 30 | 10 | 10 | 10 tohum |
| dataset | small | 15 | 4 | 60 | 10 | 10 | 10 tohum |
| dataset | small | 15 | 6 | 90 | 10 | 10 | 10 tohum |
| dataset | small | 20 | 2 | 40 | 10 | 10 | 10 tohum |
| dataset | small | 20 | 4 | 80 | 10 | 10 | 10 tohum |
| dataset | small | 20 | 6 | 120 | 10 | 10 | 10 tohum |
| dataset | small | 20 | 8 | 160 | 10 | 10 | 10 tohum |
| dataset | small | 25 | 2 | 50 | 10 | 10 | 10 tohum |
| dataset | small | 25 | 4 | 100 | 10 | 10 | 10 tohum |
| dataset | small | 25 | 6 | 150 | 10 | 10 | 10 tohum |
| dataset | small | 25 | 8 | 200 | 10 | 10 | 10 tohum |
| dataset | small | 25 | 10 | 250 | 10 | 10 | 10 tohum |

3'ten az tohumlu hücre: **0/14**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Anneal-Local/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Anneal-TreeAgg/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Anneal-TreeAgg/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Anneal-Trickle/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `DFS-Spanning-Backbone/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `DFS-Spanning-Backbone/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `GHS-MST-Backbone/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `GHS-MST-Backbone/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Greedy-Degree-Backbone/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Greedy-Degree-Backbone/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Greedy-Ratio-Backbone/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Greedy-Ratio-Backbone/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Greedy-Weight-Backbone/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `Greedy-Weight-Backbone/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `MIS-Connector-Backbone/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `MIS-Connector-Backbone/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `MIS-Connector-TreeAgg/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `MIS-Connector-TreeAgg/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `WuLi-Dominating-Bloom/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `WuLi-Dominating-Bloom/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `WuLi-Dominating-Chunked/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `WuLi-Dominating-Chunked/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `WuLi-Dominating-Exact/async` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |
| `WuLi-Dominating-Exact/sync` | 140 | 110 | 110 | infeasible=30, ok=110 | ok=110 |

### 4b. Bu k'da KANITLANABİLİR UYGUNSUZ hücreler

Aşağıdaki hücrelerde C=V ile bile kapasite atanamıyor (Hakimi). Burada bir kolun başarısız olması **kol kusuru değildir**; bu satırlar oran ortalamalarının tamamen dışındadır. Matrisi bu k ile koşmak bu hücreleri anlamsız kılar, k büyütülmelidir.

| grup | n | m/n | m | ⌈m/k⌉ |
|---|---|---|---|---|
| small | 20 | 8 | 160 | 27 |
| small | 25 | 8 | 200 | 34 |
| small | 25 | 10 | 250 | 42 |

Kol başına: uygunsuz örnekte uygunsuzluğu **ilan edemeyen** koşum sayısı `missed_infeasible` sütununda (özet JSON), harcanan slot/tx `infeasible_slots_mean`/`infeasible_tx_mean` içinde.

> **`missed_infeasible` KOLLAR ARASI FARK OKUMAK İÇİN KULLANILAMAZ.** Uygunsuzluk tespiti Faz 4'ün ortak kodundadır, dolayısıyla tespit kusuru bütün kollarda AYNI okunur.

> Ayrıca her kaçırma kusur DEĞİLDİR. Sayma sınırı (m > n·k) ucuzca kanıtlanabilir dejenere sınıfı yakalar; onun dışındaki uygunsuzluk yalnız akışla görülür ve bugünkü HELLO ile sağlam bir YEREL tanık hesaplanamaz, yani düğümün bildirememesi beklenen davranıştır. Kusur sayılabilecek olan `missed_provable_infeasible` sütunudur; `infeasible_not_cheaply_provable` ise kaçırılması normal olan satırları sayar.

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **110** örnek (toplam 110)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 30
- kesin çözüm referansı olan örnek: 50

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 1.0778 | 1.0778 | 1.1661 | 2635.89 | — |
| `Anneal-Local/sync` | 1.0865 | 1.0865 | 1.1789 | 3018.09 | — |
| `Anneal-TreeAgg/async` | 1.0778 | 1.0778 | 1.1661 | 2635.89 | — |
| `Anneal-TreeAgg/sync` | 1.0865 | 1.0865 | 1.1789 | 3018.09 | — |
| `Anneal-Trickle/async` | 1.0808 | 1.0808 | 1.1612 | 1685.31 | — |
| `DFS-Spanning-Backbone/async` | 1.235 | 1.235 | 1.3177 | 4431.49 | — |
| `DFS-Spanning-Backbone/sync` | 1.2298 | 1.2298 | 1.3057 | 7321.77 | — |
| `GHS-MST-Backbone/async` | 1.0997 | 1.0997 | 1.142 | 2624.35 | — |
| `GHS-MST-Backbone/sync` | 1.1287 | 1.1287 | 1.1764 | 3276.64 | — |
| `Greedy-Degree-Backbone/async` | 1.2422 | 1.2422 | 1.3235 | 2132.53 | — |
| `Greedy-Degree-Backbone/sync` | 1.2691 | 1.2691 | 1.361 | 2469.19 | — |
| `Greedy-Ratio-Backbone/async` | 1.2422 | 1.2422 | 1.3208 | 1997.95 | — |
| `Greedy-Ratio-Backbone/sync` | 1.2747 | 1.2747 | 1.3744 | 2323.51 | — |
| `Greedy-Weight-Backbone/async` | 1.2465 | 1.2465 | 1.3266 | 1817.33 | — |
| `Greedy-Weight-Backbone/sync` | 1.276 | 1.276 | 1.3816 | 2150.43 | — |
| `MIS-Connector-Backbone/async` | 1.2036 | 1.2036 | 1.2657 | 2063.67 | — |
| `MIS-Connector-Backbone/sync` | 1.2179 | 1.2179 | 1.2779 | 2387.29 | — |
| `MIS-Connector-TreeAgg/async` | 1.2036 | 1.2036 | 1.2657 | 2352.3 | — |
| `MIS-Connector-TreeAgg/sync` | 1.2179 | 1.2179 | 1.2779 | 2741.77 | — |
| `WuLi-Dominating-Bloom/async` | 1.3309 | 1.3309 | 1.4675 | 1094.3 | — |
| `WuLi-Dominating-Bloom/sync` | 1.3309 | 1.3309 | 1.4675 | 1475.09 | — |
| `WuLi-Dominating-Chunked/async` | 1.2726 | 1.2726 | 1.3505 | 2712.49 | — |
| `WuLi-Dominating-Chunked/sync` | 1.2744 | 1.2744 | 1.3546 | 3297.88 | — |
| `WuLi-Dominating-Exact/async` | 1.2726 | 1.2726 | 1.3505 | 1815.88 | — |
| `WuLi-Dominating-Exact/sync` | 1.2744 | 1.2744 | 1.3546 | 2111.12 | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 110 | 0 | 0 | 0.988 | 0.8823 |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 110 | 0 | 0 | 1 | 1.379 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 110 | 0 | 0 | 1.0512 | 0.9189 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 110 | 0 | 0 | 1.1009 | 0.8398 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 110 | 0 | 0 | 1.0512 | 1.187 |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 110 | 0 | 0 | 1 | 1.321 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 110 | 0 | 0 | 1.0644 | 0.9603 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 110 | 0 | 0 | 1.1163 | 0.8434 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 110 | 0 | 0 | 1.0644 | 1.1825 |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 110 | 0 | 0 | 0.988 | 0.851 |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 110 | 0 | 0 | 1.004 | 0.6076 |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 110 | 0 | 0 | 0.9799 | 0.7624 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 110 | 0 | 0 | 0.9986 | 0.9115 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 110 | 0 | 0 | 1.0461 | 0.9284 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 110 | 0 | 0 | 1 | 1.2841 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 110 | 0 | 0 | 1.0476 | 0.8807 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 110 | 0 | 0 | 1 | 1.2304 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 110 | 0 | 0 | 1 | 0.8606 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 110 | 0 | 0 | 0.9612 | 1.5725 |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 110 | 0 | 0 | 0.9599 | 1.7022 |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 110 | 0 | 0 | 0.9986 | 0.8777 |
| `Anneal-Local/sync` | `Anneal-Local/async` | scheduler | 110 | 0 | 0 | 1.0017 | 0.9265 |
| `Anneal-Local/sync` | `Anneal-TreeAgg/sync` | phase5 | 110 | 0 | 0 | 1 | 1 |
| `Anneal-Local/sync` | `Anneal-Trickle/async` | scheduler | 110 | 0 | 0 | 1.005 | 0.5813 |
| `Anneal-Local/async` | `Anneal-TreeAgg/async` | phase5 | 110 | 0 | 0 | 1 | 1 |
| `Anneal-TreeAgg/sync` | `Anneal-TreeAgg/async` | scheduler | 110 | 0 | 0 | 1.0017 | 0.9265 |
| `Anneal-TreeAgg/async` | `Anneal-Trickle/async` | phase5 | 110 | 0 | 0 | 1.0067 | 0.6293 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 110 | 0 | 0 | 0.9796 | 0.8511 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 110 | 0 | 0 | 1.0052 | 0.9796 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 110 | 0 | 0 | 1.0066 | 0.9401 |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 110 | 0 | 0 | 1.0004 | 0.9746 |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 110 | 0 | 0 | 1.0039 | 0.9375 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 110 | 0 | 0 | 0.976 | 0.849 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 110 | 0 | 0 | 1.0019 | 0.9747 |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 110 | 0 | 0 | 1.0039 | 0.9718 |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 110 | 0 | 0 | 0.9781 | 0.8492 |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

750 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

| durum | satır | ort. slot | ort. tx | örnekler |
|---|---|---|---|---|
| `infeasible` | 750 | 1756.51 | 62455.3 | n20_m160_s1.txt/Anneal-Local/async, n20_m160_s1.txt/Anneal-Local/sync, n20_m160_s1.txt/Anneal-TreeAgg/async |
