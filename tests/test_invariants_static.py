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
