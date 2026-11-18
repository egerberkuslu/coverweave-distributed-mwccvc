# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **anneal_replacement**: 450 rows replaced; the originals are at _archive/medium_anneal_before_107_rows.csv
- **code_fingerprint**: 798b4393cb4f/be8a9f9c1e43/bebb0f917410
- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **fingerprint_roles**: {'798b4393cb4f': 'measured on the first pass, non-annealing arms', 'bebb0f917410': 'GHS-MST-Backbone, plus rows re-run after being skipped', 'be8a9f9c1e43': 'the three annealing arms, re-measured after the §107 fix'}
- **k**: 6
- **loss**: 0
- **rows**: 2250
- **source**: dataset
- **stage**: medium

## 1b. Girdi bağlılığı

Bütün 90 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **0** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 250 / 200 / 1800 |
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
| dataset | medium | 50 | 2 | 100 | 10 | 10 | 10 tohum |
| dataset | medium | 50 | 4 | 200 | 10 | 10 | 10 tohum |
| dataset | medium | 50 | 6 | 300 | 10 | 10 | 10 tohum |
| dataset | medium | 50 | 8 | 400 | 10 | 10 | 10 tohum |
| dataset | medium | 50 | 10 | 500 | 10 | 10 | 10 tohum |
| dataset | medium | 100 | 2 | 200 | 10 | 10 | 10 tohum |
| dataset | medium | 100 | 4 | 400 | 10 | 10 | 10 tohum |
| dataset | medium | 100 | 6 | 600 | 10 | 10 | 10 tohum |
| dataset | medium | 100 | 8 | 800 | 10 | 10 | 10 tohum |

3'ten az tohumlu hücre: **0/9**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Anneal-Local/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Anneal-TreeAgg/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Anneal-TreeAgg/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Anneal-Trickle/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `DFS-Spanning-Backbone/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `DFS-Spanning-Backbone/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `GHS-MST-Backbone/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `GHS-MST-Backbone/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Greedy-Degree-Backbone/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Greedy-Degree-Backbone/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Greedy-Ratio-Backbone/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Greedy-Ratio-Backbone/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Greedy-Weight-Backbone/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `Greedy-Weight-Backbone/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `MIS-Connector-Backbone/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `MIS-Connector-Backbone/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `MIS-Connector-TreeAgg/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `MIS-Connector-TreeAgg/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `WuLi-Dominating-Bloom/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `WuLi-Dominating-Bloom/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `WuLi-Dominating-Chunked/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `WuLi-Dominating-Chunked/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `WuLi-Dominating-Exact/async` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |
| `WuLi-Dominating-Exact/sync` | 90 | 50 | 50 | infeasible=40, ok=50 | ok=50 |

### 4b. Bu k'da KANITLANABİLİR UYGUNSUZ hücreler

Aşağıdaki hücrelerde C=V ile bile kapasite atanamıyor (Hakimi). Burada bir kolun başarısız olması **kol kusuru değildir**; bu satırlar oran ortalamalarının tamamen dışındadır. Matrisi bu k ile koşmak bu hücreleri anlamsız kılar, k büyütülmelidir.

| grup | n | m/n | m | ⌈m/k⌉ |
|---|---|---|---|---|
| medium | 50 | 6 | 300 | 50 |
| medium | 50 | 8 | 400 | 67 |
| medium | 50 | 10 | 500 | 84 |
| medium | 100 | 6 | 600 | 100 |
| medium | 100 | 8 | 800 | 134 |

Kol başına: uygunsuz örnekte uygunsuzluğu **ilan edemeyen** koşum sayısı `missed_infeasible` sütununda (özet JSON), harcanan slot/tx `infeasible_slots_mean`/`infeasible_tx_mean` içinde.

> **`missed_infeasible` KOLLAR ARASI FARK OKUMAK İÇİN KULLANILAMAZ.** Uygunsuzluk tespiti Faz 4'ün ortak kodundadır, dolayısıyla tespit kusuru bütün kollarda AYNI okunur.

