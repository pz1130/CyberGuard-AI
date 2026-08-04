# CyberGuard Desktop

macOS-first **single-operator agent app**: Electron shell + Python sidecar over **stdin/stdout JSONL** (no listen ports).

## Status

**M0a–M5 product paths + M7 delivery engineering** (development build; **not notarized, not for distribution**)

- Mock or live OpenAI-compatible LLM; Seatbelt host tools (M2); Plan Mode self-approval (M4)
- Trust Gate, evidence catalog, pause/resume (M5); local episodic + session encryption (M3)
- Built-in SOP skills (progressive disclosure); MCP stdio + Keychain secret slots
- M7: encrypted export / uninstall / update verify / EDR·notarization docs
- UI: Context → **Data · Export / Uninstall**; tray menu entries
- Packaging skeleton: `npm run pack:check` (no certs); `dist:mac` needs Developer ID

## Layout

```
apps/desktop/
  electron/          Main process + preload (contextIsolation)
  renderer/          React + Vite UI
    App.tsx          Shell (chrome / banner / status / view switch)
    hooks/           useTheme, useDesktopRuntime
    components/      EventCard, PlanPanel, SessionList, StatusBar, …
    views/           WorkbenchView · EvidenceView · SettingsView
    styles/          tokens (dark default) + base + motion + views
  sidecar/           Python JSONL RPC host
  package.json
  README.md
```

**Theme:** default `dark`; chrome toggle / Settings cycle dark → light → system (`localStorage` + `ui.prefs`).  
**Font:** Settings → Appearance (`small` / `medium` / `large` → `html[data-font]`).  
**UI waves:** P0 shell · P1 Settings (LLM/MCP GUI) · P2 Evidence catalog · P3 shortcuts/polish.  
**Shortcuts:** `⌘1` Workbench · `⌘2` Evidence · `⌘,` Settings · `⌘N` New investigation · `⌘Enter` Run.

### Settings (no JSON required)

1. **LLM** — mode / base URL / model / API key (Keychain; never re-shown) · Save · Test  
2. **MCP** — list/upsert/delete · secret slots · Discover tools · Browse command  
3. **Evidence** — Register file (picker) · list with sha256 · Verify integrity  
4. **Data** — encrypted export / uninstall inventory

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
| `sessions.create` / `list` / `events` | … | encrypted JSONL + SQLite index (M3) |
| `sessions.delete` | `session_id`, `crypto_shred?` | default crypto-shred (drop key) |
| `sessions.purge_expired` | `retention_days?` | default 90d body retention |
| `data_protection.status` | `reapply_exclusions?` | crypto + backup + FileVault |
| `episodic.recall` / `record` / `stats` | `task`, … | M3 local experience (offline embed; no upload) |
| `skills.list` / `skills.load` | `name?` | builtin SOP catalog + progressive body load |
| `plan.approve` / `reject` / `list` / `get` | `plan_id`, `revised_plan?` | M4 Plan Mode + privilege (timeout=reject; self-approval) |
| `policy_events.tail` | `n?` | sandbox deny / privilege retry trail |
| `trust.set` / `evaluate` / `status` | `path`, `level?` | M5 Trust Gate (default deny project-local) |
| `evidence.register` / `list` / `verify` | `path` / `evidence_id` | read-only catalog + sha256 |
| `runs.paused` / `agent.resume` | `run_id` | provider disconnect pause/resume |
| `export.encrypted` | `dest_path`, `passphrase` | M7 encrypted backup export |
| `uninstall.inventory` / `execute` | `confirm`, `dry_run` | M7 cleanup (crypto-shred keys) |
| `update.verify` | `manifest`, `current_version` | INV-42 anti-tamper / anti-downgrade |
| `mcp.spawn_mock` / `stop` / `list` | … | lifecycle drill (orphan governance) |

## Local data (managed root)

Default: `~/Library/Application Support/CyberGuard` (macOS) or `~/.cyberguard`.

Override: `CYBERGUARD_DATA_DIR=/path`.

```
sessions/*.jsonl   # Fernet-encrypted append-only event log (M3)
sessions/index.sqlite3  # titles encrypted with index key
episodic/index.sqlite3  # local experience store (no auto-upload)
tmp/ workspace/ audit/  # backup-excluded (.cg-nobackup + xattr on macOS)
logs/
```

Session body keys live in the secrets store (`cyberguard.data.session` /
`<session_id>`). **Deleting a session drops its key (crypto-shred)** — residual
ciphertext without the key is unreadable. Does not replace FileVault (INV-38).

## Orphan governance (MCP)

