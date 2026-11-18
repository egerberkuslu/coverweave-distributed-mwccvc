#!/usr/bin/env python3
"""The mininet-wifi ad-hoc topology built from a target graph (brief 7, 3.6).

WHY THERE IS NO ACCESS POINT. An AP is a COORDINATOR: broadcasts pass through
it, so the broadcast neighbourhood depends on association rather than position,
and BB-CVC's founding assumption -- "a broadcast is exactly the one-hop
neighbourhood" -- collapses. Hence ad-hoc (IBSS) mode and 255.255.255.255.

WHY wmediumd INTERFERENCE MODE. The default mode behaves close to "everyone
hears everyone"; range and RSSI are not real. In interference mode the
log-distance propagation model plus position produces a UNIT DISK graph, and
channel utilisation becomes observable.

THIS FILE HAS THREE JOBS
  1. Generate positions that REALISE the target graph as a unit disk graph.
  2. Measure which graph those positions ACTUALLY produce and compare it to the
     target (missing/extra edges). This is not a debugging aid, it is a
     DELIVERABLE: it is the one number that says how faithfully the emulator
     realises the intended topology.
  3. Compute T_hello and tau FROM THE TOPOLOGY via the channel-time rule
     (brief 3.6). Never hard-coded, always written to the log.

The only part that needs privilege is `build_net`; everything else runs without
sudo and is covered by tests.
"""
from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from ccvc.bb.bbcvc import mac_for_id  # noqa: E402
from ccvc.bb.bootstrap import t_hello_lower_bound_ms  # noqa: E402

Edge = Tuple[int, int]
Pos = Tuple[float, float]


def edge(u: int, v: int) -> Edge:
    return (u, v) if u <= v else (v, u)


# ==========================================================================
# 1. Channel-time rule (brief 3.6)
# ==========================================================================
#: Frame time at 1 Mbps. The brief gives two anchors: 24 B ~ 0.7 ms and
#: 250 B ~ 2.5 ms. The only affine model that satisfies both is 0.5 ms of fixed
#: overhead plus 8 bits/byte (24 B -> 0.692, 250 B -> 2.500). So the model is
#: DERIVED from the brief rather than invented; the fixed part is preamble plus
#: header plus SIFS.
FRAME_OVERHEAD_MS = 0.5
DEFAULT_RATE_MBPS = 1.0


def t_frame_ms(nbytes: int, rate_mbps: float = DEFAULT_RATE_MBPS) -> float:
    """Analytic frame time. It is COMPUTED, never measured (brief section 7)."""
    return FRAME_OVERHEAD_MS + (nbytes * 8.0) / (rate_mbps * 1000.0)


def two_hop_counts(edges: Iterable[Edge], nodes: Optional[Iterable[int]] = None
                   ) -> Dict[int, int]:
    """Two-hop neighbour count N2(v) per node, excluding the node itself."""
    adj: Dict[int, Set[int]] = {}
    for u, v in edges:
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)
    for n in (nodes or ()):
        adj.setdefault(int(n), set())
    out: Dict[int, int] = {}
    for v, nb in adj.items():
        s: Set[int] = set(nb)
        for u in nb:
            s |= adj[u]
        s.discard(v)
        out[v] = len(s)
    return out


@dataclass(frozen=True)
class ChannelTime:
    """What the channel-time rule of brief 3.6 yields for a given topology.

    `t_hello_ms` is a LOWER BOUND; the run uses it as-is and writes it to the
    log. `tau_ms ~ 1.2 * T_hello` (brief section 7).
    """

    n2_max: int
    n2_by_node: Dict[int, int]
    t_frame_ms: float
    rho_max: float
    t_hello_ms: int
    tau_ms: int
    hello_bytes: int

    def as_dict(self) -> Dict[str, object]:
        return {"n2_max": self.n2_max, "t_frame_ms": round(self.t_frame_ms, 4),
                "rho_max": self.rho_max, "t_hello_ms": self.t_hello_ms,
                "tau_ms": self.tau_ms, "hello_bytes": self.hello_bytes,
                "rule": "T_hello >= N2 * t_f / rho_max  (brief 3.6)"}


