from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission, Role, has_permission
from app.models.finding import Finding, FindingEvent
from app.models.user import User
from app.schemas.finding import FindingCreate, FindingChange, FindingStatus
from app.services.findings import create_finding, change_finding, serialize, report_markdown

router = APIRouter(prefix="/findings")


@router.get("")
async def list_findings(status: FindingStatus | None = None, offset: int = Query(0, ge=0),
                        limit: int = Query(50, ge=1, le=100), db: AsyncSession = Depends(get_db),
                        actor=Depends(require_permission(Permission.FINDING_READ))):
    query = select(Finding)
    if status:
        query = query.where(Finding.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Finding.id.desc()).offset(offset).limit(limit))).scalars().all()
    return {"items": [serialize(r) for r in rows], "total": total}


@router.get("/assignees")
async def assignees(db: AsyncSession = Depends(get_db),
                    actor=Depends(require_permission(Permission.FINDING_MANAGE))):
    rows = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    return [{"id": r.id, "username": r.username} for r in rows
            if has_permission(Role(r.role), Permission.FINDING_MANAGE)]


@router.post("", status_code=201)
async def submit(body: FindingCreate, db: AsyncSession = Depends(get_db),
                 actor=Depends(require_permission(Permission.FINDING_SUBMIT))):
    return serialize(await create_finding(db, body, actor))


async def load_detail(db, finding_id):
    row = await db.get(Finding, finding_id)
    if row is None:
        raise HTTPException(404, "Finding not found")
    events = (await db.execute(select(FindingEvent).where(FindingEvent.finding_id == finding_id)
                              .order_by(FindingEvent.id))).scalars().all()
    return row, events


@router.get("/{finding_id}")
async def detail(finding_id: int, db: AsyncSession = Depends(get_db),
                 actor=Depends(require_permission(Permission.FINDING_READ))):
    row, events = await load_detail(db, finding_id)
    return {**serialize(row), "events": [serialize(e) for e in events]}


@router.post("/{finding_id}/actions")
async def change(finding_id: int, body: FindingChange, db: AsyncSession = Depends(get_db),
                 actor=Depends(require_permission(Permission.FINDING_READ))):
    return serialize(await change_finding(db, finding_id, body, actor))


@router.get("/{finding_id}/report")
async def report(finding_id: int, db: AsyncSession = Depends(get_db),
                 actor=Depends(require_permission(Permission.FINDING_READ))):
    row, events = await load_detail(db, finding_id)
    return Response(report_markdown(row, events), media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="finding-{row.id}.md"'})
