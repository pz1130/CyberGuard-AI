"""Sub-Agent HTTP executor wrapper."""
import httpx
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import urlparse

from app.config import settings
from app.core.security import decrypt_data
from app.core.rbac import Permission


def _resolve_api_key(config: Dict[str, Any]) -> str:
    """Extract the API key for an agent, trying multiple storage locations.

    Priority:
      1. env_vars_encrypted JSON field with key "OPENCLAW_API_KEY"
      2. metadata_json.api_key_encrypted  (AES-256 encrypted)
      3. metadata_json.api_key            (plain, legacy / dev)
    """
    # 1. env_vars_encrypted
    env_enc = config.get("env_vars_encrypted")
    if env_enc:
        try:
            env_vars = json.loads(decrypt_data(env_enc))
            key = env_vars.get("OPENCLAW_API_KEY", "")
            if key:
                return key
        except Exception:
            pass

    # 2. metadata_json.api_key_encrypted
    meta = config.get("metadata_json") or {}
    enc = meta.get("api_key_encrypted", "")
    if enc:
        try:
            return decrypt_data(enc)
        except Exception:
            pass

    # 3. metadata_json.api_key (plain)
    return meta.get("api_key", "")

# Blocked hostnames for SSRF protection
_BLOCKED_HOSTS = frozenset({
    "169.254.169.254",       # AWS / Azure metadata
    "metadata.google.internal",  # GCP metadata
    "metadata.internal",
    "metadata.azure.com",
    "localhost",
    "0.0.0.0",
    "127.0.0.1",
})


def _validate_endpoint_url(endpoint_url: str) -> str:
    """
    Validate endpoint URL to prevent SSRF.
    Returns the validated URL or raises ValueError.
    """
    if not endpoint_url:
        raise ValueError("Endpoint URL cannot be empty")
    parsed = urlparse(endpoint_url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Disallowed scheme: {scheme}. Only http/https allowed.")
    hostname = parsed.hostname or ""
    # Block direct IP access to private ranges
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"Disallowed host: {hostname}")
    # Block obvious private/CIDR ranges (basic check)
    if hostname.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                            "172.20.", "172.21.", "172.22.", "172.23.",
                            "172.24.", "172.25.", "172.26.", "172.27.",
                            "172.28.", "172.29.", "172.30.", "172.31.",
                            "192.168.")):
        raise ValueError(f"Disallowed private network range: {hostname}")
    return endpoint_url


