# TODO

_Last updated: 2026-10-20 (groundwork and obd2 0.1.0 done)_

Candidate extras for `p4n4-extras`: what each one is for, why it's an extra rather than core, and which other p4n4 projects it helps. Nothing here is committed to; it's the backlog to pick from. Each one, once built, follows the rules in the [README](README.md#adding-an-extra) and the contract in the [AI harness design §5.3](https://github.com/raisga/p4n4-docs/blob/main/decisions/ai-harness.md#53-contract).

Already in the core, so **not** candidates here: Telegraf, Loki, Alloy and the MQTTX web client (p4n4-iot's optional profiles), and the dashboard's own Caddy TLS front end (`p4n4-dashboard/docker-compose.tls.yml`).

Image names are candidates only. Pin an exact version, and check the license against the allowlist (§12 Q5), when the extra is added.

## Suggested order

Ordered by which open gaps (from the [harness design §8](https://github.com/raisga/p4n4-docs/blob/main/decisions/ai-harness.md#8-gaps)) and planned work each one unblocks:

- [x] **Groundwork for every extra:** `schema/extra.schema.json`, `schema/licenses.yaml` (permissive and copyleft, labelled), `scripts/validate.py` with its tests, both in CI, plus `.github/CODEOWNERS`, the hardened `_template/` and [The Contract](README.md#the-contract) in the README. Kinds `ingest`, `bridge` and `actuator` meet every container rule; kind `service` may declare exceptions, each with a reason.
- [x] `obd2` 0.1.0 (incubating): python-OBD bridge (GPL-2.0-only), read-only guard at the serial port, our own ELM327 simulator, tests and a Docker smoke test, all in CI. Built against the simulator only; see follow-ups.
- [ ] `backup`: no supported backup path today (G12; deployment guide checklist "Backups configured and one restore tested").
- [ ] `go2rtc`: promote the template's video extra into a shared one for the dashboard's Video tab.
- [ ] `modbus`: next in the harness catalog; energy meters and solar inverters.
- [ ] `mqtt-uplink`: push to a home or cloud broker (G11).
- [ ] `ntfy`: phone push for `alerts/…`.
- [ ] `proxy`: one HTTPS entry point for every web UI (G13).
- [ ] `tailscale`: reach a deployment remotely without opening ports.
- [ ] The rest, as projects ask for them.

### Follow-ups from the groundwork and obd2

- [ ] **obd2 on the real car:** spikes S-OBD-1 to S-OBD-4 (harness §6.4). Confirm the protocol, PIDs and rates on a real car, record its scenario (no VIN in it), measure power and heat. Then move obd2 to `community`.
- [ ] **obd2 manufacturer PIDs** (S-OBD-2): e.g. a transmission temperature, through a maker-specific request where one exists. It needs the guard to allow that one request, reviewed.
- [ ] **Clearing codes** (mode 04): only once p4n4-api has confirmation tokens (G10) and the harness has `obd_dtc_clear` (§7.3). Then add the endpoint and allow mode 04 in the guard for it alone, and that changes obd2's safety class.
- [ ] **Store `alerts/<id>/dtc`** in an `events` measurement in p4n4-iot's Node-RED (G14); today only `sensors/` and `inference/` are stored.
- [ ] **p4n4-lib / p4n4-cli `extra add`** (G1, G2): copy `<name>/` from this catalog into a project, add its `include:` line, and merge its `.env.example` into the layer's. Keys several extras share (`MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`) must appear once.
- [ ] **p4n4-emu:** run `obd2` with `obd2-sim` under the `rpi5` profile (S-OBD-0's emulator half).
- [ ] **p4n4-docs:** update `stacks/extras.md` and the harness design. §5.2 (schema and validator exist), §6.2 (our own simulator instead of ELM327-emulator, whose CC-BY-NC-SA license rules out an image), §12 Q5 (the license allowlist is decided), and the guard's allowed modes (06 added, because python-OBD asks for it on connect).
- [ ] **Upstream:** report python-OBD 0.7.3's VIN decoder, which strips `0`, `1`, `2`, `x` and `\` from both ends of the VIN (obd2 decodes the bytes itself).
- [ ] **Images:** built locally while incubating. Publish to GHCR under `raisga` once an extra is `official` (§12 Q9).

## Catalog

### Device ingest and protocol bridges

Kind `ingest` or `bridge`. Each one publishes under `sensors/<device-id>/<measurement>` with the reading in `value`, plus `status/<device-id>/online`, so Node-RED's existing storage rules put it in InfluxDB and Grafana with no core changes.

| Extra | Candidate | Why | Helps |
|-------|-----------|-----|-------|
| `obd2` | python-OBD or our own client, USB/Bluetooth ELM327 | Vehicle data over OBD-II. Hardware-bound and niche, the textbook extra. Read-only safety class; clearing DTCs only behind approval (harness §7.3) | p4n4 Car (harness §3), the dashboard Vehicle tab (G15), Ollama explaining trouble codes, `alerts/` storage (G14) |
| `modbus` | pymodbus (RTU over RS-485 and TCP) | Energy meters, PLCs, solar inverters, pumps: most industrial and energy hardware speaks it | The "home energy monitor" and "predictive maintenance" use cases in the p4n4 README; the `pidurable` pumps template with real pumps instead of simulated ones |
| `canbus` | python-can + cantools (DBC decoding), SocketCAN | Raw CAN on vehicles and machines; a faster back end for `obd2` | p4n4 Car beyond standard PIDs (manufacturer-specific data), agricultural and industrial machines |
| `gps` | gpsd → MQTT | Location for vehicles and moving assets | p4n4 Car trip logs, Grafana Geomap panels, location as context for the agent |
| `zigbee2mqtt` | koenkk/zigbee2mqtt, USB coordinator in the override file | Cheap off-the-shelf Zigbee sensors and plugs, no firmware to write; needs its topic mapping onto `sensors/…` | "Home energy monitor" (smart plugs), "greenhouse" (soil and climate sensors); a no-soldering start for new users |
| `ble` | Theengs Gateway | Bluetooth LE thermometers, plant sensors and beacons → MQTT | Greenhouse, cold-chain demos; works on the Pi 5's onboard Bluetooth |
| `rtl433` | rtl_433 with an RTL-SDR dongle | 433/868 MHz weather stations, soil probes, door sensors | Greenhouse and outdoor monitoring with cheap commercial sensors |
| `esphome` | esphome/esphome dashboard | Build and flash firmware for ESP32 boards that already publish to MQTT | `p4n4-hw` reference designs (flash a board from the browser), the "rapid IoT prototyping" path |
| later | BACnet, 1-Wire, OPC UA | From the harness catalog's candidate row | Building automation, industrial users |

### Video and vision

| Extra | Candidate | Why | Helps |
|-------|-----------|-----|-------|
| `go2rtc` | alexxit/go2rtc | Turns RTSP/USB cameras into the MJPEG, snapshot and HLS URLs the dashboard's Video tab plays. The `mqtt-influx-grafana-ollama-go2rtc` template already runs it as its extras layer; a shared extra stops every project copying that setup | `p4n4-dashboard` Video tab (real cameras instead of demo clips), `p4n4-templates` (the go2rtc template uses the shared extra) |
| `frigate` | Frigate NVR | Object detection on camera feeds (Coral/Hailo in the override file), events published over MQTT. Heavy, and overlaps go2rtc (it bundles its own), so it's an alternative to `go2rtc`, not a dependency on it | Vision alerts into `alerts/…` for Node-RED and n8n; camera events as context for the agent; dashboard vision overlay |
| `label-studio` | Label Studio | Label images, audio and time-series windows collected on the device | Training data for Edge Impulse and ONNX models (G16, `p4n4 ei`), with the `dataset-export` extra below |

### AI and voice

Next to p4n4-ai, not in it: the AI stack's core is Ollama, Letta, n8n, System 1 and the runner, and these only add to it.

| Extra | Candidate | Why | Helps |
|-------|-----------|-----|-------|
| `qdrant` | qdrant/qdrant (or Chroma) | A vector store for RAG over manuals, datasheets, `HOME.md` and past investigations. Letta has its own pgvector store, so this is for n8n and the agent | The agent and `pidurable` investigations citing manuals; p4n4 Car explaining DTCs from the service manual; n8n RAG workflows |
| `whisper` | wyoming-whisper or faster-whisper | Local speech-to-text | Voice questions in the dashboard Assistant (needs a p4n4-api audio endpoint), hands-free use in p4n4 Car |
| `piper` | wyoming-piper | Local text-to-speech | Spoken alerts and answers, e.g. reading a trouble code explanation aloud in the car |
| `open-webui` | Open WebUI | A full chat UI over Ollama for power users at a workstation. The dashboard's Assistant covers normal users, so this stays optional. Check its license: it's no longer plain BSD | Model testing and prompt work while building a project; trying models before an admin picks the deployment's assistant |
| `dataset-export` | Small p4n4 service (Python) | Cuts labelled windows out of InfluxDB and uploads them to Edge Impulse's ingestion API or writes CSV/Parquet for ONNX training | G16: the missing path from stored telemetry to a trained edge model; `p4n4 ei` in the CLI |

### Connectivity and remote access

| Extra | Candidate | Why | Helps |
|-------|-----------|-----|-------|
| `mqtt-uplink` | Mosquitto in bridge mode, or a small bridge like the go2rtc template's `uplink/` | Push selected topics to a home or cloud broker when a link is up, with the broker queueing while offline. The core bridge only pulls | G11; p4n4 Car syncing at home; several sites feeding one central p4n4 |
| `tailscale` | tailscale/tailscale (or `wireguard` with wg-easy, for fully self-hosted) | Remote access without exposing ports, in line with the "trusted networks only" rule in the README and security guide | The dashboard's Clients fleet view reaching deployments in the field; the cloud deployment guides; remote `p4n4` CLI and harness use |
| `proxy` | Caddy (as the dashboard already uses), or Traefik | One HTTPS entry point with hostnames for Grafana, Node-RED, n8n, the API and the dashboard, instead of one port each. Could add SSO (Authelia) later | G13; the dashboard's https page framing Grafana, Node-RED and n8n without mixed-content blocks; p4n4-api's `P4N4_API_TRUSTED_PROXIES` |

### Operations

| Extra | Candidate | Why | Helps |
|-------|-----------|-----|-------|
| `backup` | offen/docker-volume-backup or restic, plus `influx backup` | Scheduled, consistent backups of the volumes (InfluxDB, Node-RED, Grafana, n8n, Letta, the API's database) to a disk, NAS or S3, with retention. Restores tested in CI | G12; the deployment guide's backup checklist; a future `p4n4 backup` / `restore` in the CLI; a "last backup" card in the dashboard via p4n4-api |
| `ntfy` | binwiederhier/ntfy | Self-hosted push notifications to phones, no Google/Apple account per device. Node-RED and n8n post to it over HTTP | Alerts from `alerts/…` and `pidurable` investigations reaching people off the dashboard; outage notices for the Clients view |
| `cadvisor` | cAdvisor, scraped by core Telegraf or Alloy | Per-container CPU, memory and disk; the core has host and broker metrics, not per-container ones | The dashboard Services tab (resource use per service), p4n4-emu (checking real usage against its resource limits), sizing guides for the Pi 5 and Jetson |
| `diun` | crazymax/diun | Tells you when a pinned image has a new version; it notifies instead of auto-updating, so pinned versions stay pinned | Release work across the stacks; a future `p4n4 upgrade`; an "updates available" notice in the dashboard |
| `renderer` | grafana/grafana-image-renderer | PNG/PDF of Grafana panels. Pulls in Chromium, so it's heavy on a Pi | n8n daily or weekly reports (Ollama's summary plus the charts) by email or ntfy; snapshots in agent findings |
| `object-store` | Garage or SeaweedFS (check MinIO's current license and status first) | S3-compatible storage on the device or LAN | A `backup` target, video clips and snapshots, model artifacts for `ei-runner` |

## What each p4n4 project gets

| Project | Extras that help it |
|---------|---------------------|
| `p4n4-harness` (planned) | Device bridges give it the uniform ingest contract (goal G-C); `qdrant` for document tools; `backup` before risky changes |
| `p4n4-cli` / `p4n4-lib` | Drives `p4n4 extra list\|add\|remove` (G1, G2) with real extras to install; `backup` → `p4n4 backup`; `dataset-export` → `p4n4 ei`; `diun` → `p4n4 upgrade` |
| `p4n4-api` | `cadvisor` metrics and `backup` status as new read endpoints; `whisper`/`piper` behind an audio endpoint; trusted-proxy setup with `proxy` |
| `p4n4-dashboard` | `go2rtc`/`frigate` for Video; `obd2` for a Vehicle tab (G15); `cadvisor` for Services; `ntfy` for alerts on phones; `tailscale` for the Clients fleet; `whisper`/`piper` for voice in the Assistant |
| `p4n4-iot` | Bridges feed its storage rules with no flow changes; `mqtt-uplink` closes G11; `renderer` for Grafana reports |
| `p4n4-ai` | `qdrant` for RAG; `dataset-export` and `label-studio` to train `ei-runner` models (G16) |
| `p4n4-templates` | New templates: Zigbee home energy, Modbus solar, BLE greenhouse, Frigate camera alerts, p4n4 Car |
| `p4n4-emu` | Each extra's simulator runs with device passthrough off; `cadvisor` checks the emulated resource limits |
| `p4n4-hw` | `esphome` flashes its boards; `obd2`, `canbus`, `gps`, `zigbee2mqtt` document the adapters and dongles to buy |
| `p4n4-docs` | One `stacks/extras.md` entry per extra; the backup and remote-access guides point at `backup` and `tailscale` |

## Considered, not planned

- **Portainer / Dockge:** container management overlaps the dashboard's Services tab and p4n4-api's stack control, and needs the Docker socket. Revisit only if users ask for it.
- **Dozzle:** log viewing is covered by Loki in the core and the API's log streaming (the dashboard logs viewer is pending in p4n4-api's TODO).
- **Watchtower-style auto-updates:** replacing images automatically conflicts with the pinned-image rule. `diun` notifies instead.
- **Prometheus:** Telegraf and Alloy already collect metrics into the core; `cadvisor` plugs into them instead of adding a second metrics store.
- **Wi-Fi hotspot (hostapd) for p4n4 Car:** host-level networking, so it belongs in `p4n4-hw`'s Raspberry Pi scripts, not in a container here.
