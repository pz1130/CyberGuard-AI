"""Pydantic schemas for agent management."""
import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


def _validate_endpoint_url(v: Optional[str]) -> Optional[str]:
    """Validate endpoint URL format and scheme at schema level."""
    if v is None:
        return v
    if not isinstance(v, str):
        raise ValueError("endpoint_url must be a string")
    if not v.startswith(("http://", "https://")):
        raise ValueError("endpoint_url must start with http:// or https://")
    # Basic hostname check — no suspicious schemes
    if re.search(r"[;&|`$<>]", v):
        raise ValueError("endpoint_url contains disallowed characters")
    return v


class AgentConfigBase(BaseModel):
    """Base agent configuration schema."""
    agent_name: str = Field(..., min_length=1, max_length=100)
    backend_type: str = Field(..., description="openclaw, hermes, custom")
    provider_id: Optional[str] = None
    endpoint_url: Optional[str] = Field(default=None)
    description: Optional[str] = None
    is_active: bool = True
    permission_level: str = "medium"
    associated_skills: Optional[List[int]] = None
    metadata_json: Optional[Dict[str, Any]] = None
    # OpenClaw-specific fields
    auth_mode: Optional[str] = Field(default="api_key", description="api_key, bearer, none")
    streaming: Optional[bool] = Field(default=True, description="Enable streaming")

    _url_validator = field_validator("endpoint_url", mode="before")(_validate_endpoint_url)


class AgentConfigCreate(AgentConfigBase):
    """Agent configuration creation schema."""
    system_prompt: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None
    api_key: Optional[str] = Field(default=None, description="OpenClaw API key (stored encrypted)")


class AgentConfigUpdate(BaseModel):
    """Agent configuration update schema."""
    agent_name: Optional[str] = None
    backend_type: Optional[str] = None
    provider_id: Optional[str] = None
    endpoint_url: Optional[str] = Field(default=None)
    system_prompt: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    permission_level: Optional[str] = None
    associated_skills: Optional[List[int]] = None
    metadata_json: Optional[Dict[str, Any]] = None
    auth_mode: Optional[str] = None
    streaming: Optional[bool] = None
    api_key: Optional[str] = None

    _url_validator = field_validator("endpoint_url", mode="before")(_validate_endpoint_url)


class AgentConfigResponse(BaseModel):
    """Agent configuration response schema."""
    id: int
    agent_name: str
    backend_type: str
    provider_id: Optional[str]
    endpoint_url: Optional[str]
    description: Optional[str]
    is_active: bool
    permission_level: str
    associated_skills: Optional[List[int]]
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentExecutionBase(BaseModel):
    """Base agent execution schema."""
    agent_id: int
    input_data: Optional[Dict[str, Any]] = None



class AgentConfigListResponse(BaseModel):
    """Paginated list of agent configurations."""
    total: int
    agents: list[AgentConfigResponse]


class AgentExecutionCreate(AgentExecutionBase):
    """Agent execution creation schema."""
    task: str


class AgentExecutionResponse(BaseModel):
    """Agent execution response schema."""
    id: int
    execution_id: str
    agent_id: int
    status: str
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class AgentExecuteRequest(BaseModel):
    """Request to execute an agent task."""
    agent_id: int
    task: str
    context: Optional[Dict[str, Any]] = None


class AgentExecuteResponse(BaseModel):
    """Agent execution result response."""
    execution_id: str
    agent_id: int
    agent_name: str
    status: str
    output: Optional[Any]
    error: Optional[str]
    execution_time: float
    timestamp: str

# Aliases for router compatibility
AgentConfigRead = AgentConfigResponse
AgentExecutionRead = AgentExecutionResponse
AgentTestRequest = AgentExecuteRequest
AgentTestResponse = AgentExecuteResponse
