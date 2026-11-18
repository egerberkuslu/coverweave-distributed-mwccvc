# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **groups**: medium
- **k**: 6
- **loss**: 0
- **max_ms**: 8000000
- **max_n**: 50
- **max_seeds**: 6
- **mis_nbrs_max**: 64
- **ratios**: 2,4,6
- **rows**: 450
- **schedulers**: sync,async
- **seconds**: 520
- **source**: dataset
- **variants**: MIS-Connector-Backbone,MIS-Connector-TreeAgg,DFS-Spanning-Backbone,GHS-MST-Backbone,WuLi-Dominating-Exact,WuLi-Dominating-Bloom,WuLi-Dominating-Chunked,Anneal-Local,Anneal-TreeAgg,Anneal-Trickle,Greedy-Degree-Backbone,Greedy-Ratio-Backbone,Greedy-Weight-Backbone

## 1b. Girdi bağlılığı

Bütün 18 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **0** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 85 / 5 / 360 |
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
| dataset | medium | 50 | 2 | 100 | 6 | 10 | 6 tohum |
| dataset | medium | 50 | 4 | 200 | 6 | 10 | 6 tohum |
| dataset | medium | 50 | 6 | 300 | 6 | 10 | 6 tohum |

3'ten az tohumlu hücre: **0/3**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Anneal-Local/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Anneal-TreeAgg/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Anneal-TreeAgg/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Anneal-Trickle/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `DFS-Spanning-Backbone/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `DFS-Spanning-Backbone/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `GHS-MST-Backbone/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `GHS-MST-Backbone/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Greedy-Degree-Backbone/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Greedy-Degree-Backbone/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Greedy-Ratio-Backbone/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Greedy-Ratio-Backbone/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Greedy-Weight-Backbone/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `Greedy-Weight-Backbone/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `MIS-Connector-Backbone/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `MIS-Connector-Backbone/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `MIS-Connector-TreeAgg/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `MIS-Connector-TreeAgg/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `WuLi-Dominating-Bloom/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `WuLi-Dominating-Bloom/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `WuLi-Dominating-Chunked/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `WuLi-Dominating-Chunked/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `WuLi-Dominating-Exact/async` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |
| `WuLi-Dominating-Exact/sync` | 18 | 17 | 17 | infeasible=1, ok=17 | ok=17 |

### 4b. Bu k'da KANITLANABİLİR UYGUNSUZ hücreler

Aşağıdaki hücrelerde C=V ile bile kapasite atanamıyor (Hakimi). Burada bir kolun başarısız olması **kol kusuru değildir**; bu satırlar oran ortalamalarının tamamen dışındadır. Matrisi bu k ile koşmak bu hücreleri anlamsız kılar, k büyütülmelidir.

| grup | n | m/n | m | ⌈m/k⌉ |
|---|---|---|---|---|
| medium | 50 | 6 | 300 | 50 |

Kol başına: uygunsuz örnekte uygunsuzluğu **ilan edemeyen** koşum sayısı `missed_infeasible` sütununda (özet JSON), harcanan slot/tx `infeasible_slots_mean`/`infeasible_tx_mean` içinde.

> **`missed_infeasible` KOLLAR ARASI FARK OKUMAK İÇİN KULLANILAMAZ.** Uygunsuzluk tespiti Faz 4'ün ortak kodundadır, dolayısıyla tespit kusuru bütün kollarda AYNI okunur.

