"""Static enforcement of release architecture boundaries.

These checks keep the shared agent kernel deployment-agnostic and prevent
network-discovery dependencies from entering the Docker service.

These are deliberately grep-shaped rather than AST-shaped. The point is a check
that stays obvious enough that someone tightening it later can see what it does.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _py_files(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


# --------------------------------------------------------------------------
# INV-17 · agent-core does not know about infrastructure
# --------------------------------------------------------------------------

FORBIDDEN_IN_AGENT_CORE = ("sqlalchemy", "redis", "celery", "fastapi", "app")


def _imported_roots(path: Path) -> set[str]:
    """Top-level module names imported by *path*, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import — never infrastructure
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize(
    "package", ["agent_core", "llm_router"], ids=["agent-core", "llm-router"]
)
def test_kernel_packages_do_not_import_infrastructure(package):
    """INV-17: the kernel must stay deployment-agnostic so the node can reuse it."""
    offenders = []
    for path in _py_files(REPO / "packages" / package):
        bad = _imported_roots(path) & set(FORBIDDEN_IN_AGENT_CORE)
        if bad:
            offenders.append(f"{path.relative_to(REPO)}: {sorted(bad)}")
    assert offenders == [], "INV-17 violated:\n" + "\n".join(offenders)


def test_llm_router_holds_no_agent_concepts():
    """packages/llm-router is a pure provider abstraction (03-ROADMAP M0a-1)."""
    offenders = []
    for path in _py_files(REPO / "packages" / "llm_router"):
        if "agent_core" in _imported_roots(path):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], f"llm_router must not depend on agent_core: {offenders}"


# --------------------------------------------------------------------------
# INV-09 · no LAN discovery, no node-to-node P2P
# --------------------------------------------------------------------------

# Discovery/P2P libraries turn the star topology into a lateral-movement path
# inside a customer network. Blocked at the dependency level so it cannot be
# introduced by accident.
BANNED_DEPENDENCIES = (
    "zeroconf", "pybonjour", "mdns", "bonjour", "python-zeroconf",
    "libp2p", "pyp2p", "ssdp", "upnp", "miniupnpc", "netifaces-discovery",
)


def _declared_python_dependencies() -> list[str]:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    return re.findall(r'"([A-Za-z0-9_.\-]+)[><=\[]', text)


def test_no_discovery_or_p2p_python_dependency():
    """INV-09: dependency manifest must not carry mDNS / Bonjour / P2P libraries."""
    declared = {d.lower() for d in _declared_python_dependencies()}
    banned = declared & {b.lower() for b in BANNED_DEPENDENCIES}
    assert banned == set(), f"INV-09 violated by Python dependencies: {sorted(banned)}"


@pytest.mark.parametrize("manifest", ["webui/package.json"])
def test_no_discovery_or_p2p_node_dependency(manifest):
    data = json.loads((REPO / manifest).read_text(encoding="utf-8"))
    declared = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        declared |= {k.lower() for k in (data.get(key) or {})}
    banned = declared & {b.lower() for b in BANNED_DEPENDENCIES}
    assert banned == set(), f"INV-09 violated by {manifest}: {sorted(banned)}"


# --------------------------------------------------------------------------
# Long-lived Compose services must survive a Docker daemon restart
# --------------------------------------------------------------------------

LONG_LIVED_COMPOSE_SERVICES = (
    "postgres",
    "redis",
    "api",
    "tool-runner",
    "celery_worker",
    "celery_beat",
    "webui",
)


def _compose_restart_policies(text: str) -> dict[str, str | None]:
    """Map top-level Compose service names to their `restart:` value."""
    policies: dict[str, str | None] = {}
    current: str | None = None
    in_services = False
    for line in text.splitlines():
        if line == "services:":
            in_services = True
            continue
        if in_services and line and not line.startswith((" ", "\t")):
            break
        service = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if service:
            current = service.group(1)
            policies[current] = None
            continue
        restart = re.match(r"^    restart:\s*[\"']?([^\"'\s]+)[\"']?\s*$", line)
        if restart and current is not None:
            policies[current] = restart.group(1)
    return policies


