"""Webhook CRUD + the public incoming endpoint."""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.security import encrypt_data
from app.models.webhook import Webhook
from app.models.agent import AgentExecution
from app.schemas.webhook import (
    WebhookCreate, WebhookUpdate, WebhookRead, WebhookListResponse,
    WebhookTestRequest, WebhookTestResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_token() -> tuple[str, str]:
    """Return (plaintext, sha256_hash). Plaintext is shown once."""
    raw = f"whk_{secrets.token_urlsafe(32)}"
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _base_url(request: Request) -> str:
    """Best-effort base URL for the running deployment, used in WebhookRead."""
    return str(request.base_url).rstrip("/")


def _attach_incoming_url(read: WebhookRead, wh: Webhook, base: str, plaintext: str | None = None):
    """Fill in incoming_url with either the freshly-issued token (on create /
    regenerate) or the `<TOKEN>` placeholder (lookup never recovers plaintext)."""
    if wh.direction != "incoming":
        return read
    if plaintext:
        read.incoming_url = f"{base}/api/v1/webhooks/incoming/{plaintext}"
        read.plaintext_token = plaintext
    else:
        read.incoming_url = f"{base}/api/v1/webhooks/incoming/<TOKEN>"
    return read


# ---------------------------------------------------------------------------
# CRUD (require settings:write)
# ---------------------------------------------------------------------------

@router.get("/webhooks", response_model=WebhookListResponse)
async def list_webhooks(
    skip: int = 0,
    limit: int = 100,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_READ)),
):
    total = (await db.execute(select(func.count(Webhook.id)))).scalar()
    rows = (await db.execute(select(Webhook).offset(skip).limit(limit))).scalars().all()
    base = _base_url(request) if request else ""
    return WebhookListResponse(
        total=total,
        webhooks=[_attach_incoming_url(WebhookRead.from_orm_with_url(r, base), r, base) for r in rows],
    )


