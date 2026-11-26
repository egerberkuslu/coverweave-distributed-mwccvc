#!/usr/bin/env python3
"""Block M7 harness readiness. NO ROOT, NO MININET, NO HELD-OUT INSTANCE.

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest ccvc/bb/test_mnwifi_m7.py -q

Only development seeds are generated. The W manifest built here names the
registered (n, seed) pairs but holds no instance: `make_jobs` reads only the
manifest, and the sealed files are never generated or opened.
"""
from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from ccvc.bb import heldout, matrix  # noqa: E402
from ccvc.bb.api import Role  # noqa: E402
from ccvc.bb.bootstrap import hash16  # noqa: E402
from ccvc.bb.mnwifi import collect as collector  # noqa: E402
from ccvc.bb.mnwifi import m7, node_main  # noqa: E402
from ccvc.bb.mnwifi import run as runner_mod  # noqa: E402
from ccvc.bb.mnwifi import topology as topo  # noqa: E402
from ccvc.bb.mnwifi.udp_port import loopback_peers  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(m7.__file__)), "run_m7.sh")
DEV_SEEDS_FOR_TESTS = (1, 2)


def _w_manifest(**over):
    files = [
        {
            "file": f"W/deg6/n{n}_m{3 * n}_s{s}.txt",
            "family": "W",
            "deg": 6,
            "n": n,
            "m": 3 * n,
            "seed": s,
            "sha256": f"{n}-{s}",
        }
        for _, n, _, s in heldout.plan("W")
    ]
    doc = {"set": "W", "preregistered_seeds": True, "files": files}
    doc.update(over)
    return doc


# --------------------------------------------------------------------------
# 1. jobs
# --------------------------------------------------------------------------
def test_jobs_are_the_27_archived_runs_and_set_w_with_three_arms(tmp_path):
    dataset = matrix.dataset_dir()
    if dataset is None:
        pytest.skip("published dataset not present")
    w_set = tmp_path / "w"
    w_set.mkdir()
    (w_set / "manifest.json").write_text(json.dumps(_w_manifest()))
    jobs = m7.make_jobs(dataset, str(w_set), str(tmp_path / "out"))

    assert len(jobs) == 87 and len({j["id"] for j in jobs}) == 87
    dev = [j for j in jobs if j["block"] == "dev"]
    w = [j for j in jobs if j["block"] == "W"]
    assert len(dev) == 27 and len(w) == 60
    assert {(j["n"], j["m"], j["k"]) for j in dev} == {
        (10, 20, 6),
        (15, 90, 8),
        (20, 160, 12),
    }
    assert {j["seed"] for j in dev} == {1, 2, 3}
    assert {(j["n"], j["k"], j["max_ms"]) for j in w} == {
        (30, 6, 600_000),
        (50, 6, 600_000),
    }
    assert {j["seed"] for j in w} == set(range(401, 411))
    assert all(j["max_ms"] == 240_000 for j in dev)
    assert {j["node_kind"] for j in jobs} == {"bbcvc", "mst", "anneal"}
    assert all(
        j["mode"] == "sync" and j["wall_limit_s"] > j["max_ms"] / 1000 for j in jobs
    )
    assert all(j["sha256"] == f"{j['n']}-{j['seed']}" for j in w)


@pytest.mark.parametrize(
    "bad",
    [
        {"preregistered_seeds": False},
        {"set": "H2a"},
        {"files": _w_manifest()["files"][:-1]},
    ],
)
def test_a_w_set_that_is_not_the_registered_one_is_refused(bad):
    with pytest.raises(ValueError, match="set W"):
        m7.check_w_manifest(_w_manifest(**bad))


# --------------------------------------------------------------------------
# 2. topology generation and planning at the registered sizes (development seeds)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("n", [30, 50])
@pytest.mark.parametrize("seed", DEV_SEEDS_FOR_TESTS)
def test_w_family_instances_plan_at_m7_settings(tmp_path, n, seed):
    assert seed not in heldout.PREREGISTERED
    weights, edges, pos = heldout.generate_one("W", n, 6, seed)
    assert len(edges) == 3 * n and heldout._connected(n, edges)
    assert sorted(topo.realised_edges(pos, heldout.RADIO_RANGE_M)) == [
        (u + 1, v + 1) for u, v in edges
    ]

    path = tmp_path / f"n{n}_m{3 * n}_s{seed}.txt"
    path.write_text(heldout.instance_text(weights, edges))
    job = m7._arm_jobs(
        "W", str(path), "W", m7.W_K, m7.W_MAX_MS, str(tmp_path), m7._sha256(str(path))
    )[2]
    run_dir = m7.plan_job(job)
    meta = json.loads((tmp_path / "runs" / job["id"] / "run.json").read_text())
    assert run_dir.endswith(job["id"])
    assert (meta["n"], meta["m"], meta["k"], meta["max_ms"]) == (n, 3 * n, 6, 600_000)
    assert meta["radio_range_m"] == m7.RANGE_M and meta["node_kind"] == "anneal"
    deg = max(sum(1 for e in edges if v in e) for v in range(n))
    assert meta["mis_nbrs_max"] >= deg
    assert meta["channel"]["tau_ms"] >= meta["channel"]["t_hello_ms"] > 0
    assert len(meta["positions"]) == n


