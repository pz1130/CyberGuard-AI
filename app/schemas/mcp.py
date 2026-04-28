"""Pydantic schemas for MCP (Model Context Protocol) tool integration."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class MCPServerBase(BaseModel):
    """Base MCP server schema."""
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., description="MCP server endpoint URL")
    description: Optional[str] = None


class MCPServerCreate(MCPServerBase):
    """MCP server creation schema."""
    auth_token: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    is_active: bool = True
    timeout: int = 30
    metadata_json: Optional[Dict[str, Any]] = None


class MCPServerUpdate(BaseModel):
    """MCP server update schema."""
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    auth_token: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    timeout: Optional[int] = None
    metadata_json: Optional[Dict[str, Any]] = None


class MCPServerResponse(BaseModel):
    """MCP server response schema."""
    id: int
    name: str
    url: str
    description: Optional[str]
    is_active: bool
    timeout: int
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


class MCPToolCreate(MCPToolBase):
    """MCP tool creation schema."""
    input_schema_json: Optional[str] = None
    category: Optional[str] = None
    is_active: bool = True


class MCPToolResponse(BaseModel):
    """MCP tool response schema."""
    id: int
    server_id: int
    tool_name: str
    description: Optional[str]
    input_schema_json: Optional[str]
    category: Optional[str]
    is_active: bool
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

# Aliases
MCPServerRead = MCPServerResponse
