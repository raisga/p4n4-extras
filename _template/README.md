# my-extra

One paragraph: what it does, and why it's an extra rather than part of the core (p4n4
works without it).

| | |
|---|---|
| Profile | `my-extra` |
| Container | `p4n4-my-extra` |
| Image | `example/my-extra:1.0.0` |
| Ports | `9999` on `127.0.0.1` (`MY_EXTRA_BIND`, `MY_EXTRA_PORT`) |
| Uses | Core services it talks to, e.g. `p4n4-mqtt:1883`, `p4n4-influxdb:8086` |
| Hardware | Devices or accelerators it needs, set in `docker-compose.override.yml`; none |

## Settings

The variables it reads from the layer's `.env` (see `.env.example`).

## Check it

```bash
COMPOSE_PROFILES=my-extra docker compose up -d   # in the extras layer
curl -s localhost:9999/health
```
