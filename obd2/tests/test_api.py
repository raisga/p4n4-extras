"""The read-only HTTP API."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from conftest import wait_for
from obd2_bridge.api import make_server


@pytest.fixture
def api(make_sim, scenario_data, run_bridge):
    sim = make_sim(scenario_data, at=130)
    bridge, pub = run_bridge(f"socket://127.0.0.1:{sim.port}")
    loop = threading.Thread(target=threading.Event().wait)   # stands in for the bridge loop
    loop.daemon = True
    loop.start()
    server = make_server(bridge, loop, pub, host="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield bridge, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def get(url: str, method: str = "GET") -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health(api):
    bridge, base = api
    wait_for(lambda: get(base + "/health")[1]["vehicle"])
    code, body = get(base + "/health")
    assert code == 200
    assert body["status"] == "ok" and body["adapter"] is True and body["mqtt"] is True
    assert body["blocked_writes"] >= 0


def test_probe_and_codes(api):
    bridge, base = api
    wait_for(lambda: bridge.dtc() is not None)
    code, probe = get(base + "/api/v1/probe")
    assert code == 200 and probe["protocol"] == "ISO 15765-4 (CAN 11/500)"
    code, dtc = get(base + "/api/v1/dtc")
    assert code == 200 and dtc["codes"] == ["P0171"] and dtc["read_age_s"] >= 0


def test_read_only_and_unknown_routes(api):
    bridge, base = api
    assert get(base + "/api/v1/dtc/clear", "POST")[0] == 405
    assert get(base + "/api/v1/dtc", "DELETE")[0] == 405
    assert get(base + "/nope")[0] == 404
