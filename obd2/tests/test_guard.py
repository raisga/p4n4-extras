"""The read-only guard: what may reach the adapter, and proof that nothing else does."""

from __future__ import annotations

import obd
import pytest

from obd2_bridge import guard

ALLOWED = [
    b"ATZ", b"ATE0", b"ATH1", b"ATL0", b"AT RV", b"ATRV", b"ATSP0", b"ATTP6", b"ATDPN",
    b"ATI", b"AT SH 7E0 ", b"ATD",
    b"0100", b"010C", b"010C1", b"0101", b"03", b"07", b"0A", b"0600", b"0900", b"0902",
    b"\x7f\x7f", b"", b" ",
]

BLOCKED = [
    b"04",                 # clear codes and freeze frames
    b"0400",
    b"08",                 # control of on-board systems (actuator tests)
    b"05",                 # legacy O2 monitoring: not something we use
    b"2EF19000",           # UDS write data by identifier
    b"3101FF00",           # UDS routine control
    b"2701",               # UDS security access
    b"1003",               # UDS diagnostic session
    b"14FFFFFF",           # UDS clear diagnostic information
    b"ATMA",               # monitor all: floods the link, never needed
    b"ATLP",               # low power
    b"ATBRD23",            # change the adapter's baud rate
    b"ATPP2CSV81",         # programmable parameters
    b"STDI",               # STN commands
    b"hello",
]


@pytest.mark.parametrize("line", ALLOWED)
def test_allows_diagnostic_reads_and_setup(line):
    assert guard.check(line) is None


@pytest.mark.parametrize("line", BLOCKED)
def test_blocks_everything_else(line):
    assert guard.check(line) is not None


class RecordingPort:
    def __init__(self):
        self.written = []
        self.baudrate = 0

    def write(self, data):
        self.written.append(data)
        return len(data)


def test_port_refuses_a_write_with_a_forbidden_line():
    inner = RecordingPort()
    port = guard.GuardedPort(inner)
    before = guard.blocked()
    with pytest.raises(guard.ReadOnlyViolation):
        port.write(b"0100\r04\r")
    assert inner.written == []
    assert guard.blocked() == before + 1


def test_port_passes_allowed_writes_and_attributes():
    inner = RecordingPort()
    port = guard.GuardedPort(inner)
    port.write(b"010C1\r")
    port.write(b"\r")                       # repeat the last request
    port.baudrate = 38400                   # python-OBD sets these on the port
    assert inner.written == [b"010C1\r", b"\r"]
    assert inner.baudrate == 38400 and port.baudrate == 38400


def test_forced_clear_never_reaches_the_car(make_sim, scenario_data):
    """python-OBD will send CLEAR_DTC when forced; the guard stops it at the port."""
    sim = make_sim(scenario_data, at=130)   # past the point P0171 sets
    conn = obd.OBD(f"socket://127.0.0.1:{sim.port}", baudrate=38400, protocol="6", fast=False)
    assert conn.status() == obd.OBDStatus.CAR_CONNECTED
    assert [c for c, _ in conn.query(obd.commands.GET_DTC).value] == ["P0171"]

    before = guard.blocked()
    r = conn.query(obd.commands.CLEAR_DTC, force=True)
    assert r.is_null()
    assert guard.blocked() == before + 1
    assert not any(c.startswith("04") for c in sim.obd_requests())
    assert sim.cleared_at is None
    # python-OBD drops the connection after the failed write
    assert conn.status() == obd.OBDStatus.NOT_CONNECTED
