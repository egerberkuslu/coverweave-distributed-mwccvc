#!/usr/bin/env python3
"""The mininet-wifi/UDP implementation of `Platform` (brief section 7, api I2/I3).

THE CONTRACT IS THE SAME FOUR CALLS. Node code cannot discover that it is on an
emulator: it holds `send_broadcast`, `send_unicast`, `now_ms`, `log` and its own
`mac`. Whatever `SimNet._Port` offers, this class offers, and nothing more. The
receive path (`receive`) is deliberately OUTSIDE Platform: the node does not pull
frames itself, `node_main` pulls them and hands them to `on_frame`, exactly as
`SimNet.deliver` does.

This is not an argument, it is a result. The same unmodified `BbcvcNode`
reproduces the simulator's counters exactly across ten separate OS processes, so
every difference between the platforms sits BELOW this interface.

WHY `src` IS NOT IN THE PAYLOAD, AND WHERE THIS IMPLEMENTATION FALLS SHORT.
Both halves matter and both are stated, because the second one is easy to leave
implicit and it should not be.

  The justification is physical and it survives. `src` in `on_frame(src, ...)`
  is the sender's 48-bit MAC (the api.NodeCore.on_frame decision). IEEE 802.11
  carries the transmitter address in Address 2 of EVERY frame header, mandated
  by the standard and independent of whatever runs above it. ESP-NOW inherits
  that; it does not provide it. Now that mininet-wifi is the reference platform
  rather than a validation step, the reasoning rests on a standard instead of on
  a vendor protocol, which makes it stronger than it was.

  The implementation here is a stand-in. A UDP socket CANNOT SEE the 802.11
  header. `recvmsg` returns the source (ip, port); this port maps that to a MAC
  through its own address table. The payload is never opened to find out who
  sent it, so the node's contract is intact, but the address does not come off
  the wire the way it would on a device. This is the same privilege
  `SimNet._unicast` takes with `self._by_mac`: the table belongs to the
  PLATFORM, never to the node.

  PROPOSAL ON RECORD, NOT YET TAKEN (team lead, deferred deliberately).
  `AF_PACKET`/`SOCK_RAW` would read the real source MAC out of the frame header
  and drop the IP/UDP/ARP layer entirely, which is closer to ESP-NOW addressing
  rather than further from it. Cost: it needs CAP_NET_RAW (free inside a
  station, which is already root) and it would trade away the unprivileged
  loopback tests that presently cover the whole port. The shape it should take
  when it happens is UDP kept as the testable path with raw sockets opt-in, so
  the suite never goes dark. Sequenced AFTER the current verification pass, not
  during it.

TIMESTAMPS AND SLOT FIDELITY. In the simulator's synchronous mode a frame sent
in slot t is processed at the START of slot t+1. A real socket does not do this
by itself: inside a 59 ms slot a 1 ms UDP datagram arrives within the SAME slot.
So each datagram's KERNEL ARRIVAL TIME is read via `SO_TIMESTAMPNS` and the
frame is deferred to slot `floor(t_arrival/tau) + 1`. The simulator's slot
semantics are preserved without adding a single byte to the payload (putting a
slot number in the payload would have polluted both the size budget and the wire
format).
"""
from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

from ccvc.bb import wire  # noqa: E402
from ccvc.bb.api import MAX_PAYLOAD, PayloadTooLarge, Platform  # noqa: E402
from ccvc.bb.mnwifi.topology import Peer, format_mac, parse_mac  # noqa: E402

Addr = Tuple[str, int]

#: SO_TIMESTAMPNS is missing from the socket module on some Python/kernel pairs.
SO_TIMESTAMPNS = getattr(socket, "SO_TIMESTAMPNS", 35)
SCM_TIMESTAMPNS = getattr(socket, "SCM_TIMESTAMPNS", 35)
SO_BINDTODEVICE = getattr(socket, "SO_BINDTODEVICE", 25)


