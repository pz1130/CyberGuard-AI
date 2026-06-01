# Multi-Worker Phase 3 + 4 — MCP STDIO → tool-runner, then flip workers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate STDIO MCP server hosting (the live subprocess table) from the API/Celery workers into the single `tool-runner` process, turn `mcp_executor` into a thin HTTP client, then flip the API to multiple uvicorn workers.

**Architecture:** `tool-runner` gains `tool_runner/mcp_host.py` which owns the authoritative `_live_processes` table and exposes start/stop/status/rpc over token-authenticated endpoints. `app/services/mcp_executor.py` becomes a thin client: it decrypts per-server env (the tool-runner has no encryption key), then proxies STDIO start/stop/status/call/discovery to the tool-runner over HTTP; HTTP-transport MCP stays in-process (already stateless, worker-safe). With no worker holding subprocess handles, the API runs `--workers N`.

**Tech Stack:** Python 3.11, FastAPI (tool-runner), `httpx` (client → tool-runner), `asyncio.subprocess`, `unittest` / `fastapi.testclient.TestClient`.

**Scope note:** Phases 3 + 4 of the multi-worker unblock (spec: `docs/superpowers/specs/2026-06-01-multi-worker-unblock-design.md`). **Decision revised during planning:** only **STDIO** relocates to tool-runner; **HTTP MCP stays in-process** (it has no multi-worker problem, and tool-runner lacks `httpx`/SSRF/encryption). The worker flip (Phase 4) is the last task and must run only after Phases 1, 2, and 3 are all merged.

**Run tests with:**
- tool-runner: `python -m unittest tests.test_tool_runner_mcp_host tests.test_tool_runner_endpoints -v`
- client: `python -m unittest tests.test_mcp_executor_client -v`

---

## Key constraints discovered (read before starting)

1. **tool-runner is minimal and isolated.** `tool_runner/main.py` is a standalone FastAPI app with only `fastapi`+`uvicorn` installed. It has **no `app/` package, no `ENCRYPTION_KEY`, no DB**. So decryption of `env_vars_encrypted` happens **client-side** (in `mcp_executor`); the client sends already-decrypted per-server env to tool-runner.
2. **Validation must be server-side.** `_validate_command` checks the binary exists and is executable **on the host that spawns it** — now tool-runner. So command/arg validation + env sanitisation live in `tool_runner/mcp_host.py`, not the client.
3. **Operational implication:** any STDIO MCP server binary must be present **in the tool-runner image**, not the API image. (Documented in Task 5; installing specific binaries is out of scope — depends on which MCP servers are configured.)
4. **The router touches `_live_processes` directly** in two spots — the status check and the `tools/list` discovery JSON-RPC (`app/routers/mcp.py` `_discover_tools_via_jsonrpc`). Both STDIO paths must become client proxies (Task 4). HTTP discovery stays.
5. **Client config:** `TOOL_RUNNER_URL` / `RUNNER_TOKEN` are read from `os.environ` exactly as `app/services/tool_executor.py` already does (header `X-Runner-Token`).

---

## File Structure

- `tool_runner/mcp_host.py` — **new.** Authoritative STDIO subprocess table + validation + spawn + generic JSON-RPC. No `app/` imports.
- `tool_runner/main.py` — **modify.** Add `/mcp/start`, `/mcp/stop`, `/mcp/status`, `/mcp/rpc` endpoints (token-auth) delegating to `mcp_host`.
- `app/services/mcp_executor.py` — **rewrite.** Thin client: decrypt env, proxy STDIO ops to tool-runner; keep `execute_http_tool` and `execute_mcp_tool` (HTTP path unchanged). Remove `_live_processes` + the validation helpers (moved to tool-runner).
- `app/routers/mcp.py` — **modify.** Drop `_live_processes` import; STDIO status-check and STDIO discovery go through client proxies.
- `Dockerfile` — **modify.** API CMD honours `${API_WORKERS}`.
- `docker-compose.yml` — **modify.** Add `API_WORKERS` to the api service env.
- `tests/fixtures/echo_mcp_server.py` — **new.** Tiny JSON-RPC echo server for tool-runner tests.
- `tests/test_tool_runner_mcp_host.py`, `tests/test_tool_runner_endpoints.py`, `tests/test_mcp_executor_client.py` — **new.**

