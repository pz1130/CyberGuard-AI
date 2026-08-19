import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n/I18nProvider";
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
import { TimelineEmpty } from "./TimelineEmpty";
import "./Timeline.css";

const SYSTEM_LABEL_KEY: Record<string, string> = {
  start: "timeline.system.start",
  run_started: "timeline.system.runStarted",
  run_paused: "timeline.system.runPaused",
  run_resumed: "timeline.system.runResumed",
  episodic_recall: "timeline.system.episodicRecall",
  episodic_recorded: "timeline.system.episodicRecorded",
  auth_bounds_check: "timeline.system.authBounds",
  policy_event: "timeline.system.policyEvent",
  token_done: "timeline.system.tokenDone",
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
  const { t } = useI18n();

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    bottomRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
  }, [events.length, streaming]);

  // 已提交但首包未到：显示骨架。正文流只给 StreamEvent 订阅。
  const awaitingFirstToken =
    status === "running" && !streaming && events.length <= 1;

  // 未跑过任何事：中间栏是视线落点，不能空着
  if (events.length === 0 && !streaming && status === "idle") {
    return (
      <div className="timeline2">
        <TimelineEmpty />
      </div>
    );
  }

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
        const labelKey = SYSTEM_LABEL_KEY[ev.type];
        return (
          <p key={key} className="timeline2-system">
            {labelKey ? t(labelKey) : ev.type}
          </p>
        );
      })}

      {awaitingFirstToken ? <SkeletonLines /> : <StreamEvent />}
      <div ref={bottomRef} />
    </div>
  );
}
