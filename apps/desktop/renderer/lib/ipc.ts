import type { Caps, Ev, SessionRow, Tier } from "./types";

export function getApi() {
  return typeof window !== "undefined" ? window.cyberguard : undefined;
}

export async function ping() {
  return getApi()?.ping();
}

export async function capabilities(tier: Tier): Promise<Caps | undefined> {
  return getApi()?.capabilities(tier);
}

export async function run(task: string, tier: Tier, sessionId?: string) {
  return getApi()?.run(task, tier, sessionId);
}

export async function abort(runId: string) {
  return getApi()?.abort(runId);
}

export async function steer(runId: string, message: string) {
  return getApi()?.steer(runId, message);
}

export async function listSessions(): Promise<SessionRow[]> {
  const r = await getApi()?.listSessions();
  return r?.sessions || [];
}

export async function sessionEvents(sessionId: string): Promise<Ev[]> {
  const r = await getApi()?.sessionEvents(sessionId);
  return r?.events || [];
}

export function onEvent(handler: (ev: Ev) => void): () => void {
  return getApi()?.onEvent(handler) || (() => undefined);
}
