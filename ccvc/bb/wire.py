#!/usr/bin/env python3
"""BB-CVC serialization layer (brief 3.3, 5; api.py I3).

PRINCIPLES
  * Deterministic: the same message always produces the same byte string.
  * NO TRUNCATION. Exceeding 250 B raises `PayloadTooLarge` (I3).
  * Field widths are fixed by brief 3.3: id 2 B, key 4 B, role 1 B,
    phase 1 B, seq 2 B. A 1 B type header is added on top; the type sits at
    `payload[0]` so the network layer can read it without decoding the body.

SIZES (measured; `sizes()` reproduces them)
  HELLO   13 B (mis_nbrs empty) .. 23 B (the five MIS neighbours of brief G8)
  LINK / LINK_ACK              5 B
  TOKEN / TOKEN_DONE           7 B  (seq + init)
  JOIN / JOIN_ACK              6 B
  HANDOVER/ACK/NACK, PUSH/ACK/NACK  10 B
  TREE                        10 B
  STABLE                      25 B
  FINISH                       8 B
None of these depend on density; the only variable-length field is HELLO's
`mis_nbrs` array, and G8 caps that at five.

THE 250 B CEILING IS SELF-IMPOSED AND IT NEVER BINDS.
  250 B is the ESP-NOW limit. The target platform is mininet-wifi, where the
  real ceiling is the UDP payload under a 1500 B MTU, i.e. 1472 B. We keep 250
  deliberately, because brief section 5's message-size argument is built on it
  and because a design that also fits constrained hardware is a feature. It is
  a declared choice, not a necessity.

  It also never binds. The largest message any arm emits is 31 B (HELLO with
  the ANNEAL tail and five mis_nbrs); at the sweep's mis_nbrs_max=32 a HELLO is
  77 B. A full neighbour list would fit 118 ids under 250 and 729 under 1472,
  against a measured maximum degree of 17 in the benchmark. The neighbour table
  cap fills long before the payload ceiling is reached.

KEY REPRESENTATION
  The key is a signed 16.16 fixed-point INTEGER (api.to_fp). A key that has not
  been frozen yet is `None` and travels as `KEY_NONE` (INT32_MIN); that value
  can never be a legitimate key, because keys are produced from w/(deg+1) >= 0.

  Fixed point here is WIRE-ONLY, and the justification is determinism rather
  than the absence of an FPU: the wire format and the key are 16.16, node
  decision arithmetic is integer, but Anneal-Local's internals (lambda,
  temperatures, every Metropolis acceptance) are IEEE double. Claiming "fixed
  point everywhere per brief 3.6" would be false as this code stands.

  A floating-point key is REJECTED, never coerced. The remaining fields are
  already protected by `struct` ('H' and 'B' refuse floats); the only places a
  silent coercion was possible were the explicit `int()` calls, and those now
  go through `_exact_int`.
"""
from __future__ import annotations

import os
import struct
import math
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Union

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb.api import MAX_PAYLOAD, MsgType, PayloadTooLarge, Role  # noqa: E402

# The "absent" value for the key field. Real keys derive from w/(deg+1) >= 0.
KEY_NONE = -(2 ** 31)

# brief G8: the number of MIS neighbours carried in a HELLO is fixed and small.
# The wire does NOT enforce this; the wire enforces only the 250 B ceiling.
MIS_NBRS_SOFT_MAX = 5

# ANNEAL block (brief section 6.5 / .tex section 13): an OPTIONAL 8-byte tail
# appended to a HELLO. A bare HELLO stays 13 B, so BB-CVC and bootstrap are
# untouched; the block is attached only on Anneal-Local runs.
#   flags(1): bit0 = x (in the cover), bits 1..7 = cooling step index j
#             (T = T0*alpha^j; j travels rather than T itself, because j is
#              exact and the receiver rebuilds T from its own parameters)
#   ell(2)  : fractional load, 8.8 fixed point (brief section 3.6)
#   label(2), label_ctr(1) : Loop C component label + staleness counter
#   token(2): Loop A local-exclusion token
_ANNEAL = struct.Struct("<BHHBH")
ANNEAL_BYTES = _ANNEAL.size          # 8
COOL_MAX = 0x7F                      # largest j that fits the 7 bits of flags

