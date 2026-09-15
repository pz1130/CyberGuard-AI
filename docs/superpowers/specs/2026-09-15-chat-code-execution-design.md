# Model-Authored Code Execution in Chat — Phase 3

**Date:** 2026-09-15
**Scope:** A `run_python` built-in tool that lets an agent write a script mid-conversation and run it in the existing sandbox, under a per-agent execution mode.
**Goal:** Make "the model decides this needs a script" a real capability without giving `SKILL_WRITE`-free arbitrary code execution, and without breaking the property that makes the current approval machinery correct.

**Builds on:** Phase 1 (`docs/superpowers/specs/2026-09-15-skill-script-execution-design.md`) and Phase 2 (`…-egress-allowlist-design.md`). The sandbox, its hardening and its network isolation are reused unchanged.

---

## 1. What exists, and what does not

Investigated before designing, because the answers decide the shape:

| Question | Answer |
|---|---|
| Is there any code-execution path today? | **No.** An agent's tools are MCP tools, pool `Tool` rows, `kb_search`, `web_search`, `vuln_search` and `load_skill` (`internal_agent._build_tools`). Nothing turns model-generated text into execution. |
| Do tool-level approvals resume? | **No.** `internal_agent._request_approval` writes records with `action_type="tool.execute"` and no `thread_id`; `graph_resume_target` returns `None` for them, so approving one re-executes nothing. |
| Do graph-level approvals resume? | **Yes.** `MasterAgent._approval_node` suspends on LangGraph `interrupt()` with a checkpointer, and `resume_master_agent_task` feeds the decision back via `Command`. |
| Is there an existing no-approval mode? | **Yes.** `AUTO_APPROVE`, honored inside `_approval_node`. `app/config.py:131` refuses to start when it is set outside `ENVIRONMENT=development`. |

### 1.1 Why the tool loop cannot host the interrupt

The obvious design — raise `interrupt()` from inside the tool loop — does not work, and fails in a way that would be hard to diagnose.

`InternalAgentRunner`'s tool loop runs inside `MasterAgent._sub_agent_executor_node`, and that node dispatches sub-agents concurrently:

```python
results_list = await asyncio.gather(*tasks, return_exceptions=True)   # master.py:687
...
if isinstance(r, Exception):                                          # master.py:691
    results[key] = {"status": "failed", ...}
```

`return_exceptions=True` **captures** `GraphInterrupt` as a result rather than propagating it. It would then be classified as a failed sub-agent. The graph would not suspend, no approval would take effect, and the model would be told the tool failed.

There is a second reason, independent of the first. `interrupt()` re-runs its node from the top on resume and discards the writes made before suspending — the docstring on `_approval_node` says so explicitly. `_sub_agent_executor_node` is where **all** tool execution happens, so suspending inside it means every sibling sub-agent's already-executed tools run again on resume.

This is why the existing design puts the interrupt in `approval_node`: **a side-effect-free node is the only safe place to suspend.** Phase 3 does not move it.

---

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | `run_python` returns `needs_approval` and lets the **existing** `validation_node → approval_node → re_execute` loop do the suspending. | `interrupt()` from the tool loop (§1.1: swallowed by `gather`, and would replay sibling side effects). |
| D2 | The approval record pins **`sha256(code)`**. Execution requires an approved record whose digest matches the code being run. | Approving "the run" rather than "this code": the node re-runs on resume and the model may author different code, so approval would cover code nobody read — the same laundering hole Phase 1 closed with the bundle digest. |
| D3 | Execution reuses `skill-runner` with a one-file bundle. **No runner changes.** | A third sandbox: the runner already accepts `files` + `argv`, and `_validate_argv` only requires `argv[1]` to be present in the bundle. |
| D4 | `script_network` is always `none`. Phase 2's allowlist is **not** available to `run_python`. | Model-authored code plus egress is an exfiltration path with no reviewer. |
| D5 | A per-agent `code_execution_mode` column: `off` \| `approval` \| `auto`, default `approval`. | `AUTO_APPROVE` alone (development-only by design, so it cannot serve a production need); a global switch (all agents or none, no middle setting); a per-conversation toggle (lets the person being gated ungate themselves, which contradicts the `separation_of_duties` marking the project already records). |
| D6 | `run_python` is a built-in, never a `Tool` row. | A `Tool` row would carry Phase 1's promotion semantics — a prior human review and a pinned bundle — neither of which exists for code written seconds ago. |

