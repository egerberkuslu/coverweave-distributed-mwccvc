#!/usr/bin/env python3
"""BB-CVC bootstrap katmanının testleri.

Koşum:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_bootstrap.py -q

Bu dosya iki şeyi birden sınamaktadır. Birincisi katmanın DOĞRU sonucu
üretmesidir: on düğümlük çalışan örnekte keşfedilen derece ve donmuş anahtar
gerçek çizgeyle birebir tutmalıdır. İkincisi ve daha önemlisi, sonuca NASIL
varıldığıdır: düğüm çizgeyi göremez, kenar yalnız çift yönlü doğrulanmışsa
vardır, anahtar kararlılık kapısından önce donmaz ve karar yolunda hiç float
bulunmaz. Birinci grubu geçip ikinciyi geçmeyen bir uygulama, brief §3.1'in
yerellik ilkesini çiğnediği için yanlıştır.
"""
from __future__ import annotations

import ast
import inspect
import os
import re
import struct
import sys
from fractions import Fraction

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb.api import (
    FP_SHIFT,
    Counters,
    MsgType,
    Neighbor,
    PayloadTooLarge,
    Role,
    from_fp,
    key_of,
    to_fp,
)
from ccvc.bb import wire
from ccvc.bb.bootstrap import (
    BootNeighbor,
    BootstrapNode,
    BootstrapParams,
    RunInvalid,
    bootstrap_report,
    epoch_newer,
    hash16,
    t_hello_lower_bound_ms,
    xorshift32,
)
from ccvc.bb.simnet import SimNet, default_mac, fixed_delay


# --------------------------------------------------------------------------
# Koşum koşumu: GERÇEK taşıma (ccvc/bb/simnet.py) üzerinde ince bir sürücü.
#
# Burada bir zamanlar StubNet adında ikinci bir taşıma vardı. SimNet'e yönlü,
# zamanlı ve tip-seçici `drop` yüklemi ile çağrılabilir RSSI eklendiğinde
# gerekçesi kalmadı: aşağıdaki dört arıza sınıfının hepsi artık gerçek taşıma
# üzerinde yazılabilmektedir, dolayısıyla tek bir taşıma sınanmaktadır.
#
# SimNet'in `drop(t_ms, src, dst, msg_type)` ve `rssi(t_ms, src, dst)`
# kancaları DÜĞÜM ID'si alır; senaryolar topolojiyi zaten düğüm id'siyle
# kurduğu için bu, MAC'ten daha okunaklıdır ve değiştirilmesi gerekmez.
# --------------------------------------------------------------------------
class BootNet:
    """Düğümleri SimNet'e bağlar ve senkron tick'lerle sürer.

    Gecikme tam bir tick olduğundan `drain_all` + hepsini teslim etmek,
    o yöntemin belgelenmiş senkron kullanımıdır.
    """

    def __init__(
        self,
        weights,
        edges,
        params=None,
        tick_ms: int = 20,
        rssi=None,
        drop=None,
        macs=None,
        epoch_ms: int = 0,
        **kw,
    ):
        # epoch_ms: saatin BAŞLADIĞI an. Simülatör 0'dan başlar, duvar saati
        # ~1.7e12'den. Düğüm ikisi altında da doğru olmalıdır.
        self.p = params or BootstrapParams()
        self.tick_ms = tick_ms
        self.labels = sorted(weights)
        self.sim = SimNet(
            self.labels,
            edges,
            delay=fixed_delay(tick_ms),
            rssi=rssi if rssi is not None else (lambda t, u, v: -60.0),
            rssi_range=None,
            drop=drop,
            macs=macs,
            **kw,
        )
        self.nodes = {}
        self.plats = {}
        for lab in self.labels:
            port = self.sim.port(lab)
            node = BootstrapNode(weights[lab], port, self.p)
            self.sim.attach(lab, node)
            self.nodes[lab] = node
            self.plats[lab] = port
        self.t = int(epoch_ms)

    # -- test yüzeyi ----------------------------------------------------
    @property
    def macs(self):
        return self.sim.macs

    def node(self, label):
        return self.nodes[label]

    def counters(self, label):
        return self.sim.counters[label]

    def label_of_id(self, nid):
        for lab, nd in self.nodes.items():
            if nd.nid == nid:
                return lab
        return None

    def set_drop(self, fn):
        self.sim.drop = fn

    def all_done(self):
        return all(n.done for n in self.nodes.values())

    def run_until(self, t_end):
        while self.t <= t_end:
            self.sim.set_now(self.t)
            for d in self.sim.drain_all():
                self.sim.deliver(d)
            for lab in self.labels:
                self.nodes[lab].on_timer("tick")
                if self.nodes[lab].done:
                    self.sim.mark_done(lab, self.t)
            self.t += self.tick_ms
        self.sim.finalize(self.t)


# --------------------------------------------------------------------------
# Kalibrasyon çizgesi: .tex Bölüm 12.6 / DISCOVERY §9 çalışan örneği.
# 10 düğüm, 15 kenar, k=2.
# --------------------------------------------------------------------------
EDGES = [
    (1, 2),
    (1, 3),
    (2, 3),
    (2, 4),
    (3, 4),
    (4, 5),
    (4, 6),
    (5, 6),
    (5, 7),
    (6, 7),
    (7, 8),
    (7, 9),
    (8, 9),
    (8, 10),
    (9, 10),
]
WEIGHTS = {i + 1: w for i, w in enumerate([5, 2, 4, 3, 6, 2, 3, 2, 5, 4])}
TRUE_DEG = {1: 2, 2: 3, 3: 3, 4: 4, 5: 3, 6: 3, 7: 4, 8: 3, 9: 3, 10: 2}
EXPECTED_KEY = {
    1: 1.67,
    2: 0.50,
    3: 1.00,
    4: 0.60,
    5: 1.50,
    6: 0.50,
    7: 0.60,
    8: 0.50,
    9: 1.25,
    10: 1.33,
}


def calibration_net(**kw) -> "BootNet":
    return BootNet(WEIGHTS, EDGES, **kw)


def hello_only(mtype: int) -> bool:
    return mtype == int(MsgType.HELLO)


def a_hello(nid: int, **kw) -> bytes:
    """Testlerin ürettiği HELLO da wire.py'den geçer; ikinci kodlayıcı yoktur."""
    f = dict(key=None, deg=0, role=Role.OUT, phase=0, load=0, epoch=0)
    f.update(kw)
    return wire.encode(wire.Hello(src=nid, **f))


def a_ctrl(mtype: MsgType, nid: int, seq: int) -> bytes:
    return wire.encode(wire.Ctrl(mtype, nid, seq))


# ==========================================================================
# 1. Kimlik
# ==========================================================================
def test_hash16_is_deterministic_and_fits_two_bytes():
    for mac in range(0x020000000000, 0x020000000000 + 500):
        nid = hash16(mac)
        assert nid == hash16(mac), "hash16 deterministik olmalıdır"
        assert 1 <= nid <= 0xFFFF, "id 2 bayta sığmalı ve 0 ayrılmış olmalıdır"


def test_salt_changes_the_derived_id():
    mac = 0x02AABBCCDDEE
    ids = {hash16(mac, salt) for salt in range(8)}
    assert len(ids) == 8, "tuzlu yeniden türetme farklı id üretmelidir"


def colliding_mac_pair(limit: int = 200_000):
    """hash16 altında çakışan iki MAC bul. Doğum günü ile birkaç yüz denemede gelir."""
    seen = {}
    base = 0x02_00_00_00_00_00
    for i in range(1, limit):
        mac = base + i
        nid = hash16(mac)
        if nid in seen:
            return seen[nid], mac
        seen[nid] = mac
    raise AssertionError("çakışma bulunamadı")


def test_identity_collision_larger_mac_rederives_and_both_converge():
    """Aynı id, farklı MAC: büyük MAC tuzlu hash ile yeniden karar verir."""
    a, b = colliding_mac_pair()
    assert hash16(a) == hash16(b) and a != b
    small, large = min(a, b), max(a, b)

    net = BootNet({1: 5, 2: 3}, [(1, 2)], macs={1: small, 2: large})
    n_small, n_large = net.node(1), net.node(2)
    assert n_small.nid == n_large.nid, "başlangıçta kimlikler çakışmalıdır"

    net.run_until(3000)

    assert n_large.id_rederivations == 1, "yalnız büyük MAC yeniden türetmelidir"
    assert n_small.id_rederivations == 0, "küçük MAC kimliğini korumalıdır"
    assert n_small.nid != n_large.nid, "çakışma çözülmemiş"
    assert n_small.deg == 1 and n_large.deg == 1
    assert n_small.edges() == frozenset({n_large.nid})
    assert n_large.edges() == frozenset({n_small.nid})


def test_identity_collision_is_judged_by_the_header_mac_not_the_payload():
    """MAC yükte değil başlıktadır: çakışma kararı `src` ile verilir.

    Kendi id'mizi taşıyan bir HELLO kendi MAC'imizden geliyorsa bu yankıdır,
    çakışma değil. Aynı yük BAŞKA bir MAC'ten gelirse çakışmadır.
    """
    net = BootNet({1: 5, 2: 3}, [(1, 2)])
    n = net.node(1)
    payload = a_hello(n.nid)

    n.on_frame(n.mac, -60.0, payload)  # kendi yankımız
    n.on_timer()
    assert n.id_rederivations == 0

    n.on_frame(n.mac - 1, -60.0, payload)  # küçük MAC iddia ediyor: biz çekiliriz
    n.on_timer()
    assert n.id_rederivations == 1


def test_the_sender_mac_is_never_carried_in_the_payload():
    """MAC çerçeve başlığındadır; PAYLAŞILAN kodlayıcıda da hiçbir yük taşımaz.

    Bu test artık wire.py'yi bekçiliyor, kendi kopyamı değil.
    """
    assert not hasattr(wire.Hello(1, None, 0, Role.OUT, 0, 0), "mac")
    mac = 0x02AABBCCDDEE
    for payload in (a_hello(0xBEEF), a_ctrl(MsgType.LINK, 0xBEEF, 7)):
        for order in ("big", "little"):
            assert mac.to_bytes(6, order) not in payload
    assert len(a_ctrl(MsgType.LINK, 0xBEEF, 7)) == 5


# ==========================================================================
# 2. Yerellik: düğüm çizgeyi GÖREMEZ (brief §3.1, api I1)
# ==========================================================================
GRAPH_WORDS = re.compile(
    r"neighbou?rs?|adj|edges?|graph|topolog|degree|deg_|n_nodes|num_nodes|node_list",
    re.I,
)


