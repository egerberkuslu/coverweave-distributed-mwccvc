"""r1_run: one job end to end, restart, infeasible witness, loss label pass-through."""
import csv
import json
import os

import pytest

from ccvc.bb import r1_run
from ccvc.bb import sweep as S

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(S.__file__))))

# 6 nodes, 12 edges: a 6-cycle, its three long diagonals and three chords.
EDGES = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5),
         (0, 3), (1, 4), (2, 5), (0, 2), (2, 4), (1, 3)]  # fmt: skip
WEIGHTS = [3.5, 2.0, 4.25, 1.5, 2.75, 3.0]


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("BB_SNAPSHOT", ROOT)
    data = tmp_path / "data"
    data.mkdir()
    lines = [f"{i} {w}" for i, w in enumerate(WEIGHTS)] + [f"{u} {v}" for u, v in EDGES]
    (data / "tiny.txt").write_text("\n".join(lines) + "\n")
    base = dict(
        id="j1", dataset=str(data), instance="tiny.txt", group="small", n=6, m=12,
        ratio=2, seed=1, k=3, loss=0.0, rng_seed=7,
        configs=[["MIS-Connector-Backbone", "sync"], ["MIS-Connector-Backbone", "async"]],
        max_ms=60_000, mis_nbrs_max=32, out=str(tmp_path / "parts" / "j1.csv"),
    )  # fmt: skip

    def run(**over):
        j = {**base, **over}
        path = tmp_path / "jobs.jsonl"
        path.write_text(json.dumps(j) + "\n")
        rc = r1_run.main(["--jobs", str(path), "--id", j["id"]])
        rows = []
        if os.path.exists(j["out"]):
            with open(j["out"], newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        return rc, rows, j["out"]

    return run


def test_one_job_end_to_end_at_k3_and_restart(job):
    rc, rows, out = job()
    assert rc == 0 and os.path.exists(out + ".done")
    assert [(r["variant"], r["scheduler"]) for r in rows] == [
        ("MIS-Connector-Backbone", "sync"),
        ("MIS-Connector-Backbone", "async"),
    ]
    for r in rows:
        assert (r["k"], r["loss"], r["seed"], r["rng_seed"]) == ("3", "0.0", "1", "7")
        assert r["code_fingerprint"] == S.code_fingerprint()
        assert r["instance_feasible"] == "yes" and r["status"] == "ok"
        assert r["params"] == ""
    rc, again, _ = job()
    assert rc == 0 and again == rows, "a finished job must not re-measure"


def test_infeasible_instance_runs_one_witness_config(job):
    rc, rows, _ = job(k=1, max_ms=5_000)
    assert rc == 0
    assert len(rows) == 1 and rows[0]["instance_feasible"] == "no"


def test_all_configs_on_infeasible_runs_every_config(job):
    rc, rows, _ = job(k=1, max_ms=5_000, all_configs_on_infeasible=True)
    assert rc == 0 and len(rows) == 2
    assert {r["instance_feasible"] for r in rows} == {"no"}


def test_params_reach_the_run_and_the_params_column(job):
    with pytest.raises(S.ParamsOverrideError):
        job(params={"no_such_field": 1})
    rc, rows, _ = job(params={"gap_patience": 4})
    assert rc == 0 and {r["params"] for r in rows} == {'{"gap_patience": 4}'}


def test_a_frozen_fingerprint_that_differs_is_refused(job, monkeypatch):
    monkeypatch.setenv("R1_FROZEN_FINGERPRINT", "000000000000")
    rc, rows, _ = job()
    assert rc == 2 and rows == []
    monkeypatch.setenv("R1_FROZEN_FINGERPRINT", S.code_fingerprint())
    assert job()[0] == 0


def test_loss_label_and_rng_seed_reach_the_run_request(job, monkeypatch):
    seen = []

    def run(req):
        seen.append(req)
        raise RuntimeError("recorded")

    spec = S.VariantSpec("Probe", "probe", "mis", "local", run)
    monkeypatch.setattr(S, "discover", lambda: [spec])
    rc, rows, _ = job(loss="ge:0.10:4", rng_seed=11, configs=[["Probe", "sync"]])
    assert rc == 0
    assert (seen[0].loss, seen[0].seed) == ("ge:0.10:4", 11)
    assert (rows[0]["loss"], rows[0]["rng_seed"], rows[0]["status"]) == (
        "ge:0.10:4", "11", "error")  # fmt: skip


def test_guards(job, monkeypatch):
    rc, rows, _ = job(configs=[["No-Such-Arm", "sync"]])
    assert rc == 4 and rows == []
    monkeypatch.setenv("BB_SNAPSHOT", "/nonexistent")
    assert job()[0] == 2
