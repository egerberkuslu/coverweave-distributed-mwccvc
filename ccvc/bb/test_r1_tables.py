"""Section V generators (r1_tables, r1_figures) on synthetic rows only."""

import json
import re

import pytest

from ccvc.bb import r1_figures as F
from ccvc.bb import r1_tables as T

P, B = T.PRIMARY, T.BASELINE
MIS = "MIS-Connector-Backbone/async"
N_INST = 8


def row(arm, inst, weight=None, n=10, m=20, k=6, **kw):
    variant, sched = arm.split("/")
    base = dict(
        instance=inst,
        variant=variant,
        scheduler=sched,
        n=str(n),
        m=str(m),
        k=str(k),
        loss="0.0",
        params="",
        group="H1",
        infeasible="False",
        instance_feasible="yes",
        status="ok",
        verdict="solved",
        valid="True",
        valid_discovered="True",
        total_weight="" if weight is None else str(weight),
        cover_size="5",
        exact_status="skipped:n>18",
        exact_weight="",
        tx="100",
        rx="300",
        bytes_tx="2000",
        max_payload="23",
        slots="40",
        mis_depth="",
        restarts="0",
        state_bytes_max="64",
        radio_activity_mJ_proxy="1.5",
        planned_missing="0",
        double_claims="0",
        weight_scale="10",
    )
    base.update({k_: str(v) for k_, v in kw.items()})
    return base


def info_for(insts, m=20, lp=lambda i: 80.0 + i):
    return {
        (f"i{i}", 6): {
            "n": 10,
            "m": m,
            "w_all": 300.0,
            "lp_status": "optimal",
            "lp": lp(i),
            "path": "",
        }
        for i in insts
    }


def quality_block(group="H1", primary_lower=True):
    """Eight free instances; the primary arm is lighter on all of them, or tied in sign."""
    rows = []
    for i in range(N_INST):
        d = 10 + i if primary_lower else (5 + i) * (1 if i % 2 else -1)
        rows += [
            row(
                P, f"i{i}", 100 + i, group=group, exact_status="ok", exact_weight=90 + i
            ),
            row(B, f"i{i}", 100 + i + d, group=group),
            row(MIS, f"i{i}", 130 + 3 * i, group=group),
        ]
    # one instance forced to C = V, one without any cover
    rows += [row(a, "f1", 300, m=60, group=group) for a in (P, B, MIS)]
    rows.append(
        row(
            P,
            "x1",
            n=10,
            m=50,
            status="infeasible",
            verdict="unresolved",
            valid="False",
            infeasible="True",
            instance_feasible="no",
            group=group,
        )
    )
    info = info_for(range(N_INST))
    info[("f1", 6)] = {
        "n": 10,
        "m": 60,
        "w_all": 300.0,
        "lp_status": "optimal",
        "lp": 300.0,
        "path": "",
    }
    info[("x1", 6)] = {
        "n": 10,
        "m": 50,
        "w_all": 300.0,
        "lp_status": "infeasible",
        "lp": None,
        "path": "",
    }
    return T.Block(rows, info, T.optima_of(rows), {})


def captions_ok(tex):
    cap = re.search(r"\\caption\{(.*?)\}\n", tex).group(1)
    sentences = [s for s in re.split(r"(?<=[a-z0-9}])\.\s", cap) if s.strip()]
    assert len(sentences) <= 2, cap
    assert ".txt" not in tex and "seed" not in tex.lower() and "_s1" not in tex
    assert tex.count(r"\toprule") == 1 and r"\bottomrule" in tex


def test_prepare_scopes_by_instance_feasibility():
    # An arm that ends Unresolved on a flow-infeasible instance is not a feasible run.
    r = T.prepare(
        [
            row(
                P,
                "x",
                status="unresolved",
                verdict="unresolved",
                valid="False",
                infeasible="False",
                instance_feasible="no",
            )
        ]
    )[0]
    assert T.scope(r) == "infeasible"
    assert T.scope(T.prepare([row(P, "f", m=60)])[0]) == "forced"


def test_optima_from_rows_must_agree():
    rows = [
        row(P, "i0", 100, exact_status="ok", exact_weight=90),
        row(B, "i0", 110, exact_status="ok", exact_weight=91),
    ]
    with pytest.raises(SystemExit):
        T.optima_of(rows)