> Ayrıca her kaçırma kusur DEĞİLDİR. Sayma sınırı (m > n·k) ucuzca kanıtlanabilir dejenere sınıfı yakalar; onun dışındaki uygunsuzluk yalnız akışla görülür ve bugünkü HELLO ile sağlam bir YEREL tanık hesaplanamaz, yani düğümün bildirememesi beklenen davranıştır. Kusur sayılabilecek olan `missed_provable_infeasible` sütunudur; `infeasible_not_cheaply_provable` ise kaçırılması normal olan satırları sayar.

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **50** örnek (toplam 50)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 40
- kesin çözüm referansı olan örnek: 0

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 1.0401 | 1.0401 | — | 9949.28 | — |
| `Anneal-Local/sync` | 1.0474 | 1.0474 | — | 11341.7 | — |
| `Anneal-TreeAgg/async` | 1.0401 | 1.0401 | — | 9949.28 | — |
| `Anneal-TreeAgg/sync` | 1.0474 | 1.0474 | — | 11341.7 | — |
| `Anneal-Trickle/async` | 1.0644 | 1.0644 | — | 6315.44 | — |
| `DFS-Spanning-Backbone/async` | 1.281 | 1.281 | — | 39965.5 | — |
| `DFS-Spanning-Backbone/sync` | 1.276 | 1.276 | — | 75343.4 | — |
| `GHS-MST-Backbone/async` | 1.1987 | 1.1987 | — | 9572.58 | — |
| `GHS-MST-Backbone/sync` | 1.2095 | 1.2095 | — | 13098.6 | — |
| `Greedy-Degree-Backbone/async` | 1.2941 | 1.2941 | — | 5665.22 | — |
| `Greedy-Degree-Backbone/sync` | 1.2942 | 1.2942 | — | 7491.4 | — |
| `Greedy-Ratio-Backbone/async` | 1.2941 | 1.2941 | — | 5635.8 | — |
| `Greedy-Ratio-Backbone/sync` | 1.2942 | 1.2942 | — | 7491.4 | — |
| `Greedy-Weight-Backbone/async` | 1.2941 | 1.2941 | — | 5635.94 | — |
| `Greedy-Weight-Backbone/sync` | 1.2942 | 1.2942 | — | 7491.4 | — |
| `MIS-Connector-Backbone/async` | 1.2935 | 1.2935 | — | 4763.34 | — |
| `MIS-Connector-Backbone/sync` | 1.294 | 1.294 | — | 6279.18 | — |
| `MIS-Connector-TreeAgg/async` | 1.2935 | 1.2935 | — | 8958.68 | — |
| `MIS-Connector-TreeAgg/sync` | 1.294 | 1.294 | — | 11808 | — |
| `WuLi-Dominating-Bloom/async` | 1.2966 | 1.2966 | — | 3995.74 | — |
| `WuLi-Dominating-Bloom/sync` | 1.2966 | 1.2966 | — | 5340.06 | — |
| `WuLi-Dominating-Chunked/async` | 1.2951 | 1.2951 | — | 5804.22 | — |
| `WuLi-Dominating-Chunked/sync` | 1.2951 | 1.2951 | — | 7977.74 | — |
| `WuLi-Dominating-Exact/async` | 1.2951 | 1.2951 | — | 4136.34 | — |
| `WuLi-Dominating-Exact/sync` | 1.2951 | 1.2951 | — | 5432.46 | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 50 | 0 | 0 | 0.9996 | 0.8025 |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 50 | 0 | 0 | 1 | 2.1316 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 50 | 0 | 0 | 1.0009 | 0.867 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 50 | 0 | 0 | 1.0019 | 0.8622 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 50 | 0 | 0 | 1.0009 | 1.0893 |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 50 | 0 | 0 | 1 | 1.9521 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 50 | 0 | 0 | 1.0012 | 0.9179 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 50 | 0 | 0 | 1.0023 | 0.9099 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 50 | 0 | 0 | 1.0012 | 1.1086 |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 50 | 0 | 0 | 0.9996 | 0.7415 |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 50 | 0 | 0 | 1.0039 | 0.5377 |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 50 | 0 | 0 | 0.9917 | 0.6926 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 50 | 0 | 0 | 1 | 0.8498 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 50 | 0 | 0 | 1.001 | 0.9962 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 50 | 0 | 0 | 1 | 1.2539 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 50 | 0 | 0 | 1.001 | 0.9896 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 50 | 0 | 0 | 1 | 1.2189 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 50 | 0 | 0 | 1 | 0.8436 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 50 | 0 | 0 | 0.999 | 1.2641 |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 50 | 0 | 0 | 0.999 | 1.2564 |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 50 | 0 | 0 | 1 | 0.8281 |
| `Anneal-Local/sync` | `Anneal-Local/async` | scheduler | 50 | 0 | 0 | 0.9994 | 0.9221 |
| `Anneal-Local/sync` | `Anneal-TreeAgg/sync` | phase5 | 50 | 0 | 0 | 1 | 1 |
| `Anneal-Local/sync` | `Anneal-Trickle/async` | scheduler | 50 | 0 | 0 | 1.0203 | 0.5775 |
| `Anneal-Local/async` | `Anneal-TreeAgg/async` | phase5 | 50 | 0 | 0 | 1 | 1 |
| `Anneal-TreeAgg/sync` | `Anneal-TreeAgg/async` | scheduler | 50 | 0 | 0 | 0.9994 | 0.9221 |
| `Anneal-TreeAgg/async` | `Anneal-Trickle/async` | phase5 | 50 | 0 | 0 | 1.0257 | 0.6287 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 50 | 0 | 0 | 0.9999 | 0.7942 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 50 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 50 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 50 | 0 | 0 | 1 | 0.9972 |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 50 | 0 | 0 | 1 | 0.9972 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 50 | 0 | 0 | 0.9999 | 0.7919 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 50 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 50 | 0 | 0 | 1 | 1 |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 50 | 0 | 0 | 0.9999 | 0.792 |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

1000 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

| durum | satır | ort. slot | ort. tx | örnekler |
|---|---|---|---|---|
| `infeasible` | 1000 | 2116.92 | 180787 | n100_m600_s1.txt/Anneal-Local/async, n100_m600_s1.txt/Anneal-Local/sync, n100_m600_s1.txt/Anneal-TreeAgg/async |
