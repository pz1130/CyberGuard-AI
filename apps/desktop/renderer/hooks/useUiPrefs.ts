import { useCallback, useEffect, useState } from "react";
import { useTheme } from "./useTheme";

export type FontSize = "small" | "medium" | "large";

const FONT_KEY = "cg.font_size";
const SIDEBAR_KEY = "cg.sidebar_collapsed";
const RAIL_KEY = "cg.rail_collapsed";

function applyFont(size: FontSize) {
  document.documentElement.dataset.font = size;
}

function readFont(): FontSize {
  try {
    const v = localStorage.getItem(FONT_KEY);
    if (v === "small" || v === "medium" || v === "large") return v;
  } catch {
    /* ignore */
  }
  return "medium";
}

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  return fallback;
}

function mediaBelow(px: number): boolean {
  return window.matchMedia?.(`(max-width: ${px}px)`).matches ?? false;
}

export function useUiPrefs() {
  const { theme, setTheme, resolved, cycleTheme } = useTheme();
  const [fontSize, setFontSizeState] = useState<FontSize>(() => readFont());
  // 断点只在初始化读一次；不监听 resize，否则拖窗口会覆盖用户手动选择
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(() =>
    readFlag(SIDEBAR_KEY, mediaBelow(900))
  );
  const [railCollapsed, setRailCollapsedState] = useState(() =>
    readFlag(RAIL_KEY, mediaBelow(1180))
  );

  useEffect(() => {
    applyFont(fontSize);
  }, [fontSize]);

  useEffect(() => {
    const api = typeof window !== "undefined" ? window.cyberguard : undefined;
    if (!api?.prefsGet) return;
    void api
      .prefsGet()
      .then((p) => {
        const t = p?.theme;
        if (t === "dark" || t === "light" || t === "system") {
          setTheme(t);
        }
        const f = p?.font_size;
        if (f === "small" || f === "medium" || f === "large") {
          setFontSizeState(f);
          try {
            localStorage.setItem(FONT_KEY, f);
          } catch {
            /* ignore */
          }
          applyFont(f);
        }
      })
      .catch(() => undefined);
  }, [setTheme]);

  const setFontSize = useCallback((size: FontSize) => {
    setFontSizeState(size);
    try {
      localStorage.setItem(FONT_KEY, size);
    } catch {
      /* ignore */
    }
    applyFont(size);
  }, []);

  const setSidebarCollapsed = useCallback((v: boolean) => {
    setSidebarCollapsedState(v);
    try {
      localStorage.setItem(SIDEBAR_KEY, v ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  const setRailCollapsed = useCallback((v: boolean) => {
    setRailCollapsedState(v);
    try {
      localStorage.setItem(RAIL_KEY, v ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  return {
    theme,
    setTheme,
    resolved,
    cycleTheme,
    fontSize,
    setFontSize,
    sidebarCollapsed,
    setSidebarCollapsed,
    railCollapsed,
    setRailCollapsed,
  };
}
