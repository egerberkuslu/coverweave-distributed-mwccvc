# BB-CVC katmanı: durum ve bulgular

Son güncelleme: 2026-09-15. Brief: `plan/MWCCVC_DAGITIK_TASARIM_BRIEF.md`.
Keşif: `DISCOVERY.md`. Sözleşme: `ccvc/bb/api.py`.

ADLANDIRMA. Kollar 2026-09-16'da yeniden adlandırıldı. Bu dosya tarihli bir
bulgu kaydı olduğu için eski adları (`V1-DFS`, `V4-BB-MST`, `V6-ANNEAL`...)
yazıldıkları hâliyle korumaktadır; eski adın bugünkü karşılığı
`ccvc/bb/armnames.py` ile `docs/SESSION_HANDOFF.md` içindeki eşleme
tablosundadır.

Koşum: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/ -q`
365 test + 1 atlanmış, 31 saniye. Yavaş hücreler: `BBCVC_SLOW=1`.

## Katmanlar

| dosya | ne | test |
|---|---|---|
| `api.py` | sözleşme, sabit nokta, Counters, Role | |
| `wire.py` | serileştirme, 250 B dayatması | 32 |
| `sched.py` + `simnet.py` | iki zamanlayıcı, kayıplı ağ, muhasebe | 46 |
| `bootstrap.py` | kimlik, keşif, çift yön, histerezis, epoch | 80 |
| `validate.py` | üç kapı + ihlal listesi | 85 |
| `bbcvc.py` | BB-CVC beş faz | 129 |

## Çalışan örnek: doğrulandı

10 düğüm, 15 kenar, k=2. MIS **{2,6,8}**, omurga **{2,4,6,7,8}** — belgedeki
figürle birebir. |C|=8 = ⌈15/2⌉ alt sınırı. Üç kapı da geçiyor.

| | slot / süre | tx | rx | Σw |
|---|---|---|---|---|
| senkron | 53 slot | 482 | 1294 | 27 |
| asenkron | 6371 ms | 368 | 932 | 27 |
| **belgede** | **20 slot** | **214** | **614** | opt 25 |

## BULGU 1: belgenin maliyet tablosu iki kalemi hiç saymıyor

Fark ayarlanarak değil, ayrıştırılarak açıklandı:

* **120 iletim bootstrap'a gidiyor.** Gerçek komşu keşfi 3 periyotluk kararlılık
  penceresi + el sıkışma istiyor; belge Faz 0'a **tek slot** ayırmış.
* **60 iletim çift yönlülük doğrulaması** (15 kenar × 2 yön × 2 çerçeve).
  Belgenin tablosunda bu kalem **hiç yok**.
* Yerel bariyer faz başına bir oturma tiki istiyor; belge sıfır ayırmış.
* Algoritma tekil gönderimleri 40, belgede 14.

Yani fark uygulamada değil, **analizde eksik kalemlerde**. Raporlanacak bulgu.

## BULGU 2: Σw=27, optimum 25 — yapısal, hata değil

8 esnek kenara karşı 7 birim bütçe var, dolayısıyla **tam olarak bir yükseltme
zorunlu**. Yerel kurallar bunu kimin yapacağını belirlemiyor: belgede düğüm 8
yarışı kazanıp 10'u (w=4) davet ediyor, bizde düğüm 6 kazanıp 5'i (w=6) davet
ediyor. İkisi de aynı kuralların geçerli koşumu. 25'i yakalamak için tek
atlamada var olmayan bir çapraz-düğüm sıralama sinyali gerekir.

## BULGU 3: G8 kıyas verisinde TUTMUYOR (ölçüldü)

Brief §5'in "HELLO sabit boyutlu, yoğunluktan bağımsız" manşeti tamamen G8'e
dayanıyor, o da birim disk çizgesi teoremi. Dagdeviren kıyas verisinde:

| çizge | ort. derece | maks bağımsız komşu | 5'i aşan düğüm |
|---|---|---|---|
| n=25 | 8,0 | 6 | 4 |
| n=100 | 12,0 | 13 | 92 |
| n=200 | 16,0 | **17** | **200/200** |

17 komşuda HELLO 23 yerine 47 bayt. 250 B sınırı 118 girişte geliyor, yani
aşılmıyor. **"250 bayta sığar" ayakta, "sabit boyutlu" değil.** Kapsam koşulu.
Sınır telde değil üreticide, parametre olarak (`mis_nbrs_max`), çünkü telde
dayatılsa 200 düğümlük örnekte her düğüm hata atardı.

## BULGU 4: komşu tablosu sınırı güvenli (ölçüldü)

54 örnek grubu, n=10..1000. **En büyük derece 36**, tablo sınırı 64, pay 28.
Hiçbir örnekte aşılmıyor. Taşma artık koşumu **geçersiz kılıyor** (`RunInvalid`),
çünkü kırpılmış tablo dereceyi, derece anahtarı, anahtar da MIS sıralamasını
zehirliyor.

## Sessizce yanlış çalışan üç hata (hepsi temiz sayı raporluyordu)

1. **Bütün günlük satırları çöpe gidiyordu.** Anahtar kelime çakışması + geniş
   istisna yutucu. Brief sayaçları günlükten türettiği için tüm ölçümler boş
   çıkacaktı. Taklit ağın imzası uyumlu olduğu için iki taşıma varken görünemezdi.
2. **Onay tekrarları sayılmıyordu.** Yeniden gönderim sayacı yalnız istek
   tarafını sayıyordu; kayıplı koşumda maliyet ~yarı yarıya eksikti.
3. **Bekleyen tekil gönderimler yalnız sıra numarasıyla eşleşiyordu.** Sıra
   numarası gönderici başına olduğu için bir komşunun onayı başkasının isteğini
   kapatıyor, kenar sahipsiz kalıyordu.

Ortak ders: **sınırın tuttuğunu değil, bozulmanın gerçekleştiğini test et.**

## Telde kapatılan iki sessiz tip dönüştürmesi

Kayan noktalı anahtar `int()` ile eziliyordu: 1,67 tele 1 olarak gidip 0,00002
olarak geri okunuyordu, yani MIS sıralaması çöp üzerinden yapılırdı. Rol alanında
aynı hata vardı ve **`Role(2.0)` bunu yakalamıyor**, çünkü numaralandırma 2.0 ile
2'yi aynı karma değerinde görüyor. Yalnız kesin tip denetimi yakalıyor.

## .tex'ten üç bilinçli sapma (bb-algo raporladı)

* **3 atlama boşluk kuralı** MIS düğümünden köprüleyen düğüme taşındı. Özgün hali
  yıldız ve tam çizgede de tetikleniyor; K5'te |C| 4 yerine 5 çıkıyordu.
* **DONE iki adımlı** (QUIET sonra DONE); tek koşullu okuma kilitleniyor.
* **Uygunsuzluk tanığı eklendi.** Belgedeki koşul "C = V" ama düğüm bunu göremez.
  Tanıksız 120 koşumda 6 yanlış uygunsuzluk ölçüldü.

## Açık kalan kararlar (kullanıcıya soruldu, yanıt bekliyor)

1. Mininet-wifi'de hedef n: 100 mü 200 mü.
2. Bağlılık: katı mı bileşen bazlı mı (varsayılan katı).
3. Kampüs çizgelerindeki ağırlık fiziksel olarak ne.
4. Faz 5b kök seçimi koordinatörsüzlüğe aykırı sayılacak mı.

## Sırada

Brief §12 adım 4 ve sonrası: mininet-wifi koşum altyapısı, şekiller (§8),
karşılaştırma varyantları (§6: V1-DFS, V4-BB-MST, V5-BB-WuLi, V6-ANNEAL),
deney koşucusu ve `docs/message_complexity.md`.

---

## 15. METODOLOJİK BULGU: "suç ortağı taklit" hata sınıfı (2026-09-15)

Bugün yakalanan üç ciddi hatanın ortak yapısı var ve bu yapı, test edilmemiş kod
yolundan **farklı bir sınıf**. Ayırt edici özelliği şu:

> Taklit ile kod, **ikisinin de dile getirmediği bir varsayımda** anlaşıyor.
> Dolayısıyla taklit, kodla o konuda çelişemez ve **o taklit üzerinden ne kadar
> test yazılırsa yazılsın hata yüzeye çıkamaz.**

Test edilmemiş yolda kapsam eksiktir ve bir test daha yazmak onu bulur. Burada
kapsam tamdır, testler geçer, ve daha fazla test yazmak **kanıtlanabilir biçimde
işe yaramaz**. Yalnız taklidi gerçeğiyle değiştirmek işe yarar.

| Taklit | Dile getirilmeyen ortak varsayım | Gizlediği hata |
|---|---|---|
| Taklit ağın `log` imzası | platformun günlük imzası uyumludur | düğümün **bütün** günlük satırları çöpe gidiyordu; yeniden gönderim sayacı hep 0 |
| Sanal saat | saat sıfırdan başlar | kararlılık kapısı ilk tikte **ters** çalışıyor, her düğüm derece 0 ile anahtar donduruyor |
| `Neighbor.last_ms = 0` varsayılanı | 0 makul bir zaman damgasıdır | yeni kayıt duvar saatinde **doğduğu anda** yumuşak-durumdan düşüyor |

Üçüncüsü aynı sınıfın "taklit"i bir test nesnesi değil bir **varsayılan değer**
olan hali. Yani örüntü test taklitlerinin ötesine, kodla kurgu gereği uyuşan her
vekile genelleniyor.

### Pratik kural

Savunma, taklide karşı daha çok test yazmak değil, **taklidi en az bir kez
gerçeğiyle değiştirmek**.

* Taklit ağı silmek → birinci hatayı buldu
* Emülatörde koşmak → ikinci hatayı buldu
* Emülatörün tetiklediği süpürme → üçüncü hatayı buldu

**Üç hata, üç değiştirme, test ekleyerek bulunan sıfır.**

### Rapor için en çarpıcı ayrıntı

Bu süre boyunca test sayısı sürekli arttı ve hep yeşildi. Ters çalışan kapının
üzerinden **461 test** geçti. Yani "testler geçiyor" ve "test sayısı büyüyor"
ifadelerinin ikisi de doğruydu ve ikisi de bu üç hata hakkında hiçbir bilgi
taşımıyordu.

### İlgili ikinci kural: boş test

Aynı gün üç kez, geçtiği halde hiçbir şey doğrulamayan test görüldü:

1. Yerellik denetçisi yalnız bir erişim biçimine bakıyordu; port okuması
   kurucuya taşınınca sayımın dışında kaldı ve test **boşa geçmeye** başladı.
2. Port yüzeyi testi özel nitelikleri süzüyordu, dolayısıyla `_net` üzerinden
   çizgeye erişim açık kalıyordu. Delik **kapatılamadığı için varlığı test
   edildi** ve gerçek korumanın nerede olduğu belgelendi.
3. Saat hatasını sabitlemek için önerdiğim iddia, tek düğümlü kurulumda **yanlış
   sebepten** geçiyordu: düğüm hiç komşu edinmediği için anahtar zaten boş
   kalıyordu. İki düğümlü kurulumla ve iki yarısı birden doğrulanarak düzeltildi.

Savunma: **denetçiyi mutasyonla sına.** Kasten bozulmuş bir sürüme karşı
koşmayan bir denetçi, hiçbir şey kanıtlamaz.

### Üçüncü kural: bozulmayı test et, sınırı değil

Sınırın tuttuğunu doğrulayan test, sınır aşıldığında ne olacağını söylemez.
Komşu tablosu taşmasında yapılan doğru şey, taşmanın **dereceyi bozduğunu**
doğrulamak oldu; ardından taşma koşumu geçersiz kılan bir hataya bağlandı.
Aynı kalıp kapasite fazlarında da uygulandı: sahiplik haritasından bir kenar
silinince doğrulayıcının bunu yakaladığı test edildi.

### Dördüncü kural: etkiyi çivile, yazımı değil

Boş testin bugün ortaya çıkan dördüncü hali, ötekilerden farklı olarak **zaman
içinde** boşaldı. İddia kaynak metne bakıyordu:

    assert "_t0_ms" not in inspect.getsource(BbcvcNode.on_timer)

Saat tabanı hatası düzeltilirken `on_timer` tabanı doğrudan kurmak yerine
bootstrap'ın `_establish_clock_baseline` uzatma noktasını ezip `super()`
çağırmaya başladı. Aranan dizi metinde gerçekten yok, dolayısıyla test yeşil.
Ama ölçtüm: bir tikten sonra `_t0_ms` **1700000000000**, yani ne None ne de ölü
kod. Testin iddiası da, gerekçesini anlatan docstring'in her cümlesi de artık
yanlıştı, üstelik yeşil bir testin arkasında duruyorlardı.

Bu, suç ortağı taklidin bir üst katmanı. Orada taklit kodla bir varsayımda
anlaşıyordu; burada test, değişmezin **tutup tutmadığı** hakkında değil,
düzeltmenin **nereye yazılacağı** hakkında haklıydı. Düzeltme başka bir yere
yazılınca test hiçbir şey söylemeden boşaldı ve **kanıt gibi okunmaya** devam
etti. Değişmezini yitirmiş bir tuzak, hiç tuzak olmamasından kötüdür.

Yanlış onarım, `on_timer` içine göstermelik bir `_t0_ms` geçirip dizi eşleşmesini
kurtarmak olurdu. bb-algo bunu bilerek yapmadı ve haklıydı: test o zaman
doğrulukla ilgisi olmayan bir sebeple geçer, sökülmek istenen kaynak bağımlılığı
da kalıcılaşırdı.

Doğru onarım, iddiayı etkiye taşımak. İki yarım birlikte yük taşıyor, çünkü
`_t0_ms` yarısı pencerenin gerçekten kollandığını kanıtlıyor ve `key is None`
yarısının yanlış sebepten geçmesini engelliyor:

    assert nodes[nid].__dict__.get("_t0_ms") == WALL_MS
    assert nodes[nid].key is None

Yerine koyma iki yönde de mutasyonla sınandı. Uzatma noktası tamamen iptal
edilince kod `bootstrap.py:718`'de `TypeError` ile çöküyor, yani iddia yük
taşıyor ama bu sadık bir gerileme değil. Eski yolu sadık taklit eden mutasyonda
(super() çağrılır, ardından `_t0_ms = None`) kod **çökmüyor** ve test 2/2 düğümde
ateşliyor. Belgelenen hatanın tam biçimi, temiz yakalandı.

`__dict__.get` kullanımı bilinçli: saklanan değeri okur, değeri hesaplayan bir
property ile tatmin edilemez.

**Kural:** bir testin iddiası kodun yazımına bakıyorsa, o test kodun yeniden
düzenlenmesiyle sessizce boşalır. Değişmez, hangi yöntemin yaptığından bağımsız
olarak gözlenebilir etki üzerinden çivilenir.

## 16. BULGU: mesaj maliyeti üç mekanizmaya ayrışıyor (ölçüldü, 2026-09-15)

**ÖNCE BİR DÜZELTME.** Bu bulgunun ilk sürümü **kopuk** UDG çizgelerinde
ölçülmüştü. Doğrulayıcı girdinin 6 bileşenli olduğunu bildirdi, ben fark
etmemiştim. Brief §1 G'nin bağlı olduğunu varsaydığı için kopuk girdi bir deney
değil bir harness hatasıdır. Bağlı çizgelerde yinelenen ölçüm hem daha temiz
hem de daha güçlü çıktı, aşağıdaki sayılar düzeltilmiş olanlardır.

Kendi harness'ini denetlemeyen bir ölçüm, denetlenmemiş bir taklit kadar
tehlikelidir. Bu, 15. maddedeki sınıfın ölçüm tarafındaki karşılığıdır.

**Faz 0 bir üst sınır değil, bir ÖZDEŞLİKTİR.** Bağlı çizgede ve **yalnız
SENKRON** zamanlayıcıda (kapsam düzeltmesi aşağıda, madde 28)

    Faz 0 tx = 6·n + 4·m        (YALNIZ SENKRON)

Dokuz koşuma en küçük karelerle oturtulan model `6,000·n + 4,000·m` vermekte ve
artık **sıfır** çıkmaktadır (ortalama ve en büyük bağıl artık %0,0). Katsayılar
uydurulmamıştır, iki mekanizmadan okunmaktadır: altı slotluk keşif penceresi ve
kenar başına dört çerçevelik LINK el sıkışması.

**LINK el sıkışması kenar başına TAM 4 gönderimdir.** Tip 1 ve tip 2 çerçeveleri
on iki koşumun on ikisinde de kenar başına tam 2,000 çıkmakta, hiç sapma
göstermemektedir. Terim zamanlayıcıdan bağımsızdır. Brief'e eşlik eden belgenin
maliyet tablosu bu kalemi hiç saymamaktadır (bkz. BULGU 1).

**Faz 1-4 dereceden neredeyse bağımsızdır.** Kenar sayısı dört kattan fazla
değişirken bu fazların maliyeti yaklaşık iki kat artmaktadır. Yoğun çizgede
pahalı olan şey örtü hesabı değildir, keşif ve el sıkışmasıdır.

**Zamanlayıcı farkının tamamı HELLO'dadır.** Asenkron kol %7-10 ucuzdur, ancak
HELLO dışı gönderim sayısı iki zamanlayıcıda neredeyse aynıdır (390/384,
826/826, 1326/1312). Zamanlayıcı seçimi algoritmanın yaptığı işi
değiştirmemekte, yalnız düğümlerin uyanık kalma süresini değiştirmektedir.

## 17. BULGU: uygunsuzluğun yarıçap-1 tanığı var (ölçüldü, 2026-09-15)

n=100, m=364, k=4 örneğinde koşum `infeasible=True` ile bitmektedir ve **bu
cevap doğrudur**. Bağımsız maksimum-akış denetimi, bütün düğümler örtüye konsa
bile uygun bir sahiplik ataması olmadığını doğrulamaktadır. Yani daha önce
"Faz 4 yeterince yükseltmiyor" diye raporladığım şey, düzgün bağlı girdide
bir eskalasyon kusuru değildir, örneğin kendisi uygunsuzdur.

Kusur cevapta değil, cevaba varmanın bedelindedir. Faz 0-4 toplam 2877 gönderim
harcarken Faz 5 tek başına **15365** gönderim ve 1310 slot tüketmektedir. Aynı
örnek k=6'da 70 slotta bitmektedir.

**Uygunsuzluk yerel olarak görülebilmektedir.** Bu örnekte 58 numaralı düğümün
kapalı komşuluğu 16 düğüm ve 73 kenar içermekte, kapasite ise ancak 64 kenara
izin vermektedir. Bir sayma çelişkisi olduğu için tanık **sağlamdır**: göründüğü
her yerde örnek gerçekten uygunsuzdur, ek kanıt gerekmez.

Kapsamı ölçüldü: 30 örnekte (2 boyut × 3 tohum × 5 kapasite) yerel tanık küresel
maksimum-akış cevabıyla **30/30 aynı** sonucu vermektedir.

Sağlamlık kanıtlı, **tamlık yalnız görgüldür**.

**DÜZELTME (aynı gün, ölçümle).** Tanığın kapsamı yukarıda yazdığımdan dardır ve
iki ayrı sorunu birbirine karıştırmışım. Tanık **uygunsuz ÖRNEĞİ** yakalar,
**uygun bir örneğin uygunsuz ÖRTÜSÜNÜ** yakalamaz. Ayrıca ilk yazdığım koşul
(`|E(S)| > k|S|`) zorunlu yükü saymıyordu, doğrusu `|E(S)| > Σ(k − F(v))`. Erken çıkış olarak bile Faz 5'in on beş bin gönderimini
Faz 0 sonunda yapılacak bir yerel denetimle değiştirmektedir. Gereken bilgi,
düğümün kapalı komşuluğunda hangi komşuların birbirine bitişik olduğudur, yani
V5-BB-WuLi kolunun zaten taşımak üzere kurulduğu bilgi.

## 18. BULGU: Faz 4'ün gerçek kusuru ve derinleştirmenin saf maliyeti (2026-09-15)

**Benim ilk teşhisim yanlıştı ve bb-algo onu olduğu gibi almadı.** "Faz 4
yeterince yükseltmiyor" demiştim. Ölçüm başka bir şey söyledi: dal ZATEN
çalışıyor, ama yapacak bir şey bulamıyor. Her başarısız koşumda her aşırı yüklü
düğümün dış komşu listesi boştu, çünkü aşırı yük örtünün **içinde** oluşuyor ve
orada her komşu zaten örtüde. Yani kusur az-tetiklenme değil, kuralın
**yapısal olarak erişilemez** olmasıydı. Farklı bir kusur, farklı bir çözüm.

Düzeltme, vekâleten eskalasyon (kademe 3b): HELLO'daki `load` alanı zaten F
olduğu için `F(u) > 0` tam olarak "u'nun dış komşusu var" demektir. Sıkışan
düğüm böyle bir komşudan kendi adına eskale etmesini ister. Tek atlamalık
bilgiyle iki atlamalık erişim, yeni mesaj tipi gerektirmeden.

### Derinleştirme saf maliyetti (bağımsız olarak doğrulandı)

bb-algo, PUSH derinleştirmesinin (ttl 6-8) 115 gönderimde **sıfır** başarı
ürettiğini ölçtü. Kendi bağlı üreticimle, **gerçekten uygunsuz** bir örnekte
bağımsız olarak doğruladım ve etki onların raporladığından büyük çıktı:

```
push_ttl_max   slot    tx       sonuc
     3         1310    65690    infeasible
     8         4085   218632    infeasible
```

Aynı doğru cevap için 3,1 kat slot ve 3,3 kat iletim. Derinleştirme, lehine en
çok sav üretilebilecek durumda (uygunsuzluğu kanıtlamak) bile saf maliyettir.
Varsayılan 3'e çekildi, parametre deneyler için duruyor.

Ayrıca derinleştirmenin eklenme gerekçesi de tutmuyordu: yanlış `INFEASIBLE`
alarmını önleyen şey derinleştirme değil, C=V tanığıydı. Özellik matrisi
`push_ttl_max=3` ile de sıfır yanlış alarm veriyor.

### Yöntem notu

bb-algo'nun ilk hipotezi (ACK geri çekilme merdiveni) yanlıştı ve **üstüne
inşa etmeden önce ölçüldü**. PUSH gecikmesi ortanca 2 slot çıkınca hipotez
temizce düştü ve asıl neden (6032 PUSH gönderimi, 5981'i NACK, %1,3 başarı)
ancak o zaman göründü. Bir teşhisi, onu bildiren kişiden gelse bile
doğrulamadan kabul etmemek bu projede üç kez işe yaradı.


## 19. BULGU: ikinci uygunsuzluk kipi yerel olarak GÖRÜLEMEZ (ölçüldü, 2026-09-15)

bb-bootstrap, hiç aşırı yüklü düğüm olmadan kapasitenin uygunsuz kalabildiği
ikinci bir kip buldu. Ölçerek karakterize ettim.

**Örnek:** `figures.udg_instance(100, 0.15, 4)`, k=4. Bütün düğümler örtüde
uygun, ama BB-CVC'nin 89 düğümlük örtüsü uygun değil, ve en büyük F yalnız 2.
Yani `F(v) > k` yordamı sessiz kalıyor, çünkü kimse aşırı yüklü değil. Sorun
Hakimi yönlendirmesinin esnek kenarlar üzerinde tıkanması (brief G5).

**Tanığım bu sınıfı kapsamıyor, önceki iddiamı daraltıyorum.** Sekiz tohumda
sınadım: 0, 1 ve 6'da (gerçekten uygunsuz örnekler) ateşliyor, dört geçerli
tohumda sessiz kalıyor, tohum 4'ü ise büsbütün kaçırıyor. Uygunsuz ÖRNEK ile
uygun bir örneğin uygunsuz ÖRTÜSÜ farklı problemlerdir, ben ikisini tek şey
sanmışım.

**Tespit yerel DEĞİLDİR ve bu ölçüldü.** Tohum 4'te yarıçap 1, 2, 3 ve 4'ün
hiçbirinde ihlal görünmüyor; bütün toplar üzerinde en büyük `|E(S)| − bütçe(S)`
yarıçap 1'de −4 ve yarıçap büyüdükçe daha da negatifleşiyor. Min-kesit engeli
G[C] içinde **13 atlama** yayılıyor. Dolayısıyla top şeklinde hiçbir yordam bu
sınıfı hiçbir yarıçapta bulamaz.

**Açık minik, onarım tek düğüm.** Maksimum akış 242 esnek kenarın 240'ını
yerleştiriyor, yani yalnız iki kenar açıkta. Örtü dışındaki 11 düğümün **tam
biri** (78) sorunu çözüyor ve ortaya çıkan ağırlık 407, merkezi çözücünün
409'unu yeniyor.

**Yerel bir TETİK var, yerel bir TESPİT yok.** Ayırt edici koşul aşırı yük
değil, **doymuş esnek kenar**: k kenar sahiplenen bir düğümün esnek kenarının
öbür ucu da doluysa, kenar hiçbir uca kaydırılamaz ve iki uç da aşırı yüklü
değildir. Düğümün zaten sahip olduğu bilgiyle görülür ve tohum 4'te ateşler
(131 kenar). Ancak **isteklidir**: dört geçerli tohumda da ateşliyor (93-144).
Dolayısıyla uygunsuzluk ilan edemez, yalnız bir DENEMEYİ tetikleyebilir; davet
edilir ve ancak gerçekten rahatlama sağlıyorsa örtüde tutulur. Sayılar geçerli
tohumlarda da aynı mertebede olduğu için eşikle ayrıştırılamaz.

Vekâleten eskalasyon iki atlamaya erişiyor, bu engel ise 13 atlama genişliğinde.
Dolayısıyla o düzeltmenin bu sınıfı kapsaması beklenmemelidir.

## 20. BULGU: 4m özdeşliği TEMİZ KANAL içindir (bb-algo buldu, doğrulandı)

Madde 16'daki kenar başına tam 4 gönderim özdeşliği **kayıpsız** koşumlar
içindir. Benim altı koşumum da temiz kanaldı, dolayısıyla sınırı gösteremezdi.
bb-algo kayıp altında kırıldığını gösterdi, kendi üreticimle doğruladım:

```
kayıp   tip1/m   tip2/m       tx    slot
 %0       2,00     2,00     1211      22
 %5       2,17     2,04     2057      44
%15       2,82     2,40    32629    4500
```

**Asıl sayı oran değil ölçektir.** Kenar başına çerçeve yalnız 2,00'den 2,82'ye
çıkarken toplam iletim 27 kat, slot sayısı **205 kat** artmaktadır. Sebep
yeniden gönderim değil, epoch yükselmesidir: düşen komşu çift yönlü kümeyi
değiştirir, herkes Faz 0'a döner, el sıkışması baştan koşar. Yalnız oranı
raporlamak etkiyi iki mertebe küçük göstermektedir.

Kapsamı yazılmadan kaydedilen bir değişmez evrensel yasa gibi okunur.

## 21. BULGU: sıkı kapasitenin maliyeti onarım değil yeniden yerleşmedir

n=100, r=0,15 örneklerinde Faz 5 sonrası maliyetin dağılımı:

```
tohum  k   Faz 0-4   Faz 5   QUIET   QUIET payı
  2    4      2716     608     687       %53
  3    4      2821    2323    4320       %65
  5    4      2804     986    2043       %67
  2    8      2716     328     147       %31
  5    8      2804     352     264       %43
```

Sıkı kapasitede maliyetin **üçte ikisi** onarım değildir. Sükûnete ulaşıp hâlâ
yerleşmekte olan bir komşu yüzünden sükûnetten çıkan düğümlerdir, yani Faz 5a'nın
yerel bariyer bedelidir. Kapasite gevşedikçe pay düşmektedir.

Dolayısıyla "yoğunlukta onarım zorlaşıyor" okuması yanlıştır, doğrusu "yerel
bariyer daha çok kez yeniden kuruluyor"dur.

**Kapasite ilk dört faza hiç dokunmamaktadır.** Aynı çizgede k=4/6/8 için
Faz 0-4 bayt bayt aynıdır (2716 üç kez, 2804 üç kez, 2821/2820/2818). Kapasite
deneyleri ilk dört fazı yeniden ölçmek zorunda değildir.

## 22. Sınıfın beşinci örneği: kapıyı atlayan ikinci yol

bb-algo'nun kendi kodunda, kayıplı koşum testinin bulduğu hata. `_nkey` ham
`(anahtar, id)` demetlerini karşılaştırıyordu, oysa komşunun anahtarı kararlılık
kapısı açılana kadar None'dır. Karar KURALLARI güvenliydi çünkü `_step` önce
`_keys_ready`e bakıyor, ama MESAJ İŞLEYİCİLERİ o kapının arkasında değil ve
kademe 3b `_on_join` üzerinden erişiliyor.

Sınıfın beş örneği artık şöyle:

| # | Uyuşan iki taraf |
|---|---|
| 1 | taklit ağ ile kod, günlük imzası üzerinde |
| 2 | sanal saat ile kod, saatin sıfırdan başlaması üzerinde |
| 3 | varsayılan değer ile kod, 0'ın makul zaman damgası olması üzerinde |
| 4 | test ile kod, düzeltmenin NEREYE yazılacağı üzerinde |
| 5 | işleyici ile kural, kapının zaten geçilmiş olması üzerinde |

Ortak biçim: **çelişmesi gereken taraf çelişemiyor.** Beşincisi kayıpsız testle
asla bulunamazdı, çünkü kapıyı atlayan yol ancak epoch sıfırlaması olunca
tetikleniyor.

## 23. YÖNTEM HATASI (benim): bir kolun çıktısından problemin özelliğine atlamak

Faz 4 eskalasyon kusurunun omurga şeklinden bağımsız olduğunu söyledim ve
yanlıştı. Dayanağım şuydu: her başarısız koşumda her aşırı yüklü düğümün dış
komşu listesi boştu.

Bu gözlem **problemin** değil, **V2'nin örtülerinin** bir özelliğidir. Aşırı
yükün örtünün içine mi kenarına mı düşeceği C'nin şeklinden gelir, C'nin şekli
de Faz 1'den gelir, yani dikişin değiştirmek için var olduğu değişkenden.
Dolayısıyla tek bir kolun çıktısından bütün kolların davranışına geçilemez.

bb-bootstrap benzetmeyi doğru kurdu: bu, G8'in UDG'ye kapsamlı savını kıyas
verisinde de geçerli saymakla aynı hamledir, ki o sav n=25 üstündeki her
boyutta ölçülerek çürütülmüştü (BULGU 3).

**İkinci hata daha ağırdı:** bb-algo kusurun şekle BAĞLI olduğunu söylemişti,
ben bb-bootstrap'a tersini söyleyip bunu bb-algo'ya atfettim. Özetleme kayması
değil, sonucun tersine çevrilmesiydi. bb-algo'nun sonucu geçerli olandır.

**Kural:** bir ölçüm hangi kolun çıktısı üzerinde yapıldıysa, sonuç o kola
kapsamlıdır. Problemin özelliği olduğunu iddia etmek için kolun kendisi
değiştirilip yeniden ölçülmelidir.

### İlgili: eksik sayaç

Aynı konunun ölçme tarafı. `relay_escalate` sayacı "Faz 4 bunu onaramadı"nın
tam sayacı DEĞİLDİR: hiç aşırı yüklü düğüm bulunmayan kipte sıfır okur, oysa
koşum uygunsuz biter (BULGU 19). Vekâleten eskalasyon iki atlamaya erişir,
o kipteki engel ise 13 atlama genişliğindedir. İki kip ayrı sütun olarak
raporlanır, ortalaması alınmaz, yoksa önemli olan kip gizlenir.

## 24. BULGU: Bloom özeti bizim derecelerimizde tam listeden BÜYÜK (V5, doğrulandı)

Brief §5 madde 1, komşuluk özetini sabit 64 baytlık Bloom filtresiyle taşımayı
öneriyor, gerekçe mesaj boyutunu küçültmek. **Ölçüm bunun tersini söylüyor.**
bb-validate ölçtü, `--sizes-only` ile bağımsız doğruladım:

```
derece    full   bloom  chunked
     2      19      79       19
     5      25      79       25
    10      35      79       31
    20      55      79       31
    36      87      79       31
   117     249      79       31   <- tam listenin sığdığı en büyük derece
   118     251      79       31   <- 250 B aşıldı
