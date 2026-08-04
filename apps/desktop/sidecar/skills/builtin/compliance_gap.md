---
name: compliance_gap
description: Lightweight control-gap review (advisory) against a stated framework
version: "1.0.0"
requires_tools: []
mode: advisory
---

# SOP · Compliance gap (advisory)

When the user asks about control coverage (ISO 27001, NIST CSF, CIS, internal policy):

1. **Pin the framework and scope** (org unit, systems, time horizon).
2. **Inventory stated controls** vs **observed evidence** (docs, configs, tickets).
3. **Gap classes**: missing / partial / implemented-but-unproven / out of scope.
4. **Risk-rank** gaps by likelihood × impact on stated objectives.
5. **Output** Markdown:
   - Scope & framework
   - Strengths (keep)
   - Top gaps with suggested evidence to collect
   - 30/60/90 day remediation sketch (optional)
   - Explicit non-findings (what was not assessed)

Constraints:

- This is **advisory**: no claim of certification readiness.
- Do not invent audit evidence; mark "not observed".
- Prefer short, decision-useful output over full GRC platform depth.