> Ayrıca her kaçırma kusur DEĞİLDİR. Sayma sınırı (m > n·k) ucuzca kanıtlanabilir dejenere sınıfı yakalar; onun dışındaki uygunsuzluk yalnız akışla görülür ve bugünkü HELLO ile sağlam bir YEREL tanık hesaplanamaz, yani düğümün bildirememesi beklenen davranıştır. Kusur sayılabilecek olan `missed_provable_infeasible` sütunudur; `infeasible_not_cheaply_provable` ise kaçırılması normal olan satırları sayar.

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **17** örnek (toplam 17)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 1
- kesin çözüm referansı olan örnek: 0

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 1.0576 | 1.0576 | — | 7693.94 | — |
| `Anneal-Local/sync` | 1.0373 | 1.0373 | — | 8860.76 | — |
| `Anneal-TreeAgg/async` | 1.0576 | 1.0576 | — | 7693.94 | — |
| `Anneal-TreeAgg/sync` | 1.0373 | 1.0373 | — | 8860.76 | — |
| `Anneal-Trickle/async` | 1.0715 | 1.0715 | — | 4947.18 | — |
| `DFS-Spanning-Backbone/async` | 1.2654 | 1.2654 | — | 22595.4 | — |
| `DFS-Spanning-Backbone/sync` | 1.2589 | 1.2589 | — | 41561.6 | — |
| `GHS-MST-Backbone/async` | 1.2081 | 1.2081 | — | 8087.18 | — |
| `GHS-MST-Backbone/sync` | 1.2083 | 1.2083 | — | 10285.7 | — |
| `Greedy-Degree-Backbone/async` | 1.2822 | 1.2822 | — | 4688.06 | — |
| `Greedy-Degree-Backbone/sync` | 1.2837 | 1.2837 | — | 6318.06 | — |
| `Greedy-Ratio-Backbone/async` | 1.2822 | 1.2822 | — | 4601.94 | — |
| `Greedy-Ratio-Backbone/sync` | 1.2837 | 1.2837 | — | 6318.06 | — |
| `Greedy-Weight-Backbone/async` | 1.2822 | 1.2822 | — | 4601.94 | — |
| `Greedy-Weight-Backbone/sync` | 1.2837 | 1.2837 | — | 6318.06 | — |
| `MIS-Connector-Backbone/async` | 1.2822 | 1.2822 | — | 4193.12 | — |
| `MIS-Connector-Backbone/sync` | 1.2837 | 1.2837 | — | 5994.47 | — |
| `MIS-Connector-TreeAgg/async` | 1.2822 | 1.2822 | — | 7691.18 | — |
| `MIS-Connector-TreeAgg/sync` | 1.2837 | 1.2837 | — | 10047.7 | — |
| `WuLi-Dominating-Bloom/async` | 1.2877 | 1.2877 | — | 3594.06 | — |
| `WuLi-Dominating-Bloom/sync` | 1.2877 | 1.2877 | — | 4641.53 | — |
| `WuLi-Dominating-Chunked/async` | 1.2869 | 1.2869 | — | 5347.35 | — |
| `WuLi-Dominating-Chunked/sync` | 1.2869 | 1.2869 | — | 7162.88 | — |
| `WuLi-Dominating-Exact/async` | 1.2869 | 1.2869 | — | 3594.06 | — |
| `WuLi-Dominating-Exact/sync` | 1.2869 | 1.2869 | — | 4641.53 | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 17 | 0 | 0 | 0.9989 | 0.7835 |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 17 | 0 | 0 | 1 | 1.9788 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 17 | 0 | 0 | 1.0023 | 0.8411 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 17 | 0 | 0 | 1.0027 | 0.8411 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 17 | 0 | 0 | 1.0023 | 1.095 |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 17 | 0 | 0 | 1 | 1.8988 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 17 | 0 | 0 | 1.0034 | 0.9205 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 17 | 0 | 0 | 1.0039 | 0.9205 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 17 | 0 | 0 | 1.0034 | 1.155 |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 17 | 0 | 0 | 0.9989 | 0.754 |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 17 | 0 | 0 | 1.005 | 0.5449 |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 17 | 0 | 0 | 1.0005 | 0.7283 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 17 | 0 | 0 | 1 | 0.8531 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 17 | 0 | 0 | 1.0005 | 1 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 17 | 0 | 0 | 1 | 1.3109 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 17 | 0 | 0 | 1.0005 | 1 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 17 | 0 | 0 | 1 | 1.266 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 17 | 0 | 0 | 1 | 0.8531 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 17 | 0 | 0 | 0.9995 | 1.3109 |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 17 | 0 | 0 | 0.9995 | 1.266 |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 17 | 0 | 0 | 1 | 0.8248 |
| `Anneal-Local/sync` | `Anneal-Local/async` | scheduler | 17 | 0 | 0 | 1.0261 | 0.9141 |
| `Anneal-Local/sync` | `Anneal-TreeAgg/sync` | phase5 | 17 | 0 | 0 | 1 | 1 |
| `Anneal-Local/sync` | `Anneal-Trickle/async` | scheduler | 17 | 0 | 0 | 1.0378 | 0.5764 |
| `Anneal-Local/async` | `Anneal-TreeAgg/async` | phase5 | 17 | 0 | 0 | 1 | 1 |
| `Anneal-TreeAgg/sync` | `Anneal-TreeAgg/async` | scheduler | 17 | 0 | 0 | 1.0261 | 0.9141 |
| `Anneal-TreeAgg/async` | `Anneal-Trickle/async` | phase5 | 17 | 0 | 0 | 1.0158 | 0.6329 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 17 | 0 | 0 | 0.9989 | 0.7878 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 17 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 17 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 17 | 0 | 0 | 1 | 0.9917 |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 17 | 0 | 0 | 1 | 0.9917 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 17 | 0 | 0 | 0.9989 | 0.7812 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 17 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 17 | 0 | 0 | 1 | 1 |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 17 | 0 | 0 | 0.9989 | 0.7812 |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

25 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

| durum | satır | ort. slot | ort. tx | örnekler |
|---|---|---|---|---|
| `infeasible` | 25 | 778.5 | 32664.1 | n50_m300_s6.txt/Anneal-Local/async, n50_m300_s6.txt/Anneal-Local/sync, n50_m300_s6.txt/Anneal-TreeAgg/async |
