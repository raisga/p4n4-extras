# p4n4-extras

> **Optional services** for p4n4 that are not part of the core platform. Nothing here starts by default.

The p4n4 core is two stacks: [`p4n4-iot`](https://github.com/raisga/p4n4-iot) (MQTT, Node-RED, InfluxDB, Grafana) and [`p4n4-ai`](https://github.com/raisga/p4n4-ai) (Ollama, Letta, n8n, System 1 and the Edge Impulse / ONNX inference runner). This stack is the home for services that are useful next to them but not required, one directory per extra: each one is opt-in, and no core service depends on any of them. A project without this stack, or with it and nothing enabled, works exactly the same.

Attaches to the shared `p4n4-net` Docker bridge network created by `p4n4-iot`.

Part of the [p4n4](https://github.com/raisga/p4n4) platform — an EdgeAI + GenAI integration platform for IoT deployments.

> **Formerly p4n4-edge.** The Edge Impulse / ONNX inference runner that lived here is now the `ei-runner` profile of [p4n4-ai](https://github.com/raisga/p4n4-ai#edge-inference), and this repository holds the optional services instead. To move a project, run `p4n4 migrate edge`, or see [Migrating from p4n4-edge](https://github.com/raisga/p4n4-ai#migrating-from-p4n4-edge).

---

## Table of Contents

- [Core or Extra?](#core-or-extra)
- [Services](#services)
- [Getting Started](#getting-started)
- [Adding an Extra](#adding-an-extra)
- [The Contract](#the-contract)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [License](#license)

---

## Core or Extra?

| | Core (p4n4-iot, p4n4-ai) | Extras (this stack) |
|---|---|---|
| **Belongs there when** | p4n4's value depends on it: device → MQTT → Node-RED → InfluxDB → Grafana, local GenAI, and edge inference | It's useful but optional: the pipeline works without it |
| **Starts** | The stack's default `COMPOSE_PROFILES` | Only when `COMPOSE_PROFILES` lists it |
| **Depends on** | Other core services only | Core services (via `p4n4-net`), never another extra by default |
| **Depended on by** | Anything | Nothing in the core |

Typical extras: a reverse proxy with TLS, a container manager, image auto-updates, metrics (Prometheus, cAdvisor), a vector database, a chat UI, speech (Whisper, Piper), extra MQTT bridges, backup jobs, video (go2rtc).

---

## Services

The catalog: extras that live here, one directory each, for projects to copy in. None is part of a new project's layer: `p4n4 init` copies only `docker-compose.yml` (with `include: []`) and `_template/`, so a project adds the ones it wants (each extra's README says how, until `p4n4 extra add` exists). The catalog grows from the one planned in p4n4-docs' [AI harness design](https://github.com/raisga/p4n4-docs/blob/main/decisions/ai-harness.md#5-extras-community-stacks) (Modbus and CAN bus are next), and [TODO.md](TODO.md) lists more candidates. The [`mqtt-influx-grafana-ollama-go2rtc`](https://github.com/raisga/p4n4-templates/tree/main/projects/mqtt-influx-grafana-ollama-go2rtc) template runs go2rtc video and a device uplink as its own extras layer.

| Extra | Kind | Maturity | License | Profiles | Description |
|-------|------|----------|---------|----------|-------------|
| [`obd2`](obd2/) | ingest, read-only | incubating | GPL-2.0-only (copyleft) | `obd2`, `obd2-sim` | A vehicle's OBD-II port (ELM327/STN adapter, USB or Wi-Fi) → MQTT: readings, trouble codes, adapter status; with an ELM327 simulator |

Copyleft extras are labelled here and ship their license text in their directory; the repository itself is MIT.

---

## Getting Started

With the p4n4 CLI, add the layer when creating a project (it isn't part of `--layer all`):

```bash
p4n4 init my-project --layer all,extras
cd my-project
# add an extra (below), list it in extras/.env COMPOSE_PROFILES, then:
p4n4 up extras
```

By hand:

```bash
git clone https://github.com/raisga/p4n4-extras.git
cd p4n4-extras
cp .env.example .env
docker network create p4n4-net   # skip if p4n4-iot is already running
make up                          # starts what COMPOSE_PROFILES lists: nothing by default
```

`p4n4 up` and `make up` skip this stack while nothing is enabled, so keeping it in a project costs nothing.

---

## Adding an Extra

Each extra is a directory of its own. In a project, the layer's `docker-compose.yml` pulls it in with [`include:`](https://docs.docker.com/compose/how-tos/multiple-compose-files/include/), so every extra runs in the layer's one Compose project, on `p4n4-net`, with one `.env`. [`_template/`](_template/) is a complete, valid extra to start from:

1. **Copy it:** `cp -r _template <name>`, then rename `my-extra` and `MY_EXTRA` everywhere in `<name>/`.
2. **Describe it** in `<name>/extra.yaml`: kind, license, maintainers, safety, services, topics, env keys (see [The Contract](#the-contract)).
3. **Variables:** every `${VAR}` in `<name>/docker-compose.yml` gets a line in `<name>/.env.example`. `python3 scripts/check_env_example.py` checks it, and CI runs it.
4. **Config files** go in `<name>/config/`: paths in `<name>/docker-compose.yml` are relative to `<name>/`.
5. **Document it** in `<name>/README.md`, add its row to the [Services](#services) table (with its license and maturity), and its line to `.github/CODEOWNERS`.
6. **Check it:** `make validate`, then `make config`.
7. **Use it** in a project: copy `<name>/` into the project's `extras/`, add `- <name>/docker-compose.yml` under `include:` there (replacing `include: []` for the first one), append its `.env.example` to the layer's `.env` and add the profile to `COMPOSE_PROFILES`. Don't add catalog extras to this repository's own `include:`: a new project gets that file without their directories.

---

## The Contract

Every extra meets these rules, from the [AI harness design §5.3](https://github.com/raisga/p4n4-docs/blob/main/decisions/ai-harness.md#53-contract). `scripts/validate.py` checks them (`make validate`; CI runs it), against [`schema/extra.schema.json`](schema/extra.schema.json) for `extra.yaml` and directly for the rest.

- **Manifest:** `extra.yaml` declares its kind (`ingest`, `bridge`, `actuator` or `service`), license, maintainers, safety class (`read-only` or `writes-bus`), services and their profiles, the topics it publishes and subscribes to, and its env keys.
- **Opt-in:** each service in a profile of its own, `<name>` or `<name>-<suffix>`, so it starts only when `COMPOSE_PROFILES` lists it.
- **Names:** services named `<name>` or `<name>-<suffix>`, containers `p4n4-<service>`: other stacks reach them at that name on `p4n4-net`.
- **Pinned images:** an exact version, never `latest`, and pinned `FROM` lines; a built image is tagged with the extra's `version`.
- **Container hardening:** non-root, read-only root filesystem, `cap_drop: [ALL]`, `no-new-privileges`, no `privileged` or host network, a healthcheck, `restart: ${RESTART_POLICY:-unless-stopped}`.
- **Localhost-only ports** by default (`<NAME>_BIND=127.0.0.1`).
- **Hardware in the override:** devices (and GPUs) go in the layer's `docker-compose.override.yml`, shipped as `<name>/override.example.yml` and mapping only the devices `extra.yaml` declares, so the extra runs on a Raspberry Pi 5 or an x86 host without them.
- **Topics** (specs §8.6): publish only `sensors/<device-id>/<measurement>`, `alerts/<device-id>/<alert-type>` and the retained `status/<device-id>/online` heartbeat. Subscribing to `commands/…` needs safety `writes-bus`, and kind `actuator` needs it too.
- **Simulator, smoke test and health** for kinds `ingest`, `bridge` and `actuator`: `hardware.simulator` (a hardware-free stand-in for CI and p4n4-emu), an executable `smoke_test`, and a `health` URL.
- **License** from [`schema/licenses.yaml`](schema/licenses.yaml): permissive or copyleft. Anything but MIT ships its text in `<name>/LICENSE`, and copyleft is labelled in the catalog.
- **Ownership:** a `.github/CODEOWNERS` line for `/<name>/` listing its maintainers.
- **Secrets in `.env`** only, empty or placeholder values in `.env.example`.
- **No core dependency on it:** no p4n4-iot or p4n4-ai service, flow or workflow may require it. It may use core services (`p4n4-mqtt:1883`, `p4n4-influxdb:8086`, `p4n4-ollama:11434`).

Kinds `ingest`, `bridge` and `actuator` meet every rule. Kind `service` (a proxy, a VPN, a notification server: usually a third-party image) may relax a container rule it can't meet with an `exceptions:` entry in `extra.yaml`, naming the service, the rule and why. The validator rejects an exception that isn't needed.

**Maturity:** `incubating` (works for its author, passes the checks), `community` (tested by someone else on real hardware, simulator in CI) or `official` (maintained by the core team, images built and signed in CI).

---

## Project Structure

```
p4n4-extras/
├── docker-compose.yml       # The layer a project gets: include: [] (its own extras), p4n4-net
├── .env.example             # COMPOSE_PROFILES (empty) and the layer's variables
├── Makefile                 # Convenience commands
├── _template/               # The skeleton extra to copy (validated in CI)
│   ├── extra.yaml           #   its manifest
│   ├── docker-compose.yml   #   its service, in its own profile, hardened
│   ├── .env.example         #   its variables, to append to the layer's .env.example
│   ├── config/              #   its config files, mounted read-only
│   └── README.md            #   what it does and why it isn't core
├── obd2/                    # Catalog extra: OBD-II → MQTT (see its README)
├── schema/
│   ├── extra.schema.json    # extra.yaml's schema
│   └── licenses.yaml        # The license allowlist
├── scripts/
│   ├── validate.py          # CI: every extra against the contract
│   └── check_env_example.py # CI: .env.example completeness check
├── tests/                   # The validator's own tests
└── .github/CODEOWNERS       # Maintainers, one line per extra
```

---

## Usage

```bash
make help                  # Show all available commands
make up                    # Start the services in COMPOSE_PROFILES (none by default)
make down                  # Stop all services
make logs                  # Follow logs
make ps                    # Show service status
make config                # Validate docker-compose.yml, its extras, the catalog and the template
make validate              # Check every extra against the contract (scripts/validate.py)
make test                  # The validator's tests and each extra's tests (no Docker)
make smoke                 # Each extra's smoke test, in Docker
make start SERVICE=<name>  # Start one extra, listed in COMPOSE_PROFILES or not
make stop SERVICE=<name>   # Stop one extra
make clean                 # Stop services and remove their data volumes
```

---

## License

This project is licensed under the [MIT License](LICENSE).