def test_constructor_accepts_nothing_that_describes_the_graph():
    """Düğüme kendi ağırlığı ve kapasitesi dışında hiçbir şey verilmez.

    MAC bile parametre değildir: port'tan okunur. id ondan türetilir.
    """
    params = list(inspect.signature(BootstrapNode.__init__).parameters)
    assert params == ["self", "weight", "platform", "params", "capacity_k"]
    for name in params:
        assert not GRAPH_WORDS.search(name), f"kurucu çizgeye dair alan alıyor: {name}"
    assert "mac" not in params and "nid" not in params


def _is_port_ref(node) -> bool:
    """`self.plat` ya da kurucudaki `platform` adı: ikisi de aynı port nesnesidir."""
    if isinstance(node, ast.Attribute) and node.attr == "plat":
        return isinstance(node.value, ast.Name) and node.value.id == "self"
    return isinstance(node, ast.Name) and node.id == "platform"


def _plat_surface_used_by_node():
    """Düğüm kodunun PORT üzerinde dokunduğu her ad, çağrı/okuma ayrımıyla.

    Hem `self.plat.X` hem de kurucudaki `platform.X` sayılır; yoksa kurucuda
    yapılan bir erişim (örneğin `platform.mac`) sayımdan kaçardı ve test
    boşuna geçerdi.
    """
    tree = ast.parse(inspect.getsource(BootstrapNode))
    called, read = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if _is_port_ref(node.func.value):
                called.add(node.func.attr)
        if isinstance(node, ast.Attribute) and _is_port_ref(node.value):
            read.add(node.attr)
    return called, read


def test_node_only_ever_calls_the_four_platform_primitives():
    """api I2: çağrılabilen tam olarak dört ilkel vardır, beşincisi yoktur."""
    called, _ = _plat_surface_used_by_node()
    assert called == {"send_broadcast", "send_unicast", "now_ms", "log"}, called


def test_node_touches_nothing_outside_the_declared_port_surface():
    """Port yüzeyi {log, mac, now_ms, send_broadcast, send_unicast}.

    Düğüm bunların dışında yalnız `counters`a dokunur ve o da ÖLÇÜM içindir:
    `snapshot()` dışında hiçbir yerde geçmez, dolayısıyla karar yoluna giremez.
    `nid` asla okunmaz; kimlik türetilir, verilmez.
    """
    port_surface = {"log", "mac", "now_ms", "send_broadcast", "send_unicast"}
    called, read = _plat_surface_used_by_node()
    assert read - port_surface == set(), read - port_surface
    assert called <= port_surface
    assert "mac" in read, "kendi MAC'i port'tan OKUNMALI, parametre olmamalı"
    assert "nid" not in read, "kimlik port'tan OKUNAMAZ, hash16(MAC) ile türetilir"

    # Dolaylı erişim de kapalı: sınıfta `self.plat` üzerinde tek bir getattr
    # vardır, o da ölçüm amaçlı `counters` okumasıdır ve snapshot içindedir.
    tree = ast.parse(inspect.getsource(BootstrapNode))
    dynamic = [
        n.args[1].value
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "getattr"
        and _is_port_ref(n.args[0])
    ]
    assert dynamic == ["counters"], dynamic
    assert "counters" in inspect.getsource(BootstrapNode.snapshot)


def _code_without_comments_or_strings(src: str) -> str:
    """Yorumları ve dizgileri atıp geriye YALNIZ kodu bırak.

    Düz metin araması yapan bir test, bir açıklama satırında geçen adı ihlal
    sanar. Sınamak istediğimiz şey kodun ne YAPTIĞIdır, ne anlattığı değil.
    """
    import io
    import tokenize

    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    # Ayırıcısız birleştirilir: " ".join olsaydı `self . plat . adj` üretir ve
    # ".adj" araması HİÇBİR ŞEY bulmazdı. Test boşuna geçerdi.
    return "".join(out)


def test_node_source_never_reaches_into_the_simulator():
    """Düğüm KODU simülatöre uzanmaz. Açıklamalarda adı geçebilir."""
    code = _code_without_comments_or_strings(inspect.getsource(BootstrapNode))
    for forbidden in (".net", ".adj", ".labels", ".nodes", "SimNet", ".sim"):
        assert forbidden not in code, f"düğüm kodu simülatöre uzanıyor: {forbidden}"

    # Dedektörün boş geçmediğini göster: gerçekten bir ihlali yakalıyor mu?
    mutant = _code_without_comments_or_strings(
        "def f(self):\n    return self.plat._net.adj\n"
    )
    assert ".adj" in mutant and "._net" in mutant


def test_node_knows_nothing_before_the_first_frame():
    net = calibration_net()
    n = net.node(4)
    assert n.deg is None and n.key is None and n.nbrs == {}
    assert n.phase == 0
    assert n.edges() == frozenset()


def test_a_node_that_receives_no_frame_learns_no_neighbour():
    """Bütün çerçeveler düşerse düğüm hiçbir komşu öğrenemez.

    Gerçek çizgede düğüm 4'ün dört komşusu vardır; teslim kesilince deg 0
    donmaktadır. Demek ki bilginin TEK kaynağı on_frame'dir; motor hiçbir şey
    sızdırmamaktadır.
    """
    net = calibration_net(drop=lambda t, u, v, mt: True)
    net.run_until(2000)
    n = net.node(4)
    assert n.nbrs == {}
    assert n.deg == 0, "teslim yokken derece 0 olmalıdır"
    assert n.key == key_of(WEIGHTS[4], 0, n.nid)
    assert TRUE_DEG[4] == 4, "gerçek derece 4'tür; düğüm onu göremediği için 0 dedi"


def test_node_state_holds_no_reference_to_the_graph():
    """Düğümün kendi durumunda simülatörün çizge nesnelerine erişim yoktur.

    Tek dış kapı platformdur ve o da yalnız dört çağrıdır (üstteki test).
    """
    net = calibration_net()
    net.run_until(1500)
    n = net.node(4)
    banned = {
        id(net.sim),
        id(net.sim._adj),
        id(net.sim.nodes),
        id(net.sim.macs),
        id(net.sim.edges),
        id(net.nodes),
    }
    seen, stack = set(), [v for k, v in n.__dict__.items() if k != "plat"]
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        assert id(obj) not in banned, "düğüm çizge nesnesine erişebiliyor"
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
        elif hasattr(obj, "__dict__"):
            stack.extend(obj.__dict__.values())


# ==========================================================================
# 3. Kalibrasyon: keşfedilen derece ve anahtar gerçek çizgeyle tutmalı
# ==========================================================================
def test_calibration_every_node_discovers_its_true_degree():
    net = calibration_net()
    net.run_until(2000)
    assert net.all_done()
    for lab in net.labels:
        assert net.node(lab).deg == TRUE_DEG[lab], f"düğüm {lab} derecesi"


def test_calibration_frozen_keys_match_the_document_to_two_decimals():
    net = calibration_net()
    net.run_until(2000)
    got = {lab: round(from_fp(net.node(lab).key[0]), 2) for lab in net.labels}
    assert got == EXPECTED_KEY


def test_calibration_discovered_edges_match_the_true_graph_exactly():
    net = calibration_net()
    net.run_until(2000)
    true_adj = {u: set() for u in net.labels}
    for u, v in EDGES:
        true_adj[u].add(v)
        true_adj[v].add(u)
    for lab in net.labels:
        found = {net.label_of_id(nid) for nid in net.node(lab).edges()}
        assert found == true_adj[lab], f"düğüm {lab} komşu kümesi"


def test_calibration_key_order_is_the_documents_order():
    """.tex Şekil: 2,6,8 -> 0.50 (id ile sıralanır), sonra 4,7 -> 0.60, ..."""
    net = calibration_net()
    net.run_until(2000)
    order = sorted(net.labels, key=lambda l: net.node(l).key)
    assert [round(from_fp(net.node(l).key[0]), 2) for l in order] == [
        0.50,
        0.50,
        0.50,
        0.60,
        0.60,
        1.00,
        1.25,
        1.33,
        1.50,
        1.67,
    ]


def test_calibration_converges_without_a_single_epoch_bump():
    net = calibration_net()
    net.run_until(2000)
    assert all(net.node(l).epoch_bumps == 0 for l in net.labels)
    assert all(net.node(l).epoch == 0 for l in net.labels)


def test_key_is_frozen_exactly_once_per_epoch():
    net = calibration_net()
    net.run_until(660)
    froze = {l: net.node(l).frozen_at_ms for l in net.labels}
    keys = {l: net.node(l).key for l in net.labels}
    net.run_until(4000)
    assert {l: net.node(l).frozen_at_ms for l in net.labels} == froze
    assert {l: net.node(l).key for l in net.labels} == keys


# ==========================================================================
# 4. Kararlılık kapısı — brief'in adıyla istediği "düğüm 4" testi
# ==========================================================================
def test_stability_gate_node4_missing_neighbour_hello_does_not_freeze_wrong_key():
    """.tex Şekil "kararlılık kapısı": düğüm 6'nın HELLO'su üç periyot kayıp.

    Kapı olmasaydı düğüm 4 deg=3 ile key = 3/4 = 0.75 dondururdu; gerçek değer
    3/5 = 0.60'tır. Test önce YANLIŞ değerin gerçekten elde edilebilir durumda
    olduğunu (kapısız bir uygulamanın tam olarak onu donduracağını) gösterir,
    sonra kapılı uygulamanın 0.60'ta dondurduğunu gösterir.
    """
    p = BootstrapParams()
    outage = 3 * p.t_hello_ms  # T1, T2, T3

    def drop(t, u, v, mt):
        return hello_only(mt) and u == 6 and v == 4 and t < outage

    net = calibration_net(params=p, drop=drop)
    n4 = net.node(4)

    net.run_until(outage)
    assert 6 not in {net.label_of_id(i) for i in n4.edges()}, "6 henüz duyulmamalı"
    assert n4.candidate_deg() == 3, "kapısız uygulamanın göreceği (yanlış) derece"
    assert (
        round(from_fp(n4.candidate_key_fp()), 2) == 0.75
    ), "kapısız uygulamanın donduracağı yanlış anahtar"
    assert n4.phase == 0, "kapı hâlâ kapalı olmalı"
    assert n4.key is None, "kapı anahtarın erken donmasını engellemeli"

    net.run_until(4000)
    assert n4.deg == 4, "kayıp biter bitmez gerçek derece bulunmalı"
    assert round(from_fp(n4.key[0]), 2) == 0.60
    assert (
        n4.frozen_at_ms is not None and n4.frozen_at_ms >= outage + p.t_stab_ms
    ), "kapının bedeli üç periyotluk gecikmedir; ondan önce donmamalı"
    for lab in net.labels:
        assert round(from_fp(net.node(lab).key[0]), 2) == EXPECTED_KEY[lab], lab


