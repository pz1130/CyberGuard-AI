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

export { MessageEvent } from "./MessageEvent";
export { PlanEvent } from "./PlanEvent";
export { SkeletonLines, StreamEvent } from "./StreamEvent";
export { ToolEvent } from "./ToolEvent";
