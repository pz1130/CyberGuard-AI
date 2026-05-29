---
name: tool-pool-executable-design
description: Subproject ① of the QwenPaw pool alignment — turn the Tool pool from a doc-only table into executable, parameterised host-tool commands run in an isolated tool-runner container, wired into the internal agent.
type: design
date: 2026-05-29
status: implemented (2026-05-29, feat/internal-agents)
---

# Tool Pool → Executable (subproject ①)

## Context

The platform has three "pools": **Skill** (markdown docs injected into prompts),
**Tool**, and **MCP** (executable tools reached over the MCP protocol). Today the
`Tool` table is doc-only — it has a `md_content` field and nothing executable —
so it duplicates `Skill` and is never actually run.

The user wants the **Tool pool to be executable scripts/commands** that let an
agent use host tools and installed software (e.g. `nmap`, `nuclei`). This is the
first of three subprojects aligning the pools with QwenPaw; subprojects ② (unified
assignment + tags/version) and ③ (external agents using the pools) build on it.

This is **subproject ①** only.

## Goals

1. Turn `Tool` into an **executable** definition: a command template + parameter
   schema, run with the supplied arguments.
2. Run commands in a **dedicated, isolated `tool-runner` container** (not in the
   api container, not on the host), so the tool environment is separate and
   resource/network-limitable.
3. Make execution **injection-safe**: parameterised templates, schema validation,
   argv (no shell), per-arg quoting.
4. Enforce **security**: per-tool RBAC (`required_permission`) and approval for
   `permission_level=high`.
5. Wire executable Tools into the **internal agent** (`InternalAgentRunner`) as
   callable tools, using a temporary `metadata_json.tool_ids` association, so the
   feature is verifiable end-to-end.
6. Update the **WebUI** Tool form to author command template + schema, and add a
   standalone "execute" test path.

## Non-goals (deferred)

- **Unified assignment** (`AgentConfig.associated_tools`, a proper UI panel to
  pick skills/tools/mcp together) → subproject ②. ① uses a temporary
  `metadata_json.tool_ids` list, mirroring the existing `mcp_tool_ids`.
- **tags / version metadata** on the pools → subproject ②.
- **External agents** (OpenClaw/Custom) using the pools (payload delivery +
  gateway callbacks) → subproject ③.
- Multi-file skill artifacts / filesystem provisioning (explicitly out of scope
  for the whole alignment per the brainstorming decision).
- A large pre-installed tool catalogue in the runner image. The runner Dockerfile
  installs a minimal set; operators extend it as needed (documented).

## Architecture overview

```
            ┌── api container ───────────────────────────────┐
            │  tool_executor.py                              │
 agent /    │   1. load Tool (command_template, schema)      │
 API call ──┤   2. validate args against input_schema        │
            │   3. build argv (shlex.split template,         │
            │      placeholders → individual argv tokens)    │
            │   4. RBAC + approval gate                       │
            │   5. POST argv to tool-runner ─────────────────┼──┐
            └────────────────────────────────────────────────┘  │
                                                                  ▼
            ┌── tool-runner container (isolated) ────────────────────┐
            │  FastAPI: POST /run {argv, timeout}                     │
            │   subprocess.run(argv, shell=False, timeout) capture    │
            │   → {stdout, stderr, exit_code, duration_ms}            │
            │  image = api base + security tools (nmap, ...)          │
            └─────────────────────────────────────────────────────────┘
```

The api never runs tool commands itself; it only validates, builds a safe argv,
and forwards it. The runner never touches the DB — it just executes an argv it is
given. Injection safety lives in `tool_executor` (argv, not shell strings).

## Detailed design

### 1. Data model — `Tool` table

Add columns (Alembic migration; keep `md_content` but make it optional/“notes”):

| column | type | notes |
|---|---|---|
| `command_template` | `Text` | e.g. `nmap -sV -p {ports} {target}`; required for executable tools |
| `input_schema_json` | `Text` | JSON Schema for params (same convention as `MCPTool`) |
| `timeout_seconds` | `Integer` default 60 | per-tool execution timeout |
| `required_permission` | `String(100)` nullable, indexed | RBAC; null/empty = any `TASK_EXECUTE` user |
| `md_content` | (existing) made nullable | now optional human notes/docs |

`permission_level` already exists and is reused (`high` → approval).

Migration: add the four new columns; make `md_content` nullable. Existing rows
get `command_template=NULL` and are treated as "not executable / legacy doc"
until edited. No data loss.

### 2. `tool-runner` container

- New `docker-compose.yml` service `tool-runner`, built from a new
  `tool-runner/Dockerfile` = api base image + a minimal security-tool layer
  (start with `nmap`; documented how to add `nuclei`, etc.). Not exposed to the
  host network; reachable only on the compose network as `tool-runner:9000`.
- Runs a tiny FastAPI app (`tool_runner/main.py`) with a single endpoint:

  ```
  POST /run    {argv: [str], timeout: int}
  → 200 {stdout: str, stderr: str, exit_code: int, duration_ms: int, timed_out: bool}
  ```

  Implementation: `asyncio.create_subprocess_exec(*argv)` (shell=False), wait
  with `asyncio.wait_for(timeout)`; on timeout kill the process group and return
  `timed_out=true`. stdout/stderr captured and **truncated** at a max-bytes cap
  before returning. A shared secret header (`X-Runner-Token`, from env) guards
  the endpoint so only the api can call it.

### 3. Execution service — `app/services/tool_executor.py`

`async def execute_tool(tool, args: dict, user_id, *, approved=False) -> dict`:

1. **Validate** `args` against `tool.input_schema_json` (required keys, basic
   type checks, enum if present). Reject unknown keys.