def test_stability_gate_node4_hello_dropped_three_times_neighbours_freeze_correct_keys():
    """Aynı kapı, ters yön: düğüm 4'ün HELLO'su üç kez üst üste düşürülür.

    Bu kez zarar gören 4 değil, komşularıdır. Düğüm 2 kapısız olsaydı deg=2 ile
    2/3 = 0.67 dondururdu; doğru değer 2/4 = 0.50'dir.
    """
    p = BootstrapParams()
    outage = 3 * p.t_hello_ms

    def drop(t, u, v, mt):
        return hello_only(mt) and u == 4 and t < outage

    net = calibration_net(params=p, drop=drop)
    victims = [2, 3, 5, 6]

    net.run_until(outage)
    for lab in victims:
        n = net.node(lab)
        assert n.phase == 0, f"düğüm {lab} kapı açılmadan dondu"
        assert (
            n.candidate_deg() == TRUE_DEG[lab] - 1
        ), f"düğüm {lab} henüz 4'ü duymamalı"
        assert n.candidate_key_fp() != key_of(WEIGHTS[lab], TRUE_DEG[lab], n.nid)[0]

    net.run_until(4000)
    for lab in net.labels:
        n = net.node(lab)
        assert n.deg == TRUE_DEG[lab], f"düğüm {lab} derecesi"
        assert round(from_fp(n.key[0]), 2) == EXPECTED_KEY[lab], f"düğüm {lab} anahtarı"
    assert (
        round(from_fp(net.node(2).key[0]), 2) == 0.50
    ), "kapısız uygulama 0.67 dondururdu"


def test_gate_is_local_and_epoch_repairs_what_the_gate_cannot_see():
    """Kapının dürüst sınırı: T_stab'dan UZUN bir sessizlik kapıyı aldatır.

    Düğüm 6, düğüm 4'e beş periyot boyunca sessiz kalırsa 4 için o komşu
    yoktur; kapı sükûnet gördüğü için deg=3 ile donar. Bu bir hata değil,
    yerelliğin sonucudur. Onarım yolu yama değil, epoch ile yeniden koşumdur:
    6 duyulduğu anda 4 epoch'u artırır ve doğru anahtarla yeniden donar.
    """
    p = BootstrapParams()
    outage = 5 * p.t_hello_ms

    def drop(t, u, v, mt):
        return hello_only(mt) and u == 6 and v == 4 and t < outage

    net = calibration_net(params=p, drop=drop)
    n4 = net.node(4)

    net.run_until(outage)
    assert n4.phase == 1 and n4.deg == 3, "kapı, duyulmayan komşuyu icat edemez"
    assert round(from_fp(n4.key[0]), 2) == 0.75

    net.run_until(6000)
    assert n4.epoch_bumps >= 1, "yama yok, epoch artıp baştan koşulmalı"
    assert n4.deg == 4
    assert round(from_fp(n4.key[0]), 2) == 0.60


# ==========================================================================
# 5. Çift yönlülük: kenar yalnız LINK-ACK ile vardır
# ==========================================================================
def test_asymmetric_link_never_becomes_an_edge():
    """1 -> 2 yönü sağlam, 2 -> 1 yönü kopuk: (1,2) kenarı YOKTUR.

    Simülatör simetrik olsa da kod LINK/LINK-ACK yolunu izlediği için
    asimetri yakalanır (brief §3.5 madde 3).
    """
    net = BootNet(
        {1: 5, 2: 3, 3: 4},
        [(1, 2), (1, 3), (2, 3)],
        drop=lambda t, u, v, mt: (u == 1 and v == 2),
    )
    # Note to Amendment 15 (D2): the freeze waits link_rounds_max failed rounds
    # for a heard, unverified link, so a dead direction delays the freeze.
    net.run_until(20000)
    n1, n2, n3 = net.node(1), net.node(2), net.node(3)
    l = net.label_of_id
    assert {l(i) for i in n1.edges()} == {
        3
    }, "1, kendisini duymayan 2'yi kenar saymamalı"
    assert {l(i) for i in n2.edges()} == {3}, "2, LINK'i ulaşmayan 1'i kenar saymamalı"
    assert {l(i) for i in n3.edges()} == {1, 2}
    assert n1.deg == 1 and n2.deg == 1 and n3.deg == 2


def test_a_neighbour_seen_but_not_acked_is_in_the_table_yet_not_an_edge():
    net = BootNet({1: 5, 2: 3}, [(1, 2)], drop=lambda t, u, v, mt: not hello_only(mt))
    # Note to Amendment 15 (D2): the freeze waits link_rounds_max failed rounds
    # for a heard, unverified link, so a dead direction delays the freeze.
    net.run_until(20000)
    n1 = net.node(1)
    assert len(n1.nbrs) == 1, "HELLO duyulduğu için tabloda olmalı"
    assert list(n1.nbrs.values())[0].bidir is False
    assert n1.edges() == frozenset(), "ACK yoksa kenar yok"
    assert n1.deg == 0


def test_link_is_retried_with_backoff_and_then_given_up():
    net = BootNet({1: 5, 2: 3}, [(1, 2)], drop=lambda t, u, v, mt: not hello_only(mt))
    net.run_until(3000)
    p = BootstrapParams()
    assert net.counters(1).retx == p.link_max_attempts - 1
    # Note to Amendment 15 (D2): the freeze waits link_rounds_max failed rounds
    # for a heard, unverified link, so a dead direction delays the freeze.
    assert not net.node(1).done, "the next round is still owed"
    net.run_until(20000)
    assert net.node(1).nbrs and next(iter(net.node(1).nbrs.values())).link_rounds >= p.link_rounds_max
    assert net.node(1).done, "after link_rounds_max rounds the node settles"


def test_duplicate_link_ack_does_not_change_state():
    """api I5: aynı mesajın tekrarı durumu değiştirmez."""
    net = BootNet({1: 5, 2: 3}, [(1, 2)])
    net.run_until(2000)
    n1 = net.node(1)
    before = (n1.deg, n1.key, n1.stable_since_ms, n1.frozen_at_ms, n1.epoch)
    nbr = list(n1.nbrs.values())[0]
    for _ in range(4):
        n1.on_frame(nbr.mac, -60.0, a_ctrl(MsgType.LINK_ACK, nbr.nid, nbr.link_seq))
        n1.on_timer()
    assert (n1.deg, n1.key, n1.stable_since_ms, n1.frozen_at_ms, n1.epoch) == before


def test_a_link_frame_alone_does_not_create_a_neighbour():
    """Komşuluk YALNIZ HELLO ile kurulur; LINK yanıtlanır ama tablo açmaz."""
    net = BootNet({1: 5, 2: 3}, [(1, 2)])
    n1 = net.node(1)
    n1.on_frame(0x02DEADBEEF00, -60.0, a_ctrl(MsgType.LINK, 0x1234, 7))
    n1.on_timer()
    assert 0x1234 not in n1.nbrs


def test_a_link_ack_from_the_wrong_mac_cannot_open_an_edge():
    """ACK'in geldiği MAC tablodakiyle tutmalıdır; başka MAC kenar açamaz."""
    net = BootNet({1: 5, 2: 3}, [(1, 2)], drop=lambda t, u, v, mt: not hello_only(mt))
    net.run_until(300)
    n1 = net.node(1)
    nbr = list(n1.nbrs.values())[0]
    n1.on_frame(nbr.mac ^ 0xFF, -60.0, a_ctrl(MsgType.LINK_ACK, nbr.nid, nbr.link_seq))
    n1.on_timer()
    assert nbr.bidir is False
    assert n1.edges() == frozenset()