# ==========================================================================
# 1. Address table
# ==========================================================================
class AddressMap:
    """MAC <-> socket address. Lives in the platform, outside the node's view.

    One class covers both deployments because the only difference is the
    BROADCAST MECHANISM:
      subnet  : mininet-wifi. Each station has its own IP and a shared UDP
                port; a broadcast is one datagram to 255.255.255.255
                (brief section 7).
      fanout  : loopback. One IP, a separate port per node; a broadcast is
                IMITATED by writing to each peer in turn. For unprivileged
                tests only. It does not corrupt the accounting, because `tx` is
                logged once per send CALL, not per datagram.
    """

    def __init__(
        self,
        peers: Dict[int, Peer],
        me: int,
        *,
        broadcast: str = "subnet",
        broadcast_ip: str = "255.255.255.255",
        reach: Optional[Iterable[int]] = None,
    ) -> None:
        if me not in peers:
            raise ValueError(f"my own id is not in the table: {me}")
        if broadcast not in ("subnet", "fanout"):
            raise ValueError(f"unknown broadcast mode: {broadcast!r}")
        self.peers = dict(peers)
        self.me = int(me)
        self.mode = broadcast
        self.broadcast_ip = broadcast_ip
        self._by_mac: Dict[int, Addr] = {
            p.mac: (p.ip, p.udp_port) for p in peers.values()
        }
        self._by_addr: Dict[Addr, int] = {
            (p.ip, p.udp_port): p.mac for p in peers.values()
        }
        #: Radio range. `None` means THE RADIO decides (wmediumd on
        #: mininet-wifi). On loopback there is no radio, so range is imitated
        #: here. This is the counterpart of `SimNet._adj` and it lives in the
        #: PLATFORM for the same reason: the medium knows the neighbourhood,
        #: the node does not (I1).
        self.reach: Optional[Set[int]] = (
            None if reach is None else {int(m) for m in reach}
        )

    @property
    def my_peer(self) -> Peer:
        return self.peers[self.me]

    @property
    def my_mac(self) -> int:
        return self.my_peer.mac

    def bind_addr(self) -> Addr:
        p = self.my_peer
        return ("" if self.mode == "subnet" else p.ip, p.udp_port)

    def addr_of(self, mac: int) -> Optional[Addr]:
        return self._by_mac.get(int(mac) & 0xFFFFFFFFFFFF)

    def mac_of(self, addr: Addr) -> Optional[int]:
        hit = self._by_addr.get((addr[0], int(addr[1])))
        if hit is not None:
            return hit
        # In subnet mode the source port may be ephemeral; the IP alone suffices.
        for (ip, _port), mac in self._by_addr.items():
            if ip == addr[0]:
                return mac
        return None

    def in_range(self, mac: int) -> bool:
        return self.reach is None or int(mac) in self.reach

    def broadcast_targets(self) -> List[Addr]:
        if self.mode == "subnet":
            return [(self.broadcast_ip, self.my_peer.udp_port)]
        return [
            (p.ip, p.udp_port)
            for p in sorted(self.peers.values(), key=lambda q: q.nid)
            if p.nid != self.me and self.in_range(p.mac)
        ]


# ==========================================================================
# 2. RSSI: iw dev staX-wlan0 station dump
# ==========================================================================
def parse_station_dump(text: str) -> Dict[int, float]:
    """Turn `iw ... station dump` output into {MAC: signal dBm}.

    `signal avg` is preferred when present: the single-frame `signal` is very
    noisy under wmediumd and would trip the hysteresis (brief 3.5/4) spuriously.
    """
    out: Dict[int, float] = {}
    cur: Optional[int] = None
    best: Dict[int, Tuple[int, float]] = {}  # mac -> (priority, value)
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith("station "):
            try:
                cur = parse_mac(line.split()[1])
            except Exception:
                cur = None
            continue
        if cur is None or ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = label.strip().lower()
        if label not in ("signal", "signal avg"):
            continue
        tok = value.strip().split()
        if not tok:
            continue
        try:
            dbm = float(tok[0])
        except ValueError:
            continue
        prio = 2 if label == "signal avg" else 1
        if cur not in best or best[cur][0] <= prio:
            best[cur] = (prio, dbm)
    for mac, (_prio, dbm) in best.items():
        out[mac] = dbm
    return out


