#!/usr/bin/env python3
"""Tests for the mininet-wifi layer. NO PRIVILEGE REQUIRED.

Run from the repository root:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_mnwifi.py -q

WHY THERE IS NO SUDO HERE. sudo asks for a password on this machine, so the
privileged run is left to the user. The ONLY thing that needs privilege is
creating network namespaces; everything else is exercised here:

  * does the layout realise the target graph,
  * does the channel-time rule give the documented lower bound,
  * does the collector rebuild known counters from synthetic JSONL,
  * does the port satisfy the `Platform` contract OVER A REAL SOCKET,
  * is exceeding 250 B an error,
  * does serialisation survive a round trip through a real socket,
  * does `node_main` run a `NodeCore` UNMODIFIED.

The last item is the claim the architecture rests on. It is tested on the
OBJECT rather than on source text, over every registered implementation, and
end to end by running the ten-node worked example over REAL UDP SOCKETS and
comparing the result against the simulator's counters.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import math
import os
import socket
import sys
from typing import Dict, List, Sequence, Tuple

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from ccvc.bb import bbcvc, validate, wire  # noqa: E402
from ccvc.bb.api import (MAX_PAYLOAD, NodeCore, PayloadTooLarge,  # noqa: E402
                         Platform, Role, key_of)
from ccvc.bb.bbcvc import BbcvcNode, BbcvcParams, mac_for_id  # noqa: E402
from ccvc.bb.bootstrap import hash16, t_hello_lower_bound_ms  # noqa: E402
from ccvc.bb.mnwifi import collect as collector  # noqa: E402
from ccvc.bb.mnwifi import node_main, run as runner_mod, topology as topo  # noqa: E402
from ccvc.bb.mnwifi.node_main import NodeRunner  # noqa: E402
from ccvc.bb.mnwifi.udp_port import (AddressMap, DropRule, JsonlLog,  # noqa: E402
                                     RssiReader, UdpPort, loopback_peers,
                                     parse_station_dump)
from ccvc.bb.simnet import _Port as SimPort  # noqa: E402

EDGES = runner_mod.EXAMPLE_EDGES
WEIGHTS = runner_mod.EXAMPLE_WEIGHTS
K = runner_mod.EXAMPLE_K

#: What the channel rule yields on the worked example (derived in this file).
TAU_MS = 59
T_HELLO_MS = 49

#: Base port handed out per test so that tests never collide on a port.
_PORT_BASE = [47301]


def next_port_base(n: int) -> int:
    base = _PORT_BASE[0]
    _PORT_BASE[0] += n + 4
    return base


# ==========================================================================
# 1. Channel-time rule (brief 3.6)
# ==========================================================================
def test_channel_rule_matches_documented_lower_bound():
    """T_hello >= N2 * t_f / rho_max, exactly the rule the brief states."""
    ch = topo.channel_time(EDGES)
    assert ch.n2_max == 7, "largest 2-hop neighbourhood in the worked example"
    # The rule must give the SAME value as the function bootstrap.py documents.
    assert ch.t_hello_ms == t_hello_lower_bound_ms(7, t_frame_ms=ch.t_frame_ms,
                                                   rho_max=0.1)
    assert ch.t_hello_ms == T_HELLO_MS
    assert ch.tau_ms == TAU_MS == math.ceil(1.2 * ch.t_hello_ms)


def test_channel_rule_is_a_lower_bound_not_a_guess():
    """Does the rule actually hold channel utilisation below rho_max."""
    ch = topo.channel_time(EDGES)
    rho = ch.n2_max * ch.t_frame_ms / ch.t_hello_ms
    assert rho <= ch.rho_max + 1e-9, f"channel utilisation {rho} > {ch.rho_max}"


def test_frame_time_model_reproduces_both_brief_anchors():
    """The t_f model must hold BOTH brief anchors: 24 B ~ 0.7, 250 B ~ 2.5."""
    assert topo.t_frame_ms(24) == pytest.approx(0.7, abs=0.01)
    assert topo.t_frame_ms(250) == pytest.approx(2.5, abs=0.01)


def test_channel_rule_grows_with_density():
    """A denser topology demands a longer T_hello; the rule must show that."""
    dense = [(u, v) for u in range(1, 15) for v in range(u + 1, 15)]
    assert topo.channel_time(dense).t_hello_ms > topo.channel_time(EDGES).t_hello_ms


def test_two_hop_counts_exclude_self():
    n2 = topo.two_hop_counts(EDGES)
    assert n2[1] == 3 and n2[5] == 7 and n2[10] == 3


# ==========================================================================
# 2. Layout: does it realise the target graph
# ==========================================================================
def test_layout_realises_the_worked_example_exactly():
    """The worked example IS realisable as a unit disk graph, so it must be."""
    lay = topo.layout(EDGES, radio_range_m=100.0, seed=0)
    diff = topo.compare_topology(EDGES, topo.realised_edges(lay.positions, 100.0))
    assert diff.exact, diff.summary()
    assert lay.conflicts == 0


#: THE TOLERANCE, STATED EXPLICITLY. The layout is a local optimiser; on a
#: target that already IS a unit disk graph the worst measured Jaccard is 0.989
#: (n=20..100, average degree 3.9..16.3). The gate is set at 0.97: below what
#: was measured, but close enough to catch a real regression.
LAYOUT_JACCARD_MIN = 0.97


@pytest.mark.parametrize("n,seed", [(20, 1), (40, 2), (60, 3)])
def test_layout_recovers_a_unit_disk_graph(n, seed):
    """A graph that already is a unit disk graph must be recovered near-exactly.

    This is the one measurable correctness claim the layout can make: if the
    input is realisable, the layout must find it. NO such claim exists for an
    arbitrary graph, which is what the K_{1,6} test demonstrates.
    """
    edges, _pos = runner_mod.unit_disk_graph(n, seed=seed, side=520.0,
                                             radio_range_m=140.0)
    lay = topo.layout(edges, radio_range_m=100.0, seed=seed, iterations=900)
    diff = topo.compare_topology(edges, topo.realised_edges(lay.positions, 100.0))
    assert diff.jaccard >= LAYOUT_JACCARD_MIN, diff.summary()


def test_layout_reports_unrealisable_graphs_instead_of_hiding_them():
    """The star K_{1,6} CANNOT be realised as a unit disk graph in the plane.

    Six leaves sit at best 60 degrees apart around the centre, and at that angle
    the chord EQUALS the radius, so two adjacent leaves are inevitably within
    range of each other and an edge appears that is not in the target. (K_{1,5}
    IS realisable: at 72 degrees the chord is 1.18r.) The layout does not paper
    over this, it reports it through `conflicts`; a target that is not a unit
    disk graph must never silently claim it was "realised".
    """
    star = [(0, i) for i in range(1, 7)]
    lay = topo.layout(star, radio_range_m=100.0, seed=0, iterations=900)
    diff = topo.compare_topology(star, topo.realised_edges(lay.positions, 100.0))
    assert lay.conflicts == len(diff.missing) + len(diff.extra)
    assert not diff.exact, "K_{1,6} is unrealisable; 'exact' would be suspect"


def test_topology_diff_reports_both_directions():
    d = topo.compare_topology([(1, 2), (2, 3)], [(2, 1), (3, 4)])
    assert d.missing == [(2, 3)] and d.extra == [(3, 4)]
    assert d.jaccard == pytest.approx(1 / 3)
    assert not d.exact


def test_plan_is_reproducible():
    a = topo.plan(EDGES, WEIGHTS, K, seed=7)
    b = topo.plan(EDGES, WEIGHTS, K, seed=7)
    assert a.positions == b.positions and a.channel == b.channel


# ==========================================================================
# 3. Addressing
# ==========================================================================
def test_station_mac_derives_the_simulator_node_id():
    """The interface MAC must yield the identity the node will DERIVE.

    Required because the node finds its own identity through `hash16(MAC)`
    (brief 3.5/1). If the interface MAC mapped to a different identity, the
    emulator and simulator counters would not be describing the same nodes.
    """
    peers = topo.assign_peers(sorted(WEIGHTS))
    for nid, p in peers.items():
        assert hash16(p.mac) == nid
        assert p.mac == mac_for_id(nid)


def test_peer_table_round_trips_through_json():
    peers = topo.assign_peers(sorted(WEIGHTS))
    assert topo.peers_from_json(topo.peers_to_json(peers)) == peers


def test_mac_formatting_round_trips():
    for nid in sorted(WEIGHTS):
        m = mac_for_id(nid)
        assert topo.parse_mac(topo.format_mac(m)) == m


def test_address_map_recovers_mac_from_source_address():
    """`src` is resolved from the source address, NEVER from the payload."""
    peers = loopback_peers([1, 2, 3], base_port=next_port_base(3))
    amap = AddressMap(peers, 1, broadcast="fanout")
    for nid, p in peers.items():
        assert amap.mac_of((p.ip, p.udp_port)) == p.mac
        assert amap.addr_of(p.mac) == (p.ip, p.udp_port)
    assert amap.addr_of(0xDEADBEEF) is None


def test_broadcast_target_is_the_limited_broadcast_address():
    """brief 7: broadcast to 255.255.255.255. No AP, hence no coordinator."""
    peers = topo.assign_peers([1, 2, 3])
    amap = AddressMap(peers, 1, broadcast="subnet")
    assert amap.broadcast_targets() == [("255.255.255.255", peers[1].udp_port)]


# ==========================================================================
# 4. RSSI parsing
# ==========================================================================
STATION_DUMP = """Station 02:00:00:00:00:01 (on sta1-wlan0)
\tinactive time:\t12 ms
\trx bytes:\t4096
\tsignal:  \t-42 dBm
\tsignal avg:\t-45 dBm
\ttx bitrate:\t1.0 MBit/s
Station 02:00:00:00:00:02 (on sta1-wlan0)
\tinactive time:\t8 ms
\tsignal:  \t-88 dBm
"""


def test_station_dump_parsing_prefers_the_average():
    got = parse_station_dump(STATION_DUMP)
    assert got[topo.parse_mac("02:00:00:00:00:01")] == -45.0   # avg preferred
    assert got[topo.parse_mac("02:00:00:00:00:02")] == -88.0   # no avg: instant
    assert len(got) == 2


def test_station_dump_parsing_survives_garbage():
    assert parse_station_dump("") == {}
    assert parse_station_dump("Station not-a-mac\n\tsignal: x dBm\n") == {}


def test_rssi_reader_polls_at_most_once_per_period():
    """Her çerçevede `iw` çağırmak düğümü zamanlamadan düşürür."""
    calls = []

    def fake(iface):
        calls.append(iface)
        return STATION_DUMP

    r = RssiReader("sta1-wlan0", period_ms=500, runner=fake)
    r.refresh(0)
    r.refresh(100)
    r.refresh(400)
    assert len(calls) == 1
    r.refresh(600)
    assert len(calls) == 2
    assert r.of(topo.parse_mac("02:00:00:00:00:01")) == -45.0
    assert r.failures == 0


def test_rssi_reader_failure_does_not_kill_the_node():
    def boom(_iface):
        raise OSError("iw yok")

    r = RssiReader("sta1-wlan0", period_ms=10, runner=boom)
    assert r.refresh(0) == {}
    assert r.failures == 1


# ==========================================================================
# 5. Port: Platform sözleşmesi, gerçek soket
# ==========================================================================
def make_port(tmp_path, nids, me, *, reach=None, base=None, clock=None):
    peers = loopback_peers(nids, base_port=base or next_port_base(len(nids)))
    amap = AddressMap(peers, me, broadcast="fanout",
                      reach=None if reach is None else [peers[u].mac for u in reach])
    jlog = JsonlLog(os.path.join(str(tmp_path), f"{me}.jsonl"))
    kw = {} if clock is None else {"clock": clock}
    return UdpPort(amap, jlog, **kw), peers


def test_port_is_a_platform_and_adds_nothing_the_node_can_see(tmp_path):
    """api I2: düğümün göreceği yüzey dört çağrı + `mac`tır, fazlası değil.

    `SimNet._Port` ile YÜZEY KARŞILAŞTIRMASI yapılır: emülatör portu
    simülatör portunun sunduğundan fazla bir şey SUNMAMALIDIR, yoksa düğüm
    kodu emülatöre özgü bir çağrıya yaslanabilirdi.
    """
    port, _ = make_port(tmp_path, [1, 2], 1)
    try:
        assert isinstance(port, Platform)
        sim_surface = {n for n in dir(SimPort) if not n.startswith("_")}
        assert sim_surface == {"send_broadcast", "send_unicast", "now_ms",
                               "log", "mac"}
        for name in sim_surface:
            assert hasattr(port, name), f"portta eksik: {name}"
    finally:
        port.close()


def test_port_rejects_payloads_over_250_bytes(tmp_path):
    """api I3: aşım HATADIR, kırpma değil. Kırpılmış çerçeve sessiz yanlış karar."""
    port, peers = make_port(tmp_path, [1, 2], 1)
    try:
        port.send_broadcast(b"\x00" * MAX_PAYLOAD)          # sınır: geçer
        with pytest.raises(PayloadTooLarge):
            port.send_broadcast(b"\x00" * (MAX_PAYLOAD + 1))
        with pytest.raises(PayloadTooLarge):
            port.send_unicast(peers[2].mac, b"\x00" * (MAX_PAYLOAD + 1))
    finally:
        port.close()


def test_wire_round_trips_through_a_real_socket(tmp_path):
    """Serileştirme gerçek UDP soketinden gidip gelmeli; kaynak MAC ÇERÇEVEDEN."""
    base = next_port_base(2)
    p1, peers = make_port(tmp_path, [1, 2], 1, base=base)
    p2, _ = make_port(tmp_path, [1, 2], 2, base=base)
    try:
        msg = wire.Hello(src=1, key=12345, deg=3, role=Role.MIS, phase=2,
                         load=1, epoch=7, mis_nbrs=(4, 5))
        payload = wire.encode(msg)
        p1.send_broadcast(payload)
        frames = _drain(p2)
        assert len(frames) == 1
        f = frames[0]
        assert f.src_mac == peers[1].mac, "kaynak MAC yükten değil çerçeveden"
        assert f.payload == payload
        back = wire.decode(f.payload)
        assert (back.src, back.key, back.deg, back.role, back.phase,
                back.epoch, back.mis_nbrs) == (1, 12345, 3, Role.MIS, 2, 7, (4, 5))
    finally:
        p1.close()
        p2.close()


def test_unicast_reaches_only_the_addressed_peer(tmp_path):
    base = next_port_base(3)
    p1, peers = make_port(tmp_path, [1, 2, 3], 1, base=base)
    p2, _ = make_port(tmp_path, [1, 2, 3], 2, base=base)
    p3, _ = make_port(tmp_path, [1, 2, 3], 3, base=base)
    try:
        p1.send_unicast(peers[2].mac, wire.encode(
            wire.Ctrl(mtype=wire.MsgType.LINK, src=1, seq=1)))
        assert len(_drain(p2)) == 1
        assert _drain(p3) == []
    finally:
        for p in (p1, p2, p3):
            p.close()


def test_unicast_to_unknown_mac_is_lost_not_an_error(tmp_path):
    """simnet I1 ile aynı: düğüm 'bu benim komşum değilmiş'i ÖĞRENEMEZ."""
    port, _ = make_port(tmp_path, [1, 2], 1)
    try:
        port.send_unicast(0x020000009999, b"\x00\x01\x02")   # kimse
        assert port.unreachable == 1
        assert port.tx_calls == 1, "tx yine sayılır: çerçeve havaya çıktı"
    finally:
        port.close()


def test_port_ignores_its_own_broadcast(tmp_path):
    """Yayını kendine geri gelirse düğüm kendi HELLO'sunu komşu sanardı."""
    base = next_port_base(2)
    p1, _ = make_port(tmp_path, [1, 2], 1, base=base)
    try:
        p1.amap.reach = {p1.mac}            # kendine yolla
        p1.send_broadcast(wire.encode(wire.Hello(
            src=1, key=1, deg=0, role=Role.OUT, phase=0, load=0)))
        assert _drain(p1) == []
    finally:
        p1.close()