# ==========================================================================
# 6. RSSI histerezisi
# ==========================================================================
def oscillating_rssi(strong_until: int, hi: float = -76.0, lo: float = -84.0):
    def fn(t, u, v):
        if t < strong_until:
            return -60.0
        return hi if (t // 200) % 2 == 0 else lo

    return fn


def test_link_oscillating_between_the_two_thresholds_does_not_flap():
    """-75 ile -85 ARASINDA salınan link ne açılır ne kapanır: titreme yok."""
    p = BootstrapParams(rssi_ema_alpha=1.0)  # ham değer = EMA: saf histerezis
    net = BootNet(WEIGHTS, EDGES, params=p, rssi=oscillating_rssi(400))
    net.run_until(1000)
    snap = {
        l: (net.node(l).deg, net.node(l).key, net.node(l).frozen_at_ms)
        for l in net.labels
    }
    net.run_until(8000)
    for l in net.labels:
        n = net.node(l)
        assert (n.deg, n.key, n.frozen_at_ms) == snap[l], f"düğüm {l} titredi"
        assert n.epoch_bumps == 0, f"düğüm {l} salınım yüzünden epoch artırdı"
        assert n.deg == TRUE_DEG[l]


def test_link_below_the_open_threshold_never_becomes_an_edge():
    net = BootNet({1: 5, 2: 3}, [(1, 2)], rssi=lambda t, u, v: -80.0)
    net.run_until(3000)
    n1 = net.node(1)
    assert len(n1.nbrs) == 1, "HELLO duyuldu, tabloda"
    assert list(n1.nbrs.values())[0].link_up is False, "-80 dBm kapıyı açmaz"
    assert n1.deg == 0 and n1.edges() == frozenset()


def test_link_closes_below_the_close_threshold_and_bumps_the_epoch():
    net = BootNet(
        {1: 5, 2: 3}, [(1, 2)], rssi=lambda t, u, v: -60.0 if t < 1000 else -95.0
    )
    net.run_until(1000)
    assert net.node(1).deg == 1
    net.run_until(4000)
    n1 = net.node(1)
    assert list(n1.nbrs.values())[0].link_up is False
    assert n1.epoch_bumps >= 1, "kenar kaybı epoch artırmalıdır"
    assert n1.deg == 0


def test_hysteresis_thresholds_are_parametric():
    p = BootstrapParams(rssi_open_dbm=-90.0, rssi_close_dbm=-95.0, rssi_ema_alpha=1.0)
    net = BootNet({1: 5, 2: 3}, [(1, 2)], params=p, rssi=lambda t, u, v: -80.0)
    net.run_until(3000)
    assert net.node(1).deg == 1, "eşik gevşetilince aynı link kenar olmalı"


# ==========================================================================
# 7. Soft state
# ==========================================================================
def test_entry_is_dropped_after_three_missed_hello_periods():
    p = BootstrapParams()
    net = BootNet(
        {1: 5, 2: 3}, [(1, 2)], params=p, drop=lambda t, u, v, mt: t >= 1000 and u == 2
    )
    net.run_until(1000)
    n1 = net.node(1)
    assert n1.deg == 1 and len(n1.nbrs) == 1
    last_seen = list(n1.nbrs.values())[0].last_ms

    net.run_until(last_seen + p.t_stale_ms)
    assert len(n1.nbrs) == 1, "3*T_hello dolmadan giriş düşmemeli"

    net.run_until(last_seen + p.t_stale_ms + 5 * p.t_hello_ms)
    assert n1.nbrs == {}, "3*T_hello içinde yenilenmeyen giriş düşmeli"
    assert n1.epoch_bumps >= 1

    # The restart is now one stability window later than the drop: a
    # neighbourhood that differs from the frozen one has to STAY different for
    # `t_stab_ms` before it counts as a change (see `_gate`). Right after the
    # reset the node is in phase 0 with no key, so `deg` is None rather than 0;
    # it settles on the new degree once the window has passed.
    net.run_until(last_seen + p.t_stale_ms + 5 * p.t_hello_ms + 3 * p.t_stab_ms)
    assert n1.deg == 0


def test_soft_state_is_refreshed_by_every_hello():
    net = BootNet({1: 5, 2: 3}, [(1, 2)])
    net.run_until(5000)
    assert net.node(1).deg == 1, "periyodik HELLO girişi canlı tutmalı"
    assert net.node(1).epoch_bumps == 0


# ==========================================================================
# 8. Epoch
# ==========================================================================
def test_larger_epoch_is_adopted_and_resets_the_node_to_phase_zero():
    net = calibration_net()
    net.run_until(2000)
    assert net.node(7).phase == 1
    net.node(1).epoch = 9  # bir düğüm topolojide değişiklik gördü
    net.run_until(4000)  # max-gossip atlama başına bir T_hello ilerler
    for lab in net.labels:
        assert net.node(lab).epoch == 9, f"düğüm {lab} max-gossip ile 9'a gelmeli"
    net.run_until(9000)
    for lab in net.labels:
        n = net.node(lab)
        assert n.deg == TRUE_DEG[lab], "yeniden koşum aynı sonucu vermeli"
        assert round(from_fp(n.key[0]), 2) == EXPECTED_KEY[lab]


def test_epoch_comparison_survives_the_one_byte_wrap():
    assert epoch_newer(1, 0) and not epoch_newer(0, 1)
    assert epoch_newer(0, 255), "255 -> 0 sarmalaması ilerleme sayılmalı"
    assert not epoch_newer(255, 0)
    assert not epoch_newer(7, 7)


def test_epoch_is_bumped_when_the_bidir_set_changes_after_freezing():
    net = BootNet({1: 5, 2: 3, 3: 4}, [(1, 2), (1, 3)])
    net.run_until(2000)
    n1 = net.node(1)
    assert n1.deg == 2 and n1.epoch_bumps == 0
    net.set_drop(lambda t, u, v, mt: u == 3)
    net.run_until(8000)
    assert n1.epoch_bumps >= 1, "komşu kaybı yamanmaz, epoch artar"
    assert n1.deg == 1, "yeniden koşum yeni dereceyi vermeli"
    assert round(from_fp(n1.key[0]), 2) == round(5 / 2, 2)


def test_epoch_and_key_travel_inside_the_real_hello_frames():
    """Komşunun epoch ve anahtarını TEL ÜZERİNDEN öğreniyor muyuz?

    Düğüm 2'ye gerçekten teslim edilen çerçeveler yakalanıp çözülmektedir;
    yeniden kodlama yapılmamaktadır.
    """
    net = calibration_net()
    caught = []
    n2 = net.node(2)
    real_on_frame = n2.on_frame

    def spy(src, rssi, payload):
        if wire.peek_type(payload) is MsgType.HELLO:
            caught.append(wire.decode(payload))
        real_on_frame(src, rssi, payload)

    n2.on_frame = spy
    net.run_until(1000)
    net.node(1).epoch = 42
    net.run_until(2000)

    assert any(h.epoch == 42 for h in caught), "epoch HELLO ile taşınmalıdır"
    frozen = [h for h in caught if h.key is not None]
    assert frozen, "donmuş anahtar HELLO ile taşınmalıdır"
    # Epoch 42 benimsendikten sonra düğümler Faz 0'a döndüğü için anahtarları
    # yeniden bilinmez olur; tel üzerinde görülen anahtarın o anki donmuş
    # değerle tutarlı olduğunu donma anındaki kayıtla sınarız.
    for h in frozen:
        lab = net.label_of_id(h.src)
        assert lab is not None
        assert h.key == key_of(WEIGHTS[lab], TRUE_DEG[lab], h.src)[0]


# ==========================================================================
# 9. Sabit nokta: karar yolunda float yok (brief §3.6)
# ==========================================================================
def is_plain_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def test_key_of_is_exact_fixed_point_for_every_calibration_case():
    """Anahtar 16.16'dır ve 1 ULP içinde doğru yuvarlanmıştır.

    Karşılaştırma TAMAMEN tamsayı aritmetiğiyle yapılmaktadır (Fraction),
    yani testin kendisi de float kullanmamaktadır.
    """
    for lab, w in WEIGHTS.items():
        for deg in range(0, 65):
            fp, tie = key_of(w, deg, lab)
            assert is_plain_int(fp) and is_plain_int(tie)
            exact = Fraction(w * (1 << FP_SHIFT), deg + 1)
            assert abs(Fraction(fp) - exact) <= Fraction(1, 2), (w, deg, fp)


def test_no_float_ever_reaches_the_key_path():
    net = calibration_net()
    net.run_until(2000)
    for lab in net.labels:
        n = net.node(lab)
        # Değişmez "ağırlık tamsayıdır" DEĞİL; kıyas kümesinin 310/310'u
        # kesirli ağırlık taşıyor. Değişmez, ağırlığın sabit noktaya TAM
        # oturması ve ANAHTARIN tamsayı olmasıdır.
        assert is_plain_int(n.w_fp), "ağırlık sabit noktaya çevrilmiş olmalı"
        assert is_plain_int(n.deg)
        assert is_plain_int(n.key[0]) and is_plain_int(n.key[1])
        assert is_plain_int(n.key_fp)
        for nbr in n.nbrs.values():
            assert is_plain_int(nbr.key), "komşudan gelen anahtar da tamsayıdır"
        assert is_plain_int(wire.decode(n._hello_payload()).key)


def test_a_fractional_weight_is_accepted_and_stored_as_fixed_point():
    """Kesirli ağırlık REDDEDİLMEZ; sabit noktaya çevrilir.

    Eski kapı "tamsayı olmalı" diyordu ve brief §3.6'yı yanlış okuyordu:
    §3.6 sabit noktalı ARİTMETİK ister, tamsayı GİRDİ değil. Ölçüldü:
    Dagdeviren örneklerinin 310/310'u kesirli ağırlık taşıyor, yani o kapı
    bütün kıyas kümesini koşulamaz kılıyordu.
    """
    from ccvc.bb.api import from_fp, to_fp

    net = calibration_net()
    n = BootstrapNode(26.20965451126096, net.plats[1])
    assert n.w_fp == to_fp(26.20965451126096)
    assert is_plain_int(n.w_fp)
    assert abs(from_fp(n.w_fp) - 26.20965451126096) < 1e-4


def test_a_weight_that_cannot_be_represented_is_refused():
    net = calibration_net()
    with pytest.raises(TypeError):
        BootstrapNode(float("nan"), net.plats[1])
    with pytest.raises(ValueError):
        BootstrapNode(1e9, net.plats[1])


def test_the_node_derives_its_own_id_from_the_port_mac():
    net = calibration_net()
    for lab in net.labels:
        n = net.node(lab)
        assert n.mac == net.plats[lab].mac
        assert n.nid == hash16(n.mac), "id verilmez, MAC'ten türetilir"


def test_the_producer_refuses_a_float_key():
    """Bizim katmanımız float anahtarı asla tele vermez."""
    net = calibration_net()
    n = net.node(1)
    n.key = (1.67, n.nid)
    with pytest.raises(TypeError):
        n._hello_payload()


def test_the_wire_refuses_a_float_key():
    """Tel de float anahtarı REDDEDER (bb-core düzeltti; tripwire görevini yaptı).

    Sessiz zorlama olsaydı 1.67 tele 1 olarak yazılır, doğru 16.16 değeri olan
    109445 kaybolur ve bütün MIS sıralaması sessizce bozulurdu.
    """
    with pytest.raises(TypeError):
        wire.encode(wire.Hello(src=7, key=1.67, deg=3, role=Role.OUT, phase=1, load=0))
    assert to_fp(1.67) == 109445
    good = wire.encode(
        wire.Hello(src=7, key=to_fp(1.67), deg=3, role=Role.OUT, phase=1, load=0)
    )
    assert wire.decode(good).key == 109445


def test_key_comparison_is_integer_only_and_breaks_ties_by_id():
    a = key_of(2, 3, 11)
    b = key_of(2, 3, 4)
    assert a[0] == b[0] and b < a, "eşit anahtar id ile kırılır"


# ==========================================================================
# 10. Mesaj boyutu (api I3) ve serileştirme
# ==========================================================================
def test_hello_round_trips_and_stays_far_below_the_250_byte_limit():
    h = wire.Hello(
        src=0xBEEF,
        key=key_of(5, 2, 1)[0],
        deg=2,
        role=Role.MIS,
        phase=1,
        load=4,
        epoch=3,
        mis_nbrs=(1, 2, 3, 4, 5),
    )
    buf = wire.encode(h)
    assert len(a_hello(1)) == 13, "wire.py boş HELLO'yu 13 B'de tutmalı"
    assert len(buf) == 23, f"beş mis komşusuyla 23 B bekleniyor, {len(buf)} B çıktı"
    assert wire.decode(buf) == h


def test_hello_without_a_key_marks_it_invalid_rather_than_guessing():
    assert wire.decode(a_hello(1)).key is None
    assert wire.KEY_NONE == -(2**31), "key=None telde INT32_MIN ile taşınır"


def test_mis_nbrs_cap_is_enforced_by_the_producer_not_by_the_wire():
    """G8 sınırını kim dayatır? Tel değil, üretici.

    wire.py bilerek yalnız 250 B'yi dayatmaktadır; "en fazla 5 mis komşusu"
    birim disk çizgesine dair bir ÇİZGE olgusudur ve serileştirmenin işi
    değildir. Tel altı komşuyu KIRPMADAN kodlar (kırpma sessiz veri kaybı
    olurdu), üretici ise hata atar. İki özellik de burada sınanır.
    """
    six = (1, 2, 3, 4, 5, 6)
    buf = wire.encode(
        wire.Hello(src=1, key=None, deg=0, role=Role.OUT, phase=0, load=0, mis_nbrs=six)
    )
    assert wire.decode(buf).mis_nbrs == six, "tel KIRPMAMALI"

    net = calibration_net()
    with pytest.raises(ValueError):
        net.node(1)._hello_payload(mis_nbrs=six)
    assert wire.MIS_NBRS_SOFT_MAX == 5


def test_a_degree_too_wide_for_one_byte_is_an_error_at_the_producer():
    net = calibration_net()
    n = net.node(1)
    n.deg = 300
    with pytest.raises(ValueError):
        n._hello_payload()


def test_oversized_payload_is_an_error_not_a_trim():
    c = Counters()
    with pytest.raises(PayloadTooLarge):
        c.record_tx(int(MsgType.HELLO), 0, 251, 3)


def test_calibration_run_never_exceeds_the_payload_limit():
    net = calibration_net()
    net.run_until(2000)
    for lab in net.labels:
        assert 0 < net.counters(lab).max_payload <= 23


# ==========================================================================
# 11. Muhasebe: tx ve rx ayrıdır (DISCOVERY §3'ün düzelttiği hata)
# ==========================================================================
def test_broadcast_counts_one_tx_and_degree_many_rx():
    net = calibration_net()
    net.run_until(2000)
    agg_tx = sum(net.counters(l).tx for l in net.labels)
    agg_rx = sum(net.counters(l).rx for l in net.labels)
    assert agg_tx > 0 and agg_rx > agg_tx, "yayın rx'i dereceyle çarpar"
    hello_tx = sum(
        net.counters(l).by_type_tx.get(int(MsgType.HELLO), 0) for l in net.labels
    )
    assert hello_tx >= len(net.labels), "her düğüm en az bir HELLO yaymalı"


def test_radio_on_time_is_recorded_until_local_quiescence():
    net = calibration_net()
    net.run_until(2000)
    for lab in net.labels:
        c = net.counters(lab)
        assert c.radio_on_ms > 0
        assert c.energy_mah() > 0.0


# ==========================================================================
# 12. Yardımcılar ve sözleşme uyumu
# ==========================================================================
def test_boot_neighbour_is_still_an_api_neighbour():
    n = BootNeighbor(nid=5, mac=0x02AABBCCDDEE, last_ms=WALL_CLOCK_MS)
    assert isinstance(n, Neighbor)
    assert n.is_edge is False


def test_a_neighbour_record_cannot_be_built_without_a_timestamp():
    """api.py artık `last_ms`i ZORUNLU kılıyor; bu kapı çalışmalı.

    Varsayılan 0 yalnız sıfırdan başlayan bir saatte zararsızdır. Duvar
    saatinde 0 "sonsuz eski" demektir ve kayıt doğduğu anda yumuşak-durumdan
    düşer. Eski kod yalnız tesadüfen doğruydu: `last_ms = now` kurucudan
    birkaç satır sonra atanıyordu ve arada `return` yoktu.
    """
    with pytest.raises(TypeError):
        BootNeighbor(nid=5, mac=0x02AABBCCDDEE)
    with pytest.raises(TypeError):
        Neighbor(nid=5)


def test_the_node_always_stamps_new_neighbour_records():
    """Düğüm hiçbir kaydı damgasız kurmaz; saat nereden başlarsa başlasın."""
    net = calibration_net(epoch_ms=WALL_CLOCK_MS)
    net.run_until(WALL_CLOCK_MS + 2000)
    for lab in net.labels:
        for nbr in net.node(lab).nbrs.values():
            assert nbr.last_ms >= WALL_CLOCK_MS, "damga koşum saatinden olmalı"


def test_snapshot_matches_the_api_shape():
    net = calibration_net()
    net.run_until(2000)
    s = net.node(4).snapshot()
    assert s.nid == net.node(4).nid and s.phase == 1 and s.deg == 4
    assert s.role is Role.OUT and s.owned == () and s.forced_load == 0
    assert is_plain_int(s.key)


def test_t_hello_lower_bound_follows_the_channel_time_rule():
    """brief §3.6: T_hello >= N2 * t_f / rho_max."""
    assert t_hello_lower_bound_ms(30, 0.7, 0.1) == 210
    assert t_hello_lower_bound_ms(10, 0.7, 0.1) == 70
    assert BootstrapParams().t_hello_ms >= t_hello_lower_bound_ms(28, 0.7, 0.1)


def test_defaults_follow_the_brief():
    p = BootstrapParams()
    assert p.t_stab_ms == 3 * p.t_hello_ms
    assert p.t_stale_ms == 3 * p.t_hello_ms
    assert (p.rssi_open_dbm, p.rssi_close_dbm) == (-75.0, -85.0)
    assert p.nbr_table_max == 64


def test_xorshift32_never_collapses_to_zero():
    s = 0
    seen = set()
    for _ in range(1000):
        s = xorshift32(s)
        assert 0 < s <= 0xFFFFFFFF
        seen.add(s)
    assert len(seen) > 900


def test_neighbour_table_is_bounded_and_evicts_the_weakest():
    p = BootstrapParams(nbr_table_max=3)
    net = BootNet(
        {i: 2 for i in range(1, 8)},
        [(1, j) for j in range(2, 8)],
        params=p,
        rssi=lambda t, u, v: -95.0 + v,
    )
    net.run_until(1200)
    assert len(net.node(1).nbrs) <= 3, "statik tablo sınırı aşılmamalı"


def test_a_full_neighbour_table_corrupts_the_degree_and_says_so():
    """Tablo sınırının DÜRÜST bedeli: derece yanlış donar.

    Düşen komşu derece sayımına girmez, dolayısıyla anahtar da yanlış donar ve
    bunu doğru bir donmadan ayırt edecek başka hiçbir işaret yoktur. Tek işaret
    `table_overflow` sayacıdır; koşum betiği onu raporlamazsa yoğun bir
    topolojide sonuçlar SESSİZCE bozulur. Kapı testinin kardeşidir: sınırı
    güçlü göstermek yerine nerede bittiğini yazıya geçiririz.
    """
    true_deg = 6
    p = BootstrapParams(nbr_table_max=3)
    net = BootNet(
        {i: 2 for i in range(1, 8)},
        [(1, j) for j in range(2, 8)],
        params=p,
        rssi=lambda t, u, v: -95.0 + v,
    )
    net.run_until(2000)
    n1 = net.node(1)
    assert n1.table_overflow > 0, "taşma sayaca yazılmalı"
    assert n1.deg < true_deg, "taşan tablo dereceyi kırpar"
    assert n1.key != key_of(2, true_deg, n1.nid), "anahtar da yanlış donar"
    assert any(
        r["event"] in ("nbr_evicted", "nbr_table_full_drop")
        for r in net.sim.log_records
    ), "taşma günlüğe de düşmeli"


def test_a_healthy_run_reports_zero_table_overflow():
    net = calibration_net()
    net.run_until(2000)
    for lab in net.labels:
        assert net.node(lab).table_overflow == 0


def test_the_mis_nbrs_cap_is_a_parameter_because_g8_fails_off_udg():
    """G8 kıyas kümesinde geçmiyor, bu yüzden sınır sabit değil parametredir.

    Ölçüm (ekip lideri, Dagdeviren veri kümesi): en büyük bağımsız komşu sayısı
    n=25'te 6, n=200'de 17 ve n=200'de bütün düğümler 5'i aşmaktadır. Sabit 5
    dayatan bir uygulama kıyas kümesinde hiç koşamazdı.
    """
    assert BootstrapParams().mis_nbrs_max == 5, "UDG varsayılanı 5 kalmalı"

    net = calibration_net()
    with pytest.raises(ValueError):
        net.node(1)._hello_payload(mis_nbrs=tuple(range(6)))

    wide = BootNet(WEIGHTS, EDGES, params=BootstrapParams(mis_nbrs_max=17))
    wide.run_until(2000)
    n = wide.node(1)
    payload = n._hello_payload(mis_nbrs=tuple(range(17)))
    assert len(payload) == 13 + 2 * 17 == 47, "yoğunlukla büyüyen HELLO"
    assert len(payload) < 250, "yine de I3 sınırının çok altında"
    assert wire.decode(payload).mis_nbrs == tuple(range(17))
    with pytest.raises(ValueError):
        n._hello_payload(mis_nbrs=tuple(range(18)))


def test_hello_size_grows_linearly_off_udg_which_scopes_the_constant_size_claim():
    """brief §5'in 'yoğunluktan bağımsız' savının kapsam koşulu, sayıyla.

    250 B'ye ancak 118 mis komşusunda varılır, yani hiçbir şey kırılmaz; ama
    '250 B'ye sığar' ile 'sabit boyutlu' aynı sav değildir ve ikincisi yalnız
    UDG rejiminde doğrudur.
    """
    sizes = {
        k: len(
            wire.encode(
                wire.Hello(
                    src=1,
                    key=0,
                    deg=1,
                    role=Role.OUT,
                    phase=0,
                    load=0,
                    mis_nbrs=tuple(range(k)),
                )
            )
        )
        for k in (0, 5, 6, 9, 13, 17)
    }
    assert sizes == {0: 13, 5: 23, 6: 25, 9: 31, 13: 39, 17: 47}
    assert all(sizes[k] == 13 + 2 * k for k in sizes), "büyüme tam olarak doğrusal"
    biggest = max(k for k in range(0, 200) if 13 + 2 * k <= 250)
    assert biggest == 118, "250 B sınırına 118 mis komşusunda varılır"


def test_simnet_default_macs_give_distinct_ids():
    """Kalibrasyon kimlik çakışmasını TETİKLEMEMELİ; çakışma ayrı testin konusu."""
    for n in (10, 64, 200):
        assert len({hash16(default_mac(i)) for i in range(1, n + 1)}) == n


# ==========================================================================
# 13. Gerçek taşıma katmanı: bb-core'un SimNet'i üzerinde kalibrasyon
#     Diğer bütün testler BootNet sürücüsünden geçmektedir; bu test SimNet'i
#     hiçbir sarmalayıcı olmadan, doğrudan kurup sürerek sürücünün kendisinin
#     sonucu şekillendirmediğini gösterir.
# ==========================================================================
def test_calibration_also_converges_on_the_real_simnet():
    from ccvc.bb.simnet import SimNet, fixed_delay

    p = BootstrapParams()
    tick, delay = 20, 20
    net = SimNet(
        list(WEIGHTS),
        EDGES,
        delay=fixed_delay(delay),
        rssi_range=None,  # RSSI vermeyen platform: histerezis kapısı hep açık
    )
    nodes = {}
    for lab in WEIGHTS:
        node = BootstrapNode(WEIGHTS[lab], net.port(lab), p)
        net.attach(lab, node)
        nodes[lab] = node

    # Gecikme tam bir tick olduğundan bu, `drain_all`'ın belgelenmiş senkron
    # kullanımıdır: slot sınırında kuyruk boşaltılır, t_ms yok sayılır.
    t = 0
    while t <= 2000:
        net.set_now(t)
        for d in net.drain_all():
            net.deliver(d)
        for lab in sorted(nodes):
            nodes[lab].on_timer("tick")
            if nodes[lab].done:
                net.mark_done(lab, t)
        t += tick

    id_to_lab = {nodes[lab].nid: lab for lab in nodes}
    assert len(id_to_lab) == len(nodes), "SimNet'in MAC'leri id çakışması vermemeli"
    for lab, n in nodes.items():
        assert n.deg == TRUE_DEG[lab], f"düğüm {lab} derecesi (SimNet)"
        assert round(from_fp(n.key[0]), 2) == EXPECTED_KEY[lab], f"düğüm {lab} anahtarı"
        assert {id_to_lab[i] for i in n.edges()} == set(net.neighbors(lab))
        assert n.epoch_bumps == 0


def test_the_real_port_exposes_mac_but_never_the_node_id():
    """bb-core'un port'u kimlik vermez; verseydi hash16'yı atlayabilirdik."""
    from ccvc.bb.simnet import SimNet

    net = SimNet([1, 2], [(1, 2)])
    port = net.port(1)
    assert port.mac == net.mac_of(1)
    assert not hasattr(port, "nid"), "port kimlik vermemeli (I1)"
    node = BootstrapNode(5, port)
    assert node.nid == hash16(net.mac_of(1))


def test_unicast_to_an_unknown_mac_is_silent_on_the_real_simnet():
    """Bilinmeyen MAC ile komşu olmayan MAC ayırt edilemez: ikisi de sessiz."""
    from ccvc.bb.simnet import SimNet

    net = SimNet([1, 2, 3], [(1, 2)])
    port = net.port(1)
    before = net.counters[1].tx
    port.send_unicast(0xFFFFFFFFFFFF, a_ctrl(MsgType.LINK, 1, 1))
    port.send_unicast(net.mac_of(3), a_ctrl(MsgType.LINK, 1, 1))
    assert net.counters[1].tx == before + 2, "ikisi de bir iletim maliyeti"
    assert net.counters[1].rx == 0, "ikisi de sıfır teslim"


# ==========================================================================
# 14. Tek kodlayıcı: bootstrap'ın yaydığı çerçeve wire.py ile ÇÖZÜLEBİLMELİ
#     Bir zamanlar iki HELLO kodlayıcısı vardı ve iki test takımı da bunu
#     göremiyordu, çünkü her biri kendi kodlayıcısını sınıyordu. Aşağıdaki
#     test o boşluğu kalıcı olarak kapatır: üretilen bayt, ORTAK çözücüden
#     geçer ve alanları beklenen değerleri taşır.
# ==========================================================================
def test_frames_emitted_by_bootstrap_decode_with_the_shared_wire_codec():
    net = calibration_net()
    net.run_until(2000)
    n = net.node(4)

    h = wire.decode(n._hello_payload())
    assert isinstance(h, wire.Hello)
    assert (h.src, h.deg, h.key, h.epoch, h.phase) == (n.nid, 4, n.key[0], 0, 1)
    assert round(from_fp(h.key), 2) == EXPECTED_KEY[4]

    c = wire.decode(wire.encode(wire.Ctrl(MsgType.LINK, n.nid, 9)))
    assert (c.mtype, c.src, c.seq) == (MsgType.LINK, n.nid, 9)


def test_bootstrap_module_contains_no_second_serialiser():
    """`ccvc/bb/bootstrap.py` artık hiçbir mesaj alanını kendisi paketlemez."""
    src = open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap.py")
    ).read()
    for forbidden in (
        "struct.pack",
        "struct.unpack",
        "struct.Struct",
        "struct.calcsize",
    ):
        assert forbidden not in src, f"ikinci bir kodlayıcı geri geldi: {forbidden}"
    for name in ("encode_hello", "decode_hello", "encode_link", "decode_link"):
        assert name not in src, f"silinmiş kodlayıcı geri geldi: {name}"


