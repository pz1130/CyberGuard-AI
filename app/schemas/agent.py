"""Pydantic schemas for agent management."""
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _validate_endpoint_url(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not isinstance(v, str):
        raise ValueError("endpoint_url must be a string")
    from app.core.ssrf import validate_outbound_url, SSRFError
    try:
        validate_outbound_url(v)
    except SSRFError as e:
        raise ValueError(str(e))
    return v


class AgentConfigBase(BaseModel):
    """Shared fields for agent create/update."""
    agent_name: str = Field(..., min_length=1, max_length=100)
    backend_type: str = Field(
        default="openclaw",
        description="openclaw | hermes | custom",
    )
    kind: str = Field(
        default="external",
        description="external | internal",
    )
    provider_id: Optional[str] = None
    endpoint_url: Optional[str] = Field(
        default=None,
        description="Clawith base URL, e.g. http://clawith:18789",
    )
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    is_active: bool = True
    permission_level: str = Field(
        default="medium",
        description="low | medium | high",
    )
    associated_skills: Optional[List[int]] = None
    associated_tools: Optional[List[int]] = None
    associated_mcp_tools: Optional[List[int]] = None
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None
    tool_loop_max_steps: int = 8
    memory_window: int = 20
    knowledge_base_id: Optional[int] = None

    _url_validator = field_validator("endpoint_url", mode="before")(_validate_endpoint_url)
    _kind_validator = field_validator("kind", mode="before")(lambda v: (v or "external").lower())


class AgentConfigCreate(AgentConfigBase):
    """Create a new agent.

    OpenClaw (Clawith) 必填字段:
      - endpoint_url:        Clawith 部署地址，如 http://clawith:18789
      - openclaw_agent_id:   Clawith 里该 Agent 的 UUID
      - api_key:             Clawith API Key（加密存储）

    Internal agents require llm_provider_id and must not set endpoint_url.
    """
    # OpenClaw / Clawith 接入字段
    openclaw_agent_id: Optional[str] = Field(
        default=None,
        description="Clawith Agent UUID（对应 x-openclaw-agent-id 请求头）",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Clawith API Key（AES-256 加密后存入 DB）",
    )
    # 任意额外配置
    env_vars: Optional[Dict[str, str]] = Field(
        default=None,
        description="注入到 agent 的环境变量（加密存储）",
    )
    metadata_json: Optional[Dict[str, Any]] = None

    model_config = {"extra": "forbid"}


class AgentConfigUpdate(BaseModel):
    """Partial update — all fields optional."""
    agent_name: Optional[str] = None
    backend_type: Optional[str] = None
    kind: Optional[str] = None
    provider_id: Optional[str] = None
    endpoint_url: Optional[str] = Field(default=None)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None
    permission_level: Optional[str] = None
    associated_skills: Optional[List[int]] = None
    associated_tools: Optional[List[int]] = None
    associated_mcp_tools: Optional[List[int]] = None
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None
    tool_loop_max_steps: Optional[int] = None
    memory_window: Optional[int] = None
    knowledge_base_id: Optional[int] = None
    # OpenClaw fields
    openclaw_agent_id: Optional[str] = None
    api_key: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None
    metadata_json: Optional[Dict[str, Any]] = None

    _url_validator = field_validator("endpoint_url", mode="before")(_validate_endpoint_url)
    _kind_validator = field_validator("kind", mode="before")(lambda v: v or None)

    model_config = {"extra": "forbid"}


class AgentConfigRead(BaseModel):
    """Agent config returned by the API.

    `api_key` 只在创建时一次性返回，其余时候为 None。
    `has_api_key` 表示 DB 里是否已存有 Key（不暴露明文）。
    `is_online` 仅 openclaw 后端有意义：最近 5 分钟内有 poll/heartbeat 即视为在线。
    """
    id: int
    agent_name: str
    kind: str
    backend_type: str
    provider_id: Optional[str]
    endpoint_url: Optional[str]
    description: Optional[str]
    system_prompt: Optional[str]
    is_active: bool
    permission_level: str
    associated_skills: Optional[List[int]]
    associated_tools: Optional[List[int]] = None
    associated_mcp_tools: Optional[List[int]] = None
    metadata_json: Optional[Dict[str, Any]]
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None
    tool_loop_max_steps: int = 8
    memory_window: int = 20
    knowledge_base_id: Optional[int] = None
    openclaw_last_seen: Optional[datetime] = None
    has_api_key: bool = False
    is_online: bool = False
    api_key: Optional[str] = None   # 仅创建时填充，其余 None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def model_validate(cls, obj, **kwargs):
        inst = super().model_validate(obj, **kwargs)
        inst.has_api_key = bool(getattr(obj, "api_key_hash", None))
        last_seen = getattr(obj, "openclaw_last_seen", None)
        inst.openclaw_last_seen = last_seen
        if last_seen:
            from datetime import timezone
            # DB stores naive UTC; make it aware so the subtraction works
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            delta = (datetime.now(timezone.utc) - last_seen).total_seconds()
            inst.is_online = delta < 300
        return inst

    model_config = ConfigDict(from_attributes=True)


class AgentConfigListResponse(BaseModel):
    total: int
    agents: List[AgentConfigRead]


class AgentTestResponse(BaseModel):
    """Result of a connectivity test."""
    success: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


# ---------------------------------------------------------------------------
# Execution schemas (unchanged)
# ---------------------------------------------------------------------------

class AgentExecutionRead(BaseModel):
    id: int
    execution_id: str
    agent_id: Optional[int]
    status: str
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
