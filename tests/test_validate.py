"""scripts/validate.py: the repository passes, and each broken rule is caught.

Each test copies the real extras into a temporary repository (obd2 as the valid
ingest extra, _template as the valid service one), breaks one thing and checks
the validator says so.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("validate", ROOT / "scripts" / "validate.py")
validate = importlib.util.module_from_spec(_spec)
sys.modules["validate"] = validate   # dataclasses look their module up there
_spec.loader.exec_module(validate)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for name in ("schema", "_template", "obd2", ".github"):
        shutil.copytree(ROOT / name, tmp_path / name)
    for name in (".env.example", "docker-compose.yml", "README.md"):
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


def errors(repo: Path, extra: str) -> list[str]:
    return validate.check_extra(repo / extra, repo).errors


def edit_yaml(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def edit_text(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new))


def has(errs: list[str], fragment: str) -> bool:
    return any(fragment in e for e in errs)


# ---- the repository itself ---------------------------------------------------

def test_the_repository_passes(capsys):
    assert validate.main([]) == 0
    out = capsys.readouterr().out
    assert "OK: obd2 (copyleft: GPL-2.0-only)" in out and "OK: _template" in out


def test_the_copies_pass(repo):
    assert errors(repo, "obd2") == []
    assert errors(repo, "_template") == []


def test_lists_smoke_tests(repo):
    assert validate.smoke_tests(repo) == [repo / "obd2" / "tests" / "smoke.sh"]


# ---- manifest ----------------------------------------------------------------

def test_missing_manifest(repo):
    (repo / "obd2" / "extra.yaml").unlink()
    assert has(errors(repo, "obd2"), "extra.yaml is missing")


def test_schema_errors_are_reported(repo):
    edit_yaml(repo / "obd2" / "extra.yaml", lambda m: m.update(kind="sensor", version="one"))
    errs = errors(repo, "obd2")
    assert has(errs, "kind: 'sensor' is not one of") and has(errs, "version:")


def test_name_matches_directory(repo):
    shutil.move(repo / "obd2", repo / "obd3")
    assert has(errors(repo, "obd3"), "must match its directory")


def test_license_allowlist_and_text(repo):
    edit_yaml(repo / "obd2" / "extra.yaml", lambda m: m.update(license="CC-BY-NC-SA-4.0"))
    assert has(errors(repo, "obd2"), "isn't on the allowlist")
    edit_yaml(repo / "obd2" / "extra.yaml", lambda m: m.update(license="Apache-2.0"))
    (repo / "obd2" / "LICENSE").unlink()
    assert has(errors(repo, "obd2"), "ship its text in LICENSE")


def test_codeowners_and_catalog_row(repo):
    (repo / ".github" / "CODEOWNERS").write_text("* @jraleman\n")
    edit_text(repo / "README.md", "| incubating | GPL-2.0-only", "| community | GPL-2.0-only")
    errs = errors(repo, "obd2")
    assert has(errs, "CODEOWNERS has no /obd2/ line")
    assert has(errs, "needs a row for `obd2`")


def test_actuator_needs_writes_bus(repo):
    edit_yaml(repo / "obd2" / "extra.yaml", lambda m: m.update(kind="actuator"))
    assert has(errors(repo, "obd2"), "kind actuator needs safety writes-bus")


# ---- topics ------------------------------------------------------------------

def test_publish_patterns(repo):
    def change(m):
        m["data"]["publishes"].append({"pattern": "inference/<device-id>/result"})
        m["data"]["publishes"].append({"pattern": "car/rpm"})
    edit_yaml(repo / "obd2" / "extra.yaml", change)
    errs = errors(repo, "obd2")
    assert has(errs, "publishes inference/<device-id>/result") and has(errs, "publishes car/rpm")


def test_commands_need_writes_bus(repo):
    edit_yaml(repo / "obd2" / "extra.yaml",
              lambda m: m["data"].update(subscribes=[{"pattern": "commands/<device-id>/clear"}]))
    assert has(errors(repo, "obd2"), "needs safety writes-bus")


def test_ingest_needs_a_retained_heartbeat(repo):
    def drop(m):
        m["data"]["publishes"] = [t for t in m["data"]["publishes"] if not t["pattern"].startswith("status/")]
    edit_yaml(repo / "obd2" / "extra.yaml", drop)
    assert has(errors(repo, "obd2"), "must publish the status/<device-id>/online heartbeat")
    shutil.copy(ROOT / "obd2" / "extra.yaml", repo / "obd2" / "extra.yaml")
    def unretain(m):
        for t in m["data"]["publishes"]:
            t.pop("retained", None)
    edit_yaml(repo / "obd2" / "extra.yaml", unretain)
    assert has(errors(repo, "obd2"), "must be retained")


# ---- files -------------------------------------------------------------------

def test_ingest_needs_simulator_smoke_test_and_health(repo):
    def change(m):
        del m["hardware"]["simulator"], m["smoke_test"], m["services"][0]["health"]
    edit_yaml(repo / "obd2" / "extra.yaml", change)
    errs = errors(repo, "obd2")
    assert has(errs, "needs hardware.simulator") and has(errs, "needs a smoke_test")
    assert has(errs, "needs a `health` URL")


def test_smoke_test_must_be_executable(repo):
    (repo / "obd2" / "tests" / "smoke.sh").chmod(0o644)
    assert has(errors(repo, "obd2"), "isn't executable")


def test_env_keys_documented(repo):
    edit_yaml(repo / "obd2" / "extra.yaml", lambda m: m["env"]["optional"].append("OBD_TURBO"))
    assert has(errors(repo, "obd2"), "env key OBD_TURBO isn't in .env.example")


# ---- compose -----------------------------------------------------------------

def test_unpinned_images(repo):
    edit_text(repo / "_template" / "docker-compose.yml", "example/my-extra:1.0.0", "example/my-extra:latest")
    edit_text(repo / "obd2" / "service" / "Dockerfile", "python:3.13.16-slim-trixie", "python")
    assert has(errors(repo, "_template"), "isn't pinned")
    assert has(errors(repo, "obd2"), "FROM python isn't pinned")


def test_built_image_carries_the_version(repo):
    edit_text(repo / "obd2" / "docker-compose.yml", "p4n4-obd2:0.1.0", "p4n4-obd2:0.0.9")
    assert has(errors(repo, "obd2"), "tagged with the extra's version (0.1.0)")


def test_names_profiles_and_containers(repo):
    def change(c):
        svc = c["services"]["obd2"]
        svc["container_name"] = "obd2"
        svc["profiles"] = ["car"]
    edit_yaml(repo / "obd2" / "docker-compose.yml", change)
    errs = errors(repo, "obd2")
    assert has(errs, "container_name must be p4n4-obd2") and has(errs, "`profiles` must be [obd2]")


def test_undeclared_service(repo):
    edit_yaml(repo / "obd2" / "docker-compose.yml",
              lambda c: c["services"].update(obd2_extra=c["services"]["obd2-sim"]))
    assert has(errors(repo, "obd2"), "isn't declared in extra.yaml")


def test_ports_bound_beyond_localhost(repo):
    edit_text(repo / "obd2" / "docker-compose.yml", "${OBD2_BIND:-127.0.0.1}:", "")
    assert has(errors(repo, "obd2"), "(localhost-ports)")
    # The default in .env.example counts too
    shutil.copy(ROOT / "obd2" / "docker-compose.yml", repo / "obd2" / "docker-compose.yml")
    edit_text(repo / "obd2" / ".env.example", "OBD2_BIND=127.0.0.1", "OBD2_BIND=0.0.0.0")
    assert has(errors(repo, "obd2"), "(localhost-ports)")


def test_hardening_is_strict_for_ingest(repo):
    edit_text(repo / "obd2" / "docker-compose.yml", "    read_only: true\n    tmpfs: [/tmp]\n", "")
    assert has(errors(repo, "obd2"), "(read-only-rootfs)")
    def excuse(m):
        m["exceptions"] = [{"service": "obd2", "rule": "read-only-rootfs", "reason": "it writes a cache to /app"}]
    edit_yaml(repo / "obd2" / "extra.yaml", excuse)
    assert has(errors(repo, "obd2"), "can't declare exceptions")


def test_root_user_detected_from_the_dockerfile(repo):
    edit_text(repo / "obd2" / "service" / "Dockerfile", "USER 10001:10001", "USER root")
    assert has(errors(repo, "obd2"), "(non-root)")


def test_service_kind_may_declare_exceptions(repo):
    edit_text(repo / "_template" / "docker-compose.yml", '    user: "10001:10001"\n', "")
    assert has(errors(repo, "_template"), "(non-root)")
    edit_yaml(repo / "_template" / "extra.yaml", lambda m: m.update(
        exceptions=[{"service": "my-extra", "rule": "non-root", "reason": "upstream image chowns /data as root"}]))
    r = validate.check_extra(repo / "_template", repo)
    assert r.errors == [] and "service my-extra: non-root excepted" in r.notes


def test_unneeded_exception(repo):
    edit_yaml(repo / "_template" / "extra.yaml", lambda m: m.update(
        exceptions=[{"service": "my-extra", "rule": "privileged", "reason": "just in case it needs it"}]))
    assert has(errors(repo, "_template"), "exception for privileged isn't needed")


def test_restart_policy_and_network(repo):
    def change(c):
        c["services"]["obd2"]["restart"] = "always"
        c["networks"]["p4n4-net"]["external"] = False
    edit_yaml(repo / "obd2" / "docker-compose.yml", change)
    errs = errors(repo, "obd2")
    assert has(errs, "`restart` must be") and has(errs, "must be `external: true`")


def test_devices_belong_in_the_override(repo):
    edit_yaml(repo / "obd2" / "docker-compose.yml",
              lambda c: c["services"]["obd2"].update(devices=["/dev/ttyUSB0:/dev/ttyUSB0"]))
    assert has(errors(repo, "obd2"), "devices belong in the layer's docker-compose.override.yml")


def test_override_maps_only_declared_devices(repo):
    edit_yaml(repo / "obd2" / "override.example.yml",
              lambda c: c["services"]["obd2"]["devices"].append("/dev/ttyACM0:/dev/ttyACM0"))
    assert has(errors(repo, "obd2"), "device /dev/ttyACM0:/dev/ttyACM0 on obd2 isn't one of hardware.devices")


# ---- helpers -----------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("${A}", "1"), ("${A:-x}", "1"), ("${EMPTY:-x}", "x"), ("${EMPTY-x}", ""),
    ("${MISSING-x}", "x"), ("${MISSING}", ""), ("$${A}", "${A}"), ("a${A}b", "a1b"),
])
def test_interpolate(text, expected):
    assert validate.interpolate(text, {"A": "1", "EMPTY": ""}) == expected


@pytest.mark.parametrize("ports, ips", [
    (["127.0.0.1:80:80"], ["127.0.0.1"]),
    (["80:80"], [""]),
    (["80"], [""]),
    (["127.0.0.1:53:53/udp"], ["127.0.0.1"]),
    ([{"target": 80, "published": 8080, "host_ip": "127.0.0.1"}], ["127.0.0.1"]),
    ([{"target": 80, "published": 8080}], [""]),
    ([{"target": 80}], []),
])
def test_host_ips(ports, ips):
    assert validate.host_ips(ports) == ips


@pytest.mark.parametrize("image, pinned", [
    ("eclipse-mosquitto:2.0.22", True), ("ghcr.io/raisga/p4n4-obd2:0.1.0", True),
    ("localhost:5000/x:1.2", True), ("caddy@sha256:abc", True),
    ("python", False), ("python:latest", False), ("localhost:5000/x", False),
])
def test_image_pinned(image, pinned):
    assert validate.image_pinned(image) is pinned