def test_message_type_is_readable_without_decoding_the_body():
    """wire.py tipi payload[0]'a koyar; simnet tip başına muhasebeyi buna dayar."""
    for payload, expected in (
        (a_hello(1), MsgType.HELLO),
        (a_ctrl(MsgType.LINK, 1, 1), MsgType.LINK),
        (a_ctrl(MsgType.LINK_ACK, 1, 1), MsgType.LINK_ACK),
    ):
        assert payload[0] == int(expected)
        assert wire.peek_type(payload) is expected


# ==========================================================================
# 15. Günlük gerçekten ULAŞIYOR mu?
#     `_log` bir zamanlar `nid=` alanı gönderiyor ve bu SimNet'in
#     `_record_log(nid, event, **fields)` imzasıyla çakışıyordu; üstelik
#     `except Exception: pass` hatayı yutuyordu. Sonuç: düğümün YAYDIĞI HER
#     GÜNLÜK SATIRI sessizce düşüyordu ve `retx` hep 0 kalıyordu. Hiçbir test
#     bunu görmüyordu, çünkü hepsi düğüm durumuna bakıyordu, günlüğe değil.
# ==========================================================================
def test_node_log_lines_actually_reach_the_platform():
    net = calibration_net()
    net.run_until(2000)
    events = {r["event"] for r in net.sim.log_records}
    assert "bidir" in events, "çift yön doğrulaması günlüğe düşmeli"
    assert "key_frozen" in events, "anahtar dondurma günlüğe düşmeli"
    for rec in net.sim.log_records:
        assert rec["nid"] in net.labels
        assert isinstance(rec["t_ms"], int)


