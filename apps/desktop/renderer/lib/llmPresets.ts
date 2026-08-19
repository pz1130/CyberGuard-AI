/** OpenAI-compatible LLM provider presets for Settings UI. */

export type LlmPreset = {
  id: string;
  labelKey: string;
  group: "cloud" | "china" | "local" | "other";
  /** Default OpenAI-compatible base URL (often …/v1) */
  baseUrl: string;
  /** Suggested models for the dropdown */
  models: string[];
  /** Whether an API key is required for live mode */
  requiresKey: boolean;
  /** i18n key for short help under the form */
  hintKey?: string;
  /** Optional docs URL (shown as text only) */
  docs?: string;
};

export const LLM_PRESETS: LlmPreset[] = [
  {
    id: "openai",
    labelKey: "llm.preset.openai.label",
    group: "cloud",
    baseUrl: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini"],
    requiresKey: true,
    hintKey: "llm.preset.openai.hint",
  },
  {
    id: "azure-openai",
    labelKey: "llm.preset.azure-openai.label",
    group: "cloud",
    baseUrl: "https://YOUR_RESOURCE.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT",
    models: ["gpt-4o", "gpt-4o-mini"],
    requiresKey: true,
    hintKey: "llm.preset.azure-openai.hint",
  },
  {
    id: "anthropic",
    labelKey: "llm.preset.anthropic.label",
    group: "cloud",
    baseUrl: "https://api.anthropic.com/v1",
    models: ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"],
    requiresKey: true,
    hintKey: "llm.preset.anthropic.hint",
  },
  {
    id: "google-gemini",
    labelKey: "llm.preset.google-gemini.label",
    group: "cloud",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    models: ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    requiresKey: true,
    hintKey: "llm.preset.google-gemini.hint",
  },
  {
    id: "groq",
    labelKey: "llm.preset.groq.label",
    group: "cloud",
    baseUrl: "https://api.groq.com/openai/v1",
    models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    requiresKey: true,
  },
  {
    id: "together",
    labelKey: "llm.preset.together.label",
    group: "cloud",
    baseUrl: "https://api.together.xyz/v1",
    models: ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"],
    requiresKey: true,
  },
  {
    id: "fireworks",
    labelKey: "llm.preset.fireworks.label",
    group: "cloud",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    models: ["accounts/fireworks/models/llama-v3p1-70b-instruct"],
    requiresKey: true,
  },
  {
    id: "mistral",
    labelKey: "llm.preset.mistral.label",
    group: "cloud",
    baseUrl: "https://api.mistral.ai/v1",
    models: ["mistral-large-latest", "mistral-small-latest", "codestral-latest"],
    requiresKey: true,
  },
  {
    id: "deepseek",
    labelKey: "llm.preset.deepseek.label",
    group: "china",
    baseUrl: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"],
    requiresKey: true,
  },
  {
    id: "moonshot",
    labelKey: "llm.preset.moonshot.label",
    group: "china",
    baseUrl: "https://api.moonshot.cn/v1",
    models: ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2-turbo-preview"],
    requiresKey: true,
  },
  {
    id: "zhipu",
    labelKey: "llm.preset.zhipu.label",
    group: "china",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    models: ["glm-4-plus", "glm-4-flash", "glm-4-air"],
    requiresKey: true,
  },
  {
    id: "qwen",
    labelKey: "llm.preset.qwen.label",
    group: "china",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
    requiresKey: true,
  },
  {
    id: "baichuan",
    labelKey: "llm.preset.baichuan.label",
    group: "china",
    baseUrl: "https://api.baichuan-ai.com/v1",
    models: ["Baichuan4", "Baichuan3-Turbo"],
    requiresKey: true,
  },
  {
    id: "minimax",
    labelKey: "llm.preset.minimax.label",
    group: "china",
    baseUrl: "https://api.minimaxi.com/v1",
    models: ["MiniMax-M3", "MiniMax-Text-01", "abab6.5s-chat"],
    requiresKey: true,
  },
  {
    id: "yi",
    labelKey: "llm.preset.yi.label",
    group: "china",
    baseUrl: "https://api.lingyiwanwu.com/v1",
    models: ["yi-lightning", "yi-large", "yi-medium"],
    requiresKey: true,
  },
  {
    id: "stepfun",
    labelKey: "llm.preset.stepfun.label",
    group: "china",
    baseUrl: "https://api.stepfun.com/v1",
    models: ["step-2-16k", "step-1-8k"],
    requiresKey: true,
  },
  {
    id: "siliconflow",
    labelKey: "llm.preset.siliconflow.label",
    group: "china",
    baseUrl: "https://api.siliconflow.cn/v1",
    models: ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct", "THUDM/glm-4-9b-chat"],
    requiresKey: true,
  },
  {
    id: "openrouter",
    labelKey: "llm.preset.openrouter.label",
    group: "other",
    baseUrl: "https://openrouter.ai/api/v1",
    models: ["openai/gpt-4o-mini", "anthropic/claude-sonnet-4", "google/gemini-2.5-flash"],
    requiresKey: true,
    hintKey: "llm.preset.openrouter.hint",
  },
  {
    id: "xai",
    labelKey: "llm.preset.xai.label",
    group: "cloud",
    baseUrl: "https://api.x.ai/v1",
    models: ["grok-3", "grok-3-mini", "grok-2-latest"],
    requiresKey: true,
  },
  {
    id: "ollama",
    labelKey: "llm.preset.ollama.label",
    group: "local",
    baseUrl: "http://127.0.0.1:11434/v1",
    models: ["llama3.2", "llama3.1", "qwen2.5", "mistral", "deepseek-r1", "phi4"],
    requiresKey: false,
    hintKey: "llm.preset.ollama.hint",
  },
  {
    id: "lmstudio",
    labelKey: "llm.preset.lmstudio.label",
    group: "local",
    baseUrl: "http://127.0.0.1:1234/v1",
    models: ["local-model"],
    requiresKey: false,
    hintKey: "llm.preset.lmstudio.hint",
  },
  {
    id: "llamacpp",
    labelKey: "llm.preset.llamacpp.label",
    group: "local",
    baseUrl: "http://127.0.0.1:8080/v1",
    models: ["local"],
    requiresKey: false,
    hintKey: "llm.preset.llamacpp.hint",
  },
  {
    id: "vllm",
    labelKey: "llm.preset.vllm.label",
    group: "local",
    baseUrl: "http://127.0.0.1:8000/v1",
    models: ["default"],
    requiresKey: false,
    hintKey: "llm.preset.vllm.hint",
  },
  {
    id: "localai",
    labelKey: "llm.preset.localai.label",
    group: "local",
    baseUrl: "http://127.0.0.1:8080/v1",
    models: ["gpt-4", "gpt-3.5-turbo"],
    requiresKey: false,
  },
  {
    id: "jan",
    labelKey: "llm.preset.jan.label",
    group: "local",
    baseUrl: "http://127.0.0.1:1337/v1",
    models: ["local"],
    requiresKey: false,
  },
  {
    id: "custom",
    labelKey: "llm.preset.custom.label",
    group: "other",
    baseUrl: "http://127.0.0.1:8000/v1",
    models: [],
    requiresKey: false,
    hintKey: "llm.preset.custom.hint",
  },
];

