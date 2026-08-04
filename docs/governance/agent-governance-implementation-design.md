# Agent Governance — Implementation Design (P0 controls)

Design proposal for closing the three highest-priority gaps against the NDB
Standard *AI Agent Governance for Security Automation v1.0*:

- **B3 Kill Switch**
- **B2 Action Gatekeeper** (+ taxonomies A1–A4)
- **B4 Audit hardening**

> Status: **design only — no code written yet.** This documents *where* each
> control slots into the existing architecture so we can agree the approach
> before implementing. Companion deliverable: the formal gap report at
> `docs/governance/CyberGuard_AI_Agent_Governance_Gap_Assessment_v1.0.docx`.

## Architectural facts this design relies on

- **The tool-execution chokepoint is `app/services/tool_executor.py::execute_tool()`.**
  It already does RBAC + a binary high-permission approval gate and returns a
  JSON-safe `{"status": ...}`. This is where the Gatekeeper belongs.
- **Two agent execution paths exist** and both must be covered:
  1. `app/services/internal_agent.py` `_run_loop` → calls `execute_tool()` (covered for free).
  2. `app/agents/master.py` → calls `self.executor.execute()` / `local_exec.execute()`
     (sub-agent / local-exec path — needs the same gate applied at its dispatch points).
- **Multi-worker runtime** (`API_WORKERS=4`): any halt/state signal must be in
  Redis/DB, never an in-process flag or a single-host file. `app/core/redis_client.py`
  already exposes `RedisCache.get/set/delete/publish/subscribe`.
- **Existing approval** (`app/services/approval_service.py`) already implements
  pause → notify → `wait_for_decision(timeout)` → `decide(approver_id, comment)`.
  The Gatekeeper should *route into* it, not replace it.
- **Existing audit** (`app/core/audit.py` + `app/models/audit.py`) hashes
  input/output but writes to a mutable, buffered Postgres table that drops most
  fields. Hardening extends this, keeping the `log_audit()` call sites.
- **Timestamp convention**: all DateTime columns are naive UTC (project rule).
  New columns must follow this (strip tzinfo before write) — see the prior
  approval-service tz bug.

---

## B3 — Kill Switch

**Requirement:** remotely stoppable < 5s via file / API / UI; ~1s poll; on
trigger stop new actions, finish/abort current safely, write `EMERGENCY_HALT`
to audit, notify on-call.

### Design

A **platform-level halt flag**, authoritative in Redis with a DB fallback.

- **Signal store:** `RedisCache.set("governance:halt", <json>)` where the value
  records `{by, reason, ts, scope}`. `scope` ∈ `{global, agent:<id>}`. DB table
  `kill_switch_state` mirrors it so the flag survives a Redis flush and is
  auditable; Redis is the fast path, DB is the source of truth on cold start.
- **Enforcement (the important part):** check the flag **inside
  `execute_tool()` before any state-changing action**, not only in a poller.
  This guarantees < 1 action latency regardless of poll interval. Add at the top
  of `execute_tool()`:
  - if halted (global, or matches this agent) → return
    `{"status": "halted", "error": "kill switch engaged"}` and emit an
    `EMERGENCY_HALT` audit record. Never run the tool-runner call.
- **Poller:** a background task (FastAPI lifespan or the existing Celery/worker
  layer) refreshes the in-process cached copy every 1s so non-`execute_tool`
  loops (e.g. `master.py` sub-agent dispatch) can short-circuit cheaply between
  steps. The poller is an optimisation; `execute_tool` is the hard gate.
- **Triggers:**
  - **API:** `POST /agents/halt` and `POST /agents/{id}/halt` (+ `DELETE` to
    clear), admin-only, in a new `app/routers/kill_switch.py`. Returns the
    halt record.
  - **UI:** a persistent red “EMERGENCY STOP” control in the WebUI header/agent
    dashboard calling the API.
  - **File trigger (Standard-mandated):** poller also treats presence of a
    configured path as a halt. Use a **configurable, persistent, permissioned**
    path (e.g. `settings.KILL_SWITCH_FILE`), **not** `/tmp/soc_kill_switch`
    (world-writable, lost on reboot, multi-instance collision). Document the
    deviation-with-rationale in the governance config.