def test_retx_is_derived_from_the_log_not_reported_by_the_node():
    """api sözleşmesi: düğüm kendi sayacını raporlamaz, `log("retx", n=...)` der."""
    net = BootNet({1: 5, 2: 3}, [(1, 2)], drop=lambda t, u, v, mt: not hello_only(mt))
    net.run_until(3000)
    p = BootstrapParams()
    # log_records AĞ GENELİNDEDİR; her iki düğüm de yeniden dener, o yüzden süz.
    retx_logs = [
        r for r in net.sim.log_records if r["event"] == "retx" and r["nid"] == 1
    ]
    assert len(retx_logs) == p.link_max_attempts - 1
    assert [r["attempt"] for r in retx_logs] == [2, 3], "üstel geri çekilme sırası"
    assert net.counters(1).retx == p.link_max_attempts - 1
    assert net.counters(1).by_type_tx[int(MsgType.LINK)] == p.link_max_attempts


def test_the_node_never_writes_to_a_counter_itself():
    """Sayaçlar günlükten türetilir; düğüm koduna sayaç ataması giremez."""
    code = _code_without_comments_or_strings(inspect.getsource(BootstrapNode))
    for forbidden in ("counters.retx", "counters.tx", "counters.rx", "record_tx"):
        assert forbidden not in code, f"düğüm sayaca yazıyor: {forbidden}"


# ==========================================================================
# 16. Her yeniden gönderim sayılır mı?
#     Sayaç temiz okurken kanalın gerçekten tekrar iletmesi, ölçümün en
#     sinsi arıza biçimidir: %15 kayıplı koşumda kanal sağlıklı görünür ve
#     makaledeki bütün mesaj maliyeti olduğundan küçük çıkar.
# ==========================================================================
def _retx_kinds(net, label):
    out = {}
    for r in net.sim.log_records:
        if r["event"] == "retx" and r["nid"] == label:
            out[r["kind"]] = out.get(r["kind"], 0) + 1
    return out


def test_a_repeated_link_ack_is_counted_as_a_retransmission():
    """ACK kaybolunca akran LINK'i tekrarlar; bizim İKİNCİ ACK'imiz de retx'tir.

    Yalnız LINK_ACK çerçeveleri düşürülmektedir, dolayısıyla LINK'ler varır:
    her iki düğüm de hem kendi LINK'ini yeniden gönderir hem de aynı seq için
    tekrar tekrar ACK üretir. İkisi de sayılmalıdır.
    """
    p = BootstrapParams()
    net = BootNet(
        {1: 5, 2: 3},
        [(1, 2)],
        drop=lambda t, u, v, mt: mt == int(MsgType.LINK_ACK),
    )
    net.run_until(3000)

    for lab in (1, 2):
        kinds = _retx_kinds(net, lab)
        assert kinds.get("link") == p.link_max_attempts - 1, f"düğüm {lab} LINK tekrarı"
        assert kinds.get("link_ack", 0) >= 1, f"düğüm {lab} tekrar ACK'i sayılmadı"
        assert net.counters(lab).retx == sum(kinds.values())

    # Muhasebe kimliği: gönderilen her LINK_ACK ya bir ilk ACK ya bir tekrardır.
    acks = net.counters(1).by_type_tx[int(MsgType.LINK_ACK)]
    assert acks == 1 + _retx_kinds(net, 1)["link_ack"]


def test_no_retransmission_is_reported_on_a_clean_channel():
    """Tersi de doğru olmalı: kayıpsız koşumda retx sıfırdır."""
    net = calibration_net()
    net.run_until(2000)
    for lab in net.labels:
        assert net.counters(lab).retx == 0
        assert _retx_kinds(net, lab) == {}


def test_every_send_site_is_either_a_first_send_or_logs_retx():
    """Sessiz bir yeniden gönderim yolu EKLENEMESİN diye yapısal bekçi.

    Sınıftaki her port gönderimi, aşağıdaki listede adı geçen bir yöntemin
    içindedir. Listedeki her yöntem ya ilk gönderimdir ya da retx günlükler.
    Yeni bir gönderim yolu eklendiğinde bu test kırılır ve ekleyen kişi
    hangisi olduğuna karar vermek zorunda kalır.
    """
    tree = ast.parse(inspect.getsource(BootstrapNode))
    # Amendment 13, G2(b): a LINK heard before its asker's HELLO is answered
    # from `_on_hello` when the HELLO opens the record; that is a first send.
    first_send = {"_bcast", "_ucast", "_maybe_hello", "_start_link", "_on_hello"}
    retransmits = {"_retry_links", "_on_link"}

    senders = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        body = _code_without_comments_or_strings(ast.unparse(fn))
        if "_ucast(" in body or "_bcast(" in body or ".send_unicast(" in body:
            senders[fn.name] = body
    assert set(senders) == first_send | retransmits, set(senders)

    for name in retransmits:
        assert "retx" in ast.unparse(
            next(
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == name
            )
        ), f"{name} yeniden gönderiyor ama retx günlüklemiyor"


def test_the_wire_refuses_a_float_role_which_the_enum_would_have_accepted():
    """Rol monotonluğu (api I5) sessiz bir tip zorlamasıyla bozulabilirdi.

    `Role(2.0)` HATA VERMEZ: enum araması 2.0'ı 2 ile aynı hash'ler ve
    sessizce Role.CONNECTOR döner. Yalnız tam tip denetimi yakalar. Anahtar
    için geçerli olan aynı gerekçe rol için de geçerlidir: sessizce kaymış
    bir rol, sessizce kaymış bir anahtarla aynı sınıf hasardır.
    """
    assert Role(2.0) is Role.CONNECTOR, "enum kendi başına korumuyor"
    with pytest.raises(TypeError):
        wire.encode(wire.Hello(src=1, key=None, deg=1, role=2.0, phase=0, load=0))
    with pytest.raises(ValueError):
        wire.encode(
            wire.Hello(src=1, key=2**40, deg=1, role=Role.OUT, phase=0, load=0)
        )


