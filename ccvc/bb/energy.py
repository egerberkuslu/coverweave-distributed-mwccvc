"""Mininet-WiFi estimated energy: a model, never a measurement.

WHY THIS MODULE EXISTS. The project previously reported `energy_mah` from an
ESP32 radio model: 100 mA listening, 240 mA transmitting, 1 Mbps frame times.
The reference platform is now Mininet-WiFi, where a station is a Linux process
inside a network namespace. It has no radio and draws no current, so that number
measured nothing on the target platform while looking exactly like a measurement.

WHAT THIS MODULE DOES INSTEAD. It estimates the cost of running a station from
quantities the emulator can actually observe, keeps the components separate so a
reader can see which part came from where, and names every output so that the
caveat travels with the value rather than sitting in a docstring:

    mininet_wifi_energy_mJ_estimated   the combined model output
    cpu_energy_mJ_estimated            process CPU time component
    radio_activity_mJ_proxy            traffic component (tx/rx/retx)
    energy_model_version               so a stored row can be re-derived
    energy_model_coefficients          the assumptions, recorded with the run

WHAT IT IS NOT. It is not measured host electrical energy, not PHY airtime, and
not 802.11 MAC retry cost. Those require instrumentation this project does not
have. Four different things must never share a column:

    measured host electrical energy      not available here
    Mininet-WiFi process/traffic estimate  this module
    radio activity proxy                 a component of this module
    ESP32 energy model                    `api.Counters.energy_mah_esp32_model`

MISSING INPUTS ARE NOT ZERO. If `/proc/<pid>/stat` is unreadable, the CPU
component is `None` and the row reports `unavailable`, never 0.0. Writing zero
for an unmeasured quantity is how an absent measurement becomes a published one.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Dict, Mapping, Optional

#: Bump when a coefficient or the formula changes; stored rows record it so a
#: later reader can tell which model produced a number.
ENERGY_MODEL_VERSION = "mnwifi-proc-v1"

_CLK_TCK = float(os.sysconf("SC_CLK_TCK")) if hasattr(os, "sysconf") else 100.0


@dataclass(frozen=True)
class EnergyCoefficients:
    """Model assumptions. Defaults are DECLARED ESTIMATES, not measurements.

    Sources and reasoning, recorded because a coefficient without a source is
    indistinguishable from a coefficient that was invented:

    `cpu_power_mW`
        Order-of-magnitude figure for one busy core of a commodity x86 laptop
        CPU under the emulator, taken as a round 15 W / 8 threads. It scales the
        CPU-time component only. ASSUMPTION, not measured on this host.

    `idle_station_power_mW`
        A station that is alive but not computing still occupies a namespace and
        a scheduler slot. Set deliberately small so that wall-clock time does
        not dominate; its role is to keep a long idle run from looking free.

    `tx_cost_mJ_per_byte`, `rx_cost_mJ_per_delivery`, `retx_cost_mJ`
        Traffic components. These are PROXIES: in the emulator a byte does not
        cost radio energy, it costs kernel and userspace work. They make the
        traffic difference between arms visible on an energy-shaped axis, which
        is the only claim made for them.

    Change these per experiment if better numbers exist; they are recorded with
    every row, so two sweeps with different coefficients can never be silently
    compared.
    """

    cpu_power_mW: float = 1875.0
    idle_station_power_mW: float = 5.0
    tx_cost_mJ_per_byte: float = 2.0e-5
    rx_cost_mJ_per_delivery: float = 1.0e-3
    retx_cost_mJ: float = 5.0e-3


@dataclass
class StationEnergySample:
    """One station's observed inputs. `None` means NOT OBSERVED, never zero."""

    nid: int
    pid: Optional[int] = None
    cpu_user_ms: Optional[float] = None
    cpu_sys_ms: Optional[float] = None
    active_ms: Optional[float] = None
    tx_bytes: Optional[int] = None
    rx_deliveries: Optional[int] = None
    retx: Optional[int] = None
    rss_kb: Optional[int] = None
    source: str = "unavailable"

    @property
    def cpu_time_ms(self) -> Optional[float]:
        if self.cpu_user_ms is None or self.cpu_sys_ms is None:
            return None
        return self.cpu_user_ms + self.cpu_sys_ms


@dataclass
class EnergyEstimate:
    """Model output. Every field says what kind of number it is."""

    mininet_wifi_energy_mJ_estimated: Optional[float]
    cpu_energy_mJ_estimated: Optional[float]
    radio_activity_mJ_proxy: Optional[float]
    idle_energy_mJ_estimated: Optional[float]
    energy_model_version: str
    energy_model_coefficients: Dict[str, float]
    status: str            # "estimated" | "partial" | "unavailable"
    missing: tuple = ()

    def as_row(self) -> Dict[str, object]:
        d = asdict(self)
        d["energy_model_coefficients"] = dict(self.energy_model_coefficients)
        d["missing"] = ",".join(self.missing)
        return d