def test_long_lived_compose_services_restart_unless_stopped():
    """Postgres/Redis must come back after a Docker restart, same as API/Celery.

    A daemon reboot that only restarts API/Celery leaves them hammering dead
    backends. The one-shot migrate job stays `restart: no`.
    """
    policies = _compose_restart_policies(
        (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    )
    missing = [name for name in LONG_LIVED_COMPOSE_SERVICES if name not in policies]
    assert missing == [], f"unknown compose services: {missing}"
    offenders = [
        f"{name}={policies[name]!r}"
        for name in LONG_LIVED_COMPOSE_SERVICES
        if policies[name] != "unless-stopped"
    ]
    assert offenders == [], (
        "long-lived services must set restart: unless-stopped:\n"
        + "\n".join(offenders)
    )
    assert policies.get("migrate") == "no"


# --------------------------------------------------------------------------
# Runtime hardening — non-root, cap_drop, no-new-privileges
# --------------------------------------------------------------------------

ALL_COMPOSE_SERVICES = LONG_LIVED_COMPOSE_SERVICES + ("migrate",)
APP_COMPOSE_SERVICES = (
    "api",
    "migrate",
    "tool-runner",
    "celery_worker",
    "celery_beat",
    "webui",
)
RELEASE_DOCKERFILES = (
    ("Dockerfile", "10001:10001"),
    ("tool-runner/Dockerfile", "10001:10001"),
    ("webui/Dockerfile", "101:101"),
)


def _compose_service_blocks(text: str) -> dict[str, str]:
    """Map service name -> raw YAML body (lines under the service key)."""
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    in_services = False
    for line in text.splitlines():
        if line == "services:":
            in_services = True
            continue
        if in_services and line and not line.startswith((" ", "\t", "#")):
            break
        service = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if service:
            if current is not None:
                blocks[current] = "\n".join(buf)
            current = service.group(1)
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = "\n".join(buf)
    return blocks


def _final_user_instruction(dockerfile: str) -> str | None:
    users = re.findall(r"^USER\s+(\S+)\s*$", dockerfile, flags=re.M)
    return users[-1] if users else None


def test_release_dockerfiles_run_as_numeric_non_root():
    """A missing USER leaves the process as root inside the image."""
    for relative, expected in RELEASE_DOCKERFILES:
        text = (REPO / relative).read_text(encoding="utf-8")
        user = _final_user_instruction(text)
        assert user == expected, f"{relative} final USER={user!r}, expected {expected}"
        uid = int(expected.split(":")[0])
        assert uid != 0


def test_compose_runtime_hardening_drops_caps_and_forbids_new_privileges():
    """Every Compose service must drop capabilities and set no-new-privileges.

    Official Postgres/Redis entrypoints still start as root to gosu; they keep
    cap_drop ALL plus the few caps gosu needs. Application services also get a
    read-only rootfs.
    """
    blocks = _compose_service_blocks(
        (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    )
    missing = [name for name in ALL_COMPOSE_SERVICES if name not in blocks]
    assert missing == [], f"unknown compose services: {missing}"
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(
        r"x-app-hardening: &app-hardening\n"
        r"  cap_drop:\n"
        r"    - ALL\n"
        r"  security_opt:\n"
        r"    - no-new-privileges:true\n"
        r"  read_only: true\n",
        compose,
    )
    assert re.search(
        r"x-data-hardening: &data-hardening\n"
        r"  cap_drop:\n"
        r"    - ALL\n",
        compose,
    )
    assert "no-new-privileges:true" in compose.split("x-app-hardening", 1)[0]

    offenders = []
    for name in ALL_COMPOSE_SERVICES:
        body = blocks[name]
        uses_app = "<<: *app-hardening" in body
        uses_data = "<<: *data-hardening" in body
        inline = "cap_drop:" in body and "no-new-privileges:true" in body
        if name in ("postgres", "redis"):
            if not (uses_data or inline):
                offenders.append(f"{name}: missing data hardening")
        elif not (uses_app or inline):
            offenders.append(f"{name}: missing app hardening")
    assert offenders == [], "compose hardening gaps:\n" + "\n".join(offenders)
    ro_missing = [
        name
        for name in APP_COMPOSE_SERVICES
        if "<<: *app-hardening" not in blocks[name]
        and "read_only: true" not in blocks[name]
    ]
    assert ro_missing == [], f"app services missing read_only: {ro_missing}"


def test_webui_listens_unprivileged():
    """Non-root nginx cannot bind :80; the published host port stays 3000."""
    nginx = (REPO / "webui" / "nginx.conf").read_text(encoding="utf-8")
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r"listen\s+8080\s*;", nginx)
    assert not re.search(r"listen\s+80\s*;", nginx)
    assert re.search(r"WEBUI_PORT:-3000}:8080", compose)


# --------------------------------------------------------------------------
# INV-40 · skill scripts run in an isolated sandbox, not beside the data plane
# --------------------------------------------------------------------------

def _compose() -> dict:
    import yaml
    return yaml.safe_load((REPO / "docker-compose.yml").read_text())


def test_inv40_skill_runner_is_sandboxed():
    """INV-40: the script sandbox must not share a network with postgres/redis."""
    compose = _compose()
    services = compose["services"]
    assert "skill-runner" in services, "skill-runner service is missing"

    sandbox_nets = set(services["skill-runner"].get("networks") or [])
    assert sandbox_nets, "skill-runner must declare its networks explicitly"

    for data_service in ("postgres", "redis"):
        shared = sandbox_nets & set(services[data_service].get("networks") or [])
        assert not shared, f"skill-runner shares network {shared} with {data_service}"

    # The sandbox segment must have no route off the host network.
    for net in sandbox_nets:
        assert compose["networks"][net].get("internal") is True, (
            f"network {net} must be internal: true"
        )


def test_inv40_skill_runner_does_not_receive_the_tool_runner_token():
    services = _compose()["services"]
    env = services["skill-runner"].get("environment") or {}
    keys = set(env if isinstance(env, dict) else [e.split("=", 1)[0] for e in env])
    assert "RUNNER_TOKEN" not in keys, "skill-runner must not hold the tool-runner token"
    assert "SKILL_RUNNER_TOKEN" in keys
    assert "env_file" not in services["skill-runner"], (
        "skill-runner must not be handed the app's .env"
    )


def test_inv40_skill_runner_package_is_standalone():
    """It must not import app/agent_core, same rule tool_runner follows."""
    offenders = []
    for path in _py_files(REPO / "skill_runner"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if m.split(".")[0] in ("app", "agent_core", "tool_runner"):
                    offenders.append(f"{path.relative_to(REPO)}: {m}")
    assert offenders == [], "INV-40 violated:\n" + "\n".join(offenders)
