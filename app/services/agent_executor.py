"""Sub-Agent HTTP executor wrapper."""
import httpx
import json
from typing import Dict, Any, Optional
from datetime import datetime

from app.config import settings
from app.core.security import decrypt_data
from app.core.rbac import Permission


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

        payload = {
            "task": task,
            "context": context or {},
            "env_vars": self.env_vars,
            "timestamp": datetime.utcnow().isoformat(),
        }

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.endpoint_url}/execute",
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
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.endpoint_url}/health",
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
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.endpoint_url}/status",
                    headers=self._get_headers(),
                )
                if response.status_code == 200:
                    return response.json()
                return {"status": "unknown", "code": response.status_code}
        except Exception as e:
            return {"status": "offline", "error": str(e)}


class AgentExecutor:
    """Service for managing sub-agent executions."""

    async def execute(self, agent_id: int, task: str, user_id: int) -> Dict[str, Any]:
        """
        Execute task on a specific sub-agent.

        Args:
            agent_id: Database ID of the agent config
            task: Task description
            user_id: User ID making the request

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
                "endpoint_url": agent_obj.endpoint_url,
                "env_vars_encrypted": agent_obj.env_vars_encrypted,
                "permission_level": getattr(agent_obj, "permission_level", "medium"),
            }

        wrapper = SubAgentWrapper(config_dict)

        # Check permission level
        permission_level = config_dict.get("permission_level", "medium")
        if permission_level == "high":
            # Require admin approval
            return {
                "status": "needs_approval",
                "output": None,
                "error": "High permission agent requires approval",
            }

        result = await wrapper.execute(
            task=task,
            context={"user_id": user_id},
        )

        result["agent_id"] = agent_id
        result["agent_name"] = config_dict.get("agent_name")
        result["timestamp"] = datetime.utcnow().isoformat()

        return result

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