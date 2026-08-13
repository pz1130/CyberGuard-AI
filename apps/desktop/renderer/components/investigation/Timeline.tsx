import { useEffect, useRef } from "react";
import { useRun, useStreamFlag } from "../../state";
import {
  classify,
  isClosedToolStart,
  MessageEvent,
  PlanEvent,
  SkeletonLines,
  StreamEvent,
  ToolEvent,
} from "./events";
import "./Timeline.css";

const SYSTEM_LABEL: Record<string, string> = {
  start: "会话开始",
  run_started: "运行开始",
  run_paused: "已暂停",
  run_resumed: "已恢复",
  episodic_recall: "召回经验",
  episodic_recorded: "已写入经验库",
  auth_bounds_check: "授权边界校验",
  policy_event: "策略事件",
  token_done: "流式完成",
};

export function Timeline({
  onViewEvidence,
}: {
  onViewEvidence: (evidenceId?: string) => void;
}) {
  const { events, status } = useRun();
  // 只订阅布尔 —— 订阅 useStreamText 会让整条时间线随每个 token 重渲染
  const streaming = useStreamFlag();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    bottomRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
  }, [events.length, streaming]);

  // 已提交但首包未到：显示骨架。正文流只给 StreamEvent 订阅。
  const awaitingFirstToken =
    status === "running" && !streaming && events.length <= 1;

  return (
    <div className="timeline2">
      {events.map((ev, i) => {
        const kind = classify(ev);
        const key = `${i}-${ev.type}`;
        if (kind === "tool") {
          if (isClosedToolStart(events, i)) return null;
          return <ToolEvent key={key} ev={ev} onViewEvidence={onViewEvidence} />;
        }
        if (kind === "plan")
          return <PlanEvent key={key} ev={ev} onViewEvidence={onViewEvidence} />;
        if (kind === "message")
          return (
            <MessageEvent key={key} ev={ev} onViewEvidence={onViewEvidence} />
          );
        return (
          <p key={key} className="timeline2-system">
            {SYSTEM_LABEL[ev.type] || ev.type}
          </p>
        );
      })}

      {awaitingFirstToken ? <SkeletonLines /> : <StreamEvent />}
      <div ref={bottomRef} />
    </div>
  );
}
