import type { Caps } from "../lib/types";

export type EnvState = {
  pingOk: boolean | null;
  caps: Caps | null;
  dataRoot: string;
  providerMode: string;
  sandboxImpl: string;
  sandboxMode: string;
  fvWarning: string | null;
  tccSummary: string;
  tccWarning: string | null;
  tccGuidance: string | null;
  evidenceCount: number;
  mcpTools: string[];
};

export const initialEnvState: EnvState = {
  pingOk: null,
  caps: null,
  dataRoot: "",
  providerMode: "mock",
  sandboxImpl: "unknown",
  sandboxMode: "—",
  fvWarning: null,
  tccSummary: "—",
  tccWarning: null,
  tccGuidance: null,
  evidenceCount: 0,
  mcpTools: [],
};

export type DegradationLevel = "warn" | "danger";

export type DegradationId =
  | "offline"
  | "sandbox"
  | "filevault"
  | "tcc"
  | "mock";

export type Degradation = {
  id: DegradationId;
  level: DegradationLevel;
  labelKey: string;
  detailKey: string;
  /** sidecar 回传原文；有则优先显示，不翻（spec §2.2） */
  detailText?: string;
  /** true = 安全边界降级，必须顶部浮出且用专属视觉（INV-38） */
  security: boolean;
};

/**
 * 从环境状态派生降级清单。
 * 纯函数，便于测试；顺序为 danger 在前、warn 在后。
 * 只产出 key；渲染侧用 t() 取文案。
 */
export function deriveDegradations(env: EnvState): Degradation[] {
  const out: Degradation[] = [];

  if (env.pingOk === false) {
    out.push({
      id: "offline",
      level: "danger",
      labelKey: "degradation.offline.label",
      detailKey: "degradation.offline.detail",
      security: true,
    });
  }

  if (env.sandboxImpl === "none") {
    out.push({
      id: "sandbox",
      level: "danger",
      labelKey: "degradation.sandbox.label",
      detailKey: "degradation.sandbox.detail",
      security: true,
    });
  }

  if (env.fvWarning) {
    out.push({
      id: "filevault",
      level: "danger",
      labelKey: "degradation.filevault.label",
      detailKey: "degradation.filevault.detail",
      detailText: env.fvWarning,
      security: true,
    });
  }

  if (env.tccSummary === "restricted" || env.tccWarning) {
    out.push({
      id: "tcc",
      level: "warn",
      labelKey: "degradation.tcc.label",
      detailKey: "degradation.tcc.detail",
      // sidecar 回传的原文，有就优先显示——它不是 UI 文案，不翻（spec §2.2）
      detailText: env.tccGuidance || env.tccWarning || undefined,
      security: true,
    });
  }

  if (env.providerMode !== "live") {
    out.push({
      id: "mock",
      level: "warn",
      labelKey: "degradation.mock.label",
      detailKey: "degradation.mock.detail",
      security: false,
    });
  }

  return out.sort((a, b) => {
    if (a.level === b.level) return 0;
    return a.level === "danger" ? -1 : 1;
  });
}
