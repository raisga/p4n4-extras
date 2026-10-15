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

None yet: this stack ships the structure and [the skeleton extra](#adding-an-extra). Projects add their own, and the catalog of community extras (OBD-II, Modbus, CAN bus, …) planned in p4n4-docs' [AI harness design](https://github.com/raisga/p4n4-docs/blob/main/decisions/ai-harness.md#5-extras-community-stacks) will live here, one directory each. The [`mqtt-influx-grafana-ollama-go2rtc`](https://github.com/raisga/p4n4-templates/tree/main/projects/mqtt-influx-grafana-ollama-go2rtc) template runs go2rtc video and a device uplink as its extras layer.

| Extra | Profile | Port | Description |
|-------|---------|------|-------------|
| — | — | — | — |

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

Each extra is a directory of its own, and `docker-compose.yml` pulls it in with [`include:`](https://docs.docker.com/compose/how-tos/multiple-compose-files/include/), so every extra runs in this one Compose project, on `p4n4-net`, with one `.env`. [`_template/`](_template/) is a complete, valid extra to start from:

1. **Copy it:** `cp -r _template <name>`, then rename `my-extra` and `MY_EXTRA` everywhere in `<name>/`.
2. **Include it:** add `- <name>/docker-compose.yml` under `include:` in `docker-compose.yml` (replace `include: []` for the first one).
3. **Variables:** append `<name>/.env.example` to `.env.example` and add the profile to its `Available:` list. Variables in an included file resolve from this layer's `.env`. `python3 scripts/check_env_example.py` checks every `${VAR}` has a line, and CI runs it.
4. **Config files** go in `<name>/config/`: paths in `<name>/docker-compose.yml` are relative to `<name>/`.
5. **Document it** in `<name>/README.md` and the [Services](#services) table above.
6. **Check it:** `make config`, then `COMPOSE_PROFILES=<name> make up`.

The rules the template follows:

- **Opt-in:** `profiles: [<name>]`, so it starts only when `COMPOSE_PROFILES` lists it.
- **Pinned image:** an exact version, never `latest`.
- **Container name `p4n4-<name>`:** other stacks reach it at that name on `p4n4-net`.
- **Localhost-only ports** by default (`<NAME>_BIND=127.0.0.1`), unless the service is meant to be reached from the network.
- **Secrets in `.env`** only, empty or placeholder values in `.env.example`.
- **No core dependency on it:** don't make a p4n4-iot or p4n4-ai service, flow or workflow require it. It may use core services (`p4n4-mqtt:1883`, `p4n4-influxdb:8086`, `p4n4-ollama:11434`).
- **Hardware-specific settings** (a GPU, a device) go in `docker-compose.override.yml`, so the extra still runs on a Raspberry Pi 5 or an x86 host without them.

---

## Project Structure

```
p4n4-extras/
├── docker-compose.yml       # include: one line per extra (none yet), and p4n4-net
├── .env.example             # COMPOSE_PROFILES (empty) and every extra's variables
├── Makefile                 # Convenience commands
├── _template/               # The skeleton extra to copy (validated in CI)
│   ├── docker-compose.yml   #   its service, in its own profile
│   ├── .env.example         #   its variables, to append to ../.env.example
│   ├── config/              #   its config files, mounted read-only
│   └── README.md            #   what it does and why it isn't core
└── scripts/
    └── check_env_example.py # CI: .env.example completeness check
```

---

## Usage

```bash
make help                  # Show all available commands
make up                    # Start the services in COMPOSE_PROFILES (none by default)
make down                  # Stop all services
make logs                  # Follow logs
make ps                    # Show service status
make config                # Validate docker-compose.yml, its extras and the template
make start SERVICE=<name>  # Start one extra, listed in COMPOSE_PROFILES or not
make stop SERVICE=<name>   # Stop one extra
make clean                 # Stop services and remove their data volumes
```

---

## License

This project is licensed under the [MIT License](LICENSE).
