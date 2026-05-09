"""OpenClaw Gateway — poll / report / heartbeat endpoints.

OpenClaw 节点用这三个接口与 CyberGuard 通信：

  GET  /api/v1/gateway/poll       — 取待处理任务
  POST /api/v1/gateway/report     — 回报执行结果
  POST /api/v1/gateway/heartbeat  — 保持在线状态

所有请求用 X-Api-Key 头携带创建 Agent 时返回的 oc-xxx 密钥。
"""
import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_context, AsyncSessionLocal
from app.models.agent import AgentConfig
from app.models.gateway_message import GatewayMessage

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _auth_agent(x_api_key: str) -> AgentConfig:
    """Verify X-Api-Key and return the matching AgentConfig."""
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Api-Key header required")

    key_hash = _hash_key(x_api_key)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AgentConfig).where(
                AgentConfig.api_key_hash == key_hash,
                AgentConfig.is_active == True,
            )
        )
        agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return agent


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PollResponse(BaseModel):
    messages: list[dict]

class ReportRequest(BaseModel):
    message_id: int
    result: str

class ReportResponse(BaseModel):
    success: bool
    message_id: int

class HeartbeatResponse(BaseModel):
    success: bool
    timestamp: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/gateway/poll", response_model=PollResponse)
async def poll(x_api_key: str = Header(..., alias="X-Api-Key")):
    """OpenClaw 节点轮询待处理任务。

    返回所有 status=pending 的任务，并将其标记为 delivered。
    同时更新 openclaw_last_seen 维持在线状态。
    """
    agent = await _auth_agent(x_api_key)

    async with AsyncSessionLocal() as session:
        # 取 pending 任务
        result = await session.execute(
            select(GatewayMessage).where(
                GatewayMessage.agent_id == agent.id,
                GatewayMessage.status == "pending",
            ).order_by(GatewayMessage.created_at)
        )
        messages = list(result.scalars().all())

        now = datetime.utcnow()
        for msg in messages:
            msg.status = "delivered"
            msg.delivered_at = now

        # 更新在线时间
        agent_result = await session.execute(
            select(AgentConfig).where(AgentConfig.id == agent.id)
        )
        agent_row = agent_result.scalar_one_or_none()
        if agent_row:
            agent_row.openclaw_last_seen = now

        await session.commit()

    return PollResponse(
        messages=[
            {
                "id": m.id,
                "content": m.content,
                "execution_id": m.execution_id,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    )


@router.post("/gateway/report", response_model=ReportResponse)
async def report(
    body: ReportRequest,
    x_api_key: str = Header(..., alias="X-Api-Key"),
):
    """OpenClaw 节点回报任务执行结果。

    将对应 GatewayMessage 标记为 completed，写入 result。
    同时通过 Redis pub/sub 通知等待中的 AgentExecutor。
    """
    agent = await _auth_agent(x_api_key)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GatewayMessage).where(
                GatewayMessage.id == body.message_id,
                GatewayMessage.agent_id == agent.id,
            )
        )
        msg = result.scalar_one_or_none()

        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        if msg.status == "completed":
            raise HTTPException(status_code=409, detail="Message already completed")

        msg.status = "completed"
        msg.result = body.result
        msg.completed_at = datetime.utcnow()
        await session.commit()

    # 通知等待中的 AgentExecutor（best-effort）
    if msg.execution_id:
        try:
            from app.core.redis_client import get_redis
            r = await get_redis()
            await r.publish(
                f"gateway:result:{msg.execution_id}",
                json.dumps({"message_id": msg.id, "result": body.result}),
            )
        except Exception:
            pass  # 即使 Redis 失败，结果也已写入 DB

    return ReportResponse(success=True, message_id=body.message_id)


@router.post("/gateway/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(x_api_key: str = Header(..., alias="X-Api-Key")):
    """OpenClaw 节点心跳，维持在线状态。"""
    agent = await _auth_agent(x_api_key)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.id == agent.id)
        )
        agent_row = result.scalar_one_or_none()
        if agent_row:
            agent_row.openclaw_last_seen = datetime.utcnow()
            await session.commit()

    return HeartbeatResponse(success=True, timestamp=datetime.utcnow().isoformat())
