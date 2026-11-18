#!/usr/bin/env python3
"""BB-CVC deney koşucusu (brief §12 adım 9): matris süpürmesi, CSV ve summary.md.

Koşum:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m ccvc.bb.sweep --groups small \
        --max-seeds 3 --out results/bb/<ad>

Bu dosya HİÇBİR varyantı bilmez. Varyantlar kendilerini `BB_VARIANTS` ile
bildirir (aşağıdaki sözleşme), koşucu onları bulur ve satır üretir. Amacı,
varyantlar yazılmadan önce var olmak ve hepsinin aynı sütunlara yazmasıdır.

DÖRT DİSİPLİN KURALI — üçü CCVC katmanında gerçek geri çekmelere mal oldu
-------------------------------------------------------------------------
**1. Hayatta kalma yanlılığı.** Bir kol başarısız olunca oran ortalamasından
DÜŞER, kötü bir oran olarak GÖRÜNMEZ; çok düşen kol, sağ kalan kolay örnekler
üstünde haksız yere iyi görünür. Bu yüzden iki oran ayrı raporlanır:
`ratio_own_*` kolun kendi geçerli örneklerinde, `ratio_common_*` BÜTÜN kolların
geçerli olduğu ortak altkümede. Karşılaştırma `ratio_common_*` ile yapılır;
ikisi ayrışıyorsa fark doğrudan başarısızlık örüntüsünden gelir ve özet bunu
yazar.

**2. Eşleşmiş hücreler.** İki kol ancak "aynı algoritma, farklı koşul" ise
kıyaslanabilir. Bu kendiliğinden olmuyor: bir kez sıralı bir açgözlüyle paralel
bir yerel-maksimallik yöntemi kıyaslanıp 2x2 denildi. Burada dikkatle değil
YAPISAL olarak engellenir: her varyant üç ekseni (`scheduler`, `phase1`,
`phase5`) BİLDİRİR ve eşleşmiş çift, TAM OLARAK BİR eksende ayrılıp geri
kalanında ve (hücre, tohum) kimliğinde aynı olan iki koldur. Eksen bildirmeyen
bir varyant eşleşmiş kıyasa giremez.

**3. Başarısızlık veridir.** `unresolved` bir sonuçtur; CSV'de kendi durumuyla,
slot sayısı ve tx'iyle DURUR, eksik satır olarak değil. BB-CVC n=100/k=4'te
gerçekten başarısız ve bunu 1598 slot harcayarak yapıyor, yani başarılı bir
koşumun ~50 katı; koşucunun görevi bunu gizlemek değil ölçmek.

**4. Tohum sayısı.** Büyük grupta hücre başına TEK tohum var. Tek koşuma
"ortalama" demek yalandır; özet her hücrenin tohum sayısını yazar ve 3'ten az
olanları `TEK KOŞUM` diye işaretler.

VERİ KAYNAĞI DÜRÜSTLÜĞÜ
-----------------------
Her satır `source` sütunu taşır: `dataset` (Dagdeviren kıyas kümesi) ya da
`synthetic` (testler ve duman koşuları için üretilmiş çizge). Sentetik satır
kıyas sonucu gibi okunamaz, çünkü sütun bunu söyler. Veri kümesi yoksa koşucu
kıyas modunda ÇALIŞMAZ, sessizce sentetiğe düşmez.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from typing import (Any, Callable, Dict, List, Mapping, Optional, Sequence,
                    Set, Tuple)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import matrix, validate  # noqa: E402
from ccvc.bb.matrix import Cell  # noqa: E402

Edge = Tuple[int, int]

# ==========================================================================
# 1. SÖZLEŞME — varyant yazanlar YALNIZ bunu okumalı
# ==========================================================================
#: Koşucunun varyant arayacağı modüller. Modül `BB_VARIANTS` adında bir
#: `Sequence[VariantSpec]` dışa vermeli; vermezse sessizce atlanır ama
#: `discover(strict=True)` bunu hata yapar.
VARIANT_MODULES: Tuple[str, ...] = (
    "ccvc.bb.bbcvc_variants",   # MIS-Connector-Backbone, MIS-Connector-TreeAgg (bb-algo)
    "ccvc.bb.v1_dfs",           # DFS-Spanning-Backbone
    "ccvc.bb.v4_mst",           # GHS-MST-Backbone
    "ccvc.bb.v5_wuli",          # WuLi-Dominating (tam liste / Bloom / parçalı)
    "ccvc.bb.v6_anneal",        # Anneal-Local
    "ccvc.greedy.distributed",  # Three local greedy backbone adaptations
)

#: Eşleşmiş kıyasın izin verdiği eksenler. Bir çiftin kıyaslanabilmesi için
#: TAM OLARAK BİRİNDE ayrılması gerekir (disiplin kuralı 2).
AXES: Tuple[str, ...] = ("scheduler", "phase1", "phase5")

#: Varyant sonucunda BULUNMASI ZORUNLU alanlar. `bbcvc.BbcvcRun` hepsini taşır,
#: dolayısıyla BB ailesi için uyarlayıcı yazmaya gerek yoktur.
REQUIRED_RESULT_FIELDS: Tuple[str, ...] = (
    "cover", "owner", "total_weight", "tx", "rx", "retx", "bytes_tx",
    "max_payload", "slots", "t_conv_ms", "converged", "infeasible",
    "unresolved", "by_phase_tx", "by_type_tx",
)


class ContractError(RuntimeError):
    """Varyant sözleşmeyi tutmuyor. SESSİZ VARSAYILAN YOK: yüksek sesle patlar.

    Eksik alanı 0 ya da None ile doldurmak, ölçülmemiş bir şeyi ölçülmüş gibi
    CSV'ye yazmak olurdu; bütün özet ondan türetiliyor.
    """


@dataclass(frozen=True)
class RunRequest:
    """Koşucunun varyanta verdiği her şey. Varyant başka hiçbir şey almaz."""

    edges: Tuple[Edge, ...]
    weights: Mapping[int, float]
    k: int
    scheduler: str            # "sync" | "async"
    seed: int
    max_ms: int
    loss: float = 0.0
    mis_nbrs_max: int = 32
    """HELLO'da taşınabilecek en çok MIS komşusu (BootstrapParams aynı adla).

    BU BİR ÜST SINIRDIR, dayatılan bir boyut DEĞİL: HELLO gerçekten
    13 + 2·|mis_nbrs| bayttır, dolayısıyla sınırı yükseltmek ölçülen yükü
    BÜYÜTMEZ, yalnız izin verir. Varsayılan 5 (UDG, G8) kıyas kümesinde
    ÇALIŞMIYOR: n=100/m=400'de düğüm 6 MIS komşusu görüp `ValueError` atıyor
    (ölçüldü). BULGU 3 kıyas kümesinde en büyüğünü 17 ölçmüş; 32 bol pay
    bırakır ve HELLO'yu en kötü 77 bayta çıkarır, yani 250 B'nin çok altında.
    """


@dataclass(frozen=True)
class VariantSpec:
    """Bir deney kolu.

    `family`  : "bb" | "dfs" | "anneal" ... aynı aileden olmayan kollar
                eşleşmiş çift kuramaz, yalnız çapraz kıyasta görünür.
    `phase1`  : Faz 1'in yerine ne konduğu ("mis", "mst", "wuli", "dfs", "anneal").
    `phase5`  : "local" (5a) | "tree" (5b).
    `run`     : RunRequest -> REQUIRED_RESULT_FIELDS taşıyan nesne.
    `anytime` : koşum `trace` (AnytimeTrace) döndürüyor mu; Anneal için True.
    """

    name: str
    family: str
    phase1: str
    phase5: str
    run: Callable[[RunRequest], Any]
    schedulers: Tuple[str, ...] = ("sync", "async")
    anytime: bool = False

    def axis(self, name: str) -> str:
        if name == "phase1":
            return self.phase1
        if name == "phase5":
            return self.phase5
        raise KeyError(name)


# ---- Anneal-Local'ın anytime izi: ayrı ve KATI bir sözleşme -------------------
@dataclass(frozen=True)
class AnytimeSample:
    """Bir andaki durum. İKİ ağırlık taşır ve ikisi FARKLI şeylerdir.

    `observer_best_weight` — o ana kadar GÖRÜLEN en iyi geçerli çözümün
    ağırlığı; monoton azalır. Adı bilerek uzun: bu bir GÖZLEMCİ büyüklüğüdür,
    ağın kendisi hakkında söyleyebileceği bir şey DEĞİL. Geçerlilik örtü +
    bağlılık + kapasite demektir ve üçü de 1-atlama durumundan bilinemez;
    örnekleyici bunu küresel bilgiyle hesaplar. Ağın kendi en iyisini gerçekten
    raporlaması için periyodik bir convergecast (Faz 5b TREE/STABLE) gerekir ve
    onun `tx` maliyeti bu sayılarda YOKTUR. Bu proje, eski MWCCVC-MININET kodu
    dağıtık olmadığı ve cevabı küresel çizgeden kurduğu için var; küresel
    hesaplanmış bir "en iyi"yi Anneal'ın sonucu diye yayımlamak aynı hatayı bizim
    adımızla yapmak olurdu.

    `current_weight` — O ANKİ durumun ağırlığı, geçersizse None. Monoton
    DEĞİLDİR ve olmamalıdır: Metropolis yokuş yukarı hamle kabul eder, son
    durum ziyaret edilen en iyi durum değil bir yerel minimumdur. 60 tohumda
    29'unda son durum görülen en iyiden KÖTÜDÜR (ortalama fark 2,17, en çok
    8,0), yani zarf ile bitiş noktası tohumların yarısında ayrışıyor. Bu
    sapmalar gürültü değil MEKANİZMADIR; gizleyen bir şekil, gösterdiği farkın
    açıklamasını da silmiş olur.

    Raporlanan sayı SON DONMUŞ DURUMdur (`total_weight`), zarf değil.
    """

    t_ms: int
    energy_mah: float
    tx: int
    observer_best_weight: Optional[float]
    cover_size: Optional[int]
    current_weight: Optional[float] = None

    @property
    def valid(self) -> bool:
        return self.observer_best_weight is not None


@dataclass
class AnytimeTrace:
    variant: str
    samples: List[AnytimeSample]

    #: Şekil altyazısına AYNEN girmesi gereken uyarı. Kodda alanın yanında
    #: durur, çünkü yorumda yazılan bir uyarı tabloya asla kopyalanmıyor.
    OBSERVER_LABEL = ("gözlemci sınırı: küresel bilgiyle hesaplanmıştır, ağ "
                      "kendi en iyisini sayılmayan bir convergecast olmadan "
                      "bildiremez")

    @property
    def t_first_valid_ms(self) -> Optional[int]:
        for s in self.samples:
            if s.valid:
                return s.t_ms
        return None

    def check(self) -> None:
        """İzin KENDİ tutarlılığı. Bozuksa şekil çizilmez, hata yükselir."""
        if not self.samples:
            raise ContractError(f"{self.variant}: boş anytime izi")
        ts = [s.t_ms for s in self.samples]
        if ts != sorted(ts):
            raise ContractError(f"{self.variant}: örnekler zaman sırasında değil")
        en = [s.energy_mah for s in self.samples]
        if en != sorted(en):
            raise ContractError(f"{self.variant}: enerji azalıyor; birikimli olmalı")
        best = [s.observer_best_weight for s in self.samples if s.valid]
        if best != sorted(best, reverse=True):
            raise ContractError(
                f"{self.variant}: 'o ana kadarki en iyi' ağırlık artıyor; "
                "anytime sözleşmesi bunu yasaklar"
            )


@dataclass
class VariantResult:
    """Sözleşmeyi tutan, koşucunun okuduğu biçim."""

    cover: List[int]
    owner: Dict[Edge, int]
    total_weight: float
    tx: int
    rx: int
    retx: int
    bytes_tx: int
    max_payload: int
    slots: Optional[int]
    t_conv_ms: Optional[int]
    converged: bool
    infeasible: bool
    unresolved: bool
    by_phase_tx: Dict[int, int]
    by_type_tx: Dict[int, int]
    verdict: str = ""
    """KOŞUMUN hükmü: "solved" | "unresolved" | "truncated" (bb-algo).

    BAYRAKLARIN YOKLUĞUNDAN başarı ÇIKARILAMAZ ve bu ölçüldü: duvar bütçesi
    bağladığında hiçbir düğüm henüz pes etmemiştir, dolayısıyla
    `infeasible=False, unresolved=False` olur. Çalışan örnekte max_ms=2000 ile
    |C|=3, SIFIR sahiplik ve KOPUK bir örtü dönüyor, iki bayrak da temiz;
    yalnız `converged=False` bunu söylüyor, ki unutulan alan tam olarak odur.

    Boş dizge = varyant bildirmiyor; o zaman `converged`den türetilir.
    """
    truncated: bool = False
    infeasible_reason: str = ""
    backbone: Tuple[int, ...] = ()
    trace: Optional[AnytimeTrace] = None
    notes: Tuple[str, ...] = ()
    params: Dict[str, int] = dataclass_field(default_factory=dict)
    """Koşumun GERÇEKTEN kullandığı maliyet parametreleri.

    İstenen değeri değil kullanılanı yazmak şart: `push_ttl_max` eskiden 8'di ve
    ekip lideri ölçtü, aynı doğru yanıt için 4085 slot / 218632 iletim yerine
    1310 / 65690 veriyor. Yani bu tek sayı bütün maliyet sütunlarını ~3 kat
    şişirebiliyor. CSV hangi değerle ölçüldüğünü taşımazsa, iki süpürmenin
    maliyet sayıları sessizce kıyaslanamaz hale gelir.
    """


def adapt_result(obj: Any, *, variant: str) -> VariantResult:
    """Varyantın döndürdüğünü sözleşmeye çevir; EKSİK ALAN HATADIR."""
    missing = [f for f in REQUIRED_RESULT_FIELDS if not hasattr(obj, f)]
    if missing:
        raise ContractError(
            f"{variant}: sonuç sözleşmeyi tutmuyor, eksik alanlar {missing}. "
            f"Zorunlu alanlar: {list(REQUIRED_RESULT_FIELDS)}"
        )
    backbone: Tuple[int, ...] = tuple(getattr(obj, "backbone", ()) or ())
    if not backbone:
        nodes = getattr(obj, "nodes", None)
        if isinstance(nodes, dict):
            backbone = tuple(sorted(
                nid for nid, nd in nodes.items()
                if getattr(getattr(nd, "role", None), "in_backbone", False)))
    params: Dict[str, int] = {}
    nodes_obj = getattr(obj, "nodes", None)
    if isinstance(nodes_obj, dict) and nodes_obj:
        p = getattr(next(iter(nodes_obj.values())), "p", None)
        for fname in ("push_ttl", "push_ttl_max", "mis_nbrs_max", "quiet_periods",
                      "ack_max_attempts", "nbr_table_max"):
            val = getattr(p, fname, None)
            if isinstance(val, int):
                params[fname] = val
    verdict = str(getattr(obj, "verdict", "") or "")
    if verdict and verdict not in ("solved", "unresolved", "truncated"):
        raise ContractError(
            f"{variant}: bilinmeyen verdict {verdict!r}; "
            "'solved' | 'unresolved' | 'truncated' olmalı")
    trace = getattr(obj, "trace", None)
    if trace is not None:
        if not isinstance(trace, AnytimeTrace):
            raise ContractError(f"{variant}: trace AnytimeTrace olmalı, {type(trace)}")
        trace.check()
    return VariantResult(
        cover=sorted(int(v) for v in obj.cover),
        owner={(int(u), int(v)) if u <= v else (int(v), int(u)): int(o)
               for (u, v), o in dict(obj.owner).items()},
        total_weight=float(obj.total_weight),
        tx=int(obj.tx), rx=int(obj.rx), retx=int(obj.retx),
        bytes_tx=int(obj.bytes_tx), max_payload=int(obj.max_payload),
        slots=None if obj.slots is None else int(obj.slots),
        t_conv_ms=None if obj.t_conv_ms is None else int(obj.t_conv_ms),
        converged=bool(obj.converged), infeasible=bool(obj.infeasible),
        unresolved=bool(obj.unresolved),
        by_phase_tx={int(a): int(b) for a, b in dict(obj.by_phase_tx).items()},
        by_type_tx={int(a): int(b) for a, b in dict(obj.by_type_tx).items()},
        verdict=verdict,
        truncated=bool(getattr(obj, "truncated", not bool(obj.converged))),
        infeasible_reason=str(getattr(obj, "infeasible_reason", "") or ""),
        backbone=backbone, trace=trace, params=params,
        notes=tuple(getattr(obj, "notes", ()) or ()),
    )


# ==========================================================================
# 2. Varyant keşfi
# ==========================================================================
def builtin_variants() -> List[VariantSpec]:
    """Her zaman var olan iki kol: BB-CVC'nin 5a ve 5b sürümleri.

    `enable_tree` dışında TEK SATIR fark yoktur, dolayısıyla ikisi `phase5`
    ekseninde eşleşmiş bir çifttir ve eşleşme testi bunu kullanır.
    """
    from ccvc.bb.bbcvc import BbcvcParams, run_bbcvc

    def _make(tree: bool):
        def run(req: RunRequest):
            return run_bbcvc(list(req.edges), dict(req.weights), req.k,
                             scheduler=req.scheduler, max_ms=req.max_ms,
                             loss=req.loss, seed=req.seed,
                             params=BbcvcParams(enable_tree=tree,
                                                mis_nbrs_max=req.mis_nbrs_max))
        return run

    return [
        VariantSpec("MIS-Connector-Backbone", "bb", "mis", "local", _make(False)),
        VariantSpec("MIS-Connector-TreeAgg", "bb", "mis", "tree", _make(True)),
    ]


#: Bir varyant bildiriminde BULUNMASI gereken alanlar.
_SPEC_ATTRS: Tuple[str, ...] = ("name", "family", "phase1", "phase5", "run",
                                "schedulers")


def _check_spec(obj: Any, where: str) -> None:
    """Varyant bildirimi YAPISAL olarak denetlenir, `isinstance` ile DEĞİL.

    `isinstance` burada yanlış araç ve bu ölçüldü: `python -m ccvc.bb.sweep`
    modülü `__main__` adıyla ikinci kez yükler, dolayısıyla `__main__.VariantSpec`
    ile varyantın import ettiği `ccvc.bb.sweep.VariantSpec` FARKLI sınıf
    nesneleridir ve kontrol, tamamen doğru bir bildirimi

        BB_VARIANTS içinde VariantSpec değil: <class 'ccvc.bb.sweep.VariantSpec'>

    diye reddeder. Hata metninin kendisi saçmalıyordu, çünkü iki sınıfın adı
    aynı. `__main__` artık gerçek modüle devrediyor (dosyanın sonuna bak), ama
    kontrol yine de yapısal: aynı tuzak `importlib.reload` ve ayrı sys.path
    girişleriyle de kurulabilir ve varyant yazarının bunu teşhis etmesi için
    hiçbir sebep yok.
    """
    missing = [a for a in _SPEC_ATTRS if not hasattr(obj, a)]
    if missing:
        raise ContractError(
            f"{where}: BB_VARIANTS girdisi varyant bildirimi değil "
            f"({type(obj).__name__}), eksik alanlar {missing}. "
            f"Zorunlu alanlar: {list(_SPEC_ATTRS)}")
    if not callable(getattr(obj, "run")):
        raise ContractError(f"{where}: {obj.name}.run çağrılabilir değil")
    for ax in ("phase1", "phase5"):
        if not isinstance(getattr(obj, ax), str):
            raise ContractError(f"{where}: {obj.name}.{ax} metin olmalı "
                                "(eşleşmiş kıyas ekseni)")


def discover(extra: Sequence[VariantSpec] = (), *,
             strict: bool = False) -> List[VariantSpec]:
    """Yerleşik kollar + `VARIANT_MODULES` içinde bulunanlar.

    Bulunamayan modül normalde SESSİZCE atlanır, çünkü varyantlar sırayla
    yazılıyor ve koşucunun onlardan önce var olması gerekiyor. `strict=True`
    ile eksik modül hata olur; sürüm koşusunda bu kullanılır.
    """
    specs: List[VariantSpec] = list(builtin_variants())
    for mod_name in VARIANT_MODULES:
        try:
            mod = __import__(mod_name, fromlist=["BB_VARIANTS"])
        except ImportError as exc:
            if strict:
                raise ContractError(f"{mod_name} bulunamadı: {exc}") from exc
            continue
        found = getattr(mod, "BB_VARIANTS", None)
        if not found:
            if strict:
                raise ContractError(f"{mod_name}: BB_VARIANTS yok ya da boş")
            continue
        for s in found:
            _check_spec(s, mod_name)
            specs.append(s)
    specs.extend(extra)
    names = [s.name for s in specs]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ContractError(f"varyant adı çakışması: {dupes}")
    return specs


# ==========================================================================
# 3. Satır — CSV ŞEMASI. Alan sırası CSV sütun sırasıdır.
# ==========================================================================
#: `status` tek bir ETİKETTİR ve kayıplıdır: bir koşum hem `unresolved` hem
#: `not_converged` olabilir. Bu yüzden üç bayrak da AYRI sütun olarak durur ve
#: özet onları kullanır; `status` yalnız okunabilirlik içindir.
#:
#: Öncelik (yukarıdan aşağı): koşum çöktü > komşu tablosu taştı > uygunsuz >
#: sahiplik çözülemedi > sükûnete ermedi > doğrulama kapısı düştü > tamam.
#: `unresolved` bilerek `gate_fail`in ÜSTÜNDE: çözülemeyen taşkın zaten
#: doğrulayıcıda taşkın olarak görünür, ve o satırın `gate_fail` diye
#: etiketlenmesi "başarısızlık veridir" kuralını görünmez kılardı.
STATUS_ORDER: Tuple[str, ...] = (
    "bad_input", "error", "invalid", "truncated", "infeasible", "unresolved",
    "contradiction", "ok",
)
#: `contradiction`: kol BAŞARI İDDİA ETTİ (hiçbir bayrak kalkmadı, sükûnete
#: erdi) ama DOĞRULAYICI ihlal buldu. Eski adı `gate_fail`di ve adı yaptığı işi
#: söylemiyordu: bir kapının düşmesi ile bir kolun yanlış beyanı aynı şey değil.
#: Bu satır sessizce geçerli bir sonuç gibi okunamamalı, çünkü ortalamalara
#: girseydi hiçbir sütunda başarısızlık gibi görünmezdi.


@dataclass
class Row:
    # -- kimlik
    source: str              # "dataset" | "synthetic"
    group: str
    n: int
    ratio: int
    m: int
    seed: int
    instance: str
    variant: str
    family: str
    phase1: str
    phase5: str
    scheduler: str
    k: int
    loss: float
    graph_connected: bool    # brief §1 G'nin BAĞLI olduğunu varsayar; değilse satır kaydedilmez
    code_fingerprint: str    # satırın ölçüldüğü kod sürümü; karışık CSV'yi görünür kılar
    counting_bound_infeasible: bool
    """m > n·k, yani uygunsuzluk UCUZCA kanıtlanabilir.

    `instance_feasible == "no"` ile aynı şey DEĞİLDİR. Akış, sayma sınırının
    yakalayamadığı uygunsuzlukları da bulur; sayma sınırı bilerek dardır ve
    yalnız dejenere sınıfı yakalar. Ayrım `missed_infeasible` için belirleyici:
    ucuzca kanıtlanabilir bir örnekte uygunsuzluğu bildirmemek KOL KUSURUDUR,
    ama yalnız akışla görülebilen bir örnekte bildirmemek kusur değildir,
    çünkü bugünkü HELLO ile sağlam bir yerel tanık hesaplanamıyor (bb-algo).
    """
    trace_agrees: str        # anytime izi ile çözüm aynı şeyi mi söylüyor: "yes"|"no:..."|"none"
    verdict_agrees: str      # kolun kendi beyanı ile doğrulayıcının kararı: "yes"|"no:..."
    instance_feasible: str   # "yes" | "no" | "unknown:<neden>" (bkz. instance_feasibility)
    relabelled: bool         # 0 tabanlı etiketler 1..n'e taşındı mı (bkz. prepare)
    weight_scale: int        # ağırlık nicemleme ölçeği
    weight_rel_error: float  # nicemlemenin soktuğu en büyük bağıl hata
    mis_nbrs_max: int        # HELLO'daki MIS komşusu üst sınırı (yük ölçümünü SANSÜRLEYEBİLİR)
    push_ttl_max: int        # Faz 4 PUSH derinlik tavanı; maliyeti ~3 kat değiştirir
    payload_at_cap: bool     # ölçülen max_payload tam sınıra oturdu mu -> ölçüm sansürlü
    # -- sonuç
    status: str
    verdict: str             # koşumun hükmü (bb-algo): solved|unresolved|truncated
    truncated: bool          # duvar bütçesi bağladı mı; bağladıysa sayılar kesiktir
    infeasible_reason: str   # "" | "counting_bound" | "node"
    converged: bool
    infeasible: bool
    unresolved: bool
    valid: bool
    vertex_cover: bool
    connected: bool
    capacity: bool
    violations: int
    violation_kinds: str
    # -- çözüm
    cover_size: Optional[int]
    total_weight: Optional[float]
    lower_bound_g6: int
    backbone_size: Optional[int]
    backbone_weight: Optional[float]
    # -- maliyet (BAŞARISIZ SATIRLARDA DA DOLU)
    slots: Optional[int]
    t_conv_ms: Optional[int]
    tx: Optional[int]
    rx: Optional[int]
    retx: Optional[int]
    bytes_tx: Optional[int]
    max_payload: Optional[int]
    hello_tx: Optional[int]
    # -- referans
    exact_weight: Optional[float]
    exact_status: str
    # -- meta
    seeds_in_cell: int
    seconds: float
    detail: str = ""
    # -- dagilim: ORTALAMA DEGIL MAKSIMUM da verilir, cunku pilin once bittigi
    #    dugum ortalama degil en yuklu olandir
    cover_components: Optional[int] = None
    owner_load_max: Optional[int] = None
    owner_load_mean: Optional[float] = None
    nodes_at_capacity: Optional[int] = None
    tx_per_node_max: Optional[int] = None
    tx_per_node_mean: Optional[float] = None
    #: Yalniz RADYO terimi. Tam enerji tahmini /proc'tan CPU zamani ister ve
    #: simulatorde surec olmadigi icin uretilemez; adi bu yuzden "proxy".
    radio_activity_mJ_proxy: Optional[float] = None
    energy_model_version: str = ""


    @property
    def cell_key(self) -> Tuple[str, int, int, int]:
        return (self.source, self.n, self.m, self.k)

    @property
    def instance_key(self) -> Tuple[str, int, int, int, int]:
        return (self.source, self.n, self.m, self.k, self.seed)

    @property
    def arm(self) -> str:
        return f"{self.variant}/{self.scheduler}"

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


CSV_FIELDS: Tuple[str, ...] = tuple(Row.__annotations__.keys())


# ==========================================================================
# 4. Örnek kaynağı
# ==========================================================================
#: Ağırlık ölçeği. Kıyas kümesinin ağırlıkları GERÇEK SAYI (ör. 76,168), düğüm
#: kodu ise tamsayı ister (brief §3.6: ESP32-C3'te FPU yok). Ölçekleyip
#: yuvarlamak ÖRNEĞİ DEĞİŞTİRİR, dolayısıyla üç şey birden yapılır: ölçek
#: satıra yazılır, bağıl hata ölçülür, ve kesin çözücü de AYNI nicemlenmiş
#: ağırlıklarla koşar. Aksi halde oran iki farklı problemin oranı olurdu.
DEFAULT_WEIGHT_SCALE = 10

#: 16.16 sabit noktalı anahtar int32'ye sığmalı: key = w/(deg+1) <= 32767.
MAX_FIXED_POINT_WEIGHT = (2 ** 31 - 1) // (1 << 16)


@dataclass(frozen=True)
class Adaptation:
    """Örneği düğüm koduna sokmak için yapılan ve SAKLANMAYAN dönüşümler."""

    relabelled: bool          # 0 tabanlı etiketler 1..n'e taşındı mı
    weight_scale: int
    weight_rel_error: float   # nicemlemenin soktuğu en büyük bağıl hata


def prepare(weights: Mapping[int, float], edges: Sequence[Edge], *,
            weight_scale: int = DEFAULT_WEIGHT_SCALE
            ) -> Tuple[Dict[int, float], List[Edge], Adaptation]:
    """Kıyas örneğini düğüm kodunun kabul ettiği biçime getir.

    İKİ GERÇEK UYUMSUZLUK, ikisi de ölçüldü:

    1. **Etiketler 0 tabanlı.** `bbcvc.mac_for_id(0)` hash16 ön görüntüsü
       bulamıyor ve ~24 saniye tarayıp `RuntimeError` atıyor. Düğüm etiketi
       problemin parçası değil, dolayısıyla 1..n'e taşımak bilgi kaybetmez;
       ama satırda `relabelled` olarak GÖRÜNÜR.
    2. **Ağırlıklar gerçek sayı.** Düğüm tamsayı ister. Ölçekleyip yuvarlamak
       amacı değiştirir; bu yüzden ölçek ve ölçülen bağıl hata satıra yazılır
       ve referans çözücü de aynı nicemlenmiş örneği görür.
    """
    order = sorted(weights)
    relabel = order != list(range(1, len(order) + 1))
    idx = {old_id: i + 1 for i, old_id in enumerate(order)}
    err = 0.0
    out: Dict[int, float] = {}
    for old_id in order:
        w = float(weights[old_id])
        q = max(1, int(round(w * weight_scale)))
        out[idx[old_id]] = float(q)
        if w > 0:
            err = max(err, abs(q / weight_scale - w) / w)
    if out and max(out.values()) > MAX_FIXED_POINT_WEIGHT:
        raise ContractError(
            f"nicemlenmiş ağırlık {max(out.values()):g} > {MAX_FIXED_POINT_WEIGHT}; "
            f"16.16 anahtarı int32'ye sığmaz, weight_scale küçültülmeli")
    new_edges = sorted({(idx[u], idx[v]) if idx[u] <= idx[v] else (idx[v], idx[u])
                        for u, v in edges})
    return out, new_edges, Adaptation(relabel, weight_scale, round(err, 6))


@dataclass(frozen=True)
class Instance:
    source: str
    cell: Cell
    seed: int
    path: str
    edges: Tuple[Edge, ...]
    weights: Mapping[int, float]
    seeds_in_cell: int
    adaptation: Adaptation = Adaptation(False, 1, 0.0)


def dataset_instances(cells: Sequence[Cell], *, max_seeds: Optional[int] = None,
                      directory: Optional[str] = None,
                      weight_scale: int = DEFAULT_WEIGHT_SCALE) -> List[Instance]:
    """Kıyas kümesinden örnekler. Veri kümesi yoksa BOŞ döner, uydurmaz."""
    d = directory or matrix.dataset_dir()
    if d is None:
        return []
    out: List[Instance] = []
    for cell in cells:
        seeds = matrix.seeds_available(cell, d)
        for seed in (seeds if max_seeds is None else seeds[:max_seeds]):
            path = matrix.instance_path(cell, seed, d)
            if not path:
                continue
            raw_w, raw_e = matrix.load_instance(path)
            w, e, adapt = prepare(raw_w, raw_e, weight_scale=weight_scale)
            out.append(Instance("dataset", cell, seed, path, tuple(e), w,
                                len(seeds), adapt))
    return out


def synthetic_instance(cell: Cell, seed: int) -> Instance:
    """Testler ve duman koşuları için üretilmiş bağlı çizge.

    `source="synthetic"` sütunuyla İŞARETLENİR; kıyas sonucu gibi okunamaz.
    """
    import random as _random

    rng = _random.Random(seed * 1_000_003 + cell.n * 31 + cell.m)
    nodes = list(range(1, cell.n + 1))
    rng.shuffle(nodes)
    edges: Set[Edge] = set()
    for i in range(1, len(nodes)):              # önce omurga ağacı: bağlılık garanti
        u, v = nodes[i], nodes[rng.randrange(i)]
        edges.add((u, v) if u < v else (v, u))
    target = min(cell.m, cell.max_edges)
    guard = 0
    while len(edges) < target and guard < 200 * target:
        guard += 1
        u, v = rng.sample(nodes, 2)
        edges.add((u, v) if u < v else (v, u))
    weights = {i: float(rng.randint(1, 9)) for i in range(1, cell.n + 1)}
    return Instance("synthetic", cell, seed, f"synthetic:{cell.stem}_s{seed}",
                    tuple(sorted(edges)), weights, 0,
                    Adaptation(False, 1, 0.0))


# ==========================================================================
# 5. Tek koşum
# ==========================================================================
@dataclass
class SweepOptions:
    k: int = 4
    loss: float = 0.0
    max_ms: int = 600_000
    connectivity: str = validate.STRICT
    mis_nbrs_max: int = 32
    require_connected: bool = True
    """Kopuk girdi çizgesinde satır KAYDEDİLMESİN mi (brief §1).

    Varsayılan True ve öyle kalmalı: kopuk çizgede ölçülen sayı farklı bir
    çizge POPÜLASYONUNDAN gelir, dolayısıyla bağlı çizge satırlarıyla aynı
    ortalamaya girerse kollar farklı popülasyonlar üstünde kıyaslanmış olur.
    Bileşen bazlı ölçüm bilinçli bir karardır ve `connectivity` ile birlikte
    açıkça istenir.
    """
    exact_max_n: int = 18
    exact_time_limit_s: float = 5.0
    feasibility_max_n: int = 200
    time_budget_s: Optional[float] = None


def _exact_reference(edges: Sequence[Edge], weights: Mapping[int, float], k: int,
                     opts: SweepOptions) -> Tuple[Optional[float], str]:
    """Küçük örneklerde optimum gerçeği. Koşamıyorsa NEDENİ döner, sessizlik değil."""
    if len(weights) > opts.exact_max_n:
        return None, f"skipped:n>{opts.exact_max_n}"
    try:
        from ccvc import central
        g = validate.make_graph(list(edges), k, dict(weights))
        r = central.solve_exact(g, max_n=opts.exact_max_n,
                                time_limit_s=opts.exact_time_limit_s, strict=False)
    except Exception as exc:                      # noqa: BLE001 - nedeni satıra yazılır
        return None, f"error:{type(exc).__name__}"
    if not getattr(r, "feasible", True):
        return None, "infeasible"
    if getattr(r, "timed_out", False):
        return None, "timed_out"
    cover = list(getattr(r, "cover", []) or [])
    return round(sum(float(weights[v]) for v in cover), 6), "ok"


def code_fingerprint() -> str:
    """Koşumun karşısında koştuğu KODUN parmak izi (bb paketinin dosya imzası).

    Bir süpürme 20 dakika sürüyor ve depo canlı: bir takım arkadaşı ortasında
    yama geçirdiğinde CSV, İKİ FARKLI KOD SÜRÜMÜNDEN ölçülmüş satırları aynı
    tabloda toplar ve bunu hiçbir sütun söylemez. Bugün tam olarak bu oldu:
    süpürme sırasında `unresolved` temizleme yaması indi, bitmiş CSV hâlâ üç
    uyuşmazlık gösteriyordu, oysa aynı örnek tek başına koşturulunca temizdi.

    Parmak izi mtime+boyuta dayanır, içeriğe değil: amaç kriptografik bütünlük
    değil, "bu satırlar aynı koddan mı" sorusunun ucuz ve kesin yanıtı.
    """
    import hashlib
    import pathlib

    here = pathlib.Path(__file__).parent
    h = hashlib.sha256()
    for f in sorted(here.glob("*.py")):
        if f.name.startswith("test_"):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        h.update(f"{f.name}:{st.st_mtime_ns}:{st.st_size};".encode())
    return h.hexdigest()[:12]


def is_connected(nodes: Sequence[int], edges: Sequence[Edge]) -> bool:
    """Girdi çizgesi TEK parça mı (brief §1'in varsayımı)."""
    adj: Dict[int, List[int]] = {v: [] for v in nodes}
    for u, v in edges:
        if u in adj and v in adj:
            adj[u].append(v)
            adj[v].append(u)
    if not adj:
        return False
    start = next(iter(adj))
    seen, stack = {start}, [start]
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return len(seen) == len(adj)


def _hello_sizes(n_mis: int) -> Set[int]:
    """Sınıra oturmuş HELLO'nun olabilecek boyları.

    Anneal-Local HELLO'ya 8 baytlık bir kuyruk takıyor, dolayısıyla "sınırdaki
    HELLO" tek bir sayı değil; iki biçim de sansür işareti sayılır.
    """
    from ccvc.bb import wire
    return {wire.hello_size(n_mis), wire.hello_size(n_mis) + wire.ANNEAL_BYTES}


def _verdict_of(res: VariantResult) -> str:
    """Koşumun hükmü. Varyant bildirmiyorsa `converged`den TÜRETİLİR.

    Türetme tahmin değil: `converged=False` duvar bütçesinin bağladığı TEK
    durumdur, dolayısıyla "truncated" kesindir. Ayırt edemediği şey
    solved/unresolved ayrımıdır ve onu `unresolved` bayrağı zaten söyler.
    """
    if res.verdict:
        return res.verdict
    if not res.converged:
        return "truncated"
    return "unresolved" if res.unresolved else "solved"


def _verdict_agreement(res: VariantResult, rep: Any) -> str:
    """Kolun KENDİ BEYANI ile doğrulayıcının kararı aynı şeyi mi söylüyor.

    `status` zaten doğrulayıcıdan TÜRETİLİR (bayraklar temizken ihlal varsa
    satır `ok` olamaz), dolayısıyla yanlış bir "başarı" CSV'ye giremez. Ama
    `status` tek bir etikettir ve İKİ FARKLI kusuru ayırt etmez:

      * kol "başardım" dedi, doğrulayıcı ihlal buldu  -> TEHLİKELİ yön;
        ortalamalara girseydi hiçbir sütunda başarısızlık gibi görünmezdi.
      * kol "çözemedim/uygunsuz" dedi, doğrulayıcı temiz -> ters yön; kol
        kendi başarısını göremiyor, ki bu da bir tespit kusuru.

    İkisi de burada AYRI AYRI kayda geçer, çünkü ekip lideri ilkini elle
    yakaladı (K6, k=2: n·k=12 < m=15 iken kol başarı bildiriyordu) ve elle
    yakalanan şey bir dahaki sefere yakalanmayabilir.
    """
    # Kesik koşum başarı İDDİA ETMEZ; onu çelişki saymak, gerçek yanlış
    # beyanları gürültüye gömerdi.
    verdict = _verdict_of(res)
    # ÜÇÜNCÜ bir çelişki biçimi: `verdict` ile bayraklar birbiriyle çelişiyor.
    # bb-algo'nun kodunda bu olamaz (verdict oradan türetiliyor ve testle
    # sabitlenmiş), ama koşucu her varyanta açık ve "solved" diyen bir kolun
    # aynı anda pes etmiş olması sessizce geçilmemeli.
    if verdict == "solved" and (res.unresolved or res.infeasible):
        bad = "+".join(n for n, v in (("unresolved", res.unresolved),
                                      ("infeasible", res.infeasible)) if v)
        return f"no:verdict='solved' ama {bad} bayrağı da kalkmış"
    claims_ok = (verdict == "solved" and not res.infeasible)
    valid = bool(getattr(rep, "valid", False))
    if claims_ok and not valid:
        kinds = sorted({v.kind for v in getattr(rep, "violations", [])})
        return (f"no:kol başarı bildirdi, doğrulayıcı "
                f"{len(rep.violations)} ihlal buldu ({'|'.join(kinds)})")
    if verdict == "truncated":
        # Kesilmiş bir koşum elinde geçerli bir örtü tutuyor olabilir; bu bir
        # tespit kusuru DEĞİL, yalnız bütçenin erken bağlamasıdır. Çelişki
        # saymak sütunu her kısa bütçede ateşlerdi ve gerçek yanlış beyanları
        # gürültüye gömerdi (ölçüldü: max_ms=4000'de geçerli örtü + kesinti).
        return "yes"
    if not claims_ok and valid:
        flags = [n for n, v in (("infeasible", res.infeasible),
                                ("unresolved", res.unresolved)) if v]
        return (f"no:kol {'+'.join(flags) or 'başarısızlık'} bildirdi, "
                "doğrulayıcı temiz")
    return "yes"



def _distribution_metrics(res, inst, k: int) -> Dict[str, object]:
    """Per-node spread and the radio proxy: the numbers an AVERAGE hides.

    A mean is the wrong summary for a battery-powered network. The node that
    runs out first is the MAXIMUM, not the average, so ownership load and
    per-node traffic are reported as max AND mean and never as one number.

    `cover_components` is recorded even though `connected` already says
    whether it is 1, because "disconnected" and "disconnected into seven
    pieces" call for different conclusions and the boolean cannot tell them
    apart.

    ENERGY IS DELIBERATELY NOT REPORTED HERE. `ccvc.bb.energy` estimates a
    station's energy from its CPU time in /proc, and a simulator run has no
    process, so the estimate is UNAVAILABLE rather than zero. What the
    simulator does measure is traffic, so only the radio term is derived, and
    it is named a proxy so that it is never read as total energy.
    """
    from ccvc.bb.energy import EnergyCoefficients

    adj: Dict[int, set] = {v: set() for v in inst.weights}
    for u, v in inst.edges:
        adj[u].add(v)
        adj[v].add(u)
    cover = set(res.cover)
    seen: set = set()
    comps = 0
    for start in sorted(cover):
        if start in seen:
            continue
        comps += 1
        stack = [start]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend((adj[x] & cover) - seen)

    load = Counter(res.owner.values())
    loads = [load.get(v, 0) for v in cover] or [0]
    coeff = EnergyCoefficients()
    radio = (res.bytes_tx * coeff.tx_cost_mJ_per_byte
             + res.rx * coeff.rx_cost_mJ_per_delivery
             + res.retx * coeff.retx_cost_mJ)

    per_node_tx = getattr(res, "tx_by_node", None)
    tx_max = max(per_node_tx.values()) if per_node_tx else None
    tx_mean = (sum(per_node_tx.values()) / len(per_node_tx)) if per_node_tx else None

    return dict(
        cover_components=comps,
        owner_load_max=max(loads),
        owner_load_mean=round(sum(loads) / len(loads), 4),
        nodes_at_capacity=sum(1 for x in loads if x >= k),
        tx_per_node_max=tx_max,
        tx_per_node_mean=None if tx_mean is None else round(tx_mean, 4),
        radio_activity_mJ_proxy=round(radio, 6),
        energy_model_version="mnwifi-proc-v1 (radio term only)",
    )


def _trace_agreement(res: VariantResult, feasible: str = "") -> str:
    """Anytime izi ile çözüm AYNI koşumun iki görünümüdür; çelişirlerse söyle.

    İz "elimde geçerli bir örtü var" derken koşum boş örtü raporlarsa, biri
    yanlıştır ve hangisi olduğu tek başına HİÇBİR çıktıdan görünmez: şekil 8
    yalnız ize bakar ve sapasağlam görünür, CSV yalnız çözüme bakar ve
    algoritma hiçbir şey örtmemiş gibi okunur. Ölçüldü (Anneal-Local, 195/195
    satır): iz Σw=5328 ile 10 düğümlük bir örtü bildirirken koşum `cover=[]`
    döndürüyordu.

    KIYASLANAN BÜYÜKLÜK AĞIRLIKTIR, ÖRTÜ BOYU DEĞİL. İlk yazdığım hâli
    `cover_size`ı kıyaslıyordu ve YANLIŞTI (bb-core ölçtü): zarf AĞIRLIĞI
    enküçültür, ağırlık ile boy ise birlikte artmaz. Ölçülen karşı örnek,
    n=10 m=20 tohum 4 async: zarf |C|=6 ve Σw=2821 iken son durum |C|=7 ve
    Σw=4045 — daha AZ düğüm VE daha az ağırlık. Boy kıyası bunu çelişki
    sayıyordu; oysa sözleşmenin söz verdiği ağırlık sıralaması tam olarak
    tutuyor.

    UYGUNSUZ ÖRNEKTE ÇELİŞKİ YOKTUR. Geçerli çözümü olmayan bir örnekte izin
    hiç geçerli durum görmemesi ile koşumun son (geçersiz) yapılandırmayı
    döndürmesi birbiriyle TAM UYUMLUDUR; ikisi de doğrudur. Bunu "çelişki"
    saymak, bir sorunun çözümü olmadığını doğru bildiren kolu bozuk gösterirdi
    ve daha kötüsü: rutin olarak beklenen uyuşmazlık bildiren bir çapraz
    denetim göz atılıp geçilir, gerçek olan da içinde saklanır. Ayrı bir
    değer alır ve uyuşmazlık sayılmaz.
    """
    t = res.trace
    if t is None:
        return "none"
    valid = [s for s in t.samples if s.valid]
    if feasible == "no":
        return "n/a:örnek uygunsuz, geçerli durum beklenmiyor"
    if not valid:
        return "yes" if not res.cover else (
            f"no:iz hiç geçerli çözüm görmedi ama koşum |C|={len(res.cover)} döndü")
    last = valid[-1]
    if not res.cover:
        return (f"no:iz Σw={last.observer_best_weight:g} ile geçerli çözüm "
                "bildiriyor, koşum BOŞ örtü döndü")
    # Zarf ile SON DURUM bilerek farklı olabilir (Metropolis yokuş yukarı
    # kabul eder; 60 tohumda 29'unda fark var). Bu bir çelişki DEĞİLDİR.
    # Yalnız TERS yön ihlaldir ve bb-core bunu kanıtladı: son durum her zaman
    # örneklenir ve örnekleyicinin geçerlilik ölçütü süpürmeninkinden ZAYIFTIR
    # (akış tabanlı, sahipliksiz), dolayısıyla süpürmenin geçerli saydığı her
    # son durum zarfa girmiş olmak zorundadır. Zarfın daha kötü çıkması ancak
    # son durum GEÇERSİZKEN olur, ki boş örtü hatası tam olarak öyle görünmüştü.
    if (last.observer_best_weight is not None
            and last.observer_best_weight > res.total_weight + 1e-6):
        return (f"no:gözlemci zarfı Σw={last.observer_best_weight:g}, koşumun "
                f"son durumu Σw={res.total_weight:g} ile DAHA İYİ; zarf en "
                "iyiyi kaçırmış (son durum geçersiz olabilir)")
    return "yes"


def instance_feasibility(inst: Instance, opts: SweepOptions) -> str:
    """C=V ile bile kapasite atanabiliyor mu (Hakimi). Kolun değil ÖRNEĞİN kusuru.

    Bir örnek kanıtlanabilir biçimde uygunsuzsa hiçbir kol onu çözemez ve o
    örneği kol başarısızlığı saymak bütün oranları bozar. Akış denetimi büyük
    çizgede pahalı olduğundan sınırın üstünde KOŞULMAZ ve sonuç `unknown:` diye
    işaretlenir; "uygun varsayalım" demek ölçmediğimizi ölçmüş gibi göstermek
    olurdu.
    """
    if inst.cell.n > opts.feasibility_max_n:
        return f"unknown:n>{opts.feasibility_max_n}"
    try:
        from ccvc import bridge
        g = validate.make_graph(list(inst.edges), opts.k, dict(inst.weights),
                                nodes=sorted(inst.weights))
        ok, _ = bridge.capacity_feasible(g, set(inst.weights))
    except Exception as exc:                      # noqa: BLE001
        return f"unknown:{type(exc).__name__}"
    return "yes" if ok else "no"


def run_one(inst: Instance, spec: VariantSpec, scheduler: str, opts: SweepOptions,
            *, exact: Optional[Tuple[Optional[float], str]] = None,
            feasible: str = "unknown:not_requested") -> Row:
    """Tek kolu tek örnekte koş ve HER DURUMDA bir satır üret.

    Çöken, yakınsamayan, çözülemeyen koşum da satır yazar; maliyet sütunları
    elde olan neyse onunla dolar. Eksik satır, ölçülmüş bir başarısızlığı
    ölçülmemiş gibi gösterirdi.

    TEK İSTİSNA BAĞLILIK. Brief §1 G'nin BAĞLI olduğunu VARSAYAR; kopuk bir
    çizgede ölçülen sayı, algoritmanın taahhüt etmediği bir öncül üstünde
    ölçülmüştür ve bağlı çizgelerde ölçülen sayılarla aynı sütuna yazılamaz.
    Böyle bir satır `bad_input` ile işaretlenir ve maliyet sütunları BOŞ kalır;
    ekip lideri docs/message_complexity.md'yi tam olarak bu yüzden bir kez
    baştan yazmak zorunda kaldı (ölçüm koşumu kopuk çizge üretiyordu, sayılar
    temiz görünüyordu).
    """
    t0 = time.perf_counter()
    connected = is_connected(sorted(inst.weights), inst.edges)
    ex_w, ex_s = exact if exact is not None else (None, "not_requested")
    k = opts.k
    base = dict(
        source=inst.source, group=inst.cell.group, n=inst.cell.n,
        ratio=inst.cell.ratio, m=len(inst.edges), seed=inst.seed,
        instance=os.path.basename(inst.path), variant=spec.name,
        family=spec.family, phase1=spec.phase1, phase5=spec.phase5,
        scheduler=scheduler, k=k, loss=opts.loss,
        graph_connected=connected, code_fingerprint=code_fingerprint(),
        counting_bound_infeasible=(len(inst.edges) > len(inst.weights) * k
                                   if k > 0 else True),
        instance_feasible=feasible,
        relabelled=inst.adaptation.relabelled,
        weight_scale=inst.adaptation.weight_scale,
        weight_rel_error=inst.adaptation.weight_rel_error,
        lower_bound_g6=math.ceil(len(inst.edges) / k) if k > 0 else 0,
        exact_weight=ex_w, exact_status=ex_s,
        seeds_in_cell=inst.seeds_in_cell,
    )
    empty = dict(
        verdict="", truncated=False, infeasible_reason="",
        trace_agrees="none", verdict_agrees="yes",
        mis_nbrs_max=opts.mis_nbrs_max, push_ttl_max=0,
        payload_at_cap=False, converged=False, infeasible=False, unresolved=False, valid=False,
        vertex_cover=False, connected=False, capacity=False, violations=0,
        violation_kinds="", cover_size=None, total_weight=None,
        backbone_size=None, backbone_weight=None, slots=None, t_conv_ms=None,
        tx=None, rx=None, retx=None, bytes_tx=None, max_payload=None,
        hello_tx=None,
    )

    if not connected and opts.require_connected:
        return Row(status="bad_input", seconds=round(time.perf_counter() - t0, 3),
                   detail=("girdi çizgesi kopuk; brief §1 bağlı G varsayar. "
                           "Bileşen bazlı ölçüm isteniyorsa "
                           "SweepOptions(require_connected=False, "
                           "connectivity='per_component')"),
                   **base, **empty)

    req = RunRequest(edges=inst.edges, weights=dict(inst.weights), k=k,
                     scheduler=scheduler, seed=inst.seed, max_ms=opts.max_ms,
                     loss=opts.loss, mis_nbrs_max=opts.mis_nbrs_max)
    try:
        res = adapt_result(spec.run(req), variant=spec.name)
    except Exception as exc:                      # noqa: BLE001
        status = "invalid" if type(exc).__name__ == "RunInvalid" else "error"
        return Row(status=status, seconds=round(time.perf_counter() - t0, 3),
                   detail=f"{type(exc).__name__}: {exc}"[:300], **base, **empty)

    from ccvc.bb.api import MsgType
    cost = dict(
        verdict=_verdict_of(res), truncated=res.truncated,
        infeasible_reason=res.infeasible_reason,
        converged=res.converged, infeasible=res.infeasible,
        unresolved=res.unresolved, slots=res.slots, t_conv_ms=res.t_conv_ms,
        tx=res.tx, rx=res.rx, retx=res.retx, bytes_tx=res.bytes_tx,
        max_payload=res.max_payload,
        hello_tx=int(res.by_type_tx.get(int(MsgType.HELLO), 0)),
        # Sınıra oturan yük ÖLÇÜLMEMİŞ demektir, "tam bu kadar" demek değil:
        # düğüm sınırı aşmak yerine hata atıyor, dolayısıyla eşitlik sansür
        # işaretidir ve şekil 6 bunu bilmek zorundadır.
        payload_at_cap=bool(res.max_payload in _hello_sizes(opts.mis_nbrs_max)),
        # İSTENEN değil KULLANILAN değer; varyant isteği yok sayabilir.
        mis_nbrs_max=res.params.get("mis_nbrs_max", opts.mis_nbrs_max),
        push_ttl_max=res.params.get("push_ttl_max", 0),
        cover_size=len(res.cover), total_weight=res.total_weight,
        trace_agrees=_trace_agreement(res, feasible),
        backbone_size=len(res.backbone) or None,
        backbone_weight=(round(sum(float(inst.weights[v]) for v in res.backbone), 6)
                         if res.backbone else None),
        **_distribution_metrics(res, inst, k),
    )
    g = validate.make_graph(list(inst.edges), k, dict(inst.weights),
                            nodes=sorted(inst.weights))
    rep = validate.validate(g, res.cover, res.owner, connectivity=opts.connectivity)
    gates = dict(
        valid=bool(rep.valid), vertex_cover=bool(rep.vertex_cover),
        connected=bool(rep.connected), capacity=bool(rep.capacity),
        violations=len(rep.violations),
        violation_kinds="|".join(sorted({v.kind for v in rep.violations})),
        # `rep` BURADA hesaplanmış oluyor; çapraz denetim maliyet sözlüğünde
        # değil burada durmalı (ilk denememde `rep` henüz yoktu).
        verdict_agrees=_verdict_agreement(res, rep),
    )
    verdict = _verdict_of(res)
    if verdict == "truncated":
        # Kesik koşumun sayıları hiçbir şey anlatmaz; ÖNCE bu söylenir, çünkü
        # kesilmiş bir koşumda bayrakların temiz olması BEKLENİR.
        status = "truncated"
    elif res.infeasible:
        status = "infeasible"
    elif verdict == "unresolved" or res.unresolved:
        status = "unresolved"
    elif not rep.valid:
        status = "contradiction"
    else:
        status = "ok"
    return Row(status=status, seconds=round(time.perf_counter() - t0, 3),
               detail="; ".join(res.notes)[:300], **base, **cost, **gates)


# ==========================================================================
# 6. Süpürme
# ==========================================================================
@dataclass(frozen=True)
class PlanEntry:
    instance: Instance
    spec: VariantSpec
    scheduler: str


def plan(instances: Sequence[Instance], specs: Sequence[VariantSpec], *,
         schedulers: Sequence[str] = ("sync", "async")) -> List[PlanEntry]:
    """Ne koşulacağını KOŞMADAN listele.

    Matris 310 örnek ve n=1000'e kadar çıkıyor; kaç koşum olacağını önceden
    bilmeden süpürme başlatmak, ne kadar süreceğini bilmeden başlatmaktır.
    """
    out: List[PlanEntry] = []
    for inst in instances:
        for spec in specs:
            for sch in schedulers:
                if sch in spec.schedulers:
                    out.append(PlanEntry(inst, spec, sch))
    return out


def sweep(instances: Sequence[Instance], specs: Sequence[VariantSpec], *,
          schedulers: Sequence[str] = ("sync", "async"),
          opts: Optional[SweepOptions] = None,
          progress: Optional[Callable[[str], None]] = None) -> List[Row]:
    """Bütün kolları AYNI örnekler üstünde koş (eşleştirilmiş tasarım).

    Süre bütçesi dolarsa kalan girdiler `skipped` satırı olarak yazılır, sessizce
    düşürülmez: eksik satır ile koşulmamış satır CSV'de ayırt edilebilmelidir.
    """
    o = opts or SweepOptions()
    entries = plan(instances, specs, schedulers=schedulers)
    rows: List[Row] = []
    exact_cache: Dict[Tuple[str, int, int, int], Tuple[Optional[float], str]] = {}
    feas_cache: Dict[Tuple[str, int, int, int], str] = {}
    t_start = time.perf_counter()
    stopped = False
    for i, e in enumerate(entries, 1):
        key = (e.instance.source, e.instance.cell.n, len(e.instance.edges),
               e.instance.seed)
        if key not in exact_cache:
            exact_cache[key] = _exact_reference(e.instance.edges,
                                                e.instance.weights, o.k, o)
            feas_cache[key] = instance_feasibility(e.instance, o)
        if stopped or (o.time_budget_s is not None
                       and time.perf_counter() - t_start > o.time_budget_s):
            stopped = True
            rows.append(_skipped_row(e, o, exact_cache[key], feas_cache[key],
                                     "süre bütçesi doldu"))
            continue
        row = run_one(e.instance, e.spec, e.scheduler, o,
                      exact=exact_cache[key], feasible=feas_cache[key])
        rows.append(row)
        if progress:
            progress(f"[{i}/{len(entries)}] {row.instance} {row.arm} "
                     f"-> {row.status} ({row.seconds:.1f}s)")
    return rows


def _skipped_row(e: PlanEntry, o: SweepOptions,
                 exact: Tuple[Optional[float], str], feasible: str,
                 why: str) -> Row:
    inst, spec = e.instance, e.spec
    return Row(
        source=inst.source, group=inst.cell.group, n=inst.cell.n,
        ratio=inst.cell.ratio, m=len(inst.edges), seed=inst.seed,
        instance=os.path.basename(inst.path), variant=spec.name,
        family=spec.family, phase1=spec.phase1, phase5=spec.phase5,
        scheduler=e.scheduler, k=o.k, loss=o.loss,
        graph_connected=is_connected(sorted(inst.weights), inst.edges),
        code_fingerprint=code_fingerprint(),
        counting_bound_infeasible=(len(inst.edges) > len(inst.weights) * o.k
                                   if o.k > 0 else True),
        trace_agrees="none", instance_feasible=feasible,
        relabelled=inst.adaptation.relabelled,
        weight_scale=inst.adaptation.weight_scale,
        weight_rel_error=inst.adaptation.weight_rel_error,
        mis_nbrs_max=o.mis_nbrs_max, push_ttl_max=0, payload_at_cap=False,
        verdict="", truncated=False, infeasible_reason="", verdict_agrees="yes",
        status="skipped", converged=False, infeasible=False, unresolved=False,
        valid=False, vertex_cover=False, connected=False, capacity=False,
        violations=0, violation_kinds="", cover_size=None, total_weight=None,
        lower_bound_g6=math.ceil(len(inst.edges) / o.k) if o.k > 0 else 0,
        backbone_size=None, backbone_weight=None, slots=None, t_conv_ms=None,
        tx=None, rx=None, retx=None, bytes_tx=None, max_payload=None,
        hello_tx=None, exact_weight=exact[0], exact_status=exact[1],
        seeds_in_cell=inst.seeds_in_cell, seconds=0.0, detail=why)


# ==========================================================================
# 7. Özet: hayatta kalma yanlılığı ve eşleşmiş çiftler
# ==========================================================================
def matched_pairs(specs: Sequence[VariantSpec],
                  schedulers: Sequence[str] = ("sync", "async")
                  ) -> List[Tuple[str, str, str]]:
    """TAM OLARAK BİR eksende ayrılan kol çiftleri (disiplin kuralı 2).

    Kıyas edilebilirlik bir dikkat meselesi değil, bir SÜZGEÇ: iki şeyi birden
    değiştiren kollar buradan geçemez, dolayısıyla "aynı algoritma, farklı
    koşul" olmayan bir kıyas raporda oluşamaz.
    """
    arms: List[Tuple[str, VariantSpec, str]] = [
        (f"{s.name}/{sch}", s, sch)
        for s in specs for sch in schedulers if sch in s.schedulers
    ]
    out: List[Tuple[str, str, str]] = []
    for i, (na, sa, scha) in enumerate(arms):
        for nb, sb, schb in arms[i + 1:]:
            if sa.family != sb.family:
                continue
            diff: List[str] = []
            if scha != schb:
                diff.append("scheduler")
            for ax in ("phase1", "phase5"):
                if sa.axis(ax) != sb.axis(ax):
                    diff.append(ax)
            if len(diff) == 1:
                out.append((na, nb, diff[0]))
    return out


def _mean(xs: Sequence[float]) -> Optional[float]:
    return round(statistics.mean(xs), 4) if xs else None


def summarize(rows: Sequence[Row], *,
              specs: Optional[Sequence[VariantSpec]] = None,
              schedulers: Sequence[str] = ("sync", "async")) -> Dict[str, Any]:
    """Kol başına istatistik + ORTAK ALTKÜME oranları + eşleşmiş çiftler."""
    arms = sorted({r.arm for r in rows})
    by_arm: Dict[str, List[Row]] = {a: [] for a in arms}
    for r in rows:
        by_arm[r.arm].append(r)

    # Kanıtlanabilir uygunsuz örnek KOL BAŞARISIZLIĞI DEĞİLDİR; oranlardan çıkar.
    infeasible_instances = {r.instance_key for r in rows if r.instance_feasible == "no"}
    all_instances = {r.instance_key for r in rows} - infeasible_instances

    valid_keys: Dict[str, Set[Any]] = {
        a: {r.instance_key for r in by_arm[a]
            if r.status == "ok" and r.valid and r.instance_key in all_instances}
        for a in arms
    }
    common: Set[Any] = (set.intersection(*valid_keys.values())
                        if valid_keys else set())

    # Referans ağırlık: küçük örnekte kesin çözüm, yoksa ortak altkümedeki EN İYİ
    # kol. İkincisi bir yaklaşım oranı DEĞİLDİR, göreli bir orandır ve öyle
    # etiketlenir; karıştırılırsa "optimumun 1,02 katı" diye okunur.
    exact_ref: Dict[Any, float] = {}
    best_ref: Dict[Any, float] = {}
    for r in rows:
        if r.exact_status == "ok" and r.exact_weight is not None:
            exact_ref[r.instance_key] = float(r.exact_weight)
        if r.status == "ok" and r.valid and r.total_weight is not None:
            cur = best_ref.get(r.instance_key)
            if cur is None or r.total_weight < cur:
                best_ref[r.instance_key] = float(r.total_weight)

    out: Dict[str, Any] = {
        "_arms": arms,
        "_instances": len(all_instances),
        "_instances_provably_infeasible": len(infeasible_instances),
        "_common_subset_size": len(common),
        "_exact_reference_instances": len(exact_ref),
        "_status_vocabulary": list(STATUS_ORDER) + ["skipped"],
    }

    for a in arms:
        rs = [r for r in by_arm[a] if r.instance_key in all_instances]
        ok = [r for r in rs if r.status == "ok" and r.valid]
        # İKİ SAYIM. `status` yalnız oranlara giren (uygun) örnekler üstünde,
        # `status_all` KOLUN BÜTÜN SATIRLARI üstünde. Tek sayım tutulsaydı,
        # kanıtlanabilir uygunsuz hücrelerdeki 24 `unresolved` satır envanterden
        # düşer ve kol hiç başarısız olmamış gibi görünürdü (ölçüldü); oysa o
        # satırlar gerçek slot ve tx harcadı ve maliyetleri raporun konusu.
        counts = {st: sum(1 for r in rs if r.status == st)
                  for st in list(STATUS_ORDER) + ["skipped"]}
        counts_all = {st: sum(1 for r in by_arm[a] if r.status == st)
                      for st in list(STATUS_ORDER) + ["skipped"]}
        # Kanıtlanabilir uygunsuz örnekte kolun UYGUNSUZ DEMESİ beklenir
        # (brief Faz 4). Dememek bir tespit boşluğudur ve ayrı sayılır; oran
        # ortalamalarına girmediği için başka hiçbir sütunda görünmez.
        infeas_rows = [r for r in by_arm[a] if r.instance_feasible == "no"]
        entry: Dict[str, Any] = {
            "n": len(rs), "valid": len(ok),
            "rows_total": len(by_arm[a]),
            "status": {k: v for k, v in counts.items() if v},
            "status_all": {k: v for k, v in counts_all.items() if v},
            "trace_disagrees": sum(1 for r in by_arm[a]
                                   if r.trace_agrees.startswith("no:")),
            "verdict_disagrees": sum(1 for r in by_arm[a]
                                     if r.verdict_agrees.startswith("no:")),
            "false_success": sum(1 for r in by_arm[a]
                                 if r.status == "contradiction"),
            "on_infeasible_instances": len(infeas_rows),
            # AYIRIM: ucuzca kanıtlanabilir olanı kaçırmak kol kusurudur;
            # yalnız akışla görülebileni kaçırmak değildir (bb-algo).
            "missed_infeasible": sum(1 for r in infeas_rows if not r.infeasible),
            "missed_provable_infeasible": sum(
                1 for r in infeas_rows
                if r.counting_bound_infeasible and not r.infeasible),
            "infeasible_not_cheaply_provable": sum(
                1 for r in infeas_rows if not r.counting_bound_infeasible),
        }
        if infeas_rows:
            sl = [float(r.slots) for r in infeas_rows if r.slots is not None]
            tx_ = [float(r.tx) for r in infeas_rows if r.tx is not None]
            entry["infeasible_slots_mean"] = _mean(sl)
            entry["infeasible_tx_mean"] = _mean(tx_)
        for tag, ref, keys in (("exact_own", exact_ref, None),
                               ("exact_common", exact_ref, common),
                               ("best_own", best_ref, None),
                               ("best_common", best_ref, common)):
            vals = [r.total_weight / ref[r.instance_key] for r in ok
                    if r.instance_key in ref and ref[r.instance_key] > 0
                    and (keys is None or r.instance_key in keys)]
            if vals:
                entry[f"ratio_{tag}_mean"] = _mean(vals)
                entry[f"ratio_{tag}_max"] = round(max(vals), 4)
                entry[f"ratio_{tag}_n"] = len(vals)
        for col in ("tx", "rx", "bytes_tx", "slots", "t_conv_ms", "max_payload"):
            vals = [getattr(r, col) for r in ok
                    if r.instance_key in common and getattr(r, col) is not None]
            if vals:
                entry[f"{col}_common_mean"] = _mean([float(v) for v in vals])
        # Hayatta kalma sinyali: kolun kendi altkümesi ile ortak altküme
        # ayrışıyorsa fark doğrudan başarısızlık örüntüsünden geliyordur.
        own = entry.get("ratio_best_own_mean")
        com = entry.get("ratio_best_common_mean")
        if own is not None and com is not None and abs(own - com) > 0.02:
            entry["survivorship_warning"] = (
                f"kendi altkümesinde {own}, ortak altkümede {com}; "
                f"fark {round(abs(own - com), 4)} başarısızlık örüntüsünden geliyor")
        out[a] = entry

    if specs:
        pairs = []
        for na, nb, axis in matched_pairs(specs, schedulers):
            ka = valid_keys.get(na, set())
            kb = valid_keys.get(nb, set())
            both = ka & kb
            ra = {r.instance_key: r for r in by_arm.get(na, [])}
            rb = {r.instance_key: r for r in by_arm.get(nb, [])}
            item: Dict[str, Any] = {
                "a": na, "b": nb, "axis": axis,
                "n_both_valid": len(both),
                "only_a_valid": len(ka - kb), "only_b_valid": len(kb - ka),
            }
            if both:
                wa = [ra[k].total_weight for k in both]
                wb = [rb[k].total_weight for k in both]
                item["same_cover"] = sum(
                    1 for k in both if ra[k].cover_size == rb[k].cover_size)
                item["weight_ratio_b_over_a"] = _mean(
                    [y / x for x, y in zip(wa, wb) if x])
                txa = [ra[k].tx for k in both if ra[k].tx is not None]
                txb = [rb[k].tx for k in both if rb[k].tx is not None]
                if txa and txb and len(txa) == len(txb):
                    item["tx_ratio_b_over_a"] = _mean(
                        [y / x for x, y in zip(txa, txb) if x])
            pairs.append(item)
        out["_matched_pairs"] = pairs
        out["_unmatched_note"] = (
            "Eşleşmiş çift listesinde OLMAYAN kol ikilileri, birden çok eksende "
            "ayrıldıkları için kıyaslanabilir değildir; özet onları kıyaslamaz.")
    return out


# ==========================================================================
# 8. Hücre kapsamı: tohum sayısı GİZLENMEZ
# ==========================================================================
def cell_coverage(rows: Sequence[Row]) -> List[Dict[str, Any]]:
    """Her hücre için koşulan tohum sayısı ve TEK KOŞUM işareti."""
    cells: Dict[Tuple[str, str, int, int, int], Dict[str, Any]] = {}
    for r in rows:
        key = (r.source, r.group, r.n, r.ratio, r.m)
        c = cells.setdefault(key, {
            "source": r.source, "group": r.group, "n": r.n, "ratio": r.ratio,
            "m": r.m, "seeds_run": set(), "seeds_in_dataset": r.seeds_in_cell,
            "rows": 0, "ok": 0,
        })
        c["seeds_run"].add(r.seed)
        c["rows"] += 1
        c["ok"] += 1 if r.status == "ok" else 0
    out = []
    for key in sorted(cells):
        c = cells[key]
        n_seeds = len(c["seeds_run"])
        c["seeds_run"] = n_seeds
        c["single_run"] = n_seeds < 3
        c["label"] = ("TEK KOŞUM (ortalama denemez)" if n_seeds == 1
                      else f"{n_seeds} tohum" + (" (3'ten az)" if n_seeds < 3 else ""))
        out.append(c)
    return out


# ==========================================================================
# 9. Çıktılar
# ==========================================================================
def write_csv(rows: Sequence[Row], path: str) -> str:
    """Satırları CSV'ye yaz. Önce geçici dosya, sonra yerine koy.

    `open(path, "w")` dosyayı açar açmaz siler; süpürme saatler sürebildiği için
    kısmi yazımda eski CSV'nin kaybolması kabul edilemez.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CSV_FIELDS))
        w.writeheader()
        for r in rows:
            w.writerow(r.as_dict())
    os.replace(tmp, path)
    return path


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "evet" if x else "hayır"
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def summary_markdown(rows: Sequence[Row], summary: Mapping[str, Any],
                     manifest: Mapping[str, Any]) -> str:
    """`summary.md`. Tohum sayısı, başarısızlıklar ve yanlılık uyarısı ZORUNLU."""
    L: List[str] = ["# BB-CVC süpürme özeti", ""]

    L += ["## 1. Koşum künyesi", ""]
    for key in sorted(manifest):
        L.append(f"- **{key}**: {_fmt(manifest[key])}")
    L.append("")

    cov = matrix.coverage(manifest.get("dataset_dir") or None)
    bad = [r for r in rows if r.status == "bad_input"]
    if bad:
        cells = sorted({(r.group, r.n, r.m, r.seed) for r in bad})
        L += ["## 1b. UYARI: KOPUK GİRDİ ÇİZGESİ", "",
              f"**{len(bad)} satır kaydedilmedi** çünkü girdi çizgesi kopuktu. "
              "Brief §1 G'nin BAĞLI olduğunu VARSAYAR; kopuk bir çizgede ölçülen "
              "sayı, algoritmanın taahhüt etmediği bir öncül üstünde ölçülmüştür "
              "ve bağlı çizge sayılarıyla aynı ortalamaya giremez.", "",
              "Bu bir kol kusuru değil **girdi kusurudur** ve sessizce "
              "geçilemez: farklı çizge popülasyonlarından gelen satırları aynı "
              "sütunda toplamak, kolları farklı popülasyonlar üstünde "
              "kıyaslamak demektir.", "",
              "| grup | n | m | tohum |", "|---|---|---|---|"]
        for g, n, m, seed in cells[:20]:
            L.append(f"| {g} | {n} | {m} | {seed} |")
        if len(cells) > 20:
            L.append(f"| … | | | {len(cells) - 20} örnek daha |")
        L.append("")
    else:
        L += ["## 1b. Girdi bağlılığı", "",
              f"Bütün {len({r.instance_key for r in rows})} örnek **bağlı** "
              "(brief §1). Kopuk çizgede ölçüm yapılmadı.", ""]

    # ÇAPRAZ DENETİM KARNESİ — sayı SIFIR OLSA DA yazılır.
    # Yalnız sorun varken beliren bir bölüm, "koştu ve bir şey bulmadı" ile
    # "hiç koşmadı"yı ayırt edilemez kılar; sıfırın kendisi de bir ölçümdür.
    n_inst = len({r.instance_key for r in rows})
    fingerprints = {r.code_fingerprint for r in rows if r.code_fingerprint}
    tr_no = sum(1 for r in rows if r.trace_agrees.startswith("no:"))
    tr_na = sum(1 for r in rows if r.trace_agrees.startswith("n/a"))
    tr_yes = sum(1 for r in rows if r.trace_agrees == "yes")
    tr_none = sum(1 for r in rows if r.trace_agrees == "none")
    vd_no = sum(1 for r in rows if r.verdict_agrees.startswith("no:"))
    false_ok = sum(1 for r in rows if r.status == "contradiction")
    trunc = sum(1 for r in rows if r.status == "truncated")
    L += ["## 1c. Çapraz denetim karnesi", "",
          "Her satır iki bağımsız görünümle karşılaştırılır: kolun kendi beyanı "
          "doğrulayıcının kararıyla, anytime izi de çözümle. Aşağıdaki sayılar "
          "SIFIR olsa da yazılır, çünkü boş bir bölüm denetimin koşup bir şey "
          "bulmadığını değil, koşmadığını da anlatabilirdi.", "",
          "| denetim | sonuç |", "|---|---|",
          f"| yanlış başarı (`contradiction`) | **{false_ok}** |",
          f"| beyan-doğrulayıcı uyuşmazlığı | **{vd_no}** |",
          f"| iz-çözüm uyuşmazlığı | **{tr_no}** |",
          f"| iz: uyumlu / uygunsuzda n-a / izsiz | {tr_yes} / {tr_na} / {tr_none} |",
          f"| kesik koşum (`truncated`) | {trunc} |",
          f"| kopuk girdi (`bad_input`) | {len(bad)} |",
          f"| kod sürümü (parmak izi) | {'/'.join(sorted(fingerprints))} |",
          "",
          ("> **UYARI: bu CSV birden çok KOD SÜRÜMÜNDEN ölçülmüş satır "
           f"içeriyor** ({len(fingerprints)} ayrı parmak izi). Süpürme "
           "sürerken depoya yama inmiş demektir; satırlar aynı tabloda "
           "toplanamaz, süpürme yeniden koşulmalıdır."
           if len(fingerprints) > 1 else
           "> Bütün satırlar TEK bir kod sürümünden ölçülmüştür."), "",
          "`n/a` satırları uyuşmazlık DEĞİLDİR: çözümü olmayan bir örnekte izin "
          "hiç geçerli durum görmemesi ile koşumun son yapılandırmayı döndürmesi "
          "birbiriyle tam uyumludur. Ayrı sayılmalarının nedeni, rutin olarak "
          "beklenen uyuşmazlık bildiren bir denetimin göz atılıp geçilmesi ve "
          "gerçek olanın içinde saklanmasıdır.", ""]


    L += ["## 2. Matris kapsamı", "",
          f"İstenen {cov['requested']} hücrenin {cov['impossible']} tanesi "
          "**matematiksel olarak imkânsız** (basit çizgede m > C(n,2)), veri "
          "kümesinde eksik değil:", ""]
    for c in matrix.impossible_cells():
        L.append(f"- n={c.n}, m/n={c.ratio}: {c.why_impossible()}")
    L += ["", f"Kalan {cov['possible']} hücrenin {cov['present_in_dataset']} tanesi "
          f"veri kümesinde var, toplam {cov['instances_total']} örnek. "
          f"**{cov['cells_with_fewer_than_3_seeds']} hücrede 3'ten az tohum var.**",
          ""]

    cells = cell_coverage(rows)
    thin = [c for c in cells if c["single_run"]]
    L += ["## 3. Hücre başına tohum sayısı", "",
          "Deney disiplini hücre başına en az 3 tohum ister. Aşağıdaki tabloda "
          "`TEK KOŞUM` yazan satırlarda **ortalama alınamaz**: tek koşum bir "
          "ortalama değil bir gözlemdir ve öyle etiketlenmiştir.", "",
          "| kaynak | grup | n | m/n | m | koşulan tohum | veri kümesinde | etiket |",
          "|---|---|---|---|---|---|---|---|"]
    for c in cells:
        L.append(f"| {c['source']} | {c['group']} | {c['n']} | {c['ratio']} | "
                 f"{c['m']} | {c['seeds_run']} | {c['seeds_in_dataset'] or '—'} | "
                 f"{c['label']} |")
    L += ["", f"3'ten az tohumlu hücre: **{len(thin)}/{len(cells)}**.", ""]

    L += ["## 4. Kol envanteri ve durum dağılımı", "",
          "Her kol AYNI örnekler üstünde koştu (eşleştirilmiş tasarım). "
          "`unresolved` bir başarısızlık değil bir **sonuçtur** ve satırı "
          "slot/tx'iyle birlikte CSV'de durur.", "",
          "`durum (hepsi)` kolun BÜTÜN satırlarını sayar; `durum (uygun)` yalnız "
          "kanıtlanabilir uygunsuz örnekler çıkarıldıktan sonrasını, yani "
          "oranların hesaplandığı altkümeyi. İkisi ayrışıyorsa kol yalnız "
          "çözümü olmayan örneklerde düşmüş demektir.", "",
          "| kol | satır | oranlara giren | geçerli | durum (hepsi) | durum (uygun) |",
          "|---|---|---|---|---|---|"]
    for arm in summary["_arms"]:
        e = summary[arm]
        st = ", ".join(f"{k}={v}" for k, v in sorted(e["status"].items()))
        st_all = ", ".join(f"{k}={v}" for k, v in sorted(e["status_all"].items()))
        L.append(f"| `{arm}` | {e.get('rows_total', e['n'])} | {e['n']} | "
                 f"{e['valid']} | {st_all} | {st} |")
    L.append("")

    infeas_cells = sorted({(r.group, r.n, r.ratio, r.m) for r in rows
                           if r.instance_feasible == "no"})
    if infeas_cells:
        L += ["### 4b. Bu k'da KANITLANABİLİR UYGUNSUZ hücreler", "",
              "Aşağıdaki hücrelerde C=V ile bile kapasite atanamıyor (Hakimi). "
              "Burada bir kolun başarısız olması **kol kusuru değildir**; bu "
              "satırlar oran ortalamalarının tamamen dışındadır. Matrisi bu k "
              "ile koşmak bu hücreleri anlamsız kılar, k büyütülmelidir.", "",
              "| grup | n | m/n | m | ⌈m/k⌉ |", "|---|---|---|---|---|"]
        for g, n, ratio, m in infeas_cells:
            kk = rows[0].k
            L.append(f"| {g} | {n} | {ratio} | {m} | "
                     f"{math.ceil(m / kk) if kk else '—'} |")
        L += ["", "Kol başına: uygunsuz örnekte uygunsuzluğu **ilan edemeyen** "
              "koşum sayısı `missed_infeasible` sütununda (özet JSON), harcanan "
              "slot/tx `infeasible_slots_mean`/`infeasible_tx_mean` içinde.", "",
                  "> **`missed_infeasible` KOLLAR ARASI FARK OKUMAK İÇİN "
              "KULLANILAMAZ.** Uygunsuzluk tespiti Faz 4'ün ortak kodundadır, "
              "dolayısıyla tespit kusuru bütün kollarda AYNI okunur.", "",
              "> Ayrıca her kaçırma kusur DEĞİLDİR. Sayma sınırı (m > n·k) "
              "ucuzca kanıtlanabilir dejenere sınıfı yakalar; onun dışındaki "
              "uygunsuzluk yalnız akışla görülür ve bugünkü HELLO ile sağlam "
              "bir YEREL tanık hesaplanamaz, yani düğümün bildirememesi "
              "beklenen davranıştır. Kusur sayılabilecek olan "
              "`missed_provable_infeasible` sütunudur; "
              "`infeasible_not_cheaply_provable` ise kaçırılması normal olan "
              "satırları sayar.", ""]

    vdis = [r for r in rows if r.verdict_agrees.startswith("no:")]
    if vdis:
        false_ok = [r for r in vdis if r.status == "contradiction"]
        L += ["### 4d. UYARI: kolun beyanı doğrulayıcıyla ÇELİŞİYOR", "",
              f"**{len(vdis)} satırda** kolun kendi bildirdiği sonuç ile "
              "doğrulayıcının kararı uyuşmuyor; bunların "
              f"**{len(false_ok)} tanesi YANLIŞ BAŞARI** (kol başardım dedi, "
              "doğrulayıcı ihlal buldu) ve `contradiction` durumuyla "
              "işaretlendi.", "",
              "`status` doğrulayıcıdan türetildiği için yanlış bir başarı zaten "
              "`ok` olamaz; bu bölüm onu ayrıca SAYAR, çünkü tek bir etiket "
              "\"kol yanlış beyan etti\" ile \"kol dürüstçe başarısızlık "
              "bildirdi\" arasındaki farkı taşımaz.", "",
              "| kol | çelişen satır | yanlış başarı | örnek neden |",
              "|---|---|---|---|"]
        byv: Dict[str, List[Row]] = {}
        for r in vdis:
            byv.setdefault(r.arm, []).append(r)
        for arm in sorted(byv):
            rs2 = byv[arm]
            nf = sum(1 for r in rs2 if r.status == "contradiction")
            L.append(f"| `{arm}` | {len(rs2)} | {nf} | {rs2[0].verdict_agrees[3:]} |")
        L.append("")

    dis = [r for r in rows if r.trace_agrees.startswith("no:")]
    if dis:
        reasons = sorted({r.trace_agrees for r in dis})
        L += ["### 4c. UYARI: anytime izi çözümle ÇELİŞİYOR", "",
              f"**{len(dis)} satırda** koşumun döndürdüğü çözüm ile kendi "
              "anytime izi aynı şeyi söylemiyor. Bunlar aynı koşumun iki "
              "görünümüdür; biri yanlıştır ve hangisi olduğu şeklin içinden "
              "GÖRÜNMEZ, çünkü şekil 8 yalnız ize, CSV yalnız çözüme bakar.", "",
              "| kol | çelişen satır | neden |", "|---|---|---|"]
        by = {}
        for r in dis:
            by.setdefault(r.arm, []).append(r)
        for arm in sorted(by):
            L.append(f"| `{arm}` | {len(by[arm])} | {by[arm][0].trace_agrees[3:]} |")
        L += ["", f"Görülen nedenler: {len(reasons)} ayrı biçim.", ""]

    L += ["## 5. Hayatta kalma yanlılığı", "",
          "Bir kol başarısız olunca oran ortalamasından **düşer**, kötü bir oran "
          "olarak görünmez. Bu yüzden iki oran ayrı verilir: `own` kolun kendi "
          "geçerli örneklerinde, `common` **bütün kolların** geçerli olduğu ortak "
          "altkümede. Kıyas `common` ile yapılır.", "",
          f"- ortak altküme: **{summary['_common_subset_size']}** örnek "
          f"(toplam {summary['_instances']})",
          f"- kanıtlanabilir uygunsuz örnek (kol kusuru DEĞİL): "
          f"{summary['_instances_provably_infeasible']}",
          f"- kesin çözüm referansı olan örnek: {summary['_exact_reference_instances']}",
          "",
          "| kol | ratio_best_own | ratio_best_common | ratio_exact_common "
          "| tx (ortak) | uyarı |",
          "|---|---|---|---|---|---|"]
    for arm in summary["_arms"]:
        e = summary[arm]
        L.append(f"| `{arm}` | {_fmt(e.get('ratio_best_own_mean'))} | "
                 f"{_fmt(e.get('ratio_best_common_mean'))} | "
                 f"{_fmt(e.get('ratio_exact_common_mean'))} | "
                 f"{_fmt(e.get('tx_common_mean'))} | "
                 f"{e.get('survivorship_warning', '—')} |")
    L += ["", "`ratio_best_*` bir **yaklaşım oranı değildir**: referans, ortak "
          "altkümedeki en iyi koldur, optimum değil. Yaklaşım oranı yalnız "
          "`ratio_exact_*` sütunundadır ve o da kesin çözücünün koşabildiği "
          "küçük örneklerde tanımlıdır.", ""]

    pairs = summary.get("_matched_pairs") or []
    L += ["## 6. Eşleşmiş kıyaslar", "",
          "İki kol ancak **tam olarak bir eksende** ayrılıyorsa kıyaslanır "
          f"(eksenler: {', '.join(AXES)}). Birden çok şeyi birden değiştiren "
          "kollar bu tabloya giremez; bu bir dikkat kuralı değil, süzgeçtir.", ""]
    if pairs:
        L += ["| A | B | eksen | ikisi de geçerli | yalnız A | yalnız B | Σw B/A | tx B/A |",
              "|---|---|---|---|---|---|---|---|"]
        for p in pairs:
            L.append(f"| `{p['a']}` | `{p['b']}` | {p['axis']} | {p['n_both_valid']} | "
                     f"{p['only_a_valid']} | {p['only_b_valid']} | "
                     f"{_fmt(p.get('weight_ratio_b_over_a'))} | "
                     f"{_fmt(p.get('tx_ratio_b_over_a'))} |")
        L += ["", "`yalnız A` / `yalnız B` sütunları çiftin kendi hayatta kalma "
              "sinyalidir: sıfır değilse iki kol farklı örnek kümelerinde "
              "başarılı demektir ve oran tek başına yanıltıcıdır.", ""]
    else:
        L += ["Eşleşmiş çift yok: ya tek kol koştu ya da kollar birden çok "
              "eksende ayrılıyor.", ""]

    fails = [r for r in rows if r.status != "ok"]
    L += ["## 7. Başarısızlık envanteri", "",
          f"{len(fails)} satır `ok` değil. **Hepsi CSV'de**, maliyet sütunlarıyla "
          "birlikte; başarısızlığın ne kadara mal olduğu ölçülen bir büyüklüktür.", ""]
    if fails:
        by_status: Dict[str, List[Row]] = {}
        for r in fails:
            by_status.setdefault(r.status, []).append(r)
        L += ["| durum | satır | ort. slot | ort. tx | örnekler |", "|---|---|---|---|---|"]
        for st in sorted(by_status):
            rs = by_status[st]
            sl = [r.slots for r in rs if r.slots is not None]
            tx = [r.tx for r in rs if r.tx is not None]
            sample = ", ".join(sorted({f"{r.instance}/{r.arm}" for r in rs})[:3])
            L.append(f"| `{st}` | {len(rs)} | {_fmt(_mean([float(x) for x in sl]))} | "
                     f"{_fmt(_mean([float(x) for x in tx]))} | {sample} |")
        ok_rows = [r for r in rows if r.status == "ok" and r.slots is not None]
        un = [r for r in fails if r.status == "unresolved" and r.slots is not None]
        if ok_rows and un:
            a, b = _mean([float(r.slots) for r in ok_rows]), _mean(
                [float(r.slots) for r in un])
            if a and b:
                L += ["", f"Çözülemeyen koşum ortalama **{b} slot** harcıyor, "
                      f"başarılı koşum {a}; oran **{round(b / a, 1)}×**. "
                      "Başarısızlık ucuz değildir ve bu sayı raporun kendisidir.", ""]
    return "\n".join(L) + "\n"


def write_outputs(rows: Sequence[Row], summary: Mapping[str, Any],
                  manifest: Mapping[str, Any], outdir: str) -> Dict[str, str]:
    os.makedirs(outdir, exist_ok=True)
    paths = {"csv": write_csv(rows, os.path.join(outdir, "rows.csv"))}
    js = os.path.join(outdir, "summary.json")
    tmp = js + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"manifest": dict(manifest), "summary": dict(summary),
                   "cells": cell_coverage(rows)}, fh, indent=1,
                  ensure_ascii=False, default=str)
    os.replace(tmp, js)
    paths["json"] = js
    md = os.path.join(outdir, "summary.md")
    tmp = md + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(summary_markdown(rows, summary, manifest))
    os.replace(tmp, md)
    paths["md"] = md
    return paths


# ==========================================================================
# 10. Komut satırı
# ==========================================================================
def select_cells(groups: Sequence[str], max_n: Optional[int],
                 ratios: Optional[Sequence[int]]) -> List[Cell]:
    cells = [c for c in matrix.feasible_cells() if c.group in groups]
    if max_n is not None:
        cells = [c for c in cells if c.n <= max_n]
    if ratios:
        cells = [c for c in cells if c.ratio in ratios]
    return cells


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="BB-CVC deney süpürmesi")
    ap.add_argument("--groups", default="small",
                    help="small,medium,large (virgülle)")
    ap.add_argument("--max-n", type=int, default=None)
    ap.add_argument("--ratios", default="", help="ör. 2,4")
    ap.add_argument("--max-seeds", type=int, default=3)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--max-ms", type=int, default=600_000)
    ap.add_argument("--mis-nbrs-max", type=int, default=32,
                    help="HELLO'daki MIS komşusu üst sınırı; 5 (UDG varsayılanı) "
                         "kıyas kümesinde ÇALIŞMAZ")
    ap.add_argument("--schedulers", default="sync,async")
    ap.add_argument("--variants", default="", help="boşsa hepsi")
    ap.add_argument("--time-budget-s", type=float, default=None)
    ap.add_argument("--synthetic", action="store_true",
                    help="veri kümesi yerine üretilmiş çizge (source=synthetic)")
    ap.add_argument("--dry-run", action="store_true",
                    help="yalnız ne koşulacağını yaz")
    ap.add_argument("--out", default="results/bb/sweep")
    a = ap.parse_args(argv)

    groups = [g.strip() for g in a.groups.split(",") if g.strip()]
    ratios = [int(x) for x in a.ratios.split(",") if x.strip()] or None
    schedulers = [s.strip() for s in a.schedulers.split(",") if s.strip()]
    cells = select_cells(groups, a.max_n, ratios)

    specs = discover()
    if a.variants:
        want = {v.strip() for v in a.variants.split(",") if v.strip()}
        specs = [s for s in specs if s.name in want]
        missing = want - {s.name for s in specs}
        if missing:
            print(f"HATA: bilinmeyen varyant {sorted(missing)}", file=sys.stderr)
            return 2

    if a.synthetic:
        instances = [synthetic_instance(c, s)
                     for c in cells for s in range(a.max_seeds)]
        dsdir = None
    else:
        dsdir = matrix.dataset_dir()
        if dsdir is None:
            print("HATA: Dagdeviren veri kümesi bulunamadı. Kıyas modu "
                  "sentetiğe DÜŞMEZ; --synthetic ile açıkça iste ya da "
                  f"{matrix.DATASET_ENV} ayarla.", file=sys.stderr)
            return 2
        instances = dataset_instances(cells, max_seeds=a.max_seeds, directory=dsdir)

    entries = plan(instances, specs, schedulers=schedulers)
    print(f"hücre: {len(cells)}  örnek: {len(instances)}  kol: "
          f"{len(specs)}×{len(schedulers)}  koşum: {len(entries)}")
    if a.dry_run:
        for c in cell_coverage([]) or []:
            pass
        for s in specs:
            print(f"  kol {s.name}/{s.schedulers} "
                  f"family={s.family} phase1={s.phase1} phase5={s.phase5}")
        for na, nb, ax in matched_pairs(specs, schedulers):
            print(f"  eşleşmiş: {na} <-> {nb} ({ax})")
        return 0

    opts = SweepOptions(k=a.k, loss=a.loss, max_ms=a.max_ms,
                        mis_nbrs_max=a.mis_nbrs_max,
                        time_budget_s=a.time_budget_s)
    t0 = time.time()
    rows = sweep(instances, specs, schedulers=schedulers, opts=opts,
                 progress=lambda s: print(s, flush=True))
    manifest = {
        "dataset_dir": dsdir, "source": "synthetic" if a.synthetic else "dataset",
        "groups": ",".join(groups), "max_n": a.max_n, "ratios": a.ratios or "hepsi",
        "max_seeds": a.max_seeds, "k": a.k, "loss": a.loss, "max_ms": a.max_ms,
        "schedulers": ",".join(schedulers), "mis_nbrs_max": a.mis_nbrs_max,
        "variants": ",".join(s.name for s in specs),
        "rows": len(rows), "seconds": round(time.time() - t0, 1),
    }
    summary = summarize(rows, specs=specs, schedulers=schedulers)
    paths = write_outputs(rows, summary, manifest, a.out)
    print(f"yazıldı: {paths['csv']}, {paths['md']}, {paths['json']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    # GERÇEK modüle devret. `python -m ccvc.bb.sweep` bu dosyayı `__main__`
    # adıyla yükler; buradaki `main`i doğrudan çağırmak, varyantların import
    # ettiği `ccvc.bb.sweep` ile aynı adı taşıyan AMA farklı olan bir sınıf
    # kümesiyle koşmak demektir.
    from ccvc.bb.sweep import main as _main

    raise SystemExit(_main())
