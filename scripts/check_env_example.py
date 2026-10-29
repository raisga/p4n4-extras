#!/usr/bin/env python3
"""
Check that all environment variables referenced in the compose files are
documented in .env.example: docker-compose.yml and the extras its `include:` lists
against the layer's .env.example, and every other extra directory (the catalog's
extras, which a project copies in, and the skeleton _template/) against its own
.env.example plus the layer's.
"""

import re
import sys
from pathlib import Path

import yaml

COMPOSE_FILE = Path("docker-compose.yml")
ENV_EXAMPLE_FILE = Path(".env.example")

# Variables provided by Docker Compose itself or hardcoded in the compose file
COMPOSE_BUILTINS: set[str] = set()


def extract_compose_vars(content: str) -> set[str]:
    """Extract all ${VAR} and ${VAR:-default} references from compose YAML."""
    return set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}", content))


def extract_env_example_vars(content: str) -> set[str]:
    """Extract all variable names defined in .env.example."""
    vars_: set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name = line.split("=", 1)[0].strip()
            if name:
                vars_.add(name)
    return vars_


def _missing(compose_files: list[Path], env_files: list[Path]) -> set[str]:
    used = set().union(*(extract_compose_vars(f.read_text()) for f in compose_files))
    documented = set().union(*(extract_env_example_vars(f.read_text()) for f in env_files))
    return used - COMPOSE_BUILTINS - documented


def included(compose: Path) -> list[Path]:
    """The compose files docker-compose.yml pulls in with `include:`."""
    entries = (yaml.safe_load(compose.read_text()) or {}).get("include") or []
    paths = []
    for entry in entries:
        # Short form "a.yml", or long form {path: "a.yml"} or {path: ["a.yml", ...]}
        found = entry if isinstance(entry, str) else entry.get("path") or []
        for path in [found] if isinstance(found, str) else found:
            paths.append(Path(path))
    return paths


def main() -> int:
    for path in (COMPOSE_FILE, ENV_EXAMPLE_FILE):
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 1

    layer = included(COMPOSE_FILE)
    checks = [([COMPOSE_FILE, *layer], [ENV_EXAMPLE_FILE], ENV_EXAMPLE_FILE)]
    for compose in sorted(Path(".").glob(f"*/{COMPOSE_FILE}")):
        if compose in layer:
            continue
        own_env = compose.parent / ENV_EXAMPLE_FILE
        envs = [ENV_EXAMPLE_FILE, *([own_env] if own_env.exists() else [])]
        checks.append(([compose], envs, own_env))

    failed = False
    for compose_files, env_files, where in checks:
        missing = _missing(compose_files, env_files)
        names = ", ".join(str(f) for f in compose_files)
        if missing:
            print(f"FAIL: Variables referenced in {names} but missing from {where}:")
            for var in sorted(missing):
                print(f"  - {var}")
            failed = True
        else:
            print(f"OK: every variable in {names} is in {where}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
