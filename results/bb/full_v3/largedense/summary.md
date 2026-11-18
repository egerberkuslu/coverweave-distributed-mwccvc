# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **code_fingerprint**: 798b4393cb4f/bebb0f917410
- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **driver**: scratchpad/stage_run.py (cells enumerated directly; matrix.py ratio tuples stop at 8)
- **fingerprint_by_arm_set**: {'798b4393cb4f': ['Anneal-Local', 'Anneal-TreeAgg', 'Anneal-Trickle', 'DFS-Spanning-Backbone', 'Greedy-Degree-Backbone', 'Greedy-Ratio-Backbone', 'Greedy-Weight-Backbone', 'MIS-Connector-Backbone', 'MIS-Connector-TreeAgg', 'WuLi-Dominating-Bloom', 'WuLi-Dominating-Chunked', 'WuLi-Dominating-Exact'], 'bebb0f917410': ['GHS-MST-Backbone']}
- **groups**: medium
- **k**: 6
- **loss**: 0
- **max_ms**: 22000000
- **max_seeds**: 3
- **mis_nbrs_max**: 64
- **ns**: 150,200
- **ratios**: 8,10
- **rows**: 300
- **schedulers**: sync,async
- **seconds**: 35848.6
- **shards**: 20
- **source**: dataset
- **variants**: MIS-Connector-Backbone,MIS-Connector-TreeAgg,DFS-Spanning-Backbone,GHS-MST-Backbone,WuLi-Dominating-Exact,WuLi-Dominating-Bloom,WuLi-Dominating-Chunked,Anneal-Local,Anneal-TreeAgg,Anneal-Trickle,Greedy-Degree-Backbone,Greedy-Ratio-Backbone,Greedy-Weight-Backbone
- **wall_note**: seconds is summed shard CPU wall, not elapsed time; shards ran in parallel

## 1b. Girdi bağlılığı

Bütün 12 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **0** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 0 / 14 / 286 |
| kesik koşum (`truncated`) | 0 |
| kopuk girdi (`bad_input`) | 0 |
| kod sürümü (parmak izi) | 798b4393cb4f/bebb0f917410 |

> **UYARI: bu CSV birden çok KOD SÜRÜMÜNDEN ölçülmüş satır içeriyor** (2 ayrı parmak izi). Süpürme sürerken depoya yama inmiş demektir; satırlar aynı tabloda toplanamaz, süpürme yeniden koşulmalıdır.

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
| dataset | medium | 150 | 8 | 1200 | 3 | 10 | 3 tohum |
| dataset | medium | 150 | 10 | 1500 | 3 | 10 | 3 tohum |
| dataset | medium | 200 | 8 | 1600 | 3 | 10 | 3 tohum |
| dataset | medium | 200 | 10 | 2000 | 3 | 10 | 3 tohum |

3'ten az tohumlu hücre: **0/4**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 12 | 0 | 0 | infeasible=3, skipped=9 |  |
| `Anneal-Local/sync` | 12 | 0 | 0 | infeasible=3, skipped=9 |  |
| `Anneal-TreeAgg/async` | 12 | 0 | 0 | infeasible=3, skipped=9 |  |
| `Anneal-TreeAgg/sync` | 12 | 0 | 0 | infeasible=3, skipped=9 |  |
| `Anneal-Trickle/async` | 12 | 0 | 0 | infeasible=2, skipped=10 |  |
| `DFS-Spanning-Backbone/async` | 12 | 0 | 0 | infeasible=10, skipped=2 |  |
| `DFS-Spanning-Backbone/sync` | 12 | 0 | 0 | infeasible=10, skipped=2 |  |
| `GHS-MST-Backbone/async` | 12 | 0 | 0 | infeasible=12 |  |
| `GHS-MST-Backbone/sync` | 12 | 0 | 0 | infeasible=12 |  |
| `Greedy-Degree-Backbone/async` | 12 | 0 | 0 | infeasible=1, skipped=11 |  |
| `Greedy-Degree-Backbone/sync` | 12 | 0 | 0 | infeasible=1, skipped=11 |  |
| `Greedy-Ratio-Backbone/async` | 12 | 0 | 0 | skipped=12 |  |
| `Greedy-Ratio-Backbone/sync` | 12 | 0 | 0 | skipped=12 |  |
| `Greedy-Weight-Backbone/async` | 12 | 0 | 0 | skipped=12 |  |
| `Greedy-Weight-Backbone/sync` | 12 | 0 | 0 | skipped=12 |  |
| `MIS-Connector-Backbone/async` | 12 | 0 | 0 | infeasible=10, skipped=2 |  |
| `MIS-Connector-Backbone/sync` | 12 | 0 | 0 | infeasible=10, skipped=2 |  |
| `MIS-Connector-TreeAgg/async` | 12 | 0 | 0 | infeasible=10, skipped=2 |  |
| `MIS-Connector-TreeAgg/sync` | 12 | 0 | 0 | infeasible=10, skipped=2 |  |
| `WuLi-Dominating-Bloom/async` | 12 | 0 | 0 | infeasible=9, skipped=3 |  |
| `WuLi-Dominating-Bloom/sync` | 12 | 0 | 0 | infeasible=9, skipped=3 |  |
| `WuLi-Dominating-Chunked/async` | 12 | 0 | 0 | infeasible=5, skipped=7 |  |
| `WuLi-Dominating-Chunked/sync` | 12 | 0 | 0 | infeasible=9, skipped=3 |  |
| `WuLi-Dominating-Exact/async` | 12 | 0 | 0 | infeasible=9, skipped=3 |  |
| `WuLi-Dominating-Exact/sync` | 12 | 0 | 0 | infeasible=9, skipped=3 |  |