# header: type(1) + src(2)
_HDR = struct.Struct("<BH")
# HELLO body: key(4, signed 16.16) + deg(1) + role(1) + phase(1)
#             + load(1) + epoch(1) + mis_nbrs count(1). All unsigned.
_HELLO_BODY = struct.Struct("<iBBBBBB")
_SEQ = struct.Struct("<H")
_U8 = struct.Struct("<B")
_EDGE = struct.Struct("<HHB")            # u, v, ttl
_TOKEN_BODY = struct.Struct("<HH")       # seq, init
_TREE_BODY = struct.Struct("<HHHB")      # seq, root, parent, depth
#: seq, root, subtree, tx, rx, bytes_tx, weight_fp.
#: `weight_fp` is SIGNED 64-BIT, not 32. It carries an AGGREGATE: the 16.16
#: fixed-point weight of a whole subtree, not of one node. At the root of a
#: 100-node tree with node weights around 1000 that is 100 * 1000 * 65536, about
#: 6.5e9, against an int32 ceiling of 2.1e9.
#: MEASURED: MIS-Connector-TreeAgg raised "'i' format requires -2147483648 <= number <=
#: 2147483647" on three of twelve n=100 instances and produced no verdict at
#: all. It fitted at n <= 50, which is why the field survived this long.
#: The cost is four bytes on STABLE, and it falls only on the tree arms.
_STABLE_BODY = struct.Struct("<HHHIIIq")
_FINISH_BODY = struct.Struct("<HHB")     # seq, root, epoch
_GREEDY_BODY = struct.Struct("<IddHBBBB")  # seq, weight, denominator, degree, color, epoch, rule, phase

_HELLO_FIXED = _HDR.size + _HELLO_BODY.size   # 3 + 10 = 13


# --------------------------------------------------------------------------
# message bodies
# --------------------------------------------------------------------------
@dataclass
class Hello:
    """Phase 0 periodic broadcast (brief 4/Phase 0). Carries NO full neighbour list."""

    src: int
    key: Union[int, None]
    deg: int
    role: Role
    phase: int
    load: int
    epoch: int = 0
    mis_nbrs: Tuple[int, ...] = ()
    anneal: Optional["Anneal"] = None    # populated only on Anneal-Local runs

    mtype: MsgType = MsgType.HELLO


@dataclass
class Anneal:
    """The ANNEAL tail of a HELLO. `ell` is an 8.8 fixed-point INTEGER."""

    x: bool
    ell_fp: int
    label: int
    label_ctr: int
    token: int
    cool: int = 0            # cooling step j, T = T0 * alpha**j


@dataclass
class GreedyState:
    """A 29-byte local score advertisement. Weights retain IEEE binary64 precision.

    This Linux/Mininet-WiFi message is separate from HELLO and its fixed-point
    key. It contains no adjacency list or other nodes' candidate records.
    Colors: 0=RED, 1=WHITE, 2=GRAY, 3=BLACK. Rules: 0=GCCVC, 1=GRCCVC, 2=GWCCVC.
    """
    src: int
    seq: int
    weight: float
    denominator: float
    degree: int
    color: int
    epoch: int
    rule: int
    phase: int
    mtype: MsgType = MsgType.GREEDY_STATE


@dataclass
class Ctrl:
    """LINK and LINK_ACK: bidirectionality verification (brief 3.5/3)."""

    mtype: MsgType
    src: int
    seq: int


@dataclass
class Token:
    """TOKEN and TOKEN_DONE: the DFS-Spanning-Backbone token walk (brief section 6).

    `init` is the id of the node that STARTED the walk, and it MUST be on the
    wire. DFS-Spanning-Backbone has no elected root: every local minimum starts its own walk, and
    when two walks meet the one with the smaller `init` absorbs the other. A
    receiver cannot infer which walk an incoming token belongs to from anything
    it already holds, so the field travels.

    NOT FOLDED INTO `Ctrl`. Overloading `seq` would pollute a field the way
    reusing a type pollutes a counter; every type meaning exactly one thing is
    what keeps the `by_type_tx` identities standing, and the same discipline
    applies to fields. Two bytes are cheaper than an ambiguous field, and an
    ambiguous field cannot be validated because it no longer has a wrong value.

    There is NO reserved value for `init`: 0 encodes and round-trips like any
    other. Ids come from hash16 so zero does not arise in practice, but the
    format does not DEPEND on that.
    """

    mtype: MsgType
    src: int
    seq: int
    init: int


@dataclass
class Join:
    """JOIN and JOIN_ACK. `code` is the reason on JOIN, the accept flag on JOIN_ACK."""

    mtype: MsgType
    src: int
    seq: int
    code: int = 0


