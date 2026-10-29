# obd2

Reads a vehicle's OBD-II port through an ELM327-compatible adapter and publishes its readings, trouble codes and adapter status over MQTT, where p4n4-iot's Node-RED stores them in InfluxDB like any other sensor. It's an extra, not core: it's for vehicles only, and needs an adapter. It ships with an ELM327 simulator, so it runs, and is tested, without a car.

It's the first extra of the [AI harness design](https://github.com/raisga/p4n4-docs/blob/main/decisions/ai-harness.md) (p4n4 Car, §3 and §6).

| | |
|---|---|
| Kind | `ingest`, safety `read-only` |
| Maturity | `incubating`: tested against the simulator; the real-car spike (S-OBD-1) is still to do |
| License | **GPL-2.0-only** (copyleft): it imports [python-OBD](https://github.com/brendan-w/python-OBD), which is GPL-2.0-only. See [LICENSE](LICENSE) |
| Profiles | `obd2` (the bridge), `obd2-sim` (a simulated car) |
| Containers | `p4n4-obd2`, `p4n4-obd2-sim` |
| Images | `p4n4-obd2:0.1.0`, `p4n4-obd2-sim:0.1.0`, built locally from `service/` and `simulator/` |
| Ports | `8090` on `127.0.0.1` (`OBD2_BIND`, `OBD2_PORT`): read-only API. The simulator listens on `35000`, on `p4n4-net` only |
| Uses | `p4n4-mqtt:1883` |
| Hardware | A USB adapter (STN-based, such as the OBDLink SX, recommended) mapped in the layer's `docker-compose.override.yml`, or a Wi-Fi adapter at a `socket://` URL; none with the simulator |

```
  car ── OBD-II ── adapter ──USB/TCP── obd2 ──MQTT──► p4n4-mqtt ──► Node-RED ──► InfluxDB
  (or obd2-sim on :35000)                │
                                         └── :8090  /health  /api/v1/probe  /api/v1/dtc
```

## Topics

`<id>` is `OBD_DEVICE_ID` (default `car`). The payloads follow specs §8.6: the reading in `value`, the device and measurement in the topic.

| Topic | Payload | Rate |
|---|---|---|
| `sensors/<id>/rpm`, `speed`, `maf` | `{"value": 2150.0, "unit": "rpm"}` | `OBD_POLL_FAST_HZ` (5) |
| `sensors/<id>/engine_load`, `coolant_temp`, `intake_temp`, `stft_b1`, `ltft_b1`, `throttle_pos`, `fuel_level` | `{"value": 91.0, "unit": "C"}` | `OBD_POLL_SLOW_HZ` (1) |
| `sensors/<id>/battery_v` | `{"value": 14.1, "unit": "V"}`: the adapter's reading, which works with the ignition off too | every `OBD_VOLTAGE_INTERVAL` s (5) |
| `sensors/<id>/raw` | `{"values": [rpm, load, coolant, stft, ltft, maf, speed]}`, the edge runner's feature vector | 1 Hz, when the car supports all seven |
| `alerts/<id>/dtc` | `{"codes": ["P0171"], "pending": [], "permanent": [], "mil": true, "descriptions": {"P0171": "System Too Lean"}, "freeze_frame": {"dtc": "P0171"}}` | when the codes or the MIL change (QoS 1) |
| `status/<id>/online` | `{"online": true, "vehicle": true, "adapter": "ELM327 v1.5", "protocol": "ISO 15765-4 (CAN 11/500)"}`; `{"online": false}` as its last will | retained, on change |

A measurement the car doesn't support is skipped (`/api/v1/probe` lists them). The status says `"vehicle": false` with the ignition off, and `"adapter": null` with no adapter. obd2 keeps trying in both cases, and keeps publishing `battery_v` while the ignition is off.

The VIN is never published. `/api/v1/probe` shows a hash of it, to tell cars apart.

## Read-only

obd2 sends diagnostic requests only: modes 01 (current data), 03 (stored codes), 06 (test results; python-OBD asks for the supported ones when it connects), 07 (pending codes), 09 (vehicle information) and 0A (permanent codes), plus the AT commands that set the adapter up. `service/obd2_bridge/guard.py` checks every line at the serial port before it's written. Anything else, mode 04 (clear codes) included, is refused and never reaches the car; `blocked_writes` in `/health` counts the refusals. The tests run against the simulator, which records every request it gets, and they fail if anything outside those modes arrives.

There's no way to clear codes yet. That waits for the harness's approval flow (design §7.3), since clearing erases freeze frames and readiness monitors.

## Settings

Append [`.env.example`](.env.example) to the extras layer's `.env.example` (and `.env`). The main ones:

| Variable | Default | |
|---|---|---|
| `OBD_DEVICE` | `socket://p4n4-obd2-sim:35000` | The adapter: `socket://host:port` (the simulator, a Wi-Fi adapter), or a USB adapter's `/dev/serial/by-id/…` path |
| `OBD_DEVICE_ID` | `car` | The `<id>` in the topics |
| `OBD_PROTOCOL` | empty (detect) | `6` for CAN 11-bit 500 kbit/s skips the protocol search |
| `OBD_PIDS` | empty (all) | Only these measurements, e.g. `rpm,speed,coolant_temp` |
| `OBD_POLL_FAST_HZ`, `OBD_POLL_SLOW_HZ` | `5`, `1` | Reads per second, per group |
| `OBD_DTC_INTERVAL` | `30` | Seconds between trouble code reads |
| `MQTT_HOST`, `MQTT_USER`, `MQTT_PASSWORD` | `p4n4-mqtt`, empty | The broker, and a login once p4n4-iot requires one |

### A USB adapter

Copy [`override.example.yml`](override.example.yml) into the extras layer's `docker-compose.override.yml`, then set `OBD_DEVICE` to the adapter's stable path (`ls /dev/serial/by-id/`) and `OBD_DEVICE_GID` to the group that owns it (`stat -c %g <path>`). Don't power the Pi from the OBD port: pin 16 is live with the ignition off and drains the battery (design §6.2).

## Use it in a project

Until `p4n4 extra add` exists:

```bash
cp -r obd2 <project>/extras/
# in <project>/extras/docker-compose.yml:  include: [obd2/docker-compose.yml]
cat <project>/extras/obd2/.env.example >> <project>/extras/.env
# COMPOSE_PROFILES=obd2,obd2-sim in <project>/extras/.env (drop obd2-sim for a real car)
p4n4 up extras
```

## Check it

```bash
pip install -r service/requirements.txt pyyaml pytest
python -m pytest tests          # bridge, guard, API and simulator, no Docker
tests/smoke.sh                  # the images, a broker and the simulator, in Docker
```

By hand, in a project: `curl -s localhost:8090/health`, and `mosquitto_sub -t 'sensors/car/#' -v` on the broker.

## Simulator

`simulator/elm327_sim.py` is our own minimal ELM327 for a CAN car: the AT commands python-OBD uses, the mode 01 PIDs above, codes for modes 03, 07 and 0A, and the VIN. It isn't the ELM327-emulator the spike plan mentions, whose CC-BY-NC-SA-4.0 license rules out shipping it in an image. Scenarios in `simulator/scenarios/` set values over a timeline (a constant, a ramp or a wave), engine-off windows and codes. `warmup` (the default) warms up, drives in a loop, and sets P0171 after two minutes. `OBD_SIM_DROP_EVERY` closes the connection every N seconds, like a pulled adapter.
