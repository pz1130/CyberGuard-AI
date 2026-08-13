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
  label: string;
  detail?: string;
  /** true = 安全边界降级，必须顶部浮出且用专属视觉（INV-38） */
  security: boolean;
};

/**
 * 从环境状态派生降级清单。
 * 纯函数，便于测试；顺序为 danger 在前、warn 在后。
 */
export function deriveDegradations(env: EnvState): Degradation[] {
  const out: Degradation[] = [];

  if (env.pingOk === false) {
    out.push({
      id: "offline",
      level: "danger",
      label: "sidecar 离线",
      detail: "本地执行进程未连接，运行已禁用",
      security: true,
    });
  }

  if (env.sandboxImpl === "none") {
    out.push({
      id: "sandbox",
      level: "danger",
      label: "沙箱不可用",
      detail: "仅允许只读档位（INV-16）",
      security: true,
    });
  }

  if (env.fvWarning) {
    out.push({
      id: "filevault",
      level: "danger",
      label: "FileVault 未开启",
      detail: env.fvWarning,
      security: true,
    });
  }

  if (env.tccSummary === "restricted" || env.tccWarning) {
    out.push({
      id: "tcc",
      level: "warn",
      label: "磁盘访问受限",
      detail: env.tccGuidance || env.tccWarning || "部分目录读取会失败",
      security: true,
    });
  }

  if (env.providerMode !== "live") {
    out.push({
      id: "mock",
      level: "warn",
      label: "模型为 mock",
      detail: "未配置真实模型，输出不可用于结论",
      security: false,
    });
  }

  return out.sort((a, b) => {
    if (a.level === b.level) return 0;
    return a.level === "danger" ? -1 : 1;
  });
}
