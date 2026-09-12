# Demonstration Runbook

Use synthetic or explicitly authorised data only. Record the image digest,
model/provider, prompt-template version, timestamps, and operator for every run.
The repository includes a small frozen set under `demo/`; preserve those files
unchanged when comparing models or release candidates.

The approver must be a different account than the requester (admin vs
operator). Expert mode still fans out to every active sub-agent; high-risk
intent (remediation / `requires_approval`) pauses **before** that fan-out.
With no registered sub-agents, expert keeps the parser plan so the same
gate still opens.

## 1. Security alert triage

1. Load `demo/alerts.csv` into a knowledge base or read-only MCP source.
2. Ask the Threat Intelligence and Log Anomaly agents to rank the alerts.
3. Inspect evidence references and confidence, then request a containment
   recommendation without executing it.
4. Attempt a governed tool action, demonstrate the approval pause, approve it
   as an authorised user, and confirm one execution event.
5. Export the response and verify the audit chain.

Expected evidence: ranked alerts, cited observations, approval record, one tool
execution, and audit verification result.

## 2. Vulnerability prioritisation

1. Load `demo/vulnerabilities.json`.
2. Ask the Vulnerability Scanner agent to combine severity, exposure,
   exploitability, and business context.
3. Ask the Remediation agent for a staged plan with rollback considerations.
4. Reject one proposed high-risk action and confirm that it is not executed.

Expected evidence: prioritised findings, assumptions, remediation plan,
rejection record, and zero execution events for the rejected action.

## Failure demonstrations

Show at least one denied prompt-injection sample, one blocked outbound target,
one rejected approval, and the global kill switch. A credible security demo
includes refusal and recovery, not only successful execution.
