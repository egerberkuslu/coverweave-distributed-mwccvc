#!/usr/bin/env python3
"""wire.py tests: exact round-trip, sizes, the 250 B ceiling (brief 3.3, api I3).

Run (from the repo root):
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_wire.py -q
"""
from __future__ import annotations

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ccvc.bb import wire  # noqa: E402
from ccvc.bb.api import MAX_PAYLOAD, MsgType, PayloadTooLarge, Role, key_of  # noqa: E402

# Brief 3.3 says HELLO is "about 22 B". This is the real upper bound measured
# with the type byte included; the test keeps it as the documented limit.
HELLO_MAX_DOCUMENTED = 24


def _one_of_each():
    """One example per MsgType. This is what measures round-trip coverage."""
    return {
        MsgType.HELLO: wire.Hello(src=4113, key=key_of(5.0, 2, 1)[0], deg=7,
                                  role=Role.CONNECTOR, phase=3, load=2, epoch=9,
                                  mis_nbrs=(1, 2, 300, 40000, 65535)),
        MsgType.LINK: wire.Ctrl(MsgType.LINK, 7, 513),
        MsgType.LINK_ACK: wire.Ctrl(MsgType.LINK_ACK, 8, 514),
        MsgType.JOIN: wire.Join(MsgType.JOIN, 9, 5, code=2),
        MsgType.JOIN_ACK: wire.Join(MsgType.JOIN_ACK, 10, 5, code=1),
        MsgType.HANDOVER: wire.EdgeMsg(MsgType.HANDOVER, 11, 6, 3, 4),
        MsgType.HANDOVER_ACK: wire.EdgeMsg(MsgType.HANDOVER_ACK, 12, 6, 3, 4),
        MsgType.HANDOVER_NACK: wire.EdgeMsg(MsgType.HANDOVER_NACK, 13, 6, 3, 4),
        MsgType.PUSH: wire.EdgeMsg(MsgType.PUSH, 14, 7, 5, 6, ttl=3),
        MsgType.PUSH_ACK: wire.EdgeMsg(MsgType.PUSH_ACK, 15, 7, 5, 6),
        MsgType.PUSH_NACK: wire.EdgeMsg(MsgType.PUSH_NACK, 16, 7, 5, 6),
        MsgType.TREE: wire.Tree(src=17, seq=8, root=1, parent=2, depth=4),
        MsgType.STABLE: wire.Stable(src=18, seq=9, root=1, subtree=6,
                                    tx=1234, rx=5678, bytes_tx=98765,
                                    weight_fp=-4242),
        MsgType.FINISH: wire.Finish(src=19, seq=10, root=1, epoch=2),
        MsgType.TOKEN: wire.Token(MsgType.TOKEN, 20, 515, 9),
        MsgType.TOKEN_DONE: wire.Token(MsgType.TOKEN_DONE, 21, 516, 9),
        MsgType.GREEDY_STATE: wire.GreedyState(22, 517, 29.278536798674715,
                                            71.0, 2, 0, 1, 1, 3),
        MsgType.DFS_DONE: wire.Token(MsgType.DFS_DONE, 23, 517, 9),
        MsgType.BB_MIS: wire.Join(MsgType.BB_MIS, 24, 518, code=1),
        MsgType.GHS_CONNECT: wire.Ghs(MsgType.GHS_CONNECT, 25, 519, 0, 7, 0),
        MsgType.GHS_INITIATE: wire.Ghs(MsgType.GHS_INITIATE, 26, 520, 2, 7, 0),
        MsgType.GHS_TEST: wire.Ghs(MsgType.GHS_TEST, 27, 521, 2, 7, 0),
        MsgType.GHS_ACCEPT: wire.Ghs(MsgType.GHS_ACCEPT, 28, 522, 0, 0, 0),
        MsgType.GHS_REJECT: wire.Ghs(MsgType.GHS_REJECT, 29, 523, 0, 0, 0),
        # negative wfp exercises the signed 16.16 field
        MsgType.GHS_REPORT: wire.Ghs(MsgType.GHS_REPORT, 30, 524, 2, 7, -4242,
                                     cert=(1234, 5678, 99)),
        MsgType.GHS_CHANGE_ROOT: wire.Ghs(MsgType.GHS_CHANGE_ROOT, 31, 525, 2, 7, 0),
        # R1 repair F17: the certificate wave rides on the edge body.
        MsgType.CERT: wire.EdgeMsg(MsgType.CERT, 32, 17, 0, 0, epoch=3),
        MsgType.CERT_ACK: wire.EdgeMsg(MsgType.CERT_ACK, 33, 17, 300, 800, epoch=3),
    }


