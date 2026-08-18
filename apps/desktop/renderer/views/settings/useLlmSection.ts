import { useCallback, useEffect, useMemo, useState } from "react";
import {
  findPreset,
  isLocalBaseUrl,
  matchPresetByBaseUrl,
  type LlmPreset,
} from "../../lib/llmPresets";
import type { ProviderPublic } from "../../lib/types";

export function useLlmSection(onProviderSaved?: (mode: string) => void) {
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const [mode, setMode] = useState("mock");
  const [presetId, setPresetId] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("gpt-4o-mini");
  const [temperature, setTemperature] = useState("0.3");
  const [apiKey, setApiKey] = useState("");
  const [hasKey, setHasKey] = useState(false);
  const [llmMsg, setLlmMsg] = useState<string | null>(null);
  const [llmBusy, setLlmBusy] = useState(false);

  const preset = useMemo(() => findPreset(presetId), [presetId]);
  const requiresKey = useMemo(() => {
    if (isLocalBaseUrl(baseUrl)) return false;
    if (preset) return preset.requiresKey;
    return true;
  }, [baseUrl, preset]);

  const loadProvider = useCallback(async () => {
    if (!api?.providerGet) return;
    try {
      const p: ProviderPublic = await api.providerGet();
      setMode(p.mode || "mock");
      setBaseUrl(p.base_url || "https://api.openai.com/v1");
      setModel(p.model || "gpt-4o-mini");
      setTemperature(String(p.temperature ?? 0.3));
      setHasKey(Boolean(p.has_api_key));
      setApiKey("");
      const pid =
        p.preset_id ||
        matchPresetByBaseUrl(p.base_url || "")?.id ||
        "custom";
      setPresetId(pid);
    } catch (e) {
      setLlmMsg(String(e));
    }
  }, [api]);

  useEffect(() => {
    void loadProvider();
  }, [loadProvider]);

  const applyPreset = (p: LlmPreset) => {
    setPresetId(p.id);
    setBaseUrl(p.baseUrl);
    if (p.models.length) {
      setModel(p.models[0]);
    }
    if (p.id !== "mock") {
      // Selecting a real preset implies live (user can still switch to mock)
      if (mode === "mock") setMode("live");
    }
  };

  const onSaveLlm = async () => {
    if (!api?.providerSet) {
      setLlmMsg("provider API unavailable (open via Electron)");
      return;
    }
    if (mode === "live" && requiresKey && !hasKey && !apiKey.trim()) {
      setLlmMsg("该供应商需要 API key，请先填写");
      return;
    }
    setLlmBusy(true);
    setLlmMsg(null);
    try {
      const payload: {
        mode: string;
        base_url: string;
        model: string;
        temperature: number;
        api_key?: string;
        preset_id?: string;
      } = {
        mode,
        base_url: baseUrl,
        model,
        temperature: Number(temperature) || 0.3,
        preset_id: presetId,
      };
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      const r = await api.providerSet(payload);
      setHasKey(Boolean(r.has_api_key));
      setApiKey("");
      const eff = r.effective?.mode || r.mode || mode;
      setLlmMsg(
        r.ok === false
          ? "save failed"
          : `已保存 · ${eff}${r.local ? " · 本地" : ""}${r.has_api_key ? " · key ✓" : requiresKey ? " · 无 key" : " · 无需 key"}`
      );
      onProviderSaved?.(String(eff));
    } catch (e) {
      setLlmMsg(String(e));
    } finally {
      setLlmBusy(false);
    }
  };

  const onTestLlm = async () => {
    if (!api?.providerTest) {
      setLlmMsg("provider test unavailable");
      return;
    }
    setLlmBusy(true);
    setLlmMsg(null);
    try {
      // Ensure latest form is saved-ish: test uses server-side config
      await onSaveLlm();
      const r = await api.providerTest();
      if (r.ok) {
        setLlmMsg(
          `连通 OK · ${r.mode || "?"} · ${r.latency_ms ?? "?"}ms` +
            (r.message ? ` · ${r.message}` : "")
        );
      } else {
        setLlmMsg(`连通失败 · ${r.error || "unknown"}`);
      }
    } catch (e) {
      setLlmMsg(String(e));
    } finally {
      setLlmBusy(false);
    }
  };

  return {
    mode,
    setMode,
    presetId,
    setPresetId,
    baseUrl,
    setBaseUrl,
    model,
    setModel,
    temperature,
    setTemperature,
    apiKey,
    setApiKey,
    hasKey,
    llmMsg,
    llmBusy,
    preset,
    requiresKey,
    applyPreset,
    onSaveLlm,
    onTestLlm,
  };
}

export type LlmSectionModel = ReturnType<typeof useLlmSection>;