---

## Task 1: `tool_runner/mcp_host.py` — STDIO hosting core

**Files:**
- Create: `tool_runner/mcp_host.py`
- Create: `tests/fixtures/echo_mcp_server.py`
- Test: `tests/test_tool_runner_mcp_host.py`

- [ ] **Step 1: Write the echo fixture and the failing tests**

Create `tests/fixtures/echo_mcp_server.py`:
```python
"""Minimal JSON-RPC echo 'MCP server' for tests: echoes params back as result."""
import sys
import json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except Exception:
        continue
    resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"echo": req.get("params", {})}}
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
```

Create `tests/test_tool_runner_mcp_host.py`:
```python
import os
import sys
import unittest

from tool_runner import mcp_host

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "echo_mcp_server.py")


class TestMcpHost(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        # Clean up any spawned servers between tests.
        for name in list(mcp_host._live_processes):
            await mcp_host.stop_server(name)

    async def test_start_status_stop_lifecycle(self):
        ok = await mcp_host.start_server("sleeper", "/bin/sleep", ["30"], {})
        self.assertTrue(ok)
        self.assertTrue(mcp_host.is_running("sleeper"))
        await mcp_host.stop_server("sleeper")
        self.assertFalse(mcp_host.is_running("sleeper"))

    async def test_start_rejects_bad_command(self):
        ok = await mcp_host.start_server("bad", "relative/path", [], {})
        self.assertFalse(ok)
        self.assertFalse(mcp_host.is_running("bad"))

    async def test_rpc_echo_roundtrip(self):
        result = await mcp_host.rpc(
            name="echo",
            command=sys.executable,
            args=[_FIXTURE],
            env={},
            method="tools/call",
            params={"name": "x", "arguments": {"a": 1}},
            timeout=10,
        )
        self.assertEqual(result, {"echo": {"name": "x", "arguments": {"a": 1}}})

    async def test_rpc_autostarts_then_reuses(self):
        # First rpc auto-starts the server; it then stays live for the second.
        await mcp_host.rpc("echo2", sys.executable, [_FIXTURE], {},
                           "tools/list", {}, 10)
        self.assertTrue(mcp_host.is_running("echo2"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_tool_runner_mcp_host -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tool_runner.mcp_host'`

- [ ] **Step 3: Implement `tool_runner/mcp_host.py`**