def test_every_msgtype_has_a_codec():
    """No MsgType may be left without a codec."""
    covered = set(_one_of_each())
    assert covered == set(MsgType), f"missing codec: {set(MsgType) - covered}"


@pytest.mark.parametrize("mtype", list(MsgType))
def test_round_trip_is_exact(mtype):
    msg = _one_of_each()[mtype]
    raw = wire.encode(msg)
    back = wire.decode(raw)
    assert back == msg
    # re-encoding must give the same bytes: a deterministic format
    assert wire.encode(back) == raw
    # the type must be readable without decoding (accounting relies on it)
    assert wire.peek_type(raw) is mtype
    assert wire.peek_src(raw) == msg.src


def test_hello_key_none_round_trips():
    """Before the key is frozen it is None, and it must come back as None."""
    h = wire.Hello(src=1, key=None, deg=0, role=Role.OUT, phase=0, load=0)
    back = wire.decode(wire.encode(h))
    assert back.key is None
    assert back == h


def test_hello_key_zero_is_not_none():
    """w=0 produces a real key; it must not be confused with the None sentinel."""
    h = wire.Hello(src=1, key=0, deg=3, role=Role.OUT, phase=1, load=0)
    assert wire.decode(wire.encode(h)).key == 0


def test_hello_actual_size():
    """Brief 3.3: HELLO is about 22 B and INDEPENDENT OF DENSITY.

    Measured: 13 B (mis_nbrs empty), 23 B (the five MIS neighbours of G8).
    """
    empty = wire.encode(wire.Hello(src=1, key=100, deg=40, role=Role.MIS,
                                   phase=1, load=0))
    full = wire.encode(wire.Hello(src=1, key=100, deg=40, role=Role.MIS,
                                  phase=1, load=0, mis_nbrs=(1, 2, 3, 4, 5)))
    assert len(empty) == 13
    assert len(full) == 23
    assert len(full) <= HELLO_MAX_DOCUMENTED
    assert wire.hello_size(0) == 13 and wire.hello_size(5) == 23


def test_hello_size_independent_of_degree():
    """The size must NOT CHANGE as deg goes from 1 to 200 (brief 5: no full list)."""
    sizes = {len(wire.encode(wire.Hello(src=1, key=7, deg=d, role=Role.OUT,
                                        phase=0, load=0, mis_nbrs=(2, 3))))
             for d in (0, 1, 8, 64, 200, 255)}
    assert sizes == {wire.hello_size(2)} == {17}


def test_all_types_fit_in_250_bytes():
    for mtype, msg in _one_of_each().items():
        assert len(wire.encode(msg)) <= MAX_PAYLOAD, mtype


def test_sizes_table():
    s = wire.sizes()
    assert s == {"HELLO_min": 13, "HELLO_max": 23,
                 "HELLO_anneal_min": 21, "HELLO_anneal_max": 31,
                 "LINK": 5, "LINK_ACK": 5,
                 # R1 repair F3: JOIN, JOIN_ACK and the edge types carry the
                 # sender's epoch byte (6 -> 7 and 10 -> 11); BB_MIS does not.
                 "JOIN": 7, "JOIN_ACK": 7, "HANDOVER": 12, "PUSH": 12,
                 "TREE": 10, "STABLE": 29, "FINISH": 8,
                 "TOKEN": 7, "TOKEN_DONE": 7, "GREEDY_STATE": 29,
                 # DFS-Spanning-Backbone distributed control. DFS_DONE shares the Token body
                 # because it also carries `init`; BB_MIS shares Join because a
                 # claim needs one code byte and nothing more.
                 "DFS_DONE": 7, "BB_MIS": 6,
                 # GHS-MST-Backbone. One 13 B body for all seven steps, so each step
                 # keeps its own `by_type_tx` counter.
                 "GHS_CONNECT": 15, "GHS_INITIATE": 15, "GHS_TEST": 15,
                 # R1 repair F12b: GHS_REPORT carries the certificate sums
                 # (min(deg, k), deg, node count; 10 B), so 15 -> 25.
                 "GHS_ACCEPT": 15, "GHS_REJECT": 15, "GHS_REPORT": 25,
                 "GHS_CHANGE_ROOT": 15}