1. Sidecar `setsid` + process-group `killpg` on exit  
2. PPID watchdog (if reparented to 1 → kill children + exit)  
3. Electron `before-quit` SIGTERM with timeout → SIGKILL  

`mcp.spawn_mock` starts a long-lived mock child for drills; never use real MCP creds in M1.

## Real MCP (stdio, M1.5)

Config file: `{data_root}/mcp_servers.json`

```json
{
  "servers": [
    {
      "id": "alerts",
      "command": "python3",
      "args": ["/absolute/path/to/your_mcp_server.py"],
      "readonly": true,
      "enabled": true,
      "timeout_seconds": 30,
      "description": "Read-only alert source"
    }
  ]
}
```

Or env (single server):

```bash
export CYBERGUARD_MCP_ID=echo
export CYBERGUARD_MCP_COMMAND="$(pwd)/.venv/bin/python"
export CYBERGUARD_MCP_ARGS="$(pwd)/tests/fixtures/echo_mcp_server.py"
```

Optional per-server secret (M3 Keychain slot → child env only for that server):

```json
{
  "id": "siem",
  "command": "...",
  "args": [],
  "secret_env": "SIEM_API_TOKEN"
}
```

```bash
# store secret for server id "siem" only
printf '%s\n' '{"id":"1","method":"secrets.set_mcp","params":{"server_id":"siem","secret":"..."}}' \
  | PYTHONPATH="packages:$(pwd)" .venv/bin/python -m apps.desktop.sidecar
```

On spawn, sidecar injects the slot into `secret_env` (default `CYBERGUARD_MCP_SECRET`).  
Other servers cannot read this slot. Never put live secrets in `mcp_servers.json` `env`.

Tools appear as `mcp__{server_id}__{tool_name}` in the agent loop.  
`readonly: true` servers are available on **readonly** and **full** tiers; non-readonly only on **full**.

RPC helpers: `mcp.list`, `mcp.discover`, `mcp.call`.

Demo with fixture server:

```bash
export CYBERGUARD_DATA_DIR=/tmp/cg-mcp-demo
mkdir -p "$CYBERGUARD_DATA_DIR"
cat > "$CYBERGUARD_DATA_DIR/mcp_servers.json" <<EOF
{
  "servers": [{
    "id": "echo",
    "command": "$(pwd)/.venv/bin/python",
    "args": ["$(pwd)/tests/fixtures/echo_mcp_server.py"],
    "readonly": true
  }]
}
EOF
export PYTHONPATH="packages:$(pwd)"
printf '%s\n' \
  '{"id":"1","method":"mcp.discover","params":{"tier":"readonly"}}' \
  '{"id":"2","method":"agent.run","params":{"task":"list sample alerts with MCP","tier":"readonly"}}' \
  | .venv/bin/python -m apps.desktop.sidecar
```

## Secrets & audit (M3 start)

Provider API keys should live in the secrets store (macOS Keychain by default), not plaintext `provider.json`:

```bash
# migrate existing provider.json api_key → Keychain/file store and clear the file field
printf '%s\n' '{"id":"1","method":"secrets.migrate_provider_json","params":{}}' \
  | PYTHONPATH="packages:$(pwd)" .venv/bin/python -m apps.desktop.sidecar

# or set directly
printf '%s\n' '{"id":"1","method":"secrets.set_provider_key","params":{"api_key":"sk-..."}}' \
  | PYTHONPATH="packages:$(pwd)" .venv/bin/python -m apps.desktop.sidecar
```

Local audit hash chain (tamper-evident, **not** WORM):

```bash
printf '%s\n' \
  '{"id":"1","method":"audit.verify","params":{}}' \
  '{"id":"2","method":"audit.tail","params":{"n":10}}' \
  | PYTHONPATH="packages:$(pwd)" .venv/bin/python -m apps.desktop.sidecar
```

Override secrets backend for tests: `CYBERGUARD_SECRETS_BACKEND=file`.

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

## Packaging (M7 skeleton)

```bash
cd apps/desktop
npm run pack:check    # no Apple certs required — must PASS
# Optional full build (installs electron-builder via package.json):
# npm run dist:dir    # unsigned directory
# npm run dist:mac    # needs CSC_NAME + APPLE_* for real notarization
```

See `docs/desktop/15-NOTARIZATION-AND-UNINSTALL.md`.

## Security notes

- No listening sockets
- Dev build is **not notarized** — do not distribute (INV-38)
- Local audit hash chain is tamper-evident, **not** WORM
- FileVault-off is warned explicitly (app crypto does not replace it)
- Export does not include raw Keychain secrets; uninstall crypto-shreds session keys
