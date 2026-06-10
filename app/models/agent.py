"""Agent configuration database models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from app.core.database import Base


class AgentConfig(Base):
    """Sub-agent configuration model."""

    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(100), unique=True, nullable=False, index=True)
    backend_type = Column(String(50), nullable=False)  # openclaw, hermes, custom
    provider_id = Column(String(100), nullable=True)
    endpoint_url = Column(String(500), nullable=True)
    env_vars_encrypted = Column(Text, nullable=True)  # AES-256 encrypted JSON
    system_prompt = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    permission_level = Column(String(20), default="medium")  # low, medium, high
    associated_skills = Column(JSON, nullable=True)  # List of skill IDs
    associated_tools = Column(JSON, nullable=True)       # List of Tool IDs
    associated_mcp_tools = Column(JSON, nullable=True)   # List of MCPTool IDs
    metadata_json = Column(JSON, nullable=True)
    # --- Declarative governance (NDB Std §Mandatory Governance Taxonomy / B1) ---
    autonomy_tier = Column(String(8), nullable=False, server_default="L2", default="L2")
    l3_authorization_ref = Column(String(255), nullable=True)
    allowed_categories = Column(JSON, nullable=True)
    auto_execute_min_confidence = Column(Float, nullable=False, server_default="0.85", default=0.85)
    escalate_to_human_below = Column(Float, nullable=False, server_default="0.60", default=0.60)
    pii_handling_policy = Column(String(20), nullable=False, server_default="redact", default="redact")
    kill_switch_enabled = Column(Boolean, nullable=False, server_default="true", default=True)
    is_poc = Column(Boolean, nullable=False, server_default="true", default=True)
    requires_approval_rules = Column(JSON, nullable=True)
    governed = Column(Boolean, nullable=False, server_default="false", default=False)
    # Kind discriminator: 'external' (HTTP / OpenClaw) or 'internal' (in-app)
    kind = Column(String(20), nullable=False, default="external", index=True)
    # Internal-agent only fields (nullable for external rows)
    llm_provider_id = Column(Integer, ForeignKey("providers.id", ondelete="SET NULL"), nullable=True)
    llm_model = Column(String(100), nullable=True)
    tool_loop_max_steps = Column(Integer, nullable=False, default=8)
    memory_window = Column(Integer, nullable=False, default=20)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True)
    # OpenClaw Gateway fields
    api_key_hash = Column(String(128), nullable=True)      # SHA-256 of the oc-xxx key
    openclaw_last_seen = Column(DateTime, nullable=True)   # last poll/heartbeat time
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AgentConfig {self.agent_name} ({self.backend_type})>"


class AgentExecution(Base):
    """Agent execution/Task tracking model."""

    __tablename__ = "agent_executions"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    agent_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)  # nullable: Master Agent has no agent_configs row
    status = Column(String(20), nullable=False)  # pending, running, completed, failed
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AgentExecution {self.execution_id} ({self.status})>"