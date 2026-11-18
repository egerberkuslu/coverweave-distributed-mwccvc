# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **groups**: small
- **k**: 6
- **loss**: 0
- **max_ms**: 4000000
- **max_n**: —
- **max_seeds**: 3
- **mis_nbrs_max**: 64
- **ratios**: hepsi
- **rows**: 975
- **schedulers**: sync,async
- **seconds**: 1840
- **source**: dataset
- **variants**: MIS-Connector-Backbone,MIS-Connector-TreeAgg,DFS-Spanning-Backbone,GHS-MST-Backbone,WuLi-Dominating-Exact,WuLi-Dominating-Bloom,WuLi-Dominating-Chunked,Anneal-Local,Anneal-TreeAgg,Anneal-Trickle,Greedy-Degree-Backbone,Greedy-Ratio-Backbone,Greedy-Weight-Backbone

## 1b. Girdi bağlılığı

Bütün 39 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **0** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 165 / 30 / 780 |
| kesik koşum (`truncated`) | 0 |
| kopuk girdi (`bad_input`) | 0 |
| kod sürümü (parmak izi) | d507eeec7778 |

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
| dataset | small | 10 | 2 | 20 | 3 | 10 | 3 tohum |
| dataset | small | 10 | 4 | 40 | 3 | 10 | 3 tohum |
| dataset | small | 15 | 2 | 30 | 3 | 10 | 3 tohum |
| dataset | small | 15 | 4 | 60 | 3 | 10 | 3 tohum |
| dataset | small | 15 | 6 | 90 | 3 | 10 | 3 tohum |
| dataset | small | 20 | 2 | 40 | 3 | 10 | 3 tohum |
| dataset | small | 20 | 4 | 80 | 3 | 10 | 3 tohum |
| dataset | small | 20 | 6 | 120 | 3 | 10 | 3 tohum |
| dataset | small | 20 | 8 | 160 | 3 | 10 | 3 tohum |
| dataset | small | 25 | 2 | 50 | 3 | 10 | 3 tohum |
| dataset | small | 25 | 4 | 100 | 3 | 10 | 3 tohum |
| dataset | small | 25 | 6 | 150 | 3 | 10 | 3 tohum |
| dataset | small | 25 | 8 | 200 | 3 | 10 | 3 tohum |

3'ten az tohumlu hücre: **0/13**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Anneal-Local/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Anneal-TreeAgg/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Anneal-TreeAgg/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Anneal-Trickle/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `DFS-Spanning-Backbone/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `DFS-Spanning-Backbone/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `GHS-MST-Backbone/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `GHS-MST-Backbone/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Greedy-Degree-Backbone/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Greedy-Degree-Backbone/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Greedy-Ratio-Backbone/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Greedy-Ratio-Backbone/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Greedy-Weight-Backbone/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `Greedy-Weight-Backbone/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `MIS-Connector-Backbone/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `MIS-Connector-Backbone/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `MIS-Connector-TreeAgg/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `MIS-Connector-TreeAgg/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `WuLi-Dominating-Bloom/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `WuLi-Dominating-Bloom/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `WuLi-Dominating-Chunked/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `WuLi-Dominating-Chunked/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `WuLi-Dominating-Exact/async` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |
| `WuLi-Dominating-Exact/sync` | 39 | 33 | 33 | infeasible=6, ok=33 | ok=33 |

### 4b. Bu k'da KANITLANABİLİR UYGUNSUZ hücreler

Aşağıdaki hücrelerde C=V ile bile kapasite atanamıyor (Hakimi). Burada bir kolun başarısız olması **kol kusuru değildir**; bu satırlar oran ortalamalarının tamamen dışındadır. Matrisi bu k ile koşmak bu hücreleri anlamsız kılar, k büyütülmelidir.

| grup | n | m/n | m | ⌈m/k⌉ |
|---|---|---|---|---|
| small | 20 | 8 | 160 | 27 |
| small | 25 | 8 | 200 | 34 |

Kol başına: uygunsuz örnekte uygunsuzluğu **ilan edemeyen** koşum sayısı `missed_infeasible` sütununda (özet JSON), harcanan slot/tx `infeasible_slots_mean`/`infeasible_tx_mean` içinde.

> **`missed_infeasible` KOLLAR ARASI FARK OKUMAK İÇİN KULLANILAMAZ.** Uygunsuzluk tespiti Faz 4'ün ortak kodundadır, dolayısıyla tespit kusuru bütün kollarda AYNI okunur.

