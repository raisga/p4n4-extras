"""Shared fixtures: the simulator on a free port, and a publisher that records."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "service"), str(HERE.parent / "simulator")]

import elm327_sim  # noqa: E402
from obd2_bridge import guard  # noqa: E402
from obd2_bridge.bridge import Bridge  # noqa: E402
from obd2_bridge.config import Config  # noqa: E402

# Every python-OBD connection in these tests goes through the read-only guard
guard.install()


def wait_for(predicate, timeout: float = 15.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout} s")


class FakePublisher:
    """Records what the bridge publishes, like MqttPublisher would send it."""

    connected = True

    def __init__(self):
        self.messages: list[tuple[str, dict, bool, int]] = []
        self._lock = threading.Lock()

    def publish(self, topic, payload, retain=False, qos=0):
        with self._lock:
            self.messages.append((topic, payload, retain, qos))

    def set_status(self, topic, payload):
        self.publish(topic, payload, retain=True, qos=1)

    def on(self, topic) -> list[dict]:
        with self._lock:
            return [p for t, p, _, _ in self.messages if t == topic]

    def topics(self) -> set[str]:
        with self._lock:
            return {t for t, *_ in self.messages}


@pytest.fixture
def scenario_data() -> dict:
    return yaml.safe_load(elm327_sim.DEFAULT_SCENARIO.read_text())


@pytest.fixture
def make_sim():
    sims = []

    def make(data: dict, drop_every: float = 0, at: float = 0) -> elm327_sim.Simulator:
        sim = elm327_sim.Simulator(elm327_sim.Scenario(data), drop_every=drop_every).start()
        sim.start_time -= at  # start the scenario `at` seconds in
        sims.append(sim)
        return sim

    yield make
    for sim in sims:
        sim.stop()


@pytest.fixture
def run_bridge():
    """Start a Bridge in a thread; stopped (and joined) at teardown."""
    running = []

    def run(device: str, **settings) -> tuple[Bridge, FakePublisher]:
        # Protocol 6 skips the ELM's protocol search, so tests connect in about 1 s
        env = {"OBD_DEVICE": device, "OBD_PROTOCOL": "6", "OBD_DTC_INTERVAL": "0.5",
               "OBD_VOLTAGE_INTERVAL": "0.5", "OBD_POLL_FAST_HZ": "10", "OBD_POLL_SLOW_HZ": "5"}
        env.update({k: str(v) for k, v in settings.items()})
        pub = FakePublisher()
        bridge = Bridge(Config.from_env(env), pub)
        stop = threading.Event()
        thread = threading.Thread(target=bridge.run, args=(stop,), daemon=True)
        thread.start()
        running.append((stop, thread))
        return bridge, pub

    yield run
    for stop, thread in running:
        stop.set()
        thread.join(timeout=15)