def channel_time(edges: Iterable[Edge], *, nodes: Optional[Iterable[int]] = None,
                 hello_bytes: int = 24, rho_max: float = 0.1,
                 rate_mbps: float = DEFAULT_RATE_MBPS,
                 tau_factor: float = 1.2) -> ChannelTime:
    """T_hello >= N2 * t_f / rho_max; tau ~ 1.2 * T_hello.

    N2 is a quantity the node CANNOT KNOW (it is two hops away), so the run
    script computes it from the topology and passes it in -- exactly what
    `bootstrap.t_hello_lower_bound_ms` documents.

    `hello_bytes` defaults to 24 because that is the brief's frame-time anchor.
    A real HELLO is 13 + 2*|mis_nbrs| bytes, so 24 errs on the safe side.
    """
    n2 = two_hop_counts(edges, nodes)
    n2_max = max(n2.values()) if n2 else 0
    tf = t_frame_ms(hello_bytes, rate_mbps)
    t_hello = t_hello_lower_bound_ms(n2_max, t_frame_ms=tf, rho_max=rho_max)
    return ChannelTime(n2_max=n2_max, n2_by_node=n2, t_frame_ms=tf,
                       rho_max=rho_max, t_hello_ms=t_hello,
                       tau_ms=int(math.ceil(tau_factor * t_hello)),
                       hello_bytes=int(hello_bytes))


# ==========================================================================
# 2. Position generation: realise the target graph as a unit disk graph
# ==========================================================================
@dataclass
class LayoutResult:
    positions: Dict[int, Pos]
    radio_range_m: float
    margin: float
    iterations: int
    #: How many node pairs disagree with the target (the layout's own measure).
    conflicts: int


def _pairs(nodes: Sequence[int]) -> List[Tuple[int, int]]:
    return [(i, j) for i in range(len(nodes)) for j in range(i + 1, len(nodes))]


def layout(edges: Iterable[Edge], nodes: Optional[Iterable[int]] = None, *,
           radio_range_m: float = 100.0, margin: float = 0.15,
           iterations: int = 600, seed: int = 0,
           restarts: int = 4) -> LayoutResult:
    """Positions realising the target graph; returns the BEST restart.

    The hinge refinement is a LOCAL optimiser and at moderate density (average
    degree 5-7) it has many local minima: the same graph can finish with 17
    conflicts or with 0 depending only on the starting point (measured). So
    several seeds are tried and the one with the FEWEST CONFLICTS wins. The
    selection criterion is the symmetric difference against the target, which
    is precisely the number the experiment reports; no proxy metric is used.
    """
    best: Optional[LayoutResult] = None
    for r in range(max(1, int(restarts))):
        cand = _layout_once(edges, nodes, radio_range_m=radio_range_m,
                            margin=margin, iterations=iterations,
                            seed=seed * 1009 + r)
        if best is None or cand.conflicts < best.conflicts:
            best = cand
        if best.conflicts == 0:
            break
    assert best is not None
    return LayoutResult(positions=best.positions, radio_range_m=radio_range_m,
                        margin=margin, iterations=iterations,
                        conflicts=best.conflicts)


