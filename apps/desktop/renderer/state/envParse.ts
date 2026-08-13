import { initialEnvState, type EnvState } from "./degradations";

/**
 * ping 响应的解析层。
 *
 * 拆成纯函数有两个理由：把 useEnvironment 压回可读长度；
 * 以及 sidecar 的 ping 结构层次很深、字段可选性复杂，
 * 解析逻辑本身值得单测，而不是只能靠跑起来试。
 */

type PingShape = {
  data_root?: unknown;
  provider?: { mode?: unknown } | null;
  sandbox?: { sandbox_impl?: unknown } | null;
  policy_defaults?: { readonly?: { sandbox_mode?: unknown } | null } | null;
  filevault?: { warning?: unknown } | null;
  tcc?: {
    summary?: unknown;
    warning?: unknown;
    guidance?: unknown;
    full_disk_access?: unknown;
  } | null;
  evidence_count?: unknown;
  paused_runs?: unknown;
};

function str(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}

/** TCC 状态优先取 summary；没有则从 full_disk_access 布尔推断 */
export function deriveTccSummary(tcc: PingShape["tcc"]): string {
  const summary = str(tcc?.summary);
  if (summary) return summary;
  if (tcc?.full_disk_access === true) return "fda_likely";
  if (tcc?.full_disk_access === false) return "restricted";
  return initialEnvState.tccSummary;
}

/** 把 ping 响应映射成 EnvState 的补丁。未知/缺失字段一律回落到初始值。 */
export function parsePing(raw: Record<string, unknown>): Partial<EnvState> {
  const r = raw as PingShape;
  return {
    pingOk: true,
    dataRoot: str(r.data_root) ?? "",
    providerMode: str(r.provider?.mode) ?? "mock",
    sandboxImpl: str(r.sandbox?.sandbox_impl) ?? "unknown",
    sandboxMode:
      str(r.policy_defaults?.readonly?.sandbox_mode) ??
      initialEnvState.sandboxMode,
    fvWarning: str(r.filevault?.warning),
    tccSummary: deriveTccSummary(r.tcc),
    tccWarning: str(r.tcc?.warning),
    tccGuidance: str(r.tcc?.guidance),
    evidenceCount:
      typeof r.evidence_count === "number" ? r.evidence_count : 0,
  };
}

/** ping 会带回未完结的暂停运行，取第一条的 run_id 用于恢复暂停态 */
export function extractPausedRunId(raw: Record<string, unknown>): string | null {
  const list = (raw as PingShape).paused_runs;
  if (!Array.isArray(list) || list.length === 0) return null;
  const first = list[0] as { run_id?: unknown } | undefined;
  return str(first?.run_id);
}
