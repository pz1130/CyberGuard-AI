#!/usr/bin/env bash
# M2 acceptance suite — sandbox escape + desktop host tools + TCC.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/packages:${ROOT}:${PYTHONPATH:-}"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

echo "== M2 suite (root=$ROOT) =="
"$PY" -m pytest -q \
  tests/test_desktop_m2_escape.py \
  tests/test_desktop_m2_sandbox.py \
  tests/test_desktop_tcc.py \
  tests/test_desktop_sidecar.py \
  tests/test_desktop_m15_provider.py \
  tests/test_desktop_mcp_stdio.py \
  tests/test_desktop_m1_persistence.py \
  "$@"

echo "== M2 suite PASS =="