def test_drop_rule_looks_exactly_like_channel_loss_to_the_node(tmp_path):
    """Tek HELLO düşürme kancası (brief §3.5/5 kararlılık kapısı testi)."""
    base = next_port_base(2)
    peers = loopback_peers([1, 2], base_port=base)
    amap = AddressMap(peers, 1, broadcast="fanout")
    jlog = JsonlLog(os.path.join(str(tmp_path), "1.jsonl"))
    p1 = UdpPort(amap, jlog, drops=[DropRule(mtype=int(wire.MsgType.HELLO),
                                             count=1)])
    p2, _ = make_port(tmp_path, [1, 2], 2, base=base)
    try:
        hello = wire.encode(wire.Hello(src=1, key=1, deg=1, role=Role.OUT,
                                       phase=0, load=0))
        p1.send_broadcast(hello)            # bu düşer
        assert _drain(p2) == []
        assert p1.dropped_by_rule == 1
        assert p1.tx_calls == 1, "düşen çerçeve de tx'e yazılır (simnet kuralı)"
        p1.send_broadcast(hello)            # bu geçer
        assert len(_drain(p2)) == 1
    finally:
        p1.close()
        p2.close()


def test_out_of_range_peer_never_hears_the_broadcast(tmp_path):
    """Menzil PLATFORMDADIR (wmediumd'nin karşılığı), düğümde değil."""
    base = next_port_base(3)
    peers = loopback_peers([1, 2, 3], base_port=base)
    p1, _ = make_port(tmp_path, [1, 2, 3], 1, reach=[2], base=base)
    p2, _ = make_port(tmp_path, [1, 2, 3], 2, base=base)
    p3, _ = make_port(tmp_path, [1, 2, 3], 3, base=base)
    try:
        p1.send_broadcast(b"\x00\x01\x02")
        assert len(_drain(p2)) == 1
        assert _drain(p3) == [], "menzil dışındaki istasyon duymamalı"
        p1.send_unicast(peers[3].mac, b"\x00\x01\x02")
        assert _drain(p3) == []
        assert p1.unreachable == 0, "MAC biliniyor; menzil dışı olması ayrı şey"
    finally:
        for p in (p1, p2, p3):
            p.close()


def _drain(port: UdpPort, tries: int = 40):
    """Geri döngüde teslim eşzamansızdır; kısa süre yokla."""
    import time as _t
    out = []
    for _ in range(tries):
        got = port.receive()
        out.extend(got)
        if out:
            break
        _t.sleep(0.005)
    return out


