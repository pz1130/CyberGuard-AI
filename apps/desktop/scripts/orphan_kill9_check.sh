#!/usr/bin/env bash
# Orphan-governance lab script (M1).
#
# Unit coverage (preferred in CI):
#   pytest tests/test_desktop_m15_provider.py::test_watchdog_kills_children_when_ppid_one
#   pytest tests/test_desktop_m1_persistence.py::test_registry_kill_all_clears_children
#
# This script does an end-to-end spawn + cleanup drill:
#   1) start sidecar, spawn mock MCP child
#   2) SIGTERM sidecar (graceful path: signal handler + kill_all)
#   3) assert child is gone
#
# From cyberguard repo root:
#   ./apps/desktop/scripts/orphan_kill9_check.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/packages:${ROOT}:${PYTHONPATH:-}"
export CYBERGUARD_DATA_DIR="${CYBERGUARD_DATA_DIR:-$(mktemp -d /tmp/cg-orphan-XXXXXX)}"
export CYBERGUARD_WATCHDOG_INTERVAL=0.3
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"

exec "$PY" - <<'PY'
import json, os, signal, subprocess, sys, time
from pathlib import Path

workdir = Path(os.environ["CYBERGUARD_DATA_DIR"]) / "lab"
workdir.mkdir(parents=True, exist_ok=True)
fifo = workdir / "cmd.fifo"
out = workdir / "out.jsonl"
err = workdir / "err.log"
if fifo.exists():
    fifo.unlink()
os.mkfifo(fifo)

env = {**os.environ, "PYTHONUNBUFFERED": "1"}
# Open RDWR so open() does not block
fd = os.open(fifo, os.O_RDWR)
sidecar = subprocess.Popen(
    [sys.executable, "-m", "apps.desktop.sidecar"],
    stdin=fd,
    stdout=open(out, "w"),
    stderr=open(err, "w"),
    env=env,
)
os.close(fd)
time.sleep(0.4)

with open(fifo, "w") as w:
    for msg in (
        {"id": "1", "method": "ping", "params": {}},
        {
            "id": "2",
            "method": "mcp.spawn_mock",
            "params": {"server_id": "orphan-test", "hold_seconds": 600},
        },
    ):
        w.write(json.dumps(msg) + "\n")
    w.flush()
    time.sleep(0.8)

child = None
for line in out.read_text().splitlines() if out.exists() else []:
    try:
        m = json.loads(line)
    except Exception:
        continue
    r = m.get("result") or {}
    if isinstance(r, dict) and r.get("server_id") == "orphan-test":
        child = r.get("pid")

if not child:
    print("FAIL: no child", file=sys.stderr)
    print(err.read_text() if err.exists() else "", file=sys.stderr)
    print(out.read_text() if out.exists() else "", file=sys.stderr)
    sidecar.kill()
    sys.exit(1)

print(f"child={child} sidecar={sidecar.pid}")
os.kill(child, 0)  # must be alive

# Graceful stop — signal handler runs MCP.stop_all + REGISTRY.kill_all
sidecar.send_signal(signal.SIGTERM)
try:
    sidecar.wait(timeout=5)
except subprocess.TimeoutExpired:
    sidecar.kill()

time.sleep(0.3)
try:
    os.kill(child, 0)
    print(f"FAIL: child {child} still alive after sidecar SIGTERM", file=sys.stderr)
    os.kill(child, signal.SIGKILL)
    sys.exit(1)
except OSError:
    print(f"PASS: child {child} gone after sidecar SIGTERM (orphan cleanup path)")
    sys.exit(0)
PY
