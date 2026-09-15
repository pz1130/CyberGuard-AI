# Executable Skill Scripts — Approved-Tool Promotion + Dedicated Sandbox

**Date:** 2026-09-15
**Scope:** Phase 1 — no-network script execution. Per-script egress allowlist is specified but deferred to Phase 2 (§8).
**Goal:** Let the `scripts/` inside an imported skill bundle actually run, without opening a path around the existing kill-switch / RBAC / gatekeeper / approval / audit chain.

**Depends on:** commit `beb8344` (`feat: import skills from zip bundles and real JSON`), which added the `skill_files` table and zip bundle import.

---

## 1. Problem

Skill bundles can now carry `scripts/`, but those files are inert — stored and downloadable, never executed. Making them executable is not a matter of "add a runner"; the project already has a hardened runner. It is a matter of **authorization**.

Today there are two kinds of object in the system:

| | `Skill` | `Tool` |
|---|---|---|
| What it is | Markdown procedure text | Executable `command_template` |
| Who creates it | anyone with `SKILL_WRITE` | anyone with `SKILL_WRITE` |
| Gates on use | none — it is text | kill switch → RBAC → gatekeeper → approval → safety envelope |
| Carries risk metadata | no | `action_category`, `risk_tier`, `required_permission` |

If a skill's scripts were simply executable on import, `SKILL_WRITE` would silently become "arbitrary code execution" and the entire gate chain in `app/services/tool_executor.py` would have a bypass around it.

### 1.1 A present-day defect this design must not inherit

`tool_runner/main.py:36` calls:

```python
proc = await asyncio.create_subprocess_exec(
    *argv, stdout=..., stderr=..., start_new_session=True)
```

There is no `env=`, so **every tool subprocess inherits the runner's full environment, including `RUNNER_TOKEN`** (verified empirically, not inferred).

Today this is latent: `nmap` does not read environment variables and phone home. The moment arbitrary scripts run in that container it stops being latent — an approved script could do:

```python
import os, json, urllib.request
urllib.request.urlopen(urllib.request.Request(
    "http://tool-runner:9000/run",
    data=json.dumps({"argv": ["<anything>"]}).encode(),
    headers={"X-Runner-Token": os.environ["RUNNER_TOKEN"]}))
```

and execute any argv with no kill switch, no RBAC, no gatekeeper, no approval, and no audit record. Approval would gate only the first execution.

**This is the constraint that shapes the whole design.** A script must never sit in a process tree whose environment or namespace can be traded up into broader authority.

---

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | A script becomes a **`Tool` row only after explicit human approval**, with risk metadata assigned by the approver. | Self-declared metadata in SKILL.md frontmatter — the uploader would be grading their own risk, so `SKILL_WRITE` still equals arbitrary execution. |
| D2 | The bundle is **materialized per execution into the runner's tmpfs** and deleted afterwards. | A shared writable volume (introduces persistent cross-execution state and requires relaxing `read_only: true`); per-skill container images (needs a Docker socket or build orchestration in the API — a large new privilege surface). |
| D3 | Scripts run in a **dedicated `skill-runner` container** on an `internal: true` network segment: no route to postgres, redis, or the internet (§5.3.1 on what remains reachable). | Reusing `tool-runner` (§1.1: the token there buys arbitrary argv); same container with a second uid (dropping privileges needs `CAP_SETUID` or a setuid helper, both of which weaken the current `cap_drop: ALL` hardening). |
| D4 | Runtime is **`python3` + POSIX `sh`, standard library only**. No third-party packages. | Pre-installing common libs (grows the supply-chain surface and the SBOM); per-skill `pip install` at approval time (pulls PyPI into the build path and needs network during approval, contradicting D3). |
| D5 | Executable entrypoints are limited to **`.py` and `.sh`**. | — |
| D6 | Re-importing a skill whose bundle changed **deactivates** the dependent Tools and requires re-approval. | Refusing the import outright — an import should not be blocked by a downstream object. |

---

## 3. Data model

No new table. Five columns on `tools` (migration `038_skill_script_tools`):

| Column | Type | Meaning |
|---|---|---|
| `source_skill_id` | `INTEGER NULL` FK `skills.id` `ON DELETE SET NULL`, indexed | Non-NULL marks this as a skill-script tool. **This is the routing discriminator.** |
| `source_script_path` | `VARCHAR(500) NULL` | Entrypoint inside the bundle, e.g. `scripts/triage.py` |
| `source_bundle_digest` | `VARCHAR(64) NULL` | sha256 of the bundle as approved (§3.1) |
| `script_network` | `VARCHAR(20) NULL` | `none` \| `allowlist` (Phase 1 accepts only `none`; see §8) |
| `script_network_allowlist` | `JSON NULL` | Hostnames, used in Phase 2 |

A `CHECK` constraint enforces the shape: `source_skill_id IS NULL` **or** (`source_script_path IS NOT NULL AND source_bundle_digest IS NOT NULL AND script_network IS NOT NULL`). Application code enforces the same, so the intent is visible in both places.

Pending (not-yet-approved) scripts need no representation: they are `skill_files` rows that no `Tool` points at.