# ==========================================================================
# 6. Toplayıcı: sentetik günlükten bilinen sayaçlar
# ==========================================================================
def write_log(tmp_path, nid: int, mac: int, recs):
    path = os.path.join(str(tmp_path), f"{nid}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in recs:
            r = dict(r)
            r.setdefault("mac", topo.format_mac(mac))
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return path


def synthetic_run(tmp_path):
    """İki düğüm, ELDE SAYILMIŞ sayaçlar.

    1 -> iki yayın (tip 0, 20 B) ve bir tekil (tip 1, 12 B); ikisini de 2 aldı,
    tekili de. 2 -> bir yayın (tip 0, 20 B), 1 aldı. 1 bir kez retx bildirdi.
    Beklenen: tx(1)=3, rx(1)=3, tx(2)=1, rx(2)=1, retx(1)=2.
    """
    m1, m2 = mac_for_id(1), mac_for_id(2)
    write_log(tmp_path, 1, m1, [
        {"t_ms": 1000, "event": "run_start", "nid": 1},
        {"t_ms": 1010, "event": "tx", "mtype": 0, "bytes": 20, "phase": 0, "kind": "bcast"},
        {"t_ms": 1020, "event": "rx", "src": topo.format_mac(m2), "mtype": 0, "bytes": 20},
        {"t_ms": 1030, "event": "tx", "mtype": 0, "bytes": 20, "phase": 1, "kind": "bcast"},
        {"t_ms": 1040, "event": "tx", "mtype": 1, "bytes": 12, "phase": 1, "kind": "ucast"},
        {"t_ms": 1050, "event": "retx", "n": 2},
        {"t_ms": 1060, "event": "node_done", "role": int(Role.MIS)},
        {"t_ms": 1100, "event": "run_end", "role": int(Role.MIS), "owned": [[1, 2]],
         "deg": 1, "key_fp": 111, "epoch": 0, "bidir": [2], "infeasible": False,
         "unresolved": False, "table_overflow": 0, "id_rederivations": 0},
    ])
    write_log(tmp_path, 2, m2, [
        {"t_ms": 1000, "event": "run_start", "nid": 2},
        {"t_ms": 1005, "event": "tx", "mtype": 0, "bytes": 20, "phase": 0, "kind": "bcast"},
        {"t_ms": 1015, "event": "rx", "src": topo.format_mac(m1), "mtype": 0, "bytes": 20},
        {"t_ms": 1035, "event": "rx", "src": topo.format_mac(m1), "mtype": 0, "bytes": 20},
        {"t_ms": 1045, "event": "rx", "src": topo.format_mac(m1), "mtype": 1, "bytes": 12},
        {"t_ms": 1080, "event": "node_done", "role": int(Role.COVER)},
        {"t_ms": 1100, "event": "run_end", "role": int(Role.COVER), "owned": [],
         "deg": 1, "key_fp": 222, "epoch": 0, "bidir": [1], "infeasible": False,
         "unresolved": False, "table_overflow": 0, "id_rederivations": 0},
    ])


def test_collector_reconstructs_known_counters(tmp_path):
    synthetic_run(tmp_path)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    assert run.by_node[1].tx == 3
    assert run.by_node[1].bytes_tx == 52
    assert run.by_node[1].max_payload == 20
    assert run.by_node[1].retx == 2
    assert run.by_node[2].tx == 1
    # rx GÖNDERİCİYE yazılır: 1'in üç çerçevesini 2 aldı.
    assert run.by_node[1].rx == 3
    assert run.by_node[2].rx == 1
    # alıcı tarafı ayrı tutulur; küresel toplamları eşit.
    assert run.rx_delivered == {1: 1, 2: 3}
    assert sum(run.rx_delivered.values()) == run.totals().rx
    assert run.totals().tx == 4
    assert run.by_node[1].by_type_tx == {0: 2, 1: 1}
    assert run.by_node[1].by_phase_tx == {0: 1, 1: 2}


def test_collector_derives_radio_on_from_the_log_intervals(tmp_path):
    """radyo-açık = koşum başından o düğümün sükûnetine (simnet ile aynı)."""
    synthetic_run(tmp_path)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    assert run.by_node[1].radio_on_ms == 60
    assert run.by_node[2].radio_on_ms == 80
    # enerji tahmini: dinleme 100 mA + iletim t_f x 240 mA (brief §3.6)
    assert run.by_node[1].energy_mah(0.7) == round(
        60 / 3.6e6 * 100 + 3 * 0.7 / 3.6e6 * 240, 6)


def test_collector_derives_slots_the_same_way_the_scheduler_does(tmp_path):
    """Slot sayısı = son sükûnetin slot indisi + 1 (sched.SyncScheduler)."""
    synthetic_run(tmp_path)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    assert run.converged
    assert run.t_conv_ms == 80
    assert run.slots == 5                     # 80 // 20 + 1


def test_collector_reconstructs_cover_and_owner(tmp_path):
    synthetic_run(tmp_path)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    assert run.cover == [1, 2]
    assert run.owner == {(1, 2): 1}
    assert run.discovered_edges() == [(1, 2)]
    assert run.asymmetric_claims() == []


def test_collector_flags_asymmetric_neighbour_claims(tmp_path):
    """u, v'yi komşu sayıyor ama v saymıyorsa bu kenar DEĞİLDİR (brief §3.4)."""
    synthetic_run(tmp_path)
    path = os.path.join(str(tmp_path), "2.jsonl")
    lines = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    for r in lines:
        if r["event"] == "run_end":
            r["bidir"] = []
    with open(path, "w", encoding="utf-8") as fh:
        for r in lines:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    assert run.discovered_edges() == []
    assert run.asymmetric_claims() == [(1, 2)]


def test_collector_survives_a_truncated_last_line(tmp_path):
    """SIGTERM ile kesilen süreç yarım satır bırakır; koşum ölçülemez olmamalı."""
    synthetic_run(tmp_path)
    with open(os.path.join(str(tmp_path), "1.jsonl"), "a", encoding="utf-8") as fh:
        fh.write('{"t_ms": 1200, "event": "tx", "byt')
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    assert run.by_node[1].tx == 3
    assert run.truncated_lines == 1


def test_collector_never_trusts_a_self_reported_counter(tmp_path):
    """Düğüm 'ben 999 gönderdim' dese bile toplayıcı SATIRLARI sayar."""
    synthetic_run(tmp_path)
    with open(os.path.join(str(tmp_path), "1.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t_ms": 1090, "event": "counters", "tx": 999,
                             "rx": 999, "mac": topo.format_mac(mac_for_id(1))}) + "\n")
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    assert run.by_node[1].tx == 3 and run.by_node[1].rx == 3


def test_timeline_tracks_cover_growth(tmp_path):
    synthetic_run(tmp_path)
    logs = collector.read_run(str(tmp_path))
    tl = collector.timeline(logs, tau_ms=20, t0_ms=1000, weights={1: 5, 2: 2})
    assert tl.cover_size == sorted(tl.cover_size), "|C| MONOTON büyümeli"
    assert tl.cover_weight == sorted(tl.cover_weight)


# ==========================================================================
# 7. Simülatörle karşılaştırma mantığı
# ==========================================================================
class _FakeSim:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_comparison_reports_a_discrepancy_instead_of_explaining_it_away(tmp_path):
    synthetic_run(tmp_path)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    sim = _FakeSim(slots=5, tx=4, rx=4, bytes_tx=72, max_payload=20,
                   retx=2, total_weight=7.0, cover=[1, 2], owner={(1, 2): 1})
    cmp_ = collector.compare_with_sim(run, sim, weights={1: 5, 2: 2})
    assert cmp_.exact, cmp_.summary()

    sim.tx = 3                                  # emülatör bir fazla iletti
    cmp2 = collector.compare_with_sim(run, sim, weights={1: 5, 2: 2})
    assert not cmp2.exact
    d = [x for x in cmp2.discrepancies if x.metric == "tx"][0]
    assert (d.emulator, d.simulator, d.delta) == (4, 3, 1)
    assert "MISMATCH" in cmp2.summary()


def test_comparison_notices_a_different_cover(tmp_path):
    synthetic_run(tmp_path)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=20, t0_ms=1000)
    sim = _FakeSim(slots=5, tx=4, rx=4, bytes_tx=72, max_payload=20, retx=2,
                   total_weight=7.0, cover=[1], owner={(1, 2): 1})
    cmp_ = collector.compare_with_sim(run, sim, weights={1: 5, 2: 2})
    assert not cmp_.cover_same and not cmp_.exact