def test_oversize_hello_raises_not_truncates():
    """I3: exceeding 250 B is an ERROR. Nothing is ever truncated."""
    n = (MAX_PAYLOAD - wire.hello_size(0)) // 2 + 1   # first length that overflows
    big = wire.Hello(src=1, key=1, deg=n, role=Role.OUT, phase=1, load=0,
                     mis_nbrs=tuple(range(n)))
    assert wire.hello_size(n) > MAX_PAYLOAD
    with pytest.raises(PayloadTooLarge):
        wire.encode(big)
    # just under the limit must pass: the cut-off is exactly here
    ok = wire.Hello(src=1, key=1, deg=n - 1, role=Role.OUT, phase=1, load=0,
                    mis_nbrs=tuple(range(n - 1)))
    assert len(wire.encode(ok)) <= MAX_PAYLOAD


def test_oversize_beyond_count_field_still_raises_payload_too_large():
    """The mis_nbrs count field is one byte; a list beyond 255 must raise
    PayloadTooLarge rather than struct.error (size is checked first)."""
    big = wire.Hello(src=1, key=1, deg=0, role=Role.OUT, phase=1, load=0,
                     mis_nbrs=tuple(range(1000)))
    with pytest.raises(PayloadTooLarge):
        wire.encode(big)


def test_float_key_is_rejected_not_coerced():
    """Fixed-point discipline (brief 3.6): int() meant a silent COLLAPSE.

    For w=5, deg=2 the correct 16.16 key is 109227 and it reads back as 1.6667.
    Passing the float 1.67 put 1 on the wire and it read back as 0.00002. Every
    MIS ordering decision in Phase 1 looks at this value; a key that collapses
    silently turns the whole ordering into garbage and raises nowhere.
    """
    good = key_of(5.0, 2, 1)[0]
    assert good == 109227
    assert wire.decode(wire.encode(wire.Hello(
        src=7, key=good, deg=2, role=Role.OUT, phase=1, load=0))).key == good

    with pytest.raises(TypeError):
        wire.encode(wire.Hello(src=7, key=1.67, deg=2, role=Role.OUT,
                               phase=1, load=0))
    # even an exact-valued float is rejected: what is harmless today is not tomorrow
    with pytest.raises(TypeError):
        wire.encode(wire.Hello(src=7, key=109227.0, deg=2, role=Role.OUT,
                               phase=1, load=0))
    # bool subclasses int but it is not a key
    with pytest.raises(TypeError):
        wire.encode(wire.Hello(src=7, key=True, deg=2, role=Role.OUT,
                               phase=1, load=0))


def test_float_role_is_rejected_not_coerced():
    """The same class of bug in the same function: int(role) also coerced silently."""
    with pytest.raises(TypeError):
        wire.encode(wire.Hello(src=7, key=1, deg=2, role=2.7, phase=1, load=0))
    with pytest.raises(TypeError):
        wire.encode(wire.Hello(src=7, key=1, deg=2, role=2.0, phase=1, load=0))


def test_key_cannot_collide_with_the_none_sentinel():
    """Passing KEY_NONE explicitly would be INDISTINGUISHABLE from None on the wire."""
    with pytest.raises(ValueError):
        wire.encode(wire.Hello(src=7, key=wire.KEY_NONE, deg=2, role=Role.OUT,
                               phase=1, load=0))


def test_key_outside_int32_is_rejected_with_a_clear_error():
    with pytest.raises(ValueError):
        wire.encode(wire.Hello(src=7, key=2 ** 31, deg=2, role=Role.OUT,
                               phase=1, load=0))


