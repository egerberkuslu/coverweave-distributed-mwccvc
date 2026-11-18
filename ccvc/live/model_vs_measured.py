#!/usr/bin/env python3
"""Model ile ölçümü yan yana koyar. İki kipte çalışır.

KİP A (altyapı, salt okunur, şimdi koşulabilir):
    Havuzun GERÇEK konumlarını emu gRPC'den okur, her istasyonun ÖLÇÜLEN RSSI'sini
    okur ve kalibre modelin aynı konumda ne tahmin ettiğiyle karşılaştırır.
    Doğrudan sorusu: kalibrasyon hâlâ geçerli mi?

KİP B (ad-hoc, adhoc_measured.json gerektirir):
    ÖLÇÜLEN komşuluk çizgesini (karşılıklı ICMP) modelin aynı konumlarda
    öngördüğü çizgeyle karşılaştırır. Kenar bazında karışıklık matrisi üretir.
    Doğrudan sorusu: model çizgesi ölçülen çizgeyi ne kadar doğru veriyor?

Koş:
  /home/ege/cornet-mcp/.venv/bin/python ccvc/live/model_vs_measured.py --mode infra
  python3 ccvc/live/model_vs_measured.py --mode adhoc --adhoc results/live/adhoc_measured.json
"""
from __future__ import annotations

import argparse, json, math, os, re, subprocess, sys, time

# --- KANONİK KALİBRASYON ---------------------------------------------------
# 2026-09-11: bu modül kılavuz belgesindeki A=-28.76 / B=32.43 katsayılarını
# kullanıyordu. O katsayılar HATALI: ham veriye x koordinatı mesafe sayılarak
# uydurulmuş, oysa istasyon (x,4,10) ve AP (0,2,0), yani gerçek ayrım 3B'dir.
# Kanonik kaynak cornet-mcp/tools/calibrate_rssi.py, gerçek mesafelere uydurulmuş:
#   A = -15.129, B = 40.364, n = 4.036, R^2 = 0.99989, RMSE 0.145 dB
# Ölçümle doğrulandı: 6 canlı düğümde MAE 0.17 dB.
# Katsayı ARTIK BURAYA YAZILMIYOR, kaynaktan çağrılıyor.
import sys as _sys
_sys.path.insert(0, "/home/ege/cornet-mcp/tools")
try:
    from calibrate_rssi import rssi_at as _canonical_rssi_at, A_FIT as A, B_FIT as B
except Exception:  # kanonik kaynak yoksa açıkça patla, sessizce yanlış sayı kullanma
    raise RuntimeError(
        "kanonik kalibrasyon okunamadı (cornet-mcp/tools/calibrate_rssi.py). "
        "Sabit katsayı ile devam ETMEK YASAK; kaynağı düzelt."
    )
AP_POS = (0.0, 2.0, 0.0)        # wifi_worker_pool.py: ap1 konumu


def rssi_at(d: float) -> float:
    return A - B * math.log10(max(d, 0.1))


def sh(cmd, timeout=20):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


