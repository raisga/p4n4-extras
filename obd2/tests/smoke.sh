#!/usr/bin/env bash
# ==============================================================================
# obd2 smoke test: build both images, run the bridge against the simulator and a
# throwaway broker on a network of their own, and check what reaches MQTT and the
# API. Needs Docker; touches nothing of a running p4n4. Run from anywhere.
# ==============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
compose=(docker compose -p p4n4-obd2-smoke --env-file .env.example
         -f docker-compose.yml -f tests/compose.smoke.yml --profile obd2 --profile obd2-sim)

cleanup() { "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  "${compose[@]}" logs --tail 40 >&2 || true
  exit 1
}

# First message on a topic within $2 seconds (retained ones included)
sub() {
  docker exec p4n4-obd2-smoke-mqtt mosquitto_sub -h localhost -t "$1" -C 1 -W "$2" 2>/dev/null
}

echo "==> build and start"
"${compose[@]}" up -d --build --quiet-pull

echo "==> readings"
rpm=$(sub sensors/smoke/rpm 60) || fail "no sensors/smoke/rpm within 60 s"
echo "    sensors/smoke/rpm $rpm"
[[ $rpm == *'"unit":"rpm"'* && $rpm == *'"value":'* ]] || fail "unexpected payload: $rpm"
raw=$(sub sensors/smoke/raw 10) || fail "no sensors/smoke/raw"
echo "    sensors/smoke/raw $raw"

echo "==> status (retained)"
status=$(sub status/smoke/online 5) || fail "no status/smoke/online"
echo "    status/smoke/online $status"
[[ $status == *'"vehicle":true'* ]] || fail "vehicle not connected: $status"

echo "==> API and health"
health=$(docker exec p4n4-obd2-smoke python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8090/health').read().decode())") \
  || fail "/health didn't answer"
echo "    /health $health"
[[ $health == *'"blocked_writes": 0'* ]] || fail "the guard blocked a write: $health"
for _ in $(seq 30); do
  state=$(docker inspect -f '{{.State.Health.Status}}' p4n4-obd2-smoke)
  [[ $state == healthy ]] && break
  sleep 2
done
[[ $state == healthy ]] || fail "container health is $state"

echo "==> hardening"
[[ $(docker inspect -f '{{.Config.User}} {{.HostConfig.ReadonlyRootfs}}' p4n4-obd2-smoke) == "10001:10001 true" ]] \
  || fail "not non-root with a read-only root filesystem"

echo "==> stop: the retained status says offline"
docker stop -t 10 p4n4-obd2-smoke >/dev/null
status=$(sub status/smoke/online 5) || fail "no status/smoke/online after stopping"
echo "    status/smoke/online $status"
[[ $status == '{"online":false}' ]] || fail "still online after stopping: $status"

echo "OK: obd2 smoke test passed"
