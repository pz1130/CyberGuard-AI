/// <reference types="vite/client" />
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import en from "./en.json";
import zh from "./zh.json";
import { interpolate, pickPluralKey, type Resolved } from "./plural";

export type Language = "zh" | "en" | "system";

const LANG_KEY = "cg.language";
const TABLES: Record<Resolved, Record<string, string>> = { zh, en };

export function resolveLanguage(lang: Language): Resolved {
  if (lang === "zh" || lang === "en") return lang;
  const nav =
    typeof navigator !== "undefined" ? navigator.language || "" : "";
  return nav.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function readStored(): Language {
  try {
    const v = localStorage.getItem(LANG_KEY);
    if (v === "zh" || v === "en" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "system";
}

export type TFunc = (
  key: string,
  params?: Record<string, string | number>
) => string;

type I18nValue = {
  t: TFunc;
  language: Language;
  setLanguage: (l: Language) => void;
  resolved: Resolved;
};

const Ctx = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => readStored());
  const resolved = useMemo(() => resolveLanguage(language), [language]);

  useEffect(() => {
    document.documentElement.lang = resolved;
  }, [resolved]);

  const setLanguage = useCallback((l: Language) => {
    setLanguageState(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback<TFunc>(
    (key, params) => {
      const k =
        params && typeof params.count === "number"
          ? pickPluralKey(resolved, key, params.count)
          : key;
      const table = TABLES[resolved];
      let raw = table[k];
      if (raw === undefined) {
        // 回落到 zh，绝不回落到 key 名 —— 裸 key 出现在界面上比中文更糟
        raw = TABLES.zh[k];
        if (import.meta.env?.DEV) {
          console.warn(`[i18n] 缺 key: ${k}（locale=${resolved}）`);
        }
      }
      if (raw === undefined) return "";
      return interpolate(raw, params);
    },
    [resolved]
  );

  const value = useMemo(
    () => ({ t, language, setLanguage, resolved }),
    [t, language, setLanguage, resolved]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18nValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n 必须在 I18nProvider 内使用");
  return v;
}
