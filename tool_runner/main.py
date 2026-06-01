"""Isolated tool-runner: executes a given argv with no shell. Driven only by api."""
import asyncio
import os
import signal
import time

from fastapi import FastAPI, Header, HTTPException

from tool_runner import mcp_host

app = FastAPI(title="tool-runner")

RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
if not RUNNER_TOKEN:
    raise RuntimeError("RUNNER_TOKEN must be set for the tool-runner")
OUTPUT_MAX_BYTES = 64_000


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/run")
async def run(body: dict, x_runner_token: str = Header(default="")):
    if x_runner_token != RUNNER_TOKEN:
        raise HTTPException(status_code=401, detail="bad runner token")
    argv = body.get("argv") or []
    timeout = int(body.get("timeout") or 60)
    if not argv or not isinstance(argv, list):
        raise HTTPException(status_code=400, detail="argv must be a non-empty list")

    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True)
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"command not found: {argv[0]}",
                "exit_code": 127, "duration_ms": 0, "timed_out": False}

    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            proc.kill()
        out, err = await proc.communicate()
        timed_out = True
    return {
        "stdout": (out or b"").decode("utf-8", "replace")[:OUTPUT_MAX_BYTES],
        "stderr": (err or b"").decode("utf-8", "replace")[:OUTPUT_MAX_BYTES],
        "exit_code": proc.returncode,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "timed_out": timed_out,
    }


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