export const PRESET_GROUPS: { id: LlmPreset["group"]; labelKey: string }[] = [
  { id: "local", labelKey: "llm.group.local" },
  { id: "china", labelKey: "llm.group.china" },
  { id: "cloud", labelKey: "llm.group.cloud" },
  { id: "other", labelKey: "llm.group.other" },
];


export function findPreset(id: string | undefined | null): LlmPreset | undefined {
  if (!id) return undefined;
  return LLM_PRESETS.find((p) => p.id === id);
}

/** Best-effort match saved base_url to a preset. */
export function matchPresetByBaseUrl(baseUrl: string): LlmPreset | undefined {
  const u = (baseUrl || "").replace(/\/+$/, "").toLowerCase();
  if (!u) return undefined;

  // Port / local heuristics first (disambiguate shared localhost hosts)
  if (u.includes("11434")) return findPreset("ollama");
  if (u.includes(":1234")) return findPreset("lmstudio");
  if (u.includes(":1337")) return findPreset("jan");

  const sorted = [...LLM_PRESETS].sort(
    (a, b) => b.baseUrl.length - a.baseUrl.length
  );
  for (const p of sorted) {
    if (p.id === "custom" || p.id === "azure-openai") continue;
    if (p.baseUrl.toLowerCase().includes("your_resource")) continue;
    const pb = p.baseUrl.replace(/\/+$/, "").toLowerCase();
    if (u === pb || u.startsWith(pb + "/") || u.startsWith(pb)) return p;
    try {
      const host = new URL(
        p.baseUrl.includes("://") ? p.baseUrl : `http://${p.baseUrl}`
      ).host.toLowerCase();
      // Skip generic localhost host matches (already handled by port heuristics)
      if (
        host === "127.0.0.1" ||
        host === "localhost" ||
        host === "0.0.0.0"
      ) {
        continue;
      }
      if (u.includes(host)) return p;
    } catch {
      /* ignore */
    }
  }
  if (u.includes("127.0.0.1") || u.includes("localhost")) {
    return findPreset("custom");
  }
  return findPreset("custom");
}

/** Local / LAN OpenAI-compatible endpoints typically need no API key. */
export function isLocalBaseUrl(url: string): boolean {
  const u = (url || "").toLowerCase();
  return (
    u.includes("localhost") ||
    u.includes("127.0.0.1") ||
    u.includes("0.0.0.0") ||
    u.includes("[::1]") ||
    u.includes("host.docker.internal")
  );
}