# ==========================================================================
# 8. node_main: does the node code run UNMODIFIED
# ==========================================================================
@pytest.mark.parametrize("kind", sorted(node_main.NODE_KINDS))
def test_node_main_uses_the_unmodified_node_class(tmp_path, kind):
    """THE ARCHITECTURAL CLAIM: no subclass, no patch, no extra call.

    THE EFFECT IS TESTED, NOT THE SPELLING. The first version of this test
    searched `inspect.getsource` for text (no "setattr(node", yes
    "BbcvcNode(a.weight, ...)"). That is wrong in both directions: reformatting
    fails it SPURIOUSLY, and any patch not on the forbidden list -- written
    through an alias, or applied to the instance -- slides through silently. The
    `_t0_ms` text assertion in this same file stayed green after its fix landed
    and went on documenting a finding that had become false, which is exactly
    this failure mode. So the claim is now made ON THE OBJECT.

    It runs over EVERY registered implementation. A platform-independence claim
    demonstrated with one node class is barely a claim; running a second,
    independently written `NodeCore` over the same four calls is what turns it
    into a comparison.
    """
    node_cls, params_cls = node_main.resolve_node_kind(kind)

    # 1) The registry resolves to the class the algorithm module EXPORTS --
    #    not a subclass, not a wrapper.
    mod_name, cls_name, par_name = node_main.NODE_KINDS[kind]
    mod = __import__(mod_name, fromlist=[cls_name, par_name])
    assert node_cls is getattr(mod, cls_name)
    assert params_cls is getattr(mod, par_name)
    assert issubclass(node_cls, NodeCore)

    # 2) Importing node_main has not altered ANY method of the node class:
    #    every function in the MRO still comes from its own file. This holds
    #    however a patch might have been written.
    node_main_file = os.path.abspath(node_main.__file__)
    for klass in node_cls.__mro__:
        for attr, fn in vars(klass).items():
            code = getattr(fn, "__code__", None)
            if code is None:
                continue
            assert os.path.abspath(code.co_filename) != node_main_file, \
                f"{klass.__name__}.{attr} was patched by node_main"

    # 3) Every implementation obeys the SAME constructor contract. This is the
    #    property that makes one launcher able to run all of them.
    assert list(inspect.signature(node_cls.__init__).parameters)[1:] == \
        ["weight", "platform", "params", "capacity_k"]

    # 4) A REAL instance built through node_main's own port: exactly the
    #    registered class, and no callable in the instance dict shadowing a
    #    method (instance-level patching).
    peers = loopback_peers([1, 2], base_port=next_port_base(2))
    port = node_main.build_port(topo.peers_to_json(peers), peers[1].mac,
                                str(tmp_path), broadcast="fanout")
    try:
        params = node_main.build_params(params_cls, t_hello_ms=T_HELLO_MS)
        if kind == "anneal":
            params = params.resolved(list(WEIGHTS.values()))
        node = node_cls(WEIGHTS[1], port, params, K)
        assert type(node) is node_cls
        shadowed = [k for k, v in node.__dict__.items()
                    if callable(v) and hasattr(node_cls, k)]
        assert not shadowed, f"method shadowed on the instance: {shadowed}"
        # The event entry points are still the class's own functions.
        assert node.on_timer.__func__ is node_cls.on_timer
    finally:
        port.jlog.close()
        port.close()


def test_every_registered_node_kind_resolves():
    """The registry must not accumulate dead entries."""
    for kind in node_main.NODE_KINDS:
        node_cls, params_cls = node_main.resolve_node_kind(kind)
        assert issubclass(node_cls, NodeCore)
        assert dataclasses.is_dataclass(params_cls)
    with pytest.raises(SystemExit):
        node_main.resolve_node_kind("no-such-algorithm")


def test_build_params_ignores_knobs_an_implementation_lacks():
    """Filtering keeps an unknown option a no-op rather than a start-up crash."""
    _, params_cls = node_main.resolve_node_kind("bbcvc")
    p = node_main.build_params(params_cls, t_hello_ms=77,
                               no_such_knob=1, mis_nbrs_max=None)
    assert p.t_hello_ms == 77
    assert not hasattr(p, "no_such_knob")
    # `None` means "not supplied": the dataclass default must survive.
    assert p.mis_nbrs_max == params_cls().mis_nbrs_max


def test_node_main_builds_a_real_node_over_a_real_socket(tmp_path):
    """`build_port` + `BbcvcNode` gerçekten kurulup bir HELLO yayınlıyor mu."""
    base = next_port_base(2)
    peers = loopback_peers([1, 2], base_port=base)
    doc = topo.peers_to_json(peers)
    port = node_main.build_port(doc, peers[1].mac, str(tmp_path),
                                broadcast="fanout")
    listener, _ = make_port(tmp_path, [1, 2], 2, base=base)
    try:
        node = BbcvcNode(WEIGHTS[1], port, BbcvcParams(t_hello_ms=T_HELLO_MS), K)
        port.set_phase_source(lambda: node.phase)
        assert node.nid == 1, "kimlik MAC'ten TÜRETİLDİ"
        node.on_timer("tick")
        frames = _drain(listener)
        assert frames, "düğüm ilk tikte HELLO yayınlamalı"
        hello = wire.decode(frames[0].payload)
        assert hello.mtype == wire.MsgType.HELLO and hello.src == 1
        assert frames[0].src_mac == peers[1].mac
    finally:
        port.jlog.close()
        port.close()
        listener.close()


def test_resolve_mac_refuses_to_invent_an_identity():
    with pytest.raises(SystemExit):
        node_main.resolve_mac(None, None)
    assert node_main.resolve_mac("02:00:00:00:00:07", None) == 0x020000000007


# ==========================================================================
# 9. UÇTAN UCA: çalışan örnek GERÇEK UDP soketleri üzerinde
# ==========================================================================
class _Clock:
    """Sanal saat. Soketler gerçek, zaman denetimli.

    Gerçek saatle koşmak testi zamanlamaya bağımlı kılardı; sanal saat
    slot semantiğini AYNEN korur (`sched.SyncScheduler` de sanal saatlidir).
    """

    def __init__(self, start_ms: int = 0) -> None:
        self.ms = int(start_ms)

    def __call__(self) -> float:
        return self.ms / 1000.0


#: Tipik bir duvar saati damgası (ms). Sıfırdan başlamayan saati temsil eder.
WALL_MS = 1_700_000_000_000


def build_cluster(tmp_path, edges, weights, k, *, tau_ms, t_hello_ms,
                  epoch_ms: int = 0, clock_start_ms: int = 0,
                  kind: str = "bbcvc", params=None):
    nids = sorted({a for e in edges for a in e} | set(weights))
    base = next_port_base(len(nids))
    peers = loopback_peers(nids, base_port=base)
    adj: Dict[int, List[int]] = {n: [] for n in nids}
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    clock = _Clock(clock_start_ms)
    nodes, ports, runners = {}, {}, {}
    for nid in nids:
        amap = AddressMap(peers, nid, broadcast="fanout",
                          reach=[peers[u].mac for u in adj[nid]])
        jlog = JsonlLog(os.path.join(str(tmp_path), f"{nid}.jsonl"))
        port = UdpPort(amap, jlog, clock=clock, epoch_ms=epoch_ms)
        # === UNMODIFIED NODE CODE, whichever implementation is selected ===
        node_cls, params_cls = node_main.resolve_node_kind(kind)
        p = params if params is not None else node_main.build_params(
            params_cls, t_hello_ms=t_hello_ms)
        node = node_cls(weights[nid], port, p, k)
        port.set_phase_source(lambda n=node: n.phase)
        port.log("run_start", mode="sync", tau_ms=tau_ms, t_hello_ms=t_hello_ms,
                 k=k, weight=weights[nid], nid=node.nid)
        nodes[nid], ports[nid] = node, port
        runners[nid] = NodeRunner(node, port, mode="sync", tau_ms=tau_ms,
                                  deadline_ms=10 ** 9, log_dir=str(tmp_path),
                                  defer="boundary")
    return nids, clock, nodes, ports, runners


def drive(nids, clock, nodes, runners, *, tau_ms, max_slots):
    """`sched.SyncScheduler.run`ın süreç başına karşılığı, tek süreçte."""
    for s in range(max_slots):
        clock.ms = s * tau_ms
        # ÖNCE bütün kuyruklar boşalır, SONRA bütün zamanlayıcılar ateşler.
        # `sched.SyncScheduler.run`ın sırası birebir budur; araya karışmış
        # bir sıra bir düğüme komşusunun çerçevesini bir slot GEÇ verirdi.
        for nid in nids:
            runners[nid].poll(s)
        for nid in nids:
            runners[nid].fire(s)
        clock.ms = (s + 1) * tau_ms
        if all(nodes[n].done for n in nids):
            # Zamanlayıcının koşulu SÜKÛNET DEĞİL, sükûnet VE yolda çerçeve
            # olmamasıdır. Son slotta gönderilen çerçeveler hâlâ yoldaysa bir
            # slot daha koşulur; o slot hem sayıma hem `rx`e girer.
            for nid in nids:
                runners[nid].poll(s + 1)
            if not any(runners[nid].pending for nid in nids):
                return s + 1
    return None


def finish(nids, nodes, ports, runners):
    for nid in nids:
        n, p, r = nodes[nid], ports[nid], runners[nid]
        p.log("run_end", slots=r.slots, role=int(n.role), phase=int(n.phase),
              done=bool(n.done), deg=-1 if n.deg is None else n.deg,
              key_fp=-1 if n.key_fp is None else int(n.key_fp),
              epoch=int(n.epoch), owned=[list(e) for e in sorted(n.owned)],
              bidir=sorted(int(u) for u in n.edges()),
              infeasible=bool(n.infeasible), unresolved=bool(n.unresolved),
              table_overflow=int(n.table_overflow),
              id_rederivations=int(n.id_rederivations))
        p.jlog.close()
        p.close()


@pytest.fixture(scope="module")
def sim_reference():
    return bbcvc.run_bbcvc(EDGES, WEIGHTS, K, scheduler="sync",
                           params=BbcvcParams(t_hello_ms=T_HELLO_MS),
                           max_ms=600_000, tau_ms=TAU_MS)