### 4b. Bu k'da KANITLANABİLİR UYGUNSUZ hücreler

Aşağıdaki hücrelerde C=V ile bile kapasite atanamıyor (Hakimi). Burada bir kolun başarısız olması **kol kusuru değildir**; bu satırlar oran ortalamalarının tamamen dışındadır. Matrisi bu k ile koşmak bu hücreleri anlamsız kılar, k büyütülmelidir.

| grup | n | m/n | m | ⌈m/k⌉ |
|---|---|---|---|---|
| medium | 150 | 8 | 1200 | 200 |
| medium | 150 | 10 | 1500 | 250 |
| medium | 200 | 8 | 1600 | 267 |
| medium | 200 | 10 | 2000 | 334 |

Kol başına: uygunsuz örnekte uygunsuzluğu **ilan edemeyen** koşum sayısı `missed_infeasible` sütununda (özet JSON), harcanan slot/tx `infeasible_slots_mean`/`infeasible_tx_mean` içinde.

> **`missed_infeasible` KOLLAR ARASI FARK OKUMAK İÇİN KULLANILAMAZ.** Uygunsuzluk tespiti Faz 4'ün ortak kodundadır, dolayısıyla tespit kusuru bütün kollarda AYNI okunur.

> Ayrıca her kaçırma kusur DEĞİLDİR. Sayma sınırı (m > n·k) ucuzca kanıtlanabilir dejenere sınıfı yakalar; onun dışındaki uygunsuzluk yalnız akışla görülür ve bugünkü HELLO ile sağlam bir YEREL tanık hesaplanamaz, yani düğümün bildirememesi beklenen davranıştır. Kusur sayılabilecek olan `missed_provable_infeasible` sütunudur; `infeasible_not_cheaply_provable` ise kaçırılması normal olan satırları sayar.

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **0** örnek (toplam 0)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 12
- kesin çözüm referansı olan örnek: 0

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `Anneal-Local/async` | — | — | — | — | — |
| `Anneal-Local/sync` | — | — | — | — | — |
| `Anneal-TreeAgg/async` | — | — | — | — | — |
| `Anneal-TreeAgg/sync` | — | — | — | — | — |
| `Anneal-Trickle/async` | — | — | — | — | — |
| `DFS-Spanning-Backbone/async` | — | — | — | — | — |
| `DFS-Spanning-Backbone/sync` | — | — | — | — | — |
| `GHS-MST-Backbone/async` | — | — | — | — | — |
| `GHS-MST-Backbone/sync` | — | — | — | — | — |
| `Greedy-Degree-Backbone/async` | — | — | — | — | — |
| `Greedy-Degree-Backbone/sync` | — | — | — | — | — |
| `Greedy-Ratio-Backbone/async` | — | — | — | — | — |
| `Greedy-Ratio-Backbone/sync` | — | — | — | — | — |
| `Greedy-Weight-Backbone/async` | — | — | — | — | — |
| `Greedy-Weight-Backbone/sync` | — | — | — | — | — |
| `MIS-Connector-Backbone/async` | — | — | — | — | — |
| `MIS-Connector-Backbone/sync` | — | — | — | — | — |
| `MIS-Connector-TreeAgg/async` | — | — | — | — | — |
| `MIS-Connector-TreeAgg/sync` | — | — | — | — | — |
| `WuLi-Dominating-Bloom/async` | — | — | — | — | — |
| `WuLi-Dominating-Bloom/sync` | — | — | — | — | — |
| `WuLi-Dominating-Chunked/async` | — | — | — | — | — |
| `WuLi-Dominating-Chunked/sync` | — | — | — | — | — |
| `WuLi-Dominating-Exact/async` | — | — | — | — | — |
| `WuLi-Dominating-Exact/sync` | — | — | — | — | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 0 | 0 | 0 | — | — |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 0 | 0 | 0 | — | — |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 0 | 0 | 0 | — | — |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 0 | 0 | 0 | — | — |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 0 | 0 | 0 | — | — |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 0 | 0 | 0 | — | — |
| `Anneal-Local/sync` | `Anneal-Local/async` | scheduler | 0 | 0 | 0 | — | — |
| `Anneal-Local/sync` | `Anneal-TreeAgg/sync` | phase5 | 0 | 0 | 0 | — | — |
| `Anneal-Local/sync` | `Anneal-Trickle/async` | scheduler | 0 | 0 | 0 | — | — |
| `Anneal-Local/async` | `Anneal-TreeAgg/async` | phase5 | 0 | 0 | 0 | — | — |
| `Anneal-TreeAgg/sync` | `Anneal-TreeAgg/async` | scheduler | 0 | 0 | 0 | — | — |
| `Anneal-TreeAgg/async` | `Anneal-Trickle/async` | phase5 | 0 | 0 | 0 | — | — |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 0 | 0 | 0 | — | — |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 0 | 0 | 0 | — | — |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 0 | 0 | 0 | — | — |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 0 | 0 | 0 | — | — |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 0 | 0 | 0 | — | — |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 0 | 0 | 0 | — | — |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 0 | 0 | 0 | — | — |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 0 | 0 | 0 | — | — |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 0 | 0 | 0 | — | — |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

300 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

| durum | satır | ort. slot | ort. tx | örnekler |
|---|---|---|---|---|
| `infeasible` | 150 | 3451.95 | 697964 | n150_m1200_s1.txt/Anneal-Local/async, n150_m1200_s1.txt/Anneal-Local/sync, n150_m1200_s1.txt/Anneal-TreeAgg/async |
| `skipped` | 150 | — | — | n150_m1200_s1.txt/Greedy-Ratio-Backbone/async, n150_m1200_s1.txt/Greedy-Ratio-Backbone/sync, n150_m1200_s1.txt/Greedy-Weight-Backbone/async |
