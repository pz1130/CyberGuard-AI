"""Static enforcement of the invariants that 04-INVARIANTS.md says a machine must check.

INV-08, INV-09 and INV-17 each name "CI 阻断" / "CI 静态检查" as their verification
method, and 03-ROADMAP.md makes two of them M0a-1 exit criteria. There was no CI,
so none of them were enforced anywhere. Putting them in the test suite is
stronger than a pipeline step: they run on every local `pytest` too.

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
# INV-08 · Electron security configuration must not be relaxed
# --------------------------------------------------------------------------

MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"


@pytest.mark.parametrize(
    "setting,required",
    [
        ("contextIsolation", "true"),
        ("nodeIntegration", "false"),
        ("sandbox", "true"),
    ],
)
def test_electron_webpreferences_are_locked_down(setting, required):
    """INV-08: contextIsolation on, nodeIntegration off, sandbox on."""
    source = MAIN_CJS.read_text(encoding="utf-8")
    found = re.findall(rf"\b{setting}\s*:\s*(\w+)", source)
    assert found, f"{setting} is not set at all in {MAIN_CJS.name}"
    assert set(found) == {required}, (
        f"INV-08: {setting} must be {required} everywhere, found {found}"
    )


def test_no_renderer_gets_node_or_a_remote_origin_in_production():
    """A packaged build must load from disk, never from a remote origin."""
    source = MAIN_CJS.read_text(encoding="utf-8")
    assert "webSecurity: false" not in source
    assert "allowRunningInsecureContent" not in source
    # The only loadURL is the dev server, guarded by isDev.
    for match in re.finditer(r"loadURL\(\s*[\"'`]([^\"'`]+)", source):
        url = match.group(1)
        assert url.startswith("http://127.0.0.1") or url.startswith("http://localhost"), (
            f"INV-08: unexpected remote origin loaded into a renderer: {url}"
        )


def test_preload_exposes_an_explicit_allowlist_not_the_ipc_object():
    """contextBridge must hand over named methods, never ipcRenderer itself."""
    preload = (REPO / "apps" / "desktop" / "electron" / "preload.cjs").read_text("utf-8")
    assert "exposeInMainWorld" in preload
    assert not re.search(r"exposeInMainWorld\([^,]+,\s*ipcRenderer\s*\)", preload), (
        "INV-08: the whole ipcRenderer must never be exposed to the renderer"
    )


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


@pytest.mark.parametrize(
    "manifest",
    ["apps/desktop/package.json", "webui/package.json"],
)
def test_no_discovery_or_p2p_node_dependency(manifest):
    data = json.loads((REPO / manifest).read_text(encoding="utf-8"))
    declared = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        declared |= {k.lower() for k in (data.get(key) or {})}
    banned = declared & {b.lower() for b in BANNED_DEPENDENCIES}
    assert banned == set(), f"INV-09 violated by {manifest}: {sorted(banned)}"


def test_the_node_opens_no_listening_socket():
    """INV-07: shell <-> sidecar is stdio JSONL; the node listens on nothing."""
    offenders = []
    for path in _py_files(REPO / "apps" / "desktop"):
        source = path.read_text(encoding="utf-8")
        for pattern in ("socket.bind(", ".listen(", "start_server(", "uvicorn.run("):
            if pattern in source:
                offenders.append(f"{path.relative_to(REPO)}: {pattern}")
    assert offenders == [], "INV-07: node must not listen on a port:\n" + "\n".join(
        offenders
    )
