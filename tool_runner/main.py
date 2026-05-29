"""Isolated tool-runner: executes a given argv with no shell. Driven only by api."""
import asyncio
import os
import time

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="tool-runner")

RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
OUTPUT_MAX_BYTES = 64_000


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/run")
async def run(body: dict, x_runner_token: str = Header(default="")):
    if RUNNER_TOKEN and x_runner_token != RUNNER_TOKEN:
        raise HTTPException(status_code=401, detail="bad runner token")
    argv = body.get("argv") or []
    timeout = int(body.get("timeout") or 60)
    if not argv or not isinstance(argv, list):
        raise HTTPException(status_code=400, detail="argv must be a non-empty list")

    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"command not found: {argv[0]}",
                "exit_code": 127, "duration_ms": 0, "timed_out": False}

    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
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