---

## 3. The loop

```
model calls run_python(code)
  ├─ mode == "off"       -> refuse, tell the model this agent cannot run code
  ├─ mode == "auto"      -> execute in the sandbox; no approval record is
  │                          created, but the audit entry carries the digest
  └─ mode == "approval"
       ├─ an approved record for this run with this digest exists -> execute
       └─ otherwise -> create a pending record holding the code and its digest,
                       return {"status": "needs_approval"}
                           |
                           v
       master.py:780 sets approval_required
       validation_node --rejected--> approval_node   (side-effect free)
                           |  interrupt() suspends; the human sees the full code
                           v  approve
       resume_master_agent_task -> approval_node --re_execute--> sub_agent_executor_node
                           |
                           v  model calls run_python again; digest matches; it runs
```

Nothing in this diagram is new except the two `run_python` branches. The routing, the suspension, the resume task and the round accounting (`approval_round`, `_approval_is_current`) already exist and already work.

### 3.0 What "this run" means, and the one wire that is missing

An approval record is scoped by the graph's **`request_id`** — the same value
`_approval_node` already uses to build its deterministic per-round request id. A
record authorizes `(request_id, sha256(code))` and nothing else, so an approval
granted in one conversation turn cannot be spent in another.

That value does not currently reach the tool loop. `MasterAgent` puts it in
`dispatch_context` (`master.py:439`), which arrives as `context` at
`AgentExecutor.execute`, but line 376 pulls only `conversation_id` and
`pre_approved` out of it, and `InternalAgentRunner.execute(task, conversation_id,
user_id)` has no parameter for it.

So Phase 3 includes one small plumbing change: forward `request_id` and the
agent's `code_execution_mode` from `context` into the runner. Without it
`run_python` has no key to scope a record by, and "approved for this run" cannot
be expressed.

### 3.1 The weak point, stated plainly

On resume the node re-runs, the model is called again, and it may author **different** code. Then the digest will not match and a second approval round opens.

- **Safety is not affected.** Unapproved code never executes; that is what D2 guarantees.
- **The experience can loop.** A cap of 3 `run_python` approval rounds per run bounds it; past that the tool refuses and says why.

A stronger variant exists: have the executor node run approved-but-unexecuted code records directly before dispatching sub-agents, so the model never has to reproduce anything. It removes the non-determinism entirely but restructures the executor node. Deferred, because the failure mode of the simpler design is safe rather than dangerous.

---

## 4. Execution mode

New column on `agent_configs` (migration `039_agent_code_execution_mode`):

| Column | Type | Meaning |
|---|---|---|
| `code_execution_mode` | `VARCHAR(20) NOT NULL DEFAULT 'approval'` | `off` \| `approval` \| `auto` |

- Default is `approval`, so existing agents gain the capability in its gated form and nothing changes silently.
- Changing it requires `AGENT_WRITE` and writes an audit record naming the old and new value.
- `auto` skips **only the human**. Kill switch, gatekeeper, the audit chain, the sandbox and the network isolation all still apply. "Auto" means no human in the loop, not ungated.
- Every `auto` execution is audited with the code digest and the code itself, so what ran without review is still recoverable afterwards.
- `AUTO_APPROVE` is untouched and stays a development convenience. `code_execution_mode` is the production control.

### 4.1 Why per-agent rather than global

The realistic need is "this analysis agent should compute things without interrupting me", not "no code anywhere needs review". A per-agent column expresses the first without implying the second, and it keeps the blast radius of a mistaken `auto` to one agent.

---

## 5. Governance metadata

`_tool_meta()` currently reports `observe`/`low` for every built-in (`kb_search`, `web_search`, `vuln_search`, `load_skill`). `run_python` must not join that list — it is the one built-in that executes caller-authored code.