Create `tool_runner/mcp_host.py`:
```python
"""STDIO MCP server hosting for the isolated tool-runner.

Owns the single authoritative table of live STDIO MCP subprocesses. API / Celery
workers proxy start/stop/status/rpc here over HTTP, so no worker holds subprocess
handles and the API can run multiple uvicorn workers.

Validation, env sanitisation, and spawning happen here because this is the
process that actually runs the subprocess. Callers have already decrypted any
per-server env vars (the tool-runner holds no encryption key) and pass them as
plaintext over the isolated, token-authenticated internal network.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from typing import Any, Optional

# Authoritative live subprocess table: server_name -> Process
_live_processes: dict[str, asyncio.subprocess.Process] = {}

_DANGEROUS_ENV_VARS = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG",
    "BASH_ENV", "ENV", "PROMPT_COMMAND", "PS4",
    "GIT_TRACE_PACKET", "GIT_TRACE", "GIT_TRACE_PERFORMANCE",
    "GIT_TRACE_REFS", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS",
    "SVN_SSH", "PERL5LIB", "PERL5OPT", "PERL5DB",
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
    "NODE_PATH", "NODE_OPTIONS",
    "JAVA_HOME", "CLASSPATH",
    "RUBYOPT", "RUBYLIB",
})


def _validate_command(command: str) -> str:
    if not command:
        raise ValueError("command cannot be empty")
    if not os.path.isabs(command):
        raise ValueError("command must be an absolute path")
    base, ext = os.path.splitext(command)
    if ext.lower() in {".js", ".py", ".rb", ".php", ".pl"}:
        raise ValueError(f"unsafe command extension: {ext}")
    if not os.path.isfile(command):
        raise ValueError(f"command not found: {command}")
    if not os.access(command, os.X_OK):
        raise ValueError(f"command not executable: {command}")
    return command


def _validate_args(args: Optional[list]) -> list:
    if not args:
        return []
    shell_metachar = re.compile(r'[;&|`$<>\\\'"*?#~=[\]{}()!%^|]', re.UNICODE)
    dangerous_keywords = re.compile(
        r'^\s*(curl|wget|nc|netcat|python|perl|ruby|bash|sh|zsh|'
        r'ncat|openssl|socat|chsh|systemctl|service|reboot|shutdown|'
        r'mkfs|mke2fs|dd|rm\s+-rf|mount|umount)\s*$',
        re.IGNORECASE,
    )
    validated = []
    for arg in args:
        if not isinstance(arg, str):
            raise ValueError(f"arg must be string, got {type(arg).__name__}")
        if shell_metachar.search(arg):
            raise ValueError(f"arg contains disallowed shell metachar: {arg!r}")
        if dangerous_keywords.match(arg.strip()):
            raise ValueError(f"arg contains disallowed keyword: {arg.strip()!r}")
        validated.append(arg)
    return validated


def _sanitize_env(env: dict) -> dict:
    safe = {k: v for k, v in env.items() if k not in _DANGEROUS_ENV_VARS}
    safe.pop("SHELL", None)
    safe.pop("PATHEXT", None)
    return safe


async def start_server(name: str, command: str, args: Optional[list], env: Optional[dict]) -> bool:
    """Spawn an STDIO MCP server (idempotent). Returns True if running."""
    proc = _live_processes.get(name)
    if proc is not None and proc.returncode is None:
        return True
    if not command:
        return False
    try:
        vcmd = _validate_command(command)
        vargs = _validate_args(args)
    except ValueError:
        return False
    base_env = dict(os.environ)
    base_env.update(env or {})
    base_env = _sanitize_env(base_env)
    base_env["PATH"] = "/usr/bin:/usr/local/bin:/opt/homebrew/bin"
    try:
        proc = await asyncio.create_subprocess_exec(
            vcmd, *vargs, env=base_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _live_processes[name] = proc
        return True
    except Exception:
        return False


async def stop_server(name: str) -> None:
    proc = _live_processes.pop(name, None)
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass


def is_running(name: str) -> bool:
    proc = _live_processes.get(name)
    return proc is not None and proc.returncode is None


async def rpc(
    name: str,
    command: str,
    args: Optional[list],
    env: Optional[dict],
    method: str,
    params: Optional[dict],
    timeout: Optional[int],
) -> Any:
    """Send a single JSON-RPC request to the (auto-started) STDIO server and
    return its `result`. Used for both `tools/call` and `tools/list`."""
    proc = _live_processes.get(name)
    if proc is None or proc.returncode is not None:
        if not await start_server(name, command, args, env):
            raise RuntimeError(f"MCP server {name} is not running")
        proc = _live_processes[name]
    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("MCP subprocess has no stdio streams")

    request_id = str(uuid.uuid4())
    payload = json.dumps({
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {},
    }) + "\n"
    proc.stdin.write(payload.encode("utf-8"))
    await proc.stdin.drain()

    deadline = asyncio.get_event_loop().time() + (timeout or 30)
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            await stop_server(name)
            raise RuntimeError(f"RPC {method} timed out after {timeout}s")
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
        if not line:
            raise RuntimeError("MCP server stdout closed")
        try:
            resp = json.loads(line.decode("utf-8").strip())
        except json.JSONDecodeError:
            continue
        if resp.get("id") != request_id:
            continue
        if "error" in resp:
            raise RuntimeError(resp["error"].get("message", str(resp["error"])))
        return resp.get("result", {})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_tool_runner_mcp_host -v`
Expected: PASS (4 tests). (Requires `/bin/sleep` to exist — it does on Linux and macOS.)

- [ ] **Step 5: Commit**

```bash
git add tool_runner/mcp_host.py tests/fixtures/echo_mcp_server.py tests/test_tool_runner_mcp_host.py
git commit -m "feat(tool-runner): STDIO MCP host (authoritative _live_processes + JSON-RPC)"
```
(a git hook may auto-push; expected.)

---

## Task 2: tool-runner MCP endpoints

**Files:**
- Modify: `tool_runner/main.py`
- Test: `tests/test_tool_runner_endpoints.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tool_runner_endpoints.py`:
```python
import os
import sys
import unittest

os.environ["RUNNER_TOKEN"] = "test-token"  # must be set BEFORE importing tool_runner.main
from fastapi.testclient import TestClient
from tool_runner.main import app
from tool_runner import mcp_host

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "echo_mcp_server.py")
_HDR = {"X-Runner-Token": "test-token"}


class TestToolRunnerMcpEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.post("/mcp/stop", json={"name": "ep"}, headers=_HDR)
        self.client.post("/mcp/stop", json={"name": "epc"}, headers=_HDR)

    def test_requires_token(self):
        r = self.client.post("/mcp/start", json={"name": "ep", "command": "/bin/sleep",
                                                 "args": ["30"], "env": {}})
        self.assertEqual(r.status_code, 401)

    def test_start_status_stop(self):
        r = self.client.post("/mcp/start",
                             json={"name": "ep", "command": "/bin/sleep", "args": ["30"], "env": {}},
                             headers=_HDR)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["running"])

        r = self.client.post("/mcp/status", json={"name": "ep"}, headers=_HDR)
        self.assertTrue(r.json()["running"])

        r = self.client.post("/mcp/stop", json={"name": "ep"}, headers=_HDR)
        self.assertEqual(r.status_code, 200)

        r = self.client.post("/mcp/status", json={"name": "ep"}, headers=_HDR)
        self.assertFalse(r.json()["running"])

    def test_rpc_echo(self):
        r = self.client.post("/mcp/rpc", headers=_HDR, json={
            "name": "epc", "command": sys.executable, "args": [_FIXTURE], "env": {},
            "method": "tools/call", "params": {"name": "x", "arguments": {"a": 1}},
            "timeout": 10,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"], {"echo": {"name": "x", "arguments": {"a": 1}}})

    def test_rpc_failure_returns_500(self):
        r = self.client.post("/mcp/rpc", headers=_HDR, json={
            "name": "nope", "command": "relative/bad", "args": [], "env": {},
            "method": "tools/call", "params": {}, "timeout": 5,
        })
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_tool_runner_endpoints -v`
Expected: FAIL — the `/mcp/*` routes do not exist yet (404), so the assertions fail.

- [ ] **Step 3: Add the endpoints to `tool_runner/main.py`**

In `tool_runner/main.py`, add this import near the top (after the existing imports):
```python
from tool_runner import mcp_host
```

Add a small token guard and the four endpoints at the end of the file:
```python
def _check_token(token: str) -> None:
    if token != RUNNER_TOKEN:
        raise HTTPException(status_code=401, detail="bad runner token")


@app.post("/mcp/start")
async def mcp_start(body: dict, x_runner_token: str = Header(default="")):
    _check_token(x_runner_token)
    running = await mcp_host.start_server(
        body.get("name", ""), body.get("command", ""),
        body.get("args") or [], body.get("env") or {},
    )
    return {"running": running}


@app.post("/mcp/stop")
async def mcp_stop(body: dict, x_runner_token: str = Header(default="")):
    _check_token(x_runner_token)
    await mcp_host.stop_server(body.get("name", ""))
    return {"stopped": True}


@app.post("/mcp/status")
async def mcp_status(body: dict, x_runner_token: str = Header(default="")):
    _check_token(x_runner_token)
    return {"running": mcp_host.is_running(body.get("name", ""))}


@app.post("/mcp/rpc")
async def mcp_rpc(body: dict, x_runner_token: str = Header(default="")):
    _check_token(x_runner_token)
    try:
        result = await mcp_host.rpc(
            name=body.get("name", ""),
            command=body.get("command", ""),
            args=body.get("args") or [],
            env=body.get("env") or {},
            method=body.get("method", ""),
            params=body.get("params") or {},
            timeout=body.get("timeout"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_tool_runner_endpoints -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tool_runner/main.py tests/test_tool_runner_endpoints.py
git commit -m "feat(tool-runner): token-auth MCP start/stop/status/rpc endpoints"
```

---

## Task 3: Rewrite `mcp_executor` as a thin client

**Files:**
- Rewrite: `app/services/mcp_executor.py`
- Test: `tests/test_mcp_executor_client.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_executor_client.py`:
```python
import types
import unittest
from unittest.mock import AsyncMock, patch

import app.services.mcp_executor as mx


def _stdio_server(name="s1"):
    return types.SimpleNamespace(
        name=name, transport_type="stdio", command="/usr/bin/tool",
        args=["--flag"], env_vars_encrypted=None, timeout_seconds=15,
    )


class TestMcpExecutorClient(unittest.IsolatedAsyncioTestCase):
    async def test_start_proxies_and_returns_running(self):
        with patch.object(mx, "_runner_post", AsyncMock(return_value={"running": True})) as rp:
            ok = await mx._start_stdio_server(_stdio_server())
        self.assertTrue(ok)
        path, payload = rp.await_args.args
        self.assertEqual(path, "/mcp/start")
        self.assertEqual(payload["name"], "s1")
        self.assertEqual(payload["command"], "/usr/bin/tool")
        self.assertEqual(payload["args"], ["--flag"])
        self.assertEqual(payload["env"], {})

    async def test_stdio_status_proxies(self):
        with patch.object(mx, "_runner_post", AsyncMock(return_value={"running": False})):
            self.assertFalse(await mx.stdio_status("s1"))

    async def test_execute_stdio_tool_uses_rpc_tools_call(self):
        with patch.object(mx, "_runner_post", AsyncMock(return_value={"result": {"ok": 1}})) as rp:
            out = await mx.execute_stdio_tool(_stdio_server(), "mytool", {"x": 2})
        self.assertEqual(out, {"ok": 1})
        path, payload = rp.await_args.args
        self.assertEqual(path, "/mcp/rpc")
        self.assertEqual(payload["method"], "tools/call")
        self.assertEqual(payload["params"], {"name": "mytool", "arguments": {"x": 2}})
        self.assertEqual(payload["timeout"], 15)

    async def test_discover_stdio_tools_parses_list(self):
        with patch.object(mx, "_runner_post",
                          AsyncMock(return_value={"result": {"tools": [{"name": "t"}]}})):
            tools = await mx.discover_stdio_tools(_stdio_server())
        self.assertEqual(tools, [{"name": "t"}])

    async def test_execute_mcp_tool_dispatches_stdio_to_proxy(self):
        with patch.object(mx, "execute_stdio_tool", AsyncMock(return_value="X")) as st, \
             patch.object(mx, "execute_http_tool", AsyncMock()) as ht:
            out = await mx.execute_mcp_tool(_stdio_server(), "t", {})
        self.assertEqual(out, "X")
        st.assert_awaited_once()
        ht.assert_not_awaited()

    async def test_execute_mcp_tool_dispatches_http_locally(self):
        http_server = types.SimpleNamespace(transport_type="http")
        with patch.object(mx, "execute_stdio_tool", AsyncMock()) as st, \
             patch.object(mx, "execute_http_tool", AsyncMock(return_value="H")) as ht:
            out = await mx.execute_mcp_tool(http_server, "t", {})
        self.assertEqual(out, "H")
        ht.assert_awaited_once()
        st.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_mcp_executor_client -v`
Expected: FAIL — `AttributeError: module 'app.services.mcp_executor' has no attribute '_runner_post'` (and `stdio_status` / `discover_stdio_tools` do not exist).

- [ ] **Step 3: Rewrite `app/services/mcp_executor.py`**

Replace the entire file `app/services/mcp_executor.py` with:
```python
"""MCP tool execution.

STDIO MCP servers are hosted in the isolated `tool-runner` process; this module
is a thin client that decrypts per-server env (the tool-runner has no encryption
key), then proxies STDIO start/stop/status/call/discovery over HTTP. HTTP-transport
MCP runs in-process here (already stateless and multi-worker safe).
"""
import json
import os
from typing import Any, Dict, Optional

import httpx

from app.core.security import decrypt_data
from app.models.mcp import MCPServer

TOOL_RUNNER_URL = os.environ.get("TOOL_RUNNER_URL", "http://tool-runner:9000")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")


def _decrypt_env(server: MCPServer) -> dict:
    if server.env_vars_encrypted:
        return json.loads(decrypt_data(server.env_vars_encrypted))
    return {}


def _spawn_spec(server: MCPServer) -> dict:
    return {
        "name": server.name,
        "command": server.command or "",
        "args": list(server.args or []),
        "env": _decrypt_env(server),
    }


async def _runner_post(path: str, payload: dict, *, timeout: float = 15.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{TOOL_RUNNER_URL}{path}",
            headers={"X-Runner-Token": RUNNER_TOKEN},
            json=payload,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"tool-runner {path} failed: {resp.status_code} {resp.text}")
        return resp.json()


# ---- STDIO proxies ----

async def _start_stdio_server(server: MCPServer) -> bool:
    """Start an STDIO MCP server in the tool-runner. Returns True if running."""
    if not server.command:
        return False
    try:
        data = await _runner_post("/mcp/start", _spawn_spec(server))
        return bool(data.get("running"))
    except Exception:
        return False


async def _stop_stdio_server(server_name: str) -> None:
    try:
        await _runner_post("/mcp/stop", {"name": server_name})
    except Exception:
        pass


async def stdio_status(server_name: str) -> bool:
    """Whether an STDIO server is live in the tool-runner."""
    try:
        data = await _runner_post("/mcp/status", {"name": server_name})
        return bool(data.get("running"))
    except Exception:
        return False


async def execute_stdio_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    timeout = server.timeout_seconds or 30
    payload = _spawn_spec(server)
    payload.update({
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "timeout": timeout,
    })
    data = await _runner_post("/mcp/rpc", payload, timeout=timeout + 10)
    return data.get("result", {})


async def discover_stdio_tools(server: MCPServer) -> list:
    """Discover tools via JSON-RPC tools/list (proxied to the tool-runner)."""
    timeout = server.timeout_seconds or 30
    payload = _spawn_spec(server)
    payload.update({"method": "tools/list", "params": {}, "timeout": timeout})
    data = await _runner_post("/mcp/rpc", payload, timeout=timeout + 10)
    return (data.get("result") or {}).get("tools", [])


# ---- HTTP MCP tool invocation (in-process; stateless, multi-worker safe) ----

async def execute_http_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool via HTTP POST to an MCP server endpoint."""
    from urllib.parse import urlparse
    from app.core.ssrf import validate_outbound_url, SSRFError

    if not server.url:
        raise RuntimeError("MCP server has no URL configured")
    try:
        validate_outbound_url(server.url)
    except SSRFError as e:
        raise RuntimeError(f"SSRF blocked: {e}")
    parsed = urlparse(server.url)

    headers = dict(server.headers_json or {})
    if server.auth_token_encrypted:
        token = decrypt_data(server.auth_token_encrypted)
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "jsonrpc": "2.0", "id": "1", "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    async with httpx.AsyncClient(timeout=server.timeout_seconds, verify=parsed.scheme == "https") as client:
        response = await client.post(f"{server.url}/tools/call", headers=headers, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"MCP server returned {response.status_code}: {response.text}")
        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return data.get("result", {})


async def execute_mcp_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Transport-agnostic entry point. Dispatches by `server.transport_type`."""
    if server.transport_type == "stdio":
        return await execute_stdio_tool(server, tool_name, arguments)
    return await execute_http_tool(server, tool_name, arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_mcp_executor_client -v`
Expected: PASS (6 tests)

Confirm the old subprocess machinery is gone from the client:
Run: `grep -n "_live_processes\|create_subprocess_exec\|_validate_command" app/services/mcp_executor.py`
Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add app/services/mcp_executor.py tests/test_mcp_executor_client.py
git commit -m "refactor(mcp): mcp_executor becomes thin client proxying STDIO to tool-runner"
```

---

## Task 4: Update `app/routers/mcp.py` to use the client proxies

**Files:**
- Modify: `app/routers/mcp.py`

- [ ] **Step 1: Fix the import block**

In `app/routers/mcp.py`, the import from `app.services.mcp_executor` currently includes `_live_processes`. Change the import block (around lines 19-23):
```python
from app.services.mcp_executor import (
    _live_processes,
    _start_stdio_server,
    _stop_stdio_server,
    execute_mcp_tool as _svc_execute_mcp_tool,
)
```
to:
```python
from app.services.mcp_executor import (
    _start_stdio_server,
    _stop_stdio_server,
    stdio_status,
    discover_stdio_tools,
    execute_mcp_tool as _svc_execute_mcp_tool,
)
```

- [ ] **Step 2: Replace the STDIO discovery branch in `_discover_tools_via_jsonrpc`**

In `app/routers/mcp.py`, the function `_discover_tools_via_jsonrpc` has an STDIO branch (`if server.transport_type == "stdio":`) that pokes `_live_processes` and does raw JSON-RPC (the block spanning roughly lines 211-237, ending at `return resp.get("result", {}).get("tools", [])`). Replace that entire `if server.transport_type == "stdio":` block with:
```python
    if server.transport_type == "stdio":
        return await discover_stdio_tools(server)
```
Leave the HTTP-transport portion of the function (the `# HTTP transport` part below it) unchanged.

- [ ] **Step 3: Confirm no other `_live_processes` use remains in the router**

Run: `grep -n "_live_processes" app/routers/mcp.py`
Expected: no matches.

Run: `grep -n "stdio_status\|discover_stdio_tools" app/routers/mcp.py`
Expected: shows the new usages (discovery; `stdio_status` is now available for any future status check — it is imported but its only required use was the discovery path, which is handled).

Note: if `grep` shows `stdio_status` imported-but-unused and your linter is strict, either use it where a status check is wanted or drop it from the import. It is harmless to keep.

- [ ] **Step 4: Verify the router parses and the executor still imports**

Run: `python -c "import ast; ast.parse(open('app/routers/mcp.py').read()); print('router ok')"`
Expected: `router ok`

Run: `python -c "import app.services.mcp_executor as m; print(hasattr(m, 'discover_stdio_tools'), hasattr(m, 'stdio_status'))"`
Expected: `True True`

- [ ] **Step 5: Commit**

```bash
git add app/routers/mcp.py
git commit -m "refactor(mcp-router): use tool-runner client proxies; drop _live_processes"
```

---

## Task 5 (Phase 4): Flip the API to multiple workers + validation

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Make the API CMD honour `API_WORKERS`**

Open `Dockerfile`. Find the API start command (the final `CMD ...uvicorn app.main:app...`). It must use shell form so `${API_WORKERS}` expands. Replace the existing API `CMD` line with:
```dockerfile
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-4}
```
(If the current CMD is exec-form JSON `["uvicorn", ...]`, replace the whole line with the shell-form line above. Note: `celery_worker`, `celery_beat`, and `flower` override `command:` in compose, so this CMD only affects the `api` service.)

- [ ] **Step 2: Expose `API_WORKERS` in compose**

In `docker-compose.yml`, under the `api:` service `environment:` block, add:
```yaml
      API_WORKERS: ${API_WORKERS:-4}
```
(Keeps it overridable from the host `.env`; defaults to 4.)

- [ ] **Step 3: Rebuild and bring the stack up**

Run: `docker compose build api && docker compose up -d`
Expected: containers start; `docker compose ps` shows `api` healthy.

Confirm multiple workers are actually running:
Run: `docker compose exec -T api sh -c "ps -eo pid,args | grep -c '[u]vicorn'"`
Expected: a number > 2 (one master + N workers; with `API_WORKERS=4`, expect ~5 uvicorn-related processes).

- [ ] **Step 4: Multi-worker validation checklist (manual)**

Run each and confirm the expected behavior:

1. **MCP STDIO across workers:** create/start an STDIO MCP server via the API, then call one of its tools several times. Because hosting is in tool-runner, every API worker reaches the same live process. Expected: tool calls succeed regardless of which worker handles them.
   `curl` the create + a tool-execute endpoint a few times; expect 200s, no "server not running".

2. **Config cache across workers (Phase 1):** update a security setting via the API, then immediately GET it several times. Expected: every read reflects the new value (version-gated cache; no stale worker).

3. **Group chat across workers (Phase 2):** start a group-chat `/complete`, then poll its status repeatedly and issue a second `/complete`. Expected: status polls reflect progress from Redis; the second `/complete` is a no-op (lock held); cancel stops it within a round.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat(api): run multiple uvicorn workers (API_WORKERS, default 4)"
```

---

## Final verification

- [ ] All new automated suites pass:

Run: `python -m unittest tests.test_tool_runner_mcp_host tests.test_tool_runner_endpoints tests.test_mcp_executor_client -v`
Expected: all PASS.

- [ ] No subprocess hosting remains in the API/Celery trust domain:

Run: `grep -rn "_live_processes\|create_subprocess_exec" app/services/mcp_executor.py app/routers/mcp.py`
Expected: no matches (it now lives only in `tool_runner/mcp_host.py`).

- [ ] The client still exposes the call sites `internal_agent.py` depends on:

Run: `python -c "import app.services.mcp_executor as m; print(callable(m.execute_mcp_tool))"`
Expected: `True` (the `execute_mcp_tool(server, tool, args)` signature used by `app/services/internal_agent.py` is unchanged).

## Risks / operational notes

- **STDIO MCP binaries must live in the tool-runner image.** Previously STDIO
  servers spawned in the API container; they now spawn in tool-runner. Any
  configured STDIO MCP server's `command` must exist and be executable inside the
  `tool-runner` image. Add the needed binaries to `tool-runner/Dockerfile` per the
  MCP servers your deployment uses (out of scope here — deployment-specific).
- **Plaintext per-server env over the internal network.** The client decrypts
  `env_vars_encrypted` and sends it to tool-runner over the isolated,
  token-authenticated compose network (tool-runner exposes no host port). This is
  the deliberate trade for keeping the tool-runner free of the encryption key.
- **tool-runner is a single point of failure for STDIO MCP.** It is already
  required for tool execution; it stays single-instance by design (the dedicated
  host). A tool-runner restart drops live STDIO servers; they auto-restart on the
  next call (`rpc` auto-starts).
- **Phase ordering:** do not run Task 5 (the worker flip) until Phases 1 and 2 are
  also merged — all three blockers must be gone before multi-worker is safe.
