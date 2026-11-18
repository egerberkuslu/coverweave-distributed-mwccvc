#!/usr/bin/env python3
"""`ccvc/bb/exact_compare.py` tests: the joins it claims to refuse, it refuses.

Run:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_exact_compare.py -q

The module makes five claims a wrong table would silently violate, so each one
is tested in its BROKEN form as well: a test that only shows the rule holding
says nothing about what happens when it is crossed.

  1. An optimum measured at one capacity is not an optimum at another. The join
     is on (instance, k), so a row at k = 9 must not be used to score a k = 6
     cover.
  2. The basis is shared. An arm that fails on an instance must remove that
     instance from EVERY row's average, not just from its own.
  3. A centralized reference that fails must shrink the basis the same way a
     distributed arm does, or a 32-instance mean and a 28-instance mean end up
     in one column.
  4. Where m = nk the cover is forced and every arm is optimal without deciding
     anything, so those instances must not be counted as hits.
  5. Old arm names in measured data must be translated on read, or one arm is
     averaged twice as two.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from ccvc.bb import exact_compare as ec


def _sweep_row(instance, variant, weight, *, k=6, n=10, m=20, scheduler="sync",
               valid=True, verdict="solved"):
    return {
        "instance": instance, "variant": variant, "scheduler": scheduler,
        "k": str(k), "n": str(n), "m": str(m),
        "total_weight": str(weight),
        "valid": "True" if valid else "False",
        "verdict": verdict,
    }


def _optimum_row(instance, optimum, *, k=6, n=10, m=20, cover_size=5,
                 status="ok"):
    return {
        "instance": instance, "n": str(n), "m": str(m), "k": str(k),
        "optimum": str(optimum), "cover_size": str(cover_size),
        "status": status,
    }


def _central_row(instance, algorithm, weight, *, k=6, valid=True, n=10, m=20):
    return {
        "instance": instance, "n": str(n), "m": str(m), "k": str(k),
        "algorithm": algorithm, "arm": ec.CENTRAL_LABEL[algorithm],
        "weight": str(weight), "valid": "True" if valid else "False",
    }


ARMS = ("GHS-MST-Backbone", "Anneal-Local")


# 1 -------------------------------------------------------------------------
def test_optimum_index_keys_on_instance_and_capacity():
    rows = [_optimum_row("a.txt", 100, k=6), _optimum_row("a.txt", 80, k=9)]
    index = ec.optimum_index(rows)
    assert index[("a.txt", 6)] == 100.0
    assert index[("a.txt", 9)] == 80.0


def test_a_different_capacity_is_not_used_as_a_reference():
    """The k = 9 optimum is LIGHTER, so using it would inflate every ratio."""
    optima = ec.optimum_index([_optimum_row("a.txt", 80, k=9)])
    sweep = [_sweep_row("a.txt", arm, 120, k=6) for arm in ARMS]
    stats, prov = ec.collect(sweep, optima, ARMS)
    assert prov["instances_with_optimum"] == 0
    assert all(not s.ratios for s in stats.values())
    # and with the matching capacity present, the same rows DO score
    optima[("a.txt", 6)] = 100.0
    stats, prov = ec.collect(sweep, optima, ARMS)
    assert prov["instances_with_optimum"] == 1
    assert stats["GHS-MST-Backbone/sync"].ratios == [1.2]


# 2 -------------------------------------------------------------------------
def test_one_arms_failure_removes_the_instance_from_every_average():
    optima = ec.optimum_index([_optimum_row("a.txt", 100),
                               _optimum_row("b.txt", 100)])
    good = [_sweep_row("a.txt", arm, 110) for arm in ARMS]
    good += [_sweep_row("b.txt", arm, 200) for arm in ARMS]
    stats, prov = ec.collect(good, optima, ARMS)
    assert prov["instances_basis"] == 2
    assert stats["Anneal-Local/sync"].mean == pytest.approx(1.55)

    broken = [r for r in good if not (r["instance"] == "b.txt"
                                      and r["variant"] == "GHS-MST-Backbone")]
    broken.append(_sweep_row("b.txt", "GHS-MST-Backbone", 200,
                             valid=False, verdict="unresolved"))
    stats, prov = ec.collect(broken, optima, ARMS)
    assert prov["instances_basis"] == 1
    # the OTHER arm's mean moved too: it is no longer averaged over b.txt
    assert stats["Anneal-Local/sync"].mean == pytest.approx(1.10)
    assert stats["Anneal-Local/sync"].valid == 2      # but its validity stands


# 3 -------------------------------------------------------------------------
def test_a_failing_centralized_reference_shrinks_the_shared_basis():
    optima = ec.optimum_index([_optimum_row("a.txt", 100),
                               _optimum_row("b.txt", 100)])
    sweep = [_sweep_row(i, arm, 110) for i in ("a.txt", "b.txt") for arm in ARMS]
    central = [_central_row("a.txt", "gccvc", 105),
               _central_row("b.txt", "gccvc", 105, valid=False)]
    _, prov_alone = ec.collect(sweep, optima, ARMS)
    _, prov_shared = ec.collect(sweep, optima, ARMS, central)
    assert prov_alone["instances_basis"] == 2
    assert prov_shared["instances_basis"] == 1
    stats = ec.collect_central(central, optima, prov_shared["basis"],
                               prov_shared["scope"])
    entry = stats[ec.CENTRAL_LABEL["gccvc"]]
    assert entry.ratios == [1.05]        # only the shared instance is averaged
    assert (entry.valid, entry.runs) == (1, 2)   # the failure is still visible


# 4 -------------------------------------------------------------------------
def test_a_forced_cover_is_not_counted_as_choosing_the_optimum():
    """m = nk forces every vertex in, so being optimal there proves nothing."""
    rows = [_optimum_row("tight.txt", 100, n=10, m=60, cover_size=10),
            _optimum_row("free.txt", 100, n=10, m=20, cover_size=6)]
    forced = ec.forced_index(rows)
    assert forced == {"tight.txt"}
    optima = ec.optimum_index(rows)
    sweep = [_sweep_row(i, arm, 100, m=60 if i == "tight.txt" else 20)
             for i in ("tight.txt", "free.txt") for arm in ARMS]
    stats, prov = ec.collect(sweep, optima, ARMS, (), forced)
    assert prov["instances_basis"] == 2
    assert prov["instances_forced"] == 1 and prov["instances_free"] == 1
    for entry in stats.values():
        assert entry.ratios == [1.0, 1.0]     # both instances still scored
        assert entry.at_optimum == 1          # but only one is credited


# 5 -------------------------------------------------------------------------
def test_pre_rename_arm_names_are_translated_on_read():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "rows.csv")
        ec._write_csv(path, ("instance", "variant", "scheduler", "k", "n", "m",
                             "total_weight", "valid", "verdict"),
                      [_sweep_row("a.txt", "V2-BB-local", 110),
                       _sweep_row("b.txt", "MIS-Connector-Backbone", 120)])
        rows = ec.load_sweep_rows([path])
    assert {r["variant"] for r in rows} == {"MIS-Connector-Backbone"}


def test_a_written_table_names_no_file_and_carries_the_label():
    optima = ec.optimum_index([_optimum_row("a.txt", 100)])
    sweep = [_sweep_row("a.txt", arm, 110) for arm in ARMS]
    stats, prov = ec.collect(sweep, optima, ARMS)
    tex = ec.build_table(stats, {}, prov, 6, "Caption.", "tab:exact")
    assert r"\label{tab:exact}" in tex
    assert "a.txt" not in tex and ".csv" not in tex and "results/" not in tex
    assert r"\begin{table*}" in tex
