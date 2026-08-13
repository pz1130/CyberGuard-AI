import { useEffect, useRef, useState } from "react";
import type { Ev } from "../../../lib/types";
import { Card, Disclosure, Tooltip } from "../../../ui";
import "./events.css";

function fmtArgs(raw: unknown): string {
  if (raw == null || raw === "") return "";
  if (typeof raw === "string") return raw;
  try {
    return JSON.stringify(raw, null, 2);
  } catch {
    return String(raw);
  }
}

/** 运行中的实时计时器；结束后定格在 durationMs */
function Elapsed({ startedAt, durationMs }: { startedAt: number; durationMs?: number }) {
  const [now, setNow] = useState(Date.now());
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (durationMs != null) return;
    timer.current = window.setInterval(() => setNow(Date.now()), 100);
    return () => {
      if (timer.current != null) window.clearInterval(timer.current);
    };
  }, [durationMs]);

  const ms = durationMs ?? now - startedAt;
  return <span className="ev2-dur">{(ms / 1000).toFixed(1)}s</span>;
}

export function ToolEvent({ ev }: { ev: Ev; onViewEvidence?: (id?: string) => void }) {
  const name = String(ev.tool_name || ev.name || "tool");
  const running = ev.type === "tool_call_start";
  const failed = Boolean(ev.error) || String(ev.status || "") === "failed";
  const hostile = String(ev.source_trust || "") === "hostile";
  // live events put the preview in result_preview (T13); summary is fallback
  const summary = String(ev.result_preview || ev.summary || "");
  // live `error` is often boolean; the text lives in result_preview
  const failMsg =
    typeof ev.error === "boolean"
      ? String(ev.result_preview || ev.error_type || "执行失败")
      : String(ev.error || ev.result_preview || "");
  const args = fmtArgs(ev.args ?? ev.arguments);
  const startedAt =
    typeof ev.started_at === "number" ? ev.started_at * 1000 : Date.now();
  const durationMs =
    typeof ev.duration_ms === "number"
      ? ev.duration_ms
      : running
        ? undefined
        : 0;

  return (
    <Card tone={failed ? "danger" : running ? "info" : "default"} className="ev2">
      <div className="ev2-head">
        <span className="ev2-kind">工具</span>
        <code className="ev2-name">{name}</code>
        <Elapsed startedAt={startedAt} durationMs={durationMs} />
        {hostile ? (
          <Tooltip content="外部来源内容，默认不可信；作为结论依据时须标注可溯源（INV-39）">
            <span className="ev2-hostile">外部来源</span>
          </Tooltip>
        ) : null}
      </div>

      {failed ? (
        <div className="ev2-fail">
          <span className="ev2-fail-kind">
            {String(ev.error_type || "执行失败")}
          </span>
          <span className="ev2-fail-msg">{failMsg}</span>
          {ev.retryable === true ? (
            <span className="ev2-fail-retry">可重试</span>
          ) : null}
        </div>
      ) : summary ? (
        <p className="ev2-summary">→ {summary}</p>
      ) : null}

      {args ? (
        <Disclosure summary="参数">
          <pre className="ev2-pre">{args}</pre>
        </Disclosure>
      ) : null}
    </Card>
  );
}