def test_quality_table_marks_only_supported_best():
    tex, macros = T.table_quality(quality_block())
    captions_ok(tex)
    assert "Trivial cover $C = V$" in tex and "opt., 8 inst." in tex
    line = next(l for l in tex.splitlines() if l.startswith("TemperFlux &"))
    assert r"\textbf{" in line  # lighter than FabricTree, NexusWarp and C = V on 8 of 8
    assert tex.count(r"\textbf{") == 1
    assert any("DevPrimaryRatioOpt" in m for m in macros)
    # mean of (100+i)/(90+i), i = 0..7, printed with two decimals
    mean = sum((100 + i) / (90 + i) for i in range(N_INST)) / N_INST
    assert f"{mean:.2f} [" in line
    tex2, _ = T.table_quality(quality_block(primary_lower=False))
    assert r"\textbf{" not in tex2


def test_heldout_table_reports_hb_per_family():
    tex, macros = T.table_heldout(
        {"H1": quality_block("H1"), "H2a": quality_block("H2a", False)}
    )
    captions_ok(tex)
    lines = [l for l in tex.splitlines() if l.startswith("10-25 & 8 & opt. &")]
    assert len(lines) == 2
    assert "{Path plus random edges}" in tex and "{Unit disk graph}" in tex
    assert lines[0].endswith("& met \\\\") and r"\textbf{" in lines[0]
    assert lines[1].endswith("& not met \\\\") and r"\textbf{" not in lines[1]
    assert r"\roneHbMet}{1}" in "".join(macros) and r"\roneHbTested}{2}" in "".join(
        macros
    )


def test_reliability_counts_false_success_and_witness():
    dev = quality_block("dev")
    dev.rows.append(
        row(
            MIS,
            "i0",
            1,
            valid="False",
            valid_discovered="False",
            status="contradiction",
            group="dev",
        )
    )
    held = quality_block("H1")
    m9 = T.Block(
        [
            row(
                a,
                f"z{a}",
                n=20,
                m=60,
                status=s,
                verdict=v,
                valid="False",
                infeasible=str(s == "infeasible"),
                instance_feasible="no",
                group="M9",
            )
            for a, s, v in (
                (P, "infeasible", "unresolved"),
                (B, "truncated", "truncated"),
                (MIS, "unresolved", "unresolved"),
            )
        ],
        {},
        {},
        {},
    )
    central = {
        ("i0", 6, "Greedy-Ratio-Upstream"): {"valid": "True", "weight": "95"},
        ("f1", 6, "Greedy-Ratio-Upstream"): {"valid": "False", "weight": ""},
    }
    held = held._replace(central=central)
    # a second held-out family shares the central dict, as by_family hands it out
    h2 = quality_block("H2a")
    rows2 = [{**r, "instance": "z" + r["instance"]} for r in h2.rows]
    info2 = {("z" + i, k): v for (i, k), v in h2.info.items()}
    other = T.Block(rows2, info2, T.optima_of(rows2), central)
    tex, macros = T.table_reliability(dev, [held, other], m9)
    captions_ok(tex)
    nexus = next(l for l in tex.splitlines() if l.startswith("NexusWarp &"))
    # dev: 8 + 1 free runs, one of them a false success; upper bound printed in percent
    assert "8/9" in nexus and "1 (" in nexus
    cen = next(l for l in tex.splitlines() if l.startswith("Centralized GRCCVC"))
    assert "1/1 & 0/1" in cen
    temper = next(l for l in tex.splitlines() if l.startswith("TemperFlux &"))
    assert temper.endswith(
        "3/3 & 1/1 & 0 \\\\"
    )  # witness on the three infeasible instances, M9 announced
    assert r"\roneNineAnnounced}{1}" in "".join(macros)
    assert r"\roneHeldFalseSucc}{0}" in "".join(macros)


