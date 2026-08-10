"""N8N API integration service."""
import json
import re
import httpx
from typing import Dict, Any, Optional, List
from app.config import settings


N8N_WORKFLOW_GENERATION_PROMPT = """You are CyberGuard's N8N workflow generator. When asked to create a workflow:

1. Understand the user's automation goal in natural language
2. Design an N8N workflow JSON with appropriate nodes:
   - Trigger node (Webhook, Schedule, Manual, etc.)
   - Action nodes (HTTP Request, Code, IF, Switch, etc.)
   - Appropriate credentials configuration
3. Output the complete N8N workflow JSON structure

N8N Workflow JSON format:
{
  "name": "Workflow Name",
  "nodes": [
    {
      "id": "unique-node-id",
      "name": "Node Name",
      "type": "n8n-nodes-base.nodeType",
      "position": [x, y],
      "parameters": {...},
      "credentials": {...},
      "continueOnFail": false
    }
  ],
  "connections": {
    "Node Name": {
      "main": [[{"node": "Next Node Name", "type": "main", "index": 0}]]
    }
  },
  "settings": {
    "executionOrder": "v1"
  },
  "staticData": null,
  "tags": []
}

Important rules:
- Use real N8N node types like: "n8n-nodes-base.webhook", "n8n-nodes-base.httpRequest", "n8n-nodes-base.code", "n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.emailSend", "n8n-nodes-base.slack"
- Each node needs a unique id string
- Set appropriate positions for visual layout
- Return ONLY the JSON object, no markdown formatting, no explanation
"""


async def test_connection(base_url: str, api_key: str) -> Dict[str, Any]:
    """Test N8N connection by fetching workflow list."""
    headers = _get_headers(api_key)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/rest/workflows", headers=headers)
            if resp.status_code == 200:
                workflows = resp.json()
                return {"success": True, "workflow_count": len(workflows) if isinstance(workflows, list) else 0}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_workflows(base_url: str, api_key: str) -> List[Dict[str, Any]]:
    """List all workflows from N8N instance."""
    headers = _get_headers(api_key)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/rest/workflows", headers=headers)
        resp.raise_for_status()
        workflows = resp.json()
        return workflows if isinstance(workflows, list) else []


async def get_workflow(base_url: str, api_key: str, workflow_id: str) -> Dict[str, Any]:
    """Get a specific workflow by ID."""
    headers = _get_headers(api_key)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/rest/workflows/{workflow_id}", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def create_workflow(base_url: str, api_key: str, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new workflow in N8N."""
    headers = _get_headers(api_key)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/rest/workflows",
            headers=headers,
            json=workflow_data,
        )
        resp.raise_for_status()
        return resp.json()


async def update_workflow(
    base_url: str, api_key: str, workflow_id: str, workflow_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Update an existing workflow in N8N."""
    headers = _get_headers(api_key)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(
            f"{base_url.rstrip('/')}/rest/workflows/{workflow_id}",
            headers=headers,
            json=workflow_data,
        )
        resp.raise_for_status()
        return resp.json()


async def delete_workflow(base_url: str, api_key: str, workflow_id: str) -> bool:
    """Delete a workflow from N8N."""
    headers = _get_headers(api_key)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(
            f"{base_url.rstrip('/')}/rest/workflows/{workflow_id}",
            headers=headers,
        )
        return resp.status_code in (200, 204)


async def generate_workflow_json(description: str, llm_router) -> Dict[str, Any]:
    """Use LLM to generate N8N workflow JSON from natural language description.

    Args:
        description: Natural language description of the desired workflow
        llm_router: LLMRouter instance for making LLM calls

    Returns:
        Dict with 'workflow_json' and 'raw_llm_response'
    """
    messages = [
        {"role": "system", "content": N8N_WORKFLOW_GENERATION_PROMPT},
        {"role": "user", "content": f"Create an N8N workflow: {description}"},
    ]

    try:
        result = await llm_router.chat(
            messages=messages,
            temperature_override=0.3,  # Lower temp for more deterministic output
        )

        # Try to parse as JSON
        try:
            workflow_json = json.loads(result)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", result)
            if json_match:
                workflow_json = json.loads(json_match.group(1))
            else:
                # Try to find JSON object in text
                start = result.find("{")
                if start >= 0:
                    depth = 0
                    for i, ch in enumerate(result[start:], start):
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                workflow_json = json.loads(result[start:i+1])
                                break
                else:
                    workflow_json = {"error": "Could not parse workflow JSON", "raw": result}

        return {
            "workflow_json": workflow_json,
            "raw_llm_response": result,
        }
    except Exception as e:
        return {
            "workflow_json": {"error": str(e)},
            "raw_llm_response": "",
        }


def _get_headers(api_key: str) -> Dict[str, str]:
    """Get headers for N8N API requests."""
    return {
        "X-N8N_VERSION": "1.0",
        "Content-Type": "application/json",
    }
