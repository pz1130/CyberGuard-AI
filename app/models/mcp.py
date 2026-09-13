"""Database models for MCP servers and tools."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.time import utc_now


class MCPServer(Base):
    """MCP server configuration."""
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    transport_type = Column(String(20), nullable=False, default="stdio")  # stdio | sse | streamable_http
    # STDIO mode
    command = Column(String(500), nullable=True)
    args = Column(JSON, nullable=True)  # List[str]
    env_vars_encrypted = Column(Text, nullable=True)  # AES-256 encrypted JSON
    # HTTP mode
    url = Column(String(500), nullable=True)
    auth_token_encrypted = Column(Text, nullable=True)
    headers_json = Column(JSON, nullable=True)
    # Common
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    timeout_seconds = Column(Integer, default=30)
    process_id = Column(Integer, nullable=True)  # PID of running subprocess
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    tools = relationship("MCPTool", back_populates="server", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MCPServer {self.name} ({self.transport_type})>"


class MCPTool(Base):
    """Individual tool exposed by an MCP server."""
    __tablename__ = "mcp_tools"

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(100), nullable=False, index=True)
    description = Column(String(500), nullable=True)
    input_schema_json = Column(Text, nullable=True)  # JSON Schema string
    category = Column(String(50), nullable=True)  # threat, log, vuln, etc.
    tags = Column(JSON, nullable=True)  # List[str]
    # P2-2: Per-tool RBAC permission requirement (e.g. "knowledge:write", "admin:all")
    # Empty/null = any authenticated user with TASK_EXECUTE may execute it.
    required_permission = Column(String(100), nullable=True, index=True)
    action_category = Column(String(20), nullable=True)
    risk_tier = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    use_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    server = relationship("MCPServer", back_populates="tools")

    def __repr__(self):
        return f"<MCPTool {self.tool_name} (server={self.server_id})>"
