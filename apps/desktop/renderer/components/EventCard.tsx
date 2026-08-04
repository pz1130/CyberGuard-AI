import type { Ev } from "../lib/types";
import { Markdown } from "./Markdown";

type Props = {
  ev: Ev;
  onViewEvidence?: (evidenceId?: string) => void;
};

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

function prettyToolName(raw: string): { title: string; sub?: string } {
  const name = raw || "tool";
  // mcp__server__tool → tool · server
  const m = name.match(/^mcp__([^_]+)__(.+)$/);
  if (m) return { title: m[2], sub: m[1] };
  if (name === "load_skill") return { title: "load_skill", sub: "builtin" };
  return { title: name };
}

function formatArgs(raw: unknown): string {
  if (raw == null || raw === "") return "";
  const s = String(raw);
  try {
    const parsed = JSON.parse(s);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return s;
  }
}

function truncate(s: string, n: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n)}…` : t;
}

/** System noise → compact chips, not full cards */
const COMPACT_TYPES = new Set([
  "start",
  "episodic_recall",
  "episodic_recorded",
  "auth_bounds_check",
  "token_done",
  "policy_event",
]);

export function EventCard({ ev, onViewEvidence }: Props) {
  const t = String(ev.type || "event");

  if (COMPACT_TYPES.has(t)) {
    let label = t.replace(/_/g, " ");
    if (t === "start") label = `agent · ${String(ev.agent_name || "desktop")}`;
    if (t === "episodic_recall")
      label = `回忆 ${String(ev.count ?? "…")} 条经验`;
    if (t === "episodic_recorded") label = "已写入经验库";
    if (t === "auth_bounds_check") label = "授权边界校验";
    if (t === "token_done") label = "流式完成";
    if (t === "policy_event")
      label = `策略 · ${String(ev.policy_event_type || "event")}`;
    return (
      <div className="ev-chip" title={JSON.stringify(ev).slice(0, 200)}>
        <span className="ev-chip-dot" />
        {label}
      </div>
    );
  }

  if (t === "user_task") {
    return (
      <div className="ev type-user_task">
        <div className="ev-head">
          <span className="ev-badge">任务</span>
          {ev.tier ? (
            <span className="ev-badge muted">{String(ev.tier)}</span>
          ) : null}
        </div>
        <div className="ev-task">{String(ev.task || "")}</div>
      </div>
    );
  }

  if (t === "run_started") {
    const prov = (ev.provider || {}) as { mode?: string; model?: string };
    const tools = Array.isArray(ev.mcp_tools)
      ? (ev.mcp_tools as string[]).map((n) => prettyToolName(n).title)
      : [];
    return (
      <div className="ev type-run_started">
        <div className="ev-head">
          <span className="ev-badge info">开始</span>
          <span className="ev-badge muted">
            {prov.mode || "?"}
            {prov.model ? ` · ${prov.model}` : ""}
          </span>
        </div>
        {tools.length > 0 ? (
          <div className="ev-tool-row">
            {tools.slice(0, 6).map((name) => (
              <span key={name} className="ev-tool-pill">
                {name}
              </span>
            ))}
            {tools.length > 6 ? (
              <span className="ev-tool-pill muted">+{tools.length - 6}</span>
            ) : null}
          </div>
        ) : (
          <div className="ev-meta">无 MCP 工具</div>
        )}
      </div>
    );
  }

  if (t === "tool_call_start") {
    const { title, sub } = prettyToolName(String(ev.name || ""));
    const args = formatArgs(ev.arguments);
    return (
      <div className="ev type-tool_call_start">
        <div className="ev-head">
          <span className="ev-badge tool">工具</span>
          <code className="ev-tool-name">{title}</code>
          {sub ? <span className="ev-badge muted">{sub}</span> : null}
        </div>
        {args ? (
          <details className="ev-args">
            <summary>参数</summary>
            <pre className="ev-pre">{args}</pre>
          </details>
        ) : null}
      </div>
    );
  }

  if (t === "tool_call_end") {
    const err = Boolean(ev.error);
    const hostile = String(ev.source_trust || "") === "hostile";
    const name = String(ev.name || "");
    const { title, sub } = prettyToolName(name);
    const preview = String(ev.result_preview || "");
    const eidMatch = preview.match(
      /["']?evidence_id["']?\s*[:=]\s*["']?([0-9a-f-]{8,})/i
    );
    const shaMatch = preview.match(/\b([a-f0-9]{64})\b/i);
    const evidencey =
      /evidence/i.test(name) || Boolean(eidMatch) || Boolean(shaMatch);
    return (
      <div className={`ev type-tool_call_end${err ? " type-error" : ""}`}>
        <div className="ev-head">
          <span className={`ev-badge ${err ? "err" : "ok"}`}>
            {err ? "失败" : "结果"}
          </span>
          <code className="ev-tool-name">{title}</code>
          {sub ? <span className="ev-badge muted">{sub}</span> : null}
          {hostile ? <span className="ev-badge warn">hostile</span> : null}
        </div>
        {preview ? (
          <pre className="ev-pre ev-pre-result">{truncate(preview, 800)}</pre>
        ) : (
          <div className="ev-meta">（无预览）</div>
        )}
        {evidencey && onViewEvidence ? (
          <div className="ev-actions">
            <button
              type="button"
              className="secondary"
              onClick={() =>
                onViewEvidence(eidMatch ? eidMatch[1] : undefined)
              }
            >
              在证据库查看
            </button>
          </div>
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
        <div className="ev-head">
          <span className="ev-badge ok">报告</span>
        </div>
        {report ? (
          <div className="ev-report">
            <Markdown text={report} />
          </div>
        ) : (
          <div className="ev-meta">（无正文）</div>
        )}
        <div className="ev-actions">
          {onViewEvidence ? (
            <button
              type="button"
              className="secondary"
              onClick={() => onViewEvidence()}
            >
              证据库
            </button>
          ) : null}
          <details className="raw-details">
            <summary>原始 JSON</summary>
            <pre className="ev-pre">{JSON.stringify(ev, null, 2)}</pre>
          </details>
        </div>
      </div>
    );
  }

  if (t === "evidence_register" || t === "evidence_registered") {
    const eid = String(ev.evidence_id || ev.id || "");
    const name = String(ev.name || ev.file_name || "evidence");
    const sha = String(ev.sha256 || "");
    return (
      <div className="ev type-evidence">
        <div className="ev-head">
          <span className="ev-badge ok">证据</span>
          <span className="ev-badge muted">read-only</span>
        </div>
        <div className="ev-task">{name}</div>
        {sha ? (
          <div className="ev-meta mono-sm">
            sha256 {sha.slice(0, 12)}…{sha.slice(-8)}
          </div>
        ) : null}
        {onViewEvidence ? (
          <div className="ev-actions">
            <button
              type="button"
              className="primary"
              onClick={() => onViewEvidence(eid || undefined)}
            >
              打开证据
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  if (t === "error") {
    return (
      <div className="ev type-error">
        <div className="ev-head">
          <span className="ev-badge err">错误</span>
        </div>
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
        <div className="ev-head">
          <span className="ev-badge plan">计划待审</span>
          <span className="ev-badge muted">
            {String(ev.ui_label || "自批准")}
          </span>
          {ev.local_approve_allowed === false ? (
            <span className="ev-badge warn">本机不可批</span>
          ) : null}
        </div>
        <div className="ev-meta">
          risk {String(plan.risk_level || "?")}
          {ev.timeout_seconds != null
            ? ` · ${String(ev.timeout_seconds)}s 超时=拒绝`
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
        <div className="ev-head">
          <span className="ev-badge ok">计划已批</span>
          {ev.revised ? <span className="ev-badge muted">已改写</span> : null}
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
        <div className="ev-head">
          <span className="ev-badge err">计划未批</span>
        </div>
        <div className="ev-meta">
          {String(ev.status || "")}: {String(ev.reason || "")}
        </div>
      </div>
    );
  }

  if (t === "privilege_required") {
    return (
      <div className="ev type-plan_ready">
        <div className="ev-head">
          <span className="ev-badge plan">提权</span>
          <span className="ev-badge muted">
            {String(ev.ui_label || "自批准")}
          </span>
        </div>
        <div className="ev-meta">
          {String(ev.tool || "")} · {String(ev.denied_detail || "")}
        </div>
      </div>
    );
  }

  if (t === "privilege_decided") {
    const ok = String(ev.status || "") === "approved";
    return (
      <div className={`ev ${ok ? "type-plan_approved" : "type-error"}`}>
        <div className="ev-head">
          <span className={`ev-badge ${ok ? "ok" : "err"}`}>
            提权{ok ? "已批" : "拒绝"}
          </span>
        </div>
        <div className="ev-meta">
          {String(ev.status || "")}
          {ev.reason ? `: ${String(ev.reason)}` : ""}
        </div>
      </div>
    );
  }

  if (t === "run_paused") {
    return (
      <div className="ev type-error">
        <div className="ev-head">
          <span className="ev-badge warn">已暂停</span>
        </div>
        <div className="ev-meta">
          {String(ev.reason || "")} · 可用 Resume 继续
        </div>
      </div>
    );
  }

  if (t === "run_resumed") {
    return (
      <div className="ev type-plan_approved">
        <div className="ev-head">
          <span className="ev-badge ok">已恢复</span>
        </div>
      </div>
    );
  }

  // fallback compact
  return (
    <div className="ev-chip">
      <span className="ev-chip-dot" />
      {t.replace(/_/g, " ")}
      <details className="raw-details inline">
        <summary>详情</summary>
        <pre className="ev-pre">{JSON.stringify(ev, null, 2)}</pre>
      </details>
    </div>
  );
}
