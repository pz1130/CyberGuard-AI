import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Ev, Tier } from "../lib/types";
import {
  deriveDegradations,
  initialEnvState,
  type Degradation,
  type EnvState,
} from "./degradations";
import { useEnvSync } from "./useEnvSync";

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
  onPausedRuns,
}: {
  children: ReactNode;
  tier: Tier;
  onPausedRuns?: (runId: string) => void;
}) {
  const [env, setEnv] = useState<EnvState>(initialEnvState);
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const patch = useCallback((p: Partial<EnvState>) => {
    setEnv((prev) => ({ ...prev, ...p }));
  }, []);

  useEnvSync({ api, tier, patch, onPausedRuns });

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
