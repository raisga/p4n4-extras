"""The bridge against the simulator: readings, codes, status, and recovery."""

from __future__ import annotations

import hashlib

from conftest import wait_for
from obd2_bridge import guard
from obd2_bridge.bridge import MEASUREMENTS, RAW

UNITS = {m.name: m.unit for m in MEASUREMENTS}


def url(sim) -> str:
    return f"socket://127.0.0.1:{sim.port}"


def test_publishes_every_measurement_with_its_unit(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim))
    wanted = {f"sensors/car/{m.name}" for m in MEASUREMENTS} | {"sensors/car/raw"}
    wait_for(lambda: wanted <= pub.topics())

    for m in MEASUREMENTS:
        payload = pub.on(f"sensors/car/{m.name}")[-1]
        assert set(payload) == {"value", "unit"}
        assert payload["unit"] == UNITS[m.name]
        assert isinstance(payload["value"], float)
    assert pub.on("sensors/car/battery_v")[-1]["value"] == 14.1
    raw = pub.on("sensors/car/raw")[-1]["values"]
    assert len(raw) == len(RAW) and all(isinstance(v, float) for v in raw)


def test_status_is_retained_and_describes_the_link(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim))
    wait_for(lambda: any(s.get("vehicle") for s in pub.on("status/car/online")))
    status = [m for m in pub.messages if m[0] == "status/car/online"][-1]
    assert status[1] == {"online": True, "adapter": "ELM327 v1.5",
                         "protocol": "ISO 15765-4 (CAN 11/500)", "vehicle": True}
    assert status[2] is True and status[3] == 1     # retained, QoS 1


def test_sends_only_diagnostic_reads(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data, at=130)
    before = guard.blocked()
    bridge, pub = run_bridge(url(sim))
    wait_for(lambda: pub.on("alerts/car/dtc") and len(pub.on("sensors/car/rpm")) > 10)

    modes = {c[:2] for c in sim.obd_requests()}
    assert modes <= guard.ALLOWED_MODES, modes
    assert {"01", "03", "07", "09", "0A"} <= modes
    assert guard.blocked() == before
    assert sim.cleared_at is None


def test_trouble_codes_published_once_per_change(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data, at=130)
    bridge, pub = run_bridge(url(sim))
    alert = wait_for(lambda: pub.on("alerts/car/dtc"))[0]
    assert alert["codes"] == ["P0171"]
    assert alert["pending"] == [] and alert["permanent"] == []
    assert alert["mil"] is True
    assert "Lean" in alert["descriptions"]["P0171"]
    assert alert["freeze_frame"] == {"dtc": "P0171"}

    # Several more reads, a code read every 0.5 s, same codes: no new alert
    wait_for(lambda: len(pub.on("sensors/car/rpm")) > 30)
    assert len(pub.on("alerts/car/dtc")) == 1
    assert [m[3] for m in pub.messages if m[0] == "alerts/car/dtc"] == [1]   # QoS 1


def test_no_alert_for_a_clean_car(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data)            # P0171 is 60 s away
    bridge, pub = run_bridge(url(sim))
    wait_for(lambda: bridge.dtc() is not None and len(pub.on("sensors/car/rpm")) > 10)
    assert pub.on("alerts/car/dtc") == []
    assert bridge.dtc()["codes"] == [] and bridge.dtc()["mil"] is False


def test_probe_hashes_the_vin(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim))
    probe = wait_for(lambda: bridge.probe() if bridge.probe().get("vehicle") else None)
    # The simulator's VIN ends in "0000000001": python-OBD's own decoder would cut it
    assert probe["vin_hash"] == hashlib.sha256(b"P4N4SIM0000000001").hexdigest()[:16]
    assert "P4N4SIM" not in str(probe)
    assert set(probe["measurements"]["supported"]) == {m.name for m in MEASUREMENTS}
    assert probe["measurements"]["unsupported"] == []


def test_only_the_measurements_asked_for(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim), OBD_PIDS="rpm,coolant_temp")
    wait_for(lambda: len(pub.on("sensors/car/rpm")) > 5 and pub.on("sensors/car/coolant_temp"))
    assert {t for t in pub.topics() if t.startswith("sensors/")} == {"sensors/car/rpm", "sensors/car/coolant_temp"}
    # Fewer than the seven raw features: no raw vector
    assert "sensors/car/raw" not in pub.topics()
    assert not any(c.startswith("010D") for c in sim.obd_requests())


def test_unsupported_pids_are_skipped(make_sim, scenario_data, run_bridge):
    del scenario_data["values"]["maf"], scenario_data["values"]["fuel_level"]
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim))
    wait_for(lambda: len(pub.on("sensors/car/rpm")) > 10)
    assert "sensors/car/maf" not in pub.topics() and "sensors/car/fuel_level" not in pub.topics()
    assert "sensors/car/raw" not in pub.topics()     # maf is one of the features
    assert set(bridge.probe()["measurements"]["unsupported"]) == {"maf", "fuel_level"}
    assert not any(c.startswith("0110") for c in sim.obd_requests())


def test_reconnects_after_the_adapter_drops(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data, drop_every=2.5)
    bridge, pub = run_bridge(url(sim))
    wait_for(lambda: bridge.connects >= 2, timeout=30)
    count = len(pub.on("sensors/car/rpm"))
    wait_for(lambda: len(pub.on("sensors/car/rpm")) > count + 5)
    assert sim.connections >= 2


def test_ignition_off_reports_the_adapter_and_battery(make_sim, scenario_data, run_bridge):
    scenario_data["off"] = [[0, 10_000]]
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim))
    status = wait_for(lambda: pub.on("status/car/online"))[-1]
    assert status == {"online": True, "adapter": "ELM327 v1.5", "protocol": None, "vehicle": False}
    assert wait_for(lambda: pub.on("sensors/car/battery_v"))[-1]["value"] == 12.4
    assert not any(t.startswith("sensors/car/rpm") for t in pub.topics())


def test_engine_off_mid_drive_ends_the_session(make_sim, scenario_data, run_bridge):
    scenario_data["off"] = [[4, 10_000]]
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim))
    wait_for(lambda: any(s.get("vehicle") for s in pub.on("status/car/online")))
    wait_for(lambda: pub.on("status/car/online")[-1].get("vehicle") is False, timeout=20)
    assert bridge.probe()["vehicle"] is False


def test_no_adapter_keeps_trying(run_bridge):
    bridge, pub = run_bridge("socket://127.0.0.1:9")     # nothing listens there
    status = wait_for(lambda: pub.on("status/car/online"))[-1]
    assert status == {"online": True, "adapter": None, "protocol": None, "vehicle": False}


def test_device_id_names_the_topics(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim), OBD_DEVICE_ID="cube")
    wait_for(lambda: "sensors/cube/rpm" in pub.topics() and "status/cube/online" in pub.topics())
    assert not any("/car/" in t for t in pub.topics())


def test_auto_protocol_detection(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data)
    bridge, pub = run_bridge(url(sim), OBD_PROTOCOL="")
    wait_for(lambda: "sensors/car/rpm" in pub.topics())
    assert "ATSP0" in sim.requests and "ATDPN" in sim.requests
