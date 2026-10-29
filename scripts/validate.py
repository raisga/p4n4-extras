#!/usr/bin/env python3
"""
Check every extra against the contract (README.md, "The contract"): its extra.yaml
against schema/extra.schema.json, then what a schema can't express: its compose file
(profiles, names, pinned images, localhost ports, container hardening), its topics,
its files (README, LICENSE, simulator, smoke test), its CODEOWNERS entry and its row
in the README catalog.

Kinds ingest, bridge and actuator meet every container rule. Kind service may declare
exceptions in extra.yaml, each with a reason, for third-party images that can't.

Usage: python3 scripts/validate.py [<extra-dir> ...]    (default: every extra)
       python3 scripts/validate.py --smoke-tests        (list each extra's smoke_test)
Needs PyYAML and jsonschema: pip install pyyaml jsonschema
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "extra.yaml"
COMPOSE = "docker-compose.yml"
ENV_EXAMPLE = ".env.example"
OVERRIDE_EXAMPLE = "override.example.yml"
TEMPLATE_DIR = "_template"
NETWORK = "p4n4-net"
RESTART = "${RESTART_POLICY:-unless-stopped}"

# Kinds that touch hardware or the message bus meet every rule, no exceptions
STRICT_KINDS = {"ingest", "bridge", "actuator"}

# Specs §8.6: what an extra may publish. <device-id> is one topic level.
PUBLISH_PATTERNS = (
    re.compile(r"^sensors/<device-id>/(<measurement>|[a-z0-9_]+)$"),
    re.compile(r"^alerts/<device-id>/(<alert-type>|[a-z0-9_]+)$"),
    re.compile(r"^status/<device-id>/online$"),
)
HEARTBEAT = "status/<device-id>/online"

_VAR = re.compile(r"\$\$|\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-?])([^}]*))?\}")


@dataclass
class Report:
    name: str
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------------------

def read_env(path: Path) -> dict[str, str]:
    """KEY=value lines of an .env file; later files override earlier ones."""
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip("'\"")
    return env


def interpolate(text: str, env: dict[str, str]) -> str:
    """Compose's ${VAR}, ${VAR:-default}, ${VAR-default} and $$, against env."""

    def sub(m: re.Match) -> str:
        if m.group(0) == "$$":
            return "$"
        name, op, default = m.group(1), m.group(2), m.group(3) or ""
        value = env.get(name)
        if op == ":-":
            return value if value else default
        if op == "-":
            return default if value is None else value
        return value or ""

    return _VAR.sub(sub, text)


def load_licenses(root: Path) -> tuple[set[str], set[str]]:
    data = yaml.safe_load((root / "schema" / "licenses.yaml").read_text())
    return set(data["permissive"]), set(data["copyleft"])


def find_extras(root: Path) -> list[Path]:
    return sorted(
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
        and ((d / MANIFEST).exists() or (d / COMPOSE).exists())
    )


# ------------------------------------------------------------------------------
# Compose checks
# ------------------------------------------------------------------------------

def image_pinned(image: str) -> bool:
    """An exact tag (not latest) or a digest."""
    if "@sha256:" in image:
        return True
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return False
    return last.split(":", 1)[1] not in ("", "latest")


def host_ips(ports: list) -> list[str]:
    """The host address of each published port ("" = every interface)."""
    ips = []
    for p in ports or []:
        if isinstance(p, dict):
            if p.get("published") is not None:
                ips.append(str(p.get("host_ip", "")))
            continue
        spec = str(p).split("/", 1)[0]
        parts = spec.rsplit(":", 2)
        ips.append(parts[0] if len(parts) == 3 else "")
    return ips


def dockerfile_of(extra: Path, build) -> Path:
    if isinstance(build, str):
        return extra / build / "Dockerfile"
    context = extra / build.get("context", ".")
    return context / build.get("dockerfile", "Dockerfile")


def dockerfile_facts(path: Path) -> tuple[list[str], str | None]:
    """(unpinned FROM images, the last USER) of a Dockerfile."""
    unpinned, user, stages = [], None, set()
    for line in path.read_text().splitlines():
        words = line.split()
        if not words:
            continue
        if words[0].upper() == "FROM":
            args = [w for w in words[1:] if not w.startswith("--")]
            image = args[0]
            if len(args) >= 3 and args[1].upper() == "AS":
                stages.add(args[2].lower())
            if image.lower() not in stages and "$" not in image and not image_pinned(image):
                unpinned.append(image)
        elif words[0].upper() == "USER" and len(words) > 1:
            user = words[1]
    return unpinned, user