> Ayrıca her kaçırma kusur DEĞİLDİR. Sayma sınırı (m > n·k) ucuzca kanıtlanabilir dejenere sınıfı yakalar; onun dışındaki uygunsuzluk yalnız akışla görülür ve bugünkü HELLO ile sağlam bir YEREL tanık hesaplanamaz, yani düğümün bildirememesi beklenen davranıştır. Kusur sayılabilecek olan `missed_provable_infeasible` sütunudur; `infeasible_not_cheaply_provable` ise kaçırılması normal olan satırları sayar.

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **33** örnek (toplam 33)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 6
- kesin çözüm referansı olan örnek: 15

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 1.0963 | 1.0963 | 1.1719 | 2662.09 | — |
| `Anneal-Local/sync` | 1.0831 | 1.0831 | 1.1782 | 2933.91 | — |
| `Anneal-TreeAgg/async` | 1.0963 | 1.0963 | 1.1719 | 2662.09 | — |
| `Anneal-TreeAgg/sync` | 1.0831 | 1.0831 | 1.1782 | 2933.91 | — |
| `Anneal-Trickle/async` | 1.0858 | 1.0858 | 1.1664 | 1701.24 | — |
| `DFS-Spanning-Backbone/async` | 1.2416 | 1.2416 | 1.303 | 4480.06 | — |
| `DFS-Spanning-Backbone/sync` | 1.2502 | 1.2502 | 1.3215 | 7267.64 | — |
| `GHS-MST-Backbone/async` | 1.0998 | 1.0998 | 1.1651 | 2867.79 | — |
| `GHS-MST-Backbone/sync` | 1.1343 | 1.1343 | 1.2054 | 3146.91 | — |
| `Greedy-Degree-Backbone/async` | 1.2601 | 1.2601 | 1.3533 | 2115.09 | — |
| `Greedy-Degree-Backbone/sync` | 1.2803 | 1.2803 | 1.3811 | 2454.27 | — |
| `Greedy-Ratio-Backbone/async` | 1.2674 | 1.2674 | 1.3665 | 1966.03 | — |
| `Greedy-Ratio-Backbone/sync` | 1.2886 | 1.2886 | 1.3938 | 2160.33 | — |
| `Greedy-Weight-Backbone/async` | 1.2666 | 1.2666 | 1.3644 | 1774.7 | — |
| `Greedy-Weight-Backbone/sync` | 1.2884 | 1.2884 | 1.3831 | 1919.39 | — |
| `MIS-Connector-Backbone/async` | 1.2143 | 1.2143 | 1.2953 | 1844.76 | — |
| `MIS-Connector-Backbone/sync` | 1.2276 | 1.2276 | 1.301 | 2204.18 | — |
| `MIS-Connector-TreeAgg/async` | 1.2143 | 1.2143 | 1.2953 | 2166.7 | — |
| `MIS-Connector-TreeAgg/sync` | 1.2276 | 1.2276 | 1.301 | 2599.58 | — |
| `WuLi-Dominating-Bloom/async` | 1.3389 | 1.3389 | 1.4557 | 1115.39 | — |
| `WuLi-Dominating-Bloom/sync` | 1.3389 | 1.3389 | 1.4557 | 1397.36 | — |
| `WuLi-Dominating-Chunked/async` | 1.288 | 1.288 | 1.3633 | 2825.36 | — |
| `WuLi-Dominating-Chunked/sync` | 1.2907 | 1.2907 | 1.3692 | 3354.33 | — |
| `WuLi-Dominating-Exact/async` | 1.288 | 1.288 | 1.3633 | 1901.76 | — |
| `WuLi-Dominating-Exact/sync` | 1.2907 | 1.2907 | 1.3692 | 2160.7 | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 33 | 0 | 0 | 0.9892 | 0.864 |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 33 | 0 | 0 | 1 | 1.403 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 33 | 0 | 0 | 1.0522 | 0.9336 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 33 | 0 | 0 | 1.0959 | 0.8306 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 33 | 0 | 0 | 1.0522 | 1.2194 |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 33 | 0 | 0 | 1 | 1.3496 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 33 | 0 | 0 | 1.0634 | 1.0212 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 33 | 0 | 0 | 1.1099 | 0.8745 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 33 | 0 | 0 | 1.0634 | 1.2809 |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 33 | 0 | 0 | 0.9892 | 0.8356 |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 33 | 0 | 0 | 0.9942 | 0.6123 |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 33 | 0 | 0 | 0.9732 | 0.8095 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 33 | 0 | 0 | 0.9981 | 0.9227 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 33 | 0 | 0 | 1.0415 | 0.9162 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 33 | 0 | 0 | 1 | 1.2864 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 33 | 0 | 0 | 1.0437 | 0.8799 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 33 | 0 | 0 | 1 | 1.2307 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 33 | 0 | 0 | 1 | 0.8937 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 33 | 0 | 0 | 0.9651 | 1.6632 |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 33 | 0 | 0 | 0.9633 | 1.7095 |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 33 | 0 | 0 | 0.9981 | 0.8869 |
| `Anneal-Local/sync` | `Anneal-Local/async` | scheduler | 33 | 0 | 0 | 1.0221 | 0.9488 |
| `Anneal-Local/sync` | `Anneal-TreeAgg/sync` | phase5 | 33 | 0 | 0 | 1 | 1 |
| `Anneal-Local/sync` | `Anneal-Trickle/async` | scheduler | 33 | 0 | 0 | 1.0153 | 0.5947 |
| `Anneal-Local/async` | `Anneal-TreeAgg/async` | phase5 | 33 | 0 | 0 | 1 | 1 |
| `Anneal-TreeAgg/sync` | `Anneal-TreeAgg/async` | scheduler | 33 | 0 | 0 | 1.0221 | 0.9488 |
| `Anneal-TreeAgg/async` | `Anneal-Trickle/async` | phase5 | 33 | 0 | 0 | 0.9937 | 0.6278 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 33 | 0 | 0 | 0.9848 | 0.8533 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 33 | 0 | 0 | 1.0082 | 0.9625 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 33 | 0 | 0 | 1.0077 | 0.906 |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 33 | 0 | 0 | 1.006 | 0.9879 |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 33 | 0 | 0 | 1.0053 | 0.9363 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 33 | 0 | 0 | 0.9844 | 0.8696 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 33 | 0 | 0 | 0.9999 | 0.9585 |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 33 | 0 | 0 | 0.9993 | 0.9545 |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 33 | 0 | 0 | 0.984 | 0.8807 |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

150 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

| durum | satır | ort. slot | ort. tx | örnekler |
|---|---|---|---|---|
| `infeasible` | 150 | 1653.4 | 54300.2 | n20_m160_s1.txt/Anneal-Local/async, n20_m160_s1.txt/Anneal-Local/sync, n20_m160_s1.txt/Anneal-TreeAgg/async |
