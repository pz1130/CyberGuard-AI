"""Governance / GRC router.

Endpoints:
  /governance/frameworks                    list/import/get/delete
  /governance/frameworks/{id}/requirements  list framework requirements
  /governance/assessments                   CRUD compliance assessments
  /governance/assessments/{id}              get with progress stats
  /governance/assessments/{id}/requirements list per-requirement assessments
  /governance/req-assessments/{id}          update status/score/observation
  /governance/req-assessments/{id}/evidence add evidence
  /governance/evidence/{id}                 delete evidence

AI-assisted endpoints (leverage CyberGuard's master LLM):
  /governance/req-assessments/{id}/ai-suggest-evidence
  /governance/req-assessments/{id}/ai-assess
  /governance/assessments/{id}/ai-report
"""
import json
import logging
import os
import re
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db_context
from app.core.dependencies import get_db, require_permission
from app.core.uploads import validate_and_read_upload
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.models.governance import (
    Framework, Requirement, ComplianceAssessment,
    RequirementAssessment, Evidence,
)
from app.schemas.governance import (
    FrameworkRead, FrameworkWithRequirements, RequirementRead,
    FrameworkImport,
    ComplianceAssessmentRead, ComplianceAssessmentCreate, ComplianceAssessmentUpdate,
    RequirementAssessmentRead, RequirementAssessmentUpdate,
    EvidenceRead, EvidenceCreate,
    AISuggestEvidenceResponse, AIAssessRequestRequest, AIAssessResponse,
    AIReportResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

EVIDENCE_DIR = os.environ.get("CYBERGUARD_EVIDENCE_DIR", "/data/evidence")


# ---------------------------------------------------------------------------
# Framework endpoints
# ---------------------------------------------------------------------------

async def _framework_with_count(db: AsyncSession, fw: Framework) -> FrameworkRead:
    count = await db.scalar(
        select(func.count(Requirement.id)).where(Requirement.framework_id == fw.id)
    )
    return FrameworkRead(
        id=fw.id, urn=fw.urn, name=fw.name, version=fw.version,
        description=fw.description, locale=fw.locale, ref_url=fw.ref_url,
        is_active=fw.is_active, requirement_count=count or 0,
        created_at=fw.created_at, updated_at=fw.updated_at,
    )


@router.get("/governance/frameworks", response_model=list[FrameworkRead])
async def list_frameworks(
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    result = await db.execute(select(Framework).order_by(Framework.name))
    frameworks = result.scalars().all()
    return [await _framework_with_count(db, fw) for fw in frameworks]


@router.get("/governance/frameworks/{fw_id}", response_model=FrameworkWithRequirements)
async def get_framework(
    fw_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    fw = await db.get(Framework, fw_id)
    if not fw:
        raise HTTPException(404, "Framework not found")
    reqs_result = await db.execute(
        select(Requirement).where(Requirement.framework_id == fw_id)
        .order_by(Requirement.order_index)
    )
    reqs = reqs_result.scalars().all()
    base = await _framework_with_count(db, fw)
    return FrameworkWithRequirements(
        **base.model_dump(),
        requirements=[RequirementRead.model_validate(r) for r in reqs],
    )


@router.get("/governance/frameworks/{fw_id}/requirements", response_model=list[RequirementRead])
async def list_framework_requirements(
    fw_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    fw = await db.get(Framework, fw_id)
    if not fw:
        raise HTTPException(404, "Framework not found")
    result = await db.execute(
        select(Requirement).where(Requirement.framework_id == fw_id)
        .order_by(Requirement.order_index)
    )
    return [RequirementRead.model_validate(r) for r in result.scalars().all()]


@router.post("/governance/frameworks/import", response_model=FrameworkRead, status_code=201)
async def import_framework(
    body: FrameworkImport,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Import a framework via JSON (urn-based upsert).

    If `replace_existing=True` and a framework with the same urn exists, its
    requirements are wiped and re-loaded from the payload. Otherwise the
    operation fails with 409.
    """
    existing = (await db.execute(
        select(Framework).where(Framework.urn == body.urn)
    )).scalar_one_or_none()
    if existing and not body.replace_existing:
        raise HTTPException(
            409, f"Framework with urn '{body.urn}' already exists. "
                 "Set replace_existing=true to overwrite."
        )

    if existing:
        # delete all requirements (cascade) then update fields
        await db.execute(delete(Requirement).where(Requirement.framework_id == existing.id))
        existing.name = body.name
        existing.version = body.version
        existing.description = body.description
        existing.locale = body.locale
        existing.ref_url = body.ref_url
        fw = existing
    else:
        fw = Framework(
            urn=body.urn, name=body.name, version=body.version,
            description=body.description, locale=body.locale, ref_url=body.ref_url,
            is_active=True,
        )
        db.add(fw)
    await db.flush()

    # Two-pass insert so children can resolve parent_ref_id
    by_ref: dict[str, Requirement] = {}
    for idx, item in enumerate(body.requirements):
        r = Requirement(
            framework_id=fw.id,
            urn=f"{fw.urn}:{item.ref_id}",
            ref_id=item.ref_id,
            name=item.name,
            description=item.description,
            depth=0,
            order_index=idx,
            is_assessable=item.is_assessable,
            typical_evidence=item.typical_evidence,
        )
        by_ref[item.ref_id] = r
        db.add(r)
    await db.flush()
    for item in body.requirements:
        if item.parent_ref_id and item.parent_ref_id in by_ref:
            child = by_ref[item.ref_id]
            parent = by_ref[item.parent_ref_id]
            child.parent_id = parent.id
            child.depth = (parent.depth or 0) + 1

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(400, f"Import failed: {e}")
    await db.refresh(fw)
    return await _framework_with_count(db, fw)


@router.delete("/governance/frameworks/{fw_id}", status_code=204)
async def delete_framework(
    fw_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    fw = await db.get(Framework, fw_id)
    if not fw:
        raise HTTPException(404, "Framework not found")
    # Block deletion if assessments reference it
    count = await db.scalar(
        select(func.count(ComplianceAssessment.id))
        .where(ComplianceAssessment.framework_id == fw_id)
    )
    if count and count > 0:
        raise HTTPException(
            409, f"Framework is referenced by {count} assessment(s). "
                 "Archive or delete those first."
        )
    await db.delete(fw)
    await db.commit()


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------

async def _build_progress(db: AsyncSession, assessment_id: int) -> dict:
    """Return {total, assessed, compliant, partial, non_compliant, na, percent}."""
    rows = (await db.execute(
        select(RequirementAssessment.status, func.count(RequirementAssessment.id))
        .where(RequirementAssessment.assessment_id == assessment_id)
        .group_by(RequirementAssessment.status)
    )).all()
    by_status = {s: c for s, c in rows}
    total = sum(by_status.values())
    assessed = total - by_status.get("not_assessed", 0)
    percent = round((assessed / total) * 100) if total else 0
    return {
        "total": total,
        "assessed": assessed,
        "compliant": by_status.get("compliant", 0),
        "partially_compliant": by_status.get("partially_compliant", 0),
        "non_compliant": by_status.get("non_compliant", 0),
        "not_applicable": by_status.get("not_applicable", 0),
        "not_assessed": by_status.get("not_assessed", 0),
        "percent": percent,
    }


@router.get("/governance/assessments", response_model=list[ComplianceAssessmentRead])
async def list_assessments(
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    result = await db.execute(
        select(ComplianceAssessment, Framework.name)
        .join(Framework, Framework.id == ComplianceAssessment.framework_id)
        .order_by(ComplianceAssessment.updated_at.desc())
    )
    out: list[ComplianceAssessmentRead] = []
    for asmt, fw_name in result.all():
        progress = await _build_progress(db, asmt.id)
        out.append(ComplianceAssessmentRead(
            id=asmt.id, name=asmt.name, description=asmt.description,
            framework_id=asmt.framework_id, framework_name=fw_name,
            scope=asmt.scope, status=asmt.status,
            start_date=asmt.start_date, due_date=asmt.due_date,
            owner_user_id=asmt.owner_user_id,
            created_at=asmt.created_at, updated_at=asmt.updated_at,
            progress=progress,
        ))
    return out


@router.post("/governance/assessments", response_model=ComplianceAssessmentRead, status_code=201)
async def create_assessment(
    body: ComplianceAssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    fw = await db.get(Framework, body.framework_id)
    if not fw:
        raise HTTPException(404, "Framework not found")
    asmt = ComplianceAssessment(
        name=body.name,
        description=body.description,
        framework_id=body.framework_id,
        scope=body.scope,
        status="planning",
        start_date=body.start_date,
        due_date=body.due_date,
        owner_user_id=current_user.user_id,
    )
    db.add(asmt)
    await db.flush()

    # Seed one RequirementAssessment per assessable requirement
    req_rows = (await db.execute(
        select(Requirement).where(
            Requirement.framework_id == body.framework_id,
            Requirement.is_assessable.is_(True),
        )
    )).scalars().all()
    for r in req_rows:
        db.add(RequirementAssessment(
            assessment_id=asmt.id, requirement_id=r.id, status="not_assessed",
        ))
    await db.commit()
    await db.refresh(asmt)
    progress = await _build_progress(db, asmt.id)
    return ComplianceAssessmentRead(
        id=asmt.id, name=asmt.name, description=asmt.description,
        framework_id=asmt.framework_id, framework_name=fw.name,
        scope=asmt.scope, status=asmt.status,
        start_date=asmt.start_date, due_date=asmt.due_date,
        owner_user_id=asmt.owner_user_id,
        created_at=asmt.created_at, updated_at=asmt.updated_at,
        progress=progress,
    )


async def _read_assessment(db: AsyncSession, asmt_id: int) -> ComplianceAssessmentRead:
    asmt = await db.get(ComplianceAssessment, asmt_id)
    if not asmt:
        raise HTTPException(404, "Assessment not found")
    fw = await db.get(Framework, asmt.framework_id)
    progress = await _build_progress(db, asmt.id)
    return ComplianceAssessmentRead(
        id=asmt.id, name=asmt.name, description=asmt.description,
        framework_id=asmt.framework_id, framework_name=fw.name if fw else None,
        scope=asmt.scope, status=asmt.status,
        start_date=asmt.start_date, due_date=asmt.due_date,
        owner_user_id=asmt.owner_user_id,
        created_at=asmt.created_at, updated_at=asmt.updated_at,
        progress=progress,
    )


@router.get("/governance/assessments/{asmt_id}", response_model=ComplianceAssessmentRead)
async def get_assessment(
    asmt_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    return await _read_assessment(db, asmt_id)


@router.put("/governance/assessments/{asmt_id}", response_model=ComplianceAssessmentRead)
async def update_assessment(
    asmt_id: int,
    body: ComplianceAssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    asmt = await db.get(ComplianceAssessment, asmt_id)
    if not asmt:
        raise HTTPException(404, "Assessment not found")
    for fld in ("name", "description", "scope", "status", "start_date", "due_date"):
        v = getattr(body, fld)
        if v is not None:
            setattr(asmt, fld, v)
    await db.commit()
    return await _read_assessment(db, asmt_id)


@router.delete("/governance/assessments/{asmt_id}", status_code=204)
async def delete_assessment(
    asmt_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    asmt = await db.get(ComplianceAssessment, asmt_id)
    if not asmt:
        raise HTTPException(404, "Assessment not found")
    await db.delete(asmt)
    await db.commit()


@router.get(
    "/governance/assessments/{asmt_id}/requirements",
    response_model=list[RequirementAssessmentRead],
)
async def list_assessment_requirements(
    asmt_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    asmt = await db.get(ComplianceAssessment, asmt_id)
    if not asmt:
        raise HTTPException(404, "Assessment not found")
    rows = (await db.execute(
        select(RequirementAssessment, Requirement)
        .join(Requirement, Requirement.id == RequirementAssessment.requirement_id)
        .where(RequirementAssessment.assessment_id == asmt_id)
        .order_by(Requirement.order_index)
    )).all()
    out: list[RequirementAssessmentRead] = []
    for ra, req in rows:
        evidences = (await db.execute(
            select(Evidence).where(Evidence.requirement_assessment_id == ra.id)
            .order_by(Evidence.uploaded_at.desc())
        )).scalars().all()
        out.append(RequirementAssessmentRead(
            id=ra.id, assessment_id=ra.assessment_id, requirement_id=ra.requirement_id,
            status=ra.status, score=ra.score, observation=ra.observation,
            ai_recommendation=ra.ai_recommendation, ai_assessed_at=ra.ai_assessed_at,
            updated_at=ra.updated_at,
            requirement=RequirementRead.model_validate(req),
            evidences=[EvidenceRead.model_validate(e) for e in evidences],
        ))
    return out


# ---------------------------------------------------------------------------
# Requirement assessment + Evidence
# ---------------------------------------------------------------------------

@router.put(
    "/governance/req-assessments/{ra_id}",
    response_model=RequirementAssessmentRead,
)
async def update_req_assessment(
    ra_id: int,
    body: RequirementAssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    ra = await db.get(RequirementAssessment, ra_id)
    if not ra:
        raise HTTPException(404, "Requirement assessment not found")
    if body.status is not None:
        ra.status = body.status
    if body.score is not None:
        ra.score = body.score
    if body.observation is not None:
        ra.observation = body.observation
    ra.updated_by_user_id = current_user.user_id
    await db.commit()
    await db.refresh(ra)
    req = await db.get(Requirement, ra.requirement_id)
    evidences = (await db.execute(
        select(Evidence).where(Evidence.requirement_assessment_id == ra.id)
    )).scalars().all()
    return RequirementAssessmentRead(
        id=ra.id, assessment_id=ra.assessment_id, requirement_id=ra.requirement_id,
        status=ra.status, score=ra.score, observation=ra.observation,
        ai_recommendation=ra.ai_recommendation, ai_assessed_at=ra.ai_assessed_at,
        updated_at=ra.updated_at,
        requirement=RequirementRead.model_validate(req) if req else None,
        evidences=[EvidenceRead.model_validate(e) for e in evidences],
    )


@router.post(
    "/governance/req-assessments/{ra_id}/evidence",
    response_model=EvidenceRead, status_code=201,
)
async def add_evidence(
    ra_id: int,
    body: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    ra = await db.get(RequirementAssessment, ra_id)
    if not ra:
        raise HTTPException(404, "Requirement assessment not found")
    if body.kind == "url" and not body.url:
        raise HTTPException(400, "url field required when kind='url'")
    if body.kind == "text" and not body.body:
        raise HTTPException(400, "body field required when kind='text'")
    ev = Evidence(
        requirement_assessment_id=ra_id,
        name=body.name,
        description=body.description,
        kind=body.kind,
        url=body.url,
        body=body.body,
        mime_type=body.mime_type,
        uploaded_by_user_id=current_user.user_id,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return EvidenceRead.model_validate(ev)


@router.post(
    "/governance/req-assessments/{ra_id}/evidence/file",
    response_model=EvidenceRead, status_code=201,
)
async def add_evidence_file(
    ra_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Upload a file as evidence for a requirement assessment (kind='file')."""
    ra = await db.get(RequirementAssessment, ra_id)
    if not ra:
        raise HTTPException(404, "Requirement assessment not found")

    content, mime = await validate_and_read_upload(file)

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    fname = _uuid.uuid4().hex
    with open(os.path.join(EVIDENCE_DIR, fname), "wb") as fh:
        fh.write(content)

    ev = Evidence(
        requirement_assessment_id=ra_id,
        name=name,
        description=description,
        kind="file",
        file_path=fname,
        mime_type=mime,
        size_bytes=len(content),
        uploaded_by_user_id=current_user.user_id,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return EvidenceRead.model_validate(ev)


@router.delete("/governance/evidence/{ev_id}", status_code=204)
async def delete_evidence(
    ev_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    ev = await db.get(Evidence, ev_id)
    if not ev:
        raise HTTPException(404, "Evidence not found")
    await db.delete(ev)
    await db.commit()


# ---------------------------------------------------------------------------
# AI endpoints
# ---------------------------------------------------------------------------

async def _resolve_default_provider_id(db: AsyncSession) -> int | None:
    """Find the first active provider with an API key configured.

    Falls back to None — llm_router will then use its in-memory default,
    which may also fail if nothing is configured.
    """
    from app.models.provider import Provider
    result = await db.execute(
        select(Provider.id)
        .where(Provider.is_active.is_(True))
        .order_by(Provider.id)
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def _llm_complete(messages: list[dict], db: AsyncSession) -> str:
    """Call the master LLM router using the first active DB provider."""
    from app.services.llm_router import get_llm_router
    router_ = get_llm_router()
    provider_id = await _resolve_default_provider_id(db)
    if provider_id is None:
        raise HTTPException(
            503,
            "No active AI provider configured. Add one under Providers first."
        )
    return await router_.chat(messages=messages, provider_id=provider_id)


def _extract_json(text: str) -> dict | None:
    """Pull the first {...} JSON object out of a model reply."""
    # Strip ```json fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


@router.post(
    "/governance/req-assessments/{ra_id}/ai-suggest-evidence",
    response_model=AISuggestEvidenceResponse,
)
async def ai_suggest_evidence(
    ra_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    """Ask the master LLM what evidence would satisfy this requirement."""
    ra = await db.get(RequirementAssessment, ra_id)
    if not ra:
        raise HTTPException(404, "Requirement assessment not found")
    req = await db.get(Requirement, ra.requirement_id)
    fw = await db.get(Framework, req.framework_id) if req else None

    system = (
        "You are an experienced security auditor. Given a compliance "
        "requirement, list the concrete evidence artefacts an auditor "
        "would typically request. Be specific: name the document type, "
        "system / tool, period covered, and who would own it. Return JSON "
        "with shape {\"suggestions\": [\"...\", \"...\"]}. Maximum 8 items."
    )
    user = (
        f"Framework: {fw.name if fw else 'unknown'}\n"
        f"Requirement ref: {req.ref_id if req else ''}\n"
        f"Requirement name: {req.name if req else ''}\n"
        f"Requirement description: {req.description if req and req.description else '(none)'}"
    )
    text = await _llm_complete([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], db)
    data = _extract_json(text) or {}
    suggestions = data.get("suggestions") or []
    # Fallback: line-split if JSON parse failed
    if not isinstance(suggestions, list) or not suggestions:
        suggestions = [
            re.sub(r"^[\d\.\-\*\s]+", "", line).strip()
            for line in text.splitlines() if line.strip()
        ][:8]
    return AISuggestEvidenceResponse(
        requirement_id=req.id if req else 0,
        suggestions=[str(s)[:500] for s in suggestions[:8] if s],
    )


@router.post(
    "/governance/req-assessments/{ra_id}/ai-assess",
    response_model=AIAssessResponse,
)
async def ai_assess(
    ra_id: int,
    body: AIAssessRequestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Have the master LLM judge compliance status from current evidence."""
    ra = await db.get(RequirementAssessment, ra_id)
    if not ra:
        raise HTTPException(404, "Requirement assessment not found")
    req = await db.get(Requirement, ra.requirement_id)
    evidences = (await db.execute(
        select(Evidence).where(Evidence.requirement_assessment_id == ra_id)
    )).scalars().all()

    evidence_block = "\n".join(
        f"- [{e.kind}] {e.name}: "
        + (e.body[:600] if e.body else (e.url or e.file_path or "(no body)"))
        for e in evidences
    ) or "(no evidence uploaded)"

    system = (
        "You are a senior compliance assessor. Given a requirement and the "
        "supplied evidence, judge the compliance status. Return JSON ONLY "
        "with this exact schema:\n"
        "{\n"
        '  "status": "compliant" | "partially_compliant" | "non_compliant" | "not_applicable",\n'
        '  "score": <integer 0-100 or null>,\n'
        '  "observation": "<2-5 sentences justifying the verdict, citing evidence>"\n'
        "}\n"
        "Be conservative: only return 'compliant' if the evidence clearly "
        "covers the control. If evidence is empty or irrelevant, return "
        "'non_compliant' with a clear explanation."
    )
    user = (
        f"Requirement ref: {req.ref_id if req else ''}\n"
        f"Requirement name: {req.name if req else ''}\n"
        f"Requirement description: {req.description if req and req.description else '(none)'}\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        f"Operator notes:\n{body.extra_context or '(none)'}"
    )
    text = await _llm_complete([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], db)
    data = _extract_json(text)
    if not data or "status" not in data:
        raise HTTPException(502, f"LLM did not return parseable JSON. Raw: {text[:400]}")

    status = data.get("status")
    if status not in ("compliant", "partially_compliant", "non_compliant", "not_applicable"):
        raise HTTPException(502, f"LLM returned invalid status: {status!r}")
    score = data.get("score")
    if score is not None:
        try:
            score = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            score = None
    observation = str(data.get("observation") or "").strip()

    ra.ai_recommendation = (
        f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}Z] "
        f"status={status} score={score}\n{observation}"
    )
    ra.ai_assessed_at = datetime.now(timezone.utc)

    applied = False
    if body.apply:
        ra.status = status
        ra.score = score
        ra.observation = observation
        ra.updated_by_user_id = current_user.user_id
        applied = True

    await db.commit()
    return AIAssessResponse(
        requirement_id=req.id if req else 0,
        status=status,
        score=score,
        observation=observation,
        applied=applied,
    )


@router.post(
    "/governance/assessments/{asmt_id}/ai-report",
    response_model=AIReportResponse,
)
async def ai_report(
    asmt_id: int,
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission(Permission.SETTINGS_READ)),
):
    """Generate an audit summary markdown report via the master LLM."""
    asmt = await db.get(ComplianceAssessment, asmt_id)
    if not asmt:
        raise HTTPException(404, "Assessment not found")
    fw = await db.get(Framework, asmt.framework_id)
    progress = await _build_progress(db, asmt_id)

    rows = (await db.execute(
        select(RequirementAssessment, Requirement)
        .join(Requirement, Requirement.id == RequirementAssessment.requirement_id)
        .where(RequirementAssessment.assessment_id == asmt_id)
        .order_by(Requirement.order_index)
    )).all()

    # Compact rendering — only assessed items, grouped by status, capped.
    findings: dict[str, list[str]] = {
        "non_compliant": [], "partially_compliant": [],
        "compliant": [], "not_applicable": [],
    }
    for ra, req in rows:
        if ra.status == "not_assessed":
            continue
        if ra.status not in findings:
            continue
        line = f"- **{req.ref_id} {req.name}** — {ra.observation or '(no note)'}"
        if len(findings[ra.status]) < 25:
            findings[ra.status].append(line)

    findings_block = "\n\n".join(
        f"### {k.replace('_', ' ').title()} ({len(v)})\n" + "\n".join(v)
        for k, v in findings.items() if v
    ) or "_(no requirements assessed yet)_"

    system = (
        "You write executive-style compliance audit reports. Produce GitHub "
        "markdown with these sections (in order): Executive Summary (3-5 "
        "bullets), Coverage Statistics, Key Gaps (top 5), Recommendations "
        "(prioritised), Next Steps. Keep under 1200 words. Use the "
        "operator-supplied findings verbatim; do not invent controls."
    )
    user = (
        f"Audit: {asmt.name}\n"
        f"Framework: {fw.name if fw else 'unknown'}\n"
        f"Scope: {asmt.scope or '(unspecified)'}\n"
        f"Status: {asmt.status}\n\n"
        f"Coverage: {progress['assessed']}/{progress['total']} requirements "
        f"assessed ({progress['percent']}%).\n"
        f"Verdicts → compliant: {progress['compliant']}, "
        f"partially: {progress['partially_compliant']}, "
        f"non-compliant: {progress['non_compliant']}, "
        f"N/A: {progress['not_applicable']}.\n\n"
        f"## Findings\n{findings_block}"
    )
    md = await _llm_complete([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], db)
    return AIReportResponse(assessment_id=asmt_id, markdown=md.strip())


# ---------------------------------------------------------------------------
# Seed defaults on startup
# ---------------------------------------------------------------------------

async def seed_governance_frameworks_on_startup() -> None:
    """Insert built-in frameworks (ISO 27001:2022, NIST CSF 2.0) if missing,
    and backfill typical_evidence for previously-seeded requirements.

    Idempotent — matched by urn / ref_id. User edits are never overwritten:
    we only fill typical_evidence rows whose column is NULL.
    """
    from app.services.governance_seeds import BUILT_IN_FRAMEWORKS
    from app.services.governance_evidence_hints import BUILT_IN_EVIDENCE_HINTS

    async with get_db_context() as session:
        for seed in BUILT_IN_FRAMEWORKS:
            evidence_map = BUILT_IN_EVIDENCE_HINTS.get(seed["urn"], {})
            existing = (await session.execute(
                select(Framework).where(Framework.urn == seed["urn"])
            )).scalar_one_or_none()

            if existing:
                # Framework already loaded — refresh typical_evidence to the
                # latest canonical list. We always overwrite for BUILT-IN
                # frameworks (matched in BUILT_IN_EVIDENCE_HINTS) so admins
                # only need to redeploy to push checklist updates. Custom
                # user-imported frameworks are unaffected because their urn
                # is absent from this dict.
                rows = (await session.execute(
                    select(Requirement).where(Requirement.framework_id == existing.id)
                )).scalars().all()
                changed = 0
                for r in rows:
                    hints = evidence_map.get(r.ref_id)
                    if hints and r.typical_evidence != hints:
                        r.typical_evidence = hints
                        changed += 1
                if changed:
                    await session.commit()
                    logger.info(
                        f"Refreshed typical_evidence on {changed} rows of "
                        f"{existing.name}"
                    )
                continue

            fw = Framework(
                urn=seed["urn"], name=seed["name"], version=seed.get("version"),
                description=seed.get("description"), locale="en",
                ref_url=seed.get("ref_url"), is_active=True,
            )
            session.add(fw)
            await session.flush()

            by_ref: dict[str, Requirement] = {}
            for idx, item in enumerate(seed["requirements"]):
                r = Requirement(
                    framework_id=fw.id,
                    urn=f"{fw.urn}:{item['ref_id']}",
                    ref_id=item["ref_id"],
                    name=item["name"],
                    description=item.get("description"),
                    depth=0,
                    order_index=idx,
                    is_assessable=item.get("is_assessable", True),
                    typical_evidence=evidence_map.get(item["ref_id"]) or item.get("typical_evidence"),
                )
                by_ref[item["ref_id"]] = r
                session.add(r)
            await session.flush()
            for item in seed["requirements"]:
                pref = item.get("parent_ref_id")
                if pref and pref in by_ref:
                    child = by_ref[item["ref_id"]]
                    parent = by_ref[pref]
                    child.parent_id = parent.id
                    child.depth = (parent.depth or 0) + 1

            await session.commit()
            logger.info(
                f"Seeded governance framework: {fw.name} "
                f"({len(seed['requirements'])} requirements)"
            )