def is_root(user) -> bool:
    return str(user).split(":", 1)[0] in ("root", "0")


def container_rules(extra: Path, svc: dict) -> dict[str, str | None]:
    """Each hardening rule mapped to None (met) or what's wrong."""
    user = svc.get("user")
    if user is None and "build" in svc:
        dockerfile = dockerfile_of(extra, svc["build"])
        if dockerfile.exists():
            user = dockerfile_facts(dockerfile)[1]
    hc = svc.get("healthcheck")
    sec = [str(s).replace(" ", "") for s in svc.get("security_opt", [])]
    return {
        "non-root": None if user is not None and not is_root(user)
        else "runs as root: set `user:` (or USER in its Dockerfile) to a non-root id",
        "read-only-rootfs": None if svc.get("read_only") is True
        else "root filesystem is writable: set `read_only: true` (tmpfs for /tmp)",
        "cap-drop-all": None if "ALL" in svc.get("cap_drop", [])
        else "capabilities kept: set `cap_drop: [ALL]`",
        "cap-add": None if not svc.get("cap_add")
        else f"adds capabilities {svc['cap_add']}",
        "no-new-privileges": None if "no-new-privileges:true" in sec
        else 'set `security_opt: ["no-new-privileges:true"]`',
        "privileged": None if not svc.get("privileged") else "runs privileged",
        "host-network": None if svc.get("network_mode") != "host" else "uses the host network",
        "healthcheck": None if hc and not hc.get("disable")
        else "no healthcheck",
        "localhost-ports": None if all(ip == "127.0.0.1" for ip in host_ips(svc.get("ports")))
        else "publishes a port beyond 127.0.0.1 by default: use ${<NAME>_BIND:-127.0.0.1}",
    }


def check_compose(extra: Path, root: Path, m: dict, r: Report) -> None:
    path = extra / COMPOSE
    if not path.exists():
        r.errors.append(f"{COMPOSE} is missing")
        return
    env = {**read_env(root / ENV_EXAMPLE), **read_env(extra / ENV_EXAMPLE)}
    raw = yaml.safe_load(path.read_text()) or {}
    compose = yaml.safe_load(interpolate(path.read_text(), env)) or {}
    services = compose.get("services") or {}
    declared = {s["name"]: s for s in m["services"]}
    name, version = m["name"], m["version"]

    for missing in sorted(set(declared) - set(services)):
        r.errors.append(f"extra.yaml declares service {missing}, {COMPOSE} doesn't have it")
    for extra_svc in sorted(set(services) - set(declared)):
        r.errors.append(f"service {extra_svc} isn't declared in extra.yaml `services`")

    net = (compose.get("networks") or {}).get(NETWORK) or {}
    if not (net.get("external") is True and net.get("name") == NETWORK):
        r.errors.append(f"networks.{NETWORK} must be `external: true` with `name: {NETWORK}`")

    exceptions = {(e["service"], e["rule"]) for e in m.get("exceptions", [])}
    used: set[tuple[str, str]] = set()

    for s, svc in services.items():
        if s not in declared:
            continue
        where = f"service {s}"
        if s != name and not s.startswith(name + "-"):
            r.errors.append(f"{where}: name must be {name} or start with {name}-")
        profile = declared[s]["profile"]
        if profile != name and not profile.startswith(name + "-"):
            r.errors.append(f"{where}: profile {profile} must be {name} or start with {name}-")
        if svc.get("profiles") != [profile]:
            r.errors.append(f"{where}: `profiles` must be [{profile}]")
        if svc.get("container_name") != f"p4n4-{s}":
            r.errors.append(f"{where}: container_name must be p4n4-{s}")

        image = svc.get("image")
        if not image:
            r.errors.append(f"{where}: no `image`")
        elif not image_pinned(str(image)):
            r.errors.append(f"{where}: image {image} isn't pinned to an exact version")
        if "build" in svc:
            if image and not str(image).endswith(f":{version}"):
                r.errors.append(f"{where}: a built image is tagged with the extra's version ({version})")
            dockerfile = dockerfile_of(extra, svc["build"])
            if not dockerfile.exists():
                r.errors.append(f"{where}: {dockerfile.relative_to(extra)} not found")
            else:
                for base in dockerfile_facts(dockerfile)[0]:
                    r.errors.append(f"{where}: FROM {base} isn't pinned to an exact version")

        if (raw.get("services") or {}).get(s, {}).get("restart") != RESTART:
            r.errors.append(f"{where}: `restart` must be {RESTART}")
        nets = svc.get("networks") or []
        if NETWORK not in nets:
            r.errors.append(f"{where}: must join {NETWORK}")
        if svc.get("devices"):
            r.errors.append(
                f"{where}: devices belong in the layer's docker-compose.override.yml "
                f"(ship the snippet as {OVERRIDE_EXAMPLE}), so it runs without the hardware"
            )

        for rule, problem in container_rules(extra, svc).items():
            if (s, rule) in exceptions:
                used.add((s, rule))
                if problem is None:
                    r.errors.append(f"{where}: exception for {rule} isn't needed, remove it")
                else:
                    r.notes.append(f"{where}: {rule} excepted")
            elif problem:
                r.errors.append(f"{where}: {problem} ({rule})")

    for s, rule in sorted(exceptions - used):
        r.errors.append(f"exception for {s} / {rule}: no such service")


