"""Agent-only submission adapter. No review or mutation tool is exposed."""
import json
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.database import AsyncSessionLocal
from app.core.rbac import Role, Permission, has_permission
from app.core.auth import AuthenticatedUser
from app.models.user import User
from app.schemas.finding import FindingCreate
from app.services.findings import create_finding


async def submission_tool(user_id):
    if not user_id:
        return None
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user or not user.is_active or not has_permission(Role(user.role), Permission.FINDING_SUBMIT):
            return None
    return {"type": "function", "function": {
        "name": "finding_submit",
        "description": "Save a security finding with original evidence for human review. "
                       "Submission does not confirm the finding. Do not invent evidence. "
                       "Do not resubmit a finding that was already saved in this conversation.",
        "parameters": FindingCreate.model_json_schema(),
    }}


async def submit_from_agent(user_id, agent_id, arguments):
    try:
        body = FindingCreate.model_validate(arguments)
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id) if user_id else None
            if not user or not user.is_active:
                raise HTTPException(403, "Active user required")
            actor = AuthenticatedUser(user_id=user.id, username=user.username, email=user.email, role=user.role)
            row = await create_finding(db, body, actor, agent_id=agent_id)
            return json.dumps({"id": row.id, "status": row.status, "requires_human_review": True})
    except (HTTPException, ValidationError) as exc:
        return json.dumps({"status": "error", "error": str(exc)})
