# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **anneal_replacement**: 300 rows replaced; the originals are at _archive/large_anneal_before_107_rows.csv
- **code_fingerprint**: 798b4393cb4f/be8a9f9c1e43/bebb0f917410
- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **fingerprint_roles**: {'798b4393cb4f': 'measured on the first pass, non-annealing arms', 'bebb0f917410': 'GHS-MST-Backbone, plus rows re-run after being skipped', 'be8a9f9c1e43': 'the three annealing arms, re-measured after the §107 fix'}
- **k**: 6
- **loss**: 0
- **rows**: 1500
- **source**: dataset
- **stage**: large

## 1b. Girdi bağlılığı

Bütün 60 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **0** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 225 / 75 / 1200 |
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
| dataset | medium | 150 | 2 | 300 | 10 | 10 | 10 tohum |
| dataset | medium | 150 | 4 | 600 | 10 | 10 | 10 tohum |
| dataset | medium | 150 | 6 | 900 | 10 | 10 | 10 tohum |
| dataset | medium | 200 | 2 | 400 | 10 | 10 | 10 tohum |
| dataset | medium | 200 | 4 | 800 | 10 | 10 | 10 tohum |
| dataset | medium | 200 | 6 | 1200 | 10 | 10 | 10 tohum |

3'ten az tohumlu hücre: **0/6**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Anneal-Local/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Anneal-TreeAgg/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Anneal-TreeAgg/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Anneal-Trickle/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `DFS-Spanning-Backbone/async` | 60 | 45 | 45 | infeasible=15, ok=45 | ok=45 |
| `DFS-Spanning-Backbone/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `GHS-MST-Backbone/async` | 60 | 45 | 43 | infeasible=15, ok=43, unresolved=2 | ok=43, unresolved=2 |
| `GHS-MST-Backbone/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Greedy-Degree-Backbone/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Greedy-Degree-Backbone/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Greedy-Ratio-Backbone/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Greedy-Ratio-Backbone/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Greedy-Weight-Backbone/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `Greedy-Weight-Backbone/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `MIS-Connector-Backbone/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `MIS-Connector-Backbone/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `MIS-Connector-TreeAgg/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `MIS-Connector-TreeAgg/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `WuLi-Dominating-Bloom/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `WuLi-Dominating-Bloom/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `WuLi-Dominating-Chunked/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `WuLi-Dominating-Chunked/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `WuLi-Dominating-Exact/async` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |
| `WuLi-Dominating-Exact/sync` | 60 | 45 | 44 | infeasible=15, ok=44, unresolved=1 | ok=44, unresolved=1 |

### 4b. Bu k'da KANITLANABİLİR UYGUNSUZ hücreler

Aşağıdaki hücrelerde C=V ile bile kapasite atanamıyor (Hakimi). Burada bir kolun başarısız olması **kol kusuru değildir**; bu satırlar oran ortalamalarının tamamen dışındadır. Matrisi bu k ile koşmak bu hücreleri anlamsız kılar, k büyütülmelidir.

| grup | n | m/n | m | ⌈m/k⌉ |
|---|---|---|---|---|
| medium | 150 | 6 | 900 | 150 |
| medium | 200 | 6 | 1200 | 200 |

Kol başına: uygunsuz örnekte uygunsuzluğu **ilan edemeyen** koşum sayısı `missed_infeasible` sütununda (özet JSON), harcanan slot/tx `infeasible_slots_mean`/`infeasible_tx_mean` içinde.

> **`missed_infeasible` KOLLAR ARASI FARK OKUMAK İÇİN KULLANILAMAZ.** Uygunsuzluk tespiti Faz 4'ün ortak kodundadır, dolayısıyla tespit kusuru bütün kollarda AYNI okunur.

> Ayrıca her kaçırma kusur DEĞİLDİR. Sayma sınırı (m > n·k) ucuzca kanıtlanabilir dejenere sınıfı yakalar; onun dışındaki uygunsuzluk yalnız akışla görülür ve bugünkü HELLO ile sağlam bir YEREL tanık hesaplanamaz, yani düğümün bildirememesi beklenen davranıştır. Kusur sayılabilecek olan `missed_provable_infeasible` sütunudur; `infeasible_not_cheaply_provable` ise kaçırılması normal olan satırları sayar.

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **42** örnek (toplam 45)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 15
- kesin çözüm referansı olan örnek: 0

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 1.0322 | 1.0337 | — | 21537.9 | — |
| `Anneal-Local/sync` | 1.0404 | 1.0423 | — | 23578 | — |
| `Anneal-TreeAgg/async` | 1.0322 | 1.0337 | — | 21537.9 | — |
| `Anneal-TreeAgg/sync` | 1.0404 | 1.0423 | — | 23578 | — |
| `Anneal-Trickle/async` | 1.0666 | 1.0698 | — | 13380.4 | — |
| `DFS-Spanning-Backbone/async` | 1.2945 | 1.3155 | — | 172571 | kendi altkümesinde 1.2945, ortak altkümede 1.3155; fark 0.021 başarısızlık örüntüsünden geliyor |
| `DFS-Spanning-Backbone/sync` | 1.3008 | 1.3151 | — | 334088 | — |
| `GHS-MST-Backbone/async` | 1.209 | 1.2139 | — | 20855.8 | — |
| `GHS-MST-Backbone/sync` | 1.2266 | 1.2374 | — | 32362.2 | — |
| `Greedy-Degree-Backbone/async` | 1.3078 | 1.3224 | — | 9919.98 | — |
| `Greedy-Degree-Backbone/sync` | 1.3078 | 1.3224 | — | 13080.9 | — |
| `Greedy-Ratio-Backbone/async` | 1.3078 | 1.3224 | — | 9920.17 | — |
| `Greedy-Ratio-Backbone/sync` | 1.3078 | 1.3224 | — | 13080.9 | — |
| `Greedy-Weight-Backbone/async` | 1.3078 | 1.3224 | — | 9920.31 | — |
| `Greedy-Weight-Backbone/sync` | 1.3078 | 1.3224 | — | 13080.9 | — |
| `MIS-Connector-Backbone/async` | 1.3075 | 1.3222 | — | 7458.9 | — |
| `MIS-Connector-Backbone/sync` | 1.3075 | 1.3222 | — | 9960.74 | — |
| `MIS-Connector-TreeAgg/async` | 1.3075 | 1.3222 | — | 16404 | — |
| `MIS-Connector-TreeAgg/sync` | 1.3075 | 1.3222 | — | 23094.1 | — |
| `WuLi-Dominating-Bloom/async` | 1.3078 | 1.3225 | — | 7094.67 | — |
| `WuLi-Dominating-Bloom/sync` | 1.3078 | 1.3225 | — | 8888.5 | — |
| `WuLi-Dominating-Chunked/async` | 1.3067 | 1.3213 | — | 8941.67 | — |
| `WuLi-Dominating-Chunked/sync` | 1.3067 | 1.3213 | — | 11665.1 | — |
| `WuLi-Dominating-Exact/async` | 1.3067 | 1.3213 | — | 7094.64 | — |
| `WuLi-Dominating-Exact/sync` | 1.3067 | 1.3213 | — | 8888.74 | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 44 | 0 | 0 | 1 | 0.787 |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 44 | 0 | 0 | 1 | 2.42 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 44 | 0 | 0 | 0.9994 | 0.8709 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 44 | 0 | 0 | 1.0003 | 0.8709 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 44 | 0 | 0 | 0.9994 | 1.043 |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 44 | 0 | 0 | 1 | 2.1941 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 44 | 0 | 0 | 0.9994 | 0.9415 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 44 | 0 | 0 | 1.0003 | 0.9416 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 44 | 0 | 0 | 0.9994 | 1.1077 |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 44 | 0 | 0 | 1 | 0.7176 |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 44 | 0 | 1 | 1.0003 | 0.5169 |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 43 | 1 | 0 | 0.9819 | 0.6372 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 44 | 0 | 0 | 1 | 0.8534 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 44 | 0 | 0 | 1.0009 | 1 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 44 | 0 | 0 | 1 | 1.188 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 44 | 0 | 0 | 1.0009 | 1 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 44 | 0 | 0 | 1 | 1.1724 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 44 | 0 | 0 | 1 | 0.8535 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 44 | 0 | 0 | 0.9991 | 1.1881 |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 44 | 0 | 0 | 0.9991 | 1.1724 |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 44 | 0 | 0 | 1 | 0.8439 |
| `Anneal-Local/sync` | `Anneal-Local/async` | scheduler | 44 | 0 | 0 | 0.9975 | 0.9275 |
| `Anneal-Local/sync` | `Anneal-TreeAgg/sync` | phase5 | 44 | 0 | 0 | 1 | 1 |
| `Anneal-Local/sync` | `Anneal-Trickle/async` | scheduler | 44 | 0 | 0 | 1.0281 | 0.5746 |
| `Anneal-Local/async` | `Anneal-TreeAgg/async` | phase5 | 44 | 0 | 0 | 1 | 1 |
| `Anneal-TreeAgg/sync` | `Anneal-TreeAgg/async` | scheduler | 44 | 0 | 0 | 0.9975 | 0.9275 |
| `Anneal-TreeAgg/async` | `Anneal-Trickle/async` | phase5 | 44 | 0 | 0 | 1.0348 | 0.6215 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 44 | 0 | 0 | 1 | 0.7823 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 44 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 44 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 44 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 44 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 44 | 0 | 0 | 1 | 0.7823 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 44 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 44 | 0 | 0 | 1 | 1 |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 44 | 0 | 0 | 1 | 0.7823 |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

400 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

| durum | satır | ort. slot | ort. tx | örnekler |
|---|---|---|---|---|
| `infeasible` | 375 | 1124.88 | 139525 | n150_m900_s1.txt/Anneal-Local/async, n150_m900_s1.txt/Anneal-Local/sync, n150_m900_s1.txt/Anneal-TreeAgg/async |
| `unresolved` | 25 | 1125.42 | 140053 | n200_m1200_s10.txt/GHS-MST-Backbone/async, n200_m1200_s3.txt/GHS-MST-Backbone/async, n200_m1200_s3.txt/GHS-MST-Backbone/sync |

Çözülemeyen koşum ortalama **1125.4167 slot** harcıyor, başarılı koşum 255.8371; oran **4.4×**. Başarısızlık ucuz değildir ve bu sayı raporun kendisidir.

