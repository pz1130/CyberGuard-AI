"""Agent configuration and management router."""
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.dependencies import get_db, require_permission
from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.core.rbac import Permission
from app.core.security import CredentialField, encrypt_data, decrypt_data
from app.schemas.agent import (
    AgentConfigCreate, AgentConfigRead, AgentConfigUpdate,
    AgentConfigListResponse, AgentTestResponse,
)
from app.models.agent import AgentConfig
from app.models.provider import Provider

router = APIRouter()


# ---------------------------------------------------------------------------
# Startup seed
# ---------------------------------------------------------------------------

SEED_FLAG = "SEED_EXAMPLE_INTERNAL_AGENTS"


async def seed_example_internal_agents() -> None:
    """Idempotent — runs on startup only when SEED_EXAMPLE_INTERNAL_AGENTS=true."""
    if os.getenv(SEED_FLAG, "false").lower() != "true":
        return

    async with AsyncSessionLocal() as s:
        existing = await s.execute(select(AgentConfig).where(
            AgentConfig.agent_name.in_(["triage_analyst", "policy_writer"])
        ))
        already = {r.agent_name for r in existing.scalars().all()}
        if len(already) >= 2:
            return

        providers = await s.execute(select(AgentConfig).where(
            AgentConfig.kind == "internal"
        ))
        # Find a provider id to use — try first internal agent's provider or skip
        provider_id = None
        for ag in providers.scalars().all():
            if ag.llm_provider_id:
                provider_id = ag.llm_provider_id
                break

        to_create = []
        if "triage_analyst" not in already:
            to_create.append(AgentConfig(
                agent_name="triage_analyst",
                kind="internal",
                backend_type="openclaw",
                system_prompt="You are a SOC triage analyst. Use available tools to gather threat intelligence, enrich alerts with CVE data, and produce concise incident summaries.",
                permission_level="medium",
                llm_provider_id=provider_id,
                tool_loop_max_steps=8,
                memory_window=20,
            ))
        if "policy_writer" not in already:
            to_create.append(AgentConfig(
                agent_name="policy_writer",
                kind="internal",
                backend_type="openclaw",
                system_prompt="You are a security policy writer. Help draft and review security policies, map controls to frameworks (ISO 27001, NIST), and ensure policies are actionable and measurable.",
                permission_level="low",
                llm_provider_id=provider_id,
                tool_loop_max_steps=8,
                memory_window=20,
            ))
        for ag in to_create:
            s.add(ag)
        await s.commit()
        for ag in to_create:
            await s.refresh(ag)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_api_key() -> tuple[str, str]:
    """生成 OpenClaw API Key。返回 (plaintext, sha256_hash)。"""
    raw = f"oc-{secrets.token_urlsafe(32)}"
    h = hashlib.sha256(raw.encode()).hexdigest()
    return raw, h


def _build_metadata(fields: dict, existing: Optional[dict] = None) -> dict:
    """把 OpenClaw 专属字段合并到 metadata_json。"""
    meta = dict(existing or {})
    # api_key → 加密后存入 metadata_json
    if "api_key" in fields:
        raw = fields.pop("api_key") or ""
        if raw and raw != "******":
            meta["api_key_encrypted"] = encrypt_data(raw, CredentialField.AGENT_META_API_KEY)
    return meta


# ---------------------------------------------------------------------------
# Kind-aware validation
# ---------------------------------------------------------------------------

