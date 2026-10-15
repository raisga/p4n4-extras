#!/usr/bin/env python3
"""
Check that all environment variables referenced in the compose files are
documented in .env.example: docker-compose.yml and every extra it can include
(<name>/docker-compose.yml) against the layer's .env.example, and the skeleton
extra (_template/) against its own .env.example plus the layer's.
"""

import re
import sys
from pathlib import Path

COMPOSE_FILE = Path("docker-compose.yml")
ENV_EXAMPLE_FILE = Path(".env.example")
TEMPLATE_DIR = Path("_template")

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


def main() -> int:
    for path in (COMPOSE_FILE, ENV_EXAMPLE_FILE):
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 1

    extras = sorted(
        p for p in Path(".").glob(f"*/{COMPOSE_FILE}") if p.parent != TEMPLATE_DIR
    )
    checks = [([COMPOSE_FILE, *extras], [ENV_EXAMPLE_FILE], ENV_EXAMPLE_FILE)]
    template = TEMPLATE_DIR / COMPOSE_FILE
    if template.exists():
        template_env = TEMPLATE_DIR / ENV_EXAMPLE_FILE
        envs = [ENV_EXAMPLE_FILE, *([template_env] if template_env.exists() else [])]
        checks.append(([template], envs, template_env))

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