def test_plan_refuses_an_instance_whose_bytes_changed(tmp_path):
    weights, edges, _ = heldout.generate_one("W", 30, 6, 1)
    path = tmp_path / "n30_m90_s1.txt"
    path.write_text(heldout.instance_text(weights, edges))
    job = m7._arm_jobs("W", str(path), "W", 6, 1000, str(tmp_path), "0" * 64)[0]
    with pytest.raises(ValueError, match="sha256"):
        m7.plan_job(job)


@pytest.mark.parametrize("n", [30, 50, 200])
def test_addresses_and_ports_hold_at_the_node_count(n):
    peers = topo.assign_peers(range(1, n + 1))
    assert len({p.ip for p in peers.values()}) == n
    assert len({p.mac for p in peers.values()}) == n
    assert all(1 <= int(p.ip.rsplit(".", 1)[1]) <= 254 for p in peers.values())
    assert all(hash16(p.mac) == nid for nid, p in peers.items())
    # Linux IFNAMSIZ is 16 including the terminator.
    assert all(len(p.iface) <= 15 for p in peers.values())
    # One port for every station: each binds it inside its own namespace.
    assert {p.udp_port for p in peers.values()} == {47001}
    arp = topo.static_arp_commands(SimpleNamespace(peers=peers))
    assert sum(len(c) for c in arp.values()) == n * (n - 1)


# --------------------------------------------------------------------------
# 3. rows from station logs
# --------------------------------------------------------------------------
def _job(tmp_path):
    return m7._arm_jobs(
        "dev", "/data/n3_m2_s1.txt", "small", 2, 240_000, str(tmp_path), "f" * 64
    )[0]


def _write_run(job, ends, *, done=(1, 2, 3)):
    """Three stations on the planned path 1-2-3; `ends` gives each run_end."""
    run_dir = m7.run_dir_of(job)
    os.makedirs(run_dir)
    meta = {
        "edges": [[1, 2], [2, 3]],
        "weights": {"1": 1.0, "2": 5.0, "3": 1.0},
        "k": 2,
        "channel": {"tau_ms": 100},
        "mis_nbrs_max": 5,
        "code_fingerprint": "wifi-fp",
        "execution_backend": "mininet-wifi",
        "orchestrator_stop_ms": 2500,
    }
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    macs = {
        nid: topo.format_mac(topo.assign_peers([1, 2, 3])[nid].mac) for nid in (1, 2, 3)
    }
    for nid in (1, 2, 3):
        recs = [
            {"t_ms": 0, "event": "open", "mac": macs[nid]},
            {"t_ms": 1, "event": "run_start", "nid": nid},
            {
                "t_ms": 10 * nid,
                "event": "tx",
                "mtype": 0,
                "bytes": 13 + nid,
                "phase": 0,
            },
        ]
        recs += [
            {"t_ms": 40, "event": "rx", "src": macs[u], "mtype": 0, "bytes": 14}
            for u in (1, 2, 3)
            if u != nid
        ]
        if nid in done:
            recs.append({"t_ms": 300, "event": "node_done", "t_end_ms": 400})
        recs.append({"t_ms": 2000, "event": "run_end", **ends[nid]})
        with open(os.path.join(run_dir, f"{nid}.jsonl"), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in recs)
    return run_dir


def _end(role, owned, bidir, advance):
    return {"role": int(role), "owned": owned, "bidir": bidir, "epoch_advance": advance}


SOLVED = {
    1: _end(Role.OUT, [], [2], 0),
    2: _end(Role.MIS, [[1, 2], [2, 3]], [1, 3], 2),
    3: _end(Role.OUT, [], [2], 1),
}


def test_row_from_a_solved_run_carries_the_simulator_columns(tmp_path):
    job = _job(tmp_path)
    _write_run(job, SOLVED)
    row = m7.build_row(job, rc=0, fingerprint="r1-fp")
    assert tuple(row) == m7.COLUMNS
    assert row["status"] == "ok" and row["verdict"] == "solved"
    assert row["valid"] and row["valid_discovered"]
    assert (row["planned_missing"], row["discovered_extra"], row["double_claims"]) == (
        0,
        0,
        0,
    )
    assert (row["tx"], row["rx"], row["bytes_tx"], row["max_payload"]) == (3, 6, 45, 16)
    # slots: last DONE stamp 400 ms at tau 100 ms closes slot 3, so 5 slots.
    assert row["restarts"] == 2 and row["slots"] == 5 and row["total_weight"] == 5.0
    assert (row["code_fingerprint"], row["wifi_fingerprint"]) == ("r1-fp", "wifi-fp")
    assert (row["seed"], row["rng_seed"]) == (1, m7.LAYOUT_SEED)
    assert row["seconds"] == 2.5 and row["execution_backend"] == "mininet-wifi"