```

`full = 13 + 2(1+d)` olduğu için full ile bloom **derece 32'de** kesişiyor.
Kıyas verisinin ortalama dereceleri 6-16, en büyüğü 36. Dolayısıyla **hemen
hemen her düğüm için** Bloom daha çok bayt ödeyip karşılığında kesin bilgi
yerine belirsizlik almaktadır. Uçtan uca ölçümde Bloom koşumları tam listenin
2,8 katı `bytes_tx` harcayıp %30 daha ağır örtü döndürmektedir, yani iki eksende
birden kaybetmektedir.

**250 B bu yapılandırmada erişilemez.** Tam liste dereceye 117'ye kadar sığıyor
ve tel 118'de kalkıyor (canlı kanıtlandı). Ama komşu tablosu 64 girdilik ve
taşma koşumu zaten geçersiz kılıyor, dolayısıyla en büyük yasal tam liste
64 kimlik = 143 bayt, sınırın ancak yarısı. Brief §5'in "yoğun çizgeler 250 B'yi
aşar" savı ancak `nbr_table_max` da yükseltilirse doğrudur. İki sınır birlikte
raporlanmazsa sav yanlış okunur.

### Yanlış pozitif yalnız bozmuyor, GEÇERSİZ KILABİLİYOR

Zinciri bb-validate uçtan uca gösterdi: bit dolu -> naif politika "bitişik" okur
-> düğüm bitişik olmayan komşu çifti bulamaz -> işaretlemez -> omurga artık CDS
değil -> Faz 2'nin G2 savı çöker -> G[C] kopuk. 4 baytlık filtreyle n=30'da
25 tohumun 2'si tam bunu yapıyor ve `validate.validate` `disconnected` diyip
kopan bileşenleri adlandırıyor. Aynı örnekler tam kodlamayla ve güvenli
politikayla geçerli, yani kusur çizgede değil kodlamada.

### 64 bayt bizim derecelerimizde KAZARA güvenli

Brief'in önerdiği 64 baytta 8 örnekte sıfır sapma görülüyor, sapma ancak
ortalama derece 60 civarında başlıyor. **Bu nicel bir kaza, garanti değil.**
Rapor "bu derecelerde gözlenmedi" demelidir, "olamaz" değil.

### Derece 36 sorusu doğru birimde

Sorgu başına yanlış pozitif oranı yanıltıcı birimdir, çünkü işaretleme kuralı
düğüm başına C(36,2) = 630 soru sorar. Ölçülen 1,3e-3, **düğüm başına 0,82
beklenen bozuk cevap** demektir. Yani yanlış pozitif orada nadir değil, tipiktir.

Kurtaran şey filtre değil, bedelsiz bir uygulama tercihidir: her iki ucun
filtresine birden sormak (çiftin dönmesi için ikisinin de yanılması gerekir),
ek mesaj gerektirmez ve derece 36'da ölçülen maruziyeti sıfıra indirir
(1,5e-3 -> 0,00).

### Ölçümün yakaladığı hata: çift karma

İlk Bloom, Kirsch-Mitzenmacher çift karma kullanıyordu. m=512'de derece 10'da
ölçülen oran 2,1e-4, formül ise 1,9e-7, yani **bin kat** kötü. Sebep: m ikinin
kuvveti olunca adım yalnız 256 değer alıyor ve her öğenin konumları aritmetik
dizi oluşturuyor. Formüle güvenilseydi bu deneydeki her yanlış pozitif sayısı
yanlış olurdu.

### Parçalama: iki tasarım, iki ayrı fatura

Sıralı parçalama (periyodik HELLO başına bir parça) **sıfır ek tx** maliyetlidir.
Brief §5/2'nin "tx artar" ifadesi yalnız patlamalı tasarımı anlatmaktadır, o da
tx'i çevrim uzunluğuyla çarpmaktadır (403 -> 967 ölçüldü). Sıralı tasarım
bedeli gecikmeyle öder.

Kısmi görüş gerçektir: parça başına 1 kimlikte her düğüm eksik görüşle karar
verir ve işaretlerin dörtte birine kadarı tam listeden farklı çıkar. Ancak
sapma **her hücrede daima fazla-işaretleme yönündedir, hiç eksik-işaretleme
değildir**. Eksik parça "bilinmiyor" demektir, güvenli politika bunu "bitişik
değil" okur, dolayısıyla hata yalnız omurgayı büyütebilir. Bu, Bloom'un hata
yönünün ayna görüntüsüdür. `under_marked == 0` assert edilmektedir.

### Güvenli politika + Bloom dejenere oluyor

Bloom asla EVET diyemez, yalnız HAYIR ya da BELKİ der, ve §5/1'in güvenli
politikası BELKİ'yi hayır okur. Dolayısıyla her çift bitişik olmayan görünür,
derecesi 2 ve üstü olan herkes işaretlenir, hiçbir şey budanamaz. Güvenli Bloom
omurgası tam olarak `{v : deg(v) >= 2}` olmaktadır, ki geçerli bir CDS'tir ama
Wu-Li'nin tamamını çöpe atar. Yani 64 bayt boyut değil **nitelik** maliyeti
getirmektedir, ve madde B1'e göre boyut da kazandırmamaktadır.

## 25. BULGU: V6-ANNEAL brief'in dağılımını YENİDEN ÜRETMİYOR (bb-core)

Brief §6.5, PDF'teki 10 düğümlük örnekte 60 tohumla yaklaşık %48 optimum (25),
%33 yirmi altı, gerisi 27-29 bekliyor. **Ölçüm bunu vermiyor:**

```
ağırlık    25  26  27  28  29  30  34
ölçülen     3  13  20  14   3   6   1
brief     ~29 ~20  <-- 11 tanesi 27-29 -->
```

Altmışın altmışı da geçerli, sıfır Faz 4 eskalasyonu. Parametre değiştirilmeden
ölçüldü.

**DÜZELTME (bb-core kendi raporunu düzeltti).** Yukarıdaki satır SON DONMUŞ
DURUMU ölçmektedir. Koşumun geçtiği EN İYİ geçerli durum ölçülünce tablo
değişmektedir:

```
ağırlık        25  26  27  28  29  30
son durum       3  13  20  14   3   6
en iyi görülen 12  25  14   7   1   1
brief          ~29 ~20  <-- 11 tanesi 27-29 -->
```

En iyi görülende 25+26 toplamı 60'ta 37 (%62), brief'in %81'ine karşı; son
durumda ise 60'ta 16 (%27). Yani **brief'in sayıları son durum değil en iyi
görülen dağılımıyla çok daha iyi açıklanmaktadır**, ki standart tavlamanın
yaptığı da budur. Fark gerçektir ama sandığımdan küçüktür ve sebebi büyük
olasılıkla referansın en iyi çözümü saklamasıdır.

**Bu bir başarısızlık değil bulgudur, çünkü kütle tam .tex'in zor dediği yerde
toplanıyor.** Yığılma 27'de ve .tex ara yerel minimumu `{2..9}` diye adıyla
anıyor. 27'den kaçmak iki adımlık vadi gerektiriyor (5 çıkar, 10 girer) ve
zincir 27'ye indiğinde çizelge +4 ödeyemeyecek kadar soğumuş oluyor.

Ölçek karşılaştırması iddiayı keskinleştiriyor: aynı örnekte BB-CVC 27'yi
**deterministik** olarak 53 slot ve 482 iletimde buluyor, ANNEAL ise ortalama
109 slot ve 1136 iletim harcayıp aynı ağırlığa varıyor. Yani brief'in tahmini
**iletim maliyeti tarafında doğrulanıyor** (4-10 kat), **ağırlık üstünlüğü
tarafında çürütülüyor**. İki yarı da rapora girer.

### Brief kusuru: Trickle şartnamedeki haliyle kullanılamaz

HELLO periyodunu alıcının `stale_periods·T_hello` süresinin ötesine katlamak
komşuların birbirini düşürmesine yol açıyor, epoch sıfırlanıyor ve hiçbir şey
yakınsamıyor: 20 async koşumun 20'si geçersiz, üstelik iletim **artıyor**
(1122 -> 3268). Sebep yapısal: alıcı zaman aşımını KENDİ `T_hello`suna göre
hesaplıyor ve göndericinin uzattığı periyot hiç ilan edilmiyor.

Yumuşak-durum penceresinin altına kıstırılınca Trickle brief'in söylediğini
yapıyor: 1122 -> 665 iletim, sıfır geçersiz. Yani mekanizma sağlam, şartname
eksik. Gerçek çözüm periyodu çerçeveye koymaktır.

### Yöntem: örtüşmeli ölçüm yakınsama gibi görünür

bb-core'un Döngü B hatası iki kez saklandı. Birincisi `.tex` η'yı hiç vermiyor
ve kenar başına uygulanınca düğümün yükü periyot başına `deg·η·Δℓ/2` oynuyor,
η=1 ve derece 4'te bu iki kat aşım demek ve yineleme salınıyor. İkincisi,
**her ikinci periyotta örneklemek** salınımı "kararlı ama dengesiz sabit nokta"
gibi gösteriyor. Örtüşmeli (aliased) bir ölçüm yakınsama gibi okunur.

Ayrıca paylaşım işareti hatası `y = ½`de görünmez olduğu için `.tex`'teki elle
denetlenebilir her örnek iki yanlış işaretle de geçiyordu. Belgeyle yakalanamaz,
yalnız bağımsız küresel enerji referansıyla yakalanır, ve o referans da
mutasyonla sınandı.

### DÜZELTME: ilk ölçüm YANLIŞ BÜYÜKLÜĞÜ ölçüyordu (bb-core, aynı gün)

Yukarıdaki tablo **son donmuş durumun** ağırlığıdır. Tavlamanın gördüğü **en iyi
geçerli durum** ölçüldüğünde tablo belirgin biçimde değişmektedir:

```
ağırlık            25  26  27  28  29  30
son durum           3  13  20  14   3   6
EN İYİ GÖRÜLEN     12  25  14   7   1   1
brief              ~29 ~20  <-- 11 tanesi 27-29 -->
```

Son durumda 25+26 payı 16/60 (%27) iken, en iyi görülende 37/60 (%62)
olmaktadır; brief 49/60 (%81) beklemektedir. Yani **brief'in sayıları, son
durum dağılımı olarak değil, en-iyi-görülen dağılımı olarak çok daha iyi
açıklanmaktadır.** Aradaki fark kapanmamakta ama "%5'e karşı %48" gibi bir
uçurum da kalmamaktadır. Bir önceki paragrafın "optimum %5" ifadesi bu yüzden
yalnız son durum için doğrudur ve tek başına yanıltıcıdır.

**Altta yatan olgu ölçülmüştür: 60 koşumun 29'unda son durum, o koşumda
görülen en iyi geçerli durumdan kötüdür; ortalama fark 2,17 ve en büyüğü
8,0'dır.** Bu bir hata değil Metropolis'in tanımıdır: zincir yokuş yukarı adım
kabul ettiğinden son durum bir yerel minimumdur ama görülen en iyi durum olmak
zorunda değildir.

Burada `.tex` ile standart tavlama ayrışmaktadır ve belge bunu fark etmemiştir.
`.tex` §13 "durdurulduğu anda **son** geçerli çözüm raporlanır" demektedir;
standart tavlama ve bb-figures'ın anytime sözleşmesi ise **en iyi** geçerli
çözümü saklamaktadır. İkisi farklı algoritmalardır ve 60 tohumun 29'unda farklı
cevap vermektedir.

Sessizce biri seçilmemiştir. `run_anneal` ikisini de vermektedir ve **takım
lideri kararı şudur: rapora SON DONMUŞ DURUM girer.** `total_weight` odur ve
CSV'ye o yazılır. Gerekçe üç katmanlıdır: brief zaten "son geçerli çözüm"
demektedir, yani son-durum şartnameye uygundur; en-iyi-görülen bir gözlemci
büyüklüğüdür; ve gerçekten üretilmesi sayılmamış bir convergecast maliyeti
ister.

Görülen en iyi, `observer_best_weight` ve `observer_best_cover` adlarıyla
sözleşme DIŞI alanlarda durmaktadır. Ad `observer_` ile başlamaktadır ve bu
üslup değil kuraldır: **bu değer hiçbir tabloda ya da şekilde çıplak
geçmemeli**, her geçtiği yerde gözlemci sınırı olduğu ve sayılmamış bir
convergecast gerektirdiği yazılmalıdır. Etiket metni `AnnealRun.OBSERVER_LABEL`
olarak kodda alanın yanında durmaktadır, çünkü yoruma yazılan bir uyarı
tabloya kopyalanmaz.

Bu kararın asıl dayanağı projenin kendi gerekçesidir: eski MWCCVC-MININET kodu
küresel çizgeden cevap kurduğu için dağıtık sayılmamıştı. Küresel bilgiyle
hesaplanmış bir "en iyi görülen"i V6'nın sonucu diye yazmak, aynı hatayı kendi
rozetimizle tekrarlamak olurdu.

**Kritik uyarı: "en iyi görülen" bir GÖZLEMCİ büyüklüğüdür.** Geçerlilik
örtülülük, bağlılık ve kapasite demektir ve üçü de bir atlamalık bilgiyle
bilinemez. Dolayısıyla bu değeri dağıtık sistemin kendisi raporlayamaz;
raporlayabilmesi için düzenli bir convergecast gerekir, ki o da Faz 5b'nin
TREE/STABLE düzeneğidir ve maliyeti `tx`e eklenmek zorundadır. Şekil 8'in
başlığı bu ayrımı söylemelidir, aksi hâlde eğri sistemin kendi hakkında
bildiği bir şeymiş gibi okunur.

### Ek: kapasite V6'da erken fazları da etkiler

Takım liderinin "Faz 0-4 k'dan bağımsız, bayt bayt aynı" ölçümü **V6 için
geçerli değildir.** ANNEAL'ın enerjisinde `λ_k` terimi bulunduğundan donma
öncesi fazlar yapı gereği k duyarlıdır; BB-CVC ile paylaşılan yalnız donma
sonrası kuyruktur. Bir kez kalibre edip kapasiteyi yalnız kuyrukta değiştirmek
BB-CVC kollarında doğru, V6'da yanlıştır.

### Ek: alıcı tarafı kırılımı ayrı sayılmak zorundadır (şekil 5)

`by_phase_tx` GÖNDERENİN fazıdır ve doğrudur. Aynı kalıpla bir `by_phase_rx`
eklemek, gönderenin fazını alıcının adıyla yazmak olurdu. Ölçülmüştür: her
tick'te faz atlayan düğümlerle kayıpsız senkron koşumda gönderen kırılımı
`{0:10, 1:10, 2:10, 3:10, 4:10}`, alıcı kırılımı ise `{1:30, 2:30, 3:30, 4:30}`
çıkmaktadır, çünkü slot t'de gönderilen çerçeve slot t+1'de işlenmektedir.
Küresel toplamlar eşit olduğundan bu fark bugüne kadar görünmemiştir; faz
kırılımı görünmez olmaktan çıktığı yerdir.

Alıcı sayaçları bu yüzden `SimNet.deliver()` içinde, çerçeve İŞLENDİĞİ anda
tutulmakta ve atıf adın içinde geçmektedir: `rx_at_receiver`,
`rx_by_receiver_phase`, `bytes_rx_by_receiver_phase`,
`rx_by_receiver_phase_type`. `rx_delivered` bunun yerine geçemez çünkü
`_enqueue` anında artmakta, yani bir fazda kuyruğa girip başka fazda işlenen
çerçeveyi yanlış faza yazmaktadır; anlamı `mnwifi/collect.py` ona bağlı olduğu
için değiştirilmemiştir.

Toplamlar eşit DEĞİLDİR ve olmamalıdır: koşum sonunda yolda kalan çerçeve
`Counters.rx`e yazılmış ama hiç işlenmemiştir. Kayıpsız kalibrasyonda üretilen
teslim 600, tüketilen teslim 570'tir ve aradaki 30 tam olarak son slotta
gönderilip teslim edilmeyen çerçevelerdir.

## 26. Kıyas verisinin üç sınır sorunu (bb-figures, koşucu kurarken)

Gerçek veri kümesi, sentetik çizgelerde hiç görünmeyen üç sorunu açtı. Üçü de
sessiz uyarlamayla değil **açık sütunla** kapatıldı.

**0-indeksli veri kümesi.** `mac_for_id(0)` için hash16 ön-görüntüsü yok; kod
yaklaşık 24 saniye tarayıp kalkıyor, dolayısıyla her veri kümesi satırı hata
veriyordu. Örnekler 1..n olarak yeniden etiketleniyor ve `relabelled` sütuna
yazılıyor.

**Gerçek sayılı ağırlıklar.** Veri kümesi 76,168... gibi ağırlıklar veriyor,
düğüm kodu ise tam sayı istiyor (FPU yok, brief §3.6). `prepare()` kayıtlı bir
`weight_scale` ile niceliyor (varsayılan 10, ölçülen bağıl hata %0,13),
16.16 int32 anahtarını taşıracak ölçeği reddediyor, ve **aynı** nicelenmiş
örneği kesin çözücüye de veriyor, böylece oran tek bir problem içinde kalıyor.

**`mis_nbrs_max=5` bağlıyor — bu G8'in pratikteki çarpması.** Varsayılan bir UDG
varsayımıdır ve kıyas verisi birim disk çizgesi değildir; n=100/m=400 altı MIS
komşusuna çıkıp kalkıyor. BULGU 3'te aynı olguyu çözümsel olarak ölçmüştüm
(n=200'de 200 düğümün 200'ü 5'i aşıyor). İki harness birbirinden almadan aynı
sonuca vardı. Artık açık seçenek (varsayılan 32), satır başına kayıtlı, ve
`payload_at_cap` sütunu var: **bağlayan bir tavan, şekil 6'nın raporladığı
ölçümü tam da sansürler.**

### Başarısızlık maliyeti, kıyas verisinde ölçülmüş hali

Önceki 50 kat tahminim, Faz 4 düzeltmesinden ÖNCE ve kendi kopuk çizgelerimde
ölçülmüştü, dolayısıyla geçersizdir. Kıyas verisindeki doğru sayı:

```
çözülemeyen koşum ortalama  1789 slot,  56543 iletim
başarılı koşum   ortalama    123 slot
oran 14,5 kat
```

Ayrıca n=100/m=400 k=4'te (kanıtlanabilir uygunsuz) 369 slot / 23653 iletim,
aynı örnek k=10'da 30 slot / 4346 iletim.

### Yöntem: doğru sayılan filtre yanlış yerde

bb-figures'ın kendi özetinde bulduğu hata, benim kopuk çizge hatamla aynı
biçimdedir: bir yerde (oranlarda) doğru olan uygunsuz-örnek filtresi, ait
olmadığı yere (durum envanterine) da uygulanınca başarısızlıkları görünümden
siliyordu, `ok=33` çıkıyordu. İki sayı artık yan yana basılıyor.

### Yöntem: hayatta kalma testi nasıl yazılır

Doğru kalıp, iki oranın eşit olduğunu iddia etmek DEĞİLDİR. Bir kolu bir tohumda
kasten bozup ortak altkümenin **küçüldüğünü** iddia etmektir. Eşitlik iddiası,
ortak altkümeyi hiç hesaplamayan bir kodda da geçerdi.

## 27. SENTEZ: belgenin yapısal savları tuttu, nicel tahminleri tutmadı

Bugünkü bütün ölçümler bir araya konunca belirgin bir örüntü çıkıyor ve bu
örüntü tek tek bulgulardan daha çok şey söylüyor.

### Tutan yapısal savlar

| Sav | Durum | Nerede sınandı |
|---|---|---|
| Her CVC bir CDS'tir (G1) | tuttu | Faz 2'nin temeli |
| CDS verilince yalnız iki ucu dışarıda kenarlar açıkta (G2) | tuttu | V5'te Bloom omurgayı CDS olmaktan çıkarınca G2 savı çöktü ve G[C] koptu, yani bağımlılık DOĞRUDAN gösterildi |
| `\|C\| >= ceil(\|E\|/k)` alt sınırı | tuttu | her uygunsuzluk denetiminde |
| Hakimi yönlendirmesi | tuttu | kapasite uygunluğu bunun üzerinden çözülüyor |
| Faz 0-4'ün kapasiteden bağımsızlığı | tuttu (BB-CVC kollarında) | k=4/6/8'de bayt bayt aynı |

Yapısal savlar yalnız doğrulanmadı, biri **çürütülerek** doğrulandı: G2'nin
önkoşulu bozulunca sonucu da bozuldu.

### Tutmayan nicel tahminler

| Tahmin | Ölçülen | Madde |
|---|---|---|
| G8: bağımsız komşu sayısı sabit (<=5) | n=200'de 200 düğümün 200'ü aşıyor; 6/9/13/15/17 | 3 |
| §5/1: 64 B Bloom mesajı küçültür | derece 32'ye kadar BÜYÜTÜR; bizim ortalamamız 6-16 | 24 |
| §5: yoğun çizge 250 B'yi aşar | aşmaz, komşu tablosu 64'te önce bağlar (143 B) | 24 |
| §5/2: parçalama tx'i artırır | sıralı parçalamada sıfır ek tx; yalnız patlamalı tasarımda artar | 24 |
| §5/2: Trickle iletimi düşürür | şartnamedeki haliyle KULLANILAMAZ; 20/20 geçersiz, tx artıyor | 25 |
| §6.5: 60 tohumda ~%48 optimum | son durumda %5, en iyi görülende %20; brief'in sayıları en iyi görülen dağılımı gibi duruyor | 25, 29 |
| §6.5: "son geçerli çözüm" raporlanır | tavlama en iyi geçerliyi saklar; 60 koşumun 29'unda son durum daha kötü, belge ayrımı fark etmiyor | 25 |
| §6: "MST yanlış ağaç" | kıyas verisinde MIS+bağlayıcı ile ayırt edilemez (1,005 ortalama, aynı ortanca) | 30 |
| Maliyet tablosu | LINK el sıkışmasını (4m) ve gerçek bootstrap'ı hiç saymıyor | 1, 16 |
| Faz 4 derinliği D parametre | D>3 saf maliyet; ttl 8 aynı cevap için 3,1 kat slot | 18 |

### Okuması (bb-bootstrap'ın keskinleştirdiği hali)

Belgenin **matematiği sağlam, kalibrasyonu değil.** Ama asıl kullanışlı ifade
mekanizmadır: **tutmayan her tahmin, bizimkiyle uyuşmayan bir rejimden
taşınmış bir sayısal beklentidir.**

| Tutmayan tahmin | Taşındığı rejim |
|---|---|
| G8'in sabit boyutu | birim disk çizgesi |
| Bloom'un boyut kazancı | belirli bir derece aralığı |
| ANNEAL dağılımı | elle işlenmiş tek bir örnek |
| "MST yanlış ağaç" | kenar ağırlığı sezgisi |

Yapısal savlar (G1-G5) ispat temellidir ve rejime bağlı değildir, bu yüzden
istisnasız tuttular. G2 kıyas verisinin 310 örneğinin tamamında, üstelik iki
ayrı omurga kurulumuyla doğrulanmıştır.

Bu, "belge sık sık yanılmış"tan keskin bir ifadedir ve bir sonraki okuyucuya
**kullanılabilir bir talimat** verir: teoremlere güven, sayılara güvenme,
sayıları kendi rejiminde yeniden ölç.

Bu, kusur bulma egzersizi değildir. Aksine tasarımın en değerli tarafı budur:
yapısal savlar doğru olduğu için algoritma çalışmakta, nicel tahminler yanlış
olduğu için de **ölçmeye değer** bir iş kalmaktadır. Tahminlerin hepsi tutsaydı
deneyin bir şey öğretmesi gerekmezdi.

### Kayıt için: hiçbiri parametre oynanarak bulunmadı

Sekiz uyumsuzluğun sekizi de belgedeki parametrelerle koşularak ölçüldü.
Uydurulmuş bir uyum, dürüst bir uyumsuzluktan değersizdir ve bu kural takıma
her görev dağıtımında yazıldı.

### Bekleyen

V1-DFS'in (Savage 2-yaklaşım tabanı) gerçek dağıtık kolu henüz koşmadı. Ön
ölçüm DFS omurgasının %25 ağır olduğunu ve farkın n ile büyüdüğünü söylüyor,
ki kanıtlı bir sınırın taşıması gereken profil budur. V4 tarafı kıyas verisinde
kapandı (madde 30) ve **benim kendi savım testten sağ çıkmadı**: ölçümü gerçek
ağırlıkların bulunduğu yere taşıtmamın gerekçesi doğruydu, tahmini değildi.

## 28. KAPSAM DÜZELTMESİ: 6n+4m yalnız senkrondur (bb-figures yakaladı)

Madde 16'daki özdeşliği kapsamsız yazdım. Fitim yalnız senkron koşumlardaydı,
metin ise koşulsuz okunuyordu. bb-figures bağımsız ölçüp yakaladı, kendi
üreticimde doğruladım:

```
  n     m   sync faz0   async faz0   6n+4m   async sapması
 40    93         612          572     612          -%6,5
 60   203        1172         1113    1172          -%5,0
 80   312        1728         1648    1728          -%4,6
```

Sapma her koşumda negatif, dolayısıyla rastlantı değil.

**Bu benim aynı biçimdeki ÜÇÜNCÜ hatamdır:** adı konmamış bir öncül altında tam
doğru olan bir sayı yayımlamak. Birincisi kopuk çizgeler, ikincisi tanığın
kapsamı, üçüncüsü bu. Örüntü şu: bir sayı ne kadar temiz çıkarsa, hangi
koşullarda ölçüldüğünü yazma ihtiyacı o kadar az hissediliyor, oysa tam tersi
gerekiyor.

### Mekanizma: bb-figures'ın açıklaması ölçümle tutmadı

bb-figures sebebi **atıf sınırı** sandı: faz-0 tx gönderenin o andaki fazına
yazılıyor, asenkronda düğüm ortak slot sınırı yerine kendi tikinde faz
değiştiriyor, dolayısıyla son periyodik HELLO'sunu yaymadan Faz 0'dan çıkabilir.
Bu sınanabilir bir iddiadır: çerçeveler yalnız başka faza yazılıyorsa **Faz 1'de
fazladan görünmeleri** gerekir.

Görünmüyorlar:

```
n=40  sync : faz0 612, faz1 75, faz0+1 687, toplam HELLO 821
      async: faz0 572, faz1 63, faz0+1 635, toplam HELLO 742
```

Faz 1 de düşüyor, toplam da düşüyor. Çerçeveler kaymıyor, **hiç gönderilmiyor**.

**Gerçek mekanizma:** `6n`'deki 6, ortak keşif penceresinin slot cinsinden
uzunluğudur ve senkronda sabittir çünkü herkes aynı slot sınırına bağlıdır.
Asenkronda ortak pencere yoktur, keşfini erken bitiren düğüm yaymayı bırakır ve
en yavaşı beklemez. Yani `6` orada bir sabit değildir ve özdeşliğin katsayısı
yoktur, farklı bir katsayısı da yoktur.

Bu, madde 16'daki "sync/async farkının tamamı HELLO'dadır" bulgusuyla
tutarlıdır: asenkron keşifte daha az iş yapmaktadır, işi başka yere yazmamaktadır.

**LINK terimi zamanlayıcıdan bağımsız kalmaktadır** (kenar başına tam 2,000,
iki zamanlayıcıda da). Dolayısıyla doğru ifade şudur: el sıkışması terimi
zamanlayıcıdan bağımsız, keşif terimi değil.

### Yöntem notu

Bir teşhisi bildiren kişi doğru kusuru bulmuş olsa bile mekanizması yanlış
olabilir. bb-figures kapsam hatasını doğru yakaladı, sebebini yanlış koydu, ve
sebep ancak sınanabilir bir tahmine çevrildiği için ("kayan çerçeveler Faz 1'de
görünmeli") ayırt edilebildi.

## 29. BULGU: `.tex` "son geçerli" diyor, tavlama "en iyi geçerli" yapar

**Bu maddenin tam metni 25'in içindedir**, çünkü bb-core ile aynı bulguyu
paralel yazdık ve onlarınki daha eksiksizdi (`observer_` adlandırma kuralı,
`AnnealRun.OBSERVER_LABEL`, şekil 8 başlık şartı). Başlık aranabilirlik için
duruyor, içerik çoğaltılmıyor.

Özet: 60 koşumun 29'unda son durum, o koşumda görülen en iyi geçerli durumdan
kötüdür (ortalama fark 2,17, en büyük 8,0). Metropolis yokuş yukarı kabul
ettiği için bu bir kusur değildir. Ama `.tex` "son geçerli" şart koşarken
standart tavlama "en iyi geçerli" saklar, **bunlar farklı algoritmalardır ve
belge ayrımı fark etmemektedir.** Takım lideri kararı: rapora son donmuş durum
girer, en iyi görülen yalnız etiketli gözlemci sınırı olarak geçer.

## 30. BULGU: "MST yanlış ağaç" savı kıyas verisinde DESTEKLENMİYOR (V4 null)

bb-bootstrap, 310 Dagdeviren örneğinin tamamında üç omurgayı aynı yaklaşık
Faz 3 büyümesiyle karşılaştırdı. Örtü ağırlığı, MST'ye göre:

```
omurga            ortalama  ortanca  MST'den kötü
MST-iç                1,000    1,000    -
MIS+bağlayıcı         1,005    1,000    112/303
DFS-iç                1,247    1,227    300/303
```

MIS+bağlayıcı ile MST **ayırt edilemez**: %0,5 ortalama fark, aynı ortanca, ve
MST örneklerin yaklaşık üçte birinde kaybediyor, ki bu yazı tura demektir.
Brief'in "MST neden yanlış ağaç" savı, gerçek düğüm ağırlıklarının bulunduğu
yerde desteklenmemektedir.

**Kendi savım da testten sağ çıkmadı.** Ölçümü rastgele geometrik çizgelerden
kıyas verisine taşıtmamın gerekçesi, MST'nin KENAR ağırlığını, MWCCVC'nin ise
DÜĞÜM ağırlığını küçültmesi ve ikisinin ancak gerçek ağırlık dağılımında
ayrışabileceğiydi. Gerekçe testi haklı çıkardı, tahmini çıkarmadı: ayrışma
görünmedi. Raporda böyle yazılır, sessizce düşürülmez.

**DFS tarafı daha ilginç.** %25 kötü, 303'ün 300'ünde kötü, ve fark n ile
BÜYÜYOR (n=15-25'te %20, n=200'de %30, n=1000'e kadar sürüyor). Kanıtlı bir
sınırın taşıması gereken profil tam olarak budur. Mekanizma ham sayılarda daha
da açık: Faz 3 koşmadan önce DFS toplam düğüm ağırlığının %93,9'unu taşırken
MST %18,1 taşıyor, çünkü yoğun örneklerde DFS ağaçları uzun ve yol benzeri
oluyor, neredeyse her düğüm iç düğüm sayılıyor; MST ağaçları ise sığ ve çok
yapraklı. Faz 3 büyümesi 76 puanlık farkı 25'e sıkıştırıyor ama kapatmıyor.

**Uyarılar tabloya girer, dizide kalmaz:** büyüme kuralı Faz 3'ün yaklaşığıdır,
MIS+bağlayıcı gerçek Faz 1'in yaklaşığıdır, aynı yaklaşık bir kez zaten
yanıltmıştır, ve 310 örneğin 7'si en az bir kolda geçersiz örtü ürettiği için
dışlanmıştır. Bu tablo YÖNÜ kurmaktadır.

### DOĞRULANDI: gerçek dağıtık kollarda da null (2026-09-15)

Yukarıdaki ön ölçüm yaklaşık Faz 3 ile yapılmıştı. `node_factory` inince gerçek
dağıtık kollar koştu, n<=25, k=4, sync, hücre başına bir tohum, 13 örnek:

```
kol   geçerli  kesilmiş  çözülemedi  ort. ağırlık  slot    tx
V2          8         5           0        1149,2   120  2499
V4          7         5           1        1096,4   104  2233
```

İkisinin de geçerli olduğu 7 örnekte eşleştirilince: **V4 %1,11 daha hafif ve
7'nin hiçbirinde ağır değil.** Yani sav yalnız desteklenmiyor değil, MST
hafifçe önde.

**Hedefi doğru tutmak gerekiyor (bb-algo'nun uyarısı).** Brief'in G3'ü, DFS
özelliğini yalnız **ağırlıksız** tepe örtüsü ve k=sonsuz için iddia eder.
Bizim örneklerimiz ağırlıklı ve k sıkı. Dolayısıyla MST'nin önde çıkması
**G3'ün çelişmesi değildir**; brief'in G3'ün desteklediğinden çok daha geniş
ifade edilmiş "MST yanlış ağaç" yorumunun çelişmesidir. Raporda ikisi ayrılmalı,
yoksa dokuzuncu uyumsuzluk fazla geniş hedefe atılmış olur. V4'ün slot ve tx sayıları karşılaştırılabilir değildir, çünkü
omurgasını kendi kurmuyor (madde 30'daki kural).

**Kapsam tam olarak şudur ve sayıdan ayrılmaz:** n<=25, k=4, hücre başına tek
tohum, **yalnız sync — asenkron zamanlayıcı hiç koşulmadı**, 13 örnek koşuldu,
**7'si eşleşti** (iki kolun da geçerli olduğu). Kol başına 5 kesilmiş koşum bu
kapsamın dışında kalıyor. Merkezî ön ölçüm ayrıca yaklaşık Faz 3 ve yaklaşık
Faz 1 kullanıyor, 310 örneğin 7'si dışlanmış.

**Yön kurulmuştur, büyüklük kurulmamıştır.** Yedi eşleşmiş örnek bir eğilim
gösterir, bir kat sayısı değil.

## 31. YÖNTEM: sınıfın OLUMLU karşılığı, çelişebilen iki görüş

Gün boyu kovaladığımız hata sınıfı "çelişmesi gereken taraf çelişemiyor"du.
bb-core'un V6 düzeltmesi bunun **aynadaki görüntüsünü** verdi ve savunmanın
nasıl kurulacağını söylüyor.

bb-core ölçtükleri şeyin yanlış büyüklük olduğunu **akıl yürüterek bulmadı**.
bb-figures'ın sweep sözleşmesi izi (trace) dışarı vermeyi şart koştuğu için
izin son örneği (27), koşumun raporladığı ağırlıkla (28) daha ilk uçtan uca
denetimde **gözle görülür biçimde çelişti**. Sözleşme işi yaptı.

bb-figures o alanı istemeseydi son-durum dağılımı hikâyenin tamamı olarak
raporlanmaya devam edecek, 60 koşumun 29'undaki fark görünmeyecekti.

**Genel biçim:** aynı koşumun BAĞIMSIZ TANIMLANMIŞ iki görünümü yan yana
konunca, biri ötekini yanlışlayabilir. Suç ortağı taklitte iki görüş aynı
varsayımı paylaştığı için çelişemiyordu; burada iki görüş ayrı ayrı
tanımlandığı için çelişebildi ve çelişti.

**Pratik sonuç:** çapraz görünümleri azaltmak değil ÇOĞALTMAK gerekir. Bir
büyüklüğü iki bağımsız yoldan raporlamanın bedeli küçük, ödülü ise ölçümün
kendisinin yanlış olduğunu öğrenmektir. Bugünün üç hatası da (taklit ağ,
sanal saat, varsayılan değer) tek görüşlü ölçümlerdi.

Aynı kalıbın öteki örnekleri: V5'in üçlü denkliği (bağımsız küme cebiri
referansı, kural katmanı, gerçek dağıtık koşum), bb-core'un küresel enerji
referansı, benim maksimum derece 36 ölçümümün bb-bootstrap'ınkiyle bağımsız
buluşması, ve `mis_nbrs_max`'ın bende çözümsel bb-figures'ta çökme olarak
çıkması.

### Yapısal zorlama, belgelenmiş uyarıdan üstündür

bb-core "hiçbir tabloda çıplak geçmesin" talimatını docstring'e yazmadı, üç
katmanda yapısal hale getirdi: alan adı `observer_` ile başlıyor, uyarı metni
`AnnealRun.OBSERVER_LABEL` olarak alanın yanında kodda duruyor, ve
`adapt_result` bu alanları `VariantResult`a hiç taşımıyor, yani gözlemci sınırı
CSV'ye **yapısal olarak ulaşamıyor**. Eski çıplak adlar da kaldırıldı, böylece
onlara yazılmış kod sessizce değil gürültüyle kırılıyor.

Yoruma yazılan bir uyarı tabloya kopyalanmaz; ada yazılan uyarı kopyalanır.

## 32. BULGU: kesilen koşum kendi bayraklarında bunu SÖYLEMİYOR (iki kez düzeltildi)

Bu madde iki kez yanlış yazıldı ve ikisi de benim hatamdı. Nihai hali aşağıda,
yanlış sürümler gerekçeleriyle duruyor.

**Birinci yanlış:** "kanıtlanabilir uygunsuz örnekte yanlış başarı" diye
raporladım, sanki algoritma imkânsız bir atamayı geçerli sayıyormuş gibi.

**İkinci yanlış, daha ağırı:** bunu bb-algo'nun sürekli yazdığı bir dosyaya
karşı **yeniden koşmadan** acil olarak eskale ettim. Oysa "başkasının eşzamanlı
düzenlenen dosyasındaki kırmızıyı atfetmeden önce yeniden koş" kuralını o gün
bb-bootstrap koymuş, ben de üç ajana ev kuralı diye iletmiştim. Kendime
uygulamadım. bb-algo güncel kodda yeniden üretilemediğini gösterdi ve sahiplik
haritamızın birebir aynı olması, aynı kod yolunda bayat bir bayrak okuduğuma
iyi kanıt.

bb-algo'nun bunu sessizce "düzeltmek" yerine bildirmesi doğru davranıştı:
olmayan bir kusuru kovalamak, üstelik benim eskale gerekçem ("yeşil kod yanlış
cevap dönüyorsa o vakayı kapsayan test yoktur") üzerinden onun etrafına test
uydurmayı da haklı çıkarırdı. **Yanlış bir bulgu böyle kalıcılaşır.**

### Geriye kalan gerçek, temiz izole edilmiş hali

Sayma sınırının ateşlemediği UYGUN bir örnekte:

```
n=50, m=144, k=6   (n*k = 300 > m, counting_bound sessiz)