@router.post("/webhooks", response_model=WebhookRead, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Create a webhook. For incoming webhooks the plaintext token is in the
    response **only this one time** — store it; the server keeps only a hash.
    """
    existing = await db.execute(select(Webhook).where(Webhook.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Webhook name already exists")

    if body.direction == "outgoing":
        if not body.outgoing_url:
            raise HTTPException(status_code=400, detail="outgoing_url is required for outgoing webhooks")
        if not body.outgoing_events:
            raise HTTPException(status_code=400, detail="outgoing_events must include at least one event")

    wh = Webhook(
        name=body.name,
        direction=body.direction,
        description=body.description,
        is_active=body.is_active,
    )

    plaintext_token: str | None = None
    if body.direction == "incoming":
        plaintext_token, wh.incoming_token_hash = _generate_token()
    else:
        wh.outgoing_url = body.outgoing_url
        wh.outgoing_events = body.outgoing_events
        if body.outgoing_secret:
            wh.outgoing_secret_encrypted = encrypt_data(body.outgoing_secret)

    db.add(wh)
    await db.commit()
    await db.refresh(wh)

    base = _base_url(request)
    read = WebhookRead.from_orm_with_url(wh, base)
    return _attach_incoming_url(read, wh, base, plaintext_token)


@router.get("/webhooks/{webhook_id}", response_model=WebhookRead)
async def get_webhook(
    webhook_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_READ)),
):
    wh = await db.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    base = _base_url(request)
    return _attach_incoming_url(WebhookRead.from_orm_with_url(wh, base), wh, base)


@router.put("/webhooks/{webhook_id}", response_model=WebhookRead)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    wh = await db.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    data = body.model_dump(exclude_unset=True)
    if "outgoing_secret" in data:
        secret = data.pop("outgoing_secret")
        if secret == "":
            wh.outgoing_secret_encrypted = None
        elif secret and secret != "******":
            wh.outgoing_secret_encrypted = encrypt_data(secret)

    for k, v in data.items():
        if hasattr(wh, k):
            setattr(wh, k, v)

    await db.commit()
    await db.refresh(wh)
    base = _base_url(request)
    return _attach_incoming_url(WebhookRead.from_orm_with_url(wh, base), wh, base)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    wh = await db.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(wh)
    await db.commit()


@router.post("/webhooks/{webhook_id}/regenerate-token", response_model=WebhookRead)
async def regenerate_token(
    webhook_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """Issue a new incoming token. Old token invalidated immediately."""
    wh = await db.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if wh.direction != "incoming":
        raise HTTPException(status_code=400, detail="Only incoming webhooks have tokens")

    plaintext, wh.incoming_token_hash = _generate_token()
    await db.commit()
    await db.refresh(wh)
    base = _base_url(request)
    read = WebhookRead.from_orm_with_url(wh, base)
    return _attach_incoming_url(read, wh, base, plaintext)


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: int,
    body: WebhookTestRequest = WebhookTestRequest(),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    """For an outgoing webhook: fire a synthetic event right now (no Celery
    queue) so the user gets a sync status/latency back."""
    wh = await db.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if wh.direction != "outgoing":
        raise HTTPException(status_code=400, detail="Test fire only supported for outgoing webhooks")

    from app.services.webhook_service import deliver_sync
    sample_payload = {
        "test": True,
        "message": "This is a synthetic event from CyberGuard webhook test.",
        "fired_at": datetime.now(timezone.utc).isoformat() + "Z",
    }
    result = deliver_sync(
        webhook_id=webhook_id,
        event=body.sample_event or "approval.required",
        payload=sample_payload,
    )
    return WebhookTestResponse(
        success=result["success"],
        status_code=result.get("status_code"),
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
    )


# ---------------------------------------------------------------------------
# Public incoming endpoint — no auth, token in URL.
# Rate-limited per IP. Dispatches the payload as a Master Agent user_input.
# ---------------------------------------------------------------------------

@router.post("/webhooks/incoming/{token}", status_code=status.HTTP_202_ACCEPTED)
async def incoming_webhook(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint hit by external services.

    URL: POST /api/v1/webhooks/incoming/<token>
    Body: JSON. Expected fields (all optional, but at least one of them):
      - `message`  : str — used directly as Master Agent user_input
      - `payload`  : any — wrapped as JSON inside user_input if no `message`
    Response: 202 + {task_id} so the caller can poll /tasks/{id}.
    """
    if not token or len(token) < 16:
        raise HTTPException(status_code=400, detail="Missing or malformed token")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result = await db.execute(select(Webhook).where(Webhook.incoming_token_hash == token_hash))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if not wh.is_active:
        raise HTTPException(status_code=403, detail="Webhook is disabled")
    if wh.direction != "incoming":
        raise HTTPException(status_code=400, detail="Not an incoming webhook")

    # Parse body. Be lenient — accept any JSON, or empty body.
    try:
        body: Dict[str, Any] = await request.json()
        if not isinstance(body, dict):
            body = {"payload": body}
    except Exception:
        body = {}

    message = body.get("message")
    if not message:
        # Fall back to JSON-stringify everything for the Master Agent.
        import json as _json
        message = (
            "External webhook trigger:\n"
            + _json.dumps(body, ensure_ascii=False, indent=2)
        )

    # Record trigger.
    wh.trigger_count = (wh.trigger_count or 0) + 1
    wh.last_triggered_at = datetime.now(timezone.utc)
    await db.commit()

    # Dispatch as Master Agent task. user_id=0 = system/external.
    execution_id = str(uuid.uuid4())
    execution = AgentExecution(
        execution_id=execution_id,
        agent_id=None,
        status="pending",
        input_data={
            "user_input": message,
            "source": "webhook",
            "webhook_id": wh.id,
            "webhook_name": wh.name,
        },
    )
    db.add(execution)
    await db.commit()

    from app.workers.tasks import run_master_agent_task
    run_master_agent_task.apply_async(
        args=[execution_id, message, 0],
        kwargs={"mode": "normal", "source": "webhook"},
    )

    return {
        "task_id": execution_id,
        "status": "pending",
        "webhook": wh.name,
        "message": "Task dispatched to Master Agent",
    }