It reports `action_category="mutate"` and `risk_tier="high"`, so the gatekeeper treats it as what it is, and so an operator tightening category rules catches it rather than skipping past it as another read-only helper.

The approval requirement in `approval` mode is **in code, not policy**: it does not read a gatekeeper threshold that could later be relaxed to zero. The way to remove the human is to set `code_execution_mode`, which is an explicit, audited, per-agent act.

---

## 6. Failure modes

| Condition | Behavior |
|---|---|
| `mode == "off"` | Tool refuses with a message the model can act on |
| Digest mismatch after resume | New approval round, up to the cap (§3.1) |
| More than 3 approval rounds in one run | Refuse and say so |
| Approval rejected | Existing `approval_node → error_node` path |
| Approval expires (60 min, existing) | Existing expiry handling; the code never runs |
| Sandbox unreachable | Same error shape as any skill-script run |
| Script times out / exceeds output | Existing runner limits (SIGKILL on the process group, 64 KB cap) |

---

## 7. Testing

- Digest binding: an approved record for code A does not authorize code B
- Mode routing: `off` refuses; `approval` returns `needs_approval` on first call; `auto` executes without a record
- `needs_approval` from `run_python` sets `approval_required` and routes to `approval_node`
- Approval round cap refuses the fourth attempt within one `request_id`
- `run_python` posts to the no-network runner and never sets `proxy_url`
- `_tool_meta("run_python")` is not `observe`/`low`
- Changing `code_execution_mode` requires `AGENT_WRITE` and writes an audit record
- `request_id` and `code_execution_mode` reach the runner (§3.0), since without
  the first there is no way to scope a record to a run
- Static invariant: `run_python` never reaches `SKILL_RUNNER_NET_URL`
- End to end: propose → approve → execute → result returns to the model

---

## 7.1 Correction from implementation

Two things the design did not anticipate, found while building it and recorded
here rather than left in the commit log:

**`mutate` is denied by default.** §5 chose `action_category = "mutate"` so the
tool would be visible to category rules. It is more than visible: `gatekeeper.py`
forbids `mutate` in a POC, requires `L3` autonomy for it, and leaves it out of
`DEFAULT_ALLOWED`. A stock deployment therefore refuses `run_python` outright.
That is the right answer — the taxonomy has no "always ask a human" tier, and
every alternative category is either ungated or denied for want of a rollback
procedure — but it means `approval` is the default *mode*, not the default
*behaviour*. Enabling the tool is three deliberate settings on the agent.

**The generic escalation had to defer to the specific one.** The gatekeeper
escalates `run_python` on its confidence heuristic before `_run_python` runs, so
the first record a reviewer saw carried no code and the code-carrying record
appeared a round later. For this one tool a `NEEDS_APPROVAL` verdict now falls
through to the tool's own gate, which opens an approval holding the program and
its digest. `DENY` still short-circuits.

## 8. Out of scope

- Network access for model-authored code (D4)
- Interpreters other than `python3`, and third-party packages — the sandbox's existing limits stand
- The stronger re-execution design in §3.1
- Fixing the pre-existing replay behavior in §9

---

## 9. A pre-existing behavior this inherited, and then had to fix

`approval_node --re_execute--> sub_agent_executor_node` re-ran the whole
executor node after any approval, so sibling sub-agents' already-executed tools
ran a second time.

This was written up as "Phase 3 neither worsens nor fixes it". That turned out
to be wrong on the first half. `_approval_decision` routes to `re_execute` only
when some sub-result reports `needs_approval`, and until a gated tool's
`needs_approval` reached the graph, the internal-agent path always reported
`completed` — so that route was dead for this transport. Making the status
propagate brought the replay to life.

The node now carries forward results that already completed and dispatches only
the rest (`tasks_needing_dispatch`). A task whose key does not match a completed
result is dispatched, so an unmatched key repeats work — today's behaviour —
rather than skipping work that never ran.

The stronger design in §3.1 remains deferred; it is not blocked by this.
