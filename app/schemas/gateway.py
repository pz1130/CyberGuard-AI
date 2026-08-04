"""Pydantic schemas for the /gateway/manifest endpoint."""
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ManifestSkill(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    md_content: str


class ManifestTool(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    command_template: Optional[str] = None
    input_schema: Dict[str, Any]


class ManifestMCPTool(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]


class ManifestResponse(BaseModel):
    agent_id: int
    agent_name: str
    governed: bool = False
    skills: list[ManifestSkill]
    tools: list[ManifestTool]
    mcp_tools: list[ManifestMCPTool]