class SubAgentWrapper:
    """
    Wrapper for executing tasks on remote Sub-Agents via HTTP.

    Sub-Agents are deployed separately and registered via WebUI.
    The Master Agent communicates with them via REST endpoints.
    """

    def __init__(self, agent_config: Dict[str, Any]):
        self.agent_id = agent_config.get("id")
        self.agent_name = agent_config.get("agent_name")
        self.backend_type = agent_config.get("backend_type", "openclaw")
        self.endpoint_url = agent_config.get("endpoint_url")
        self.env_vars_encrypted = agent_config.get("env_vars_encrypted")

        # Decrypt environment variables if present
        self.env_vars = {}
        if self.env_vars_encrypted:
            try:
                self.env_vars = json.loads(decrypt_data(self.env_vars_encrypted))
            except Exception:
                pass

        self.timeout = settings.SUB_AGENT_TIMEOUT
        self.max_retries = settings.SUB_AGENT_MAX_RETRIES

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for sub-agent communication."""
        return {
            "Content-Type": "application/json",
            "X-Agent-ID": str(self.agent_id),
            "X-Timestamp": datetime.utcnow().isoformat(),
        }

    async def execute(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a task on the sub-agent.

        Args:
            task: Task description/instruction
            context: Additional context (user_id, session_id, etc.)

        Returns:
            Result dict with status, output, error
        """
        if not self.endpoint_url:
            return {
                "status": "error",
                "output": None,
                "error": f"No endpoint configured for agent {self.agent_name}",
            }

        # SSRF protection + scheme check
        try:
            validated_url = _validate_endpoint_url(self.endpoint_url)
        except ValueError as e:
            return {"status": "error", "output": None, "error": f"Invalid endpoint URL: {e}"}

        payload = {
            "task": task,
            "context": context or {},
            "env_vars": self.env_vars,
            "timestamp": datetime.utcnow().isoformat(),
        }

        for attempt in range(self.max_retries):
            try:
                # Enforce HTTPS; verify certs in production
                import ssl
                parsed = urlparse(validated_url)
                verify_certs = parsed.scheme == "https"
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    verify=verify_certs,
                ) as client:
                    response = await client.post(
                        f"{validated_url}/execute",
                        headers=self._get_headers(),
                        json=payload,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        return {
                            "status": "completed",
                            "output": result.get("output"),
                            "execution_time": result.get("execution_time", 0),
                        }
                    elif response.status_code == 401:
                        return {
                            "status": "error",
                            "output": None,
                            "error": "Authentication failed with sub-agent",
                        }
                    elif response.status_code == 403:
                        return {
                            "status": "needs_approval",
                            "output": None,
                            "error": "Sub-agent requires human approval",
                        }
                    else:
                        error_msg = f"Sub-agent returned status {response.status_code}"

            except httpx.TimeoutException:
                error_msg = f"Timeout communicating with {self.agent_name}"
            except httpx.ConnectError:
                error_msg = f"Cannot connect to {self.agent_name} at {self.endpoint_url}"
            except Exception as e:
                error_msg = str(e)

            if attempt < self.max_retries - 1:
                continue

        return {
            "status": "failed",
            "output": None,
            "error": error_msg,
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to the sub-agent."""
        if not self.endpoint_url:
            return {"success": False, "error": "No endpoint configured"}

        try:
            validated_url = _validate_endpoint_url(self.endpoint_url)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        try:
            parsed = urlparse(validated_url)
            verify_certs = parsed.scheme == "https"
            async with httpx.AsyncClient(timeout=10, verify=verify_certs) as client:
                response = await client.get(
                    f"{validated_url}/health",
                    headers=self._get_headers(),
                )
                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                return {"success": False, "error": f"Health check failed: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_status(self) -> Dict[str, Any]:
        """Get sub-agent status."""
        if not self.endpoint_url:
            return {"status": "offline", "error": "No endpoint configured"}

        try:
            validated_url = _validate_endpoint_url(self.endpoint_url)
        except ValueError as e:
            return {"status": "offline", "error": str(e)}

        try:
            parsed = urlparse(validated_url)
            verify_certs = parsed.scheme == "https"
            async with httpx.AsyncClient(timeout=10, verify=verify_certs) as client:
                response = await client.get(
                    f"{validated_url}/status",
                    headers=self._get_headers(),
                )
                if response.status_code == 200:
                    return response.json()
                return {"status": "unknown", "code": response.status_code}
        except Exception as e:
            return {"status": "offline", "error": str(e)}


class AgentExecutor:
    """Service for managing sub-agent executions."""

    async def get_mcp_tools_for_agent(self, agent_metadata_json: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Fetch active MCP tools and convert to OpenClaw tool format.
        If agent metadata specifies mcp_tool_ids, only those tools are returned.
        Otherwise all active MCP tools are returned.
        """
        from app.core.database import get_db_context
        from app.models.mcp import MCPTool
        from sqlalchemy import select
        import json

        async with get_db_context() as session:
            query = select(MCPTool).where(MCPTool.is_active == True)
            # Filter by selected tool IDs if specified in agent config
            if agent_metadata_json and agent_metadata_json.get("mcp_tool_ids"):
                tool_ids = agent_metadata_json["mcp_tool_ids"]
                query = query.where(MCPTool.id.in_(tool_ids))
            result = await session.execute(query)
            tools = result.scalars().all()

        openclaw_tools = []
        for t in tools:
            try:
                input_schema = json.loads(t.input_schema_json) if t.input_schema_json else {}
            except Exception:
                input_schema = {}
            openclaw_tools.append({
                "name": t.tool_name,
                "description": t.description or "",
                "input_schema": input_schema,
            })
        return openclaw_tools

    async def execute(
        self,
        agent_id: int,
        task: str,
        user_id: int,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Execute task on a specific sub-agent.

        Args:
            agent_id: Database ID of the agent config
            task: Task description
            user_id: User ID making the request
            tools: Optional list of tool definitions to pass to the agent

        Returns:
            Execution result
        """
        # Fetch agent config from database
        from app.core.database import get_db_context
        from app.models.agent import AgentConfig
        from sqlalchemy import select
        import json

        async with get_db_context() as session:
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.id == agent_id)
            )
            agent_obj = result.scalar_one_or_none()

            if not agent_obj:
                return {
                    "status": "error",
                    "output": None,
                    "error": f"Agent {agent_id} not found",
                }

            config_dict = {
                "id": agent_obj.id,
                "agent_name": agent_obj.agent_name,
                "backend_type": agent_obj.backend_type,
                "provider_id": agent_obj.provider_id,
                "endpoint_url": agent_obj.endpoint_url,
                "env_vars_encrypted": agent_obj.env_vars_encrypted,
                "system_prompt": agent_obj.system_prompt,
                "permission_level": getattr(agent_obj, "permission_level", "medium"),
                "associated_skills": agent_obj.associated_skills,
                "metadata_json": agent_obj.metadata_json,
                # OpenClaw-specific fields (from metadata_json if not set directly)
                "api_key": getattr(agent_obj, "api_key", "") or "",
                "auth_mode": getattr(agent_obj, "auth_mode", "api_key"),
                "streaming": getattr(agent_obj, "streaming", True),
            }

        # Check permission level
        permission_level = config_dict.get("permission_level", "medium")
        if permission_level == "high":
            return {
                "status": "needs_approval",
                "output": None,
                "error": "High permission agent requires approval",
            }

        backend = config_dict["backend_type"]

        if backend == "openclaw":
            result = await self._execute_openclaw(config_dict, task)
        else:
            # Generic HTTP fallback (Hermes / custom backends)
            wrapper = SubAgentWrapper(config_dict)
            result = await wrapper.execute(task=task, context={"user_id": user_id})

        result["agent_id"] = agent_id
        result["agent_name"] = config_dict.get("agent_name")
        result["timestamp"] = datetime.utcnow().isoformat()

        return result

    async def _execute_openclaw(self, config: Dict[str, Any], task: str) -> Dict[str, Any]:
        """Execute a task on a Clawith/OpenClaw agent via /v1/responses."""
        from app.services import openclaw_executor

        endpoint = config.get("endpoint_url", "").rstrip("/")
        if not endpoint:
            return {"status": "error", "output": None, "error": "No endpoint URL configured"}

        # Resolve api_key — stored encrypted in env_vars or metadata_json
        api_key = _resolve_api_key(config)
        if not api_key:
            return {"status": "error", "output": None, "error": "No API key configured for OpenClaw agent"}

        # Resolve the Clawith agent ID (distinct from our internal DB id)
        meta = config.get("metadata_json") or {}
        openclaw_agent_id = meta.get("openclaw_agent_id") or meta.get("agent_id") or "main"

        return await openclaw_executor.execute(
            endpoint_url=endpoint,
            api_key=api_key,
            openclaw_agent_id=openclaw_agent_id,
            task=task,
        )

    async def execute_parallel(self, agent_ids: list, task: str, user_id: int) -> Dict[int, Dict[str, Any]]:
        """Execute task on multiple agents in parallel."""
        import asyncio

        tasks = [
            self.execute(agent_id, task, user_id)
            for agent_id in agent_ids
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            agent_id: results[i] if not isinstance(results[i], Exception) else {
                "status": "error",
                "error": str(results[i]),
            }
            for i, agent_id in enumerate(agent_ids)
        }