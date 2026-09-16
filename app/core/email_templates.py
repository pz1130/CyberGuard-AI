"""Restricted mail placeholders: no expressions, loops, or code execution."""
import re
from html import escape

DEFAULT_TEMPLATES = {
    "created_subject": "[CyberGuard] 审批请求待处理 — 风险: {{risk_level}}",
    "created_body": """<h2>CyberGuard — 新审批请求</h2>
<p>请求 ID：{{request_id}}</p>
<p>操作描述：{{action_description}}</p>
<p>风险等级：{{risk_level}}</p>
<p>发起用户 ID：{{user_id}}</p>
<p>请登录 CyberGuard 管理界面处理此请求。</p>""",
    "decided_subject": "[CyberGuard] 审批结果: {{decision}}",
    "decided_body": """<h2>CyberGuard — 审批结果通知</h2>
<p>请求 ID：{{request_id}}</p>
<p>决定：{{decision}}</p>
<p>备注：{{comment}}</p>""",
}
VARIABLES = {
    "created": {"request_id", "action_description", "risk_level", "user_id"},
    "decided": {"request_id", "decision", "comment"},
}
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
SAMPLE_VALUES = {
    "created": {"request_id": "sample-request-001", "action_description": "隔离可疑主机 / Isolate suspicious host",
                "risk_level": "HIGH", "user_id": "42"},
    "decided": {"request_id": "sample-request-001", "decision": "APPROVED", "comment": "已确认，可执行 / Reviewed and approved"},
}


def validate_template(value: str, kind: str, *, subject: bool = False) -> str:
    if subject and ("\r" in value or "\n" in value):
        raise ValueError("Email subjects cannot contain line breaks")
    if not value.strip():
        raise ValueError("Email templates cannot be empty")
    for match in PLACEHOLDER.finditer(value):
        if match.group(1) not in VARIABLES[kind]:
            raise ValueError(f"Unknown {kind} template variable: {match.group(1)}")
    remainder = PLACEHOLDER.sub("", value)
    if "{{" in remainder or "}}" in remainder:
        raise ValueError("Use {{variable_name}} for template variables")
    return value


def render_notification(cfg: dict, kind: str, values: dict) -> tuple[str, str]:
    def render(template: str, html: bool) -> str:
        def substitute(match):
            value = str(values.get(match.group(1), ""))
            return escape(value) if html else value.replace("\r", " ").replace("\n", " ")
        return PLACEHOLDER.sub(substitute, template)
    subject = cfg.get(f"{kind}_subject", DEFAULT_TEMPLATES[f"{kind}_subject"])
    body = cfg.get(f"{kind}_body", DEFAULT_TEMPLATES[f"{kind}_body"])
    return render(subject, False), render(body, True)
