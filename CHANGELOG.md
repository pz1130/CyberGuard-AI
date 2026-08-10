# Changelog

All notable changes to CyberGuard are documented here.

## [Unreleased] — `feature/desktop-app-frontend` (+ prior `security-enhance`)

### Desktop UI (P0–P3)

- **P0 shell**: design tokens, dual theme (dark default), chrome nav, Workbench three-column split (`App` shell + `useDesktopRuntime` + components/views).
- **P1 Settings GUI**: LLM provider get/set/test (API keys → secrets store, never re-shown); MCP config list/upsert/delete; `ui.prefs` theme; EmptyState deep-links.
- **P2 Evidence page**: list / register (file picker) / verify integrity with sha256 expand.
- **P3 polish**: ⌘1/2/N/, hotkeys, font-size prefs, documentation status.
- **Demo MCP one-click**: Settings → Install demo alerts MCP (`echo` + `list_alerts`) for M1.5 golden path without hand-editing JSON.
- **File-backed alerts MCP**: Settings → Install file alerts MCP (sample JSON or pick CSV/JSON export); tools `list_alerts` / `get_alert` / `search_alerts`.
- **Session titles**: dual-backend secret get + recover title from first `user_task` when index decrypt fails.
- **Streaming UI**: live token deltas + Evidence timeline links.

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
| **Auth** | Group chat's five session endpoints required no authentication at all — read a full transcript, inject a message, drive rounds, cancel. Now ADMIN + owner-scoped (404, not 403, so a session id is not confirmed). Unauthenticated routes: 22 → 17. |
| **P1 / INV-05** | `AUTO_APPROVE` defaulted to **True** — the master switch for the whole HITL boundary, with only a `warnings.warn` outside development. Now defaults False and is a hard config error outside dev. |
| **INV-35** | `find -exec` / `-execdir` / `-ok` reached any binary from inside the `host_run` allowlist (Seatbelt permits process-exec). Per-binary argument policy added; `find -name` / `grep -r` unaffected. |
| **INV-01** | Sandboxed children inherited the sidecar's environment incl. `CYBERGUARD_LLM_API_KEY` on the read/list/write/delete paths. `run_sandboxed` now falls back to a scrubbed env, so a missing `env=` fails safe. |
| **INV-29** | HTTP audit was `create_task` fire-and-forget, logged **before** the request, with `user_id=None` on every row. Now awaited, logged after (in `finally`), and names the actor. `AuditLog.ip_address` / `user_agent` / `request_path` / `metadata_json` existed and were never written — now they are. |
| **Audit bus** | The lifespan subscribed a DB-writing sink to the process-global bus and never detached; every app instance in a process left a live sink behind. `AuditBus.unsubscribe()` added. |
| **Passwords** | Two implementations: `app/core/auth.py` used passlib (whose bcrypt backend raises against bcrypt ≥ 5), the routers each had their own. Consolidated; > 72-byte passphrases now 400 instead of 500. `passlib` dropped. Existing hashes still verify. |

### Delivery & deployment

- **The image never contained `packages/`.** `Dockerfile` copied only `app/` + `alembic/`, and `pip install -e .` ran with neither tree present, so `packages.find` resolved to nothing — the container died on `ModuleNotFoundError: agent_core` at boot (`app` imports it at module scope). compose bind-mounted `./app` but not `./packages`. Both fixed; verified by building the image and importing inside it.
- **compose exposure**: Postgres (postgres/postgres), Redis and Flower were published on `0.0.0.0`; all three now bind `127.0.0.1` (local dev unchanged). Flower — the Celery admin UI, which lists task arguments and can revoke tasks, with no auth of its own — additionally moves behind an opt-in `monitoring` profile and refuses to start without `FLOWER_BASIC_AUTH`.
- `.dockerignore` excluded `.env.local` / `.env.example` but not `.env`.

### Engineering

- **`make check` is the verification gate** — there is no CI. INV-07/08/09/17 (all of which name "CI 阻断" as their check, two of them M0a-1 exit criteria) are enforced as **pytest cases**, not pipeline steps, so a bare `pytest` runs them too. Mutation-tested against injected violations.
- `scripts/eslint_ratchet.py`: webui carries 211 pre-existing eslint errors; the gate fails only when the count **rises**, and reports when it falls.

### WebUI

- Skills tab: progressive disclosure banner; description vs body labels; card badge `CATALOG → LOAD_SKILL`.
- Agents (internal): note under Skills assignment explaining catalog + `load_skill`.

### Tests

- Desktop M3–M7 suites; `test_privilege_inherit`, `test_fanout_gate`, `test_inv13_control_flow`, `test_conversation_messages`, `test_episodic_memory`, `test_skill_progressive`, `test_local_executor_skills`, kill-switch fail-closed, MCP/agent decrypt logging, tool truncate direction.
- `test_invariants_static` (INV-07/08/09/17), `test_groupchat_authz`, `test_auto_approve_default`, `test_password_hashing`, `test_http_audit_actor`; INV-35 argument-policy and INV-01 environment cases in `test_desktop_m2_escape`. Suite 641 → 706.

### Still external / deferred

- Apple Developer ID **real** notarization and Gatekeeper double-click install.
- EDR allowlist validation on customer environments.
- M6 connected mode (on demand).
- M0b `ui-shared` extraction (not scheduled).
- The approval loop still has no end-to-end run across a real LLM, a Celery worker and `AsyncPostgresSaver` — see `docs/superpowers/plans/2026-08-08-approval-loop-verification-debt.md`.
- **Running `scripts/reencrypt_credentials.py` is an operator action.** Until it is run, existing credentials stay in the old format — readable, but alterable by a database write. The startup scan and `GET /api/v1/security/encryption-status` report how many remain.
- Key rotation is unimplemented; the ciphertext format reserves a `key_id` so it needs no second migration.

### Credential encryption (AEAD)

Server credentials moved from unauthenticated AES-CBC to **AES-256-GCM**. Design and decisions: `docs/superpowers/specs/2026-08-10-server-credential-aead-design.md`.

- **What was wrong**: CBC computes `plaintext[0] = D(ct[0]) XOR IV` and the IV sat in the clear at the head of the blob, while PKCS7 padding lives in the *last* block. Anyone with database write access could rewrite the first 16 bytes of any credential to a value of their choosing, and decryption **raised nothing** — `sk-live-PRODUCTION-key` → `sk-live-ATTACKERON-key`, silently. That exact case is now a regression test.
- **Format** `CG2.<key_id>.<b64url(nonce‖ct‖tag)>`; base64 has no `.`, so old and new are distinguishable without trial decryption.
- **AAD binds each ciphertext to its field** (`providers.api_key_encrypted`, …) via `CredentialField`, so a value moved between columns no longer decrypts. Movement between *rows* of one column is deliberately not prevented — see the design's §5 for why, and do not claim otherwise.
- **The legacy read path is permanent, not a deprecation window.** Backup dumps are encrypted with the old scheme into files outside the database, and a backup's whole purpose is restoring years later.
- **Migration is lazy**: new writes use AEAD immediately; `scripts/reencrypt_credentials.py` (idempotent, `--dry-run`, aborts without committing if any row fails) rewrites the rest. No alembic revision — no schema change, and a migration would need `ENCRYPTION_KEY` in the deploy context.
- Startup scans for residual legacy ciphertext and warns; exposed at `GET /api/v1/security/encryption-status`.
- Decryption failures now raise a single `DecryptionError` with an identical message for every cause — the old code distinguished padding failure from other failures, which is how a padding oracle starts. Tag mismatches log loudly as a tampering signal (INV-25).
