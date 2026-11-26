"""Run counts of build_jobs against the pre-registration arithmetic.

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest results/bb/r1_dryrun/test_build_jobs.py
No instance is generated or read: cells are listed in memory with seeds 1..10.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_jobs as B  # noqa: E402

CELLS = {  # family -> (cells as (n, param, m), seeds per cell), heldout.FAMILIES with Amendment 2
    "H1": (
        [(n, r, n * r) for n in (10, 15, 20, 25, 50, 100, 150, 200) for r in (2, 4)],
        10,
    ),
    "H1-large": ([(n, r, n * r) for n in (500, 1000) for r in (2, 4)], 2),
    "H2a": ([(n, d, n * d // 2) for n in (25, 50, 100, 200) for d in (6, 8)], 10),
    "H2b": ([(n, a, a * (n - a)) for n in (25, 50, 100, 200) for a in (2, 4)], 10),
    "M9": ([(n, 6, 100) for n in (20, 30, 50)], 7),
    "H1-unit": ([(n, r, n * r) for n in (25, 50, 100) for r in (2, 4)], 5),
    "H1-degree": ([(n, r, n * r) for n in (25, 50, 100) for r in (2, 4)], 5),
    "H1-lognormal": ([(n, r, n * r) for n in (25, 50, 100) for r in (2, 4)], 5),
    "H1-energy": ([(n, r, n * r) for n in (25, 50, 100) for r in (2, 4)], 5),
}


def fake(families):
    return [
        dict(
            dataset="/nonexistent",
            instance=f"n{n}_m{m}_s{s}.txt",
            family=f,
            param=p,
            n=n,
            m=m,
            seed=s,
        )
        for f in families
        for n, p, m in CELLS[f][0]
        for s in range(1, CELLS[f][1] + 1)
    ]


def runs(block, families, monkeypatch):
    monkeypatch.setattr(B, "feasible", lambda inst, k: True)
    return sum(len(j["configs"]) for j in B.build(block, fake(families), "/tmp/x"))


def test_block_counts(monkeypatch):
    assert len(B.ALL25) == 25 and B.ALL25[0] == B.WITNESS
    assert runs("M3", ["H1", "H1-large"], monkeypatch) == 4200
    assert runs("M4", ["H2a", "H2b"], monkeypatch) == 4000
    # prereg says 6400; Amendment 2 leaves H2a degree 8 only and H2a has no n = 15 cell
    assert runs("M5", ["H1", "H2a"], monkeypatch) == 3200 + 1200
    # 60 instances x 8 conditions x 5 x 3 = 7200, plus the F9-off ablation 60 x 3 x 5 x 3
    assert runs("M6", ["H1", "H2a"], monkeypatch) == 7200 + 2700
    assert runs("M8", ["H1", "H2a"], monkeypatch) == 40 * (16 * 14 + 11 * 12)
    laws = ["H1-unit", "H1-degree", "H1-lognormal", "H1-energy"]
    assert runs("M8", ["H1", "H2a", *laws], monkeypatch) == 14240 + 120 * 10


def test_profile_counts_amendment15(monkeypatch):
    monkeypatch.setattr(B, "feasible", lambda inst, k: True)
    prof = {"adaptive_stale": False, "stale_periods": 24, "stab_periods": 24}
    m6 = B.build("M6", fake(["H1", "H2a"]), "/tmp/x", profile=prof)
    # 60 x 3 x 5 x (lossless default + profile, 7 lossy at the profile), plus the ablation
    # 40 instances (n 25, 50) x 2 conditions x channel seed 1 x 5
    assert sum(len(j["configs"]) for j in m6) == 60 * 3 * 5 * 9 + 40 * 2 * 5
    lossy = [j for j in m6 if j["loss"] != 0.0]
    assert all(j.get("params") == prof for j in lossy if "params" in j)
    assert {(j["n"], j["rng_seed"], j["loss"]) for j in lossy if "params" not in j} <= {
        (n, 1, c) for n in (25, 50) for c in B.M6_ABLATION
    }
    m8 = B.build("M8", fake(["H1", "H2a"]), "/tmp/x", profile=prof)
    assert sum(len(j["configs"]) for j in m8) == 40 * (16 * 14 + 11 * 12)
    for j in m8:
        p = j.get("params") or {}
        assert (j["loss"] != 0.0) == (p.get("adaptive_stale") is False)
        if j["loss"] and p.get("stale_periods") != 24:
            assert (
                p["stale_periods"] in (12, 48)
                and p["stab_periods"] == p["stale_periods"]
            )
    assert len({j["id"] for j in m6 + m8}) == len(m6) + len(m8)


def test_split_and_witness(monkeypatch):
    monkeypatch.setattr(B, "feasible", lambda inst, k: inst["m"] <= inst["n"] * k)
    big = fake(["H1-large"])
    jobs = B.build("M3", big, "/tmp/x")
    assert all(
        len(j["configs"]) == 1 for j in jobs
    )  # feasible n > 200: one job per configuration
    inf = dict(big[0], m=big[0]["n"] * 7)
    (j,) = B.jobs_for(
        inf, 6, 0.0, 1, B.ALL25, "/tmp/x"
    )  # infeasible: one job, witness first
    assert j["configs"][0] == list(B.WITNESS)
    m9 = B.build("M9", fake(["M9"]), "/tmp/x")
    assert all(j["all_configs_on_infeasible"] for j in m9) and len(m9) == 21


def test_sealed_set_refused_without_tag(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"generator": "ccvc.bb.heldout", "preregistered_seeds": True, "files": []}
        )
    )
    monkeypatch.setattr(B, "tag_exists", lambda: False)
    assert (
        B.main(
            [
                "--block",
                "M3",
                "--instances",
                str(tmp_path),
                "--out",
                str(tmp_path / "o"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "o").exists()


def test_ids_unique_across_blocks(monkeypatch):
    monkeypatch.setattr(B, "feasible", lambda inst, k: True)
    insts = fake(["H1", "H2a"])
    ids = [
        j["id"] for b in ("M3", "M5", "M6", "M8") for j in B.build(b, insts, "/tmp/x")
    ]
    assert len(ids) == len(set(ids))  # the merged pool of the run plan needs this


def test_bridge_block(monkeypatch):
    monkeypatch.setattr(B, "feasible", lambda inst, k: True)
    dev = [
        dict(
            dataset="/nonexistent",
            instance=f"n{n}_m{2 * n}_s{s}.txt",
            family="Development",
            param=2,
            n=n,
            m=2 * n,
            seed=s,
        )
        for n in (25, 50)
        for s in (1, 2, 3)
    ]
    jobs = B.build("bridge", dev, "/tmp/x")
    assert sum(len(j["configs"]) for j in jobs) == 24  # the submitted 24 runs
    assert {j["max_ms"] for j in jobs} == {200_000}
    held = B.build("bridge", fake(["H1"]), "/tmp/x")
    assert (
        sum(len(j["configs"]) for j in held) == 2 * 10 * 2 * 2
    )  # H1 n 25, 50 at m/n 2