def check_override(extra: Path, m: dict, r: Report) -> None:
    path = extra / OVERRIDE_EXAMPLE
    if not path.exists():
        return
    envs = {d["env"] for d in m.get("hardware", {}).get("devices", [])}
    data = yaml.safe_load(path.read_text()) or {}
    for s, svc in (data.get("services") or {}).items():
        for dev in (svc or {}).get("devices", []):
            text = dev if isinstance(dev, str) else str(dev.get("source", ""))
            if not any(f"${{{e}" in text for e in envs):
                r.errors.append(
                    f"{OVERRIDE_EXAMPLE}: device {text} on {s} isn't one of hardware.devices "
                    f"({', '.join(sorted(envs)) or 'none declared'})"
                )


# ------------------------------------------------------------------------------
# Manifest checks
# ------------------------------------------------------------------------------

def check_topics(m: dict, r: Report) -> None:
    data = m.get("data", {})
    publishes = [t["pattern"] for t in data.get("publishes", [])]
    for pattern in publishes:
        if not any(p.match(pattern) for p in PUBLISH_PATTERNS):
            r.errors.append(
                f"publishes {pattern}: only sensors/<device-id>/<measurement>, "
                f"alerts/<device-id>/<alert-type> and {HEARTBEAT} (specs §8.6)"
            )
    for t in data.get("subscribes", []):
        if t["pattern"].startswith("commands/") and m["safety"] != "writes-bus":
            r.errors.append(f"subscribes to {t['pattern']}: needs safety writes-bus")
    if m["kind"] in STRICT_KINDS and HEARTBEAT not in publishes:
        r.errors.append(f"kind {m['kind']} must publish the {HEARTBEAT} heartbeat")
    hb = next((t for t in data.get("publishes", []) if t["pattern"] == HEARTBEAT), None)
    if hb is not None and not hb.get("retained"):
        r.errors.append(f"{HEARTBEAT} must be retained")


def check_files(extra: Path, m: dict, r: Report) -> None:
    strict = m["kind"] in STRICT_KINDS
    if not (extra / "README.md").exists():
        r.errors.append("README.md is missing")

    sim = m.get("hardware", {}).get("simulator")
    if sim is None:
        if strict:
            r.errors.append(f"kind {m['kind']} needs hardware.simulator, for CI and p4n4-emu")
    elif not (extra / sim).is_dir():
        r.errors.append(f"hardware.simulator {sim} isn't a directory")

    smoke = m.get("smoke_test")
    if smoke is None:
        if strict:
            r.errors.append(f"kind {m['kind']} needs a smoke_test")
    elif not (extra / smoke).is_file():
        r.errors.append(f"smoke_test {smoke} not found")
    elif not os.access(extra / smoke, os.X_OK):
        r.errors.append(f"smoke_test {smoke} isn't executable (chmod +x)")

    if strict and not m["services"][0].get("health"):
        r.errors.append(f"service {m['services'][0]['name']} needs a `health` URL")