@dataclass
class EdgeMsg:
    """The six edge-carrying types: HANDOVER/ACK/NACK and PUSH/ACK/NACK.

    `ttl` is meaningful only on PUSH (brief Phase 4, D=3) but always travels,
    so that the layout stays fixed.
    """

    mtype: MsgType
    src: int
    seq: int
    u: int
    v: int
    ttl: int = 0


@dataclass
class Tree:
    """Phase 5b backbone tree construction."""

    src: int
    seq: int
    root: int
    parent: int
    depth: int

    mtype: MsgType = MsgType.TREE


@dataclass
class Stable:
    """Phase 5b convergecast: the subtree's counter totals."""

    src: int
    seq: int
    root: int
    subtree: int
    tx: int
    rx: int
    bytes_tx: int
    weight_fp: int

    mtype: MsgType = MsgType.STABLE


@dataclass
class Finish:
    """Phase 5b completion, flooded from the root."""

    src: int
    seq: int
    root: int
    epoch: int = 0

    mtype: MsgType = MsgType.FINISH


@dataclass
class Ghs:
    """The seven GHS messages of GHS-MST-Backbone's distributed MST (section 6).

    One body serves all seven so that `by_type_tx` still attributes each
    protocol step separately: the TYPE carries the step, the body carries the
    operands. Overloading one type with a mode field would have collapsed seven
    counters into one, which is the same contamination that kept the DFS-Spanning-Backbone token
    out of `Ctrl`.

    `level` and `frag` are the fragment's level and identity, which must travel
    because a node cannot infer another fragment's state from anything it
    holds. `wfp` is a 16.16 fixed-point edge weight: the node compares weights,
    never tests one against a threshold, so the comparison is scale-free
    (see the scale-invariance note in `bbcvc.py`).
    """

    mtype: MsgType
    src: int
    seq: int
    level: int = 0
    frag: int = 0
    wfp: int = 0


Message = Union[Hello, GreedyState, Ctrl, Token, Join, EdgeMsg, Tree, Stable, Finish, Ghs]

#: The `Ctrl` body (type, src, seq = 5 B): types with NO extra field.
_CTRL_TYPES = (MsgType.LINK, MsgType.LINK_ACK)
#: The DFS-Spanning-Backbone token walk. It rode on `Ctrl` at first and was SPLIT OUT when the
#: `init` field arrived. Keeping it folded in would have meant overloading
#: `seq`, which pollutes a field the way reusing a type pollutes a counter.
#: DFS_DONE joins them: it also carries `init`, because a completion flood
#: has to say WHICH walk completed -- a node may have been preempted since.
_TOKEN_TYPES = (MsgType.TOKEN, MsgType.TOKEN_DONE, MsgType.DFS_DONE)
#: BB_MIS rides the Join body: it needs one small code (claim / withdraw)
#: and nothing else, which is exactly what that body already carries.
_JOIN_TYPES = (MsgType.JOIN, MsgType.JOIN_ACK, MsgType.BB_MIS)
_EDGE_TYPES = (MsgType.HANDOVER, MsgType.HANDOVER_ACK, MsgType.HANDOVER_NACK,
               MsgType.PUSH, MsgType.PUSH_ACK, MsgType.PUSH_NACK)
_GHS_TYPES = (MsgType.GHS_CONNECT, MsgType.GHS_INITIATE, MsgType.GHS_TEST,
              MsgType.GHS_ACCEPT, MsgType.GHS_REJECT, MsgType.GHS_REPORT,
              MsgType.GHS_CHANGE_ROOT)
#: seq(2) + level(2) + frag(4) + wfp(4) = 12 B of body, 15 B on the wire.
#:
#: `frag` IS FOUR BYTES ON PURPOSE. GHS identifies a fragment by the weight of
#: the edge that created it, and here that weight is 16.16 fixed point, which
#: does not fit in two. A 16-bit field truncated it, every fragment collided on
#: identity 0, every TEST compared equal and was REJECTED, no node ever found an
#: outgoing edge, and the fragments halted without ever merging -- a spanning
#: tree that did not span. Measured, not hypothesised.
_GHS_BODY = struct.Struct("<HHii")


# --------------------------------------------------------------------------
# kodlama
# --------------------------------------------------------------------------
def _guard(nbytes: int, mtype: int) -> None:
    if nbytes > MAX_PAYLOAD:
        raise PayloadTooLarge(f"{nbytes} B > {MAX_PAYLOAD} B (tip {int(mtype)})")


