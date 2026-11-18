#!/usr/bin/env python3
"""AeroWeave ad-hoc (IBSS) mesh: GERÇEKTEN ÖLÇÜLEN komşuluk çizgesi.

Altyapı kipindeki temel sınırı çözer: tek AP varken istasyondan istasyona her
paket AP üzerinden gider, dolayısıyla erişilebilirlik mantıksal bir kliktir ve
işçi-işçi kenarı ÖLÇÜLEMEZ. Ad-hoc kipinde AP yoktur; iki düğüm ancak birbirini
gerçekten duyuyorsa haberleşir, yani kenar ÖLÇÜM olur.

ÖNKOŞUL — pazarlıksız:
  * NEXUS emülatörü DURDURULMUŞ olmalı (aynı mac80211_hwsim modülünü paylaşır)
  * sudo gerekir (host mn-wifi)
  * `mn -c` sonrası: sudo modprobe mac80211_hwsim radios=0

Koş (kullanıcı `!` ile):
  cd /home/ege/cornet-mcp && echo <şifre> | sudo -S .venv/bin/python \
      /home/ege/Desktop/MDS_SKYFABRIC/ccvc/live/adhoc_mesh.py --n 9 --spacing 15

KENAR ÖLÇÜTÜ: i -> j `ping -c3 -W1` %0 kayıpla dönüyorsa kenar vardır.
Bu gerçek 802.11 çerçevesinin gerçekten taşınıp taşınmadığını doğrudan yanıtlar.

TUZAKLAR (runbook §4.3, hepsi burada ele alındı):
  1. Ad-hoc arayüzde `iw dev link` SİNYAL VERMEZ, intf.rssi None'dır.
     RSSI eşikli kenar tanımı ad-hoc'ta KULLANILAMAZ -> erişilebilirlik kullanılır.
  2. net.start() sonrası ısınma ŞART: 3 sn bekle + çift yönlü ping, yoksa ilk
     ping %100 kayıp verir ve çizge yanlış boş görünür.
  3. wmediumd interference kipi çerçeve düşürebilir; tekrar sayısı 3.
"""
from __future__ import annotations

import argparse, json, math, os, sys, time


def build(n: int, spacing: float, altitude: float, prop_exp: float):
    from mn_wifi.net import Mininet_wifi
    from mn_wifi.link import wmediumd
    from mn_wifi.wmediumdConnector import interference

    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)
    cols = max(1, int(math.sqrt(n)))
    stas = []
    for i in range(n):
        x = 10.0 + (i % cols) * spacing
        y = 10.0 + (i // cols) * spacing
        stas.append(net.addStation(f"sta{i+1}", ip=f"10.0.0.{i+1}/8",
                                   position=f"{x},{y},{altitude}"))
    net.setPropagationModel(model="logDistance", exp=prop_exp)
    net.configureWifiNodes()
    for s in stas:
        net.addLink(s, cls=__import__("mn_wifi.link", fromlist=["adhoc"]).adhoc,
                    intf=f"{s.name}-wlan0", ssid="mesh", mode="g", channel=5,
                    ht_cap="HT40+")
    net.build()
    return net, stas


def warmup(stas, seconds: float = 3.0):
    """TUZAK 2: ısınma olmadan ilk ping %100 kayıp verir."""
    time.sleep(seconds)
    a, b = stas[0], stas[1]
    a.cmd(f"ping -c1 -W1 {b.IP()} >/dev/null 2>&1")
    b.cmd(f"ping -c1 -W1 {a.IP()} >/dev/null 2>&1")
    time.sleep(1.0)


def measure_edges(stas, count: int = 3):
    """ÖLÇÜM: karşılıklı ICMP erişilebilirliği. Simetri ayrıca kaydedilir."""
    n = len(stas)
    reach = [[None] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            out = stas[i].cmd(f"ping -c{count} -W1 {stas[j].IP()}")
            loss = 100.0
            for tok in out.split():
                if tok.endswith("%"):
                    try:
                        loss = float(tok[:-1]); break
                    except ValueError:
                        pass
            reach[i][j] = loss
    edges, asym = [], []
    for i in range(n):
        for j in range(i + 1, n):
            ok_ij = reach[i][j] is not None and reach[i][j] < 100.0
            ok_ji = reach[j][i] is not None and reach[j][i] < 100.0
            if ok_ij and ok_ji:
                edges.append((i, j))
            elif ok_ij or ok_ji:
                asym.append((i, j, reach[i][j], reach[j][i]))
    return edges, asym, reach


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=9)
    ap.add_argument("--spacing", type=float, default=15.0)
    ap.add_argument("--altitude", type=float, default=10.0)
    ap.add_argument("--prop-exp", type=float, default=3.5)
    ap.add_argument("--out", default="/home/ege/Desktop/MDS_SKYFABRIC/results/live/adhoc_measured.json")
    a = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("sudo gerekiyor (host mn-wifi)")

    from mininet.log import setLogLevel
    setLogLevel("warning")
    net, stas = build(a.n, a.spacing, a.altitude, a.prop_exp)
    try:
        net.start()
        warmup(stas)
        t0 = time.time()
        edges, asym, reach = measure_edges(stas)
        pos = {}
        for i, s in enumerate(stas):
            p = getattr(s, "position", None)
            pos[i] = [float(v) for v in p] if p else None
        snap = {
            "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": "ad-hoc (IBSS), NO access point",
            "n": a.n, "spacing": a.spacing, "altitude": a.altitude,
            "propagation": {"model": "logDistance", "exp": a.prop_exp},
            "edge_criterion": "mutual ICMP reachability, ping -c3 -W1, loss < 100%",
            "measured": ["pairwise ICMP reachability"],
            "note_rssi": "ad-hoc arayüzde iw link sinyal vermez; RSSI eşiği kullanılamaz",
            "positions": pos,
            "edges_measured": edges,
            "asymmetric_links": asym,
            "loss_matrix": reach,
            "measure_seconds": round(time.time() - t0, 1),
        }
        json.dump(snap, open(a.out, "w"), indent=1, ensure_ascii=False)
        print(f"ÖLÇÜLEN kenar: {len(edges)} / olası {a.n*(a.n-1)//2}")
        print(f"asimetrik link: {len(asym)}")
        print("yazıldı:", a.out)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