# --------------------------------------------------------------- KİP A
def infra():
    sys.path.insert(0, "/home/ege/cornet-mcp")
    import grpc
    from cornet_mcp.nexus_pb import emulation_pb2 as pb, emulation_pb2_grpc as pbg

    stub = pbg.EmulationServiceStub(grpc.insecure_channel("127.0.0.1:50051"))
    devs = stub.ListDevices(pb.ListDevicesRequest(), timeout=10).devices
    pos = {}
    for d in devs:
        p = dict(d.properties).get("position")
        if p and d.name.startswith("worker-"):
            pos[d.name] = tuple(float(v) for v in p.split(","))

    # ÖLÇÜM: her işçinin RSSI'si
    meas = {}
    for c in sh("docker ps --format '{{.Names}}' | grep '^mn\\.'").splitlines():
        iface = sh(f"docker exec {c} sh -lc 'ls /sys/class/net | grep wlan | head -1'")
        if not iface:
            continue
        ip = sh(f"docker exec {c} sh -lc 'ip -4 addr show {iface}'")
        m = re.search(r"inet 10\.0\.0\.(\d+)", ip)
        if not m or int(m.group(1)) < 11:
            continue
        name = f"worker-{int(m.group(1)) - 10:02d}"
        link = sh(f"docker exec {c} sh -lc 'iw dev {iface} link'")
        if "Connected to" not in link:
            meas[name] = None
            continue
        s = re.search(r"signal:\s*(-?\d+)", link)
        meas[name] = float(s.group(1)) if s else None

    rows = []
    for name in sorted(set(pos) & set(meas)):
        if meas[name] is None:
            continue
        d = math.dist(pos[name], AP_POS)
        pred = rssi_at(d)
        rows.append({"node": name, "position": list(pos[name]), "distance_m": round(d, 2),
                     "rssi_measured": meas[name], "rssi_model": round(pred, 2),
                     "residual": round(meas[name] - pred, 2)})
    print(f"{'düğüm':10s} {'konum x':>8} {'mesafe':>8} {'ÖLÇÜLEN':>9} {'MODEL':>8} {'artık':>7}")
    for r in rows:
        print(f"{r['node']:10s} {r['position'][0]:8.1f} {r['distance_m']:8.2f} "
              f"{r['rssi_measured']:9.0f} {r['rssi_model']:8.1f} {r['residual']:+7.1f}")
    if rows:
        res = [r["residual"] for r in rows]
        mae = sum(abs(x) for x in res) / len(res)
        bias = sum(res) / len(res)
        print(f"\nn={len(rows)}  ortalama mutlak hata {mae:.2f} dB  yanlılık {bias:+.2f} dB  "
              f"en büyük |artık| {max(abs(x) for x in res):.1f} dB")
        out = {"mode": "infrastructure", "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "calibration": {"A": A, "B": B}, "ap_position": list(AP_POS),
               "rows": rows, "mae_db": round(mae, 3), "bias_db": round(bias, 3)}
        json.dump(out, open("results/live/model_vs_measured_infra.json", "w"), indent=1, ensure_ascii=False)
        print("yazıldı: results/live/model_vs_measured_infra.json")


# --------------------------------------------------------------- KİP B
def adhoc(path: str, thresholds):
    snap = json.load(open(path))
    pos = {int(k): v for k, v in snap["positions"].items() if v}
    measured = {tuple(sorted(e)) for e in snap["edges_measured"]}
    n = snap["n"]
    allp = [(i, j) for i in range(n) for j in range(i + 1, n) if i in pos and j in pos]
    print(f"ölçülen kenar {len(measured)} / olası {len(allp)}   (ad-hoc, karşılıklı ICMP)\n")
    print(f"{'eşik':>6} {'model kenar':>12} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4} "
          f"{'doğruluk':>9} {'F1':>6}")
    best = None
    for thr in thresholds:
        model = {(i, j) for i, j in allp if rssi_at(math.dist(pos[i], pos[j])) >= thr}
        tp = len(model & measured); fp = len(model - measured)
        fn = len(measured - model); tn = len(allp) - tp - fp - fn
        acc = (tp + tn) / len(allp) if allp else 0
        f1 = (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else 0
        print(f"{thr:>6} {len(model):>12} {tp:>4} {fp:>4} {fn:>4} {tn:>4} {acc:>9.3f} {f1:>6.3f}")
        if best is None or f1 > best[1]:
            best = (thr, f1, tp, fp, fn, tn, acc)
    print(f"\nen iyi eşik {best[0]} dBm: F1={best[1]:.3f}, doğruluk={best[6]:.3f}, "
          f"yanlış pozitif {best[3]}, yanlış negatif {best[4]}")
    json.dump({"mode": "adhoc", "source": path, "best_threshold_dbm": best[0],
               "f1": round(best[1], 4), "accuracy": round(best[6], 4),
               "false_positive": best[3], "false_negative": best[4],
               "measured_edges": len(measured), "possible_pairs": len(allp)},
              open("results/live/model_vs_measured_adhoc.json", "w"), indent=1, ensure_ascii=False)
    print("yazıldı: results/live/model_vs_measured_adhoc.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["infra", "adhoc"], required=True)
    ap.add_argument("--adhoc", default="results/live/adhoc_measured.json")
    ap.add_argument("--thresholds", default="-70,-75,-80,-85,-90")
    a = ap.parse_args()
    if a.mode == "infra":
        infra()
    else:
        adhoc(a.adhoc, [float(v) for v in a.thresholds.split(",")])


if __name__ == "__main__":
    main()