# ==========================================================================
# 17. Taşma koşumu GEÇERSİZ kılar; yalnız günlüğe yazılmaz.
#     Kırpılmış tablodan donan derece anahtarı zehirler, anahtar MIS'i
#     sıralar, MIS omurgayı belirler: tek bir taşma bütün bileşenin cevabını
#     sessizce değiştirir. Sessizce yanlış bir sonucu raporlamaktansa
#     raporlamayı reddetmek yeğdir.
# ==========================================================================
from ccvc.bb.bootstrap import validate_bootstrap  # noqa: E402


def _overflowing_net():
    return BootNet(
        {i: 2 for i in range(1, 8)},
        [(1, j) for j in range(2, 8)],
        params=BootstrapParams(nbr_table_max=3),
        rssi=lambda t, u, v: -95.0 + v,
    )


def test_a_healthy_run_validates_and_reports_valid():
    net = calibration_net()
    net.run_until(2000)
    validate_bootstrap(net.nodes.values())  # atmamalı
    rep = bootstrap_report(net.nodes.values())
    assert rep["valid"] == 1
    assert rep == {
        "nodes": 10,
        "frozen": 10,
        "table_overflow": 0,
        "epoch_bumps": 0,
        "id_rederivations": 0,
        "valid": 1,
    }


def test_a_single_table_overflow_invalidates_the_whole_run():
    net = _overflowing_net()
    net.run_until(2000)

    assert net.node(1).invalid_reasons, "taşan düğüm kendini güvenilmez ilan etmeli"
    assert bootstrap_report(net.nodes.values())["valid"] == 0

    with pytest.raises(RunInvalid) as e:
        validate_bootstrap(net.nodes.values())
    assert "nbr_table_max=3" in str(e.value), "hata nedeni ve sınırı adıyla söylemeli"
    assert str(net.node(1).nid) in str(e.value), "hangi düğüm olduğunu söylemeli"


def test_validation_is_a_raise_not_a_flag_the_caller_may_ignore():
    """Sessiz bir alan değil, koşumu durduran bir hata olduğunu sabitler."""
    net = _overflowing_net()
    net.run_until(2000)
    assert isinstance(RunInvalid("x"), RuntimeError)
    try:
        validate_bootstrap(net.nodes.values())
        raised = False
    except RunInvalid:
        raised = True
    assert raised, "taşma sessizce geçemez"


def test_the_measured_worst_case_degree_fits_the_table_with_margin():
    """ÖLÇÜLDÜ: Dagdeviren veri kümesinin tamamı (54 grup, n=10..1000).

    En büyük derece 36 (n=150/m=1500'de 35, n=500/m=5000'de 36); 64'ü aşan
    tek bir düğüm yok. Sayıyı burada sabitliyoruz ki "sorun beklemiyoruz"
    değil "en kötü durumu ölçtük" savı koda bağlı kalsın ve varsayılan
    düşürülürse test kırılsın.
    """
    MEASURED_MAX_DEGREE = 36
    cap = BootstrapParams().nbr_table_max
    assert cap == 64
    assert MEASURED_MAX_DEGREE < cap, "tablo kıyas kümesinde bağlayıcı değil"
    assert cap - MEASURED_MAX_DEGREE == 28, "ölçülen pay"
    assert MEASURED_MAX_DEGREE <= 0xFF, "tel üzerindeki bir baytlık deg alanı"


# ==========================================================================
# 18. Gerçek saat: düğüm SIFIRDAN BAŞLAMAYAN bir saat altında da doğru olmalı
#     Sanal saat 0'dan başladığı için bu sınıf hata simülasyonda tamamen
#     görünmezdi ve 461 test üzerinden geçti. Emülatör ilk tıkta yakaladı.
# ==========================================================================
WALL_CLOCK_MS = 1_763_000_000_000  # tipik bir Unix epoch ms değeri


def test_a_wall_clock_start_does_not_open_the_gate_on_the_first_tick():
    """Hata buydu: `stable_since_ms = 0` iken `now - 0` ilk tıkta ~1.7e12 ms.

    Kapı anında açılır ve her düğüm HENÜZ KİMSEYİ DUYMADAN deg=0 ile
    anahtarını dondurur. Kendini onarır, çünkü ilk çift yönlü komşu kümeyi
    değiştirip sıfırlama tetikler; ama kendini onarmak kapının çalışması
    değildir. Kapı tam da yanlış anahtarın donmasını engellemek için vardır.
    """
    net = calibration_net(epoch_ms=WALL_CLOCK_MS)

    net.run_until(WALL_CLOCK_MS + net.tick_ms)  # YALNIZCA ilk tık
    for lab in net.labels:
        n = net.node(lab)
        assert n.phase == 0, f"düğüm {lab} ilk tıkta dondu"
        assert n.key is None, f"düğüm {lab} kimseyi duymadan anahtar dondurdu"
        assert n.deg is None

    net.run_until(WALL_CLOCK_MS + 4000)
    for lab in net.labels:
        n = net.node(lab)
        assert n.deg == TRUE_DEG[lab], f"düğüm {lab} derecesi"
        assert round(from_fp(n.key[0]), 2) == EXPECTED_KEY[lab]
        assert n.epoch_bumps == 0, "sahte donma olmadığı için sıfırlama da olmamalı"
        assert n.table_overflow == 0
    validate_bootstrap(net.nodes.values())


def test_the_gate_costs_the_same_three_periods_under_either_clock():
    """Kapının bedeli saatin nereden başladığına bağlı OLMAMALI."""
    p = BootstrapParams()
    zero = calibration_net(params=p)
    zero.run_until(4000)
    wall = calibration_net(params=p, epoch_ms=WALL_CLOCK_MS)
    wall.run_until(WALL_CLOCK_MS + 4000)
    for lab in zero.labels:
        a = zero.node(lab).frozen_at_ms
        b = wall.node(lab).frozen_at_ms - WALL_CLOCK_MS
        assert a == b, f"düğüm {lab}: sanal {a} ms, duvar {b} ms"


def test_soft_state_and_backoff_also_survive_a_wall_clock():
    """Süpürme: 0 tabanlı DİĞER zamanlayıcılar da yanlış davranmamalı.

    `last_ms`ın api varsayılanı 0'dır ve duvar saatinde 0 "sonsuz eski"
    demektir; giriş doğduğu anda soft-state ile düşerdi. Geri çekilme
    son tarihi de aynı şekle sahiptir.
    """
    p = BootstrapParams()
    net = BootNet({1: 5, 2: 3}, [(1, 2)], params=p, epoch_ms=WALL_CLOCK_MS)
    net.run_until(WALL_CLOCK_MS + 2000)
    n1 = net.node(1)
    assert n1.deg == 1, "giriş anında düşmüş olmamalı"
    assert list(n1.nbrs.values())[0].last_ms >= WALL_CLOCK_MS
    assert n1.epoch_bumps == 0

    lossy = BootNet(
        {1: 5, 2: 3},
        [(1, 2)],
        params=p,
        epoch_ms=WALL_CLOCK_MS,
        drop=lambda t, u, v, mt: not hello_only(mt),
    )
    lossy.run_until(WALL_CLOCK_MS + 3000)
    assert lossy.counters(1).retx == p.link_max_attempts - 1, "geri çekilme tabanı"


def test_no_clock_baseline_is_initialised_to_zero():
    """Yapısal bekçi: bu hata sınıfı GERİ GELEMESİN.

    `__init__` içinde adı `_ms` ile biten hiçbir alan 0 sabitiyle
    başlatılamaz. Sıfır yalnız saati sıfırdan başlayan bir saat altında
    doğrudur ve o varsayım tam olarak hatanın kendisiydi. Doğru başlangıç
    `None`'dır; taban ilk gözlemlenen `now_ms()`ten kurulur.
    """
    init = next(
        n
        for n in ast.walk(ast.parse(inspect.getsource(BootstrapNode)))
        if isinstance(n, ast.FunctionDef) and n.name == "__init__"
    )
    offenders = []
    for node in ast.walk(init):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.attr for t in targets if isinstance(t, ast.Attribute)]
        val = node.value
        if isinstance(val, ast.Constant) and val.value == 0:
            offenders += [n for n in names if n.endswith("_ms")]
    assert offenders == [], f"sıfır tabanlı zaman alanı: {offenders}"

    # Dedektörün boş geçmediğini göster.
    mutant = ast.parse(
        "class X:\n    def __init__(self):\n        self.stable_since_ms = 0\n"
    )
    bad = [
        t.attr
        for n in ast.walk(mutant)
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Constant)
        and n.value.value == 0
        for t in n.targets
        if isinstance(t, ast.Attribute) and t.attr.endswith("_ms")
    ]
    assert bad == ["stable_since_ms"], "dedektör ihlali yakalamıyor"


# ==========================================================================
# 19. Taban, `on_timer`ı EZEN bir alt sınıfta da kurulmalı.
#     `BbcvcNode.on_timer` bilerek ezilmiştir ve `super()` çağırmaz, bu yüzden
#     tabanı yalnız taban `on_timer`ında kurmak üretimde hiç koşmayan bir satır
#     demekti (ölçen: bb-mnwifi). Garanti artık `_gate`tedir: kapıya giden her
#     yol oradan geçer, dolayısıyla hiçbir ezen sözleşmeyi unutamaz.
# ==========================================================================
class _OverridingNode(BootstrapNode):
    """`super().on_timer()` ÇAĞIRMAYAN bir alt sınıf: üretimdeki biçim."""

    def on_timer(self, name: str = "tick") -> None:
        now = self.plat.now_ms()
        before = self._bidir_ids()
        self._drain_rx(now)
        self._expire(now)
        self._retry_links(now)
        self._maybe_hello(now)
        after = self._bidir_ids()
        if after != before:
            self.stable_since_ms = now
        self._gate(now, after)


def test_an_override_that_skips_super_still_gets_a_clock_baseline():
    p = BootstrapParams()
    net = BootNet({1: 5, 2: 3}, [(1, 2)], params=p, epoch_ms=WALL_CLOCK_MS)
    for lab in net.labels:
        port = net.plats[lab]
        node = _OverridingNode({1: 5, 2: 3}[lab], port, p)
        net.nodes[lab] = node
        net.sim.attach(lab, node)

    net.run_until(WALL_CLOCK_MS + net.tick_ms)
    for lab in net.labels:
        n = net.node(lab)
        assert n.key is None, "ezen alt sınıf ilk tıkta dondu"
        assert n._t0_ms == WALL_CLOCK_MS, "taban ezenin yolunda da kurulmalı"

    net.run_until(WALL_CLOCK_MS + 4000)
    for lab in net.labels:
        n = net.node(lab)
        assert n.deg == 1 and n.epoch_bumps == 0
        assert n.key == key_of({1: 5, 2: 3}[lab], 1, n.nid)