class RssiReader:
    """Polls the interface periodically and holds the RSSI for `on_frame`.

    Calling `iw` per frame DOES NOT WORK: each call spawns a process, and with
    dozens of frames in a 59 ms slot it would push the node off its schedule.
    So it is read once per `period_ms` and frames in between take the last
    reading. On a real device RSSI arrives WITH the frame; this is an emulator
    deviation and it is reported rather than hidden.
    """

    def __init__(
        self,
        iface: str,
        *,
        period_ms: int = 500,
        runner: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.iface = iface
        self.period_ms = int(period_ms)
        self._runner = runner or self._iw
        self._cache: Dict[int, float] = {}
        self._next_ms = 0
        self.reads = 0
        self.failures = 0

    @staticmethod
    def _iw(iface: str) -> str:
        return subprocess.run(
            ["iw", "dev", iface, "station", "dump"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout

    def refresh(self, now_ms: int, *, force: bool = False) -> Dict[int, float]:
        if not force and now_ms < self._next_ms:
            return self._cache
        self._next_ms = int(now_ms) + self.period_ms
        try:
            self._cache = parse_station_dump(self._runner(self.iface))
            self.reads += 1
        except Exception:
            self.failures += 1
        return self._cache

    def of(self, mac: int) -> Optional[float]:
        return self._cache.get(int(mac))


# ==========================================================================
# 3. Log
# ==========================================================================
class JsonlLog:
    """One event per line. Namespaces share the filesystem, so the log NEVER
    TRAVELS OVER THE NETWORK (brief section 7); the collector reads it directly."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self._fh = open(path, "a", buffering=1, encoding="utf-8")
        self.n = 0

    def write(self, rec: Dict[str, object]) -> None:
        self._fh.write(json.dumps(rec, separators=(",", ":"), sort_keys=True) + "\n")
        self.n += 1

    def flush(self) -> None:
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        try:
            self.flush()
        finally:
            self._fh.close()


# ==========================================================================
# 4. Frame
# ==========================================================================
@dataclass(frozen=True)
class RxFrame:
    src_mac: int
    rssi: Optional[float]
    payload: bytes
    t_recv_ms: int


# ==========================================================================
# 4b. Measurement hook: directed, typed, counted frame drop
# ==========================================================================
@dataclass
class DropRule:
    """Drop one frame surgically. THIS IS A MEASUREMENT HOOK.

    It is the emulator's counterpart of the `SimNet.drop` predicate and exists
    for the same reason: the faults brief 3.4 asks us to test CANNOT BE WRITTEN
    with probabilistic loss. The test "drop a single HELLO and show the
    stability gate does not freeze a wrong key" (brief 3.5/5) cannot be built
    from 5 percent netem; it needs exactly one frame. The rule is applied at the
    SENDER, because a broadcast is a single transmission.

    The node CANNOT SEE this hook: a dropped frame is counted in `tx` and not in
    `rx`, exactly as if it had been lost on the channel. From the node's side
    there is no difference between the two (I1).

    NOT INSTEAD OF netem, ALONGSIDE IT: the 0/5/15 percent channel loss comes
    from `tc netem` (brief section 7); this hook is only for counted, typed
    faults.
    """

    mtype: Optional[int] = None  # None = any type
    count: int = 1  # how many frames to drop
    after_ms: int = 0  # leave alone before this timestamp
    before_ms: Optional[int] = None  # leave alone after this timestamp
    fired: int = 0

    def hits(self, t_ms: int, mtype: int) -> bool:
        if self.fired >= self.count:
            return False
        if t_ms < self.after_ms:
            return False
        if self.before_ms is not None and t_ms > self.before_ms:
            return False
        if self.mtype is not None and int(mtype) != int(self.mtype):
            return False
        self.fired += 1
        return True

    @staticmethod
    def parse(spec: str) -> "DropRule":
        """Format: `mtype=0,count=1,after_ms=1000`."""
        kw: Dict[str, object] = {}
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            key, _, val = part.partition("=")
            key = key.strip()
            if key not in ("mtype", "count", "after_ms", "before_ms"):
                raise ValueError(f"unknown drop field: {key!r}")
            kw[key] = int(val)
        return DropRule(**kw)  # type: ignore[arg-type]


# ==========================================================================
# 5. Port
# ==========================================================================
class UdpPort(Platform):
    """One station's contact with the world. It never exceeds api I2.

    THE 250 B CEILING IS A SELF-IMPOSED DESIGN CONSTRAINT, NOT A PLATFORM
    LIMIT, and the two must not be confused. Measured on this platform: with
    `IP_PMTUDISC_DO` set, the largest datagram accepted is exactly `MTU - 28`
    and one byte more returns EMSGSIZE. Station MTU is 1500 (mininet-wifi never
    sets one, so stations inherit the mac80211 netdev default), which puts the
    real cliff at 1472 bytes; the 802.11 MSDU ceiling of 2304 never binds
    because the netdev MTU binds first.

    Against that, the protocol is tiny: the largest message actually emitted on
    the worked example is 17-21 bytes, every fixed message is at most 25, and a
    HELLO at the worst benchmark degree (36) is 85. A HELLO first touches 250 B
    at degree 118 and 1472 B at degree 729. So the headroom is roughly 60x at
    the worst density we run, and 250 NEVER BINDS.

    It is enforced anyway, and on purpose: it keeps the wire format portable to
    ESP-NOW, and bb-validate's ceiling-unreachable finding is stated against
    this constant. Exceeding it raises `PayloadTooLarge`. THERE IS NO
    TRUNCATION; a truncated frame is a silently wrong decision.
    """

    def __init__(
        self,
        amap: AddressMap,
        log: JsonlLog,
        *,
        rssi: Optional[RssiReader] = None,
        sock: Optional[socket.socket] = None,
        bind_device: Optional[str] = None,
        clock: Callable[[], float] = time.time,
        phase_of: Optional[Callable[[], int]] = None,
        drops: Optional[Sequence["DropRule"]] = None,
        epoch_ms: int = 0,
    ) -> None:
        self.amap = amap
        self.jlog = log
        self.rssi = rssi
        self._clock = clock
        #: THE CLOCK'S ZERO POINT. `now_ms` counts from here.
        #:
        #: WHY IT EXISTS. `Platform.now_ms` says "monotonic clock" but says
        #: NOTHING about the zero point; the simulator counts from 0, an ESP32
        #: counts from boot via `esp_timer_get_time`, and a wall clock counts
        #: from 1970. The difference looks irrelevant and is not: the node used
        #: to start with `stable_since_ms = 0` and opened the stability gate on
        #: `now - stable_since_ms >= T_stab`. Under a wall clock that difference
        #: is 1.7e12 ms on the first tick, the gate opens IMMEDIATELY, and every
        #: node FREEZES A WRONG KEY with `deg = 0` (measured with real
        #: processes: 10 nodes out of 10, followed by 10 epoch resets).
        #:
        #: STATUS. The real fix landed in `bootstrap.py` (`stable_since_ms`
        #: now starts unset and is established from the first observed clock,
        #: and `_gate` establishes the baseline for every path including
        #: overridden ones), so this field is NO LONGER REQUIRED FOR
        #: CORRECTNESS. Two reasons to keep it: it is the faithful imitation of
        #: a device clock counting from boot, and it does not tie the defence to
        #: a single layer. `test_mnwifi.py` exercises the two layers separately.
        #:
        #: Slot alignment is NOT disturbed: `epoch_ms` is chosen as a multiple
        #: of tau, so floor((t - epoch)/tau) = floor(t/tau) - epoch/tau.
        self.epoch_ms = int(epoch_ms)
        self._phase_of = phase_of or (lambda: 0)
        self.tx_calls = 0
        self.tx_bytes = 0
        self.max_payload_seen = 0
        self.rx_frames = 0
        self.unreachable = 0
        self.drops: List[DropRule] = list(drops or ())
        self.dropped_by_rule = 0
        self.sock = sock or self._open(amap, bind_device)

    # -- socket -----------------------------------------------------------
    @staticmethod
    def _open(amap: AddressMap, bind_device: Optional[str]) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)
        except OSError:
            pass
        if bind_device:
            try:
                s.setsockopt(
                    socket.SOL_SOCKET, SO_BINDTODEVICE, bind_device.encode() + b"\0"
                )
            except OSError:
                pass  # unprivileged: broadcast still takes the default route
        s.bind(amap.bind_addr())
        s.setblocking(False)
        return s

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def set_phase_source(self, fn: Callable[[], int]) -> None:
        """Read the node's `phase` attribute for per-phase accounting.

        This is the same measurement hook as `SimNet._phase_of`: the network
        layer READS the node's phase (api.NodeCore.phase is a plain class
        attribute) and GIVES the node nothing. The set of calls the node sees is
        unchanged.
        """
        self._phase_of = fn

    # -- Platform ---------------------------------------------------------
    @property
    def mac(self) -> int:
        """This station's own radio address. On a device that is
        `esp_wifi_get_mac`; on the emulator it is the interface MAC, which
        `topology` assigns via `mac_for_id`."""
        return self.amap.my_mac

    def now_ms(self) -> int:
        return int(self._clock() * 1000.0) - self.epoch_ms

    def send_broadcast(self, payload: bytes) -> None:
        data = self._guard(payload)
        if self._suppressed(data):
            # As if lost on the channel: tx counted, nobody receives, node not told.
            self._account(data, kind="bcast", dst=None, delivered=False)
            return
        for addr in self.amap.broadcast_targets():
            self._sendto(data, addr)
        self._account(data, kind="bcast", dst=None)

    def send_unicast(self, dst: int, payload: bytes) -> None:
        """`dst` is a MAC (48 bit), not a node id."""
        data = self._guard(payload)
        if self._suppressed(data):
            self._account(data, kind="ucast", dst=dst, delivered=False)
            return
        addr = self.amap.addr_of(dst)
        if addr is None:
            # I1: the node is not told. An unknown MAC and an out-of-range MAC
            # give the same outcome: the frame goes on the air, nobody hears it.
            self.unreachable += 1
            self._account(data, kind="ucast", dst=dst, delivered=False)
            self.log("unicast_unreachable", dst_mac=format_mac(dst))
            return
        if not self.amap.in_range(dst):
            self._account(data, kind="ucast", dst=dst, delivered=False)
            return
        self._sendto(data, addr)
        self._account(data, kind="ucast", dst=dst)

    def log(self, event: str, **fields: object) -> None:
        rec: Dict[str, object] = {
            "t_ms": self.now_ms(),
            "event": event,
            "mac": format_mac(self.mac),
        }
        rec.update(fields)
        self.jlog.write(rec)

    # -- send path --------------------------------------------------------
    @staticmethod
    def _guard(payload: bytes) -> bytes:
        data = bytes(payload)
        if len(data) > MAX_PAYLOAD:
            raise PayloadTooLarge(f"{len(data)} B > {MAX_PAYLOAD} B (I3)")
        return data

    def _suppressed(self, data: bytes) -> bool:
        if not self.drops:
            return False
        mtype = int(wire.peek_type(data)) if data else -1
        now = self.now_ms()
        for rule in self.drops:
            if rule.hits(now, mtype):
                self.dropped_by_rule += 1
                self.log("drop_rule", mtype=mtype, bytes=len(data), fired=rule.fired)
                return True
        return False

    def _sendto(self, data: bytes, addr: Addr) -> None:
        try:
            self.sock.sendto(data, addr)
        except OSError as exc:
            # The channel refused it (interface down, no route). Same meaning as
            # a loss: tx is counted, nobody receives. The node is not told.
            self.log("send_failed", err=str(exc), dst=f"{addr[0]}:{addr[1]}")

    def _account(
        self, data: bytes, *, kind: str, dst: Optional[int], delivered: bool = True
    ) -> None:
        mtype = int(wire.peek_type(data)) if data else -1
        self.tx_calls += 1
        self.tx_bytes += len(data)
        self.max_payload_seen = max(self.max_payload_seen, len(data))
        self.log(
            "tx",
            kind=kind,
            mtype=mtype,
            bytes=len(data),
            phase=int(self._phase_of()),
            dst=None if dst is None else format_mac(dst),
            delivered=bool(delivered),
        )

    # -- receive path -----------------------------------------------------
    def receive(self, *, limit: int = 4096) -> List[RxFrame]:
        """Drain everything waiting on the socket. THE NODE NEVER CALLS THIS;
        `node_main` calls it and hands the frames to `on_frame`, the way
        `SimNet.deliver` does."""
        out: List[RxFrame] = []
        now = self.now_ms()
        if self.rssi is not None:
            self.rssi.refresh(now)
        for _ in range(limit):
            try:
                data, anc, _flags, addr = self.sock.recvmsg(2048, 256)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            if not data:
                continue
            src = self.amap.mac_of((addr[0], int(addr[1])))
            if src is None or src == self.mac:
                continue  # my own broadcast, or a stranger
            stamp = self._stamp(anc)
            t_recv = self.now_ms() if stamp is None else (stamp - self.epoch_ms)
            rssi = self.rssi.of(src) if self.rssi is not None else None
            self.rx_frames += 1
            self.log(
                "rx",
                src=format_mac(src),
                mtype=int(wire.peek_type(data)),
                bytes=len(data),
                rssi=rssi,
                t_recv_ms=t_recv,
            )
            out.append(
                RxFrame(src_mac=src, rssi=rssi, payload=bytes(data), t_recv_ms=t_recv)
            )
        return out

    @staticmethod
    def _stamp(ancdata: Sequence[Tuple[int, int, bytes]]) -> Optional[int]:
        """Kernel arrival time (ms). Slot fidelity rests on this value."""
        for level, typ, blob in ancdata:
            if (
                level == socket.SOL_SOCKET
                and typ == SCM_TIMESTAMPNS
                and len(blob) >= 16
            ):
                sec, nsec = struct.unpack("qq", blob[:16])
                return int(sec * 1000 + nsec // 1_000_000)
        return None


# ==========================================================================
# 6. Helper: a port pair over loopback (unprivileged testing)
# ==========================================================================
def loopback_peers(nids: Sequence[int], *, base_port: int = 47101) -> Dict[int, Peer]:
    """A separate port per node on 127.0.0.1. FOR TESTS ONLY."""
    from ccvc.bb.bbcvc import mac_for_id

    out: Dict[int, Peer] = {}
    for i, nid in enumerate(sorted(int(n) for n in nids)):
        out[nid] = Peer(
            nid=nid,
            station=f"sta{i + 1}",
            mac=mac_for_id(nid),
            ip="127.0.0.1",
            udp_port=base_port + i,
        )
    return out
