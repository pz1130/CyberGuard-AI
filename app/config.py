"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import List
import json


DEFAULT_KEY = "72afad1417e44d63d11975fd873f86e2dcf7e262a4c461ea4a0c43939868f5e4"
DEFAULT_REDIS_PASSWORD = "cyberguard-redis-pass"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cyberguard"

    # Redis
    REDIS_PASSWORD: str = DEFAULT_REDIS_PASSWORD
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

    # Context Compressor (master-agent conversation-history compression)
    # CONTEXT_COMPRESS_MAX_TOKENS is the *fallback* absolute threshold when no
    # model context_window is available. Preferred path: remaining_budget(
    #   context_window - reserve_output - reserve_system).
    CONTEXT_COMPRESS_MAX_TOKENS: int = 8000
    CONTEXT_COMPRESS_KEEP_LAST: int = 6
    CONTEXT_COMPRESS_RESERVE_OUTPUT: int = 1024
    CONTEXT_COMPRESS_RESERVE_SYSTEM: int = 512
    # Default context window when provider model entry has none (M0a-2 catalog).
    DEFAULT_CONTEXT_WINDOW: int = 128000

    # Sub-Agent Defaults
    SUB_AGENT_TIMEOUT: int = 30
    SUB_AGENT_MAX_RETRIES: int = 2
    # INV-23 · fan-out gates (conservative defaults)
    SUB_AGENT_MAX_CONCURRENT: int = 4          # semaphore for parallel execute
    SUB_AGENT_MAX_PLAN_SIZE: int = 12          # hard cap on tasks per master turn
    SUB_AGENT_MAX_PER_AGENT: int = 2           # same agent_id occurrences per plan
    SUB_AGENT_MAX_DEPTH: int = 1               # master=0; sub dispatch depth ≤ this
    SUB_AGENT_REQUIRE_TARGET: bool = True  # need agent_id, agent_name, or agent_type

    # Public base URL used to inject manifest_url into external agent payloads.
    # Leave empty to disable manifest_url injection (safe default).
    BASE_URL: str = ""

    # Azure AD / Entra ID SSO. The client secret is read from the environment
    # ONLY (never stored in the DB). Non-secret config (tenant/client id, redirect,
    # enabled, role mappings) lives in the sso_config / sso_role_mapping tables.
    AZURE_CLIENT_SECRET: str = ""

    # Environment
    ENVIRONMENT: str = "development"

    # Mock mode (for demo without real LLM API keys) — defaults False for safety
    MOCK_MODE: bool = False

    # Chat attachment extraction caps (chars)
    ATTACHMENT_MAX_CHARS: int = 8000          # per attachment
    ATTACHMENT_TOTAL_MAX_CHARS: int = 24000   # across all attachments in one request

    # Group-chat consensus detection (issue #14)
    GROUPCHAT_CONSENSUS_HIGH: float = 0.85      # min cosine >= HIGH => consensus
    GROUPCHAT_CONSENSUS_LOW: float = 0.65       # min cosine < LOW  => no consensus
    GROUPCHAT_JACCARD_THRESHOLD: float = 0.7    # lexical fallback threshold

    # Auto-approve approval requests without human intervention.
    # NDB Std §B5 / P1 (default deny): security actions must never auto-approve.
    # This is the master switch for the entire HITL boundary — when it is on,
    # ApprovalService.wait_for_decision resolves every request as approved
    # without a human. It therefore defaults OFF, and turning it on outside
    # development is a hard configuration error (see validate_security_keys).
    AUTO_APPROVE: bool = False

    # Kill switch file trigger (NDB Std §Kill Switch)
    KILL_SWITCH_FILE: str = "var/governance/kill_switch"

    # PII filter settings (NDB Std §Data Lineage & PII / A5)
    PII_FILTER_ENABLED: bool = True
    PII_HANDLING_POLICY: str = "redact"

    # Egress allowlist (defense-in-depth over SSRF block-list)
    EGRESS_ALLOWLIST_ENABLED: bool = False
    EGRESS_ALLOWLIST: str = ""

    @model_validator(mode="after")
    def validate_security_keys(self) -> "Settings":
        """Ensure security keys are properly configured."""
        errors = []
        if self.ENCRYPTION_KEY == DEFAULT_KEY or self.SECRET_KEY == DEFAULT_KEY:
            errors.append(
                "ENCRYPTION_KEY and SECRET_KEY must be configured with unique values. "
                "Set the ENCRYPTION_KEY and SECRET_KEY environment variables."
            )
        if self.ENCRYPTION_KEY == self.SECRET_KEY:
            errors.append(
                "ENCRYPTION_KEY and SECRET_KEY must be different. "
                "Using the same key for AES encryption and JWT signing is a security risk."
            )
        if self.REDIS_PASSWORD == DEFAULT_REDIS_PASSWORD and self.ENVIRONMENT == "production":
            errors.append(
                "REDIS_PASSWORD is using the default value. "
                "Set the REDIS_PASSWORD environment variable."
            )
        # NDB Std §B5: never auto-approve security actions outside development.
        # A warning is the wrong control here — it prints once, to stderr, and
        # is invisible under a process manager, so the approval boundary could
        # be off in production with nothing to show for it (INV-25: security
        # degradation must be loud, never silent).
        if self.ENVIRONMENT != "development" and self.AUTO_APPROVE:
            errors.append(
                f"AUTO_APPROVE must not be enabled when ENVIRONMENT={self.ENVIRONMENT!r}. "
                "It bypasses every human approval gate. Unset AUTO_APPROVE "
                "or set ENVIRONMENT=development."
            )
        if errors:
            raise ValueError("\n".join(errors))
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
