#!/usr/bin/env bash
# Headless sidecar demo — no Electron, no listen ports.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/packages:${ROOT}:${PYTHONPATH:-}"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

"$PY" -m apps.desktop.sidecar <<'EOF'
{"id":"1","method":"ping","params":{}}
{"id":"2","method":"session.capabilities","params":{"tier":"readonly"}}
{"id":"3","method":"session.capabilities","params":{"tier":"full"}}
{"id":"4","method":"agent.run","params":{"task":"triage these sample alerts","tier":"readonly"}}
{"id":"5","method":"agent.run","params":{"task":"run a mock scan","tier":"full"}}
EOF
