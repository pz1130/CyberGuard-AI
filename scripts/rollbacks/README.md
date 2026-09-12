# Rollback Procedures (NDB Std §Safety Envelope)

Rollbacks are **declarative**: each envelope tool (`contain_soft`/`contain_hard`/
`remediate`) declares a `rollback_command_template` (and optional
`validation_`/`verification_command_template`). On a successful action,
`execute_tool()` registers the computed rollback argv in `rollback_registrations`
with a TTL (default 3600s).

- Trigger a revert: `POST /api/v1/governance/rollback/{action_id}` (admin).
- List active registrations: `GET /api/v1/governance/rollback`.
- On rollback failure the event is written to the application log and audit trail;
  operators should route those logs through their normal alerting platform.

Add per-tool rollback scripts here when a single inverse command is insufficient,
and reference them from the tool's `rollback_command_template`.
