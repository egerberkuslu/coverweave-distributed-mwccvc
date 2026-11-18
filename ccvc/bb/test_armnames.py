#!/usr/bin/env python3
"""Arm naming: the registries agree and no old name is ever written again.

These tests exist because the rename touched six registries in five modules and
a sweep CSV on disk. The failure they guard against is silent: one registry
keeps an old spelling, the report pipeline then sees two arms where there is
one, and each half is averaged separately into what reads as a real difference.
"""
from __future__ import annotations

import re

import pytest

from ccvc.bb import armnames, report_pipeline, sweep
from ccvc.greedy import audit, central

#: What an arm name looked like before the rename: a version number first.
OLD_SHAPE = re.compile(r"^(V\d|[CD]-[A-Z]+-)")


def _names():
    return [spec.name for spec in sweep.discover()]


def test_no_registered_arm_still_carries_a_version_number_name():
    stale = [n for n in _names() if OLD_SHAPE.match(n)]
    assert not stale, f"these arms were not renamed: {stale}"


def test_every_legacy_name_maps_to_something_that_exists():
    """A legacy row that points nowhere is worse than no row at all.

    The family prefix `V5-BB-WuLi` and the three central `C-*-UPSTREAM` arms
    are not sweep arms, so they are named explicitly rather than looked up.
    """
    registered = set(_names())
    not_sweep_arms = {"WuLi-Dominating"} | {
        armnames.greedy_arm(rule, "Upstream") for rule in central.ALGORITHMS}
    for old, new in armnames.LEGACY_NAMES.items():
        assert new in registered or new in not_sweep_arms, (
            f"{old} maps to {new}, which no registry defines")


def test_legacy_translation_is_idempotent_and_keeps_the_scheduler_field():
    assert armnames.canonical("V4-BB-MST") == "GHS-MST-Backbone"
    assert armnames.canonical("GHS-MST-Backbone") == "GHS-MST-Backbone"
    assert armnames.canonical("V6-ANNEAL/sync") == "Anneal-Local/sync"
    assert armnames.canonical("Anneal-Local/sync") == "Anneal-Local/sync"
    # The message-size label is family/scheduler/encoding/policy; only the
    # first field is an arm name and only it may be rewritten.
    assert (armnames.canonical("V5-BB-WuLi/sync/bloom/safe")
            == "WuLi-Dominating/sync/bloom/safe")
    # An unknown arm passes through: a new variant must not need a legacy row.
    assert armnames.canonical("V-yeni/async") == "V-yeni/async"


def test_a_sweep_row_measured_before_the_rename_lands_on_the_new_arm():
    rows = [{"variant": "V2-BB-local", "scheduler": "sync"},
            {"variant": "MIS-Connector-Backbone", "scheduler": "sync"}]
    armnames.canonical_rows(rows)
    assert {r["variant"] for r in rows} == {"MIS-Connector-Backbone"}, (
        "old and new spellings must collapse to one arm, or the report "
        "averages one arm as two")


def test_station_configuration_is_reachable_under_both_spellings():
    assert audit.arm_config("D-GRCCVC-BB") == audit.arm_config(
        "Greedy-Ratio-Backbone")


def test_arm_config_covers_every_registered_arm():
    assert set(audit.ARM_CONFIGS) == set(_names())


def test_report_row_order_covers_every_registered_arm():
    assert set(report_pipeline.ARM_ORDER) == set(_names())


@pytest.mark.parametrize("rule,word", [("gccvc", "Degree"),
                                       ("grccvc", "Ratio"),
                                       ("gwccvc", "Weight")])
def test_greedy_arm_names_the_score_not_the_shared_word_cover(rule, word):
    """The three greedy arms differ only in the score, so the name must say it."""
    assert armnames.greedy_arm(rule, "Backbone") == f"Greedy-{word}-Backbone"
    assert armnames.greedy_arm(rule, "Upstream") == f"Greedy-{word}-Upstream"


def test_an_unknown_rule_or_role_is_refused():
    with pytest.raises(ValueError):
        armnames.greedy_arm("gxccvc", "Backbone")
    with pytest.raises(ValueError):
        armnames.greedy_arm("gccvc", "Sideways")


# --------------------------------------------------------------------------
# THE MANUSCRIPT NAMES MUST COVER EVERY ARM THE PAPER PRINTS
#
# The rename is applied to the .tex in one pass, driven by this map. An arm
# missing from it would keep its repository spelling in one table while every
# other table carried the paper name, and the two would read as two arms.
# --------------------------------------------------------------------------


def test_every_registered_arm_has_a_manuscript_name():
    missing = [n for n in _names() if n not in armnames.DISPLAY_NAMES]
    assert not missing, f"these arms would print their code name: {missing}"


def test_every_display_key_is_a_real_arm_or_a_documented_non_arm():
    """A key that names nothing silently stops translating when a name moves."""
    known = set(_names()) | {"BB-CVC", "WuLi-Dominating"}
    known |= {armnames.greedy_arm(rule, "Upstream") for rule in central.ALGORITHMS}
    # The short spellings the single-column tables use for the same arms.
    known |= {"MIS-Connector", "GHS-MST", "DFS-Spanning",
              "WuLi-Exact", "WuLi-Bloom", "WuLi-Chunked"}
    orphans = [k for k in armnames.DISPLAY_NAMES if k not in known]
    assert not orphans, f"these keys name no arm: {orphans}"