2. **Build argv**: `shlex.split(tool.command_template)` → token list; each token
   that is exactly a `{name}` placeholder is replaced by `str(args[name])` as a
   **single argv element** (never re-split, never shell-interpreted). Unfilled
   placeholders or placeholders not in the schema → error. This makes command
   injection structurally impossible (no shell, args are separate argv items).
3. **RBAC**: if `tool.required_permission` set, caller must hold it (reuse
   `require_permission`/rbac helpers). 
4. **Approval**: if `tool.permission_level == "high"` and not `approved`, create
   an `ApprovalService` request and return `status="needs_approval"` (mirrors the
   existing agent/high pattern).
5. **Dispatch**: `POST http://tool-runner:9000/run {argv, timeout}` with the
   runner token; on connection/timeout errors return a structured error.
6. **Result**: `{status, stdout, stderr, exit_code, duration_ms, timed_out}` with
   stdout/stderr truncated (reuse the internal-agent truncation cap).

Return shape is JSON-safe so it can be fed back to an LLM tool-call loop.

### 4. Standalone execute API

`POST /api/v1/tools/{id}/execute` (perm `TASK_EXECUTE` + tool's
`required_permission`): body `{args: {...}}` → calls `execute_tool`. Used by the
WebUI test button and available for direct testing. Usage metrics
(`use_count`/`last_used_at`) are out of scope for ① (YAGNI).

### 5. Internal agent wiring (temporary association)

In `InternalAgentRunner` (mirrors the existing MCP handling):

- Read `metadata_json.tool_ids` (temporary; becomes `associated_tools` in ②).
- `_build_tools()` also loads these `Tool`s and appends OpenAI function schemas
  `{name, description, parameters: input_schema}` to the tool catalogue.
- `_resolve_*` builds a `{tool_name: Tool}` lookup.
- `_dispatch()` gains a Tool branch: when a tool_call name matches a pool Tool,
  call `tool_executor.execute_tool` and return its stdout (or an error string).
  `permission_level=high` tools return a "needs approval" tool result rather than
  executing inline (consistent with the agent's existing high-permission gate).

Naming: pool Tool function names must not collide with MCP tool names; on
collision, MCP wins and the Tool is skipped with a logged warning (documented).

### 6. WebUI

- Tool pool form: replace the markdown-only editor with fields for
  `command_template`, a parameter-schema editor (reuse the MCP input-schema UI if
  one exists, else a JSON textarea), `timeout_seconds`, `permission_level`,
  `required_permission`, and an optional notes (`md_content`) field.
- Tool list: show an "EXECUTABLE" badge and the command template preview.
- Add a "TEST" action that opens a small args form (driven by the schema) and
  calls `POST /tools/{id}/execute`, showing stdout/exit code.

## Data flow (happy path, internal agent)

1. Agent's LLM emits a tool_call for a pool Tool with args.
2. `InternalAgentRunner._dispatch` → `tool_executor.execute_tool`.
3. Validate args → build argv → RBAC/approval pass.
4. `POST tool-runner:9000/run` → subprocess → stdout.
5. Truncated stdout returned as the tool result → fed back into the loop.

## Error handling

- Invalid/missing args, unknown keys, unfilled placeholders → `status="error"`
  with a clear message (no execution).
- Missing RBAC permission → `status="error"` (forbidden).
- `permission_level=high` unapproved → `status="needs_approval"`.
- Runner unreachable / non-200 → `status="error"` with the cause.
- Timeout → `timed_out=true`, process group killed, partial output truncated.
- Non-zero exit code → returned as a normal result (`exit_code != 0`), not an
  exception — the agent/user sees stderr.

## Security considerations

- **No shell**: argv + `shell=False`; placeholders become single argv tokens.
- **Parameterised only**: only schema-defined `{name}` placeholders are fillable;
  the static part of the template is author-controlled (admin authoring the Tool).
- **Isolation**: commands run only in `tool-runner`, not api/host; the container
  can be given resource limits and a restricted network (documented; hard limits
  are an ops concern, not enforced in code here).
- **RBAC + approval**: `required_permission` and `permission_level=high` gate
  execution.
- **Runner auth**: `X-Runner-Token` shared secret so only api can drive the runner.
- Authoring a Tool (the static command + which binary) is an **admin** action;
  agents only supply parameters.

## Testing

Unit (no external deps, mock the runner HTTP call):
- argv builder: template + args → correct argv; quoting/placeholder-as-single-token;
  reject unknown keys, unfilled placeholders, missing required.
- schema validation: required/type/enum failures.
- approval gate: `high` unapproved → `needs_approval`.
- RBAC: missing permission → error.
- internal agent: a tool_call to a pool Tool dispatches to `execute_tool`
  (mocked) and feeds the result back; MCP-name-collision skip.

Integration (with the runner container, opt-in/marked):
- `POST /tools/{id}/execute` runs a benign command (e.g. `echo {msg}`) end-to-end
  and returns stdout/exit_code; timeout path kills a `sleep` command.

The DB-async test-isolation issue noted in `project_status.md` still applies to
DB-backed tests; pure-logic tests (argv builder, schema, gates) are unaffected.

## Migration / rollout

1. Alembic migration adds Tool columns (`md_content` → nullable).
2. Build/start `tool-runner`; set `RUNNER_TOKEN` in env for api + runner.
3. Author an executable Tool in the WebUI; verify via the TEST button.
4. Attach via `metadata_json.tool_ids` on an internal agent; verify end-to-end.

## Open questions

None — resolved during brainstorming (HTTP runner; ① includes temporary internal-
agent wiring; command-template + schema; isolated runner container).