def read_proc_cpu_ms(pid: int, proc_root: str = "/proc") -> Optional[tuple]:
    """(user_ms, sys_ms) from /proc/<pid>/stat, or None if not readable.

    Fields 14 and 15 of `stat` are utime and stime in clock ticks. The comm
    field can contain spaces and parentheses, so the split starts after the
    LAST ')' -- parsing from the left is the classic bug here.
    """
    try:
        with open(f"{proc_root}/{pid}/stat", "r", encoding="utf-8") as fh:
            raw = fh.read()
    except (OSError, ValueError):
        return None
    cut = raw.rfind(")")
    if cut < 0:
        return None
    parts = raw[cut + 2:].split()
    if len(parts) < 13:
        return None
    try:
        utime, stime = int(parts[11]), int(parts[12])
    except (ValueError, IndexError):
        return None
    return (utime / _CLK_TCK * 1000.0, stime / _CLK_TCK * 1000.0)


def estimate(sample: StationEnergySample,
             coeff: EnergyCoefficients = EnergyCoefficients()) -> EnergyEstimate:
    """Estimate one station's energy. Missing inputs propagate, never default."""
    missing = []
    cpu_ms = sample.cpu_time_ms
    if cpu_ms is None:
        missing.append("cpu_time")
    if sample.active_ms is None:
        missing.append("active_ms")
    if sample.tx_bytes is None:
        missing.append("tx_bytes")
    if sample.rx_deliveries is None:
        missing.append("rx_deliveries")

    cpu_e = None if cpu_ms is None else cpu_ms * coeff.cpu_power_mW / 1000.0
    idle_e = (None if sample.active_ms is None
              else sample.active_ms * coeff.idle_station_power_mW / 1000.0)
    if sample.tx_bytes is None or sample.rx_deliveries is None:
        radio_e = None
    else:
        radio_e = (sample.tx_bytes * coeff.tx_cost_mJ_per_byte
                   + sample.rx_deliveries * coeff.rx_cost_mJ_per_delivery
                   + (sample.retx or 0) * coeff.retx_cost_mJ)

    parts = [cpu_e, idle_e, radio_e]
    if all(p is None for p in parts):
        total, status = None, "unavailable"
    elif any(p is None for p in parts):
        total, status = sum(p for p in parts if p is not None), "partial"
    else:
        total, status = sum(parts), "estimated"

    return EnergyEstimate(
        mininet_wifi_energy_mJ_estimated=None if total is None else round(total, 6),
        cpu_energy_mJ_estimated=None if cpu_e is None else round(cpu_e, 6),
        radio_activity_mJ_proxy=None if radio_e is None else round(radio_e, 6),
        idle_energy_mJ_estimated=None if idle_e is None else round(idle_e, 6),
        energy_model_version=ENERGY_MODEL_VERSION,
        energy_model_coefficients=asdict(coeff),
        status=status,
        missing=tuple(missing),
    )


def estimate_run(samples: Mapping[int, StationEnergySample],
                 coeff: EnergyCoefficients = EnergyCoefficients()) -> Dict[str, object]:
    """Aggregate a run. A run with any unavailable station is NOT 'estimated'."""
    per = {nid: estimate(s, coeff) for nid, s in sorted(samples.items())}
    known = [e for e in per.values() if e.mininet_wifi_energy_mJ_estimated is not None]
    statuses = {e.status for e in per.values()}
    if not known:
        status = "unavailable"
    elif "unavailable" in statuses or "partial" in statuses:
        status = "partial"
    else:
        status = "estimated"
    total = None if not known else round(
        sum(e.mininet_wifi_energy_mJ_estimated for e in known), 6)
    return {
        "mininet_wifi_energy_mJ_estimated": total,
        "cpu_energy_mJ_estimated": None if not known else round(
            sum(e.cpu_energy_mJ_estimated or 0.0 for e in per.values()), 6),
        "radio_activity_mJ_proxy": None if not known else round(
            sum(e.radio_activity_mJ_proxy or 0.0 for e in per.values()), 6),
        "energy_model_version": ENERGY_MODEL_VERSION,
        "energy_model_coefficients": asdict(coeff),
        "energy_status": status,
        "stations_reporting": len(known),
        "stations_total": len(per),
        "per_station": {nid: e.as_row() for nid, e in per.items()},
    }
