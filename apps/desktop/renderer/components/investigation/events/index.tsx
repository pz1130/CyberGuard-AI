import type { Ev } from "../../../lib/types";

export type EventKind = "tool" | "plan" | "message" | "system";

const TOOL = new Set(["tool_call_start", "tool_call_end"]);
const PLAN = new Set([
  "plan_ready",
  "plan_approved",
  "plan_rejected",
  "privilege_required",
  "privilege_decided",
]);
const MESSAGE = new Set([
  "user_task",
  "answer_ready",
  "error",
  "evidence_register",
  "evidence_registered",
]);

export function classify(ev: Ev): EventKind {
  if (TOOL.has(ev.type)) return "tool";
  if (PLAN.has(ev.type)) return "plan";
  if (MESSAGE.has(ev.type)) return "message";
  return "system";
}

/** Live start/end identity. Sidecar uses `name`; some payloads use `tool_name`. */
export function toolIdentity(ev: Ev): string {
  return String(ev.tool_name || ev.name);
}

/**
 * Append-only log: a start is closed if a later `tool_call_end` shares the name.
 * Only the unmatched in-flight start (if any) should render as running.
 */
export function isClosedToolStart(events: Ev[], index: number): boolean {
  const ev = events[index];
  if (!ev || ev.type !== "tool_call_start") return false;
  const id = toolIdentity(ev);
  for (let j = index + 1; j < events.length; j++) {
    const later = events[j];
    if (later.type === "tool_call_end" && toolIdentity(later) === id) return true;
  }
  return false;
}

export { MessageEvent } from "./MessageEvent";
export { PlanEvent } from "./PlanEvent";
export { SkeletonLines, StreamEvent } from "./StreamEvent";
export { ToolEvent } from "./ToolEvent";
