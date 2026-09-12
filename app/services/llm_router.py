"""LLM model routing service.

M0a-1: pure helpers and resilience live in ``packages/llm_router``. This module
keeps DB/provider/master-config/PII wiring and business methods (parse_intent,
generate_summary, build_chat_system_prompt).
"""
import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI

from llm_router import acall_with_retry, rate_limit
from llm_router.utils import (
    extract_json_object as _extract_json_object_pure,
    model_name as _model_name,
    strip_think_blocks as _strip_think_blocks_pure,
)

logger = logging.getLogger(__name__)

from app.config import settings


def _record_generation(name, model, input_messages, output, response,
                       provider_id) -> None:
    """Best-effort Langfuse generation record. No-op unless Langfuse is set up."""
    try:
        from app.core.langfuse_tracing import record_generation
        record_generation(name=name, model=model, input=input_messages,
                          output=output, usage=getattr(response, "usage", None),
                          provider=str(provider_id) if provider_id else None)
    except Exception:  # noqa: BLE001 - tracing must never break an LLM call
        pass


class LLMRouter:
    """
    LLM model router supporting multiple providers.

    Uses litellm-style config for provider management.
    Supports OpenAI, Anthropic, and custom OpenAI-compatible endpoints.
    """

    def __init__(self):
        self.providers = []
        self._client_cache: dict[int | str, AsyncOpenAI] = {}
        self._master_config: Optional[dict] = None
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

    async def _load_master_config(self) -> dict:
        """Load master agent config from DB (cached)."""
        if self._master_config is not None:
            return self._master_config
        try:
            from app.core.database import get_db_context
            from app.services.master_config import get_master_config
            async with get_db_context() as session:
                config = await get_master_config(session)
                self._master_config = {
                    "provider_id": getattr(config, "llm_provider_id", None),
                    "model": getattr(config, "llm_model", None) or getattr(config, "model", None),
                    "temperature": config.temperature,
                    "system_prompt": config.system_prompt,
                    "intent_parser_prompt": config.intent_parser_prompt,
                    "summarizer_prompt": config.summarizer_prompt,
                }
        except Exception:
            self._master_config = {}
        return self._master_config or {}

    def invalidate_master_config_cache(self):
        """Invalidate cached master config (call after updates)."""
        self._master_config = None

    async def _get_agents_info(self) -> List[tuple]:
        """Fetch active sub-agents from DB for intent parser injection.

        Returns:
            List of (agent_name, endpoint_url, backend_type, description) tuples.
        """
        try:
            from app.core.database import get_db_context
            from sqlalchemy import select
            from app.models.agent import AgentConfig

            async with get_db_context() as session:
                result = await session.execute(
                    select(
                        AgentConfig.agent_name,
                        AgentConfig.endpoint_url,
                        AgentConfig.backend_type,
                        AgentConfig.description,
                    ).where(AgentConfig.is_active.is_(True))
                )
                rows = result.all()
                return [(r[0], r[1], r[2], r[3]) for r in rows]
        except Exception:
            return []

    async def build_chat_system_prompt(
        self,
        base_prompt: Optional[str] = None,
        mode: Optional[str] = None,
        expert_no_agents: bool = False,
    ) -> str:
        """Build the system prompt used by direct-chat replies (no sub-agent invoked).

        Combines:
          1. `base_prompt` (per-conversation override) or master_config.system_prompt or a fallback.
          2. A mode-aware sub-agent snapshot:
             - "fast": tell the LLM it's the only one answering (no agent listing).
             - "expert" + no agents: explain why fan-out didn't happen.
             - otherwise: list active sub-agents so meta-questions answer truthfully.

        Called by master.py `_summarizer_node` whenever it falls through to a
        direct LLM reply.
        """
        master_config = await self._load_master_config()
        prompt = (
            base_prompt
            or master_config.get("system_prompt")
            or "You are CyberGuard, a security operations assistant. Be precise and actionable."
        )

        m = (mode or "normal").lower()
        if m == "fast":
            prompt += (
                "\n\n## Mode\n"
                "You are running in **FAST mode**: respond directly without "
                "consulting any external sub-agent. Be concise."
            )
            return prompt

        if m == "expert" and expert_no_agents:
            prompt += (
                "\n\n## Mode\n"
                "You are running in **EXPERT mode**, but no external sub-agents "
                "are registered or active. You're answering as the Master Agent "
                "alone — explicitly tell the user this limitation in your reply."
            )
            return prompt

        agents = await self._get_agents_info()
        if not agents:
            prompt += (
                "\n\n## Sub-agents registered\n"
                "(None — no external sub-agents are currently registered or active.)"
            )
            return prompt

        lines = ["\n\n## Sub-agents registered (live snapshot)"]
        lines.append(
            "These external Sub-Agents are currently registered on this CyberGuard "
            "instance and can be dispatched by the Master Agent. When the user "
            "asks whether you can see / call a sub-agent by name, the answer is YES "
            "for any agent listed below."
        )
        for name, url, backend, desc in agents:
            descr = f" — {desc}" if desc else ""
            target = url or "(OpenClaw Gateway / no endpoint URL)"
            lines.append(f"- **{name}** [{backend}]{descr}  ⇢ {target}")
        lines.append(
            "\nIf the user mentions one of these agent names, you may answer "
            "from this list. To actually invoke a sub-agent the user must select "
            "it in the chat UI's AGENT dropdown, or phrase the request so the "
            "intent parser routes by name (e.g. \"ask test to ...\")."
        )
        return prompt + "\n".join(lines)

    def invalidate_provider_cache(self, provider_id: Optional[int] = None):
        """Invalidate cached OpenAI client(s).

        Call after a provider's API key or base_url is updated so the next
        request picks up the new credentials.

        Args:
            provider_id: invalidate only this provider's entry; if None,
                         clears the entire client cache.
        """
        if provider_id is None:
            self._client_cache.clear()
        else:
            self._client_cache.pop(provider_id, None)
            # The deterministic automatic selection may resolve to this same
            # provider, so its cached client must be refreshed as well.
            self._client_cache.pop("__default__", None)

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        """Remove provider-specific reasoning tags from visible output."""
        return _strip_think_blocks_pure(text)

    def _guard_messages(self, messages, pii_policy=None):
        """Redact PII + block secrets across all message contents (A5).

        Returns a NEW message list (originals untouched). Best-effort proof
        record; raises SecretsDetectedError/PIIBlockedError to abort the call.
        """
        from app.config import settings
        if not settings.PII_FILTER_ENABLED or not messages:
            return messages
        from app.core.pii import apply_policy
        policy = pii_policy or settings.PII_HANDLING_POLICY
        cleaned, total = [], 0
        for m in messages:
            content = m.get("content")
            if isinstance(content, str) and content:
                new_content, findings = apply_policy(content, policy=policy)
                total += len(findings)
                cleaned.append({**m, "content": new_content})
            else:
                cleaned.append(m)
        if total:
            self._emit_pii_proof(total, policy)
        return cleaned

    def _emit_pii_proof(self, count, policy):
        """POC proof: log redaction COUNT only — never the values."""
        try:
            import asyncio
            from app.core.audit import record_action
            asyncio.get_event_loop().create_task(record_action(
                user_id=None, action="pii_redaction", action_category="annotate",
                input_data={"policy": policy, "redactions": count},
                output_data={"redactions": count}))
        except Exception:
            import logging
            logging.getLogger("pii").info("pii_redaction policy=%s count=%d", policy, count)

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse the first balanced top-level JSON object from text."""
        return _extract_json_object_pure(text)

    async def _get_provider_from_db(self, provider_id: int) -> Optional[Dict[str, Any]]:
        """Fetch provider config from database by ID."""
        from app.core.database import get_db_context
        from app.core.ssrf import validate_outbound_url, SSRFError
        from sqlalchemy import text

        try:
            async with get_db_context() as session:
                result = await session.execute(
                    text(
                        "SELECT name, api_key_encrypted, base_url, models, metadata_json, provider_type "
                        "FROM providers WHERE id = :id AND is_active = true"
                    ),
                    {"id": provider_id}
                )
                row = result.fetchone()
                if not row:
                    return None

                api_key = ""
                if row[1]:
                    try:
                        from app.core.security import CredentialField, decrypt_data
                        api_key = decrypt_data(row[1], CredentialField.PROVIDER_API_KEY)
                    except Exception:
                        api_key = ""
                if not api_key:
                    return None

                base_url = row[2] or "https://api.openai.com/v1"
                try:
                    validate_outbound_url(base_url)
                except SSRFError as e:
                    logger.error(f"[llm_router] Provider {provider_id} base_url SSRF blocked: {e}")
                    return None

                models = row[3]
                if isinstance(models, str):
                    models = json.loads(models) if models else []
                elif not isinstance(models, list):
                    models = []

                return {
                    "name": row[0],
                    "api_key": api_key,
                    "base_url": base_url,
                    "models": models,
                    "metadata_json": row[4] or {},
                    "provider_type": row[5],
                }
        except Exception:
            return None

    def get_provider_config(self, provider_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get provider config by ID (from DB) or name."""
        if provider_id:
            # Sync wrapper — in an async context, use _get_provider_from_db instead
            return None  # Will be called asynchronously via get_client
        return None

    async def get_provider_config_async(self, provider_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get provider config by ID from DB, or by name from config."""
        if provider_id:
            db_config = await self._get_provider_from_db(provider_id)
            if db_config:
                return db_config

        return None

    async def _provider_rpm(self, provider_id: Optional[int]):
        """Per-provider requests-per-minute limit from metadata_json, or None (no limit)."""
        if not provider_id:
            return None
        cfg = await self.get_provider_config_async(provider_id)
        if not cfg:
            return None
        return (cfg.get("metadata_json") or {}).get("rate_limit_rpm")

    async def _get_first_active_provider(self) -> Optional[Dict[str, Any]]:
        """Fetch the first active provider from DB (for default routing)."""
        from app.core.database import get_db_context
        from app.core.ssrf import validate_outbound_url, SSRFError

        try:
            async with get_db_context() as session:
                from sqlalchemy import text
                result = await session.execute(
                    text(
                        "SELECT name, api_key_encrypted, base_url, models, metadata_json "
                        "FROM providers "
                        "WHERE is_active = true "
                        "AND api_key_encrypted IS NOT NULL "
                        "AND base_url IS NOT NULL AND base_url <> '' "
                        "AND json_array_length(COALESCE(models, '[]'::json)) > 0 "
                        "ORDER BY updated_at DESC, id ASC LIMIT 1"
                    )
                )
                row = result.fetchone()
                if not row:
                    return None

                api_key = ""
                if row[1]:
                    try:
                        from app.core.security import CredentialField, decrypt_data
                        api_key = decrypt_data(row[1], CredentialField.PROVIDER_API_KEY)
                    except Exception:
                        api_key = ""

                base_url = row[2] or "https://api.openai.com/v1"
                if not api_key:
                    return None
                try:
                    validate_outbound_url(base_url)
                except SSRFError as e:
                    logger.error(f"[llm_router] Default provider base_url SSRF blocked: {e}")
                    return None

                models = row[3]
                if isinstance(models, str):
                    models = json.loads(models) if models else []
                elif not isinstance(models, list):
                    models = []

                return {
                    "name": row[0],
                    "api_key": api_key,
                    "base_url": base_url,
                    "models": models,
                    "metadata_json": row[4] or {},
                }
        except Exception:
            return None

    async def _should_strip_think(self, provider_id: Optional[int]) -> bool:
        """
        Provider-level switch:
        - default: strip think tags
        - metadata_json.preserve_think = true: keep think tags
        """
        if not provider_id:
            return True
        config = await self.get_provider_config_async(provider_id)
        metadata = (config or {}).get("metadata_json") or {}
        return not bool(metadata.get("preserve_think"))

    def get_client(self, provider_id: Optional[int] = None, provider_name: Optional[str] = None) -> AsyncOpenAI:
        """Get OpenAI client for a specific provider (by ID or name)."""
        # Note: This is synchronous and uses cached providers list.
        # For DB-backed providers, use get_client_async instead.

        # 1. Try by provider_name
        if provider_name:
            provider = next((p for p in self.providers if p["name"] == provider_name), None)
            if provider:
                return AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])

        # 2. Fall back to first configured environment provider
        provider = next((item for item in self.providers if item.get("api_key")), None)
        if provider is None:
            raise RuntimeError("No environment-configured AI provider is available.")
        return AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])

    async def get_client_async(self, provider_id: Optional[int] = None, provider_name: Optional[str] = None) -> AsyncOpenAI:
        """Async version: get OpenAI client, fetching provider config from DB if needed."""
        cache_key = provider_id if provider_id else (provider_name or "__default__")

        # Check cache first
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        # 1. Try by provider_id (DB)
        if provider_id:
            config = await self.get_provider_config_async(provider_id)
            if config and config.get("api_key"):
                client = AsyncOpenAI(api_key=config["api_key"], base_url=config["base_url"])
                self._client_cache[cache_key] = client
                return client
            raise RuntimeError(
                "The selected AI provider is inactive, missing, or has no usable API key."
            )

        # 2. Try by provider_name (config)
        if provider_name:
            provider = next((p for p in self.providers if p["name"] == provider_name), None)
            if provider:
                client = AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])
                self._client_cache[cache_key] = client
                return client

        # 3. Prefer a configured DB provider. Selection is deterministic and
        # excludes seeded placeholders with no credential.
        default_provider = await self._get_first_active_provider()
        if default_provider:
            client = AsyncOpenAI(api_key=default_provider["api_key"], base_url=default_provider["base_url"])
            self._client_cache[cache_key] = client
            return client

        # 4. Environment-configured providers are a deployment fallback, but
        # empty placeholder keys are never considered configured.
        provider = next((item for item in self.providers if item.get("api_key")), None)
        if provider:
            client = AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])
            self._client_cache[cache_key] = client
            return client

        raise RuntimeError(
            "No configured AI provider is available. Configure and verify a provider first."
        )

    async def _record_token_usage(self, model_name: str, provider_id: Optional[int], response: Any) -> None:
        """Record token usage from an LLM response."""
        try:
            usage = getattr(response, "usage", None)
            if not usage:
                return

            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)

            if prompt_tokens <= 0 and completion_tokens <= 0:
                return

            from app.core.database import get_db_context
            from app.services.token_usage_service import TokenUsageService

            async with get_db_context() as session:
                provider_name = f"Provider-{provider_id}" if provider_id else "default"
                if provider_id:
                    provider_name = await TokenUsageService.get_provider_name(session, provider_id)
                await TokenUsageService.record_usage(
                    db=session,
                    provider_id=provider_id or 0,
                    provider_name=provider_name,
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
        except Exception:
            # Don't fail the main request if token recording fails
            logger.warning("[llm_router] Failed to record token usage", exc_info=True)

    async def parse_intent(
        self,
        user_input: str,
        provider_id: Optional[int] = None,
        model: Optional[str] = None,
        intent_parser_prompt_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        model_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parse user intent and create task plan.

        Uses the master agent model to understand user requirements
        and decompose into sub-agent tasks.
        """
        from app.core.telemetry import get_tracer
        tracer = get_tracer()

        # Mock mode — return a simple general task plan without calling LLM
        if settings.MOCK_MODE:
            from app.services.local_executor import match_agent_type
            agent_type = match_agent_type(user_input) or "general"
            return {
                "intent": "task_execution",
                "task_plan": [{"agent_type": agent_type, "task": user_input, "requires_approval": False}],
                "reasoning": "Mock mode — intent parsed via keyword matching",
            }

        master_config = await self._load_master_config()
        active_provider_id = provider_id or master_config.get("provider_id")
        client = await self.get_client_async(provider_id=active_provider_id)
        active_model = _model_name(model_override or model or master_config.get("model") or settings.MASTER_AGENT_MODEL)

        # Load available sub-agents from DB to include in prompt
        agents_info = await self._get_agents_info()

        # Use per-conversation override if provided, else global config
        system_prompt = (
            intent_parser_prompt_override
            or master_config.get("intent_parser_prompt")
            or """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, knowledge_query, admin_action]
- task_plan: array of {"agent_type": str, "agent_name": str, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

Task decomposition rules:
- Split compound requests into multiple tasks
- Each task maps to one agent_type or one agent_name
- If user mentions a specific agent by name, use agent_name to route directly to that agent
- Do NOT use agent_id — use agent_name or agent_type only

agent_type options (fallback when no specific agent is mentioned):
- threat_intel: threat IOC analysis, CVE lookup, malware analysis, APT tracking
- log_anomaly: log parsing, anomaly detection, SIEM alerts
- vuln_scanner: vulnerability scanning, CVE assessment, exploit analysis
- remediation: fix/remediate/mute/isolate/quarantine actions
- osint: open-source intelligence, recon, footprinting
- general: anything not matching above categories

Examples:
- "scan 192.168.1.0/24 for vulns" → agent_type: vuln_scanner
- "check if this IP is malicious" → agent_type: threat_intel
- "analyze firewall logs for anomalies" → agent_type: log_anomaly
- "block this domain" → agent_type: remediation
- "ask 1p to do something" → agent_name: "1p" (use this to route to the named sub-agent)
"""
        )

        # Append available agents to system prompt so LLM knows which agents exist
        if agents_info:
            agents_list = "\n".join(
                f'- agent_name: "{name}", endpoint: {url or "none"}, backend: {backend}'
                for name, url, backend, _desc in agents_info
            )
            system_prompt += f"\n\nAvailable sub-agents in this system:\n{agents_list}\n"
            system_prompt += '\nIf user asks about or mentions a specific agent by name (e.g. "1p", "test"), use agent_name to route to it.'
        span_name = f"llm.chat parse_intent/{active_model}"
        with tracer.start_as_current_span(span_name, attributes={
            "llm.model": active_model,
            "llm.operation": "chat",
            "llm.user_input_length": len(user_input),
        }) as span:
            try:
                await rate_limit(active_provider_id, await self._provider_rpm(active_provider_id))
                _pi_messages = self._guard_messages([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ])
                response = await acall_with_retry(lambda: client.chat.completions.create(
                    model=active_model,
                    messages=_pi_messages,
                    temperature=temperature_override if temperature_override is not None else (master_config.get("temperature") or settings.MASTER_AGENT_TEMPERATURE),
                    response_format={"type": "json_object"},
                ), label="parse_intent")
                content = response.choices[0].message.content or ""
                span.set_attribute("llm.response_length", len(content))
                span.set_attribute("llm.finish_reason", response.choices[0].finish_reason)

                # Record token usage
                await self._record_token_usage(active_model, active_provider_id, response)
                _record_generation(
                    "parse_intent", active_model,
                    [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_input}],
                    content, response, active_provider_id)

                parsed = self._extract_json_object(content)
                if parsed is not None:
                    return parsed
                raise json.JSONDecodeError("Failed to parse JSON from provider response", content, 0)
            except json.JSONDecodeError:
                from app.services.local_executor import match_agent_type
                agent_type = match_agent_type(user_input) or "general"
                return {
                    "intent": "task_execution",
                    "task_plan": [{"agent_type": agent_type, "task": user_input, "requires_approval": False}],
                    "reasoning": "Fallback parsing due to JSON error",
                }

    async def generate_summary(
        self,
        results: List[Dict[str, Any]],
        provider_id: Optional[int] = None,
        summarizer_prompt_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        model_override: Optional[str] = None,
    ) -> str:
        """Generate summary from sub-agent results."""
        from app.core.telemetry import get_tracer
        tracer = get_tracer()

        # Mock mode — return a simple text summary
        if settings.MOCK_MODE:
            lines = [f"**{r.get('agent_name', 'Agent')}**:\n{r.get('output', 'No output')}" for r in results]
            return "📊 **CyberGuard 分析报告**\n\n" + "\n\n".join(lines) + "\n\n_此结果为 Mock 模式输出，配置真实 AI Provider 后可获得更智能的分析。_"

        # Get model from config (before span so active_model is defined)
        master_config = await self._load_master_config()
        active_provider_id = provider_id or master_config.get("provider_id")
        client = await self.get_client_async(provider_id=active_provider_id)
        active_model = (
            model_override
            or master_config.get("model")
            or settings.MASTER_AGENT_MODEL
        )
        if not active_model and active_provider_id:
            provider_config = await self.get_provider_config_async(active_provider_id)
            if provider_config and provider_config.get("models"):
                active_model = provider_config["models"][0]
        active_model = _model_name(active_model)

        results_text = "\n".join([
            f"Agent {r.get('agent_name', 'unknown')}: {r.get('output', 'No output')}"
            for r in results
        ])

        with tracer.start_as_current_span(
            f"llm.chat generate_summary/{active_model}",
            attributes={
                "llm.model": active_model,
                "llm.operation": "chat",
                "llm.num_results": len(results),
                "llm.provider_id": active_provider_id,
            },
        ) as span:
            summarizer_prompt = (
                summarizer_prompt_override
                or master_config.get("summarizer_prompt")
                or "You are CyberGuard's summarizer. Create a concise summary of agent results."
            )

            await rate_limit(active_provider_id, await self._provider_rpm(active_provider_id))
            _gs_messages = self._guard_messages([
                {"role": "system", "content": summarizer_prompt},
                {"role": "user", "content": f"Results:\n{results_text}"},
            ])
            response = await acall_with_retry(lambda: client.chat.completions.create(
                model=active_model,
                messages=_gs_messages,
                temperature=temperature_override if temperature_override is not None else (master_config.get("temperature") or 0.3),
            ), label="generate_summary")
            raw_content = response.choices[0].message.content or ""
            content = (
                self._strip_think_blocks(raw_content)
                if await self._should_strip_think(active_provider_id)
                else raw_content
            )
            span.set_attribute("llm.response_length", len(content))

            # Record token usage
            await self._record_token_usage(active_model, active_provider_id, response)
            _record_generation(
                "generate_summary", active_model,
                [{"role": "system", "content": summarizer_prompt},
                 {"role": "user", "content": f"Results:\n{results_text}"}],
                content, response, active_provider_id)

            return content

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        pii_policy: Optional[str] = None,
        thinking: Optional[str] = None,
        enable_prompt_cache: bool = False,
        prompt_cache_key: Optional[str] = None,
    ):
        """General chat completion.

        Returns:
            - str (final text) when `tools` is None — backward-compatible.
            - openai ChatCompletionMessage when `tools` is provided, so callers
              can inspect `.tool_calls`.

        M0a-2 extras:
            thinking — portable level off|minimal|low|medium|high|xhigh
            enable_prompt_cache — mark system content for Anthropic-style cache
            prompt_cache_key — optional OpenAI-style cache routing key
        """
        from app.core.telemetry import get_tracer
        from llm_router.cache_control import apply_prompt_cache_key, mark_system_for_cache
        from llm_router.thinking import apply_thinking_to_kwargs
        from agent_core.messages import messages_for_model

        tracer = get_tracer()

        master_config = await self._load_master_config()

        # Determine active provider/model. Explicit conversation or request
        # values win; otherwise use the validated Master Agent selection.
        active_provider_id = provider_id or master_config.get("provider_id")
        active_model = model_override or model or master_config.get("model")
        provider_config = None
        if not active_model and active_provider_id:
            provider_config = await self.get_provider_config_async(active_provider_id)
            if provider_config and provider_config.get("models"):
                active_model = provider_config["models"][0]
        active_model = _model_name(active_model or settings.MASTER_AGENT_MODEL)

        # Drop exclude_from_context before any provider call (M0a-2)
        messages = messages_for_model(messages)

        # Mock mode — return a simple acknowledgment
        if settings.MOCK_MODE:
            last_msg = messages[-1]["content"] if messages else ""
            mock_text = f"🛡️ **CyberGuard (Mock Mode)**\n\n已收到您的消息：\"{last_msg[:100]}\"\n\n当前运行在 Mock 模式下，请配置真实的 AI Provider（Providers 页面）以获得实际的安全分析能力。"
            if tools:
                return SimpleNamespace(content=mock_text, tool_calls=None)
            return mock_text

        client = await self.get_client_async(provider_id=active_provider_id)
        if provider_config is None and active_provider_id:
            provider_config = await self.get_provider_config_async(active_provider_id)
        provider_type = (provider_config or {}).get("provider_type") or (
            provider_config or {}
        ).get("name")

        with tracer.start_as_current_span(
            f"llm.chat/{active_model}",
            attributes={
                "llm.model": active_model,
                "llm.operation": "chat",
                "llm.num_messages": len(messages),
                "llm.has_tools": bool(tools),
            },
        ) as span:
            messages = self._guard_messages(messages, pii_policy)
            if enable_prompt_cache:
                messages = mark_system_for_cache(
                    messages, provider_type=str(provider_type or ""), enabled=True
                )
            kwargs = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature_override if temperature_override is not None else (master_config.get("temperature") or settings.MASTER_AGENT_TEMPERATURE),
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            # Thinking / reasoning effort (portable level → provider params)
            thinking_level = thinking or (master_config or {}).get("thinking_level")
            kwargs = apply_thinking_to_kwargs(
                kwargs,
                level=thinking_level,
                model=active_model or "",
                provider_type=str(provider_type or ""),
            )
            kwargs = apply_prompt_cache_key(kwargs, cache_key=prompt_cache_key)

            await rate_limit(active_provider_id, await self._provider_rpm(active_provider_id))
            response = await acall_with_retry(
                lambda: client.chat.completions.create(**kwargs), label="chat")
            message = response.choices[0].message
            raw_content = message.content or ""
            content = (
                self._strip_think_blocks(raw_content)
                if await self._should_strip_think(active_provider_id)
                else raw_content
            )
            span.set_attribute("llm.response_length", len(content))
            span.set_attribute("llm.finish_reason", response.choices[0].finish_reason)
            await self._record_token_usage(active_model, active_provider_id, response)
            _record_generation("chat", active_model, messages, content,
                               response, active_provider_id)

            if tools:
                return SimpleNamespace(content=content, tool_calls=message.tool_calls)
            return content

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        pii_policy: Optional[str] = None,
    ):
        """Stream chat completion tokens as an async generator.

        Yields string chunks as they arrive from the provider.
        Usage::
            async for chunk in router.stream_chat(messages, provider_id=1):
                yield f"data: {chunk}\\n\\n"
        """
        messages = self._guard_messages(messages, pii_policy)
        master_config = await self._load_master_config()
        active_provider_id = provider_id or master_config.get("provider_id")
        active_model = model_override or model or master_config.get("model")
        if not active_model and active_provider_id:
            config = await self.get_provider_config_async(active_provider_id)
            if config and config.get("models"):
                active_model = config["models"][0]
        active_model = _model_name(active_model or settings.MASTER_AGENT_MODEL)

        if settings.MOCK_MODE:
            last_msg = messages[-1]["content"] if messages else ""
            mock = (
                f"🛡️ **CyberGuard (Mock Mode)**\n\n"
                f"已收到您的消息：\"{last_msg[:100]}\"\n\n"
                "当前运行在 Mock 模式下，请配置真实 AI Provider。"
            )
            for word in mock.split(" "):
                yield word + " "
                await asyncio.sleep(0.02)
            return

        client = await self.get_client_async(provider_id=active_provider_id)
        temperature = (
            temperature_override
            if temperature_override is not None
            else (master_config.get("temperature") or settings.MASTER_AGENT_TEMPERATURE)
        )

        accumulated = []
        usage_response = None
        try:
            await rate_limit(active_provider_id, await self._provider_rpm(active_provider_id))
            # Retry only the connection/handshake; mid-stream failures are not retried.
            stream_kwargs = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            try:
                stream = await acall_with_retry(
                    lambda: client.chat.completions.create(**stream_kwargs),
                    label="stream_chat",
                )
            except Exception as exc:
                # Some OpenAI-compatible endpoints reject stream_options. Keep
                # streaming functional, but usage cannot be recorded for those
                # providers unless they include it without being asked.
                if getattr(exc, "status_code", None) not in {400, 422}:
                    raise
                stream_kwargs.pop("stream_options")
                logger.warning(
                    "[llm_router] Provider rejected stream usage reporting; "
                    "retrying without stream_options"
                )
                stream = await acall_with_retry(
                    lambda: client.chat.completions.create(**stream_kwargs),
                    label="stream_chat_compat",
                )
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage_response = chunk
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    accumulated.append(delta)
                    yield delta
        except Exception as e:
            yield f"\n\n[错误: {e}]"
            return

        full = "".join(accumulated)
        if usage_response is not None:
            await self._record_token_usage(active_model, active_provider_id, usage_response)
        _record_generation("stream_chat", active_model, messages, full,
                           usage_response, active_provider_id)

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

        client = await self.get_client_async(provider_id=provider_id)
        embedding_model = model or "text-embedding-3-small"

        response = await client.embeddings.create(
            model=embedding_model,
            input=texts,
        )
        await self._record_token_usage(embedding_model, provider_id, response)
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
