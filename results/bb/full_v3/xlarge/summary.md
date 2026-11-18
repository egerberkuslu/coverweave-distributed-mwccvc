# BB-CVC süpürme özeti

## 1. Koşum künyesi

- **anneal_replacement**: 60 rows replaced; the originals are at _archive/xlarge_anneal_before_107_rows.csv
- **code_fingerprint**: 798b4393cb4f/be8a9f9c1e43/bebb0f917410
- **dataset_dir**: /home/ege/Desktop/MDS_SKYFABRIC/data/DagdevirenDataset
- **fingerprint_roles**: {'798b4393cb4f': 'measured on the first pass, non-annealing arms', 'bebb0f917410': 'GHS-MST-Backbone, plus rows re-run after being skipped', 'be8a9f9c1e43': 'the three annealing arms, re-measured after the §107 fix'}
- **k**: 6
- **loss**: 0
- **rows**: 300
- **source**: dataset
- **stage**: xlarge

## 1b. Girdi bağlılığı

Bütün 12 örnek **bağlı** (brief §1). Kopuk çizgede ölçüm yapılmadı.

## 1c. Çapraz denetim karnesi

Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey bulmadığını değil, koşmadığını da anlatabilirdi.

| denetim | sonuç |
|---|---|
| yanlış başarı (`contradiction`) | **0** |
| beyan-doğrulayıcı uyuşmazlığı | **0** |
| iz-çözüm uyuşmazlığı | **20** |
| iz: uyumlu / uygunsuzda n-a / izsiz | 40 / 0 / 240 |
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
| dataset | large | 250 | 2 | 500 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 250 | 4 | 1000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 250 | 6 | 1500 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 500 | 2 | 1000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 500 | 4 | 2000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 500 | 6 | 3000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 750 | 2 | 1500 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 750 | 4 | 3000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 750 | 6 | 4500 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 1000 | 2 | 2000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 1000 | 4 | 4000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |
| dataset | large | 1000 | 6 | 6000 | 1 | 1 | TEK KOŞUM (ortalama denemez) |

3'ten az tohumlu hücre: **12/12**.

## 4. Kol envanteri ve durum dağılımı

Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). `unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı slot/tx'iyle birlikte CSV'de durur.

`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız çözümü olmayan örneklerde düşmüş demektir.

| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 12 | 12 | 8 | infeasible=4, ok=8 | infeasible=4, ok=8 |
| `Anneal-Local/sync` | 12 | 12 | 8 | infeasible=4, ok=8 | infeasible=4, ok=8 |
| `Anneal-TreeAgg/async` | 12 | 12 | 8 | infeasible=4, ok=8 | infeasible=4, ok=8 |
| `Anneal-TreeAgg/sync` | 12 | 12 | 8 | infeasible=4, ok=8 | infeasible=4, ok=8 |
| `Anneal-Trickle/async` | 12 | 12 | 8 | infeasible=4, ok=8 | infeasible=4, ok=8 |
| `DFS-Spanning-Backbone/async` | 12 | 12 | 8 | infeasible=2, ok=8, skipped=2 | infeasible=2, ok=8, skipped=2 |
| `DFS-Spanning-Backbone/sync` | 12 | 12 | 8 | infeasible=3, ok=8, skipped=1 | infeasible=3, ok=8, skipped=1 |
| `GHS-MST-Backbone/async` | 12 | 12 | 8 | infeasible=4, ok=8 | infeasible=4, ok=8 |
| `GHS-MST-Backbone/sync` | 12 | 12 | 8 | infeasible=4, ok=8 | infeasible=4, ok=8 |
| `Greedy-Degree-Backbone/async` | 12 | 12 | 8 | infeasible=1, ok=8, skipped=3 | infeasible=1, ok=8, skipped=3 |
| `Greedy-Degree-Backbone/sync` | 12 | 12 | 8 | infeasible=1, ok=8, skipped=3 | infeasible=1, ok=8, skipped=3 |
| `Greedy-Ratio-Backbone/async` | 12 | 12 | 8 | infeasible=1, ok=8, skipped=3 | infeasible=1, ok=8, skipped=3 |
| `Greedy-Ratio-Backbone/sync` | 12 | 12 | 8 | infeasible=1, ok=8, skipped=3 | infeasible=1, ok=8, skipped=3 |
| `Greedy-Weight-Backbone/async` | 12 | 12 | 8 | infeasible=1, ok=8, skipped=3 | infeasible=1, ok=8, skipped=3 |
| `Greedy-Weight-Backbone/sync` | 12 | 12 | 8 | infeasible=1, ok=8, skipped=3 | infeasible=1, ok=8, skipped=3 |
| `MIS-Connector-Backbone/async` | 12 | 12 | 8 | infeasible=3, ok=8, skipped=1 | infeasible=3, ok=8, skipped=1 |
| `MIS-Connector-Backbone/sync` | 12 | 12 | 8 | infeasible=3, ok=8, skipped=1 | infeasible=3, ok=8, skipped=1 |
| `MIS-Connector-TreeAgg/async` | 12 | 12 | 8 | infeasible=3, ok=8, skipped=1 | infeasible=3, ok=8, skipped=1 |
| `MIS-Connector-TreeAgg/sync` | 12 | 12 | 8 | infeasible=3, ok=8, skipped=1 | infeasible=3, ok=8, skipped=1 |
| `WuLi-Dominating-Bloom/async` | 12 | 12 | 8 | infeasible=2, ok=8, skipped=2 | infeasible=2, ok=8, skipped=2 |
| `WuLi-Dominating-Bloom/sync` | 12 | 12 | 8 | infeasible=2, ok=8, skipped=2 | infeasible=2, ok=8, skipped=2 |
| `WuLi-Dominating-Chunked/async` | 12 | 12 | 8 | infeasible=2, ok=8, skipped=2 | infeasible=2, ok=8, skipped=2 |
| `WuLi-Dominating-Chunked/sync` | 12 | 12 | 8 | infeasible=2, ok=8, skipped=2 | infeasible=2, ok=8, skipped=2 |
| `WuLi-Dominating-Exact/async` | 12 | 12 | 8 | infeasible=2, ok=8, skipped=2 | infeasible=2, ok=8, skipped=2 |
| `WuLi-Dominating-Exact/sync` | 12 | 12 | 8 | infeasible=2, ok=8, skipped=2 | infeasible=2, ok=8, skipped=2 |

### 4c. UYARI: anytime izi çözümle ÇELİŞİYOR

**20 satırda** koşumun döndürdüğü çözüm ile kendi anytime izi aynı şeyi söylemiyor. Bunlar aynı koşumun iki görünümüdür; biri yanlıştır ve hangisi olduğu şeklin içinden GÖRÜNMEZ, çünkü şekil 8 yalnız ize, CSV yalnız çözüme bakar.

| kol | çelişen satır | neden |
|---|---|---|
| `Anneal-Local/async` | 4 | iz hiç geçerli çözüm görmedi ama koşum |C|=250 döndü |
| `Anneal-Local/sync` | 4 | iz hiç geçerli çözüm görmedi ama koşum |C|=250 döndü |
| `Anneal-TreeAgg/async` | 4 | iz hiç geçerli çözüm görmedi ama koşum |C|=250 döndü |
| `Anneal-TreeAgg/sync` | 4 | iz hiç geçerli çözüm görmedi ama koşum |C|=250 döndü |
| `Anneal-Trickle/async` | 4 | iz hiç geçerli çözüm görmedi ama koşum |C|=250 döndü |

Görülen nedenler: 4 ayrı biçim.

## 5. Hayatta kalma yanlılığı

Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak altkümede. Kıyas `common` ile yapılır.

- ortak altküme: **8** örnek (toplam 12)
- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): 0
- kesin çözüm referansı olan örnek: 0

