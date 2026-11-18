"""Validation for the Mininet-WiFi estimated energy model.

Each test pins one property the model must have. The point of the set is not
that the numbers are right -- the coefficients are declared assumptions -- but
that the model separates its components, propagates missing inputs instead of
defaulting them, and reproduces the same output from the same inputs.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from ccvc.bb import energy as en  # noqa: E402

C = en.EnergyCoefficients()


def _sample(**kw):
    base = dict(nid=1, cpu_user_ms=0.0, cpu_sys_ms=0.0, active_ms=0.0,
                tx_bytes=0, rx_deliveries=0, retx=0)
    base.update(kw)
    return en.StationEnergySample(**base)


# ---------------------------------------------------------------- components
def test_a_cpu_only_station_charges_only_the_cpu_component():
    """No traffic at all: the radio proxy must be exactly zero, not merely small."""
    e = en.estimate(_sample(cpu_user_ms=100.0, cpu_sys_ms=50.0), C)
    assert e.status == "estimated"
    assert e.radio_activity_mJ_proxy == 0.0
    assert e.cpu_energy_mJ_estimated == pytest.approx(150.0 * C.cpu_power_mW / 1000.0)


def test_a_zero_traffic_station_still_costs_wall_clock_time():
    """A station that is alive but idle is not free: idle time is charged."""
    e = en.estimate(_sample(active_ms=10_000.0), C)
    assert e.idle_energy_mJ_estimated > 0.0
    assert e.radio_activity_mJ_proxy == 0.0


def test_a_tx_heavy_station_costs_more_than_an_idle_one():
    idle = en.estimate(_sample(active_ms=1000.0), C)
    heavy = en.estimate(_sample(active_ms=1000.0, tx_bytes=1_000_000), C)
    assert (heavy.mininet_wifi_energy_mJ_estimated
            > idle.mininet_wifi_energy_mJ_estimated)
    assert heavy.cpu_energy_mJ_estimated == idle.cpu_energy_mJ_estimated


def test_an_rx_heavy_station_is_charged_per_delivery():
    """rx is charged per DELIVERY, because that is the unit of listener work."""
    one = en.estimate(_sample(rx_deliveries=1), C)
    many = en.estimate(_sample(rx_deliveries=1000), C)
    assert many.radio_activity_mJ_proxy == pytest.approx(
        1000 * C.rx_cost_mJ_per_delivery)
    assert many.radio_activity_mJ_proxy > one.radio_activity_mJ_proxy


def test_retransmissions_are_charged_separately_from_first_sends():
    """A retry is its own cost; folding it into tx_bytes would hide the retry."""
    clean = en.estimate(_sample(tx_bytes=1000, retx=0), C)
    lossy = en.estimate(_sample(tx_bytes=1000, retx=20), C)
    assert (lossy.radio_activity_mJ_proxy - clean.radio_activity_mJ_proxy
            == pytest.approx(20 * C.retx_cost_mJ))


# -------------------------------------------------------------- missing data
def test_a_missing_input_is_unavailable_and_never_zero():
    """Writing 0 for an unmeasured quantity publishes an absent measurement."""
    e = en.estimate(en.StationEnergySample(nid=7), C)
    assert e.status == "unavailable"
    assert e.mininet_wifi_energy_mJ_estimated is None
    assert e.cpu_energy_mJ_estimated is None
    assert "cpu_time" in e.missing


def test_a_partially_observed_station_is_partial_not_estimated():
    """Half the inputs is not a measurement; the status has to say so."""
    e = en.estimate(en.StationEnergySample(nid=8, tx_bytes=10, rx_deliveries=2), C)
    assert e.status == "partial"
    assert e.mininet_wifi_energy_mJ_estimated is not None
    assert "cpu_time" in e.missing


def test_one_unavailable_station_makes_the_whole_run_partial():
    """A run is only `estimated` when EVERY station reported."""
    good = _sample(nid=1, cpu_user_ms=10.0, active_ms=100.0, tx_bytes=10,
                   rx_deliveries=1)
    bad = en.StationEnergySample(nid=2)
    out = en.estimate_run({1: good, 2: bad}, C)
    assert out["energy_status"] == "partial"
    assert out["stations_reporting"] == 1
    assert out["stations_total"] == 2


# ------------------------------------------------------------ reproducibility
def test_the_same_inputs_reproduce_the_same_output():
    s = _sample(cpu_user_ms=31.25, cpu_sys_ms=7.5, active_ms=4321.0,
                tx_bytes=98765, rx_deliveries=432, retx=7)
    first = en.estimate(s, C)
    second = en.estimate(s, C)
    assert first == second


def test_the_coefficients_travel_with_every_estimate():
    """A number whose assumptions are not attached cannot be re-derived later."""
    e = en.estimate(_sample(cpu_user_ms=1.0), C)
    assert e.energy_model_version == en.ENERGY_MODEL_VERSION
    assert e.energy_model_coefficients["cpu_power_mW"] == C.cpu_power_mW


def test_changed_coefficients_change_the_output_and_are_recorded():
    """Two sweeps with different coefficients must never look comparable."""
    s = _sample(cpu_user_ms=100.0)
    a = en.estimate(s, en.EnergyCoefficients(cpu_power_mW=1000.0))
    b = en.estimate(s, en.EnergyCoefficients(cpu_power_mW=2000.0))
    assert b.mininet_wifi_energy_mJ_estimated > a.mininet_wifi_energy_mJ_estimated
    assert (a.energy_model_coefficients["cpu_power_mW"]
            != b.energy_model_coefficients["cpu_power_mW"])


# ------------------------------------------------------------------- /proc
def test_proc_cpu_read_works_on_a_real_process():
    """The parser must survive a real /proc/<pid>/stat, comm parentheses and all."""
    got = en.read_proc_cpu_ms(os.getpid())
    assert got is not None
    user_ms, sys_ms = got
    assert user_ms >= 0.0 and sys_ms >= 0.0


def test_proc_cpu_read_returns_none_for_a_dead_pid():
    """Unreadable /proc must be None so the caller reports `unavailable`."""
    assert en.read_proc_cpu_ms(2 ** 22) is None


def test_a_cpu_burning_child_shows_more_cpu_than_a_sleeping_one():
    """End-to-end: the CPU component actually tracks real process CPU time."""
    burner = subprocess.Popen(
        [sys.executable, "-c", "t=__import__('time').time()\nwhile __import__('time').time()-t<0.4: pass"])
    sleeper = subprocess.Popen([sys.executable, "-c", "__import__('time').sleep(0.4)"])
    time.sleep(0.45)
    burn = en.read_proc_cpu_ms(burner.pid)
    sleep = en.read_proc_cpu_ms(sleeper.pid)
    burner.wait(); sleeper.wait()
    if burn is None or sleep is None:
        pytest.skip("process exited before /proc could be read")
    assert sum(burn) > sum(sleep)


def test_the_comm_field_parser_is_not_fooled_by_parentheses():
    """A process named `foo) (bar` breaks any parser that splits from the left."""
    fake = "1234 (weird) name) S 1 1 1 0 -1 0 0 0 0 0 " + " ".join(str(i) for i in range(1, 20))
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(f"{d}/99")
        with open(f"{d}/99/stat", "w", encoding="utf-8") as fh:
            fh.write(fake)
        got = en.read_proc_cpu_ms(99, proc_root=d)
    assert got is not None