max_ms=  2000 -> 10 slot, converged=False, bayraklar temiz, DOĞRULAYICI: 242 ihlal
max_ms=  5000 -> 25 slot, converged=False, bayraklar temiz, doğrulayıcı temiz
max_ms= 20000 -> 26 slot, converged=True,  bayraklar temiz, doğrulayıcı temiz
```

İki saniyelik bütçede koşum 10 slotta kesiliyor, 242 ihlal taşıyor, ve ne
`unresolved` ne `infeasible` diyor. Yani **kesinti koşumun kendi bayraklarında
görünmüyor**, yalnız `converged=False` alanında görünüyor.

Benim ilk K6 gözlemim de büyük olasılıkla buydu: kesilmiş bir koşum, yanlış
başarı değil. `converged`i o an okumadım, oysa söyleyecek olan alan oydu.

### Tüketici bunu zaten yakalıyor (bağımsız doğrulandı)

`sweep.py:886-894`'te `not res.converged` denetimi, geçerlilik denetiminden
ÖNCE gelir, dolayısıyla bu satırlar `ok` değil `not_converged` olur. Kodu
okuyarak doğruladım. Yani bugün hiçbir şeyi kirletmiyor.

Kalan artık dar: koşumun kendi bayraklarını `converged`i okumadan yorumlayan
biri, kesilmiş koşumu başarılı sanır.

### Yine de duran ders

Süit bu ölçümler boyunca yeşildi. Yeşil süit doğruluk kanıtı değildir. Ama bu
maddenin asıl dersi o değil: **kendi koyduğun usul kuralını en çok, acil
sandığın anda çiğnersin.**

## 33. DÜZELTME: yarıçap-1 tanığının tamlığı %88,6, benim 30/30'um değil

bb-algo tanığı 580 vakada sınadı (UDG, G(n,p) p=0,08-0,45, ve kasten yerel yoğun
kurulan klik-artı-kuyruk; n=10..35, k=1,2,3,4,6):

```
tanık ateşledi & küresel uygunsuz : 225
tanık ateşledi & küresel UYGUN    :   0   <- sağlamlık ihlali
tanık sessiz  & küresel uygunsuz  :  29   <- tamlık boşluğu
tanık sessiz  & küresel uygun     : 326
```

**Sağlamlık kusursuz** (225'te 0), ki sayma kanıtının gerektirdiği budur.
**Tamlık 225/254 = %88,6**, oysa ben 30/30 yayımlamıştım. Benim 30 vakam dar bir
aileden geliyordu; G(n,p) ve klik-artı-kuyruk ailelerinde hiçbir kapalı
komşuluğun tanıklık etmediği gerçekten uygunsuz örnekler var. Kendi uyarım
("tamlık yalnız görgüldür") doğruydu, bu ona sayı koyuyor: **düşme yolu
zorunludur, formalite değildir.**

**Küresel sayım eklemek %98,4'e çıkarıyor.** `m > k·n` testi (doğrulayıcının
`lower_bound_g6` diye zaten hesapladığı şey) tanıkla iç içe değil tamamlayıcıdır:

```
yalnız yarıçap-1 : 40
yalnız küresel   : 25
ikisi birden     : 185
hiçbiri          :  4
```

Temiz bir kaçan örnek: k=1, n=10, m=12. Sayarak küresel olarak uygunsuz, ama
her kapalı komşuluğun payı sıfır ya da daha iyi, dolayısıyla yarıçap-1 bunu
**yapısal olarak göremez**. Erken çıkış yazılırken ikisi birlikte kurulmalıdır.

## 34. BULGU: doğru cevap, geçersiz argüman (bb-algo)

bb-algo'nun kendi kodunda bulduğu hata, bu projenin en iyi tek cümlelik dersi.

Düğüm uygunsuzluğu şundan ilan ediyordu: "benim F=0 VE bütün komşularımın F=0".
Bu `.tex`'in C=V koşulu için iki atlamalık tanık diye belgelenmişti. **Hiçbir
şeyin tanığı değil**: yalnız iki atlamalık görüşümün örtünün içinde kaldığını
söylüyor, öteki 89 düğüm hakkında bir şey söylemiyor. 62 ve 94 numaralı düğümler
bu koşulu |C|=89/100 iken sağlıyordu.

bb-algo'nun kendi "INFEASIBLE asla yanlış alarm değildir" testi bunu kaçırdı,
çünkü yalnız küçük çizgelerde koşuyordu ve orada hatalı akıl yürütme kazara
doğru cevabı veriyordu.

**Sayının okunuşu:** bu, 8'de 1 yanlışın 8'de 0'a inmesi değildir. **8'de 4
desteksiz iddiadır, üçü kazara doğru çıkmıştır.** Geçersiz argümanla varılan
doğru cevap, doğru cevap değildir, sınanmamış cevaptır.

Düzeltme: düğüm artık uygunsuzluğu hiç iddia etmemekte, "çözemedim" demekte,
doğrulayıcı yetkili kalmaktadır. `local_infeasibility_witness()` bilgi yokken
`False` değil **`None`** dönmektedir, çünkü "hesaplayamıyorum" ile "tanık
ateşlemedi" farklı ifadelerdir ve ikisini karıştırmak kaldırılan hatanın tam
biçimidir.

## 35. BULGU: sahipsiz kenarın üçüncü örneği bir PROTOKOL YARIŞI

İlk ikisi muhasebe kaymasıydı, üçüncüsü değil. 6 numaralı düğüm (6,17) kenarını
17'ye PUSH ederken, 17 aynı slotta aynı kenarı 6'ya HANDOVER etti. İki aktarım
da `.tex`'in rezervasyon disiplinine göre **tek tek doğruydu**, ikisi de kabul
edildi, iki taraf da bıraktı, kenar kimsede kalmadı.

`.tex`'in kuralı tek yönde tek bir aktarım üzerine akıl yürütmekte, aynı kenarın
zıt yönlü iki aktarımını kapsamamaktadır. Düzeltme anahtar üzerinden
antisimetrik: küçük anahtarlı ucun isteği kazanır, tam bir aktarım ilerler, ne
kilitlenme ne kayıp mümkündür.

**Üçünün de ortak yanı:** hepsi doğrulayıcının `bad_owner` denetimiyle
yakalandı, hiçbiri koşumun yanlış görünmesiyle değil. Her biri yakınsadı ve
temiz sayaçlar raporladı, üstelik yanlışken.


## 36. Çapraz görünüm mekanizması işledi: V6'nın iki çıktısı çelişti

Madde 31'de "aynı koşumun bağımsız tanımlanmış iki görünümü yan yana konunca
biri ötekini yanlışlayabilir" demiştim. Aynı gün somut karşılığı çıktı.

bb-figures'ın süpürmesinde V6-ANNEAL **195 satırın 195'inde** `cover=[]`,
`owner={}`, `total_weight=0` döndürüyor, üstelik 105 slot ve 1120 iletimle
yakınsayarak. Ama **aynı koşumun izi** `cover_size=10, weight=5328` ve
`t_first_valid_ms=0` diyor.

**Hiçbir çıktı bunu tek başına göstermiyor.** Şekil 8 yalnız izi okuyor ve
gayet sağlıklı görünüyor; CSV yalnız çözümü okuyor ve hiçbir şey örtülmemiş
diyor. bb-figures'ın kendi ifadesiyle: o gün traceslerden tertemiz görünen bir
şekil 8 yayımlanacaktı.

Not: hata kıyas verisi yoluna özgü görünüyor. Kendi UDG örneğimde (n=20, r=0,4)
V6 düzgün çalışıyor: örtü 20, sahiplik 70, `total_weight=121`,
`observer_best_weight=117`. Yani sorun `run_anneal`ın kendisinde değil, süpürme
yolunda olabilir. bb-core'da.

### Kurumsallaştırma: `trace_agrees` sütunu

bb-figures her satıra `trace_agrees` (`yes` / `none` / `no:<sebep>`) ekledi ve
`summary.md`ye çelişkide bağıran bir bölüm koydu. **Kaydediyor, hata
fırlatmıyor**, çünkü slot ve iletim sayıları gerçek ölçümlerdir ve satırı
düşürmek onları da atmak olurdu.

Bu, tek seferlik bir yakalamayı **duran bir denetime** çeviriyor. Madde 31'in
pratik sonucuydu: çapraz görünümleri çoğalt.

## 37. YÖNTEM: sayıyı rapor etmeden önce geri almak

bb-bootstrap'ın V1 simülasyonu kenar başına 1,74 jeton teklifi verdi, 2m
sınırına karşı temiz görünen bir sonuç. Raporlamadan önce geri aldılar, çünkü
simülasyon yalnız **kazanan** gezintiyi koşuyor ve öncelenmiş gezintilerin
teklifleri hiç sayılmıyor. Yani 1,74 bir alt sınır ve benim "önceleme maliyeti
çıkarsanabilir değil okunabilir olsun" koşulumu karşılamıyor.

Yaptıkları üç şey kayda değer. Sayacı `offers_winning_walk_only` diye yeniden
adlandırdılar. Kapsam sınırını docstring'e yazdılar. Ve **çıplak `offers` adının
bulunmadığını iddia eden bir test eklediler**, çünkü o ad tam da neredeyse
düştükleri yanlış okumayı davet ediyor.

Ad, uyarıyı taşıyan yerdir. Aynı ilke bb-core'un `observer_best_weight`
adlandırmasında da uygulandı (madde 31).

**Ve koşulun karşılanmadığını açıkça söylediler**, karşılanmış gibi okunan bir
sayı vermek yerine. Önceleme maliyeti gerçek koşumdaki `dfs_preempted`'dan
gelecek, simülasyondan değil.

## 38. Kolun kendi beyanı ile doğrulayıcının kararı: iki yönlü denetim

bb-figures, süpürmenin her satırına `verdict_agrees` sütunu ekledi ve **iki
yönü de** kaydetti. Ben yalnız tehlikeli yönü istemiştim.

**Yön 1 (tehlikeli):** kol başarı iddia ediyor, doğrulayıcı ihlal buluyor.
Satır `ok` değil `contradiction` olur. Tabloyu bozabilecek tek yön budur.

**Yön 2 (tespit kusuru):** kol `unresolved` ya da `infeasible` diyor,
doğrulayıcı ise temiz. Yani **kol kendi başarısını göremiyor.** Bu kurgusal bir
kaygı değildir: bb-algo aynı gün, düğümün destekleyemediği şeyleri iddia etmesi
yüzünden sağlam olmayan uygunsuzluk iddiasını kaldırdı (madde 34). Bu sütun o
biçimi bağımsız olarak yakalardı.

### Testin kurulumu (kalıp olarak alınmalı)

Yük taşıyan test, gerçekten koşan bir kol kuruyor, sonra bütün kenarları tek
düğüme yığıyor ve hiçbir bayrak kaldırmıyor, ardından satırın `ok` değil
`contradiction` döndüğünü iddia ediyor. **Üstelik kolun gerçekten başarı iddia
ettiğini doğrulayan bir önkoşul assert'i var**, yani test yanlış sebepten
geçemiyor. Ayrıca dürüst bir başarısızlığın bu sütunu TETİKLEMEDİĞİNİ iddia
eden ikinci bir test var, yani sütun her şeye ateşlemiyor.

İki yön birden sınanmadan bir denetçi hiçbir şey kanıtlamaz (madde 15).

### `status` doğrulayıcıdan türetiliyor (bağımsız doğrulandı)

Güvenmek yerine kodu okudum: `sweep.py:875-894`. `ok` için `rep.valid` şart.
Dolayısıyla madde 32'deki yanlış başarı biçimi CSV'ye geçerli kol sonucu olarak
giremez.


## 39. KOPYA KAYMASI GERÇEKLEŞTİ (uyarının doğrulanması)

Gün boyu üç kez "elle kopyalanan koşum hattı kayar" diye uyardım ve dikişi
(`_backbone_step`) ile `node_factory` kancasını bu gerekçeyle ısmarladım.
Uyarı kurgusal değilmiş.

bb-validate'in V5 kolu `run_bbcvc`in yaklaşık bir kopyasını taşıyordu. bb-algo
oturum ortasında sayma sınırı uygunsuzluğunu ve `infeasible_reason` alanını
ekleyince, **kopya bunları sessizce kaçırdı**. bb-validate'in kendi ifadesiyle:
her süpürme satırına yanlış durum yazacaktı.

Kayma gürültüyle değil sessizce oldu. Kopya çalışmaya devam etti, testleri
geçti, ve yalnız yeni alanı bilmediği için yanlış cevap üretecekti. Kancaya
geçince kopya ortadan kalktı.

**Ders:** yinelemenin bedeli yazıldığı gün ödenmez, orijinal değiştiği gün
ödenir, ve o gün kimse yinelemeye bakmaz.

### bb-validate'in düzeltmesi, ki argümanı güçlendiriyor

Bu maddeyi ilk yazdığımda kaymanın nasıl fark edildiğini atlamışım. bb-validate
kaymayı **yinelemeyi fark ederek bulmadı.** Hiç duymadığı bir alan üzerinde
`TypeError` aldı, ancak o zaman kancaların var olduğunu ve kopyasının sayma
sınırını sessizce kaçırdığını gördü.

Kritik ayrıntı şu: **yineleme baştan beri görünürdü.** İlk raporunda "bilerek
kopyalandı" diye kendisi yazmıştı. Yine de kırılana kadar davranmadı.

Yani argüman "yinelemeyi fark et" değildir, çünkü fark edilmişti.
**Argüman, kopyayı fark ettiğin gün kaldırmaktır, ısırdığı gün değil.**

## 40. DÜZELTME: 250 B sınırı bu yapılandırmada ERİŞİLEMEZ (V5, kesinleşti)

Madde 24'te "komşu tablosu 64'te önce bağlar" demiştim. bb-validate bunu
ölçerek kesinleştirdi ve sonuç brief §5'in savını daha da daraltıyor:

* komşu tablosu dereceyi 64'te sınırlıyor, ki bu 143 bayt
* tel ancak derece 118'de kalkıyor (249 B'de sığıyor, 251 B'de kalkıyor)
* **gerçekten yakınsayan en yoğun örnek maksimum derece 48, ölçülen 111 bayt**,
  çözümsel değerle birebir

Tavanın ötesinde koşum yalnız büyük değil **geçersizdir** (`RunInvalid`,
başarısız olması 89 saniye sürüyor).

Yani mesaj boyutu savı **telsizle değil BELLEKLE** sınırlıdır. Brief §5'in
"yoğun çizgeler 250 B'yi aşar" ifadesi bu yapılandırmada hiçbir zaman
gözlemlenemez. Şekil 6'da ölçülen noktaların yanına etiketli çözümsel bir çizgi
konur, uydurulmuş veri noktası konmaz.

### Wu-Li tam çizgede kimseyi işaretlemiyor

bb-validate'in bulduğu yan sonuç: tam çizgede Wu-Li hiçbir düğümü
işaretlemediği için dikişin "B baskındır" şartı **yapı gereği** düşüyor. Örtü
yine de geçerli. Testle çivilendi.

Kayda değer, çünkü bir dikiş sözleşmesinin bütün kollarda tutmadığı ilk yer.

### `naive` politika kolu deliberately KAYDEDİLMEDİ

bb-validate güvensiz olduğunu ölçtükleri kolu karşılaştırma matrisine
kaydetmedi, çünkü matriste yer almak aday olduğunu ima ederdi. Doğru karar:
ölçülmüş bir olumsuz sonuç raporda anlatılır, matriste yarıştırılmaz.

## 41. Yalnız tam süitte düşen test: sıra bağımlılığı

`test_figures.py::test_figure8...` tek başına ve bb-validate'in dosyasıyla
birlikte geçiyor, tam pakette düşüyor. Yani daha erken sıralanan bir dosyadan
kalan **paylaşılan durum** var.

bb-validate'in notu yerinde: **yalnız tam süitte düşen bir test "flaky" diye
yazılıp geçilmeye meyillidir.** Oysa sıra bağımlılığı gerçek bir hata sınıfıdır
ve testin kendisinde değil, sızdıran modülde durur.

## 42. BULGU: λ ve T oyuncak örnekten sabitlenmiş (V6, bb-core)

V6'nın 195 satırda boş örtü döndürmesinin kökü bulundu ve iki katmanlıydı.

**Birinci katman, gürültülü olan.** `AnnealParams` λ değerlerini `.tex` §13.3'ten
`12.0` diye sabitliyordu. Brief **λ > w_max** şart koşuyor ve işlenmiş örnekte
w_max = 6 olduğu için 12 bunu sağlıyor. Ama Dagdeviren kümesinde ağırlıklar
**26 ile 115** arasında. λ = 12 yaklaşık sekiz kat küçük kalınca örtüden çıkmak
94'e kadar kazanç sağlarken açıkta kalan kenar yalnız 12'ye mal oluyor. Bütün
cezalar ağırlıkla **satın alınabilir** hale geliyor, herkes örtüden çıkıyor, ve
koşum yine de `converged=True` diyor.

**İkinci katman, sessiz olan ve asıl öğretici olan.** Aynı hata sıcaklıkta da
vardı: `.tex` T₀ = 6 veriyor, ki o da tam olarak w_max. Ölçeklenmeyince, yirmi
kat ağır bir örnekte her ΔE yirmi kat büyürken T yerinde kalıyor,
`exp(−Δ/T)` çöküyor ve zincir fiilen sıfır sıcaklıkta koşuyor. **Tavlama
sessizce açgözlü inişe dönüşüyor.**

Bu ikincisi **geçerli çıktı üretiyor**, dolayısıyla hiçbir kapı yakalayamaz.
Yalnız tavlama kullanmanın sebebi ortadan kalkıyor. Birinci katman olmasaydı
ikincisi hiç bulunmayacaktı.

**Düzeltme kuralı geri kazanıyor, ayarlamıyor:** λ = 2·w_max, T₀ = w_max,
T_min = (0,05/6)·T₀. `.tex` örneğinde bunlar tam olarak 12, 6 ve 0,05 veriyor,
yani belgenin **örneklediği kural** bu. Bağımsız doğruladım:

```
agirlik carpani c    |C|   tx    slot     yorunge
      1             19   3299    166      -
     10             19   3299    166      AYNI
    100             19   3299    166      AYNI
```

Ölçek değişmezliği birebir. Ağır ağırlıklarla (26-115 aralığı) örtü dolu geliyor.

Düğüm ayrıca λ ≤ kendi ağırlığı ise başlamayı reddediyor: düğüm w_max'ı bilemez
ama kendi ağırlığını bilir, dolayısıyla bu **yerel olarak denetlenebilir gerekli
bir koşuldur**.

### Suç ortağı testin en saf hali

bb-core'un testi `min(λ) > max(W.values())` iddia ediyordu, **kendi
fikstürüne karşı**, ki orada w_max = 6. Test mutlu mesut geçiyordu, oysa adını
taşıdığı değişmez önemli olduğu her yerde sekiz kat çiğneniyordu.

> **Bir değişmezi tuttuğu yerde denetlemek, denetlemek değildir.**

Yerine 1×, 10× ve 100× ölçekte denetleyen testler, gerçek ağırlıklı bir gerileme
testi, ve beş sabiti geri getirip boş örtünün döndüğünü iddia eden bir mutasyon
testi kondu.

### V6'nın kendi uygunsuzluk tanığı yok

`AnnealRun.infeasible` BbcvcNode'un Faz 4 bayrağını okuyor, ANNEAL ise Faz 3'ün
zorunlu yük yolunu hiç koşmuyor. Dolayısıyla gerçekten uygunsuz bir örnekte V6
geçersiz örtü döndürüyor, `infeasible=True` demiyor. bb-figures o hücreleri
süzdüğü için bugün bir şey bozulmuyor, ama açık bir boşluk.

## 43. `verdict` koşum hakkında, `infeasible` örnek hakkında

bb-algo'nun kesinti düzeltmesi bir ayrımı netleştirdi ve ayrım bulgunun kendisi.

`BbcvcRun.verdict` ∈ {`solved`, `unresolved`, `truncated`} eklendi. Önerdiğim
yedek çözüm (bütçe bağladığında `unresolved` işaretle) **alınmadı ve doğru
yapıldı**: `unresolved` "yerel onarım pes etti" demektir ve bb-bootstrap'ın
sınıflandırıcısı bu anlama dayanır. Aşırı yüklemek, bir tüketicide güvenliği
öteki tüketiciyi bozarak satın almak olurdu.

**Ayrım:** `verdict` KOŞUM hakkındadır, `infeasible` ÖRNEK hakkındadır, ve
ikisi aynı anda doğru olabilir. Kısa bütçeli bir koşum kanıtlanabilir uygunsuz
bir örnekte hem `truncated` hem `infeasible=True` der. İkisini birleştirmek
doğal hatadır ve sessizce yanlış soruyu cevaplar, bu yüzden testle çivilendi.

Ad `outcome` değil `verdict` seçildi, çünkü `BbcvcRun.outcome` zaten
zamanlayıcının `RunOutcome`unu tutuyor. Farklı şeyler demek isteyen iki
`outcome` alanı sessiz hata üreticisidir.

**Süpürme için:** satır durumu `verdict == "solved"` üzerinden anahtarlanır,
bayrak yokluğu üzerinden değil.

### Gerçek maruziyet benim örneğimden kötüydü

K6/k=2 artık sayma sınırıyla maskeleniyor. Asıl açık, kanıt bulunmayan UYGUN
örneklerde: işlenmiş örnekte 2 saniyelik bütçede **|C|=3, sıfır sahiplik,
KOPUK örtü**, ve iki bayrak da False. Bu satır bir sonuç tablosuna çözülmüş
koşumdan ayırt edilemez halde girerdi.

### Her iki taraf da kendi kaydını düzeltti

bb-algo daha önce "yeniden üretilmiyor" demişti. Bunu kendisi düzeltti: iddia
algoritma hatası için doğruydu ve kontrol etmekle doğru yapmıştı, ama "orada bir
şey yok" doğru değildi, çünkü ilk raporu algoritma iddiası diye okuyup yalnız
onu sınamıştı. Kendi süiti de aynı körlüğü taşıyordu: her test yakınsamaya
yetecek bütçe veriyordu, dolayısıyla kesinti yolunun **hiç kapsaması yoktu**.

## 44. BULGU: kesilmiş koşum doğrulamadan GEÇEBİLİYOR

Benim n=50 örneğim, ikimizin de elinde olmayan bir satır üretti:

```
n=50, m=144, k=6   (sayma sınırı sessiz: n*k=300 > m)
max_ms= 2000 -> 10 slot, truncated, 241 doğrulayıcı ihlali
max_ms= 5000 -> 25 slot, truncated, SIFIR ihlal          <-- kritik satır
max_ms=20000 -> 29 slot, solved,    sıfır ihlal
```

Orta satır belirleyicidir. 241 ihlalli satırı herhangi bir geçerlilik denetimi
yakalar, dolayısıyla yeni alana hiç ihtiyacı yoktu. **5000 ms satırı ise
doğrulayıcıya temiz görünür** çünkü örtü o anda kendi içinde tutarlıdır, ama
koşum bitmemiştir ve devam etseydi değişecekti.

**Sonuç:** geçerlilik, `verdict`in yerini tutmaz. Bir satırın kol sonucu olarak
kaydedilme koşulu "doğrulayıcı memnun" değil **"koşum bitti"**dir.

Sıralama da rastlantısal değil yük taşıyıcıdır: süpürme `not converged`
denetimini geçerlilik denetiminden ÖNCE yapar. Ters olsaydı 5000 ms satırı
temiz sonuç olarak kaydedilirdi.

## 45. Tamamlayıcı usul kuralı (bb-algo'dan, benimkinden iyi)

Ben kendi hatamdan "başkasının eşzamanlı düzenlenen dosyasına atfetmeden önce
yeniden koş" dersini çıkarmıştım. bb-algo daha keskin ve tamamlayıcı bir kural
koydu:

> **Bir rapor yeniden üretilemiyorsa, "ne olabilirdi" diye sor.**

İkisi farklı hataları önlüyor. Benimki benim kötü eskalasyonumu önlerdi.
Onlarınki gerçek kusuru bir saat önce yakalardı, çünkü bb-algo ilk raporu
"algoritma hatası" iddiası diye okuyup yalnız onu sınadı, `converged`e
bakmadı, ve "yeniden üretilmiyor" deyip geçti. `converged` ikimize de açıktı.

### Ve süit yine yanıltıcıydı

bb-algo'nun 159 testinin **hiçbiri** kesinti yolunu kapsamıyordu, çünkü her test
yakınsamaya yetecek bütçe veriyordu. Bütün arıza kipi, eksiksiz görünen bir
süite görünmezdi.

> **Bir kaynak sınırını hiç zorlamayan test süiti, o sınır altındaki davranışı
> sınamamıştır; sınırsız davranışı sınamıştır.**

## 46. KARAR: iki açık madde kapatılmıyor, ikisi de SONUÇ olarak yazılıyor

bb-algo'nun bildirdiği iki açık madde karara bağlandı ve ikisinde de karar
"yapma" oldu, çünkü yapmamanın kendisi sonuç.

### Seed-4 yönlendirme sınıfı düzeltilmiyor

Ölçüldü: yarıçap 1'den 4'e kadar hiçbir topta ihlal yok, min-kesit engeli 13
atlama yayılıyor, vekâleten eskalasyon iki atlamaya erişiyor ve bu sınıfta
yapısal olarak sessiz. Bu uygulamada bir boşluk değil, **yerellik altında
problemin bir özelliği**.

Rapora şöyle girer: hiçbir yerel algoritmanın tespit edemeyeceği bir
uygunsuzluk sınıfı vardır, somut olarak sergilenmiştir, açığı 242 kenarın
2'sidir ve örtü dışı 11 düğümden tam biri onarmaktadır. Orada `unresolved`
diyen bir dağıtık algoritma, **sorabildiği soruya doğru cevabı vermektedir.**
Yamamak, bütün proje boyunca kullanmayı reddettiğimiz küresel bilgiyi
gerektirirdi.

### Yerel tanık taşıyıcısı bağlanmıyor

Kanca ve "alan belirirse ateşleyen" test kalıyor, hiçbir şey bağlanmıyor.
Gerekçe ölçülmüştür.

**Bedel:** tanık |E(N[v])| ister, o da komşu bitişikliği ister. Bunun maliyeti
ölçüldü: HELLO 13 bayttan `13 + 2(1+d)` bayta çıkar, yani derece 8'de 31,
derece 36'da 87. HELLO bütün iletimlerin yaklaşık yarısıdır. Yani baskın
çerçevede **kalıcı** bir yük artışı, yalnız uygunsuz örneklerde işe yarayacak
bir denetim için.

**Kazanç:** yerel tanık tek başına %88,6 tam. Küresel sayım tek başına yerel
tanığın yapısal olarak göremediği 25 vakayı kapsıyor. İkisi birlikte %98,4.
Küresel sayım ise **bedava**, harness'ta zaten duran üç tam sayı üzerinde
aritmetik. Yerel tanığı bağlamak yalnız-yerel 40 vakayı HELLO'yu ikiye
katlayarak satın alır. Bu takas kapanmıyor.

Biri ileride **başka bir sebeple** komşu bitişikliği alanı eklerse
(V5-BB-WuLi'nin zaten var), tanığı bağlamak neredeyse bedava olur ve bb-algo'nun
testi o kişiye söyler. Bırakılması gereken hal budur.

## 47. YÖNTEM: kırmızıyı yamama, aynı hastalığı dosyada tara

bb-validate'in fikstür düzeltmesi tek bir testi kurtarmakla kalmadı. Kendi
dosyasını aynı örüntü için **taradı** ve üç tane daha buldu, hepsi üretilmiş bir
örneğin rastlantısal bir özelliğine çivilenmişti:

* en yoğun ölçülen nokta testi `deg == 48` iddia ediyordu,
* tablo tavanı testi `deg == 66` iddia ediyordu,
* Bloom geçersizlik testinin tohumları 16 ve 17 diye sabitlenmişti.

Düzeltmeler iki ilkeyi uyguluyor.

**Önkoşulu yapı gereği doğru kıl.** Kırmızı olan test artık 40 yapraklı bir
yıldız kullanıyor: merkezin derecesi 40, çünkü 40 yapraklı yıldız budur.
Üretici yok, tohum yok, `assert deg > cap` bir umut değil bir olgu ifadesi.

**Dereceyi değil İDDİAYI çivile.** Öteki ikisi artık `instance_with_max_degree`
çağırıyor ve hiçbir derece sabitlemiyor; ölçülen `max_payload`ın çözümsel
eğriyle birebir eşleştiğini iddia ediyorlar, ki asıl sınanmak istenen buydu ve
bu üretici değişse de ayakta kalır. Aday bulunamazsa mesaj **"Bu bir ÖNCÜL
hatasıdır"** diyor, algoritmayı suçlamıyor.

### Testin yarısı boşmuş, kırmızı olduğu halde

En öğretici ayrıntı: kırmızı testin önkoşulu düzelse bile **yarısı boş
kalıyordu.** Test yalnız koşumun başarılı olduğunu gösteriyordu, oysa
"tavan yükseltildi" ile "tavana hiç yaklaşılmadı" arasında ayrım yapamıyordu.
Şimdi aynı çizgeyi tavan yükseltilmeden koşup üreticinin `ValueError`
kaldırdığını da iddia ediyor.

Yani bir testin geçmesi kadar, **düşmesi gereken yerde düştüğü** de gösterilmeli
(madde 15).

### Hata mesajı da bir denetimdir

`assert small >= 4, small` çıplak bir tam sayı basardı. Yeni mesaj, ölçütün
4 bayt ile 64 baytı ayırt etmeyi bıraktığını söylüyor, ki okuyucunun bilmesi
gereken şey bu: ayırt etmeyi bırakmışsa, yanındaki "64 baytta sapma yok"
iddiası hiçbir şey kanıtlamıyor demektir.

## 48. Dikiş sözleşmesinin V5'te tutmayan iki şartı

bb-validate, `_backbone_step` sözleşmesinin V5'te karşılanamayan iki şartını
bb-bootstrap'a doğrudan iletti, bir sonraki kol yeniden keşfetmesin diye.

**"B bağlı ve baskındır"** tam çizgede düşüyor, çünkü Wu-Li'nin işaretleme
kuralı ("iki komşusu bitişik değilse v'yi işaretle") her komşuluk klik olduğunda
kimseyi işaretlemiyor. Bu kolun kusuru değil, algoritmanın **belgelenmiş
önkoşulu**: CDS teoremi bağlı ve **tam olmayan** çizgeler için ifade edilmiştir.
Hat yine de Faz 2 üzerinden geçerli örtü döndürüyor. Kıyas verisinde tam çizge
olmadığı için gizli kalıyor, ama omurga temelli bir kapı buna takılırdı.

**"`mis_nbrs` MIS rollü komşuları taşır"** V5'te hiç tutamaz, çünkü Wu-Li iki
atlamalık bir kuraldır ve dondurulmuş telde komşu özeti için ikinci bir
değişken uzunluklu alan yoktur. Güvenli olmasının tek sebebi üç okuyucunun da
ezilmiş olması.

Ölçülmüş ayrıntı: geri getirilen 3 atlama boşluk kuralı o yeniden kullanılan
alanda **atıl** kalıyor, üç tohumda birebir aynı omurga veriyor, çünkü tam
komşu listesi kuralın kendi bastırma koşulunu sağlıyor ve kural kendini
kapatıyor. Bu verinin bir rastlantısı, dolayısıyla **alarm testi** olarak
duruyor, iddia edilen bir güvenlik özelliği olarak değil.

## 49. ENTEGRASYON KOŞUMU: hat çalışıyor, iki gerçek kusur çıktı

Her ajan kendi kolunu sınıyordu, bütünü sınayan yoktu. Süpürmeyi uçtan uca
koşturdum: küçük grup, k=6, 195 koşum, 52 sütun.

```
durum dağılımı : ok 160, infeasible 30, unresolved 3, contradiction 2
verdict_agrees : yes 190, no 5
trace_agrees   : yes 52, none 130, no 13
```

**Hat çalışıyor.** 195 koşumun tamamı bitti, üç çıktı dosyası üretildi, kollar
doğru eksenlerde eşleşti.

Ama tek koşumda **iki gerçek kusur** çıktı, ikisi de V6'da ve ikisi de yalnız
async'te.

### V6 KOPUK örtü döndürüp başarı bildiriyor

```
V6-ANNEAL/async ve V6-ANNEAL-tree/async, n25_m50_s1, k=6
cover_size=16, vertex_cover=True, capacity=True, connected=FALSE
kol hiçbir bayrak kaldırmadı -> satır contradiction
```

Örtü her kenarı örtüyor ve kapasiteyi sağlıyor ama **bağlı değil**, ve koşum
fark etmiyor. Bağlılık CCVC'nin C'sidir, dolayısıyla bu nitelik sorunu değildir.
Döngü C'nin köprü teşviki (`−λ_b`) bunu önlemeliydi. V6-ANNEAL-trickle aynı
örnekte takılmıyor, ki o da async, dolayısıyla ayırt edici bir ipucu.

### İz ile çözüm 13 koşumda çelişiyor

```
"iz hiç geçerli çözüm görmedi ama koşum |C|=20 döndü"   (10 koşum)
"iz |C|=8, koşum |C|=7"                                 (1)
"iz |C|=17, koşum |C|=16"                               (2)
```

İz hiç geçerli durum kaydetmezken koşum tam örtü döndürüyor, yani örnekleyici
koşumun yaptığını gözlemlemiyor. Bir-eksik çiftler (8/7, 17/16) "hiç görmedi"
vakalarından farklı görünüyor, iki ayrı sebep olabilir. Şekil 8 tam da bu alanı
çiziyor.

### Asıl gösterdiği şey

Bütün ajanların süitleri yeşildi, paket 1239 testle temizdi, ve **birleştirilmiş
hattı bir kez koşmak anında 2 çelişki ve 13 iz uyuşmazlığı üretti.**

Bunları yakalayan iki sütunun ikisi de bu sabah yoktu. `verdict_agrees` ve
`trace_agrees`, çapraz görünüm argümanının (madde 31, 36) doğrudan sonucu, ve
ikisi de **ilk gerçek çıkışlarında** karşılığını verdi.

Ters yön de üç kez ateşledi: "kol unresolved bildirdi, doğrulayıcı temiz".
Kendi başarısını tanıyamayan bir kol, bugün bir maliyeti olmasa da tespit
kusurudur.

**Ders:** bileşen testleri bütünü sınamaz. Her parçanın yeşil olması, parçaların
birlikte doğru çalıştığının kanıtı değildir, ve bunu ancak bütünü koşarak
öğrenirsin.

## 50. İLKE: karşılaştırma ölçek değişmezdir, EŞİK değildir

bb-core'un λ/T hatası (madde 42) bir sınıfa işaret ediyordu ve bb-algo o sınıfı
kendi koluna karşı sınayıp **yapısal sebebi** buldu. Tek cümle:

> **Her eşitlik bozumu iki anahtarı KARŞILAŞTIRARAK çözülür, bir anahtarı
> EŞİĞE vurarak değil. Karşılaştırma ölçek değişmezdir, eşik değildir.**

BB-CVC'nin dokuz parametresinin hiçbiri ağırlık boyutlu değildir; hepsi atlama,
adım ya da periyot sayısıdır. Ağırlık düğüm gövdesinde yalnız iki yerde geçer
(bir günlük alanı ve Faz 5b toplamı), ikisi de karar değildir.

V6 ise tam tersini yapıyordu: `λ` ve `T₀` ağırlık boyutlu **eşiklerdi** ve
işlenmiş örneğin w_max = 6 değerinden sabitlenmişlerdi. Kıyas verisinde
ağırlıklar 26-115'e çıkınca eşikler anlamını yitirdi.

### Bağımsız doğrulama (ve boş olmayan kontrol)

```
n=40, k=6           |C|    ağırlık      tx   slot   sonuç
ağırlıklar ×1        33        123    1150     23   taban
ağırlıklar ×1000     33     123000    1150     23   ÖRTÜ/TX/SLOT BİREBİR AYNI
ağırlıklar +1000     30      30120    1158     22   FARKLI, ama geçerli
```

`+1000` vakası kontrol grubudur ve **testin boş olmamasını sağlar**: sabit
eklemek anahtar sıralamasını gerçekten değiştirir, dolayısıyla davranış
değişmelidir, ve orada istenen tek şey örtünün boş olmaması ve geçerli
kalmasıdır. Yalnız `×1000` sınansaydı, hiçbir şey yapmayan bir kod da geçerdi.

### Pratik kural

Bir koldaki her sabit için sorulacak soru: **bu sabit gerçekten bir sabit mi,
yoksa örneğe bağlı bir şeye ORAN mı?** bb-core'un üçü de orandı, ve oran olarak
yazıldıklarında `.tex` örneğinde belgelenen sayıları birebir veriyorlar.

## 51. DÜZELTME: `verdict == "solved"` tek başına YETMİYOR

bb-algo kendi önerisini düzeltti ve ortaya tamamlayıcı bir çift çıktı. Süpürme
satırının kol sonucu sayılması için **iki koşul da** gerekiyor.

```
verdict "solved"    + doğrulayıcı KİRLİ  -> bb-core'un boş örtüsü
                                            (verdict bunu göremez: yakınsadı,
                                             kimse pes etmedi, örtü boş)
verdict "truncated" + doğrulayıcı TEMİZ  -> n=50/m=144/k=6, 5 saniye
                                            (geçerlilik bunu göremez: örtü o an
                                             tutarlı ama koşum bitmemiş)
