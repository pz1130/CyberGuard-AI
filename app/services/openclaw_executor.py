"""OpenClaw sub-agent executor — Clawith /v1/responses API.

接入方式（3 步）:
  1. 在 Clawith 里创建一个 Agent，记下它的 Agent ID
  2. 在 Clawith 生成一个 API Key
  3. 在 CyberGuard 的 Sub-Agent 管理页面填入：
       - 端点 URL: http(s)://your-clawith-host:18789
       - OpenClaw Agent ID: Clawith 里的 Agent UUID
       - API Key: Clawith 生成的 key

Clawith API 文档: https://docs.openclaw.ai/gateway/openresponses-http-api
"""
import httpx
from typing import Any
from urllib.parse import urlparse

from app.config import settings

def _validate_url(url: str) -> None:
    """Raise ValueError if the URL is unsafe (SSRF protection)."""
    from app.core.ssrf import validate_outbound_url, SSRFError
    try:
        validate_outbound_url(url)
    except SSRFError as e:
        raise ValueError(str(e))


def _extract_text(data: dict) -> str:
    """Pull plain text out of a Clawith /v1/responses response body."""
    parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    parts.append(block.get("text", ""))
    return "\n".join(parts).strip()


async def execute(
    *,
    endpoint_url: str,
    api_key: str,
    openclaw_agent_id: str,
    task: str,
    max_output_tokens: int = 2000,
    max_tool_calls: int = 5,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Call Clawith and return a normalised result dict.

    Returns::
        {"status": "completed", "output": "<text>"}          # success
        {"status": "error",     "output": None, "error": "…"} # failure
    """
    base = endpoint_url.rstrip("/")
    try:
        _validate_url(base)
    except ValueError as e:
        return {"status": "error", "output": None, "error": str(e)}

    timeout = timeout or settings.SUB_AGENT_TIMEOUT

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/v1/responses",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "x-openclaw-agent-id": openclaw_agent_id,
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openclaw",
                    "input": task,
                    "stream": False,
                    "max_output_tokens": max_output_tokens,
                    "max_tool_calls": max_tool_calls,
                },
            )
    except httpx.TimeoutException:
        return {"status": "error", "output": None, "error": "Request timed out"}
    except httpx.ConnectError:
        return {"status": "error", "output": None, "error": f"Cannot connect to {base}"}
    except Exception as e:
        return {"status": "error", "output": None, "error": str(e)}

    if resp.status_code == 200:
        text = _extract_text(resp.json())
        return {"status": "completed", "output": text or resp.text}
    if resp.status_code == 401:
        return {"status": "error", "output": None, "error": "Invalid API key"}
    if resp.status_code == 403:
        return {"status": "needs_approval", "output": None, "error": "Approval required by Clawith"}
    return {"status": "error", "output": None, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}


async def test_connection(
    *,
    endpoint_url: str,
    api_key: str,
    openclaw_agent_id: str,
) -> dict[str, Any]:
    """Send a minimal request to verify credentials and connectivity.

    Returns::
        {"success": True,  "latency_ms": 120}
        {"success": False, "error": "…"}
    """
    import time
    t0 = time.monotonic()
    result = await execute(
        endpoint_url=endpoint_url,
        api_key=api_key,
        openclaw_agent_id=openclaw_agent_id,
        task="ping",
        max_output_tokens=10,
        max_tool_calls=0,
        timeout=10,
    )
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    if result["status"] in ("completed", "needs_approval"):
        return {"success": True, "latency_ms": latency_ms}
    return {"success": False, "error": result.get("error", "Unknown error"), "latency_ms": latency_ms}
