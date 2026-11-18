#!/usr/bin/env python3
"""CCVC deney koşucusu (F5). Eşleştirilmiş, çok tohumlu, doğrulama kapılı.

Koş:
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m ccvc.experiment \
      --frames results/mds_campus_seed0_frames.json --name kampus_drone \
      --ks 2,3,4,6 --weights unit,random --seeds 3 --stride 5

Disiplin (plan/PLAN_DCCVC.md §6):
  * EŞLEŞTİRİLMİŞ: bütün çözücüler AYNI çizge üstünde koşar, ayrı koşum yok.
  * ÇOK TOHUMLU: tohum ağırlık atamasını ve rastgele bileşenleri değiştirir.
  * DOĞRULAMA KAPISI: her sonuç üç kapıdan geçirilir; geçmeyen "sonuç" değil, hata.
  * DÜRÜST UYGUNSUZLUK: k çok küçükse çözüm yoktur; bu kaydedilir, gizlenmez.
  * TAM ÇÖZÜM yalnız küçük bileşenlerde koşar, üst sınır olarak.

Dağıtık kollar (d_repair, d_cds) varsa otomatik eklenir; yoksa merkezi kısım
tek başına koşar ve eksik kol raporda açıkça belirtilir.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import bridge, central
from .bridge import CcvcGraph

# --------------------------------------------------------------------------
# çözücü kaydı: merkezi her zaman, dağıtık varsa
# --------------------------------------------------------------------------
EXACT_MAX_COMPONENT = (
    18  # gerçek karelerde dev bileşen 16 düğüm; 14'te tam çözüm hiç koşmuyordu
)
EXACT_TIME_LIMIT_S = 5.0


@dataclass
class SolverSpec:
    """Bir çözücü kolu. `run(graph) -> (cover, extra)`; extra mesaj/tur taşır."""

    name: str
    kind: str  # "central" | "distributed" | "exact" | "trivial"
    run: Callable[[CcvcGraph], Tuple[Optional[List[int]], Dict[str, Any]]]


def _central_spec(algo: str) -> SolverSpec:
    def run(g: CcvcGraph):
        r = central.solve(algo, g)
        cover = list(getattr(r, "cover", []) or [])
        return cover, {"feasible": True}

    return SolverSpec(name=algo, kind="central", run=run)


def _exact_spec() -> SolverSpec:
    def run(g: CcvcGraph):
        comps = bridge.graph_components(g)
        if any(len(c) > EXACT_MAX_COMPONENT for c in comps):
            return None, {"skipped": "bileşen çok büyük"}
        r = central.solve_exact(
            g, max_n=EXACT_MAX_COMPONENT, time_limit_s=EXACT_TIME_LIMIT_S
        )
        cover = list(getattr(r, "cover", []) or [])
        return cover, {"timed_out": bool(getattr(r, "timed_out", False))}

    return SolverSpec(name="exact", kind="exact", run=run)


def _trivial_spec() -> SolverSpec:
    """Üst sınır: kenarı olan her düğüm örtüde. Her zaman geçerli, her zaman kötü."""

    def run(g: CcvcGraph):
        return [v for v in g.nodes if g.degree(v) > 0], {}

    return SolverSpec(name="all_nodes", kind="trivial", run=run)


def _distributed_specs() -> List[SolverSpec]:
    """d_repair / d_cds modülleri varsa kollarını ekler; yoksa boş liste."""
    out: List[SolverSpec] = []
    for mod_name, factory_names in (("d_repair", None), ("d_cds", None)):
        try:
            mod = __import__(f"ccvc.{mod_name}", fromlist=["*"])
        except Exception:
            continue
        # modül kendi kollarını `SPECS` ile bildirebilir: [(ad, callable(graph)->RunResult)]
        specs = getattr(mod, "SPECS", None)
        if not specs:
            continue
        for label, fn in specs:

            def run(g: CcvcGraph, _fn=fn):
                rr = _fn(g)
                extra = {
                    "rounds": getattr(rr, "rounds", None),
                    "messages": getattr(rr, "messages", None),
                    "converged": getattr(rr, "converged", None),
                }
                return list(getattr(rr, "cover", []) or []), extra

            # Oracle = aynı stratejinin tam bilgili sürümü; mesaj üretmez ve
            # dağıtık sayılmamalıdır, yoksa sıfır-mesajlı bir kol dağıtık mesaj
            # maliyetinin ortalamasına karışır. (f3-repair bildirdi, 2026-09-11)
            kind = (
                "oracle" if ("central" in label or "oracle" in label) else "distributed"
            )
            out.append(SolverSpec(name=label, kind=kind, run=run))
    return out


def build_solvers() -> List[SolverSpec]:
    specs = [_central_spec(a) for a in ("gccvc", "grccvc", "gwccvc")]
    specs += _distributed_specs()
    specs.append(_exact_spec())
    specs.append(_trivial_spec())
    return specs


# --------------------------------------------------------------------------
# tek koşum
# --------------------------------------------------------------------------
@dataclass
class Row:
    frame: int
    k: int
    weight_scheme: str
    seed: int
    solver: str
    kind: str
    n: int
    m: int
    components: int
    isolated: int
    cover_size: Optional[int]
    total_weight: Optional[float]
    valid: bool
    vertex_cover: bool
    connected: bool
    capacity_feasible: bool
    rounds: Optional[int]
    messages: Optional[int]
    seconds: float
    status: str  # ok | infeasible | skipped | error
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def run_one(g: CcvcGraph, spec: SolverSpec, meta: Dict[str, Any]) -> Row:
    """Tek çözücüyü tek çizgede koş, üç kapıdan geçir, satır üret."""
    t0 = time.perf_counter()
    status, detail, cover, extra = "ok", "", None, {}
    try:
        cover, extra = spec.run(g)
        if cover is None:
            status = "skipped"
            detail = str(extra.get("skipped", ""))
    except central.CcvcInfeasible as exc:
        status, detail = "infeasible", str(exc)[:120]
    except Exception as exc:  # noqa: BLE001 — dürüst kayıt
        status, detail = "error", f"{type(exc).__name__}: {exc}"[:160]
    dt = time.perf_counter() - t0

    if cover is None:
        v = None
    else:
        v = bridge.verify(g, cover)
        if not v.valid and status == "ok":
            status = "gate_fail"
            detail = f"vc={v.vertex_cover} conn={v.connected} cap={v.capacity_feasible}"

    comps = bridge.graph_components(g)
    return Row(
        frame=meta["frame"],
        k=g.capacity_k,
        weight_scheme=meta["weight_scheme"],
        seed=meta["seed"],
        solver=spec.name,
        kind=spec.kind,
        n=len(g.nodes),
        m=len(g.edges),
        components=sum(1 for c in comps if len(c) > 1),
        isolated=sum(1 for c in comps if len(c) == 1),
        cover_size=(None if v is None else v.cover_size),
        total_weight=(None if v is None else round(v.total_weight, 4)),
        valid=(False if v is None else v.valid),
        vertex_cover=(False if v is None else v.vertex_cover),
        connected=(False if v is None else v.connected),
        capacity_feasible=(False if v is None else v.capacity_feasible),
        rounds=extra.get("rounds"),
        messages=extra.get("messages"),
        seconds=round(dt, 5),
        status=status,
        detail=detail,
    )


# --------------------------------------------------------------------------
# süpürme
# --------------------------------------------------------------------------
def sweep(
    frames: Sequence[dict],
    ks: Sequence[int],
    weight_schemes: Sequence[str],
    seeds: Sequence[int],
    solvers: Sequence[SolverSpec],
    stride: int = 1,
    edge_field: str = "edges_obs",
    progress: bool = True,
) -> List[Row]:
    rows: List[Row] = []
    picked = list(range(0, len(frames), stride))
    total = len(picked) * len(ks) * len(weight_schemes) * len(seeds)
    done = 0
    for fi in picked:
        for k in ks:
            for ws in weight_schemes:
                for sd in seeds:
                    g = bridge.graph_from_frame(
                        frames[fi],
                        capacity_k=k,
                        weight_scheme=ws,
                        edge_field=edge_field,
                        seed=sd,
                    )
                    meta = {"frame": fi, "weight_scheme": ws, "seed": sd}
                    for spec in solvers:  # EŞLEŞTİRİLMİŞ: aynı g nesnesi
                        rows.append(run_one(g, spec, meta))
                    done += 1
                    if progress and done % 25 == 0:
                        print(f"  {done}/{total} yapılandırma", flush=True)
    return rows


# --------------------------------------------------------------------------
# özet
# --------------------------------------------------------------------------
def summarize(rows: Sequence[Row]) -> Dict[str, Any]:
    """Çözücü ve k başına ortalama ± standart sapma, geçerlilik ve tam çözüme oran.

    HAYATTA KALMA YANLILIĞI UYARISI (f4-cds bulgusu, 2026-09-11).
    Bir kolun başarısızlığı "kötü oran" olarak GÖRÜNMEZ; örnek kapıdan düşer ve
    oran ortalamasından tamamen çıkar. Yani çok düşen bir kol, sağ kalan kolay
    örnekler üstünde haksız biçimde iyi görünür. Bu yüzden iki oran raporlanır:

      ratio_to_exact_*        kolun kendi geçerli örneklerinde (yanlı olabilir)
      ratio_common_*          TÜM kolların geçerli olduğu ORTAK altkümede (yansız)

    Karşılaştırma yapılırken `ratio_common_*` esas alınmalıdır; ikisi ayrışıyorsa
    fark doğrudan başarısızlık örüntüsünden geliyordur ve raporlanmalıdır.
    """
    by: Dict[Tuple[str, int], List[Row]] = {}
    for r in rows:
        by.setdefault((r.solver, r.k), []).append(r)

    # ÖRNEK-BAZLI UYGUNSUZLUK: her düğüm örtüde olsa bile kapasite kapısı düşüyorsa
    # o örneğin hiçbir çözümü yoktur. Bu bir kol başarısızlığı DEĞİLDİR; oran
    # ortalamalarından çıkarılır ve ayrı sayılır. (f4-cds bulgusu, 2026-09-11)
    infeasible_instances = {
        (r.frame, r.k, r.weight_scheme, r.seed)
        for r in rows
        if r.solver == "all_nodes" and not r.capacity_feasible
    }

    # tam çözümün referansı: (frame,k,ws,seed) -> ağırlık
    exact_ref: Dict[Tuple[int, int, str, int], float] = {
        (r.frame, r.k, r.weight_scheme, r.seed): r.total_weight
        for r in rows
        if r.solver == "exact" and r.status == "ok" and r.total_weight is not None
    }

    # ORTAK ALTKÜME: her kolun (exact dahil) geçerli çözüm ürettiği örnekler.
    # Hayatta kalma yanlılığına karşı yansız karşılaştırma tabanı.
    solver_names = {r.solver for r in rows}
    valid_keys: Dict[str, set] = {
        s: {
            (r.frame, r.k, r.weight_scheme, r.seed)
            for r in rows
            if r.solver == s and r.status == "ok" and r.valid
        }
        for s in solver_names
    }
    common: set = set.intersection(*valid_keys.values()) if valid_keys else set()
    common -= infeasible_instances

    out: Dict[str, Any] = {
        "_instances_provably_infeasible": len(infeasible_instances),
        "_common_subset_size": len(common),
        "_solvers": sorted(solver_names),
    }
    for (solver, k), rs in sorted(by.items()):
        feas = [
            r
            for r in rs
            if (r.frame, r.k, r.weight_scheme, r.seed) not in infeasible_instances
        ]
        ok = [r for r in feas if r.status == "ok" and r.valid]
        ratios, ratios_common = [], []
        for r in ok:
            key = (r.frame, r.k, r.weight_scheme, r.seed)
            ref = exact_ref.get(key)
            if ref and ref > 0 and r.total_weight is not None:
                ratios.append(r.total_weight / ref)
                if key in common:
                    ratios_common.append(r.total_weight / ref)
        msgs = [r.messages for r in ok if r.messages is not None]
        rnds = [r.rounds for r in ok if r.rounds is not None]
        entry = {
            # n = ÇÖZÜLEBİLİR örnek sayısı; kanıtlanabilir çözümsüzler dışarıda
            "n": len(feas),
            "valid": len(ok),
            "instance_infeasible": len(rs) - len(feas),
            "infeasible": sum(1 for r in feas if r.status == "infeasible"),
            "gate_fail": sum(1 for r in feas if r.status == "gate_fail"),
            "error": sum(1 for r in feas if r.status == "error"),
            "skipped": sum(1 for r in feas if r.status == "skipped"),
        }
        if ok:
            entry["cover_size_mean"] = round(
                statistics.mean(r.cover_size for r in ok), 3
            )
            entry["weight_mean"] = round(statistics.mean(r.total_weight for r in ok), 3)
            if len(ok) > 1:
                entry["weight_sd"] = round(
                    statistics.stdev(r.total_weight for r in ok), 3
                )
        if ratios:
            entry["ratio_to_exact_mean"] = round(statistics.mean(ratios), 4)
            entry["ratio_to_exact_max"] = round(max(ratios), 4)
            entry["n_ratio"] = len(ratios)
        if ratios_common:
            # YANSIZ oran: yalnız her kolun başarılı olduğu ortak altkümede
            entry["ratio_common_mean"] = round(statistics.mean(ratios_common), 4)
            entry["ratio_common_max"] = round(max(ratios_common), 4)
            entry["n_common"] = len(ratios_common)
        if msgs:
            entry["messages_mean"] = round(statistics.mean(msgs), 1)
        if rnds:
            entry["rounds_mean"] = round(statistics.mean(rnds), 2)
        out[f"{solver}@k{k}"] = entry
    return out


def write_outputs(
    rows: Sequence[Row], summary: Dict[str, Any], outdir: str, manifest: Dict[str, Any]
) -> None:
    os.makedirs(outdir, exist_ok=True)
    fields = list(Row.__annotations__.keys())
    with open(os.path.join(outdir, "rows.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r.as_dict())
    json.dump(
        {"manifest": manifest, "summary": summary},
        open(os.path.join(outdir, "summary.json"), "w"),
        indent=1,
        ensure_ascii=False,
    )
    print(f"yazıldı: {outdir}/rows.csv ({len(rows)} satır), {outdir}/summary.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--ks", default="2,3,4,6")
    ap.add_argument("--weights", default="unit,random")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--stride", type=int, default=5, help="her N'inci kare")
    ap.add_argument("--edge-field", default="edges_obs")
    ap.add_argument("--outdir", default="")
    a = ap.parse_args()

    frames, meta = bridge.load_frames(a.frames)
    solvers = build_solvers()
    dist = [s.name for s in solvers if s.kind == "distributed"]
    print(f"kare: {len(frames)}, çözücü: {[s.name for s in solvers]}")
    if not dist:
        print(
            "UYARI: dağıtık kol YOK (ccvc/d_repair.py, ccvc/d_cds.py bulunamadı). "
            "Yalnız merkezi referans koşuluyor."
        )

    ks = [int(v) for v in a.ks.split(",")]
    ws = a.weights.split(",")
    seeds = list(range(a.seeds))
    t0 = time.time()
    rows = sweep(
        frames, ks, ws, seeds, solvers, stride=a.stride, edge_field=a.edge_field
    )
    summary = summarize(rows)
    manifest = {
        "experiment": "CCVC-" + a.name,
        "frames_path": a.frames,
        "frames_total": len(frames),
        "stride": a.stride,
        "ks": ks,
        "weight_schemes": ws,
        "seeds": seeds,
        "edge_field": a.edge_field,
        "solvers": [s.name for s in solvers],
        "distributed_arms": dist,
        "exact_max_component": EXACT_MAX_COMPONENT,
        "source_meta": {k: v for k, v in meta.items() if k != "buildings"},
        "runtime_min": round((time.time() - t0) / 60, 2),
        "honest_note": (
            "model tabanlı çizge; RSSI kalibrasyonu emülatörden, bina kaybı varsayım. "
            "Bağlılık BİLEŞEN BAZLI (çizge çoğu karede kopuk)."
        ),
    }
    outdir = a.outdir or os.path.join("results", "ccvc", a.name)
    write_outputs(rows, summary, outdir, manifest)

    print(
        f"\n{'çözücü@k':22s} {'geçerli':>9} {'|C|':>7} {'ağırlık':>9} {'tam-oran':>9} {'ORTAK':>9} {'mesaj':>8} {'tur':>6}"
    )
    print(
        f"(kanıtlanabilir çözümsüz örnek: {summary.get('_instances_provably_infeasible', 0)}, oranlardan çıkarıldı)"
    )
    for key, e in summary.items():
        if key.startswith("_"):
            continue
        print(
            f"{key:22s} {e['valid']:>4}/{e['n']:<4} {e.get('cover_size_mean','-'):>7} "
            f"{e.get('weight_mean','-'):>9} {e.get('ratio_to_exact_mean','-'):>9} "
            f"{e.get('ratio_common_mean','-'):>9} "
            f"{e.get('messages_mean','-'):>8} {e.get('rounds_mean','-'):>6}"
        )


if __name__ == "__main__":
    main()
