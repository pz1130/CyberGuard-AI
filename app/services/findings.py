"""Human-reviewed findings; state and signed audit event commit atomically."""
import re
import hashlib
import uuid
from fastapi import HTTPException
from sqlalchemy import select

from app.core.rbac import Permission, Role, has_permission
from app.core.time import utc_now
from app.models.finding import Finding, FindingEvent
from app.models.user import User

REVIEW_ACTIONS = {"confirm", "reject", "resolve", "reopen"}
TRANSITIONS = {
    "confirm": ({"pending"}, "confirmed"),
    "reject": ({"pending"}, "rejected"),
    "assign": ({"confirmed", "in_progress"}, "in_progress"),
    "ready": ({"in_progress"}, "ready_for_retest"),
    "resolve": ({"ready_for_retest"}, "resolved"),
    "reopen": ({"ready_for_retest", "resolved", "rejected"}, "confirmed"),
}


def require(actor, permission):
    if not has_permission(Role(actor.role), permission):
        raise HTTPException(403, "Permission denied")


def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


async def append_event(db, row, actor, action, note, evidence, *, agent_id=None):
    from app.core.audit import append_chained_audit

    request_id = str(uuid.uuid4())
    snapshot = {"status": row.status, "assignee_id": row.assignee_id, "version": row.version}
    digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
    event_data = dict(finding_id=row.id, actor_id=actor.user_id, action=action,
                      note=note, evidence=evidence, evidence_hash=digest, snapshot=snapshot)
    db.add(FindingEvent(**event_data, audit_request_id=request_id))
    # In the finding transaction: neither an unlogged state change nor a
    # phantom successful audit can commit.
    await append_chained_audit(
        db, user_id=actor.user_id, agent_id=agent_id, action=f"finding.{action}",
        action_category="annotate", request_id=request_id, input_data=event_data,
        output_data={k: str(v) for k, v in serialize(row).items()})


async def remediation_parties(db, row):
    """Everyone who has owned the fix or claimed it ready, not only the current owner.

    Otherwise an owner could reassign the finding away and then sign off their own fix.
    """
    events = (await db.execute(select(FindingEvent.action, FindingEvent.actor_id, FindingEvent.snapshot)
        .where(FindingEvent.finding_id == row.id))).all()
    parties = {row.assignee_id}
    for action, actor_id, snapshot in events:
        parties.add((snapshot or {}).get("assignee_id"))
        if action == "ready":
            parties.add(actor_id)
    parties.discard(None)
    return parties


async def create_finding(db, body, actor, *, agent_id=None):
    require(actor, Permission.FINDING_SUBMIT)
    row = Finding(**body.model_dump(exclude={"evidence"}), created_by=actor.user_id,
                  source="agent" if agent_id is not None else "human", agent_id=agent_id,
                  status="pending", version=1)
    db.add(row)
    await db.flush()
    await append_event(db, row, actor, "submit", row.description, body.evidence, agent_id=agent_id)
    await db.commit()
    return row


async def change_finding(db, finding_id, body, actor):
    permission = Permission.FINDING_REVIEW if body.action in REVIEW_ACTIONS else Permission.FINDING_MANAGE
    require(actor, permission)
    row = (await db.execute(select(Finding).where(Finding.id == finding_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Finding not found")
    if body.version != row.version:
        raise HTTPException(409, "Finding changed; reload before submitting")
    if body.action in REVIEW_ACTIONS and (
            actor.user_id == row.created_by or actor.user_id in await remediation_parties(db, row)):
        raise HTTPException(403, "The submitter or a remediation owner cannot review their own finding")
    if body.action == "evidence":
        if not body.evidence.strip():
            raise HTTPException(422, "Evidence is required")
    else:
        allowed, next_status = TRANSITIONS[body.action]
        if row.status not in allowed:
            raise HTTPException(409, "Action is not allowed in the current status")
        if body.action in {"resolve", "reopen"} and not body.evidence.strip():
            raise HTTPException(422, "Retest evidence is required")
        if body.action == "assign":
            assignee = await db.get(User, body.assignee_id) if body.assignee_id else None
            if not assignee or not assignee.is_active or not has_permission(Role(assignee.role), Permission.FINDING_MANAGE):
                raise HTTPException(422, "Choose an active remediation owner")
            row.assignee_id = assignee.id
        if body.action == "ready" and actor.user_id != row.assignee_id and actor.role != "admin":
            raise HTTPException(403, "Only the remediation owner can request a retest")
        row.status = next_status
    row.version += 1
    row.updated_at = utc_now()
    await append_event(db, row, actor, body.action, body.note, body.evidence)
    await db.commit()
    return row


def report_markdown(row, events):
    # Fence arbitrary data so evidence cannot inject active HTML or report sections.
    def block(value):
        text = str(value or "")
        fence = "`" * (max([len(run) for run in re.findall(r"`+", text)] or [2]) + 1)
        return f"{fence}text\n{text}\n{fence}\n"
    lines = [f"# Finding {row.id}\n", "## Summary\n"]
    for key in ("title", "target", "severity", "status", "source", "created_by", "assignee_id", "description", "remediation"):
        lines += [f"### {key}\n", block(getattr(row, key))]
    lines += ["## Evidence and review timeline\n"]
    for event in events:
        lines += [f"### Event {event.id}: {event.action}\n",
                  f"Actor: {event.actor_id} · UTC: {event.created_at.isoformat()}\n",
                  f"Audit reference: {event.audit_request_id}\n",
                  block(event.note), block(event.evidence), f"SHA-256: {event.evidence_hash}\n"]
    return "\n".join(lines)
