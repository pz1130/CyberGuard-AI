"""Agent configuration and management router."""
import hashlib
import json
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.security import encrypt_data, decrypt_data
from app.schemas.agent import (
    AgentConfigCreate, AgentConfigRead, AgentConfigUpdate,
    AgentConfigListResponse, AgentTestResponse,
)
from app.models.agent import AgentConfig

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_api_key() -> tuple[str, str]:
    """生成 OpenClaw API Key。返回 (plaintext, sha256_hash)。"""
    raw = f"oc-{secrets.token_urlsafe(32)}"
    h = hashlib.sha256(raw.encode()).hexdigest()
    return raw, h


def _build_metadata(fields: dict, existing: dict | None = None) -> dict:
    """把 OpenClaw 专属字段合并到 metadata_json。"""
    meta = dict(existing or {})
    # api_key → 加密后存入 metadata_json
    if "api_key" in fields:
        raw = fields.pop("api_key") or ""
        if raw and raw != "******":
            meta["api_key_encrypted"] = encrypt_data(raw)
    return meta


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/agents", response_model=AgentConfigListResponse)
async def list_agents(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    total = (await db.execute(select(func.count(AgentConfig.id)))).scalar()
    rows = (await db.execute(select(AgentConfig).offset(skip).limit(limit))).scalars().all()
    return AgentConfigListResponse(
        total=total,
        agents=[AgentConfigRead.model_validate(a) for a in rows],
    )


@router.post("/agents", response_model=AgentConfigRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """创建 Sub-Agent。

    **OpenClaw 模式**（backend_type="openclaw"）：
    - 系统自动生成 `oc-xxx` API Key，**只在此响应中返回一次**。
    - 把返回的 `api_key` 配置到 OpenClaw 节点的 X-Api-Key 头。
    - `endpoint_url` 留空（OpenClaw 主动来轮询，无需 CyberGuard 主动调用）。

    **其他模式**（hermes / custom）：
    - 填写 `endpoint_url`，CyberGuard 会主动 POST 到该地址。
    """
    existing = await db.execute(select(AgentConfig).where(AgentConfig.agent_name == body.agent_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Agent name already exists")

    body_dict = body.model_dump()
    env_vars = body_dict.pop("env_vars", None)
    metadata = _build_metadata(body_dict, existing=body_dict.pop("metadata_json", None) or {})

    agent = AgentConfig(
        **{k: v for k, v in body_dict.items() if hasattr(AgentConfig, k)},
        metadata_json=metadata or None,
        env_vars_encrypted=encrypt_data(json.dumps(env_vars)) if env_vars else None,
    )

    # OpenClaw 模式：生成 Gateway API Key
    plaintext_key: str | None = None
    if body.backend_type == "openclaw":
        plaintext_key, agent.api_key_hash = _generate_api_key()

    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    resp = AgentConfigRead.model_validate(agent)
    # 只在创建时返回明文 key
    if plaintext_key:
        resp = resp.model_copy(update={"api_key": plaintext_key})
    return resp


@router.get("/agents/{agent_id}", response_model=AgentConfigRead)
async def get_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentConfigRead.model_validate(agent)


@router.put("/agents/{agent_id}", response_model=AgentConfigRead)
async def update_agent(
    agent_id: int,
    body: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    body_dict = body.model_dump(exclude_unset=True)

    if "env_vars" in body_dict:
        ev = body_dict.pop("env_vars")
        agent.env_vars_encrypted = encrypt_data(json.dumps(ev)) if ev else None

    if "api_key" in body_dict:
        meta = dict(agent.metadata_json or {})
        raw = body_dict.pop("api_key") or ""
        if raw and raw != "******":
            meta["api_key_encrypted"] = encrypt_data(raw)
        agent.metadata_json = meta

    if "metadata_json" in body_dict:
        existing = dict(agent.metadata_json or {})
        existing.update(body_dict.pop("metadata_json") or {})
        agent.metadata_json = existing

    for key, value in body_dict.items():
        if hasattr(agent, key):
            setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
    return AgentConfigRead.model_validate(agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()


# ---------------------------------------------------------------------------
# API Key 轮换
# ---------------------------------------------------------------------------

@router.post("/agents/{agent_id}/api-key")
async def regenerate_api_key(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """重新生成 OpenClaw Gateway API Key。

    旧 Key 立即失效，新 Key 只返回一次，请立即更新 OpenClaw 节点配置。
    """
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.backend_type != "openclaw":
        raise HTTPException(status_code=400, detail="Only openclaw agents have a Gateway API Key")

    plaintext, agent.api_key_hash = _generate_api_key()
    await db.commit()

    return {"api_key": plaintext, "note": "此 Key 只显示一次，请立即保存并更新 OpenClaw 节点配置。"}


# ---------------------------------------------------------------------------
# 连通性测试
# ---------------------------------------------------------------------------

@router.post("/agents/{agent_id}/test", response_model=AgentTestResponse)
async def test_agent_connection(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """测试 Sub-Agent 连通性。

    - OpenClaw 模式：检查节点最近一次 poll/heartbeat 时间，判断是否在线。
    - 其他模式：向 endpoint_url/health 发 GET 请求。
    """
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.backend_type == "openclaw":
        if not agent.api_key_hash:
            return AgentTestResponse(success=False, error="尚未生成 API Key，无法判断在线状态")
        last_seen = agent.openclaw_last_seen
        if last_seen is None:
            return AgentTestResponse(success=False, error="OpenClaw 节点从未上线（尚未首次 poll）")
        delta = (datetime.utcnow() - last_seen).total_seconds()
        if delta < 300:   # 5 分钟内 poll 过 = 在线
            return AgentTestResponse(success=True, latency_ms=None,
                                     error=f"在线（最近活跃：{int(delta)} 秒前）")
        return AgentTestResponse(success=False,
                                 error=f"离线（最近活跃：{int(delta)} 秒前，超过 5 分钟）")

    # 其他后端：HTTP ping
    endpoint = agent.endpoint_url or ""
    if not endpoint:
        return AgentTestResponse(success=False, error="未配置 endpoint_url")

    import httpx, time
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{endpoint.rstrip('/')}/health")
        latency = round((time.monotonic() - t0) * 1000, 1)
        return AgentTestResponse(success=resp.status_code == 200,
                                 latency_ms=latency,
                                 status_code=resp.status_code)
    except Exception as e:
        return AgentTestResponse(success=False, error=str(e))


# ---------------------------------------------------------------------------
# 手动触发
# ---------------------------------------------------------------------------

@router.post("/agents/{agent_id}/execute")
async def execute_agent(
    agent_id: int,
    body: dict,
    _=Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """手动向指定 Sub-Agent 派发一个任务。"""
    from app.services.agent_executor import AgentExecutor
    task = body.get("task", "")
    if not task:
        raise HTTPException(status_code=400, detail="'task' 字段不能为空")
    return await AgentExecutor().execute(agent_id=agent_id, task=task, user_id=0)