- **“Finish current action safely”:** in-flight tool calls already run with a
  timeout in the tool-runner; on halt we let a read-only/soft action complete
  and abort before issuing any *new* state-changing call. No mid-call kill of a
  destructive op (matches the Standard’s “or abort if destructive”).
- **Notify on-call:** reuse `email_service` / approval’s admin-notify path.

### Touch points
`app/services/tool_executor.py` (gate), new `app/routers/kill_switch.py`, new
`app/services/kill_switch.py` (state read/write), `app/core/audit.py`
(`EMERGENCY_HALT` action), a lifespan/worker poller, WebUI button, one Alembic
migration (`kill_switch_state`), `app/config.py` (`KILL_SWITCH_FILE`).

### Tests
halt blocks a state-changing tool; clear re-enables; agent-scoped halt only
affects that agent; `EMERGENCY_HALT` is audited; flag survives simulated Redis
loss via DB fallback.

---

## B2 — Action Gatekeeper (+ taxonomies A1–A4)

**Requirement:** every action passes a single gatekeeper checking allow-list,
confidence, approval, rate limits → `ALLOW | DENY | NEEDS_APPROVAL`, called
before any state-changing action.

### Design

**1. Taxonomy as data, on the tool registry.** Add to the `Tool` (and `MCPTool`)
model / config:
- `action_category` ∈ `observe | annotate | notify | contain_soft |
  contain_hard | remediate | mutate` (A2).
- `risk_tier` ∈ `critical | high | medium | low` (A3).

Per-agent governance carries `autonomy_tier` (A1) and confidence thresholds
(A4) — see B1 in the roadmap. Backfill existing tools with a sensible default
(`observe`/`low` for read-only; `contain_hard`/`high` for the offensive/
exploitation tools).

**2. One `gatekeeper_check()` inside `execute_tool()`**, replacing the current
ad-hoc binary approval branch. Ordered evaluation (first decisive rule wins):

1. **Kill switch** engaged → `DENY` (halted). *(B3)*
2. **Category allow-list:** category ∉ agent’s `allowed_actions` → `DENY`.
   `mutate` is `DENY` in POC; `contain_hard` / `remediate` default
   `NEEDS_APPROVAL` (Standard’s default governance column).
3. **Autonomy ceiling:** action exceeds the agent’s `autonomy_tier` → `DENY`
   (e.g. an L2 agent cannot run a `mutate`).
4. **Risk routing:** map `risk_tier` → required approver role; if approval not
   yet granted → `NEEDS_APPROVAL` via the existing `ApprovalService`
   (`risk_level` already a field there).
5. **Rate limit:** `notify` category is rate-limited via existing
   `app/core/ratelimit.py` (`check_rate_limit`); over limit → `DENY`/defer.
6. **Confidence (advisory, A4):** below `escalate_to_human_below` →
   `NEEDS_APPROVAL`. **Recommendation:** treat confidence as a *secondary*
   signal, not the primary gate (see the report’s critique — LLM self-confidence
   is poorly calibrated). Thresholds come from per-agent config, defaults
   `0.85 / 0.60`.
7. Otherwise → `ALLOW`.

`gatekeeper_check()` returns a small result object
(`decision`, `reason`, `category`, `risk_tier`) that is **always written to the
audit trail** (B4), satisfying the Standard’s “every decision logged”.

**3. Cover the second path.** Apply the same gate at the `master.py`
sub-agent / `local_exec.execute()` dispatch points (call `gatekeeper_check`
before dispatch, or route those executions through `execute_tool`). This is the
main extra wiring beyond the internal-agent path.

