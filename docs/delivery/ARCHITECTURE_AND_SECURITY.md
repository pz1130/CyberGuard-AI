# Architecture and Security

## Trust boundaries

The browser is untrusted input. FastAPI authenticates users and applies RBAC.
PostgreSQL stores configuration, conversations, and audit data. Redis provides
coordination and rate-limit state. Celery runs
background agent work. The tool-runner is isolated on the Compose network and
accepts only authenticated, structured execution requests.

External LLM and MCP endpoints are separate trust domains. Their use must be
covered by deployment-specific allowlists and data-handling decisions.

## Principal controls

- Password hashing and optional Entra ID SSO
- AES-256-GCM authenticated encryption for stored credentials
- Prompt-injection detection and input sanitisation
- PII redaction/blocking and secrets detection
- Structured risk categories, confidence gates, and human approval
- Cross-agent privilege inheritance and fan-out limits
- Kill switch and safety-envelope/rollback registration
- SSRF checks and optional egress allowlist
- HTTP, action, and run-event audit records with chain verification
- Encrypted backup and controlled restore

## Important boundaries

An application-level audit chain is tamper-evident, not external WORM storage.
Encrypted credentials do not protect a running process that is already
compromised. Approval reduces agent error but is only separation of duties when
the approver is organisationally independent. A deployment must supply TLS,
host hardening, monitoring, backup custody, and provider governance.

## Container runtime hardening

Release images do not run as root. API, Celery, migrate, and tool-runner use
uid/gid `10001`; WebUI nginx uses uid/gid `101` and binds 8080. Compose drops
all capabilities, sets `no-new-privileges:true`, and mounts a read-only root
filesystem for those services. PostgreSQL and Redis still start as root only
long enough for their official entrypoints to gosu, with `cap_drop: ALL` plus
the gosu capabilities. This is process containment, not a substitute for host
TLS, network policy, or secret custody.

## Executable skill scripts

A script inside a skill bundle is inert on import. An admin holding
`skill:script_approve` reviews it and promotes it into a `Tool`, supplying the
risk metadata; from then on it is gated by the same chain as every other tool,
because it is the same object. That permission is deliberately separate from
`skill:write`, so uploading a script and granting it the right to run stay
independently revocable.

The `Tool` pins the sha256 of the bundle it was approved against. Re-importing
the skill with different contents deactivates the tool until it is reviewed
again, so an approval cannot be reused for code nobody read.

Scripts execute in a runner on an `internal: true` network: `python3`/`sh` and
the standard library only, and a subprocess environment carrying no token or
secret. The bundle is written to tmpfs per execution and deleted afterwards; the
bundle tree is read-only and a separate scratch directory is the only writable
place, so a script cannot rewrite the code its approval covered.

A script approved with no network runs in `skill-runner`, which has no route off
its segment at all. A script approved with an egress allowlist runs in
`skill-runner-net`, whose only reachable endpoint is `egress-proxy` — the sole
service bridging that segment to the internet. Before each such run the API
registers a one-execution nonce with the proxy carrying that tool's allowlist,
and the nonce travels to the script as proxy credentials; the proxy authorizes
every request by nonce, port, hostname and **resolved IP**, then connects to the
address it just validated. `HTTP_PROXY` is a convenience for well-behaved
clients, never the control: a script that ignores it finds no route.

`api:8000` remains reachable from the sandbox segments — compose network
membership is bidirectional and plain compose cannot express a one-way rule —
but a script holds no credential for it, so its reach there is the
unauthenticated surface. This is a known limit, recorded rather than left to be
discovered.

See `docs/superpowers/specs/2026-09-15-skill-script-execution-design.md` and
`docs/superpowers/specs/2026-09-15-skill-script-egress-allowlist-design.md`.

### Model-authored code in chat

An agent can also write a Python program during a conversation and run it, via
the `run_python` built-in. This is a different trust object from a promoted
skill script: nobody reviewed it in advance, so it carries none of the
promotion machinery and none of the egress.

Each agent has a `code_execution_mode`: `off`, `approval` (the default) or
`auto`. In `approval` mode the first call opens an approval carrying the full
program and its sha256, and the graph suspends at its existing approval node —
the only node with no side effects, which is why suspension is safe there. The
program runs only when an approved record matches both the run and the exact
digest, so an approval cannot be reused for code the model rewrote on resume.

`auto` skips the human and nothing else: the kill switch, the gatekeeper, the
audit chain, the sandbox and the network isolation all still apply. Changing the
mode needs `AGENT_WRITE` and is audited before it takes effect. `AUTO_APPROVE`
remains a development-only convenience; `code_execution_mode` is the production
control.

Model-authored code always runs in the no-network sandbox (INV-42). Because the
default mode offers the tool, every agent now has at least one tool; an agent
that should never run code is set to `off`.

INV-43: the assistant's words are evidence. Every message persisted to a
conversation enters a per-conversation hash chain before it is readable
(`app/services/conversation_chain.py`), no API accepts a message-content write
outside that path, and each conversation's chain head is periodically anchored
into the global audit chain (`app/services/conversation_anchor.py`). The chain
is per conversation rather than global so chat writes never queue on the audit
advisory lock that `audit_logs` uses; the anchor is what makes a deleted
conversation detectable, since a chain cannot prove its own existence. Deleting
a conversation tombstones it (`conversations.deleted_at`) and leaves the
messages in place.
See `docs/superpowers/specs/2026-09-16-chat-message-storage-design.md`.

`code_execution_mode` is not the only gate. `run_python` is classified
`action_category = "mutate"`, which a default deployment denies three ways over:
forbidden in a POC, below the `L3` autonomy floor, and absent from
`DEFAULT_ALLOWED`. So on a stock install the tool is offered and the gatekeeper
refuses it with a reason the model can report. Enabling it is three deliberate
settings on the agent — `is_poc: false`, `autonomy_tier: "L3"`, and `mutate` in
`allowed_categories` — which is the intended friction for letting a model run
code. Classifying it as `observe` to avoid that would be mislabelling: running a
program a model wrote seconds ago is a mutating capability whatever the program
turns out to do.

Where the gatekeeper *would* escalate `run_python` on its confidence heuristic,
it defers instead, because that escalation opens a record with no code in it.
The tool's own gate then opens one carrying the program and its digest, so the
reviewer sees what they are approving. A denial still short-circuits.

See `docs/superpowers/specs/2026-09-15-chat-code-execution-design.md`.

## Data flow review

Before deployment, document for each provider or MCP connection: data classes,
purpose, legal basis, destination, subprocessors, retention, deletion, logging,
and incident contact. Configure egress to match the approved inventory.
