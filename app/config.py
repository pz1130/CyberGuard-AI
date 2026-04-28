"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cyberguard"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    ENCRYPTION_KEY: str = "change-me-32-bytes"
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # LLM Providers
    LITELLM_CONFIG: str = "{}"

    # WebUI
    WEBUI_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:8000"]'

    # Master Agent
    MASTER_AGENT_MODEL: str = "gpt-4o"
    MASTER_AGENT_TEMPERATURE: float = 0.7

    # Sub-Agent Defaults
    SUB_AGENT_TIMEOUT: int = 30
    SUB_AGENT_MAX_RETRIES: int = 2

    # Environment
    ENVIRONMENT: str = "development"

    @property
    def litellm_providers(self) -> list:
        """Parse LITELLM_CONFIG JSON."""
        try:
            return json.loads(self.LITELLM_CONFIG).get("providers", [])
        except json.JSONDecodeError:
            return []

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS JSON string."""
        try:
            return json.loads(self.CORS_ORIGINS)
        except json.JSONDecodeError:
            return []

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