### Touch points
`app/services/tool_executor.py` (gate + decision object), new
`app/services/gatekeeper.py` (pure decision logic, unit-testable), `Tool` /
`MCPTool` models + Alembic migration (`action_category`, `risk_tier`),
`app/agents/master.py` (apply at dispatch), config plumbing for per-agent
thresholds, WebUI tool editor (category/risk fields), audit fields (B4).

### Tests
table-driven over the 7 categories × tiers: read-only `observe` → ALLOW;
`mutate` in POC → DENY; `contain_hard` → NEEDS_APPROVAL then ALLOW after
`decide(approved)`; low confidence → NEEDS_APPROVAL; over rate-limit `notify` →
deferred; every path emits exactly one audit decision record.

---

## B4 — Audit hardening

**Requirement:** immutable JSON-lines audit; WORM or cryptographically signed;
required field set incl. input/output hashes; deletion forbidden.

### Design

Keep the `log_audit()` API and call sites; change *what* is stored and *how*.

**1. Full field set.** Extend the persisted record (currently drops most
fields) to the Standard’s schema: `timestamp` (naive UTC), `agent_name`,
`action`, `action_category`, `confidence`, `human_reviewer`,
`rollback_possible`, `input_hash`, `output_hash`, `risk_tier`, plus the existing
`request_id` / `user_id`. Most arrive from the Gatekeeper decision (B2).

**2. Hash chain (tamper-evidence without external WORM).** Add `prev_hash` and
`entry_hash` to `AuditLog`. `entry_hash = sha256(canonical(record) || prev_hash)`,
chained per stream. Any deletion or edit breaks the chain and is detectable by a
verifier (`GET /audit/verify`). This is the pragmatic “cryptographically signed
logs” option; an HMAC/private-key signature can be layered on if NDB requires
non-repudiation beyond tamper-evidence.

**3. Durability for action events.** The current 10-item in-memory buffer can
lose entries on crash. For **action/decision events specifically**, write
**synchronously** (buffering is acceptable only for chatty HTTP-middleware
request logs). The hash chain also requires ordered, serialised appends — take a
per-stream lock or a single-writer pattern.

**4. Deletion forbidden / WORM.** Revoke `DELETE` at the DB-grant level for the
app role; expose no delete endpoint. For true WORM, mirror the chain to an
object store with object-lock (S3/MinIO) — optional phase 2, recommended for
production per the bank context.

### Touch points
`app/core/audit.py` (field set, sync path for actions, chain compute),
`app/models/audit.py` + Alembic migration (`prev_hash`, `entry_hash`, new
columns), new `GET /audit/verify`, DB grant change (deploy note).

### Tests
record carries full field set; `entry_hash` chains correctly; tampering with a
row fails verification; concurrent appends keep a single valid chain; no delete
endpoint exists.

---

## Suggested sequencing

1. **B4 field set + chain** first — it is the substrate the Gatekeeper and Kill
   Switch both write into.
2. **B2 Gatekeeper + taxonomy** — the core control; emits audit decisions.
3. **B3 Kill Switch** — reuses the Gatekeeper chokepoint and audit `EMERGENCY_HALT`.

Each is independently shippable behind the existing test suite. Recommend TDD per
the project convention (write the gate/chain tests first).

## Open decisions (need your call before coding)

1. **Per-agent governance config (B1):** store as a DB record surfaced in the
   WebUI, and *export* to the Standard’s `agent_governance.yaml` shape for
   auditor delivery — agreed? (Recommended over a literal repo-root YAML.)
2. **Confidence gate:** keep advisory/secondary as recommended, or enforce the
   literal `0.85 / 0.60` hard gate the Standard prescribes?
3. **WORM phase 2:** is hash-chain tamper-evidence sufficient for the POC, with
   object-lock WORM deferred to production?
4. **Kill-switch file path:** confirm a configurable persistent path instead of
   `/tmp/soc_kill_switch` (logged as a deviation-with-rationale).
