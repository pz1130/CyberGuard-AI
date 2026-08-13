import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Caps, Ev, Tier } from "../lib/types";
import {
  deriveDegradations,
  initialEnvState,
  type Degradation,
  type EnvState,
} from "./degradations";

export type EnvironmentContextValue = EnvState & {
  degradations: Degradation[];
  securityDegradations: Degradation[];
  refreshProvider: () => Promise<void>;
  setProviderMode: (m: string) => void;
  setEvidenceCount: (n: number) => void;
  ingest: (ev: Ev) => void;
};

const EnvironmentContext = createContext<EnvironmentContextValue | null>(null);

export function EnvironmentProvider({
  children,
  tier,
}: {
  children: ReactNode;
  tier: Tier;
}) {
  const [env, setEnv] = useState<EnvState>(initialEnvState);
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const patch = useCallback((p: Partial<EnvState>) => {
    setEnv((prev) => ({ ...prev, ...p }));
  }, []);

  // ping：拉一次环境全貌
  useEffect(() => {
    if (!api) {
      patch({ pingOk: false });
      return;
    }
    api
      .ping()
      .then((r: Record<string, unknown>) => {
        const prov = r?.provider as { mode?: string } | undefined;
        const sb = r?.sandbox as { sandbox_impl?: string } | undefined;
        const defaults = r?.policy_defaults as
          | { readonly?: { sandbox_mode?: string } }
          | undefined;
        const fv = r?.filevault as { warning?: string | null } | undefined;
        const tcc = r?.tcc as
          | {
              summary?: string;
              warning?: string | null;
              guidance?: string | null;
              full_disk_access?: boolean | null;
            }
          | undefined;

        let tccSummary = initialEnvState.tccSummary;
        if (tcc?.summary) tccSummary = String(tcc.summary);
        else if (tcc?.full_disk_access === true) tccSummary = "fda_likely";
        else if (tcc?.full_disk_access === false) tccSummary = "restricted";

        patch({
          pingOk: true,
          dataRoot: typeof r?.data_root === "string" ? r.data_root : "",
          providerMode: prov?.mode ? String(prov.mode) : "mock",
          sandboxImpl: sb?.sandbox_impl ? String(sb.sandbox_impl) : "unknown",
          sandboxMode: defaults?.readonly?.sandbox_mode
            ? String(defaults.readonly.sandbox_mode)
            : "—",
          fvWarning: fv?.warning || null,
          tccSummary,
          tccWarning: tcc?.warning || null,
          tccGuidance: tcc?.guidance || null,
          evidenceCount:
            typeof r?.evidence_count === "number" ? r.evidence_count : 0,
        });

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

  const ingest = useCallback(
    (ev: Ev) => {
      if (ev.type === "run_started" && Array.isArray(ev.mcp_tools)) {
        patch({ mcpTools: ev.mcp_tools.map(String) });
      }
    },
    [patch]
  );

  const refreshProvider = useCallback(async () => {
    if (!api?.providerGet) return;
    try {
      const p = await api.providerGet();
      patch({ providerMode: String(p.effective?.mode || p.mode || "mock") });
    } catch {
      /* 功能性失败，best-effort */
    }
  }, [api, patch]);

  const setProviderMode = useCallback(
    (m: string) => patch({ providerMode: m }),
    [patch]
  );
  const setEvidenceCount = useCallback(
    (n: number) => patch({ evidenceCount: n }),
    [patch]
  );

  const degradations = useMemo(() => deriveDegradations(env), [env]);
  const securityDegradations = useMemo(
    () => degradations.filter((d) => d.security),
    [degradations]
  );

  const value = useMemo<EnvironmentContextValue>(
    () => ({
      ...env,
      degradations,
      securityDegradations,
      refreshProvider,
      setProviderMode,
      setEvidenceCount,
      ingest,
    }),
    [
      env,
      degradations,
      securityDegradations,
      refreshProvider,
      setProviderMode,
      setEvidenceCount,
      ingest,
    ]
  );

  return (
    <EnvironmentContext.Provider value={value}>
      {children}
    </EnvironmentContext.Provider>
  );
}

export function useEnvironment(): EnvironmentContextValue {
  const ctx = useContext(EnvironmentContext);
  if (!ctx)
    throw new Error("useEnvironment must be used within EnvironmentProvider");
  return ctx;
}