def test_an_isolated_node_still_freezes_degree_zero_after_t_stab():
    """Hiç çift yönlü komşu edinmeyen düğüm pencereyi yine de kurmalı.

    Tabanı YALNIZ "küme değişti" satırına bırakmak bu düğümde hiç koşmaz ve
    kapı sonsuza dek kapalı kalırdı: deg=0 dondurmaktan daha güvenli ama
    doğru da değil, çünkü yalıtılmış bir düğümün doğru cevabı deg=0'dır.
    """
    p = BootstrapParams()
    for epoch in (0, WALL_CLOCK_MS):
        net = BootNet(
            {1: 5, 2: 3},
            [(1, 2)],
            params=p,
            epoch_ms=epoch,
            drop=lambda t, u, v, mt: True,
        )
        net.run_until(epoch + 4000)
        n = net.node(1)
        assert n.phase == 1, f"epoch={epoch}: yalıtılmış düğüm kapıda takıldı"
        assert n.deg == 0
        assert n.key == key_of(5, 0, n.nid)
        assert n.frozen_at_ms == epoch + p.t_stab_ms, "bedel tam T_stab olmalı"


def test_reaching_the_gate_by_any_route_establishes_the_baseline():
    """Değişmez DAVRANIŞLA sınanır, kaynak metniyle DEĞİL.

    Önceki sürüm `_gate`in kaynağında "_establish_clock_baseline" arıyordu.
    Bu, düzeltmenin NEREYE yazıldığını sabitler, DEĞİŞMEZİN GEÇERLİ OLUP
    OLMADIĞINI değil: garanti aynı derecede geçerli başka bir yere taşınsa
    test yeşil kalırdı. bb-mnwifi'nin `"_t0_ms" not in getsource(...)` testi
    tam olarak bu yüzden hatayı kaçırdı. Doğru soru: kapıya varan HERHANGİ
    bir yol tabanı kuruyor mu?
    """
    net = calibration_net(epoch_ms=WALL_CLOCK_MS)
    n = net.node(1)
    assert n.stable_since_ms is None and n._t0_ms is None, "kurulmadan önce None"
    n._gate(WALL_CLOCK_MS, frozenset())
    assert n._t0_ms == WALL_CLOCK_MS and n.stable_since_ms == WALL_CLOCK_MS


class _GateOnlyNode(BootstrapNode):
    """`on_timer`ı tamamen ezip YALNIZ kapıyı çağıran en uç alt sınıf.

    Taban kurulumu kapıdan başka bir yere taşınırsa bu düğüm asla donmaz;
    testi geçiren şey kaynakta bir ad değil, gözlenen davranıştır.
    """

    def on_timer(self, name: str = "tick") -> None:
        self._gate(self.plat.now_ms(), self._bidir_ids())


def test_a_subclass_that_calls_only_the_gate_still_freezes_correctly():
    p = BootstrapParams()
    net = BootNet({1: 5}, [], params=p, epoch_ms=WALL_CLOCK_MS)
    node = _GateOnlyNode(5, net.plats[1], p)
    net.nodes[1] = node
    net.sim.attach(1, node)

    net.run_until(WALL_CLOCK_MS + net.tick_ms)
    assert node.key is None, "ilk tıkta donmamalı"

    net.run_until(WALL_CLOCK_MS + 4000)
    assert node.phase == 1, "kapıya varan tek yol bile tabanı kurmalı"
    assert node.deg == 0 and node.key == key_of(5, 0, node.nid)
    assert node.frozen_at_ms == WALL_CLOCK_MS + p.t_stab_ms


class _BrokenBaselineNode(BootstrapNode):
    """Uzantı noktasını ezip tabanı KURMAYAN sınıf: sözleşme ihlali."""

    def _establish_clock_baseline(self, now: int) -> None:
        pass  # bilerek hiçbir şey yapmıyor


def test_a_subclass_that_breaks_the_baseline_contract_fails_by_name():
    """Çökerek saptamak yerine ADIYLA saptamak.

    Eskiden bu durum `now - None` aritmetiğinde ham bir TypeError veriyordu;
    saptanıyordu ama hangi sözleşmenin çiğnendiğini söylemiyordu.
    """
    from ccvc.bb.bootstrap import ClockBaselineMissing

    net = calibration_net(epoch_ms=WALL_CLOCK_MS)
    node = _BrokenBaselineNode(5, net.plats[1], BootstrapParams())
    with pytest.raises(ClockBaselineMissing, match="_BrokenBaselineNode"):
        node._gate(WALL_CLOCK_MS, frozenset())


# ==========================================================================
# 7b. READINGS THE RADIO CANNOT HAVE PRODUCED, AND NEIGHBOURHOODS THAT BLINK
#
# Both defects were found on real Mininet-WiFi runs and are written up in
# BULGULAR_BB.md §92. They share one shape: something that is not a real
# change was allowed to tear the whole network down.
# ==========================================================================
def test_an_impossible_rssi_reading_may_not_close_the_gate():
    """A positive dBm reading is a wrapped byte, not a weak signal.

    MEASURED on n15_m90 seed 1: the embedding placed two stations 0.036 m
    apart and each read the other over the WHOLE int8 range, -128 to +127,
    while all thirteen of their other peers read one constant value. Fed to
    the hysteretic gate that toggled the link roughly every 1.2 s, and each
    toggle reset the network: 148 local toggles, 2057 network-wide resets.
    """
    net = BootNet({1: 5, 2: 3}, [(1, 2)],
                  params=BootstrapParams(rssi_ema_alpha=1.0),
                  rssi=lambda t, u, v: 120.0 if t < 100 else -128.0)
    net.run_until(4000)
    n1 = net.node(1)
    # Condemned ONCE, not per sample, and the -128 dBm samples that follow are
    # ignored rather than being read as a signal that has gone away.
    assert n1.rssi_implausible == 1
    assert list(n1.nbrs.values())[0].rssi_untrusted is True
    assert list(n1.nbrs.values())[0].link_up is True
    assert n1.deg == 1
    assert n1.epoch_bumps == 0


def test_a_believable_weak_signal_still_closes_the_gate():
    """The guard must not turn the gate off for readings that ARE possible."""
    net = BootNet({1: 5, 2: 3}, [(1, 2)],
                  params=BootstrapParams(rssi_ema_alpha=1.0),
                  rssi=lambda t, u, v: -60.0 if t < 1000 else -95.0)
    net.run_until(4000)
    n1 = net.node(1)
    assert n1.rssi_implausible == 0
    assert list(n1.nbrs.values())[0].link_up is False
    assert n1.deg == 0


def test_a_neighbourhood_that_blinks_and_returns_does_not_restart_the_network():
    """Phase 1 now applies the stability test phase 0 always applied.

    MEASURED on n20_m160 seed 1: t_hello is 132 ms and an entry expires after
    three of them, 396 ms, but with twenty stations sharing the medium the gap
    between receptions reached 800 ms. Entries expired and came straight back,
    and 62 local changes became 458 network-wide resets.
    """
    p = BootstrapParams(rssi_ema_alpha=1.0)
    blink = 0.4 * p.t_stab_ms
    net = BootNet({1: 5, 2: 3}, [(1, 2)], params=p,
                  rssi=lambda t, u, v: -95.0 if 1000 <= t < 1000 + blink else -60.0)
    net.run_until(4000)
    n1 = net.node(1)
    assert n1.epoch_bumps == 0, "t_stab içinde dönen komşu ağı sıfırlamaz"
    assert n1.deg == 1


def test_a_neighbour_that_really_leaves_still_restarts_the_network():
    """The window delays the restart; it must not swallow it."""
    p = BootstrapParams(rssi_ema_alpha=1.0)
    net = BootNet({1: 5, 2: 3}, [(1, 2)], params=p,
                  rssi=lambda t, u, v: -60.0 if t < 1000 else -95.0)
    net.run_until(1000 + 4 * p.t_stab_ms)
    n1 = net.node(1)
    assert n1.epoch_bumps >= 1
    assert n1.deg == 0


# --------------------------------------------------------------------------
# AN EXHAUSTED HANDSHAKE MUST NOT BE PERMANENT
#
# The one-shot rule stops a unicast flood and is kept. Making the failure
# permanent, however, relied on a recovery that cannot happen: the entry was
# supposed to drop through soft state and re-open, but the entry only drops
# when the neighbour goes silent, and a neighbour that keeps sending HELLOs
# keeps it fresh. MEASURED at five per cent loss on the n=20 graph the stations
# saw: node 16's entry for node 9 stayed `link_failed` while node 9 still
# considered the edge up, so node 16 could not answer node 9's TEST and the
# fragment never reported.
# --------------------------------------------------------------------------
def test_an_exhausted_handshake_is_retried_after_the_cooldown():
    p = BootstrapParams()
    assert p.link_retry_after_ms > p.t_stale_ms, (
        "bekleme süresi soft-state penceresinden uzun olmalı, yoksa kural "
        "HELLO başına yeniden denemeye dönüşür")
    # Every LINK_ACK is lost, so the handshake exhausts; the entry stays fresh
    # because HELLOs keep arriving, which is exactly the case the permanent
    # failure could never recover from.
    net = BootNet({1: 5, 2: 3}, [(1, 2)], params=p,
                  drop=lambda t, u, v, mt: mt == int(MsgType.LINK_ACK))
    net.run_until(2 * p.link_retry_after_ms)
    n1 = net.node(1)
    nbr = list(n1.nbrs.values())[0]
    assert nbr.link_failed, "üç deneme tükenmeliydi"
    first_deadline = nbr.link_retry_ms

    net.run_until(6 * p.link_retry_after_ms)

    nbr = list(n1.nbrs.values())[0]
    # A second give-up moves the deadline; a permanently failed entry never
    # would. `link_attempts` is NOT the witness: `_start_link` resets it to 1.
    assert nbr.link_retry_ms > first_deadline, (
        "bekleme dolunca el sıkışma yeniden denenmeli")


def test_the_cooldown_does_not_become_a_retry_per_hello():
    """The flood the one-shot rule prevents must stay prevented."""
    p = BootstrapParams()
    net = BootNet({1: 5, 2: 3}, [(1, 2)], params=p,
                  drop=lambda t, u, v, mt: mt == int(MsgType.LINK_ACK))
    net.run_until(2 * p.link_retry_after_ms)
    first = list(net.node(1).nbrs.values())[0].link_retry_ms
    net.run_until(8 * p.link_retry_after_ms)
    last = list(net.node(1).nbrs.values())[0].link_retry_ms

    rounds = (last - first) / p.link_retry_after_ms
    assert rounds <= 8, f"{rounds} tur: bekleme süresi pacing yapmıyor"
    assert rounds >= 1, "hiç yeniden denenmemiş"
