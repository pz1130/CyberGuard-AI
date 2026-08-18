import { createContext, useContext, type ReactNode } from "react";
import { useUiPrefs } from "../hooks/useUiPrefs";

type UiPrefsValue = ReturnType<typeof useUiPrefs>;

const Ctx = createContext<UiPrefsValue | null>(null);

export function UiPrefsProvider({ children }: { children: ReactNode }) {
  const value = useUiPrefs();
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUiPrefsCtx(): UiPrefsValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useUiPrefsCtx 必须在 UiPrefsProvider 内使用");
  return v;
}
