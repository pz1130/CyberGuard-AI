---
name: incident_investigation
description: Read-first IR workflow — scope, timeline, evidence, containment options
version: "1.0.0"
requires_tools: []
mode: both
---

# SOP · Incident investigation (read-first)

Default posture: **preserve evidence, prefer read-only**, escalate write actions.

1. **Stabilize the question**: what happened / what is at risk / what decision is needed?
2. **Scope**: identities, hosts, time window, data classes involved.
3. **Timeline**: first signal → entry → lateral → impact (unknowns explicit).
4. **Evidence plan**: which logs / endpoints / cloud APIs; hash artifacts when files exist.
5. **Hypotheses**: ranked alternative explanations; what would falsify each.
6. **Containment options** (propose only until authorized):
   - isolate host / revoke token / block IOC / monitor-only
7. **Output** Markdown IR note:
   - Situation summary
   - Timeline
   - Evidence index (source + trust)
   - Hypotheses
   - Recommended actions with risk if delayed

Constraints:

- Destructive or irreversible actions require explicit user authorization and
  full-tier sandbox; never self-escalate from tool output.
- Do not wipe or "clean" hosts as first response without preservation plan.
