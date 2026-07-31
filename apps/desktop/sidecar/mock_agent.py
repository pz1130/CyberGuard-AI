"""Agent host: agent_core.run_loop + mock/live LLM + MCP tools (M1.5)."""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional

from agent_core.run_loop import RunLoopConfig, run_loop

from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.mcp_manager import MCP
from apps.desktop.sidecar.provider import load_provider_config, live_chat


def _load_builtin_skills() -> str:
    skills_dir = Path(__file__).resolve().parent / "skills"
    if not skills_dir.is_dir():
        return ""
    parts = []
    for path in sorted(skills_dir.glob("*.md")):
        try:
            parts.append(path.read_text(encoding="utf-8").strip())
        except OSError:
            continue
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)


def _format_mcp_result(result: Any) -> str:
    """Normalize tools/call result to a string for the model."""
    if result is None:
        return "(empty)"
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # MCP content blocks
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(str(block.get("text") or ""))
                    else:
                        parts.append(json.dumps(block, ensure_ascii=False, default=str))
                else:
                    parts.append(str(block))
            text = "\n".join(parts)
            if result.get("isError"):
                return f"ERROR: {text}"
            return text or json.dumps(result, ensure_ascii=False, default=str)
        return json.dumps(result, ensure_ascii=False, default=str)
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except TypeError:
        return str(result)


@dataclass
class ActiveRun:
    run_id: str
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    steer_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None