### 3.1 Bundle digest — what makes approval mean something

```
digest = sha256( for each (path, bytes) in sorted(bundle_files_of_skill, key=path):
                     len(path) ‖ path ‖ len(bytes) ‖ bytes )
```

Length-prefixing each field prevents two different bundles from hashing identically by shifting a boundary between path and content.

The digest covers the **whole bundle**, not just the entrypoint, because a Python entrypoint can `import` a sibling module and a shell entrypoint can `.` a sibling file. Hashing only the entrypoint would leave the real payload unprotected.

Without this column, approval is a one-time event: an admin reviews `scripts/triage.py`, and afterwards anyone with `SKILL_WRITE` re-imports the same skill name with different script contents, and the already-approved Tool starts executing the new code. Call this **approval laundering**; §3.1 plus §4.5 and §5.2 are what close it.

---

## 4. Approval flow

### 4.1 New permission

`Permission.SKILL_SCRIPT_APPROVE = "skill:script_approve"`, granted to `Role.ADMIN` only.

Deliberately **not** `SKILL_WRITE`. Today only ADMIN holds `SKILL_WRITE`, so this is not a live escalation — but that is a coincidence of the current role table, not a property of the design. Uploading a script and granting it the right to execute must be two separately revocable capabilities, so that adding a future role cannot silently merge them.

### 4.2 Steps

1. Import a zip (existing flow). Scripts land in `skill_files`. **Inert.**
2. Skills UI lists bundle files; `.py` / `.sh` entries show a "promote to tool" action, visible only with `SKILL_SCRIPT_APPROVE`.
3. The promotion form shows **the full script source, read-only**, for review, and requires the approver to supply: tool name, description, `input_schema_json`, `command_template`, `required_permission`, `action_category`, `risk_tier`, `permission_level`, `timeout_seconds`, `script_network`.
4. On submit: recompute the digest, create the `Tool` row, write an audit record naming the approver, the skill, the script path and the digest.

### 4.3 The command template keeps the existing injection guarantee

`command_template` takes the form `python3 scripts/triage.py {target}` and is built by the **existing, unmodified** `build_argv()` (`app/services/tool_executor.py:30`): each `{name}` must be a standalone token declared in the schema, and becomes exactly one argv element. Nothing is shell-parsed. Command injection through arguments stays structurally impossible, and it stays impossible for the same reason it already is — not a second mechanism that has to be kept in sync.

Interpreter flags are **not** permitted, so the built argv is exactly
`[interpreter, source_script_path, *arguments]`: `argv[0]` must be `python3` or `sh`, and
`argv[1]` must equal `source_script_path` and exist in the bundle. Forbidding flags keeps this
a two-token check rather than a parser for each interpreter's option grammar — `python3 -c`
would otherwise let an approved template carry its own inline program.
Checked at approval time and re-checked at execution.

### 4.4 Endpoints

- `POST /skills/{id}/promote?script_path=<path>` → creates the Tool. Requires
  `SKILL_SCRIPT_APPROVE`. The path is a query parameter rather than a route segment
  because a greedy `{path:path}` converter would swallow a trailing `/promote`.
- `DELETE /tools/{id}` already exists and revokes.

### 4.5 Re-import invalidation

`_upsert_skill()` (`app/routers/skills.py`) already replaces a skill's file set wholesale. After it does, it recomputes the digest and sets `is_active = False` on every `Tool` with that `source_skill_id` and a mismatched `source_bundle_digest`, writing one audit record per deactivation.

Fails closed and fails **visibly at import time**, rather than silently at some later execution.

---

## 5. Execution path

### 5.1 API side — one branch, nothing else changes

In `_pool_execute()`:

```
tool.source_skill_id is None  → unchanged: POST TOOL_RUNNER_URL/run
otherwise                     → load bundle → verify digest → build_argv (unchanged)
                                → POST SKILL_RUNNER_URL/run  {argv, timeout, files}
```

Everything upstream — `run_tool_call` (INV-28), kill switch, RBAC, gatekeeper, approval, safety envelope, audit — is reached by the identical code path and is not modified. Skill scripts are gated by the same chain as every other tool because they *are* the same object.

### 5.2 Digest re-verification

Execution recomputes the digest from the current `skill_files` rows and compares against `tool.source_bundle_digest`. Mismatch → refuse, deactivate the tool, audit. This is redundant with §4.5 by design: §4.5 catches the normal path, §5.2 catches a bundle changed by any route that did not go through `_upsert_skill` (direct DB access, restore from backup, a future code path).

### 5.3 `skill-runner` container

Same shape as `tool-runner` (`POST /run`, token header), with:

- its **own** `SKILL_RUNNER_TOKEN`, distinct from `RUNNER_TOKEN`
- its **own `internal: true` network segment**: no route to postgres, redis, or the internet (§5.3.1)
- the existing hardening: `cap_drop: ALL`, `no-new-privileges: true`, `read_only: true`, non-root uid, no host port
- added: `pids_limit`, memory limit, CPU limit
- `/tmp` tmpfs sized for the 10 MB bundle cap with headroom