def test_no_other_field_can_be_silently_coerced():
    """struct 'H'/'B' already refuse floats; the only places with an explicit
    int() call were key and role. This test exists so that a new silent
    coercion cannot slip in later unnoticed."""
    base = dict(src=7, key=1, deg=2, role=Role.OUT, phase=1, load=0, epoch=0)
    for field in ("src", "deg", "phase", "load", "epoch"):
        bad = dict(base); bad[field] = 2.5
        with pytest.raises((TypeError, struct.error)):
            wire.encode(wire.Hello(**bad))
    bad = dict(base); bad["mis_nbrs"] = (1.5,)
    with pytest.raises((TypeError, struct.error)):
        wire.encode(wire.Hello(**bad))


# --------------------------------------------------------------------------
# The ANNEAL tail (brief section 6.5): OPTIONAL and backward compatible
# --------------------------------------------------------------------------
def test_anneal_tail_round_trips_and_costs_exactly_eight_bytes():
    """.tex §13: HELLO gains x, ell, label+counter, token and T, for +8 B."""
    a = wire.Anneal(x=True, ell_fp=int(2.5 * 256), label=2, label_ctr=9,
                    token=41234, cool=46)
    h = wire.Hello(src=7, key=100, deg=3, role=Role.COVER, phase=3, load=1,
                   mis_nbrs=(1, 2), anneal=a)
    raw = wire.encode(h)
    assert wire.decode(raw) == h
    bare = wire.encode(wire.Hello(src=7, key=100, deg=3, role=Role.COVER,
                                  phase=3, load=1, mis_nbrs=(1, 2)))
    assert len(raw) - len(bare) == wire.ANNEAL_BYTES == 8
    assert wire.hello_size(0, anneal=True) == 21
    assert wire.hello_size(5, anneal=True) == 31      # .tex "toplam ~32 B"


def test_anneal_tail_is_optional_and_bare_hello_is_unchanged():
    """The BB-CVC and bootstrap HELLO must not grow by a SINGLE BYTE."""
    bare = wire.Hello(src=7, key=100, deg=3, role=Role.COVER, phase=3, load=1)
    assert len(wire.encode(bare)) == 13
    assert wire.decode(wire.encode(bare)).anneal is None
    assert wire.hello_size(0) == 13 and wire.hello_size(5) == 23


def test_anneal_tail_size_is_independent_of_degree():
    a = wire.Anneal(x=False, ell_fp=0, label=1, label_ctr=0, token=0)
    sizes = {len(wire.encode(wire.Hello(src=1, key=7, deg=d, role=Role.OUT,
                                        phase=0, load=0, anneal=a)))
             for d in (0, 1, 8, 64, 255)}
    assert sizes == {21}


def test_cooling_index_is_carried_exactly_not_quantised():
    """The cooling step j travels instead of T: j is exact and T = T0*alpha^j
    is rebuilt exactly."""
    for j in (0, 1, 46, 92, wire.COOL_MAX):
        a = wire.Anneal(x=True, ell_fp=0, label=1, label_ctr=0, token=0, cool=j)
        got = wire.decode(wire.encode(wire.Hello(
            src=1, key=1, deg=0, role=Role.OUT, phase=0, load=0, anneal=a)))
        assert got.anneal.cool == j
    with pytest.raises(ValueError):
        wire.encode(wire.Hello(src=1, key=1, deg=0, role=Role.OUT, phase=0, load=0,
                               anneal=wire.Anneal(True, 0, 1, 0, 0, wire.COOL_MAX + 1)))


def test_x_flag_and_cooling_index_share_a_byte_without_collision():
    """x in bit 0, j in bits 1..7. Neither may corrupt the other."""
    for x in (False, True):
        for j in (0, 1, 63, wire.COOL_MAX):
            a = wire.Anneal(x=x, ell_fp=513, label=9, label_ctr=3, token=7, cool=j)
            got = wire.decode(wire.encode(wire.Hello(
                src=1, key=1, deg=0, role=Role.OUT, phase=0, load=0,
                anneal=a))).anneal
            assert (got.x, got.cool) == (x, j)


