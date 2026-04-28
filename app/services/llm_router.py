"""LLM model routing service."""
import json
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI

from app.config import settings


class LLMRouter:
    """
    LLM model router supporting multiple providers.

    Uses litellm-style config for provider management.
    Supports OpenAI, Anthropic, and custom OpenAI-compatible endpoints.
    """

    def __init__(self):
        self.providers = []
        self._load_providers()

    def _load_providers(self):
        """Load providers from config."""
        for provider in settings.litellm_providers:
            self.providers.append({
                "name": provider.get("name"),
                "api_key": provider.get("api_key", ""),
                "base_url": provider.get("base_url", "https://api.openai.com/v1"),
                "models": provider.get("models", ["gpt-4o"]),
            })

        # Default to OpenAI if no providers configured
        if not self.providers:
            self.providers = [{
                "name": "openai",
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "models": ["gpt-4o"],
            }]

    def get_client(self, provider_name: Optional[str] = None) -> AsyncOpenAI:
        """Get OpenAI client for a specific provider."""
        provider = None
        if provider_name:
            provider = next((p for p in self.providers if p["name"] == provider_name), None)
        if not provider:
            provider = self.providers[0]

        return AsyncOpenAI(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
        )

    async def parse_intent(self, user_input: str) -> Dict[str, Any]:
        """
        Parse user intent and create task plan.

        Uses the master agent model to understand user requirements
        and decompose into sub-agent tasks.
        """
        client = self.get_client()

        system_prompt = """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, group_chat, knowledge_query, admin_action]
- task_plan: array of {"agent_id": null, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

For task_execution, identify which sub-agents are needed based on keywords:
- threat/cve/ioc -> Threat Intelligence Agent
- log/anomaly -> Log Anomaly Agent
- vuln/scan -> Vulnerability Scanner
- fix/remediate -> Remediation Advisor
- compliance/policy -> Compliance Checker
"""

        response = await client.chat.completions.create(
            model=settings.MASTER_AGENT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            temperature=settings.MASTER_AGENT_TEMPERATURE,
            response_format={"type": "json_object"},
        )

        try:
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            return {
                "intent": "task_execution",
                "task_plan": [{"agent_id": None, "task": user_input, "requires_approval": False}],
                "reasoning": "Fallback parsing due to JSON error",
            }

    async def generate_summary(self, results: List[Dict[str, Any]]) -> str:
        """Generate summary from sub-agent results."""
        client = self.get_client()

        results_text = "\n".join([
            f"Agent {r.get('agent_name', 'unknown')}: {r.get('output', 'No output')}"
            for r in results
        ])

        response = await client.chat.completions.create(
            model=settings.MASTER_AGENT_MODEL,
            messages=[
                {"role": "system", "content": "You are CyberGuard's summarizer. Create a concise summary of agent results."},
                {"role": "user", "content": f"Results:\n{results_text}"},
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content

    async def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        """General chat completion."""
        client = self.get_client()

        response = await client.chat.completions.create(
            model=model or settings.MASTER_AGENT_MODEL,
            messages=messages,
            temperature=settings.MASTER_AGENT_TEMPERATURE,
        )

        return response.choices[0].message.content


# Singleton instance
_llm_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Get or create LLM router singleton."""
    global _llm_router
    if _llm_router is None:
        _llm_router = LLMRouter()
    return _llm_router