# CyberGuard Desktop (M1 skeleton)

macOS-first **single-operator agent app**: Electron shell + Python sidecar over **stdin/stdout JSONL** (no listen ports).

## Status

**M1 skeleton + M1.5 live LLM path** (self-use; not for distribution)

- Default: mock LLM + mock tools (safe)
- Optional: **live OpenAI-compatible LLM** via env / `provider.json` (tools still mock until M2)
- Built-in SOP: `sidecar/skills/alert_triage.md`
- Capability tier: `readonly` has no `ExecOperations` / `EditOperations`
- FileVault status surfaced on `ping` + UI banner
- Orphan cleanup: process group + PPID watchdog + Electron SIGTERM

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
| `ping` | `{}` | liveness + `data_root` |
| `agent.run` | `task`, `tier`, `session_id?`, `system_prompt?` | mock loop; auto-creates session JSONL |
| `agent.abort` | `run_id` | sets abort flag |
| `agent.steer` | `run_id`, `message` | inject user text mid-run |
| `session.capabilities` | `tier` | inspect Operations ports (exec is null in readonly) |
| `sessions.create` / `list` / `events` | … | local JSONL + SQLite index |
| `mcp.spawn_mock` / `stop` / `list` | … | lifecycle drill (orphan governance) |

## Local data (managed root)

Default: `~/Library/Application Support/CyberGuard` (macOS) or `~/.cyberguard`.

Override: `CYBERGUARD_DATA_DIR=/path`.

```
sessions/*.jsonl   # append-only event log per investigation
sessions/index.sqlite3
tmp/               # managed temp — not system /tmp
logs/ audit/
```

## Orphan governance (MCP)

1. Sidecar `setsid` + process-group `killpg` on exit  
2. PPID watchdog (if reparented to 1 → kill children + exit)  
3. Electron `before-quit` SIGTERM with timeout → SIGKILL  

`mcp.spawn_mock` starts a long-lived mock child for drills; never use real MCP creds in M1.

## Live LLM (M1.5 self-use)

```bash
# env (highest priority)
export CYBERGUARD_LLM_MODE=live
export CYBERGUARD_LLM_BASE_URL=https://api.openai.com/v1
export CYBERGUARD_LLM_API_KEY=sk-...
export CYBERGUARD_LLM_MODEL=gpt-4o-mini

./apps/desktop/scripts/headless_demo.sh
```

Or write `{data_root}/provider.json` (keep file permissions tight):

```json
{
  "mode": "live",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "model": "gpt-4o-mini"
}
```

Default without config remains **mock**.

## Orphan check

```bash
./apps/desktop/scripts/orphan_kill9_check.sh
# unit: pytest tests/test_desktop_m15_provider.py -k watchdog
```

## Security notes (M1/M1.5)

- No listening sockets
- Real host tool execution blocked until M2 sandbox exit criteria
- Dev build banner: no sandbox / no at-rest encryption
- FileVault-off is warned explicitly (does not pretend app crypto replaces it)
- Do not distribute this build; do not process real production secrets without M2+
