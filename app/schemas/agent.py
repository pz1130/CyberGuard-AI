"""Pydantic schemas for agent management."""
import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


def _validate_endpoint_url(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not isinstance(v, str):
        raise ValueError("endpoint_url must be a string")
    if not v.startswith(("http://", "https://")):
        raise ValueError("endpoint_url must start with http:// or https://")
    if re.search(r"[;&|`$<>]", v):
        raise ValueError("endpoint_url contains disallowed characters")
    return v


class AgentConfigBase(BaseModel):
    """Shared fields for agent create/update."""
    agent_name: str = Field(..., min_length=1, max_length=100)
    backend_type: str = Field(
        default="openclaw",
        description="openclaw | hermes | custom",
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

    _url_validator = field_validator("endpoint_url", mode="before")(_validate_endpoint_url)


class AgentConfigCreate(AgentConfigBase):
    """Create a new agent.

    OpenClaw (Clawith) 必填字段:
      - endpoint_url:        Clawith 部署地址，如 http://clawith:18789
      - openclaw_agent_id:   Clawith 里该 Agent 的 UUID
      - api_key:             Clawith API Key（加密存储）
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


class AgentConfigUpdate(BaseModel):
    """Partial update — all fields optional."""
    agent_name: Optional[str] = None
    backend_type: Optional[str] = None
    provider_id: Optional[str] = None
    endpoint_url: Optional[str] = Field(default=None)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None
    permission_level: Optional[str] = None
    associated_skills: Optional[List[int]] = None
    # OpenClaw fields
    openclaw_agent_id: Optional[str] = None
    api_key: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None
    metadata_json: Optional[Dict[str, Any]] = None

    _url_validator = field_validator("endpoint_url", mode="before")(_validate_endpoint_url)


class AgentConfigRead(BaseModel):
    """Agent config returned by the API.

    api_key is never returned — only a masked placeholder if one is set.
    openclaw_agent_id is surfaced from metadata_json for display.
    """
    id: int
    agent_name: str
    backend_type: str
    provider_id: Optional[str]
    endpoint_url: Optional[str]
    description: Optional[str]
    system_prompt: Optional[str]
    is_active: bool
    permission_level: str
    associated_skills: Optional[List[int]]
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    @property
    def openclaw_agent_id(self) -> Optional[str]:
        return (self.metadata_json or {}).get("openclaw_agent_id")

    @property
    def has_api_key(self) -> bool:
        return bool((self.metadata_json or {}).get("api_key_encrypted"))

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True
