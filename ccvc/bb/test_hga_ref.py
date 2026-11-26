"""hga_ref on development files only (dataset seeds 1-10); no held-out file is generated or opened."""
import csv
import os
import subprocess

import pytest

from ccvc.bb import hga_ref, matrix, revision_stats

DEV = matrix.dataset_dir()
pytestmark = pytest.mark.skipif(DEV is None, reason="published dataset not found")


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_valid_row_resume_and_stats_reader(tmp_path):
    out = str(tmp_path / "hga.csv")
    argv = [os.path.join(DEV, "n10_m20_s1.txt"), "--out", out, "--time-limit", "60"]
    assert hga_ref.main(argv) == 0
    (r,) = _rows(out)
    assert (r["status"], r["valid"], r["owner_source"], r["group"]) == (
        "ok",
        "True",
        "flow",
        "small",
    )
    assert (r["pop_size"], r["generations"], r["ga_seed"]) == ("40", "60", "42")
    # quantized units of the sweep rows; the proven optimum at k = 6 is 3384 (results/bb/exact/optima.csv)
    assert float(r["weight"]) >= 3384
    assert hga_ref.main(argv) == 0 and len(_rows(out)) == 1  # resumed, nothing re-run
    assert set(revision_stats.load_central([out])) == {
        ("n10_m20_s1.txt", 6, hga_ref.ARM)
    }


def test_time_limit_keeps_the_run_as_a_failure(tmp_path):
    out = str(tmp_path / "hga.csv")
    path = os.path.join(DEV, "n10_m20_s1.txt")
    assert (
        hga_ref.main([path, "--out", out, "--time-limit", "0.05", "--ga-seeds", "1"])
        == 0
    )
    (r,) = _rows(out)
    assert (r["status"], r["timed_out"], r["valid"], r["weight"]) == (
        "timeout",
        "True",
        "False",
        "",
    )
    # the profiling timer and process_time start a few instructions apart and the value is rounded
    assert float(r["cpu_seconds"]) >= 0.04


def test_sealed_seed_refused_before_any_file_is_opened(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hga_ref, "frozen_tag_exists", lambda: False)
    never_created = tmp_path / "H1" / "ratio2" / "n10_m20_s101.txt"
    out = tmp_path / "hga.csv"
    assert (
        hga_ref.main([str(never_created), "--out", str(out), "--time-limit", "1"]) == 2
    )
    assert not out.exists() and hga_ref.TAG in capsys.readouterr().err


def test_only_an_annotated_tag_unseals(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)  # fmt: skip

    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "init")
    git("tag", hga_ref.TAG)
    assert not hga_ref.frozen_tag_exists(str(tmp_path))
    git("tag", "-d", hga_ref.TAG)
    git("tag", "-a", hga_ref.TAG, "-m", "frozen")
    assert hga_ref.frozen_tag_exists(str(tmp_path))
