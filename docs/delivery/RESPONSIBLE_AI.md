# Responsible AI Statement

## Intended use

CyberGuard assists authorised security professionals with analysis,
prioritisation, and controlled tool use.

## Human accountability

- A named human owns every operational decision.
- High-risk actions require an authorised approval unless a development-only
  bypass is explicitly enabled; that bypass is rejected outside development.
- AI-generated summaries never replace examination of the source.
- Kill-switch and audit facilities support intervention and investigation.

## Prohibited or unsupported use

- Unauthorised access, scanning, surveillance, or remediation
- Fully autonomous destructive or irreversible actions
- Treating generated output as legal advice or audit certification
- Processing data through an external provider without an approved data-flow
  and retention assessment

## Known risks

Hallucination, incomplete evidence, biased prioritisation, prompt injection,
tool misuse, provider outage, and model/version drift remain possible. Controls
reduce these risks but do not eliminate them.

Prompt-injection screening in particular is narrow: rule-based, English-only,
and applied only to text a user types. Instructions embedded in attachments,
knowledge-base documents, or tool and MCP output are not screened; approval
gates, risk categories and the kill switch limit what such instructions can
cause, not what they can make the model say. See *Prompt-injection screening*
in ARCHITECTURE_AND_SECURITY.md.

## Operator duties

Use least privilege, constrain egress, configure retention, review provider
terms, keep secrets out of prompts, validate cited evidence, treat ingested
documents and tool output as untrusted input, monitor audit
events, and re-evaluate performance after model or prompt changes.