```

Her iki yönde birer karşı örnek var ve **her koşul ötekinin göremediğini
yakalıyor**. İkisi de zorunlu.

`verdict`in geçerlilikten TÜRETİLMEDİĞİNİ iddia eden bir test de kondu, ki
ileride sessizce birleştirilmesinler.

Not: ikinci satırdaki karşı örnek benim n=50 örneğimden, birincisi ise bb-core'un
boş örtü hatasından geldi. Yani çift, iki ayrı ajanın iki ayrı hatasından
kuruldu ve hiçbiri tek başına yeterli olmadığını gösteremezdi.

## 52. YÖNTEMİN SINIRI: gözlenebilir hiçbir şeyin yanlış olmadığı hata

Bugün işe yarayan bütün yöntemler tek bir varsayıma dayanıyor ve bb-core bunu
kendi bulgusu üzerinden açıkça söyledi. Kayda en çok değer cümle bu.

> Çalışan her yöntem — iki görünümün çelişmesi, tuzağın mutasyonla sınanması,
> taklidin gerçeğiyle değiştirilmesi — **gözlenebilir bir şeyin yanlış olmasını
> gerektirir.** Sessiz sıcaklık hatasında hiçbiri yanlış değildi.

Sabitlenmiş `T₀` geçerli çıktı üretiyordu: örtü geçerli, kapasite tamam,
bağlılık tamam, sayaçlar temiz, doğrulayıcı memnun, iz ile çözüm uyumlu. Yanlış
olan tek şey **tavlamanın tavlama olmaktan çıkmasıydı**, ve bunun hiçbir
gözlenebilir izdüşümü yoktu.

Dolayısıyla bu hatanın **bağımsız keşif yolu yoktu**. Gürültülü λ hatası
düzeltilirken aynı beş satırın içinde bulunuldu ve zihinde "burada başka hangi
sabit aslında bir oran olmalı" sorusu vardı. bb-core'un kendi ifadesiyle: bu bir
yöntem değil, **hazırlıklı zihinle rastlantı**.

### Neden bunu böyle kaydediyoruz

Çünkü aksi, sürecin yakaladığını ima etmek olurdu. Yakalamadı. Bugün kataloğa
giren beş suç ortağı örneği, çapraz görünüm mekanizması, mutasyon disiplini ve
entegrasyon koşumu, hepsi **bir yerde bir sayının yanlış olmasına** dayanıyor.

Bu sınıfa karşı elimizde kalan tek şey, madde 50'nin sorusudur ve o da bir
denetim değil bir okuma alışkanlığıdır:

> **Bu sabit gerçekten sabit mi, yoksa örneğe bağlı bir şeye oran mı?**

Sorunun kendisi otomatikleştirilemez. Ama ağırlık boyutlu her sabit için
sorulabilir, ve bb-algo'nun BB-CVC'de yaptığı gibi **hiç ağırlık boyutlu sabit
bulunmadığını** göstermek, sorunun cevabını yapısal olarak kapatmaktır.

### Sınır dürüstçe yazılmalı

Raporda "yöntemimiz şu hataları yakaladı" denecekse, yanına "ve şu sınıfı
yakalayamaz" da yazılmalıdır. Sessiz ölçek hatası bu projede bir kez oldu ve
bir kez de yalnız şansla bulundu.

## 53. V6 zarf denetimi: ölçülmüş değil KANITLANMIŞ

bb-figures, zarfın son durumdan daha KÖTÜ olup olamayacağını sordu. bb-core
ölçmekle yetinmeyip kanıtladı, ve kanıt denetimin neden tutulması gerektiğini
de söylüyor:

1. Son durum her zaman örneklenir (`run_anneal` duvarda bir örnek daha alır).
2. Örnekleyicinin geçerlilik testi süpürmeninkinden **daha zayıftır**: sahiplik
   olmadan akışla kapasiteye bakar, çünkü tavlama sırasında sahiplik yoktur.
   Akış uygunluğu, sahiplik uygunluğunun **gerekli** koşuludur.
3. Dolayısıyla süpürme-geçerli ⇒ örnekleyici-geçerli, yani geçerli bir son durum
   koşan asgarinin içindeydi, yani **zarf ≤ son durum**.

60 tohum, 60 geçerli, sıfır karşı örnek.

**Sonuç:** denetim tam olarak son durum GEÇERSİZ olduğunda ateşler. Boş örtü
hatası kendini böyle duyurmuştu, ve bunu doğrulayıcıdan **farklı bir eksende**
yakalar: iz ile çözümün karşılaştırılması. Tutulmalı.

## 54. Aynı eksende olmayan iki eğri: biçimle değil PANELLE ayrılır

bb-validate, şekil 6'da çözümsel eğrinin ölçülen noktalardan **görsel olarak**
ayrılmasını önerdi. bb-figures daha derin bir sorun buldu: ikisi **aynı
değişkenin fonksiyonu değil.** Çerçeve boyu düğümün KENDİ derecesine bağlı,
ölçülen x ekseni ise çizgenin ORTALAMA derecesi.

Dolayısıyla hiçbir stil seçimi bunu düzeltmezdi; farklı renk ya da kesik çizgi,
iki eğriyi aynı eksende karşılaştırılabilirmiş gibi göstermeye devam ederdi.
Çözüm ayrı panel, ve çözümsel panelin derece aralığının ölçülen aralıktan kat
kat geniş olduğunu iddia eden bir test.

**Ders:** iki eğriyi aynı eksene koymadan önce ikisinin de aynı değişkenin
fonksiyonu olduğu doğrulanmalı. Görsel ayrım, kategori hatasını gizler.

### İki öz-düzeltme daha (bb-validate)

`mis_nbrs_max` sütununun V5 satırlarında anlamsız olacağını **kontrol etmeden**
iddia etmişler; sütun istenen değeri değil koşumun gerçekten kullandığı değeri
okuyor, dolayısıyla V5'in 4096'sı V2'nin 32'sine karşı görünür oluyor.

Şekil 8'in sıra bağımlılığı teşhisi de yanlışmış: sızan durum değil, bir yeniden
adlandırmadan kalan bayat `info["best_weight"]` anahtarıymış. **Bildirmek yine
de doğruydu** — gerçek bir başarısızlıktı, kararsızlık değil — ama önerilen
mekanizma doğru değildi. Madde 45 ile aynı kalıp: doğru kusur, yanlış mekanizma.

## 55. BİRLEŞTİRİCİ ÖRÜNTÜ: çelişmesi gereken denetim çelişemiyordu

bb-algo dokuz kusurunu kapatırken aralarındaki ortak yapıyı tek cümleye
indirdi ve bu, bütün günün özeti:

> **Her vakada, çelişmesi gereken denetim ÇELİŞEMİYORDU.**

Dokuz kusur, dokuz farklı biçim, tek yapı:

| Kusur | Çelişemeyen taraf |
|---|---|
| Sıra numarası akranı olmadan anahtarlanmış | eşleştirme yapacak ikinci uç yok |
| Dönüş değeri yok sayılmış | çağıran hata olduğunu öğrenemiyor |
| İki doğru aktarım birleşince kenar kayboluyor | her aktarım tek tek doğru |
| Sağlam olmayan tanık dörtte üç doğru çıkmış | doğru cevap argümanı doğrulamıyor |
| Saat tabanı yan etkiyle tutuluyor | satır taşınınca hiçbir şey şikâyet etmiyor |
| Her test yakınsamaya yeten bütçe veriyor | kesinti yolunun gözlemi yok |
| λ kendi fikstürüne karşı sınanıyor | fikstürde değişmez zaten tutuyor |
| T₀ geçerli çıktı üretiyor | yanlış olan hiçbir gözlenebilir yok |
| Kaynak metne bakan tuzak | kod taşınınca iddia hâlâ doğru |

Hepsi yakınsadı, hepsi temiz sayaç raporladı, hepsi yanlıştı. Ve hepsi
**dışarıdan** bir şeyle yakalandı: doğrulayıcı, kayıplı koşum, başka bir ajanın
ilgisiz hata raporu, ya da entegrasyon koşumu.

### İki usul kuralının sırası

bb-algo sıralamayı şöyle koydu ve doğru koydu:

1. **"Atfetmeden önce yeniden koş"** — bu, başkalarına borcun olan kural.
2. **"Rapor yeniden üretilemiyorsa ne olabilirdi diye sor"** — bu, rapora
   borcun olan kural, ve ancak birincisi çiğnendikten sonra işe yarıyor.

### Tek bulgu kalacaksa

bb-algo'nun önerisi, katılıyorum: **kesinti körlüğü.** Yüz elli dokuz yeşil
test, hiçbiri bağlayan bir bütçe koşmuyor. Süit algoritmanın **yeterli süre
verilince** çalıştığını kanıtladı ve yetmediğinde ne olduğu hakkında hiçbir şey
söylemedi. Bu eksik bir test vakası değil, **eksik bir eksen**: süitin kaynak
sınırı diye bir değişkeni yoktu.

## 56. Kıyas verisini ilk kez koşmak iki kapıyı birden açtı

bb-bootstrap gerçek veri kümesini koşturan ilk kişi oldu ve iki şey bütün
kıyas verisini tıkıyormuş.

### 0-indeksleme ve `hash16`'nın ayırdığı 0

310 örneğin hepsinde 0 numaralı düğüm var, `mac_for_id(0)` için ön-görüntü yok,
dolayısıyla **hiçbir kıyas örneği koşamıyordu.**

Bariz düzeltme `hash16`'da 0'ı serbest bırakmaktır ve bb-bootstrap bunu
**yapmadı**, çünkü ayrım başka bir dosyada yük taşıyor: `bbcvc.py:1341` TREE
kökünü `self.tree_root or 0` diye kodluyor, yani 0 "henüz kök yok" demek. 0
serbest bırakılsa gerçek bir 0 kökü ile kök yokluğu **sessizce** ayırt
edilemez hale gelirdi.

Kendi harness'inde yeniden etiketleyerek çözdüler ve ters haritayı sakladılar,
böylece örtüler kıyas etiketleriyle raporlanıyor.

**Kayda değer olan:** bir dosyanın doğruluğu, kendisinin ifade etmediği ve
başka bir modülün docstring'inde duran bir değişmeze bağlı. Bugün bir şey
bozulmuyor, ama o değişmezi gevşetme baskısı gerçek, çünkü az önce bütün kıyas
verisini tıkadı.

### Kesirli ağırlıklar ve fazla sıkı kendi kapısı

310 örneğin hepsinde `26.20965451126096` gibi ağırlıklar var ve
bb-bootstrap'ın **kendi kapısı** bunları reddediyordu: "ağırlık tamsayı
olmalıdır".

Kapı yanlıştı. Brief §3.6 sabit noktalı **ARİTMETİK** istiyor (ESP32-C3'te FPU
yok), tamsayı **GİRDİ** değil. 26,2096 cihazda 16.16 olarak saklanır, ki
`to_fp` tam olarak bunu yapar. Kesirli ağırlıkta `key_of`un tamsayı döndürdüğü
ve tamsayı-referansla ULP'ye kadar eşleştiği doğrulandı.

Kapı yalnız gerçekten temsil edilemeyeni (NaN, sonsuz, 16.16 aralığı dışı)
reddedecek şekilde gevşetildi. "Ağırlık tamsayıdır" diyen test, asıl önemli
değişmezi iddia edecek şekilde değiştirildi: ağırlık sabit noktaya tam
dönüşüyor ve anahtar tamsayı çıkıyor.

### Ve bu G8'in bir alt katmanıdır

bb-bootstrap'ın kendi sözleri: gereksinimden **daha sıkı** bir koşul dayatan bir
kapı yazdılar, kapıyı çivileyen bir test yazdılar, ve ikisi bütün oturum boyunca
doğru göründü, çünkü sınadıkları her çizgenin ağırlıkları kazara tamsayıydı.
Ancak gerçek veri gelince ortaya çıktı.

**Sınadığın rejimde tutan bir kısıtı, problemin özelliği sanmak.** Brief G8'de
bunu yaptı, biz burada yaptık. Aynı hata, bir katman aşağıda.

## 57. YENİ SINIF: uydurulmuş kısıt — hiç sınanmayan tek kısıt türü

Bugün kataloğa giren bütün hatalar "çelişmesi gereken denetim çelişemiyordu"
biçimindeydi (madde 55). bb-validate'inki farklı ve sınıf olarak yeni:
**hiç denetim yoktu, çünkü kısıt kendi koydukları bir kısıttı.**

V5'in komşu özetini HELLO'nun mevcut `mis_nbrs` dizisine sıkıştırma kararının
tamamı "api.py ve wire.py dondurulmuş" gerekçesine dayanıyordu. **Bu hiç doğru
değildi.** bb-core saatler önce iki yeni MsgType eklemiş ve ihtiyacı olan her
kola kodek ekleme teklifini açık bırakmıştı. Kanıt, V5 başlamadan önce
depodaydı.

bb-validate'in kendi ifadesi: "düzenlemek bana düşmez" ile "değişemez"i
karıştırdım ve hiç sormadım.

> **Kendi koyduğun kısıt, asla yanlışlayamayacağın tek kısıttır**, çünkü
> sistemde onu iddia eden hiçbir şey yoktur. Mutasyon sınaması yoktur, çapraz
> görünüm yoktur, doğrulayıcı yoktur. Yalnız soru vardır ve o da sorulmaz.

Pratik alışkanlık, bugün benimsediğimiz her denetimden ucuz: **kısıt gerçek mi
diye sor.**

## 58. KARAR: V5'in tel yapısı değiştirilmiyor, tuzak yeri değiştiriliyor

bb-validate haklı olarak bir tasarım kararının çürük öncüle dayandığını bildirdi
ve düzeltmeyi teklif etti. Karar: **yapma.**

**Gerekçe kendi maliyet çözümlemesidir.** `hello_size = 13 + 2n` sayısı madde
16'nın aritmetiğinde, işlenmiş örnek kalibrasyonunda, şekil 6'nın ölçülen
noktalarında ve bir bb-figures testinde yük taşıyor. (O test bir bayt sabitini
DEĞİL, derece 64'ün 65 kelimeye eşlendiğini çiviliyor: `curves["full"][64] ==
wire.hello_size(65)`. Doğrulandı: `hello_size(64)=141`, `hello_size(65)=143`.
Maliyet savını ilk yazarken 141 demiştim, yanlıştı; yapısal nokta değişmiyor
ama **ölçüm disiplini üzerine bir savın içine ezberden sayı koymak** tam da gün
boyu katalogladığımız sınıf.)
Gövdeyi değiştirmek yayımlanmış birkaç bulguyu yeniden ölçmek demek. Karşılığı
ise **gizli** bir tehlikeyi kapatmak: birinin temel sınıfa dördüncü bir okuyucu
eklemesi gerekiyor, ki bugün kimse yapmıyor.

Teklif ettikleri çözüm doğruydu ve reddedilse de kayda geçer: yeni bir MsgType
değil, Hello gövdesine adanmış isteğe bağlı bir alan. Çünkü V5'in yaydığı şey
gerçekten bir HELLO'dur ve ona ayrı tip vermek `by_type_tx`'te HELLO maliyetini
**eksik** gösterirdi, yani bb-core'un uyardığı kirlenmenin ters yönü. Brief de
biçim olarak katılıyor: §6.5 ANNEAL için HELLO'ya alan ekliyor, çerçeve
tanımlamıyor.

### Yerine yapılan: tuzağı TEHLİKENİN olduğu yere taşımak

bb-validate'in kendi teşhisi: alarm testi, kazanın olmak üzere olduğunu değil
**çoktan bittiğini** raporluyor, ve yalnız birisi koşarsa ateşliyor.

Tehlike "temel sınıfta `mis_nbrs`'in dördüncü bir okuyucusu belirir" olduğuna
göre, tuzak da temel sınıfın yanında durmalıdır, V5'in dosyasında değil. O alanın
okuyucularını sayan ve sayı değiştiğinde düşen bir test, dördüncü okuyucuyu
ekleyen kişiye **kendi düzenlediği dosyada, düzenlediği anda** söyler.

Böylece tehlike "V5 sessizce kırılır, başka yerdeki bir alarm sonradan fark
eder"den "V5'i kıracak değişiklik sessizce inemez"e dönüşür. Birkaç satır, ve
hiçbir yeniden ölçüm gerektirmez.

**Genel kural:** tuzak, belirtinin göründüğü yere değil, **değişikliğin
yapılacağı yere** konur.

## 59. V6'nın kopuk örtüsü: sebep bulundu, kalıntı ÖLÇÜLDÜ, kapatıldı

Entegrasyon koşumunun bulduğu (madde 49) kopuk örtü hatasının kökü bulundu ve
**λ_b ölçeklemesi değildi.**

**Mekanizma:** düğüm dondurduktan sonra `_anneal_period` durur, dolayısıyla
Döngü C (etiket dedikodusu) de durur. Ama `on_frame` komşu tablosunu
güncellemeye devam eder. Yani **etiket katmanı donarken komşu görüşü hareket
etmeye devam ediyor.** Ölçülen örnekte 13 numaralı düğüm örtüde yalnız kalmış,
iki komşusunun da ayrıldığını **doğru biçimde görmüş**, ama büyük bileşenin
etiketini taşımaya devam etmiş, çünkü Döngü C bir daha hiç koşmamış. Örtü
dışında hiçbir düğüm iki etiket göremediği için köprü teşviki hiç ateşlemedi.

Bu ayrıca trickle'ın neden takılmadığını da açıklıyor: trickle `_t_hello_cur`i
uzatıyor, bayatlık penceresi genişliyor ve etiketler dondurma inmeden önce daha
çok duvar saati kazanıyor.

**Dar düzeltme uygulandı:** Döngü C dondurmadan sonra da koşuyor. Hiçbir kararı
değiştirmiyor (donmuş düğümün `x`i sabit), yalnız etiketleri dürüst tutuyor, ki
herhangi bir köprünün ayrılmayı görebilmesinin önkoşulu bu.

**Tam düzeltme denendi ve GERİ ALINDI.** Donmuş düğümleri uyandırmak etiketleri
düzeltti ama kusuru daha kötüsüyle takas etti: uyanan düğümler sıfır sıcaklıkta
inmeye devam edip bazı örtüleri |C|=2'ye indirdi, üstelik açıkta kenar
bırakarak. **Bir kusuru daha büyüğüyle değiştirmek onarım değildir.** Deneme ve
ölçülen başarısızlığı sessizce atılmayıp dosyaya yazıldı.

### Karar: burada durulur, kalıntı sonuç olarak raporlanır

Gevşek kapasiteli hücrelerde oran **80 koşumda 3**. Bu bir açık uç değil,
mekanizması adlandırılmış ölçülü bir sayıdır.

Ve kusur **görünür**: süpürme bunları `verdict_agrees` üzerinden
`contradiction` olarak yakalıyor, dolayısıyla karşılaştırmaya geçerli kol
sonucu olarak giremiyor. Harness'ın tespit edip etiketlediği bilinen bir arıza
kipi, tabloları kirleten bir kipten bambaşka şeydir.

### Defect 2'nin iki yarısı da RAPORLAMA tarafındaydı

"İz hiç geçerli çözüm görmedi" diyen on satır: n20_m160, k=6'da m=160 > n·k=120,
yani örnek sayma sınırıyla uygunsuz. **İz doğru.** Bayrağın, satır zaten
uygunsuzken bastırılması gerekiyor, yoksa kol çözümü olmayan bir problemi doğru
raporladığı için bozuk görünüyor.

Bir-eksik çiftler: yanlış büyüklük karşılaştırılıyormuş. Zarf **ağırlığı**
küçültüyor, ağırlık ile örtü boyu eş-monoton değil. Ölçülen: zarf |C|=6,
ağırlık 2821; son durum |C|=7, ağırlık 4045. Hem daha az düğüm hem daha düşük
ağırlık. Karşılaştırma `observer_best_weight` ile `total_weight` arasında
yapılmalı.

## 60. SINIF: bir yapılandırmada etkisizlik ölçmek, etkisizlik ölçmek değildir

bb-core'un kendi hatası, suç ortağı fikstürün tam tamamlayıcısı.

Etiket-hareketi sükûnet kapısını, "yük taşımıyor" diye ölçtükten sonra
kaldırmışlar.

**İlk yazdığım hali fazla kolaycıydı ve bb-core düzeltti.** Ölçümü atlamadılar:
60 tohum ve 30 düğümlük bir çizge üzerinde ölçtüler, ikisinde de sıfır etki
gördüler, ve ölü karmaşıklık diye kaldırdılar, ki bu normalde doğru içgüdüdür.
Hata ölçmemek değildi. Hata, **iki ölçümün de sync olmasıydı**, oysa mekanizma
yalnız periyotlar hizasızken önemli.

Dolayısıyla kuralın işler hali "daha çok test et" değil, daha dar:

> **Üzerinde ölçüm yaptığın yapılandırmalar, mekanizmanın bağlı olduğu EKSENİ
> kapsamak zorundadır.**

Altmış tohum, **yanlış eksende** büyük bir örneklemdir. Örneklem büyüklüğü
titizlik gibi okunur ama sabit tuttuğun boyut hakkında hiçbir şey söylemez.
Kendinden emin yanlışı, arkasında gerçek kanıt olan bir yanlış yapan şey budur.

Suç ortağı fikstürde bir değişmez **tuttuğu yerde** denetleniyordu (madde 42).
Burada bir mekanizma **önemsiz olduğu yerde** ölçülüyor. İkisi de temsil
etmeyen bir örneklemden sonuca varıyor, ve ikisi de arkasında bir ölçüm olan
kendinden emin bir yanlış üretiyor.

Bu ayrıca entegrasyon koşumunun (madde 49) neden bütün yeşil süitlerin
kaçırdığını bulduğunu açıklıyor: **her süit kendi tek yapılandırmasını iyi
sınıyordu.**

### Küçük ama gerçek: örnek hattı örneğin parçasıdır

bb-core'un ilk yeniden üretme denemesi başarısız olmuş, çünkü ağırlıkları
süpürmenin nicelemesinden geçirmek yerine kendileri yuvarlamışlar. Aynı çizge,
farklı örnek.

## 61. KENDİ KURALIMI ÇİĞNEDİM: kaynak metne bakan bir tuzak ısmarladım

bb-validate'e, V5'in gizli tehlikesi için temel sınıftaki `mis_nbrs`
okuyucularını **sayan** ve sayı değişince düşen bir test yazmalarını söyledim.

Reddettiler ve haklıydılar. Bu bir **kaynak metin iddiasıdır**, yani madde 28'de
kendi yazdığım kuralın ("etkiyi çivile, yazımı değil") tam ihlali. Üstelik o
kuralı `_t0_ms` tuzağının sessizce bayatlaması üzerine yazmıştım.

Önerdiğim testin somut kusurları: `getattr(n, "mis_nbrs")` çağrısını göremez,
yerel takma adı göremez, ve `bbcvc.py`'de birkaç tane bulunan docstring
geçişlerine ateşler.

**Yerine gönderdikleri:** temel sınıfta tek bir okuma yolu (`_nbr_mis`), mevcut
üç okuma oradan geçirilir, V5 o tek erişimciyi ezip kaldırır. Aynı koruma, ama
**çalışma zamanı değişmezi** olarak.

### Ve önermeden önce iki yarısını da ölçtüler

Tehlike gerçek ve çirkin: temel sınıfın erişilebilir bir metoduna eklenen
dördüncü bir okuyucu, V5'in cevabını örtü 12 / Σw 957'den örtü 20 / Σw 1180'e
taşıyor, yani **%23 ağırlık artışı**, ve koşum yine `converged` diyor,
doğrulayıcı yine GEÇERLİ diyor. Hiçbir şey düşmüyor. Erişimci konunca aynı
dördüncü okuyucu anında kalkıyor.

**Yani değişiklik, yanlış bir sayıyı bir yığın izine dönüştürüyor.**

Sınırını da söylediler: erişimciden geçen okuyucuları korur, doğrudan
`n.mis_nbrs` yazanı korumaz. Tehlikeyi ortadan kaldırmıyor, tek dosyadaki tek
satırlık bir disipline indiriyor.

### Kendi hafifletmelerini de düzelttiler

"V5 üç okuyucunun üçünü de eziyor" demişlerdi. Etmiyormuş: Faz 1'i dikişe
taşıdıklarından beri `_rule_connector` ezilmiyor, yalnız **erişilemez**.
Erişilemezlik bugünkü çağrı çizgesinin özelliğidir, değişmez değildir.

## 62. bb-algo'nun üç kör noktası: hepsi eksik VAKA değil eksik EKSEN

bb-algo, bb-bootstrap'ın tamsayı-ağırlık hatasını kendi koluna karşı sınadı ve
üçüncü kör noktasını buldu. Üçü birlikte örüntüyü tamamlıyor:

```
hiçbir test bağlayan bir bütçe koşmuyordu      -> kesinti yolu kapsamsız
hiçbir test kesirli ağırlık kullanmıyordu      -> kıyas verisinin REJİMİ kapsamsız
hiçbir test relay yolunda kayıplı kanal kurmuyordu -> epoch sıfırlaması kapsamsız
```

Üçü de 162 yeşil teste **görünmezdi**, ve üçü de eksik bir test vakası değil
**eksik bir eksen**. Her seferinde süit, algoritmanın *seçilen rejimde*
çalıştığını kanıtladı.

Kesirli ağırlık düzeltilirken çıkan ayrım kayda değer: brief §3.6 kayan noktalı
**ARİTMETİĞİ** yasaklıyor, kesirli **GİRDİYİ** değil. BB-CVC ağırlığı yalnız
anahtar kurmak için kullanıyor ve `api.key_of` o sınırda dönüştürüyor, dolayısıyla
kesirli girdi hiçbir karara ulaşmıyor. Test anahtarların hâlâ tamsayı olduğunu
iddia ediyor, böylece float sızdıran bir değişiklik sessizce bozulmak yerine
düşüyor.

## 63. Çapraz dosya değişmezi: BAĞIMLI dosya düşmeli

bb-algo TREE sentinel bağımlılığını yorumla belgelemekle yetinmedi, **çalışma
zamanında zorladı.** `_TREE_NO_NODE = 0` tam gerekçesiyle adlandırıldı ve
`_tree_send` artık denetliyor: kodlayıcıya 0 düğüm kimliği ulaşırsa kalkıyor,
değişmezi adlandırıyor ve harness'ın 0-indeksli girdiyi yeniden etiketlemesi
gerektiğini söylüyor.

Gerekçesi doğru: **yorum yalnız okunursa uyarır**, oysa baskı `hash16`'yı
düzenleme yönünde ve orası başka bir dosya, üstelik oradan buraya işaret eden
hiçbir şey yok.

> **Değişmeze BAĞIMLI olan dosya düşmelidir, çünkü neden önemli olduğunu bilen
> tek dosya odur.**

Test iki yarıyı da çiviliyor: `hash16` 4000 MAC'te hiç 0 döndürmüyor, ve
döndürüyormuş gibi yapılınca koruma ateşliyor.

## 64. İLKE: rutin olarak beklenen uyuşmazlık bildiren denetim, okunmaz olur

bb-core kendi önerisini geri çekti ve yerine daha iyisini koydu. Konu,
entegrasyon koşumundaki (madde 49) 10 "iz hiç geçerli çözüm görmedi" satırı.

O satırlarda **iz ile koşum tamamen uyuşuyor**: örnek sayma sınırıyla uygunsuz,
dolayısıyla görülecek geçerli bir şey yok. İz doğru, koşum doğru.

bb-core önce satırların gizlenmesini önerdi. bb-figures itiraz etti: "iz
geçerli bir şey görmedi" ifadesi orada doğru ve yararlı. bb-core itirazı kabul
edip asıl sorunun **görünürlük değil ETİKET** olduğunu gördü.

> Otuz doğru satır, sıfır-dışı her girdisi "bir şeyler yanlış" demek olan bir
> sütunu şişiriyor. **Rutin olarak beklenen uyuşmazlık bildiren bir çapraz
> denetim göz gezdirilir hale gelir, ve gerçek olan onun içinde saklanır.**

Çözüm üçüncü bir değer: `n/a: infeasible`. Gözlem korunur, sütunun anlamı
korunur.

Bu, madde 15'teki boş test sorununun aynası. Orada denetim hiç ateşlemiyordu;
burada **çok ateşliyor**, ve ikisi de denetimi işe yaramaz hale getiriyor.

### Oran iki bağımsız örneklemde tutuyor

V6'nın kopuk örtü kalıntısı (madde 59): bb-core gevşek kapasiteli hücrelerde
80 koşumda 3 ölçmüştü, bb-figures'ın tam süpürmesi 195 koşumda 3 verdi. İki
ayrı örneklem, tutarlı oran. Tek ölçümden gelen bir kalıntı sayısına göre daha
güvenilir.

### Ters yön bb-algo'yu işaret ediyor

Süpürmedeki 2 ters yönlü satır (`unresolved` ama doğrulayıcı temiz) muhtemelen
V6'ya değil **paylaşılan Faz 4'e** ait, çünkü V5-BB-WuLi-bloom/sync aynı
örnekte yeniden üretiyor. Kol farkı değil, ortak kod.

## 65. Düzeltmelerden sonra süpürme: V6 195/195 boştan 155 geçerliye

bb-figures'ın tam süpürmesi, λ ve sıcaklık düzeltmesini (madde 42) **bb-core'un
kendi örneğinde değil ölçekte** doğruladı.

```
V6-ANNEAL, küçük grup, 195 koşum
önce:  195/195 boş örtü
sonra: 155/195 ok
```

Ve **altı kanıtlanabilir uygunsuz hücrenin altısı da** artık her kolda doğru
biçimde `infeasible` ilan ediliyor, oysa önce `unresolved` diyorlardı. Zayıf
yargı bulgusu (madde 32) gerçek veride kapandı.

### Kalıntı iki bağımsız örneklemde doğrulandı

V6'nın kopuk örtüsü (madde 59): bb-core gevşek kapasiteli hücrelerde 80 koşumda
3, bb-figures tam süpürmede 195 koşumda 3. Üstelik bir örnek **iki kolda birden**
yapıyor, üçüncüsü temiz, yani rastgele değil **örnek ve zamanlayıcı biçimli**,
ki bb-core'un adlandırdığı mekanizmayla birebir uyuşuyor.

Kapattığım kalıntıyı raporlanabilir kılan şey bu: tek ölçüm değil, iki bağımsız
örneklemde tutarlı oran.

### Test yazarken iki çapraz görünüm boşluğu daha çıktı

**Kesilmiş ama geçerli koşum, ters yön uyarısını ateşliyordu.** Yanlış: kesinti
bir tespit kusuru değildir. Madde 64'ün (rutin beklenen uyuşmazlık) aynı
oturumda ikinci örneği.

**`verdict` kendi bayraklarıyla çelişebiliyor.** `verdict="solved"` ile
`unresolved=True` `bbcvc` içinde oluşamaz, ama koşucu her varyanta açık.
Üreticiye güvenmek yerine **tüketicide** korumak doğrusu.

### Şekil 6: destekleyemediği bir iddiada bulunuyordu

"Tavana 118 girişte varılır" notu ölçülen noktaların yanında duruyor ve
yaklaşılan bir sınır gibi okunuyordu. Oysa tavan erişilemez (madde 40): tablo
64 girişte doluyor ve taşma koşumu geçersiz kılıyor, dolayısıyla raporlanabilir
en yoğun çerçeve 143 bayt.

Düzeltirken bb-figures kendi eksen hatasını da buldu (madde 54) ve şekil dört
panele çıktı. Çözümsel panelin derece aralığının ölçülen aralıktan kat kat
geniş olduğunu iddia eden test, eksenlerin farklı olduğunun **gözlenebilir**
kanıtı.

### Hayatta kalma makinesi gerçek veride ateşledi

Altı kol, kendi altkümesi ile ortak altküme arasında sapma uyarısı taşıyor.
Eşiğin üstünde bir sapma, o kolun kendi oranının **başarısızlıkları düştüğü
için** güzelleştiği anlamına gelir. İlk kez gerçek veride çalışıyor.

## 66. Okuyucu sayısı üç değil DÖRTMÜŞ: saymanın neden yanlış yöntem olduğu

Erişimci kurulurken (madde 61) `mis_nbrs`in temel sınıftaki okuyucu sayısı
**dört** çıktı, üç değil. 641. satırda tek ifade içinde iki okuma varmış.

Bu, ısmarladığım saymalı testin yalnız biçim olarak değil **taban değeri olarak
da** yanlış olacağını gösteriyor. Test "sayı 3'ten farklıysa düş" diye
yazılsaydı ilk koşumda düşerdi; "4'ten farklıysa" diye yazılsaydı doğru sayıyı
elle bulmuş olmak gerekirdi, ki asıl mesele elle sayılamaz olması.

Ayrıca bb-validate'in hafifletmesi, düzelttikleri hâlinden de zayıfmış: üç
okuyucudan ikisi eziliyor, biri erişilemez, ve dördüncüsü hiç bilinmiyordu.

## 67. Kaynak metin iddiaları İKİ YÖNDE birden bozuluyor

bb-algo, bugün ikisini de yaşadığımızı belirtti ve tablo böylece tamamlandı.

**Yanlış negatif:** saat tabanı tuzağı, sabitlediği şey düzeltildikten sonra
**yeşil kaldı**, çünkü eşleştirdiği dizi bir yardımcı metoda taşındı
(madde 28).

**Yanlış pozitif:** bb-algo'nun kendi yerellik testi, içinde "slot" kelimesi
geçen bir **yorum** yüzünden tetikleniyordu ve AST ayrıştırması gerektirdi.

bb-validate'in önceden saydığı körlükler (`getattr`, yerel takma ad, docstring
geçişi) tam olarak bu arıza kipinin önceden sayılmış hali.

> **Çalışma zamanı değişmezi yeniden ifade edilerek atlatılamaz. Kaynak metin
> iddiası hem taşınarak hem de yanlışlıkla eşleşerek bozulur.**

### İstisna, kulübü kirletmeden kapsamlandı

bb-algo istenmeyen ama doğru bir şey ekledi: tam çizge istisnasının **V2'ye
uzanmadığını** gösteren bir test. K5'te MIS omurgası tek düğüm, bağlı ve
baskın. Gerekçesi önemli: aksi hâlde sonraki okuyucu, maddenin tamamının
güvenilmez olduğu sonucuna varabilirdi, oysa istisna tek bir kolun işaretleme
kuralına özgü.

**Bir istisna, kapsamı gösterilmezse onu içeren kuralı da şüpheli kılar.**

### Sözleşme gevşetilmedi

Clause 3, "alanı yeniden kullanan kol erişimciyi ezmek ZORUNDADIR" diye
sıkılaştırıldı, gevşetilmedi. Gevşetmek, bb-validate'in kendi işaretlediği
rastlantıyı (3 atlama kuralının V5'te atıl kalması) **sözleşmeye bağlamak**
olurdu, yani veriye ait bir kazayı yük taşıyıcı hale getirmek.

## 68. KARAR: V1-DFS kurulmuyor, eksik olduğu yazılıyor

bb-bootstrap V1'in durumunu dürüstçe raporladı: **bağlı değil, koşmuyor.**
Var olan şey durum, karar mantığı ve referans DFS ağacıyla 310 örneğin
tamamında eşleşen bir protokol simülasyonu. `dfs_preempted` gerçek bir koşumda
hiç artmadı, dolayısıyla önceleme maliyetinin okunabilir olması koşulum
karşılanmadı.

**Karar: durulur.** Gerekçe onların cümlesi:

> Yarı bağlı, koşan ama sonlanma ya da MIS fazı ince biçimde yanlış olan bir V1,
> **hiç V1 olmamasından kötüdür**, çünkü üç kollu tabloya girip makul görünen
> sayılar üretir.

Bu projede bu varsayımsal bir risk değil. bb-algo'nun Faz 4 kusurlarının
hepsi yakınsadı, temiz sayaç raporladı ve yanlıştı. V6'nın boş örtüleri de.
Sahiplik haritası tam olan kesilmiş koşumlar da. Aceleye gelmiş bir V1 o listeye
katılırdı, üstelik ötekilerden farklı olarak **harness denetlenmeyi bıraktıktan
sonra**.

### Neden tahmine inandım

Üç parçalık ayrıştırmaları belirsiz değil somut:

**Gezintiyi sürmek** tutkal, bir günlük iş.

**Dağıtık sonlanma tespiti** ayrı bir problem. İnisiyatörün yığını boşaldığında
gezintinin bittiğini yalnız o bilir. Ve `_barrier` yardım edemez, çünkü faz
üzerinden senkronlanıyor, oysa karar verilmesi gereken şey **fazın
ilerlemesinin kendisi**. Bu tür somut bir engel, tahmini temkinlilikten ayırır.

**Omurga üzerinde dağıtık MIS.** En çok hafife alınan parça. V4 bunu merkezî
yapıyor çünkü tam bilgili bir kol, V1 kategorik olarak yapamaz.

Üçüncüsü bb-algo'nun uyarısıyla daha da kötü: bütün iç düğümler CONNECTOR
işaretlenip hiç MIS kalmazsa `mis_nbrs` her yerde boş olur ve **3 atlama boşluk
kuralı sessizce hiç ateşlemez.** Çökmez, sessizce hiçbir şey yapmaz. Yani kol
daha bir kez koşmadan içine sessiz bozulma yolu yerleşmiş oluyor.

### Eksik bırakmanın bedeli düşük

V1 kanıtlı 2-yaklaşım tabanıdır, dolayısıyla yokluğu **yazılmış bir sınırdır**,
sonuçlarda delik değil. Üstelik cevaplaması istenen soruda elimiz boş değil:
ön ölçüm DFS omurgalarının büyüme öncesi düğüm ağırlığının %93,9'unu taşıdığını
(MST %18,1), büyüme sonrası %25 ağır örtü verdiğini ve farkın n ile büyüdüğünü
gösteriyor. Yön kurulmuş, merkezî ölçüldüğü etiketlenmiş durumda.

### Devir doğru yapıldı

Karar mantığı telden bağımsız ve referans ağaçla 310 örnekte sıfır uyuşmazlıkla
doğrulanmış. Devralan kişi doğruluğu zaten kurulmuş bir protokolden başlayıp
yalnız dağıtık denetimi kuracak. Kol teslim edilmediği hâlde bu sıralama
karşılığını verdi.

**İki günlük bir işi bir saatlik diye adlandırmayı reddetmek** doğru davranıştı.
İyimser tahmin yerine doğru tahmini almak, bu projede defalarca ödediğimiz
bedelin tam tersi.

## 69. Silmek ile tutmanın asimetrisi

bb-core kendi hatasıyla bb-figures'ın kararını yan yana koydu ve ortaya temiz
bir kural çıktı.

**bb-core**, etiket-hareketi kapısını tek yapılandırmada atıl ölçtükten sonra
**sildi** (madde 60). Geri keşfi kendi süitinden değil, benim entegrasyon
koşumumdan geldi (madde 49).

**bb-figures**, kendi hatasını kodlayan bir tuzağı **silmedi**; tersine çevirip
gerekçesini docstring'e yazdı.

> **Tutmak birkaç satıra mal olur, silmek bir yeniden keşfe mal olur.**

Yanlış çıkmış bir tuzak, tersine çevrilip gerekçesiyle saklandığında bir sonraki
okuyucuya "burası daha önce yanlış anlaşıldı" diyor. Silindiğinde o bilgi de
gidiyor ve aynı yanlış yeniden yapılıyor.

## 70. Okuma tuzağı: uygunsuzluğu az ilan eden kol, kusurlu görünür ama değildir

Sonuç tablosunda yanlış okunmaya en açık sütun bu, bb-core önceden uyardı.

V6 için `missed_provable_infeasible` **yapısal olarak sıfırdır**: dikişe
taşındıktan sonra V6 `run_bbcvc` üzerinden koşuyor ve sayma sınırı koldan
bağımsız olarak her koşumda hesaplanıyor. V6 bir `m > n·k` vakasını kaçıramaz,
çünkü kontrol eden V6 değil. Ölçüldü: 4 kanıtlanabilir örnek, 0 kaçırma.

`infeasible_not_cheaply_provable` sütununda ise V6 sessiz, **ve bu doğrudur**:
V6'nın Faz 3'ü yok, dolayısıyla sayma sınırı uygunsuzluk yargısına tek yolu, ve
geri kalan sınıf hiçbir top yarıçapında yerel olarak görülemiyor (madde 19, 46).

**Naif okuma** — "uygunsuzluğu neredeyse hiç ilan etmeyen kol" — tespit
kusuruymuş gibi görünür. Değildir. Raporda bu ayrım yazılmazsa V6 haksız yere
zayıf görünür.

## 71. Alarm, garantiye yükseldi: kazayı izleyen testin doğru sonu

Erişimci (madde 61) konunca bb-validate'in **kendi testlerinden biri kırıldı**
ve kırılma iyi haberdi.

Ellerinde şunu iddia eden bir test vardı: V5'te `_rule_gap` geri getirilirse
omurga değişmez. Bu, belgelenmiş **kazayı** izleyen bir alarmdı — tam komşu
listesi kuralın kendi mesafe-2 bastırma koşulunu sağladığı için kural kendini
sessizce kapatıyordu.

Erişimciyle o test düştü, çünkü geri getirilen kural artık **kalkıyor**. Testi
tam bunu iddia edecek şekilde yeniden yazdılar ve öncesini-sonrasını docstring'e
koydular.

> Önce: bir kazanın sürdüğünü izleyen alarm.
> Sonra: yanlış okumanın **olamayacağının** garantisi.

Kesinlikle daha iyi, ve kendi başlarına yazamazlardı. Bir değişikliğin başka bir
ajanın testini kırması, bazen o testin yükseltilmesi gerektiğinin işaretidir.

### Boş demet değil, istisna

V5'in erişimcisi boş demet döndürmüyor, `NotImplementedError` kaldırıyor.
Gerekçe ince: boş demet "MIS komşum yok" gibi **geçerli görünen** bir cevaptır,
kuralları sessizce koşturur ve aynı arızayı bir katman aşağıda yeniden üretir.

Aynı ilke bb-algo'nun `local_infeasibility_witness`inde de uygulanmıştı: bilgi
yokken `False` değil `None` (madde 34). **"Hesaplayamıyorum" ile "sonuç yok"
farklı ifadelerdir ve ikisini karıştırmak bu projede iki kez hataya yol açtı.**

### Neden üç sanmışlar

Okuyucuları değil **ifadeleri** saymışlar; 641. satırda tek ifadede iki okuma
varmış. Elle sayımın neden yöntem olamayacağının bir örneği daha.

## 72. BEŞİNCİ SINIF: dar dağılımdan örneklenmiş test verisi

bb-bootstrap, tamsayı-ağırlık hatasının suç ortağı taklit sınıfına (madde 15,
55) **ait olmadığını** doğru biçimde belirtti. Mekanizma farklı ve ayrı
adlandırılmalı.

**Suç ortağı taklitte** bir vekil kodla dile getirilmemiş bir varsayımda
anlaşır, dolayısıyla çelişemez.

**Burada vekil yok.** Test verisi, üretimde görülecek dağılımdan **daha dar bir
dağılımdan** çekilmiş. Kod doğru, taklit yok, ve o dağılımın **içinde** ne kadar
test yazılırsa yazılsın hata bulunamaz.

Bu sınıfın bugünkü örnekleri:

| Örnek | Dar tutulan boyut |
|---|---|
| Brief'in G8 savı | yalnız birim disk çizgeleri |
| bb-bootstrap'ın tamsayı-ağırlık kapısı | yalnız tamsayı ağırlıklı çizgeler |
| bb-algo'nun 162 testi | yalnız tamsayı ağırlıklar |
| bb-algo'nun bütçe kapsaması | yalnız yakınsamaya yeten bütçeler |
| bb-algo'nun kayıp kapsaması | yalnız temiz kanal |
| bb-core'un kapı ölçümü | yalnız sync |
| benim mesaj karmaşıklığı fitim | yalnız sync |
| benim ilk ölçüm harness'im | yalnız (kazara) kopuk çizgeler |

İki şekli var. **Dar dağılım:** sınadığın veri göreceğinin altkümesi (tamsayı
ağırlık). **Eksik eksen:** bir boyutu hiç değiştirmemişsin (hep sync, hep bol
bütçe). İkisi de örneklem uzayı kapsamıyor.

### Savunma aynı biçimde ama gerekçesi farklı

Suç ortağı taklitte savunma **taklidi gerçeğiyle değiştirmek**tir.
Burada savunma **gerçeğini bir kez koşmak**tır.

İkisi de "vekili çoğaltma, gerçeği koş" diyor, ama birinde sorun vekilin
uyumluluğu, ötekinde örneklemin darlığı. Ayrımı korumak gerekiyor, çünkü ilkinde
daha çok test yazmak **kanıtlanabilir biçimde** işe yaramaz, ikincisinde ise
doğru eksende yazılan tek bir test yeterlidir.

### Ve bu, entegrasyon koşumunun neden işe yaradığını tamamlıyor

Madde 49'da entegrasyon koşumunun bütün yeşil süitlerin kaçırdığını bulduğunu
yazmıştım. Sebebi şimdi tam: **her süit kendi dar dağılımını iyi sınıyordu**,
ve entegrasyon koşumu her birinin sabit tuttuğu boyutu değiştiren tek şeydi.

## 73. KAPAK: iki tür değişmez

bb-algo, gün boyu bulunan her şeyin altındaki ayrımı tek cümleye indirdi ve
bu belgenin kapağı olmayı hak ediyor:

> **Henüz kimse bozmadığı için tutan bir değişmez ile, bozulsa bir şey
> düşeceği için tutan bir değişmez arasındaki fark.**

Bugün bulunan her kusur birinci türdendi. Saat tabanı bir yan etkiyle tutuyordu.
Sıra numarası akranı olmadığı için çakışmıyordu. Sağlam olmayan tanık dört
vakanın üçünde kazara doğruydu. Wu-Li'nin 3 atlama kuralı, tam komşu listesi
kendi bastırma koşulunu sağladığı için sessizce kapanıyordu. λ, fikstürün
w_max'ı küçük olduğu için yeterliydi. `mis_nbrs`in yeniden kullanımı, bugünkü
çağrı çizgesinde dördüncü okuyucu bulunmadığı için güvenliydi.

Hiçbiri yanlış değildi. Hepsi **korunmasızdı**.

Ve bugün yapılan her düzeltme aynı dönüşümdü: bir şeyin öylece doğru olmasından,
yanlış olsa bir şeyin **düşmesine** geçmek. Erişimci, sentinel denetimi,
`verdict` alanı, mutasyonla sınanmış tuzaklar, çapraz görünüm sütunları, hepsi
bu.

bb-validate'in testi bu dönüşümün en temiz örneği: bir **kazanın sürdüğünü**
izleyen alarmdan, yanlış okumanın **olamayacağının** garantisine yükseldi.

### Yöntemin sınırı yine burada

Madde 52'de yazdığım sınır bu kapağın altında da geçerli: bu dönüşüm ancak
gözlenebilir bir şey yanlış olabiliyorsa kurulabilir. Sessiz sıcaklık hatasında
düşecek bir şey yoktu, çünkü yanlış olan hiçbir gözlenebilir yoktu. Orada
elimizde kalan tek şey sorudur: **bu sabit gerçekten sabit mi?**

## 74. SONUÇ: kalite ve maliyet sıralaması

Tam süpürme, küçük grup, k=6. **Kapsam sayıdan ayrılmaz:** 13 hücre, hücre
başına 3 tohum (mevcut 10'dan), 33 örnek, 6'sı kanıtlanabilir uygunsuz, ortak
altküme 28. **Kesin çözücü yalnız 15 örnekte koşuyor (n=10 ve n=15), dolayısıyla
bütün oranlar n_ratio=15 üzerinde.** Hiçbir hücre tek koşum değil.

```
kol                        exact_common   best_own  best_common   tx(common)
V6-ANNEAL/sync                   1,0674     1,0346       1,0353         3456
V6-ANNEAL-tree/sync              1,0674     1,0346       1,0353         3456
V6-ANNEAL/async                  1,1186     1,0627       1,0717         2616
V6-ANNEAL-trickle/async          1,1931     1,0930       1,1005         1679
V2-BB-local/async                1,2953     1,2437       1,2308         2166
V3-BB-tree/async                 1,2953     1,2437       1,2308         2425
V2-BB-local/sync                 1,3010     1,2574       1,2470         2621
V3-BB-tree/sync                  1,3010     1,2574       1,2470         2938
V5-BB-WuLi-full/async            1,3633     1,3179       1,3177         1700
V5-BB-WuLi-full/sync             1,3692     1,3303       1,3204         2768
V5-BB-WuLi-bloom/async           1,4557     1,3683       1,3770         1135
V5-BB-WuLi-bloom/sync            1,4557     1,3798       1,3770         2005
```

**Aşağı değil, YANA okunmalı.** Tablo tek bir sıralama değil, temiz bir
ödünleşim gösteriyor.

**V6 en iyi örtüyü veriyor ve bedelini ödüyor.** Sync'te optimumun %7 üstünde,
BB-CVC ise %30 üstünde. Ama 3456 iletim harcıyor, V2-BB-local/async 2166.
Bu, madde 25'teki kaydı **kıyas verisinde tersine çeviriyor**: `.tex`'in
işlenmiş örneğinde ANNEAL aynı ağırlığa 4-10 kat iletimle varıyordu ve ağırlık
üstünlüğü çürütülmüştü. Gerçek veride üstünlük var, ve brief §6.5'in
beklentisini kısmen iade ediyor.

**Bloom tam ayna görüntüsü:** en ucuz iletim (1135), en kötü örtü (%46 üstünde).
bb-validate'in öngördüğü boyut-nitelik ödünleşimi (madde 24), ve şekil 6'nın
(d) panelinde omurganın bütün düğüm kümesine eşit olması olarak görünüyor.

**V3-BB-tree, V2-BB-local'in ağırlığını her satırda BİREBİR eşliyor ve %12-15
daha çok iletim harcıyor.** Faz 5b ölçüm amaçlı olduğu için ağırlığın aynı
olması gerekir, dolayısıyla fark **saf ölçüm ek yükü**. `phase5` ekseni bunu
temiz izole ediyor; eksenin var olma sebebi buydu.

### HAYATTA KALMA DENETİMİ: V6 güzelleşmemiş

Sorduğum soru buydu ve cevap kesin. V6-ANNEAL/sync'in **kendi** altkümesindeki
oranı 1,0346, **ortak** altkümedeki 1,0353. Ortak sayı 0,0007 daha **KÖTÜ**,
yani düştüğü örnekleri çıkarmak konumunu iyileştirmiyor.

Daha güçlüsü: V6 sync ortak altkümeye 33'ün **31'iyle** katılıyor, ki bütün
kolların en büyük eksiği, **ve yine de** kısıtlamadan kazanç sağlamıyor.

**Yönü okumak belirleyici.** BB ve V5-sync kolları kendiden ortağa **aşağı**
iniyor (başarısızlıkları daha zor örneklerdeydi), V6 ve V5-bloom ise **yukarı**
çıkıyor. Yukarı hareket, hayatta kalma güzellemesinin **olamayacağı** yöndür.

Bütün kolların `exact_common` oranı aynı 15 örnek üzerinde (n_ratio=15),
dolayısıyla sıralama benzerle benzer.

### `.tex` ile kıyas verisi ÇELİŞMİYOR, ikisi de doğru

Madde 25'te V6'nın brief'in ağırlık üstünlüğünü yeniden üretmediğini yazmıştım.
Yukarıdaki tablo tersini söylüyor gibi duruyor, ama bb-figures ikisini
uzlaştırdı ve uzlaşma bulgunun kendisi:

İşlenmiş 10 düğümlük örnekte `|C| = ceil(m/k) = 8`, yani **G6 alt sınırı
tarafından zorlanmış**. Orada daha hafif olmaya yer yoktur, tavlama yalnız mesaj
harcayabilir. Kıyas verisinin k=6 hücreleri ise o sınırdan uzaktır ve tavlamanın
kullanacağı boşluk oradadır.

Dolayısıyla doğru ifade **düz bir tersine çevirme değildir**:

> §6.5'in ağırlık beklentisi **gevşek kapasitede iade edilmiştir**, alt sınırda
> ise çürütülmemiş, yalnız uygulanamaz olmuştur.

**Kapsam uyarısı:** bu tek bir grubun tek bir süpürmesidir. Üstüne ağırlık
koymadan önce orta grup koşulmalıdır.

### Hayatta kalma makinesi: asıl hikâye SIRA

Önceki koşumda altı kol 0,024-0,028 aralığında sapma uyarısı taşıyordu. Bu
koşumda **sıfır**, ve ortak altküme 27'den 28'e çıktı.

Sebep, uyarıların **gerçek başarısızlıkları izliyor olması**. Önceki koşumda V6
bazı uygun örneklerde düşüyordu (bb-core'un kopuk örtü kalıntısı, 3 yanlış
başarı) ve V5 sync kolları birer örnek kaybediyordu; bu düşmeler ortak altkümeyi
daraltıp kendi/ortak oranlarını ayırıyordu. loop-C düzeltmesi V6'nın
başarısızlıklarını kaldırınca kollar aynı örneklerde başarılı oldu ve iki
altküme neredeyse çakıştı.

> **Araç iki yönde de doğru davrandı:** hayatta kalanları güzelleştirecek
> başarısızlık varken ateşledi, başarısızlıklar düzeltilince sustu.

Raporda altı uyarı **güncel bulgu olarak yazılmaz**. Doğru ifade şudur:
"mekanizma düzeltme öncesi veride 0,024-0,028 aralığında ateşledi ve düzeltme
sonrası sıfıra indi", ki bu araç hakkında iki sayıdan da güçlü bir ifadedir.

### Ortak altküme dışındaki kalıntı başarısızlıklar

V5-BB-WuLi'nin üç sync kolu `n25_m150_s1`de birer `unresolved`, ve beş V6 kolu
`n15_m30_s3`te birer `truncated`. Üç V5 satırı, bb-algo'ya giden ters yönlü
uyuşmazlıkların ta kendisi: doğrulayıcı o örtülerde sıfır ihlal buluyor, yani
**kollar kendi başarılarını göremiyor**.

### Harness'ın son durumu

```
585 satır, 56 sütun, 15 kol
ok 485 · infeasible 90 · unresolved 5 · truncated 5 · contradiction 0
gerçek iz uyuşmazlığı: 0   (42'den; 30'u doğru-ama-beklenen -> n/a, 12'si bb-figures'ın hatası)
```

90 uygunsuz satır, altı kanıtlanabilir uygunsuz hücrenin her kolda doğru ilan
edilmesi. Önce hepsi `unresolved` diyordu.

> Sıfır-dışı girdisi gerçekten bir şeyin yanlış olduğu anlamına gelen bir
> çapraz denetim sütunu, o sütunların kurulma amacıdır. Buraya **eşik
> gevşeterek değil, üç ayrı hatayı bularak** gelindi.


## 75. SINIFIN ÜÇÜNCÜ YERİ: yalnız sorun varken basan rapor

Boş test sınıfı (madde 15) testlerde, sonra ölçümlerde (madde 72) çıkmıştı.
bb-figures onu **raporlamada** buldu.

`summary.md`'nin çapraz denetim bölümleri **yalnız bir şey yanlışken**
basılıyordu. Yani "koştu ve hiçbir şey bulmadı" ile "hiç koşmadı" okuyucu
açısından **ayırt edilemez** hale geliyordu.

Bu tam olarak aynı hata: bir denetimin sessizliği, iki bambaşka anlama gelip
hangisi olduğu söylenemiyor.

**Çözüm:** her zaman basılan bir karne, sıfırlar dahil.

```
yanlış başarı (contradiction)     0
beyan-doğrulayıcı uyuşmazlığı     3
iz-çözüm uyuşmazlığı              0
iz: uyumlu / n-a / izsiz          165 / 30 / 390
kesik koşum (truncated)           5
kopuk girdi (bad_input)           0
```

İki testle çivilendi: temiz koşumda sıfırların **bastığı** ve karnenin ayrıntı
bölümlerinden **önce** geldiği, ve gerçek bir başarısızlıkta sayının değiştiği.

> **Sıfır basılmayan bir rapor, sıfır olduğunu söylemez; hiçbir şey söylemez.**

Sınıf artık üç yerde görüldü: **testte** (ateşlemeyen denetim), **ölçümde**
(dar dağılım), **raporda** (basılmayan sıfır). Üçünde de sessizlik iki anlama
geliyor ve hangisi olduğu belirtilmiyor.

## 76. Ailenin dördüncüsü: ÇİFTE sahiplenilen kenar (bulundu, izlendi, düzeltildi)

Üç kolun "kendi başarısını görememesi" bayat bayrak değildi. **Düğüm haklıydı.**

```
n25_m150_s1 (GERCEK veri kümesi dosyası), k=6, sync
düğüm 15: node.owned = 7 kenar, k=6
kenar (15,19) HEM 15 HEM 19 tarafından sahipleniliyor
toplam iddia 151, kenar 150, sahipsiz 0
doğrulayıcı: GEÇERLİ, 0 ihlal
```

### Mekanizma (bb-algo izledi, çıkarsamadı)

Slot 508'de düğüm 19, 15'ten gelen PUSH işini servis ediyor. Zincir yoklaması
nihayet başarılı oluyor, kenarı **kabul ediyor** ve PUSH_ACK gönderiyor. Ama
düğüm 15'in bekleyen isteği yüzlerce slot önce `R_max`'ı tüketip **vazgeçmişti**.
ACK indiğinde eşleşen kayıt bulunamıyor ve **atılıyor**. 19 taahhüt etmiş, 15 hiç
bırakmamış.

**Bu, aynı gün yapılan vazgeçme düzeltmesinin aynasıdır.** Vazgeçme
güvenlileştirilirken yalnız **GÖNDEREN** için güvenlileştirilmiş: tükenmeyi NACK
say, bırakma. **ALICININ sonradan hâlâ taahhüt edebileceği** hiç düşünülmemiş.
Koruma tek yönlüydü.

### Düzeltme

Geç gelen olumlu yanıt **yetkilidir**. Eşleşen bekleyen kayıt yokken bir ACK
gelirse ve kenar hâlâ bendeyse ve akran öbür uçsa, bırakırım. Tek tutarlı sonuç
budur ve kenarı sahipsiz bırakamaz, çünkü akran ancak kendisi ACK alırsa bırakır.

96 koşumda doğrulandı (V2 ve üç V5 kodlaması, iki kapasite, iki zamanlayıcı):
sıfır çifte iddia, sıfır sahipsiz kenar, **425 geç ACK işlendi**.

### EN ÇARPICI AYRINTI: temiz görünen kollar da hastaydı

Yol tek bir koşumda **8-16 kez** ateşliyor. Ve `full` ile `chunked` kolları
**zaten `solved` ve geçerli rapor ediyordu**, 150/150 sahiplikle — üstelik her
biri **16 geç ACK günlüğe yazarken**.

Aynı yarış onlarda da vardı, yalnız son duruma **denk gelmemişti**. O kollarda
kusur yok değildi, **gizliydi**.

Bu, madde 55'in en net örneği: temiz sayaç, geçerli sonuç, ve altında koşan bir
tanım ihlali.

### Görünmezliğin kaynağı ve kapatılması

`owner[e] = nid` satırı çifte iddiayı tek girdiye çökertiyordu: harita 150/150
tam, her kenarın tek sahibi, kimse taşkın değil, doğrulayıcı geçiyor. Tek iz,
düğümün özel görüşünün toplamla çelişmesiydi ve hiçbir tüketici oraya bakmıyordu.

Artık `BbcvcRun.double_claimed` çakışmayı **sözlük yutmadan önce**, düğüm başına
`owned` kümelerinden topluyor. Boş olmaması tanım ihlali demektir ve koşum
raporlanabilir değildir. Canlı doğruladım: n=40, 60, 80'de üçü de boş.

### Kendi testi kırıldı ve doğrusu buydu

bb-algo `repair_recovered` yolunu belirli bir örneğe çivilemişti. Sahiplik yarışı
düzelince hayalet aşırı yük kalktı, düğüm artık pes etmiyor, test boşaldı.
Mekanizmayı doğrudan süren bir teste çevirdiler: bir dış komşu bayrağı temizler,
üç tanesi temizlemez. Örneği değil **kuralı** sınıyor artık (madde 47).

### Ailenin kapanış dersi

Dört hata: üçü kenar **kaybetti**, biri **çoğalttı**. Ve çoğaltan, hiçbir
tüketicinin göremediği tek olandı — kaybedenlerin üçü de `bad_owner`a takılmıştı.

> **Bir korunum yasası ancak İKİ YÖNDE birden denetlenirse zorlanmış olur.**

### Ve reçeteyi yeniden koşmasam yanlış tartışacaktım

bb-mnwifi yeniden üretemediğini bildirdiğinde cevap vermeden önce **kendi
reçetemi yeniden koştum**. Bende de çıkmıyordu, çünkü arada düzeltilmişti.
Hafızadan tartışsaydım, bugün herkese dayattığım kuralı üçüncü kez çiğnemiş
olacaktım.


## 77. PLATFORM DEĞİŞİKLİĞİ: hedef mininet-wifi, ESP32 değil (kullanıcı, 2026-09-15)

Kullanıcı hedef platformu netleştirdi: kod **mininet-wifi** için, ESP32 için
değil. Bu, birkaç kısıtın **gerekçesini** değiştiriyor, çünkü bir kısıtın
gerekçesi okuyucunun onu beklemesi gerekip gerekmediğini belirler.

bb-core denetimi yaptı, bb-mnwifi gerçek sınırları ölçtü. Karar tablosu:

| Kısıt | Eski gerekçe | Durum |
|---|---|---|
| MAC adresleme | ESP-NOW ve 802.11 | **Aynen geçerli, hatta güçlü** |
| 250 B yük | ESP-NOW satıcı sınırı | **Kendi koyduğumuz kısıt**, hiç bağlamıyor |
| 16.16 sabit nokta | ESP32-C3'te FPU yok | **Yalnız TELDE**, gerekçe belirlenimcilik |
| Tamsayı ağırlık | aynı | Şimdilik duruyor, gerekçesi yazıldı |
| 64 girdilik komşu tablosu | cihaz belleği | **Kendi koyduğumuz kısıt**, tutulacak |
| Enerji modeli (100/240 mA) | ESP32 radyo akımları | **Türetilmiş kestirim**, etiketlendi |

### Ölçülen gerçek sınırlar (bb-mnwifi)

`IP_PMTUDISC_DO` ile gerçek bir dinleyiciye karşı ölçüldü, alıntılanmadı: en
büyük kabul edilen datagram tam `MTU − 28`, bir bayt fazlası `EMSGSIZE`.
İstasyon MTU'su 1500 (mininet-wifi hiç atamıyor, mac80211 varsayılanı), yani:

```
etkin UDP yükü = 1500 − 20 (IP) − 8 (UDP) = 1472 bayt
```

802.11'in MSDU tavanı 2304, dolayısıyla **netdev MTU önce bağlıyor, radyo değil.**

Protokolün gerçekte durduğu yer:

```
ölçülen max_payload, işlenmiş örnek      17-21 B
sabit mesajların tamamı                  <= 25 B
HELLO, kıyas verisinin en kötü derecesi     85 B
HELLO 250 B'ye ilk değdiği derece          118
HELLO 1472 B'ye ilk değdiği derece         729
```

Yani en kötü yoğunlukta bile **yaklaşık 60 kat boşluk** var. 250 artık
"yaklaştığımız sınır" değil, hiç bağlamayan bir taşınabilirlik tercihidir ve
öyle yazılmalıdır.

### En tehlikeli kalem listede yoktu: ENERJİ MODELİ

`Counters.energy_mah` 100 mA dinleme, 240 mA iletim, 0,7 ms çerçeve süresi diye
sabitliyor. Bunlar ESP32'nin 1 Mbps radyo akımları. Mininet-wifi istasyonu ise
**radyosu ve akım çekimi olmayan bir Linux süreci.** Yani hedef platformda
hiçbir şeyin ölçümü değil, emüle zamanlamalara uygulanmış bir ESP32 güç modeli.

**Ve şekil 8 onu çiziyor.** Bir hakemin ilk saldıracağı sayı bu olur ve geri
kalanı sağlam olan sonuçları gölgeler.

Karar: **tutulur, her yerde etiketlenir.** Kollar arası karşılaştırma anlamlı
kalır çünkü hepsi aynı modeli kullanır, ama mutlak bir enerji rakamı değildir.
Ad `energy_mah_esp32_model` oldu ve uyarı `ENERGY_LABEL` olarak **kodda değerin
yanında** duruyor, çünkü docstring'e yazılan çekince figür başlığına gitmez
(aynı kural: `observer_best_weight`, madde 42).

### Sabit nokta iddiası olduğu gibi YANLIŞ olurdu

bb-core'un açıklaması yayımlamadan önce yapılması gereken cinsten: **V6 içeride
IEEE double kullanıyor** — λ, T₀, her Metropolis kabulü, bütün enerji hesabı.
Sabit nokta yalnız telde (anahtar 16.16, ℓ 8.8). "§3.6 uyarınca her yerde sabit
nokta" cümlesi kodun bugünkü hâlinde **yanlış** olurdu.

### Bellek tavanı iki kat kötümserdi (benim hatam)

n=200'ü 4,4 GB diye kaydetmiştim, RSS'ten. bb-mnwifi on canlı süreçte
`smaps_rollup`'tan PSS ölçtü: süreç başına RSS 17,1 MB, **PSS 10,5 MB**, çünkü
bütün düğüm süreçleri aynı yorumlayıcı ve libc sayfalarını paylaşıyor. RSS %63
abartıyor. Doğru tavan **~2,1 GB**, ve bağlayıcı kısıt bellekten **duvar
saatine** kayıyor.

### Dört platform çağrısı: iddia değil SONUÇ

bb-mnwifi benim soruşumu düzeltti. "Hâlâ geçerli mi" diye sormuştum; cevap
"bu bir iddia değil, zaten elindeki sonuç": aynı değiştirilmemiş düğüm kodu on
ayrı işletim sistemi sürecinde simülatörü birebir yeniden üretiyor, dolayısıyla
bütün farklar arayüzün **altında**. Gelecek bir platform için varsayılmış değil,
**referans platformda doğrulanmış**.

### MAC: gerekçe güçlendi, uygulama bir vekil

İki yarı da yazılmalı. **Gerekçe:** 802.11 her çerçeve başlığının Address 2
alanında verici adresini zorunlu kılar, üstteki hiçbir şeyden bağımsız olarak.
ESP-NOW bunu sağlamaz, devralır. Mininet-wifi referans olunca gerekçe satıcı
protokolüne değil **standarda** dayanıyor, yani güçleniyor.

**Uygulama:** UDP soketi 802.11 başlığını göremez, `UdpPort` göndericinin MAC'ini
kaynak IP'den tablo bakarak kurtarıyor. Düğümün sözleşmesi bozulmuyor (yük hiç
açılmıyor) ama adres telden gelmiyor.

Ham soket (`AF_PACKET`) bunu kapatır ve ESP-NOW'un adresleme modeline **daha
yakındır**, ama portun tamamını kapsayan ayrıcalıksız testleri takas eder.
Şimdilik ertelendi; yapılırsa UDP yolu sınanabilir yol olarak kalmalı, ham soket
tercihe bağlı kip olmalı.

## 78. Denetim, yakalamak için kurulduğu arızayı gösteremeyen yapıya yazıldı

bb-bootstrap'ın kendi gözlemi ve bugünün en keskin cümlesi:

> `unowned_edges`i, hepsi "iyi görünen" üç hatanın ardından ekledim, sonra onu
> **dördüncüyü gösteremeyen tek veri yapısına karşı** yazdım.

`owner[e] = nid` ikinci yazanın birinciyi ezmesi demektir, yani **harita arızayı
temsil edemez**. Onu okuyan her denetim "her kenarın sahibi var mı" diye sorar
ve evet alır. Sahipsiz kenarı görür, çifte sahiplenileni göremez, ve bunu
göremediğini de söyleyemez.

Düzeltme, denetimi **toplanmadan önceki** veriye taşımak oldu: düğüm başına
`owned` kümelerinden iddia saymak. Ve kanıtı yapıya değil **davranışa** yazdılar:
üç kenarlık bir vaka kurup `owner`ın 3/3 tam göründüğünü, `unowned_edges`in boş
döndüğünü ve `double_owned_edges`in yakaladığını birlikte iddia ediyorlar.
Yönelim de ele alınmış, `(v,u)` ile `(u,v)` tek kenar sayılıyor.

**Genel kural:** bir denetim, sınadığı arızayı **temsil edebilen** bir yapı
üzerinde çalışmalıdır. Toplanmış bir görünüm üzerinde çalışan denetim, o
toplamanın sildiği her şeye kördür ve körlüğünü bildiremez.

## 79. Bileşen haklıydı, TOPLAM yanlıştı

Aynı vakanın ikinci dersi ve alışılmış varsayımı tersine çeviriyor.

Üç kol `unresolved` bildirdi, doğrulayıcı örtüleri temiz buldu. İlk tepki
"kol kendi başarısını göremiyor" oldu ve bb-algo bayat bayrak hipotezine
yönlendirildi. Oysa:

> **Düğüm haklıydı, toplam yanlıştı.**

Düğüm 15 gerçekten k=6 iken 7 kenar tutuyordu ve `unresolved`ı doğru
kaldırıyordu. Yanlış olan, çifte iddiayı tek girdiye çökerten owner
haritasıydı.

Genelde özetin bileşenden güvenilir olduğu varsayılır: tek düğümün görüşü
kısmidir, toplam ise bütünü görür. Burada tersi geçerliydi, çünkü **toplama
işlemi bilgi siliyordu.** Bir çelişkide hangi tarafın kaybettiği, hangisinin
daha çok bilgi taşıdığına bakılarak belirlenmeli, hangisinin daha üst düzeyde
olduğuna değil.

## 80. V4-BB-MST: dağıtık GHS'te beş hata ve hepsinin ortak kökü

V4-BB-MST, Gallager-Humblet-Spira'yı `_backbone_step` dikişine oturtuyor.
Kurgu aileleri geçtiği hâlde gerçek veri kümesinde 7/12'de kalıyordu. Beş
ayrı arıza çıktı ve dördü tek bir hata sınıfının farklı yüzleriydi:
**bilmemeyi bilgi sanmak.**

**(a) Parça kimliği tel üzerinde kırpılıyordu.** Parça kimliği bir 16.16
sabit noktalı kenar ağırlığı, tel alanı ise 2 baytlıktı. Her kimlik aynı
değere çöktü, her TEST eşit karşılaştırdı ve REJECT aldı, hiçbir düğüm dışa
giden kenar bulamadı. `frag` 4 bayta genişletildi.

**(b) Ölçüt asimetrikti.** Düğüm A `to_fp(w_A) + yeniden_kurulan(w_B)`, B ise
`yeniden_kurulan(w_A) + to_fp(w_B)` hesaplıyordu. `w/(deg+1)` tam bölünmediğinde
bunlar ayrışıyor: ölçüldü, w=1 ve deg=4 için 65536'ya karşı 65535. Bir birimlik
fark bir birimlik sonuç vermedi, bir birleşmenin iki ucu aynı parçaya **farklı
kimlik** atadı. Artık her düğüm kendi ağırlığını da karşı tarafın gördüğü
kayıplı biçimde kuruyor, yani iki taraf aynı sayıyı şansa değil inşa gereği
buluyor.

**(c) Ertelenmiş ileti yanıt sanıldı, sonra her ertelenmiş ileti engel sayıldı.**
İlk hâlde bir parça, iki TEST hâlâ ertelenmişken `best == INF` görüp durdu,
yani "belirleyemedim"den "yok" sonucunu çıkardı. Düzeltme her ertelemeyi engel
sayınca bu sefer çember kapandı. Doğru ayrım şu: **yalnız kendi cevapsız sorum
engeller.** Ertelenmiş REPORT başkasının erken gelen cevabı, ertelenmiş CONNECT
başkasının katılma isteği; ikisi de beni FIND'de tutmamalı. Ölçüldü, n15_m30
s1 sync'te üç parça seviye 1'de kilitlendi, düğüm 14 tek çocuğu rapor vermişken
rapor veremiyordu çünkü ancak kendi raporunun serbest bırakabileceği bir
CONNECT'i tutuyordu.

**(d) Sonsuz TEST döngüsü.** ACCEPT kenar durumunu değiştirmez, bu doğru GHS'tir;
ama `_ghs_test` her adımda `_ghs_try_report`'tan önce koşuyordu, dolayısıyla
ACCEPT `test_nid`'i temizler temizlemez aynı kenar yeniden sınanıyordu. `bridge`
ailesinde 4 ile 5 birbirini sonsuza kadar test etti. `ghs_test_done` eklendi ve
yalnız `_ghs_initiate`'te sıfırlanıyor, çünkü yeni parça aramayı yeniden açar.

**(e) Eksik bilgiyle uyanmak.** En sinsisi buydu. Uyuyan düğümün parçası tekil,
dolayısıyla en hafif komşu kenarı seçmesi gerekir; ama komşunun ağırlığı ancak
derecesi bir HELLO'yla geldikten sonra kurulabiliyor, öncesinde `_peer_w`
`INF_W` dönüyor. Gelen bir CONNECT uyuyan düğümü uyandırırken bu denetlenmiyordu.
Ölçüldü, n10_m20 s2'de düğümü 8'in en hafif kenarı (7,8)=545 iken 7'nin derecesi
gelmeden uyandı ve (4,8)=565'e bağlandı.

Bu sonuncusu neden ayrı bir ders: koşum **sonlandı**, doğru sayıda kenar
üretti, doğrulayıcıdan temiz geçti ve `solved` dedi. Hiçbir kapı ötmedi. Yalnız
ağaç 8480 ağırlığındaydı, gerçek minimum ise 7708. İlk tepkim "ağırlıklar eşit,
iki farklı ama eşit ağırlıklı MST çıkmış olmalı" oldu; ölçtüm, eşit ağırlıklı
kenar çifti yoktu ve ağaç gerçekten minimum değildi. **Doğrulanan yanlış cevap,
çöken koşumdan kötüdür,** çünkü çöken koşum kendini bildirir.

Uyuyan düğüm artık kenarlarını sıralayamıyorsa CONNECT'i erteleyip uykuda
kalıyor. Kurgu aileleri 10/10, küçük grubun tamamı (3 tohum × iki çizelgeleyici)
kapıyı geçiyor.

## 81. Kapıyı kuran, kapının ayırt etmesi gereken ayrımı yaptı mı

V4'ün küçük grup kapısı 61/78 verdi ve 17 satır düştü. İlk okuyuşta bu 17
arızaydı. Değildi.

On satır n20_m160 ve n25_m200 hücrelerindendi. Bu hücrelerde ortalama derece
16, k ise 6. Her düğüm en çok k kenar sahiplenebildiğine ve her kenarın bir
sahibi olmak zorunda olduğuna göre toplam kapasite n·k'dır, dolayısıyla
m > n·k ise hiçbir örtü, hiçbir sırayla çalışamaz. Ölçüldü: 20·6 = 120 < 160
ve 25·6 = 150 < 200. Bu örnekler **kanıtlanabilir biçimde imkânsız**.

Üç şeyi ayrı ayrı doğruladım, çünkü üçü ayrı iddia:

1. Taban BB-CVC aynı örneklerde k=6'da aynen `unresolved` veriyor, yani arıza
   V4'e özgü değil.
2. İkisi de k=12 ve k=20'de `solved` ve doğrulayıcıdan temiz geçiyor, yani
   arıza örneğin kendisinde değil, k ile örneğin bileşiminde.
3. Koşum zaten `infeasible=True, infeasible_reason='counting_bound'`
   bildiriyor, yani kod bunu **baştan beri doğru söylüyordu**.

Yanlış olan kapı betiğiydi. Geçme ölçütünü `verdict == "solved" and valid`
diye yazmıştım, oysa imkânsız bir örnekte ikisi de erişilebilir değil. Brief
bunun için üçüncü bir değer tanımlıyor ve ben onu kullanmayı ihmal ettim.

**Ders, ölçüm aracının kendisi hakkında.** `infeasible` ÖRNEK, `verdict` ise
KOŞUM hakkındadır ve kod bu ayrımı `counting_bound_infeasible` ile özenle
kuruyor. Kapıyı kuran kişi o ayrımı okumayınca, doğru çalışan bir sistemin
doğru yanıtı on kez arıza diye sayıldı. Bir denetim, denetlediği sistemin
zaten yaptığı ayrımı yapmıyorsa, sistemi değil kendini ölçer.

Kalan yedi satır gerçek: m/n=2 olan seyrek hücrelerde koşum `truncated` ve
üçünde omurga yanlış. Sürenin on katıyla da değişmiyor, dolayısıyla zaman
sınırı değil.

**Deney tasarımına doğrudan sonucu:** matris hücreleri `m <= C(n,2)` ile
eleniyor, yani yalnız ÇİZGE olarak kurulabilirlik denetleniyor. Kapasite
kurulabilirliği (n·k >= m) denetlenmiyor. Sabit k ile bütün matrisi koşmak,
yoğun hücrelerde algoritmaları değil k'yı ölçer. Ya k yoğunlukla ölçeklenmeli
ya da bu hücreler raporda `n/a` olarak, imkânsızlık gerekçesiyle görünmeli.

## 82. Tam sıra için gereken bilgi, tel sınırında üç kez düştü

V4'ün son iki arızası ve ikisi de aynı kökten.

**Uyuyan düğüm soruyu düşürüyordu.** `_ghs_on_test`, `ghs_state == SLEEPING`
iken hiçbir şey yapmadan dönüyordu: soru ne cevaplanıyor ne erteleniyordu.
Gönderen o cevaba kilitli ve zaman aşımı yok, çünkü `ghs_test_nid` doluyken
`_ghs_test` bir daha sormuyor; dolayısıyla düşen bir TEST kalıcı. Klasik GHS'te
bu durum yok, orada herhangi bir ileti uyuyan düğümü uyandırır. Burada
uyandıramıyor, çünkü bir önceki düzeltme düğümün komşu ağırlıklarını
öğrenmeden uyanmasını yasakladı. **Kendi düzeltmem hatanın penceresini
genişletti.** n20_m40 s2 async'te ölçüldü: iki parça seviye 1'de kilitli,
düğüm 11'in 8'e ve düğüm 14'ün 20'ye sorusu bu satırda kaybolmuş.

Bu, oturumdaki üçüncü "cevaplayamıyorum ile cevap yok aynı değil" vakası.

**Çekirdek karşılaştırması eşitlikte tanımsızdı.** `_weight_of` zaten düzgün
bir tam sıra döndürüyor, `(w(u)+w(v), min id, max id)`. Ama yalnız BİRİNCİ
bileşeni saklanıp REPORT'ta taşınıyordu. Çekirdekteki iki düğüm kendi yarısının
en hafif dışa giden kenarını bildirir ve küçük olan davranır; eşit ağırlıklı
FARKLI iki kenar eşit karşılaştırınca ne `>` ne de durma koşulu ateşliyor ve
iki taraf birbirini bekliyor.

n25_m50 s2'de ölçüldü, ki bu örnek sınadığım bütün örnekler içinde en çok
eşitliğe sahip olanı (iki grup, dört kenar): beş parça seviye 1'de donmuş,
herkes FOUND, bekleyen TEST yok, düğüm 1'in 58392575'i düğüm 9'un
58392575'ine karşı ve bunlar farklı kenarlar. REPORT artık kullanılmayan
`frag` alanında eşitlik kırıcı iki kimliği taşıyor.

Burada kendi yöntemim hakkında bir not düşmek gerekiyor. n10_m20 s2'de omurga
yanlış çıktığında ilk açıklamam "eşitlik vardır, iki farklı ama eşit ağırlıklı
MST çıkmıştır" olmuştu. Ölçtüm, o örnekte hiç eşit ağırlıklı kenar çifti yoktu
ve hipotezi attım; hata başkaydı. Aynı hipotez n25_m50 s2'de doğru çıktı.
**Bir açıklamanın bir vakada yanlış olması onu her vakada yanlış yapmıyor,
ama her vakada ayrıca ölçülmesi gerekiyor.**

**Tel sınırı, bu oturumda üç kez aynı biçimde bilgi sildi:**

1. Parça kimliği 32 bitlik sabit noktalıydı, alan 2 baytlıktı (§80a).
2. Ağırlık iki uçta farklı kurulduğu için sıra iki uçta farklıydı (§80b).
3. Sıralama anahtarı üç bileşenliydi, taşınan bir bileşendi (bu madde).

Üçünde de kod çalışıyor, iletiler gidip geliyor ve sistem kendini sağlıklı
sanıyordu. Bir protokolde karşılaştırılan her değerin, karşılaştırmayı
yapmaya YETECEK kadarının tele sığdığı ayrıca doğrulanmalı.

**Kapı sonucu:** küçük grubun tamamı, üç tohum, iki çizelgeleyici —
geçen 66, `n/a` 12 (kapasite bakımından kanıtlı imkânsız), düşen 0.
V4-BB-MST sweep'e kaydedildi.

## 83. İlk tam ölçüm: V4 nerede duruyor ve tavlama neyi pahalıya alıyor

Küçük grubun tamamı, k=6, üç tohum, iki çizelgeleyici, 975 koşum, tek kod
sürümü. 39 örneğin 6'sı kapasite bakımından kanıtlı imkânsız (§81), kalan
33'ün 30'u bütün kolların geçerli çözüm ürettiği ortak altkümeyi kuruyor,
15'inde kesin çözücü referansı var.

Kesin optimuma oran (`ratio_exact_common`), ortak altkümede:

| kol | oran | tx |
|---|---|---|
| V6-ANNEAL(-tree)/sync | 1,067 | 2943 |
| V6-ANNEAL(-tree)/async | 1,119 | 2687 |
| **V4-BB-MST/async** | **1,192** | **2752** |
| V6-ANNEAL-trickle/async | 1,193 | 1721 |
| V4-BB-MST/sync | 1,198 | 3023 |
| V2/V3-BB-local(-tree)/async | 1,295 | 1955 |
| V1-DFS/async | 1,303 | 4662 |
| D-GWCCVC-BB/async | 1,364 | 1840 |
| V5-BB-WuLi-full/async | 1,363 | 2020 |
| V5-BB-WuLi-bloom | 1,456 | 1162 |

**V4 tavlama dışındaki bütün kolları açık farkla yeniyor**: en yakın rakibi
V2-BB-local'a göre yaklaşık yüzde 8 daha iyi çözüm.

Ama karşılaştırmayı V4 lehine kırpmamak gerekiyor. İlk dilimde (yalnız
n=10,15) V4 hem tavlamadan çok daha ucuzdu hem ona yakındı; **ölçek büyüyünce
o avantaj kayboldu.** Tam grupta V6-ANNEAL-trickle V4'ün kalitesini tam olarak
yakalıyor (1,193'e karşı 1,192) ve bunu iletinin yüzde 62'siyle yapıyor.
Tavlamanın ağaç kipi ise hem daha iyi hem aynı maliyette. Yani ölçülen veriye
göre **tavlama V4'ü domine ediyor.**

V4'ün elinde kalan tek nicel üstünlük sonlanma: bütçesini dolduran beş koşumun
**hepsi tavlama** (V6-ANNEAL, -tree ve -trickle), V4'te ve diğer bütün kollarda
sıfır. Bu sayı küçük ama yönü açık, çünkü tavlama bir anytime yöntemi ve
bütçeyle sınırlanması doğasının parçası.

Burada ortak altküme kuralının neyi koruduğunu söylemek gerekiyor. Tavlama üç
örnekte düşüyor, ortak altküme kuralı o örnekleri **bütün kollardan** atıyor,
dolayısıyla tavlamanın yukarıdaki oranı yalnız başardığı örneklerde ölçülmüş
oluyor. Kural olmasaydı tavlama zor örneklerden sessizce düşer ve ortalaması
iyileşirdi; başarısızlık kötü bir değer olarak değil, hiç değer olmayarak
görünürdü.

**Yan bulgu, çizelgeleyici.** V1-DFS asenkronda senkrondan çok daha ucuz
(4662'ye karşı 7532 ileti, yüzde 38 az) ve bu fark bütün kollar içinde en
büyüğü. Tavlama ise ters yönde: asenkron kipte çözüm kalitesi düşüyor
(1,067 -> 1,119), çünkü eşzamansız güncellemeler kabul kararlarını bozuyor.

## 84. n=50'de tavlama kendini doğru sanan yanlış cevap veriyor

Orta grubun ilk basamağı (n=50, m/n ∈ {2,4}, k=6, 3 tohum, 150 koşum, tek kod
sürümü) küçük grupta hiç görülmeyen bir şey çıkardı: **5 `contradiction`**,
yani kol `solved` diyor, doğrulayıcı katılmıyor.

Dokuz sorunlu satırın hepsi V6-ANNEAL ailesinden ve ihlal her seferinde aynı:
`disconnected`. V4-BB-MST, V1-DFS, V2, V3, V5 aileleri ve üç açgözlü taban
n=50'de sıfır sorun veriyor.

Ölçtüm: n50_m100 s3 sync'te örtü 31 düğüm, iki bileşen (29 ve 2), ve bileşenler
arasında **tek bir örtü dışı düğüm** var. Yani köprü teşvikinin ateşlemesi
gereken tam da o yapı. `anneal.py` bu sınıfı zaten biliyor; kopukluğun nedeni
daha önce `_loop_c`'de bayat etiketin ölmemesi olarak bulunmuş, bir onarım
denenmiş ve **başka bir kusur ürettiği için geri alınmış** (örtüyü |C|=2'ye
soyup kenarları örtüsüz bırakıyormuş). Küçük ölçekte kapanan bu sınır n=50'de
geri geliyor.

Kapsam kararı: V6 karşılaştırma tabanı, katkı değil. Süpürme bu satırları
`contradiction` olarak yakalayıp ortak altkümeden dışlıyor, dolayısıyla kıyas
kirlenmiyor ve figürler etkilenmiyor. Tavlamanın tavlama dinamiğini onarmak bu
oturumun işi değil; **bildirilmesi** işi.

**Ama sonucun kıyasa bedeli var ve söylenmeli.** Tavlama 6 örneğin 3'ünde
düştüğü için ortak altküme 3'e iniyor, yani n=50 kıyası üç örnek üzerinde
duruyor ve n=50'de kesin çözücü koşamadığından yaklaşım oranı sütunu tamamen
boş. Bu tabloyla "tavlama en iyi" demek, tavlamayı yalnız başardığı örneklerde
ölçüp başaramadıklarını herkesin tablosundan silmek olurdu.

**§83'ün okunuşu bu yüzden değişiyor.** Küçük grupta tavlama V4'ü domine
ediyordu ve bunu yazmıştım. n=50'de tavlama hâlâ daha iyi sayı üretiyor ama
ürettiği sayının geçerli olup olmadığını **kendisi bilemiyor**; V4 ise her
satırda geçerli. İki kol arasındaki fark artık yalnız kalite-maliyet
ödünleşmesi değil, cevabın güvenilirliği.

Yan bulgu: n=50'de V2, V3, V5 aileleri ve üç açgözlü tabanın hepsi ortak
altkümede tam olarak aynı orana (1,3955) çöküyor. Hepsi aynı MIS Faz 1'ini
paylaşıyor ve bu ölçekte aynı örtüyü buluyorlar. V4 (1,318-1,335) ve V1-DFS
(1,354-1,362) ayrışan tek iki kol, yani Faz 1'i gerçekten değiştiren kollar.

## 85. Aynı hatanın dördüncü yüzü ve onu ayırt eden deney

n=50'ye çıkınca V4 iki satırda kesildi. İkisi ayrı şeydi ve ayırmak, ikisini de
"V4 ölçekte bozuluyor" diye toplamaktan daha çok iş yaptı.

**n50_m200 s4 V4'ün kusuru değil.** Tek parça, elli düğümün hepsi, seviye 2,
omurga referansla birebir aynı, ve düğümler çoktan sonraki fazlara geçmiş
(faz dağılımı {6:19, 4:27, 3:3, 2:1}). GHS temiz bitmiş; kesilme bütün kolların
paylaştığı örtme/sahiplik fazında. Beş kat bütçeyle de değişmiyor.

**n50_m100 s5 gerçek bir GHS kilidi** ve sebebi bu oturumda dördüncü kez çıkan
aynı sınıf. Düğüm 4 seviye 2'de, düğüm 28'e sorduğu TEST cevapsız; düğüm 28
seviye 1'de olduğu için erteliyor. `_ghs_pending_unknown` ertelenmiş TEST'i hâlâ
engel sayıyordu, dolayısıyla 28 rapor veremiyordu. Ama o TEST ancak 28'in
parçası seviye atlayınca cevaplanabilir, parça ise ancak 28'in raporu köke
ulaşınca yükselebilir.

**Ayırt edici deney, tahmin değil.** Kilidi yavaşlıktan ayırmanın ucuz ve kesin
yolu bütçeyi beşe katlamaktı: 8.000k ile 40.000k arasında sonuç birebir aynı
kaldı, altı parça, aynı kesilme. Bir kilit süreyle ölçeklenmez; bir yavaşlık
ölçeklenir. Bu tek ölçüm, "belki biraz daha süre verirsek" tartışmasını
tamamen kapattı.

**Engelin kaldırılmasının gerekçesi, çünkü oraya ters bir korkuyla konmuştu.**
Bu engel, bir parçanın "belirleyemedim"den "dışa giden kenar yok" sonucunu
çıkarmasını durdurmak için eklenmişti. Oysa bir düğüm ertelenmiş bir TEST
tutarken INF bildiremez: o TEST farklı bir parçadan geldiğine göre kenar
REJECTED değildir, dolayısıyla hâlâ BASIC'tir, ve `_ghs_test` aramayı bitirmeden
önce bütün BASIC kenarları ağırlık sırasıyla dener. Düğümün kendi araması o
kenarı, komşusuna cevap verip vermediğinden bağımsız olarak kapsıyor.

Böylece kural son hâlini aldı: **hiçbir ertelenmiş ileti engel değildir,
yalnız düğümün kendi cevapsız sorusu engeldir.** Ertelenmiş REPORT başkasının
erken cevabı, ertelenmiş CONNECT başkasının katılma isteği, ertelenmiş TEST
komşunun sorusu. TEST'i görmek en uzun süreni oldu çünkü belirsizliğe benziyor;
oysa gönderen zaten kendi `ghs_test_nid`'iyle doğru biçimde bekliyor.

Kendi yazdığım "ertelenmiş TEST engeller" gerileme testi bu yüzden düştü. Test
kodu değil, testin iddiası yanlıştı.

## 86. Dikiş sözleşmesi: paylaşılan makine Faz 1'in bitmediğini varsaymıyor

V4'ün n=50'de kalan son arızası GHS'de değildi ve bir önceki turda "paylaşılan
örtme fazı, V4'ün suçu değil" diye yazmıştım. Faz dağılımına bakınca yanlış
olduğu ortaya çıktı: `{6:19, 4:27, 3:3, **2:1**}`, yani bir düğüm hâlâ
PH_CONN'da, V4'ün kendi fazında.

**Ölçüm zinciri, tahmin değil.** Düğüm 16 faz 2'de takılı ve düğüm 30'u
bekliyor. Düğüm 30 omurgada, ama `claim=None` ve faz 4'te. İlk hipotezim
`_backbone_step`'in "komşu listesi boşsa rolleri bitir" yoluydu; kodu okuyunca
`_v4_finish_roles`'ın bunu zaten koruduğu görüldü (omurgadaysa ve karar
yoksa faz ilerletmeden döner), yani hipotez çürüdü. Faz yazmalarını izleyince
kesin olgu çıktı: faz **2'den doğrudan 4'e, tek yazmada** gidiyor, arada 3 yok.
`_v4_finish_roles` fazı 3 yaptığına göre yazan başka bir yerdi. Fazı 4'e yazan
tek yer `_on_join`.

```python
elif self.role == Role.OUT:
    self.role = Role.CONNECTOR if msg.code == JOIN_CONNECTOR else Role.COVER
    self.phase = max(self.phase, PH_FORCED)
