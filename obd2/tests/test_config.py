"""Settings from the environment."""

from __future__ import annotations

import pytest

from obd2_bridge.config import MEASUREMENT_NAMES, Config, ConfigError


def test_defaults():
    cfg = Config.from_env({"OBD_DEVICE": "/dev/ttyUSB0"})
    assert cfg.device_id == "car" and cfg.baudrate is None and cfg.protocol is None
    assert (cfg.fast_hz, cfg.slow_hz, cfg.dtc_interval) == (5.0, 1.0, 30.0)
    assert cfg.measurements == MEASUREMENT_NAMES and cfg.raw is True
    assert (cfg.mqtt_host, cfg.mqtt_port) == ("p4n4-mqtt", 1883)


def test_socket_devices_skip_the_baud_probe():
    assert Config.from_env({"OBD_DEVICE": "socket://p4n4-obd2-sim:35000"}).baudrate == 38400
    assert Config.from_env({"OBD_DEVICE": "socket://x:1", "OBD_BAUDRATE": "115200"}).baudrate == 115200


@pytest.mark.parametrize("env, message", [
    ({}, "OBD_DEVICE"),
    ({"OBD_DEVICE": "x", "OBD_DEVICE_ID": "my/car"}, "one topic level"),
    ({"OBD_DEVICE": "x", "OBD_DEVICE_ID": "car#1"}, "one topic level"),
    ({"OBD_DEVICE": "x", "OBD_PIDS": "rpm,boost"}, "unknown boost"),
    ({"OBD_DEVICE": "x", "OBD_PROTOCOL": "Z"}, "OBD_PROTOCOL"),
    ({"OBD_DEVICE": "x", "OBD_POLL_FAST_HZ": "0"}, "above 0"),
    ({"OBD_DEVICE": "x", "OBD_POLL_SLOW_HZ": "fast"}, "isn't a number"),
])
def test_rejects_bad_settings(env, message):
    with pytest.raises(ConfigError, match=message):
        Config.from_env(env)


def test_measurement_filter_and_raw_switch():
    cfg = Config.from_env({"OBD_DEVICE": "x", "OBD_PIDS": " rpm , speed ", "OBD_RAW": "false"})
    assert cfg.measurements == ("rpm", "speed") and cfg.raw is False
