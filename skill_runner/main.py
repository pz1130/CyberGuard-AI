"""Sandbox runner for promoted skill scripts.

Separate from tool-runner on purpose. Its token unlocks only "run a script in an
empty, network-isolated sandbox" — which is what the caller is already doing — so
stealing it buys nothing. The tool-runner token, by contrast, buys arbitrary argv
on a container that can reach the database.
"""
import asyncio
import os
import shutil
import signal
import tempfile
import time

from fastapi import FastAPI, Header, HTTPException

from skill_runner.materialize import (
    MaterializeError,
    materialize,
    safe_relative_path,
    unlock_for_removal,
)

app = FastAPI(title="skill-runner")

SKILL_RUNNER_TOKEN = os.environ.get("SKILL_RUNNER_TOKEN", "")
if not SKILL_RUNNER_TOKEN:
    raise RuntimeError("SKILL_RUNNER_TOKEN must be set for the skill-runner")

OUTPUT_MAX_BYTES = 64_000
ALLOWED_INTERPRETERS = frozenset({"python3", "sh"})

# Pinned rather than left to tempfile's TMPDIR lookup: the container rootfs is
# read-only and /tmp is the one tmpfs mount, so a stray TMPDIR would send bundles
# somewhere unwritable. Overridable for test runs on hosts without a usable /tmp.
SANDBOX_TMP_DIR = os.environ.get("SKILL_RUNNER_TMP_DIR", "/tmp")

# No token, no secret. An inherited environment is how a sandboxed process
# trades up into broader authority — see the design's section 1.1.
MINIMAL_ENV_BASE = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "LANG": os.environ.get("LANG", "C.UTF-8"),
    "PYTHONDONTWRITEBYTECODE": "1",
}


@app.get("/health")
async def health():
    return {"status": "ok"}


def _validate_argv(argv, files) -> str:
    """Enforce [interpreter, script_path, *args] and return the script path."""
    if not argv or not isinstance(argv, list):
        raise HTTPException(status_code=400, detail="argv must be a non-empty list")
    if argv[0] not in ALLOWED_INTERPRETERS:
        raise HTTPException(
            status_code=400,
            detail=f"interpreter must be one of {sorted(ALLOWED_INTERPRETERS)}",
        )
    if len(argv) < 2:
        raise HTTPException(status_code=400, detail="argv must name a script to run")

    script = argv[1]
    if script.startswith("-"):
        # `python3 -c ...` would let the caller carry its own inline program,
        # which is exactly what promotion review is supposed to have seen.
        raise HTTPException(status_code=400, detail="interpreter flags are not permitted")

    try:
        script = safe_relative_path(script)
        known = {safe_relative_path(f.get("path", "")) for f in (files or [])}
    except MaterializeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if script not in known:
        raise HTTPException(status_code=400, detail=f"script not in bundle: {script}")
    return script


@app.post("/run")
async def run(body: dict, x_skill_runner_token: str = Header(default="")):
    if x_skill_runner_token != SKILL_RUNNER_TOKEN:
        raise HTTPException(status_code=401, detail="bad skill runner token")

    argv = body.get("argv") or []
    files = body.get("files") or []
    timeout = int(body.get("timeout") or 60)

    _validate_argv(argv, files)

    root = tempfile.mkdtemp(prefix="skill-", dir=SANDBOX_TMP_DIR)
    try:
        try:
            bundle, scratch = materialize(files, root)
        except MaterializeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"cannot write bundle: {e}") from e

        env = dict(MINIMAL_ENV_BASE, HOME=scratch, TMPDIR=scratch)
        # Phase 2: per-execution egress. The URL carries the nonce as proxy
        # credentials, so an ordinary urllib call is scoped without the script
        # author doing anything. It is a convenience, not the boundary — the
        # boundary is that this container has no other route out.
        proxy_url = body.get("proxy_url")
        if proxy_url:
            env.update({
                "HTTP_PROXY": proxy_url, "HTTPS_PROXY": proxy_url,
                "http_proxy": proxy_url, "https_proxy": proxy_url,
            })
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=bundle, env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True)
        except FileNotFoundError:
            return {"stdout": "", "stderr": f"interpreter not found: {argv[0]}",
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
    finally:
        # The bundle tree is read-only, and unlinking needs write permission on
        # the containing directory — so restore that before removing anything.
        unlock_for_removal(root)
        shutil.rmtree(root, ignore_errors=True)