def _exact_int(value, field: str) -> int:
    """REJECT a non-integer, never COERCE it (brief 3.6 fixed-point discipline).

    `int(1.67)` silently yields 1. Because the key is 16.16 fixed point that is
    not a rounding but a COLLAPSE: the correct value is 109445, the wire gets 1,
    and it reads back as 0.00002. Every MIS ordering decision in Phase 1 looks
    at this value, so a silent coercion turns the whole ordering into garbage.
    An exception that is raised always beats a collapse that is not.

    `bool` is rejected too: it subclasses int but it is neither a key nor a role.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"{field} must be an integer, got {type(value).__name__} ({value!r}). "
            f"Convert a floating-point key to fixed point with api.to_fp().")
    return int(value)


def _check_type(got: MsgType, allowed: Tuple[MsgType, ...]) -> None:
    if got not in allowed:
        names = "/".join(t.name for t in allowed)
        raise ValueError(f"type {got!r} does not fit this body; expected {names}")


def encode(msg: Message) -> bytes:
    """Encode a message to bytes. Over 250 B raises PayloadTooLarge; no truncation."""
    if isinstance(msg, Hello):
        return _encode_hello(msg)
    if isinstance(msg, GreedyState):
        if (not math.isfinite(msg.weight) or msg.weight <= 0
                or not math.isfinite(msg.denominator) or msg.denominator < 0
                or msg.color not in (0, 1, 2, 3) or msg.rule not in (0, 1, 2)):
            raise ValueError("Invalid greedy score advertisement")
        out = (_HDR.pack(int(MsgType.GREEDY_STATE), msg.src)
               + _GREEDY_BODY.pack(msg.seq, msg.weight, msg.denominator,
                                   msg.degree, msg.color, msg.epoch, msg.rule, msg.phase))
    elif isinstance(msg, Ctrl):
        _check_type(msg.mtype, _CTRL_TYPES)
        out = _HDR.pack(int(msg.mtype), msg.src) + _SEQ.pack(msg.seq)
    elif isinstance(msg, Token):
        _check_type(msg.mtype, _TOKEN_TYPES)
        out = (_HDR.pack(int(msg.mtype), msg.src)
               + _TOKEN_BODY.pack(msg.seq, msg.init))
    elif isinstance(msg, Ghs):
        _check_type(msg.mtype, _GHS_TYPES)
        out = (_HDR.pack(int(msg.mtype), msg.src)
               + _GHS_BODY.pack(msg.seq, msg.level,
                                _exact_int(msg.frag, "Ghs.frag"),
                                _exact_int(msg.wfp, "Ghs.wfp")))
    elif isinstance(msg, Join):
        _check_type(msg.mtype, _JOIN_TYPES)
        out = _HDR.pack(int(msg.mtype), msg.src) + _SEQ.pack(msg.seq) + _U8.pack(msg.code)
    elif isinstance(msg, EdgeMsg):
        _check_type(msg.mtype, _EDGE_TYPES)
        out = (_HDR.pack(int(msg.mtype), msg.src) + _SEQ.pack(msg.seq)
               + _EDGE.pack(msg.u, msg.v, msg.ttl))
    elif isinstance(msg, Tree):
        out = (_HDR.pack(int(MsgType.TREE), msg.src)
               + _TREE_BODY.pack(msg.seq, msg.root, msg.parent, msg.depth))
    elif isinstance(msg, Stable):
        out = (_HDR.pack(int(MsgType.STABLE), msg.src)
               + _STABLE_BODY.pack(msg.seq, msg.root, msg.subtree,
                                   msg.tx, msg.rx, msg.bytes_tx, msg.weight_fp))
    elif isinstance(msg, Finish):
        out = (_HDR.pack(int(MsgType.FINISH), msg.src)
               + _FINISH_BODY.pack(msg.seq, msg.root, msg.epoch))
    else:
        raise TypeError(f"unknown message body: {type(msg).__name__}")
    _guard(len(out), msg.mtype)
    return out


def _encode_hello(msg: Hello) -> bytes:
    n = len(msg.mis_nbrs)
    # Size is computed FIRST: even when n does not fit a single byte the error
    # must be PayloadTooLarge rather than struct.error. Nothing is ever truncated.
    tail = ANNEAL_BYTES if msg.anneal is not None else 0
    _guard(_HELLO_FIXED + 2 * n + tail, MsgType.HELLO)
    if msg.key is None:
        key = KEY_NONE
    else:
        key = _exact_int(msg.key, "key")
        if key == KEY_NONE:
            raise ValueError(
                f"key cannot be the sentinel value ({KEY_NONE}); it would be "
                f"indistinguishable from None on the wire")
        if not (-(2 ** 31) < key < 2 ** 31):
            raise ValueError(f"key does not fit the signed 32-bit range: {key}")
    role = _exact_int(msg.role, "role")
    out = (_HDR.pack(int(MsgType.HELLO), msg.src)
           + _HELLO_BODY.pack(key, msg.deg, role, msg.phase,
                              msg.load, msg.epoch, n)
           + struct.pack(f"<{n}H", *msg.mis_nbrs))
    if msg.anneal is not None:
        a = msg.anneal
        cool = _exact_int(a.cool, "anneal.cool")
        if not 0 <= cool <= COOL_MAX:
            raise ValueError(f"anneal.cool does not fit 7 bits: {cool}")
        ell = _exact_int(a.ell_fp, "anneal.ell_fp")
        if not 0 <= ell <= 0xFFFF:
            raise ValueError(f"anneal.ell_fp is outside the 8.8 range: {ell}")
        flags = (1 if a.x else 0) | (cool << 1)
        out += _ANNEAL.pack(flags, ell, _exact_int(a.label, "anneal.label"),
                            _exact_int(a.label_ctr, "anneal.label_ctr"),
                            _exact_int(a.token, "anneal.token"))
    _guard(len(out), MsgType.HELLO)
    return out


# --------------------------------------------------------------------------
# decoding
# --------------------------------------------------------------------------
def peek_type(payload: bytes) -> MsgType:
    """Read the type without decoding the payload. Accounting uses this."""
    if not payload:
        raise ValueError("empty payload")
    return MsgType(payload[0])


def peek_src(payload: bytes) -> int:
    if len(payload) < _HDR.size:
        raise ValueError("payload shorter than the header")
    return _HDR.unpack_from(payload, 0)[1]


def decode(payload: bytes) -> Message:
    """Decode bytes to a message. Round-trips exactly with encode."""
    mtype = peek_type(payload)
    _, src = _HDR.unpack_from(payload, 0)
    off = _HDR.size

    if mtype is MsgType.GREEDY_STATE:
        if len(payload) != off + _GREEDY_BODY.size:
            raise ValueError("GREEDY_STATE length mismatch")
        msg = GreedyState(src, *_GREEDY_BODY.unpack_from(payload, off))
        encode(msg)  # Reject invalid numeric values and unknown rule/color codes.
        return msg

    if mtype is MsgType.HELLO:
        key, deg, role, phase, load, epoch, n = _HELLO_BODY.unpack_from(payload, off)
        off += _HELLO_BODY.size
        need = off + 2 * n
        extra = len(payload) - need
        if extra not in (0, ANNEAL_BYTES):
            raise ValueError(
                f"HELLO length mismatch: {len(payload)}, expected {need} "
                f"or {need + ANNEAL_BYTES} (with the ANNEAL tail)")
        mis = struct.unpack_from(f"<{n}H", payload, off)
        ann = None
        if extra:
            flags, ell, label, lctr, token = _ANNEAL.unpack_from(payload, need)
            ann = Anneal(x=bool(flags & 1), ell_fp=ell, label=label,
                         label_ctr=lctr, token=token, cool=flags >> 1)
        return Hello(src=src, key=None if key == KEY_NONE else key, deg=deg,
                     role=Role(role), phase=phase, load=load, epoch=epoch,
                     mis_nbrs=tuple(mis), anneal=ann)

    if mtype in _CTRL_TYPES:
        (seq,) = _SEQ.unpack_from(payload, off)
        return Ctrl(mtype=mtype, src=src, seq=seq)

    if mtype in _TOKEN_TYPES:
        seq, init = _TOKEN_BODY.unpack_from(payload, off)
        return Token(mtype=mtype, src=src, seq=seq, init=init)

    if mtype in _GHS_TYPES:
        seq, level, frag, wfp = _GHS_BODY.unpack_from(payload, off)
        return Ghs(mtype=mtype, src=src, seq=seq, level=level, frag=frag, wfp=wfp)

    if mtype in _JOIN_TYPES:
        (seq,) = _SEQ.unpack_from(payload, off)
        (code,) = _U8.unpack_from(payload, off + _SEQ.size)
        return Join(mtype=mtype, src=src, seq=seq, code=code)

    if mtype in _EDGE_TYPES:
        (seq,) = _SEQ.unpack_from(payload, off)
        u, v, ttl = _EDGE.unpack_from(payload, off + _SEQ.size)
        return EdgeMsg(mtype=mtype, src=src, seq=seq, u=u, v=v, ttl=ttl)

    if mtype is MsgType.TREE:
        seq, root, parent, depth = _TREE_BODY.unpack_from(payload, off)
        return Tree(src=src, seq=seq, root=root, parent=parent, depth=depth)

    if mtype is MsgType.STABLE:
        seq, root, sub, tx, rx, bt, wfp = _STABLE_BODY.unpack_from(payload, off)
        return Stable(src=src, seq=seq, root=root, subtree=sub,
                      tx=tx, rx=rx, bytes_tx=bt, weight_fp=wfp)

    if mtype is MsgType.FINISH:
        seq, root, epoch = _FINISH_BODY.unpack_from(payload, off)
        return Finish(src=src, seq=seq, root=root, epoch=epoch)

    raise ValueError(f"type has no decoder: {mtype!r}")


# --------------------------------------------------------------------------
# measurement helpers
# --------------------------------------------------------------------------
def hello_size(n_mis: int, anneal: bool = False) -> int:
    """Byte size of a HELLO carrying n_mis MIS neighbours."""
    return _HELLO_FIXED + 2 * n_mis + (ANNEAL_BYTES if anneal else 0)


def sizes() -> Dict[str, int]:
    """Representative byte size per type. Used in the report and in tests."""
    return {
        "HELLO_min": hello_size(0),
        "HELLO_max": hello_size(MIS_NBRS_SOFT_MAX),
        "HELLO_anneal_min": hello_size(0, anneal=True),
        "HELLO_anneal_max": hello_size(MIS_NBRS_SOFT_MAX, anneal=True),
        "LINK": len(encode(Ctrl(MsgType.LINK, 1, 0))),
        "LINK_ACK": len(encode(Ctrl(MsgType.LINK_ACK, 1, 0))),
        "JOIN": len(encode(Join(MsgType.JOIN, 1, 0, 0))),
        "JOIN_ACK": len(encode(Join(MsgType.JOIN_ACK, 1, 0, 0))),
        "HANDOVER": len(encode(EdgeMsg(MsgType.HANDOVER, 1, 0, 1, 2))),
        "PUSH": len(encode(EdgeMsg(MsgType.PUSH, 1, 0, 1, 2, 3))),
        "TREE": len(encode(Tree(1, 0, 1, 1, 0))),
        "STABLE": len(encode(Stable(1, 0, 1, 1, 0, 0, 0, 0))),
        "FINISH": len(encode(Finish(1, 0, 1))),
        "TOKEN": len(encode(Token(MsgType.TOKEN, 1, 0, 1))),
        "TOKEN_DONE": len(encode(Token(MsgType.TOKEN_DONE, 1, 0, 1))),
        "GREEDY_STATE": len(encode(GreedyState(1, 0, 1.0, 2.0, 2, 1, 0, 0, 3))),
        "DFS_DONE": len(encode(Token(MsgType.DFS_DONE, 1, 0, 1))),
        "BB_MIS": len(encode(Join(MsgType.BB_MIS, 1, 0, 1))),
        "GHS_CONNECT": len(encode(Ghs(MsgType.GHS_CONNECT, 1, 0, 0, 1, 0))),
        "GHS_INITIATE": len(encode(Ghs(MsgType.GHS_INITIATE, 1, 0, 0, 1, 0))),
        "GHS_TEST": len(encode(Ghs(MsgType.GHS_TEST, 1, 0, 0, 1, 0))),
        "GHS_ACCEPT": len(encode(Ghs(MsgType.GHS_ACCEPT, 1, 0, 0, 1, 0))),
        "GHS_REJECT": len(encode(Ghs(MsgType.GHS_REJECT, 1, 0, 0, 1, 0))),
        "GHS_REPORT": len(encode(Ghs(MsgType.GHS_REPORT, 1, 0, 0, 1, 7))),
        "GHS_CHANGE_ROOT": len(encode(Ghs(MsgType.GHS_CHANGE_ROOT, 1, 0, 0, 1, 0))),
    }


if __name__ == "__main__":  # pragma: no cover
    for k, v in sizes().items():
        print(f"{k:12s} {v:3d} B")
