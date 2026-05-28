"""LLM model routing service."""
import json
import re
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
        self._client_cache: dict[int, AsyncOpenAI] = {}
        self._client_cache_lock = __import__("asyncio").Lock()
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

        # Default to OpenAI if no providers configured
        if not self.providers:
            self.providers = [{
                "name": "openai",
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "models": ["gpt-4o"],
            }]

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
                    "model": config.model,
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
                    ).where(AgentConfig.is_active == True)
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

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        """Remove provider-specific reasoning tags from visible output."""
        if not text:
            return text
        return re.sub(r"<think>[\s\S]*?</think>\s*", "", text, flags=re.IGNORECASE).strip()

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        """
        Extract and parse the first balanced top-level JSON object from text.
        Handles provider outputs like: <think>...</think>{...json...}
        """
        cleaned = LLMRouter._strip_think_blocks(text)

        # Fast path: pure JSON
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        # Balanced-brace scan
        start = cleaned.find("{")
        if start < 0:
            return None
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        data = json.loads(candidate)
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        return None
        return None

    async def _get_provider_from_db(self, provider_id: int) -> Optional[Dict[str, Any]]:
        """Fetch provider config from database by ID."""
        from app.core.database import get_db_context
        from sqlalchemy import text

        try:
            async with get_db_context() as session:
                result = await session.execute(
                    text("SELECT name, api_key_encrypted, base_url, models, metadata_json FROM providers WHERE id = :id AND is_active = true"),
                    {"id": provider_id}
                )
                row = result.fetchone()
                if not row:
                    return None

                api_key = ""
                if row[1]:
                    try:
                        from app.core.security import decrypt_data
                        api_key = decrypt_data(row[1])
                    except Exception:
                        api_key = ""

                models = row[3]
                if isinstance(models, str):
                    models = json.loads(models) if models else []
                elif not isinstance(models, list):
                    models = []

                return {
                    "name": row[0],
                    "api_key": api_key,
                    "base_url": row[2] or "https://api.openai.com/v1",
                    "models": models,
                    "metadata_json": row[4] or {},
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

    async def _get_first_active_provider(self) -> Optional[Dict[str, Any]]:
        """Fetch the first active provider from DB (for default routing)."""
        from app.core.database import get_db_context

        try:
            async with get_db_context() as session:
                from sqlalchemy import text
                result = await session.execute(
                    text(
                        "SELECT name, api_key_encrypted, base_url, models, metadata_json "
                        "FROM providers WHERE is_active = true LIMIT 1"
                    )
                )
                row = result.fetchone()
                if not row:
                    return None

                api_key = ""
                if row[1]:
                    try:
                        from app.core.security import decrypt_data
                        api_key = decrypt_data(row[1])
                    except Exception:
                        api_key = ""

                models = row[3]
                if isinstance(models, str):
                    models = json.loads(models) if models else []
                elif not isinstance(models, list):
                    models = []

                return {
                    "name": row[0],
                    "api_key": api_key,
                    "base_url": row[2] or "https://api.openai.com/v1",
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

        # 2. Fall back to first configured provider
        provider = self.providers[0]
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
            if config:
                client = AsyncOpenAI(api_key=config["api_key"], base_url=config["base_url"])
                self._client_cache[cache_key] = client
                return client

        # 2. Try by provider_name (config)
        if provider_name:
            provider = next((p for p in self.providers if p["name"] == provider_name), None)
            if provider:
                client = AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])
                self._client_cache[cache_key] = client
                return client

        # 3. Try first litellm provider if available
        if self.providers:
            provider = self.providers[0]
            client = AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])
            self._client_cache[cache_key] = client
            return client

        # 4. Fall back to first active DB provider (no specific provider_id)
        default_provider = await self._get_first_active_provider()
        if default_provider:
            client = AsyncOpenAI(api_key=default_provider["api_key"], base_url=default_provider["base_url"])
            self._client_cache[cache_key] = client
            return client

        # 5. Last resort — use a placeholder that will fail with a clear error
        client = AsyncOpenAI(api_key="no-api-key-configured", base_url="https://api.openai.com/v1")
        self._client_cache[cache_key] = client
        return client

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

            provider_name = f"Provider-{provider_id}" if provider_id else "default"
            if provider_id:
                async with get_db_context() as session:
                    provider_name = await TokenUsageService.get_provider_name(session, provider_id)

            async with get_db_context() as session:
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
            pass

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

        client = await self.get_client_async(provider_id=provider_id)

        master_config = await self._load_master_config()
        active_model = model_override or model or master_config.get("model") or settings.MASTER_AGENT_MODEL

        # Load available sub-agents from DB to include in prompt
        agents_info = await self._get_agents_info()

        # Use per-conversation override if provided, else global config
        system_prompt = (
            intent_parser_prompt_override
            or master_config.get("intent_parser_prompt")
            or """You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, group_chat, knowledge_query, admin_action]
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
- compliance: policy audit, framework compliance (ISO27001, GDPR, PCI-DSS)
- osint: open-source intelligence, recon, footprinting
- n8n_workflow: generate n8n automation workflows from natural language
- general: anything not matching above categories

Examples:
- "scan 192.168.1.0/24 for vulns" → agent_type: vuln_scanner
- "check if this IP is malicious" → agent_type: threat_intel
- "analyze firewall logs for anomalies" → agent_type: log_anomaly
- "block this domain" → agent_type: remediation
- "create a n8n workflow to check my email every hour" → agent_type: n8n_workflow
- "帮我创建一个 n8n 工作流" → agent_type: n8n_workflow
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
                response = await client.chat.completions.create(
                    model=active_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input},
                    ],
                    temperature=temperature_override if temperature_override is not None else (master_config.get("temperature") or settings.MASTER_AGENT_TEMPERATURE),
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ""
                span.set_attribute("llm.response_length", len(content))
                span.set_attribute("llm.finish_reason", response.choices[0].finish_reason)

                # Record token usage
                await self._record_token_usage(active_model, provider_id, response)

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

        client = await self.get_client_async(provider_id=provider_id)

        # Get model from config (before span so active_model is defined)
        master_config = await self._load_master_config()
        active_model = (
            model_override
            or master_config.get("model")
            or settings.MASTER_AGENT_MODEL
        )
        if provider_id:
            provider_config = await self.get_provider_config_async(provider_id)
            if provider_config and provider_config.get("models"):
                active_model = provider_config["models"][0]

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
                "llm.provider_id": provider_id,
            },
        ) as span:
            summarizer_prompt = (
                summarizer_prompt_override
                or master_config.get("summarizer_prompt")
                or "You are CyberGuard's summarizer. Create a concise summary of agent results."
            )

            response = await client.chat.completions.create(
                model=active_model,
                messages=[
                    {"role": "system", "content": summarizer_prompt},
                    {"role": "user", "content": f"Results:\n{results_text}"},
                ],
                temperature=temperature_override if temperature_override is not None else (master_config.get("temperature") or 0.3),
            )
            raw_content = response.choices[0].message.content or ""
            strip_think = await self._should_strip_think(provider_id)
            content = self._strip_think_blocks(raw_content) if strip_think else raw_content
            span.set_attribute("llm.response_length", len(content))

            # Record token usage
            await self._record_token_usage(active_model, provider_id, response)

            return content

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """General chat completion.

        Returns:
            - str (final text) when `tools` is None — backward-compatible.
            - openai ChatCompletionMessage when `tools` is provided, so callers
              can inspect `.tool_calls`.
        """
        from app.core.telemetry import get_tracer
        tracer = get_tracer()

        # Determine active model
        active_model = model_override or model
        active_provider_id = provider_id
        if not active_model and provider_id:
            config = await self.get_provider_config_async(provider_id)
            if config and config.get("models"):
                active_model = config["models"][0]
        active_model = active_model or settings.MASTER_AGENT_MODEL

        master_config = await self._load_master_config()

        # Mock mode — return a simple acknowledgment
        if settings.MOCK_MODE:
            last_msg = messages[-1]["content"] if messages else ""
            mock_text = f"🛡️ **CyberGuard (Mock Mode)**\n\n已收到您的消息：\"{last_msg[:100]}\"\n\n当前运行在 Mock 模式下，请配置真实的 AI Provider（Providers 页面）以获得实际的安全分析能力。"
            if tools is not None:
                from types import SimpleNamespace
                return SimpleNamespace(content=mock_text, tool_calls=None)
            return mock_text

        client = await self.get_client_async(provider_id=provider_id)

        with tracer.start_as_current_span(
            f"llm.chat/{active_model}",
            attributes={
                "llm.model": active_model,
                "llm.operation": "chat",
                "llm.num_messages": len(messages),
                "llm.has_tools": bool(tools),
            },
        ) as span:
            kwargs = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature_override if temperature_override is not None else (master_config.get("temperature") or settings.MASTER_AGENT_TEMPERATURE),
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            raw_content = message.content or ""
            strip_think = await self._should_strip_think(provider_id)
            content = self._strip_think_blocks(raw_content) if strip_think else raw_content
            span.set_attribute("llm.response_length", len(content))
            span.set_attribute("llm.finish_reason", response.choices[0].finish_reason)
            await self._record_token_usage(active_model, active_provider_id, response)

            if tools is not None:
                message.content = content
                return message
            return content

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider_id: Optional[int] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
    ):
        """Stream chat completion tokens as an async generator.

        Yields string chunks as they arrive from the provider.
        Usage::
            async for chunk in router.stream_chat(messages, provider_id=1):
                yield f"data: {chunk}\\n\\n"
        """
        active_model = model_override or model
        if not active_model and provider_id:
            config = await self.get_provider_config_async(provider_id)
            if config and config.get("models"):
                active_model = config["models"][0]
        active_model = active_model or settings.MASTER_AGENT_MODEL

        master_config = await self._load_master_config()

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

        client = await self.get_client_async(provider_id=provider_id)
        temperature = (
            temperature_override
            if temperature_override is not None
            else (master_config.get("temperature") or settings.MASTER_AGENT_TEMPERATURE)
        )

        accumulated = []
        try:
            stream = await client.chat.completions.create(
                model=active_model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    accumulated.append(delta)
                    yield delta
        except Exception as e:
            yield f"\n\n[错误: {e}]"
            return

        # Strip think tags from final accumulated response (best-effort)
        full = "".join(accumulated)
        strip = await self._should_strip_think(provider_id)
        if strip and "<think>" in full.lower():
            # We already streamed the raw content — emit a replacement signal
            # so the client knows to strip think blocks from display
            pass  # client-side stripping for streamed content

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
