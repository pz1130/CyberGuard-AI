"""OpenClaw sub-agent executor wrapper."""
import httpx
import json
import asyncio
from typing import Dict, Any, Optional, List, AsyncIterator
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

from app.config import settings
from app.core.security import decrypt_data


class OpenClawAuthMode(str, Enum):
    """OpenClaw authentication modes."""
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"


class OpenClawExecutor:
    """
    Executor for OpenClaw-compatible remote agents.

    OpenClaw agents are external AI agents that advertise their capabilities
    and can be called via a OpenAI-compatible API with tool support.
    """

    def __init__(self, agent_config: Dict[str, Any]):
        self.agent_id = agent_config.get("id")
        self.agent_name = agent_config.get("agent_name")
        self.endpoint_url = agent_config.get("endpoint_url", "").rstrip("/")
        # api_key may come direct or from metadata_json (encrypted)
        self.api_key = agent_config.get("api_key") or ""
        if not self.api_key and agent_config.get("metadata_json"):
            meta = agent_config.get("metadata_json", {})
            encrypted_key = meta.get("api_key", "")
            if encrypted_key:
                try:
                    self.api_key = decrypt_data(encrypted_key)
                except Exception:
                    self.api_key = ""
        # auth_mode and streaming from direct config or metadata_json
        metadata = agent_config.get("metadata_json", {}) or {}
        auth_mode_str = agent_config.get("auth_mode") or metadata.get("auth_mode", "api_key")
        streaming_val = agent_config.get("streaming")
        if streaming_val is None:
            streaming_val = metadata.get("streaming", True)
        self.auth_mode = OpenClawAuthMode(auth_mode_str)
        self.capabilities: List[Dict[str, Any]] = agent_config.get("capabilities", [])
        self.streaming_enabled = streaming_val
        self.timeout = agent_config.get("timeout", settings.SUB_AGENT_TIMEOUT)

        # Decrypt environment variables if present
        self.env_vars: Dict[str, str] = {}
        env_encrypted = agent_config.get("env_vars_encrypted")
        if env_encrypted:
            try:
                self.env_vars = json.loads(decrypt_data(env_encrypted))
            except Exception:
                self.env_vars = {}

        # Parse and validate endpoint
        self._validated = False
        self._error: Optional[str] = None

    def _validate(self) -> bool:
        """Validate endpoint URL (SSRF protection)."""
        if self._validated:
            return self._error is None

        self._validated = True
        if not self.endpoint_url:
            self._error = "No endpoint configured"
            return False

        try:
            parsed = urlparse(self.endpoint_url)
            scheme = parsed.scheme.lower()
            if scheme not in ("http", "https"):
                self._error = f"Invalid scheme: {scheme}"
                return False
            hostname = parsed.hostname or ""
            # Block metadata IP ranges
            blocked = {"169.254.169.254", "metadata.google.internal",
                      "metadata.internal", "metadata.azure.com",
                      "localhost", "127.0.0.1", "0.0.0.0"}
            if hostname in blocked:
                self._error = f"Blocked host: {hostname}"
                return False
            # Block private ranges
            if hostname.startswith(("10.", "172.16.", "172.17.", "172.18.",
                                     "172.19.", "172.20.", "172.21.", "172.22.",
                                     "172.23.", "172.24.", "172.25.", "172.26.",
                                     "172.27.", "172.28.", "172.29.", "172.30.",
                                     "172.31.", "192.168.")):
                self._error = f"Blocked private range: {hostname}"
                return False
            return True
        except Exception as e:
            self._error = str(e)
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers including auth."""
        headers = {
            "Content-Type": "application/json",
            "X-Agent-ID": str(self.agent_id),
            "X-Timestamp": datetime.utcnow().isoformat(),
        }
        if self.auth_mode == OpenClawAuthMode.API_KEY and self.api_key:
            headers["X-API-Key"] = self.api_key
        elif self.auth_mode == OpenClawAuthMode.BEARER and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _make_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Make HTTP request with SSRF validation."""
        if not self._validate():
            raise ValueError(self._error)

        parsed = urlparse(self.endpoint_url)
        verify_certs = parsed.scheme == "https"
        url = f"{self.endpoint_url}{path}"

        async with httpx.AsyncClient(timeout=self.timeout, verify=verify_certs) as client:
            if method == "GET":
                return await client.get(url, headers=self._get_headers(), params=params)
            elif method == "POST":
                return await client.post(url, headers=self._get_headers(), json=json_data)
            else:
                raise ValueError(f"Unsupported method: {method}")

    async def get_capabilities(self) -> Dict[str, Any]:
        """
        Fetch agent capabilities/tools from the OpenClaw agent.

        Returns dict with:
        - success: bool
        - capabilities: list of tool definitions
        - model: model name used by the agent
        """
        if not self._validate():
            return {"success": False, "error": self._error, "capabilities": []}

        try:
            response = await self._make_request("GET", "/capabilities")
            if response.status_code == 200:
                data = response.json()
                self.capabilities = data.get("capabilities", [])
                return {
                    "success": True,
                    "capabilities": self.capabilities,
                    "model": data.get("model", "unknown"),
                    "agent_name": data.get("agent_name", self.agent_name),
                }
            return {"success": False, "error": f"Status {response.status_code}", "capabilities": []}
        except Exception as e:
            return {"success": False, "error": str(e), "capabilities": []}

    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task on the OpenClaw agent.

        Args:
            task: Task description/instruction
            context: Additional context (user_id, session_id, etc.)
            tools: Optional list of tool definitions to expose to the agent
            system_prompt: Optional system prompt override

        Returns:
            Result dict with status, output, error
        """
        if not self._validate():
            return {"status": "error", "output": None, "error": self._error}

        payload = {
            "task": task,
            "context": context or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        if self.env_vars:
            payload["env_vars"] = self.env_vars
        if tools:
            payload["tools"] = tools
        if system_prompt:
            payload["system_prompt"] = system_prompt

        try:
            response = await self._make_request("POST", "/execute", json_data=payload)
            if response.status_code == 200:
                result = response.json()
                return {
                    "status": "completed",
                    "output": result.get("output"),
                    "execution_time": result.get("execution_time", 0),
                    "tool_calls": result.get("tool_calls", []),
                }
            elif response.status_code == 401:
                return {"status": "error", "output": None, "error": "Authentication failed"}
            elif response.status_code == 403:
                return {"status": "needs_approval", "output": None, "error": "Approval required"}
            else:
                return {"status": "error", "output": None, "error": f"Status {response.status_code}"}
        except httpx.TimeoutException:
            return {"status": "error", "output": None, "error": "Timeout"}
        except Exception as e:
            return {"status": "error", "output": None, "error": str(e)}

    async def execute_stream(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a task with streaming response.

        Yields dict chunks with:
        - chunk: text chunk from the response
        - tool_call: optional tool call notification
        - status: optional status update
        """
        if not self._validate():
            yield {"type": "error", "error": self._error}
            return

        if not self.streaming_enabled:
            # Fall back to non-streaming
            result = await self.execute(task, context, tools)
            if result["status"] == "completed":
                yield {"type": "content", "content": result.get("output", "")}
            else:
                yield {"type": "error", "error": result.get("error", "Unknown error")}
            return

        payload = {
            "task": task,
            "context": context or {},
            "stream": True,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if self.env_vars:
            payload["env_vars"] = self.env_vars
        if tools:
            payload["tools"] = tools

        try:
            parsed = urlparse(self.endpoint_url)
            verify_certs = parsed.scheme == "https"
            url = f"{self.endpoint_url}/execute"
            async with httpx.AsyncClient(timeout=self.timeout, verify=verify_certs) as client:
                async with client.stream("POST", url, headers=self._get_headers(), json=payload) as response:
                    if response.status_code != 200:
                        yield {"type": "error", "error": f"Status {response.status_code}"}
                        return

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                if "chunk" in chunk:
                                    yield {"type": "content", "content": chunk["chunk"]}
                                elif "tool_call" in chunk:
                                    yield {"type": "tool_call", "tool_call": chunk["tool_call"]}
                                elif "status" in chunk:
                                    yield {"type": "status", "status": chunk["status"]}
                            except json.JSONDecodeError:
                                continue
                        elif line.startswith("event:"):
                            event_type = line[6:].strip()
                            yield {"type": "event", "event": event_type}
        except Exception as e:
            yield {"type": "error", "error": str(e)}

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to the OpenClaw agent."""
        if not self._validate():
            return {"success": False, "error": self._error}

        try:
            response = await self._make_request("GET", "/health")
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "data": data,
                    "version": data.get("version", "unknown"),
                    "model": data.get("model", "unknown"),
                }
            elif response.status_code == 401:
                return {"success": False, "error": "Authentication required"}
            else:
                return {"success": False, "error": f"Health check failed: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_status(self) -> Dict[str, Any]:
        """Get agent status and load."""
        if not self._validate():
            return {"status": "offline", "error": self._error}

        try:
            response = await self._make_request("GET", "/status")
            if response.status_code == 200:
                return response.json()
            return {"status": "unknown", "code": response.status_code}
        except Exception as e:
            return {"status": "offline", "error": str(e)}


class HermesExecutor:
    """
    Executor for Hermes-compatible remote agents.

    Hermes is a lightweight agent protocol with simpler API than OpenClaw.
    """

    def __init__(self, agent_config: Dict[str, Any]):
        self.agent_id = agent_config.get("id")
        self.agent_name = agent_config.get("agent_name")
        self.endpoint_url = agent_config.get("endpoint_url", "").rstrip("/")
        self.api_key = agent_config.get("api_key") or ""
        self.timeout = agent_config.get("timeout", settings.SUB_AGENT_TIMEOUT)
        # Decrypt environment variables if present
        self.env_vars: Dict[str, str] = {}
        env_encrypted = agent_config.get("env_vars_encrypted")
        if env_encrypted:
            try:
                self.env_vars = json.loads(decrypt_data(env_encrypted))
            except Exception:
                self.env_vars = {}

    def _validate(self) -> bool:
        """Validate endpoint URL."""
        if not self.endpoint_url:
            return False
        try:
            parsed = urlparse(self.endpoint_url)
            return parsed.scheme in ("http", "https")
        except:
            return False

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute task on Hermes agent."""
        if not self._validate():
            return {"status": "error", "output": None, "error": "Invalid endpoint"}

        payload = {
            "task": task,
            "context": context or {},
        }
        if self.env_vars:
            payload["env_vars"] = self.env_vars

        try:
            parsed = urlparse(self.endpoint_url)
            verify_certs = parsed.scheme == "https"
            async with httpx.AsyncClient(timeout=self.timeout, verify=verify_certs) as client:
                response = await client.post(
                    f"{self.endpoint_url}/execute",
                    headers=self._get_headers(),
                    json=payload,
                )
                if response.status_code == 200:
                    return {
                        "status": "completed",
                        "output": response.json().get("output"),
                    }
                return {"status": "error", "output": None, "error": f"Status {response.status_code}"}
        except Exception as e:
            return {"status": "error", "output": None, "error": str(e)}

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to Hermes agent."""
        if not self._validate():
            return {"success": False, "error": "Invalid endpoint"}

        try:
            parsed = urlparse(self.endpoint_url)
            verify_certs = parsed.scheme == "https"
            async with httpx.AsyncClient(timeout=10, verify=verify_certs) as client:
                response = await client.get(f"{self.endpoint_url}/health", headers=self._get_headers())
                return {"success": response.status_code == 200, "status_code": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}


def get_executor_for_backend(agent_config: Dict[str, Any]):
    """
    Factory function to get the appropriate executor for a backend type.

    Args:
        agent_config: Agent configuration dict

    Returns:
        Executor instance (OpenClawExecutor, HermesExecutor, or SubAgentWrapper)
    """
    backend_type = agent_config.get("backend_type", "openclaw")

    if backend_type == "openclaw":
        return OpenClawExecutor(agent_config)
    elif backend_type == "hermes":
        return HermesExecutor(agent_config)
    else:
        # Fall back to basic HTTP executor for custom backends
        from app.services.agent_executor import SubAgentWrapper
        return SubAgentWrapper(agent_config)