def check_env(extra: Path, m: dict, r: Report) -> None:
    documented = set(read_env(extra / ENV_EXAMPLE))
    env = m.get("env", {})
    keys = [*env.get("required", []), *env.get("optional", [])]
    for key in keys:
        if key not in documented:
            r.errors.append(f"env key {key} isn't in {ENV_EXAMPLE}")
    for name in [m.get("data", {}).get("device_id_env")] + [
        d["env"] for d in m.get("hardware", {}).get("devices", [])
    ]:
        if name and name not in keys:
            r.errors.append(f"{name} must be listed under env.required or env.optional")


def check_catalog(extra: Path, root: Path, m: dict, permissive: set, copyleft: set, r: Report) -> None:
    license_ = m["license"]
    if license_ not in permissive | copyleft:
        r.errors.append(f"license {license_} isn't on the allowlist (schema/licenses.yaml)")
    elif license_ in copyleft:
        r.notes.append(f"copyleft: {license_}")
    if license_ != "MIT" and not (extra / "LICENSE").exists():
        r.errors.append(f"{license_} differs from the repository's MIT: ship its text in LICENSE")
    if m["kind"] == "actuator" and m["safety"] != "writes-bus":
        r.errors.append("kind actuator needs safety writes-bus")
    if m["kind"] in STRICT_KINDS and m.get("exceptions"):
        r.errors.append(f"kind {m['kind']} can't declare exceptions: only kind service may")

    if extra.name == TEMPLATE_DIR:
        return
    if m["name"] != extra.name:
        r.errors.append(f"name {m['name']} must match its directory, {extra.name}")

    owners = root / ".github" / "CODEOWNERS"
    lines = owners.read_text().splitlines() if owners.exists() else []
    entry = next((ln.split() for ln in lines if ln.split()[:1] == [f"/{extra.name}/"]), None)
    if entry is None:
        r.errors.append(f".github/CODEOWNERS has no /{extra.name}/ line")
    else:
        for handle in m["maintainers"]:
            if f"@{handle}" not in entry:
                r.errors.append(f".github/CODEOWNERS /{extra.name}/ doesn't list @{handle}")

    readme = (root / "README.md").read_text() if (root / "README.md").exists() else ""
    rows = [ln for ln in readme.splitlines() if ln.startswith("|") and f"`{m['name']}`" in ln]
    if not any(license_ in row and m["maturity"] in row for row in rows):
        r.errors.append(
            f"README.md's Services table needs a row for `{m['name']}` with its "
            f"license ({license_}) and maturity ({m['maturity']})"
        )


def check_extra(extra: Path, root: Path = ROOT) -> Report:
    r = Report(extra.name)
    path = extra / MANIFEST
    if not path.exists():
        r.errors.append(f"{MANIFEST} is missing (copy and fill in {TEMPLATE_DIR}/{MANIFEST})")
        return r
    try:
        m = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        r.errors.append(f"{MANIFEST}: {e}")
        return r

    schema = json.loads((root / "schema" / "extra.schema.json").read_text())
    problems = sorted(Draft202012Validator(schema).iter_errors(m), key=lambda e: list(e.path))
    for e in problems:
        loc = "/".join(str(p) for p in e.path) or "(top)"
        r.errors.append(f"{MANIFEST}: {loc}: {e.message}")
    if problems:
        return r

    permissive, copyleft = load_licenses(root)
    check_catalog(extra, root, m, permissive, copyleft, r)
    check_topics(m, r)
    check_files(extra, m, r)
    check_env(extra, m, r)
    check_compose(extra, root, m, r)
    check_override(extra, m, r)
    return r


def smoke_tests(root: Path = ROOT) -> list[Path]:
    """Each extra's smoke_test, for `make smoke` and CI."""
    tests = []
    for extra in find_extras(root):
        path = extra / MANIFEST
        smoke = (yaml.safe_load(path.read_text()) or {}).get("smoke_test") if path.exists() else None
        if smoke:
            tests.append(extra / smoke)
    return tests


def main(argv: list[str], root: Path = ROOT) -> int:
    if argv[:1] == ["--smoke-tests"]:
        for path in smoke_tests(root):
            print(path.relative_to(root))
        return 0
    extras = [Path(a).resolve() for a in argv] if argv else find_extras(root)
    failed = False
    for extra in extras:
        r = check_extra(extra, root)
        notes = f" ({'; '.join(r.notes)})" if r.notes else ""
        if r.errors:
            failed = True
            print(f"FAIL: {r.name}{notes}")
            for err in r.errors:
                print(f"  - {err}")
        else:
            print(f"OK: {r.name}{notes}")
    if not extras:
        print("OK: no extras to check")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
