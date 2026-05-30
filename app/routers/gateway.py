"""OpenClaw Gateway — poll / report / heartbeat / send-message endpoints.

OpenClaw 节点用这四个接口与 CyberGuard 通信：

  GET  /api/v1/gateway/poll         — 取待处理任务
  POST /api/v1/gateway/report       — 回报执行结果
  POST /api/v1/gateway/heartbeat    — 保持在线状态
  POST /api/v1/gateway/send-message — 主动向 CyberGuard 发送消息

所有请求用 X-Api-Key 头携带创建 Agent 时返回的 oc-xxx 密钥。
"""
import hashlib
import json
import json as _json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.agent import AgentConfig
from app.models.gateway_message import GatewayMessage
from app.models.mcp import MCPTool
from app.models.skill import Skill, Tool
from app.schemas.gateway import (
    ManifestMCPTool,
    ManifestResponse,
    ManifestSkill,
    ManifestTool,
)

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

class SendMessageRequest(BaseModel):
    content: str
    target: Optional[str] = None  # 预留：指定目标用户或 Agent 名称

class SendMessageResponse(BaseModel):
    success: bool
    message_id: int


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

    has_manifest = bool(
        agent.associated_skills or agent.associated_tools or agent.associated_mcp_tools
    )

    return PollResponse(
        messages=[
            {
                "id": m.id,
                "content": m.content,
                "execution_id": m.execution_id,
                "conversation_id": m.execution_id,  # alias for AI agent compatibility
                "sender_user_name": "CyberGuard",
                "sender_user_id": 0,
                "created_at": m.created_at.isoformat(),
                "has_manifest": has_manifest,
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


@router.post("/gateway/send-message", response_model=SendMessageResponse)
async def send_message(
    body: SendMessageRequest,
    x_api_key: str = Header(..., alias="X-Api-Key"),
):
    """OpenClaw 节点主动向 CyberGuard 发送消息（存入 gateway_messages 供 UI 查看）。"""
    agent = await _auth_agent(x_api_key)

    async with AsyncSessionLocal() as session:
        msg = GatewayMessage(
            agent_id=agent.id,
            content=f"[来自 Agent] {body.content}",
            status="completed",          # 主动发送的消息无需等待执行
            result=body.content,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        session.add(msg)

        # 更新在线时间
        agent_row = await session.get(AgentConfig, agent.id)
        if agent_row:
            agent_row.openclaw_last_seen = datetime.utcnow()

        await session.commit()
        await session.refresh(msg)

    # 尝试通过 Redis 通知 UI（best-effort）
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        await r.publish(
            f"gateway:incoming:{agent.id}",
            json.dumps({"agent_id": agent.id, "content": body.content, "target": body.target}),
        )
    except Exception:
        pass

    return SendMessageResponse(success=True, message_id=msg.id)


@router.get("/gateway/manifest", response_model=ManifestResponse)
async def manifest(x_api_key: str = Header(..., alias="X-Api-Key")):
    """Return the full manifest of skills/tools/mcp-tools assigned to this agent.

    The calling agent authenticates with the same X-Api-Key used for poll/report.
    An empty assignment list returns [] — the endpoint never falls back to the
    whole pool.
    """
    agent = await _auth_agent(x_api_key)

    skill_ids: list = agent.associated_skills or []
    tool_ids: list = agent.associated_tools or []
    mcp_ids: list = agent.associated_mcp_tools or []

    async with AsyncSessionLocal() as session:
        # Always execute all three queries to keep a predictable call order.
        # When the id list is empty, the IN-clause returns no rows.
        rows = (await session.execute(
            select(Skill).where(
                Skill.is_active == True,
                Skill.id.in_(skill_ids) if skill_ids else Skill.id.is_(None),
            )
        )).scalars().all()
        skills = [
            ManifestSkill(id=s.id, name=s.name, description=s.description, md_content=s.md_content)
            for s in rows
        ]

        trows = (await session.execute(
            select(Tool).where(
                Tool.is_active == True,
                Tool.id.in_(tool_ids) if tool_ids else Tool.id.is_(None),
            )
        )).scalars().all()
        tools = []
        for t in trows:
            try:
                schema = _json.loads(t.input_schema_json) if t.input_schema_json else {}
            except Exception:
                schema = {}
            tools.append(ManifestTool(
                id=t.id, name=t.name, description=t.description,
                command_template=t.command_template, input_schema=schema,
            ))

        mrows = (await session.execute(
            select(MCPTool).where(
                MCPTool.is_active == True,
                MCPTool.id.in_(mcp_ids) if mcp_ids else MCPTool.id.is_(None),
            )
        )).scalars().all()
        mcp_tools = []
        for m in mrows:
            try:
                schema = _json.loads(m.input_schema_json) if m.input_schema_json else {}
            except Exception:
                schema = {}
            mcp_tools.append(ManifestMCPTool(
                id=m.id, name=m.tool_name, description=m.description, input_schema=schema,
            ))

    return ManifestResponse(
        agent_id=agent.id,
        agent_name=agent.agent_name,
        skills=skills,
        tools=tools,
        mcp_tools=mcp_tools,
    )
