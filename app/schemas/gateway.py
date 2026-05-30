"""Pydantic schemas for the /gateway/manifest endpoint."""
from typing import Optional
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
    input_schema: dict


class ManifestMCPTool(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    input_schema: dict


class ManifestResponse(BaseModel):
    agent_id: int
    agent_name: str
    skills: list[ManifestSkill]
    tools: list[ManifestTool]
    mcp_tools: list[ManifestMCPTool]
