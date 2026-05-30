"""Sub-Agent HTTP executor wrapper."""
import httpx
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.config import settings
from app.core.security import decrypt_data
from app.core.rbac import Permission
from app.services.internal_agent import InternalAgentRunner


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

from app.core.ssrf import validate_outbound_url as _validate_endpoint_url


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
            "X-Timestamp": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if settings.BASE_URL:
            payload["manifest_url"] = (
                f"{settings.BASE_URL.rstrip('/')}/api/v1/gateway/manifest"
            )

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

    async def get_mcp_tools_for_agent(
        self,
        agent_associated_mcp_tools: Optional[List[int]] = None,
        agent_metadata_json: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch active MCP tools for an agent and convert to OpenClaw tool format.

        Priority:
          1. agent_associated_mcp_tools (new column) — filter to these IDs
          2. agent_metadata_json.mcp_tool_ids (legacy key) — filter to these IDs
          3. Neither set — return all active MCP tools
        """
        from app.core.database import get_db_context
        from app.models.mcp import MCPTool
        from sqlalchemy import select
        import json

        # Column-first, metadata fallback
        tool_ids = agent_associated_mcp_tools
        if tool_ids is None and agent_metadata_json:
            tool_ids = agent_metadata_json.get("mcp_tool_ids")

        async with get_db_context() as session:
            query = select(MCPTool).where(MCPTool.is_active == True)
            if tool_ids is not None:
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
        context: Optional[Dict[str, Any]] = None,
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
                "kind": agent_obj.kind,
                "backend_type": agent_obj.backend_type,
                "provider_id": agent_obj.provider_id,
                "llm_provider_id": agent_obj.llm_provider_id,
                "llm_model": agent_obj.llm_model,
                "endpoint_url": agent_obj.endpoint_url,
                "env_vars_encrypted": agent_obj.env_vars_encrypted,
                "system_prompt": agent_obj.system_prompt,
                "permission_level": getattr(agent_obj, "permission_level", "medium"),
                "tool_loop_max_steps": agent_obj.tool_loop_max_steps,
                "memory_window": agent_obj.memory_window,
                "knowledge_base_id": agent_obj.knowledge_base_id,
                "associated_skills": agent_obj.associated_skills,
                "associated_tools": agent_obj.associated_tools,
                "associated_mcp_tools": agent_obj.associated_mcp_tools,
                "metadata_json": agent_obj.metadata_json,
                # OpenClaw-specific fields (from metadata_json if not set directly)
                "api_key": getattr(agent_obj, "api_key", "") or "",
                "auth_mode": getattr(agent_obj, "auth_mode", "api_key"),
                "streaming": getattr(agent_obj, "streaming", True),
            }

        # Check permission level (external — internal handles it internally)
        permission_level = config_dict.get("permission_level", "medium")
        kind = config_dict.get("kind") or "external"

        if kind == "internal":
            runner = InternalAgentRunner(config_dict)
            conv_id = (context or {}).get("conversation_id")
            result = await runner.execute(task=task, conversation_id=conv_id, user_id=user_id)
        else:
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
                wrapper = SubAgentWrapper(config_dict)
                result = await wrapper.execute(task=task, context={"user_id": user_id})

        result["agent_id"] = agent_id
        result["agent_name"] = config_dict.get("agent_name")
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result

    async def _execute_openclaw(self, config: Dict[str, Any], task: str) -> Dict[str, Any]:
        """向 OpenClaw 节点派发任务（Gateway 轮询模式）。

        流程：
          1. 在 gateway_messages 表写入一条 pending 任务
          2. 等待 OpenClaw 节点 poll → execute → report
          3. 通过 Redis pub/sub（或 DB 轮询兜底）等待结果
          4. 超时返回 error
        """
        import asyncio
        import uuid
        from app.core.database import AsyncSessionLocal
        from app.models.gateway_message import GatewayMessage
        from sqlalchemy import select

        agent_id = config["id"]
        execution_id = str(uuid.uuid4())
        timeout = config.get("timeout", settings.SUB_AGENT_TIMEOUT)

        # 1. 写入 pending 任务
        async with AsyncSessionLocal() as session:
            msg = GatewayMessage(
                agent_id=agent_id,
                content=task,
                execution_id=execution_id,
                status="pending",
            )
            session.add(msg)
            await session.commit()
            await session.refresh(msg)
            message_id = msg.id

        # 2. 订阅 Redis 频道等待结果
        channel = f"gateway:result:{execution_id}"
        pubsub = None
        try:
            from app.core.redis_client import get_redis
            r = await get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(channel)
        except Exception:
            pubsub = None

        # 3. 等待 report，同时 DB 轮询兜底（每 3 秒）
        deadline = asyncio.get_event_loop().time() + timeout
        result_text: str | None = None

        try:
            while asyncio.get_event_loop().time() < deadline:
                remaining = deadline - asyncio.get_event_loop().time()

                # 等 Redis 通知（最多 3 秒一次）
                if pubsub:
                    try:
                        msg_data = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True, timeout=3),
                            timeout=3.5,
                        )
                        if msg_data and msg_data.get("data"):
                            import json as _json
                            data = _json.loads(msg_data["data"])
                            result_text = data.get("result", "")
                            break
                    except (asyncio.TimeoutError, Exception):
                        pass

                # DB 轮询兜底
                async with AsyncSessionLocal() as session:
                    r2 = await session.execute(
                        select(GatewayMessage).where(GatewayMessage.id == message_id)
                    )
                    row = r2.scalar_one_or_none()
                    if row and row.status == "completed":
                        result_text = row.result or ""
                        break
                    if row and row.status == "failed":
                        return {"status": "error", "output": None, "error": row.error or "Agent reported failure"}
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                except Exception:
                    pass

        if result_text is None:
            return {"status": "error", "output": None,
                    "error": f"OpenClaw 节点在 {timeout}s 内未响应（节点可能离线或负载过高）"}

        return {"status": "completed", "output": result_text}

    async def execute_parallel(self, agent_ids: list, task: str, user_id: int,
                                context: Optional[Dict[str, Any]] = None) -> Dict[int, Dict[str, Any]]:
        """Execute task on multiple agents in parallel."""
        import asyncio
        tasks = [self.execute(agent_id, task, user_id, context=context)
                 for agent_id in agent_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            agent_id: results[i] if not isinstance(results[i], Exception) else {
                "status": "error", "error": str(results[i]),
            }
            for i, agent_id in enumerate(agent_ids)
        }
