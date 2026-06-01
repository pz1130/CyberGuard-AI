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
