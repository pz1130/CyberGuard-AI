"""Pydantic schemas for MCP (Model Context Protocol) tool integration."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class MCPServerBase(BaseModel):
    """Base MCP server schema."""
    name: str = Field(..., min_length=1, max_length=100)
    transport_type: str = Field(default="stdio", description="stdio | sse | streamable_http")
    # STDIO mode fields
    command: Optional[str] = Field(default=None, description="Executable path (for STDIO)")
    args: Optional[List[str]] = Field(default=None, description="Command arguments")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables (encrypted at rest)")
    # HTTP mode fields
    url: Optional[str] = Field(default=None, description="HTTP endpoint (for SSE/streamable_http)")
    auth_token: Optional[str] = Field(default=None, description="Bearer token (encrypted at rest)")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Custom HTTP headers")
    # Common
    description: Optional[str] = None
    is_active: bool = True
    timeout: int = Field(default=30, ge=1, le=300, description="Timeout in seconds")
    metadata_json: Optional[Dict[str, Any]] = None


class MCPServerCreate(MCPServerBase):
    """MCP server creation schema."""
    pass


class MCPServerUpdate(BaseModel):
    """MCP server update schema."""
    name: Optional[str] = None
    transport_type: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    auth_token: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    timeout: Optional[int] = Field(default=None, ge=1, le=300)
    metadata_json: Optional[Dict[str, Any]] = None


class MCPServerResponse(BaseModel):
    """MCP server response schema."""
    id: int
    name: str
    transport_type: str
    command: Optional[str]
    args: Optional[List[str]]
    url: Optional[str]
    description: Optional[str]
    is_active: bool
    timeout_seconds: int
    metadata_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MCPToolBase(BaseModel):
    """Base MCP tool schema."""
    server_id: int
    tool_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    input_schema_json: Optional[str] = None
    category: Optional[str] = None
    is_active: bool = True


class MCPToolCreate(MCPToolBase):
    """MCP tool creation schema."""
    pass


class MCPToolUpdate(BaseModel):
    """MCP tool update schema."""
    tool_name: Optional[str] = None
    description: Optional[str] = None
    input_schema_json: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class MCPToolResponse(BaseModel):
    """MCP tool response schema."""
    id: int
    server_id: int
    tool_name: str
    description: Optional[str]
    input_schema_json: Optional[str]
    category: Optional[str]
    is_active: bool
    last_used_at: Optional[datetime]
    use_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class MCPToolExecuteRequest(BaseModel):
    """MCP tool execution request schema."""
    tool_id: int
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPToolExecuteResponse(BaseModel):
    """MCP tool execution response schema."""
    tool_id: int
    tool_name: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float


class MCPServerListResponse(BaseModel):
    """Paginated MCP server list response."""
    total: int
    servers: List[MCPServerResponse]


class MCPToolListResponse(BaseModel):
    """Paginated MCP tool list response."""
    total: int
    tools: List[MCPToolResponse]


# Aliases
MCPServerRead = MCPServerResponse
MCPToolRead = MCPToolResponse
