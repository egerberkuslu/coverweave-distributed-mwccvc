# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **groups**: medium
- **k**: 6
- **loss**: 0
- **max_ms**: 12000000
- **max_n**: 100
- **max_seeds**: 3
- **mis_nbrs_max**: 64
- **ratios**: 2,4
- **rows**: 240
- **schedulers**: sync,async
- **seconds**: 175.6
- **source**: dataset
- **variants**: MIS-Connector-Backbone,MIS-Connector-TreeAgg,DFS-Spanning-Backbone,GHS-MST-Backbone,WuLi-Dominating-Exact,WuLi-Dominating-Bloom,WuLi-Dominating-Chunked,Greedy-Degree-Backbone,Greedy-Ratio-Backbone,Greedy-Weight-Backbone

## 1b. Girdi bağlılığı

Bütün 12 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **0** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 0 / 0 / 240 |
| kesik koşum (`truncated`) | 0 |
| kopuk girdi (`bad_input`) | 0 |
| kod sürümü (parmak izi) | 26230cea50b4 |

> Bütün satırlar TEK bir kod sürümünden ölçülmüştür.

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
| dataset | medium | 50 | 2 | 100 | 3 | 10 | 3 tohum |
| dataset | medium | 50 | 4 | 200 | 3 | 10 | 3 tohum |
| dataset | medium | 100 | 2 | 200 | 3 | 10 | 3 tohum |
| dataset | medium | 100 | 4 | 400 | 3 | 10 | 3 tohum |

3'ten az tohumlu hücre: **0/4**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `DFS-Spanning-Backbone/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `DFS-Spanning-Backbone/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `GHS-MST-Backbone/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `GHS-MST-Backbone/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `Greedy-Degree-Backbone/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `Greedy-Degree-Backbone/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `Greedy-Ratio-Backbone/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `Greedy-Ratio-Backbone/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `Greedy-Weight-Backbone/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `Greedy-Weight-Backbone/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `MIS-Connector-Backbone/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `MIS-Connector-Backbone/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `MIS-Connector-TreeAgg/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `MIS-Connector-TreeAgg/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `WuLi-Dominating-Bloom/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `WuLi-Dominating-Bloom/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `WuLi-Dominating-Chunked/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `WuLi-Dominating-Chunked/sync` | 12 | 12 | 12 | ok=12 | ok=12 |
| `WuLi-Dominating-Exact/async` | 12 | 12 | 12 | ok=12 | ok=12 |
| `WuLi-Dominating-Exact/sync` | 12 | 12 | 12 | ok=12 | ok=12 |

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **12** örnek (toplam 12)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 0
- kesin çözüm referansı olan örnek: 0

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `DFS-Spanning-Backbone/async` | 1.0948 | 1.0948 | — | 35158.4 | — |
| `DFS-Spanning-Backbone/sync` | 1.0898 | 1.0898 | — | 66707.2 | — |
| `GHS-MST-Backbone/async` | 1.0151 | 1.0151 | — | 5717.5 | — |
| `GHS-MST-Backbone/sync` | 1.0227 | 1.0227 | — | 8909.58 | — |
| `Greedy-Degree-Backbone/async` | 1.1159 | 1.1159 | — | 3701.33 | — |
| `Greedy-Degree-Backbone/sync` | 1.1159 | 1.1159 | — | 4670.42 | — |
| `Greedy-Ratio-Backbone/async` | 1.1159 | 1.1159 | — | 3700.75 | — |
| `Greedy-Ratio-Backbone/sync` | 1.1159 | 1.1159 | — | 4670.42 | — |
| `Greedy-Weight-Backbone/async` | 1.1159 | 1.1159 | — | 3701.33 | — |
| `Greedy-Weight-Backbone/sync` | 1.1159 | 1.1159 | — | 4670.42 | — |
| `MIS-Connector-Backbone/async` | 1.1159 | 1.1159 | — | 2655.42 | — |
| `MIS-Connector-Backbone/sync` | 1.1159 | 1.1159 | — | 3361.17 | — |
| `MIS-Connector-TreeAgg/async` | 1.1159 | 1.1159 | — | 5463.58 | — |
| `MIS-Connector-TreeAgg/sync` | 1.1159 | 1.1159 | — | 8160.33 | — |
| `WuLi-Dominating-Bloom/async` | 1.1141 | 1.1141 | — | 2511.08 | — |
| `WuLi-Dominating-Bloom/sync` | 1.1141 | 1.1141 | — | 2932.83 | — |
| `WuLi-Dominating-Chunked/async` | 1.1125 | 1.1125 | — | 2873.92 | — |
| `WuLi-Dominating-Chunked/sync` | 1.1125 | 1.1125 | — | 3512.92 | — |
| `WuLi-Dominating-Exact/async` | 1.1125 | 1.1125 | — | 2511.08 | — |
| `WuLi-Dominating-Exact/sync` | 1.1125 | 1.1125 | — | 2932.83 | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 12 | 0 | 0 | 1 | 0.8076 |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 12 | 0 | 0 | 1 | 2.334 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 12 | 0 | 0 | 0.997 | 0.8674 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 12 | 0 | 0 | 0.9985 | 0.8674 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 12 | 0 | 0 | 0.997 | 1.0068 |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 12 | 0 | 0 | 1 | 2.014 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 12 | 0 | 0 | 0.997 | 0.9436 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 12 | 0 | 0 | 0.9985 | 0.9436 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 12 | 0 | 0 | 0.997 | 1.0495 |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 12 | 0 | 0 | 1 | 0.7 |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 12 | 0 | 0 | 1.0046 | 0.5332 |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 12 | 0 | 0 | 0.9935 | 0.6503 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 12 | 0 | 0 | 1 | 0.8796 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 12 | 0 | 0 | 1.0015 | 1 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 12 | 0 | 0 | 1 | 1.1564 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 12 | 0 | 0 | 1.0015 | 1 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 12 | 0 | 0 | 1 | 1.1115 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 12 | 0 | 0 | 1 | 0.8796 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 12 | 0 | 0 | 0.9985 | 1.1564 |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 12 | 0 | 0 | 0.9985 | 1.1115 |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 12 | 0 | 0 | 1 | 0.8489 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 12 | 0 | 0 | 1 | 0.7995 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 12 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 12 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 12 | 0 | 0 | 1 | 0.9999 |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 12 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 12 | 0 | 0 | 1 | 0.7994 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 12 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 12 | 0 | 0 | 1 | 1.0001 |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 12 | 0 | 0 | 1 | 0.7995 |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

0 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

