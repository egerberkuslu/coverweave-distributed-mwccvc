"""Tests for the reporting layer, where a wrong number is published quietly.

A defect here does not crash and does not fail a run. It prints a table that
looks finished and is read as evidence, so each test below pins a case where
that actually happened.
"""

import json
import os

from ccvc.bb import report_pipeline as rp


def test_infeasibility_uses_the_strongest_bound_not_only_the_counting_one():
    """A DENOMINATOR BUG CHARGES EVERY ARM AT ONCE.

    Two bounds prove a BB-CVC instance unsolvable. The counting bound is
    `m > n*k`; the degree deficiency `sum_v min(deg v, k) < m` is strictly
    stronger because a node cannot own more edges than it has. The pipeline
    read the counting bound alone, so at the exact boundary `m == n*k`, where
    the counting bound is silent, an impossible instance stayed in the
    denominator and all twenty-five arms read 17/18 for a row none of them
    could ever solve. MEASURED on `n50_m300_s6`: m = n*k = 300, two nodes of
    degree five, ownable capacity 298.
    """
    boundary = {"infeasible": "True", "instance_feasible": "no",
                "infeasible_reason": "degree_deficiency",
                "counting_bound_infeasible": "False"}
    assert rp._run_infeasible(boundary), "derece açığı tanığı okunmuyor"

    solvable = {"infeasible": "False", "instance_feasible": "yes",
                "infeasible_reason": "", "counting_bound_infeasible": "False"}
    assert not rp._run_infeasible(solvable)

    # An older CSV has neither column, and must keep reading exactly as before.
    legacy_bad = {"counting_bound_infeasible": "True"}
    legacy_ok = {"counting_bound_infeasible": "False"}
    assert rp._run_infeasible(legacy_bad)
    assert not rp._run_infeasible(legacy_ok)


def test_wireless_documents_are_found_in_the_directory_layout(tmp_path):
    """A TABLE THAT CANNOT BE REBUILT IS A TABLE NOBODY CAN CHECK.

    The runner used to write one flat `<stem>.json` per run and now writes a
    DIRECTORY per run with `summary.json` inside. The loader read only the flat
    form, so it returned nothing for an archive that was completely intact:
    `table_wireless` returned None, the pipeline skipped the table without a
    word, and the published `wireless.tex` silently froze while still being
    cited as evidence. Both layouts must resolve to the same run identity.
    """
    root = tmp_path / "wifi"
    (root / "dag_anneal_n10_m20_s1").mkdir(parents=True)
    body = {"n_nodes": 10, "cover": [1, 2], "cover_weight": 3.0, "slots": 7,
            "discovered_vs_target": {"n_target": 20, "n_observed": 34},
            "validation": {"valid": True}}
    (root / "dag_anneal_n10_m20_s1" / "summary.json").write_text(
        json.dumps(body), encoding="utf-8")
    # A side file in the same directory must not be mistaken for a run.
    (root / "dag_anneal_n10_m20_s1" / "run.json").write_text(
        json.dumps({"k": 6}), encoding="utf-8")

    docs = rp._wireless_docs(str(root))
    assert len(docs) == 1, f"dizin düzeni okunmuyor: {len(docs)} belge"
    assert docs[0]["_arm"] == "anneal"
    assert docs[0]["_seed"] == 1
    assert docs[0]["_family"] == "n10_m20"

    # The flat layout keeps working, and the two agree on identity.
    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "dag_anneal_n10_m20_s1.json").write_text(
        json.dumps(body), encoding="utf-8")
    flat_docs = rp._wireless_docs(str(flat))
    assert len(flat_docs) == 1
    assert ((flat_docs[0]["_arm"], flat_docs[0]["_seed"], flat_docs[0]["_family"])
            == (docs[0]["_arm"], docs[0]["_seed"], docs[0]["_family"]))


def test_published_wireless_table_still_matches_its_archive():
    """The published table must be reproducible from the runs it came from.

    This is the check that would have caught the frozen table: rebuild it from
    the archive and compare against what is on disk.
    """
    indir = "results/bb/wifi_dagdeviren"
    published = "results/bb/report/tables/wireless.tex"
    if not (os.path.isdir(indir) and os.path.exists(published)):
        import pytest
        pytest.skip("arşiv bu ağaçta yok")
    rebuilt = rp.table_wireless(indir)
    assert rebuilt is not None, "arşivden tablo üretilemiyor"
    assert rebuilt.strip() == open(published, encoding="utf-8").read().strip()
