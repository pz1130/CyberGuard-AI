"""MCP (Model Context Protocol) server configuration router."""
from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import require_permission
from app.core.rbac import Permission
from app.schemas.mcp import MCPServerCreate, MCPServerRead, MCPServerListResponse

router = APIRouter()

# In-memory MCP server store
_mcp_servers = {}


@router.get("/mcp", response_model=MCPServerListResponse)
async def list_mcp_servers(_=Depends(require_permission(Permission.AGENT_READ))):
    """List all configured MCP servers."""
    return MCPServerListResponse(total=len(_mcp_servers), servers=list(_mcp_servers.values()))


@router.post("/mcp", response_model=MCPServerRead, status_code=201)
async def create_mcp_server(body: MCPServerCreate, _=Depends(require_permission(Permission.AGENT_WRITE))):
    """Register a new MCP server."""
    if body.name in _mcp_servers:
        raise HTTPException(status_code=400, detail="MCP server name already exists")
    server_data = body.model_dump()
    _mcp_servers[body.name] = server_data
    return MCPServerRead(**server_data)


@router.delete("/mcp/{server_name}", status_code=204)
async def delete_mcp_server(server_name: str, _=Depends(require_permission(Permission.AGENT_WRITE))):
    """Delete an MCP server."""
    if server_name not in _mcp_servers:
        raise HTTPException(status_code=404, detail="MCP server not found")
    del _mcp_servers[server_name]
