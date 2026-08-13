import { useEffect, useRef } from "react";
import type { Caps, Tier } from "../lib/types";
import { initialEnvState, type EnvState } from "./degradations";
import { extractPausedRunId, parsePing } from "./envParse";

type Api = NonNullable<Window["cyberguard"]>;

/**
 * 环境状态与 sidecar 的同步 —— 两个 effect 从 EnvironmentProvider 抽出，
 * 让那边只剩「持有 state + 派生 + 提供 context」。
 *
 * ping 失败一律落到 pingOk: false，由 deriveDegradations 转成 danger 级
 * 安全降级。这里不许 catch 了不动（P5 / INV-25：安全边界失败必须响）。
 */
export function useEnvSync({
  api,
  tier,
  patch,
  onPausedRuns,
}: {
  api: Api | undefined;
  tier: Tier;
  patch: (p: Partial<EnvState>) => void;
  onPausedRuns?: (runId: string) => void;
}) {
  // 用 ref 持有回调，避免调用方传内联箭头导致 effect 反复重跑
  const onPausedRunsRef = useRef(onPausedRuns);
  onPausedRunsRef.current = onPausedRuns;

  // ping：拉一次环境全貌
  useEffect(() => {
    if (!api) {
      patch({ pingOk: false });
      return;
    }
    api
      .ping()
      .then((r: Record<string, unknown>) => {
        patch(parsePing(r));

        const pausedRunId = extractPausedRunId(r);
        if (pausedRunId) onPausedRunsRef.current?.(pausedRunId);

        // 与 provider.get 对账（secrets 载入后的实际 live/mock）
        void api.providerGet?.().then((p) => {
          const eff = p?.effective?.mode || p?.mode;
          if (eff) patch({ providerMode: String(eff) });
        });
      })
      .catch(() => patch({ pingOk: false }));
  }, [api, patch]);

  // caps 随档位变化
  useEffect(() => {
    if (!api) return;
    api
      .capabilities(tier)
      .then((c: Caps) => {
        patch({
          caps: c,
          sandboxMode: c.policy?.sandbox_mode
            ? String(c.policy.sandbox_mode)
            : initialEnvState.sandboxMode,
        });
      })
      .catch(() => patch({ caps: null }));
  }, [api, tier, patch]);
}