def test_a_doubly_owned_edge_is_a_false_success_on_the_discovered_graph(tmp_path):
    job = _job(tmp_path)
    _write_run(job, {**SOLVED, 1: _end(Role.OUT, [[1, 2]], [2], 0)})
    row = m7.build_row(job, rc=0, fingerprint="r1-fp")
    assert row["verdict"] == "solved" and row["status"] == "contradiction"
    assert (
        row["double_claims"] == 1 and not row["valid"] and not row["valid_discovered"]
    )
    assert "double_owner" in row["violation_kinds"]


def test_missing_and_extra_links_are_counted_against_the_plan(tmp_path):
    job = _job(tmp_path)
    # 2-3 is never verified both ways; 1-3, which the plan lacks, is.
    _write_run(
        job,
        {
            1: _end(Role.OUT, [], [2, 3], 0),
            2: _end(Role.MIS, [[1, 2]], [1], 0),
            3: _end(Role.OUT, [], [1], 0),
        },
    )
    row = m7.build_row(job, rc=0, fingerprint="r1-fp")
    assert (row["planned_missing"], row["discovered_extra"]) == (1, 1)
    assert not row["valid_discovered"] and row["status"] == "contradiction"


def test_a_run_that_hit_its_limit_keeps_its_costs(tmp_path):
    job = _job(tmp_path)
    _write_run(job, SOLVED, done=(1, 2))
    row = m7.build_row(job, rc=124, fingerprint="r1-fp")
    assert row["status"] == "truncated" and row["verdict"] == "truncated"
    assert row["tx"] == 3 and row["slots"] is None and row["harness_rc"] == 124
    assert "harness exit 124" in row["detail"]


def test_a_run_without_station_logs_is_an_error_row(tmp_path):
    job = _job(tmp_path)
    row = m7.build_row(job, rc=1, fingerprint="r1-fp")
    assert row["status"] == "error" and row["tx"] == ""
    assert "harness exit 1" in row["detail"] and row["run_id"] == job["id"]


