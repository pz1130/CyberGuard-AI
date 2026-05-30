"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import List
import json


DEFAULT_KEY = "72afad1417e44d63d11975fd873f86e2dcf7e262a4c461ea4a0c43939868f5e4"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cyberguard"

    # Redis
    REDIS_PASSWORD: str = "cyberguard-redis-pass"
    REDIS_URL: str = "redis://:${REDIS_PASSWORD}@redis:6379/0"

    # Security
    ENCRYPTION_KEY: str = DEFAULT_KEY
    SECRET_KEY: str = DEFAULT_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # LLM Providers
    LITELLM_CONFIG: str = '{"providers": []}'

    # WebUI
    WEBUI_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:8000"]'

    # Master Agent
    MASTER_AGENT_MODEL: str = "gpt-4o"
    MASTER_AGENT_TEMPERATURE: float = 0.7

    # Sub-Agent Defaults
    SUB_AGENT_TIMEOUT: int = 30
    SUB_AGENT_MAX_RETRIES: int = 2

    # Public base URL used to inject manifest_url into external agent payloads.
    # Leave empty to disable manifest_url injection (safe default).
    BASE_URL: str = ""

    # Environment
    ENVIRONMENT: str = "development"

    # Mock mode (for demo without real LLM API keys) — defaults False for safety
    MOCK_MODE: bool = False

    # Auto-approve approval requests without human intervention
    AUTO_APPROVE: bool = True

    @model_validator(mode="after")
    def validate_security_keys(self) -> "Settings":
        """Ensure ENCRYPTION_KEY and SECRET_KEY are not using default values."""
        if self.ENCRYPTION_KEY == DEFAULT_KEY or self.SECRET_KEY == DEFAULT_KEY:
            raise ValueError(
                "ENCRYPTION_KEY and SECRET_KEY must be configured with unique values. "
                "Do not use the default insecure key in production. "
                "Set the CYBERGUARD_ENCRYPTION_KEY and CYBERGUARD_SECRET_KEY environment variables."
            )
        return self

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

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