| kol | ratio_best_own | ratio_best_common | ratio_exact_common | tx (ortak) | uyarı |
|---|---|---|---|---|---|
| `Anneal-Local/async` | 1.0327 | 1.0327 | — | 73944.6 | — |
| `Anneal-Local/sync` | 1.044 | 1.044 | — | 77144.4 | — |
| `Anneal-TreeAgg/async` | 1.0327 | 1.0327 | — | 73944.6 | — |
| `Anneal-TreeAgg/sync` | 1.044 | 1.044 | — | 77144.4 | — |
| `Anneal-Trickle/async` | 1.0908 | 1.0908 | — | 45572 | — |
| `DFS-Spanning-Backbone/async` | 1.3399 | 1.3399 | — | 2.40805e+06 | — |
| `DFS-Spanning-Backbone/sync` | 1.3399 | 1.3399 | — | 4.72504e+06 | — |
| `GHS-MST-Backbone/async` | 1.2339 | 1.2339 | — | 92920.1 | — |
| `GHS-MST-Backbone/sync` | 1.2628 | 1.2628 | — | 155736 | — |
| `Greedy-Degree-Backbone/async` | 1.3434 | 1.3434 | — | 32279.4 | — |
| `Greedy-Degree-Backbone/sync` | 1.3434 | 1.3434 | — | 41135.2 | — |
| `Greedy-Ratio-Backbone/async` | 1.3434 | 1.3434 | — | 32279.4 | — |
| `Greedy-Ratio-Backbone/sync` | 1.3434 | 1.3434 | — | 41135.2 | — |
| `Greedy-Weight-Backbone/async` | 1.3434 | 1.3434 | — | 32279 | — |
| `Greedy-Weight-Backbone/sync` | 1.3434 | 1.3434 | — | 41135.2 | — |
| `MIS-Connector-Backbone/async` | 1.3434 | 1.3434 | — | 23340.1 | — |
| `MIS-Connector-Backbone/sync` | 1.3434 | 1.3434 | — | 29675.8 | — |
| `MIS-Connector-TreeAgg/async` | 1.3434 | 1.3434 | — | 62240.8 | — |
| `MIS-Connector-TreeAgg/sync` | 1.3434 | 1.3434 | — | 86632.8 | — |
| `WuLi-Dominating-Bloom/async` | 1.3428 | 1.3428 | — | 21599 | — |
| `WuLi-Dominating-Bloom/sync` | 1.3428 | 1.3428 | — | 25421.5 | — |
| `WuLi-Dominating-Chunked/async` | 1.3427 | 1.3427 | — | 25077.9 | — |
| `WuLi-Dominating-Chunked/sync` | 1.3427 | 1.3427 | — | 30026 | — |
| `WuLi-Dominating-Exact/async` | 1.3427 | 1.3427 | — | 21599 | — |
| `WuLi-Dominating-Exact/sync` | 1.3427 | 1.3427 | — | 25421.5 | — |

`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız `ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği küçük örneklerde tanımlıdır.

## 6. Eşleşmiş kıyaslar

İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır (eksenler: scheduler, phase1, phase5). Birden çok şeyi birden değiştiren kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.

| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |
|---|---|---|---|---|---|---|---|
| `MIS-Connector-Backbone/sync` | `MIS-Connector-Backbone/async` | scheduler | 8 | 0 | 0 | 1 | 0.7904 |
| `MIS-Connector-Backbone/sync` | `MIS-Connector-TreeAgg/sync` | phase5 | 8 | 0 | 0 | 1 | 2.7768 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Exact/sync` | phase1 | 8 | 0 | 0 | 0.9995 | 0.8534 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 8 | 0 | 0 | 0.9996 | 0.8534 |
| `MIS-Connector-Backbone/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 8 | 0 | 0 | 0.9995 | 0.9759 |
| `MIS-Connector-Backbone/async` | `MIS-Connector-TreeAgg/async` | phase5 | 8 | 0 | 0 | 1 | 2.659 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Exact/async` | phase1 | 8 | 0 | 0 | 0.9995 | 0.9231 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Bloom/async` | phase1 | 8 | 0 | 0 | 0.9996 | 0.9231 |
| `MIS-Connector-Backbone/async` | `WuLi-Dominating-Chunked/async` | phase1 | 8 | 0 | 0 | 0.9995 | 1.0425 |
| `MIS-Connector-TreeAgg/sync` | `MIS-Connector-TreeAgg/async` | scheduler | 8 | 0 | 0 | 1 | 0.7682 |
| `DFS-Spanning-Backbone/sync` | `DFS-Spanning-Backbone/async` | scheduler | 8 | 0 | 0 | 1 | 0.5105 |
| `GHS-MST-Backbone/sync` | `GHS-MST-Backbone/async` | scheduler | 8 | 0 | 0 | 0.9773 | 0.5989 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Exact/async` | scheduler | 8 | 0 | 0 | 1 | 0.8561 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Bloom/sync` | phase1 | 8 | 0 | 0 | 1.0001 | 1 |
| `WuLi-Dominating-Exact/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 8 | 0 | 0 | 1 | 1.1404 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Bloom/async` | phase1 | 8 | 0 | 0 | 1.0001 | 1 |
| `WuLi-Dominating-Exact/async` | `WuLi-Dominating-Chunked/async` | phase1 | 8 | 0 | 0 | 1 | 1.1277 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Bloom/async` | scheduler | 8 | 0 | 0 | 1 | 0.8561 |
| `WuLi-Dominating-Bloom/sync` | `WuLi-Dominating-Chunked/sync` | phase1 | 8 | 0 | 0 | 0.9999 | 1.1404 |
| `WuLi-Dominating-Bloom/async` | `WuLi-Dominating-Chunked/async` | phase1 | 8 | 0 | 0 | 0.9999 | 1.1277 |
| `WuLi-Dominating-Chunked/sync` | `WuLi-Dominating-Chunked/async` | scheduler | 8 | 0 | 0 | 1 | 0.8451 |
| `Anneal-Local/sync` | `Anneal-Local/async` | scheduler | 8 | 0 | 0 | 0.994 | 0.9597 |
| `Anneal-Local/sync` | `Anneal-TreeAgg/sync` | phase5 | 8 | 0 | 0 | 1 | 1 |
| `Anneal-Local/sync` | `Anneal-Trickle/async` | scheduler | 8 | 0 | 0 | 1.0484 | 0.5922 |
| `Anneal-Local/async` | `Anneal-TreeAgg/async` | phase5 | 8 | 0 | 0 | 1 | 1 |
| `Anneal-TreeAgg/sync` | `Anneal-TreeAgg/async` | scheduler | 8 | 0 | 0 | 0.994 | 0.9597 |
| `Anneal-TreeAgg/async` | `Anneal-Trickle/async` | phase5 | 8 | 0 | 0 | 1.0572 | 0.617 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Degree-Backbone/async` | scheduler | 8 | 0 | 0 | 1 | 0.7868 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Ratio-Backbone/sync` | phase1 | 8 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 8 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/async` | `Greedy-Ratio-Backbone/async` | phase1 | 8 | 0 | 0 | 1 | 1 |
| `Greedy-Degree-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 8 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Ratio-Backbone/async` | scheduler | 8 | 0 | 0 | 1 | 0.7868 |
| `Greedy-Ratio-Backbone/sync` | `Greedy-Weight-Backbone/sync` | phase1 | 8 | 0 | 0 | 1 | 1 |
| `Greedy-Ratio-Backbone/async` | `Greedy-Weight-Backbone/async` | phase1 | 8 | 0 | 0 | 1 | 1 |
| `Greedy-Weight-Backbone/sync` | `Greedy-Weight-Backbone/async` | scheduler | 8 | 0 | 0 | 1 | 0.7867 |

`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde başarılı demektir ve oran tek başına yanıltıcıdır.

## 7. Başarısızlık envanteri

100 satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.

| durum | satır | ort. slot | ort. tx | örnekler |
|---|---|---|---|---|
| `infeasible` | 63 | 2087.1 | 694380 | n1000_m6000_s1.txt/Anneal-Local/async, n1000_m6000_s1.txt/Anneal-Local/sync, n1000_m6000_s1.txt/Anneal-TreeAgg/async |
| `skipped` | 37 | — | — | n1000_m6000_s1.txt/DFS-Spanning-Backbone/async, n1000_m6000_s1.txt/DFS-Spanning-Backbone/sync, n1000_m6000_s1.txt/Greedy-Degree-Backbone/async |
