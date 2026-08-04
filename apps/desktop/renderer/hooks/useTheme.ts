import { useCallback, useEffect, useMemo, useState } from "react";
import type { ThemeMode } from "../lib/types";

const STORAGE_KEY = "cg.theme";

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches
  );
}

function resolveTheme(mode: ThemeMode): "dark" | "light" {
  if (mode === "system") return systemPrefersDark() ? "dark" : "light";
  return mode;
}

function applyDom(resolved: "dark" | "light") {
  document.documentElement.dataset.theme = resolved;
}

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "dark" || v === "light" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "dark";
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() => readStored());

  const resolved = useMemo(() => resolveTheme(theme), [theme]);

  useEffect(() => {
    applyDom(resolved);
  }, [resolved]);

  // Prefer ui.prefs from sidecar when available (P1); fall back to localStorage
  useEffect(() => {
    const api = typeof window !== "undefined" ? window.cyberguard : undefined;
    if (!api?.prefsGet) return;
    void api
      .prefsGet()
      .then((p) => {
        const t = p?.theme;
        if (t === "dark" || t === "light" || t === "system") {
          setThemeState(t);
          try {
            localStorage.setItem(STORAGE_KEY, t);
          } catch {
            /* ignore */
          }
          applyDom(resolveTheme(t));
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyDom(resolveTheme("system"));
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, [theme]);

  const setTheme = useCallback((mode: ThemeMode) => {
    setThemeState(mode);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* ignore */
    }
    applyDom(resolveTheme(mode));
  }, []);

  const cycleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : theme === "light" ? "system" : "dark");
  }, [theme, setTheme]);

  return { theme, setTheme, resolved, cycleTheme };
}