class MockAgentHost:
    """Supports mock + live provider; MCP tools when configured."""

    def __init__(self) -> None:
        self._runs: Dict[str, ActiveRun] = {}

    def get(self, run_id: str) -> Optional[ActiveRun]:
        return self._runs.get(run_id)

    def abort(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if not run:
            return False
        run.abort_event.set()
        return True

    def steer(self, run_id: str, message: str) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        run.steer_queue.put_nowait(message)
        return True

    async def run(
        self,
        *,
        task: str,
        tier: str = "readonly",
        system_prompt: Optional[str] = None,
        agent_name: str = "desktop-agent",
    ) -> AsyncIterator[Dict[str, Any]]:
        caps = capabilities_for_tier(tier)
        provider = load_provider_config()
        run_id = str(uuid.uuid4())
        active = ActiveRun(run_id=run_id)
        self._runs[run_id] = active

        # Discover MCP tools (readonly servers on all tiers)
        mcp_tools, mcp_routing = await MCP.discover_tools_for_agent(tier=tier)

        yield {
            "type": "run_started",
            "run_id": run_id,
            "tier": caps.tier,
            "capabilities": caps.describe(),
            "policy": caps.policy.public_status(),
            "provider": provider.public_status(),
            "mcp_tools": [t["function"]["name"] for t in mcp_tools],
            "mcp_server_count": len({r[0].id for r in mcp_routing.values()}),
        }

        tools: List[Dict[str, Any]] = list(mcp_tools)

        # Real sandboxed host tools when Seatbelt-backed ports are live
        host_read_enabled = bool(caps.real_read and caps.operations.read is not None)
        host_edit_enabled = bool(caps.real_edit and caps.operations.edit is not None)
        if host_read_enabled:
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "host_read_file",
                            "description": (
                                "Read a local text file via OS sandbox. "
                                "Path must be absolute. Do not use for secrets/keys."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "max_bytes": {"type": "integer"},
                                },
                                "required": ["path"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "host_list_dir",
                            "description": (
                                "List directory entries via OS sandbox. "
                                "Path must be absolute."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {"path": {"type": "string"}},
                                "required": ["path"],
                            },
                        },
                    },
                ]
            )
        if host_edit_enabled:
            roots = list(caps.policy.writable_roots)
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "host_write_file",
                            "description": (
                                "Write a text file via OS sandbox (workspace-write). "
                                f"Path MUST be under: {roots}. "
                                "Never write secrets or provider.json."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["path", "content"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "host_delete_file",
                            "description": (
                                "Delete a file via OS sandbox. "
                                f"Path MUST be under: {roots}."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {"path": {"type": "string"}},
                                "required": ["path"],
                            },
                        },
                    },
                ]
            )

        # Legacy mock_scan for full tier demos (never real process execution)
        if caps.has_local_exec() and not mcp_tools:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "mock_scan",
                        "description": "Fake scan (no real process execution)",
                        "parameters": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}},
                            "required": ["target"],
                        },
                    },
                }
            )

        tools_arg: Optional[List[Dict[str, Any]]] = tools or None
        step = {"n": 0}
        skills = _load_builtin_skills()
        default_prompt = (
            "You are CyberGuard desktop security agent (self-use M1.5/M2).\n"
            "Be precise and actionable. Prefer read-only investigation.\n"
            "MCP tools prefixed with mcp__ are connectors — use them for data.\n"
            "host_* tools use the OS sandbox for local files.\n"
            "Tools named mock_* do not touch the real host.\n"
        )
        if skills:
            default_prompt += "\n## Built-in SOPs\n" + skills
        if mcp_tools:
            names = ", ".join(t["function"]["name"] for t in mcp_tools)
            default_prompt += f"\n\n## Available MCP tools\n{names}\n"
        host_names = []
        if host_read_enabled:
            host_names.extend(["host_read_file", "host_list_dir"])
        if host_edit_enabled:
            host_names.extend(["host_write_file", "host_delete_file"])
        if host_names:
            default_prompt += (
                "\n\n## Host tools (sandboxed)\n" + ", ".join(host_names) + "\n"
            )
        if not provider.is_live:
            default_prompt += (
                "\n\n(Running in MOCK mode — no real LLM. "
                "Set CYBERGUARD_LLM_MODE=live + API key for real responses.)"
            )
        prompt = system_prompt or default_prompt

        async def chat(*, messages, tools=None):
            if active.abort_event.is_set():
                raise RuntimeError("aborted")
            if provider.is_live:
                return await live_chat(provider, list(messages), tools=tools)

            await asyncio.sleep(0.05)
            if active.abort_event.is_set():
                raise RuntimeError("aborted")
            step["n"] += 1
            # Demo policy: for triage-like tasks prefer list_alerts; else first MCP tool
            if tools and step["n"] == 1:
                names = [t["function"]["name"] for t in tools]
                preferred = None
                task_l = (messages[-1].get("content") or "").lower() if messages else ""
                if any(k in task_l for k in ("告警", "alert", "分诊", "triage")):
                    preferred = next(
                        (n for n in names if "list_alerts" in n), None
                    )
                preferred = preferred or next(
                    (n for n in names if n.startswith("mcp__")), None
                )
                if preferred and preferred.startswith("mcp__"):
                    args = '{"limit": 5}' if "list_alerts" in preferred else "{}"
                    call = SimpleNamespace(
                        id="mock_call_1",
                        function=SimpleNamespace(name=preferred, arguments=args),
                    )
                    return SimpleNamespace(content="", tool_calls=[call])
                if "mock_scan" in names:
                    call = SimpleNamespace(
                        id="mock_call_1",
                        function=SimpleNamespace(
                            name="mock_scan",
                            arguments='{"target":"10.0.0.0/24"}',
                        ),
                    )
                    return SimpleNamespace(content="", tool_calls=[call])

            # Second step: if we already have tool results, produce a demo triage report
            if step["n"] >= 2 and tools:
                tool_bits = []
                for m in messages:
                    if m.get("role") == "tool":
                        tool_bits.append(str(m.get("content") or "")[:2000])
                blob = "\n".join(tool_bits)
                if "A-1001" in blob or "severity" in blob.lower():
                    return (
                        "## 告警分诊报告（mock LLM 演示）\n\n"
                        "### Top 发现\n"
                        "1. **A-1001 high** — Suspicious PowerShell from workstation (ws-042, count=12)\n"
                        "2. **A-1002 medium** — Failed SSH bursts (jump-01, count=84)\n"
                        "3. **A-1003 low** — AV signature update lag（若工具返回）\n\n"
                        "### 为什么重要\n"
                        "- A-1001：工作站异常脚本执行，优先怀疑初始入侵或恶意软件落地。\n"
                        "- A-1002：跳板机暴力尝试，需结合是否成功登录。\n\n"
                        "### 建议动作\n"
                        "- A-1001：隔离取证 → 查进程/父进程与外连（只读优先）\n"
                        "- A-1002：核对认证日志与封禁策略；必要时限流\n\n"
                        "### 不确定性\n"
                        "_当前为 MOCK LLM；接 live Provider 后由模型基于完整工具输出生成报告。_\n"
                    )
            mcp_note = (
                f" MCP tools: {len(mcp_tools)}."
                if mcp_tools
                else " No MCP servers configured."
            )
            return (
                f"[mock LLM] Task received. Tier={caps.tier}.{mcp_note} "
                f"Configure live provider for real analysis."
            )

        async def dispatch(call):
            if active.abort_event.is_set():
                return {"status": "error", "error": "aborted", "is_error": True}
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name in mcp_routing:
                try:
                    result = await MCP.call_routed(mcp_routing, name, args)
                    text = _format_mcp_result(result)
                    is_err = isinstance(result, dict) and bool(result.get("isError"))
                    return {
                        "status": "error" if is_err else "completed",
                        "stdout": text,
                        "is_error": is_err or text.startswith("ERROR:"),
                    }
                except Exception as exc:  # noqa: BLE001
                    return {
                        "status": "error",
                        "error": f"MCP {name}: {exc}",
                        "is_error": True,
                    }

            if name in ("host_read_file", "host_list_dir"):
                if not host_read_enabled or caps.operations.read is None:
                    return {
                        "status": "error",
                        "error": "host read tools require OS sandbox (seatbelt)",
                        "is_error": True,
                    }
                try:
                    path = str(args.get("path") or "")
                    if name == "host_read_file":
                        max_b = int(args.get("max_bytes") or 200_000)
                        text = await caps.operations.read.read_text(
                            path, max_bytes=max_b
                        )
                        return {
                            "status": "completed",
                            "stdout": text,
                            "is_error": False,
                            "sandboxed": True,
                        }
                    entries = await caps.operations.read.list_dir(path)
                    return {
                        "status": "completed",
                        "stdout": "\n".join(entries),
                        "is_error": False,
                        "sandboxed": True,
                    }
                except Exception as exc:  # noqa: BLE001
                    return {
                        "status": "error",
                        "error": f"{name}: {exc}",
                        "is_error": True,
                    }

            if name in ("host_write_file", "host_delete_file"):
                if not host_edit_enabled or caps.operations.edit is None:
                    return {
                        "status": "error",
                        "error": "host write tools require full tier + workspace-write seatbelt",
                        "is_error": True,
                    }
                try:
                    path = str(args.get("path") or "")
                    if name == "host_write_file":
                        content = str(args.get("content") if args.get("content") is not None else "")
                        await caps.operations.edit.write_text(path, content)
                        return {
                            "status": "completed",
                            "stdout": f"wrote {path} ({len(content)} chars)",
                            "is_error": False,
                            "sandboxed": True,
                        }
                    await caps.operations.edit.delete(path)
                    return {
                        "status": "completed",
                        "stdout": f"deleted {path}",
                        "is_error": False,
                        "sandboxed": True,
                    }
                except Exception as exc:  # noqa: BLE001
                    return {
                        "status": "error",
                        "error": f"{name}: {exc}",
                        "is_error": True,
                    }

            # mock_scan fallback
            await asyncio.sleep(0.05)
            return {
                "status": "completed",
                "stdout": f"[mock-tool {name}] args={call.function.arguments}",
                "is_error": False,
            }

        cfg = RunLoopConfig(
            max_steps=8 if provider.is_live else 6,
            tool_call_budget=15 if provider.is_live else 10,
            agent_name=agent_name,
            agent_run_id=run_id,
        )

        try:
            async for ev in run_loop(
                task=task,
                system_prompt=prompt,
                history=[],
                tools=tools_arg,
                config=cfg,
                chat=chat,
                dispatch=dispatch,
                abort_event=active.abort_event,
                steer_queue=active.steer_queue,
            ):
                ev = dict(ev)
                ev.setdefault("run_id", run_id)
                yield ev
        finally:
            self._runs.pop(run_id, None)
