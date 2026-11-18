"""Regression checks for small experiment gates, without running experiments."""
from types import SimpleNamespace as NS

from ccvc.bb.smoke import validation_report


def fixture():
    entry = NS(instance=NS(source="synthetic", cell=NS(n=10),
                           edges=[(1, 2)], seed=1),
               spec=NS(name="test"), scheduler="async")
    row = NS(source="synthetic", n=10, m=1, seed=1, variant="test",
             scheduler="async", status="ok", converged=True,
             truncated=False, unresolved=False, infeasible=False,
             valid=True, vertex_cover=True, connected=True, capacity=True,
             violations=0, verdict_agrees="yes", trace_agrees="none",
             tx=1, rx=1, retx=0, bytes_tx=13, max_payload=13,
             code_fingerprint="revision")
    return entry, row


def test_missing_or_duplicated_runs_fail_coverage():
    entry, row = fixture()
    assert validation_report([row], [entry])["passed"]
    assert not validation_report([], [entry])["passed"]
    assert not validation_report([row, row], [entry])["gates"]["complete_paired_coverage"]


def test_valid_aggregate_cannot_hide_unresolved_node():
    entry, row = fixture()
    row.unresolved = True
    report = validation_report([row], [entry])
    assert report["gates"]["cover_connectivity_capacity"]
    assert not report["passed"]


def test_missing_measurement_is_not_treated_as_zero():
    entry, row = fixture()
    row.tx = None
    assert not validation_report([row], [entry])["gates"]["costs_recorded"]


def test_disagreeing_verdict_or_trace_blocks_scale_increase():
    entry, row = fixture()
    row.trace_agrees = "no"
    assert not validation_report([row], [entry])["passed"]
