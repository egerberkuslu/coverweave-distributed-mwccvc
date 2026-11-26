"""Repair F6: a doubly claimed edge makes a run invalid in every validator path.

`run.owner` is a dict and keeps one claim per edge, so `validate.validate`
passes a run in which both endpoints claim an edge (proof audit: three lost
HANDOVER_ACK copies). Each test takes a real, valid run, adds one double claim
to `double_claimed` and asks one validator path for its verdict:
`sweep.validate_run`, `sweep.run_one` and `sweep.sweep`, `r1_run`, and the two
`v5_wuli` helpers that validate. The annealing sampler validates without an
owner map (flow capacity), so it has no ownership to double.
"""

import csv
import dataclasses
import json
import os

from ccvc.bb import matrix, r1_run, v5_wuli, validate
from ccvc.bb import sweep as S

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(S.__file__))))
SMALL = S.SweepOptions(k=4, max_ms=600_000)
INST = S.synthetic_instance(matrix.Cell("small", 10, 2), 0)


def _doubled(run):
    """`run` with one edge of G[C] also claimed by its other endpoint."""
    cover = set(run.cover)
    e = next(e for e in sorted(run.owner) if set(e) <= cover)
    return dataclasses.replace(run, double_claimed={e: e})


BASE = S.builtin_variants()[0]
DOUBLED = S.VariantSpec(
    "Doubled",
    "bb",
    "mis",
    "local",
    lambda req: _doubled(BASE.run(req)),
    schedulers=("sync",),
)


def _req():
    return S.RunRequest(
        edges=INST.edges,
        weights=dict(INST.weights),
        k=SMALL.k,
        scheduler="sync",
        seed=INST.seed,
        max_ms=SMALL.max_ms,
    )


def test_validate_run_sees_what_the_owner_dict_hides():
    g = validate.make_graph(
        list(INST.edges), SMALL.k, dict(INST.weights), nodes=sorted(INST.weights)
    )
    run = BASE.run(_req())
    assert S.validate_run(g, run).valid, "the control run must be valid"
    bad = _doubled(run)
    assert validate.validate(g, bad.cover, bad.owner).valid, "the dict hides it"
    rep = S.validate_run(g, bad)
    assert not rep.valid
    assert [v.kind for v in rep.violations] == [S.DOUBLE_OWNER]


def test_run_one_and_sweep_count_a_double_claim_as_a_false_success():
    clean = S.run_one(INST, BASE, "sync", SMALL)
    assert (clean.status, clean.valid, clean.double_claims) == ("ok", True, 0)
    row = S.run_one(INST, DOUBLED, "sync", SMALL)
    assert (row.status, row.valid, row.double_claims) == ("contradiction", False, 1)
    assert row.violation_kinds.split("|") == [S.DOUBLE_OWNER]
    assert row.verdict_agrees.startswith("no:")
    rows = S.sweep([INST], [DOUBLED], schedulers=("sync",), opts=SMALL)
    assert S.summarize(rows)["Doubled/sync"]["false_success"] == 1


def test_r1_run_writes_a_double_claim_as_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("BB_SNAPSHOT", ROOT)
    monkeypatch.setattr(S, "discover", lambda: [DOUBLED])
    data = tmp_path / "data"
    data.mkdir()
    lines = [f"{v} {w}" for v, w in sorted(INST.weights.items())]
    (data / "inst.txt").write_text(
        "\n".join(lines + [f"{u} {v}" for u, v in INST.edges])
    )
    job = dict(
        id="d1",
        dataset=str(data),
        instance="inst.txt",
        group="small",
        n=10,
        m=len(INST.edges),
        ratio=2,
        seed=0,
        k=SMALL.k,
        loss=0.0,
        rng_seed=0,
        configs=[["Doubled", "sync"]],
        max_ms=SMALL.max_ms,
        mis_nbrs_max=32,
        out=str(tmp_path / "d1.csv"),
    )
    jobs = tmp_path / "jobs.jsonl"
    jobs.write_text(json.dumps(job) + "\n")
    assert r1_run.main(["--jobs", str(jobs), "--id", "d1"]) == 0
    with open(job["out"], newline="", encoding="utf-8") as fh:
        (row,) = list(csv.DictReader(fh))
    assert (row["status"], row["valid"], row["double_claims"]) == (
        "contradiction",
        "False",
        "1",
    )
    assert row["violation_kinds"] == S.DOUBLE_OWNER


def test_the_wuli_helpers_see_a_double_claim(monkeypatch):
    case = v5_wuli.Case(n=20, radius=0.38, seed=0)
    assert v5_wuli.run_case(case)["valid"], "the control run must be valid"
    real = v5_wuli.run_wuli
    monkeypatch.setattr(v5_wuli, "run_wuli", lambda *a, **kw: _doubled(real(*a, **kw)))
    out = v5_wuli.run_case(case)
    assert out["valid"] is False and out["violations"] == [S.DOUBLE_OWNER]
    rows = v5_wuli.chunk_divergence_sweep(chunk_words=(8,), seeds=(0,))
    assert [r["valid"] for r in rows] == [False]