```

Paylaşılan makine, rolü hâlâ `OUT` olan her düğümü JOIN daveti gelince doğrudan
PH_FORCED'a terfi ettiriyor. V2 ve V3 için zararsız, çünkü onların Faz 1'i rolü
erken atıyor. **V4 ise omurga MIS kararı verilene kadar rolü OUT bırakıyor**,
dolayısıyla bir JOIN düğümü kararını duyurmadan PH_CONN'dan koparıyor; o
duyuruyu yapacak olan `_backbone_step` ise yalnız PH_MIS ve PH_CONN'da
çağrılıyor. Komşu sonsuza kadar bekliyor, (15,16) kenarı açıkta kalıyor ve
arkasında 120 kenar sahipsiz duruyor.

**Ders: `_backbone_step` dikişinin yazılı olmayan bir ön koşulu varmış.**
Sözleşme "Faz 1'i istediğin gibi değiştir" diyor ama paylaşılan Faz 2/3
makinesi, bir düğümün rolünün PH_CONN'dan sonra kesinleştiğini sessizce
varsayıyor. Rolü geç atayan her varyant bu tuzağa düşer. Bu, bir arayüzün
belgelenmiş sözleşmesi ile gerçek sözleşmesi arasındaki farkın ölçülmüş bir
örneği.

Düzeltme paylaşılan koda değil V4'e kondu, çünkü kusur V4'ün geç rol atamasıyla
paylaşılan varsayımın birleşiminden doğuyor ve paylaşılan yolu değiştirmek
bütün kolları etkilerdi. JOIN ile terfi eden düğüm artık "MIS üyesi değilim"
duyurusu yapıyor: o JOIN onu zaten CONNECTOR yaptığına göre vardığı rol aynı,
komşular da beklemeyi bırakıyor.

Ölçüldü, n50_m200 s4 async: önce `truncated valid=False` (beş kat bütçe
değiştirmedi), sonra `solved valid=True` ve omurga doğru.

## 87. n=100: V4 kapanışı ve tel sınırının üçüncü kurbanı

Tavlama hariç on kol, n ∈ {50,100}, m/n ∈ {2,4}, k=6, üç tohum, 240 koşum,
tek kod sürümü. Denetim karnesi tamamen sıfır: yanlış başarı yok, kesik koşum
yok, kopuk girdi yok, ortak altküme **12/12**.

| kol | ratio_best_common | tx (ortak) |
|---|---|---|
| **V4-BB-MST/async** | **1,0117** | 5099 |
| **V4-BB-MST/sync** | **1,0245** | 7375 |
| V1-DFS/sync | 1,0909 | 66554 |
| V1-DFS/async | 1,0960 | 35138 |
| V2-BB-local (her iki kip) | 1,1170 | 2632 / 3190 |
| V3-BB-tree (her iki kip) | 1,1170 | 5439 / 7990 |
| V5 ve açgözlü tabanlar | 1,1170 | 2286-4122 |

**V4 ölçek büyüdükçe ayrışıyor.** Küçük grupta taban kollardan yaklaşık yüzde 8
iyiydi, n=100'de yüzde 9'a çıkıyor ve artık tek başına en iyi kol. V1-DFS ondan
kötü çözüm buluyor ve bunu **yedi ilâ on üç kat** iletiyle yapıyor. V3'ün ağaç
kipi ise V2 ile TAM AYNI çözümü buluyor, iletisi iki katı: Faz 5b bu ölçekte
maliyet getirip kalite getirmiyor.

**İlk koşum V3'te bir çökme yakaladı ve bu, §82'de adlandırdığım birinci
sınıfın üçüncü örneği.** `_STABLE_BODY` içindeki `weight_fp` işaretli 32 bitti,
ama taşıdığı şey tek düğümün değil **bütün alt ağacın** 16.16 sabit noktalı
toplam ağırlığı. n=100'de kökte yaklaşık 100 × 1000 × 65536, yani 6,5 milyar;
int32 tavanı 2,1 milyar. On iki örneğin üçünde istisna attı ve koşum hiç verdict
üretmedi. n ≤ 50'de sığdığı için bugüne kadar görünmedi.

Burada dikkat çekici olan, hatanın **gürültülü** olması. V4'ün parça kimliği
aynı sınıftandı ama sessizce kırpılıyordu ve haftalarca yanlış cevap
üretebilirdi; bu alan ise çöküyor. **Sessizce kırpan bir alan, atan bir alandan
tehlikelidir.** Alan 64 bite genişletildi; maliyet STABLE iletisinde dört bayt
ve yalnız ağaç kollarına düşüyor, dolayısıyla V3 ile V6-ANNEAL-tree'nin bayt
sayıları bu değişiklikten sonra ölçülmüş sayılmalı.

Böylece bu oturumda tel sınırı üç kez aynı biçimde bilgi sildi (parça kimliği,
sıralama anahtarı, alt ağaç ağırlığı) ve üçüncüsü başka bir kolun kusuruydu.
Bir protokolde karşılaştırılan ya da toplanan her değerin, **taşıdığı en büyük
değere** yetecek kadarının tele sığdığı ayrıca doğrulanmalı; alanın tek bir
düğüm için yeterli olması, toplam için yeterli olduğu anlamına gelmiyor.

## 88. İlk gerçek Mininet-WiFi koşumu: planlanan çizge ile görülen çizge aynı değil

V1 ve V4 için emülatör node kind'ı yazıldı ve ilk gerçek kablosuz koşum yapıldı.
Koşumun kendisi ilk denemede çalıştı, on istasyonun hepsi sessizliğe ulaştı.
Asıl bulgu sonrasında çıktı.

**Dört ayrı yerde aynı listenin kopyası vardı.** `node_main.NODE_KINDS` istasyonu
gerçekten başlatabilen tek kayıt; `run.py`'de argparse seçenekleri, `make_plan`
doğrulaması ve toplayıcının simülatör eşlemesi aynı listeyi elle tekrarlıyordu.
Üçü de `dfs` ile `mst`'yi reddetti, yani bir node kind kayıtlı olup launcher'dan
erişilemez durumdaydı. Üçü de kayda bağlandı. Bunların ikisi koşumdan ÖNCE,
biri koşum BİTTİKTEN sonra patladı; sonuncusu en pahalısı.

**Planlayıcının diski ile düğümün RSSI kapısı farklı şeyler.** Planlayıcı
`radio_range_m=100` varsayımıyla konum üretiyordu; `bootstrap.py` ise komşuluğu
`rssi_open_dbm = -75` ile açıyor. İlk koşumda geometrik denetim "25 kenarın
hepsi gerçeklendi, Jaccard 1,0" derken istasyonlar 25 kenarın **5'ini** gördü,
Jaccard 0,2. Kurulan beş bağlantı tam olarak en kısa beş kenardı, dolayısıyla
kesim mesafeseldi; ama menzili 30'a çekince keşif 0,89'a çıktı ve örtü
simülatörünkiyle birebir aynı oldu.

**Kapı keskin bir disk değil, bir bant.** Ölçümler: 34,2 m'de açıldı, 34,5'te
açılmadı; başka bir koşumda 31,1'de açıldı, 31,6'da açılmadı; üçüncü koşumda
29,9 m'nin altındaki altı kenar hiç açılmadı. Aynı konumlarda koşumdan koşuma
değişiyor. Bu kovalanacak bir hata değil, kaydedilecek bir olgu: simülatör birim
disk varsayar, emülatörde komşuluğu dalgalı bir kanal üzerindeki histerezisli
bir RSSI kapısı belirler.

**Bunun doğrudan sonucu: tek bir geçerlilik biti iki soruyu birbirine karıştırır.**
Toplayıcı örtüyü PLANLANAN çizgeye göre yargılıyordu, dolayısıyla "telsiz planı
gerçekledi mi" ile "algoritma problemi çözdü mü" aynı bite sıkışıyordu. İki
koşum da plana göre INVALID okundu; **istasyonların gerçekten gördüğü çizgeye
göre ikisi de VALID.** Yalnız birincisini raporlamak, kanalın kusurunu
algoritmaya yazmak olurdu. `validation_vs_discovered` bu yüzden eklendi.

Simülatörle karşılaştırma (menzil 30, aynı örnek): örtü birebir aynı
[1,2,3,4,5,6,9,10], slot 41'e karşı 42, tx 690'a karşı 684. Yani **algoritma
gerçek kanalda simülatördeki gibi davranıyor**; ayrışan tek büyük sayı rx
(+%69), çünkü yayın çerçevesini menzildeki herkes alır ve bu sayı alıcıda
tutulur.

## 89. Bağımsız denetim: gerçek kanal, tabanda bir kusuru açığa çıkardı

On gerçek Mininet-WiFi koşumu (n=10, k=6, senkron, beş tohum × V4-MST ve
V2-BB-local). Toplayıcının `valid` bayrağına güvenmeden bütün kurallar ham
çıktıdan yeniden hesaplandı.

**Sert kuralların hepsi onunda da geçti:** açıkta kenar yok, kapasite aşımı yok,
sahipsiz kenar yok, sahiplik haritasında yabancı kenar yok, her sahip kenarın
ucu ve örtüde, `|C| >= ceil(m/k)` tutuyor, bildirilen örtü ağırlığı düğüm
ağırlıklarının toplamına eşit.

**İlk denetimimde ağırlıklar tutmamıştı ve hata bendeydi:** ağırlıkları düğüm
kimliği varsaymıştım. Gerçek ağırlıklarla 10/10 birebir. Bir denetimin ilk
çıktısı, denetlenen sistemi değil denetimi suçlayabilir.

**Değerler tutarlı ve simülatördeki örüntüyü tekrarlıyor.** V4 tohum başına
478-549 ileti ve 30-36 slot, V2 229-343 ileti ve 20-24 slot. Kalitede V4 önde
(22'ye karşı 28, 38'e karşı 45, 19'a karşı 23; iki tohumda berabere), maliyeti
yaklaşık iki katı. Gerçek kanalda ölçülen bu ödünleşim, olay simülatöründe
ölçülenle aynı yönde.

**Denetim gerçek bir kusur buldu ve taban kolundaydı.** Tohum 5'te telsiz
yeterince bağlantı düşürünce düğüm 9 sıfır komşuyla kaldı. V4-BB-MST onu örtüye
almadı ve geçerli kaldı; V2-BB-local aldı. Kenarsız bir düğüm hiçbir kenarı
örtmez, yalnız ağırlık ekler ve G[C]'yi ikiye böler, dolayısıyla kol kendi
örtüsünü geçersiz yaptı. Kanal artefaktı olmadığı simülatörde birebir üretilerek
gösterildi: altı düğümlü bağlı çizge artı tek kenarsız düğüm, V2 kenarsız
düğümü alıyor ve `disconnected` ihlali veriyor, V4 almıyor.

Düzeltme `_rule_mis` başına kondu ve **sözleşme içi hiçbir sonucu
değiştiremez**, çünkü bağlı bir çizgede kenarsız düğüm yoktur. Yalnız sözleşme
dışı bir girdinin kendi kendine yara açmasını engelliyor.

**Bu kusurun yalnız gerçek kanalda görünmesinin sebebi kayda değer.** Veri
kümesindeki her örnek bağlı, dolayısıyla simülatör süpürmelerinin hiçbiri
kenarsız düğüm üretmiyor. Emülatörde bağlantı kaybı, planlanan topolojide bağlı
olan bir düğümü izole edebiliyor. Gerçek kanal burada yeni bir hata yaratmadı,
var olan bir hatayı **tetikleyebilen girdiyi** üretti.

## 90. Ödenmeyen indirim: tavlamanın bütün geçersizlikleri tek bir satıra indi

Tavlama tabanı ölçekte `solved` deyip kopuk örtü veriyordu, koşumlar bütçeyi
dolduruyordu ve bileşen etiketleri hiç yakınsamıyordu. İki oturum boyunca
etiket mekanizması onarılmaya çalışıldı. **Etiketler sebep değil, semptomdu.**

**Kök sebep.** `_delta_e`'de köprü indirimi yalnız KATILMA dalında vardı:

    0 -> 1:  d -= lam_b * (len(labels) - 1)      # indirim veriliyor
    1 -> 0:  (hicbir sey)                        # geri odenmiyor

Kodun kendi yorumu bunu ".tex diyor ki kesim düğümü kendi kesim düğümü olduğunu
bilemez" diye gerekçelendiriyordu. O cümle doğru, ama ondan çıkarılan sonuç
yanlıştı: bilinemezlik "hiçbir şey tahsil etme" demek değil.

Sonuç, tanımsız bir enerji fonksiyonuydu. Düğüm örtüye giriyor ve indirimi
alıyor, çıkarken bedel ödemiyor, tekrar giriyor ve indirimi tekrar alıyor.
**Hiç geri ödenmeyen bir indirim, sonsuz bir enerji kaynağıdır.**

**Ölçüm, tahmin değil.** Aynı anda aynı komşu durumunda iki dal da hesaplandı;
tutarlı bir fonksiyonda gir-çık toplamı sıfır olmak zorundadır:

| farklı etiket | ölçülen toplam |
|---|---|
| 2 | -2400 |
| 3 | -4800 |
| 4 | -7200 |

Sapma birebir `lam_b * (etiket - 1)` ve bütün kapasite terimleri sıfırdı, yani
kapasitede aranacak bir şey yoktu. Bir düğüm 12.493 kez çevrilmişti.

**Düzeltme.** Düğüm aldığı indirimi ÇEVİRME ANINDA yazar (`_bridge_credit`) ve
çıkarken geri öder. Anında yazmak zorunlu, çünkü köprü kurulunca komşuların
etiketleri birleşir ve borcun kanıtı ortadan kalkar; sonradan hesaplanamaz.

**Ölçülen sonuç** (n50_m100 ve n25_m50, üç tohum, iki çizelgeleyici):

| ölçüt | önce | sonra |
|---|---|---|
| en çok çevirme | 12.493 | 5-15 |
| donan düğüm | 47-49/50 | 50/50 |
| periyot | 39.994 | 92 |
| farklı etiket | 11-26 | 1 |
| bileşen | 2 | 1 |
| sonuç | truncated/geçersiz | 10/10 solved + geçerli |

**Zincir buydu:** ödenmeyen indirim -> salınım -> düğüm donmuyor -> bütçe
tükeniyor -> sahiplik yarım kalıyor; ve salınan düğüm örtüyü sürekli
değiştirdiği için etiketler oturmuyor -> köprü onarımı gürültüye ateşliyor ->
kopuk örtü. Tek bir satır, altı ayrı belirti.

**Yöntem dersi.** Bu oturumda üç hipotez kuruldu ve üçü de ölçümle çürüdü:
etiketi sessizlik sayacına sokmak (ölçüldü, KÖTÜLEŞTİRDİ ve geri alındı),
bayatlama penceresini genişletmek (2/6 -> 3/6, çözmedi), süre yetmemesi
(40.000 periyot ölçüldü, yetiyordu). Dördüncüde tahmin bırakılıp enerji
fonksiyonunun kendi tutarlılığı sınandı ve sebep bir hamlede çıktı. **Bir
semptomu onarmaya çalışmadan önce, sistemin kendi tanımının tutarlı olup
olmadığı sınanmalı.**

## 91. Dikiş, kanalda değil günlüktedir: yeniden kullanılan koşum dizini

Dagdeviren örneklerinin ilk kablosuz turunda tohum 2, üç kolda birden
"geçersiz" göründü ve `dag_mst_n10_m20_s2` koşumunda sahiplik haritasında
keşfedilen çizgede bulunmayan iki kenar çıktı, (5,9) ile (7,9). İlk açıklama
denemem RSSI kapısının bir bant olmasıydı: sınırdaki bağlantı açılıp kapanır,
sahiplik monotondur, dolayısıyla koşum artık var olmayan bir kenarı sahiplenmiş
bitebilir. Anlatı tutarlıydı ama **yanlıştı** ve ölçüm onu düşürdü.

Belirleyici ölçüm, bant hipotezini çürüterek başladı. Bantta (26-38 m) en çok
düğüm çifti tohum 3'teydi (32 çift), oysa kararsız olan tohum 2'ydi (24 çift).
Geometri de açıklamadı: tohum 3 geometrik olarak en seyrek komşuluğu
öngörürken (19 kenar) en çok kenarı keşfeden ve üç kolda da birebir aynı
sonucu veren tohum oydu.

Sonra RSSI zaman serisine bakıldı. Her yönlü çiftin RSSI'si **sabitti ve tam
iki değer** alıyordu, aralarında +4/+5 dB'lik tek bir basamak vardı; üstelik
doksan çiftin hepsi aynı anda sıçrıyordu. Sönümleme böyle davranmaz. Basamağın
yeri bulundu: `t_ms` 8056'dan 4'e **geri düşüyordu**. Dosyada iki `run_start`
kaydı vardı, 203 saniye arayla ve farklı pid'lerle.

Kök neden `JsonlLog`'un dosyayı `"a"` kipinde açması ve toplayıcının bölümleme
yapmamasıdır. Koşum dizini yeniden kullanıldığında ikinci yürütme birincinin
üstüne eklenir. İki yürütme de saatini sıfırdan başlattığı için toplayıcının
`recs.sort(key=t_ms)` satırı onları **iç içe geçirir**: eski koşumun bir rx
kaydı yeni koşumun iki tick'i arasına düşer. Komşuluk, sahiplik, slot ve RSSI
dahil aşağı akıştaki her nicelik, hiç var olmamış bir çizge üzerinden
hesaplanır.

Teşhisi tek başına doğrulayan gözlem şudur: dokuz koşumun altısında kayıtların
kabaca yarısı eski yürütmeye aitti, hiç eski kaydı olmayan tek tohum tohum
3'tü, ve zaten üç kolda da kusursuz tutarlı olan tek tohum oydu.

Düzeltme iki yerdedir. `split_last_execution` dosya sırasındaki son
`run_start`'tan öncesini atar ve kaçının atıldığını `health.stale_records`
alanında görünür kılar; sıralama artık ancak bu kesimden sonra yapılır.
`write_plan` ise planı yazarken dizinde kalmış `<nid>.jsonl` dosyalarını siler,
böylece dikiş sonradan onarılacağına hiç oluşmaz.

Düzeltilmiş toplayıcıyla yeniden türetildiğinde tohum 2'de üç kol da aynı
çizgeyi görür (27 kenar), iki yabancı kenar kaybolur ve `bbcvc` kolunun
keşfettiği kenar sayısı 10'dan 27'ye çıkar. Ayrıca eski toplayıcının
gizlediği bir gerçek açığa çıkar: `dag_mst_n10_m20_s1`'in ikinci yürütmesi on
düğümün dokuzunda yarıda kesilmişti, `done` kayıtları birinci yürütmeden
geliyordu, yani o koşumun "yakınsadı, 26 slot" özeti bir ölçüm değil iki
koşumun birleşimiydi.

Yöntem dersi §90'dakinin eşidir ve ondan farklı bir yeri gösterir. §90'da
sistemin kendi tanımının tutarlılığı sınanmıştı; burada sınanması gereken
**kanıtın kendisiydi**. Bir anomali için makul bir fiziksel hikâye
kurulabiliyor olması, o hikâyenin doğru olduğunu göstermez; ölçüm aygıtının
gördüğünü gerçekten o koşumda görüp görmediği önce sorulur.

## 92. Bayta sığmayan RSSI: tek bir okuma bütün ağın canlılığını düşürüyor

n=15, m=90 ölçeğine çıkıldığında GHS-MST-Backbone ile Anneal-Local üç tohumun
ikisinde **hiçbir örtü döndürmedi**; 240 saniye koştular, otuz bin ileti
gönderdiler ve boş sonuçla kesildiler. MIS-Connector-Backbone aynı örnekte 24
saniyede bitirdi. İlk okuma "zaman aşımı" derdi, değildi: `mst` günlüğünde
**2205 kez `reset_phase0`** vardı.

Sebep zincirine inerken iki hipotez ölçümle düştü. Birincisi "komşuluk
çalkalanıyor" idi; sıfırlamaların sebep alanı bakıldığında çoğunun
`bidir_changed` değil `epoch_adopt` olduğu görüldü, yani yalnız iki düğüm
komşuluk değiştiriyor ve geri kalan her şey onların tetiklediği ağ çapında
çığdı. İkincisi "sınırdaki bir bağlantı RSSI bandında oynuyor" idi; şüpheli
komşunun 31,1 m'deki RSSI'si ölçüldüğünde 2054 örnekte sabit −73 dBm çıktı,
açma eşiğinin belirgin biçimde üstünde.

Kaynak başına dağılıma bakılınca görüldü. Düğüm 5'in on üç komşusunun her biri
**tek bir sabit** RSSI veriyordu; düğüm 9 ise −128'den +127'ye, işaretli bir
baytın bütün aralığına yayılan 128 ayrı değer veriyordu. Bir telsiz gönderdiği
güçten fazlasını alamaz, dolayısıyla pozitif dBm bir ölçüm değil, sarmalanmış
bir bayttır.

Nedeni gömmenin geometrisidir. Planlayıcının yerleşimi düğüm 5 ile 9'u
**0,036 m** mesafeye koymuştu. Metre altı mesafede yol kaybı, okumanın bayta
sığmayacağı kadar küçülmektedir. Kural ölçümle tam olarak ayrıştı: bozuk RSSI
üreten çiftler **sıfırdan büyük ama bir metreden küçük** mesafedeki çiftlerdir;
tohum 1'de (5,9) 0,036 m, tohum 3'te (5,8) 0,06 m ve (2,15) 0,117 m. Mesafesi
TAM sıfır olan çiftler ((8,11) ve (8,14)) hiç bozuk okuma üretmemektedir.

Zarar zinciri şöyledir. Sarmalanmış değer rastgele −85'in altına düştüğünde
histerezis kapısı bağlantıyı kapatmakta, −75'in üstüne çıktığında yeniden
açmaktadır, dolayısıyla bağlantı kabaca 1,2 saniyede bir çevrilmektedir. Her
çevrim düğümün çift yönlü komşu kümesini değiştirmekte, bu da §3.5 madde 6
gereği epoch'u artırıp **bütün ağı evre 0'a döndürmektedir**. 240 saniyede 148
yerel çevrim 2057 ağ çapında sıfırlamaya dönüşmektedir. MIS-Connector-Backbone
ayakta kalmaktadır çünkü evre 1'i kısadır ve iki sıfırlama arasına
sığmaktadır; GHS ile tavlama ise kesintisiz uzun bir pencereye ihtiyaç duyduğu
için hiç bitememektedir.

Sayılar bağıntıyı tek başına kurmaktadır: imkânsız RSSI örneği sıfır olan üç
koşumda sıfırlama sayısı da sıfırdır ve üç kol da temiz sonuç vermektedir; iki
binin üzerinde imkânsız örnek olan koşumların hiçbiri yakınsamamaktadır.

Düzeltme sözleşmenin var olan kuralını genişletmektedir. Kod zaten "RSSI
vermeyen platform: kapı hep açık" demektedir, çünkü ölçüm yoksa kapı
yönetemez; imkânsız bir okuma da bir ölçüm değildir. `rssi_impossible_dbm`
eşiğini aşan tek bir örnek o komşunun RSSI kanalını kalıcı olarak güvenilmez
işaretlemekte ve bağlantı bundan sonra yalnız tazelik ile yönetilmektedir.
Yalnız pozitif örnekleri atmak YETMEZ: sarmalanmış değerlerin negatif yarısı
gerçekten zayıf bir sinyalden ayırt edilemez ve kapıyı yine çöp veriyle
kapatırdı. Sayaç `health.rssi_implausible` olarak rapora çıkmakta, planlayıcı
da `closest_pair_m` ile en yakın çifti basmaktadır, böylece koşum harcanmadan
önce koşul görünür olmaktadır.

Yöntem dersi §91'i tamamlamaktadır. Orada kanıtın hangi koşuma ait olduğu
sorulmuştu; burada sorulması gereken, bir ölçümün **fiziksel olarak mümkün
olup olmadığıdır**. Sistem +127 dBm'i sorgusuzca kabul edip onu zayıf sinyal
muamelesi gören −128 ile aynı kapıdan geçirmekteydi.

## 93. Geri sarılmayan saat: yeniden başlayan ağ, başlamayan tavlama

`dag_anneal_n15_m90_s3` ile `dag_anneal_n20_m160_s2` koşumları `converged`
bildirip **boş örtü** döndürmüştür: yirmi düğümün yirmisi de rol OUT, evre 7 ve
tam komşulukla (derece 17-19) bitmiştir. Doğrulayıcı ikisini de geçersiz
saymaktadır, yani kapı çalışmaktadır, ancak koşum işe yarar hiçbir şey
üretmemektedir.

Kodun statik okunması çelişki vermektedir. Bütün düğümler örtü dışındayken bir
düğümün katılması, kapasite cezası da hesaba katıldığında n=20 ve k=12 için
yaklaşık $-22{.}560$ enerji farkı taşımaktadır, yani katılmak ezici biçimde
çekicidir; üstelik `pending` bayrağı "token'ı kaybettiğim için yapamadığım
inişli adım" durumunu da sükûnet sayacına saydırmamaktadır. Dolayısıyla hiçbir
düğümün donmaması gerekirdi.

Belirleyici ölçüm zamandadır. Tavlamanın `t_min_temp`'e soğuması **92 periyot**
almakta ve `_maybe_freeze` sıcaklık bu eşiğin üstündeyken erken dönmektedir.
Oysa her iki koşumda da SON `reset_phase0` ile ilk `quiet` arasında yalnız 36
ve 29 periyot geçmiştir. Bu kadar erken donmak tek bir durumda mümkündür:
sıfırlama `periods` sayacını geri sarmamaktadır.

Kök neden budur. Epoch artışı §3.5 madde 6 gereği "herkes baştan koşar"
demektedir ve taban sınıf bunu yapmaktadır, yani evre, anahtar, derece ve
dondurulmuş komşuluk geri alınmaktadır. Tavlama durumu ise ayakta kalmaktadır
ve kararı veren tam olarak o durumdur. `periods` sıcaklığı sürdüğünden, zaten
soğumuş bir düğüm yeniden başlatmanın ardından da soğuk kalmakta; `frozen`
bayrağı ise `on_period`'u baştan kısa devre ettiğinden, bir kez donmuş düğüm bir
daha hiç tavlanmamaktadır. Yeniden başlatmadan sonra herkesin $x$ değeri sıfır
olduğundan sonuç boş örtüdür.

Düzeltme, `_reset_to_phase0`'ı tavlama düğümünde ezip `periods`, `frozen`,
`frozen_ms`, sükûnet sayacı ve köprü kredisini geri almaktadır. Köprü kredisi de
listeye girmektedir, çünkü o, yeniden başlatmanın az önce attığı bir komşuluğa
karşı kaydedilmiş bir borçtur.

Kusurun neden yalnız gerçek kanalda göründüğü ölçülerek gösterilmiştir. Aynı iki
örnek olay simülatöründe üçer tohumla koşulduğunda altı koşumun altısı da
`solved` ve geçerli, dolu örtü vermektedir; simülatörde RSSI kapısı
çalkalanmadığından epoch sıfırlaması hiç tetiklenmemekte, dolayısıyla geri
sarılmayan saat de hiç görünmemektedir.

Bu, oturumun aynı biçimli üçüncü kusurudur ve üçü birlikte bir sınıf
tanımlamaktadır: **yarım kalan geri alma**. §90'da katılırken verilen indirim
ayrılırken geri alınmamakta, §92'de ölçüm olmayan bir okuma ölçüm gibi
yutulmakta, burada ise yeniden başlatma durumun yalnız bir katmanını geri
sarmaktadır. Üçünde de sistem kendi sözleşmesini söylemekte ama tümüyle
uygulamamaktadır.

## 94. Bir kez denenen el sıkışma: yirmi istasyonda bağlayıcı olan sabit

n=20 ve m=160'ta dokuz koşumun yalnız biri bağımsız denetimden geçiyordu ve ilk
bakışta suç algoritmalarda görünüyordu. Ölçüm başka yeri gösterdi.

Teşhise giden yol iki yanlış genellemeden geçti ve ikisini de az sayıda koşuma
bakmak üretti. Önce "komşu girişleri düşüyor ve geri geliyor" denildi; dört
koşuma bakılıp `nbr_expired` sıfır bulununca bu terk edilip "sebep düşme değil
eklenmedir" denildi; yirmi yedi koşumun tamamı sayıldığında ikisinin de eksik
olduğu görüldü. Doğru sayılar şunlardır: n=10'da dokuz koşumun dokuzunda
`nbr_expired` ve `link_gave_up` sıfırdır, n=15'te düşme 0 ile 2 arasında ve
tükenme yine sıfırdır, n=20'de ise düşme 0 ile 551, tükenme 0 ile 134 arasında
değişmektedir.

Belirleyici gözlem, n=20'de bazı koşumlarda **hiçbir giriş düşmeden** el
sıkışmanın tükenmesidir. `dag_anneal_n20_m160_s3` koşumunda `nbr_expired`
sıfırken 124, `dag_mst_n20_m160_s1` koşumunda ise sıfıra karşı 80 tükenme
sayılmıştır. Yani birincil olgu düşme değildir; unicast LINK ile ACK'in yoğun
ortamda geçememesidir. El sıkışma giriş başına BİR KEZ denenir ve
`link_max_attempts` tükenirse o giriş için bir daha denenmez, çünkü kural
sonsuz unicast selini önlemek için konmuştur. Bedeli, komşunun kalıcı olarak
tek yönlü kalması ve o kenarın hiç oluşmamasıdır. Keşfin koşum boyunca
doymaması bunun SONUCUDUR, sebebi değildir.

Sınama doğrudan yapıldı. `link_max_attempts` üçten sekize çıkarıldı, başka
hiçbir şey değiştirilmedi ve aynı dokuz hücre yeniden koşuldu. Dokuz koşumun
dokuzunda da `link_gave_up`, `nbr_expired` ve `reset_phase0` **sıfır** çıktı,
keşif 185-188 kenarla tamamlandı ve GHS kullanmayan altı koşumun altısı da
bağımsız denetimden geçti: MIS-Connector 59-72 slot ve 2385-3018 ileti,
Anneal-Local 145-153 slot. GHS-MST üç koşumda da hiçbir şey döndürmedi, ki bu
teşhisi ayrıca doğrulamaktadır, çünkü onun sınırı el sıkışma değil kendi tur
karmaşıklığıdır.

Düzeltme `link_max_attempts`'i planlayıcıda beklenen komşuluk büyüklüğüne
bağlamaktadır. Denemenin bir TAVAN olması, sayaç olmaması bunu ucuz kılar: ilk
denemede ACK gelen bir komşuluk fazladan hiçbir şey harcamaz, dolayısıyla tavanı
büyütmek üç denemenin zaten yettiği n=10 ve n=15'te ölçülebilir hiçbir değişiklik
yaratmaz ve orada kural üçü korur.

Ders §91 ve §92'nin yanına yazılır ve onlardan farklı bir yeri gösterir.
Orada kanıtın hangi koşuma ait olduğu ve bir okumanın fiziksel olarak mümkün
olup olmadığı sorulmuştu; burada sorulması gereken, **bir sabitin hangi rejimde
seçildiğiydi**. Üç deneme seyrek bir komşuluk için seçilmiş makul bir sayıdır ve
yoğun bir komşulukta sessizce bağlayıcı hâle gelmektedir; sabit yanlış değil,
kapsamı beyan edilmemiş olarak yanlıştır.

## 95. Cevapsız kalan soru: GHS'in üç ayrı kilidi

§94'ten sonra n=20'de geriye yalnız GHS-MST'nin üç koşumu kalmıştı ve bunu
"GHS'in kendi tur karmaşıklığı bütçeye sığmıyor" diye yazmıştım. **Yanlıştı** ve
yanlışlığını ilk gösteren ileti sayısı oldu: 32.086 iletinin 30.192'si HELLO
idi, yani GHS'in kendi trafiği n=15'tekiyle aynı mertebedeydi. Trafik,
algoritmanın konuşkanlığı değil koşumun bitmemesiydi. §89'da öğrenilen ders
burada ikinci kez uygulanmayı bekliyordu.

Simülatörde birebir üretildi. İstasyonların gerçekten gördüğü çizge alınıp olay
simülatöründe koşulduğunda GHS %0 kayıpta üç tohumu da 81 slot civarında
çözmekte, **%2 kayıpta üçü de boş örtüyle kesilmektedir**. Kusur ölçekte değil
kayıptaydı.

Üç ayrı kilit bulundu.

**Birincisi, yeniden gönderim yokluğu.** `_ghs_send` doğrudan unicast'tir;
LINK el sıkışmasının `awaiting_ack` ve yeniden deneme mekanizması GHS
iletilerinde yoktur, oysa protokolün ilerlemesi her sorunun eninde sonunda
cevaplanmasına bağlıdır. Düşen tek bir TEST göndereni `ghs_test_nid` üzerinde
süresiz kilitler, düşen tek bir REPORT ise ebeveyni zaten cevaplamış bir çocuğu
saymaya devam ettirir. Hiçbir yerde hata oluşmaz, koşum yalnızca durur.
`_ghs_reassert` cevapsız soruyu süreli olarak yeniden sormaktadır ve **yalnız
tekrarı işlemsiz olan sorular** tekrarlanır: TEST aynı ACCEPT ya da REJECT'i
üretir, REPORT ise artık sayaç yerine kümede tutulmaktadır. CONNECT'in alıcısı
da aynı kenar üzerinde ikinci kez birleşmeyecek, yalnız INITIATE'i yineleyecek
biçimde idempotent kılınmıştır.

**İkincisi, cevaplanamayan sorunun ertelenecek yerde düşürülmesi.** Dosya bu
kuralı uyuyan düğüm için zaten yazmaktadır: "DEFER, never drop; 'henüz
cevaplayamam' ile 'cevap yok' aynı şey değildir." `_on_algo` girişi ise bir
katman dışarıda tam bunu yapmakta, kenar o an inikken gelen soruyu sessizce
atmaktaydı. Ölçüldü: düğüm 16, düğüm 9'un 339 TEST'inin **311'ini** orada
düşürmüş, yalnız 28'ini cevaplamıştır.

**Üçüncüsü, kalıcı el sıkışma başarısızlığı.** `link_failed` için belgelenen
toparlanma yolu girişin soft-state ile düşüp yeniden açılmasıdır, ancak giriş
yalnız komşu susunca düşer; HELLO göndermeye devam eden bir komşu girişi taze
tuttuğundan `link_failed` hiç temizlenmez. Sonuç asimetrik bir kenardır: düğüm
9 kenarı açık görürken düğüm 16 aynı kenarı kapalı görmekte, dolayısıyla soruyu
cevaplayamamaktadır. Kurtarma yolunu tam da komşunun canlı olması
kapatmaktadır. Düzeltme, kalıcı başarısızlık yerine bekleme süreli yeniden
denemedir; tek-seferlik kuralın amacı olan unicast seli korunmakta, giriş
başına tur oranı `link_retry_after_periods` ile sınırlı kalmaktadır.

Ölçülen etki: GHS-MST %2 kayıpta boş örtüden 92 slotluk çözüme, %5 kayıpta ise
boş örtüden geçerli 19 düğümlük örtüye geçmektedir.

Bir ölçüm de geçersiz sayılmıştır. El sıkışma tavanının etkisi önce dataclass
SINIF ÖZNİTELİĞİ değiştirilerek sınanmış, oysa dataclass varsayılanı sınıf
oluşumunda dondurulduğundan değişiklik hiçbir örneği etkilememiştir; o turdaki
"tavan sebep değil" sonucu dayanaksızdır ve kayıttan düşülmüştür.

Yöntem dersi §89'un tekrarıdır ve tekrar edilmesi gerektiği için buradadır:
**tek bir `tx` sayısı bir kolu konuşkan sanmaya yol açar.** Otuz iki bin ileti
burada bir maliyet değil, bir belirtiydi.

## 96. Tam sınırda susan kapı: derece açığı tanığı

n50_m300 hücresi oturumlar boyunca "bazı tohumlarda bütün kollar çözümsüz
kalıyor, gerçekten imkânsız mı bilinmiyor" diye açık kalmıştı. Kapatıldı ve
sonuç **kısmi imkânsızlıktır**: on tohumun sekizi çözülebilir, ikisi
kanıtlanabilir biçimde çözümsüzdür.

Hücrenin özelliği `m = n*k = 300` olmasıdır, yani sayma sınırı EŞİTLİKLE
sağlanır. Bunun üç zorunlu sonucu vardır. Birincisi `|C| >= ceil(m/k) = 50 = n`
olduğundan örtü zorunlu olarak V'nin tamamıdır ve her düğüm tam olarak altı
kenar sahiplenmek zorundadır. İkincisi C = V her kenarı örttüğünden ve veri
kümesindeki her örnek bağlı olduğundan örtü ile bağlılık bu hücrede engel
olamaz. Geriye tek soru kalır: indegree'si k'yı aşmayan bir yönlendirme var
mıdır. Bu bir akış sorusudur ve Hakimi yönlendirme teoremiyle karara bağlanır.

Karar iki bağımsız çözücüyle verildi ve on tohumun onunda da birebir uyuştular.
Çözülebilir tohumlarda kanıt bir çözücünün "evet"i değil AÇIK (örtü, sahiplik)
çiftidir ve `validate.validate` sıfır ihlalle geçmektedir; her düğümün yükü tam
altıdır. Çözümsüz tohumlarda tanık min-kesitten okunmuş, sonra çözücüye
güvenilmeden düz kenar sayımıyla yeniden doğrulanmıştır.

Tanığın okunaklı hâli şudur: bir sahip, sahiplendiği kenarın UCU olmak
zorundadır, dolayısıyla bir düğüm en çok `min(deg(v), k)` kenar sahiplenebilir
ve toplam sahiplenilebilir kapasite `sum(min(deg(v), k))`'dir. Tohum 6'da iki
düğümün derecesi beş, tohum 8'de bir düğümün derecesi dörttür, dolayısıyla
kapasite iki tohumda da **298 < 300** çıkmaktadır. Derecesi k'nın altında kalan
bir düğüm kendi kotasını dolduramaz ve sınır tam eşitlikte olduğundan bu boşluğu
telafi edecek hiçbir bolluk yoktur.

Kusur bu değildi; kusur bunun RAPORLANMAYIŞIYDI. `counting_bound_infeasible`
yalnız `m > n*k`'ya bakmakta, burada eşitlik bulunduğundan kapı hiç
açılmamaktaydı. Sonuç olarak iki imkânsız örnek `infeasible` değil `unresolved`
etiketleniyordu, yani çözülebilir bir örnekte başarısız olmuş bir kol gibi
okunuyordu. Bu, "çözemedim" ile "çözümü yok"u ayırt etme sözleşmesinin sessizce
çiğnenmesidir.

Düzeltme `degree_deficiency_infeasible` tanığıdır. O(n) maliyetlidir, koşum
düzeyindedir ve sayma sınırını KESİN OLARAK kapsar, çünkü
`sum(min(deg, k)) <= n*k` her zaman doğrudur; dolayısıyla sayma sınırının
reddettiği her örneği o da reddeder ve ek olarak sınırın göremediği tam eşitlik
durumunu yakalar. Gerçek örneklerde doğrulandı: on tohumun sekizinde kapasite
tam 300, altı ve sekizinci tohumlarda 298 çıkmakta, yani tanık akış
çözücüsünün kararını birebir üretmektedir.

Kapsam uyarısı sayma sınırınınkiyle aynıdır ve aynı sebeple yazılmıştır: derece
dizisi küresel bir niceliktir, hiçbir düğüm onu göremez (api I1). Bu bir KOŞUM
düzeyi denetimidir ve yerel bir yükleme dönüştürülmemelidir.

## 97. Dördüncü kilit: mandalın hayatta kalması

%10 kayıpta GHS'in hâlâ boş örtü döndürmesi açık kalmıştı ve ilk teşhisim
"durma kararı ağaçta yayılmıyor" olmuştu, çünkü ölçtüğüm son durumda yirmi
düğümün yalnız ikisinde `ghs_halted` vardı. **Bu hipotez ölçümle çürütüldü** ve
çürüten şey aynı koşumdaki ikinci bir alandır: `_v4_done_seen` yirmi düğümün
HEPSİNDE doğrudur, yani duyuru zaten herkese ulaşmıştır. §95a tarzı bir yeniden
gönderim hiçbir şeyi değiştirmezdi, çünkü tekrar aynı mandala çarpardı.

Gerçek sebep şudur: `ghs_halted` ve `_v4_done_seen` birer MANDALDIR. Birincisi
`_ghs_halt`'ı, ikincisi `_on_v4_done`'ı bir daha hiç çalışmayacak hâle getirir
ve bu ikisi bir düğümün PH_MIS'ten çıkmasının tek iki yoludur. Taban sınıfın
`_reset_to_phase0`'ı evreyi, anahtarı, dereceyi, dondurulmuş komşuluğu ve rolü
geri sarar, `_init_algo_state` de Faz 2-5'i geri sarar, ancak GHS durumunu hiç
tanımaz ve o durum mandallarıyla birlikte olduğu gibi hayatta kalır. Sonuç:
Faz 1'i bir kez bitirmiş bir düğüm, sonraki hiçbir epoch'ta bir daha
bitiremez.

Ölçüm zaman çizelgesiyle nettir. Faz 1 t = 11,6-12,0 s arasında kusursuz
tamamlanmakta, çekirdek çifti halt etmekte, `v4_phase1_done` yirmi düğümün
yirmisinde görünmekte ve t = 12,8 s'ye kadar on sekiz `cover` kaydı
düşmektedir. t = 13,4 s'de bir düğüm epoch'u artırır, herkes sıfırlanır, ve
onu izleyen sekiz epoch boyunca bütçe dolana dek **tek bir** `ghs_halt`,
`v4_phase1_done` ya da `cover` kaydı daha yoktur. Koşum boş örtüyle biter.

Düzeltme `_reset_to_phase0`'ın GHS düğümünde ezilmesidir ve §93'teki tavlama
emsalinin birebir aynısıdır. Korunanlar gerekçesiyle yazılmıştır: `ghs_peer_deg`
HELLO'dan DUYULMUŞ komşu bilgisidir, `self.nbrs` ile aynı sınıftandır ve taban
sıfırlaması onu da korur; üç sayaç ise koşumun tamamının ölçümüdür ve hiçbir
karara girmez.

Bağımsız olarak doğrulandı: %0 ve %2'de çözüm sürüyor, %5 kesikten ÇÖZÜME
geçiyor, %10'da üç tohumun üçünde de boş örtü yerine geçerli on dokuz düğümlük
örtü çıkıyor. %10'da kalan `truncated` artık GHS değildir; Faz 1 o koşumda üç
ayrı kez baştan tamamlanmakta, sonda yirmi düğümün on yedisi PH_DONE olmakta ve
eksik kalan yalnız paylaşılan yoldaki sessizlik tespitinin sürekli çalkantı
altındaki kuyruğudur. Bütçeyi üç katına çıkarmak sonucu değiştirmemektedir,
dolayısıyla bu yavaşlık değil ayrı kapsamda bir konudur.

**Sınıf sayımı bununla değişmektedir.** Oturumun sekiz kusurundan DÖRDÜ artık
yarım kalan geri alma sınıfındadır (§90, §92, §93, §97), biri kapsamı beyan
edilmemiş bir sabittir (§94), üçü cevapsız bırakılmış sorudur (§95a-c). Baskın
sınıf, sistemin bir şeyi geri aldığını söyleyip yalnız bir katmanını geri
sarmasıdır.

## 98. Bir kez duyurulan sonlanma ve onun açtığı yanlış başarı

`dag_anneal_n20_m160_s2` koşumu geçerli örtü bulmasına rağmen yakınsama
bildirmiyordu ve bunu tavlamanın bir kusuru sanmıştım. Değilmiş: tavlama normal
yakınsamış, yirmi istasyonun yirmisi de t≈23,5 s'de, yani kardeş tohumlarla
aynı slot sayısında donmuştu. Kilitlenen **Faz 5a sonlanma bariyeridir**.

Mekanizma §95a ile aynıdır. Bir düğüm PH_DONE'a geçerken **tek bir** olay
HELLO'su yayınlar ve ardından periyodik canlılık yayınını tamamen keser;
üstelik evre ≥ QUIET'teki her düğüm yumuşak durum süre aşımını da askıya
aldığından komşu girişi ne tazelenebilir ne düşebilir. Tek bir kayıp çerçeve
bütün ağın sonlanmasını kilitler ve toparlanma yolu yoktur. Kusur tavlamaya
özgü de değildir, üç kol da aynı `_quiescence`'ı miras alır.

Ölçüm nettir: 10, 13 ve 20 numaralı düğümler aynı slotta DONE olmuş, üçünün
phase-7 çerçevesi de aynı patlamada on dokuz alıcının hepsinde kaybolmuş ve
kalan on yedi istasyon onları sonsuza dek evre 5'te görmüştür. Koşumun 27.375
iletisinin 23.611'i yakınsama sonrası gevezeliktir, kardeş tohumlarda bu sayı
568 ve 483'tür. Çarpışma şans eseri de değildir: geçişteki `_touch()` ANINDA
yayın zorladığından aynı slotta biten düğümler kilitli adımda konuşur, oysa
olağan periyodik HELLO'lar zamana yayılmıştır; bitin tek taşıyıcısı tam da en
çok çarpışacağı anda gönderilmektedir.

Düzeltme `_barrier_closed`'dır: DONE düğüm, HER komşusu da PH_DONE'a ulaşana
kadar susmaz. Eşiğin PH_QUIET değil PH_DONE olması farkın tamamıdır, çünkü
benim DONE'ımı kaçıran komşu zaten PH_QUIET'te takılıdır ve QUIET'e bakan bir
sınama aynı kilidi bir üst seviyede kurardı. Maliyeti sınırlamak için bariyer
açıkken yayın yavaşlatılır, yani durgunluk penceresinde bir kez konuşulur; bu
çalışan örnekte ileti sayısını 482'den 570 yerine 507'ye çıkarır ve belgeye
göre 2,5 kat sınırının içinde kalır.

**Düzeltmenin açığa çıkardığı şey kaydedilmelidir.** Bariyer kapanınca daha
önce `truncated` biten bazı koşumlar `solved` bitmeye başladı ve içlerinden
geçersiz olanlar **yanlış başarıya** dönüştü, ki sözleşme açısından bu daha
kötüdür. Geçersizlik zaten oradaydı, verdict onu gizliyordu.

İki ayrı sebep ölçüldü. Birincisi **asimetrik kenardır**: %5 kayıpta kenar
(1,7) için düğüm 1 girişi `is_edge=False` ve `link_failed=True` tutar, düğüm 7
ise `is_edge=True`. Faz 2 açıktaki kenarı küçük anahtarlı uca verir; küçük
anahtar düğüm 1'indir (9.240.576'ya karşı 9.961.472), ama kenarın varlığından
haberi yoktur, düğüm 7 de beklediği için kenar açıkta kalır. Buna karşı
`_sees_uncovered_edge` konmuştur: OUT bir düğüm, OUT bir komşu görürken
sessizliğe geçemez. Bu asimetriyi onarmaz, yalnız düğümün kırıklığı görürken
"bitirdim" demesini engeller ve yanlış başarıyı dürüst bir çözümsüzlüğe
çevirir; ölçüldü, n10 vakası geçersizken geçerli hâle gelmiştir.

**Denenen ve geri alınan düzeltme.** `_sees_uncovered_edge`, yani OUT bir
düğümün OUT bir komşu görürken sessizliğe geçememesi, motive eden vakada
çalışmıştı: n=10 çizgesi %5 kayıpta `solved` + geçersizken `solved` + geçerli
hâle gelmişti. Yine de YANLIŞTIR ve gerekçesini bu dosyanın kendi sözleşmesi
vermektedir (`test_verdict_is_not_derived_from_validity`): `verdict` yalnızca
SONLANMA BİÇİMİDİR, dolayısıyla donmuş ama geçersiz bir koşum da `solved`
okumalı ve doğrulayıcı onu çürütebilmelidir. Bir satır ancak verdict `solved`
VE doğrulayıcı temizse kol sonucu sayılır. İkisini birbirine bağlamak,
SAPTANABİLİR bir yanlış başarıyı saptanamaz bir kesintiye çevirmekte, yani
ayrımın var olma sebebini ortadan kaldırmaktadır. Asimetrik kenar gerçektir ve
kırıldığı yerde onarılmalıdır, çıkışta gizlenmemelidir.

İkincisi **kapasite doygunluğudur** ve YEREL OLARAK SAPTANAMAZ. Kenar (12,15)
için iki uç da örtüdedir, birbirini simetrik görür ve ikisi de tam kapasitedir
(8 = k), dolayısıyla kimse kenarı alamaz ve her biri ötekinin sahiplendiğini
sanır. HELLO sahiplik kümesini değil yalnız yükü taşıdığından hiçbir düğüm bu
durumu kendi bilgisiyle ayırt edemez. Kodun sayma sınırı için zaten yazdığı
kapsam uyarısının aynısı buraya da geçerlidir. Düzeltilmemiştir; %5 kayıpta üç koşumda görülmüştür.

**Bunun gerçek kanal için ne anlama geldiği önce YANLIŞ yazıldı ve ölçümle
düzeltildi.** İlk hâli "gerçek kanalda ölçülen kayıp bu seviyenin altında
kaldığından 27/27 sonucunu etkilemez" diyordu; bu varsayımdı, ölçüm değildi.
Arşivlenmiş yirmi yedi koşumdan bağlantı başına HELLO teslim oranı sayıldığında
6108 (gönderen, alıcı) çifti için medyan 0,971 ve ortalama 0,968 çıkmaktadır,
yani ortalama kayıp yaklaşık %3'tür. Ancak dağılım ölçekle kayar: n=20
koşumlarında bağlantı başına teslim 0,944 ile 0,959 arasındadır, yani kayıp
**%4-6**, ve en kötü yüzdelik dilimde 0,903'e, yani %10'a inmektedir.

Gerçek kanal n=20'de tam olarak bu kusurun göründüğü rejimdedir. Dolayısıyla
27/27 sonucu, sorunun uzağında olunduğu için değil, o yirmi yedi koşumun bu
tuzağa denk gelmediği için elde edilmiştir. Pay değil, şanstır ve öyle
okunmalıdır.

## 99. Kayıpsız/kayıplı eşleştirilmiş deney ve epoch'unu aşan onay

Kayıp dayanıklılığı bu oturuma kadar tek tek vakalarla kovalanmıştı. Düzgün
kurulmuş bir deney istendi ve kuruldu: aynı dokuz çizge (istasyonların gerçekten
gördüğü topolojiler, n=10/15/20 ve üçer tohum), aynı üç kol, tek değişken kayıp.

Kayıplı koşulun seviyesi keyfî seçilmemiştir. Arşivlenmiş yirmi yedi koşumdan
bağlantı başına HELLO teslimi sayıldığında 6108 (gönderen, alıcı) çifti için
medyan 0,971 çıkmakta, ancak n=20 koşumlarında 0,944 ile 0,959 arasına
inmektedir, yani yirmi istasyonun yaşadığı rejim **%5 kayıptır**. Kayıp
rastgele olduğundan hücre başına beş RNG tohumu koşulmuştur; tek tohum bir
yazı-turayı bulgu diye raporlamak olurdu. Toplam 270 koşum.

**Kayıpsızda üç kol da kusursuzdur: 135 koşumun 135'i geçerli.** Fark tamamen
kayıplı koşulda ortaya çıkmaktadır ve kollar arasında eşit dağılmamaktadır.

| kol | kayıpsız | kayıplı | yanlış başarı |
|---|---|---|---|
| Anneal-Local | 45/45 | **45/45** | 0 |
| GHS-MST-Backbone | 45/45 | 40/45 | 0 |
| MIS-Connector-Backbone | 45/45 | 39/45 → **43/45** | 6 → **2** |

GHS'in beş başarısızlığı DÜRÜSTTÜR: hepsi `truncated` bildirir, yani koşum
bitiremediğini söyler. MIS-Connector'ın altı başarısızlığı ise `solved`
bildirip geçersiz sonuç vermekteydi ve bu en tehlikeli sınıftır, çünkü sessizce
doğru görünür.

Altısının da kökü tek bir yerdedir ve oraya varmadan iki hipotez ölçümle
düşmüştür. Birincisi "iki uç da kapasite dolu" idi; ölçüldüğünde çoğu vakada
BİR UÇTA YER olduğu görüldü, (2,19) için 7/12, (3,11) için 9/12, (1,16) için
11/12. İkincisi "epoch sıfırlaması anahtarları bayatlatıyor, ters-simetri
bozuluyor" idi; ölçüldüğünde iki ucun epoch, anahtar ve yük konusunda TAM
MUTABIK olduğu görüldü, dolayısıyla eşitlik dalındaki anahtar karşılaştırması
kusursuz çalışmaktaydı.

Gerçek sebep `late_ack_release`'tir. Bekleyen kaydı olmayan geç bir olumlu
yanıt geldiğinde düğüm kenarı yine de bırakır ve kodun gerekçesi tek bir epoch
içinde doğrudur: komşu kenarı aldığını AÇIKÇA söylemekte ve `_explicit` ile
tutmaktadır, dolayısıyla bırakmak kenarı sahipsiz bırakamaz. Ancak epoch
sıfırlaması devri İKİ TARAFTA DA iptal eder, çünkü `_init_algo_state` her
düğümde `_explicit`, `owned` ve `_pending`'i temizler. Sıfırlamayı aşan bir
onay, artık var olmayan bir devri onaylamaktadır. Kanıt üç vakada birebir
aynıdır: veren `_explicit[e] = False` tutarken alanda HİÇ KAYIT YOKTUR.

Düzeltme, geç onayın yalnız BU EPOCH'ta teklif edilmiş bir kenar için
onurlandırılmasıdır (`_offered`, `_init_algo_state` ile temizlenir). Etkisi
ölçülmüştür: yanlış başarı altıdan ikiye, geçerli koşum 39/45'ten 43/45'e
gitmekte, n=20'deki dört vakanın dördü de kapanmaktadır.

**Kalan iki vaka ve neden düzeltilmedikleri.** Biri §98'deki asimetrik
kenardır (n10 tohum 3): bir uç `link_failed` yüzünden kenarın varlığından hiç
haberdar değildir ve küçük anahtar tam da o uçtadır. Öteki kapasite
doygunluğudur (n15 tohum 2): iki uç da tam kapasitededir ve zincirleme PUSH
onarımı kayıp altında tamamlanamamıştır. İkisi de tanımlanmıştır, ikisi de
yerel bilgiyle saptanamaz ve ikisi de tahminle değil ölçülmüş bir tasarımla
kapatılmalıdır.

## 100. Yeniden-sorma: neyin tekrarı zararsızdır?

§99'un tablosunda GHS-MST kayıplıda 40/45 görünmekteydi, çünkü o ölçüm
yeniden-sorma açıkken alınmıştı. Sonra yeniden-sorma geri alındı ve arşivlenen
sayı 1/45'e düştü. Geri almanın gerekçesi de ölçülmüştü: yeniden-sorma açıkken
veri kümesi örneklerinden n10_m20 s1 ve n25_m50 s1, **hiç kayıp yokken** boş
örtü döndürmekteydi. Yani elde birbirini dışlayan iki ölçüm vardı ve hangisinin
feda edileceği sorusu açık kalmıştı.

Soru yanlış kurulmuştu. Yeniden-sorma tek bir anahtar değildir, üç ayrı sorunun
tekrarıdır ve üçü aynı şeyi yapmamaktadır. Bileşenler teker teker açılıp aynı
dokuz çizge ve beşer tohumla ölçüldüğünde tablo şöyle çıkmaktadır.

| tekrarlanan | kayıpsız (ham veri kümesi) | kayıplı (%5) |
|---|---|---|
| hiçbiri | 9/9 | 1/45 |
| TEST | 9/9 | 10/45 |
| TEST+CONNECT | 9/9 | 25/45 |
| TEST+CONNECT+REPORT | 7/9 | 40/45 |

Kurtarmanın büyük kısmını CONNECT ve REPORT taşımaktadır, oysa `_ghs_reassert`
belgesi yalnızca kayıp TEST'in kilitlemesini gerekçe göstermekteydi. Kayıpsızı
bozan bileşen ise tek başına REPORT'tur ve bu, yeniden-sormanın kendisinin değil
onun AÇIĞA ÇIKARDIĞI iki kusurun bedelidir. Bir soruyu tekrarlamak ancak
cevaplamanın iki kez zararsız olduğu durumda zararsızdır; ikisinde de değildi.

**Birincisi kök değişimidir.** Çekirdek raporu `_ghs_change_root`'a girmekte,
o da en iyi dış kenarı talep etmektedir. Rapor tekrarlandığında aynı karar bir
kez daha işlenmekte ve zaten kullanılmış kenardan ikinci bir CONNECT çıkmakta,
karşı taraf bunu taze bir birleşme sayıp yeni bir ebeveyn atamaktadır. n25_m50
s2'de sıfır kayıpta ölçüldüğünde 2, 25 ve 7 numaralı düğümlerin ebeveyn
işaretçileri üçlü bir çevrim kapatmakta, beş düğüm sonsuza dek FIND'de kalmakta
ve yirmi beş düğümün tamamı tek parçada dışarı kenarı kalmamış olmasına rağmen
koşum boş örtü döndürmekteydi. Kök değişimi artık tur başına bir kez
yapılmaktadır; hak `_ghs_initiate` ile, yani bir sonraki turun başında geri
verilmektedir, dolayısıyla kaybolan bir CONNECT yine kurtarılmaktadır çünkü
`ghs_connect_out` içinde durmaktadır.

**İkincisi raporun turudur.** REPORT üzerinde hangi tura ait olduğunu söyleyen
bir alan yoktu, oysa `_ghs_initiate` biriken `best` değerini silmektedir; önceki
seviye için yazılmış bir rapor, artık var olmayan bir soruyu yanıtlamaktadır.
n10_m20 s1'de sıfır kayıpta ölçüldüğünde düğüm 9, 76218369 raporlamış, sonra
seviye 2'ye yeniden başlatılıp INF bulmuş, ancak eski raporu FIND'deki düğüm
6'nın ertelenmiş kuyruğunda beklemiş ve sıfırlamadan SONRA işlenmişti. Düğüm 5
ile 6 olmayan bir dış kenarı sonsuza dek ellerinde tutmakta, çekirdek durma
sınaması hiç ateşlenmemekteydi. REPORT artık `level` alanında yazıldığı seviyeyi
taşımaktadır; çocuk her zaman raporlamadan önce başlatıldığından seviyesi
ebeveyninkini aşamaz, dolayısıyla daha düşük olan yapı gereği bayattır ve
düşürülmektedir.

İki kusur giderildikten sonra üç sorunun tamamı tekrarlanabilmektedir:
**kayıpsız 9/9 ve kayıplı 40/45.** Eşli deney bu kodla, ardından §102'nin
kuyruk tekilleştirmesiyle birlikte bir kez daha koşulmuş olup aşağıdaki tablo
sonuncusundan, yani bugünkü koddan gelmektedir.

| kol | kayıpsız | kayıplı (%5) | yanlış başarı |
|---|---|---|---|
| Anneal-Local | 45/45 | **45/45** | 0 |
| GHS-MST-Backbone | 45/45 | **41/45** | 0 |
| MIS-Connector-Backbone | 45/45 | 42/45 | 2 |

GHS'in kalan dört başarısızlığı `truncated` bildirmektedir, yani koşum
bitiremediğini söylemektedir; hiçbiri yanlış başarı değildir.

Yukarıdaki bileşen tablosu ile bu sonuç tablosu ARASINDA BİR KOD DEĞİŞİKLİĞİ
vardır ve kayda geçmesi gerekir. Bileşenler ölçülürken `_ghs_defer` birebir
aynı soruyu henüz düşürmemekteydi; §102'de anlatılan tekilleştirme sonradan
eklenmiş ve eşli deney son kodla yeniden koşulmuştur. Fark 270 satırın 5'inde
görülmekte, GHS kayıplıda 40/45'ten 41/45'e çıkmaktadır. Bileşen tablosunun dört
satırı ise kendi aralarında karşılaştırılabilsin diye tek bir kod durumunda
bırakılmıştır.

Aynı dokuz çizge ve beşer tohumla %10 kayıp da ölçülmüştür ve GHS orada 45/45
vermektedir. Bu bir eğilim değildir; kayıp arttıkça iyileşme beklenmez, aynı
tohumlar yalnızca farklı sıralanmakta ve %5'te kilitlenen dört koşum %10'da
kilitlenmemektedir. Dayanıklılık için alıntılanacak hücre düşük olanıdır. Maliyet tarafında
da bir sürpriz yoktur: n50_m100 örneği 0,6 saniyede ve 0,03 GB ile bitmektedir,
oysa yeniden-sormanın sınırsız ertelenmiş kuyrukla birlikte koştuğu sürümde aynı
örnek 115 saniyeyi aşıp 4,7 GB tutmaktaydı. Yığan taraf tekrar değil kuyruktu.

Bu oturumda ayrıca iki hipotez ölçümle düşmüştür. Birincisi "kayıpsızı bozan
şey, tekrarlanan CONNECT'in o anki seviyeyle gitmesidir" idi; gönderim seviyesi
kaydedilip aynısı tekrarlandığında hiçbir şey değişmedi. İkincisi "aynı seviye
ve parçayı taşıyan INITIATE bir ekodur, düşürülmelidir" idi; sıkı biçimi 6/9,
ebeveyn istisnalı biçimi 7/9 verdi, yani ikisi de düzeltmedi. Asıl sebep her
iki durumda da kök değişiminin tekrarıydı.

## 101. Payda: susan sınırın herkese ödettiği bir örnek

§96'da derece açığı tanığı eklenmişti: bir düğüm derecesinden fazla kenar
sahiplenemediğinden sahiplenilebilir gerçek kapasite $\sum_v \min(\deg v, k)$
olmakta ve bu toplam $m$'nin altına düştüğünde örnek çözümsüzdür. Tanık koşum
düzeyine bağlanmış, rapor hattına bağlanmamıştı.

Hat uygulanabilirliği yalnız `counting_bound_infeasible` ile sınamaktaydı.
`n50_m300_s6` için o sütun `False` okumaktadır, çünkü $m = n\cdot k = 300$
eşitliği sağlanmakta ve sayma sınırı tam sınırda susmaktadır. Oysa aynı örnekte
iki düğümün derecesi beştir, dolayısıyla sahiplenilebilir kapasite 298'de
kalmakta ve iki kenarı sahiplenecek kimse bulunmamaktadır.

Sonucu tek bir satır değil **bütün tablo** ödemekteydi: yirmi beş kolun hepsi
n=50 tablosunda 17/18 okumakta, kaybedilen bir puan hiçbir kolun kusuru
olmadığı hâlde her kola yazılmaktaydı. Tanık bağlandıktan sonra tablo dürüst
sayıyı, 17/17'yi yazmaktadır. Başlık da düzeltilmiştir: dışlama gerekçesi
$m > nk$ diye basılmaktaydı, oysa bu örnekte ateşleyen tanık derece açığıdır ve
o örnek için $m > nk$ doğru bir ifade değildir.

Ders §96'nın dersinin ikinci yarısıdır. Bir sınır eklemek yetmemekte, onu
okuyan her yere bağlamak gerekmektedir; bağlanmamış bir sınır sessizce eski ve
zayıf olanı kullandırmaktadır.

## 102. Süpürmelerin tek parmak izinde yenilenmesi

Üç süpürme (küçük n=10..25, orta n=50, orta n=100) düzeltilmiş kodla yeniden
koşulmuş ve üçü de tek parmak izi `b1b0a4761be4` taşımaktadır. Toplam 1665
satır, 1490 uygulanabilir koşum, **1489 geçerli ve sıfır yanlış başarı.**

Tavlama kollarının n=50'de 12/18 ve 13/18 okuyan satırları 17/17 olmuştur.
Bunu sağlayan yeni bir şey yapılmamıştır; o satırlar bu oturumda giderilen
epoch sıfırlama kusurunun izidir ve tablolar yalnızca düzeltmeden önceki kodla
ölçülmüş olduğundan eski kalmıştı. Ölçüm şu an gerçeği göstermektedir.

Geriye tek bir kesik koşum kalmaktadır: GHS-MST-Backbone/async, `n15_m30_s2`,
ikinci tohum, SIFIR kayıpta. Durum dökümü iki parçanın birbirini beklediğini
göstermektedir: düğüm 13 çekirdeğe FOUND durumunda girdiğinden hiç TEST
etmemekte, kendi dış kenarı (13,6) 103088128 ağırlığıyla parçasının talep
ettiği 106758143'ten HAFİF olduğu hâlde raporuna INF yazmaktadır. İki hipotez
ölçümle çürümüştür. Birincisi ertelenmiş kuyruğun yığılmasıydı; düğüm 13'te
6665 kayıt sayılmış, tam-demet tekilleştirmesi eklenmiş, yığılma kesilmiş ancak
kilit sürmüştür. İkincisi yinelenen INITIATE'in uçuştaki TEST'i silmesiydi;
koruma konduğunda kayıpsız dokuz örnek 9/9 kalmış, kayıplı hücre ise 41/45
yerine 40/45 okumuş, yani koruma bir koşum KAYBETTİRMİŞ ve kilidi de
açmamıştır; bu yüzden geri alınmış ve gerekçesi koda yazılmıştır. Kusur açıktır ve koşum `truncated` bildirdiğinden
yanlış başarı değildir.

## 103. Yeniden üretilemeyen tablo ve bir puan eski sayı

"Her şey yerli yerinde mi" sorusu iki şey açığa çıkardı ve ikisi de sessizdi.

**Kablosuz tablosu artık kendi kanıtından üretilemiyordu.** `_wireless_docs`
yalnız düz `<stem>.json` dosyalarını okumaktaydı, oysa koşucu bir süredir koşum
başına DİZİN yazmakta ve özet `summary.json` içinde durmaktadır. Yükleyici
`results/bb/wifi_dagdeviren` için sıfır belge bulmakta, `table_wireless` `None`
döndürmekte ve rapor hattı tabloyu üretmeden geçmekteydi. Yayımlanmış
`wireless.tex` dosyası yerinde durduğundan hiçbir şey hata vermemiş, tablo
yalnızca DONMUŞTU. Denetlenemeyen tablo, bu hattın var olma sebebinin tam
tersidir. Yükleyici iki düzeni de okumaktadır ve tablo arşivden **birebir aynı**
üretilmektedir; içeriği ayrıca 26 satır için `summary.json` değerlerine karşı ve
27 koşumun tamamı doğrulayıcıdan yeniden geçirilerek sınanmıştır, 27/27
geçerlidir.

**Eşli deneyin yayımlanmış CSV'si bir kod değişikliği eskiydi.** Deney,
§102'nin kuyruk tekilleştirmesi eklenmeden hemen önce koşulmuştu. Aynı deney son
kodla yeniden koşulduğunda 270 satırın 5'i değişmekte, GHS kayıplıda 40/45'ten
**41/45'e** çıkmakta, %10 kayıpta ise 42/45'ten **45/45'e** çıkmaktadır. Kollar
arası sıralama ve yanlış başarı sayıları değişmemektedir. Arşiv son ölçümle
değiştirilmiş, tüm belgeler ve `_ghs_reassert` ile testin gövde notları yeni
sayıya çekilmiştir.

Bunun yan ürünü olarak eko korumasının bedeli de netleşmiştir. Önceki kayıt onu
"kayıplıda 40/45'i aynen bıraktı" diye anmaktaydı, oysa kıyas yanlış tabana
yapılmıştı: tekilleştirme sonrası taban 41/45'tir, koruma ile 40/45 okunmakta,
yani koruma bir koşum KAYBETTİRMEKTEDİR. Geri alınmış olması doğrudur ve
gerekçesi artık ölçülen bedeliyle birlikte durmaktadır.

Ders ikisinde de aynıdır. Bir sayı bir kez ölçülüp yazıldıktan sonra, altındaki
kod ya da düzen değiştiğinde kendi kendine bağırmamaktadır; hangi kodun hangi
sayıyı ürettiği yazılmadıkça ve tablo kanıtından yeniden üretilebilir kalmadıkça
eskimesi görülmemektedir.

## 104. "Neden hâlâ 41, 42?" — kalan dördün üçü ayrı birer kusurdu

Kayıplı hücrelerin 45'e ulaşmaması kayıp altında kaçınılmaz sanılıyordu. Değildi.
Başarısız koşumların durumu tek tek döküldüğünde üç ayrı ve birbirinden bağımsız
kusur çıkmıştır. Üçü de aynı biçimdedir: **bir kez söylenen şeyin geri dönüş
yolu yoktur.**

**Birincisi, parça kimliği kenarı değil ağırlığını saklıyordu.** `ghs_frag`
çekirdek kenarının AĞIRLIĞIDIR ve ders kitabı bütün kenar ağırlıklarının farklı
olduğunu varsaymaktadır. Burada değildir: bir kenarın ağırlığı $w(u)+w(v)$
olduğundan iki farklı kenar, iki ayrı düğüm çiftinin toplamı denk düştüğünde
çakışmaktadır. İstasyonların gördüğü çizgelerde ölçülen çakışma n15_m90 s3'te 6
kenarda 3 toplam, n20_m160 s1'de 10 kenarda 5 toplamdır.

Çakışma bir eşitlik değil YANLIŞ CEVAPTIR. `_ghs_on_test` soranın parça kimliği
kendisininkine eşitse REJECT yanıtlamakta, REJECT ise kenarı kalıcı olarak
REJECTED işaretlemektedir. Dolayısıyla çekirdek kenarları aynı ağırlığı taşıyan
İKİ FARKLI parça birbirine "biz aynı parçayız" demekte ve onları birleştirebilecek
kenar temelli olarak atılmaktadır. Kimlik artık `_pack_tie` ile kenarın iki uç
kimliğinden kurulmakta, yani kenarı tekil olarak adlandırmaktadır. Kayıplı hücre
41/45'ten **43/45**'e çıkmıştır.

**İkincisi, birinci evrenin bittiği bir kez duyuruluyordu.** `_v4_flood_done` tek
bir DFS_DONE yayınlamakta ve bir daha tekrarlamamakta, `_v4_done_seen` de
işleyiciyi kalıcı olarak etkisizleştirmektedir. Bir kesme noktasında düşen tek
çerçeve arkasındaki bütün alt ağacı öksüz bırakmakta, o düğümler tamamlanmış bir
ağaçla, soracak sorusu ve bekleyecek kimsesi olmadan evre 1'de kalmaktadır.
n15_m90 s1 tohum 3'te ölçülen tam budur: çekirdek çifti 12 ve 13 durup evre 3'e
geçerken diğer ON ÜÇ düğüm evre 1'de kalmış, koşum iki düğümlük örtü döndürmüştür.

Önce duyuruyu tekrarlatmak denenmiş ve iki kez çürümüştür. Tekrarı halt eden
düğüme koymak işe yaramamıştır, çünkü `_backbone_step` yalnız evre 1-2'de
çağrılmakta olup düğüm o sırada evre 3'tedir, üstelik orada kanca açmak dikiş
sözleşmesine aykırıdır. Doğru taraf terstir: **öksüz kalan düğüm zaten görmektedir.**
Evre 1'i geçmiş bir komşu her HELLO'da evresini yaymakta, ve oraya ancak durarak
ya da DONE duyarak geçebilmektedir. Yeni ileti gerekmemekte, periyodik işaret
okunmaktadır. Hücre **44/45** olmuştur.

**Üçüncüsü, sessiz evrenin kendi deliğiydi.** Son DONE HELLO'su da düşebilmekte,
o zaman komşunun bendeki kaydı PH_DONE'un altında donmakta, bariyeri hiç
kapanmamakta ve sonsuza dek yayın yapmakta, ben ise onu DONE gördüğümden kendi
bariyerimi kapatıp susmaktayım. Bayat yarıyı tazeleyecek hiçbir şey kalmamakta,
ağ hiç boşalmamakta ve koşum **geçerli bir örtüyü elinde tutarken** `truncated`
bildirmektedir. n15_m90 s3 tohum 1'de on beş düğümün on beşi de PH_DONE'a
ulaşmış, buna rağmen 10, 12 ve 13 numaralı düğümler komşularını hâlâ PH_QUIET'te
kaydetmekteydi; dört kat bütçede de değişmemiştir.

Eksik bilgi yine havadadır: DONE bir düğüm ancak bariyeri AÇIKKEN yayın yapar,
dolayısıyla DONE bir komşudan HELLO almak onun birini kaçırdığının kanıtıdır ve
benden kaçırabileceği tek şey kendi son HELLO'mdur. Ancak kuralın üç kez
daraltılması gerekmiştir ve üçü de ölçümle zorunlu kılınmıştır.

- Serbest yanıt KENDİNİ ÇÜRÜTMEKTEDİR: kapalı bir düğüm yanıtlayınca "DONE olan
  yalnız açıkken yayın yapar" önermesi bozulmakta, iki kapalı düğüm birbirini
  sonsuza dek yanıtlamaktadır. Ölçüldüğünde kayıpsız 9 koşumun 0'ı, kayıplı 45
  koşumun 0'ı yakınsamıştır. Bu yüzden her komşuya DONE dönemi başına en çok bir
  yanıt verilmektedir.
- Duvar saatiyle kurulmuş eşik EMÜLATÖR İLE SİMÜLATÖRÜ AYIRMAKTADIR: aynı koşum
  gerçek soketlerde 53, simülatörde 57 slotta bitmiş, örtü ve tx birebir aynı
  kalmıştır. İki periyot iki arka uçta aynı yere düşmemektedir. Eşik bu yüzden
  olaya bağlanmıştır: kendi DONE HELLO'mdan sonra o komşudan duyduğum İKİNCİ
  yayın. İleti dizisi iki arka uçta birebir aynı olduğundan eşik de aynıdır.
- Onarım `_hello_dirty` üzerinden gönderildiğinde OLAY sütununa yazılmakta ve
  sayaç ayrımını yanlış söyletmektedir (109'dan 113'e). Onarım hiçbir durum
  değişikliği taşımamakta, yalnız duyurulmuş bir olguyu yinelemektedir, bu
  yüzden canlılık işareti olarak gönderilmektedir; olay payı 109'da sabit
  kalmakta, canlılık payı 173'ten 176'ya çıkmaktadır.

Üçünün bedeli çalışılan örnekte dört HELLO'dur: tx 507'den 510'a, rx 1367'den
1373'e, **slot sayısı 53'te değişmemekte** ve emülatör simülatörle birebir
uyuşmaya devam etmektedir.

## 105. MIS-Connector'ın iki yanlış başarısı ve kapanışları

§104 GHS'i 45/45'e taşıdıktan sonra kayıplı koşulda geriye MIS-Connector'ın iki
koşumu kalmıştı ve ikisi de `solved` bildirip doğrulayıcıdan geçemediğinden en
tehlikeli sınıftaydı. İkisi de ayrı kusurdur ve ikisi de kapanmıştır.

**Birincisi, ACK'in yetkilendirdiği şeyin elde kalıp kalmadığı sorulmuyordu.**
Devir ile onun onayı arasında aynı kenar BANA GERİ DÖNEBİLMEKTEDİR; o zaman ACK,
sonradan yeniden edindiğim bir kenarın devrini onaylamaktadır ve ona uymak
kimsenin tutmadığı bir şeyi elden çıkarmaktadır. n15_m90 s2 tohum 0'da (12,15)
kenarının izi şöyledir: 15 kabul etti, 12 bıraktı, 12 geri aldı, 15 kabul etti,
ardından İKİSİ DE bıraktı; her biri kendi yeniden edinişinden ÖNCE gönderdiği
devrin onayına uymaktaydı. `_loses_race` aynı anda bekleyen iki isteği
korumakta, bunlar ise aynı anda beklememekteydi. Kenar sahipsiz kalmıştır.

Düzeltme, devri kenarın SÜRÜMÜNE bağlamaktadır: `Pending` gönderim anındaki
ediniş sayısını taşımakta, onay geldiğinde sayı değişmişse bırakma
yapılmamaktadır. Bu, işlemin "altımdan dünya kaydı mı" sorusunu sormasıdır.
Yan olarak `_offered` da kabul anında temizlenmektedir; küme yalnızca
ekleniyordu, dolayısıyla geri aldığım bir kenar koşumun sonuna kadar "teklif
edilmiş" sayılmaktaydı.

**İkincisi, anahtar seçimi iki ucun da kenarı gördüğünü varsayıyordu.**
`_rule_cover` iki ucu da dışarıda olan kenarı KÜÇÜK ANAHTARLI uca vermekte ve
mesajsız olmasını tam da iki ucun aynı iki anahtardan aynı sonucu hesaplamasına
borçludur. Kenarın iki komşu tablosunda da bulunduğunu sessizce varsaymaktadır.
Kayıp altında bulunmayabilir: yumuşak durum tek tarafta çürüyebilmekte, seçilen
uç kenarın varlığından habersiz kalmakta ve hiç davranmamakta, öteki uç ise ona
sonsuza dek yol vermektedir. n10_m20 s3 tohum 0'da (1,7) kenarında ölçülen budur:
düğüm 1'de `bidir=False`, yani kenar yok; düğüm 7'de `is_edge=True` ve karşı
tarafın anahtarı küçük. İkisi de OUT kalmış, kenar hem örtüsüz hem sahipsiz
çıkmıştır.

Onarım BİR ROL'dür, bir hüküm değil. "Açıkta kenar görürken yerleşmeyi reddet"
daha önce denenip geri alınmıştı: `verdict` yalnız sonlanma kipidir ve onu
geçerliliğe bağlamak SAPTANABİLİR bir yanlış başarıyı saptanamaz bir kesintiye
çevirmektedir. Bunun yerine kenar örtülmekte, yani CEVAP doğru yapılmaktadır ve
işlem tek yönlü olduğundan salınım üretmemektedir. Seçim ancak başarısız olduğu
GÖSTERİLDİKTEN sonra bozulmaktadır: komşu hâlâ OUT olmalı ve ilan ettiği evreye
göre kendi örtü kararını çoktan geçmiş olmalıdır. Öncesinde yalnızca erkendir ve
erken davranmak boş yere bir düğümü örtüye sokardı.

**Sonuç: üç kolun üçü de kayıpsızda 45/45 ve kayıplıda 45/45, yanlış başarı
sıfır.** MIS-Connector'ın geçerli koşumlarındaki ortalama ağırlık düzeltmelerle
birlikte 8901,7'den 8873,9'a inmiştir, yani doğruluk kaliteye mal olmamıştır.

## 106. Başlamamış arama, boş arama diye raporlandı

Küçük gruptaki son kesik koşum — GHS-MST-Backbone/async, `n15_m30_s2`, SIFIR
kayıpta — kapandı. Kusur ne düşen bir iletiydi ne de bir yığılma; İKİ AYRI
SORUYU YANITLAYAN İKİ ALANIN tek alan sanılmasıydı.

`ghs_test_nid` "uçuşta sorum var mı" sorusunu, `ghs_test_done` ise "aramam bitti
mi" sorusunu yanıtlamaktadır. `_ghs_pending_unknown` yalnız birincisine
bakmakta, `_ghs_try_report` de yalnız onu sınamaktaydı. Bir REJECT
`ghs_test_nid`'i temizledikten sonra, düğümün bir sonraki zamanlayıcı vuruşunda
`_ghs_test` sıradaki BASIC kenarı sınayana kadar İKİSİ DE yanlıştır ve düğüm
yerleşmiş görünmektedir. `_ghs_on_report` ise `_ghs_try_report`'u İLETİ
yolundan çağırmaktadır; tam o pencerede gelen bir çocuk raporu düğümü FIND'den
kalıcı olarak çıkarmakta, `_ghs_test` yalnız FIND'de koştuğundan geriye kalan
BASIC kenarlar hiç sınanmamaktadır. Bu, §95'te kapanan sınıfın bir adım
içerisidir: orada ERTELENMİŞ BİR SORU cevap diye okunmuştu, burada HİÇ
BAŞLAMAMIŞ BİR ARAMA boş arama diye raporlanmaktadır.

**Bedeli tek düğümün best'i değil PARÇANIN best'idir.** Böyle INF raporlayan bir
düğüm sahibi olduğu bütün dışarı kenarları parçasından gizlemekte, parça da
gerçekte sahip olduğundan DAHA AĞIR bir asgari dış kenar ilan etmektedir. O
zaman iki parça İKİ FARKLI kenarı adlandırmakta, her biri karşı tarafın hâlâ
BASIC tuttuğu bir kenarda eşit seviyede CONNECT göndermekte, ikisi de
`_ghs_on_connect`'in "eşit seviye ama kenar henüz bizim değil" dalına düşüp
sonsuza dek ertelemektedir. Hiçbir ileti kaybolmamakta ve hiçbir tekrar yanlış
yapmamaktadır, dolayısıyla ne bütçe ne de yeniden-sorma bunu kurtarmaktadır.

İz (async, tohum 2, kayıpsız):

```
t=1550 n13 INITIATE   par=12 L=1 frag=360460 state=FIND
t=1550 n13 TEST       -> 14                      # (13,14), REJECT ile döner
t=1742 n 1 REPORTED   test_done=True  best=INF   # düğüm 1'in tek kenarı kalmamış
t=1950 n13 RX REPORT  from=1 ... test_done=False
t=1950 n13 REPORTED   test_done=False test_nid=None best=INF BASIC=[4, 6, 7, 9]
```

Düğüm 13'ün sınamadığı (13,6) kenarı 103088128 ağırlığındadır ve donan iki
parçayı ayıran BEŞ kenarın EN HAFİFİDİR. Bu yüzden 13'ün parçası
{1,2,3,7,9,10,11,12,13,14,15} onun yerine (5,9)'u 106758143 ile talep
etmektedir. Öteki parça {4,5,6,8} (6,13)'ü talep etmekte, düğüm 13 o CONNECT'i
kendi tarafında (13,6) BASIC olduğu için ertelemekte, düğüm 5 de aynasını (5,9)
üzerinde ertelemektedir. İki parça da seviye 1'de donmuş hâlde dört bin saniyelik
bütçenin sonuna kadar beklemektedir.

**Üçüncü hipotez de düştü ve düşen bu kez bizim kendi teşhisimizdi.** §102 iki
hipotezi ölçümle çürütmüştü: ertelenmiş kuyruğun yığılması (6665 kayıt;
tekilleştirme yığılmayı kesti, kilidi açmadı) ve yinelenen INITIATE'in uçuştaki
TEST'i silmesi (koruma kayıplıyı 41/45'ten 40/45'e düşürdü, kilidi açmadı). Aynı
kayıt teşhisi de yazmıştı: "düğüm 13 çekirdeğe FOUND durumunda girdiğinden hiç
TEST etmemektedir." İz bunu çürütmektedir; düğüm 13 `state=FIND` ile
başlatılmakta ve (13,14)'ü sınamaktadır. Hiç çıkamadığı durum FOUND değildir,
FIND'dir ve oradan ERKEN çıkmaktadır. Doğru okuma tersidir: soru "neden hiç
TEST etmedi" değil, "neden TEST etmeyi bıraktı" olmalıydı.

Düzeltme tek koşuldur: `_ghs_try_report` artık `ghs_test_done` de doğru değilse
raporlamamaktadır. Bedeli en fazla bir vuruştur, çünkü BASIC kenarı kalmamış bir
düğümde `_ghs_test` bir sonraki çağrısında hiçbir ileti göndermeden
`ghs_test_done`'u kurmaktadır.

**Ölçüm, öncesi ve sonrası.** Küçük grup süpürmesi aynı bayraklarla (small, üç
tohum, k=6, kayıpsız, `mis_nbrs_max=64`, dört bin saniye, iki zamanlayıcı)
yeniden koşuldu.

| hücre | önce | sonra |
|---|---|---|
| GHS-MST-Backbone/sync | 33/33 | 33/33 |
| GHS-MST-Backbone/async | **32/33** | **33/33** |
| yanlış başarı | 0 | 0 |

Kurtarılan satır `n15_m30_s2` async'tir: önce boş örtüyle `truncated`, sonra
5543 ms'de yakınsayıp Σw = 9153 ile `solved`. Dağıtık omurga merkezî kâhinle
birebir aynıdır ({5, 6, 11, 12, 13, 15}) ve ağaç Kruskal'ınkiyle aynı ağırlığı
taşımaktadır.

**BİR SATIR DA BEDEL ÖDEDİ ve kayda geçmesi gerekmektedir.** `n10_m20_s3`/sync
hâlâ `solved` ve geçerlidir ama örtüsü yedi düğüm ve Σw = 4201 iken sekiz düğüm
ve Σw = 5336 olmuştur; kesin optimum 3810 olduğundan oran 1,10'dan 1,40'a
çıkmaktadır. Diğer 64 satır birebir aynıdır. Toplamda, iki ölçümde de geçerli
olan 65 satırın örtü ağırlığı toplamı %0,16 artmakta, kesin çözücünün koştuğu
29 satırda ortalama oran 1,1715'ten 1,1818'e gitmektedir.

Bu satırdaki farkın NEREDE doğmadığını söylemek onu okumanın tek yoludur:
OMURGA DEĞİŞMEMİŞTİR. Aynı örnek iki kodla tek tek koşulduğunda dağıtık MST'nin
iç düğümleri her iki durumda da beş düğüm ve 2772 ağırlıktadır. Değişen yalnız
iletilerin sırasıdır ve fark evre 2-5'in sıraya duyarlı örtü kararlarında
doğmaktadır; `slots` 36'dan 37'ye çıkmakta, yani rapor gerçekten bir vuruş
geç gitmektedir. Yani bu bir MST kusuru değil, düzeltmenin kaçınılmaz yan
etkisidir: raporunu bekleten bir düğüm ağı farklı bir sırada ilerletmektedir.

Bedelsiz bir biçimi arandı ve ölçümle elendi. İkinci biçim raporlamayı
engellemek yerine `_ghs_try_report` içinden `_ghs_test`'i ÇAĞIRMAKTA, böylece
aramayı aynı çağrıda başlatmaktaydı. `n10_m20_s3`/sync yine 5336 vermekte, yani
hiçbir şey kazandırmamakta, üstelik "aramam bitmeden raporlamam" değişmezini de
bozmaktadır çünkü BASIC kenarı kalmamış düğüm aynı çağrıda raporlamaktadır. Geri
alındı; şu an duran biçim birincisidir.

Eşli kayıpsız/kayıplı deney yalnız GHS için yeniden koşuldu: **45/45 ve 45/45,
sıfır yanlış başarı**, ve doksan satırın doksanı arşivdekiyle alan alan aynıdır.
Düzeltme o deneyi HİÇ oynatmamaktadır ve nedeni yapısaldır: oradaki dokuz çizge
senkron zamanlayıcıyla koşulmaktadır, senkron kipte ise bir slotta önce bütün
çerçeveler teslim edilip sonra her düğümün zamanlayıcısı ateşlendiğinden REJECT
ile `_ghs_test`'in sıradaki kenarı sınaması arasına bir rapor giremez. Pencere
yalnız asenkron kipte açılmaktadır ve ölçüm de tam olarak orada, tek bir
satırda görünmüştür.

**Tablo kendi kanıtından yeniden üretildi.** §103'ün dersi burada da geçerlidir:
bir sayı, altındaki kod değişince kendi kendine bağırmaz. Bu yüzden küçük grup
süpürmesi yalnız GHS için değil ON ÜÇ KOLUN TAMAMI için yeniden koşuldu ve tek
parmak izi `d507eeec7778` taşımaktadır (`sweep_small_full_k6_clean_v3`). 975
satırın **975'i geçerli, yanlış başarı sıfır**, ve arşivlenmiş v2 ölçümüne göre
değişen satır sayısı **ikidir**; ikisi de yukarıda adı geçen GHS satırlarıdır.
Diğer on iki kolun 897 satırı alan alan aynıdır, yani düzeltme gerçekten
yalnız kendi kolunu ilgilendirmektedir.

Bunun bir yan sonucu vardır ve tablo okunurken görülmesi gerekir: ORTAK GEÇERLİ
ALTKÜME 32'DEN 33'E ÇIKMAKTADIR. Kurtarılan `n15_m30_s2` bütün kollar için zor
bir örnektir, dolayısıyla paydaya girmesi yirmi beş kolun HEPSİNİN kesin
optimuma oranını yukarı itmektedir. Bu bir kalite kaybı değil, daha dürüst bir
paydadır; §101'in dersinin aynadaki hâlidir, orada haksız yere dışarıda kalan
bir örnek herkese bir puan ödetmekteydi, burada haklı olarak içeri giren bir
örnek herkesin oranını gerçeğe çekmektedir.

Sıralamada tek bir yer değişmektedir. GHS-MST/async 1,157'den 1,165'e çıkmakta
ve hâlâ tek başına en iyi koldur, ancak Anneal-Trickle 1,166 ile onunla
neredeyse başa baş gelmektedir. GHS-MST/sync ise 1,169'dan 1,205'e çıkarak
tavlama ailesinin ALTINA düşmektedir; sebebi yukarıdaki tek satırdır, çünkü
otuz üç örnekli bir ortalamada 4201'den 5336'ya çıkan bir satır tek başına
yaklaşık 0,03 taşımaktadır. n=50 ve n=100 süpürmeleri bu koşuda yeniden
koşulmamıştır ve `b1b0a4761be4` parmak izinde durmaktadır; düzeltme yalnız
asenkron GHS'i ilgilendirdiğinden bu ayrım tabloların yanına yazılmıştır.

**Eşli deneyin tamamı düzeltilmiş kodla yeniden koşuldu.** Yukarıdaki ölçüm
yalnız GHS kolunu kapsamakta olduğundan, aynı dokuz çizge, üç kol, iki koşul ve
beşer tohumla kurulu 270 koşumluk deneyin bütünü `d507eeec7778` parmak izi
altında baştan alınmıştır ve tablo yerinden oynamamaktadır: **270 satırın 270'i
`solved` ve geçerlidir, yanlış başarı sıfırdır**, altı hücrenin altısı da 45/45
okumaktadır. Düzeltmeden önceki arşivle alan alan karşılaştırıldığında DEĞİŞEN
TEK BİR HÜCRE YOKTUR ve iki ölçümün örtü ağırlığı toplamı 2.398.044 ile birebir
aynı kalmaktadır. Karşılaştırma dosyası `rows_before_106.csv` adıyla
saklanmakta, koşucu ise artık her satıra `code_fp` sütununu basmakta, böylece
§102'nin sorduğu "bu satırlar aynı koddan mı" sorusu bu deneyde de tabloya
bakılarak yanıtlanabilmektedir.

**Bir hücre kaydın dışında kalmamalıdır: %10 kayıpta GHS artık 45/45 değil
44/45 vermektedir.** Düşen satır `dag_mst_n10_m20_s1`/rng=2'dir ve verdiği şey
yanlış başarı değil `truncated`'dır, yani kol kendi başarısızlığını
bildirmektedir. Sebep de doğruluk değil bütçedir: aynı örnek 200 saniyelik
sınırın karşılığı olan 1000 slotta kesilmekte, sınır 400 saniyeye
çıkarıldığında ise 1119 slotta yakınsayıp Σw = 4385 ile geçerli bir örtü
vermektedir. Bu, §106'nın kendi ölçtüğü yan etkinin ikinci görünümüdür, çünkü
raporunu bir vuruş bekleten düğüm sınıra yakın duran bir koşumu sınırın öbür
yanına itmektedir. Alıntılanacak dayanıklılık hücresi hâlâ %5'tir ve orada
45/45 durmaktadır; %10'un ham satırları `rows_ghs_loss10_v3.csv` içindedir.

Makale denetimi bu satırlarla yeniden koşulmuş ve `paper/tools/check_paper.py`
**sıfır başarısız denetim** vermiştir.

## 107. Donmuş iki ucun üstünde açıkta kalan kenar

`full_v3`'ün bütün kümeyi tarayan süpürmesinde geriye **iki** yanlış başarı
kalmıştı ve ikisi de aynı koldaydı: Anneal-Trickle/async, SIFIR kayıpta,
`n100_m400_s10` ile `n200_m800_s1`. İkisi de `verdict=solved` bildirip
doğrulayıcıdan `bad_owner|uncovered_edge` ile dönüyordu. İkisi TEK bir kusurdur
ve kusur ne bir ileti kaybı ne de Trickle'a özgü bir şeydir.

**İki ihlal değil, bir ihlal ve onun sonucu.** `bad_owner` burada çakışan bir
sahiplik değil, doğrulayıcının "kenar sahiplik tablosunda yok" satırıdır: iki
ucu da örtü dışında olan kenarı sahiplenebilecek düğüm yoktur. Sahipsizlik
örtüsüzlüğün TÜREVİDİR, ayrı bir arıza değildir.

**Önce yanlış çıkan varsayımlar, çünkü asıl bilgi onlardadır.**

*Trickle'ın uzattığı HELLO periyodu yumuşak durum penceresini aşıyor, komşu
düşüyor ve donma kararı BAYAT durum üstünde veriliyor.* YANLIŞ. Donma anında
iki düğümün de görüşü tazedir: `_t_hello_cur` tavanda 400 ms'tedir ve düğüm 7
komşusu 70'i 200 ms önce, düğüm 70 ise 7'yi 0 ms önce duymuştur. Dahası ikisi
de karşısını DOĞRU görmektedir, `x=0`. Donan düğüm kenarın açıkta olduğunu
bilmemekte değildir; bilmektedir.

*Donma, etiket bölünmesi askıdayken gerçekleşiyor.* YANLIŞ. İki düğüm de örtü
dışındadır, dolayısıyla `_loop_c` etiketlerini kendi kimliklerine sabitlemiştir
ve katılma deltasının köprü indirimi terimi SIFIRDIR: düğüm 7'nin on altı örtü
komşusunun tamamı tek etiket taşımaktadır, yani örtü bağlıdır.

*Faz 4'te async altında kabul-serbest bırakma sırası bozuluyor.* YANLIŞ; Faz 4
hiç oynamamaktadır, çünkü sahiplenilecek bir uç yoktur.

**Kök sebep, tavlamanın atladığı fazdır.** Donma `phase = PH_OWN` yazmakta,
dolayısıyla PH_FORCED hiç işgal edilmemektedir; oysa BB-CVC'nin
`_cover_what_the_key_election_missed` onarımı — §105'te tam bu belirti için
yazılan onarım — yalnız oradan çağrılmaktadır. Tavlama, BB-CVC'nin Faz 4 ve
Faz 5'ini satırı satırına devralırken Faz 3'ün ÜSTÜNDEN ATLAMAKTA ve atladığı
şey "iki ucu da kararını vermiş, kenar hâlâ açıkta" durumunun tek çaresidir.

**Peki enerji fonksiyonu neden kurtarmıyor?** Çünkü açıkta kalan kenarı
kapatacak hamle YOKUŞ YUKARI fiyatlanmaktadır. Katılma, `_loop_a`'da bütün
esnek payları y = 1/2'ye SIFIRLAMAKTA ve `_delta_e` bu sıfırlamanın yarattığı
GEÇİCİ aşırı yükü aynı deltada tahsil etmektedir. `n100_m400_s10` seed 10'da
düğüm 7'nin derecesi 17, F = 1, k = 6'dır:

```
ell_yeni = 1 + 16 x 1/2 = 9  ->  asim = 3
delta(katil) = +w - lam_c x 1 + lam_k x 3
             = +261 - 2370 + 7110 = +5001