def test_loss_table_orders_conditions_and_checks_hc():
    rows = []
    for cond, params in (
        ("ge:0.10:4", ""),
        ("0.0", ""),
        ("0.05", ""),
        ("ge:0.10:4", json.dumps({"adaptive_stale": False})),
    ):
        for i in range(4):
            bad = cond == "0.05" and i == 0
            rows += [
                row(
                    P,
                    f"i{i}",
                    100,
                    loss=cond,
                    params=params,
                    restarts=i,
                    slots=50 + i,
                    valid_discovered=str(not bad),
                    planned_missing=1 if bad else 0,
                ),
                row(B, f"i{i}", 110, loss=cond, params=params, double_claims=int(bad)),
                row(
                    "DFS-Spanning-Backbone/async",
                    f"i{i}",
                    120,
                    loss=cond,
                    params=params,
                    status="truncated",
                    verdict="truncated",
                ),
            ]
    tex, macros = T.table_loss(T.Block(rows, {}, {}, {}))
    captions_ok(tex)
    body = [l for l in tex.splitlines() if l.endswith("\\\\") and "&" in l][2:]
    assert [l.split(" & ")[0] for l in body] == ["0\\%", "5\\%", "10\\%", "10\\%"]
    groups = re.findall(r"\\multicolumn\{13\}\{@\{\}l\}\{(.*?)\}", tex)
    assert groups == [
        "Lossless",
        "Independent loss",
        "Gilbert-Elliott loss, mean burst 4",
        "Gilbert-Elliott loss, mean burst 4, fixed stale window",
    ]
    five = body[1].split(" & ")
    assert five[1] == "8" and five[2].startswith("87.5 [") and five[3] == "75.0"
    assert five[5] == "1" and five[9] == "1" and five[-1] == "0/4 \\\\"
    assert r"\roneLossWorstArmValid}{75.0}" in "".join(macros)
    rows[0]["valid_discovered"] = ""
    with pytest.raises(SystemExit):
        T.table_loss(T.Block(rows, {}, {}, {}))


def test_cost_table_medians_per_band():
    rows = [
        row("Anneal-Local/sync", f"i{i}", 100, tx=100 * (i + 1), mis_depth="")
        for i in range(3)
    ]
    rows += [
        row(
            "MIS-Connector-Backbone/sync",
            f"i{i}",
            120,
            mis_depth=i + 2,
            state_bytes_max=50 + i,
        )
        for i in range(3)
    ]
    rows.append(row(P, "i0", 100, tx=10**6))  # asynchronous: not in this table
    tex, macros = T.table_cost(T.Block(rows, {}, {}, {}))
    captions_ok(tex)
    temper = next(l for l in tex.splitlines() if "TemperFlux &" in l)
    assert temper.split(" & ")[2] == "200" and temper.split(" & ")[7] == "--"
    nexus = next(l for l in tex.splitlines() if "NexusWarp &" in l)
    assert nexus.split(" & ")[7] == "3" and r"\roneStateBytesMax}{64}" in "".join(
        macros
    )


def test_wireless_from_m7_rows_and_backend_guard(tmp_path):
    """M7 rows (E2 m7_rows.csv) with the ESP32 charge joined from run summaries."""
    (tmp_path / "runs" / "m7_dev_mst_a").mkdir(parents=True)
    (tmp_path / "runs" / "m7_dev_mst_a" / "summary.json").write_text(
        json.dumps({"totals": {"energy_mah_esp32_model": 0.45}})
    )
    charge = T.esp32_charge([str(tmp_path / "m7_rows.csv")])
    assert charge == {"m7_dev_mst_a": 0.45}
    common = dict(execution_backend="mininet-wifi", tx=300, max_payload=17)
    rows = [
        # valid on the discovered graph, not on the planned one: the radio lost a link
        row(
            "GHS-MST-Backbone/sync",
            "a",
            100,
            block="dev",
            run_id="m7_dev_mst_a",
            valid="False",
            planned_missing=2,
            **common,
        ),
        row(
            "GHS-MST-Backbone/sync", "w", 100, block="W", run_id="m7_W_mst_w", **common
        ),
        row(
            "Anneal-Local/sync",
            "w",
            90,
            block="W",
            run_id="m7_W_anneal_w",
            verdict="solved",
            valid="False",
            valid_discovered="False",
            **common,
        ),
    ]
    tex, _ = T.table_wireless(T.Block(rows, {}, {}, {}), charge)
    captions_ok(tex)
    assert "Published benchmark & FabricTree & 1 & 1/1 & 0/1 & 2.00 & 300" in tex
    assert "0.450" in tex
    assert "Unit disk graph & FabricTree & 1 & 1/1" in tex
    assert tex.index("Published benchmark &") < tex.index("Unit disk graph &")
    assert "\n & TemperFlux & 1 & 0/1 & 0/1" in tex
    rows[0]["execution_backend"] = "simulator"
    with pytest.raises(SystemExit):
        T.table_wireless(T.Block(rows, {}, {}, {}), charge)


