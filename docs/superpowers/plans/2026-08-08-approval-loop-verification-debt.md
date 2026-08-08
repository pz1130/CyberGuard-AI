---
name: approval-loop-verification-debt
description: What the 2026-08-08 approval-loop work did NOT prove, plus two local-only repo footguns. Companion to commits cd59555..fffe507.
type: project
---

# Approval loop — verification debt

**Date:** 2026-08-08
**Covers:** `cd59555` … `fffe507` on `security-enhance`

Named separately from the feature backlog because these are gaps in what has
been **proven**, not in what has been built. Everything below is a known hole,
deliberately recorded rather than quietly carried.

## The big one: no end-to-end run of the approval path

**Every test of the approval loop is mocked.** The three layers that have never
been exercised together are a real LLM provider, a Celery worker, and the
`AsyncPostgresSaver` checkpointer. The suite proves the state machine; it
proves nothing about the wiring between processes — and the whole point of the
`interrupt()` rework is that the decision arrives in the API process while the
run lives in a worker.

The manual pass worth doing before this ships:

1. Submit a task that trips a gate (a high-permission agent, or a tool whose
   `action_category` is `remediate` / `mutate`).
2. Confirm the execution record reports `waiting_approval` and the chat shows
   the pause rather than spinning.
3. Approve it in the Approvals UI.
4. **Confirm the action actually ran** — not that the run "completed". The
   defect being fixed was precisely a run that summarised itself without ever
   performing the approved action.
5. Repeat with a run that hits a *second* gate. It must stop again. That is the
   case `approval_round` exists for, and the one a mocked test can flatter.

Also worth checking under a real checkpointer: a worker restart between suspend
and resume. `MemorySaver` (what the tests use) cannot show that.

## Smaller gaps

- **No test runner in `webui/`.** No vitest/jest, no test files, no `test`
  script. Frontend changes are verifiable only by `tsc -b` and `eslint`, so the
  chat poller's `waiting_approval` handling has no regression test.
  `eslint src/pages/Chat.tsx` reports **16 pre-existing problems** — that is
  the baseline to compare against, not a clean sheet.
- **`escalate_to_human_below` now fires, and no one has tuned it.**
  `estimate_tool_confidence` is a heuristic picked to be defensible, not
  calibrated against real traffic. The default threshold is `0.60`; an untagged
  `mutate` tool with empty arguments scores below that. Expect the escalation
  rate to need tuning once real tool inventory runs through it.
- **MCP tools are still mostly untagged.** `_tool_meta` falls back to
  `observe` when `action_category` / `risk_tier` are NULL, so for untagged MCP
  tools the *category* rules remain inert. What genuinely landed for them is
  the kill switch and the audit trail. **Tagging the existing MCP inventory is
  outstanding operational work** — without it the gate is thinner than it looks.
- **The recovery sweep only reports.** Nothing acts on an interrupted run, by
  design, but there is no UI for the report either — it exists only in the
  startup log.

## Local-only repo footguns

Neither is in version control, so a fresh clone will not have them and reading
the repo will not reveal them.

- **`.git/hooks/post-commit`** used to run `git push origin main`
  unconditionally — pushing `main` regardless of the branch being committed, so
  it neither backed up the work in progress nor stayed out of the way. It only
  looked harmless because local `main` was behind and every push was rejected;
  once `main` caught up it would have begun publishing unreviewed `main` to the
  public repo on every commit. **Fixed 2026-08-08** to push the current branch,
  with a detached-HEAD guard. Original preserved at
  `.git/hooks/post-commit.orig-backup`.
- **`.gitignore` ends with a blanket `*.png`.** Existing tracked assets
  (`webui/src/assets/hero.png`) are unaffected, but any *new* image asset is
  silently ignored. Probably meant to catch agent debug screenshots only.

## Superseded work

An earlier attempt at this (PR #17, branch `agent-core-audit`) was built on the
2026-07 baseline and closed as superseded; its branch is deleted. The commits
remain reachable at `refs/pull/17/head` — `git fetch origin refs/pull/17/head`.
Do not resurrect it wholesale: it contained an `app/agents/validation.py` that
formalised keyword matching over agent output into a module, which is the
INV-13 violation this repo names as one to repair rather than copy, and audit
handling that swallowed write failures against INV-25 / INV-29.
