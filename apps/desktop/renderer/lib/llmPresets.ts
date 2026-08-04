/** OpenAI-compatible LLM provider presets for Settings UI. */

export type LlmPreset = {
  id: string;
  label: string;
  group: "cloud" | "china" | "local" | "other";
  /** Default OpenAI-compatible base URL (often …/v1) */
  baseUrl: string;
  /** Suggested models for the dropdown */
  models: string[];
  /** Whether an API key is required for live mode */
  requiresKey: boolean;
  /** Short help under the form */
  hint?: string;
  /** Optional docs URL (shown as text only) */
  docs?: string;
};

export const LLM_PRESETS: LlmPreset[] = [
  {
    id: "openai",
    label: "OpenAI",
    group: "cloud",
    baseUrl: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini"],
    requiresKey: true,
    hint: "官方 OpenAI API",
  },
  {
    id: "azure-openai",
    label: "Azure OpenAI",
    group: "cloud",
    baseUrl: "https://YOUR_RESOURCE.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT",
    models: ["gpt-4o", "gpt-4o-mini"],
    requiresKey: true,
    hint: "将 URL 换成你的 resource/deployment；api-version 可拼在 query",
  },
  {
    id: "anthropic",
    label: "Anthropic (OpenAI 兼容代理)",
    group: "cloud",
    baseUrl: "https://api.anthropic.com/v1",
    models: ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"],
    requiresKey: true,
    hint: "需兼容 OpenAI chat/completions 的网关；原生 Anthropic 协议不在此列",
  },
  {
    id: "google-gemini",
    label: "Google Gemini",
    group: "cloud",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    models: ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    requiresKey: true,
    hint: "Gemini 官方 OpenAI 兼容端点",
  },
  {
    id: "groq",
    label: "Groq",
    group: "cloud",
    baseUrl: "https://api.groq.com/openai/v1",
    models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    requiresKey: true,
  },
  {
    id: "together",
    label: "Together AI",
    group: "cloud",
    baseUrl: "https://api.together.xyz/v1",
    models: [
      "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
      "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    ],
    requiresKey: true,
  },
  {
    id: "fireworks",
    label: "Fireworks",
    group: "cloud",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    models: ["accounts/fireworks/models/llama-v3p1-70b-instruct"],
    requiresKey: true,
  },
  {
    id: "mistral",
    label: "Mistral",
    group: "cloud",
    baseUrl: "https://api.mistral.ai/v1",
    models: ["mistral-large-latest", "mistral-small-latest", "codestral-latest"],
    requiresKey: true,
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    group: "china",
    baseUrl: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"],
    requiresKey: true,
  },
  {
    id: "moonshot",
    label: "Moonshot (Kimi)",
    group: "china",
    baseUrl: "https://api.moonshot.cn/v1",
    models: ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2-turbo-preview"],
    requiresKey: true,
  },
  {
    id: "zhipu",
    label: "智谱 GLM",
    group: "china",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    models: ["glm-4-plus", "glm-4-flash", "glm-4-air"],
    requiresKey: true,
  },
  {
    id: "qwen",
    label: "通义千问 (DashScope)",
    group: "china",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
    requiresKey: true,
  },
  {
    id: "baichuan",
    label: "百川",
    group: "china",
    baseUrl: "https://api.baichuan-ai.com/v1",
    models: ["Baichuan4", "Baichuan3-Turbo"],
    requiresKey: true,
  },
  {
    id: "minimax",
    label: "MiniMax",
    group: "china",
    baseUrl: "https://api.minimaxi.com/v1",
    models: ["MiniMax-M3", "MiniMax-Text-01", "abab6.5s-chat"],
    requiresKey: true,
  },
  {
    id: "yi",
    label: "零一万物 Yi",
    group: "china",
    baseUrl: "https://api.lingyiwanwu.com/v1",
    models: ["yi-lightning", "yi-large", "yi-medium"],
    requiresKey: true,
  },
  {
    id: "stepfun",
    label: "阶跃星辰 StepFun",
    group: "china",
    baseUrl: "https://api.stepfun.com/v1",
    models: ["step-2-16k", "step-1-8k"],
    requiresKey: true,
  },
  {
    id: "siliconflow",
    label: "SiliconFlow 硅基流动",
    group: "china",
    baseUrl: "https://api.siliconflow.cn/v1",
    models: [
      "deepseek-ai/DeepSeek-V3",
      "Qwen/Qwen2.5-72B-Instruct",
      "THUDM/glm-4-9b-chat",
    ],
    requiresKey: true,
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    group: "other",
    baseUrl: "https://openrouter.ai/api/v1",
    models: [
      "openai/gpt-4o-mini",
      "anthropic/claude-sonnet-4",
      "google/gemini-2.5-flash",
    ],
    requiresKey: true,
    hint: "统一路由多模型，注意模型 ID 格式",
  },
  {
    id: "xai",
    label: "xAI Grok",
    group: "cloud",
    baseUrl: "https://api.x.ai/v1",
    models: ["grok-3", "grok-3-mini", "grok-2-latest"],
    requiresKey: true,
  },
  // —— Local ——
  {
    id: "ollama",
    label: "Ollama（本地）",
    group: "local",
    baseUrl: "http://127.0.0.1:11434/v1",
    models: ["llama3.2", "llama3.1", "qwen2.5", "mistral", "deepseek-r1", "phi4"],
    requiresKey: false,
    hint: "无需 API key。先 ollama serve 并 pull 模型；模型名与 ollama list 一致",
  },
  {
    id: "lmstudio",
    label: "LM Studio（本地）",
    group: "local",
    baseUrl: "http://127.0.0.1:1234/v1",
    models: ["local-model"],
    requiresKey: false,
    hint: "在 LM Studio 开启本地 Server，模型名填已加载模型",
  },
  {
    id: "llamacpp",
    label: "llama.cpp server（本地）",
    group: "local",
    baseUrl: "http://127.0.0.1:8080/v1",
    models: ["local"],
    requiresKey: false,
    hint: "llama-server --port 8080，OpenAI 兼容",
  },
  {
    id: "vllm",
    label: "vLLM（本地/内网）",
    group: "local",
    baseUrl: "http://127.0.0.1:8000/v1",
    models: ["default"],
    requiresKey: false,
    hint: "vllm serve … --port 8000",
  },
  {
    id: "localai",
    label: "LocalAI",
    group: "local",
    baseUrl: "http://127.0.0.1:8080/v1",
    models: ["gpt-4", "gpt-3.5-turbo"],
    requiresKey: false,
  },
  {
    id: "jan",
    label: "Jan.ai（本地）",
    group: "local",
    baseUrl: "http://127.0.0.1:1337/v1",
    models: ["local"],
    requiresKey: false,
  },
  {
    id: "custom",
    label: "自定义 OpenAI 兼容",
    group: "other",
    baseUrl: "http://127.0.0.1:8000/v1",
    models: [],
    requiresKey: false,
    hint: "任意兼容 /v1/chat/completions 的端点",
  },
];

export const PRESET_GROUPS: { id: LlmPreset["group"]; label: string }[] = [
  { id: "local", label: "本地模型" },
  { id: "china", label: "国内云" },
  { id: "cloud", label: "国际云" },
  { id: "other", label: "其他 / 自定义" },
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