Why a separate token matters: stealing `SKILL_RUNNER_TOKEN` buys the ability to run a script in an empty, network-less sandbox — which is what the thief is already doing. Stealing `RUNNER_TOKEN` buys arbitrary argv on a container that can reach the database. The blast radius collapses to zero, and that is a property of the topology rather than of a mitigation that must be re-argued every time a binary is added to the tool image.

### 5.3.1 What a script can still reach, stated honestly

Compose network membership is bidirectional: `api` must reach `skill-runner:9000`, so both sit
on the `sandbox` network, and therefore **`api:8000` is reachable from a script**. There is no
way to make that one-directional with plain compose networks; claiming otherwise would be
designing against a control that does not exist.

What this does and does not buy:

- **Removed:** postgres (encrypted provider keys, the audit chain), redis, and all internet
  egress. `internal: true` gives no NAT to the outside.
- **Remains:** `api:8000`. A script holds no credential for it — `MINIMAL_ENV` (§5.4) carries no
  token and no secret — so its reach is the API's *unauthenticated* surface: health endpoints and
  the login endpoint, the latter already rate-limited.

Narrowing this further needs per-container network policy, which compose does not express. It is
recorded here as a known limit rather than left for a reader to discover.

### 5.4 `/run` handling

```
root = mkdtemp(dir="/tmp")
root/bundle/   ← bundle files, then chmod read+execute only
root/scratch/  ← writable, the only place the script may write
create_subprocess_exec(*argv, cwd=root/bundle, env=MINIMAL_ENV, start_new_session=True)
timeout → SIGKILL the process group   (existing logic)
finally: rmtree(root)
```

Bundle files are written under the same path-safety rules the importer already applies:
no absolute paths, no `..` components, no symlink entries.

The split matters: a script must not be able to rewrite its own approved contents mid-run,
which would put the executing code out of step with the digest that authorized it. It still
needs somewhere to write, so it gets `scratch/`, handed to it as `HOME` and `TMPDIR`. Both
directories die with the execution.

`MINIMAL_ENV` contains `PATH`, `LANG`, `PYTHONDONTWRITEBYTECODE`, and `HOME` = `TMPDIR` = the
scratch directory — **and no token or secret of any kind**. This is the line that closes §1.1 on the new path.

### 5.5 Independent fix to the existing runner

`tool_runner/main.py` gets the same explicit minimal `env=`. This is correct today regardless of this feature and should land as its own commit **before** the rest of the work, so it is reviewable on its own terms.

---

## 6. Failure modes

| Condition | Behavior |
|---|---|
| Digest mismatch | Refuse, deactivate the tool, audit |
| Entrypoint missing from bundle | Structured error naming the path |
| `argv[0]` not `python3`/`sh`, or `argv[1]` ≠ `source_script_path` | Refuse at approval and at execution |
| Timeout | Existing SIGKILL of the process group |
| tmpfs exhausted | Explicit error; bundle total already capped at 10 MB by the importer, re-checked here |
| Output over cap | Existing 64 KB cap + directional truncation (tail kept) |
| `skill-runner` unreachable | Same error shape as `tool-runner` unreachable today |

Promotion, deactivation, and every execution go through the existing `record_action` hash chain.

---

## 7. Testing

- Digest: computation, length-prefix boundary cases, mismatch detection
- Re-import deactivates dependent tools; audit record written
- Promotion endpoint refuses without `SKILL_SCRIPT_APPROVE`
- `argv[0]` / entrypoint restrictions refused at both approval and execution
- `skill-runner`: files materialized, `cwd` correct, the bundle tree is not writable by the script, `scratch/` is, the whole temp root is removed after both success and timeout, traversal and symlink entries rejected, timeout kills the process group
- **Regression test for §1.1: a child process's environment contains no token.** Asserted for both runners.
- Static invariant test: any `Tool` with `source_skill_id IS NOT NULL` routes to `SKILL_RUNNER_URL` and never to `TOOL_RUNNER_URL`
- Compose assertion: `skill-runner` is attached only to the `internal: true` network, and is not attached to the network carrying postgres or redis
- End to end: import → promote → execute → result; then re-import → execution refused

---

## 8. Phase 2 — per-script egress allowlist (specified, not built)

`script_network = 'allowlist'` cannot be enforced inside a single container: processes there share one network namespace, so two scripts cannot be given different allowlists.

The Phase 2 shape is a second container, `skill-runner-net`:

- no default route of its own
- outbound only through a forward proxy holding the domain allowlist, injected as `HTTP_PROXY` / `HTTPS_PROXY`
- `tool.script_network` selects which runner URL the API posts to

Phase 1 ships `none` only and **rejects** `allowlist` at the promotion endpoint. The schema already carries both columns, so Phase 2 adds a container and a branch — no migration, no rework of anything in §3–§7.

---

## 9. Out of scope

- Third-party Python packages for scripts (D4)
- Interpreters beyond `python3` and `sh` (D4, D5)
- Scripts reading or writing the database directly — they receive arguments and their own bundle, nothing else (D3)
- Executing scripts from a skill installed via URL rather than a zip bundle: the URL installer fetches a single Markdown file and produces no bundle, so there is nothing to execute