def _layout_once(edges: Iterable[Edge], nodes: Optional[Iterable[int]] = None, *,
                 radio_range_m: float = 100.0, margin: float = 0.15,
                 iterations: int = 600, seed: int = 0) -> LayoutResult:
    """One layout attempt: spring layout followed by unit-disk refinement.

    A plain spring layout IS NOT DESIGNED FOR UNIT-DISK REALISATION: it shortens
    edges but has no term pushing non-adjacent pairs out of range. Hence two
    stages:

      1. spring layout (Fruchterman-Reingold) for a reasonable starting point,
      2. hinge refinement -- if adjacent, want d < r(1-m); if not adjacent, want
         d > r(1+m); only VIOLATING pairs generate force.

    The second stage optimises the objective directly. Not every graph is a unit
    disk graph (K_{1,6} is the smallest star that cannot be realised: six leaves
    sit at best 60 degrees apart, and at that angle the chord equals the radius,
    so two leaves are inevitably in range of each other). So `conflicts > 0` is
    not a bug, it MEASURES how far the target is from being realisable as a unit
    disk graph, and it goes into the report.
    """
    tgt = {edge(u, v) for u, v in edges}
    ids = sorted({a for e in tgt for a in e} | set(int(n) for n in (nodes or ())))
    n = len(ids)
    if n == 0:
        return LayoutResult({}, radio_range_m, margin, 0, 0)
    if n == 1:
        return LayoutResult({ids[0]: (0.0, 0.0)}, radio_range_m, margin, 0, 0)

    idx = {nid: i for i, nid in enumerate(ids)}
    adj = [[False] * n for _ in range(n)]
    for u, v in tgt:
        adj[idx[u]][idx[v]] = adj[idx[v]][idx[u]] = True

    rng = random.Random(seed * 2654435761 + 0x5EED)
    side = radio_range_m * math.sqrt(max(n, 2)) / 1.6
    px = [rng.uniform(0.0, side) for _ in range(n)]
    py = [rng.uniform(0.0, side) for _ in range(n)]

    # --- 1. spring layout -------------------------------------------------
    k = side / math.sqrt(n)
    temp = side / 6.0
    spring_iters = max(1, iterations // 3)
    for it in range(spring_iters):
        dx = [0.0] * n
        dy = [0.0] * n
        for i in range(n):
            for j in range(i + 1, n):
                ex, ey = px[i] - px[j], py[i] - py[j]
                d2 = ex * ex + ey * ey
                if d2 < 1e-9:
                    ex, ey, d2 = rng.uniform(-1, 1), rng.uniform(-1, 1), 1.0
                d = math.sqrt(d2)
                rep = (k * k) / d
                fx, fy = ex / d * rep, ey / d * rep
                dx[i] += fx; dy[i] += fy
                dx[j] -= fx; dy[j] -= fy
                if adj[i][j]:
                    att = (d * d) / k
                    ax, ay = ex / d * att, ey / d * att
                    dx[i] -= ax; dy[i] -= ay
                    dx[j] += ax; dy[j] += ay
        for i in range(n):
            d = math.hypot(dx[i], dy[i]) or 1.0
            step = min(d, temp)
            px[i] += dx[i] / d * step
            py[i] += dy[i] / d * step
        temp *= 0.95

    # --- 2. global scale: put the median edge length inside the range ------
    # The spring layout gets the SHAPE right but its SCALE is arbitrary. Pulling
    # every edge inside the range with a single factor cuts the number of
    # violations the hinge refinement has to fix by an order of magnitude.
    def _scale_to(factor: float) -> None:
        cx = sum(px) / n
        cy = sum(py) / n
        for i in range(n):
            px[i] = cx + (px[i] - cx) * factor
            py[i] = cy + (py[i] - cy) * factor

    lens = sorted(math.hypot(px[i] - px[j], py[i] - py[j])
                  for i in range(n) for j in range(i + 1, n) if adj[i][j])
    if lens:
        med = lens[len(lens) // 2]
        if med > 1e-9:
            _scale_to(radio_range_m * 0.80 / med)

    # --- 3. unit-disk refinement ------------------------------------------
    r_in = radio_range_m * (1.0 - margin)
    r_out = radio_range_m * (1.0 + margin)
    refine_iters = max(1, iterations - spring_iters)
    for it in range(refine_iters):
        # THE STEP CAP IS MANDATORY. Hinge forces are summed PER PAIR; in a
        # dense graph one node has fifty non-neighbours, and an uncapped step
        # blows the layout apart (measured: at n=60 with average degree 9.6
        # every edge was flung out of range, Jaccard 0). The cap plays the same
        # role as `temp` does in the spring phase.
        cool = radio_range_m * (0.18 * (1.0 - it / refine_iters) + 0.01)
        dx = [0.0] * n
        dy = [0.0] * n
        for i in range(n):
            for j in range(i + 1, n):
                ex, ey = px[i] - px[j], py[i] - py[j]
                d = math.hypot(ex, ey)
                if d < 1e-9:
                    ex, ey, d = rng.uniform(-1, 1), rng.uniform(-1, 1), 1.0
                if adj[i][j]:
                    if d <= r_in:
                        continue
                    pull = min(d - r_in, radio_range_m)   # pull together
                    fx, fy = -ex / d * pull, -ey / d * pull
                else:
                    if d >= r_out:
                        continue
                    push = r_out - d                       # push apart
                    fx, fy = ex / d * push, ey / d * push
                dx[i] += fx; dy[i] += fy
                dx[j] -= fx; dy[j] -= fy
        for i in range(n):
            d = math.hypot(dx[i], dy[i])
            if d < 1e-9:
                continue
            step = min(d, cool)
            px[i] += dx[i] / d * step
            py[i] += dy[i] / d * step

    # --- 4. global scale search: pick the factor with fewest conflicts -----
    # The refinement is a local optimiser, and a single wrong scale factor
    # corrupts every edge at once. This one-dimensional search is cheap and
    # removes that failure mode entirely.
    best = (None, None)
    snapshot = (list(px), list(py))
    for factor in (0.88, 0.92, 0.96, 1.0, 1.04, 1.08, 1.12):
        px[:], py[:] = list(snapshot[0]), list(snapshot[1])
        _scale_to(factor)
        cand = {(ids[i], ids[j]) if ids[i] <= ids[j] else (ids[j], ids[i])
                for i in range(n) for j in range(i + 1, n)
                if math.hypot(px[i] - px[j], py[i] - py[j]) <= radio_range_m}
        bad = len(tgt ^ cand)
        if best[0] is None or bad < best[0]:
            best = (bad, (list(px), list(py)))
    px[:], py[:] = best[1]

    # Move into the positive quadrant (mininet wants a 'x,y,z' position string).
    mnx, mny = min(px), min(py)
    pos = {ids[i]: (round(px[i] - mnx + 10.0, 2), round(py[i] - mny + 10.0, 2))
           for i in range(n)}
    got = realised_edges(pos, radio_range_m)
    return LayoutResult(positions=pos, radio_range_m=radio_range_m,
                        margin=margin, iterations=iterations,
                        conflicts=len(tgt ^ got))


def realised_edges(positions: Dict[int, Pos], radio_range_m: float) -> Set[Edge]:
    """The unit disk graph the positions ACTUALLY produce."""
    ids = sorted(positions)
    out: Set[Edge] = set()
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            u, v = ids[a], ids[b]
            (x1, y1), (x2, y2) = positions[u], positions[v]
            if math.hypot(x1 - x2, y1 - y2) <= radio_range_m:
                out.add((u, v))
    return out


# ==========================================================================
# 3. Target versus observed (A DELIVERABLE, brief section 7)
# ==========================================================================
@dataclass
class TopologyDiff:
    """The difference between the target graph and the one actually observed.

    `missing`  in the target, not observed -> loss, asymmetry, RSSI threshold
    `extra`    observed, not in the target -> range calibration is too wide

    These two lists are a measurement that CANNOT BE OBTAINED on a real device;
    ground truth is the emulator's one genuine advantage over hardware.
    """

    target: Set[Edge]
    observed: Set[Edge]
    missing: List[Edge] = field(default_factory=list)
    extra: List[Edge] = field(default_factory=list)

    @property
    def exact(self) -> bool:
        return not self.missing and not self.extra

    @property
    def jaccard(self) -> float:
        uni = self.target | self.observed
        if not uni:
            return 1.0
        return round(len(self.target & self.observed) / len(uni), 6)

    def as_dict(self) -> Dict[str, object]:
        return {"n_target": len(self.target), "n_observed": len(self.observed),
                "n_missing": len(self.missing), "n_extra": len(self.extra),
                "missing": [list(e) for e in self.missing],
                "extra": [list(e) for e in self.extra],
                "jaccard": self.jaccard, "exact": self.exact}

    def summary(self) -> str:
        if self.exact:
            return f"topology realised exactly ({len(self.target)} edges)"
        return (f"target {len(self.target)} edges, observed {len(self.observed)}; "
                f"{len(self.missing)} missing, {len(self.extra)} extra, "
                f"Jaccard {self.jaccard}")


def compare_topology(target: Iterable[Edge], observed: Iterable[Edge]) -> TopologyDiff:
    t = {edge(u, v) for u, v in target}
    o = {edge(u, v) for u, v in observed}
    return TopologyDiff(target=t, observed=o,
                        missing=sorted(t - o), extra=sorted(o - t))


# ==========================================================================
# 4. Adresleme: MAC, IP, UDP portu
# ==========================================================================
@dataclass(frozen=True)
class Peer:
    """A station's identity inside the emulator.

    `mac` is THE ALGORITHM's address and it is assigned to the interface's REAL
    MAC. That is required: RSSI is read with `iw dev staX-wlan0 station dump`,
    keyed by peer MAC, so if the interface MAC differed from the algorithm MAC
    no RSSI reading could be attached to any neighbour.

    `mac_for_id` is used because it guarantees `hash16(mac) == nid`. When the
    node DERIVES its own identity from its MAC it therefore arrives at the same
    identity the simulator used, which is what makes the counters of the two
    runs comparable at all.
    """

    nid: int
    station: str
    mac: int
    ip: str
    udp_port: int

    @property
    def mac_str(self) -> str:
        return format_mac(self.mac)

    @property
    def iface(self) -> str:
        return f"{self.station}-wlan0"


def format_mac(mac: int) -> str:
    b = int(mac) & 0xFFFFFFFFFFFF
    return ":".join(f"{(b >> s) & 0xFF:02x}" for s in (40, 32, 24, 16, 8, 0))


def parse_mac(text: str) -> int:
    parts = text.strip().split(":")
    if len(parts) != 6:
        raise ValueError(f"malformed MAC: {text!r}")
    v = 0
    for p in parts:
        v = (v << 8) | int(p, 16)
    return v


def assign_peers(nodes: Iterable[int], *, udp_port: int = 47001,
                 subnet: str = "10.0") -> Dict[int, Peer]:
    """Derive station name, MAC, IP and port from node ids.

    The IP is derived from the INDEX, not from the identity: hash16 identities
    are 16-bit and could land on reserved addresses such as .0 or .255.
    """
    ids = sorted(int(n) for n in set(nodes))
    if len(ids) > 254 * 254:
        raise ValueError("address space exhausted")
    out: Dict[int, Peer] = {}
    for i, nid in enumerate(ids):
        ip = f"{subnet}.{i // 254}.{(i % 254) + 1}"
        out[nid] = Peer(nid=nid, station=f"sta{i + 1}", mac=mac_for_id(nid),
                        ip=ip, udp_port=udp_port)
    macs = {p.mac for p in out.values()}
    if len(macs) != len(out):
        raise ValueError("MAC collision: mac_for_id gave two ids the same MAC")
    return out


def peers_to_json(peers: Dict[int, Peer]) -> Dict[str, object]:
    return {"udp_port": next(iter(peers.values())).udp_port if peers else 0,
            "peers": [{"nid": p.nid, "station": p.station, "mac": p.mac_str,
                       "ip": p.ip, "udp_port": p.udp_port}
                      for p in sorted(peers.values(), key=lambda q: q.nid)]}


def peers_from_json(doc: Dict[str, object]) -> Dict[int, Peer]:
    out: Dict[int, Peer] = {}
    for row in doc["peers"]:                      # type: ignore[index]
        p = Peer(nid=int(row["nid"]), station=str(row["station"]),
                 mac=parse_mac(str(row["mac"])), ip=str(row["ip"]),
                 udp_port=int(row["udp_port"]))
        out[p.nid] = p
    return out


# ==========================================================================
# 5. The privileged part: build the mininet-wifi network
# ==========================================================================
MININET_WIFI_HOME = "/home/ege/mininet-wifi"


def mininet_available() -> bool:
    """Check the usable net class, not merely the mn_wifi namespace package."""
    try:
        from mn_wifi.net import Mininet_wifi  # noqa: F401
        return True
    except Exception:
        for directory in (MININET_WIFI_HOME, os.path.join(MININET_WIFI_HOME, "mininet")):
            if os.path.isdir(directory) and directory not in sys.path:
                sys.path.insert(0, directory)
        try:
            from mn_wifi.net import Mininet_wifi  # noqa: F401
            return True
        except Exception:
            return False
        return False


@dataclass
class TopoSpec:
    """Everything the privileged run needs. PRODUCIBLE without sudo."""

    edges: List[Edge]
    weights: Dict[int, int]
    k: int
    positions: Dict[int, Pos]
    peers: Dict[int, Peer]
    radio_range_m: float
    channel: ChannelTime
    geometric_diff: TopologyDiff
    prop_exp: float = 3.0
    rate_mbps: float = DEFAULT_RATE_MBPS
    mis_nbrs_max: int = 5
    """Maximum MIS neighbours carried in a HELLO (`BbcvcParams.mis_nbrs_max`).

    A FIXED 5 IS NOT ENOUGH. G8 is a unit-disk theorem; the measurement in
    `BULGULAR_BB.md` shows that on the Dagdeviren benchmark at n=200 every node
    exceeds 5, with a maximum of 17. So the value is DERIVED FROM THE TOPOLOGY:
    the maximum degree is a safe upper bound (an independent neighbour set
    cannot exceed the degree), and at 17 entries a HELLO is 47 bytes, far below
    the 250 B design ceiling.
    """
    max_degree: int = 0

    def as_dict(self) -> Dict[str, object]:
        return {
            "k": self.k,
            "mis_nbrs_max": self.mis_nbrs_max,
            "max_degree": self.max_degree,
            "n": len(self.peers),
            "m": len(self.edges),
            "radio_range_m": self.radio_range_m,
            "prop_exp": self.prop_exp,
            "rate_mbps": self.rate_mbps,
            "channel": self.channel.as_dict(),
            "geometric": self.geometric_diff.as_dict(),
            "positions": {str(n): list(p) for n, p in sorted(self.positions.items())},
            "weights": {str(n): w for n, w in sorted(self.weights.items())},
            "edges": [list(e) for e in self.edges],
            "peers": peers_to_json(self.peers),
        }


def plan(edges: Sequence[Edge], weights: Dict[int, int], k: int, *,
         radio_range_m: float = 100.0, margin: float = 0.15,
         seed: int = 0, udp_port: int = 47001, rho_max: float = 0.1,
         hello_bytes: int = 24, prop_exp: float = 3.0,
         iterations: int = 600) -> TopoSpec:
    """Unprivileged planning: positions, addresses, T_hello, tau, geometry."""
    nodes = sorted({a for e in edges for a in e} | set(weights))
    lay = layout(edges, nodes, radio_range_m=radio_range_m, margin=margin,
                 iterations=iterations, seed=seed)
    ch = channel_time(edges, nodes=nodes, hello_bytes=hello_bytes, rho_max=rho_max)
    diff = compare_topology(edges, realised_edges(lay.positions, radio_range_m))
    deg: Dict[int, int] = {n: 0 for n in nodes}
    for u, v in edges:
        deg[u] += 1
        deg[v] += 1
    dmax = max(deg.values()) if deg else 0
    return TopoSpec(edges=[edge(u, v) for u, v in edges],
                    weights={int(n): float(w) for n, w in weights.items()},
                    k=int(k), positions=lay.positions,
                    peers=assign_peers(nodes, udp_port=udp_port),
                    radio_range_m=radio_range_m, channel=ch,
                    geometric_diff=diff, prop_exp=prop_exp,
                    mis_nbrs_max=max(5, dmax), max_degree=dmax)


def build_net(spec: TopoSpec, *, ssid: str = "mwccvc", channel: int = 1,
              mode: str = "g", noise_th: int = -91, fading: float = 0.0):
    """Build the ad-hoc network. REQUIRES PRIVILEGE; only called under sudo.

    The setup order is binding in mininet-wifi: stations -> propagation model ->
    configureWifiNodes -> adhoc links -> build/start. Positions must be supplied
    before `configureWifiNodes`, otherwise wmediumd computes its first SNR with
    no positions at all.
    """
    if not mininet_available():
        raise RuntimeError("cannot import mn_wifi; is mininet-wifi installed?")
    from mn_wifi.net import Mininet_wifi
    from mn_wifi.link import adhoc, wmediumd
    from mn_wifi.wmediumdConnector import interference

    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference, noise_th=noise_th,
                       fading_cof=fading)
    stations = {}
    for nid, p in sorted(spec.peers.items()):
        x, y = spec.positions[nid]
        stations[nid] = net.addStation(
            p.station, mac=p.mac_str, ip=f"{p.ip}/8",
            position=f"{x},{y},0", range=int(spec.radio_range_m))
    net.setPropagationModel(model="logDistance", exp=spec.prop_exp)
    net.configureWifiNodes()
    for nid, sta in sorted(stations.items()):
        net.addLink(sta, cls=adhoc, intf=f"{spec.peers[nid].station}-wlan0",
                    ssid=ssid, mode=mode, channel=channel)
    net.build()
    net.start()
    return net, stations


def static_arp_commands(spec: TopoSpec) -> Dict[int, List[str]]:
    """Permanent ARP entries for every station.

    ARP RESOLUTION WOULD POLLUTE THE EXPERIMENT: every unicast would be preceded
    by an ARP broadcast that occupies the channel and generates collisions while
    never appearing in the counters. We already hold the table, so it is filled
    statically.
    """
    out: Dict[int, List[str]] = {}
    for nid, p in sorted(spec.peers.items()):
        cmds = []
        for other in sorted(spec.peers.values(), key=lambda q: q.nid):
            if other.nid == nid:
                continue
            cmds.append(f"ip neigh replace {other.ip} lladdr {other.mac_str} "
                        f"dev {p.iface} nud permanent")
        out[nid] = cmds
    return out


def netem_command(spec: TopoSpec, nid: int, loss_pct: float) -> str:
    """Extra loss (brief 7: 0/5/15 percent), per interface, on top of wmediumd."""
    p = spec.peers[nid]
    if loss_pct <= 0:
        return f"tc qdisc del dev {p.iface} root 2>/dev/null || true"
    return (f"tc qdisc replace dev {p.iface} root netem "
            f"loss {float(loss_pct):g}%")