def test_simulator_reference_is_the_measured_one_not_the_document(sim_reference):
    """Kalibrasyon hedefi belgenin 214/20'si DEĞİL, simülatörün ÖLÇÜLENİDİR.

    Fark anlaşılmış ve `ccvc/bb/BULGULAR_BB.md` içinde ayrıştırılmıştır
    (120 iletim bootstrap'a, 60 iletim çift yön doğrulamasına gidiyor).
    """
    # 482 -> 507 tx and 1294 -> 1367 rx, slots unchanged: a DONE node now keeps
    # a slow beacon until every neighbour has also reached PH_DONE, so one lost
    # DONE frame can no longer deadlock termination (BULGULAR_BB.md section 98).
    # The emulator and the simulator move together, which is the point of this
    # test and is still asserted exactly below.
    # UPDATED: the quiet phase now repairs a lost DONE HELLO. A node that has
    # finished answers a neighbour which is still beaconing at PH_DONE, once,
    # on the SECOND such beacon after its own DONE HELLO. That neighbour could
    # only still be beaconing because it missed mine, and without the answer it
    # beacons for ever while I stay silent, so the network never goes quiet even
    # though every node has finished. Price on this example: four HELLOs, tx 507
    # to 510 and rx 1367 to 1373, with SLOTS UNCHANGED at 53 and the emulator
    # still matching the simulator exactly.
    assert (sim_reference.slots, sim_reference.tx, sim_reference.rx) == (53, 510, 1373)
    assert sim_reference.converged and not sim_reference.infeasible


@pytest.mark.parametrize("scenario", ["clean"])
def test_end_to_end_over_real_sockets_reproduces_the_simulator(
        tmp_path, sim_reference, scenario):
    """KAYIPSIZ SENKRON EMÜLATÖR = SİMÜLATÖR (brief §7, sıra maddesi 2).

    Gerçek UDP soketleri, gerçek `UdpPort`, değiştirilmemiş `BbcvcNode`,
    gerçek `NodeRunner`. Uyuşmazlık çıkarsa test AÇIKLAMAZ, RAPOR EDER.
    """
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, EDGES, WEIGHTS, K, tau_ms=TAU_MS, t_hello_ms=T_HELLO_MS)
    try:
        slots = drive(nids, clock, nodes, runners, tau_ms=TAU_MS, max_slots=400)
    finally:
        finish(nids, nodes, ports, runners)
    assert slots is not None, "emülatör yolu sükûnete ermedi"

    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=TAU_MS, t0_ms=0)
    cmp_ = collector.compare_with_sim(run, sim_reference, weights=WEIGHTS)
    assert cmp_.exact, cmp_.summary()
    assert run.slots == sim_reference.slots == 53
    assert run.totals().tx == 510 and run.totals().rx == 1373
    assert run.cover == sim_reference.cover
    assert run.owner == {topo.edge(*e): v for e, v in sim_reference.owner.items()}


def test_a_second_node_implementation_also_reproduces_its_simulator(tmp_path):
    """PLATFORM INDEPENDENCE AS A COMPARISON, not as an assertion.

    `UdpPort` was written against BB-CVC. WuLi is a separately written
    `NodeCore` that this port has never been adapted to. If the four platform
    calls really are the whole interface, WuLi must reproduce ITS OWN simulator
    over this port with nothing changed on either side.

    One implementation matching its simulator shows the port is correct for that
    implementation. TWO implementations matching theirs, over the same port and
    the same collector, is what distinguishes "the port happens to suit this
    node" from "the interface is the whole contract".
    """
    from ccvc.bb import v5_wuli as wuli
    ch = topo.channel_time(EDGES)
    params = wuli.WuLiParams(t_hello_ms=ch.t_hello_ms, encoding=wuli.ENC_BLOOM)
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, EDGES, WEIGHTS, K, tau_ms=ch.tau_ms,
        t_hello_ms=ch.t_hello_ms, kind="wuli", params=params)
    try:
        slots = drive(nids, clock, nodes, runners, tau_ms=ch.tau_ms,
                      max_slots=800)
    finally:
        finish(nids, nodes, ports, runners)
    assert slots is not None, "the WuLi emulator path did not reach quiescence"

    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=ch.tau_ms, t0_ms=0)
    sim = wuli.run_wuli(EDGES, WEIGHTS, K, scheduler="sync", params=params,
                        max_ms=600_000, tau_ms=ch.tau_ms)
    cmp_ = collector.compare_with_sim(run, sim, weights=WEIGHTS)
    assert cmp_.exact, cmp_.summary()


def test_end_to_end_output_is_a_valid_solution(tmp_path):
    """Üç kapı (brief §9) emülatör yolunun çıktısında da geçmeli."""
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, EDGES, WEIGHTS, K, tau_ms=TAU_MS, t_hello_ms=T_HELLO_MS)
    try:
        drive(nids, clock, nodes, runners, tau_ms=TAU_MS, max_slots=400)
    finally:
        finish(nids, nodes, ports, runners)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=TAU_MS, t0_ms=0)
    g = validate.make_graph(EDGES, K, WEIGHTS)
    rep = validate.validate(g, run.cover, run.owner)
    assert rep.valid, rep.summary()
    assert len(run.owner) == len(EDGES), "her kenarın tam bir sahibi var"


def test_end_to_end_discovers_exactly_the_target_topology(tmp_path):
    """Keşfedilen çizge hedefle karşılaştırılır; kayıpsız kanalda BİREBİR."""
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, EDGES, WEIGHTS, K, tau_ms=TAU_MS, t_hello_ms=T_HELLO_MS)
    try:
        drive(nids, clock, nodes, runners, tau_ms=TAU_MS, max_slots=400)
    finally:
        finish(nids, nodes, ports, runners)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=TAU_MS, t0_ms=0)
    diff = topo.compare_topology(EDGES, run.discovered_edges())
    assert diff.exact, diff.summary()
    assert run.asymmetric_claims() == []
    assert run.table_overflow == 0 and run.id_rederivations == 0


def test_end_to_end_max_payload_stays_under_the_esp_now_limit(tmp_path):
    """250 B birinci sınıf kısıt: gerçek soket yolunda da aşılmamalı."""
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, EDGES, WEIGHTS, K, tau_ms=TAU_MS, t_hello_ms=T_HELLO_MS)
    try:
        drive(nids, clock, nodes, runners, tau_ms=TAU_MS, max_slots=400)
    finally:
        finish(nids, nodes, ports, runners)
    run = collector.counters_from_logs(collector.read_run(str(tmp_path)),
                                       tau_ms=TAU_MS, t0_ms=0)
    assert 0 < run.totals().max_payload <= MAX_PAYLOAD


def test_a_dropped_hello_does_not_freeze_a_wrong_key(tmp_path):
    """brief §3.5/5: tek HELLO düşmesi kararlılık kapısını yanıltmamalı.

    Düşürme kancası düğüm 4'ün ilk HELLO'sunu yok eder. Anahtarlar yine
    belgedeki değerlere donmalıdır: kapı kaybı TOLERE ETMELİ, yanlış bir
    dereceyle donmamalıdır.
    """
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, EDGES, WEIGHTS, K, tau_ms=TAU_MS, t_hello_ms=T_HELLO_MS)
    ports[4].drops = [DropRule(mtype=int(wire.MsgType.HELLO), count=1)]
    try:
        slots = drive(nids, clock, nodes, runners, tau_ms=TAU_MS, max_slots=400)
    finally:
        finish(nids, nodes, ports, runners)
    assert slots is not None
    assert ports[4].dropped_by_rule == 1
    expected = {1: 1.67, 2: 0.50, 3: 1.00, 4: 0.60, 5: 1.50,
                6: 0.50, 7: 0.60, 8: 0.50, 9: 1.25, 10: 1.33}
    from ccvc.bb.api import from_fp
    got = {n: round(from_fp(nodes[n].key_fp), 2) for n in nids}
    assert got == expected, "tek HELLO kaybı yanlış anahtar dondurdu"


# ==========================================================================
# 10. Düzenleyici: ayrıcalıksız taraf
# ==========================================================================
def test_plan_writes_everything_the_privileged_run_needs(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="t", run_root=str(tmp_path))
    runner_mod.write_plan(plan)
    run_dir = os.path.join(str(tmp_path), "t")
    assert os.path.exists(os.path.join(run_dir, "run.json"))
    with open(os.path.join(run_dir, "peers.json"), encoding="utf-8") as fh:
        peers = topo.peers_from_json(json.load(fh))
    assert sorted(peers) == sorted(WEIGHTS)
    assert plan.spec.channel.t_hello_ms == T_HELLO_MS
    assert plan.spec.channel.tau_ms == TAU_MS


def test_plan_logs_t_hello_instead_of_hard_coding_it(tmp_path):
    """brief §3.6: T_hello topolojiden HESAPLANIR ve GÜNLÜĞE YAZILIR."""
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="t", run_root=str(tmp_path))
    runner_mod.write_plan(plan)
    with open(os.path.join(str(tmp_path), "t", "run.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["channel"]["t_hello_ms"] == T_HELLO_MS
    assert doc["channel"]["n2_max"] == 7
    assert "N2" in doc["channel"]["rule"]


def test_plan_derives_the_hello_mis_limit_from_the_topology(tmp_path):
    """Sabit 5 yetmez: sınır TOPOLOJİDEN gelir (BULGULAR_BB.md, BULGU 3)."""
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="t", run_root=str(tmp_path))
    assert plan.spec.max_degree == 4            # çalışan örnekte düğüm 4 ve 7
    assert plan.spec.mis_nbrs_max == 5          # taban 5'in altına inilmez
    dense = [(u, v) for u in range(1, 12) for v in range(u + 1, 12)]
    p2 = runner_mod.make_plan(dense, {n: 1 for n in range(1, 12)}, 2,
                              run_id="d", run_root=str(tmp_path))
    assert p2.spec.max_degree == 10
    assert p2.spec.mis_nbrs_max == 10, "yoğun çizgede sınır büyümeli"


def test_node_argv_passes_the_computed_timings(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="t", run_root=str(tmp_path))
    argv = runner_mod.node_argv(plan, 4)
    assert "--tau-ms" in argv and argv[argv.index("--tau-ms") + 1] == str(TAU_MS)
    assert argv[argv.index("--t-hello-ms") + 1] == str(T_HELLO_MS)
    assert float(argv[argv.index("--weight") + 1]) == WEIGHTS[4]
    assert argv[argv.index("--iface") + 1] == plan.spec.peers[4].iface
    assert argv[argv.index("--mis-nbrs-max") + 1] == str(plan.spec.mis_nbrs_max)


def test_execute_refuses_without_privilege_and_prints_the_command(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="t", run_root=str(tmp_path))
    if os.geteuid() == 0:
        pytest.skip("root olarak koşuluyor")
    with pytest.raises(SystemExit) as exc:
        runner_mod.execute(plan)
    assert "sudo" in str(exc.value)


def test_static_arp_avoids_polluting_the_experiment(tmp_path):
    """ARP yayını kanalı meşgul eder ve sayaçlara girmez; statik doldurulur."""
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="t", run_root=str(tmp_path))
    cmds = topo.static_arp_commands(plan.spec)
    assert len(cmds[1]) == len(WEIGHTS) - 1
    assert all("nud permanent" in c for c in cmds[1])


