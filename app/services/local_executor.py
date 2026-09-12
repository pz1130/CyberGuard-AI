"""Built-in local agent executor — fallback when no remote sub-agent is registered."""
import json
import logging
from typing import Dict, Any, Optional
from app.services.llm_router import get_llm_router

logger = logging.getLogger(__name__)


# Keyword → agent type mapping for intent resolution
AGENT_TYPE_KEYWORDS = {
    "threat_intel": [
        "threat", "cve", "ioc", "malware", "apt", "ransomware",
        "phishing", "indicator", "firewall alert", "ids", "ips",
        "threat intelligence", "malicious", "apt", "攻击", "威胁情报",
        "恶意软件", "漏洞情报", "ip", "domain", "hash",
    ],
    "log_anomaly": [
        "log", "anomaly", "unusual", "pattern", "detect",
        "siem", "splunk", "elk", "日志", "异常", "入侵检测",
    ],
    "vuln_scanner": [
        "scan", "vuln", "cve", "exploit", "penetration", "nmap",
        "security scan", "漏洞扫描", "渗透测试",
    ],
    "remediation": [
        "fix", "remediate", "patch", "remediate", "mitigate",
        "block", "quarantine", "isolate", "修复", "封禁", "隔离",
    ],
    "osint": [
        "osint", "recon", " footprint", "whois", "dns lookup",
        "子域名", "信息收集", "侦察",
    ],
}

# Default fallback system prompts (used when no skill is configured in DB)
FALLBACK_SYSTEM_PROMPTS: Dict[str, str] = {
    "threat_intel": """你是一个网络安全威胁情报分析 Agent。
当给定 IOC（IP、域名、Hash、URL）时，请从以下角度分析：
1. 该 IOC 的恶意活动历史
2. 关联的 APT 组织或攻击活动
3. 推荐的下一步行动（监控/封禁/深入调查）
如果无法确定，给出最可能的分类和置信度。""",
    "log_anomaly": """你是一个日志异常分析 Agent。
分析给定的日志条目，识别：
1. 异常模式（多次失败登录、异常时间访问等）
2. 可能的攻击向量
3. 推荐的响应动作
请用结构化格式输出。""",
    "vuln_scanner": """你是一个漏洞扫描分析 Agent。
分析目标系统或 CVE 描述，提供：
1. 漏洞严重程度和 CVSS 评分
2. 受影响版本/配置
3. 利用可行性（PoC/野利用）
4. 修复建议（补丁/缓解措施）""",
    "remediation": """你是一个安全事件响应 Agent。
给定安全事件，提供：
1. 紧急止损措施
2. 事件遏制步骤
3. 根因分析框架
4. 后续加固建议""",
    "osint": """你是一个 OSINT 侦察 Agent。
对目标进行开源情报收集：
1. WHOIS / DNS 信息
2. 关联的公开数据泄露
3. 社交媒体足迹
4. 网络空间测绘数据
提示：当作为「internal」类型 Agent 并启用 enable_search 时，你可调用 web_search
（公开网络检索）与 vuln_search（Sploitus 漏洞/利用检索）工具获取实时情报。""",
    "general": """你 CyberGuard 安全助理。
基于你的网络安全知识，帮助用户：
- 分析安全事件和 IOC
- 提供威胁情报
- 回答安全问题
- 指导安全运营""",
}


def match_agent_type(task_description: str) -> Optional[str]:
    """Match a task description to an agent type by keyword."""
    task_lower = task_description.lower()
    for agent_type, keywords in AGENT_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in task_lower:
                return agent_type
    return None


class LocalAgentExecutor:
    """
    Fallback executor that runs tasks directly via LLM when no remote
    sub-agent is available.

    Skills: **catalog only** (name + description) — no full SOP body in the
    system prompt (progressive disclosure; local path has no load_skill tool).
    Role behaviour comes from built-in fallback prompts.
    """

    def __init__(self, llm_router=None):
        self.llm_router = llm_router or get_llm_router()

    async def _get_system_prompt(self, agent_type: str) -> str:
        """Built-in role prompt + optional skill catalog (no full bodies)."""
        from app.services.skill_loader import SkillLoader

        base = FALLBACK_SYSTEM_PROMPTS.get(
            agent_type, FALLBACK_SYSTEM_PROMPTS["general"]
        )
        parts = [base]
        try:
            catalog = await SkillLoader.load_catalog_for_agent_type(agent_type)
            if catalog:
                parts.append(
                    SkillLoader.format_catalog_prompt(
                        catalog,
                        intro=(
                            "## Related skill catalog (reference only)\n"
                            "Full procedure bodies are **not** injected here "
                            "(local fallback has no load_skill tool). "
                            "Use name/description as high-level guidance only."
                        ),
                    )
                )
        except Exception as e:  # noqa: BLE001 — functional degrade, must be visible
            logger.warning(
                "local_executor skill catalog load failed for %s: %s",
                agent_type,
                e,
            )
        return "\n\n".join(parts)

    async def execute(
        self,
        task: str,
        agent_type: Optional[str] = None,
        user_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        provider_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task locally using the LLM, optionally scoped to an agent type.

        Returns dict with status, output, agent_name, execution_time.
        """
        import time
        start = time.monotonic()

        agent_type = agent_type or match_agent_type(task) or "general"
        system_prompt = await self._get_system_prompt(agent_type)

        user_content = task
        if context:
            user_content = f"上下文信息：{json.dumps(context, ensure_ascii=False)}\n\n任务：{task}"

        try:
            response = await self.llm_router.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                provider_id=provider_id,
            )
            execution_time = time.monotonic() - start
            return {
                "status": "completed",
                "output": response,
                "agent_type": agent_type,
                "agent_name": f"Local/{agent_type}",
                "execution_time": round(execution_time, 2),
            }
        except Exception as e:
            execution_time = time.monotonic() - start
            return {
                "status": "failed",
                "output": None,
                "error": str(e),
                "agent_type": agent_type,
                "agent_name": f"Local/{agent_type}",
                "execution_time": round(execution_time, 2),
            }


# Singleton
_local_executor: Optional[LocalAgentExecutor] = None


def get_local_executor() -> LocalAgentExecutor:
    global _local_executor
    if _local_executor is None:
        _local_executor = LocalAgentExecutor()
    return _local_executor