def test_chain_length_known_graphs():
    # Path 1-2-3-4 with weights rising faster than degree: keys increase along it.
    assert F.chain_length({1: 1, 2: 10, 3: 20, 4: 40}, [(1, 2), (2, 3), (3, 4)]) == 3
    # Star with the lightest centre: every leaf is one step above it.
    assert F.chain_length({1: 1, 2: 50, 3: 60, 4: 70}, [(1, 2), (1, 3), (1, 4)]) == 1


def test_factor_effects_pairs_with_default():
    rows = []
    for i in range(3):
        rows.append(row("MIS-Connector-Backbone/sync", f"i{i}", 100))
        rows.append(
            row(
                "MIS-Connector-Backbone/sync",
                f"i{i}",
                110,
                params=json.dumps({"gap_patience": 8}),
            )
        )
        rows.append(
            row(
                "MIS-Connector-Backbone/sync",
                f"i{i}",
                100,
                params=json.dumps({"gap_patience": 1}),
                status="unresolved" if i == 0 else "ok",
            )
        )
    eff, changed = F.factor_effects(rows, info_for(range(3), lp=lambda i: 100.0))
    assert eff[("MIS-Connector-Backbone/sync", "gap_patience")] == {
        "8": pytest.approx(0.1),
        "1": 0.0,
    }
    assert changed == 1
    with pytest.raises(SystemExit):
        F.factor_effects(
            [row(P, "i0", 1, params=json.dumps({"alpha": 0.8, "t0_scale": 2}))], {}
        )


def _tiny_instance(path, n):
    """A path over n nodes plus one chord, in the published file format."""
    lines = [f"{v} {20 + 7 * v}.0" for v in range(n)]
    lines += [f"{v} {v + 1}" for v in range(n - 1)] + [f"0 {n - 1}"]
    path.write_text("\n".join(lines) + "\n")


def test_write_all_renders_every_asset(tmp_path):
    """End to end: tables, macros and figure files, figure height within 70 mm."""
    (tmp_path / "inst").mkdir()
    for i in range(N_INST):
        _tiny_instance(tmp_path / "inst" / f"i{i}", 10)
    dev, h1, h2 = quality_block("dev"), quality_block("H1"), quality_block("H2a", False)
    for b in (dev, h1, h2):
        for key, it in b.info.items():
            it["path"] = (
                str(tmp_path / "inst" / key[0]) if key[0].startswith("i") else ""
            )
        b.rows[:] = [r for r in b.rows if r["instance"].startswith("i")]
        for r in b.rows:
            if r["variant"] == "MIS-Connector-Backbone":
                r.update(scheduler="sync", mis_depth="2")
    m5_rows = [r for b in (h1,) for r in b.rows]
    m5 = T.Block(
        [{**r, "k": str(k)} for r in m5_rows for k in (3, 6)],
        {
            (i, k): {**it, "n": 10, "m": 20}
            for (i, _), it in h1.info.items()
            for k in (3, 6)
        },
        {},
        {},
    )
    m8 = []
    for i in range(N_INST):
        for g in ("H1", "H1-lognormal"):
            m8.append(row("Anneal-Local/async", f"i{i}", 100 + i, group=g))
        m8.append(
            row(
                "Anneal-Local/async",
                f"i{i}",
                104 + i,
                params=json.dumps({"alpha": 0.8}),
            )
        )
    m8b = T.Block(m8, info_for(range(N_INST)), {}, {})
    blocks = {"M2": dev, "M5": m5, "M8": m8b}
    wrote = T.write_all(blocks, str(tmp_path / "tables"), str(tmp_path / "figs"))
    names = {p.rsplit("/", 1)[1] for p in wrote}
    stems = (
        "quality_dev",
        "quality_key",
        "sens_tightness",
        "sens_factors",
        "sens_weights",
        "sens_key",
        "chain",
    )
    for stem in stems:
        assert {f"{stem}.png", f"{stem}.svg", f"{stem}.pdf"} <= names
        h, w = F.plt.imread(str(tmp_path / "figs" / f"{stem}.png")).shape[:2]
        assert h / 200 <= 70 / 25.4 + 1e-6
    assert {"quality.tex", "cost.tex", "reliability.tex", "numbers.tex"} <= names
    numbers = (tmp_path / "tables" / "numbers.tex").read_text()
    assert (
        r"\roneLMax}{9}" in numbers
        and r"\roneRMax}{2}" in numbers
        and r"\roneRAboveL}{0}" in numbers
    )
