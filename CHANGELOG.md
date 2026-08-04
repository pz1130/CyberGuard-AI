# Changelog

All notable changes to CyberGuard are documented here.

## [Unreleased] — `feature/desktop-app-frontend` (+ prior `security-enhance`)

### Desktop UI (P0–P3)

- **P0 shell**: design tokens, dual theme (dark default), chrome nav, Workbench three-column split (`App` shell + `useDesktopRuntime` + components/views).
- **P1 Settings GUI**: LLM provider get/set/test (API keys → secrets store, never re-shown); MCP config list/upsert/delete; `ui.prefs` theme; EmptyState deep-links.
- **P2 Evidence page**: list / register (file picker) / verify integrity with sha256 expand.
- **P3 polish**: ⌘1/2/N/, hotkeys, font-size prefs, documentation status.
- **Demo MCP one-click**: Settings → Install demo alerts MCP (`echo` + `list_alerts`) for M1.5 golden path without hand-editing JSON.

### Desktop (macOS standalone)

- **M0a–M5 product paths**: Seatbelt host tools, Plan Mode self-approval, Trust Gate, evidence catalog, pause/resume, local episodic memory, session encryption / crypto-shred, progressive SOP skills, MCP stdio + Keychain slots.
- **M7 delivery engineering**: encrypted export, uninstall inventory/execute, Ed25519 update verify, EDR/notarization docs, `electron-builder` skeleton, in-app Export/Uninstall UI, `npm run pack:check` (unsigned dry-run).
- **M2 deepen**: `always_readonly_paths` includes `evidence` / `secrets` / `config`; Seatbelt network-deny probe (`python` socket / `curl`); evidence write refused even if data_root is mis-listed as writable.

### Server security & invariants

| ID | Change |
|----|--------|
| **INV-13** | No keyword-driven control flow; group chat / HITL use structured fields only. |
| **INV-21** | Cross-agent privilege inheritance on master dispatch (LLM cap medium/L2). |
| **INV-23** | Fan-out gates: plan size, per-agent cap, depth, concurrency semaphore. |
| **INV-25** | Audit flush awaited; kill switch fail-closed; credential decrypt failures visible; MCP env decrypt fails closed. |
| **Sessions** | `messages_json` append under `SELECT FOR UPDATE` (multi-worker safe). |
| **Episodes** | Record failures (`success=false`); prune to 200/agent. |
| **Skills** | Progressive disclosure: catalog in prompt, body via `load_skill`. Local executor catalog-only. |
| **Truncate** | Directional tool output (tool-runner keeps tail by default). |

### WebUI

- Skills tab: progressive disclosure banner; description vs body labels; card badge `CATALOG → LOAD_SKILL`.
- Agents (internal): note under Skills assignment explaining catalog + `load_skill`.

### Tests

- Desktop M3–M7 suites; `test_privilege_inherit`, `test_fanout_gate`, `test_inv13_control_flow`, `test_conversation_messages`, `test_episodic_memory`, `test_skill_progressive`, `test_local_executor_skills`, kill-switch fail-closed, MCP/agent decrypt logging, tool truncate direction.

### Still external / deferred

- Apple Developer ID **real** notarization and Gatekeeper double-click install.
- EDR allowlist validation on customer environments.
- M6 connected mode (on demand).
- M0b `ui-shared` extraction (not scheduled).