def test_display_translates_legacy_rows_and_keeps_the_scheduler_field():
    assert armnames.display("V4-BB-MST") == "FabricTree"
    assert armnames.display("GHS-MST-Backbone") == "FabricTree"
    assert armnames.display("Anneal-Trickle/async") == "TemperFlux-Tk/async"
    assert (armnames.display("V5-BB-WuLi/sync/bloom/safe")
            == "Wu-Li CDS/sync/bloom/safe")
    # An arm with no paper name yet must pass through, not vanish.
    assert armnames.display("V-yeni/async") == "V-yeni/async"


def test_display_is_idempotent():
    """Printing a name twice must not translate it twice."""
    for name in armnames.DISPLAY_NAMES:
        once = armnames.display(name)
        assert armnames.display(once) == once, name


# --------------------------------------------------------------------------
# THE BRIDGE-FIX TABLE MUST COME FROM DATA
#
# tab:bridgefix was typed into the .tex by hand, so nothing regenerated it and
# nothing noticed when the code moved. It is now produced by
# `bridgefix_measure` and only carried through by the pipeline.
# --------------------------------------------------------------------------
def test_bridgefix_table_is_carried_through_when_measured(tmp_path):
    from ccvc.bb import report_pipeline as rp
    body = "\\label{tab:bridgefix}\nFlips, worst node & 269 & 6 \\\\\n"
    (tmp_path / "tab_bridgefix.tex").write_text(body, encoding="utf-8")
    assert rp.table_bridgefix(str(tmp_path)) == body


def test_bridgefix_table_is_absent_rather_than_invented(tmp_path):
    from ccvc.bb import report_pipeline as rp
    assert rp.table_bridgefix(str(tmp_path)) is None


def test_the_unrepaid_discount_can_still_be_reproduced_on_demand():
    """The flag is the evidence: without it the defect is only a memory.

    A single flip is enough to see the asymmetry, so this stays a unit test.
    Joining records a debt only when the fix is on; with it off the credit
    stays zero and leaving therefore repays nothing.
    """
    from ccvc.bb.anneal import AnnealParams
    assert AnnealParams().repay_bridge_credit is True
    assert AnnealParams(repay_bridge_credit=False).repay_bridge_credit is False


# --------------------------------------------------------------------------
# THE WIRELESS TABLE IS READ FROM THE RUNS, NOT WRITTEN INTO THE CAPTION
# --------------------------------------------------------------------------
def _wifi_doc(tmp_path, stem, *, observed, cover, weight, valid=True, tx=100):
    import json as _json
    doc = {
        "n_nodes": 15,
        "discovered_vs_target": {"n_target": 90, "n_observed": observed,
                                 "n_missing": 0, "n_extra": observed - 90,
                                 "missing": [], "extra": [], "jaccard": 1.0},
        "cover": cover, "cover_weight": weight, "slots": 10,
        "totals": {"tx": tx},
        "validation": {"valid": valid},
        "validation_vs_discovered": {"valid": valid},
    }
    (tmp_path / f"{stem}.json").write_text(_json.dumps(doc), encoding="utf-8")


def test_wireless_table_names_an_empty_result_instead_of_printing_zero(tmp_path):
    """Weight 0 in a "lower is better" column would read as the best row."""
    from ccvc.bb import report_pipeline as rp
    _wifi_doc(tmp_path, "dag_bbcvc_n15_m90_s1", observed=98, cover=[1, 2],
              weight=500.0)
    _wifi_doc(tmp_path, "dag_mst_n15_m90_s1", observed=98, cover=[], weight=0.0,
              valid=False, tx=31949)

    tex = rp.table_wireless(str(tmp_path))

    assert r"\textit{no cover}" in tex
    assert "& 0.0 &" not in tex, "boş sonuç ağırlık sütununda sıfır olarak yazılamaz"
    assert "1 of 2 runs returned no cover" in tex
    assert "31949" in tex, "sonuç vermeyen kolun maliyeti yine de görünmeli"


def test_wireless_table_says_when_the_arms_did_not_see_the_same_graph(tmp_path):
    from ccvc.bb import report_pipeline as rp
    _wifi_doc(tmp_path, "dag_bbcvc_n15_m90_s1", observed=98, cover=[1], weight=5.0)
    _wifi_doc(tmp_path, "dag_mst_n15_m90_s1", observed=97, cover=[1], weight=5.0)

    tex = rp.table_wireless(str(tmp_path))

    assert "did not all discover the same" in tex
    assert "comparison is paired" not in tex


def test_wireless_loader_skips_the_side_files_a_run_directory_holds(tmp_path):
    from ccvc.bb import report_pipeline as rp
    _wifi_doc(tmp_path, "dag_bbcvc_n15_m90_s1", observed=98, cover=[1], weight=5.0)
    (tmp_path / "dag_bbcvc_n15_m90_s1.plan.json").write_text(
        '{"run_dir": "/tmp/run/x", "n": 15}' + " " * 120, encoding="utf-8")

    docs = rp._wireless_docs(str(tmp_path))

    assert [d["_arm"] for d in docs] == ["bbcvc"]
