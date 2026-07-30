# CyberGuard Desktop (M1 skeleton)

macOS-first **single-operator agent app**: Electron shell + Python sidecar over **stdin/stdout JSONL** (no listen ports).

## Status

**M1 · 壳 + Sidecar + 单工作台骨架** (in progress)

- Mock LLM + fake Operations only — **no real host tools, no real Provider**
- Capability tier: `readonly` has no `ExecOperations` / `EditOperations`
- Headless sidecar for CI / sandbox tests later
- Dev build only — not for distribution (INV-38)

## Layout

```
apps/desktop/
  electron/          Main process + preload (contextIsolation)
  renderer/          React + Vite single workbench
  sidecar/           Python JSONL RPC host
  package.json
  README.md
```

## Prerequisites

- Node ≥ 20, npm
- Project venv with `packages/agent_core` installed (`uv pip install -e .` from repo root)

## Headless sidecar (no Electron)

```bash
# from cyberguard repo root
export PYTHONPATH="packages:${PYTHONPATH}"
.venv/bin/python -m apps.desktop.sidecar <<'EOF'
{"id":"1","method":"ping","params":{}}
{"id":"2","method":"agent.run","params":{"task":"summarize these alerts","tier":"readonly"}}
EOF
```

Or use the helper script:

```bash
./apps/desktop/scripts/headless_demo.sh
```

## Electron (dev)

```bash
cd apps/desktop
npm install
npm run dev
```

This starts Vite (renderer) + Electron main, which spawns the sidecar from the project `.venv`.

## JSONL RPC (v1)

Request:

```json
{"id":"<string>","method":"<name>","params":{}}
```

Response (result):

```json
{"id":"<string>","result":{...}}
```

Streaming events (same id):

```json
{"id":"<string>","event":{"type":"start|tool_call_start|tool_call_end|answer_ready|error|steer|token",...}}
```

Error:

```json
{"id":"<string>","error":{"code":"...","message":"..."}}
```

### Methods

| method | params | notes |
|--------|--------|--------|
| `ping` | `{}` | liveness |
| `agent.run` | `task`, `tier`=`readonly`\|`full`, `system_prompt?` | mock loop |
| `agent.abort` | `run_id` | sets abort flag |
| `agent.steer` | `run_id`, `message` | inject user text mid-run |
| `session.capabilities` | `tier` | inspect Operations ports (exec is null in readonly) |

## Security notes (M1)

- No listening sockets
- Sidecar is a child process; MCP children must be in the same process group (orphan governance hooks stubbed for M1 mock)
- Real tool execution blocked until M2 sandbox exit criteria