def test_netem_commands_cover_the_brief_loss_levels(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="t", run_root=str(tmp_path))
    assert "del dev" in topo.netem_command(plan.spec, 1, 0)
    for pct in (5, 15):
        assert f"loss {pct}%" in topo.netem_command(plan.spec, 1, pct)


def test_unit_disk_generator_is_connected():
    for n, seed in ((50, 0), (50, 1), (100, 2), (200, 3)):
        edges, pos = runner_mod.unit_disk_graph(n, seed=seed, radio_range_m=200.0)
        assert runner_mod._connected(sorted(pos), edges)
        # Kenar yoğunluktan TÜRETİLİR; hedef ortalama dereceye yakın çıkmalı.
        assert 5.0 <= 2 * len(edges) / n <= 12.0


def test_scale_estimate_reports_what_it_cannot_measure():
    """Ölçek tahmini sudo'suz ÖLÇÜLEMEZ; rapor bunu SÖYLEMELİ."""
    row = runner_mod.scale_estimate(50, radio_range_m=200.0)
    assert row["n"] == 50 and row["processes"] == 50
    assert row["wmediumd_pairs"] == 50 * 49 // 2
    # Measured and estimated are reported SEPARATELY; a report that blended
    # them would present an unverified number as a measurement.
    assert "T_hello" in row["measured"] and "PSS" in row["measured"]
    assert "wmediumd CPU" in row["estimated"]
    # The memory figure is PSS, not RSS. Using RSS overstated n=200 by 2x.
    assert row["est_mem_mb"] == round(50 * runner_mod.PROC_PSS_MB, 1)
    assert "slots" not in row, "the slot count is only MEASURED with --with-sim"
    assert runner_mod.scale_estimate(12, radio_range_m=200.0,
                                     with_sim=True)["converged"]


# ==========================================================================
# 11. Saatin sıfır noktası: emülatörün ortaya çıkardığı tuzak
# ==========================================================================
# 11. Saatin sıfır noktası: emülatörün ortaya çıkardığı tuzak ve düzeltmesi
# ==========================================================================
@pytest.mark.parametrize("epoch_ms,label", [(0, "duvar saati"),
                                            (WALL_MS, "koşuma göre saat")])
def test_stability_gate_holds_under_a_clock_that_does_not_start_at_zero(
        tmp_path, epoch_ms, label):
    """Kararlılık kapısı SAAT NE OLURSA OLSUN doğru çalışmalı.

    BULGU (bu katmanın ortaya çıkardığı). `BootstrapNode.stable_since_ms`
    kurucuda 0'a kuruluyordu ve kapı `now - stable_since_ms >= T_stab` ile
    açılıyordu. Saat 0'dan başlıyorsa (simülatör) ya da açılıştan sayıyorsa
    (ESP32 `esp_timer_get_time`) bu doğruydu; duvar saatiyle fark ilk tikte
    1,7e12 ms çıkıyor, kapı anında açılıyor ve düğüm HENÜZ KİMSEYİ DUYMADAN
    `deg = 0` ile anahtar donduruyordu. On ayrı süreçle koşulan çalışan
    örnekte on düğümün onu da böyle dondu, ardından on epoch sıfırlaması
    yaşandı ve bytes_tx 6250 yerine 6310 çıktı.

    DÜZELTME (bb-bootstrap, `bootstrap.py`): `stable_since_ms` artık None
    başlıyor ve ilk gözlenen saatten kuruluyor; `_gate` taban kurulmadan
    açılmıyor. `UdpPort.epoch_ms` de korunuyor, çünkü ESP32'nin açılıştan
    sayan saatinin doğru taklidi odur.

    Bu test İKİ YARIYI BİRDEN çivilemektedir ve ikisi de gereklidir:
      (a) kapı ilk tikte AÇILMAZ  — eski hata geri gelirse düşer,
      (b) kapı zamanı gelince DOĞRU DERECEYLE açılır — düzeltme kapıyı
          büsbütün kilitlerse düşer.
    Tek başına (a), kapının hiç açılmadığı bir gerilemede de geçerdi.

    İKİ ARMIN İŞİ AYRIDIR ve mutasyon denemesiyle doğrulanmıştır (düzeltme
    öncesi davranış süreç içinde yamalanarak):
      `epoch_ms=0`       ham duvar saati. Düzeltme geri alınırsa DÜŞER;
                         bootstrap gerilemesini yakalayan arm budur.
      `epoch_ms=WALL_MS` portun kendi sıfır noktası. Düzeltme geri alınsa
                         bile GEÇER, çünkü port tuzağı tek başına kapatır.
                         Bu arm bir gerileme dedektörü değildir; portun
                         savunmasının bootstrap'tan BAĞIMSIZ durduğunu
                         gösterir ve ESP32 yolunun güvencesidir.
    """
    edges = [(1, 2)]
    weights = {1: 2, 2: 6}
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, edges, weights, 2, tau_ms=TAU_MS, t_hello_ms=T_HELLO_MS,
        epoch_ms=epoch_ms, clock_start_ms=WALL_MS)
    try:
        # (a) ilk tik: kimse kimseyi duymadı, anahtar DONMAMALI
        for nid in nids:
            runners[nid].poll(0)
        for nid in nids:
            runners[nid].fire(0)
        for nid in nids:
            assert nodes[nid].key is None, f"{label}: kapı ilk tikte açıldı"
            assert nodes[nid].deg is None, f"{label}: deg erken donduruldu"

        # (b) yeterince slot sonra DOĞRU dereceyle donmalı
        for s in range(1, 40):
            clock.ms = WALL_MS + s * TAU_MS
            for nid in nids:
                runners[nid].poll(s)
            for nid in nids:
                runners[nid].fire(s)
            if all(nodes[n].key is not None for n in nids):
                break
    finally:
        finish(nids, nodes, ports, runners)

    for nid in nids:
        assert nodes[nid].deg == 1, \
            f"{label}: derece {nodes[nid].deg}, oysa tek komşu var"
        assert nodes[nid].key == key_of(weights[nid], 1, nid), \
            f"{label}: anahtar w/(deg+1) ile donmadı"
        # (c) EPOCH SIFIRLAMASI OLMAMALI. Eski hatanın gözlenebilir belirtisi
        # buydu: yanlış donan anahtar, ilk çift yönlü komşu geldiğinde epoch
        # yükseltip herkesi Faz 0'a atıyordu. Anahtarlar doğru olsa bile bir
        # sıfırlama görülüyorsa kapı yine erken açılmış demektir.
        assert nodes[nid].epoch_bumps == 0, \
            f"{label}: {nodes[nid].epoch_bumps} epoch sıfırlaması"
        assert nodes[nid].epoch == 0, f"{label}: epoch {nodes[nid].epoch}"

    # Günlükten de doğrula: sayaç düğümün beyanı, olay ise kayıt (brief §7).
    for nid in nids:
        recs = collector.read_node_log(
            os.path.join(str(tmp_path), f"{nid}.jsonl")).records
        evs = [r["event"] for r in recs]
        assert "reset_phase0" not in evs, f"{label}: günlükte Faz 0'a dönüş var"
        assert evs.count("key_frozen") == 1, \
            f"{label}: anahtar {evs.count('key_frozen')} kez donduruldu"