def test_a_hello_with_a_malformed_tail_is_rejected():
    """The tail is either absent or exactly 8 B. No length in between may be
    swallowed silently."""
    raw = wire.encode(wire.Hello(src=1, key=1, deg=0, role=Role.OUT, phase=0,
                                 load=0, anneal=wire.Anneal(True, 0, 1, 0, 0)))
    for cut in (1, 3, 7):
        with pytest.raises(ValueError):
            wire.decode(raw[:-cut])
    with pytest.raises(ValueError):
        wire.decode(raw + b"\x00")


def test_anneal_fields_reject_silent_coercion_too():
    """The same discipline applies in the tail: a float is never coerced silently."""
    base = dict(src=1, key=1, deg=0, role=Role.OUT, phase=0, load=0)
    for field in ("ell_fp", "label", "label_ctr", "token", "cool"):
        kw = dict(x=True, ell_fp=0, label=1, label_ctr=0, token=0, cool=0)
        kw[field] = 2.5
        with pytest.raises((TypeError, ValueError, struct.error)):
            wire.encode(wire.Hello(anneal=wire.Anneal(**kw), **base))


def test_wrong_type_for_body_is_rejected():
    with pytest.raises(ValueError):
        wire.encode(wire.Ctrl(MsgType.JOIN, 1, 0))
    with pytest.raises(ValueError):
        wire.encode(wire.EdgeMsg(MsgType.HELLO, 1, 0, 1, 2))


def test_token_carries_the_walk_initiator(): 
    """DFS-Spanning-Backbone has no elected root: every local minimum starts its own walk and
    the walk with the smaller `init` absorbs the other. A receiver cannot infer
    which walk an incoming token belongs to from anything it already holds, so
    `init` MUST be on the wire (brief section 6, bb-bootstrap)."""
    for mt in (MsgType.TOKEN, MsgType.TOKEN_DONE):
        m = wire.Token(mt, src=7, seq=3, init=42)
        raw = wire.encode(m)
        assert len(raw) == 7
        assert wire.decode(raw) == m
        assert wire.decode(raw).init == 42


def test_token_initiator_has_no_reserved_value():
    """bb-bootstrap compares initiators NUMERICALLY and does not rely on a
    sentinel; the format must not either. 0 and 65535 must encode and return."""
    for init in (0, 1, 65535):
        got = wire.decode(wire.encode(wire.Token(MsgType.TOKEN, 1, 0, init)))
        assert got.init == init


def test_token_is_not_smuggled_into_the_ctrl_body():
    """Overloading `seq` would pollute a field the way reusing a type pollutes
    a counter. The two bodies
    are SEPARATE and each REJECTS the other's type."""
    with pytest.raises(ValueError):
        wire.encode(wire.Ctrl(MsgType.TOKEN, 1, 0))
    with pytest.raises(ValueError):
        wire.encode(wire.Ctrl(MsgType.TOKEN_DONE, 1, 0))
    with pytest.raises(ValueError):
        wire.encode(wire.Token(MsgType.LINK, 1, 0, 1))
    # LINK is still 5 B: the initiator field did NOT grow it
    assert len(wire.encode(wire.Ctrl(MsgType.LINK, 1, 0))) == 5


def test_token_is_unicast_sized_and_far_below_the_payload_limit():
    """TOKEN is unicast: it does not touch the HELLO density argument and is
    far below the I3 ceiling."""
    assert wire.sizes()["TOKEN"] == 7 < MAX_PAYLOAD
    assert wire.hello_size(0) == 13      # HELLO is unchanged


def test_truncated_payload_is_rejected():
    raw = wire.encode(_one_of_each()[MsgType.HELLO])
    with pytest.raises((ValueError, struct.error)):
        wire.decode(raw[:-3])
    with pytest.raises(ValueError):
        wire.decode(b"")


def test_unknown_type_byte_is_rejected():
    with pytest.raises(ValueError):
        wire.decode(bytes([200, 1, 0]))


def test_encoding_is_deterministic_across_instances():
    a = _one_of_each()
    b = _one_of_each()
    for mtype in MsgType:
        assert wire.encode(a[mtype]) == wire.encode(b[mtype])
