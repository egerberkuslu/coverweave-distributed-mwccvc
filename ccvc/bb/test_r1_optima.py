"""r1_optima on development files only (dataset seeds 1-10); no held-out file is generated or opened."""
import csv
import os

import pytest

from ccvc.bb import hga_ref, matrix, r1_optima, revision_stats

DEV = matrix.dataset_dir()
pytestmark = pytest.mark.skipif(DEV is None, reason="published dataset not found")


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_optimum_timeout_resume_and_stats_reader(tmp_path):
    out = str(tmp_path / "optima.csv")
    small, slow = os.path.join(DEV, "n10_m20_s1.txt"), os.path.join(
        DEV, "n50_m100_s3.txt"
    )
    # n50_m100_s3 needed 49.6 s in results/bb/exact/optima_n50.csv
    argv = [small, slow, "--out", out, "--time-limit", "0.5", "--processes", "2"]
    assert r1_optima.main(argv) == 0
    rows = {r["instance"]: r for r in _rows(out)}
    ok, late = rows["n10_m20_s1.txt"], rows["n50_m100_s3.txt"]
    # the proven optimum at k = 6 is 3384 (results/bb/exact/optima.csv)
    assert (ok["status"], ok["optimum"], ok["group"], ok["seed"]) == (
        "ok",
        "3384",
        "small",
        "1",
    )
    assert ok["lp_status"] == "optimal" and float(ok["lp_bound"]) <= 3384
    assert (late["status"], late["optimum"], late["lp_status"]) == (
        "timed_out",
        "",
        "optimal",
    )
    assert float(late["cpu_seconds"]) >= 0.4 and float(late["lp_bound"]) <= 19299
    assert r1_optima.main(argv) == 0 and len(_rows(out)) == 2  # resumed, nothing re-run
    # the timed-out instance carries no optimum, so the tables use its LP bound
    assert revision_stats.load_optima([out]) == {("n10_m20_s1.txt", 6): 3384.0}


def test_sealed_seed_refused_before_any_file_is_opened(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hga_ref, "frozen_tag_exists", lambda: False)
    never_created = tmp_path / "H1-unit" / "ratio2" / "n25_m50_s101_unit.txt"
    out = tmp_path / "optima.csv"
    argv = [str(never_created), "--out", str(out), "--time-limit", "1"]
    assert r1_optima.main(argv) == 2
    assert not out.exists() and hga_ref.TAG in capsys.readouterr().err
    with pytest.raises(SystemExit):  # a name without its seed cannot pass the guard
        r1_optima.main(
            [str(tmp_path / "graph.txt"), "--out", str(out), "--time-limit", "1"]
        )
