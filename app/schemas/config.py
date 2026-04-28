"""Pydantic schemas for system configuration."""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class ConfigValueUpdate(BaseModel):
    """Configuration value update schema."""
    value: str


class ConfigSectionResponse(BaseModel):
    """Configuration section response schema."""
    section: str
    key: str
    value: str
    is_encrypted: bool
    description: Optional[str] = None


class LLMProviderConfig(BaseModel):
    """LLM provider configuration schema."""
    name: str
    api_key: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    models: List[str] = ["gpt-4o"]
    is_active: bool = True


class LLMProviderUpdate(BaseModel):
    """LLM provider update schema."""
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: Optional[List[str]] = None
    is_active: Optional[bool] = None


class SystemConfigResponse(BaseModel):
    """Full system configuration response schema."""
    database_url: str
    redis_url: str
    encryption_key_set: bool
    master_agent_model: str
    master_agent_temperature: float
    sub_agent_timeout: int
    sub_agent_max_retries: int
    log_level: str
    jwt_expiration_minutes: int
    llm_providers: List[LLMProviderConfig]


class FeatureFlagsResponse(BaseModel):
    """Feature flags response schema."""
    enable_group_chat: bool
    enable_knowledge_base: bool
    enable_scheduled_tasks: bool
    enable_audit_logging: bool
    enable_backup: bool