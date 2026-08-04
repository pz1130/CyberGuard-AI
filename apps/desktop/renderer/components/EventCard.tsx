import type { Ev } from "../lib/types";
import { Markdown } from "./Markdown";

function extractAssistantText(ev: Ev): string {
  const messages = ev.messages;
  if (!Array.isArray(messages)) return "";
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i] as { role?: string; content?: string };
    if (m?.role === "assistant" && m.content && m.content.trim()) {
      return m.content;
    }
  }
  return "";
}

export function EventCard({ ev }: { ev: Ev }) {
  const t = String(ev.type || "event");

  if (t === "user_task") {
    return (
      <div className="ev type-user_task">
        <div className="ev-label">你提交的任务</div>
        <div className="ev-task">{String(ev.task || "")}</div>
        {ev.tier ? (
          <div className="ev-meta">档位: {String(ev.tier)}</div>
        ) : null}
      </div>
    );
  }

  if (t === "run_started") {
    const prov = (ev.provider || {}) as {
      mode?: string;
      model?: string;
    };
    const tools = Array.isArray(ev.mcp_tools)
      ? (ev.mcp_tools as string[]).join(", ")
      : "—";
    return (
      <div className="ev type-run_started">
        <div className="ev-label">开始运行</div>
        <div className="ev-meta">
          LLM: {prov.mode || "?"}
          {prov.model ? ` · ${prov.model}` : ""} · MCP: {tools}
        </div>
      </div>
    );
  }

  if (t === "start") {
    return (
      <div className="ev type-start muted-ev">
        <span className="ev-label">agent 循环</span>
        <span className="ev-meta"> {String(ev.agent_name || "desktop-agent")}</span>
      </div>
    );
  }

  if (t === "tool_call_start") {
    return (
      <div className="ev type-tool_call_start">
        <div className="ev-label">调用工具</div>
        <code>{String(ev.name || "")}</code>
        {ev.arguments ? (
          <pre className="ev-pre">{String(ev.arguments)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "tool_call_end") {
    const err = Boolean(ev.error);
    const hostile = String(ev.source_trust || "") === "hostile";
    return (
      <div className={`ev type-tool_call_end${err ? " type-error" : ""}`}>
        <div className="ev-label">
          {err ? "工具失败" : "工具结果"}
          {hostile ? " · source_trust=hostile" : ""}
        </div>
        <code>{String(ev.name || "")}</code>
        {ev.result_preview ? (
          <pre className="ev-pre">{String(ev.result_preview)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "answer_ready") {
    const report =
      (typeof ev.candidate_text === "string" && ev.candidate_text) ||
      extractAssistantText(ev) ||
      "";
    return (
      <div className="ev type-answer_ready report">
        <div className="ev-label">报告</div>
        {report ? (
          <Markdown text={report} />
        ) : (
          <div className="ev-meta">（无 candidate_text）</div>
        )}
        <details className="raw-details">
          <summary>原始事件 JSON</summary>
          <pre className="ev-pre">{JSON.stringify(ev, null, 2)}</pre>
        </details>
      </div>
    );
  }

  if (t === "error") {
    return (
      <div className="ev type-error">
        <div className="ev-label">错误</div>
        <pre className="ev-pre">
          {String(ev.error || ev.message || JSON.stringify(ev))}
        </pre>
      </div>
    );
  }

  if (t === "plan_ready") {
    const plan = (ev.plan || {}) as {
      summary?: string;
      steps?: string[];
      risk_level?: string;
    };
    return (
      <div className="ev type-plan_ready">
        <div className="ev-label">
          执行计划待审 · {String(ev.ui_label || "自批准")}
          {ev.local_approve_allowed === false ? " · 本机不可批（职责分离）" : ""}
        </div>
        <div className="ev-meta">
          risk={String(plan.risk_level || "?")} · plan_id={String(ev.plan_id || "")}
          {ev.timeout_seconds != null
            ? ` · timeout ${String(ev.timeout_seconds)}s → 拒绝`
            : ""}
        </div>
        {plan.summary ? (
          <pre className="ev-pre plan-summary">{String(plan.summary)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "plan_approved") {
    return (
      <div className="ev type-plan_approved">
        <div className="ev-label">
          计划已批准 · {String(ev.ui_label || "自批准")}
          {ev.revised ? "（已改写）" : ""}
        </div>
        {ev.plan_summary ? (
          <pre className="ev-pre">{String(ev.plan_summary)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "plan_rejected") {
    return (
      <div className="ev type-error">
        <div className="ev-label">计划未批准 — 未执行</div>
        <div className="ev-meta">
          {String(ev.status || "")}: {String(ev.reason || "")}
        </div>
      </div>
    );
  }

  if (t === "privilege_required") {
    return (
      <div className="ev type-plan_ready">
        <div className="ev-label">
          提权申请 · {String(ev.ui_label || "自批准")}
        </div>
        <div className="ev-meta">
          tool={String(ev.tool || "")} · {String(ev.denied_detail || "")}
        </div>
        {ev.plan &&
        typeof ev.plan === "object" &&
        (ev.plan as { summary?: string }).summary ? (
          <pre className="ev-pre plan-summary">
            {String((ev.plan as { summary?: string }).summary)}
          </pre>
        ) : null}
      </div>
    );
  }

  if (t === "privilege_decided") {
    const ok = String(ev.status || "") === "approved";
    return (
      <div className={`ev ${ok ? "type-plan_approved" : "type-error"}`}>
        <div className="ev-label">
          提权{ok ? "已批准 — 重试中" : "未批准"}
        </div>
        <div className="ev-meta">
          {String(ev.status || "")}
          {ev.reason ? `: ${String(ev.reason)}` : ""}
        </div>
      </div>
    );
  }

  if (t === "policy_event") {
    return (
      <div className="ev type-plan_approved">
        <div className="ev-label">policy_event</div>
        <div className="ev-meta">
          {String(ev.policy_event_type || "")} · tool={String(ev.tool || "")} ·
          success={String(ev.success)}
        </div>
      </div>
    );
  }

  if (t === "run_paused") {
    return (
      <div className="ev type-error">
        <div className="ev-label">已暂停</div>
        <div className="ev-meta">
          {String(ev.reason || "")} · messages={String(ev.message_count ?? "")}
          · 可 agent.resume 继续
        </div>
      </div>
    );
  }

  if (t === "run_resumed") {
    return (
      <div className="ev type-plan_approved">
        <div className="ev-label">已恢复</div>
        <div className="ev-meta">messages={String(ev.message_count ?? "")}</div>
      </div>
    );
  }

  return (
    <div className={`ev type-${t}`}>
      <div className="ev-label">{t}</div>
      <details className="raw-details">
        <summary>详情</summary>
        <pre className="ev-pre">{JSON.stringify(ev, null, 2)}</pre>
      </details>
    </div>
  );
}