def _validate_agent_payload(body, existing: Optional[AgentConfig] = None) -> None:
    """Enforce kind-specific constraints before persisting.

    For updates (existing provided), merge unset Optional fields from the
    existing row so partial payloads don't fail validation.
    """
    # Merge: use body value if set, else fall back to existing row
    kind = getattr(body, "kind", None)
    if kind is None and existing:
        kind = existing.kind
    kind = (kind or "external").lower()

    backend_type = getattr(body, "backend_type", None)
    if backend_type is None and existing:
        backend_type = existing.backend_type

    endpoint_url = getattr(body, "endpoint_url", None)
    if endpoint_url is None and existing:
        endpoint_url = existing.endpoint_url

    llm_provider_id = getattr(body, "llm_provider_id", None)
    if llm_provider_id is None and existing:
        llm_provider_id = existing.llm_provider_id

    if kind not in ("external", "internal"):
        raise HTTPException(status_code=400, detail=f"invalid kind: {kind!r}")
    if kind == "external":
        if not backend_type:
            raise HTTPException(status_code=400, detail="external agent requires backend_type")
        if backend_type in ("hermes", "custom") and not endpoint_url:
            raise HTTPException(status_code=400, detail=f"{backend_type} requires endpoint_url")
    else:  # internal
        if not llm_provider_id:
            raise HTTPException(status_code=400, detail="internal agent requires llm_provider_id")
        if endpoint_url:
            raise HTTPException(status_code=400, detail="internal agent must not set endpoint_url")
        if backend_type and backend_type != "openclaw":
            raise HTTPException(status_code=400, detail="internal agent must not set backend_type")


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

    所有 backend 创建时均自动生成 `oc-xxx` Gateway API Key，**只在此响应中返回一次**。
    外部节点用此 key 调用 /gateway/poll、/gateway/manifest 等接口。

    **OpenClaw 模式**（backend_type="openclaw"）：
    - `endpoint_url` 留空（OpenClaw 主动来轮询）。

    **其他模式**（hermes / custom）：
    - 填写 `endpoint_url`，CyberGuard 会主动 POST 到该地址。

    **内部 Agent**（kind="internal"）：
    - 配置 LLM Provider，系统通过 Tool-Call 循环执行。
    """
    _validate_agent_payload(body)
    existing = await db.execute(select(AgentConfig).where(AgentConfig.agent_name == body.agent_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Agent name already exists")

    body_dict = body.model_dump()
    env_vars = body_dict.pop("env_vars", None)
    metadata = _build_metadata(body_dict, existing=body_dict.pop("metadata_json", None) or {})

    agent = AgentConfig(
        **{k: v for k, v in body_dict.items() if hasattr(AgentConfig, k)},
        metadata_json=metadata or None,
        env_vars_encrypted=encrypt_data(json.dumps(env_vars), CredentialField.AGENT_ENV_VARS) if env_vars else None,
    )

    # 所有 backend 生成 Gateway API Key（外部节点用此 key 调 /gateway/manifest 等接口）
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

    _validate_agent_payload(body, existing=agent)

    body_dict = body.model_dump(exclude_unset=True)

    if "env_vars" in body_dict:
        ev = body_dict.pop("env_vars")
        agent.env_vars_encrypted = encrypt_data(json.dumps(ev), CredentialField.AGENT_ENV_VARS) if ev else None

    if "api_key" in body_dict:
        meta = dict(agent.metadata_json or {})
        raw = body_dict.pop("api_key") or ""
        if raw and raw != "******":
            meta["api_key_encrypted"] = encrypt_data(raw, CredentialField.AGENT_META_API_KEY)
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
    """重新生成 Gateway API Key。

    旧 Key 立即失效，新 Key 只返回一次。
    """
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    plaintext, agent.api_key_hash = _generate_api_key()
    await db.commit()

    return {"api_key": plaintext, "note": "此 Key 只显示一次，请立即保存并更新节点配置。"}


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

    - 内部模式：在系统进程内运行，无网络连通性可测；校验所配置的 LLM Provider。
    - OpenClaw 模式：检查节点最近一次 poll/heartbeat 时间，判断是否在线。
    - 其他模式：向 endpoint_url/health 发 GET 请求。
    """
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.kind == "internal":
        # 内部 Agent 在系统进程内运行，没有外部连通性概念（offline/poll）。
        # 唯一会"断"的是其 LLM Provider，所以校验它即可。
        if not agent.llm_provider_id:
            return AgentTestResponse(success=False, error="内部 Agent 未配置 LLM Provider")
        prov = await db.execute(select(Provider).where(Provider.id == agent.llm_provider_id))
        p = prov.scalar_one_or_none()
        if p is None:
            return AgentTestResponse(success=False, error="所配置的 LLM Provider 不存在")
        if not p.is_active:
            return AgentTestResponse(success=False, error=f"LLM Provider「{p.name}」已禁用")
        return AgentTestResponse(success=True, error=f"就绪 · 进程内运行（LLM Provider：{p.name}）")

    if agent.backend_type == "openclaw":
        if not agent.api_key_hash:
            return AgentTestResponse(success=False, error="尚未生成 API Key，无法判断在线状态")
        last_seen = agent.openclaw_last_seen
        if last_seen is None:
            return AgentTestResponse(success=False, error="OpenClaw 节点从未上线（尚未首次 poll）")
        delta = (datetime.now(timezone.utc) - last_seen).total_seconds()
        if delta < 300:   # 5 分钟内 poll 过 = 在线
            return AgentTestResponse(success=True, latency_ms=None,
                                     error=f"在线（最近活跃：{int(delta)} 秒前）")
        return AgentTestResponse(success=False,
                                 error=f"离线（最近活跃：{int(delta)} 秒前，超过 5 分钟）")

    # 其他后端：HTTP ping
    endpoint = agent.endpoint_url or ""
    if not endpoint:
        return AgentTestResponse(success=False, error="未配置 endpoint_url")

    # SSRF protection — validate before making outbound request
    from app.core.ssrf import validate_outbound_url, SSRFError
    try:
        validate_outbound_url(endpoint)
    except SSRFError as e:
        return AgentTestResponse(success=False, error=f"SSRF blocked: {e}")

    import httpx, time
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
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
    current_user: AuthenticatedUser = Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """手动向指定 Sub-Agent 派发一个任务。"""
    from app.core.guardrails import check_prompt_sync
    from app.services.agent_executor import AgentExecutor
    task = body.get("task", "")
    if not task:
        raise HTTPException(status_code=400, detail="'task' 字段不能为空")

    # Guardrail check — same as /chat endpoint
    gr = check_prompt_sync(task)
    if gr.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input blocked: {gr.message} (risk={gr.risk_level})",
        )

    return await AgentExecutor().execute(
        agent_id=agent_id, task=task, user_id=current_user.user_id,
    )


@router.post("/agents/{agent_id}/execute/stream")
async def execute_agent_stream(
    agent_id: int,
    body: dict,
    current_user: AuthenticatedUser = Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """流式向指定 Sub-Agent 派发任务（SSE）。

    事件: start / tool_call_start / tool_call_end / text / done / error。
    internal agent 逐字流式; 其它 kind 以单个 done 事件返回批量结果。
    """
    import json as _json
    from fastapi.responses import StreamingResponse
    from app.core.guardrails import check_prompt_sync
    from app.services.agent_executor import AgentExecutor

    task = body.get("task", "")
    if not task:
        raise HTTPException(status_code=400, detail="'task' 字段不能为空")

    gr = check_prompt_sync(task)
    if gr.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input blocked: {gr.message} (risk={gr.risk_level})",
        )

    conversation_id = body.get("conversation_id")
    context = {"conversation_id": conversation_id} if conversation_id else None
    user_id = current_user.user_id

    async def event_generator():
        executor = AgentExecutor()
        try:
            async for ev in executor.execute_stream(
                agent_id=agent_id, task=task, user_id=user_id, context=context):
                yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