def test_the_clock_baseline_reaches_the_production_node_path(tmp_path):
    """Saat tabanı ÜRETİMDE KOŞAN yolda gerçekten kuruluyor mu.

    GEÇMİŞ. Düzeltmenin ilk hâli tabanı yalnız `BootstrapNode.on_timer`da
    kuruyordu. `BbcvcNode` `on_timer`i eziyordu ve `super()` çağırmıyordu,
    dolayısıyla o satır üretimde hiç koşmuyordu: ölçüldüğünde `_t0_ms` duvar
    saati altında +600 ms'te bile None'dı ve hiç çift yönlü komşu edinemeyen
    bir düğüm penceresini hiç kurmuyor, anahtarını hiç dondurmuyordu.

    ŞİMDİ iki bağımsız yol var: `_gate` (bb-bootstrap, her yolun geçtiği tek
    nokta) ve `BbcvcNode._establish_clock_baseline` (bb-algo, `super()`
    çağırarak). Bu test DAVRANIŞI sınar, kaynak metnini değil; hangi yolun
    kurduğu umurunda değildir, taban kurulmuş olmalıdır.

    İKİ SAV BİRLİKTE TAŞIR. `_t0_ms` kurulmuş olmalı VE anahtar donmamış
    olmalı. Tek başına `key is None`, pencerenin hiç kurulmadığı bir
    gerilemede de geçerdi; `_t0_ms` savı pencerenin GERÇEKTEN kurulduğunu
    gösterdiği için ikincisi artık yanlış nedenle geçemez.

    `__dict__` ÜZERİNDEN OKUNUR, öznitelik erişimiyle değil: taban bir
    property'ye dönüştürülüp okundukça hesaplanırsa, saklanan değer hâlâ
    kurulmamış olduğu hâlde test geçerdi. Saklanan değer sınanmaktadır.
    (Bu ayrıntı ekip liderinden; property denemesi bb-bootstrap tarafından
    ayrıca denenip geri alınmıştır.)

    KAPSAM DÜRÜSTLÜĞÜ: iki yol birbirini yedeklediğinden bu test TEK BİR
    satırın gerileme dedektörü DEĞİLDİR; yalnız biri kaldırılırsa geçmeyi
    sürdürür. Çivilediği şey değişmezin kendisidir: taban üretim yolunda
    kurulur. Sadık mutasyon (`super()` çağır, sonra `_t0_ms = None`) ile
    doğrulanmıştır: iki düğümde de düşmektedir.
    """
    nids, clock, nodes, ports, runners = build_cluster(
        tmp_path, [(1, 2)], {1: 2, 2: 6}, 2, tau_ms=TAU_MS,
        t_hello_ms=T_HELLO_MS, epoch_ms=0, clock_start_ms=WALL_MS)
    try:
        for nid in nids:
            assert nodes[nid].__dict__.get("_t0_ms") is None, \
                "taban ilk tikten ÖNCE kurulmuş olamaz"
        for nid in nids:
            runners[nid].poll(0)
        for nid in nids:
            runners[nid].fire(0)
        for nid in nids:
            assert nodes[nid].__dict__.get("_t0_ms") == WALL_MS, \
                "üretim yolunda saat tabanı kurulmuyor: kapı duvar saatinde bozuk"
            assert nodes[nid].key is None, "ilk tikte anahtar donmamalı"
    finally:
        finish(nids, nodes, ports, runners)


def test_an_isolated_node_freezes_degree_zero_exactly_at_t_stab():
    """Yalıtılmış düğüm T_stab'da `deg=0` dondurmalı; ne önce ne hiç.

    Bu, düzeltmenin kapıyı büsbütün kilitlemediğinin kanıtıdır. Bir düğümün
    gerçekten komşusu yoksa doğru yanıt `deg=0`dır; yanlış olan, HENÜZ
    duymadan dondurmaktı. İkisini ayıran şey ZAMANLAMADIR, bu yüzden test
    donma anını tam olarak sınar.
    """
    import socket as _socket
    import tempfile as _tempfile
    tmp = _tempfile.mkdtemp()
    peers = loopback_peers([1, 2], base_port=next_port_base(2))
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    sock.setblocking(False)
    now = {"ms": WALL_MS}
    port = UdpPort(AddressMap(peers, 1, broadcast="fanout"),
                   JsonlLog(os.path.join(tmp, "1.jsonl")),
                   clock=lambda: now["ms"] / 1000.0, epoch_ms=0, sock=sock)
    try:
        node = BbcvcNode(WEIGHTS[1], port,
                         BbcvcParams(t_hello_ms=T_HELLO_MS), K)
        t_stab = node.p.t_stab_ms
        for step in (0, t_stab - 1):
            now["ms"] = WALL_MS + step
            node.on_timer("tick")
            assert node.key is None, f"+{step} ms: T_stab dolmadan dondu"
        now["ms"] = WALL_MS + t_stab
        node.on_timer("tick")
        assert node.deg == 0 and node.key is not None, "T_stab'da donmadı"
        assert node.frozen_at_ms == WALL_MS + t_stab
    finally:
        port.jlog.close()
        port.close()


def test_port_clock_epoch_preserves_slot_alignment():
    """Sıfır noktası tau'nun katıysa slot hizası KAYMAZ.

    floor((t - epoch)/tau) = floor(t/tau) - epoch/tau. Bu eşitlik, ortak
    saatle hizalanan senkron slotların (brief §7) sıfır noktası taşınsa bile
    aynı sınırlara oturmasını sağlar.
    """
    tau = TAU_MS
    epoch = (WALL_MS // tau) * tau
    for t in (epoch, epoch + 1, epoch + tau - 1, epoch + tau, epoch + 7 * tau + 3):
        assert (t - epoch) // tau == t // tau - epoch // tau


# ==========================================================================
# 12. Arıza enjeksiyonu (brief §7): ölüm, taşıma, kayıp, tek çerçeve
# ==========================================================================
def test_fault_spec_parsing_covers_both_brief_faults():
    kill = runner_mod.Fault.parse("kill:4@2000")
    assert (kill.kind, kill.nid, kill.at_ms) == ("kill", 4, 2000)
    move = runner_mod.Fault.parse("move:7@2500:310,120")
    assert (move.kind, move.nid, move.at_ms, move.x, move.y) == \
        ("move", 7, 2500, 310.0, 120.0)
    with pytest.raises(ValueError):
        runner_mod.Fault(at_ms=0, kind="explode", nid=1)


def test_faults_are_ordered_and_persisted(tmp_path):
    """Arıza zamanı KOŞUMA GÖREDİR: aynı senaryo her koşumda aynı slotta."""
    faults = [runner_mod.Fault.parse("move:7@2500:310,120"),
              runner_mod.Fault.parse("kill:4@2000")]
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="f",
                                run_root=str(tmp_path), faults=faults)
    assert [f.at_ms for f in plan.faults] == [2000, 2500], "zamana göre sıralı"
    runner_mod.write_plan(plan)
    with open(os.path.join(str(tmp_path), "f", "run.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["faults"][0]["kind"] == "kill"
    # `--resume` yolunda arızalar geri yüklenebilmeli.
    back = [runner_mod.Fault(**f) for f in doc["faults"]]
    assert back == plan.faults


def test_fault_application_touches_the_right_station(tmp_path):
    """Arıza günlüğü AYRI dosyaya yazılır: düğüm bunu bilmez (api I1)."""
    plan = runner_mod.make_plan(
        EDGES, WEIGHTS, K, run_id="f", run_root=str(tmp_path),
        faults=[runner_mod.Fault.parse("kill:4@2000"),
                runner_mod.Fault.parse("move:7@2500:310,120")])
    runner_mod.write_plan(plan)

    class FakeSta:
        def __init__(self):
            self.cmds, self.pos = [], None

        def cmd(self, c):
            self.cmds.append(c)

        def setPosition(self, p):
            self.pos = p

    stations = {nid: FakeSta() for nid in WEIGHTS}
    class FakeProcess:
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    processes = {nid: FakeProcess() for nid in WEIGHTS}
    runner_mod.apply_fault(plan, stations, plan.faults[0], 2000,
                           processes=processes)
    runner_mod.apply_fault(plan, stations, plan.faults[1], 2500)
    assert processes[4].killed
    assert not any(p.killed for nid, p in processes.items() if nid != 4)
    assert not any(sta.cmds for sta in stations.values())
    assert stations[7].pos == "310.0,120.0,0"
    assert not stations[1].cmds and stations[1].pos is None
    lines = [json.loads(x) for x in
             open(os.path.join(plan.run_dir, "faults.jsonl"), encoding="utf-8")]
    assert [r["event"] for r in lines] == ["kill", "move"]
    # Düğüm günlüklerine SIZMAMALI.
    assert not os.path.exists(os.path.join(plan.run_dir, "4.jsonl"))


def test_collector_keeps_fault_journal_separate_from_node_logs(tmp_path):
    (tmp_path / "1.jsonl").write_text(
        json.dumps({"t_ms": 0, "event": "node_start"}) + "\n")
    (tmp_path / "faults.jsonl").write_text(
        json.dumps({"t_ms": 2000, "event": "kill", "nid": 4}) + "\n")
    assert set(collector.read_run(str(tmp_path))) == {1}


def test_process_cleanup_reaps_only_supplied_children():
    import subprocess

    children = [subprocess.Popen([sys.executable, "-c",
                                 "import time; time.sleep(30)"])
                for _ in range(3)]
    try:
        runner_mod.stop_processes({1: children[0], 2: children[1]})
        assert all(p.poll() is not None for p in children[:2])
        assert children[2].poll() is None, "another run must remain alive"
    finally:
        runner_mod.stop_processes(dict(enumerate(children)))


def test_kill_fault_refuses_unscoped_process_lookup(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="f",
                                run_root=str(tmp_path))
    with pytest.raises(ValueError, match="process handles"):
        runner_mod.apply_fault(plan, {4: object()},
                               runner_mod.Fault.parse("kill:4@2000"), 2000)


def test_quiescence_uses_relative_end_of_slot_and_waits(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="clock",
                                run_root=str(tmp_path))
    tau = plan.spec.channel.tau_ms
    logs = {nid: collector.NodeLog(nid, 0, "", [
        {"event": "node_done", "t_ms": 1000, "t_end_ms": 1000 + tau}])
        for nid in plan.spec.peers}
    assert runner_mod.quiescence(plan, logs, 1000 + 3 * tau)[0] is False
    assert runner_mod.quiescence(plan, logs, 1000 + 4 * tau)[0] is True


def test_quiescence_excludes_killed_nodes_without_masking_live_nodes(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="survivors",
        run_root=str(tmp_path), faults=[runner_mod.Fault.parse("kill:4@2000")])
    logs = {nid: collector.NodeLog(nid, 0, "", [
        {"event": "node_done", "t_ms": 1000}]) for nid in plan.spec.peers}
    del logs[7]
    assert runner_mod.quiescence(plan, logs, 10000) == (False, 8, 9)
    logs[7] = collector.NodeLog(7, 0, "", [{"event": "node_done", "t_ms": 1000}])
    assert runner_mod.quiescence(plan, logs, 10000) == (True, 9, 9)


def test_execute_refuses_existing_wireless_network_before_build(tmp_path, monkeypatch):
    import subprocess
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="collision",
                                run_root=str(tmp_path))
    monkeypatch.setattr(runner_mod.os, "geteuid", lambda: 0)
    # THE PID MUST BE A LIVE ONE ON THIS HOST. The guard now reads
    # /proc/<pid>/stat to tell a running daemon from a zombie, so a hardcoded
    # number makes the test depend on what happens to occupy that slot. It bit
    # us: the number previously written here was, on the development machine, a
    # real defunct wmediumd, and the guard correctly ignored it.
    live_pid = os.getpid()
    monkeypatch.setattr(runner_mod.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a, 0, f"{live_pid}\n", ""))
    monkeypatch.setattr(runner_mod.topo, "build_net", lambda *_:
                        pytest.fail("must refuse before allocating radios"))
    with pytest.raises(RuntimeError, match="Another wmediumd network"):
        runner_mod.execute(plan)


