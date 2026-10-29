"""The simulator's encoding, so a passing bridge test means what it says."""

from __future__ import annotations

import elm327_sim as sim


def test_dtc_encoding():
    assert sim.dtc_bytes("P0171") == [0x01, 0x71]
    assert sim.dtc_bytes("C1234") == [0x52, 0x34]
    assert sim.dtc_bytes("U0100") == [0xC1, 0x00]


def test_supported_pid_bitmap():
    # PIDs 0x01 and 0x20 in the first block: the top and bottom bits
    assert sim.bitmap({0x01, 0x20, 0x42}, 0x00) == [0x80, 0x00, 0x00, 0x01]
    assert sim.bitmap({0x42}, 0x40) == [0x40, 0x00, 0x00, 0x00]


def test_scenario_values():
    s = sim.Scenario({"loop": 100, "values": {
        "rpm": 800, "coolant_temp": {"from": 20, "to": 90, "over": 70},
        "speed": {"base": 50, "amplitude": 10, "period": 40}}})
    assert s.value("rpm", 5) == 800
    assert s.value("coolant_temp", 35) == 55 and s.value("coolant_temp", 99) == 90
    assert round(s.value("speed", 10), 6) == 60
    assert s.at(130) == 30


def test_multi_frame_answer_reassembles():
    scenario = sim.Scenario({"vin": "P4N4SIM0000000001"})
    session = sim.Session(sim.Simulator(scenario))
    session.headers = True
    frames = session.frames(session.answer("09", "02", 0))
    assert frames[0].startswith("7E8 10 14 49 02 01")
    assert [f.split()[1] for f in frames[1:]] == ["21", "22"]


def test_codes_follow_the_timeline_and_a_clear():
    s = sim.Scenario({"dtcs": [{"code": "P0171", "type": "pending", "from": 60, "to": 120},
                               {"code": "P0171", "from": 120}]})
    assert s.codes(30, "stored", None) == []
    assert s.codes(90, "pending", None) == ["P0171"]
    assert s.codes(150, "stored", None) == ["P0171"]
    assert s.codes(150, "stored", cleared_at=140) == []


def test_records_every_request_and_answers_unknown_modes_with_no_data():
    simulator = sim.Simulator(sim.Scenario({"values": {"rpm": 800}}))
    session = sim.Session(simulator)
    session.handle("ATE0")
    assert session.handle("22F190").startswith("NO DATA")   # UDS read: not simulated
    session.handle("010C")
    assert session.handle("").startswith("41 0C 0C 80")    # a bare CR repeats 010C
    assert simulator.requests == ["ATE0", "22F190", "010C", "010C"]
    assert simulator.obd_requests() == ["22F190", "010C", "010C"]
