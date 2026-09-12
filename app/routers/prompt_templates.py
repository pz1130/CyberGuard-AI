"""Prompt template CRUD router.

Provides reusable system prompts that the Chat UI can pick from to fill
the "CUSTOM SYSTEM PROMPT" / intent-parser / summarizer override fields.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db_context
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.models.prompt_template import PromptTemplate

logger = logging.getLogger(__name__)


VALID_CATEGORIES = {"system", "intent_parser", "summarizer", "general"}


class PromptTemplateRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    content: str
    category: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)
    content: str = Field(..., min_length=1)
    category: str = "general"
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)
    content: str | None = None
    category: str | None = None
    is_active: bool | None = None


router = APIRouter()


def _validate_category(cat: str) -> None:
    if cat not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {sorted(VALID_CATEGORIES)}",
        )


@router.get("/prompt-templates", response_model=list[PromptTemplateRead])
async def list_prompt_templates(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_permission(Permission.SETTINGS_READ)),
):
    """List prompt templates. Optionally filter by category."""
    stmt = select(PromptTemplate).order_by(desc(PromptTemplate.updated_at))
    if category:
        _validate_category(category)
        stmt = stmt.where(PromptTemplate.category == category)
    result = await db.execute(stmt)
    return [PromptTemplateRead.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/prompt-templates", response_model=PromptTemplateRead, status_code=201
)
async def create_prompt_template(
    body: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    _validate_category(body.category)
    tpl = PromptTemplate(
        name=body.name.strip(),
        description=body.description,
        content=body.content,
        category=body.category,
        is_active=body.is_active,
    )
    db.add(tpl)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Name already exists")
    await db.refresh(tpl)
    return PromptTemplateRead.model_validate(tpl)


@router.get("/prompt-templates/{tpl_id}", response_model=PromptTemplateRead)
async def get_prompt_template(
    tpl_id: int,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_permission(Permission.SETTINGS_READ)),
):
    tpl = await db.get(PromptTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return PromptTemplateRead.model_validate(tpl)


@router.put("/prompt-templates/{tpl_id}", response_model=PromptTemplateRead)
async def update_prompt_template(
    tpl_id: int,
    body: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    tpl = await db.get(PromptTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    if body.name is not None:
        tpl.name = body.name.strip()
    if body.description is not None:
        tpl.description = body.description
    if body.content is not None:
        tpl.content = body.content
    if body.category is not None:
        _validate_category(body.category)
        tpl.category = body.category
    if body.is_active is not None:
        tpl.is_active = body.is_active
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Name already exists")
    await db.refresh(tpl)
    return PromptTemplateRead.model_validate(tpl)


@router.delete("/prompt-templates/{tpl_id}", status_code=204)
async def delete_prompt_template(
    tpl_id: int,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    tpl = await db.get(PromptTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    await db.delete(tpl)
    await db.commit()


# ---------------------------------------------------------------------------
# Seed defaults
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: list[dict] = [
    {
        "name": "Pentest Auditor",
        "category": "system",
        "description": "Penetration testing and red-team analysis reported using the PTES methodology.",
        "content": (
            "You are a senior penetration-testing auditor working under explicit "
            "authorization from the operator. Follow the PTES phases (recon → "
            "scanning → exploitation → post-exploitation → reporting).\n\n"
            "RULES:\n"
            "- Confirm authorization scope before running any active probe.\n"
            "- Prefer non-destructive checks; never execute denial-of-service.\n"
            "- For every finding output: title, CVSS v3 vector + score, "
            "evidence/PoC, business impact, remediation steps.\n"
            "- Cite tool output verbatim when summarising. If a step requires "
            "operator approval (e.g. exploit payload), pause and ask.\n"
        ),
    },
    {
        "name": "Threat Hunter",
        "category": "system",
        "description": "Hypothesis-driven threat hunting aligned with MITRE ATT&CK.",
        "content": (
            "You are a threat hunter. For each user request, generate a "
            "hypothesis-driven hunt plan aligned to MITRE ATT&CK.\n\n"
            "Output format:\n"
            "1. Hypothesis (single sentence, testable).\n"
            "2. ATT&CK techniques mapped (Txxxx.xxx).\n"
            "3. Data sources & queries (sigma / KQL / SPL where applicable).\n"
            "4. Expected baseline vs. anomalous signal.\n"
            "5. Triage / escalation criteria.\n"
            "Never invent IoCs. If insufficient telemetry, say so and propose "
            "the missing data source."
        ),
    },
    {
        "name": "SOC Analyst (L2)",
        "category": "system",
        "description": "L2 SOC analysis with incident triage and priority-based response.",
        "content": (
            "You are an L2 SOC analyst. For every alert or log excerpt, "
            "produce a triage report:\n"
            "- Verdict: True Positive / False Positive / Benign / Needs more "
            "data.\n"
            "- Severity (P1–P4) with one-line justification.\n"
            "- Attacker objective (per ATT&CK tactic).\n"
            "- Containment & eradication steps, in priority order.\n"
            "- Suggested detection-engineering follow-up (rule tuning, new "
            "signature, telemetry gap).\n"
            "Be calibrated — express confidence in % when verdict is uncertain."
        ),
    },
    {
        "name": "Incident Responder",
        "category": "system",
        "description": "Incident response coordination following NIST SP 800-61.",
        "content": (
            "You are an incident response coordinator following NIST SP 800-61 "
            "(Preparation, Detection & Analysis, Containment / Eradication / "
            "Recovery, Post-Incident Activity).\n\n"
            "For each operator update:\n"
            "- Maintain a running timeline with UTC timestamps.\n"
            "- Track affected assets, compromised credentials, and IoCs in a "
            "structured list.\n"
            "- Recommend the next single highest-priority action; do not "
            "expand scope without operator approval.\n"
            "- Draft holding statements for stakeholders (technical / "
            "executive / regulator) on demand.\n"
        ),
    },
    {
        "name": "Vulnerability Triage",
        "category": "system",
        "description": "Prioritizes vulnerabilities by exploitability, exposure, and business impact.",
        "content": (
            "You triage vulnerabilities for a security operations team. Given "
            "a CVE list or scanner export, rank items by:\n"
            "1. Known exploitation in the wild (CISA KEV, EPSS > 0.5).\n"
            "2. Internet-facing exposure of the affected asset.\n"
            "3. Business criticality of the host / data.\n"
            "4. CVSS v3 base score (tiebreaker only).\n\n"
            "Output a table with: CVE, EPSS, KEV, Exposure, Asset Tier, "
            "Priority (P1–P4), Remediation Owner, ETA. Flag anything where "
            "input data is missing instead of guessing."
        ),
    },
    {
        "name": "Compliance Reviewer (ISO 27001 / NIST CSF)",
        "category": "system",
        "description": "Assesses controls against ISO 27001 Annex A and NIST CSF.",
        "content": (
            "You are a compliance reviewer for ISO 27001 (Annex A) and NIST "
            "CSF 2.0. For each control or evidence artefact provided:\n"
            "- Identify mapped controls (e.g. A.8.16, GV.PO-01).\n"
            "- Rate maturity: Initial / Managed / Defined / Quantitatively "
            "Managed / Optimising.\n"
            "- List gaps with concrete remediation actions and owner role "
            "suggestions.\n"
            "- Cite the source paragraph rather than paraphrasing standards.\n"
            "Never claim certification readiness from incomplete evidence."
        ),
    },
    {
        "name": "Secure Code Reviewer (OWASP)",
        "category": "general",
        "description": "Secure code review mapped to the OWASP Top 10 and CWE.",
        "content": (
            "You review code for security defects. For each finding emit:\n"
            "- File:line range, code excerpt.\n"
            "- CWE id and OWASP Top 10 category.\n"
            "- Exploitation scenario in 2–3 sentences.\n"
            "- Suggested patch (diff or function rewrite).\n"
            "- Severity: Critical / High / Medium / Low (justified).\n\n"
            "Prioritise: injection, auth/session, access control, cryptographic "
            "misuse, SSRF, deserialisation, secrets handling, supply chain.\n"
            "Do NOT flag style issues. Be specific — vague advice like "
            "'sanitise input' is forbidden; show the exact transform."
        ),
    },
    {
        "name": "Concise Bullet Summarizer",
        "category": "summarizer",
        "description": "Condenses a conversation into three to five key points.",
        "content": (
            "Summarise the conversation so far in 3–5 short bullets. "
            "Preserve: key decisions, outstanding action items (with owner), "
            "and any approval-pending requests. Drop pleasantries and "
            "tool-call boilerplate. Keep to plain English, no markdown headers."
        ),
    },
    {
        "name": "Intent Router (Cyber Ops)",
        "category": "intent_parser",
        "description": "Routes each user message to the appropriate sub-agent.",
        "content": (
            "Classify the user message into ONE of the following intents and "
            "return JSON {intent, target_agent, confidence}:\n"
            "- recon          → reconnaissance / OSINT agent\n"
            "- vuln_scan      → vulnerability scanner agent\n"
            "- exploit        → exploitation agent (requires approval)\n"
            "- forensics      → DFIR / log-analysis agent\n"
            "- threat_intel   → threat-intel enrichment agent\n"
            "- general_chat   → master agent only\n\n"
            "If confidence < 0.6 OR the message asks for an exploit, set "
            "target_agent to 'master' and confidence accordingly. Output JSON "
            "only — no prose."
        ),
    },
]


# Descriptions shipped before the English-language release candidate. They are
# retained only to identify untouched built-in rows during an upgrade.
LEGACY_DEFAULT_DESCRIPTIONS = {
    "Pentest Auditor": "渗透测试 / 红队视角，按 PTES 流程汇报。",
    "Threat Hunter": "基于假设驱动的威胁狩猎，对齐 MITRE ATT&CK。",
    "SOC Analyst (L2)": "二级 SOC 分析师，按事件优先级分级响应。",
    "Incident Responder": "事件响应协调员，遵循 NIST SP 800-61 流程。",
    "Vulnerability Triage": "对漏洞按可利用性 / 暴露面 / 业务影响排序。",
    "Compliance Reviewer (ISO 27001 / NIST CSF)": (
        "对照 ISO 27001 Annex A 与 NIST CSF 评估控制项。"
    ),
    "Secure Code Reviewer (OWASP)": "代码安全审查，对照 OWASP Top 10 + CWE。",
    "Concise Bullet Summarizer": "把多轮对话压缩为 3–5 条要点。",
    "Intent Router (Cyber Ops)": "把用户消息路由到合适的 sub-agent。",
}


async def seed_prompt_templates_on_startup() -> None:
    """Insert built-in templates and migrate untouched legacy descriptions.

    Idempotent: matches by name. User-edited rows are never overwritten; an
    existing description is migrated only when it exactly matches the legacy
    built-in Chinese text.
    """
    async with get_db_context() as session:
        existing = await session.execute(select(PromptTemplate))
        by_name = {row.name: row for row in existing.scalars().all()}
        inserted = 0
        migrated = 0
        for tpl in DEFAULT_TEMPLATES:
            current = by_name.get(tpl["name"])
            if current is not None:
                legacy_description = LEGACY_DEFAULT_DESCRIPTIONS.get(tpl["name"])
                if current.description == legacy_description:
                    current.description = tpl["description"]
                    migrated += 1
                continue
            session.add(PromptTemplate(**tpl))
            inserted += 1
        if inserted or migrated:
            await session.commit()
            logger.info(
                "Prompt templates ready: inserted=%d, migrated=%d",
                inserted,
                migrated,
            )
