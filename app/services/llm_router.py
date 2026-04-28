"""LLM model routing service."""
import json
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI

from app.config import settings


def _get_providers_store():
    """Lazy import to avoid circular dependency."""
    from app.routers.providers import _providers as store
    return store


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

    def get_provider_config(self, provider_id: Optional[int] = None) -> Dict[str, Any]:
        """Get provider config by ID (from runtime providers store) or name."""
        if provider_id:
            store = _get_providers_store()
            provider_data = store.get(provider_id)
            if provider_data:
                return {
                    "name": provider_data.get("name"),
                    "api_key": provider_data.get("api_key", ""),
                    "base_url": provider_data.get("base_url", "https://api.openai.com/v1"),
                    "models": provider_data.get("models", []),
                }
        return None

    def get_client(self, provider_id: Optional[int] = None, provider_name: Optional[str] = None) -> AsyncOpenAI:
        """Get OpenAI client for a specific provider (by ID or name)."""
        # 1. Try by provider_id (runtime store)
        if provider_id:
            config = self.get_provider_config(provider_id)
            if config:
                return AsyncOpenAI(api_key=config["api_key"], base_url=config["base_url"])

        # 2. Try by provider_name
        if provider_name:
            provider = next((p for p in self.providers if p["name"] == provider_name), None)
            if provider:
                return AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])

        # 3. Fall back to first configured provider
        provider = self.providers[0]
        return AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])

    async def parse_intent(self, user_input: str, provider_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Parse user intent and create task plan.

        Uses the master agent model to understand user requirements
        and decompose into sub-agent tasks.
        """
        # Mock mode — return a simple general task plan without calling LLM
        if settings.MOCK_MODE:
            from app.services.local_executor import match_agent_type
            agent_type = match_agent_type(user_input) or "general"
            return {
                "intent": "task_execution",
                "task_plan": [{"agent_type": agent_type, "task": user_input, "requires_approval": False}],
                "reasoning": "Mock mode — intent parsed via keyword matching",
            }

        client = self.get_client(provider_id=provider_id)

        system_prompt = """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, group_chat, knowledge_query, admin_action]
- task_plan: array of {"agent_type": str, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

Task decomposition rules:
- Split compound requests into multiple tasks
- Each task maps to one agent_type
- Do NOT use agent_id — use agent_type only

agent_type options:
- threat_intel: threat IOC analysis, CVE lookup, malware analysis, APT tracking
- log_anomaly: log parsing, anomaly detection, SIEM alerts
- vuln_scanner: vulnerability scanning, CVE assessment, exploit analysis
- remediation: fix/remediate/mute/isolate/quarantine actions
- compliance: policy audit, framework compliance (ISO27001, GDPR, PCI-DSS)
- osint: open-source intelligence, recon, footprinting
- general: anything not matching above categories

Examples:
- "scan 192.168.1.0/24 for vulns" → agent_type: vuln_scanner
- "check if this IP is malicious" → agent_type: threat_intel
- "analyze firewall logs for anomalies" → agent_type: log_anomaly
- "block this domain" → agent_type: remediation
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
            # Fallback: match by keyword → single general task
            from app.services.local_executor import match_agent_type
            agent_type = match_agent_type(user_input) or "general"
            return {
                "intent": "task_execution",
                "task_plan": [{"agent_type": agent_type, "task": user_input, "requires_approval": False}],
                "reasoning": "Fallback parsing due to JSON error",
            }

    async def generate_summary(self, results: List[Dict[str, Any]], provider_id: Optional[int] = None) -> str:
        """Generate summary from sub-agent results."""
        # Mock mode — return a simple text summary
        if settings.MOCK_MODE:
            lines = [f"**{r.get('agent_name', 'Agent')}**:\n{r.get('output', 'No output')}" for r in results]
            return "📊 **CyberGuard 分析报告**\n\n" + "\n\n".join(lines) + "\n\n_此结果为 Mock 模式输出，配置真实 AI Provider 后可获得更智能的分析。_"

        client = self.get_client(provider_id=provider_id)

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

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
    ) -> str:
        """General chat completion."""
        # Mock mode — return a simple acknowledgment
        if settings.MOCK_MODE:
            last_msg = messages[-1]["content"] if messages else ""
            return f"🛡️ **CyberGuard (Mock Mode)**\n\n已收到您的消息：\"{last_msg[:100]}\"\n\n当前运行在 Mock 模式下，请配置真实的 AI Provider（Providers 页面）以获得实际的安全分析能力。"

        client = self.get_client(provider_id=provider_id)

        response = await client.chat.completions.create(
            model=model or settings.MASTER_AGENT_MODEL,
            messages=messages,
            temperature=settings.MASTER_AGENT_TEMPERATURE,
        )

        return response.choices[0].message.content

    async def embed(
        self,
        texts: List[str],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts via OpenAI-compatible /embeddings.

        Args:
            texts: list of strings to embed
            model: embedding model name (e.g. "text-embedding-3-small")
            provider_id: which configured provider to use

        Returns:
            list of embedding vectors, same order as input.
        """
        if not texts:
            return []

        client = self.get_client(provider_id=provider_id)
        embedding_model = model or "text-embedding-3-small"

        response = await client.embeddings.create(
            model=embedding_model,
            input=texts,
        )
        # response.data is sorted by index per OpenAI spec
        ordered = sorted(response.data, key=lambda d: d.index)
        return [item.embedding for item in ordered]


# Singleton instance
_llm_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Get or create LLM router singleton."""
    global _llm_router
    if _llm_router is None:
        _llm_router = LLMRouter()
    return _llm_router