def test_execute_ignores_a_defunct_wmediumd(tmp_path, monkeypatch):
    """A zombie holds no radio, so refusing because of one is a false positive.

    A defunct process has already exited and released its netlink socket and
    hwsim radio; it lingers only until its parent reaps it, and `pgrep -x` still
    matches it by name. MEASURED: an orphaned wmediumd was terminated, an
    unrelated long-running service never reaped it, and the guard then refused
    every new network for as long as that service stayed alive. The only cure
    available to the user would have been killing somebody else's process.
    """
    import subprocess
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="zombie",
                                run_root=str(tmp_path))
    monkeypatch.setattr(runner_mod.os, "geteuid", lambda: 0)
    monkeypatch.setattr(runner_mod.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a, 0, "424242\n", ""))
    real_open = open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/424242/stat":
            import io
            return io.StringIO("424242 (wmediumd) Z 1 0 0 0 -1 0")
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    assert runner_mod._live_wmediumd_pids() == []


def test_unreadable_proc_entry_counts_as_live(tmp_path, monkeypatch):
    """Only a POSITIVE reading of "Z" excuses a process; anything else refuses.

    Guessing the permissive way on an unreadable /proc would let a second
    network onto a radio module that is already in use, and that costs more
    than one unnecessary refusal.
    """
    import subprocess
    monkeypatch.setattr(runner_mod.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a, 0, "424243\n", ""))
    real_open = open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/424243/stat":
            raise PermissionError("restricted /proc")
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    assert runner_mod._live_wmediumd_pids() == [424243]


def test_resume_preserves_nondefault_timing_addresses_and_propagation(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="resume",
        run_root=str(tmp_path), rho_max=0.025, udp_port=49002, prop_exp=4.2)
    runner_mod.write_plan(plan)
    restored = runner_mod.load_plan(plan.run_dir)
    assert restored.spec.channel.as_dict() == plan.spec.channel.as_dict()
    assert restored.spec.peers == plan.spec.peers
    assert restored.spec.prop_exp == 4.2
    assert restored.spec.mis_nbrs_max == plan.spec.mis_nbrs_max
    assert restored.run_dir == plan.run_dir


def test_evaluation_catches_duplicate_claims_hidden_by_owner_map(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from ccvc.bb.api import Role
    run = object.__new__(collector.RunCounters)
    run.roles = {1: Role.MIS, 2: Role.MIS}
    run.owned = {1: [(1, 2)], 2: [(2, 1)]}
    assert run.owner == {(1, 2): 2}
    assert run.double_owned_edges() == {(1, 2): [1, 2]}
    meta = {"channel": {"tau_ms": 200}, "edges": [[1, 2]],
            "weights": {"1": 1, "2": 1}, "k": 1}
    (tmp_path / "run.json").write_text(json.dumps(meta))
    monkeypatch.setattr(collector, "collect", lambda *a, **kw:
                       (run, {}, SimpleNamespace(as_dict=lambda: {})))
    doc = runner_mod.evaluate(str(tmp_path), compare_sim=False)
    assert not doc["validation"]["valid"]
    assert doc["validation"]["capacity"]
    assert any(v["kind"] == "duplicate_ownership" for v in doc["validation"]["violations"])


# --------------------------------------------------------------------------
# A RE-USED RUN DIRECTORY MUST NOT BE READ AS ONE RUN
#
# `JsonlLog` appends, so running twice into the same directory concatenates
# the executions. Both start their clock at 0, so sorting by `t_ms` used to
# interleave them and every derived quantity was computed over a graph that
# never existed. MEASURED on dag_anneal_n10_m20_s1: two `run_start` records
# 203 s apart, and one directed pair reading -74 dBm for 105 samples then
# -69 dBm for 108 more, the jump landing exactly where t_ms falls from 8056
# back to 4.
# --------------------------------------------------------------------------
def _rec(t, event, **kw):
    d = {"t_ms": t, "event": event, "mac": "02:00:00:00:00:01"}
    d.update(kw)
    return d


def test_only_the_last_execution_is_read_from_an_appended_log(tmp_path):
    old = [_rec(-10, "run_start", nid=1), _rec(0, "rx", rssi=-79.0, src="a"),
           _rec(8000, "done")]
    new = [_rec(-10, "run_start", nid=1), _rec(4, "rx", rssi=-69.0, src="a"),
           _rec(9000, "done")]
    path = tmp_path / "1.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for r in old + new:
            fh.write(json.dumps(r) + "\n")

    log = collector.read_node_log(str(path))

    # The old execution is gone, not merged: no -79 dBm sample survives, and
    # the seam that made t_ms run 8000 -> 4 cannot appear after sorting.
    assert log.stale_records == len(old)
    assert [r["rssi"] for r in log.records if r.get("event") == "rx"] == [-69.0]
    assert len(log.of("done")) == 1
    assert log.records == sorted(log.records, key=lambda r: r["t_ms"])


def test_a_log_with_one_execution_is_left_whole(tmp_path):
    recs = [_rec(-10, "run_start", nid=1), _rec(0, "rx", rssi=-70.0, src="a"),
            _rec(50, "done")]
    path = tmp_path / "1.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")

    log = collector.read_node_log(str(path))

    assert log.stale_records == 0
    assert len(log.records) == len(recs)


def test_writing_a_plan_clears_node_logs_left_by_an_earlier_run(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="reused",
                                run_root=str(tmp_path))
    runner_mod.write_plan(plan)
    stale = os.path.join(plan.run_dir, "7.jsonl")
    with open(stale, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec(0, "run_start", nid=7)) + "\n")
    keep = os.path.join(plan.run_dir, "faults.jsonl")
    with open(keep, "w", encoding="utf-8") as fh:
        fh.write("{}\n")

    runner_mod.write_plan(plan)

    # The station telemetry is cleared so the next run cannot append onto it;
    # the orchestrator's own files are not the collector's problem and stay.
    assert not os.path.exists(stale)
    assert os.path.exists(keep)
    assert os.path.exists(os.path.join(plan.run_dir, "run.json"))


# --------------------------------------------------------------------------
# R_MAX IS A CAP, NOT A COST
#
# Three attempts is a binding constraint at twenty stations: MEASURED on
# n20_m160, the handshake exhausted itself 14 to 134 times per run and a
# giving-up entry is never retried, so the neighbour stayed one-way and edges
# never formed. With eight attempts the same nine runs recorded zero give-ups.
# --------------------------------------------------------------------------
def test_handshake_attempts_grow_with_the_expected_neighbourhood():
    from ccvc.bb.mnwifi.config import link_attempts_for
    assert link_attempts_for(5) == 3, "seyrek komşulukta üç deneme yetiyordu"
    assert link_attempts_for(6) == 3
    assert link_attempts_for(18) >= 8, "yirmi istasyonda üç deneme bağlayıcıydı"
    assert link_attempts_for(30) > link_attempts_for(18)


def test_station_params_carry_the_density_scaled_attempt_cap(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="attempts",
                                run_root=str(tmp_path))
    from ccvc.bb.mnwifi.config import link_attempts_for
    assert plan.node_params["link_max_attempts"] == link_attempts_for(
        plan.spec.mis_nbrs_max)


def test_an_explicit_attempt_override_still_wins(tmp_path):
    plan = runner_mod.make_plan(EDGES, WEIGHTS, K, run_id="attempts_override",
                                run_root=str(tmp_path),
                                node_params={"link_max_attempts": 2})
    assert plan.node_params["link_max_attempts"] == 2


def test_records_before_a_lone_run_start_are_kept(tmp_path):
    """One execution needs no seam, and its preamble carries the MAC.

    The first version cut at the only `run_start`, which threw away the `open`
    record that names the station. Without it the node cannot be matched to its
    peers and every rx is attributed to nobody: a greedy provenance fixture
    went from 40 receptions to 0.
    """
    recs = [{"t_ms": 0, "event": "open", "mac": "02:00:00:00:00:09"},
            _rec(-10, "run_start", nid=9),
            _rec(5, "rx", rssi=-60.0, src="a")]
    path = tmp_path / "9.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")

    log = collector.read_node_log(str(path))

    assert log.stale_records == 0
    assert any(r.get("event") == "open" for r in log.records)
    assert len(log.records) == len(recs)