```

Düğüm 70 için aynı hesap +3218 vermektedir. Koşul kapalı biçimde
`deg > 2k - F`'tir. T <= T_min'de yalnız iniş kabul edildiğinden onarım hiçbir
zaman alınamamakta, iki uç da **gerçek bir yerel asgariye** donmaktadır.
Buradaki asıl sonuç şudur: `.tex`'in "enerji asgarileri tam olarak geçerli
çözümlerdir" savı bu enerji fonksiyonu ve bu y-sıfırlaması ile YANLIŞTIR.
Donmuş durum hem yerel asgaridir hem geçersizdir.

**Düzeltme bir ROL'dür, bir hüküm değil** (§105 ile aynı biçim). "Açıkta kenar
görürken donmayı reddet" burada zaten işe yaramazdı: düğümün elindeki bütün
hamleler yokuş yukarı olduğu için reddetmek onarım satın almaz, yalnız hiç
bitmeyen bir koşum üretir. Onun yerine donmuş dalda BB-CVC'nin KENDİ onarımı
çağrılmaktadır. Yeni bir kural yazılmamıştır; onarımın kendi kapısı zaten tam
olarak donmanın yanıtladığı soruyu sormaktadır: komşu hâlâ OUT olmalı ve İLAN
ETTİĞİ EVREYE göre kendi örtü kararını geçmiş olmalıdır. Tavlayan bir düğüm
PH_ANNEAL = PH_COVER ilan eder, bu da PH_FORCED'ın ALTINDADIR, dolayısıyla hâlâ
tavlanan bir komşu onarımı tetikleyemez ve kenarı kendi kapatmaya bırakılır.
Donmuş komşu PH_OWN ilan eder ve bir daha asla flip etmez; kenar o noktada
kanıtlanabilir biçimde başka kimsenin kapatamayacağı bir kenardır.

Tavlamaya özgü tek ek, örtü bitinin İKİ ALANDA yaşamasıdır: `role` tabanın
taşıdığı, `x` ise bütün tavlama kurallarının okuduğu alandır ve yalnız birinin
taşınmasının bedeli `_reset_to_phase0`'da zaten kayıtlıdır. Bu yüzden onarım
`x`'i, payları ve ilan edilen yükü `_loop_a`'nın katılmada yaptığı gibi
kurmaktadır. İşlem TEK YÖNLÜDÜR: `role` OUT'tan bir kez çıkar ve Loop A çoktan
donmuştur, dolayısıyla salınım üretemez.

**Öncesi / sonrası** (Anneal-Trickle/async, kayıpsız, k = 6):

```
ornek                 |C|        Sigma w              tx         gecerli  verdict
n100_m400_s10   84 -> 85   48950 -> 49211   7729 -> 7785   F -> T   solved
n200_m800_s1   170 -> 171 114908 -> 115748 15264 -> 15333   F -> T   solved
```

Her iki koşumda da tek bir uç onarmaktadır, ikisi birden değil: `n100` kenar
(7,70)'te düğüm 7'yi, `n200` kenar (30,51)'de düğüm 51'i örtüye almaktadır.
Hüküm YERİNDE KALMAKTADIR — ikisi de `solved`'dır — ve bedeli iki düğüm ile
%0,5'ten küçük bir iletidir.

**Değişiklik paylaşılan tavlama kodundadır, Trickle'a özel değildir.** Kusurun
kendisi de öyledir: `_delta_e` ile donma kuralı üç tavlama kolunun ortağıdır ve
Trickle yalnızca yörüngeyi o tuzağa götüren koldur. Bu yüzden Anneal-Local ve
Anneal-TreeAgg de yeniden ölçülmüştür ve HİÇBİR SAYI OYNAMAMIŞTIR:

- Küçük grubun (`sweep_small_full_k6_clean_v3`) 195 tavlama satırı yeniden
  ölçülmüştür. Puanlanan 165 satırın TAMAMI, beş kol-zamanlayıcı
  yapılandırmasının hepsinde, |C|, Σw ve tx bakımından BİREBİR aynı çıkmıştır;
  oynayan satır sayısı sıfırdır. Kalan 30 satır sayma sınırıyla imkânsız
  örneklerdir (`n20_m160`, `n25_m200`; m > nk) ve durumları değişmemiştir.
- Yukarıdaki iki örnekte Anneal-Local ile Anneal-TreeAgg her iki zamanlayıcıda
  da birebir aynıdır; oynayan yalnız Anneal-Trickle/async'tir.
- Ölçek değişmezliği (ağırlık x1 / x10 / x100) 32 kıyas örneğinde tam olarak
  korunmaktadır.
- Tam süit yeşildir.

Bir başka kolun etkilenmesi zaten YAPI GEREĞİ mümkün değildir: eklenen geçersiz
kılma `AnnealNode` üstündedir ve tabanın `_rule_forced`'ı tavlamada hiç
koşmadığından tek çağıran yeni çağrı yeridir.

**Ama onarımın bir BEDELİ vardır ve süit onu hemen gösterdi.** Üç test düştü:
`test_fixed_lambda_on_heavy_weights_empties_the_cover`,
`test_an_invalid_final_state_is_exactly_when_the_flag_can_fire` ve
`test_verdict_is_not_derived_from_validity`. Üçü de ARIZA ENJEKSİYONUDUR ve
üçü de aynı kurguyu kullanmaktadır: donduktan sonra herkesi örtüden çıkarıp BOŞ
örtü üretmek. Onarım tam olarak bunu iyileştirmektedir, dolayısıyla kurgu
artık boş değil DOLU örtü vermektedir (ölçüldü: `[]` yerine `[1..10]`).

Bu, onarımın §42'nin manşet arızasını — λ sabit 12 iken örtünün boşalmasını —
MASKELEDİĞİ anlamına gelir ve bunun söylenmesi gerekir. Emniyet ağı hatayı
TELAFİ eder, GİDERMEZ: λ hâlâ yanlıştır, örtü hâlâ olması gerekenden kötüdür,
yalnız artık geçersiz görünmemektedir. `_check_lambdas`'ın yerinde kalması bu
yüzden ONARIMDAN SONRA DAHA ÖNEMLİDİR, daha az değil; hatayı yakalayan ilk ve
gürültülü kapı odur.

Üç testin enjekte ettiği arızaya onarımın devre dışı bırakılması da eklenmiştir,
çünkü onarımın bozukluğu enjekte edilen arızanın parçasıdır; böylece her test
gene KENDİ değişmezini ölçmektedir. Emniyet ağının kendisi maskelemeye
bırakılmamış, `test_the_freeze_repair_refills_a_cover_that_annealing_emptied`
ile ayrıca çivilenmiştir: aynı kurgu onarım AÇIKKEN koşmakta, örtünün
dolduğunu, doğrulayıcıdan geçtiğini ve `x` ile `role`'ün ayrışmadığını
sınamaktadır. Onarım sessizce silinirse o test düşer.

**Yeniden ölçülmesi gereken `full_v3` satırları.** DEĞER olarak yalnız
Anneal-Trickle satırları değişebilir, ama sorumluluk sınırı kolun değil kodun
sınırıdır: değişen dosya üç tavlama kolunun ortağıdır, dolayısıyla yeniden
ölçülecek küme ÜÇ TAVLAMA KOLUNUN TAMAMIDIR. Diğer on kolun sayıları
değişemez; yalnız `code_fingerprint` sütunu, parmak izi içerik değil değişiklik
zamanı ve boyut üstünden hesaplandığı için, bu düzeltmeden sonra ölçülen HER
satırda yeni bir değer taşıyacaktır.