def test_rows_append_once_and_an_interrupted_run_is_recorded_not_rerun(tmp_path):
    jobs = m7._arm_jobs(
        "dev", "/data/n3_m2_s1.txt", "small", 2, 240_000, str(tmp_path), "f" * 64
    )
    _write_run(jobs[0], SOLVED)
    by_id = {j["id"]: j for j in jobs}
    assert m7.todo(by_id, "r1-fp") == [j["id"] for j in jobs[1:]]
    with open(jobs[0]["rows"], newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == list(m7.COLUMNS) and len(rows) == 1
    assert rows[0]["run_id"] == jobs[0]["id"] and "interrupted" in rows[0]["detail"]
    assert m7.todo(by_id, "r1-fp") == [j["id"] for j in jobs[1:]]
    assert m7.done_ids(jobs[0]["rows"]) == {jobs[0]["id"]}


def test_a_real_station_process_reports_its_restarts(tmp_path, monkeypatch):
    """node_main's own run_end, over loopback, carries what the row reads."""
    monkeypatch.setattr(node_main.signal, "signal", lambda *a: None)
    peers = loopback_peers([1, 2], base_port=47901)
    (tmp_path / "peers.json").write_text(json.dumps(topo.peers_to_json(peers)))
    node_main.main(
        [
            "--peers",
            str(tmp_path / "peers.json"),
            "--log-dir",
            str(tmp_path),
            "--mac",
            topo.format_mac(peers[1].mac),
            "--weight",
            "3",
            "--k",
            "2",
            "--tau-ms",
            "50",
            "--t-hello-ms",
            "40",
            "--max-ms",
            "300",
            "--broadcast",
            "fanout",
        ]
    )
    logs = collector.read_run(str(tmp_path))
    advance = logs[1].last_of("run_end")["epoch_advance"]
    assert isinstance(advance, int)
    assert collector.counters_from_logs(logs, tau_ms=50, t0_ms=0).restarts == advance


# --------------------------------------------------------------------------
# 4. teardown and host checks
# --------------------------------------------------------------------------
class _Thing:
    def __init__(self, log, name, fail=False):
        self.log, self.name, self.fail = log, name, fail

    def stop(self):
        self.log.append(("stop", self.name))
        if self.fail:
            raise RuntimeError("link already gone")

    def terminate(self):
        self.log.append(("terminate", self.name))

    def __str__(self):
        return self.name


def test_teardown_touches_only_this_networks_processes_and_radios(
    tmp_path, monkeypatch
):
    log, commands, kills = [], [], []
    fake = ModuleType("mn_wifi.wmediumdConnector")
    fake.w_server = SimpleNamespace(disconnect=lambda: log.append(("disconnect", "w")))
    monkeypatch.setitem(sys.modules, "mn_wifi.wmediumdConnector", fake)
    monkeypatch.setattr(runner_mod, "_live_wmediumd_pids", lambda: [111, 222])
    monkeypatch.setattr(runner_mod, "_ppid", {111: 4242, 222: 1}.get)
    monkeypatch.setattr(
        runner_mod.os, "kill", lambda pid, sig: kills.append((pid, sig))
    )
    monkeypatch.setattr(
        runner_mod.subprocess,
        "run",
        lambda argv, **kw: (
            commands.append(argv),
            SimpleNamespace(returncode=0, stderr=""),
        )[1],
    )
    for phy in ("mn04242p00s00", "mn04242p00s01", "mn09999p00s00", "phy0"):
        (tmp_path / phy).mkdir()
        if phy.startswith("mn"):
            (tmp_path / phy / "hwsim").mkdir()
    monkeypatch.setattr(runner_mod, "HWSIM_DEBUGFS", str(tmp_path))
    net = SimpleNamespace(
        links=[_Thing(log, "l1", fail=True), _Thing(log, "l2")],
        stations=[_Thing(log, "sta1"), _Thing(log, "sta2")],
    )

    errors = runner_mod.scoped_stop(net, owner_pid=4242)

    assert log == [
        ("stop", "l1"),
        ("stop", "l2"),
        ("terminate", "sta1"),
        ("terminate", "sta2"),
        ("disconnect", "w"),
    ]
    assert kills == [(111, signal.SIGTERM)], "another network's wmediumd survives"
    assert commands == [
        ["hwsim_mgmt", "-x", "mn04242p00s00"],
        ["hwsim_mgmt", "-x", "mn04242p00s01"],
    ]
    assert errors == ["stop l1: link already gone"]
    banned = ("pkill", "killall", "rmmod", "mn")
    assert not any(c[0] in banned for c in commands)


def test_host_problems_name_every_reason_to_wait():
    assert (
        m7.host_problems(wmediumd=list, shells=list, load=lambda: (0.5,), cpus=16) == []
    )
    got = m7.host_problems(
        wmediumd=lambda: [7], shells=lambda: [8, 9], load=lambda: (6.0,), cpus=16
    )
    assert (
        len(got) == 3
        and "wmediumd" in got[0]
        and "[8, 9]" in got[1]
        and "6.00" in got[2]
    )


# --------------------------------------------------------------------------
# 5. the run script refuses to start without the frozen tag
# --------------------------------------------------------------------------
def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _run_script(tmp_path, release):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    marker = tmp_path / "sudo_called"
    sudo = bin_dir / "sudo"
    sudo.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    sudo.chmod(0o755)
    (tmp_path / "w").mkdir(exist_ok=True)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    res = subprocess.run(
        [
            "bash",
            SCRIPT,
            "--release",
            str(release),
            "--w-set",
            str(tmp_path / "w"),
            "--out",
            str(tmp_path / "out"),
        ],
        input="not-a-password\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return res, marker


def test_run_script_refuses_without_the_frozen_tag(tmp_path):
    repo = tmp_path / "release"
    repo.mkdir()
    res, marker = _run_script(tmp_path, repo)  # not a repository at all
    assert res.returncode == 2 and "coverweave-r1-frozen" in res.stderr

    _git(repo, "init", "-q")
    (repo / "README").write_text("x\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-qm", "init")
    res, marker = _run_script(tmp_path, repo)
    assert res.returncode == 2 and "annotated tag" in res.stderr

    _git(repo, "tag", "coverweave-r1-frozen")  # lightweight: not the frozen tag
    res, marker = _run_script(tmp_path, repo)
    assert res.returncode == 2 and "annotated tag" in res.stderr
    assert not marker.exists(), "sudo must not be reached"
    assert not (tmp_path / "out").exists(), "nothing may be written"


def test_every_job_runs_the_default_stale_window(tmp_path):
    """Second note to Amendment 15: F9 is the protocol under loss, so no arm overrides it."""
    path = tmp_path / "n10_m20_s1.txt"
    path.write_text("x")
    jobs = m7._arm_jobs("W", str(path), "W", 6, 1000, str(tmp_path), "0" * 64)
    assert len(jobs) == len(m7.ARMS)
    for j in jobs:
        assert m7.M7_PROFILE == {}
        assert "adaptive_stale" not in j["params"] and "stale_periods" not in j["params"]
    assert jobs[0]["params"]["enable_tree"] is False
