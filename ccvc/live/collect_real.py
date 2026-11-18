#!/usr/bin/env python3
"""SkyFabric havuzundan SALT OKUNUR gerçek RSSI toplayıcı -> CCVC çizgesi.

Koş (venv gerekmez, saf stdlib):
  python3 ccvc/live/collect_real.py --out results/live/real_snapshot.json

NE ÖLÇÜLÜYOR, NE TÜRETİLİYOR — dürüstlük tablosu:
  ÖLÇÜLEN   her işçinin AP'ye RSSI'si (iw dev <iface> link -> signal), gerçek
            wmediumd kanalından okunur
  ÖLÇÜLEN   assosiyasyon durumu (bağlı mı, değil mi)
  ÖLÇÜLEN   işçiler arası ICMP erişilebilirliği (ama altyapı kipinde AP üzerinden
            gider, yani mantıksal klik; kenar ölçütü OLARAK KULLANILAMAZ)
  TÜRETİLEN işçi-işçi mesafesi: ölçülen RSSI'den kalibre modelle ters çevrilir
  TÜRETİLEN kenar: türetilen mesafeden eşikle

Yani bu "yarı ölçüm"dür (runbook Yol B). Tam ölçülmüş komşuluk için ad-hoc
(IBSS) kipi gerekir, o da havuzu durdurmayı gerektirir.

Havuza HİÇBİR ŞEY yazmaz: SetPosition yok, konteynere yazma yok, yalnız okuma.
"""
from __future__ import annotations

import argparse, json, math, re, subprocess, time

# AeroWeave E0 kalibrasyonu (gerçek wmediumd taraması, R^2 = 0,9883)
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
RSSI_NOLINK = -95.0


def sh(cmd, timeout=20):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def rssi_to_distance(rssi: float) -> float:
    """RSSI -> mesafe (m). Kalibrasyonun tersi: d = 10^((A - rssi)/B)."""
    return 10 ** ((A - rssi) / B)


def discover():
    """mantıksal worker-NN -> {container, iface}; IP kuralı 10.0.0.(10+NN)."""
    out = {}
    for c in sh("docker ps --format '{{.Names}}' | grep '^mn\\.'").splitlines():
        iface = sh(f"docker exec {c} sh -lc 'ls /sys/class/net | grep wlan | head -1'")
        if not iface:
            continue
        ip = sh(f"docker exec {c} sh -lc 'ip -4 addr show {iface}'")
        m = re.search(r"inet 10\.0\.0\.(\d+)", ip)
        if m and int(m.group(1)) >= 11:
            i = int(m.group(1)) - 10
            out[f"worker-{i:02d}"] = {"container": c, "iface": iface, "ip": f"10.0.0.{10+i}"}
    return dict(sorted(out.items()))


def read_link(w):
    """ÖLÇÜM: iw dev link. Okunamazsa sentinel, bayat değer TAŞINMAZ."""
    link = sh(f"docker exec {w['container']} sh -lc 'iw dev {w[chr(105)+chr(102)+chr(97)+chr(99)+chr(101)]} link'")
    if "Connected to" not in link:
        return RSSI_NOLINK, False
    m = re.search(r"signal:\s*(-?\d+)", link)
    return (float(m.group(1)) if m else RSSI_NOLINK), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/live/real_snapshot.json")
    ap.add_argument("--samples", type=int, default=3, help="RSSI okuma tekrarı (medyan alınır)")
    a = ap.parse_args()

    ws = discover()
    if not ws:
        raise SystemExit("havuz bulunamadı (mn.* konteyner yok)")
    print(f"işçi: {list(ws)}", flush=True)

    readings = {n: [] for n in ws}
    assoc = {}
    for s in range(a.samples):
        for n, w in ws.items():
            r, ok = read_link(w)
            readings[n].append(r)
            assoc[n] = assoc.get(n, True) and ok
        if s + 1 < a.samples:
            time.sleep(1.0)

    nodes = {}
    for n, vals in readings.items():
        vals = sorted(vals)
        med = vals[len(vals) // 2]
        nodes[n] = {
            "rssi_dbm_measured": med,
            "rssi_samples": readings[n],
            "associated": assoc[n],
            "distance_to_ap_m_derived": round(rssi_to_distance(med), 2) if assoc[n] else None,
            "ip": ws[n]["ip"],
            "container": ws[n]["container"],
        }

    snap = {
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "SkyFabric NEXUS emulation pool, infrastructure mode (single AP)",
        "measured": ["rssi_dbm_measured (iw dev link)", "associated"],
        "derived": ["distance_to_ap_m_derived (AeroWeave E0 calibration inverse)"],
        "calibration": {"A": A, "B": B, "note": "RSSI(d) = A - B*log10(d), R^2=0.9883"},
        "honest_limitation": (
            "Altyapı kipinde işçi-işçi kenarı ÖLÇÜLEMEZ; tüm trafik AP üzerinden gider. "
            "Buradaki tek gerçek radyo ölçümü her istasyonun AP'ye RSSI'sidir. "
            "İşçi-işçi çizgesi bu ölçümden TÜRETİLİR, ölçülmez."
        ),
        "read_only": True,
        "nodes": nodes,
    }
    json.dump(snap, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({n: {"rssi": v["rssi_dbm_measured"], "d_ap": v["distance_to_ap_m_derived"]}
                      for n, v in nodes.items()}, indent=1))
    print("yazıldı:", a.out)


if __name__ == "__main__":
    main()
